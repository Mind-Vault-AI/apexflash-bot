# ApexFlash Bot — Project Instructions

## VERPLICHT: LEES EERST
1. Box Drive HANDOVER_SESSION.md (file_id: 2160131113318, folder_id: 369272330163)
2. Box Drive DASHBOARD.md (file_id: 2154368375132) — master draaiboek
3. MEMORY.md in dit project's memory directory

## EIGENAAR
Erik — doel: EUR 1M netto voor 29-03-2028. Alle werk dient dit doel.

## WERKWIJZE
- PDCA: geen nieuwe features zonder overleg met Erik
- LEAN: minimale oplossing die werkt, geen over-engineering
- Eerlijk zijn, niet naar de mond praten, FOCUS op het doel
- Na iedere sessie: Box Drive DASHBOARD.md bijwerken
- Bij twijfel: niet doen, eerst overleggen

## KRITIEKE REGELS
- `.python-version` = 3.11.10 (NIET runtime.txt — dat is Heroku!)
- Render PUT /env-vars VERVANGT ALLES — eerst GET, tel (moet 23 zijn), dan PUT
- Na ELKE deploy: Erik moet backup forwarden (geen persistent disk!)
- Procfile overrulet Render dashboard start command
- Code fix != productie fix — check Render env vars!
- NEVER npm install op H: drive — all dev op C:/Users/erik_/projects/

## RENDER
- Service: srv-d6kcjbpaae7s73aadsu0
- API key: rnd_F6SnsNvz5CKtds7WZ3EGwp9xlDGZ
- Env vars: 23 stuks (BOT_TOKEN, ADMIN_IDS, etc.)
- Dashboard: https://dashboard.render.com/worker/srv-d6kcjbpaae7s73aadsu0

## BETAALROUTES (9 actief, alle OK per 10-03-2026)
- Trading fee 1% → FEE_COLLECT_WALLET (4LKQ...uYWi)
- Gumroad Pro $19 (rwauqu) + Elite $49 (unetcl)
- SOL Pro 0.23 + Elite 0.59
- Bitunix (xc6jzk) + MEXC (BPM0e8Rm) + BloFin (b996...)

## BEKENDE BUGS
- BUG-007: Wallet data verloren bij elke deploy (Render geen persistent disk)
  - Workaround: auto-backup + manual restore
  - Fix nodig: Upstash Redis (PDCA)
