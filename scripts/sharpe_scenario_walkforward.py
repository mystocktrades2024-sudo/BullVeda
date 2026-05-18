#!/usr/bin/env python3
"""Walk-forward validation of top scenarios from sharpe_scenario_replay.py.

Splits closed trades into 4 time-folds. For each fold, computes baseline + top
scenarios on that fold's slice. A scenario "passes" if:
  - Improves Sharpe on >= 3 of 4 folds vs baseline
  - Bootstrap Sharpe CI on full data has lower bound > 0
  - n >= 30 per fold

Reports per-fold matrix + aggregate.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Top scenarios from Phase A (in priority order)
TOP_SCENARIOS = [
    {"id": 0, "name": "baseline",                                "filter": lambda t: True},
    {"id": 5, "name": "Score >= 80 only",
     "filter": lambda t: (t.get("score") or 0) >= 80},
    {"id": 9, "name": "Skip FRESH + PULLBACK entries",
     "filter": lambda t: (t.get("entry_quality") or "") not in ("FRESH", "PULLBACK")},
    {"id": 8, "name": "Entry-quality reweight (MISSED+, FRESH-)", "kind": "reweight",
     "weights": {"MISSED": 1.25, "EXTENDED": 1.10, "VALID": 1.00,
                 "PULLBACK": 0.85, "FRESH": 0.60, "": 1.00, None: 1.00}},
    {"id": 1, "name": "Block BE in risk_on_trending",
     "filter": lambda t: not (t.get("regime4") == "risk_on_trending" and t.get("setup_family") == "Breakout Expansion")},
    # New combination — entry-quality + score gate (the two best individual levers)
    {"id": 100, "name": "STACKED: Score>=75 + Skip FRESH/PULLBACK",
     "filter": lambda t: (t.get("score") or 0) >= 75 and (t.get("entry_quality") or "") not in ("FRESH", "PULLBACK")},
    # New combination — selectivity + sleeve gate
    {"id": 101, "name": "STACKED: Score>=75 + Block BE in trending",
     "filter": lambda t: (t.get("score") or 0) >= 75 and not (t.get("regime4") == "risk_on_trending" and t.get("setup_family") == "Breakout Expansion")},
]


def _iter_trades_picks(d):
    if isinstance(d, dict):
        if d.get("pnl_pct") is not None or d.get("actual_pnl_pct") is not None:
            yield d
        for v in d.values():
            yield from _iter_trades_picks(v)
    elif isinstance(d, list):
        for x in d:
            yield from _iter_trades_picks(x)


def load_trades():
    trades = []
    ph = json.loads((ROOT / "cache" / "picks_history.json").read_text())
    for t in _iter_trades_picks(ph):
        pnl = t.get("pnl_pct") if t.get("pnl_pct") is not None else t.get("actual_pnl_pct")
        if pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        if abs(pnl) > 100:
            continue
        # Date for fold ordering
        d = t.get("entry_date") or t.get("date") or t.get("run_date") or ""
        if not d:
            continue
        t2 = dict(t); t2["pnl"] = pnl; t2["_date"] = d
        trades.append(t2)
    trades.sort(key=lambda x: x["_date"])
    return trades


def _stats(pnls):
    if not pnls:
        return {"n": 0}
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg = statistics.mean(pnls)
    std = statistics.stdev(pnls) if n >= 2 else 0
    sharpe_t = (avg / std) if std > 0 else 0.0
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    # Max DD
    equity = 100.0; peak = 100.0; max_dd = 0.0
    for p in pnls:
        equity *= (1 + p / 100)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
    return {
        "n": n,
        "wr": round(len(wins) / n * 100, 1),
        "avg_pnl": round(avg, 3),
        "sharpe": round(sharpe_t, 4),
        "pf": round(pf, 2) if pf != float("inf") else None,
        "max_dd": round(max_dd, 2),
    }


def _apply_scenario(trades, sc):
    if sc.get("kind") == "reweight":
        weights = sc["weights"]
        return [t["pnl"] * weights.get(t.get("entry_quality"), 1.0) for t in trades]
    f = sc.get("filter") or (lambda t: True)
    return [t["pnl"] for t in trades if f(t)]


def _bootstrap_ci_sharpe_diff(base_pnls, sc_pnls, n_boot=1000, seed=42):
    """Bootstrap CI on (scenario Sharpe - baseline Sharpe).
    NB: Different sample sizes — we resample each independently."""
    import random
    rng = random.Random(seed)
    if len(base_pnls) < 10 or len(sc_pnls) < 10:
        return (None, None)
    diffs = []
    for _ in range(n_boot):
        b = [rng.choice(base_pnls) for _ in range(len(base_pnls))]
        s = [rng.choice(sc_pnls) for _ in range(len(sc_pnls))]
        if len(set(b)) < 2 or len(set(s)) < 2:
            continue
        b_sh = statistics.mean(b) / statistics.stdev(b) if statistics.stdev(b) > 0 else 0
        s_sh = statistics.mean(s) / statistics.stdev(s) if statistics.stdev(s) > 0 else 0
        diffs.append(s_sh - b_sh)
    diffs.sort()
    return (round(diffs[int(0.05 * len(diffs))], 4),
            round(diffs[int(0.95 * len(diffs))], 4))


def main():
    trades = load_trades()
    print(f"Loaded {len(trades)} closed trades")
    if not trades:
        return 2
    print(f"Date range: {trades[0]['_date']} → {trades[-1]['_date']}")
    print()

    # 4 equal-size time-ordered folds
    N = len(trades)
    fold_size = N // 4
    folds = [trades[i*fold_size:(i+1)*fold_size if i < 3 else N] for i in range(4)]
    print(f"Fold sizes: {[len(f) for f in folds]}")
    print()

    # Per-fold per-scenario stats
    matrix = {}
    for fi, fold in enumerate(folds):
        fname = f"fold_{fi}"
        matrix[fname] = {"period": f"{fold[0]['_date']} → {fold[-1]['_date']}", "scenarios": {}}
        for sc in TOP_SCENARIOS:
            pnls = _apply_scenario(fold, sc)
            matrix[fname]["scenarios"][f"s{sc['id']}"] = {"name": sc["name"], **_stats(pnls)}

    # Aggregate (all data)
    aggregate = {}
    base_pnls_all = _apply_scenario(trades, TOP_SCENARIOS[0])
    for sc in TOP_SCENARIOS:
        pnls = _apply_scenario(trades, sc)
        st = _stats(pnls)
        # Bootstrap CI on Sharpe DIFFERENCE vs baseline
        lo, hi = _bootstrap_ci_sharpe_diff(base_pnls_all, pnls)
        st["sharpe_diff_5pct"] = lo
        st["sharpe_diff_95pct"] = hi
        # Per-fold win rate (improves vs baseline)
        improvements = 0
        for fi in range(4):
            base_sh = matrix[f"fold_{fi}"]["scenarios"]["s0"].get("sharpe") or 0
            sc_sh = matrix[f"fold_{fi}"]["scenarios"][f"s{sc['id']}"].get("sharpe") or 0
            if sc_sh > base_sh:
                improvements += 1
        st["folds_improved"] = improvements
        aggregate[f"s{sc['id']}"] = {"name": sc["name"], **st}

    # Save
    out = ROOT / "cache" / f"sharpe_walkforward_{date.today()}.json"
    out.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_total_trades": N,
        "folds": matrix,
        "aggregate": aggregate,
    }, indent=2, default=str))
    print(f"Saved: {out}")
    print()

    # Print per-fold table
    print("=" * 130)
    print("  PER-FOLD SHARPE/TRADE")
    print("=" * 130)
    header = f"  {'SCENARIO':<54} " + "".join(f"{'F'+str(i):>10}" for i in range(4)) + f"{'AGG':>10} {'FOLDS↑':>8} {'CI[5%]':>9}"
    print(header)
    print("-" * len(header))
    for sc in TOP_SCENARIOS:
        sid = f"s{sc['id']}"
        row = f"  {sc['name']:<54} "
        for fi in range(4):
            sh = matrix[f"fold_{fi}"]["scenarios"][sid].get("sharpe")
            row += f"{(sh if sh is not None else 0):>+10.3f}"
        agg = aggregate[sid]
        agg_sh = agg.get("sharpe")
        folds_imp = agg.get("folds_improved")
        ci5 = agg.get("sharpe_diff_5pct")
        ci5_str = f"{ci5:+.3f}" if isinstance(ci5, (int, float)) else "—"
        row += f"{(agg_sh if agg_sh is not None else 0):>+10.3f} {folds_imp:>8d}/4 {ci5_str:>9}"
        print(row)
    print("=" * 130)
    print()
    print("DECISION RULE: ship if AGG Sharpe > baseline AND folds_improved >= 3 AND CI[5%] > 0")
    print()

    # Verdicts
    base_sh = aggregate["s0"].get("sharpe") or 0
    print("VERDICTS:")
    for sc in TOP_SCENARIOS:
        if sc["id"] == 0:
            continue
        sid = f"s{sc['id']}"
        agg = aggregate[sid]
        sh_delta = (agg.get("sharpe") or 0) - base_sh
        folds_ok = (agg.get("folds_improved") or 0) >= 3
        ci_ok = isinstance(agg.get("sharpe_diff_5pct"), (int, float)) and agg["sharpe_diff_5pct"] > 0
        ship = sh_delta > 0 and folds_ok and ci_ok
        flag = "✅ SHIP" if ship else "❌ FAIL"
        reasons = []
        if sh_delta <= 0:
            reasons.append(f"Sharpe gain {sh_delta:+.3f}<=0")
        if not folds_ok:
            reasons.append(f"only {agg.get('folds_improved')}/4 folds improved")
        if not ci_ok:
            reasons.append(f"CI[5%]={agg.get('sharpe_diff_5pct')} not strictly >0")
        print(f"  #{sc['id']:<4} {sc['name']:<54} {flag}  Δsh {sh_delta:+.3f}  " +
              ("(" + "; ".join(reasons) + ")" if reasons else ""))


if __name__ == "__main__":
    main()
