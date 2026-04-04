"""
ApexFlash Marketing Agency Worker (Cycle 4 Delegation)
────────────────────────────────────────────────────────
Objective: Offload high-latency social media tasks from the core trading engine.
Consumes: Redis list 'queue:marketing'
Tasks: discord_alert, twitter_post, telegram_broadcast
"""

import json
import time
import logging
import asyncio
import aiohttp
from core.persistence import _get_redis
from core.config import DISCORD_WEBHOOK_URL, TWITTER_ENABLED

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] AGENCY: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MarketingAgency")

async def send_discord_webhook(content: str):
    """Send alert to Discord without blocking the bot."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"content": content}
            async with session.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5) as resp:
                if resp.status in [200, 204]:
                    logger.info("Discord alert sent successfully.")
                else:
                    logger.warning(f"Discord alert failed with status {resp.status}")
    except Exception as e:
        logger.error(f"Discord error: {e}")

async def process_task(task: dict):
    """Router for agency tasks."""
    action = task.get("action")
    data = task.get("data", {})
    
    logger.info(f"Processing Task: {action}")
    
    if action == "discord_alert":
        await send_discord_webhook(data.get("msg", ""))
    elif action == "twitter_post":
        # Placeholder for twitter integration (already exists in twitter_poster.py)
        # We can call twitter_poster.post_tweet(data.get("msg")) here
        logger.info(f"Simulating Twitter Post: {data.get('msg')[:50]}...")
    else:
        logger.warning(f"Unknown agency action: {action}")

async def agency_loop():
    """Main worker loop."""
    r = _get_redis()
    if not r:
        logger.error("Redis not available. Agency worker shutting down.")
        return
        
    logger.info("🚀 MARKETING AGENCY WORKER v1.0: ONLINE")
    
    while True:
        try:
            # BLPOP blocks until a task is available (efficient)
            # Timeout 10s to allow loop to breathe
            result = r.blpop("queue:marketing", timeout=10)
            if result:
                _, task_json = result
                task = json.loads(task_json)
                await process_task(task)
        except Exception as e:
            logger.error(f"Agency loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(agency_loop())
