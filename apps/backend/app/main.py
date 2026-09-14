"""
main.py — FastAPI application factory and global exception handler.

Responsibilities:
  1. Create and configure the FastAPI application instance.
  2. Register the global VerificationError exception handler (rules.md §1
     "Structured Exceptions Only" — never leak raw Python tracebacks).
  3. Register CORS middleware.
  4. Include the v1 API router.
  5. Bootstrap the SQLite schema on startup.

Usage:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sqlite3
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.config import settings
from app.core.db import get_db_connection
from app.core.exceptions import VerificationError
from app.schemas.errors import ErrorCode, VerificationErrorResponse

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Startup: SQLite schema bootstrap ─────────────────────────────────────────

def _bootstrap_schema() -> None:
    """
    Apply database/schema.sql to the local SQLite file on startup.

    Uses CREATE TABLE IF NOT EXISTS so running this on an existing DB is safe.
    Runs synchronously at startup — before the first request is accepted.

    Raises:
        RuntimeError: If the schema file cannot be found or the SQL fails.
    """
    schema_path = Path(__file__).parent.parent.parent.parent / "database" / "schema.sql"
    if not schema_path.exists():
        logger.warning(
            "schema.sql not found at %s — skipping schema bootstrap.", schema_path
        )
        return

    sql = schema_path.read_text(encoding="utf-8")
    try:
        conn = get_db_connection()
        conn.executescript(sql)
        # Migrate existing audit_logs to add audit_hash if missing
        try:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN audit_hash TEXT;")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Already exists
        conn.close()
        logger.info("SQLite schema bootstrapped from %s", schema_path)
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to bootstrap SQLite schema: {exc}") from exc


# ─── Application lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Async context manager executed at application startup and shutdown.

    Startup:
      - Bootstrap SQLite schema (idempotent — IF NOT EXISTS).
      - Log the session idle-lock timeout so the ops team can confirm config.

    Shutdown:
      - Placeholder for any cleanup (connection pool teardown, etc.).
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    logger.info(
        "Session idle-lock timeout: %d s (Rule 1.1)", settings.SESSION_TTL_SECONDS
    )
    _bootstrap_schema()
    logger.info("Application ready.")

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down %s.", settings.APP_NAME)


# ─── Application factory ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Offline-first AI-augmented document verification engine for frontline "
        "border security and immigration control. "
        "All verification logic runs 100% locally — zero cloud dependencies."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# ─── Global Exception Handlers ────────────────────────────────────────────────
#
# rules.md §1 "Structured Exceptions Only":
#   "Wrap pipeline failures in a custom VerificationError JSON response.
#    Never leak raw Python tracebacks to the client."
#
# Handler priority (FastAPI evaluates in registration order for overlapping types):
#   1. VerificationError (and all subclasses) → domain-aware structured response.
#   2. RequestValidationError (Pydantic) → PAYLOAD_INVALID structured response.
#   3. Exception (catch-all) → INTERNAL_ERROR, traceback logged server-side only.


@app.exception_handler(VerificationError)
async def verification_error_handler(
    request: Request, exc: VerificationError
) -> JSONResponse:
    """
    Handles all VerificationError subclasses raised anywhere in the pipeline.

    Serializes the exception into VerificationErrorResponse and returns it with
    the HTTP status code set on the exception.  The raw traceback is logged
    server-side only — never included in the response body.
    """
    logger.warning(
        "VerificationError on %s %s: [%s] %s",
        request.method,
        request.url.path,
        exc.error_code,
        exc.message,
        exc_info=exc,
    )

    response_body = VerificationErrorResponse(
        error_code=exc.error_code,
        message=exc.message,
        detail=exc.detail,
    )

    return JSONResponse(
        status_code=exc.http_status,
        content=response_body.model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handles Pydantic RequestValidationError (422) raised by FastAPI when a
    request body fails schema validation.

    Converts the native FastAPI validation error into a VerificationErrorResponse
    so the client always receives the same error envelope regardless of failure type.
    """
    # Build a compact detail string from the validation error list.
    errors = exc.errors()
    detail_parts = [
        f"{' → '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in errors
    ]
    detail_str = "; ".join(detail_parts)

    logger.warning(
        "Payload validation error on %s %s: %s",
        request.method,
        request.url.path,
        detail_str,
    )

    response_body = VerificationErrorResponse(
        error_code=ErrorCode.PAYLOAD_INVALID,
        message="Request payload validation failed. Check the 'detail' field for specifics.",
        detail=detail_str,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response_body.model_dump(mode="json"),
    )



@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all handler for any unhandled exception that escapes the pipeline.

    !! SECURITY !! The traceback is logged server-side at ERROR level but
    is NEVER included in the response body — clients only receive the opaque
    INTERNAL_ERROR code and a generic message.
    """
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )

    response_body = VerificationErrorResponse(
        error_code=ErrorCode.INTERNAL_ERROR,
        message=(
            "An unexpected internal error occurred. "
            "The incident has been logged. Please retry or contact support."
        ),
        detail=None,  # Never expose traceback to the client.
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response_body.model_dump(mode="json"),
    )


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(api_v1_router)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get(
    "/health",
    summary="Health check",
    description="Returns 200 OK if the backend process is alive. Does not check DB connectivity.",
    tags=["System"],
    include_in_schema=True,
)
async def health_check() -> dict:
    return {
        "ok": True,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
