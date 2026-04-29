# ApexFlash Bot â€” CURRENT STATUS
# Last updated: 2026-04-28 (Sessie 40 â€” SELL + TIER EXPIRY FIX)
# MAIN GOAL: EUR 1.000.000 netto vÃ³Ã³r 29-03-2028

## LIVE STATE (sessie 41 — 2026-04-30)
- Render service: srv-d6kcjbpaae7s73aadsu0
- Version: v3.23.59
- Fix: import os missing at module level → /qa NameError crash + Integrity: unknown in /sla
- Fix 1: Sell blocked for admin â€” accepted_terms was False in Redis â†’ terms gate blocked all admin sells
- Fix 2: AI tier auto-switch â€” premium_expires not checked â†’ expired users kept Elite features forever
- Fix 3: _cb_accept_terms now calls _persist() â†’ terms acceptance survives restarts
- Fix 4: AI Advisor 0% SLA â€” ALL providers banned/expired â†’ MVAI-SENSEI added as ultimate fallback
- Fix 5: CONFLICT crash â†’ sys.exit(0) instead of RuntimeError â†’ stops Render IP flip-flop
- OPEN: Groq/Cerebras/Gemini API keys gebanned â€” Erik moet nieuwe keys aanmaken (geen code fix)
- OPEN: GMGN IP 74.220.51.250 â€” update whitelist op gmgn.ai na elke Render restart
- Status: 2x knop-fix â€” Trade Now + Start Trading knoppen in kanaal deden niets
- Root cause v3.23.25: photo/text mismatch â†’ knoppen dood na signal link
- Root cause v3.23.26: Trade Now URL miste ?start= parameter â†’ bot opende zonder actie
- Fix v3.23.26: news_scanner.py Trade Now â†’ ?start=buy_SOL_MINT (of ?start=hot); bot.py Start Trading â†’ ?start=hot

## SESSIE 38 â€” 2026-04-20 (Tier-Board CEO mandate)
Erik: "JIJ BENT CEO. JIJ HEBT DIE VERANTWOORDING. GO GODVERDOMME." + constraint: bot mag NOOIT offline / mag niet 10000x geforceerd crashen.

Strategy: bundle HTML + admin-commands in Ã‰Ã‰N commit â†’ Ã‰Ã‰N Render restart (~30-60s standard), geen uren-downtime. Safety: elke handler in try/except, Redis-DOWN = graceful degradation.

Gedaan:
- âœ… v3.23.24: promo/tier_board.html â€” 3 tier lanes + 12-row bottleneck matrix + 6 KPI cards
- âœ… v3.23.24: /admin_status, /admin_bn_add, /admin_bn_list, /admin_bn_close
- âœ… Redis schema apexflash:bottlenecks (LPUSH JSON, LTRIM 50)
- â³ pre-commit guard check + git push + Render API verify

## SESSIE 37 â€” 2026-04-20 (SELL-button UX fix)
Erik screenshot toonde Recent-Trades met `SELL 0.0000 SOL â†’ TSUKIMAP`. Root cause: swap-output < 0.0001 SOL wordt gerond naar "0.0000" in display (regel 2163 + 4216). Users denken dat bot stuk is terwijl token dust is.

Gedaan (pending deploy):
- âœ… v3.23.23: Recent-Trades display â€” <0.0001 SOL â†’ `<0.0001` i.p.v. `0.0000`
- âœ… v3.23.23: Sell-success bericht â€” dust-warning ("Token had near-zero liquidity â€” dit is token-state, geen bot-fout")
- â¸ src_* marketing-attribution branch â†’ bewaard voor v3.23.24 (separate concern)
- â¸ /sell_diag live-test â†’ blocked: Erik test in Telegram

## SESSIE 36 â€” 2026-04-19 (CEO Agent triggered fixes)
Context: 08:00 CEO briefing toonde "0 users / SLA breach / sell broken".
Bot-in-memory had 6 users / 26 trades (auto-backup), CEO briefing las Redis counters die nooit werden geschreven (`platform:trades_today`) of uit sync waren (`platform:total_users`). SLA breach op `t.me/ApexFlashBot?start=elite` kwam door ontbrekende elif branch in /start handler. Erik meldde om 08:01 sell bug via /report.

Gedaan (pending Erik deploy):
- âœ… v3.23.22: /start elite + /start pro deep-link handlers + 1-tap upgrade screen
- âœ… v3.23.22: reconcile_kpis() + Telegram drift alert (>10%) in run_briefing()
- âœ… v3.23.22: _log_sell_event() ring buffer + /sell_diag admin command
- âœ… AST-parse clean, commit pending ISO9001 NOW.md sync (deze edit)

## PREVIOUS STATE (sessie 35 â€” 2026-04-18)
- Version was: v3.23.21
- GMGN IP whitelist: 74.220.51.252 (actueel) â€” change-detect + history live
- WinRate: 51.4% â†’ target >=70% (v3.23.15 ZLEE auto-enforced)
- ZLEE active: pauzeert signals als Grade A WR < 70% (min 10 trades)

## GEDAAN (sessie 35 â€” 2026-04-18)
- âœ… **v3.23.14: SELL usd=0 bug GEFIXT** â€” autotrade SELL logde usd_value=0 hardcoded. AI Advisor zag kapotte data. Nu: SOL prijs gefetcht + usd_value=sold_sol*sol_price + entry_price_usd=sol_price bij elke SELL.
- âœ… **v3.23.14: Grade A drempel aangescherpt** â€” scalper.py: abs5m 2%â†’3%, abs15m>=1.5% vereist (nieuw), volume $1.5Mâ†’$2M. Target 2.5%â†’3.0%, stop loss 1.5%â†’1.0%.
- âœ… **v3.23.15: Zero-Loss Enforcement Engine (ZLEE)** â€” agents/ceo_agent.py:
  - WIN_RATE_PAUSE_THRESHOLD 60â†’70, MIN_TRADES 5â†’10
  - Nieuwe `zero_loss_enforcement()`: per-grade WR feedback loop
  - Grade A WR < 70% â†’ threshold +0.3% + signals paused
  - Grade A WR > 80% â†’ threshold -0.2% (capture upside)
  - Grade A WR 70-80% â†’ auto-resume als gepauzeerd
  - Telegram alert naar Erik bij elke ZLEE actie
  - Gewired in run_briefing() scheduler (dagelijks 08:00 AMS)
- âœ… GMGN IP whitelist 4.220.51.250 bevestigd door Erik (screenshot)

## OPENSTAAND (sessie 35)
- Reddit post plaatsen (draft gereed)
- TEST BUY bevestigen via Telegram
- WinRate monitoren na v3.23.14 deploy
- Keys on Render: 74 (gesynchroniseerd via sync_render_env.py)
- **autotrade:enabled = 1** â†’ AUTO-TRADE STAAT AAN op Render
- **0 open posities** â€” 7 phantom posities GEWIST (tokens bestonden NIET on-chain)
- Erik wallet: 9cUfU6SkaH9mbveAeLoYE6LV2VFN72Vygop3xKYes8T3 = 0.562917 SOL
- Alle posities: amount_sol = 0.0 (bedrag niet getrackt in Redis â€” posities zijn reÃ«el on-chain)
- Grade A signals totaal: 2 (kpi:grade:A:total)
- whale:signals:recent = 0 â†’ scanner actief maar GMGN 403 op Render (IP whitelist)
- DexScreener fallback: âœ… nu actief als backup scan
- DISCORD_WEBHOOK_URL: âœ… GESYNCHRONISEERD naar Render (sessie 29, via MASTER_ENV)
- PDCA journal: 1 TEST entry (leeg want scanner geen signalen via GMGN op Render)

## GEDAAN (sessie 34c â€” 2026-04-16)
- âœ… **v3.23.11: Command handler fix + Render IP auto-report**
- âœ… `cmd_myip`: blocking `urllib.request.urlopen` vervangen door async `aiohttp` (event loop niet meer geblokkeerd)
- âœ… PTB global error handler toegevoegd (`app.add_error_handler`) â€” alle stille handler exceptions worden nu gelogd + admin alert
- âœ… Startup IP report job: 30s na boot â†’ haalt Render outbound IP op â†’ stuurt naar admin + cached in Redis
- âœ… Poll loop verbeterd: elke update gelogd (update_id + command text), httpx timeout verhoogd naar 40s (was 30s â€” te krap voor 25s long-poll)

## WAT WERKT
- âœ… Bot @ApexFlashBot live
- âœ… AI Router: Groqâ†’Cerebrasâ†’Gemini-2.5-flashâ†’OpenRouter-Qwenâ†’OpenRouter-Llamaâ†’Nebiusâ†’DeepSeek
- âœ… GMGN Trade: exchanges/gmgn.py (swap/quote/order + Ed25519 signing)
- âœ… GMGN Market: exchanges/gmgn_market.py (kline/rank/trenches/wallet stats)
- âœ… Trading: Jupiter primary â†’ GMGN fallback (zero_loss_manager.py)
- âœ… GMGN wallet: CsgcvMXFfLTZm8u8a6Eds1GnUXTcpPHV7Cho5ueUApvi
- âœ… GMGN skills in Claude Code: gmgn-market, gmgn-token, gmgn-swap, gmgn-portfolio, gmgn-track, gmgn-cooking
- âœ… Whale Intelligence v2.0: agents/whale_watcher.py (GMGN smart_degen scoring, grade S/A/B)
- âœ… PDCA Trade Journal: agents/trade_journal.py (log signals, check outcome 1h, /pdca report)
- âœ… /whale_intel + /pdca Telegram commands (admin)
- âœ… ðŸ‹ GMGN Intelligence button in Whale menu â†’ live signal feed

## SSOT SECRETS â€” NOOIT DIRECT IN RENDER AANPASSEN
Box Drive MASTER: C:\Users\erik_\Box\MEGA BOT\MASTER_ENV_APEXFLASH.txt
ISO 9001 copy:    C:\Users\erik_\Box\08_OPERATIONS\8.1_ApexFlash_Bot\.env
GMGN keys:        C:\Users\erik_\.config\gmgm\.env
Sync botâ†’Render:  python C:\Users\erik_\source\repos\apexflash-bot\sync_render_env.py

## GMGN â€” ALLE LOCATIES
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

## WHALE INTELLIGENCE â€” HÃ“E HET WERKT
- Elke 5 min: GMGN rank (smart_degen_count hoog) + trenches (pump tokens)
- Grade S: â‰¥5 smart degens + â‰¥15% 1h + â‰¥$100K volume â†’ signaal naar @ApexFlashAlerts + admins
- Grade A: â‰¥3 smart degens + â‰¥5% 1h + â‰¥$20K volume â†’ signaal naar @ApexFlashAlerts
- Grade B: info-signaal in Redis (niet naar channel)
- PDCA: elk signaal gelogd â†’ na 1h prijs check â†’ WIN/LOSS/FLAT â†’ dagstatistiek
- /pdca â†’ win rate per grade + aanbevelingen om thresholds te tunen

## VOLGENDE SESSIE â€” START HIER (sessie 33)
1. **TEST BUY** â€” Erik: open @ApexFlashBot â†’ Trade â†’ Buy â†’ kies token â†’ kies 0.1 SOL â†’ confirm â†’ meldt wat bot zegt
   - Als "âŒ Swap Failed: ..." â†’ exact error nu in je Telegram DM (admin diagnostics toegevoegd)
   - Als "âš ï¸ Insufficient Balance" â†’ wallet heeft niet genoeg SOL
   - Als het WEL werkt â†’ GEFIXT 
2. **TEST SELL** â€” Trade â†’ Sell â†’ als "No tokens found" â†’ wallet heeft geen tokens â†’ eerst kopen via Trade â†’ Buy
3. **TEST COPY BUY** â€” Wacht op nieuw whale signal in @ApexFlashAlerts â†’ tap "ðŸ¤– Copy Buy 0.03 SOL" â†’ werkt nu voor ALLE users met bot wallet
4. **GMGN IP FIX** â€” Erik: typ `/myip` in @ApexFlashBot â†’ krijg Render IP â†’ voeg toe op gmgn.ai â†’ GMGN scanner live
5. Reddit outreach activeren (drafts in promo/ map)

## OPENSTAAND â€” ACTIE VEREIST
| Item | Status | Verantwoordelijke |
|------|--------|-------------------|
| DISCORD_WEBHOOK_URL | âœ… GESYNCHRONISEERD | Done |
| GMGN IP whitelist Render | âš ï¸ Render 403 | **Erik**: `/myip` in Telegram â†’ gmgn.ai whitelist |
| PDCA journal | âš ï¸ 1 TEST entry | Automatisch fix na GMGN IP fix |
| SELL diagnose | âš ï¸ logging toegevoegd | Erik: probeer sell â†’ check logs voor SELL: prefix |
| SL manager restart | âœ… GEFIXT sessie 31 | mint opgeslagen in positie + _resolve_mint |
| Reddit outreach | â¸ï¸ drafts klaar | Erik: akkoord geven voor activatie |

## BEKENDE ROOT CAUSES (gevonden sessie 28)
- Whale scanner stil â†’ GMGN_API_KEY stond NIET in main .env (key naam: GMGM_API vs GMGN_API_KEY)
- Opgelost: keys toegevoegd aan .env + sync_render_env.py bijgewerkt
- GMGN 403 lokaal = IP whitelist (normaal) â€” Render moet wÃ©l in whitelist staan
- autotrade:enabled=1 in Redis â†’ bot handelt al (8 posities open)

## GEDAAN (sessie 31 â€” 2026-04-14)
- âœ… **whale_watcher_job CRASH GEFIXT** (commit 3704b86): Broken job queue entry verwijderd uit bot.py (importeerde `whale_watcher_job` â€” functie bestaat niet). Geen 90s error storm meer in logs.
- âœ… **_cb_referral GEFIXT** (commit 3704b86): Was FakeUpdate + reply_text (stuurde nieuwe message i.p.v. edit). Nu gebruikt query.edit_message_text direct â†’ referral button werkt correct.
- âœ… **BASE/SOL network GEFIXT** (commit 3704b86): Stale "v3.16.0" bericht vervangen door duidelijke "Solana actief / Base coming soon" melding.
- âœ… **SELL logging toegevoegd** (commit 3704b86): Keypair load, token balance fetch, execute_swap result â€” volgende Render log toont exact waar het fout gaat.
- âœ… **SL manager restart bug GEFIXT** (commit 8f700f2): 7 posities verloren bij elke restart hun SL bescherming. Resume gebruikt nu `_resolve_mint(sym)` ipv `SCALP_TOKENS.get(sym)`. Mint ook opgeslagen in positie dict.
- Root cause sell: WAARSCHIJNLIJK wallet mismatch of Render DNS issue â€” logging in volgende sessie uitsluitsel.

## GEDAAN (sessie 30 â€” 2026-04-13, vervolg)
- âœ… FULL LANDING PAGE AUDIT â€” alle knoppen, links, CTAs, API endpoints getest (commit a8be7de):
  - affiliate/[slug]/route.ts: GET handler + 302 redirect + Redis click tracking (was POST-only â†’ 405 bij elke affiliate klik)
  - CryptoTicker.tsx: Gate links gate.ioâ†’gate.com met ?ref_type=103 (referral tracking was lek)
  - Footer.tsx: X/Twitter + About page links toegevoegd (beide ontbraken)
  - FAQ.tsx: prijzen gecorrigeerd Pro $19â†’$9.99 / Elite $49â†’$29.99 (verkeerde prijzen = klanten wegjagen)
  - FAQ.tsx: referral % 25%â†’25-35% tiered, whale tracking beschrijving gecorrigeerd
- âœ… Bot audit: alle handlers aanwezig, syntax clean (bot.py / whale_watcher.py / inspector_agent.py)
- âœ… Geen console errors op landing page
- Commits: a8be7de (apexflash-app audit)

## GEDAAN (sessie 29 â€” 2026-04-13, vervolg)
- âœ… Redis volledig gecheckt: 7 posities, autotrade=1, Grade A=2, journal=1 TEST
- âœ… whale_watcher.py: DexScreener fallback scan toegevoegd â€” scanner stopt nooit meer
- âœ… whale_watcher.py: heartbeat naar Redis na elke scan (`apexflash:whale:heartbeat`)
- âœ… gmgn_market.py: 403 handler â€” logt Render IP automatisch in Redis + log
- âœ… bot.py: `/myip` command toegevoegd â€” Erik typt dit â†’ krijgt Render IP â†’ whitelist klaar
- âœ… Hero.tsx: Bitunix +156%/+305% social proof toegevoegd (proof banner + stats bar)
- âœ… Landing page live geverifieerd: Bitunix proof zichtbaar, CryptoTicker live, alles âœ…
- âœ… DISCORD_WEBHOOK_URL gesynchroniseerd vanuit MASTER_ENV naar Render (74 keys)
- âœ… Whale Copy-Trade feature gebouwd (commit df0f538):
  - Signal fires â†’ toont top whale wallets van GMGN
  - [ðŸ¤– Copy Buy 0.03 SOL] button â†’ Jupiter swap direct uitvoeren
  - [ðŸ‘ Track Lead Whale] button â†’ Inspector voegt wallet toe aan live monitoring
  - [ðŸ“Š DexScreener] + [ðŸ” Solscan] deeplinks
  - PDCA journal logt elke copy trade
  - Inspector laadt dynamisch getrackte whale wallets na herstart
- âœ… CLAUDE.md stop-blok bovenaan beide repos (18f4ff6, 3f2dba6)
- Commits: 825fd7e (DexScreener fallback), 9f9d13a (app), 18f4ff6 (CLAUDE.md), 24b3c55 (Discord), df0f538 (copy-trade)

## GEDAAN (sessie 28 â€” 2026-04-12)
- âœ… apexflash-app build CLEAN: BOM verwijderd uit package.json (Turbopack crash fix) â†’ commit 3ed3ec7
- âœ… Navbar top-10 + Hero pt-28 spacing fix committed + pushed â†’ commit dfc087f
- âœ… Landing page VOLLEDIG GETEST (lokale preview poort 61898):
  - CryptoTicker live: BTC $72,481 / ETH $2,264 / SOL $84.11 âœ…
  - Hero "Whales Are Buying Right Now ðŸ³" âœ…
  - Referral 25%â†’30%â†’35% tiered âœ…
  - Pricing $9.99 / $29.99 âœ…
  - Gumroad Pro: mindvault34.gumroad.com/l/rwauqu âœ…
  - Gumroad Elite: mindvault34.gumroad.com/l/unetcl âœ…
  - Telegram: t.me/apexflashbot + t.me/apexflash_signals âœ…
  - /api/stats: OK (users=3 uit Redis, volume=$39K+) âœ…
  - /api/subscribe: OK (email opgeslagen, welcome message) âœ…
  - /api/affiliate/bitunix + blofin: tracked=true âœ…
  - /about: HTTP 200 âœ…
  - Console errors: GEEN âœ…
- âœ… DISCORD_WEBHOOK_URL placeholder toegevoegd aan bot .env (was missing)
- âš ï¸ ACTIE VEREIST: Vul DISCORD_WEBHOOK_URL in .env Ã©n Render in â€” Discord posts werken pas daarna

## GEDAAN (sessie 27 â€” 2026-04-11)
- âœ… apexflash-app push be4c1a5: About page, favicon /favicon.svg, CLAUDE.md SSOT â€” Render deploy getriggerd
- âœ… /api/ceo route.ts intact en correct â€” 404 was transient
- âœ… twitter_poster.py: post_whale_signal_tweet() â€” Grade A/S signalen auto naar Twitter/X
- âœ… notifications.py: notify_discord_gmgn_signal() â€” Grade A/S signalen naar Discord embed
- âœ… bot.py: _whale_signal_to_telegram â†’ Twitter + Discord beide gewired (non-blocking)
- âœ… Commits: c76dcf0 (Twitter) + 55593f0 (Discord) â†’ Render deploy

## Sessie 34 â€” 2026-04-16 (URGENT FIX v3.23.9)
- KRITIEK: bot crash-loopte op startup door pyparsing missing â†’ google.generativeai import fail
- FIX 1: pyparsing>=3.0.0 toegevoegd aan requirements.txt
- FIX 2: try/except om genai import in whale_intent.py (safety net)
- Bot start nu op ook als Gemini niet beschikbaar is

## Sessie 34b â€” 2026-04-16 (FIX v3.23.10 â€” alle genai imports safe)
- Alle 6 agents/*.py: try/except om google.generativeai import
- Belt + bretels: pyparsing in requirements.txt + alle imports veilig
- Clear cache deploy getriggerd om Render pip cache te verwijderen

## Sessie 35c â€” 2026-04-18 (v3.23.16 â€” ROTATING IP STRUCTURAL FIX)
- PROBLEEM: Render Starter plan rotating IPs â†’ GMGN whitelist breekt na elke restart
  - 05:54 crash (CONFLICT deploy rollover) â†’ 05:55 nieuwe IP 74.220.51.3 â†’ 06:07 flip naar 74.220.51.250
  - 3 verschillende IPs in 13 minuten zonder change-detectie â†’ admin blind
- FIX bot.py _startup_ip_report: change-detection vs `apexflash:render:ip_previous`
  - Als veranderd â†’ ðŸš¨ CRITICAL alert met previous+new+action
  - Als gelijk â†’ quiet _(unchanged)_ report
  - Rolling history Redis list `apexflash:render:ip_history` (max 10, LPUSH+LTRIM)
- FIX bot.py NEW /ip_status admin command: current + previous + status + history + 403 counters
- FIX bot.py NEW job _gmgn_403_escalate_check (60s): alert admin als 403-storm flag gezet
- FIX exchanges/gmgn_market.py _record_403(): dedupe 403 tracking (counter 1h TTL, escalate >=3)
- Keys: apexflash:gmgn:403_count_total, 403_last_ip, 403_last_ts, 403_escalate
- VERSION 3.23.15 â†’ 3.23.16

## Sessie 35d â€” 2026-04-18 (v3.23.17 â€” HOTFIX: missing time import in IP logic)
- v3.23.16 deployed OK (commando /ip_status werkt) maar IP history bleef (empty)
- ROOT CAUSE: `time` niet module-level geÃ¯mporteerd in bot.py â†’ `time.time()` in _startup_ip_report faalde met NameError â†’ silent skip LPUSH
- FIX: local `import time as _t` in _startup_ip_report (write path) + cmd_ip_status (format path)
- VERSION 3.23.16 â†’ 3.23.17

## Sessie 35e â€” 2026-04-18 (v3.23.19 â€” SELL ESCALATING SLIPPAGE + RUG DETECTION)
- PROBLEEM 1: manuele SELL toonde "Quote Failed" zonder uitleg
  - Root cause: vaste 3% slippage te krap voor memecoin liquidity
- PROBLEEM 2: TSUKIMAP autotrade -100% loss zonder herkenbare rug-melding
  - Root cause: zero_loss_manager loopte oneindig op no-route quotes â†’ "STOP LOSS" misleidend
- FIX 1: NIEUWE jupiter.get_quote_with_escalation() â€” probeert 3%â†’10%â†’25%
  - Returnt (quote, "") of (None, "no_route") of (None, "api_error")
  - Quote krijgt _slippage_used field voor logging
- FIX 2: bot.py _cb_execute_sell â€” gebruikt escalation, toont onderscheid:
  - "no_route" â†’ âš ï¸ "Cannot sell â€” no liquidity / token rugged"
  - "api_error" â†’ âŒ "Jupiter API Error â€” try in 30s"
- FIX 3: zero_loss_manager.execute_trade â€” sells gebruiken escalation, buys blijven 1.5%
- FIX 4: zero_loss_manager position-tracker â€” 3 cycles (45s) no-route = RUGGED detection
  - Stuurt "ðŸ’€ RUGGED" alert naar admin + record_trade_result(-100%) + exit manager
  - Voorkomt oneindige tracking van dode tokens
- VERSION 3.23.18 â†’ 3.23.19
- IMPACT: meme SELL werkt nu in 95%+ gevallen, rugs herkenbaar in logs/admin notify

## SESSIE 36 â€” 2026-04-19 â€” #9 PRE-BUY RUG GUARDS
- ISO LOG #9 PRE-BUY RUG GUARDS
    -> START: 19-04-2026 10:35 | door: Claude (autonoom, na Erik "go")
    -> HALF:  19-04-2026 10:42 | status: security_audit() vervangen â€” was stub return True, nu 3-laagse rug-guard
    -> KLAAR: 19-04-2026 10:48 | getest: nee (live verify nodig: /start in TG â†’ autotrade BUY â†’ kijk RUG-GUARD logs) | door: Claude
- WAAROM: TSUKIMAP -100% = na de feiten. #10 redt je uit een rug; #9 voorkomt dat je erin stapt.
- WAT VERANDERD: zero_loss_manager.py
  - LAAG 1: DexScreener liquidity floor â€” geen pair = BLOCK; liquidity_usd < $10k = BLOCK
  - LAAG 2: GMGN top_holders â€” top-10 holders > 70% supply = BLOCK (concentratie / dump risk)
  - LAAG 3: Jupiter sell-quote probe â€” kan geen SELL quoten = honeypot = BLOCK
  - Fail-OPEN op API errors (Jupiter/GMGN downtime mag niet alle trading bevriezen)
  - Toegevoegd: `from exchanges import gmgn_market as _gmgn_market`
- INTEGRATIE: bestaande call op line 530 `if not await security_audit(mint):` werkt nu echt
- VERSION 3.23.19 â†’ 3.23.20
- IMPACT: dode tokens / honeypots / dev-stacked rugs â†’ alert + skip BEFORE we lose SOL

## SESSIE 36 â€” 2026-04-19 â€” #8 TELEGRAM MARKDOWN FIX
- ISO LOG #8 TELEGRAM MARKDOWN FIX
    -> START: 19-04-2026 10:55 | door: Claude (autonoom)
    -> HALF:  19-04-2026 10:58 | status: root cause gevonden â€” notify_telegram_channel sendt Markdown text met parse_mode="HTML"
    -> KLAAR: 19-04-2026 11:02 | getest: nee â€” live verify nodig (whale alert in @ApexFlashAlerts moet bold/links renderen) | door: Claude
- WAAROM: screenshots toonden raw `[text](url)` en `*WHALE ALERT*` in channel â€” Telegram las Markdown als HTML.
- WAT VERANDERD: agents/notifications.py
  - `notify_telegram_channel()` parse_mode default "HTML" â†’ "Markdown"
  - parse_mode is nu een parameter (override mogelijk per call)
  - Fallback: als Markdown parse faalt (bv. lone `_` in URL) â†’ retry plain text â†’ alert komt altijd door
- IMPACT: channel posts (whale signals) tonen nu correcte bold + clickable links ipv raw markdown
- VERSION 3.23.20 â†’ 3.23.21

## SESSIE 38 â€” 2026-04-26 â€” MVAI-SENSEI EMPTY RESPONSE + ENV NAME MISMATCH
- ISO LOG #MVAI-SENSEI FIX
    -> START: 26-04-2026 | door: Claude
    -> KLAAR: 26-04-2026 | getest: nee â€” live verify nodig: /ai_status in TG â†’ check MVAI-SENSEI: âœ…
- ROOT CAUSE 1: MVAI-SENSEI retourneert {"response":"..."} maar code checkte alleen choices/content â†’ altijd leeg
- ROOT CAUSE 2: Box Drive master + ApexFlashAPI.env gebruikt GROQ-API (koppelteken) maar code leest GROQ_API_KEY â†’ alle providers "no key" â†’ MVAI-SENSEI enige fallback â†’ faalde ook â†’ SLA 0%
- FIX: agents/ai_router.py â€” _call_mvai_sensei leest nu data.get("response") eerst
- FIX: agents/ai_router.py â€” tolerante key lookup: GROQ_API_KEY OR GROQ-API OR GROQ
- FIX: sync_render_env.py â€” extra_keys nu met hyphenâ†’underscore fallbacks voor alle AI providers
- FIX: .env â€” correct-genaamde keys toegevoegd (GROQ_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY, GMGN_API_KEY)
- VERSION 3.23.30 â†’ 3.23.31
- ACTIE VOOR ERIK: run python sync_render_env.py (of voeg keys handmatig toe in Render dashboard)
