"""Import a Veryon Excel export into the veryon_tasks table (US 2.4).

Veryon exports vary between operators, so column names are matched loosely
against the internal schema rather than assumed to be exact.
"""

from pathlib import Path

import database

# Map internal field -> candidate header substrings (lowercased, matched loosely).
COLUMN_ALIASES = {
    "task_code": ["task code", "task no", "task number", "item", "ata", "code"],
    "description": ["description", "task description", "title", "name"],
    "interval": ["interval", "frequency", "due", "recurrence"],
    "last_compliance_date": ["last compliance date", "last done", "compliance date",
                             "last accomplished", "date"],
    "last_compliance_hours": ["last compliance hours", "hours", "tsn", "tso",
                              "last hours"],
}


def _match_columns(columns: list[str]) -> dict[str, str | None]:
    """Map each internal field to the best-matching source column header."""
    lowered = {col: str(col).strip().lower() for col in columns}
    mapping: dict[str, str | None] = {}
    for field, aliases in COLUMN_ALIASES.items():
        match = None
        for alias in aliases:
            for col, low in lowered.items():
                if alias in low:
                    match = col
                    break
            if match:
                break
        mapping[field] = match
    return mapping


def import_excel(xlsx_path: str | Path, db_path: Path = database.DB_PATH) -> dict:
    """Load a Veryon export and insert rows into veryon_tasks.

    Returns a summary dict with the imported count and resolved column map
    so the UI can show what was loaded (US 2.4 acceptance criteria).
    """
    import pandas as pd

    xlsx_path = Path(xlsx_path)
    df = pd.read_excel(xlsx_path)
    mapping = _match_columns(list(df.columns))

    def value(row, field):
        col = mapping.get(field)
        if not col:
            return None
        val = row.get(col)
        if pd.isna(val):
            return None
        # Render dates as date-only strings, not "2024-01-15 00:00:00".
        if isinstance(val, pd.Timestamp):
            return val.strftime("%Y-%m-%d")
        return str(val).strip()

    imported = 0
    for _, row in df.iterrows():
        database.add_veryon_task(
            task_code=value(row, "task_code"),
            description=value(row, "description"),
            interval=value(row, "interval"),
            last_compliance_date=value(row, "last_compliance_date"),
            last_compliance_hours=value(row, "last_compliance_hours"),
            source_file=xlsx_path.name,
            db_path=db_path,
        )
        imported += 1

    return {
        "imported": imported,
        "total_rows": len(df),
        "column_map": mapping,
        "source_columns": list(df.columns),
    }
