#!/usr/bin/env python3
"""
compare_backtests.py — diff a "current" backtest result vs a "baseline" snapshot.

Usage:
    python3 scripts/compare_backtests.py [current_path] [baseline_path]

Defaults:
    current  = cache/portfolio_backtest.json
    baseline = picks the most-recent portfolio_backtest_*.json with mtime
               < current's mtime (i.e., the prior run).

Prints:
    - side-by-side metrics (PF, WR, MaxDD, total_return, n_trades, sharpe)
    - delta column (current - baseline)
    - acceptance bar pass/fail (PF≥1.4, WR≥40%, MaxDD<20%)
    - per-setup breakdown if both have setup_stats
    - regime breakdown if both have it
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _find_baseline(current_path: Path) -> Path | None:
    cur_mtime = current_path.stat().st_mtime
    candidates = sorted(
        (REPO / "cache").glob("portfolio_backtest_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if p.stat().st_mtime < cur_mtime:
            return p
    return None


def _fmt(val, fmt="6.2f"):
    if val is None:
        return f"{'—':>{int(fmt.split('.')[0])}s}"
    try:
        return f"{val:{fmt}}"
    except (ValueError, TypeError):
        return str(val)


def _regime_stats(trades: list) -> dict:
    """Group by regime; compute n, WR, PF, avg."""
    from collections import defaultdict
    g = defaultdict(lambda: {'n': 0, 'wins': 0, 'sum_win': 0.0, 'sum_loss': 0.0, 'sum': 0.0})
    for t in trades or []:
        r = (t.get('regime') or 'unknown').lower()
        pnl = t.get('pnl_pct') or 0
        g[r]['n'] += 1
        g[r]['sum'] += pnl
        if pnl > 0:
            g[r]['wins'] += 1
            g[r]['sum_win'] += pnl
        else:
            g[r]['sum_loss'] += abs(pnl)
    out = {}
    for r, d in g.items():
        wr = d['wins'] / d['n'] if d['n'] else 0
        pf = d['sum_win'] / d['sum_loss'] if d['sum_loss'] else float('inf') if d['sum_win'] else 0
        avg = d['sum'] / d['n'] if d['n'] else 0
        out[r] = {'n': d['n'], 'wr': wr, 'pf': pf, 'avg': avg}
    return out


def _setup_stats_simple(trades: list) -> dict:
    """Same shape but grouped by setup_type."""
    from collections import defaultdict
    g = defaultdict(lambda: {'n': 0, 'wins': 0, 'sum_win': 0.0, 'sum_loss': 0.0})
    for t in trades or []:
        s = t.get('setup_type') or 'unknown'
        pnl = t.get('pnl_pct') or 0
        g[s]['n'] += 1
        if pnl > 0:
            g[s]['wins'] += 1
            g[s]['sum_win'] += pnl
        else:
            g[s]['sum_loss'] += abs(pnl)
    out = {}
    for s, d in g.items():
        wr = d['wins'] / d['n'] if d['n'] else 0
        pf = d['sum_win'] / d['sum_loss'] if d['sum_loss'] else float('inf') if d['sum_win'] else 0
        out[s] = {'n': d['n'], 'wr': wr, 'pf': pf}
    return out


def main():
    args = sys.argv[1:]
    current_path = Path(args[0]) if len(args) > 0 else REPO / "cache" / "portfolio_backtest.json"
    if not current_path.exists():
        print(f"ERROR: {current_path} missing")
        sys.exit(1)

    baseline_path = Path(args[1]) if len(args) > 1 else _find_baseline(current_path)
    if baseline_path is None or not baseline_path.exists():
        print("WARN: no baseline found (prior portfolio_backtest_*.json), showing current only")
        baseline = {}
    else:
        baseline = json.loads(baseline_path.read_text())
    current = json.loads(current_path.read_text())

    print(f"CURRENT:  {current_path.name}")
    if baseline:
        print(f"BASELINE: {baseline_path.name}")
    print()

    rows = [
        ('PF', 'profit_factor', '6.2f'),
        ('WR%', 'win_rate', '5.1f'),
        ('MaxDD%', 'max_drawdown_pct', '6.2f'),
        ('Return%', 'total_return_pct', '+6.2f'),
        ('Trades', 'total_trades', '5d'),
        ('Wins', 'wins', '5d'),
        ('Losses', 'losses', '5d'),
        ('Sharpe', 'sharpe', '+5.2f'),
        ('Avg Win%', 'avg_win_pct', '+6.2f'),
        ('Avg Loss%', 'avg_loss_pct', '+6.2f'),
    ]
    print(f"{'METRIC':<12} {'CURRENT':>10} {'BASELINE':>10} {'DELTA':>10}")
    print('-' * 50)
    for label, key, fmt in rows:
        cv = current.get(key)
        bv = baseline.get(key)
        delta = (cv - bv) if (cv is not None and bv is not None) else None
        # Pick formatter that handles ints / floats
        if 'd' in fmt:
            cv_s = f"{cv:>10}" if cv is not None else f"{'—':>10}"
            bv_s = f"{bv:>10}" if bv is not None else f"{'—':>10}"
            d_s = f"{delta:+10}" if delta is not None and isinstance(delta, int) else (
                  f"{delta:+10.0f}" if delta is not None else f"{'—':>10}")
        else:
            cv_s = f"{cv:>10.2f}" if cv is not None else f"{'—':>10}"
            bv_s = f"{bv:>10.2f}" if bv is not None else f"{'—':>10}"
            d_s = f"{delta:+10.2f}" if delta is not None else f"{'—':>10}"
        print(f"{label:<12} {cv_s} {bv_s} {d_s}")

    # Acceptance bar
    print()
    print('ACCEPTANCE BAR (paper-trading activation):')
    pf = current.get('profit_factor', 0) or 0
    wr = current.get('win_rate', 0) or 0
    mdd = current.get('max_drawdown_pct', 999) or 999
    pf_pass = pf >= 1.4
    wr_pass = wr >= 40
    mdd_pass = mdd < 20
    all_pass = pf_pass and wr_pass and mdd_pass
    print(f"  PF >= 1.4:    {pf:6.2f}  {'✓ PASS' if pf_pass else '✗ FAIL'}")
    print(f"  WR >= 40%:    {wr:6.1f}  {'✓ PASS' if wr_pass else '✗ FAIL'}")
    print(f"  MaxDD < 20%:  {mdd:6.2f}  {'✓ PASS' if mdd_pass else '✗ FAIL'}")
    print()
    print(f"  OVERALL: {'✓ READY FOR PAPER TRADING' if all_pass else '✗ NOT READY'}")

    # Regime breakdown
    cur_trades = current.get('trades') or []
    base_trades = baseline.get('trades') or []
    if cur_trades:
        print()
        print('PER-REGIME (CURRENT):')
        rs = _regime_stats(cur_trades)
        for r in sorted(rs.keys(), key=lambda x: -rs[x]['n']):
            d = rs[r]
            print(f"  {r:10s} n={d['n']:>3} WR={d['wr']*100:5.1f}% PF={d['pf']:.2f} avg={d['avg']:+5.2f}%")
    if base_trades:
        print()
        print('PER-REGIME (BASELINE):')
        rs = _regime_stats(base_trades)
        for r in sorted(rs.keys(), key=lambda x: -rs[x]['n']):
            d = rs[r]
            print(f"  {r:10s} n={d['n']:>3} WR={d['wr']*100:5.1f}% PF={d['pf']:.2f} avg={d['avg']:+5.2f}%")

    # Per-setup breakdown
    if cur_trades:
        print()
        print('PER-SETUP (CURRENT, top 8):')
        ss = _setup_stats_simple(cur_trades)
        for s in sorted(ss.keys(), key=lambda x: -ss[x]['n'])[:8]:
            d = ss[s]
            print(f"  {s[:25]:<25} n={d['n']:>3} WR={d['wr']*100:5.1f}% PF={d['pf']:.2f}")


if __name__ == '__main__':
    main()
