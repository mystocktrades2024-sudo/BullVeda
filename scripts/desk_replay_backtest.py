#!/usr/bin/env python3
"""desk_replay_backtest.py — point-in-time PRICE replay for the two price-only desks
(Mean-Reversion, Short) that the trade-log attribution can't cover.

ZERO EODHD: reads only cached daily bars from data/ohlcv/*.parquet (2k+ tickers,
2-3yr history). For every historical day it computes the desk's signal from bars up to
that day (no look-ahead), then measures the forward 5-day swing outcome with a
1.25×ATR stop (stopped = −1R). Wilson WR + PF + E[R] merged into
cache/desk_edge_stats.json (mr, short). Value/Quality stay 'pending' — they need
point-in-time fundamentals we don't have (paid source rejected).

Run: python3 scripts/desk_replay_backtest.py [--window 500] [--hold 5]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OHLCV = BASE / "data" / "ohlcv"
STATS = BASE / "cache" / "desk_edge_stats.json"

PF_HAIRCUT = 0.10
WR_HAIRCUT = 0.03
ATR_STOP = 1.25
MIN_DOLLAR_VOL = 5e6   # skip illiquid names (tradability floor)


def _rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr_pct(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean() / c * 100


def _wilson_lb(w, n, z=1.96):
    if n == 0:
        return 0.0
    p = w / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n))


def _forward_R(df, i, hold, stop_pct, short=False):
    """Forward outcome in R from entry at bar i (Close), 1.25×ATR stop, `hold`-day exit."""
    entry = df["Close"].iloc[i]
    if stop_pct is None or stop_pct <= 0 or not np.isfinite(entry) or entry <= 0:
        return None
    stop = entry * (1 + stop_pct / 100) if short else entry * (1 - stop_pct / 100)
    lo = i + 1
    hi = min(i + hold, len(df) - 1)
    if hi <= lo:
        return None
    win = df.iloc[lo:hi + 1]
    if short:
        if (win["High"] >= stop).any():
            return -1.0
        ret = (entry - win["Close"].iloc[-1]) / entry * 100
    else:
        if (win["Low"] <= stop).any():
            return -1.0
        ret = (win["Close"].iloc[-1] - entry) / entry * 100
    return ret / stop_pct


def _stats(rms):
    n = len(rms)
    if not n:
        return {"n": 0, "pending": True, "note": "no signals in window"}
    w = sum(1 for r in rms if r > 0)
    wr = w / n
    pos = sum(r for r in rms if r > 0)
    neg = abs(sum(r for r in rms if r < 0))
    pf = pos / neg if neg > 0 else (pos if pos > 0 else 0.0)
    return {
        "n": n, "wr": round(wr, 4), "wilson_lb": round(_wilson_lb(w, n), 4),
        "pf": round(pf, 3), "pf_haircut": round(max(0.0, pf - PF_HAIRCUT), 3),
        "wr_haircut": round(max(0.0, wr - WR_HAIRCUT), 4),
        "expectancy_R": round(sum(rms) / n, 3),
        "method": "price replay (cached bars, 0 EODHD, PIT signals + fwd 5d/1.25ATR-stop)",
        "low_sample": n < 20,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=500, help="lookback days of signal days to sample")
    ap.add_argument("--hold", type=int, default=5)
    args = ap.parse_args()

    files = glob.glob(str(OHLCV / "*.parquet"))
    spy = None
    spy_path = OHLCV / "SPY.parquet"
    if spy_path.exists():
        spy = pd.read_parquet(spy_path)["Close"]
        spy_ret63 = spy.pct_change(63)

    mr_R, short_R = [], []
    scanned = 0
    for f in files:
        sym = os.path.basename(f)[:-8]
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        if len(df) < 220:
            continue
        c = df["Close"]
        if (c.iloc[-1] * df["Volume"].iloc[-20:].mean()) < MIN_DOLLAR_VOL:
            continue
        scanned += 1
        rsi = _rsi(c)
        ema50 = c.ewm(span=50, adjust=False).mean()
        ema200 = c.ewm(span=200, adjust=False).mean()
        atrp = _atr_pct(df)
        ret63 = c.pct_change(63)
        start = max(200, len(df) - args.window)
        end = len(df) - args.hold  # need forward bars
        # align SPY underperformance for shorts
        spy_r = spy_ret63.reindex(df.index) if spy is not None else None
        for i in range(start, end):
            sp = ATR_STOP * atrp.iloc[i] if np.isfinite(atrp.iloc[i]) else None
            # Mean-Reversion: RSI<30 AND price > EMA200
            if rsi.iloc[i] < 30 and c.iloc[i] > ema200.iloc[i]:
                r = _forward_R(df, i, args.hold, sp, short=False)
                if r is not None:
                    mr_R.append(r)
            # Short: price < EMA50 AND underperforming SPY over 63d (RS-weak)
            weak = (spy_r is not None and np.isfinite(spy_r.iloc[i]) and ret63.iloc[i] < spy_r.iloc[i]) \
                or (spy_r is None and ret63.iloc[i] < -0.05)
            if c.iloc[i] < ema50.iloc[i] and weak:
                r = _forward_R(df, i, args.hold, sp, short=True)
                if r is not None:
                    short_R.append(r)

    out = json.loads(STATS.read_text()) if STATS.exists() else {"_meta": {}, "desks": {}}
    out.setdefault("desks", {})
    for key, rms in (("mr", mr_R), ("short", short_R)):
        s = _stats(rms)
        s["approximate"] = True  # ADX/exact desk gate simplified in replay
        out["desks"][key] = s
    out["_meta"]["replay"] = {"scanned_tickers": scanned, "window": args.window, "hold": args.hold,
                              "source": "data/ohlcv/*.parquet", "eodhd_calls": 0}
    STATS.write_text(json.dumps(out, indent=2))
    print(f"scanned {scanned} tickers (cached bars, 0 EODHD)")
    for key, rms in (("mr", mr_R), ("short", short_R)):
        s = out["desks"][key]
        if s.get("n"):
            print(f"  {key:5s} n={s['n']:5d}  WR {s['wr']*100:4.1f}%  Wilson {s['wilson_lb']*100:4.1f}%  "
                  f"PF {s['pf']:.2f}->{s['pf_haircut']:.2f}  E[R] {s['expectancy_R']:+.2f}")
        else:
            print(f"  {key:5s} no signals")


if __name__ == "__main__":
    main()
