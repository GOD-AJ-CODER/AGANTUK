"""
config.py — Single source of truth for all thresholds, environment variables,
and tunable constants.

Rules reference: rules.md §1 "Architecture Integrity" — thresholds are declared
here only, never duplicated inline in pipeline code.

Usage:
    from app.config import settings

    timeout = settings.SESSION_TTL_SECONDS   # 180
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide configuration.  Values are loaded from environment
    variables first, falling back to the defaults defined here.

    For local development, create an `apps/backend/.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "Border Verification Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ── Security & JWT ────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = os.environ.get(
        "JWT_SECRET_KEY",
        "CHANGE_ME_IN_PRODUCTION_THIS_IS_NOT_SECURE",
    )
    """
    HS256 signing secret for session JWTs.
    MUST be overridden via environment variable in any non-development deployment.
    Minimum 32 characters recommended.
    """
    JWT_ALGORITHM: str = "HS256"

    # ── Session / Idle Lock (Rule 1.1) ─────────────────────────────────────
    SESSION_TTL_SECONDS: int = 180
    """
    Rule 1.1 — Biometric Terminal Lock:
    After SESSION_TTL_SECONDS of inactivity the session is force-locked.
    The JWT expiry is set to this value; any request after expiry is rejected
    with AUTH_SESSION_EXPIRED and must re-authenticate via fingerprint.
    180 s is the non-negotiable value set in project_requirements.md F1.
    """

    # ── Database ──────────────────────────────────────────────────────────────
    DB_PATH: str = os.path.join(
        os.path.dirname(__file__), "../../../database/local.db"
    )
    """Path to the embedded SQLite database file."""

    DB_BUSY_TIMEOUT_MS: int = 5000
    """
    SQLite busy-timeout: wait up to 5 s for a write lock before raising.
    Satisfies rules.md §1 "Database Resiliency — retry-on-lock logic".
    """

    # ── Image Quality Thresholds (Stage 1 / Phase 2) ─────────────────────────
    LAPLACIAN_VARIANCE_THRESHOLD: float = 100.0
    """
    Rule 1.2 — Motion Blur Check:
    Images with Laplacian variance below this value are rejected as too blurry.
    Populated here so Phase 2 can import the value without touching auth code.
    """

    PERSPECTIVE_MAX_ANGLE_DEG: float = 45.0
    """
    Rule 1.3 — Perspective Warp:
    If the detected document bounding angle exceeds this, the image is rejected.
    """

    GLARE_HSV_V_THRESHOLD: int = 240
    """
    Rule 1.4 — Specular Glare:
    HSV Value channel threshold for specular highlight detection.
    Pixels with V > this value are flagged as glare.
    """

    # ── AI / Inference Thresholds (Stage 3 / Phase 3) ────────────────────────
    YOLO_CONFIDENCE_FLOOR: float = 0.60
    """
    Rule 3.1: YOLO confidence below this → ERR_AI_UNKNOWN_DOC_FORMAT.
    """
    YOLO_MANUAL_REVIEW_THRESHOLD: float = 0.85
    """
    Rule 3.1: YOLO confidence in [YOLO_CONFIDENCE_FLOOR, this) → MANUAL_REVIEW.
    """
    OCR_CONFIDENCE_FLOOR: float = 0.90
    """
    Rule 3.2: Average OCR field confidence below this → WARN_OCR_LOW_CONFIDENCE.
    """

    # ── Forensics Thresholds (Stage 2 / Phase 4) ──────────────────────────────
    ELA_VARIANCE_RATIO_THRESHOLD: float = 0.15
    """
    Rule 2.2 — ELA: photo-zone vs. substrate variance ratio above this value
    flags a potential face splice.  Calibration target — adjust with test corpus.
    """
    ASPECT_RATIO_TOLERANCE_PCT: float = 3.0
    """
    Rule 2.4 — ISO/IEC 7810 Aspect Ratio:
    Deviation beyond ±this percentage from the standard ratio flags
    ERR_FORENSIC_INVALID_DIMENSIONS.
    """

    # ── Anti-Fraud (Stage 6 / Phase 4) ───────────────────────────────────────
    PASSBACK_WINDOW_SECONDS: int = 900
    """
    Rule 6.1 — Pass-Back Prevention:
    Scanning the same document number within this window (15 min = 900 s)
    triggers ERR_SECURITY_PASSBACK_DETECTED.
    """

    # ── Latency Budget ────────────────────────────────────────────────────────
    PIPELINE_LATENCY_BUDGET_MS: int = 1500
    """
    rules.md §1 — Execution Latency Constraint:
    Stages A–D must complete within 1,500 ms on target edge hardware.
    """

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ALLOW_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    """Origins allowed for CORS — local Next.js dev server only by default."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached singleton Settings instance.
    Use this function (not direct instantiation) to avoid re-parsing env on
    every import.
    """
    return Settings()


# Module-level singleton for simple `from app.config import settings` usage.
settings: Settings = get_settings()
