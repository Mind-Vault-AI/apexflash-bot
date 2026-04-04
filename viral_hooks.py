from config import BOT_USERNAME
"""
ApexFlash Viral Hook Generator (v3.18.0)
────────────────────────────────────────────────────────
Objective: Generate TikTok/Reels captions & screen-text.
Logic: Convert raw blockchain data into viral-ready hooks.
"""

import random
import logging
from typing import List

logger = logging.getLogger("ViralHooks")

# ── Hook Templates ────────────────────────────────────────────────────────────

HOOK_TEMPLATES = [
    "⚠️ {whale_move} just hit the market. The dump is coming. Are you ready? @{BOT_USERNAME}",
    "🚀 {token} is being accumulated by whales right now. 10x potential? Join the tracker. @{BOT_USERNAME}",
    "⚖️ FREE MONEY? found a {spread}% spread on {asset} between SOL and BASE. Move fast. @{BOT_USERNAME}",
    "🏛️ INSTITUTIONAL ALERT: {inst_move} detected. The smart money is buying. @{BOT_USERNAME}",
    "📈 I just made {amount} SOL in 24h doing NOTHING. The referral program is broken. 🚀 @{BOT_USERNAME}",
    "🛡️ RUG-GUARD TRAP: {token} just failed the safety scan. Saved 10 SOL. Don't trade blind. @{BOT_USERNAME}"
]

# ── Hook Engine ───────────────────────────────────────────────────────────────

def generate_viral_hook(data: dict) -> str:
    """
    Generate a high-conversion hook based on current bot activity.
    Data can include 'whale_move', 'token', 'spread', 'asset', etc.
    """
    hook = random.choice(HOOK_TEMPLATES)
    
    # Fill placeholders with provided data or defaults
    placeholders = {
        "whale_move": data.get("whale_move", "Massive whale transfer"),
        "token": data.get("token", "This coin"),
        "spread": data.get("spread", "2.1"),
        "asset": data.get("asset", "USDC"),
        "inst_move": data.get("inst_move", "Blackrock activity"),
        "amount": data.get("amount", "2.4")
    }
    
    try:
        return hook.format(**placeholders)
    except Exception as e:
        logger.error(f"Hook generation failed: {e}")
        return "⚠️ Massive crypto move detected! Follow the smart money at @{BOT_USERNAME} 🚀"

def get_marketing_playbook() -> List[str]:
    """Return a list of viral hooks for the daily marketing playbook."""
    # Simulation: In production, this would pull from seen_tx_hashes and arbitrage_alerts
    sample_data = [
        {"whale_move": "50,000 SOL", "token": "SOL"},
        {"spread": "1.9", "asset": "WETH"},
        {"inst_move": "ETF Filing update"},
        {"amount": "1.2"}
    ]
    
    return [generate_viral_hook(d) for d in sample_data]
