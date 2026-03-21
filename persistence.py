"""
ApexFlash MEGA BOT - Data Persistence
Redis (Upstash) as primary storage, JSON files as fallback.
Telegram backup as tertiary safety net.

Priority: Redis > JSON file > Telegram backup
If UPSTASH_REDIS_URL is not set, falls back to JSON-only (current behavior).
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
STATS_FILE = DATA_DIR / "stats.json"

# Redis keys
_REDIS_USERS_KEY = "apexflash:users"
_REDIS_STATS_KEY = "apexflash:stats"

# Redis connection (lazy init)
_redis_client = None
_redis_available = None  # None = not checked yet


def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


def _get_redis():
    """Lazy-init Redis connection. Returns client or None."""
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    url = os.getenv("UPSTASH_REDIS_URL", "")
    if not url:
        _redis_available = False
        logger.info("No UPSTASH_REDIS_URL — using JSON-only persistence")
        return None

    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(url, decode_responses=True, socket_timeout=5)
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected (Upstash)")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis connection failed, falling back to JSON: {e}")
        _redis_available = False
        _redis_client = None
        return None


def _serialize_for_json(data: dict) -> dict:
    """Convert sets to lists for JSON serialization."""
    result = {}
    for k, v in data.items():
        if isinstance(v, set):
            result[k] = list(v)
        else:
            result[k] = v
    return result


# ══════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════

def save_users(users: dict) -> bool:
    """Save users dict. Redis primary, JSON fallback."""
    serializable = {str(k): v for k, v in users.items()}
    json_str = json.dumps(serializable, default=str)
    saved = False

    # 1) Redis (primary)
    r = _get_redis()
    if r:
        try:
            r.set(_REDIS_USERS_KEY, json_str)
            saved = True
        except Exception as e:
            logger.error(f"Redis save_users failed: {e}")

    # 2) JSON file (fallback / local cache)
    try:
        _ensure_dir()
        tmp = USERS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            f.write(json_str)
        tmp.replace(USERS_FILE)
        saved = True
    except Exception as e:
        logger.error(f"JSON save_users failed: {e}")

    return saved


def load_users() -> dict:
    """Load users dict. Redis first, then JSON fallback."""
    # 1) Try Redis
    r = _get_redis()
    if r:
        try:
            data = r.get(_REDIS_USERS_KEY)
            if data:
                parsed = json.loads(data)
                users = {int(k): v for k, v in parsed.items()}
                logger.info(f"Loaded {len(users)} users from Redis")
                return users
        except Exception as e:
            logger.error(f"Redis load_users failed: {e}")

    # 2) Fallback to JSON file
    try:
        if not USERS_FILE.exists():
            logger.info("No users file found — starting fresh")
            return {}
        with open(USERS_FILE) as f:
            data = json.load(f)
        users = {int(k): v for k, v in data.items()}
        logger.info(f"Loaded {len(users)} users from disk")
        # Seed Redis if we loaded from disk but Redis is available
        if r and users:
            try:
                r.set(_REDIS_USERS_KEY, json.dumps({str(k): v for k, v in users.items()}, default=str))
                logger.info("Seeded Redis with users from disk")
            except Exception:
                pass
        return users
    except Exception as e:
        logger.error(f"Load users failed: {e}")
        return {}


# ══════════════════════════════════════════════
# PLATFORM STATS
# ══════════════════════════════════════════════

def save_stats(stats: dict) -> bool:
    """Save platform stats. Redis primary, JSON fallback."""
    serializable = _serialize_for_json(stats)
    json_str = json.dumps(serializable, default=str)
    saved = False

    # 1) Redis
    r = _get_redis()
    if r:
        try:
            r.set(_REDIS_STATS_KEY, json_str)
            saved = True
        except Exception as e:
            logger.error(f"Redis save_stats failed: {e}")

    # 2) JSON file
    try:
        _ensure_dir()
        tmp = STATS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            f.write(json_str)
        tmp.replace(STATS_FILE)
        saved = True
    except Exception as e:
        logger.error(f"JSON save_stats failed: {e}")

    return saved


def load_stats() -> dict | None:
    """Load platform stats. Redis first, then JSON fallback."""
    # 1) Try Redis
    r = _get_redis()
    if r:
        try:
            data = r.get(_REDIS_STATS_KEY)
            if data:
                parsed = json.loads(data)
                if "active_traders_today" in parsed and isinstance(parsed["active_traders_today"], list):
                    parsed["active_traders_today"] = set(parsed["active_traders_today"])
                logger.info("Loaded platform stats from Redis")
                return parsed
        except Exception as e:
            logger.error(f"Redis load_stats failed: {e}")

    # 2) Fallback to JSON
    try:
        if not STATS_FILE.exists():
            return None
        with open(STATS_FILE) as f:
            data = json.load(f)
        if "active_traders_today" in data and isinstance(data["active_traders_today"], list):
            data["active_traders_today"] = set(data["active_traders_today"])
        logger.info("Loaded platform stats from disk")
        # Seed Redis
        if r and data:
            try:
                r.set(_REDIS_STATS_KEY, json.dumps(_serialize_for_json(data), default=str))
                logger.info("Seeded Redis with stats from disk")
            except Exception:
                pass
        return data
    except Exception as e:
        logger.error(f"Load stats failed: {e}")
        return None


# ══════════════════════════════════════════════
# TELEGRAM BACKUP (tertiary safety net)
# ══════════════════════════════════════════════

def export_backup(users: dict, stats: dict) -> str:
    """Export all data as JSON string for Telegram backup."""
    data = {
        "users": {str(k): v for k, v in users.items()},
        "stats": _serialize_for_json(stats),
        "version": "1.0",
    }
    return json.dumps(data, indent=2, default=str)


# ══════════════════════════════════════════════
# ANALYTICS (funnel, token popularity, affiliate)
# ══════════════════════════════════════════════

def track_funnel(step: str):
    """Track funnel step: start, wallet_created, funded, first_trade, upgrade."""
    r = _get_redis()
    if not r:
        return
    try:
        from datetime import date
        today = date.today().isoformat()
        r.incr(f"funnel:{step}:{today}")
    except Exception as e:
        logger.debug(f"Funnel track failed: {e}")


def track_token_lookup(token_mint: str, token_symbol: str = ""):
    """Track token lookup for popularity analytics."""
    r = _get_redis()
    if not r:
        return
    try:
        from datetime import date
        today = date.today().isoformat()
        r.zincrby("token:lookups:alltime", 1, token_mint)
        r.zincrby(f"token:lookups:{today}", 1, token_mint)
        if token_symbol:
            r.hset("token:symbols", token_mint, token_symbol)
    except Exception as e:
        logger.debug(f"Token tracking failed: {e}")


def track_token_trade(token_mint: str, amount_sol: float):
    """Track token trade for volume analytics."""
    r = _get_redis()
    if not r:
        return
    try:
        from datetime import date
        today = date.today().isoformat()
        r.zincrby("token:trades:alltime", 1, token_mint)
        r.zincrby(f"token:trades:{today}", 1, token_mint)
        r.incrbyfloat(f"token:volume:{today}", amount_sol)
        r.incrbyfloat("token:volume:alltime", amount_sol)
    except Exception as e:
        logger.debug(f"Trade tracking failed: {e}")


def track_affiliate_click(user_id: int, exchange: str):
    """Track affiliate link click."""
    r = _get_redis()
    if not r:
        return
    try:
        import json as _json
        from datetime import datetime
        r.lpush(f"affiliate:clicks:{exchange}", _json.dumps({
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }))
        r.ltrim(f"affiliate:clicks:{exchange}", 0, 999)  # keep last 1000
        r.incr(f"affiliate:clicks:count:{exchange}")
    except Exception as e:
        logger.debug(f"Affiliate tracking failed: {e}")


def update_last_active(user_id: int):
    """Update last_active timestamp for churn detection."""
    r = _get_redis()
    if not r:
        return
    try:
        from datetime import datetime
        r.hset(f"user:activity:{user_id}", "last_active", datetime.utcnow().isoformat())
    except Exception as e:
        logger.debug(f"Last active update failed: {e}")


def get_popular_tokens(timeframe: str = "alltime", top_n: int = 10) -> list:
    """Get top N most looked-up tokens."""
    r = _get_redis()
    if not r:
        return []
    try:
        key = f"token:lookups:{timeframe}"
        results = r.zrevrange(key, 0, top_n - 1, withscores=True)
        tokens = []
        for mint, score in results:
            symbol = r.hget("token:symbols", mint) or "?"
            tokens.append({"mint": mint, "symbol": symbol, "lookups": int(score)})
        return tokens
    except Exception as e:
        logger.debug(f"Get popular tokens failed: {e}")
        return []


def get_funnel_stats(date_str: str = None) -> dict:
    """Get funnel metrics for a given date (default today)."""
    r = _get_redis()
    if not r:
        return {}
    try:
        if not date_str:
            from datetime import date
            date_str = date.today().isoformat()
        steps = ["start", "wallet_created", "funded", "first_trade", "upgrade"]
        stats = {}
        for step in steps:
            val = r.get(f"funnel:{step}:{date_str}")
            stats[step] = int(val) if val else 0
        return stats
    except Exception as e:
        logger.debug(f"Get funnel stats failed: {e}")
        return {}


def get_affiliate_stats() -> dict:
    """Get affiliate click counts per exchange."""
    r = _get_redis()
    if not r:
        return {}
    try:
        exchanges = ["mexc", "bitunix", "blofin", "gate"]
        stats = {}
        for ex in exchanges:
            val = r.get(f"affiliate:clicks:count:{ex}")
            stats[ex] = int(val) if val else 0
        return stats
    except Exception as e:
        logger.debug(f"Get affiliate stats failed: {e}")
        return {}


def import_backup(json_str: str) -> tuple[dict, dict]:
    """Import backup from JSON string. Returns (users_dict, stats_dict).
    Also syncs to Redis if available."""
    data = json.loads(json_str)
    users_raw = data.get("users", {})
    users = {int(k): v for k, v in users_raw.items()}
    stats = data.get("stats", {})
    if "active_traders_today" in stats and isinstance(stats["active_traders_today"], list):
        stats["active_traders_today"] = set(stats["active_traders_today"])

    # Sync restored data to Redis immediately
    r = _get_redis()
    if r:
        try:
            r.set(_REDIS_USERS_KEY, json.dumps({str(k): v for k, v in users.items()}, default=str))
            r.set(_REDIS_STATS_KEY, json.dumps(_serialize_for_json(stats), default=str))
            logger.info("Restored backup synced to Redis")
        except Exception as e:
            logger.warning(f"Redis sync after restore failed: {e}")

    return users, stats
