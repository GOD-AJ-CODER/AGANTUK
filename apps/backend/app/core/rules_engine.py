"""
core/rules_engine.py — Core security logic and verdict assembly.

Rules Reference:
  - Stage 5: Chronological and Logical consistency checks.
  - Rule 6.1: Pass-back detection (same doc within 15 minutes).
  - Rule 6.2: Local Watchlist matching.
  - Rule 4.4: Modulo-37 cross-reference validation.
  - Verdict Precedence: Highest severity wins (rules.md §3).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from app.core.db import get_db
from app.core.mrz import ParsedMRZ, MRZ_CHAR_MAP, CHAR_WEIGHTS
from app.schemas.verification import FailureCode, VerdictStatus

logger = logging.getLogger(__name__)

# ─── Modulo-37 Engine (Rule 4.4) ─────────────────────────────────────────────

# Modulo-37 result alphabet: 0-9 then A-Z then *
MOD37_RESULT_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*"


def calculate_mod37_digit(data: str) -> str:
    """
    Rule 4.4: Modulo-37 Cross-Reference Engine.

    Uses the same MRZ character map and [7,3,1] repeating weights as Modulo-10
    but divides modulo 37, with the result mapped to alphanumeric characters
    (0-9 → '0'-'9', 10-35 → 'A'-'Z', 36 → '*').

    Args:
        data: Alphanumeric string to validate (without the check character).

    Returns:
        Single character check-character string from MOD37_RESULT_CHARS.
    """
    total = 0
    for i, char in enumerate(data.upper()):
        val = MRZ_CHAR_MAP.get(char, 0)
        weight = CHAR_WEIGHTS[i % 3]
        total += val * weight
    remainder = total % 37
    return MOD37_RESULT_CHARS[remainder]


def verify_mod37(data: str, expected_char: str) -> bool:
    """
    Rule 4.4: Validate a Modulo-37 check character.

    Args:
        data: The alphanumeric data string (without check character).
        expected_char: The single check character to validate against.

    Returns:
        True if calculated check character matches expected_char.
    """
    return calculate_mod37_digit(data) == expected_char.upper()

def check_chronological_logic(mrz: ParsedMRZ, viz_fields: Optional[dict] = None) -> List[FailureCode]:
    """
    Stage 5: Chronological & Logical Consistency.
    - Expiry_Date < Current_UTC_Date
    - Issue_Date > Current_UTC_Date
    - Issue_Date >= Expiry_Date
    - Age bounds [0, 120]
    - Issue_Date < DOB
    """
    failures = []
    now = datetime.now(timezone.utc)
    current_year_last2 = now.year % 100
    current_century = (now.year // 100) * 100

    def parse_yymmdd(yymmdd: str, is_dob: bool = False) -> Optional[datetime]:
        if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
            return None
        
        yy = int(yymmdd[:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])

        if mm < 1 or mm > 12 or dd < 1 or dd > 31:
            return None

        # Handle century (simplified ICAO 9303 rule)
        if is_dob:
            year = current_century + yy if yy <= current_year_last2 else current_century - 100 + yy
        else:
            year = current_century + yy if yy <= (current_year_last2 + 20) else current_century - 100 + yy
            
        try:
            return datetime(year, mm, dd, tzinfo=timezone.utc)
        except ValueError:
            return None

    dob_dt = parse_yymmdd(mrz.date_of_birth, is_dob=True)
    exp_dt = parse_yymmdd(mrz.expiry_date)
    
    # Try to get Issue Date from VIZ
    issue_dt = None
    if viz_fields and viz_fields.get("issue_date"):
        from app.core.ocr import normalize_date_to_yymmdd
        issue_yymmdd = normalize_date_to_yymmdd(viz_fields.get("issue_date"))
        if issue_yymmdd:
            issue_dt = parse_yymmdd(issue_yymmdd)

    # 1. Expiry Check
    if exp_dt and exp_dt < now:
        failures.append(FailureCode.ERR_LOGIC_DOCUMENT_EXPIRED)

    # 2. Age Check
    if dob_dt:
        age = now.year - dob_dt.year
        if age < 0 or age > 120:
            failures.append(FailureCode.ERR_LOGIC_INVALID_AGE)

    # 3. Issue Date Checks
    if issue_dt:
        if issue_dt > now:
            failures.append(FailureCode.ERR_LOGIC_FUTURE_ISSUE_DATE)
        if exp_dt and issue_dt >= exp_dt:
            failures.append(FailureCode.ERR_LOGIC_TIMELINE_CONTRADICTION)
        if dob_dt and issue_dt < dob_dt:
            failures.append(FailureCode.ERR_LOGIC_ISSUED_BEFORE_BIRTH)
    
    return failures

def check_passback(doc_number: str) -> bool:
    """
    Rule 6.1 (Pass-Back): Document number matches a local SQLite scan 
    within the last 15 minutes.
    """
    if not doc_number:
        return False
        
    try:
        with get_db() as conn:
            # Check for same doc_number in the last 15 minutes
            fifteen_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
            query = """
                SELECT 1 FROM audit_logs 
                WHERE doc_number = ? 
                AND timestamp_utc >= ? 
                LIMIT 1
            """
            result = conn.execute(query, (doc_number, fifteen_mins_ago)).fetchone()
            return result is not None
    except Exception as e:
        logger.error(f"Passback check failed: {e}")
        return False

def check_watchlist(doc_number: str, full_name: str, dob: str) -> bool:
    """
    Rule 6.2 (Blacklist Match): Document_Number OR Full_Name + DOB exact-matches 
    the local watchlist cache.
    """
    try:
        with get_db() as conn:
            # 1. Check Doc Number
            if doc_number:
                res = conn.execute("SELECT 1 FROM watchlist WHERE doc_number = ? LIMIT 1", (doc_number,)).fetchone()
                if res:
                    return True
            
            # 2. Check Name + DOB
            if full_name and dob:
                res = conn.execute("SELECT 1 FROM watchlist WHERE full_name = ? AND dob = ? LIMIT 1", (full_name, dob)).fetchone()
                if res:
                    return True
                    
        return False
    except Exception as e:
        logger.error(f"Watchlist check failed: {e}")
        return False

def resolve_verdict(failure_codes: List[FailureCode]) -> VerdictStatus:
    """
    Resolve verdict precedence per rules.md §3.
    Highest-severity verdict always wins.
    """
    if not failure_codes:
        return VerdictStatus.PASS

    # 1. CRITICAL_SECURITY_ALERT
    if FailureCode.ERR_SECURITY_WATCHLIST_HIT in failure_codes:
        return VerdictStatus.CRITICAL_SECURITY_ALERT

    # 2. FLAGGED with CRITICAL FLAG (Rules 4.2, 4.3, 6.1)
    critical_flags = {
        FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH,
        FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED,
        FailureCode.ERR_MATH_MOD10_DOB_FAILED,
        FailureCode.ERR_MATH_MOD10_EXPIRY_FAILED,
        FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED,
        FailureCode.ERR_SECURITY_PASSBACK_DETECTED
    }
    if any(fc in critical_flags for fc in failure_codes):
        return VerdictStatus.FLAGGED

    # 3. FLAGGED (Standard flags starting with ERR_)
    if any(fc.value.startswith("ERR_") for fc in failure_codes):
        return VerdictStatus.FLAGGED

    # 4. MANUAL_REVIEW (Starting with WARN_)
    if any(fc.value.startswith("WARN_") for fc in failure_codes):
        return VerdictStatus.MANUAL_REVIEW

    return VerdictStatus.PASS

def evaluate_rules(
    mrz: ParsedMRZ,
    forensics_failures: List[FailureCode],
    viz_fields: Optional[dict] = None,
    ocr_failure_codes: Optional[List[FailureCode]] = None,
) -> List[FailureCode]:
    """
    Main rule evaluation pipeline.

    Args:
        mrz: Parsed MRZ object containing MRZ-level failure codes.
        forensics_failures: Failure codes from the forensics stage (Rules 2.x).
        viz_fields: Optional VIZ fields for cross-zonal consistency (Rule 4.2).
        ocr_failure_codes: Optional additional failure codes from OCR pipeline
                           (e.g., WARN_OCR_LOW_CONFIDENCE, ERR_OCR_MISSING_MANDATORY_FIELD).
                           These are merged after MRZ failures to prevent double-counting.
    """
    all_failures = list(forensics_failures)

    # 1. MRZ/OCR failures from parsed MRZ object (Rules 4.1, 4.2, 4.3)
    all_failures.extend(mrz.failure_codes)

    # 2. Additional OCR-level codes from process_ocr_and_mrz (Rule 3.2)
    if ocr_failure_codes:
        for code in ocr_failure_codes:
            if code not in all_failures:
                all_failures.append(code)

    # 3. Chronological Logic (Stage 5)
    all_failures.extend(check_chronological_logic(mrz, viz_fields))

    # 4. Pass-back detection (Rule 6.1)
    if mrz.document_number and check_passback(mrz.document_number):
        all_failures.append(FailureCode.ERR_SECURITY_PASSBACK_DETECTED)

    # 5. Watchlist Hit (Rule 6.2)
    full_name = f"{mrz.given_names} {mrz.surname}".strip()
    if check_watchlist(mrz.document_number, full_name, mrz.date_of_birth):
        all_failures.append(FailureCode.ERR_SECURITY_WATCHLIST_HIT)

    # Remove duplicates while preserving insertion order
    seen: set[FailureCode] = set()
    deduped: list[FailureCode] = []
    for fc in all_failures:
        if fc not in seen:
            seen.add(fc)
            deduped.append(fc)
    return deduped

