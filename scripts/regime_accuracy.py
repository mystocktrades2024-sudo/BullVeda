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

SYNTHETIC / HISTORICAL mode (--synthetic-labels):
  The default (scan-history) mode can only validate regimes the scanner actually
  ran through — over the 64-day labeled history that was ONLY risk_on_choppy +
  risk_on_trending; risk_off_trending and panic were NEVER validated. To test the
  drawdown hypotheses, --synthetic-labels RE-LABELS every session in the local
  SPY.parquet archive by running the SAME classifier thresholds (panic_vix=35,
  trending_vix=20, risk_off_consecutive_closes=2) over SPY-position + VIX, then
  checks forward accuracy exactly as the scan-history mode does.
  LIMITATION: market breadth (pct_above_50d) is NOT in the local archive, so the
  breadth branches (panic_breadth<20, trending_breadth>60) cannot be applied —
  historical labels use VIX + SPY-position (EMA50/SMA200) only. The local SPY/VIX
  archive begins 2023-05, so 2018-Q4 / 2020-COVID / 2022-bear are out of range
  (no network is used); but 2023-2026 still contains real stress (VIX peak 52.3
  on 2025-04-08, 6 sessions VIX>35, 167 sessions SPY<EMA50) which exercises the
  risk_off_trending and panic labels the scan history never reached.
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HIST = BASE / "cache" / "picks_history.json"
SPY = BASE / "data" / "ohlcv" / "SPY.parquet"
VIX = BASE / "data" / "ohlcv" / "VIX.parquet"
CONFIG = BASE / "config" / "config.json"


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


def _vix_series():
    import pandas as pd
    df = pd.read_parquet(VIX)
    if not isinstance(df.index, pd.DatetimeIndex):
        dcol = next((c for c in ("date", "Date") if c in df.columns), df.columns[0])
        df = df.set_index(pd.to_datetime(df[dcol]))
    ccol = next((c for c in ("adj_close", "Adj Close", "Close", "close") if c in df.columns), None)
    return df.sort_index()[ccol]


def _load_thresholds():
    """The SAME thresholds the live classifier uses (data_fetcher.get_market_regime
    reads config.regime_classifier, falling back to these hardcoded defaults)."""
    cfg = {}
    try:
        cfg = json.loads(CONFIG.read_text()).get("regime_classifier", {})
    except Exception:
        pass
    return {
        "panic_vix":        cfg.get("panic_vix", 35.0),
        "panic_breadth":    cfg.get("panic_breadth", 20.0),
        "trending_vix":     cfg.get("trending_vix", 20.0),
        "trending_breadth": cfg.get("trending_breadth", 60.0),
        "risk_off_closes":  int(cfg.get("risk_off_consecutive_closes", 2)),
    }


def synthetic_label_by_date(min_history=200):
    """Re-label every historical SPY session from SPY-position + VIX using the SAME
    classification order and thresholds as data_fetcher.get_market_regime:
        panic  ← VIX > panic_vix           (breadth<panic_breadth branch OMITTED — no archive)
        risk_off_trending ← N consecutive closes below EMA50 (risk_off_consecutive_closes)
        risk_on_trending  ← SPY>EMA50 AND SPY>SMA200 AND VIX<trending_vix
                            (breadth>trending_breadth branch OMITTED — no archive)
        risk_on_choppy    ← otherwise
    Returns ({date_iso: regime4}, thresholds).  Local parquet only; no network."""
    import pandas as pd
    thr = _load_thresholds()
    spy = _spy_series()
    vix = _vix_series().reindex(spy.index).ffill()   # align VIX onto SPY sessions
    ema50 = spy.ewm(span=50, adjust=False).mean()
    sma200 = spy.rolling(200).mean()
    n_closes = max(1, thr["risk_off_closes"])
    out = {}
    for i in range(len(spy)):
        if i < min_history:            # SMA200 not meaningful before this
            continue
        price = float(spy.iloc[i])
        v = float(vix.iloc[i]) if pd.notna(vix.iloc[i]) else None
        above50 = price > float(ema50.iloc[i])
        above200 = pd.notna(sma200.iloc[i]) and price > float(sma200.iloc[i])
        # consecutive closes below EMA50 (risk_off confirmation) — mirrors the code
        if i >= n_closes - 1:
            roff = all(float(spy.iloc[i - k]) < float(ema50.iloc[i - k]) for k in range(n_closes))
        else:
            roff = not above50
        if v is not None and v > thr["panic_vix"]:
            rg = "panic"
        elif roff:
            rg = "risk_off_trending"
        elif above50 and above200 and v is not None and v < thr["trending_vix"]:
            rg = "risk_on_trending"
        else:
            rg = "risk_on_choppy"
        out[spy.index[i].strftime("%Y-%m-%d")] = rg
    return out, thr


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


def run(horizon=5, days=0, synthetic=False):
    thr = None
    if synthetic:
        labels, thr = synthetic_label_by_date()
    else:
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
    _dates = sorted(labels.keys())
    return {"horizon": horizon, "window_days": days or "all", "per_regime": per,
            "n_days": sum(v["n"] for v in per.values()), "synthetic": synthetic,
            "thresholds": thr, "label_span": (_dates[0], _dates[-1]) if _dates else None,
            "n_labeled": len(labels)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--synthetic-labels", "--historical", dest="synthetic",
                    action="store_true",
                    help="re-label the full local SPY.parquet history from SPY-position + VIX "
                         "using live classifier thresholds (tests risk_off_trending + panic)")
    a = ap.parse_args()
    r = run(a.horizon, a.days, a.synthetic)
    print("=" * 74)
    _mode = "SYNTHETIC/HISTORICAL (SPY+VIX re-label)" if a.synthetic else "SCAN-HISTORY (labeled picks)"
    print(f"  REGIME CLASSIFIER ACCURACY — {a.horizon}-session forward · window={r['window_days']}")
    print(f"  source: {_mode}")
    if r.get("label_span"):
        print(f"  labeled span: {r['label_span'][0]} → {r['label_span'][1]}  ({r['n_labeled']} sessions)")
    if a.synthetic and r.get("thresholds"):
        t = r["thresholds"]
        print(f"  thresholds: panic_vix={t['panic_vix']}  trending_vix={t['trending_vix']}  "
              f"risk_off_closes={t['risk_off_closes']}  (breadth branches OMITTED — not archived)")
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
    if a.synthetic:
        print("  NOTE: synthetic labels use VIX + SPY-position ONLY (breadth not archived);")
        print("  local SPY/VIX archive starts 2023-05 (2018/2020/2022 out of range, no network).")
    else:
        print("  NOTE: most history is one regime (risk_on_choppy) so per-regime n is skewed.")
        print("  Run with --synthetic-labels to test risk_off_trending + panic over full SPY history.")


if __name__ == "__main__":
    main()
