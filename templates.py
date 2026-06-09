"""Field-map template store.

A template is a JSON file in ``/templates`` describing one form type: its
field names and the (x, y) coordinates on the output PDF where each field's
text should be placed. Shared by form reconstruction (Sprint 3) and the
template builder (Sprint 5).

Template schema::

    {
      "form_type": "AW109SP Work Order",
      "aircraft_type": "AW109SP",
      "pdf_template": "templates/aw109sp_workorder.pdf",   # optional blank PDF
      "fields": [
        {"name": "work_order_no", "x": 430, "y": 712, "page": 0},
        ...
      ]
    }

Coordinates are PDF points with origin at the bottom-left (reportlab convention).
"""

import json
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def slugify(name: str) -> str:
    """Turn a form-type name into a safe filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "form"


def template_path(form_type: str) -> Path:
    return TEMPLATES_DIR / f"{slugify(form_type)}.json"


def list_templates() -> list[dict]:
    """Return metadata for every saved template."""
    TEMPLATES_DIR.mkdir(exist_ok=True)
    out = []
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "form_type": data.get("form_type", path.stem),
            "aircraft_type": data.get("aircraft_type"),
            "field_count": len(data.get("fields", [])),
            "path": str(path),
        })
    return out


def load_template(form_type: str) -> dict | None:
    """Load a template by form-type name, or None if not found."""
    path = template_path(form_type)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_template(template: dict) -> Path:
    """Write a template to disk, keyed by its form_type. Returns the path."""
    form_type = template.get("form_type")
    if not form_type:
        raise ValueError("template must include a 'form_type'")
    TEMPLATES_DIR.mkdir(exist_ok=True)
    path = template_path(form_type)
    template.setdefault("fields", [])
    path.write_text(json.dumps(template, indent=2))
    return path


def field_names(template: dict) -> list[str]:
    return [f["name"] for f in template.get("fields", []) if f.get("name")]


def delete_template(form_type: str) -> int:
    """Delete a template and its sibling files (PDF, corrections). Returns count."""
    slug = slugify(form_type)
    removed = 0
    for path in TEMPLATES_DIR.glob(f"{slug}.*"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
