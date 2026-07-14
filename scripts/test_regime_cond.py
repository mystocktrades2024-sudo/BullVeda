#!/usr/bin/env python3
"""test_regime_cond.py — where does each setup ACTUALLY work? (principle 5)

Regime-conditional performance decomposition. Principle 5 says strategies work in
some regimes and fail in others; "surface THIS setup in THIS regime, not generic
averages." This script operationalizes that (and the KILL-TO-LABEL idea): for every
(setup_family x regime4) cell it reports n, win-rate, avg return, profit factor and
the Wilson 95% lower bound on WR, then sorts to surface the best and worst cells.

A cell's aggregate stats are inadmissible below n<30 (principle 1 / principle 16 —
"aggregate metrics are meaningless"); such cells are flagged and excluded from the
best/worst leaderboards but still printed for transparency.

KILL-TO-LABEL: rather than blanket-killing a setup, this finds the specific regime
cells where it loses (Wilson LB below the breakeven WR) — the label to condition on.

READ-ONLY. No network, no config / scoring mutation. Local cache only.
Reuses tracker.wilson_ci (the same Wilson helper the live kill-list uses).

Usage:
  python3 scripts/test_regime_cond.py
  python3 scripts/test_regime_cond.py --verdict BUY --min-n 30
  python3 scripts/test_regime_cond.py --verdict ALL --source both --top 8
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
HIST = BASE / "cache" / "picks_history.json"
SIGLOG = BASE / "data" / "signal_log.json"
OUT = BASE / "cache" / "test_regime_cond_result.json"

N30 = 30  # admissibility floor (principle 1)

try:
    from tracker import wilson_ci  # same helper the live kill-list uses
except Exception:
    def wilson_ci(wins: int, total: int, confidence: float = 0.95):
        if total == 0:
            return (0.0, 1.0)
        z = 1.96
        phat = wins / total
        denom = 1 + z * z / total
        center = (phat + z * z / (2 * total)) / denom
        spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
        return (max(0.0, center - spread), min(1.0, center + spread))


# ----------------------------------------------------------------------------- data
def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def load_trades(source: str) -> list[dict]:
    rows: list[dict] = []
    if source in ("picks", "both"):
        d = json.loads(HIST.read_text())
        for t in d.get("trades", []):
            pc = _num(t.get("pct_chg"))
            if pc is None:
                continue
            rows.append({
                "pct_chg": pc,
                "verdict": (t.get("verdict") or "").strip().upper(),
                "setup_family": (t.get("setup_family") or "").strip() or "(unlabelled)",
                "regime4": (t.get("regime4") or "").strip() or "unknown",
            })
    if source in ("signal", "both") and SIGLOG.exists():
        try:
            sd = json.loads(SIGLOG.read_text())
            recs = sd if isinstance(sd, list) else sd.get("signals", sd.get("entries", []))
            for t in recs:
                if not isinstance(t, dict):
                    continue
                pc = _num(t.get("pct_chg", t.get("pnl_pct", t.get("realized_pct"))))
                if pc is None:
                    continue
                rows.append({
                    "pct_chg": pc,
                    "verdict": (t.get("verdict") or t.get("decision") or "").strip().upper(),
                    "setup_family": (t.get("setup_family") or "").strip() or "(unlabelled)",
                    "regime4": (t.get("regime4") or "").strip() or "unknown",
                })
        except Exception:
            pass
    return rows


# ----------------------------------------------------------------------------- cell stats
def cell_stats(returns: list[float]) -> dict:
    n = len(returns)
    wins = sum(1 for r in returns if r > 0)
    wr = wins / n if n else 0.0
    avg = sum(returns) / n if n else 0.0
    gains = sum(r for r in returns if r > 0)
    losses = sum(-r for r in returns if r < 0)
    pf = (gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)
    lo, hi = wilson_ci(wins, n, 0.95)
    # breakeven WR at the cell's realized win/loss asymmetry
    avg_win = (gains / wins) if wins else 0.0
    n_loss = n - wins
    avg_loss = (losses / n_loss) if n_loss else 0.0
    breakeven_wr = avg_loss / (avg_win + avg_loss) if (avg_win + avg_loss) > 0 else None
    return {
        "n": n, "wins": wins, "wr": round(wr, 4),
        "avg_return": round(avg, 4), "pf": round(pf, 4) if pf != float("inf") else None,
        "wilson_lb": round(lo, 4), "wilson_hi": round(hi, 4),
        "avg_win": round(avg_win, 4), "avg_loss": round(avg_loss, 4),
        "breakeven_wr": round(breakeven_wr, 4) if breakeven_wr is not None else None,
        "admissible": n >= N30,
    }


def run(source: str, verdict: str, min_n: int) -> dict:
    trades = load_trades(source)
    if verdict != "ALL":
        trades = [t for t in trades if t["verdict"] == verdict]

    cells = defaultdict(list)
    fam_tot = defaultdict(list)
    reg_tot = defaultdict(list)
    for t in trades:
        cells[(t["setup_family"], t["regime4"])].append(t["pct_chg"])
        fam_tot[t["setup_family"]].append(t["pct_chg"])
        reg_tot[t["regime4"]].append(t["pct_chg"])

    cell_rows = []
    for (fam, reg), rets in cells.items():
        s = cell_stats(rets)
        s.update({"setup_family": fam, "regime4": reg})
        # kill-to-label flag: admissible AND Wilson LB below breakeven (edge fails)
        be = s["breakeven_wr"]
        s["kill_label"] = bool(s["admissible"] and be is not None and s["wilson_lb"] < be)
        cell_rows.append(s)

    admissible = [c for c in cell_rows if c["admissible"]]
    best = sorted(admissible, key=lambda c: c["wilson_lb"], reverse=True)
    worst = sorted(admissible, key=lambda c: c["wilson_lb"])

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": source, "verdict_filter": verdict, "min_n": min_n,
        "n_trades": len(trades), "n_cells": len(cell_rows),
        "n_cells_admissible": len(admissible),
        "cells": sorted(cell_rows, key=lambda c: (c["setup_family"], c["regime4"])),
        "family_marginals": {f: cell_stats(r) for f, r in fam_tot.items()},
        "regime_marginals": {r: cell_stats(v) for r, v in reg_tot.items()},
        "best_cells": best[:12],
        "worst_cells": worst[:12],
        "kill_labels": [c for c in cell_rows if c["kill_label"]],
    }


# ----------------------------------------------------------------------------- render
def _pf(v):
    return "  inf" if v is None else f"{v:6.2f}"


def _cellline(c):
    flag = "" if c["admissible"] else "  ⚠n<30"
    kl = "  ☠KILL" if c.get("kill_label") else ""
    return (f"    {c['setup_family'][:22]:<23}{c['regime4'][:18]:<19}"
            f"{c['n']:>5}{c['wr']*100:>6.0f}%{c['avg_return']:>+8.2f}%"
            f"{_pf(c['pf'])}{c['wilson_lb']*100:>7.0f}%{flag}{kl}")


def print_report(r: dict):
    W = 92
    print("=" * W)
    print("  REGIME-CONDITIONAL PERFORMANCE DECOMPOSITION  (setup_family x regime4)")
    print(f"  source={r['source']}  verdict={r['verdict_filter']}  "
          f"trades={r['n_trades']}  cells={r['n_cells']} "
          f"({r['n_cells_admissible']} admissible n>={N30})")
    print("=" * W)
    hdr = (f"    {'setup_family':<23}{'regime4':<19}{'n':>5}{'WR':>7}"
           f"{'avgRet':>9}{'PF':>7}{'WilsLB':>8}")
    print("  ALL CELLS (sorted by setup, then regime)")
    print(hdr)
    for c in r["cells"]:
        print(_cellline(c))
    print("-" * W)
    print("  BEST CELLS (admissible, by Wilson LB) — where setups actually work")
    print(hdr)
    for c in r["best_cells"][:8]:
        print(_cellline(c))
    print("-" * W)
    print("  WORST CELLS (admissible, by Wilson LB) — KILL-TO-LABEL candidates")
    print(hdr)
    for c in r["worst_cells"][:8]:
        print(_cellline(c))
    print("-" * W)
    kl = r["kill_labels"]
    if kl:
        print(f"  ☠ KILL-TO-LABEL: {len(kl)} admissible cell(s) where Wilson LB < breakeven WR")
        print(f"    (condition the setup OUT of these regimes rather than killing it outright)")
        for c in kl:
            print(f"      {c['setup_family']} x {c['regime4']}: "
                  f"n={c['n']} WR {c['wr']*100:.0f}% WilsLB {c['wilson_lb']*100:.0f}% "
                  f"< breakeven {c['breakeven_wr']*100:.0f}%  PF {_pf(c['pf']).strip()}")
    else:
        print("  ☠ KILL-TO-LABEL: no admissible cell has Wilson LB below its breakeven WR.")
    print("-" * W)
    n_bad = r["n_cells"] - r["n_cells_admissible"]
    if n_bad:
        print(f"  ⚠  {n_bad} cell(s) below n<{N30} — non-admissible, excluded from "
              f"best/worst (principle 1).")
    print(f"  JSON: {OUT}")
    print("=" * W)


def main():
    ap = argparse.ArgumentParser(description="Regime-conditional (setup x regime4) decomposition (read-only).")
    ap.add_argument("--source", choices=["picks", "signal", "both"], default="picks")
    ap.add_argument("--verdict", default="BUY",
                    help="filter to this verdict, or ALL (default BUY)")
    ap.add_argument("--min-n", type=int, default=N30, help="admissibility floor (default 30)")
    ap.add_argument("--top", type=int, default=8, help="rows in best/worst tables")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    r = run(args.source, args.verdict.upper(), args.min_n)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2))
    if not args.json_only:
        r["best_cells"] = r["best_cells"][:args.top]
        r["worst_cells"] = r["worst_cells"][:args.top]
        print_report(r)


if __name__ == "__main__":
    main()
