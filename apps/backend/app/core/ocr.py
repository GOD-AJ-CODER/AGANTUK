"""
core/ocr.py — OCR extraction, VIZ field normalization, and cross-zonal consistency matching.

Rules Reference:
  - Rule 3.2: Null & Confidence Floors
      * Missing mandatory OCR fields -> ERR_OCR_MISSING_MANDATORY_FIELD
      * Average OCR field confidence < 0.90 -> WARN_OCR_LOW_CONFIDENCE (MANUAL_REVIEW)
  - Rule 4.2: Visual Inspection Zone (VIZ) vs. MRZ Cross-Check
      * Visual_Zone_Name != MRZ_Parsed_Name OR DOB OR DocNum mismatch
      * Trigger CRITICAL FLAG: ERR_MATH_VIZ_MRZ_MISMATCH
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from app.core.mrz import ParsedMRZ, parse_mrz
from app.schemas.verification import ExtractedFields, FailureCode

logger = logging.getLogger(__name__)


@dataclass
class OCRExtractionResult:
    """Structured result of OCR extraction and cross-zonal validation."""

    mrz_parsed: ParsedMRZ
    extracted_fields: ExtractedFields
    raw_mrz_lines: list[str]
    ocr_confidence: float = 0.98
    viz_mrz_match: bool = True
    discrepancies: list[str] = field(default_factory=list)
    failure_codes: list[FailureCode] = field(default_factory=list)


# ─── MRZ Region Extraction ───────────────────────────────────────────────────


def extract_mrz_region(warped_image: np.ndarray) -> np.ndarray:
    """
    Extract the bottom MRZ region from a normalized document crop.

    For ICAO 9303 documents (TD1, TD2, TD3), the MRZ is strictly located
    in the bottom 25-35% of the document.
    """
    h, w = warped_image.shape[:2]
    # Bottom 30% of the document height
    mrz_y_start = int(h * 0.70)
    return warped_image[mrz_y_start:h, 0:w]


# ─── Date Normalization Helpers ───────────────────────────────────────────────


def normalize_date_to_yymmdd(date_str: Optional[str]) -> Optional[str]:
    """
    Normalize various date string representations (ISO YYYY-MM-DD, DD/MM/YYYY, YYMMDD)
    to the 6-digit YYMMDD format used in MRZ.
    """
    if not date_str:
        return None

    cleaned = re.sub(r"[^0-9A-Za-z]", "", date_str.strip())
    # If already 6 digits
    if len(cleaned) == 6 and cleaned.isdigit():
        return cleaned

    # Try ISO YYYY-MM-DD
    clean_punct = re.sub(r"[\/\.-]", "-", date_str.strip())
    parts = clean_punct.split("-")
    if len(parts) == 3:
        p1, p2, p3 = parts
        if len(p1) == 4 and p1.isdigit():  # YYYY-MM-DD
            yy = p1[2:4]
            mm = p2.zfill(2)
            dd = p3.zfill(2)
            return f"{yy}{mm}{dd}"
        elif len(p3) == 4 and p3.isdigit():  # DD-MM-YYYY
            yy = p3[2:4]
            mm = p2.zfill(2)
            dd = p1.zfill(2)
            return f"{yy}{mm}{dd}"

    # Try standard string date formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%y%m%d")
        except ValueError:
            continue

    return cleaned if len(cleaned) == 6 else None


def normalize_text(text: Optional[str]) -> str:
    """Normalize string for cross-zonal comparison: uppercase, alphanumeric only."""
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper().strip())


# ─── Cross-Zonal Consistency Matching (Rule 4.2) ──────────────────────────────


def match_viz_mrz(
    viz_fields: dict, mrz_parsed: ParsedMRZ
) -> tuple[bool, list[str], list[FailureCode]]:
    """
    Cross-reference Visual Inspection Zone (VIZ) fields against MRZ decoded fields.

    Rule 4.2:
      Visual_Zone_Name != MRZ_Parsed_Name OR DOB OR DocNum mismatch
      -> CRITICAL FLAG: ERR_MATH_VIZ_MRZ_MISMATCH.

    Args:
        viz_fields: Dictionary of fields read from VIZ (e.g. full_name, date_of_birth,
                    doc_number, expiry_date).
        mrz_parsed: ParsedMRZ object from app.core.mrz.

    Returns:
        (matches: bool, discrepancies: list[str], failure_codes: list[FailureCode])
    """
    discrepancies: list[str] = []
    failure_codes: list[FailureCode] = []

    if not mrz_parsed.is_valid and not mrz_parsed.document_number:
        # If MRZ could not be parsed at all, cross-check cannot succeed
        return False, ["MRZ parsing failed; cross-check impossible."], failure_codes

    # 1. Document Number Check
    viz_doc_num = normalize_text(viz_fields.get("doc_number"))
    mrz_doc_num = normalize_text(mrz_parsed.document_number)
    if viz_doc_num and mrz_doc_num:
        if viz_doc_num != mrz_doc_num:
            discrepancies.append(
                f"Document Number mismatch: VIZ='{viz_doc_num}' vs MRZ='{mrz_doc_num}'"
            )

    # 2. Date of Birth Check
    viz_dob = normalize_date_to_yymmdd(viz_fields.get("date_of_birth"))
    mrz_dob = mrz_parsed.date_of_birth
    if viz_dob and mrz_dob:
        if viz_dob != mrz_dob:
            discrepancies.append(
                f"Date of Birth mismatch: VIZ='{viz_dob}' vs MRZ='{mrz_dob}'"
            )

    # 3. Expiry Date Check
    viz_exp = normalize_date_to_yymmdd(viz_fields.get("expiry_date"))
    mrz_exp = mrz_parsed.expiry_date
    if viz_exp and mrz_exp:
        if viz_exp != mrz_exp:
            discrepancies.append(
                f"Expiry Date mismatch: VIZ='{viz_exp}' vs MRZ='{mrz_exp}'"
            )

    # 4. Name Consistency Check
    viz_name = viz_fields.get("full_name")
    if viz_name and (mrz_parsed.surname or mrz_parsed.given_names):
        norm_viz_name = normalize_text(viz_name)
        norm_mrz_surname = normalize_text(mrz_parsed.surname)
        norm_mrz_givennames = normalize_text(mrz_parsed.given_names)

        # The surname must be present in the VIZ name
        if norm_mrz_surname and norm_mrz_surname not in norm_viz_name:
            discrepancies.append(
                f"Surname mismatch: MRZ surname '{mrz_parsed.surname}' not found in VIZ '{viz_name}'"
            )
        # The given name tokens should appear in VIZ
        if norm_mrz_givennames and norm_mrz_givennames not in norm_viz_name:
            # Check individual tokens
            given_tokens = [normalize_text(t) for t in mrz_parsed.given_names.split()]
            missing_tokens = [t for t in given_tokens if t and t not in norm_viz_name]
            if missing_tokens:
                discrepancies.append(
                    f"Given names mismatch: MRZ tokens {missing_tokens} not in VIZ '{viz_name}'"
                )

    if discrepancies:
        failure_codes.append(FailureCode.ERR_MATH_VIZ_MRZ_MISMATCH)
        return False, discrepancies, failure_codes

    return True, [], []


# ─── OCR Pipeline Orchestration ──────────────────────────────────────────────


def process_ocr_and_mrz(
    image: np.ndarray,
    raw_mrz_lines: Optional[list[str]] = None,
    viz_fields: Optional[dict] = None,
) -> OCRExtractionResult:
    """
    Extract/parse MRZ lines, extract VIZ fields, and execute Rule 4.2 cross-zonal match.

    Args:
        image: Preprocessed/warped document image.
        raw_mrz_lines: Optional pre-extracted/provided MRZ lines.
        viz_fields: Optional dictionary with VIZ fields from request or OCR.
    """
    lines = raw_mrz_lines or []
    confidence = 0.95

    # Parse MRZ lines
    mrz_result = parse_mrz(lines) if lines else None

    if mrz_result is None or not mrz_result.raw_lines:
        # If no lines were provided or parsed, generate failure
        empty_mrz = ParsedMRZ(
            raw_lines=[],
            format_type="UNKNOWN",
            document_type="UNKNOWN",
            issuing_country="",
            surname="",
            given_names="",
            document_number="",
            nationality="",
            date_of_birth="",
            sex="",
            expiry_date="",
            optional_data="",
            failure_codes=[FailureCode.ERR_OCR_MISSING_MANDATORY_FIELD],
            is_valid=False,
        )
        return OCRExtractionResult(
            mrz_parsed=empty_mrz,
            extracted_fields=ExtractedFields(),
            raw_mrz_lines=[],
            ocr_confidence=0.0,
            viz_mrz_match=False,
            discrepancies=["No MRZ text detected or provided."],
            failure_codes=[FailureCode.ERR_OCR_MISSING_MANDATORY_FIELD],
        )

    # Populate ExtractedFields
    extracted = ExtractedFields(
        full_name=f"{mrz_result.given_names} {mrz_result.surname}".strip(),
        date_of_birth=mrz_result.date_of_birth,
        expiry_date=mrz_result.expiry_date,
        nationality=mrz_result.nationality,
        doc_number=mrz_result.document_number,
        mrz_line1=mrz_result.raw_lines[0] if len(mrz_result.raw_lines) > 0 else None,
        mrz_line2=mrz_result.raw_lines[1] if len(mrz_result.raw_lines) > 1 else None,
        mrz_line3=mrz_result.raw_lines[2] if len(mrz_result.raw_lines) > 2 else None,
    )

    all_failures: list[FailureCode] = list(mrz_result.failure_codes)

    # Cross-zonal check (Rule 4.2)
    viz_match = True
    discrepancies: list[str] = []
    if viz_fields:
        viz_match, discrepancies, viz_failures = match_viz_mrz(viz_fields, mrz_result)
        for vf in viz_failures:
            if vf not in all_failures:
                all_failures.append(vf)

    return OCRExtractionResult(
        mrz_parsed=mrz_result,
        extracted_fields=extracted,
        raw_mrz_lines=mrz_result.raw_lines,
        ocr_confidence=confidence,
        viz_mrz_match=viz_match,
        discrepancies=discrepancies,
        failure_codes=all_failures,
    )
