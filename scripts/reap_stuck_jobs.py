#!/usr/bin/env python3
"""
reap_stuck_jobs.py — kill heavy SwingTrade jobs that have hung past a sane max
runtime, so a single stall can't run for DAYS and pile up (the 2026-06-28 incident:
a walk-forward + ml-predict + scan each stuck ~4 days, schedulers stacking new
instances on top → load 408, 1156 procs).

For each heavy job pattern we know roughly how long a healthy run takes; anything
older than the cap is hung → kill the process group. Runs every 30 min via
com.swingtrade.reap-stuck. Best-effort, always exits 0. Slack-alerts what it killed.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# pattern → max healthy runtime (seconds). A run older than this is a hang.
LIMITS = {
    r"run_daily_scan\.sh":  90 * 60,    # a scan should finish in ~20-40m
    r"swing_trade\.py":     90 * 60,
    r"ml\.run_ml_edge":     60 * 60,    # ML inference ~10-20m
    r"backtest\.py":       120 * 60,
    r"walk_forward":       300 * 60,    # WF is long but >5h = hung
}


def _etime_to_secs(et: str) -> int:
    # ps etime: [[DD-]HH:]MM:SS
    et = et.strip()
    days = 0
    if "-" in et:
        d, et = et.split("-", 1)
        days = int(d)
    parts = [int(p) for p in et.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return days * 86400 + h * 3600 + m * 60 + s


def main() -> int:
    try:
        out = subprocess.run(["ps", "-axo", "pid,pgid,etime,command"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception as e:
        print(f"reap: ps failed: {e}", file=sys.stderr)
        return 0

    killed = []
    seen_pgids = set()
    for line in out.splitlines()[1:]:
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*)", line)
        if not m:
            continue
        pid, pgid, etime, cmd = int(m[1]), int(m[2]), m[3], m[4]
        if "reap_stuck_jobs" in cmd or "SwingTrade" not in cmd:
            continue
        for pat, limit in LIMITS.items():
            if re.search(pat, cmd):
                age = _etime_to_secs(etime)
                if age > limit and pgid not in seen_pgids:
                    seen_pgids.add(pgid)
                    try:
                        os.killpg(pgid, signal.SIGKILL)  # whole job tree
                        killed.append((pat, pgid, age // 60))
                        print(f"reap: KILLED pgid={pgid} ({pat}) age={age//60}m > {limit//60}m")
                    except Exception as e:
                        print(f"reap: kill pgid={pgid} failed: {e}", file=sys.stderr)
                break

    if killed:
        try:
            from alerts import send_alert
            body = "\n".join(f"• {p} (pgid {g}, ran {a}m)" for p, g, a in killed)
            send_alert("WARN", f"Reaped {len(killed)} hung job(s)",
                       body + "\n\nA scheduled job hung past its max runtime and was "
                       "killed to prevent pileup. Check why it stalled.")
        except Exception:
            pass
    else:
        print("reap: nothing stuck ✓")
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"reap fatal (suppressed): {e}", file=sys.stderr)
    sys.exit(0)
