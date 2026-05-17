#!/usr/bin/env python3
"""
SMC Hit-Rate Backfill
─────────────────────
Computes per-ticker Wilson LB hit rates for OB / FVG / Breaker concepts.
Persists to data/smc_hit_rates.json (30-day TTL).

Runs as a separate offline batch — keeps the main swing_trade.py scan fast.

Usage:
    python3 backfill_smc_hit_rates.py [--limit N] [--tickers TICKER1,TICKER2,...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from smc_engine import compute_smc_hit_rates, save_hit_rate, load_hit_rates


def get_scan_universe() -> list[str]:
    """Pull current scan tickers from data.json + custom watchlist."""
    tickers = set()
    try:
        with open("infra/prototype/data.json") as f:
            d = json.load(f)
        for t in d.get("short_term", []):
            if t.get("ticker"):
                tickers.add(t["ticker"].upper())
    except Exception as e:
        print(f"WARN: data.json unreachable: {e}")
    return sorted(tickers)


def fetch_bars(ticker: str):
    """Fetch 6mo OHLC via data_fetcher (with EODHD primary)."""
    from data_fetcher import fetch_ohlcv_with_failover
    result = fetch_ohlcv_with_failover(ticker, days=180)
    df = result[0] if isinstance(result, tuple) else result
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process first N tickers")
    ap.add_argument("--tickers", default=None,
                    help="Comma-separated explicit ticker list")
    ap.add_argument("--max-age-days", type=int, default=30,
                    help="Skip tickers cached within this many days")
    args = ap.parse_args()

    if args.tickers:
        universe = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        universe = get_scan_universe()
    if args.limit:
        universe = universe[:args.limit]

    print(f"Backfilling {len(universe)} tickers ...")
    cache = load_hit_rates()
    from datetime import datetime

    n_skipped = n_done = n_failed = 0
    t0 = time.time()
    for i, tk in enumerate(universe, 1):
        # Skip fresh cache entries
        rec = cache.get(tk)
        if rec:
            try:
                upd = datetime.fromisoformat(rec.get("updated", "1970-01-01"))
                age = (datetime.utcnow() - upd).days
                if age < args.max_age_days:
                    n_skipped += 1
                    continue
            except Exception:
                pass

        # Fetch + compute
        try:
            df = fetch_bars(tk)
            if df is None or len(df) < 90:
                print(f"  [{i}/{len(universe)}] {tk:6s} insufficient bars · skip")
                n_failed += 1
                continue
            rates = compute_smc_hit_rates(df, tk, horizon_days=10)
            rates["updated"] = datetime.utcnow().isoformat()
            save_hit_rate(tk, rates)
            n_done += 1
            elapsed = time.time() - t0
            avg = elapsed / n_done if n_done else 0
            eta = avg * (len(universe) - i)
            ob = rates["order_blocks"]
            print(f"  [{i}/{len(universe)}] {tk:6s} OB={ob['wilson_lb']:5.1f}% n={ob['total']:3d} · "
                  f"FVG={rates['fvgs']['wilson_lb']:5.1f}% · Brk={rates['breakers']['wilson_lb']:5.1f}% · "
                  f"avg={avg:.1f}s · eta={eta/60:.0f}min")
        except Exception as e:
            print(f"  [{i}/{len(universe)}] {tk:6s} ERROR: {e}")
            n_failed += 1

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} min · {n_done} computed · {n_skipped} skipped (cached) · {n_failed} failed")
    print(f"Cache: {Path('data/smc_hit_rates.json')}")


if __name__ == "__main__":
    main()
