"""Map detected/OCR'd boxes to template field names (US 3.3).

Qwen does the fuzzy matching of box text to the correct field. Corrections the
user makes in the UI are persisted per form type so the same scan maps better
next time.
"""

import json
from pathlib import Path

import qwen_client
import templates

_SYSTEM = (
    "You map text snippets extracted from a scanned form to the correct field "
    "names of a digital template. Respond only with JSON."
)


def _corrections_path(form_type: str) -> Path:
    return templates.TEMPLATES_DIR / f"{templates.slugify(form_type)}.corrections.json"


def load_corrections(form_type: str) -> dict:
    """Return saved {normalized_box_text: field_name} hints for a form type."""
    path = _corrections_path(form_type)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_corrections(form_type: str, mappings: list[dict]) -> Path:
    """Persist user-confirmed mappings as text->field hints (US 3.3)."""
    hints = load_corrections(form_type)
    for m in mappings:
        text = (m.get("text") or "").strip().lower()
        field = m.get("field_name")
        if text and field:
            hints[text] = field
    templates.TEMPLATES_DIR.mkdir(exist_ok=True)
    path = _corrections_path(form_type)
    path.write_text(json.dumps(hints, indent=2))
    return path


def map_boxes_to_fields(boxes: list[dict], template: dict) -> list[dict]:
    """Assign each box to a template field name with a confidence score.

    Applies saved corrections first (confidence 1.0), then asks Qwen for the
    rest. Returns ``[{box_id, text, field_name, confidence}]``.
    """
    fields = templates.field_names(template)
    form_type = template.get("form_type", "")
    hints = load_corrections(form_type)

    resolved: list[dict] = []
    unresolved: list[dict] = []
    for box in boxes:
        text = (box.get("text") or "").strip()
        key = text.lower()
        if key and key in hints and hints[key] in fields:
            resolved.append({
                "box_id": box.get("id"), "text": text,
                "field_name": hints[key], "confidence": 1.0,
            })
        else:
            unresolved.append(box)

    if unresolved and fields:
        resolved.extend(_map_with_qwen(unresolved, fields))
    return sorted(resolved, key=lambda r: (r["box_id"] or 0))


def _map_with_qwen(boxes: list[dict], fields: list[str]) -> list[dict]:
    payload = [{"box_id": b.get("id"), "text": (b.get("text") or "").strip()}
               for b in boxes]
    prompt = (
        "Match each extracted box to the single best field name, or null if "
        "none fits.\n\n"
        f"FIELD NAMES: {json.dumps(fields)}\n\n"
        f"BOXES: {json.dumps(payload)}\n\n"
        "Return a JSON array of "
        "{\"box_id\": int, \"field_name\": string|null, "
        "\"confidence\": number between 0 and 1}."
    )
    try:
        result = qwen_client.generate_json(prompt, system=_SYSTEM)
    except qwen_client.QwenError:
        result = []
    if isinstance(result, dict):
        result = [result]

    by_id = {b.get("id"): (b.get("text") or "").strip() for b in boxes}
    out = []
    for r in result if isinstance(result, list) else []:
        if not isinstance(r, dict):
            continue
        box_id = r.get("box_id")
        if box_id not in by_id:  # ignore boxes we didn't ask about
            continue
        field = r.get("field_name")
        if field not in fields:  # ignore hallucinated field names
            field = None
        try:
            conf = max(0.0, min(1.0, float(r.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        out.append({
            "box_id": box_id, "text": by_id.get(box_id, ""),
            "field_name": field, "confidence": conf if field else 0.0,
        })
    return out


def mappings_to_values(mappings: list[dict]) -> dict:
    """Collapse mappings into {field_name: text} for the PDF writer."""
    values: dict[str, str] = {}
    for m in mappings:
        field = m.get("field_name")
        text = (m.get("text") or "").strip()
        if field and text and field not in values:
            values[field] = text
    return values
