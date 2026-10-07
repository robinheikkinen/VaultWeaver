# VaultWeaver

A security-focused tool for merging two Bitwarden / Vaultwarden JSON vault exports — or any two JSON files containing arrays of records. No official merge feature exists in Bitwarden/Vaultwarden; this fills that gap.

Not affiliated with Bitwarden Inc. or the Vaultwarden project.

---

## Status

Public-facing repo, not yet pushed to GitHub/GitLab. See [README.md](README.md) for features and usage, [TODO.md](TODO.md) for what's done vs. planned, [CHANGELOG.md](CHANGELOG.md) for version history.

This started as a private tool (`merge_json_v4.py`, originally at `merge_json_v4` in a private repo) and was spun out into this standalone, public-ready repo with tests, CI, and a UI pass added on top.

---

## Architecture

| Component | File | Purpose |
|---|---|---|
| CLI merger | `merge_json_v4.py` | Primary CLI tool (Python 3.8+, stdlib only) |
| Browser UI | `merge_tool.html` | Client-side JS, no server required |
| GitHub Pages mirror | `index.html` | Identical copy of `merge_tool.html` — **must be manually re-synced** (`cp merge_tool.html index.html`) after any edit to the browser UI |
| Tests | `tests/test_merge_json_v4.py` | pytest, run with `python -m pytest tests/ -v` |
| CI | `.github/workflows/tests.yml` | Runs tests on push/PR, Python 3.8/3.11/3.13, Linux + Windows |

Data flow: two JSON exports → deduplication + conflict resolution → merged JSON + HTML report.

---

## Tech Stack

- **Python 3.8+** — no external packages, stdlib only
- **Vanilla JavaScript** — browser UI runs entirely client-side, no network requests (the one exception: WebCrypto's native SubtleCrypto API for the experimental encrypted-export decryption — still zero external dependencies)
- **JSON** — Bitwarden unencrypted export format (`items` array); supports generic array-of-objects JSON too

---

## Security Rules

- Never show sensitive fields (passwords, TOTP, tokens, keys) in reports — only "Differs (hidden)".
- Output files use `chmod 600` permissions on Unix.
- Atomic writes via `.tmp` → rename to prevent corruption on crash.
- No subprocess calls, no `eval`, no network requests (CLI or browser).
- Browser UI is 100% client-side — vault data never leaves the machine.
- `--shred-inputs` (CLI) overwrites + deletes input files after a successful merge — best-effort, not a guarantee on SSD/CoW filesystems.

## Known limitations (be upfront about these, don't quietly "fix" by guessing)

- Encrypted-export decryption (browser only) supports **PBKDF2 KDF only**, not Argon2id — WebCrypto has no native Argon2id and adding a library would break the zero-dependency design.
- Encrypted-export decryption has been verified against Bitwarden's published crypto spec via a self-test, but **not against a real Bitwarden-generated file** — flag this if asked about it.
- No support for Bitwarden folders/collections/tags — only login-level fields (password, TOTP, URIs, notes, custom fields) are merged.

---

## Rules for AI Assistance

- Do not add network requests or external dependencies to CLI or browser UI.
- Do not log or display raw sensitive field values.
- Preserve atomic write behavior when modifying file output logic.
- Python target: 3.8+ with stdlib only — no pip dependencies.
- Generic JSON mode must remain functional alongside Bitwarden-specific logic.
- After editing `merge_tool.html`, always re-sync `index.html` (`cp merge_tool.html index.html`) — they must stay byte-identical.
- After editing `merge_json_v4.py` or the HTML tool, run `python -m pytest tests/ -v` before considering the change done.
- Never test against real vault data. Use synthetic/example records only, even for manual verification.

## Session hygiene
Before I run /clear or end a session: update STATUS.md (done / in 
progress / next) before ending.
At the start of a new session: read STATUS.md first. If missing or 
empty, ask me what we're working on instead of guessing.
