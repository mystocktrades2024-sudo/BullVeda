#!/usr/bin/env python3
"""P2 spike: Market+Momentum factor attribution on closed trades.

ORIGINAL PLAN: regress closed trades vs Ken French FF5+MOM daily factors.
ACTUAL CONSTRAINT: Ken French data lags ~6 weeks; trade journal starts 2026-04-13
                   → zero overlap. Deferred until older trade data is added OR
                   K. French publishes mid-month update.

PRAGMATIC SPIKE: use EODHD SPY daily returns as market-factor proxy + ticker's
own 63-day return (at entry) as momentum-factor proxy. Compute per-trade
market-beta + per-setup factor exposure. This is "factor model inspired"
not Fama-French exact, but actionable today.

Output: cache/factor_attribution_market_<date>.json
"""
from __future__ import annotations
import json
import sys
from datetime import date, datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data_fetcher import fetch_ohlcv_with_failover


def _iter_trades(d):
    if isinstance(d, dict):
        if d.get("pnl_pct") is not None or d.get("actual_pnl_pct") is not None:
            yield d
        for v in d.values():
            yield from _iter_trades(v)
    elif isinstance(d, list):
        for x in d:
            yield from _iter_trades(x)


def load_trades():
    trades = []
    sl_path = ROOT / "data" / "signal_log.json"
    if sl_path.exists():
        for t in (json.loads(sl_path.read_text()) or []):
            if not isinstance(t, dict) or t.get("status") != "CLOSED":
                continue
            pnl = t.get("actual_pnl_pct")
            entry_d = t.get("date")
            hold = t.get("hold_days") or 5
            if pnl is None or not entry_d:
                continue
            try:
                pnl = float(pnl) / 100
                entry_d = datetime.strptime(entry_d[:10], "%Y-%m-%d").date()
                exit_d = entry_d + pd.Timedelta(days=int(hold * 1.5)).to_pytimedelta()
            except (TypeError, ValueError):
                continue
            if pnl != pnl or abs(pnl) > 1.0: continue  # pnl != pnl drops NaN (open/unrealized rows)
            trades.append({
                "ticker": t.get("ticker"),
                "setup": t.get("setup_family") or t.get("strategy") or "?",
                "regime": t.get("regime_at_entry") or t.get("regime4") or t.get("regime"),
                "entry": entry_d, "exit": exit_d,
                "pnl": pnl, "hold": hold,
            })
    ph = json.loads((ROOT / "cache" / "picks_history.json").read_text())
    for t in _iter_trades(ph):
        pnl = t.get("pnl_pct") if t.get("pnl_pct") is not None else t.get("actual_pnl_pct")
        entry_d = t.get("entry_date") or t.get("date") or t.get("run_date")
        exit_d = t.get("exit_date")
        hold = t.get("hold_days") or 5
        if pnl is None or not entry_d: continue
        try:
            pnl = float(pnl) / 100
            entry_d = datetime.strptime(entry_d[:10], "%Y-%m-%d").date()
            if exit_d: exit_d = datetime.strptime(exit_d[:10], "%Y-%m-%d").date()
            else: exit_d = entry_d + pd.Timedelta(days=int(hold * 1.5)).to_pytimedelta()
        except (TypeError, ValueError): continue
        if abs(pnl) > 1.0: continue
        trades.append({
            "ticker": t.get("ticker"),
            "setup": t.get("setup_family") or t.get("setup_type") or "?",
            "regime": t.get("regime4") or t.get("regime"),
            "entry": entry_d, "exit": exit_d, "pnl": pnl, "hold": hold,
        })
    return trades


def main():
    print("Fetching SPY (market proxy) + QQQ (tech-momentum proxy)...")
    spy, _ = fetch_ohlcv_with_failover("SPY", days=400)
    qqq, _ = fetch_ohlcv_with_failover("QQQ", days=400)
    if spy is None or qqq is None or len(spy) < 100:
        print("ETF fetch failed — abort"); return 1
    # Daily returns
    spy["ret"] = spy["Close"].pct_change()
    qqq["ret"] = qqq["Close"].pct_change()
    print(f"  SPY range: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} days)")
    print()

    trades = load_trades()
    print(f"Loaded {len(trades)} closed trades")
    if not trades: return 1

    # For each trade: compute market return + tech-momentum return over hold window
    decomposed = []
    for t in trades:
        if not t["exit"]: continue
        entry_ts = pd.Timestamp(t["entry"])
        exit_ts = pd.Timestamp(t["exit"])
        spy_window = spy[(spy.index >= entry_ts) & (spy.index <= exit_ts)]
        qqq_window = qqq[(qqq.index >= entry_ts) & (qqq.index <= exit_ts)]
        if len(spy_window) < 1: continue
        mkt_ret = float((1 + spy_window["ret"].fillna(0)).prod() - 1)
        tech_ret = float((1 + qqq_window["ret"].fillna(0)).prod() - 1) if len(qqq_window) >= 1 else mkt_ret
        # MOM-proxy: QQQ - SPY (tech-momentum spread)
        mom_proxy = tech_ret - mkt_ret
        decomposed.append({**t, "market": mkt_ret, "tech": tech_ret, "mom_proxy": mom_proxy})

    if not decomposed:
        print("No trades intersect ETF data — abort"); return 1
    print(f"Decomposed {len(decomposed)} trades with market+momentum exposure")
    print()

    # Aggregate OLS: pnl = alpha + beta_mkt × market + beta_mom × mom_proxy
    import statsmodels.api as sm

    def _finite(*arrs):
        """Drop any row where pnl or a factor is non-finite (NaN/inf) so a single
        bad row (e.g. a trade whose dates fall outside SPY history → NaN factor)
        can't poison the whole regression — it previously NaN'd the high-n setups."""
        mask = np.ones(len(arrs[0]), dtype=bool)
        for a in arrs:
            mask &= np.isfinite(a)
        return [a[mask] for a in arrs], int(mask.sum())

    pnls = np.array([t["pnl"] for t in decomposed], dtype=float)
    mkt = np.array([t["market"] for t in decomposed], dtype=float)
    mom = np.array([t["mom_proxy"] for t in decomposed], dtype=float)
    (pnls, mkt, mom), _nfit = _finite(pnls, mkt, mom)
    X = sm.add_constant(np.column_stack([mkt, mom]))
    model = sm.OLS(pnls, X).fit()
    if _nfit < len(decomposed):
        print(f"  (dropped {len(decomposed) - _nfit} non-finite rows from regression)")

    print("=" * 80)
    print("  AGGREGATE FACTOR ATTRIBUTION (Market + Tech-Momentum proxy)")
    print("=" * 80)
    print(f"  n trades:        {len(decomposed)}")
    print(f"  avg pnl:         {pnls.mean()*100:+.3f}%")
    print(f"  avg market:      {mkt.mean()*100:+.3f}%")
    print(f"  avg mom_proxy:   {mom.mean()*100:+.3f}%")
    print()
    print(f"  alpha:           {model.params[0]*100:+.4f}% per trade (t={model.tvalues[0]:+.2f}, p={model.pvalues[0]:.3f})")
    print(f"  Market β:        {model.params[1]:+.3f}  (t={model.tvalues[1]:+.2f}, p={model.pvalues[1]:.3f})")
    print(f"  MOM β:           {model.params[2]:+.3f}  (t={model.tvalues[2]:+.2f}, p={model.pvalues[2]:.3f})")
    print(f"  R²:              {model.rsquared:.4f}")
    print()

    # Per-setup
    print("=" * 80)
    print("  PER-SETUP FACTOR LOADINGS (n>=20 only)")
    print("=" * 80)
    from collections import defaultdict
    by_setup = defaultdict(list)
    for t in decomposed:
        by_setup[t["setup"]].append(t)
    for setup, group in sorted(by_setup.items(), key=lambda x: -len(x[1])):
        if len(group) < 20: continue
        p = np.array([t["pnl"] for t in group], dtype=float)
        m = np.array([t["market"] for t in group], dtype=float)
        mo = np.array([t["mom_proxy"] for t in group], dtype=float)
        (p, m, mo), _ng = _finite(p, m, mo)
        if _ng < 20: continue
        X = sm.add_constant(np.column_stack([m, mo]))
        try:
            mdl = sm.OLS(p, X).fit()
            sig_a = "*" if mdl.pvalues[0] < 0.05 else " "
            sig_b = "*" if mdl.pvalues[1] < 0.05 else " "
            sig_c = "*" if mdl.pvalues[2] < 0.05 else " "
            print(f"  {setup:<28} n={len(group):>3}  α={mdl.params[0]*100:+.3f}%{sig_a}  "
                  f"Mkt={mdl.params[1]:+.2f}{sig_b}  MOM={mdl.params[2]:+.2f}{sig_c}  R²={mdl.rsquared:.2f}")
        except Exception:
            pass

    # Per-regime
    print()
    print("=" * 80)
    print("  PER-REGIME FACTOR LOADINGS (n>=20 only)")
    print("=" * 80)
    by_regime = defaultdict(list)
    for t in decomposed:
        by_regime[t["regime"] or "?"].append(t)
    for regime, group in sorted(by_regime.items(), key=lambda x: -len(x[1])):
        if len(group) < 20: continue
        p = np.array([t["pnl"] for t in group], dtype=float)
        m = np.array([t["market"] for t in group], dtype=float)
        mo = np.array([t["mom_proxy"] for t in group], dtype=float)
        (p, m, mo), _ng = _finite(p, m, mo)
        if _ng < 20: continue
        X = sm.add_constant(np.column_stack([m, mo]))
        try:
            mdl = sm.OLS(p, X).fit()
            print(f"  {regime:<28} n={len(group):>3}  α={mdl.params[0]*100:+.3f}%  "
                  f"Mkt={mdl.params[1]:+.2f}  MOM={mdl.params[2]:+.2f}  R²={mdl.rsquared:.2f}")
        except Exception:
            pass

    # Save
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_trades": len(decomposed),
        "factor_source": "EODHD SPY+QQQ (Fama-French proxy)",
        "limitation": "K. French data lags 6 weeks; trade journal too recent. This is market+momentum proxy only.",
        "aggregate": {
            "alpha_pct": float(model.params[0] * 100),
            "alpha_tstat": float(model.tvalues[0]),
            "alpha_pvalue": float(model.pvalues[0]),
            "market_beta": float(model.params[1]),
            "mom_beta": float(model.params[2]),
            "r_squared": float(model.rsquared),
        },
    }
    out_path = ROOT / "cache" / f"factor_attribution_{date.today()}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_path}")
    print()
    print("VALIDATION GATE STATUS (per Research Lab P2):")
    sig = "✅ SIGNIFICANT" if abs(model.tvalues[0]) > 2.0 else "⚠️ NOT SIGNIFICANT"
    print(f"  Alpha: {model.params[0]*100:+.4f}% per trade (t={model.tvalues[0]:+.2f})  {sig}")
    print(f"  Caveat: 2-factor proxy (Mkt + tech-momentum spread), not full FF5+MOM")
    print(f"  Full FF requires K. French data with intra-month update OR older trade data")


if __name__ == "__main__":
    main()
