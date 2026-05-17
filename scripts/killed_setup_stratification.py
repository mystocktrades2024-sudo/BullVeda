#!/usr/bin/env python3
"""
killed_setup_stratification.py — find profitable sub-segments within killed setups.

The setup_score_multiplier kills 52wk Breakout (n=114, WR 31.6%, avg -0.62%)
and EMA21 Pullback (n=59, WR 11.9%, avg -2.10%). Aggregate evidence is
overwhelmingly negative.

But the kill could be over-broad. Maybe a sub-segment within those n=114
trades was actually profitable (e.g., high-RS-rank 52wk breakouts).

This script stratifies the killed-setup historical trades by:
  - score band
  - rs_rank band
  - regime4
  - entry_quality
  - has tier-1 catalyst

If ANY sub-segment shows n>=15, WR>50%, PF>1.2 — that's an actionable
exemption. Otherwise the kill is correct as a blanket rule.

Usage: python3 scripts/killed_setup_stratification.py
"""
from __future__ import annotations
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _wlb(wins, n, z=1.96):
    if n == 0: return 0
    p = wins / n
    return (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


def _stats(grp):
    n = len(grp)
    if n == 0: return None
    wins = sum(1 for r in grp if r["pnl"] > 0)
    pnl = [r["pnl"] for r in grp]
    avg = statistics.mean(pnl)
    pf_w = sum(p for p in pnl if p > 0)
    pf_l = abs(sum(p for p in pnl if p <= 0)) or 1
    return {
        "n": n, "wins": wins, "wr": wins/n,
        "wlb": _wlb(wins, n),
        "avg": round(avg, 2),
        "pf": round(pf_w / pf_l, 3),
    }


def _load(target_setups: set):
    """Load closed trades matching target setup_types from both data sources."""
    rows = []
    # picks_history
    try:
        ph = json.loads((REPO / "cache" / "picks_history.json").read_text())
        for t in ph.get("trades") or []:
            if t.get("pct_chg") is None: continue
            pnl = float(t["pct_chg"])
            if abs(pnl) > 100: continue
            family = t.get("setup_family") or ""
            tp = t.get("trade_plan") or {}
            setup = tp.get("setup_type") or family
            if setup not in target_setups and family not in target_setups: continue
            rows.append({
                "src": "picks_history",
                "ticker": t.get("ticker"),
                "pnl": pnl,
                "setup": setup,
                "family": family,
                "score": t.get("score"),
                "rs_rank": t.get("rs_rank"),
                "regime4": t.get("regime4") or "unknown",
                "entry_quality": t.get("entry_quality") or "unknown",
                "catalyst_tier": t.get("catalyst_tier"),
            })
    except Exception as e:
        print(f"picks_history read fail: {e}")
    # signal_log
    try:
        sl = json.loads((REPO / "data" / "signal_log.json").read_text())
        for s in sl:
            if s.get("status") != "CLOSED": continue
            if (s.get("verdict") or "").upper() != "BUY": continue
            pnl = s.get("actual_pnl_pct")
            if pnl is None: continue
            pnl = float(pnl)
            if abs(pnl) > 100: continue
            setup = s.get("strategy") or s.get("setup_family") or ""
            family = s.get("setup_family") or ""
            if setup not in target_setups and family not in target_setups: continue
            rows.append({
                "src": "signal_log",
                "ticker": s.get("ticker"),
                "pnl": pnl,
                "setup": setup,
                "family": family,
                "score": s.get("score"),
                "rs_rank": s.get("rs_rank"),
                "regime4": s.get("regime4") or "unknown",
                "entry_quality": s.get("entry_quality") or "unknown",
                "catalyst_tier": s.get("catalyst_tier"),
            })
    except Exception as e:
        print(f"signal_log read fail: {e}")
    return rows


def _stratify(rows: list, dim: str, dim_fn=None):
    """Group by a dimension, compute stats per group."""
    by = defaultdict(list)
    for r in rows:
        key = dim_fn(r) if dim_fn else r.get(dim, "unknown")
        by[key].append(r)
    out = []
    for k, grp in by.items():
        s = _stats(grp)
        if s:
            s["group"] = str(k)
            out.append(s)
    out.sort(key=lambda x: -x["n"])
    return out


def _print_strat(label, results):
    print(f"  By {label}:")
    print(f"    {'group':<20} {'n':>4s} {'WR':>6s} {'WLB':>6s} {'avg':>8s} {'PF':>6s}  exemption?")
    for r in results:
        ex = ""
        if r["n"] >= 15 and r["wr"] >= 0.50 and r["pf"] >= 1.2 and r["avg"] > 0:
            ex = " ✅ POTENTIAL EXEMPTION"
        elif r["n"] >= 15 and r["pf"] >= 1.0:
            ex = " 🟡 break-even — investigate"
        elif r["n"] < 15:
            ex = " (n<15 noise)"
        print(f"    {r['group'][:20]:<20} {r['n']:>4d} {r['wr']*100:>5.1f}% {r['wlb']*100:>5.1f}% {r['avg']:>+7.2f}% {r['pf']:>5.2f}{ex}")
    print()


def main():
    targets = {"52wk Breakout", "EMA21 Pullback"}
    rows = _load(targets)
    if not rows:
        print("No matching trades found")
        return

    # By raw setup_type
    by_setup = defaultdict(list)
    for r in rows: by_setup[r["setup"]].append(r)

    print(f"Loaded {len(rows)} closed trades in killed setups")
    print()

    for setup in ("52wk Breakout", "EMA21 Pullback"):
        grp = by_setup.get(setup) or []
        if len(grp) < 5:
            print(f"=== {setup} — only {len(grp)} trades, skipping ===\n")
            continue
        agg = _stats(grp)
        print(f"=" * 90)
        print(f"{setup} — AGGREGATE: n={agg['n']} WR={agg['wr']*100:.1f}% WLB={agg['wlb']*100:.1f}% avg={agg['avg']:+.2f}% PF={agg['pf']:.2f}")
        print(f"=" * 90)

        # Score band
        def _scb(r):
            sc = r.get("score") or 0
            if sc >= 80: return "80+"
            if sc >= 70: return "70-79"
            if sc >= 60: return "60-69"
            if sc >= 50: return "50-59"
            return "<50"
        _print_strat("score band", _stratify(grp, "score", _scb))

        # RS band
        def _rsb(r):
            rs = r.get("rs_rank") or 0
            if rs >= 90: return "90+"
            if rs >= 80: return "80-89"
            if rs >= 70: return "70-79"
            if rs >= 60: return "60-69"
            return "<60"
        _print_strat("rs_rank band", _stratify(grp, "rs_rank", _rsb))

        # Regime
        _print_strat("regime4", _stratify(grp, "regime4"))

        # Entry quality
        _print_strat("entry_quality", _stratify(grp, "entry_quality"))

        # Catalyst tier
        def _cat(r):
            ct = r.get("catalyst_tier")
            return "T1" if ct == 1 else "T2" if ct == 2 else "T3+" if ct else "—"
        _print_strat("catalyst_tier", _stratify(grp, "catalyst_tier", _cat))

        # Score × RS combined
        def _combo(r):
            sc = r.get("score") or 0
            rs = r.get("rs_rank") or 0
            if sc >= 75 and rs >= 80: return "high-score + high-RS"
            if sc >= 75: return "high-score"
            if rs >= 80: return "high-RS"
            return "neither-high"
        _print_strat("composite (score≥75 ∧ RS≥80)", _stratify(grp, None, _combo))

        print()


if __name__ == "__main__":
    main()
