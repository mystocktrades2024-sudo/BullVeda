#!/usr/bin/env python3
"""
backfill_signal_log_regime.py — recover regime4 for closed signals from scan logs.

The scan logs at cache/logs/scan_YYYYMMDD_HHMMSS.log record the regime4
state at scan time. For closed signals with null regime4, look up the
scan log matching their entry date and extract the regime.

One-time cleanup. Future signals get regime4 stamped at write time via
signal_tracker.log_signals (swing_trade.py:2967).

Usage: python3 scripts/backfill_signal_log_regime.py [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _build_date_to_regime() -> dict[str, str]:
    """Scan all log files, build YYYY-MM-DD → regime4 mapping."""
    out: dict[str, str] = {}
    for log in sorted((REPO / "cache" / "logs").glob("scan_*.log")):
        m = re.match(r"scan_(\d{8})_", log.name)
        if not m:
            continue
        ymd = m.group(1)
        date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
        if date in out:
            continue  # first scan of the day wins
        try:
            txt = log.read_text(errors="ignore")
        except Exception:
            continue
        # Look for regime4 mentions in the log body
        rm = re.search(r"regime4['\":]?\s*[:=]\s*['\"]?([a-z_]+)", txt)
        if rm:
            out[date] = rm.group(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without writing")
    args = ap.parse_args()

    date_to_regime = _build_date_to_regime()
    print(f"Built date→regime map from scan logs: {len(date_to_regime)} dates")
    if not date_to_regime:
        print("No scan logs found — nothing to backfill")
        sys.exit(0)

    sl_p = REPO / "data" / "signal_log.json"
    sl = json.loads(sl_p.read_text())

    backfilled = 0
    backfilled_dates = Counter()
    by_regime = Counter()
    for s in sl:
        if not isinstance(s, dict):
            continue
        if s.get("regime4") not in (None, "unknown"):
            continue
        date = (s.get("date") or "")[:10]
        if not date:
            continue
        regime = date_to_regime.get(date)
        if not regime:
            continue
        s["regime4"] = regime
        backfilled += 1
        backfilled_dates[date] += 1
        by_regime[regime] += 1

    print(f"\nWould backfill {backfilled} entries")
    print("By date:")
    for d, n in sorted(backfilled_dates.items()):
        print(f"  {d}: {n}  (→ {date_to_regime.get(d)})")
    print("By regime:")
    for r, n in by_regime.most_common():
        print(f"  {r}: {n}")

    if args.dry_run:
        print("\n[dry-run] No changes written.")
        return

    if backfilled:
        # Backup before write
        import shutil
        backup = REPO / "data" / f"signal_log.bak.regime_backfill.json"
        shutil.copy(sl_p, backup)
        sl_p.write_text(json.dumps(sl, indent=2, default=str))
        print(f"\nSaved {backfilled} backfilled entries to {sl_p}")
        print(f"Backup at: {backup}")


if __name__ == "__main__":
    main()
