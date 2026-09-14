"""
schemas/errors.py — Structured error response schemas.

All API errors must surface as a VerificationErrorResponse, never as a raw
Python traceback. This satisfies rules.md §1 "Structured Exceptions Only".
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """
    Machine-readable error codes emitted by the VerificationError handler.
    These sit above the stage-level failure codes (ERR_FORENSIC_*, ERR_MATH_*, etc.)
    and represent system-level / auth-level problems detected before or outside
    the verification pipeline.
    """

    # ── Authentication & Session ──────────────────────────────────────────────
    AUTH_NO_FINGERPRINT = "AUTH_NO_FINGERPRINT"
    """Request arrived without a valid biometric session token (Rule 1.1)."""

    AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    """Session idle time exceeded 180 s — forced logout, re-auth required (Rule 1.1)."""

    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    """JWT is malformed, tampered with, or signed by the wrong key."""

    AUTH_OFFICER_INACTIVE = "AUTH_OFFICER_INACTIVE"
    """The officer account referenced by the token is marked inactive in the DB."""

    AUTH_FINGERPRINT_MISMATCH = "AUTH_FINGERPRINT_MISMATCH"
    """Hardware reader returned a fingerprint that does not match any enrolled officer."""

    # ── Payload / Input ───────────────────────────────────────────────────────
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    """Request body failed Pydantic validation — missing required fields or bad types."""

    PAYLOAD_IMAGE_MISSING = "PAYLOAD_IMAGE_MISSING"
    """No image data was provided in the request payload."""

    PAYLOAD_IMAGE_DECODE_FAILED = "PAYLOAD_IMAGE_DECODE_FAILED"
    """The provided image bytes could not be decoded into a valid image buffer."""

    # ── System / Infrastructure ───────────────────────────────────────────────
    DB_WRITE_FAILED = "DB_WRITE_FAILED"
    """
    SQLite audit-log write failed.  Per Rule 7.1 and Database Resiliency rules,
    no verdict is returned to the client until the audit write succeeds.
    """

    DB_READ_FAILED = "DB_READ_FAILED"
    """A required database read (watchlist, pass-back check) failed."""

    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Unexpected server-side error not covered by a more specific code."""

    # ── Pipeline / Stage ─────────────────────────────────────────────────────
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    """
    A pipeline stage is defined but not yet built.  Raised instead of faking
    a result (rules.md §1 "No Placeholder Cheating").
    """

    # ── Ingestion & Image Quality (Stage 1 / Phase 2) ────────────────────────
    TOO_BLURRY = "TOO_BLURRY"
    """Rule 1.2: Laplacian variance < 100.0 — image too blurry."""

    IMAGE_TOO_BLURRY = "IMAGE_TOO_BLURRY"
    """Rule 1.2 alias: Laplacian variance < 100.0."""

    DOCUMENT_CONTOUR_NOT_FOUND = "DOCUMENT_CONTOUR_NOT_FOUND"
    """Rule 1.3: Document 4-point contour could not be detected."""

    DOCUMENT_ANGLE_EXCEEDED = "DOCUMENT_ANGLE_EXCEEDED"
    """Rule 1.3: Document bounding angle exceeds 45.0 degrees."""

    GLARE_DETECTED = "GLARE_DETECTED"
    """Rule 1.4: Specular glare (HSV V > 240) detected over key text zones."""


class VerificationErrorResponse(BaseModel):
    """
    Canonical JSON body returned for every non-2xx response.

    The FastAPI global exception handler wraps every VerificationError (and
    unhandled Exception) in this schema before sending it to the client.
    """

    ok: bool = Field(
        default=False,
        description="Always False for error responses — mirrors the 'ok' field on success.",
    )
    error_code: ErrorCode = Field(
        ...,
        description="Machine-readable error code for programmatic handling by the client.",
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the error, safe to surface in the UI.",
    )
    detail: Optional[str] = Field(
        default=None,
        description=(
            "Optional extra context (e.g., which field failed validation). "
            "Never contains a raw Python traceback."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ok": False,
                    "error_code": "AUTH_SESSION_EXPIRED",
                    "message": "Session timed out after 180 seconds of inactivity. Re-authenticate.",
                    "detail": None,
                }
            ]
        }
    }
