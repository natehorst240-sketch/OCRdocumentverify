"""SQLite setup and queries for the Aviation Maintenance Records Processor.

This module owns the database schema. ``init_db()`` is idempotent and is
called on every app start, so the schema here is the single source of truth
for all sprints, not just Sprint 1.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "records.db"

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


if __name__ == "__main__":
    path = init_db()
    print(f"Initialized database at {path}")
    print("Table counts:", table_counts())
