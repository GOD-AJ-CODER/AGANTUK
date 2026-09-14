# project_requirements.md

## 1. Executive Summary & Vision

An offline-first, AI-augmented, tamper-evident document verification system built for frontline border security and immigration control. The system replaces subjective visual inspection with automated computer vision, signal-level image forensics, deterministic mathematical checksums, and biometric officer accountability — intercepting fraudulent travel documents at the point of inspection, with or without a network connection.

**Non-negotiables:**
- Verification must complete with zero cloud dependency.
- Every verdict must be traceable to a single authenticated officer.
- The system must degrade gracefully, never silently.

---

## 2. Target Audience

* **Primary Users:** Frontline immigration officers, border control agents, and checkpoint personnel working in high-pressure, physical booths, land crossings, and airport gates. Assume gloved hands, cheap touchscreens, screen glare, and 12-hour fatigue.
* **Secondary Users:** Shift supervisors and station commanders reviewing flagged cases and overrides.
* **Tertiary Users:** National document fraud audit teams requiring immutable, exportable forensic logs.

---

## 3. Core Problem Statement

* **High Cognitive Load & Fatigue:** Officers processing hundreds of documents per shift miss microscopic tampering, spliced photos, and altered text.
* **Unstable Network Environments:** Checkpoints often run on unstable, low-bandwidth, or fully severed connections where cloud-only tools fail outright.
* **Lack of Biometric Accountability:** Shared terminals and unauthenticated scans create legal ambiguity when fraud slips through.
* **Storage & Privacy Overhead:** Unregulated high-resolution document storage violates privacy protocol and inflates infrastructure cost over time.

---

## 4. Key Functional Requirements

### F1 — Biometric Officer Access & Authentication Gate
- Hardware fingerprint reader required before any session or scan.
- Auto session lock after 180s idle; requires re-authentication (no soft-dismiss).
- Every document scan and verdict is immutably linked to the authenticating officer's biometric ID — never a shared or role-based account.

### F2 — Mobile & Desktop Image Ingestion & Quality Pre-Processing
- Accepts high-resolution camera and mobile phone photo input.
- Laplacian-variance motion-blur check; instant rejection below threshold.
- Automated 4-point contour detection + perspective warp to flatten angled captures.
- HSV-space specular glare detection over critical fields (Name, DOB, MRZ), blocking scans where glare occludes them.

### F3 — Signal-Level Forensic Engine
- **JPEG Quantization Matrix Analysis** — detects double-compression signatures from re-saving in editing software.
- **Error Level Analysis (ELA)** — compares compression variance between the facial photo region and the document substrate to expose splicing/face substitution.
- **Photo-Response Non-Uniformity (PRNU)** — sensor noise fingerprinting to detect localized digital patching.
- **Aspect Ratio Verification** — validates physical dimensions against ISO/IEC 7810 ID-1 and ID-3.

### F4 — AI Document Classification & Text Extraction
- **YOLOv8 (INT8, edge-optimized)** — classifies document type: Passport, Visa, National ID, Driver's License.
- **PaddleOCR (local, ONNX runtime)** — extracts Name, DOB, Expiry Date, Issue Date, Nationality, Document Number, and MRZ.

### F5 — Mathematical & Cryptographic Validation Engine
- **ICAO-9303 weighted Modulo-10 checksums** on Document Number, DOB, Expiry Date, and the Composite MRZ field, using repeating weights `[7, 3, 1]`.
- **Modulo-37 cross-reference validation** on alphanumeric ID card fields.
- **VIZ vs. MRZ cross-matching** — field-by-field string comparison between the Visual Inspection Zone and the parsed MRZ.
- **MRZ format enforcement** — character whitelist `^[A-Z0-9<]+$`; strict line lengths (44 chars × 2 lines for passports, 30 chars × 3 lines for ID/Visa).

### F6 — Chronological & Logical Constraint Validation
- Live expiry check against local system clock.
- Sequence checks: `Issue_Date < Current_Date`, `Issue_Date < Expiry_Date`, `Birth_Date < Issue_Date`.
- Human age bounds: `0 ≤ Age ≤ 120`.

### F7 — Offline-First Synchronization & Data Lifecycle
- **Local-first storage** — SQLite handles 100% of verification with zero cloud dependency at scan time.
- **PowerSync** — asynchronous background replication to Supabase once connectivity returns.
- **Local watchlist matching** — real-time check against a locally cached blacklist/stolen-document database.
- **Pass-back fraud prevention** — flags duplicate scans of the same document number within a 15-minute window.
- **Rolling data retention** — daily cron purges non-flagged scan images/logs older than 30 days; flagged incidents retained permanently.

### F8 — Bureaucrat-Proof UI & Audit Logging
- Traffic-light verdicts: `PASS`, `FLAGGED`, `MANUAL_REVIEW`.
- Biometrically stamped audit log for every operation, no exceptions.
- Mandatory typed justification (>15 characters) for any officer override of a flagged document.

---

## 5. Explicit Out-of-Scope (v1)

To keep phases bounded, the following are **not** part of this build and should be flagged if an AI coding agent starts drifting toward them:
- Any cloud-based vision/OCR API (Google Vision, AWS Rekognition, Azure Read, etc.) in the core verification path.
- Multi-tenant / multi-country configuration management.
- Officer performance analytics or gamification.
- Mobile native apps (iOS/Android) — the frontend is a responsive Next.js web app only.
