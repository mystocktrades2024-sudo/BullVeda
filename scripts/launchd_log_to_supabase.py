#!/usr/bin/env python3
"""launchd_log_to_supabase.py — write a single launchd_runs row to Supabase.
Invoked by launchd_wrapper.sh after each plist firing."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--started-at", required=True)
    ap.add_argument("--finished-at", required=True)
    ap.add_argument("--duration-s", type=int, required=True)
    ap.add_argument("--exit-code", type=int, required=True)
    ap.add_argument("--stdout-tail", default="")
    args = ap.parse_args()

    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    try:
        from supabase_client import sb_client
        sb = sb_client()
        if sb is None:
            return 0
    except Exception:
        return 0

    sync_key = hashlib.sha1(f"{args.label}|{args.started_at}".encode()).hexdigest()[:32]
    row = {
        "plist_label": args.label,
        "started_at": args.started_at,
        "finished_at": args.finished_at,
        "duration_s": float(args.duration_s),
        "exit_code": args.exit_code,
        "success": args.exit_code == 0,
        "stdout_tail": (args.stdout_tail or "")[:2000],
        "stderr_tail": "",
        "host": "mac-local",
        "sync_key": sync_key,
        "raw_json": json.dumps({"label": args.label, "exit": args.exit_code, "duration_s": args.duration_s}),
    }
    try:
        sb.table("launchd_runs").upsert([row], on_conflict="sync_key").execute()
    except Exception as e:
        print(f"supabase write failed: {e}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
