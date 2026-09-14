export type VerdictStatus =
  | "PASS"
  | "MANUAL_REVIEW"
  | "FLAGGED"
  | "CRITICAL_SECURITY_ALERT";

export interface ExtractedFields {
  doc_number?: string | null;
  full_name?: string | null;
  surname?: string | null;
  given_names?: string | null;
  date_of_birth?: string | null;
  expiry_date?: string | null;
  nationality?: string | null;
  issuing_country?: string | null;
  sex?: string | null;
}

export interface ConfidenceScores {
  laplacian_variance?: number | null;
  ocr_average?: number | null;
  ela_variance_ratio?: number | null;
  yolo_classification?: number | null;
}

export interface VerificationResponse {
  ok: boolean;
  log_id: string;
  verdict: VerdictStatus;
  failure_codes: string[];
  doc_type_detected?: string | null;
  extracted_fields?: ExtractedFields | null;
  confidence_scores?: ConfidenceScores;
  officer_id: string;
  audit_hash?: string | null;
}

export interface AuthSession {
  token: string;
  officer_id: string;
  badge_number: string;
  full_name: string;
  expires_at: number; // UTC timestamp ms
}

export interface AuditLogItem {
  log_id: string;
  timestamp_utc: string;
  officer_id: string;
  doc_type?: string | null;
  doc_number?: string | null;
  verdict_status: VerdictStatus;
  confidence_scores?: ConfidenceScores | string;
  failure_reason_codes?: string[] | string;
  audit_hash?: string | null;
  is_synced_cloud?: number;
}
