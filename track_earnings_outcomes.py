#!/usr/bin/env python3
"""
track_earnings_outcomes.py — capture earnings BEAT/MISS post-event.

Daily script that polls EODHD's earnings calendar for actuals, joins with
the per-ticker estimate snapshot, and stores the outcome in
data/earnings_outcomes.jsonl. Append-only.

Schema:
  {ticker, report_date, estimate, actual, surprise_pct, beat, captured_at}

  beat: "BEAT" | "MISS" | "INLINE" (within 1% of estimate)

Schedule: daily 1:30pm PT (after AMC reports and morning BMO data has settled).

Use: per-setup beat-rate stat — feeds the audit trail / performance attribution.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "earnings_outcomes.log"
OUT_FILE = BASE / "data" / "earnings_outcomes.jsonl"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [earn_outcomes] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _load_env() -> None:
    env_path = BASE / ".env"
    if not env_path.exists(): return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _is_us(code: str) -> bool:
    if "." not in code: return True
    return code.rsplit(".", 1)[1].upper() == "US"


def _strip(code: str) -> str:
    return code.split(".")[0].upper() if code else ""


def _already_captured() -> set:
    """Return {(ticker, report_date)} tuples already in our log."""
    if not OUT_FILE.exists(): return set()
    seen = set()
    for line in OUT_FILE.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
            seen.add((e.get("ticker"), e.get("report_date")))
        except Exception:
            continue
    return seen


def main(lookback_days: int = 5) -> int:
    """Capture last N days of completed earnings (with `actual` populated)."""
    _load_env()
    today = date.today()
    start = today - timedelta(days=lookback_days)

    log.info(f"Polling EODHD earnings calendar {start} → {today} ({lookback_days}d back)")
    import eodhd_client as e
    try:
        raw = e.earnings_calendar(from_date=str(start), to_date=str(today))
    except e.EODHDError as _qe:
        # Quota soft-limit defer (the guard's intended behavior) or a persistent EODHD
        # error. This is a NON-ESSENTIAL daily back-fill; skip cleanly (exit 0) instead
        # of crashing the launchd job. The 5-day lookback window recaptures any missed
        # report dates on the next run. (Fix 2026-06-04: was exiting 1 on quota-defer.)
        log.warning(f"earnings_calendar deferred/failed — skipping this run (non-fatal): {_qe}")
        return 0
    except Exception as _ne:
        log.warning(f"earnings_calendar network/transient error — skipping this run (non-fatal): {_ne}")
        return 0
    if not isinstance(raw, dict):
        log.error("earnings_calendar returned non-dict")
        return 1
    entries = raw.get("earnings") or raw.get("data") or []

    seen = _already_captured()
    new_rows = []
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code", "")
        if not _is_us(code): continue
        ticker = _strip(code)
        rep_date = entry.get("report_date")
        actual = entry.get("actual")
        estimate = entry.get("estimate")
        # Only capture once we have an actual reported (rules out future dates)
        if actual is None: continue
        if not rep_date or not ticker: continue
        key = (ticker, rep_date)
        if key in seen: continue
        # Compute surprise %
        try:
            est = float(estimate) if estimate is not None else None
            act = float(actual)
        except (TypeError, ValueError):
            est, act = None, None
        if est is None or act is None or abs(est) < 1e-6:
            surprise_pct = None
            beat = "INLINE"
        else:
            surprise_pct = round((act - est) / abs(est) * 100, 2)
            if surprise_pct > 1.0: beat = "BEAT"
            elif surprise_pct < -1.0: beat = "MISS"
            else: beat = "INLINE"
        row = {
            "ticker":       ticker,
            "report_date":  rep_date,
            "estimate":     est,
            "actual":       act,
            "surprise_pct": surprise_pct,
            "beat":         beat,
            "before_after_market": entry.get("before_after_market") or "",
            "captured_at":  datetime.now().isoformat(),
        }
        new_rows.append(row)

    if not new_rows:
        log.info("No new outcomes since last run")
        return 0

    with OUT_FILE.open("a") as f:
        for r in new_rows:
            f.write(json.dumps(r) + "\n")

    beats = sum(1 for r in new_rows if r["beat"] == "BEAT")
    misses = sum(1 for r in new_rows if r["beat"] == "MISS")
    inline = sum(1 for r in new_rows if r["beat"] == "INLINE")
    log.info(f"Captured {len(new_rows)} new outcomes  ·  BEAT={beats}  MISS={misses}  INLINE={inline}")
    return 0


if __name__ == "__main__":
    sys.exit(main(lookback_days=5))
