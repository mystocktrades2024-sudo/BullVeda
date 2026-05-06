"""Quick parameter sweep on cached Stage 2 backtest picks.

Uses cache/backtest_results.json (1110 precomputed picks) to sweep filter
thresholds. Ranks by PF * sqrt(N) * (1 - maxDD_pct), writes top-20 CSV.

No re-simulation — uses the r5d return + win flag already in each pick.
For stop/target sweeps, use the full signal cache (Task #2) instead.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "cache" / "backtest_results.json"
OUT_CSV = ROOT / "cache" / "param_sweep_quick.csv"


def metrics(trades: list[dict]) -> dict:
    n = len(trades)
    if n < 10:
        return {"n": n, "wr": 0, "pf": 0, "avg_ret": 0, "max_dd": 1, "score": 0}
    wins = [t["r5d"] for t in trades if t["r5d"] > 0]
    losses = [t["r5d"] for t in trades if t["r5d"] <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else 0
    wr = len(wins) / n
    avg_ret = sum(t["r5d"] for t in trades) / n

    # Equity curve for max DD (chronological)
    chron = sorted(trades, key=lambda t: t["as_of_date"])
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in chron:
        equity *= 1 + (t["r5d"] / 100)
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)

    # Ranking: reward PF, sample size, penalize DD
    rank_score = pf * math.sqrt(n) * max(0, 1 - max_dd)

    return {
        "n": n,
        "wr": round(wr * 100, 1),
        "pf": round(pf, 2),
        "avg_ret": round(avg_ret, 2),
        "max_dd": round(max_dd * 100, 1),
        "score": round(rank_score, 2),
    }


def filter_picks(picks, cfg):
    out = []
    for p in picks:
        if p.get("r5d") is None:
            continue
        if p["score"] < cfg["min_score"]:
            continue
        if p["rs_rank"] < cfg["min_rs"]:
            continue
        if cfg["require_gate"] and not p.get("gate_passed"):
            continue
        if cfg["require_weekly_bull"] and not p.get("weekly_bull"):
            continue
        if cfg["setups"] != "all" and p["setup_type"] not in cfg["setups"]:
            continue
        if cfg["regimes"] != "all" and p["regime"] not in cfg["regimes"]:
            continue
        if cfg["min_rr"] > 0 and (p.get("rr_ratio") or 0) < cfg["min_rr"]:
            continue
        out.append(p)
    return out


def main():
    with open(RESULTS) as f:
        data = json.load(f)
    picks = data["picks"]
    print(f"Loaded {len(picks)} picks from Stage 2 backtest")

    # Setups ranked best→worst from Stage 2 results
    all_setups = sorted({p["setup_type"] for p in picks})
    top_setups = ["Near-VCP Breakout", "Squeeze Expansion", "VCP Breakout", "Pocket Pivot"]
    top3 = ["Near-VCP Breakout", "Squeeze Expansion", "VCP Breakout"]

    grid = {
        "min_score": [50, 55, 60, 65, 70, 75],
        "min_rs": [60, 70, 80, 90],
        "require_gate": [True],
        "require_weekly_bull": [False, True],
        "min_rr": [0, 2.5],
        "setups": [tuple(all_setups), tuple(top_setups), tuple(top3)],
        "regimes": [("bull", "bear", "neutral"), ("bear", "neutral")],
    }
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"Testing {len(combos)} parameter combinations...")

    results = []
    for vals in combos:
        cfg = dict(zip(keys, vals))
        cfg["setups"] = list(cfg["setups"]) if cfg["setups"] != "all" else "all"
        cfg["regimes"] = list(cfg["regimes"])
        trades = filter_picks(picks, cfg)
        m = metrics(trades)
        if m["n"] < 30:  # sample size floor
            continue
        results.append({**cfg, **m})

    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:20]

    # Baseline: current production config (min_score 55, min_rs 70, all, all)
    base_cfg = {
        "min_score": 55, "min_rs": 70, "require_gate": True,
        "require_weekly_bull": False, "min_rr": 0,
        "setups": "all", "regimes": ["bull", "bear", "neutral"],
    }
    base = metrics(filter_picks(picks, base_cfg))

    # Write CSV
    fields = ["rank", "min_score", "min_rs", "require_weekly_bull", "min_rr",
              "setups", "regimes", "n", "wr", "pf", "avg_ret", "max_dd", "score"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(top, 1):
            w.writerow({
                "rank": i,
                "min_score": r["min_score"],
                "min_rs": r["min_rs"],
                "require_weekly_bull": r["require_weekly_bull"],
                "min_rr": r["min_rr"],
                "setups": ",".join(r["setups"]) if r["setups"] != "all" else "all",
                "regimes": ",".join(r["regimes"]),
                "n": r["n"], "wr": r["wr"], "pf": r["pf"],
                "avg_ret": r["avg_ret"], "max_dd": r["max_dd"], "score": r["score"],
            })

    print(f"\nBaseline (current prod): N={base['n']} WR={base['wr']}% PF={base['pf']} DD={base['max_dd']}% avg_ret={base['avg_ret']}%")
    print(f"\nTop 10 of {len(results)} valid combos (N≥30):")
    print(f"{'#':<3}{'score':<6}{'rs':<5}{'wkly':<6}{'rr':<5}{'setups':<10}{'regimes':<18}{'N':<5}{'WR':<6}{'PF':<5}{'DD':<6}{'rank':<6}")
    for i, r in enumerate(top[:10], 1):
        setups_short = "all" if r["setups"] == "all" else f"top{len(r['setups'])}"
        regimes_short = ",".join(r["regimes"])[:16]
        print(f"{i:<3}{r['min_score']:<6}{r['min_rs']:<5}{str(r['require_weekly_bull'])[:1]:<6}{r['min_rr']:<5}{setups_short:<10}{regimes_short:<18}{r['n']:<5}{r['wr']:<6}{r['pf']:<5}{r['max_dd']:<6}{r['score']:<6}")

    print(f"\nFull top-20 saved to {OUT_CSV}")


if __name__ == "__main__":
    main()
