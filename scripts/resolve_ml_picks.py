"""Resolve matured ML Edge paper picks · backfill outcomes.

Reads cache/ml_edge_picks_history.jsonl, finds rows with status='pending'
whose scan_date + horizon_days <= today, looks up the close price on that
exit date via EODHD, computes realized_pct + realized_r, and rewrites the
file with status='resolved'.

Run daily from launchd or weekly diagnostics. Idempotent.

Usage:
    python3 scripts/resolve_ml_picks.py
    python3 scripts/resolve_ml_picks.py --dry-run

Closes the loop on principle 16 (Performance attribution by sub-strategy)
and feeds the AI Prediction tab's walk-forward equity curve.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PICKS_PATH = ROOT / "cache" / "ml_edge_picks_history.jsonl"


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Resolve matured ML Edge paper picks")
    ap.add_argument("--dry-run", action="store_true", help="don't rewrite file, just print")
    ap.add_argument("--max-age-days", type=int, default=180,
                    help="ignore picks older than this (sanity guard)")
    return ap.parse_args(argv)


def _ohlcv_close(ticker: str, target_date: str) -> float | None:
    """Get the close price for `ticker` on `target_date` (or nearest trading day after)."""
    try:
        from data_fetcher import fetch_ohlcv_with_failover
        df = fetch_ohlcv_with_failover(ticker, lookback_days=400)
        if df is None or df.empty:
            return None
        # Look for the first row at-or-after target_date
        for idx, row in df.iterrows():
            d = str(idx)[:10] if hasattr(idx, "strftime") else str(idx)[:10]
            if d >= target_date:
                close = row.get("close") or row.get("Close")
                return float(close) if close is not None else None
        return None
    except Exception as e:
        print(f"  [resolver] OHLCV fetch failed for {ticker}: {e}")
        return None


def main(argv=None):
    args = _parse_args(argv)
    if not PICKS_PATH.exists():
        print(f"[resolver] no picks file at {PICKS_PATH} — nothing to do")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    lines = PICKS_PATH.read_text().splitlines()
    print(f"[resolver] reading {len(lines)} picks · today={today}")

    out_lines = []
    n_resolved, n_pending, n_stale, n_failed = 0, 0, 0, 0

    for ln in lines:
        try:
            rec = json.loads(ln)
        except Exception:
            out_lines.append(ln)
            continue

        # Already resolved → keep
        if rec.get("status") == "resolved":
            out_lines.append(ln)
            continue

        scan_date = rec.get("scan_date", "")
        horizon = int(rec.get("horizon_days") or 5)
        ticker = rec.get("ticker")
        entry  = float(rec.get("entry") or 0)
        atr    = float(rec.get("atr") or 0)

        if not scan_date or not ticker or entry <= 0:
            out_lines.append(ln)
            continue

        try:
            scan_dt = datetime.strptime(scan_date, "%Y-%m-%d")
        except Exception:
            out_lines.append(ln)
            continue

        # Compute exit date (calendar + slack for weekends)
        exit_dt = scan_dt + timedelta(days=horizon + 3)  # +3 to clear weekend
        exit_date = exit_dt.strftime("%Y-%m-%d")

        # Too old? Skip stale entries to avoid burning EODHD quota
        age_days = (datetime.now() - scan_dt).days
        if age_days > args.max_age_days:
            n_stale += 1
            out_lines.append(ln)
            continue

        # Not yet matured?
        if exit_date > today:
            n_pending += 1
            out_lines.append(ln)
            continue

        # Resolve via OHLCV
        exit_close = _ohlcv_close(ticker, exit_date)
        if exit_close is None or exit_close <= 0:
            n_failed += 1
            out_lines.append(ln)
            continue

        realized_pct = (exit_close - entry) / entry * 100.0
        # R-multiple = realized / risk_per_share (uses 1.5×ATR convention)
        risk_per_share = max(0.01, 1.5 * atr)
        realized_r = (exit_close - entry) / risk_per_share

        rec["status"] = "resolved"
        rec["exit_date"] = exit_date
        rec["exit_price"] = round(exit_close, 4)
        rec["realized_pct"] = round(realized_pct, 3)
        rec["realized_r"] = round(realized_r, 3)
        out_lines.append(json.dumps(rec))
        n_resolved += 1

    print(f"[resolver] resolved={n_resolved} pending={n_pending} stale={n_stale} failed={n_failed}")

    if not args.dry_run and n_resolved > 0:
        PICKS_PATH.write_text("\n".join(out_lines) + "\n")
        print(f"[resolver] rewrote {PICKS_PATH}")
    elif args.dry_run:
        print("[resolver] dry-run; no file write")


if __name__ == "__main__":
    main()
