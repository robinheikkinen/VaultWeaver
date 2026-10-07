"""
merge_json_v4.py — VaultWeaver
============================================
Fungerar med Bitwarden/Vaultwarden-exporter OCH godtyckliga JSON-filer.

ANVÄNDNING:
  # Bitwarden/Vaultwarden (auto-detekteras):
  python3 merge_json_v4.py vault1.json vault2.json

  # Generisk JSON — ange nyckelfält:
  python3 merge_json_v4.py users1.json users2.json --key-fields id
  python3 merge_json_v4.py contacts.json new.json --key-fields email
  python3 merge_json_v4.py a.json b.json --key-fields name,email

  # Nästlad array:
  python3 merge_json_v4.py a.json b.json --items-path data.records --key-fields uuid

  # Alternativ:
  python3 merge_json_v4.py f1.json f2.json --policy prefer_newer --dry-run
  python3 merge_json_v4.py f1.json f2.json --diff
  python3 merge_json_v4.py --rollback

SÄKERHET:
  - Känsliga fält (password, secret, token, key …) maskeras alltid i rapporten
  - Utdatafiler sätts till 600-rättigheter (Unix) direkt vid skapandet
  - Filskrivning är atomisk (tmp + os.replace) — skyddar mot korruption vid avbrott
  - Inga känsliga värden loggas till terminal eller rapport

Python 3.8+, inga externa paket.
"""

import copy
import json
import os
import shutil
import argparse
import sys
import stat
from datetime import datetime
from urllib.parse import urlparse


# ── Konstanter ────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT = "merged_output.json"
DEFAULT_REPORT = "merge_report.html"
STATE_FILE     = ".merge_state.json"

# Fältnamn som automatiskt maskeras i rapporten oavsett format
SENSITIVE_PATTERNS = frozenset([
    "password", "passwd", "secret", "token", "key", "pin", "totp",
    "credential", "auth", "apikey", "api_key", "private", "passphrase",
    "otp", "mfa", "ssn", "cvv", "cvc", "masterpassword",
])

# Fält som används för att auto-detektera nyckel i generisk JSON
_ID_FIELDS   = ["id", "uuid", "guid", "_id"]
_NAME_FIELDS = ["name", "title", "label", "username", "email", "login", "slug"]
_DATE_FIELDS = [
    "updatedAt", "updated_at", "modifiedAt", "modified_at",
    "revisionDate", "lastModified", "last_modified", "timestamp", "modified",
]


# ── Säkerhetsverktyg ──────────────────────────────────────────────────────────

def _secure_chmod(path):
    """Sätter 600-rättigheter (owner r/w only). No-op på Windows."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (AttributeError, NotImplementedError, OSError):
        pass


def is_sensitive(field_name):
    lower = str(field_name).lower()
    return any(p in lower for p in SENSITIVE_PATTERNS)


def shred_file(path, passes=3):
    """
    Skriver över filen med slumpdata innan den tas bort, istället för en vanlig delete.
    Best-effort: på SSD/CoW-filsystem (Windows ReFS, journaling, wear-leveling) finns
    ingen garanti att gamla block faktiskt skrivs över fysiskt — se det som ett extra
    lager, inte en kryptografisk garanti.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "r+b", buffering=0) as f:
            for _ in range(passes):
                f.seek(0)
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
        os.remove(path)
        return True
    except OSError:
        return False


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Filen saknas: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Atomisk skrivning via tmp-fil + os.replace. Sätter 600 på tmp innan swap."""
    dir_ = os.path.dirname(os.path.abspath(path))
    tmp  = os.path.join(dir_, f".{os.path.basename(path)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _secure_chmod(tmp)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def backup_file(path):
    if os.path.exists(path):
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.{ts}.bak"
        shutil.copy2(path, backup_path)
        _secure_chmod(backup_path)
        return backup_path
    return None


def save_state(output_path, backup_path):
    state = {
        "timestamp":   datetime.now().isoformat(),
        "output_file": output_path,
        "backup_file": backup_path,
    }
    save_json(STATE_FILE, state)


def do_rollback():
    if not os.path.exists(STATE_FILE):
        print("Ingen merge-historik hittad. Kör en merge först.")
        sys.exit(1)
    state  = load_json(STATE_FILE)
    backup = state.get("backup_file")
    output = state.get("output_file")
    ts     = state.get("timestamp", "?")
    if not backup or not os.path.exists(backup):
        print(f"Backup-fil saknas: {backup}")
        sys.exit(1)
    shutil.copy2(backup, output)
    _secure_chmod(output)
    print(f"✓ Rollback klar. Återställde {output} från backup ({ts})")
    os.remove(STATE_FILE)


# ── Formatdetektering ─────────────────────────────────────────────────────────

def is_bitwarden_format(data):
    """Känner igen Bitwarden/Vaultwarden JSON-export."""
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, list):
        return False
    if not items:
        return True
    return isinstance(items[0], dict) and "type" in items[0]


def find_items_array(data, items_path=None):
    """
    Hittar arrayen av poster i en JSON-fil.
    Returnerar (items_list, array_key_or_None).
    array_key används för att rekonstruera output-strukturen.
    """
    if items_path:
        parts = items_path.split(".")
        node  = data
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                raise ValueError(
                    f"--items-path '{items_path}': hittade inte '{p}' i strukturen"
                )
        if not isinstance(node, list):
            raise ValueError(
                f"--items-path '{items_path}': pekar inte på en array"
            )
        return node, items_path

    if isinstance(data, list):
        return data, None

    if isinstance(data, dict):
        best_key = None
        best_len = -1
        for k, v in data.items():
            if isinstance(v, list) and len(v) > best_len:
                if not v or isinstance(v[0], dict):
                    best_len = len(v)
                    best_key = k
        if best_key is not None:
            return data[best_key], best_key

    raise ValueError(
        "Hittade ingen array av objekt. Använd --items-path för att peka ut rätt array."
    )


def auto_detect_key_fields(items):
    if not items:
        return []
    sample = items[0]
    for f in _ID_FIELDS:
        if f in sample:
            return [f]
    found = [f for f in _NAME_FIELDS if f in sample]
    return found[:2]


def auto_detect_date_field(items):
    if not items:
        return None
    sample = items[0]
    for f in _DATE_FIELDS:
        if f in sample:
            return f
    return None


# ── Gemensamma hjälpare ───────────────────────────────────────────────────────

def normalize_text(v):
    return str(v or "").strip()


def normalize_lower(v):
    return normalize_text(v).lower()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def choose_source(existing, incoming, policy, date_field="revisionDate"):
    if policy == "prefer_file1":
        return "existing"
    if policy == "prefer_file2":
        return "incoming"
    if policy == "prefer_newer":
        dt_e = parse_dt(existing.get(date_field))
        dt_i = parse_dt(incoming.get(date_field))
        if dt_e and dt_i:
            return "incoming" if dt_i > dt_e else "existing"
        return "incoming" if (dt_i and not dt_e) else "existing"
    return "manual"


# ── Generisk merge-motor ──────────────────────────────────────────────────────

def generic_fingerprint(item):
    return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)


def generic_key(item, key_fields):
    return tuple(normalize_lower(item.get(f)) for f in key_fields)


def generic_merge_item(existing, incoming, policy, date_field, extra_sensitive):
    """
    Jämför alla fält och tillämpar policy vid konflikt.
    Returnerar (merged_item, diff_log).
    Muterar inte existing eller incoming.
    """
    merged   = copy.deepcopy(existing)
    diff     = []
    all_keys = set(existing.keys()) | set(incoming.keys())

    for field in sorted(all_keys):
        if field == date_field:
            continue

        val_e = existing.get(field)
        val_i = incoming.get(field)

        if val_e == val_i:
            continue

        sensitive = is_sensitive(field) or field in extra_sensitive

        if field not in existing:
            merged[field] = copy.deepcopy(val_i)
            diff.append({"type": "field_added", "field": field, "sensitive": sensitive})
            continue

        if field not in incoming:
            continue

        decision = choose_source(existing, incoming, policy, date_field or "")
        diff.append({
            "type":      "field_conflict",
            "field":     field,
            "old":       "***" if sensitive else val_e,
            "new":       "***" if sensitive else val_i,
            "decision":  decision,
            "sensitive": sensitive,
        })
        if decision == "incoming":
            merged[field] = copy.deepcopy(val_i)

    if date_field:
        dt_e = parse_dt(existing.get(date_field))
        dt_i = parse_dt(incoming.get(date_field))
        if dt_i and (not dt_e or dt_i > dt_e):
            merged[date_field] = incoming[date_field]

    if any(c.get("decision") == "manual" for c in diff):
        merged["_merge_review"] = "true"

    return merged, diff


def run_generic_merge(items1, items2, args, key_fields, date_field, extra_sensitive):
    merged_map = {}
    for item in items1:
        merged_map.setdefault(generic_key(item, key_fields), []).append(copy.deepcopy(item))

    report = _empty_report(args.policy, len(items1), len(items2))

    def dn(item):
        for f in key_fields:
            v = item.get(f)
            if v:
                return str(v)
        return str(item)[:60]

    def safe_preview(item):
        parts = []
        for k, v in list(item.items())[:4]:
            if not is_sensitive(k) and k not in extra_sensitive:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    for item in items2:
        k          = generic_key(item, key_fields)
        candidates = merged_map.get(k, [])
        fp         = generic_fingerprint(item)

        if not candidates:
            if not args.dry_run:
                merged_map.setdefault(k, []).append(copy.deepcopy(item))
            report["stats"]["new_entries_from_file2"] += 1
            report["new_entries"].append({"display_name": dn(item),
                                          "fields_preview": safe_preview(item), "uris": []})
            continue

        matched = False
        for idx, existing in enumerate(candidates):
            if generic_fingerprint(existing) == fp:
                report["stats"]["exact_duplicates"] += 1
                matched = True
                break

            merged_item, diff = generic_merge_item(
                existing, item, args.policy, date_field, extra_sensitive
            )
            if not args.dry_run:
                candidates[idx] = merged_item

            if diff:
                name = dn(existing)
                report["stats"]["merged_entries"] += 1
                report["merged_changes"].append({"display_name": name, "changes": diff})
                if any(c.get("decision") == "manual" for c in diff):
                    report["stats"]["conflicted_entries"] += 1
                    report["manual_review"].append({"display_name": name, "changes": diff})

            matched = True
            break

        if not matched:
            if not args.dry_run:
                merged_map[k].append(copy.deepcopy(item))
            report["stats"]["new_entries_from_file2"] += 1
            report["new_entries"].append({"display_name": dn(item),
                                          "fields_preview": safe_preview(item), "uris": []})

    return [item for lst in merged_map.values() for item in lst], report


# ── Bitwarden/Vaultwarden merge-motor ─────────────────────────────────────────

def _bw_login(item):
    return item.get("login") or {}


def _bw_norm_uri(uri, strict=True):
    raw = normalize_lower(uri)
    if not raw:
        return ""
    inp = raw if "://" in raw else f"http://{raw}"
    try:
        p = urlparse(inp)
    except Exception:
        return raw
    host = (p.hostname or "").lower()
    port = p.port
    path = (p.path or "").rstrip("/")
    if not host:
        return raw
    if port in (80, 443):
        port = None
    if strict:
        r = host + (f":{port}" if port else "") + (path if path else "")
        return r
    return host


def _bw_uri_objects(item, strict=True):
    out = []
    for u in (_bw_login(item).get("uris") or []):
        if isinstance(u, dict) and u.get("uri"):
            out.append({"uri": u["uri"],
                        "normalized": _bw_norm_uri(u["uri"], strict),
                        "match": u.get("match")})
    return out


def _bw_uri_set(item, strict=True):
    return sorted({u["normalized"] for u in _bw_uri_objects(item, strict) if u["normalized"]})


def _bw_fields_map(item):
    result = {}
    for f in (item.get("fields") or []):
        name = normalize_text(f.get("name"))
        if name:
            result[name] = {"value": f.get("value"), "type": f.get("type")}
    return result


def bw_exact_fingerprint(item):
    login = _bw_login(item)
    fm    = _bw_fields_map(item)
    return json.dumps({
        "type":       item.get("type"),
        "name":       normalize_lower(item.get("name")),
        "username":   normalize_lower(login.get("username")),
        "password":   login.get("password"),
        "totp":       login.get("totp"),
        "uris":       _bw_uri_set(item),
        "notes":      item.get("notes"),
        "fields":     [(k, fm[k]["value"], fm[k]["type"]) for k in sorted(fm)],
        "card":       item.get("card"),
        "identity":   item.get("identity"),
        "secureNote": item.get("secureNote"),
        "sshKey":     item.get("sshKey"),
    }, sort_keys=True, ensure_ascii=False)


def bw_soft_key(item):
    login     = _bw_login(item)
    item_type = item.get("type")
    return (
        int(item_type) if item_type is not None else -1,
        normalize_lower(item.get("name")),
        normalize_lower(login.get("username")),
    )


def bw_summarize(item):
    login = _bw_login(item)
    return {
        "name":     item.get("name"),
        "username": login.get("username"),
        "uris":     _bw_uri_set(item),
    }


def bw_merge_item(existing, incoming, policy="prefer_newer", strict_uri=True):
    merged  = copy.deepcopy(existing)
    login_m = merged.setdefault("login", {})
    login_i = incoming.get("login") or {}
    diff    = []

    for field in ["password", "totp"]:
        val_e = login_m.get(field)
        val_i = login_i.get(field)
        if val_e != val_i:
            decision = choose_source(existing, incoming, policy)
            diff.append({"type": f"{field}_conflict", "decision": decision, "sensitive": True})
            if decision == "incoming":
                login_m[field] = val_i

    if normalize_text(merged.get("notes")) != normalize_text(incoming.get("notes")):
        decision = choose_source(existing, incoming, policy)
        diff.append({"type": "notes_conflict", "decision": decision})
        if decision == "incoming" and incoming.get("notes"):
            merged["notes"] = incoming["notes"]

    uris_m = login_m.setdefault("uris", [])
    known  = {_bw_norm_uri(u["uri"], strict_uri)
              for u in uris_m if isinstance(u, dict) and u.get("uri")}
    added  = []
    for u in _bw_uri_objects(incoming, strict_uri):
        if u["normalized"] not in known:
            uris_m.append({"uri": u["uri"], "match": u.get("match")})
            known.add(u["normalized"])
            added.append(u["uri"])
    if added:
        diff.append({"type": "uris_added", "value": added})

    fields_m  = merged.setdefault("fields", []) or []
    fields_i  = incoming.get("fields") or []
    field_idx = {normalize_text(f.get("name")): i
                 for i, f in enumerate(fields_m) if normalize_text(f.get("name"))}
    for f in fields_i:
        name = normalize_text(f.get("name"))
        if not name:
            continue
        if name not in field_idx:
            fields_m.append(copy.deepcopy(f))
            diff.append({"type": "field_added", "field": name, "sensitive": is_sensitive(name)})
        else:
            idx = field_idx[name]
            if (fields_m[idx].get("value") != f.get("value") or
                    fields_m[idx].get("type") != f.get("type")):
                decision = choose_source(existing, incoming, policy)
                diff.append({"type": "field_conflict", "field": name,
                             "old": "***", "new": "***",
                             "decision": decision, "sensitive": True})
                if decision == "incoming":
                    fields_m[idx] = copy.deepcopy(f)
    merged["fields"] = fields_m

    for top in ["card", "identity", "secureNote", "sshKey"]:
        if merged.get(top) != incoming.get(top):
            decision = choose_source(existing, incoming, policy)
            diff.append({"type": f"{top}_conflict", "decision": decision})
            if decision == "incoming":
                merged[top] = copy.deepcopy(incoming.get(top))

    dt_e = parse_dt(merged.get("revisionDate"))
    dt_i = parse_dt(incoming.get("revisionDate"))
    if dt_i and (not dt_e or dt_i > dt_e):
        merged["revisionDate"] = incoming["revisionDate"]

    hist_e = merged.get("passwordHistory") or []
    hist_i = incoming.get("passwordHistory") or []
    if hist_i:
        seen = {(h.get("password"), h.get("lastUsedDate")) for h in hist_e}
        for h in hist_i:
            k = (h.get("password"), h.get("lastUsedDate"))
            if k not in seen:
                hist_e.append(copy.deepcopy(h))
                seen.add(k)
        merged["passwordHistory"] = hist_e

    manual_types = [c["type"] for c in diff if c.get("decision") == "manual"]
    if manual_types:
        existing_names = {normalize_text(f.get("name")) for f in (merged.get("fields") or [])}
        if "_merge_review" not in existing_names:
            merged.setdefault("fields", []).append(
                {"name": "_merge_review", "value": "true", "type": 0}
            )
        if "_merge_review_reason" not in existing_names:
            merged.setdefault("fields", []).append(
                {"name": "_merge_review_reason", "value": ", ".join(manual_types), "type": 0}
            )

    return merged, diff


def flag_reused_bw_passwords(items):
    """
    Flaggar poster som delar lösenord med minst en annan post (_reused_password=true).
    Lösenordsvärdet självt lagras aldrig separat — bara en boolesk flagga per post.
    Returnerar antal poster som flaggades.
    """
    by_password = {}
    for item in items:
        pw = _bw_login(item).get("password")
        if pw:
            by_password.setdefault(pw, []).append(item)

    flagged = 0
    for pw, group in by_password.items():
        if len(group) < 2:
            continue
        for item in group:
            fields = item.setdefault("fields", []) or []
            names = {normalize_text(f.get("name")) for f in fields}
            if "_reused_password" not in names:
                fields.append({"name": "_reused_password", "value": "true", "type": 0})
                item["fields"] = fields
                flagged += 1
    return flagged


def run_bitwarden_merge(items1, items2, args):
    merged_map = {}
    file1_ids  = set()
    for item in items1:
        copied = copy.deepcopy(item)
        merged_map.setdefault(bw_soft_key(item), []).append(copied)
        file1_ids.add(id(copied))

    touched_ids = set()
    report = _empty_report(args.policy, len(items1), len(items2))

    for item in items2:
        s_key      = bw_soft_key(item)
        candidates = merged_map.get(s_key, [])
        fp         = bw_exact_fingerprint(item)

        if not candidates:
            if not args.dry_run:
                merged_map.setdefault(s_key, []).append(copy.deepcopy(item))
            report["stats"]["new_entries_from_file2"] += 1
            s = bw_summarize(item)
            report["new_entries"].append({
                "display_name":   s["name"] or "(inget namn)",
                "fields_preview": f"user={s['username'] or '–'}",
                "uris":           s["uris"],
            })
            continue

        matched = False
        for idx, existing in enumerate(candidates):
            if bw_exact_fingerprint(existing) == fp:
                touched_ids.add(id(existing))
                report["stats"]["exact_duplicates"] += 1
                matched = True
                break

            e_uris = set(_bw_uri_set(existing, args.strict_uri))
            i_uris = set(_bw_uri_set(item,     args.strict_uri))
            if (e_uris & i_uris) or (not e_uris and not i_uris):
                touched_ids.add(id(existing))
                merged_item, diff = bw_merge_item(
                    existing, item, policy=args.policy, strict_uri=args.strict_uri
                )
                if not args.dry_run:
                    candidates[idx] = merged_item

                if diff:
                    login = _bw_login(existing)
                    name  = existing.get("name") or "(inget namn)"
                    user  = login.get("username") or ""
                    dn    = f"{name} / {user}" if user else name
                    report["stats"]["merged_entries"] += 1
                    report["merged_changes"].append({"display_name": dn, "changes": diff})
                    if any(c.get("decision") == "manual" for c in diff):
                        report["stats"]["conflicted_entries"] += 1
                        report["manual_review"].append({"display_name": dn, "changes": diff})

                matched = True
                break

        if not matched:
            if not args.dry_run:
                merged_map[s_key].append(copy.deepcopy(item))
            report["stats"]["new_entries_from_file2"] += 1
            s = bw_summarize(item)
            report["new_entries"].append({
                "display_name":   s["name"] or "(inget namn)",
                "fields_preview": f"user={s['username'] or '–'}",
                "uris":           s["uris"],
            })

    for lst in merged_map.values():
        for it in lst:
            if id(it) in file1_ids and id(it) not in touched_ids:
                s = bw_summarize(it)
                report["stats"]["file1_only_unchanged"] += 1
                report["file1_only"].append({
                    "display_name":   s["name"] or "(inget namn)",
                    "fields_preview": f"user={s['username'] or '–'}",
                    "uris":           s["uris"],
                })

    return [item for lst in merged_map.values() for item in lst], report


# ── Diff-läge ─────────────────────────────────────────────────────────────────

def run_diff(items1, items2, args, mode, key_fields=None, date_field=None, extra_sensitive=None):
    W = 68
    if mode == "bitwarden":
        map1  = {}
        for i in items1:
            map1.setdefault(bw_soft_key(i), []).append(i)
        keys2 = {bw_soft_key(i) for i in items2}
        only1, only2, changed, identical = [], [], [], 0
        for item in items2:
            sk = bw_soft_key(item)
            cands = map1.get(sk, [])
            if not cands:
                only2.append(item); continue
            matched = False
            for existing in cands:
                if bw_exact_fingerprint(existing) == bw_exact_fingerprint(item):
                    identical += 1; matched = True; break
                e_u = set(_bw_uri_set(existing, args.strict_uri))
                i_u = set(_bw_uri_set(item,     args.strict_uri))
                if (e_u & i_u) or (not e_u and not i_u):
                    _, diff = bw_merge_item(existing, item, args.policy, args.strict_uri)
                    if diff: changed.append((existing, item, diff))
                    matched = True; break
            if not matched: only2.append(item)
        for i in items1:
            if bw_soft_key(i) not in keys2: only1.append(i)

        def label(i):
            l = _bw_login(i)
            return f"{i.get('name','?')} / {l.get('username','–')}"
    else:
        map1  = {}
        for i in items1:
            map1.setdefault(generic_key(i, key_fields), []).append(i)
        keys2 = {generic_key(i, key_fields) for i in items2}
        only1, only2, changed, identical = [], [], [], 0
        for item in items2:
            k     = generic_key(item, key_fields)
            cands = map1.get(k, [])
            if not cands:
                only2.append(item); continue
            matched = False
            for existing in cands:
                if generic_fingerprint(existing) == generic_fingerprint(item):
                    identical += 1; matched = True; break
                _, diff = generic_merge_item(existing, item, args.policy, date_field, extra_sensitive)
                if diff: changed.append((existing, item, diff))
                matched = True; break
            if not matched: only2.append(item)
        for i in items1:
            if generic_key(i, key_fields) not in keys2: only1.append(i)

        def label(i):
            for f in key_fields:
                if i.get(f): return str(i[f])
            return str(i)[:50]

    print(f"\n{'='*W}")
    print(f"  DIFF — fil1 ↔ fil2")
    print(f"{'='*W}")
    print(f"  Identiska:   {identical}")
    print(f"  Ändrade:     {len(changed)}")
    print(f"  Bara fil 1:  {len(only1)}")
    print(f"  Bara fil 2:  {len(only2)}")
    print(f"{'='*W}")
    for i in only1: print(f"  < {label(i)}")
    for i in only2: print(f"  > {label(i)}")
    for existing, incoming, diff in changed:
        print(f"\n  ~ {label(existing)}")
        for c in diff:
            dec = c.get("decision", "")
            marker = ">" if dec == "incoming" else ("<" if dec == "existing" else "?")
            print(f"    {marker} {c['type']}" + (f" [{dec}]" if dec else ""))
    print(f"\n{'='*W}\n")


# ── HTML-rapport ──────────────────────────────────────────────────────────────

def _esc(text):
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _safe_href(uri):
    """Tillåter bara http/https — blockerar javascript: och liknande."""
    s = str(uri).strip().lower()
    if s.startswith(("http://", "https://")):
        return _esc(uri)
    return "#"


def _badge(label, color):
    colors = {"green": "#22c55e", "red": "#ef4444", "yellow": "#f59e0b",
              "blue": "#3b82f6", "gray": "#6b7280"}
    bg = colors.get(color, "#6b7280")
    return (f'<span style="background:{bg};color:#fff;padding:2px 9px;'
            f'border-radius:99px;font-size:.75em;font-weight:700">{_esc(label)}</span>')


def _decision_badge(decision):
    if decision == "existing": return _badge("fil 1 vann", "blue")
    if decision == "incoming": return _badge("fil 2 vann", "green")
    if decision == "manual":   return _badge("⚠ manuell",  "red")
    return _badge(decision, "gray")


def _change_row(ch):
    ctype     = ch.get("type", "")
    decision  = ch.get("decision", "")
    badge     = _decision_badge(decision) if decision else ""
    sensitive = ch.get("sensitive", False)

    if ctype in ("password_conflict", "totp_conflict"):
        label = "🔑 Lösenord" if "password" in ctype else "🔐 TOTP"
        return (f"<tr><td>{label}</td>"
                f"<td><em class='muted'>Skiljer sig (dold)</em></td>"
                f"<td>{badge}</td></tr>")
    if ctype == "notes_conflict":
        return (f"<tr><td>📝 Anteckningar</td>"
                f"<td><em class='muted'>Skiljer sig</em></td><td>{badge}</td></tr>")
    if ctype == "uris_added":
        links = []
        for u in (ch.get("value") or []):
            links.append(f'<a href="{_safe_href(u)}" target="_blank" rel="noopener" '
                         f'class="link">{_esc(u)}</a>')
        return (f"<tr><td>🔗 URI tillagd</td><td>{', '.join(links)}</td>"
                f"<td>{_badge('ny','green')}</td></tr>")
    if ctype == "field_added":
        return (f"<tr><td>➕ Nytt fält</td><td>{_esc(ch.get('field'))}</td>"
                f"<td>{_badge('ny','green')}</td></tr>")
    if ctype == "field_conflict":
        if sensitive:
            detail = "<em class='muted'>Skiljer sig (dold)</em>"
        else:
            detail = f"<code>{_esc(ch.get('old') or '–')}</code> → <code>{_esc(ch.get('new') or '–')}</code>"
        return (f"<tr><td>📋 {_esc(ch.get('field'))}</td>"
                f"<td>{detail}</td><td>{badge}</td></tr>")
    return f"<tr><td>{_esc(ctype)}</td><td>–</td><td>{badge}</td></tr>"


def _empty_report(policy, n1, n2):
    return {
        "policy": policy,
        "stats": {
            "file1_items": n1, "file2_items": n2,
            "exact_duplicates": 0, "merged_entries": 0,
            "new_entries_from_file2": 0, "conflicted_entries": 0,
            "reused_passwords": 0, "file1_only_unchanged": 0,
        },
        "exact_duplicates": [], "merged_changes": [],
        "new_entries": [],     "manual_review": [],
        "file1_only": [],
    }


def build_html_report(report, total_output, file1, file2, mode_label):
    stats  = report["stats"]
    merged = report.get("merged_changes", [])
    new_e  = report.get("new_entries", [])
    manual = report.get("manual_review", [])
    dups   = report.get("exact_duplicates", [])
    f1only = report.get("file1_only", [])
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M")

    def card(label, value, color="default"):
        bg = {"default": "#1e293b", "yellow": "#78350f",
              "red": "#7f1d1d", "green": "#14532d"}.get(color, "#1e293b")
        return (f'<div class="card" style="background:{bg}">'
                f'<div class="card-val">{value}</div>'
                f'<div class="card-lbl">{label}</div></div>')

    stat_cards = "".join([
        card("Fil 1",          stats["file1_items"]),
        card("Fil 2",          stats["file2_items"]),
        card("Exakta kopior",  stats["exact_duplicates"]),
        card("Mergade (diff)", stats["merged_entries"],
             "yellow" if stats["merged_entries"] else "default"),
        card("Nya från fil 2", stats["new_entries_from_file2"],
             "green"  if stats["new_entries_from_file2"] else "default"),
        card("Bara i fil 1",   stats.get("file1_only_unchanged", 0)),
        card("Kräver review",  stats["conflicted_entries"],
             "red"    if stats["conflicted_entries"] else "default"),
        card("Återanvända lösenord", stats.get("reused_passwords", 0),
             "yellow" if stats.get("reused_passwords") else "default"),
        card("Totalt output",  total_output),
    ])

    manual_html = ""
    if manual:
        rows = ""
        for entry in manual:
            name  = _esc(entry.get("display_name", "?"))
            inner = "".join(_change_row(c) for c in entry.get("changes", []))
            rows += (f'<details open style="margin-bottom:8px">'
                     f'<summary class="summary-red"><strong>{name}</strong></summary>'
                     f'<div class="detail-body"><table>'
                     f'<thead><tr><th>Fält</th><th>Detalj</th><th>Beslut</th></tr></thead>'
                     f'<tbody>{inner}</tbody></table></div></details>')
        manual_html = (
            f'<div class="alert-box">'
            f'<h2 style="margin-top:0;color:#fca5a5;border:none">'
            f'⚠️ Manuell granskning krävs ({len(manual)} st)</h2>'
            f'<p style="color:#fecaca;margin-bottom:16px">'
            f'Dessa poster har konflikter som inte kunde lösas automatiskt. '
            f'De har fått fältet <code>_merge_review=true</code> i utdatan.</p>'
            f'{rows}</div>'
        )

    merged_html = ""
    for entry in merged:
        name    = _esc(entry.get("display_name", "(inget namn)"))
        changes = entry.get("changes", [])
        flag    = " ⚠️" if any(c.get("decision") == "manual" for c in changes) else ""
        types   = " ".join(c["type"] for c in changes)
        inner   = "".join(_change_row(c) for c in changes)
        merged_html += (
            f'<details class="merge-item" data-name="{name.lower()}" '
            f'data-types="{_esc(types)}" style="margin-bottom:5px">'
            f'<summary class="summary-default">'
            f'<span><strong>{name}</strong>{flag}</span>'
            f'<span class="muted small">{len(changes)} ändring(ar)</span></summary>'
            f'<div class="detail-body"><table>'
            f'<thead><tr><th>Fält</th><th>Detalj</th><th>Beslut</th></tr></thead>'
            f'<tbody>{inner}</tbody></table></div></details>'
        )
    if not merged_html:
        merged_html = "<p class='muted center'>Inga poster mergades med skillnader.</p>"

    new_rows = ""
    for e in new_e:
        name  = _esc(e.get("display_name") or "(inget namn)")
        prev  = _esc(e.get("fields_preview", ""))
        uris  = "".join(
            f'<a href="{_safe_href(u)}" target="_blank" rel="noopener" class="link">{_esc(u)}</a> '
            for u in (e.get("uris") or [])
        ) or "–"
        new_rows += f"<tr><td>{name}</td><td class='small muted'>{prev}</td><td class='small muted'>{uris}</td></tr>"
    if not new_rows:
        new_rows = "<tr><td colspan='3' class='muted center'>Inga nya poster.</td></tr>"

    f1only_rows = ""
    for e in f1only:
        name  = _esc(e.get("display_name") or "(inget namn)")
        prev  = _esc(e.get("fields_preview", ""))
        uris  = "".join(
            f'<a href="{_safe_href(u)}" target="_blank" rel="noopener" class="link">{_esc(u)}</a> '
            for u in (e.get("uris") or [])
        ) or "–"
        f1only_rows += f"<tr><td>{name}</td><td class='small muted'>{prev}</td><td class='small muted'>{uris}</td></tr>"
    if not f1only_rows:
        f1only_rows = "<tr><td colspan='3' class='muted center'>Inga poster bara i fil 1.</td></tr>"

    css = """
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;
         color:#e2e8f0;padding:32px 16px;line-height:1.6}
    .wrap{max-width:960px;margin:0 auto}
    h1{font-size:1.7rem;margin-bottom:4px}
    h2{font-size:1.15rem;margin:36px 0 12px;border-bottom:1px solid #334155;padding-bottom:8px}
    .meta{color:#64748b;font-size:.85em;margin-bottom:28px}
    .cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:28px}
    .card{background:#1e293b;border-radius:10px;padding:16px 22px;flex:1;min-width:110px;text-align:center}
    .card-val{font-size:2rem;font-weight:700}
    .card-lbl{font-size:.78rem;color:#94a3b8;margin-top:4px}
    .alert-box{background:#450a0a;border:1px solid #ef4444;border-radius:10px;
               padding:20px;margin-bottom:28px}
    .toolbar{display:flex;gap:8px;align-items:center;margin:12px 0 10px;flex-wrap:wrap}
    .toolbar input{background:#1e293b;border:1px solid #334155;color:#e2e8f0;
                   padding:6px 12px;border-radius:6px;font-size:.85em;flex:1;min-width:200px}
    .toolbar input:focus{outline:none;border-color:#3b82f6}
    button{background:#334155;color:#f8fafc;border:none;padding:6px 14px;
           border-radius:6px;cursor:pointer;font-size:.82em;font-weight:600}
    button:hover{background:#475569}
    .filter-btn.active{background:#3b82f6}
    details summary::-webkit-details-marker{display:none}
    .summary-default{cursor:pointer;padding:10px 14px;background:#1e293b;border-radius:6px;
                     list-style:none;display:flex;justify-content:space-between;
                     align-items:center;user-select:none}
    .summary-default:hover{background:#263347}
    details[open] .summary-default{border-radius:6px 6px 0 0;background:#263347}
    .summary-red{cursor:pointer;padding:8px 12px;list-style:none;user-select:none}
    .detail-body{padding:6px 14px 12px;border:1px solid #1e293b;border-top:none;
                 border-radius:0 0 6px 6px;overflow-x:auto}
    table{width:100%;border-collapse:collapse;font-size:.87em}
    th,td{padding:7px 10px;text-align:left;border-bottom:1px solid #1e293b;vertical-align:top}
    th{color:#64748b;font-size:.78em;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
    .muted{color:#64748b} .small{font-size:.82em} .center{text-align:center;padding:20px}
    code{background:#1e293b;padding:1px 5px;border-radius:3px;font-size:.9em}
    .link{color:#60a5fa;text-decoration:none} .link:hover{text-decoration:underline}
    .hidden{display:none!important}
    .new-table{background:#1e293b;border-radius:10px;overflow:hidden}
    .footer{margin-top:48px;padding:16px 20px;background:#1e293b;border-radius:10px;
            color:#64748b;font-size:.85em}
    """

    js = """
    let activeFilter = 'all';
    function toggleAll(open) {
      document.querySelectorAll('.merge-item').forEach(d => d.open = open);
    }
    function setFilter(filter, btn) {
      activeFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterItems();
    }
    function filterItems() {
      const q = document.getElementById('search').value.toLowerCase().trim();
      document.querySelectorAll('.merge-item').forEach(el => {
        const nameOk   = !q || (el.dataset.name || '').includes(q);
        const filterOk = activeFilter === 'all' || (el.dataset.types || '').includes(activeFilter);
        el.classList.toggle('hidden', !(nameOk && filterOk));
      });
    }
    """

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JSON Merge-rapport — {_esc(ts)}</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <h1>🔐 JSON Merge-rapport</h1>
  <div class="meta">
    Genererad: {_esc(ts)} &nbsp;·&nbsp;
    Läge: <strong>{_esc(mode_label)}</strong> &nbsp;·&nbsp;
    Policy: <strong>{_esc(report.get('policy','?'))}</strong><br>
    <span style="color:#475569">Fil 1: {_esc(file1)} &nbsp;·&nbsp; Fil 2: {_esc(file2)}</span>
  </div>

  <div class="cards">{stat_cards}</div>
  {manual_html}

  <h2>🔄 Mergade poster med skillnader ({len(merged)} st)</h2>
  <div class="toolbar">
    <input type="text" id="search" placeholder="Sök på namn…" oninput="filterItems()">
    <button class="filter-btn active" onclick="setFilter('all',this)">Alla</button>
    <button class="filter-btn" onclick="setFilter('password_conflict',this)">Lösenord</button>
    <button class="filter-btn" onclick="setFilter('field_conflict',this)">Fält</button>
    <button onclick="toggleAll(true)">Expandera alla</button>
    <button onclick="toggleAll(false)">Stäng alla</button>
  </div>
  <div id="merge-list">{merged_html}</div>

  <h2>🆕 Nya poster från fil 2 ({len(new_e)} st)</h2>
  <div class="new-table">
    <table>
      <thead><tr><th>Namn/Nyckel</th><th>Fält</th><th>URI(er)</th></tr></thead>
      <tbody>{new_rows}</tbody>
    </table>
  </div>

  <details style="margin-top:20px">
    <summary class="summary-default"><strong>📄 Bara i fil 1, oförändrade ({len(f1only)} st)</strong></summary>
    <div class="new-table" style="margin-top:8px">
      <table>
        <thead><tr><th>Namn/Nyckel</th><th>Fält</th><th>URI(er)</th></tr></thead>
        <tbody>{f1only_rows}</tbody>
      </table>
    </div>
  </details>

  <div class="footer">
    ✅ <strong>{len(dups)}</strong> identiska poster ignorerades.
    &nbsp;·&nbsp; Totalt <strong>{total_output}</strong> poster i merged-filen.
  </div>
</div>
<script>{js}</script>
</body>
</html>"""


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    # Tvinga UTF-8 på stdout så att unicode-tecken fungerar även i Windows-terminal
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="VaultWeaver — Bitwarden/Vaultwarden + generisk JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exempel:
  # Bitwarden/Vaultwarden (auto-detekteras):
  python3 merge_json_v4.py vault1.json vault2.json

  # Generisk JSON:
  python3 merge_json_v4.py users1.json users2.json --key-fields id
  python3 merge_json_v4.py contacts.json new.json --key-fields email
  python3 merge_json_v4.py a.json b.json --key-fields name,email

  # Nästlad array:
  python3 merge_json_v4.py a.json b.json --items-path data.records --key-fields uuid

  # Torra körningar, diff, rollback:
  python3 merge_json_v4.py f1.json f2.json --dry-run
  python3 merge_json_v4.py f1.json f2.json --diff
  python3 merge_json_v4.py --rollback
        """)

    parser.add_argument("file1", nargs="?")
    parser.add_argument("file2", nargs="?")
    parser.add_argument("-o", "--output",  default=DEFAULT_OUTPUT)
    parser.add_argument("-r", "--report",  default=DEFAULT_REPORT)
    parser.add_argument("--policy",
                        choices=["prefer_newer", "prefer_file1", "prefer_file2", "manual"],
                        default="prefer_newer")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--diff",       action="store_true",
                        help="Visa diff utan att merga")
    parser.add_argument("--shred-inputs", action="store_true",
                        help="Skriv över och radera de två input-filerna efter en lyckad merge "
                             "(best-effort — se README för begränsningar på SSD)")
    parser.add_argument("--rollback",   action="store_true",
                        help="Återställ senaste merge från backup")
    parser.add_argument("-v", "--verbose", action="store_true")

    # Bitwarden-specifikt
    parser.add_argument("--strict-uri", action="store_true",
                        help="Inkludera port och sökväg i URI-jämförelse (bra för homelab)")

    # Generiskt läge
    parser.add_argument("--key-fields",
                        help="Komma-separerade fältnamn som identifierar en post unikt, t.ex. id eller name,email")
    parser.add_argument("--sensitive-fields",
                        help="Extra fält att maskera i rapporten, t.ex. pin,recovery_code")
    parser.add_argument("--items-path",
                        help="Punkt-notation till arrayen, t.ex. data.records")
    parser.add_argument("--date-field",
                        help="Fält med ändringsdatum för prefer_newer (auto-detekteras om ej angivet)")

    args = parser.parse_args()

    if args.rollback:
        do_rollback()
        return

    if not args.file1 or not args.file2:
        # Auto-detektera JSON-filer i aktuell mapp
        candidates = sorted(
            [f for f in os.listdir(".")
             if f.lower().endswith(".json")
             and not f.startswith(".")
             and f != STATE_FILE
             and os.path.isfile(f)],
            key=lambda f: os.path.getmtime(f),
        )
        if len(candidates) == 2:
            args.file1, args.file2 = candidates[0], candidates[1]
            print(f"Auto-detekterade: {args.file1}  +  {args.file2}")
        elif len(candidates) > 2:
            print("Hittade flera JSON-filer i mappen — ange filerna explicit:")
            for f in candidates:
                print(f"  {f}")
            print("\nExempel: python3 merge_json_v4.py fil1.json fil2.json")
            sys.exit(1)
        else:
            parser.error("Inga JSON-filer hittades i mappen. Ange filerna explicit.")

    print("VaultWeaver")
    print("-" * 42)

    try:
        data1 = load_json(args.file1)
        data2 = load_json(args.file2)
    except Exception as e:
        print(f"FEL: {e}")
        sys.exit(1)

    # ── Formatdetektering ────────────────────────────────────────────────────
    if is_bitwarden_format(data1) and is_bitwarden_format(data2) and not args.key_fields:
        mode       = "bitwarden"
        mode_label = "Bitwarden / Vaultwarden"
        print(f"Format:  {mode_label} (auto-detekterat)")
    else:
        mode = "generic"
        if args.key_fields:
            key_fields = [f.strip() for f in args.key_fields.split(",") if f.strip()]
        else:
            try:
                sample, _ = find_items_array(data1, args.items_path)
            except ValueError:
                sample = []
            key_fields = auto_detect_key_fields(sample)
            if not key_fields:
                print("FEL: Kunde inte auto-detektera nyckelfält.")
                print("     Ange --key-fields <fält> (t.ex. --key-fields id)")
                sys.exit(1)
            print(f"Format:     Generisk JSON (auto-detekterat)")
            print(f"Nyckelfält: {', '.join(key_fields)}  "
                  f"(överstyr med --key-fields om detta är fel)")

        extra_sensitive = set()
        if args.sensitive_fields:
            extra_sensitive = {f.strip() for f in args.sensitive_fields.split(",") if f.strip()}

        try:
            items1_arr, array_key = find_items_array(data1, args.items_path)
            items2_arr, _         = find_items_array(data2, args.items_path)
        except ValueError as e:
            print(f"FEL: {e}")
            sys.exit(1)

        date_field = args.date_field or auto_detect_date_field(items1_arr)
        if date_field:
            print(f"Datumfält:  {date_field}  (används för prefer_newer)")

        mode_label = f"Generisk JSON  ·  nyckel: {', '.join(key_fields)}"

    print(f"Fil 1:   {args.file1}")
    print(f"Fil 2:   {args.file2}")

    # ── Bitwarden-flöde ──────────────────────────────────────────────────────
    if mode == "bitwarden":
        items1_arr = data1.get("items", [])
        items2_arr = data2.get("items", [])
        print(f"Poster:  fil1={len(items1_arr)}, fil2={len(items2_arr)}")

        if args.diff:
            run_diff(items1_arr, items2_arr, args, "bitwarden")
            return

        merged_items, report = run_bitwarden_merge(items1_arr, items2_arr, args)
        report["stats"]["reused_passwords"] = flag_reused_bw_passwords(merged_items)
        output_data = dict(data1)
        output_data["items"] = merged_items

    # ── Generiskt flöde ──────────────────────────────────────────────────────
    else:
        print(f"Poster:  fil1={len(items1_arr)}, fil2={len(items2_arr)}")

        if args.diff:
            run_diff(items1_arr, items2_arr, args, "generic",
                     key_fields, date_field, extra_sensitive)
            return

        merged_items, report = run_generic_merge(
            items1_arr, items2_arr, args, key_fields, date_field, extra_sensitive
        )

        if isinstance(data1, list):
            output_data = merged_items
        elif array_key:
            output_data = dict(data1)
            if "." in str(array_key):
                # Navigera nästlad struktur för dot-notation path (t.ex. "data.records")
                parts = str(array_key).split(".")
                node = output_data
                for p in parts[:-1]:
                    node = node[p]
                node[parts[-1]] = merged_items
            else:
                output_data[array_key] = merged_items
        else:
            output_data = merged_items

    # ── Sammanfattning ───────────────────────────────────────────────────────
    stats = report["stats"]
    print(f"\n{'-'*42}")
    print(f"  Exakta kopior (ignorerade):  {stats['exact_duplicates']}")
    print(f"  Mergade (med skillnader):    {stats['merged_entries']}")
    print(f"  Nya poster fran fil 2:       {stats['new_entries_from_file2']}")
    print(f"  Kräver manuell granskning:   {stats['conflicted_entries']}")
    print(f"  Totalt i output:             {len(merged_items)}")
    print(f"{'-'*42}")

    if args.verbose and report["merged_changes"]:
        print()
        for entry in report["merged_changes"]:
            print(f"  ~ {entry['display_name']}")
            for ch in entry.get("changes", []):
                dec = ch.get("decision", "")
                print(f"    → {ch['type']}" + (f" [{dec}]" if dec else ""))

    html = build_html_report(report, len(merged_items), args.file1, args.file2, mode_label)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(html)
    _secure_chmod(args.report)
    print(f"\n✓ Rapport:  {args.report}")

    if args.dry_run:
        print("  [DRY RUN] Ingen merged-fil sparades.\n")
        return

    backup_path = backup_file(args.output)
    if backup_path:
        print(f"✓ Backup:   {backup_path}")

    save_json(args.output, output_data)
    print(f"✓ Merged:   {args.output}")

    save_state(args.output, backup_path)

    if args.shred_inputs:
        for path in (args.file1, args.file2):
            if shred_file(path):
                print(f"✓ Shreddad: {path} (skriven över + borttagen)")
            else:
                print(f"⚠️  Kunde inte shredda: {path}")

    if stats["conflicted_entries"] > 0:
        print(f"\n⚠️  {stats['conflicted_entries']} poster kräver manuell granskning.")
        print(f"   Sök på '_merge_review=true' i utdatan.")
        print(f"   Detaljer: {args.report}")


if __name__ == "__main__":
    main()
