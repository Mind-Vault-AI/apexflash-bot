"""
ApexFlash Whale Intent Engine v1.0 (Cycle 8)
────────────────────────────────────────────────────────
Objective: Analyze whale transactions using Gemini 1.5 Pro.
Target: Provide "Elite" signals by predicting whale motives.
"""

import logging
import os
import aiohttp
from typing import Optional
import google.generativeai as genai

logger = logging.getLogger("WhaleIntent")

# Configure Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

async def analyze_whale_intent(tx_hash: str, wallet: str, token: str, amount_sol: float) -> str:
    """
    Uses Gemini to hypothesize the motive behind a whale transaction.
    Returns a formatted string for the Telegram alert.
    """
    if not GEMINI_API_KEY:
        return "⚠️ AI Analysis unavailable (No API Key)."

    prompt = f"""
    You are a professional Solana Whale Analyst.
    Analyze this transaction and categorize it with a high-conviction hypothesis.
    
    Transaction Data:
    - Wallet: {wallet}
    - Token: {token}
    - Amount: {amount_sol} SOL
    - TX: {tx_hash}
    
    Categorize as one of:
    1. [ACCUMULATION] - Whale is loading up for a long-term hold or pump.
    2. [DISTRIBUTION] - Whale is preparing to dump on retail.
    3. [MARKET MAKING] - High-frequency circular volume to attract eyes.
    4. [INSIDER SIGNAL] - Precognitive buy before news/listing.
    
    Return a concise 2-3 sentence analysis with a 'Confidence Score (%)'.
    Use a professional, "Flash" style tone.
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response and response.text:
            return response.text.strip()
        return "🤖 Whale intent is currently ambiguous. Monitoring..."
        
    except Exception as e:
        logger.error(f"Whale Intent Analysis failed: {e}")
        return "🤖 AI model is busy. Move categorized as High Convection."

import asyncio # Needed for to_thread in older versions

# Helper for the bot to check if user is Elite
def can_user_analyze(user_tier: str) -> bool:
    return user_tier.lower() == "elite"
