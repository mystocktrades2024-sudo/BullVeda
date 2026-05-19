#!/usr/bin/env python3
"""Count WATCH-reasons across N historical dates in the backtest path.

For each historical date, run _score_as_of for ~30 random tickers, collect the
verdict reasons, tabulate. Shows which gate is the dominant blocker.
"""
from __future__ import annotations
import sys, json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
_spec = importlib.util.spec_from_file_location("backtest_mod", ROOT / "backtest.py")
_bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bt)
_score_as_of = _bt._score_as_of

from data_fetcher import fetch_ohlcv_with_failover, get_finviz_bulk


def main():
    cfg = json.loads((ROOT / "config" / "config.json").read_text())
    cfg.setdefault("rolling_sharpe_kill", {})["_enabled"] = False

    end_date = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else "2025-09-15")
    days_back = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    n_tickers = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    # Sample tickers — S&P 500 large-caps
    tickers = ["AAPL","MSFT","GOOGL","NVDA","AMZN","META","TSLA","BRK-B","UNH","JPM",
               "V","XOM","JNJ","WMT","PG","MA","HD","CVX","ABBV","KO",
               "PEP","COST","MRK","AVGO","TMO","BAC","ORCL","ADBE","CRM","NFLX"][:n_tickers]

    print(f"Loading SPY + FINVIZ...")
    spy, _ = fetch_ohlcv_with_failover("SPY", days=400)
    fvz_all = get_finviz_bulk()
    print(f"  spy: {len(spy)} bars; finviz: {len(fvz_all)} tickers")
    print()

    reason_counts = Counter()
    verdict_counts = Counter()
    score_buckets = Counter()
    sample_reasons = []
    n_total = 0

    # Generate test dates (every 2-3 trading days)
    test_dates = [end_date - timedelta(days=i*3) for i in range(days_back)]
    test_dates = [d for d in test_dates if d.weekday() < 5]  # weekdays only

    for as_of in test_dates:
        if as_of not in spy.index:
            continue
        for t in tickers:
            df, _ = fetch_ohlcv_with_failover(t, days=400)
            if df is None or len(df) < 60: continue
            df_slc = df[df.index <= as_of]
            if len(df_slc) < 60: continue

            # Build _ef from FINVIZ
            fvz = fvz_all.get(t, {})
            info = {"sector": "Tech"}
            try:
                result = _score_as_of(t, df, as_of, spy, cfg, info, finviz_data=fvz)
            except Exception:
                continue
            if result is None: continue

            n_total += 1
            verdict_counts[result.get("verdict") or "?"] += 1
            reason = (result.get("reason") or "").strip()
            # Categorize the reason
            r_short = reason[:50] if reason else "(no reason)"
            reason_counts[r_short] += 1
            # Score band
            score = result.get("score") or 0
            band = f"score_{int(score//10)*10:02d}-{int(score//10)*10+9:02d}"
            score_buckets[band] += 1
            if reason and len(sample_reasons) < 30 and reason not in [s[1] for s in sample_reasons]:
                sample_reasons.append((t, reason, result.get("verdict"), score))

    print(f"=== WATCH-REASON HISTOGRAM ===")
    print(f"  Sample: {len(test_dates)} test dates × {len(tickers)} tickers = {n_total} scored")
    print()
    print(f"VERDICT BREAKDOWN:")
    for v, c in verdict_counts.most_common():
        print(f"  {v:<10} {c:>5}  ({c/n_total*100:.1f}%)")
    print()
    print(f"SCORE BAND BREAKDOWN:")
    for b in sorted(score_buckets.keys()):
        c = score_buckets[b]
        print(f"  {b:<14} {c:>5}  ({c/n_total*100:.1f}%)")
    print()
    print(f"TOP 15 REASONS (by frequency):")
    for r, c in reason_counts.most_common(15):
        print(f"  {c:>5}  {r}")
    print()
    print(f"UNIQUE REASON SAMPLES (first 15):")
    for t, r, v, s in sample_reasons[:15]:
        print(f"  [{v}, score={s:.1f}] {t}: {r[:120]}")


if __name__ == "__main__":
    main()
