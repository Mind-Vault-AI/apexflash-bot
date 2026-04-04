"""
ApexFlash MEGA BOT - MIZAR API Integration
Copy trading, DCA bots, and marketplace access.
Docs: https://docs.mizar.com
"""
import logging
import aiohttp
from core.config import MIZAR_API_KEY, MIZAR_BASE_URL, MIZAR_REFERRAL_URL

logger = logging.getLogger(__name__)


async def get_marketplace_bots(limit: int = 10) -> list[dict]:
    """Fetch top performing bots from MIZAR marketplace."""
    if not MIZAR_API_KEY:
        return []

    try:
        url = f"{MIZAR_BASE_URL}/marketplace/bots"
        headers = {"Authorization": f"Bearer {MIZAR_API_KEY}"}
        params = {"limit": limit, "sort": "pnl_30d", "order": "desc"}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("results", data) if isinstance(data, dict) else data
                logger.warning(f"MIZAR marketplace HTTP {resp.status}")
                return []
    except Exception as e:
        logger.error(f"MIZAR marketplace error: {e}")
        return []


async def create_dca_bot(params: dict) -> dict | None:
    """Create a new DCA bot via MIZAR API."""
    if not MIZAR_API_KEY:
        return None

    try:
        url = f"{MIZAR_BASE_URL}/dca-bots"
        headers = {
            "Authorization": f"Bearer {MIZAR_API_KEY}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                error = await resp.text()
                logger.error(f"MIZAR DCA create failed: {resp.status} - {error}")
                return None
    except Exception as e:
        logger.error(f"MIZAR DCA error: {e}")
        return None


async def execute_dca_command(bot_id: str, command: str) -> dict | None:
    """Execute a command on a DCA bot (start/stop/close)."""
    if not MIZAR_API_KEY:
        return None

    try:
        url = f"{MIZAR_BASE_URL}/dca-bots/trading-view/execute-command"
        headers = {
            "Authorization": f"Bearer {MIZAR_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"bot_id": bot_id, "command": command}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                error = await resp.text()
                logger.error(f"MIZAR command failed: {resp.status} - {error}")
                return None
    except Exception as e:
        logger.error(f"MIZAR command error: {e}")
        return None


async def get_user_bots() -> list[dict]:
    """Get all DCA bots owned by the authenticated user."""
    if not MIZAR_API_KEY:
        return []

    try:
        url = f"{MIZAR_BASE_URL}/dca-bots"
        headers = {"Authorization": f"Bearer {MIZAR_API_KEY}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("results", data) if isinstance(data, dict) else data
                return []
    except Exception as e:
        logger.error(f"MIZAR get bots error: {e}")
        return []


def get_referral_url() -> str:
    """Get MIZAR referral URL for affiliate revenue."""
    return MIZAR_REFERRAL_URL
