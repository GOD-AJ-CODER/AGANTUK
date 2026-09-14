# AGANTUK (आगंतुक)
### Frontline Travel Credential Verification & Anti-Spoofing Engine

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20v0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat&logo=next.js)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/Tests-99%20Passing%20(100%25)-success?style=flat&logo=pytest)](apps/backend/tests)
[![Operation](https://img.shields.io/badge/Operation-100%25%20Offline%20Edge-informational?style=flat)]()


---

## 📌 Problem Statement

**Smart India Hackathon (SIH) | PS ID: 26188 | Ministry of Home Affairs & SSB**

**The Current Reality:** Right now, a traveler hands over their ID, and an officer has to manually juggle a dozen variables in their head under intense pressure—checking expiry dates, spotting tampered photos, and scanning for fake text. The final security decision relies entirely on the subjective judgment, mood, and fatigue of an exhausted officer working a 12-hour shift.

**Our Solution:** AGANTUK removes the guesswork. We replace human mood with a strict, automated safety net. Running 100% offline on standard laptops, it mathematically processes all those variables in milliseconds, catching fakes instantly and giving the officer a clear, foolproof verdict.

---

## ⚡ Core Features

* **Eliminating Expensive Licensing:** We dropped the overpriced vendor APIs. This is built entirely on open-source tools (OpenCV, FastAPI, SQLite) and open standards (ICAO Doc 9303).
* **No Silent Failures:** If a passport is flagged, an officer can't just click "ignore" to clear the queue. The system forces them to type a justification, or locks them out completely for severe threats.
* **Super Fast Offline Processing:** The entire computer vision, math, and database pipeline runs in under 1.5 seconds without making a single internet request.



---

## 🛡️ How We Catch Fakes (Threat Model)

| What Forgers Try | How AGANTUK Catches It |
| --- | --- |
| **Fake or Swapped Photos** | **Error Level Analysis (ELA):** Detects if the photo was copy-pasted by comparing compression noise against the background.

 |
| **Forged Dates or ID Numbers** | **Math Checksums:** Validates standard Modulo-10 `[7, 3, 1]` math formulas. If a number was changed, the math breaks.

 |
| **Same Passport Scanned Twice** | **15-Minute Cooldown:** Our local SQLite database automatically blocks duplicate document scans within a 15-minute window.

 |
| **Photoshop & Digital Edits** | **Noise Analysis:** Scans for hidden digital artifacts and re-compression traces.

 |
| **Corrupt Officers / Bribery** | **Secure Audit Log:** Every scan writes a permanent, SHA-256 hashed log. Nobody can alter the history to cover their tracks.

 |

---

## 🏛️ How the Code Works

```text
[ Upload Document Image ]
           │
           ▼
[ 1. Image Quality Check ] ────(Blur / Glare / Bad Angle)──► [ HTTP 400: "Hold Steady" ]
           │
           ▼
[ 2. Forensics Engine ] ───────(Photo Splice / Edits)──┐
           │                                           │
           ▼                                           │
[ 3. ICAO Math Engine ] ───────(Math / Checksum fail)──┼──► [ Collect All Errors ]
           │                                           │             │
           ▼                                           │             │
[ 4. Local Watchlist ] ────────(Pass-back / Blacklist)─┘             ▼
           │                                                [ Final Verdict ]
           ▼                                        (CRITICAL > FLAGGED > WARN > PASS)
[ 5. Secure Audit Log ]                                              │
     SHA-256 Hashed ─────────► Saved to SQLite & audit_trail.jsonl ◄─┘

```

---

## 🧪 99 Automated Tests

This isn't just a prototype. We wrote 99 automated tests across 4 suites to prove it handles real edge-cases reliably:

* **Stage 1 (7 Tests):** Drops blurry images, bad angles, and heavy camera glare.


* **Stage 3 (5 Tests):** Parses standard IDs/Passports and flags if the printed name doesn't match the machine-readable text.


* **Stage 4 (63 Tests):** Tests the math engines, pass-back protection, and logical flaws (like a passport issued *before* the person was born).


* **Stage 5 (24 Tests):** Proves the SHA-256 audit logs cannot be tampered with.



---

## 🚀 Local Quickstart

**1. Run the Backend (FastAPI):**

```bash
cd apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

```

**2. Run the Frontend (Next.js):**

```bash
cd apps/frontend
npm install
npm run dev

```

*Open `http://localhost:3000/scan` in your browser.*

---

## 🗺️ What's Next?

* **Current Status:** Fully working image quality gating, math checks, photo forensics, SQLite database, secure hashing, and Next.js frontend.


* **Future Work:** Hooking up physical USB passport scanners directly to the app, and syncing data between local laptops over a wireless mesh network when the internet is completely down.FingerPrint checking of each officer so he don't have to enter his or her officer id everytime to log into the system, Auth system is to be build so that the admin can add or remove fingerprint and entries of each officer and check out log of them...

```

```
