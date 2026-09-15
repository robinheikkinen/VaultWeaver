# VaultWeaver

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](merge_json_v4.py)

**Merge two Bitwarden / Vaultwarden vault exports into one — with real conflict resolution, a diff you can review, and a one-command rollback.**

There's no official way to combine two vaults. This exists because that gap is real: you've got one account on Bitwarden.com and another on a self-hosted Vaultwarden instance, and you want one clean vault, not a manual copy-paste marathon.

> **Not affiliated with Bitwarden Inc. or the Vaultwarden project.** VaultWeaver just reads and writes the JSON export format both of them produce.

---

## Why this exists

Search "bitwarden merge duplicates" and you'll find a handful of tools — all of them clean up duplicates **inside one vault export**. None of them merge **two separate vaults** into one. That's the actual problem when you're consolidating accounts or migrating to self-hosted.

| | Merges two separate vaults | Zero install (browser) | Diff / dry-run | Rollback | Conflict policies | Generic JSON support |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **VaultWeaver** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [bitwarden-vault-cleanup](https://github.com/no84by/bitwarden-vault-cleanup) | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| [Bitwarden-Dedupe-Tool](https://github.com/bcalmkid/Bitwarden-Dedupe-Tool) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [bitwarden_find_duplicates](https://github.com/eliasfloreteng/bitwarden_find_duplicates) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [bitwarden-tools](https://github.com/Hannoma/bitwarden-tools) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

*(Comparison based on public README/source as of the tools' latest release. Every one of them is a solid, purpose-built dedup tool — just solving a different problem than the one VaultWeaver solves.)*

---

## Features

- **Browser UI** — drag and drop two files, merge runs entirely client-side. Nothing leaves your computer, ever — no network calls exist in the code.
- **Encrypted export support** (browser, experimental) — decrypts Bitwarden's password-protected "Encrypted JSON" export locally via native WebCrypto (PBKDF2 KDF only — see [Quick start](#quick-start)).
- **CLI** — auto-detects the two JSON files in the current folder; no arguments needed.
- **Bitwarden / Vaultwarden mode** — deep merge with conflict resolution, URI deduplication, password history merge, TOTP handling.
- **Generic JSON mode** — works with any array-of-objects JSON; key fields auto-detected or specified manually.
- **Conflict policies** — `prefer_newer`, `prefer_file1`, `prefer_file2`, or `manual` (flags items for review instead of guessing).
- **Reused-password detection** (CLI) — items sharing a password with another item get flagged `_reused_password=true`, so you catch credential reuse for free while merging. The password value itself is never duplicated anywhere — just a boolean flag.
- **Rationale on manual-review items** (CLI) — `_merge_review_reason` records *why* an item needs a human look (e.g. `password_conflict, notes_conflict`), not just that it does.
- **Diff mode** — see exactly what would change before touching anything.
- **Dry run** — full report, zero writes.
- **Rollback** — one command restores the previous output from its automatic backup.
- **HTML report** — searchable, filterable summary of every change. Sensitive fields never appear — only "Differs (hidden)".
- **Tested** — pytest suite covering conflict logic, dry-run safety, report masking, reused-password flagging, and review rationale; runs on every push via GitHub Actions.

---

## Quick start

### Browser UI (recommended, zero install)

Open [`merge_tool.html`](merge_tool.html) directly in any modern browser (also published as [`index.html`](index.html) for GitHub Pages hosting — same file, same code, nothing hidden).

Supports Bitwarden's password-protected **Encrypted JSON** export too — drop one in and you'll be prompted for the export password, decrypted entirely client-side via the browser's native WebCrypto API. ⚠️ **Experimental:** only the PBKDF2 KDF is supported (not Argon2id — WebCrypto has no native Argon2id, and adding a library would break the zero-dependency design); verified against Bitwarden's published crypto spec and an independent decrypt implementation via a self-test, but not yet against a real Bitwarden-generated file. Test it with your own export before relying on it for a real migration.

1. Drag your two JSON exports onto the drop zones (or click to browse).
2. Pick a conflict policy — `prefer_newer` is the default and usually right.
3. Click **Merge**.
4. Download the merged JSON file.

Or serve it locally instead of double-clicking the file:

```bash
python -m http.server 7432
```

### CLI

Requires Python 3.8+. No pip installs.

```bash
# Auto-detect: if exactly two .json files are in the current folder
python merge_json_v4.py

# Explicit files
python merge_json_v4.py vault1.json vault2.json

# Preview only — writes a report, touches nothing else
python merge_json_v4.py vault1.json vault2.json --dry-run

# See exactly what would change
python merge_json_v4.py vault1.json vault2.json --diff

# Made a mistake? Undo the last merge.
python merge_json_v4.py --rollback
```

<details>
<summary><strong>All CLI options</strong></summary>

| Flag | Default | Description |
|---|---|---|
| `--policy` | `prefer_newer` | `prefer_newer`, `prefer_file1`, `prefer_file2`, `manual` |
| `-o / --output` | `merged_output.json` | Output file path |
| `-r / --report` | `merge_report.html` | HTML report path |
| `--dry-run` | off | Generate report without writing output |
| `--diff` | off | Show diff and exit |
| `--rollback` | — | Restore previous output from backup |
| `--shred-inputs` | off | Overwrite (3 passes) + delete both input files after a successful (non-dry-run) merge — best-effort, see [Security](#security) |
| `--strict-uri` | off | Include port and path in URI comparison (useful for homelab IPs) |
| `--key-fields` | auto | Comma-separated fields identifying records in generic-JSON mode |
| `--sensitive-fields` | — | Extra fields to mask in the HTML report |
| `--items-path` | auto | Dot-notation path to the items array, e.g. `data.records` |
| `--date-field` | auto | Field used for `prefer_newer` in generic mode |
| `-v / --verbose` | off | Print each merged item to the terminal |

```bash
# Generic JSON — any array of objects, not just vault exports
python merge_json_v4.py contacts.json contacts_new.json --key-fields email

# Nested array, e.g. {"data": {"records": [...]}}
python merge_json_v4.py a.json b.json --items-path data.records --key-fields uuid

# Mask extra fields beyond the built-in sensitive-field list
python merge_json_v4.py data1.json data2.json --key-fields id --sensitive-fields pin,recovery_code
```
</details>

---

## How conflicts get resolved

When the same record exists in both files with different values:

| Policy | Behaviour |
|---|---|
| `prefer_newer` | Keeps the value from whichever file has the later `revisionDate` (or equivalent date field) |
| `prefer_file1` | File 1 always wins |
| `prefer_file2` | File 2 always wins |
| `manual` | Both values kept; item flagged with `_merge_review=true` for you to check after import |

After importing into Bitwarden / Vaultwarden, filter on `_merge_review` to find anything that needs a manual look — the `_merge_review_reason` field on the same item tells you *why* (e.g. `password_conflict, notes_conflict`), so you're not guessing what to check.

Separately, any item whose password is reused elsewhere in the merged vault gets `_reused_password=true`, regardless of conflict policy — free credential-hygiene signal, no extra flags needed.

---

## Security

- **No network requests, anywhere.** The browser UI is 100% client-side JS; the CLI is stdlib-only, no `subprocess`, no `eval`.
- **Sensitive fields are never shown.** Passwords, TOTP secrets, tokens, keys — masked as "Differs (hidden)" in every report. Covered by [tests](tests/test_merge_json_v4.py).
- **Atomic writes.** Output is written to a `.tmp` file, then renamed — a crash mid-write can't corrupt your merged vault.
- **Restrictive permissions.** Output, backups, and reports get `chmod 600` on Unix/macOS/Linux.
- **Delete your plaintext exports when you're done.** An unencrypted vault export is a plaintext copy of every secret you own. Run the CLI with `--shred-inputs` to have it overwrite (3 passes) and delete both input files automatically right after a successful merge — or do it manually with your OS's secure-delete tool. Best-effort: on SSDs and copy-on-write filesystems (most modern disks), overwriting a file's logical content doesn't guarantee the physical blocks are wiped due to wear-leveling — treat this as a solid extra layer, not a cryptographic guarantee. The merged output and reports are gitignored by default, but that only protects you from committing them, not from them sitting on disk.
- **Homelab IPs:** by default, URIs are matched by hostname only (port ignored) — fine for public domains, but risky if you self-host many services on the same IP at different ports (`192.168.1.10:8080` and `192.168.1.10:9090` would be treated as "the same site"). Use `--strict-uri` to compare host **and** port. Trade-off: if the same service was saved with a port in one vault and without it in the other, `--strict-uri` won't recognize them as the same login — it'll come through as a new entry instead of a clean merge, so a quick look at `_merge_review`/new-entries in the report is worth it either way.

Found a security issue? Please open an issue rather than a PR containing an exploit — happy to fix it fast.

---

## Vault export / import

Export as **unencrypted JSON**:
- Bitwarden: `Settings → Vault → Export → Format: JSON (unencrypted)`
- Vaultwarden: same path

Import the merged result:
- `Settings → Vault → Import → Format: Bitwarden (JSON)`

> **Note:** Import is additive — it does not delete existing items. If you want to fully replace a vault, empty it first or import into a fresh account.

---

## Development

```bash
python -m pip install pytest
python -m pytest tests/ -v
```

Tests run automatically on every push and PR via GitHub Actions (Python 3.8 / 3.11 / 3.13, Linux + Windows).

---

## Contributing

Issues and PRs welcome — especially around edge cases in real-world vault exports (weird nested custom fields, unusual date formats, etc.). Please don't attach real vault data to an issue; a redacted or synthetic example is enough to reproduce almost anything here.

---

## A few features borrowed from elsewhere

VaultWeaver's core — merging two separate vaults with conflict policies, diff/dry-run/rollback — wasn't inspired by any of the projects below; none of them even solve that problem (they all clean up duplicates *within* one export). But while surveying that space, a handful of small extra features seemed worth adding, and where an idea came from another project, that's credited here (concepts only — no code copied, everything is a fresh implementation with its own tests):

- Reused-password flagging (`_reused_password`) — idea seen in [no84by/bitwarden-vault-cleanup](https://github.com/no84by/bitwarden-vault-cleanup)
- Showing *why* an item needs manual review (`_merge_review_reason`), not just that it does — idea seen in [bcalmkid/Bitwarden-Dedupe-Tool](https://github.com/bcalmkid/Bitwarden-Dedupe-Tool)
- Hosting the same file both locally and on GitHub Pages, so the live version and the source are provably identical — pattern seen in [eliasfloreteng/bitwarden_find_duplicates](https://github.com/eliasfloreteng/bitwarden_find_duplicates)
- The `--shred-inputs` flag — reminder to securely wipe plaintext export files instead of just deleting them, seen in [qyqsoft/Bitwarden-Vault-Cleaner](https://github.com/qyqsoft/Bitwarden-Vault-Cleaner)

---

## Roadmap

See [TODO.md](TODO.md) for full history. Current state: two-vault merge, conflict policies, reused-password flagging, manual-review rationale, `--shred-inputs`, and experimental encrypted-export decryption (browser, PBKDF2 only) are all shipped. No open items beyond what's documented as known limitations above.

---

## License

MIT — see [LICENSE](LICENSE).
