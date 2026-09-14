"""
Pydantic schemas for the Border Verification Engine API.

Exports:
  - auth: Officer session, fingerprint auth request/response
  - verification: Document scan request/response, verdict schemas
  - errors: Structured VerificationError response schema
"""

from .auth import (
    FingerprintLoginRequest,
    FingerprintLoginResponse,
    SessionStatus,
    OfficerRole,
)
from .verification import (
    VerificationRequest,
    VerificationResponse,
    VerdictStatus,
    FailureCode,
    ConfidenceScores,
    IngestRequest,
    IngestResponse,
    ProcessVerificationRequest,
)
from .errors import (
    VerificationErrorResponse,
    ErrorCode,
)

__all__ = [
    # Auth
    "FingerprintLoginRequest",
    "FingerprintLoginResponse",
    "SessionStatus",
    "OfficerRole",
    # Verification
    "VerificationRequest",
    "ProcessVerificationRequest",
    "VerificationResponse",
    "VerdictStatus",
    "FailureCode",
    "ConfidenceScores",
    "IngestRequest",
    "IngestResponse",
    # Errors
    "VerificationErrorResponse",
    "ErrorCode",
]
