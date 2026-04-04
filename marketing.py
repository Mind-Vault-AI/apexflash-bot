"""
ApexFlash MEGA BOT - Marketing Auto-Poster
Scheduled Telegram channel posts to drive growth.
Posts rotate through a content bank 3x daily.
"""
import random
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONTENT BANK — Rotate through these posts
# Categories: feature, whale, tip, cta, social
# ══════════════════════════════════════════════

POSTS = [
    # ── FEATURE HIGHLIGHTS ──
    {
        "cat": "feature",
        "text": (
            "\U0001f680 *ApexFlash Trading Bot*\n\n"
            "Buy & sell Solana tokens directly from Telegram.\n"
            "No DEX UI needed. No seed phrase exposed.\n\n"
            "\u2022 Instant Jupiter swaps\n"
            "\u2022 Built-in encrypted wallet\n"
            "\u2022 1% flat fee (no hidden costs)\n"
            "\u2022 Real-time whale alerts\n\n"
            "\U0001f449 Start free: @ApexFlashBot"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "\u26a1 *Swap any Solana token in 3 taps*\n\n"
            "1\ufe0f\u20e3 Open @ApexFlashBot\n"
            "2\ufe0f\u20e3 Tap Trade \u2192 Buy/Sell\n"
            "3\ufe0f\u20e3 Confirm & done\n\n"
            "Jupiter V6 aggregator. Best routes. Auto slippage.\n"
            "Your keys, your wallet, your control.\n\n"
            "\U0001f510 All wallets encrypted with military-grade Fernet."
        ),
    },
    {
        "cat": "feature",
        "text": (
            "\U0001f4b0 *Stop paying 2-3% on other bots*\n\n"
            "ApexFlash charges a flat 1% per trade.\n"
            "No subscription needed for basic trading.\n\n"
            "Compare:\n"
            "\u2022 BonkBot: 1% + tip\n"
            "\u2022 Trojan: 0.9% + priority fee\n"
            "\u2022 ApexFlash: 1% all-in\n\n"
            "Try it free \U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "\U0001f40b *Whale Alerts \u2192 Telegram*\n\n"
            "Know what the big money is doing before everyone else.\n\n"
            "\u2022 ETH whale wallet tracking\n"
            "\u2022 SOL large transfers\n"
            "\u2022 Exchange inflow/outflow signals\n"
            "\u2022 AI-powered analysis (Elite)\n\n"
            "Free alerts: @ApexFlashBot\n"
            "Pro alerts: instant, multi-chain, custom thresholds"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "\U0001f6e1 *Your keys. Your wallet. Always.*\n\n"
            "ApexFlash creates an encrypted Solana wallet inside Telegram.\n"
            "We never see your private key.\n\n"
            "\u2022 Fernet encryption (AES-128-CBC)\n"
            "\u2022 Export your key anytime\n"
            "\u2022 Backup sent to you after every trade\n"
            "\u2022 No custodial risk\n\n"
            "Start: @ApexFlashBot"
        ),
    },
    # ── TRADING TIPS ──
    {
        "cat": "tip",
        "text": (
            "\U0001f4ca *Trading Tip: Slippage matters*\n\n"
            "High slippage = you lose more per trade.\n"
            "ApexFlash defaults to 3% but you can adjust.\n\n"
            "Low-cap memecoins: 5-10% needed\n"
            "Blue chips (SOL, JUP): 0.5-1% is fine\n\n"
            "Always check price impact before confirming.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "tip",
        "text": (
            "\U0001f4a1 *Pro move: Set custom buy amounts*\n\n"
            "Don't always ape the same size.\n\n"
            "Small test buy (0.05 SOL) first.\n"
            "Confirm the token is legit.\n"
            "Then scale in with bigger size.\n\n"
            "ApexFlash supports custom SOL amounts on every trade.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "tip",
        "text": (
            "\u26a0\ufe0f *Never trade more than you can afford to lose*\n\n"
            "ApexFlash has built-in risk controls:\n"
            "\u2022 Max trade limit (10 SOL default)\n"
            "\u2022 SOL reserve (keeps rent for fees)\n"
            "\u2022 Daily trade limit\n"
            "\u2022 Price impact warnings\n\n"
            "Trade smart. Not emotional.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    # ── CALL TO ACTION ──
    {
        "cat": "cta",
        "text": (
            "\U0001f525 *Why are you still using DEX UIs?*\n\n"
            "Open Telegram. Tap buy. Done.\n"
            "No browser extensions. No gas estimation.\n"
            "No connecting wallets to random sites.\n\n"
            "Just fast, clean Solana swaps.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "\U0001f3af *Free tier includes:*\n\n"
            "\u2705 Solana token trading\n"
            "\u2705 Built-in encrypted wallet\n"
            "\u2705 Basic whale alerts\n"
            "\u2705 Token search by name/symbol\n"
            "\u2705 Portfolio balance check\n\n"
            "No credit card. No signup form.\n"
            "Just open Telegram:\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "\U0001f680 *Pro traders upgrade for $19/mo:*\n\n"
            "\u2022 50 trades/day (vs 5 free)\n"
            "\u2022 Instant whale alerts (no delay)\n"
            "\u2022 Multi-chain tracking\n"
            "\u2022 Priority execution\n"
            "\u2022 Referral earnings (25% share)\n\n"
            "Pay with SOL or card.\n"
            "\U0001f449 @ApexFlashBot \u2192 /upgrade"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "\U0001f451 *Elite tier ($49/mo) unlocks everything:*\n\n"
            "\u2022 Unlimited trades\n"
            "\u2022 AI-powered signals\n"
            "\u2022 Copy trading (coming soon)\n"
            "\u2022 DCA automation\n"
            "\u2022 1-on-1 onboarding\n\n"
            "Built for serious Solana traders.\n"
            "\U0001f449 @ApexFlashBot \u2192 /upgrade"
        ),
    },
    # ── WHALE / MARKET ──
    {
        "cat": "whale",
        "text": (
            "\U0001f40b *Why whale tracking matters:*\n\n"
            "When a whale moves 50K+ SOL to an exchange = potential sell.\n"
            "When a whale withdraws = potential accumulation.\n\n"
            "These signals precede price moves by minutes to hours.\n\n"
            "Get free alerts: @ApexFlashBot"
        ),
    },
    {
        "cat": "whale",
        "text": (
            "\U0001f4c8 *Follow the smart money*\n\n"
            "ApexFlash tracks wallets from:\n"
            "\u2022 Binance, Coinbase, Kraken\n"
            "\u2022 OKX, Bitfinex, MEXC\n"
            "\u2022 Robinhood, Arbitrum Bridge\n\n"
            "See large transfers before the market reacts.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    # ── REFERRAL ──
    {
        "cat": "referral",
        "text": (
            "\U0001f91d *Earn from every trade your friends make*\n\n"
            "ApexFlash referral program:\n"
            "\u2022 Share your /referral link\n"
            "\u2022 Friends trade using ApexFlash\n"
            "\u2022 You earn 25% of platform fees\n\n"
            "No limits. Lifetime earnings.\n"
            "\U0001f449 @ApexFlashBot \u2192 /referral"
        ),
    },
    # ── EXCHANGE AFFILIATE ──
    {
        "cat": "exchange",
        "text": (
            "\U0001f4b1 *Need a CEX? We got you.*\n\n"
            "ApexFlash partners with top exchanges:\n\n"
            "\u2022 Bitunix \u2014 50% fee rebate\n"
            "\u2022 MEXC \u2014 70% fee rebate, zero spot fees\n"
            "\u2022 BloFin \u2014 Copy trading built-in\n\n"
            "Check /exchanges in @ApexFlashBot for all deals."
        ),
    },
    # ── TRUST / SAFETY ──
    {
        "cat": "trust",
        "text": (
            "\U0001f512 *Security-first architecture:*\n\n"
            "\u2022 Non-custodial wallets\n"
            "\u2022 Fernet encryption (military-grade)\n"
            "\u2022 No database of private keys\n"
            "\u2022 Automatic backups to you\n"
            "\u2022 Global kill switch for emergencies\n"
            "\u2022 Open-source risk controls\n\n"
            "Your money, your control.\n"
            "\U0001f449 @ApexFlashBot"
        ),
    },
    {
        "cat": "trust",
        "text": (
            "\u2699\ufe0f *Built different:*\n\n"
            "ApexFlash isn't another rug-pull bot.\n\n"
            "\u2022 1% transparent fee (no hidden markup)\n"
            "\u2022 Jupiter best-route aggregation\n"
            "\u2022 Helius RPC for reliability\n"
            "\u2022 24/7 uptime monitoring\n"
            "\u2022 Admin heartbeat every hour\n\n"
            "Try it: @ApexFlashBot"
        ),
    },
]

# ── Dynamic Social Proof Engine (v3.18.0) ─────────────────────────────────────

async def get_social_proof_post() -> str:
    """Generate high-conversion social proof based on real bot data."""
    from persistence import get_referral_leaderboard, platform_stats
    
    # 1. Referral Success
    top_refs = get_referral_leaderboard(limit=1)
    if top_refs:
        ref = top_refs[0]
        # Anonymize user ID
        anon_name = f"User_{str(ref['user_id'])[-4:]}"
        return (
            f"🔥 *SOCIAL PROOF: THE GODMODE SCALE*\n"
            f"{'━' * 22}\n"
            f"🏆 *{anon_name}* just hit a new milestone!\n"
            f"💰 Total Referral Earnings: `{ref['total_sol']:.2f} SOL`\n"
            f"\n"
            f"They aren't even trading—just sharing the link.\n"
            f"🚀 **Start your Affiliate Empire:** @ApexFlashBot"
        )
    
    # 2. Platform Volume Success (Fallback)
    vol = platform_stats.get("volume_total_usd", 0)
    if vol > 0:
        return (
            f"📈 *PLATFORM DOMINANCE*\n"
            f"{'━' * 22}\n"
            f"ApexFlash users have traded over *${vol:,.0f}* in volume!\n"
            f"⚡ Proof that the fastest swaps are on Telegram.\n"
            f"\n"
            f"Join the smart money: @ApexFlashBot"
        )

    return random.choice(POSTS)["text"]


    if 6 <= hour_utc < 12:
        cats = ["tip", "whale", "trust"]
    elif 12 <= hour_utc < 18:
        cats = ["feature", "whale", "exchange"]
    else:
        cats = ["cta", "referral", "feature"]

    pool = [p for p in POSTS if p["cat"] in cats]
    if not pool:
        pool = POSTS
    return random.choice(pool)["text"]


async def post_to_channel(bot, channel_id: str) -> bool:
    """Post a marketing message to the Telegram channel."""
    if not channel_id:
        logger.warning("No ALERT_CHANNEL_ID set — skipping marketing post")
        return False
    try:
        hour = datetime.now(timezone.utc).hour
        # 30% chance to send a Dynamic Social Proof post
        if random.random() < 0.3:
            text = await get_social_proof_post()
        else:
            text = get_scheduled_post(hour)
            
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        logger.info(f"Marketing post sent to {channel_id}")
        return True
    except Exception as e:
        logger.error(f"Marketing post error: {e}")
        return False
