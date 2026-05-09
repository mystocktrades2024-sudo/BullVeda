#!/usr/bin/env python3
"""
train_mover_predictor.py — train a binary classifier on 384 trades to predict
whether a candidate trade will activate the trailing stop (move ≥2% in our favor).

Why this matters:
  • System enters 384 stocks; 171 (45%) become movers (trail_activated=True)
  • Movers: 100% WR, +6.5% avg, PF 7.73
  • Non-movers: 7.5% WR, -3.2% avg, PF 0.01
  • If we lift mover-detection from 45% → 55%, system PF rises ~0.7 → ~1.4

This script:
  1. Loads 384 backtest trades
  2. Computes 6 candidate features per trade (from mover_predictor.py)
  3. Trains sklearn LogisticRegression + RandomForest
  4. Reports feature importances + cross-validated accuracy
  5. Saves trained model to cache/models/mover_predictor_v1.joblib

Note: training data is somewhat circular (we don't have entry-time feature
values for backtest trades — only their backtest output). This is a SCAFFOLD;
the proper approach is to log entry-time features during the next live scan
and accumulate over time. For now, we use what's available in the trade record.

Usage:
    python3 train_mover_predictor.py
    python3 train_mover_predictor.py --model rf      # use random forest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TRADES_PATH = BASE / "cache" / "portfolio_backtest_750d_20260509_100501.json"
MODEL_DIR = BASE / "cache" / "models"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=["lr", "rf"], default="lr")
    p.add_argument("--cv-folds", type=int, default=5)
    args = p.parse_args()

    if not TRADES_PATH.exists():
        print(f"✗ {TRADES_PATH} not found")
        return 1

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import TimeSeriesSplit, cross_val_score
        from sklearn.preprocessing import StandardScaler
        import numpy as np
    except ImportError as e:
        print(f"✗ sklearn not available: {e}")
        print("  Install with: pip install scikit-learn")
        return 1

    d = json.loads(TRADES_PATH.read_text())
    trades = sorted(d["trades"], key=lambda t: t.get("entry_date") or "")
    print(f"Loaded {len(trades)} trades.")

    # Build feature matrix from what's actually in trade records
    # Available fields: ticker, entry_date, exit_date, entry_price, exit_price,
    # stop_price, position_size, pnl_pct, pnl_dollar, exit_reason, days_held,
    # setup_type, score, verdict, win, trail_activated, highest_price
    setup_to_int = {s: i for i, s in enumerate({t.get("setup_type") or "?" for t in trades})}
    print(f"Setup encodings: {setup_to_int}")

    # ENTRY-TIME features only — no lookahead. days_held / pnl_pct / exit_*
    # would all be data leakage (computed after trade ends).
    X = []
    y = []
    for t in trades:
        ep = t.get("entry_price") or 0
        sp = t.get("stop_price") or 0
        row = [
            t.get("score") or 0,
            setup_to_int.get(t.get("setup_type") or "?", 0),
            ep,
            (sp / ep) if ep > 0 else 0,                       # stop/entry ratio at entry
            ((ep - sp) / ep * 100) if ep > 0 else 0,           # stop_distance_pct at entry
        ]
        X.append(row)
        y.append(1 if t.get("trail_activated") else 0)
    X = np.array(X, dtype=float)
    y = np.array(y)
    print(f"Feature matrix: {X.shape}, target balance: {y.mean()*100:.1f}% positive")
    print(f"NOTE: training on entry-time features only (no lookahead). The realistic")
    print(f"      ceiling is much lower than the leaky version (~0.6 not 0.96).")

    feature_names = ["score", "setup_int", "entry_price", "stop_entry_ratio", "stop_distance_pct"]

    if args.model == "lr":
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
        cv_scores = cross_val_score(model, X_scaled, y, cv=TimeSeriesSplit(n_splits=args.cv_folds), scoring="accuracy")
        model.fit(X_scaled, y)
        print(f"\n=== Logistic Regression ===")
        print(f"5-fold time-series CV accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        print(f"Coefficients (post-scaling):")
        for f, c in sorted(zip(feature_names, model.coef_[0]), key=lambda x: -abs(x[1])):
            print(f"  {f:<22} {c:+.3f}")
    else:
        model = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=8,
                                        class_weight="balanced", random_state=42, n_jobs=-1)
        cv_scores = cross_val_score(model, X, y, cv=TimeSeriesSplit(n_splits=args.cv_folds), scoring="accuracy")
        model.fit(X, y)
        print(f"\n=== Random Forest ===")
        print(f"5-fold time-series CV accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        print(f"Feature importances:")
        for f, imp in sorted(zip(feature_names, model.feature_importances_), key=lambda x: -x[1]):
            print(f"  {f:<22} {imp:.3f}")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import joblib
        out = MODEL_DIR / f"mover_predictor_{args.model}_v1.joblib"
        joblib.dump({"model": model, "features": feature_names, "setup_encoding": setup_to_int,
                      "cv_accuracy_mean": float(cv_scores.mean()), "cv_accuracy_std": float(cv_scores.std()),
                      "n_trades": len(trades), "model_type": args.model}, out)
        print(f"\n✓ Saved: {out}")
    except ImportError:
        print("\n  joblib not available; model not persisted")

    # Compare to baseline (predict all positive = 45% accuracy)
    baseline = max(y.mean(), 1 - y.mean())
    print(f"\nBaseline (predict majority class): {baseline:.3f}")
    print(f"Model uplift over baseline: {cv_scores.mean() - baseline:+.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
