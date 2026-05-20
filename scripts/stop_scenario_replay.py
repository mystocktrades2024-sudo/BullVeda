#!/usr/bin/env python3
"""Counterfactual stop-tightening replay on closed trades.

Uses mae_pct (max adverse excursion) to determine "would tighter stop have hit?"
For each trade:
  - original_stop_pct = planned_risk / entry_price × 100
  - For tightness multiplier M (M < 1):
      new_stop_pct = original_stop_pct × M
      If |mae_pct| > new_stop_pct → tighter stop fires; locked loss = -new_stop_pct
      Else → trade behaves as before (same pnl_pct)
  - For M > 1 (wider): if pnl_pct > 0 unchanged; if loser, can't honestly simulate
    without intra-trade price data. Mark scenario as "wider-unreliable".

Output: cache/stop_scenarios_<date>.json + console matrix
"""
from __future__ import annotations
import json, math, statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT / "cache" / "picks_history.json"
TRADING_DAYS_PER_YEAR = 252


def _iter_trades(d):
    if isinstance(d, dict):
        if d.get("pnl_pct") is not None: yield d
        for v in d.values(): yield from _iter_trades(v)
    elif isinstance(d, list):
        for x in d: yield from _iter_trades(x)


def load_trades():
    out = []
    ph = json.loads(PICKS.read_text())
    for t in _iter_trades(ph):
        try:
            pnl = float(t["pnl_pct"])
            mae = float(t.get("mae_pct") or 0)
            mfe = float(t.get("mfe_pct") or 0)
            entry = float(t.get("entry_price") or 0)
            risk = float(t.get("planned_risk") or 0)
        except (TypeError, ValueError):
            continue
        if abs(pnl) > 100: continue
        if entry <= 0 or risk <= 0: continue
        original_stop_pct = (risk / entry) * 100  # e.g., 2.0 means 2% stop
        out.append({
            **t,
            "_pnl": pnl, "_mae_pct": mae, "_mfe_pct": mfe,
            "_entry": entry, "_orig_stop_pct": original_stop_pct,
        })
    return out


def simulate_stop_tightening(trades, mult: float, label: str):
    """For each trade, simulate stop at original × mult.
    M < 1 = tighter, M > 1 = wider (caveat applies)."""
    results = []
    n_changed = 0
    for t in trades:
        orig_stop_pct = t["_orig_stop_pct"]
        new_stop_pct = orig_stop_pct * mult
        mae_abs = abs(t["_mae_pct"])
        pnl = t["_pnl"]

        if mult < 1.0:
            # Tighter — fires if MAE exceeded new stop
            if mae_abs > new_stop_pct:
                # Tighter stop fires before MAE. Locked loss = -new_stop_pct (no slippage assumed).
                new_pnl = -new_stop_pct
                n_changed += 1
            else:
                new_pnl = pnl  # never reached new stop, outcome unchanged
        elif mult > 1.0:
            # Wider — can't honestly simulate losers; honest approximation:
            # If trade was a winner, unchanged.
            # If trade was a loser AND |pnl| ≈ orig_stop_pct (stop-hit), assume worst case:
            #   wider stop just locks bigger loss (-new_stop_pct).
            # If trade was a loser but didn't hit stop (time exit), no change.
            if pnl >= 0:
                new_pnl = pnl
            else:
                # Was the original loss close to original stop? (stop-hit)
                if abs(pnl) >= orig_stop_pct * 0.85:
                    new_pnl = -new_stop_pct  # worst-case: wider stop, bigger loss
                    n_changed += 1
                else:
                    new_pnl = pnl  # time-exit loser, no change
        else:
            new_pnl = pnl  # mult==1.0 baseline
        results.append({"orig": pnl, "new": new_pnl, "ticker": t.get("ticker")})
    return results, n_changed


def _wilson_lb(wins, n, z=1.96):
    if n == 0: return 0
    p = wins / n
    den = 1 + z*z/n
    num = p + z*z/(2*n) - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return max(0, num/den)


def _stats(pnls, avg_hold=5.0):
    if not pnls: return {"n": 0}
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg = statistics.mean(pnls)
    std = statistics.stdev(pnls) if n >= 2 else 0
    sharpe_t = (avg/std) if std > 0 else 0
    tpy = TRADING_DAYS_PER_YEAR / max(avg_hold, 1)
    sharpe_a = sharpe_t * math.sqrt(tpy) if std > 0 else 0
    gross_w = sum(wins); gross_l = abs(sum(losses))
    pf = (gross_w/gross_l) if gross_l > 0 else float("inf")
    # Sortino
    downside = [p for p in pnls if p < 0]
    dsd = statistics.stdev(downside) if len(downside) >= 2 else (abs(downside[0]) if downside else 0)
    sortino_t = (avg/dsd) if dsd > 0 else 0
    sortino_a = sortino_t * math.sqrt(tpy) if dsd > 0 else 0
    # Max DD
    eq = 100; peak = 100; max_dd = 0
    for p in pnls:
        eq *= (1 + p/100)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak-eq)/peak*100)
    return {
        "n": n, "wr": round(len(wins)/n*100, 1),
        "wilson_lb": round(_wilson_lb(len(wins), n)*100, 1),
        "avg_pnl": round(avg, 3), "stdev": round(std, 3),
        "sharpe_per_trade": round(sharpe_t, 4),
        "sharpe_ann": round(sharpe_a, 3),
        "sortino_per_trade": round(sortino_t, 4),
        "sortino_ann": round(sortino_a, 3),
        "pf": round(pf, 3) if pf != float("inf") else None,
        "pf_haircut": round(pf - 0.10, 3) if isinstance(pf, float) and pf != float("inf") else None,
        "max_dd": round(max_dd, 2),
        "total_pnl": round(sum(pnls), 2),
    }


def main():
    trades = load_trades()
    print(f"Loaded {len(trades)} closed trades")
    avg_hold = statistics.mean([t.get("hold_days") for t in trades if t.get("hold_days")] or [5.0])
    print(f"Avg original stop: {statistics.mean([t['_orig_stop_pct'] for t in trades]):.2f}%")
    print(f"Avg MAE: {statistics.mean([abs(t['_mae_pct']) for t in trades]):.2f}%")
    print(f"Avg MFE: {statistics.mean([t['_mfe_pct'] for t in trades]):.2f}%")
    print()

    # Scenarios — fine-grained sweep around baseline and optimum
    scenarios = [
        ("M=0.50 (very tight)",     0.50),
        ("M=0.65 (tight)",           0.65),
        ("M=0.80 (slightly tight)",  0.80),
        ("M=0.90 (mildly tight)",    0.90),
        ("M=1.00 (BASELINE 1.25xATR)", 1.00),
        ("M=1.05 (= 1.31x ATR)",     1.05),
        ("M=1.10 (= 1.38x ATR)",     1.10),
        ("M=1.15 (= 1.44x ATR)",     1.15),
        ("M=1.20 (= 1.50x ATR)",     1.20),
        ("M=1.25 (= 1.56x ATR)",     1.25),
        ("M=1.30 (= 1.63x ATR)",     1.30),
        ("M=1.35 (= 1.69x ATR)",     1.35),
        ("M=1.40 (= 1.75x ATR)",     1.40),
        ("M=1.50 (= 1.88x ATR)",     1.50),
        ("M=1.75 (= 2.19x ATR)",     1.75),
        ("M=2.00 (= 2.50x ATR)",     2.00),
    ]

    rows = []
    baseline_pnls = None
    for label, mult in scenarios:
        results, n_changed = simulate_stop_tightening(trades, mult, label)
        pnls = [r["new"] for r in results]
        st = _stats(pnls, avg_hold)
        st["mult"] = mult
        st["n_changed"] = n_changed
        st["label"] = label
        rows.append(st)
        if mult == 1.0:
            baseline_pnls = pnls

    # Diff vs baseline
    base = _stats(baseline_pnls, avg_hold) if baseline_pnls else {}
    for r in rows:
        if r["mult"] != 1.0:
            for k in ("sharpe_per_trade", "sortino_per_trade", "pf", "max_dd", "avg_pnl", "wr"):
                if base.get(k) is not None and r.get(k) is not None:
                    r[f"d_{k}"] = round(r[k] - base[k], 4)

    # Print
    print("="*145)
    print(f"  {'SCENARIO':<25} {'n':>5} {'WR':>5} {'WLB':>5} {'avg%':>6} {'σ%':>5} {'Sh/t':>8} {'Sh ann':>7} {'So/t':>8} {'PF':>6} {'MaxDD':>7} {'ΔSh/t':>8} {'ΔPF':>6} {'ΔMaxDD':>8}")
    print("-"*145)
    for r in rows:
        d_sh = r.get("d_sharpe_per_trade")
        d_pf = r.get("d_pf")
        d_dd = r.get("d_max_dd")
        flag = " ⚠️" if r["mult"] > 1.0 else ""
        print(f"  {r['label']:<25} "
              f"{r['n']:>5} {r['wr']:>5.1f} {r['wilson_lb']:>5.1f} "
              f"{r['avg_pnl']:>+6.2f} {r['stdev']:>5.2f} "
              f"{r['sharpe_per_trade']:>+8.4f} {r['sharpe_ann']:>+7.3f} "
              f"{r['sortino_per_trade']:>+8.4f} "
              f"{(r['pf'] if r['pf'] is not None else 0):>6.2f} {r['max_dd']:>6.1f}% "
              f"{(d_sh if d_sh is not None else 0):>+8.4f} "
              f"{(d_pf if d_pf is not None else 0):>+6.3f} "
              f"{(d_dd if d_dd is not None else 0):>+8.2f}{flag}")
    print("="*145)
    print()
    print("⚠️  Wider stops (M>1) flagged — uses worst-case assumption for stop-hit losers (locked at new wider stop).")
    print("    True wider-stop simulation needs intra-trade price data we don't have.")

    # Save
    out = ROOT / "cache" / f"stop_scenarios_{date.today()}.json"
    out.write_text(json.dumps({
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "n_total_trades": len(trades),
        "avg_hold_days": round(avg_hold, 2),
        "scenarios": rows,
    }, indent=2, default=str))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
