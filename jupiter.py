"""
ApexFlash MEGA BOT - Jupiter Swap API Client
Solana token swaps via Jupiter V6 aggregator.
Quote → Sign → Execute — with 1% platform fee.
"""
import base64
import logging
import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from config import (
    JUPITER_API_KEY, JUPITER_QUOTE_URL, JUPITER_SWAP_URL,
    HELIUS_RPC_URL, PLATFORM_FEE_PCT,
)

logger = logging.getLogger(__name__)


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if JUPITER_API_KEY:
        h["x-api-key"] = JUPITER_API_KEY
    return h


# ══════════════════════════════════════════════
# FEE CALCULATION
# ══════════════════════════════════════════════

def calculate_fee(amount_lamports: int) -> tuple[int, int]:
    """Split amount into (swap_amount, fee). Fee stays in bot wallet.

    Returns (swap_lamports, fee_lamports).
    """
    fee = int(amount_lamports * PLATFORM_FEE_PCT / 100)
    return amount_lamports - fee, fee


# ══════════════════════════════════════════════
# QUOTE
# ══════════════════════════════════════════════

async def get_quote(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    slippage_bps: int = 300,
) -> dict | None:
    """Get a swap quote from Jupiter.

    amount_raw: smallest units (lamports for SOL, i.e. 1 SOL = 1_000_000_000).
    slippage_bps: 300 = 3 %.
    """
    try:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_raw,
            "slippageBps": slippage_bps,
            "swapMode": "ExactIn",
            "restrictIntermediateTokens": "true",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                JUPITER_QUOTE_URL, params=params,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                error = await resp.text()
                logger.error(f"Jupiter quote {resp.status}: {error}")
                return None
    except Exception as e:
        logger.error(f"Jupiter quote error: {e}")
        return None


# ══════════════════════════════════════════════
# EXECUTE SWAP
# ══════════════════════════════════════════════

async def execute_swap(keypair: Keypair, quote: dict) -> tuple[str | None, str]:
    """Execute a swap: get tx from Jupiter → sign → send to Solana.

    Returns (transaction_signature, error_reason).
    On success: (sig, "")
    On failure: (None, "human-readable reason")
    """
    # Validate RPC URL
    if not HELIUS_RPC_URL:
        return None, "No HELIUS_RPC_URL configured"

    try:
        swap_body = {
            "userPublicKey": str(keypair.pubkey()),
            "quoteResponse": quote,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "dynamicSlippage": True,
            "prioritizationFeeLamports": {
                "priorityLevelWithMaxLamports": {
                    "priorityLevel": "high",
                    "maxLamports": 1_500_000,
                }
            },
        }

        async with aiohttp.ClientSession() as session:
            # 1) Get serialized transaction from Jupiter
            try:
                async with session.post(
                    JUPITER_SWAP_URL, json=swap_body,
                    headers=_headers(),
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        logger.error(f"Jupiter swap {resp.status}: {err}")
                        return None, f"Jupiter API {resp.status}: {err[:120]}"
                    swap_data = await resp.json()
            except Exception as e:
                logger.error(f"Jupiter swap request failed: {type(e).__name__}: {e}")
                return None, f"Jupiter request failed: {type(e).__name__}: {str(e)[:100]}"

            # 2) Deserialize → sign
            try:
                raw_tx = VersionedTransaction.from_bytes(
                    base64.b64decode(swap_data["swapTransaction"])
                )
                sig = keypair.sign_message(bytes(raw_tx.message))
                signed_tx = VersionedTransaction.populate(raw_tx.message, [sig])
                encoded = base64.b64encode(bytes(signed_tx)).decode()
            except Exception as e:
                logger.error(f"TX signing failed: {type(e).__name__}: {e}")
                return None, f"Signing failed: {type(e).__name__}: {str(e)[:100]}"

            # 3) Send to Solana via Helius
            try:
                rpc_payload = {
                    "jsonrpc": "2.0", "id": 1,
                    "method": "sendTransaction",
                    "params": [encoded, {
                        "encoding": "base64",
                        "skipPreflight": True,
                        "maxRetries": 3,
                    }],
                }
                async with session.post(
                    HELIUS_RPC_URL, json=rpc_payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if "result" in data:
                        tx_sig = data["result"]
                        logger.info(f"Swap OK: {tx_sig}")
                        return tx_sig, ""
                    err = data.get("error", {})
                    err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    logger.error(f"Swap send error: {err_msg}")
                    return None, f"RPC: {err_msg[:150]}"
            except Exception as e:
                logger.error(f"RPC send failed: {type(e).__name__}: {e}")
                return None, f"RPC send failed: {type(e).__name__}: {str(e)[:100]}"

    except Exception as e:
        logger.error(f"Swap execution error: {type(e).__name__}: {e}")
        return None, f"{type(e).__name__}: {str(e)[:120]}"


# ══════════════════════════════════════════════
# TOKEN LOOKUP
# ══════════════════════════════════════════════

async def get_token_info(mint: str) -> dict | None:
    """Look up token metadata by mint address. Jupiter first, DexPaprika fallback."""
    # 1) Try Jupiter
    try:
        url = "https://api.jup.ag/tokens/v2/search"
        params = {"query": mint}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    results = await resp.json()
                    if isinstance(results, list):
                        match = None
                        for t in results:
                            if t.get("id") == mint or t.get("address") == mint:
                                match = t
                                break
                        if not match and results:
                            match = results[0]
                        if match:
                            return {
                                "address": match.get("id") or match.get("address", mint),
                                "symbol": match.get("symbol", "???"),
                                "name": match.get("name", "Unknown"),
                                "decimals": match.get("decimals", 0),
                                "logoURI": match.get("icon", ""),
                            }
                else:
                    logger.warning(f"Jupiter search returned {resp.status}, trying DexPaprika")
    except Exception as e:
        logger.warning(f"Jupiter token info failed: {e}, trying DexPaprika")

    # 2) Fallback: DexPaprika (free, no API key needed)
    try:
        dex_url = f"https://api.dexpaprika.com/networks/solana/tokens/{mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                dex_url, timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("symbol"):
                        logger.info(f"DexPaprika fallback: found {data['symbol']}")
                        return {
                            "address": data.get("id", mint),
                            "symbol": data.get("symbol", "???"),
                            "name": data.get("name", "Unknown"),
                            "decimals": data.get("decimals", 0),
                            "logoURI": "",
                        }
    except Exception as e:
        logger.error(f"DexPaprika fallback also failed: {e}")

    return None


async def search_token(query: str) -> list[dict]:
    """Search token by name or symbol. Jupiter first, DexPaprika fallback."""
    # 1) Try Jupiter
    try:
        url = "https://api.jup.ag/tokens/v2/search"
        params = {"query": query}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    results = await resp.json()
                    if isinstance(results, list) and results:
                        return results
                else:
                    logger.warning(f"Jupiter search returned {resp.status}")
    except Exception as e:
        logger.warning(f"Jupiter search failed: {e}")

    # 2) Fallback: DexPaprika search
    try:
        dex_url = "https://api.dexpaprika.com/search"
        params = {"q": query}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                dex_url, params=params, timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tokens = data.get("tokens", [])
                    results = []
                    for t in tokens[:5]:
                        if t.get("network") == "solana":
                            results.append({
                                "id": t.get("address", ""),
                                "address": t.get("address", ""),
                                "symbol": t.get("symbol", "???"),
                                "name": t.get("name", "Unknown"),
                            })
                    if results:
                        logger.info(f"DexPaprika search fallback: {len(results)} results")
                        return results
    except Exception as e:
        logger.error(f"DexPaprika search also failed: {e}")

    return []
        return []


# ══════════════════════════════════════════════
# COMMON TOKENS
# ══════════════════════════════════════════════

COMMON_TOKENS = {
    "SOL":    {"mint": "So11111111111111111111111111111111111111112",
               "decimals": 9, "name": "Solana"},
    "USDC":   {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
               "decimals": 6, "name": "USD Coin"},
    "USDT":   {"mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
               "decimals": 6, "name": "Tether"},
    "JUP":    {"mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
               "decimals": 6, "name": "Jupiter"},
    "BONK":   {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
               "decimals": 5, "name": "Bonk"},
    "WIF":    {"mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
               "decimals": 6, "name": "dogwifhat"},
    "TRUMP":  {"mint": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
               "decimals": 6, "name": "TRUMP"},
    "RAY":    {"mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
               "decimals": 6, "name": "Raydium"},
    "ORCA":   {"mint": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
               "decimals": 6, "name": "Orca"},
    "PYTH":   {"mint": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
               "decimals": 6, "name": "Pyth Network"},
    "W":      {"mint": "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ",
               "decimals": 6, "name": "Wormhole"},
    "RENDER": {"mint": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
               "decimals": 8, "name": "Render"},
    "HNT":    {"mint": "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux",
               "decimals": 8, "name": "Helium"},
    "PENGU":  {"mint": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
               "decimals": 6, "name": "Pudgy Penguins"},
}
