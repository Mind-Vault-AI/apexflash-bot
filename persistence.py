"""
ApexFlash MEGA BOT - Data Persistence
JSON file storage with atomic writes. Telegram backup for deploy resilience.
Zero cost, zero dependencies beyond stdlib.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
STATS_FILE = DATA_DIR / "stats.json"


def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════

def save_users(users: dict) -> bool:
    """Save users dict to JSON file. Atomic write (tmp + rename)."""
    try:
        _ensure_dir()
        serializable = {str(k): v for k, v in users.items()}
        tmp = USERS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(serializable, f, default=str)
        tmp.replace(USERS_FILE)
        return True
    except Exception as e:
        logger.error(f"Save users failed: {e}")
        return False


def load_users() -> dict:
    """Load users dict from JSON file. Returns empty dict if none."""
    try:
        if not USERS_FILE.exists():
            logger.info("No users file found — starting fresh")
            return {}
        with open(USERS_FILE) as f:
            data = json.load(f)
        users = {int(k): v for k, v in data.items()}
        logger.info(f"Loaded {len(users)} users from disk")
        return users
    except Exception as e:
        logger.error(f"Load users failed: {e}")
        return {}


# ══════════════════════════════════════════════
# PLATFORM STATS
# ══════════════════════════════════════════════

def save_stats(stats: dict) -> bool:
    """Save platform stats to JSON file."""
    try:
        _ensure_dir()
        # Convert sets to lists for JSON serialization
        serializable = {}
        for k, v in stats.items():
            if isinstance(v, set):
                serializable[k] = list(v)
            else:
                serializable[k] = v
        tmp = STATS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(serializable, f, default=str)
        tmp.replace(STATS_FILE)
        return True
    except Exception as e:
        logger.error(f"Save stats failed: {e}")
        return False


def load_stats() -> dict | None:
    """Load platform stats. Returns None if no file."""
    try:
        if not STATS_FILE.exists():
            return None
        with open(STATS_FILE) as f:
            data = json.load(f)
        # Restore sets
        if "active_traders_today" in data and isinstance(data["active_traders_today"], list):
            data["active_traders_today"] = set(data["active_traders_today"])
        logger.info("Loaded platform stats from disk")
        return data
    except Exception as e:
        logger.error(f"Load stats failed: {e}")
        return None


# ══════════════════════════════════════════════
# TELEGRAM BACKUP (deploy resilience)
# ══════════════════════════════════════════════

def export_backup(users: dict, stats: dict) -> str:
    """Export all data as JSON string for Telegram backup."""
    data = {
        "users": {str(k): v for k, v in users.items()},
        "stats": {},
        "version": "1.0",
    }
    # Serialize stats safely
    for k, v in stats.items():
        if isinstance(v, set):
            data["stats"][k] = list(v)
        else:
            data["stats"][k] = v
    return json.dumps(data, indent=2, default=str)


def import_backup(json_str: str) -> tuple[dict, dict]:
    """Import backup from JSON string. Returns (users_dict, stats_dict)."""
    data = json.loads(json_str)
    users_raw = data.get("users", {})
    users = {int(k): v for k, v in users_raw.items()}
    stats = data.get("stats", {})
    if "active_traders_today" in stats and isinstance(stats["active_traders_today"], list):
        stats["active_traders_today"] = set(stats["active_traders_today"])
    return users, stats
