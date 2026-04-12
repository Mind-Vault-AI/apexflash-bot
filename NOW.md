<!-- markdownlint-disable MD013 MD022 MD025 MD032 MD058 MD060 -->
<!-- cspell:disable -->

# ApexFlash Bot â€” CURRENT STATUS
# Last updated: 2026-04-12 (Sessie 26)
# MAIN GOAL: EUR 1.000.000 netto vÃ³Ã³r 29-03-2028

## LIVE STATE
- Render service: srv-d6kcjbpaae7s73aadsu0
- Version: v3.23.3
- Global release: R2026.04.11.01
- Keys on Render: 74

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

## VOLGENDE SESSIE â€” START HIER
1. /whale_intel â†’ verwacht eerste GMGN signals binnen 5 min na restart
2. /pdca â†’ PDCA journal start leeg; na 1h eerste outcomes
3. apexflash.pro â†’ About page, CEO API route, favicon herstel
4. Groei: Twitter auto-post Grade A signals, Discord webhook, Reddit outreach
5. WHALE_AUTO_TRADE=true zetten als eerste results positief zijn

## OPENSTAAND
- About page, CEO API, favicon (apexflash-app) nog niet hersteld
- WHALE_AUTO_TRADE staat op false (veilig) â€” aanzetten na PDCA validatie
