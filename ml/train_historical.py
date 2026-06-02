"""Train mode-aware ML Edge models from the historical backfill.

For each horizon h ∈ {5d (swing), 21d (position), 126d (invest)} trains:
  - Direction (3-class: P_up / P_chop / P_down)  — GradientBoostingClassifier + isotonic
  - Magnitude (q10/25/50/75/90 quantile regression) — 5× GradientBoostingRegressor
  - Hit-Net (binary: did fwd return clear an asymmetric reward threshold) — GBC + isotonic

Direction threshold scales with √t:  2% × √(h/5)  — so a "chop" zone is
[-2%, +2%] at 5d, [-4.1%, +4.1%] at 21d, [-10.0%, +10.0%] at 126d.

Walk-forward: chronological 75/25 train/holdout. Final production models refit
on full data after holdout metrics captured.

Sample (2026-05-15 backfill): 66,366 rows × 17 features × 18mo. Each horizon
trains independently; artifacts go to cache/ml/{swing,position,invest}_*.pkl."""
from __future__ import annotations
import json
import math
import os
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import (accuracy_score, brier_score_loss, log_loss,
                             mean_pinball_loss, roc_auc_score)

# HistGradientBoosting is 10-20× faster than GradientBoosting on tabular data.
# sklearn 1.6 supports loss='quantile' with `quantile=alpha`. This is what makes
# 66K rows × 9 fits tractable (was ~40min before, ~3min now).

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "cache", "ml")
BACKFILL = os.path.join(ART_DIR, "historical_backfill.json")
os.makedirs(ART_DIR, exist_ok=True)

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]

# Horizon → (label_col, direction_threshold_pct, hit_threshold_pct, prefix)
# direction_thr is the +/- band defining the "chop" class (sqrt-t scaled).
# hit_thr is the binary "won" threshold (Brownian-scaled to ~1× expected vol).
MODES = {
    "swing":    {"label": "y_5d",   "horizon_days":   5, "dir_thr": 2.0,  "hit_thr": 3.0,   "label_pct_scale": 100},
    "position": {"label": "y_21d",  "horizon_days":  21, "dir_thr": 4.1,  "hit_thr": 6.0,   "label_pct_scale": 100},
    "invest":   {"label": "y_126d", "horizon_days": 126, "dir_thr": 10.0, "hit_thr": 15.0,  "label_pct_scale": 100},
}

# Imported from historical_backfill to stay in sync — v3 added 12
# cross-sectional pct_rank columns (rsi/macd/atr/rvol/returns/distances/RS).
from ml.historical_backfill import FEATURE_COLS  # noqa: E402

# Conditional Hit-Net threshold grid. For each (row, mode) we replicate the
# row K times with K different "what if T1 distance was X%?" thresholds, and
# build the label y_hit = (forward_return >= T). The trained Hit-Net then
# answers P(reach +T%) for ANY T at inference time — matching the actual
# canonical_trade_plan.t1 distance instead of a single fixed threshold.
HIT_NET_THRESHOLDS = {
    "swing":    [0.015, 0.025, 0.035, 0.05, 0.07, 0.10],
    "position": [0.03,  0.05,  0.08,  0.12, 0.18, 0.25],
    "invest":   [0.08,  0.15,  0.25,  0.35, 0.50, 0.70],
}


def _wilson_lb(p: float, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / den)


def _load_backfill() -> pd.DataFrame:
    with open(BACKFILL) as f:
        payload = json.load(f)
    df = pd.DataFrame(payload["rows"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _make_hgb():
    return HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.05,
        l2_regularization=0.5, random_state=42,
    )


def _fit_isotonic_heldout(make_base, X_tr, y_tr, calib_frac: float = 0.20, multiclass: bool = False):
    """Calibrate on a SEPARATE later slice of the (time-ordered) train set — never
    the rows the base saw. Fixes the in-sample calibration leak (audit 2026-06-01:
    held-out Brier is the honest one). Falls back to in-sample only when the calib
    slice is too thin. Returns (calibrated_model, mode)."""
    n = len(X_tr); cut = max(1, int(n * (1.0 - calib_frac)))
    Xb = X_tr.iloc[:cut]; yb = y_tr.iloc[:cut]
    Xc = X_tr.iloc[cut:]; yc = y_tr.iloc[cut:]
    need = 3 if multiclass else 2
    dist_c = yc.nunique() if hasattr(yc, "nunique") else len(set(yc))
    dist_b = yb.nunique() if hasattr(yb, "nunique") else len(set(yb))
    if len(Xc) >= 200 and dist_c >= need and dist_b >= need:
        base = make_base(); base.fit(Xb, yb)
        cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit"); cal.fit(Xc, yc)
        return cal, "heldout"
    base = make_base(); base.fit(X_tr, y_tr)
    cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit"); cal.fit(X_tr, y_tr)
    return cal, "insample_fallback"


def _train_direction(X, y_dir, tr, ho):
    cal, _calib_mode = _fit_isotonic_heldout(_make_hgb, X.iloc[tr], y_dir.iloc[tr], multiclass=True)
    p_ho = cal.predict_proba(X.iloc[ho])
    pred = p_ho.argmax(axis=1)
    truth = y_dir.iloc[ho].values
    acc = float(accuracy_score(truth, pred))
    ll  = float(log_loss(truth, p_ho, labels=[0, 1, 2]))
    score = p_ho[:, 2] - p_ho[:, 0]
    mag_truth = pd.Series(truth).map({0: -1, 1: 0, 2: 1}).values
    deciles = pd.qcut(score, q=10, labels=False, duplicates="drop")
    decile_mean = pd.DataFrame({"d": deciles, "y": mag_truth}).groupby("d")["y"].mean().to_dict()
    return cal, {
        "accuracy": acc, "log_loss": ll,
        "base_rate_up": float((truth == 2).mean()),
        "base_rate_dn": float((truth == 0).mean()),
        "decile_mean": {int(k): float(v) for k, v in decile_mean.items()},
        "n_train": int(len(tr)), "n_holdout": int(len(ho)),
    }


def _train_magnitude(X, y_mag, tr, ho):
    truth = y_mag.iloc[ho].values
    models, losses, preds = {}, {}, {}
    for q in QUANTILES:
        m = HistGradientBoostingRegressor(
            loss="quantile", quantile=q,
            max_iter=150, max_depth=4, learning_rate=0.05,
            l2_regularization=0.5, random_state=42,
        )
        m.fit(X.iloc[tr], y_mag.iloc[tr])
        p = m.predict(X.iloc[ho])
        models[q] = m
        preds[q] = p
        losses[q] = float(mean_pinball_loss(truth, p, alpha=q))
    q50 = preds[0.5]
    deciles = pd.qcut(q50, q=10, labels=False, duplicates="drop")
    decile_mean = pd.DataFrame({"d": deciles, "y": truth}).groupby("d")["y"].mean().to_dict()
    return models, {
        "pinball_loss_by_q": {str(q): losses[q] for q in QUANTILES},
        "decile_mean_q50":   {int(k): float(v) for k, v in decile_mean.items()},
        "median_holdout_truth": float(np.median(truth)),
    }


def _train_hit_net_conditional(X, y_mag, tr, ho, thresholds: list[float]):
    """Threshold-conditional Hit-Net.

    For each row in the training set, replicate K times with K different
    thresholds T. Label is `y_hit = (forward_return >= T)`. Feature row
    gets `target_thr_pct = T * 100` appended. Model learns to answer
    P(reach +T%) for any T at inference time.

    Note: Direction + Magnitude models still use the BASE feature set
    (no target_thr_pct). Only this Hit-Net does."""
    def _build_conditional(idx):
        # Build K-replicated training set with target_thr_pct column
        Xi = X.iloc[idx].reset_index(drop=True)
        yi = y_mag.iloc[idx].reset_index(drop=True)
        frames, labels = [], []
        for T in thresholds:
            Xj = Xi.copy()
            Xj["target_thr_pct"] = T * 100  # in percent
            frames.append(Xj)
            labels.append((yi >= T).astype(int))
        return pd.concat(frames, ignore_index=True), pd.concat(labels, ignore_index=True)

    X_tr_cond, y_tr_cond = _build_conditional(tr)
    X_ho_cond, y_ho_cond = _build_conditional(ho)

    cal, _calib_mode = _fit_isotonic_heldout(_make_hgb, X_tr_cond, y_tr_cond)
    p_ho = cal.predict_proba(X_ho_cond)[:, 1]
    truth = y_ho_cond.values
    try:
        auc = float(roc_auc_score(truth, p_ho))
    except ValueError:
        auc = float("nan")
    brier = float(brier_score_loss(truth, p_ho))
    base_rate = float(truth.mean())
    # Per-threshold breakdown so the UI can show which T-values were learned best
    per_thr = {}
    n_per = len(ho)
    for k, T in enumerate(thresholds):
        sl = slice(k * n_per, (k + 1) * n_per)
        try:
            per_thr[f"{T*100:.1f}%"] = {
                "auc": float(roc_auc_score(truth[sl], p_ho[sl])),
                "base_rate": float(truth[sl].mean()),
                "n": int(n_per),
            }
        except ValueError:
            per_thr[f"{T*100:.1f}%"] = {"auc": None, "base_rate": float(truth[sl].mean()), "n": int(n_per)}

    # --- Selectivity: realized hit rate per prediction-probability decile ---
    # For each target T, score the base holdout at a FIXED target_thr_pct=T,
    # then bucket predictions into deciles and report the realized fraction
    # that actually reached +T%. This turns "AUC 0.76" into a tradeable
    # threshold: "trade the top decile → X% hit vs Y% base".
    selectivity = _compute_selectivity(cal, X, y_mag, ho, thresholds)

    return cal, {
        "auc": auc, "brier": brier, "base_rate": base_rate,
        "n_train": int(len(X_tr_cond)), "n_holdout": int(len(X_ho_cond)),
        "wilson_lb_base_rate": _wilson_lb(base_rate, len(X_ho_cond)),
        "thresholds_pct": [T * 100 for T in thresholds],
        "per_threshold": per_thr,
        "selectivity":   selectivity,
        "conditional":   True,
    }


def _compute_selectivity(cal, X, y_mag, ho, thresholds: list[float]):
    """Per-decile realized hit rate on the holdout, scored at each FIXED target.

    Returns {"primary_target_pct": T0*100, "by_target": [ {target_pct, base,
    top10, top25, top50, lift, decile_ladder[10], n}, ... ]}. The decile
    ladder is monotonic when the model's ranking carries real edge."""
    Xb = X.iloc[ho].reset_index(drop=True)
    yb = y_mag.iloc[ho].reset_index(drop=True).values
    n = len(yb)
    by_target = []
    for T in thresholds:
        Xj = Xb.copy()
        Xj["target_thr_pct"] = T * 100
        p = cal.predict_proba(Xj)[:, 1]
        true = (yb >= T).astype(float)
        base = float(true.mean())
        order = np.argsort(-p)  # most-confident first

        def _rate(frac):
            k = max(1, int(n * frac))
            return float(true[order[:k]].mean())

        d10, d25, d50 = _rate(0.10), _rate(0.25), _rate(0.50)
        try:
            dec = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False).values
            ladder = [float(true[dec == i].mean()) for i in range(10)]
        except (ValueError, IndexError):
            ladder = []
        by_target.append({
            "target_pct": round(T * 100, 1),
            "base": base, "top10": d10, "top25": d25, "top50": d50,
            "lift": (round(d10 / base, 2) if base > 0 else None),
            "decile_ladder": ladder, "n": int(n),
        })
    # primary = median threshold (the canonical swing/position/invest target)
    primary = thresholds[len(thresholds) // 2] * 100 if thresholds else None
    return {"primary_target_pct": (round(primary, 1) if primary else None),
            "by_target": by_target}


def _refit_full(X, y_dir, y_mag, thresholds):
    """Refit Direction + Magnitude + Hit-Net (threshold-conditional) on full data."""
    dir_base = HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.05,
        l2_regularization=0.5, random_state=42,
    )
    dir_base.fit(X, y_dir)
    dir_final = CalibratedClassifierCV(dir_base, method="isotonic", cv="prefit")
    dir_final.fit(X, y_dir)

    mag_final = {}
    for q in QUANTILES:
        m = HistGradientBoostingRegressor(
            loss="quantile", quantile=q,
            max_iter=150, max_depth=4, learning_rate=0.05,
            l2_regularization=0.5, random_state=42,
        )
        m.fit(X, y_mag)
        mag_final[q] = m

    # Conditional Hit-Net on full data — replicate × K thresholds
    frames, labels = [], []
    for T in thresholds:
        Xj = X.copy()
        Xj["target_thr_pct"] = T * 100
        frames.append(Xj)
        labels.append((y_mag >= T).astype(int))
    X_cond = pd.concat(frames, ignore_index=True)
    y_cond = pd.concat(labels, ignore_index=True)
    hit_base = HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.05,
        l2_regularization=0.5, random_state=42,
    )
    hit_base.fit(X_cond, y_cond)
    hit_final = CalibratedClassifierCV(hit_base, method="isotonic", cv="prefit")
    hit_final.fit(X_cond, y_cond)
    return dir_final, mag_final, hit_final


def train_mode(df: pd.DataFrame, mode: str) -> dict:
    cfg = MODES[mode]
    label_col = cfg["label"]
    dir_thr = cfg["dir_thr"] / 100.0  # already in %, convert to fractional

    # Build X, y. Hit-Net base rate is no longer at a single threshold —
    # it's reported per-threshold inside _train_hit_net_conditional.
    df = df.dropna(subset=[label_col]).copy()
    df = df.sort_values("date").reset_index(drop=True)
    X = df[FEATURE_COLS]
    y_mag = df[label_col]
    y_dir = pd.Series(np.where(y_mag >= dir_thr, 2, np.where(y_mag <= -dir_thr, 0, 1)), name="dir")
    dates = df["date"]

    print(f"\n[train · {mode}] X={X.shape}  date {dates.min().date()} → {dates.max().date()}")
    print(f"[train · {mode}] dir distribution: {y_dir.value_counts().to_dict()}")

    cut = int(len(X) * 0.75)
    tr = np.arange(cut)
    ho = np.arange(cut, len(X))
    print(f"[train · {mode}] walk-forward split: train={len(tr)} holdout={len(ho)}")

    cal_dir, dir_metrics = _train_direction(X, y_dir, tr, ho)
    print(f"[train · {mode}] direction: acc={dir_metrics['accuracy']:.3f} log_loss={dir_metrics['log_loss']:.3f}")

    mag_models, mag_metrics = _train_magnitude(X, y_mag, tr, ho)
    print(f"[train · {mode}] magnitude: pinball q50={mag_metrics['pinball_loss_by_q']['0.5']:.4f}")

    # v3: Hit-Net is threshold-conditional — model learns P(reach +T%) for
    # any T in the threshold grid. At inference, caller passes actual
    # (T1 - entry) / entry as target_thr_pct feature.
    thresholds = HIT_NET_THRESHOLDS[mode]
    cal_hit, hit_metrics = _train_hit_net_conditional(X, y_mag, tr, ho, thresholds)
    print(f"[train · {mode}] hit-net:   AUC={hit_metrics['auc']:.3f} brier={hit_metrics['brier']:.3f} base={hit_metrics['base_rate']:.3f}  (conditional · {len(thresholds)} thresholds)")

    # Refit on full data for production
    y_dir_full = pd.Series(np.where(y_mag >= dir_thr, 2, np.where(y_mag <= -dir_thr, 0, 1)), name="dir")
    dir_final, mag_final, hit_final = _refit_full(X, y_dir_full, y_mag, thresholds)

    # HistGradientBoosting doesn't expose feature_importances_ directly —
    # use permutation importance on a small holdout for the top-feature
    # ranking. Cheap (~10K rows, 3-class predict_proba × 17 features).
    from sklearn.inspection import permutation_importance
    n_perm = min(5000, len(ho))
    ho_idx = np.arange(len(X) - n_perm, len(X))
    base_dir_uncal = HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.05,
        l2_regularization=0.5, random_state=42,
    ).fit(X.iloc[:len(X)-n_perm], y_dir_full.iloc[:len(X)-n_perm])
    try:
        pi = permutation_importance(base_dir_uncal, X.iloc[ho_idx], y_dir_full.iloc[ho_idx],
                                    n_repeats=3, random_state=42, n_jobs=-1)
        top_feat = sorted(((c, float(v)) for c, v in zip(FEATURE_COLS, pi.importances_mean)),
                          key=lambda x: -x[1])[:15]
    except Exception:
        top_feat = []

    joblib.dump(dir_final, os.path.join(ART_DIR, f"{mode}_direction.pkl"))
    joblib.dump(mag_final, os.path.join(ART_DIR, f"{mode}_magnitude.pkl"))
    joblib.dump(cal_hit if hit_final is None else hit_final,
                os.path.join(ART_DIR, f"{mode}_hit_net.pkl"))

    return {
        "mode": mode,
        "label_col": label_col,
        "horizon_days": cfg["horizon_days"],
        "dir_threshold_pct": cfg["dir_thr"],
        "hit_thresholds_pct": [T * 100 for T in HIT_NET_THRESHOLDS[mode]],
        "feature_cols": FEATURE_COLS,
        "hit_feature_cols": FEATURE_COLS + ["target_thr_pct"],
        "n_total": int(len(X)),
        "date_range": [str(dates.min().date()), str(dates.max().date())],
        "split": {"train": int(len(tr)), "holdout": int(len(ho))},
        "direction":   dir_metrics,
        "magnitude":   mag_metrics,
        "hit_net":     hit_metrics,
        "top_features": top_feat,
    }


def main():
    print(f"[train-hist] loading {BACKFILL}")
    df = _load_backfill()
    print(f"[train-hist] rows: {len(df)} · tickers: {df['ticker'].nunique()}")

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_count": len(FEATURE_COLS),
        "feature_cols":  FEATURE_COLS,
        "modes": {},
    }

    for mode in MODES:
        report["modes"][mode] = train_mode(df, mode)

    # Roll into the legacy calibration_report.json shape for swing so the
    # existing UI keeps working unchanged.
    legacy = {
        "trained_at":   report["trained_at"],
        "n_total":      report["modes"]["swing"]["n_total"],
        "date_range":   report["modes"]["swing"]["date_range"],
        "feature_count":report["feature_count"],
        "split":        report["modes"]["swing"]["split"],
        "direction":    report["modes"]["swing"]["direction"],
        "magnitude":    report["modes"]["swing"]["magnitude"],
        "hit_net":      report["modes"]["swing"]["hit_net"],
        "top_features": report["modes"]["swing"]["top_features"],
        "calibration_health": "ok" if report["modes"]["swing"]["direction"]["accuracy"] > 0.40 else "warn",
        "preliminary":  False,
        "source":       "historical_backfill",
        "_modes":       {k: {"direction": v["direction"], "hit_net": v["hit_net"], "magnitude": v["magnitude"]}
                         for k, v in report["modes"].items()},
    }
    with open(os.path.join(ART_DIR, "calibration_report.json"), "w") as f:
        json.dump(legacy, f, indent=2)
    with open(os.path.join(ART_DIR, "calibration_report_historical.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[train-hist] artifacts written to {ART_DIR}")
    print(f"[train-hist] modes: {list(report['modes'].keys())}")


if __name__ == "__main__":
    main()
