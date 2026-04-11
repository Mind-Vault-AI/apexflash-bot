"""
ApexFlash Conversion Agent (v3.22.0)
────────────────────────────────────────────────────────
Objective: Convert Free users to Pro/Elite via AI FOMO.
Logic: Transform "Missed Signals" into persuasive Opportunity Reports.
"""

import asyncio
import logging
import google.generativeai as genai
from core.persistence import get_missed_signals
from core.i18n import get_text
from core.config import VERSION

logger = logging.getLogger("ConversionAgent")

async def generate_opportunity_report(user_id: int, user_lang: str = "en") -> str:
    """
    Generate a personalized AI report showing what a user missed.
    """
    missed = get_missed_signals(user_id)
    if not missed:
        return ""

    # 1. Aggregate data for the prompt
    summary = ""
    total_pnl = 0.0
    for s in missed:
        summary += f"- {s['type']} on ${s['token']} (+{s['pnl']}%)\n"
        total_pnl += s['pnl']

    # 2. AI Persuasion via router
    try:
        from agents.ai_router import complete
        prompt = (
            f"You are the ApexFlash AI Growth Advisor. Write a short, professional, and high-impact "
            f"personal report for a user who is currently on the FREE tier.\n"
            f"In the last 24h, they MISSED these high-conviction signals because they don't have ELITE access:\n"
            f"{summary}\n"
            f"Total missed potential profit: +{total_pnl:.1f}%\n"
            f"Language: {user_lang}\n\n"
            f"Rules: Be respectful but create clear FOMO (Fear of Missing Out). "
            f"Highlight that institutional-tier tools pay for themselves. "
            f"Keep it under 300 characters. End with an invitation to use /upgrade."
        )
        ai_text, model_used, err = await complete("CONVERSION", prompt)
        ai_msg = ai_text.strip() if ai_text else None
        if not ai_msg:
            raise ValueError(err or "empty")
        
        header = f"📉 *OPPORTUNITY REPORT (24H)*\n\n"
        footer = f"\n\n🚀 _ApexFlash v{VERSION} — Don't Trade Blind._"
        return f"{header}{ai_msg}{footer}"

    except Exception as e:
        logger.error(f"Failed to generate conversion report: {e}")
        # Fallback if AI fails
        return (
            f"📉 *OPPORTUNITY REPORT*\n\n"
            f"You missed *{len(missed)}* high-conviction signals today.\n"
            f"Estimated potential profit: *+{total_pnl:.1f}%*\n\n"
            f"Elite users received these alerts in real-time. Don't leave money on the table.\n\n"
            f"👉 /upgrade to capture the next wave."
        )

async def check_conversion_eligibility(user_id: int, user_data: dict) -> bool:
    """
    Logic to determine if a user should receive a conversion nudge.
    Don't spam; only nudge if significant value was missed.
    """
    if user_data.get("tier") != "free":
        return False
    
    missed = get_missed_signals(user_id)
    if len(missed) >= 3: # Nudge if they missed at least 3 signals
        return True
    
    return False
