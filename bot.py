"""
ApexFlash MEGA BOT - MINIMAL TEST v3.7.6d
Tests if the bot can start at all on Render.
No custom module imports — just telegram framework.
"""
import os
import sys
import json
import logging
import urllib.request

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ApexFlash")


def diag(msg):
    """Send diagnostic message to channel."""
    token = os.getenv("BOT_TOKEN", "")
    chat = os.getenv("ALERT_CHANNEL_ID", "")
    print(f"DIAG: {msg}", flush=True)
    if not token or not chat:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat, "text": f"🔧 {msg}"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as ex:
        print(f"DIAG TG fail: {ex}", flush=True)


diag(f"BOOT: Python {sys.version}")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    diag("BOOT: telegram lib imported OK")
except Exception as e:
    diag(f"CRASH: telegram import: {e}")
    raise

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    diag("CRASH: No BOT_TOKEN!")
    sys.exit(1)

diag(f"BOOT: BOT_TOKEN present (len={len(BOT_TOKEN)})")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "✅ ApexFlash ALIVE! v3.7.6d (minimal test)\n"
        "Full bot features temporarily disabled for diagnostics."
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    await update.message.reply_text(f"Your Telegram ID: `{uid}`", parse_mode="Markdown")


def main():
    diag("MAIN: Building application...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))

    diag("MAIN: Starting polling...")
    logger.info("⚡ ApexFlash MINIMAL TEST v3.7.6d starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        diag(f"FATAL CRASH:\n{str(e)[:300]}\n\n{tb[-500:]}")
        logging.error(f"FATAL: {e}", exc_info=True)
        raise
