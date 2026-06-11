"""Decide whether a generic manual inspection applies to a specific tail.

Conservative by policy: an inspection is only marked NOT APPLICABLE when it is
*clearly* excluded (e.g. the aircraft's serial number is provably outside a
stated range). Anything that can't be resolved confidently is left as REVIEW
and still counted as applicable, so a required inspection is never silently
dropped.

Deterministic only — no LLM — so it runs identically on the no-LLM N100. An
optional LLM assist for REVIEW cases can be layered on later.
"""

import re

APPLIES = "applies"
NOT_APPLICABLE = "not_applicable"
REVIEW = "review"

# Applicability text that means "everything" -> always applies.
_UNIVERSAL = {"", "all", "n/a", "na", "none", "all aircraft", "all s/n",
              "all serials", "as required", "all models"}

# Words that signal a conditional (optional equipment / part dependent).
_CONDITIONAL = ("if ", "when ", "equipped", "installed", "fitted",
                "incorporating", "with the", "optional", "provided with")


def _lines(text: str | None) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _serial_int(serial: str | None) -> int | None:
    """Extract the numeric portion of a serial number, if any."""
    if not serial:
        return None
    digits = re.findall(r"\d+", serial)
    return int(digits[-1]) if digits else None


def _significant_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _serial_decision(applic: str, aircraft_sn: int | None):
    """Return APPLIES/NOT_APPLICABLE/None from a serial-number condition.

    None means 'no serial condition recognized' (caller continues checking).
    Only a confident, in/out-of-range numeric comparison yields a decision.
    """
    low = applic.lower()
    if not re.search(r"s/?n|msn|serial", low):
        return None
    if aircraft_sn is None:
        return REVIEW  # there's a serial condition but we can't compare

    # Range: "0001-0100", "0001 to 0100", "0001 thru 0100"
    rng = re.search(r"(\d{1,7})\s*(?:-|–|to|thru|through)\s*(\d{1,7})", low)
    if rng:
        lo, hi = int(rng.group(1)), int(rng.group(2))
        return APPLIES if lo <= aircraft_sn <= hi else NOT_APPLICABLE

    # Open-ended lower bound: "0123 and subsequent / and up / and on / later"
    up = re.search(r"(\d{1,7})\s*(?:and\s+)?(?:subsequent|sub|up|on|later|after)",
                   low)
    if up:
        return APPLIES if aircraft_sn >= int(up.group(1)) else NOT_APPLICABLE

    # Open-ended upper bound: "prior to / before / up to 0123"
    dn = re.search(r"(?:prior to|before|up to|and prior)\s*(?:s/?n\s*)?(\d{1,7})",
                   low)
    if dn:
        return APPLIES if aircraft_sn <= int(dn.group(1)) else NOT_APPLICABLE

    # Explicit list of serials: applies only if the tail is in it.
    serials = [int(s) for s in re.findall(r"\b(\d{3,7})\b", low)]
    if serials:
        return APPLIES if aircraft_sn in serials else REVIEW
    return REVIEW


def evaluate(applicability: str | None, aircraft: dict | None) -> tuple[str, str]:
    """Return (status, reason) for one requirement against an aircraft config."""
    applic = " ".join((applicability or "").split())
    if applic.lower() in _UNIVERSAL:
        return APPLIES, "applies to all"
    if aircraft is None:
        return REVIEW, "no aircraft profile selected"

    # 1) Serial-number conditions (the one case we'll confidently exclude on).
    serial_call = _serial_decision(applic, _serial_int(aircraft.get("serial_number")))
    if serial_call == NOT_APPLICABLE:
        return NOT_APPLICABLE, f"serial {aircraft.get('serial_number')} outside range"
    if serial_call == APPLIES:
        return APPLIES, "serial in range"

    # 2) Optional-equipment / part conditions matched against the profile.
    config_text = " ".join(_lines(aircraft.get("optional_equipment")) +
                           _lines(aircraft.get("installed_parts"))).lower()
    config_tokens = _significant_tokens(config_text)
    applic_tokens = _significant_tokens(applic)
    if config_tokens & applic_tokens:
        return APPLIES, "matches installed equipment/part"

    # Conditional wording but nothing in the profile matched -> stay cautious.
    if any(word in applic.lower() for word in _CONDITIONAL):
        return REVIEW, "condition not found in aircraft profile — confirm"

    return REVIEW, "could not resolve applicability"


def evaluate_all(requirements: list, aircraft: dict | None) -> dict:
    """Map requirement id -> (status, reason) for a set of requirement rows."""
    out = {}
    for req in requirements:
        out[req["id"]] = evaluate(req["applicability"], aircraft)
    return out
