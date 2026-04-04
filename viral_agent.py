"""
viral_agent.py — The ApexFlash Viral Growth Engine (v3.15.9)
=========================================================
Automatically transforms real trading wins into social proof.
Drives user acquisition toward the €1,000,000 target.

Logic:
1. Scan persistence for recent wins (>2% PNL).
2. Use Google Gemini to generate 'clickbait' style hooks.
3. Post to ALERT_CHANNEL_ID with deep-linked referral buttons.
"""

import asyncio
import logging
import os
import google.generativeai as genai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from persistence import get_recent_wins, _get_redis
from config import BOT_TOKEN, ALERT_CHANNEL_ID, VERSION, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
from video_agent import generate_viral_infographic
from twitter_poster import post_tweet_with_media

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ViralAgent")

# AI Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

async def generate_viral_hook(trade: dict) -> str:
    """Use Gemini to create a viral hype post from trade data."""
    if not GEMINI_API_KEY:
        # Fallback if no AI key
        return (
            f"🚀 *ANOTHER WIN DETECTED!* 🚀\n\n"
            f"Token: *${trade['token']}*\n"
            f"Profit: *+{trade['pnl_pct']}%*\n\n"
            f"The ApexFlash AI catches the pumps before they happen. "
            f"Join the top 1% now."
        )

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Write a short, professional but hype-filled Telegram post for a crypto trading bot called ApexFlash.\n"
            f"The bot just closed a trade with {trade['pnl_pct']}% profit on token ${trade['token']}.\n"
            f"Focus on: speed, safety, and 'smart money' tracking.\n"
            f"Use emojis. Keep it under 200 characters. End with a strong CTA."
        )
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini viral hook failed: {e}")
        return f"🚀 {trade['pnl_pct']}% GAINS on ${trade['token']}! ApexFlash Godmode is LIVE."

async def viral_poster_job(context):
    """Scan and post high-performing wins periodically (JobQueue compatible)."""
    bot = context.bot
    logger.info("📱 Viral Agent v3.15.9: ACTIVE")
    r = _get_redis()
    
    while True:
        try:
            # 1. Get recent wins
            wins = get_recent_wins(limit=10)
            if not wins:
                await asyncio.sleep(3600) # Wait an hour
                continue

            # 2. Filter for best wins (>3% and not already posted)
            for trade in wins:
                # We need a unique ID for the trade (tx or timestamp+token)
                # For now, let's use a tx hash if available or mock it
                tx_id = trade.get("tx", f"{trade['ts']}_{trade['token']}")
                
                if r and r.sismember("kpi:viral_posted_tx", tx_id):
                    continue
                
                if trade["pnl_pct"] < 3.0:
                    continue

                # 3. Generate Hook
                hook = await generate_viral_hook(trade)
                
                # 4. Format Content
                header = f"🏆 *PROOF OF WIN: +{trade['pnl_pct']}%*"
                footer = f"\n\n🤖 _ApexFlash v{VERSION} — Precision Scalping_"
                text = f"{header}\n\n{hook}{footer}"

                # 5. Buttons (Referral Loop)
                # Note: This uses a generic bot start link. 
                # In production, this would be the affiliate's link or the main bot.
                bot_info = await bot.get_me()
                kb = [
                    [InlineKeyboardButton("⚡ Copy This Alpha", url=f"https://t.me/{bot_info.username}?start=viral_win")],
                    [InlineKeyboardButton("📊 Join Official Channel", url="https://t.me/ApexFlashAlerts")]
                ]

                # 6. Post to Channel
                if ALERT_CHANNEL_ID:
                    try:
                        await bot.send_message(
                            chat_id=ALERT_CHANNEL_ID,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(kb),
                            parse_mode="Markdown"
                        )
                        logger.info(f"Viral post sent for {trade['token']} (+{trade['pnl_pct']}%)")
                        # 7. Visual Alpha (Cycle 13)
                        if trade["pnl_pct"] > 5.0: # Only for big wins
                            media_path = generate_viral_infographic("win", {"token": trade["token"], "pnl": trade["pnl_pct"]})
                            if media_path and os.path.exists(media_path):
                                # Post to Twitter
                                await post_tweet_with_media(
                                    TWITTER_API_KEY, TWITTER_API_SECRET, 
                                    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
                                    f"GODMODE WIN: {trade['pnl_pct']}% on ${trade['token']}! 🚀\nCaptured by #ApexFlash AI. Join us: t.me/ApexFlashBot",
                                    media_path
                                )
                                # Also send to Telegram Admin for "Viral Kit"
                                await bot.send_photo(chat_id=ALERT_CHANNEL_ID, photo=open(media_path, 'rb'), caption=f"📸 *Viral Visual Kit Generated*\nReady for TikTok/Reels/X scaling.", parse_mode="Markdown")

                        # 8. Tracking & Persistence
                        if r: r.sadd("kpi:viral_posted_tx", tx_id)
                        
                        await asyncio.sleep(1200) # Post every 20 min max
                    except Exception as post_err:
                        logger.error(f"Failed to post viral win: {post_err}")
                
                break # Only post one per cycle

        except Exception as e:
            logger.error(f"Viral loop error: {e}")
        
        await asyncio.sleep(3600) # Run check every hour

if __name__ == "__main__":
    # Standard test logic
    import sys
    if "--test" in sys.argv:
        async def run_test():
            test_trade = {"token": "SOL", "pnl_pct": 8.5, "pnl_sol": 0.21, "ts": datetime.now().isoformat()}
            print(f"Testing Hook: {await generate_viral_hook(test_trade)}")
        asyncio.run(run_test())
