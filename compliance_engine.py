"""Compliance matching and Veryon comparison (US 4.1, 4.2).

Stage 1 is a cheap, deterministic keyword pre-filter that narrows each
requirement to a few candidate record pages. Stage 2 asks Qwen to confirm
whether a candidate page actually shows compliance and to pull the date/hours.
If Qwen is unavailable, the engine degrades to keyword-only scoring and flags
everything plausible for manual review rather than guessing "complied".
"""

import re

import database
import qwen_client

# Confidence thresholds for classifying a requirement's status.
HIGH_CONFIDENCE = 0.75
LOW_CONFIDENCE = 0.40
MAX_CANDIDATES = 5  # cap Qwen calls per requirement

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "per", "shall",
    "must", "all", "any", "are", "was", "has", "have", "not", "inspect",
    "inspection", "complete", "completed", "due", "ref", "rev",
}

_CONFIRM_SYSTEM = (
    "You determine whether a maintenance record page shows compliance with a "
    "specific airworthiness requirement. Respond only with JSON."
)


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, minus short words and stopwords."""
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def overlap_score(a: str, b: str) -> float:
    """Jaccard-style overlap of the token sets of two strings (0..1)."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def prefilter(requirement_text: str, pages: list, top_n: int = MAX_CANDIDATES,
              min_score: float = 0.04) -> list[tuple]:
    """Rank candidate pages for a requirement by keyword overlap (US 4.1)."""
    scored = []
    for page in pages:
        score = overlap_score(requirement_text, page["extracted_text"] or "")
        if score >= min_score:
            scored.append((score, page))
    scored.sort(key=lambda s: s[0], reverse=True)
    return scored[:top_n]


def confirm_match(requirement: dict, page_text: str) -> dict:
    """Ask Qwen whether a page satisfies a requirement.

    Returns ``{"complied": bool|None, "confidence": float, "compliance_date",
    "compliance_hours", "notes"}``. ``complied`` is ``None`` when Qwen is
    unavailable so the caller can fall back to keyword scoring.
    """
    prompt = (
        "Does the maintenance RECORD below show compliance with the "
        "REQUIREMENT? Extract the compliance date and hours if present.\n\n"
        f"REQUIREMENT:\n{requirement.get('doc_number') or ''} "
        f"{requirement.get('description') or ''}\n"
        f"Action: {requirement.get('required_action') or ''}\n\n"
        f"RECORD:\n\"\"\"\n{(page_text or '')[:4000]}\n\"\"\"\n\n"
        "Return JSON: {\"complied\": boolean, \"confidence\": number 0-1, "
        "\"compliance_date\": string|null, \"compliance_hours\": string|null, "
        "\"notes\": string}."
    )
    try:
        result = qwen_client.generate_json(prompt, system=_CONFIRM_SYSTEM)
    except qwen_client.QwenError:
        return {"complied": None, "confidence": 0.0, "compliance_date": None,
                "compliance_hours": None, "notes": "LLM unavailable"}
    if not isinstance(result, dict):
        return {"complied": None, "confidence": 0.0, "compliance_date": None,
                "compliance_hours": None, "notes": "bad LLM response"}
    try:
        conf = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    # Preserve None when the model omits "complied" so run_matching can fall
    # back to keyword scoring rather than treating it as a definite "no".
    complied = result.get("complied")
    return {
        "complied": None if complied is None else bool(complied),
        "confidence": conf,
        "compliance_date": result.get("compliance_date"),
        "compliance_hours": result.get("compliance_hours"),
        "notes": result.get("notes"),
    }


def _classify(complied, confidence: float) -> str:
    if complied and confidence >= HIGH_CONFIDENCE:
        return "complied"
    if confidence >= LOW_CONFIDENCE:
        return "needs_review"
    return "outstanding"


def run_matching(db_path=database.DB_PATH, use_llm: bool | None = None) -> dict:
    """Match every requirement against record pages and store results.

    Clears prior results, then writes exactly one compliance row per
    requirement. Returns a count summary by status. ``use_llm`` defaults to the
    deployment's LLM setting (off → keyword-only, conservative).
    """
    if use_llm is None:
        use_llm = qwen_client.llm_enabled()
    requirements = database.fetch_all("requirements", db_path)
    pages = [p for p in database.fetch_all("pages", db_path)
             if (p["extracted_text"] or "").strip()]
    database.clear_table("compliance", db_path)

    summary = {"complied": 0, "needs_review": 0, "outstanding": 0}
    for req in requirements:
        req_text = " ".join(filter(None, [
            req["doc_number"], req["description"], req["required_action"]]))
        candidates = prefilter(req_text, pages)

        best = None  # (page_row, result_dict)
        for score, page in candidates:
            if use_llm:
                result = confirm_match(dict(req), page["extracted_text"])
            else:
                result = {"complied": None, "confidence": 0.0}
            # Fall back to keyword score when the LLM can't confirm.
            if result["complied"] is None:
                result = {"complied": None, "confidence": score,
                          "compliance_date": None, "compliance_hours": None,
                          "notes": "keyword match only"}
            if best is None or result["confidence"] > best[1]["confidence"]:
                best = (page, result)

        if best is None:
            database.add_compliance(req["id"], None, "outstanding", 0.0,
                                    db_path=db_path)
            summary["outstanding"] += 1
            continue

        page, result = best
        status = _classify(result["complied"], result["confidence"])
        # Keyword-only matches can never be auto-confirmed.
        if result["complied"] is None and status == "complied":
            status = "needs_review"
        database.add_compliance(
            req["id"], page["id"], status, result["confidence"],
            result.get("compliance_date"), result.get("compliance_hours"),
            result.get("notes"), db_path=db_path)
        summary[status] += 1

    return summary


# --- US 4.2: Veryon comparison ----------------------------------------------

def compare_to_veryon(db_path=database.DB_PATH,
                      match_threshold: float = 0.12) -> dict:
    """Diff Veryon tasks against complied paper records.

    Returns three lists:
      matched           - requirement complied in paper AND present in Veryon
      missing_in_veryon - complied in paper but no Veryon task (enter these)
      missing_in_records- Veryon task with no complied paper record
    """
    report = database.compliance_report(db_path)
    veryon = database.fetch_all("veryon_tasks", db_path)

    complied = [r for r in report if r["status"] in ("complied", "needs_review")]
    used_veryon: set[int] = set()

    matched, missing_in_veryon = [], []
    for req in complied:
        req_text = " ".join(filter(None, [req["doc_number"], req["description"]]))
        best_task, best_score = None, 0.0
        for task in veryon:
            task_text = " ".join(filter(None, [task["task_code"],
                                               task["description"]]))
            score = overlap_score(req_text, task_text)
            if score > best_score:
                best_task, best_score = task, score
        if best_task is not None and best_score >= match_threshold:
            used_veryon.add(best_task["id"])
            matched.append({
                "doc_number": req["doc_number"],
                "description": req["description"],
                "veryon_task": best_task["task_code"],
                "score": round(best_score, 2),
            })
        else:
            missing_in_veryon.append({
                "doc_number": req["doc_number"],
                "description": req["description"],
                "record_source": req["record_source"],
                "page_number": req["page_number"],
            })

    missing_in_records = [
        {"task_code": t["task_code"], "description": t["description"],
         "interval": t["interval"]}
        for t in veryon if t["id"] not in used_veryon
    ]

    return {
        "matched": matched,
        "missing_in_veryon": missing_in_veryon,
        "missing_in_records": missing_in_records,
    }
