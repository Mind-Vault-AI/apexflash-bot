"""
Crypto Sentiment Analysis via HuggingFace Inference API
════════════════════════════════════════════════════════
Uses ElKulako/cryptobert (free tier) to classify whale alerts
as Bullish / Neutral / Bearish based on recent crypto Twitter.

Zero cost, ~200 requests/day on free tier.
"""
import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")
MODEL_ID = "ElKulako/cryptobert"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
TIMEOUT = 8  # seconds — if HF is slow, skip sentiment (don't block alerts)

# Cache to avoid re-querying same token within scan interval
_cache: dict[str, dict] = {}
_CACHE_MAX = 200


async def analyze_crypto_sentiment(text: str) -> Optional[dict]:
    """
    Classify text as Bullish / Neutral / Bearish using CryptoBERT.

    Returns:
        {"label": "Bullish", "score": 0.87, "emoji": "🟢"} or None on failure.
    """
    if not HF_TOKEN:
        logger.debug("No HUGGINGFACE_TOKEN set — skipping sentiment")
        return None

    # Check cache
    cache_key = text[:100]
    if cache_key in _cache:
        return _cache[cache_key]

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": text}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(API_URL, json=payload, headers=headers, timeout=TIMEOUT)

        if resp.status_code == 503:
            # Model loading (cold start) — skip this time, will work next scan
            logger.info("CryptoBERT loading (cold start) — skipping sentiment")
            return None

        if resp.status_code != 200:
            logger.warning(f"HF API error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()

        # HF returns [[{"label": "Bullish", "score": 0.87}, ...]]
        if not data or not isinstance(data, list) or not data[0]:
            return None

        results = data[0]
        if isinstance(results, list):
            # Sort by score, pick top
            top = max(results, key=lambda x: x.get("score", 0))
        else:
            top = results

        label = top.get("label", "Neutral")
        score = top.get("score", 0)

        # Map to emoji
        emoji_map = {
            "Bullish": "\U0001f7e2",   # 🟢
            "Bearish": "\U0001f534",   # 🔴
            "Neutral": "\u26aa",       # ⚪
        }

        result = {
            "label": label,
            "score": round(score, 2),
            "emoji": emoji_map.get(label, "\u26aa"),
        }

        # Cache it
        if len(_cache) >= _CACHE_MAX:
            # Drop oldest half
            keys = list(_cache.keys())
            for k in keys[:_CACHE_MAX // 2]:
                del _cache[k]
        _cache[cache_key] = result

        return result

    except httpx.TimeoutException:
        logger.info("HF API timeout — skipping sentiment (alert still sends)")
        return None
    except Exception as e:
        logger.warning(f"Sentiment analysis error: {e}")
        return None


def format_sentiment_line(sentiment: Optional[dict]) -> str:
    """Format sentiment as a single line for whale alert messages."""
    if not sentiment:
        return ""

    label = sentiment["label"]
    score = sentiment["score"]
    emoji = sentiment["emoji"]
    pct = int(score * 100)

    return f"{emoji} *Market Sentiment:* {label} ({pct}%)\n"


async def get_whale_alert_sentiment(alert: dict) -> Optional[dict]:
    """
    Build a contextual query from a whale alert and analyze sentiment.

    Uses the token symbol + direction to query CryptoBERT with
    a crypto-native prompt that reflects the whale activity.
    """
    symbol = alert.get("symbol", "")
    direction = alert.get("direction", "")
    value = alert.get("value", 0)
    chain = alert.get("chain", "")

    if not symbol:
        return None

    # Build a crypto-native text that CryptoBERT understands
    if direction == "IN":
        text = f"Major whale accumulation: {value:,.0f} {symbol} moved to exchange wallet. Big {chain} buy signal."
    else:
        text = f"Whale selling alert: {value:,.0f} {symbol} withdrawn from exchange. Potential {chain} dump incoming."

    return await analyze_crypto_sentiment(text)


# ══════════════════════════════════════════════
# SIGNAL QUALITY SCORING — filters bad signals
# ══════════════════════════════════════════════

# Minimum quality score to send alert (0-100). Below this = suppressed.
MIN_SIGNAL_QUALITY = 80

# Wallets with historically better signals get bonus points
HIGH_QUALITY_WALLETS = {
    "Binance Hot", "Binance Cold", "Coinbase Prime", "Kraken Hot",
    "OKX Reserve", "Bitfinex Cold",
}
LOW_QUALITY_WALLETS = {
    "Unknown",
}


def score_whale_signal(alert: dict, sentiment: Optional[dict] = None) -> dict:
    """
    Score a whale alert on signal quality (0-100).

    Factors:
    - Direction (IN to exchange = sell pressure = bearish, OUT = accumulation = bullish)
    - Amount relative to threshold (bigger = stronger signal)
    - Wallet reputation (known exchange vs unknown)
    - AI sentiment alignment (CryptoBERT agrees with direction?)
    - Chain (SOL = more volatile = higher opportunity)

    Returns:
        {"quality": 72, "grade": "B", "action": "BUY", "reason": "Strong accumulation..."}
    """
    score = 50  # Base score
    reasons = []

    direction = alert.get("direction", "")
    value = alert.get("value", 0)
    chain = alert.get("chain", "")
    from_wallet = alert.get("from_label", alert.get("from", "Unknown"))
    to_wallet = alert.get("to_label", alert.get("to", "Unknown"))

    # === Direction Analysis ===
    # OUT from exchange = whale withdrawing = accumulating = BULLISH
    # IN to exchange = whale depositing = likely selling = BEARISH
    if direction == "OUT":
        score += 15
        action = "BUY"
        reasons.append("Whale withdrawing from exchange (accumulation)")
    else:
        score -= 10
        action = "CAUTION"
        reasons.append("Whale depositing to exchange (potential sell)")

    # === Size Factor ===
    # Bigger transfers = stronger conviction
    if chain == "ETH":
        threshold = 100  # ETH_ALERT_THRESHOLD
        if value >= threshold * 10:
            score += 15
            reasons.append(f"Massive transfer: {value:,.0f} ETH")
        elif value >= threshold * 3:
            score += 8
            reasons.append(f"Large transfer: {value:,.0f} ETH")
    elif chain == "SOL":
        threshold = 10000  # SOL_ALERT_THRESHOLD
        if value >= threshold * 5:
            score += 15
            reasons.append(f"Massive transfer: {value:,.0f} SOL")
        elif value >= threshold * 2:
            score += 8
            reasons.append(f"Large transfer: {value:,.0f} SOL")

    # === Wallet Reputation ===
    wallet_label = to_wallet if direction == "IN" else from_wallet
    if wallet_label in HIGH_QUALITY_WALLETS:
        score += 10
        reasons.append(f"Known wallet: {wallet_label}")
    elif wallet_label in LOW_QUALITY_WALLETS:
        score -= 15
        reasons.append("Unknown wallet (higher risk)")

    # === AI Sentiment Alignment ===
    if sentiment:
        sent_label = sentiment.get("label", "Neutral")
        sent_score = sentiment.get("score", 0)

        if action == "BUY" and sent_label == "Bullish" and sent_score > 0.7:
            score += 15
            reasons.append(f"AI confirms: Bullish ({int(sent_score * 100)}%)")
        elif action == "BUY" and sent_label == "Bearish" and sent_score > 0.7:
            score -= 20
            reasons.append(f"AI warns: Bearish ({int(sent_score * 100)}%)")
        elif action == "CAUTION" and sent_label == "Bearish":
            score -= 10
            reasons.append("AI confirms sell pressure")

    # === Chain Bonus ===
    if chain == "SOL":
        score += 5  # More volatile = more opportunity

    # Clamp 0-100
    score = max(0, min(100, score))

    # Grade
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "quality": score,
        "grade": grade,
        "action": action,
        "reasons": reasons,
        "pass": score >= MIN_SIGNAL_QUALITY,
    }


def format_signal_quality(sq: dict) -> str:
    """Format signal quality as lines for whale alert message."""
    grade = sq["grade"]
    quality = sq["quality"]
    action = sq["action"]

    grade_emoji = {"A": "\U0001f525", "B": "\U0001f7e2", "C": "\U0001f7e1", "D": "\U0001f534"}
    action_emoji = {"BUY": "\U0001f4b0", "CAUTION": "\u26a0\ufe0f"}

    lines = f"{grade_emoji.get(grade, '')} *Signal Grade:* {grade} ({quality}/100)\n"
    lines += f"{action_emoji.get(action, '')} *Action:* {action}\n"

    # Top reason only (keep it clean)
    if sq["reasons"]:
        lines += f"\U0001f4a1 {sq['reasons'][0]}\n"

    return lines
