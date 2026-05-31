#!/usr/bin/env python3
"""regime_accuracy.py — does the regime classifier actually predict the tape? (Q3 / principle 18)

The 4-regime model is "the most important code in the system" (principle 18) but was never
validated for CLASSIFICATION ACCURACY — only per-setup Sharpe decomposition. This closes that
gap: for each date the scanner labeled a regime, check whether SPY's FORWARD move over the
next N sessions matched the regime's hypothesis.

Regime hypotheses (what each label predicts about forward SPY):
  risk_on_trending  → forward up,  low realized vol   (trend persists up)
  risk_on_choppy    → small net move, range-bound     (chop)
  risk_off_trending → forward down or weak            (trend persists down)
  panic             → sharp down / extreme vol        (capitulation)

Sources (all local, no network):
  - regime label per date  ← cache/picks_history.json trades[].regime4 + entry_date
  - forward SPY returns     ← data/ohlcv/SPY.parquet (the local archive)

Outputs a confusion-style hit-rate per regime + an overall classifier accuracy.
Read-only.  Usage: python3 scripts/regime_accuracy.py [--horizon 5] [--days 0]
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HIST = BASE / "cache" / "picks_history.json"
SPY = BASE / "data" / "ohlcv" / "SPY.parquet"


def _spy_series():
    import pandas as pd
    df = pd.read_parquet(SPY)
    # archive parquet is DatetimeIndex + OHLCV columns
    if not isinstance(df.index, pd.DatetimeIndex):
        dcol = next((c for c in ("date", "Date") if c in df.columns), df.columns[0])
        df = df.set_index(pd.to_datetime(df[dcol]))
    ccol = next((c for c in ("adj_close", "Adj Close", "Close", "close") if c in df.columns), None)
    return df.sort_index()[ccol]


def regime_label_by_date():
    """date -> regime4 (most common label stamped that day)."""
    d = json.loads(HIST.read_text())
    by_date = defaultdict(list)
    for t in d.get("trades", []):
        dt = t.get("entry_date"); rg = t.get("regime4") or t.get("regime")
        if dt and rg:
            by_date[dt].append(rg)
    out = {}
    for dt, rgs in by_date.items():
        out[dt] = max(set(rgs), key=rgs.count)
    return out


def forward_ret(spy, date, horizon):
    """SPY % return from `date` over the next `horizon` sessions, + realized vol."""
    import pandas as pd
    try:
        idx = spy.index.searchsorted(pd.to_datetime(date))
        if idx >= len(spy) - 1:
            return None, None
        end = min(idx + horizon, len(spy) - 1)
        p0, p1 = spy.iloc[idx], spy.iloc[end]
        seg = spy.iloc[idx:end + 1]
        ret = (p1 / p0 - 1) * 100
        vol = float(seg.pct_change().std() * 100) if len(seg) > 2 else 0.0
        return round(ret, 2), round(vol, 2)
    except Exception:
        return None, None


def matched(regime, ret, vol):
    """Did the forward tape match the regime hypothesis? (calibrated, lenient thresholds)"""
    if ret is None:
        return None
    if regime == "risk_on_trending":
        return ret > 0.5                       # forward up
    if regime == "risk_on_choppy":
        return abs(ret) <= 2.5                  # range-bound
    if regime == "risk_off_trending":
        return ret < 0.5                        # flat-to-down
    if regime == "panic":
        return ret < -2.0 or (vol or 0) > 2.0   # sharp down / high vol
    return None


def run(horizon=5, days=0):
    labels = regime_label_by_date()
    if days and days > 0:
        import datetime as _dt
        cut = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        labels = {d: r for d, r in labels.items() if d >= cut}
    spy = _spy_series()
    per = defaultdict(lambda: {"n": 0, "hit": 0, "rets": []})
    for dt, rg in sorted(labels.items()):
        ret, vol = forward_ret(spy, dt, horizon)
        m = matched(rg, ret, vol)
        if m is None:
            continue
        per[rg]["n"] += 1
        per[rg]["hit"] += 1 if m else 0
        per[rg]["rets"].append(ret)
    return {"horizon": horizon, "window_days": days or "all", "per_regime": per,
            "n_days": sum(v["n"] for v in per.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--days", type=int, default=0)
    a = ap.parse_args()
    r = run(a.horizon, a.days)
    print("=" * 74)
    print(f"  REGIME CLASSIFIER ACCURACY — {a.horizon}-session forward · window={r['window_days']}")
    print(f"  (did SPY's forward move match the regime hypothesis?)  n_days={r['n_days']}")
    print("=" * 74)
    tot_n = tot_h = 0
    for rg, v in sorted(r["per_regime"].items(), key=lambda x: -x[1]["n"]):
        n, h = v["n"], v["hit"]
        tot_n += n; tot_h += h
        avg = sum(v["rets"]) / len(v["rets"]) if v["rets"] else 0
        acc = h / n * 100 if n else 0
        flag = "✓" if acc >= 60 else "⚠" if acc >= 45 else "✗"
        print(f"  {flag} {rg:20s} n={n:>4}  hit={acc:>5.1f}%  avg fwd SPY={avg:>+5.2f}%")
    overall = tot_h / tot_n * 100 if tot_n else 0
    print("-" * 74)
    print(f"  OVERALL classifier accuracy: {overall:.1f}%  ({tot_h}/{tot_n} days matched)")
    print("=" * 74)
    print("  READ: ≥60% = classifier is predictive; 45-60% = weak; <45% = the regime label")
    print("  disagrees with the tape (principle 18 — fix this before trusting regime gates).")
    print("  NOTE: most history is one regime (risk_on_choppy) so per-regime n is skewed.")


if __name__ == "__main__":
    main()
