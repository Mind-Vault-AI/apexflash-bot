#!/usr/bin/env python3
"""
Sync ALL env vars from MASTER_ENV to Render.
Run this INSTEAD of manual Render env var edits.

Usage: python sync_render_env.py

This script reads MASTER_ENV_APEXFLASH.txt from Box Drive
and PUTs ALL keys to Render. No keys can be lost.
"""
import json
import os
import urllib.request

RENDER_API_KEY = os.getenv("RENDER_API_KEY")
if not RENDER_API_KEY:
    raise RuntimeError("RENDER_API_KEY missing — add it to .env (Box Drive master file). NEVER hardcode.")
SERVICE_ID = "srv-d6kcjbpaae7s73aadsu0"
API = f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars"
HDR = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Master env file location (Box Drive)
MASTER_FILE = os.path.expanduser("~/Box/MEGA BOT/MASTER_ENV_APEXFLASH.txt")


def load_master_env(path: str) -> dict[str, str]:
    """Parse KEY=VALUE from master env file, skip comments and blanks."""
    env = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and key != "PYTHON_VERSION":  # Render uses .python-version file
                    env[key] = value
    return env


def sync():
    # Load master
    if not os.path.exists(MASTER_FILE):
        print(f"ERROR: Master file not found: {MASTER_FILE}")
        return

    master = load_master_env(MASTER_FILE)
    print(f"Master: {len(master)} keys loaded from {MASTER_FILE}")

    # Add keys that are in memory but not in Box Drive master
    # NOTE: All secrets (API keys, tokens, webhooks) are now in MASTER_ENV_APEXFLASH.txt
    # This extra_keys block only contains non-secret config values and public identifiers.
    # MASTER_ENV is the SSOT — add new secrets there, not here.
    extra_keys = {
        # Wallets (public addresses — not private keys)
        "PHANTOM_WALLET_MVAI": "3zSWHK9NZdSd6fcAy6AK4VyVrwuKERo27B26Dk5yEEnX",  # @MVAIphantomP1
        # Affiliate ref codes (public)
        "GMGN_REF": "cBB5zbUF",
        "MIZAR_REF": "apexflash",
        "MIZAR_REFERRAL_URL": "https://mizar.com/?ref=apexflash",
        # Twitter posting flag
        "TWITTER_ENABLED": "true",
        # OKX account ID (not a secret)
        "OKX_ACCOUNT_ID": "797696059626980898",
        # Reddit (from local env — leave empty to disable posting)
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID", ""),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "REDDIT_USERNAME": os.getenv("REDDIT_USERNAME", ""),
        "REDDIT_PASSWORD": os.getenv("REDDIT_PASSWORD", ""),
        # GMGN.AI — critical for whale scanner (bot silently disabled without these)
        # Local file uses GMGM_ prefix (M typo) — fall back to it so sync works without manual rename
        "GMGN_API_KEY":      os.getenv("GMGN_API_KEY")      or os.getenv("GMGM_API", ""),
        "GMGN_PRIVATE_KEY":  os.getenv("GMGN_PRIVATE_KEY")  or os.getenv("GMGM_PRIVATE_KEY", ""),
        # AI router keys — Box Drive master uses hyphen names (GROQ-API etc.) not underscore
        # These extra_keys ensure Render always has the correct underscore names
        "GROQ_API_KEY":        os.getenv("GROQ_API_KEY")        or os.getenv("GROQ-API",        ""),
        "CEREBRAS_API_KEY":    os.getenv("CEREBRAS_API_KEY")    or os.getenv("CEREBRAS-API",    ""),
        "OPENROUTER_API_KEY":  os.getenv("OPENROUTER_API_KEY")  or os.getenv("OPENROUTER-API",  ""),
        "DEEPSEEK_API_KEY":    os.getenv("DEEPSEEK_API_KEY")    or os.getenv("DEEPSEEK-API",    ""),
        "NEBIUS_API_KEY":      os.getenv("NEBIUS_API_KEY")      or os.getenv("NEBIUS-API",      ""),
        "GEMINI_API_KEY":      os.getenv("GEMINI_API_KEY")      or os.getenv("GEMINI-API",      ""),
        "GMGN_WALLET_ADDRESS": os.getenv("GMGN_WALLET_ADDRESS", "CsgcvMXFfLTZm8u8a6Eds1GnUXTcpPHV7Cho5ueUApvi"),
        # Discord webhook for Grade A/S signals
        "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", ""),
        # GODMODE trading params — tuned for Solana meme volatility
        "TEST_TRADE_SOL": "0",
        "AUTONOMOUS_TRADE_AMOUNT_SOL": "0.05",
        "BREAKEVEN_TRIGGER_PCT": "10.0",  # trail SL at +10% (was 0.5 — too tight)
        "TAKE_PROFIT_PCT": "50.0",        # TP at +50% (was 2.0 — memes need room)
        "STOP_LOSS_PCT": "15.0",          # SL at -15% (was 1.0 — stopped out by noise)
        "MIN_SOL_RESERVE": "0.1",
        "AUTONOMOUS_COOLDOWN": "300",
        # Bot config
        "BOT_USERNAME": "ApexFlashBot",
        "SITE_URL": "https://apexflash.pro",
    }
    for k, v in extra_keys.items():
        if k not in master:
            master[k] = v
            print(f"  Added from memory: {k}")

    # PRO_PRICE_SOL/ELITE_PRICE_SOL removed — pricing is now dynamic (live SOL/USD rate)

    # PUT to Render
    payload = json.dumps([{"key": k, "value": v} for k, v in master.items()]).encode()
    req = urllib.request.Request(API, data=payload, headers=HDR, method="PUT")
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    print(f"Render PUT: {len(result)} keys written")

    # Verify
    req2 = urllib.request.Request(API, headers=HDR)
    with urllib.request.urlopen(req2) as r2:
        verify = json.loads(r2.read())
    visible = [e.get("envVar", e)["key"] for e in verify]
    print(f"Visible: {len(visible)} (secret keys hidden by Render API)")
    print(f"Total synced: {len(master)} keys")
    print("DONE")


if __name__ == "__main__":
    sync()
