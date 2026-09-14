# design.md

## 1. Core Design Philosophy: "Tactical Utility"

This is not a trendy SaaS surface. It's a mission-critical interface for exhausted border officers working 12-hour shifts in poorly lit booths, fighting screen glare, under real cognitive load with real consequences for a missed detail.

The interface must be **unambiguous, indestructible, and instantly readable.**

* **Zero friction:** no hidden menus, no hover-dependent states (touchscreens have no hover), no glassmorphism.
* **High contrast:** every element must pass WCAG AAA contrast ratios.
* **Glanceability:** verdict must be legible from 3 feet away within 0.2 seconds.

---

## 2. Color Palette (High-Contrast Dark Theme)

Dark mode is default — reduces eye strain on night shifts, with aggressive high-contrast accents on top.

### Base & Backgrounds
* App Background: `#121212` (deep charcoal — less glare than pure black).
* Panel/Card Background: `#1E1E1E`.
* Borders & Dividers: `#333333`, 2px minimum, used to physically separate every data zone.

### Traffic-Light Status System (Critical)
Color is never the only signal — every status pairs with a heavy icon for colorblind officers.

| Status | Color | Hex | Icon |
|---|---|---|---|
| PASS | Neon Mint | `#00E676` | `[ ✓ ]` — massive |
| MANUAL REVIEW | Warning Yellow | `#FFC107` | `[ ! ]` triangle |
| CRITICAL FLAG | Blaring Crimson | `#FF3B30` | `[ X ]` octagon, screen border flashes |
| CRITICAL SECURITY ALERT | Blaring Crimson + strobe | `#FF3B30` | `[ ⛔ ]` — full-screen takeover, cannot be dismissed by the scanning officer (see rules.md Rule 7.4) |

### Text Colors
* Primary Text: `#FFFFFF`.
* Secondary Text: `#A0A0A0` (field labels — "Date of Birth", etc.).
* Data Highlight: `#4FC3F7` (electric blue — marks the exact digit/string that triggered a failure).

---

## 3. Typography: Legibility Over Aesthetics

Fonts must eliminate the `I` vs `1` and `O` vs `0` failure mode entirely.

* **UI Font (headers, buttons, labels):** Inter or Roboto, heavily weighted (Bold/Black) for headers.
* **Data Font (MRZ, passport numbers, DOB, any officer-verified string):** JetBrains Mono or Fira Code — **must** have a slashed zero and a distinct tail on lowercase `l` / uppercase `I`. Every OCR readout and MRZ line renders in this font, no exceptions.

---

## 4. Component Anatomy & Layout

### Grid & Spacing
* Rigid, blocky layout. `border-radius: 2px` maximum, everywhere.
* CSS Grid keeps data aligned in fixed columns — the officer's eyes never hunt for the Expiry Date.

### Touch Targets
* Assume cheap touchscreens and gloved hands.
* All interactive elements ≥64px tall with generous hit-boxes — no exceptions for "minor" buttons.

### The Verdict Card (Hero Component)
Dominates ~70% of the screen the moment a scan completes.

* **PASS:** solid green box, large checkmark, extracted passport photo next to name at 48pt.
* **FLAGGED:** screen border turns red; failure code(s) render in large monospace type, with the exact offending value highlighted in the data-highlight blue, not red (red is reserved for the verdict chrome, not the data itself — keeps the highlighted string readable against the flag color).
* **CRITICAL_SECURITY_ALERT:** full-screen red takeover, no dismiss control visible to the scanning officer — this state routes to a supervisor action, not an "Override" button.

### Forensic Heatmap Modal
Triggered on any ELA/PRNU anomaly flag.
* 50/50 split: raw document (left) vs. forensic heatmap (right), deep blues with the forged/spliced region glowing in neon orange/red thermal tones.

---

## 5. UI Feedback & Interaction

* **No spinners.** Use a blocky, staged progress bar: `[██████░░░░]` stepping through named stages ("Pre-Processing…" → "Forensics…" → "Math Validation…") so the officer always knows the system is alive, and roughly where in the 1,500ms budget it is.
* **Audio feedback (recommended):**
  * Success: single sharp, pleasant beep.
  * Flag: harsh dual-tone buzzer.
  * Critical Security Alert: continuous alarm tone until acknowledged by a supervisor-level action.
* **The Override control:** visually subordinate (hollow outline, never solid fill), physically separated from "Next Scan" to prevent mis-taps. Only enabled for `FLAGGED`, never for `CRITICAL_SECURITY_ALERT`. Clicking it dims the screen and opens a stark modal demanding the >15-character typed justification (Rule 7.4) — no submit button lights up until that minimum is met.
