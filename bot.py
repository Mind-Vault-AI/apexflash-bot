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
VERSION = "3.22.0"
import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import re
import random
from datetime import datetime, timezone, time as dt_time
import asyncio

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
    track_paid_conversion, track_user_active, track_visitor,
    get_user_bucket, track_bucket_kpi, track_user_profit, get_leaderboard_stats,
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
    return u


def _persist():
    """Save users + stats to disk after any mutation."""
    save_users(users)
    save_stats(platform_stats)


def is_admin(user_id: int) -> bool:
    """Check if user_id is in the ADMIN_IDS list from config."""
    # Kaizen: Convert to list of ints for safe comparison
    return user_id in ADMIN_IDS

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                        # KAIZEN: Viral Reward Loop (v3.15.2) - 24h Pro for every referral
                        referrer["tier"] = "pro"
                        referrer["tier_expires"] = (datetime.now(timezone.utc).timestamp() + 86400)
                        logger.info(f"Referral+Reward: user {uid} referred by {referrer_id}. Referrer awarded 24h Pro.")
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
                    logger.info(f"Referral: user {uid} referred by {referrer_id}")
            except (ValueError, IndexError):
                pass

    # Track unique visitor globally and per channel
    track_visitor(uid, visitor_channel)

    # A/B Split Content (Variant A: Safety vs Variant B: Revenue)
    if bucket_id == 1:
        # Variant B: Revenue & Speed Focus
        welcome_header = (
            "\u26a1 *ApexFlash MEGA BOT v3.15.5*\n"
            "━━━━━ Institutional Speed ━━━━━\n"
        )
        tagline = "The world's fastest autonomous scalp engine. Your path to financial immunity starts here."
    else:
        # Variant A: Safety & Zero-Loss Focus
        welcome_header = (
            "\u26a1 *ApexFlash MEGA BOT v3.15.5*\n"
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

                # Try with chart
                try:
                    chart_url = await get_token_chart_url(deep_link_mint, hours=24)
                    if chart_url:
                        await update.message.reply_photo(
                            photo=chart_url, caption=msg,
                            reply_markup=InlineKeyboardMarkup(kb),
                            parse_mode="Markdown",
                        )
                    else:
                        await update.message.reply_text(
                            msg, reply_markup=InlineKeyboardMarkup(kb),
                            parse_mode="Markdown",
                        )
                except Exception:
                    await update.message.reply_text(
                        msg, reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown",
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
            aff_info = AFFILIATE_LINKS.get(aff_key, AFFILIATE_LINKS.get("mexc"))
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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    text = (
        "\U0001f4d6 *Help & FAQ (v3.15.4)*\n"
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
            "🌐 *BASE/SOL Network*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 Base & Arbitrum signals are launching in v3.16.0.\n"
            "✅ Auto-trading currently runs on Solana (primary engine).\n\n"
            "Use Trade to continue on SOL.",
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
    }

    # Basic dispatch for exact matches in the routes dictionary
    if data in routes:
        try:
            await routes[data](query, user, context)
        except Exception as e:
            logger.error(f"Callback error [{data}]: {e}")
            from traceback import format_exc
            logger.error(format_exc())
            try:
                await query.edit_message_text("\u26a0\ufe0f An error occurred. Please use /start.")
            except Exception:
                pass
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
            sol_bal = await get_sol_balance(user.get("wallet_pubkey", ""))
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
                "⚠️ Could not load token info.",
                reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
                parse_mode="Markdown",
            )
        return

    # Handle /hot refresh
    if data == "cmd_hot_refresh":
        await query.edit_message_text("🔥 *Refreshing...*", parse_mode="Markdown")
        update.message = query.message
        await cmd_hot(update, context)
        return

    # Handle /market refresh
    if data == "cmd_market_refresh":
        await query.edit_message_text("📊 *Refreshing market...*", parse_mode="Markdown")
        update.message = query.message
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
            sol_bal = await get_sol_balance(user.get("wallet_pubkey", ""))
            prices = await get_crypto_prices()
            sol_price = prices.get("SOL", 0)
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
        await query.edit_message_text(
            "\u270f\ufe0f *Custom Buy Amount*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Type your desired SOL amount (0.01 \u2013 {MAX_TRADE_SOL}):\n\n"
            "_Example: `0.25` or `3.5`_",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u274c Cancel", callback_data="trade_buy")],
            ]),
            parse_mode="Markdown",
        )
        return

    if data.startswith("buy_"):
        try:
            await _cb_preview_buy(query, user, context, data)
        except Exception as e:
            logger.error(f"Buy preview [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Trade failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
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
            aff_info = AFFILIATE_LINKS.get(exchange, AFFILIATE_LINKS.get("mexc"))
            
            text = (
                f"🚀 *Affiliate Redirect*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You are opening *{aff_info['name']}*.\n"
                f"Benefit: *{aff_info['commission']} fee rebate*\n\n"
                f"Click below to open in your browser:"
            )
            kb = [
                [InlineKeyboardButton(f"🔗 Open {aff_info['name']}", url=aff_info["url"])],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
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
            "Trading is temporarily disabled by admin.\n"
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
    sol_bal = await get_sol_balance(pubkey)
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
            sol_str = f"{t['sol']:.2f}" if t['sol'] >= 0.01 else f"{t['sol']:.4f}"
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
        [InlineKeyboardButton("\U0001f504 Refresh", callback_data="portfolio")],
        [InlineKeyboardButton("\U0001f3c6 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
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
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "Automated copy trading for any SOL token.\n"
            "Powered by MIZAR.\n"
            "\n"
            "1. Choose a top trader to follow\n"
            "2. Set your risk parameters\n"
            "3. Watch the profits roll in 🚀\n"
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
            [InlineKeyboardButton("\U0001f4d6 How Copy Trading Works", callback_data="help_copy")],
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
    text += "\U0001f525 *Top Exchange Deals:*\n"
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
        for k, v in AFFILIATE_LINKS.items()
        if v.get("featured") and v.get("url", "").find("YOUR_REF") == -1
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
        "\u2022 Copy Trading & DCA Bot\n"
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
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\n"
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
            await notify_discord_trade(uname, "UPGRADE", "Gumroad License", f"{tier_info['name']} Plan", "", 0)
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

async def _cb_referral(query, user, context):
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
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
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
    user = get_user(uid)
    
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
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


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
    """Admin dashboard."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 Unauthorized.")
        return

    total = len(users)
    active = sum(1 for u in users.values() if u.get("alerts_on"))
    pro = sum(1 for u in users.values() if u.get("tier") == "pro")
    elite = sum(1 for u in users.values() if u.get("tier") == "elite")
    uptime = datetime.now(timezone.utc) - bot_start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)

    text = (
        "\U0001f451 *Admin Panel (v3.15.2)*\n"
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
        "\U0001f4ca *Revenue & Growth (v3.15.2)*\n"
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
        "\U0001f465 *User List (v3.15.2)*\n"
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
        "\U0001f4e2 *Broadcast (v3.15.2)*\n"
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

def format_whale_alert(alert: dict, prices: dict, sentiment: dict = None) -> str:
    """Format a whale alert message with signal quality, affiliate CTA and AI sentiment."""
    chain = alert["chain"]
    value = alert["value"]
    symbol = alert["symbol"]
    direction = alert.get("direction", "IN")
    alert_type = alert.get("type", "TRANSFER")

    # SWAP alerts = most actionable (whale buying a specific token)
    if alert_type == "SWAP":
        emoji = "\U0001f6a8"  # 🚨
        amount = alert.get("amount", 0)
        amount_str = f"{amount:,.0f}" if amount >= 100 else f"{amount:,.2f}"
        wallet = alert.get("wallet_name", "Unknown Whale")

        price = prices.get(symbol, 0)
        usd_value = value * price if value > 0 else 0
        usd_str = f"(${usd_value:,.0f})" if usd_value > 0 else ""

        # Special SWAP format — actionable
        text = (
            f"{emoji} *WHALE BUY DETECTED* \u2502 {chain}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\n"
            f"\U0001f4b0 *{wallet}* just bought:\n"
            f"\U0001f3af *{amount_str} {symbol}* {usd_str}\n"
            f"\U0001f6a8 This is a LIVE swap — whale is accumulating!\n"
        )

        # Signal quality
        from sentiment import format_signal_quality
        sq = alert.get("_signal_quality")
        if sq:
            text += f"\n{format_signal_quality(sq)}"

        # Sentiment
        sentiment_line = format_sentiment_line(sentiment)
        if sentiment_line:
            text += f"\n\U0001f9e0 *AI Sentiment*\n{sentiment_line}"

        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
        text += f"\n\U0001f517 [View Swap on Solscan]({explorer})\n"

        # Exchange promo
        featured = [k for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
        aff_key = random.choice(featured) if featured else list(AFFILIATE_LINKS.keys())[0]
        aff = AFFILIATE_LINKS[aff_key]
        promo = aff.get("promo", "")

        text += (
            f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )
        if promo:
            text += f"\U0001f381 *{promo}*\n"
        text += (
            f"\U0001f525 [{aff['name']} \u2014 {aff['commission']} fee rebate]({aff['url']})\n"
            f"\U0001f48e Instant alerts + more chains \u2192 /premium"
        )
        return text

    # Regular TRANSFER alert (existing format)
    emoji = "\U0001f534" if direction == "OUT" else "\U0001f7e2"
    value_str = f"{value:,.0f}" if value >= 100 else f"{value:,.2f}"

    price = prices.get(symbol, 0)
    usd_value = value * price
    usd_str = f"(${usd_value:,.0f})" if usd_value > 0 else ""

    # Random featured affiliate with promo bonus
    featured = [(k, v) for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
    aff_key = random.choice(featured) if featured else list(AFFILIATE_LINKS.keys())[0]
    aff = AFFILIATE_LINKS[aff_key]

    # Explorer
    if chain == "ETH":
        explorer = f"https://etherscan.io/tx/{alert['tx_hash']}"
    elif chain == "SOL":
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
    else:
        explorer = ""

    # AI Sentiment line (CryptoBERT)
    sentiment_line = format_sentiment_line(sentiment)

    # Signal quality line
    from sentiment import format_signal_quality
    sq = alert.get("_signal_quality")
    sq_line = format_signal_quality(sq) if sq else ""

    text = (
        f"{emoji} *WHALE ALERT* \u2502 {chain}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f4b0 *{value_str} {symbol}* {usd_str}\n"
        f"\U0001f4e4 From: `{alert['from_label']}`\n"
        f"\U0001f4e5 To: `{alert['to_label']}`\n"
    )

    # Signal quality (new — shows grade + action)
    if sq_line:
        text += f"\n\U0001f3af *Signal Analysis*\n{sq_line}"

    if sentiment_line:
        text += f"\n\U0001f9e0 *AI Sentiment*\n{sentiment_line}"

    if explorer:
        text += f"\n\U0001f517 [View Transaction]({explorer})\n"

    # Exchange promo with bonus (rotates)
    promo_line = aff.get("promo", "")
    if promo_line:
        text += (
            f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f381 *{promo_line}*\n"
            f"\U0001f525 [{aff['name']} \u2014 {aff['commission']} fee rebate]({aff['url']})\n"
            f"\U0001f48e Instant alerts + more chains \u2192 /premium"
        )
    else:
        text += (
            f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f525 [{aff['name']} \u2014 {aff['commission']} fee rebate]({aff['url']})\n"
            f"\U0001f48e Instant alerts + more chains \u2192 /premium"
        )

    return text
