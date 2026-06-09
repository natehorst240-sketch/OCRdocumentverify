"""Aviation Maintenance Records Processor — Streamlit entry point.

Sprint 1: app boots, initializes SQLite, reports Qwen/Ollama status.
Sprint 2: ingestion + OCR for scanned records, AD/ASB/ICA requirement PDFs,
          and Veryon Excel exports.
"""

from pathlib import Path

import streamlit as st

import database
import ocr
import pdf_parser
import qwen_client
import veryon_import

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


def save_upload(uploaded_file, subdir: str = "") -> Path:
    """Persist a Streamlit UploadedFile under /uploads and return its path."""
    target_dir = UPLOADS_DIR / subdir if subdir else UPLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / uploaded_file.name
    target.write_bytes(uploaded_file.getbuffer())
    return target


# --- Pages ------------------------------------------------------------------

def page_dashboard(db_path: Path) -> None:
    st.title("🛩️ Aviation Maintenance Records Processor")
    st.caption("Local-first OCR and compliance gap analysis — no cloud required.")

    st.subheader("System status")
    col_db, col_qwen = st.columns(2)
    with col_db:
        st.markdown("**Database**")
        (st.success if db_path.exists() else st.error)(
            f"SQLite ready: `{db_path.name}`" if db_path.exists()
            else "Database not initialized."
        )
    with col_qwen:
        st.markdown("**Qwen / Ollama**")
        ok, message = qwen_client.is_available()
        (st.success if ok else st.error)(message)

    st.subheader("Loaded data")
    counts = database.table_counts()
    labels = {
        "documents": "Documents", "pages": "Pages",
        "requirements": "Requirements", "veryon_tasks": "Veryon Tasks",
        "compliance": "Compliance Records",
    }
    cols = st.columns(len(counts))
    for col, (table, count) in zip(cols, counts.items()):
        col.metric(labels.get(table, table), count)


def page_upload_records() -> None:
    st.title("📄 Upload Scanned Records")
    st.caption("Logbook pages and work orders (JPG / PNG / PDF).")

    files = st.file_uploader(
        "Upload scanned records", type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
    )
    if not files:
        return

    run_ocr = st.checkbox("Run OCR after upload", value=True)
    if not st.button("Process records"):
        return

    for uploaded in files:
        saved = save_upload(uploaded, subdir="records")
        suffix = saved.suffix.lower()

        # Resolve the page images for this upload.
        if suffix == ".pdf":
            with st.spinner(f"Splitting {saved.name} into pages…"):
                page_images = ocr.pdf_to_images(saved, UPLOADS_DIR / "records")
        else:
            page_images = [saved]

        doc_id = database.add_document(
            filename=uploaded.name, stored_path=str(saved),
            file_type=suffix.lstrip("."), category="record",
            page_count=len(page_images),
        )

        st.markdown(f"### {uploaded.name} — {len(page_images)} page(s)")
        for page_no, image_path in enumerate(page_images, start=1):
            cols = st.columns([1, 2])
            with cols[0]:
                st.image(str(image_path), caption=f"Page {page_no}",
                         use_container_width=True)

            text = None
            if run_ocr:
                with st.spinner(f"OCR page {page_no}…"):
                    try:
                        text = ocr.ocr_page(image_path)
                    except Exception as exc:  # surface, don't crash the run
                        st.error(f"OCR failed on page {page_no}: {exc}")

            page_id = database.add_page(
                document_id=doc_id, page_number=page_no,
                source_file=uploaded.name, extracted_text=text,
            )
            with cols[1]:
                if text:
                    st.text_area(
                        f"Extracted text (page {page_no})", text, height=200,
                        key=f"text_{page_id}",
                    )
                elif run_ocr:
                    st.warning("No text extracted.")
                else:
                    st.info("Stored without OCR.")

    st.success("Records processed and stored.")


def page_upload_requirements() -> None:
    st.title("📋 Upload Requirements (AD / ASB / ICA)")
    st.caption("Regulatory PDFs are parsed into structured requirements.")

    files = st.file_uploader(
        "Upload requirement documents", type=["pdf"],
        accept_multiple_files=True,
    )
    if not files or not st.button("Parse requirements"):
        return

    for uploaded in files:
        saved = save_upload(uploaded, subdir="requirements")
        with st.spinner(f"Extracting text from {saved.name}…"):
            text = pdf_parser.extract_text(saved)
        if not text.strip():
            st.warning(f"No extractable text in {saved.name} (scanned PDF?).")
            continue

        with st.spinner("Asking Qwen to structure requirements…"):
            try:
                requirements = pdf_parser.extract_requirements(text)
            except Exception as exc:
                st.error(f"Requirement extraction failed: {exc}")
                continue

        added, skipped = 0, 0
        for req in requirements:
            new_id = database.add_requirement(
                doc_number=req.get("doc_number"),
                req_type=req.get("req_type"),
                description=req.get("description"),
                interval=req.get("interval"),
                applicability=req.get("applicability"),
                required_action=req.get("required_action"),
                source_file=uploaded.name,
            )
            if new_id:
                added += 1
            else:
                skipped += 1

        st.markdown(f"### {uploaded.name}")
        st.write(f"Parsed {len(requirements)} requirement(s): "
                 f"**{added} added**, {skipped} duplicate(s) skipped.")
        if requirements:
            st.dataframe(requirements, use_container_width=True)


def page_upload_veryon() -> None:
    st.title("📊 Upload Veryon Export")
    st.caption("Excel export of tasks already built in Veryon.")

    uploaded = st.file_uploader("Upload Veryon Excel", type=["xlsx", "xls"])
    if not uploaded or not st.button("Import tasks"):
        return

    saved = save_upload(uploaded, subdir="veryon")
    database.add_document(
        filename=uploaded.name, stored_path=str(saved),
        file_type=saved.suffix.lstrip("."), category="veryon",
    )
    with st.spinner("Importing Veryon tasks…"):
        try:
            summary = veryon_import.import_excel(saved)
        except Exception as exc:
            st.error(f"Import failed: {exc}")
            return

    st.success(f"Imported {summary['imported']} of {summary['total_rows']} rows.")
    st.markdown("**Resolved column mapping**")
    st.json(summary["column_map"])


PAGES = {
    "Dashboard": page_dashboard,
    "Upload Records": page_upload_records,
    "Upload Requirements": page_upload_requirements,
    "Upload Veryon Export": page_upload_veryon,
}


def main() -> None:
    st.set_page_config(
        page_title="Aviation Maintenance Records Processor",
        page_icon="🛩️", layout="wide",
    )
    db_path = bootstrap()

    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.markdown("---")
    st.sidebar.caption("Sprint 2: ingestion + OCR")

    if choice == "Dashboard":
        page_dashboard(db_path)
    else:
        PAGES[choice]()


if __name__ == "__main__":
    main()
