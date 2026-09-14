"""
api/v1/endpoints/verify.py — Document verification & ingestion endpoints.

Endpoints:
  POST /api/v1/verify/ingest (Phase 2):
    - Protected by get_current_officer dependency (Rule 1.1).
    - Ingests uploaded image, runs Stage 1 OpenCV preprocessor:
        * Rule 1.2: Laplacian motion-blur check (< 100.0) -> HTTP 400
        * Rule 1.3: 4-point contour detection & perspective warp
                    (not found / angle > 45° -> HTTP 400, warp failure -> fallback)
        * Rule 1.4: HSV specular glare check (V > 240) over OCR key zones -> HTTP 400
    - Returns warped document crop (base64) + pass/fail quality flags.
"""

import logging
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    UploadFile,
    status,
)

import uuid
from app.api.v1.endpoints.auth import get_current_officer
from app.core.db import write_audit_log
from app.core.exceptions import PayloadError
from app.core.forensics import run_forensics
from app.core.ocr import process_ocr_and_mrz
from app.core.preprocessor import preprocess_document
from app.core.rules_engine import evaluate_rules, resolve_verdict
from app.schemas.errors import ErrorCode
from app.schemas.verification import (
    ConfidenceScores,
    DocumentType,
    ExtractedFields,
    FailureCode,
    IngestRequest,
    IngestResponse,
    ProcessVerificationRequest,
    VerdictStatus,
    VerificationRequest,
    VerificationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest and pre-process document image",
    description=(
        "Protected by biometric session auth (Rule 1.1). "
        "Runs Stage 1 OpenCV quality checks (blur, perspective warp, specular glare) "
        "and returns the flattened document crop with quality metrics."
    ),
    responses={
        200: {"description": "Document passed quality gates and was warped successfully."},
        400: {"description": "Image failed quality gate (blurry, steep angle, or glare)."},
        401: {"description": "Missing, expired, or invalid biometric session token."},
        422: {"description": "Malformed image payload or decode failure."},
    },
)
async def ingest_document(
    request: Request,
    officer: Annotated[dict, Depends(get_current_officer)],
    file: Optional[UploadFile] = File(None),
    image_b64: Optional[str] = Form(None),
    enforce_quality: bool = Query(
        True,
        description="If True (default), quality gate failures raise HTTP 400.",
    ),
) -> IngestResponse:
    """
    Ingest a document image via multipart/form-data upload or JSON payload.

    Extracts raw image bytes or base64 string, runs the OpenCV Stage 1 preprocessor,
    and returns the warped document crop and quality metrics.
    """
    image_payload: str | bytes | None = None
    content_type = request.headers.get("content-type", "").lower()

    # 1. Handle multipart file upload or form field
    if file is not None:
        image_payload = await file.read()
    elif image_b64 is not None:
        image_payload = image_b64
    elif "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                image_payload = body.get("image_b64")
                if "enforce_quality" in body:
                    enforce_quality = bool(body["enforce_quality"])
        except Exception as exc:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_INVALID,
                message="Malformed JSON request body.",
                detail=str(exc),
            ) from exc
    elif content_type in ("image/jpeg", "image/png", "application/octet-stream"):
        image_payload = await request.body()

    if not image_payload:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
            message="No image data provided. Send a file upload or JSON with image_b64.",
        )

    logger.info(
        "Officer %s ingesting document image at terminal %s",
        officer.get("sub"),
        officer.get("terminal"),
    )

    result = preprocess_document(
        image_input=image_payload,
        enforce_quality=enforce_quality,
    )

    return IngestResponse(
        ok=True,
        warped_image_b64=result.warped_image_b64,
        laplacian_variance=round(result.laplacian_variance, 2),
        bounding_angle=round(result.bounding_angle, 2),
        glare_detected=result.glare_detected,
        warp_fallback_used=result.warp_fallback_used,
        quality_flags=result.quality_flags,
        crop_width=result.crop_width,
        crop_height=result.crop_height,
    )


# ─── Phase 3 & 4: Full Verification Process Endpoint ─────────────────────────


@router.post(
    "/process",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Process document verification pipeline",
    description=(
        "Protected by get_current_officer dependency (Rule 1.1). "
        "Runs full verification pipeline: preprocessor → forensics → "
        "MRZ extraction → Rule Validation Engine (Modulo-10, Chronological, Watchlist). "
        "Writes immutable non-repudiation log to audit_logs table (Rule 7.1)."
    ),
)
@router.post(
    "",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def process_verification(
    request: Request,
    officer: Annotated[dict, Depends(get_current_officer)],
    file: Optional[UploadFile] = File(None),
    image_b64: Optional[str] = Form(None),
    declared_doc_type: Optional[str] = Form(None),
    terminal_id: Optional[str] = Form(None),
) -> VerificationResponse:
    """
    Execute end-to-end document verification pipeline and write audit log.
    """
    import uuid
    from app.core.audit import write_audit_record
    from app.core.ocr import process_ocr_and_mrz
    from app.schemas.verification import (
        ConfidenceScores,
        DocumentType,
        ExtractedFields,
        FailureCode,
        VerdictStatus,
        VerificationResponse,
    )

    image_payload: str | bytes | None = None
    mrz_lines: list[str] | None = None
    viz_fields: dict | None = None
    content_type = request.headers.get("content-type", "").lower()

    raw_bytes: bytes | None = None

    if file is not None:
        image_payload = await file.read()
        if not image_payload or len(image_payload) == 0:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                message="Uploaded file is empty (0 bytes).",
            )
        raw_bytes = image_payload if isinstance(image_payload, bytes) else None
    elif image_b64 is not None:
        cleaned = image_b64.strip()
        if not cleaned:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                message="Image base64 string is empty.",
            )
        image_payload = cleaned
    elif "application/json" in content_type:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise PayloadError(
                    error_code=ErrorCode.PAYLOAD_INVALID,
                    message="JSON request body must be an object.",
                )
            image_payload = body.get("image_b64")
            if image_payload is not None and isinstance(image_payload, str):
                image_payload = image_payload.strip()
            if not image_payload:
                raise PayloadError(
                    error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                    message="No image data provided for verification.",
                )
            declared_doc_type = body.get("declared_doc_type", declared_doc_type)
            terminal_id = body.get("terminal_id", terminal_id)
            mrz_lines = body.get("mrz_lines")
            viz_fields = body.get("viz_fields")
        except PayloadError:
            raise
        except Exception as exc:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_INVALID,
                message="Malformed JSON request body.",
                detail=str(exc),
            ) from exc
    elif content_type in ("image/jpeg", "image/png", "application/octet-stream"):
        image_payload = await request.body()
        if not image_payload or len(image_payload) == 0:
            raise PayloadError(
                error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
                message="Raw image byte stream is empty.",
            )
        raw_bytes = image_payload if isinstance(image_payload, bytes) else None

    if not image_payload:
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_IMAGE_MISSING,
            message="No image data provided for verification.",
        )

    # Sanitize inputs
    if mrz_lines is not None and not isinstance(mrz_lines, list):
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_INVALID,
            message="mrz_lines must be a list of strings.",
        )
    if viz_fields is not None and not isinstance(viz_fields, dict):
        raise PayloadError(
            error_code=ErrorCode.PAYLOAD_INVALID,
            message="viz_fields must be a JSON object (key-value mapping).",
        )

    officer_id = officer.get("sub", "UNKNOWN-OFFICER")
    term = terminal_id or officer.get("terminal", "TERMINAL-01")

    # 1. Preprocessing Stage (Rule 1.2, 1.3, 1.4)
    prep_result = preprocess_document(image_payload, enforce_quality=True)

    # 2. Forensics Stage (Rule 2.x)
    forensics_result = run_forensics(prep_result.warped_image, raw_bytes)

    # 3. OCR & MRZ Parsing Stage (Rules 4.1, 4.2, 4.3)
    ocr_result = process_ocr_and_mrz(
        image=prep_result.warped_image,
        raw_mrz_lines=mrz_lines,
        viz_fields=viz_fields,
    )

    # 4. Rule Validation Engine (Stages 4, 5, 6)
    # Collect ingestion flags
    ingestion_failures = []
    for qf in prep_result.quality_flags:
        try:
            ingestion_failures.append(FailureCode(qf))
        except ValueError:
            pass

    all_failures = evaluate_rules(
        mrz=ocr_result.mrz_parsed,
        forensics_failures=forensics_result.failure_codes + ingestion_failures,
        viz_fields=viz_fields,
        ocr_failure_codes=ocr_result.failure_codes,
    )

    # 5. Resolve Verdict Precedence (rules.md §3)
    verdict = resolve_verdict(all_failures)

    # 6. Confidence Scores
    confidence = ConfidenceScores(
        laplacian_variance=round(prep_result.laplacian_variance, 2),
        ocr_average=ocr_result.ocr_confidence,
        ela_variance_ratio=forensics_result.ela_variance_ratio,
    )

    # Document type
    detected_type: DocumentType | None = None
    if ocr_result.mrz_parsed.document_type == "PASSPORT":
        detected_type = DocumentType.PASSPORT
    elif ocr_result.mrz_parsed.document_type in ("NATIONAL_ID", "ID"):
        detected_type = DocumentType.NATIONAL_ID
    elif ocr_result.mrz_parsed.document_type in ("VISA", "V"):
        detected_type = DocumentType.VISA
    else:
        detected_type = DocumentType.UNKNOWN

    log_id = str(uuid.uuid4())
    doc_number = ocr_result.mrz_parsed.document_number or (viz_fields.get("doc_number") if viz_fields else None)

    # 7. Commit Immutable Non-Repudiation Audit Log with SHA-256 (Rule 7.1)
    raw_mrz_data = ocr_result.mrz_parsed.raw_lines if (ocr_result.mrz_parsed and ocr_result.mrz_parsed.raw_lines) else (mrz_lines or [])
    audit_rec = write_audit_record(
        log_id=log_id,
        officer_id=officer_id,
        verdict=verdict.value,
        failure_codes=[f.value for f in all_failures],
        doc_type=detected_type.value if detected_type else None,
        doc_number=doc_number,
        raw_mrz=raw_mrz_data,
        forensics_metrics=confidence.model_dump(),
    )

    logger.info(
        "Verification complete: log_id=%s, verdict=%s, failures=%s, audit_hash=%s",
        log_id,
        verdict.value,
        [f.value for f in all_failures],
        audit_rec.audit_hash,
    )

    return VerificationResponse(
        ok=True,
        log_id=log_id,
        verdict=verdict,
        failure_codes=all_failures,
        doc_type_detected=detected_type,
        extracted_fields=ocr_result.extracted_fields,
        confidence_scores=confidence,
        officer_id=officer_id,
        audit_hash=audit_rec.audit_hash,
    )
