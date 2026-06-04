#!/usr/bin/env python3
"""_diag_report.py — Slack START / FINISH alerts for weekly diagnostics.

Posts two messages around the weekly-diagnostics run:
  • START  — when the job kicks off
  • FINISH — # of EODHD calls (billed-unit delta over the run window), run time,
             and which diagnostic snapshots were UPDATED vs still PENDING.

EODHD count comes from cache/eodhd_quota.json (the daily cumulative billed-unit
counter shared across processes). "Calls during the run" = end − start; it's the
best cross-process proxy available (there is no per-job counter), so it may
include a little traffic from other processes active in the same window — labelled
honestly. Reuses lib.autorun_reporter.report() for the actual Slack post.

Usage:
  _diag_report.py start  [--dry]
  _diag_report.py finish <start_epoch> <eodhd_start_count> [--dry]

--dry prints the message it WOULD send and posts nothing (no Slack, no EODHD).
Never raises — alerting is best-effort and must not fail the job.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

JOB = "weekly-diagnostics"
DATE = time.strftime("%Y-%m-%d")

# the core diagnostic snapshots this job refreshes (label → dated path template)
EXPECTED = [
    ("regime_sharpe_decomp", "cache/regime_sharpe_decomp_{d}.json"),
    ("loss_streak",          "cache/loss_streak_investigation_{d}.json"),
    ("sharpe_screen",        "cache/sharpe_screen_{d}.json"),
    ("sharpe_per_regime",    "cache/sharpe_per_regime_{d}.json"),
    ("sharpe_setup_trend",   "cache/sharpe_setup_trend_{d}.json"),
    ("sharpe_kpi",           "cache/sharpe_kpi_{d}.json"),
    ("forensics_weekly",     "cache/forensics_weekly_{d}.json"),
]


def eodhd_count() -> int:
    """Today's cumulative billed-unit EODHD count (0 if unavailable / stale date)."""
    try:
        st = json.loads((REPO / "cache" / "eodhd_quota.json").read_text())
        if st.get("date") and st.get("date") != DATE:
            return 0  # counter is for another day → treat as fresh
        return int(st.get("count", 0))
    except Exception:
        return 0


def fmt_dur(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _emit(status: str, summary: str, details: dict, duration: float | None, dry: bool) -> None:
    if dry:
        print(f"[DRY] status={status}")
        print(f"[DRY] summary:\n{summary}")
        print(f"[DRY] details: {json.dumps(details)}")
        if duration is not None:
            print(f"[DRY] duration_sec={duration:.0f}")
        return
    try:
        from lib.autorun_reporter import report
        ok = report(JOB, status, summary=summary, duration_sec=duration, details=details)
        print(f"Slack: {'sent' if ok else 'skipped (no webhook)'}")
    except Exception as e:  # never crash the job
        print(f"Slack: failed ({e})")


def do_start(dry: bool) -> None:
    cnt = eodhd_count()
    _emit("info",
          summary=f"⏳ *Weekly diagnostics STARTED* — {len(EXPECTED)} snapshots queued.",
          details={"started": time.strftime("%H:%M:%S PT"),
                   "EODHD billed-units today (pre-run)": cnt},
          duration=None, dry=dry)


def do_finish(start_epoch: float, eodhd_start: int, dry: bool) -> None:
    end = eodhd_count()
    calls = end - eodhd_start
    if calls < 0:           # day rolled over mid-run → counter reset
        calls = end
    dur = time.time() - start_epoch

    updated, pending = [], []
    for label, tmpl in EXPECTED:
        p = REPO / tmpl.format(d=DATE)
        # "updated" = exists AND refreshed during this run (mtime within the window)
        if p.exists() and p.stat().st_mtime >= (start_epoch - 5):
            updated.append(label)
        else:
            pending.append(label)

    status = "success" if not pending else "warning"
    head = "✅" if not pending else "⚠️"
    summary = (f"{head} *Weekly diagnostics FINISHED* — "
               f"{len(updated)}/{len(EXPECTED)} snapshots refreshed · "
               f"{calls} EODHD units · {fmt_dur(dur)}\n"
               f"*Updated:* {', '.join(updated) or 'none'}")
    if pending:
        summary += f"\n*Pending:* {', '.join(pending)}"

    details = {
        "EODHD API calls (billed units, Δ run window)": calls,
        "run time": fmt_dur(dur),
        "data updated": f"{len(updated)}/{len(EXPECTED)}",
        "pending": ", ".join(pending) if pending else "none",
    }
    _emit(status, summary, details, duration=dur, dry=dry)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv
    mode = args[0] if args else "start"
    try:
        if mode == "start":
            do_start(dry)
        elif mode == "finish":
            start_epoch = float(args[1]) if len(args) > 1 else time.time()
            eodhd_start = int(args[2]) if len(args) > 2 else 0
            do_finish(start_epoch, eodhd_start, dry)
        else:
            print(f"unknown mode '{mode}' (use start|finish)")
    except Exception as e:  # best-effort
        print(f"_diag_report error: {e}")


if __name__ == "__main__":
    main()
