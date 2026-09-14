"""
schemas/auth.py — Officer authentication and session schemas.

Covers:
  - FingerprintLoginRequest  : body for POST /api/v1/auth/fingerprint
  - FingerprintLoginResponse : successful auth response with JWT + session info
  - SessionStatus            : idle-lock status check response
  - OfficerRole              : enum mirroring the DB CHECK constraint
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OfficerRole(str, Enum):
    """
    Mirrors the CHECK constraint in schema.sql:
      role IN ('OFFICER', 'SUPERVISOR', 'AUDITOR')
    """

    OFFICER = "OFFICER"
    SUPERVISOR = "SUPERVISOR"
    AUDITOR = "AUDITOR"


# ─── Request Schemas ──────────────────────────────────────────────────────────


class FingerprintLoginRequest(BaseModel):
    """
    POST /api/v1/auth/fingerprint — request body.

    In production the fingerprint payload arrives as a raw byte string from the
    hardware reader SDK; the frontend encodes it as base64 before sending JSON.

    Rule 1.1: No processing occurs without a valid fingerprint match — this is
    the gate that all downstream routes depend on.
    """

    fingerprint_payload: str = Field(
        ...,
        min_length=1,
        description=(
            "Base64-encoded raw fingerprint template bytes as captured by the "
            "hardware biometric reader."
        ),
        examples=["AQIDBA=="],
    )
    terminal_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier of the physical checkpoint terminal making the request.",
        examples=["TERMINAL-GATE-07"],
    )

    @field_validator("fingerprint_payload")
    @classmethod
    def payload_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("fingerprint_payload must not be blank.")
        return v

    @field_validator("terminal_id")
    @classmethod
    def terminal_id_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("terminal_id must not be blank.")
        return v.strip().upper()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "fingerprint_payload": "AQIDBA==",
                    "terminal_id": "TERMINAL-GATE-07",
                }
            ]
        }
    }


# ─── Response Schemas ─────────────────────────────────────────────────────────


class AuthenticatedOfficer(BaseModel):
    """Subset of officer data embedded in auth responses. Never includes secrets."""

    officer_id: str = Field(..., description="UUID primary key of the officer.")
    badge_number: str = Field(..., description="Physical badge / personnel number.")
    full_name: str = Field(..., description="Officer's display name.")
    role: OfficerRole = Field(..., description="Access-control role.")


class FingerprintLoginResponse(BaseModel):
    """
    POST /api/v1/auth/fingerprint — success response.

    Returns a short-lived JWT that the client must include as
    ``Authorization: Bearer <access_token>`` on every subsequent request.

    The ``session_expires_at`` field echoes the absolute UTC timestamp after
    which the token is invalid (access_token TTL == SESSION_TTL_SECONDS from
    config.py).

    The ``idle_lock_seconds`` field reminds the client of the Rule 1.1 idle
    timeout so the UI can start its own countdown timer.
    """

    ok: bool = Field(default=True)
    access_token: str = Field(
        ...,
        description="Signed JWT bearer token. Must be sent on every protected request.",
    )
    token_type: str = Field(default="bearer")
    session_expires_at: datetime = Field(
        ...,
        description="Absolute UTC datetime at which this token expires.",
    )
    idle_lock_seconds: int = Field(
        ...,
        description=(
            "Number of seconds of inactivity that will trigger an automatic "
            "session lock (Rule 1.1 — always 180 s in production)."
        ),
    )
    officer: AuthenticatedOfficer = Field(
        ...,
        description="The officer whose fingerprint was matched.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ok": True,
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "session_expires_at": "2026-09-12T16:21:05Z",
                    "idle_lock_seconds": 180,
                    "officer": {
                        "officer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "badge_number": "BGD-00142",
                        "full_name": "Officer Jane Doe",
                        "role": "OFFICER",
                    },
                }
            ]
        }
    }


class SessionStatus(BaseModel):
    """
    Response for any endpoint that checks the liveness of the current session.

    Used by the frontend idle-lock countdown: if ``is_locked`` is True the
    client must redirect to the fingerprint gate immediately — no soft-dismiss.
    """

    ok: bool = Field(default=True)
    is_locked: bool = Field(
        ...,
        description=(
            "True if the session has been force-locked due to idle timeout "
            "(Rule 1.1). The client must redirect to the biometric gate."
        ),
    )
    idle_seconds_remaining: Optional[int] = Field(
        default=None,
        description=(
            "Seconds of activity remaining before the system auto-locks. "
            "None when is_locked is True."
        ),
    )
    officer_id: Optional[str] = Field(
        default=None,
        description="The authenticated officer ID, or None when locked.",
    )
