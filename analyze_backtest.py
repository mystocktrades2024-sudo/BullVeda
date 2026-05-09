#!/usr/bin/env python3
"""
analyze_backtest.py — turn backtest output into actionable improvements.

Reads cache/backtest_results.json (or stdout/log) and emits:
  1. Per-setup performance ranking (which setups to keep/kill)
  2. Per-score-band WR (validates whether 80+ threshold holds up)
  3. Per-regime conditional WR (does each setup work in each regime?)
  4. Hold-day sensitivity (5d/7d/10d/15d returns)
  5. Top 5 RECOMMENDED CHANGES based on the data

Output: cache/backtest_analysis_<date>.txt (and prints to stdout).

Usage:
  python3 analyze_backtest.py
  python3 analyze_backtest.py --top-n 10
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load_picks() -> list[dict]:
    """Find backtest output. Tries multiple paths."""
    candidates = [
        BASE / "cache" / "backtest_results.json",
        BASE / "cache" / "portfolio_backtest_results.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                d = json.loads(p.read_text())
                if isinstance(d, list): return d
                if isinstance(d, dict):
                    return d.get("trades") or d.get("picks") or []
            except Exception:
                continue
    return []


def _summarize_group(items: list[dict], group_key: str | None = None,
                      ret_key: str = "r5d") -> list[dict]:
    """Bucket by group_key, compute WR + avg-R + n."""
    buckets = defaultdict(list)
    for x in items:
        if group_key:
            k = x.get(group_key) or "unknown"
        else:
            k = "ALL"
        ret = x.get(ret_key)
        if ret is None: continue
        buckets[k].append(ret)
    rows = []
    for k, rets in buckets.items():
        if not rets: continue
        wins = sum(1 for r in rets if r > 0)
        losses = sum(1 for r in rets if r < 0)
        avg = sum(rets) / len(rets)
        wr = wins / len(rets) * 100
        rows.append({
            "group": k, "n": len(rets), "wins": wins, "losses": losses,
            "wr": round(wr, 1), "avg_pct": round(avg, 2),
            "best": round(max(rets), 2), "worst": round(min(rets), 2),
        })
    return sorted(rows, key=lambda r: -r["n"])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top-n", type=int, default=5)
    args = p.parse_args()

    picks = _load_picks()
    if not picks:
        print("✗ No backtest results found. Run backtest.py first:")
        print("    python3 backtest.py --portfolio --days 252 --hold 7 --min-score 35 ...")
        return 1

    print("=" * 76)
    print(f" BACKTEST ANALYSIS — {len(picks)} trades")
    print("=" * 76)

    # 1. Overall
    print("\n[1] OVERALL")
    overall = _summarize_group(picks)
    if overall:
        o = overall[0]
        print(f"  Trades: {o['n']}  ·  WR: {o['wr']}%  ·  avg P&L: {o['avg_pct']}%  ·  best: {o['best']}%  ·  worst: {o['worst']}%")

    # 2. By setup
    print("\n[2] BY SETUP — keep / fix / kill list")
    by_setup = _summarize_group(picks, "strategy")
    print(f"  {'SETUP':<28} {'N':>5} {'WR%':>6} {'avgP%':>7} {'BEST%':>7} {'WORST%':>8}")
    for r in by_setup:
        keep_kill = "✓" if r["wr"] >= 50 and r["avg_pct"] > 0 else \
                    "⚠" if r["avg_pct"] > 0 or r["wr"] >= 40 else "✗"
        print(f"  {keep_kill} {r['group'][:26]:<26} {r['n']:>5} {r['wr']:>6} {r['avg_pct']:>7} {r['best']:>7} {r['worst']:>8}")

    # 3. By score band
    print("\n[3] BY SCORE BAND — validates the 80+ threshold")
    bands = []
    for x in picks:
        sc = x.get("score") or 0
        if   sc >= 90: band = "90-100"
        elif sc >= 80: band = "80-89"
        elif sc >= 70: band = "70-79"
        elif sc >= 60: band = "60-69"
        elif sc >= 50: band = "50-59"
        elif sc >= 40: band = "40-49"
        elif sc >= 35: band = "35-39"
        else:          band = "<35"
        bands.append({**x, "_band": band})
    by_band = _summarize_group(bands, "_band")
    by_band.sort(key=lambda r: r["group"])
    print(f"  {'BAND':<10} {'N':>5} {'WR%':>6} {'avgP%':>7}")
    for r in by_band:
        flag = "✓" if r["wr"] >= 55 else "⚠" if r["wr"] >= 40 else "✗"
        print(f"  {flag} {r['group']:<8} {r['n']:>5} {r['wr']:>6} {r['avg_pct']:>7}")

    # 4. By regime
    print("\n[4] BY REGIME — conditional performance")
    by_reg = _summarize_group(picks, "regime")
    for r in by_reg:
        print(f"  {r['group']:<24} n={r['n']:>4}  WR={r['wr']}%  avgP={r['avg_pct']}%")

    # 5. By verdict (BUY vs WATCH historically promoted)
    print("\n[5] BY VERDICT")
    for r in _summarize_group(picks, "verdict"):
        print(f"  {r['group']:<10} n={r['n']:>4}  WR={r['wr']}%  avgP={r['avg_pct']}%")

    # 6. RECOMMENDATIONS
    print("\n[6] TOP RECOMMENDED CHANGES")
    recs = []
    # 6a. Setups to kill (negative avg with significant n)
    for r in by_setup:
        if r["avg_pct"] < -0.5 and r["n"] >= 20:
            recs.append({
                "priority": "HIGH",
                "rec": f"KILL setup '{r['group']}' — {r['n']} trades, avg {r['avg_pct']}%, WR {r['wr']}%",
                "impact": f"saves {r['n']} bad trades over 252d",
            })
    # 6b. Score bands that lose money
    bad_bands = [r for r in by_band if r["wr"] < 40 and r["n"] >= 30]
    for r in bad_bands:
        recs.append({
            "priority": "HIGH",
            "rec": f"RAISE threshold above {r['group'].split('-')[1] if '-' in r['group'] else r['group']} — {r['n']} trades at WR {r['wr']}%",
            "impact": f"removes {r['n']} negative-expectancy signals",
        })
    # 6c. Score bands that work great
    good_bands = [r for r in by_band if r["wr"] >= 60 and r["n"] >= 15]
    for r in good_bands:
        recs.append({
            "priority": "MEDIUM",
            "rec": f"PRIORITIZE {r['group']} band — {r['n']} trades at WR {r['wr']}% (alpha here)",
            "impact": f"size up trades scoring in this band",
        })
    # 6d. Regimes that fail
    for r in by_reg:
        if r["avg_pct"] < -0.5 and r["n"] >= 15:
            recs.append({
                "priority": "MEDIUM",
                "rec": f"REDUCE size in {r['group']} regime — n={r['n']}, avg {r['avg_pct']}%",
                "impact": f"avoid grinding losses in this regime",
            })
    if not recs:
        print("  No strong signals from this run — try longer window or more setups.")
    else:
        for i, r in enumerate(recs[:args.top_n], 1):
            print(f"  {i}. [{r['priority']}] {r['rec']}")
            print(f"     → {r['impact']}")

    # Save
    out = BASE / "cache" / f"backtest_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "n_trades": len(picks),
        "by_setup": by_setup,
        "by_band":  by_band,
        "by_regime": by_reg,
        "recommendations": recs,
    }, indent=2, default=str))
    print(f"\n  Full analysis saved: {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
