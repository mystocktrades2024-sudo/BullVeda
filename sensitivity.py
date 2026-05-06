"""
Parameter Sensitivity Testing — SwingTrade
==========================================
Sweeps score/RR thresholds against historical trades and prints a ranked table
showing which threshold combinations maximise win rate and profit factor.

Usage:
    cd SwingTrade && python3 sensitivity.py

No arguments needed — reads cache/picks_history.json automatically.
Writes results to cache/sensitivity_report.txt and prints to stdout.
"""

from __future__ import annotations

import json
import itertools
from pathlib import Path

BASE_DIR = Path(__file__).parent
HISTORY_FILE = BASE_DIR / "cache" / "picks_history.json"
REPORT_FILE  = BASE_DIR / "cache" / "sensitivity_report.txt"


def load_trades() -> list[dict]:
    """Load completed (evaluated) trades from picks history."""
    if not HISTORY_FILE.exists():
        print("No history file found — run a daily scan first.")
        return []
    raw = json.loads(HISTORY_FILE.read_text())
    trades = raw.get("trades", [])
    # Also pull evaluated picks from runs
    for run in raw.get("runs", []):
        if run.get("evaluated"):
            for pick in run.get("picks", []):
                if "pct_chg" in pick and pick not in trades:
                    trades.append(pick)
    return trades


def compute_metrics(trades: list[dict],
                    min_score: float,
                    min_rr: float,
                    direction: str = "all") -> dict:
    """Filter trades by threshold and compute win rate + profit factor.
    rr_ratio may be absent from older records — default to 3.0 (system minimum)."""
    filtered = [t for t in trades
                if t.get("score", 0) >= min_score
                and t.get("rr_ratio", 3.0) >= min_rr  # assume 3:1 if missing
                and (direction == "all" or t.get("direction", "long") == direction)]

    if not filtered:
        return {"n": 0, "win_rate": 0, "profit_factor": 0, "avg_return": 0}

    wins  = [t for t in filtered if t.get("win", False)]
    loses = [t for t in filtered if not t.get("win", False)]

    win_sum  = sum(abs(t.get("pct_chg", 0)) for t in wins)
    loss_sum = sum(abs(t.get("pct_chg", 0)) for t in loses)
    total_return = sum(t.get("pct_chg", 0) for t in filtered)

    pf = round(win_sum / loss_sum, 2) if loss_sum > 0 else (99.0 if win_sum > 0 else 0.0)

    return {
        "n":             len(filtered),
        "win_rate":      round(len(wins) / len(filtered) * 100, 1),
        "profit_factor": pf,
        "avg_return":    round(total_return / len(filtered), 2),
    }


def run_sweep(trades: list[dict]) -> list[dict]:
    """Sweep all threshold combinations and return sorted results."""
    score_values = [40, 45, 50, 55, 60, 65, 70, 75]
    rr_values    = [2.0, 2.5, 3.0, 3.5, 4.0]
    directions   = ["all", "long", "short"]

    results = []
    for min_score, min_rr, direction in itertools.product(score_values, rr_values, directions):
        m = compute_metrics(trades, min_score, min_rr, direction)
        if m["n"] < 2:  # skip combos with too few trades to be meaningful
            continue
        results.append({
            "min_score": min_score,
            "min_rr":    min_rr,
            "direction": direction,
            **m,
        })

    # Sort: profit_factor desc, then win_rate desc
    results.sort(key=lambda x: (-x["profit_factor"], -x["win_rate"]))
    return results


def format_table(results: list[dict], top_n: int = 20) -> str:
    lines = [
        "=" * 75,
        f"  PARAMETER SENSITIVITY REPORT  ({len(results)} combos with n>=3 trades)",
        "=" * 75,
        f"  {'Score':>6}  {'R:R':>4}  {'Dir':>6}  {'N':>4}  {'WinRate':>8}  {'PF':>6}  {'AvgRet%':>8}",
        "-" * 75,
    ]
    for r in results[:top_n]:
        lines.append(
            f"  {r['min_score']:>6}  {r['min_rr']:>4.1f}  {r['direction']:>6}  "
            f"{r['n']:>4}  {r['win_rate']:>7.1f}%  {r['profit_factor']:>6.2f}  {r['avg_return']:>+7.2f}%"
        )
    lines.append("=" * 75)
    lines.append("  PF = Profit Factor (gross wins / gross losses). Target: > 1.5")
    lines.append("  WinRate target: > 55% for swing trading")
    lines.append("")
    lines.append("  RECOMMENDED SETTINGS (top result):")
    if results:
        r = results[0]
        lines.append(f"    min_score = {r['min_score']}  min_rr = {r['min_rr']}  direction = {r['direction']}")
        lines.append(f"    → WinRate {r['win_rate']}%, PF {r['profit_factor']}, AvgRet {r['avg_return']:+.2f}%, N={r['n']}")
    lines.append("=" * 75)
    return "\n".join(lines)


def main():
    trades = load_trades()
    if not trades:
        print("No completed trades found in history. Run more scans and let picks mature.")
        return

    print(f"\nLoaded {len(trades)} completed trades from history.\n")

    # Overall stats at current defaults (score>=75, rr>=3)
    current = compute_metrics(trades, min_score=75, min_rr=3.0)
    print(f"Current config (score≥75, R:R≥3): {current}")

    results = run_sweep(trades)
    report  = format_table(results)
    print(report)

    REPORT_FILE.write_text(report)
    print(f"\nFull report saved to: {REPORT_FILE}")

    # Insight: score distribution of wins vs losses
    if trades:
        wins  = [t["score"] for t in trades if t.get("win")]
        loses = [t["score"] for t in trades if not t.get("win")]
        if wins:
            print(f"\nWinner score avg:  {sum(wins)/len(wins):.1f}  (n={len(wins)})")
        if loses:
            print(f"Loser  score avg:  {sum(loses)/len(loses):.1f}  (n={len(loses)})")


if __name__ == "__main__":
    main()
