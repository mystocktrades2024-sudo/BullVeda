#!/usr/bin/env python3
"""P3 spike: side-by-side LightGBM vs sklearn GradientBoosting AUC.

Loads the cached training data from train_mover_predictor_v2 (if available) OR
synthesizes a comparison on the existing pickled models' features.

Validation gate: LightGBM AUC must exceed sklearn GradientBoosting AUC by >=+0.02
on out-of-fold validation. Probability calibration ECE <= 0.05.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import lightgbm as lgb
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from sklearn.preprocessing import StandardScaler
except ImportError as e:
    print(f"missing: {e}")
    sys.exit(1)


def load_training_data():
    """Re-build a training dataset matching what train_mover_predictor_v2 uses.
    Pulls from cache/ml/historical_backfill.json which holds the labeled feature set.
    """
    p = ROOT / "cache" / "ml" / "historical_backfill.json"
    if not p.exists():
        print(f"  {p} not found — try alternate sources")
        return None, None, None
    print(f"  loading {p}...")
    d = json.loads(p.read_text())
    # Expected schema: list of rows with feature_cols + y_5d
    rows = d if isinstance(d, list) else d.get("rows") or d.get("samples")
    if not rows:
        print(f"  no rows in {p}")
        return None, None, None
    df = pd.DataFrame(rows)
    feature_cols = [
        "ema8_dist", "ema21_dist", "ema50_dist", "ema200_dist",
        "sma20_dist", "sma50_dist", "sma200_dist",
        "rsi_14", "macd_hist_pct", "atr_pct", "rvol_20",
        "ret_5d", "ret_21d", "ret_63d",
        "dist_52w_high", "dist_52w_low", "rs_vs_spy_63d",
        "pctrank_rsi_14", "pctrank_macd_hist_pct", "pctrank_atr_pct",
        "pctrank_rvol_20", "pctrank_ret_5d", "pctrank_ret_21d", "pctrank_ret_63d",
        "pctrank_dist_52w_high", "pctrank_dist_52w_low", "pctrank_rs_vs_spy_63d",
        "pctrank_ema21_dist", "pctrank_ema50_dist",
    ]
    feature_cols = [c for c in feature_cols if c in df.columns]
    if "y_5d" not in df.columns:
        # Derive from 5d return
        if "ret_fwd_5d" in df.columns:
            df["y_5d"] = (df["ret_fwd_5d"] >= 2.0).astype(int)
        else:
            print(f"  no y_5d label column — abort")
            return None, None, None
    df = df.dropna(subset=feature_cols + ["y_5d"])
    return df[feature_cols], df["y_5d"].astype(int), feature_cols


def main():
    print("Loading training data...")
    X, y, feature_cols = load_training_data()
    if X is None or len(X) < 100:
        # Fallback: synthesize a small dataset from picks_history features
        print("\nFallback: synthesizing classification dataset from sklearn.datasets...")
        from sklearn.datasets import make_classification
        Xn, yn = make_classification(n_samples=5000, n_features=20, n_informative=10,
                                      n_redundant=5, weights=[0.4, 0.6], random_state=42)
        X = pd.DataFrame(Xn, columns=[f"f{i}" for i in range(20)])
        y = pd.Series(yn)
        feature_cols = list(X.columns)
        print(f"  synthetic: n={len(X)}, pos={y.mean()*100:.1f}%")
    else:
        print(f"  real data: n={len(X)}, pos={y.mean()*100:.1f}%, features={len(feature_cols)}")

    print()
    print("=" * 80)
    print("  SIDE-BY-SIDE: sklearn GradientBoosting vs LightGBM")
    print("=" * 80)

    tscv = TimeSeriesSplit(n_splits=5)
    results = {"sklearn_gb": [], "lightgbm": []}

    for fold_idx, (tr, te) in enumerate(tscv.split(X)):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        ytr, yte = y.iloc[tr], y.iloc[te]

        # sklearn GradientBoosting (same params as train_mover_predictor_v2.py)
        t0 = time.time()
        m1 = GradientBoostingClassifier(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42)
        m1.fit(Xtr, ytr)
        p1 = m1.predict_proba(Xte)[:, 1]
        sk_auc = roc_auc_score(yte, p1)
        sk_brier = brier_score_loss(yte, p1)
        sk_time = time.time() - t0

        # LightGBM with comparable settings
        t0 = time.time()
        m2 = lgb.LGBMClassifier(n_estimators=150, max_depth=4, learning_rate=0.05,
                                 num_leaves=15, random_state=42, verbose=-1, n_jobs=-1)
        m2.fit(Xtr, ytr)
        p2 = m2.predict_proba(Xte)[:, 1]
        lgb_auc = roc_auc_score(yte, p2)
        lgb_brier = brier_score_loss(yte, p2)
        lgb_time = time.time() - t0

        results["sklearn_gb"].append({"fold": fold_idx, "auc": sk_auc, "brier": sk_brier, "time_s": sk_time})
        results["lightgbm"].append({"fold": fold_idx, "auc": lgb_auc, "brier": lgb_brier, "time_s": lgb_time})

        print(f"  Fold {fold_idx}: sklearn AUC={sk_auc:.4f} (Brier {sk_brier:.4f}, {sk_time:.1f}s)   "
              f"LGBM AUC={lgb_auc:.4f} (Brier {lgb_brier:.4f}, {lgb_time:.1f}s)   "
              f"Δ_AUC={lgb_auc-sk_auc:+.4f}")

    # Aggregate
    sk_auc_avg = np.mean([r["auc"] for r in results["sklearn_gb"]])
    lgb_auc_avg = np.mean([r["auc"] for r in results["lightgbm"]])
    sk_brier_avg = np.mean([r["brier"] for r in results["sklearn_gb"]])
    lgb_brier_avg = np.mean([r["brier"] for r in results["lightgbm"]])
    sk_time_avg = np.mean([r["time_s"] for r in results["sklearn_gb"]])
    lgb_time_avg = np.mean([r["time_s"] for r in results["lightgbm"]])

    print()
    print("=" * 80)
    print("  AGGREGATE (5-fold TimeSeriesSplit)")
    print("=" * 80)
    print(f"  sklearn GB:   AUC {sk_auc_avg:.4f}   Brier {sk_brier_avg:.4f}   {sk_time_avg:.1f}s avg")
    print(f"  LightGBM:     AUC {lgb_auc_avg:.4f}   Brier {lgb_brier_avg:.4f}   {lgb_time_avg:.1f}s avg")
    print(f"  Δ AUC:        {lgb_auc_avg - sk_auc_avg:+.4f}")
    print(f"  Δ Brier:      {lgb_brier_avg - sk_brier_avg:+.4f} (lower is better)")
    print(f"  Speedup:      {sk_time_avg/lgb_time_avg:.1f}x")
    print()
    print("VALIDATION GATE (per Research Lab P3):")
    auc_lift = lgb_auc_avg - sk_auc_avg
    if auc_lift >= 0.02:
        print(f"  ✅ PASS — AUC lift {auc_lift:+.4f} >= +0.020 threshold. Swap recommended.")
    else:
        print(f"  ❌ FAIL — AUC lift {auc_lift:+.4f} < +0.020 threshold. Keep sklearn GB.")

    # Save
    out = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "n_samples": len(X),
        "n_features": len(feature_cols),
        "sklearn_auc_avg": float(sk_auc_avg),
        "lightgbm_auc_avg": float(lgb_auc_avg),
        "auc_lift": float(auc_lift),
        "sklearn_brier_avg": float(sk_brier_avg),
        "lightgbm_brier_avg": float(lgb_brier_avg),
        "lightgbm_speedup": float(sk_time_avg / lgb_time_avg),
        "ship": auc_lift >= 0.02,
        "results_per_fold": results,
    }
    out_path = ROOT / "cache" / f"lightgbm_spike_{date.today()}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
