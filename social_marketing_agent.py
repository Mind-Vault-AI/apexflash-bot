"""
Omni-Asset Viral Loop Agent (Phase 3)
-------------------------------------
Doel: Genereer en distribueer autonome "Proof of Win" marketing.
- Reddit: Post automatisch je geslaagde trades op PRAW (r/Solana, r/CryptoMoonShots).
- TikTok: Genereert een hapklaar video-script met hooks, hashtags en Call-to-Actions voor de CEO.

Usage: 
  python social_marketing_agent.py --reddit
  python social_marketing_agent.py --tiktok "SOL" "312%"
"""

import argparse
import sys
import random
from datetime import datetime
from config import AFFILIATE_LINKS, ADMIN_IDS

# Dummy Trade History (to be replaced with live persistence db hook)
MOCK_RECENT_TRADES = [
    {"asset": "OIL_PERPS", "roi": "A+$478 SOL", "time": "2 Hours ago", "proof_link": "https://mexc.com"},
    {"asset": "RENDER", "roi": "+12%", "time": "30 Mins ago", "proof_link": "https://solscan.io"}
]

REDDIT_SUBS = ["CryptoMoonShots", "Solana", "CryptoCurrencyTrading", "Daytrading"]

def generate_reddit_post(asset: str, roi: str):
    """Berekent een Reddit titel en post body volgeladen met Affiliate en bewijs."""
    ref_id = ADMIN_IDS[0] if ADMIN_IDS else "7851853521"
    bot_url = f"https://t.me/ApexFlashBot?start=ref_{ref_id}"
    
    titles = [
        f"Just automated {roi} profit on {asset} purely based on Geopolitics. Set and forget. 🤖",
        f"Why I stopped trading {asset} manually. My AI agent just hit {roi} using War Watch API.",
        f"My autonomous Solana bot caught the {asset} volatility... {roi} locked in. ZERO losses."
    ]
    
    body = f"""
Hey guys, I wanted to share the exact setup I'm using to escape the manual trading grind. 

Today my "War Watch" AI agent detected a massive momentum shift on **{asset}** and immediately executed a buy order. 
It utilizes a built-in *Breakeven Lock* — the moment I was up 0.5%, risk was completely eliminated. The trade eventually closed at **{roi}**.

**The Setup:**
1. Omni-Asset scanning (Oil, Gold, Chips, Drones, Solana memecoins)
2. Jupiter v6 aggregator for best routing
3. 24/7 background execution

I'm using the ApexFlash AI. You don't even have to understand coding, just plug in your wallet and click start.
It has 1-Tap trading integrated.

👉 Check it out and run it yourself: [ApexFlash Autonomous Bot]({bot_url})

*(Not financial advice, always test with small bags first. But seriously, manual trading is dead).*
    """
    return random.choice(titles), body

def post_to_reddit(asset: str, roi: str):
    """
    Connects to Reddit via PRAW and posts to subreddits. 
    (Requires Reddit API keys in .env, mocking for now to prevent spam during setup).
    """
    title, body = generate_reddit_post(asset, roi)
    print("="*60)
    print("🚀 REDDIT VIRAL LOOP: INITIATING POST...")
    print(f"Targeting subreddits: {', '.join(REDDIT_SUBS[:2])}")
    print("="*60)
    print(f"TITLE: {title}")
    print(f"BODY:\n{body}")
    print("="*60)
    print("✅ Post (simulated) distributed successfully. Awaiting inbound leads.")

def generate_tiktok_script(asset: str, roi: str):
    """Genereert een TikTok script voor de CEO om binnen 30 sec op te nemen."""
    ref_id = ADMIN_IDS[0] if ADMIN_IDS else "7851853521"
    
    script = f"""
📱 TIKTOK VIRAL SCRIPT PUSH 📱
Geef deze tekst aan de CEO. 

📌 Text on Screen: 
"Hoe ik {roi} verdiende op {asset} terwijl ik sliep 🤯 AI Trading"

🎵 Sound Suggestion: Trending 'Sigma Grindset' of 'Cyberpunk EDM'

🗣️ Spoken Script (Snel, energiek, 15 seconden!):
"Stop met handmatig traden. Alles wat je doet is te traag.
Kijk naar deze trade op {asset}. Exact {roi} winst. 
Heb ik uren naar een grafiek gekeken? Nee. 
Mijn AI Bot scant 24/7 het wereldnieuws, koopt in 1 milliseconde, en zet automatisch een Breakeven Lock aan.
Zodra de trade 0.5% in de plus staat, draai je RISICOLOOS.
De bot is live. Klik op de link in m'n bio en start met je eerste 5 cent."

🔗 Bio Call to Action: "Start de AI Bot Nu: https://t.me/ApexFlashBot?start=ref_{ref_id}"
#TradingBot #CryptoAI #Solana #{asset.replace('_', '')} #Daytrading
"""
    print(script)

def main():
    parser = argparse.ArgumentParser(description="ApexFlash Social Viral Engine")
    parser.add_argument('--reddit', action='store_true', help="Auto-post to Reddit subs")
    parser.add_argument('--tiktok', nargs=2, metavar=('ASSET', 'ROI'), help="Generate TikTok script for Asset + ROI")
    args = parser.parse_args()

    if args.reddit:
        # Pakt de best presterende laaste trade
        trade = MOCK_RECENT_TRADES[0]
        post_to_reddit(trade['asset'], trade['roi'])
    elif args.tiktok:
        generate_tiktok_script(args.tiktok[0], args.tiktok[1])
    else:
        print("Mislukt: Gebruik --reddit of --tiktok ASSET ROI")

if __name__ == "__main__":
    main()
