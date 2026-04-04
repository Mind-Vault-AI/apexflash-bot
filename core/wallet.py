"""
ApexFlash MEGA BOT - Solana Wallet Management
Secure wallet creation, encryption, balance checking via Helius RPC.
Fee collection transfers to platform wallet.
"""
import base64
import logging
import aiohttp
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.message import Message
from solders.hash import Hash
from cryptography.fernet import Fernet

from core.config import HELIUS_RPC_URL, WALLET_ENCRYPTION_KEY

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
# SOLANA RPC CALLS (Helius + public fallback)
# ══════════════════════════════════════════════

_PUBLIC_RPC = "https://api.mainnet-beta.solana.com"


async def _rpc(method: str, params: list) -> dict:
    """JSON-RPC call to Solana. Tries Helius first, falls back to public RPC."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [HELIUS_RPC_URL, _PUBLIC_RPC]

    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(endpoints):
            try:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp:
                    if resp.status == 429:
                        logger.warning(f"RPC [{method}]: 429 rate-limited on endpoint {i}, trying fallback")
                        continue
                    if resp.status != 200:
                        logger.warning(f"RPC [{method}]: HTTP {resp.status} on endpoint {i}, trying fallback")
                        continue
                    data = await resp.json()
                    if "error" in data:
                        logger.error(f"RPC [{method}]: {data['error']}")
                    return data
            except Exception as e:
                logger.warning(f"RPC [{method}]: endpoint {i} failed: {e}")
                continue

    # All endpoints failed
    logger.error(f"RPC [{method}]: all endpoints failed")
    return {"error": "all RPC endpoints unreachable"}


async def get_sol_balance(pubkey: str) -> float | None:
    """Get SOL balance in human-readable units.
    Returns None if ALL RPC endpoints fail (caller should show error, not 0.0)."""
    try:
        data = await _rpc("getBalance", [pubkey])
        if "error" in data and data["error"] == "all RPC endpoints unreachable":
            logger.error(f"Balance UNREACHABLE for {pubkey[:8]}... — all RPCs down")
            return None
        lamports = data.get("result", {}).get("value", 0)
        sol = lamports / 1_000_000_000
        logger.info(f"Balance for {pubkey[:8]}...: {sol} SOL ({lamports} lamports)")
        return sol
    except Exception as e:
        logger.error(f"Balance error for {pubkey[:8]}...: {e}")
        return None


async def get_token_balances(pubkey: str) -> list[dict]:
    """Get all SPL token balances for a wallet.
    Checks BOTH Token Program (legacy) AND Token2022 Program (modern memecoins).
    """
    TOKEN_PROGRAMS = [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token (legacy)
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",   # Token2022 (modern)
    ]
    tokens = []
    seen_mints = set()
    for program_id in TOKEN_PROGRAMS:
        try:
            data = await _rpc("getTokenAccountsByOwner", [
                pubkey,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ])
            accounts = data.get("result", {}).get("value", [])
            for acc in accounts:
                info = (acc.get("account", {}).get("data", {})
                        .get("parsed", {}).get("info", {}))
                ta = info.get("tokenAmount", {})
                # uiAmount can be null for Token2022 tokens with certain extensions.
                # Fall back to uiAmountString (always present as a string) before giving up.
                ui = ta.get("uiAmount")
                if ui is None:
                    try:
                        ui = float(ta.get("uiAmountString", "0") or "0")
                    except (ValueError, TypeError):
                        ui = 0.0
                amount = float(ui or 0)
                mint = info.get("mint", "")
                if amount > 0 and mint and mint not in seen_mints:
                    seen_mints.add(mint)
                    tokens.append({
                        "mint": mint,
                        "amount": amount,
                        "decimals": ta.get("decimals", 0),
                        "raw_amount": ta.get("amount", "0"),
                    })
        except Exception as e:
            logger.error(f"Token balances error (program {program_id[:8]}...): {e}")
    return tokens


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


# ══════════════════════════════════════════════
# FEE COLLECTION (SOL transfer)
# ══════════════════════════════════════════════

async def _get_recent_blockhash() -> str | None:
    """Get a recent blockhash for transaction building."""
    try:
        data = await _rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        return data.get("result", {}).get("value", {}).get("blockhash")
    except Exception as e:
        logger.error(f"Blockhash error: {e}")
        return None


async def transfer_sol(
    from_keypair: Keypair,
    to_pubkey_str: str,
    lamports: int,
) -> str | None:
    """Transfer SOL from one wallet to another.

    Used to collect platform fees after each swap.
    Returns transaction signature or None.
    """
    if lamports <= 0:
        return None

    try:
        to_pubkey = Pubkey.from_string(to_pubkey_str)
        blockhash_str = await _get_recent_blockhash()
        if not blockhash_str:
            logger.error("Fee transfer: no blockhash")
            return None

        # Build transfer instruction
        ix = transfer(TransferParams(
            from_pubkey=from_keypair.pubkey(),
            to_pubkey=to_pubkey,
            lamports=lamports,
        ))

        # Build and sign transaction
        blockhash = Hash.from_string(blockhash_str)
        msg = Message.new_with_blockhash(
            [ix], from_keypair.pubkey(), blockhash,
        )
        tx = Transaction.new_unsigned(msg)
        tx.sign([from_keypair], blockhash)

        # Send
        encoded = base64.b64encode(bytes(tx)).decode()
        sig = await send_raw_transaction(encoded)
        if sig:
            logger.info(f"Fee transfer OK: {lamports} lamports -> {to_pubkey_str[:12]}... tx={sig}")
        return sig

    except Exception as e:
        logger.error(f"Fee transfer error: {e}")
        return None


async def collect_fee(
    user_keypair: Keypair,
    fee_lamports: int,
    fee_wallet: str,
) -> str | None:
    """Collect platform fee from user wallet to fee collection wallet.

    Called after a successful swap. Best-effort — if this fails,
    the fee stays in the user wallet (no money lost, just uncollected).
    """
    if fee_lamports < 5000:  # Skip dust (< 0.000005 SOL, less than tx fee)
        logger.debug(f"Fee too small to collect: {fee_lamports} lamports")
        return None

    return await transfer_sol(user_keypair, fee_wallet, fee_lamports)
