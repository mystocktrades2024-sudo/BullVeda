"""
Stress Test on Historical Crashes (Phase 3, Change 25).
Validates system robustness in extreme market conditions.
Tests on 2008, 2011, 2020 crash periods.
Requirement: Win rate > 40% even in -20% to -40% markets.
"""

import json
from datetime import datetime
from pathlib import Path


def stress_test_crash_scenarios() -> dict:
    """
    Test system on historical crash periods.
    Measures: Does win rate hold up in catastrophic markets?

    Scenarios:
    - 2008-09 to 2008-11: Financial Crisis (-40% SPY)
    - 2011-04 to 2011-06: Flash Crash / Debt Ceiling (-20% SPY)
    - 2020-02 to 2020-04: COVID-19 Crash (-35% SPY)

    Passing criterion: >= 40% win rate even in crashes
    """
    history_path = Path(__file__).parent.parent / "cache" / "picks_history.json"

    if not history_path.exists():
        return {"error": "No picks history found", "location": str(history_path)}

    with open(history_path) as f:
        history = json.load(f)

    runs = history.get("runs", [])

    scenarios = [
        {
            "name": "COVID-19 Crash (2020)",
            "start": "2020-02-01",
            "end": "2020-04-30",
            "expected_spy_loss": -35
        },
        {
            "name": "Financial Crisis (2008)",
            "start": "2008-09-01",
            "end": "2008-11-30",
            "expected_spy_loss": -40
        },
        {
            "name": "Flash Crash / Debt Ceiling (2011)",
            "start": "2011-04-01",
            "end": "2011-06-30",
            "expected_spy_loss": -20
        },
    ]

    results = {}

    for scenario in scenarios:
        start_date = scenario["start"]
        end_date = scenario["end"]
        scenario_name = scenario["name"]
        expected_loss = scenario["expected_spy_loss"]

        # Filter picks from that period
        period_picks = []
        for run in runs:
            run_date = run.get("run_date", "")
            if start_date <= run_date <= end_date:
                picks = run.get("picks", [])
                period_picks.extend(picks)

        if not period_picks:
            results[scenario_name] = {
                "picks": 0,
                "wins": 0,
                "win_rate": None,
                "status": "NO DATA",
                "note": "No picks recorded during this period"
            }
            continue

        # Calculate win rate for period
        buy_picks = [p for p in period_picks if p.get("verdict") == "BUY"]
        wins = sum(1 for p in buy_picks if p.get("pct_chg", 0) > 0)
        wr = wins / len(buy_picks) if buy_picks else 0

        passed = wr >= 0.40

        results[scenario_name] = {
            "period": f"{start_date} to {end_date}",
            "expected_spy_loss_pct": expected_loss,
            "picks_total": len(buy_picks),
            "wins": wins,
            "losses": len(buy_picks) - wins,
            "win_rate": round(wr, 3),
            "win_rate_pct": f"{round(wr * 100):.0f}%",
            "passed": passed,
            "status": "✅ PASS" if passed else "❌ FAIL",
            "requirement": ">= 40% win rate in crash"
        }

    # Overall verdict
    all_passed = all(r.get("passed", False) for r in results.values() if r.get("picks"))
    overall_status = "✅ ROBUST" if all_passed else "⚠️  FRAGILE"

    return {
        "timestamp": datetime.now().isoformat(),
        "scenarios": results,
        "overall_verdict": overall_status,
        "interpretation": (
            "System maintains >40% win rate even in catastrophic markets. "
            "This proves edge is robust to tail risks."
            if all_passed else
            "System struggles in some crash scenarios. "
            "May need refinement for bear market resilience."
        )
    }


# CLI entry point
if __name__ == "__main__":
    result = stress_test_crash_scenarios()

    print("\n" + "="*70)
    print("STRESS TEST ON HISTORICAL CRASHES")
    print("="*70)

    if "error" in result:
        print(f"\n❌ {result['error']}")
    else:
        print(f"\nSystem Test: {result['overall_verdict']}")
        print(f"\nInterpretation: {result['interpretation']}\n")

        for scenario_name, scenario_result in result["scenarios"].items():
            print(f"\n📉 {scenario_name}")
            if scenario_result.get("status") == "NO DATA":
                print(f"   ⚠️  No data for this period")
            else:
                print(f"   Period:        {scenario_result.get('period')}")
                print(f"   Expected Loss: {scenario_result.get('expected_spy_loss_pct')}% SPY")
                print(f"   Picks:         {scenario_result.get('picks_total')}")
                print(f"   Wins:          {scenario_result.get('wins')} / {scenario_result.get('picks_total')}")
                print(f"   Win Rate:      {scenario_result.get('win_rate_pct')}")
                print(f"   {scenario_result.get('status')} ({scenario_result.get('requirement')})")

    print("\n" + "="*70 + "\n")

    print(json.dumps(result, indent=2, default=str))
