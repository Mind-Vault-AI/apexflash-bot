"""
news_scanner.py — War Watch Module (Sprint 2)
=============================================
Scans NewsAPI + CryptoPanic every 10 minutes for geopolitical events
that historically correlate with crypto price moves.

War Watch logic:
  1. Detect geopolitical keywords (Iran, Hormuz, sanctions, war, etc.)
  2. Map to affected commodity/crypto pairs (Oil → BTC/ETH sell, Gold → BTC buy)
  3. Generate Grade A signal with War Watch tag
  4. Alert via Telegram + Discord

LEAN STOP-REGEL: Meetbaar (Redis warwatch:alerts), Legaal (geen US-sanctioned content),
                 Waste-vrij (gratis APIs), €1M bijdrage (competitor gap).

Usage:
  Standalone test: python news_scanner.py --test
  Scheduler: from news_scanner import start_war_watch_scheduler
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

import aiohttp

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
CRYPTOPANIC_KEY = os.getenv("CRYPTOPANIC_KEY", "")
SCAN_INTERVAL_SECONDS = 600  # 10 minutes (respects both APIs' rate limits)

# NewsAPI endpoint
NEWSAPI_URL = "https://newsapi.org/v2/everything"

# CryptoPanic endpoint (Developer v2)
CRYPTOPANIC_URL = "https://cryptopanic.com/api/developer/v2/posts/"

# ── Geopolitical Keyword → Signal Mapping ─────────────────────────────────────

# Format: keyword → {signal, assets, direction, grade, reason}
WAR_WATCH_SIGNALS = {
    # Middle East / Oil supply disruption
    "iran": {"assets": ["BTC", "ETH", "SOL"], "direction": "SELL", "grade": "B",
             "reason": "Iran tension → oil spike → risk-off → crypto sell"},
    "hormuz": {"assets": ["BTC", "ETH"], "direction": "SELL", "grade": "A",
               "reason": "Strait of Hormuz → oil supply shock → extreme risk-off"},
    "saudi": {"assets": ["BTC", "ETH"], "direction": "SELL", "grade": "B",
              "reason": "Saudi geopolitics → oil price impact → crypto risk-off"},
    "opec": {"assets": ["BTC", "ETH"], "direction": "SELL", "grade": "B",
             "reason": "OPEC cut/hike → oil market → institutional rebalancing"},

    # Sanctions / Finance
    "sanctions": {"assets": ["BTC", "USDT"], "direction": "BUY", "grade": "B",
                  "reason": "New sanctions → BTC as sanctions-bypass asset → demand spike"},
    "swift": {"assets": ["BTC", "USDT"], "direction": "BUY", "grade": "A",
              "reason": "SWIFT block → immediate crypto alternative demand"},
    "cbdc": {"assets": ["BTC"], "direction": "BUY", "grade": "B",
             "reason": "CBDC news → BTC as alternative store of value narrative"},

    # Fed / Macro
    "federal reserve": {"assets": ["BTC", "ETH", "SOL"], "direction": "BUY", "grade": "B",
                        "reason": "Fed dovish signal → liquidity injection → crypto rally"},
    "interest rate": {"assets": ["BTC", "ETH"], "direction": "BUY", "grade": "B",
                      "reason": "Rate cut signal → risk assets rally → crypto up"},
    "recession": {"assets": ["BTC"], "direction": "SELL", "grade": "B",
                  "reason": "Recession fear → risk-off → gold up, crypto down short-term"},

    # War / Conflict
    "nuclear": {"assets": ["BTC", "ETH", "SOL"], "direction": "SELL", "grade": "A",
                "reason": "Nuclear threat → extreme risk-off → flight to USD/gold"},
    "invasion": {"assets": ["BTC", "ETH"], "direction": "SELL", "grade": "A",
                 "reason": "Armed conflict → immediate risk-off selloff (Ukraine precedent)"},
    "ceasefire": {"assets": ["BTC", "ETH", "SOL"], "direction": "BUY", "grade": "B",
                  "reason": "Ceasefire → risk-on recovery → crypto bounce"},

    # Crypto-specific macro
    "etf approved": {"assets": ["BTC", "ETH"], "direction": "BUY", "grade": "A",
                     "reason": "Spot ETF approval → institutional demand flood → strong rally"},
    "sec": {"assets": ["BTC", "ETH", "SOL"], "direction": "SELL", "grade": "B",
            "reason": "SEC action → regulatory FUD → short-term dump"},
    "hack": {"assets": ["BTC", "ETH"], "direction": "SELL", "grade": "B",
             "reason": "Major hack → trust crisis → immediate sell pressure"},
    "blackrock": {"assets": ["BTC", "ETH"], "direction": "BUY", "grade": "A",
                  "reason": "BlackRock crypto move → institutional signal → strong buy"},
    "trump": {"assets": ["BTC", "SOL"], "direction": "BUY", "grade": "B",
              "reason": "Trump pro-crypto statement → regulatory optimism → rally"},
}

# ── Redis helpers ─────────────────────────────────────────────────────────────

def _get_redis():
    try:
        from persistence import _get_redis as _r
        return _r()
    except Exception:
        return None


def _log_alert(alert: dict) -> None:
    """Store alert in Redis warwatch:alerts list (keep last 100)."""
    r = _get_redis()
    if not r:
        return
    try:
        r.lpush("warwatch:alerts", json.dumps(alert, default=str))
        r.ltrim("warwatch:alerts", 0, 99)
        r.incr("warwatch:total_alerts")
    except Exception as e:
        logger.error(f"War Watch Redis log failed: {e}")


# ── News Fetchers ─────────────────────────────────────────────────────────────

async def fetch_newsapi(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch top crypto + geopolitical headlines from NewsAPI."""
    if not NEWSAPI_KEY:
        return []

    params = {
        "q": "crypto OR bitcoin OR geopolitical OR iran OR sanctions OR federal reserve",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": NEWSAPI_KEY,
    }

    try:
        async with session.get(
            NEWSAPI_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"NewsAPI {resp.status}: {await resp.text()}")
                return []
            data = await resp.json()
            articles = data.get("articles", [])
            logger.debug(f"NewsAPI: {len(articles)} articles fetched")
            return [
                {
                    "source": "newsapi",
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                }
                for a in articles
                if a.get("title")
            ]
    except Exception as e:
        logger.error(f"NewsAPI fetch error: {e}")
        return []


async def fetch_cryptopanic(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch top crypto news + sentiment from CryptoPanic."""
    if not CRYPTOPANIC_KEY:
        return []

    params = {
        "auth_token": CRYPTOPANIC_KEY,
        "filter": "hot",
        "public": "true",
    }

    try:
        async with session.get(
            CRYPTOPANIC_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"CryptoPanic {resp.status}: {await resp.text()}")
                return []
            data = await resp.json()
            posts = data.get("results", [])
            logger.debug(f"CryptoPanic: {len(posts)} posts fetched")
            return [
                {
                    "source": "cryptopanic",
                    "title": p.get("title", ""),
                    "description": "",
                    "url": p.get("url", ""),
                    "published": p.get("published_at", ""),
                    "panic_score": p.get("panic_score", 0),
                    "votes": p.get("votes", {}),
                }
                for p in posts
                if p.get("title")
            ]
    except Exception as e:
        logger.error(f"CryptoPanic fetch error: {e}")
        return []


# ── Signal Detector ───────────────────────────────────────────────────────────

def detect_war_watch_signals(articles: list[dict]) -> list[dict]:
    """
    Scan article titles for War Watch keywords.
    Returns list of signal dicts (deduplicated by keyword).
    """
    triggered: dict[str, dict] = {}  # keyword → signal (dedup)

    for article in articles:
        title_lower = (article.get("title", "") + " " + article.get("description", "")).lower()

        for keyword, signal_def in WAR_WATCH_SIGNALS.items():
            if keyword in title_lower and keyword not in triggered:
                triggered[keyword] = {
                    "keyword": keyword,
                    "assets": signal_def["assets"],
                    "direction": signal_def["direction"],
                    "grade": signal_def["grade"],
                    "reason": signal_def["reason"],
                    "headline": article.get("title", "")[:120],
                    "url": article.get("url", ""),
                    "source": article.get("source", ""),
                    "panic_score": article.get("panic_score", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tag": "WAR_WATCH",
                }

    return list(triggered.values())


# ── Alert Formatters ──────────────────────────────────────────────────────────

def format_telegram_alert(signal: dict) -> str:
    """Format War Watch signal as Telegram Markdown message."""
    grade = signal["grade"]
    direction = signal["direction"]
    assets = " | ".join(signal["assets"])
    emoji = "🟢" if direction == "BUY" else "🔴"
    grade_emoji = "⭐" if grade == "A" else "🔹"

    return (
        f"⚡ *WAR WATCH — Grade {grade} Signal*\n"
        f"{'━' * 22}\n"
        f"\n"
        f"{grade_emoji} Keyword: *{signal['keyword'].upper()}*\n"
        f"{emoji} Direction: *{direction}*\n"
        f"📊 Assets: *{assets}*\n"
        f"💡 Reden: _{signal['reason']}_\n"
        f"\n"
        f"📰 _{signal['headline']}_\n"
        f"\n"
        f"{'━' * 22}\n"
        f"🤖 ApexFlash War Watch | @ApexFlashBot"
    )


def format_discord_embed(signal: dict) -> dict:
    """Format War Watch signal as Discord embed."""
    direction = signal["direction"]
    color = 0x00CC66 if direction == "BUY" else 0xFF4444
    grade = signal["grade"]

    return {
        "content": f"⚡ **WAR WATCH — Grade {grade} Signal** | {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}",
        "embeds": [{
            "title": f"War Watch: {signal['keyword'].upper()} detected",
            "description": signal["reason"],
            "color": color,
            "fields": [
                {"name": "Grade", "value": grade, "inline": True},
                {"name": "Direction", "value": direction, "inline": True},
                {"name": "Assets", "value": " | ".join(signal["assets"]), "inline": True},
                {"name": "Headline", "value": signal["headline"][:200], "inline": False},
            ],
            "footer": {"text": "ApexFlash War Watch | apexflash.pro"},
            "timestamp": signal["timestamp"],
            "url": signal.get("url", ""),
        }],
    }


# ── Notifier ──────────────────────────────────────────────────────────────────

async def notify_signal(signal: dict, bot=None) -> None:
    """Send War Watch signal to Telegram channel + Discord."""
    from config import DISCORD_WEBHOOK_URL, ALERT_CHANNEL_ID

    text = format_telegram_alert(signal)

    # Telegram channel
    if bot and ALERT_CHANNEL_ID:
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⚡ Trade Now", url="https://t.me/ApexFlashBot"),
                InlineKeyboardButton("📊 More Signals", url="https://apexflash.pro"),
            ]])
            await bot.send_message(
                chat_id=ALERT_CHANNEL_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            logger.info(f"War Watch: Telegram alert sent for '{signal['keyword']}'")
        except Exception as e:
            logger.error(f"War Watch Telegram notify failed: {e}")

    # Discord
    if DISCORD_WEBHOOK_URL:
        try:
            payload = format_discord_embed(signal)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info(f"War Watch: Discord alert sent for '{signal['keyword']}'")
                    else:
                        logger.warning(f"War Watch Discord: {resp.status}")
        except Exception as e:
            logger.error(f"War Watch Discord notify failed: {e}")


# ── Main Scanner ──────────────────────────────────────────────────────────────

# Track already-alerted keywords to avoid spam (in-memory, resets on restart)
_alerted_keywords: set[str] = set()
_alerted_reset_time: datetime = datetime.now(timezone.utc)


async def scan_once(bot=None) -> list[dict]:
    """
    One scan cycle: fetch news → detect signals → notify.
    Returns list of triggered signals.
    """
    global _alerted_keywords, _alerted_reset_time

    # Reset dedup set every 4 hours
    now = datetime.now(timezone.utc)
    if now - _alerted_reset_time > timedelta(hours=4):
        _alerted_keywords.clear()
        _alerted_reset_time = now
        logger.debug("War Watch: dedup set reset")

    async with aiohttp.ClientSession() as session:
        newsapi_articles, cryptopanic_articles = await asyncio.gather(
            fetch_newsapi(session),
            fetch_cryptopanic(session),
        )

    all_articles = newsapi_articles + cryptopanic_articles
    logger.info(f"War Watch: {len(all_articles)} total articles scanned")

    signals = detect_war_watch_signals(all_articles)
    new_signals = [s for s in signals if s["keyword"] not in _alerted_keywords]

    for signal in new_signals:
        _alerted_keywords.add(signal["keyword"])
        _log_alert(signal)
        await notify_signal(signal, bot=bot)
        logger.info(
            f"War Watch SIGNAL: {signal['grade']} | {signal['keyword']} | "
            f"{signal['direction']} {signal['assets']}"
        )

    return new_signals


async def war_watch_loop(bot=None) -> None:
    """Continuous scanner — runs every 10 minutes."""
    logger.info("War Watch: scanner started (interval: 10 min)")
    while True:
        try:
            signals = await scan_once(bot=bot)
            if not signals:
                logger.debug("War Watch: no signals this cycle")
        except Exception as e:
            logger.error(f"War Watch loop error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


def start_war_watch(bot=None) -> asyncio.Task:
    """Start War Watch as a background asyncio task. Call from bot.py after app starts."""
    loop = asyncio.get_event_loop()
    task = loop.create_task(war_watch_loop(bot=bot))
    logger.info("War Watch: background task created")
    return task


# ── CLI Test Mode ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _test():
        print("\n=== WAR WATCH TEST ===\n")
        print(f"NewsAPI key: {'OK set' if NEWSAPI_KEY else 'MISSING'}")
        print(f"CryptoPanic key: {'OK set' if CRYPTOPANIC_KEY else 'MISSING'}")
        print()

        async with aiohttp.ClientSession() as session:
            news = await fetch_newsapi(session)
            panic = await fetch_cryptopanic(session)

        print(f"NewsAPI articles: {len(news)}")
        print(f"CryptoPanic posts: {len(panic)}")
        print()

        signals = detect_war_watch_signals(news + panic)
        if signals:
            print(f"🚨 {len(signals)} War Watch signal(s) detected:\n")
            for s in signals:
                print(f"  Grade {s['grade']} | {s['direction']} | {s['keyword'].upper()}")
                print(f"  Assets: {s['assets']}")
                print(f"  Reason: {s['reason']}")
                print(f"  Headline: {s['headline'][:80]}...")
                print()
        else:
            print("✅ No War Watch signals in current news cycle (this is normal)")

        print("=== Telegram format preview ===")
        if signals:
            print(format_telegram_alert(signals[0]))
        else:
            # Demo with a fake signal
            demo = {
                "keyword": "sanctions", "assets": ["BTC", "USDT"],
                "direction": "BUY", "grade": "A",
                "reason": "SWIFT block → immediate crypto alternative demand",
                "headline": "New sanctions block Iran from SWIFT banking system",
                "url": "https://example.com", "source": "demo",
                "panic_score": 0, "timestamp": datetime.now(timezone.utc).isoformat(),
                "tag": "WAR_WATCH",
            }
            print(format_telegram_alert(demo))

    asyncio.run(_test())
