"""
ApexFlash Bot - Configuration
All affiliate links, thresholds, and chain configs in one place.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === Telegram ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8000))

# === Blockchain API Keys ===
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")

# === OpenAI (for Phase 2 AI signals) ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# === Affiliate Links ===
AFFILIATE_LINKS = {
    "bitunix": {
        "name": "Bitunix",
        "url": f"https://www.bitunix.com/register?vipCode={os.getenv('BITUNIX_REF', 'xc6jzk')}",
        "commission": "50%",
        "featured": True,
    },
    "mexc": {
        "name": "MEXC",
        "url": f"https://www.mexc.com/register?inviteCode={os.getenv('MEXC_REF', 'BPM0e8Rm')}",
        "commission": "up to 70%",
        "featured": True,
    },
    "blofin": {
        "name": "BloFin",
        "url": f"https://www.blofin.com/register?referral_code={os.getenv('BLOFIN_REF', '')}",
        "commission": "50%",
        "featured": True,
    },
    "binance": {
        "name": "Binance",
        "url": "https://accounts.binance.com/register?ref=YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
    },
    "bybit": {
        "name": "Bybit",
        "url": "https://www.bybit.com/invite?ref=YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
    },
    "okx": {
        "name": "OKX",
        "url": "https://www.okx.com/join/YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
    },
}

# === Gumroad Premium Links ===
GUMROAD_PRO_URL = os.getenv("GUMROAD_PRO_URL", "https://apexflash.gumroad.com/l/pro")
GUMROAD_ELITE_URL = os.getenv("GUMROAD_ELITE_URL", "https://apexflash.gumroad.com/l/elite")

# === Whale Tracking Config ===
# ETH whale wallets (known exchange/whale addresses)
ETH_WHALE_WALLETS = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot Wallet",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance Cold Wallet",
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": "Binance Whale",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0x8894e0a0c962cb723c1976a4421c95949be2d4e3": "Bitfinex",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x75e89d5979e4f6fba9f97c104c2f0afb3f1dcb88": "MEXC",
    "0xda9dfa130df4de4673b89022ee50ff26f6ea73cf": "Kraken",
    "0x1b3cb81e51011b549d78bf720b0d924ac763a7c2": "Coinbase Whale",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Bitget",
}

# SOL whale wallets (known large holders)
SOL_WHALE_WALLETS = {
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Binance SOL",
    "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S": "FTX Estate",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Coinbase SOL",
}

# Alert thresholds
ETH_ALERT_THRESHOLD = 100  # ETH minimum for alert
SOL_ALERT_THRESHOLD = 10000  # SOL minimum for alert

# Scan interval in seconds
SCAN_INTERVAL = 60

# === Premium Tiers ===
TIERS = {
    "free": {
        "name": "Free",
        "chains": ["ETH"],
        "alert_delay": 300,  # 5 min delay vs premium
        "max_wallets": 3,
        "ai_signals": False,
    },
    "pro": {
        "name": "Pro ($19/mo)",
        "chains": ["ETH", "SOL"],
        "alert_delay": 0,
        "max_wallets": 20,
        "ai_signals": False,
        "gumroad_url": GUMROAD_PRO_URL,
    },
    "elite": {
        "name": "Elite ($49/mo)",
        "chains": ["ETH", "SOL", "BSC", "ARB"],
        "alert_delay": 0,
        "max_wallets": 100,
        "ai_signals": True,
        "gumroad_url": GUMROAD_ELITE_URL,
    },
}
