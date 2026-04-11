"""
viral_agent.py — The ApexFlash Viral Growth Engine (v3.22.0)
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
from core.persistence import get_recent_wins, _get_redis
from core.config import BOT_TOKEN, ALERT_CHANNEL_ID, VERSION, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
from agents.video_agent import generate_viral_infographic
from agents.twitter_poster import post_tweet_with_media

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ViralAgent")

# AI Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Reddit config (optional — set env vars to enable)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")
REDDIT_ENABLED = all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD])

REDDIT_SUBS = ["Solana", "CryptoMoonShots", "CryptoCurrencyTrading"]
_reddit_last_post_ts = 0.0  # rate-limit: max 1 post per 8 hours


def _post_to_reddit_sync(title: str, body: str, bot_url: str) -> bool:
    """Post to Reddit subreddits. Returns True if posted."""
    global _reddit_last_post_ts
    import time
    if not REDDIT_ENABLED:
        return False
    if time.time() - _reddit_last_post_ts < 28800:  # 8h cooldown
        return False
    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent="ApexFlash Viral Agent v3.22.0",
        )
        sub = reddit.subreddit(REDDIT_SUBS[0])
        sub.submit(title=title, selftext=body)
        _reddit_last_post_ts = time.time()
        logger.info(f"Reddit post submitted to r/{REDDIT_SUBS[0]}: {title[:60]}")
        return True
    except Exception as e:
        logger.warning(f"Reddit post failed: {e}")
        return False


async def post_to_reddit(trade: dict) -> bool:
    """Async wrapper for Reddit posting."""
    bot_url = f"https://t.me/{os.getenv('BOT_USERNAME', 'ApexFlashBot')}?start=ref_{os.getenv('ADMIN_IDS','7851853521').split(',')[0]}"
    title = f"My AI bot just closed +{trade['pnl_pct']}% on ${trade.get('token','SOL')} autonomously — here's the setup"
    body = (
        f"The ApexFlash Zero-Loss Manager just caught a +{trade['pnl_pct']}% move on "
        f"**${trade.get('token', 'SOL')}**.\n\n"
        f"It uses a breakeven lock: after +0.5%, the stop-loss moves to entry price. "
        f"Worst case = zero loss. This trade closed at the 2% take-profit target.\n\n"
        f"Running 24/7 on Solana — Grade A whale signals only.\n\n"
        f"Bot is free: {bot_url}\n\n"
        f"*(Not financial advice — always start small)*"
    )
    return await asyncio.to_thread(_post_to_reddit_sync, title, body, bot_url)

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
        from agents.ai_router import complete
        prompt = (
            f"Write a short, professional but hype-filled Telegram post for a crypto trading bot called ApexFlash.\n"
            f"The bot just closed a trade with {trade['pnl_pct']}% profit on token ${trade['token']}.\n"
            f"Focus on: speed, safety, and 'smart money' tracking.\n"
            f"Use emojis. Keep it under 200 characters. End with a strong CTA."
        )
        text, model_used, err = await complete("MARKETING", prompt)
        return text.strip() if text else f"🚀 {trade['pnl_pct']}% GAINS on ${trade['token']}! ApexFlash Godmode is LIVE."
    except Exception as e:
        logger.error(f"AI Router MARKETING failed: {e}")
        return f"🚀 {trade['pnl_pct']}% GAINS on ${trade['token']}! ApexFlash Godmode is LIVE."

async def viral_poster_job(context):
    """Scan and post high-performing wins periodically (JobQueue compatible)."""
    bot = context.bot
    logger.info("📱 Viral Agent v3.22.0: ACTIVE")
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
                                    f"GODMODE WIN: {trade['pnl_pct']}% on ${trade['token']}! 🚀\nCaptured by #ApexFlash AI. Join us: t.me/apexflash_bot",
                                    media_path
                                )
                                # Also send to Telegram Admin for "Viral Kit"
                                await bot.send_photo(chat_id=ALERT_CHANNEL_ID, photo=open(media_path, 'rb'), caption=f"📸 *Viral Visual Kit Generated*\nReady for TikTok/Reels/X scaling.", parse_mode="Markdown")

                        # 8. Reddit autonomous post (if credentials set)
                        if trade["pnl_pct"] > 3.0:
                            await post_to_reddit(trade)

                        # 9. Tracking & Persistence
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
