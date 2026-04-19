# ApexFlash Bot — CHANGELOG
<!-- ISO 9001 SSOT: every version change is logged here -->
<!-- Format: ## [version] YYYY-MM-DD — one-line summary -->
<!-- Rule: bump VERSION file + bot.py VERSION constant on every release -->

## [3.23.22] 2026-04-19 — Deep-link SLA fix + KPI self-heal + sell diagnostics
### fix: Elite/Pro deep-link handlers (SLA breach root cause)
- `/start elite` and `/start pro` now route to a 1-tap upgrade screen (were silently falling through to default welcome → SLA breach on `t.me/ApexFlashBot?start=elite` observed 2026-04-19 12:11 UTC)
- New funnel tracking keys: `funnel:deeplink_elite:YYYY-MM-DD`, `funnel:deeplink_elite_shown`, `funnel:deeplink_pro*` for conversion measurement

### fix: KPI drift "new baseline" (dual-source-of-truth)
- Root cause: `auto_backup` reads in-memory `users` dict ("6 users") while `CEO briefing` reads Redis counters (`platform:total_users`, `platform:trades_today`) which were either never written (`trades_today`) or reset across deploys → every day CEO briefing showed "0 (new baseline)"
- `core/persistence.py::reconcile_kpis()` — rebuilds aggregate counters from the authoritative users dict, upwards-only for monotonic counters, overwrite for daily ones
- `agents/ceo_agent.py::run_briefing()` — calls reconcile_kpis() before collect_kpis(); if drift > 10% sends loud Telegram alert (option B) with before/after values for full ISO9001 audit trail

### feat: Sell diagnostic ring buffer + /sell_diag admin command
- `_log_sell_event()` pushes every sell outcome (success/fail + reason + mint) to Redis ring buffer `apexflash:sell_diag` (last 30)
- Instrumented 4 failure paths: `token_not_found_3x`, `zero_balance`, `quote_no_route`, `quote_api_error`, `swap_execute_failed`
- New admin command `/sell_diag` shows last 30 events + success-rate summary + top failure reasons — eliminates the need to pull Render logs for sell-bug triage

### chore
- VERSION 3.23.17 → 3.23.22 (syncs bot.py constant with VERSION file; catches ISO9001 drift from 3.23.18–3.23.21 unpushed bumps)

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
