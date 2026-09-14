"""
api/v1/router.py — Aggregates all v1 endpoint routers under /api/v1.

New endpoint modules added in future phases must be imported and included here.
Do NOT create parallel router files at the same level — this is the single
v1 routing entry-point (architecture.md §4).
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth

api_v1_router = APIRouter(prefix="/api/v1")

# ── Phase 1 ───────────────────────────────────────────────────────────────────
api_v1_router.include_router(auth.router, prefix="/auth")

# ── Phase 2: Verification & Ingestion ─────────────────────────────────────────
from app.api.v1.endpoints import verify
api_v1_router.include_router(verify.router, prefix="/verify")

# ── Phase 5 (not yet built — do NOT uncomment until Phase 5) ─────────────────
# from app.api.v1.endpoints import sync
# api_v1_router.include_router(sync.router, prefix="/sync")
