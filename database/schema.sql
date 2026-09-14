PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS officers (
    officer_id TEXT PRIMARY KEY,
    badge_number TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT CHECK(role IN ('OFFICER', 'SUPERVISOR', 'AUDITOR')) NOT NULL DEFAULT 'OFFICER',
    is_active INTEGER NOT NULL DEFAULT 1,
    last_login_utc TEXT,
    created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    watchlist_id TEXT PRIMARY KEY,
    doc_number TEXT NOT NULL,
    full_name TEXT,
    dob TEXT,
    issuing_country TEXT,
    reason TEXT NOT NULL,
    added_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_watchlist_doc_number ON watchlist(doc_number);
CREATE INDEX IF NOT EXISTS idx_watchlist_name_dob ON watchlist(full_name, dob);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY,
    officer_id TEXT NOT NULL,
    timestamp_utc TEXT DEFAULT CURRENT_TIMESTAMP,
    doc_type TEXT,
    doc_number TEXT,
    verdict_status TEXT CHECK(verdict_status IN ('PASS', 'MANUAL_REVIEW', 'FLAGGED', 'CRITICAL_SECURITY_ALERT')) NOT NULL,
    confidence_scores TEXT,
    failure_reason_codes TEXT,
    audit_hash TEXT,
    is_synced_cloud INTEGER DEFAULT 0,
    FOREIGN KEY (officer_id) REFERENCES officers(officer_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_passback ON audit_logs(doc_number, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_audit_logs_sync ON audit_logs(is_synced_cloud);

PRAGMA foreign_keys = ON;
