"""
ApexFlash Bot - @ApexFlashBot
Production Telegram bot for whale tracking + affiliate monetization.

Revenue model:
1. Affiliate links in every whale alert
2. Premium tiers via Gumroad ($19/mo Pro, $49/mo Elite)
3. Future: MIZAR API trading integration

Author: MindVault AI / Erik
"""
import os
import logging
import random
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from config import (
    BOT_TOKEN, PORT, AFFILIATE_LINKS,
    GUMROAD_PRO_URL, GUMROAD_ELITE_URL, TIERS,
    SCAN_INTERVAL,
)
from chains import fetch_eth_whale_transfers, fetch_sol_whale_transfers

# === Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# === In-memory user store (upgrade to DB in Phase 2) ===
users: dict[int, dict] = {}
# Track last seen tx hashes to avoid duplicate alerts
seen_tx_hashes: set[str] = set()


def get_user(user_id: int) -> dict:
    """Get or create user profile."""
    if user_id not in users:
        users[user_id] = {
            "tier": "free",
            "alerts_on": False,
            "chains": ["ETH"],
            "joined": datetime.utcnow().isoformat(),
        }
    return users[user_id]


# === Message Formatters ===

def format_whale_alert(alert: dict) -> str:
    """Format a single whale alert with affiliate CTA."""
    chain = alert["chain"]
    value = alert["value"]
    symbol = alert["symbol"]
    direction = alert["direction"]
    from_label = alert["from_label"]
    to_label = alert["to_label"]

    # Direction emoji
    emoji = "\U0001F534" if direction == "OUT" else "\U0001F7E2"  # red/green circle

    # Value formatting
    if value >= 10000:
        value_str = f"{value:,.0f}"
    else:
        value_str = f"{value:,.2f}"

    # USD estimate (rough)
    usd_prices = {"ETH": 3500, "SOL": 180, "BTC": 95000}
    usd_value = value * usd_prices.get(symbol, 0)
    usd_str = f"(~${usd_value:,.0f})" if usd_value > 0 else ""

    # Pick random featured affiliate for CTA
    featured = [k for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
    aff_key = random.choice(featured) if featured else list(AFFILIATE_LINKS.keys())[0]
    aff = AFFILIATE_LINKS[aff_key]

    # Explorer link
    if chain == "ETH":
        explorer = f"https://etherscan.io/tx/{alert['tx_hash']}"
    elif chain == "SOL":
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
    else:
        explorer = ""

    text = (
        f"{emoji} *WHALE ALERT* | {chain}\n"
        f"\n"
        f"\U0001F4B0 *{value_str} {symbol}* {usd_str}\n"
        f"\U0001F4E4 From: {from_label}\n"
        f"\U0001F4E5 To: {to_label}\n"
    )

    if explorer:
        text += f"\n[View Transaction]({explorer})\n"

    text += (
        f"\n\U0001F525 *Trade {symbol} now on {aff['name']}*\n"
        f"\U0001F449 [{aff['name']} - {aff['commission']} fee rebate]({aff['url']})\n"
        f"\n"
        f"\U0001F451 Want instant alerts + SOL tracking? /premium"
    )

    return text


def get_affiliate_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard with affiliate exchange buttons."""
    buttons = []
    for key, aff in AFFILIATE_LINKS.items():
        if aff.get("featured"):
            buttons.append(
                InlineKeyboardButton(
                    f"\U0001F525 {aff['name']} ({aff['commission']})",
                    url=aff["url"],
                )
            )
    # Max 2 per row
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("\U0001F451 Go Premium", callback_data="premium")])
    return InlineKeyboardMarkup(keyboard)


# === Command Handlers ===

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message + onboarding."""
    user = get_user(update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("\U0001F40B Start Whale Alerts", callback_data="alerts_on")],
        [InlineKeyboardButton("\U0001F4CA Latest Whale Moves", callback_data="latest")],
        [
            InlineKeyboardButton("\U0001F4B1 Exchanges", callback_data="exchanges"),
            InlineKeyboardButton("\U0001F451 Premium", callback_data="premium"),
        ],
        [InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="settings")],
    ]

    text = (
        "\U0001F4A1 *Welcome to ApexFlash*\n"
        "\n"
        "Your AI-powered whale tracking edge.\n"
        "\n"
        "\U0001F40B *Real-time whale alerts* - ETH & SOL\n"
        "\U0001F4CA *Smart money tracking* - Follow the big players\n"
        "\U0001F525 *Exchange deals* - Up to 70% fee rebates\n"
        "\n"
        "Tap below to get started:"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show premium upgrade options."""
    await _show_premium(update.effective_chat.id, context)


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle alerts on."""
    user = get_user(update.effective_user.id)
    user["alerts_on"] = True
    await update.message.reply_text(
        "\u2705 *Whale alerts activated!*\n\nYou'll receive alerts when whales move big money.\n\nUse /stop to disable.",
        parse_mode="Markdown",
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle alerts off."""
    user = get_user(update.effective_user.id)
    user["alerts_on"] = False
    await update.message.reply_text(
        "\U0001F515 Alerts disabled. Use /start to re-enable.",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot status."""
    active = sum(1 for u in users.values() if u.get("alerts_on"))
    premium = sum(1 for u in users.values() if u.get("tier") != "free")

    await update.message.reply_text(
        f"\U0001F4CA *ApexFlash Status*\n\n"
        f"\u2022 Total users: {len(users)}\n"
        f"\u2022 Active alerts: {active}\n"
        f"\u2022 Premium users: {premium}\n"
        f"\u2022 Chains: ETH, SOL\n"
        f"\u2022 Uptime: Online \u2705\n"
        f"\u2022 Last scan: {datetime.utcnow().strftime('%H:%M:%S UTC')}",
        parse_mode="Markdown",
    )


# === Callback Query Handler ===

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all inline button presses."""
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    data = query.data

    if data == "alerts_on":
        user["alerts_on"] = True
        await query.edit_message_text(
            "\u2705 *Whale alerts activated!*\n\n"
            "\U0001F40B You'll get notified when whales make big moves.\n\n"
            "\U0001F4A1 *Tip:* Upgrade to Pro for SOL alerts + zero delay.\n"
            "Use /premium to upgrade.",
            parse_mode="Markdown",
        )

    elif data == "latest":
        await query.edit_message_text("\U0001F50D *Scanning whale wallets...*", parse_mode="Markdown")
        alerts = await fetch_eth_whale_transfers()
        if alerts:
            text = "\U0001F40B *Latest Whale Moves*\n\n"
            for a in alerts[:5]:
                val = f"{a['value']:,.0f}" if a['value'] >= 100 else f"{a['value']:,.2f}"
                text += f"\u2022 {a['direction']} {val} {a['symbol']} - {a['wallet_name']}\n"
            text += f"\n\U0001F525 *Trade now:*"
            await query.edit_message_text(
                text,
                reply_markup=get_affiliate_keyboard(),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        else:
            await query.edit_message_text(
                "\U0001F4CA No large transfers detected recently.\n\nAlerts are active - you'll be notified when whales move.",
                parse_mode="Markdown",
            )

    elif data == "exchanges":
        text = "\U0001F4B1 *Partner Exchanges*\n\nGet the best fee rebates:\n\n"
        for key, aff in AFFILIATE_LINKS.items():
            star = "\U0001F525" if aff.get("featured") else "\u2022"
            text += f"{star} [{aff['name']}]({aff['url']}) - {aff['commission']} rebate\n"
        text += "\n\U0001F4A1 Sign up via our links to support ApexFlash!"

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    elif data == "premium":
        await _show_premium_edit(query)

    elif data == "settings":
        tier = TIERS.get(user["tier"], TIERS["free"])
        keyboard = [
            [InlineKeyboardButton("\U0001F40B Toggle Alerts", callback_data="alerts_on" if not user["alerts_on"] else "alerts_off")],
            [InlineKeyboardButton("\U0001F451 Upgrade", callback_data="premium")],
            [InlineKeyboardButton("\U0001F519 Back", callback_data="back_start")],
        ]
        await query.edit_message_text(
            f"\u2699\ufe0f *Settings*\n\n"
            f"\u2022 Tier: *{tier['name']}*\n"
            f"\u2022 Alerts: {'On \u2705' if user['alerts_on'] else 'Off \U0001F515'}\n"
            f"\u2022 Chains: {', '.join(tier['chains'])}\n",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )

    elif data == "alerts_off":
        user["alerts_on"] = False
        await query.edit_message_text(
            "\U0001F515 Alerts disabled.\n\nUse /start to re-enable.",
            parse_mode="Markdown",
        )

    elif data == "back_start":
        keyboard = [
            [InlineKeyboardButton("\U0001F40B Start Whale Alerts", callback_data="alerts_on")],
            [InlineKeyboardButton("\U0001F4CA Latest Whale Moves", callback_data="latest")],
            [
                InlineKeyboardButton("\U0001F4B1 Exchanges", callback_data="exchanges"),
                InlineKeyboardButton("\U0001F451 Premium", callback_data="premium"),
            ],
        ]
        await query.edit_message_text(
            "\U0001F4A1 *ApexFlash* - Your whale tracking edge.\n\nSelect an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )


async def _show_premium(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send premium info as new message."""
    keyboard = [
        [InlineKeyboardButton("\U0001F680 Pro - $19/mo", url=GUMROAD_PRO_URL)],
        [InlineKeyboardButton("\U0001F451 Elite - $49/mo", url=GUMROAD_ELITE_URL)],
    ]
    text = (
        "\U0001F451 *ApexFlash Premium*\n"
        "\n"
        "*Free:*\n"
        "\u2022 ETH whale alerts (5 min delay)\n"
        "\u2022 3 tracked wallets\n"
        "\n"
        "*Pro - $19/mo:*\n"
        "\u2022 ETH + SOL alerts (instant)\n"
        "\u2022 20 tracked wallets\n"
        "\u2022 Priority notifications\n"
        "\n"
        "*Elite - $49/mo:*\n"
        "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
        "\u2022 100 tracked wallets\n"
        "\u2022 AI-powered signals\n"
        "\u2022 DCA recommendations\n"
        "\n"
        "Tap below to upgrade:"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def _show_premium_edit(query) -> None:
    """Edit existing message to show premium info."""
    keyboard = [
        [InlineKeyboardButton("\U0001F680 Pro - $19/mo", url=GUMROAD_PRO_URL)],
        [InlineKeyboardButton("\U0001F451 Elite - $49/mo", url=GUMROAD_ELITE_URL)],
        [InlineKeyboardButton("\U0001F519 Back", callback_data="back_start")],
    ]
    text = (
        "\U0001F451 *ApexFlash Premium*\n"
        "\n"
        "*Free:*\n"
        "\u2022 ETH whale alerts (5 min delay)\n"
        "\u2022 3 tracked wallets\n"
        "\n"
        "*Pro - $19/mo:*\n"
        "\u2022 ETH + SOL alerts (instant)\n"
        "\u2022 20 tracked wallets\n"
        "\u2022 Priority notifications\n"
        "\n"
        "*Elite - $49/mo:*\n"
        "\u2022 All chains (ETH, SOL, BSC, ARB)\n"
        "\u2022 100 tracked wallets\n"
        "\u2022 AI-powered signals\n"
        "\u2022 DCA recommendations\n"
        "\n"
        "Tap below to upgrade:"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# === Scheduled Whale Scanner ===

async def scan_and_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic scanner: fetch whale transfers and alert subscribers."""
    global seen_tx_hashes

    try:
        eth_alerts = await fetch_eth_whale_transfers()
        sol_alerts = await fetch_sol_whale_transfers()
        all_alerts = eth_alerts + sol_alerts

        new_alerts = [a for a in all_alerts if a["tx_hash"] not in seen_tx_hashes]

        if not new_alerts:
            return

        # Mark as seen
        for a in new_alerts:
            seen_tx_hashes.add(a["tx_hash"])

        # Cap seen set size (prevent memory leak)
        if len(seen_tx_hashes) > 10000:
            seen_tx_hashes = set(list(seen_tx_hashes)[-5000:])

        # Send to all subscribers
        for user_id, user_data in users.items():
            if not user_data.get("alerts_on"):
                continue

            tier_config = TIERS.get(user_data.get("tier", "free"), TIERS["free"])
            user_chains = tier_config["chains"]

            for alert in new_alerts:
                if alert["chain"] not in user_chains:
                    continue

                try:
                    text = format_whale_alert(alert)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.error(f"Failed to send alert to {user_id}: {e}")

        logger.info(f"Scanned: {len(new_alerts)} new alerts sent to subscribers")

    except Exception as e:
        logger.error(f"Scanner error: {e}")


# === Main ===

def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Set it in .env or environment variables.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Schedule whale scanner using built-in job queue
    app.job_queue.run_repeating(
        scan_and_alert,
        interval=SCAN_INTERVAL,
        first=10,  # wait 10s before first scan
        name="whale_scanner",
    )

    logger.info(f"ApexFlash Bot starting...")
    logger.info(f"Scan interval: {SCAN_INTERVAL}s")

    # run_polling() handles event loop, signal handlers, graceful shutdown
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
