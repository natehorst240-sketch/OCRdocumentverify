"""Extract scheduled-inspection tables from OEM maintenance manuals.

Chapter 4 (Airworthiness Limitations) and Chapter 5 (Time Limits / Scheduled
Maintenance) are tabular. For digital PDFs, pdfplumber pulls the tables out
directly — deterministic, no LLM, no truncation. The user reviews/edits the
rows before they are saved as requirements, so heuristic column-matching only
needs to get close.
"""

from pathlib import Path

# Candidate header substrings (lowercased) -> internal requirement field.
# Order matters: description is matched before doc_number so a "Task
# Description" column isn't grabbed by an id alias.
COLUMN_ALIASES = {
    "description": ["description", "component", "nomenclature", "inspection",
                    "check", "maintenance task", "work scope", "requirement"],
    "doc_number": ["task no", "task number", "task id", "item no",
                   "item number", "part number", "part no", "mpd item",
                   "amp task", "ata", "ref no", "reference", "item", "ref",
                   "p/n"],
    "interval": ["interval", "threshold", "repeat", "frequency", "hours",
                 "hrs", "cycles", "landings", "calendar", "months", "years",
                 "life", "limit", "due", "fh", "fc", "tbo"],
    "applicability": ["applicability", "effectivity", "zone", "model",
                      "remarks", "notes", "applic", "note"],
}


def _map_columns(header: list) -> dict:
    """Map each internal field to a column index from a header row.

    A column is used at most once, and fields are matched in COLUMN_ALIASES
    order so more specific columns win.
    """
    cleaned = [str(h or "").strip().lower() for h in header]
    used: set[int] = set()
    col_for: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for idx, text in enumerate(cleaned):
            if idx in used or not text:
                continue
            if any(alias in text for alias in aliases):
                col_for[field] = idx
                used.add(idx)
                break
    return col_for


def _rows_from_table(table: list, page: int) -> list[dict]:
    """Convert one extracted table into requirement-shaped row dicts.

    Tables without a recognizable description column are skipped (they are
    almost always something other than an inspection schedule).
    """
    if not table or len(table) < 2:
        return []
    col_for = _map_columns(table[0])
    if "description" not in col_for:
        return []

    def cell(raw, field):
        idx = col_for.get(field)
        if idx is None or idx >= len(raw):
            return None
        val = raw[idx]
        if val is None:
            return None
        # pdfplumber leaves newlines inside wrapped cells; flatten them.
        text = " ".join(str(val).split())
        return text or None

    rows = []
    for raw in table[1:]:
        description = cell(raw, "description")
        if not description:
            continue
        rows.append({
            "doc_number": cell(raw, "doc_number"),
            "description": description,
            "interval": cell(raw, "interval"),
            "applicability": cell(raw, "applicability"),
            "source_page": page,
        })
    return rows


def parse_inspections(pdf_path: str | Path) -> list[dict]:
    """Extract all inspection-schedule rows from a maintenance-manual PDF."""
    import pdfplumber

    rows: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                rows.extend(_rows_from_table(table, page_no))
    return rows
