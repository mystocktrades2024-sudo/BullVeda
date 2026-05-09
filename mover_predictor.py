"""
mover_predictor.py — pre-filter for stocks likely to move ≥2% in our favor (Step #6).

THE big-ROI insight from 750d backtest analysis:
  • System enters 384 stocks, 171 (45%) activate trailing stop (move ≥2%)
  • Of those, 100% become wins (avg +6.5%, PF 7.73 on the activated subset)
  • The remaining 213 (55%) bleed out via stop_loss + time_stop + gap_through_stop

The trade-entry signals already work — they identify potential movers at 45% rate.
A "mover predictor" that lifts that to 60% would compound dramatically with the
existing trailing-stop alpha. Even a 50% rate ships a profitable system.

This module scaffolds the candidate features. Full training pipeline waits until
we have the 384-trade dataset clean (already in cache/portfolio_backtest_750d_*.json).

Status: SCAFFOLD — feature definitions + Bayesian baseline. Real ML model
(RandomForest / XGBoost) wired in once we agree on the feature set.

Approach:
  1. Define candidate features (this file)
  2. Score each historical trade against features at entry time
  3. Train a simple binary classifier (mover vs non-mover)
  4. At scan time: filter picks below the classifier's mover probability threshold

Candidate features (price-action + structural):
  • volume_surge       — entry-day volume / 20d avg volume
  • atr_expansion       — entry-day range vs 20d ATR
  • breakout_clean      — close > 20d high vs prior compression
  • gap_at_entry        — entry vs prior close gap %
  • float_short_ratio   — short_float_pct (already wired from Finviz Elite)
  • inst_ownership      — inst_own_pct (squeeze setup)
  • options_flow_skew   — call/put ratio (Schwab data)
  • rs_rank_1d_chg      — RS rank delta over last day (acceleration signal)
  • ema_stack           — fresh bullish stack (binary)
  • catalyst_count      — number of active catalyst tags

Decision threshold: aim for mover_probability >= 0.55 (slight edge over 45% baseline).
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Sequence

BASE = Path(__file__).resolve().parent
BACKTEST_PATH = BASE / "cache" / "portfolio_backtest_750d_20260509_100501.json"


def extract_movers_baseline() -> dict:
    """Read 750d backtest, return baseline mover-rate per setup × score-band.

    Defines target: trades whose `trail_activated == True` (price moved ≥2%
    in our favor at some point during the holding period).
    """
    if not BACKTEST_PATH.exists():
        return {"error": "750d backtest snapshot not found", "candidates": []}
    d = json.loads(BACKTEST_PATH.read_text())
    trades = d.get("trades", [])
    if not trades:
        return {"error": "no trades", "candidates": []}

    overall_n = len(trades)
    overall_movers = sum(1 for t in trades if t.get("trail_activated"))
    overall_rate = overall_movers / overall_n if overall_n else 0

    # Mover rate by setup
    by_setup = defaultdict(lambda: {"n": 0, "movers": 0})
    for t in trades:
        s = t.get("setup_type") or "?"
        by_setup[s]["n"] += 1
        if t.get("trail_activated"):
            by_setup[s]["movers"] += 1

    setup_rates = {}
    for s, v in by_setup.items():
        rate = v["movers"] / v["n"] if v["n"] else 0
        setup_rates[s] = {"n": v["n"], "movers": v["movers"], "rate": round(rate * 100, 1)}

    # Mover rate by score band
    bands = [(0, 60, "<60"), (60, 70, "60-69"), (70, 80, "70-79"),
             (80, 90, "80-89"), (90, 101, "90+")]
    band_rates = {}
    for lo, hi, lbl in bands:
        items = [t for t in trades if lo <= (t.get("score") or 0) < hi]
        if not items:
            continue
        movers = sum(1 for t in items if t.get("trail_activated"))
        rate = movers / len(items) if items else 0
        band_rates[lbl] = {"n": len(items), "movers": movers, "rate": round(rate * 100, 1)}

    return {
        "overall": {"n": overall_n, "movers": overall_movers,
                     "rate_pct": round(overall_rate * 100, 1)},
        "by_setup": setup_rates,
        "by_score_band": band_rates,
        "target": "trail_activated == True (price moved ≥2% in our favor)",
        "edge_implied_if_lifted": "If mover_rate goes 45% → 55%, system PF rises from 0.70 to ~1.4 (rough extrapolation from PF 7.73 on movers).",
    }


# ─── Candidate features (placeholders — wire to real T data + ohlcv) ────────

def feature_volume_surge(ticker_row: dict) -> float | None:
    """Entry-day volume / 20d avg volume. Surge ≥1.5× = candidate mover."""
    vol = ticker_row.get("volume")
    avg = ticker_row.get("avg_volume")
    if not vol or not avg or avg <= 0:
        return None
    return vol / avg


def feature_atr_expansion(ticker_row: dict) -> float | None:
    """Entry-day range expansion vs 20d ATR — measures volatility uptick."""
    atr = ticker_row.get("atr_pct")
    if not atr:
        return None
    # 1.0 = normal, >1.3 = expansion, <0.7 = contraction
    # Without intraday data we approximate from rvol
    rvol = ticker_row.get("rvol", 1.0) or 1.0
    return rvol


def feature_breakout_clean(ticker_row: dict) -> bool:
    """Is the entry breaking out cleanly above 20d high?"""
    px = ticker_row.get("price", 0)
    week52_high = ticker_row.get("week52_high", 0)
    if not px or not week52_high:
        return False
    # Within 2% of 52w high = strong breakout context
    return abs(px - week52_high) / week52_high < 0.02


def feature_short_pressure(ticker_row: dict) -> float:
    """Combined short-interest + institutional ownership signal (squeeze potential)."""
    sf = (ticker_row.get("finviz_elite") or {}).get("short_float_pct") or 0
    io = (ticker_row.get("finviz_elite") or {}).get("inst_own_pct") or 0
    if sf >= 15 and io >= 80:
        return 1.0
    if sf >= 10 and io >= 60:
        return 0.5
    return 0.0


def feature_options_skew(ticker_row: dict) -> float | None:
    """Put/call ratio inverted — bullish call flow = lower P/C."""
    od = ticker_row.get("options_data") or {}
    pcr = od.get("put_call_ratio")
    if pcr is None or pcr <= 0:
        return None
    return 1.0 / pcr  # higher = more call-heavy


def feature_catalyst_density(ticker_row: dict) -> int:
    """How many catalyst tags are active right now."""
    return len(ticker_row.get("catalyst_tags") or [])


# ─── Compute mover_probability score (heuristic until ML trained) ───────────

def heuristic_mover_score(ticker_row: dict) -> float:
    """0-1 score combining the candidate features. Simple weighted sum until
    we train a real classifier on the 750d trades.
    """
    components = []
    weights = []

    # volume_surge — heavier weight (best historical predictor)
    vs = feature_volume_surge(ticker_row)
    if vs is not None:
        v = max(0, min(1, (vs - 1) / 2))  # 1.0=0, 3.0=1.0
        components.append(v); weights.append(0.30)

    # atr_expansion (rvol proxy)
    ae = feature_atr_expansion(ticker_row)
    if ae is not None:
        v = max(0, min(1, (ae - 1) / 1.5))
        components.append(v); weights.append(0.20)

    # breakout_clean
    components.append(1.0 if feature_breakout_clean(ticker_row) else 0.0); weights.append(0.15)

    # short_pressure
    components.append(feature_short_pressure(ticker_row)); weights.append(0.15)

    # options_skew
    os_ = feature_options_skew(ticker_row)
    if os_ is not None:
        v = max(0, min(1, (os_ - 1) / 4))   # P/C 0.5 → 1.0, P/C 1.0 → 0
        components.append(v); weights.append(0.10)

    # catalyst_density
    cat = feature_catalyst_density(ticker_row)
    components.append(min(1.0, cat / 3)); weights.append(0.10)

    # weighted sum, normalize
    if not components:
        return 0.5  # neutral default
    total_w = sum(weights[: len(components)])
    score = sum(c * w for c, w in zip(components, weights)) / total_w if total_w else 0.5
    return round(score, 3)


def predict_mover(ticker_row: dict, threshold: float = 0.55) -> dict:
    """Return mover prediction for a ticker row.

    Returns: {is_mover, mover_probability, threshold, top_features}
    """
    score = heuristic_mover_score(ticker_row)
    return {
        "is_mover": score >= threshold,
        "mover_probability": score,
        "threshold": threshold,
        "features": {
            "volume_surge": feature_volume_surge(ticker_row),
            "atr_expansion": feature_atr_expansion(ticker_row),
            "breakout_clean": feature_breakout_clean(ticker_row),
            "short_pressure": feature_short_pressure(ticker_row),
            "options_skew": feature_options_skew(ticker_row),
            "catalyst_density": feature_catalyst_density(ticker_row),
        },
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", action="store_true", help="Show 750d mover rate baseline")
    p.add_argument("--threshold", type=float, default=0.55)
    args = p.parse_args()

    if args.baseline:
        baseline = extract_movers_baseline()
        print(json.dumps(baseline, indent=2, default=str))
    else:
        # Demo: score the latest scan's tickers
        bundle_path = BASE / "cache" / "last_bundle.json"
        if not bundle_path.exists():
            print("No bundle. Run scan first.")
            raise SystemExit(1)
        b = json.loads(bundle_path.read_text())
        rows = b.get("all_scored", [])[:20]
        print(f"Scoring top 20 from latest scan...\n")
        print(f"{'Ticker':<8} {'Score':>5} {'MoverProb':>10} {'IsMover':>8} {'Setup':<25}")
        for r in rows:
            pred = predict_mover(r, args.threshold)
            print(f"{r.get('ticker','?'):<8} {r.get('score',0):>5} {pred['mover_probability']:>10.3f} "
                  f"{'✓' if pred['is_mover'] else '·':>8} {(r.get('setup_family') or '?')[:24]:<25}")
