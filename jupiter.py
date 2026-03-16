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

async def execute_swap(keypair: Keypair, quote: dict) -> str | None:
    """Execute a swap: get tx from Jupiter → sign → send to Solana.

    Returns transaction signature or None.
    """
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
            # 1) Get serialized transaction
            async with session.post(
                JUPITER_SWAP_URL, json=swap_body,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error(f"Jupiter swap {resp.status}: {err}")
                    return None
                swap_data = await resp.json()

            # 2) Deserialize → sign
            raw_tx = VersionedTransaction.from_bytes(
                base64.b64decode(swap_data["swapTransaction"])
            )
            sig = keypair.sign_message(bytes(raw_tx.message))
            signed_tx = VersionedTransaction.populate(raw_tx.message, [sig])

            # 3) Send to Solana via Helius
            encoded = base64.b64encode(bytes(signed_tx)).decode()
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
                    return tx_sig
                logger.error(f"Swap send error: {data.get('error')}")
                return None

    except Exception as e:
        logger.error(f"Swap execution error: {e}")
        return None


# ══════════════════════════════════════════════
# TOKEN LOOKUP
# ══════════════════════════════════════════════

async def get_token_info(mint: str) -> dict | None:
    """Look up token metadata by mint address."""
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
                    for t in results:
                        if t.get("id") == mint:
                            return {
                                "address": t["id"],
                                "symbol": t.get("symbol", "???"),
                                "name": t.get("name", "Unknown"),
                                "decimals": t.get("decimals", 0),
                                "logoURI": t.get("icon", ""),
                            }
                    return results[0] if results else None
                return None
    except Exception as e:
        logger.error(f"Token info error: {e}")
        return None


async def search_token(query: str) -> list[dict]:
    """Search Jupiter token list by name or symbol."""
    try:
        url = "https://api.jup.ag/tokens/v2/search"
        params = {"query": query}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []
    except Exception as e:
        logger.error(f"Token search error: {e}")
        return []


# ══════════════════════════════════════════════
# COMMON TOKENS
# ══════════════════════════════════════════════

COMMON_TOKENS = {
    "SOL":   {"mint": "So11111111111111111111111111111111111111112",
              "decimals": 9, "name": "Solana"},
    "USDC":  {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
              "decimals": 6, "name": "USD Coin"},
    "USDT":  {"mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
              "decimals": 6, "name": "Tether"},
    "JUP":   {"mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
              "decimals": 6, "name": "Jupiter"},
    "BONK":  {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
              "decimals": 5, "name": "Bonk"},
    "WIF":   {"mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
              "decimals": 6, "name": "dogwifhat"},
    "TRUMP": {"mint": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
              "decimals": 6, "name": "TRUMP"},
}
