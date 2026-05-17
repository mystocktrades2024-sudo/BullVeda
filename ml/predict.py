"""Inference for the 3-headed ML Edge model · mode-aware (swing/position/invest).

Each mode has its own model triple (direction / magnitude / hit-net) trained on
the matching forward-return horizon from cache/ml/historical_backfill.json.
Live features come from `ml.feature_extractor.extract_for_ticker` which computes
the same 17-feature row off EODHD bars.

Legacy callers (the pre-v2 predict_one(ticker_dict) interface) still work — they
fall through to mode='swing' and re-use the historical model. The old categorical
features (regime4 / setup_family / catalyst_tier / etc.) are no longer used."""
from __future__ import annotations
import json
import math
import os
from typing import Any
import joblib
import numpy as np
import pandas as pd

from ml.feature_extractor import FEATURE_COLS as RAW_FEATURE_COLS, extract_for_ticker
from ml.historical_backfill import FEATURE_COLS, PCTRANK_BASE_COLS, PCTRANK_COLS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "cache", "ml")

MODES = ("swing", "position", "invest")

# horizon → display label (matches kairos UI mode pills)
MODE_LABEL = {"swing": "5-day swing", "position": "21-day position", "invest": "126-day invest"}
MODE_DAYS  = {"swing": 5, "position": 21, "invest": 126}

# in-process cache so a single run_ml_edge invocation doesn't reload pkls 178×
_models_cache: dict[str, Any] = {}


def _load(mode: str):
    key = f"models_{mode}"
    if key in _models_cache:
        return _models_cache[key]
    try:
        dir_m = joblib.load(os.path.join(ART_DIR, f"{mode}_direction.pkl"))
        mag_m = joblib.load(os.path.join(ART_DIR, f"{mode}_magnitude.pkl"))
        hit_m = joblib.load(os.path.join(ART_DIR, f"{mode}_hit_net.pkl"))
    except FileNotFoundError as e:
        # Model missing for this mode — caller should fall back to Brownian projection
        _models_cache[key] = None
        return None
    _models_cache[key] = {"dir": dir_m, "mag": mag_m, "hit": hit_m}
    return _models_cache[key]


def _load_report() -> dict:
    if "report" in _models_cache:
        return _models_cache["report"]
    path = os.path.join(ART_DIR, "calibration_report_historical.json")
    if os.path.exists(path):
        _models_cache["report"] = json.load(open(path))
    else:
        legacy = os.path.join(ART_DIR, "calibration_report.json")
        _models_cache["report"] = json.load(open(legacy)) if os.path.exists(legacy) else {}
    return _models_cache["report"]


# ── Verdict construction ────────────────────────────────────────────────────

def _verdict_label(p_up: float, p_dn: float, edge: float) -> tuple[str, str, str]:
    if p_up >= 0.55 and edge >= 0.35:
        return "BULLISH · STRONG", "STRONG", "pass"
    if p_up >= 0.45:
        return "BULLISH", "MODERATE", "pass"
    if p_dn >= 0.55 and edge <= -0.35:
        return "BEARISH · STRONG", "STRONG", "fail"
    if p_dn >= 0.45:
        return "BEARISH", "MODERATE", "fail"
    return "NEUTRAL", "LOW", "warn"


def _confluences(payload: dict, ticker: dict) -> list[str]:
    out = []
    dir_p = payload["direction"]
    if dir_p["p_up"] >= 0.55: out.append(f"P(up) {int(dir_p['p_up']*100)}%")
    if dir_p["p_dn"] >= 0.55: out.append(f"P(dn) {int(dir_p['p_dn']*100)}%")
    hit = payload.get("hit_net")
    if hit and hit.get("p_t1_first") and hit["p_t1_first"] >= 0.55:
        out.append(f"P(target first) {int(hit['p_t1_first']*100)}%")
    skew = payload["magnitude"]["skew"]
    if skew > 0.30:  out.append(f"Skew +{skew:.2f}")
    if skew < -0.30: out.append(f"Skew {skew:.2f}")
    setup = ticker.get("setup_family") or ticker.get("setup_type")
    if setup and setup not in ("", "unknown", "Mixed"):
        out.append(setup)
    eq = ticker.get("entry_quality")
    if eq in ("FRESH", "PULLBACK"):
        out.append(eq)
    return out[:8]


_shap_explainer_cache: dict[str, Any] = {}


def _get_explainer(model, X_row: np.ndarray):
    """Cache TreeExplainer per underlying base estimator id() since the
    explainer is expensive to build."""
    base = None
    if hasattr(model, "calibrated_classifiers_") and model.calibrated_classifiers_:
        base = model.calibrated_classifiers_[0].estimator
    elif hasattr(model, "estimator"):
        base = model.estimator
    if base is None:
        return None
    key = str(id(base))
    if key in _shap_explainer_cache:
        return _shap_explainer_cache[key]
    try:
        import shap
        # HistGradientBoosting is supported by TreeExplainer in shap 0.49+
        explainer = shap.TreeExplainer(base)
        _shap_explainer_cache[key] = explainer
        return explainer
    except Exception:
        _shap_explainer_cache[key] = None
        return None


def _shap_topk(model, X_row: np.ndarray, columns: list[str], k: int = 5) -> list[dict]:
    """Real SHAP via shap.TreeExplainer when available; falls back to
    feature_importance × sign(value) proxy if shap can't load the model."""
    try:
        explainer = _get_explainer(model, X_row)
        if explainer is not None:
            # shap_values shape:
            #  - binary classifier: (n_samples, n_features)
            #  - multiclass classifier: (n_samples, n_features, n_classes)
            X_2d = X_row.reshape(1, -1)
            sv = explainer.shap_values(X_2d, check_additivity=False)
            if isinstance(sv, list):  # legacy list-of-arrays
                # For multiclass, take the "up" class (class index 2 for direction; 1 for hit)
                idx = -1 if len(sv) >= 2 else 0
                arr = sv[idx][0]
            else:
                arr = np.asarray(sv)
                if arr.ndim == 3:  # (1, n_features, n_classes)
                    arr = arr[0, :, -1]
                elif arr.ndim == 2:  # (1, n_features)
                    arr = arr[0]
            contribs = [{"feature": columns[i], "shap": float(arr[i])} for i in range(len(columns))]
            contribs.sort(key=lambda d: -abs(d["shap"]))
            return contribs[:k]
    except Exception:
        pass
    # Fallback proxy — used if shap not installed or model not tree-explorable
    try:
        base = None
        if hasattr(model, "calibrated_classifiers_") and model.calibrated_classifiers_:
            base = model.calibrated_classifiers_[0].estimator
        elif hasattr(model, "estimator"):
            base = model.estimator
        if base is None or not hasattr(base, "feature_importances_"):
            return []
        importance = base.feature_importances_
        contribs = []
        for i, col in enumerate(columns):
            val = float(X_row[i])
            imp = float(importance[i])
            if imp == 0 or val == 0:
                continue
            sign = 1.0 if val > 0 else -1.0
            contribs.append({"feature": col, "shap": sign * imp * (abs(val) + 0.5)})
        contribs.sort(key=lambda d: -abs(d["shap"]))
        return contribs[:k]
    except Exception:
        return []


# ── Core prediction ─────────────────────────────────────────────────────────

def predict_with_features(features: dict, mode: str = "swing", ticker: dict | None = None) -> dict | None:
    """Pass pre-extracted features (RAW + cross-sectional pctrank) directly.
    Returns ml_edge payload or None if the mode's model triple is missing.

    `features` must include both the 17 raw features AND the 12 pctrank_* features
    that the v3 model expects. The orchestrator `ml.run_ml_edge` computes pctranks
    universe-wide before calling this per-ticker."""
    models = _load(mode)
    if models is None:
        return None
    report = _load_report()
    cols = FEATURE_COLS
    row = np.array([features.get(c, 0.0) for c in cols], dtype=float)
    X = pd.DataFrame([row], columns=cols)

    # Direction head — 3-class
    p_dir = models["dir"].predict_proba(X)[0]
    cls = list(getattr(models["dir"], "classes_", [0, 1, 2]))
    p_map = {int(c): float(p_dir[i]) for i, c in enumerate(cls)}
    p_dn, p_chop, p_up = p_map.get(0, 0.0), p_map.get(1, 0.0), p_map.get(2, 0.0)
    edge_dir = p_up - p_dn

    # Magnitude head — 5 quantile predictions
    quantiles = {q: float(models["mag"][q].predict(X)[0]) for q in models["mag"]}
    quantiles_pct = {q: v * 100 for q, v in quantiles.items()}
    q50 = quantiles_pct[0.5]
    upper = quantiles_pct[0.9] - q50
    lower = q50 - quantiles_pct[0.1]
    denom = upper + lower
    skew = (upper - lower) / denom if denom > 0 else 0.0

    # Hit-Net — threshold-conditional. Compute target_thr_pct from the trade
    # plan's T1 distance when available; otherwise use a mode-specific default.
    # `entry` and `t1` can be dicts in canonical_trade_plan (low/high band) —
    # coerce to a single mid-price float.
    def _num(x):
        if isinstance(x, dict):
            for k in ("mid", "price", "value", "low", "high"):
                if k in x and isinstance(x[k], (int, float)):
                    return float(x[k])
            return 0.0
        try:
            return float(x) if x not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    ticker = ticker or {}
    plan = ticker.get("canonical_trade_plan") or ticker.get("trade_plan") or {}
    entry = _num(plan.get("entry") or plan.get("entry_price") or ticker.get("price"))
    t1    = _num(plan.get("t1") or plan.get("target1"))
    if entry > 0 and t1 > 0 and t1 > entry:
        target_thr_pct = (t1 - entry) / entry * 100
    else:
        target_thr_pct = {"swing": 3.0, "position": 6.0, "invest": 15.0}[mode]
    X_hit = X.copy()
    X_hit["target_thr_pct"] = target_thr_pct
    p_t1 = float(models["hit"].predict_proba(X_hit)[0, 1])
    hit_metrics = (report.get("modes", {}) or {}).get(mode, {}).get("hit_net", {})
    hit_payload = {
        "p_t1_first":     p_t1,
        "p_stop_first":   1.0 - p_t1,
        "target_thr_pct": target_thr_pct,
        "conditional":    True,
        "model_auc":      hit_metrics.get("auc"),
        "model_n":        hit_metrics.get("n_holdout"),
    }

    verdict_text, level, color = _verdict_label(p_up, p_dn, edge_dir)
    edge_10 = round(min(10, max(0, 5 + edge_dir * 5)), 1)

    mode_metrics = (report.get("modes", {}) or {}).get(mode, {})
    payload = {
        "mode": mode,
        "mode_label":   MODE_LABEL[mode],
        "horizon_days": MODE_DAYS[mode],
        "verdict": {
            "text":       verdict_text,
            "level":      level,
            "color":      color,
            "edge":       edge_10,
            "confidence": "HIGH" if abs(edge_dir) > 0.40 else ("MED" if abs(edge_dir) > 0.20 else "LOW"),
        },
        "direction": {"p_up": p_up, "p_chop": p_chop, "p_dn": p_dn, "edge": edge_dir},
        "magnitude": {
            "q10": quantiles_pct[0.1], "q25": quantiles_pct[0.25], "q50": q50,
            "q75": quantiles_pct[0.75], "q90": quantiles_pct[0.9], "skew": skew,
        },
        "hit_net": hit_payload,
        "shap": {"dir_top": _shap_topk(models["dir"], row, cols)},
        "model_meta": {
            "trained_at":  report.get("trained_at"),
            "n_total":     mode_metrics.get("n_total") or report.get("n_total"),
            "preliminary": False,
            "calibration_health": "ok" if mode_metrics.get("direction", {}).get("accuracy", 0) > 0.40 else "warn",
            "feature_cols": cols,
            "source":       "historical",
            "mode_metrics": mode_metrics,
        },
    }
    payload["verdict"]["confluences"] = _confluences(payload, ticker or {})
    return payload


def predict_one(ticker: dict, mode: str = "swing") -> dict | None:
    """Legacy-compatible entry — extracts features from EODHD bars for the ticker,
    then calls predict_with_features. Returns None if features unavailable."""
    sym = (ticker.get("ticker") or ticker.get("symbol") or "").upper()
    if not sym:
        return None
    feats = extract_for_ticker(sym)
    if feats is None:
        return None
    return predict_with_features(feats, mode=mode, ticker=ticker)


def predict_many(tickers: list[dict], mode: str = "swing") -> dict[str, dict]:
    out = {}
    for t in tickers:
        sym = (t.get("ticker") or t.get("symbol") or "").upper().strip()
        if not sym:
            continue
        try:
            p = predict_one(t, mode=mode)
            if p is not None:
                out[sym] = p
            else:
                out[sym] = {"error": "features unavailable"}
        except Exception as e:
            out[sym] = {"error": str(e)}
    return out


if __name__ == "__main__":
    sample = {"ticker": "ROST"}
    for m in MODES:
        p = predict_one(sample, mode=m)
        if p is None:
            print(f"[{m}] no model or features"); continue
        d, mg, h = p["direction"], p["magnitude"], p["hit_net"]
        print(f"[{m}] verdict={p['verdict']['text']:22s}  P(up)={d['p_up']:.2f}  P(dn)={d['p_dn']:.2f}  "
              f"q50={mg['q50']:+.2f}%  q90={mg['q90']:+.2f}%  P(hit)={h['p_t1_first']:.2f}")
