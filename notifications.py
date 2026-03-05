"""
ApexFlash MEGA BOT - Multi-Channel Notifications
Push whale alerts and trade notifications to Discord + Telegram channel.
Every notification = distribution = more users = more 1% fees.
"""
import logging
import aiohttp

from config import (
    DISCORD_WEBHOOK_URL, DISCORD_TRADE_WEBHOOK_URL,
    AFFILIATE_LINKS, WEBSITE_URL, CHANNEL_URL,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# DISCORD WEBHOOKS
# ══════════════════════════════════════════════

async def _send_discord_webhook(url: str, payload: dict) -> bool:
    """Send a message to a Discord webhook. Returns True on success."""
    if not url:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 204):
                    return True
                logger.warning(f"Discord webhook {resp.status}: {await resp.text()}")
                return False
    except Exception as e:
        logger.error(f"Discord webhook error: {e}")
        return False


def _discord_whale_embed(alert: dict, prices: dict) -> dict:
    """Build a Discord embed for a whale alert."""
    chain = alert["chain"]
    value = alert["value"]
    symbol = alert["symbol"]
    direction = alert["direction"]

    price = prices.get(symbol, 0)
    usd_value = value * price
    value_str = f"{value:,.0f}" if value >= 100 else f"{value:,.2f}"
    usd_str = f"${usd_value:,.0f}" if usd_value > 0 else ""

    color = 0xFF4444 if direction == "OUT" else 0x00CC66  # Red or Green

    # Explorer link
    if chain == "ETH":
        explorer = f"https://etherscan.io/tx/{alert['tx_hash']}"
    elif chain == "SOL":
        explorer = f"https://solscan.io/tx/{alert['tx_hash']}"
    else:
        explorer = ""

    # Pick a featured affiliate
    featured = [(k, v) for k, v in AFFILIATE_LINKS.items() if v.get("featured")]
    aff = featured[0][1] if featured else None

    fields = [
        {"name": "Amount", "value": f"**{value_str} {symbol}** {usd_str}", "inline": True},
        {"name": "Chain", "value": chain, "inline": True},
        {"name": "Direction", "value": direction, "inline": True},
        {"name": "From", "value": f"`{alert['from_label']}`", "inline": True},
        {"name": "To", "value": f"`{alert['to_label']}`", "inline": True},
    ]

    if explorer:
        fields.append({"name": "Transaction", "value": f"[View on Explorer]({explorer})", "inline": False})

    embed = {
        "title": f"{'🔴' if direction == 'OUT' else '🟢'} WHALE ALERT | {chain}",
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"ApexFlash | Trade with 1% fee | {WEBSITE_URL}",
        },
    }

    # Build message with CTA
    content = ""
    if aff:
        content = f"🔥 **Trade now on [{aff['name']}]({aff['url']})** — {aff['commission']} fee rebate!\n"
    content += f"🤖 **Start trading**: https://t.me/ApexFlashBot"

    return {"content": content, "embeds": [embed]}


def _discord_trade_embed(user_name: str, action: str, amount: str,
                         token: str, tx_sig: str, fee_sol: float) -> dict:
    """Build a Discord embed for a trade notification (social proof)."""
    color = 0x00CC66 if action == "BUY" else 0xFF9900

    embed = {
        "title": f"{'💰' if action == 'BUY' else '💸'} Trade Executed",
        "color": color,
        "fields": [
            {"name": "Action", "value": action, "inline": True},
            {"name": "Amount", "value": amount, "inline": True},
            {"name": "Token", "value": token, "inline": True},
            {"name": "Fee", "value": f"{fee_sol:.4f} SOL (1%)", "inline": True},
        ],
        "footer": {
            "text": f"ApexFlash | Swap any Solana token | {WEBSITE_URL}",
        },
    }

    if tx_sig:
        embed["fields"].append({
            "name": "Transaction",
            "value": f"[View on Solscan](https://solscan.io/tx/{tx_sig})",
            "inline": False,
        })

    content = "🤖 **Trade on ApexFlash**: https://t.me/ApexFlashBot — best prices, 1% fee"

    return {"content": content, "embeds": [embed]}


async def notify_discord_whale(alert: dict, prices: dict) -> bool:
    """Send whale alert to Discord."""
    if not DISCORD_WEBHOOK_URL:
        return False
    payload = _discord_whale_embed(alert, prices)
    return await _send_discord_webhook(DISCORD_WEBHOOK_URL, payload)


async def notify_discord_trade(user_name: str, action: str, amount: str,
                               token: str, tx_sig: str, fee_sol: float) -> bool:
    """Send trade notification to Discord (social proof)."""
    webhook = DISCORD_TRADE_WEBHOOK_URL or DISCORD_WEBHOOK_URL
    if not webhook:
        return False
    payload = _discord_trade_embed(user_name, action, amount, token, tx_sig, fee_sol)
    return await _send_discord_webhook(webhook, payload)


# ══════════════════════════════════════════════
# TELEGRAM CHANNEL NOTIFICATIONS
# ══════════════════════════════════════════════

async def notify_telegram_channel(bot, alert_text: str, alert_kb=None,
                                  channel_id: str = "") -> bool:
    """Post an alert to the public Telegram channel.

    Args:
        bot: telegram.Bot instance
        alert_text: Formatted alert message (Markdown)
        alert_kb: InlineKeyboardMarkup (optional)
        channel_id: Channel ID or @username (e.g. "@ApexFlashAlerts")

    Returns True on success.
    """
    from config import ALERT_CHANNEL_ID
    target = channel_id or ALERT_CHANNEL_ID
    if not target:
        return False

    try:
        await bot.send_message(
            chat_id=target,
            text=alert_text,
            reply_markup=alert_kb,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.error(f"Telegram channel post failed: {e}")
        return False


async def notify_channel_trade(bot, action: str, sol_amount: float,
                               token_name: str, tx_sig: str,
                               channel_id: str = "") -> bool:
    """Post trade notification to Telegram channel (social proof)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from config import ALERT_CHANNEL_ID

    target = channel_id or ALERT_CHANNEL_ID
    if not target:
        return False

    emoji = "💰" if action == "BUY" else "💸"
    text = (
        f"{emoji} *Trade Alert*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"Someone just {'bought' if action == 'BUY' else 'sold'} "
        f"*{token_name}* for *{sol_amount:.2f} SOL*\n"
        "\n"
        f"🔗 [View Transaction](https://solscan.io/tx/{tx_sig})\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Trade any Solana token with 1% fee!\n"
        "👉 Start now: @ApexFlashBot"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Start Trading", url="https://t.me/ApexFlashBot")],
    ])

    try:
        await bot.send_message(
            chat_id=target,
            text=text,
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.error(f"Telegram channel trade post failed: {e}")
        return False
