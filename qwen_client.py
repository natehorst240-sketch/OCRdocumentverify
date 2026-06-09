"""Thin wrapper around the local Ollama API for the Qwen2.5 model.

Everything runs locally — no internet or hosting required. The model is
expected to be served by Ollama at ``localhost:11434``.
"""

import json
import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("QWEN_MODEL", "qwen2.5:7b")
DEFAULT_TIMEOUT = int(os.environ.get("QWEN_TIMEOUT", "120"))


class QwenError(RuntimeError):
    """Raised when the Ollama backend is unreachable or returns an error."""


def is_available(timeout: int = 5) -> tuple[bool, str]:
    """Check that Ollama is up and the Qwen model is installed.

    Returns ``(ok, message)`` so the UI can show a friendly status line.
    """
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, f"Ollama not reachable at {OLLAMA_HOST}: {exc}"

    models = [m.get("name", "") for m in resp.json().get("models", [])]
    if not any(name.startswith(MODEL.split(":")[0]) for name in models):
        return False, (
            f"Ollama is up but model '{MODEL}' is not installed. "
            f"Run: ollama pull {MODEL}"
        )
    return True, f"Ollama reachable, model '{MODEL}' available."


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.0, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Send a single prompt to Qwen and return the text response."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise QwenError(f"Qwen request failed: {exc}") from exc

    return resp.json().get("response", "").strip()


def generate_json(prompt: str, system: str | None = None,
                  timeout: int = DEFAULT_TIMEOUT) -> dict | list:
    """Generate and parse a JSON response, tolerating code-fence wrapping."""
    raw = generate(prompt, system=system, timeout=timeout)
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences that models sometimes add.
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise QwenError(f"Qwen did not return valid JSON: {raw[:200]}") from exc


if __name__ == "__main__":
    ok, message = is_available()
    print(message)
    if ok:
        print("Test prompt ->", generate("Reply with the single word: OK"))
