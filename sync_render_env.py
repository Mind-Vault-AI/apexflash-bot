#!/usr/bin/env python3
"""
Sync ALL env vars from MASTER_ENV to Render.
Run this INSTEAD of manual Render env var edits.

Usage: python sync_render_env.py

This script reads MASTER_ENV_APEXFLASH.txt from Box Drive
and PUTs ALL keys to Render. No keys can be lost.
"""
import json
import os
import urllib.request

RENDER_API_KEY = os.getenv("RENDER_API_KEY", "rnd_F6SnsNvz5CKtds7WZ3EGwp9xlDGZ")
SERVICE_ID = "srv-d6kcjbpaae7s73aadsu0"
API = f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars"
HDR = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Master env file location (Box Drive)
MASTER_FILE = os.path.expanduser("~/Box/MEGA BOT/MASTER_ENV_APEXFLASH.txt")


def load_master_env(path: str) -> dict[str, str]:
    """Parse KEY=VALUE from master env file, skip comments and blanks."""
    env = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and key != "PYTHON_VERSION":  # Render uses .python-version file
                    env[key] = value
    return env


def sync():
    # Load master
    if not os.path.exists(MASTER_FILE):
        print(f"ERROR: Master file not found: {MASTER_FILE}")
        return

    master = load_master_env(MASTER_FILE)
    print(f"Master: {len(master)} keys loaded from {MASTER_FILE}")

    # Add keys that are in memory but not in Box Drive master
    extra_keys = {
        "FEE_COLLECT_WALLET": "4LKQGKyjhCpVm7TAnDRtR5dPNExEhSADNCumvZjiuYWi",
        "GATE_REF": "VFFHXVFDUG",
        "GEMINI_API_KEY": "AIzaSyAtG0vWvL91DmYEZxG42fELXyPZms29HHI",
        "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1486870373684482219/Fauj_qcE21v0ET1CLQWbJtY51LJniY_gj7WDRLRn3PhIIZkv8wVtaBnNxfubIERzka5E",
        "DISCORD_TRADE_WEBHOOK_URL": "https://discord.com/api/webhooks/1486870373684482219/Fauj_qcE21v0ET1CLQWbJtY51LJniY_gj7WDRLRn3PhIIZkv8wVtaBnNxfubIERzka5E",
    }
    for k, v in extra_keys.items():
        if k not in master:
            master[k] = v
            print(f"  Added from memory: {k}")

    # Updated prices (sessie 16+)
    master["PRO_PRICE_SOL"] = "0.07"      # $9.99 at SOL=$142
    master["ELITE_PRICE_SOL"] = "0.21"    # $29.99 at SOL=$142

    # PUT to Render
    payload = json.dumps([{"key": k, "value": v} for k, v in master.items()]).encode()
    req = urllib.request.Request(API, data=payload, headers=HDR, method="PUT")
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    print(f"Render PUT: {len(result)} keys written")

    # Verify
    req2 = urllib.request.Request(API, headers=HDR)
    with urllib.request.urlopen(req2) as r2:
        verify = json.loads(r2.read())
    visible = [e.get("envVar", e)["key"] for e in verify]
    print(f"Visible: {len(visible)} (secret keys hidden by Render API)")
    print(f"Total synced: {len(master)} keys")
    print("DONE")


if __name__ == "__main__":
    sync()
