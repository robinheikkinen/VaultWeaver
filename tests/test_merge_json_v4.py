"""
Tester för merge_json_v4.py.

Kör: pytest tests/ -v
Ingen riktig valv-data används — bara syntetiska exempel-poster.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "merge_json_v4.py"

sys.path.insert(0, str(ROOT))
import merge_json_v4 as mj  # noqa: E402


# ── Enhetstester: säkerhets- och formatlogik ─────────────────────────────────

@pytest.mark.parametrize("field,expected", [
    ("password", True),
    ("totp", True),
    ("api_key", True),
    ("token", True),
    ("username", False),
    ("name", False),
    ("uri", False),
])
def test_is_sensitive(field, expected):
    assert mj.is_sensitive(field) is expected


def test_is_bitwarden_format_detects_export():
    data = {"items": [{"id": "1", "type": 1, "name": "x"}]}
    assert mj.is_bitwarden_format(data) is True


def test_is_bitwarden_format_rejects_generic_json():
    data = {"users": [{"id": "1", "email": "a@example.com"}]}
    assert mj.is_bitwarden_format(data) is False


def test_is_bitwarden_format_handles_empty_items():
    assert mj.is_bitwarden_format({"items": []}) is True


# ── Enhetstester: konfliktpolicy ─────────────────────────────────────────────

def test_choose_source_prefer_file1_always_wins():
    a, b = {"revisionDate": "2020-01-01T00:00:00Z"}, {"revisionDate": "2030-01-01T00:00:00Z"}
    assert mj.choose_source(a, b, "prefer_file1") == "existing"


def test_choose_source_prefer_file2_always_wins():
    a, b = {"revisionDate": "2030-01-01T00:00:00Z"}, {"revisionDate": "2020-01-01T00:00:00Z"}
    assert mj.choose_source(a, b, "prefer_file2") == "incoming"


def test_choose_source_prefer_newer_picks_later_date():
    older = {"revisionDate": "2020-01-01T00:00:00Z"}
    newer = {"revisionDate": "2030-01-01T00:00:00Z"}
    assert mj.choose_source(older, newer, "prefer_newer") == "incoming"
    assert mj.choose_source(newer, older, "prefer_newer") == "existing"


def test_choose_source_manual_flags_for_review():
    assert mj.choose_source({}, {}, "manual") == "manual"


# ── End-to-end CLI-tester (generiskt JSON-läge, syntetisk data) ─────────────

@pytest.fixture()
def generic_files(tmp_path):
    file1 = tmp_path / "a.json"
    file2 = tmp_path / "b.json"
    file1.write_text(json.dumps([
        {"id": "1", "name": "Alice", "email": "alice@example.com", "revisionDate": "2020-01-01T00:00:00Z"},
        {"id": "2", "name": "Bob", "email": "bob@example.com", "revisionDate": "2020-01-01T00:00:00Z"},
    ]), encoding="utf-8")
    file2.write_text(json.dumps([
        {"id": "1", "name": "Alice", "email": "alice@newmail.example.com", "revisionDate": "2025-01-01T00:00:00Z"},
        {"id": "3", "name": "Carol", "email": "carol@example.com", "revisionDate": "2020-01-01T00:00:00Z"},
    ]), encoding="utf-8")
    return file1, file2


def run_cli(*args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )


def test_dry_run_does_not_write_output(generic_files, tmp_path):
    file1, file2 = generic_files
    output = tmp_path / "out.json"
    result = run_cli(
        str(file1), str(file2), "--key-fields", "id",
        "-o", str(output), "--dry-run", cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert not output.exists()


def test_merge_writes_expected_record_count(generic_files, tmp_path):
    file1, file2 = generic_files
    output = tmp_path / "out.json"
    result = run_cli(
        str(file1), str(file2), "--key-fields", "id",
        "-o", str(output), "-r", str(tmp_path / "report.html"), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    merged = json.loads(output.read_text(encoding="utf-8"))
    # id=1 (mergad), id=2 (bara fil1), id=3 (bara fil2) => 3 poster
    assert len(merged) == 3


def test_prefer_newer_keeps_latest_value(generic_files, tmp_path):
    file1, file2 = generic_files
    output = tmp_path / "out.json"
    run_cli(
        str(file1), str(file2), "--key-fields", "id", "--policy", "prefer_newer",
        "-o", str(output), "-r", str(tmp_path / "report.html"), cwd=tmp_path,
    )
    merged = {item["id"]: item for item in json.loads(output.read_text(encoding="utf-8"))}
    assert merged["1"]["email"] == "alice@newmail.example.com"


def test_cli_end_to_end_flags_reused_password_without_leaking_it(tmp_path):
    secret = "reused-password-value-123"
    file1 = tmp_path / "a.json"
    file2 = tmp_path / "b.json"
    file1.write_text(json.dumps({"items": [
        {"id": "1", "type": 1, "name": "Service A",
         "login": {"username": "a", "password": secret}, "revisionDate": "2020-01-01T00:00:00Z"},
    ]}), encoding="utf-8")
    file2.write_text(json.dumps({"items": [
        {"id": "2", "type": 1, "name": "Service B",
         "login": {"username": "b", "password": secret}, "revisionDate": "2020-01-01T00:00:00Z"},
    ]}), encoding="utf-8")
    output = tmp_path / "out.json"
    report = tmp_path / "report.html"
    result = run_cli(
        str(file1), str(file2), "-o", str(output), "-r", str(report), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    merged = json.loads(output.read_text(encoding="utf-8"))["items"]
    for item in merged:
        names = {f["name"] for f in item.get("fields", [])}
        assert "_reused_password" in names
    assert secret not in report.read_text(encoding="utf-8")


def test_shred_file_overwrites_and_removes(tmp_path):
    f = tmp_path / "secret.json"
    f.write_text('{"password": "correct-horse-battery-staple"}', encoding="utf-8")
    assert mj.shred_file(str(f), passes=1) is True
    assert not f.exists()


def test_shred_file_missing_file_returns_false(tmp_path):
    assert mj.shred_file(str(tmp_path / "does-not-exist.json")) is False


def test_cli_shred_inputs_removes_source_files_after_merge(generic_files, tmp_path):
    file1, file2 = generic_files
    output = tmp_path / "out.json"
    result = run_cli(
        str(file1), str(file2), "--key-fields", "id", "--shred-inputs",
        "-o", str(output), "-r", str(tmp_path / "report.html"), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert not file1.exists()
    assert not file2.exists()
    assert output.exists()


def test_cli_shred_inputs_not_applied_on_dry_run(generic_files, tmp_path):
    file1, file2 = generic_files
    result = run_cli(
        str(file1), str(file2), "--key-fields", "id", "--shred-inputs", "--dry-run",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert file1.exists()
    assert file2.exists()


def test_rollback_without_history_exits_nonzero(tmp_path):
    result = run_cli("--rollback", cwd=tmp_path)
    assert result.returncode != 0


# ── Enhetstester: återanvänt lösenord-flagga ─────────────────────────────────

def test_flag_reused_bw_passwords_flags_shared_password():
    items = [
        {"id": "1", "type": 1, "login": {"password": "shared-secret"}},
        {"id": "2", "type": 1, "login": {"password": "shared-secret"}},
        {"id": "3", "type": 1, "login": {"password": "unique-secret"}},
    ]
    flagged = mj.flag_reused_bw_passwords(items)
    assert flagged == 2
    assert any(f["name"] == "_reused_password" for f in items[0]["fields"])
    assert any(f["name"] == "_reused_password" for f in items[1]["fields"])
    assert "fields" not in items[2] or not any(
        f["name"] == "_reused_password" for f in items[2].get("fields", [])
    )


def test_flag_reused_bw_passwords_ignores_empty_passwords():
    items = [
        {"id": "1", "type": 1, "login": {}},
        {"id": "2", "type": 1, "login": {}},
    ]
    assert mj.flag_reused_bw_passwords(items) == 0


def test_flag_reused_bw_passwords_never_stores_raw_password_in_flag():
    items = [
        {"id": "1", "type": 1, "login": {"password": "shared-secret"}},
        {"id": "2", "type": 1, "login": {"password": "shared-secret"}},
    ]
    mj.flag_reused_bw_passwords(items)
    for item in items:
        flag = next(f for f in item["fields"] if f["name"] == "_reused_password")
        assert flag["value"] == "true"


# ── Enhetstester: manual-review rationale ────────────────────────────────────

def test_manual_policy_adds_rationale_field():
    existing = {"login": {"password": "old-pw"}, "notes": "a", "revisionDate": "2020-01-01T00:00:00Z"}
    incoming = {"login": {"password": "new-pw"}, "notes": "b", "revisionDate": "2025-01-01T00:00:00Z"}
    merged, diff = mj.bw_merge_item(existing, incoming, policy="manual")
    names = {f["name"]: f["value"] for f in merged["fields"]}
    assert names.get("_merge_review") == "true"
    assert "password_conflict" in names.get("_merge_review_reason", "")
    assert "notes_conflict" in names.get("_merge_review_reason", "")


def test_report_never_shows_raw_sensitive_values(tmp_path):
    file1 = tmp_path / "a.json"
    file2 = tmp_path / "b.json"
    secret_old, secret_new = "correct-horse-battery-staple", "totally-different-secret"
    file1.write_text(json.dumps([
        {"id": "1", "name": "svc", "password": secret_old, "revisionDate": "2020-01-01T00:00:00Z"},
    ]), encoding="utf-8")
    file2.write_text(json.dumps([
        {"id": "1", "name": "svc", "password": secret_new, "revisionDate": "2025-01-01T00:00:00Z"},
    ]), encoding="utf-8")
    report = tmp_path / "report.html"
    result = run_cli(
        str(file1), str(file2), "--key-fields", "id",
        "-o", str(tmp_path / "out.json"), "-r", str(report), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    html = report.read_text(encoding="utf-8")
    assert secret_old not in html
    assert secret_new not in html
