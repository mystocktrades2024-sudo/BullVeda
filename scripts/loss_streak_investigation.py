#!/usr/bin/env python3
"""
loss_streak_investigation.py — find what changed in the last 20 closed BUYs.

The aggregate (n=897) shows Sharpe +0.11 / WR 56% / PF 1.38.
The recent 20 closed BUYs show Sharpe -0.43 / avg pnl -3.27%.
That's a structural divergence. Something changed.

This script answers:
  1. WHICH tickers / dates are in the recent-20 bucket?
  2. WHICH setup_family/regime/entry_quality breakdown?
  3. HOW does it compare to the prior-20 (rolling baseline)?
  4. WHICH exit reasons (target/stop/time/manual)?
  5. ARE certain conditions over-represented vs aggregate?
"""
from __future__ import annotations
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_closed_buys() -> list[dict]:
    """All closed BUY signals with valid pnl, sorted by date ascending."""
    p = REPO / "data" / "signal_log.json"
    if not p.exists():
        return []
    sigs = json.loads(p.read_text())
    rows = []
    for s in sigs:
        if not isinstance(s, dict):
            continue
        if s.get("status") != "CLOSED":
            continue
        if (s.get("verdict") or "").upper() != "BUY":
            continue
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        if abs(pnl) > 100:
            continue
        rows.append({
            "ticker": s.get("ticker"),
            "date": s.get("date") or "",
            "pnl": pnl,
            "regime4": s.get("regime4") or s.get("regime_name") or "unknown",
            "setup": s.get("setup_family") or s.get("strategy") or "unknown",
            "entry_quality": s.get("entry_quality") or "unknown",
            "score": s.get("score"),
            "rs_rank": s.get("rs_rank"),
            "rr": s.get("rr"),
            "stars": s.get("stars"),
            "conviction_label": s.get("conviction_label"),
            "exit_reason": s.get("exit_reason") or "unknown",
            "actual_r_multiple": s.get("actual_r_multiple"),
            "spy_return_over_hold": s.get("spy_return_over_hold"),
            "alpha_vs_spy": s.get("alpha_vs_spy"),
            "vix_at_signal": s.get("vix_at_signal"),
            "mfe_pct": s.get("mfe_pct"),
            "mae_pct": s.get("mae_pct"),
            "win": pnl > 0,
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _stats(grp: list[dict]) -> dict:
    n = len(grp)
    if n == 0:
        return {"n": 0}
    wins = sum(1 for r in grp if r["win"])
    pnl = [r["pnl"] for r in grp]
    avg = statistics.mean(pnl)
    std = statistics.stdev(pnl) if n >= 2 else 0
    return {
        "n": n,
        "wr": wins / n,
        "avg_pnl": round(avg, 3),
        "stdev": round(std, 3),
        "sharpe_per_trade": round(avg / std, 3) if std > 0 else 0,
        "max_loss": round(min(pnl), 2),
        "max_win": round(max(pnl), 2),
    }


def _compare_buckets(recent: list[dict], baseline: list[dict], dim_key: str) -> None:
    """Show how recent-20 distribution differs from baseline aggregate."""
    rcounter = Counter(r[dim_key] for r in recent)
    bcounter = Counter(r[dim_key] for r in baseline)
    n_rec = len(recent); n_bas = len(baseline)
    print(f"  {dim_key:<18}    {'recent20%':>10} {'baseline%':>10} {'over/under':>12}")
    keys = sorted(set(rcounter) | set(bcounter), key=lambda k: -rcounter.get(k, 0))
    for k in keys:
        r_pct = (rcounter.get(k, 0) / n_rec * 100) if n_rec else 0
        b_pct = (bcounter.get(k, 0) / n_bas * 100) if n_bas else 0
        over = r_pct - b_pct
        flag = " ⚠️ over-rep" if over > 15 else (" ⚠️ under-rep" if over < -15 else "")
        print(f"  {str(k)[:18]:<18}    {r_pct:>9.1f}%  {b_pct:>9.1f}%  {over:>+10.1f}pp{flag}")


def main():
    rows = _load_closed_buys()
    if len(rows) < 20:
        print(f"ERROR: only {len(rows)} closed BUYs — need 20 minimum")
        sys.exit(1)
    recent = rows[-20:]
    baseline = rows[:-20]
    n_total = len(rows)

    print(f"Loaded {n_total} closed BUYs from signal_log.json")
    print(f"  recent-20:  {recent[0]['date']} → {recent[-1]['date']}")
    print(f"  baseline:   {baseline[0]['date']} → {baseline[-1]['date']}  (n={len(baseline)})")
    print()

    # ─── Aggregate stats comparison ───
    print("=" * 100)
    print("AGGREGATE COMPARISON")
    print("=" * 100)
    rs = _stats(recent)
    bs = _stats(baseline)
    print(f"  {'metric':<22}  {'recent20':>12s}  {'baseline':>12s}  {'delta':>12s}")
    for k in ["n", "wr", "avg_pnl", "stdev", "sharpe_per_trade", "max_loss", "max_win"]:
        rv = rs.get(k, 0); bv = bs.get(k, 0)
        if isinstance(rv, float) and isinstance(bv, float):
            d = f"{rv - bv:+.3f}"
        else:
            d = "—"
        print(f"  {k:<22}  {str(rv):>12}  {str(bv):>12}  {d:>12}")
    print()

    # ─── Distribution skew analysis ───
    print("=" * 100)
    print("DISTRIBUTION SKEW (recent-20 vs prior-baseline)")
    print("=" * 100)
    print()
    for dim in ["regime4", "setup", "entry_quality", "exit_reason", "conviction_label"]:
        print(f"By {dim}:")
        _compare_buckets(recent, baseline, dim)
        print()

    # ─── The 20 individual losing trades ───
    print("=" * 100)
    print("INDIVIDUAL TRADES (recent-20, sorted by pnl ascending)")
    print("=" * 100)
    recent_sorted = sorted(recent, key=lambda r: r["pnl"])
    print(f"  {'TICKER':<7} {'DATE':<11} {'PNL':>7s} {'R':>6s} {'REGIME':<19} {'SETUP':<22} {'ENTRY':<10} {'EXIT':<14} {'SCORE':>5}")
    for r in recent_sorted:
        rm = r.get("actual_r_multiple")
        rstr = f"{rm:+.2f}" if rm is not None else "—"
        print(f"  {r['ticker']:<7} {r['date'][:10]:<11} {r['pnl']:>+6.1f}% {rstr:>6} "
              f"{r['regime4'][:19]:<19} {r['setup'][:22]:<22} "
              f"{r['entry_quality'][:10]:<10} {r['exit_reason'][:14]:<14} {r.get('score','—'):>5}")
    print()

    # ─── SPY alpha decomposition ───
    print("=" * 100)
    print("ALPHA vs SPY (did the market move against us, or did we lose vs market?)")
    print("=" * 100)
    rec_alpha = [r["alpha_vs_spy"] for r in recent if r.get("alpha_vs_spy") is not None]
    rec_spy_ret = [r["spy_return_over_hold"] for r in recent if r.get("spy_return_over_hold") is not None]
    if rec_alpha:
        avg_alpha = statistics.mean(rec_alpha)
        avg_spy = statistics.mean(rec_spy_ret) if rec_spy_ret else 0
        print(f"  recent-20 avg alpha vs SPY:   {avg_alpha:+.2f}%")
        print(f"  recent-20 avg SPY return:     {avg_spy:+.2f}% during trades")
        print(f"  recent-20 avg pnl:            {rs['avg_pnl']:+.2f}%")
        print()
        if avg_spy < -1.0:
            print("  → SPY moved AGAINST us — losses driven by market environment, not strategy")
        elif avg_spy > 1.0 and rs["avg_pnl"] < 0:
            print("  → SPY was UP but we lost — STRATEGY underperformance vs benchmark")
        else:
            print("  → Mixed environment — neither pure market nor pure strategy")

    # ─── Persist for diff/audit ───
    out = {
        "generated_at": date.today().isoformat(),
        "n_total_closed_buys": n_total,
        "window": {"recent_start": recent[0]['date'], "recent_end": recent[-1]['date']},
        "recent_stats": rs,
        "baseline_stats": bs,
        "recent_trades": recent_sorted,
        "spy_alpha_avg_recent": statistics.mean(rec_alpha) if rec_alpha else None,
        "spy_return_avg_recent": statistics.mean(rec_spy_ret) if rec_spy_ret else None,
    }
    out_p = REPO / "cache" / f"loss_streak_investigation_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print()
    print(f"Saved: {out_p}")


if __name__ == "__main__":
    main()
