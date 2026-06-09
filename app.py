"""Aviation Maintenance Records Processor — Streamlit entry point.

Sprint 1: app boots, initializes SQLite, reports Qwen/Ollama status.
Sprint 2: ingestion + OCR for scanned records, AD/ASB/ICA requirement PDFs,
          and Veryon Excel exports.
"""

from pathlib import Path

import streamlit as st

import compliance_engine
import database
import excel_export
import field_mapper
import form_detector
import ocr
import pdf_parser
import pdf_writer
import qwen_client
import templates
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


def _first_page_image(saved: Path) -> Path:
    """Return an image path for a saved upload (rasterize PDF first page)."""
    if saved.suffix.lower() == ".pdf":
        return ocr.pdf_to_images(saved, UPLOADS_DIR / "forms")[0]
    return saved


def page_reconstruct() -> None:
    st.title("🧩 Reconstruct Form")
    st.caption("Detect the form type, OCR each field box, map to a template, "
               "and export a filled PDF.")

    uploaded = st.file_uploader(
        "Upload one scanned form", type=["jpg", "jpeg", "png", "pdf"])
    if uploaded and st.button("Analyze form"):
        saved = save_upload(uploaded, subdir="forms")
        with st.spinner("Reading and analyzing the form…"):
            image_path = _first_page_image(saved)
            full_text = ocr.ocr_page(image_path)
            classification = form_detector.classify_form_type(full_text)
            boxes = form_detector.detect_boxes(image_path)
            boxes = form_detector.ocr_boxes(image_path, boxes)
            annotated = form_detector.annotate_image(
                image_path, boxes,
                OUTPUT_DIR / f"annotated_{Path(image_path).stem}.png")
        st.session_state["recon"] = {
            "image_path": str(image_path),
            "annotated": str(annotated),
            "classification": classification,
            "boxes": boxes,
        }
        st.session_state.pop("recon_mappings", None)

    recon = st.session_state.get("recon")
    if not recon:
        return

    # --- US 3.1: detected type + manual override -----------------------------
    cls = recon["classification"]
    st.subheader("Detected form type")
    st.write(f"**{cls['form_type']}**  ·  confidence {cls['confidence']:.0%}")

    known = [t["form_type"] for t in templates.list_templates()]
    options = known + (["Unknown"] if "Unknown" not in known else [])
    default = cls["form_type"] if cls["form_type"] in options else \
        (options[0] if options else "Unknown")
    chosen = st.selectbox(
        "Confirm or override form type", options or ["Unknown"],
        index=(options.index(default) if default in options else 0))

    # --- US 3.2: annotated boxes --------------------------------------------
    st.subheader(f"Detected boxes ({len(recon['boxes'])})")
    st.image(recon["annotated"], use_container_width=True)

    template = templates.load_template(chosen) if chosen != "Unknown" else None
    if template is None:
        st.warning(
            f"No template for '{chosen}'. Build one in the Template Builder "
            "(Sprint 5) to enable field mapping and PDF output.")
        return

    # --- US 3.3: map boxes -> fields, editable -------------------------------
    if st.button("Map boxes to fields"):
        with st.spinner("Mapping fields with Qwen…"):
            st.session_state["recon_mappings"] = \
                field_mapper.map_boxes_to_fields(recon["boxes"], template)

    mappings = st.session_state.get("recon_mappings")
    if mappings:
        st.subheader("Field mapping (edit before export)")
        edited = st.data_editor(
            mappings, use_container_width=True, num_rows="fixed",
            key="mapping_editor")
        # st.data_editor returns the same container type it was given.
        edited = list(edited) if not isinstance(edited, list) else edited

        # --- US 3.4: generate filled PDF ------------------------------------
        if st.button("Generate filled PDF"):
            field_mapper.save_corrections(chosen, edited)
            values = field_mapper.mappings_to_values(edited)
            out_pdf = OUTPUT_DIR / f"{templates.slugify(chosen)}_filled.pdf"
            with st.spinner("Building PDF…"):
                pdf_writer.fill_pdf(template, values, out_pdf, base_dir=BASE_DIR)
            st.success("Filled PDF generated.")
            st.download_button(
                "⬇️ Download filled PDF", data=out_pdf.read_bytes(),
                file_name=out_pdf.name, mime="application/pdf")


def page_gap_analysis() -> None:
    st.title("📑 Compliance Gap Analysis")
    st.caption("Match records to requirements, compare against Veryon, and "
               "export a gap report.")

    # --- US 4.1: match records to requirements ------------------------------
    st.subheader("1 · Match records to requirements")
    if st.button("Run compliance matching"):
        with st.spinner("Pre-filtering and confirming matches with Qwen…"):
            st.session_state["match_summary"] = compliance_engine.run_matching()

    summary = st.session_state.get("match_summary")
    if summary:
        cols = st.columns(3)
        cols[0].metric("Complied", summary["complied"])
        cols[1].metric("Needs Review", summary["needs_review"])
        cols[2].metric("Outstanding", summary["outstanding"])
        report = [dict(r) for r in database.compliance_report()]
        if report:
            st.dataframe(report, use_container_width=True)

    # --- US 4.2: compare against Veryon -------------------------------------
    st.subheader("2 · Compare against Veryon export")
    if st.button("Compare to Veryon"):
        st.session_state["veryon_gap"] = compliance_engine.compare_to_veryon()

    gap = st.session_state.get("veryon_gap")
    if gap:
        cat = st.radio(
            "Category", ["matched", "missing_in_veryon", "missing_in_records"],
            format_func=lambda k: {
                "matched": f"Matched ({len(gap['matched'])})",
                "missing_in_veryon":
                    f"Missing from Veryon ({len(gap['missing_in_veryon'])})",
                "missing_in_records":
                    f"Missing from records ({len(gap['missing_in_records'])})",
            }[k], horizontal=True)
        st.dataframe(gap[cat] or [{"info": "none"}], use_container_width=True)

    # --- US 4.3: export gap report to Excel ---------------------------------
    st.subheader("3 · Export gap report")
    tail = st.text_input("Aircraft tail number", placeholder="e.g. N109SP")
    if st.button("Generate Excel gap report"):
        with st.spinner("Building workbook…"):
            out_xlsx = excel_export.build_gap_report(tail, OUTPUT_DIR)
        st.success(f"Report generated: {out_xlsx.name}")
        st.download_button(
            "⬇️ Download gap report", data=out_xlsx.read_bytes(),
            file_name=out_xlsx.name,
            mime="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


@st.cache_data(show_spinner=False)
def _grid_preview(pdf_path: str, mtime: float, spacing: int = 50) -> str | None:
    """Render a blank PDF's first page with a labeled point grid as a coordinate
    aid. Guarded — returns None on any failure so the builder never breaks."""
    try:
        import cv2
        from pypdf import PdfReader

        image_path = ocr.pdf_to_images(pdf_path, UPLOADS_DIR / "templates")[0]
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        h, w = img.shape[:2]
        media = PdfReader(pdf_path).pages[0].mediabox
        w_pts, h_pts = float(media.width), float(media.height)
        sx, sy = w / w_pts, h / h_pts  # pixels per point

        x = 0
        while x <= w_pts:
            px = int(x * sx)
            cv2.line(img, (px, 0), (px, h), (200, 200, 200), 1)
            cv2.putText(img, str(x), (px + 2, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
            x += spacing
        y = 0
        while y <= h_pts:
            py = h - int(y * sy)  # PDF y is from the bottom
            cv2.line(img, (0, py), (w, py), (200, 200, 200), 1)
            cv2.putText(img, str(y), (2, py - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
            y += spacing
        out = OUTPUT_DIR / f"grid_{Path(image_path).stem}.png"
        cv2.imwrite(str(out), img)
        return str(out)
    except Exception:
        return None


def _clean_fields(rows) -> list[dict]:
    """Coerce edited table rows into clean field dicts; drop unnamed rows."""
    if not isinstance(rows, list):
        rows = rows.to_dict("records")  # pandas DataFrame fallback
    fields = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        try:
            x = float(r.get("x") or 0)
        except (TypeError, ValueError):
            x = 0.0
        try:
            y = float(r.get("y") or 0)
        except (TypeError, ValueError):
            y = 0.0
        try:
            page = int(float(r.get("page") or 0))
        except (TypeError, ValueError):
            page = 0
        fields.append({"name": name, "x": x, "y": y, "page": page})
    return fields


def page_template_builder() -> None:
    st.title("🗂️ Template Builder")
    st.caption("Map a form's fields once; reused on every future scan. "
               "Coordinates are PDF points from the bottom-left corner.")

    existing = [t["form_type"] for t in templates.list_templates()]
    choice = st.selectbox("Template", ["➕ New template"] + existing)
    is_new = choice == "➕ New template"
    current = None if is_new else templates.load_template(choice)
    state_key = "new" if is_new else templates.slugify(choice)

    # Metadata. Keyed by selection so switching templates reloads cleanly.
    form_type = st.text_input(
        "Form type (required)",
        value="" if is_new else (current.get("form_type") or ""),
        key=f"ft_{state_key}")
    aircraft_type = st.text_input(
        "Aircraft type",
        value="" if is_new else (current.get("aircraft_type") or ""),
        key=f"at_{state_key}")

    # Optional blank PDF template + coordinate-grid aid.
    st.markdown("**Blank PDF template** (optional — without one, output is a "
                "plain page using your coordinates)")
    pdf_upload = st.file_uploader("Upload blank form PDF", type=["pdf"],
                                  key=f"pdf_{state_key}")
    pdf_rel = current.get("pdf_template") if current else None
    if pdf_upload and form_type.strip():
        slug = templates.slugify(form_type)
        saved_pdf = templates.TEMPLATES_DIR / f"{slug}.pdf"
        saved_pdf.write_bytes(pdf_upload.getbuffer())
        pdf_rel = f"templates/{slug}.pdf"

    pdf_abs = (BASE_DIR / pdf_rel) if pdf_rel else None
    if pdf_abs and pdf_abs.exists():
        grid = _grid_preview(str(pdf_abs), pdf_abs.stat().st_mtime)
        if grid:
            st.image(grid, caption="Read x/y in points off the grid",
                     use_container_width=True)
        else:
            st.info("Preview unavailable; enter coordinates from a PDF viewer.")

    # Field map table — built-in editor, add/remove rows freely.
    st.markdown("**Fields**")
    seed = (current.get("fields") if current else None) or \
        [{"name": "", "x": 0, "y": 0, "page": 0}]
    edited = st.data_editor(
        seed, num_rows="dynamic", use_container_width=True,
        key=f"fields_{state_key}",
        column_config={
            "name": st.column_config.TextColumn("Field name"),
            "x": st.column_config.NumberColumn("X (pts)"),
            "y": st.column_config.NumberColumn("Y (pts)"),
            "page": st.column_config.NumberColumn("Page", min_value=0, step=1),
        })

    col_save, col_delete = st.columns([3, 1])
    with col_save:
        if st.button("Save template", type="primary"):
            if not form_type.strip():
                st.error("Form type is required.")
            else:
                template = {"form_type": form_type.strip(),
                            "aircraft_type": aircraft_type.strip() or None,
                            "fields": _clean_fields(edited)}
                if pdf_rel:
                    template["pdf_template"] = pdf_rel
                path = templates.save_template(template)
                st.success(f"Saved {path.name} "
                           f"({len(template['fields'])} field(s)).")
    with col_delete:
        if not is_new and st.button("Delete"):
            templates.delete_template(choice)
            st.warning(f"Deleted '{choice}'. Reselect a template.")


PAGES = {
    "Dashboard": page_dashboard,
    "Upload Records": page_upload_records,
    "Upload Requirements": page_upload_requirements,
    "Upload Veryon Export": page_upload_veryon,
    "Reconstruct Form": page_reconstruct,
    "Gap Analysis": page_gap_analysis,
    "Template Builder": page_template_builder,
}


def main() -> None:
    st.set_page_config(
        page_title="Aviation Maintenance Records Processor",
        page_icon="🛩️", layout="wide",
    )
    db_path = bootstrap()

    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.markdown("---")
    st.sidebar.caption("Sprint 5: template builder")

    if choice == "Dashboard":
        page_dashboard(db_path)
    else:
        PAGES[choice]()


if __name__ == "__main__":
    main()
