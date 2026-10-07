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
  - **[x] VERIFIERAT mot en riktig Bitwarden-genererad fil (2026-09-15):** testat med en riktig lösenordsskyddad export (`kdfType: 0` / PBKDF2, kontot använder PBKDF2 SHA-256 som KDF — bekräftat under Inställningar → Säkerhet → Nycklar). Dekrypterades korrekt och mergades: 15 mergade poster, 96 nya, 767 exakta kopior ignorerade. Fungerar alltså på riktigt, inte bara i självtest.
  - **VIKTIG DISTINKTION upptäckt under testet:** Bitwarden/Vaultwarden har två olika "krypterade export"-lägen som lätt blandas ihop — (1) **"Encrypted" med kontots egen krypteringsnyckel** (knuten till master-lösenordet, inte ett exportlösenord) — stödjs INTE och kommer aldrig stödjas (samma risk-resonemang som Argon2id-beslutet), och (2) **"Password protected"/lösenordsskyddad** (eget engångs-exportlösenord, ger `kdfType`-fältet) — det är den vi faktiskt stödjer. Värt att förtydliga i README så folk inte testar fel exportläge och tror verktyget är trasigt.
  - CLI:t (`merge_json_v4.py`) har fortfarande inget stöd — Python saknar AES i standardbiblioteket, och att lägga till en dependency bryter mot projektregeln.

## Klart: sista avstämningen (2026-09-13)
- [x] Bytte "VaultWeaver v4" → **VaultWeaver** överallt — hittade att det bara var gjort i README/TODO, inte i själva verktyget (`<title>`, `<h1>` i merge_tool.html/index.html, samt CLI:ns banner/description-text i merge_json_v4.py)
- [x] Lagt till kredit-sektion i README ("A few features borrowed from elsewhere") — omskriven efter feedback: ursprungliga "Inspired by"-rubriken antydde felaktigt att HELA verktyget kom från de fyra projekten, när det egentligen bara var 4 specifika småfunktioner vi la till i denna session. Kärnfunktionen (tvåvalv-merge) fanns redan innan vi tittade på konkurrenterna.
- [x] 28/28 tester gröna, index.html = merge_tool.html verifierat identiska efter ändringarna

## Klart: full transparens i rapporten (2026-09-15)
- [x] Ny sektion **"Bara i fil 1, oförändrade"** i rapporten (CLI + browser-UI) — listar poster som fanns i fil 1 men aldrig matchade något i fil 2 (varken exakt dubblett eller merge-kandidat). Tidigare osynliga i rapporten trots att de räknades in i totalen. Nytt stat-kort "Bara i fil 1" i båda gränssnitten.
- [x] Testat: pytest (29/29 gröna, inkl. nytt test `test_run_bitwarden_merge_reports_file1_only_items`), riktig CLI-körning (grep:ad HTML-rapport), och live i browser (verifierat att delade/mergade poster INTE dyker upp i fel sektion)

## Klart: manuell uteslutning av poster (2026-09-15)
- [x] Ny funktion i **browser-UI:t** (bara Bitwarden-läge — kräver stabilt `id`-fält): kryssruta "Ta bort" på varje post i "Mergade", "Nya poster från fil 2" och "Bara i fil 1"-sektionerna. Kryssar man i en post utesluts den direkt från nedladdningsfilen — ingen ny merge-körning behövs, filen byggs om live.
- [x] Visuell feedback: uteslutna poster tonas ner + genomstrykning, plus en räknare ("X poster uteslutna från nedladdningen") ovanför nedladdningsknappen.
- [x] Tänkt användning: rensa bort gamla homelab-IP:n, utgångna lösenord eller annat skräp som inte ska följa med till den nya valv-filen, utan att behöva redigera JSON:en manuellt efteråt.
- [x] Testat live i browser (inte bara kod-granskning): kryssade i en post, verifierade via fetch mot den nedladdningsbara blob-URL:en att posten faktiskt saknas i output, att övriga poster finns kvar, och att avbockning återställer den korrekt.
- **Begränsning:** bara browser-UI, bara Bitwarden-läge. CLI:t och det generiska JSON-läget har inte fått funktionen (skulle kräva ett sätt att ange vilka poster som ska uteslutas via kommandorad — inte byggt ännu).

## Namn
- **VaultWeaver** — permanent, genomgående nu (verktyg + CLI + README)
