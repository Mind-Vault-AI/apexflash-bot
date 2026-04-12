# ApexFlash Bot — CLAUDE.md (Single Source of Truth)
> Laatste update: 2026-04-13 (sessie 29)

---

## ⛔ STOP — LEES DIT EERST. GEEN UITZONDERINGEN.

**STAP 1 — Lees nu direct dit bestand volledig:**
```
C:/Users/erik_/projects/apexflash-bot/NOW.md
```
Dit bevat: wat open staat, wat gedaan is, waar te starten. **Zonder dit lezen: NIETS uitvoeren.**

**STAP 2 — Maak een plan op basis van NOW.md → notuleer als todo list**

**STAP 3 — Uitvoeren, stuk voor stuk, direct markeren als done**

**STAP 4 — Na IEDERE wijziging: NOW.md bijwerken + git commit**

**STAP 5 — Sessie afsluiten: "VOLGENDE SESSIE — START HIER" bijwerken in NOW.md**

### MEMO (Erik's wet — nooit overtreden):
- UPDATE = VOORUITGANG, NOOIT ACHTERUITGANG
- ALLES SYNCHROON NA IEDERE WIJZIGING (Redis · Git · Render · NOW.md)
- PDCA 99.9% SLA — testen VOOR opleveren, niet erna
- MAIN GOAL: EUR 1.000.000 netto vóór 29-03-2028

### SECRETS SSOT (altijd hier ophalen, nooit hardcoden):
| Locatie | Inhoud |
|---------|--------|
| `C:/Users/erik_/Box/MEGA BOT/MASTER_ENV_APEXFLASH.txt` | Alle bot secrets (leidend) |
| `C:/Users/erik_/.config/gmgm/.env` | GMGN API + private key |
| `C:/Users/erik_/Box/08_OPERATIONS/8.1_ApexFlash_Bot/.env` | ISO9001 backup copy |
| Sync naar Render: | `python C:/Users/erik_/projects/apexflash-bot/sync_render_env.py` |

---

---

## EIGENAAR & DOEL
- **Erik** — doel: EUR 1.000.000 netto vóór 29-03-2028
- Telegram ID: 7851853521 | Admin: enige gebruiker
- Filosofie: LEAN · PDCA · FOCUS · Eerlijk · Geen BS

---

## PROJECT LOCATIES (ALTIJD ACTUEEL)
| Component | Lokaal pad | Render service |
|---|---|---|
| **Bot** (Python) | `C:/Users/erik_/projects/apexflash-bot/` | `srv-d6kcjbpaae7s73aadsu0` |
| **Site** (Next.js) | `C:/Users/erik_/projects/apexflash-app/` | `srv-d6k5voh5pdvs73dsru5g` |
| **BigFish Watcher** | `C:/Users/erik_/source/repos/bigfish-watcher/` | Docker Desktop (lokaal) |
| **GMGN keys** | `C:/Users/erik_/.config/gmgm/` | Render: GMGN_* env vars |
| **Master env** | `C:/Users/erik_/Box/MEGA BOT/MASTER_ENV_APEXFLASH.txt` | sync via `sync_render_env.py` |
| **Memory** | `C:/Users/erik_/.claude/projects/.../memory/` | — |

---

## HUIDIGE STATUS (update dit na elke sessie)
| Item | Waarde |
|---|---|
| **Bot versie** | v3.23.x (Render live) — commit 2ed7717 (2026-04-13) |
| **Site versie** | commit 9f9d13a — Bitunix social proof live |
| **Python** | 3.14.3 — **HAND-GEPATCHED** (zie sectie Python 3.14) |
| **Render env vars bot** | 74 keys (gesynchroniseerd 2026-04-12) |
| **Render env vars site** | 12 visible + secret group |
| **autotrade:enabled** | 1 (Redis) — bot handelt autonoom |
| **Open posities** | 7: POPCAT/PNUT/FARTCOIN/MEW/JUP/WIF/GOAT |
| **GMGN scanner** | ⚠️ 403 op Render — IP whitelist fix: `/myip` in Telegram |
| **DexScreener fallback** | ✅ actief als backup scan |
| **DISCORD_WEBHOOK_URL** | ❌ leeg — Erik actie vereist |
| **TEST_TRADE_SOL** | 0 → PRODUCTIE (geen cap) |
| **AUTONOMOUS_TRADE_AMOUNT_SOL** | 0.05 SOL (~EUR 5/trade) |
| **Redis** | Upstash Frankfurt — apparent-wildcat-76903.upstash.io |

---

## KRITIEKE REGELS — NUL TOLERANTIE

### Env Vars (3x gebrand)
- **Render PUT /env-vars VERVANGT ALLES** — altijd `sync_render_env.py` gebruiken, NOOIT handmatig PUT
- Procedure: GET → tel keys → voeg toe → PUT volledige lijst → GET verificatie
- NOOIT secrets/values tonen in output of chat — alleen key namen + aanwezig/ontbreekt

### Code
- `ast.parse()` + import check VOOR elke git push
- Testen met zowel volledige als afgekorte adressen
- Debug messages verwijderen voor productie

### Sessie
- Dit bestand lezen = sessie gestart, direct bouwen
- NOOIT vragen wat te doen als het hier staat
- Na sessie: dit bestand bijwerken (status sectie)

### Deploy
- Render events checken na push — server_failed binnen 5 min = kritiek
- Na deploy: heartbeat check, test mint address

---

## PYTHON 3.14 — KRITIEK
Render draait Python **3.14.3**. PTB 22.7 is NIET compatibel zonder patches.

**Hand-gepatched bestanden in site-packages:**
- `_application.py`
- `_updater.py`
- `_jobqueue.py`
- `_extbot.py`

`.python-version` = `3.14.3` (dit bestand stuurt Render, NIET runtime.txt)

**BUG-005 / BUG-014:** Python 3.14 enforceert striktere `__slots__` regels voor PTB 22.7. Patches zijn aangebracht in de Render deployment. Niet aanpassen zonder dit te begrijpen.

---

## BOT ARCHITECTUUR (v3.23.0)

### Hoofd bestanden
| File | Doel |
|---|---|
| `bot.py` | Main bot — commands, handlers, startup |
| `start.py` | Render entry point — conflict cleanup + isolatie |
| `sync_render_env.py` | Env var sync naar Render (gebruik dit altijd) |
| `zero_loss_manager.py` | 24/7 autonome scalper (Zero-Loss engine) |
| `scalper.py` | Token momentum monitor (17 tokens) |
| `gumroad.py` | Gumroad subscription sync |
| `sentiment.py` | CryptoBERT signal grading (A/B/C/D) |
| `whale_intent.py` | Whale intent detection |
| `diagnose.py` | Diagnostic tool |

### Core (`/core/`)
| File | Doel |
|---|---|
| `config.py` | Alle env vars + constanten (VERSION hier) |
| `i18n.py` | Internationalisatie |
| `persistence.py` | Redis/JSON opslag + KPI functies |
| `wallet.py` | Solana wallet + Token2022 support |

### Agents (`/agents/`)
| Agent | Doel |
|---|---|
| `ceo_agent.py` | Dagelijkse briefing 08:00 AMS (Gemini 2.5) |
| `inspector_agent.py` | Alpha wallet tracking (60s polling) |
| `news_scanner.py` | War Watch geopolitiek scanner (10 min) |
| `whale_watcher.py` | Whale Intelligence v2.0 + GMGN smart_degen scoring |
| `viral_agent.py` | Autonome Reddit posting |
| `marketing_agency.py` | Marketing automation + Gumroad→Discord queue |
| `social_manager.py` | Social media management |
| `social_marketing_agent.py` | AI social content |
| `advisor_agent.py` | Trading advice agent |
| `conversion_agent.py` | Conversie optimalisatie |
| `notifications.py` | Discord/Telegram alerts |
| `twitter_poster.py` | Twitter auto-post (3x/dag: 09:00/15:00/21:00) |
| `marketing.py` | Marketing utilities |
| `video_agent.py` | Video content agent |
| `viral_hooks.py` | Viral content hooks |

### Exchanges (`/exchanges/`)
| File | Doel |
|---|---|
| `jupiter.py` | Jupiter DEX swap execution (Solana) |
| `chains.py` | ETH/SOL whale tracking |
| `whale_copy.py` | Whale copy trading module |
| `mizar.py` | Mizar API integratie |
| `evm_trader.py` | EVM chain trading |
| `arbitrage_scanner.py` | Arbitrage scanner |

---

## GODMODE SIGNAL POLICY
- **Grade A**: 2.5%+ signal → actief handelen
- **High-Vol Grade B**: 1.2%+ met $2M+ volume → actief handelen
- **Zero-Loss Manager**: breakeven-lock op 0.5%, TP 2.0%, SL 1.0%
- **Shock Breaker**: als Panic Score > 85 → halt new buys + tighten SL to 0.5%
- **AUTONOMOUS_TRADE_AMOUNT_SOL**: 0.05 SOL/trade (verhoog naar 0.1 als win rate >65%)

### Systemen 24/7 actief
- Zero-Loss Manager (auto_trader_loop)
- CEO Agent briefing (dagelijks 08:00 AMS)
- War Watch (elke 10 min)
- Inspector Gadget (elke 60s)
- SL Monitor (elke 15s)
- Twitter auto-post (3x/dag)
- Heartbeat (elke 4h naar Erik)
- Gumroad sync (elke 15 min)

---

## GMGN INTEGRATIE
- **API Key**: `gmgn_69ed2f741906301ebd076b2016522044` → Render: `GMGN_API_KEY`
- **Private key** (Ed25519): `C:/Users/erik_/.config/gmgm/id_ed25519` → Render: `GMGN_PRIVATE_KEY`
- **Public key**: `C:/Users/erik_/.config/gmgm/Public_key.txt` → Render: `GMGN_PUBLIC_KEY`
- **Wallet**: `CsgcvMXFfLTZm8u8a6Eds1GnUXTcpPHV7Cho5ueUApvi` → Render: `GMGN_WALLET_ADDRESS`
- **Trusted IP**: `86.88.183.115` → Render: `GMGN_TRUSTED_IP`
- **Referral**: `cBB5zbUF` (10% commissie) → Render: `GMGN_REF`
- **whale_watcher.py**: gebruikt GMGN smart_degen scoring voor Whale Intelligence v2.0

---

## REVENUE STREAMS (actief)
| Stream | Commissie | Code/Route |
|---|---|---|
| Jupiter trade fee | 1% per swap | FEE_COLLECT_WALLET |
| Bitunix affiliate | 50% | `xc6jzk` |
| MEXC affiliate | 70% | `BPM0e8Rm` |
| BloFin affiliate | 50% | `b996a0111c1b4497b53d9b3cc82e4539` |
| Gate.com affiliate | 30% | `VFFHXVFDUG` |
| GMGN.ai affiliate | 10% | `cBB5zbUF` |
| Gumroad Pro | $9.99/mo | `rwauqu` |
| Gumroad Elite | $29.99/mo | `unetcl` |
| Mizar referral | — | `mizar.com/?ref=apexflash` |

---

## BEKENDE BUGS & STATUS
| Bug | Status |
|---|---|
| BUG-016: env vars gewist door Render PUT | ✅ OPGELOST — sync_render_env.py |
| BUG-017: SELL button werkte niet na restart | ✅ OPGELOST — mint in callback_data |
| BUG-018: Token2022 0 balance (uiAmount=null) | ✅ OPGELOST — wallet.py fallback |
| BUG-014: Python 3.14 / PTB 22.7 incompatibiliteit | ✅ OPGELOST — hand-patches |
| BUG-008: BONK token lookup inconsistent | OPEN — niet kritiek |
| /api/ceo 404 op site | OPEN — Next.js routing issue |

---

## ERIK'S ACTIES (handmatig)
1. **BigFish Docker starten** — `docker compose up -d` in `bigfish-watcher/`
2. **AUTONOMOUS_TRADE_AMOUNT_SOL verhogen** → 0.1 of 0.25 als win rate >65%
3. **OKX API key** — passphrase `OkX_ApI=13!` hebben, key + secret nog ophalen
4. **Bybit/Binance affiliate** — aanvragen bij exchanges
5. **Reddit post plaatsen** — draft klaar in handover

---

## VERBODEN (juridisch)
- **Polymarket** — KSA officieel verbod NL (feb 2026), €420k/week boete
- **ETFs/TradFi executie** — MiFID II + AFM licentie vereist

---

## LEAN CHECKLIST (vóór elke push)
- [ ] Is het meetbaar?
- [ ] Is het legaal?
- [ ] Elimineert het waste?
- [ ] Draagt het bij aan EUR 1M?
- [ ] ast.parse() geslaagd?
- [ ] Import check geslaagd?
- [ ] Render events na deploy gecontroleerd?
