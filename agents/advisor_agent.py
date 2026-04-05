# ApexFlash AI Trading Advisor

import json
import logging
import os
from typing import List, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger("AIAdvisor")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_CHAIN = [
    m.strip()
    for m in os.getenv(
        "GEMINI_MODEL_CHAIN",
        "models/gemini-2.0-flash,models/gemini-2.0-flash-lite,models/gemini-1.5-flash-latest,models/gemini-1.5-pro-latest",
    ).split(",")
    if m.strip()
]

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _discover_generate_models() -> List[str]:
    try:
        discovered = []
        for model in genai.list_models():
            methods = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                name = getattr(model, "name", "")
                if name:
                    discovered.append(name)
        return discovered
    except Exception as e:
        logger.warning("AI Advisor list_models failed: %s", e)
        return []


def _resolve_model_chain() -> List[str]:
    discovered = _discover_generate_models()
    if not discovered:
        return MODEL_CHAIN

    discovered_set = set(discovered)
    resolved: List[str] = []

    for configured in MODEL_CHAIN:
        direct = configured
        prefixed = configured if configured.startswith("models/") else f"models/{configured}"
        if direct in discovered_set:
            resolved.append(direct)
        elif prefixed in discovered_set:
            resolved.append(prefixed)

    # Append any remaining discovered models as last resort.
    for model in discovered:
        if model not in resolved:
            resolved.append(model)

    return resolved


def _build_prompt(history_summary: List[dict]) -> str:
    return (
        "You are the ApexFlash Pro Advisor. Analyze the following 15 crypto trades. "
        "Identify psychological biases (FOMO, revenge trading, etc.) or execution errors. "
        "Output formatting: Markdown. Include:\n"
        "1. Trader Grade (S, A, B, C, D)\n"
        "2. Psychological Analysis (1-2 sentences)\n"
        "3. 3 Actionable Tips to increase win rate.\n\n"
        f"USER TRADE HISTORY (JSON):\n{json.dumps(history_summary, indent=2)}"
    )


async def _try_gemini(prompt: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not GEMINI_API_KEY:
        return None, None, "GEMINI_API_KEY missing"

    errors: List[str] = []
    for model_name in _resolve_model_chain():
        try:
            model = genai.GenerativeModel(model_name)
            response = await model.generate_content_async(prompt)
            text = (response.text or "").strip()
            if text:
                return text, model_name, None
            errors.append(f"empty response: {model_name}")
        except Exception as e:
            msg = f"{model_name}: {type(e).__name__}: {e}"
            errors.append(msg)
            logger.warning("AI Advisor model failed: %s", msg)

    reason = " | ".join(errors[-3:]) if errors else "no model response"
    return None, None, reason


async def analyze_trader_performance(user_id: int, history: List[dict]) -> str:
    if not history:
        return "No trade history found. Start trading to receive AI coaching!"

    history_summary = []
    for t in history[-15:]:
        history_summary.append(
            {
                "token": t.get("token"),
                "side": t.get("side"),
                "sol": t.get("sol"),
                "usd": t.get("usd"),
                "entry_price": t.get("entry_price_usd"),
                "timestamp": t.get("ts"),
            }
        )

    prompt = _build_prompt(history_summary)
    text, model_name, reason = await _try_gemini(prompt)

    if text:
        return f"Model: {model_name}\n\n{text}"

    return _local_fallback_analysis(history, reason=reason)


def get_advisor_intro(use_fallback: bool = False) -> str:
    if use_fallback:
        return (
            "🤖 *ApexFlash AI Advisor (Elite)*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Gemini temporarily unavailable. Fallback coaching active.\n\n"
        )

    return (
        "🤖 *ApexFlash AI Advisor (Elite)*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "I have analyzed your last 15 trades using Gemini Intelligence.\n\n"
        "_My mission is to turn your trades into institutional alpha._\n\n"
    )


def _local_fallback_analysis(history: List[dict], reason: Optional[str] = None) -> str:
    recent = history[-15:]
    completed = [t for t in recent if str(t.get("side", "")).upper() == "SELL"]

    if not completed:
        base = (
            "Trader Grade: B\n"
            "Psychological Analysis: Not enough completed sell data for deep coaching yet.\n"
            "3 Actionable Tips:\n"
            "1. Close partial positions (25-50%) to lock gains and generate data.\n"
            "2. Use stop-loss on every trade to avoid emotional decisions.\n"
            "3. Avoid buying after large green candles."
        )
        return f"Fallback reason: {reason}\n\n{base}" if reason else base

    wins = sum(1 for t in completed if float(t.get("pnl_pct", 0) or 0) > 0)
    total = len(completed)
    win_rate = (wins / total) * 100 if total else 0

    if win_rate >= 70:
        grade = "A"
    elif win_rate >= 55:
        grade = "B"
    elif win_rate >= 40:
        grade = "C"
    else:
        grade = "D"

    base = (
        f"Trader Grade: {grade} (Fallback Model)\n"
        f"Psychological Analysis: Completed sells: {total}, Win rate: {win_rate:.1f}%. Keep execution systematic.\n"
        "3 Actionable Tips:\n"
        "1. Pre-define stop-loss and take-profit before entry.\n"
        "2. Scale out winners instead of full close at once.\n"
        "3. Limit revenge trading: max 3 discretionary trades per session."
    )
    return f"Fallback reason: {reason}\n\n{base}" if reason else base
