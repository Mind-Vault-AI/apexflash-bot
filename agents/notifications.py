"""
ApexFlash MEGA BOT - Multi-Channel Notifications
Push whale alerts and trade notifications to Discord + Telegram channel.
Every notification = distribution = more users = more 1% fees.
"""
import logging
import asyncio
import aiohttp

from core.config import (
    BOT_USERNAME,
    DISCORD_WEBHOOK_URL, DISCORD_TRADE_WEBHOOK_URL,
    AFFILIATE_LINKS, WEBSITE_URL, CHANNEL_URL, ADMIN_IDS,
)
from agents.social_manager import handle_viral_dispatch

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
    content += f"🤖 **Start trading**: https://t.me/{BOT_USERNAME}"

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

    content = f"🤖 **Trade on ApexFlash**: https://t.me/{BOT_USERNAME} — best prices, 1% fee"

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

async def notify_telegram_channel(bot, alert: dict, alert_text: str, alert_kb=None,
                                  channel_id: str = "") -> bool:
    """Post an alert to the public Telegram channel (Gold Signals)."""
    from core.config import ALERT_CHANNEL_ID
    # Trigger Social Manager for Viral Viral Drop (v3.15.2)
    bot_info = await bot.get_me() if bot else None
    bot_username = bot_info.username if bot_info else "apexflash_bot"
    admin_id = ADMIN_IDS[0] if ADMIN_IDS else 0
    asyncio.create_task(handle_viral_dispatch(alert, bot_username, admin_id))

    target = channel_id or ALERT_CHANNEL_ID
    if not target:
        return False

    try:
        await bot.send_message(
            chat_id=target,
            text=alert_text,
            reply_markup=alert_kb,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.error(f"Telegram channel post failed: {e}")
        return False


async def notify_channel_trade(bot, action: str, sol_amount: float,
                               token_name: str, tx_sig: str,
                               channel_id: str = "",
                               token_mint: str = "",
                               sol_price: float = 0,
                               fee_sol: float = 0) -> bool:
    """Post rich trade notification to Telegram channel (social proof)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from core.config import ALERT_CHANNEL_ID, ADMIN_IDS

    target = channel_id or ALERT_CHANNEL_ID
    if not target:
        return False

    usd_value = f" (${sol_amount * sol_price:,.2f})" if sol_price else ""
    action_emoji = "🟢" if action == "BUY" else "🔴"
    action_word = "BOUGHT" if action == "BUY" else "SOLD"

    text = (
        f"{action_emoji} <b>{action_word} {token_name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"💎 Token: <b>{token_name}</b>\n"
        f"💰 Amount: <b>{sol_amount:.2f} SOL</b>{usd_value}\n"
    )
    if fee_sol:
        text += f"💸 Fee: <b>{fee_sol:.4f} SOL</b> (1%)\n"
    text += (
        "\n"
        f"🔗 <a href='https://solscan.io/tx/{tx_sig}'>View on Solscan</a>\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>ApexFlash</b> — Trade any Solana token\n"
        f"🤖 Start now → @{BOT_USERNAME}"
    )

    ref_id = ADMIN_IDS[0] if ADMIN_IDS else 0
    # USE DEEP LINKS IN CHANNEL (callback_data is NOT supported in channels!)
    trade_url = f"https://t.me/{BOT_USERNAME}?start=buy_{token_mint}" if token_mint else f"https://t.me/{BOT_USERNAME}?start=ref_{ref_id}"
    aff_url = f"https://t.me/{BOT_USERNAME}?start=aff_mexc"  # Default trackable deep link

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 1-Tap Auto-Trade", url=trade_url)],
        [InlineKeyboardButton("🔗 Claim Partner Bonus", url=aff_url)],
        [InlineKeyboardButton("📊 Join Alerts", url="https://t.me/ApexFlashAlerts")],
    ])

    try:
        chart_url = None
        if token_mint:
            try:
                from exchanges.jupiter import get_token_chart_url
                chart_url = await get_token_chart_url(token_mint, hours=24)
            except Exception:
                pass

        if chart_url:
            await bot.send_photo(
                chat_id=target,
                photo=chart_url,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=target,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return True
    except Exception as e:
        logger.error(f"Telegram channel trade post failed: {e}")
        return False


# ══════════════════════════════════════════════
# DAILY DIGEST
# ══════════════════════════════════════════════

def _discord_digest_embed(stats: dict) -> dict:
    """Build a Discord embed for the daily digest."""
    trades = stats.get("trades_today", 0)
    volume = stats.get("volume_today_usd", 0)
    active = stats.get("active_traders", 0)
    total_users = stats.get("total_users", 0)
    total_trades = stats.get("trades_total", 0)

    embed = {
        "title": "\U0001f4ca ApexFlash Daily Digest",
        "color": 0x7C3AED,
        "fields": [
            {"name": "Trades Today", "value": str(trades), "inline": True},
            {"name": "Volume Today", "value": f"${volume:,.0f}", "inline": True},
            {"name": "Active Traders", "value": str(active), "inline": True},
            {"name": "Total Users", "value": str(total_users), "inline": True},
            {"name": "All-Time Trades", "value": str(total_trades), "inline": True},
        ],
        "footer": {
            "text": f"ApexFlash | Trade any Solana token | {WEBSITE_URL}",
        },
    }

    content = (
        "\U0001f4ca **Daily Digest** \u2014 Here's what happened on ApexFlash today!\n"
        f"\U0001f916 **Start trading**: https://t.me/{BOT_USERNAME}"
    )

    return {"content": content, "embeds": [embed]}


async def notify_discord_digest(stats: dict) -> bool:
    """Send daily digest to Discord."""
    webhook = DISCORD_TRADE_WEBHOOK_URL or DISCORD_WEBHOOK_URL
    if not webhook:
        return False
    payload = _discord_digest_embed(stats)
    return await _send_discord_webhook(webhook, payload)


async def notify_channel_digest(bot, stats: dict,
                                channel_id: str = "") -> bool:
    """Post daily digest to Telegram channel."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from core.config import ALERT_CHANNEL_ID

    target = channel_id or ALERT_CHANNEL_ID
    if not target:
        return False

    trades = stats.get("trades_today", 0)
    volume = stats.get("volume_today_usd", 0)
    active = stats.get("active_traders", 0)
    total_users = stats.get("total_users", 0)

    text = (
        "\U0001f4ca *ApexFlash Daily Digest*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\n"
        f"\U0001f4b0 *{trades}* trades executed\n"
        f"\U0001f4b5 *${volume:,.0f}* volume\n"
        f"\U0001f465 *{active}* active traders\n"
        f"\U0001f310 *{total_users}* total users\n"
        "\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f916 Trade any Solana token with 1% fee!\n"
        f"\U0001f449 @{BOT_USERNAME}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f916 Start Trading", url=f"https://t.me/{BOT_USERNAME}")],
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
        logger.error(f"Telegram digest post failed: {e}")
        return False
