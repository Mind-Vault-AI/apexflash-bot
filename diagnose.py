"""Quick diagnostic — tests all imports and sends result to admin."""
import os
import sys
import httpx

TOK = os.getenv("BOT_TOKEN", "")
ADMIN = os.getenv("ADMIN_IDS", "").split(",")[0].strip()

def msg(text):
    if TOK and ADMIN:
        httpx.post(
            f"https://api.telegram.org/bot{TOK}/sendMessage",
            json={"chat_id": int(ADMIN), "text": text[:4000]},
            timeout=10,
        )
    print(text)

msg(f"🔍 DIAGNOSE START\nPython: {sys.version}\nCWD: {os.getcwd()}")

results = []

# Test each import
modules = [
    ("telegram", "from telegram import Update"),
    ("telegram.ext", "from telegram.ext import Application"),
    ("aiohttp", "import aiohttp"),
    ("solders.keypair", "from solders.keypair import Keypair"),
    ("solders.pubkey", "from solders.pubkey import Pubkey"),
    ("cryptography", "from cryptography.fernet import Fernet"),
    ("tweepy", "import tweepy"),
    ("config", "import config"),
    ("chains", "import chains"),
    ("wallet", "import wallet"),
    ("jupiter", "import jupiter"),
    ("notifications", "import notifications"),
    ("gumroad", "import gumroad"),
    ("persistence", "import persistence"),
    ("marketing", "import marketing"),
    ("twitter_poster", "import twitter_poster"),
    ("bot", "import bot"),
]

for name, stmt in modules:
    try:
        exec(stmt)
        results.append(f"✅ {name}")
    except Exception as e:
        results.append(f"❌ {name}: {type(e).__name__}: {e}")

report = "🔍 IMPORT TEST:\n\n" + "\n".join(results)
msg(report)

# Test config values
try:
    from core import config
    cfg_report = (
        f"\n📋 CONFIG:\n"
        f"BOT_TOKEN: {'SET' if config.BOT_TOKEN else 'MISSING'}\n"
        f"ADMIN_IDS: {config.ADMIN_IDS}\n"
        f"TRADING_ENABLED: {config.TRADING_ENABLED}\n"
        f"TWITTER_ENABLED: {getattr(config, 'TWITTER_ENABLED', '?')}\n"
        f"WALLET_ENCRYPTION_KEY: {'SET' if config.WALLET_ENCRYPTION_KEY else 'MISSING'}\n"
    )
    msg(cfg_report)
except Exception as e:
    msg(f"❌ Config check failed: {e}")

msg("🔍 DIAGNOSE COMPLETE")
