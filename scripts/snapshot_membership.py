"""Monthly point-in-time membership snapshot · S&P 500 / R1000 / R2000.

Run on the 1st of each month via launchd. Writes:
  data/membership/sp500_YYYY-MM.csv
  data/membership/r1000_YYYY-MM.csv
  data/membership/r2000_YYYY-MM.csv

Used by data_fetcher.get_universe_as_of() for survivorship-bias-aware
backtesting. Over time, accumulates enough history to backfill point-in-time
universe membership for any month.

Idempotent: existing files are NOT overwritten. To force, pass --overwrite.

Usage:
    python3 scripts/snapshot_membership.py
    python3 scripts/snapshot_membership.py --overwrite
    python3 scripts/snapshot_membership.py --month 2026-04   # force a specific stamp
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

MEMBERSHIP_DIR = ROOT / "data" / "membership"


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Snapshot S&P 500 / R1000 / R2000 membership")
    ap.add_argument("--overwrite", action="store_true", help="overwrite existing files")
    ap.add_argument("--month", type=str, default=None, help="month stamp 'YYYY-MM', defaults to now")
    return ap.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    MEMBERSHIP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = args.month or datetime.now().strftime("%Y-%m")

    from ml.universe_loader import _load_sp500, _load_r1000, _load_r2000

    snapshots = [
        ("sp500", sorted(_load_sp500())),
        ("r1000", sorted(_load_r1000())),
        ("r2000", sorted(_load_r2000())),
    ]
    for name, syms in snapshots:
        path = MEMBERSHIP_DIR / f"{name}_{stamp}.csv"
        if path.exists() and not args.overwrite:
            existing = len(path.read_text().splitlines())
            print(f"[snapshot] {path.name} exists ({existing} tickers) — skip")
            continue
        if len(syms) < 100:
            print(f"[snapshot] {name} returned only {len(syms)} tickers — refusing to write (likely EODHD outage)")
            continue
        path.write_text("\n".join(syms) + "\n")
        print(f"[snapshot] wrote {path.name}: {len(syms)} tickers")


if __name__ == "__main__":
    main()
