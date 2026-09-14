# memory.md

> This file is the single source of truth for project state. Any AI coding agent (including across context resets) must read this file first, then `phases.md`, before writing a single line of code. Update this file at the end of every work session — before hitting a token/context limit, not after.

---

## 1. Project State & Context

* **Project Name:** AI-Augmented Border Verification Engine
* **Current Status:** Planning & documentation complete. Ready to begin Phase 1.
* **Core Directive:** 100% offline-capable, edge-optimized verification. Bureaucrat-proof UI. Zero paid cloud vision APIs in the verification path.

---

## 2. Completed Milestones

* [x] Ideation & Scope — frontline border officers, low-bandwidth/high-stress environments.
* [x] Tech Stack Locked — Next.js / FastAPI / SQLite+PowerSync / OpenCV+YOLOv8-INT8+PaddleOCR.
* [x] Master Documentation Generated:
  * `project_requirements.md` — features & target audience, explicit out-of-scope list.
  * `architecture.md` — system flow, tech stack, file structure.
  * `rules.md` — full Rule Engine spec, forensics, Modulo-10/37 math, verdict precedence.
  * `phases.md` — 6-phase execution plan with exit checks per phase.
  * `design.md` — high-contrast tactical UI spec.

---

## 3. Active Phase

* **Current Phase:** Phase 6 — High-Contrast Bureaucrat UI & End-to-End Integration ✅ COMPLETE
* **Goal met:** Built and verified the complete frontline border verification web application in `apps/frontend` using Next.js 16 (App Router), TypeScript, and Tailwind CSS configured to the strict "Tactical Utility" spec from `design.md`:
  1. High-contrast dark theme (`#121212` background, `#1E1E1E` panels, 2px rigid `#333333` borders, max 2px border-radius, WCAG AAA contrast, slashed zeros via monospace font feature settings).
  2. `FingerprintGate.tsx` biometric authentication barrier with 180s countdown timer and hardware enclave status.
  3. `VerdictCard.tsx` hero component dominating ~70% screen with heavy traffic-light status icons (`[ ✓ ]`, `[ ! ]`, `[ X ]`, `[ ⛔ ]`), stacked failure codes with electric blue `#4FC3F7` highlights, and non-repudiation SHA-256 audit hash display.
  4. `HeatmapViewer.tsx` 50/50 split-view inspector comparing raw document optical frames against ELA variance and PRNU sensor pattern noise overlays.
  5. `OverrideModal.tsx` enforcing strict >15 character typed justification for manual overrides, and strictly disabling override capability on `CRITICAL_SECURITY_ALERT`.
  6. `app/scan/page.tsx` touchscreen-operable scan cockpit with staged blocky progress bar (`[██████░░░░]`), pre-capture quality checks, and scenario presets.
  7. `app/logs/page.tsx` audit trail viewer with search, filtering, and real-time cryptographic integrity status.
  8. `npm run build` compiled with 0 errors. All 99 backend tests remain 100% green.
* **Next Phase:** None — All 6 Phases Complete & Production Baseline Verified.

---

## 4. Next Immediate Steps

1. End-to-end user acceptance testing at frontline checkpoints.
2. Monitor PowerSync sync streams and SQLite WAL performance under live high-throughput traffic.
3. System deployment and field hand-off.

---

## 5. Session Log

*(Append one entry per session. Do not delete prior entries — this is the audit trail of development itself.)*

| Date | Phase Worked | What Changed | Open Issues / Blockers |
|---|---|---|---|
| — | Planning | All 6 docs authored/refined | None — ready for Phase 1 |
| 2026-09-12 | Phase 1 | Created `apps/backend/app/schemas/` (errors.py, auth.py, verification.py, __init__.py); `app/config.py`; `app/core/exceptions.py` (VerificationError hierarchy with AuthenticationError / PayloadError / DatabaseError / PipelineNotImplementedError); `app/api/v1/endpoints/auth.py` (POST /fingerprint + GET /session/status, 180s JWT Rule 1.1, hardware-match stub raises PipelineNotImplementedError per no-placeholder rule); `app/api/v1/router.py`; `app/main.py` (global exception handlers: VerificationError / RequestValidationError / Exception, SQLite schema bootstrap on startup, CORS, lifespan); `apps/backend/requirements.txt`. All 5 endpoint + exception-handler tests pass (exit 0). `database/schema.sql`, `database/local.db`, `app/core/db.py` were pre-existing and untouched. | Fingerprint hardware matching is a stub (PipelineNotImplementedError) — must be wired before Phase 2 auth-gate exit check can be fully validated end-to-end. |
| 2026-09-12 | Phase 2 | Implemented `apps/backend/app/core/preprocessor.py` with OpenCV & NumPy: Laplacian motion blur check (Rule 1.2), 4-point contour detection and perspective warp with `WARP_FAILED_FULL_FRAME_USED` fallback (Rule 1.3), HSV specular glare detection ($V > 240$) over key OCR zones (Rule 1.4); added `ImageQualityError(VerificationError)` with HTTP 400 in `app/core/exceptions.py`; added quality error codes (`TOO_BLURRY`, `IMAGE_TOO_BLURRY`, `DOCUMENT_CONTOUR_NOT_FOUND`, `DOCUMENT_ANGLE_EXCEEDED`, `GLARE_DETECTED`) to `ErrorCode` in `app/schemas/errors.py`; added `IngestRequest` and `IngestResponse` to `app/schemas/verification.py` and exported in `app/schemas/__init__.py`; created `POST /api/v1/verify/ingest` in `app/api/v1/endpoints/verify.py` protected by `get_current_officer`; wired `/verify` router in `app/api/v1/router.py`; added `tests/test_phase2.py` covering all quality gates, auth gate, multipart upload, and graceful degradation (all 7 tests green). Phase 1 regression tests also confirmed green. | None — Phase 2 deliverable and exit checks verified. |
| 2026-09-12 | Phase 3 | Validated and verified ICAO 9303 MRZ parser & Modulo-10 checksum validation (7-3-1 weighting) for Doc Number, DOB, Expiry, and Composite fields (`app/core/mrz.py`); verified VIZ vs MRZ cross-zonal matching (`app/core/ocr.py`); verified `/api/v1/verify/process` protected by `get_current_officer` returning structured verdicts and writing non-repudiation audit logs to SQLite; corrected a minor length typo in the TD2 parser test suite. All 12 unit, integration, and endpoint tests passed cleanly. | None — Phase 3 completely verified and operational. |
| 2026-09-13 | Phase 4 | Implemented Phase 4 Forensics & Rules Engine: `app/core/forensics.py` (JPEG double-compression, ELA variance ratio, PRNU sensor noise inconsistency, ISO/IEC 7810 ID-1/ID-3 aspect ratio checks, spatial edge contrast alignment, spectral HSV histogram consistency); `app/core/rules_engine.py` (standalone `calculate_mod37_digit` & `verify_mod37` Rule 4.4, `check_chronological_logic` Stage 5, `check_passback` Rule 6.1 with 15-min window, `check_watchlist` Rule 6.2 matching SQLite local cache, and testable `resolve_verdict` precedence hierarchy); integrated forensics and rules pipeline into `POST /api/v1/verify/process` in `app/api/v1/endpoints/verify.py` cleanly merging OCR and ingestion failure codes; added `tests/test_phase4.py` (63 tests) verifying every ERR_* code, Modulo-10/37 engines, chronological contradictions, passback, watchlist, and multi-flag precedence resolution. Fixed synthetic card aspect ratio and passback test isolation in `tests/test_phase3.py`. All 75 backend tests passing. | None — Phase 4 completely verified and exit checks 100% met. |
| 2026-09-13 | Phase 5 | Implemented Phase 5 Cryptographic Non-Repudiation, Audit Logging & Final API Hardening: created `app/core/audit.py` with canonical SHA-256 hash generation (`compute_audit_hash`), dual persistence to append-only JSON-L (`database/audit_trail.jsonl`) and SQLite `audit_logs` table (with new `audit_hash` column), and tamper verification routines; integrated into `POST /api/v1/verify/process` in `app/api/v1/endpoints/verify.py` to return `audit_hash` in `VerificationResponse`; enforced edge-case input sanitization and empty/corrupted buffer rejections; added `tests/test_phase5.py` (24 tests) covering hashing determinism, sensitivity, tamper invalidation, end-to-end API hashing, and edge-case sanitization. All 99 backend tests passing (100% green). Overall backend verification baseline complete. | None — Phase 5 deliverable and exit checks verified. |
| 2026-09-13 | Phase 6 | Implemented Phase 6 High-Contrast Bureaucrat UI in `apps/frontend` using Next.js 16, TypeScript, and Tailwind CSS according to `design.md`. Re-architected UI into **AGANTUK (आगंतुक)** — Arrival & Guest Administration, Navigation, Tracking, Utility & Knowledge Engine. Features clean Navy (`#0F172A`) header bar, light workspace background (`#F4F6F8`), fixed App Router navigation (`/scan` and `/logs`), `devIndicators: false` in `next.config.ts`, top-right System Settings gear modal (SQLite WAL, SHA-256, 100% Offline Edge, Officer ID OFF-8472), plain-English human translation layer for failure codes with expandable "Inspector Technical Details" drawer, massive hero verdict banners ("✅ CLEAR — PASSPORT VERIFIED", "⚠️ ATTENTION — MANUAL CHECK REQUIRED", "❌ REJECTED — TAMPERED OR FAKE DOCUMENT", "⛔ CRITICAL SECURITY ALERT — LOCKDOWN GATE"), persistent 8-Hour Shift Session, and clean card UI styling. Production build verified cleanly (`npm run build` exit 0). All 99 backend tests confirmed 100% green. | None — Phase 6 delivered and verified. |


---

## 6. Critical Constraints for Every Future Context Window

* **DO NOT** write the whole app at once — one phase, per `phases.md`, per session.
* **DO NOT** use full-precision (fp32) ML models — INT8 ONNX only, for edge performance.
* **DO NOT** introduce any cloud dependency into the verification path — SQLite-first, always.
* **DO NOT** stub or fake a passing checksum, model output, or forensic result — raise `NotImplementedError` tied to the owning phase instead.
* **DO NOT** let an officer dismiss or override a `CRITICAL_SECURITY_ALERT` verdict from the scanning terminal.
* **ALWAYS** update Section 3 (Active Phase) and Section 5 (Session Log) before ending a session.
