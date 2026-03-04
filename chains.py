"""
ApexFlash Bot - Blockchain Data Fetchers
Etherscan (ETH) + Helius/Solscan (SOL) whale tracking.
"""
import logging
import aiohttp
from config import (
    ETHERSCAN_API_KEY, HELIUS_API_KEY, SOLSCAN_API_KEY,
    ETH_WHALE_WALLETS, SOL_WHALE_WALLETS,
    ETH_ALERT_THRESHOLD, SOL_ALERT_THRESHOLD,
)

logger = logging.getLogger(__name__)


async def fetch_eth_whale_transfers() -> list[dict]:
    """Fetch recent large ETH transfers from tracked whale wallets."""
    if not ETHERSCAN_API_KEY:
        logger.warning("Etherscan API key not set")
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        for wallet, name in ETH_WHALE_WALLETS.items():
            try:
                url = (
                    f"https://api.etherscan.io/v2/api"
                    f"?chainid=1&module=account&action=txlist"
                    f"&address={wallet}"
                    f"&startblock=0&endblock=99999999"
                    f"&page=1&offset=5&sort=desc"
                    f"&apikey={ETHERSCAN_API_KEY}"
                )
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                result = data.get("result")
                if data.get("status") == "1" and isinstance(result, list):
                    for tx in result:
                        value_eth = int(tx.get("value", 0)) / 10**18
                        if value_eth >= ETH_ALERT_THRESHOLD:
                            from_addr = tx.get("from", "").lower()
                            to_addr = tx.get("to", "").lower()
                            direction = "OUT" if from_addr == wallet.lower() else "IN"

                            from_label = ETH_WHALE_WALLETS.get(from_addr, _short(from_addr))
                            to_label = ETH_WHALE_WALLETS.get(to_addr, _short(to_addr))

                            alerts.append({
                                "chain": "ETH",
                                "value": round(value_eth, 2),
                                "symbol": "ETH",
                                "from_label": from_label,
                                "to_label": to_label,
                                "direction": direction,
                                "wallet_name": name,
                                "tx_hash": tx.get("hash", ""),
                                "timestamp": int(tx.get("timeStamp", 0)),
                            })
            except Exception as e:
                logger.error(f"Etherscan error for {name}: {e}")

    # Deduplicate by tx hash
    seen = set()
    unique = []
    for a in alerts:
        if a["tx_hash"] not in seen:
            seen.add(a["tx_hash"])
            unique.append(a)

    return sorted(unique, key=lambda x: x["timestamp"], reverse=True)[:10]


async def fetch_sol_whale_transfers() -> list[dict]:
    """Fetch recent large SOL transfers via Helius."""
    if not HELIUS_API_KEY:
        logger.warning("Helius API key not set")
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        for wallet, name in SOL_WHALE_WALLETS.items():
            try:
                url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={HELIUS_API_KEY}&limit=5"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                if isinstance(data, list):
                    for tx in data:
                        # Parse native SOL transfers
                        native = tx.get("nativeTransfers", [])
                        for transfer in native:
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
                logger.error(f"Helius error for {name}: {e}")

    seen = set()
    unique = []
    for a in alerts:
        if a["tx_hash"] not in seen:
            seen.add(a["tx_hash"])
            unique.append(a)

    return sorted(unique, key=lambda x: x["timestamp"], reverse=True)[:10]


def _short(address: str) -> str:
    """Shorten a blockchain address for display."""
    if not address or len(address) < 10:
        return address or "Unknown"
    return f"{address[:6]}...{address[-4:]}"
