"""
ApexFlash MEGA BOT - @ApexFlashBot
═══════════════════════════════════════════════
The all-in-one crypto whale tracking & trading bot.

Features:
  - Real-time whale alerts (ETH, SOL)
  - Solana token swaps via Jupiter V6 (1% platform fee)
  - Copy trading via MIZAR marketplace
  - DCA bot automation via MIZAR
  - Exchange affiliate hub (50-70% fee rebates)
  - Premium tiers ($19/mo Pro, $49/mo Elite)
  - Admin dashboard with stats & broadcast

Revenue model:
  1. 1% fee on every Solana token swap (Jupiter V6)
  2. Affiliate commissions (every whale alert + exchange hub)
  3. Premium subscriptions via Gumroad (Pro $19, Elite $49)
  4. MIZAR copy trading referrals (future)

Author: MindVault AI / Erik
Version: 3.1.0 (MEGA BOT + FEE COLLECTION + REFERRALS)
"""
import logging
import re
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

from config import (
    BOT_TOKEN, AFFILIATE_LINKS, ADMIN_IDS,
    GUMROAD_PRO_URL, GUMROAD_ELITE_URL, TIERS,
    SCAN_INTERVAL, WEBSITE_URL, SUPPORT_URL,
    MIZAR_REFERRAL_URL, PLATFORM_FEE_PCT,
    ETH_WHALE_WALLETS, SOL_WHALE_WALLETS,
    WALLET_ENCRYPTION_KEY, SOL_MINT,
    FEE_COLLECT_WALLET, REFERRAL_FEE_SHARE_PCT,
)
from chains import fetch_eth_whale_transfers, fetch_sol_whale_transfers, get_crypto_prices
from wallet import (
    create_wallet, load_keypair, get_sol_balance,
    get_token_balances, collect_fee, transfer_sol,
)
from jupiter import (
    get_quote, execute_swap, calculate_fee,
    get_token_info, search_token, COMMON_TOKENS,
)

# ══════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ApexFlash")

# ══════════════════════════════════════════════
# USER STORE  (Phase 2: migrate to PostgreSQL)
# ══════════════════════════════════════════════
users: dict[int, dict] = {}
seen_tx_hashes: set[str] = set()
bot_start_time = datetime.now(timezone.utc)


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
            # Referral
            "referred_by": 0,
            "referral_earnings": 0.0,
            "referral_count": 0,
        }
    # Migrate old users missing wallet/referral fields
    u = users[user_id]
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
    return u


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ══════════════════════════════════════════════
# KEYBOARD BUILDERS
# ══════════════════════════════════════════════

def main_menu_kb(user_id: int = 0) -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard."""
    user = get_user(user_id) if user_id else {"alerts_on": False}
    alert_icon = "\U0001f7e2" if user.get("alerts_on") else "\U0001f534"

    kb = [
        [InlineKeyboardButton(
            f"\U0001f40b Whale Alerts [{alert_icon}]", callback_data="whale",
        )],
        [
            InlineKeyboardButton("\U0001f4ca Top Wallets", callback_data="whale_top"),
            InlineKeyboardButton("\U0001f4b0 Latest Moves", callback_data="whale_latest"),
        ],
        [InlineKeyboardButton(
            "\U0001f4b0 Trade (Solana)", callback_data="trade",
        )],
        [
            InlineKeyboardButton("\U0001f4c8 Copy Trade", callback_data="copy_trade"),
            InlineKeyboardButton("\U0001f916 DCA Bot", callback_data="dca_bot"),
        ],
        [InlineKeyboardButton("\U0001f4b1 Exchanges", callback_data="exchanges")],
        [
            InlineKeyboardButton("\U0001f91d Referral", callback_data="referral"),
            InlineKeyboardButton("\U0001f48e Premium", callback_data="premium"),
        ],
        [
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="settings"),
            InlineKeyboardButton("\U0001f4d6 Help", callback_data="help"),
        ],
    ]

    if is_admin(user_id):
        kb.append([InlineKeyboardButton("\U0001f451 Admin Panel", callback_data="admin")])

    return InlineKeyboardMarkup(kb)


def _back_main() -> list:
    """Single back-to-main button row."""
    return [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="main")]


# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with main menu. Also handles referral deep links."""
    uid = update.effective_user.id
    user = get_user(uid)
    user["username"] = update.effective_user.username or ""

    # ── Handle referral deep link: /start ref_123456 ──
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
            # Don't self-refer, don't overwrite existing referrer
            if referrer_id != uid and not user.get("referred_by"):
                user["referred_by"] = referrer_id
                # Make sure referrer exists in store
                referrer = get_user(referrer_id)
                if "referral_count" not in referrer:
                    referrer["referral_count"] = 0
                referrer["referral_count"] = referrer.get("referral_count", 0) + 1
                logger.info(f"Referral: user {uid} referred by {referrer_id}")
        except (ValueError, IndexError):
            pass

    text = (
        "\u26a1 *ApexFlash MEGA BOT*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Your all-in-one crypto trading edge:\n"
        "\n"
        "\U0001f40b *Whale Tracking* \u2014 Real-time alerts\n"
        "\U0001f4b0 *Trade* \u2014 Swap Solana tokens instantly\n"
        "\U0001f4c8 *Copy Trade* \u2014 Follow top traders\n"
        "\U0001f916 *DCA Bot* \u2014 Automate your strategy\n"
        "\U0001f4b1 *Exchange Deals* \u2014 Up to 70% fee rebates\n"
        "\U0001f91d *Referral* \u2014 Earn 25% of friends' fees\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Select an option below:"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu_kb(update.effective_user.id),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    text = (
        "\U0001f4d6 *Help & FAQ*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "\U0001f40b *Whale Alerts* \u2014 Track large crypto transfers\n"
        "\U0001f4c8 *Copy Trade* \u2014 Copy top traders (Pro+)\n"
        "\U0001f916 *DCA Bot* \u2014 Automated buying (Pro+)\n"
        "\U0001f4b1 *Exchanges* \u2014 Fee rebates up to 70%\n"
        "\U0001f48e *Premium* \u2014 From $19/mo\n"
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


# ══════════════════════════════════════════════
# CALLBACK ROUTER
# ══════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline button presses to handlers."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    user["username"] = query.from_user.username or ""
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
        "copy_trade":    _cb_copy_trade,
        "dca_bot":       _cb_dca_bot,
        "exchanges":     _cb_exchanges,
        # Referral
        "referral":      _cb_referral,
        "referral_link": _cb_referral_link,
        "referral_stats": _cb_referral_stats,
        "premium":       _cb_premium,
        "settings":      _cb_settings,
        "help":          _cb_help,
        "help_faq":      _cb_help_faq,
        "help_copy":     _cb_help_copy,
        "help_dca":      _cb_help_dca,
        "admin":         _cb_admin,
        "admin_stats":   _cb_admin_stats,
        "admin_users":   _cb_admin_users,
        "admin_broadcast": _cb_admin_broadcast,
    }

    # Handle dynamic buy/sell amount callbacks (buy_01, buy_05, buy_1, buy_5, sell_25, sell_50, sell_100)
    if data.startswith("buy_"):
        try:
            await _cb_execute_buy(query, user, context, data)
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

    if data.startswith("sell_"):
        try:
            await _cb_execute_sell(query, user, context, data)
        except Exception as e:
            logger.error(f"Sell [{data}] error: {e}")
            try:
                await query.edit_message_text(
                    "\u26a0\ufe0f Trade failed. Use /start to return.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    handler = routes.get(data)
    if handler:
        try:
            await handler(query, user, context)
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
        f"\U0001f4cd Tracking *{len(ETH_WHALE_WALLETS)}* ETH "
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
    """Trade sub-menu."""
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
        f"\U0001f4cd `{pubkey}`\n"
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

    text += (
        "\n"
        f"\U0001f4ca Trades: *{user.get('total_trades', 0)}*\n"
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
        [InlineKeyboardButton("\U0001f504 Refresh", callback_data="trade_refresh")],
        [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
        [_back_main()[0]],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_trade_refresh_balance(query, user, context):
    """Alias for wallet view (refresh)."""
    await _cb_trade_wallet(query, user, context)


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
        "\U0001f4b5 *Buy Tokens*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "*Paste a Solana token address* in chat\n"
        "and I'll show you the token info with\n"
        "buy buttons!\n"
        "\n"
        "\U0001f4a1 *Popular tokens:*\n"
    )
    for sym, info in list(COMMON_TOKENS.items())[:6]:
        if sym != "SOL":
            text += f"\u2022 {sym} \u2014 `{info['mint'][:20]}...`\n"

    text += (
        "\n"
        "_Copy any mint address above and paste it_\n"
        "_in this chat to start buying!_\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = [
        [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
        [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
        [_back_main()[0]],
    ]

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

    tokens = await get_token_balances(user["wallet_pubkey"])

    if not tokens:
        await query.edit_message_text(
            "\U0001f4b8 *Sell Tokens*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "No tokens found in your wallet.\n"
            "Buy some tokens first!\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
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
        "Your tokens:\n\n"
    )

    # Store first sellable token for quick sell
    first_token = None
    for t in tokens[:8]:
        token_name = None
        for sym, info in COMMON_TOKENS.items():
            if info["mint"] == t["mint"]:
                token_name = sym
                break
        display = token_name or f"{t['mint'][:8]}..."
        text += f"\u2022 *{display}:* {t['amount']:,.4f}\n"
        if first_token is None:
            first_token = t

    text += (
        "\n"
        "To sell: paste the token mint address\n"
        "and I'll detect it as a sell.\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = []
    # Quick sell buttons for first token
    if first_token:
        context.user_data["sell_mint"] = first_token["mint"]
        context.user_data["sell_amount_raw"] = first_token["raw_amount"]
        context.user_data["sell_decimals"] = first_token["decimals"]
        kb.append([
            InlineKeyboardButton("Sell 25%", callback_data="sell_25"),
            InlineKeyboardButton("Sell 50%", callback_data="sell_50"),
            InlineKeyboardButton("Sell 100%", callback_data="sell_100"),
        ])
    kb.append([InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


async def _cb_execute_buy(query, user, context, data):
    """Execute a buy order. data = buy_01, buy_05, buy_1, buy_5"""
    if not user.get("wallet_pubkey") or not user.get("wallet_secret_enc"):
        await query.edit_message_text(
            "\u26a0\ufe0f No wallet. Create one first!",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    target_mint = context.user_data.get("target_mint")
    if not target_mint:
        await query.edit_message_text(
            "\u26a0\ufe0f No token selected. Paste a mint address first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b5 Buy Token", callback_data="trade_buy")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    # Parse SOL amount from callback data
    amount_map = {
        "buy_01": 0.1,
        "buy_05": 0.5,
        "buy_1": 1.0,
        "buy_5": 5.0,
    }
    sol_amount = amount_map.get(data)
    if not sol_amount:
        await query.edit_message_text("\u26a0\ufe0f Invalid amount.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown")
        return

    await query.edit_message_text(
        f"\u23f3 *Swapping {sol_amount} SOL...*\n"
        f"Token: `{target_mint[:20]}...`\n"
        f"Fee: {PLATFORM_FEE_PCT}%\n\n"
        "_Getting best price via Jupiter..._",
        parse_mode="Markdown",
    )

    # Calculate amounts (SOL has 9 decimals)
    total_lamports = int(sol_amount * 1_000_000_000)
    swap_lamports, fee_lamports = calculate_fee(total_lamports)

    # Get quote
    quote = await get_quote(
        input_mint=SOL_MINT,
        output_mint=target_mint,
        amount_raw=swap_lamports,
        slippage_bps=300,
    )

    if not quote:
        await query.edit_message_text(
            "\u274c *Quote Failed*\n\n"
            "Could not get a price for this token.\n"
            "The token may be illiquid or invalid.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Try Again", callback_data=data)],
                [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    # Execute swap
    try:
        keypair = load_keypair(user["wallet_secret_enc"])
    except Exception as e:
        logger.error(f"Keypair load error: {e}")
        await query.edit_message_text(
            "\u274c Wallet error. Please contact support.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    tx_sig = await execute_swap(keypair, quote)

    if tx_sig:
        user["total_trades"] = user.get("total_trades", 0) + 1
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
        kb = [
            [InlineKeyboardButton("\U0001f4bc View Wallet", callback_data="trade_wallet")],
            [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            [_back_main()[0]],
        ]
        logger.info(f"TRADE OK: user={query.from_user.id} buy={sol_amount}SOL token={target_mint[:12]} tx={tx_sig}")

        # ── Fee collection (best-effort, async) ──
        try:
            # Collect platform fee → ApexFlash hot wallet
            if FEE_COLLECT_WALLET and fee_lamports > 5000:
                # Check if user was referred → split fee
                referrer_id = user.get("referred_by", 0)
                if referrer_id and referrer_id in users:
                    referrer = users[referrer_id]
                    referral_share = int(fee_lamports * REFERRAL_FEE_SHARE_PCT / 100)
                    platform_share = fee_lamports - referral_share

                    # Platform fee
                    await collect_fee(keypair, platform_share, FEE_COLLECT_WALLET)
                    # Referrer share → referrer's bot wallet
                    if referrer.get("wallet_pubkey") and referral_share > 5000:
                        ref_kp = keypair  # fee comes from trader's wallet
                        await transfer_sol(ref_kp, referrer["wallet_pubkey"], referral_share)
                        referrer["referral_earnings"] = referrer.get("referral_earnings", 0) + referral_share / 1e9
                        logger.info(f"Referral fee: {referral_share} lamports -> user {referrer_id}")
                else:
                    # No referrer — full fee to platform
                    await collect_fee(keypair, fee_lamports, FEE_COLLECT_WALLET)
        except Exception as fee_err:
            logger.warning(f"Fee collection failed (non-fatal): {fee_err}")
    else:
        text = (
            "\u274c *Swap Failed*\n\n"
            "Transaction could not be executed.\n"
            "Possible reasons:\n"
            "\u2022 Insufficient SOL balance\n"
            "\u2022 Slippage too high\n"
            "\u2022 Network congestion\n"
            "\n"
            "Check your balance and try again."
        )
        kb = [
            [InlineKeyboardButton("\U0001f4bc My Wallet", callback_data="trade_wallet")],
            [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
            [_back_main()[0]],
        ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def _cb_execute_sell(query, user, context, data):
    """Execute a sell order. data = sell_25, sell_50, sell_100"""
    if not user.get("wallet_pubkey") or not user.get("wallet_secret_enc"):
        await query.edit_message_text(
            "\u26a0\ufe0f No wallet found.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    sell_mint = context.user_data.get("sell_mint")
    sell_amount_raw = context.user_data.get("sell_amount_raw", "0")
    if not sell_mint:
        await query.edit_message_text(
            "\u26a0\ufe0f No token selected for selling.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b8 Sell Token", callback_data="trade_sell")],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    # Calculate sell amount based on percentage
    pct_map = {"sell_25": 0.25, "sell_50": 0.50, "sell_100": 1.0}
    pct = pct_map.get(data, 1.0)
    raw_total = int(sell_amount_raw)
    sell_raw = int(raw_total * pct)

    if sell_raw <= 0:
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

    # Apply fee
    swap_amount, fee_amount = calculate_fee(sell_raw)

    # Get quote (token → SOL)
    quote = await get_quote(
        input_mint=sell_mint,
        output_mint=SOL_MINT,
        amount_raw=swap_amount,
        slippage_bps=300,
    )

    if not quote:
        await query.edit_message_text(
            "\u274c *Quote Failed*\n\nCould not get price.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
                [_back_main()[0]],
            ]),
            parse_mode="Markdown",
        )
        return

    try:
        keypair = load_keypair(user["wallet_secret_enc"])
    except Exception as e:
        logger.error(f"Keypair load error: {e}")
        await query.edit_message_text(
            "\u274c Wallet error.",
            reply_markup=InlineKeyboardMarkup([[_back_main()[0]]]),
            parse_mode="Markdown",
        )
        return

    tx_sig = await execute_swap(keypair, quote)

    if tx_sig:
        user["total_trades"] = user.get("total_trades", 0) + 1
        out_lamports = int(quote.get("outAmount", 0))
        sol_received = out_lamports / 1_000_000_000

        text = (
            "\u2705 *Sell Successful!*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f4b8 Sold: *{pct_label}* of token\n"
            f"\U0001f4b5 Received: ~*{sol_received:.4f} SOL*\n"
            f"\U0001f4b0 Fee: {PLATFORM_FEE_PCT}%\n"
            "\n"
            f"\U0001f517 [View on Solscan](https://solscan.io/tx/{tx_sig})\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )
        kb = [
            [InlineKeyboardButton("\U0001f4bc View Wallet", callback_data="trade_wallet")],
            [_back_main()[0]],
        ]
        logger.info(f"SELL OK: user={query.from_user.id} pct={pct_label} tx={tx_sig}")

        # ── Fee collection (best-effort) ──
        try:
            if FEE_COLLECT_WALLET and fee_amount > 5000:
                referrer_id = user.get("referred_by", 0)
                if referrer_id and referrer_id in users:
                    referrer = users[referrer_id]
                    referral_share = int(fee_amount * REFERRAL_FEE_SHARE_PCT / 100)
                    platform_share = fee_amount - referral_share
                    # Note: sell fee is in token units, not SOL — for now we collect
                    # the SOL received as fee after it arrives. Simplified v1:
                    # we collect from the SOL received after swap
                    sol_fee_lamports = int(out_lamports * PLATFORM_FEE_PCT / 100)
                    if sol_fee_lamports > 5000:
                        ref_share_sol = int(sol_fee_lamports * REFERRAL_FEE_SHARE_PCT / 100)
                        platform_sol = sol_fee_lamports - ref_share_sol
                        await collect_fee(keypair, platform_sol, FEE_COLLECT_WALLET)
                        if referrer.get("wallet_pubkey") and ref_share_sol > 5000:
                            await transfer_sol(keypair, referrer["wallet_pubkey"], ref_share_sol)
                            referrer["referral_earnings"] = referrer.get("referral_earnings", 0) + ref_share_sol / 1e9
                else:
                    sol_fee_lamports = int(out_lamports * PLATFORM_FEE_PCT / 100)
                    if sol_fee_lamports > 5000:
                        await collect_fee(keypair, sol_fee_lamports, FEE_COLLECT_WALLET)
        except Exception as fee_err:
            logger.warning(f"Sell fee collection failed (non-fatal): {fee_err}")
    else:
        text = (
            "\u274c *Sell Failed*\n\n"
            "Transaction failed. Try again."
        )
        kb = [
            [InlineKeyboardButton("\U0001f504 Retry", callback_data=data)],
            [_back_main()[0]],
        ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


async def handle_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect Solana token addresses pasted in chat and show buy options."""
    text = update.message.text.strip()

    # Check if it looks like a Solana address
    if not SOL_ADDR_RE.match(text):
        return

    user_id = update.effective_user.id
    user = get_user(user_id)

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

        # Store target mint for buy callbacks
        context.user_data["target_mint"] = text
        context.user_data["target_name"] = symbol
        context.user_data["target_decimals"] = decimals

        # Get SOL balance for display
        sol_bal = await get_sol_balance(user["wallet_pubkey"])
        prices = await get_crypto_prices()
        sol_price = prices.get("SOL", 0)

        msg = (
            f"\U0001f3af *{name}* ({symbol})\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            f"\U0001f4cd Mint: `{text}`\n"
            f"\U0001f522 Decimals: {decimals}\n"
            "\n"
            f"\U0001f4bc Your SOL: *{sol_bal:.4f}*"
        )
        if sol_price:
            msg += f" (${sol_bal * sol_price:,.2f})"
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
            [InlineKeyboardButton("\U0001f4b0 Trade Menu", callback_data="trade")],
            [_back_main()[0]],
        ]

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

async def _cb_copy_trade(query, user, context):
    """Copy trading via MIZAR."""
    tier = TIERS.get(user["tier"], TIERS["free"])

    if not tier.get("copy_trade"):
        # Upsell
        text = (
            "\U0001f4c8 *Copy Trading*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "\U0001f512 *Pro Feature*\n"
            "\n"
            "Copy the exact trades of profitable\n"
            "traders automatically. Set your risk,\n"
            "and let the pros trade for you.\n"
            "\n"
            "\u2705 Auto-copy whale traders\n"
            "\u2705 Adjustable position sizing\n"
            "\u2705 Stop-loss protection\n"
            "\u2705 Multiple traders at once\n"
            "\n"
            "Unlock with Pro or Elite:"
        )
        kb = [
            [InlineKeyboardButton("\U0001f680 Pro \u2014 $19/mo", url=GUMROAD_PRO_URL)],
            [InlineKeyboardButton("\U0001f451 Elite \u2014 $49/mo", url=GUMROAD_ELITE_URL)],
            [_back_main()[0]],
        ]
    else:
        text = (
            "\U0001f4c8 *Copy Trading*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\n"
            "Copy profitable traders automatically.\n"
            "Powered by MIZAR.\n"
            "\n"
            "\U0001f3c6 *How it works:*\n"
            "1\ufe0f\u20e3 Browse top-performing traders\n"
            "2\ufe0f\u20e3 Connect your exchange API\n"
            "3\ufe0f\u20e3 Set your risk & position size\n"
            "4\ufe0f\u20e3 Trades are copied automatically\n"
            "\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Open MIZAR to start copying:"
        )
        kb = [
            [InlineKeyboardButton("\U0001f517 Open MIZAR Platform", url=MIZAR_REFERRAL_URL)],
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
        kb = [
            [InlineKeyboardButton("\U0001f680 Pro \u2014 $19/mo", url=GUMROAD_PRO_URL)],
            [InlineKeyboardButton("\U0001f451 Elite \u2014 $49/mo", url=GUMROAD_ELITE_URL)],
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
    """Show exchange affiliate hub."""
    text = (
        "\U0001f4b1 *Partner Exchanges*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Trade with the lowest fees using\n"
        "our exclusive referral links:\n\n"
    )

    # Featured exchanges
    for key, aff in AFFILIATE_LINKS.items():
        if aff.get("featured"):
            text += (
                f"\U0001f525 *{aff['name']}* \u2014 {aff['commission']} rebate\n"
                f"   _{aff.get('description', '')}_\n\n"
            )

    text += "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"

    # Other exchanges
    for key, aff in AFFILIATE_LINKS.items():
        if not aff.get("featured"):
            text += f"\u2022 *{aff['name']}* \u2014 {aff['commission']} rebate\n"

    text += "\n\U0001f4a1 _Sign up via our links to support ApexFlash!_"

    # Buttons: featured
    featured_btns = [
        InlineKeyboardButton(f"\U0001f525 {v['name']}", url=v["url"])
        for k, v in AFFILIATE_LINKS.items() if v.get("featured")
    ]
    # Other
    other_btns = [
        InlineKeyboardButton(v["name"], url=v["url"])
        for k, v in AFFILIATE_LINKS.items() if not v.get("featured")
    ]

    kb = []
    # 2 per row for featured
    for i in range(0, len(featured_btns), 2):
        kb.append(featured_btns[i:i + 2])
    # 3 per row for others
    if other_btns:
        for i in range(0, len(other_btns), 3):
            kb.append(other_btns[i:i + 3])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


# ══════════════════════════════════════════════
# PREMIUM SECTION
# ══════════════════════════════════════════════

async def _cb_premium(query, user, context):
    """Show premium tiers with upsell."""
    current = user.get("tier", "free")
    tier_info = TIERS[current]

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
        "\U0001f680 *Pro \u2014 $19/mo*\n"
        "\u2022 ETH + SOL alerts (instant)\n"
        "\u2022 20 tracked wallets\n"
        "\u2022 Copy Trading access\n"
        "\u2022 DCA Bot access\n"
        "\u2022 Priority support\n"
        "\n"
        "\U0001f451 *Elite \u2014 $49/mo*\n"
        "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
        "\u2022 100 tracked wallets\n"
        "\u2022 AI-powered signals\n"
        "\u2022 Copy Trading + DCA Bot\n"
        "\u2022 Custom alert thresholds\n"
        "\u2022 1-on-1 onboarding call\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    )

    kb = []
    if current == "free":
        kb.append([InlineKeyboardButton("\U0001f680 Get Pro \u2014 $19/mo", url=GUMROAD_PRO_URL)])
        kb.append([InlineKeyboardButton("\U0001f451 Get Elite \u2014 $49/mo", url=GUMROAD_ELITE_URL)])
    elif current == "pro":
        kb.append([InlineKeyboardButton("\U0001f451 Upgrade to Elite", url=GUMROAD_ELITE_URL)])
    kb.append([_back_main()[0]])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown", disable_web_page_preview=True,
    )


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
        f"`{ref_link}`\n"
        "\n"
        "_Tap the link to copy it!_\n"
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
        f"\n\u2022 Fee share: *{REFERRAL_FEE_SHARE_PCT}%* of 1% trade fee\n"
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
        "   starting at $19/mo\n"
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
        "\U0001f451 *Admin Panel*\n"
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
    kb = [
        [InlineKeyboardButton("\U0001f4ca Revenue Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("\U0001f465 User List", callback_data="admin_users")],
        [InlineKeyboardButton("\U0001f4e2 Broadcast Info", callback_data="admin_broadcast")],
        [_back_main()[0]],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown",
    )


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
        "\U0001f4ca *Revenue & Growth*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4b0 *Revenue*\n"
        f"\u2022 Trade fees ({PLATFORM_FEE_PCT}%): *~${trade_fees_est:,.2f}*\n"
        f"\u2022 MRR (subs): *${mrr}/mo*\n"
        f"\u2022 Pro: {pro_c} \u00d7 $19 = ${pro_c * 19}\n"
        f"\u2022 Elite: {elite_c} \u00d7 $49 = ${elite_c * 49}\n"
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
        "\U0001f465 *User List*\n"
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
        "\U0001f4e2 *Broadcast*\n"
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

def format_whale_alert(alert: dict, prices: dict) -> str:
    """Format a whale alert message with affiliate CTA."""
    chain = alert["chain"]
    value = alert["value"]
    symbol = alert["symbol"]
    direction = alert["direction"]

    emoji = "\U0001f534" if direction == "OUT" else "\U0001f7e2"
    value_str = f"{value:,.0f}" if value >= 100 else f"{value:,.2f}"

    price = prices.get(symbol, 0)
    usd_value = value * price
    usd_str = f"(~${usd_value:,.0f})" if usd_value > 0 else ""

    # Random featured affiliate
    featured = [k for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
    aff_key = random.choice(featured) if featured else list(AFFILIATE_LINKS.keys())[0]
    aff = AFFILIATE_LINKS[aff_key]

    # Explorer
    if chain == "ETH":
        explorer = f"https://etherscan.io/tx/{alert['tx_hash']}"
    elif chain == "SOL":
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
    else:
        explorer = ""

    text = (
        f"{emoji} *WHALE ALERT* \u2502 {chain}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4b0 *{value_str} {symbol}* {usd_str}\n"
        f"\U0001f4e4 From: `{alert['from_label']}`\n"
        f"\U0001f4e5 To: `{alert['to_label']}`\n"
    )

    if explorer:
        text += f"\n\U0001f517 [View Transaction]({explorer})\n"

    text += (
        f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f525 [{aff['name']} \u2014 {aff['commission']} fee rebate]({aff['url']})\n"
        f"\U0001f48e Instant alerts + more chains \u2192 /premium"
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
        all_alerts = eth_alerts + sol_alerts

        new_alerts = [a for a in all_alerts if a["tx_hash"] not in seen_tx_hashes]

        if not new_alerts:
            return

        # Mark as seen
        for a in new_alerts:
            seen_tx_hashes.add(a["tx_hash"])

        # Cap memory
        if len(seen_tx_hashes) > 10000:
            seen_tx_hashes = set(list(seen_tx_hashes)[-5000:])

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
                    text = format_whale_alert(alert, prices)

                    # Add trade + affiliate buttons
                    alert_kb = []
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
                            "\U0001f4b0 Trade Now", callback_data="trade",
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

        logger.info(f"Scanner: {len(new_alerts)} new alerts distributed")

    except Exception as e:
        logger.error(f"Scanner error: {e}")


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Add it to .env or environment variables.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Inline callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Token address detection (Solana addresses pasted in chat)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_token_address,
    ))

    # Whale scanner repeating job
    app.job_queue.run_repeating(
        scan_and_alert,
        interval=SCAN_INTERVAL,
        first=10,
        name="whale_scanner",
    )

    logger.info("\u26a1 ApexFlash MEGA BOT v3.1 starting (Trading + Fees + Referrals)...")
    logger.info(f"\U0001f4e1 Scan interval: {SCAN_INTERVAL}s")
    logger.info(f"\U0001f451 Admin IDs: {ADMIN_IDS}")
    logger.info(f"\U0001f40b Tracking {len(ETH_WHALE_WALLETS)} ETH + {len(SOL_WHALE_WALLETS)} SOL wallets")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
