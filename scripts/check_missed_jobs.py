#!/usr/bin/env python3
"""
check_missed_jobs.py — missed-scheduled-job watchdog (Phase 5 · Open Risk #11).
==============================================================================
Verifies that the CRITICAL scheduled jobs actually ran in their most-recent
window. The #1 silent failure this guards against: the Mac idle-sleeps overnight
(or over a weekend) and misses the 19:30 EOD-targets pass + the morning chain —
the dashboard then shows stale targets/picks with NO warning. Phase 5 added
`caffeinate -i` to the load-window jobs (launchd_wrapper.sh) to PREVENT that
sleep; this script is the DETECTOR that fires if it happened anyway (sleep
deeper than -i can block, a crashed launchd agent, an unloaded plist, etc).

How it decides "missed"
-----------------------
For each tracked job we know its launchd schedule (weekday set + HH:MM PT). We
compute the most-recent scheduled fire time at-or-before "now" (skipping days
the job doesn't run). Then we look for evidence the job ran AFTER that expected
fire time, from two independent sources:

  1. launchd_wrapper.log  — the authoritative "did this LABEL run" signal. Every
     wrapped job writes "[<UTC>] <LABEL>: START ·" and "... : END · exit=N ...".
     We read the latest START and END per label.
  2. artifact mtime       — a job-specific output file/dir whose freshness is a
     second, independent witness (e.g. cache/last_bundle.json for the scan).

A job is FRESH if EITHER witness is newer than its expected fire time (minus a
grace margin). If a job has a START after the expected time but NO matching END,
we flag it as DID-NOT-FINISH (machine likely slept mid-run) rather than missed.

Output
------
- Prints a freshness table (always).
- If any tracked job is STALE/UNFINISHED → ONE Slack WARN naming the job(s),
  via alerts.send_alert (the canonical helper; auto-loads SLACK_WEBHOOK_URL).
- --dry-run: print the table + the would-alert body, never post to Slack.

Always exits 0 — a watchdog must not fail its own launchd job.

Wired as com.swingtrade.missed-job-check @ ~07:30 PT Mon-Fri (after the morning
chain — scan/strategy-warm/morning-briefing — should all be done).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WRAPPER_LOG = ROOT / "cache" / "logs" / "launchd-wrapper.log"

# Pacific time. Use the IANA zone if available (handles PST/PDT automatically);
# fall back to a fixed -07:00 (PDT) offset on the rare 3.9 build without zoneinfo.
try:
    from zoneinfo import ZoneInfo  # py3.9+
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover - fallback
    PT = timezone(timedelta(hours=-7))

# Monday=0 .. Sunday=6 (Python weekday()). Market jobs run Mon-Fri = {0,1,2,3,4}.
WEEKDAYS_MON_FRI = {0, 1, 2, 3, 4}


class Job:
    """A tracked scheduled job and how to prove it ran recently."""

    def __init__(self, label, fire_times, weekdays, grace_min, artifact=None,
                 critical=True, note=""):
        self.label = label
        self.fire_times = fire_times      # list of (hour, minute) PT
        self.weekdays = weekdays          # set of Python weekday() ints
        self.grace_min = grace_min        # minutes of slack before "stale"
        self.artifact = artifact          # Path | None — secondary freshness witness
        self.critical = critical
        self.note = note

    def last_expected_fire(self, now_pt: datetime) -> datetime | None:
        """Most-recent scheduled fire time at-or-before now (PT, tz-aware).

        Walks back up to 8 days to skip weekends / non-run days.
        """
        for back in range(0, 9):
            day = (now_pt - timedelta(days=back)).date()
            if day.weekday() not in self.weekdays:
                continue
            # candidate fire times on this day, latest first
            cands = sorted(self.fire_times, reverse=True)
            for (hh, mm) in cands:
                fire = datetime(day.year, day.month, day.day, hh, mm, tzinfo=PT)
                if fire <= now_pt:
                    return fire
        return None


# ── Tracked jobs ─────────────────────────────────────────────────────────────
# Schedules mirror the installed plists (PT). Keep in sync with infra/launchd/*.
def _build_jobs() -> list:
    return [
        Job(
            label="com.swingtrade.morning-briefing",
            fire_times=[(6, 30)],
            weekdays=WEEKDAYS_MON_FRI,
            grace_min=120,  # morning chain can stack; allow 2h
            # morning_briefing.py writes data/morning_briefings/<date>.json each
            # run — a clean dated witness that survives wrapper-log rotation.
            artifact=ROOT / "data" / "morning_briefings",
            note="6:30 PT scan + Slack post",
        ),
        Job(
            label="com.swingtrade.strategy-warm",
            fire_times=[(6, 15)],
            weekdays=WEEKDAYS_MON_FRI,
            grace_min=120,
            # strategy-warm logs to /tmp/strategy-warm.log (plist StandardOutPath);
            # it warms the structural-target cache, so a fresh cache/target_engine
            # child is the durable witness. /tmp log is the primary signal.
            artifact=Path("/tmp/strategy-warm.log"),
            note="6:15 PT strategy-pick warm pass",
        ),
        Job(
            label="com.swingtrade.precompute-prewarm",
            fire_times=[(3, 0)],
            weekdays=WEEKDAYS_MON_FRI,
            grace_min=240,  # overnight job, can be long; check by 07:30
            artifact=ROOT / "cache" / "logs" / "precompute_top1000.log",
            note="3:00 PT top-1000 warm-cache batch",
        ),
        Job(
            label="com.swingtrade.eod-targets",
            fire_times=[(19, 30)],
            weekdays=WEEKDAYS_MON_FRI,
            grace_min=300,  # sequenced after ML close-loop; can wait up to 30m + run
            artifact=ROOT / "cache" / "target_engine",
            note="19:30 PT prior-session EOD structural targets",
        ),
        # The daily scan: no single launchd label (runs on a 30-min cadence via
        # run_daily_scan), so prove freshness purely from the bundle artifact.
        Job(
            label="daily-scan (cache/last_bundle.json)",
            fire_times=[(6, 30)],   # first scan of the trading day
            weekdays=WEEKDAYS_MON_FRI,
            grace_min=120,
            artifact=ROOT / "cache" / "last_bundle.json",
            note="latest scan bundle — should refresh every trading morning",
        ),
    ]


# ── Wrapper-log parsing ──────────────────────────────────────────────────────
_LINE_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]\s+"
    r"(?P<label>[\w.\-]+):\s+(?P<event>START|END)\b"
)


def parse_wrapper_log(path: Path):
    """Return {label: {'start': dt|None, 'end': dt|None}} of latest UTC events."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    try:
        # Only the tail matters; read the whole file (it's rotated elsewhere).
        for line in path.read_text(errors="replace").splitlines():
            m = _LINE_RE.match(line)
            if not m:
                continue
            ts = datetime.strptime(m["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
            rec = out.setdefault(m["label"], {"start": None, "end": None})
            key = "start" if m["event"] == "START" else "end"
            if rec[key] is None or ts > rec[key]:
                rec[key] = ts
    except Exception:
        pass
    return out


def _mtime(path: Path | None):
    if not path:
        return None
    try:
        if not path.exists():
            return None
        if path.is_dir():
            # freshest child mtime (the dir mtime itself can lag on rewrites)
            best = path.stat().st_mtime
            for child in path.iterdir():
                try:
                    best = max(best, child.stat().st_mtime)
                except Exception:
                    pass
            return datetime.fromtimestamp(best, tz=timezone.utc)
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(PT).strftime("%a %m-%d %H:%M PT")


def evaluate(now_pt: datetime):
    """Return (rows, missed, unfinished). rows = list of dicts for the table."""
    jobs = _build_jobs()
    wlog = parse_wrapper_log(WRAPPER_LOG)
    rows, missed, unfinished = [], [], []

    for job in jobs:
        expected = job.last_expected_fire(now_pt)
        deadline = (expected + timedelta(minutes=job.grace_min)) if expected else None

        rec = wlog.get(job.label, {"start": None, "end": None})
        last_end = rec.get("end")
        last_start = rec.get("start")
        art_mt = _mtime(job.artifact)

        # Freshest proof-of-run = newest of (wrapper END, artifact mtime).
        proofs = [p for p in (last_end, art_mt) if p is not None]
        freshest = max(proofs) if proofs else None

        status = "OK"
        reason = ""
        if expected is None:
            status = "SKIP"
            reason = "no scheduled window in lookback"
        elif freshest is not None and freshest >= expected:
            status = "OK"
        elif last_start is not None and last_start >= expected and (
            last_end is None or last_end < expected
        ):
            status = "UNFINISHED"
            reason = "started after expected fire but no END (machine slept mid-run?)"
            unfinished.append(job)
        else:
            # No proof at/after the expected fire. Only alert once we're past the
            # grace deadline (a still-running overnight job isn't "missed" yet).
            if deadline is not None and now_pt >= deadline:
                status = "STALE"
                reason = f"no run since expected {_fmt(expected)} (deadline {_fmt(deadline)} passed)"
                missed.append(job)
            else:
                status = "PENDING"
                reason = "within grace window — not yet due"

        rows.append({
            "label": job.label,
            "status": status,
            "expected": expected,
            "freshest": freshest,
            "last_start": last_start,
            "last_end": last_end,
            "artifact_mt": art_mt,
            "reason": reason,
            "note": job.note,
        })
    return rows, missed, unfinished


def render_table(rows) -> str:
    lines = []
    hdr = f"{'JOB':<46} {'STATUS':<11} {'EXPECTED':<18} {'LAST-RUN':<18}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for r in rows:
        lines.append(
            f"{r['label']:<46} {r['status']:<11} "
            f"{_fmt(r['expected']):<18} {_fmt(r['freshest']):<18}"
        )
        if r["reason"]:
            lines.append(f"{'':<46} └ {r['reason']}")
    return "\n".join(lines)


def build_alert_body(missed, unfinished, now_pt) -> str:
    parts = []
    if missed:
        parts.append("MISSED (no run in the expected window):")
        for j in missed:
            exp = j.last_expected_fire(now_pt)
            parts.append(f"  • {j.label} — expected {_fmt(exp)}; {j.note}")
    if unfinished:
        parts.append("UNFINISHED (started but never ended — likely mid-run sleep):")
        for j in unfinished:
            parts.append(f"  • {j.label} — {j.note}")
    parts.append("")
    parts.append("Likely cause: Mac idle-slept overnight or a launchd agent is "
                 "unloaded. Check `pmset -g log | grep Sleep`, then "
                 "`launchctl list | grep swingtrade`.")
    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="check_missed_jobs.py")
    ap.add_argument("--dry-run", action="store_true",
                    help="probe + print, never post to Slack")
    ap.add_argument("--now", default=None,
                    help="override 'now' (ISO, PT) for testing")
    args = ap.parse_args(argv)

    if args.now:
        try:
            now_pt = datetime.fromisoformat(args.now)
            if now_pt.tzinfo is None:
                now_pt = now_pt.replace(tzinfo=PT)
        except Exception:
            print(f"bad --now: {args.now}", file=sys.stderr)
            now_pt = datetime.now(PT)
    else:
        now_pt = datetime.now(PT)

    rows, missed, unfinished = evaluate(now_pt)

    print(f"missed-job check @ {now_pt.strftime('%Y-%m-%d %H:%M %Z')}")
    print(render_table(rows))
    print()

    if not missed and not unfinished:
        print("✓ all tracked jobs fresh — no alert")
        return 0

    flagged = [j.label for j in (missed + unfinished)]
    title = f"Scheduled job(s) missed: {', '.join(flagged)}"
    body = build_alert_body(missed, unfinished, now_pt)

    if args.dry_run:
        print("WOULD ALERT (WARN) — Slack suppressed by --dry-run:")
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
        print(f"check_missed_jobs fatal (suppressed): {e}", file=sys.stderr)
    sys.exit(0)
