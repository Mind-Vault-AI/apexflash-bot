"""
ApexFlash Whale Intelligence v2.0 — GMGN-powered
=================================================
Strategy: "Lift with Smart Money"
  1. Scan GMGN rank every 5 min → tokens with high smart_degen_count
  2. Scan GMGN trenches → early-stage pump tokens with smart wallet activity
  3. Grade: S (auto-execute) / A (alert) / B (info)
  4. Dedup via Redis — no repeat signals within 4h
  5. Grade S: auto-execute small position via GMGN swap (when AUTO_TRADE_ENABLED)

Why GMGN smart_degen_count:
  GMGN internally identifies wallets with consistent early-entry + profit records.
  Multiple smart wallets converging on same token = highest-confidence buy signal.

SSOT: GMGN_API_KEY in MASTER_ENV_APEXFLASH.txt (Box Drive)
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from core.persistence import _get_redis
from exchanges.gmgn_market import (
    rank as gmgn_rank,
    trenches as gmgn_trenches,
    is_configured as gmgn_ready,
)

logger = logging.getLogger("WhaleWatcher")

# ─── Grading thresholds (tunable via env) ─────────────────────────────────────

GRADE_S_SMART_DEGENS = int(os.getenv("WHALE_GRADE_S_DEGENS", "5"))
GRADE_A_SMART_DEGENS = int(os.getenv("WHALE_GRADE_A_DEGENS", "3"))
GRADE_S_PRICE_CHANGE = float(os.getenv("WHALE_GRADE_S_PCT", "15.0"))
GRADE_A_PRICE_CHANGE = float(os.getenv("WHALE_GRADE_A_PCT", "5.0"))
GRADE_S_VOLUME_USD   = float(os.getenv("WHALE_GRADE_S_VOL", "100000"))
GRADE_A_VOLUME_USD   = float(os.getenv("WHALE_GRADE_A_VOL", "20000"))

# ─── Auto-trade (Grade S only, disabled by default) ────────────────────────────

AUTO_TRADE_ENABLED = os.getenv("WHALE_AUTO_TRADE", "false").lower() == "true"
AUTO_TRADE_SOL     = float(os.getenv("WHALE_AUTO_TRADE_SOL", "0.05"))

# ─── Timing ───────────────────────────────────────────────────────────────────

SCAN_INTERVAL_SECONDS = int(os.getenv("WHALE_SCAN_INTERVAL", "300"))  # 5 min
SIGNAL_TTL_SECONDS    = 4 * 3600  # 4 hour dedup

# ─── Signal callbacks (registered by bot.py) ───────────────────────────────────

_signal_callbacks: list = []


def register_signal_callback(cb):
    """bot.py registers here to receive whale signals (grade + metadata)."""
    _signal_callbacks.append(cb)


# ─── Grading logic ─────────────────────────────────────────────────────────────

def _grade_rank_token(token: dict) -> Optional[str]:
    smart  = int(token.get("smart_degen_count", 0) or 0)
    renown = int(token.get("renowned_count", 0) or 0)
    chg_1h = float(token.get("price_change_percent1h", 0) or 0)
    chg_5m = float(token.get("price_change_percent5m", 0) or 0)
    vol    = float(token.get("volume", 0) or 0)

    if smart >= GRADE_S_SMART_DEGENS and chg_1h >= GRADE_S_PRICE_CHANGE and vol >= GRADE_S_VOLUME_USD:
        return "S"
    if smart >= GRADE_A_SMART_DEGENS and chg_1h >= GRADE_A_PRICE_CHANGE and vol >= GRADE_A_VOLUME_USD:
        return "A"
    if renown >= 2 and chg_1h >= GRADE_A_PRICE_CHANGE and vol >= GRADE_A_VOLUME_USD:
        return "A"
    if smart >= 1 and chg_5m > 0 and chg_1h > 0 and vol >= GRADE_A_VOLUME_USD:
        return "B"
    return None


def _grade_trenches_token(token: dict, category: str) -> Optional[str]:
    smart     = int(token.get("smart_degen_count", 0) or 0)
    hot_level = int(token.get("hot_level", 0) or 0)

    if category == "pump" and smart >= GRADE_A_SMART_DEGENS:
        return "A"
    if hot_level >= 3 and smart >= 1:
        return "A"
    if category == "completed" and smart >= 1:
        return "B"
    return None


# ─── Signal builder ─────────────────────────────────────────────────────────────

def _build_signal(token: dict, grade: str, source: str) -> dict:
    return {
        "grade":       grade,
        "source":      source,
        "symbol":      token.get("symbol", "?"),
        "mint":        token.get("address", ""),
        "price":       float(token.get("price", 0) or 0),
        "chg_1h":      float(token.get("price_change_percent1h", 0) or 0),
        "chg_5m":      float(token.get("price_change_percent5m", 0) or 0),
        "volume":      float(token.get("volume", 0) or 0),
        "smart_degens": int(token.get("smart_degen_count", 0) or 0),
        "renowned":    int(token.get("renowned_count", 0) or 0),
        "market_cap":  float(token.get("market_cap", 0) or 0),
        "timestamp":   int(time.time()),
    }


def format_whale_signal(sig: dict) -> str:
    """Format a whale signal for Telegram."""
    grade_emoji = {"S": "🚨", "A": "🔥", "B": "⚡"}.get(sig["grade"], "📊")
    auto_tag = " | 🤖 AUTO-BUYING" if sig["grade"] == "S" and AUTO_TRADE_ENABLED else ""
    return (
        f"{grade_emoji} *GRADE {sig['grade']} WHALE SIGNAL*{auto_tag}\n"
        f"📌 *{sig['symbol']}* | {sig['source']}\n"
        f"💵 ${sig['price']:.8f}\n"
        f"📈 1h: {sig['chg_1h']:+.1f}% | 5m: {sig['chg_5m']:+.1f}%\n"
        f"💰 Vol: ${sig['volume']:,.0f} | MC: ${sig['market_cap']:,.0f}\n"
        f"🧠 Smart Degens: {sig['smart_degens']} | Renowned: {sig['renowned']}\n"
        f"`{sig['mint'][:20]}...`"
    )


# ─── Deduplication ─────────────────────────────────────────────────────────────

def _already_signalled(r, mint: str, grade: str) -> bool:
    key = f"whale:signal:{grade}:{mint}"
    if r.exists(key):
        return True
    r.setex(key, SIGNAL_TTL_SECONDS, "1")
    return False


# ─── Auto-trade ────────────────────────────────────────────────────────────────

async def _auto_execute_trade(sig: dict):
    """Execute 0.05 SOL position for Grade S signals."""
    try:
        from exchanges.gmgn import is_configured as trade_ready, swap
        from core.config import GMGN_WALLET_ADDRESS

        if not trade_ready():
            logger.warning("WHALE AUTO-TRADE: GMGN trade not configured")
            return

        SOL_MINT = "So11111111111111111111111111111111111111112"
        amount_lamports = int(AUTO_TRADE_SOL * 1_000_000_000)

        logger.info(f"WHALE AUTO-TRADE: {sig['symbol']} {AUTO_TRADE_SOL} SOL")

        loop = asyncio.get_event_loop()
        order = await loop.run_in_executor(
            None,
            lambda: swap(
                from_token_address=SOL_MINT,
                to_token_address=sig["mint"],
                from_token_amount=amount_lamports,
                slippage=500,
                from_address=GMGN_WALLET_ADDRESS,
            )
        )
        tx = order.get("hash") or order.get("order_id", "unknown")
        logger.info(f"WHALE AUTO-TRADE: done → {tx}")

        r = _get_redis()
        if r:
            r.setex(
                f"whale:trade:{sig['mint']}",
                3600,
                json.dumps({"tx": tx, "sol": AUTO_TRADE_SOL, "grade": sig["grade"]}),
            )
    except Exception as e:
        logger.error(f"WHALE AUTO-TRADE ERROR: {e}")


# ─── DexScreener fallback scan ───────────────────────────────────────────────────

async def _dexscreener_scan(r) -> list:
    """
    Fallback scanner using DexScreener boosted tokens.
    No API key or IP whitelist required — always available.
    Grades tokens by momentum (no smart_degen_count available):
      A: ≥15% 1h change + ≥$100K volume
      B: ≥5% 1h change  + ≥$20K volume
    """
    import aiohttp
    fired = []
    try:
        boost_url = "https://api.dexscreener.com/token-boosts/latest/v1"
        async with aiohttp.ClientSession() as session:
            async with session.get(boost_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                boosts = await resp.json()

        sol_boosts = [t for t in (boosts if isinstance(boosts, list) else [])
                      if t.get("chainId") == "solana"][:15]

        async with aiohttp.ClientSession() as session:
            for boost in sol_boosts:
                addr = boost.get("tokenAddress", "")
                if not addr:
                    continue
                try:
                    async with session.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{addr}",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        pair_data = await resp.json()
                    pairs = pair_data.get("pairs") or []
                    if not pairs:
                        continue
                    pair = pairs[0]

                    chg_1h = float((pair.get("priceChange") or {}).get("h1", 0) or 0)
                    chg_5m = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
                    vol    = float((pair.get("volume") or {}).get("h24", 0) or 0)
                    price  = float(pair.get("priceUsd", 0) or 0)
                    sym    = (pair.get("baseToken") or {}).get("symbol", "?")
                    mc     = float(pair.get("fdv", 0) or 0)

                    if chg_1h >= GRADE_S_PRICE_CHANGE and vol >= GRADE_S_VOLUME_USD:
                        grade = "A"  # capped at A — no smart-money confirmation
                    elif chg_1h >= GRADE_A_PRICE_CHANGE and vol >= GRADE_A_VOLUME_USD:
                        grade = "B"
                    else:
                        continue

                    if r and _already_signalled(r, addr, grade):
                        continue

                    token = {
                        "address": addr,
                        "symbol": sym,
                        "price": price,
                        "price_change_percent1h": chg_1h,
                        "price_change_percent5m": chg_5m,
                        "volume": vol,
                        "market_cap": mc,
                        "smart_degen_count": 0,
                        "renowned_count": 0,
                    }
                    fired.append(_build_signal(token, grade, "DEXSCREENER_BOOST"))
                except Exception:
                    continue

    except Exception as e:
        logger.warning(f"DexScreener fallback error: {e}")
    return fired


# ─── Main scan loop ─────────────────────────────────────────────────────────────

async def whale_scan_loop():
    """
    Runs forever. Every SCAN_INTERVAL_SECONDS:
      - GMGN rank (smart_degen order) → grade S/A/B   [primary]
      - GMGN trenches (pump/completed) → grade A/B    [primary]
      - DexScreener boosted tokens → grade A/B        [fallback if GMGN fails]
    Emits signals via callbacks; deduplicates via Redis.
    Never exits — degrades gracefully to DexScreener when GMGN unavailable.
    """
    gmgn_available = gmgn_ready()
    if not gmgn_available:
        logger.warning("WHALE: GMGN_API_KEY not set — running on DexScreener fallback only")
    else:
        logger.info(
            f"🐋 WHALE INTELLIGENCE v2.0 ONLINE | "
            f"S≥{GRADE_S_SMART_DEGENS} degens / {GRADE_S_PRICE_CHANGE}%+ / ${GRADE_S_VOLUME_USD:,.0f}+ | "
            f"Auto-trade: {'ON ' + str(AUTO_TRADE_SOL) + ' SOL' if AUTO_TRADE_ENABLED else 'OFF'}"
        )

    while True:
        try:
            r = _get_redis()
            fired = []
            gmgn_ok = False

            # ── GMGN Rank scan ────────────────────────────────────────────────
            if gmgn_available:
                try:
                    tokens = gmgn_rank(chain="sol", interval="1h", limit=50, order_by="smart_degen_count")
                    for token in tokens:
                        grade = _grade_rank_token(token)
                        mint  = token.get("address", "")
                        if not grade or not mint:
                            continue
                        if r and _already_signalled(r, mint, grade):
                            continue
                        fired.append(_build_signal(token, grade, "GMGN_RANK"))
                    gmgn_ok = True
                except Exception as e:
                    logger.warning(f"GMGN rank scan failed: {e}")

            # ── GMGN Trenches scan ────────────────────────────────────────────
            if gmgn_available and gmgn_ok:
                try:
                    trench = gmgn_trenches(chain="sol", limit=20)
                    for cat in ("pump", "completed"):
                        for token in trench.get(cat, []):
                            grade = _grade_trenches_token(token, cat)
                            mint  = token.get("address", "")
                            if not grade or not mint:
                                continue
                            if r and _already_signalled(r, mint, grade):
                                continue
                            fired.append(_build_signal(token, grade, f"GMGN_{cat.upper()}"))
                except Exception as e:
                    logger.warning(f"GMGN trenches scan failed: {e}")

            # ── DexScreener fallback (when GMGN unavailable or failed) ────────
            if not gmgn_available or not gmgn_ok:
                dex_signals = await _dexscreener_scan(r)
                fired.extend(dex_signals)
                if dex_signals:
                    logger.info(f"WHALE (DexScreener fallback): {len(dex_signals)} signals")

            # ── Emit ──────────────────────────────────────────────────────────
            for sig in fired:
                if r:
                    r.lpush("whale:signals:recent", json.dumps(sig))
                    r.ltrim("whale:signals:recent", 0, 49)
                    r.incr(f"kpi:grade:{sig['grade']}:total")

                for cb in _signal_callbacks:
                    try:
                        await cb(sig)
                    except Exception as e:
                        logger.error(f"signal callback error: {e}")

                if sig["grade"] == "S" and AUTO_TRADE_ENABLED:
                    asyncio.create_task(_auto_execute_trade(sig))

            if fired:
                logger.info(f"WHALE: {len(fired)} signals this scan (source: {'GMGN' if gmgn_ok else 'DEXSCREENER'})")

            # ── Heartbeat ─────────────────────────────────────────────────────
            if r:
                r.setex("apexflash:whale:heartbeat", 600,
                        json.dumps({"ts": int(time.time()), "gmgn_ok": gmgn_ok,
                                    "signals_this_scan": len(fired)}))

        except Exception as e:
            logger.error(f"whale_scan_loop error: {e}")

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


# ─── Status ─────────────────────────────────────────────────────────────────────

def get_whale_stats() -> dict:
    r = _get_redis()
    if not r:
        return {"error": "no_redis"}
    raw = r.lrange("whale:signals:recent", 0, 9) or []
    recent = []
    for item in raw:
        try:
            recent.append(json.loads(item))
        except Exception:
            pass
    return {
        "gmgn_configured": gmgn_ready(),
        "auto_trade": AUTO_TRADE_ENABLED,
        "auto_trade_sol": AUTO_TRADE_SOL,
        "scan_interval_min": SCAN_INTERVAL_SECONDS // 60,
        "thresholds": {
            "grade_s": {"smart_degens": GRADE_S_SMART_DEGENS, "price_1h": GRADE_S_PRICE_CHANGE, "volume": GRADE_S_VOLUME_USD},
            "grade_a": {"smart_degens": GRADE_A_SMART_DEGENS, "price_1h": GRADE_A_PRICE_CHANGE, "volume": GRADE_A_VOLUME_USD},
        },
        "recent_signals": recent,
    }


async def get_recent_whale_signals(limit: int = 10) -> list:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _get_recent_sync(limit))


def _get_recent_sync(limit: int) -> list:
    r = _get_redis()
    if not r:
        return []
    raw = r.lrange("whale:signals:recent", 0, limit - 1) or []
    result = []
    for item in raw:
        try:
            result.append(json.loads(item))
        except Exception:
            pass
    return result
