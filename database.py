"""SQLite setup and queries for the Aviation Maintenance Records Processor.

This module owns the database schema. ``init_db()`` is idempotent and is
called on every app start, so the schema here is the single source of truth
for all sprints, not just Sprint 1.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Honor RECORDS_DB so all state can live on one mounted volume (see compose).
DB_PATH = Path(os.environ.get("RECORDS_DB")
               or Path(__file__).resolve().parent / "records.db")

# --- Schema -----------------------------------------------------------------
# Each table maps to a user story in the plan:
#   documents / pages   -> Epic 2 ingestion + OCR (US 2.1, 2.2)
#   requirements        -> AD/ASB/ICA parsing (US 2.3)
#   veryon_tasks        -> Veryon Excel export (US 2.4)
#   compliance          -> Gap analysis matching (US 4.1, 4.2)
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    stored_path   TEXT NOT NULL,
    file_type     TEXT,                 -- jpg | png | pdf | xlsx
    category      TEXT,                 -- record | requirement | veryon
    page_count    INTEGER DEFAULT 1,
    uploaded_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL,
    page_number   INTEGER NOT NULL,
    source_file   TEXT NOT NULL,        -- denormalized for easy reporting
    extracted_text TEXT,
    form_type     TEXT,                 -- detected form type (Epic 3)
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS requirements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_number    TEXT,                 -- e.g. AD 2021-12-05
    req_type      TEXT,                 -- AD | ASB | ICA
    description   TEXT,
    interval      TEXT,
    applicability TEXT,
    required_action TEXT,
    source_file   TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE (doc_number, req_type, description)
);

CREATE TABLE IF NOT EXISTS veryon_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_code     TEXT,
    description   TEXT,
    interval      TEXT,
    last_compliance_date TEXT,
    last_compliance_hours TEXT,
    source_file   TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS compliance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_id INTEGER,
    page_id        INTEGER,
    status         TEXT,                -- complied | outstanding | needs_review
    confidence     REAL,
    compliance_date TEXT,
    compliance_hours TEXT,
    notes          TEXT,
    created_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE SET NULL
);
"""


@contextmanager
def get_connection(db_path: Path = DB_PATH):
    """Yield a SQLite connection with row access by column name."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> Path:
    """Create the database file and all tables if they do not exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


def table_counts(db_path: Path = DB_PATH) -> dict:
    """Return row counts per table, for the dashboard / status display."""
    tables = ["documents", "pages", "requirements", "veryon_tasks", "compliance"]
    counts = {}
    with get_connection(db_path) as conn:
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            counts[table] = row["n"]
    return counts


# --- Insert / update helpers ------------------------------------------------

def add_document(filename: str, stored_path: str, file_type: str | None,
                 category: str, page_count: int = 1,
                 db_path: Path = DB_PATH) -> int:
    """Record an uploaded document and return its id."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO documents (filename, stored_path, file_type, "
            "category, page_count) VALUES (?, ?, ?, ?, ?)",
            (filename, stored_path, file_type, category, page_count),
        )
        return cur.lastrowid


def add_page(document_id: int, page_number: int, source_file: str,
             extracted_text: str | None = None, form_type: str | None = None,
             db_path: Path = DB_PATH) -> int:
    """Record one page of a document and return its id."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO pages (document_id, page_number, source_file, "
            "extracted_text, form_type) VALUES (?, ?, ?, ?, ?)",
            (document_id, page_number, source_file, extracted_text, form_type),
        )
        return cur.lastrowid


def update_page_text(page_id: int, extracted_text: str,
                     db_path: Path = DB_PATH) -> None:
    """Attach OCR text to an existing page row."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pages SET extracted_text = ? WHERE id = ?",
            (extracted_text, page_id),
        )


def add_requirement(doc_number: str | None, req_type: str | None,
                    description: str | None, interval: str | None = None,
                    applicability: str | None = None,
                    required_action: str | None = None,
                    source_file: str | None = None,
                    db_path: Path = DB_PATH) -> int | None:
    """Insert a requirement, skipping duplicates.

    Returns the new row id, or ``None`` if it was a duplicate (the UNIQUE
    constraint on doc_number/type/description satisfies US 2.3 dedup).
    """
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO requirements (doc_number, req_type, "
            "description, interval, applicability, required_action, "
            "source_file) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_number, req_type, description, interval, applicability,
             required_action, source_file),
        )
        return cur.lastrowid if cur.rowcount else None


def add_veryon_task(task_code: str | None, description: str | None,
                    interval: str | None = None,
                    last_compliance_date: str | None = None,
                    last_compliance_hours: str | None = None,
                    source_file: str | None = None,
                    db_path: Path = DB_PATH) -> int:
    """Insert one Veryon task row and return its id."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO veryon_tasks (task_code, description, interval, "
            "last_compliance_date, last_compliance_hours, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_code, description, interval, last_compliance_date,
             last_compliance_hours, source_file),
        )
        return cur.lastrowid


def add_compliance(requirement_id: int, page_id: int | None, status: str,
                   confidence: float | None = None,
                   compliance_date: str | None = None,
                   compliance_hours: str | None = None,
                   notes: str | None = None,
                   db_path: Path = DB_PATH) -> int:
    """Record one compliance result for a requirement (US 4.1)."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO compliance (requirement_id, page_id, status, "
            "confidence, compliance_date, compliance_hours, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (requirement_id, page_id, status, confidence, compliance_date,
             compliance_hours, notes),
        )
        return cur.lastrowid


# --- Read helpers -----------------------------------------------------------

def clear_table(table: str, db_path: Path = DB_PATH) -> None:
    """Delete all rows from a table (used to re-run matching cleanly)."""
    with get_connection(db_path) as conn:
        conn.execute(f"DELETE FROM {table}")


def fetch_all(table: str, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    """Return all rows from a table, newest first where an id exists."""
    with get_connection(db_path) as conn:
        return conn.execute(
            f"SELECT * FROM {table} ORDER BY id DESC"
        ).fetchall()


def compliance_report(db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    """Join requirements to their compliance result and source page (US 4.3)."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT r.id AS requirement_id, r.doc_number, r.req_type, "
            "r.description, r.interval, r.source_file AS requirement_source, "
            "c.status, c.confidence, c.compliance_date, c.compliance_hours, "
            "c.notes, p.source_file AS record_source, p.page_number "
            "FROM requirements r "
            "LEFT JOIN compliance c ON c.requirement_id = r.id "
            "LEFT JOIN pages p ON c.page_id = p.id "
            "ORDER BY r.id"
        ).fetchall()


if __name__ == "__main__":
    path = init_db()
    print(f"Initialized database at {path}")
    print("Table counts:", table_counts())
