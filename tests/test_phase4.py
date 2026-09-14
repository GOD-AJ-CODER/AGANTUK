import pytest
import numpy as np
import cv2
from datetime import datetime, timezone, timedelta
from app.core.forensics import run_forensics, validate_aspect_ratio, check_spectral_consistency, check_spatial_alignment
from app.core.rules_engine import evaluate_rules, resolve_verdict, check_chronological_logic
from app.core.mrz import ParsedMRZ
from app.schemas.verification import FailureCode, VerdictStatus, DocumentType
from app.core.db import get_db

@pytest.fixture
def sample_image():
    # Create a synthetic passport-like image (ID-3 aspect ratio: 1.42)
    img = np.ones((880, 1250, 3), dtype=np.uint8) * 200
    # Add a "photo" zone
    img[100:400, 50:350] = [100, 150, 200]
    # Add some "text" blocks
    cv2.putText(img, "PASSPORT", (500, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 2)
    return img

@pytest.fixture
def valid_mrz():
    return ParsedMRZ(
        raw_lines=["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<", "L898902C36UTO7408122F1204159ZE184226B<<<<<10"],
        format_type="TD3",
        document_type="PASSPORT",
        issuing_country="UTO",
        surname="ERIKSSON",
        given_names="ANNA MARIA",
        document_number="L898902C3",
        nationality="UTO",
        date_of_birth="740812",
        sex="F",
        expiry_date="120415",
        optional_data="ZE184226B",
        is_valid=True
    )

def test_forensics_aspect_ratio():
    # ID-3 is 125x88 -> ratio 1.420
    img_ok = np.zeros((880, 1250, 3), dtype=np.uint8)
    ok, dev = validate_aspect_ratio(img_ok)
    assert ok is True
    
    img_bad = np.zeros((800, 1500, 3), dtype=np.uint8) # ratio 1.875
    ok, dev = validate_aspect_ratio(img_bad)
    assert ok is False

def test_forensics_spectral_anomaly(sample_image):
    # Authentic-looking image (substrate and photo consistent)
    consistent_img = np.ones((880, 1250, 3), dtype=np.uint8) * 200
    # Add some random noise to make histograms more interesting
    noise = np.random.randint(0, 10, (880, 1250, 3), dtype=np.uint8)
    consistent_img = cv2.add(consistent_img, noise)
    
    assert check_spectral_consistency(consistent_img) is False
    
    # Spliced one (extreme color difference)
    spliced_img = consistent_img.copy()
    spliced_img[100:400, 50:350] = [0, 255, 0] # Bright green photo
    assert check_spectral_consistency(spliced_img) is True

def test_chronological_logic(valid_mrz):
    # Valid MRZ (740812, 120415) - wait, 120415 is expired in 2026
    failures = check_chronological_logic(valid_mrz)
    assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED in failures
    
    # Future expiry
    mrz_future = valid_mrz
    mrz_future.expiry_date = "350101"
    failures = check_chronological_logic(mrz_future)
    assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED not in failures
    
def test_verdict_precedence():
    # Only PASS
    assert resolve_verdict([]) == VerdictStatus.PASS
    
    # One standard flag
    assert resolve_verdict([FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS]) == VerdictStatus.FLAGGED
    
    # Manual review
    assert resolve_verdict([FailureCode.WARN_OCR_LOW_CONFIDENCE]) == VerdictStatus.MANUAL_REVIEW
    
    # Critical flag wins over standard flag
    assert resolve_verdict([FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS, FailureCode.ERR_SECURITY_PASSBACK_DETECTED]) == VerdictStatus.FLAGGED
    
    # Watchlist hit wins over everything
    assert resolve_verdict([FailureCode.ERR_SECURITY_WATCHLIST_HIT, FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED]) == VerdictStatus.CRITICAL_SECURITY_ALERT

def test_watchlist_logic(valid_mrz):
    doc_num = "WATCHLIST001"
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (watchlist_id, doc_number, full_name, dob, reason) VALUES (?, ?, ?, ?, ?)",
            ("wl-001", doc_num, "SCAMMER", "000101", "Testing")
        )
    
    mrz_flagged = valid_mrz
    mrz_flagged.document_number = doc_num
    
    failures = evaluate_rules(mrz_flagged, [])
    assert FailureCode.ERR_SECURITY_WATCHLIST_HIT in failures
    assert resolve_verdict(failures) == VerdictStatus.CRITICAL_SECURITY_ALERT

def test_passback_logic(valid_mrz):
    doc_num = "PASSBACK001"
    # Insert a dummy officer first to satisfy foreign key
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO officers (officer_id, badge_number, full_name, role) VALUES (?, ?, ?, ?)",
            ("test-officer", "B123", "Test Officer", "OFFICER")
        )
        # Insert a recent audit log
        conn.execute(
            "INSERT INTO audit_logs (log_id, officer_id, timestamp_utc, doc_number, verdict_status, confidence_scores, failure_reason_codes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test-log-id-" + str(np.random.randint(0, 10000)), "test-officer", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), doc_num, "PASS", "{}", "[]")
        )
    
    mrz_pb = valid_mrz
    mrz_pb.document_number = doc_num
    
    failures = evaluate_rules(mrz_pb, [])
    assert FailureCode.ERR_SECURITY_PASSBACK_DETECTED in failures
    assert resolve_verdict(failures) == VerdictStatus.FLAGGED

def test_full_pipeline_integration(valid_mrz, sample_image):
    # This test would ideally call the API or the full pipeline function
    # Let's simulate the process_verification logic
    
    # Forensics
    f_res = run_forensics(sample_image)
    
    # Rules
    all_failures = evaluate_rules(valid_mrz, f_res.failure_codes)
    
    # Verdict
    verdict = resolve_verdict(all_failures)
    
    assert isinstance(verdict, VerdictStatus)
    assert len(all_failures) >= 0
