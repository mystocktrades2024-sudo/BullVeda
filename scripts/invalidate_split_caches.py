#!/usr/bin/env python3
"""Split-driven cache invalidation — Open Risk #9 (b).

A stock split makes cached bars + cached structural targets WRONG until they are
re-fetched split-adjusted (EODHD returns adjusted_close on the next pull, so a
fresh fetch fixes it automatically — we just have to force one).

This script reads cache/corporate_events.json (built by
scripts/fetch_corporate_events.py from the EODHD splits calendar) and, for every
split whose ex-date (`split_date`) is <= today, deletes that ticker's cached
artifacts so the next scan re-fetches split-adjusted data:

  • cache/ohlcv/{T}.parquet           — live OHLCV cache (data_fetcher)
  • data/ohlcv/{T}.parquet            — OHLCV archive (data_archive, last-resort tier)
  • cache/target_engine/{T}_*.json    — structural T1/T2 targets (all modes)

It is ADDITIVE + SAFE: it only removes *regenerable* cache files. It never
touches picks_history / signal_log / audit_ledger / portfolio_state. Idempotent —
a ledger (cache/split_invalidation_state.json) records the last processed
split_date per ticker so a re-run on the same events file is a no-op (a *new*
split on the same ticker still re-fires).

Usage:
    python3 scripts/invalidate_split_caches.py            # process today & earlier
    python3 scripts/invalidate_split_caches.py --dry-run  # show what would clear
    python3 scripts/invalidate_split_caches.py --ticker NVDA   # force one ticker
    python3 scripts/invalidate_split_caches.py --all-future     # also clear upcoming

Designed to run right after scripts/fetch_corporate_events.py (same daily job).
Also importable: `from scripts.invalidate_split_caches import invalidate_on_split`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE / "cache" / "corporate_events.json"
STATE_FILE = BASE / "cache" / "split_invalidation_state.json"

# Cache layers to invalidate (relative to BASE).
LIVE_OHLCV_DIR = BASE / "cache" / "ohlcv"          # data_fetcher live cache
ARCHIVE_OHLCV_DIR = BASE / "data" / "ohlcv"         # data_archive last-resort tier
TARGET_ENGINE_DIR = BASE / "cache" / "target_engine"  # structural targets


def _norm_ticker(code: str) -> str:
    """`NVDA.US` / `nvda` → `NVDA`. Strips exchange suffix, uppercases."""
    return (code or "").upper().split(".")[0].strip()


def invalidate_on_split(ticker: str, *, dry_run: bool = False) -> list[str]:
    """Remove all regenerable cache artifacts for `ticker` so the next scan
    re-fetches split-adjusted bars + recomputes targets.

    Returns the list of file paths removed (or that WOULD be removed in dry-run).
    Safe to call on any ticker; missing files are silently skipped. NEVER touches
    history / portfolio state.
    """
    t = _norm_ticker(ticker)
    if not t:
        return []
    removed: list[str] = []

    candidates: list[Path] = [
        LIVE_OHLCV_DIR / f"{t}.parquet",
        ARCHIVE_OHLCV_DIR / f"{t}.parquet",
    ]
    # Structural targets: cache/target_engine/{T}_{MODE}.json across all modes.
    if TARGET_ENGINE_DIR.exists():
        candidates += sorted(TARGET_ENGINE_DIR.glob(f"{t}_*.json"))

    for p in candidates:
        if p.exists():
            removed.append(str(p))
            if not dry_run:
                try:
                    p.unlink()
                except Exception as e:
                    print(f"  [warn] could not remove {p}: {e}", file=sys.stderr)
    return removed


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def run(dry_run: bool = False, all_future: bool = False,
        only_ticker: str | None = None) -> int:
    """Process cache/corporate_events.json splits; invalidate eligible caches."""
    if only_ticker:
        removed = invalidate_on_split(only_ticker, dry_run=dry_run)
        verb = "would remove" if dry_run else "removed"
        print(f"[split-invalidate] {only_ticker.upper()}: {verb} {len(removed)} file(s)")
        for r in removed:
            print(f"    - {r}")
        return 0

    if not EVENTS_FILE.exists():
        print(f"[split-invalidate] no events file at {EVENTS_FILE} — nothing to do")
        return 0

    try:
        events = json.loads(EVENTS_FILE.read_text())
    except Exception as e:
        print(f"[split-invalidate] could not read events file: {e}", file=sys.stderr)
        return 1

    splits = events.get("splits") or []
    today = datetime.date.today().isoformat()
    state = _load_state()

    processed = 0
    skipped_future = 0
    skipped_dup = 0
    total_removed = 0

    for s in splits:
        if not isinstance(s, dict):
            continue
        code = s.get("code") or ""
        t = _norm_ticker(code)
        if not t:
            continue
        sdate = (s.get("split_date") or "").strip()
        if not sdate:
            continue

        # Ex-date gating: only invalidate once the split has actually taken
        # effect (split_date <= today), unless --all-future is set.
        if not all_future and sdate > today:
            skipped_future += 1
            continue

        # Idempotency: skip if we already processed THIS split_date for THIS
        # ticker. A *new* split (later split_date) re-fires.
        if state.get(t) == sdate and not dry_run:
            skipped_dup += 1
            continue

        removed = invalidate_on_split(t, dry_run=dry_run)
        total_removed += len(removed)
        processed += 1
        ratio = s.get("_ratio") or "?"
        verb = "would clear" if dry_run else "cleared"
        print(f"[split-invalidate] {t} ({ratio}, ex {sdate}): {verb} {len(removed)} cache file(s)")
        for r in removed:
            print(f"    - {r}")
        if not dry_run:
            state[t] = sdate

    if not dry_run and processed:
        _save_state(state)

    print(f"[split-invalidate] done · {processed} ticker(s) invalidated · "
          f"{total_removed} file(s) {'(dry-run)' if dry_run else 'removed'} · "
          f"{skipped_future} future-dated skipped · {skipped_dup} already-processed skipped")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Split-driven cache invalidation")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be cleared without deleting")
    ap.add_argument("--all-future", action="store_true",
                    help="also clear caches for upcoming (future-dated) splits")
    ap.add_argument("--ticker", default=None,
                    help="force-invalidate a single ticker, ignore events file")
    args = ap.parse_args(argv[1:])
    return run(dry_run=args.dry_run, all_future=args.all_future, only_ticker=args.ticker)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
