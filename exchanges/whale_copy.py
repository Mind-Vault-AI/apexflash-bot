"""Whale copy trading module - monitor top wallets and mirror their buys.

Real-time whale monitoring via Helius websocket.
Paper trading mode for Week 1 testing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Known profitable whale wallets (verify performance before activating)
WHALE_WALLETS = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": {
        "name": "Solana Foundation",
        "enabled": False,  # Disable until verified
        "min_trade_usd": 10000,  # Only copy trades > $10K
    },
    "GThUX76zMmFrCwbjMG3C3VHLzuM8k9AMegXZ7u9NdH4p": {
        "name": "Jump Trading",
        "enabled": False,
        "min_trade_usd": 50000,
    },
}

# Whale copy state
WHALE_COPY_STATE = {
    "paper_trading": True,  # Week 1: log only, no real trades
    "tracked_wallets": [],
    "signals_logged": 0,
    "would_be_pnl": 0.0,
}


async def monitor_whale_wallet(wallet_address: str, whale_name: str):
    """Monitor single whale wallet for swap transactions."""
    logger.info(f"?? Monitoring whale: {whale_name} ({wallet_address[:8]}...)")

    # TODO: Implement Helius websocket subscription
    # For now: placeholder
    while True:
        await asyncio.sleep(60)
        # Placeholder: would parse TX, detect swaps, validate, execute
        pass


def log_whale_signal(whale_addr: str, token_mint: str, amount_sol: float, action: str):
    """Log whale signal for paper trading analysis."""
    WHALE_COPY_STATE["signals_logged"] += 1
    timestamp = datetime.now(timezone.utc).isoformat()

    log_entry = {
        "timestamp": timestamp,
        "whale": whale_addr[:8],
        "action": action,
        "token": token_mint[:8],
        "amount_sol": amount_sol,
        "paper_trading": WHALE_COPY_STATE["paper_trading"],
    }

    logger.info(f"?? WHALE SIGNAL: {log_entry}")

    # TODO: Save to file for Week 1 analysis
    # with open("data/whale_signals.jsonl", "a") as f:
    #     f.write(json.dumps(log_entry) + "\n")


def get_whale_stats() -> dict:
    """Return whale copy trading stats."""
    return {
        "paper_trading": WHALE_COPY_STATE["paper_trading"],
        "tracked_wallets": len(WHALE_COPY_STATE["tracked_wallets"]),
        "signals_logged": WHALE_COPY_STATE["signals_logged"],
        "would_be_pnl_sol": WHALE_COPY_STATE["would_be_pnl"],
    }
