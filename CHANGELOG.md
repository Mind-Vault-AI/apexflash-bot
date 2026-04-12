# ApexFlash Bot — CHANGELOG
<!-- ISO 9001 SSOT: every version change is logged here -->
<!-- Format: ## [version] YYYY-MM-DD — one-line summary -->
<!-- Rule: bump VERSION file + bot.py VERSION constant on every release -->

## [3.23.3] 2026-04-12
- docs: CHANGELOG.md created — full version history + VERSION rules (ISO 9001)
- chore: bot.py VERSION constant synced via bump_version.ps1

## [3.23.2] 2026-04-11
- chore: sync VERSION file + bot.py constant (both now 3.23.2)
- fix: zero_loss_manager.py — clean imports, optional aiohttp guard, MAX_TRADE_SOL/MAX_DAILY_TRADES, load/save_active_positions

## [3.23.1] 2026-04-11
- fix: ISO9001 pre-commit guard, secrets hardening, release tag R2026.04.11.01

## [3.23.0] 2026-04-11 — Whale Intelligence + PDCA
- feat: agents/whale_watcher.py v2.0 — GMGN smart_degen scoring (Grade S/A/B), auto-execute
- feat: agents/trade_journal.py — PDCA engine, log signal → check 1h outcome → WIN/LOSS stats
- feat: bot.py — /whale_intel + /pdca commands, whale scanner in post_init, Telegram callback
- feat: Discord webhook for Grade A/S signals (agents/whale_watcher.py)
- feat: Twitter/X auto-post for Grade A/S signals
- feat: Helius + GMGN smart_degen live data in whale scanner

## [3.22.x] 2026-04-10
- feat: GMGN Market API client (exchanges/gmgn_market.py) — rank, trenches, wallet stats
- feat: GMGN Trade API client (exchanges/gmgn.py) — swap, quote, order + Ed25519 signing
- feat: Jupiter primary → GMGN fallback in zero_loss_manager.execute_trade()
- feat: AI Router Cerebras slot-2 (Groq→Cerebras→Gemini→OpenRouter→Nebius→DeepSeek)
- fix: Gemini model names — gemini-2.5-flash, gemini-1.5-flash (deprecated models removed)
- fix: show all AI Router errors (not just last 4)
- feat: GMGN_WALLET_ADDRESS in core/config.py

## [3.22.0] 2026-04-09 — CEO Agent + Arbitrage + Inspector
- feat: CEO Agent (agents/ceo_agent.py) — daily KPI report, governance, auto-pause
- feat: Inspector Agent — alpha wallet tracking, copy-trade signals
- feat: Arbitrage Scanner
- feat: Social Marketing Agency (Discord + Twitter auto-post)
- feat: War Watch news scanner (NewsAPI + CryptoPanic)

## VERSION RULES (ISO 9001)
- MAJOR.MINOR.PATCH — all three files MUST match: VERSION file, bot.py VERSION=, NOW.md
- PATCH: bugfix, refactor, config change
- MINOR: new feature or module
- MAJOR: breaking change or full rebuild
- On every commit: run python sync_render_env.py if env vars changed
