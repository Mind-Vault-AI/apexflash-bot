"""Zero-loss autonomous trading loop and position management."""

import asyncio
import logging
import time
from datetime import datetime, timezone

try:
    import aiohttp
except ImportError:
    aiohttp = None

from core.config import (
    ADMIN_IDS,
    SOL_MINT,
    AUTONOMOUS_TRADE_AMOUNT_SOL,
    BREAKEVEN_TRIGGER_PCT,
    TAKE_PROFIT_PCT,
    STOP_LOSS_PCT,
    MIN_SOL_RESERVE,
    MAX_TRADE_SOL,
    MAX_DAILY_TRADES,
    GMGN_WALLET_ADDRESS,
)
from core.persistence import (
    load_users,
    record_trade_result,
    get_governance_config,
    get_market_panic_score,
    _get_redis,
    load_active_positions,
    save_active_positions,
)
from core.wallet import load_keypair, get_sol_balance
from exchanges.jupiter import get_quote, execute_swap
from exchanges import gmgn as _gmgn
from exchanges import gmgn_market as _gmgn_market
from scalper import check_scalp_signals, SCALP_TOKENS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] ZERO-LOSS: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ZeroLossManager")

# Active positions tracker
active_positions = {}
# Centralized task tracker to prevent "Task destroyed" warnings
_manager_tasks = {}
AUTOTRADE_STATE = {
    "last_cycle_ts": "-",
    "signals_scanned": 0,
    "candidates": 0,
    "skipped_panic": 0,
    "skipped_selectivity": 0,
    "skipped_trend": 0,
    "skipped_balance": 0,
    "last_entry_symbol": "-",
    "last_entry_ts": "-",
    "last_reason": "-",
    "last_entry_error": "-",
    "no_signal_cycles": 0,
}


def _get_autotrade_test_cap_sol() -> float:
    """Runtime test cap from Redis. 0 means disabled."""
    try:
        r = _get_redis()
        if not r:
            return 0.0
        raw = r.get("apexflash:autotrade:test_cap_sol")
        return max(0.0, float(raw or 0.0))
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _is_autotrade_enabled() -> bool:
    """Runtime toggle for autonomous entries. Defaults to enabled."""
    try:
        r = _get_redis()
        if not r:
            return True
        raw = str(r.get("apexflash:autotrade:enabled") or "1").strip().lower()
        return raw not in ("0", "false", "off", "no")
    except (TypeError, ValueError, AttributeError):
        return True


def _enforce_risk_limits(admin_id: int, trade_amount_sol: float, _symbol: str) -> tuple[bool, str]:
    """
    Check if trade respects risk limits.
    Returns: (allowed: bool, reason: str)
    """
    # 1. Max single trade check
    if trade_amount_sol > MAX_TRADE_SOL:
        return False, f"exceeds_max_single_trade ({trade_amount_sol} > {MAX_TRADE_SOL})"

    # 2. Daily trade limit check (graceful fallback if function missing)
    try:
        from core.persistence import get_daily_trade_count
        daily_count = get_daily_trade_count(admin_id)
        if daily_count >= MAX_DAILY_TRADES:
            return False, f"daily_trade_limit_reached ({daily_count} >= {MAX_DAILY_TRADES})"
    except (ImportError, AttributeError):
        pass  # Fallback: allow trade if function unavailable

    # 3. Check drawdown (via panic score as proxy)
    panic = get_market_panic_score()
    if panic >= 85:
        return False, f"market_panic_too_high ({panic})"

    return True, "pass"


def _resolve_mint(symbol: str) -> str:
    """Resolve symbol -> mint across flat or chain-grouped SCALP_TOKENS structures."""
    try:
        raw = SCALP_TOKENS.get(symbol)
        if isinstance(raw, str) and raw:
            return raw
        for _chain, tokens in SCALP_TOKENS.items():
            if isinstance(tokens, dict) and symbol in tokens:
                return str(tokens[symbol])
    except (AttributeError, TypeError):
        pass
    return ""

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
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Admin notify failed for %s: %s", admin_id, e)

async def execute_trade(keypair, action, input_mint, output_mint, amount_raw):
    """Executes a buy/sell via Jupiter (primary) → GMGN (fallback).

    v3.23.19: SELL paths use escalating slippage (3% → 10% → 25%) — memecoins
    have thin liquidity and a fixed low slippage causes silent SL failures.
    BUY paths keep tight slippage (1.5%) to protect entry price.
    """
    # ── Primary: Jupiter ──────────────────────────────────────────────────────
    is_sell = (action or "").lower().startswith("sell") or output_mint.endswith("So11111111111111111111111111111111111111112")
    if is_sell:
        from exchanges.jupiter import get_quote_with_escalation
        quote, _reason = await get_quote_with_escalation(
            input_mint, output_mint, amount_raw,
            slippage_steps=(300, 1000, 2500),
        )
    else:
        quote = await get_quote(input_mint, output_mint, amount_raw, slippage_bps=150)
    if quote:
        out_amount = int(quote.get("outAmount", 0))
        if out_amount > 0:
            sig, err = await execute_swap(keypair, quote)
            if sig:
                slip_info = f" (slip={quote.get('_slippage_used', 'n/a')}bps)" if is_sell else ""
                logger.info("[%s] Jupiter swap OK%s: %s", action, slip_info, sig)
                return sig, out_amount, ""
            logger.warning("[%s] Jupiter failed: %s - trying GMGN fallback", action, err)
        else:
            logger.warning("[%s] Jupiter zero outAmount - trying GMGN fallback", action)
    else:
        logger.warning("[%s] Jupiter no quote - trying GMGN fallback", action)

    # ── Fallback: GMGN ────────────────────────────────────────────────────────
    if _gmgn.is_configured():
        try:
            from_addr = GMGN_WALLET_ADDRESS
            if not from_addr:
                logger.warning("[%s] GMGN_WALLET_ADDRESS not set - skip GMGN", action)
                return None, 0.0, "gmgn_wallet_not_set"
            loop = asyncio.get_event_loop()
            order = await loop.run_in_executor(
                None,
                lambda: _gmgn.swap(
                    from_address=from_addr,
                    input_token=input_mint,
                    output_token=output_mint,
                    input_amount=str(amount_raw),
                    slippage=0.05,
                    chain="sol",
                    is_anti_mev=True,
                ),
            )
            order_id = order.get("order_id", "")
            status = order.get("status", "unknown")
            tx_hash = order.get("hash", "")
            if status in ("pending", "processed", "confirmed"):
                logger.info("[%s] GMGN swap OK: order=%s status=%s", action, order_id, status)
                # Poll until confirmed (max 45s)
                await loop.run_in_executor(
                    None,
                    lambda: _gmgn.wait_for_confirmation(order_id, "sol", timeout_sec=45),
                )
                return tx_hash or order_id, 0, ""
            else:
                logger.error("[%s] GMGN swap rejected: %s", action, order)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[%s] GMGN fallback error: %s", action, e)

    return None, 0.0, "both_jupiter_and_gmgn_failed"

async def security_audit(mint: str) -> bool:
    """
    Pre-buy rug-guard (v3.23.20).

    BLOCKS the BUY (returns False) if any active failure:
      1. DexScreener has no pair       → no market exists
      2. liquidity_usd < $10,000       → thin pool / rug-prone
      3. top-10 holders own > 70%      → concentrated dump risk
      4. Jupiter cannot quote a SELL   → honeypot suspected

    Fails-OPEN (returns True) on API errors / not-configured —
    we don't want Jupiter or GMGN downtime to freeze all trading.
    """
    short = (mint or "?")[:8]
    try:
        logger.info("🛡️ RUG-GUARD: Auditing %s...", short)

        # ── 1. DexScreener: market existence + liquidity floor ──────────────
        if aiohttp is not None:
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=6)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            pairs = data.get("pairs") or []
                            if not pairs:
                                logger.error(
                                    "🚨 RUG-GUARD: %s — no DexScreener pair (no market)",
                                    short,
                                )
                                return False
                            best = max(
                                pairs,
                                key=lambda p: float(
                                    ((p or {}).get("liquidity") or {}).get("usd") or 0
                                ),
                            )
                            liq_usd = float(
                                (best.get("liquidity") or {}).get("usd") or 0
                            )
                            if liq_usd < 10_000:
                                logger.error(
                                    "🚨 RUG-GUARD: %s — liquidity $%.0f below $10k floor",
                                    short, liq_usd,
                                )
                                return False
                            logger.info(
                                "🛡️ RUG-GUARD: %s liquidity $%.0f ✅", short, liq_usd
                            )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "RUG-GUARD: dexscreener probe failed for %s: %s — fail-open",
                    short, e,
                )

        # ── 2. GMGN top-10 holder concentration ────────────────────────────
        try:
            holders = await asyncio.to_thread(
                _gmgn_market.top_holders, mint, "sol", 10
            )
            if holders:
                total_pct = 0.0
                for h in holders:
                    raw = (
                        h.get("amount_percentage")
                        or h.get("amount_percent")
                        or h.get("percentage")
                        or h.get("percent")
                        or 0
                    )
                    try:
                        total_pct += float(raw)
                    except (TypeError, ValueError):
                        pass
                # GMGN may return 0..1 fraction or 0..100 percent — normalize
                if 0 < total_pct <= 1.5:
                    total_pct *= 100
                if total_pct > 70.0:
                    logger.error(
                        "🚨 RUG-GUARD: %s — top10 holders own %.1f%% (>70%% concentration)",
                        short, total_pct,
                    )
                    return False
                if total_pct > 0:
                    logger.info(
                        "🛡️ RUG-GUARD: %s top10 holders %.1f%% ✅", short, total_pct
                    )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug(
                "RUG-GUARD: gmgn holders probe failed for %s: %s — fail-open",
                short, e,
            )

        # ── 3. Jupiter honeypot probe: can we get a SELL quote? ────────────
        try:
            probe = await get_quote(mint, SOL_MINT, 1000, slippage_bps=2500)
            if probe is None:
                logger.error(
                    "🚨 RUG-GUARD: %s — Jupiter cannot quote SELL (honeypot suspected)",
                    short,
                )
                return False
            logger.info("🛡️ RUG-GUARD: %s sell-quote OK ✅", short)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug(
                "RUG-GUARD: honeypot probe failed for %s: %s — fail-open",
                short, e,
            )

        return True
    except (TypeError, ValueError, RuntimeError) as e:
        logger.debug("RUG-GUARD: outer exception for %s: %s — fail-open", short, e)
        return True

_trend_cache: dict = {"pct": 0.0, "ts": 0.0}

async def check_market_trend() -> float:
    """SOL 1-hour trend from DexScreener (Cached for 5m)."""
    global _trend_cache
    now = time.time()
    if now - _trend_cache["ts"] < 300:
        return _trend_cache["pct"]

    if aiohttp is None:
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
                    logger.info("SOL 1h trend: %+.2f%%", pct)
                    return pct
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Trend error: %s", e)
    return _trend_cache["pct"]

async def position_manager(keypair, symbol, mint, bot=None):
    """Sub-task: Manages an open position with Breakeven Lock."""

    pos = active_positions.get(symbol)
    if not pos:
        return

    logger.info("🛡️ MANAGER ACTIVE: %s (Entry: $%.6f)", symbol, pos["entry_price"])

    # v3.23.19: rug detection — count consecutive no-route quotes
    no_route_count = 0
    NO_ROUTE_RUG_THRESHOLD = 3  # 3 cycles × 15s = 45s of no liquidity = rug

    while symbol in active_positions:
        try:
            await asyncio.sleep(15) # Optimal interval for RPC safety

            # --- SHOCK BREAKER CHECK ---
            panic = get_market_panic_score()
            is_panic = panic >= 85

            # 1. Price Check & Dynamic Config
            gov = get_governance_config()
            tp_pct = gov.get("tp_pct", TAKE_PROFIT_PCT)
            _sl_pct = gov.get("sl_pct", STOP_LOSS_PCT)
            be_pct = gov.get("breakeven_pct", BREAKEVEN_TRIGGER_PCT)

            # If AI detects EXTREME panic, tighten SL to 0.5% or Breakeven
            if is_panic:
                _sl_pct = 0.5
                logger.warning("🛡️ SHOCK BREAKER: Tightening %s SL due to Panic (%s)", symbol, panic)

            # Use escalating slippage quote so memecoin price-check works at all tiers
            from exchanges.jupiter import get_quote_with_escalation
            quote, q_reason = await get_quote_with_escalation(
                mint, SOL_MINT, pos["amount"],
                slippage_steps=(300, 1000, 2500),
            )
            if not quote:
                if q_reason == "no_route":
                    no_route_count += 1
                    logger.warning("🚨 %s no Jupiter route (%d/%d) — possible rug",
                                   symbol, no_route_count, NO_ROUTE_RUG_THRESHOLD)
                    if no_route_count >= NO_ROUTE_RUG_THRESHOLD:
                        # Confirmed rug — token has no liquidity for 45+ seconds
                        _entry_sol = float(pos.get("entry_sol", AUTONOMOUS_TRADE_AMOUNT_SOL) or AUTONOMOUS_TRADE_AMOUNT_SOL)
                        logger.error("💀 RUGGED: %s — exiting manager (no liquidity %ds)",
                                     symbol, no_route_count * 15)
                        await _notify_admin(
                            bot,
                            f"💀 *RUGGED* — {symbol}\n"
                            f"No Jupiter route at any slippage for {no_route_count*15}s.\n"
                            f"Position abandoned (token cannot be sold).\n"
                            f"Entry: {_entry_sol:.4f} SOL = total loss."
                        )
                        record_trade_result(ADMIN_IDS[0], symbol, -100.0, -_entry_sol)
                        break
                else:  # api_error
                    logger.debug("Quote API error for %s, retrying next cycle", symbol)
                continue
            # Quote OK → reset rug counter
            no_route_count = 0

            out_amount = quote.get("outAmount")
            if not out_amount or out_amount <= 0:
                logger.debug("Invalid quote outAmount for %s: %s", symbol, out_amount)
                continue

            curr_sol = int(out_amount) / 1e9
            orig_sol = float(pos.get("entry_sol", AUTONOMOUS_TRADE_AMOUNT_SOL) or AUTONOMOUS_TRADE_AMOUNT_SOL)
            pnl = ((curr_sol - orig_sol) / orig_sol) * 100

            # 2. Breakeven Lock
            if pnl >= be_pct and pos['sl_price'] < pos['entry_price']:
                logger.info("🔒 BREAKEVEN LOCKED: %s", symbol)
                pos['sl_price'] = pos['entry_price'] * 1.001
                save_active_positions(active_positions)
                await _notify_admin(bot, f"🔒 *BREAKEVEN LOCK* — {symbol}\nRisk = ZERO ✅")

            # 2.5 MAX HOLD TIME — Force exit if position > 4 hours (protect old positions without created_at)
            created_at = pos.get("created_at")
            if created_at is None:
                # Old position without timestamp — use current time as fallback
                created_at = int(time.time())
            pos_age_sec = int(time.time()) - created_at
            max_hold_sec = 4 * 3600  # 4 hours
            if pos_age_sec > max_hold_sec and pnl < tp_pct:
                logger.warning("⏰ MAX HOLD TIME EXCEEDED: %s (%.1fh)", symbol, pos_age_sec / 3600)
                sig, _, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
                record_trade_result(ADMIN_IDS[0], symbol, pnl, pnl * orig_sol / 100)
                await _notify_admin(bot, f"⏰ *MAX HOLD EXIT* — {symbol}\nHeld: {pos_age_sec/3600:.1f}h | PNL: {pnl:+.2f}%\nTx: `{sig or 'failed'}`")
                break

            # 3. Stop Loss
            curr_price = pos['entry_price'] * (1 + (pnl/100))
            if curr_price <= pos['sl_price']:
                logger.info("🛑 STOP OUT: %s", symbol)
                sig, _, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
                record_trade_result(ADMIN_IDS[0], symbol, pnl, pnl * orig_sol / 100)
                await _notify_admin(bot, f"🛑 *STOP OUT* — {symbol}\nPNL: {pnl:+.2f}%\nTx: `{sig or 'failed'}`")
                break

            # 4. Take Profit
            if pnl >= tp_pct:
                logger.info("💰 TAKE PROFIT: %s", symbol)
                sig, _, _ = await execute_trade(keypair, "SELL", mint, SOL_MINT, pos["amount"])
                record_trade_result(ADMIN_IDS[0], symbol, pnl, pnl * orig_sol / 100)

                # Viral Loop Hook for CEO/Admin
                viral_hook = (
                    f"\n\n📱 *TIKTOK HOOK INC:*\n"
                    f"\"How I made {pnl:+.1f}% on {symbol} while sleeping. "
                    f"My AI agent caught the volatility before I even woke up. "
                    f"Zero-Loss mode is LIVE. Link in bio.\""
                )

                await _notify_admin(bot, f"💰 *PROFIT TAKEN* — {symbol}\nPNL: *{pnl:+.2f}%* ✅\nTx: `{sig}`{viral_hook}")
                break

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Position manager error [%s]: %s", symbol, e)
            await asyncio.sleep(60)

    # Clean up
    if symbol in active_positions:
        del active_positions[symbol]
    if symbol in _manager_tasks:
        del _manager_tasks[symbol]
    save_active_positions(active_positions)

async def auto_trader_loop(bot=None):
    """Main loop checking for Grade A signals 24/7."""
    logger.info("🚀 ZERO-LOSS ENGINE v3.22.0: ENGAGED")

    # ── 1. RESTORE STATE ──
    active_positions.clear()
    active_positions.update(load_active_positions())
    admin_id = ADMIN_IDS[0] if isinstance(ADMIN_IDS, list) else ADMIN_IDS

    # ── 2. MAIN 24/7 LOOP ──
    while True:
        try:
            AUTOTRADE_STATE["last_cycle_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            AUTOTRADE_STATE["signals_scanned"] = 0
            AUTOTRADE_STATE["candidates"] = 0
            AUTOTRADE_STATE["skipped_panic"] = 0
            AUTOTRADE_STATE["skipped_selectivity"] = 0
            AUTOTRADE_STATE["skipped_trend"] = 0
            AUTOTRADE_STATE["skipped_balance"] = 0

            users = load_users()
            admin_user = users.get(admin_id) or users.get(str(admin_id))
            if not admin_user or not admin_user.get("wallet_secret_enc"):
                # Fallback: try bot.py in-memory users dict
                try:
                    import bot as _bot_mod
                    _mem_users = getattr(_bot_mod, "users", {})
                    admin_user = _mem_users.get(admin_id) or _mem_users.get(str(admin_id))
                except (ImportError, AttributeError):
                    admin_user = None
            if not admin_user or not admin_user.get("wallet_secret_enc"):
                logger.error("❌ Admin wallet missing. Auto Trader waiting for /start...")
                AUTOTRADE_STATE["last_reason"] = "admin_wallet_missing"
                await asyncio.sleep(60)
                continue

            keypair = load_keypair(admin_user["wallet_secret_enc"])

            # Resume tasks for existing positions if not already running
            for sym, _pos in list(active_positions.items()):
                # Prefer mint stored in position dict (set at entry time).
                # Fall back to SCALP_TOKENS lookup via _resolve_mint.
                mint = _pos.get("mint") or _resolve_mint(sym)
                if mint and sym not in _manager_tasks:
                    logger.info("🛡️ RESUMING MANAGER: %s mint=%s...", sym, mint[:8])
                    _manager_tasks[sym] = asyncio.create_task(position_manager(keypair, sym, mint, bot=bot))
                elif not mint:
                    logger.error("🛡️ RESUME FAILED: %s — mint not found. Position unmonitored!", sym)

            # ── 3. SEARCH FOR ALPHA (FETCH UPDATED SELECTIVITY) ──
            if not _is_autotrade_enabled():
                AUTOTRADE_STATE["last_reason"] = "autotrade_disabled"
                await asyncio.sleep(45)
                continue

            gov = get_governance_config()
            signals = await check_scalp_signals()
            AUTOTRADE_STATE["signals_scanned"] = len(signals)
            if not signals:
                AUTOTRADE_STATE["no_signal_cycles"] = int(AUTOTRADE_STATE.get("no_signal_cycles", 0)) + 1
                AUTOTRADE_STATE["last_reason"] = "no_signals"
            else:
                AUTOTRADE_STATE["no_signal_cycles"] = 0

            test_cap_sol = _get_autotrade_test_cap_sol()
            if not signals and test_cap_sol > 0 and int(AUTOTRADE_STATE.get("no_signal_cycles", 0)) >= 3:
                probe_sym = "BONK" if _resolve_mint("BONK") else "JUP"
                if _resolve_mint(probe_sym):
                    signals = [{
                        "symbol": probe_sym,
                        "grade": "C",
                        "pct_5m": 0.50,
                        "volume_usd": 0.0,
                        "price": 1.0,
                    }]
                    AUTOTRADE_STATE["last_reason"] = "test_probe_candidate"
            for s in signals:
                sym = s['symbol']
                if sym in active_positions:
                    continue
                AUTOTRADE_STATE["candidates"] = int(AUTOTRADE_STATE.get("candidates", 0)) + 1

                # Dynamic Selectivity: Use governance Grade A/B thresholds
                configured_min_move = float(gov.get("grade_a_min_pct", 2.5) or 2.5)
                # HOTFIX 68: execution profile tuned for calmer markets.
                min_move = min(configured_min_move, 0.8)

                # --- SHOCK BREAKER: Skip Buys if Panic is High ---
                panic = get_market_panic_score()
                if panic >= 85:
                    logger.warning("🛑 SHOCK BREAKER: Skipping %s buy due to market panic (%s)", sym, panic)
                    AUTOTRADE_STATE["skipped_panic"] = int(AUTOTRADE_STATE.get("skipped_panic", 0)) + 1
                    AUTOTRADE_STATE["last_reason"] = f"panic_{panic}"
                    continue

                # ── Security Scan (Rug-Guard) ──────────────────
                mint = _resolve_mint(sym)
                if not await security_audit(mint):
                    logger.error("🚨 RUG-GUARD: Aborting %s (Security Check Failed)", sym)
                    await _notify_admin(bot, f"🚨 *RUG ATTEMPT BLOCKED* — {sym}\nToken failed security audit. 🛡️")
                    continue

                is_whale = (s.get('grade') == 'S')
                if (
                    is_whale
                    or abs(float(s.get('pct_5m', 0.0) or 0.0)) >= min_move
                    or s['grade'] == "A"
                    or s['grade'] == "B"
                    or (s['grade'] == "C" and abs(float(s.get('pct_5m', 0.0) or 0.0)) >= 0.35)
                ):
                    # Check Market Hedge
                    if await check_market_trend() < -4.0:
                        AUTOTRADE_STATE["skipped_trend"] = int(AUTOTRADE_STATE.get("skipped_trend", 0)) + 1
                        AUTOTRADE_STATE["last_reason"] = "market_trend_block"
                        continue

                    # Entry sizing (LEAN): auto-scale to available SOL so autotrade doesn't idle below default size.
                    wallet_pub = str(admin_user.get("wallet_pubkey") or "")
                    avail_sol = float(await get_sol_balance(wallet_pub) or 0.0) if wallet_pub else 0.0
                    trade_sol = min(float(AUTONOMOUS_TRADE_AMOUNT_SOL), max(0.0, avail_sol - float(MIN_SOL_RESERVE)))
                    test_cap_sol = _get_autotrade_test_cap_sol()
                    if test_cap_sol > 0:
                        trade_sol = min(trade_sol, test_cap_sol)
                    min_exec_floor = 0.05 if test_cap_sol <= 0 else max(0.01, min(test_cap_sol, 0.05))
                    if trade_sol < min_exec_floor:
                        logger.info("⏸️ AUTOTRADE WAIT: balance=%.4f SOL, tradeable=%.4f SOL", avail_sol, trade_sol)
                        AUTOTRADE_STATE["skipped_balance"] = int(AUTOTRADE_STATE.get("skipped_balance", 0)) + 1
                        AUTOTRADE_STATE["last_reason"] = f"insufficient_tradeable_balance<{min_exec_floor:.4f}"
                        continue

                    # Entry
                    prefix = "🐋 WHALE ENTRY" if is_whale else "⚡ ENTRY"
                    logger.info("%s DETECTED: %s", prefix, sym)
                    mint = _resolve_mint(sym)

                    # ── RISK CHECK before BUY ────────────────────────────────
                    allowed, risk_reason = _enforce_risk_limits(admin_id, trade_sol, sym)
                    if not allowed:
                        logger.warning("🛡️ RISK BLOCKED: %s - %s", sym, risk_reason)
                        AUTOTRADE_STATE["last_reason"] = f"risk_blocked:{risk_reason}"
                        continue

                    sig, out_tokens, entry_err = await execute_trade(keypair, "BUY", SOL_MINT, mint, int(trade_sol * 1e9))

                    if sig and out_tokens > 0:
                        sl_pct_val = gov.get('sl_pct', STOP_LOSS_PCT)
                        tp_pct_val = gov.get('tp_pct', TAKE_PROFIT_PCT)
                        active_positions[sym] = {
                            "mint": mint,
                            "entry_price": s['price'],
                            "entry_sol": trade_sol,
                            "amount": out_tokens,
                            "sl_price": s['price'] * (1 - sl_pct_val / 100),
                            "tp_price": s['price'] * (1 + tp_pct_val / 100),
                            "created_at": int(time.time()),
                        }
                        save_active_positions(active_positions)

                        # ── SYNC to user active_positions for manual SELL visibility ──
                        try:
                            from bot import users as _bot_users  # noqa: PLC0415
                            if admin_id in _bot_users:
                                _u = _bot_users[admin_id]
                                if "active_positions" not in _u:
                                    _u["active_positions"] = []
                                # Remove any stale entry for same mint before adding
                                _u["active_positions"] = [p for p in _u["active_positions"] if p.get("mint") != mint]
                                _u["active_positions"].append({
                                    "token": sym,
                                    "mint": mint,
                                    "entry_sol": trade_sol,
                                    "token_amount_raw": int(out_tokens),
                                    "sl_pct": sl_pct_val,
                                    "tp_pct": tp_pct_val,
                                    "peak_sol": trade_sol,
                                    "source": "autotrade",
                                })
                        except Exception as _sync_err:
                            logger.warning("Position sync to bot users failed: %s", _sync_err)

                        await _notify_admin(bot, f"⚡ *ZERO-LOSS BUY* — {sym}\nAmt: *{trade_sol:.4f} SOL*\nTx: `{sig}`\nSL: -{sl_pct_val}% | TP: +{tp_pct_val}%")
                        _manager_tasks[sym] = asyncio.create_task(position_manager(keypair, sym, mint, bot=bot))
                        AUTOTRADE_STATE["last_entry_symbol"] = sym
                        AUTOTRADE_STATE["last_entry_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        AUTOTRADE_STATE["last_reason"] = "entry_executed"
                        AUTOTRADE_STATE["last_entry_error"] = "-"
                    else:
                        AUTOTRADE_STATE["last_reason"] = "entry_failed"
                        AUTOTRADE_STATE["last_entry_error"] = entry_err or "unknown"
                else:
                    AUTOTRADE_STATE["skipped_selectivity"] = int(AUTOTRADE_STATE.get("skipped_selectivity", 0)) + 1
                    AUTOTRADE_STATE["last_reason"] = "below_selectivity"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Auto-trader loop error: %s", e)
            AUTOTRADE_STATE["last_reason"] = f"loop_error:{type(e).__name__}"
        await asyncio.sleep(45)

if __name__ == "__main__":
    asyncio.run(auto_trader_loop())
