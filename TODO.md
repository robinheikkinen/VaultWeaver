# Roadmap

## Klart för lansering
- [x] Ren publik mapp separerad från privata exporter/testdata
- [x] `.gitignore` för publikt repo
- [x] README skrivet om (badges, jämförelsetabell, säkerhetssektion)
- [x] CHANGELOG.md
- [x] Grundtester (pytest) för CLI-kärnlogiken
- [x] GitHub Actions CI som körs på varje push/PR

## Klart: färgpalett låst
- [x] Ljust läge = **Warm Graphite** (varm off-white bas, brandorange accent), mörkt läge = **Charcoal + Teal** (GitHub-mörk bas, turkos accent) — följer `prefers-color-scheme`, ingen egen toggle-knapp än
- [x] Fixade en kontrastbugg som dök upp under jämförelsen: statustexter (filnamn, stat-kort, statusrad) använde hårdkodade ljusa färger som inte syntes mot ljus bakgrund — bytt till temavariabler så grön/gul/röd nu har egna ljus/mörk-varianter
- [x] Rensade bort alla kvarvarande hårdkodade hex-färger i merge_tool.html/index.html till förmån för CSS-variabler, så framtida temaändringar är enkla
- [x] Testat live i båda lägen (color-scheme emulation) — merge, rapport, stat-kort, alla läsbara i både ljust och mörkt

## Klart: design-pass (browser-UI)
- [x] CSS-variabler för konsekvent tema, bättre kontrast/hierarki
- [x] Header med logotyp-badge + "trust pills" (inga nätverksanrop / offline / känsliga fält dolda)
- [x] Emoji-favicon (data-URI, inget nätverksanrop)
- [x] Hover/fokus-states, skuggor, rundade hörn genomgående — mer polerat men samma funktionalitet
- [x] Testat live i browser: merge, rapport, stat-kort — allt renderar korrekt, inga konsolfel

## Nästa omgång (efter första push)
- [x] Flagga återanvända lösenord — `_reused_password=true` på delade lösenord, aldrig själva värdet (se `flag_reused_bw_passwords` i merge_json_v4.py + tester)
- [x] Rationale-fält i rapporten — `_merge_review_reason` listar vilka konflikttyper som triggade manuell granskning
- [x] `index.html` skapad som kopia av `merge_tool.html`, redo för GitHub Pages (Settings → Pages → Deploy from branch → main → /root). **OBS:** manuell kopia — om `merge_tool.html` ändras måste `index.html` uppdateras igen (`cp merge_tool.html index.html`) innan push.
- [x] Flagga återanvända lösenord + rationale-fält speglat i **merge_tool.html**/**index.html** (JS) — testat live i browser: stat-kort visas, statusrad uppdateras, inget lösenordsvärde läcker i rapport-DOM:en
- [x] `--shred-inputs`-flagga — skriver över input-filerna 3 gånger med slumpdata + raderar, bara efter lyckad (icke-dry-run) merge. Testat: körs inte vid `--dry-run`, testat att filerna faktiskt försvinner. **OBS:** best-effort — ingen garanti på SSD/CoW-filsystem, dokumenterat i README.
- [x] Stöd för Bitwardens lösenordsskyddade "Encrypted JSON"-export — implementerat i **merge_tool.html**/**index.html** (browser-UI, WebCrypto/SubtleCrypto). Spec verifierad mot Bitwardens öppna källkod (`bitwarden/sdk-internal`) och en oberoende decrypt-implementation (GurpreetKang/BitwardenDecrypt).
  - **Testat:** självtest i webbläsaren där en export-container byggdes helt oberoende av verktygets egen kod (ren WebCrypto, inte via våra hjälpfunktioner) — `decryptPasswordProtectedExport()` dekrypterade den korrekt (roundtrip matchar exakt), och fel lösenord avvisas korrekt via MAC-verifiering.
  - **VIKTIG BEGRÄNSNING:** endast **PBKDF2**-KDF stöds (kdfType 0). **Argon2id** (kdfType 1, standard för nyare Bitwarden-konton) stöds INTE — WebCrypto saknar Argon2id inbyggt, och ett externt bibliotek hade brutit mot "no dependencies"-regeln. Verktyget ger ett tydligt felmeddelande om det stöter på en Argon2id-export.
  - **INTE testat mot en riktig Bitwarden-genererad fil** — vi har inte tillgång till ett live-konto för att generera en äkta lösenordsskyddad export. Självtestet bevisar att krypto-pusslet (PBKDF2 → HKDF-expand → AES-CBC/HMAC) är internt konsekvent och matchar den publicerade specen, men inte 100% att det är byte-för-byte kompatibelt med en riktig fil. **Testa med en egen riktig export innan ni litar på det för migreringen**, och hör av er om något inte funkar.
  - CLI:t (`merge_json_v4.py`) har fortfarande inget stöd — Python saknar AES i standardbiblioteket, och att lägga till en dependency bryter mot projektregeln.

## Klart: sista avstämningen (2026-09-13)
- [x] Bytte "VaultWeaver v4" → **VaultWeaver** överallt — hittade att det bara var gjort i README/TODO, inte i själva verktyget (`<title>`, `<h1>` i merge_tool.html/index.html, samt CLI:ns banner/description-text i merge_json_v4.py)
- [x] Lagt till kredit-sektion i README ("A few features borrowed from elsewhere") — omskriven efter feedback: ursprungliga "Inspired by"-rubriken antydde felaktigt att HELA verktyget kom från de fyra projekten, när det egentligen bara var 4 specifika småfunktioner vi la till i denna session. Kärnfunktionen (tvåvalv-merge) fanns redan innan vi tittade på konkurrenterna.
- [x] 28/28 tester gröna, index.html = merge_tool.html verifierat identiska efter ändringarna

## Namn
- **VaultWeaver** — permanent, genomgående nu (verktyg + CLI + README)
