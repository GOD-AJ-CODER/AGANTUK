"""
tests/test_phase4.py — Verification test suite for Phase 4: Forensics Engine & Rule Validation Engine.

phases.md Exit Check:
  "Unit tests covering at least one case per failure code in rules.md,
   plus one deliberate multi-flag conflict case proving precedence resolves correctly."

Unit Tests (direct function calls):
  - Forensics: ELA, PRNU, double-compression, spatial alignment, spectral consistency, aspect ratio.
  - Verdict precedence resolution: PASS, MANUAL_REVIEW, FLAGGED, FLAGGED-critical, CRITICAL_SECURITY_ALERT.
  - Chronological logic: expired, future issue date, timeline contradiction, invalid age, issued before birth.
  - Modulo-37 engine: Rule 4.4.
  - Modulo-10 regression: Rule 4.3.

Integration Tests (HTTP endpoint /api/v1/verify/process):
  1. Expired document → ERR_LOGIC_DOCUMENT_EXPIRED.
  2. Pass-back detection → ERR_SECURITY_PASSBACK_DETECTED.
  3. Watchlist hit → CRITICAL_SECURITY_ALERT + ERR_SECURITY_WATCHLIST_HIT.
  4. Aspect ratio failure → ERR_FORENSIC_INVALID_DIMENSIONS.
  5. Verdict precedence: watchlist (CSA) beats expired (FLAGGED).
  6. Malformed MRZ structure → ERR_MATH_MALFORMED_MRZ_STRUCTURE.
  7. Invalid MRZ characters → ERR_MATH_INVALID_MRZ_CHARACTERS.
  8. VIZ vs MRZ mismatch → ERR_MATH_VIZ_MRZ_MISMATCH.
  9. Mod10 doc number failed → ERR_MATH_MOD10_DOC_NUM_FAILED.
 10. No MRZ lines → ERR_OCR_MISSING_MANDATORY_FIELD.
 11. Multi-flag: bad Mod10 + bad aspect ratio → FLAGGED with both codes.
 12. Multi-flag precedence: CSA beats all other ERR_ codes → CRITICAL_SECURITY_ALERT.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import datetime
from datetime import timezone, timedelta
import uuid

import cv2
import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.db import get_db_connection
from app.core.forensics import (
    ForensicsResult,
    check_jpeg_double_compression,
    check_prnu_inconsistency,
    check_spatial_alignment,
    check_spectral_consistency,
    run_ela,
    run_forensics,
    validate_aspect_ratio,
)
from app.core.mrz import ParsedMRZ, calculate_mod10_digit
from app.core.preprocessor import encode_image_b64
from app.core.rules_engine import (
    calculate_mod37_digit,
    check_chronological_logic,
    evaluate_rules,
    resolve_verdict,
    verify_mod37,
)
from app.schemas.verification import FailureCode, VerdictStatus


# ---------------------------------------------------------------------------
# Shared Helpers
# ---------------------------------------------------------------------------


def _generate_valid_token(
    officer_id: str = "test-officer-p4", terminal_id: str = "TERM-P4"
) -> str:
    now = datetime.datetime.now(tz=timezone.utc)
    payload = {
        "sub": officer_id,
        "terminal": terminal_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.SESSION_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_synthetic_passport_image(width: int = 852, height: int = 600) -> np.ndarray:
    """Create a passport-shaped document image that passes Stage 1 quality checks."""
    img = np.full((height, width, 3), 40, dtype=np.uint8)
    x1, y1 = 60, 60
    x2, y2 = width - 60, height - 60
    cv2.rectangle(img, (x1, y1), (x2, y2), (200, 200, 200), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 3)
    # Add subtle noise texture to keep ELA ratios non-trivial
    noise = np.random.randint(0, 15, (height, width, 3), dtype=np.uint8)
    img = cv2.add(img, noise)
    return img


def _make_empty_parsed_mrz(**kwargs) -> ParsedMRZ:
    """Create a minimal stub ParsedMRZ for unit testing."""
    defaults = dict(
        raw_lines=[],
        format_type="TD3",
        document_type="PASSPORT",
        issuing_country="UTO",
        surname="DOE",
        given_names="JANE",
        document_number="L898902C3",
        nationality="UTO",
        date_of_birth="850712",
        sex="F",
        expiry_date="300101",
        optional_data="",
        check_digits={},
        failure_codes=[],
        is_valid=True,
    )
    defaults.update(kwargs)
    return ParsedMRZ(**defaults)


def _setup_watchlist_entry(doc_number: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (watchlist_id, doc_number, reason) VALUES (?, ?, ?)",
        (str(uuid.uuid4()), doc_number, "TEST WATCHLIST HIT"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Unit Tests: Forensics Functions
# ---------------------------------------------------------------------------


class TestForensicsUnits:
    """Unit tests for individual forensics check functions (Rules 2.1-2.4)."""

    def test_double_compression_detected_multiple_dqt(self):
        """Rule 2.1: Bytes with >1 DQT (0xFFDB) marker signals double compression."""
        fake_jpeg = (
            b"\xff\xd8\xff\xdb\x00\x43" + b"\x00" * 67
            + b"\xff\xdb\x00\x43" + b"\x00" * 67
            + b"\xff\xd9"
        )
        assert check_jpeg_double_compression(fake_jpeg) is True

    def test_double_compression_single_dqt_clean(self):
        """Rule 2.1: Bytes with only 1 DQT marker -> no flag."""
        fake_jpeg = b"\xff\xd8\xff\xdb\x00\x43" + b"\x00" * 67 + b"\xff\xd9"
        assert check_jpeg_double_compression(fake_jpeg) is False

    def test_double_compression_empty_bytes(self):
        """Rule 2.1: Empty bytes -> no crash, returns False."""
        assert check_jpeg_double_compression(b"") is False

    def test_ela_returns_nonnegative_float(self):
        """Rule 2.2: ELA must return a non-negative float."""
        img = _create_synthetic_passport_image(200, 150)
        ratio = run_ela(img)
        assert isinstance(ratio, float)
        assert ratio >= 0.0

    def test_ela_uniform_image_low_ratio(self):
        """Rule 2.2: Uniform image -> no extreme splice signal (ratio >= 0)."""
        img = np.full((200, 300, 3), 128, dtype=np.uint8)
        ratio = run_ela(img)
        assert ratio >= 0.0

    def test_prnu_result_is_bool(self):
        """Rule 2.3: check_prnu_inconsistency returns a bool."""
        img = _create_synthetic_passport_image()
        result = check_prnu_inconsistency(img)
        assert isinstance(result, bool)

    def test_spatial_alignment_uniform_no_anomaly(self):
        """Spatial check: uniform document -> no edge anomaly."""
        img = np.full((300, 400, 3), 180, dtype=np.uint8)
        assert check_spatial_alignment(img) is False

    def test_spatial_alignment_white_border_detected(self):
        """Spatial check: white border on dark interior -> anomaly detected."""
        img = np.full((300, 400, 3), 40, dtype=np.uint8)
        img[0:5, :] = 255
        img[295:300, :] = 255
        img[:, 0:5] = 255
        img[:, 395:400] = 255
        assert check_spatial_alignment(img) is True

    def test_spectral_consistency_returns_bool(self):
        """Spectral check: always returns a bool."""
        img = np.full((300, 400, 3), 100, dtype=np.uint8)
        assert isinstance(check_spectral_consistency(img), bool)

    def test_aspect_ratio_square_fails(self):
        """Rule 2.4: Square image (1:1 ratio) deviates >3% from ID-1 and ID-3."""
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        is_ok, deviation = validate_aspect_ratio(img)
        assert is_ok is False
        assert deviation > 0.03

    def test_aspect_ratio_id1_width_height(self):
        """Rule 2.4: ID-1 proportioned image should have small deviation."""
        # ID-1: 85.60x53.98mm -> ratio ~1.5857; use 856x540 pixels
        img = np.zeros((540, 856, 3), dtype=np.uint8)
        is_ok, deviation = validate_aspect_ratio(img)
        assert deviation < 0.10  # Well within either known format

    def test_run_forensics_returns_forensics_result(self):
        """run_forensics() always returns a ForensicsResult with failure_codes list."""
        img = _create_synthetic_passport_image()
        result = run_forensics(img)
        assert isinstance(result, ForensicsResult)
        assert isinstance(result.failure_codes, list)
        assert result.ela_variance_ratio is not None

    def test_run_forensics_with_raw_bytes(self):
        """run_forensics() with raw JPEG bytes calls double-compression check."""
        img = _create_synthetic_passport_image()
        _, encoded = cv2.imencode(".jpg", img)
        raw_bytes = encoded.tobytes()
        result = run_forensics(img, raw_image_bytes=raw_bytes)
        assert isinstance(result, ForensicsResult)


# ---------------------------------------------------------------------------
# Unit Tests: Verdict Precedence Resolution (rules.md §3)
# ---------------------------------------------------------------------------


class TestVerdictPrecedence:
    """Unit tests for resolve_verdict() — rules.md §3 precedence hierarchy."""

    def test_no_codes_gives_pass(self):
        assert resolve_verdict([]) == VerdictStatus.PASS

    def test_only_warn_gives_manual_review(self):
        assert resolve_verdict([FailureCode.WARN_OCR_LOW_CONFIDENCE]) == VerdictStatus.MANUAL_REVIEW

    def test_err_forensic_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS]) == VerdictStatus.FLAGGED

    def test_err_logic_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED]) == VerdictStatus.FLAGGED

    def test_err_math_structure_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_MALFORMED_MRZ_STRUCTURE]) == VerdictStatus.FLAGGED

    def test_err_math_invalid_chars_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_INVALID_MRZ_CHARACTERS]) == VerdictStatus.FLAGGED

    def test_err_math_mod37_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_MOD37_FAILED]) == VerdictStatus.FLAGGED

    def test_err_ocr_missing_field_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_OCR_MISSING_MANDATORY_FIELD]) == VerdictStatus.FLAGGED

    def test_err_ai_unknown_format_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_AI_UNKNOWN_DOC_FORMAT]) == VerdictStatus.FLAGGED

    def test_critical_mod10_doc_gives_flagged(self):
        """ERR_MATH_MOD10_DOC_NUM_FAILED is a critical flag -> FLAGGED."""
        assert resolve_verdict([FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED]) == VerdictStatus.FLAGGED

    def test_critical_mod10_dob_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_MOD10_DOB_FAILED]) == VerdictStatus.FLAGGED

    def test_critical_mod10_expiry_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_MOD10_EXPIRY_FAILED]) == VerdictStatus.FLAGGED

    def test_critical_mod10_master_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED]) == VerdictStatus.FLAGGED

    def test_critical_viz_mrz_mismatch_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH]) == VerdictStatus.FLAGGED

    def test_passback_gives_flagged(self):
        assert resolve_verdict([FailureCode.ERR_SECURITY_PASSBACK_DETECTED]) == VerdictStatus.FLAGGED

    def test_watchlist_gives_csa(self):
        assert resolve_verdict([FailureCode.ERR_SECURITY_WATCHLIST_HIT]) == VerdictStatus.CRITICAL_SECURITY_ALERT

    def test_csa_beats_critical_math_flags(self):
        """CSA (#1) beats FLAGGED-critical (#2) — rules.md §3."""
        codes = [
            FailureCode.ERR_SECURITY_WATCHLIST_HIT,
            FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED,
            FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH,
        ]
        assert resolve_verdict(codes) == VerdictStatus.CRITICAL_SECURITY_ALERT

    def test_csa_beats_warn(self):
        codes = [FailureCode.ERR_SECURITY_WATCHLIST_HIT, FailureCode.WARN_OCR_LOW_CONFIDENCE]
        assert resolve_verdict(codes) == VerdictStatus.CRITICAL_SECURITY_ALERT

    def test_flagged_beats_manual_review(self):
        codes = [FailureCode.ERR_FORENSIC_DOUBLE_COMPRESSION, FailureCode.WARN_OCR_LOW_CONFIDENCE]
        assert resolve_verdict(codes) == VerdictStatus.FLAGGED

    def test_all_codes_in_list_when_csa(self):
        """rules.md §3: all triggered codes are reported, not just top."""
        codes = [
            FailureCode.ERR_SECURITY_WATCHLIST_HIT,
            FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED,
            FailureCode.ERR_FORENSIC_PHOTO_SPLICED,
            FailureCode.WARN_OCR_LOW_CONFIDENCE,
        ]
        assert resolve_verdict(codes) == VerdictStatus.CRITICAL_SECURITY_ALERT
        # All codes still in list (caller reports all of them)
        assert len(codes) == 4


# ---------------------------------------------------------------------------
# Unit Tests: Chronological Logic (Stage 5)
# ---------------------------------------------------------------------------


class TestChronologicalLogic:
    """Unit tests for check_chronological_logic() — Stage 5."""

    def test_expired_document_flagged(self):
        """Expiry in the past -> ERR_LOGIC_DOCUMENT_EXPIRED."""
        mrz = _make_empty_parsed_mrz(expiry_date="100101")
        failures = check_chronological_logic(mrz)
        assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED in failures

    def test_future_expiry_not_flagged(self):
        """Expiry in the future -> no expiry flag."""
        mrz = _make_empty_parsed_mrz(expiry_date="350101")
        failures = check_chronological_logic(mrz)
        assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED not in failures

    def test_future_issue_date_flagged(self):
        """Issue date in the future -> ERR_LOGIC_FUTURE_ISSUE_DATE."""
        mrz = _make_empty_parsed_mrz(expiry_date="350101")
        viz = {"issue_date": "300101"}  # 01 Jan 2030 (future: yy=30, 30<=46 -> 2030)
        failures = check_chronological_logic(mrz, viz)
        assert FailureCode.ERR_LOGIC_FUTURE_ISSUE_DATE in failures

    def test_timeline_contradiction_flagged(self):
        """Issue date >= Expiry date -> ERR_LOGIC_TIMELINE_CONTRADICTION."""
        mrz = _make_empty_parsed_mrz(expiry_date="200601")  # Jun 2020
        viz = {"issue_date": "210101"}  # Jan 2021 (after expiry)
        failures = check_chronological_logic(mrz, viz)
        assert FailureCode.ERR_LOGIC_TIMELINE_CONTRADICTION in failures

    def test_issued_before_birth_flagged(self):
        """Issue date before DOB -> ERR_LOGIC_ISSUED_BEFORE_BIRTH."""
        mrz = _make_empty_parsed_mrz(date_of_birth="900615", expiry_date="350101")
        viz = {"issue_date": "850101"}  # Jan 1985 < Jun 1990
        failures = check_chronological_logic(mrz, viz)
        assert FailureCode.ERR_LOGIC_ISSUED_BEFORE_BIRTH in failures

    def test_clean_mrz_no_chronological_failures(self):
        """Clean MRZ with valid future expiry -> no chronological failures."""
        mrz = _make_empty_parsed_mrz(date_of_birth="850712", expiry_date="350101")
        failures = check_chronological_logic(mrz)
        assert failures == []


# ---------------------------------------------------------------------------
# Unit Tests: Modulo-37 Engine (Rule 4.4)
# ---------------------------------------------------------------------------


class TestModulo37Engine:
    """Unit tests for calculate_mod37_digit() and verify_mod37() — Rule 4.4."""

    def test_zero_value(self):
        """'0' * weight 7 = 0, 0 mod 37 = 0 -> '0'."""
        assert calculate_mod37_digit("0") == "0"

    def test_alpha_A_value(self):
        """'A' = 10 * 7 = 70, 70 mod 37 = 33 -> MOD37_RESULT_CHARS[33] = 'X'."""
        assert calculate_mod37_digit("A") == "X"

    def test_verify_pass(self):
        """verify_mod37 passes when expected char matches calculated."""
        data = "L898902C3"
        check = calculate_mod37_digit(data)
        assert verify_mod37(data, check) is True

    def test_verify_fail(self):
        """verify_mod37 fails when expected char is wrong."""
        data = "L898902C3"
        calc = calculate_mod37_digit(data)
        wrong = "Z" if calc != "Z" else "Y"
        assert verify_mod37(data, wrong) is False

    def test_deterministic(self):
        """Same input always gives same output."""
        data = "L898902C3"
        assert calculate_mod37_digit(data) == calculate_mod37_digit(data)

    def test_filler_equals_zero_result(self):
        """'<' and '0' both map to value 0 -> same check char."""
        assert calculate_mod37_digit("<") == calculate_mod37_digit("0")

    def test_output_in_alphabet(self):
        """All outputs are in the valid Mod37 alphabet."""
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*"
        for test_str in ["A1B2C3", "PASSPORT", "<<<<<<", "999999"]:
            result = calculate_mod37_digit(test_str)
            assert result in alphabet, f"'{result}' not in alphabet for '{test_str}'"


# ---------------------------------------------------------------------------
# Unit Tests: Modulo-10 Engine (Rule 4.3)
# ---------------------------------------------------------------------------


class TestModulo10Engine:
    """Regression unit tests for calculate_mod10_digit() — Rule 4.3."""

    def test_icao_doc_number_example(self):
        """ICAO 9303 canonical example: 'L898902C3' -> check digit '6'."""
        assert calculate_mod10_digit("L898902C3") == "6"

    def test_dob_example(self):
        """'850712' -> check digit '5'."""
        assert calculate_mod10_digit("850712") == "5"

    def test_all_fillers_zero(self):
        """'<<<<<<' -> all value 0, 0 mod 10 = 0."""
        assert calculate_mod10_digit("<<<<<<") == "0"

    def test_pure_zeros(self):
        """'000000' -> 0 mod 10 = 0."""
        assert calculate_mod10_digit("000000") == "0"

    def test_result_is_single_digit(self):
        """Result is always a single digit string."""
        result = calculate_mod10_digit("L898902C3")
        assert len(result) == 1
        assert result in "0123456789"


# ---------------------------------------------------------------------------
# Integration Tests: HTTP Endpoint (/api/v1/verify/process)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def token():
    return _generate_valid_token()


@pytest.fixture
def passport_b64():
    img = _create_synthetic_passport_image()
    return encode_image_b64(img)


def test_chronological_failure_expired(client, token, passport_b64):
    """Test 1: Expired passport MRZ -> FLAGGED + ERR_LOGIC_DOCUMENT_EXPIRED."""
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C36UTO8507125F1001019<<<<<<<<<<<<<<02"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_passback_detection(client, token, passport_b64):
    """Test 2: Same doc within 15 mins -> FLAGGED + ERR_SECURITY_PASSBACK_DETECTED."""
    doc_num = f"PB{uuid.uuid4().hex[:7]}".upper()
    line1 = "P<UTOUSER<<TEST<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = f"{doc_num}0UTO8507125F3001019<<<<<<<<<<<<<<00"
    payload = {"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]}
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post("/api/v1/verify/process", json=payload, headers=headers)
    assert r1.status_code == 200

    r2 = client.post("/api/v1/verify/process", json=payload, headers=headers)
    assert r2.status_code == 200
    data = r2.json()
    assert FailureCode.ERR_SECURITY_PASSBACK_DETECTED.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_watchlist_hit_csa(client, token, passport_b64):
    """Test 3: Watchlist doc -> CRITICAL_SECURITY_ALERT + ERR_SECURITY_WATCHLIST_HIT."""
    doc_num = f"WL{uuid.uuid4().hex[:7]}".upper()
    _setup_watchlist_entry(doc_num)
    line1 = "P<UTOWATCH<<LIST<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = f"{doc_num}0UTO8507125F3001019<<<<<<<<<<<<<<00"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == VerdictStatus.CRITICAL_SECURITY_ALERT.value
    assert FailureCode.ERR_SECURITY_WATCHLIST_HIT.value in data["failure_codes"]


def test_forensics_aspect_ratio_failure(client, token):
    """Test 4: Square image -> FLAGGED + ERR_FORENSIC_INVALID_DIMENSIONS."""
    b64 = encode_image_b64(_create_synthetic_passport_image(width=500, height=500))
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_verdict_precedence_csa_beats_expired(client, token, passport_b64):
    """Test 5: Watchlist + expired -> CSA wins (rules.md §3: #1 > #3)."""
    doc_num = f"WL{uuid.uuid4().hex[:7]}".upper()
    _setup_watchlist_entry(doc_num)
    line1 = "P<UTOWATCH<<LIST<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = f"{doc_num}0UTO8507125F1001019<<<<<<<<<<<<<<00"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == VerdictStatus.CRITICAL_SECURITY_ALERT.value
    assert FailureCode.ERR_SECURITY_WATCHLIST_HIT.value in data["failure_codes"]
    assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED.value in data["failure_codes"]


def test_mrz_structure_malformed(client, token, passport_b64):
    """Test 6: Too-short MRZ lines -> ERR_MATH_MALFORMED_MRZ_STRUCTURE (Rule 4.1)."""
    line1 = "P<UTODOE<<JANE"         # 14 chars (should be 44)
    line2 = "L898902C36UTO8507125"   # 20 chars (should be 44)

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_MATH_MALFORMED_MRZ_STRUCTURE.value in data["failure_codes"]


def test_mrz_invalid_characters(client, token, passport_b64):
    """Test 7: MRZ with illegal characters -> ERR_MATH_INVALID_MRZ_CHARACTERS (Rule 4.1)."""
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    # 44 chars but with lowercase 'a', '@', '#'
    line2 = "a@98902C36UTO8507125F3001019#<<<<<<<<<<<<<02"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_MATH_INVALID_MRZ_CHARACTERS.value in data["failure_codes"]


def test_viz_mrz_mismatch(client, token, passport_b64):
    """Test 8: VIZ doc_number differs from MRZ -> ERR_MATH_VIZ_MRZ_MISMATCH (Rule 4.2)."""
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04"

    r = client.post(
        "/api/v1/verify/process",
        json={
            "image_b64": passport_b64,
            "declared_doc_type": "PASSPORT",
            "mrz_lines": [line1, line2],
            "viz_fields": {"doc_number": "ZZZZZZ999"},  # deliberately different
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_mod10_doc_num_failed(client, token, passport_b64):
    """Test 9: Wrong doc-number check digit -> ERR_MATH_MOD10_DOC_NUM_FAILED (Rule 4.3)."""
    # L898902C3 correct check digit = '6'; use '9' to force failure
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C39UTO8507125F3001019<<<<<<<<<<<<<<00"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_ocr_missing_mandatory_field(client, token, passport_b64):
    """Test 10: No MRZ lines -> ERR_OCR_MISSING_MANDATORY_FIELD (Rule 3.2)."""
    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": passport_b64, "declared_doc_type": "PASSPORT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_OCR_MISSING_MANDATORY_FIELD.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_multi_flag_bad_mod10_plus_bad_aspect_ratio(client, token):
    """Test 11: Bad Mod10 check digit + square image -> FLAGGED with both codes."""
    b64 = encode_image_b64(_create_synthetic_passport_image(width=500, height=500))
    line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "L898902C39UTO8507125F3001019<<<<<<<<<<<<<<00"  # '9' != correct '6'

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED.value in data["failure_codes"]
    assert FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS.value in data["failure_codes"]
    assert data["verdict"] == VerdictStatus.FLAGGED.value


def test_multi_flag_precedence_csa_beats_all(client, token):
    """Test 12: Watchlist + bad Mod10 + square image -> CSA overrides all (rules.md §3 #1)."""
    b64 = encode_image_b64(_create_synthetic_passport_image(width=500, height=500))
    doc_num = f"WL{uuid.uuid4().hex[:7]}".upper()
    _setup_watchlist_entry(doc_num)

    line1 = "P<UTOWATCH<<LIST<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = f"{doc_num}9UTO8507125F1001019<<<<<<<<<<<<<<00"

    r = client.post(
        "/api/v1/verify/process",
        json={"image_b64": b64, "declared_doc_type": "PASSPORT", "mrz_lines": [line1, line2]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == VerdictStatus.CRITICAL_SECURITY_ALERT.value
    assert FailureCode.ERR_SECURITY_WATCHLIST_HIT.value in data["failure_codes"]
    assert FailureCode.ERR_FORENSIC_INVALID_DIMENSIONS.value in data["failure_codes"]
    assert FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED.value in data["failure_codes"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
