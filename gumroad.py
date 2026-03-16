"""
ApexFlash MEGA BOT - Gumroad API Integration
═════════════════════════════════════════════
Verifies Gumroad license keys and manages premium activations.

Flow:
  1. User buys Pro/Elite on Gumroad → gets license key
  2. User enters license key in bot (/activate or menu)
  3. Bot verifies via Gumroad API → activates premium tier

Endpoints used:
  - POST /v2/licenses/verify  — verify a license key
  - GET  /v2/products         — list products (admin)
  - GET  /v2/sales            — list recent sales (admin)
"""
import logging
import aiohttp

from config import (
    GUMROAD_ACCESS_TOKEN,
    GUMROAD_PRO_PRODUCT_ID,
    GUMROAD_ELITE_PRODUCT_ID,
)

logger = logging.getLogger("ApexFlash.gumroad")

GUMROAD_API_BASE = "https://api.gumroad.com/v2"


async def verify_license(license_key: str) -> dict | None:
    """
    Verify a Gumroad license key.

    Returns dict with:
      - valid: bool
      - tier: "pro" | "elite" | None
      - email: str (buyer email)
      - product_name: str
      - uses: int (how many times activated)
      - purchase_id: str

    Returns None on API error.
    """
    url = f"{GUMROAD_API_BASE}/licenses/verify"

    # Try each product permalink to find which one the key belongs to
    product_ids = []
    if GUMROAD_PRO_PRODUCT_ID:
        product_ids.append(("pro", GUMROAD_PRO_PRODUCT_ID))
    if GUMROAD_ELITE_PRODUCT_ID:
        product_ids.append(("elite", GUMROAD_ELITE_PRODUCT_ID))

    for tier, product_id in product_ids:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "product_id": product_id,
                    "license_key": license_key.strip(),
                    "increment_uses_count": True,
                }
                async with session.post(url, data=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            purchase = data.get("purchase", {})
                            return {
                                "valid": True,
                                "tier": tier,
                                "email": purchase.get("email", ""),
                                "product_name": purchase.get("product_name", ""),
                                "uses": data.get("uses", 0),
                                "purchase_id": purchase.get("id", ""),
                                "refunded": purchase.get("refunded", False),
                                "chargebacked": purchase.get("chargebacked", False),
                                "subscription_cancelled": purchase.get(
                                    "subscription_cancelled_at"
                                )
                                is not None,
                            }
                    # 404 means wrong product for this key — try next
                    elif resp.status == 404:
                        continue
                    else:
                        error_text = await resp.text()
                        logger.warning(
                            f"Gumroad verify error ({resp.status}): {error_text[:200]}"
                        )
        except Exception as e:
            logger.error(f"Gumroad API error: {e}")
            return None

    # Key didn't match any product
    return {"valid": False, "tier": None, "email": "", "product_name": "",
            "uses": 0, "purchase_id": "", "refunded": False,
            "chargebacked": False, "subscription_cancelled": False}


async def get_products() -> list[dict]:
    """List all Gumroad products (admin use)."""
    if not GUMROAD_ACCESS_TOKEN:
        logger.warning("GUMROAD_ACCESS_TOKEN not set — cannot list products")
        return []

    url = f"{GUMROAD_API_BASE}/products"
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {GUMROAD_ACCESS_TOKEN}"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("products", [])
                logger.warning(f"Gumroad products error: {resp.status}")
    except Exception as e:
        logger.error(f"Gumroad products API error: {e}")
    return []


async def get_recent_sales(page: int = 1) -> list[dict]:
    """Get recent sales (admin use). Returns list of sale dicts."""
    if not GUMROAD_ACCESS_TOKEN:
        logger.warning("GUMROAD_ACCESS_TOKEN not set — cannot list sales")
        return []

    url = f"{GUMROAD_API_BASE}/sales"
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {GUMROAD_ACCESS_TOKEN}"}
            params = {"page": page}
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("sales", [])
                logger.warning(f"Gumroad sales error: {resp.status}")
    except Exception as e:
        logger.error(f"Gumroad sales API error: {e}")
    return []


async def get_subscriber_count() -> dict:
    """Get subscriber counts per product (admin use)."""
    products = await get_products()
    counts = {"pro": 0, "elite": 0, "total": 0}

    for p in products:
        permalink = p.get("custom_permalink") or p.get("short_url", "")
        subs = p.get("sales_count", 0)
        if GUMROAD_PRO_PRODUCT_ID and GUMROAD_PRO_PRODUCT_ID in permalink:
            counts["pro"] = subs
        elif GUMROAD_ELITE_PRODUCT_ID and GUMROAD_ELITE_PRODUCT_ID in permalink:
            counts["elite"] = subs
        counts["total"] += subs

    return counts
