"""
profile_manager.py — Switch SwingTrade config profiles with history tracking.

Usage:
    python3 profile_manager.py list                       # list available profiles
    python3 profile_manager.py current                    # show currently active profile
    python3 profile_manager.py diff <profile>             # preview before/after table
    python3 profile_manager.py switch <profile> [--note]  # apply + record history
    python3 profile_manager.py history                    # show last 20 changes

Profiles live in config/profiles/*.json. Each profile is an OVERLAY on
config/config.json — only listed keys are overwritten, everything else is
preserved. History is append-only in config/history/changes.jsonl, with a
human-readable mirror in config/history/HISTORY.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent
CONFIG = BASE / "config" / "config.json"
PROFILES_DIR = BASE / "config" / "profiles"
HISTORY_DIR = BASE / "config" / "history"
HISTORY_JSONL = HISTORY_DIR / "changes.jsonl"
HISTORY_MD = HISTORY_DIR / "HISTORY.md"
ACTIVE_POINTER = HISTORY_DIR / "active_profile.txt"

PST = ZoneInfo("America/Los_Angeles")

# Keys that profiles are allowed to touch (safety — prevents accidental overwrite of other config)
PROFILE_KEYS = {"decisions", "regime_thresholds", "regime4_thresholds", "gates",
                 "scoring_weights", "entry_quality_rules", "catalyst_tiers",
                 "setup_gates", "filters", "score_bands", "short_rules", "price_buckets"}


def _now_pst() -> str:
    return datetime.now(PST).strftime("%Y-%m-%d %H:%M:%S %Z")


def _load_profile(name: str) -> dict:
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        sys.exit(f"ERROR: profile '{name}' not found at {path}")
    return json.loads(path.read_text())


def _load_config() -> dict:
    return json.loads(CONFIG.read_text())


def _save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, indent=2))


def list_profiles() -> None:
    if not PROFILES_DIR.exists():
        sys.exit("No profiles/ directory.")
    current = _current_profile_name()
    print(f"Available profiles (active = {current or 'custom/unknown'}):\n")
    for p in sorted(PROFILES_DIR.glob("*.json")):
        data = json.loads(p.read_text())
        name = data.get("_profile_name", p.stem)
        desc = data.get("_description", "")
        marker = " *" if name == current else ""
        print(f"  {name}{marker}")
        print(f"    {desc}")
        if data.get("_tradeoffs"):
            print(f"    tradeoffs: {data['_tradeoffs']}")
        print()


def _current_profile_name() -> str | None:
    if ACTIVE_POINTER.exists():
        return ACTIVE_POINTER.read_text().strip() or None
    return None


def _collect_diff(cfg: dict, profile: dict) -> list[tuple[str, object, object]]:
    """Return list of (dotted.key.path, before_value, after_value) tuples."""
    rows: list[tuple[str, object, object]] = []

    def _walk(prefix: str, before_node, after_node):
        if isinstance(after_node, dict):
            if not isinstance(before_node, dict):
                before_node = {}
            for k, v in after_node.items():
                if k.startswith("_"):
                    continue  # skip meta keys
                _walk(f"{prefix}.{k}" if prefix else k, before_node.get(k), v)
        else:
            if before_node != after_node:
                rows.append((prefix, before_node, after_node))

    for top_key, new_val in profile.items():
        if top_key.startswith("_"):
            continue
        if top_key not in PROFILE_KEYS:
            continue  # safety guard
        _walk(top_key, cfg.get(top_key, {}), new_val)
    return rows


def _format_table(rows: list[tuple[str, object, object]]) -> str:
    if not rows:
        return "  (no changes)"
    width_k = max(len("Key"), max(len(r[0]) for r in rows))
    width_b = max(len("Before"), max(len(str(r[1])) for r in rows))
    width_a = max(len("After"),  max(len(str(r[2])) for r in rows))
    line = f"  {'Key':<{width_k}}  {'Before':<{width_b}}  {'After':<{width_a}}"
    sep  = f"  {'-'*width_k}  {'-'*width_b}  {'-'*width_a}"
    out = [line, sep]
    for k, b, a in rows:
        out.append(f"  {k:<{width_k}}  {str(b):<{width_b}}  {str(a):<{width_a}}")
    return "\n".join(out)


def _markdown_table(rows: list[tuple[str, object, object]]) -> str:
    if not rows:
        return "_(no changes)_"
    out = ["| Key | Before | After |", "|---|---|---|"]
    for k, b, a in rows:
        out.append(f"| `{k}` | `{b}` | `{a}` |")
    return "\n".join(out)


def diff(profile_name: str) -> None:
    cfg = _load_config()
    profile = _load_profile(profile_name)
    rows = _collect_diff(cfg, profile)
    print(f"\nDiff: current → {profile_name}\n")
    print(_format_table(rows))
    print(f"\nTotal keys changing: {len(rows)}")


def switch(profile_name: str, note: str = "") -> None:
    cfg = _load_config()
    profile = _load_profile(profile_name)
    rows = _collect_diff(cfg, profile)

    if not rows:
        print(f"Profile '{profile_name}' matches current config — nothing to apply.")
        return

    # Apply overlay
    for top_key, new_val in profile.items():
        if top_key.startswith("_") or top_key not in PROFILE_KEYS:
            continue
        if isinstance(new_val, dict) and isinstance(cfg.get(top_key), dict):
            # merge
            for k, v in new_val.items():
                if isinstance(v, dict) and isinstance(cfg[top_key].get(k), dict):
                    cfg[top_key][k].update(v)
                else:
                    cfg[top_key][k] = v
        else:
            cfg[top_key] = new_val

    # Backup current config
    backup_path = HISTORY_DIR / f"config_backup_{datetime.now(PST).strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(CONFIG, backup_path)

    _save_config(cfg)
    ACTIVE_POINTER.write_text(profile_name)

    # Record history
    entry = {
        "timestamp": _now_pst(),
        "profile": profile_name,
        "note": note,
        "changes": [{"key": k, "before": b, "after": a} for (k, b, a) in rows],
        "backup": backup_path.name,
    }
    with HISTORY_JSONL.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    # Append to human-readable HISTORY.md
    header = f"\n## {entry['timestamp']} — switched to `{profile_name}`\n"
    if note:
        header += f"\n**Note:** {note}\n"
    header += f"\n**Backup:** `config/history/{backup_path.name}`\n\n"
    md = header + _markdown_table(rows) + "\n"
    if not HISTORY_MD.exists():
        HISTORY_MD.write_text("# SwingTrade Config Change History\n\nAppend-only log of profile switches.\n")
    with HISTORY_MD.open("a") as f:
        f.write(md)

    print(f"\n✓ Applied profile '{profile_name}' at {entry['timestamp']}")
    print(f"  Backup: config/history/{backup_path.name}")
    print(f"  History: config/history/HISTORY.md, changes.jsonl\n")
    print(_format_table(rows))
    print(f"\n  {len(rows)} keys changed.")

    # Unified audit log (2026-04-15) — so profile switches appear alongside
    # scan runs, signals, and trades in data/audit.jsonl for attribution joins.
    try:
        import audit
        audit.log("profile_switch", {"to": profile_name, "note": note,
                                     "keys_changed": len(rows),
                                     "backup": backup_path.name},
                  profile=profile_name)
    except Exception:
        pass


def history(limit: int = 20) -> None:
    if not HISTORY_JSONL.exists():
        print("No history yet.")
        return
    lines = HISTORY_JSONL.read_text().splitlines()
    entries = [json.loads(l) for l in lines[-limit:]]
    print(f"\nLast {len(entries)} profile changes (newest last):\n")
    for e in entries:
        ts = e["timestamp"]
        prof = e["profile"]
        n = len(e["changes"])
        note = f" — {e['note']}" if e.get("note") else ""
        print(f"  {ts}  →  {prof}  ({n} keys){note}")
    print()


def current() -> None:
    name = _current_profile_name()
    if name:
        print(f"Active profile: {name}")
        path = PROFILES_DIR / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text())
            print(f"  {data.get('_description', '')}")
    else:
        print("No profile explicitly set (config/config.json is custom or pre-profile-system).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    sub.add_parser("current")
    sub.add_parser("history")

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("profile")

    p_sw = sub.add_parser("switch")
    p_sw.add_argument("profile")
    p_sw.add_argument("--note", default="", help="Optional note to record with this change")

    args = parser.parse_args()

    if args.cmd == "list":
        list_profiles()
    elif args.cmd == "current":
        current()
    elif args.cmd == "history":
        history()
    elif args.cmd == "diff":
        diff(args.profile)
    elif args.cmd == "switch":
        switch(args.profile, args.note)


if __name__ == "__main__":
    main()
