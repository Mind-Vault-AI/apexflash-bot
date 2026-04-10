"""
ApexFlash AI Router — Free Model Circulation Engine
====================================================
Central routing layer: picks the best available FREE AI model per job type.
All agents call `complete(job, prompt)` — never touch providers directly.

Providers (all free-tier / keys already on Render):
  - Gemini     : google.generativeai (free tier via Google AI Studio)
  - DeepSeek   : api.deepseek.com  (OpenAI-compat, free tier 6M tok/day)
  - Nebius     : api.studio.nebius.com/v1 (OpenAI-compat, free, open models)
  - Groq       : api.groq.com/openai/v1  (OpenAI-compat, free, ultra-fast)

Job types → priority chains:
  ADVISOR    : trade coaching / psychological analysis  → fast + smart
  CEO        : daily strategic briefing                 → most intelligent
  NEWS       : sentiment scoring 0-100                  → fast + cheap
  MARKETING  : viral content / captions                 → creative
  CONVERSION : user onboarding messages                 → friendly/concise
"""

import asyncio
import json
import logging
import os
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger("AIRouter")

# ─── Keys ────────────────────────────────────────────────────────────────────
_GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "").strip()
_DEEPSEEK_KEY    = os.getenv("DEEPSEEK_API_KEY", "").strip()
_NEBIUS_KEY      = os.getenv("NEBIUS_API_KEY", "").strip()
_GROQ_KEY        = os.getenv("GROQ_API_KEY", "").strip()
_OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY", "").strip()

if _GEMINI_KEY:
    genai.configure(api_key=_GEMINI_KEY)

# ─── Model registry ───────────────────────────────────────────────────────────
# Each entry: (model_id, provider_tag, max_tokens)
# Priority order: Groq (fast+free) → Gemini (smart) → OpenRouter (free models) → Nebius → DeepSeek
MODELS = {
    "groq-llama":      ("llama-3.3-70b-versatile",                          "groq",       800),
    "groq-fast":       ("llama-3.1-8b-instant",                             "groq",       800),
    "gemini-flash":    ("models/gemini-2.0-flash",                          "gemini",     800),
    "gemini-flash-15": ("models/gemini-1.5-flash-latest",                   "gemini",     800),
    "openrouter-ds":   ("deepseek/deepseek-r1:free",                        "openrouter", 800),
    "openrouter-llama":("meta-llama/llama-3.3-70b-instruct:free",           "openrouter", 800),
    "nebius-llama":    ("meta-llama/Meta-Llama-3.1-70B-Instruct",           "nebius",     800),
    "nebius-mistral":  ("mistralai/Mistral-Nemo-Instruct-2407",             "nebius",     800),
    "deepseek":        ("deepseek-chat",                                     "deepseek",   800),
}

# Job → ordered list of model keys
# Groq first: free, 14400 req/day, ultra-fast. Gemini when key is valid.
JOB_CHAINS: Dict[str, List[str]] = {
    "ADVISOR":    ["groq-llama",   "gemini-flash",    "openrouter-ds",    "nebius-llama",   "deepseek"],
    "CEO":        ["groq-llama",   "openrouter-ds",   "gemini-flash",     "nebius-llama",   "deepseek"],
    "NEWS":       ["groq-fast",    "groq-llama",      "gemini-flash",     "openrouter-llama","nebius-mistral"],
    "MARKETING":  ["groq-llama",   "gemini-flash-15", "openrouter-llama", "nebius-llama",   "deepseek"],
    "CONVERSION": ["groq-fast",    "gemini-flash-15", "openrouter-llama", "nebius-mistral", "deepseek"],
    "GENERIC":    ["groq-llama",   "gemini-flash",    "openrouter-ds",    "nebius-llama",   "deepseek"],
}

# Per-model cooldown tracking (blocked until timestamp)
_BLOCKED_UNTIL: Dict[str, float] = {}
_LAST_SUCCESS: Dict[str, str] = {}  # job → model_key

COOLDOWN_RATE    = int(os.getenv("AI_RATE_COOLDOWN_SEC",     "300"))
COOLDOWN_NOTFOUND= int(os.getenv("AI_NOTFOUND_COOLDOWN_SEC", "3600"))
COOLDOWN_KEYINV  = int(os.getenv("AI_KEYINVALID_COOLDOWN_SEC","86400"))  # 24h


# ─── Health snapshot (for /ai_status dashboard) ───────────────────────────────
_health: Dict[str, dict] = {k: {"calls": 0, "ok": 0, "last_error": ""} for k in MODELS}

# Re-initialize if new keys are added at import time (router hot-reload safe)
for _k in MODELS:
    if _k not in _health:
        _health[_k] = {"calls": 0, "ok": 0, "last_error": ""}


def get_health_snapshot() -> Dict[str, dict]:
    """Returns per-model stats + current block status for the dashboard."""
    now = time.time()
    out = {}
    for key, stats in _health.items():
        model_id, provider, _ = MODELS[key]
        blocked_secs = max(0, int(_BLOCKED_UNTIL.get(key, 0) - now))
        key_present = _key_present(provider)
        out[key] = {
            "model":        model_id,
            "provider":     provider,
            "key_present":  key_present,
            "calls":        stats["calls"],
            "ok":           stats["ok"],
            "blocked_secs": blocked_secs,
            "last_error":   stats["last_error"][-80:] if stats["last_error"] else "",
        }
    return out


def _key_present(provider: str) -> bool:
    return {
        "gemini":     bool(_GEMINI_KEY),
        "deepseek":   bool(_DEEPSEEK_KEY),
        "nebius":     bool(_NEBIUS_KEY),
        "groq":       bool(_GROQ_KEY),
        "openrouter": bool(_OPENROUTER_KEY),
    }.get(provider, False)


# ─── Provider call implementations ───────────────────────────────────────────

async def _call_gemini(model_id: str, prompt: str, max_tokens: int) -> str:
    model = genai.GenerativeModel(model_id)
    response = await model.generate_content_async(prompt)
    text = (response.text or "").strip()
    if not text:
        raise ValueError("empty response")
    return text


async def _call_openai_compat(
    base_url: str, api_key: str, model_id: str, prompt: str, max_tokens: int
) -> str:
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    loop = asyncio.get_event_loop()
    def _do():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    data = await loop.run_in_executor(None, _do)
    text = data["choices"][0]["message"]["content"].strip()
    if not text:
        raise ValueError("empty response")
    return text


async def _call_model(model_key: str, prompt: str) -> str:
    model_id, provider, max_tokens = MODELS[model_key]
    if provider == "gemini":
        return await _call_gemini(model_id, prompt, max_tokens)
    elif provider == "deepseek":
        return await _call_openai_compat(
            "https://api.deepseek.com", _DEEPSEEK_KEY, model_id, prompt, max_tokens
        )
    elif provider == "nebius":
        return await _call_openai_compat(
            "https://api.studio.nebius.com/v1", _NEBIUS_KEY, model_id, prompt, max_tokens
        )
    elif provider == "groq":
        return await _call_openai_compat(
            "https://api.groq.com/openai/v1", _GROQ_KEY, model_id, prompt, max_tokens
        )
    elif provider == "openrouter":
        return await _call_openai_compat(
            "https://openrouter.ai/api/v1", _OPENROUTER_KEY, model_id, prompt, max_tokens
        )
    raise ValueError(f"Unknown provider: {provider}")


# ─── Main router ──────────────────────────────────────────────────────────────

async def complete(
    job: str,
    prompt: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Route `prompt` to the best available free model for the given `job`.
    Returns (text, model_key_used, error_reason).
    """
    chain = JOB_CHAINS.get(job, JOB_CHAINS["GENERIC"])
    now = time.time()
    errors: List[str] = []

    # Prefer last known working model for this job
    last = _LAST_SUCCESS.get(job)
    if last and last in chain:
        chain = [last] + [m for m in chain if m != last]

    for model_key in chain:
        model_id, provider, _ = MODELS[model_key]

        # Skip if key missing
        if not _key_present(provider):
            errors.append(f"{model_key}: no key")
            continue

        # Skip if model on cooldown
        blocked_until = _BLOCKED_UNTIL.get(model_key, 0)
        if blocked_until > now:
            errors.append(f"{model_key}: blocked {int(blocked_until - now)}s")
            continue

        _health[model_key]["calls"] += 1
        try:
            text = await _call_model(model_key, prompt)
            _health[model_key]["ok"] += 1
            _health[model_key]["last_error"] = ""
            _LAST_SUCCESS[job] = model_key
            logger.info("AIRouter [%s] → %s ✅", job, model_key)
            return text, model_key, None

        except Exception as e:
            msg = str(e)
            _health[model_key]["last_error"] = msg
            errors.append(f"{model_key}: {msg[:60]}")
            logger.warning("AIRouter [%s] %s failed: %s", job, model_key, msg)

            low = msg.lower()
            if "api_key_invalid" in low or "invalid api key" in low or "api key not found" in low:
                _BLOCKED_UNTIL[model_key] = now + COOLDOWN_KEYINV
            elif "429" in low or "resourceexhausted" in low or "rate" in low:
                _BLOCKED_UNTIL[model_key] = now + COOLDOWN_RATE
            elif "notfound" in low or "not found" in low or "not supported" in low:
                _BLOCKED_UNTIL[model_key] = now + COOLDOWN_NOTFOUND

    reason = " | ".join(errors[-4:])
    logger.error("AIRouter [%s] ALL models failed: %s", job, reason)
    return None, None, reason


async def probe_all() -> Dict[str, bool]:
    """Quick probe: returns {model_key: ok} for dashboard."""
    probe_prompt = "Reply with exactly: OK"
    results = {}
    for model_key in MODELS:
        model_id, provider, _ = MODELS[model_key]
        if not _key_present(provider):
            results[model_key] = None  # no key
            continue
        try:
            text = await _call_model(model_key, probe_prompt)
            results[model_key] = bool(text)
        except Exception:
            results[model_key] = False
    return results
