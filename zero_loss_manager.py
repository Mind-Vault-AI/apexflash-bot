import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp

from config import (
    ADMIN_IDS, SOL_MINT, 
    AUTONOMOUS_TRADE_AMOUNT_SOL, BREAKEVEN_TRIGGER_PCT, 
    TAKE_PROFIT_PCT, STOP_LOSS_PCT, AUTONOMOUS_COOLDOWN
)
from persistence import load_users
from wallet import load_keypair, get_sol_balance, get_token_balances
from jupiter import get_quote, execute_swap
from scalper import check_scalp_signals, SCALP_TOKENS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] ZERO-LOSS: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ZeroLossManager")

# Active positions tracker
# Format: { token_mint: { "entry_price": float, "amount": float, "sl_price": float, "tp_price": float } }
active_positions = {}
last_trade_ts = {}

async def _notify_admin(bot, text: str) -> None:
    """Send a trade notification to all admins via Telegram."""
    if not bot:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"🛡️ *ZERO-LOSS ALERT*\n{text}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.debug(f"Admin notify failed for {admin_id}: {e}")

async def execute_trade(keypair, action, input_mint, output_mint, amount_raw):
    """Executes a buy/sell securely via Jupiter."""
    quote = await get_quote(input_mint, output_mint, amount_raw, slippage_bps=150)
    if not quote:
        logger.error(f"[{action}] No quote received for {input_mint} -> {output_mint}.")
        return None, 0.0
    
    out_amount = int(quote.get("outAmount", 0))
    if out_amount == 0:
        return None, 0.0

    sig, err = await execute_swap(keypair, quote)
    if sig:
        logger.info(f"[{action}] Swap Success! Signature: {sig}")
        return sig, out_amount
    else:
        logger.error(f"[{action}] Swap Failed: {err}")
        return None, 0.0

_trend_cache: dict = {"pct": 0.0, "ts": 0.0}

async def check_market_trend() -> float:
    """
    Fetches SOL 1-hour price change from DexScreener.
    Returns % change (negative = bearish). Entry skipped if < -5.0%.
    Cached for 5 minutes to avoid rate limits.
    """
    global _trend_cache
    now = time.time()

    if now - _trend_cache["ts"] < 300:
        return _trend_cache["pct"]

    try:
        url = (
            "https://api.dexscreener.com/latest/dex/tokens/"
            "So11111111111111111111111111111111111111112"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    pairs = data.get("pairs") or []
                    sol_pair = next(
                        (p for p in pairs if p.get("quoteToken", {}).get("symbol") == "USDC"),
                        pairs[0] if pairs else None,
                    )
                    if sol_pair:
                        raw = sol_pair.get("priceChange", {}).get("h1")
                        pct = float(raw) if raw is not None else 0.0
                        _trend_cache = {"pct": pct, "ts": now}
                        logger.info(f"SOL 1h trend: {pct:+.2f}%")
                        return pct
    except Exception as e:
        logger.debug(f"check_market_trend error: {e}")

    return _trend_cache["pct"]

async def position_manager(keypair, symbol, mint, bot=None):
    """
    Sub-task: Manages an open position with Breakeven Lock 
    and strict take-profit execution.
    """
    pos = active_positions[symbol]
    logger.info(f"🛡️ POSITION MANAGER STARTED for {symbol}. Entry: ${pos['entry_price']:.6f}")
    
    while symbol in active_positions:
        await asyncio.sleep(10)
        
        # 1. Price Update
        quote = await get_quote(mint, SOL_MINT, pos["amount"])
        if not quote:
            continue
        
        current_amount_sol = int(quote.get("outAmount", 0)) / 1_000_000_000
        original_amount_sol = AUTONOMOUS_TRADE_AMOUNT_SOL
        
        pct_change = ((current_amount_sol - original_amount_sol) / original_amount_sol) * 100
        current_price = pos['entry_price'] * (1 + (pct_change/100))
        
        logger.debug(f"[{symbol}] PNL: {pct_change:+.2f}% | Current: ${current_price:.6f} | SL: ${pos['sl_price']:.6f}")

        # 2. Breakeven Lock (No-Loss enforcement)
        if pct_change >= BREAKEVEN_TRIGGER_PCT and pos['sl_price'] < pos['entry_price']:
            logger.info(f"🔒 BREAKEVEN LOCK TRIGGERED for {symbol}! Risk is now ZERO.")
            pos['sl_price'] = pos['entry_price'] * 1.001 
            await _notify_admin(bot, (
                f"🔒 *BREAKEVEN LOCK* — {symbol}\n"
                f"PNL: {pct_change:+.2f}% | Risk = ZERO"
            ))
        
        # 3. Hard Stop Loss / Hit Breakeven Lock
        if current_price <= pos['sl_price']:
            logger.info(f"🛑 STOP OUT for {symbol} at {pct_change:+.2f}% PNL. Selling...")
            sig, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
            await _notify_admin(bot, (
                f"🛑 *STOP OUT* — {symbol}\n"
                f"PNL: {pct_change:+.2f}%\n"
                f"Tx: `{sig or 'failed'}`"
            ))
            del active_positions[symbol]
            break
            
        # 4. Take Profit
        if pct_change >= TAKE_PROFIT_PCT:
            logger.info(f"💰 TAKE PROFIT for {symbol} at {pct_change:+.2f}% PNL. Selling...")
            sig, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
            if sig:
                 await _notify_admin(bot, (
                    f"💰 *PROFIT TAKEN* — {symbol}\n"
                    f"PNL: *{pct_change:+.2f}%* ✅\n"
                    f"Tx: `{sig}`"
                ))
            del active_positions[symbol]
            break

async def auto_trader_loop(bot=None):
    """Main loop checking for Grade A signals 24/7."""
    logger.info("🚀 ZERO-LOSS AUTONOMOUS SCALPER: BOOTING...")
    
    users = load_users()
    if not ADMIN_IDS:
        logger.error("❌ CRITICAL: No ADMIN_IDS configured in environment! Check your .env file.")
        return

    # Safely get the first admin ID (handles both a single int or a list)
    if isinstance(ADMIN_IDS, list):
        admin_id = ADMIN_IDS[0]
    else:
        admin_id = ADMIN_IDS
    
    admin_user = users.get(str(admin_id)) or users.get(admin_id)
    if not admin_user or not admin_user.get("wallet_secret_enc"):
        logger.error(f"❌ ERROR: Admin wallet not found for user {admin_id}. Use /start in the bot first.")
        return

    keypair = load_keypair(admin_user["wallet_secret_enc"])
    admin_wallet_pub = str(keypair.pubkey())
    logger.info(f"🔑 Loaded Admin Wallet: {admin_wallet_pub}")
    
    while True:
        try:
            # Kaizen: Block NEW signals if administrative pause is active
            from persistence import _get_redis
            r = _get_redis()
            if r and r.get("signals:paused") == "1":
                logger.info("⏸️ Signal Engine PAUSED. Skipping alpha search...")
                await asyncio.sleep(60) 
                continue

            sol_balance = await get_sol_balance(admin_wallet_pub)
            if sol_balance is None or sol_balance < AUTONOMOUS_TRADE_AMOUNT_SOL + 0.01:
                logger.warning(f"⚠️ Low Balance: {sol_balance} SOL. Waiting...")
                await asyncio.sleep(300)
                continue

            signals = await check_scalp_signals()
            for s in signals:
                sym = s['symbol']
                vol = s.get('volume_usd', 0)
                grade = s['grade']
                
                # Zero-Loss Policy Update: Grade A is preferred, but Grade B with $2M+ volume is also high confidence.
                is_high_conf = (grade == "A") or (grade == "B" and vol >= 2_000_000)
                
                if not is_high_conf:
                    logger.debug(f"Skipping {sym} Grade {grade} (Conf: low, Vol: ${vol/1e6:.1f}M)")
                    continue
                
                now = time.time()
                if sym in active_positions:
                    continue
                if (now - last_trade_ts.get(sym, 0) < AUTONOMOUS_COOLDOWN):
                    logger.debug(f"Skipping {sym} (Cooldown active)")
                    continue
                
                # Hedge/Safety Filter
                trend = await check_market_trend()
                if trend < -4.0:
                    logger.warning(f"Market Trend Bearish ({trend}%). Entry skipped for {sym}.")
                    continue

                logger.info(f"⚡ GODMODE SIGNAL TRIGGERED: {sym} Grade {grade} (Vol: ${vol/1e6:.1f}M)")
                mint = SCALP_TOKENS.get(sym)
                amount_lamports = int(AUTONOMOUS_TRADE_AMOUNT_SOL * 1_000_000_000)
                
                sig, out_tokens = await execute_trade(keypair, "BUY", SOL_MINT, mint, amount_lamports)
                
                if sig and out_tokens > 0:
                    active_positions[sym] = {
                        "entry_price": s['price'],
                        "amount": out_tokens,
                        "sl_price": s['price'] * (1 - (STOP_LOSS_PCT/100)),
                        "tp_price": s['price'] * (1 + (TAKE_PROFIT_PCT/100))
                    }
                    last_trade_ts[sym] = time.time()
                    await _notify_admin(bot, (
                        f"⚡ *ZERO-LOSS BUY* — {sym}\n"
                        f"Amt: *{AUTONOMOUS_TRADE_AMOUNT_SOL} SOL*\n"
                        f"Tx: `{sig}`"
                    ))
                    asyncio.create_task(position_manager(keypair, sym, mint, bot=bot))

        except Exception as e:
            logger.error(f"Loop error: {e}")
        
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(auto_trader_loop())
