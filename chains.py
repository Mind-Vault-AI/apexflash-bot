"""
ApexFlash MEGA BOT - Blockchain Data Fetchers
Etherscan V2 (ETH) + Helius (SOL) whale tracking + CoinGecko price feed.
"""
import logging
import time
import aiohttp
from config import (
    ETHERSCAN_API_KEY, HELIUS_API_KEY, SOLSCAN_API_KEY,
    ETH_WHALE_WALLETS, SOL_WHALE_WALLETS,
    ETH_ALERT_THRESHOLD, SOL_ALERT_THRESHOLD,
    COINGECKO_PRICE_URL, PRICE_IDS, FALLBACK_PRICES,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# PRICE FEED (CoinGecko, cached 2 min)
# ══════════════════════════════════════════════
_price_cache: dict[str, float] = {}
_price_cache_ts: float = 0
PRICE_CACHE_TTL = 120


async def get_crypto_prices() -> dict[str, float]:
    """Fetch current crypto prices from CoinGecko (cached 2min)."""
    global _price_cache, _price_cache_ts

    if _price_cache and (time.time() - _price_cache_ts) < PRICE_CACHE_TTL:
        return _price_cache

    try:
        ids = ",".join(PRICE_IDS.values())
        url = f"{COINGECKO_PRICE_URL}?ids={ids}&vs_currencies=usd"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prices = {}
                    for symbol, cg_id in PRICE_IDS.items():
                        if cg_id in data and "usd" in data[cg_id]:
                            prices[symbol] = data[cg_id]["usd"]
                    if prices:
                        _price_cache = prices
                        _price_cache_ts = time.time()
                        return prices
    except Exception as e:
        logger.warning(f"CoinGecko price error: {e}")

    return _price_cache if _price_cache else FALLBACK_PRICES


# ══════════════════════════════════════════════
# ETH WHALE TRACKER (Etherscan V2)
# ══════════════════════════════════════════════

async def fetch_eth_whale_transfers() -> list[dict]:
    """Fetch recent large ETH transfers from tracked whale wallets."""
    if not ETHERSCAN_API_KEY:
        logger.warning("Etherscan API key not set")
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        for wallet, name in ETH_WHALE_WALLETS.items():
            try:
                url = "https://api.etherscan.io/v2/api"
                params = {
                    "chainid": "1", "module": "account", "action": "txlist",
                    "address": wallet,
                    "startblock": "0", "endblock": "99999999",
                    "page": "1", "offset": "5", "sort": "desc",
                    "apikey": ETHERSCAN_API_KEY,
                }
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                result = data.get("result")
                if data.get("status") == "1" and isinstance(result, list):
                    for tx in result:
                        value_eth = int(tx.get("value", 0)) / 10**18
                        if value_eth >= ETH_ALERT_THRESHOLD:
                            from_addr = tx.get("from", "").lower()
                            to_addr = tx.get("to", "").lower()
                            direction = "OUT" if from_addr == wallet.lower() else "IN"

                            alerts.append({
                                "chain": "ETH",
                                "value": round(value_eth, 2),
                                "symbol": "ETH",
                                "from_label": ETH_WHALE_WALLETS.get(from_addr, _short(from_addr)),
                                "to_label": ETH_WHALE_WALLETS.get(to_addr, _short(to_addr)),
                                "direction": direction,
                                "wallet_name": name,
                                "tx_hash": tx.get("hash", ""),
                                "timestamp": int(tx.get("timeStamp", 0)),
                            })
            except Exception as e:
                logger.error(f"Etherscan error [{name}]: {e}")

    return _dedupe_and_sort(alerts)


# ══════════════════════════════════════════════
# SOL WHALE TRACKER (Helius)
# ══════════════════════════════════════════════

async def fetch_sol_whale_transfers() -> list[dict]:
    """Fetch recent large SOL transfers via Helius."""
    if not HELIUS_API_KEY:
        logger.warning("Helius API key not set")
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        for wallet, name in SOL_WHALE_WALLETS.items():
            try:
                url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
                params = {"api-key": HELIUS_API_KEY, "limit": "5"}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                if isinstance(data, list):
                    for tx in data:
                        for transfer in tx.get("nativeTransfers", []):
                            amount_sol = transfer.get("amount", 0) / 10**9
                            if amount_sol >= SOL_ALERT_THRESHOLD:
                                from_addr = transfer.get("fromUserAccount", "")
                                to_addr = transfer.get("toUserAccount", "")
                                direction = "OUT" if from_addr == wallet else "IN"

                                alerts.append({
                                    "chain": "SOL",
                                    "value": round(amount_sol, 2),
                                    "symbol": "SOL",
                                    "from_label": SOL_WHALE_WALLETS.get(from_addr, _short(from_addr)),
                                    "to_label": SOL_WHALE_WALLETS.get(to_addr, _short(to_addr)),
                                    "direction": direction,
                                    "wallet_name": name,
                                    "tx_hash": tx.get("signature", ""),
                                    "timestamp": tx.get("timestamp", 0),
                                })
            except Exception as e:
                logger.error(f"Helius error [{name}]: {e}")

    return _dedupe_and_sort(alerts)


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════

def _dedupe_and_sort(alerts: list[dict], limit: int = 10) -> list[dict]:
    """Remove duplicate tx hashes and sort by timestamp descending."""
    seen = set()
    unique = []
    for a in alerts:
        if a["tx_hash"] not in seen:
            seen.add(a["tx_hash"])
            unique.append(a)
    return sorted(unique, key=lambda x: x["timestamp"], reverse=True)[:limit]


def _short(address: str) -> str:
    """Shorten a blockchain address for display."""
    if not address or len(address) < 10:
        return address or "Unknown"
    return f"{address[:6]}...{address[-4:]}"
