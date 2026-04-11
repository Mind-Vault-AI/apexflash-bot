"""
ApexFlash — GMGN.AI Trading API Client
=======================================
Solana/BSC/Base swaps via GMGN API with Ed25519 signature auth.

Auth flow (per GMGN docs/auth.md):
  1. Build query string from params (sorted alphabetically)
  2. Append ?api_key=<key>&timestamp=<unix_ms>&client_id=<uuid>
  3. Sign the full URL path+query with Ed25519 private key (PKCS#8)
  4. Add X-API-Signature header

SSOT: keys come from env — set in MASTER_ENV_APEXFLASH.txt (Box Drive).
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

logger = logging.getLogger("GMGN")

# ─── Keys ────────────────────────────────────────────────────────────────────
_API_KEY     = os.getenv("GMGN_API_KEY", "").strip()
_PRIVATE_KEY = os.getenv("GMGN_PRIVATE_KEY", "").strip()   # base64 PKCS#8 DER
_BASE_URL    = "https://gmgn.ai"

_privkey_obj = None


def _load_privkey():
    """Load Ed25519 private key from env (lazy, once)."""
    global _privkey_obj
    if _privkey_obj is not None:
        return _privkey_obj
    if not _PRIVATE_KEY:
        raise RuntimeError("GMGN_PRIVATE_KEY not set")
    try:
        from cryptography.hazmat.primitives.serialization import load_der_private_key
        der = base64.b64decode(_PRIVATE_KEY)
        _privkey_obj = load_der_private_key(der, password=None)
    except Exception as e:
        raise RuntimeError(f"Failed to load GMGN private key: {e}")
    return _privkey_obj


def _sign(url_path_and_query: str) -> str:
    """Sign a URL path+query string with Ed25519. Returns base64url signature."""
    key = _load_privkey()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    msg = url_path_and_query.encode("utf-8")
    sig_bytes = key.sign(msg)
    return base64.urlsafe_b64encode(sig_bytes).decode("utf-8").rstrip("=")


def _auth_params() -> dict:
    return {
        "api_key":   _API_KEY,
        "timestamp": str(int(time.time() * 1000)),
        "client_id": str(uuid.uuid4()),
    }


def _signed_url(path: str, params: dict) -> tuple[str, str]:
    """
    Build full signed URL.
    Returns (full_url, signature) — signature goes in X-API-Signature header.
    """
    all_params = {**params, **_auth_params()}
    # Sort params for deterministic signing
    qs = urllib.parse.urlencode(sorted(all_params.items()))
    path_and_query = f"{path}?{qs}"
    sig = _sign(path_and_query)
    return f"{_BASE_URL}{path_and_query}", sig


def _get(path: str, params: dict) -> dict:
    url, sig = _signed_url(path, params)
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('msg', data)}")
    return data["data"]


def _post(path: str, body: dict) -> dict:
    auth = _auth_params()
    # For POST: auth params go in query string, body is JSON
    qs = urllib.parse.urlencode(sorted(auth.items()))
    path_and_query = f"{path}?{qs}"
    sig = _sign(path_and_query)
    url = f"{_BASE_URL}{path_and_query}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-API-Signature": sig,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"GMGN error {data.get('code')}: {data.get('msg', data)}")
    return data["data"]


# ─── Public API ───────────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(_API_KEY and _PRIVATE_KEY)


def quote(
    from_address: str,
    input_token: str,
    output_token: str,
    input_amount: str,
    slippage: float = 0.1,
    chain: str = "sol",
) -> dict:
    """
    GET /v1/trade/quote — get swap quote (no transaction submitted).

    Returns QuoteResult dict with: input_amount, output_amount,
    min_output_amount, slippage.
    """
    return _get("/v1/trade/quote", {
        "chain":        chain,
        "from_address": from_address,
        "input_token":  input_token,
        "output_token": output_token,
        "input_amount": input_amount,
        "slippage":     str(slippage),
    })


def swap(
    from_address: str,
    input_token: str,
    output_token: str,
    input_amount: str,
    slippage: float = 0.1,
    chain: str = "sol",
    is_anti_mev: bool = True,
    priority_fee: Optional[str] = None,
) -> dict:
    """
    POST /v1/trade/swap — submit a swap transaction.

    from_address must match the wallet bound to the GMGN API key.
    Returns OrderResponse with: status, hash, order_id.
    """
    body = {
        "chain":        chain,
        "from_address": from_address,
        "input_token":  input_token,
        "output_token": output_token,
        "input_amount": input_amount,
        "slippage":     slippage,
        "is_anti_mev":  is_anti_mev,
    }
    if priority_fee:
        body["priority_fee"] = priority_fee
    return _post("/v1/trade/swap", body)


def query_order(order_id: str, chain: str = "sol") -> dict:
    """
    GET /v1/trade/query_order — poll order status.

    Returns OrderResponse: status (pending/processed/confirmed/failed/expired).
    """
    return _get("/v1/trade/query_order", {
        "order_id": order_id,
        "chain":    chain,
    })


def wait_for_confirmation(
    order_id: str,
    chain: str = "sol",
    timeout_sec: int = 60,
    poll_sec: int = 3,
) -> dict:
    """Poll order until confirmed/failed/expired or timeout. Returns final order dict."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        order = query_order(order_id, chain)
        status = order.get("status", "")
        if status in ("confirmed", "failed", "expired"):
            return order
        time.sleep(poll_sec)
    return {"status": "timeout", "order_id": order_id}
