"""
backtest_v2.py — Minimal V2-aligned backtest.

Reuses:
  - data_fetcher.fetch_market_data  (EODHD, post-2026-04-25 sole provider)
  - backtest._score_as_of, backtest._regime_as_of  (as-of-date scoring)

Bypasses zombie legacy paths (Polygon/yfinance/Finviz). Uses neutral stubs for
news/earnings/insider/finviz (same as legacy backtest's documented limitation).

Universe: BUY + WATCH tickers from today's last_bundle.json (so we test the
same names V2 actually surfaces).

Output:
  - Per-trade: ticker, signal_date, decision, score, regime, fwd_return
  - Aggregate: total trades, win rate, avg return, breakdown by regime/decision
  - JSON written to cache/backtest_v2_results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from data_fetcher import fetch_market_data, get_sp500
import importlib.util as _il
_spec = _il.spec_from_file_location("_bt_legacy", ROOT / "backtest.py")
_bt = _il.module_from_spec(_spec); _spec.loader.exec_module(_bt)
_score_as_of, _regime_as_of = _bt._score_as_of, _bt._regime_as_of

CFG = json.loads((ROOT / "config" / "config.json").read_text())
BUNDLE = json.loads((ROOT / "cache" / "last_bundle.json").read_text())

# Universe: full S&P 500 (today's membership — minor survivorship bias for short windows)
universe = get_sp500()
print(f"Universe: S&P 500, {len(universe)} tickers — {universe[:5]}...")

# Fetch ~1y OHLCV for universe + SPY
print("Fetching OHLCV via EODHD (1y)...")
md = fetch_market_data(universe + ["SPY"], period="1y")
spy_df = md.get("SPY")
if spy_df is None or len(spy_df) < 200:
    print("FATAL: SPY data unavailable or too short")
    sys.exit(1)
print(f"SPY rows: {len(spy_df)}, ticker dataframes: {sum(1 for t in universe if md.get(t) is not None)}/{len(universe)}")

# 12 as-of dates spaced every 5 trading days, ending 5 days before latest
spy_dates = list(spy_df.index)
last_safe = len(spy_dates) - 6   # need 5 days forward
asof_indices = [last_safe - i * 5 for i in range(12) if last_safe - i * 5 >= 60]
asof_dates = [spy_dates[i] for i in asof_indices]
print(f"Test dates: {len(asof_dates)} — {asof_dates[-1].date()} back to {asof_dates[0].date()}")

trades = []
errors = 0
for asof in asof_dates:
    asof_idx = spy_dates.index(asof)
    fwd_idx = asof_idx + 5
    if fwd_idx >= len(spy_dates):
        continue
    regime = _regime_as_of(spy_df, asof)
    for tk in universe:
        df = md.get(tk)
        if df is None or len(df) < 60 or asof not in df.index:
            continue
        try:
            res = _score_as_of(tk, df, asof, spy_df, CFG, info={}, finviz_data=None)
        except Exception as e:
            errors += 1
            continue
        if not res:
            continue
        verdict = res.get("verdict")
        score = res.get("score") or 0
        gate_passed = res.get("gate_passed")
        rr = res.get("rr_ratio") or 0
        # Backtest-mode threshold: live BUY threshold (58-60) is unreachable
        # without news/fundamentals/insider/earnings pillars (no point-in-time data).
        # Treat gated WATCH+ with score>=40 and R:R>=2.5 as would-have-been-BUY.
        if verdict not in ("BUY", "WATCH") or not gate_passed or score < 40 or rr < 2.5:
            continue
        # Forward 5-day return
        try:
            entry = float(df.loc[asof, "Close"])
            exit_date = spy_dates[fwd_idx]
            if exit_date not in df.index:
                continue
            exit_p = float(df.loc[exit_date, "Close"])
            ret = (exit_p / entry - 1) * 100
        except Exception:
            continue
        trades.append({
            "ticker": tk,
            "signal_date": str(asof.date()),
            "score": round(float(score), 1),
            "verdict": verdict,
            "rr": round(float(rr), 2),
            "setup": res.get("setup_type"),
            "regime": regime["regime"],
            "entry": round(entry, 2),
            "exit": round(exit_p, 2),
            "fwd_return_pct": round(ret, 2),
        })

# Aggregate
n = len(trades)
if n == 0:
    print("\n=== RESULT: 0 BUY signals generated across test dates ===")
    print(f"Errors during scoring: {errors}")
    sys.exit(0)

wins = sum(1 for t in trades if t["fwd_return_pct"] > 0)
avg_ret = sum(t["fwd_return_pct"] for t in trades) / n
win_rate = wins / n * 100
by_regime: dict = {}
for t in trades:
    r = t["regime"]
    by_regime.setdefault(r, []).append(t["fwd_return_pct"])

summary = {
    "total_trades": n,
    "win_rate_pct": round(win_rate, 1),
    "avg_return_pct": round(avg_ret, 2),
    "scoring_errors": errors,
    "by_regime": {r: {"n": len(v), "win_rate_pct": round(sum(1 for x in v if x>0)/len(v)*100, 1),
                       "avg_return_pct": round(sum(v)/len(v), 2)} for r, v in by_regime.items()},
    "trades": trades,
    "limitations": [
        "5-day fixed hold (no stop/target)",
        "neutral stubs for news/earnings/insider/finviz (no point-in-time)",
        "RELAXED THRESHOLD: gated WATCH+ with score>=40 and R:R>=2.5 (live BUY thresh is 58-60)",
        "universe is TODAY's S&P 500 membership (minor survivorship bias on 3-mo window)",
        "no slippage / commissions",
    ],
    "ran_at": datetime.now().isoformat(timespec="seconds"),
}
out = ROOT / "cache" / "backtest_v2_results.json"
out.write_text(json.dumps(summary, indent=2))

print()
print("=" * 60)
print(f"  BACKTEST V2 — {n} BUY signals over {len(asof_dates)} dates")
print("=" * 60)
print(f"  Win rate:    {win_rate:.1f}%   ({wins}/{n})")
print(f"  Avg return:  {avg_ret:+.2f}%   (5-day hold)")
print(f"  Errors:      {errors}")
print()
print("  By regime:")
for r, stats in summary["by_regime"].items():
    print(f"    {r:10s}  n={stats['n']:3d}  WR={stats['win_rate_pct']:5.1f}%  avg={stats['avg_return_pct']:+.2f}%")
print()
print(f"  Full results: cache/backtest_v2_results.json")
print("=" * 60)
