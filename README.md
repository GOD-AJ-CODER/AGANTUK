# AGANTUK (आगंतुक)
### Frontline Travel Credential Verification & Anti-Spoofing Engine

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20v0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat&logo=next.js)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/Tests-99%20Passing%20(100%25)-success?style=flat&logo=pytest)](apps/backend/tests)
[![Operation](https://img.shields.io/badge/Operation-100%25%20Offline%20Edge-informational?style=flat)]()



## 📌 Problem Statement & Operational Context

**Smart India Hackathon (SIH) | PS ID: 26188 | Ministry of Home Affairs & SSB**

Frontline border checkpoints operate in grueling, low-bandwidth environments where proprietary, cloud-dependent verification systems fail. Furthermore, physical security is highly vulnerable to human cognitive fatigue; exhausted officers working 12-hour shifts can miss subtle photo-splices or forged expiration dates.

**AGANTUK** replaces subjective human inspection with a deterministic, zero-discretion verification pipeline. It executes 100% locally on commodity edge hardware, mathematically validating travel credentials and completely eliminating single-point human failure.

---

## ⚡ Core Architectural USPs

* **Zero Proprietary Licensing:** Built entirely on open standards (ICAO Doc 9303, ISO/IEC 7810, OpenCV, FastAPI, SQLite) rather than expensive, locked-in vendor SDKs.


* **Fail-Closed Security Design:** If an anomaly is detected, the system forces a structured override justification or triggers a complete terminal lockout—officers cannot silently wave through flagged documents.


* **<1,500ms Edge Latency:** The entire computer vision, forensics, and cryptographic pipeline executes in under 1.5 seconds without a single cloud API call.



---

## 🛡️ Threat Model & Attack Vector Mitigation

| Attack Vector | AGANTUK Mitigation Engine |
| --- | --- |
| **Photo Swapping / Splicing** | **Error Level Analysis (ELA):** Detects variance ratio anomalies ($>15.0$) between the photo tile and document substrate.

 |
| **Altered Expiry / Doc Number** | **Cryptographic Math:** Validates ICAO 9303 Modulo-10 $[7, 3, 1]$ checksums and Modulo-37 alphanumeric cross-references.

 |
| **Credential Sharing (Pass-back)** | **Temporal Guardrail:** SQLite Write-Ahead Logging blocks duplicate document scans within a rolling 15-minute window.

 |
| **Digital Manipulation / Cloning** | **PRNU & Quantization:** Analyzes Photo-Response Non-Uniformity noise and JPEG double-compression tables.

 |
| **Operator Collusion** | **Cryptographic Non-Repudiation:** Every verdict writes an immutable SHA-256 hashed ledger entry.

 |

---

## 🏛️ Multi-Layer Pipeline Architecture

```text
[ Document Image Ingest ]
           │
           ▼
[ 1. Physical Quality Gate ] ──(Blur / Glare / Tilt)──► [ HTTP 400: "Hold Steady" ]
           │
           ▼
[ 2. Anti-Spoofing Forensics ] ──(ELA / PRNU / Ratio flags)──┐
           │                                                 │
           ▼                                                 │
[ 3. ICAO 9303 Math Engine ] ──(Mod-10/37 fail)──────────────┼──► [ Collect All Failure Codes ]
           │                                                 │                  │
           ▼                                                 │                  │
[ 4. Anti-Fraud & Watchlist ] ──(Pass-back / Blacklist)──────┘                  ▼
           │                                                       [ Verdict Precedence Engine ]
           ▼                                                       (CRITICAL > FLAGGED > WARN > PASS)
[ 5. Cryptographic Ledger ]                                                     │
     SHA-256 Canonical Hash ──► Dual-Write: SQLite WAL + audit_trail.jsonl ◄────┘

```

---

## 🧪 99-Test Proof of Reliability

The AGANTUK codebase is hardened by 99 passing unit and integration tests across 4 dedicated suites, proving edge-case resilience:

* **Stage 1 (7 Tests):** Motion blur (`σ² < 100.0`), document tilt ($>45^\circ$), HSV specular glare rejection.


* **Stage 3 (5 Tests):** TD1/TD2/TD3 MRZ parsers and Visual Inspection Zone (VIZ) mismatch detection.


* **Stage 4 (63 Tests):** Modulo math engines, ELA variance, pass-back protection, chronological contradictions, and verdict hierarchy resolution.


* **Stage 5 (24 Tests):** SHA-256 audit hashing determinism, tamper detection, and corrupted buffer sanitization.



---

## 🚀 Local Quickstart

**Backend Edge Node (FastAPI):**

```bash
cd apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

```

**Frontend Tactical Console (Next.js):**

```bash
cd apps/frontend
npm install
npm run dev

```

Access the inspection console at `http://localhost:3000/scan`.

---

## 🗺️ Scope & Roadmap

* **Current Baseline:** Full OpenCV gating, ICAO Mod-10/37 math, ELA/PRNU forensics, SQLite WAL, SHA-256 non-repudiation ledger, and high-contrast tactical UI.


* **Future Work:** Direct USB-HID passport hardware scanner integration, peer-to-peer mesh synchronization between checkpoint booths during WAN outages.

```

```
