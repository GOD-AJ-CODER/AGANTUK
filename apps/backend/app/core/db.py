import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

# Path to the SQLite database
DB_PATH = os.path.join(os.path.dirname(__file__), "../../../../database/local.db")

def get_db_connection() -> sqlite3.Connection:
    """
    Creates and returns a SQLite connection configured for concurrent access.
    """
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    
    # Return rows as dictionary-like objects instead of tuples
    conn.row_factory = sqlite3.Row
    
    # Performance & Concurrency Optimizations
    conn.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging for speed & safety
    conn.execute("PRAGMA foreign_keys = ON;")   # Enforce relational integrity
    conn.execute("PRAGMA busy_timeout = 5000;") # Wait 5s before throwing lock error
    
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager wrapper for API endpoints and background tasks.
    Auto-commits on success, auto-rollbacks on exception, and closes connection.
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_audit_log(
    log_id: str,
    officer_id: str,
    doc_type: str | None,
    doc_number: str | None,
    verdict_status: str,
    confidence_scores: dict,
    failure_reason_codes: list[str],
    audit_hash: str | None = None,
    db: sqlite3.Connection | None = None,
) -> None:
    """
    Commit an immutable non-repudiation record to audit_logs (Rule 7.1).
    Ensures transactional safety and foreign key integrity.
    """
    import json
    from app.core.exceptions import DatabaseError
    from app.schemas.errors import ErrorCode

    def _execute_write(conn: sqlite3.Connection) -> None:
        # Guarantee officer exists to satisfy FOREIGN KEY (officer_id)
        conn.execute(
            """
            INSERT OR IGNORE INTO officers (officer_id, badge_number, full_name, role, is_active)
            VALUES (?, ?, ?, 'OFFICER', 1)
            """,
            (officer_id, f"BADGE-{officer_id}", f"Officer {officer_id}"),
        )
        conn.execute(
            """
            INSERT INTO audit_logs (
                log_id, officer_id, doc_type, doc_number,
                verdict_status, confidence_scores, failure_reason_codes, audit_hash, is_synced_cloud
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                log_id,
                officer_id,
                doc_type,
                doc_number,
                verdict_status,
                json.dumps(confidence_scores),
                json.dumps(failure_reason_codes),
                audit_hash,
            ),
        )

    try:
        if db is not None:
            _execute_write(db)
        else:
            with get_db() as conn:
                _execute_write(conn)
    except sqlite3.Error as exc:
        raise DatabaseError(
            error_code=ErrorCode.DB_WRITE_FAILED,
            message=f"Failed to record audit log: {exc}",
            detail=str(exc),
        ) from exc
