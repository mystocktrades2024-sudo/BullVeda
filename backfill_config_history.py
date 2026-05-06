"""
backfill_config_history.py — One-time backfill of pre-profile-system config history.

The audit/profile system started 2026-04-15. This script walks git history
for config/config.json, extracts each historical version, and writes:

  - config/history/config_backup_<YYYYMMDD_HHMMSS>.json  (one per commit)
  - A row in config/history/changes.jsonl              (type='config_commit')
  - A row in data/audit.jsonl                          (type='config_commit')
  - A row in config/history/HISTORY.md                 (human-readable)

Each entry carries the real commit timestamp + hash + subject + changed-keys
so the Settings → Recent Audit Events view shows the full timeline.

Idempotent: re-running skips commits already recorded (keyed by commit hash).

Usage:
  python3 backfill_config_history.py                # dry run (prints plan)
  python3 backfill_config_history.py --apply         # actually write
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE    = Path(__file__).parent
CONFIG  = "SwingTrade/config/config.json"  # path as git sees it
CFG_LOCAL = BASE / "config" / "config.json"
HIST_DIR = BASE / "config" / "history"
JSONL    = HIST_DIR / "changes.jsonl"
MD       = HIST_DIR / "HISTORY.md"
AUDIT    = BASE / "data" / "audit.jsonl"
MARKER   = HIST_DIR / ".backfilled_commits.json"


def _git_root() -> Path:
    # Script lives at /Volumes/MyMacDisk/Claude Skills/SwingTrade;
    # git repo root is typically one level up.
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(BASE), text=True).strip()
    return Path(out)


def _git_log() -> list[dict]:
    """Return list of {hash, iso_ts, subject} for commits touching config.json, oldest first."""
    root = _git_root()
    # Path relative to git root:
    rel = str(CFG_LOCAL.resolve().relative_to(root))
    out = subprocess.check_output(
        ["git", "log", "--all", "--reverse",
         "--pretty=format:%H|%aI|%s", "--", rel],
        cwd=str(root), text=True)
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "ts": parts[1], "subject": parts[2]})
    return commits


def _git_show(commit_hash: str) -> str | None:
    """Return config.json text at a given commit, or None if unavailable."""
    root = _git_root()
    rel = str(CFG_LOCAL.resolve().relative_to(root))
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit_hash}:{rel}"],
            cwd=str(root), text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None


def _load_marker() -> set[str]:
    if MARKER.exists():
        try:
            return set(json.loads(MARKER.read_text()).get("hashes", []))
        except Exception:
            return set()
    return set()


def _save_marker(hashes: set[str]) -> None:
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"hashes": sorted(hashes),
                                  "last_updated": datetime.now(timezone.utc).isoformat()}, indent=2))


def _summarize_diff(prev_text: str | None, curr_text: str) -> dict:
    """Count changed top-level config keys between two JSON strings."""
    try:
        curr = json.loads(curr_text)
    except json.JSONDecodeError:
        return {"keys_changed": 0, "note": "config not valid JSON at this commit"}
    try:
        prev = json.loads(prev_text) if prev_text else {}
    except json.JSONDecodeError:
        prev = {}
    changed = []
    for k in set(list(prev.keys()) + list(curr.keys())):
        if prev.get(k) != curr.get(k):
            changed.append(k)
    return {"keys_changed": len(changed), "changed_top_level": sorted(changed)}


def run(apply: bool = False) -> None:
    commits = _git_log()
    if not commits:
        print("No git history found for config.json")
        return

    seen = _load_marker()
    to_process = [c for c in commits if c["hash"] not in seen]

    print(f"Git config commits total:   {len(commits)}")
    print(f"Already backfilled:         {len(seen)}")
    print(f"New to backfill this run:   {len(to_process)}")
    if not to_process:
        print("Nothing to do.")
        return

    print()
    print(f"{'Date':<20} {'Hash':<10} {'Subject':<50} {'Keys':>5}")
    print("-" * 90)

    new_seen = set(seen)
    prev_text: str | None = None
    # Rebuild prev from the commit immediately before the earliest unseen one
    if commits and commits[0]["hash"] in seen:
        # Find the last already-seen commit before each new commit
        pass  # simple linear walk below

    for c in commits:
        txt = _git_show(c["hash"])
        if txt is None:
            continue
        if c["hash"] in seen:
            prev_text = txt
            continue

        summary = _summarize_diff(prev_text, txt)
        ts = c["ts"]  # ISO with offset
        dt_obj = datetime.fromisoformat(ts)
        date_str = dt_obj.strftime("%Y-%m-%d %H:%M")
        backup_stamp = dt_obj.strftime("%Y%m%d_%H%M%S")

        subj = c["subject"][:48]
        print(f"{date_str:<20} {c['hash'][:9]:<10} {subj:<50} {summary['keys_changed']:>5}")

        if apply:
            HIST_DIR.mkdir(parents=True, exist_ok=True)
            AUDIT.parent.mkdir(parents=True, exist_ok=True)
            backup_path = HIST_DIR / f"config_backup_{backup_stamp}_{c['hash'][:7]}.json"
            backup_path.write_text(txt)

            entry = {
                "timestamp":  dt_obj.astimezone().isoformat(timespec="seconds"),
                "date":       dt_obj.strftime("%Y-%m-%d"),
                "type":       "config_commit",
                "commit":     c["hash"],
                "commit_short": c["hash"][:7],
                "subject":    c["subject"],
                "keys_changed": summary.get("keys_changed", 0),
                "changed_top_level": summary.get("changed_top_level", []),
                "backup":     backup_path.name,
                "source":     "backfill",
            }
            with JSONL.open("a") as f:
                f.write(json.dumps(entry) + "\n")

            audit_entry = {
                "ts":       dt_obj.astimezone(timezone.utc).isoformat(),
                "type":     "config_commit",
                "profile":  None,
                "payload":  {k: entry[k] for k in
                             ("commit_short", "subject", "keys_changed",
                              "changed_top_level", "backup", "date")}
            }
            with AUDIT.open("a") as f:
                f.write(json.dumps(audit_entry) + "\n")

            if not MD.exists():
                MD.write_text("# SwingTrade Config Change History\n\nAppend-only log of profile switches and config commits.\n")
            with MD.open("a") as f:
                f.write(f"\n## {date_str} — commit `{c['hash'][:7]}` — {c['subject']}\n\n")
                f.write(f"- Backup: `config/history/{backup_path.name}`\n")
                f.write(f"- Top-level keys changed: {summary['keys_changed']} — {', '.join(summary.get('changed_top_level', [])) or '—'}\n")

        new_seen.add(c["hash"])
        prev_text = txt

    if apply:
        _save_marker(new_seen)
        print()
        print(f"Wrote {len(to_process)} entries. Marker updated: {MARKER}")
        print(f"View in UI: http://localhost:7432/ → ⚙ Settings → Recent Audit Events (filter: config_commit)")
    else:
        print()
        print("Dry run — re-run with --apply to actually write.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually write backup/history/audit entries")
    args = ap.parse_args()
    run(apply=args.apply)
