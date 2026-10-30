"""Optional server-side OpenAI-compatible JSON integration (stdlib only).

No request is made unless CIVICPULSE_LLM_ENABLED=1, API key, and model are set.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def is_configured(env=None) -> bool:
    env = os.environ if env is None else env
    return (env.get("CIVICPULSE_LLM_ENABLED", "").strip() == "1"
            and bool(env.get("CIVICPULSE_LLM_API_KEY", "").strip())
            and bool(env.get("CIVICPULSE_LLM_MODEL", "").strip()))


def _endpoint(base_url: str) -> str:
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def generate_json(system_prompt: str, user_prompt: str, *, timeout: float = 8.0, env=None) -> dict:
    """Call a configured OpenAI-compatible chat endpoint and parse JSON only."""
    env = os.environ if env is None else env
    if not is_configured(env):
        raise RuntimeError("LLM credentials/provider are not configured")
    body = json.dumps({"model": env["CIVICPULSE_LLM_MODEL"],
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0, "response_format": {"type": "json_object"}}).encode("utf-8")
    request = Request(_endpoint(env.get("CIVICPULSE_LLM_BASE_URL", "")), data=body, method="POST",
        headers={"Authorization": "Bearer " + env["CIVICPULSE_LLM_API_KEY"], "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError("LLM response exceeded the 512 KB limit")
        envelope = json.loads(raw)
        content = envelope["choices"][0]["message"]["content"]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("LLM JSON response must be an object")
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Configured LLM unavailable or returned malformed output ({type(exc).__name__})") from exc
