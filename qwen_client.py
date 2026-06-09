"""Thin wrapper around the local Ollama API for the Qwen2.5 model.

Everything runs locally — no internet or hosting required. The model is
expected to be served by Ollama at ``localhost:11434``.
"""

import json
import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("QWEN_MODEL", "qwen2.5:7b")

try:
    DEFAULT_TIMEOUT = int(os.environ.get("QWEN_TIMEOUT", "120"))
except ValueError:
    DEFAULT_TIMEOUT = 120  # ignore a malformed QWEN_TIMEOUT rather than crash


class QwenError(RuntimeError):
    """Raised when the Ollama backend is unreachable or returns an error."""


def _model_installed(models: list[str]) -> bool:
    """True only if the *exact* configured model tag is present.

    A prefix match would wrongly accept qwen2.5:3b when qwen2.5:7b is
    configured, so generate() calls would then fail. If MODEL has no explicit
    tag, accept the base name with any tag (Ollama defaults to ':latest').
    """
    if MODEL in models:
        return True
    if ":" not in MODEL:
        return any(m == f"{MODEL}:latest" or m.startswith(f"{MODEL}:")
                   for m in models)
    return False


def llm_enabled() -> bool:
    """False when the deployment is configured for no-LLM mode.

    Set ``DISABLE_LLM=1`` (the N100 / low-RAM host) to run the deterministic
    pipeline with manual entry instead of Qwen.
    """
    return os.environ.get("DISABLE_LLM", "").strip().lower() not in {
        "1", "true", "yes", "on"}


def is_available(timeout: int = 5) -> tuple[bool, str]:
    """Check that Ollama is up and the Qwen model is installed.

    Returns ``(ok, message)`` so the UI can show a friendly status line.
    """
    if not llm_enabled():
        return False, "LLM disabled (no-LLM mode) — manual entry in use."
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
    except requests.RequestException as exc:
        return False, f"Ollama not reachable at {OLLAMA_HOST}: {exc}"
    except ValueError as exc:  # invalid JSON from the backend
        return False, f"Ollama returned an unexpected response: {exc}"

    if not _model_installed(models):
        return False, (
            f"Ollama is up but model '{MODEL}' is not installed. "
            f"Run: ollama pull {MODEL}"
        )
    return True, f"Ollama reachable, model '{MODEL}' available."


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.0, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Send a single prompt to Qwen and return the text response."""
    if not llm_enabled():
        raise QwenError("LLM disabled (no-LLM mode)")
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

    try:
        return resp.json().get("response", "").strip()
    except ValueError as exc:  # invalid JSON from the backend
        raise QwenError(f"Qwen returned invalid JSON: {exc}") from exc


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
