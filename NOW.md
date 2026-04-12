# ApexFlash Bot — CURRENT STATUS
# Last updated: 2026-04-12 (Sessie 28)
# MAIN GOAL: EUR 1.000.000 netto vóór 29-03-2028

## LIVE STATE (sessie 28 — VERIFIED via Redis)
- Render service: srv-d6kcjbpaae7s73aadsu0
- Version: v3.23.x → commit 5f77f30
- Keys on Render: 74 (gesynchroniseerd via sync_render_env.py)
- **autotrade:enabled = 1** → AUTO-TRADE STAAT AAN op Render
- **8 open posities**: BONK, POPCAT, PNUT, FARTCOIN, MEW, JUP, WIF, GOAT
- Grade A signals totaal: 2 (kpi:grade:A:total in Redis)
- GMGN market API: 403 lokaal (IP whitelist = 86.88.183.115 thuis) → OK op Render
- DISCORD_WEBHOOK_URL: LEEG → Discord alerts werken NIET tot gevuld
- PDCA journal: leeg (0 entries) → trade journal schrijft niet of bot herstart frequent

## WAT WERKT
- ✅ Bot @ApexFlashBot live
- ✅ AI Router: Groq→Cerebras→Gemini-2.5-flash→OpenRouter-Qwen→OpenRouter-Llama→Nebius→DeepSeek
- ✅ GMGN Trade: exchanges/gmgn.py (swap/quote/order + Ed25519 signing)
- ✅ GMGN Market: exchanges/gmgn_market.py (kline/rank/trenches/wallet stats)
- ✅ Trading: Jupiter primary → GMGN fallback (zero_loss_manager.py)
- ✅ GMGN wallet: CsgcvMXFfLTZm8u8a6Eds1GnUXTcpPHV7Cho5ueUApvi
- ✅ GMGN skills in Claude Code: gmgn-market, gmgn-token, gmgn-swap, gmgn-portfolio, gmgn-track, gmgn-cooking
- ✅ Whale Intelligence v2.0: agents/whale_watcher.py (GMGN smart_degen scoring, grade S/A/B)
- ✅ PDCA Trade Journal: agents/trade_journal.py (log signals, check outcome 1h, /pdca report)
- ✅ /whale_intel + /pdca Telegram commands (admin)
- ✅ 🐋 GMGN Intelligence button in Whale menu → live signal feed

## SSOT SECRETS — NOOIT DIRECT IN RENDER AANPASSEN
Box Drive MASTER: C:\Users\erik_\Box\MEGA BOT\MASTER_ENV_APEXFLASH.txt
ISO 9001 copy:    C:\Users\erik_\Box\08_OPERATIONS\8.1_ApexFlash_Bot\.env
GMGN keys:        C:\Users\erik_\.config\gmgm\.env
Sync bot→Render:  python C:\Users\erik_\source\repos\apexflash-bot\sync_render_env.py

## GMGN — ALLE LOCATIES
| Bestand | Locatie |
|---------|---------|
| Trade client | apexflash-bot/exchanges/gmgn.py |
| Market client | apexflash-bot/exchanges/gmgn_market.py |
| Config vars | apexflash-bot/core/config.py |
| Keys (local) | C:\Users\erik_\.config\gmgm\.env |
| Keys (Render) | GMGN_API_KEY, GMGN_PRIVATE_KEY, GMGN_WALLET_ADDRESS |
| Claude skills | C:\Users\erik_\.agents\skills\gmgn-* |
| Wallet (SOL) | CsgcvMXFfLTZm8u8a6Eds1GnUXTcpPHV7Cho5ueUApvi |
| API key | gmgn_69ed2f741906301ebd076b2016522044 |

## WHALE INTELLIGENCE — HÓE HET WERKT
- Elke 5 min: GMGN rank (smart_degen_count hoog) + trenches (pump tokens)
- Grade S: ≥5 smart degens + ≥15% 1h + ≥$100K volume → signaal naar @ApexFlashAlerts + admins
- Grade A: ≥3 smart degens + ≥5% 1h + ≥$20K volume → signaal naar @ApexFlashAlerts
- Grade B: info-signaal in Redis (niet naar channel)
- PDCA: elk signaal gelogd → na 1h prijs check → WIN/LOSS/FLAT → dagstatistiek
- /pdca → win rate per grade + aanbevelingen om thresholds te tunen

## VOLGENDE SESSIE — START HIER (sessie 29)
1. CHECK Redis: `apexflash:active_positions` — zijn posities nog open? Wat zijn P&L?
2. CHECK `/whale_intel` in Telegram — scanner actief? Signalen recent?
3. DISCORD_WEBHOOK_URL invullen — Erik: Discord channel → Integrations → Webhooks → Copy URL → Render env var
4. PDCA journal leeg: debug waarom trade_journal.py niet schrijft naar Redis
5. Bitunix resultaten (+156%/+305% SIREN) gebruiken als sociale bewijs in Hero copy
6. Reddit outreach activeren (drafts in promo/ map)
7. Landing page apexflash.pro live controleren na alle commits van sessie 28

## OPENSTAAND — ACTIE VEREIST
| Item | Status | Verantwoordelijke |
|------|--------|-------------------|
| DISCORD_WEBHOOK_URL | ❌ leeg | **Erik** (30 sec) |
| GMGN IP whitelist Render | ⚠️ lokale 403 | **Erik**: voeg Render IP toe op gmgn.ai |
| PDCA journal schrijft niet | ❌ 0 entries | AI: debug trade_journal.py |
| Active positions P&L | ❓ onbekend | AI: Redis uitlezen na restart |
| WHALE_AUTO_TRADE env var | false (maar Redis=1) | Controleer welke flag leidend is |

## BEKENDE ROOT CAUSES (gevonden sessie 28)
- Whale scanner stil → GMGN_API_KEY stond NIET in main .env (key naam: GMGM_API vs GMGN_API_KEY)
- Opgelost: keys toegevoegd aan .env + sync_render_env.py bijgewerkt
- GMGN 403 lokaal = IP whitelist (normaal) — Render moet wél in whitelist staan
- autotrade:enabled=1 in Redis → bot handelt al (8 posities open)

## GEDAAN (sessie 28 — 2026-04-12)
- ✅ apexflash-app build CLEAN: BOM verwijderd uit package.json (Turbopack crash fix) → commit 3ed3ec7
- ✅ Navbar top-10 + Hero pt-28 spacing fix committed + pushed → commit dfc087f
- ✅ Landing page VOLLEDIG GETEST (lokale preview poort 61898):
  - CryptoTicker live: BTC $72,481 / ETH $2,264 / SOL $84.11 ✅
  - Hero "Whales Are Buying Right Now 🐳" ✅
  - Referral 25%→30%→35% tiered ✅
  - Pricing $9.99 / $29.99 ✅
  - Gumroad Pro: mindvault34.gumroad.com/l/rwauqu ✅
  - Gumroad Elite: mindvault34.gumroad.com/l/unetcl ✅
  - Telegram: t.me/apexflashbot + t.me/apexflash_signals ✅
  - /api/stats: OK (users=3 uit Redis, volume=$39K+) ✅
  - /api/subscribe: OK (email opgeslagen, welcome message) ✅
  - /api/affiliate/bitunix + blofin: tracked=true ✅
  - /about: HTTP 200 ✅
  - Console errors: GEEN ✅
- ✅ DISCORD_WEBHOOK_URL placeholder toegevoegd aan bot .env (was missing)
- ⚠️ ACTIE VEREIST: Vul DISCORD_WEBHOOK_URL in .env én Render in — Discord posts werken pas daarna

## GEDAAN (sessie 27 — 2026-04-11)
- ✅ apexflash-app push be4c1a5: About page, favicon /favicon.svg, CLAUDE.md SSOT — Render deploy getriggerd
- ✅ /api/ceo route.ts intact en correct — 404 was transient
- ✅ twitter_poster.py: post_whale_signal_tweet() — Grade A/S signalen auto naar Twitter/X
- ✅ notifications.py: notify_discord_gmgn_signal() — Grade A/S signalen naar Discord embed
- ✅ bot.py: _whale_signal_to_telegram → Twitter + Discord beide gewired (non-blocking)
- ✅ Commits: c76dcf0 (Twitter) + 55593f0 (Discord) → Render deploy
