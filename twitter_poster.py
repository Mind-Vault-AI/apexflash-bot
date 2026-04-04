from __future__ import annotations
from config import BOT_USERNAME
"""
ApexFlash MEGA BOT - Twitter/X Auto-Poster + Analytics
Posts to @MindVault_ai via Twitter API v2 (tweepy).
Pay-per-use plan: ~90 tweets/month (3/day).

Analytics features:
- Tracks all posted tweets (in-memory, survives within session)
- Fetches engagement metrics (impressions, likes, retweets, replies)
- Smart content rotation: boosts categories that perform well
- /tweetstats admin command for performance overview
"""

import random
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

# Try importing tweepy — graceful fallback if not installed
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.warning("tweepy not installed — Twitter posting disabled")


# ══════════════════════════════════════════════
# TWEET HISTORY & ANALYTICS (in-memory)
# ══════════════════════════════════════════════

# Stores: [{"id": str, "cat": str, "text": str, "ts": datetime, "metrics": dict}]
tweet_history: list[dict] = []

# Category performance scores (higher = more engagement)
# Starts equal, adjusts based on real engagement data
category_scores: dict[str, float] = {
    "feature": 1.0,
    "whale": 1.0,
    "tip": 1.0,
    "cta": 1.0,
    "referral": 1.0,
    "trust": 1.0,
    "exchange": 1.0,
}

# Track recently used tweets to avoid repeats
_recent_indices: list[int] = []


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
            "Try it free \U0001f449 @{BOT_USERNAME}\n\n"
            "#Solana #SOL #CryptoTrading #DeFi"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "Swap any Solana token in 3 taps:\n\n"
            "1\ufe0f\u20e3 Open @{BOT_USERNAME}\n"
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
            "Start free: @{BOT_USERNAME}\n\n"
            "#Solana #DeFi #CryptoTrading"
        ),
    },
    {
        "cat": "feature",
        "text": (
            "Your keys never leave your device.\n\n"
            "ApexFlash creates an encrypted Solana wallet inside Telegram.\n"
            "Fernet encryption. Export anytime. Non-custodial.\n\n"
            "@{BOT_USERNAME}\n\n"
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
            "Free alerts: @{BOT_USERNAME}\n\n"
            "#WhaleAlert #Solana #Crypto"
        ),
    },
    {
        "cat": "whale",
        "text": (
            "Follow the smart money.\n\n"
            "ApexFlash tracks wallets from Binance, Coinbase, Kraken, OKX & more.\n\n"
            "See large transfers before the market reacts.\n\n"
            "@{BOT_USERNAME}\n\n"
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
            "Free tier available \U0001f449 @{BOT_USERNAME}\n\n"
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
            "\U0001f449 @{BOT_USERNAME}\n\n"
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
            "@{BOT_USERNAME}"
        ),
    },
    {
        "cat": "cta",
        "text": (
            "Flash Pro — $9.99/mo:\n\n"
            "\u2022 Unlimited trades\n"
            "\u2022 Instant whale alerts\n"
            "\u2022 Copy trading\n"
            "\u2022 DCA bot\n"
            "\u2022 Earn up to 35% referral fees\n\n"
            "@{BOT_USERNAME} \u2192 /upgrade\n\n"
            "#Solana #CryptoTrading"
        ),
    },
    # ── REFERRAL ──
    {
        "cat": "referral",
        "text": (
            "Earn from every trade your friends make.\n\n"
            "Share your referral link \u2192 friends trade \u2192 you earn up to 35% of fees.\n\n"
            "No limits. Lifetime earnings.\n\n"
            "@{BOT_USERNAME} \u2192 /referral\n\n"
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
            "Try it: @{BOT_USERNAME}\n\n"
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
            "@{BOT_USERNAME}\n\n"
            "#CryptoSecurity #Solana"
        ),
    },
    # ── EXCHANGE ──
    {
        "cat": "exchange",
        "text": (
            "Need a CEX? We got you.\n\n"
            "\u2022 Bitunix \u2014 50% fee rebate + $8K bonus\n"
            "\u2022 MEXC \u2014 70% rebate, zero spot fees\n"
            "\u2022 BloFin \u2014 Copy trading built-in\n"
            "\u2022 Gate.io \u2014 40% rebate + $6.6K bonus\n\n"
            "All deals: apexflash.pro\n\n"
            "#Crypto #Exchange #Trading"
        ),
    },
]


# ══════════════════════════════════════════════
# ANALYTICS: Fetch engagement metrics
# ══════════════════════════════════════════════


def _get_api_v1(api_key: str, api_secret: str,
                access_token: str, access_secret: str) -> Optional["tweepy.API"]:
    """Create authenticated tweepy v1.1 API for media upload."""
    if not TWEEPY_AVAILABLE:
        return None
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    return tweepy.API(auth)


def _get_client(api_key: str, api_secret: str,
                access_token: str, access_secret: str) -> Optional["tweepy.Client"]:
    """Create authenticated tweepy v2 Client."""
    if not TWEEPY_AVAILABLE:
        return None
    if not all([api_key, api_secret, access_token, access_secret]):
        return None
    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )


def fetch_tweet_metrics(client: "tweepy.Client", tweet_ids: list[str]) -> dict:
    """Fetch public_metrics for a list of tweet IDs.

    Returns: {tweet_id: {impressions, likes, retweets, replies, quotes, bookmarks}}
    """
    if not tweet_ids or not client:
        return {}

    metrics = {}
    try:
        # Twitter API allows up to 100 tweet IDs per request
        batch = tweet_ids[:100]
        response = client.get_tweets(
            ids=batch,
            tweet_fields=["public_metrics", "created_at"],
        )
        if response and response.data:
            for tweet in response.data:
                pm = tweet.public_metrics or {}
                metrics[str(tweet.id)] = {
                    "impressions": pm.get("impression_count", 0),
                    "likes": pm.get("like_count", 0),
                    "retweets": pm.get("retweet_count", 0),
                    "replies": pm.get("reply_count", 0),
                    "quotes": pm.get("quote_count", 0),
                    "bookmarks": pm.get("bookmark_count", 0),
                }
    except Exception as e:
        logger.error(f"Failed to fetch tweet metrics: {e}")

    return metrics


def update_history_metrics(api_key: str, api_secret: str,
                           access_token: str, access_secret: str) -> int:
    """Fetch metrics for all tracked tweets and update history.

    Returns number of tweets updated.
    """
    if not tweet_history:
        return 0

    client = _get_client(api_key, api_secret, access_token, access_secret)
    if not client:
        return 0

    ids = [t["id"] for t in tweet_history if t.get("id")]
    if not ids:
        return 0

    metrics = fetch_tweet_metrics(client, ids)

    updated = 0
    for entry in tweet_history:
        tid = entry.get("id")
        if tid and tid in metrics:
            entry["metrics"] = metrics[tid]
            updated += 1

    # Update category scores based on engagement
    _recalculate_category_scores()

    return updated


def _recalculate_category_scores():
    """Recalculate category scores based on engagement data.

    Uses engagement rate: (likes + retweets + replies) / impressions
    Falls back to absolute engagement if impressions are 0.
    """
    cat_engagement: dict[str, list[float]] = {}

    for entry in tweet_history:
        m = entry.get("metrics")
        if not m:
            continue

        cat = entry.get("cat", "unknown")
        impressions = m.get("impressions", 0)
        engagement = m.get("likes", 0) + m.get("retweets", 0) + m.get("replies", 0)

        if impressions > 0:
            rate = engagement / impressions * 100  # engagement rate %
        else:
            rate = engagement * 0.1  # fallback: raw engagement scaled down

        if cat not in cat_engagement:
            cat_engagement[cat] = []
        cat_engagement[cat].append(rate)

    # Update scores: average engagement rate per category
    for cat, rates in cat_engagement.items():
        if rates:
            avg = sum(rates) / len(rates)
            # Score range: 0.3 (worst) to 3.0 (best) — smoothed
            category_scores[cat] = max(0.3, min(3.0, 0.5 + avg * 2))

    if cat_engagement:
        logger.info(f"Category scores updated: {category_scores}")


# ══════════════════════════════════════════════
# SMART CONTENT SELECTION
# ══════════════════════════════════════════════

def _get_live_stats() -> dict:
    """Fetch live stats from Redis for data-driven tweets."""
    try:
        from persistence import get_win_rate
        wr = get_win_rate()
        if wr and wr.get("total", 0) > 0:
            return wr
    except Exception:
        pass
    return {}


def _make_live_tweet(stats: dict) -> tuple[str, str] | None:
    """Generate a tweet with real platform data. Returns (text, cat) or None."""
    if not stats or stats.get("total", 0) < 3:
        return None

    total = stats["total"]
    win_rate = stats.get("win_rate", 0)
    pnl = stats.get("total_pnl_sol", 0)
    wins = stats.get("wins", 0)

    templates = [
        (
            f"\U0001f4ca ApexFlash Stats Update\n\n"
            f"\u2022 {total} trades executed\n"
            f"\u2022 {win_rate}% win rate\n"
            f"\u2022 {wins} winning trades\n\n"
            f"AI-graded whale signals. Free on Telegram.\n\n"
            f"\U0001f449 @{BOT_USERNAME}\n"
            f"apexflash.pro\n\n"
            f"#Solana #WhaleAlert #CryptoTrading"
        ),
        (
            f"{win_rate}% win rate across {total} trades.\n\n"
            f"We don't predict. We follow the whales.\n\n"
            f"\u2022 Real-time ETH + SOL whale tracking\n"
            f"\u2022 AI signal grading (A-D)\n"
            f"\u2022 1-tap copy trading\n\n"
            f"Free: @{BOT_USERNAME}\n\n"
            f"#Crypto #WhaleTracking #Solana"
        ),
        (
            f"Whales moved. We alerted. Traders profited.\n\n"
            f"\U0001f40b {total} signals tracked\n"
            f"\U0001f3af {win_rate}% accuracy\n"
            f"\U0001f4b0 {pnl:+.2f} SOL total P/L\n\n"
            f"See for yourself \U0001f449 @{BOT_USERNAME}\n\n"
            f"#WhaleAlert #Solana #DeFi"
        ),
    ]

    text = random.choice(templates)
    return text, "live_stats"


def get_scheduled_tweet(hour_utc: int) -> tuple[str, str]:
    """Pick a tweet based on time of day + engagement scores.
    Prioritizes live data tweets when stats are available.

    Returns: (text, category)
    """
    # 40% chance of live stats tweet (if data available)
    if random.random() < 0.4:
        stats = _get_live_stats()
        live = _make_live_tweet(stats)
        if live:
            return live

    if 6 <= hour_utc < 12:
        cats = ["tip", "whale", "trust"]
    elif 12 <= hour_utc < 18:
        cats = ["feature", "whale", "exchange"]
    else:
        cats = ["cta", "referral", "feature"]

    pool = [(i, t) for i, t in enumerate(TWEETS) if t["cat"] in cats]
    if not pool:
        pool = list(enumerate(TWEETS))

    # Filter out recently used tweets (avoid repeats within last 6 posts)
    if len(pool) > 3:
        pool = [(i, t) for i, t in pool if i not in _recent_indices[-6:]]
        if not pool:
            pool = [(i, t) for i, t in enumerate(TWEETS) if t["cat"] in cats]

    # Weighted random selection based on category scores
    weights = [category_scores.get(t["cat"], 1.0) for _, t in pool]
    total = sum(weights)
    weights = [w / total for w in weights]

    chosen_idx, chosen = random.choices(pool, weights=weights, k=1)[0]

    # Track to avoid repeats
    _recent_indices.append(chosen_idx)
    if len(_recent_indices) > 12:
        _recent_indices.pop(0)

    return chosen["text"], chosen["cat"]


# ══════════════════════════════════════════════
# STATS FORMATTING (for /tweetstats command)
# ══════════════════════════════════════════════

def get_stats_text() -> str:
    """Format tweet analytics for the /tweetstats admin command."""
    if not tweet_history:
        return (
            "\U0001f4ca *Twitter Analytics*\n\n"
            "No tweets tracked yet.\n"
            "Tweets are tracked after the bot posts them.\n"
            "Check back after the next scheduled post."
        )

    total = len(tweet_history)
    with_metrics = sum(1 for t in tweet_history if t.get("metrics"))

    # Aggregate metrics
    total_impressions = 0
    total_likes = 0
    total_retweets = 0
    total_replies = 0
    total_bookmarks = 0

    for entry in tweet_history:
        m = entry.get("metrics", {})
        total_impressions += m.get("impressions", 0)
        total_likes += m.get("likes", 0)
        total_retweets += m.get("retweets", 0)
        total_replies += m.get("replies", 0)
        total_bookmarks += m.get("bookmarks", 0)

    total_engagement = total_likes + total_retweets + total_replies
    eng_rate = (total_engagement / total_impressions * 100) if total_impressions > 0 else 0

    lines = [
        "\U0001f4ca *Twitter Analytics — @MindVault\\_ai*\n",
        f"\U0001f4dd Tweets posted: {total}",
        f"\U0001f4c8 With metrics: {with_metrics}\n",
        "*Totals:*",
        f"  \U0001f441 Impressions: {total_impressions:,}",
        f"  \u2764\ufe0f Likes: {total_likes:,}",
        f"  \U0001f501 Retweets: {total_retweets:,}",
        f"  \U0001f4ac Replies: {total_replies:,}",
        f"  \U0001f516 Bookmarks: {total_bookmarks:,}",
        f"  \U0001f4af Engagement rate: {eng_rate:.2f}%\n",
        "*Category scores (auto-adjusted):*",
    ]

    for cat, score in sorted(category_scores.items(), key=lambda x: -x[1]):
        bar_len = int(score * 5)
        bar = "\u2588" * bar_len + "\u2591" * (15 - bar_len)
        lines.append(f"  {cat:10s} {bar} {score:.1f}x")

    # Best & worst performing tweet
    if with_metrics > 0:
        best = max(
            (t for t in tweet_history if t.get("metrics")),
            key=lambda t: t["metrics"].get("likes", 0) + t["metrics"].get("retweets", 0),
        )
        worst = min(
            (t for t in tweet_history if t.get("metrics")),
            key=lambda t: t["metrics"].get("impressions", 0),
        )
        bm = best["metrics"]
        wm = worst["metrics"]

        lines.append(f"\n*Best tweet* ({best['cat']}):")
        lines.append(f"  {bm.get('impressions', 0):,} views, {bm.get('likes', 0)} likes, {bm.get('retweets', 0)} RTs")
        preview = best["text"][:60].replace("\n", " ")
        lines.append(f"  _{preview}..._")

        lines.append(f"\n*Lowest reach* ({worst['cat']}):")
        lines.append(f"  {wm.get('impressions', 0):,} views, {wm.get('likes', 0)} likes")
        preview = worst["text"][:60].replace("\n", " ")
        lines.append(f"  _{preview}..._")

    lines.append(f"\n_Auto-adjusting: high-engagement categories get posted more._")

    return "\n".join(lines)


# ══════════════════════════════════════════════
# POSTING
# ══════════════════════════════════════════════

async def post_tweet(api_key: str, api_secret: str,
                     access_token: str, access_secret: str) -> bool:
    """Post a marketing tweet to @MindVault_ai.

    - Selects content using smart rotation (engagement-weighted)
    - Tracks posted tweet for analytics
    - Fetches metrics for previous tweets
    """
    if not TWEEPY_AVAILABLE:
        logger.warning("tweepy not installed — skipping Twitter post")
        return False

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning("Twitter API keys not configured — skipping post")
        return False

    try:
        hour = datetime.now(timezone.utc).hour
        text, cat = get_scheduled_tweet(hour)

        client = _get_client(api_key, api_secret, access_token, access_secret)
        if not client:
            return False

        response = client.create_tweet(text=text)

        if response and response.data:
            tweet_id = str(response.data.get("id", "unknown"))
            logger.info(f"Tweet posted [{cat}]: https://x.com/MindVault_ai/status/{tweet_id}")

            # Track in history
            tweet_history.append({
                "id": tweet_id,
                "cat": cat,
                "text": text,
                "ts": datetime.now(timezone.utc),
                "metrics": None,  # fetched later
            })

            # Keep history manageable (last 100 tweets)
            while len(tweet_history) > 100:
                tweet_history.pop(0)

            # Fetch metrics for previous tweets (not current — too fresh)
            if len(tweet_history) > 1:
                try:
                    updated = update_history_metrics(
                        api_key, api_secret, access_token, access_secret
                    )
                    if updated:
                        logger.info(f"Updated metrics for {updated} tweets")
                except Exception as e:
                    logger.warning(f"Metrics fetch failed (non-critical): {e}")

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


async def post_tweet_with_media(api_key: str, api_secret: str,
                                access_token: str, access_secret: str,
                                text: str, media_path: str) -> bool:
    """Post a tweet with an image using API v1.1 for upload and v2 for tweet creation."""
    if not TWEEPY_AVAILABLE or not os.path.exists(media_path):
        return False

    try:
        api_v1 = _get_api_v1(api_key, api_secret, access_token, access_secret)
        client = _get_client(api_key, api_secret, access_token, access_secret)
        
        if not api_v1 or not client:
            return False

        # 1. Upload media (v1.1)
        media = api_v1.media_upload(filename=media_path)
        media_id = media.media_id

        # 2. Create tweet with media (v2)
        response = client.create_tweet(text=text, media_ids=[media_id])
        
        if response and response.data:
            logger.info(f"Media tweet posted: https://x.com/status/{response.data['id']}")
            return True
        return False

    except Exception as e:
        logger.error(f"Twitter media post error: {e}")
        return False


async def post_thread(api_key: str, api_secret: str,
                      access_token: str, access_secret: str,
                      tweets: list[str]) -> bool:
    """Post a Twitter thread (chain of reply tweets).

    Args:
        tweets: List of tweet texts in order. First becomes the root tweet.

    Returns:
        True if full thread posted successfully.
    """
    if not TWEEPY_AVAILABLE or not tweets:
        return False

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning("Twitter API keys not configured — skipping thread")
        return False

    try:
        client = _get_client(api_key, api_secret, access_token, access_secret)
        if not client:
            return False

        previous_id = None
        posted_count = 0

        for i, text in enumerate(tweets):
            kwargs = {"text": text}
            if previous_id:
                kwargs["in_reply_to_tweet_id"] = previous_id

            response = client.create_tweet(**kwargs)

            if response and response.data:
                previous_id = str(response.data.get("id", ""))
                posted_count += 1
                logger.info(f"Thread [{i + 1}/{len(tweets)}] posted: {previous_id}")
            else:
                logger.error(f"Thread tweet {i + 1} failed — stopping thread")
                break

        logger.info(f"Thread complete: {posted_count}/{len(tweets)} tweets posted")
        return posted_count == len(tweets)

    except tweepy.TooManyRequests:
        logger.warning("Twitter rate limit hit during thread — partial thread posted")
        return False
    except Exception as e:
        logger.error(f"Thread post error: {e}")
        return False
