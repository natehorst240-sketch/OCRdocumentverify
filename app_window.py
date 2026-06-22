"""Launch the app in its own chromeless window, like a desktop application.

Instead of opening a browser tab with tabs and an address bar, this starts the
Streamlit server headless (so it doesn't pop a tab) and opens the app in
Edge/Chrome "app mode" (--app), which is a clean standalone window. Closing that
window quits the whole app: we wait on the dedicated browser process and then
shut the server down.

No extra dependencies — everything here is the Python standard library plus the
Streamlit that already ships with the app. If no Chromium-based browser is
found, it falls back to opening the default browser and leaves the server
running until this process is stopped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

HOST = "localhost"
PORT = int(os.environ.get("APP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"
APP_DIR = Path(__file__).resolve().parent


def _find_browser() -> str | None:
    """Locate Edge or Chrome (they both support --app windows)."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        os.path.join(pfx86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pfx86, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _wait_until_ready(timeout: float = 60.0) -> bool:
    """Poll the server until it answers, or give up after `timeout` seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _start_server() -> subprocess.Popen:
    """Start Streamlit headless so it doesn't open its own browser tab."""
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        f"--server.address={HOST}",
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",   # hide the dev menu for an app-like look
    ]
    return subprocess.Popen(cmd, cwd=str(APP_DIR))


def main() -> int:
    print("Starting the app… this window can be minimized.")
    server = _start_server()

    if not _wait_until_ready():
        print("The app server did not start in time.")
        server.terminate()
        return 1

    browser = _find_browser()
    if browser is None:
        # No Edge/Chrome: fall back to a normal browser tab and keep running.
        print(f"Opening {URL} in your default browser…")
        webbrowser.open(URL)
        try:
            server.wait()
        except KeyboardInterrupt:
            server.terminate()
        return 0

    # A dedicated profile dir forces a fresh browser instance whose process we
    # can wait on, so closing the window reliably signals "quit the app".
    profile = tempfile.mkdtemp(prefix="aviation_app_")
    args = [
        browser,
        f"--app={URL}",
        f"--user-data-dir={profile}",
        "--window-size=1280,840",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    print("Opening the app window… close it to quit.")
    window = subprocess.Popen(args)

    try:
        window.wait()          # blocks until the user closes the app window
    except KeyboardInterrupt:
        pass
    finally:
        # Window closed (or Ctrl-C): shut the server down and clean up.
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
