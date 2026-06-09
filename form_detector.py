"""Form-type classification (US 3.1) and box detection/OCR (US 3.2).

Box detection is pure OpenCV — no LLM. Form-type classification asks Qwen to
pick from the set of known template form types, returning a confidence the UI
shows alongside a manual-override control.
"""

from pathlib import Path

import ocr
import qwen_client
import templates

_CLASSIFY_SYSTEM = (
    "You classify scanned aircraft maintenance forms by type. "
    "Respond only with JSON."
)


def classify_form_type(text: str, known_types: list[str] | None = None) -> dict:
    """Classify a form from its OCR text.

    Returns ``{"form_type": str, "confidence": float}``. ``known_types`` are
    the form types we already have templates for; the model is told to prefer
    them but may answer "Unknown" so the UI can flag it for manual mapping.
    """
    if not qwen_client.llm_enabled():
        return {"form_type": "Unknown", "confidence": 0.0}  # user picks manually
    known_types = known_types or [t["form_type"] for t in templates.list_templates()]
    options = ", ".join(known_types) if known_types else "(none defined yet)"
    prompt = (
        "Classify the maintenance form below. Prefer one of the known form "
        f"types if it matches: {options}. If none fit, use \"Unknown\".\n\n"
        "Return JSON: {\"form_type\": string, \"confidence\": number between "
        "0 and 1}.\n\nFORM TEXT:\n\"\"\"\n" + (text or "")[:6000] + "\n\"\"\""
    )
    try:
        result = qwen_client.generate_json(prompt, system=_CLASSIFY_SYSTEM)
    except qwen_client.QwenError:
        return {"form_type": "Unknown", "confidence": 0.0}
    if not isinstance(result, dict):
        return {"form_type": "Unknown", "confidence": 0.0}
    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "form_type": result.get("form_type") or "Unknown",
        "confidence": max(0.0, min(1.0, confidence)),
    }


def detect_boxes(image_path: str | Path, min_area: int = 1500,
                 min_aspect: float = 1.2) -> list[dict]:
    """Find rectangular field boxes via OpenCV contour detection (US 3.2).

    Returns a list of ``{"id", "x", "y", "w", "h"}`` sorted top-to-bottom,
    left-to-right. Filters tiny specks and near-square noise by area/aspect.
    """
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
    )[1]

    # Connect strokes into box outlines so closed rectangles are found.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(thresh, kernel, iterations=1)

    contours, _ = cv2.findContours(
        dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        aspect = w / h if h else 0
        if area >= min_area and aspect >= min_aspect:
            boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})

    # Sort row-major (group by ~row then by x) and assign stable ids.
    boxes.sort(key=lambda b: (round(b["y"] / 25), b["x"]))
    for i, box in enumerate(boxes, start=1):
        box["id"] = i
    return boxes


def ocr_boxes(image_path: str | Path, boxes: list[dict]) -> list[dict]:
    """OCR each detected box individually and attach its text (US 3.2)."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    enriched = []
    for box in boxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        crop = image[y:y + h, x:x + w]
        try:
            text = ocr.ocr_image(crop).strip()
        except Exception:
            text = ""
        enriched.append({**box, "text": text})
    return enriched


def annotate_image(image_path: str | Path, boxes: list[dict],
                   out_path: str | Path) -> Path:
    """Draw detected boxes with their ids and save an annotated image."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    for box in boxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 180, 0), 2)
        cv2.putText(image, str(box.get("id", "")), (x + 3, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), image)
    return out_path
