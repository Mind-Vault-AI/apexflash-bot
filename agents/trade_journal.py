"""
ApexFlash Trade Journal + PDCA Engine
======================================
Every signal fired -> logged with entry price.
After 1h -> outcome checked via DexScreener price.
Daily PDCA report -> grade accuracy, win rate, threshold recommendations.

PDCA cycle:
  Plan  -- set grade thresholds (WHALE_GRADE_S_DEGENS etc.)
  Do    -- fire signal, optional auto-execute
  Check -- compare entry_price vs price_1h_later
  Act   -- CEO/admin receives daily PDCA report with improvement suggestions

Storage: Redis keys
  journal:signal:{uuid}  ->  JSON (entry + outcome)
  journal:daily:{date}:{grade}  ->  aggregate stats hash
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from core.persistence import _get_redis

logger = logging.getLogger("TradeJournal")

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
CHECK_DELAY_SEC = 3600  # Check outcome 1 hour after signal


# -- Log a new signal ─────────────────────────────────────────────────────────

def log_signal(sig: dict) -> Optional[str]:
    """
    Called immediately when a signal fires.
    Stores entry state; outcome is filled in later by outcome_check_loop.
    """
    r = _get_redis()
    if not r:
        return None

    entry_id = str(uuid.uuid4())[:8]
    record = {
        "id":           entry_id,
        "grade":        sig.get("grade", "?"),
        "symbol":       sig.get("symbol", "?"),
        "mint":         sig.get("mint", ""),
        "source":       sig.get("source", ""),
        "entry_price":  sig.get("price", 0),
        "chg_1h_at_signal": sig.get("chg_1h", 0),
        "smart_degens": sig.get("smart_degens", 0),
        "volume":       sig.get("volume", 0),
        "timestamp":    int(time.time()),
        "check_at":     int(time.time()) + CHECK_DELAY_SEC,
        "outcome":      None,
    }

    key = f"journal:signal:{entry_id}"
    r.setex(key, 48 * 3600, json.dumps(record))
    r.lpush("journal:pending_checks", entry_id)
    r.ltrim("journal:pending_checks", 0, 199)
    logger.info(f"JOURNAL: logged {entry_id} {sig.get('symbol')} [{sig.get('grade')}]")
    return entry_id


# -- Fetch current price from DexScreener ─────────────────────────────────────

async def _fetch_price(mint: str) -> Optional[float]:
    try:
        url = DEXSCREENER_URL.format(mint)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                pairs = data.get("pairs") or []
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
    except Exception as e:
        logger.warning(f"JOURNAL: price fetch error {mint}: {e}")
    return None


# -- Outcome checker ──────────────────────────────────────────────────────────

async def _check_outcome(record: dict) -> dict:
    price_now = await _fetch_price(record["mint"])
    entry = record.get("entry_price", 0)

    if price_now and entry and entry > 0:
        pct = (price_now - entry) / entry * 100
        outcome = "WIN" if pct >= 5 else ("LOSS" if pct <= -5 else "FLAT")
    else:
        pct = None
        outcome = "UNKNOWN"

    record["price_1h"]      = price_now
    record["pct_change_1h"] = pct
    record["outcome"]       = outcome
    record["checked_at"]    = int(time.time())
    return record


# -- Background outcome check loop ────────────────────────────────────────────

async def outcome_check_loop():
    """Runs forever. Every 5 min, resolves pending outcome checks."""
    logger.info("PDCA TradeJournal: outcome checker ONLINE")
    while True:
        try:
            r = _get_redis()
            if not r:
                await asyncio.sleep(60)
                continue

            pending = r.lrange("journal:pending_checks", 0, -1) or []
            now = int(time.time())

            for raw_id in pending:
                entry_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
                key = f"journal:signal:{entry_id}"
                raw = r.get(key)
                if not raw:
                    r.lrem("journal:pending_checks", 0, entry_id)
                    continue

                record = json.loads(raw)
                if record.get("outcome") is not None:
                    r.lrem("journal:pending_checks", 0, entry_id)
                    continue

                if now < record.get("check_at", 0):
                    continue

                record = await _check_outcome(record)
                r.setex(key, 48 * 3600, json.dumps(record))
                r.lrem("journal:pending_checks", 0, entry_id)

                # Aggregate daily stats
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                day_key = f"journal:daily:{date_str}:{record['grade']}"
                r.hincrby(day_key, "total", 1)
                if record["outcome"] == "WIN":
                    r.hincrby(day_key, "wins", 1)
                elif record["outcome"] == "LOSS":
                    r.hincrby(day_key, "losses", 1)
                r.expire(day_key, 30 * 24 * 3600)

                logger.info(
                    f"JOURNAL outcome: {record['symbol']} [{record['grade']}] "
                    f"entry={record['entry_price']:.8f} "
                    f"1h={record.get('price_1h', 'n/a')} "
                    f"-> {record['outcome']} {record.get('pct_change_1h', '?')}%"
                )

        except Exception as e:
            logger.error(f"JOURNAL outcome loop error: {e}")

        await asyncio.sleep(300)


# -- Daily PDCA report ─────────────────────────────────────────────────────────

def get_pdca_report(days: int = 7) -> str:
    """Generate PDCA performance report for last N days."""
    r = _get_redis()
    if not r:
        return "Redis unavailable"

    lines = [f"PDCA Trade Journal -- Last {days} days\n"]

    for grade in ("S", "A", "B"):
        total = wins = losses = 0
        for d in range(days):
            date_str = (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
            day_key = f"journal:daily:{date_str}:{grade}"
            data = r.hgetall(day_key) or {}
            total  += int((data.get(b"total")  or data.get("total",  0) or 0))
            wins   += int((data.get(b"wins")   or data.get("wins",   0) or 0))
            losses += int((data.get(b"losses") or data.get("losses", 0) or 0))

        if total == 0:
            lines.append(f"Grade {grade}: no data\n")
            continue
        wr = round(wins / total * 100)
        lines.append(f"Grade {grade}: {total} signals | {wins}W/{losses}L | WR {wr}%\n")

    lines.append("\nPDCA Recommendations:\n")
    lines.append("- Grade B WR < 40% -> raise WHALE_GRADE_A_DEGENS\n")
    lines.append("- Grade A WR > 70% -> lower WHALE_GRADE_S_DEGENS\n")
    lines.append("- Grade S WR < 60% -> raise WHALE_GRADE_S_PCT\n")
    return "".join(lines)


def format_pdca_report_telegram(days: int = 7) -> str:
    """Telegram-formatted PDCA report."""
    r = _get_redis()
    if not r:
        return "❌ Redis unavailable"

    lines = [f"📊 *PDCA Signal Journal — {days}d*\n━━━━━━━━━━━━━━━━\n"]
    grade_emoji = {"S": "🚨", "A": "🔥", "B": "⚡"}

    for grade in ("S", "A", "B"):
        total = wins = losses = 0
        for d in range(days):
            date_str = (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
            day_key = f"journal:daily:{date_str}:{grade}"
            data = r.hgetall(day_key) or {}
            total  += int((data.get(b"total")  or data.get("total",  0) or 0))
            wins   += int((data.get(b"wins")   or data.get("wins",   0) or 0))
            losses += int((data.get(b"losses") or data.get("losses", 0) or 0))

        em = grade_emoji.get(grade, "📊")
        if total == 0:
            lines.append(f"{em} Grade *{grade}*: _no data yet_\n")
        else:
            wr = round(wins / total * 100)
            bar = "🟢" * (wr // 20) + "⬜" * (5 - wr // 20)
            lines.append(f"{em} Grade *{grade}*: {total} signals | {wins}W/{losses}L | {bar} *{wr}%*\n")

    lines.append("\n💡 *Act:*\n")
    lines.append("B WR<40% → `WHALE_GRADE_A_DEGENS` ↑\n")
    lines.append("A WR>70% → `WHALE_GRADE_S_DEGENS` ↓\n")
    lines.append("S WR<60% → `WHALE_GRADE_S_PCT` ↑\n")
    return "".join(lines)
