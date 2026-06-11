"""Pull installed part numbers from a scanned equipment list / Chart A.

Scanned paper is the hardest input: OCR loses table structure, so this is a
best-effort candidate extractor — it surfaces part-number-like tokens from the
OCR text for the user to review and correct, rather than pretending to parse a
clean table. The raw OCR text is always kept so nothing is silently dropped.
"""

import re
from pathlib import Path

# Two complementary shapes of part number:
#   dashed:        109-0810-05, EC135-FK-01
#   alphanumeric:  3G2820V00251 (a letter and a digit, length >= 5)
_DASHED = re.compile(r"\b[0-9A-Z]{2,}-[0-9A-Z][0-9A-Z-]*\b")
_ALNUM = re.compile(r"\b(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*[0-9])[0-9A-Z]{5,}\b")

_DATE = re.compile(r"^\d{1,4}-\d{1,2}-\d{1,4}$")     # 2026-01-15, 1-2-26
_NOISE = {"QTY", "PART", "PN", "NO", "REF", "ATA", "REV", "ITEM", "ASSY"}


def extract_candidates(text: str | None) -> list[str]:
    """Return candidate part-number tokens from OCR text, in order, deduped."""
    upper = (text or "").upper()
    seen: set[str] = set()
    out: list[str] = []
    for pattern in (_DASHED, _ALNUM):
        for match in pattern.finditer(upper):
            token = match.group(0)
            if token in seen or token in _NOISE:
                continue
            if _DATE.match(token):
                continue
            if not any(c.isdigit() for c in token):  # need at least one digit
                continue
            seen.add(token)
            out.append(token)
    return out


def ocr_equipment_list(path: str | Path, work_dir: str | Path) -> tuple[str, list[str]]:
    """OCR a scanned equipment list and return (full_text, candidate_parts)."""
    import ocr

    path = Path(path)
    if path.suffix.lower() == ".pdf":
        images = ocr.pdf_to_images(path, work_dir)
    else:
        images = [path]
    texts = [ocr.ocr_page(img) for img in images]
    full_text = "\n".join(texts)
    return full_text, extract_candidates(full_text)
