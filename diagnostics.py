"""
Diagnostics and analytics for SwingTrade (Phase 2, Change 22).
Win-rate analysis by setup type, regime, score decile.
Helps understand which strategies actually work.
"""

from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
from collections import defaultdict
from typing import Optional


def generate_diagnostics_report(config: Optional[dict] = None) -> dict:
    """
    Generate comprehensive win-rate analysis.
    Breaks down performance by: setup type, regime, score decile.
    """
    history_path = Path(__file__).parent / "cache" / "picks_history.json"

    if not history_path.exists():
        return {"error": "No picks history found", "location": str(history_path)}

    with open(history_path) as f:
        history = json.load(f)

    trades = history.get("trades", [])

    if not trades:
        return {"error": "No completed trades to analyze", "total_trades": 0, "note": "Run screener first to generate trade history"}

    df = pd.DataFrame(trades)

    # Check if required columns exist
    required_cols = ["setup_type", "regime", "score", "win", "pct_chg"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return {"error": f"Missing columns in trade data: {missing}", "available_columns": list(df.columns)}

    report = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "total_trades": len(trades),
        "wins": sum(df["win"]),
        "losses": sum(~df["win"]),
        "overall_win_rate": round(sum(df["win"]) / len(df), 3) if len(df) > 0 else 0,
        "avg_return_pct": round(df["pct_chg"].mean(), 2),
        "profit_factor": _calc_profit_factor(df),

        "win_rate_by_setup": _breakdown_by_column(df, "setup_type"),
        "win_rate_by_regime": _breakdown_by_column(df, "regime"),
        "win_rate_by_score_decile": _breakdown_by_score_decile(df),

        "best_setups": _top_performers(df, "setup_type", n=3),
        "worst_setups": _worst_performers(df, "setup_type", n=3),

        "best_setup_regime_combos": _best_combos(df, n=5),
        "worst_setup_regime_combos": _worst_combos(df, n=5),
    }

    return report


def _breakdown_by_column(df: pd.DataFrame, column: str) -> dict[str, dict]:
    """Win rate breakdown by column value."""
    result = {}

    for val in df[column].unique():
        if pd.isna(val):
            continue

        subset = df[df[column] == val]
        wins = sum(subset["win"])
        total = len(subset)
        wr = wins / total if total > 0 else 0

        result[str(val)] = {
            "trades": total,
            "wins": wins,
            "win_rate": round(wr, 3),
            "avg_return": round(subset["pct_chg"].mean(), 2),
            "profit_factor": _calc_profit_factor(subset)
        }

    return result


def _breakdown_by_score_decile(df: pd.DataFrame) -> dict[str, dict]:
    """Win rate by score decile (0-10, 10-20, ..., 90-100)."""
    result = {}

    df_copy = df.copy()
    df_copy["score_decile"] = pd.cut(
        df_copy["score"],
        bins=10,
        labels=[f"{i*10}-{(i+1)*10}" for i in range(10)]
    )

    for decile in sorted(df_copy["score_decile"].unique()):
        if pd.isna(decile):
            continue

        subset = df_copy[df_copy["score_decile"] == decile]
        wins = sum(subset["win"])
        total = len(subset)
        wr = wins / total if total > 0 else 0

        result[str(decile)] = {
            "trades": total,
            "wins": wins,
            "win_rate": round(wr, 3),
            "avg_return": round(subset["pct_chg"].mean(), 2)
        }

    return result


def _top_performers(df: pd.DataFrame, column: str, n: int = 3) -> list:
    """Top N performing setups by win rate."""
    breakdown = _breakdown_by_column(df, column)

    sorted_items = sorted(
        breakdown.items(),
        key=lambda x: (x[1]["trades"], x[1]["win_rate"]),
        reverse=True
    )

    return [
        {"name": k, **v}
        for k, v in sorted_items[:n]
        if v["trades"] >= 3  # minimum 3 trades
    ]


def _worst_performers(df: pd.DataFrame, column: str, n: int = 3) -> list:
    """Worst N performing setups by win rate."""
    breakdown = _breakdown_by_column(df, column)

    sorted_items = sorted(
        breakdown.items(),
        key=lambda x: x[1]["win_rate"]
    )

    return [
        {"name": k, **v}
        for k, v in sorted_items[:n]
        if v["trades"] >= 3  # minimum 3 trades
    ]


def _best_combos(df: pd.DataFrame, n: int = 5) -> list:
    """Best setup+regime combinations by win rate (min 3 trades)."""
    if df.empty or "setup_type" not in df.columns or "regime" not in df.columns:
        return []
    grouped = df.groupby(["setup_type", "regime"])
    results = []
    for (setup, regime), subset in grouped:
        if len(subset) < 3:
            continue
        wins = int(subset["win"].sum())
        results.append({
            "setup": setup, "regime": regime,
            "trades": len(subset), "wins": wins,
            "win_rate": round(wins / len(subset), 3),
            "avg_return": round(float(subset["pct_chg"].mean()), 2)
        })
    results.sort(key=lambda x: (x["trades"], x["win_rate"]), reverse=True)
    return results[:n]


def _worst_combos(df: pd.DataFrame, n: int = 5) -> list:
    """Worst setup+regime combinations by win rate (min 3 trades)."""
    if df.empty or "setup_type" not in df.columns or "regime" not in df.columns:
        return []
    grouped = df.groupby(["setup_type", "regime"])
    results = []
    for (setup, regime), subset in grouped:
        if len(subset) < 3:
            continue
        wins = int(subset["win"].sum())
        results.append({
            "setup": setup, "regime": regime,
            "trades": len(subset), "wins": wins,
            "win_rate": round(wins / len(subset), 3),
            "avg_return": round(float(subset["pct_chg"].mean()), 2)
        })
    results.sort(key=lambda x: x["win_rate"])
    return results[:n]


def _calc_profit_factor(df: pd.DataFrame) -> float:
    """Calculate profit factor: gross wins / gross losses."""
    wins = df[df["win"]]["pct_chg"].sum() if len(df[df["win"]]) > 0 else 0
    losses = abs(df[~df["win"]]["pct_chg"].sum()) if len(df[~df["win"]]) > 0 else 0

    if losses == 0:
        return float("inf") if wins > 0 else 0

    return round(wins / losses, 2)


# CLI entry point
if __name__ == "__main__":
    report = generate_diagnostics_report()
    print(json.dumps(report, indent=2, default=str))
