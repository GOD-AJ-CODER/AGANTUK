"""
tests/test_phase3.py — Verification test suite for Phase 3: OCR Engine & ICAO 9303 Verification Logic.

Tests:
  1. Valid Passport verification: valid document image + TD3 MRZ -> PASS verdict, audit_log written.
  2. Bad check digit: corrupt DocNum / DOB check digit -> FLAGGED with ERR_MATH_MOD10_*.
  3. Cross-zonal VIZ-MRZ mismatch: VIZ name / doc number differs from MRZ -> FLAGGED with ERR_MATH_VIZ_MRZ_MISMATCH.
  4. Audit log SQLite insertion: queries audit_logs table in local.db to verify non-repudiation record.
  5. Multi-format MRZ parsing: TD1 (3x30) and TD2 (2x36) Modulo-10 validation.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import datetime
from datetime import timezone, timedelta
import json
import uuid
import cv2
import jwt
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.db import get_db_connection
from app.core.mrz import calculate_mod10_digit, parse_mrz
from app.core.preprocessor import encode_image_b64
from app.schemas.verification import FailureCode, VerdictStatus


def _generate_valid_token(officer_id: str = "test-officer-p3", terminal_id: str = "TERM-P3") -> str:
    now = datetime.datetime.now(tz=timezone.utc)
    payload = {
        "sub": officer_id,
        "terminal": terminal_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.SESSION_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_synthetic_passport_image() -> np.ndarray:
    """Create a realistic passport image that passes Stage 1 quality checks."""
    width, height = 852, 600
    img = np.full((height, width, 3), 40, dtype=np.uint8)

    # Document card: ID-3 aspect ratio (125/88 ~ 1.42)
    # 710 / 500 = 1.42
    x1, y1 = 71, 50
    x2, y2 = width - 71, height - 50
    cv2.rectangle(img, (x1, y1), (x2, y2), (230, 230, 230), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 3)

    # VIZ Zone
    cv2.putText(img, "PASSPORT / PASSEPORT", (x1 + 30, y1 + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 2)
    cv2.putText(img, "SURNAME: DOE", (x1 + 30, y1 + 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "GIVEN NAMES: JANE", (x1 + 30, y1 + 160),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "NATIONALITY: UTO", (x1 + 30, y1 + 200),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "DATE OF BIRTH: 12 JUL 1985", (x1 + 30, y1 + 240),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "DOC NUMBER: L898902C3", (x1 + 30, y1 + 280),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)
    cv2.putText(img, "EXPIRY DATE: 01 JAN 2030", (x1 + 30, y1 + 320),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2)

    # MRZ Zone (bottom)
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    # DocNum=L898902C3 (cd=6), DOB=850712 (cd=5), Exp=300101 (cd=9), Opt=<<<<<<<<<<<<<< (cd=0)
    # Composite over L898902C36 + 8507125 + 3001019<<<<<<<<<<<<<<0 -> cd=4
    line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04"
    cv2.putText(img, line1, (x1 + 15, y2 - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 2)
    cv2.putText(img, line2, (x1 + 15, y2 - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 10), 2)

    return img


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_valid_passport_verification_pass():
    """Test 1: Valid passport image and matching VIZ/MRZ returns PASS and writes audit log."""
    client = TestClient(app)
    officer_id = f"off-{uuid.uuid4().hex[:8]}"
    token = _generate_valid_token(officer_id=officer_id)

    doc_img = _create_synthetic_passport_image()
    b64_str = encode_image_b64(doc_img)

    # Clear any prior audit log for this document to avoid passback check in repeated runs
    with get_db_connection() as conn:
        conn.execute("DELETE FROM audit_logs WHERE doc_number = ?", ("L898902C3",))
        conn.commit()

    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04"
    viz = {
        "full_name": "JANE DOE",
        "date_of_birth": "1985-07-12",
        "doc_number": "L898902C3",
        "expiry_date": "2030-01-01",
    }

    payload = {
        "image_b64": b64_str,
        "declared_doc_type": "PASSPORT",
        "terminal_id": "GATE-04",
        "mrz_lines": [line1, line2],
        "viz_fields": viz,
    }

    response = client.post(
        "/api/v1/verify/process",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["verdict"] == VerdictStatus.PASS.value
    assert data["failure_codes"] == []
    assert data["officer_id"] == officer_id
    assert data["extracted_fields"]["doc_number"] == "L898902C3"
    assert data["extracted_fields"]["full_name"] == "JANE DOE"

    # Verify audit log in SQLite DB
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM audit_logs WHERE log_id = ?", (data["log_id"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["verdict_status"] == "PASS"
    assert row["officer_id"] == officer_id
    assert row["doc_number"] == "L898902C3"


def test_bad_check_digit_flagged():
    """Test 2: Corrupted check digit triggers FLAGGED and ERR_MATH_MOD10_*."""
    client = TestClient(app)
    officer_id = f"off-{uuid.uuid4().hex[:8]}"
    token = _generate_valid_token(officer_id=officer_id)

    doc_img = _create_synthetic_passport_image()
    b64_str = encode_image_b64(doc_img)

    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    # Corrupt doc number check digit from 6 to 9
    line2_corrupted = "L898902C39UTO8507125F3001019<<<<<<<<<<<<<<04"
    viz = {
        "full_name": "JANE DOE",
        "date_of_birth": "1985-07-12",
        "doc_number": "L898902C3",
        "expiry_date": "2030-01-01",
    }

    payload = {
        "image_b64": b64_str,
        "declared_doc_type": "PASSPORT",
        "terminal_id": "GATE-04",
        "mrz_lines": [line1, line2_corrupted],
        "viz_fields": viz,
    }

    response = client.post(
        "/api/v1/verify/process",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["verdict"] == VerdictStatus.FLAGGED.value
    assert FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED.value in data["failure_codes"]

    # Verify audit log recorded the failure
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM audit_logs WHERE log_id = ?", (data["log_id"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["verdict_status"] == "FLAGGED"
    failure_codes_in_db = json.loads(row["failure_reason_codes"])
    assert FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED.value in failure_codes_in_db


def test_viz_mrz_mismatch_flagged():
    """Test 3: VIZ Name / Doc Number differing from MRZ triggers ERR_MATH_VIZ_MRZ_MISMATCH."""
    client = TestClient(app)
    officer_id = f"off-{uuid.uuid4().hex[:8]}"
    token = _generate_valid_token(officer_id=officer_id)

    doc_img = _create_synthetic_passport_image()
    b64_str = encode_image_b64(doc_img)

    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04"
    # Mismatch: VIZ surname is SMITH instead of DOE
    viz_mismatched = {
        "full_name": "JANE SMITH",
        "date_of_birth": "1985-07-12",
        "doc_number": "L898902C3",
        "expiry_date": "2030-01-01",
    }

    payload = {
        "image_b64": b64_str,
        "declared_doc_type": "PASSPORT",
        "terminal_id": "GATE-04",
        "mrz_lines": [line1, line2],
        "viz_fields": viz_mismatched,
    }

    response = client.post(
        "/api/v1/verify/process",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["verdict"] == VerdictStatus.FLAGGED.value
    assert FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH.value in data["failure_codes"]

    # Verify audit log in DB
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM audit_logs WHERE log_id = ?", (data["log_id"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["verdict_status"] == "FLAGGED"
    assert FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH.value in json.loads(row["failure_reason_codes"])


def test_td1_and_td2_parsing():
    """Test 4: Parsing of TD1 (3x30 ID cards) and TD2 (2x36 Visas)."""
    # TD1 valid example (German ID card style)
    # line1: IDD<<T220001293<<<<<<<<<<<<<<< (doc=T22000129, cd=3)
    # line2: 6408125<2010315D<<0000000<<<<1 (dob=640812 cd=5, exp=201031 cd=5)
    # line3: MUSTERMANN<<ERIKA<<<<<<<<<<<<<
    l1 = "IDD<<T220001293<<<<<<<<<<<<<<<"
    l2 = "6408125<2010315D<<0000000<<<<1"
    l3 = "MUSTERMANN<<ERIKA<<<<<<<<<<<<<"

    res_td1 = parse_mrz([l1, l2, l3])
    assert res_td1.format_type == "TD1"
    assert res_td1.surname == "MUSTERMANN"
    assert res_td1.given_names == "ERIKA"
    assert res_td1.document_number == "T22000129"
    assert res_td1.check_digits["document_number"].is_valid is True
    assert res_td1.check_digits["date_of_birth"].is_valid is True
    assert res_td1.check_digits["expiry_date"].is_valid is True

    # TD2 valid example (2x36)
    # line1: I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<
    # line2: D231458907UTO7408122F1204159<<<<<<<6
    # D23145890 -> cd=7, 740812 -> cd=2, 120415 -> cd=9
    l2_1 = "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<"
    l2_2 = "D231458907UTO7408122F1204159<<<<<<<6"
    res_td2 = parse_mrz([l2_1, l2_2])
    assert res_td2.format_type == "TD2"
    assert res_td2.surname == "ERIKSSON"
    assert res_td2.given_names == "ANNA MARIA"
    assert res_td2.check_digits["document_number"].is_valid is True
    assert res_td2.check_digits["date_of_birth"].is_valid is True
    assert res_td2.check_digits["expiry_date"].is_valid is True


def test_auth_gate_on_verify_process():
    """Test 5: POST /api/v1/verify/process without auth token is blocked with 401."""
    client = TestClient(app)
    response = client.post("/api/v1/verify/process", json={"image_b64": "dummy"})
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_NO_FINGERPRINT"


if __name__ == "__main__":
    print("Running Phase 3 tests...")
    test_auth_gate_on_verify_process()
    print("✓ test_auth_gate_on_verify_process passed")
    test_valid_passport_verification_pass()
    print("✓ test_valid_passport_verification_pass passed")
    test_bad_check_digit_flagged()
    print("✓ test_bad_check_digit_flagged passed")
    test_viz_mrz_mismatch_flagged()
    print("✓ test_viz_mrz_mismatch_flagged passed")
    test_td1_and_td2_parsing()
    print("✓ test_td1_and_td2_parsing passed")
    print("\nALL 5 PHASE 3 TESTS PASSED SUCCESSFULLY! 🎉")
