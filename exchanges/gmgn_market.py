"""
ApexFlash — GMGN.AI Market Data Client
=======================================
Read-only market endpoints: trending, kline, top traders/holders, user wallets.

Auth modes (per official gmgn-cli source):
  Normal (market/token/portfolio): X-APIKEY header + timestamp (seconds) + client_id in query
  Critical (swap/order):           normal auth + X-Signature (Ed25519 signed message)

SSOT: GMGN_API_KEY + GMGN_PRIVATE_KEY in MASTER_ENV_APEXFLASH.txt (Box Drive)
"""
import base64
import json
import logging
import os
import time
import urllib.parse
import urllib.request
import uuid
from typing import Optional

logger = logging.getLogger("GMGNMarket")

_API_KEY     = os.getenv("GMGN_API_KEY", "").strip()
_PRIVATE_KEY = os.getenv("GMGN_PRIVATE_KEY", "").strip()
_BASE_URL    = "https://openapi.gmgn.ai"
_privkey_obj = None


def _load_privkey():
    global _privkey_obj
    if _privkey_obj is not None:
        return _privkey_obj
    if not _PRIVATE_KEY:
        raise RuntimeError("GMGN_PRIVATE_KEY not set")
    from cryptography.hazmat.primitives.serialization import load_der_private_key
    der = base64.b64decode(_PRIVATE_KEY)
    _privkey_obj = load_der_private_key(der, password=None)
    return _privkey_obj


def _auth_query() -> dict:
    """Auth query params for normal requests: timestamp (seconds) + client_id only.
    API key goes in the X-APIKEY header, NOT in query params.
    """
    return {
        "timestamp": str(int(time.time())),   # SECONDS — not milliseconds
        "client_id": str(uuid.uuid4()),
    }


def _normal_headers() -> dict:
    """Headers for normal (non-signing) requests."""
    return {
        "X-APIKEY":       _API_KEY,
        "Content-Type":   "application/json",
        "User-Agent":     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":         "application/json, text/plain, */*",
    }


def _build_critical_signature(sub_path: str, query: dict, body_str: str, timestamp: int) -> str:
    """Ed25519 signature for critical (swap/order) endpoints.
    Message format: {sub_path}:{sorted_query_string}:{body}:{timestamp}
    """
    key = _load_privkey()
    sorted_qs = "&".join(
        f"{k}={v}" for k, v in sorted(query.items())
    )
    message = f"{sub_path}:{sorted_qs}:{body_str}:{timestamp}"
    sig_bytes = key.sign(message.encode("utf-8"))
    return base64.b64encode(sig_bytes).decode("utf-8")  # standard base64, not URL-safe


def _get_outbound_ip() -> str:
    """Fetch current outbound IP — used for GMGN whitelist diagnostics."""
    try:
        req = urllib.request.Request("https://api.ipify.org?format=json",
                                     headers={"User-Agent": "ApexFlash/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("ip", "unknown")
    except Exception:
        return "unknown"


def _get(path: str, params: dict = None) -> dict:
    """Normal GET request — X-APIKEY header, no signature."""
    if not _API_KEY:
        raise RuntimeError("GMGN_API_KEY not set")
    all_params = {**(params or {}), **_auth_query()}
    qs = urllib.parse.urlencode(sorted(all_params.items()))
    url = f"{_BASE_URL}{path}?{qs}"
    req = urllib.request.Request(url, headers=_normal_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            ip = _get_outbound_ip()
            logger.error(f"GMGN 403 — IP [{ip}] rejected (check GMGN whitelist)")
            _record_403(ip)
            raise RuntimeError(f"GMGN 403 — IP {ip}")
        raise RuntimeError(f"GMGN HTTP {e.code}: {e.reason}")
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('message', data)}")
    # openapi.gmgn.ai double-wraps: outer.data = inner; inner.data = actual payload
    inner = data.get("data", {})
    return inner.get("data", inner)


def _record_403(ip: str) -> None:
    """
    Track every GMGN 403 in Redis so bot.py's /ip_status and escalate-job
    can surface a coherent picture to the admin. Escalates after 3 in 1h.
    """
    try:
        from core.persistence import _get_redis
        r = _get_redis()
        if not r:
            return
        r.setex("apexflash:render:outbound_ip", 3600, ip)
        r.setex("apexflash:gmgn:403_last_ip", 7200, ip)
        r.setex("apexflash:gmgn:403_last_ts", 7200, str(int(time.time())))
        cnt = r.incr("apexflash:gmgn:403_count_total")
        r.expire("apexflash:gmgn:403_count_total", 3600)
        if cnt and int(cnt) >= 3:
            r.setex("apexflash:gmgn:403_escalate", 3600, ip)
    except Exception:
        pass


def _post(path: str, body: dict, params: dict = None) -> dict:
    """Normal POST request — X-APIKEY header, no signature."""
    if not _API_KEY:
        raise RuntimeError("GMGN_API_KEY not set")
    all_params = {**(params or {}), **_auth_query()}
    qs = urllib.parse.urlencode(sorted(all_params.items()))
    url = f"{_BASE_URL}{path}?{qs}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers=_normal_headers(),
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            ip = _get_outbound_ip()
            logger.error(f"GMGN 403 — IP {ip} rejected")
            _record_403(ip)
            raise RuntimeError(f"GMGN 403 — IP {ip}")
        raise RuntimeError(f"GMGN HTTP {e.code}: {e.reason}")
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('message', data)}")
    inner = data.get("data", {})
    return inner.get("data", inner)


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
    all_params = {
        "chain": chain,
        "interval": interval,
        "limit": str(limit),
        "order_by": order_by,
        **_auth_query(),
    }
    qs_parts = [urllib.parse.urlencode(sorted(all_params.items()))]
    if filters:
        qs_parts.append("&".join(f"filters={f}" for f in filters))
    url = f"{_BASE_URL}/v1/market/rank?{'&'.join(qs_parts)}"
    req = urllib.request.Request(url, headers=_normal_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            ip = _get_outbound_ip()
            _record_403(ip)
            raise RuntimeError(f"GMGN rank 403 — IP {ip}")
        raise RuntimeError(f"GMGN rank HTTP {e.code}: {e.reason}")
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error: {data}")
    inner = data.get("data", {})
    actual = inner.get("data", inner)
    return actual.get("rank", [])


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
    return bool(_API_KEY and _PRIVATE_KEY)


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
