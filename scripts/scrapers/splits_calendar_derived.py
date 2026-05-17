#!/usr/bin/env python3
"""
splits_calendar_derived.py — Project rows from corporate_actions WHERE
action_type='split' into splits_calendar. No new fetch — purely derived.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sb = load_env_and_supabase()

    try:
        data = sb.table("corporate_actions").select("ticker,ex_date,ratio,raw_json").eq("action_type", "split").limit(5000).execute().data or []
    except Exception as e:
        print(f"✗ select: {e}"); return 1
    print(f"  Found {len(data)} splits in corporate_actions")
    rows = []
    for s in data:
        ratio = s.get("ratio")
        if ratio is None:
            continue
        direction = "forward" if ratio > 1 else "reverse"
        rows.append({
            "ticker": s["ticker"],
            "ex_date": s["ex_date"],
            "ratio": ratio,
            "direction": direction,
            "sync_key": h("sp", s["ticker"], s["ex_date"]),
            "raw_json": s.get("raw_json"),
        })
    print(f"  Normalized {len(rows)} splits_calendar rows")
    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "splits_calendar", rows, "sync_key")
    print(f"  pushed={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
