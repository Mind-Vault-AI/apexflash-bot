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


def _mask_secrets(text: str) -> str:
    """Remove API keys, tokens, and secrets from error text before logging."""
    import re
    for env_key in ("BOT_TOKEN", "JUPITER_API_KEY", "HELIUS_API_KEY",
                     "ETHERSCAN_API_KEY", "GUMROAD_ACCESS_TOKEN",
                     "WALLET_ENCRYPTION_KEY", "OPENAI_API_KEY"):
        val = os.getenv(env_key, "")
        if val and len(val) > 6:
            text = text.replace(val, f"{env_key}=***")
    text = re.sub(r'api[_-]?key[=:]\s*[A-Za-z0-9_-]{8,}', 'api_key=***', text, flags=re.IGNORECASE)
    return text


def send_crash_report(msg: str):
    """Send crash report to admin via Telegram (sync, no dependencies beyond httpx)."""
    try:
        import httpx
        tok = os.getenv("BOT_TOKEN", "")
        admin = os.getenv("ADMIN_IDS", "").split(",")[0].strip()
        if tok and admin:
            safe_msg = _mask_secrets(msg)
            httpx.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": int(admin), "text": safe_msg[:4000]},
                timeout=10,
            )
            logger.info("Crash report sent to admin")
    except Exception as e2:
        logger.error(f"Failed to send crash report: {e2}")


# ─── Pre-startup: aggressively clear stale Telegram connections ───────────────
try:
    import httpx
    tok = os.getenv("BOT_TOKEN", "")
    if tok:
        # Step 1: Delete any active webhook
        resp = httpx.post(
            f"https://api.telegram.org/bot{tok}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10,
        )
        logger.info(f"deleteWebhook: {resp.status_code} {resp.text[:120]}")

        # Step 2: Close any active getUpdates session
        resp2 = httpx.post(
            f"https://api.telegram.org/bot{tok}/close",
            timeout=10,
        )
        logger.info(f"close session: {resp2.status_code} {resp2.text[:120]}")

        # Step 3: Wait for Telegram to release old polling connections
        # Telegram needs ~7s to time out an old long-poll session
        logger.info("Waiting 10s for Telegram to release old polling connections...")
        time.sleep(10)

        # Step 4: Confirm bot is reachable
        resp3 = httpx.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
        logger.info(f"getMe: {resp3.status_code} — bot identity confirmed")
except Exception as e:
    logger.warning(f"Pre-startup cleanup failed: {e}")

# ─── Now try to import and run the bot ────────────────────────────────────────
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
