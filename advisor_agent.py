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
        return "⚠️ AI Advisor offline (missing API key)."
        
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
        return "⚠️ AI Advisor encountered an error. Please try again later."

def get_advisor_intro() -> str:
    """Return a compelling intro for the /advisor command."""
    return (
        "🤖 *ApexFlash AI Advisor (Elite)*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "I have analyzed your last 15 trades using Gemini 2.0 Intelligence.\n\n"
        "_My mission is to turn your trades into institutional alpha._\n\n"
    )
