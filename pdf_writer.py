"""Generate a filled PDF from mapped field values (US 3.4).

Text is drawn at each field's template coordinates onto a reportlab overlay,
which is then merged onto the blank PDF template with pypdf. If a template has
no blank PDF, a plain letter-size page is generated so output still works.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter  # noqa: E402  (lightweight)


def _build_overlay(field_values: dict, fields: list[dict], page_size,
                   font: str = "Helvetica", font_size: int = 10) -> bytes:
    """Render an overlay PDF (in memory) with field text at field coords."""
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=page_size)
    pdf.setFont(font, font_size)

    # Group fields by page index so multi-page templates work.
    max_page = max((f.get("page", 0) for f in fields), default=0)
    for page_index in range(max_page + 1):
        for field in fields:
            if field.get("page", 0) != page_index:
                continue
            value = field_values.get(field.get("name"))
            if not value:
                continue
            pdf.drawString(float(field.get("x", 0)), float(field.get("y", 0)),
                           str(value))
        pdf.showPage()
        pdf.setFont(font, font_size)
    pdf.save()
    return buf.getvalue()


def fill_pdf(template: dict, field_values: dict, out_path: str | Path,
             base_dir: Path | None = None) -> Path:
    """Produce a filled PDF for a form template and return its path.

    ``template`` is a field-map dict (see templates.py). If it references a
    blank ``pdf_template``, the overlay is merged onto it; otherwise the
    overlay itself is the output.
    """
    import io

    from pypdf import PdfReader, PdfWriter

    fields = template.get("fields", [])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    template_pdf = template.get("pdf_template")
    if template_pdf and base_dir is not None:
        template_pdf = (base_dir / template_pdf) if not Path(template_pdf).is_absolute() else Path(template_pdf)

    if template_pdf and Path(template_pdf).exists():
        base = PdfReader(str(template_pdf))
        page_size = (float(base.pages[0].mediabox.width),
                     float(base.pages[0].mediabox.height))
        overlay_bytes = _build_overlay(field_values, fields, page_size)
        overlay = PdfReader(io.BytesIO(overlay_bytes))
        writer = PdfWriter()
        for i, page in enumerate(base.pages):
            if i < len(overlay.pages):
                page.merge_page(overlay.pages[i])
            writer.add_page(page)
        with open(out_path, "wb") as fh:
            writer.write(fh)
    else:
        # No blank template — the overlay alone is the output.
        overlay_bytes = _build_overlay(field_values, fields, letter)
        out_path.write_bytes(overlay_bytes)

    return out_path
