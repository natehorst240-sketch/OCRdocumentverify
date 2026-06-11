"""Business-hours and single-user gating for the hosted instance.

Both are opt-in via environment variables so local development is unaffected.
Enable them on the hosted (Cloudflare Tunnel) instance:

    SINGLE_USER=1
    BUSINESS_HOURS=1  BIZ_START=8  BIZ_END=17  BIZ_DAYS=0-4   # Mon-Fri 8-5

Times use the host machine's local clock, so set the server timezone correctly.
"""

import datetime
import json
import os
import time
from pathlib import Path

LOCK_FILE = Path(__file__).resolve().parent / ".session_lock.json"
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "120"))  # seconds

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _enabled(var: str) -> bool:
    return os.environ.get(var, "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_days(spec: str) -> set[int]:
    """Parse '0-4' or '0,1,2' (Mon=0) into a set of weekday numbers."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            if lo.isdigit() and hi.isdigit():
                out.update(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            out.add(int(part))
    return out or set(range(5))


def business_open() -> tuple[bool, str]:
    """Return (is_open, human-readable schedule). Always open if not enabled."""
    if not _enabled("BUSINESS_HOURS"):
        return True, ""
    start = int(os.environ.get("BIZ_START", "8"))
    end = int(os.environ.get("BIZ_END", "17"))
    days = _parse_days(os.environ.get("BIZ_DAYS", "0-4"))
    now = datetime.datetime.now()
    is_open = now.weekday() in days and start <= now.hour < end
    day_label = "".join(d for i, d in enumerate(_DAY_NAMES) if i in days) \
        if len(days) > 3 else "/".join(_DAY_NAMES[i] for i in sorted(days))
    schedule = f"{start:02d}:00–{end:02d}:00, {day_label}"
    return is_open, schedule


def acquire_single_user(session_id: str) -> bool:
    """Claim the single-user slot. Returns False if someone else holds it.

    The lock is held by whoever last refreshed it within SESSION_TIMEOUT; an
    idle/disconnected session releases it automatically once it goes stale.
    """
    if not _enabled("SINGLE_USER"):
        return True
    now = time.time()
    try:
        lock = json.loads(LOCK_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        lock = None
    if (lock and lock.get("owner") != session_id
            and now - lock.get("ts", 0) < SESSION_TIMEOUT):
        return False
    try:
        LOCK_FILE.write_text(json.dumps({"owner": session_id, "ts": now}))
    except OSError:
        pass
    return True
