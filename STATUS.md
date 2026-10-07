# STATUS
Senast uppdaterad: 2026-09-30

## Klart
- Repot publicerat till GitLab (origin) och GitHub (github-remote)
- CLI: grundfunktion, generiskt JSON-läge, --dry-run, --diff, --rollback, --strict-uri, --shred-inputs, flagga återanvända lösenord, rationale-fält
- Browser-UI: design-pass, Warm Graphite/Charcoal+Teal-tema, krypterade PBKDF2-exporter
- Rapport: "Bara i fil 1"-sektion, manuell uteslutning av poster (browser-UI, Bitwarden-läge)
- 29/29 tester gröna, GitHub Actions CI på Python 3.8/3.11/3.13
- Verifierat mot riktig Bitwarden-export (2026-09-15): PBKDF2-dekryptering fungerar end-to-end

## Pågår
- Uncommittade ändringar i merge_json_v4.py, merge_tool.html, index.html, tests/, README.md, TODO.md — ej granskade/committade ännu

## Näst på tur
- Testa merge mot riktig Vaultwarden-export (--dry-run först)
- Eventuellt: manuell uteslutning i CLI (kräver flaggdesign)
