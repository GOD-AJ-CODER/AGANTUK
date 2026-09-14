"""
core/exceptions.py — Custom exception classes for the verification pipeline.

Rules reference: rules.md §1 "Structured Exceptions Only":
  "Wrap pipeline failures in a custom VerificationError JSON response.
   Never leak raw Python tracebacks to the client."

All exceptions raised anywhere in the pipeline inherit from VerificationError.
The global FastAPI exception handler in main.py catches these and serializes
them into VerificationErrorResponse before sending to the client.
"""

import http
from typing import Optional

from app.schemas.errors import ErrorCode


class VerificationError(Exception):
    """
    Base exception for all domain-level errors in the verification pipeline.

    Raising VerificationError (or any subclass) from an endpoint handler or
    pipeline stage guarantees that the global exception handler will:
      1. Catch the exception.
      2. Serialize it into VerificationErrorResponse (never a raw traceback).
      3. Return the appropriate HTTP status code.

    Attributes:
        error_code: Machine-readable code from the ErrorCode enum.
        message:    Human-readable description safe to surface in the UI.
        http_status: HTTP status code to return (default: 500).
        detail:     Optional extra context (field name, offending value, etc.).
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        http_status: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.detail = detail

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"http_status={self.http_status}, "
            f"message={self.message!r})"
        )


# ─── Convenience Subclasses ───────────────────────────────────────────────────
# These let call-sites read like: raise AuthenticationError(...)
# and keep the global handler simple (catch VerificationError, done).


class AuthenticationError(VerificationError):
    """
    Raised when a request cannot be authenticated.

    Default HTTP status: 401 Unauthorized.
    Typical error codes: AUTH_NO_FINGERPRINT, AUTH_SESSION_EXPIRED,
                         AUTH_INVALID_TOKEN, AUTH_OFFICER_INACTIVE,
                         AUTH_FINGERPRINT_MISMATCH.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            http_status=http.HTTPStatus.UNAUTHORIZED,
            detail=detail,
        )


class PayloadError(VerificationError):
    """
    Raised when the request payload is malformed or missing required data.

    Default HTTP status: 422 Unprocessable Entity.
    Typical error codes: PAYLOAD_INVALID, PAYLOAD_IMAGE_MISSING,
                         PAYLOAD_IMAGE_DECODE_FAILED.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            http_status=http.HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class DatabaseError(VerificationError):
    """
    Raised when a required SQLite read or write fails.

    Default HTTP status: 503 Service Unavailable.
    Per Rule 7.1 and Database Resiliency rules, a DB_WRITE_FAILED on the
    audit log must prevent the verdict from being returned to the client.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            http_status=http.HTTPStatus.SERVICE_UNAVAILABLE,
            detail=detail,
        )


class PipelineNotImplementedError(VerificationError):
    """
    Raised when a pipeline stage is referenced but not yet built.

    Satisfies rules.md §1 "No Placeholder Cheating":
      "If a dependency isn't ready, raise a clear NotImplementedError
       with a TODO tied to its phase."

    Default HTTP status: 501 Not Implemented.
    """

    def __init__(self, stage_name: str, phase: int) -> None:
        super().__init__(
            error_code=ErrorCode.NOT_IMPLEMENTED,
            message=(
                f"Pipeline stage '{stage_name}' is not yet implemented. "
                f"It is scheduled for Phase {phase}."
            ),
            http_status=http.HTTPStatus.NOT_IMPLEMENTED,
            detail=f"TODO: Phase {phase} — implement {stage_name}.",
        )


class ImageQualityError(VerificationError):
    """
    Raised when an ingested image fails Stage 1 quality checks (Rules 1.2 - 1.4).

    Default HTTP status: 400 Bad Request.
    Typical error codes: TOO_BLURRY, DOCUMENT_CONTOUR_NOT_FOUND,
                         DOCUMENT_ANGLE_EXCEEDED, GLARE_DETECTED.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            http_status=http.HTTPStatus.BAD_REQUEST,
            detail=detail,
        )
