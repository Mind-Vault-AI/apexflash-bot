"""
ApexFlash MEGA BOT - @{BOT_USERNAME}
═══════════════════════════════════════════════
The all-in-one crypto whale tracking & trading bot.

Features:
  - Real-time whale alerts (ETH, SOL)
  - Solana token swaps via Jupiter V6 (1% platform fee)
  - Copy trading via MIZAR marketplace
  - DCA bot automation via MIZAR
  - Exchange affiliate hub (50-70% fee rebates)
  - Premium tiers ($9.99/mo Pro, $29.99/mo Elite)
  - Admin dashboard with stats & broadcast

Revenue model:
  1. 1% fee on every Solana token swap (Jupiter V6)
  2. Affiliate commissions (every whale alert + exchange hub)
  3. Premium subscriptions via Gumroad (Pro $9.99, Elite $29.99)
  4. MIZAR copy trading referrals (future)

# ApexFlash v3.22.0 "Conversion Godmode"
# PDCA Cycle 14 Implementation
# ═══════════════════════════════════════════════
"""
VERSION = "3.23.34"
import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import re
import random
from datetime import datetime, timezone, time as dt_time, timedelta
import asyncio
import json
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

from core.config import (
    BOT_USERNAME,
    BOT_TOKEN, AFFILIATE_LINKS, AFFILIATE_LINKS_ACTIVE, TOOL_AFFILIATE_LINKS, ADMIN_IDS,
    GUMROAD_PRO_URL, GUMROAD_ELITE_URL, TIERS,
    GUMROAD_ACCESS_TOKEN,
    PRO_PRICE_USD, ELITE_PRICE_USD, FALLBACK_PRICES,
    SCAN_INTERVAL, WEBSITE_URL, SUPPORT_URL,
    MIZAR_REFERRAL_URL, PLATFORM_FEE_PCT,
    ETH_WHALE_WALLETS, SOL_WHALE_WALLETS,
    WALLET_ENCRYPTION_KEY, SOL_MINT,
    FEE_COLLECT_WALLET, REFERRAL_FEE_SHARE_PCT,
    TRADING_ENABLED, MAX_TRADE_SOL, MIN_SOL_RESERVE,
    AUTONOMOUS_TRADE_AMOUNT_SOL,
    MAX_SLIPPAGE_BPS, DEFAULT_SLIPPAGE_BPS,
    PRICE_IMPACT_WARN_PCT, MAX_DAILY_TRADES, TEST_TRADE_SOL,
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    TWITTER_ENABLED, ALERT_CHANNEL_ID,
)
from exchanges.chains import fetch_eth_whale_transfers, fetch_sol_whale_transfers, get_crypto_prices
from exchanges.arbitrage_scanner import scan_arbitrage, format_arbitrage_alert
from agents.viral_hooks import get_marketing_playbook
from sentiment import get_whale_alert_sentiment, format_sentiment_line
from core.wallet import (
    create_wallet, load_keypair, get_sol_balance,
    get_token_balances, collect_fee, transfer_sol,
)
from exchanges.jupiter import (
    get_quote, execute_swap, calculate_fee,
    get_token_info, search_token, get_token_chart_url, COMMON_TOKENS,
)
from agents.notifications import (
    notify_discord_whale, notify_discord_trade,
    notify_telegram_channel, notify_channel_trade,
    notify_discord_digest, notify_channel_digest,
)
from gumroad import verify_license, get_subscriber_count
from core.persistence import (
    save_users, load_users, save_stats, load_stats, export_backup, import_backup,
    track_funnel, track_token_lookup, track_token_trade, track_affiliate_click,
    update_last_active, get_popular_tokens, get_funnel_stats, get_affiliate_stats,
    track_paid_conversion, track_user_active, track_visitor, track_new_user,
    get_user_bucket, track_bucket_kpi, track_user_profit, get_leaderboard_stats,
    get_governance_config,
)
from agents.marketing import post_to_channel as marketing_post
from agents.twitter_poster import post_tweet as twitter_post, post_thread as twitter_post_thread, get_stats_text as twitter_stats_text

# ── ApexFlash Godmode Agents ──
from zero_loss_manager import auto_trader_loop
from agents.ceo_agent import start_ceo_scheduler
from whale_intent import analyze_whale_intent, can_user_analyze

# ══════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ApexFlash")

# ══════════════════════════════════════════════
# USER STORE  (persistent JSON — survives restarts)
# ══════════════════════════════════════════════
users: dict[int, dict] = load_users()
seen_tx_hashes: set[str] = set()
bot_start_time = datetime.now(timezone.utc)
# Global kill switch — mutable at runtime via /killswitch
trading_enabled: bool = TRADING_ENABLED
# Global platform stats (for social proof + digest) — loaded from disk if available
_saved_stats = load_stats()
platform_stats = _saved_stats if _saved_stats else {
    "trades_today": 0,
    "volume_today_usd": 0.0,
    "trades_total": 0,
    "volume_total_usd": 0.0,
    "last_reset": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "top_gainer_today": {"token": "", "pct": 0.0, "user_anon": ""},
    "active_traders_today": set(),
}

# Runtime health snapshot for admin SLA visibility.
RUNTIME_HEALTH = {
    "advisor_ok": None,
    "advisor_reason": "",
    "advisor_model": "",
    "advisor_checks_total": 0,
    "advisor_checks_ok": 0,
    "advisor_sla_breach": False,
    "endpoint_ok": None,
    "endpoint_failed": [],
    "endpoint_checks_total": 0,
    "endpoint_checks_ok": 0,
    "endpoint_sla_breach": False,
    "last_smoke_ts": "",
    "last_watchdog_ts": "",
    "last_ops_autocheck_ts": "",
    "ops_running": False,
    "last_ops_status": "idle",
    "last_ops_error": "",
    "sla_history": [],
    "daily_kpi_snapshots": {},
    "daily_drift_alert_active": False,
    "last_daily_drift_alert_ts": "",
    "integrity_ok": None,
    "integrity_missing_env": [],
    "integrity_affiliate_invalid": [],
    "last_integrity_ts": "",
}

RUNTIME_HEALTH_FILE = Path("data") / "runtime_health.json"
SLA_HISTORY_MAX = 120
DAILY_KPI_HISTORY_MAX_DAYS = 14
DRIFT_ADVISOR_SLA_DROP_PCT = 0.30
DRIFT_ENDPOINT_SLA_DROP_PCT = 0.30
DRIFT_VOLUME_DROP_PCT = 35.0



def _load_runtime_health() -> None:
    """Load runtime SLA/health snapshot from disk if available."""
    try:
        if not RUNTIME_HEALTH_FILE.exists():
            return
        with open(RUNTIME_HEALTH_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return
        for key in RUNTIME_HEALTH.keys():
            if key in raw:
                RUNTIME_HEALTH[key] = raw[key]
        if not isinstance(RUNTIME_HEALTH.get("sla_history"), list):
            RUNTIME_HEALTH["sla_history"] = []
        if not isinstance(RUNTIME_HEALTH.get("daily_kpi_snapshots"), dict):
            RUNTIME_HEALTH["daily_kpi_snapshots"] = {}
    except Exception as e:
        logger.warning(f"load runtime health failed: {e}")


def _save_runtime_health() -> None:
    """Persist runtime SLA/health snapshot to disk (atomic write)."""
    try:
        RUNTIME_HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = RUNTIME_HEALTH_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(RUNTIME_HEALTH, f, ensure_ascii=False)
        tmp.replace(RUNTIME_HEALTH_FILE)
    except Exception as e:
        logger.warning(f"save runtime health failed: {e}")


def _record_sla_history(source: str) -> None:
    """Append a compact SLA point to in-memory history ring buffer."""
    advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
    advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
    endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
    endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))

    advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
    endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0

    point = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source": source,
        "advisor_ok": bool(RUNTIME_HEALTH.get("advisor_ok")) if RUNTIME_HEALTH.get("advisor_ok") is not None else None,
        "endpoint_ok": bool(RUNTIME_HEALTH.get("endpoint_ok")) if RUNTIME_HEALTH.get("endpoint_ok") is not None else None,
        "advisor_sla": round(advisor_sla, 2),
        "endpoint_sla": round(endpoint_sla, 2),
        "advisor_state": "BREACH" if RUNTIME_HEALTH.get("advisor_sla_breach") else "OK",
        "endpoint_state": "BREACH" if RUNTIME_HEALTH.get("endpoint_sla_breach") else "OK",
    }

    history = RUNTIME_HEALTH.get("sla_history", [])
    if not isinstance(history, list):
        history = []
    history.append(point)
    if len(history) > SLA_HISTORY_MAX:
        history = history[-SLA_HISTORY_MAX:]
    RUNTIME_HEALTH["sla_history"] = history


def _compute_sla_percentages() -> tuple[float, float]:
    advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
    advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
    endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
    endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))
    advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
    endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0
    return advisor_sla, endpoint_sla


def _build_daily_kpi_snapshot() -> dict:
    advisor_sla, endpoint_sla = _compute_sla_percentages()
    wallets_total = 0
    for u in users.values():
        wallets_total += len(u.get("wallets", []))

    return {
        "users_total": len(users),
        "wallets_total": wallets_total,
        "trades_total": int(platform_stats.get("trades_total", 0) or 0),
        "trades_today": int(platform_stats.get("trades_today", 0) or 0),
        "volume_total_usd": float(platform_stats.get("volume_total_usd", 0.0) or 0.0),
        "volume_today_usd": float(platform_stats.get("volume_today_usd", 0.0) or 0.0),
        "advisor_sla": round(advisor_sla, 2),
        "endpoint_sla": round(endpoint_sla, 2),
    }


def _delta_line(label: str, current: float | int, previous: float | int | None, suffix: str = "") -> str:
    if previous is None:
        return f"• {label}: `{current}{suffix}` (new baseline)"
    delta = current - previous
    sign = "+" if delta >= 0 else ""
    return f"• {label}: `{current}{suffix}` ({sign}{delta}{suffix} vs yesterday)"


def _drift_signals(current: dict, previous: dict | None) -> list[str]:
    """Evaluate day-over-day KPI drift and return triggered signal lines."""
    if not isinstance(previous, dict):
        return []

    triggered = []

    prev_advisor = previous.get("advisor_sla")
    curr_advisor = current.get("advisor_sla")
    if isinstance(prev_advisor, (int, float)) and isinstance(curr_advisor, (int, float)):
        if curr_advisor < prev_advisor - DRIFT_ADVISOR_SLA_DROP_PCT:
            triggered.append(f"• Advisor SLA drop: `{prev_advisor:.2f}% -> {curr_advisor:.2f}%`")

    prev_endpoint = previous.get("endpoint_sla")
    curr_endpoint = current.get("endpoint_sla")
    if isinstance(prev_endpoint, (int, float)) and isinstance(curr_endpoint, (int, float)):
        if curr_endpoint < prev_endpoint - DRIFT_ENDPOINT_SLA_DROP_PCT:
            triggered.append(f"• Endpoint SLA drop: `{prev_endpoint:.2f}% -> {curr_endpoint:.2f}%`")

    prev_volume = previous.get("volume_total_usd")
    curr_volume = current.get("volume_total_usd")
    if isinstance(prev_volume, (int, float)) and isinstance(curr_volume, (int, float)) and prev_volume > 0:
        drop_pct = (prev_volume - curr_volume) / prev_volume * 100.0
        if drop_pct >= DRIFT_VOLUME_DROP_PCT:
            triggered.append(f"• Volume drop: `{drop_pct:.2f}%` (`${prev_volume:,.2f} -> ${curr_volume:,.2f}`)")

    return triggered


def _runtime_integrity_snapshot() -> dict:
    """Run lightweight runtime integrity checks (env + affiliate link sanity)."""
    critical_env_keys = [
        "BOT_TOKEN",
        "ADMIN_IDS",
        "UPSTASH_REDIS_URL",
        "FEE_COLLECT_WALLET",
        "WALLET_ENCRYPTION_KEY",
        "HELIUS_API_KEY",
        "ETHERSCAN_API_KEY",
    ]

    missing_env = [k for k in critical_env_keys if not os.getenv(k, "").strip()]

    affiliate_invalid = []
    for key, aff in AFFILIATE_LINKS.items():
        if not isinstance(aff, dict):
            affiliate_invalid.append(f"{key}:not_dict")
            continue
        url = str(aff.get("url") or "").strip()
        name = str(aff.get("name") or "").strip()
        commission = str(aff.get("commission") or "").strip()
        if not name:
            affiliate_invalid.append(f"{key}:missing_name")
        if not commission:
            affiliate_invalid.append(f"{key}:missing_commission")
        if not url or not url.startswith("https://"):
            affiliate_invalid.append(f"{key}:invalid_url")

    return {
        "ok": len(missing_env) == 0 and len(affiliate_invalid) == 0,
        "missing_env": missing_env[:16],
        "affiliate_invalid": affiliate_invalid[:16],
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


_load_runtime_health()

# ══════════════════════════════════════════════
# DISCLAIMER TEXT
# ══════════════════════════════════════════════

RISK_DISCLAIMER = (
    "\u26a0\ufe0f *Risk Disclaimer*\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "\n"
    "Cryptocurrency trading involves *substantial risk of loss*.\n"
    "\n"
    "\u2022 You may lose *100% of your deposited funds*\n"
    "\u2022 Past performance does not guarantee future results\n"
    "\u2022 Only trade with funds you can afford to lose\n"
    "\u2022 This bot is a *tool*, not financial advice\n"
    "\u2022 You are *solely responsible* for your trades\n"
    "\u2022 Slippage, MEV, and network issues can cause losses\n"
    "\n"
    "By using this bot, you accept full responsibility for all "
    "trading decisions and outcomes.\n"
    "\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)


# ══════════════════════════════════════════════
# RISK MANAGEMENT HELPERS
# ══════════════════════════════════════════════

def _user_daily_trades(user: dict) -> int:
    """Count trades today for rate limiting."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if user.get("last_trade_date") != today:
        user["last_trade_date"] = today
        user["trades_today"] = 0
    return user.get("trades_today", 0)


def _increment_daily_trades(user: dict) -> None:
    """Record a trade for daily limit tracking."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if user.get("last_trade_date") != today:
        user["last_trade_date"] = today
        user["trades_today"] = 0
    user["trades_today"] = user.get("trades_today", 0) + 1


def _reset_daily_stats():
    """Reset daily platform stats at midnight UTC."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if platform_stats["last_reset"] != today:
        platform_stats["trades_today"] = 0
        platform_stats["volume_today_usd"] = 0.0
        platform_stats["top_gainer_today"] = {"token": "", "pct": 0.0, "user_anon": ""}
        platform_stats["active_traders_today"] = set()
        platform_stats["last_reset"] = today


def _record_trade(user_id: int, user: dict, side: str, token_name: str,
                  token_mint: str, sol_amount: float, usd_value: float,
                  tx_sig: str, entry_price_usd: float = 0.0):
    """Record a trade for history, PnL, leaderboard, and platform stats."""
    _reset_daily_stats()

    trade = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "side": side,  # "BUY" or "SELL"
        "token": token_name,
        "mint": token_mint,
        "sol": sol_amount,
        "usd": usd_value,
        "tx": tx_sig,
        "entry_price_usd": entry_price_usd,
    }

    # User trade history (keep last 50)
    if "trade_history" not in user:
        user["trade_history"] = []
    user["trade_history"].append(trade)
    if len(user["trade_history"]) > 50:
        user["trade_history"] = user["trade_history"][-50:]

    # Platform stats
    platform_stats["trades_today"] += 1
    platform_stats["trades_total"] += 1
    platform_stats["volume_today_usd"] += usd_value
    platform_stats["volume_total_usd"] += usd_value
    platform_stats["active_traders_today"].add(user_id)

    logger.info(f"TRADE RECORDED: {side} {sol_amount} SOL for {token_name} by user {user_id}")


def _get_price_impact(quote: dict) -> float:
    """Extract price impact percentage from Jupiter quote."""
    try:
        impact = quote.get("priceImpactPct")
        if impact is not None:
            return abs(float(impact)) * 100
    except (ValueError, TypeError):
        pass
    return 0.0


def get_user(user_id: int) -> dict:
    """Get or create user profile."""
    if user_id not in users:
        users[user_id] = {
            "tier": "free",
            "alerts_on": False,
            "chains": ["ETH"],
            "joined": datetime.now(timezone.utc).isoformat(),
            "username": "",
            # Solana wallet (created on demand)
            "wallet_pubkey": "",
            "wallet_secret_enc": "",
            # Trading stats
            "total_trades": 0,
            "total_volume_usd": 0.0,
            # Premium
            "premium_expires": "",
            "gumroad_license": "",
            # Referral
            "referred_by": 0,
            "referral_earnings": 0.0,
            "referral_count": 0,
            # State tracking
            "awaiting_input": "",
            # Risk management
            "accepted_terms": False,
            "trades_today": 0,
            "last_trade_date": "",
            "active_chain": "SOL",  # Default to Solana
        }
    # Migrate old users missing wallet/referral fields
    u = users[user_id]
    # Owner/admin must always keep full internal access
    if user_id in ADMIN_IDS:
        u["tier"] = "admin"
        u["accepted_terms"] = True  # admins never blocked by terms gate
    if "wallet_pubkey" not in u:
        u["wallet_pubkey"] = ""
        u["wallet_secret_enc"] = ""
        u["total_trades"] = 0
        u["total_volume_usd"] = 0.0
        u["referred_by"] = 0
        u["referral_earnings"] = 0.0
        u["referral_count"] = 0
    if "referral_count" not in u:
        u["referral_count"] = 0
    if "premium_expires" not in u:
        u["premium_expires"] = ""
    if "gumroad_license" not in u:
        u["gumroad_license"] = ""
    if "awaiting_input" not in u:
        u["awaiting_input"] = ""
    if "accepted_terms" not in u:
        u["accepted_terms"] = False
    if "trades_today" not in u:
        u["trades_today"] = 0
    if "last_trade_date" not in u:
        u["last_trade_date"] = ""
    if "active_chain" not in u:
        u["active_chain"] = "SOL"
    # Auto-expire premium tiers: downgrade to free when premium_expires has passed
    if u.get("tier") not in ("free", "admin"):
        exp = u.get("premium_expires") or ""
        if exp:
            try:
                if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                    logger.info(f"Tier expired for user {user_id}: {u['tier']} → free")
                    u["tier"] = "free"
                    _persist()
            except (ValueError, TypeError):
                pass
    return u


def _persist():
    """Save users + stats to disk after any mutation."""
    save_users(users)
    save_stats(platform_stats)


def is_admin(user_id: int) -> bool:
    """Check if user_id is in the ADMIN_IDS list from config."""
    # Kaizen: Convert to list of ints for safe comparison
    return user_id in ADMIN_IDS

async def _legacy_cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Helper to find Telegram ID for admin setup."""
    uid = update.effective_user.id
    await update.message.reply_text(
        f"\U0001f194 *Your Telegram ID:*\n`{uid}`\n\n"
        "Add this to your `ADMIN_IDS` in `.env` to gain full access.",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# KEYBOARD BUILDERS
# ══════════════════════════════════════════════

async def _legacy_cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the top profitable ApexFlash traders."""
    from core.persistence import get_leaderboard_stats
    stats = get_leaderboard_stats(limit=10)
    
    if not stats:
        await update.message.reply_text("🏆 *Leaderboard is warming up...*\nNo trades tracked yet!", parse_mode="Markdown")
        return
        
    lines = []
    emojis = ["🥇", "🥈", "🥉", "👤", "👤", "👤", "👤", "👤", "👤", "👤"]
    for i, s in enumerate(stats):
        emoji = emojis[i] if i < len(emojis) else "👤"
        uid_anon = f"User_{s['id'][-4:]}"
        lines.append(f"{emoji} *{uid_anon}*: `{float(s['profit']):.2f} SOL` profit")
        
    text = "\n".join(lines)
    await update.message.reply_text(
        f"🏆 *APEXFLASH GLOBAL LEADERBOARD*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Top profitable users (all-time):\n\n"
        f"{text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 _Trade like a whale. ApexFlash v{VERSION}_",
        parse_mode="Markdown"
    )

def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    from core.i18n import get_text
    user = get_user(user_id)
    lang = user.get("language_code", "en")
    
    kb = [
        [
            InlineKeyboardButton("\U0001f4ca " + get_text("TRADE", lang), callback_data="trade"),
            InlineKeyboardButton("\U0001f916 " + get_text("ADVISOR", lang), callback_data="cmd_advisor"),
        ],
        [InlineKeyboardButton("\U0001f4b1 Partners & Tools", callback_data="exchanges")],
        [
            InlineKeyboardButton("\U0001f680 " + get_text("AFFILIATE", lang), callback_data="referral"),
            InlineKeyboardButton("\U0001f48e " + get_text("PREMIUM", lang), callback_data="premium"),
        ],
        [
            InlineKeyboardButton("\U0001f504 Base/SOL Network", callback_data="switch_network"),
            InlineKeyboardButton("\U0001f5e3 " + get_text("LANGUAGE", lang), callback_data="language_menu"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def _back_main() -> list:
    """Single back-to-main button row."""
    return [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="main")]


def _autotrade_enabled_flag() -> bool:
    """Redis-backed runtime toggle. Defaults to enabled."""
    try:
        from core.persistence import _get_redis
        r = _get_redis()
        if not r:
            return True
        raw = str(r.get("apexflash:autotrade:enabled") or "1").strip().lower()
        return raw not in ("0", "false", "off", "no")
    except Exception:
        return True


def _set_autotrade_enabled_flag(enabled: bool) -> None:
    try:
        from core.persistence import _get_redis
        r = _get_redis()
        if r:
            r.set("apexflash:autotrade:enabled", "1" if enabled else "0")
    except Exception:
        pass


async def cmd_admin_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause auto-trading signals (Admin only)."""
    if not is_admin(update.effective_user.id): return
    from core.persistence import _get_redis
    r = _get_redis()
    if r: r.set("signals:paused", "1")
    await update.message.reply_text("⏸️ *Auto-Trading PAUSED*\nNew signals will be ignored.", parse_mode="Markdown")

async def cmd_admin_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume auto-trading signals (Admin only)."""
    if not is_admin(update.effective_user.id): return
    from core.persistence import _get_redis
    r = _get_redis()
    if r: r.set("signals:paused", "0")
    await update.message.reply_text("▶️ *Auto-Trading RESUMED*\nSearching for Grade A signals...", parse_mode="Markdown")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with main menu. Also handles referral deep links."""
    uid = update.effective_user.id
    is_new_user = uid not in users
    user = get_user(uid)
    user["username"] = update.effective_user.username or ""
    user["language_code"] = getattr(update.effective_user, "language_code", "") or ""

    # Analytics
    track_funnel("start")
    update_last_active(uid)
    track_user_active(uid)
    
    # A/B Testing Bucket Assignment
    bucket_id = get_user_bucket(uid)
    track_bucket_kpi(bucket_id, "start")
    
    # Default channel is direct; updated if ref prefix matches marketing campaigns
    visitor_channel = "direct"
    
    if is_new_user:
        track_funnel("new_user")
        track_new_user()

    # ── Handle deep links: /start ref_123456 OR /start buy_MINT_ref_123456 ──
    deep_link_mint = None  # Token to show after welcome
    if context.args:
        arg = context.args[0]

        # Format: hot (trending tokens deep link)
        if arg == "hot":
            # Show welcome first, then auto-trigger /hot after
            context.user_data["_auto_hot"] = True

        # Format: aff_EXCHANGE (trackable affiliate deep link from channel)
        elif arg.startswith("aff_"):
            exchange = arg[4:]
            track_affiliate_click(uid, exchange)
            context.user_data["_auto_aff"] = exchange
            logger.info(f"Deep link: user {uid} tracked for affiliate {exchange}")

        # Format: elite (Elite-upgrade deep link from marketing / health-check)  v3.23.18
        elif arg == "elite":
            context.user_data["_auto_elite"] = True
            track_funnel("deeplink_elite")
            logger.info(f"Deep link: user {uid} requested Elite upgrade")

        # Format: pro (Pro-upgrade deep link)  v3.23.18
        elif arg == "pro":
            context.user_data["_auto_pro"] = True
            track_funnel("deeplink_pro")
            logger.info(f"Deep link: user {uid} requested Pro upgrade")

        # Format: buy_MINTADDRESS_ref_USERID (viral token link with referral)
        elif arg.startswith("buy_"):
            parts = arg[4:]  # Remove "buy_"
            if "_ref_" in parts:
                mint_part, ref_part = parts.rsplit("_ref_", 1)
                deep_link_mint = mint_part
                try:
                    referrer_id = int(ref_part)
                    if referrer_id != uid and not user.get("referred_by"):
                        user["referred_by"] = referrer_id
                        referrer = get_user(referrer_id)
                        referrer["referral_count"] = referrer.get("referral_count", 0) + 1
                        _cur = referrer.get("premium_expires") or ""
                        try:
                            _base = datetime.fromisoformat(_cur) if _cur else datetime.now(timezone.utc)
                            if _base < datetime.now(timezone.utc):
                                _base = datetime.now(timezone.utc)
                        except (ValueError, TypeError):
                            _base = datetime.now(timezone.utc)
                        referrer["tier"] = "pro"
                        referrer["premium_expires"] = (_base + timedelta(days=7)).isoformat()
                        _persist()
                        logger.info(f"Referral+Reward: user {uid} → referrer {referrer_id} +7d Pro.")
                        try:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=(
                                    "🎉 *Iemand gebruikte jouw referral link!*\n"
                                    "━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"Je hebt *7 dagen Pro* ontvangen.\n"
                                    f"Totaal uitgenodigd: *{referrer['referral_count']}*\n\n"
                                    "Meer vrienden = meer Pro tijd! 🚀"
                                ),
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
                except (ValueError, IndexError):
                    pass
            else:
                deep_link_mint = parts  # Just buy_MINT without referral

        # Format: ref_USERID (simple referral)
        elif arg.startswith("ref_"):
            try:
                ref_val = arg[4:]
                # Check for marketing channel prefixes
                if ref_val.startswith("tt"): visitor_channel = "tiktok"
                elif ref_val.startswith("rl"): visitor_channel = "reels"
                elif ref_val.startswith("tg"): visitor_channel = "tg_channel"
                
                referrer_id = int(ref_val)
                if referrer_id != uid and not user.get("referred_by"):
                    user["referred_by"] = referrer_id
                    referrer = get_user(referrer_id)
                    referrer["referral_count"] = referrer.get("referral_count", 0) + 1
                    _cur2 = referrer.get("premium_expires") or ""
                    try:
                        _base2 = datetime.fromisoformat(_cur2) if _cur2 else datetime.now(timezone.utc)
                        if _base2 < datetime.now(timezone.utc):
                            _base2 = datetime.now(timezone.utc)
                    except (ValueError, TypeError):
                        _base2 = datetime.now(timezone.utc)
                    referrer["tier"] = "pro"
                    referrer["premium_expires"] = (_base2 + timedelta(days=7)).isoformat()
                    _persist()
                    logger.info(f"Referral+Reward: user {uid} → referrer {referrer_id} +7d Pro.")
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=(
                                "🎉 *Iemand gebruikte jouw referral link!*\n"
                                "━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Je hebt *7 dagen Pro* ontvangen.\n"
                                f"Totaal uitgenodigd: *{referrer['referral_count']}*\n\n"
                                "Meer vrienden = meer Pro tijd! 🚀"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
            except (ValueError, IndexError):
                pass

    # Track unique visitor globally and per channel
    track_visitor(uid, visitor_channel)

    # A/B Split Content (Variant A: Safety vs Variant B: Revenue)
    if bucket_id == 1:
        # Variant B: Revenue & Speed Focus
        welcome_header = (
            f"\u26a1 *ApexFlash MEGA BOT v{VERSION}*\n"
            "━━━━━ Institutional Speed ━━━━━\n"
        )
        tagline = "The world's fastest autonomous scalp engine. Your path to financial immunity starts here."
    else:
        # Variant A: Safety & Zero-Loss Focus
        welcome_header = (
            f"\u26a1 *ApexFlash MEGA BOT v{VERSION}*\n"
            "━━━━━ Godmode Zero-Loss ━━━━━\n"
        )
        tagline = "Protect your capital with the only bot that has a built-in Breakeven Lock. Zero-loss philosophy active."

    text = (
        f"{welcome_header}"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"{tagline}\n"
        "\n"
        "\U0001f40b *Whale Tracking* \u2014 Real-time alerts\n"
        "\U0001f4b0 *Trade* \u2014 Swap Solana tokens instantly\n"
        "\U0001f4c8 *Copy Trade* \u2014 Follow top traders\n"
        "\U0001f916 *DCA Bot* \u2014 Automate your strategy\n"
        "\U0001f4b1 *Partners & Tools* \u2014 Exchanges + crypto tools\n"
        "\U0001f91d *Referral* \u2014 Earn up to 35% of friends' fees\n"
        "\n"
        "\u26a0\ufe0f _Trading involves risk. Only trade with funds_\n"
        "_you can afford to lose._\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Select an option below:"
    )

    _persist()  # Save new user / referral link

    await update.message.reply_text(
        text,
        reply_markup=main_menu_kb(update.effective_user.id),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

    # ── New user onboarding: show exchange deals + referral link immediately ──
    if is_new_user:
        try:
            bot_username = (await context.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

            onboard_text = (
                "\U0001f525 *Quick wins before you start:*\n\n"
            )
            for aff in AFFILIATE_LINKS_ACTIVE.values():
                onboard_text += f"✅ *{aff['name']}* — {aff['commission']} fee rebate\n"

            onboard_text += (
                "\n"
                "Sign up via our links = save on every trade.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤝 *Your referral link:*\n{ref_link}\n\n"
                "_Share it — earn 25% of every trade your friends make. Forever._"
            )

            kb = []
            for key, aff in AFFILIATE_LINKS_ACTIVE.items():
                kb.append([InlineKeyboardButton(
                    f"🔗 Open {aff['name']} ({aff['commission']} rebate)", callback_data=f"aff_click_{key}"
                )])

            await update.message.reply_text(
                onboard_text,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"New user onboarding message failed: {e}")

    # ── Deep link: auto-show token buy screen if mint was in the link ──
    if deep_link_mint and SOL_ADDR_RE.match(deep_link_mint):
        try:
            token_info = await get_token_info(deep_link_mint)
            if token_info and token_info.get("symbol"):
                symbol = token_info.get("symbol", "???")
                name = token_info.get("name", "Unknown")
                decimals = token_info.get("decimals", 0)
                context.user_data["target_mint"] = deep_link_mint
                context.user_data["target_name"] = symbol
                context.user_data["target_decimals"] = decimals

                sol_bal = await get_sol_balance(user.get("wallet_pubkey", ""))
                bal_str = f"{sol_bal:.4f}" if sol_bal is not None else "N/A"

                msg = (
                    f"🔥 *{name}* ({symbol})\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🔗 `{deep_link_mint}`\n"
                    f"💼 Your SOL: *{bal_str}*\n"
                    f"💰 Fee: *{PLATFORM_FEE_PCT}%*\n\n"
                    "⬇️ *Choose buy amount:*"
                )

                kb = [
                    [InlineKeyboardButton("0.1 SOL", callback_data="buy_01"),
                     InlineKeyboardButton("0.5 SOL", callback_data="buy_05")],
                    [InlineKeyboardButton("1 SOL", callback_data="buy_1"),
                     InlineKeyboardButton("5 SOL", callback_data="buy_5")],
                    [InlineKeyboardButton("✏️ Custom", callback_data="buy_custom")],
                    [_back_main()[0]],
                ]

                # ALWAYS send as text so inline buttons (edit_message_text) work.
                # Photo messages break all callbacks — chart accessible via button.
                try:
                    chart_url = await get_token_chart_url(deep_link_mint, hours=24)
                except Exception:
                    chart_url = None
                kb_final = kb[:]
                if chart_url:
                    kb_final.insert(-1, [InlineKeyboardButton("📈 View Chart", url=chart_url)])
                await update.message.reply_text(
                    msg, reply_markup=InlineKeyboardMarkup(kb_final),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                logger.info(f"Deep link buy: user={uid} token={symbol} mint={deep_link_mint[:12]}")
        except Exception as e:
            logger.warning(f"Deep link token lookup failed: {e}")

    # ── Auto-trigger /hot if deep linked ──
    if context.user_data.pop("_auto_hot", False):
        try:
            await cmd_hot(update, context)
        except Exception as e:
            logger.warning(f"Auto-hot trigger failed: {e}")

    # ── Auto-trigger Affiliate Redirect if deep linked (Strategy Pivot v1.2) ──
    aff_key = context.user_data.pop("_auto_aff", None)
    if aff_key:
        try:
            aff_info = AFFILIATE_LINKS.get(aff_key) or AFFILIATE_LINKS.get("mexc")
            if not isinstance(aff_info, dict):
                raise ValueError("affiliate config missing")
            text = (
                f"🚀 <b>Affiliate Redirect</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You are opening <b>{aff_info['name']}</b>.\n"
                f"Benefit: <b>{aff_info['commission']} fee rebate</b>\n\n"
                f"Click below to open in your browser:"
            )
            kb = [
                [InlineKeyboardButton(f"🔗 Open {aff_info['name']}", url=aff_info["url"])],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
            ]
            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Auto-aff trigger failed: {e}")

    # ── Auto-trigger Elite Upgrade if deep linked (v3.23.18, option C: hybrid) ──
    if context.user_data.pop("_auto_elite", False):
        try:
            elite_sol = await _get_tier_price_sol("elite")
            text = (
                "\U0001f451 *Elite Upgrade \u2014 1-tap*\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                f"\n"
                f"*${ELITE_PRICE_USD}/mo \u2014 pay {elite_sol} SOL, 30 days access*\n"
                "\n"
                "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
                "\u2022 100 tracked wallets\n"
                "\u2022 AI-powered signals (Grade A/B+)\n"
                "\u2022 Copy Trading + DCA Bot\n"
                "\u2022 1-on-1 onboarding call\n"
                "\n"
                "_Instant activation on SOL payment. 0% platform fee._\n"
            )
            kb = [
                [InlineKeyboardButton(f"\U0001f451 Pay {elite_sol} SOL now", callback_data="pay_sol_elite")],
                [InlineKeyboardButton("\U0001f4b0 Compare all plans", callback_data="premium")],
                [InlineKeyboardButton("\u2b05\ufe0f Back to Menu", callback_data="main_menu")],
            ]
            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )
            track_funnel("deeplink_elite_shown")
        except Exception as e:
            logger.warning(f"Auto-elite trigger failed: {e}")

    # ── Auto-trigger Pro Upgrade if deep linked (v3.23.18) ──
    if context.user_data.pop("_auto_pro", False):
        try:
            pro_sol = await _get_tier_price_sol("pro")
            text = (
                "\U0001f680 *Pro Upgrade \u2014 1-tap*\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                f"\n"
                f"*${PRO_PRICE_USD}/mo \u2014 pay {pro_sol} SOL, 30 days access*\n"
                "\n"
                "\u2022 ETH + SOL alerts (instant)\n"
                "\u2022 20 tracked wallets\n"
                "\u2022 Copy Trading + DCA Bot\n"
                "\u2022 Priority support\n"
            )
            kb = [
                [InlineKeyboardButton(f"\U0001f680 Pay {pro_sol} SOL now", callback_data="pay_sol_pro")],
                [InlineKeyboardButton("\U0001f4b0 Compare all plans", callback_data="premium")],
                [InlineKeyboardButton("\u2b05\ufe0f Back to Menu", callback_data="main_menu")],
            ]
            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )
            track_funnel("deeplink_pro_shown")
        except Exception as e:
            logger.warning(f"Auto-pro trigger failed: {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    text = (
        f"\U0001f4d6 *Help & FAQ (v{VERSION})*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "\U0001f40b *Whale Alerts* \u2014 Track large crypto transfers\n"
        "\U0001f4c8 *Copy Trade* \u2014 Copy top traders (Pro+)\n"
        "\U0001f916 *DCA Bot* \u2014 Automated buying (Pro+)\n"
        "\U0001f4b1 *Exchanges* \u2014 Fee rebates up to 70%\n"
        "\U0001f48e *Premium* \u2014 From $9.99/mo\n"
        "\n"
        "Use /start for the main menu."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's Telegram ID (needed for admin setup)."""
    uid = update.effective_user.id
    await update.message.reply_text(
        f"\U0001f194 Your Telegram ID: `{uid}`\n\n"
        "_Send this to the bot admin to get admin access._",
        parse_mode="Markdown",
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command entry point."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return
    # Send admin panel as new message
    await _send_admin_panel(update.effective_chat.id, context)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast a message to all users with alerts on. Admin only."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/broadcast Your message here`",
            parse_mode="Markdown",
        )
        return

    message = " ".join(context.args)
    sent = 0
    failed = 0

    for uid in list(users.keys()):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"\U0001f4e2 *ApexFlash Announcement*\n\n{message}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"\u2705 Broadcast complete: {sent} delivered, {failed} failed."
    )


async def cmd_share(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Viral share command: Provides ref link + marketing copy."""
    uid = update.effective_user.id
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
    
    text = (
        "\U0001f381 *ApexFlash: Share & Win Pro*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Copy and share the message below to any crypto group. "
        "When someone joins, you automatically get **24 HOURS OF PRO STATUS**! \U0001f680\n"
        "\n"
        "\U0001f4cb *Your Viral Message:*\n"
        "```\n"
        "\U0001f40b See what Solana whales are buying BEFORE the pump! \U0001f680\n"
        "\n"
        "\U0001f916 ApexFlash AI grades every signal A-D and buys in 1-tap.\n"
        "\U0001f512 Breakeven-Lock ensures zero-loss trading.\n"
        "\n"
        "Join the 1% for FREE now: \n"
        f"{ref_link}\n"
        "```\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Users referred: *{get_user(uid).get('referral_count', 0)}*"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def _cb_share(query, user, context):
    """Callback version of share command."""
    # We call cmd_share with a mock update to reuse logic
    class MockUpdate:
        def __init__(self, query):
            self.effective_user = query.from_user
            self.effective_chat = query.message.chat
            self.message = query.message
        async def reply_text(self, *args, **kwargs):
            return await self.message.reply_text(*args, **kwargs)

    await cmd_share(MockUpdate(query), context)
    await query.answer()


async def _cb_stats(query, user, context):
    """Generic stats callback."""
    if is_admin(query.from_user.id):
        return await _cb_admin_stats(query, user, context)
    # For regular users, show referral stats
    return await _cb_referral_stats(query, user, context)


async def cmd_tweetstats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Twitter/X analytics dashboard. Admin only."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return

    stats = twitter_stats_text()
    await update.message.reply_text(stats, parse_mode="Markdown")


async def cmd_killswitch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle global trading kill switch. Admin only."""
    global trading_enabled
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return

    trading_enabled = not trading_enabled
    status = "ENABLED" if trading_enabled else "DISABLED"
    emoji = "\u2705" if trading_enabled else "\U0001f6d1"
    await update.message.reply_text(
        f"{emoji} *Trading Kill Switch*\n\n"
        f"Trading is now: *{status}*\n\n"
        f"{'All users can trade normally.' if trading_enabled else 'ALL trades are blocked until re-enabled.'}",
        parse_mode="Markdown",
    )
    logger.warning(f"KILL SWITCH: trading={trading_enabled} by admin {update.effective_user.id}")


async def cmd_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate premium with a Gumroad license key. Usage: /activate LICENSE_KEY"""
    uid = update.effective_user.id
    user = get_user(uid)

    if context.args:
        # Direct activation: /activate XXXX-XXXX-XXXX-XXXX
        license_key = context.args[0].strip()
        await _verify_and_activate(update.effective_chat.id, uid, user, license_key, context)
    else:
        # Ask for license key
        user["awaiting_input"] = "license_key"
        await update.message.reply_text(
            "\U0001f511 *Activate Premium*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            "Enter your Gumroad license key below.\n\n"
            "You received it by email after purchasing "
            "Pro or Elite on Gumroad.\n\n"
            "Format: `XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`\n\n"
            "Or use: `/activate YOUR_LICENSE_KEY`",
            parse_mode="Markdown",
        )


async def _verify_and_activate(chat_id: int, uid: int, user: dict, license_key: str, context) -> None:
    """Verify a Gumroad license key and activate premium."""
    # Clear awaiting state
    user["awaiting_input"] = ""

    await context.bot.send_message(
        chat_id=chat_id,
        text="\u23f3 Verifying license key...",
    )

    result = await verify_license(license_key)

    if result is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "\u26a0\ufe0f *Verification Error*\n\n"
                "Could not reach Gumroad API. Please try again later.\n"
                "Or contact support: /help"
            ),
            parse_mode="Markdown",
        )
        return

    if not result.get("valid"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "\u274c *Invalid License Key*\n\n"
                "This key was not recognized. Please check:\n"
                "\u2022 Copy the full key from your Gumroad email\n"
                "\u2022 Make sure there are no extra spaces\n"
                "\u2022 Keys are case-sensitive\n\n"
                "Try again: /activate YOUR_KEY\n"
                "Or buy: /start \u2192 Premium"
            ),
            parse_mode="Markdown",
        )
        return

    # Check for refunded/chargebacked
    if result.get("refunded") or result.get("chargebacked"):
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "\u274c *License Revoked*\n\n"
                "This purchase was refunded or chargebacked.\n"
                "Please purchase a new subscription."
            ),
            parse_mode="Markdown",
        )
        return

    # Activate premium
    from datetime import timedelta
    tier = result["tier"]
    tier_info = TIERS[tier]

    user["tier"] = tier
    user["premium_expires"] = (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat()
    user["gumroad_license"] = license_key

    text = (
        f"\u2705 *License Activated!*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"Plan: *{tier_info['emoji']} {tier_info['name']}*\n"
        f"Product: *{result.get('product_name', tier_info['name'])}*\n"
        f"Active for: *30 days*\n\n"
        f"\U0001f389 Welcome to {tier_info['name']}! You now have:\n"
    )
    if tier == "pro":
        text += (
            "\u2022 ETH + SOL instant alerts\n"
            "\u2022 20 tracked wallets\n"
            "\u2022 Copy Trading & DCA Bot\n"
        )
    else:
        text += (
            "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
            "\u2022 100 tracked wallets\n"
            "\u2022 AI-powered signals\n"
            "\u2022 Copy Trading & DCA Bot\n"
        )

    text += "\n\U0001f3e0 Use /start to explore your new features!"

    logger.info(f"Gumroad activation: user {uid} → {tier} (key: {license_key[:8]}...)")

    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode="Markdown",
    )

    # Social proof notification
    try:
        uname = f"User {uid}"
        await notify_discord_trade(uname, "ACTIVATE", "Gumroad License", f"{tier_info['name']} Plan", "", 0)
    except Exception:
        pass


async def _cb_switch_network(query, user, context):
    """Callback to handle switching between SOL and Base/Arbitrum."""
    user_chain = user.get("active_chain", "SOL")

    if user_chain == "SOL":
        # Callback already acknowledged in callback_handler; avoid double-answer errors.
        await query.edit_message_text(
            "🌐 *Network: Solana*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ *Current network: Solana* (primary engine)\n\n"
            "⏳ *Base & Arbitrum* — coming soon.\n"
            "You will be notified when multi-chain trading launches.\n\n"
            "_All your trades and whale signals are on Solana._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
        )
        return

    user["active_chain"] = "SOL"
    _persist()
    await query.edit_message_text(
        "✅ *Network switched back to Solana (Primary Engine).*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
    )


async def _safe_edit_message(query, text: str, reply_markup=None, parse_mode: str = "Markdown") -> None:
    """Edit message text or caption safely regardless of message type.

    Telegram does not allow edit_message_text on photo/video messages.
    This helper detects the message type and uses the correct API call,
    preventing the silent crash that makes buttons appear unresponsive.
    """
    kwargs = {"reply_markup": reply_markup, "parse_mode": parse_mode}
    try:
        if query.message and (query.message.photo or query.message.video or query.message.document):
            await query.edit_message_caption(caption=text, **kwargs)
        else:
            await query.edit_message_text(text=text, **kwargs)
    except Exception as e:
        logger.warning(f"_safe_edit_message fallback triggered: {e}")
        try:
            await query.message.reply_text(text=text, **kwargs)
        except Exception:
            pass


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline button presses to handlers."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    user["username"] = query.from_user.username or ""
    track_user_active(user_id)
    data = query.data

    routes = {
        "main":          _cb_main,
        "whale":         _cb_whale,
        "whale_on":      _cb_whale_on,
        "whale_off":     _cb_whale_off,
        "whale_latest":  _cb_whale_latest,
        "whale_top":     _cb_whale_top,
        "whale_intel":   _cb_whale_intel,
        # Trading
        "trade":         _cb_trade,
        "trade_wallet":  _cb_trade_wallet,
        "trade_create":  _cb_trade_create_wallet,
        "trade_buy":     _cb_trade_buy,
        "trade_sell":    _cb_trade_sell,
        "trade_refresh": _cb_trade_refresh_balance,
        # Copy / DCA
        "portfolio":     _cb_portfolio,
        "copy_trade":    _cb_copy_trade,
        "dca_bot":       _cb_dca_bot,
        "exchanges":     _cb_exchanges,
        "aff_exchanges": _cb_aff_exchanges,
        "aff_tools":     _cb_aff_tools,
        # Referral
        "referral":      _cb_referral,
        "referral_link": _cb_referral_link,
        "referral_stats": _cb_referral_stats,
        "premium":       _cb_premium,
        "pay_sol_pro":   _cb_pay_sol_pro,
        "pay_sol_elite": _cb_pay_sol_elite,
        "confirm_pay_pro":   _cb_confirm_pay_pro,
        "confirm_pay_elite": _cb_confirm_pay_elite,
        "activate_license": _cb_activate_license,
        "accept_terms":  _cb_accept_terms,
        "view_disclaimer": _cb_view_disclaimer,
        "leaderboard":   _cb_leaderboard,
        "settings":      _cb_settings,
        "help":          _cb_help,
        "help_faq":      _cb_help_faq,
        "help_copy":     _cb_help_copy,
        "help_dca":      _cb_help_dca,
        "admin":         _cb_admin,
        "share":         _cb_share,
        "stats":         _cb_stats,
        "admin_stats":   _cb_admin_stats,
        "admin_users":   _cb_admin_users,
        "admin_broadcast": _cb_admin_broadcast,
        "admin_autotrade": _cb_admin_autotrade,
        "admin_at_on": _cb_admin_at_on,
        "admin_at_off": _cb_admin_at_off,
        "admin_at_test_003": _cb_admin_at_test_003,
        "admin_at_test_005": _cb_admin_at_test_005,
        "admin_at_test_off": _cb_admin_at_test_off,
        "admin_at_preset_safe": _cb_admin_at_preset_safe,
        "admin_at_preset_bal": _cb_admin_at_preset_bal,
        "admin_at_preset_active": _cb_admin_at_preset_active,
        "admin_at_custom": _cb_admin_at_custom,
        "admin_pause":   _cb_admin_pause_logic,
        "admin_resume":  _cb_admin_resume_logic,
        # Withdraw
        "withdraw_start":   _cb_withdraw_start,
        "withdraw_confirm": _cb_withdraw_confirm,
        "withdraw_cancel":  _cb_trade_wallet,
        # SL/TP
        "set_sl_tp":      _cb_sl_select_start,
        "skip_sl_tp":     _cb_skip_sl_tp,
        "positions":      _cb_positions,
        "switch_network": _cb_switch_network,
        # v3.20.0 Core
        "language_menu":  _cb_language_menu,
        "set_lang_en":    _cb_set_lang_en,
        "set_lang_es":    _cb_set_lang_es,
        "set_lang_zh":    _cb_set_lang_zh,
        "set_lang_nl":    _cb_set_lang_nl,
        "cmd_advisor":    _cb_advisor,
        "advisor_upgrade_elite": _cb_advisor_upgrade_elite,
        "advisor_view_pricing": _cb_advisor_view_pricing,
    }

    # Basic dispatch for exact matches in the routes dictionary
    if data in routes:
        try:
            await routes[data](query, user, context)
        except Exception as e:
            logger.error(f"Callback error [{data}] user={user_id}: {e}")
            from traceback import format_exc
            logger.error(format_exc())
            # Silent fail to avoid user-facing noise; errors are logged for PDCA/debug.
        return

    # Handle /hot trending buy buttons — user tapped a trending token
    if data.startswith("hot_buy_"):
        mint = data[8:]  # Remove "hot_buy_" prefix
        # Prefix match against COMMON_TOKENS if truncated
        if not SOL_ADDR_RE.match(mint):
            for sym, info in COMMON_TOKENS.items():
                if info["mint"].startswith(mint):
                    mint = info["mint"]
                    break
        token_info = await get_token_info(mint)
        if token_info and token_info.get("symbol"):
            symbol = token_info.get("symbol", "???")
            context.user_data["target_mint"] = token_info.get("address", mint)
            context.user_data["target_name"] = symbol
            context.user_data["target_decimals"] = token_info.get("decimals", 0)
            sol_bal = float(await get_sol_balance(user.get("wallet_pubkey", "")) or 0.0)
            bal_str = f"{sol_bal:.4f}" if sol_bal is not None else "N/A"
            await query.edit_message_text(
                f"🔥 *{token_info.get('name', symbol)}* ({symbol})\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔗 `{mint}`\n"
                f"💼 Your SOL: *{bal_str}*\n"
                f"💰 Fee: *{PLATFORM_FEE_PCT}%*\n\n"
                "⬇️ *Choose buy amount:*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("0.1 SOL", callback_data="buy_01"),
                     InlineKeyboardButton("0.5 SOL", callback_data="buy_05")],
                    [InlineKeyboardButton("1 SOL", callback_data="buy_1"),
                     InlineKeyboardButton("5 SOL", callback_data="buy_5")],
                    [InlineKeyboardButton("✏️ Custom", callback_data="buy_custom")],
                    [_back_main()[0]],
                ]),
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                f"⚠️ Could not load token info for `{mint[:20]}...`",
                reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
                parse_mode="Markdown",
            )
        return

    # Handle /hot refresh
    if data == "cmd_hot_refresh":
        await query.edit_message_text("🔥 *Refreshing...*", parse_mode="Markdown")
        await cmd_hot(update, context)
        return

    # Handle /market refresh
    if data == "cmd_market_refresh":
        await query.edit_message_text("📊 *Refreshing market...*", parse_mode="Markdown")
        await cmd_market(update, context)
        return

    # Handle portfolio
    if data == "portfolio":
        await _cb_portfolio(query, user, context)
        return

    # Handle search result callbacks — user tapped a token from search
    if data.startswith("search_"):
        raw = data[7:]  # Remove "search_" prefix
        # Grade may be encoded as "MINT:GRADE" (from signal alerts)
        if ":" in raw:
            mint, sig_grade = raw.split(":", 1)
        else:
            mint, sig_grade = raw, ""
        context.user_data["target_signal_grade"] = sig_grade  # propagate to buy flow
        # Look up full token info and show buy buttons directly
        token_info = await get_token_info(mint)
        if token_info and token_info.get("symbol"):
            symbol = token_info.get("symbol", "???")
            name = token_info.get("name", "Unknown")
            decimals = token_info.get("decimals", 0)
            context.user_data["target_mint"] = token_info.get("address", mint)
            context.user_data["target_name"] = symbol
            context.user_data["target_decimals"] = decimals
            sol_bal = float(await get_sol_balance(user.get("wallet_pubkey", "")) or 0.0)
            prices = await get_crypto_prices()
            sol_price = float(prices.get("SOL") or 0.0)
            msg = (
                f"\U0001f3af *{name}* ({symbol})\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"\U0001f517 Mint: `{mint}`\n"
                f"\U0001f522 Decimals: {decimals}\n\n"
                f"\U0001f4bc Your SOL: *{sol_bal:.4f}*"
            )
            if sol_price:
                msg += f" (${sol_bal * sol_price:,.2f})"
            msg += (
                f"\n\U0001f4b0 Fee: *{PLATFORM_FEE_PCT}%* per trade\n\n"
                "\u2b07\ufe0f *Choose buy amount:*"
            )
            kb = [
                [InlineKeyboardButton("0.1 SOL", callback_data="buy_01"),
                 InlineKeyboardButton("0.5 SOL", callback_data="buy_05")],
                [InlineKeyboardButton("1 SOL", callback_data="buy_1"),
                 InlineKeyboardButton("5 SOL", callback_data="buy_5")],
                [InlineKeyboardButton("\u270f\ufe0f Custom Amount", callback_data="buy_custom")],
                [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
                [_back_main()[0]],
            ]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await query.edit_message_text(
                "\u26a0\ufe0f Token not found on Jupiter.",
                reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
                parse_mode="Markdown",
            )
        return

    # Handle dynamic buy/sell amount callbacks (buy_01, buy_05, buy_1, buy_5, sell_25, sell_50, sell_100)
    # These now go through confirm step first (confirm_buy_X / confirm_sell_X)
    if data.startswith("confirm_buy_"):
        try:
            actual_data = data.replace("confirm_buy_", "buy_")
            await _cb_execute_buy(query, user, context, actual_data)
            _persist()
        except Exception as e:
            logger.error(f"Buy [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Trade failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    if data == "buy_custom":
        # Prompt user to type a custom SOL amount
        context.user_data["awaiting_input"] = "custom_buy_amount"
        await _safe_edit_message(
            query,
            "\u270f\ufe0f *Custom Buy Amount*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Type your desired SOL amount (0.01 \u2013 {MAX_TRADE_SOL}):\n\n"
            "_Example: `0.25` or `3.5`_",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
            ]),
        )
        return

    if data.startswith("buy_"):
        try:
            await _cb_preview_buy(query, user, context, data)
        except Exception as e:
            logger.error(f"Buy preview [{data}] error: {e}")
            await _safe_edit_message(
                query,
                "\u26a0\ufe0f Trade failed. Use /start to return.",
            )
        return

    # sell_tok_{mint} — user selected a token from wallet list
    if data.startswith("sell_tok_"):
        try:
            await _cb_sell_token_select(query, user, context, data)
        except Exception as e:
            logger.error(f"Sell token select [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Error. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # sel_{pct}_{mint} — show sell preview/confirmation screen
    if data.startswith("sel_"):
        try:
            await _cb_preview_sell(query, user, context, data)
        except Exception as e:
            logger.error(f"Sell preview [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Trade failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # csel_{pct}_{mint} — confirmed, execute the sell
    if data.startswith("csel_"):
        try:
            await _cb_execute_sell(query, user, context, data)
            _persist()
        except Exception as e:
            logger.error(f"Sell execute [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Trade failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # Withdraw amount selection (withdraw_amt_25, withdraw_amt_50, withdraw_amt_100)
    if data.startswith("withdraw_amt_"):
        try:
            await _cb_withdraw_amount(query, user, context)
        except Exception as e:
            logger.error(f"Withdraw amount [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "⚠️ Withdrawal failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # SL/TP selection callbacks (sl_10, sl_15, sl_25, sl_none, tp_25, tp_50, tp_100, tp_none)
    if data.startswith("sl_"):
        try:
            await _cb_sl_select(query, user, context)
            _persist()
        except Exception as e:
            logger.error(f"SL select [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "⚠️ SL/TP setup failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    if data.startswith("tp_"):
        try:
            await _cb_tp_select(query, user, context)
            _persist()
        except Exception as e:
            logger.error(f"TP select [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "⚠️ SL/TP setup failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # Cancel SL/TP position (cancel_pos_0, cancel_pos_1, etc.)
    if data.startswith("cancel_pos_"):
        try:
            idx = int(data.replace("cancel_pos_", ""))
            await _cb_cancel_position(query, user, context, idx)
            _persist()
        except Exception as e:
            logger.error(f"Cancel position [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "⚠️ Cancel failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    # Static route handlers
    # Mutating actions that need persistence:
    _mutating = {
        "create_wallet", "accept_terms", "pay_sol_pro", "pay_sol_elite",
        "confirm_pay_pro", "confirm_pay_elite", "activate_license",
        "settings", "referral_link",
    }
    # CEO Agent callbacks (TIER 1 approve/deny buttons)
    if data.startswith("ceo:"):
        try:
            from agents.ceo_agent import handle_ceo_callback
            await handle_ceo_callback(query, context)
        except Exception as e:
            logger.error(f"CEO callback [{data}] error: {e}")
        return

    # aff_click_{exchange} — track affiliate click then show link
    if data.startswith("aff_click_"):
        try:
            exchange = data.replace("aff_click_", "")
            track_affiliate_click(user_id, exchange)
            aff_info = AFFILIATE_LINKS.get(exchange) or AFFILIATE_LINKS.get("mexc")
            if not isinstance(aff_info, dict):
                raise ValueError("affiliate config missing")
            
            text = (
                f"🚀 *Affiliate Redirect*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You are opening *{aff_info['name']}*.\n"
                f"Benefit: *{aff_info['commission']} fee rebate*\n\n"
                f"Click below to open in your browser:"
            )
            kb = [
                [InlineKeyboardButton(f"🔗 Open {aff_info['name']}", url=aff_info["url"])],
                [_back_main()[0]]
            ]
            await query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Affiliate tracking error: {e}")
        return

    handler = routes.get(data)
    if handler:
        try:
            await handler(query, user, context)
            if data in _mutating:
                _persist()
        except Exception as e:
            logger.error(f"Callback [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Something went wrong. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
    else:
        logger.warning(f"Unknown callback data: {data}")


# ══════════════════════════════════════════════
# NAVIGATION
# ══════════════════════════════════════════════

async def _cb_main(query, user, context):
    """Back to main menu."""
    text = (
        "\u26a1 *ApexFlash MEGA BOT*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Select an option:"
    )
    await query.edit_message_text(
        text,
        reply_markup=main_menu_kb(query.from_user.id),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# WHALE SECTION
# ══════════════════════════════════════════════

async def _cb_whale(query, user, context):
    """Whale alerts sub-menu."""
    status = "\U0001f7e2 Active" if user["alerts_on"] else "\U0001f534 Inactive"
    tier = TIERS.get(user["tier"], TIERS["free"])
    delay = "None" if tier["alert_delay"] == 0 else f"{tier['alert_delay'] // 60}min"

    text = (
        "\U0001f40b *Whale Alerts*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"Status: *{status}*\n"
        f"Chains: *{', '.join(tier['chains'])}*\n"
        f"Delay: *{delay}*\n"
        f"\n"
        "Get notified when whales move\n"
        "large amounts of crypto.\n"
        f"\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    toggle = (
        InlineKeyboardButton("\U0001f534 Turn OFF", callback_data="whale_off")
        if user["alerts_on"]
        else InlineKeyboardButton("\U0001f7e2 Turn ON", callback_data="whale_on")
    )

    kb = [
        [toggle],
        [
            InlineKeyboardButton("\U0001f4ca Top Wallets", callback_data="whale_top"),
            InlineKeyboardButton("\U0001f4b0 Latest", callback_data="whale_latest"),
        ],
        [InlineKeyboardButton("🐋 GMGN Intelligence", callback_data="whale_intel")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_whale_on(query, user, context):
    """Enable whale alerts."""
    user["alerts_on"] = True
    await query.edit_message_text(
        "\u2705 *Whale Alerts Activated!*\n"
        "\n"
        "\U0001f40b You'll be notified when whales\n"
        "make large transfers.\n"
        "\n"
        "\U0001f4a1 *Tip:* Upgrade to Pro for SOL\n"
        "alerts with zero delay \u2192 /premium",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f40b Whale Menu", callback_data="whale")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )


async def _cb_whale_off(query, user, context):
    """Disable whale alerts."""
    user["alerts_on"] = False
    await query.edit_message_text(
        "\U0001f515 *Whale Alerts Disabled*\n"
        "\n"
        "You won't receive notifications.\n"
        "Turn them back on anytime.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f7e2 Turn Back ON", callback_data="whale_on")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )


async def _cb_whale_latest(query, user, context):
    """Show latest whale transfers."""
    await query.edit_message_text(
        "\U0001f50d *Scanning whale wallets...*", parse_mode="Markdown",
    )

    prices = await get_crypto_prices()
    eth_alerts = await fetch_eth_whale_transfers()
    sol_alerts = await fetch_sol_whale_transfers()
    all_alerts = (eth_alerts + sol_alerts)[:8]

    if all_alerts:
        text = (
            "\U0001f4b0 *Latest Whale Moves*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        )
        for a in all_alerts:
            emoji = "\U0001f534" if a["direction"] == "OUT" else "\U0001f7e2"
            val = f"{a['value']:,.0f}" if a["value"] >= 100 else f"{a['value']:,.2f}"
            price = prices.get(a["symbol"], 0)
            usd = f" (${a['value'] * price:,.0f})" if price else ""
            text += f"{emoji} {val} {a['symbol']}{usd}\n"
            text += f"   {a['from_label']} \u2192 {a['to_label']}\n\n"

        text += (
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f525 Trade now on our partner exchanges:"
        )

        featured = [(k, v) for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
        aff_btns = [
            InlineKeyboardButton(f"\U0001f525 {v['name']}", url=v["url"])
            for _, v in featured[:3]
        ]

        kb = [aff_btns]
        kb.append([InlineKeyboardButton("\U0001f504 Refresh", callback_data="whale_latest")])
        kb.append([_back_main()[0]])

        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown", disable_web_page_preview=True,
        )
    else:
        await query.edit_message_text(
            "\U0001f4ca *No large transfers detected.*\n\n"
            "Whale wallets are quiet right now.\n"
            "Enable alerts to get notified instantly.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f7e2 Enable Alerts", callback_data="whale_on")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )


async def _cb_whale_top(query, user, context):
    """Show tracked whale wallets."""
    text = (
        "\U0001f4ca *Top Tracked Wallets*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "*ETH Whales:*\n"
    )
    for addr, name in list(ETH_WHALE_WALLETS.items())[:10]:
        short = f"{addr[:6]}...{addr[-4:]}"
        text += f"\u2022 {name} (`{short}`)\n"

    text += "\n*SOL Whales:*\n"
    for addr, name in list(SOL_WHALE_WALLETS.items())[:6]:
        short = f"{addr[:6]}...{addr[-4:]}"
        text += f"\u2022 {name} (`{short}`)\n"

    text += (
        f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4e1 Tracking *{len(ETH_WHALE_WALLETS)}* ETH "
        f"+ *{len(SOL_WHALE_WALLETS)}* SOL wallets\n"
        f"\U0001f48e Pro users get custom wallet tracking"
    )

    kb = [
        [InlineKeyboardButton("\U0001f4b0 Latest Moves", callback_data="whale_latest")],
        [InlineKeyboardButton("\U0001f48e Upgrade for Custom Wallets", callback_data="premium")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_whale_intel(query, user, context):
    """Show live GMGN whale intelligence — recent Grade S/A signals."""
    from agents.whale_watcher import get_whale_stats, format_whale_signal
    stats = get_whale_stats()
    if "error" in stats:
        await query.edit_message_text("❌ Redis unavailable", parse_mode="Markdown")
        return

    lines = [
        "🐋 *WHALE INTELLIGENCE — GMGN Smart Money*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n",
        f"🔌 GMGN: {'✅' if stats['gmgn_configured'] else '❌'}  |  "
        f"🤖 Auto-trade: {'✅ ' + str(stats['auto_trade_sol']) + ' SOL' if stats['auto_trade'] else '❌'}\n"
        f"⏱ Scan every {stats['scan_interval_min']} min\n\n",
        "*Recent Signals:*\n",
    ]
    recent = stats.get("recent_signals", [])
    if not recent:
        lines.append("_No signals yet — first scan runs within 5 min_\n")
    else:
        for sig in recent[:5]:
            grade_e = {"S": "🚨", "A": "🔥", "B": "⚡"}.get(sig.get("grade", ""), "📊")
            lines.append(
                f"{grade_e} [{sig.get('grade','')}] *{sig.get('symbol','?')}* "
                f"| 1h: {sig.get('chg_1h', 0):+.1f}% | 🧠{sig.get('smart_degens', 0)}\n"
            )
    text = "".join(lines)
    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="whale_intel")],
        [InlineKeyboardButton("🐋 Whale Menu", callback_data="whale")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


# ══════════════════════════════════════════════
# TRADE SECTION (Jupiter Solana Swaps)
# ══════════════════════════════════════════════

# Solana address regex (base58, 32-44 chars)
SOL_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


async def _cb_trade(query, user, context):
    """Trade sub-menu with risk management."""
    global trading_enabled

    # Kill switch check
    if not trading_enabled:
        await query.edit_message_text(
            "\U0001f6d1 *Trading Paused*\n\n"
            "Trading is temporarily disabled.\n"
            "Please try again later.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    has_wallet = bool(user.get("wallet_pubkey"))

    text = (
        "\U0001f4b0 *Solana Token Trading*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Swap any Solana token instantly\n"
        "via Jupiter aggregator.\n"
        "\n"
        "\u2705 Best price across all Solana DEXs\n"
        "\u2705 Instant execution\n"
        f"\u2705 Only {PLATFORM_FEE_PCT}% platform fee\n"
        f"\u2705 Max single trade: {MAX_TRADE_SOL} SOL\n"
        "\n"
    )

    # Live activity counter (social proof)
    _reset_daily_stats()
    active_now = len(platform_stats["active_traders_today"])
    today_count = platform_stats["trades_today"]
    if today_count > 0 or active_now > 0:
        text += (
            f"\U0001f7e2 *Live:* {active_now} traders active | "
            f"{today_count} trades today\n"
            "\n"
        )

    if has_wallet:
        short = f"{user['wallet_pubkey'][:6]}...{user['wallet_pubkey'][-4:]}"
        text += (
            f"\U0001f4bc Wallet: `{short}`\n"
            "\n"
            "*How to trade:*\n"
            "1\ufe0f\u20e3 Send SOL to your wallet address\n"
            "2\ufe0f\u20e3 Paste a token mint address in chat\n"
            "3\ufe0f\u20e3 Choose amount and confirm\n"
        )
        kb = [
            [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
            [
                InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy"),
                InlineKeyboardButton("\U0001f4b8 Sell Token", callback_data="trade_sell"),
            ],
            [InlineKeyboardButton("\U0001f504 Refresh Balance", callback_data="trade_refresh")],
            [InlineKeyboardButton("\u26a0\ufe0f Risk Disclaimer", callback_data="view_disclaimer")],
            [_back_main()[0]],
        ]
    else:
        text += (
            "\u26a0\ufe0f *No wallet yet!*\n"
            "Create a Solana wallet to start trading.\n"
            "Your keys are encrypted and stored securely.\n"
        )
        kb = [
            [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
            [_back_main()[0]],
        ]

    text += (
        "\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


async def _cb_trade_create_wallet(query, user, context):
    """Create a new Solana wallet for the user."""
    if user.get("wallet_pubkey"):
        await query.edit_message_text(
            "\u26a0\ufe0f You already have a wallet!\n\n"
            f"\U0001f4bc `{user['wallet_pubkey']}`\n\n"
            "Use \U0001f4bc My Wallet to view balance.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    if not WALLET_ENCRYPTION_KEY:
        await query.edit_message_text(
            "\u26a0\ufe0f Wallet system not configured yet.\n"
            "Please try again later.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    try:
        wallet_data = create_wallet()
        user["wallet_pubkey"] = wallet_data["pubkey"]
        user["wallet_secret_enc"] = wallet_data["encrypted_secret"]

        text = (
            "\u2705 *Wallet Created!*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f4bc *Address:*\n`{wallet_data['pubkey']}`\n"
            "\n"
            "\U0001f4b5 *Next steps:*\n"
            "1\ufe0f\u20e3 Copy the address above\n"
            "2\ufe0f\u20e3 Send SOL to it from any wallet\n"
            "3\ufe0f\u20e3 Paste a token address to trade!\n"
            "\n"
            "\U0001f512 _Your private key is encrypted and stored securely._\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )

        kb = [
            [InlineKeyboardButton("\U0001f4bc View Wallet", callback_data="trade_wallet")],
            [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            [_back_main()[0]],
        ]

        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )
        logger.info(f"Wallet created for user {query.from_user.id}: {wallet_data['pubkey']}")
        track_funnel("wallet_created")
        # CRITICAL: Instant backup — wallet = money, can't lose this
        try:
            await _send_backup_to_admin(
                context.bot,
                f"\U0001f510 WALLET CREATED — instant backup\nUser: {query.from_user.id}\nPubkey: {wallet_data['pubkey'][:20]}...\nTotal wallets: {sum(1 for u in users.values() if u.get('wallet_pubkey'))}",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Wallet creation error: {e}")
        await query.edit_message_text(
            "\u26a0\ufe0f Failed to create wallet. Please try again.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )


async def _cb_trade_wallet(query, user, context):
    """Show wallet balance and details."""
    if not user.get("wallet_pubkey"):
        await query.edit_message_text(
            "\u26a0\ufe0f No wallet found. Create one first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        "\U0001f50d *Loading wallet...*", parse_mode="Markdown",
    )

    pubkey = user["wallet_pubkey"]
    sol_bal = float(await get_sol_balance(pubkey) or 0.0)
    tokens = await get_token_balances(pubkey)
    prices = await get_crypto_prices()
    sol_price = prices.get("SOL", 0)
    sol_usd = sol_bal * sol_price

    text = (
        "\U0001f4bc *Your Wallet*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f4cb `{pubkey}`\n"
        "\n"
        f"\u25ce *SOL:* {sol_bal:.4f}"
    )
    if sol_usd > 0:
        text += f" (${sol_usd:,.2f})"
    text += "\n"

    if tokens:
        text += "\n*Tokens:*\n"
        for t in tokens[:10]:
            mint_short = f"{t['mint'][:6]}...{t['mint'][-4:]}"
            # Try to find name from COMMON_TOKENS
            token_name = None
            for sym, info in COMMON_TOKENS.items():
                if info["mint"] == t["mint"]:
                    token_name = sym
                    break
            display = token_name or mint_short
            text += f"\u2022 {display}: {t['amount']:,.4f}\n"

    # Trade stats
    total_trades = user.get("total_trades", 0)
    total_vol = user.get("total_volume_usd", 0)
    text += f"\n\U0001f4ca *Stats:* {total_trades} trades"
    if total_vol > 0:
        text += f" | ${total_vol:,.0f} volume"
    text += "\n"

    # Recent trade history (last 5)
    history = user.get("trade_history", [])
    if history:
        text += "\n\U0001f4dc *Recent Trades:*\n"
        for t in history[-5:]:
            side_emoji = "\U0001f7e2" if t["side"] == "BUY" else "\U0001f534"
            # v3.23.23: honest dust display — "0.0000 SOL" looked broken
            _v = t.get('sol', 0) or 0
            if _v >= 0.01:
                sol_str = f"{_v:.2f}"
            elif _v >= 0.0001:
                sol_str = f"{_v:.4f}"
            elif _v > 0:
                sol_str = "<0.0001"
            else:
                sol_str = "0"
            text += f"{side_emoji} {t['side']} {sol_str} SOL \u2192 {t['token']}\n"

    # Platform activity (social proof)
    _reset_daily_stats()
    active = len(platform_stats["active_traders_today"])
    today_trades = platform_stats["trades_today"]
    today_vol = platform_stats["volume_today_usd"]
    if today_trades > 0 or active > 0:
        text += (
            f"\n\U0001f30d *Platform Today:* {today_trades} trades"
            f" | {active} traders"
        )
        if today_vol > 0:
            text += f" | ${today_vol:,.0f}"
        text += "\n"

    text += (
        "\n"
        "*To trade:* Paste a Solana token\n"
        "mint address in chat!\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [
            InlineKeyboardButton("\U0001f4b5 Buy", callback_data="trade_buy"),
            InlineKeyboardButton("\U0001f4b8 Sell", callback_data="trade_sell"),
        ],
        [InlineKeyboardButton("📤 Withdraw SOL", callback_data="withdraw_start")],
        [InlineKeyboardButton("📊 Positions (SL/TP)", callback_data="positions")],
        [InlineKeyboardButton("\U0001f504 Refresh", callback_data="trade_refresh")],
        [InlineKeyboardButton("\U0001f3c6 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_trade_refresh_balance(query, user, context):
    """Alias for wallet view (refresh)."""
    await _cb_trade_wallet(query, user, context)


# ── Withdraw SOL ──────────────────────────────

async def _cb_withdraw_start(query, user, context):
    """Prompt user to enter destination address for withdrawal."""
    pubkey = user.get("wallet_pubkey")
    if not pubkey:
        await query.edit_message_text(
            "⚠️ No wallet found. Create one first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    sol_bal = float(await get_sol_balance(pubkey) or 0.0)
    available = sol_bal - MIN_SOL_RESERVE
    if available <= 0:
        await query.edit_message_text(
            f"⚠️ *Insufficient balance*\n\n"
            f"◎ Balance: {sol_bal:.4f} SOL\n"
            f"🔒 Reserved for fees: {MIN_SOL_RESERVE} SOL\n\n"
            f"You need more than {MIN_SOL_RESERVE} SOL to withdraw.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    context.user_data["awaiting_input"] = "withdraw_address"
    await query.edit_message_text(
        "📤 *Withdraw SOL*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"◎ Available: *{available:.4f} SOL*\n"
        f"🔒 Reserved: {MIN_SOL_RESERVE} SOL (tx fees)\n\n"
        "📤 *Send me the destination SOL address:*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="trade_wallet")],
        ]),
        parse_mode="Markdown",
    )


async def _cb_withdraw_amount(update_or_query, user, context):
    """Show confirmation after user selects withdraw percentage."""
    query = update_or_query
    data = query.data  # withdraw_amt_25, withdraw_amt_50, withdraw_amt_100
    pct_str = data.replace("withdraw_amt_", "")
    try:
        pct = int(pct_str)
    except ValueError:
        await query.edit_message_text("⚠️ Invalid amount. Use /start to return.", parse_mode="Markdown")
        return

    dest = context.user_data.get("withdraw_dest")
    pubkey = user.get("wallet_pubkey")
    if not dest or not pubkey:
        await query.edit_message_text(
            "⚠️ Session expired. Start a new withdrawal from your wallet.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    # Fresh balance check (security)
    sol_bal = float(await get_sol_balance(pubkey) or 0.0)
    available = sol_bal - MIN_SOL_RESERVE
    if available <= 0:
        context.user_data.pop("withdraw_dest", None)
        await query.edit_message_text(
            "⚠️ *Insufficient balance* — cannot withdraw.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            ]),
            parse_mode="Markdown",
        )
        return

    import math
    send_sol = available * (pct / 100.0)
    send_lamports = math.floor(send_sol * 1_000_000_000)
    send_display = send_lamports / 1_000_000_000

    context.user_data["withdraw_lamports"] = send_lamports

    dest_short = f"{dest[:6]}...{dest[-4:]}"
    await query.edit_message_text(
        "📤 *Confirm Withdrawal*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Amount: *{send_display:.4f} SOL*\n"
        f"📤 To: `{dest_short}`\n"
        f"📋 Full: `{dest}`\n\n"
        "⚠️ This action cannot be undone!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Send", callback_data="withdraw_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="withdraw_cancel")],
        ]),
        parse_mode="Markdown",
    )


async def _cb_withdraw_confirm(query, user, context):
    """Execute the SOL withdrawal or cancel."""
    dest = context.user_data.get("withdraw_dest")
    lamports = context.user_data.get("withdraw_lamports")
    pubkey = user.get("wallet_pubkey")
    encrypted = user.get("wallet_secret")

    # Clean up session data regardless of outcome
    def _clear_withdraw():
        context.user_data.pop("withdraw_dest", None)
        context.user_data.pop("withdraw_lamports", None)

    if not all([dest, lamports, pubkey, encrypted]):
        _clear_withdraw()
        await query.edit_message_text(
            "⚠️ Session expired. Start a new withdrawal from your wallet.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            ]),
            parse_mode="Markdown",
        )
        return

    # Final balance safety check
    sol_bal = float(await get_sol_balance(pubkey) or 0.0)
    available = sol_bal - MIN_SOL_RESERVE
    needed_sol = lamports / 1_000_000_000
    if needed_sol > available:
        _clear_withdraw()
        await query.edit_message_text(
            f"⚠️ *Balance changed!*\n\n"
            f"Requested: {needed_sol:.4f} SOL\n"
            f"Available: {available:.4f} SOL\n\n"
            "Try again with updated balance.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            ]),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text("⏳ *Processing withdrawal...*", parse_mode="Markdown")

    try:
        keypair = load_keypair(encrypted)
        tx_sig = await transfer_sol(keypair, dest, lamports)
    except Exception as e:
        logger.error(f"Withdraw error for user {user.get('user_id')}: {e}")
        _clear_withdraw()
        await query.edit_message_text(
            "❌ *Withdrawal failed*\n\n"
            f"Error: {str(e)[:100]}\n\n"
            "Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="withdraw_start")],
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            ]),
            parse_mode="Markdown",
        )
        return

    _clear_withdraw()

    if tx_sig:
        sol_sent = lamports / 1_000_000_000
        new_bal = await get_sol_balance(pubkey)
        dest_short = f"{dest[:6]}...{dest[-4:]}"
        await query.edit_message_text(
            "✅ *Withdrawal Successful!*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Sent: *{sol_sent:.4f} SOL*\n"
            f"📤 To: `{dest_short}`\n"
            f"◎ Remaining: *{new_bal:.4f} SOL*\n\n"
            f"🔗 [View on Solscan](https://solscan.io/tx/{tx_sig})",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        logger.info(f"Withdraw OK: user={user.get('user_id')} amount={sol_sent:.4f} tx={tx_sig}")
    else:
        await query.edit_message_text(
            "❌ *Withdrawal failed*\n\n"
            "Transaction could not be confirmed.\n"
            "Your SOL is safe — please try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="withdraw_start")],
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            ]),
            parse_mode="Markdown",
        )


# ══════════════════════════════════════════════
# STOP LOSS / TAKE PROFIT (SL/TP)
# ══════════════════════════════════════════════

_sl_tp_lock = False  # prevents overlapping monitor cycles


async def _ask_sl_tp(chat_id, user, context, bot,
                     mint: str, token_name: str, entry_sol: float,
                     token_amount_raw: str, token_decimals: int, tx_sig: str,
                     signal_grade: str = ""):
    """After a successful buy, ask user if they want SL/TP protection."""
    # Store pending position data in context for the callbacks
    context.user_data["pending_position"] = {
        "mint": mint,
        "token": token_name,
        "entry_sol": entry_sol,
        "token_amount_raw": token_amount_raw,
        "token_decimals": token_decimals,
        "buy_tx": tx_sig,
        "signal_grade": signal_grade,  # A/B/C/D — for win rate KPI breakdown
    }

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🛡️ *Protect your trade?*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 {token_name} | Entry: *{entry_sol:.4f} SOL*\n\n"
            "Set stop loss & take profit to auto-sell\n"
            "when price hits your targets. 24/7 monitoring."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡️ Set SL/TP", callback_data="set_sl_tp")],
            [InlineKeyboardButton("⏭️ Skip", callback_data="skip_sl_tp")],
        ]),
        parse_mode="Markdown",
    )


async def _cb_sl_select_start(query, user, context):
    """Start SL selection — show stop loss percentage options."""
    pending = context.user_data.get("pending_position")
    if not pending:
        await query.edit_message_text(
            "⚠️ No pending trade found. Buy a token first!",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    token = pending.get("token", "Token")
    await query.edit_message_text(
        f"🔴 *Set Stop Loss for {token}*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Auto-sell if your position drops by:\n\n"
        "• -3% → scalp (tight)\n"
        "• -5% → scalp (loose)\n"
        "• -10% → conservative\n"
        "• -15% → balanced\n"
        "• -25% → aggressive\n",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("-3% 🎯", callback_data="sl_3"),
                InlineKeyboardButton("-5% ⚡", callback_data="sl_5"),
            ],
            [
                InlineKeyboardButton("-10%", callback_data="sl_10"),
                InlineKeyboardButton("-15%", callback_data="sl_15"),
                InlineKeyboardButton("-25%", callback_data="sl_25"),
            ],
            [InlineKeyboardButton("⏭️ No Stop Loss", callback_data="sl_none")],
        ]),
        parse_mode="Markdown",
    )


async def _cb_sl_select(query, user, context):
    """Handle SL selection, then ask for TP."""
    data = query.data  # sl_10, sl_15, sl_25, sl_none
    pending = context.user_data.get("pending_position")
    if not pending:
        await query.edit_message_text(
            "⚠️ Session expired. Buy a token first!",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    sl_map = {"sl_3": 3, "sl_5": 5, "sl_10": 10, "sl_15": 15, "sl_25": 25, "sl_none": 0}
    sl_pct = sl_map.get(data, 0)
    context.user_data["pending_sl"] = sl_pct

    token = pending.get("token", "Token")
    sl_text = f"-{sl_pct}%" if sl_pct > 0 else "None"

    await query.edit_message_text(
        f"🟢 *Set Take Profit for {token}*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Stop Loss: *{sl_text}* ✓\n\n"
        "Auto-sell when your position gains:\n\n"
        "• +25% → quick scalp\n"
        "• +50% → balanced\n"
        "• +100% → moon bag\n",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("+25%", callback_data="tp_25"),
                InlineKeyboardButton("+50%", callback_data="tp_50"),
                InlineKeyboardButton("+100%", callback_data="tp_100"),
            ],
            [InlineKeyboardButton("⏭️ No Take Profit", callback_data="tp_none")],
        ]),
        parse_mode="Markdown",
    )


async def _cb_tp_select(query, user, context):
    """Handle TP selection — save position with SL/TP."""
    data = query.data  # tp_25, tp_50, tp_100, tp_none
    pending = context.user_data.get("pending_position")
    if not pending:
        await query.edit_message_text(
            "⚠️ Session expired. Buy a token first!",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    tp_map = {"tp_25": 25, "tp_50": 50, "tp_100": 100, "tp_none": 0}
    tp_pct = tp_map.get(data, 0)
    sl_pct = context.user_data.get("pending_sl", 0)

    # Both zero = user chose no SL and no TP → skip saving
    if sl_pct == 0 and tp_pct == 0:
        context.user_data.pop("pending_position", None)
        context.user_data.pop("pending_sl", None)
        await query.edit_message_text(
            "⏭️ No SL/TP set — trade is unprotected.\n"
            "You can always set protection later from your positions.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    # Save position
    position = {
        "mint": pending["mint"],
        "token": pending["token"],
        "entry_sol": pending["entry_sol"],
        "token_amount_raw": pending["token_amount_raw"],
        "token_decimals": pending["token_decimals"],
        "sl_pct": sl_pct,
        "tp_pct": tp_pct,
        "created": datetime.now(timezone.utc).isoformat(),
        "buy_tx": pending.get("buy_tx", ""),
        "signal_grade": pending.get("signal_grade", ""),  # A/B/C/D — win rate tracking
    }

    if "active_positions" not in user:
        user["active_positions"] = []
    user["active_positions"].append(position)
    _persist()

    # Clean up
    context.user_data.pop("pending_position", None)
    context.user_data.pop("pending_sl", None)

    sl_text = f"-{sl_pct}%" if sl_pct > 0 else "Off"
    tp_text = f"+{tp_pct}%" if tp_pct > 0 else "Off"
    entry = position["entry_sol"]
    sl_val = f"{entry * (1 - sl_pct / 100):.4f}" if sl_pct > 0 else "—"
    tp_val = f"{entry * (1 + tp_pct / 100):.4f}" if tp_pct > 0 else "—"

    await query.edit_message_text(
        "✅ *Position Protected!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 {position['token']}\n"
        f"📥 Entry: *{entry:.4f} SOL*\n\n"
        f"🔴 Stop Loss: *{sl_text}* (trigger: {sl_val} SOL)\n"
        f"🟢 Take Profit: *{tp_text}* (trigger: {tp_val} SOL)\n\n"
        "🤖 Bot monitors 24/7 — auto-sells when triggered.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Positions", callback_data="positions")],
            [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )
    logger.info(f"SL/TP set: user={query.from_user.id} token={position['token']} SL={sl_pct}% TP={tp_pct}%")


async def _cb_skip_sl_tp(query, user, context):
    """User chose to skip SL/TP."""
    context.user_data.pop("pending_position", None)
    context.user_data.pop("pending_sl", None)
    await query.edit_message_text(
        "⏭️ No SL/TP set — trade is unprotected.\n\n"
        "You can set protection anytime from 📊 Positions.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )


# ── View & Cancel Positions ──────────────────

async def _cb_positions(query, user, context):
    """Show all active SL/TP positions."""
    positions = user.get("active_positions", [])

    if not positions:
        await query.edit_message_text(
            "📊 *My Positions*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "No active SL/TP positions.\n\n"
            "Buy a token and set SL/TP to start!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    text = (
        "📊 *My Positions (SL/TP)*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )

    kb = []
    for i, pos in enumerate(positions):
        sl_text = f"-{pos['sl_pct']}%" if pos.get("sl_pct", 0) > 0 else "Off"
        tp_text = f"+{pos['tp_pct']}%" if pos.get("tp_pct", 0) > 0 else "Off"
        entry = pos.get("entry_sol", 0)

        # Try to get current value via Jupiter quote
        current_text = "⏳"
        try:
            raw_amount = int(pos["token_amount_raw"])
            quote = await get_quote(
                input_mint=pos["mint"],
                output_mint=SOL_MINT,
                amount_raw=raw_amount,
                slippage_bps=DEFAULT_SLIPPAGE_BPS,
            )
            if quote and quote.get("outAmount"):
                current_sol = int(quote["outAmount"]) / 1_000_000_000
                pnl_pct = ((current_sol - entry) / entry * 100) if entry > 0 else 0
                pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
                current_text = f"{current_sol:.4f} SOL ({pnl_emoji} {pnl_pct:+.1f}%)"
        except Exception:
            current_text = "⚠️ Price unavailable"

        text += (
            f"\n*{i + 1}. {pos['token']}*\n"
            f"   📥 Entry: {entry:.4f} SOL\n"
            f"   📈 Now: {current_text}\n"
            f"   🔴 SL: {sl_text} | 🟢 TP: {tp_text}\n"
        )
        kb.append([InlineKeyboardButton(
            f"❌ Cancel #{i + 1} ({pos['token']})",
            callback_data=f"cancel_pos_{i}",
        )])

    kb.append([InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


async def _cb_cancel_position(query, user, context, index: int):
    """Cancel SL/TP for a position (keeps tokens, removes auto-sell)."""
    positions = user.get("active_positions", [])
    if index < 0 or index >= len(positions):
        await query.edit_message_text(
            "⚠️ Position not found.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    removed = positions.pop(index)
    _persist()

    await query.edit_message_text(
        f"❌ *SL/TP Cancelled for {removed['token']}*\n\n"
        "Your tokens are safe — only the auto-sell was removed.\n"
        "You can still sell manually from the Trade menu.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Positions", callback_data="positions")],
            [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )
    logger.info(f"SL/TP cancelled: user={query.from_user.id} token={removed['token']}")


# ── Background SL/TP Monitor ─────────────────

async def sl_tp_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """Check all active SL/TP positions every 30s.

    Logic: For each position, get Jupiter quote (sell token → SOL).
    If current_sol <= entry × (1 - sl_pct/100) → stop loss triggered.
    If current_sol >= entry × (1 + tp_pct/100) → take profit triggered.
    """
    global _sl_tp_lock
    import asyncio

    if _sl_tp_lock:
        return  # previous cycle still running
    _sl_tp_lock = True

    try:
        # Collect all positions across all users
        all_positions = []  # (chat_id, user, pos_index, position)
        for chat_id, user in users.items():
            for i, pos in enumerate(user.get("active_positions", [])):
                all_positions.append((chat_id, user, i, pos))

        if not all_positions:
            return

        # Group by mint to minimize API calls (1 quote per unique mint+amount combo)
        # But each position can have different token amounts, so we check individually
        # Rate limit: max 10 checks per cycle
        checked = 0
        triggered = []  # (chat_id, user, pos_index, position, trigger_type, current_sol)

        for chat_id, user, pos_index, pos in all_positions:
            if checked >= 10:
                break  # rate limit — continue next cycle

            try:
                raw_amount = int(pos["token_amount_raw"])
                if raw_amount <= 0:
                    continue

                entry_sol = pos.get("entry_sol", 0)
                if entry_sol <= 0:
                    continue

                sl_pct = pos.get("sl_pct", 0)
                tp_pct = pos.get("tp_pct", 0)
                if sl_pct == 0 and tp_pct == 0:
                    continue  # nothing to monitor

                # Get current value: "if I sell all my tokens now, how much SOL?"
                quote = await get_quote(
                    input_mint=pos["mint"],
                    output_mint=SOL_MINT,
                    amount_raw=raw_amount,
                    slippage_bps=DEFAULT_SLIPPAGE_BPS,
                )
                checked += 1

                if not quote or not quote.get("outAmount"):
                    continue

                current_sol = int(quote["outAmount"]) / 1_000_000_000

                # ── Trailing SL: update peak and move SL floor up ──
                # Logic: lock in profits as price rises.
                #   +10% gain → SL moves to break-even (0%)
                #   +25% gain → SL moves to +10% (never lose this)
                #   +50% gain → SL moves to +25%
                #   +100% gain → SL moves to +50%
                peak_sol = pos.get("peak_sol", entry_sol)
                if current_sol > peak_sol:
                    pos["peak_sol"] = current_sol  # track all-time high for this position
                    peak_sol = current_sol

                gain_pct = (peak_sol / entry_sol - 1) * 100 if entry_sol > 0 else 0
                if gain_pct >= 100:
                    effective_sl_floor = entry_sol * 1.50   # lock in 50%
                elif gain_pct >= 50:
                    effective_sl_floor = entry_sol * 1.25   # lock in 25%
                elif gain_pct >= 25:
                    effective_sl_floor = entry_sol * 1.10   # lock in 10%
                elif gain_pct >= 10:
                    effective_sl_floor = entry_sol * 1.00   # break-even
                else:
                    effective_sl_floor = 0  # no trailing protection yet

                # Check stop loss (use whichever is HIGHER: fixed SL or trailing floor)
                if sl_pct > 0 or effective_sl_floor > 0:
                    fixed_sl = entry_sol * (1 - sl_pct / 100) if sl_pct > 0 else 0
                    sl_trigger = max(fixed_sl, effective_sl_floor)
                    if current_sol <= sl_trigger:
                        trigger_label = "TRAIL_SL" if effective_sl_floor > fixed_sl else "SL"
                        triggered.append((chat_id, user, pos_index, pos, trigger_label, current_sol))
                        continue  # don't also check TP

                # Check take profit
                if tp_pct > 0:
                    tp_trigger = entry_sol * (1 + tp_pct / 100)
                    if current_sol >= tp_trigger:
                        triggered.append((chat_id, user, pos_index, pos, "TP", current_sol))

                # Rate limit delay between API calls
                await asyncio.sleep(1)

            except Exception as pos_err:
                logger.warning(f"SL/TP check error for {pos.get('token', '?')}: {pos_err}")
                continue

        # Execute triggered sells (process in reverse to maintain indices)
        for chat_id, user, pos_index, pos, trigger_type, current_sol in reversed(triggered):
            try:
                encrypted = user.get("wallet_secret_enc")
                if not encrypted:
                    continue

                keypair = load_keypair(encrypted)
                raw_amount = int(pos["token_amount_raw"])

                # Get fresh quote for execution
                quote = await get_quote(
                    input_mint=pos["mint"],
                    output_mint=SOL_MINT,
                    amount_raw=raw_amount,
                    slippage_bps=DEFAULT_SLIPPAGE_BPS,
                )

                if not quote:
                    logger.warning(f"SL/TP sell quote failed for {pos['token']}")
                    continue

                # Calculate fee on output
                out_lamports = int(quote.get("outAmount", 0))
                swap_lamports, fee_lamports = calculate_fee(out_lamports)

                # Execute sell
                tx_sig, swap_err = await execute_swap(keypair, quote)

                if tx_sig:
                    # Collect fee
                    try:
                        if FEE_COLLECT_WALLET and fee_lamports > 5000:
                            await collect_fee(keypair, fee_lamports, FEE_COLLECT_WALLET)
                    except Exception:
                        pass

                    # Remove position (safe because we process in reverse)
                    positions = user.get("active_positions", [])
                    if pos_index < len(positions):
                        positions.pop(pos_index)

                    entry = pos.get("entry_sol", 0)

                    # Use actual SOL received from sell (after fee)
                    sold_sol = swap_lamports / 1_000_000_000  # net SOL after fee deduction

                    # Sanity check: sold amount should be in reasonable range of entry
                    # If wildly off (>100x entry), use the pre-sell quote value instead
                    if entry > 0 and sold_sol > entry * 100:
                        sold_sol = current_sol  # fall back to quote estimate

                    pnl_sol = sold_sol - entry
                    pnl_pct = (pnl_sol / entry * 100) if entry > 0 else 0
                    pnl_emoji = "🟢" if pnl_sol >= 0 else "🔴"

                    if trigger_type == "TRAIL_SL":
                        trigger_label = "🟡 TRAILING SL"
                    elif trigger_type == "SL":
                        trigger_label = "🔴 STOP LOSS"
                    else:
                        trigger_label = "🟢 TAKE PROFIT"

                    # Record trade (fetch SOL price for USD value — was hardcoded 0)
                    try:
                        _sell_prices = await get_crypto_prices()
                        _sol_px = _sell_prices.get("SOL") or FALLBACK_PRICES.get("SOL", 130)
                    except Exception:
                        _sol_px = FALLBACK_PRICES.get("SOL", 130)
                    _record_trade(
                        chat_id, user, "SELL", pos["token"], pos["mint"],
                        sold_sol, sold_sol * _sol_px, tx_sig,
                        entry_price_usd=_sol_px,
                    )

                    # Track win rate (critical for marketing + trust)
                    try:
                        from core.persistence import record_trade_result
                        record_trade_result(
                            chat_id, pos["token"], pnl_pct, pnl_sol,
                            signal_grade=pos.get("signal_grade", ""),
                        )
                    except Exception:
                        pass

                    _persist()

                    # ── CEO TIER 2: Track consecutive losses + auto-pause ──
                    try:
                        from core.persistence import _get_redis as _pr
                        _r = _pr()
                        if _r:
                            if pnl_sol < 0:
                                consec = _r.incr("winrate:consecutive_losses")
                                logger.info(f"Consecutive losses: {consec}")
                                # Check if auto-pause should trigger
                                from agents.ceo_agent import check_win_rate_and_pause
                                pause_result = check_win_rate_and_pause()
                                if pause_result.get("action") == "paused":
                                    # Alert Erik via Telegram
                                    for admin_id in ADMIN_IDS:
                                        try:
                                            await context.bot.send_message(
                                                chat_id=admin_id,
                                                text=(
                                                    "🤖 *CEO Agent TIER 2 — ACTIE GENOMEN*\n"
                                                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                                                    f"⚠️ Signals **GEPAUZEERD**\n"
                                                    f"Reden: {pause_result.get('reason', '?')}\n"
                                                    f"Win rate: {pause_result.get('win_rate', '?')}%\n"
                                                    f"Trades: {pause_result.get('total_trades', '?')}\n\n"
                                                    "Signals worden NIET meer verzonden.\n"
                                                    "Klik hervat om handmatig te hervatten:"
                                                ),
                                                reply_markup=InlineKeyboardMarkup([[
                                                    InlineKeyboardButton(
                                                        "▶️ Hervat Signals", callback_data="admin_resume_signals"
                                                    ),
                                                    InlineKeyboardButton(
                                                        "📊 Stats", callback_data="admin_stats"
                                                    ),
                                                ]]),
                                                parse_mode="Markdown",
                                            )
                                        except Exception:
                                            pass
                            else:
                                # Win: reset consecutive loss counter
                                _r.set("winrate:consecutive_losses", "0")
                    except Exception as pause_err:
                        logger.debug(f"CEO pause check failed (non-fatal): {pause_err}")

                    # Notify user
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"{trigger_label} *TRIGGERED!*\n"
                            "━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🎯 {pos['token']}\n"
                            f"📥 Entry: *{entry:.4f} SOL*\n"
                            f"📤 Sold: *{sold_sol:.4f} SOL*\n"
                            f"{pnl_emoji} P/L: *{pnl_sol:+.4f} SOL* ({pnl_pct:+.1f}%)\n\n"
                            f"🔗 [View on Solscan](https://solscan.io/tx/{tx_sig})"
                        ),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )

                    logger.info(
                        f"SL/TP {trigger_type} executed: user={chat_id} "
                        f"token={pos['token']} entry={entry:.4f} exit={current_sol:.4f} "
                        f"pnl={pnl_pct:+.1f}% tx={tx_sig}"
                    )

                    # Social proof: post trade result to channel (anonymous)
                    if ALERT_CHANNEL_ID and pnl_sol != 0:
                        try:
                            win_streak = ""
                            from core.persistence import get_win_rate
                            wr = get_win_rate()
                            if wr and wr.get("total", 0) >= 5:
                                win_streak = f"\n📊 Platform Win Rate: *{wr.get('win_rate', 0)}%* ({wr.get('total', 0)} trades)"

                            channel_text = (
                                f"{'🟢 WIN' if pnl_sol > 0 else '🔴 LOSS'} — *{pos['token']}*\n"
                                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"📥 Entry: {entry:.4f} SOL\n"
                                f"📤 Exit: {sold_sol:.4f} SOL\n"
                                f"{pnl_emoji} *P/L: {pnl_sol:+.4f} SOL ({pnl_pct:+.1f}%)*\n"
                                f"⏱ Trigger: {trigger_label}\n"
                                f"{win_streak}\n\n"
                                f"🔗 [Verify on Solscan](https://solscan.io/tx/{tx_sig})\n\n"
                                f"💡 _Get these signals free → @{BOT_USERNAME}_\n"
                                "🔥 _Copy top traders → apexflash.pro_"
                            )
                            await context.bot.send_message(
                                chat_id=ALERT_CHANNEL_ID,
                                text=channel_text,
                                parse_mode="Markdown",
                                disable_web_page_preview=True,
                            )
                        except Exception as ch_err:
                            logger.warning(f"Channel trade post failed: {ch_err}")
                else:
                    logger.warning(f"SL/TP sell failed for {pos['token']} user={chat_id}")

                await asyncio.sleep(1)  # rate limit between sells

            except Exception as sell_err:
                logger.error(f"SL/TP sell error for {pos.get('token', '?')}: {sell_err}")
                continue

    except Exception as monitor_err:
        logger.error(f"SL/TP monitor error: {monitor_err}")
    finally:
        _sl_tp_lock = False


async def _cb_trade_buy(query, user, context):
    """Buy token instructions."""
    if not user.get("wallet_pubkey"):
        await query.edit_message_text(
            "\u26a0\ufe0f Create a wallet first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    text = (
        "💰 *Buy Tokens*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "Tap a token below to buy instantly!\n"
        "Or paste any Solana mint address.\n"
        "\n"
        "🔥 *Popular tokens:*"
    )

    # Build clickable token buttons with fun icons — 1 tap = buy screen
    TOKEN_ICONS = {
        "USDC": "💵", "USDT": "💲", "JUP": "🪐", "BONK": "🐕",
        "WIF": "🐶", "TRUMP": "🇺🇸", "RAY": "☀️", "ORCA": "🐋",
        "PYTH": "🐍", "W": "🌀", "SOL": "◎",
    }
    token_buttons = []
    shown = 0
    for sym, info in COMMON_TOKENS.items():
        if sym == "SOL":
            continue
        icon = TOKEN_ICONS.get(sym, "🪙")
        token_buttons.append(
            InlineKeyboardButton(f"{icon} {sym}", callback_data=f"hot_buy_{info['mint']}")
        )
        shown += 1
        if shown >= 10:
            break

    # Arrange in rows of 2 for better readability
    kb = []
    for i in range(0, len(token_buttons), 2):
        kb.append(token_buttons[i:i+2])

    kb.append([InlineKeyboardButton("🔥 Trending Tokens", callback_data="cmd_hot_refresh")])
    kb.append([InlineKeyboardButton("💼 My Wallet", callback_data="trade_wallet")])
    kb.append([InlineKeyboardButton("💰 Trade Menu", callback_data="trade")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_trade_sell(query, user, context):
    """Show tokens available to sell."""
    if not user.get("wallet_pubkey"):
        await query.edit_message_text(
            "\u26a0\ufe0f Create a wallet first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        "\U0001f50d *Scanning tokens...*", parse_mode="Markdown",
    )
    
    logger.info(f"Scanning tokens for user {query.from_user.id} ({user['wallet_pubkey']})")

    tokens = await get_token_balances(user["wallet_pubkey"])

    if not tokens:
        pubkey = user["wallet_pubkey"]
        short = pubkey[:20]
        await query.edit_message_text(
            "\U0001f4b8 *Sell Tokens*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "\u26a0\ufe0f No tokens found in your bot wallet.\n\n"
            f"\U0001f510 *Bot wallet:*\n`{pubkey}`\n\n"
            "Steps to get tokens:\n"
            "1\ufe0f\u20e3 Send SOL to the address above\n"
            "2\ufe0f\u20e3 Use Trade \u2192 Buy to purchase a token\n"
            "3\ufe0f\u20e3 Come back here to sell\n\n"
            "_Your Phantom wallet is separate \u2014 the bot uses its own wallet._",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
                [InlineKeyboardButton("\U0001f4cb Copy Address", callback_data=f"copy_addr_{pubkey}")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    text = (
        "\U0001f4b8 *Sell Tokens*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Select a token to sell:\n"
    )

    kb = []
    for t in tokens[:8]:
        token_name = None
        for sym, info in COMMON_TOKENS.items():
            if info["mint"] == t["mint"]:
                token_name = sym
                break
        display = token_name or f"{t['mint'][:8]}..."
        label = f"\U0001f534 {display} \u2014 {t['amount']:,.4f}"
        kb.append([InlineKeyboardButton(label, callback_data=f"sell_tok_{t['mint']}")])

    kb.append([InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# RISK MANAGEMENT — TERMS, CONFIRMATION, CHECKS
# ══════════════════════════════════════════════

async def _cb_accept_terms(query, user, context):
    """User accepts risk disclaimer."""
    user["accepted_terms"] = True
    _persist()  # save immediately so acceptance survives restarts
    logger.info(f"Terms accepted: user {query.from_user.id}")
    await query.edit_message_text(
        "\u2705 *Terms Accepted*\n\n"
        "You can now trade. Be careful and only risk what you can afford to lose.\n\n"
        "Tap below to continue:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
    )


async def _cb_view_disclaimer(query, user, context):
    """Show full risk disclaimer."""
    kb = [[_back_main()[0]]]
    if not user.get("accepted_terms"):
        kb.insert(0, [InlineKeyboardButton(
            "\u2705 I Understand & Accept", callback_data="accept_terms",
        )])
    await query.edit_message_text(
        RISK_DISCLAIMER,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


def _apply_test_cap(sol_amount: float) -> float:
    """If TEST_TRADE_SOL is set, cap the trade to that micro amount.
    Prevents expensive mistakes during testing. 0 = disabled."""
    if TEST_TRADE_SOL > 0 and sol_amount > TEST_TRADE_SOL:
        logger.warning(f"TEST MODE: capping trade {sol_amount} SOL → {TEST_TRADE_SOL} SOL")
        return TEST_TRADE_SOL
    return sol_amount


def _check_trade_allowed(user: dict, sol_amount: float = 0) -> str | None:
    """Pre-trade risk checks. Returns error message or None if OK."""
    global trading_enabled

    # Kill switch
    if not trading_enabled:
        return (
            "\U0001f6d1 *Trading Paused*\n\n"
            "Trading is temporarily disabled by admin.\n"
            "Please try again later."
        )

    # Terms acceptance
    if not user.get("accepted_terms"):
        return None  # Handled separately with accept flow

    # Daily trade limit
    daily = _user_daily_trades(user)
    if daily >= MAX_DAILY_TRADES:
        return (
            f"\u26a0\ufe0f *Daily Limit Reached*\n\n"
            f"You've made {daily}/{MAX_DAILY_TRADES} trades today.\n"
            f"Limits reset at midnight UTC."
        )

    # Max single trade size
    if sol_amount > MAX_TRADE_SOL:
        return (
            f"\u26a0\ufe0f *Trade Too Large*\n\n"
            f"Max single trade: *{MAX_TRADE_SOL} SOL*\n"
            f"You tried: *{sol_amount} SOL*\n\n"
            f"Split into smaller trades for safety."
        )

    return None


async def _cb_preview_buy(query, user, context, data):
    """Show trade confirmation with quote before executing."""
    global trading_enabled

    # Check terms first
    if not user.get("accepted_terms"):
        await _safe_edit_message(
            query,
            RISK_DISCLAIMER,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "\u2705 I Understand & Accept", callback_data="accept_terms",
                )],
                [_back_main()[0]],
            ]),
        )
        return

    if not user.get("wallet_pubkey"):
        await _safe_edit_message(
            query,
            "\u26a0\ufe0f Create a wallet first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
        )
        return

    target_mint = context.user_data.get("target_mint")
    if not target_mint:
        await _safe_edit_message(
            query,
            "\u26a0\ufe0f No token selected. Paste a mint address first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
                [_back_main()[0]],
            ]),
        )
        return

    # Parse SOL amount (preset or custom)
    amount_map = {"buy_01": 0.1, "buy_05": 0.5, "buy_1": 1.0, "buy_5": 5.0}
    if data == "buy_custom_exec":
        sol_amount = context.user_data.get("custom_sol_amount")
    else:
        sol_amount = amount_map.get(data)
    if not sol_amount:
        return

    # Apply test cap (micro amounts for safe testing)
    sol_amount = _apply_test_cap(sol_amount)

    # Risk checks
    error = _check_trade_allowed(user, sol_amount)
    if error:
        await _safe_edit_message(
            query,
            error,
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
        )
        return

    # Balance check (None = RPC unreachable)
    balance = await get_sol_balance(user["wallet_pubkey"])
    if balance is None:
        await _safe_edit_message(
            query,
            "⚠️ *RPC Temporarily Unavailable*\n\n"
            "Could not check your balance. Please try again in a moment.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry", callback_data=query.data)],
                [_back_main()[0]],
            ]),
        )
        return
    needed = sol_amount + MIN_SOL_RESERVE
    if balance < needed:
        await _safe_edit_message(
            query,
            f"\u26a0\ufe0f *Insufficient Balance*\n\n"
            f"Balance: *{balance:.4f} SOL*\n"
            f"Needed: *{sol_amount} SOL* + {MIN_SOL_RESERVE} reserve\n"
            f"= *{needed:.4f} SOL*\n\n"
            f"Deposit more SOL to your wallet first.\n\n"
            f"\U0001f4b3 *Buy SOL on an exchange:*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
                [
                    InlineKeyboardButton(
                        "\U0001f525 Buy on MEXC (70% fee back)",
                        url=AFFILIATE_LINKS["mexc"]["url"],
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "\U0001f525 Buy on Bitunix (50%)",
                        url=AFFILIATE_LINKS["bitunix"]["url"],
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "\U0001f525 Buy on Gate.io (30%)",
                        url=AFFILIATE_LINKS.get("gate", {}).get("url", "https://www.gate.com/signup/VFFHXVFDUG?ref_type=103"),
                    ),
                ],
                [_back_main()[0]],
            ]),
        )
        return

    # Get quote for preview
    await _safe_edit_message(query, "\U0001f50d *Getting quote...*")

    total_lamports = int(sol_amount * 1_000_000_000)
    swap_lamports, fee_lamports = calculate_fee(total_lamports)

    quote = await get_quote(
        input_mint=SOL_MINT,
        output_mint=target_mint,
        amount_raw=swap_lamports,
        slippage_bps=DEFAULT_SLIPPAGE_BPS,
    )

    if not quote:
        await _safe_edit_message(
            query,
            "\u274c *Quote Failed*\n\nCould not get price. Token may be illiquid.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
                [_back_main()[0]],
            ]),
        )
        return

    # Store quote for execution (with timestamp for freshness check)
    import time as _time
    context.user_data["pending_quote"] = quote
    context.user_data["pending_quote_ts"] = _time.time()
    context.user_data["pending_quote_mint"] = target_mint
    context.user_data["pending_buy_data"] = data

    # Extract info for confirmation
    token_name = context.user_data.get("target_name", "Token")
    fee_sol = fee_lamports / 1_000_000_000
    price_impact = _get_price_impact(quote)
    out_amount = quote.get("outAmount", "?")

    # Price impact warning
    impact_warn = ""
    if price_impact > PRICE_IMPACT_WARN_PCT:
        impact_warn = (
            f"\n\u26a0\ufe0f *HIGH PRICE IMPACT: {price_impact:.1f}%*\n"
            f"You may receive significantly less than expected!\n"
        )

    # ── Token Safety Check (DexPaprika — free, no key) ──
    safety_text = ""
    try:
        import aiohttp as _aio_safety
        async with _aio_safety.ClientSession() as _ss:
            async with _ss.get(
                f"https://api.dexpaprika.com/networks/solana/tokens/{target_mint}/pools",
                params={"limit": "5"},
                timeout=_aio_safety.ClientTimeout(total=5),
            ) as _sr:
                if _sr.status == 200:
                    _pools = await _sr.json()
                    _pool_list = _pools.get("pools", _pools) if isinstance(_pools, dict) else _pools
                    if isinstance(_pool_list, list) and _pool_list:
                        _top = _pool_list[0]
                        _liq = _top.get("liquidity_usd", 0) or 0
                        _vol = _top.get("volume_usd", 0) or 0
                        _age_str = _top.get("created_at", "")

                        # Liquidity grade
                        if _liq >= 100_000:
                            _grade = "\U0001f7e2 HIGH"
                        elif _liq >= 10_000:
                            _grade = "\U0001f7e1 MEDIUM"
                        else:
                            _grade = "\U0001f534 LOW \u26a0\ufe0f"

                        # Pool age
                        _age_label = ""
                        if _age_str:
                            from datetime import datetime, timezone
                            try:
                                _created = datetime.fromisoformat(_age_str.replace("Z", "+00:00"))
                                _days = (datetime.now(timezone.utc) - _created).days
                                _age_label = f"{_days}d" if _days >= 1 else "<1d \u26a0\ufe0f"
                            except Exception:
                                _age_label = "?"

                        safety_text = (
                            f"\n\U0001f6e1 *Safety Check*\n"
                            f"Liquidity: {_grade} (${_liq:,.0f})\n"
                            f"24h Volume: ${_vol:,.0f}\n"
                        )
                        if _age_label:
                            safety_text += f"Pool Age: {_age_label}\n"

                        if _liq < 5_000:
                            safety_text += "\u26a0\ufe0f _Very low liquidity — high rug risk!_\n"
                        elif _liq < 10_000:
                            safety_text += "\u26a0\ufe0f _Low liquidity — trade with caution_\n"
                    else:
                        safety_text = "\n\U0001f6e1 _No pool data found — unknown token, trade carefully!_\n"
    except Exception:
        pass  # Safety check is optional — never block a trade

    # ── RugCheck Safety Score (Solana-specific, free) ──
    try:
        import aiohttp as _aio_rug
        async with _aio_rug.ClientSession() as _rs:
            async with _rs.get(
                f"https://api.rugcheck.xyz/v1/tokens/{target_mint}/report/summary",
                timeout=_aio_rug.ClientTimeout(total=4),
            ) as _rr:
                if _rr.status == 200:
                    _rug = await _rr.json()
                    _risk = _rug.get("score", 0)
                    _risks = _rug.get("risks", [])
                    if _risk > 0:
                        if _risk >= 800:
                            _rug_grade = "\U0001f7e2 SAFE"
                        elif _risk >= 500:
                            _rug_grade = "\U0001f7e1 CAUTION"
                        else:
                            _rug_grade = "\U0001f534 RISKY \u26a0\ufe0f"
                        safety_text += f"RugCheck: {_rug_grade} ({_risk}/1000)\n"
                        if _risks:
                            top_risks = [r.get("name", "?") for r in _risks[:3]]
                            safety_text += f"Flags: {', '.join(top_risks)}\n"
    except Exception:
        pass  # RugCheck is bonus — never block a trade

    text = (
        "\U0001f4cb *Trade Confirmation*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f504 *BUY {token_name}*\n"
        f"\U0001f4b5 Spend: *{sol_amount} SOL*\n"
        f"\U0001f4b0 Fee: *{fee_sol:.4f} SOL* ({PLATFORM_FEE_PCT}%)\n"
        f"\U0001f3af Slippage: max {DEFAULT_SLIPPAGE_BPS/100:.1f}%\n"
        f"\U0001f4bc Balance: *{balance:.4f} SOL*\n"
        f"{safety_text}"
        f"{impact_warn}\n"
        f"\u26a0\ufe0f _This trade is irreversible once confirmed._\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [
            InlineKeyboardButton(
                f"\u2705 Confirm Buy {sol_amount} SOL",
                callback_data=f"confirm_{data}",
            ),
        ],
        [InlineKeyboardButton("\u274c Cancel", callback_data="trade")],
    ]

    await _safe_edit_message(
        query, text, reply_markup=InlineKeyboardMarkup(kb),
    )


async def _cb_preview_sell(query, user, context, data):
    """Show sell confirmation before executing."""
    # Check terms first
    if not user.get("accepted_terms"):
        await query.edit_message_text(
            RISK_DISCLAIMER,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "\u2705 I Understand & Accept", callback_data="accept_terms",
                )],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    # Kill switch / limits
    error = _check_trade_allowed(user)
    if error:
        await query.edit_message_text(
            error,
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    # data format: sel_25_{mint}, sel_50_{mint}, sel_100_{mint}
    try:
        _, pct_str, sell_mint = data.split("_", 2)
        pct_label = int(pct_str)
    except Exception:
        await query.edit_message_text(
            "\u26a0\ufe0f Invalid sell request.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    # Find token name
    token_name = f"{sell_mint[:8]}..."
    for sym, info in COMMON_TOKENS.items():
        if info["mint"] == sell_mint:
            token_name = sym
            break

    text = (
        "\U0001f4cb *Sell Confirmation*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f4b8 *SELL {pct_label}% of {token_name}*\n"
        f"\U0001f4b0 Fee: {PLATFORM_FEE_PCT}%\n"
        f"\U0001f3af Slippage: max {DEFAULT_SLIPPAGE_BPS/100:.1f}%\n"
        f"\n"
        f"\u26a0\ufe0f _This trade is irreversible once confirmed._\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton(
            f"\u2705 Confirm Sell {pct_label}%",
            callback_data=f"csel_{pct_str}_{sell_mint}",
        )],
        [InlineKeyboardButton("\u274c Cancel", callback_data="trade_sell")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_sell_token_select(query, user, context, data):
    """User tapped a token to sell. data = sell_tok_{mint}"""
    mint = data[9:]  # strip "sell_tok_"
    token_name = None
    for sym, info in COMMON_TOKENS.items():
        if info["mint"] == mint:
            token_name = sym
            break
    display = token_name or f"{mint[:8]}..."

    text = (
        f"\U0001f534 *Sell {display}*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "How much do you want to sell?\n"
    )
    kb = [
        [
            InlineKeyboardButton("Sell 25%", callback_data=f"sel_25_{mint}"),
            InlineKeyboardButton("Sell 50%", callback_data=f"sel_50_{mint}"),
            InlineKeyboardButton("Sell 100%", callback_data=f"sel_100_{mint}"),
        ],
        [InlineKeyboardButton("\u25c0 Back", callback_data="trade_sell")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# LEADERBOARD
# ══════════════════════════════════════════════

async def _cb_leaderboard(query, user, context):
    """Show anonymized leaderboard — top traders by volume."""
    _reset_daily_stats()

    # Gather all users with trades
    traders = []
    for uid, u in users.items():
        trades = u.get("total_trades", 0)
        vol = u.get("total_volume_usd", 0)
        if trades > 0:
            # Anonymize: show first 2 chars of username or "Trader"
            uname = u.get("username", "")
            anon = f"{uname[:2]}***" if uname and len(uname) >= 2 else f"Trader#{uid % 1000:03d}"
            traders.append({
                "name": anon,
                "trades": trades,
                "volume": vol,
                "today": uid in platform_stats["active_traders_today"],
            })

    # Sort by volume (highest first)
    traders.sort(key=lambda x: x["volume"], reverse=True)

    text = (
        "\U0001f3c6 *ApexFlash Leaderboard*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
    )

    if not traders:
        text += (
            "No trades yet! Be the first.\n"
            "\n"
            "Paste a token address to start trading.\n"
        )
    else:
        medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
        for i, t in enumerate(traders[:10]):
            rank = medals[i] if i < 3 else f"{i+1}."
            active = " \U0001f7e2" if t["today"] else ""
            text += (
                f"{rank} *{t['name']}*{active}\n"
                f"   {t['trades']} trades | ${t['volume']:,.0f} volume\n"
            )

        # Platform totals
        text += (
            "\n"
            f"\U0001f30d *Platform Total:*\n"
            f"\u2022 {platform_stats['trades_total']} trades all-time\n"
            f"\u2022 ${platform_stats['volume_total_usd']:,.0f} total volume\n"
            f"\u2022 {len(traders)} active traders\n"
        )

    # Mandatory disclaimer
    text += (
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f _Leaderboard shows volume, not profit._\n"
        "_High volume does not mean positive returns._\n"
        "_Past performance is not indicative of future results._\n"
        "_Trading crypto involves substantial risk of loss._"
    )

    # User's own position
    my_trades = user.get("total_trades", 0)
    my_vol = user.get("total_volume_usd", 0)
    my_refs = user.get("referral_count", 0)
    my_earnings = user.get("referral_earnings", 0)
    if my_trades > 0:
        my_rank = sum(1 for t in traders if t["volume"] > my_vol) + 1
        text += (
            f"\n\n📊 *Your Stats:*\n"
            f"• Rank: #{my_rank} of {len(traders)}\n"
            f"• {my_trades} trades | ${my_vol:,.0f} volume\n"
        )
    if my_refs > 0:
        text += f"• {my_refs} referrals | {my_earnings:.4f} SOL earned\n"

    # Share link
    try:
        _bot_un = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{_bot_un}?start=ref_{query.from_user.id}"
    except Exception:
        ref_link = None

    kb = [
        [InlineKeyboardButton("🔥 Hot Tokens", callback_data="cmd_hot_refresh")],
        [InlineKeyboardButton("💼 My Wallet", callback_data="trade_wallet")],
        [InlineKeyboardButton("💰 Trade Menu", callback_data="trade")],
    ]
    if ref_link:
        kb.insert(0, [InlineKeyboardButton("🤝 Invite & Earn 25%", url=f"https://t.me/share/url?url={ref_link}&text=Trade Solana tokens free on ApexFlash! 🚀")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# TRADE EXECUTION (now requires confirmation)
# ══════════════════════════════════════════════

async def _cb_execute_buy(query, user, context, data):
    """Execute a buy order. data = buy_01, buy_05, buy_1, buy_5"""
    if not user.get("wallet_pubkey") or not user.get("wallet_secret_enc"):
        await _safe_edit_message(
            query,
            "\u26a0\ufe0f No wallet. Create one first!",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
        )
        return

    target_mint = context.user_data.get("target_mint")
    if not target_mint:
        await _safe_edit_message(
            query,
            "\u26a0\ufe0f No token selected. Paste a mint address first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
                [_back_main()[0]],
            ]),
        )
        return

    # Parse SOL amount from callback data (preset or custom)
    amount_map = {
        "buy_01": 0.1,
        "buy_05": 0.5,
        "buy_1": 1.0,
        "buy_5": 5.0,
    }
    if data == "buy_custom_exec":
        sol_amount = context.user_data.get("custom_sol_amount")
    else:
        sol_amount = amount_map.get(data)
    if not sol_amount:
        await _safe_edit_message(
            query,
            "\u26a0\ufe0f Invalid amount.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
        )
        return

    await _safe_edit_message(
        query,
        f"\u23f3 *Swapping {sol_amount} SOL...*\n"
        f"Token: `{target_mint[:20]}...`\n"
        f"Fee: {PLATFORM_FEE_PCT}%\n\n"
        "_Getting best price via Jupiter..._",
    )

    # Calculate amounts (SOL has 9 decimals)
    total_lamports = int(sol_amount * 1_000_000_000)
    swap_lamports, fee_lamports = calculate_fee(total_lamports)

    # Get quote (reuse cached if fresh enough — within 30 seconds)
    import time as _time
    cached_quote = context.user_data.get("pending_quote")
    cached_ts = context.user_data.get("pending_quote_ts", 0)
    cached_mint = context.user_data.get("pending_quote_mint")
    if (cached_quote and cached_mint == target_mint
            and (_time.time() - cached_ts) < 30):
        quote = cached_quote
        logger.info("Reusing cached quote (< 30s old)")
    else:
        quote = await get_quote(
            input_mint=SOL_MINT,
            output_mint=target_mint,
            amount_raw=swap_lamports,
            slippage_bps=DEFAULT_SLIPPAGE_BPS,
        )

    if not quote:
        await _safe_edit_message(
            query,
            "\u274c *Quote Failed*\n\n"
            "Could not get a price for this token.\n"
            "The token may be illiquid or invalid.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Try Again", callback_data=data)],
                [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
                [_back_main()[0]],
            ]),
        )
        return

    # Execute swap
    try:
        keypair = load_keypair(user["wallet_secret_enc"])
    except Exception as e:
        logger.error(f"Keypair load error: {e}")
        await _safe_edit_message(
            query,
            "\u274c Wallet error. Please contact support.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
        )
        return

    tx_sig, swap_err = await execute_swap(keypair, quote)

    if tx_sig:
        user["total_trades"] = user.get("total_trades", 0) + 1
        _increment_daily_trades(user)
        prices = await get_crypto_prices()
        sol_price = prices.get("SOL", 0)
        usd_value = sol_amount * sol_price
        user["total_volume_usd"] = user.get("total_volume_usd", 0) + usd_value
        fee_sol = fee_lamports / 1_000_000_000

        out_amount = quote.get("outAmount", "?")
        token_name = context.user_data.get("target_name", "Token")

        text = (
            "\u2705 *Swap Successful!*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f4b5 Spent: *{sol_amount} SOL*"
        )
        if usd_value > 0:
            text += f" (${usd_value:,.2f})"
        text += (
            f"\n\U0001f4b0 Fee: *{fee_sol:.4f} SOL* ({PLATFORM_FEE_PCT}%)\n"
            f"\U0001f3af Received: *{token_name}*\n"
            "\n"
            f"\U0001f517 [View on Solscan](https://solscan.io/tx/{tx_sig})\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )
        # Generate viral share link: t.me/apexflash_bot?start=buy_MINT_ref_USERID
        try:
            _bot_un = (await context.bot.get_me()).username
            share_link = f"https://t.me/{_bot_un}?start=buy_{target_mint}_ref_{query.from_user.id}"
            share_text = f"I just bought ${token_name} on Solana via @{_bot_un}! 🚀 Trade it too:"
            share_url = f"https://t.me/share/url?url={share_link}&text={share_text}"
        except Exception:
            share_url = None

        kb = [
            [InlineKeyboardButton("💼 View Wallet", callback_data="trade_wallet")],
            [InlineKeyboardButton("💰 Trade Menu", callback_data="trade")],
        ]
        if share_url:
            kb.insert(0, [InlineKeyboardButton("🔗 Share & Earn 25%", url=share_url)])
        kb.append([_back_main()[0]])

        logger.info(f"TRADE OK: user={query.from_user.id} buy={sol_amount}SOL token={target_mint[:12]} tx={tx_sig}")

        # Analytics: track trade + funnel
        track_token_trade(target_mint, sol_amount)
        update_last_active(query.from_user.id)
        if user.get("total_trades", 0) == 1:
            track_funnel("first_trade")

        # CRITICAL: Instant backup after trade (wallet balances changed)
        try:
            await _send_backup_to_admin(
                context.bot,
                f"\U0001f4b5 BUY trade backup | {sol_amount} SOL | user {query.from_user.id} | tx: {tx_sig[:16]}...",
            )
        except Exception:
            pass

        # ── Record trade for PnL + leaderboard ──
        _record_trade(
            query.from_user.id, user, "BUY", token_name, target_mint,
            sol_amount, usd_value, tx_sig, entry_price_usd=sol_price,
        )

        # ── Fee collection (best-effort, async) ──
        try:
            # Collect platform fee → ApexFlash hot wallet
            if FEE_COLLECT_WALLET and fee_lamports > 5000:
                # Check if user was referred → split fee
                referrer_id = user.get("referred_by", 0)
                if referrer_id and referrer_id in users:
                    referrer = users[referrer_id]
                    from core.config import get_referral_pct
                    ref_pct = get_referral_pct(referrer.get("referral_count", 0))
                    referral_share = int(fee_lamports * ref_pct / 100)
                    platform_share = fee_lamports - referral_share

                    # Platform fee
                    await collect_fee(keypair, platform_share, FEE_COLLECT_WALLET)
                    # Referrer share → referrer's bot wallet
                    if referrer.get("wallet_pubkey") and referral_share > 5000:
                        ref_kp = keypair  # fee comes from trader's wallet
                        await transfer_sol(ref_kp, referrer["wallet_pubkey"], referral_share)
                        referrer["referral_earnings"] = referrer.get("referral_earnings", 0) + referral_share / 1e9
                        logger.info(f"Referral fee ({ref_pct}%): {referral_share} lamports -> user {referrer_id}")
                else:
                    # No referrer — full fee to platform
                    await collect_fee(keypair, fee_lamports, FEE_COLLECT_WALLET)
        except Exception as fee_err:
            logger.warning(f"Fee collection failed (non-fatal): {fee_err}")

        # ── Social proof notifications (Discord + Telegram channel) ──
        try:
            uname = query.from_user.username or "Anon"
            await notify_discord_trade(uname, "BUY", f"{sol_amount} SOL", token_name, tx_sig, fee_sol)
            await notify_channel_trade(
                context.bot, "BUY", sol_amount, token_name, tx_sig,
                token_mint=target_mint, sol_price=sol_price,
                fee_sol=fee_sol,
            )
        except Exception:
            pass

        # ── SL/TP prompt (send as separate message after the buy confirmation) ──
        try:
            token_decimals = context.user_data.get("target_decimals", 0)
            await _ask_sl_tp(
                chat_id=query.from_user.id,
                user=user,
                context=context,
                bot=context.bot,
                mint=target_mint,
                token_name=token_name,
                entry_sol=sol_amount,
                token_amount_raw=str(out_amount),
                token_decimals=token_decimals,
                tx_sig=tx_sig,
                signal_grade=context.user_data.get("target_signal_grade", ""),
            )
        except Exception as sltp_err:
            logger.warning(f"SL/TP prompt failed (non-fatal): {sltp_err}")
    else:
        reason = swap_err or "Unknown error"
        text = (
            "\u274c *Swap Failed*\n\n"
            f"Reason: `{reason}`\n\n"
            "Check your balance and try again."
        )
        kb = [
            [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
            [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
            [_back_main()[0]],
        ]
        logger.error(f"BUY FAILED: user={query.from_user.id} amount={sol_amount} token={target_mint[:12]} reason={reason}")
        # Notify admin with full error detail for diagnosis
        try:
            for aid in ADMIN_IDS:
                await context.bot.send_message(
                    chat_id=aid,
                    text=f"🔴 BUY FAILED\nUser: {query.from_user.id}\nToken: `{target_mint[:20]}`\nAmount: {sol_amount} SOL\nError: `{reason[:300]}`",
                    parse_mode="Markdown",
                )
        except Exception:
            pass

    await _safe_edit_message(
        query, text, reply_markup=InlineKeyboardMarkup(kb),
    )


def _log_sell_event(user_id: int, status: str, reason: str, mint: str = "", extra: str = "") -> None:
    """Push a sell audit entry to a Redis ring buffer (v3.23.22).

    status: 'success' | 'fail'
    Keeps last 30 entries under apexflash:sell_diag so /sell_diag is self-serve.
    """
    try:
        from core.persistence import _get_redis as _pr
        r = _pr()
        if not r:
            return
        from datetime import datetime, timezone
        entry = json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "uid": user_id,
            "status": status,
            "reason": reason,
            "mint": (mint or "")[:12],
            "extra": (extra or "")[:120],
        })
        r.lpush("apexflash:sell_diag", entry)
        r.ltrim("apexflash:sell_diag", 0, 29)
    except Exception as _e:
        logger.debug(f"_log_sell_event failed: {_e}")


async def cmd_sell_diag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/sell_diag — Admin: show last 30 sell events (success + failure reasons)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return

    try:
        from core.persistence import _get_redis as _pr
        r = _pr()
        if not r:
            await update.message.reply_text("\u26a0\ufe0f Redis unavailable — no sell diag data.")
            return

        entries_raw = r.lrange("apexflash:sell_diag", 0, 29) or []
        if not entries_raw:
            await update.message.reply_text(
                "\U0001f4ca *Sell Diagnostic*\n\n_No sell events logged yet (v3.23.22+)._\n"
                "_Try a sell from the bot; events will appear here._",
                parse_mode="Markdown"
            )
            return

        lines = ["\U0001f4ca *Sell Diagnostic \u2014 last 30 events*", ""]
        counts = {"success": 0, "fail": 0}
        fail_reasons: dict = {}

        for raw in entries_raw:
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            counts[ev.get("status", "fail")] = counts.get(ev.get("status", "fail"), 0) + 1
            if ev.get("status") == "fail":
                reason = ev.get("reason", "unknown")
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            icon = "\u2705" if ev.get("status") == "success" else "\u274c"
            lines.append(
                f"{icon} `{ev.get('ts', '')[-8:]}` u={ev.get('uid')} {ev.get('reason')} "
                f"mint=`{ev.get('mint', '')}`"
            )

        total = counts["success"] + counts["fail"]
        success_rate = (counts["success"] / total * 100) if total > 0 else 0.0
        summary = [
            "",
            f"\U0001f4c8 *Summary:* {counts['success']}/{total} success ({success_rate:.0f}%)",
        ]
        if fail_reasons:
            summary.append("\U0001f534 *Top failure reasons:*")
            for reason, n in sorted(fail_reasons.items(), key=lambda x: -x[1])[:5]:
                summary.append(f"\u2022 `{reason}` \u2014 {n}\u00d7")

        text = "\n".join(lines + summary)
        # Telegram message limit: 4096 chars
        if len(text) > 3900:
            text = text[:3900] + "\n\n_\u2026truncated_"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_sell_diag failed: {e}")
        await update.message.reply_text(f"\u26a0\ufe0f sell_diag error: `{e}`", parse_mode="Markdown")


# ============================================================
# v3.23.24 — Tier-Board admin commands (mobile companion for promo/tier_board.html)
# ISO9001: all changes survive restart via Redis. Bot-safe: every handler wrapped.
# Erik's rule: bot must NEVER crash. Redis-unavailable = graceful degradation.
# ============================================================

_BN_KEY = "apexflash:bottlenecks"      # LPUSH JSON, LTRIM 0..49 (keep last 50)
_BN_MAX = 50
_BN_VALID_STATUS = {"PROBLEM", "STALL", "STARTED", "ON-GOING", "DONE", "BLOCKED"}
_BN_VALID_TIER = {"T1", "T2", "T3"}


def _bn_redis():
    """Return Redis client or None (never raises)."""
    try:
        from core.persistence import _get_redis as _pr
        return _pr()
    except Exception as _e:
        logger.debug(f"_bn_redis failed: {_e}")
        return None


async def cmd_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin_status — Tier-Board live snapshot: version, users, trades, bottlenecks."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return
    try:
        r = _bn_redis()
        # Bot version (this process)
        bot_ver = VERSION
        # User count from in-memory dict (monolith pattern)
        try:
            n_users = len(users) if isinstance(users, dict) else 0
        except Exception:
            n_users = -1
        # Redis-backed KPIs (best-effort)
        n_trades_today = 0
        n_bn_open = 0
        sell_success_pct = None
        if r is not None:
            try:
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                n_trades_today = int(r.get(f"platform:trades:{today}") or 0)
            except Exception:
                pass
            try:
                entries = r.lrange(_BN_KEY, 0, _BN_MAX - 1) or []
                for raw in entries:
                    try:
                        bn = json.loads(raw)
                        if bn.get("status") not in ("DONE",):
                            n_bn_open += 1
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                sd = r.lrange("apexflash:sell_diag", 0, 29) or []
                ok = sum(1 for raw in sd if (json.loads(raw).get("status") == "success"))
                if sd:
                    sell_success_pct = int(ok / len(sd) * 100)
            except Exception:
                pass

        redis_state = "UP" if r is not None else "DOWN"
        lines = [
            "\U0001f3db *Tier-Board \u2014 /admin\\_status*",
            "",
            f"\U0001f4cc *Version:* `{bot_ver}` (bot-process)",
            f"\U0001f4be *Redis:* `{redis_state}`",
            f"\U0001f464 *Users:* `{n_users}`",
            f"\U0001f4c8 *Trades today:* `{n_trades_today}`",
            f"\U0001f6a7 *Open bottlenecks:* `{n_bn_open}`",
        ]
        if sell_success_pct is not None:
            lines.append(f"\U0001f4b8 *Sell success 30d:* `{sell_success_pct}%`")
        lines += [
            "",
            "_Commands:_ `/admin_bn_add` `/admin_bn_list` `/admin_bn_close`",
            "_Dashboard:_ `promo/tier_board.html`",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_admin_status failed: {e}")
        try:
            await update.message.reply_text(f"\u26a0\ufe0f admin_status error: `{e}`", parse_mode="Markdown")
        except Exception:
            pass


async def cmd_admin_bn_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin_bn_add <TIER> <CAT> <STATUS> <DEADLINE> <aktie...>
    Example: /admin_bn_add T3 TECH PROBLEM 2026-04-21 Sell knop stuurt 0.0000
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return
    try:
        args = context.args or []
        if len(args) < 5:
            await update.message.reply_text(
                "*Usage:* `/admin_bn_add <T1|T2|T3> <CAT> <STATUS> <YYYY-MM-DD> <aktie...>`\n"
                f"_STATUS in:_ {', '.join(sorted(_BN_VALID_STATUS))}",
                parse_mode="Markdown"
            )
            return
        tier, cat, status, deadline = args[0].upper(), args[1].upper(), args[2].upper(), args[3]
        aktie = " ".join(args[4:])
        if tier not in _BN_VALID_TIER:
            await update.message.reply_text(f"\u274c TIER must be one of: {', '.join(sorted(_BN_VALID_TIER))}")
            return
        if status not in _BN_VALID_STATUS:
            await update.message.reply_text(f"\u274c STATUS must be one of: {', '.join(sorted(_BN_VALID_STATUS))}")
            return

        from datetime import datetime, timezone
        bn_id = f"bn_{int(datetime.now(timezone.utc).timestamp())}"
        entry = {
            "id": bn_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "creator": f"tg:{update.effective_user.id}",
            "owner": "T2-AI-CEO",   # default to Claude; Erik can reassign
            "status": status,
            "aktie": aktie,
            "cat": cat,
            "deadline": deadline,
            "tier": tier,
            "note": "",
        }
        r = _bn_redis()
        if r is None:
            await update.message.reply_text("\u26a0\ufe0f Redis DOWN \u2014 bottleneck NOT persisted.")
            return
        r.lpush(_BN_KEY, json.dumps(entry))
        r.ltrim(_BN_KEY, 0, _BN_MAX - 1)
        await update.message.reply_text(
            f"\u2705 Bottleneck added: `{bn_id}`\n*{tier}* \u00b7 *{status}* \u00b7 deadline `{deadline}`\n\u2192 {aktie}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"cmd_admin_bn_add failed: {e}")
        try:
            await update.message.reply_text(f"\u26a0\ufe0f bn_add error: `{e}`", parse_mode="Markdown")
        except Exception:
            pass


async def cmd_admin_bn_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin_bn_list [tier] — list open bottlenecks (optionally filter by T1/T2/T3)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return
    try:
        tier_filter = None
        if context.args:
            tf = context.args[0].upper()
            if tf in _BN_VALID_TIER:
                tier_filter = tf
        r = _bn_redis()
        if r is None:
            await update.message.reply_text("\u26a0\ufe0f Redis DOWN \u2014 cannot list.")
            return
        raw_entries = r.lrange(_BN_KEY, 0, _BN_MAX - 1) or []
        if not raw_entries:
            await update.message.reply_text("\U0001f7e2 *No bottlenecks.* Clean board.", parse_mode="Markdown")
            return
        lines = [f"\U0001f4cb *Bottlenecks* ({'all' if not tier_filter else tier_filter})", ""]
        shown = 0
        for raw in raw_entries:
            try:
                bn = json.loads(raw)
            except Exception:
                continue
            if bn.get("status") == "DONE":
                continue
            if tier_filter and bn.get("tier") != tier_filter:
                continue
            icon = {"PROBLEM": "\U0001f534", "STALL": "\U0001f7e0", "STARTED": "\U0001f535",
                    "ON-GOING": "\U0001f7e1", "BLOCKED": "\u26d4"}.get(bn.get("status"), "\u26aa")
            lines.append(
                f"{icon} `{bn.get('id','?')}` \u00b7 *{bn.get('tier','?')}* \u00b7 "
                f"{bn.get('status','?')} \u00b7 dl `{bn.get('deadline','?')}`\n"
                f"    \u2192 {bn.get('aktie','?')[:120]}"
            )
            shown += 1
            if shown >= 15:
                lines.append(f"\n_\u2026 truncated at 15 (total open > 15)_")
                break
        if shown == 0:
            lines.append("_(none match filter)_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_admin_bn_list failed: {e}")
        try:
            await update.message.reply_text(f"\u26a0\ufe0f bn_list error: `{e}`", parse_mode="Markdown")
        except Exception:
            pass


async def cmd_admin_bn_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin_bn_close <bn_id> [note] — mark bottleneck DONE (audit trail preserved)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return
    try:
        args = context.args or []
        if not args:
            await update.message.reply_text("*Usage:* `/admin_bn_close <bn_id> [note]`", parse_mode="Markdown")
            return
        bn_id = args[0]
        note = " ".join(args[1:]) if len(args) > 1 else ""
        r = _bn_redis()
        if r is None:
            await update.message.reply_text("\u26a0\ufe0f Redis DOWN \u2014 cannot close.")
            return
        raw_entries = r.lrange(_BN_KEY, 0, _BN_MAX - 1) or []
        updated = False
        new_list = []
        for raw in raw_entries:
            try:
                bn = json.loads(raw)
            except Exception:
                new_list.append(raw)
                continue
            if bn.get("id") == bn_id and bn.get("status") != "DONE":
                bn["status"] = "DONE"
                bn["note"] = (bn.get("note", "") + f" | closed by tg:{update.effective_user.id}: {note}").strip(" |")
                from datetime import datetime, timezone
                bn["closed_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                new_list.append(json.dumps(bn))
                updated = True
            else:
                new_list.append(raw)
        if not updated:
            await update.message.reply_text(f"\u26a0\ufe0f `{bn_id}` not found or already DONE.", parse_mode="Markdown")
            return
        # Atomic-ish rewrite: delete + rpush reversed
        pipe = r.pipeline()
        pipe.delete(_BN_KEY)
        # new_list is in original LPUSH order (newest first); rpush in that order preserves it
        for item in new_list:
            pipe.rpush(_BN_KEY, item)
        pipe.execute()
        await update.message.reply_text(f"\u2705 `{bn_id}` marked DONE.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_admin_bn_close failed: {e}")
        try:
            await update.message.reply_text(f"\u26a0\ufe0f bn_close error: `{e}`", parse_mode="Markdown")
        except Exception:
            pass


async def _cb_execute_sell(query, user, context, data):
    """Execute a sell order. data = csel_{pct}_{mint}"""
    if not user.get("wallet_pubkey") or not user.get("wallet_secret_enc"):
        await query.edit_message_text(
            "\u26a0\ufe0f No wallet found.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    # Parse mint and pct from callback_data (no user_data dependency)
    try:
        _, pct_str, sell_mint = data.split("_", 2)
        pct = int(pct_str) / 100.0
    except Exception:
        await query.edit_message_text(
            "\u26a0\ufe0f Invalid sell request.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        "\u23f3 *Fetching token balance...*", parse_mode="Markdown",
    )

    # Fresh balance fetch with RPC retry (Helius can be slow under load)
    pubkey = user["wallet_pubkey"]
    logger.info(f"SELL: fetching balance for {pubkey[:8]}... mint={sell_mint[:8]}...")
    token_info = None
    for _attempt in range(3):  # retry up to 3x with 2s delay
        tokens = await get_token_balances(pubkey)
        logger.info(f"SELL attempt {_attempt+1}: got {len(tokens)} token(s)")
        token_info = next((t for t in tokens if t["mint"] == sell_mint), None)
        if token_info:
            break
        if _attempt < 2:
            import asyncio as _aio
            await _aio.sleep(2)
    if not token_info:
        logger.warning(f"SELL: mint {sell_mint[:8]}... not found after 3 retries. Wallet has: {[t['mint'][:8] for t in tokens]}")
        _log_sell_event(query.from_user.id, "fail", "token_not_found_3x", sell_mint,
                        f"wallet_mints={[t['mint'][:8] for t in tokens]}")
        await query.edit_message_text(
            "\u26a0\ufe0f *Token not found in wallet.*\n\n"
            "_Tried 3x — RPC may be slow or token already sold._\n"
            "_Tap Retry to try again._",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Retry", callback_data="trade_sell")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    raw_total = int(token_info["raw_amount"])
    sell_raw = int(raw_total * pct)
    logger.info(f"SELL: raw_total={raw_total} sell_raw={sell_raw} pct={pct}")

    if sell_raw <= 0:
        _log_sell_event(query.from_user.id, "fail", "zero_balance", sell_mint,
                        f"raw_total={raw_total} pct={pct}")
        await query.edit_message_text(
            "\u26a0\ufe0f Nothing to sell (zero balance).",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    pct_label = f"{int(pct * 100)}%"
    await query.edit_message_text(
        f"\u23f3 *Selling {pct_label} of token...*\n\n"
        "_Getting best price via Jupiter..._",
        parse_mode="Markdown",
    )

    # Sell: swap ALL tokens → SOL, then collect fee from SOL output
    # (No upfront token deduction — fee is taken from SOL received)

    # Get quote with ESCALATING SLIPPAGE (v3.23.19)
    # Memecoins have thin liquidity → 3% often fails. Retry 3% → 10% → 25%.
    from exchanges.jupiter import get_quote_with_escalation
    quote, reason = await get_quote_with_escalation(
        input_mint=sell_mint,
        output_mint=SOL_MINT,
        amount_raw=sell_raw,
        slippage_steps=(300, 1000, 2500),
    )

    if not quote:
        if reason == "no_route":
            # Token has no Jupiter liquidity = RUGGED or paused trading
            err_text = (
                "\u26a0\ufe0f *Cannot sell — no liquidity*\n\n"
                "_Jupiter returned no route at any slippage tier (3%, 10%, 25%)._\n"
                "_This usually means the token has been **rugged** (LP removed) "
                "or trading is paused._\n\n"
                "_Token stays in your wallet. You can keep trying — sometimes "
                "liquidity returns. If it stays gone, the token is dead._"
            )
        else:  # api_error
            err_text = (
                "\u274c *Jupiter API Error*\n\n"
                "_Jupiter could not respond. Try again in 30 seconds._"
            )
        logger.warning(f"SELL quote failed mint={sell_mint[:8]}... reason={reason}")
        _log_sell_event(query.from_user.id, "fail", f"quote_{reason}", sell_mint,
                        f"slippage_steps=(300,1000,2500)")
        await query.edit_message_text(
            err_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    slip_used = quote.get("_slippage_used", DEFAULT_SLIPPAGE_BPS)
    logger.info(f"SELL quote OK at {slip_used}bps slippage")

    try:
        keypair = load_keypair(user["wallet_secret_enc"])
        logger.info(f"SELL: keypair loaded OK for {str(keypair.pubkey())[:8]}...")
    except Exception as e:
        logger.error(f"SELL: Keypair load FAILED: {e}")
        await query.edit_message_text(
            "\u274c *Wallet decryption error.*\n\n"
            "_Contact admin if this persists._",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    logger.info(f"SELL: calling execute_swap mint={sell_mint[:8]}... raw={sell_raw}")
    tx_sig, swap_err = await execute_swap(keypair, quote)
    logger.info(f"SELL: execute_swap result tx_sig={tx_sig} err={swap_err[:80] if swap_err else None}")

    if not tx_sig:
        _log_sell_event(query.from_user.id, "fail", "swap_execute_failed", sell_mint,
                        f"err={(swap_err or '')[:100]} slippage={slip_used}bps")
    else:
        _log_sell_event(query.from_user.id, "success", "swap_ok", sell_mint,
                        f"tx={tx_sig[:16]}... slippage={slip_used}bps")

    if tx_sig:
        user["total_trades"] = user.get("total_trades", 0) + 1
        _increment_daily_trades(user)
        out_lamports = int(quote.get("outAmount", 0))
        sol_received = out_lamports / 1_000_000_000

        # v3.23.23: Honest dust reporting. Users were seeing "Received: 0.0000 SOL"
        # on crashed memecoins, thought the bot was broken. Show reality instead.
        if sol_received >= 0.0001:
            received_str = f"{sol_received:.4f} SOL"
            dust_warning = ""
        elif sol_received > 0:
            received_str = "<0.0001 SOL (dust)"
            dust_warning = (
                "\n\u26a0\ufe0f *Note:* Token had near-zero liquidity — "
                "you received dust. This is the token's state, not a bot error.\n"
            )
        else:
            received_str = "0 SOL"
            dust_warning = (
                "\n\u26a0\ufe0f *Note:* Swap reported zero output. "
                "Token likely fully rugged.\n"
            )

        text = (
            "\u2705 *Sell Successful!*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f4b8 Sold: *{pct_label}* of token\n"
            f"\U0001f4b5 Received: ~*{received_str}*\n"
            f"\U0001f4b0 Fee: {PLATFORM_FEE_PCT}%\n"
            f"{dust_warning}"
            "\n"
            f"\U0001f517 [View on Solscan](https://solscan.io/tx/{tx_sig})\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )
        # Viral + affiliate hook — user just won, best moment to share/convert
        _bot_un_s = context.bot.username or "ApexFlashBot"
        _ref_link_s = f"https://t.me/{_bot_un_s}?start=ref_{query.from_user.id}"
        _share_url_s = f"https://t.me/share/url?url={_ref_link_s}&text=Net%20SOL%20gemaakt%20met%20ApexFlash!%20%F0%9F%9A%80%20Gratis%20mee%20traden"
        _aff = AFFILIATE_LINKS.get("bitunix", {})
        _aff_url = _aff.get("url", "")
        text += (
            "\n━━━━━━━━━━"
            "━━━━━━━━━━━\n"
            "\U0001f4a1 *Verdien meer:*\n"
            f"\U0001f91d [Vriend uitnodigen]({_share_url_s}) → *7 dagen Pro gratis*\n"
        )
        if _aff_url:
            text += f"\U0001f4b0 [Bitunix openen]({_aff_url}) → *50% fee terugverdienen*\n"
        kb = [
            [InlineKeyboardButton("🤝 Deel & Verdien Pro", url=_share_url_s)],
        ]
        if _aff_url:
            kb.append([InlineKeyboardButton("💰 Bitunix — 50% Fee Rebate", url=_aff_url)])
        kb += [
            [InlineKeyboardButton("\U0001f4bc View Wallet", callback_data="trade_wallet")],
            [_back_main()[0]],
        ]
        logger.info(f"SELL OK: user={query.from_user.id} pct={pct_label} tx={tx_sig}")

        # CRITICAL: Instant backup after trade (wallet balances changed)
        try:
            await _send_backup_to_admin(
                context.bot,
                f"\U0001f4b8 SELL trade backup | {pct_label} | user {query.from_user.id} | tx: {tx_sig[:16]}...",
            )
        except Exception:
            pass

        # ── Record trade for PnL + leaderboard ──
        prices = await get_crypto_prices()
        sol_price = prices.get("SOL", 0)
        sell_usd_value = sol_received * sol_price
        sell_token_name = "Token"
        for sym, info in COMMON_TOKENS.items():
            if info["mint"] == sell_mint:
                sell_token_name = sym
                break
        _record_trade(
            query.from_user.id, user, "SELL", sell_token_name, sell_mint,
            sol_received, sell_usd_value, tx_sig,
        )

        # ── Fee collection from SOL received (best-effort) ──
        try:
            sol_fee_lamports = int(out_lamports * PLATFORM_FEE_PCT / 100)
            if FEE_COLLECT_WALLET and sol_fee_lamports > 5000:
                referrer_id = user.get("referred_by", 0)
                if referrer_id and referrer_id in users:
                    referrer = users[referrer_id]
                    from core.config import get_referral_pct
                    _ref_pct = get_referral_pct(referrer.get("referral_count", 0))
                    ref_share_sol = int(sol_fee_lamports * _ref_pct / 100)
                    platform_sol = sol_fee_lamports - ref_share_sol
                    await collect_fee(keypair, platform_sol, FEE_COLLECT_WALLET)
                    if referrer.get("wallet_pubkey") and ref_share_sol > 5000:
                        await transfer_sol(keypair, referrer["wallet_pubkey"], ref_share_sol)
                        referrer["referral_earnings"] = referrer.get("referral_earnings", 0) + ref_share_sol / 1e9
                else:
                    await collect_fee(keypair, sol_fee_lamports, FEE_COLLECT_WALLET)
        except Exception as fee_err:
            logger.warning(f"Sell fee collection failed (non-fatal): {fee_err}")

        # ── Social proof notifications (Discord + Telegram channel) ──
        try:
            uname = query.from_user.username or "Anon"
            await notify_discord_trade(uname, "SELL", f"{pct_label}", sell_token_name, tx_sig, sol_received * PLATFORM_FEE_PCT / 100)
            await notify_channel_trade(
                context.bot, "SELL", sol_received, sell_token_name, tx_sig,
                token_mint=sell_mint, sol_price=sol_price,
                fee_sol=sol_received * PLATFORM_FEE_PCT / 100,
            )
        except Exception:
            pass

        # ── CRITICAL: Sync active_positions after manual sell ──
        # Without this, SL monitor keeps monitoring a sold position and
        # tries to sell tokens that no longer exist.
        try:
            positions = user.get("active_positions", [])
            updated_positions = []
            for p in positions:
                if p.get("mint") != sell_mint:
                    updated_positions.append(p)  # different token — keep
                    continue
                # Track P&L for win rate KPI (manual sell)
                try:
                    entry_sol = float(p.get("entry_sol", 0))
                    if entry_sol > 0 and pct >= 1.0:
                        pnl_sol = sol_received - entry_sol
                        pnl_pct = (pnl_sol / entry_sol) * 100
                        from core.persistence import record_trade_result
                        record_trade_result(
                            query.from_user.id, sell_token_name, pnl_pct, pnl_sol,
                            signal_grade=p.get("signal_grade", ""),
                        )
                except Exception:
                    pass
                if pct >= 1.0:
                    # 100% sell → remove position entirely
                    logger.info(f"Position removed after 100% manual sell: user={query.from_user.id} token={sell_token_name}")
                else:
                    # Partial sell → update remaining raw amount
                    original_raw = int(p.get("token_amount_raw", 0))
                    remaining_raw = original_raw - sell_raw
                    if remaining_raw > 0:
                        p["token_amount_raw"] = str(remaining_raw)
                        updated_positions.append(p)
                        logger.info(f"Position updated after {pct_label} sell: remaining_raw={remaining_raw}")
                    else:
                        logger.info(f"Position removed (0 remaining): user={query.from_user.id} token={sell_token_name}")
            user["active_positions"] = updated_positions
            _persist()
        except Exception as pos_err:
            logger.warning(f"Position sync after sell failed (non-fatal): {pos_err}")

    else:
        reason = swap_err or "Unknown error"
        text = (
            "\u274c *Sell Failed*\n\n"
            f"Reason: `{reason}`\n\n"
            "Try again or check your balance."
        )
        kb = [
            [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
            [_back_main()[0]],
        ]
        logger.error(f"SELL FAILED: user={query.from_user.id} reason={reason}")
        # Notify admin with full error detail
        try:
            for aid in ADMIN_IDS:
                await context.bot.send_message(
                    chat_id=aid,
                    text=f"🔴 SELL FAILED\nUser: {query.from_user.id}\nToken: `{sell_mint[:20]}`\nPct: {pct_label}\nError: `{reason[:300]}`",
                    parse_mode="Markdown",
                )
        except Exception:
            pass

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def handle_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect Solana token addresses or license keys pasted in chat.
    GUARANTEE: user ALWAYS gets a response if text looks like a SOL address."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text:
        return

    # ALWAYS log for admin visibility
    uid = getattr(update.effective_user, 'id', 0)
    is_sol_address = SOL_ADDR_RE.match(text)
    logger.info(f"HANDLER_ENTRY: user={uid} len={len(text)} is_addr={bool(is_sol_address)} text={text[:25]}")

    # Admin debug ack only for actual SOL addresses (avoid noise on pasted status lines).
    if uid == 7851853521 and is_sol_address:
        try:
            await update.message.reply_text(
                f"Processing `{text[:20]}...`",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    try:
        await _handle_token_address_inner(update, context, cleaned_text=text)
    except Exception as e:
        logger.error(f"handle_token_address CRASH: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await update.message.reply_text(
                f"⚠️ Error processing: {type(e).__name__}\n\nPlease try again.",
                parse_mode=None,
            )
        except Exception:
            pass


async def _handle_token_address_inner(update: Update, context: ContextTypes.DEFAULT_TYPE, cleaned_text: str = "") -> None:
    """Inner handler — separated so crashes are caught and reported."""
    if not update.message:
        return
    # Use cleaned text from wrapper (prefix-matched, dots stripped) or fall back to raw
    text = cleaned_text or (update.message.text or "").strip()
    if not text:
        return

    # FIX: Strip trailing dots/ellipsis from truncated addresses (popular token list copies)
    text = text.rstrip('.').rstrip(' ').rstrip('\u2026')  # Remove "..." and "…"

    # FIX: If text looks like start of a known token address, expand to full address
    if len(text) >= 10 and not SOL_ADDR_RE.match(text):
        for sym, info in COMMON_TOKENS.items():
            if info["mint"].startswith(text):
                logger.info(f"Prefix match: {text[:15]}... -> {sym} ({info['mint'][:15]}...)")
                text = info["mint"]
                break

    user_id = update.effective_user.id
    user = get_user(user_id)

    # Log entry for debugging
    if user_id == 7851853521 and SOL_ADDR_RE.match(text):
        logger.info(f"[ADMIN-DEBUG] Handler fired. Text={text[:20]}... awaiting={user.get('awaiting_input','')} ctx_await={context.user_data.get('awaiting_input','')}")

    # ── Handle license key input (when awaiting) ──
    if user.get("awaiting_input") == "license_key":
        # Gumroad keys look like: XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
        if re.match(r'^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}$', text):
            await _verify_and_activate(update.effective_chat.id, user_id, user, text, context)
            return
        else:
            user["awaiting_input"] = ""
            await update.message.reply_text(
                "\u26a0\ufe0f That doesn't look like a valid license key.\n\n"
                "Format: `XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`\n\n"
                "Try again: /activate",
                parse_mode="Markdown",
            )
            return

    # ── Handle custom buy amount input ──
    if context.user_data.get("awaiting_input") == "custom_buy_amount":
        context.user_data["awaiting_input"] = None
        try:
            sol_amount = float(text.replace(",", "."))
        except ValueError:
            await update.message.reply_text(
                "\u26a0\ufe0f Invalid number. Please type a valid amount (e.g. `0.25` or `3.5`).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
                ]),
                parse_mode="Markdown",
            )
            return
        if sol_amount < 0.01:
            await update.message.reply_text(
                f"\u26a0\ufe0f Minimum buy is *0.01 SOL*.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u270f\ufe0f Try Again", callback_data="buy_custom")],
                    [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
                ]),
                parse_mode="Markdown",
            )
            return
        if sol_amount > MAX_TRADE_SOL:
            await update.message.reply_text(
                f"\u26a0\ufe0f Maximum single trade is *{MAX_TRADE_SOL} SOL*.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u270f\ufe0f Try Again", callback_data="buy_custom")],
                    [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
                ]),
                parse_mode="Markdown",
            )
            return
        # Store custom amount and trigger preview
        context.user_data["custom_sol_amount"] = sol_amount
        # Show buy buttons with the custom amount
        token_name = context.user_data.get("target_name", "Token")
        target_mint = context.user_data.get("target_mint")
        if not target_mint:
            await update.message.reply_text(
                "\u26a0\ufe0f No token selected. Paste a mint address first!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
                    [_back_main()[0]],
                ]),
                parse_mode="Markdown",
            )
            return
        await update.message.reply_text(
            f"\u2705 Custom amount: *{sol_amount} SOL*\n\n"
            f"Token: *{token_name}*\n\n"
            "Tap below to preview the trade:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"\U0001f4b5 Preview Buy {sol_amount} SOL", callback_data="buy_custom_exec")],
                [InlineKeyboardButton("\u270f\ufe0f Change Amount", callback_data="buy_custom")],
                [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
            ]),
            parse_mode="Markdown",
        )
        return

    # ── Handle withdraw address input (when awaiting) ──
    if context.user_data.get("awaiting_input") == "autotrade_custom_profile":
        context.user_data["awaiting_input"] = None
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin only.")
            return

        raw = text.replace(";", ",").replace(" ", "")
        if "," not in raw:
            await update.message.reply_text(
                "⚠️ Invalid format. Use `min_move_pct,min_volume_usd` (example: `0.9,300000`).",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_autotrade")]]),
            )
            return

        try:
            move_s, vol_s = raw.split(",", 1)
            move = float(move_s)
            vol = float(vol_s)
        except Exception:
            await update.message.reply_text(
                "⚠️ Invalid numbers. Example: `0.9,300000`.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_autotrade")]]),
            )
            return

        move = max(0.30, min(move, 5.00))
        vol = max(50_000.0, min(vol, 5_000_000.0))

        from core.persistence import update_governance_config
        update_governance_config("grade_a_min_pct", move)
        update_governance_config("min_volume_usd", vol)

        await update.message.reply_text(
            f"✅ Custom profile saved\n"
            f"• min_move_pct: `{move:.2f}`\n"
            f"• min_volume_usd: `{vol:,.0f}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Autotrade Controls", callback_data="admin_autotrade")]]),
        )
        return

    if context.user_data.get("awaiting_input") == "withdraw_address":
        context.user_data["awaiting_input"] = None
        # Validate as SOL address
        if not SOL_ADDR_RE.match(text):
            await update.message.reply_text(
                "⚠️ That doesn't look like a valid Solana address.\n\n"
                "Please send a valid SOL address (32-44 characters, base58).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="trade_wallet")],
                ]),
                parse_mode="Markdown",
            )
            return
        # Block self-transfer
        if text == user.get("wallet_pubkey"):
            await update.message.reply_text(
                "⚠️ Cannot withdraw to your own bot wallet.\n\n"
                "Send a *different* SOL address (e.g. your Trust Wallet, Phantom, exchange).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="trade_wallet")],
                ]),
                parse_mode="Markdown",
            )
            return

        # Store destination and show amount options
        context.user_data["withdraw_dest"] = text
        sol_bal = float(await get_sol_balance(user["wallet_pubkey"]) or 0.0)
        available = sol_bal - MIN_SOL_RESERVE
        if available <= 0:
            context.user_data.pop("withdraw_dest", None)
            await update.message.reply_text(
                "⚠️ *Insufficient balance* — cannot withdraw.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💼 Wallet", callback_data="trade_wallet")],
                ]),
                parse_mode="Markdown",
            )
            return

        dest_short = f"{text[:6]}...{text[-4:]}"
        await update.message.reply_text(
            "📤 *Withdraw SOL*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📤 To: `{dest_short}`\n"
            f"◎ Available: *{available:.4f} SOL*\n\n"
            "💰 *How much do you want to send?*",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("25%", callback_data="withdraw_amt_25"),
                    InlineKeyboardButton("50%", callback_data="withdraw_amt_50"),
                    InlineKeyboardButton("100%", callback_data="withdraw_amt_100"),
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="withdraw_cancel")],
            ]),
            parse_mode="Markdown",
        )
        return

    # Check if it looks like a Solana address
    if not SOL_ADDR_RE.match(text):
        # Not an address — try token search by name/symbol (e.g. "PEPE", "bonk")
        if len(text) >= 2 and len(text) <= 20 and text.replace(" ", "").isalnum():
            results = await search_token(text)
            if results:
                msg = f"\U0001f50d *Search: {text}*\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                kb_rows = []
                for t in results[:5]:
                    sym = t.get("symbol", "???")
                    name = t.get("name", "Unknown")
                    mint = t.get("id") or t.get("address", "")
                    msg += f"\u2022 *{sym}* — {name}\n  `{mint}`\n\n"
                    kb_rows.append([InlineKeyboardButton(
                        f"{sym} — {name[:20]}", callback_data=f"search_{mint[:40]}"
                    )])
                msg += "_Tap a token or paste the mint address to buy!_"
                kb_rows.append([InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")])
                await update.message.reply_text(
                    msg, reply_markup=InlineKeyboardMarkup(kb_rows),
                    parse_mode="Markdown",
                )
                return
        return

    if not user.get("wallet_pubkey"):
        await update.message.reply_text(
            "\U0001f4b0 That looks like a Solana token!\n\n"
            "Create a wallet first to start trading:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
            ]),
            parse_mode="Markdown",
        )
        return

    # Look up token info
    await update.message.reply_text(
        f"\U0001f50d Looking up token `{text[:12]}...`",
        parse_mode="Markdown",
    )

    token_info = await get_token_info(text)

    if token_info and token_info.get("symbol"):
        name = token_info.get("name", "Unknown")
        symbol = token_info.get("symbol", "???")
        decimals = token_info.get("decimals", 0)

        # Analytics: track token lookup
        track_token_lookup(text, symbol)
        update_last_active(user_id)

        # Store target mint for buy callbacks
        context.user_data["target_mint"] = text
        context.user_data["target_name"] = symbol
        context.user_data["target_decimals"] = decimals

        # Get SOL balance for display (None = RPC down)
        sol_bal = await get_sol_balance(user["wallet_pubkey"])
        if sol_bal is None:
            sol_bal = 0.0
            bal_display = "⚠️ RPC busy — balance unavailable"
        else:
            prices = await get_crypto_prices()
            sol_price = prices.get("SOL", 0)
            bal_display = f"💼 Your SOL: *{sol_bal:.4f}*"
            if sol_price:
                bal_display += f" (${sol_bal * sol_price:,.2f})"

        msg = (
            f"\U0001f3af *{name}* ({symbol})\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f517 Mint: `{text}`\n"
            f"\U0001f522 Decimals: {decimals}\n"
            "\n"
            f"{bal_display}"
        )
        msg += (
            f"\n\U0001f4b0 Fee: *{PLATFORM_FEE_PCT}%* per trade\n"
            "\n"
            "\u2b07\ufe0f *Choose buy amount:*"
        )

        kb = [
            [
                InlineKeyboardButton("0.1 SOL", callback_data="buy_01"),
                InlineKeyboardButton("0.5 SOL", callback_data="buy_05"),
            ],
            [
                InlineKeyboardButton("1 SOL", callback_data="buy_1"),
                InlineKeyboardButton("5 SOL", callback_data="buy_5"),
            ],
            [InlineKeyboardButton("\u270f\ufe0f Custom Amount", callback_data="buy_custom")],
            [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            [_back_main()[0]],
        ]

        # Try to send chart image first (non-blocking — if fails, just show text)
        try:
            chart_url = await get_token_chart_url(text, hours=24)
            if chart_url:
                await update.message.reply_photo(
                    photo=chart_url,
                    caption=msg,
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    msg, reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown",
                )
        except Exception as chart_err:
            logger.warning(f"Chart send failed: {chart_err}, falling back to text")
            await update.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
            )
    else:
        # Also try to store it for selling (user might own this token)
        context.user_data["target_mint"] = text
        context.user_data["target_name"] = "Unknown"

        await update.message.reply_text(
            f"\u26a0\ufe0f Token `{text[:20]}...` not found on Jupiter.\n\n"
            "It may be a very new or illiquid token.\n"
            "Try again or paste a different address.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Anyway (0.1 SOL)", callback_data="buy_01")],
                [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            ]),
            parse_mode="Markdown",
        )


# ══════════════════════════════════════════════
# TRADE SECTION (Copy Trade + DCA via MIZAR)
# ══════════════════════════════════════════════

async def _cb_portfolio(query, user, context):
    """Show portfolio: SOL balance + token holdings + trade stats."""
    update_last_active(query.from_user.id)

    if not user.get("wallet_pubkey"):
        await query.edit_message_text(
            "\U0001f4bc *Portfolio*\n\n"
            "Create a wallet first to start tracking your trades!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f510 Create Wallet", callback_data="trade_create")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text("\U0001f4bc *Loading portfolio...*", parse_mode="Markdown")

    # Get SOL balance
    sol_bal = await get_sol_balance(user["wallet_pubkey"])
    if sol_bal is None:
        sol_bal = 0.0
    prices = await get_crypto_prices()
    sol_price = prices.get("SOL", 0)
    sol_usd = sol_bal * sol_price

    # Get token holdings
    tokens = await get_token_balances(user["wallet_pubkey"])

    # Trade stats
    total_trades = user.get("total_trades", 0)
    total_vol = user.get("total_volume_usd", 0)
    referral_earnings = user.get("referral_earnings", 0)

    # Active positions (SL/TP)
    positions = user.get("active_positions", [])

    # Build message
    msg = (
        "\U0001f4bc *Your Portfolio*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\u25ce SOL: *{sol_bal:.4f}*"
    )
    if sol_usd > 0:
        msg += f" (${sol_usd:,.2f})"
    msg += "\n"

    if tokens:
        msg += "\n\U0001f4b0 *Token Holdings:*\n"
        for t in tokens[:10]:
            # Try to find symbol
            symbol = "?"
            for sym, info in COMMON_TOKENS.items():
                if info["mint"] == t["mint"]:
                    symbol = sym
                    break
            if symbol == "?":
                symbol = f"{t['mint'][:6]}..."
            msg += f"  \u2022 *{symbol}:* {t['amount']:,.4f}\n"
    else:
        msg += "\n\U0001f4ad No tokens — all SOL\n"

    if positions:
        msg += f"\n\U0001f6e1\ufe0f *Active Positions:* {len(positions)}\n"
        for p in positions[:5]:
            sl = p.get("sl_pct", 0)
            tp = p.get("tp_pct", 0)
            entry = p.get("entry_sol", 0)
            # Try to get live value
            try:
                raw_amt = int(p.get("token_amount_raw", 0))
                if raw_amt > 0 and entry > 0:
                    live_quote = await get_quote(
                        input_mint=p.get("mint", ""),
                        output_mint="So11111111111111111111111111111111111111112",
                        amount_raw=raw_amt,
                        slippage_bps=300,
                    )
                    if live_quote and live_quote.get("outAmount"):
                        current_val = int(live_quote["outAmount"]) / 1_000_000_000
                        pnl = current_val - entry
                        pnl_pct = (pnl / entry * 100) if entry > 0 else 0
                        emoji = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                        pnl_sign = "+" if pnl >= 0 else ""
                        msg += (
                            f"  {emoji} *{p.get('token', '?')}*\n"
                            f"     Entry: {entry:.4f} → Now: {current_val:.4f} SOL\n"
                            f"     P/L: *{pnl_sign}{pnl:.4f} SOL ({pnl_sign}{pnl_pct:.1f}%)*\n"
                            f"     SL: -{sl}% | TP: +{tp}%\n"
                        )
                        continue
            except Exception:
                pass
            msg += f"  \u2022 {p.get('token', '?')} | Entry: {entry:.4f} SOL | SL: -{sl}% | TP: +{tp}%\n"

    msg += (
        f"\n\U0001f4ca *Stats:*\n"
        f"  \u2022 Trades: *{total_trades}*\n"
        f"  \u2022 Volume: *${total_vol:,.2f}*\n"
    )
    if referral_earnings > 0:
        msg += f"  \u2022 Referral earnings: *{referral_earnings:.4f} SOL*\n"

    msg += (
        f"  \u2022 Tier: *{user.get('tier', 'free').title()}*\n"
        "\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    # Build keyboard
    buy_btn = InlineKeyboardButton("\U0001f4b5 Buy", callback_data="trade_buy")
    sell_btn = InlineKeyboardButton("\U0001f4b8 Sell", callback_data="trade_sell")
    
    # Kaizen: Show Sell button only if there are active positions
    trade_row = [buy_btn]
    if positions:
        trade_row.append(sell_btn)

    kb = [
        trade_row,
        [InlineKeyboardButton("\U0001f6e1\ufe0f Positions (SL/TP)", callback_data="positions")],
        [InlineKeyboardButton("\U0001f504 Refresh", callback_data="portfolio")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        msg, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


async def _cb_copy_trade(query, user, context):
    """Copy trading via MIZAR — with LIVE marketplace data."""
    tier = TIERS.get(user["tier"], TIERS["free"])

    if not tier.get("copy_trade"):
        # Show top traders as teaser (free users see stats but can't copy)
        from exchanges.mizar import get_marketplace_bots
        top_bots = await get_marketplace_bots(limit=5)

        text = (
            "\U0001f4c8 *Copy Trading \u2014 Live Leaderboard*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        )

        if top_bots:
            for i, bot in enumerate(top_bots[:5], 1):
                name = bot.get("name", f"Bot #{i}")[:20]
                pnl = bot.get("pnl_30d", bot.get("pnl", 0))
                win_rate = bot.get("win_rate", 0)
                trades = bot.get("total_trades", 0)

                pnl_val = float(pnl) if pnl else 0
                wr_val = float(win_rate) if win_rate else 0
                pnl_emoji = "\U0001f7e2" if pnl_val > 0 else "\U0001f534"

                text += (
                    f"{i}. *{name}*\n"
                    f"   {pnl_emoji} P/L 30d: {pnl_val:+.1f}% | "
                    f"WR: {wr_val:.0f}% | "
                    f"Trades: {trades}\n\n"
                )
        else:
            text += (
                "\U0001f3c6 *Top performers copy their trades*\n"
                "\U0001f4ca Verified P/L and win rates\n"
                "\U0001f6e1 Auto stop-loss protection\n\n"
            )

        text += (
            "\U0001f512 *Unlock Copy Trading with Pro:*\n"
            "\u2022 Auto-copy top traders\n"
            "\u2022 Set your own risk limits\n"
            "\u2022 Stop-loss protection included"
        )
        _pro_sol = await _get_tier_price_sol("pro")
        _elite_sol = await _get_tier_price_sol("elite")
        kb = [
            [InlineKeyboardButton(f"\U0001f680 Pro \u2014 {_pro_sol} SOL", callback_data="pay_sol_pro")],
            [InlineKeyboardButton(f"\U0001f451 Elite \u2014 {_elite_sol} SOL", callback_data="pay_sol_elite")],
            [InlineKeyboardButton("\U0001f517 Preview MIZAR", url=MIZAR_REFERRAL_URL)],
            [_back_main()[0]],
        ]
    else:
        # Pro/Elite users — live leaderboard + direct copy link
        from exchanges.mizar import get_marketplace_bots
        top_bots = await get_marketplace_bots(limit=5)

        text = (
            "\U0001f4c8 *Copy Trading \u2014 Live Leaderboard*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        )

        if top_bots:
            for i, bot in enumerate(top_bots[:5], 1):
                name = bot.get("name", f"Bot #{i}")[:20]
                pnl = bot.get("pnl_30d", bot.get("pnl", 0))
                win_rate = bot.get("win_rate", 0)
                trades = bot.get("total_trades", 0)
                copiers = bot.get("copiers", bot.get("followers", 0))

                pnl_val = float(pnl) if pnl else 0
                wr_val = float(win_rate) if win_rate else 0
                pnl_emoji = "\U0001f7e2" if pnl_val > 0 else "\U0001f534"

                text += (
                    f"{i}. *{name}*\n"
                    f"   {pnl_emoji} P/L 30d: {pnl_val:+.1f}% | "
                    f"WR: {wr_val:.0f}% | "
                    f"Copiers: {copiers}\n\n"
                )

            text += "\U0001f4a1 Click below to start copying the best traders:"
        else:
            text += (
                "Copy profitable traders automatically.\n"
                "Powered by MIZAR.\n\n"
                "\U0001f3c6 *How it works:*\n"
                "1\ufe0f\u20e3 Browse top-performing traders\n"
                "2\ufe0f\u20e3 Connect your exchange API\n"
                "3\ufe0f\u20e3 Set your risk & position size\n"
                "4\ufe0f\u20e3 Trades are copied automatically"
            )

        kb = [
            [InlineKeyboardButton("\U0001f680 Start Copying Top Traders", url=MIZAR_REFERRAL_URL)],
            [InlineKeyboardButton("\U0001f4d6 How It Works", callback_data="help_copy")],
            [_back_main()[0]],
        ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_dca_bot(query, user, context):
    """DCA Bot via MIZAR."""
    tier = TIERS.get(user["tier"], TIERS["free"])

    if not tier.get("dca_bot"):
        text = (
            "\U0001f916 *DCA Bot*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "\U0001f512 *Pro Feature*\n"
            "\n"
            "Automate Dollar-Cost Averaging on\n"
            "any token. Set it and forget it.\n"
            "\n"
            "\u2705 Auto-buy on schedule\n"
            "\u2705 Smart entry signals\n"
            "\u2705 Take-profit automation\n"
            "\u2705 Multi-pair support\n"
            "\n"
            "Unlock with Pro or Elite:"
        )
        _pro_sol = await _get_tier_price_sol("pro")
        _elite_sol = await _get_tier_price_sol("elite")
        kb = [
            [InlineKeyboardButton(f"\U0001f680 Pro \u2014 {_pro_sol} SOL", callback_data="pay_sol_pro")],
            [InlineKeyboardButton(f"\U0001f451 Elite \u2014 {_elite_sol} SOL", callback_data="pay_sol_elite")],
            [_back_main()[0]],
        ]
    else:
        text = (
            "\U0001f916 *DCA Bot*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "Automated Dollar-Cost Averaging.\n"
            "Powered by MIZAR.\n"
            "\n"
            "\U0001f4cb *Popular Strategies:*\n"
            "\u2022 BTC Weekly DCA \u2014 Best for long-term\n"
            "\u2022 ETH Daily Micro \u2014 Smooth entry\n"
            "\u2022 SOL Dip Buyer \u2014 Buy the dips\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Set up your strategy on MIZAR:"
        )
        kb = [
            [InlineKeyboardButton("\U0001f517 Open MIZAR Platform", url=MIZAR_REFERRAL_URL)],
            [InlineKeyboardButton("\U0001f4d6 How DCA Works", callback_data="help_dca")],
            [_back_main()[0]],
        ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# EXCHANGE SECTION
# ══════════════════════════════════════════════

async def _cb_exchanges(query, user, context):
    """Show partner hub with exchange + tools categories."""
    text = (
        "\U0001f4b1 *Partner Hub*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Trade with the lowest fees & access\n"
        "top crypto tools with our deals:\n"
    )

    kb = [
        [
            InlineKeyboardButton("\U0001f3e6 Exchanges", callback_data="aff_exchanges"),
            InlineKeyboardButton("\U0001f6e0 Crypto Tools", callback_data="aff_tools"),
        ],
        [_back_main()[0]],
    ]

    # Show featured exchanges preview
    text += "\n\U0001f525 *Top Exchange Deals:*\n"
    for key, aff in AFFILIATE_LINKS.items():
        if aff.get("featured"):
            text += f"\u2022 *{aff['name']}* \u2014 {aff['commission']} rebate\n"

    text += "\n\U0001f6e0 *Top Tools:*\n"
    for key, aff in TOOL_AFFILIATE_LINKS.items():
        if aff.get("featured"):
            text += f"\u2022 *{aff['name']}* \u2014 {aff['commission']}\n"

    text += "\n\U0001f4a1 _Tap a category for all partner links!_"

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_aff_exchanges(query, user, context):
    """Show all exchange affiliate links."""
    text = (
        "\U0001f3e6 *Partner Exchanges*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
    )

    # Featured
    for key, aff in AFFILIATE_LINKS.items():
        if aff.get("featured"):
            text += (
                f"\U0001f525 *{aff['name']}* \u2014 {aff['commission']} rebate\n"
                f"   _{aff.get('description', '')}_\n\n"
            )

    text += "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"

    # Others
    for key, aff in AFFILIATE_LINKS.items():
        if not aff.get("featured"):
            text += f"\u2022 *{aff['name']}* \u2014 {aff['commission']} rebate\n"

    text += "\n\U0001f4a1 _Sign up via our links for fee rebates!_"

    # Buttons
    featured_btns = [
        InlineKeyboardButton(f"\U0001f525 {v['name']}", url=v["url"])
        for k, v in AFFILIATE_LINKS.items() if v.get("featured") and v.get("url", "").find("YOUR_REF") == -1
    ]
    other_btns = [
        InlineKeyboardButton(v["name"], url=v["url"])
        for k, v in AFFILIATE_LINKS.items()
        if not v.get("featured") and v.get("url", "").find("YOUR_REF") == -1 and v.get("url", "").strip()
    ]

    kb = []
    for i in range(0, len(featured_btns), 2):
        kb.append(featured_btns[i:i + 2])
    if other_btns:
        for i in range(0, len(other_btns), 3):
            kb.append(other_btns[i:i + 3])
    kb.append([InlineKeyboardButton("\u25c0 Partners", callback_data="exchanges")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_aff_tools(query, user, context):
    """Show crypto tools affiliate links."""
    text = (
        "\U0001f6e0 *Crypto Tools & Security*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
    )

    # Featured tools
    for key, aff in TOOL_AFFILIATE_LINKS.items():
        if aff.get("featured"):
            text += (
                f"\U0001f525 *{aff['name']}* \u2014 {aff['commission']}\n"
                f"   _{aff.get('description', '')}_\n\n"
            )

    text += "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"

    # Others
    for key, aff in TOOL_AFFILIATE_LINKS.items():
        if not aff.get("featured"):
            text += f"\u2022 *{aff['name']}* \u2014 {aff['commission']}\n"

    text += "\n\U0001f512 _Protect your gains & level up your trading!_"

    # Buttons
    featured_btns = [
        InlineKeyboardButton(f"\U0001f525 {v['name']}", url=v["url"])
        for k, v in TOOL_AFFILIATE_LINKS.items()
        if v.get("featured") and v.get("url", "").strip()
    ]
    other_btns = [
        InlineKeyboardButton(v["name"], url=v["url"])
        for k, v in TOOL_AFFILIATE_LINKS.items()
        if not v.get("featured") and v.get("url", "").strip()
    ]

    kb = []
    for i in range(0, len(featured_btns), 2):
        kb.append(featured_btns[i:i + 2])
    if other_btns:
        for i in range(0, len(other_btns), 3):
            kb.append(other_btns[i:i + 3])
    kb.append([InlineKeyboardButton("\u25c0 Partners", callback_data="exchanges")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# PREMIUM SECTION
# ══════════════════════════════════════════════

async def _get_tier_price_sol(tier: str) -> float:
    """Calculate SOL price dynamically from live SOL/USD rate.
    Always charges the USD equivalent — SOL amount adjusts to market."""
    usd = PRO_PRICE_USD if tier == "pro" else ELITE_PRICE_USD
    prices = await get_crypto_prices()
    sol_usd = prices.get("SOL", 0)
    if sol_usd <= 0:
        sol_usd = FALLBACK_PRICES.get("SOL", 130)
    raw = usd / sol_usd
    # Round up to 4 decimals so we never undercharge
    import math
    return math.ceil(raw * 10000) / 10000


async def _cb_premium(query, user, context):
    """Show premium tiers with SOL payment + Gumroad backup."""
    current = user.get("tier", "free")
    tier_info = TIERS[current]

    pro_sol = await _get_tier_price_sol("pro")
    elite_sol = await _get_tier_price_sol("elite")

    text = (
        "\U0001f48e *ApexFlash Premium*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"Your plan: *{tier_info['emoji']} {tier_info['name']}*\n"
        f"\n"
        "\U0001f193 *Free*\n"
        "\u2022 ETH whale alerts (5min delay)\n"
        "\u2022 3 tracked wallets\n"
        "\u2022 Exchange affiliate deals\n"
        "\n"
        f"\U0001f680 *Pro \u2014 ${PRO_PRICE_USD}/mo ({pro_sol} SOL)*\n"
        "\u2022 ETH + SOL alerts (instant)\n"
        "\u2022 20 tracked wallets\n"
        "\u2022 Copy Trading access\n"
        "\u2022 DCA Bot access\n"
        "\u2022 Priority support\n"
        "\n"
        f"\U0001f451 *Elite \u2014 ${ELITE_PRICE_USD}/mo ({elite_sol} SOL)*\n"
        "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
        "\u2022 100 tracked wallets\n"
        "\u2022 AI-powered signals\n"
        "\u2022 Copy Trading + DCA Bot\n"
        "\u2022 Custom alert thresholds\n"
        "\u2022 1-on-1 onboarding call\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "\U0001f4b0 *Pay with SOL* \u2014 0% fee, instant activation!\n"
        "\U0001f4c8 SOL price updates live \u2014 you always pay the USD equivalent.\n"
    )

    # Only show Gumroad card option if products are configured
    _gumroad_ready = (
        GUMROAD_PRO_URL and "gumroad.com/l/" in GUMROAD_PRO_URL
        and not GUMROAD_PRO_URL.endswith("/l/")
    )
    if _gumroad_ready:
        text += "\U0001f4b3 *Pay with card* \u2014 via Gumroad\n"

    kb = []
    if current == "free":
        kb.append([
            InlineKeyboardButton(
                f"\U0001f680 Pro \u2014 {pro_sol} SOL", callback_data="pay_sol_pro"),
            InlineKeyboardButton(
                f"\U0001f451 Elite \u2014 {elite_sol} SOL", callback_data="pay_sol_elite"),
        ])
        if _gumroad_ready:
            kb.append([
                InlineKeyboardButton("\U0001f4b3 Pro $9.99 (Card)", url=GUMROAD_PRO_URL),
                InlineKeyboardButton("\U0001f4b3 Elite $29.99 (Card)", url=GUMROAD_ELITE_URL),
            ])
        kb.append([InlineKeyboardButton("\U0001f511 Activate License Key", callback_data="activate_license")])
    elif current == "pro":
        kb.append([InlineKeyboardButton(
            f"\U0001f451 Upgrade Elite \u2014 {elite_sol} SOL", callback_data="pay_sol_elite")])
        if _gumroad_ready:
            kb.append([InlineKeyboardButton("\U0001f4b3 Elite $29.99 (Card)", url=GUMROAD_ELITE_URL)])
        kb.append([InlineKeyboardButton("\U0001f511 Activate License Key", callback_data="activate_license")])

    # Show expiry for premium users
    if current != "free" and user.get("premium_expires"):
        try:
            expires = datetime.fromisoformat(user["premium_expires"])
            days_left = (expires - datetime.now(timezone.utc)).days
            text += f"\n\u23f0 *{days_left} days* remaining on your plan.\n"
        except (ValueError, TypeError):
            pass

    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_activate_license(query, user, context):
    """Prompt user to enter their Gumroad license key."""
    user["awaiting_input"] = "license_key"
    text = (
        "\U0001f511 *Activate License Key*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "Enter your Gumroad license key below.\n\n"
        "You received it by email after purchasing "
        "Pro or Elite on Gumroad.\n\n"
        "Format: `XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`\n\n"
        "_Just paste it in the chat and I'll verify it instantly!_"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u274c Cancel", callback_data="premium")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


async def _cb_pay_sol_pro(query, user, context):
    """Handle SOL payment for Pro tier."""
    price_sol = await _get_tier_price_sol("pro")
    await _process_sol_payment(query, user, context, "pro", price_sol)


async def _cb_pay_sol_elite(query, user, context):
    """Handle SOL payment for Elite tier."""
    price_sol = await _get_tier_price_sol("elite")
    await _process_sol_payment(query, user, context, "elite", price_sol)


async def _process_sol_payment(query, user, context, tier: str, price_sol: float):
    """Process SOL payment from user's bot wallet to fee wallet."""
    # Check wallet exists
    if not user.get("wallet_pubkey"):
        text = (
            "\u26a0\ufe0f *Wallet Required*\n\n"
            "You need a bot wallet to pay with SOL.\n"
            "Create one first, then fund it.\n"
        )
        kb_rows = [
            [InlineKeyboardButton("\U0001f4b0 Create Wallet", callback_data="trade_create")],
        ]
        _gum_url = GUMROAD_PRO_URL if tier == "pro" else GUMROAD_ELITE_URL
        if _gum_url and "gumroad.com/l/" in _gum_url and not _gum_url.endswith("/l/"):
            kb_rows.append([InlineKeyboardButton("\U0001f4b3 Pay with Card instead", url=_gum_url)])
        kb_rows.append([_back_main()[0]])
        kb = InlineKeyboardMarkup(kb_rows)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        return

    # Check balance
    balance = await get_sol_balance(user["wallet_pubkey"])
    if balance is None or balance < price_sol:
        text = (
            f"\u26a0\ufe0f *Insufficient Balance*\n\n"
            f"Required: *{price_sol} SOL*\n"
            f"Your balance: *{balance:.4f} SOL*\n\n"
            f"Deposit SOL to your bot wallet:\n"
            f"`{user['wallet_pubkey']}`\n\n"
            f"Then come back and tap Pay again!"
        )
        kb_rows = [
            [InlineKeyboardButton("\U0001f504 Check Again", callback_data=f"pay_sol_{tier}")],
        ]
        _gum_url = GUMROAD_PRO_URL if tier == "pro" else GUMROAD_ELITE_URL
        if _gum_url and "gumroad.com/l/" in _gum_url and not _gum_url.endswith("/l/"):
            kb_rows.append([InlineKeyboardButton("\U0001f4b3 Pay with Card", url=_gum_url)])
        kb_rows.append([InlineKeyboardButton(
            "\U0001f525 Buy SOL on MEXC (70% fee back)",
            url=AFFILIATE_LINKS["mexc"]["url"],
        )])
        kb_rows.append([_back_main()[0]])
        kb = InlineKeyboardMarkup(kb_rows)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        return

    # Confirm payment
    tier_info = TIERS[tier]
    text = (
        f"\U0001f4b0 *Confirm Payment*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"Plan: *{tier_info['emoji']} {tier_info['name']}*\n"
        f"Price: *{price_sol} SOL*\n"
        f"Duration: *30 days*\n\n"
        f"Your balance: *{balance:.4f} SOL*\n"
        f"After payment: *{balance - price_sol:.4f} SOL*\n\n"
        f"Tap \u2705 to confirm payment."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"\u2705 Pay {price_sol} SOL", callback_data=f"confirm_pay_{tier}")],
        [InlineKeyboardButton("\u274c Cancel", callback_data="premium")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


async def _cb_confirm_pay_pro(query, user, context):
    """Execute Pro payment."""
    price_sol = await _get_tier_price_sol("pro")
    await _execute_sol_payment(query, user, context, "pro", price_sol)


async def _cb_confirm_pay_elite(query, user, context):
    """Execute Elite payment."""
    price_sol = await _get_tier_price_sol("elite")
    await _execute_sol_payment(query, user, context, "elite", price_sol)


async def _execute_sol_payment(query, user, context, tier: str, price_sol: float):
    """Execute the SOL transfer and activate tier."""
    await query.edit_message_text(
        "\u23f3 Processing payment...", parse_mode="Markdown",
    )

    try:
        keypair = load_keypair(user["wallet_secret_enc"])
        if not keypair:
            raise ValueError("Could not load wallet keypair")

        lamports = int(price_sol * 1_000_000_000)

        # Transfer SOL to fee collection wallet
        if not FEE_COLLECT_WALLET:
            raise ValueError("Fee wallet not configured")

        success = await collect_fee(keypair, lamports, FEE_COLLECT_WALLET)
        if not success:
            raise ValueError("Transaction failed")

        # Activate premium tier
        from datetime import timedelta
        user["tier"] = tier
        user["premium_expires"] = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).isoformat()

        tier_info = TIERS[tier]
        text = (
            f"\u2705 *Payment Successful!*\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Plan: *{tier_info['emoji']} {tier_info['name']}*\n"
            f"Paid: *{price_sol} SOL*\n"
            f"Active for: *30 days*\n\n"
            f"\U0001f389 Welcome to {tier_info['name']}! Enjoy:\n"
        )
        if tier == "pro":
            text += (
                "\u2022 ETH + SOL instant alerts\n"
                "\u2022 20 tracked wallets\n"
                "\u2022 Copy Trading & DCA Bot\n"
            )
        else:
            text += (
                "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
                "\u2022 100 tracked wallets\n"
                "\u2022 AI-powered signals\n"
                "\u2022 Copy Trading & DCA Bot\n"
            )

        track_paid_conversion(query.from_user.id, tier)
        logger.info(f"Premium payment: user {query.from_user.id} → {tier} ({price_sol} SOL)")

        kb = InlineKeyboardMarkup([[_back_main()[0]]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

        # Social proof
        try:
            uname = query.from_user.username or "Anon"
            await notify_discord_trade(uname, "UPGRADE", f"{price_sol} SOL", f"{tier_info['name']} Plan", "", price_sol)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Premium payment error: {e}")
        text = (
            f"\u274c *Payment Failed*\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Your SOL has not been deducted.\n"
            f"Try again or pay with card."
        )
        kb_rows = [
            [InlineKeyboardButton(f"\U0001f504 Try Again", callback_data=f"pay_sol_{tier}")],
        ]
        _gum_url = GUMROAD_PRO_URL if tier == "pro" else GUMROAD_ELITE_URL
        if _gum_url and "gumroad.com/l/" in _gum_url and not _gum_url.endswith("/l/"):
            kb_rows.append([InlineKeyboardButton("\U0001f4b3 Pay with Card", url=_gum_url)])
        kb_rows.append([_back_main()[0]])
        kb = InlineKeyboardMarkup(kb_rows)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


# ══════════════════════════════════════════════
# REFERRAL SECTION
# ══════════════════════════════════════════════

async def _legacy_cb_referral(query, user, context):
    """Referral program main menu."""
    uid = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    # Count referrals
    ref_count = user.get("referral_count", 0)
    if ref_count == 0:
        # Recount from users store
        ref_count = sum(1 for u in users.values() if u.get("referred_by") == uid)
        user["referral_count"] = ref_count

    earnings_sol = user.get("referral_earnings", 0.0)
    prices = await get_crypto_prices()
    sol_price = prices.get("SOL", 0)
    earnings_usd = earnings_sol * sol_price

    text = (
        "\U0001f91d *Referral Program*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Earn *25% of every trade fee* from\n"
        "friends you invite! Passive income\n"
        "for life \u2014 every trade they make,\n"
        "you earn.\n"
        "\n"
        "\U0001f4b0 *How it works:*\n"
        "1\ufe0f\u20e3 Share your unique referral link\n"
        "2\ufe0f\u20e3 Friend signs up and trades\n"
        "3\ufe0f\u20e3 You earn 25% of their 1% trade fee\n"
        "4\ufe0f\u20e3 Earnings sent to your bot wallet\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f465 Referrals: *{ref_count}*\n"
        f"\U0001f4b5 Earned: *{earnings_sol:.6f} SOL*"
    )
    if earnings_usd > 0.01:
        text += f" (${earnings_usd:,.2f})"
    text += (
        "\n\n\U0001f517 *Your link:*\n"
        f"{ref_link}\n"
        "\n"
        "_Forward this link to your friends!_\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton("\U0001f4cb Copy Link", callback_data="referral_link")],
        [InlineKeyboardButton("\U0001f4ca Referral Stats", callback_data="referral_stats")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_referral_link(query, user, context):
    """Show referral link in easy-copy format."""
    uid = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    text = (
        "\U0001f517 *Your Referral Link*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"`{ref_link}`\n"
        "\n"
        "_Tap the link above to copy it!_\n"
        "\n"
        "\U0001f4ac *Share template:*\n"
        f"_Hey! Trade crypto on Solana with the_\n"
        f"_best prices. Use my link to get started:_\n"
        f"_{ref_link}_\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton("\U0001f519 Back to Referral", callback_data="referral")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_referral_stats(query, user, context):
    """Detailed referral statistics."""
    from core.config import get_referral_pct
    uid = query.from_user.id
    ref_count = sum(1 for u in users.values() if u.get("referred_by") == uid)
    user["referral_count"] = ref_count

    # Count active referrals (those who traded)
    active_refs = sum(
        1 for u in users.values()
        if u.get("referred_by") == uid and u.get("total_trades", 0) > 0
    )
    ref_volume = sum(
        u.get("total_volume_usd", 0) for u in users.values()
        if u.get("referred_by") == uid
    )

    earnings_sol = user.get("referral_earnings", 0.0)
    prices = await get_crypto_prices()
    sol_price = prices.get("SOL", 0)
    earnings_usd = earnings_sol * sol_price

    text = (
        "\U0001f4ca *Referral Stats*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f465 Total referrals: *{ref_count}*\n"
        f"\U0001f7e2 Active traders: *{active_refs}*\n"
        f"\U0001f4b0 Their volume: *${ref_volume:,.2f}*\n"
        "\n"
        f"\U0001f4b5 *Your earnings:*\n"
        f"\u2022 SOL: *{earnings_sol:.6f}*"
    )
    if earnings_usd > 0.01:
        text += f" (${earnings_usd:,.2f})"
    text += (
        f"\n\u2022 Fee share: *{get_referral_pct(ref_count)}%* of 1% trade fee\n"
    )
    # Show tier progression
    if ref_count < 5:
        text += f"\U0001f4c8 _Get {5 - ref_count} more refs for 30% share!_\n"
    elif ref_count < 20:
        text += f"\U0001f4c8 _Get {20 - ref_count} more refs for 35% share!_\n"
    else:
        text += "\U0001f451 _MAX TIER — 35% share!_\n"
    text += (
        "\n"
        "\U0001f4a1 _Earnings are automatically sent_\n"
        "_to your bot wallet after each trade!_\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton("\U0001f519 Back to Referral", callback_data="referral")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# SETTINGS SECTION
# ══════════════════════════════════════════════

async def _cb_settings(query, user, context):
    """User settings panel."""
    tier = TIERS.get(user["tier"], TIERS["free"])
    alert_txt = "\U0001f7e2 ON" if user["alerts_on"] else "\U0001f534 OFF"

    ref_count = user.get("referral_count", 0)
    has_wallet = "\u2705" if user.get("wallet_pubkey") else "\u274c"
    trades = user.get("total_trades", 0)

    text = (
        "\u2699\ufe0f *Settings*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4cb Plan: *{tier['emoji']} {tier['name']}*\n"
        f"\U0001f514 Alerts: *{alert_txt}*\n"
        f"\u26d3 Chains: *{', '.join(tier['chains'])}*\n"
        f"\U0001f4bc Wallet: *{has_wallet}*\n"
        f"\U0001f4ca Trades: *{trades}*\n"
        f"\U0001f91d Referrals: *{ref_count}*\n"
        f"\U0001f4c5 Joined: {user.get('joined', 'N/A')[:10]}\n"
        f"\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    toggle_btn = (
        InlineKeyboardButton("\U0001f534 Turn Alerts OFF", callback_data="whale_off")
        if user["alerts_on"]
        else InlineKeyboardButton("\U0001f7e2 Turn Alerts ON", callback_data="whale_on")
    )

    kb = [
        [toggle_btn],
        [InlineKeyboardButton("\U0001f91d My Referral Link", callback_data="referral")],
        [InlineKeyboardButton("\U0001f48e Upgrade Plan", callback_data="premium")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# HELP SECTION
# ══════════════════════════════════════════════

async def _cb_help(query, user, context):
    """Help overview."""
    text = (
        "\U0001f4d6 *Help & FAQ*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "\U0001f40b *Whale Alerts* \u2014 Track large crypto\n"
        "   transfers in real-time\n"
        "\n"
        "\U0001f4c8 *Copy Trade* \u2014 Automatically copy\n"
        "   profitable traders (Pro+)\n"
        "\n"
        "\U0001f916 *DCA Bot* \u2014 Set up automated\n"
        "   buying strategies (Pro+)\n"
        "\n"
        "\U0001f4b1 *Exchanges* \u2014 Partner deals with\n"
        "   up to 70% fee rebates\n"
        "\n"
        "\U0001f48e *Premium* \u2014 Unlock all features\n"
        "   starting at $9.99/mo\n"
        "\n"
        "*Commands:*\n"
        "/start \u2014 Main menu\n"
        "/activate \u2014 Activate Gumroad license\n"
        "/myid \u2014 Show your Telegram ID\n"
        "/help \u2014 This help page\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton("\u2753 FAQ", callback_data="help_faq")],
        [
            InlineKeyboardButton("\U0001f310 Website", url=WEBSITE_URL),
            InlineKeyboardButton("\U0001f4ac Support", url=SUPPORT_URL),
        ],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_help_faq(query, user, context):
    """Frequently asked questions."""
    text = (
        "\u2753 *FAQ*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "*Q: What are whale alerts?*\n"
        "Notifications when large wallets move\n"
        "big amounts of crypto. Often signals\n"
        "upcoming price movements.\n"
        "\n"
        "*Q: How does copy trading work?*\n"
        "Connect your exchange and automatically\n"
        "mirror the trades of top-performing\n"
        "traders via MIZAR.\n"
        "\n"
        "*Q: What is DCA?*\n"
        "Dollar-Cost Averaging \u2014 buying a fixed\n"
        "amount on a regular schedule to reduce\n"
        "volatility risk.\n"
        "\n"
        "*Q: How do I earn fee rebates?*\n"
        "Sign up for exchanges through our links\n"
        "in \U0001f4b1 Exchanges. You get up to 70%\n"
        "of your trading fees back.\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )
    kb = [
        [InlineKeyboardButton("\U0001f4ac Contact Support", url=SUPPORT_URL)],
        [InlineKeyboardButton("\U0001f519 Back to Help", callback_data="help")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_help_copy(query, user, context):
    """How copy trading works."""
    text = (
        "\U0001f4c8 *How Copy Trading Works*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "1\ufe0f\u20e3 *Browse Traders*\n"
        "   View performance stats, win rates,\n"
        "   and risk profiles of top traders.\n"
        "\n"
        "2\ufe0f\u20e3 *Connect Exchange*\n"
        "   Link your exchange account via API.\n"
        "   Your funds stay on your exchange.\n"
        "\n"
        "3\ufe0f\u20e3 *Set Parameters*\n"
        "   Choose position size, max risk,\n"
        "   and stop-loss levels.\n"
        "\n"
        "4\ufe0f\u20e3 *Auto-Copy*\n"
        "   Every trade the leader makes is\n"
        "   replicated in your account.\n"
        "\n"
        "\U0001f6e1 *Your funds never leave your exchange.*"
    )
    kb = [
        [InlineKeyboardButton("\U0001f517 Open MIZAR", url=MIZAR_REFERRAL_URL)],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="copy_trade")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_help_dca(query, user, context):
    """How DCA works."""
    text = (
        "\U0001f916 *How DCA Bots Work*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "DCA (Dollar-Cost Averaging) reduces\n"
        "risk by spreading buys over time.\n"
        "\n"
        "*Example:* Instead of buying $1000 of\n"
        "BTC at once, buy $100 every week.\n"
        "\n"
        "\U0001f4c8 *Benefits:*\n"
        "\u2022 Lower average entry price\n"
        "\u2022 Removes emotional decisions\n"
        "\u2022 Works in any market condition\n"
        "\u2022 Set and forget automation\n"
        "\n"
        "*How to start:*\n"
        "1. Pick a token (BTC, ETH, SOL...)\n"
        "2. Set amount & frequency\n"
        "3. Connect your exchange\n"
        "4. Bot executes automatically"
    )
    kb = [
        [InlineKeyboardButton("\U0001f517 Open MIZAR", url=MIZAR_REFERRAL_URL)],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="dca_bot")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# ADMIN SECTION
async def _cb_admin_resume_signals(query, user, context):
    """CEO TIER 2: Erik resumes signals after auto-pause."""
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin only.", show_alert=True)
        return
    try:
        from core.persistence import _get_redis as _pr
        _r = _pr()
        if _r:
            _r.set("signals:paused", "0")
            _r.set("winrate:consecutive_losses", "0")
        await query.edit_message_text(
            "✅ *Signals hervat*\n\n"
            "CEO Agent heeft de pauze opgeheven.\n"
            "Signals worden weer verzonden.\n\n"
            "_Consecutive loss teller gereset._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Admin Stats", callback_data="admin_stats")],
            ]),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Fout: {e}", parse_mode="Markdown")


# ══════════════════════════════════════════════

async def _cb_admin_autotrade(query, user, context):
    """Admin control panel for autotrade runtime and profile tuning."""
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin only.", show_alert=True)
        return

    enabled = _autotrade_enabled_flag()
    gov = get_governance_config()
    cfg_move = float(gov.get("grade_a_min_pct", 2.5) or 2.5)
    cfg_vol = float(gov.get("min_volume_usd", 1500000) or 1500000)
    eff_move = min(cfg_move, 0.8)
    eff_vol = min(cfg_vol, 250000.0)

    test_cap = 0.0
    try:
        from core.persistence import _get_redis
        r = _get_redis()
        if r:
            test_cap = max(0.0, float(r.get("apexflash:autotrade:test_cap_sol") or 0.0))
    except Exception:
        test_cap = 0.0

    text = (
        "🛡️ *Autotrade Control Center*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Runtime: `{'ON' if enabled else 'OFF'}`\n"
        f"Test mode cap: `{test_cap:.4f} SOL` ({'ON' if test_cap > 0 else 'OFF'})\n"
        f"Profile cfg: move>={cfg_move:.2f}% | vol>={cfg_vol:,.0f}\n"
        f"Profile effective: move>={eff_move:.2f}% | vol>={eff_vol:,.0f}\n\n"
        f"Updated: `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`\n\n"
        "Use presets or set custom `min_move,min_volume`."
    )
    kb = [
        [
            InlineKeyboardButton("✅ Autotrade ON", callback_data="admin_at_on"),
            InlineKeyboardButton("⏹️ Autotrade OFF", callback_data="admin_at_off"),
        ],
        [
            InlineKeyboardButton("🧪 Test 0.03", callback_data="admin_at_test_003"),
            InlineKeyboardButton("🧪 Test 0.05", callback_data="admin_at_test_005"),
            InlineKeyboardButton("🧪 Test OFF", callback_data="admin_at_test_off"),
        ],
        [
            InlineKeyboardButton("🟢 Safe preset", callback_data="admin_at_preset_safe"),
            InlineKeyboardButton("🟡 Balanced", callback_data="admin_at_preset_bal"),
            InlineKeyboardButton("🔴 Active", callback_data="admin_at_preset_active"),
        ],
        [InlineKeyboardButton("✍️ Custom min/max", callback_data="admin_at_custom")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def _cb_admin_at_on(query, user, context):
    if not is_admin(query.from_user.id):
        return
    _set_autotrade_enabled_flag(True)
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Autotrade runtime set to ON")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_off(query, user, context):
    if not is_admin(query.from_user.id):
        return
    _set_autotrade_enabled_flag(False)
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="⏹️ Autotrade runtime set to OFF")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_test_003(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import _get_redis
    r = _get_redis()
    if r:
        r.set("apexflash:autotrade:test_cap_sol", "0.03")
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="🧪 Test mode cap set to 0.03 SOL")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_test_005(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import _get_redis
    r = _get_redis()
    if r:
        r.set("apexflash:autotrade:test_cap_sol", "0.05")
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="🧪 Test mode cap set to 0.05 SOL")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_test_off(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import _get_redis
    r = _get_redis()
    if r:
        r.delete("apexflash:autotrade:test_cap_sol")
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Test mode turned OFF")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_preset_safe(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import update_governance_config
    update_governance_config("grade_a_min_pct", 1.2)
    update_governance_config("min_volume_usd", 900000)
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="🟢 SAFE preset applied")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_preset_bal(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import update_governance_config
    update_governance_config("grade_a_min_pct", 0.8)
    update_governance_config("min_volume_usd", 250000)
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="🟡 BALANCED preset applied")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_preset_active(query, user, context):
    if not is_admin(query.from_user.id):
        return
    from core.persistence import update_governance_config
    update_governance_config("grade_a_min_pct", 0.5)
    update_governance_config("min_volume_usd", 100000)
    try:
        await context.bot.send_message(chat_id=query.message.chat_id, text="🔴 ACTIVE preset applied")
    except Exception:
        pass
    await _cb_admin_autotrade(query, user, context)


async def _cb_admin_at_custom(query, user, context):
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_input"] = "autotrade_custom_profile"
    await query.edit_message_text(
        "✍️ *Custom Autotrade Profile*\n\n"
        "Send in format:\n"
        "`min_move_pct,min_volume_usd`\n"
        "Example: `0.9,300000`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin_autotrade")],
        ]),
    )


# ══════════════════════════════════════════════

async def _cb_admin(query, user, context):
    """Admin dashboard."""
    if not is_admin(query.from_user.id):
        await query.edit_message_text("\u26d4 Unauthorized.")
        return

    total = len(users)
    active = sum(1 for u in users.values() if u.get("alerts_on"))
    pro = sum(1 for u in users.values() if u.get("tier") == "pro")
    elite = sum(1 for u in users.values() if u.get("tier") == "elite")
    uptime = datetime.now(timezone.utc) - bot_start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)

    text = (
        f"\U0001f451 *Admin Panel (v{VERSION})*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f465 Total users: *{total}*\n"
        f"\U0001f7e2 Active alerts: *{active}*\n"
        f"\U0001f680 Pro subs: *{pro}*\n"
        f"\U0001f451 Elite subs: *{elite}*\n"
        f"\u23f1 Uptime: *{hours}h {minutes}m*\n"
        f"\U0001f504 Scan interval: *{SCAN_INTERVAL}s*\n"
        f"\U0001f4e1 TX cache: *{len(seen_tx_hashes)}*\n"
        f"\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )
    from core.persistence import _get_redis
    r = _get_redis()
    is_paused = r.get("signals:paused") == "1" if r else False

    kb = [
        [InlineKeyboardButton("\U0001f4ca Revenue Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🛡️ Autotrade Controls", callback_data="admin_autotrade")],
        [InlineKeyboardButton("\U0001f465 User List", callback_data="admin_users")],
        [InlineKeyboardButton("\U0001f4e2 Broadcast Info", callback_data="admin_broadcast")],
        [InlineKeyboardButton("▶️ Resume Auto-Trading" if is_paused else "⏸️ Pause Auto-Trading", 
                              callback_data="admin_resume" if is_paused else "admin_pause")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_admin_resume_logic(query, user, context):
    """Resume signals via callback."""
    if not is_admin(query.from_user.id): return
    from core.persistence import _get_redis
    r = _get_redis()
    if r: r.set("signals:paused", "0")
    await query.answer("▶️ Auto-Trading RESUMED")
    await _cb_admin(query, user, context)

async def _cb_admin_pause_logic(query, user, context):
    """Pause signals via callback."""
    if not is_admin(query.from_user.id): return
    from core.persistence import _get_redis
    r = _get_redis()
    if r: r.set("signals:paused", "1")
    await query.answer("⏸️ Auto-Trading PAUSED")
    await _cb_admin(query, user, context)


async def _cb_admin_stats(query, user, context):
    """Revenue statistics."""
    if not is_admin(query.from_user.id):
        return

    pro_c = sum(1 for u in users.values() if u.get("tier") == "pro")
    elite_c = sum(1 for u in users.values() if u.get("tier") == "elite")
    mrr = pro_c * 19 + elite_c * 49
    total = len(users)
    active = sum(1 for u in users.values() if u.get("alerts_on"))
    conversion = ((pro_c + elite_c) / max(total, 1)) * 100
    active_rate = (active / max(total, 1)) * 100
    total_trades = sum(u.get("total_trades", 0) for u in users.values())
    total_vol = sum(u.get("total_volume_usd", 0) for u in users.values())
    wallets_created = sum(1 for u in users.values() if u.get("wallet_pubkey"))
    trade_fees_est = total_vol * PLATFORM_FEE_PCT / 100
    total_referrals = sum(1 for u in users.values() if u.get("referred_by"))
    total_ref_earnings = sum(u.get("referral_earnings", 0) for u in users.values())

    text = (
        f"\U0001f4ca *Revenue & Growth (v{VERSION})*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4b0 *Revenue*\n"
        f"\u2022 Trade fees ({PLATFORM_FEE_PCT}%): *~${trade_fees_est:,.2f}*\n"
        f"\u2022 MRR (subs): *${mrr}/mo*\n"
        f"\u2022 Pro: {pro_c} \u00d7 $9.99 = ${pro_c * 9.99:.2f}\n"
        f"\u2022 Elite: {elite_c} \u00d7 $29.99 = ${elite_c * 29.99:.2f}\n"
        f"\u2022 Affiliate: _check exchange dashboards_\n"
        f"\n"
        f"\U0001f4c8 *Trading*\n"
        f"\u2022 Total trades: *{total_trades}*\n"
        f"\u2022 Volume: *${total_vol:,.2f}*\n"
        f"\u2022 Wallets: *{wallets_created}*\n"
        f"\n"
        f"\U0001f91d *Referrals*\n"
        f"\u2022 Referred users: *{total_referrals}*\n"
        f"\u2022 Ref earnings paid: *{total_ref_earnings:.6f} SOL*\n"
        f"\n"
        f"\U0001f465 *Growth*\n"
        f"\u2022 Total signups: {total}\n"
        f"\u2022 Conversion: {conversion:.1f}%\n"
        f"\u2022 Active rate: {active_rate:.1f}%\n"
        f"\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )
    kb = [
        [InlineKeyboardButton("\U0001f519 Admin Panel", callback_data="admin")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def _cb_admin_users(query, user, context):
    """List recent users."""
    if not is_admin(query.from_user.id):
        return

    text = (
        f"\U0001f465 *User List (v{VERSION})*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    )

    sorted_users = sorted(
        users.items(), key=lambda x: x[1].get("joined", ""), reverse=True,
    )
    for uid, udata in sorted_users[:20]:
        t_emoji = TIERS.get(udata.get("tier", "free"), {}).get("emoji", "\U0001f193")
        alert = "\U0001f7e2" if udata.get("alerts_on") else "\U0001f534"
        name = f"@{udata['username']}" if udata.get("username") else str(uid)
        # Escape for Markdown
        name = name.replace("_", "\\_")
        text += f"{t_emoji} {alert} {name}\n"

    if len(users) > 20:
        text += f"\n_...and {len(users) - 20} more_\n"

    text += (
        "\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )
    kb = [
        [InlineKeyboardButton("\U0001f519 Admin Panel", callback_data="admin")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def _cb_admin_broadcast(query, user, context):
    """Broadcast instructions."""
    if not is_admin(query.from_user.id):
        return

    text = (
        f"\U0001f4e2 *Broadcast (v{VERSION})*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Send a message to ALL users:\n"
        "\n"
        "`/broadcast Your message here`\n"
        "\n"
        "This sends to every registered user.\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )
    kb = [
        [InlineKeyboardButton("\U0001f519 Admin Panel", callback_data="admin")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def _send_admin_panel(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send admin panel as new message."""
    total = len(users)
    active = sum(1 for u in users.values() if u.get("alerts_on"))
    text = (
        "\U0001f451 *Admin Panel*\n\n"
        f"Users: {total} | Active: {active}\n\n"
        "Use the buttons below:"
    )
    kb = [
        [InlineKeyboardButton("\U0001f4ca Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🛡️ Autotrade Controls", callback_data="admin_autotrade")],
        [InlineKeyboardButton("\U0001f465 Users", callback_data="admin_users")],
        [InlineKeyboardButton("\U0001f4e2 Broadcast", callback_data="admin_broadcast")],
        [_back_main()[0]],
    ]
    await context.bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
# WHALE ALERT FORMATTER
# ══════════════════════════════════════════════

def format_whale_alert(alert: dict, prices: dict, sentiment: dict | None = None) -> str:
    """Format whale alert — compact, scannable, direct action. GMGN-style."""
    sentiment = sentiment or {}
    chain = alert["chain"]
    value = alert["value"]
    symbol = alert["symbol"]
    direction = alert.get("direction", "IN")
    alert_type = alert.get("type", "TRANSFER")

    # Signal quality
    from sentiment import format_signal_quality
    sq = alert.get("_signal_quality") or {}
    grade = sq.get("grade", "B")
    action = sq.get("action", "WATCH")
    quality = sq.get("quality", 0)
    grade_emoji = {"S": "🔥", "A": "⚡", "B": "📊", "C": "👁"}.get(grade, "📊")

    # Affiliate (rotates)
    featured = [k for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
    aff_key = random.choice(featured) if featured else list(AFFILIATE_LINKS.keys())[0]
    aff = AFFILIATE_LINKS[aff_key]

    if alert_type == "SWAP":
        # ── SWAP: whale buying a token ──────────────────────────────────────
        amount = alert.get("amount", 0)
        amount_str = f"{amount:,.0f}" if amount >= 100 else f"{amount:,.2f}"
        wallet = alert.get("wallet_name", "Unknown Whale")
        price = prices.get(symbol, 0)
        usd_value = value * price if value > 0 else 0
        usd_str = f"~${usd_value:,.0f}" if usd_value > 1000 else ""
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"

        text = (
            f"{grade_emoji} *WHALE SWAP* | {chain} | Grade {grade}\n\n"
            f"💰 *{amount_str} {symbol}* {usd_str}\n"
            f"🐋 {wallet}\n"
            f"🎯 {action}\n\n"
            f"[🔍 Solscan]({explorer}) | [📈 Chart](https://dexscreener.com/solana/{alert.get('token_address','')}) | "
            f"[⚡ {aff['name']}]({aff['url']})\n"
            f"💎 /premium — SOL + instant alerts"
        )
        return text

    # ── TRANSFER ─────────────────────────────────────────────────────────────
    dir_emoji = "🔴" if direction == "OUT" else "🟢"
    value_str = f"{value:,.0f}" if value >= 100 else f"{value:,.2f}"
    price = prices.get(symbol, 0)
    usd_value = value * price
    usd_str = f"~${usd_value:,.0f}" if usd_value > 1000 else ""

    if chain == "ETH":
        explorer = f"https://etherscan.io/tx/{alert['tx_hash']}"
        chart_link = f"https://www.coingecko.com/en/coins/ethereum"
    elif chain == "SOL":
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
        chart_link = f"https://dexscreener.com/solana"
    else:
        explorer = ""
        chart_link = ""

    from_lbl = alert['from_label']
    to_lbl = alert['to_label']

    # Sentiment one-liner
    sentiment_line = format_sentiment_line(sentiment)
    si = f"\n🧠 {sentiment_line}" if sentiment_line else ""

    tx_link = f"[🔍 TX]({explorer}) | " if explorer else ""
    chart = f"[📈 Chart]({chart_link}) | " if chart_link else ""

    text = (
        f"{dir_emoji}{grade_emoji} *WHALE ALERT* | {chain} | Grade {grade}\n\n"
        f"💰 *{value_str} {symbol}* {usd_str}\n"
        f"📤 `{from_lbl}` → `{to_lbl}`\n"
        f"🎯 {action} ({quality}/100){si}\n\n"
        f"{tx_link}{chart}[⚡ {aff['name']} {aff['commission']}]({aff['url']})\n"
        f"💎 /premium — more chains + instant alerts"
    )
    return text


# ══════════════════════════════════════════════
# WHALE SCANNER (Job Queue)
# ══════════════════════════════════════════════

async def scan_and_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic whale scanner: fetch transfers and broadcast to subscribers."""
    global seen_tx_hashes

    try:
        prices = await get_crypto_prices()
        eth_alerts = await fetch_eth_whale_transfers()
        sol_alerts = await fetch_sol_whale_transfers()

        # NEW: Detect what tokens whales are BUYING (the real signal)
        try:
            from exchanges.chains import fetch_sol_whale_token_swaps
            swap_alerts = await fetch_sol_whale_token_swaps()
        except Exception as swap_err:
            logger.debug(f"Swap tracker: {swap_err}")
            swap_alerts = []

        all_alerts = eth_alerts + sol_alerts + swap_alerts

        new_alerts = [a for a in all_alerts if a["tx_hash"] not in seen_tx_hashes]

        if not new_alerts:
            return

        # Mark as seen
        for a in new_alerts:
            seen_tx_hashes.add(a["tx_hash"])

        # Cap memory
        if len(seen_tx_hashes) > 10000:
            seen_tx_hashes = set(list(seen_tx_hashes)[-5000:])

        # AI Sentiment + Signal Quality scoring per alert
        for alert in new_alerts:
            try:
                sentiment = await get_whale_alert_sentiment(alert)
                alert["_sentiment"] = sentiment
            except Exception:
                alert["_sentiment"] = None

            # Score signal quality (filters bad trades)
            from sentiment import score_whale_signal, format_signal_quality
            sq = score_whale_signal(alert, alert.get("_sentiment"))
            alert["_signal_quality"] = sq
            if not sq["pass"]:
                logger.info(
                    f"Signal filtered: {alert.get('symbol')} grade={sq['grade']} "
                    f"score={sq['quality']} — below threshold, not sending"
                )

        # Remove low-quality signals (grade D = likely bad trade)
        new_alerts = [a for a in new_alerts if a.get("_signal_quality", {}).get("pass", True)]

        if not new_alerts:
            return

        # ── CEO TIER 2: Check signals:paused before broadcasting ──
        try:
            from core.persistence import _get_redis as _pr
            _r = _pr()
            if _r and _r.get("signals:paused") == b"1":
                logger.warning("CEO TIER 2: signals PAUSED — skipping broadcast this cycle")
                return
        except Exception:
            pass  # Redis unavailable → proceed (fail open)

        # Broadcast to subscribers
        for user_id, user_data in list(users.items()):
            if not user_data.get("alerts_on"):
                continue

            tier_config = TIERS.get(user_data.get("tier", "free"), TIERS["free"])
            user_chains = tier_config["chains"]

            for alert in new_alerts:
                if alert["chain"] not in user_chains:
                    continue

                try:
                    # AI sentiment analysis (non-blocking — if HF fails, alert still sends)
                    sentiment = alert.get("_sentiment")
                    text = format_whale_alert(alert, prices, sentiment=sentiment)

                    # Add trade + affiliate buttons
                    alert_kb = []

                    # Direct "Buy this token" button
                    token_symbol = alert.get("symbol", "")
                    # Swap alerts already have mint address (most actionable!)
                    token_mint = alert.get("mint", "")
                    if not token_mint:
                        for sym, info in COMMON_TOKENS.items():
                            if sym == token_symbol:
                                token_mint = info["mint"]
                                break
                    if token_mint and token_mint != SOL_MINT:
                        alert_kb.append([
                            InlineKeyboardButton(
                                f"\U0001f4b5 Buy {token_symbol}", callback_data=f"search_{token_mint[:40]}",
                            )
                        ])

                    # PREMIUM: Whale Intent AI (Elite Only)
                    if can_user_analyze(user_data.get("tier", "free")):
                        tx_hash = alert.get("tx_hash", "")
                        alert_kb.append([
                            InlineKeyboardButton(
                                "🤖 Analyze Intent (AI)", 
                                callback_data=f"whale_intent_{tx_hash[:20]}_{token_symbol}"
                            )
                        ])

                    featured = [
                        (k, v) for k, v in AFFILIATE_LINKS.items()
                        if v.get("featured")
                    ]
                    if featured:
                        _, aff = random.choice(featured)
                        alert_kb.append([
                            InlineKeyboardButton(
                                f"\U0001f525 {aff['name']} \u2014 {aff['commission']}",
                                url=aff["url"],
                            )
                        ])
                    alert_kb.append([
                        InlineKeyboardButton(
                            "\U0001f4b0 Trade Menu", callback_data="trade",
                        )
                    ])

                    await context.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(alert_kb),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.error(f"Alert send failed [{user_id}]: {e}")

        # ── Cross-platform distribution (Discord + Telegram Channel) ──
        for alert in new_alerts:
            try:
                # Discord webhook
                await notify_discord_whale(alert, prices)
            except Exception as e:
                logger.debug(f"Discord notify error: {e}")

            try:
                # Telegram public channel — with tradeable deep links + AI sentiment
                channel_text = format_whale_alert(alert, prices, sentiment=alert.get("_sentiment"))
                token_symbol = alert.get("symbol", "")
                token_mint = ""
                for sym, info in COMMON_TOKENS.items():
                    if sym == token_symbol:
                        token_mint = info["mint"]
                        break

                ch_buttons = []
                if token_mint and token_mint != SOL_MINT:
                    # Deep link: opens bot with this token ready to buy
                    ch_buttons.append([InlineKeyboardButton(
                        f"💰 Buy {token_symbol} Now",
                        url=f"https://t.me/{BOT_USERNAME}?start=buy_{token_mint}",
                    )])
                ch_buttons.append([InlineKeyboardButton(
                    "🔥 Trending Tokens", url=f"https://t.me/{BOT_USERNAME}?start=hot",
                )])
                ch_buttons.append([InlineKeyboardButton(
                    "⚡ Start Trading", url=f"https://t.me/{BOT_USERNAME}?start=hot",
                )])

                channel_kb = InlineKeyboardMarkup(ch_buttons)
                await notify_telegram_channel(
                    context.bot, alert, channel_text, channel_kb,
                )
            except Exception as e:
                logger.debug(f"Telegram channel notify error: {e}")

        logger.info(f"Scanner: {len(new_alerts)} new alerts distributed")

    except Exception as e:
        logger.error(f"Scanner error: {e}")


# ══════════════════════════════════════════════
# DAILY DIGEST JOB
# ══════════════════════════════════════════════

async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post daily digest summary to Discord + TG channel. Runs once/day at 20:00 UTC."""
    try:
        _reset_daily_stats()

        stats = {
            "trades_today": platform_stats["trades_today"],
            "volume_today_usd": platform_stats["volume_today_usd"],
            "active_traders": len(platform_stats["active_traders_today"]),
            "total_users": len(users),
            "trades_total": platform_stats["trades_total"],
            "volume_total_usd": platform_stats["volume_total_usd"],
        }

        # Skip if no activity today (don't spam empty digests)
        if stats["trades_today"] == 0 and stats["active_traders"] == 0:
            logger.info("Daily digest: no activity, skipping")
            return

        # Discord
        try:
            await notify_discord_digest(stats)
        except Exception as e:
            logger.debug(f"Digest Discord error: {e}")

        # Telegram channel
        try:
            await notify_channel_digest(context.bot, stats)
        except Exception as e:
            logger.debug(f"Digest TG channel error: {e}")

        logger.info(f"Daily digest posted: {stats['trades_today']} trades, ${stats['volume_today_usd']:,.0f} volume")

    except Exception as e:
        logger.error(f"Daily digest error: {e}")


# ══════════════════════════════════════════════
# AUTO-SAVE & BACKUP JOBS
# ══════════════════════════════════════════════

async def auto_save_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic auto-save every 60 seconds — safety net."""
    try:
        _persist()
    except Exception as e:
        logger.error(f"Auto-save error: {e}")


async def _send_backup_to_admin(bot, caption: str = "") -> None:
    """Send backup file to all admins. Used by auto-backup and critical events."""
    if not ADMIN_IDS or not users:
        return
    try:
        import io
        backup_json = export_backup(users, platform_stats)
        bio = io.BytesIO(backup_json.encode())
        bio.name = f"apexflash_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
        default_caption = f"\U0001f4be Backup | {len(users)} users | {platform_stats.get('trades_total', 0)} trades"
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_document(
                    chat_id=admin_id,
                    document=bio,
                    caption=caption or default_caption,
                )
                bio.seek(0)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Backup send error: {e}")


async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send backup to admin via Telegram every 2 hours. Deploy resilience."""
    await _send_backup_to_admin(context.bot, f"\U0001f4be Auto-backup (2h) | {len(users)} users | {platform_stats.get('trades_total', 0)} trades")
    logger.info(f"Auto-backup sent to {len(ADMIN_IDS)} admin(s)")


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hourly heartbeat — admin knows the bot is alive 24/7."""
    if not ADMIN_IDS:
        return
    try:
        uptime = datetime.now(timezone.utc) - bot_start_time
        hours = int(uptime.total_seconds() // 3600)
        mins = int((uptime.total_seconds() % 3600) // 60)
        wallets = sum(1 for u in users.values() if u.get("wallet_pubkey"))
        # Env var health check in heartbeat
        import os as _hb_os
        _crit = {"HELIUS": _hb_os.getenv("HELIUS_API_KEY",""), "ETHERSCAN": _hb_os.getenv("ETHERSCAN_API_KEY",""),
                 "REDIS": _hb_os.getenv("UPSTASH_REDIS_URL",""), "FEE_WALLET": _hb_os.getenv("FEE_COLLECT_WALLET",""),
                 "JUPITER": _hb_os.getenv("JUPITER_API_KEY",""), "ALERT_CH": _hb_os.getenv("ALERT_CHANNEL_ID","")}
        _miss = [k for k,v in _crit.items() if not v]
        _env_status = "\U0001f534 MISSING: " + ",".join(_miss) if _miss else "\U0001f7e2 All env OK"

        msg = (
            f"\U0001f49a *Heartbeat OK*\n"
            f"Uptime: {hours}h {mins}m\n"
            f"Users: {len(users)} | Wallets: {wallets}\n"
            f"Trades today: {platform_stats.get('trades_today', 0)} | "
            f"Total: {platform_stats.get('trades_total', 0)}\n"
            f"{_env_status}\n"
            f"v{VERSION}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id, text=msg, parse_mode="Markdown",
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")


async def marketing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post marketing content to Telegram + Twitter 3x daily (08:00, 14:00, 20:00 UTC)."""
    # Telegram channel post
    try:
        if ALERT_CHANNEL_ID:
            success = await marketing_post(context.bot, ALERT_CHANNEL_ID)
            if success:
                platform_stats["marketing_posts"] = platform_stats.get("marketing_posts", 0) + 1
                logger.info(f"Marketing post #{platform_stats['marketing_posts']} sent (Telegram)")
    except Exception as e:
        logger.error(f"Marketing job (Telegram) error: {e}")

    # Twitter/X post
    try:
        if TWITTER_ENABLED and TWITTER_API_KEY:
            tw_ok = await twitter_post(
                TWITTER_API_KEY, TWITTER_API_SECRET,
                TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
            )
            if tw_ok:
                platform_stats["twitter_posts"] = platform_stats.get("twitter_posts", 0) + 1
                logger.info(f"Twitter post #{platform_stats['twitter_posts']} sent")
    except Exception as e:
        logger.error(f"Marketing job (Twitter) error: {e}")


# ══════════════════════════════════════════════
# LIVE SCALPING MONITOR (Job Queue — every 30s)
# ══════════════════════════════════════════════

async def scalper_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Live scalping signal detector — fires every 30 seconds.
    Monitors SOL/BONK/JUP/WIF/RAY/PYTH for rapid momentum moves.
    Alerts Grade A/B to channel; Grade C logged only.
    """
    try:
        from scalper import check_scalp_signals, format_scalp_alert
        signals = await check_scalp_signals()

        for sig in signals:
            grade = sig["grade"]
            msg = format_scalp_alert(sig)
            is_high_conviction = (grade == "A")

            # 1. Public Channel Alert — ONLY Grade A (Protect Social Proof)
            if is_high_conviction and ALERT_CHANNEL_ID:
                try:
                    await context.bot.send_message(
                        chat_id=ALERT_CHANNEL_ID,
                        text=f"⭐ <b>HIGH CONVICION SIGNAL</b>\n{msg}",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as ch_err:
                    logger.warning(f"Scalper channel send error: {ch_err}")

            # 2. Individual User Alerts (Tiered Broadcast)
            for uid, udata in list(users.items()):
                if not udata.get("alerts_enabled", True):
                    continue
                
                user_tier = udata.get("tier", "free").lower()
                is_premium = user_tier in ("pro", "elite")
                
                # --- BROADCAST LOGIC ---
                # Grade A: Everyone (Social Proof)
                # Grade B/C: Pro/Elite only (Premium Value)
                should_alert = False
                alert_text = msg
                
                if grade == "A":
                    should_alert = True
                    alert_text = f"⭐ <b>GOLD SIGNAL (Grade A)</b>\n{msg}"
                elif grade in ("B", "C") and is_premium:
                    should_alert = True
                    alert_text = f"⚠️ <b>PRO ALERT (Grade {grade} - High Risk)</b>\n{msg}"
                
                if not should_alert:
                    continue

                try:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            f"⚡ Trade {sig['symbol']}",
                            callback_data=f"search_{sig['symbol']}:{grade}",
                        )
                    ]])
                    await context.bot.send_message(
                        chat_id=uid,
                        text=alert_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=kb,
                    )
                except Exception:
                    pass

            # Logging
            if is_high_conviction:
                logger.info(f"GOLD signal broadcast: {sig['symbol']} {sig['pct_5m']:+.2f}%")
            else:
                logger.info(f"Scalp watch (Grade {grade}): {sig['symbol']} — sent to Pro users only")

    except Exception as e:
        logger.error(f"Scalper job error: {e}")


# ══════════════════════════════════════════════
# ADMIN: /backup & /restore COMMANDS
# ══════════════════════════════════════════════

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: send manual backup file."""
    if not is_admin(update.effective_user.id):
        return
    import io
    backup_json = export_backup(users, platform_stats)
    bio = io.BytesIO(backup_json.encode())
    bio.name = f"apexflash_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    await update.message.reply_document(
        document=bio,
        caption=f"\U0001f4be Manual backup | {len(users)} users | {platform_stats.get('trades_total', 0)} trades",
    )


async def cmd_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🔥 Show trending Solana tokens by volume — DexScreener + DexPaprika."""
    await update.effective_message.reply_text("🔥 *Loading trending tokens...*", parse_mode="Markdown")

    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as session:
            # Try DexScreener first (boosted tokens = paid promotions = high interest)
            dexscreener_tokens = []
            _ds_seen_mints: set = set()  # dedup boosted list itself
            try:
                async with session.get(
                    "https://api.dexscreener.com/token-boosts/top/v1",
                    timeout=_aiohttp.ClientTimeout(total=5),
                ) as ds_resp:
                    if ds_resp.status == 200:
                        ds_data = await ds_resp.json()
                        for item in (ds_data if isinstance(ds_data, list) else []):
                            tok_addr = item.get("tokenAddress", "")
                            if item.get("chainId") == "solana" and tok_addr:
                                if tok_addr in _ds_seen_mints:
                                    continue  # skip duplicate boosted entries
                                _ds_seen_mints.add(tok_addr)
                                dexscreener_tokens.append({
                                    "mint": tok_addr,
                                    "symbol": item.get("description", item.get("url", ""))[:10] or "???",
                                    "source": "dexscreener",
                                    "link": item.get("url", ""),
                                })
                            if len(dexscreener_tokens) >= 3:
                                break
            except Exception:
                pass  # DexScreener is bonus, not critical

            # DexPaprika: top pools by volume on Solana
            async with session.get(
                "https://api.dexpaprika.com/networks/solana/pools",
                params={"order_by": "volume_usd", "sort": "desc", "limit": "100"},
                timeout=_aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    await update.effective_message.reply_text("⚠️ Could not fetch trending data. Try again later.")
                    return
                data = await resp.json()

        # Parse: extract unique tokens (skip SOL/USDC/USDT base pairs)
        pools = data.get("pools", data) if isinstance(data, dict) else data
        if not isinstance(pools, list) or not pools:
            await update.effective_message.reply_text("⚠️ No trending data available.")
            return

        # Skip stablecoins and base pairs
        SKIP_MINTS = {
            "So11111111111111111111111111111111111111112",   # SOL
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", # USDT
            "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
            "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj", # stSOL
        }

        # Deduplicate: one entry per unique token (highest volume pool wins)
        # Dedup on BOTH mint AND symbol — prevents same token from multiple pools
        seen_mints: set = set()
        seen_syms: set = set()
        trending = []
        for pool in pools:
            tokens = pool.get("tokens", [])
            # Find the non-base token in this pool
            target_tok = None
            for tok in tokens:
                mint = tok.get("id", "") or tok.get("address", "")
                if mint not in SKIP_MINTS and mint:
                    target_tok = tok
                    break
            if not target_tok:
                continue

            mint = target_tok.get("id", "") or target_tok.get("address", "")
            symbol = (target_tok.get("symbol", "") or "???").strip()
            # Skip if we already have this token (by mint OR symbol)
            if (mint and mint in seen_mints) or (symbol != "???" and symbol in seen_syms):
                continue
            if mint:
                seen_mints.add(mint)
            if symbol != "???":
                seen_syms.add(symbol)

            pct_24h = pool.get("last_price_change_usd_24h", 0) or 0
            volume = pool.get("volume_usd", 0) or 0
            price = pool.get("price_usd", 0) or 0
            trending.append({
                "symbol": symbol,
                "name": target_tok.get("name", "Unknown"),
                "mint": mint,
                "pct_24h": pct_24h,
                "volume": volume,
                "price": price,
            })
            if len(trending) >= 10:
                break

        if not trending:
            await update.effective_message.reply_text("⚠️ No trending tokens found.")
            return

        # Build message
        msg = "\U0001f525 *HOT TOKENS \u2014 Solana*\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        kb_rows = []

        # DexScreener boosted tokens first (if any)
        if dexscreener_tokens:
            msg += "\U0001f680 *BOOSTED (DexScreener):*\n"
            for ds in dexscreener_tokens:
                short_mint = f"{ds['mint'][:6]}...{ds['mint'][-4:]}"
                msg += f"\u26a1 `{short_mint}`\n"
                kb_rows.append([InlineKeyboardButton(
                    f"\U0001f680 Buy Boosted {short_mint}",
                    callback_data=f"hot_buy_{ds['mint']}",
                )])
            msg += "\n"

        # DexPaprika volume leaders
        msg += "\U0001f4ca *TOP BY VOLUME:*\n"
        for i, t in enumerate(trending, 1):
            arrow = "\U0001f4c8" if t["pct_24h"] >= 0 else "\U0001f4c9"
            pct = f"+{t['pct_24h']:.1f}%" if t["pct_24h"] >= 0 else f"{t['pct_24h']:.1f}%"
            vol_str = f"${t['volume']:,.0f}" if t["volume"] >= 1 else "$0"
            msg += f"{i}. {arrow} *{t['symbol']}* \u2014 {pct} | Vol: {vol_str}\n"
            kb_rows.append([InlineKeyboardButton(
                f"\U0001f4b0 Buy {t['symbol']}",
                callback_data=f"hot_buy_{t['mint']}",
            )])

        msg += (
            "\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f446 Tap to buy | Paste any mint to trade\n"
            "\u26a1 Powered by ApexFlash + DexScreener"
        )

        kb_rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="cmd_hot_refresh")])
        kb_rows.append([_back_main()[0]])

        await update.effective_message.reply_text(
            msg,
            reply_markup=InlineKeyboardMarkup(kb_rows),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"cmd_hot error: {e}")
        await update.effective_message.reply_text("⚠️ Error loading trending tokens. Try again.")


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show portfolio — wrapper for /portfolio command."""
    uid = update.effective_user.id
    user = get_user(uid)
    # Fake a query-like object to reuse _cb_portfolio
    class FakeQuery:
        from_user = update.effective_user
        message = update.effective_message
        async def edit_message_text(self, *a, **kw):
            await update.effective_message.reply_text(*a, **kw)
    await _cb_portfolio(FakeQuery(), user, context)


async def cmd_policy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show no-risk policy."""
    text = (
        "\U0001f6e1\ufe0f *ApexFlash — No Risk Policy*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "*5-Point Protection:*\n\n"
        "1\ufe0f\u20e3 *You Control Everything*\n"
        "Your wallet, your keys. We never hold your funds.\n\n"
        "2\ufe0f\u20e3 *Built-In Safety Net*\n"
        "Stop Loss default ON. Max trade 10 SOL.\n\n"
        "3\ufe0f\u20e3 *Transparent Fees*\n"
        "1% per trade. No hidden charges. Ever.\n\n"
        "4\ufe0f\u20e3 *Rug Pull Protection*\n"
        "AI token scanning. Liquidity monitoring.\n\n"
        "5\ufe0f\u20e3 *No Pressure*\n"
        "No fake urgency. Real data, real trades.\n\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f *Disclaimer:* Trading crypto involves risk. "
        "Only trade with funds you can afford to lose. "
        "ApexFlash provides tools, not financial advice.\n\n"
        "\U0001f4e7 support@apexflash.pro"
    )
    await update.effective_message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f310 Website", url="https://www.apexflash.pro")],
            [InlineKeyboardButton("\U0001f4ac Support", url="https://t.me/ApexFlashSupport")],
            [_back_main()[0]],
        ]),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 Live market overview — gainers, losers, new tokens."""
    await update.effective_message.reply_text("📊 *Loading market data...*", parse_mode="Markdown")
    update_last_active(update.effective_user.id)

    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.dexpaprika.com/networks/solana/pools",
                params={"order_by": "volume_usd", "sort": "desc", "limit": "200"},
                timeout=_aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    await update.effective_message.reply_text("⚠️ Market data unavailable.")
                    return
                data = await resp.json()

        SKIP_MINTS = {
            "So11111111111111111111111111111111111111112",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
            "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
        }

        pools = data.get("pools", data) if isinstance(data, dict) else data
        if not isinstance(pools, list):
            await update.effective_message.reply_text("⚠️ No market data.")
            return

        seen = set()
        all_tokens = []
        for pool in pools:
            tokens = pool.get("tokens", [])
            target = None
            for tok in tokens:
                if tok.get("id", "") not in SKIP_MINTS:
                    target = tok
                    break
            if not target:
                continue
            mint = target.get("id", "")
            if mint in seen:
                continue
            seen.add(mint)
            pct = pool.get("last_price_change_usd_24h", 0) or 0
            vol = pool.get("volume_usd", 0) or 0
            all_tokens.append({
                "symbol": target.get("symbol", "???"),
                "mint": mint,
                "pct": pct,
                "volume": vol,
            })

        # Sort for categories
        gainers = sorted([t for t in all_tokens if t["pct"] > 0], key=lambda x: -x["pct"])[:5]
        losers = sorted([t for t in all_tokens if t["pct"] < 0], key=lambda x: x["pct"])[:5]
        by_volume = sorted(all_tokens, key=lambda x: -x["volume"])[:5]

        msg = "📊 *SOLANA MARKET*\n━━━━━━━━━━━━━━━━━━━━━\n\n"

        msg += "🟢 *TOP GAINERS (24h)*\n"
        for i, t in enumerate(gainers, 1):
            msg += f"  {i}. *{t['symbol']}* +{t['pct']:.1f}%\n"

        msg += "\n🔴 *TOP LOSERS (24h)*\n"
        for i, t in enumerate(losers, 1):
            msg += f"  {i}. *{t['symbol']}* {t['pct']:.1f}%\n"

        msg += "\n💎 *HIGHEST VOLUME*\n"
        for i, t in enumerate(by_volume, 1):
            vol_str = f"${t['volume']:,.0f}" if t['volume'] >= 1 else "$0"
            msg += f"  {i}. *{t['symbol']}* — {vol_str}\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n⚡ Tap to buy instantly"

        kb = []
        # Top 3 gainers as buy buttons
        for t in gainers[:3]:
            kb.append([InlineKeyboardButton(
                f"🟢 Buy {t['symbol']} (+{t['pct']:.0f}%)",
                callback_data=f"hot_buy_{t['mint']}",
            )])
        kb.append([InlineKeyboardButton("🔥 Hot Tokens", callback_data="cmd_hot_refresh")])
        kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="cmd_market_refresh")])
        kb.append([_back_main()[0]])

        await update.effective_message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"cmd_market error: {e}")
        await update.effective_message.reply_text("⚠️ Error loading market data.")


async def cmd_admin_marketing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: get the current viral hooks for social media."""
    if not is_admin(update.effective_user.id):
        return
        
    hooks = get_marketing_playbook()
    text = "🚀 **SOCIAL DOMINANCE PLAYBOOK (v3.18.0)**\n"
    text += "Use these high-conversion hooks for TikTok/Reels:\n\n"
    for hook in hooks:
        text += f"• `{hook}`\n\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show funnel, popular tokens, affiliate stats, and referral revenue."""
    if not is_admin(update.effective_user.id):
        return

    from core.persistence import get_funnel_stats, get_popular_tokens, get_affiliate_stats, _get_redis
    
    funnel = get_funnel_stats()
    popular = get_popular_tokens("alltime", 5)
    affiliates = get_affiliate_stats()

    advisor_paywall_views = int(funnel.get("advisor_paywall_view", 0) or 0)
    advisor_used = int(funnel.get("advisor_used", 0) or 0)
    advisor_upgrade_clicks = int(funnel.get("advisor_upgrade_click", 0) or 0)
    advisor_pricing_clicks = int(funnel.get("advisor_pricing_click", 0) or 0)
    advisor_upgrade_ctr = (advisor_upgrade_clicks / advisor_paywall_views * 100.0) if advisor_paywall_views else 0.0
    advisor_pricing_ctr = (advisor_pricing_clicks / advisor_paywall_views * 100.0) if advisor_paywall_views else 0.0
    advisor_total_intent = advisor_upgrade_clicks + advisor_pricing_clicks
    advisor_total_intent_ctr = (advisor_total_intent / advisor_paywall_views * 100.0) if advisor_paywall_views else 0.0
    
    r = _get_redis()
    referral_payouts_sol = float(r.get("kpi:total_referral_payouts_sol") or 0) if r else 0
    
    # REVENUE MISSION TRACKER (€1M Goal)
    total_vol = platform_stats.get("volume_total_usd", 0)
    # Estimated gross revenue from 1% platform fee
    gross_revenue_usd = total_vol * 0.01
    
    # Calculate net (payouts subtracted)
    sol_price = 150.0  # Placeholder, in prod use get_crypto_prices
    payouts_usd = referral_payouts_sol * sol_price
    net_revenue_usd = gross_revenue_usd - payouts_usd
    
    goal_usd = 1000000.0
    progress_pct = (net_revenue_usd / goal_usd * 100) if goal_usd > 0 else 0
    
    # WHALE SEGMENTATION (v3.19.0)
    whale_vol_usd = float(r.get("kpi:whale_volume_usd") or 0) if r else 0
    alpha_clan_hits = int(r.get("kpi:alpha_clan_signals") or 0) if r else 0
    retail_vol_usd = total_vol - whale_vol_usd
    
    whale_share = (whale_vol_usd / total_vol * 100) if total_vol > 0 else 0
    
    revenue_text = (
        "\U0001f3af *MISSION: €1,000,000 NET REVENUE*\n"
        f"\u25b6 Gross Revenue: *${gross_revenue_usd:,.2f}*\n"
        f"\u25b6 Referral Payouts: *-${payouts_usd:,.2f}* ({referral_payouts_sol:.2f} SOL)\n"
        f"\u25b6 *NET REVENUE:* *${max(0, net_revenue_usd):,.2f}*\n"
        f"————————————————————————\n"
        f"\U0001f40b *WHALE SEGMENTATION:*\n"
        f"• Institutional/Whale: *${whale_vol_usd:,.0f}* ({whale_share:.1f}%)\n"
        f"• Retail/Organic: *${retail_vol_usd:,.0f}*\n"
        f"• Alpha Clan Signals: *{alpha_clan_hits}* triggers\n"
        f"————————————————————————\n"
        f"\u25b6 Progress to €1M: *{progress_pct:.2f}%*\n"
        f"————————————————————————\n"
    )

    # Simplified formatting for long outputs
    funnel_labels = [
        ("start", "Start"),
        ("wallet_created", "Wallet created"),
        ("funded", "Funded"),
        ("first_trade", "First trade"),
        ("upgrade", "Upgrade"),
        ("conversion_report_sent", "Conversion report sent"),
        ("advisor_used", "Advisor used (Elite/Admin)"),
        ("advisor_paywall_view", "Advisor paywall view"),
        ("advisor_upgrade_click", "Advisor upgrade click"),
        ("advisor_pricing_click", "Advisor pricing click"),
    ]
    funnel_text = "\U0001f4ca *Funnel Stats:*\n" + "\n".join(
        [f"• {label}: {int(funnel.get(key, 0) or 0)}" for key, label in funnel_labels]
    )
    advisor_conversion_text = (
        "\n\n🤖 *Advisor Paywall Conversion:*\n"
        f"• Advisor used: *{advisor_used}*\n"
        f"• Views: *{advisor_paywall_views}*\n"
        f"• Upgrade clicks: *{advisor_upgrade_clicks}* ({advisor_upgrade_ctr:.2f}%)\n"
        f"• Pricing clicks: *{advisor_pricing_clicks}* ({advisor_pricing_ctr:.2f}%)\n"
        f"• Total intent CTR: *{advisor_total_intent_ctr:.2f}%*"
    )
    popular_text = "\n\n🔥 *Popular Tokens:*\n" + "\n".join([f"• {t['symbol']}" for t in popular])
    
    await update.message.reply_text(
        f"{revenue_text}\n{funnel_text}{advisor_conversion_text}{popular_text}",
        parse_mode="Markdown",
    )


async def cmd_advisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show personalized AI trade analysis for Elite users."""
    from agents.advisor_agent import analyze_trader_performance, get_advisor_intro

    async def _safe_send(text: str, *, parse_mode: str | None = "Markdown", reply_markup=None):
        if update.message:
            return await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    uid = update.effective_user.id
    user = get_user(uid)
    advisor_lock_key = f"apexflash:advisor:lock:{uid}"
    redis_lock_acquired = False

    # Cross-instance lock (prevents duplicate advisor runs during rolling deploy overlap).
    try:
        from core.persistence import _get_redis
        _r = _get_redis()
        if _r:
            redis_lock_acquired = bool(_r.set(advisor_lock_key, "1", ex=25, nx=True))
            if not redis_lock_acquired:
                await _safe_send("⏳ *AI Advisor is already processing your previous request...*")
                return
    except Exception:
        redis_lock_acquired = False

    # Local debounce for rapid repeated taps in same client session.
    advisor_busy = bool(context.user_data.get("advisor_busy"))
    last_advisor_ts = float(context.user_data.get("advisor_last_ts", 0.0) or 0.0)
    now_ts = datetime.now(timezone.utc).timestamp()
    if advisor_busy or (now_ts - last_advisor_ts) < 8.0:
        await _safe_send("⏳ *AI Advisor is already processing your previous request...*")
        return

    context.user_data["advisor_busy"] = True
    context.user_data["advisor_last_ts"] = now_ts
    try:
        if user.get("tier", "free") not in ("elite", "admin"):
            bucket = get_user_bucket(uid)
            track_funnel("advisor_paywall_view")
            track_bucket_kpi(bucket, "advisor_paywall_view")

            if bucket == 0:
                paywall_text = (
                    "💎 *ApexFlash AI Advisor (Elite)*\n\n"
                    "This professional feature is reserved for **Elite** members.\n"
                    "Upgrade now to unlock personalized Gemini trade coaching."
                )
                upgrade_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Upgrade to Elite", callback_data="advisor_upgrade_elite")],
                    [InlineKeyboardButton("📈 View Pricing", callback_data="advisor_view_pricing")],
                ])
            else:
                paywall_text = (
                    "🚀 *AI Coach Pro Access (Elite)*\n\n"
                    "You reached the highest-intent advisor path.\n"
                    "Activate Elite to access full AI coaching and faster execution guidance."
                )
                upgrade_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📈 View Pricing", callback_data="advisor_view_pricing")],
                    [InlineKeyboardButton("💎 Activate Elite", callback_data="advisor_upgrade_elite")],
                ])

            await _safe_send(
                paywall_text,
                reply_markup=upgrade_kb,
            )
            return

        track_funnel("advisor_used")
        track_bucket_kpi(get_user_bucket(uid), "advisor_used")

        history = user.get("trade_history", [])
        if not history:
            await _safe_send("📈 *No Trade History Found.*")
            return

        msg = await _safe_send("🤖 *AI Advisor is analyzing your stats...*")
        analysis = await analyze_trader_performance(uid, history)
        use_fallback_intro = "(Fallback Model)" in analysis or analysis.startswith("Fallback reason:")
        final_text = f"{get_advisor_intro(use_fallback=use_fallback_intro)}{analysis}"
        try:
            await msg.edit_text(final_text[:3900], parse_mode="Markdown")
        except Exception:
            # Fallback for markdown parse issues or message edit constraints.
            try:
                await msg.edit_text(final_text[:3900])
            except Exception:
                await _safe_send(final_text[:3900], parse_mode=None)
    except Exception as e:
        logger.error(f"cmd_advisor error user={uid}: {e}")
        await _safe_send("⚠️ AI Advisor tijdelijk niet beschikbaar. Probeer opnieuw over 30 sec.", parse_mode=None)
    finally:
        context.user_data["advisor_busy"] = False
        # Keep redis lock until TTL expires to absorb queued/double taps
        # across rolling instances and delayed callback deliveries.


async def cmd_advisor_diag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin diagnostics for advisor runtime state."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    from agents.advisor_agent import advisor_runtime_snapshot, advisor_live_probe

    snap = advisor_runtime_snapshot()
    configured = snap.get("configured_chain", [])
    resolved = snap.get("resolved_chain", [])

    text = (
        "🧪 *Advisor Runtime Diagnostics*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"GEMINI_API_KEY: {'✅ present' if snap.get('gemini_key_present') else '❌ missing'}\n"
        f"Configured chain ({len(configured)}):\n"
        + "\n".join([f"• `{m}`" for m in configured[:8]])
        + "\n\n"
        + f"Resolved chain ({len(resolved)}):\n"
        + "\n".join([f"• `{m}`" for m in resolved[:12]])
    )

    probe = await advisor_live_probe()
    if probe.get("ok"):
        text += (
            "\n\n✅ *Live probe:* Gemini reachable\n"
            f"Model: `{probe.get('model')}`\n"
            f"Preview: `{str(probe.get('preview', ''))[:90]}`"
        )
    else:
        text += (
            "\n\n⚠️ *Live probe:* Gemini unavailable\n"
            f"Reason: `{probe.get('reason', 'unknown')}`"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_smoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only live smoke test for core app/bot endpoints."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    from agents.advisor_agent import advisor_live_probe

    urls = [
        WEBSITE_URL,
        f"{WEBSITE_URL}/api/events?hours=24&latest=1",
        f"{WEBSITE_URL}/api/subscribe",
        f"https://t.me/{BOT_USERNAME}",
        f"https://t.me/{BOT_USERNAME}?start=elite",
    ]

    lines = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for url in urls:
            status = 0
            ok = False
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    status = resp.status
                    ok = 200 <= status < 400
            except Exception:
                ok = False

            emoji = "✅" if ok else "❌"
            lines.append(f"{emoji} `{status if status else 'ERR'}` {url}")

    probe = await advisor_live_probe()
    if probe.get("ok"):
        advisor_line = f"✅ Advisor probe: `{probe.get('model')}`"
    else:
        advisor_line = f"⚠️ Advisor probe fallback: `{probe.get('reason', 'unknown')}`"

    # Update runtime snapshot for SLA command
    RUNTIME_HEALTH["advisor_ok"] = bool(probe.get("ok"))
    RUNTIME_HEALTH["advisor_reason"] = str(probe.get("reason") or "")
    RUNTIME_HEALTH["advisor_model"] = str(probe.get("model") or "")
    RUNTIME_HEALTH["advisor_checks_total"] = int(RUNTIME_HEALTH.get("advisor_checks_total", 0)) + 1
    if probe.get("ok"):
        RUNTIME_HEALTH["advisor_checks_ok"] = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0)) + 1

    RUNTIME_HEALTH["endpoint_ok"] = all(line.startswith("✅") for line in lines)
    RUNTIME_HEALTH["endpoint_failed"] = [line for line in lines if line.startswith("❌")][:8]
    RUNTIME_HEALTH["endpoint_checks_total"] = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0)) + 1
    if RUNTIME_HEALTH["endpoint_ok"]:
        RUNTIME_HEALTH["endpoint_checks_ok"] = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0)) + 1

    RUNTIME_HEALTH["last_smoke_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _record_sla_history("smoke")
    _save_runtime_health()

    text = (
        "🧪 *ApexFlash Live Smoke Test*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines)
        + "\n\n"
        + advisor_line
    )

    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_autotrade_diag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only quick diagnostics for autonomous trading readiness."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    admin_id = ADMIN_IDS[0] if isinstance(ADMIN_IDS, list) and ADMIN_IDS else (ADMIN_IDS if isinstance(ADMIN_IDS, int) else 0)
    admin_user = users.get(admin_id) if isinstance(admin_id, int) else None
    if not admin_user and isinstance(admin_id, int):
        admin_user = users.get(str(admin_id))

    wallet_pub = str((admin_user or {}).get("wallet_pubkey") or "")
    wallet_ready = bool((admin_user or {}).get("wallet_secret_enc"))
    sol_balance = 0.0
    if wallet_pub:
        try:
            sol_balance = float(await get_sol_balance(wallet_pub) or 0.0)
        except Exception:
            sol_balance = 0.0

    reserve = float(MIN_SOL_RESERVE)
    configured_trade = float(AUTONOMOUS_TRADE_AMOUNT_SOL)
    required = configured_trade + reserve
    tradeable_sol = max(0.0, sol_balance - reserve)
    # Dynamic sizing floor in zero_loss_manager
    dynamic_floor = 0.05
    test_cap_sol = 0.0
    runtime_enabled = _autotrade_enabled_flag()
    try:
        from core.persistence import _get_redis
        _r = _get_redis()
        if _r:
            test_cap_sol = max(0.0, float(_r.get("apexflash:autotrade:test_cap_sol") or 0.0))
    except Exception:
        test_cap_sol = 0.0
    effective_floor = 0.05 if test_cap_sol <= 0 else max(0.01, min(test_cap_sol, 0.05))
    funding_ok = tradeable_sol >= effective_floor

    pos_count = 0
    gov = get_governance_config()
    cfg_min_move = float(gov.get("grade_a_min_pct", 2.5) or 2.5)
    cfg_min_vol = float(gov.get("min_volume_usd", 1500000) or 1500000)
    eff_min_move = min(cfg_min_move, 0.8)
    eff_min_vol = min(cfg_min_vol, 250000.0)
    try:
        from zero_loss_manager import active_positions, AUTOTRADE_STATE
        from scalper import SCALPER_STATE
        pos_count = len(active_positions) if isinstance(active_positions, dict) else 0
        auto_state = AUTOTRADE_STATE if isinstance(AUTOTRADE_STATE, dict) else {}
        scalper_state = SCALPER_STATE if isinstance(SCALPER_STATE, dict) else {}
    except Exception:
        pos_count = 0
        active_positions = {}
        auto_state = {}
        scalper_state = {}

    last_reason = str(auto_state.get("last_reason", "-"))
    last_entry_symbol = str(auto_state.get("last_entry_symbol", "-"))
    last_entry_ts = str(auto_state.get("last_entry_ts", "-"))
    if pos_count > 0 and last_reason == "no_signals":
        last_reason = "holding_position"
    if pos_count > 0 and last_entry_symbol == "-" and isinstance(active_positions, dict) and active_positions:
        try:
            last_entry_symbol = next(iter(active_positions.keys()))
            if last_entry_ts == "-":
                last_entry_ts = "open_position"
        except Exception:
            pass

    text = (
        "🛡️ *Autotrade Diagnostics*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Autotrade runtime: `{'ON' if runtime_enabled else 'OFF'}`\n"
        f"Admin user found: `{'YES' if isinstance(admin_user, dict) else 'NO'}`\n"
        f"Wallet secret: `{'READY' if wallet_ready else 'MISSING'}`\n"
        f"Wallet pubkey: `{wallet_pub or '-'}`\n"
        f"SOL balance: `{sol_balance:.4f}`\n"
        f"Configured trade: `{configured_trade:.4f}` | Reserve: `{reserve:.4f}`\n"
        f"Tradeable SOL now: `{tradeable_sol:.4f}`\n"
        f"Strict min (configured): `{required:.4f}`\n"
        f"Selectivity cfg: move>={cfg_min_move:.2f}% | vol>={cfg_min_vol:,.0f} USD\n"
        f"Selectivity effective: move>={eff_min_move:.2f}% | vol>={eff_min_vol:,.0f} USD\n"
        f"Test mode cap: `{test_cap_sol:.4f} SOL` ({'ON' if test_cap_sol > 0 else 'OFF'})\n"
        f"Dynamic floor: `{effective_floor:.4f}`\n"
        f"Funding OK (dynamic): `{'YES' if funding_ok else 'NO'}`\n"
        f"Active positions: `{pos_count}`\n"
        f"Scan ts: `{auto_state.get('last_cycle_ts', '-')}`\n"
        f"Signals scanned: `{auto_state.get('signals_scanned', 0)}` | candidates: `{auto_state.get('candidates', 0)}`\n"
        f"No-signal cycles: `{auto_state.get('no_signal_cycles', 0)}`\n"
        f"Skips — selectivity `{auto_state.get('skipped_selectivity', 0)}`, trend `{auto_state.get('skipped_trend', 0)}`, panic `{auto_state.get('skipped_panic', 0)}`, balance `{auto_state.get('skipped_balance', 0)}`\n"
        f"Scalper fetch: prices `{scalper_state.get('prices_count', 0)}` | volume symbols `{scalper_state.get('volume_symbols', 0)}` | history ready `{scalper_state.get('history_ready', 0)}` | signals `{scalper_state.get('signals_generated', 0)}`\n"
        f"Scalper ts: `{scalper_state.get('last_fetch_ts', '-')}`\n"
        f"Last reason: `{last_reason}`\n"
        f"Last entry error: `{auto_state.get('last_entry_error', '-')}`\n"
        f"Last entry: `{last_entry_symbol} @ {last_entry_ts}`\n"
        "Tip: run `/ops_now` and check for zero-loss entry alerts."
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_autotrade_test_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: enable controlled autotrade test mode with mini-size cap."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    cap = float(TEST_TRADE_SOL) if TEST_TRADE_SOL > 0 else 0.05
    if context.args:
        try:
            cap = float(context.args[0])
        except Exception:
            pass
    cap = max(0.01, min(cap, 0.10))
    from core.persistence import _get_redis
    r = _get_redis()
    if r:
        r.set("apexflash:autotrade:test_cap_sol", f"{cap:.4f}")
    await update.message.reply_text(
        f"🧪 *Autotrade Test Mode: ON*\n"
        f"Cap set to *{cap:.4f} SOL* per entry.\n"
        f"Use `/autotrade_test_off` to disable.",
        parse_mode="Markdown",
    )


async def cmd_autotrade_test_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: disable controlled autotrade test mode."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    from core.persistence import _get_redis
    r = _get_redis()
    if r:
        r.delete("apexflash:autotrade:test_cap_sol")
    await update.message.reply_text("✅ *Autotrade Test Mode: OFF*", parse_mode="Markdown")


async def cmd_ai_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: AI Router dashboard — shows all free model health & routing."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    await update.message.reply_text("🔄 Probing all AI models... (~10s)", parse_mode="Markdown")

    try:
        from agents.ai_router import get_health_snapshot, probe_all, JOB_CHAINS
        probe_results = await probe_all()
        health = get_health_snapshot()

        lines = ["🤖 *AI Router Dashboard*\n━━━━━━━━━━━━━━━━━━━━━\n"]

        for key, info in health.items():
            probe_ok = probe_results.get(key)
            if probe_ok is None:
                status = "⚫ no key"
            elif probe_ok:
                status = "✅ online"
            else:
                status = "🔴 failed"

            blocked = f" ⏳{info['blocked_secs']}s" if info["blocked_secs"] > 0 else ""
            calls = info["calls"]
            ok = info["ok"]
            sla = f"{ok}/{calls}" if calls else "-"
            lines.append(
                f"`{key:<16}` {status}{blocked}\n"
                f"  _{info['model']}_\n"
                f"  SLA: `{sla}` | Provider: `{info['provider']}`\n"
            )

        lines.append("\n*Job → Active Chain*\n")
        for job, chain in JOB_CHAINS.items():
            lines.append(f"`{job:<12}` → {' → '.join(chain)}\n")

        await update.message.reply_text("".join(lines), parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ AI Status error: `{e}`", parse_mode="Markdown")


async def cmd_whale_intel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/whale_intel — Show GMGN whale intelligence signals (admin)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    from agents.whale_watcher import get_whale_stats, format_whale_signal
    stats = get_whale_stats()
    if "error" in stats:
        await update.message.reply_text("❌ Redis unavailable")
        return
    lines = [
        f"🐋 *Whale Intelligence v2.0*\n"
        f"GMGN: {'✅' if stats['gmgn_configured'] else '❌'} | "
        f"Auto: {'✅' if stats['auto_trade'] else '❌'} {stats.get('auto_trade_sol',0)} SOL\n"
        f"Scan: every {stats['scan_interval_min']}min\n\n"
        f"*Recent Signals:*\n"
    ]
    for sig in (stats.get("recent_signals") or [])[:8]:
        em = {"S": "🚨", "A": "🔥", "B": "⚡"}.get(sig.get("grade", ""), "📊")
        lines.append(
            f"{em} [{sig.get('grade','')}] *{sig.get('symbol','?')}* "
            f"1h:{sig.get('chg_1h',0):+.1f}% 🧠{sig.get('smart_degens',0)}\n"
        )
    if not stats.get("recent_signals"):
        lines.append("_No signals yet — scanner active, first scan within 5 min_\n")
    await update.message.reply_text("".join(lines), parse_mode="Markdown")


async def cmd_pdca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pdca — PDCA signal journal: win rates per grade + improvement recommendations."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    from agents.trade_journal import format_pdca_report_telegram
    text = format_pdca_report_telegram(days=7)
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_whale_copy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: wcp_{short_mint} — Copy-trade a whale signal.
    Executes a small SOL buy via Jupiter using the CLICKING USER's bot wallet.
    Open to any user who has created a bot wallet.
    """
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    user = _get_or_create_user(uid, query.from_user.username)

    # Require bot wallet
    if not user.get("wallet_pubkey") or not user.get("wallet_secret_enc"):
        await query.message.reply_text(
            "⚠️ You need a bot wallet to copy trade.\n"
            "Open @ApexFlashBot → /start → Trade → My Wallet → Create Wallet."
        )
        return

    short = query.data.replace("wcp_", "", 1)

    from agents.whale_watcher import load_signal_from_callback, COPY_TRADE_SOL
    sig = load_signal_from_callback(short)
    if not sig:
        await query.message.reply_text(
            "⏰ Signal expired (>24h old).\n"
            "Open @ApexFlashBot for fresh signals."
        )
        return

    mint   = sig.get("mint", "")
    symbol = sig.get("symbol", "?")
    grade  = sig.get("grade", "?")

    await query.message.reply_text(
        f"🤖 Copy buy: *{symbol}* [{grade}]\n"
        f"Amount: `{COPY_TRADE_SOL} SOL`\n"
        f"Token: `{mint[:20]}...`\n"
        f"_Routing via Jupiter..._",
        parse_mode="Markdown",
    )

    try:
        import json as _json, time as _time
        from exchanges.jupiter import get_quote, execute_swap

        SOL_MINT = "So11111111111111111111111111111111111111112"
        lamports = int(COPY_TRADE_SOL * 1_000_000_000)

        # Check user balance
        bal = await get_sol_balance(user["wallet_pubkey"])
        if bal is None or bal < COPY_TRADE_SOL + 0.01:
            await query.message.reply_text(
                f"⚠️ Insufficient balance.\n"
                f"Need: {COPY_TRADE_SOL + 0.01:.3f} SOL | Have: {bal or 0:.4f} SOL\n"
                f"Deposit SOL to: `{user['wallet_pubkey']}`",
                parse_mode="Markdown",
            )
            return

        keypair = load_keypair(user["wallet_secret_enc"])

        # Get quote
        quote = await get_quote(
            input_mint=SOL_MINT,
            output_mint=mint,
            amount_raw=lamports,
            slippage_bps=500,
        )
        if not quote:
            await query.message.reply_text(f"Quote failed — {symbol} may be illiquid.")
            return

        # Execute
        tx_sig, swap_err = await execute_swap(keypair, quote)
        if not tx_sig:
            await query.message.reply_text(f"Swap failed: {swap_err or 'unknown error'}")
            return

        # Log to PDCA journal
        from agents.trade_journal import log_signal as journal_log
        journal_log({**sig, "source": f"COPY_TRADE_{grade}"})

        # Store in Redis for position tracking
        r = _get_redis()
        if r:
            r.setex(
                f"whale:copy:{mint[:16]}",
                8 * 3600,
                _json.dumps({"tx": tx_sig, "sol": COPY_TRADE_SOL, "symbol": symbol,
                              "grade": grade, "ts": int(_time.time())}),
            )

        await query.message.reply_text(
            f"DONE Copy buy executed!\n"
            f"Token: {symbol} [{grade}]\n"
            f"Amount: {COPY_TRADE_SOL} SOL\n"
            f"TX: {tx_sig}\n"
            f"https://solscan.io/tx/{tx_sig}",
        )
    except Exception as e:
        logger.error(f"Whale copy buy error: {e}")
        await query.message.reply_text(
            f"Copy buy failed: {str(e)[:150]}\nCheck Render logs."
        )


async def handle_whale_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: wtr_{wallet_short} — Add whale wallet to Inspector live tracking.
    """
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_reply_markup(reply_markup=None)
        return

    short_addr = query.data.replace("wtr_", "", 1)

    # Lookup full wallet address from the stored signal
    r = _get_redis()
    full_addr = short_addr  # fallback
    if r:
        import json as _json
        # Search recent signals for a matching wallet
        keys = r.keys("whale:sig:*")
        for k in keys[:20]:
            raw = r.get(k)
            if not raw:
                continue
            try:
                d = _json.loads(raw)
                for w in (d.get("whale_wallets") or []):
                    addr = w.get("wallet_address") or w.get("address", "")
                    if addr.startswith(short_addr):
                        full_addr = addr
                        break
            except Exception:
                continue
            if full_addr != short_addr:
                break

    try:
        from agents.inspector_agent import add_alpha_wallet
        is_new = add_alpha_wallet(full_addr, label=f"WhaleSignal_{short_addr[:8]}")

        # Also persist in Redis so Inspector picks it up after restart
        if r:
            import time as _time
            r.sadd("inspector:dynamic_wallets", full_addr)
            r.setex(f"inspector:wallet:{full_addr[:16]}", 7 * 24 * 3600,
                    f"WhaleSignal_{short_addr[:8]}")

        status = "Added to live tracking" if is_new else "Already being tracked"
        await query.message.reply_text(
            f"👁 *Whale Wallet Tracking*\n"
            f"`{full_addr[:20]}...`\n"
            f"Status: {status}\n"
            f"Inspector will alert on next buy/sell.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Track error: {e}")


async def cmd_myip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/myip — Show current outbound IP of Render. Use to whitelist on GMGN dashboard."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # Use async aiohttp — blocking urllib.request would stall the event loop
    try:
        async with aiohttp.ClientSession() as _ses:
            async with _ses.get(
                "https://api.ipify.org?format=json",
                headers={"User-Agent": "ApexFlash/1.0"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as _resp:
                ip = (await _resp.json()).get("ip", "unknown")
    except Exception as e:
        ip = f"error: {e}"

    # Also check cached IP from last GMGN 403
    from core.persistence import _get_redis
    r = _get_redis()
    cached_ip = r.get("apexflash:render:outbound_ip") if r else None

    text = (
        f"🌐 *Render Outbound IP*\n"
        f"Current: `{ip}`\n"
    )
    if cached_ip and cached_ip != ip:
        text += f"Last 403 IP: `{cached_ip}`\n"

    text += (
        f"\n📋 *Action needed:*\n"
        f"1. Go to [gmgn.ai](https://gmgn.ai) → API settings → Trusted IPs\n"
        f"2. Add: `{ip}`\n"
        f"3. GMGN whale scanner activates within 5 min\n"
    )
    if r:
        r.setex("apexflash:render:outbound_ip", 3600, ip)
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_ip_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ip_status — Admin diagnostics: current IP, previous, history, GMGN 403 counters."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    try:
        async with aiohttp.ClientSession() as _ses:
            async with _ses.get(
                "https://api.ipify.org?format=json",
                headers={"User-Agent": "ApexFlash/1.0"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as _resp:
                current_ip = (await _resp.json()).get("ip", "unknown")
    except Exception as e:
        current_ip = f"error: {e}"

    from core.persistence import _get_redis
    r = _get_redis()

    def _decode(v):
        if v is None:
            return None
        return v.decode() if isinstance(v, bytes) else v

    prev_ip = last_403_ip = gmgn_403_cnt = None
    history_entries = []
    if r:
        try:
            prev_ip = _decode(r.get("apexflash:render:ip_previous"))
            last_403_ip = _decode(r.get("apexflash:gmgn:403_last_ip"))
            gmgn_403_cnt = _decode(r.get("apexflash:gmgn:403_count_total")) or "0"
            raw_hist = r.lrange("apexflash:render:ip_history", 0, 9) or []
            import time as _t
            for item in raw_hist:
                s = _decode(item)
                if not s or "|" not in s:
                    continue
                ip_part, ts_part = s.split("|", 1)
                try:
                    ts_fmt = _t.strftime("%m-%d %H:%M", _t.gmtime(int(ts_part)))
                except Exception:
                    ts_fmt = ts_part
                history_entries.append(f"• `{ip_part}` — {ts_fmt}Z")
        except Exception as _e:
            logger.error(f"/ip_status Redis read failed: {_e}")

    changed = bool(prev_ip and current_ip and prev_ip != current_ip and not current_ip.startswith("error"))
    change_line = "🚨 CHANGED vs last boot" if changed else "✅ stable"

    hist_block = "\n".join(history_entries) if history_entries else "_(empty)_"

    text = (
        f"🌐 *IP Status Diagnostics*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Current:  `{current_ip}`\n"
        f"Previous: `{prev_ip or '—'}`\n"
        f"Status:   {change_line}\n\n"
        f"*GMGN 403 telemetry*\n"
        f"Last rejected IP: `{last_403_ip or '—'}`\n"
        f"403 count (1h):   {gmgn_403_cnt}\n\n"
        f"*IP history (last 10)*\n"
        f"{hist_block}"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only lean QA summary: integrity + watchdog + autotrade readiness."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    integrity = _runtime_integrity_snapshot()
    advisor_ok = RUNTIME_HEALTH.get("advisor_ok")
    endpoint_ok = RUNTIME_HEALTH.get("endpoint_ok")

    admin_id = ADMIN_IDS[0] if isinstance(ADMIN_IDS, list) and ADMIN_IDS else (ADMIN_IDS if isinstance(ADMIN_IDS, int) else 0)
    admin_user = users.get(admin_id) if isinstance(admin_id, int) else None
    if not admin_user and isinstance(admin_id, int):
        admin_user = users.get(str(admin_id))
    if not admin_user and isinstance(admin_id, int):
        admin_user = users.get(str(admin_id))
    wallet_ready = bool((admin_user or {}).get("wallet_secret_enc"))

    text = (
        "🧪 *Lean QA Snapshot*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Runtime integrity: `{'OK' if integrity.get('ok') else 'ISSUES'}`\n"
        f"Advisor watchdog: `{'OK' if advisor_ok is True else 'ISSUES' if advisor_ok is False else 'UNKNOWN'}`\n"
        f"Endpoint watchdog: `{'OK' if endpoint_ok is True else 'ISSUES' if endpoint_ok is False else 'UNKNOWN'}`\n"
        f"Autotrade wallet: `{'READY' if wallet_ready else 'MISSING'}`\n"
        f"Last smoke: `{RUNTIME_HEALTH.get('last_smoke_ts', '-')}`\n"
        f"Last integrity: `{RUNTIME_HEALTH.get('last_integrity_ts', '-')}`\n"
        "Tip: run `/ops_now` for full cycle."
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_sla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only SLA snapshot from runtime watchdog/smoke states."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    advisor_ok = RUNTIME_HEALTH.get("advisor_ok")
    endpoint_ok = RUNTIME_HEALTH.get("endpoint_ok")
    advisor_status = "✅ online" if advisor_ok is True else "⚠️ fallback" if advisor_ok is False else "❔ unknown"
    endpoint_status = "✅ healthy" if endpoint_ok is True else "⚠️ issues" if endpoint_ok is False else "❔ unknown"
    failed = RUNTIME_HEALTH.get("endpoint_failed", []) or []

    advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
    advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
    endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
    endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))

    advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
    endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0
    advisor_breach = bool(RUNTIME_HEALTH.get("advisor_sla_breach"))
    endpoint_breach = bool(RUNTIME_HEALTH.get("endpoint_sla_breach"))

    history = RUNTIME_HEALTH.get("sla_history", [])
    if not isinstance(history, list):
        history = []
    recent = history[-12:]
    incident_points = [
        h for h in history[-20:]
        if (h.get("advisor_state") == "BREACH" or h.get("endpoint_state") == "BREACH"
            or h.get("advisor_ok") is False or h.get("endpoint_ok") is False)
    ]

    uptime = datetime.now(timezone.utc) - bot_start_time
    uptime_h = int(uptime.total_seconds() // 3600)
    uptime_m = int((uptime.total_seconds() % 3600) // 60)

    admin_id = ADMIN_IDS[0] if isinstance(ADMIN_IDS, list) and ADMIN_IDS else (ADMIN_IDS if isinstance(ADMIN_IDS, int) else 0)
    admin_user = users.get(admin_id) if isinstance(admin_id, int) else None
    autotrade_wallet_ready = bool(admin_user and admin_user.get("wallet_secret_enc"))
    autotrade_positions = 0
    try:
        from zero_loss_manager import active_positions
        autotrade_positions = len(active_positions) if isinstance(active_positions, dict) else 0
    except Exception:
        autotrade_positions = 0

    text = (
        "📡 *ApexFlash SLA Snapshot*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Advisor: {advisor_status}\n"
        f"Endpoints: {endpoint_status}\n"
        f"Model: `{RUNTIME_HEALTH.get('advisor_model', '') or '-'}" + "`\n"
        f"Fallback reason: `{RUNTIME_HEALTH.get('advisor_reason', '') or '-'}" + "`\n"
        f"Advisor SLA window: `{advisor_ok_count}/{advisor_total}` ({advisor_sla:.2f}%)\n"
        f"Endpoint SLA window: `{endpoint_ok_count}/{endpoint_total}` ({endpoint_sla:.2f}%)\n"
        f"Advisor SLA state: `{'BREACH' if advisor_breach else 'OK'}`\n"
        f"Endpoint SLA state: `{'BREACH' if endpoint_breach else 'OK'}`\n"
        f"Last smoke: `{RUNTIME_HEALTH.get('last_smoke_ts', '-')}`\n"
        f"Last watchdog: `{RUNTIME_HEALTH.get('last_watchdog_ts', '-')}`\n"
        f"Last ops autocheck: `{RUNTIME_HEALTH.get('last_ops_autocheck_ts', '-')}`\n"
        f"Integrity: `{'OK' if RUNTIME_HEALTH.get('integrity_ok') else 'ISSUES' if RUNTIME_HEALTH.get('integrity_ok') is False else 'unknown'}`\n"
        f"Last integrity check: `{RUNTIME_HEALTH.get('last_integrity_ts', '-')}`\n"
        f"Daily drift alert: `{'ACTIVE' if RUNTIME_HEALTH.get('daily_drift_alert_active') else 'OK'}`\n"
        f"Last drift alert: `{RUNTIME_HEALTH.get('last_daily_drift_alert_ts', '-')}`\n"
        f"Ops status: `{'running' if RUNTIME_HEALTH.get('ops_running') else RUNTIME_HEALTH.get('last_ops_status', 'idle')}`\n"
        f"Ops error: `{RUNTIME_HEALTH.get('last_ops_error', '') or '-'}`\n"
        f"Uptime: `{uptime_h}h {uptime_m}m`\n"
        "Tip: run `/ops_now` for immediate full autonomous health cycle."
    )

    if failed:
        text += "\n\n❌ Failed endpoints:\n" + "\n".join(failed[:6])

    missing_env = RUNTIME_HEALTH.get("integrity_missing_env", []) or []
    invalid_aff = RUNTIME_HEALTH.get("integrity_affiliate_invalid", []) or []
    if missing_env:
        text += "\n\n⚠️ Missing critical env:\n" + "\n".join([f"• `{k}`" for k in missing_env[:8]])
    if invalid_aff:
        text += "\n\n⚠️ Affiliate config issues:\n" + "\n".join([f"• `{k}`" for k in invalid_aff[:8]])

    if recent:
        text += "\n\n📈 Recent trend (last 12 points):\n"
        for h in recent[-6:]:
            text += (
                f"• `{h.get('ts','-')}` [{h.get('source','-')}] "
                f"A:{h.get('advisor_sla','-')}% ({h.get('advisor_state','-')}) | "
                f"E:{h.get('endpoint_sla','-')}% ({h.get('endpoint_state','-')})\n"
            )

    if incident_points:
        text += "\n🧯 Mini incident timeline:\n"
        for h in incident_points[-4:]:
            text += (
                f"• `{h.get('ts','-')}` [{h.get('source','-')}] "
                f"advisor_ok={h.get('advisor_ok')} endpoint_ok={h.get('endpoint_ok')}\n"
            )

    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_ops_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only trigger to force immediate autonomous ops checks."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if RUNTIME_HEALTH.get("ops_running"):
        await update.message.reply_text("⏳ Ops check already running. Please wait for completion.")
        return

    await update.message.reply_text("🛰️ Running full autonomous ops check now...")

    RUNTIME_HEALTH["ops_running"] = True
    RUNTIME_HEALTH["last_ops_status"] = "running"
    RUNTIME_HEALTH["last_ops_error"] = ""
    try:
        # Reuse existing commands so behavior stays aligned with /smoke + /advisor_diag + /sla.
        await cmd_smoke(update, context)
        await cmd_advisor_diag(update, context)
        await cmd_sla(update, context)
        RUNTIME_HEALTH["last_ops_status"] = "ok"
    except Exception as e:
        RUNTIME_HEALTH["last_ops_status"] = "failed"
        RUNTIME_HEALTH["last_ops_error"] = str(e)
        raise
    finally:
        RUNTIME_HEALTH["ops_running"] = False
        _record_sla_history("ops_now")
        _save_runtime_health()

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language selection menu."""
    from core.i18n import get_text
    uid = update.effective_user.id
    user = get_user(uid)
    lang = user.get("language_code", "en")
    
    kb = [
        [InlineKeyboardButton("English 🇺🇸", callback_data="set_lang_en"), InlineKeyboardButton("Español 🇪🇸", callback_data="set_lang_es")],
        [InlineKeyboardButton("中文 🇨🇳", callback_data="set_lang_zh"), InlineKeyboardButton("Nederlands 🇳🇱", callback_data="set_lang_nl")],
        [_back_main()[0]]
    ]
    await update.message.reply_text(get_text("SELECT_LANG", lang), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def cmd_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user their AI-personalized 'Road to €1M' path."""
    user_id = update.effective_user.id
    lang = context.user_data.get("lang", "en")
    
    # Static content for now, but AI-ready for customization
    title = "🏆 *THE APEX ROAD TO €1,000,000*"
    body = (
        "1. 🚀 *Onboarding:* Fund your wallet with 0.1+ SOL.\n"
        "2. 🛡️ *Protection:* Lock in 0.5% Breakeven (Auto-Guard).\n"
        "3. 📈 *Scaling:* Copy elite traders via 'Alpha Clan'.\n"
        "4. 💎 *Compounding:* Reinvest 50% of profits into the bot.\n\n"
        "Your current progress: *Phase 1 (Active)*"
    )
    kb = [[InlineKeyboardButton("⚡ Optimize Strategy", callback_data="cmd_advisor")]]
    await update.message.reply_text(f"{title}\n\n{body}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def scheduled_conversion_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily check for free users to send FOMO reports."""
    from agents.conversion_agent import check_conversion_eligibility, generate_opportunity_report
    logger.info("🕒 Scheduled Job: Conversion AI (Cycle 14)")
    
    from core.persistence import load_users
    users_data = load_users()
    
    for user_id, data in users_data.items():
        if await check_conversion_eligibility(user_id, data):
            lang = data.get("language_code", data.get("lang", "en"))
            report = await generate_opportunity_report(user_id, lang)
            if report:
                try:
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("💎 Upgrade to Elite", callback_data="advisor_upgrade_elite")],
                        [InlineKeyboardButton("📈 View Pricing", callback_data="advisor_view_pricing")],
                    ])
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=report,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                    track_funnel("conversion_report_sent")
                    track_bucket_kpi(get_user_bucket(user_id), "conversion_report_sent")
                    logger.info(f"Conversion report sent to {user_id}")
                except Exception as e:
                    logger.debug(f"Failed to send conversion report to {user_id}: {e}")


async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug: show handler and state info. No admin check for debugging."""
    uid = update.effective_user.id
    user = users.get(uid, {})
    has_wallet = bool(user.get("wallet_pubkey"))
    h_count = sum(len(v) for v in context.application.handlers.values())
    msg = (
        f"🔧 Debug Info\n"
        f"Users in memory: {len(users)}\n"
        f"Your ID: {uid}\n"
        f"Your user exists: {uid in users}\n"
        f"Your wallet: {has_wallet}\n"
        f"Handlers: {h_count}\n"
        f"Admin IDs: {ADMIN_IDS}\n"
        f"Is admin: {uid in ADMIN_IDS}\n"
        f"Trading: {trading_enabled}\n"
        f"Redis: {bool(os.getenv('UPSTASH_REDIS_URL', ''))}\n"
        f"Helius: {bool(HELIUS_API_KEY)}\n"
        f"Jupiter: {bool(JUPITER_API_KEY)}\n"
    )
    await update.message.reply_text(msg)


async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: restore from backup file. Reply to a backup JSON file with /restore."""
    if not is_admin(update.effective_user.id):
        return
    global users, platform_stats

    reply = update.message.reply_to_message
    if not reply or not reply.document:
        await update.message.reply_text(
            "\u26a0\ufe0f Reply to a backup JSON file with /restore"
        )
        return

    try:
        file = await reply.document.get_file()
        raw = await file.download_as_bytearray()
        json_str = raw.decode("utf-8")
        restored_users, restored_stats = import_backup(json_str)

        if not restored_users:
            await update.message.reply_text("\u274c Backup file contains no users.")
            return

        users.update(restored_users)
        if restored_stats:
            for k, v in restored_stats.items():
                platform_stats[k] = v
        _persist()

        await update.message.reply_text(
            f"\u2705 Restored {len(restored_users)} users from backup.\n"
            f"Total users now: {len(users)}"
        )
        logger.info(f"Backup restored: {len(restored_users)} users by admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Restore error: {e}")
        await update.message.reply_text(f"\u274c Restore failed: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-restore when admin forwards a backup JSON file (no /restore needed)."""
    if not is_admin(update.effective_user.id):
        return
    doc = update.message.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".json"):
        return
    if "backup" not in doc.file_name.lower() and "apexflash" not in doc.file_name.lower():
        return

    global users, platform_stats
    try:
        file = await doc.get_file()
        raw = await file.download_as_bytearray()
        json_str = raw.decode("utf-8")
        restored_users, restored_stats = import_backup(json_str)

        if not restored_users:
            await update.message.reply_text("\u274c Backup file contains no users.")
            return

        users.update(restored_users)
        if restored_stats:
            for k, v in restored_stats.items():
                platform_stats[k] = v
        _persist()

        wallets = sum(1 for u in restored_users.values() if u.get("wallet_pubkey"))
        await update.message.reply_text(
            f"\u2705 *Auto-Restore Complete*\n\n"
            f"Users restored: *{len(restored_users)}*\n"
            f"Wallets restored: *{wallets}*\n"
            f"Total users now: {len(users)}*\n\n"
            f"\U0001f512 All wallet keys recovered.",
            parse_mode="Markdown",
        )
        logger.info(f"Auto-restore from document: {len(restored_users)} users, {wallets} wallets")
    except Exception as e:
        logger.error(f"Document restore error: {e}")
        await update.message.reply_text(f"\u274c Auto-restore failed: {e}")


# ══════════════════════════════════════════════
# REFERRAL LEADERBOARD & STATS
# ══════════════════════════════════════════════

async def cmd_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show personal referral stats and the Global Leaderboard."""
    from core.persistence import get_user_referral_stats, get_referral_leaderboard
    
    uid = update.effective_user.id
    user = get_user(uid)
    stats = get_user_referral_stats(uid)
    leaderboard = get_referral_leaderboard(limit=5)
    
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    
    # 🏆 Personal Stats
    text = (
        "\U0001f91d *ApexFlash Referral Program*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"👤 *Your Stats:*\n"
        f"\u2022 Total Referrals: *{user.get('referral_count', 0)}*\n"
        f"\u2022 Total Earned: *{stats['earnings']:.4f} SOL*\n"
        f"\u2022 Global Rank: *#{stats['rank'] if stats['rank'] > 0 else 'N/A'}*\n\n"
        f"\U0001f517 *Your Referral Link:*\n{ref_link}\n\n"
        f"_Share this link to earn 25-40% of every trade fee your friends pay!_\n\n"
    )
    
    # 🥇 Global Leaderboard
    if leaderboard:
        text += "🏆 *GLOBAL REFERRAL LEADERS:*\n"
        emojis = ["🥇", "🥈", "🥉", "👤", "👤"]
        for i, entry in enumerate(leaderboard):
            emoji = emojis[i] if i < len(emojis) else "👤"
            # Anonymize user ID
            anon_name = f"User_{str(entry['user_id'])[-4:]}"
            text += f"{emoji} *{anon_name}*: `{entry['total_sol']:.2f} SOL` earned\n"
        text += "\n"
    
    kb = [
        [InlineKeyboardButton("\U0001f4e3 Share Link", switch_inline_query=f"\nJoin me on ApexFlash! The fastest whale tracker on Solana: {ref_link}")],
        [_back_main()[0]],
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def arbitrage_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recurring job to scan cross-chain arbitrage spreads (Elite Feature)."""
    from core.config import ELITE_CHANNEL_ID
    
    alerts = await scan_arbitrage()
    for alert in alerts:
        text = format_arbitrage_alert(alert)
        # Broadcast to Elite Channel and Admin Chat
        if ELITE_CHANNEL_ID:
            try:
                await context.bot.send_message(
                    chat_id=ELITE_CHANNEL_ID,
                    text=text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Arbitrage Elite alert failed: {e}")
        
        # Admin direct alert
        for admin_id in [u_id for u_id, u in users.items() if u.get("tier") == "admin"]:
            try:
                await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
            except: pass

async def _cb_switch_network_v320_legacy(query, user, context):
    """Toggle between Solana and Base networks."""
    current = user.get("active_chain", "SOL")
    new_chain = "BASE" if current == "SOL" else "SOL"
    user["active_chain"] = new_chain
    _persist()
    
    await query.answer(f"🌐 Switched to {new_chain} network")
    # Refresh menu
    await query.edit_message_reply_markup(reply_markup=main_menu_kb(query.from_user.id))

async def _cb_language_menu(query, user, context):
    """Callback to show language selection."""
    class FakeUpdate:
        effective_user = query.from_user
        message = query.message
    await cmd_language(FakeUpdate(), context)

async def _cb_advisor(query, user, context):
    """Callback to show AI advisor analysis."""
    try:
        await query.answer("🤖 AI Coach starting...")
    except Exception:
        pass

    # Fast callback-level lock on the tapped message (cross-instance safe when Redis is available).
    try:
        from core.persistence import _get_redis
        _r = _get_redis()
        if _r and query.message:
            cb_lock_key = f"apexflash:advisor:cb:{query.message.chat.id}:{query.message.message_id}"
            if not bool(_r.set(cb_lock_key, "1", ex=20, nx=True)):
                try:
                    await query.answer("⏳ AI Advisor is bezig met je vorige klik.", show_alert=False)
                except Exception:
                    pass
                return
    except Exception:
        pass

    if context.user_data.get("advisor_busy"):
        try:
            await query.answer("⏳ AI Advisor is bezig met je vorige request.", show_alert=False)
        except Exception:
            pass
        return

    class FakeUpdate:
        effective_user = query.from_user
        message = query.message
    await cmd_advisor(FakeUpdate(), context)


async def _cb_advisor_upgrade_elite(query, user, context):
    """Track advisor paywall upgrade intent and provide direct conversion links."""
    uid = query.from_user.id
    track_funnel("advisor_upgrade_click")
    track_bucket_kpi(get_user_bucket(uid), "advisor_upgrade_click")

    text = (
        "💎 *Upgrade to ApexFlash Elite*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Unlock full AI Advisor, advanced signals, and conversion-grade tooling.\n\n"
        "Choose your upgrade path below:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Open Elite Upgrade", url=f"https://t.me/{BOT_USERNAME}?start=elite")],
        [InlineKeyboardButton("📈 Compare Plans", url=f"{WEBSITE_URL}#pricing")],
        [_back_main()[0]],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _cb_advisor_view_pricing(query, user, context):
    """Track advisor paywall pricing intent."""
    uid = query.from_user.id
    track_funnel("advisor_pricing_click")
    track_bucket_kpi(get_user_bucket(uid), "advisor_pricing_click")

    text = (
        "📈 *ApexFlash Pricing*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Review Pro vs Elite and choose the best growth path."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Open Pricing Page", url=f"{WEBSITE_URL}#pricing")],
        [InlineKeyboardButton("💎 Go Elite in Telegram", url=f"https://t.me/{BOT_USERNAME}?start=elite")],
        [_back_main()[0]],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

async def _cb_set_lang_en(query, user, context): await _set_lang(query, user, "en")
async def _cb_set_lang_es(query, user, context): await _set_lang(query, user, "es")
async def _cb_set_lang_zh(query, user, context): await _set_lang(query, user, "zh")
async def _cb_set_lang_nl(query, user, context): await _set_lang(query, user, "nl")

async def _set_lang(query, user, lang_code):
    user["language_code"] = lang_code
    _persist()
    await query.answer(f"🗣 Language: {lang_code.upper()}")
    await query.edit_message_reply_markup(reply_markup=main_menu_kb(query.from_user.id))


async def _cb_referral(query, user, context):
    """Callback for referral button in main menu."""
    from core.persistence import get_user_referral_stats, get_referral_leaderboard

    uid = query.from_user.id
    stats = get_user_referral_stats(uid)
    leaderboard = get_referral_leaderboard(limit=5)

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    text = (
        "\U0001f91d *ApexFlash Referral Program*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\U0001f465 *Your Stats:*\n"
        f"\u2022 Total Referrals: *{user.get('referral_count', 0)}*\n"
        f"\u2022 Total Earned: *{stats['earnings']:.4f} SOL*\n"
        f"\u2022 Global Rank: *#{stats['rank'] if stats['rank'] > 0 else 'N/A'}*\n\n"
        f"\U0001f517 *Your Referral Link:*\n`{ref_link}`\n\n"
        f"_Share this link to earn 25-35% of every trade fee!_\n\n"
    )

    if leaderboard:
        text += "\U0001f3c6 *GLOBAL REFERRAL LEADERS:*\n"
        emojis = ["\U0001f947", "\U0001f948", "\U0001f949", "\U0001f464", "\U0001f464"]
        for i, entry in enumerate(leaderboard):
            emoji = emojis[i] if i < len(emojis) else "\U0001f464"
            anon_name = f"User_{str(entry['user_id'])[-4:]}"
            text += f"{emoji} *{anon_name}*: `{entry['total_sol']:.2f} SOL` earned\n"
        text += "\n"

    kb = [
        [InlineKeyboardButton(
            "\U0001f4e3 Share Link",
            switch_inline_query=f"Join me on ApexFlash! Fastest whale tracker on Solana: {ref_link}",
        )],
        [InlineKeyboardButton("\U0001f4ca Referral Stats", callback_data="referral_stats")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def _cb_whale_intent(query, user, context):
    """Callback for Elite users to analyze whale intent via AI."""
    if not can_user_analyze(user.get("tier", "free")):
        await query.answer("💎 Elite feature! Upgrade to analyze whale intent.", show_alert=True)
        return

    data = query.data.split("_")
    if len(data) < 4:
        await query.answer("⚠️ Analysis data incomplete.")
        return
    
    tx_hash_prefix = data[2]
    token_symbol = data[3]
    
    await query.answer("🤖 AI is analyzing whale history...")
    await query.edit_message_text(
        f"{query.message.text}\n\n"
        f"⏳ *AI ANALYZING INTENT...*",
        parse_mode="Markdown"
    )

    # Note: In a real system, we'd look up the full tx_hash from the prefix in seen_tx_hashes
    # For now, we use the token info we have.
    analysis = await analyze_whale_intent(
        tx_hash=tx_hash_prefix,
        wallet="Tracked Whale",
        token=token_symbol,
        amount_sol=0  # Simplified for the callback
    )

    await query.edit_message_text(
        f"{query.message.text}\n\n"
        f"\U0001f9e0 *AI WHALE INTENT:*\n"
        f"{analysis}",
        parse_mode="Markdown",
        reply_markup=query.message.reply_markup
    )


async def cmd_winrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show platform and user win rate stats."""
    from core.persistence import get_win_rate, get_user_win_rate

    uid = update.effective_user.id
    platform = get_win_rate()
    user_wr = get_user_win_rate(uid)

    p_rate = platform["win_rate"]
    p_total = platform["total"]
    p_wins = platform["wins"]
    p_losses = platform["losses"]
    p_pnl = platform["total_pnl_sol"]

    u_rate = user_wr["win_rate"]
    u_total = user_wr["total"]
    u_wins = user_wr["wins"]

    # Platform emoji
    if p_rate >= 65:
        rate_emoji = "\U0001f525"  # fire
    elif p_rate >= 50:
        rate_emoji = "\U0001f7e2"  # green
    else:
        rate_emoji = "\U0001f7e1"  # yellow

    text = (
        "\U0001f3af *ApexFlash Win Rate*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"{rate_emoji} *Platform Win Rate:* {p_rate}%\n"
        f"\U0001f4ca Total Trades: {p_total}\n"
        f"\u2705 Wins: {p_wins} | \u274c Losses: {p_losses}\n"
        f"\U0001f4b0 Total P/L: {p_pnl:+.4f} SOL\n\n"
    )

    if u_total > 0:
        text += (
            "\U0001f464 *Your Stats:*\n"
            f"Win Rate: {u_rate}% ({u_wins}/{u_total})\n\n"
        )

    if p_total < 10:
        text += "_Building track record... More trades = more data._\n"

    text += (
        "\n\U0001f4a1 *Tip:* Our AI Signal Filter only sends Grade A-C alerts.\n"
        "Grade D signals are automatically suppressed."
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_deals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current exchange deals and promo bonuses."""
    text = (
        "\U0001f381 *Exclusive Exchange Deals*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    )

    deals = [
        (k, v) for k, v in AFFILIATE_LINKS.items()
        if v.get("promo")
    ]

    for i, (key, aff) in enumerate(deals, 1):
        text += (
            f"*{i}. {aff['name']}*\n"
            f"\U0001f381 {aff['promo']}\n"
            f"\U0001f4b8 Commission: {aff['commission']} fee rebate\n"
            f"\u2192 [Sign Up Now]({aff['url']})\n\n"
        )

    # Non-promo featured exchanges
    others = [
        (k, v) for k, v in AFFILIATE_LINKS.items()
        if not v.get("promo") and v.get("featured")
    ]
    if others:
        for key, aff in others:
            text += f"\u2022 [{aff['name']}]({aff['url']}) \u2014 {aff['commission']}\n"

    text += (
        "\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f4a1 Sign up via our links and you support ApexFlash!\n"
        "All bonuses are verified and exclusive."
    )

    kb = []
    for key, aff in deals[:4]:
        kb.append([InlineKeyboardButton(
            f"\U0001f525 {aff['name']} \u2014 {aff.get('promo', '')[:30]}",
            callback_data=f"aff_click_{key}",
        )])
    kb.append([InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# LEADERBOARD COMMAND
# ══════════════════════════════════════════════

async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top traders by win rate and P/L — public social proof."""
    from core.persistence import get_win_rate

    platform = get_win_rate()

    text = (
        "\U0001f3c6 *ApexFlash Leaderboard*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    )

    # Build leaderboard from user trade histories
    traders = []
    for uid, udata in users.items():
        history = udata.get("trade_history", [])
        if not history:
            continue

        buys = [t for t in history if t.get("side") == "BUY"]
        sells = [t for t in history if t.get("side") == "SELL"]
        total_trades = len(history)

        # Calculate rough P/L from trade history
        total_buy_sol = sum(t.get("sol_amount", 0) for t in buys)
        total_sell_sol = sum(t.get("sol_amount", 0) for t in sells)

        if total_trades >= 2 and total_buy_sol > 0:
            pnl_sol = total_sell_sol - total_buy_sol
            pnl_pct = (pnl_sol / total_buy_sol * 100) if total_buy_sol > 0 else 0

            # Anonymize: show first 4 chars of user ID
            display_name = f"Trader #{str(uid)[-4:]}"
            traders.append({
                "name": display_name,
                "trades": total_trades,
                "pnl_sol": pnl_sol,
                "pnl_pct": pnl_pct,
            })

    # Sort by P/L percentage (best first)
    traders.sort(key=lambda x: x["pnl_pct"], reverse=True)

    if traders:
        for i, t in enumerate(traders[:10], 1):
            pnl_emoji = "\U0001f7e2" if t["pnl_pct"] >= 0 else "\U0001f534"
            medal = ["\U0001f947", "\U0001f948", "\U0001f949"][i-1] if i <= 3 else f"{i}."
            text += (
                f"{medal} *{t['name']}*\n"
                f"   {pnl_emoji} P/L: {t['pnl_sol']:+.4f} SOL ({t['pnl_pct']:+.1f}%)\n"
                f"   \U0001f4ca Trades: {t['trades']}\n\n"
            )
    else:
        text += (
            "\U0001f4ad No trades recorded yet.\n"
            "Be the first on the leaderboard!\n\n"
        )

    # Platform stats
    text += (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4ca *Platform Stats*\n"
        f"Total Trades: {platform['total']} | "
        f"Win Rate: {platform['win_rate']}%\n"
        f"Total P/L: {platform['total_pnl_sol']:+.4f} SOL"
    )

    kb = [
        [InlineKeyboardButton("\U0001f4b0 Start Trading", callback_data="trade")],
        [InlineKeyboardButton("\U0001f381 Exchange Deals", callback_data="deals_menu")],
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )




# TOKEN AUDIT (public -- like Trojan, via DexScreener)

async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Public: /audit <token> -- instant token audit via DexScreener."""
    user = get_user(update.effective_user)
    args = context.args
    if not args:
        await update.message.reply_text(
            "\U0001f50d *Token Audit*\n\n"
            "Usage: `/audit <symbol or mint>`\n"
            "Example: `/audit BONK` or `/audit So11...`",
            parse_mode="Markdown",
        )
        return
    query = args[0].strip()
    # Known token mints for common symbols (avoid memecoin confusion)
    _KNOWN_MINTS = {
        "SOL": "So11111111111111111111111111111111111111112",
        "BONK": "DezXAZ8z7PnrnRJjz3wXBNTs2ZmBT5J2ySSd5VqEpump",
        "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "RNDR": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
        "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
        "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
        "WBTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
        "RENDER":"rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
        "MEW":  "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",
        "POPCAT":"7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
        "PENGU": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
        "TRUMP": "6p1xzgVJfydnFP3VQRHRfmu45CCgQ4jE5NMXLhfeN2hN",
        "PEPE": "4Bskt3gjpvZetH1xKpH67qMDbypSFc58rt7NLRADYqWL",
        "FLOKI": "57DxWKEQxn55a7anKiQVaRMjivUQY7dQx9gYFpix9HqG",
        "FARTCOIN":"9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
        "GOAT":"CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
        "PNUT":"2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",
        "GIGA":"63LfDmNb3MQ8mw9MtZ2To9bEA2M71kZUUGq5tiJxcqj9",
    }
    if query.upper() in _KNOWN_MINTS:
        query = _KNOWN_MINTS[query.upper()]
    await update.message.reply_text("\U0001f50d Scanning token...", parse_mode="Markdown")
    try:
        import aiohttp, asyncio
        if len(query) > 30:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{query}"
        else:
            url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        data = None
        for _attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            break
                        if resp.status == 429:
                            await asyncio.sleep(2)
                            continue
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(1)
        if data is None:
            await update.message.reply_text("\u26a0\ufe0f DexScreener unavailable. Try again in a few seconds.")
            return
        pairs = data.get("pairs", [])
        if not pairs:
            await update.message.reply_text(f"\u274c No data for `{query[:30]}`.", parse_mode="Markdown")
            return
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        pair = sol_pairs[0] if sol_pairs else pairs[0]
        base = pair.get("baseToken", {})
        symbol = base.get("symbol", "???")
        name = base.get("name", symbol)
        mint = base.get("address", "-")
        price_usd = pair.get("priceUsd", "0")
        liq = pair.get("liquidity", {}).get("usd", 0)
        vol24 = pair.get("volume", {}).get("h24", 0)
        mc = pair.get("marketCap", 0) or pair.get("fdv", 0)
        chg5m = pair.get("priceChange", {}).get("m5", 0)
        chg1h = pair.get("priceChange", {}).get("h1", 0)
        chg24h = pair.get("priceChange", {}).get("h24", 0)
        txns = pair.get("txns", {})
        buys24 = txns.get("h24", {}).get("buys", 0)
        sells24 = txns.get("h24", {}).get("sells", 0)
        chain = pair.get("chainId", "unknown")
        dex = pair.get("dexId", "unknown")
        pair_url = pair.get("url", "")
        flags = []
        if liq and liq < 10000:
            flags.append("\U0001f534 Low liquidity (<$10K)")
        elif liq and liq < 50000:
            flags.append("\U0001f7e1 Medium liquidity")
        else:
            flags.append("\U0001f7e2 Good liquidity")
        if sells24 > 0 and buys24 > 0:
            ratio = buys24 / sells24
            if ratio < 0.5:
                flags.append("\U0001f534 Heavy sell pressure")
            elif ratio > 2.0:
                flags.append("\U0001f7e2 Strong buy pressure")
        if mc and mc < 50000:
            flags.append("\u26a0\ufe0f Micro-cap (<$50K)")
        flags_text = "\n".join(f"  {f}" for f in flags) if flags else "  \u2705 No major flags"
        text = (
            f"\U0001f50d *Token Audit: {name}* (`{symbol}`)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Chain: `{chain}` | DEX: `{dex}`\n"
            f"Mint: `{mint[:20]}...`\n\n"
            f"\U0001f4b0 Price: `${price_usd}`\n"
            f"\U0001f4ca MCap: `${mc:,.0f}`\n"
            f"\U0001f4a7 Liquidity: `${liq:,.0f}`\n"
            f"\U0001f4c8 Vol 24h: `${vol24:,.0f}`\n\n"
            f"\u23f1 Changes:\n"
            f"  5m: `{chg5m:+.1f}%` | 1h: `{chg1h:+.1f}%` | 24h: `{chg24h:+.1f}%`\n\n"
            f"\U0001f504 Txns 24h: `{buys24}` buys / `{sells24}` sells\n\n"
            f"\U0001f6e1\ufe0f Risk Flags:\n{flags_text}\n"
        )
        kb = []
        if pair_url:
            kb.append([InlineKeyboardButton("\U0001f4ca DexScreener", url=pair_url)])
        if mint and len(mint) > 30:
            kb.append([InlineKeyboardButton(f"\u26a1 Buy {symbol}", callback_data=f"hot_buy_{mint[:50]}")])
        kb.append([_back_main()[0]])
        from core.persistence import track_token_lookup
        track_token_lookup(mint, symbol)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"cmd_audit error: {e}")
        await update.message.reply_text(f"\u26a0\ufe0f Audit failed: `{str(e)[:100]}`", parse_mode="Markdown")




# FORCE TRADE (admin - direct test trade)



async def cmd_copy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Mizar copy trading bots."""
    user = get_user(update.effective_user.id)
    if user["tier"] == "free":
        await update.message.reply_text(
            "Copy Trading is Pro+ only.\n\n/upgrade",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("Fetching traders...")

    try:
        from exchanges.mizar import get_marketplace_bots, get_referral_url
        bots = await get_marketplace_bots(limit=5)
        if not bots:
            await update.message.reply_text("Mizar API down. Try later.")
            return

        text = "Top Copy Traders (30D PnL)\n\n"
        for i, bot in enumerate(bots[:5], 1):
            name = bot.get("name", "?")
            pnl = bot.get("pnl_30d", 0)
            text += f"{i}. {name}: {pnl:+.2f}%\n"

        ref_url = get_referral_url()
        text += f"\n[Start on Mizar]({ref_url})"

        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"cmd_copy: {e}")
        await update.message.reply_text(f"Error: {str(e)[:80]}")






async def cmd_whale_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: start tracking whale wallet (paper trading Week 1)."""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("Admin only.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /whale_track <wallet_address>\n\n"
            "Example: /whale_track 5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
            parse_mode="Markdown",
        )
        return

    wallet = context.args[0].strip()
    if len(wallet) < 32:
        await update.message.reply_text("Invalid Solana wallet address.")
        return

    from exchanges.whale_copy import WHALE_COPY_STATE
    if wallet not in WHALE_COPY_STATE["tracked_wallets"]:
        WHALE_COPY_STATE["tracked_wallets"].append(wallet)

    await update.message.reply_text(
        f"Whale tracking started (PAPER TRADING)\n\n"
        f"Wallet: {wallet[:8]}...\n\n"
        f"Mode: Log only, no real trades\n"
        f"Check /whale_stats for signals",
        parse_mode="Markdown",
    )


async def cmd_whale_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show whale copy trading stats."""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("Admin only.")
        return

    from exchanges.whale_copy import get_whale_stats
    stats = get_whale_stats()

    mode = "PAPER TRADING (Week 1)" if stats["paper_trading"] else "LIVE TRADING"

    text = (
        f"Whale Copy Trading Stats\n\n"
        f"Mode: {mode}\n"
        f"Tracked wallets: {stats['tracked_wallets']}\n"
        f"Signals logged: {stats['signals_logged']}\n"
        f"Would-be PnL: {stats['would_be_pnl_sol']:.4f} SOL\n\n"
        f"Paper trading = signals logged, no real trades.\n"
        f"Use /whale_track <address> to add wallets."
    )

    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch between SOL and BASE networks."""
    user = get_user(update.effective_user.id)
    current = user.get("active_chain", "SOL")
    new_chain = "BASE" if current == "SOL" else "SOL"
    user["active_chain"] = new_chain
    save_users(users)
    await update.message.reply_text(
        f"Network switched to {new_chain}.\n\n"
        f"All trades now route via {new_chain}.",
        parse_mode="Markdown",
    )

async def cmd_dca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """DCA bot info."""
    user = get_user(update.effective_user.id)
    if user["tier"] == "free":
        await update.message.reply_text("DCA Bot is Pro+ only.\n\n/upgrade", parse_mode="Markdown")
        return

    from exchanges.mizar import get_referral_url
    ref_url = get_referral_url()

    text = (
        "DCA Bot (Dollar Cost Averaging)\n\n"
        "Auto-buy at intervals to smooth volatility.\n\n"
        "Features:\n"
        "- Set amount & frequency\n"
        "- Auto-buy dips\n"
        "- Stop-loss & TP\n\n"
        f"[Create on Mizar]({ref_url})"
    )

    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_force_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: force 1 test trade on BONK/WIF/JUP zonder te wachten op signals."""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("Admin only.")
        return

    await update.message.reply_text("Forcing test trade...", parse_mode="Markdown")

    try:
        from zero_loss_manager import execute_trade, _resolve_mint
        from core.wallet import load_keypair
        from core.persistence import load_users

        users = load_users()
        admin_user = users.get(uid)
        if not admin_user or not admin_user.get("wallet_secret_enc"):
            await update.message.reply_text("Wallet missing. /start first.")
            return

        keypair = load_keypair(admin_user["wallet_secret_enc"])

        # Pick token: BONK if available, else WIF, else JUP
        token = "BONK"
        mint = _resolve_mint(token)
        if not mint:
            token = "WIF"
            mint = _resolve_mint(token)
        if not mint:
            token = "JUP"
            mint = _resolve_mint(token)
        if not mint:
            await update.message.reply_text("No tradeable tokens found.")
            return

        # Force 0.1 SOL test trade
        from core.config import SOL_MINT
        sig, out_tokens, err = await execute_trade(keypair, "BUY", SOL_MINT, mint, int(0.1 * 1e9))

        if sig and out_tokens > 0:
            await update.message.reply_text(
                f"FORCE TRADE SUCCESS\n\n"
                f"Token: {token}\n"
                f"Amount: {out_tokens / 1e9:.4f}\n"
                f"Sig: `{sig[:20]}...`",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(f"FORCE TRADE FAILED\n\nError: {err or 'unknown'}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_force_trade error: {e}")
        await update.message.reply_text(f"Error: `{str(e)[:100]}`", parse_mode="Markdown")

# ══════════════════════════════════════════════
# INSPECTOR GADGET — ADMIN COMMANDS
# ══════════════════════════════════════════════

async def cmd_addwallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /addwallet <address> [label] — add an alpha wallet to track."""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/addwallet <solana_address> [label]`\n"
            "Example: `/addwallet 7xKX... CryptoGodJohn`",
            parse_mode="Markdown",
        )
        return

    address = args[0].strip()
    label = " ".join(args[1:]).strip() if len(args) > 1 else address[:8] + "..."

    # Basic Solana address validation (base58, 32-44 chars)
    if not (32 <= len(address) <= 44):
        await update.message.reply_text("❌ Invalid Solana address length.")
        return

    try:
        from agents.inspector_agent import add_alpha_wallet, get_alpha_wallets
        add_alpha_wallet(address, label)
        wallets = get_alpha_wallets()
        await update.message.reply_text(
            f"✅ *Alpha wallet added*\n"
            f"Label: `{label}`\n"
            f"Address: `{address}`\n"
            f"Total tracked: {len(wallets)}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"cmd_addwallet error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /wallets — list all tracked alpha wallets."""
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return

    try:
        from agents.inspector_agent import get_alpha_wallets
        wallets = get_alpha_wallets()
        if not wallets:
            await update.message.reply_text("No alpha wallets tracked yet.\nUse `/addwallet <address> [label]`")
            return

        lines = ["🕵️ *Inspector Gadget — Tracked Wallets*\n━━━━━━━━━━━━━━━━━━━━━\n"]
        for i, (addr, label) in enumerate(wallets.items(), 1):
            short = addr[:6] + "..." + addr[-4:]
            lines.append(f"{i}. *{label}*\n   `{short}`")

        text = "\n".join(lines)
        kb = [[InlineKeyboardButton(
            "🔍 View on Solscan",
            url=f"https://solscan.io/account/{list(wallets.keys())[0]}",
        )]]
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"cmd_list_wallets error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

def _check_critical_env():
    """Verify all critical env vars are present at startup. Alert admin if missing."""
    import os
    CRITICAL = {
        "BOT_TOKEN": BOT_TOKEN,
        "ADMIN_IDS": ADMIN_IDS,
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
        "HUGGINGFACE_TOKEN": os.getenv("HUGGINGFACE_TOKEN", ""),
        "UPSTASH_REDIS_URL": os.getenv("UPSTASH_REDIS_URL", ""),
        "GUMROAD_ACCESS_TOKEN": os.getenv("GUMROAD_ACCESS_TOKEN", ""),
        "NEWSAPI_KEY": os.getenv("NEWSAPI_KEY", ""),
        "CRYPTOPANIC_KEY": os.getenv("CRYPTOPANIC_KEY", ""),
        "HELIUS_API_KEY": os.getenv("HELIUS_API_KEY", ""),
        "ETHERSCAN_API_KEY": os.getenv("ETHERSCAN_API_KEY", ""),
        "WALLET_ENCRYPTION_KEY": os.getenv("WALLET_ENCRYPTION_KEY", ""),
        "FEE_COLLECT_WALLET": os.getenv("FEE_COLLECT_WALLET", ""),
        "ALERT_CHANNEL_ID": os.getenv("ALERT_CHANNEL_ID", ""),
        "JUPITER_API_KEY": os.getenv("JUPITER_API_KEY", ""),
    }
    missing = [k for k, v in CRITICAL.items() if not v]
    if missing:
        logger.critical(f"MISSING ENV VARS: {missing} — bot may malfunction!")
        # Will alert admin via Telegram after bot starts (startup_alert logic)
        return missing
    logger.info(f"Env check OK: {len(CRITICAL)} critical vars present")
    return []


def main() -> None:
    # Python 3.12+ / 3.14+ loop fix
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Add it to .env or environment variables.")
        return

    # Check all critical env vars before starting
    missing_env = _check_critical_env()
    if missing_env:
        logger.critical(f"STARTUP WARNING: Missing {missing_env}")

    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    # VIRAL AGENT: Start the autonomous social proof loop
    try:
        from agents.viral_agent import viral_poster_job
        app.job_queue.run_repeating(viral_poster_job, interval=3600, first=10)
        logger.info("📱 VIRAL AGENT: Loop scheduled (every 1h)")
    except Exception as viral_err:
        logger.error(f"Failed to start Viral Agent: {viral_err}")

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("share", cmd_share))
    app.add_handler(CommandHandler("admin_pause", cmd_admin_pause))
    app.add_handler(CommandHandler("admin_resume", cmd_admin_resume))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("killswitch", cmd_killswitch))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("restore", cmd_restore))
    app.add_handler(CommandHandler("hot", cmd_hot))
    app.add_handler(CommandHandler("trending", cmd_hot))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("policy", cmd_policy))
    app.add_handler(CommandHandler("tweetstats", cmd_tweetstats))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(CommandHandler("analytics", cmd_analytics))
    app.add_handler(CommandHandler("admin_marketing", cmd_admin_marketing))
    app.add_handler(CommandHandler("advisor", cmd_advisor))
    app.add_handler(CommandHandler("advisor_diag", cmd_advisor_diag))
    app.add_handler(CommandHandler("autotrade_diag", cmd_autotrade_diag))
    app.add_handler(CommandHandler("autotrade_test_on", cmd_autotrade_test_on))
    app.add_handler(CommandHandler("autotrade_test_off", cmd_autotrade_test_off))
    app.add_handler(CommandHandler("ai_status", cmd_ai_status))
    app.add_handler(CommandHandler("whale_intel", cmd_whale_intel))
    app.add_handler(CommandHandler("pdca", cmd_pdca))
    app.add_handler(CommandHandler("myip", cmd_myip))
    app.add_handler(CommandHandler("ip_status", cmd_ip_status))
    app.add_handler(CommandHandler("sell_diag", cmd_sell_diag))  # v3.23.22
    # v3.23.24 — Tier-Board mobile companion
    app.add_handler(CommandHandler("admin_status", cmd_admin_status))
    app.add_handler(CommandHandler("admin_bn_add", cmd_admin_bn_add))
    app.add_handler(CommandHandler("admin_bn_list", cmd_admin_bn_list))
    app.add_handler(CommandHandler("admin_bn_close", cmd_admin_bn_close))
    app.add_handler(CommandHandler("qa", cmd_qa))
    app.add_handler(CommandHandler("smoke", cmd_smoke))
    app.add_handler(CommandHandler("sla", cmd_sla))
    app.add_handler(CommandHandler("ops_now", cmd_ops_now))
    app.add_handler(CommandHandler("language", cmd_language))
    # app.add_handler(CommandHandler("admin_studio", cmd_admin_studio)) # TEMPORARY FIX: Disabled until implemented
    app.add_handler(CommandHandler("path", cmd_path))
    app.add_handler(CommandHandler("winrate", cmd_winrate))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("promos", cmd_deals))  # alias
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("top", cmd_leaderboard))  # alias
    app.add_handler(CommandHandler("referrals", cmd_referrals))
    app.add_handler(CommandHandler("ref", cmd_referrals))     # alias
    app.add_handler(CommandHandler("addwallet", cmd_addwallet))    # Inspector: add alpha wallet
    app.add_handler(CommandHandler("wallets", cmd_list_wallets))
    app.add_handler(CommandHandler("force_trade", cmd_force_trade))
    app.add_handler(CommandHandler("copy", cmd_copy))
    app.add_handler(CommandHandler("dca", cmd_dca))
    app.add_handler(CommandHandler("switch", cmd_switch))
    app.add_handler(CommandHandler("whale_track", cmd_whale_track))
    app.add_handler(CommandHandler("whale_stats", cmd_whale_stats))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("scan", cmd_audit))  # alias   # Inspector: list tracked wallets

    # Inline callbacks — whale copy-trade (specific pattern first)
    app.add_handler(CallbackQueryHandler(handle_whale_copy, pattern=r"^wcp_"))
    app.add_handler(CallbackQueryHandler(handle_whale_track, pattern=r"^wtr_"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Document handler — admin can forward backup JSON to auto-restore
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Token address detection — TWO handlers for maximum compatibility
    # Handler 1: explicit TEXT filter (standard text messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token_address))
    # Handler 2: catch messages with entities (URLs, etc.) that TEXT might miss
    app.add_handler(MessageHandler(
        filters.Entity("url") | filters.Entity("text_link") | filters.CaptionEntity("url"),
        handle_token_address,
    ))

    # ── Global PTB error handler: surface ALL silent handler exceptions ───────
    async def _ptb_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Catch and log every unhandled exception from any PTB handler or job."""
        import traceback as _tb
        err_text = "".join(_tb.format_exception(type(context.error), context.error, context.error.__traceback__))
        logger.error(f"[PTB-ERROR] Unhandled handler exception:\n{err_text}")
        # Alert admin so we know exactly what's breaking
        for admin_id in ADMIN_IDS:
            try:
                snippet = str(context.error)[:300]
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ *Bot handler error*\n`{type(context.error).__name__}: {snippet}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    app.add_error_handler(_ptb_error_handler)

    # Whale scanner repeating job
    app.job_queue.run_repeating(
        scan_and_alert,
        interval=SCAN_INTERVAL,
        first=10,
        name="whale_scanner",
    )

    # Conversion AI daily nudge (Cycle 14)
    app.job_queue.run_daily(
        scheduled_conversion_job,
        time=dt_time(hour=9, minute=0, tzinfo=timezone.utc),
        name="conversion_nudge",
    )

    # Daily digest — posts to Discord + TG channel at 20:00 UTC
    app.job_queue.run_daily(
        daily_digest_job,
        time=dt_time(hour=20, minute=0, tzinfo=timezone.utc),
        name="daily_digest",
    )

    # Auto-save every 60s (safety net for crash recovery)
    app.job_queue.run_repeating(
        auto_save_job, interval=60, first=60, name="auto_save",
    )

    # Auto-backup to admin every 30 min (deploy resilience — Render has no persistent disk)
    app.job_queue.run_repeating(
        auto_backup_job, interval=30 * 60, first=300, name="auto_backup",
    )

    # Heartbeat monitor (legacy compact pulse) disabled to prevent duplicate heartbeat spam.
    # Use `system_heartbeat_job` below as single heartbeat channel.

    # SL/TP monitor — checks positions every 15s for stop loss / take profit triggers
    # Fast enough for scalping (-3% SL can trigger quickly)
    app.job_queue.run_repeating(
        sl_tp_monitor_job, interval=15, first=60, name="sl_tp_monitor",
    )

    # Marketing auto-poster — repeating every 4 hours (survives restarts!)
    # run_daily loses schedule on restart; run_repeating always fires
    app.job_queue.run_repeating(
        marketing_job, interval=4 * 3600, first=300, name="marketing_auto",
    )

    # Live scalping monitor — every 30s (price momentum on SOL/BONK/JUP/WIF/RAY/PYTH)
    app.job_queue.run_repeating(
        scalper_job, interval=30, first=60, name="scalper",
    )

    # CEO Agent daily briefing — 08:00 Amsterdam time (UTC+1 winter / UTC+2 summer)
    # Reads all KPIs from Redis, prioritises via Gemini, sends Telegram briefing to Erik
    async def ceo_briefing_job(context) -> None:
        try:
            from agents.ceo_agent import run_briefing
            await run_briefing()
        except Exception as e:
            logger.error(f"CEO briefing job failed: {e}")

    app.job_queue.run_daily(
        ceo_briefing_job,
        time=dt_time(hour=6, minute=0, tzinfo=timezone.utc),  # 08:00 AMS (UTC+2 summer)
        name="ceo_daily_briefing",
    )

    # ── War Watch: geopolitical news scanner (every 10 min) ───────────────────
    async def war_watch_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from agents.news_scanner import scan_once
            signals = await scan_once(bot=context.bot)
            if signals:
                logger.info(f"War Watch: {len(signals)} new signal(s) sent")
        except Exception as e:
            logger.error(f"War Watch job failed: {e}")

    app.job_queue.run_repeating(
        war_watch_job,
        interval=600,   # every 10 minutes
        first=120,      # first run 2 min after startup (let bot settle)
        name="war_watch",
    )

    # ── Zero Loss Manager: autonomous breakeven-lock scalper (24/7) ────────
    _zero_loss_task = None  # Track the background task

    async def zero_loss_start_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start the Zero Loss autonomous trader as a persistent background task."""
        nonlocal _zero_loss_task
        try:
            import asyncio as _aio
            _zero_loss_task = _aio.create_task(auto_trader_loop(bot=context.bot))
            logger.info("🛡️ Zero Loss Manager: 24/7 autonomous trader STARTED")
            # Notify admin
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            "🛡️ *Zero Loss Manager ONLINE*\n"
                            "━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "✅ Grade A signals only\n"
                            "✅ Breakeven lock active\n"
                            "✅ Auto stop-loss / take-profit\n"
                            "✅ 24/7 autonomous execution\n\n"
                            "_All trades reported to this chat._"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Zero Loss Manager start failed: {e}")

    app.job_queue.run_once(
        zero_loss_start_job,
        when=45,  # start 45s after boot (let other systems settle)
        name="zero_loss_start",
    )

    # ── Inspector Gadget: Alpha wallet copy-trade intelligence (every 60s) ─────
    async def _inspector_copy_signal(signal: dict) -> None:
        """Callback: broadcast Inspector copy-trade signal to all alert subscribers."""
        try:
            from agents.inspector_agent import format_inspector_signal
            text = format_inspector_signal(signal)
            mint = signal["mint"]

            kb = [
                [InlineKeyboardButton(
                    "⚡ Copy Trade Now",
                    url=f"https://t.me/{BOT_USERNAME}?start=buy_{mint}",
                )],
                [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}")],
            ]

            # Send to Erik + all admin (signal test phase first)
            for admin_id in ADMIN_IDS:
                try:
                    await app.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            # Also post to alert subscribers (same as whale alerts)
            for uid, udata in list(users.items()):
                if not udata.get("alerts_on"):
                    continue
                try:
                    await app.bot.send_message(
                        chat_id=uid,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Inspector signal dispatch error: {e}")

    async def inspector_gadget_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Inspector Gadget: scan alpha wallets, fire copy-trade signals."""
        try:
            from agents.inspector_agent import inspector_job, register_signal_callback
            register_signal_callback(_inspector_copy_signal)
            results = await inspector_job(context)
            if results:
                logger.info(f"Inspector: {len(results)} signal(s) fired")
        except Exception as e:
            logger.error(f"Inspector job failed: {e}")

    app.job_queue.run_repeating(
        inspector_gadget_job,
        interval=60,   # every 60s — alpha wallets checked every minute
        first=90,      # first run 90s after startup
        name="inspector_gadget",
    )

    # ── Whale Watcher: Grade S signals from legendary wallets (every 90s) ──────
    async def _whale_grade_s_signal(signal: dict) -> None:
        """Callback: broadcast Grade S whale signal to admin + alert subscribers."""
        try:
            from agents.whale_watcher import format_whale_signal
            text = format_whale_signal(signal)
            mint = signal["mint"]

            kb = [
                [InlineKeyboardButton(
                    "🐋 Buy Now — Grade S",
                    url=f"https://t.me/{BOT_USERNAME}?start=buy_{mint}",
                )],
                [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}")],
                [InlineKeyboardButton("🔍 GMGN", url=f"https://gmgn.ai/sol/token/{mint}")],
            ]

            # Admin first (always)
            for admin_id in ADMIN_IDS:
                try:
                    await app.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            # Alert subscribers
            for uid, udata in list(users.items()):
                if not udata.get("alerts_on"):
                    continue
                try:
                    await app.bot.send_message(
                        chat_id=uid,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Whale Grade S signal dispatch error: {e}")

    # Whale scanner runs as asyncio task in post_init (see line ~9846).
    # The job_queue version was removed — it imported a non-existent function.

    # Arbitrage Scanner (Cycle 9)
    app.job_queue.run_repeating(arbitrage_job, interval=60, first=10)

    async def system_heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Periodic status update for admin visibility (Heartbeat)."""
        try:
            from zero_loss_manager import check_market_trend
            trend = await check_market_trend()
            emoji = "\U0001f7e2" if trend >= 0 else "\U0001f534"

            advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
            advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
            endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
            endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))
            advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
            endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0
            advisor_state = "OK" if not RUNTIME_HEALTH.get("advisor_sla_breach") else "BREACH"
            endpoint_state = "OK" if not RUNTIME_HEALTH.get("endpoint_sla_breach") else "BREACH"

            msg = (
                f"\U0001f493 *APEXFLASH HEARTBEAT*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Status: **System Healthy**\n"
                f"{emoji} SOL Trend: **{trend:+.2f}%**\n"
                f"📡 Scanning: **Grade A/B+ active**\n"
                f"🤖 Advisor SLA: **{advisor_sla:.2f}%** ({advisor_state})\n"
                f"🌐 Endpoint SLA: **{endpoint_sla:.2f}%** ({endpoint_state})\n"
                f"\n"
                f"_Bot is monitoring markets 24/7._"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=msg, parse_mode="Markdown")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Heartbeat failed: {e}")

    app.job_queue.run_repeating(
        system_heartbeat_job,
        interval=14400, # every 4 hours
        first=300,      # first run 5 min after startup
        name="heartbeat_job",
    )

    integrity_last_ok = RUNTIME_HEALTH.get("integrity_ok")

    async def runtime_integrity_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        nonlocal integrity_last_ok
        try:
            snap = _runtime_integrity_snapshot()
            current_ok = bool(snap.get("ok"))

            RUNTIME_HEALTH["integrity_ok"] = current_ok
            RUNTIME_HEALTH["integrity_missing_env"] = snap.get("missing_env", [])
            RUNTIME_HEALTH["integrity_affiliate_invalid"] = snap.get("affiliate_invalid", [])
            RUNTIME_HEALTH["last_integrity_ts"] = str(snap.get("ts") or "")
            _save_runtime_health()

            if integrity_last_ok is None or integrity_last_ok != current_ok:
                if current_ok:
                    text = (
                        "✅ *Runtime Integrity: OK*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "Critical env + affiliate/referral config are valid."
                    )
                else:
                    lines = []
                    for k in (snap.get("missing_env", []) or [])[:8]:
                        lines.append(f"• missing env: `{k}`")
                    for k in (snap.get("affiliate_invalid", []) or [])[:8]:
                        lines.append(f"• affiliate: `{k}`")
                    text = (
                        "⚠️ *Runtime Integrity: ISSUES*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        + ("\n".join(lines) if lines else "Unknown integrity issue")
                    )

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                    except Exception:
                        pass

            integrity_last_ok = current_ok
        except Exception as e:
            logger.warning(f"runtime_integrity_job failed: {e}")

    app.job_queue.run_repeating(
        runtime_integrity_job,
        interval=21600,  # every 6 hours
        first=120,       # first run 2 min after startup
        name="runtime_integrity",
    )

    # Advisor runtime watchdog — checks AI health every 30 min and only alerts on state changes
    advisor_probe_last_ok = RUNTIME_HEALTH.get("advisor_ok")
    _gemini_key_invalid_alerted = False  # send only once per boot until key is fixed

    async def advisor_watchdog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        nonlocal advisor_probe_last_ok, _gemini_key_invalid_alerted
        try:
            from agents.advisor_agent import advisor_live_probe
            probe = await advisor_live_probe()
            current_ok = bool(probe.get("ok"))
            reason_str = str(probe.get("reason") or "")

            # Immediate alert if Gemini key is permanently invalid (API_KEY_INVALID)
            # This is distinct from transient failures — requires human action.
            if "API_KEY_INVALID" in reason_str and not _gemini_key_invalid_alerted:
                _gemini_key_invalid_alerted = True
                key_alert = (
                    "🔑 *ACTIE VEREIST — Gemini API key INVALIDE*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "Google weigert de key. Bot draait nu op *DeepSeek fallback*.\n\n"
                    "Fix:\n"
                    "1. Ga naar aistudio.google.com/apikey\n"
                    "2. Maak nieuwe key aan\n"
                    "3. Update `MASTER_ENV_APEXFLASH.txt` + `sync_render_env.py:66`\n"
                    "4. Run: `python sync_render_env.py`"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=key_alert, parse_mode="Markdown")
                    except Exception:
                        pass
            elif "API_KEY_INVALID" not in reason_str:
                _gemini_key_invalid_alerted = False  # reset if key becomes valid again
            RUNTIME_HEALTH["last_watchdog_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            RUNTIME_HEALTH["advisor_ok"] = current_ok
            RUNTIME_HEALTH["advisor_reason"] = reason_str
            RUNTIME_HEALTH["advisor_model"] = str(probe.get("model") or "")
            RUNTIME_HEALTH["advisor_checks_total"] = int(RUNTIME_HEALTH.get("advisor_checks_total", 0)) + 1
            if current_ok:
                RUNTIME_HEALTH["advisor_checks_ok"] = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0)) + 1

            advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
            advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
            advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
            prev_breach = bool(RUNTIME_HEALTH.get("advisor_sla_breach"))
            curr_breach = advisor_total >= 10 and advisor_sla < 99.9
            RUNTIME_HEALTH["advisor_sla_breach"] = curr_breach

            if curr_breach != prev_breach:
                if curr_breach:
                    sla_text = (
                        "🚨 *Advisor SLA BREACH*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Window: `{advisor_ok_count}/{advisor_total}` ({advisor_sla:.2f}%)\n"
                        "Target: `99.90%`"
                    )
                else:
                    sla_text = (
                        "✅ *Advisor SLA RECOVERED*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Window: `{advisor_ok_count}/{advisor_total}` ({advisor_sla:.2f}%)"
                    )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=sla_text, parse_mode="Markdown")
                    except Exception:
                        pass

            # Notify only on first run or when state changes (LEAN: avoid noisy spam)
            if advisor_probe_last_ok is None or advisor_probe_last_ok != current_ok:
                if current_ok:
                    text = (
                        "✅ *Advisor Watchdog: RECOVERED*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Model: `{probe.get('model')}`"
                    )
                else:
                    text = (
                        "⚠️ *Advisor Watchdog: FALLBACK ACTIVE*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Reason: `{probe.get('reason', 'unknown')}`"
                    )

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                    except Exception:
                        pass

            advisor_probe_last_ok = current_ok
            _record_sla_history("advisor_watchdog")
            _save_runtime_health()
        except Exception as e:
            logger.warning(f"advisor_watchdog_job failed: {e}")

    app.job_queue.run_repeating(
        advisor_watchdog_job,
        interval=1800,  # every 30 minutes
        first=180,      # first check after 3 minutes
        name="advisor_watchdog",
    )

    # Production endpoint watchdog — verifies key app/telegram links and alerts on state changes only.
    endpoint_watchdog_last_ok = RUNTIME_HEALTH.get("endpoint_ok")
    endpoint_watchdog_urls = [
        WEBSITE_URL,
        f"{WEBSITE_URL}/api/events?hours=24&latest=1",
        f"{WEBSITE_URL}/api/subscribe",
        f"https://t.me/{BOT_USERNAME}",
        f"https://t.me/{BOT_USERNAME}?start=elite",
    ]

    async def endpoint_watchdog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        nonlocal endpoint_watchdog_last_ok
        try:
            results = []
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                for url in endpoint_watchdog_urls:
                    ok = False
                    status = 0
                    try:
                        async with session.get(url, allow_redirects=True) as resp:
                            status = resp.status
                            ok = 200 <= status < 400
                    except Exception:
                        ok = False
                    results.append((url, ok, status))

            all_ok = all(item[1] for item in results)
            RUNTIME_HEALTH["endpoint_ok"] = all_ok
            RUNTIME_HEALTH["endpoint_failed"] = [f"• `{u}` → {s if s else 'ERR'}" for u, ok, s in results if not ok][:8]
            RUNTIME_HEALTH["last_watchdog_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            RUNTIME_HEALTH["endpoint_checks_total"] = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0)) + 1
            if all_ok:
                RUNTIME_HEALTH["endpoint_checks_ok"] = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0)) + 1

            endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
            endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))
            endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0
            prev_ep_breach = bool(RUNTIME_HEALTH.get("endpoint_sla_breach"))
            curr_ep_breach = endpoint_total >= 10 and endpoint_sla < 99.9
            RUNTIME_HEALTH["endpoint_sla_breach"] = curr_ep_breach

            if curr_ep_breach != prev_ep_breach:
                if curr_ep_breach:
                    sla_text = (
                        "🚨 *Endpoint SLA BREACH*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Window: `{endpoint_ok_count}/{endpoint_total}` ({endpoint_sla:.2f}%)\n"
                        "Target: `99.90%`"
                    )
                else:
                    sla_text = (
                        "✅ *Endpoint SLA RECOVERED*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Window: `{endpoint_ok_count}/{endpoint_total}` ({endpoint_sla:.2f}%)"
                    )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=sla_text, parse_mode="Markdown")
                    except Exception:
                        pass

            # Notify only on first run or when aggregate health changes.
            if endpoint_watchdog_last_ok is None or endpoint_watchdog_last_ok != all_ok:
                if all_ok:
                    text = (
                        "✅ *Endpoint Watchdog: ALL GREEN*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "Core app/API/Telegram endpoints are reachable."
                    )
                else:
                    failed = [f"• `{u}` → {s if s else 'ERR'}" for u, ok, s in results if not ok]
                    text = (
                        "⚠️ *Endpoint Watchdog: FAILURE*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        + "\n".join(failed[:8])
                    )

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                    except Exception:
                        pass

            endpoint_watchdog_last_ok = all_ok
            _record_sla_history("endpoint_watchdog")
            _save_runtime_health()
        except Exception as e:
            logger.warning(f"endpoint_watchdog_job failed: {e}")

    app.job_queue.run_repeating(
        endpoint_watchdog_job,
        interval=1800,  # every 30 minutes
        first=240,      # first check after 4 minutes
        name="endpoint_watchdog",
    )

    # Autonomous ops check — runs /sla + /smoke + /advisor_diag equivalent and pushes summary.
    async def ops_autocheck_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        if RUNTIME_HEALTH.get("ops_running"):
            logger.info("ops_autocheck skipped: another ops cycle is running")
            return

        RUNTIME_HEALTH["ops_running"] = True
        RUNTIME_HEALTH["last_ops_status"] = "running"
        RUNTIME_HEALTH["last_ops_error"] = ""
        try:
            from agents.advisor_agent import advisor_live_probe

            # --- advisor probe (advisor_diag equivalent) ---
            probe = await advisor_live_probe()
            advisor_ok = bool(probe.get("ok"))
            RUNTIME_HEALTH["advisor_ok"] = advisor_ok
            RUNTIME_HEALTH["advisor_reason"] = str(probe.get("reason") or "")
            RUNTIME_HEALTH["advisor_model"] = str(probe.get("model") or "")
            RUNTIME_HEALTH["advisor_checks_total"] = int(RUNTIME_HEALTH.get("advisor_checks_total", 0)) + 1
            if advisor_ok:
                RUNTIME_HEALTH["advisor_checks_ok"] = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0)) + 1

            # --- endpoint probe (smoke equivalent) ---
            results = []
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                for url in endpoint_watchdog_urls:
                    ok = False
                    status = 0
                    try:
                        async with session.get(url, allow_redirects=True) as resp:
                            status = resp.status
                            ok = 200 <= status < 400
                    except Exception:
                        ok = False
                    results.append((url, ok, status))

            endpoint_ok = all(item[1] for item in results)
            RUNTIME_HEALTH["endpoint_ok"] = endpoint_ok
            RUNTIME_HEALTH["endpoint_failed"] = [f"• `{u}` → {s if s else 'ERR'}" for u, ok, s in results if not ok][:8]
            RUNTIME_HEALTH["endpoint_checks_total"] = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0)) + 1
            if endpoint_ok:
                RUNTIME_HEALTH["endpoint_checks_ok"] = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0)) + 1

            now_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            RUNTIME_HEALTH["last_smoke_ts"] = now_stamp
            RUNTIME_HEALTH["last_watchdog_ts"] = now_stamp
            RUNTIME_HEALTH["last_ops_autocheck_ts"] = now_stamp

            # --- sla summary (sla equivalent) ---
            advisor_total = int(RUNTIME_HEALTH.get("advisor_checks_total", 0))
            advisor_ok_count = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0))
            endpoint_total = int(RUNTIME_HEALTH.get("endpoint_checks_total", 0))
            endpoint_ok_count = int(RUNTIME_HEALTH.get("endpoint_checks_ok", 0))
            advisor_sla = (advisor_ok_count / advisor_total * 100.0) if advisor_total else 0.0
            endpoint_sla = (endpoint_ok_count / endpoint_total * 100.0) if endpoint_total else 0.0

            text = (
                "🛰️ *ApexFlash Auto Ops Check*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"Advisor: {'✅ online' if advisor_ok else '⚠️ fallback'}\n"
                f"Endpoints: {'✅ healthy' if endpoint_ok else '⚠️ issues'}\n"
                f"Model: `{RUNTIME_HEALTH.get('advisor_model', '') or '-'}`\n"
                f"Fallback reason: `{RUNTIME_HEALTH.get('advisor_reason', '') or '-'}`\n"
                f"Advisor SLA: `{advisor_ok_count}/{advisor_total}` ({advisor_sla:.2f}%)\n"
                f"Endpoint SLA: `{endpoint_ok_count}/{endpoint_total}` ({endpoint_sla:.2f}%)\n"
                f"Checked at: `{now_stamp}`"
            )

            if RUNTIME_HEALTH["endpoint_failed"]:
                text += "\n\n❌ Failed:\n" + "\n".join(RUNTIME_HEALTH["endpoint_failed"][:6])

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                except Exception:
                    pass
            RUNTIME_HEALTH["last_ops_status"] = "ok"
            _record_sla_history("ops_autocheck")
            _save_runtime_health()
        except Exception as e:
            RUNTIME_HEALTH["last_ops_status"] = "failed"
            RUNTIME_HEALTH["last_ops_error"] = str(e)
            logger.warning(f"ops_autocheck_job failed: {e}")
            _record_sla_history("ops_autocheck_error")
            _save_runtime_health()
        finally:
            RUNTIME_HEALTH["ops_running"] = False
            _save_runtime_health()

    app.job_queue.run_repeating(
        ops_autocheck_job,
        interval=7200,  # every 2 hours
        first=420,      # first check after 7 minutes
        name="ops_autocheck",
    )

    # Also trigger one early autonomous ops cycle shortly after startup.
    app.job_queue.run_once(
        ops_autocheck_job,
        when=90,        # first full check after 90 seconds
        name="ops_autocheck_bootstrap",
    )

    # Daily self-check report with day-over-day KPI drift (LEAN/KAIZEN).
    async def daily_self_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            yesterday_key = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            snapshots = RUNTIME_HEALTH.get("daily_kpi_snapshots", {})
            if not isinstance(snapshots, dict):
                snapshots = {}

            current = _build_daily_kpi_snapshot()
            previous = snapshots.get(yesterday_key)
            previous_volume = None
            if isinstance(previous, dict) and previous.get("volume_total_usd") is not None:
                try:
                    raw_prev_volume = previous.get("volume_total_usd")
                    if isinstance(raw_prev_volume, (int, float, str)):
                        previous_volume = round(float(raw_prev_volume), 2)
                except Exception:
                    previous_volume = None

            snapshots[today_key] = current
            # Keep only latest N days.
            keep_keys = sorted(snapshots.keys())[-DAILY_KPI_HISTORY_MAX_DAYS:]
            snapshots = {k: snapshots[k] for k in keep_keys}
            RUNTIME_HEALTH["daily_kpi_snapshots"] = snapshots
            _save_runtime_health()

            drift_hits = _drift_signals(current, previous if isinstance(previous, dict) else None)
            is_drift_alert = len(drift_hits) > 0
            prev_drift_state = bool(RUNTIME_HEALTH.get("daily_drift_alert_active"))
            RUNTIME_HEALTH["daily_drift_alert_active"] = is_drift_alert
            if is_drift_alert:
                RUNTIME_HEALTH["last_daily_drift_alert_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            _save_runtime_health()

            text = (
                "📅 *Daily Self-Check (KPI Drift)*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"Date: `{today_key}`\n"
                + _delta_line("Users", current["users_total"], previous.get("users_total") if isinstance(previous, dict) else None)
                + "\n"
                + _delta_line("Wallets", current["wallets_total"], previous.get("wallets_total") if isinstance(previous, dict) else None)
                + "\n"
                + _delta_line("Trades total", current["trades_total"], previous.get("trades_total") if isinstance(previous, dict) else None)
                + "\n"
                + _delta_line(
                    "Volume total",
                    round(float(current["volume_total_usd"]), 2),
                    previous_volume,
                    " USD",
                )
                + "\n"
                + _delta_line("Advisor SLA", current["advisor_sla"], previous.get("advisor_sla") if isinstance(previous, dict) else None, "%")
                + "\n"
                + _delta_line("Endpoint SLA", current["endpoint_sla"], previous.get("endpoint_sla") if isinstance(previous, dict) else None, "%")
            )

            if is_drift_alert:
                text += "\n\n🚨 *Drift Escalation Triggered*\n" + "\n".join(drift_hits)
            elif prev_drift_state:
                text += "\n\n✅ *Drift state recovered* (back within thresholds)."

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"daily_self_check_job failed: {e}")

    app.job_queue.run_daily(
        daily_self_check_job,
        time=dt_time(hour=5, minute=45, tzinfo=timezone.utc),  # 07:45 Amsterdam (summer)
        name="daily_self_check",
    )

    logger.info(f"\u26a1 ApexFlash MEGA BOT v{VERSION} starting (Infinity Engine + The Agency Gateway)...")
    logger.info(f"\U0001f4e1 Scan interval: {SCAN_INTERVAL}s | Digest: 20:00 UTC")
    logger.info(f"\U0001f451 Admin IDs: {ADMIN_IDS}")
    logger.info(f"\U0001f40b Tracking {len(ETH_WHALE_WALLETS)} ETH + {len(SOL_WHALE_WALLETS)} SOL wallets")

    # Startup notification to channel
    async def post_init(application: Application) -> None:
        # Set persistent "/" menu commands (visible to all users)
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("help", "How to use ApexFlash"),
                BotCommand("myid", "Show your Telegram ID"),
            ])
            logger.info("✅ Menu commands set")
        except Exception as e:
            logger.warning(f"set_my_commands failed: {e}")

        # Advisor runtime health probe (Gemini availability) for fast PDCA visibility.
        try:
            from agents.advisor_agent import advisor_live_probe

            probe = await advisor_live_probe()
            probe_ok = bool(probe.get("ok"))

            # Seed runtime health snapshot immediately after startup.
            RUNTIME_HEALTH["advisor_ok"] = probe_ok
            RUNTIME_HEALTH["advisor_reason"] = str(probe.get("reason") or "")
            RUNTIME_HEALTH["advisor_model"] = str(probe.get("model") or "")
            RUNTIME_HEALTH["advisor_checks_total"] = int(RUNTIME_HEALTH.get("advisor_checks_total", 0)) + 1
            if probe_ok:
                RUNTIME_HEALTH["advisor_checks_ok"] = int(RUNTIME_HEALTH.get("advisor_checks_ok", 0)) + 1
            RUNTIME_HEALTH["last_watchdog_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            _record_sla_history("startup_probe")
            _save_runtime_health()

            if probe.get("ok"):
                text = (
                    "🤖 *Advisor Probe: ONLINE*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Model: `{probe.get('model')}`\n"
                    f"Preview: `{str(probe.get('preview', ''))[:90]}`"
                )
            else:
                text = (
                    "⚠️ *Advisor Probe: FALLBACK MODE*\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Reason: `{probe.get('reason', 'unknown')}`"
                )

            for admin_id in ADMIN_IDS:
                try:
                    await application.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"advisor_live_probe on startup failed: {e}")

        # CRITICAL: Alert admin if data was lost on restart
        if not users:
            for admin_id in ADMIN_IDS:
                try:
                    await application.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            "\u26a0\ufe0f *DATA LOST — Render restart detected*\n\n"
                            "Users: 0 | Wallets: 0\n\n"
                            "\U0001f504 *To restore:* Forward the latest backup "
                            "JSON file to this chat.\n\n"
                            "_The bot will auto-restore all wallets and user data._"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
            logger.warning("NO USER DATA — sent restore request to admins")

        if ALERT_CHANNEL_ID:
            try:
                await application.bot.send_message(
                    chat_id=ALERT_CHANNEL_ID,
                    text=(
                        f"\u26a1 *ApexFlash MEGA BOT Godmode Infinity (v{VERSION}) is LIVE*\n\n"
                        "\u2705 All systems operational\n"
                        "\u2705 Whale tracking active\n"
                        "\u2705 Trading engine ready\n"
                        "\u2705 SL/TP monitor active (30s)\n"
                        "\u2705 Auto-backup every 30 min\n"
                        "\u2705 Marketing auto-poster scheduled\n"
                        "\u2705 Zero Loss Manager (24/7 autonomous)\n"
                        "\u2705 War Watch (geopolitics scanner)\n"
                        "\u2705 CEO Agent (daily briefing)"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Startup notification failed: {e}")

        # 🚀 START GODMODE AGENTS
        try:
            # CEO Agent Scheduler (Daily 08:00 Amsterdam)
            start_ceo_scheduler(application.job_queue.scheduler)
            logger.info("🤖 CEO Agent: scheduler hooked to JobQueue")

            # Marketing Agency: async Redis queue consumer for discord/twitter tasks
            from agents.marketing_agency import agency_loop
            asyncio.ensure_future(agency_loop())
            logger.info("📣 Marketing Agency: background worker STARTED")

            # 🐋 Whale Intelligence v2.0 — GMGN Smart Money Scanner
            from agents.whale_watcher import (
                whale_scan_loop, register_signal_callback, format_whale_signal,
                get_top_whale_wallets, store_signal_for_callback, COPY_TRADE_SOL,
            )
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            from agents.trade_journal import log_signal as journal_log, outcome_check_loop
            asyncio.ensure_future(outcome_check_loop())
            logger.info("📊 PDCA Trade Journal: outcome checker STARTED")

            async def _whale_signal_to_telegram(sig: dict):
                """Forward whale signals: journal + Telegram (with copy-trade buttons) + Twitter + Discord."""
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: journal_log(sig))

                # Fetch top whale wallets (non-blocking, best-effort)
                wallets = []
                if sig.get("grade") in ("A", "S") and sig.get("source", "").startswith("GMGN"):
                    try:
                        wallets = await loop.run_in_executor(
                            None, lambda: get_top_whale_wallets(sig["mint"], limit=3)
                        )
                    except Exception:
                        pass

                # Store signal in Redis for callback lookup
                short = await loop.run_in_executor(
                    None, lambda: store_signal_for_callback(sig, wallets)
                )

                # Build inline keyboard with copy-trade + solscan buttons
                mint = sig.get("mint", "")
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            f"🤖 Copy Buy {COPY_TRADE_SOL} SOL",
                            callback_data=f"wcp_{short}"
                        ),
                        InlineKeyboardButton(
                            "📊 Chart ↗",
                            url=f"https://dexscreener.com/solana/{mint}"
                        ),
                    ],
                ])
                if wallets:
                    w0_addr = wallets[0].get("wallet_address") or wallets[0].get("address", "")
                    if w0_addr:
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(
                                    f"🤖 Copy Buy {COPY_TRADE_SOL} SOL",
                                    callback_data=f"wcp_{short}"
                                ),
                                InlineKeyboardButton(
                                    "📊 Chart ↗",
                                    url=f"https://dexscreener.com/solana/{mint}"
                                ),
                            ],
                            [
                                InlineKeyboardButton(
                                    f"👁 Track Lead Whale",
                                    callback_data=f"wtr_{w0_addr[:14]}"
                                ),
                                InlineKeyboardButton(
                                    "🔍 Solscan ↗",
                                    url=f"https://solscan.io/account/{w0_addr}"
                                ),
                            ],
                        ])

                try:
                    text = format_whale_signal(sig, wallets)
                    if ALERT_CHANNEL_ID:
                        await application.bot.send_message(
                            chat_id=ALERT_CHANNEL_ID,
                            text=text,
                            parse_mode="Markdown",
                            reply_markup=keyboard,
                            disable_web_page_preview=True,
                        )
                    if sig["grade"] == "S":
                        for admin_id in ADMIN_IDS:
                            try:
                                await application.bot.send_message(
                                    chat_id=admin_id,
                                    text=f"🚨 GRADE S AUTO-SIGNAL\n{text}",
                                    parse_mode="Markdown",
                                    reply_markup=keyboard,
                                    disable_web_page_preview=True,
                                )
                            except Exception:
                                pass
                except Exception as e:
                    logger.error(f"Whale Telegram dispatch error: {e}")

                if TWITTER_ENABLED and TWITTER_API_KEY and sig.get("grade") in ("A", "S"):
                    try:
                        from agents.twitter_poster import post_whale_signal_tweet
                        await post_whale_signal_tweet(
                            TWITTER_API_KEY, TWITTER_API_SECRET,
                            TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
                            sig,
                        )
                    except Exception as e:
                        logger.warning(f"Whale Twitter post error (non-critical): {e}")

                if sig.get("grade") in ("A", "S"):
                    try:
                        from agents.notifications import notify_discord_gmgn_signal
                        await notify_discord_gmgn_signal(sig)
                    except Exception as e:
                        logger.warning(f"Whale Discord post error (non-critical): {e}")

            register_signal_callback(_whale_signal_to_telegram)
            asyncio.ensure_future(whale_scan_loop())
            logger.info("🐋 Whale Intelligence v2.0: GMGN scanner STARTED")

        except Exception as e:
            logger.error(f"Godmode Agent activation failed: {e}")

    app.post_init = post_init
    # ── Gumroad Revenue Sync: Poll for new sales (every 15 min) ───────────────
    async def gumroad_sync_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Poll Gumroad for recent sales and sync to KPI tracking."""
        try:
            from gumroad import get_recent_sales
            from core.persistence import (
                is_purchase_synced, 
                mark_purchase_synced, 
                track_paid_conversion, 
                track_revenue,
                get_tier_from_product_id,
                _get_redis
            )
            
            sales = await get_recent_sales(page=1)
            if not sales:
                return

            new_count = 0
            for sale in sales:
                purchase_id = sale.get("id")
                product_id = sale.get("product_id")
                
                if not purchase_id or is_purchase_synced(purchase_id):
                    continue
                
                # New sale detected!
                if not product_id:
                    continue

                tier = get_tier_from_product_id(str(product_id))
                if tier == "unknown":
                    continue
                
                # 1. Track in Redis
                raw_price_cents = sale.get("price", 0)
                try:
                    price = float(raw_price_cents or 0) / 100.0  # cents to dollars
                except Exception:
                    price = 0.0
                track_paid_conversion(0, tier) 
                track_revenue(price)
                mark_purchase_synced(purchase_id)
                new_count += 1
                
                # 2. Get Progress Data
                r = _get_redis()
                total_usd = float(r.get("kpi:total_revenue_usd") or 0) if r else price
                total_eur = total_usd * 0.92  # Approx conversion for €1M goal progress
                progress_pct = (total_eur / 1_000_000) * 100

                # 3. Notify Admin
                currency = sale.get("currency", "USD")
                formatted_price = f"{price:,.2f} {currency}"
                
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"💰 <b>NEW GUMROAD SALE!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"Tier: <b>{tier.upper()}</b>\n"
                                f"Amount: <b>{formatted_price}</b>\n"
                                f"Product: <i>{sale.get('product_name', 'Unknown')}</i>\n\n"
                                f"📈 <b>Progress to €1,000,000:</b>\n"
                                f"Total: <b>€{total_eur:,.2f}</b> ({progress_pct:.4f}%)\n\n"
                                f"🚀 <i>Every sale counts! Godmode active.</i>"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                # 4. Push to marketing queue → Discord auto-broadcast
                if r:
                    import json as _json
                    discord_msg = (
                        f"💰 **NEW SALE — {tier.upper()}**\n"
                        f"Amount: **{formatted_price}**\n"
                        f"Product: {sale.get('product_name', 'Unknown')}\n"
                        f"Progress to €1M: **€{total_eur:,.2f}** ({progress_pct:.4f}%)\n"
                        f"🚀 Godmode active."
                    )
                    r.lpush("queue:marketing", _json.dumps({
                        "action": "discord_alert",
                        "data": {"msg": discord_msg},
                    }))

            if new_count > 0:
                logger.info(f"Gumroad Sync: {new_count} new sales synced to Redis")
        except Exception as e:
            logger.error(f"Gumroad sync job failed: {e}")

    app.job_queue.run_repeating(
        gumroad_sync_job,
        interval=900,   # every 15 minutes
        first=60,       # first run 1 min after startup
        name="gumroad_sync",
    )

    # ── Startup: IP change-detection + history + GMGN escalation ────────────
    async def _startup_ip_report(context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Fire 30s after boot. Detect IP rotation vs previous boot, maintain
        rolling history of last 10 IPs, alert admin CRITICAL on change.
        """
        try:
            async with aiohttp.ClientSession() as _ses:
                async with _ses.get(
                    "https://api.ipify.org?format=json",
                    headers={"User-Agent": "ApexFlash/1.0"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as _r:
                    ip = (await _r.json()).get("ip", "unknown")
        except Exception as _e:
            ip = f"error: {_e}"

        from core.persistence import _get_redis
        r = _get_redis()
        prev_ip = None
        changed = False
        if r:
            try:
                prev_ip_raw = r.get("apexflash:render:ip_previous")
                prev_ip = prev_ip_raw.decode() if isinstance(prev_ip_raw, bytes) else prev_ip_raw
            except Exception:
                prev_ip = None
            changed = bool(prev_ip and prev_ip != ip and not ip.startswith("error"))
            try:
                r.setex("apexflash:render:outbound_ip", 7200, ip)
                if not ip.startswith("error"):
                    r.set("apexflash:render:ip_previous", ip)
                    import time as _t
                    ts = int(_t.time())
                    r.lpush("apexflash:render:ip_history", f"{ip}|{ts}")
                    r.ltrim("apexflash:render:ip_history", 0, 9)
            except Exception as _re:
                logger.error(f"IP report Redis write failed: {_re}")

        if changed:
            header = "🚨 *RENDER IP CHANGED — ACTION REQUIRED*"
            body = (
                f"Previous: `{prev_ip}`\n"
                f"New:      `{ip}`\n\n"
                f"⚠️ GMGN whale scanner will 403 until whitelist updated.\n\n"
                f"📋 *FIX NOW:*\n"
                f"1. gmgn.ai → Profile → API Settings → Trusted IPs\n"
                f"2. Add: `{ip}`\n"
                f"3. Remove stale: `{prev_ip}`"
            )
        else:
            header = "🌐 *Render IP — startup report*"
            suffix = " _(unchanged)_" if prev_ip == ip else ""
            body = (
                f"Outbound IP: `{ip}`{suffix}\n\n"
                f"📋 *GMGN whitelist action (if not yet added):*\n"
                f"gmgn.ai → Profile → API Settings → Trusted IPs → Add `{ip}`"
            )

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"{header}\n{body}",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

    app.job_queue.run_once(_startup_ip_report, when=30, name="startup_ip_report")

    # ── Periodic: escalate GMGN 403 floods to admin ──────────────────────────
    async def _gmgn_403_escalate_check(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Every 60s: if gmgn_market.py raised the escalate flag, alert admin once."""
        try:
            from core.persistence import _get_redis
            r = _get_redis()
            if not r:
                return
            flag = r.get("apexflash:gmgn:403_escalate")
            if not flag:
                return
            bad_ip = flag.decode() if isinstance(flag, bytes) else flag
            try:
                cnt_raw = r.get("apexflash:gmgn:403_count_total") or b"0"
                cnt = int(cnt_raw.decode() if isinstance(cnt_raw, bytes) else cnt_raw)
            except Exception:
                cnt = 0
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🚨 *GMGN 403 STORM*\n"
                            f"IP rejected: `{bad_ip}`\n"
                            f"403 count (1h): {cnt}\n\n"
                            f"📋 Whitelist `{bad_ip}` on gmgn.ai NOW.\n"
                            f"Whale scanner is degraded until fixed."
                        ),
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass
            r.delete("apexflash:gmgn:403_escalate")
        except Exception as _e:
            logger.error(f"gmgn 403 escalate check failed: {_e}")

    app.job_queue.run_repeating(
        _gmgn_403_escalate_check,
        interval=60,
        first=90,
        name="gmgn_403_escalate",
    )

    # ── Direct httpx polling loop — bypasses PTB run_polling() Python 3.14 issues ──
    import asyncio as _asyncio
    import httpx as _httpx
    from telegram import Update as _Update

    async def _direct_poll_loop():
        """
        Raw getUpdates loop — never returns under normal operation.
        PTB app.process_update() dispatches to all registered handlers.
        """
        await app.initialize()
        await app.start()
        logger.info("[POLL] Direct polling loop started (Python 3.14 compat mode)")
        offset = None
        consecutive_errors = 0

        # Drop pending updates (skip backlog)
        async with _httpx.AsyncClient(timeout=5) as _c:
            try:
                _r = await _c.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                    params={"offset": -1, "limit": 1, "timeout": 0},
                )
                _d = _r.json()
                if _d.get("ok") and _d["result"]:
                    offset = _d["result"][-1]["update_id"] + 1
                    logger.info(f"[POLL] Skipped pending updates, offset={offset}")
            except Exception:
                pass

        _poll_count = 0
        async with _httpx.AsyncClient(timeout=50) as client:
            while True:
                try:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                        params={
                            "offset": offset,
                            "timeout": 25,
                            "allowed_updates": '["message","callback_query"]',
                        },
                        timeout=40,  # 15s margin over Telegram's 25s long-poll
                    )
                    data = resp.json()
                    consecutive_errors = 0
                    _poll_count += 1

                    if not data.get("ok"):
                        desc = data.get("description", "")
                        if "Conflict" in desc or "409" in str(resp.status_code):
                            # Another instance is already polling (Render zero-downtime deploy).
                            # Sleep and retry once — if still conflict, exit cleanly so Render
                            # does NOT restart this old instance and assign a new IP.
                            logger.warning(f"[POLL] CONFLICT detected: {desc} — waiting 20s before clean exit")
                            await _asyncio.sleep(20)
                            import sys as _sys
                            _sys.exit(0)
                        logger.warning(f"[POLL] Non-ok response: {data}")
                        await _asyncio.sleep(5)
                        continue

                    updates = data.get("result", [])
                    if updates:
                        logger.info(f"[POLL] #{_poll_count}: {len(updates)} update(s) received")
                    for raw_upd in updates:
                        upd_id = raw_upd.get("update_id")
                        msg = raw_upd.get("message", {})
                        cmd_text = msg.get("text", "")[:60] if msg else ""
                        logger.info(f"[POLL] Processing update {upd_id}: {cmd_text!r}")
                        try:
                            upd = _Update.de_json(raw_upd, app.bot)
                            await app.process_update(upd)
                            logger.info(f"[POLL] Update {upd_id} dispatched OK")
                        except Exception as pe:
                            logger.error(f"[POLL] process_update error for {upd_id}: {pe}", exc_info=True)
                        offset = upd_id + 1

                except RuntimeError:
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"[POLL] Error #{consecutive_errors}: {type(e).__name__}: {e}")
                    if consecutive_errors > 20:
                        raise RuntimeError(f"[POLL] Too many consecutive errors: {e}")
                    await _asyncio.sleep(min(5 * consecutive_errors, 60))

    _asyncio.run(_direct_poll_loop())
    raise RuntimeError("Direct poll loop exited — crashing for Render restart")


if __name__ == "__main__":
    import os as _os
    import time as _time
    import traceback
    import httpx

    def _send_crash_report(msg: str):
        """Send crash report to admin via Telegram."""
        try:
            _tok = _os.getenv("BOT_TOKEN", "")
            _admin = _os.getenv("ADMIN_IDS", "").split(",")[0].strip()
            if _tok and _admin:
                httpx.post(
                    f"https://api.telegram.org/bot{_tok}/sendMessage",
                    json={"chat_id": int(_admin), "text": msg[:4000]},
                    timeout=10,
                )
        except Exception:
            pass

    # Clear any stale webhook (but do NOT call /close — it kills the session)
    try:
        _tok = _os.getenv("BOT_TOKEN", "")
        if _tok:
            httpx.post(
                f"https://api.telegram.org/bot{_tok}/deleteWebhook",
                json={"drop_pending_updates": False},
                timeout=10,
            )
            logging.info("Cleared webhook before startup")
            _time.sleep(3)  # Brief pause for Telegram to release old polling lock
    except Exception as e:
        logging.warning(f"Pre-startup cleanup failed: {e}")

    try:
        main()
    except Exception as e:
        err_str = str(e)
        if "Conflict" in err_str or "terminated by other getUpdates" in err_str:
            logging.warning("Auto-fix: telegram.error.Conflict detected. Exiting gracefully.")
        else:
            err_msg = f"\U0001f534 BOT CRASH:\n\n{e}\n\n{traceback.format_exc()}"
            logging.error(err_msg)
            _send_crash_report(err_msg)
            raise
