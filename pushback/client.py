"""OpenRouter chat calls. The key comes from the OPENROUTER_API_KEY environment variable."""

import json
import os
import re
import time

import requests

URL = "https://openrouter.ai/api/v1/chat/completions"


class CallError(Exception):
    """A call kept failing after retries."""


def chat(model, prompt, *, temperature=None, max_tokens=16000, effort=None, schema=None, schema_name="answer", retries=4, timeout=900):
    """Send one user message; return the reply text. With `schema`, ask for JSON matching it."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise CallError("OPENROUTER_API_KEY is not set")
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    if effort:
        body["reasoning"] = {"effort": effort}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
    err = ""
    for attempt in range(retries):
        try:
            r = requests.post(URL, headers={"Authorization": "Bearer " + key}, json=body, timeout=timeout)
            data = r.json()
            if "choices" not in data:
                raise CallError(str(data)[:300])
            choice = data["choices"][0]
            text = choice.get("message", {}).get("content") or ""
            if not text.strip():
                raise CallError("empty reply")
            if (choice.get("native_finish_reason") or choice.get("finish_reason")) == "length":
                raise CallError("reply cut off at max_tokens")
            return text
        except Exception as e:  # network errors, provider errors, empty or truncated replies
            err = f"{type(e).__name__}: {str(e)[:300]}"
            time.sleep(5 * (attempt + 1))
    raise CallError(f"{model}: {err}")


def parse_json(text, trailing=False):
    """The JSON object in a reply: the whole text if it parses; otherwise the outermost {...} span,
    or with trailing=True the last flat {...} block (for replies that end with a JSON line)."""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    pattern = r"\{[^{}]*\}" if trailing else r"\{.*\}"
    for m in reversed(list(re.finditer(pattern, text or "", re.DOTALL))):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None
