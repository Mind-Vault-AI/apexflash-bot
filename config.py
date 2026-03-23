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
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
# Fallback RPC when Helius quota is exhausted
FALLBACK_RPC_URL = os.getenv("FALLBACK_RPC_URL", "https://api.mainnet-beta.solana.com")
RPC_URLS = [url for url in [HELIUS_RPC_URL, FALLBACK_RPC_URL] if url]

# === Trading Config ===
PLATFORM_FEE_PCT = float(os.getenv("PLATFORM_FEE_PCT", "1.0"))  # 1% per trade
WALLET_ENCRYPTION_KEY = os.getenv("WALLET_ENCRYPTION_KEY", "")
SOL_MINT = "So11111111111111111111111111111111111111112"
# Fee collection wallet — all 1% fees are transferred here after each swap
FEE_COLLECT_WALLET = os.getenv(
    "FEE_COLLECT_WALLET",
    "4LKQGKyjhCpVm7TAnDRtR5dPNExEhSADNCumvZjiuYWi",  # ApexFlash Hot wallet
)
# Referral config — referrers earn a share of fees from referred users
REFERRAL_FEE_SHARE_PCT = float(os.getenv("REFERRAL_FEE_SHARE_PCT", "25.0"))  # 25%

# === Risk Management ===
TRADING_ENABLED = os.getenv("TRADING_ENABLED", "true").lower() == "true"  # Global kill switch
MAX_TRADE_SOL = float(os.getenv("MAX_TRADE_SOL", "10.0"))  # Max single trade in SOL
MIN_SOL_RESERVE = float(os.getenv("MIN_SOL_RESERVE", "0.01"))  # Keep for rent/fees
MAX_SLIPPAGE_BPS = int(os.getenv("MAX_SLIPPAGE_BPS", "500"))  # 5% max slippage
DEFAULT_SLIPPAGE_BPS = int(os.getenv("DEFAULT_SLIPPAGE_BPS", "300"))  # 3% default
PRICE_IMPACT_WARN_PCT = float(os.getenv("PRICE_IMPACT_WARN_PCT", "3.0"))  # Warn if > 3%
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "50"))  # Per user per day

# === OpenAI (for AI signals - Elite tier) ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# === Affiliate Links — Exchanges ===
AFFILIATE_LINKS = {
    "bitunix": {
        "name": "Bitunix",
        "url": f"https://www.bitunix.com/register?vipCode={os.getenv('BITUNIX_REF', 'xc6jzk')}",
        "commission": "50%",
        "featured": True,
        "category": "exchange",
        "description": "Low fees, high leverage, fast execution",
        "promo": "$8,000+ Welcome Bonus — Sign up now!",
    },
    "mexc": {
        "name": "MEXC",
        "url": f"https://www.mexc.com/register?inviteCode={os.getenv('MEXC_REF', 'BPM0e8Rm')}",
        "commission": "up to 70%",
        "featured": True,
        "category": "exchange",
        "description": "70% fee rebate, 2000+ trading pairs",
        "promo": "70% Fee Rebate + $1,000 New User Bonus",
    },
    "blofin": {
        "name": "BloFin",
        "url": f"https://www.blofin.com/register?referral_code={os.getenv('BLOFIN_REF', 'b996a0111c1b4497b53d9b3cc82e4539')}",
        "commission": "50%",
        "featured": True,
        "category": "exchange",
        "description": "Copy trading built-in, deep liquidity",
        "promo": "50% Fee Rebate + Copy Trading Free Trial",
    },
    "gate": {
        "name": "Gate.io",
        "url": f"https://www.gate.io/signup/{os.getenv('GATE_REF', 'VFFHXVFDUG')}",
        "commission": "up to 40%",
        "featured": True,
        "category": "exchange",
        "description": "1400+ trading pairs, margin trading",
        "promo": "$6,666 Welcome Bonus + 40% Fee Rebate",
    },
    "binance": {
        "name": "Binance",
        "url": f"https://accounts.binance.com/register?ref={os.getenv('BINANCE_REF', 'YOUR_REF')}",
        "commission": "up to 50%",
        "featured": False,
        "category": "exchange",
        "description": "World's largest exchange",
    },
    "bybit": {
        "name": "Bybit",
        "url": f"https://www.bybit.com/invite?ref={os.getenv('BYBIT_REF', 'YOUR_REF')}",
        "commission": "up to 50%",
        "featured": False,
        "category": "exchange",
        "description": "Top derivatives platform",
    },
    "okx": {
        "name": "OKX",
        "url": f"https://www.okx.com/join/{os.getenv('OKX_REF', 'YOUR_REF')}",
        "commission": "up to 50%",
        "featured": False,
        "category": "exchange",
        "description": "Web3 wallet + exchange",
    },
    "bitget": {
        "name": "Bitget",
        "url": f"https://www.bitget.com/referral/register?clacCode={os.getenv('BITGET_REF', '')}",
        "commission": "up to 50%",
        "featured": False,
        "category": "exchange",
        "description": "Top copy trading exchange",
    },
    "kucoin": {
        "name": "KuCoin",
        "url": f"https://www.kucoin.com/r/{os.getenv('KUCOIN_REF', '')}",
        "commission": "up to 40%",
        "featured": False,
        "category": "exchange",
        "description": "Gem hunter exchange, low-cap coins",
    },
    "bingx": {
        "name": "BingX",
        "url": f"https://bingx.com/invite/{os.getenv('BINGX_REF', '')}",
        "commission": "up to 50%",
        "featured": False,
        "category": "exchange",
        "description": "Copy trading + futures, beginner friendly",
    },
    "phemex": {
        "name": "Phemex",
        "url": f"https://phemex.com/register?referralCode={os.getenv('PHEMEX_REF', '')}",
        "commission": "up to 45%",
        "featured": False,
        "category": "exchange",
        "description": "Zero-fee spot trading, fast engine",
    },
}

# === Affiliate Links — Crypto Tools ===
TOOL_AFFILIATE_LINKS = {
    "tradingview": {
        "name": "TradingView",
        "url": f"https://www.tradingview.com/gopro/?share_your_love={os.getenv('TV_REF', 'apexflash')}",
        "commission": "$15-30/signup",
        "featured": True,
        "description": "Charts, alerts & analysis",
    },
    "ledger": {
        "name": "Ledger",
        "url": f"https://shop.ledger.com/?r={os.getenv('LEDGER_REF', '')}",
        "commission": "10%",
        "featured": True,
        "description": "Hardware wallet, keep crypto safe",
    },
    "trezor": {
        "name": "Trezor",
        "url": f"https://trezor.io/?offer_id=87&aff_id={os.getenv('TREZOR_REF', '')}",
        "commission": "12-15%",
        "featured": False,
        "description": "Open-source hardware wallet",
    },
    "dextools": {
        "name": "DEXTools",
        "url": "https://www.dextools.io/?ref=apexflash",
        "commission": "referral",
        "featured": False,
        "description": "DEX analytics & token scanner",
    },
    "coinglass": {
        "name": "Coinglass",
        "url": f"https://www.coinglass.com/pricing?ref={os.getenv('COINGLASS_REF', '')}",
        "commission": "20%",
        "featured": False,
        "description": "Liquidation data & derivatives analytics",
    },
    "3commas": {
        "name": "3Commas",
        "url": f"https://3commas.io/?c={os.getenv('THREECOMMAS_REF', '')}",
        "commission": "25%",
        "featured": False,
        "description": "Trading bots & portfolio management",
    },
    "nordvpn": {
        "name": "NordVPN",
        "url": f"https://nordvpn.com/risk-free/?ref={os.getenv('NORD_REF', '')}",
        "commission": "40-100%",
        "featured": True,
        "description": "Secure your trading connection",
    },
}

# === Premium Payment ===
# Gumroad (card payments, backup) — actual account is mindvault34.gumroad.com
GUMROAD_ACCESS_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")
GUMROAD_PRO_URL = os.getenv("GUMROAD_PRO_URL", "https://mindvault34.gumroad.com/l/rwauqu")
GUMROAD_ELITE_URL = os.getenv("GUMROAD_ELITE_URL", "https://mindvault34.gumroad.com/l/unetcl")
# Gumroad product IDs for license verification
GUMROAD_PRO_PRODUCT_ID = os.getenv("GUMROAD_PRO_PRODUCT_ID", "rwauqu")
GUMROAD_ELITE_PRODUCT_ID = os.getenv("GUMROAD_ELITE_PRODUCT_ID", "unetcl")
# In-bot SOL payment (0% processing fee — preferred!)
PRO_PRICE_SOL = float(os.getenv("PRO_PRICE_SOL", "0.23"))    # ~$19 at SOL=$83
ELITE_PRICE_SOL = float(os.getenv("ELITE_PRICE_SOL", "0.59"))  # ~$49 at SOL=$83

# === Twitter/X Auto-Posting ===
# Get keys from: https://developer.x.com → Your App → Keys and tokens
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")
TWITTER_ENABLED = os.getenv("TWITTER_ENABLED", "true").lower() == "true"

# === Discord Integration ===
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")  # Whale alerts → Discord
DISCORD_TRADE_WEBHOOK_URL = os.getenv("DISCORD_TRADE_WEBHOOK_URL", "")  # Trade notifications

# === Telegram Channel ===
# Public channel for whale alerts — bot must be admin of this channel
ALERT_CHANNEL_ID = os.getenv("ALERT_CHANNEL_ID", "")  # e.g. "@ApexFlashAlerts" or "-100xxxxx"

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
FALLBACK_PRICES = {"ETH": 2000, "SOL": 130, "BTC": 85000, "BNB": 550, "ARB": 0.35}
