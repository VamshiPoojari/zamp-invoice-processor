"""
Talks to the AI (OpenRouter, free models only).

Free models are sometimes busy or rate-limited, so this file:
  1. tries the main model first,
  2. if it fails, tries the backup models,
  3. rotates through your API keys,
  4. waits a moment and retries on "too many requests".
"""
import json
import re
import time

import requests

from pipeline.config import get_api_keys

URL = "https://openrouter.ai/api/v1/chat/completions"

# All three can read text AND images. Order = preference.
# (Free model list changes over time — check https://openrouter.ai/models?q=free)
MODELS = [
    "nvidia/nemotron-3.5-super-vl:free",   # most reliable in testing (12 Nov 2026)
    "google/gemma-4-31b-it:free",          # often rate-limited, used as backup
    "google/gemma-4-26b-a4b-it:free",
]


class LLMError(Exception):
    pass


def call_llm(messages, log=print):
    """Send messages to the AI. Returns (reply_text, model_used).
    `log` is a function that receives progress messages (shown in the UI later)."""
    keys = get_api_keys()
    if not keys:
        raise LLMError("No OpenRouter API key found in .env")

    errors = []
    attempt = 0
    for model in MODELS:
        for try_no in range(2):  # each model gets 2 tries
            key = keys[attempt % len(keys)]
            attempt += 1
            try:
                r = requests.post(
                    URL,
                    headers={"Authorization": f"Bearer {key}",
                             "X-Title": "Invoice Processor (case study)"},
                    json={"model": model, "messages": messages, "temperature": 0},
                    timeout=120,
                )
            except requests.RequestException as e:
                errors.append(f"{model}: network error {e}")
                log(f"{model} – network error, retrying")
                continue

            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices") or []
                text = (choices[0].get("message", {}).get("content") or "") if choices else ""
                if text.strip():
                    return text, model
                errors.append(f"{model}: empty reply")
                log(f"{model} – empty reply, trying again")
                continue

            msg = r.text[:200]
            errors.append(f"{model}: HTTP {r.status_code} {msg}")
            if r.status_code == 429:
                if "per-day" in msg or "free-models-per-day" in msg:
                    raise LLMError("Daily free limit reached (50 requests/day). Try again tomorrow.")
                log(f"{model} is busy (rate limited) – waiting 5s, then retrying")
                time.sleep(5)
            elif r.status_code in (401, 403):
                log(f"Key #{(attempt - 1) % len(keys) + 1} rejected – trying next key")
            else:
                log(f"{model} – error {r.status_code}, switching to backup model")
                break  # this model is broken right now, go to next model

    raise LLMError("All free models failed:\n" + "\n".join(errors[-6:]))


def free_requests_left():
    """How many free AI requests are left today, summed over all keys (None if unknown).
    This lookup itself is free."""
    left = 0
    for key in get_api_keys():
        try:
            r = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {key}"}, timeout=10)
            left += r.json()["data"]["free_model_daily_requests"]["remaining"]
        except Exception:
            return None
    return left


def parse_json(text):
    """AI models sometimes wrap JSON in ```json ... ``` or add a sentence.
    This pulls out just the {...} part and turns it into a Python dict."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("AI reply did not contain JSON")
    return json.loads(text[start:end + 1])
