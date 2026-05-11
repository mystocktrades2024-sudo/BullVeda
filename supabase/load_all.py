#!/usr/bin/env python3
"""Orchestrator: applies all migrations then runs every loader, in order.

Usage:
    python3 supabase/load_all.py                # full migration + load
    python3 supabase/load_all.py --skip-apply   # skip DDL, just load data
    python3 supabase/load_all.py --smoke        # decision_log capped at 5000 rows
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-apply", action="store_true", help="skip DDL migrations")
    ap.add_argument("--smoke",      action="store_true", help="cap decision_log at 5000 rows")
    args = ap.parse_args()

    py = sys.executable

    if not args.skip_apply:
        rc = run([py, str(HERE / "apply.py")])
        if rc != 0:
            print("✗ DDL migration failed — aborting")
            sys.exit(rc)

    rc = run([py, str(HERE / "scripts" / "load_reference.py")])
    if rc != 0:
        print("✗ reference loader failed — continuing for visibility")

    rc = run([py, str(HERE / "scripts" / "load_sqlite.py")])
    if rc != 0:
        print("✗ sqlite loader failed — continuing")

    json_cmd = [py, str(HERE / "scripts" / "load_json.py")]
    if args.smoke:
        json_cmd += ["--decision-log-max", "5000"]
    rc = run(json_cmd)
    if rc != 0:
        print("✗ json loader failed — continuing")

    print("\n--- VERIFY ---")
    run([py, str(HERE / "scripts" / "verify.py")])


if __name__ == "__main__":
    main()
