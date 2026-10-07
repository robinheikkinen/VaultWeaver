# Changelog

## v4.1
- Flagga återanvända lösenord (CLI) — `_reused_password=true` på poster som delar lösenord med en annan post
- Rationale-fält vid manuell granskning (CLI) — `_merge_review_reason` listar vilka konflikttyper som triggade granskningen
- `--shred-inputs` — skriver över (3 pass) och raderar båda input-filerna efter en lyckad (icke-dry-run) merge
- `--strict-uri` — inkluderar port och sökväg i URI-jämförelsen, för homelab-IP:n
- Krypterad export-dekryptering (browser, experimentell) — Bitwardens lösenordsskyddade "Encrypted JSON"-export, WebCrypto/PBKDF2 (Argon2id stöds ej)
- "Bara i fil 1, oförändrade"-sektion i rapporten (CLI + browser-UI)
- Manuell uteslutning av poster (browser-UI, Bitwarden-läge) — kryssruta för att utesluta enskilda poster från nedladdningsfilen

## v4.0.0
- Universal merge engine: Bitwarden/Vaultwarden-läge auto-detekteras, generiskt array-of-objects JSON-läge för allt annat
- `--diff`-läge, `--dry-run`, `--rollback`
- Atomiska skrivningar (`.tmp` → `os.replace`), `chmod 600` på output/backup (Unix)
- HTML-rapport med maskade känsliga fält
- Testsvit (pytest) + GitHub Actions CI

## v3
- Bitwarden-specifik merge med URI-deduplicering, lösenordshistorik-merge, TOTP-hantering

## v1–v2
- Första CLI-iterationerna, Bitwarden-only
