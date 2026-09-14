# rules.md

## 1. AI Code Generation & Development Boundaries

* **Zero Cloud Dependencies for Verification:** Core verification, image processing, OCR, and checksum logic MUST run 100% locally on FastAPI. Never introduce a cloud vision API call (Google Vision, AWS Rekognition, Azure Read, etc.) anywhere in the verification path.
* **Architecture Integrity:** Do not alter directory structure, filenames, or interface contracts from `architecture.md` without updating that file first, in the same change.
* **Strict Typing:** All Python uses full type hints and Pydantic schemas for every request/response. All TypeScript uses strict interfaces — zero use of `any`.
* **Execution Latency Constraint:** Stages A–D (preprocessing → forensics → inference → rule validation) must complete in ≤1,500ms per scan on target edge hardware. Anything approaching this budget gets flagged, not silently optimized away.
* **One Phase at a Time:** An AI coding agent must implement only the current phase in `phases.md`. Do not pre-build later-phase components "while you're in there."
* **No Placeholder Cheating:** Never fake a passing checksum, mock an ML model's output as a hardcoded constant, or stub forensic logic with `return True`. If a dependency isn't ready, raise a clear `NotImplementedError` with a TODO tied to its phase.

### Error Handling & Fallback Protocols

* **Structured Exceptions Only:** Wrap pipeline failures in a custom `VerificationError` JSON response. Never leak raw Python tracebacks to the client.
* **Database Resiliency:** All SQLite reads/writes run inside transactional context managers with retry-on-lock logic. A failed local write forces the system into a local fallback state before any PowerSync attempt.
* **Graceful Degradation:** If perspective warping can't find a document boundary, fall back to whole-image processing and append `WARP_FAILED_FULL_FRAME_USED` to the audit payload — never fail silently or drop the scan.

---

## 2. Rule Engine Specification Matrix

### STAGE 1 — Biometric Access & Mobile Ingestion Quality

**Rule 1.1 — Biometric Terminal Lock**
- `Session_Fingerprint_Auth == False` → **BLOCK.** HTTP 401. No processing without hardware fingerprint auth.
- `System_Idle_Time > 180s` → **FORCE LOGOUT.** Clear session tokens, require re-authentication.

**Rule 1.2 — Laplacian Motion Blur Check**
- Grayscale crop → `cv2.Laplacian()` → variance σ².
- `Laplacian_Variance < 100.0` → **REJECT.** HTTP 400, `"Image too blurry. Hold device steady."`

**Rule 1.3 — Auto-Perspective Warp & Contour Flattening**
- `cv2.findContours` → approximate to 4-point polygon → affine perspective transform to flat rectangle.
- `Document_Contour_NotFound == True` OR `Bounding_Angle > 45.0°` → **REJECT.** HTTP 400, `"Position full document within frame."`
- *(Exception: if a document boundary was found but the warp itself fails post-detection, apply the Graceful Degradation fallback above instead of rejecting.)*

**Rule 1.4 — Specular Glare Masking**
- HSV space, isolate `V > 240`. Check overlap against OCR key-zone bounding boxes (Name, DOB, MRZ).
- `Glare_Mask_Overlap(OCR_Key_Zones) == True` → **REJECT.** HTTP 400, `"Glare detected over key text fields. Adjust lighting or turn off flash."`

---

### STAGE 2 — Signal-Level Digital & Physical Forensics

**Rule 2.1 — JPEG Quantization / Double-Compression**
- `Inconsistent_Quantization_Tables == True` → **FLAG** `ERR_FORENSIC_DOUBLE_COMPRESSION`.

**Rule 2.2 — Error Level Analysis (ELA)**
- Resave at 95% quality, `cv2.absdiff`, compare photo-zone vs. substrate variance ratio.
- `ELA_Variance_Ratio > Threshold_Limit` → **FLAG** `ERR_FORENSIC_PHOTO_SPLICED`.

**Rule 2.3 — PRNU Noise Inconsistency**
- High-pass filter isolates sensor pattern noise.
- `Noise_Distribution_Inconsistency == True` → **FLAG** `ERR_FORENSIC_DIGITAL_PATCHING`.

**Rule 2.4 — Physical Aspect Ratio**
- Deviation > ±3.0% from ISO/IEC 7810 ID-1 (85.60×53.98mm) or ID-3 (125.0×88.0mm) → **FLAG** `ERR_FORENSIC_INVALID_DIMENSIONS`.

---

### STAGE 3 — AI Classification & OCR

**Rule 3.1 — YOLOv8 Document Type Match**
- `YOLO_Confidence_Score < 0.60` → **FLAG** `ERR_AI_UNKNOWN_DOC_FORMAT`.
- `0.60 ≤ YOLO_Confidence_Score < 0.85` → **MANUAL_REVIEW**.
- `Selected_Doc_Type != YOLO_Detected_Doc_Type` → **FLAG** `ERR_AI_DOC_TYPE_MISMATCH`.
- *(Precedence: evaluate confidence bands first; the type-mismatch check runs independently and can stack an additional flag on top of a confidence-band outcome.)*

**Rule 3.2 — PaddleOCR Null & Confidence Floors**
- Any of `Name`, `DOB`, `Document_Number`, `Expiry_Date`, `MRZ` == `NULL` → **FLAG** `ERR_OCR_MISSING_MANDATORY_FIELD`.
- `Average_OCR_Field_Confidence < 0.90` → **MANUAL_REVIEW**, append `WARN_OCR_LOW_CONFIDENCE`.

---

### STAGE 4 — Mathematical & Cryptographic Validation

**Rule 4.1 — MRZ Structure & Character Whitelist**
- Passport: line count ≠ 2 OR length ≠ 44 chars → **FLAG** `ERR_MATH_MALFORMED_MRZ_STRUCTURE`. ID/Visa: line count ≠ 3 OR length ≠ 30 chars → same code.
- Any character outside `^[A-Z0-9<]+$` → **FLAG** `ERR_MATH_INVALID_MRZ_CHARACTERS`.

**Rule 4.2 — VIZ vs. MRZ Cross-Check**
- `Visual_Zone_Name != MRZ_Parsed_Name` OR DOB OR DocNum mismatch → **CRITICAL FLAG** `ERR_MATH_VIZ_MRZ_MISMATCH`.

**Rule 4.3 — ICAO 9303 Weighted Modulo-10 Checksum**

Character mapping:
```
0–9   → 0–9
A–Z   → 10–35   (A=10, B=11, ..., Z=35)
<     → 0
```
Weights: `[7, 3, 1]` repeating.
```
Checksum = ( Σ MappedValue_i × Weight_i ) mod 10
```
- `Calculated_Mod10(Doc_Number) != Printed_MRZ_CheckDigit_1` → **CRITICAL FLAG** `ERR_MATH_MOD10_DOC_NUM_FAILED`.
- `Calculated_Mod10(DOB) != Printed_MRZ_CheckDigit_2` → **CRITICAL FLAG** `ERR_MATH_MOD10_DOB_FAILED`.
- `Calculated_Mod10(Expiry_Date) != Printed_MRZ_CheckDigit_3` → **CRITICAL FLAG** `ERR_MATH_MOD10_EXPIRY_FAILED`.
- `Calculated_Composite_Mod10 != Final_MRZ_Composite_CheckDigit` → **CRITICAL FLAG** `ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED`.

**Rule 4.4 — Modulo-37 Cross-Reference**
```
Remainder = ( Σ MappedValue_i × Weight_i ) mod 37
```
- `Calculated_Mod37(Alphanumeric_String) != Cross_Ref_Check_Char` → **FLAG** `ERR_MATH_MOD37_FAILED`.

---

### STAGE 5 — Chronological & Logical Consistency

- `Expiry_Date < Current_UTC_Date` → **FLAG** `ERR_LOGIC_DOCUMENT_EXPIRED`.
- `Issue_Date > Current_UTC_Date` → **FLAG** `ERR_LOGIC_FUTURE_ISSUE_DATE`.
- `Issue_Date >= Expiry_Date` → **FLAG** `ERR_LOGIC_TIMELINE_CONTRADICTION`.
- `(Current_Year - Birth_Year) < 0` OR `> 120` → **FLAG** `ERR_LOGIC_INVALID_AGE`.
- `Issue_Date < DOB` → **FLAG** `ERR_LOGIC_ISSUED_BEFORE_BIRTH`.

---

### STAGE 6 — Local Watchlist & Anti-Fraud

- **Rule 6.1 (Pass-Back):** Document number matches a local SQLite scan within the last 15 minutes → **CRITICAL FLAG** `ERR_SECURITY_PASSBACK_DETECTED`.
- **Rule 6.2 (Blacklist Match):** `Document_Number` OR `Full_Name + DOB` exact-matches the local watchlist cache → verdict forced to `CRITICAL_SECURITY_ALERT`, append `ERR_SECURITY_WATCHLIST_HIT`. This verdict cannot be downgraded by any other rule outcome.

---

### STAGE 7 — Offline Sync, Audit & Lifecycle

**Rule 7.1 — Biometric Audit Logging**
- Every verification request commits an immutable row to `audit_logs`: `officer_id` (biometric GUID), `timestamp_utc`, `doc_number`, `verdict_status`, `confidence_scores`, `failure_reason_codes`. No verdict is returned to the client until this write succeeds (see Database Resiliency above).

**Rule 7.2 — PowerSync Offline Queue Guard**
- Network offline AND unsynced queue length > 1,000 → display banner `"Local Audit Queue High. Network Sync Required Soon."` This is advisory only; it never blocks scanning.

**Rule 7.3 — CCTV-Style Rolling Data Purge**
- Daily cron (`cron_purge.py`): `Scan_Record_Age > 30 Days` AND `Verdict_Status == 'PASS'` → hard-delete raw image blobs and log entries, local and cloud. Any non-`PASS` record is retained indefinitely, regardless of age.

**Rule 7.4 — Mandatory Officer Manual Override Log**
- Verdict == `FLAGGED` AND officer clicks "Manual Pass Override" → intercept the UI event, require typed justification >15 characters, write a `MANUAL_OVERRIDE` record tagged with `officer_id` and the justification string, both to local SQLite and the PowerSync stream.
- **Override is never available for `CRITICAL_SECURITY_ALERT` verdicts** (Rule 6.2) — those must escalate to a supervisor workflow outside this system's scope, not be dismissible by the scanning officer.

---

## 3. Verdict Precedence (resolves ordering ambiguity across stages)

When multiple stages produce conflicting verdict levels for the same scan, the **highest-severity verdict always wins**, in this order (highest first):

1. `CRITICAL_SECURITY_ALERT` (Rule 6.2 — never overridable by an officer)
2. `FLAGGED` with any `CRITICAL FLAG`-tagged code (Rules 4.2, 4.3, 6.1)
3. `FLAGGED` with any standard flag code (Rules 2.x, 3.1, 3.2 missing-field, 4.1, 4.4, 5.x)
4. `MANUAL_REVIEW` (Rules 3.1 confidence band, 3.2 low confidence)
5. `PASS`

All triggered failure codes are collected and reported together regardless of which one determined the final verdict — the officer sees the full list, not just the top one.
