/**
 * Plain-English Human Language Layer for AGANTUK.
 * Translates cryptographic, mathematical, and forensic failure codes into
 * crystal-clear, everyday English for frontline border officers.
 */

export interface HumanExplanation {
  title: string;
  summary: string;
  action: string;
  severity: "critical" | "high" | "medium" | "low";
}

const FAILURE_TRANSLATIONS: Record<string, (context?: { expiryDate?: string | null; docNumber?: string | null }) => HumanExplanation> = {
  ERR_SECURITY_WATCHLIST_HIT: (ctx) => ({
    title: "ALERT: Passport Number On Active Flag List",
    summary: `Target credential ${ctx?.docNumber ? `[${ctx.docNumber}] ` : ""}exact-matches a high-priority national or international watchlist.`,
    action: "Do not clear traveler. Detain credential and notify shift supervisor immediately.",
    severity: "critical",
  }),

  ERR_SECURITY_PASSBACK_DETECTED: (ctx) => ({
    title: "Duplicate Scan (Passback Detected)",
    summary: `This exact document number ${ctx?.docNumber ? `[${ctx.docNumber}] ` : ""}was already cleared at this terminal within the last 15 minutes.`,
    action: "Check for duplicate traveler, line-cutting, or credential sharing.",
    severity: "high",
  }),

  ERR_MATH_MOD10_DOC_NUM_FAILED: () => ({
    title: "Passport Number Altered or Misprinted",
    summary: "Passport number on bottom machine-readable strip has been altered, forged, or misprinted.",
    action: "Carefully compare printed passport number on top against the bottom machine-readable strip.",
    severity: "high",
  }),

  ERR_MATH_MOD10_DOB_FAILED: () => ({
    title: "Date of Birth Checksum Failed",
    summary: "Date of birth on bottom machine strip fails the international mathematical security checksum.",
    action: "Verify traveler's actual date of birth against visual page.",
    severity: "high",
  }),

  ERR_MATH_MOD10_EXPIRY_FAILED: () => ({
    title: "Expiry Date Checksum Failed",
    summary: "Expiry date digits on bottom strip do not match mathematical check digit.",
    action: "Check if expiry date has been overwritten or modified.",
    severity: "high",
  }),

  ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED: () => ({
    title: "Master Composite Checksum Failed",
    summary: "Master security check across all combined data fields failed. High probability of fraudulent credential.",
    action: "Reject travel clearance. Route to secondary inspection.",
    severity: "high",
  }),

  ERR_MATH_VIZ_MRZ_MISMATCH: () => ({
    title: "Printed Details Do Not Match Bottom Strip",
    summary: "Information printed on main document page (Name, Doc Number, or DOB) contradicts bottom readable strip.",
    action: "Look for visual stickers, swapped photo inserts, or physical alterations.",
    severity: "high",
  }),

  ERR_MATH_MOD37_FAILED: () => ({
    title: "Alphanumeric Cross-Check Mismatch",
    summary: "National identity alphanumeric cross-reference checksum (Modulo-37) failed.",
    action: "Inspect national identity card numbers and issuing jurisdiction marks.",
    severity: "high",
  }),

  ERR_LOGIC_DOCUMENT_EXPIRED: (ctx) => ({
    title: ctx?.expiryDate ? `Document Expired on ${ctx.expiryDate}` : "Document Has Expired",
    summary: `Travel credential expired ${ctx?.expiryDate ? `on ${ctx.expiryDate}` : "prior to today"} and is no longer legally valid for border transit.`,
    action: "Deny departure or entry unless traveler holds valid emergency visa extension.",
    severity: "high",
  }),

  ERR_LOGIC_FUTURE_ISSUE_DATE: () => ({
    title: "Issue Date Is In The Future",
    summary: "Document issue date is chronologically impossible (future date).",
    action: "Physical document is counterfeit or printed with incorrect clock.",
    severity: "high",
  }),

  ERR_LOGIC_TIMELINE_CONTRADICTION: () => ({
    title: "Timeline Contradiction (Issue Date After Expiry)",
    summary: "Document timeline is logically backwards: date of issue is recorded after expiry date.",
    action: "Verify official passport validity window.",
    severity: "high",
  }),

  ERR_LOGIC_ISSUED_BEFORE_BIRTH: () => ({
    title: "Issued Before Holder Was Born",
    summary: "Passport record claims this credential was issued before the traveler was born.",
    action: "Check for clerical error or identity theft.",
    severity: "high",
  }),

  ERR_LOGIC_INVALID_AGE: () => ({
    title: "Holder Age Falls Outside Human Range",
    summary: "Derived age from birth date is invalid (less than 0 or over 120 years).",
    action: "Examine date of birth field formatting.",
    severity: "high",
  }),

  ERR_FORENSIC_PHOTO_SPLICED: () => ({
    title: "Photo Area Shows Tampering or Splicing",
    summary: "Photo area shows signs of digital photo substitution, editing, or physical cut-and-paste.",
    action: "Inspect photo page under oblique desk light for physical razor cuts or glue lines.",
    severity: "high",
  }),

  ERR_FORENSIC_DIGITAL_PATCHING: () => ({
    title: "Digital Cloning or Patching Detected",
    summary: "Camera sensor pattern analysis shows digital copy-paste artifacts.",
    action: "Credential may be a printed scan rather than an authentic integrated card.",
    severity: "high",
  }),

  ERR_FORENSIC_DOUBLE_COMPRESSION: () => ({
    title: "Digital Image Re-Compression Detected",
    summary: "Underlying file contains multiple JPEG quantization tables, indicating it was opened and saved in photo-editing software.",
    action: "Verify physical original document, not phone photo or screenshot.",
    severity: "medium",
  }),

  ERR_FORENSIC_INVALID_DIMENSIONS: () => ({
    title: "Incorrect Document Physical Size",
    summary: "Credential dimensions deviate by more than 3% from ISO/IEC standard passport and ID card sizes.",
    action: "Check if document was cropped or printed on substandard paper stock.",
    severity: "medium",
  }),

  ERR_MATH_MALFORMED_MRZ_STRUCTURE: () => ({
    title: "Bottom Readable Strip Formatting Broken",
    summary: "Machine-readable strip does not follow international line length (TD1: 30 chars, TD3: 44 chars).",
    action: "Ensure entire credential is flat inside scanner viewport.",
    severity: "medium",
  }),

  ERR_MATH_INVALID_MRZ_CHARACTERS: () => ({
    title: "Illegal Characters On Machine Strip",
    summary: "Found invalid characters on bottom strip. Only uppercase A-Z, 0-9, and '<' are permitted.",
    action: "Clean scanner glass or wipe dirt off document strip.",
    severity: "medium",
  }),

  ERR_OCR_MISSING_MANDATORY_FIELD: () => ({
    title: "Required Information Missing",
    summary: "Could not read one or more mandatory fields (Holder Name, DOB, Document Number, or Expiry).",
    action: "Align document straight and avoid covering fields with fingers.",
    severity: "medium",
  }),

  WARN_OCR_LOW_CONFIDENCE: () => ({
    title: "Text Clarity Is Low",
    summary: "Optical clarity is below optimal confidence due to glare, worn ink, or low scanner contrast.",
    action: "Officer must manually verify traveler names and numbers.",
    severity: "low",
  }),
};

export function translateFailureCode(
  code: string,
  context?: { expiryDate?: string | null; docNumber?: string | null }
): HumanExplanation {
  const translator = FAILURE_TRANSLATIONS[code];
  if (translator) {
    return translator(context);
  }

  // Sensible humanized fallback
  const cleanTitle = code
    .replace(/^ERR_/, "")
    .replace(/^WARN_/, "")
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return {
    title: cleanTitle,
    summary: `Technical verification rule ${code} was triggered during document inspection.`,
    action: "Conduct standard visual secondary check.",
    severity: code.startsWith("ERR_SECURITY") ? "critical" : code.startsWith("ERR_") ? "high" : "low",
  };
}
