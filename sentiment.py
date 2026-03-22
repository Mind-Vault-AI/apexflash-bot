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
