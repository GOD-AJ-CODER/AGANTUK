"""
core/preprocessor.py — Image ingestion and pre-processing pipeline.

Rules reference: rules.md Stage 1 & architecture.md Stage A:
  - Rule 1.2: Laplacian motion-blur check (variance < 100.0) -> HTTP 400
              "Image too blurry. Hold device steady."
  - Rule 1.3: 4-point contour detection + perspective warp -> flat rectangle.
              Contour not found OR bounding angle > 45.0° -> HTTP 400
              "Position full document within frame."
              Graceful Degradation fallback: if document boundary was found
              but warp fails post-detection, fall back to whole image and append
              WARP_FAILED_FULL_FRAME_USED to failure codes (never drop scan).
  - Rule 1.4: Specular glare masking in HSV space (V > 240) over OCR key zones
              (Name, DOB, MRZ) -> HTTP 400
              "Glare detected over key text fields. Adjust lighting or turn off flash."
"""

import base64
import logging
import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import cv2
import numpy as np

from app.config import settings
from app.core.exceptions import ImageQualityError, PayloadError
from app.schemas.errors import ErrorCode
from app.schemas.verification import FailureCode

logger = logging.getLogger(__name__)


# ─── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class PreprocessorResult:
    """Result of the Stage 1 preprocessor pipeline."""

    warped_image: np.ndarray
    warped_image_b64: str
    laplacian_variance: float
    bounding_angle: float
    glare_detected: bool
    warp_fallback_used: bool
    quality_flags: list[str] = field(default_factory=list)
    blur_passed: bool = True
    contour_passed: bool = True
    angle_passed: bool = True
    glare_passed: bool = True
    crop_width: int = 0
    crop_height: int = 0


# ─── Image Encoding / Decoding Helpers ────────────────────────────────────────


def decode_image(image_input: str | bytes | np.ndarray) -> np.ndarray:
    """
    Decode image input (base64 string, raw bytes, or numpy array) into a BGR numpy array.

    Raises:
        PayloadError(PAYLOAD_IMAGE_MISSING): If input is empty.
        PayloadError(PAYLOAD_IMAGE_DECODE_FAILED): If decoding fails.
    """
    if image_input is None:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
            message="No image data provided.",
        )

    if isinstance(image_input, np.ndarray):
        if image_input.size == 0:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                message="Image array is empty.",
            )
        return image_input

    raw_bytes: bytes
    if isinstance(image_input, str):
        cleaned = image_input.strip()
        if not cleaned:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                message="Image base64 string is empty.",
            )
        # Strip data URI scheme prefix if present (e.g. data:image/jpeg;base64,...)
        if "," in cleaned and cleaned.startswith("data:"):
            cleaned = cleaned.split(",", 1)[1].strip()

        try:
            raw_bytes = base64.b64decode(cleaned)
        except Exception as exc:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_DECODE_FAILED,
                message="Invalid base64 encoding in image payload.",
                detail=str(exc),
            ) from exc
    elif isinstance(image_input, bytes):
        raw_bytes = image_input
    else:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_INVALID,
            message=f"Unsupported image input type: {type(image_input).__name__}",
        )

    if len(raw_bytes) == 0:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
            message="Raw image byte buffer is empty.",
        )

    nparr = np.frombuffer(raw_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None or image.size == 0:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_IMAGE_DECODE_FAILED,
            message="Failed to decode image buffer into a valid image.",
        )

    return image


def encode_image_b64(
    image: np.ndarray, format_ext: str = ".jpg", quality: int = 95
) -> str:
    """Encode BGR numpy array to base64 JPEG/PNG string."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(format_ext, image, encode_params)
    if not success:
        raise RuntimeError("Failed to encode image to buffer.")
    return base64.b64encode(buffer).decode("utf-8")


# ─── Rule 1.2 — Laplacian Motion-Blur Check ───────────────────────────────────


def compute_laplacian_variance(image: np.ndarray) -> float:
    """
    Compute Laplacian variance (sigma^2) of grayscale image.
    Rule 1.2: Grayscale crop -> cv2.Laplacian() -> variance sigma^2.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(laplacian.var())
    return variance


def check_motion_blur(
    image: np.ndarray, threshold: Optional[float] = None
) -> tuple[float, bool]:
    """
    Check if image passes the Laplacian motion blur threshold.

    Returns:
        (variance, passed)
    """
    limit = (
        threshold
        if threshold is not None
        else settings.LAPLACIAN_VARIANCE_THRESHOLD
    )
    variance = compute_laplacian_variance(image)
    passed = variance >= limit
    return variance, passed


# ─── Rule 1.3 — Contour Detection & Perspective Warp ──────────────────────────


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 (x, y) coordinates clockwise:
    [top-left, top-right, bottom-right, bottom-left].
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)

    # Top-left has smallest x + y sum; bottom-right has largest x + y sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # Top-right has smallest y - x difference; bottom-left has largest y - x difference
    diff = pts[:, 1] - pts[:, 0]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def calculate_bounding_angle(rect: np.ndarray) -> float:
    """
    Calculate orientation angle (in degrees) of a quadrilateral relative to the frame.

    rect: coordinates of the 4 corners.
    Combines minAreaRect bounding angle with ordered edge vectors to detect tilt.
    """
    min_rect = cv2.minAreaRect(rect)
    raw_angle = min_rect[2]
    mag = abs(raw_angle)
    if mag == 90.0 or mag == 0.0:
        angle_rect = 0.0
    else:
        angle_rect = float(mag)

    ordered = order_points(rect)
    tl, tr, br, bl = ordered

    # Top edge vector (dx, dy)
    dx_top = tr[0] - tl[0]
    dy_top = tr[1] - tl[1]
    angle_top = abs(math.degrees(math.atan2(dy_top, dx_top)))
    if angle_top > 90.0:
        angle_top = 180.0 - angle_top

    # Left edge vector (dx, dy)
    dx_left = bl[0] - tl[0]
    dy_left = bl[1] - tl[1]
    angle_left = abs(math.degrees(math.atan2(dx_left, dy_left)))
    if angle_left > 90.0:
        angle_left = 180.0 - angle_left

    edge_angle = max(angle_top, angle_left)
    angle = max(angle_rect, edge_angle)
    return float(angle)


def detect_document_contour(
    image: np.ndarray,
    min_area_ratio: float = 0.10,
) -> tuple[Optional[np.ndarray], float]:
    """
    Locate the 4 document corners and compute the bounding angle.

    Rule 1.3:
      cv2.findContours -> approximate to 4-point polygon -> affine perspective transform.

    Returns:
        (ordered_points, bounding_angle_deg)
        ordered_points is None if no valid document contour was found.
    """
    height, width = image.shape[:2]
    img_area = float(height * width)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive / Canny edge detection
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    candidate_rect: Optional[np.ndarray] = None
    max_area = 0.0

    # Sort contours by area descending
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for c in contours:
        area = cv2.contourArea(c)
        if area < img_area * min_area_ratio:
            continue

        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        if len(approx) == 4 and cv2.isContourConvex(approx):
            candidate_rect = order_points(approx)
            max_area = area
            break

    # If no strict 4-point approx found, check rotated bounding rectangle of largest significant contour
    if candidate_rect is None and contours:
        largest = contours[0]
        largest_area = cv2.contourArea(largest)
        if largest_area >= img_area * min_area_ratio:
            min_rect = cv2.minAreaRect(largest)
            box = cv2.boxPoints(min_rect)
            candidate_rect = order_points(box)

    if candidate_rect is None:
        return None, 0.0

    angle = calculate_bounding_angle(candidate_rect)
    return candidate_rect, angle


def four_point_perspective_warp(
    image: np.ndarray, pts: np.ndarray
) -> tuple[np.ndarray, bool]:
    """
    Warp quadrilateral defined by pts to a flat rectangle.

    Rule 1.3 & §1 Graceful Degradation:
      If perspective warp fails post-detection, fall back to whole image
      and set warp_fallback_used = True (append WARP_FAILED_FULL_FRAME_USED).

    Returns:
        (warped_image, warp_fallback_used)
    """
    rect = order_points(pts)
    tl, tr, br, bl = rect

    # Compute width of new image
    width_top = np.hypot(tr[0] - tl[0], tr[1] - tl[1])
    width_bottom = np.hypot(br[0] - bl[0], br[1] - bl[1])
    max_width = int(max(width_top, width_bottom))

    # Compute height of new image
    height_left = np.hypot(bl[0] - tl[0], bl[1] - tl[1])
    height_right = np.hypot(br[0] - tr[0], br[1] - tr[1])
    max_height = int(max(height_left, height_right))

    # Guard against degenerated dimensions
    if max_width < 10 or max_height < 10:
        logger.warning(
            "Degenerate warp dimensions (%d x %d). Using full frame fallback.",
            max_width,
            max_height,
        )
        return image.copy(), True

    dst = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )

    try:
        matrix = cv2.getPerspectiveTransform(rect, dst)
        if matrix is None:
            raise ValueError("Perspective transform matrix is None")
        warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
        if warped is None or warped.size == 0:
            raise ValueError("Warp perspective resulted in empty image")
        return warped, False
    except Exception as exc:
        logger.warning(
            "Perspective warp failed post-detection: %s. Applying Graceful Degradation fallback.",
            exc,
        )
        return image.copy(), True


# ─── Rule 1.4 — Specular Glare Masking ────────────────────────────────────────


def get_default_key_zones(
    width: int, height: int
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """
    Define standard OCR key-zone bounding boxes for passports/IDs (Name, DOB, MRZ).
    Format: [(zone_name, (x_min, y_min, x_max, y_max))]
    """
    return [
        (
            "NAME_ZONE",
            (
                int(0.20 * width),
                int(0.20 * height),
                int(0.95 * width),
                int(0.48 * height),
            ),
        ),
        (
            "DOB_ZONE",
            (
                int(0.20 * width),
                int(0.48 * height),
                int(0.95 * width),
                int(0.70 * height),
            ),
        ),
        (
            "MRZ_ZONE",
            (
                int(0.05 * width),
                int(0.70 * height),
                int(0.95 * width),
                int(height),
            ),
        ),
    ]


def check_specular_glare(
    image: np.ndarray,
    key_zones: Optional[Sequence[tuple[str, tuple[int, int, int, int]]]] = None,
    threshold_v: Optional[int] = None,
    min_glare_pixels: int = 25,
    min_glare_ratio: float = 0.015,
) -> tuple[bool, list[dict]]:
    """
    Check for specular glare in HSV space (V > 240) over OCR key zones.

    Rule 1.4:
      HSV space, isolate V > 240. Check overlap against OCR key-zone bounding boxes.
      Glare_Mask_Overlap(OCR_Key_Zones) == True -> REJECT. HTTP 400.

    Returns:
        (glare_detected, list_of_zone_details)
    """
    limit_v = (
        threshold_v if threshold_v is not None else settings.GLARE_HSV_V_THRESHOLD
    )
    height, width = image.shape[:2]

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    v_channel = hsv[:, :, 2]
    glare_mask = v_channel > limit_v

    zones = (
        key_zones
        if key_zones is not None
        else get_default_key_zones(width, height)
    )
    zone_results = []
    glare_detected = False

    for zone_name, (x1, y1, x2, y2) in zones:
        # Clamp to image boundaries
        x1_c = max(0, min(width - 1, x1))
        x2_c = max(0, min(width, x2))
        y1_c = max(0, min(height - 1, y1))
        y2_c = max(0, min(height, y2))

        if x2_c <= x1_c or y2_c <= y1_c:
            continue

        zone_mask = glare_mask[y1_c:y2_c, x1_c:x2_c]
        glare_pixels = int(np.count_nonzero(zone_mask))
        total_pixels = int(zone_mask.size)
        ratio = glare_pixels / total_pixels if total_pixels > 0 else 0.0

        zone_has_glare = (
            glare_pixels >= min_glare_pixels and ratio >= min_glare_ratio
        )
        if zone_has_glare:
            glare_detected = True

        zone_results.append(
            {
                "zone": zone_name,
                "bbox": [x1_c, y1_c, x2_c, y2_c],
                "glare_pixels": glare_pixels,
                "total_pixels": total_pixels,
                "glare_ratio": ratio,
                "glare_detected": zone_has_glare,
            }
        )

    return glare_detected, zone_results


# ─── Orchestrated Preprocessing Pipeline ─────────────────────────────────────


def preprocess_document(
    image_input: str | bytes | np.ndarray,
    enforce_quality: bool = True,
    allow_full_frame_fallback_for_contour: bool = False,
) -> PreprocessorResult:
    """
    Execute full Stage 1 image quality verification and perspective correction.

    Pipeline:
      1. Decode image -> validate payload.
      2. Rule 1.2: Laplacian blur check (sigma^2 < 100.0).
      3. Rule 1.3: 4-point contour detection & bounding angle check (angle <= 45.0°).
                   Perspective transform to flat rectangle.
                   Graceful degradation on warp computation failure -> WARP_FAILED_FULL_FRAME_USED.
      4. Rule 1.4: Specular glare masking (HSV V > 240) over OCR key zones.

    If enforce_quality is True:
      Raises ImageQualityError (HTTP 400) on any quality gate failure.
    If enforce_quality is False:
      Populates pass/fail flags on PreprocessorResult without raising.
    """
    image = decode_image(image_input)
    quality_flags: list[str] = []

    # ── Rule 1.2: Motion Blur Check ──────────────────────────────────────────
    variance, blur_passed = check_motion_blur(image)
    if not blur_passed and enforce_quality:
        raise ImageQualityError(
            error_code=ErrorCode.TOO_BLURRY,
            message="Image too blurry. Hold device steady.",
            detail=(
                f"Laplacian variance {variance:.2f} is below threshold "
                f"{settings.LAPLACIAN_VARIANCE_THRESHOLD}."
            ),
        )

    # ── Rule 1.3: Contour Detection & Perspective Warp ───────────────────────
    pts, angle = detect_document_contour(image)
    contour_passed = pts is not None
    angle_passed = angle <= settings.PERSPECTIVE_MAX_ANGLE_DEG

    if not contour_passed:
        if allow_full_frame_fallback_for_contour:
            # When pre-cropped images are explicitly allowed
            h, w = image.shape[:2]
            pts = np.array(
                [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]],
                dtype=np.float32,
            )
            angle = 0.0
            angle_passed = True
            contour_passed = True
        elif enforce_quality:
            raise ImageQualityError(
                error_code=ErrorCode.DOCUMENT_CONTOUR_NOT_FOUND,
                message="Position full document within frame.",
                detail="Could not detect 4-point document boundary in frame.",
            )

    if not angle_passed and enforce_quality:
        raise ImageQualityError(
            error_code=ErrorCode.DOCUMENT_ANGLE_EXCEEDED,
            message="Position full document within frame.",
            detail=(
                f"Document bounding angle {angle:.1f}° exceeds maximum allowed "
                f"{settings.PERSPECTIVE_MAX_ANGLE_DEG}°."
            ),
        )

    # Warp perspective (pts is guaranteed non-None here if passed or full-frame fallback)
    warp_fallback_used = False
    if pts is not None:
        warped, warp_fallback_used = four_point_perspective_warp(image, pts)
        if warp_fallback_used:
            quality_flags.append(FailureCode.WARP_FAILED_FULL_FRAME_USED.value)
    else:
        warped = image.copy()

    # ── Rule 1.4: Specular Glare Masking ─────────────────────────────────────
    glare_detected, _ = check_specular_glare(warped)
    glare_passed = not glare_detected
    if glare_detected and enforce_quality:
        raise ImageQualityError(
            error_code=ErrorCode.GLARE_DETECTED,
            message=(
                "Glare detected over key text fields. Adjust lighting or turn off flash."
            ),
            detail="Specular highlight (HSV V > 240) detected over critical OCR zones.",
        )

    warped_b64 = encode_image_b64(warped)
    h_crop, w_crop = warped.shape[:2]

    return PreprocessorResult(
        warped_image=warped,
        warped_image_b64=warped_b64,
        laplacian_variance=variance,
        bounding_angle=angle,
        glare_detected=glare_detected,
        warp_fallback_used=warp_fallback_used,
        quality_flags=quality_flags,
        blur_passed=blur_passed,
        contour_passed=contour_passed,
        angle_passed=angle_passed,
        glare_passed=glare_passed,
        crop_width=w_crop,
        crop_height=h_crop,
    )
