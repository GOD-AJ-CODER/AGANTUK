"""
core/forensics.py — Digital and physical forensics for document integrity.

Rules Reference:
  - Rule 2.1: JPEG Quantization / Double-Compression check.
  - Rule 2.2: Error Level Analysis (ELA) for photo-zone splicing.
  - Rule 2.3: PRNU Noise Inconsistency for digital patching.
  - Rule 2.4: Physical Aspect Ratio validation.
"""

import logging
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from app.schemas.verification import FailureCode

logger = logging.getLogger(__name__)

@dataclass
class ForensicsResult:
    failure_codes: list[FailureCode] = field(default_factory=list)
    ela_variance_ratio: Optional[float] = None
    aspect_ratio_deviation: Optional[float] = None
    double_compression_detected: bool = False
    digital_patching_detected: bool = False
    spatial_anomaly_detected: bool = False
    spectral_inconsistency_detected: bool = False

def check_jpeg_double_compression(image_bytes: bytes) -> bool:
    """
    Rule 2.1: JPEG Quantization / Double-Compression check.
    Simplified version: Check for 'JPEG Ghosts' or quantization artifacts.
    """
    # Real quantization analysis requires low-level JPEG parsing.
    # Here we look for common markers of re-compression if bytes are provided.
    if not image_bytes:
        return False
    # Simplified: if we see multiple DHT/DQT segments, it might be double compressed
    # (Very crude heuristic for this stage)
    return image_bytes.count(b'\xff\xdb') > 1

def run_ela(image: np.ndarray, quality: int = 95) -> float:
    """
    Rule 2.2: Error Level Analysis (ELA).
    Compares variance in different regions to detect splicing.
    """
    pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    buffer = BytesIO()
    pil_img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    resaved_img = np.array(Image.open(buffer))
    resaved_img = cv2.cvtColor(resaved_img, cv2.COLOR_RGB2BGR)
    
    diff = cv2.absdiff(image, resaved_img)
    
    # Analyze variance in tiles to find anomalies
    h, w = diff.shape[:2]
    tile_size = 32
    variances = []
    for y in range(0, h - tile_size, tile_size):
        for x in range(0, w - tile_size, tile_size):
            tile = diff[y:y+tile_size, x:x+tile_size]
            variances.append(np.var(tile))
            
    if not variances:
        return 0.0
        
    avg_var = np.mean(variances)
    max_var = np.max(variances)
    
    # Return ratio of peak variance to average
    return float(max_var / avg_var) if avg_var > 0 else 0.0

def check_prnu_inconsistency(image: np.ndarray) -> bool:
    """
    Rule 2.3: PRNU Noise Inconsistency.
    Isolates sensor pattern noise to find digital patches.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Use a faster denoising for real-time
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    noise_pattern = gray - denoised
    
    h, w = noise_pattern.shape
    tile_size = 64
    variances = []
    for y in range(0, h - tile_size, tile_size):
        for x in range(0, w - tile_size, tile_size):
            tile = noise_pattern[y:y+tile_size, x:x+tile_size]
            variances.append(np.var(tile))
    
    if not variances:
        return False
        
    avg_var = np.mean(variances)
    max_var = np.max(variances)
    
    # High local variance in noise pattern suggests digital manipulation
    return bool(max_var > avg_var * 10.0)

def check_spatial_alignment(image: np.ndarray) -> bool:
    """
    Spatial alignment/crop anomaly checks.
    Detects if the document has irregular edges or suspicious white borders 
    after warping, which might indicate a physical cutout.
    """
    h, w = image.shape[:2]
    # Check edges for high intensity (white) or low intensity (black) strips
    edge_thickness = 5
    top = image[0:edge_thickness, :]
    bottom = image[h-edge_thickness:h, :]
    left = image[:, 0:edge_thickness]
    right = image[:, w-edge_thickness:w]
    
    # If edges are too uniform or too contrasty vs the center, it's an anomaly
    edge_means = [np.mean(top), np.mean(bottom), np.mean(left), np.mean(right)]
    center = image[h//4:3*h//4, w//4:3*w//4]
    center_mean = np.mean(center)
    
    for m in edge_means:
        if abs(m - center_mean) > 100: # Extreme contrast at edge
            return True
    return False

def check_spectral_consistency(image: np.ndarray) -> bool:
    """
    Spectral/color consistency checks.
    Compares color distribution (histograms) between key zones.
    """
    h, w = image.shape[:2]
    # Photo zone is typically top-left for passports
    photo_zone = image[int(0.1*h):int(0.5*h), int(0.05*w):int(0.4*w)]
    substrate_zone = image[int(0.1*h):int(0.5*h), int(0.6*w):int(0.9*w)]
    
    if photo_zone.size == 0 or substrate_zone.size == 0:
        return False
        
    # Compare histograms in HSV space
    hsv_photo = cv2.cvtColor(photo_zone, cv2.COLOR_BGR2HSV)
    hsv_subst = cv2.cvtColor(substrate_zone, cv2.COLOR_BGR2HSV)
    
    hist_photo = cv2.calcHist([hsv_photo], [0, 1], None, [180, 256], [0, 180, 0, 256])
    hist_subst = cv2.calcHist([hsv_subst], [0, 1], None, [180, 256], [0, 180, 0, 256])
    
    cv2.normalize(hist_photo, hist_photo, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist_subst, hist_subst, 0, 1, cv2.NORM_MINMAX)
    
    # Correlation should be reasonably high for authentic integrated documents
    score = cv2.compareHist(hist_photo, hist_subst, cv2.HISTCMP_CORREL)
    return bool(score < 0.1) # Very low correlation suggests splicing

def validate_aspect_ratio(image: np.ndarray) -> Tuple[bool, float]:
    """
    Rule 2.4: Physical Aspect Ratio.
    """
    h, w = image.shape[:2]
    current_ratio = w / h if h > 0 else 0
    
    id1_ratio = 85.60 / 53.98
    id3_ratio = 125.0 / 88.0
    
    dev_id1 = abs(current_ratio - id1_ratio) / id1_ratio
    dev_id3 = abs(current_ratio - id3_ratio) / id3_ratio
    
    min_dev = min(dev_id1, dev_id3)
    return min_dev <= 0.03, min_dev

def run_forensics(image: np.ndarray, raw_image_bytes: Optional[bytes] = None) -> ForensicsResult:
    """
    Execute all forensics rules.
    """
    result = ForensicsResult()
    
    # Rule 2.1
    if raw_image_bytes and check_jpeg_double_compression(raw_image_bytes):
        result.failure_codes.append(FailureCode.ERR_FORENSIC_DOUBLE_COMPRESSION)
        result.double_compression_detected = True
        
    # Rule 2.2
    ela_ratio = run_ela(image)
    result.ela_variance_ratio = ela_ratio
    if ela_ratio > 15.0: # Threshold for peak variance ratio
        result.failure_codes.append(FailureCode.ERR_FORENSIC_PHOTO_SPLICED)
        
    # Rule 2.3
    if check_prnu_inconsistency(image):
        result.failure_codes.append(FailureCode.ERR_FORENSIC_DIGITAL_PATCHING)
        result.digital_patching_detected = True
        
    # Rule 2.4
    is_aspect_ok, deviation = validate_aspect_ratio(image)
    result.aspect_ratio_deviation = deviation
    if not is_aspect_ok:
        result.failure_codes.append(FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS)
        
    # Spatial Alignment
    if check_spatial_alignment(image):
        # We don't have a specific ERR code for this in rules.md, but it falls under 
        # general forensic flag or we can use ERR_FORENSIC_PHOTO_SPLICED as a proxy 
        # or append it if we had a code. For now, let's use ERR_FORENSIC_DIGITAL_PATCHING.
        if FailureCode.ERR_FORENSIC_DIGITAL_PATCHING not in result.failure_codes:
            result.failure_codes.append(FailureCode.ERR_FORENSIC_DIGITAL_PATCHING)
        result.spatial_anomaly_detected = True
        
    # Spectral Consistency
    if check_spectral_consistency(image):
        if FailureCode.ERR_FORENSIC_PHOTO_SPLICED not in result.failure_codes:
            result.failure_codes.append(FailureCode.ERR_FORENSIC_PHOTO_SPLICED)
        result.spectral_inconsistency_detected = True
        
    return result
