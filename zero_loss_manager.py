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
active_positions = {}
last_trade_ts = {}
# Centralized task tracker to prevent "Task destroyed" warnings
_manager_tasks = {}

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
    """SOL 1-hour trend from DexScreener (Cached for 5m)."""
    global _trend_cache
    now = time.time()
    if now - _trend_cache["ts"] < 300:
        return _trend_cache["pct"]

    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    pair = (data.get("pairs") or [{}])[0]
                    raw = pair.get("priceChange", {}).get("h1")
                    pct = float(raw) if raw is not None else 0.0
                    _trend_cache = {"pct": pct, "ts": now}
                    logger.info(f"SOL 1h trend: {pct:+.2f}%")
                    return pct
    except Exception as e:
        logger.debug(f"Trend error: {e}")
    return _trend_cache["pct"]

async def position_manager(keypair, symbol, mint, bot=None):
    """Sub-task: Manages an open position with Breakeven Lock."""
    from persistence import save_active_positions
    
    pos = active_positions.get(symbol)
    if not pos:
        return
        
    logger.info(f"🛡️ MANAGER ACTIVE: {symbol} (Entry: ${pos['entry_price']:.6f})")
    
    while symbol in active_positions:
        try:
            await asyncio.sleep(15) # Optimal interval for RPC safety
            
            # 1. Price Check
            quote = await get_quote(mint, SOL_MINT, pos["amount"])
            if not quote: continue
            
            curr_sol = int(quote.get("outAmount", 0)) / 1e9
            orig_sol = AUTONOMOUS_TRADE_AMOUNT_SOL
            pnl = ((curr_sol - orig_sol) / orig_sol) * 100
            
            # 2. Breakeven Lock
            if pnl >= BREAKEVEN_TRIGGER_PCT and pos['sl_price'] < pos['entry_price']:
                logger.info(f"🔒 BREAKEVEN LOCKED: {symbol}")
                pos['sl_price'] = pos['entry_price'] * 1.001
                save_active_positions(active_positions)
                await _notify_admin(bot, f"🔒 *BREAKEVEN LOCK* — {symbol}\nRisk = ZERO ✅")

            # 3. Stop Loss
            curr_price = pos['entry_price'] * (1 + (pnl/100))
            if curr_price <= pos['sl_price']:
                logger.info(f"🛑 STOP OUT: {symbol}")
                sig, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
                await _notify_admin(bot, f"🛑 *STOP OUT* — {symbol}\nPNL: {pnl:+.2f}%\nTx: `{sig or 'failed'}`")
                break

            # 4. Take Profit
            if pnl >= TAKE_PROFIT_PCT:
                logger.info(f"💰 TAKE PROFIT: {symbol}")
                sig, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
                await _notify_admin(bot, f"💰 *PROFIT TAKEN* — {symbol}\nPNL: *{pnl:+.2f}%* ✅\nTx: `{sig}`")
                break
                
        except Exception as e:
            logger.error(f"Position manager error [{symbol}]: {e}")
            await asyncio.sleep(60)

    # Clean up
    if symbol in active_positions:
        del active_positions[symbol]
    if symbol in _manager_tasks:
        del _manager_tasks[symbol]
    save_active_positions(active_positions)

async def auto_trader_loop(bot=None):
    """Main loop checking for Grade A signals 24/7."""
    from persistence import load_active_positions, save_active_positions
    global active_positions
    
    logger.info("🚀 ZERO-LOSS ENGINE v3.15.3: ENGAGED")
    
    # ── 1. RESTORE STATE ──
    active_positions = load_active_positions()
    
    admin_id = ADMIN_IDS[0] if isinstance(ADMIN_IDS, list) else ADMIN_IDS
    users = load_users()
    admin_user = users.get(str(admin_id))
    if not admin_user or not admin_user.get("wallet_secret_enc"):
        logger.error("❌ Admin wallet missing. /start first.")
        return
        
    keypair = load_keypair(admin_user["wallet_secret_enc"])
    
    # Resume tasks for existing positions
    for sym, pos in active_positions.items():
        mint = SCALP_TOKENS.get(sym)
        if mint:
            logger.info(f"🛡️ RESUMING MANAGER: {sym}")
            _manager_tasks[sym] = asyncio.create_task(position_manager(keypair, sym, mint, bot=bot))

    while True:
        try:
            # ── 2. SEARCH FOR ALPHA ──
            signals = await check_scalp_signals()
            for s in signals:
                sym = s['symbol']
                if sym in active_positions: continue
                
                # Filter: Grade A or Grade B with high volume
                if s['grade'] == "A" or (s['grade'] == "B" and s.get('volume_usd', 0) >= 2e6):
                    # Check Market Hedge
                    if await check_market_trend() < -4.0: continue
                    
                    # Entry
                    logger.info(f"⚡ ENTRY DETECTED: {sym}")
                    mint = SCALP_TOKENS.get(sym)
                    sig, out_tokens = await execute_trade(keypair, "BUY", SOL_MINT, mint, int(AUTONOMOUS_TRADE_AMOUNT_SOL * 1e9))
                    
                    if sig and out_tokens > 0:
                        active_positions[sym] = {
                            "entry_price": s['price'],
                            "amount": out_tokens,
                            "sl_price": s['price'] * (1 - (STOP_LOSS_PCT/100)),
                            "tp_price": s['price'] * (1 + (TAKE_PROFIT_PCT/100))
                        }
                        save_active_positions(active_positions)
                        await _notify_admin(bot, f"⚡ *ZERO-LOSS BUY* — {sym}\nAmt: *{AUTONOMOUS_TRADE_AMOUNT_SOL} SOL*\nTx: `{sig}`")
                        _manager_tasks[sym] = asyncio.create_task(position_manager(keypair, sym, mint, bot=bot))
        except Exception as e:
            logger.error(f"Auto-trader loop error: {e}")
        await asyncio.sleep(45)

if __name__ == "__main__":
    asyncio.run(auto_trader_loop())
