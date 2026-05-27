#!/usr/bin/env python3
"""
import_positions.py — bulk import existing holdings from CSV.

Usage:
  1. Create a CSV with one row per holding:
       ticker,entry,shares,stop,target1[,target2,setup,direction,notes,entry_date]

     Required: ticker, entry, shares, stop, target1
     Optional: target2 (defaults to None), setup, direction (default "long"),
               notes, entry_date (YYYY-MM-DD; default today)

  2. Run:
       python3 import_positions.py my_holdings.csv
       python3 import_positions.py my_holdings.csv --dry-run    # preview only

  3. Verify in V2 dashboard at http://localhost:7432/kairos.html
     → Portfolio tab.

Each row creates a paper position via portfolio_tracker.add_position().
The position then shows up in V2 with live P&L, and the minute-resolution
position_watcher will alert Slack when stop/target are approached.

Skipped rows (existing position, missing field, parse error) are reported
at the end. Run is idempotent — re-running with the same CSV will skip
tickers that already have open positions.
"""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path

REQUIRED = ["ticker", "entry", "shares", "stop", "target1"]


def _parse_row(row: dict, lineno: int) -> dict:
    out = {}
    for k in REQUIRED:
        v = (row.get(k) or "").strip()
        if not v:
            raise ValueError(f"line {lineno}: missing {k!r}")
        out[k] = v
    out["target2"]   = (row.get("target2") or "").strip() or None
    out["setup"]     = (row.get("setup") or "").strip()
    out["direction"] = (row.get("direction") or "long").strip().lower()
    out["notes"]     = (row.get("notes") or "").strip()
    out["entry_date"] = (row.get("entry_date") or "").strip() or None
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("csv_path", help="CSV file with one row per holding")
    p.add_argument("--dry-run", action="store_true", help="parse + validate only, don't add")
    args = p.parse_args()

    csv_file = Path(args.csv_path)
    if not csv_file.exists():
        print(f"ERROR: {csv_file} not found")
        return 1

    rows: list[dict] = []
    with csv_file.open() as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # start=2 because header=line1
            try:
                rows.append(_parse_row(row, i))
            except ValueError as e:
                print(f"  ✗ {e}")
                continue

    if not rows:
        print("No valid rows")
        return 1

    print(f"Parsed {len(rows)} valid rows from {csv_file}")
    print()
    for r in rows:
        t2 = f" T2={r['target2']}" if r['target2'] else ""
        print(f"  {r['ticker']:6}  entry=${r['entry']:>8}  shares={r['shares']:>4}  "
              f"stop=${r['stop']:>8}  T1=${r['target1']:>8}{t2}  ({r['direction']})")

    if args.dry_run:
        print("\n[--dry-run] No positions added. Re-run without --dry-run to import.")
        return 0

    print("\nImporting...")
    from portfolio_tracker import add_position
    added, skipped, failed = 0, 0, 0
    for r in rows:
        try:
            pos = add_position(
                ticker        = r["ticker"].upper(),
                entry_price   = float(r["entry"]),
                shares        = int(r["shares"]),
                stop          = float(r["stop"]),
                target1       = float(r["target1"]),
                target2       = float(r["target2"]) if r["target2"] else None,
                setup_type    = r["setup"],
                direction     = r["direction"],
                notes         = r["notes"],
                entry_date    = r["entry_date"],
            )
            print(f"  ✓ {r['ticker']:6}  added")
            added += 1
        except ValueError as e:
            msg = str(e)
            if "already has" in msg:
                print(f"  ⊘ {r['ticker']:6}  skipped — {msg}")
                skipped += 1
            else:
                print(f"  ✗ {r['ticker']:6}  rejected — {msg}")
                failed += 1
        except Exception as e:
            print(f"  ✗ {r['ticker']:6}  {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"Done — {added} added, {skipped} skipped (already open), {failed} failed")
    print(f"View at: http://localhost:7432/kairos.html → Portfolio tab")
    return 0 if added > 0 or skipped > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
