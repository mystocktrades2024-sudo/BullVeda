#!/usr/bin/env python3
"""Phase 2 — forward ladder log for GAM v2 target validation.

Appends today's v2 ladder (per ticker) to data/gam_ladder_log.jsonl so
hit-rates can be measured FORWARD — no reliance on historical outcome data.
Idempotent per (ticker, session_date). After 30+ sessions, score with:
  did high reach t1/t2/t3 within HORIZON(4) bars?  → calibration by
  conf band and wall/magnet tag (Wilson lower-bound, n>=30 per bucket).

Usage: python3 scripts/gam_ladder_log.py [T1 T2 ...]   (default basket below)
Wire into a daily job AFTER the market close snapshot for a clean daily bar.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, ".")
import data_fetcher                      # noqa: E402
from scripts.gam_target_v2 import compute_ladder  # noqa: E402

LOG = "data/gam_ladder_log.jsonl"
DEFAULT = ["LQDA", "NVDA", "AAPL", "MSFT", "AMD", "META", "AMZN", "GOOGL", "TSLA", "SPY"]


def main() -> None:
    tickers = sys.argv[1:] or DEFAULT
    seen = set()
    if os.path.exists(LOG):
        with open(LOG) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    seen.add((r.get("ticker"), r.get("session")))
                except Exception:  # noqa: BLE001
                    continue

    wrote = 0
    with open(LOG, "a") as f:
        for tk in tickers:
            bars, tier = data_fetcher.fetch_ohlcv_with_failover(tk, days=400)
            if bars is None or len(bars) < 80:
                print(f"{tk}: skipped (no bars, {tier})")
                continue
            d = bars.copy()
            d.columns = [str(c).lower() for c in d.columns]
            session = str(pd_last_date(d))
            if (tk, session) in seen:
                print(f"{tk}: already logged for {session}")
                continue
            lad = compute_ladder(bars)
            row = {"ticker": tk, "session": session, "horizon": 4, "preset": "swing",
                   **lad}
            f.write(json.dumps(row, default=str) + "\n")
            wrote += 1
            t1 = lad.get("t1")
            print(f"{tk}: logged  T1={t1 and t1.get('price')} "
                  f"conf={t1 and t1.get('conf')} wall={t1 and t1.get('wall')}")
    print(f"\n{wrote} rows appended → {LOG}")


def pd_last_date(d):
    import pandas as pd
    if isinstance(d.index, pd.DatetimeIndex):
        return d.index[-1].date()
    for c in ("date", "datetime", "timestamp"):
        if c in d.columns:
            return pd.to_datetime(d[c].iloc[-1]).date()
    return "unknown"


if __name__ == "__main__":
    main()
