"""
ApexFlash Whale Watcher v2.0
────────────────────────────────────────────────────────
Objective  : Track Legendary whale wallets on Solana.
Trigger    : Whale buys ≥ 10 SOL → GMGN smart_degen score ≥ 60 → Grade S signal.
Difference vs Inspector: Inspector = alpha wallets (0.05+ SOL).
                         Whale Watcher = legendary wallets (10+ SOL), Grade S.

Integrations:
  - Helius Enhanced Transactions API  (HELIUS_API_KEY)
  - GMGN wallet scoring API           (GMGN_API_KEY, no signing required for read)
  - RugCheck safety gate
  - Redis: stores signals + seen sigs

Usage (called from bot.py):
  from agents.whale_watcher import whale_watcher_job, register_whale_callback
  register_whale_callback(my_handler)
"""

import asyncio
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# LEGENDARY WALLETS — publicly known Solana mega-traders
# Add more via env: WHALE_WALLETS=addr1:Label1,addr2:Label2
# Min trade to trigger: WHALE_MIN_SOL (default 10 SOL)
# ═══════════════════════════════════════════════════════════════════

WHALE_MIN_SOL = float(os.getenv("WHALE_MIN_SOL", "10.0"))
GMGN_MIN_SCORE = float(os.getenv("GMGN_MIN_SCORE", "60.0"))  # 0-100 scale

LEGENDARY_WALLETS: dict[str, str] = {
    # Publicly identified Solana mega-wallets (on-chain, no private info)
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU": "Ansem",
    "GpcDkBEhNAzwbBLmMBnVRbcGQFJXvpxFCoPDJKnHpump": "Murad",
    "Hn7HCj2jdWfHNhXqZKnADSSzjJPFYdaVYQXfGc4vDrk3": "Hsaka",
    "5tzFkiKscXHK5ZXCGbXZxdw7gkg7jbtvX4bSBn21e3Sy": "Legendary_1",
    "CRdoZsNvGECMRAvHRLFBVHuFhRxAi3BDhR29SaYDgDx3": "Legendary_2",
}

# Add from env
_extra = os.getenv("WHALE_WALLETS", "")
if _extra:
    for entry in _extra.split(","):
        entry = entry.strip()
        if ":" in entry:
            addr, label = entry.split(":", 1)
        else:
            addr, label = entry, f"Whale_{entry[:8]}"
        if len(addr) >= 32:
            LEGENDARY_WALLETS[addr] = label.strip()

# ═══════════════════════════════════════════════════════════════════
# RUNTIME STATE
# ═══════════════════════════════════════════════════════════════════

_seen_sigs: set[str] = set()
_SEEN_MAX = 500
_signal_callbacks: list = []


def register_whale_callback(cb) -> None:
    """bot.py registers here to receive Grade S signals."""
    _signal_callbacks.append(cb)


def get_legendary_wallets() -> dict:
    return dict(LEGENDARY_WALLETS)


# ═══════════════════════════════════════════════════════════════════
# HELIUS: FETCH RECENT SWAPS
# ═══════════════════════════════════════════════════════════════════

async def _helius_swaps(session: aiohttp.ClientSession, pubkey: str, api_key: str) -> list[dict]:
    """Fetch recent SWAP transactions for a wallet via Helius Enhanced TX API."""
    url = f"https://api.helius.xyz/v0/addresses/{pubkey}/transactions"
    params = {"api-key": api_key, "limit": 10, "type": "SWAP"}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                return await r.json()
            logger.debug(f"Helius {r.status} for {pubkey[:8]}...")
    except Exception as e:
        logger.debug(f"Helius error ({pubkey[:8]}...): {e}")
    return []


def _parse_swap(tx: dict) -> Optional[dict]:
    """Extract BUY from Helius Enhanced Transaction. Returns None for sells/unknown."""
    try:
        sig = tx.get("signature", "")
        swap = (tx.get("events") or {}).get("swap") or {}
        if not swap:
            return None

        native_in = swap.get("nativeInput") or {}
        token_out = (swap.get("tokenOutputs") or [{}])[0]

        # SOL → Token = BUY
        if native_in.get("amount") and token_out.get("mint"):
            return {
                "sig": sig,
                "mint": token_out["mint"],
                "amount_sol": int(native_in["amount"]) / 1e9,
            }
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
# GMGN: SMART DEGEN SCORE
# Returns 0-100 score. ≥ GMGN_MIN_SCORE = confirmed smart money.
# ═══════════════════════════════════════════════════════════════════

async def _gmgn_score(session: aiohttp.ClientSession, wallet: str, api_key: str) -> float:
    """
    Fetch GMGN smart_degen score for a wallet.
    Endpoint: /defi/quotation/v1/smartmoney/sol/walletNew/{wallet}?period=7d
    Returns score 0-100 (higher = smarter). -1 on failure.
    """
    url = f"https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{wallet}"
    params = {"period": "7d"}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with session.get(
            url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            if r.status == 200:
                data = await r.json()
                wallet_data = (data.get("data") or {})
                score = wallet_data.get("smart_degen_score") or wallet_data.get("score")
                if score is not None:
                    return float(score)
            logger.debug(f"GMGN score {r.status} for {wallet[:8]}...")
    except Exception as e:
        logger.debug(f"GMGN error ({wallet[:8]}...): {e}")
    return -1.0


# ═══════════════════════════════════════════════════════════════════
# RUGCHECK: SAFETY GATE
# ═══════════════════════════════════════════════════════════════════

async def _rugcheck(session: aiohttp.ClientSession, mint: str) -> dict:
    """Quick rug safety gate. Returns {safe, score}."""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
            if r.status == 200:
                data = await r.json()
                score = data.get("score", 0)
                danger = [
                    x for x in (data.get("risks") or [])
                    if x.get("level") == "danger"
                ]
                return {"safe": score >= 500 and len(danger) == 0, "score": score}
    except Exception:
        pass
    return {"safe": None, "score": 0}


# ═══════════════════════════════════════════════════════════════════
# MAIN WHALE WATCHER JOB
# Called every 90s from bot.py scheduler.
# ═══════════════════════════════════════════════════════════════════

async def whale_watcher_job(context=None) -> list[dict]:
    """
    Whale surveillance cycle:
    1. Fetch recent SWAPs for each legendary wallet (Helius)
    2. Gate on size (≥ WHALE_MIN_SOL)
    3. Score wallet via GMGN (≥ GMGN_MIN_SCORE)
    4. Safety gate via RugCheck
    5. Emit Grade S signal → callbacks + Redis

    Returns list of Grade S signals fired.
    """
    from core.config import HELIUS_API_KEY
    gmgn_api_key = os.getenv("GMGN_API_KEY", "")

    if not HELIUS_API_KEY:
        logger.warning("WhaleWatcher: HELIUS_API_KEY not set — skipping")
        return []

    fired: list[dict] = []

    async with aiohttp.ClientSession() as session:
        for wallet_addr, wallet_label in list(LEGENDARY_WALLETS.items()):
            try:
                txs = await _helius_swaps(session, wallet_addr, HELIUS_API_KEY)
                await asyncio.sleep(0.4)  # Helius rate limit

                for tx in txs:
                    sig = tx.get("signature", "")
                    if not sig or sig in _seen_sigs:
                        continue

                    swap = _parse_swap(tx)
                    _seen_sigs.add(sig)

                    # Trim seen set
                    if len(_seen_sigs) > _SEEN_MAX:
                        for _ in range(50):
                            _seen_sigs.pop()

                    if not swap:
                        continue

                    amount_sol = swap["amount_sol"]
                    mint = swap["mint"]

                    # ── Size gate ──
                    if amount_sol < WHALE_MIN_SOL:
                        continue

                    logger.info(
                        f"WhaleWatcher: {wallet_label} bought {amount_sol:.1f} SOL "
                        f"→ {mint[:12]}... (tx {sig[:16]}...)"
                    )

                    # ── GMGN smart_degen score ──
                    score = await _gmgn_score(session, wallet_addr, gmgn_api_key)
                    if score >= 0 and score < GMGN_MIN_SCORE:
                        logger.info(
                            f"WhaleWatcher: {wallet_label} GMGN score {score:.0f} "
                            f"< {GMGN_MIN_SCORE} threshold — skip"
                        )
                        continue

                    # ── Safety gate ──
                    rug = await _rugcheck(session, mint)
                    if rug["safe"] is False:
                        logger.info(
                            f"WhaleWatcher: BLOCKED {mint[:12]}... rug score={rug['score']}"
                        )
                        continue

                    # ── Build Grade S signal ──
                    signal = {
                        "type": "WHALE",
                        "grade": "S",
                        "wallet_label": wallet_label,
                        "wallet_addr": wallet_addr,
                        "mint": mint,
                        "amount_sol": amount_sol,
                        "tx_sig": sig,
                        "gmgn_score": score,
                        "rug": rug,
                    }

                    # ── Persist to Redis ──
                    try:
                        from core.persistence import _get_redis
                        r = _get_redis()
                        if r:
                            import json
                            r.lpush("apexflash:whale_signals", json.dumps(signal))
                            r.ltrim("apexflash:whale_signals", 0, 99)  # keep last 100
                    except Exception as e:
                        logger.debug(f"WhaleWatcher Redis write error: {e}")

                    fired.append(signal)
                    logger.info(
                        f"WhaleWatcher: Grade S FIRED — {wallet_label} "
                        f"{amount_sol:.1f} SOL on {mint[:12]}... "
                        f"(GMGN {score:.0f})"
                    )

                    # ── Dispatch callbacks ──
                    for cb in _signal_callbacks:
                        try:
                            await cb(signal)
                        except Exception as cb_err:
                            logger.error(f"WhaleWatcher callback error: {cb_err}")

            except Exception as e:
                logger.debug(f"WhaleWatcher wallet error ({wallet_label}): {e}")
                continue

    return fired


# ═══════════════════════════════════════════════════════════════════
# FORMAT SIGNAL FOR TELEGRAM
# ═══════════════════════════════════════════════════════════════════

def format_whale_signal(signal: dict) -> str:
    """Format a Grade S whale signal for Telegram (Markdown)."""
    mint = signal["mint"]
    label = signal["wallet_label"]
    sol = signal["amount_sol"]
    gmgn = signal.get("gmgn_score", -1)
    rug = signal.get("rug", {})

    gmgn_line = f"GMGN Score: {gmgn:.0f}/100" if gmgn >= 0 else "GMGN Score: N/A"
    rug_line = (
        f"✅ Safe (rug score {rug.get('score', '?')})"
        if rug.get("safe")
        else "⚠️ Unverified"
    )

    dex_url = f"https://dexscreener.com/solana/{mint}"
    gmgn_url = f"https://gmgn.ai/sol/token/{mint}"

    return (
        f"🐋 *GRADE S — WHALE SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Wallet: *{label}*\n"
        f"💰 Size: *{sol:.1f} SOL*\n"
        f"🪙 Token: `{mint[:20]}...`\n"
        f"📊 {gmgn_line}\n"
        f"🛡 {rug_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"[DexScreener]({dex_url}) | [GMGN]({gmgn_url})"
    )
