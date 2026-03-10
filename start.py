"""
ApexFlash Boot Wrapper — catches ALL errors including import failures.
Sends crash report to admin via Telegram.
"""
import os
import sys
import time
import logging
import traceback

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ApexFlash.start")


def send_crash_report(msg: str):
    """Send crash report to admin via Telegram (sync, no dependencies beyond httpx)."""
    try:
        import httpx
        tok = os.getenv("BOT_TOKEN", "")
        admin = os.getenv("ADMIN_IDS", "").split(",")[0].strip()
        if tok and admin:
            httpx.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": int(admin), "text": msg[:4000]},
                timeout=10,
            )
            logger.info("Crash report sent to admin")
    except Exception as e2:
        logger.error(f"Failed to send crash report: {e2}")


# Pre-startup: clear stale Telegram connections
try:
    import httpx
    tok = os.getenv("BOT_TOKEN", "")
    if tok:
        resp = httpx.post(
            f"https://api.telegram.org/bot{tok}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10,
        )
        logger.info(f"deleteWebhook: {resp.status_code}")
        time.sleep(3)
except Exception as e:
    logger.warning(f"Pre-startup cleanup failed: {e}")

# Now try to import and run the bot
try:
    logger.info("Importing bot module...")
    import bot
    logger.info("Bot module imported OK, starting main()...")
    bot.main()
except Exception as e:
    err = f"\U0001f534 BOT CRASH:\n\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
    logger.error(err)
    send_crash_report(err)
    sys.exit(1)
