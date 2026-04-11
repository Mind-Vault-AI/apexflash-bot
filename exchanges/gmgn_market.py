"""
ApexFlash — GMGN.AI Market Data Client
=======================================
Read-only market endpoints: trending, kline, top traders/holders, user wallets.
Auth: standard (API Key + timestamp + client_id only — no signature needed).

SSOT: GMGN_API_KEY in MASTER_ENV_APEXFLASH.txt (Box Drive)
"""
import json
import logging
import os
import time
import urllib.parse
import urllib.request
import uuid
from typing import Optional

logger = logging.getLogger("GMGNMarket")

_API_KEY  = os.getenv("GMGN_API_KEY", "").strip()
_BASE_URL = "https://gmgn.ai"


def _auth_params() -> dict:
    return {
        "api_key":   _API_KEY,
        "timestamp": str(int(time.time())),
        "client_id": str(uuid.uuid4()),
    }


def _get(path: str, params: dict = None) -> dict:
    if not _API_KEY:
        raise RuntimeError("GMGN_API_KEY not set")
    all_params = {**(params or {}), **_auth_params()}
    qs = urllib.parse.urlencode(all_params)
    url = f"{_BASE_URL}{path}?{qs}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('message', data)}")
    return data["data"]


def _post(path: str, body: dict, params: dict = None) -> dict:
    if not _API_KEY:
        raise RuntimeError("GMGN_API_KEY not set")
    all_params = {**(params or {}), **_auth_params()}
    qs = urllib.parse.urlencode(all_params)
    url = f"{_BASE_URL}{path}?{qs}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('message', data)}")
    return data["data"]


# ─── Market endpoints ─────────────────────────────────────────────────────────

def kline(
    address: str,
    resolution: str = "1h",
    chain: str = "sol",
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
) -> list:
    """
    GET /v1/market/token_kline
    Returns list of candles: {time, open, high, low, close, volume, amount}
    resolution: 1m / 5m / 15m / 1h / 4h / 1d
    """
    params = {"chain": chain, "address": address, "resolution": resolution}
    if from_ms:
        params["from"] = str(from_ms)
    if to_ms:
        params["to"] = str(to_ms)
    data = _get("/v1/market/token_kline", params)
    return data.get("list", [])


def top_traders(
    address: str,
    chain: str = "sol",
    limit: int = 20,
    order_by: str = "profit",
    tag: str = "smart_degen",
) -> list:
    """
    GET /v1/market/token_top_traders
    Returns list of top traders with PnL, holdings, wallet tags.
    """
    data = _get("/v1/market/token_top_traders", {
        "chain": chain,
        "address": address,
        "limit": str(limit),
        "order_by": order_by,
        "tag": tag,
    })
    return data.get("list", [])


def top_holders(
    address: str,
    chain: str = "sol",
    limit: int = 20,
) -> list:
    """
    GET /v1/market/token_top_holders
    Returns list of top holders (same fields as top_traders).
    """
    data = _get("/v1/market/token_top_holders", {
        "chain": chain,
        "address": address,
        "limit": str(limit),
    })
    return data.get("list", [])


def rank(
    chain: str = "sol",
    interval: str = "1h",
    limit: int = 10,
    order_by: str = "default",
    filters: Optional[list] = None,
) -> list:
    """
    GET /v1/market/rank — trending tokens.
    Returns list of RankItem with price, volume, smart_degen_count, etc.
    filters: e.g. ['renounced', 'frozen'] for SOL
    """
    params = {
        "chain": chain,
        "interval": interval,
        "limit": str(limit),
        "order_by": order_by,
    }
    qs_parts = [urllib.parse.urlencode(params)]
    if filters:
        qs_parts.append("&".join(f"filters={f}" for f in filters))
    # Build manually for multi-value params
    auth = _auth_params()
    all_qs = "&".join(qs_parts + [urllib.parse.urlencode(auth)])
    url = f"{_BASE_URL}/v1/market/rank?{all_qs}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error: {data}")
    return data["data"].get("rank", [])


def trenches(chain: str = "sol", limit: int = 10) -> dict:
    """
    POST /v1/trenches — new/pump/migrated tokens (meme early stage).
    Returns {new_creation: [], pump: [], completed: []}
    """
    data = _post("/v1/trenches", {}, {"chain": chain, "limit": str(limit)})
    return {
        "new_creation": data.get("new_creation", []),
        "pump": data.get("pump", []),
        "completed": data.get("completed", []),
    }


# ─── User/wallet endpoints ────────────────────────────────────────────────────

def user_wallets() -> list:
    """
    GET /v1/user/info — bound wallets + SOL/USDC balances.
    """
    data = _get("/v1/user/info")
    return data.get("wallets", [])


def wallet_holdings(
    wallet_address: str,
    chain: str = "sol",
    limit: int = 20,
    hide_closed: bool = True,
) -> list:
    """
    GET /v1/user/wallet_holdings — token holdings with PnL.
    """
    data = _get("/v1/user/wallet_holdings", {
        "chain": chain,
        "wallet_address": wallet_address,
        "limit": str(limit),
        "hide_closed": "true" if hide_closed else "false",
    })
    return data.get("list", [])


def wallet_stats(wallet_address: str, chain: str = "sol", period: str = "7d") -> dict:
    """
    GET /v1/user/wallet_stats — win rate, PnL, buy/sell counts.
    """
    return _get("/v1/user/wallet_stats", {
        "chain": chain,
        "wallet_address": wallet_address,
        "period": period,
    })


def wallet_activity(
    wallet_address: str,
    chain: str = "sol",
    limit: int = 20,
    token_address: Optional[str] = None,
) -> list:
    """
    GET /v1/user/wallet_activity — buy/sell/transfer history.
    """
    params = {
        "chain": chain,
        "wallet_address": wallet_address,
        "limit": str(limit),
    }
    if token_address:
        params["token_address"] = token_address
    data = _get("/v1/user/wallet_activity", params)
    return data.get("activities", [])


def is_configured() -> bool:
    return bool(_API_KEY)


def format_rank_signal(token: dict) -> str:
    """Format a rank item into a Grade A signal string."""
    sym = token.get("symbol", "?")
    price = float(token.get("price", 0))
    chg_1h = float(token.get("price_change_percent1h", 0))
    chg_5m = float(token.get("price_change_percent5m", 0))
    vol = float(token.get("volume", 0))
    smart = token.get("smart_degen_count", 0)
    renowned = token.get("renowned_count", 0)
    addr = token.get("address", "")[:12]

    return (
        f"🔥 *{sym}* | ${price:.6f}\n"
        f"📈 1h: {chg_1h:+.1f}% | 5m: {chg_5m:+.1f}%\n"
        f"💰 Vol: ${vol:,.0f}\n"
        f"🧠 Smart Degens: {smart} | Renowned: {renowned}\n"
        f"`{addr}...`"
    )
