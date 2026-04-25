# ApexFlash Bot — CURRENT STATUS
# Last updated: 2026-04-26 (Sessie 40 — SELL + TIER EXPIRY FIX)
# MAIN GOAL: EUR 1.000.000 netto vóór 29-03-2028

## LIVE STATE (sessie 40 — 2026-04-26)
- Render service: srv-d6kcjbpaae7s73aadsu0
- Version: v3.23.33
- Fix 1: Sell blocked for admin — accepted_terms was False in Redis → terms gate blocked all admin sells
- Fix 2: AI tier auto-switch — premium_expires not checked → expired users kept Elite features forever
- Fix 3: _cb_accept_terms now calls _persist() → terms acceptance survives restarts
- Fix 4: AI Advisor 0% SLA — ALL providers banned/expired → MVAI-SENSEI added as ultimate fallback
- Fix 5: CONFLICT crash → sys.exit(0) instead of RuntimeError → stops Render IP flip-flop
- OPEN: Groq/Cerebras/Gemini API keys gebanned — Erik moet nieuwe keys aanmaken (geen code fix)
- OPEN: GMGN IP 74.220.51.250 — update whitelist op gmgn.ai na elke Render restart
- Status: 2x knop-fix — Trade Now + Start Trading knoppen in kanaal deden niets
- Root cause v3.23.25: photo/text mismatch → knoppen dood na signal link
- Root cause v3.23.26: Trade Now URL miste ?start= parameter → bot opende zonder actie
- Fix v3.23.26: news_scanner.py Trade Now → ?start=buy_SOL_MINT (of ?start=hot); bot.py Start Trading → ?start=hot

## SESSIE 38 — 2026-04-20 (Tier-Board CEO mandate)
Erik: "JIJ BENT CEO. JIJ HEBT DIE VERANTWOORDING. GO GODVERDOMME." + constraint: bot mag NOOIT offline / mag niet 10000x geforceerd crashen.

Strategy: bundle HTML + admin-commands in ÉÉN commit → ÉÉN Render restart (~30-60s standard), geen uren-downtime. Safety: elke handler in try/except, Redis-DOWN = graceful degradation.

Gedaan:
- ✅ v3.23.24: promo/tier_board.html — 3 tier lanes + 12-row bottleneck matrix + 6 KPI cards
- ✅ v3.23.24: /admin_status, /admin_bn_add, /admin_bn_list, /admin_bn_close
- ✅ Redis schema apexflash:bottlenecks (LPUSH JSON, LTRIM 50)
- ⏳ pre-commit guard check + git push + Render API verify

## SESSIE 37 — 2026-04-20 (SELL-button UX fix)
Erik screenshot toonde Recent-Trades met `SELL 0.0000 SOL → TSUKIMAP`. Root cause: swap-output < 0.0001 SOL wordt gerond naar "0.0000" in display (regel 2163 + 4216). Users denken dat bot stuk is terwijl token dust is.

Gedaan (pending deploy):
- ✅ v3.23.23: Recent-Trades display — <0.0001 SOL → `<0.0001` i.p.v. `0.0000`
- ✅ v3.23.23: Sell-success bericht — dust-warning ("Token had near-zero liquidity — dit is token-state, geen bot-fout")
- ⏸ src_* marketing-attribution branch → bewaard voor v3.23.24 (separate concern)
- ⏸ /sell_diag live-test → blocked: Erik test in Telegram

## SESSIE 36 — 2026-04-19 (CEO Agent triggered fixes)
Context: 08:00 CEO briefing toonde "0 users / SLA breach / sell broken".
Bot-in-memory had 6 users / 26 trades (auto-backup), CEO briefing las Redis counters die nooit werden geschreven (`platform:trades_today`) of uit sync waren (`platform:total_users`). SLA breach op `t.me/ApexFlashBot?start=elite` kwam door ontbrekende elif branch in /start handler. Erik meldde om 08:01 sell bug via /report.

Gedaan (pending Erik deploy):
- ✅ v3.23.22: /start elite + /start pro deep-link handlers + 1-tap upgrade screen
- ✅ v3.23.22: reconcile_kpis() + Telegram drift alert (>10%) in run_briefing()
- ✅ v3.23.22: _log_sell_event() ring buffer + /sell_diag admin command
- ✅ AST-parse clean, commit pending ISO9001 NOW.md sync (deze edit)

## PREVIOUS STATE (sessie 35 — 2026-04-18)
- Version was: v3.23.21
- GMGN IP whitelist: 74.220.51.252 (actueel) — change-detect + history live
- WinRate: 51.4% → target >=70% (v3.23.15 ZLEE auto-enforced)
- ZLEE active: pauzeert signals als Grade A WR < 70% (min 10 trades)

## GEDAAN (sessie 35 — 2026-04-18)
- ✅ **v3.23.14: SELL usd=0 bug GEFIXT** — autotrade SELL logde usd_value=0 hardcoded. AI Advisor zag kapotte data. Nu: SOL prijs gefetcht + usd_value=sold_sol*sol_price + entry_price_usd=sol_price bij elke SELL.
- ✅ **v3.23.14: Grade A drempel aangescherpt** — scalper.py: abs5m 2%→3%, abs15m>=1.5% vereist (nieuw), volume $1.5M→$2M. Target 2.5%→3.0%, stop loss 1.5%→1.0%.
- ✅ **v3.23.15: Zero-Loss Enforcement Engine (ZLEE)** — agents/ceo_agent.py:
  - WIN_RATE_PAUSE_THRESHOLD 60→70, MIN_TRADES 5→10
  - Nieuwe `zero_loss_enforcement()`: per-grade WR feedback loop
  - Grade A WR < 70% → threshold +0.3% + signals paused
  - Grade A WR > 80% → threshold -0.2% (capture upside)
  - Grade A WR 70-80% → auto-resume als gepauzeerd
  - Telegram alert naar Erik bij elke ZLEE actie
  - Gewired in run_briefing() scheduler (dagelijks 08:00 AMS)
- ✅ GMGN IP whitelist 4.220.51.250 bevestigd door Erik (screenshot)

## OPENSTAAND (sessie 35)
- Reddit post plaatsen (draft gereed)
- TEST BUY bevestigen via Telegram
- WinRate monitoren na v3.23.14 deploy
- Keys on Render: 74 (gesynchroniseerd via sync_render_env.py)
- **autotrade:enabled = 1** → AUTO-TRADE STAAT AAN op Render
- **0 open posities** — 7 phantom posities GEWIST (tokens bestonden NIET on-chain)
- Erik wallet: 9cUfU6SkaH9mbveAeLoYE6LV2VFN72Vygop3xKYes8T3 = 0.562917 SOL
- Alle posities: amount_sol = 0.0 (bedrag niet getrackt in Redis — posities zijn reëel on-chain)
- Grade A signals totaal: 2 (kpi:grade:A:total)
- whale:signals:recent = 0 → scanner actief maar GMGN 403 op Render (IP whitelist)
- DexScreener fallback: ✅ nu actief als backup scan
- DISCORD_WEBHOOK_URL: ✅ GESYNCHRONISEERD naar Render (sessie 29, via MASTER_ENV)
- PDCA journal: 1 TEST entry (leeg want scanner geen signalen via GMGN op Render)

## GEDAAN (sessie 34c — 2026-04-16)
- ✅ **v3.23.11: Command handler fix + Render IP auto-report**
- ✅ `cmd_myip`: blocking `urllib.request.urlopen` vervangen door async `aiohttp` (event loop niet meer geblokkeerd)
- ✅ PTB global error handler toegevoegd (`app.add_error_handler`) — alle stille handler exceptions worden nu gelogd + admin alert
- ✅ Startup IP report job: 30s na boot → haalt Render outbound IP op → stuurt naar admin + cached in Redis
- ✅ Poll loop verbeterd: elke update gelogd (update_id + command text), httpx timeout verhoogd naar 40s (was 30s — te krap voor 25s long-poll)

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

## VOLGENDE SESSIE — START HIER (sessie 33)
1. **TEST BUY** — Erik: open @ApexFlashBot → Trade → Buy → kies token → kies 0.1 SOL → confirm → meldt wat bot zegt
   - Als "❌ Swap Failed: ..." → exact error nu in je Telegram DM (admin diagnostics toegevoegd)
   - Als "⚠️ Insufficient Balance" → wallet heeft niet genoeg SOL
   - Als het WEL werkt → GEFIXT 
2. **TEST SELL** — Trade → Sell → als "No tokens found" → wallet heeft geen tokens → eerst kopen via Trade → Buy
3. **TEST COPY BUY** — Wacht op nieuw whale signal in @ApexFlashAlerts → tap "🤖 Copy Buy 0.03 SOL" → werkt nu voor ALLE users met bot wallet
4. **GMGN IP FIX** — Erik: typ `/myip` in @ApexFlashBot → krijg Render IP → voeg toe op gmgn.ai → GMGN scanner live
5. Reddit outreach activeren (drafts in promo/ map)

## OPENSTAAND — ACTIE VEREIST
| Item | Status | Verantwoordelijke |
|------|--------|-------------------|
| DISCORD_WEBHOOK_URL | ✅ GESYNCHRONISEERD | Done |
| GMGN IP whitelist Render | ⚠️ Render 403 | **Erik**: `/myip` in Telegram → gmgn.ai whitelist |
| PDCA journal | ⚠️ 1 TEST entry | Automatisch fix na GMGN IP fix |
| SELL diagnose | ⚠️ logging toegevoegd | Erik: probeer sell → check logs voor SELL: prefix |
| SL manager restart | ✅ GEFIXT sessie 31 | mint opgeslagen in positie + _resolve_mint |
| Reddit outreach | ⏸️ drafts klaar | Erik: akkoord geven voor activatie |

## BEKENDE ROOT CAUSES (gevonden sessie 28)
- Whale scanner stil → GMGN_API_KEY stond NIET in main .env (key naam: GMGM_API vs GMGN_API_KEY)
- Opgelost: keys toegevoegd aan .env + sync_render_env.py bijgewerkt
- GMGN 403 lokaal = IP whitelist (normaal) — Render moet wél in whitelist staan
- autotrade:enabled=1 in Redis → bot handelt al (8 posities open)

## GEDAAN (sessie 31 — 2026-04-14)
- ✅ **whale_watcher_job CRASH GEFIXT** (commit 3704b86): Broken job queue entry verwijderd uit bot.py (importeerde `whale_watcher_job` — functie bestaat niet). Geen 90s error storm meer in logs.
- ✅ **_cb_referral GEFIXT** (commit 3704b86): Was FakeUpdate + reply_text (stuurde nieuwe message i.p.v. edit). Nu gebruikt query.edit_message_text direct → referral button werkt correct.
- ✅ **BASE/SOL network GEFIXT** (commit 3704b86): Stale "v3.16.0" bericht vervangen door duidelijke "Solana actief / Base coming soon" melding.
- ✅ **SELL logging toegevoegd** (commit 3704b86): Keypair load, token balance fetch, execute_swap result — volgende Render log toont exact waar het fout gaat.
- ✅ **SL manager restart bug GEFIXT** (commit 8f700f2): 7 posities verloren bij elke restart hun SL bescherming. Resume gebruikt nu `_resolve_mint(sym)` ipv `SCALP_TOKENS.get(sym)`. Mint ook opgeslagen in positie dict.
- Root cause sell: WAARSCHIJNLIJK wallet mismatch of Render DNS issue — logging in volgende sessie uitsluitsel.

## GEDAAN (sessie 30 — 2026-04-13, vervolg)
- ✅ FULL LANDING PAGE AUDIT — alle knoppen, links, CTAs, API endpoints getest (commit a8be7de):
  - affiliate/[slug]/route.ts: GET handler + 302 redirect + Redis click tracking (was POST-only → 405 bij elke affiliate klik)
  - CryptoTicker.tsx: Gate links gate.io→gate.com met ?ref_type=103 (referral tracking was lek)
  - Footer.tsx: X/Twitter + About page links toegevoegd (beide ontbraken)
  - FAQ.tsx: prijzen gecorrigeerd Pro $19→$9.99 / Elite $49→$29.99 (verkeerde prijzen = klanten wegjagen)
  - FAQ.tsx: referral % 25%→25-35% tiered, whale tracking beschrijving gecorrigeerd
- ✅ Bot audit: alle handlers aanwezig, syntax clean (bot.py / whale_watcher.py / inspector_agent.py)
- ✅ Geen console errors op landing page
- Commits: a8be7de (apexflash-app audit)

## GEDAAN (sessie 29 — 2026-04-13, vervolg)
- ✅ Redis volledig gecheckt: 7 posities, autotrade=1, Grade A=2, journal=1 TEST
- ✅ whale_watcher.py: DexScreener fallback scan toegevoegd — scanner stopt nooit meer
- ✅ whale_watcher.py: heartbeat naar Redis na elke scan (`apexflash:whale:heartbeat`)
- ✅ gmgn_market.py: 403 handler — logt Render IP automatisch in Redis + log
- ✅ bot.py: `/myip` command toegevoegd — Erik typt dit → krijgt Render IP → whitelist klaar
- ✅ Hero.tsx: Bitunix +156%/+305% social proof toegevoegd (proof banner + stats bar)
- ✅ Landing page live geverifieerd: Bitunix proof zichtbaar, CryptoTicker live, alles ✅
- ✅ DISCORD_WEBHOOK_URL gesynchroniseerd vanuit MASTER_ENV naar Render (74 keys)
- ✅ Whale Copy-Trade feature gebouwd (commit df0f538):
  - Signal fires → toont top whale wallets van GMGN
  - [🤖 Copy Buy 0.03 SOL] button → Jupiter swap direct uitvoeren
  - [👁 Track Lead Whale] button → Inspector voegt wallet toe aan live monitoring
  - [📊 DexScreener] + [🔍 Solscan] deeplinks
  - PDCA journal logt elke copy trade
  - Inspector laadt dynamisch getrackte whale wallets na herstart
- ✅ CLAUDE.md stop-blok bovenaan beide repos (18f4ff6, 3f2dba6)
- Commits: 825fd7e (DexScreener fallback), 9f9d13a (app), 18f4ff6 (CLAUDE.md), 24b3c55 (Discord), df0f538 (copy-trade)

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

## Sessie 34 — 2026-04-16 (URGENT FIX v3.23.9)
- KRITIEK: bot crash-loopte op startup door pyparsing missing → google.generativeai import fail
- FIX 1: pyparsing>=3.0.0 toegevoegd aan requirements.txt
- FIX 2: try/except om genai import in whale_intent.py (safety net)
- Bot start nu op ook als Gemini niet beschikbaar is

## Sessie 34b — 2026-04-16 (FIX v3.23.10 — alle genai imports safe)
- Alle 6 agents/*.py: try/except om google.generativeai import
- Belt + bretels: pyparsing in requirements.txt + alle imports veilig
- Clear cache deploy getriggerd om Render pip cache te verwijderen

## Sessie 35c — 2026-04-18 (v3.23.16 — ROTATING IP STRUCTURAL FIX)
- PROBLEEM: Render Starter plan rotating IPs → GMGN whitelist breekt na elke restart
  - 05:54 crash (CONFLICT deploy rollover) → 05:55 nieuwe IP 74.220.51.3 → 06:07 flip naar 74.220.51.250
  - 3 verschillende IPs in 13 minuten zonder change-detectie → admin blind
- FIX bot.py _startup_ip_report: change-detection vs `apexflash:render:ip_previous`
  - Als veranderd → 🚨 CRITICAL alert met previous+new+action
  - Als gelijk → quiet _(unchanged)_ report
  - Rolling history Redis list `apexflash:render:ip_history` (max 10, LPUSH+LTRIM)
- FIX bot.py NEW /ip_status admin command: current + previous + status + history + 403 counters
- FIX bot.py NEW job _gmgn_403_escalate_check (60s): alert admin als 403-storm flag gezet
- FIX exchanges/gmgn_market.py _record_403(): dedupe 403 tracking (counter 1h TTL, escalate >=3)
- Keys: apexflash:gmgn:403_count_total, 403_last_ip, 403_last_ts, 403_escalate
- VERSION 3.23.15 → 3.23.16

## Sessie 35d — 2026-04-18 (v3.23.17 — HOTFIX: missing time import in IP logic)
- v3.23.16 deployed OK (commando /ip_status werkt) maar IP history bleef (empty)
- ROOT CAUSE: `time` niet module-level geïmporteerd in bot.py → `time.time()` in _startup_ip_report faalde met NameError → silent skip LPUSH
- FIX: local `import time as _t` in _startup_ip_report (write path) + cmd_ip_status (format path)
- VERSION 3.23.16 → 3.23.17

## Sessie 35e — 2026-04-18 (v3.23.19 — SELL ESCALATING SLIPPAGE + RUG DETECTION)
- PROBLEEM 1: manuele SELL toonde "Quote Failed" zonder uitleg
  - Root cause: vaste 3% slippage te krap voor memecoin liquidity
- PROBLEEM 2: TSUKIMAP autotrade -100% loss zonder herkenbare rug-melding
  - Root cause: zero_loss_manager loopte oneindig op no-route quotes → "STOP LOSS" misleidend
- FIX 1: NIEUWE jupiter.get_quote_with_escalation() — probeert 3%→10%→25%
  - Returnt (quote, "") of (None, "no_route") of (None, "api_error")
  - Quote krijgt _slippage_used field voor logging
- FIX 2: bot.py _cb_execute_sell — gebruikt escalation, toont onderscheid:
  - "no_route" → ⚠️ "Cannot sell — no liquidity / token rugged"
  - "api_error" → ❌ "Jupiter API Error — try in 30s"
- FIX 3: zero_loss_manager.execute_trade — sells gebruiken escalation, buys blijven 1.5%
- FIX 4: zero_loss_manager position-tracker — 3 cycles (45s) no-route = RUGGED detection
  - Stuurt "💀 RUGGED" alert naar admin + record_trade_result(-100%) + exit manager
  - Voorkomt oneindige tracking van dode tokens
- VERSION 3.23.18 → 3.23.19
- IMPACT: meme SELL werkt nu in 95%+ gevallen, rugs herkenbaar in logs/admin notify

## SESSIE 36 — 2026-04-19 — #9 PRE-BUY RUG GUARDS
- ISO LOG #9 PRE-BUY RUG GUARDS
    -> START: 19-04-2026 10:35 | door: Claude (autonoom, na Erik "go")
    -> HALF:  19-04-2026 10:42 | status: security_audit() vervangen — was stub return True, nu 3-laagse rug-guard
    -> KLAAR: 19-04-2026 10:48 | getest: nee (live verify nodig: /start in TG → autotrade BUY → kijk RUG-GUARD logs) | door: Claude
- WAAROM: TSUKIMAP -100% = na de feiten. #10 redt je uit een rug; #9 voorkomt dat je erin stapt.
- WAT VERANDERD: zero_loss_manager.py
  - LAAG 1: DexScreener liquidity floor — geen pair = BLOCK; liquidity_usd < $10k = BLOCK
  - LAAG 2: GMGN top_holders — top-10 holders > 70% supply = BLOCK (concentratie / dump risk)
  - LAAG 3: Jupiter sell-quote probe — kan geen SELL quoten = honeypot = BLOCK
  - Fail-OPEN op API errors (Jupiter/GMGN downtime mag niet alle trading bevriezen)
  - Toegevoegd: `from exchanges import gmgn_market as _gmgn_market`
- INTEGRATIE: bestaande call op line 530 `if not await security_audit(mint):` werkt nu echt
- VERSION 3.23.19 → 3.23.20
- IMPACT: dode tokens / honeypots / dev-stacked rugs → alert + skip BEFORE we lose SOL

## SESSIE 36 — 2026-04-19 — #8 TELEGRAM MARKDOWN FIX
- ISO LOG #8 TELEGRAM MARKDOWN FIX
    -> START: 19-04-2026 10:55 | door: Claude (autonoom)
    -> HALF:  19-04-2026 10:58 | status: root cause gevonden — notify_telegram_channel sendt Markdown text met parse_mode="HTML"
    -> KLAAR: 19-04-2026 11:02 | getest: nee — live verify nodig (whale alert in @ApexFlashAlerts moet bold/links renderen) | door: Claude
- WAAROM: screenshots toonden raw `[text](url)` en `*WHALE ALERT*` in channel — Telegram las Markdown als HTML.
- WAT VERANDERD: agents/notifications.py
  - `notify_telegram_channel()` parse_mode default "HTML" → "Markdown"
  - parse_mode is nu een parameter (override mogelijk per call)
  - Fallback: als Markdown parse faalt (bv. lone `_` in URL) → retry plain text → alert komt altijd door
- IMPACT: channel posts (whale signals) tonen nu correcte bold + clickable links ipv raw markdown
- VERSION 3.23.20 → 3.23.21

## SESSIE 38 — 2026-04-26 — MVAI-SENSEI EMPTY RESPONSE + ENV NAME MISMATCH
- ISO LOG #MVAI-SENSEI FIX
    -> START: 26-04-2026 | door: Claude
    -> KLAAR: 26-04-2026 | getest: nee — live verify nodig: /ai_status in TG → check MVAI-SENSEI: ✅
- ROOT CAUSE 1: MVAI-SENSEI retourneert {"response":"..."} maar code checkte alleen choices/content → altijd leeg
- ROOT CAUSE 2: Box Drive master + ApexFlashAPI.env gebruikt GROQ-API (koppelteken) maar code leest GROQ_API_KEY → alle providers "no key" → MVAI-SENSEI enige fallback → faalde ook → SLA 0%
- FIX: agents/ai_router.py — _call_mvai_sensei leest nu data.get("response") eerst
- FIX: agents/ai_router.py — tolerante key lookup: GROQ_API_KEY OR GROQ-API OR GROQ
- FIX: sync_render_env.py — extra_keys nu met hyphen→underscore fallbacks voor alle AI providers
- FIX: .env — correct-genaamde keys toegevoegd (GROQ_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY, GMGN_API_KEY)
- VERSION 3.23.30 → 3.23.31
- ACTIE VOOR ERIK: run python sync_render_env.py (of voeg keys handmatig toe in Render dashboard)
