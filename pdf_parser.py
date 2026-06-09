"""Parse regulatory documents (AD / ASB / ICA) into structured requirements.

Two stages:
  1. ``extract_text`` pulls clean text out of the PDF with pdfplumber.
  2. ``extract_requirements`` asks Qwen to normalize that text into the
     structured fields the compliance engine needs (US 2.3).
"""

from pathlib import Path

import qwen_client

_SYSTEM = (
    "You are an aircraft maintenance compliance assistant. You extract "
    "structured airworthiness requirements from regulatory documents "
    "(Airworthiness Directives, Alert Service Bulletins, Instructions for "
    "Continued Airworthiness). Respond only with JSON."
)

_PROMPT = """Extract every distinct requirement from the document text below.

Return a JSON array. Each element must be an object with these keys:
  "doc_number"      - the document/reference number (e.g. "AD 2021-12-05"), or null
  "req_type"        - one of "AD", "ASB", "ICA", or null if unknown
  "description"     - a concise description of the required action
  "interval"        - the compliance interval (e.g. "every 100 hrs", "one-time"), or null
  "applicability"   - the affected aircraft/part/serial range, or null
  "required_action" - the specific action to perform, or null

Return [] if no requirements are present. Do not invent values.

DOCUMENT TEXT:
\"\"\"
{text}
\"\"\""""


def extract_text(pdf_path: str | Path) -> str:
    """Extract structured text from a requirement PDF with pdfplumber."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n".join(parts)


def extract_requirements(text: str, max_chars: int = 12000) -> list[dict]:
    """Use Qwen to normalize requirement text into structured records.

    Long documents are truncated to ``max_chars`` to stay within the model's
    context; callers can chunk upstream if a document is very large.
    """
    text = (text or "").strip()
    if not text or not qwen_client.llm_enabled():
        return []  # no-LLM mode: requirements are entered manually

    result = qwen_client.generate_json(
        _PROMPT.format(text=text[:max_chars]), system=_SYSTEM
    )
    if isinstance(result, dict):
        result = [result]
    # Keep only well-formed dict rows.
    return [r for r in result if isinstance(r, dict)]


def parse_requirement_pdf(pdf_path: str | Path) -> list[dict]:
    """Convenience: PDF path -> list of structured requirement dicts."""
    return extract_requirements(extract_text(pdf_path))
