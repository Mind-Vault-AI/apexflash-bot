"""
ApexFlash MEGA BOT - DIAGNOSTIC v3.7.6g
Catches EXACT error from polling and reports to @ApexFlashAlerts.
"""
import os
import sys
import json
import time
import logging
import traceback
import urllib.request

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger("ApexFlash")

TOKEN = os.getenv("BOT_TOKEN", "")
CHAT = os.getenv("ALERT_CHANNEL_ID", "")


def send(msg):
    """Send diagnostic to channel via raw API."""
    logger.info(f"DIAG: {msg}")
    if not TOKEN or not CHAT:
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": CHAT, "text": msg[:4000]}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


send(f"DIAG v3.7.6g\nPython {sys.version}")

# Step 1: Test imports
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    import telegram
    send(f"Step 1 OK: telegram v{telegram.__version__}")
except Exception as e:
    send(f"CRASH Step 1: {e}\n{traceback.format_exc()[-800:]}")
    sys.exit(1)

# Step 2: Report key package versions
try:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True, text=True, timeout=30,
    )
    pkgs = json.loads(result.stdout)
    pkg_map = {p["name"]: p["version"] for p in pkgs}
    critical = ["python-telegram-bot", "httpx", "httpcore", "h11", "anyio",
                "APScheduler", "aiohttp", "cryptography", "solders", "pytz"]
    lines = [f"  {name}=={pkg_map.get(name, 'N/A')}" for name in critical]
    send("Step 2 packages:\n" + "\n".join(lines))
except Exception as e:
    send(f"Step 2 warn: {e}")

# Step 3: Test basic bot connection
try:
    import asyncio

    async def test_connection():
        app = Application.builder().token(TOKEN).build()
        await app.initialize()
        me = await app.bot.get_me()
        send(f"Step 3 OK: @{me.username} connected")
        await app.shutdown()

    asyncio.run(test_connection())
except Exception as e:
    send(f"CRASH Step 3: {e}\n{traceback.format_exc()[-800:]}")

# Step 4: Test full polling (the part that crashes)
try:
    async def test_polling():
        app = Application.builder().token(TOKEN).build()

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text("Alive! v3.7.6g diagnostic")

        async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id
            await update.message.reply_text(f"Your ID: `{uid}`", parse_mode="Markdown")

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("myid", cmd_myid))

        send("Step 4a: initialize...")
        await app.initialize()
        send("Step 4b: start...")
        await app.start()
        send("Step 4c: start_polling...")
        await app.updater.start_polling(drop_pending_updates=True)
        send("Step 4d: POLLING STARTED! Bot is live!")

        # Stay alive 10 min to confirm stability
        for i in range(120):
            await asyncio.sleep(5)
            if i > 0 and i % 60 == 0:
                send(f"Heartbeat: {i * 5 // 60} min uptime")

        send("10 min uptime OK - bot is STABLE")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

    asyncio.run(test_polling())

except Exception as e:
    tb = traceback.format_exc()
    send(f"CRASH Step 4:\n{str(e)[:500]}\n\nTraceback:\n{tb[-1500:]}")
    logger.error(f"Step 4 crash: {e}", exc_info=True)

send("DIAG DONE - process will exit in 30s")
time.sleep(30)
