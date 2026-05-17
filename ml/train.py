"""Train the 3-headed ML Edge model and write artifacts to cache/ml/.

Heads:
  * Direction (3-class)  — P(up)/P(chop)/P(down) via GradientBoostingClassifier + isotonic
  * Magnitude (quantile) — q10/q25/q50/q75/q90 via 5 GradientBoostingRegressor(loss='quantile')
  * Hit-Net (binary)     — P(T1 before stop) via GradientBoostingClassifier + isotonic

Validation: walk-forward — earliest 75% train, last 25% holdout. Metrics dumped
to cache/ml/calibration_report.json so the UI can read them. Final model refit
on full data after metrics are recorded (so production uses every sample).

Sample (2026-05-15 picks_history): 832 rows · 42 features · 35-day date range.
Hit-Net trains on 294 of those (label-decisive subset). Sample is small for
ironclad inference but ships a working baseline; per CLAUDE.md principle 1 the
UI flags 'PRELIM' until n≥30 per regime cell."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import (accuracy_score, brier_score_loss, log_loss,
                             mean_pinball_loss, roc_auc_score)
from sklearn.preprocessing import StandardScaler

from ml.data_loader import FeatureSpec, load_training_frame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "cache", "ml")
os.makedirs(ART_DIR, exist_ok=True)

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]


def _wilson_lb(p: float, n: int, z: float = 1.96) -> float:
    """Wilson score lower bound — for calibration sample-size honesty."""
    if n == 0:
        return 0.0
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / den)


def _split_walk_forward(X: pd.DataFrame, ys: dict, train_frac: float = 0.75):
    """Time-ordered split — earliest `train_frac` train, remainder holdout."""
    order = ys["date"].argsort().to_numpy()
    cut = int(len(order) * train_frac)
    tr, ho = order[:cut], order[cut:]
    return tr, ho


def _train_direction(X, y_dir, train_idx, holdout_idx, dates):
    base = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05,
        subsample=0.85, random_state=42,
    )
    base.fit(X.iloc[train_idx], y_dir.iloc[train_idx])
    cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    cal.fit(X.iloc[train_idx], y_dir.iloc[train_idx])

    p_holdout = cal.predict_proba(X.iloc[holdout_idx])
    pred = p_holdout.argmax(axis=1)
    truth = y_dir.iloc[holdout_idx].values
    acc = float(accuracy_score(truth, pred))
    ll  = float(log_loss(truth, p_holdout, labels=[0, 1, 2]))
    # decile-spread on (P_up - P_down)
    score = p_holdout[:, 2] - p_holdout[:, 0]
    mag_truth = pd.Series(truth).map({0: -1, 1: 0, 2: 1}).values
    deciles = pd.qcut(score, q=10, labels=False, duplicates="drop")
    decile_mean = (pd.DataFrame({"d": deciles, "y": mag_truth})
                   .groupby("d")["y"].mean().to_dict())

    return {
        "model": cal, "n_train": int(len(train_idx)), "n_holdout": int(len(holdout_idx)),
        "metrics": {
            "accuracy": acc, "log_loss": ll,
            "base_rate_up": float((truth == 2).mean()),
            "base_rate_dn": float((truth == 0).mean()),
            "decile_mean": {int(k): float(v) for k, v in decile_mean.items()},
        },
    }


def _train_magnitude(X, y_mag, train_idx, holdout_idx):
    preds = {}
    losses = {}
    quantile_models = {}
    truth = y_mag.iloc[holdout_idx].values
    for q in QUANTILES:
        m = GradientBoostingRegressor(
            loss="quantile", alpha=q,
            n_estimators=160, max_depth=3, learning_rate=0.05,
            subsample=0.85, random_state=42,
        )
        m.fit(X.iloc[train_idx], y_mag.iloc[train_idx])
        p = m.predict(X.iloc[holdout_idx])
        preds[q] = p
        losses[q] = float(mean_pinball_loss(truth, p, alpha=q))
        quantile_models[q] = m
    # decile spread on q50 prediction
    q50_pred = preds[0.5]
    deciles = pd.qcut(q50_pred, q=10, labels=False, duplicates="drop")
    decile_mean = (pd.DataFrame({"d": deciles, "y": truth})
                   .groupby("d")["y"].mean().to_dict())
    return {
        "models": quantile_models,
        "metrics": {
            "pinball_loss_by_q": {str(q): losses[q] for q in QUANTILES},
            "decile_mean_q50":   {int(k): float(v) for k, v in decile_mean.items()},
            "median_holdout_truth": float(np.median(truth)),
        },
    }


def _train_hit_net(X, y_hit, train_idx, holdout_idx):
    # filter -1 sentinel (label-undecisive rows)
    mask_tr = y_hit.iloc[train_idx].values >= 0
    mask_ho = y_hit.iloc[holdout_idx].values >= 0
    X_tr = X.iloc[train_idx][mask_tr]
    y_tr = y_hit.iloc[train_idx][mask_tr]
    X_ho = X.iloc[holdout_idx][mask_ho]
    y_ho = y_hit.iloc[holdout_idx][mask_ho]

    if len(X_tr) < 30 or len(X_ho) < 10 or y_tr.nunique() < 2:
        return {
            "model": None,
            "metrics": {"status": "INSUFFICIENT_SAMPLE",
                        "n_train": int(len(X_tr)), "n_holdout": int(len(X_ho))},
        }

    base = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05,
        subsample=0.85, random_state=42,
    )
    base.fit(X_tr, y_tr)
    cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    cal.fit(X_tr, y_tr)

    p_ho = cal.predict_proba(X_ho)[:, 1]
    try:
        auc = float(roc_auc_score(y_ho, p_ho))
    except ValueError:
        auc = float("nan")
    brier = float(brier_score_loss(y_ho, p_ho))
    base_rate = float(y_ho.mean())

    return {
        "model": cal,
        "metrics": {
            "auc": auc, "brier": brier, "base_rate": base_rate,
            "n_train": int(len(X_tr)), "n_holdout": int(len(X_ho)),
            "wilson_lb_base_rate": _wilson_lb(base_rate, len(X_ho)),
        },
    }


def _per_regime_calibration(X, y_dir, y_hit, dir_model, hit_model) -> dict:
    """Direction accuracy + hit-rate, partitioned by regime4 one-hot."""
    out = {}
    p_dir = dir_model.predict_proba(X)
    pred_dir = p_dir.argmax(axis=1)
    if hit_model is not None:
        p_hit = hit_model.predict_proba(X)[:, 1]
    else:
        p_hit = np.full(len(X), np.nan)
    for col in X.columns:
        if not col.startswith("regime4__"):
            continue
        regime = col.replace("regime4__", "")
        mask = (X[col] == 1).values
        n = int(mask.sum())
        if n == 0:
            continue
        acc = float((pred_dir[mask] == y_dir.values[mask]).mean())
        up_acc = float((pred_dir[mask][y_dir.values[mask] == 2] == 2).mean()) if (y_dir.values[mask] == 2).any() else None
        dn_acc = float((pred_dir[mask][y_dir.values[mask] == 0] == 0).mean()) if (y_dir.values[mask] == 0).any() else None
        # hit metric only where y_hit decisive
        hit_mask = mask & (y_hit.values >= 0)
        if hit_model is not None and hit_mask.any():
            try:
                hit_auc = float(roc_auc_score(y_hit.values[hit_mask], p_hit[hit_mask]))
            except ValueError:
                hit_auc = None
            hit_brier = float(brier_score_loss(y_hit.values[hit_mask], p_hit[hit_mask]))
            hit_n = int(hit_mask.sum())
        else:
            hit_auc, hit_brier, hit_n = None, None, 0
        health = "ok" if n >= 100 else ("warn" if n >= 30 else "bad")
        out[regime] = {
            "n": n, "dir_accuracy": acc, "up_acc": up_acc, "dn_acc": dn_acc,
            "hit_auc": hit_auc, "hit_brier": hit_brier, "hit_n": hit_n,
            "health": health,
        }
    return out


def _refit_full(X, y_dir, y_mag, y_hit):
    """Final production fit on ALL samples (holdout metrics already captured)."""
    dir_base = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05, subsample=0.85, random_state=42)
    dir_base.fit(X, y_dir)
    dir_final = CalibratedClassifierCV(dir_base, method="isotonic", cv="prefit")
    dir_final.fit(X, y_dir)

    mag_final = {}
    for q in QUANTILES:
        m = GradientBoostingRegressor(
            loss="quantile", alpha=q,
            n_estimators=160, max_depth=3, learning_rate=0.05,
            subsample=0.85, random_state=42)
        m.fit(X, y_mag)
        mag_final[q] = m

    hit_mask = y_hit.values >= 0
    if hit_mask.sum() >= 50 and y_hit.values[hit_mask].std() > 0:
        hit_base = GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.05, subsample=0.85, random_state=42)
        hit_base.fit(X[hit_mask], y_hit[hit_mask])
        hit_final = CalibratedClassifierCV(hit_base, method="isotonic", cv="prefit")
        hit_final.fit(X[hit_mask], y_hit[hit_mask])
    else:
        hit_final = None

    return dir_final, mag_final, hit_final


def main():
    X, ys, spec = load_training_frame()
    if len(X) < 50:
        raise RuntimeError(f"too few training rows ({len(X)}) — abort")
    y_dir, y_mag, y_hit, dates = ys["dir"], ys["mag"], ys["hit"], ys["date"]
    print(f"[train] X={X.shape}  date range: {dates.min().date()} -> {dates.max().date()}")
    print(f"[train] dir labels: {y_dir.value_counts().to_dict()}")
    print(f"[train] hit decisive: {int((y_hit >= 0).sum())} of {len(y_hit)}")

    tr_idx, ho_idx = _split_walk_forward(X, ys)
    print(f"[train] walk-forward split: train={len(tr_idx)} holdout={len(ho_idx)}")

    dir_out = _train_direction(X, y_dir, tr_idx, ho_idx, dates)
    print(f"[train] direction holdout acc={dir_out['metrics']['accuracy']:.3f} log_loss={dir_out['metrics']['log_loss']:.3f}")
    mag_out = _train_magnitude(X, y_mag, tr_idx, ho_idx)
    print(f"[train] magnitude pinball q50={mag_out['metrics']['pinball_loss_by_q']['0.5']:.3f}")
    hit_out = _train_hit_net(X, y_hit, tr_idx, ho_idx)
    if hit_out["model"] is not None:
        print(f"[train] hit-net AUC={hit_out['metrics']['auc']:.3f} brier={hit_out['metrics']['brier']:.3f} (n_ho={hit_out['metrics']['n_holdout']})")
    else:
        print(f"[train] hit-net SKIPPED — insufficient sample ({hit_out['metrics']})")

    # per-regime
    per_regime = _per_regime_calibration(
        X.iloc[ho_idx], y_dir.iloc[ho_idx], y_hit.iloc[ho_idx],
        dir_out["model"], hit_out["model"],
    )

    # final refit on all data
    dir_final, mag_final, hit_final = _refit_full(X, y_dir, y_mag, y_hit)

    # write artifacts
    joblib.dump(dir_final,            os.path.join(ART_DIR, "direction.pkl"))
    joblib.dump(mag_final,            os.path.join(ART_DIR, "magnitude.pkl"))
    joblib.dump(hit_final,            os.path.join(ART_DIR, "hit_net.pkl"))
    joblib.dump(spec,                 os.path.join(ART_DIR, "feature_spec.pkl"))

    # numeric feature importance from base estimator (post-calibration loses it)
    base_dir = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05, subsample=0.85, random_state=42)
    base_dir.fit(X, y_dir)
    importance = sorted(
        ((c, float(f)) for c, f in zip(X.columns, base_dir.feature_importances_)),
        key=lambda x: -x[1],
    )[:30]

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_total": int(len(X)),
        "date_range": [str(dates.min().date()), str(dates.max().date())],
        "feature_count": int(len(X.columns)),
        "split": {"train": int(len(tr_idx)), "holdout": int(len(ho_idx))},
        "direction":   dir_out["metrics"],
        "magnitude":   mag_out["metrics"],
        "hit_net":     hit_out["metrics"],
        "per_regime":  per_regime,
        "top_features": importance,
        "calibration_health": "ok" if dir_out["metrics"]["accuracy"] > 0.40 else "warn",
        "preliminary": int(len(X)) < 1000,
    }
    with open(os.path.join(ART_DIR, "calibration_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"[train] artifacts written to {ART_DIR}")
    print(f"[train] preliminary={report['preliminary']}  health={report['calibration_health']}")


if __name__ == "__main__":
    main()
