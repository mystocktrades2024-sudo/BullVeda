#!/usr/bin/env python3
"""
heartbeat_check.py — launchd-fleet + ML-feedback-loop heartbeat.
================================================================
A *liveness* watchdog, complementary to check_missed_jobs.py:

  - check_missed_jobs.py answers "did these 5 CRITICAL jobs RUN in their window?"
    (wrapper-log + artifact mtime, per-job schedules).
  - heartbeat_check.py answers "is the whole launchd FLEET still LOADED, and is
    the ML close-loop feedback ledger still being FED?"

Motivation (2026-06-17): com.swingtrade.ml-close-loop silently unloaded for ~7
days. Nothing alerted — the dashboard kept showing confident ML numbers while no
prediction was being scored against reality, so calibration drifted invisibly.
This check is the detector for that whole failure class: a plist that exists but
is no longer loaded, plus a feedback ledger that has gone stale.

Two checks
----------
1. FLEET COMPLETENESS — every infra/launchd/com.swingtrade.*.plist (excluding
   *.retired) must appear in `launchctl list`. Any expected-but-missing label is
   a silent unload. (EXCLUDE holds labels that are intentionally not loaded.)

2. CLOSE-LOOP LIVENESS — the close-loop runner writes a dated log
   cache/logs/ml_close_loop_<YYYYMMDD>.log every run (the job fires daily 19:00
   PT). If the newest such log is older than CLOSE_LOOP_MAX_AGE_H, the loop has
   stopped feeding. Secondary witness: the newest `resolved_at` in
   cache/ml_edge_picks_history.jsonl — flagged only past a much longer horizon
   (LEDGER_STALL_H) since it legitimately doesn't advance over weekends or while
   recent picks are still maturing to their horizon.

WARN (not CRITICAL): a stale feedback loop degrades quality but doesn't take the
system down. One Slack WARN per run via alerts.send_alert. Always exits 0 — a
watchdog must never fail its own launchd job.

Wired into scripts/weekly_diagnostics.sh (Sunday 5pm PT). --dry-run prints the
report and the would-alert body without posting.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LAUNCHD_DIR = ROOT / "infra" / "launchd"
CLOSE_LOOP_LOG_GLOB = "ml_close_loop_*.log"
LOGS_DIR = ROOT / "cache" / "logs"
LEDGER = ROOT / "cache" / "ml_edge_picks_history.jsonl"

# Labels that are intentionally NOT loaded — keep empty unless a job is
# deliberately parked. (.retired plists are already excluded by the glob.)
EXCLUDE: set[str] = set()

CLOSE_LOOP_MAX_AGE_H = 48     # close-loop runs daily; >48h ⇒ it stopped running
LEDGER_STALL_H = 120          # 5d: weekend + maturation can't explain past this
NAS_SYNC_MAX_AGE_H = 26       # nas-sync + code-backup run nightly; >26h ⇒ stale/failed
# Success markers written ONLY on a genuine completion (catches the exit=0-but-0s
# silent-failure class). Mtime = last good sync.
NAS_MARKERS = {
    "NAS data sync (Postgres)": ROOT / "cache" / "logs" / ".nas_data_sync_ok",
    "NAS code backup (SSH)":    ROOT / "cache" / "logs" / ".nas_code_backup_ok",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_age(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return "—"
    h = (now - dt).total_seconds() / 3600.0
    return f"{dt.astimezone().strftime('%a %m-%d %H:%M')} ({h:.0f}h ago)"


# ── Check 1: launchd fleet completeness ──────────────────────────────────────
def check_fleet() -> tuple[list[str], int]:
    """Return (missing_labels, expected_count)."""
    expected = sorted(
        p.stem for p in LAUNCHD_DIR.glob("com.swingtrade.*.plist")
    )  # .stem drops only the final .plist; *.retired files don't match the glob
    loaded: set[str] = set()
    try:
        out = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=15
        ).stdout
        for line in out.splitlines():
            parts = line.split("\t")
            if parts and parts[-1].startswith("com.swingtrade."):
                loaded.add(parts[-1])
    except Exception as e:
        print(f"heartbeat: launchctl list failed ({e}) — skipping fleet check",
              file=sys.stderr)
        return [], len(expected)
    missing = [lbl for lbl in expected if lbl not in loaded and lbl not in EXCLUDE]
    return missing, len(expected)


# ── Check 2: ML close-loop liveness ──────────────────────────────────────────
def _newest_close_loop_log(now: datetime) -> datetime | None:
    logs = list(LOGS_DIR.glob(CLOSE_LOOP_LOG_GLOB))
    if not logs:
        return None
    newest = max(p.stat().st_mtime for p in logs)
    return datetime.fromtimestamp(newest, tz=timezone.utc)


def _newest_resolved_at() -> datetime | None:
    """Newest resolved_at across the close-loop ledger (scan the tail cheaply)."""
    if not LEDGER.exists():
        return None
    newest: datetime | None = None
    try:
        with LEDGER.open() as fh:
            for line in fh:
                if '"resolved_at"' not in line:
                    continue
                try:
                    ra = json.loads(line).get("resolved_at")
                except Exception:
                    continue
                if not ra:
                    continue
                try:
                    dt = datetime.fromisoformat(ra.replace("Z", "+00:00"))
                except Exception:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if newest is None or dt > newest:
                    newest = dt
    except Exception:
        return newest
    return newest


def check_close_loop(now: datetime) -> tuple[list[str], datetime | None, datetime | None]:
    """Return (problems, newest_log_dt, newest_resolved_dt)."""
    problems: list[str] = []
    log_dt = _newest_close_loop_log(now)
    resolved_dt = _newest_resolved_at()

    if log_dt is None:
        problems.append("close-loop has NO run log in cache/logs/ — never ran?")
    elif (now - log_dt) > timedelta(hours=CLOSE_LOOP_MAX_AGE_H):
        problems.append(
            f"close-loop last ran {_fmt_age(log_dt, now)} "
            f"— exceeds {CLOSE_LOOP_MAX_AGE_H}h (feedback loop stalled)"
        )

    if resolved_dt is not None and (now - resolved_dt) > timedelta(hours=LEDGER_STALL_H):
        problems.append(
            f"ledger newest resolved_at {_fmt_age(resolved_dt, now)} "
            f"— exceeds {LEDGER_STALL_H}h (no prediction scored in >5d)"
        )
    return problems, log_dt, resolved_dt


def check_nas_sync(now: datetime) -> tuple[list[str], dict]:
    """Each NAS sync must have written its success marker within NAS_SYNC_MAX_AGE_H.
    A missing/stale marker means the nightly sync hasn't genuinely succeeded — even
    if its launchd job reported exit=0 (the 0s-do-nothing failure we hit on the
    stale SMB mount). Returns (problems, {name: marker_dt|None})."""
    problems, ages = [], {}
    for name, path in NAS_MARKERS.items():
        dt = None
        if path.exists():
            dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        ages[name] = dt
        if dt is None:
            problems.append(f"{name}: no success marker — has it ever completed?")
        elif (now - dt) > timedelta(hours=NAS_SYNC_MAX_AGE_H):
            problems.append(f"{name}: last success {_fmt_age(dt, now)} "
                            f"— exceeds {NAS_SYNC_MAX_AGE_H}h (sync stale/failed)")
    return problems, ages


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="heartbeat_check.py")
    ap.add_argument("--dry-run", action="store_true",
                    help="print report + would-alert body, never post to Slack")
    args = ap.parse_args(argv)

    now = _now()
    missing, n_expected = check_fleet()
    cl_problems, log_dt, resolved_dt = check_close_loop(now)
    nas_problems, nas_ages = check_nas_sync(now)

    # ── report (always) ──
    print(f"heartbeat @ {now.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  launchd fleet : {n_expected - len(missing)}/{n_expected} loaded"
          + (f"  ⚠ MISSING: {', '.join(missing)}" if missing else "  ✓"))
    print(f"  close-loop log: {_fmt_age(log_dt, now)}")
    print(f"  ledger resolved_at: {_fmt_age(resolved_dt, now)}")
    for name, dt in nas_ages.items():
        print(f"  {name}: {_fmt_age(dt, now)}")
    for p in cl_problems + nas_problems:
        print(f"    ⚠ {p}")

    problems: list[str] = []
    if missing:
        problems.append(
            f"{len(missing)} launchd job(s) expected-but-unloaded: "
            + ", ".join(missing)
        )
    problems.extend(cl_problems)
    problems.extend(nas_problems)

    if not problems:
        print("✓ heartbeat OK — fleet fully loaded, close-loop fresh")
        return 0

    title = "Heartbeat: " + (
        f"{len(missing)} job(s) unloaded" if missing
        else "NAS sync stale" if nas_problems
        else "ML close-loop stalled"
    )
    body = "\n".join(f"• {p}" for p in problems) + (
        "\n\nReload: launchctl load -w infra/launchd/<label>.plist"
    )

    if args.dry_run:
        print("\nWOULD ALERT (WARN) — Slack suppressed by --dry-run:")
        print(f"  title: {title}")
        for ln in body.splitlines():
            print(f"  {ln}")
        return 0

    try:
        from alerts import send_alert
        send_alert("WARN", title, body)
        print(f"⚠ WARN alert sent: {title}")
    except Exception as e:  # never fail the watchdog
        print(f"alert send failed (non-fatal): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # Always exit 0 — a watchdog must not fail its own launchd job.
    try:
        main()
    except Exception as e:
        print(f"heartbeat_check fatal (suppressed): {e}", file=sys.stderr)
    sys.exit(0)
