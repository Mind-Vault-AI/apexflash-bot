"""
ApexFlash - ULTRA MINIMAL TEST v3.7.6e
NO frameworks. NO telegram library. Just raw HTTP + sleep.
Tests if Render can run ANY Python process.
"""
import os
import sys
import json
import time
import urllib.request

print(f"Python {sys.version}", flush=True)
print(f"Working dir: {os.getcwd()}", flush=True)
print(f"Env vars count: {len(os.environ)}", flush=True)

token = os.getenv("BOT_TOKEN", "")
chat = os.getenv("ALERT_CHANNEL_ID", "")

def send(msg):
    print(f"MSG: {msg}", flush=True)
    if not token or not chat:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat, "text": msg}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"TG send failed: {e}", flush=True)

send(f"🟢 BOT ALIVE on Render!\nPython {sys.version}\nTime: {time.strftime('%H:%M:%S UTC')}")

# Test if telegram library can import
try:
    import telegram
    send(f"✅ telegram lib v{telegram.__version__} OK")
except Exception as e:
    send(f"❌ telegram import FAILED: {e}")

# Test other critical imports
for mod_name in ["aiohttp", "cryptography", "solders", "dotenv"]:
    try:
        __import__(mod_name)
        send(f"✅ {mod_name} OK")
    except Exception as e:
        send(f"❌ {mod_name} FAILED: {e}")

# Report ALL installed package versions
try:
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"],
                          capture_output=True, text=True, timeout=30)
    pkgs = json.loads(result.stdout)
    pkg_lines = [f"{p['name']}=={p['version']}" for p in pkgs]
    # Send in chunks (Telegram 4096 char limit)
    chunk = "📦 INSTALLED PACKAGES:\n"
    for line in pkg_lines:
        if len(chunk) + len(line) > 3900:
            send(chunk)
            chunk = "📦 PACKAGES (cont):\n"
        chunk += line + "\n"
    if chunk:
        send(chunk)
except Exception as e:
    send(f"❌ pip list failed: {e}")

# Test run_polling specifically
send("🧪 Testing run_polling now...")
try:
    from telegram.ext import Application
    bot_token = os.getenv("BOT_TOKEN", "")
    app = Application.builder().token(bot_token).build()

    import asyncio
    async def test_init():
        await app.initialize()
        me = await app.bot.get_me()
        send(f"✅ Bot init OK: @{me.username}")
        await app.shutdown()

    asyncio.run(test_init())
    send("✅ asyncio + telegram init works fine!")
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    send(f"❌ Telegram init FAILED:\n{str(e)[:300]}\n\n{tb[-800:]}")

send("🔄 All tests done. Sleeping forever to stay alive...")

# Keep the process alive — no framework, no polling
counter = 0
while True:
    time.sleep(300)  # 5 min
    counter += 1
    send(f"💓 Still alive! Uptime: {counter * 5} min")
