"""
ApexFlash MEGA BOT - Blockchain Data Fetchers
Etherscan V2 (ETH) + Helius (SOL) whale tracking + CoinGecko price feed.
"""
import logging
import time
import aiohttp
from core.config import (
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
# WHALE TOKEN SWAP TRACKER (Helius Enhanced)
# ══════════════════════════════════════════════
# Tracks WHAT TOKENS whales are buying/selling — not just SOL transfers.
# This detects Jupiter/Raydium swaps and surfaces the actual tokens.

# Top whale/smart-money wallets on Solana known for early entries
SMART_MONEY_WALLETS = {
    # DEX traders & known smart money (public addresses from on-chain analysis)
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter Aggregator",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
}

# Minimum USD value for token swap alert
SWAP_ALERT_MIN_USD = 50_000


async def fetch_sol_whale_token_swaps() -> list[dict]:
    """
    Fetch recent token swaps by whale wallets via Helius parsed transactions.

    Returns actionable alerts like:
    "Whale X bought 500K BONK via Jupiter" — with mint address for 1-tap buy.
    """
    if not HELIUS_API_KEY:
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        # Check both whale wallets AND smart money wallets
        all_wallets = {**SOL_WHALE_WALLETS, **SMART_MONEY_WALLETS}

        for wallet, name in all_wallets.items():
            try:
                url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
                params = {"api-key": HELIUS_API_KEY, "limit": "5", "type": "SWAP"}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()

                if not isinstance(data, list):
                    continue

                for tx in data:
                    # Parse token transfers from swap
                    token_transfers = tx.get("tokenTransfers", [])
                    if not token_transfers:
                        continue

                    # Find what token was RECEIVED (= bought)
                    for transfer in token_transfers:
                        to_account = transfer.get("toUserAccount", "")
                        from_account = transfer.get("fromUserAccount", "")
                        mint = transfer.get("mint", "")
                        amount = transfer.get("tokenAmount", 0)
                        token_standard = transfer.get("tokenStandard", "")

                        # Skip SOL-wrapped or USDC/USDT (not interesting)
                        skip_mints = {
                            "So11111111111111111111111111111111111111112",  # wSOL
                            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
                        }
                        if mint in skip_mints or not mint:
                            continue

                        # Determine if whale BOUGHT or SOLD this token
                        if to_account == wallet:
                            direction = "BUY"
                        elif from_account == wallet:
                            direction = "SELL"
                        else:
                            continue

                        # Only care about buys (that's the signal)
                        if direction != "BUY":
                            continue

                        if amount <= 0:
                            continue

                        alerts.append({
                            "chain": "SOL",
                            "type": "SWAP",
                            "direction": direction,
                            "symbol": _get_token_symbol(mint),
                            "mint": mint,
                            "amount": amount,
                            "value": 0,  # Will be enriched with price later
                            "wallet_name": name,
                            "from_label": name,
                            "to_label": name,
                            "tx_hash": tx.get("signature", ""),
                            "timestamp": tx.get("timestamp", 0),
                            "tradeable": True,  # Can be bought via Jupiter
                        })

            except Exception as e:
                logger.error(f"Helius swap tracker error [{name}]: {e}")

    return _dedupe_and_sort(alerts)


def _get_token_symbol(mint: str) -> str:
    """Get token symbol from mint address (uses known tokens first)."""
    known = {
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
        "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN": "TRUMP",
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
        "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
        "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
        "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux": "HNT",
        "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof": "RENDER",
    }
    return known.get(mint, mint[:6] + "...")


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
