"""
ApexFlash Arbitrage Monitor (SOL <-> BASE)
────────────────────────────────────────────────────────
Objective: Detect price spreads for high-liquidity tokens.
Channels: Solana (Jupiter) | Base (Uniswap/Aerodrome)
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger("ArbitrageScanner")

# ── Configuration ─────────────────────────────────────────────────────────────

# Common tokens to monitor (SOL Mint, BASE Address)
MONITOR_TOKENS = {
    "USDC": {
        "SOL": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    },
    "WETH": {
        "SOL": "7vfCXTUXx5WJV5JTuGB6ZEpJvMSPUXfHTNo4hfA7idv8",
        "BASE": "0x4200000000000000000000000000000000000006"
    },
    "BRETT": {
        "SOL": "BRETT_SOL_MINT_PLACEHOLDER", # BRETT is primarily Base, but some wrapped versions exist
        "BASE": "0x532f27101965dd1631953190d170eCc2Bc688C7E"
    }
}

MIN_SPREAD_PCT = 1.8 # Alert if spread > 1.8% to allow for fees

# ── Price Fetchers ────────────────────────────────────────────────────────────

async def fetch_solana_price(session: aiohttp.ClientSession, mint: str) -> Optional[float]:
    """Fetch price from Jupiter Price API."""
    url = f"https://price.jup.ag/v4/price?ids={mint}"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {}).get(mint, {}).get("price")
    except Exception as e:
        logger.error(f"SOL Price fetch failed: {e}")
    return None

async def fetch_base_price(session: aiohttp.ClientSession, address: str) -> Optional[float]:
    """Fetch price from DexScreener API (Base chain)."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    # Return price of the most liquid pair
                    return float(pairs[0].get("priceUsd", 0))
    except Exception as e:
        logger.error(f"BASE Price fetch failed: {e}")
    return None

# ── Arbitrage Logic ───────────────────────────────────────────────────────────

async def scan_arbitrage() -> list[dict]:
    """Scan all monitored tokens for spreads."""
    alerts = []
    async with aiohttp.ClientSession() as session:
        for symbol, info in MONITOR_TOKENS.items():
            if symbol == "BRETT" and info["SOL"] == "BRETT_SOL_MINT_PLACEHOLDER":
                continue # Skip placeholder
                
            sol_price, base_price = await asyncio.gather(
                fetch_solana_price(session, info["SOL"]),
                fetch_base_price(session, info["BASE"])
            )
            
            if sol_price and base_price:
                spread = abs(sol_price - base_price)
                avg = (sol_price + base_price) / 2
                spread_pct = (spread / avg) * 100
                
                if spread_pct >= MIN_SPREAD_PCT:
                    direction = "SOL -> BASE" if sol_price < base_price else "BASE -> SOL"
                    alerts.append({
                        "symbol": symbol,
                        "sol_price": sol_price,
                        "base_price": base_price,
                        "spread_pct": spread_pct,
                        "direction": direction,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    logger.info(f"🚨 ARBITRAGE DETECTED: {symbol} | Spread: {spread_pct:.2f}% | {direction}")
                    
    return alerts

def format_arbitrage_alert(alert: dict) -> str:
    """Format arbitrage data for Telegram Elite."""
    return (
        f"⚖️ *CROSS-CHAIN ARBITRAGE ALPHA*\n"
        f"{'━' * 22}\n"
        f"💎 Asset: *{alert['symbol']}*\n"
        f"\n"
        f"☀️ Solana: `${alert['sol_price']:.4f}`\n"
        f"🔵 Base: `${alert['base_price']:.4f}`\n"
        f"\n"
        f"🔥 **SPREAD: {alert['spread_pct']:.2f}%**\n"
        f"🚀 Opportunity: *{alert['direction']}*\n"
        f"{'━' * 22}\n"
        f"🤖 ApexFlash Godmode | Elite Only"
    )
