"""
ApexFlash MEGA BOT - Configuration
All affiliate links, thresholds, chain configs, MIZAR settings, and admin config.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === Telegram ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8000))

# === Admin ===
# Comma-separated Telegram user IDs (use /myid to find yours)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# === Blockchain API Keys ===
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")

# === MIZAR API ===
MIZAR_API_KEY = os.getenv("MIZAR_API_KEY", "")
MIZAR_BASE_URL = "https://api.mizar.com/api/v1"
MIZAR_REFERRAL_URL = os.getenv("MIZAR_REFERRAL_URL", "https://mizar.com/?ref=apexflash")

# === Jupiter DEX (Solana Swaps) ===
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "")
JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# === Trading Config ===
PLATFORM_FEE_PCT = float(os.getenv("PLATFORM_FEE_PCT", "1.0"))  # 1% per trade
WALLET_ENCRYPTION_KEY = os.getenv("WALLET_ENCRYPTION_KEY", "")
SOL_MINT = "So11111111111111111111111111111111111111112"

# === OpenAI (for AI signals - Elite tier) ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# === Affiliate Links ===
AFFILIATE_LINKS = {
    "bitunix": {
        "name": "Bitunix",
        "url": f"https://www.bitunix.com/register?vipCode={os.getenv('BITUNIX_REF', 'xc6jzk')}",
        "commission": "50%",
        "featured": True,
        "description": "Low fees, high leverage, fast execution",
    },
    "mexc": {
        "name": "MEXC",
        "url": f"https://www.mexc.com/register?inviteCode={os.getenv('MEXC_REF', 'BPM0e8Rm')}",
        "commission": "up to 70%",
        "featured": True,
        "description": "70% fee rebate, 2000+ trading pairs",
    },
    "blofin": {
        "name": "BloFin",
        "url": f"https://www.blofin.com/register?referral_code={os.getenv('BLOFIN_REF', '')}",
        "commission": "50%",
        "featured": True,
        "description": "Copy trading built-in, deep liquidity",
    },
    "binance": {
        "name": "Binance",
        "url": "https://accounts.binance.com/register?ref=YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
        "description": "World's largest exchange",
    },
    "bybit": {
        "name": "Bybit",
        "url": "https://www.bybit.com/invite?ref=YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
        "description": "Top derivatives platform",
    },
    "okx": {
        "name": "OKX",
        "url": "https://www.okx.com/join/YOUR_REF",
        "commission": "up to 50%",
        "featured": False,
        "description": "Web3 wallet + exchange",
    },
}

# === Gumroad Premium Links ===
GUMROAD_PRO_URL = os.getenv("GUMROAD_PRO_URL", "https://apexflash.gumroad.com/l/pro")
GUMROAD_ELITE_URL = os.getenv("GUMROAD_ELITE_URL", "https://apexflash.gumroad.com/l/elite")

# === Support & Links ===
WEBSITE_URL = "https://apexflash.pro"
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/ApexFlashSupport")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/ApexFlashAlerts")

# === Whale Tracking Config ===
ETH_WHALE_WALLETS = {
    # Binance cluster
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance Cold",
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": "Binance Whale",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    # Major exchanges
    "0x8894e0a0c962cb723c1976a4421c95949be2d4e3": "Bitfinex",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x75e89d5979e4f6fba9f97c104c2f0afb3f1dcb88": "MEXC",
    "0xda9dfa130df4de4673b89022ee50ff26f6ea73cf": "Kraken",
    "0x1b3cb81e51011b549d78bf720b0d924ac763a7c2": "Coinbase",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Bitget",
    # Smart money / bridges
    "0x40b38765696e3d5d8d9d834d8aad4bb6e418e489": "Robinhood",
    "0xbeb5fc579115071764c7423a4f12edde41f106ed": "Arbitrum Bridge",
    "0xa7efae728d2936e78bda97dc267687568dd593f3": "OKX 3",
    "0x4862733b5fddfd35f35ea8ccf08f5045e57388b3": "Bitget 2",
}

SOL_WHALE_WALLETS = {
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Binance SOL",
    "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S": "FTX Estate",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Coinbase SOL",
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Bybit SOL",
    "AobVSwdW9BbpMdJvTqeCN4hPAmh4rHm7vwLnQ5ATbo3w": "OKX SOL",
    "GJRs4FwHtemZ5ZE9Q3M7v4N4LxhP8R7GrTqPbRaT5tFx": "Kraken SOL",
}

# Alert thresholds
ETH_ALERT_THRESHOLD = 100   # ETH minimum for whale alert
SOL_ALERT_THRESHOLD = 10000  # SOL minimum for whale alert

# Scan interval in seconds
SCAN_INTERVAL = 60

# === Premium Tiers ===
TIERS = {
    "free": {
        "name": "Free",
        "emoji": "\U0001f193",
        "chains": ["ETH"],
        "alert_delay": 300,
        "max_wallets": 3,
        "ai_signals": False,
        "copy_trade": False,
        "dca_bot": False,
        "price": 0,
    },
    "pro": {
        "name": "Pro",
        "emoji": "\U0001f680",
        "chains": ["ETH", "SOL"],
        "alert_delay": 0,
        "max_wallets": 20,
        "ai_signals": False,
        "copy_trade": True,
        "dca_bot": True,
        "price": 19,
        "gumroad_url": GUMROAD_PRO_URL,
    },
    "elite": {
        "name": "Elite",
        "emoji": "\U0001f451",
        "chains": ["ETH", "SOL", "BSC", "ARB"],
        "alert_delay": 0,
        "max_wallets": 100,
        "ai_signals": True,
        "copy_trade": True,
        "dca_bot": True,
        "price": 49,
        "gumroad_url": GUMROAD_ELITE_URL,
    },
}

# === Crypto price config ===
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
PRICE_IDS = {
    "ETH": "ethereum",
    "SOL": "solana",
    "BTC": "bitcoin",
    "BNB": "binancecoin",
    "ARB": "arbitrum",
}
FALLBACK_PRICES = {"ETH": 3500, "SOL": 180, "BTC": 95000, "BNB": 600, "ARB": 1.5}
