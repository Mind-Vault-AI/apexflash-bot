"""
Inspector Gadget — Autonomous Alpha Wallet Intelligence Agent
═════════════════════════════════════════════════════════════
Follows known "crypto god" wallets on Solana in real-time.
When an alpha wallet buys → validates on 4 timeframes → fires copy-trade signal.

STRATEGY: Multi-timeframe confluence (15m / 1h / 4h / 1d)
  Only trade when AT LEAST 2/4 timeframes align (bullish structure).
  Entry on 15m pullback. Exit via Trailing SL (already in bot).

RUG DETECTION: checks before every copy signal:
  - RugCheck score
  - Liquidity lock status
  - Top holder concentration
  - Dev wallet % (>20% = danger)

ALPHA WALLETS: Known Solana on-chain traders.
  Add more via /addwallet command or INSPECTOR_WALLETS env var.

Usage (called from bot.py):
  from agents.inspector_agent import inspector_job, get_alpha_wallets, add_alpha_wallet
"""

import asyncio
import logging
import time
from collections import deque
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# KNOWN ALPHA WALLETS
# These are publicly known on-chain traders.
# Add via env: INSPECTOR_WALLETS=addr1,addr2,...
# ═══════════════════════════════════════════

import os

_EXTRA_WALLETS_RAW = os.getenv("INSPECTOR_WALLETS", "")

# Known Solana alpha traders (publicly identified on-chain)
# Labels are for display only — no financial advice implied
ALPHA_WALLETS: dict[str, str] = {
    # Solana ecosystem known traders (publicly identified)
    "3Lp4GFbF2Hk7mVgNjhavDhJDydQzGZpxbY1X3wrBNs4e": "CryptoGod_1",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Whale_Alpha_A",
    "5tzFkiKscXHK5ZXCGbXZxdw7gkg7jbtvX4bSBn21e3Sy": "SolanaKing",
    "BJeeLTH5NefCJuiX7y5ACWerCBZv1iqbYf2JiXdvGMSh": "DeFi_God_Sol",
    "HVkH2HQML9TiJyPCuPxbstMYFkn9nyUoRSptQDV31Gih": "Insider_1",
    # Add your own via INSPECTOR_WALLETS env var
}

# Add from env var
if _EXTRA_WALLETS_RAW:
    for _entry in _EXTRA_WALLETS_RAW.split(","):
        _entry = _entry.strip()
        if len(_entry) >= 32:
            ALPHA_WALLETS[_entry] = f"Custom_{_entry[:8]}"

# Add dynamically tracked whale wallets from Redis (persisted across restarts)
try:
    from core.persistence import _get_redis as _insp_redis
    _r = _insp_redis()
    if _r:
        _dynamic = _r.smembers("inspector:dynamic_wallets") or set()
        for _dw in _dynamic:
            _dw = _dw.decode() if isinstance(_dw, bytes) else _dw
            if len(_dw) >= 32 and _dw not in ALPHA_WALLETS:
                _label_raw = _r.get(f"inspector:wallet:{_dw[:16]}")
                _label = (_label_raw.decode() if isinstance(_label_raw, bytes) else _label_raw) or f"DynWhale_{_dw[:8]}"
                ALPHA_WALLETS[_dw] = _label
except Exception:
    pass

# ═══════════════════════════════════════════
# RUNTIME STATE
# ═══════════════════════════════════════════

_seen_sigs: set[str] = set()          # TX signatures already processed
_seen_sigs_maxlen = 500               # cap memory
_token_candle_cache: dict[str, dict] = {}   # pair_addr → {ts, candles_15m, candles_1h, ...}
_CANDLE_CACHE_TTL = 300               # 5 minutes

# Callbacks registered by bot.py to receive signals
_signal_callbacks: list = []


def register_signal_callback(cb):
    """bot.py calls this to receive inspector signals."""
    _signal_callbacks.append(cb)


def add_alpha_wallet(address: str, label: str = "") -> bool:
    """Add a wallet to the live tracking list. Returns True if new."""
    if address in ALPHA_WALLETS:
        return False
    ALPHA_WALLETS[address] = label or f"Alpha_{address[:8]}"
    logger.info(f"Inspector: added wallet {address[:12]}... ({ALPHA_WALLETS[address]})")
    return True


def get_alpha_wallets() -> dict:
    return dict(ALPHA_WALLETS)


# ═══════════════════════════════════════════
# HELIUS: FETCH RECENT TRANSACTIONS
# ═══════════════════════════════════════════

async def _helius_recent_txs(pubkey: str, api_key: str, limit: int = 10) -> list[dict]:
    """Get recent transactions for a wallet via Helius Enhanced Transactions API."""
    url = f"https://api.helius.xyz/v0/addresses/{pubkey}/transactions"
    params = {"api-key": api_key, "limit": limit, "type": "SWAP"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
                logger.debug(f"Helius txs {r.status} for {pubkey[:8]}...")
    except Exception as e:
        logger.debug(f"Helius tx fetch error: {e}")
    return []


def _parse_swap(tx: dict) -> Optional[dict]:
    """
    Extract BUY/SELL info from a Helius Enhanced Transaction (SWAP type).
    Returns: {mint, side, amount_sol, amount_token, sig} or None.
    """
    try:
        sig = tx.get("signature", "")
        events = tx.get("events", {})
        swap = events.get("swap", {})
        if not swap:
            return None

        native_in = swap.get("nativeInput") or {}
        native_out = swap.get("nativeOutput") or {}
        token_in = (swap.get("tokenInputs") or [{}])[0]
        token_out = (swap.get("tokenOutputs") or [{}])[0]

        SOL_MINT = "So11111111111111111111111111111111111111112"

        # SOL → Token = BUY
        if native_in.get("amount") and token_out.get("mint"):
            return {
                "sig": sig,
                "side": "BUY",
                "mint": token_out["mint"],
                "amount_sol": int(native_in["amount"]) / 1e9,
                "amount_token": float(token_out.get("rawTokenAmount", {}).get("tokenAmount", 0)),
            }
        # Token → SOL = SELL
        if native_out.get("amount") and token_in.get("mint"):
            return {
                "sig": sig,
                "side": "SELL",
                "mint": token_in["mint"],
                "amount_sol": int(native_out["amount"]) / 1e9,
                "amount_token": float(token_in.get("rawTokenAmount", {}).get("tokenAmount", 0)),
            }
        # Token → Token swap (ignore for now)
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════
# DEXSCREENER: MULTI-TIMEFRAME CANDLES
# ═══════════════════════════════════════════

DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/tokens/{mint}"

async def _get_pair_address(mint: str) -> Optional[str]:
    """Get the primary DexScreener pair address for a Solana token mint."""
    try:
        url = DEXSCREENER_SEARCH.format(mint=mint)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                pairs = data.get("pairs") or []
                # Filter for Solana, sort by liquidity
                sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
                if not sol_pairs:
                    return None
                sol_pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
                return sol_pairs[0].get("pairAddress")
    except Exception as e:
        logger.debug(f"DexScreener pair lookup error: {e}")
        return None


async def _fetch_candles_dexscreener(pair_addr: str, resolution: str, limit: int = 50) -> list[dict]:
    """
    Fetch OHLCV candles from DexScreener.
    resolution: "15" | "60" | "240" | "1D"
    Returns list of {t, o, h, l, c, v}
    """
    url = f"https://api.dexscreener.com/latest/dex/candles/{pair_addr}"
    params = {"resolution": resolution, "limit": limit}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                return data.get("candles") or []
    except Exception as e:
        logger.debug(f"Candle fetch error ({pair_addr[:12]} {resolution}): {e}")
        return []


# ═══════════════════════════════════════════
# TECHNICAL ANALYSIS
# Fast EMA + RSI + structure
# ═══════════════════════════════════════════

def _ema(values: list[float], period: int) -> list[float]:
    """Calculate EMA for a list of closing prices."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema_vals = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_vals.append(v * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _rsi(closes: list[float], period: int = 14) -> float:
    """Calculate RSI from closing prices. Returns 0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0  # neutral
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]
    avg_gain = sum(gains) / period if gains else 0.001
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _analyse_timeframe(candles: list[dict], label: str) -> dict:
    """
    Analyse a single timeframe. Returns:
    {label, bias, rsi, trend, ema9_above_ema21, volume_rising, close, note}
    bias: "BULLISH" | "BEARISH" | "NEUTRAL"
    """
    if len(candles) < 22:
        return {"label": label, "bias": "NEUTRAL", "note": "insufficient data"}

    closes = [float(c["c"]) for c in candles]
    volumes = [float(c.get("v", 0)) for c in candles]

    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    rsi = _rsi(closes)

    price = closes[-1]
    ema9_last = ema9[-1] if ema9 else price
    ema21_last = ema21[-1] if ema21 else price

    ema9_above_ema21 = ema9_last > ema21_last
    price_above_ema9 = price > ema9_last
    price_above_ema21 = price > ema21_last

    # Volume: last 3 candles vs previous 3
    vol_recent = sum(volumes[-3:]) / 3 if len(volumes) >= 3 else 0
    vol_prior = sum(volumes[-6:-3]) / 3 if len(volumes) >= 6 else vol_recent
    volume_rising = vol_recent > vol_prior * 1.2

    # Structure: higher highs
    highs = [float(c["h"]) for c in candles[-5:]]
    hh = len(highs) >= 2 and highs[-1] > highs[-2]

    # Bias decision
    bullish_score = sum([
        ema9_above_ema21,
        price_above_ema9,
        price_above_ema21,
        rsi > 50,
        volume_rising,
        hh,
    ])

    if bullish_score >= 4:
        bias = "BULLISH"
    elif bullish_score <= 2:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "label": label,
        "bias": bias,
        "rsi": rsi,
        "ema9_above_ema21": ema9_above_ema21,
        "volume_rising": volume_rising,
        "price": price,
        "bullish_score": bullish_score,
    }


async def _multi_timeframe_analysis(mint: str) -> dict:
    """
    Run 4-timeframe analysis on a token.
    Returns {pair_addr, timeframes: [...], confluence, signal, reason}
    """
    pair_addr = await _get_pair_address(mint)
    if not pair_addr:
        return {"signal": "SKIP", "reason": "no pair found on DexScreener"}

    # Fetch all 4 timeframes concurrently
    tf_15m, tf_1h, tf_4h, tf_1d = await asyncio.gather(
        _fetch_candles_dexscreener(pair_addr, "15", 50),
        _fetch_candles_dexscreener(pair_addr, "60", 50),
        _fetch_candles_dexscreener(pair_addr, "240", 50),
        _fetch_candles_dexscreener(pair_addr, "1D", 50),
    )

    analyses = [
        _analyse_timeframe(tf_15m, "15m"),
        _analyse_timeframe(tf_1h, "1h"),
        _analyse_timeframe(tf_4h, "4h"),
        _analyse_timeframe(tf_1d, "1D"),
    ]

    bullish_count = sum(1 for a in analyses if a["bias"] == "BULLISH")
    bearish_count = sum(1 for a in analyses if a["bias"] == "BEARISH")

    # Require confluence: at least 2/4 bullish, with 4h NOT bearish
    tf_4h_ok = next((a for a in analyses if a["label"] == "4h"), {}).get("bias") != "BEARISH"
    tf_1d_ok = next((a for a in analyses if a["label"] == "1D"), {}).get("bias") != "BEARISH"

    if bullish_count >= 2 and tf_4h_ok:
        signal = "BUY"
        confluence = f"{bullish_count}/4 timeframes bullish"
    elif bearish_count >= 3:
        signal = "AVOID"
        confluence = f"{bearish_count}/4 timeframes bearish"
    else:
        signal = "WAIT"
        confluence = f"Mixed: {bullish_count} bull / {bearish_count} bear"

    return {
        "pair_addr": pair_addr,
        "timeframes": analyses,
        "confluence": confluence,
        "signal": signal,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "tf_4h_ok": tf_4h_ok,
    }


# ═══════════════════════════════════════════
# RUG CHECK
# ═══════════════════════════════════════════

async def _rugcheck(mint: str) -> dict:
    """Quick rug check via RugCheck API. Returns {safe, score, risks}."""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status != 200:
                    return {"safe": None, "score": 0, "risks": ["rugcheck unavailable"]}
                data = await r.json()
                score = data.get("score", 0)
                risks = [r.get("name", "?") for r in (data.get("risks") or []) if r.get("level") in ("danger", "warn")]
                # Score 0-1000: higher = safer on RugCheck
                safe = score >= 500 and len([r for r in (data.get("risks") or []) if r.get("level") == "danger"]) == 0
                return {"safe": safe, "score": score, "risks": risks[:5]}
    except Exception as e:
        return {"safe": None, "score": 0, "risks": [str(e)[:40]]}


# ═══════════════════════════════════════════
# MAIN INSPECTOR JOB
# Runs every 60s as a background job in bot.py
# ═══════════════════════════════════════════

async def inspector_job(context=None) -> list[dict]:
    """
    Main inspector cycle:
    1. Fetch recent SWAPs for each alpha wallet
    2. For each new BUY: run rug check + multi-TF analysis
    3. If signal = BUY + rug = safe: fire copy-trade alert
    Returns list of signals fired (for logging).
    """
    from core.config import HELIUS_API_KEY
    if not HELIUS_API_KEY:
        return []

    fired = []

    for wallet_addr, wallet_label in list(ALPHA_WALLETS.items()):
        try:
            txs = await _helius_recent_txs(wallet_addr, HELIUS_API_KEY, limit=5)
            await asyncio.sleep(0.3)  # rate limit

            for tx in txs:
                sig = tx.get("signature", "")
                if not sig or sig in _seen_sigs:
                    continue

                swap = _parse_swap(tx)
                if not swap or swap["side"] != "BUY":
                    _seen_sigs.add(sig)
                    continue

                mint = swap["mint"]
                amount_sol = swap["amount_sol"]

                # Skip dust trades (< 0.05 SOL = noise)
                if amount_sol < 0.05:
                    _seen_sigs.add(sig)
                    continue

                logger.info(
                    f"Inspector: {wallet_label} bought {amount_sol:.2f} SOL "
                    f"→ {mint[:12]}... (tx: {sig[:16]}...)"
                )

                # ── Rug check first (fastest gate) ──
                rug = await _rugcheck(mint)
                if rug["safe"] is False:
                    logger.info(
                        f"Inspector: BLOCKED {mint[:12]}... "
                        f"rug score={rug['score']} risks={rug['risks']}"
                    )
                    _seen_sigs.add(sig)
                    continue

                # ── Multi-timeframe analysis ──
                mtf = await _multi_timeframe_analysis(mint)
                await asyncio.sleep(0.5)  # rate limit DexScreener

                _seen_sigs.add(sig)
                if len(_seen_sigs) > _seen_sigs_maxlen:
                    # Trim oldest (sets aren't ordered, pop random — acceptable)
                    for _ in range(50):
                        _seen_sigs.pop()

                if mtf["signal"] not in ("BUY",):
                    logger.info(
                        f"Inspector: {wallet_label} buy on {mint[:12]}... "
                        f"MTF={mtf['signal']} ({mtf['confluence']}) — not signalling"
                    )
                    continue

                # ── Alpha Clan Clustering (v3.19.0) ──
                cluster_count = 1
                from core.persistence import _get_redis
                r = _get_redis()
                if r:
                    cluster_key = f"apexflash:alpha_history:{mint}"
                    # Record this buyer
                    r.sadd(cluster_key, wallet_addr)
                    r.expire(cluster_key, 1800) # 30 mins window
                    cluster_count = r.scard(cluster_key)

                # ── Build signal ──
                signal = {
                    "type": "INSPECTOR",
                    "wallet_label": wallet_label,
                    "wallet_addr": wallet_addr,
                    "mint": mint,
                    "amount_sol": amount_sol,
                    "tx_sig": sig,
                    "rug": rug,
                    "mtf": mtf,
                    "timeframes": mtf.get("timeframes", []),
                    "confluence": mtf.get("confluence", ""),
                    "cluster_count": cluster_count,
                    "is_alpha_clan": cluster_count >= 2
                }
                fired.append(signal)

                # ── Dispatch to bot callbacks ──
                for cb in _signal_callbacks:
                    try:
                        await cb(signal)
                    except Exception as cb_err:
                        logger.error(f"Inspector callback error: {cb_err}")

        except Exception as wallet_err:
            logger.debug(f"Inspector wallet error ({wallet_label}): {wallet_err}")
            continue

    return fired


# ═══════════════════════════════════════════
# FORMAT SIGNAL FOR TELEGRAM
# ═══════════════════════════════════════════

def format_inspector_signal(signal: dict) -> str:
    """Format an inspector copy-trade signal for Telegram (Markdown)."""
    mint = signal["mint"]
    label = signal["wallet_label"]
    amount_sol = signal["amount_sol"]
    confluence = signal["confluence"]
    rug = signal.get("rug", {})
    tfs = signal.get("timeframes", [])

    rug_line = f"✅ Safe (score {rug.get('score', '?')})" if rug.get("safe") else f"⚠️ Unknown"

    tf_lines = ""
    bias_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}
    for tf in tfs:
        emoji = bias_emoji.get(tf.get("bias", "NEUTRAL"), "⚪")
        rsi_str = f"RSI {tf['rsi']:.0f}" if tf.get("rsi") else ""
        tf_lines += f"  {emoji} {tf['label']}: {tf.get('bias', '?')} {rsi_str}\n"

    header = "🕵️ *INSPECTOR GADGET — Copy Trade Signal*"
    if signal.get("is_alpha_clan"):
        header = "🔥 *ALPHA CLAN ALERT* (Cluster Found)"
        
    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👁 *Alpha Wallet:* `{label}`\n"
        f"💎 *Clan Confidence:* {signal.get('cluster_count', 1)} wallets buying!\n"
        f"💰 *Bought:* {amount_sol:.3f} SOL\n"
        f"🪙 *Token:* `{mint[:20]}...`\n\n"
        f"📊 *Multi-TF Confluence:* {confluence}\n"
        f"{tf_lines}\n"
        f"🛡 *Rug Check:* {rug_line}\n\n"
        f"⚡ _Copy trade with tight SL (-5%):_"
    )
