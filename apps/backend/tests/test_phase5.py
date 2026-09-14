"""
tests/test_phase5.py — Verification test suite for Phase 5: Non-Repudiation, Audit Logging & Final API Hardening.

Requirements:
  1. Unit tests for audit record generation and SHA-256 hash verification (proving tamper-resistance).
  2. End-to-end integration tests confirming the audit hash is properly generated and returned in API responses.
  3. Tamper detection tests (modifying an audit record invalidates its hash).
  4. Edge-case sanitization for invalid file uploads, empty buffers, and corrupted inputs.
"""

from __future__ import annotations

import copy
import datetime
from datetime import timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

import cv2
import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.audit import (
    AuditRecord,
    compute_audit_hash,
    compute_record_hash,
    verify_audit_record,
    verify_audit_log_trail,
    write_audit_record,
)
from app.core.db import get_db_connection
from app.core.preprocessor import encode_image_b64
from app.main import app
from app.schemas.errors import ErrorCode
from app.schemas.verification import FailureCode, VerdictStatus


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _generate_valid_token(officer_id: str | None = None, terminal_id: str = "TERM-P5") -> str:
    if officer_id is None:
        officer_id = f"off-{uuid.uuid4().hex[:8]}"
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
    """Create a passport image with exact ID-3 aspect ratio card."""
    img = np.full((height, width, 3), 40, dtype=np.uint8)
    x1, y1 = 71, 50
    x2, y2 = width - 71, height - 50
    cv2.rectangle(img, (x1, y1), (x2, y2), (200, 200, 200), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 3)

    cv2.putText(img, "PASSPORT", (x1 + 30, y1 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 2)
    noise = np.random.randint(0, 10, (height, width, 3), dtype=np.uint8)
    return cv2.add(img, noise)


# ---------------------------------------------------------------------------
# 1. Unit Tests: Cryptographic Hashing & Non-Repudiation
# ---------------------------------------------------------------------------


class TestAuditHashingUnits:
    def test_compute_hash_produces_valid_sha256(self):
        h = compute_audit_hash(
            log_id="log-001",
            timestamp_utc="2026-09-13 12:00:00",
            officer_id="officer-42",
            verdict="PASS",
            failure_codes=[],
            doc_type="PASSPORT",
            doc_number="A12345678",
            raw_mrz=["P<UTO...", "A123..."],
            forensics_metrics={"ela": 1.2},
        )
        assert isinstance(h, str)
        assert len(h) == 64
        int(h, 16)  # Valid hex string

    def test_hash_is_deterministic(self):
        kwargs = dict(
            log_id="log-fixed",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="FLAGGED",
            failure_codes=["ERR_MATH_MOD10_DOC_NUM_FAILED"],
            doc_type="PASSPORT",
            doc_number="X99999999",
            raw_mrz=["P<UTO...", "X999..."],
            forensics_metrics={"laplacian": 150.5},
        )
        h1 = compute_audit_hash(**kwargs)
        h2 = compute_audit_hash(**kwargs)
        assert h1 == h2

    def test_hash_order_invariance_for_failure_codes(self):
        """Canonical sorting ensures permutation of failure codes produces same hash."""
        h1 = compute_audit_hash(
            log_id="log-perm",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="FLAGGED",
            failure_codes=["ERR_B", "ERR_A"],
        )
        h2 = compute_audit_hash(
            log_id="log-perm",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="FLAGGED",
            failure_codes=["ERR_A", "ERR_B"],
        )
        assert h1 == h2

    def test_hash_sensitivity_verdict_change(self):
        h_pass = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="PASS",
            failure_codes=[],
        )
        h_flagged = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="FLAGGED",
            failure_codes=[],
        )
        assert h_pass != h_flagged

    def test_hash_sensitivity_doc_number_change(self):
        h1 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="PASS",
            failure_codes=[],
            doc_number="A11111111",
        )
        h2 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="PASS",
            failure_codes=[],
            doc_number="A22222222",
        )
        assert h1 != h2

    def test_hash_sensitivity_officer_id_change(self):
        h1 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="officer-alice",
            verdict="PASS",
            failure_codes=[],
        )
        h2 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="officer-bob",
            verdict="PASS",
            failure_codes=[],
        )
        assert h1 != h2

    def test_hash_sensitivity_mrz_change(self):
        h1 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="PASS",
            failure_codes=[],
            raw_mrz=["LINE1", "LINE2"],
        )
        h2 = compute_audit_hash(
            log_id="log-1",
            timestamp_utc="2026-09-13 10:00:00",
            officer_id="off-1",
            verdict="PASS",
            failure_codes=[],
            raw_mrz=["LINE1", "LINE2_MODIFIED"],
        )
        assert h1 != h2


# ---------------------------------------------------------------------------
# 2. Tamper Detection Tests
# ---------------------------------------------------------------------------


class TestTamperDetection:
    def _create_clean_record(self) -> dict:
        log_id = str(uuid.uuid4())
        ts = "2026-09-13 14:00:00"
        officer = "off-secure"
        verdict = "FLAGGED"
        failures = ["ERR_MATH_MOD10_DOC_NUM_FAILED"]
        doc_num = "L898902C3"
        doc_type = "PASSPORT"
        raw_mrz = ["P<UTODOE<<JANE", "L898902C3..."]
        metrics = {"laplacian_variance": 234.5}

        h = compute_audit_hash(
            log_id=log_id,
            timestamp_utc=ts,
            officer_id=officer,
            verdict=verdict,
            failure_codes=failures,
            doc_type=doc_type,
            doc_number=doc_num,
            raw_mrz=raw_mrz,
            forensics_metrics=metrics,
        )

        return {
            "log_id": log_id,
            "timestamp_utc": ts,
            "officer_id": officer,
            "verdict": verdict,
            "failure_codes": failures,
            "doc_type": doc_type,
            "doc_number": doc_num,
            "raw_mrz": raw_mrz,
            "forensics_metrics": metrics,
            "audit_hash": h,
        }

    def test_clean_record_verifies_successfully(self):
        rec = self._create_clean_record()
        assert verify_audit_record(rec) is True

    def test_tampering_verdict_invalidates_hash(self):
        rec = self._create_clean_record()
        rec["verdict"] = "PASS"  # Tamper attempt: covertly downgrade verdict
        assert verify_audit_record(rec) is False

    def test_tampering_failure_codes_invalidates_hash(self):
        rec = self._create_clean_record()
        rec["failure_codes"] = []  # Tamper attempt: erase failure codes
        assert verify_audit_record(rec) is False

    def test_tampering_doc_number_invalidates_hash(self):
        rec = self._create_clean_record()
        rec["doc_number"] = "TAMPERED99"
        assert verify_audit_record(rec) is False

    def test_tampering_officer_id_invalidates_hash(self):
        rec = self._create_clean_record()
        rec["officer_id"] = "impersonator"
        assert verify_audit_record(rec) is False

    def test_tampering_audit_hash_itself_fails(self):
        rec = self._create_clean_record()
        rec["audit_hash"] = "0" * 64  # Bad signature
        assert verify_audit_record(rec) is False

    def test_tampering_missing_audit_hash_fails(self):
        rec = self._create_clean_record()
        rec["audit_hash"] = None
        assert verify_audit_record(rec) is False

    def test_trail_verification_detects_tampered_line(self, tmp_path):
        """Append records to a JSON-L trail and verify that tampering with any line is detected."""
        trail_file = tmp_path / "test_trail.jsonl"

        rec1 = self._create_clean_record()
        rec2 = self._create_clean_record()
        rec3 = self._create_clean_record()

        # Write clean records
        with open(trail_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec1) + "\n")
            f.write(json.dumps(rec2) + "\n")
            f.write(json.dumps(rec3) + "\n")

        status_clean = verify_audit_log_trail(trail_file)
        assert status_clean["total_records"] == 3
        assert status_clean["valid_records"] == 3
        assert status_clean["tampered_records"] == []
        assert status_clean["is_tamper_free"] is True

        # Now tamper with record 2 in the file
        rec2_tampered = copy.deepcopy(rec2)
        rec2_tampered["verdict"] = "PASS"  # Tamper

        with open(trail_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec1) + "\n")
            f.write(json.dumps(rec2_tampered) + "\n")
            f.write(json.dumps(rec3) + "\n")

        status_tampered = verify_audit_log_trail(trail_file)
        assert status_tampered["total_records"] == 3
        assert status_tampered["valid_records"] == 2
        assert status_tampered["tampered_records"] == [rec2["log_id"]]
        assert status_tampered["is_tamper_free"] is False


# ---------------------------------------------------------------------------
# 3. End-to-End API Integration & Response Hashing Tests
# ---------------------------------------------------------------------------


class TestApiAuditIntegration:
    def test_verify_process_returns_audit_hash(self):
        client = TestClient(app)
        officer_id = f"off-{uuid.uuid4().hex[:8]}"
        token = _generate_valid_token(officer_id=officer_id)

        # Unique document number to avoid passback
        doc_num = f"HA{uuid.uuid4().hex[:7]}".upper()

        doc_img = _create_synthetic_passport_image()
        b64_str = encode_image_b64(doc_img)

        line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
        # Line2 with doc_num
        line2 = f"{doc_num}0UTO8507125F3001019<<<<<<<<<<<<<<00"

        payload = {
            "image_b64": b64_str,
            "declared_doc_type": "PASSPORT",
            "terminal_id": "GATE-05",
            "mrz_lines": [line1, line2],
            "viz_fields": {"doc_number": doc_num},
        }

        response = client.post(
            "/api/v1/verify/process",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert "audit_hash" in data
        assert isinstance(data["audit_hash"], str)
        assert len(data["audit_hash"]) == 64

        # Verify audit record is also in SQLite with the same hash
        conn = get_db_connection()
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE log_id = ?", (data["log_id"],)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["audit_hash"] == data["audit_hash"]

    def test_verify_process_audit_hash_verifies_successfully(self):
        """Confirm that the audit record written during the API call passes cryptographic verification."""
        client = TestClient(app)
        token = _generate_valid_token()
        doc_num = f"VR{uuid.uuid4().hex[:7]}".upper()

        doc_img = _create_synthetic_passport_image()
        b64_str = encode_image_b64(doc_img)

        line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
        line2 = f"{doc_num}0UTO8507125F3001019<<<<<<<<<<<<<<00"

        payload = {
            "image_b64": b64_str,
            "declared_doc_type": "PASSPORT",
            "terminal_id": "GATE-05",
            "mrz_lines": [line1, line2],
            "viz_fields": {"doc_number": doc_num},
        }

        response = client.post(
            "/api/v1/verify/process",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "audit_hash" in data
        audit_hash = data["audit_hash"]
        assert len(audit_hash) == 64

        # Verify the record persisted in the audit trail is valid
        trail_status = verify_audit_log_trail()
        assert trail_status["is_tamper_free"] is True
        assert trail_status["total_records"] > 0


# ---------------------------------------------------------------------------
# 4. API Hardening & Edge-Case Sanitization Tests
# ---------------------------------------------------------------------------


class TestApiHardeningAndSanitization:
    def test_empty_file_upload_rejected(self):
        """Uploading a 0-byte file must be caught with PAYLOAD_IMAGE_MISSING."""
        client = TestClient(app)
        token = _generate_valid_token()

        response = client.post(
            "/api/v1/verify/process",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_IMAGE_MISSING.value

    def test_empty_base64_string_rejected(self):
        client = TestClient(app)
        token = _generate_valid_token()

        response = client.post(
            "/api/v1/verify/process",
            json={"image_b64": "   ", "declared_doc_type": "PASSPORT", "terminal_id": "G1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_IMAGE_MISSING.value

    def test_corrupted_base64_payload_rejected(self):
        """Non-image bytes encoded in base64 must raise PAYLOAD_IMAGE_DECODE_FAILED."""
        client = TestClient(app)
        token = _generate_valid_token()

        import base64
        corrupted_b64 = base64.b64encode(b"This is definitely not a JPEG image buffer!").decode("utf-8")

        response = client.post(
            "/api/v1/verify/process",
            json={"image_b64": corrupted_b64, "declared_doc_type": "PASSPORT", "terminal_id": "G1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_IMAGE_DECODE_FAILED.value

    def test_invalid_json_body_type_rejected(self):
        client = TestClient(app)
        token = _generate_valid_token()

        response = client.post(
            "/api/v1/verify/process",
            content=b'"just a raw string, not a JSON dict"',
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_INVALID.value

    def test_invalid_mrz_lines_type_rejected(self):
        client = TestClient(app)
        token = _generate_valid_token()
        doc_img = _create_synthetic_passport_image()
        b64_str = encode_image_b64(doc_img)

        response = client.post(
            "/api/v1/verify/process",
            json={
                "image_b64": b64_str,
                "declared_doc_type": "PASSPORT",
                "terminal_id": "G1",
                "mrz_lines": "this should be a list, not a string",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_INVALID.value

    def test_invalid_viz_fields_type_rejected(self):
        client = TestClient(app)
        token = _generate_valid_token()
        doc_img = _create_synthetic_passport_image()
        b64_str = encode_image_b64(doc_img)

        response = client.post(
            "/api/v1/verify/process",
            json={
                "image_b64": b64_str,
                "declared_doc_type": "PASSPORT",
                "terminal_id": "G1",
                "viz_fields": ["should", "be", "a", "dict"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.PAYLOAD_INVALID.value

    def test_unauthenticated_request_blocked(self):
        client = TestClient(app)
        doc_img = _create_synthetic_passport_image()
        b64_str = encode_image_b64(doc_img)

        response = client.post(
            "/api/v1/verify/process",
            json={
                "image_b64": b64_str,
                "declared_doc_type": "PASSPORT",
                "terminal_id": "G1",
            },
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == ErrorCode.AUTH_NO_FINGERPRINT.value
