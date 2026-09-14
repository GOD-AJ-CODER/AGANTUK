"""
core/audit.py — Cryptographic non-repudiation audit logging.

Provides:
  - Canonical SHA-256 hash generation over verification output (verdict, failure codes,
    raw MRZ, forensics metrics, timestamp, officer ID, and document identifier).
  - Append-only tamper-evident audit record persistence (JSON-L and local SQLite audit_logs).
  - Verification & tamper-detection routines.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import write_audit_log

logger = logging.getLogger(__name__)

# Default path for the append-only JSON-L audit log file in database/
DEFAULT_AUDIT_LOG_DIR = Path(__file__).resolve().parents[4] / "database"
DEFAULT_AUDIT_JSONL_PATH = DEFAULT_AUDIT_LOG_DIR / "audit_trail.jsonl"

_FILE_LOCK = threading.Lock()


@dataclass
class AuditRecord:
    """
    Immutable representation of a completed verification scan.
    """
    log_id: str
    timestamp_utc: str
    officer_id: str
    verdict: str
    failure_codes: List[str]
    doc_type: Optional[str] = None
    doc_number: Optional[str] = None
    raw_mrz: List[str] = field(default_factory=list)
    forensics_metrics: Dict[str, Any] = field(default_factory=dict)
    audit_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_audit_hash(
    log_id: str,
    timestamp_utc: str,
    officer_id: str,
    verdict: str,
    failure_codes: List[str],
    doc_type: Optional[str] = None,
    doc_number: Optional[str] = None,
    raw_mrz: Optional[List[str]] = None,
    forensics_metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a deterministic SHA-256 hash across canonical verification output.
    
    Guarantees non-repudiation: altering verdict, failures, MRZ, metrics, or metadata
    produces a hash mismatch.
    """
    canonical_payload = {
        "doc_number": str(doc_number) if doc_number is not None else None,
        "doc_type": str(doc_type) if doc_type is not None else None,
        "failure_codes": sorted(str(code) for code in (failure_codes or [])),
        "forensics_metrics": forensics_metrics or {},
        "log_id": str(log_id),
        "officer_id": str(officer_id),
        "raw_mrz": [str(line) for line in (raw_mrz or [])],
        "timestamp_utc": str(timestamp_utc),
        "verdict": str(verdict),
    }

    canonical_json = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_record_hash(record: Dict[str, Any]) -> str:
    """
    Compute the canonical SHA-256 hash from an existing dictionary record.
    """
    return compute_audit_hash(
        log_id=record.get("log_id", ""),
        timestamp_utc=record.get("timestamp_utc", ""),
        officer_id=record.get("officer_id", ""),
        verdict=record.get("verdict", ""),
        failure_codes=record.get("failure_codes", []),
        doc_type=record.get("doc_type"),
        doc_number=record.get("doc_number"),
        raw_mrz=record.get("raw_mrz", []),
        forensics_metrics=record.get("forensics_metrics", {}),
    )


def verify_audit_record(record: Dict[str, Any]) -> bool:
    """
    Verify the cryptographic integrity of an audit record.
    Returns True if the record matches its SHA-256 hash; False if tampered.
    """
    recorded_hash = record.get("audit_hash")
    if not recorded_hash or not isinstance(recorded_hash, str):
        return False

    expected_hash = compute_record_hash(record)
    return hmac.compare_digest(recorded_hash.lower().strip(), expected_hash.lower().strip())


def write_audit_record(
    log_id: str,
    officer_id: str,
    verdict: str,
    failure_codes: List[str],
    doc_type: Optional[str] = None,
    doc_number: Optional[str] = None,
    raw_mrz: Optional[List[str]] = None,
    forensics_metrics: Optional[Dict[str, Any]] = None,
    timestamp_utc: Optional[str] = None,
    jsonl_path: Optional[Path | str] = None,
) -> AuditRecord:
    """
    Create, cryptographically sign with SHA-256, and persist an immutable audit record.
    
    Persists to:
      1. Append-only JSON-L file (DEFAULT_AUDIT_JSONL_PATH)
      2. SQLite audit_logs table with audit_hash column
    """
    if timestamp_utc is None:
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    audit_hash = compute_audit_hash(
        log_id=log_id,
        timestamp_utc=timestamp_utc,
        officer_id=officer_id,
        verdict=verdict,
        failure_codes=failure_codes,
        doc_type=doc_type,
        doc_number=doc_number,
        raw_mrz=raw_mrz,
        forensics_metrics=forensics_metrics,
    )

    record = AuditRecord(
        log_id=log_id,
        timestamp_utc=timestamp_utc,
        officer_id=officer_id,
        doc_type=doc_type,
        doc_number=doc_number,
        verdict=verdict,
        failure_codes=failure_codes,
        raw_mrz=raw_mrz or [],
        forensics_metrics=forensics_metrics or {},
        audit_hash=audit_hash,
    )

    # 1. Append to JSON-L audit file
    target_path = Path(jsonl_path) if jsonl_path else DEFAULT_AUDIT_JSONL_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    record_dict = record.to_dict()
    serialized_line = json.dumps(record_dict, sort_keys=True, ensure_ascii=True) + "\n"

    with _FILE_LOCK:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(serialized_line)
            f.flush()
            os.fsync(f.fileno())

    # 2. Commit to local SQLite audit_logs table
    write_audit_log(
        log_id=log_id,
        officer_id=officer_id,
        doc_type=doc_type,
        doc_number=doc_number,
        verdict_status=verdict,
        confidence_scores=forensics_metrics or {},
        failure_reason_codes=failure_codes,
        audit_hash=audit_hash,
    )

    return record


def verify_audit_log_trail(jsonl_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """
    Audit-integrity sweep: verify the cryptographic validity of all records in the trail.
    
    Returns:
        {
            "total_records": int,
            "valid_records": int,
            "tampered_records": List[str],  # list of tampered log_ids
            "is_tamper_free": bool
        }
    """
    target_path = Path(jsonl_path) if jsonl_path else DEFAULT_AUDIT_JSONL_PATH
    if not target_path.exists():
        return {
            "total_records": 0,
            "valid_records": 0,
            "tampered_records": [],
            "is_tamper_free": True,
        }

    total = 0
    valid = 0
    tampered_ids: List[str] = []

    with _FILE_LOCK:
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                total += 1
                try:
                    data = json.loads(line_str)
                    if verify_audit_record(data):
                        valid += 1
                    else:
                        tampered_ids.append(data.get("log_id", f"record-{total}"))
                except Exception:
                    tampered_ids.append(f"record-{total}")

    return {
        "total_records": total,
        "valid_records": valid,
        "tampered_records": tampered_ids,
        "is_tamper_free": len(tampered_ids) == 0,
    }
