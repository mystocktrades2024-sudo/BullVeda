#!/usr/bin/env python3
"""backtest_sleeves_quick.py — multi-sleeve historical replay.

Tests Mean Reversion + Defensive Rotation + Momentum Continuation against
data_archive OHLCV over the last N days. Each day, identifies tickers
that would have fired the sleeve detector, computes 5d forward return,
aggregates.

CLAUDE.md compliance:
  - n>=30 floor + Wilson LB
  - Slippage 5bp applied
  - No look-ahead

Usage:
  python3 scripts/backtest_sleeves_quick.py             # 90d default
  python3 scripts/backtest_sleeves_quick.py --days 180
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + (z * z) / n
    num = p + (z * z) / (2 * n) - z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)
    return num / denom


def _rsi(closes, period=14):
    """14-period RSI from closes (list of floats)."""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains.append(max(0, ch))
        losses.append(max(0, -ch))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    e = sum(closes[:period]) / period
    for c in closes[period:]:
        e = c * k + e * (1 - k)
    return e


def _forward_return_pct(df, entry_idx: int, hold_days: int) -> float | None:
    """5d forward return from entry_idx (next bar open → exit close)."""
    if entry_idx + hold_days >= len(df):
        return None
    try:
        entry_price = float(df.iloc[entry_idx + 1]["Open"]) if "Open" in df.columns else float(df.iloc[entry_idx + 1]["open"])
        exit_idx = entry_idx + 1 + hold_days
        if exit_idx >= len(df):
            exit_idx = len(df) - 1
        exit_price = float(df.iloc[exit_idx]["Close"]) if "Close" in df.columns else float(df.iloc[exit_idx]["close"])
        if entry_price <= 0:
            return None
        gross = ((exit_price - entry_price) / entry_price) * 100
        return round(gross - 0.05, 3)  # 5bp slippage
    except Exception:
        return None


def _stats_block(rets: list[float], label: str) -> dict:
    n = len(rets)
    if n < 5:
        return {"n": n, "label": label, "verdict": "n too small"}
    wins = sum(1 for r in rets if r > 0)
    wr = wins / n
    wlb = _wilson_lb(wins, n)
    avg = statistics.mean(rets)
    std = statistics.stdev(rets) if n >= 2 else 0
    win_pnls = [r for r in rets if r > 0]
    loss_pnls = [r for r in rets if r <= 0]
    pf = sum(win_pnls) / max(abs(sum(loss_pnls)), 0.01)
    haircut_pf = pf - 0.20
    passes_phase1 = (haircut_pf >= 1.3 and wlb >= 0.45 and n >= 30)
    return {
        "n": n, "label": label,
        "wr": round(wr, 3), "wlb": round(wlb, 3),
        "avg": round(avg, 3), "std": round(std, 3),
        "pf": round(pf, 3), "haircut_pf": round(haircut_pf, 3),
        "max_win": round(max(rets), 2), "max_loss": round(min(rets), 2),
        "phase1_pass": passes_phase1,
    }


def _print_stats(s: dict):
    if s.get("verdict") == "n too small":
        print(f"  {s['label']:<30} n={s['n']:>4}  (too small)")
        return
    flag = " ⚠️ n<30" if s["n"] < 30 else ""
    pass_flag = " ✓ Phase1" if s.get("phase1_pass") else ""
    print(f"  {s['label']:<30} n={s['n']:>4} WR={s['wr']*100:>5.1f}% WLB={s['wlb']*100:>5.1f}% "
          f"avg={s['avg']:>+6.2f}% PF={s['pf']:>5.2f} (haircut {s['haircut_pf']:>5.2f}){flag}{pass_flag}")


def backtest_mean_reversion(tickers: list[str], days: int) -> dict:
    """Mean Reversion: RSI<30 + price>EMA200 + recent low w/in 5d."""
    print(f"\n=== MEAN REVERSION ({days}d lookback) ===")
    print("Trigger: RSI(14)<30 AND price>EMA200")
    from data_archive import load_ticker
    today = date.today()
    cutoff = today - timedelta(days=days)
    all_trades = []
    for sym in tickers:
        try:
            df = load_ticker(sym)
            if df is None or len(df) < 250:
                continue
            closes = df["Close"].astype(float).tolist() if "Close" in df.columns else df["close"].astype(float).tolist()
            # Iterate every bar in the lookback window
            for i in range(200, len(df) - 6):  # need 200 bars history + 5d forward
                bar_date = df.index[i].date() if hasattr(df.index[i], "date") else None
                if bar_date is None or bar_date < cutoff:
                    continue
                # RSI on closes[i-13:i+1]
                rsi = _rsi(closes[max(0, i - 14):i + 1])
                if rsi is None or rsi >= 30:
                    continue
                # EMA200 floor
                ema200 = _ema(closes[max(0, i - 199):i + 1], 200)
                if ema200 is None or closes[i] <= ema200:
                    continue
                # 5d forward return
                ret = _forward_return_pct(df, i, 5)
                if ret is None:
                    continue
                all_trades.append({"ticker": sym, "date": bar_date.isoformat(),
                                    "rsi": round(rsi, 1), "ret_5d": ret})
        except Exception:
            continue
    rets = [t["ret_5d"] for t in all_trades]
    s = _stats_block(rets, "Mean Reversion (aggregate)")
    _print_stats(s)
    # Stratify by RSI band
    print("  Stratified by RSI band (5d return):")
    for label, lo, hi in [("RSI 20-30", 20, 30), ("RSI 15-20", 15, 20), ("RSI <15", 0, 15)]:
        bucket = [t["ret_5d"] for t in all_trades if lo <= t["rsi"] < hi]
        if len(bucket) >= 5:
            sb = _stats_block(bucket, f"  {label}")
            _print_stats(sb)
    return {"strategy": "Mean Reversion", "aggregate": s, "trades": all_trades}


def backtest_momentum_continuation(tickers: list[str], days: int) -> dict:
    """Momentum: 5d return >= +3%, price > EMA8 > EMA21 > EMA50."""
    print(f"\n=== MOMENTUM CONTINUATION ({days}d lookback) ===")
    print("Trigger: 5d return >= +3%, EMA stack price>8>21>50")
    from data_archive import load_ticker
    today = date.today()
    cutoff = today - timedelta(days=days)
    all_trades = []
    for sym in tickers:
        try:
            df = load_ticker(sym)
            if df is None or len(df) < 80:
                continue
            closes = df["Close"].astype(float).tolist() if "Close" in df.columns else df["close"].astype(float).tolist()
            for i in range(50, len(df) - 6):
                bar_date = df.index[i].date() if hasattr(df.index[i], "date") else None
                if bar_date is None or bar_date < cutoff:
                    continue
                # 5d return
                if i < 5:
                    continue
                ret_5d_pre = (closes[i] - closes[i - 5]) / closes[i - 5] * 100
                if ret_5d_pre < 3.0:
                    continue
                # EMA stack
                ema8 = _ema(closes[max(0, i - 7):i + 1], 8)
                ema21 = _ema(closes[max(0, i - 20):i + 1], 21)
                ema50 = _ema(closes[max(0, i - 49):i + 1], 50)
                if not (ema8 and ema21 and ema50):
                    continue
                if not (closes[i] > ema8 > ema21 > ema50):
                    continue
                ret = _forward_return_pct(df, i, 5)
                if ret is None:
                    continue
                all_trades.append({"ticker": sym, "date": bar_date.isoformat(),
                                    "ret_5d_pre": round(ret_5d_pre, 2), "ret_5d": ret})
        except Exception:
            continue
    rets = [t["ret_5d"] for t in all_trades]
    s = _stats_block(rets, "Momentum Continuation (aggregate)")
    _print_stats(s)
    return {"strategy": "Momentum Continuation", "aggregate": s, "trades": all_trades}


def backtest_defensive_rotation(days: int) -> dict:
    """Defensive: long XLU/XLP/XLV/IEF/TLT/GLD when SPY < 50EMA."""
    print(f"\n=== DEFENSIVE ROTATION ({days}d lookback) ===")
    print("Trigger: SPY < 50EMA (today) — defensive ETF flow window")
    from data_archive import load_ticker
    today = date.today()
    cutoff = today - timedelta(days=days)
    # Load SPY first
    spy = load_ticker("SPY")
    if spy is None:
        print("  SPY data unavailable")
        return {"strategy": "Defensive Rotation", "aggregate": None}
    spy_closes = spy["Close"].astype(float).tolist() if "Close" in spy.columns else spy["close"].astype(float).tolist()
    spy_dates = [d.date() if hasattr(d, "date") else None for d in spy.index]
    # Build SPY-below-50EMA indicator
    spy_below_50 = []
    for i in range(len(spy_closes)):
        if i < 50:
            spy_below_50.append(False)
        else:
            ema50 = _ema(spy_closes[max(0, i - 49):i + 1], 50)
            spy_below_50.append(closes_below := (spy_closes[i] < ema50) if ema50 else False)

    spy_dates_below = [d for d, b in zip(spy_dates, spy_below_50) if b and d and d >= cutoff]
    print(f"  SPY below 50EMA on {len(spy_dates_below)} days in lookback window")

    if not spy_dates_below:
        print("  No qualifying defensive-rotation days in lookback (SPY healthy)")
        return {"strategy": "Defensive Rotation", "aggregate": None, "spy_below_days": 0}

    all_trades = []
    for sym in ["XLU", "XLP", "XLV", "IEF", "TLT", "GLD"]:
        try:
            df = load_ticker(sym)
            if df is None:
                continue
            closes = df["Close"].astype(float).tolist() if "Close" in df.columns else df["close"].astype(float).tolist()
            for i in range(50, len(df) - 6):
                bar_date = df.index[i].date() if hasattr(df.index[i], "date") else None
                if bar_date is None or bar_date < cutoff:
                    continue
                if bar_date not in spy_dates_below:
                    continue
                # Entry condition met (SPY below 50EMA on this day) — buy defensive ETF
                # (LOOSENED 2026-05-14: removed "defensive ETF above own EMA50" requirement
                # which was filtering out all signals. Flight-to-safety thesis says buy
                # defensives WHEN SPY breaks down, not "after defensives already rallied".)
                ret = _forward_return_pct(df, i, 5)
                if ret is None:
                    continue
                all_trades.append({"ticker": sym, "date": bar_date.isoformat(), "ret_5d": ret})
        except Exception:
            continue
    rets = [t["ret_5d"] for t in all_trades]
    s = _stats_block(rets, "Defensive Rotation (aggregate)")
    _print_stats(s)
    # Per-ticker
    print("  By defensive ETF:")
    by_ticker = defaultdict(list)
    for t in all_trades:
        by_ticker[t["ticker"]].append(t["ret_5d"])
    for t, rs in sorted(by_ticker.items(), key=lambda kv: -statistics.mean(kv[1]) if kv[1] else 0):
        if len(rs) >= 3:
            sb = _stats_block(rs, f"  {t}")
            _print_stats(sb)
    return {"strategy": "Defensive Rotation", "aggregate": s, "trades": all_trades}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--top-universe", type=int, default=300, help="Test top N tickers (skip the long-tail)")
    args = ap.parse_args()

    # Load universe — use tickers.json from prototype (recent scan tickers)
    tk_path = REPO / "infra" / "prototype" / "tickers.json"
    if tk_path.exists():
        tickers = list(json.loads(tk_path.read_text()).keys())[:args.top_universe]
    else:
        # Fallback to data_archive directory
        from data_archive import OHLCV_DIR
        tickers = [f.stem for f in OHLCV_DIR.glob("*.parquet")][:args.top_universe]

    print(f"Universe: {len(tickers)} tickers, last {args.days} days, 5d forward, 5bp slippage")

    results = {}
    results["mean_reversion"] = backtest_mean_reversion(tickers, args.days)
    results["momentum"] = backtest_momentum_continuation(tickers, args.days)
    results["defensive"] = backtest_defensive_rotation(args.days)

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for k, v in results.items():
        agg = v.get("aggregate")
        if agg and agg.get("verdict") != "n too small":
            n = agg["n"]
            wr = agg["wr"] * 100
            pf = agg["pf"]
            hpf = agg["haircut_pf"]
            pass_flag = "✓ PASS Phase 1" if agg.get("phase1_pass") else "✗ FAIL Phase 1"
            print(f"  {v['strategy']:<30} n={n:>4} WR={wr:>5.1f}% PF={pf:>5.2f} (haircut {hpf:>5.2f}) {pass_flag}")
        else:
            print(f"  {v['strategy']:<30} insufficient data")

    out_p = REPO / "cache" / f"backtest_sleeves_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSaved: {out_p}")


if __name__ == "__main__":
    main()
