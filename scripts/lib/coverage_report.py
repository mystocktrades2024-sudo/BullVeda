#!/usr/bin/env python3
"""coverage_report.py — shared warm/precompute observability helper (Open Risk #12).

Today the warm passes (`scripts/precompute_top1000.py`, `scripts/precompute_targets.py`)
track success/reject/errors internally and append a JSON line to
`cache/logs/precompute_*.log`, but NOTHING reports whether the warm actually
worked end-to-end. This helper closes that gap:

  1. Computes a single coverage% = warmed / total (+ optional per-mode breakdown).
  2. Writes/updates a machine-readable metric file `cache/loader_coverage.json`
     keyed by job — so a dashboard / healthcheck can read one number per loader.
  3. Posts a one-line Slack heartbeat (reusing the SLACK_WEBHOOK_URL convention)
     so a degraded warm is visible without grepping logs.

Slack noise control: by default it only posts when coverage < 100% (something
went wrong) OR when `slack_always=True` (the daily "all-green" heartbeat).
A clean run with slack_always=False stays silent.

Usage (additive — callers don't change their core warm logic):

    from lib.coverage_report import emit_coverage

    emit_coverage(
        job="precompute_top1000",
        stats={"total": 1380, "warmed": 1340, "failed": 40,
               "duration_s": 1440, "by_mode": {...}},
        slack=True,            # attempt a post (subject to threshold)
        slack_always=False,    # only post on degraded coverage
    )

Field mapping: callers map their internal counters into the canonical keys
`total` / `warmed` / `failed` (and optionally `duration_s`, `by_mode`) before
calling — keeping this helper schema-agnostic.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
METRIC_FILE = ROOT / "cache" / "loader_coverage.json"
ENV_FILE = ROOT / ".env"


# ──────────────────────────────────────────────────────────────────────────
# Slack webhook (same convention as scripts/slack_eod_summary.py etc.)
# ──────────────────────────────────────────────────────────────────────────
def _webhook() -> str | None:
    """SLACK_WEBHOOK_URL from env first, then .env file. Fail-soft → None."""
    import os
    wh = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if wh:
        return wh.strip('"').strip("'")
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _post_slack(text: str) -> bool:
    """Post a plain-text Slack line. If no webhook, PRINT it instead (dry path)."""
    wh = _webhook()
    if not wh:
        print(f"[coverage] (no SLACK_WEBHOOK_URL — would post) {text}")
        return False
    try:
        req = urllib.request.Request(
            wh,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=8)
        print(f"[coverage] Slack posted (HTTP {r.status})")
        return True
    except Exception as e:  # never let observability break the warm job
        print(f"[coverage] Slack post failed (non-fatal): {e}", file=sys.stderr)
        return False


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def _num(stats: dict, *keys, default: float = 0.0) -> float:
    """First present numeric key wins."""
    for k in keys:
        v = stats.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return float(default)


def _fmt_dur(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m} min" if sec == 0 else f"{m}m {sec}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _coverage_emoji(pct: float) -> str:
    if pct >= 99.0:
        return "🟢"
    if pct >= 90.0:
        return "🟡"
    return "🔴"


def compute(stats: dict) -> dict:
    """Normalize a caller's stats dict into the canonical coverage record.

    Recognized input keys (first match wins per field):
      total   ← total / attempted / warm_set
      warmed  ← warmed / success / ok
      failed  ← failed / errors / err
      duration_s ← duration_s / elapsed_sec / elapsed
      by_mode ← by_mode (dict mode→{total,warmed,...} or mode→pct)
    """
    total = _num(stats, "total", "attempted", "warm_set")
    warmed = _num(stats, "warmed", "success", "ok")
    failed = _num(stats, "failed", "errors", "err")
    duration = _num(stats, "duration_s", "elapsed_sec", "elapsed")

    # If total wasn't supplied, fall back to warmed+failed.
    if total <= 0:
        total = warmed + failed

    coverage_pct = round((warmed / total) * 100.0, 1) if total > 0 else 0.0

    by_mode = stats.get("by_mode")
    by_mode_out: dict[str, Any] | None = None
    if isinstance(by_mode, dict) and by_mode:
        by_mode_out = {}
        for mode, mv in by_mode.items():
            if isinstance(mv, dict):
                mt = _num(mv, "total", "attempted")
                mw = _num(mv, "warmed", "success", "ok")
                mf = _num(mv, "failed", "errors", "err")
                if mt <= 0:
                    mt = mw + mf
                by_mode_out[mode] = {
                    "total": int(mt),
                    "warmed": int(mw),
                    "failed": int(mf),
                    "coverage_pct": round((mw / mt) * 100.0, 1) if mt > 0 else 0.0,
                }
            elif isinstance(mv, (int, float)):
                by_mode_out[mode] = {"coverage_pct": round(float(mv), 1)}

    return {
        "total": int(total),
        "warmed": int(warmed),
        "failed": int(failed),
        "coverage_pct": coverage_pct,
        "duration_s": round(duration, 1),
        "by_mode": by_mode_out,
    }


def _write_metric(job: str, rec: dict) -> None:
    """Merge this job's record into cache/loader_coverage.json (keyed by job)."""
    METRIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    book: dict = {}
    if METRIC_FILE.exists():
        try:
            loaded = json.loads(METRIC_FILE.read_text())
            if isinstance(loaded, dict):
                book = loaded
        except Exception:
            book = {}
    book[job] = rec
    tmp = METRIC_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(book, indent=2))
    tmp.replace(METRIC_FILE)


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────
def emit_coverage(job: str, stats: dict, slack: bool = True,
                  slack_always: bool = False) -> dict:
    """Compute coverage, persist the metric, and (optionally) post to Slack.

    Args:
        job: loader name / key (e.g. "precompute_top1000").
        stats: caller's stats dict (mapped via canonical-key fallbacks).
        slack: if True, ATTEMPT a Slack post (subject to threshold below).
        slack_always: if True, always post (daily heartbeat); if False, only
            post when coverage < 100% (i.e. something failed) to avoid noise.

    Returns the written metric record (so callers can assert on it in tests).
    """
    cov = compute(stats)
    rec = {
        "job": job,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": cov["total"],
        "warmed": cov["warmed"],
        "failed": cov["failed"],
        "coverage_pct": cov["coverage_pct"],
        "duration_s": cov["duration_s"],
        "by_mode": cov["by_mode"],
    }
    _write_metric(job, rec)

    line = (
        f"{_coverage_emoji(cov['coverage_pct'])} *{job}*: "
        f"warmed {cov['warmed']:,}/{cov['total']:,} "
        f"({cov['coverage_pct']:.1f}%) · {cov['failed']:,} failed · "
        f"{_fmt_dur(cov['duration_s'])}"
    )
    if cov["by_mode"]:
        parts = [
            f"{m} {d.get('coverage_pct', 0):.0f}%"
            for m, d in cov["by_mode"].items()
        ]
        line += "  ·  " + " / ".join(parts)

    # Always print the human line to stdout (cheap, log-visible heartbeat).
    print(f"\n── coverage ──\n  {line.replace('*', '')}")

    if slack:
        should_post = slack_always or cov["coverage_pct"] < 100.0
        if should_post:
            _post_slack(line)
        else:
            print("[coverage] coverage 100% and slack_always=False → no Slack post (noise control)")

    return rec


if __name__ == "__main__":
    # Tiny self-test / demo (no Slack post unless a webhook is set).
    demo = emit_coverage(
        job="coverage_selftest",
        stats={"total": 1380, "warmed": 1340, "failed": 40, "duration_s": 1440,
               "by_mode": {"swing": {"total": 460, "warmed": 450, "failed": 10},
                           "position": {"total": 460, "warmed": 448, "failed": 12},
                           "invest": {"total": 460, "warmed": 442, "failed": 18}}},
        slack=False,
    )
    print("\nwritten record:")
    print(json.dumps(demo, indent=2))
