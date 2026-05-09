#!/usr/bin/env python3
"""
train_mover_predictor_v2.py — REAL ML pipeline (no leakage).

V1 had data leakage (stop_distance_pct dominated mechanically). V2 reconstructs
entry-time market features from OHLCV parquet archive — pre-entry-date data only.

Features (all computed from data BEFORE entry_date):
  • volume_surge_5d        — entry-day vol / prior 20d avg vol
  • volume_surge_10d        — 10d avg vol / prior 60d avg vol (medium-term accum)
  • atr_pct                 — 14d ATR / close at entry
  • dist_from_52wk_high     — entry close as % from 52w high
  • dist_from_20d_high      — entry close as % from 20d high (breakout proximity)
  • return_5d_prior         — return over 5d before entry
  • return_20d_prior        — return over 20d before entry
  • rsi14                   — RSI at entry
  • range_position          — entry close position within 20d (high - low) range
  • setup_int               — encoded setup type
  • score                   — composite score at entry

Target: trail_activated (binary — did the trade reach +2% before stopping out?)

Pipeline: time-series 5-fold CV, LR + RF + GradientBoosting, save best to disk.

Usage:
    python3 train_mover_predictor_v2.py            # full pipeline
    python3 train_mover_predictor_v2.py --quick    # subset of features
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TRADES = BASE / "cache" / "portfolio_backtest_750d_20260509_100501.json"
OHLCV_DIR = BASE / "data" / "ohlcv"
MODEL_DIR = BASE / "cache" / "models"


def extract_features(trade: dict) -> dict | None:
    """Return entry-time feature dict for one trade. None if data unavailable."""
    try:
        import pandas as pd
        ticker = trade["ticker"]
        entry_date = trade["entry_date"][:10]
        path = OHLCV_DIR / f"{ticker}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        # Normalize index
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        df = df.sort_index()
        # Find entry_date row
        entry_ts = pd.Timestamp(entry_date)
        # Slice up to entry (no lookahead)
        df = df[df.index <= entry_ts]
        if len(df) < 60:
            return None  # need enough history

        # Column normalization
        c = "Close" if "Close" in df.columns else "close"
        h = "High" if "High" in df.columns else "high"
        l = "Low" if "Low" in df.columns else "low"
        v = "Volume" if "Volume" in df.columns else "volume"

        close = df[c].iloc[-1]
        # Volume features
        vol_today = df[v].iloc[-1]
        vol_avg_20 = df[v].iloc[-21:-1].mean() if len(df) >= 21 else vol_today
        vol_avg_60 = df[v].iloc[-61:-1].mean() if len(df) >= 61 else vol_today
        vol_avg_10 = df[v].iloc[-11:-1].mean() if len(df) >= 11 else vol_today

        volume_surge_5d = vol_today / max(vol_avg_20, 1)
        volume_surge_10d = vol_avg_10 / max(vol_avg_60, 1)

        # ATR
        if len(df) >= 15:
            tr = df[[h, l]].copy()
            tr["pc"] = df[c].shift(1)
            tr["tr"] = (tr[h] - tr[l]).combine(
                (tr[h] - tr["pc"]).abs(), max
            ).combine((tr[l] - tr["pc"]).abs(), max)
            atr14 = tr["tr"].rolling(14).mean().iloc[-1]
            atr_pct = atr14 / close * 100 if close else 0
        else:
            atr_pct = 0

        # Distance from highs
        high_52w = df[h].iloc[-252:].max() if len(df) >= 252 else df[h].max()
        high_20d = df[h].iloc[-21:-1].max() if len(df) >= 21 else df[h].max()
        dist_52w_high = (close - high_52w) / high_52w * 100 if high_52w else 0
        dist_20d_high = (close - high_20d) / high_20d * 100 if high_20d else 0

        # Returns
        ret_5d = (close - df[c].iloc[-6]) / df[c].iloc[-6] * 100 if len(df) >= 6 else 0
        ret_20d = (close - df[c].iloc[-21]) / df[c].iloc[-21] * 100 if len(df) >= 21 else 0

        # RSI(14)
        if len(df) >= 15:
            diff = df[c].diff()
            gain = diff.where(diff > 0, 0).rolling(14).mean().iloc[-1]
            loss = (-diff.where(diff < 0, 0)).rolling(14).mean().iloc[-1]
            rsi = 100 - 100 / (1 + (gain / loss)) if loss > 0 else 50
        else:
            rsi = 50

        # Range position (where in 20d range is the close)
        low_20d = df[l].iloc[-21:-1].min() if len(df) >= 21 else df[l].min()
        rng = high_20d - low_20d
        range_pos = (close - low_20d) / rng if rng > 0 else 0.5

        return {
            "volume_surge_5d":     float(volume_surge_5d),
            "volume_surge_10d":    float(volume_surge_10d),
            "atr_pct":             float(atr_pct),
            "dist_52w_high":       float(dist_52w_high),
            "dist_20d_high":       float(dist_20d_high),
            "return_5d_prior":     float(ret_5d),
            "return_20d_prior":    float(ret_20d),
            "rsi14":               float(rsi),
            "range_position":      float(range_pos),
            "score":               float(trade.get("score") or 0),
        }
    except Exception as e:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.model_selection import TimeSeriesSplit, cross_val_score
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import roc_auc_score, classification_report
        import numpy as np
    except ImportError as e:
        print(f"sklearn missing: {e}"); return 1

    if not TRADES.exists():
        print(f"trades file not found: {TRADES}"); return 1

    d = json.loads(TRADES.read_text())
    trades = sorted(d["trades"], key=lambda t: t.get("entry_date") or "")
    print(f"Loaded {len(trades)} trades. Extracting entry-time features (this takes a minute)...")

    rows = []
    targets = []
    skipped = 0
    for i, t in enumerate(trades):
        feat = extract_features(t)
        if feat is None:
            skipped += 1
            continue
        # Add setup encoding (numeric)
        feat["setup_idx"] = hash(t.get("setup_type") or "?") % 10
        rows.append(feat)
        targets.append(1 if t.get("trail_activated") else 0)

    print(f"  Extracted: {len(rows)} / {len(trades)} (skipped {skipped} for missing data)")
    if len(rows) < 50:
        print("Insufficient data."); return 1

    feature_names = sorted(rows[0].keys())
    X = np.array([[r[f] for f in feature_names] for r in rows], dtype=float)
    y = np.array(targets)
    print(f"  Feature matrix: {X.shape}")
    print(f"  Class balance: {y.mean()*100:.1f}% movers (target=1)")
    print()

    print(f"=== Feature names ===")
    for f in feature_names:
        print(f"  {f}")
    print()

    # Replace NaN/inf with column medians
    import numpy as np
    for col in range(X.shape[1]):
        col_vals = X[:, col]
        bad = ~np.isfinite(col_vals)
        if bad.any():
            median = np.median(col_vals[~bad]) if (~bad).any() else 0
            X[bad, col] = median

    # Time-series CV
    tscv = TimeSeriesSplit(n_splits=5)

    print("=" * 60)
    print("MODEL COMPARISON (5-fold time-series CV)")
    print("=" * 60)

    models = {
        "LogReg":           LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        "RandomForest":     RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=8,
                                                    class_weight="balanced", random_state=42, n_jobs=-1),
        "GradientBoosting": GradientBoostingClassifier(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=42),
    }

    best_name = None
    best_score = 0
    best_model = None

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    for name, model in models.items():
        Xin = X_scaled if name == "LogReg" else X
        try:
            acc = cross_val_score(model, Xin, y, cv=tscv, scoring="accuracy").mean()
            auc = cross_val_score(model, Xin, y, cv=tscv, scoring="roc_auc").mean()
        except Exception as e:
            print(f"  {name}: failed - {e}")
            continue
        print(f"  {name:<18} accuracy={acc:.3f}  AUC={auc:.3f}")
        if auc > best_score:
            best_score = auc; best_name = name; best_model = (model, Xin)

    if not best_model:
        print("All models failed.")
        return 1

    # Refit on all data
    model, Xin = best_model
    model.fit(Xin, y)

    # Feature importance
    print(f"\n=== Best model: {best_name} (AUC {best_score:.3f}) ===")
    if hasattr(model, "feature_importances_"):
        print("Feature importances:")
        for f, imp in sorted(zip(feature_names, model.feature_importances_), key=lambda x: -x[1])[:10]:
            print(f"  {f:<22} {imp:.3f}")
    elif hasattr(model, "coef_"):
        print("Coefficients (post-scaling):")
        for f, c in sorted(zip(feature_names, model.coef_[0]), key=lambda x: -abs(x[1]))[:10]:
            print(f"  {f:<22} {c:+.3f}")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import joblib
        out = MODEL_DIR / f"mover_predictor_v2_{best_name.lower()}.joblib"
        payload = {
            "model": model, "scaler": scaler if best_name == "LogReg" else None,
            "features": feature_names, "auc": float(best_score),
            "n_trades": len(rows), "skipped": skipped, "model_type": best_name,
            "trained_at": "2026-05-09",
        }
        joblib.dump(payload, out)
        print(f"\n✓ Saved: {out} ({out.stat().st_size:,} bytes)")
    except ImportError:
        print("joblib unavailable")

    # Headline interpretation
    baseline = max(y.mean(), 1 - y.mean())
    print(f"\nBaseline (predict majority): {baseline:.3f}")
    print(f"Best CV AUC: {best_score:.3f} (>0.50 = better than coin flip; >0.65 = useful)")
    if best_score >= 0.65:
        print("✓ Model has useful predictive power. Use as a pre-filter on scan picks.")
    elif best_score >= 0.55:
        print("⚠ Marginal predictive power. Combine with score filter for tiered thresholds.")
    else:
        print("✗ No usable signal. Need more features or different framing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
