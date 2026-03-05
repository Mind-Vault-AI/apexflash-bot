"""
ApexFlash MEGA BOT - Twitter/X Auto-Poster
Posts to @apexflashpro via Twitter API v2 (tweepy).
Free tier: 1,500 tweets/month — we use ~90/month (3/day).
"""
import random
import logging

logger = logging.getLogger(__name__)

# Try importing tweepy — graceful fallback if not installed
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.warning("tweepy not installed — Twitter posting disabled")


# ══════════════════════════════════════════════
# TWITTER CONTENT BANK
# Short, punchy tweets (max 280 chars each)
# Separate from Telegram posts — optimized for X
# ══════════════════════════════════════════════

TWEETS = [
    # ── FEATURE ──
    {
        "cat": "feature",
        "text": (
            "Buy & sell Solana tokens directly from Telegram.\n\n"
            "No DEX UI. No seed phrase exposed.\n"
            "Jupiter V6 best routes. 1% flat fee.\n\n"
            "Try it free \U0001f449 @ApexFlashBot\n\n"
            "#Solana #SOL #CryptoTrading #DeFi"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "Swap any Solana token in 3 taps:\n\n"
            "1\ufe0f\u20e3 Open @ApexFlashBot\n"
            "2\ufe0f\u20e3 Tap Trade \u2192 Buy/Sell\n"
            "3\ufe0f\u20e3 Confirm & done\n\n"
            "Your keys, your wallet, your control.\n\n"
            "#Solana #Trading #Crypto"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "Stop paying 2-3% fees on other trading bots.\n\n"
            "ApexFlash: 1% flat. No subscription needed.\n"
            "Jupiter V6 aggregator. Best routes. Auto slippage.\n\n"
            "Start free: @ApexFlashBot\n\n"
            "#Solana #DeFi #CryptoTrading"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "Your keys never leave your device.\n\n"
            "ApexFlash creates an encrypted Solana wallet inside Telegram.\n"
            "Fernet encryption. Export anytime. Non-custodial.\n\n"
            "@ApexFlashBot\n\n"
            "#Solana #Security #Crypto"
        ),
    },
    # ── WHALE ALERTS ──
    {
        "cat": "whale",
        "text": (
            "\U0001f40b Whale moves 50K+ SOL to exchange = potential sell.\n"
            "Whale withdraws = potential accumulation.\n\n"
            "These signals precede price moves by minutes.\n\n"
            "Free alerts: @ApexFlashBot\n\n"
            "#WhaleAlert #Solana #Crypto"
        ),
    },
    {
        "cat": "whale",
        "text": (
            "Follow the smart money.\n\n"
            "ApexFlash tracks wallets from Binance, Coinbase, Kraken, OKX & more.\n\n"
            "See large transfers before the market reacts.\n\n"
            "@ApexFlashBot\n\n"
            "#WhaleTracking #Solana #ETH"
        ),
    },
    {
        "cat": "whale",
        "text": (
            "Real-time whale alerts straight to Telegram.\n\n"
            "\u2022 ETH whale wallet tracking\n"
            "\u2022 SOL large transfers\n"
            "\u2022 Exchange inflow/outflow signals\n\n"
            "Free tier available \U0001f449 @ApexFlashBot\n\n"
            "#WhaleAlert #Crypto #DeFi"
        ),
    },
    # ── TIPS ──
    {
        "cat": "tip",
        "text": (
            "Trading tip: Slippage matters.\n\n"
            "Low-cap memecoins: 5-10% needed\n"
            "Blue chips (SOL, JUP): 0.5-1% is fine\n\n"
            "Always check price impact before confirming.\n\n"
            "#Solana #TradingTips #DeFi"
        ),
    },
    {
        "cat": "tip",
        "text": (
            "Pro move: Small test buy first (0.05 SOL).\n\n"
            "Confirm the token is legit.\n"
            "Then scale in with bigger size.\n\n"
            "ApexFlash supports custom amounts on every trade.\n\n"
            "#CryptoTrading #Solana #DYOR"
        ),
    },
    {
        "cat": "tip",
        "text": (
            "Never trade more than you can afford to lose.\n\n"
            "Built-in risk controls:\n"
            "\u2022 Max trade limit\n"
            "\u2022 SOL reserve for fees\n"
            "\u2022 Price impact warnings\n\n"
            "Trade smart. Not emotional.\n\n"
            "#Crypto #RiskManagement #Solana"
        ),
    },
    # ── CTA ──
    {
        "cat": "cta",
        "text": (
            "Why are you still using DEX UIs?\n\n"
            "Open Telegram. Tap buy. Done.\n"
            "No browser extensions. No connecting wallets to random sites.\n\n"
            "Just fast, clean Solana swaps.\n\n"
            "\U0001f449 @ApexFlashBot\n\n"
            "#Solana #DeFi #Trading"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "Free tier includes:\n\n"
            "\u2705 Solana token trading\n"
            "\u2705 Encrypted wallet\n"
            "\u2705 Basic whale alerts\n"
            "\u2705 Token search\n"
            "\u2705 Portfolio balance\n\n"
            "No credit card. Just open Telegram.\n\n"
            "@ApexFlashBot"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "Pro traders upgrade for $19/mo:\n\n"
            "\u2022 50 trades/day\n"
            "\u2022 Instant whale alerts\n"
            "\u2022 Multi-chain tracking\n"
            "\u2022 Priority execution\n"
            "\u2022 Referral earnings (25%)\n\n"
            "@ApexFlashBot \u2192 /upgrade\n\n"
            "#Solana #CryptoTrading"
        ),
    },
    # ── REFERRAL ──
    {
        "cat": "referral",
        "text": (
            "Earn from every trade your friends make.\n\n"
            "Share your referral link \u2192 friends trade \u2192 you earn 25% of fees.\n\n"
            "No limits. Lifetime earnings.\n\n"
            "@ApexFlashBot \u2192 /referral\n\n"
            "#PassiveIncome #Crypto #Solana"
        ),
    },
    # ── TRUST ──
    {
        "cat": "trust",
        "text": (
            "ApexFlash isn't another rug-pull bot.\n\n"
            "\u2022 1% transparent fee\n"
            "\u2022 Jupiter best-route aggregation\n"
            "\u2022 Helius RPC for reliability\n"
            "\u2022 24/7 uptime monitoring\n"
            "\u2022 Non-custodial wallets\n\n"
            "Try it: @ApexFlashBot\n\n"
            "#Solana #Security #DeFi"
        ),
    },
    {
        "cat": "trust",
        "text": (
            "Security-first architecture:\n\n"
            "\u2022 Non-custodial wallets\n"
            "\u2022 Fernet encryption\n"
            "\u2022 No database of private keys\n"
            "\u2022 Auto backups to you\n"
            "\u2022 Global kill switch\n\n"
            "Your money, your control.\n\n"
            "@ApexFlashBot\n\n"
            "#CryptoSecurity #Solana"
        ),
    },
    # ── EXCHANGE ──
    {
        "cat": "exchange",
        "text": (
            "Need a CEX? We got you.\n\n"
            "\u2022 Bitunix \u2014 50% fee rebate\n"
            "\u2022 MEXC \u2014 70% rebate, zero spot fees\n"
            "\u2022 BloFin \u2014 Copy trading built-in\n\n"
            "Check /exchanges in @ApexFlashBot\n\n"
            "#Crypto #Exchange #Trading"
        ),
    },
]


def get_scheduled_tweet(hour_utc: int) -> str:
    """Pick a tweet based on time of day (same logic as Telegram)."""
    if 6 <= hour_utc < 12:
        cats = ["tip", "whale", "trust"]
    elif 12 <= hour_utc < 18:
        cats = ["feature", "whale", "exchange"]
    else:
        cats = ["cta", "referral", "feature"]

    pool = [t for t in TWEETS if t["cat"] in cats]
    if not pool:
        pool = TWEETS
    return random.choice(pool)["text"]


def _create_client(api_key: str, api_secret: str,
                   access_token: str, access_secret: str) -> "tweepy.Client":
    """Create an authenticated tweepy v2 Client."""
    if not TWEEPY_AVAILABLE:
        raise RuntimeError("tweepy is not installed")
    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )


async def post_tweet(api_key: str, api_secret: str,
                     access_token: str, access_secret: str) -> bool:
    """Post a marketing tweet to @apexflashpro.

    Uses tweepy synchronously (Twitter API is sync) but wrapped
    for async context via the bot's job queue.
    """
    if not TWEEPY_AVAILABLE:
        logger.warning("tweepy not installed — skipping Twitter post")
        return False

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning("Twitter API keys not configured — skipping post")
        return False

    try:
        from datetime import datetime, timezone
        hour = datetime.now(timezone.utc).hour
        text = get_scheduled_tweet(hour)

        client = _create_client(api_key, api_secret, access_token, access_secret)
        response = client.create_tweet(text=text)

        if response and response.data:
            tweet_id = response.data.get("id", "unknown")
            logger.info(f"Tweet posted: https://x.com/apexflashpro/status/{tweet_id}")
            return True
        else:
            logger.error(f"Tweet post failed — no data in response: {response}")
            return False
    except tweepy.TooManyRequests:
        logger.warning("Twitter rate limit hit — skipping this post")
        return False
    except tweepy.Forbidden as e:
        logger.error(f"Twitter 403 Forbidden — check API permissions: {e}")
        return False
    except Exception as e:
        logger.error(f"Twitter post error: {e}")
        return False
