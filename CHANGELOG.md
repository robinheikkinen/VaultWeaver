# Changelog

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
