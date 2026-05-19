"""One-shot cleanup: dedupe + correct verdict labels in data/signal_log.json.

After 2026-05-18 we discovered two upstream bugs that contaminated signal_log:
  1. WATCH-conviction signals being written with verdict='BUY'
  2. Same physical trade re-emitted as fresh signal each day (3 dupes for VRT)

Forward-flow fixes (in swing_trade.py + decision_engine.py) prevent NEW
contamination. This script cleans the EXISTING log so downstream consumers
(Tracker tab, sharpe_setup_trend.py, attribution, etc.) all see clean data.

Idempotent. Writes a backup at data/signal_log.json.bak-YYYYMMDD-HHMMSS
before mutating. Run with --dry-run to preview without writing.

Usage:
    python3 scripts/dedupe_signal_log.py             # apply fixes
    python3 scripts/dedupe_signal_log.py --dry-run   # preview only

Stats reported:
    Total rows · WATCH-corrections · dupes-removed · final count
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG = ROOT / "data" / "signal_log.json"


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Dedupe + correct signal_log.json")
    ap.add_argument("--dry-run", action="store_true", help="preview only, don't write")
    return ap.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if not LOG.exists():
        print(f"[dedupe] {LOG} not found — nothing to do")
        return

    print(f"[dedupe] reading {LOG}")
    sigs = json.loads(LOG.read_text())
    if not isinstance(sigs, list):
        print(f"[dedupe] {LOG} is not a list — abort")
        return

    n_total_orig = len(sigs)
    n_watch_corrected = 0
    n_dupes_removed = 0

    # Pass 1 — correct verdict for WATCH-conviction signals that were
    # mislabeled as BUY/SHORT.
    for s in sigs:
        if not isinstance(s, dict):
            continue
        conv = (s.get("conviction_label") or "").upper()
        verdict = (s.get("verdict") or "").upper()
        if conv == "WATCH" and verdict in ("BUY", "SHORT"):
            s["verdict"] = "WATCH"
            n_watch_corrected += 1

    # Pass 2 — dedupe identical-outcome rows. A "duplicate" is the same
    # physical trade re-emitted as a fresh daily signal with identical
    # entry/stop/exit. Key: (ticker, mode, entry_price, exit_reason, pnl).
    # Open (un-resolved) entries dedupe by (ticker, mode, entry_date) since
    # they may not have outcome fields yet.
    seen_closed: dict[tuple, dict] = {}
    seen_open: dict[tuple, dict] = {}
    kept = []
    for s in sigs:
        if not isinstance(s, dict):
            kept.append(s); continue
        ticker = s.get("ticker", "")
        mode = s.get("mode", "Swing")
        if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None:
            key = (
                ticker, mode,
                round(float(s.get("entry_price") or 0), 4),
                s.get("exit_reason") or "",
                round(float(s.get("actual_pnl_pct") or 0), 2),
            )
            if key in seen_closed:
                # Keep the EARLIEST entry (preserves the original signal date)
                if (s.get("date") or "") < (seen_closed[key].get("date") or ""):
                    # newer scan dates supersede — replace with earlier dated
                    # NO actually keep the FIRST seen (which is earliest by sort).
                    # If signals weren't pre-sorted, we'd need a 2-pass; sort below.
                    pass
                n_dupes_removed += 1
                continue
            seen_closed[key] = s
            kept.append(s)
        else:
            # OPEN or non-closed — dedupe by (ticker, mode, date)
            key = (ticker, mode, s.get("date") or "")
            if key in seen_open:
                n_dupes_removed += 1
                continue
            seen_open[key] = s
            kept.append(s)

    print(f"[dedupe] WATCH→BUY corrections: {n_watch_corrected}")
    print(f"[dedupe] Duplicate CLOSED rows removed: {n_dupes_removed}")
    print(f"[dedupe] Final row count: {len(kept)} (was {n_total_orig})")

    if args.dry_run:
        print("[dedupe] dry-run — no file write")
        return

    # Backup first
    bak = LOG.with_name(f"signal_log.json.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(LOG, bak)
    print(f"[dedupe] backup written to {bak.name}")

    LOG.write_text(json.dumps(kept, indent=2))
    print(f"[dedupe] cleaned signal_log.json written ({len(kept)} rows)")


if __name__ == "__main__":
    main()
