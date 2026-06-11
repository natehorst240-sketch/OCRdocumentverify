"""Extract scheduled-inspection tasks from OEM maintenance manuals.

Two formats are handled:

  * **Task blocks** (Airbus S1000D MSM / EC135 etc.) — each task is a
    multi-line text block: task number, description, a documentation +
    interval + margin line, then EFFECTIVITY / "Only applicable" applicability
    lines. pdfplumber isolates each block into one table cell, which we parse
    with line heuristics. This captures the applicability conditions verbatim.

  * **Ruled column tables** (other OEMs) — a header row with separated columns.
    Used as a fallback when no task blocks are found.

Deterministic — no OCR or LLM. The user reviews/edits rows before saving.
"""

import re
from pathlib import Path

# --- Task-block parsing (primary) -------------------------------------------

# Airbus task id, e.g. 21/50/00/000/000/006
_TASK_RE = re.compile(r"\b\d{2}/\d{2}/\d{2}/\d{3}/\d{3}/\d{3}\b")
_UNITS = r"FH|OPH|FC|LDG|CYC|MO|YR|Y|M|H|DAYS?|MONTHS?|YEARS?"
_INTERVAL_RE = re.compile(rf"\b(\d+(?:\.\d+)?)\s*({_UNITS})\b")
_DOC_REF_RE = re.compile(r"\b(?:AMM|MSM|MTC|SB|ASB|MET|WDM|SIL|MMEL)\b", re.I)
_EFF_RE = re.compile(
    r"(effectivity|only applicable|applicable to|optional|if .*installed|p/n)",
    re.I)
_STATUS = {"changed", "unchanged", "new", "deleted", "maintenance task",
           "di", "vc", "tso", "tsn / tso", "tsn/tso"}


def _looks_like_block(cell: str | None) -> bool:
    return bool(cell and "\n" in cell
                and (_INTERVAL_RE.search(cell) or _TASK_RE.search(cell)))


def _parse_block(block: str, page: int) -> dict | None:
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if not lines:
        return None
    task_match = _TASK_RE.search(block)
    task = task_match.group(0) if task_match else lines[0]
    start = next((i for i, ln in enumerate(lines) if task in ln), 0)

    # The documentation + interval line is the first line carrying interval
    # units or a manual reference after the task line.
    doc_idx = None
    for i in range(start + 1, len(lines)):
        if _INTERVAL_RE.search(lines[i]) or _DOC_REF_RE.search(lines[i]):
            doc_idx = i
            break

    description = " ".join(
        lines[start + 1:doc_idx]).strip() if doc_idx else (
        lines[start + 1] if start + 1 < len(lines) else "")

    interval = None
    if doc_idx is not None:
        ivs = _INTERVAL_RE.findall(lines[doc_idx])
        if ivs:  # first match = interval, second = margin
            interval = " / ".join(f"{n} {u}" for n, u in ivs[:2])

    applic = [ln for ln in lines
              if _EFF_RE.search(ln) and ln.lower() not in _STATUS]
    return {
        "doc_number": task,
        "description": description or None,
        "interval": interval,
        "applicability": "; ".join(applic) or None,
        "source_page": page,
    }


# --- Ruled-table parsing (fallback) -----------------------------------------

COLUMN_ALIASES = {
    "description": ["description/remarks", "description", "remarks",
                    "component", "nomenclature", "inspection", "check",
                    "maintenance task", "task description"],
    "doc_number": ["task number", "task no", "item no", "item number",
                   "part number", "part no", "ata", "ref", "item"],
    "interval": ["interval", "threshold", "initial", "margin", "frequency",
                 "hours", "cycles", "calendar", "months", "years", "life",
                 "limit", "tbo"],
    "applicability": ["applicability", "effectivity", "zone", "model",
                      "config"],
}
_HEADER_HINTS = ("task", "description", "interval", "remarks", "item",
                 "component", "life", "limit", "part", "effectivity")


def _map_columns(header: list) -> dict:
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


def _rows_from_columns(table: list, page: int) -> list[dict]:
    if not table or len(table) < 2:
        return []
    header_idx = next(
        (i for i, row in enumerate(table[:6])
         if sum(1 for c in row if str(c or "").strip()) >= 2
         and sum(1 for h in _HEADER_HINTS
                 if h in " ".join(str(c or "").lower() for c in row)) >= 2),
        None)
    if header_idx is None:
        return []
    col_for = _map_columns(table[header_idx])
    if "description" not in col_for:
        return []

    def cell(raw, field):
        idx = col_for.get(field)
        if idx is None or idx >= len(raw) or raw[idx] is None:
            return None
        return " ".join(str(raw[idx]).split()) or None

    rows = []
    for raw in table[header_idx + 1:]:
        desc = cell(raw, "description")
        if not desc:
            continue
        rows.append({"doc_number": cell(raw, "doc_number"), "description": desc,
                     "interval": cell(raw, "interval"),
                     "applicability": cell(raw, "applicability"),
                     "source_page": page})
    return rows


def parse_inspections(pdf_path: str | Path) -> list[dict]:
    """Extract inspection-schedule rows from a maintenance-manual PDF."""
    import pdfplumber

    rows: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []

            # Primary: task blocks (one task per cell).
            block_rows: list[dict] = []
            for table in tables:
                for raw in table:
                    cell = raw[0] if raw else None
                    if not cell or ("Task Number" in cell
                                    and "Description" in cell):
                        continue
                    if _looks_like_block(cell):
                        parsed = _parse_block(cell, page_no)
                        if parsed:
                            block_rows.append(parsed)

            if block_rows:
                rows.extend(block_rows)
                continue

            # Fallback: ruled column tables (other OEM formats).
            for table in tables:
                rows.extend(_rows_from_columns(table, page_no))
    return rows
