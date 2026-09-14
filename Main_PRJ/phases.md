# phases.md

## Phase Overview & Execution Strategy

Development is split into 6 strict, sequential phases to prevent context overload and runaway code generation. Each phase must be fully implemented and verified against `rules.md` before the next begins. An AI coding agent should treat this file as a gate — read `memory.md` first to confirm current phase, do only that phase's tasks, then update `memory.md` before stopping.

---

## Phase 1: Local Backend Foundation & Database Schema
**Goal:** FastAPI core, local SQLite database, Pydantic schemas, biometric auth gate.

1. Initialize FastAPI project structure (`apps/backend/app/`).
2. Write `database/schema.sql` — creates `officers`, `audit_logs`, and `watchlist` tables.
3. Define Pydantic schemas for verification requests, officer sessions, and structured verdict responses.
4. Build `POST /api/v1/auth/fingerprint` — biometric login state, token generation, 180s idle lock (Rule 1.1).
5. Build the global FastAPI exception handler returning structured `VerificationError` responses (rules.md §1).

**Deliverable:** Functional FastAPI backend with working SQLite migrations and biometric auth routes.
**Exit check:** Can an unauthenticated request reach `/verify`? It must not.

---

## Phase 2: Ingestion & Image Pre-Processing Pipeline
**Goal:** OpenCV pre-processing engine validating image quality before AI inference.

1. Implement `app/core/preprocessor.py` (OpenCV + NumPy).
2. Laplacian motion-blur check, σ² < 100.0 threshold (Rule 1.2).
3. 4-point contour detection + perspective warp, with the `WARP_FAILED_FULL_FRAME_USED` fallback (Rule 1.3).
4. HSV specular glare masking over OCR key zones (Rule 1.4).
5. `POST /api/v1/verify/ingest` test endpoint — returns warped crop + pass/fail quality flags.

**Deliverable:** Pre-processing module that cleans, flattens, and validates uploaded document images.
**Exit check:** A deliberately blurry and a deliberately angled test image both get rejected with the correct HTTP 400 messages.

---

## Phase 3: AI Inference & OCR Parsing Engine
**Goal:** Local edge-optimized classification and text/MRZ extraction.

1. `app/core/classifier.py` — ONNX Runtime, INT8 YOLOv8 document classification (Rule 3.1).
2. `app/core/ocr.py` — PaddleOCR extraction of VIZ and MRZ bounding boxes/text (Rule 3.2).
3. Regex clean-up utility mapping raw OCR text into structured key-value fields.
4. Wire Phase 2 output directly into classifier + OCR pipeline (no re-upload).

**Deliverable:** End-to-end local inference pipeline turning a raw image into structured document data with confidence scores.
**Exit check:** A known-good test passport image returns all Stage 3 fields non-null with confidence ≥0.90.

---

## Phase 4: Forensics Engine & Rule Validation Engine
**Goal:** Core security logic — forensics, checksums, chronological rules, verdict assembly.

1. `app/core/forensics.py`: JPEG quantization (2.1), ELA (2.2), PRNU (2.3), aspect ratio (2.4).
2. `app/core/rules_engine.py`:
   - MRZ whitelist/length checks (4.1), VIZ↔MRZ cross-check (4.2).
   - Modulo-10 engine `[7,3,1]` for Doc Number, DOB, Expiry, Composite (4.3).
   - Modulo-37 cross-reference engine (4.4).
   - Chronological/date logic (Stage 5).
   - SQLite pass-back check + watchlist match (Stage 6).
   - **Verdict precedence resolution** per rules.md §3 — implement as its own testable function, not inline branching.

**Deliverable:** Complete Python verification engine returning `PASS` / `FLAGGED` / `MANUAL_REVIEW` / `CRITICAL_SECURITY_ALERT` with the full stacked list of failure codes.
**Exit check:** Unit tests covering at least one case per failure code in rules.md, plus one deliberate multi-flag conflict case proving precedence resolves correctly.

---

## Phase 5: Offline Sync, Audit Logging & CCTV Purge
**Goal:** Offline-first persistence, PowerSync replication, data lifecycle.

1. SQLite audit logging wrapper (Rule 7.1) — write-before-respond, transactional.
2. `lib/powersync.ts` — PowerSync Client SDK streaming local SQLite → Supabase when online; queue-depth banner (Rule 7.2).
3. `database/cron_purge.py` — 30-day rolling purge, `PASS`-only, permanent retention otherwise (Rule 7.3).
4. Override logging mechanism — >15 character justification, blocked entirely for `CRITICAL_SECURITY_ALERT` (Rule 7.4).

**Deliverable:** Production-grade offline persistence with background cloud sync and rolling cleanup.
**Exit check:** Pull the network mid-scan — verdict still returns, audit log still writes, PowerSync queues silently for later.

---

## Phase 6: High-Contrast Bureaucrat UI & End-to-End Integration
**Goal:** Next.js frontend for harsh field conditions, per `design.md`.

1. `components/FingerprintGate.tsx` — biometric auth screen.
2. `app/scan/page.tsx` — camera feed/upload, real-time blur/glare warnings, staged progress bar (no spinners — see design.md §5).
3. `components/VerdictCard.tsx` — traffic-light verdict, high-contrast, monospace data fields with slashed zeros.
4. `components/HeatmapViewer.tsx` — split-view forensic heatmap for ELA/PRNU anomalies.
5. `components/OverrideModal.tsx` — mandatory justification textbox; disabled entirely when verdict is `CRITICAL_SECURITY_ALERT`.
6. `app/logs/page.tsx` — local/synced audit history viewer.

**Deliverable:** Fully integrated, high-contrast web application ready for end-to-end field testing.
**Exit check:** A full scan-to-verdict cycle is operable one-handed on a touchscreen, glove on, without a mouse.
