import asyncio
import logging
import time
from datetime import datetime, timezone

from config import ADMIN_IDS, SOL_MINT
from persistence import load_users
from wallet import load_keypair, get_sol_balance, get_token_balances
from jupiter import get_quote, execute_swap
from scalper import check_scalp_signals, SCALP_TOKENS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] ZERO-LOSS: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ZeroLossManager")

TRADE_AMOUNT_SOL = 0.05
BREAKEVEN_TRIGGER_PCT = 0.5  # When up 0.5%, lock stop-loss at breakeven
TAKE_PROFIT_PCT = 2.0        # Sell completely at 2.0% profit
STOP_LOSS_PCT = 1.0          # Initial hard stop loss at 1.0%
TRADE_COOLDOWN = 300         # 5 minutes cooldown per token

# Active positions tracker
# Format: { token_mint: { "entry_price": float, "amount": float, "sl_price": float, "tp_price": float } }
active_positions = {}
last_trade_ts = {}

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

async def position_manager(keypair, symbol, mint):
    """
    Sub-task: Manages an open position with Breakeven Lock 
    and strict take-profit execution.
    """
    pos = active_positions[symbol]
    logger.info(f"🛡️ POSITION MANAGER STARTED for {symbol}. Entry: ${pos['entry_price']:.6f}")
    
    while symbol in active_positions:
        await asyncio.sleep(5)
        # Fetch current price via Jupiter quote (1 token)
        quote = await get_quote(mint, SOL_MINT, pos["amount"]) # get equivalent in SOL
        if not quote:
            continue
        
        current_amount_sol = int(quote.get("outAmount", 0)) / 1_000_000_000
        original_amount_sol = TRADE_AMOUNT_SOL
        
        pct_change = ((current_amount_sol - original_amount_sol) / original_amount_sol) * 100
        current_price = pos['entry_price'] * (1 + (pct_change/100))
        
        logger.debug(f"[{symbol}] PNL: {pct_change:+.2f}% | Current: ${current_price:.6f} | SL: ${pos['sl_price']:.6f}")

        # 1. Breakeven Lock (No-Loss enforcement)
        if pct_change >= BREAKEVEN_TRIGGER_PCT and pos['sl_price'] < pos['entry_price']:
            logger.info(f"🔒 BREAKEVEN LOCK TRIGGERED for {symbol}! Risk is now ZERO.")
            pos['sl_price'] = pos['entry_price'] * 1.001  # Lock slightly above entry to cover fees
        
        # 2. Hard Stop Loss / Hit Breakeven Lock
        if current_price <= pos['sl_price']:
            logger.info(f"🛑 STOP OUT for {symbol} at {pct_change:+.2f}% PNL. Selling...")
            await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
            del active_positions[symbol]
            break
            
        # 3. Take Profit
        if pct_change >= TAKE_PROFIT_PCT:
            logger.info(f"💰 TAKE PROFIT for {symbol} at {pct_change:+.2f}% PNL. Selling...")
            await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
            del active_positions[symbol]
            break

async def auto_trader_loop():
    """Main loop checking for Grade A signals 24/7."""
    logger.info("🚀 ZERO-LOSS AUTONOMOUS SCALPER: BOOTING...")
    
    users = load_users()
    admin_id = int(str(ADMIN_IDS).split(',')[0].strip('[]')) if isinstance(ADMIN_IDS, list) else int(ADMIN_IDS)
    
    admin_user = users.get(str(admin_id)) or users.get(admin_id)
    if not admin_user or not admin_user.get("wallet_secret_enc"):
        logger.error(f"Admin wallet not found for ID {admin_id}. Please start the bot first and generate a wallet.")
        return

    keypair = load_keypair(admin_user["wallet_secret_enc"])
    admin_wallet_pub = str(keypair.pubkey())
    logger.info(f"🔑 Loaded Admin Wallet: {admin_wallet_pub}")
    
    sol_balance = await get_sol_balance(admin_wallet_pub)
    if sol_balance is None or sol_balance < TRADE_AMOUNT_SOL + 0.01:
        logger.warning(f"⚠️ Insufficient SOL for auto-trading. Balance: {sol_balance} SOL. Need {TRADE_AMOUNT_SOL + 0.01} SOL.")
        logger.warning("Waiting for funds...")
    
    while True:
        try:
            signals = await check_scalp_signals()
            for s in signals:
                sym = s['symbol']
                # Only take Grade A strong momentum plays
                if s['grade'] != "A": 
                    continue
                
                # Check cooldown and max positions
                now = time.time()
                if sym in active_positions or (now - last_trade_ts.get(sym, 0) < TRADE_COOLDOWN):
                    continue
                
                logger.info(f"⚡ GRADE A SIGNAL DETECTED: {sym} (5m: {s['pct_5m']:+.2f}%)")
                if sol_balance is not None and sol_balance > (TRADE_AMOUNT_SOL + 0.01):
                    # EXECUTE BUY
                    mint = SCALP_TOKENS.get(sym)
                    amount_lamports = int(TRADE_AMOUNT_SOL * 1_000_000_000)
                    
                    sig, out_tokens = await execute_trade(keypair, "BUY", SOL_MINT, mint, amount_lamports)
                    
                    if sig and out_tokens > 0:
                        active_positions[sym] = {
                            "entry_price": s['price'],
                            "amount": out_tokens,
                            "sl_price": s['price'] * (1 - (STOP_LOSS_PCT/100)),
                            "tp_price": s['price'] * (1 + (TAKE_PROFIT_PCT/100))
                        }
                        last_trade_ts[sym] = time.time()
                        # Spawn background position manager
                        asyncio.create_task(position_manager(keypair, sym, mint))
                else:
                    logger.debug(f"Skipping {sym} - Insufficient balance ({sol_balance} SOL)")

        except Exception as e:
            logger.error(f"Loop error: {e}")
        
        await asyncio.sleep(30) # Check every 30s

if __name__ == "__main__":
    asyncio.run(auto_trader_loop())
