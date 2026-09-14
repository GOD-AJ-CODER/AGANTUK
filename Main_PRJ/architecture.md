# architecture.md

## 1. System Architecture Overview & Tech Stack

A decoupled, offline-first architecture: a local Next.js client, a Python FastAPI backend running embedded AI/forensic inference, an embedded SQLite database for zero-latency local operation, and PowerSync bridging to Supabase Cloud only when connectivity allows.

**Design rule:** the edge node (client + backend + SQLite) must be able to complete a full verification with the network cable pulled out. Cloud is an eventual mirror, never a dependency.

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend UI | Next.js (React, App Router), TypeScript (strict), Tailwind CSS, Lucide Icons |
| Local Backend API | Python 3.11+, FastAPI, Uvicorn (ASGI, local edge node) |
| Forensics & Pre-Processing | OpenCV (`opencv-python-headless`), NumPy, PIL, SciPy |
| Document Classifier | YOLOv8 Nano (`ultralytics`), exported to INT8 ONNX |
| OCR Engine | PaddleOCR, mobile ONNX runtime execution |
| Local DB & Offline Layer | SQLite (embedded file DB), PowerSync Client SDK |
| Cloud DB & Sync | Supabase (PostgreSQL + RLS + Storage), PowerSync Cloud Service |

---

## 2. System Architecture Diagram & Data Flow

```
+-----------------------------------------------------------------------------------+
|                                 EDGE CHECKPOINT NODE                              |
|                                                                                   |
|  +--------------------+       REST/HTTP       +--------------------------------+  |
|  | Next.js Client App | <-------------------> |    FastAPI Local Backend       |  |
|  |  (App Router UI)   |  (Image Payload/JSON) |  - Fingerprint Auth Validation |  |
|  +---------+----------+                       |  - OpenCV Pre-Processing       |  |
|            |                                  |  - INT8 YOLOv8 Classification  |  |
|            | Read/Write                       |  - PaddleOCR Extraction        |  |
|            v                                  |  - Modulo-10/37 Math Engine    |  |
|  +--------------------+                       +---------------+----------------+  |
|  | Embedded SQLite DB |                                       | Write Audit Logs  |
|  |  (Local State &    | <-------------------------------------+                   |
|  |   Watchlist Cache) |                                                           |
|  +---------+----------+                                                           |
+------------|----------------------------------------------------------------------+
             |
             | Background Sync (PowerSync Protocol) — only when online
             v
+-----------------------------------------------------------------------------------+
|                                 SUPABASE CLOUD                                    |
|                                                                                   |
|  +------------------+     +-----------------------+     +----------------------+  |
|  | PostgreSQL DB    |     | PowerSync Cloud Node  |     | Supabase Storage     |  |
|  | (Central Audits) | <-> | (Sync Orchestrator)   |     | (Flagged Scans Only) |  |
|  +------------------+     +-----------------------+     +----------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Detailed Pipeline Flow (Stages A–E map 1:1 to rules.md Stages 1–7)

### Stage A: Ingestion & Quality Gate
1. Next.js sends a base64/binary image payload to `POST /api/v1/verify`.
2. OpenCV converts to grayscale, computes Laplacian variance.
   - `variance < 100` → `HTTP 400 TOO_BLURRY`.
3. Contour detection locates the 4 document corners; perspective transform flattens the image.
   - No contour found or angle > 45° → `HTTP 400`, see Rule 1.3 fallback in rules.md.
4. HSV conversion flags specular glare over critical OCR zones.

### Stage B: Forensic Signal Analysis
1. JPEG quantization matrix extraction → double-compression signature check.
2. ELA generation: recompress at 95% quality, `cv2.absdiff`, compare photo-zone vs. substrate variance.
3. PRNU noise extraction → localized patching detection.

### Stage C: Inference & Extraction
1. YOLOv8 INT8 → document type + confidence score.
2. PaddleOCR → VIZ and MRZ field bounding boxes + text + confidence.
3. Regex clean-up normalizes whitespace, strips invalid OCR characters.

### Stage D: Rule Validation
1. MRZ structural + character-set validation.
2. Modulo-10 `[7,3,1]` checksums (Doc Number, DOB, Expiry, Composite) + Modulo-37 cross-reference.
3. Logical/date checks (expiry, sequence, age bounds).
4. Local SQLite watchlist + pass-back cross-check.

### Stage E: Persistence & Sync
1. SQLite write: scan record, verdict, failure codes, officer ID (single transaction).
2. PowerSync queues the record for cloud replication (non-blocking).
3. Daily cron (`cron_purge.py`) evaluates retention rules and purges eligible records.

**Latency budget:** Stages A–D combined must stay under 1,500ms on target edge hardware (see rules.md §1).

---

## 4. Repository File & Folder Structure

```
border-verify/
├── apps/
│   ├── web/                         # Next.js Frontend Application
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── scan/page.tsx
│   │   │   │   ├── logs/page.tsx
│   │   │   │   ├── layout.tsx
│   │   │   │   └── page.tsx
│   │   │   ├── components/
│   │   │   │   ├── CameraFeed.tsx
│   │   │   │   ├── VerdictCard.tsx
│   │   │   │   ├── OverrideModal.tsx
│   │   │   │   ├── FingerprintGate.tsx
│   │   │   │   └── HeatmapViewer.tsx
│   │   │   ├── lib/
│   │   │   │   ├── powersync.ts
│   │   │   │   └── sqlite.ts
│   │   │   └── types/
│   │   ├── public/
│   │   ├── package.json
│   │   └── tailwind.config.js
│   │
│   └── backend/                     # Python FastAPI Backend
│       ├── app/
│       │   ├── main.py
│       │   ├── config.py            # thresholds, env vars — single source of truth
│       │   ├── api/v1/
│       │   │   ├── endpoints/
│       │   │   │   ├── auth.py
│       │   │   │   ├── verify.py
│       │   │   │   └── sync.py
│       │   │   └── router.py
│       │   ├── core/
│       │   │   ├── preprocessor.py
│       │   │   ├── forensics.py
│       │   │   ├── classifier.py
│       │   │   ├── ocr.py
│       │   │   ├── rules_engine.py
│       │   │   └── db.py
│       │   ├── models/              # pre-trained ONNX models
│       │   │   ├── yolov8n_int8.onnx
│       │   │   └── ocr_mobile.onnx
│       │   └── schemas/             # Pydantic request/response/verdict schemas
│       ├── requirements.txt
│       └── Dockerfile
│
├── database/
│   ├── schema.sql
│   └── cron_purge.py
│
├── docs/
│   ├── project_requirements.md
│   ├── architecture.md
│   ├── rules.md
│   ├── phases.md
│   ├── design.md
│   └── memory.md
│
└── README.md
```

**Rule:** this structure is authoritative. Any AI coding agent must update this file *first* before deviating from it — see rules.md §1 (Architecture Integrity).
