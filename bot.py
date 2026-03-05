"""
ApexFlash MEGA BOT - @ApexFlashBot
═══════════════════════════════════════════════
The all-in-one crypto whale tracking & trading bot.

Features:
  - Real-time whale alerts (ETH, SOL)
  - Copy trading via MIZAR marketplace
  - DCA bot automation via MIZAR
  - Exchange affiliate hub (50-70% fee rebates)
  - Premium tiers ($19/mo Pro, $49/mo Elite)
  - Admin dashboard with stats & broadcast

Revenue model:
  1. Affiliate commissions (every whale alert + exchange hub)
  2. Premium subscriptions via Gumroad (Pro $19, Elite $49)
  3. MIZAR copy trading referrals (future)

Author: MindVault AI / Erik
Version: 2.0.0 (MEGA BOT)
"""
import logging
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

from config import (
    BOT_TOKEN, AFFILIATE_LINKS, ADMIN_IDS,
    GUMROAD_PRO_URL, GUMROAD_ELITE_URL, TIERS,
    SCAN_INTERVAL, WEBSITE_URL, SUPPORT_URL,
    MIZAR_REFERRAL_URL,
    ETH_WHALE_WALLETS, SOL_WHALE_WALLETS,
)
from chains import fetch_eth_whale_transfers, fetch_sol_whale_transfers, get_crypto_prices

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
        }
    return users[user_id]


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
        [
            InlineKeyboardButton("\U0001f4c8 Copy Trade", callback_data="copy_trade"),
            InlineKeyboardButton("\U0001f916 DCA Bot", callback_data="dca_bot"),
        ],
        [InlineKeyboardButton("\U0001f4b1 Exchanges", callback_data="exchanges")],
        [
            InlineKeyboardButton("\U0001f48e Premium", callback_data="premium"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="settings"),
        ],
        [InlineKeyboardButton("\U0001f4d6 Help & FAQ", callback_data="help")],
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
    """Welcome message with main menu."""
    user = get_user(update.effective_user.id)
    user["username"] = update.effective_user.username or ""

    text = (
        "\u26a1 *ApexFlash MEGA BOT*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        "Your all-in-one crypto trading edge:\n"
        "\n"
        "\U0001f40b *Whale Tracking* \u2014 Real-time alerts\n"
        "\U0001f4c8 *Copy Trade* \u2014 Follow top traders\n"
        "\U0001f916 *DCA Bot* \u2014 Automate your strategy\n"
        "\U0001f4b1 *Exchange Deals* \u2014 Up to 70% fee rebates\n"
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
        "copy_trade":    _cb_copy_trade,
        "dca_bot":       _cb_dca_bot,
        "exchanges":     _cb_exchanges,
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
# TRADE SECTION (Copy Trade + DCA)
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
# SETTINGS SECTION
# ══════════════════════════════════════════════

async def _cb_settings(query, user, context):
    """User settings panel."""
    tier = TIERS.get(user["tier"], TIERS["free"])
    alert_txt = "\U0001f7e2 ON" if user["alerts_on"] else "\U0001f534 OFF"

    text = (
        "\u2699\ufe0f *Settings*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4cb Plan: *{tier['emoji']} {tier['name']}*\n"
        f"\U0001f514 Alerts: *{alert_txt}*\n"
        f"\u26d3 Chains: *{', '.join(tier['chains'])}*\n"
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

    text = (
        "\U0001f4ca *Revenue & Growth*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\n"
        f"\U0001f4b0 *Revenue*\n"
        f"\u2022 MRR: *${mrr}/mo*\n"
        f"\u2022 Pro: {pro_c} \u00d7 $19 = ${pro_c * 19}\n"
        f"\u2022 Elite: {elite_c} \u00d7 $49 = ${elite_c * 49}\n"
        f"\u2022 Affiliate: _check exchange dashboards_\n"
        f"\n"
        f"\U0001f4c8 *Growth*\n"
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
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=text,
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

    # Whale scanner repeating job
    app.job_queue.run_repeating(
        scan_and_alert,
        interval=SCAN_INTERVAL,
        first=10,
        name="whale_scanner",
    )

    logger.info("\u26a1 ApexFlash MEGA BOT v2.0 starting...")
    logger.info(f"\U0001f4e1 Scan interval: {SCAN_INTERVAL}s")
    logger.info(f"\U0001f451 Admin IDs: {ADMIN_IDS}")
    logger.info(f"\U0001f40b Tracking {len(ETH_WHALE_WALLETS)} ETH + {len(SOL_WHALE_WALLETS)} SOL wallets")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
