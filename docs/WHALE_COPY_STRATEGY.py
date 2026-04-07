"""Whale copy trading strategie - 1W5H framework.

WHO (Wie copy-en we?)
======================
Top performers identificeren via:
1. Helius RPC - wallet transaction history (we hebben API key)
2. Known whale wallets - publieke databases (pump.fun, Birdeye leaderboards)
3. Mizar marketplace bots - proven PnL 30d

Criteria:
- Win rate > 60% (laatste 30d)
- PnL > +50% (30d)
- Min 20 trades (sample size)
- Max drawdown < 20%

WHAT (Wat copy-en we?)
=======================
Alleen ENTRY signals:
- Copy BUY orders binnen 30s van whale TX
- NIET copy SELL (exit op onze eigen breakeven/TP)
- Alleen tokens met liq > $100K

WHEN (Wanneer copy-en we?)
===========================
Real-time triggers:
1. Whale wallet nieuwe BUY TX detected (Helius websocket)
2. Token audit passed (rug check via helius_token_metadata)
3. Market panic < 85 (geen buys tijdens crash)
4. Onze wallet heeft tradeable SOL > 0.1

WHERE (Waar traden we?)
========================
Platforms:
- Jupiter swap (Solana DEX aggregator) - LIVE
- Raydium (direct pool access) - fallback
- Orca (stable swaps) - fallback

WHY (Waarom werkt dit?)
========================
1. Whales hebben alpha - betere info dan retail
2. On-chain data = objectief, geen emotions
3. Kleine position size (0.1-0.25 SOL) = laag risico
4. Exit op onze regels = bescherming tegen whale dumps

HOW (Hoe implementeren?)
=========================
Code flow:

1. MONITOR (exchanges/helius.py - nieuwe module)
   - Websocket subscribe op whale wallets (5-10 adressen)
   - Parse swap transactions (Token A ? Token B)
   - Filter: alleen BUY SOL ? Token X

2. VALIDATE (core/whale_validator.py)
   - Token audit: rugpull check, liquidity check
   - Whale reputation: check historical win rate
   - Market check: panic score, trend

3. EXECUTE (zero_loss_manager.py - extend)
   - Copy buy: zelfde token, onze position size (0.1 SOL)
   - Set breakeven trigger: +3% (whale dump protection)
   - Set TP: +10% (take profit eerder dan whale)

4. TRACK (core/persistence.py)
   - Log whale TX hash
   - Log onze mirror TX
   - Track outcome: win/loss/neutral

TEST STRATEGIE
==============
Week 1: Paper trading
- Log whale signals, simulate trades
- Track zou-zijn PnL
- Measure: hit rate, avg return, max DD

Week 2: Micro position (0.05 SOL)
- Real trades, klein bedrag
- Max 3 positions tegelijk
- Daily review: welke whales presteren

Week 3: Scale up (0.1 SOL)
- Alleen whales met 70%+ hit rate in Week 1+2
- Max 5 positions
- Auto-disable whale als 3 losses in row

KNOWN WHALE WALLETS (Solana)
==============================
Research bronnen:
- https://solscan.io/analytics/whales
- https://birdeye.so/leaderboard
- pump.fun top traders (via API)

Voorbeeld top wallets (verify eerst):
- 5Q544... (known SOL whale - grote volume)
- 8Pmk9... (memecoin flipper - hoge win rate)
- DYw8b... (DeFi positions - low risk)

ACTION ITEMS
============
1. Build exchanges/helius.py - websocket whale monitor
2. Build core/whale_validator.py - reputation + audit
3. Extend zero_loss_manager.py - whale_copy_mode flag
4. Add /whale_track <address> command - start tracking
5. Add /whale_stats command - show performance table

RISK LIMITS
===========
- Max 0.25 SOL per whale copy
- Max 30% van wallet in whale copies tegelijk
- Stop whale tracking na 5 consecutive losses
- Circuit breaker: pause all whale copies als markt panic > 90
"""

print(__doc__)
