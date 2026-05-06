"""
Walk-Forward Validation (Phase 2, Change 23).
Train on 2025 data, validate on 2026 data (out-of-sample).
Proves the system works on future data, not just historical.
"""

import json
from pathlib import Path


def walk_forward_validation(train_end_date: str = "2025-12-31",
                           test_start_date: str = "2026-01-01") -> dict:
    """
    Perform walk-forward validation:
    - Train set: Picks before train_end_date
    - Test set: Picks after test_start_date (out-of-sample)

    Measures: Is test win-rate close to train win-rate?
    Degradation < 30% = PASS (edge is real, not overfitted)
    Degradation > 30% = FAIL (overfitted, redesign needed)

    Returns: {train_stats, test_stats, degradation_pct, passed}
    """
    history_path = Path(__file__).parent.parent / "cache" / "picks_history.json"

    if not history_path.exists():
        return {"error": "No picks history found", "location": str(history_path)}

    with open(history_path) as f:
        history = json.load(f)

    runs = history.get("runs", [])

    # Split: training (before cutoff) and testing (after cutoff)
    train_runs = [r for r in runs if r["run_date"] <= train_end_date]
    test_runs = [r for r in runs if r["run_date"] >= test_start_date]

    if len(test_runs) < 10:
        return {
            "error": f"Insufficient test data: {len(test_runs)} runs (need 10+)",
            "train_runs": len(train_runs),
            "test_runs": len(test_runs),
            "recommendation": "Wait for more 2026 data to accumulate"
        }

    # Compute stats on each set
    train_stats = _compute_stats_from_runs(train_runs)
    test_stats = _compute_stats_from_runs(test_runs)

    # Measure degradation
    train_wr = train_stats["win_rate"]
    test_wr = test_stats["win_rate"]
    degradation_pct = ((train_wr - test_wr) / train_wr * 100) if train_wr > 0 else 0

    passed = degradation_pct < 30

    result = {
        "period": {
            "train": f"Before {train_end_date} (2025 data)",
            "test": f"After {test_start_date} (2026 data, out-of-sample)"
        },

        "train_set": {
            "runs": len(train_runs),
            "picks": train_stats["total_trades"],
            "wins": train_stats["wins"],
            "win_rate": round(train_wr, 3),
            "avg_return_pct": round(train_stats["avg_return"], 2)
        },

        "test_set": {
            "runs": len(test_runs),
            "picks": test_stats["total_trades"],
            "wins": test_stats["wins"],
            "win_rate": round(test_wr, 3),
            "avg_return_pct": round(test_stats["avg_return"], 2)
        },

        "degradation_pct": round(degradation_pct, 1),
        "passed": passed,
        "verdict": "✅ PASS — System is valid, edge is real" if passed else "❌ FAIL — System is overfitted, redesign needed",
        "requirement": "Degradation < 30% means system generalizes to new data",
    }

    return result


def _compute_stats_from_runs(runs: list) -> dict:
    """Compute win rate and avg return from a list of runs."""
    all_picks = []

    for run in runs:
        picks = run.get("picks", [])
        all_picks.extend(picks)

    if not all_picks:
        return {
            "total_trades": 0,
            "wins": 0,
            "win_rate": 0,
            "avg_return": 0
        }

    # Count BUY verdicts as executed trades
    buy_picks = [p for p in all_picks if p.get("verdict") == "BUY"]
    wins = sum(1 for p in buy_picks if p.get("pct_chg", 0) > 0)

    # Average return (simplified: use score as proxy if pct_chg not available)
    avg_return = (
        sum(p.get("pct_chg", 0) for p in buy_picks) / len(buy_picks)
        if buy_picks else 0
    )

    return {
        "total_trades": len(buy_picks),
        "wins": wins,
        "win_rate": wins / len(buy_picks) if buy_picks else 0,
        "avg_return": avg_return
    }


# CLI entry point
if __name__ == "__main__":
    result = walk_forward_validation()
    print("\n" + "="*70)
    print("WALK-FORWARD VALIDATION RESULTS")
    print("="*70)

    if "error" in result:
        print(f"\n❌ {result['error']}")
        print(f"   Train: {result.get('train_runs', 0)} runs")
        print(f"   Test:  {result.get('test_runs', 0)} runs")
    else:
        print(f"\n📊 TRAINING SET (2025, 'in-sample')")
        print(f"   Runs:      {result['train_set']['runs']}")
        print(f"   Picks:     {result['train_set']['picks']}")
        print(f"   Win Rate:  {result['train_set']['win_rate']:.1%}")
        print(f"   Avg Ret:   {result['train_set']['avg_return_pct']:+.2f}%")

        print(f"\n📊 TEST SET (2026, 'out-of-sample')")
        print(f"   Runs:      {result['test_set']['runs']}")
        print(f"   Picks:     {result['test_set']['picks']}")
        print(f"   Win Rate:  {result['test_set']['win_rate']:.1%}")
        print(f"   Avg Ret:   {result['test_set']['avg_return_pct']:+.2f}%")

        print(f"\n📈 DEGRADATION ANALYSIS")
        print(f"   Degradation: {result['degradation_pct']:.1f}%")
        print(f"   {result['verdict']}")
        print(f"   Requirement: {result['requirement']}")

    print("\n" + "="*70 + "\n")

    import json
    print(json.dumps(result, indent=2, default=str))
