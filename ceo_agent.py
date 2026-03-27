"""
ceo_agent.py — Autonomous CEO Agent (TIER 1)
=============================================
Runs daily at 08:00 Amsterdam time (Europe/Amsterdam).
Reads all KPIs from Redis, uses Gemini 2.5 Flash to prioritise issues,
and sends a structured briefing to Erik via Telegram with approve/deny buttons.

TIER SYSTEM:
  TIER 1 (NOW): Shadow — Agent suggests, Erik approves via Telegram buttons.
  TIER 2 (30 days stable): Conditional — Agent acts on low-risk items + logs.
  TIER 3 (60 days stable): Autonomous — Content Agent posts, stats refresh auto.

LEAN STOP-REGEL: Is it measurable? Legal? Eliminates waste? €1M before 29-03-2028?

Usage:
  Standalone test: python ceo_agent.py --test
  Scheduler (called from bot.py): from ceo_agent import start_ceo_scheduler
"""

import asyncio
import json
import logging
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ERIK_TELEGRAM_ID = 7851853521
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

AMS = ZoneInfo("Europe/Amsterdam")

# ── Redis helpers ─────────────────────────────────────────────────────────────

def _get_redis():
    """Lazy Redis connection — reuse from persistence module."""
    try:
        from persistence import _get_redis as _r  # noqa: F401
        return _r()
    except Exception:
        return None


def _redis_get(key: str):
    r = _get_redis()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception:
        return None


def _redis_incr(key: str):
    r = _get_redis()
    if not r:
        return None
    try:
        return r.incr(key)
    except Exception:
        return None


def _redis_set(key: str, value: str, ex: int = None):
    r = _get_redis()
    if not r:
        return None
    try:
        return r.set(key, value, ex=ex)
    except Exception:
        return None


# ── Win Rate Auto-Pause (TIER 2) ──────────────────────────────────────────────

WIN_RATE_PAUSE_THRESHOLD = 60   # Pause signals if win rate drops below this %
WIN_RATE_MIN_TRADES = 5         # Minimum trades before auto-pause can trigger
CONSECUTIVE_LOSS_LIMIT = 3      # Pause after N losses in a row (early warning)


def check_win_rate_and_pause() -> dict:
    """
    TIER 2 autonomous action: read win rate from Redis.
    If win rate < threshold for >= MIN_TRADES, set signals:paused=1 in Redis.
    Returns action dict: {action: "paused"|"ok"|"skip", win_rate, total_trades}
    """
    r = _get_redis()
    if not r:
        return {"action": "skip", "reason": "no redis"}

    try:
        total = _safe_int(r.get("winrate:total_trades"))
        wins = _safe_int(r.get("winrate:wins"))
        consecutive_losses = _safe_int(r.get("winrate:consecutive_losses"))

        if total < WIN_RATE_MIN_TRADES:
            return {"action": "skip", "reason": f"only {total} trades, need {WIN_RATE_MIN_TRADES}"}

        win_rate = round(wins / total * 100, 1) if total > 0 else 0

        already_paused = _safe_int(r.get("signals:paused"))
        if already_paused:
            return {"action": "already_paused", "win_rate": win_rate, "total_trades": total}

        # Auto-pause conditions
        should_pause = (
            win_rate < WIN_RATE_PAUSE_THRESHOLD or
            consecutive_losses >= CONSECUTIVE_LOSS_LIMIT
        )

        if should_pause:
            _redis_set("signals:paused", "1")  # no expiry — Erik must resume manually
            reason = (
                f"{consecutive_losses} consecutive losses"
                if consecutive_losses >= CONSECUTIVE_LOSS_LIMIT
                else f"win rate {win_rate}% < {WIN_RATE_PAUSE_THRESHOLD}%"
            )
            logger.warning(f"CEO Agent TIER 2: signals PAUSED — {reason}")
            return {
                "action": "paused",
                "win_rate": win_rate,
                "total_trades": total,
                "consecutive_losses": consecutive_losses,
                "reason": reason,
            }

        return {"action": "ok", "win_rate": win_rate, "total_trades": total}

    except Exception as e:
        logger.error(f"Win rate check failed: {e}")
        return {"action": "skip", "reason": str(e)}


def _safe_int(val, fallback: int = 0) -> int:
    if val is None:
        return fallback
    try:
        return int(val)
    except (ValueError, TypeError):
        return fallback


def _safe_float(val, fallback: float = 0.0) -> float:
    if val is None:
        return fallback
    try:
        return float(val)
    except (ValueError, TypeError):
        return fallback


# ── KPI Collection ─────────────────────────────────────────────────────────────

def collect_kpis() -> dict:
    """
    Read all KPIs from Redis in one pass.
    Returns structured dict matching /api/ceo JSON shape.
    All values default to 0/None — never raises.
    """
    r = _get_redis()
    today_str = date.today().isoformat()

    try:
        pipe = r.pipeline() if r else None

        if pipe:
            pipe.get("platform:total_users")            # 0
            pipe.get("winrate:total_trades")             # 1
            pipe.get("winrate:wins")                     # 2
            pipe.get("winrate:total_pnl_sol")            # 3
            pipe.get("platform:trades_today")            # 4
            pipe.get(f"funnel:start:{today_str}")        # 5
            pipe.get(f"funnel:upgrade:{today_str}")      # 6
            pipe.get(f"funnel:first_trade:{today_str}")  # 7
            pipe.get("kpi:grade:A:total")                # 8
            pipe.get("kpi:grade:A:wins")                 # 9
            pipe.get("kpi:grade:B:total")                # 10
            pipe.get("kpi:grade:B:wins")                 # 11
            pipe.get("affiliate:clicks:count:bitunix")   # 12
            pipe.get("affiliate:clicks:count:mexc")      # 13
            pipe.get("affiliate:clicks:count:blofin")    # 14
            pipe.get("affiliate:clicks:count:gate")      # 15
            pipe.lrange("winrate:recent", 0, 4)          # 16
            results = pipe.execute()
        else:
            results = [None] * 17

        total_users = _safe_int(results[0])
        total_trades = _safe_int(results[1])
        wins = _safe_int(results[2])
        pnl_sol = _safe_float(results[3])
        trades_today = _safe_int(results[4])
        funnel_start = _safe_int(results[5])
        funnel_upgrade = _safe_int(results[6])
        funnel_first_trade = _safe_int(results[7])
        grade_a_total = _safe_int(results[8])
        grade_a_wins = _safe_int(results[9])
        grade_b_total = _safe_int(results[10])
        grade_b_wins = _safe_int(results[11])
        affiliate_bitunix = _safe_int(results[12])
        affiliate_mexc = _safe_int(results[13])
        affiliate_blofin = _safe_int(results[14])
        affiliate_gate = _safe_int(results[15])
        recent_raw = results[16] if isinstance(results[16], list) else []

        win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0
        conversion = round(funnel_upgrade / funnel_start * 100, 1) if funnel_start > 0 else 0
        grade_a_wr = round(grade_a_wins / grade_a_total * 100) if grade_a_total > 0 else None
        grade_b_wr = round(grade_b_wins / grade_b_total * 100) if grade_b_total > 0 else None
        total_affiliate_clicks = (
            affiliate_bitunix + affiliate_mexc + affiliate_blofin + affiliate_gate
        )

        recent_trades = []
        for item in recent_raw:
            try:
                recent_trades.append(json.loads(item))
            except Exception:
                pass

        return {
            "date": today_str,
            "users": {"total": total_users},
            "trades": {
                "total_all_time": total_trades,
                "wins": wins,
                "win_rate_pct": win_rate,
                "total_pnl_sol": round(pnl_sol, 4),
                "today": trades_today,
            },
            "funnel": {
                "starts_today": funnel_start,
                "first_trades_today": funnel_first_trade,
                "upgrades_today": funnel_upgrade,
                "conversion_pct": conversion,
            },
            "grades": {
                "A": {"total": grade_a_total, "win_rate": grade_a_wr},
                "B": {"total": grade_b_total, "win_rate": grade_b_wr},
            },
            "affiliate": {
                "total_clicks": total_affiliate_clicks,
                "bitunix": affiliate_bitunix,
                "mexc": affiliate_mexc,
                "blofin": affiliate_blofin,
                "gate": affiliate_gate,
            },
            "recent_trades": recent_trades,
        }

    except Exception as e:
        logger.error(f"CEO Agent KPI collection failed: {e}")
        return {"date": date.today().isoformat(), "error": str(e)}


# ── Gemini Prioritisation ────────────────────────────────────────────────────

def gemini_prioritise(kpis: dict) -> dict:
    """
    Call Gemini 2.5 Flash with the KPI snapshot.
    Returns structured priority list: {critical: [...], high: [...], growth: [...]}
    Falls back to rule-based if Gemini unavailable.
    """
    if not GEMINI_API_KEY:
        return _rule_based_priorities(kpis)

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""You are the CEO Agent for ApexFlash, a crypto AI trading bot platform.
Goal: €1M netto before 29-03-2028 (Erik's 50th birthday).
Current date: {kpis.get('date')}

KPI SNAPSHOT (today):
{json.dumps(kpis, indent=2, default=str)}

TARGETS:
- Win rate: >65%
- Paid conversion: >8%
- Users month 6: 12,000
- Users month 18: 50,000

CONSTRAINTS:
- VERBOD: Polymarket (KSA NL ban), ETF/stock execution (MiFID II)
- Budget: €0 extra — only free APIs or existing subscriptions
- LEAN: No features without measurable impact

Analyse the KPIs. Return ONLY valid JSON, no markdown, with this exact structure:
{{
  "critical": ["max 2 issues that block the €1M goal TODAY if not fixed"],
  "high": ["max 3 issues to fix this week"],
  "growth": ["max 2 asymmetric opportunities with highest expected ROI"],
  "revenue_mtd_eur": <estimated monthly revenue in EUR based on affiliate clicks>,
  "on_track": <true/false — is the platform on track for month 6 target of 12k users>,
  "one_liner": "<one sentence status for Erik, max 15 words>"
}}"""

        resp = model.generate_content(prompt)
        text = resp.text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        return json.loads(text)

    except Exception as e:
        logger.warning(f"Gemini prioritisation failed ({e}), using rule-based fallback")
        return _rule_based_priorities(kpis)


def _rule_based_priorities(kpis: dict) -> dict:
    """Fallback priority engine — no AI needed."""
    critical, high, growth = [], [], []

    wr = kpis.get("trades", {}).get("win_rate_pct", 0)
    users = kpis.get("users", {}).get("total", 0)
    conv = kpis.get("funnel", {}).get("conversion_pct", 0)
    aff = kpis.get("affiliate", {}).get("total_clicks", 0)

    if wr > 0 and wr < 60:
        critical.append(f"Win rate {wr}% is CRITICAL — pause Grade C/D signals immediately")
    if wr == 0:
        critical.append("Win rate = 0% — no trade data in Redis, KPI tracking not active")

    if users < 500:
        critical.append(f"Only {users} users — need 12k by month 6, organic growth needed NOW")
    elif users < 3000:
        high.append(f"{users} users vs 12k target — accelerate Reddit + Discord content")

    if conv == 0:
        high.append("Paid conversion = 0% (not measured yet) — link Gumroad webhook to Redis")
    elif conv < 8:
        high.append(f"Paid conversion {conv}% below 8% target — A/B test pricing CTA")

    if aff == 0:
        high.append("Affiliate clicks = 0 — verify tracking keys in Redis after next deploy")

    growth.append("War Watch (geopolitics → commodity-perps) — zero competitors, €0 cost")
    growth.append("Discord webhook auto-posting — viral loop, free, builds community moat")

    revenue_est = round(aff * 0.5)
    on_track = users >= 1000

    return {
        "critical": critical[:2],
        "high": high[:3],
        "growth": growth[:2],
        "revenue_mtd_eur": revenue_est,
        "on_track": on_track,
        "one_liner": f"{users} users, {wr}% win rate — {'on track' if on_track else 'behind target'}",
    }


# ── Briefing Formatter ────────────────────────────────────────────────────────

def format_briefing(kpis: dict, priorities: dict) -> str:
    """Format the CEO briefing Telegram message (Markdown)."""
    now_ams = datetime.now(AMS)
    date_str = now_ams.strftime("%d %b %Y")

    users = kpis.get("users", {}).get("total", 0)
    wr = kpis.get("trades", {}).get("win_rate_pct", 0)
    trades_today = kpis.get("trades", {}).get("today", 0)
    pnl = kpis.get("trades", {}).get("total_pnl_sol", 0)
    conv = kpis.get("funnel", {}).get("conversion_pct", 0)
    aff_total = kpis.get("affiliate", {}).get("total_clicks", 0)
    revenue_mtd = priorities.get("revenue_mtd_eur", 0)
    on_track = priorities.get("on_track", False)
    one_liner = priorities.get("one_liner", "—")

    wr_status = "✅" if wr >= 65 else ("⚠️" if wr >= 55 else "🔴")
    conv_status = "✅" if conv >= 8 else ("⚠️" if conv >= 3 else "🔴")
    track_status = "✅ on track" if on_track else "❌ behind"
    wr_display = f"{wr}%" if wr > 0 else "🔴 no data"
    conv_display = f"{conv}%" if conv > 0 else "🔴 not measured"

    critical_lines = "\n".join(
        f"  {i+1}. {item}" for i, item in enumerate(priorities.get("critical", []))
    ) or "  — none 🎉"

    high_lines = "\n".join(
        f"  {i+1}. {item}" for i, item in enumerate(priorities.get("high", []))
    ) or "  — none"

    growth_lines = "\n".join(
        f"  {i+1}. {item}" for i, item in enumerate(priorities.get("growth", []))
    ) or "  — none"

    return (
        f"🤖 *ApexFlash CEO Briefing — {date_str}*\n"
        f"_{one_liner}_\n\n"
        f"📊 *KPIs (24h)*\n"
        f"├ Users actief: *{users:,}*\n"
        f"├ Win rate: *{wr_display}* (target: >65%) {wr_status}\n"
        f"├ Trades vandaag: *{trades_today}*\n"
        f"├ Totaal P/L: *{pnl:+.4f} SOL*\n"
        f"├ Affiliate clicks MTD: *{aff_total}*\n"
        f"├ Paid conversion: *{conv_display}* (target: >8%) {conv_status}\n"
        f"└ Pad naar €1M: {track_status}\n\n"
        f"🔴 *KRITIEK — fix vandaag*\n{critical_lines}\n\n"
        f"🟡 *HOOG — deze week*\n{high_lines}\n\n"
        f"🟢 *GROEI — deze sprint*\n{growth_lines}\n\n"
        f"💰 *Revenue (maand to date)*\n"
        f"├ Affiliate (geschat): €{revenue_mtd}\n"
        f"└ Gumroad: koppeling pending\n\n"
        f"📈 *Month 6 target: 12,000 users* → nu {users:,} ({track_status})\n\n"
        f"⚙️ _TIER 1 — Shadow mode. Gebruik knoppen om acties goed te keuren._"
    )


# ── Telegram Delivery ─────────────────────────────────────────────────────────

async def send_briefing(kpis: dict, priorities: dict) -> bool:
    """Send CEO briefing to Erik's Telegram with TIER 1 approve/deny buttons."""
    if not BOT_TOKEN:
        logger.error("CEO Agent: BOT_TOKEN missing")
        return False

    text = format_briefing(kpis, priorities)

    # TIER 1 inline buttons — Erik approves suggested actions
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Alles OK", callback_data="ceo:ack"),
            InlineKeyboardButton("🔴 Probleem melden", callback_data="ceo:issue"),
        ],
        [
            InlineKeyboardButton("📊 Volledige KPI dump", callback_data="ceo:full_kpi"),
            InlineKeyboardButton("⏸️ Bot pauzeren?", callback_data="ceo:pause"),
        ],
    ])

    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=ERIK_TELEGRAM_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info("CEO Agent: briefing sent to Erik")
        return True
    except Exception as e:
        logger.error(f"CEO Agent: send failed: {e}")
        return False


# ── Callback Handler (register in bot.py) ────────────────────────────────────

async def handle_ceo_callback(query, context) -> None:
    """
    Handle CEO Agent inline button callbacks.
    Register in bot.py: app.add_handler(CallbackQueryHandler(handle_ceo_callback, pattern="^ceo:"))
    """
    data = query.data

    if data == "ceo:ack":
        await query.answer("✅ Genoteerd. Tot morgen!")
        await query.edit_message_text(
            text=query.message.text + "\n\n✅ _Afgetekend door Erik_",
            parse_mode="Markdown",
        )

    elif data == "ceo:issue":
        await query.answer("🔴 Issue gemeld")
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=ERIK_TELEGRAM_ID,
            text=(
                "🔴 *Issue gemeld*\n\n"
                "Beschrijf kort wat er mis is — ik log het in Redis:\n"
                "`/report [beschrijving]`"
            ),
            parse_mode="Markdown",
        )

    elif data == "ceo:full_kpi":
        kpis = collect_kpis()
        kpi_text = json.dumps(kpis, indent=2, default=str)
        # Split if too long
        if len(kpi_text) > 3800:
            kpi_text = kpi_text[:3800] + "\n...[truncated]"
        await query.answer("📊 KPI dump...")
        await context.bot.send_message(
            chat_id=ERIK_TELEGRAM_ID,
            text=f"📊 *KPI Dump — {kpis.get('date', 'today')}*\n\n```json\n{kpi_text}\n```",
            parse_mode="Markdown",
        )

    elif data == "ceo:pause":
        await query.answer("⏸️ Bevestig in Telegram")
        await context.bot.send_message(
            chat_id=ERIK_TELEGRAM_ID,
            text=(
                "⏸️ *Bot pauzeren?*\n\n"
                "Dit stopt nieuwe buy-signalen. Bestaande trades lopen door.\n\n"
                "Typ `/admin_pause` om te bevestigen of doe niets om te annuleren."
            ),
            parse_mode="Markdown",
        )


# ── Discord Briefing ──────────────────────────────────────────────────────────

async def send_discord_briefing(kpis: dict, priorities: dict) -> bool:
    """Mirror CEO briefing to Discord #apexflash channel as a rich embed."""
    if not DISCORD_WEBHOOK_URL:
        logger.debug("CEO Agent: DISCORD_WEBHOOK_URL not set — skipping Discord")
        return False

    try:
        import aiohttp
    except ImportError:
        logger.warning("CEO Agent: aiohttp not available — Discord skipped")
        return False

    now_ams = datetime.now(AMS)
    date_str = now_ams.strftime("%d %b %Y")

    users = kpis.get("users", {}).get("total", 0)
    wr = kpis.get("trades", {}).get("win_rate_pct", 0)
    trades_today = kpis.get("trades", {}).get("today", 0)
    conv = kpis.get("funnel", {}).get("conversion_pct", 0)
    aff = kpis.get("affiliate", {}).get("total_clicks", 0)
    on_track = priorities.get("on_track", False)
    revenue = priorities.get("revenue_mtd_eur", 0)
    critical_items = priorities.get("critical", [])
    growth_items = priorities.get("growth", [])

    status_color = 0x00CC66 if on_track else 0xFF4444

    fields = [
        {"name": "👥 Users", "value": f"**{users:,}**", "inline": True},
        {"name": "📈 Win Rate", "value": f"**{wr}%**" if wr > 0 else "🔴 geen data", "inline": True},
        {"name": "🔄 Trades vandaag", "value": str(trades_today), "inline": True},
        {"name": "💸 Paid Conversie", "value": f"{conv}%" if conv > 0 else "🔴 niet gemeten", "inline": True},
        {"name": "🔗 Affiliate Clicks", "value": str(aff), "inline": True},
        {"name": "💰 Revenue MTD", "value": f"€{revenue}", "inline": True},
    ]

    if critical_items:
        fields.append({
            "name": "🔴 KRITIEK",
            "value": "\n".join(f"• {c}" for c in critical_items[:2]),
            "inline": False,
        })

    if growth_items:
        fields.append({
            "name": "🟢 GROEI",
            "value": "\n".join(f"• {g}" for g in growth_items[:2]),
            "inline": False,
        })

    embed = {
        "title": f"🤖 ApexFlash CEO Briefing — {date_str}",
        "description": priorities.get("one_liner", "—"),
        "color": status_color,
        "fields": fields,
        "footer": {"text": "ApexFlash CEO Agent TIER 1 | apexflash.pro"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    payload = {
        "content": (
            f"📊 **Daily CEO Briefing** | "
            f"{'✅ Op schema' if on_track else '❌ Achter op target'} | "
            f"Maand 6 target: 12,000 users"
        ),
        "embeds": [embed],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 204):
                    logger.info("CEO Agent: Discord briefing posted ✅")
                    return True
                body = await resp.text()
                logger.warning(f"CEO Agent Discord: {resp.status} — {body[:200]}")
                return False
    except Exception as e:
        logger.error(f"CEO Agent: Discord send failed: {e}")
        return False


# ── Scheduler Entry Point ─────────────────────────────────────────────────────

async def run_briefing() -> None:
    """Main CEO Agent task — collect KPIs, prioritise, send briefing."""
    logger.info("CEO Agent: starting daily briefing run")
    try:
        kpis = collect_kpis()
        priorities = gemini_prioritise(kpis)
        success = await send_briefing(kpis, priorities)
        await send_discord_briefing(kpis, priorities)  # Mirror to Discord #apexflash

        # Log run to Redis for audit trail
        r = _get_redis()
        if r:
            run_log = json.dumps({
                "ts": datetime.utcnow().isoformat(),
                "success": success,
                "users": kpis.get("users", {}).get("total", 0),
                "win_rate": kpis.get("trades", {}).get("win_rate_pct", 0),
                "on_track": priorities.get("on_track", False),
            })
            r.lpush("ceo:runs", run_log)
            r.ltrim("ceo:runs", 0, 29)  # keep last 30 runs

    except Exception as e:
        logger.error(f"CEO Agent run failed: {e}")
        # Notify Erik of failure
        try:
            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(
                chat_id=ERIK_TELEGRAM_ID,
                text=f"⚠️ CEO Agent: dagelijkse briefing MISLUKT\n\nFout: `{e}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass


def start_ceo_scheduler(scheduler: AsyncIOScheduler = None) -> AsyncIOScheduler:
    """
    Attach CEO Agent to an existing APScheduler, or create a new one.
    Call from bot.py after the scheduler is started.

    Usage in bot.py:
        from ceo_agent import start_ceo_scheduler
        start_ceo_scheduler(existing_scheduler)
    """
    if scheduler is None:
        scheduler = AsyncIOScheduler(timezone=AMS)

    # Daily at 08:00 Amsterdam time
    scheduler.add_job(
        run_briefing,
        CronTrigger(hour=8, minute=0, timezone=AMS),
        id="ceo_daily_briefing",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=1800,  # 30 min grace if missed
    )

    logger.info("CEO Agent: scheduled daily briefing at 08:00 Amsterdam")
    return scheduler


# ── CLI Test Mode ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if "--test" in sys.argv:
        print("CEO Agent — test run (immediate, no scheduler)")
        print("=" * 60)

        kpis = collect_kpis()
        print("KPIs collected:")
        print(json.dumps(kpis, indent=2, default=str))
        print("=" * 60)

        priorities = gemini_prioritise(kpis)
        print("Priorities (Gemini/fallback):")
        print(json.dumps(priorities, indent=2))
        print("=" * 60)

        briefing = format_briefing(kpis, priorities)
        print("Briefing preview:")
        print(briefing)
        print("=" * 60)

        if "--send" in sys.argv:
            print("Sending to Erik's Telegram...")
            asyncio.run(send_briefing(kpis, priorities))
            print("Done.")
        else:
            print("(Add --send to actually send to Telegram)")
    else:
        print("Usage: python ceo_agent.py --test [--send]")
