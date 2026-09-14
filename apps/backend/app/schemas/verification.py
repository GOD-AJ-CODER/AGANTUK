"""
schemas/verification.py — Verification pipeline request/response/verdict schemas.

These schemas define the complete data contract for a document scan:
  - VerificationRequest    : image + officer context sent to POST /api/v1/verify
  - ConfidenceScores       : per-stage model/algorithm confidence
  - VerificationResponse   : final structured verdict returned to the client
  - VerdictStatus          : enum matching DB CHECK constraint
  - FailureCode            : all stage-tagged failure codes from rules.md
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class VerdictStatus(str, Enum):
    """
    Canonical verdict values — mirrors audit_logs.verdict_status CHECK constraint
    and the precedence ordering in rules.md §3.

    Precedence (highest → lowest):
      CRITICAL_SECURITY_ALERT > FLAGGED > MANUAL_REVIEW > PASS
    """

    PASS = "PASS"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FLAGGED = "FLAGGED"
    CRITICAL_SECURITY_ALERT = "CRITICAL_SECURITY_ALERT"


class DocumentType(str, Enum):
    """Supported document types classified by the YOLOv8 model (Phase 3)."""

    PASSPORT = "PASSPORT"
    VISA = "VISA"
    NATIONAL_ID = "NATIONAL_ID"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    UNKNOWN = "UNKNOWN"


class FailureCode(str, Enum):
    """
    Complete catalogue of stage-level failure codes from rules.md.

    Naming convention: ERR_<STAGE>_<SPECIFIC_FAULT>
      FORENSIC  → Stage 2 (signal-level forensics)
      AI        → Stage 3 (classification / OCR)
      OCR       → Stage 3 (extraction)
      MATH      → Stage 4 (checksums / MRZ validation)
      LOGIC     → Stage 5 (chronological / logical)
      SECURITY  → Stage 6 (watchlist / pass-back)

    WARNING codes are advisory and never alter verdict precedence on their own.
    """

    # ── Stage 2 — Forensics ───────────────────────────────────────────────────
    ERR_FORENSIC_DOUBLE_COMPRESSION = "ERR_FORENSIC_DOUBLE_COMPRESSION"
    """Rule 2.1: JPEG quantization table inconsistency detected."""

    ERR_FORENSIC_PHOTO_SPLICED = "ERR_FORENSIC_PHOTO_SPLICED"
    """Rule 2.2: ELA variance ratio exceeds threshold — photo region splice suspected."""

    ERR_FORENSIC_DIGITAL_PATCHING = "ERR_FORENSIC_DIGITAL_PATCHING"
    """Rule 2.3: PRNU noise distribution inconsistency — localized digital patch detected."""

    ERR_FORENSIC_INVALID_DIMENSIONS = "ERR_FORENSIC_INVALID_DIMENSIONS"
    """Rule 2.4: Physical aspect ratio deviates >±3 % from ISO/IEC 7810 ID-1 or ID-3."""

    # ── Stage 3 — AI Classification & OCR ────────────────────────────────────
    ERR_AI_UNKNOWN_DOC_FORMAT = "ERR_AI_UNKNOWN_DOC_FORMAT"
    """Rule 3.1: YOLOv8 confidence < 0.60 — document type unrecognisable."""

    ERR_AI_DOC_TYPE_MISMATCH = "ERR_AI_DOC_TYPE_MISMATCH"
    """Rule 3.1: Declared document type does not match YOLOv8 classification."""

    ERR_OCR_MISSING_MANDATORY_FIELD = "ERR_OCR_MISSING_MANDATORY_FIELD"
    """Rule 3.2: One or more mandatory OCR fields (Name/DOB/DocNumber/Expiry/MRZ) is NULL."""

    WARN_OCR_LOW_CONFIDENCE = "WARN_OCR_LOW_CONFIDENCE"
    """Rule 3.2: Average OCR field confidence < 0.90 — advisory, triggers MANUAL_REVIEW."""

    # ── Stage 4 — Mathematical / Cryptographic ────────────────────────────────
    ERR_MATH_MALFORMED_MRZ_STRUCTURE = "ERR_MATH_MALFORMED_MRZ_STRUCTURE"
    """Rule 4.1: MRZ line count or character length does not match document type spec."""

    ERR_MATH_INVALID_MRZ_CHARACTERS = "ERR_MATH_INVALID_MRZ_CHARACTERS"
    """Rule 4.1: MRZ contains characters outside ^[A-Z0-9<]+$."""

    ERR_MATH_VIZ_MRZ_MISMATCH = "ERR_MATH_VIZ_MRZ_MISMATCH"
    """Rule 4.2 CRITICAL: Visual Inspection Zone fields diverge from MRZ-parsed values."""

    ERR_MATH_MOD10_DOC_NUM_FAILED = "ERR_MATH_MOD10_DOC_NUM_FAILED"
    """Rule 4.3 CRITICAL: ICAO Modulo-10 check on Document Number failed."""

    ERR_MATH_MOD10_DOB_FAILED = "ERR_MATH_MOD10_DOB_FAILED"
    """Rule 4.3 CRITICAL: ICAO Modulo-10 check on Date of Birth failed."""

    ERR_MATH_MOD10_EXPIRY_FAILED = "ERR_MATH_MOD10_EXPIRY_FAILED"
    """Rule 4.3 CRITICAL: ICAO Modulo-10 check on Expiry Date failed."""

    ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED = "ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED"
    """Rule 4.3 CRITICAL: ICAO Composite MRZ master checksum failed."""

    ERR_MATH_MOD37_FAILED = "ERR_MATH_MOD37_FAILED"
    """Rule 4.4: Modulo-37 cross-reference check on alphanumeric ID field failed."""

    # ── Stage 5 — Chronological / Logical ────────────────────────────────────
    ERR_LOGIC_DOCUMENT_EXPIRED = "ERR_LOGIC_DOCUMENT_EXPIRED"
    """Stage 5: Expiry date is earlier than the current UTC date."""

    ERR_LOGIC_FUTURE_ISSUE_DATE = "ERR_LOGIC_FUTURE_ISSUE_DATE"
    """Stage 5: Issue date is later than today — temporally impossible."""

    ERR_LOGIC_TIMELINE_CONTRADICTION = "ERR_LOGIC_TIMELINE_CONTRADICTION"
    """Stage 5: Issue date >= Expiry date — document timeline is self-contradictory."""

    ERR_LOGIC_INVALID_AGE = "ERR_LOGIC_INVALID_AGE"
    """Stage 5: Derived age from DOB falls outside the valid human range 0–120 years."""

    ERR_LOGIC_ISSUED_BEFORE_BIRTH = "ERR_LOGIC_ISSUED_BEFORE_BIRTH"
    """Stage 5: Issue date precedes the holder's date of birth."""

    # ── Stage 6 — Security / Anti-Fraud ──────────────────────────────────────
    ERR_SECURITY_PASSBACK_DETECTED = "ERR_SECURITY_PASSBACK_DETECTED"
    """Rule 6.1 CRITICAL: Same document number scanned within the last 15 minutes."""

    ERR_SECURITY_WATCHLIST_HIT = "ERR_SECURITY_WATCHLIST_HIT"
    """Rule 6.2 CRITICAL: Document number or Name+DOB exact-matches the local watchlist."""

    # ── Pre-pipeline / Ingestion ─────────────────────────────────────────────
    WARP_FAILED_FULL_FRAME_USED = "WARP_FAILED_FULL_FRAME_USED"
    """
    Rule 1.3 Graceful Degradation: Document boundary was found but perspective
    warp subsequently failed — full frame used instead of a corrected crop.
    Appended to the audit payload; scan is NOT rejected.
    """


# ─── Nested Models ────────────────────────────────────────────────────────────


class ConfidenceScores(BaseModel):
    """
    Per-stage algorithm confidence values collected during a verification run.

    All fields are Optional — a field is None when its owning stage has not yet
    run (e.g., Phase 2 and 3 modules are not built yet; they will populate these
    fields in their respective phases).
    """

    yolo_classification: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="YOLOv8 document-type classification confidence (Rule 3.1). Phase 3.",
    )
    ocr_average: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Average PaddleOCR field extraction confidence (Rule 3.2). Phase 3.",
    )
    ela_variance_ratio: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="ELA photo-zone vs. substrate variance ratio (Rule 2.2). Phase 4.",
    )
    laplacian_variance: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Laplacian variance for blur detection (Rule 1.2). Phase 2.",
    )


class ExtractedFields(BaseModel):
    """
    Structured document fields extracted by the OCR engine (Phase 3).

    All fields are Optional at Phase 1; they will be populated once
    PaddleOCR is wired in (Phase 3).
    """

    full_name: Optional[str] = Field(default=None, description="Holder's full name as read from VIZ.")
    date_of_birth: Optional[str] = Field(default=None, description="DOB in YYMMDD or ISO format.")
    expiry_date: Optional[str] = Field(default=None, description="Document expiry in YYMMDD or ISO format.")
    issue_date: Optional[str] = Field(default=None, description="Document issue date.")
    nationality: Optional[str] = Field(default=None, description="3-letter ISO country code.")
    doc_number: Optional[str] = Field(default=None, description="Document number as printed.")
    mrz_line1: Optional[str] = Field(default=None, description="First MRZ line (raw string).")
    mrz_line2: Optional[str] = Field(default=None, description="Second MRZ line (raw string).")
    mrz_line3: Optional[str] = Field(default=None, description="Third MRZ line — ID/Visa only.")


# ─── Request Schema ───────────────────────────────────────────────────────────


class VerificationRequest(BaseModel):
    """
    POST /api/v1/verify — request body.

    The image is submitted as a base64-encoded string.  This avoids multipart
    complexity in the initial phase; Phase 2 may switch to streaming upload if
    the latency budget demands it.

    ``declared_doc_type`` is the officer's manual selection in the UI before
    scanning.  The YOLOv8 classifier will cross-check this (Rule 3.1).
    """

    image_b64: str = Field(
        ...,
        min_length=4,
        description=(
            "Base64-encoded image bytes of the document to verify. "
            "JPEG or PNG. Max recommended raw size: 8 MB."
        ),
    )
    declared_doc_type: DocumentType = Field(
        ...,
        description=(
            "Document type selected by the officer before scanning. "
            "YOLOv8 will cross-check this value (Rule 3.1)."
        ),
    )
    terminal_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Terminal making the request — echoed into the audit log.",
    )
    mrz_lines: Optional[list[str]] = Field(
        default=None,
        description="Optional pre-extracted MRZ lines for validation.",
    )
    viz_fields: Optional[dict[str, Optional[str]]] = Field(
        default=None,
        description="Optional Visual Inspection Zone fields (full_name, date_of_birth, doc_number, expiry_date).",
    )

    @field_validator("image_b64")
    @classmethod
    def image_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("image_b64 must not be blank.")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "image_b64": "/9j/4AAQSkZJRgAB...",
                    "declared_doc_type": "PASSPORT",
                    "terminal_id": "TERMINAL-GATE-07",
                }
            ]
        }
    }


# ─── Response Schema ──────────────────────────────────────────────────────────


class VerificationResponse(BaseModel):
    """
    POST /api/v1/verify — success response.

    Returned only after the audit log write has succeeded (Rule 7.1).
    The ``failure_codes`` list is always populated with the complete stacked
    list of triggered codes regardless of verdict — never just the top one
    (rules.md §3 "All triggered failure codes are collected and reported together").
    """

    ok: bool = Field(default=True)
    log_id: str = Field(
        ...,
        description="UUID of the audit_logs row written for this scan.",
    )
    verdict: VerdictStatus = Field(
        ...,
        description="Final verdict after precedence resolution (rules.md §3).",
    )
    failure_codes: list[FailureCode] = Field(
        default_factory=list,
        description=(
            "All failure codes triggered across every stage. "
            "Empty list when verdict is PASS."
        ),
    )
    doc_type_detected: Optional[DocumentType] = Field(
        default=None,
        description="Document type as classified by YOLOv8 (Phase 3). None until Phase 3.",
    )
    extracted_fields: Optional[ExtractedFields] = Field(
        default=None,
        description="Structured OCR output (Phase 3). None until Phase 3.",
    )
    confidence_scores: ConfidenceScores = Field(
        default_factory=ConfidenceScores,
        description="Per-stage confidence/metric values collected during the scan.",
    )
    officer_id: str = Field(
        ...,
        description="Biometric officer ID whose token authenticated this request.",
    )
    audit_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 cryptographic hash of the audit record for non-repudiation.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ok": True,
                    "log_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    "verdict": "PASS",
                    "failure_codes": [],
                    "doc_type_detected": "PASSPORT",
                    "extracted_fields": None,
                    "confidence_scores": {
                        "yolo_classification": 0.94,
                        "ocr_average": 0.97,
                        "ela_variance_ratio": None,
                        "laplacian_variance": None,
                    },
                    "officer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                }
            ]
        }
    }


# ─── Phase 2 Ingestion Schemas ───────────────────────────────────────────────


class IngestRequest(BaseModel):
    """
    POST /api/v1/verify/ingest — optional JSON request body when not using multipart.
    """

    image_b64: str = Field(
        ...,
        min_length=4,
        description="Base64-encoded image bytes of the document to ingest.",
    )
    enforce_quality: bool = Field(
        default=True,
        description="If True (default), quality gate failures raise HTTP 400. If False, returns flags.",
    )

    @field_validator("image_b64")
    @classmethod
    def image_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("image_b64 must not be blank.")
        return v


class IngestResponse(BaseModel):
    """
    POST /api/v1/verify/ingest — success response.
    Returns the warped/flattened document crop + pass/fail quality metrics and flags.
    """

    ok: bool = Field(
        default=True,
        description="Whether the document passed quality gates or was successfully processed.",
    )
    warped_image_b64: str = Field(
        ...,
        description="Base64-encoded JPEG of the warped, flattened document crop.",
    )
    laplacian_variance: float = Field(
        ...,
        description="Computed Laplacian variance for motion blur check (Rule 1.2).",
    )
    bounding_angle: float = Field(
        ...,
        description="Computed document bounding angle in degrees (Rule 1.3).",
    )
    glare_detected: bool = Field(
        ...,
        description="Whether specular glare was detected over key text zones (Rule 1.4).",
    )
    warp_fallback_used: bool = Field(
        default=False,
        description="True if post-detection warp failed and full frame fallback was used (Rule 1.3).",
    )
    quality_flags: list[str] = Field(
        default_factory=list,
        description="Quality flags or warnings (e.g. WARP_FAILED_FULL_FRAME_USED).",
    )
    crop_width: int = Field(
        ...,
        description="Width of the warped crop in pixels.",
    )
    crop_height: int = Field(
        ...,
        description="Height of the warped crop in pixels.",
    )


# Alias for Phase 3 process endpoint
ProcessVerificationRequest = VerificationRequest
