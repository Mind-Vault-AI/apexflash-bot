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
- `.python-version` = 3.14.3 (PATCHED) — **BELANGRIJK**: Python 3.14 vereist library patches in site-packages voor `python-telegram-bot` 22.7.
- Render PUT /env-vars VERVANGT ALLES — eerst GET, tel (moet 23 zijn), dan PUT
- **GODMODE SIGNAL POLICY**: Grade A (2.5%+) and High-Vol Grade B (1.2%+ with $2M+) trades active.
- Zero-Loss Manager: 24/7 autonomous scalper with **Self-Monitoring Heartbeat**.
- CEO Agent: Daily briefings at 08:00 Amsterdam (Gemini 2.5 Flash).

## BEKENDE BUGS
- BUG-014: Python 3.14 compatibility with PTB 22.7.
  - Fix: Hand-patched `_application.py`, `_updater.py`, `_jobqueue.py`, `_extbot.py` in site-packages.
