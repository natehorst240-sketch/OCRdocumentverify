"""Aviation Maintenance Records Processor — Streamlit entry point.

Sprint 1 scope: the app launches, initializes the SQLite database on first
run, and reports whether the local Qwen model (via Ollama) is reachable.
Later sprints add ingestion, OCR, form reconstruction, and gap analysis.
"""

from pathlib import Path

import streamlit as st

import database
import qwen_client

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"


@st.cache_resource
def bootstrap() -> Path:
    """One-time startup: ensure folders and the database exist."""
    for folder in (UPLOADS_DIR, OUTPUT_DIR, TEMPLATES_DIR):
        folder.mkdir(exist_ok=True)
    return database.init_db()


def main() -> None:
    st.set_page_config(
        page_title="Aviation Maintenance Records Processor",
        page_icon="🛩️",
        layout="wide",
    )

    db_path = bootstrap()

    st.title("🛩️ Aviation Maintenance Records Processor")
    st.caption("Local-first OCR and compliance gap analysis — no cloud required.")

    # --- System status (Sprint 1 acceptance criteria) -----------------------
    st.subheader("System status")
    col_db, col_qwen = st.columns(2)

    with col_db:
        st.markdown("**Database**")
        if db_path.exists():
            st.success(f"SQLite ready: `{db_path.name}`")
        else:
            st.error("Database not initialized.")

    with col_qwen:
        st.markdown("**Qwen / Ollama**")
        ok, message = qwen_client.is_available()
        (st.success if ok else st.error)(message)

    # --- Data overview ------------------------------------------------------
    st.subheader("Loaded data")
    counts = database.table_counts()
    cols = st.columns(len(counts))
    labels = {
        "documents": "Documents",
        "pages": "Pages",
        "requirements": "Requirements",
        "veryon_tasks": "Veryon Tasks",
        "compliance": "Compliance Records",
    }
    for col, (table, count) in zip(cols, counts.items()):
        col.metric(labels.get(table, table), count)

    st.info(
        "Sprint 1 scaffold is live. Upload and OCR features arrive in Sprint 2."
    )


if __name__ == "__main__":
    main()
