"""Handwriting OCR engine backed by the standalone Go neural network.

The rest of this app already does its job well; the genuinely hard part is
reading *handwritten* logbook entries, which PaddleOCR (tuned for printed text)
struggles with. This module routes that one task to the dependency-free Go
recognizer in ``handwriting/`` — a trained neural net shipped as a single static
binary, no LLM and no Python ML stack required.

It shells out to the binary's ``read`` subcommand (JSON output) and returns
text, so it is a drop-in alternative to ``ocr.ocr_image`` / ``ocr.ocr_page`` for
handwritten scans. If the binary or a trained model is missing it degrades
gracefully: callers can fall back to the existing PaddleOCR path.

Enable it by setting ``HANDWRITING_OCR=1``. Point ``HANDWRITING_BIN`` at the
binary and ``HANDWRITING_MODEL`` at a trained model if they are not on the
default search path / embedded in the binary.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Where to find the compiled Go binary. We try, in order: an explicit env var,
# the conventional build output under ./handwriting, then anything named
# "handwriting" on PATH.
_ENV_BIN = "HANDWRITING_BIN"
_ENV_MODEL = "HANDWRITING_MODEL"
_ENV_ENABLE = "HANDWRITING_OCR"

_DEFAULT_TIMEOUT = int(os.environ.get("HANDWRITING_TIMEOUT", "60"))


class HandwritingOCRError(RuntimeError):
    """Raised when the Go recognizer is unavailable or fails."""


def enabled() -> bool:
    """True when the deployment opted into the Go handwriting engine."""
    return os.environ.get(_ENV_ENABLE, "").strip().lower() in {
        "1", "true", "yes", "on"}


def _binary_path() -> str | None:
    """Locate the Go recognizer binary, or None if not found."""
    explicit = os.environ.get(_ENV_BIN)
    if explicit and Path(explicit).is_file():
        return explicit

    here = Path(__file__).resolve().parent
    for candidate in (
        here / "handwriting" / "handwriting",
        here / "handwriting" / "handwriting.exe",
        here / "handwriting.exe",
        here / "handwriting",
    ):
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("handwriting")
    return found


def is_available(timeout: int = 5) -> tuple[bool, str]:
    """Check the binary exists and runs. Returns ``(ok, message)`` for the UI."""
    if not enabled():
        return False, "Handwriting OCR disabled (set HANDWRITING_OCR=1)."
    binary = _binary_path()
    if not binary:
        return False, (
            "Go handwriting binary not found. Build it with "
            "`cd handwriting && make build`, or set HANDWRITING_BIN."
        )
    try:
        # `help` exits cleanly and proves the binary runs on this platform.
        subprocess.run([binary, "help"], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Go handwriting binary failed to run: {exc}"
    return True, f"Go handwriting recognizer ready ({binary})."


def _run_read(image_path: str, multiline: bool, min_conf: float) -> dict:
    """Invoke `handwriting read -json` and return the parsed result."""
    binary = _binary_path()
    if not binary:
        raise HandwritingOCRError("Go handwriting binary not found")

    cmd = [binary, "read", "-json", "-image", str(image_path)]
    if multiline:
        cmd.append("-multiline")
    if min_conf > 0:
        cmd += ["-minconf", str(min_conf)]
    model = os.environ.get(_ENV_MODEL)
    if model:
        cmd += ["-model", model]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HandwritingOCRError(f"recognizer failed to run: {exc}") from exc

    if proc.returncode != 0:
        raise HandwritingOCRError(
            f"recognizer error: {proc.stderr.strip() or 'unknown error'}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HandwritingOCRError(
            f"recognizer returned invalid JSON: {proc.stdout[:200]}"
        ) from exc


def read_file(image_path: str, multiline: bool = True,
              min_conf: float = 0.0) -> dict:
    """Transcribe a handwritten image file.

    Returns the recognizer's structured result:
    ``{"text", "lines": [...], "glyphs": [[...]], "mean_confidence"}``.
    """
    return _run_read(image_path, multiline, min_conf)


def read_text(image_path: str, multiline: bool = True) -> str:
    """Transcribe a handwritten image file to plain text."""
    return read_file(image_path, multiline=multiline).get("text", "")


def ocr_image(image, multiline: bool = True) -> str:
    """OCR an in-memory image (an OpenCV/numpy array), mirroring ``ocr.ocr_image``.

    The Go binary reads files, so the array is written to a temporary PNG first.
    This lets the Go engine slot directly into ``form_detector.ocr_boxes`` for
    handwritten field boxes.
    """
    import cv2  # lazy: only needed when actually OCR-ing an array

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "box.png")
        if not cv2.imwrite(path, image):
            raise HandwritingOCRError("could not write temp image for OCR")
        return read_text(path, multiline=multiline)


def ocr_page(image_path: str) -> str:
    """Full handwritten-page pipeline mirroring ``ocr.ocr_page``."""
    return read_text(image_path, multiline=True)


def export_uncertain_glyphs(image_path: str, out_dir: str,
                            max_conf: float = 0.6,
                            multiline: bool = True) -> int:
    """Write the glyphs the model reads *below* ``max_conf`` to ``out_dir`` as
    PNGs (pre-labelled with the model's guess), for a human to correct and feed
    back into training. Returns the number of glyphs written.

    This is the capture half of the review loop: the characters the recognizer
    wasn't sure about become labelled training data once a human fixes them.
    """
    binary = _binary_path()
    if not binary:
        raise HandwritingOCRError("Go handwriting binary not found")
    cmd = [binary, "export-glyphs", "-image", str(image_path),
           "-out", str(out_dir), "-maxconf", str(max_conf)]
    if not multiline:
        cmd.append("-line")
    model = os.environ.get(_ENV_MODEL)
    if model:
        cmd += ["-model", model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_DEFAULT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HandwritingOCRError(f"export-glyphs failed to run: {exc}") from exc
    if proc.returncode != 0:
        raise HandwritingOCRError(
            f"export-glyphs error: {proc.stderr.strip() or 'unknown error'}")
    # stdout: "wrote N glyph images ..." — pull the count back out.
    for token in proc.stdout.split():
        if token.isdigit():
            return int(token)
    return 0


if __name__ == "__main__":
    import sys

    ok, message = is_available()
    print(message)
    if ok and len(sys.argv) > 1:
        print("---")
        print(read_text(sys.argv[1]))
