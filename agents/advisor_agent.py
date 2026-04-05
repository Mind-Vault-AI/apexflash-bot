"""
ApexFlash AI Trading Advisor (v3.20.0)
────────────────────────────────────────────────────────
Objective: Provide personalized, institutional-grade trade feedback.
Engine: Google Gemini 2.0 Pro
"""

import logging
import json
import google.generativeai as genai
from typing import List, Optional
import os

logger = logging.getLogger("AIAdvisor")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ── Advisor Engine ────────────────────────────────────────────────────────────

async def analyze_trader_performance(user_id: int, history: List[dict]) -> str:
    """
    Analyze user trade history and return 3 actionable tips + a 'Trader Grade'.
    """
    if not GEMINI_API_KEY:
        return _local_fallback_analysis(history)
        
    if not history:
        return "📉 No trade history found. Start trading to receive AI coaching!"

    try:
        model = genai.GenerativeModel('gemini-2.0-flash') # Using Flash for speed, can be Pro
        
        # Prepare history for Gemini (Token, Side, SOL, Entry Price, etc.)
        history_summary = []
        for t in history[-15:]:
            history_summary.append({
                "token": t.get("token"),
                "side": t.get("side"),
                "sol": t.get("sol"),
                "usd": t.get("usd"),
                "entry_price": t.get("entry_price_usd"),
                "timestamp": t.get("ts")
            })

        prompt = (
            "You are the ApexFlash Pro Advisor. Analyze the following 15 crypto trades. "
            "Identify psychological biases (FOMO, revenge trading, etc.) or execution errors. "
            "Output formatting: Markdown. "
            "Include: \n"
            "1. 🏆 Trader Grade (S, A, B, C, D)\n"
            "2. 🧠 Psychological Analysis (1-2 sentences)\n"
            "3. ⚡ 3 Actionable Tips to increase win rate.\n\n"
            f"USER TRADE HISTORY (JSON):\n{json.dumps(history_summary, indent=2)}"
        )

        response = await model.generate_content_async(prompt)
        return response.text

    except Exception as e:
        logger.error(f"AI Advisor failed: {e}")
        return _local_fallback_analysis(history)

def get_advisor_intro() -> str:
    """Return a compelling intro for the /advisor command."""
    return (
        "🤖 *ApexFlash AI Advisor (Elite)*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "I have analyzed your last 15 trades using Gemini 2.0 Intelligence.\n\n"
        "_My mission is to turn your trades into institutional alpha._\n\n"
    )


def _local_fallback_analysis(history: List[dict]) -> str:
    """Return a deterministic analysis when Gemini is unavailable or fails."""
    recent = history[-15:]
    completed = [t for t in recent if str(t.get("side", "")).upper() == "SELL"]

    if not completed:
        return (
            "🏆 *Trader Grade:* B\n"
            "🧠 *Psychological Analysis:* Good activity, but not enough completed sell data for deep coaching yet.\n"
            "⚡ *3 Actionable Tips:*\n"
            "1. Close partial positions (25-50%) to lock gains and generate data.\n"
            "2. Use stop-loss on every trade to avoid emotional decisions.\n"
            "3. Review your last entries and avoid buying after large green candles."
        )

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

    return (
        f"🏆 *Trader Grade:* {grade} (Fallback Model)\n"
        f"🧠 *Psychological Analysis:* Completed sells: {total}, Win rate: {win_rate:.1f}%. Keep execution systematic, not emotional.\n"
        "⚡ *3 Actionable Tips:*\n"
        "1. Pre-define stop-loss and take-profit before entry.\n"
        "2. Scale out winners instead of full close at once.\n"
        "3. Limit revenge trading: max 3 discretionary trades per session."
    )
