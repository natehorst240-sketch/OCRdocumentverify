"""Aviation Maintenance Records Processor — Streamlit entry point.

Sprint 1: app boots, initializes SQLite, reports Qwen/Ollama status.
Sprint 2: ingestion + OCR for scanned records, AD/ASB/ICA requirement PDFs,
          and Veryon Excel exports.
"""

import uuid
from pathlib import Path

import streamlit as st

import access_control
import applicability
import compliance_engine
import database
import excel_export
import field_mapper
import form_detector
import handwriting_ocr
import inspection_parser
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
    # Use only the basename so a crafted filename can't escape the uploads dir.
    safe_name = Path(uploaded_file.name).name
    target = target_dir / safe_name
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
        st.markdown("**LLM**")
        if not qwen_client.llm_enabled():
            st.info("No-LLM mode — manual entry, keyword matching.")
        else:
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
    for col, (table, count) in zip(cols, counts.items(), strict=True):
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


def _current_requirements_table() -> None:
    reqs = [dict(r) for r in database.fetch_all("requirements")]
    st.subheader(f"Current requirements ({len(reqs)})")
    if reqs:
        st.dataframe(
            [{k: r.get(k) for k in
              ("doc_number", "req_type", "description", "interval",
               "applicability")} for r in reqs],
            use_container_width=True)


def _manual_requirements() -> None:
    """No-LLM requirement entry: read a PDF for reference, type rows in."""
    st.title("📋 Requirements (AD / ASB / ICA) — manual entry")
    st.caption("No-LLM mode: upload a PDF to read it, then add requirements by "
               "hand. Duplicates are skipped automatically.")

    pdf = st.file_uploader("Reference PDF (optional)", type=["pdf"])
    if pdf:
        saved = save_upload(pdf, subdir="requirements")
        with st.spinner("Extracting text…"):
            text = pdf_parser.extract_text(saved)
        st.text_area("Extracted text (read-only reference)",
                     text or "(no extractable text)", height=220)

    with st.form("add_requirement", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        doc_number = c1.text_input("Doc number", placeholder="AD 2021-12-05")
        req_type = c2.selectbox("Type", [
            "AD", "ASB", "ICA", "Scheduled Inspection",
            "Airworthiness Limitation", "Other"])
        interval = c3.text_input("Interval", placeholder="100 hrs / one-time")
        description = st.text_input("Description (required)")
        applicability = st.text_input("Applicability")
        action = st.text_input("Required action")
        if st.form_submit_button("Add requirement", type="primary"):
            if not description.strip():
                st.error("Description is required.")
            else:
                new_id = database.add_requirement(
                    doc_number.strip() or None, req_type, description.strip(),
                    interval=interval.strip() or None,
                    applicability=applicability.strip() or None,
                    required_action=action.strip() or None,
                    source_file=(pdf.name if pdf else "manual"))
                st.success("Requirement added." if new_id
                           else "Duplicate — skipped.")

    _current_requirements_table()


def page_upload_requirements() -> None:
    if not qwen_client.llm_enabled():
        _manual_requirements()
        return

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
    # Only pre-select a template when the classifier matched an exact saved
    # name; otherwise default to Unknown so an unrelated template is never
    # applied (and exported) silently for a new/renamed form.
    default = cls["form_type"] if cls["form_type"] in options else "Unknown"
    chosen = st.selectbox(
        "Confirm or override form type", options or ["Unknown"],
        index=(options.index(default) if default in options else 0))

    # --- US 3.2: annotated boxes --------------------------------------------
    st.subheader(f"Detected boxes ({len(recon['boxes'])})")
    st.image(recon["annotated"], use_container_width=True)

    # --- Field-box review: flag boxes the handwriting engine read with low
    # confidence, and let a human correct them before they flow into mapping.
    boxes = recon["boxes"]
    has_conf = any(b.get("confidence") is not None for b in boxes)
    if has_conf:
        st.subheader("Field box readings — review uncertain ones")
        threshold = st.slider(
            "Review threshold", 0.0, 1.0, 0.6, 0.05, key="recon_thresh",
            help="Boxes read below this confidence are flagged for you to "
                 "verify before the form is mapped and exported.")
        flagged = [b["id"] for b in boxes
                   if b.get("confidence") is not None
                   and b["confidence"] < threshold]
        if flagged:
            st.warning(
                f"⚠️ {len(flagged)} field box(es) read below "
                f"{threshold:.0%} — verify box(es) {flagged} below before "
                "mapping. Edits here flow into the field mapping.")
        else:
            st.success("✅ All field boxes read above the review threshold.")

        review_rows = [{
            "id": b["id"],
            "review": "⚠️" if b["id"] in flagged else "",
            "text": b.get("text", ""),
            "confidence": (round(b["confidence"], 2)
                           if b.get("confidence") is not None else None),
        } for b in boxes]
        edited_boxes = st.data_editor(
            review_rows, use_container_width=True, num_rows="fixed",
            hide_index=True, disabled=["id", "review", "confidence"],
            key="box_review_editor")
        # Write any corrected text back so mapping uses the reviewed values.
        corrected = {r["id"]: r.get("text", "") for r in list(edited_boxes)}
        for b in boxes:
            if b["id"] in corrected:
                b["text"] = corrected[b["id"]]
        recon["boxes"] = boxes
        st.session_state["recon"] = recon

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

    # Active aircraft drives applicability filtering of generic inspections.
    fleet = [dict(a) for a in database.fetch_all("aircraft")]
    aircraft = None
    if fleet:
        tail = st.selectbox(
            "Active aircraft (for applicability)",
            ["(none)"] + [a["tail_number"] for a in fleet])
        aircraft = next((a for a in fleet if a["tail_number"] == tail), None)
    else:
        st.caption("Add an Aircraft Profile to filter inspections by "
                   "applicability.")

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
        # Annotate each requirement with applicability for the active aircraft.
        reqs = database.fetch_all("requirements")
        verdicts = applicability.evaluate_all(reqs, aircraft)
        for row in report:
            status, reason = verdicts.get(row["requirement_id"],
                                          (applicability.REVIEW, ""))
            row["applicability"] = status
            row["applicability_reason"] = reason

        if aircraft:
            counts = {"applies": 0, "review": 0, "not_applicable": 0}
            for row in report:
                counts[row["applicability"]] = counts.get(
                    row["applicability"], 0) + 1
            acols = st.columns(3)
            acols[0].metric("Applies", counts["applies"])
            acols[1].metric("Review", counts["review"])
            acols[2].metric("Not applicable", counts["not_applicable"])
            show_na = st.checkbox("Show not-applicable items", value=False)
            if not show_na:
                report = [r for r in report
                          if r["applicability"] != applicability.NOT_APPLICABLE]

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
        if not is_new:
            confirm = st.checkbox("Confirm", key=f"del_{state_key}")
            if st.button("Delete", disabled=not confirm):
                templates.delete_template(choice)
                st.warning(f"Deleted '{choice}'. Reselect a template.")
                st.rerun()


def page_upload_inspections() -> None:
    st.title("🗓️ Scheduled Inspections (MM Ch 4/5)")
    st.caption("Upload OEM maintenance-manual chapters with inspection schedule "
               "tables. Tables are read directly — no OCR or LLM. Review the "
               "applicability column carefully before saving.")

    uploaded = st.file_uploader("Upload maintenance manual PDF(s)",
                                type=["pdf"], accept_multiple_files=True)
    if uploaded and st.button("Extract inspection tables"):
        all_rows = []
        for f in uploaded:
            saved = save_upload(f, subdir="inspections")
            with st.spinner(f"Reading {f.name}…"):
                try:
                    rows = inspection_parser.parse_inspections(saved)
                except Exception as exc:
                    st.error(f"Extraction failed for {f.name}: {exc}")
                    rows = []
            for r in rows:
                r["req_type"] = "Scheduled Inspection"
                r["source_file"] = f.name
            st.write(f"• {f.name}: {len(rows)} task(s)")
            all_rows.extend(rows)
        if not all_rows:
            st.warning("No inspection tables detected. Confirm the PDFs are "
                       "digital (selectable text), not scans.")
        else:
            st.session_state["insp_rows"] = all_rows

    rows = st.session_state.get("insp_rows")
    if not rows:
        return

    st.subheader(f"Review {len(rows)} extracted task(s)")
    st.caption("Fix any mis-read columns, set the type, and delete rows that "
               "aren't inspections. Applicability is captured verbatim from the "
               "manual — keep the serial/part/optional-equipment conditions.")
    edited = st.data_editor(
        rows, num_rows="dynamic", use_container_width=True, key="insp_editor",
        column_config={
            "doc_number": st.column_config.TextColumn("Task / Item"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "interval": st.column_config.TextColumn("Interval"),
            "applicability": st.column_config.TextColumn(
                "Applicability", width="large"),
            "req_type": st.column_config.SelectboxColumn(
                "Type", options=["Scheduled Inspection",
                                 "Airworthiness Limitation"]),
            "source_file": st.column_config.TextColumn("Source", disabled=True),
            "source_page": st.column_config.NumberColumn("Pg", disabled=True),
        })

    if st.button("Save inspections", type="primary"):
        records = list(edited) if isinstance(edited, list) else \
            edited.to_dict("records")
        added, skipped = 0, 0
        for r in records:
            desc = str(r.get("description") or "").strip()
            if not desc:
                continue
            new_id = database.add_requirement(
                doc_number=(str(r.get("doc_number")).strip()
                            if r.get("doc_number") else None),
                req_type=r.get("req_type") or "Scheduled Inspection",
                description=desc,
                interval=(str(r.get("interval")).strip()
                          if r.get("interval") else None),
                applicability=(str(r.get("applicability")).strip()
                               if r.get("applicability") else None),
                source_file=r.get("source_file") or "inspections")
            added += 1 if new_id else 0
            skipped += 0 if new_id else 1
        st.success(f"Saved {added} inspection(s); {skipped} duplicate(s) "
                   "skipped.")
        st.session_state.pop("insp_rows", None)


def page_aircraft_profile() -> None:
    st.title("✈️ Aircraft Profile")
    st.caption("The configuration that decides which generic manual inspections "
               "actually apply to this tail — serial number, optional equipment, "
               "and installed part numbers.")

    existing = [dict(a) for a in database.fetch_all("aircraft")]
    tails = [a["tail_number"] for a in existing]
    choice = st.selectbox("Aircraft", ["➕ New aircraft"] + tails)
    current = next((a for a in existing if a["tail_number"] == choice), None)
    key = "new" if current is None else choice

    tail = st.text_input("Tail number (required)",
                         value=(current["tail_number"] if current else ""),
                         key=f"tail_{key}")
    c1, c2 = st.columns(2)
    serial = c1.text_input("Serial number",
                           value=(current["serial_number"] if current else "") or "",
                           key=f"sn_{key}")
    model = c2.text_input("Model", value=(current["model"] if current else "") or "",
                          key=f"model_{key}")
    optional = st.text_area(
        "Installed optional equipment (one per line)",
        value=(current["optional_equipment"] if current else "") or "",
        key=f"opt_{key}",
        help="e.g. emergency float kit, wire strike protection, HTAWS")
    parts = st.text_area(
        "Installed part numbers (one per line)",
        value=(current["installed_parts"] if current else "") or "",
        key=f"parts_{key}")
    notes = st.text_input("Notes", value=(current["notes"] if current else "") or "",
                          key=f"notes_{key}")

    if st.button("Save aircraft", type="primary"):
        if not tail.strip():
            st.error("Tail number is required.")
        else:
            database.save_aircraft(
                tail.strip(), serial.strip() or None, model.strip() or None,
                optional.strip() or None, parts.strip() or None,
                notes.strip() or None)
            st.success(f"Saved configuration for {tail.strip()}.")

    st.info("Next step (in design): use this profile to flag each manual "
            "inspection as Applies / Not applicable / Review before gap "
            "analysis, so you only chase inspections relevant to this tail.")


def _confidence_overlay(image_path: Path, result: dict, threshold: float):
    """Draw per-glyph boxes over the scan, highlighting what needs review.

    Confident glyphs get a thin green→red box; glyphs below ``threshold`` get a
    bold red box and a '?' so a reviewer's eye goes straight to them. Returns a
    PIL image, or None if Pillow isn't available.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    bounds = result.get("line_bounds") or []
    for li, line in enumerate(result.get("glyphs") or []):
        y0, y1 = (bounds[li] if li < len(bounds) else (0, img.height - 1))
        for g in line:
            conf = float(g.get("confidence", 0.0))
            x0, x1 = g.get("x0", 0), g.get("x1", 0)
            if conf < threshold:
                draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=4)
                draw.text((x0, max(0, y0 - 10)), "?", fill=(255, 0, 0))
            else:
                colour = (int(255 * (1 - conf)), int(255 * conf), 0)
                draw.rectangle([x0, y0, x1, y1], outline=colour, width=2)
    return img


def _flag_uncertain(result: dict, threshold: float) -> list[dict]:
    """Return the glyphs the recognizer read below ``threshold`` — the items a
    human needs to decipher."""
    flagged = []
    for li, line in enumerate(result.get("glyphs") or []):
        for pos, g in enumerate(line):
            if float(g.get("confidence", 0.0)) < threshold:
                flagged.append({
                    "line": li + 1,
                    "position": pos + 1,
                    "best guess": g.get("char", "?"),
                    "confidence": round(float(g.get("confidence", 0.0)), 3),
                })
    return flagged


def page_read_handwriting() -> None:
    """Read a handwritten logbook scan, flagging anything the model can't read
    confidently for human review and correction.

    Dedicated handwriting engine for the one task PaddleOCR (tuned for printed
    text) handles poorly. Runs fully locally — no LLM, no Python ML stack — via
    the embedded-model Go binary. The point is not perfection: uncertain
    characters are surfaced so a person decides them before the text is trusted.
    """
    st.header("📝 Read Handwritten Log")

    ok, message = handwriting_ocr.is_available()
    if not ok:
        st.warning(message)
        st.markdown(
            "**To enable:** build the recognizer and turn it on:\n"
            "```bash\n"
            "cd handwriting && make build   # alphanumeric model is embedded\n"
            "export HANDWRITING_OCR=1\n"
            "```\n"
            "Set `HANDWRITING_BIN` if the binary lives elsewhere."
        )
        return
    st.success(message)

    c1, c2 = st.columns(2)
    multiline = c1.checkbox(
        "Multi-line page", value=True,
        help="On for a whole logbook page; off for a single line / field box.")
    threshold = c2.slider(
        "Review threshold", 0.0, 1.0, 0.6, 0.05,
        help="Characters the model reads below this confidence are flagged for "
             "you to decide. Raise it to be more cautious.")

    uploaded = st.file_uploader(
        "Upload a handwritten scan",
        type=["png", "jpg", "jpeg", "tif", "tiff", "bmp"])
    if not uploaded:
        return

    path = save_upload(uploaded, subdir="handwriting")
    with st.spinner("Recognizing…"):
        try:
            # min_conf marks flagged chars with '·' in the read-only text view.
            result = handwriting_ocr.read_file(
                str(path), multiline=multiline, min_conf=threshold)
        except handwriting_ocr.HandwritingOCRError as exc:
            st.error(f"Recognition failed: {exc}")
            return

    flagged = _flag_uncertain(result, threshold)
    mean = result.get("mean_confidence", 0.0)
    m1, m2, m3 = st.columns(3)
    m1.metric("Mean confidence", f"{mean:.0%}")
    m2.metric("Lines read", str(len(result.get("lines") or [])))
    m3.metric("Need review", str(len(flagged)))

    if flagged:
        st.warning(
            f"⚠️ {len(flagged)} character(s) couldn't be read confidently. "
            "They're marked with `·` below and boxed in red on the image — "
            "please correct them before accepting.")
    else:
        st.success("✅ Every character was read above the review threshold.")

    # Read-only view with flagged characters shown as '·'.
    st.subheader("Recognized (· = needs review)")
    st.code(result.get("text", ""), language=None)

    overlay = _confidence_overlay(path, result, threshold)
    if overlay is not None:
        st.subheader("Where to look")
        st.caption("Red box + ? = needs review · green→red = confidence")
        st.image(overlay, use_column_width=True)

    if flagged:
        st.subheader("Items to decipher")
        st.dataframe(flagged, use_container_width=True, hide_index=True)

    # Human correction: pre-fill with best-guess text (not the '·' version) so
    # the reviewer only has to fix the flagged spots, then accept.
    st.subheader("Correct & accept")
    corrected = st.text_area(
        "Edit the transcription, fixing any flagged characters:",
        value=result.get("text", ""), height=160, key="hw_corrected")

    a1, a2 = st.columns(2)
    if a1.button("✅ Accept transcription", type="primary"):
        out_path = OUTPUT_DIR / "handwriting" / (Path(uploaded.name).stem + ".txt")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(corrected, encoding="utf-8")
        st.success(f"Saved reviewed transcription to `{out_path}`.")
        st.download_button("Download .txt", corrected,
                           file_name=out_path.name, mime="text/plain")

    # Capture the uncertain glyphs so corrections become training data.
    if flagged and a2.button("📁 Save flagged glyphs for retraining"):
        review_dir = UPLOADS_DIR / "handwriting_review" / Path(uploaded.name).stem
        try:
            n = handwriting_ocr.export_uncertain_glyphs(
                str(path), str(review_dir), max_conf=threshold,
                multiline=multiline)
            st.success(
                f"Wrote {n} uncertain glyph image(s) to `{review_dir}`. Sort "
                "them into per-character folders and run `handwriting train "
                "-dir …` to teach the model your hand (see "
                "`handwriting/TRAINING.md`).")
        except handwriting_ocr.HandwritingOCRError as exc:
            st.error(f"Could not export glyphs: {exc}")


PAGES = {
    "Dashboard": page_dashboard,
    "Aircraft Profile": page_aircraft_profile,
    "Read Handwritten Log": page_read_handwriting,
    "Upload Records": page_upload_records,
    "Upload Requirements": page_upload_requirements,
    "Upload Inspections": page_upload_inspections,
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

    # Business-hours gate (hosted instance only; no-op locally).
    is_open, schedule = access_control.business_open()
    if not is_open:
        st.title("🛩️ Temporarily closed")
        st.info(f"This tool is available {schedule}. Please check back then.")
        st.stop()

    # Single-user gate: hold one active session at a time.
    session_id = st.session_state.setdefault("session_id", uuid.uuid4().hex)
    if not access_control.acquire_single_user(session_id):
        st.title("🛩️ In use")
        st.warning("Someone else is using the tool right now. Please try "
                   "again in a few minutes.")
        if st.button("Retry"):
            st.rerun()
        st.stop()

    db_path = bootstrap()

    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"Mode: {'No-LLM (manual)' if not qwen_client.llm_enabled() else 'LLM'}")

    if choice == "Dashboard":
        page_dashboard(db_path)
    else:
        PAGES[choice]()


if __name__ == "__main__":
    main()
