"""
ApexFlash — Live Scalping Monitor
────────────────────────────────────────────────────────
Tracks top Solana tokens every 30s using Jupiter Price API (free, no key).
Detects rapid momentum moves and fires scalp signals to the Telegram channel.

Signal grades:
  A  — price change ≥ 3% in 5min AND volume spike detected
  B  — price change ≥ 1.5% in 5min OR ≥ 3% in 15min
  C  — price change ≥ 1% in 5min (heads-up)

No paid API keys required. No external deps beyond aiohttp (already in bot).
"""
import logging
import time
from collections import deque

import aiohttp

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Tokens to monitor
# ──────────────────────────────────────────────
# Jupiter token mints (SOL mainnet)
SCALP_TOKENS = {
    "SOL":  "So11111111111111111111111111111111111111112",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP":  "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "WIF":  "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "RAY":  "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "PYTH": "HZ1JovNiVvGrG2Ths3BKd5cSuvU4cFuTxhkS3zM7Bqm",
}

JUPITER_PRICE_URL = "https://price.jup.ag/v6/price"
DEXPAPRIKA_URL = "https://api.dexpaprika.com/networks/solana/pools?order_by=volume_usd&sort=desc&limit=30"

# ──────────────────────────────────────────────
# Ring-buffer: last 30 price snapshots per token
# Snapshot every 30s → 30 * 30s = 15-minute window
# ──────────────────────────────────────────────
_price_history: dict[str, deque] = {sym: deque(maxlen=30) for sym in SCALP_TOKENS}
_last_volume_cache: dict[str, float] = {}
_last_volume_ts: float = 0.0
_VOLUME_TTL = 120  # seconds


async def _fetch_prices() -> dict[str, float]:
    """Fetch current USD prices for all scalp tokens via Jupiter Price API."""
    ids = ",".join(SCALP_TOKENS.values())
    url = f"{JUPITER_PRICE_URL}?ids={ids}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prices = {}
                    mint_to_sym = {v: k for k, v in SCALP_TOKENS.items()}
                    for mint, info in (data.get("data") or {}).items():
                        sym = mint_to_sym.get(mint)
                        if sym and info.get("price"):
                            prices[sym] = float(info["price"])
                    return prices
    except Exception as e:
        logger.debug(f"Scalper price fetch error: {e}")
    return {}


async def _fetch_volume_spikes() -> dict[str, float]:
    """
    Fetch 24h volume for top Solana pools via DexPaprika.
    Returns {symbol: volume_usd} for known tokens.
    """
    global _last_volume_cache, _last_volume_ts
    if _last_volume_cache and (time.time() - _last_volume_ts) < _VOLUME_TTL:
        return _last_volume_cache

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DEXPAPRIKA_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pools = data.get("pools", data) if isinstance(data, dict) else data
                    volumes: dict[str, float] = {}
                    for pool in (pools if isinstance(pools, list) else []):
                        for tok in (pool.get("tokens") or []):
                            sym = (tok.get("symbol") or "").upper()
                            if sym in SCALP_TOKENS:
                                v = pool.get("volume_usd") or 0
                                if sym not in volumes or v > volumes[sym]:
                                    volumes[sym] = float(v)
                    _last_volume_cache = volumes
                    _last_volume_ts = time.time()
                    return volumes
    except Exception as e:
        logger.debug(f"Scalper volume fetch error: {e}")
    return _last_volume_cache


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100


def _grade_signal(pct_5m: float, pct_15m: float, volume_usd: float) -> str:
    """Return signal grade A/B/C or None. 
    Grade A requires trend alignment (5m and 15m in same direction).
    """
    has_high_vol = volume_usd > 1_500_000   # $1.5M+ for Grade A (liquidity)
    has_std_vol = volume_usd > 750_000     # $0.75M+ for Grade B/C
    
    abs5 = abs(pct_5m)
    abs15 = abs(pct_15m)
    
    # ── Trend Alignment: 5m and 15m MUST point same way for Grade A ──────
    trend_aligned = (pct_5m * pct_15m) > 0

    if abs5 >= 3.0 and trend_aligned and has_high_vol:
        return "A"
    if abs5 >= 1.5 or abs15 >= 3.0:
        return "B" if has_std_vol else ""
    if abs5 >= 1.0:
        return "C" if has_std_vol else ""
    return ""


def _suggest_levels(price: float, pct: float) -> tuple[str, str]:
    """Return (target_str, stoploss_str) based on direction."""
    direction = 1 if pct > 0 else -1
    target = price * (1 + direction * 0.025)   # 2.5% target
    stoploss = price * (1 - direction * 0.015)  # 1.5% stop loss
    return _fmt_price(target), _fmt_price(stoploss)


def _fmt_price(p: float) -> str:
    if p >= 1:
        return f"${p:.4f}"
    if p >= 0.01:
        return f"${p:.6f}"
    return f"${p:.8f}"


# ──────────────────────────────────────────────
# Cooldown — don't re-alert same token within 10 min
# ──────────────────────────────────────────────
_last_alert_ts: dict[str, float] = {}
ALERT_COOLDOWN = 600  # 10 minutes per token


async def check_scalp_signals() -> list[dict]:
    """
    Fetch prices, update history, detect momentum signals.
    Returns list of signal dicts with keys:
      symbol, price, pct_5m, pct_15m, grade, target, stoploss, volume_usd, direction
    """
    now = time.time()
    prices = await _fetch_prices()
    if not prices:
        return []

    volumes = await _fetch_volume_spikes()

    signals = []
    for sym, price in prices.items():
        history = _price_history[sym]
        history.append((now, price))

        if len(history) < 3:  # Need at least 3 data points (90 seconds)
            continue

        # 5-minute window: ~10 snapshots ago (30s * 10 = 300s)
        idx_5m = max(0, len(history) - 10)
        # 15-minute window: ~30 snapshots ago
        idx_15m = 0

        price_5m_ago = history[idx_5m][1]
        price_15m_ago = history[idx_15m][1]

        pct_5m = _pct_change(price_5m_ago, price)
        pct_15m = _pct_change(price_15m_ago, price)

        vol = volumes.get(sym, 0.0)
        grade = _grade_signal(pct_5m, pct_15m, vol)

        if not grade:
            continue

        # Cooldown check
        last = _last_alert_ts.get(sym, 0)
        if now - last < ALERT_COOLDOWN:
            continue

        _last_alert_ts[sym] = now
        target, stoploss = _suggest_levels(price, pct_5m)
        direction = "📈" if pct_5m > 0 else "📉"

        signals.append({
            "symbol": sym,
            "price": price,
            "pct_5m": pct_5m,
            "pct_15m": pct_15m,
            "grade": grade,
            "target": target,
            "stoploss": stoploss,
            "volume_usd": vol,
            "direction": direction,
        })

    return signals


def format_scalp_alert(s: dict) -> str:
    """Format a scalp signal into a Telegram HTML message."""
    from config import ADMIN_IDS, SCALP_TOKENS
    ref_id = ADMIN_IDS[0] if ADMIN_IDS else 0
    mint = SCALP_TOKENS.get(s["symbol"], "")
    bot_url = f"https://t.me/ApexFlashBot?start=buy_{mint}_ref_{ref_id}" if mint else f"https://t.me/ApexFlashBot?start=ref_{ref_id}"
    
    grade_emoji = {"A": "🚨", "B": "⚡", "C": "👀"}.get(s["grade"], "📡")
    grade_label = {"A": "STRONG SCALP", "B": "MOMENTUM", "C": "WATCH"}.get(s["grade"], "SIGNAL")
    vol_str = (
        f"${s['volume_usd'] / 1e6:.1f}M" if s["volume_usd"] >= 1e6
        else f"${s['volume_usd'] / 1e3:.0f}K" if s["volume_usd"] >= 1e3
        else "—"
    )
    return (
        f"{grade_emoji} <b>Grade {s['grade']} — {grade_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{s['direction']} <b>${s['symbol']}</b>  @  <code>{_fmt_price(s['price'])}</code>\n"
        f"\n"
        f"📊 <b>5-min move:</b>  {s['pct_5m']:+.2f}%\n"
        f"📊 <b>15-min move:</b> {s['pct_15m']:+.2f}%\n"
        f"💧 <b>Pool volume:</b> {vol_str}\n"
        f"\n"
        f"🎯 <b>Target:</b>  {s['target']}\n"
        f"🛡️ <b>Stop:</b>    {s['stoploss']}\n"
        f"\n"
        f"<i>⚠️ DYOR. This is AI momentum detection, not financial advice.</i>\n"
        f"👉 <a href='{bot_url}'>1-tap trade via ApexFlash</a>"
    )
