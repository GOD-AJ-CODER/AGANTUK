"""
tests/test_phase2.py — Verification test suite for Phase 2: Ingestion & Pre-Processing Pipeline.

Tests:
  1. Auth gate: Unauthenticated request to /verify/ingest is rejected (401 AUTH_NO_FINGERPRINT).
  2. Motion blur: Deliberately blurry image (sigma^2 < 100.0) -> 400 "Image too blurry. Hold device steady."
  3. Bounding angle: Deliberately angled image (> 45.0°) -> 400 "Position full document within frame."
  4. Specular glare: Glare spot (V > 240) in key zone -> 400 "Glare detected over key text fields. Adjust lighting or turn off flash."
  5. Valid document: Clean upright document -> 200 OK, returns warped document crop + quality metrics.
  6. Multipart upload: File upload via multipart/form-data -> 200 OK.
  7. Graceful degradation: Warp failure post-detection falls back to full frame with WARP_FAILED_FULL_FRAME_USED.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import base64
import datetime
from datetime import timezone, timedelta
import uuid
import cv2
import jwt
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.preprocessor import (
    preprocess_document,
    four_point_perspective_warp,
    check_motion_blur,
    check_specular_glare,
    detect_document_contour,
    encode_image_b64,
)
from app.schemas.errors import ErrorCode
from app.schemas.verification import FailureCode


def _generate_valid_token(officer_id: str = "test-officer-01", terminal_id: str = "TERM-01") -> str:
    """Helper to generate a valid JWT for the authenticated officer dependency."""
    now = datetime.datetime.now(tz=timezone.utc)
    payload = {
        "sub": officer_id,
        "terminal": terminal_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.SESSION_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_synthetic_document(width: int = 600, height: int = 800) -> np.ndarray:
    """Create a realistic synthetic ID document on a contrasting background."""
    # Dark desk background
    img = np.full((height, width, 3), 40, dtype=np.uint8)

    # Document card (light gray with border) inside frame: x: 80..520, y: 80..720
    card_x1, card_y1 = 80, 80
    card_x2, card_y2 = width - 80, height - 80
    cv2.rectangle(img, (card_x1, card_y1), (card_x2, card_y2), (220, 220, 220), -1)
    cv2.rectangle(img, (card_x1, card_y1), (card_x2, card_y2), (10, 10, 10), 3)

    # Draw high-contrast text lines for realistic Laplacian variance
    # Name zone text
    for y in range(card_y1 + 100, card_y1 + 220, 30):
        cv2.putText(img, "SURNAME: DOE GIVEN NAMES: JANE", (card_x1 + 30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 2)

    # DOB zone text
    for y in range(card_y1 + 260, card_y1 + 380, 30):
        cv2.putText(img, "DATE OF BIRTH: 850712 NATIONALITY: UTO", (card_x1 + 30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 2)

    # MRZ zone text (bottom)
    cv2.putText(img, "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", (card_x1 + 20, card_y2 - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "L898902C36UTO8507128F3001015<<<<<<<<<<<<<<04", (card_x1 + 20, card_y2 - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)

    return img


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_auth_gate_blocks_unauthenticated():
    """Exit check & Rule 1.1: Unauthenticated request must return 401."""
    client = TestClient(app)
    response = client.post("/api/v1/verify/ingest", json={"image_b64": "dummy"})
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == ErrorCode.AUTH_NO_FINGERPRINT


def test_blurry_image_rejected():
    """Rule 1.2: Image with Laplacian variance < 100.0 returns 400 'Image too blurry. Hold device steady.'"""
    client = TestClient(app)
    token = _generate_valid_token()

    doc = _create_synthetic_document()
    # Apply heavy Gaussian blur to suppress Laplacian variance
    blurred = cv2.GaussianBlur(doc, (55, 55), 0)
    variance, passed = check_motion_blur(blurred)
    assert not passed, f"Expected variance < 100, got {variance}"

    b64_str = encode_image_b64(blurred)
    response = client.post(
        "/api/v1/verify/ingest",
        json={"image_b64": b64_str},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == ErrorCode.TOO_BLURRY
    assert body["message"] == "Image too blurry. Hold device steady."


def test_angled_image_rejected():
    """Rule 1.3: Document tilted at angle > 45° returns 400 'Position full document within frame.'"""
    client = TestClient(app)
    token = _generate_valid_token()

    doc = _create_synthetic_document(width=600, height=800)
    # Rotate document by 55 degrees
    center = (300, 400)
    rot_mat = cv2.getRotationMatrix2D(center, 55.0, 0.7)
    rotated = cv2.warpAffine(doc, rot_mat, (600, 800), borderValue=(40, 40, 40))

    b64_str = encode_image_b64(rotated)
    response = client.post(
        "/api/v1/verify/ingest",
        json={"image_b64": b64_str},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == ErrorCode.DOCUMENT_ANGLE_EXCEEDED
    assert body["message"] == "Position full document within frame."


def test_specular_glare_rejected():
    """Rule 1.4: Specular highlight (V > 240) over MRZ zone returns 400 'Glare detected over key text fields...'"""
    client = TestClient(app)
    token = _generate_valid_token()

    doc = _create_synthetic_document()
    # Add intense specular glare spot (V=255) over MRZ zone (near bottom)
    cv2.circle(doc, (300, 680), 50, (255, 255, 255), -1)

    b64_str = encode_image_b64(doc)
    response = client.post(
        "/api/v1/verify/ingest",
        json={"image_b64": b64_str},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == ErrorCode.GLARE_DETECTED
    assert body["message"] == "Glare detected over key text fields. Adjust lighting or turn off flash."


def test_valid_document_success():
    """Valid sharp upright document returns 200 OK with warped crop and quality metrics."""
    client = TestClient(app)
    token = _generate_valid_token()

    doc = _create_synthetic_document()
    b64_str = encode_image_b64(doc)

    response = client.post(
        "/api/v1/verify/ingest",
        json={"image_b64": b64_str},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "warped_image_b64" in body
    assert body["laplacian_variance"] >= 100.0
    assert body["bounding_angle"] <= 45.0
    assert body["glare_detected"] is False
    assert body["warp_fallback_used"] is False
    assert body["crop_width"] > 0
    assert body["crop_height"] > 0


def test_multipart_file_upload():
    """Valid document uploaded as multipart/form-data file returns 200 OK."""
    client = TestClient(app)
    token = _generate_valid_token()

    doc = _create_synthetic_document()
    _, buffer = cv2.imencode(".jpg", doc)
    img_bytes = buffer.tobytes()

    response = client.post(
        "/api/v1/verify/ingest",
        files={"file": ("passport.jpg", img_bytes, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["warped_image_b64"]) > 100


def test_graceful_degradation_warp_fallback():
    """Rule 1.3: If warp fails post-detection, full frame fallback is used with WARP_FAILED_FULL_FRAME_USED."""
    doc = _create_synthetic_document()
    # Collinear / degenerate points that fail perspective transform
    bad_pts = np.array([[10, 10], [10, 10], [10, 10], [10, 10]], dtype=np.float32)

    warped, fallback_used = four_point_perspective_warp(doc, bad_pts)
    assert fallback_used is True
    assert warped.shape == doc.shape


if __name__ == "__main__":
    print("Running Phase 2 tests...")
    test_auth_gate_blocks_unauthenticated()
    print("✓ test_auth_gate_blocks_unauthenticated passed")
    test_blurry_image_rejected()
    print("✓ test_blurry_image_rejected passed")
    test_angled_image_rejected()
    print("✓ test_angled_image_rejected passed")
    test_specular_glare_rejected()
    print("✓ test_specular_glare_rejected passed")
    test_valid_document_success()
    print("✓ test_valid_document_success passed")
    test_multipart_file_upload()
    print("✓ test_multipart_file_upload passed")
    test_graceful_degradation_warp_fallback()
    print("✓ test_graceful_degradation_warp_fallback passed")
    print("\nALL 7 PHASE 2 TESTS PASSED SUCCESSFULLY! 🎉")
