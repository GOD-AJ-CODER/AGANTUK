"""
api/v1/endpoints/auth.py — Biometric fingerprint authentication endpoint.

Implements:
  POST /api/v1/auth/fingerprint

Rule 1.1 — Biometric Terminal Lock:
  - No processing is permitted without a valid hardware fingerprint auth.
  - A JWT with SESSION_TTL_SECONDS (180 s) expiry is issued on success.
  - Any request carrying an expired JWT triggers AUTH_SESSION_EXPIRED —
    the client must redirect to the fingerprint gate; no soft-dismiss.

Security model:
  The fingerprint payload received here is the raw template bytes from the
  hardware reader, base64-encoded by the frontend. In a full production
  deployment this is matched against enrolled templates stored in the
  officers table (or a dedicated secure enclave). For Phase 1 the matching
  logic is a clearly-marked stub that raises PipelineNotImplementedError —
  it will be replaced in the same phase once the hardware SDK wrapper is
  wired in, per rules.md §1 "No Placeholder Cheating".

  The stub is intentionally NOT a hardcoded True/pass-through. It raises
  a 501 to make it impossible for an unauthenticated path to silently succeed.

Dependencies (Phase 1):
  - PyJWT  for HS256 token signing
  - sqlite3 (via db.py) for officer lookup and last_login_utc update
"""

import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.core.db import get_db
from app.core.exceptions import (
    AuthenticationError,
    DatabaseError,
    PipelineNotImplementedError,
    VerificationError,
)
from app.schemas.auth import (
    AuthenticatedOfficer,
    FingerprintLoginRequest,
    FingerprintLoginResponse,
    OfficerRole,
    SessionStatus,
)
from app.schemas.errors import ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Token helpers ────────────────────────────────────────────────────────────


def _create_access_token(officer_id: str, terminal_id: str) -> tuple[str, datetime]:
    """
    Sign and return a short-lived HS256 JWT for an authenticated officer session.

    The token expiry is set to ``settings.SESSION_TTL_SECONDS`` from now (180 s).
    This satisfies Rule 1.1 — the idle lock is enforced at the token level so
    even if a client forgets to call the lock endpoint the token is refused.

    Returns:
        (encoded_token, expires_at_utc)
    """
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(seconds=settings.SESSION_TTL_SECONDS)

    payload: dict = {
        "sub": officer_id,          # subject — officer UUID
        "terminal": terminal_id,    # terminal making the request
        "iat": now,                  # issued-at
        "exp": expires_at,           # expiry — hard idle lock (Rule 1.1)
        "jti": str(uuid.uuid4()),    # unique token ID (prevents replay)
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, expires_at


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT, raising AuthenticationError on any failure.

    Called by the ``get_current_officer`` dependency on every protected route.

    Raises:
        AuthenticationError(AUTH_SESSION_EXPIRED) if the token has expired.
        AuthenticationError(AUTH_INVALID_TOKEN)   if the token is malformed or
                                                   has an invalid signature.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError(
            error_code=ErrorCode.AUTH_SESSION_EXPIRED,
            message=(
                f"Session timed out after {settings.SESSION_TTL_SECONDS} seconds "
                "of inactivity. Re-authenticate via fingerprint."
            ),
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(
            error_code=ErrorCode.AUTH_INVALID_TOKEN,
            message="Invalid or tampered session token. Re-authenticate via fingerprint.",
            detail=str(exc),
        )


# ─── FastAPI dependency — current authenticated officer ───────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_officer(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> dict:
    """
    FastAPI dependency that validates the bearer token on every protected route.

    Rule 1.1 — No processing without hardware fingerprint auth:
    Raises AuthenticationError (→ HTTP 401) if the token is absent, expired,
    or invalid.

    Returns the decoded JWT payload dict containing:
      - ``sub``      : officer_id (UUID string)
      - ``terminal`` : terminal_id
      - ``exp``      : expiry timestamp
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(
            error_code=ErrorCode.AUTH_NO_FINGERPRINT,
            message=(
                "No authentication token provided. "
                "Authenticate via POST /api/v1/auth/fingerprint."
            ),
        )

    return decode_access_token(credentials.credentials)


# ─── Fingerprint matching stub ────────────────────────────────────────────────


def _match_fingerprint_to_officer(
    fingerprint_payload_b64: str,
    db: sqlite3.Connection,
) -> dict:
    """
    Match the raw fingerprint template against enrolled officer templates.

    ── STUB — Phase 1 ────────────────────────────────────────────────────────
    Hardware biometric matching (enrolling templates, SDK integration) is a
    Phase 1 hardware-side task.  Rather than returning True and pretending the
    match succeeded (which violates rules.md §1 "No Placeholder Cheating"),
    this stub raises PipelineNotImplementedError so that ANY call to the
    fingerprint endpoint returns 501 until the real matcher is wired in.

    TODO (Phase 1 — hardware integration):
      1. Decode fingerprint_payload_b64 from base64 to raw bytes.
      2. Call the hardware SDK's template-match function against enrolled
         officer templates stored in the officers table (or secure enclave).
      3. Return the matched officer row dict on success.
      4. Raise AuthenticationError(AUTH_FINGERPRINT_MISMATCH) on no match.
    ──────────────────────────────────────────────────────────────────────────

    Args:
        fingerprint_payload_b64: Base64-encoded raw fingerprint template bytes.
        db: Active SQLite connection.

    Returns:
        Matched officer row as a dict (keys: officer_id, badge_number,
        full_name, role, is_active).

    Raises:
        PipelineNotImplementedError: Always, until the hardware SDK is wired.
        AuthenticationError(AUTH_FINGERPRINT_MISMATCH): When real matching
            finds no enrolled officer for the presented fingerprint.
        AuthenticationError(AUTH_OFFICER_INACTIVE): When the matched officer
            account is marked is_active = 0.
    """
    raise PipelineNotImplementedError(
        stage_name="fingerprint_hardware_matching",
        phase=1,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/fingerprint",
    response_model=FingerprintLoginResponse,
    summary="Biometric fingerprint login",
    description=(
        "Authenticates an officer using a hardware fingerprint reader. "
        "Returns a short-lived JWT valid for 180 seconds (Rule 1.1). "
        "The client must include this token as `Authorization: Bearer <token>` "
        "on every subsequent API call. An expired token requires re-authentication — "
        "no soft-dismiss."
    ),
    responses={
        200: {"description": "Fingerprint matched. JWT issued."},
        401: {
            "description": (
                "Fingerprint did not match any enrolled officer, or the officer "
                "account is inactive."
            )
        },
        501: {"description": "Fingerprint hardware matching not yet wired (Phase 1 stub)."},
        503: {"description": "Database error during officer lookup or login-time update."},
    },
    tags=["Authentication"],
)
async def fingerprint_login(
    body: FingerprintLoginRequest,
) -> FingerprintLoginResponse:
    """
    POST /api/v1/auth/fingerprint

    Phase 1 flow:
      1. Validate the request body (Pydantic — already done by FastAPI).
      2. Open a DB connection and call the fingerprint matcher.
         (Currently raises 501 — real hardware matching is Phase 1 hardware task.)
      3. On match: update officer.last_login_utc in the DB.
      4. Issue a signed JWT with SESSION_TTL_SECONDS expiry.
      5. Return FingerprintLoginResponse.

    Rule 1.1 compliance:
      - JWT expiry is set to SESSION_TTL_SECONDS (180 s) from now.
      - No downstream route processes a request without this token.
      - Expired tokens are rejected with AUTH_SESSION_EXPIRED at the
        get_current_officer dependency level.
    """
    try:
        with get_db() as db:
            # Step 1: Match fingerprint → officer row
            officer_row = _match_fingerprint_to_officer(
                fingerprint_payload_b64=body.fingerprint_payload,
                db=db,
            )

            # Step 2: Record the login timestamp
            try:
                now_utc = datetime.now(tz=timezone.utc).isoformat()
                db.execute(
                    "UPDATE officers SET last_login_utc = ? WHERE officer_id = ?",
                    (now_utc, officer_row["officer_id"]),
                )
            except sqlite3.Error as exc:
                logger.error(
                    "Failed to update last_login_utc for officer %s: %s",
                    officer_row.get("officer_id"),
                    exc,
                )
                raise DatabaseError(
                    error_code=ErrorCode.DB_WRITE_FAILED,
                    message="Failed to record login timestamp. Please retry.",
                    detail=str(exc),
                )

    except VerificationError:
        # Re-raise domain errors as-is so the global handler processes them.
        raise
    except sqlite3.Error as exc:
        logger.error("Database error during fingerprint login: %s", exc)
        raise DatabaseError(
            error_code=ErrorCode.DB_READ_FAILED,
            message="Database error during officer lookup. Please retry.",
            detail=str(exc),
        )

    # Step 3: Issue JWT
    access_token, expires_at = _create_access_token(
        officer_id=officer_row["officer_id"],
        terminal_id=body.terminal_id,
    )

    logger.info(
        "Officer %s (%s) authenticated on terminal %s",
        officer_row["badge_number"],
        officer_row["officer_id"],
        body.terminal_id,
    )

    return FingerprintLoginResponse(
        access_token=access_token,
        session_expires_at=expires_at,
        idle_lock_seconds=settings.SESSION_TTL_SECONDS,
        officer=AuthenticatedOfficer(
            officer_id=officer_row["officer_id"],
            badge_number=officer_row["badge_number"],
            full_name=officer_row["full_name"],
            role=OfficerRole(officer_row["role"]),
        ),
    )


@router.get(
    "/session/status",
    response_model=SessionStatus,
    summary="Check session liveness",
    description=(
        "Returns the current session state. "
        "The frontend idle-lock countdown polls this endpoint. "
        "If `is_locked` is True the client must redirect to the fingerprint gate — "
        "no soft-dismiss (Rule 1.1)."
    ),
    responses={
        200: {"description": "Session liveness information."},
        401: {"description": "No or invalid token — session is locked."},
    },
    tags=["Authentication"],
)
async def session_status(
    token_payload: Annotated[dict, Depends(get_current_officer)],
) -> SessionStatus:
    """
    GET /api/v1/auth/session/status

    The ``get_current_officer`` dependency handles token validation and raises
    401 if the token is missing or expired.  If execution reaches here the
    token is still valid.

    Returns remaining idle seconds derived from the JWT expiry claim.
    """
    exp_timestamp: int = token_payload["exp"]
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    remaining_seconds = max(0, int((expires_at - now).total_seconds()))

    return SessionStatus(
        is_locked=False,
        idle_seconds_remaining=remaining_seconds,
        officer_id=token_payload["sub"],
    )
