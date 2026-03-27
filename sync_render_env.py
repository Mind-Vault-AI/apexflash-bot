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
    # SESSION 23 AUDIT — alle verdwaalde keys gevonden en gecentraliseerd (27-03-2026)
    extra_keys = {
        # Wallets
        "FEE_COLLECT_WALLET": "4LKQGKyjhCpVm7TAnDRtR5dPNExEhSADNCumvZjiuYWi",  # HOT wallet
        "PHANTOM_WALLET_MVAI": "3zSWHK9NZdSd6fcAy6AK4VyVrwuKERo27B26Dk5yEEnX",  # @MVAIphantomP1
        # Affiliate ref codes
        "GATE_REF": "VFFHXVFDUG",
        "BITUNIX_REF": "xc6jzk",
        "MEXC_REF": "BPM0e8Rm",
        "BLOFIN_REF": "b996a0111c1b4497b53d9b3cc82e4539",
        # AI / LLM keys
        "GEMINI_API_KEY": "AIzaSyAtG0vWvL91DmYEZxG42fELXyPZms29HHI",
        "DEEPSEEK_API_KEY": "sk-e8d8d36841c340409f10ec61dc23eb84",
        "NEBIUS_API_KEY": "v1.CmQKHHN0YXRpY2tleS1lMDByaDlneDZlNWtheXBjMzISIXNlcnZpY2VhY2NvdW50LWUwMGIyZWUzdzdhMHczbnExdDIMCIWKls4GEJWA4q0COgwIhY2umQcQwPqmvQFAAloDZTAw.AAAAAAAAAAHJdVt_9i-e7TBnmnWZd_uDaigARH4gk6s2YuNVXpdP9gBRQ3HRjFWfIxdXI8v1e6h_5MOPBzgf3xnonV8KjzYF",
        # Discord
        "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1486870373684482219/Fauj_qcE21v0ET1CLQWbJtY51LJniY_gj7WDRLRn3PhIIZkv8wVtaBnNxfubIERzka5E",
        "DISCORD_TRADE_WEBHOOK_URL": "https://discord.com/api/webhooks/1486870373684482219/Fauj_qcE21v0ET1CLQWbJtY51LJniY_gj7WDRLRn3PhIIZkv8wVtaBnNxfubIERzka5E",
        # News / War Watch
        "NEWSAPI_KEY": "e46681a31870410fbc7413806a291acf",
        "CRYPTOPANIC_KEY": "90ff9f69c0127be870180348125c7e71293d3bd9",
        # DEX / Trading APIs
        "JUPITER_API_KEY": "42213fab-4b29-4ef2-a7e4-76b12a0276ff",  # Jupiter Solana DEX
        "BITUNIX_API_KEY": "7a7d1dbaa93de7e85dd2635228b2bbdd",
        "BITUNIX_SECRET_KEY": "fbc58430cb33733f1ea812d9b8177b39",
        "BLOFIN_API_KEY": "98f253cc41e24b468873bb9ef4edae59",
        "MIZAR_API_KEY": "798a0ea2-76b3-4d95-8904-c385d44e773e",
        "MIZAR_REF": "apexflash",  # Mizar referral slug → https://mizar.com/?ref=apexflash
        "MIZAR_REFERRAL_URL": "https://mizar.com/?ref=apexflash",
        # Gumroad (store)
        "GUMROAD_APP_ID": "s68lufD3NS4NsIXmjKgAoQkULPNfYplXk7zy0eZZC5s",
        "GUMROAD_APP_SECRET": "pMRriaBhp7lUXoYwC8b56DF013-BIaIRLj7Zy21VymU",
        "GUMROAD_ACCESS_TOKEN": "t_ot7v0emChcYXE5bsFvbJJFSBx_zskCgRPJqOiAssU",
        # Twitter/X (@MindVault_ai) — marketing auto-poster (3x/day)
        "TWITTER_API_KEY": "Wh3tVhy2uYRMIkut3cTeWpSA6",
        "TWITTER_API_SECRET": "AxSOR42545YdqTmz4YxOUoFZCWtXECJpHrH1UPl5389kBjt1h4",
        "TWITTER_ACCESS_TOKEN": "1959652751140388864-cADqHeQAHBijTyeHIp02TsAnhed7kH",
        "TWITTER_ACCESS_SECRET": "W1WBiwXXHOqiapDkmG62cgFlz3aEFqxShifPLjpC23lBW",
        "TWITTER_ENABLED": "true",
        # OKX
        "OKX_PASSPHRASE": "OkX_ApI=13!",
        "OKX_ACCOUNT_ID": "797696059626980898",
        # Safety cap for test trades (0 = disabled in production, set >0 to cap all buys)
        "TEST_TRADE_SOL": "0.001",
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
