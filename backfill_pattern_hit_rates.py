#!/usr/bin/env python3
"""
Pattern-engine Hit-Rate Backfill
────────────────────────────────
Computes per-ticker Wilson LB hit rates for the 7 pattern-engine rules:
  fib_0618_bounce · ichi_tk_cross · vp_poc_bounce · sr_level_hold ·
  trendline_break_followthrough · classical_breakout

Persists to data/pattern_hit_rates.json (30-day TTL).

Runs offline — keeps main swing_trade.py scan fast.

Usage:
    python3 backfill_pattern_hit_rates.py [--limit N] [--tickers TK1,TK2,...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from pattern_engine import (
    compute_pattern_hit_rates,
    save_pattern_hit_rate,
    load_pattern_hit_rates,
)


def get_scan_universe() -> list[str]:
    """Pull current scan tickers from data.json short_term + watch_list."""
    tickers = set()
    try:
        with open("infra/prototype/data.json") as f:
            d = json.load(f)
        for key in ("short_term", "watch_list"):
            for t in d.get(key, []):
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

    print(f"Backfilling pattern hit rates for {len(universe)} tickers ...")
    cache = load_pattern_hit_rates()

    n_skipped = n_done = n_failed = 0
    t0 = time.time()
    for i, tk in enumerate(universe, 1):
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

        try:
            df = fetch_bars(tk)
            if df is None or len(df) < 120:
                print(f"  [{i}/{len(universe)}] {tk:6s} insufficient bars ({len(df) if df is not None else 0}) · skip")
                n_failed += 1
                continue
            rates = compute_pattern_hit_rates(df, tk, horizon_days=10)
            rates["updated"] = datetime.utcnow().isoformat()
            save_pattern_hit_rate(tk, rates)
            n_done += 1
            elapsed = time.time() - t0
            avg = elapsed / n_done if n_done else 0
            eta = avg * (len(universe) - i)
            f618 = rates["fib_0618_bounce"]
            ichi = rates["ichi_tk_cross"]
            vp = rates["vp_poc_bounce"]
            sr = rates["sr_level_hold"]
            tl = rates["trendline_break_followthrough"]
            print(f"  [{i}/{len(universe)}] {tk:6s} "
                  f"fib={f618['wilson_lb']:5.1f}% n={f618['total']:2d} · "
                  f"ichi={ichi['wilson_lb']:5.1f}% · vp={vp['wilson_lb']:5.1f}% · "
                  f"sr={sr['wilson_lb']:5.1f}% · tl={tl['wilson_lb']:5.1f}% · "
                  f"avg={avg:.1f}s · eta={eta/60:.0f}min")
        except Exception as e:
            print(f"  [{i}/{len(universe)}] {tk:6s} ERROR: {e}")
            n_failed += 1

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} min · {n_done} computed · {n_skipped} skipped (cached) · {n_failed} failed")
    print(f"Cache: {Path('data/pattern_hit_rates.json')}")


if __name__ == "__main__":
    main()
