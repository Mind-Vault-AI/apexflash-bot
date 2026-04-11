# Reddit Launch Post
# Target: r/solana (primary), r/defi, r/SatoshiStreetBets
# Post as genuine builder story — NOT as advertisement
# Link to bot in COMMENTS only, not in post body

---

## TITLE OPTIONS (pick one):

1. I built a Telegram bot that tracks Solana whale wallets and lets you trade what they trade
2. Tracking $500M+ in whale movements taught me something about Solana — so I built a free tool
3. I made a free Solana whale alert bot for Telegram — here's what I learned building it

---

## POST BODY:

**For r/solana:**

I've been tracking whale wallets on Solana for the past few months and noticed patterns that most retail traders miss completely.

When a whale moves 50K+ SOL from an exchange to a private wallet = accumulation signal.
When SOL flows INTO exchanges from known whale addresses = potential sell pressure.

These signals often precede price moves by minutes to hours.

So I built a bot that does this automatically. It monitors 25+ tracked wallets across Binance, Coinbase, OKX, Bybit, and others. When large transfers happen, it sends an alert to a Telegram channel.

Some things I learned building this:

1. Most "whale alerts" on Twitter are delayed 5-15 minutes. On-chain data via Helius RPC is near real-time.
2. Exchange-to-exchange transfers are usually just internal rebalancing — not signals. Filtering these out reduced noise by ~60%.
3. The interesting moves are exchange-to-unknown-wallet (accumulation) and unknown-to-exchange (preparing to sell).

I also added Solana token trading directly in the bot via Jupiter V6 — so you can act on alerts without leaving Telegram.

It's free to use with basic features. Built it as a side project and figured I'd share it with the community.

Happy to answer any technical questions about the architecture or whale tracking methodology.

---

**COMMENT (post separately, after a few organic comments):**

For anyone interested, the bot is @ApexFlashBot on Telegram and the free alert channel is @ApexFlashAlerts. Open source risk controls, non-custodial wallet, 1% flat fee on trades.

---

## r/defi VERSION (shorter, more technical):

**Title:** Built an on-chain whale tracker for Solana — free Telegram bot

Tracks 25+ whale wallets across major exchanges. Sends real-time alerts when large transfers happen. Also has Jupiter V6 integration for instant swaps.

Non-custodial (Fernet encrypted wallet), no database of private keys, 1% transparent fee on trades.

Free tier includes basic alerts and trading. Pro tier ($19/mo) adds instant alerts and multi-chain tracking.

Curious what features the community would find most useful. Currently considering adding:
- Copy-trade automation (mirror whale buys)
- DCA bot integration
- Portfolio tracking

What would be most valuable to you?
