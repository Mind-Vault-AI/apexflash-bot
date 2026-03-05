"""
ApexFlash MEGA BOT - Solana Wallet Management
Secure wallet creation, encryption, balance checking via Helius RPC.
"""
import logging
import aiohttp
from solders.keypair import Keypair
from cryptography.fernet import Fernet

from config import HELIUS_RPC_URL, WALLET_ENCRYPTION_KEY

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# ENCRYPTION
# ══════════════════════════════════════════════

def _get_fernet() -> Fernet:
    """Get Fernet cipher for wallet key encryption."""
    if not WALLET_ENCRYPTION_KEY:
        raise ValueError("WALLET_ENCRYPTION_KEY not configured")
    return Fernet(WALLET_ENCRYPTION_KEY.encode())


def encrypt_secret(secret_bytes: bytes) -> str:
    """Encrypt a private key for safe storage."""
    return _get_fernet().encrypt(secret_bytes).decode()


def decrypt_secret(encrypted: str) -> bytes:
    """Decrypt a stored private key."""
    return _get_fernet().decrypt(encrypted.encode())


# ══════════════════════════════════════════════
# WALLET OPERATIONS
# ══════════════════════════════════════════════

def create_wallet() -> dict:
    """Generate a new Solana wallet.

    Returns dict with pubkey (str) and encrypted_secret (str).
    """
    kp = Keypair()
    return {
        "pubkey": str(kp.pubkey()),
        "encrypted_secret": encrypt_secret(bytes(kp)),
    }


def load_keypair(encrypted_secret: str) -> Keypair:
    """Load a Keypair from its encrypted secret."""
    return Keypair.from_bytes(decrypt_secret(encrypted_secret))


# ══════════════════════════════════════════════
# SOLANA RPC CALLS (via Helius)
# ══════════════════════════════════════════════

async def _rpc(method: str, params: list) -> dict:
    """JSON-RPC call to Solana via Helius."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            HELIUS_RPC_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                logger.error(f"RPC [{method}]: {data['error']}")
            return data


async def get_sol_balance(pubkey: str) -> float:
    """Get SOL balance in human-readable units."""
    try:
        data = await _rpc("getBalance", [pubkey])
        lamports = data.get("result", {}).get("value", 0)
        return lamports / 1_000_000_000
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return 0.0


async def get_token_balances(pubkey: str) -> list[dict]:
    """Get all SPL token balances for a wallet."""
    try:
        data = await _rpc("getTokenAccountsByOwner", [
            pubkey,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ])
        accounts = data.get("result", {}).get("value", [])
        tokens = []
        for acc in accounts:
            info = (acc.get("account", {}).get("data", {})
                    .get("parsed", {}).get("info", {}))
            ta = info.get("tokenAmount", {})
            amount = float(ta.get("uiAmount", 0) or 0)
            if amount > 0:
                tokens.append({
                    "mint": info.get("mint", ""),
                    "amount": amount,
                    "decimals": ta.get("decimals", 0),
                    "raw_amount": ta.get("amount", "0"),
                })
        return tokens
    except Exception as e:
        logger.error(f"Token balances error: {e}")
        return []


async def send_raw_transaction(signed_tx_b64: str) -> str | None:
    """Submit a signed transaction to Solana."""
    try:
        data = await _rpc("sendTransaction", [
            signed_tx_b64,
            {"encoding": "base64", "skipPreflight": True, "maxRetries": 3},
        ])
        return data.get("result")
    except Exception as e:
        logger.error(f"Send tx error: {e}")
        return None
