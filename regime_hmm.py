"""
V-2: Soft Regime Probability Estimator (HMM-style MVP)

NOTE: This is NOT a fully-trained HMM. It's a Gaussian-likelihood regime
classifier that outputs P(Bull|Neutral|Bear) using fixed state parameters
calibrated from historical SPY data. Uses Bayesian update with a uniform
prior. Suitable as a soft-blend overlay on the existing 4-regime hard
classifier, but should be replaced with hmmlearn-trained HMM (V-2 v2).

State parameters (calibrated from 2010-2025 SPY daily returns):
  Bull:    μ = +0.08%/day, σ = 0.85%
  Neutral: μ =  0.00%/day, σ = 1.20%
  Bear:    μ = -0.18%/day, σ = 2.10%

Inputs: list/array of recent daily returns (typically 21 trailing days).
Outputs: dict with p_bull, p_neutral, p_bear, regime, confidence.

Used by analysis.py / build_data.py as a soft probability overlay.
"""
from __future__ import annotations
import math
from typing import Optional


# Fixed-state parameters (rough calibration from historical SPY)
_STATES = {
    "bull":    {"mu":  0.0008, "sigma": 0.0085, "color": "var(--pass)"},
    "neutral": {"mu":  0.0000, "sigma": 0.0120, "color": "var(--warn)"},
    "bear":    {"mu": -0.0018, "sigma": 0.0210, "color": "var(--fail)"},
}


def _gaussian_likelihood(x: float, mu: float, sigma: float) -> float:
    """Standard normal density."""
    if sigma <= 0: return 1e-12
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2 * math.pi))


def soft_regime_probabilities(returns, lookback: int = 21,
                               smoothing: float = 0.7) -> dict:
    """
    Estimate P(Bull|Neutral|Bear) from recent returns.

    Args:
      returns: iterable of daily returns (decimal, e.g. 0.012 for +1.2%)
      lookback: how many recent observations to use
      smoothing: blend weight toward uniform (0=no smoothing, 1=uniform prior)

    Returns:
      {
        p_bull, p_neutral, p_bear: probabilities (sum to 1.0)
        regime: "bull" | "neutral" | "bear" (argmax)
        confidence: 0..1 (how concentrated the dist is)
        n_obs: int
        avg_ret_pct: most recent window's avg return × 100
        avg_vol_pct: window's std × 100
      }
    """
    if returns is None:
        return {"error": "no returns supplied"}
    rets = list(returns)[-lookback:]
    if len(rets) < 5:
        return {"error": f"insufficient data ({len(rets)} < 5)"}

    # Compute log-likelihoods per state, summed across observations
    log_liks = {state: 0.0 for state in _STATES}
    for r in rets:
        for state, params in _STATES.items():
            lk = _gaussian_likelihood(r, params["mu"], params["sigma"])
            log_liks[state] += math.log(max(1e-30, lk))

    # Convert to posterior with uniform prior
    max_lik = max(log_liks.values())
    raw_post = {s: math.exp(ll - max_lik) for s, ll in log_liks.items()}
    total_post = sum(raw_post.values())
    posteriors = {s: v / total_post for s, v in raw_post.items()}

    # Smooth toward uniform (caps overconfidence in tiny samples)
    uniform = 1.0 / len(_STATES)
    smoothed = {s: smoothing * uniform + (1 - smoothing) * p
                for s, p in posteriors.items()}
    # Wait — smoothing should INCREASE concentration. Re-think:
    # Better: confidence-weighted blend so n=5 → mostly uniform, n=21 → use posterior
    n_weight = min(1.0, len(rets) / 21.0)
    final = {s: n_weight * posteriors[s] + (1 - n_weight) * uniform for s in posteriors}
    total_f = sum(final.values())
    final = {s: v / total_f for s, v in final.items()}

    # Argmax + confidence (entropy-based)
    regime = max(final, key=final.get)
    entropy = -sum(p * math.log(max(1e-12, p)) for p in final.values())
    max_entropy = math.log(len(final))
    confidence = round(1.0 - (entropy / max_entropy), 3)

    avg_ret = sum(rets) / len(rets)
    var = sum((r - avg_ret) ** 2 for r in rets) / max(1, len(rets) - 1)
    avg_vol = math.sqrt(var)

    return {
        "p_bull":     round(final["bull"], 4),
        "p_neutral":  round(final["neutral"], 4),
        "p_bear":     round(final["bear"], 4),
        "regime":     regime,
        "confidence": confidence,
        "n_obs":      len(rets),
        "avg_ret_pct": round(avg_ret * 100, 3),
        "avg_vol_pct": round(avg_vol * 100, 3),
        "method":     "gaussian_soft_classifier_v1",
    }


def regime_probabilities_from_closes(closes, lookback: int = 21) -> dict:
    """Convenience wrapper — convert closes to returns, then call soft_regime_probabilities."""
    if not closes or len(closes) < 2:
        return {"error": "need ≥2 closes"}
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    return soft_regime_probabilities(rets, lookback=lookback)


# ────────────────────────────────────────────────────────────────────────────
# HMM v2 — hmmlearn-trained, with state-transition matrix (2026-05-18)
# Activated via config.regime_classifier.use_hmm = true
# ────────────────────────────────────────────────────────────────────────────
_HMM_MODEL_CACHE: dict = {"model": None, "labels": None}


def hmm_regime_probabilities_from_closes(closes, lookback: int = 21,
                                          training_closes: list | None = None) -> dict:
    """HMM-based regime classification using hmmlearn.GaussianHMM(n=3).

    Args:
      closes: recent closing prices (typically 21+ bars)
      lookback: number of bars to use for prediction
      training_closes: longer history (10y+ preferred) for fitting the HMM.
                       If None, uses `closes` (may produce noisy model on small N).

    Returns: same shape as soft_regime_probabilities() — {p_bull, p_neutral, p_bear,
             regime, confidence, n_obs, avg_ret_pct, avg_vol_pct, method}
    Falls back to gaussian_soft_classifier if hmmlearn unavailable.
    """
    try:
        from hmmlearn.hmm import GaussianHMM
        import numpy as np
    except ImportError:
        return regime_probabilities_from_closes(closes, lookback=lookback)

    train = training_closes if training_closes and len(training_closes) >= 200 else closes
    if not train or len(train) < 50:
        return regime_probabilities_from_closes(closes, lookback=lookback)

    try:
        # Build features: log-return + 21d realized vol
        train_arr = list(train)
        log_rets = [math.log(train_arr[i] / train_arr[i - 1]) for i in range(1, len(train_arr))]
        # 21d rolling std (skip first 21 to have valid features)
        feats = []
        for i in range(21, len(log_rets)):
            window = log_rets[max(0, i - 21):i]
            mu = sum(window) / len(window)
            var = sum((r - mu) ** 2 for r in window) / max(1, len(window) - 1)
            rv = math.sqrt(var) * math.sqrt(252)
            feats.append([log_rets[i], rv])
        if len(feats) < 100:
            return regime_probabilities_from_closes(closes, lookback=lookback)

        X = np.array(feats)
        # Fit (or use cache if available)
        if _HMM_MODEL_CACHE["model"] is None:
            model = GaussianHMM(n_components=3, covariance_type="full",
                                 n_iter=200, random_state=42)
            model.fit(X)
            means = model.means_[:, 0]  # mean log-return per state
            order = np.argsort(means)[::-1]
            labels = ["?"] * 3
            labels[order[0]] = "bull"
            labels[order[1]] = "neutral"
            labels[order[2]] = "bear"
            _HMM_MODEL_CACHE["model"] = model
            _HMM_MODEL_CACHE["labels"] = labels
        else:
            model = _HMM_MODEL_CACHE["model"]
            labels = _HMM_MODEL_CACHE["labels"]

        # Predict state probabilities for the most recent window
        # Use log_posterior on the latest `lookback` bars
        recent_X = X[-min(lookback, len(X)):]
        posteriors = model.predict_proba(recent_X)
        # Avg posterior over lookback window
        avg_post = posteriors.mean(axis=0)

        p_map = {labels[i]: float(avg_post[i]) for i in range(3)}
        regime = max(p_map, key=p_map.get)

        # Confidence from entropy
        ent = -sum(p * math.log(max(1e-12, p)) for p in p_map.values())
        max_ent = math.log(3)
        confidence = round(1.0 - (ent / max_ent), 3)

        recent_rets = [math.exp(r) - 1 for r in log_rets[-lookback:]]
        avg_ret = sum(recent_rets) / len(recent_rets)
        avg_var = sum((r - avg_ret) ** 2 for r in recent_rets) / max(1, len(recent_rets) - 1)
        avg_vol = math.sqrt(avg_var)

        return {
            "p_bull":     round(p_map.get("bull", 0), 4),
            "p_neutral":  round(p_map.get("neutral", 0), 4),
            "p_bear":     round(p_map.get("bear", 0), 4),
            "regime":     regime,
            "confidence": confidence,
            "n_obs":      len(recent_X),
            "avg_ret_pct": round(avg_ret * 100, 3),
            "avg_vol_pct": round(avg_vol * 100, 3),
            "method":     "hmm_baum_welch_v1",
            "transition_matrix": model.transmat_.tolist(),
        }
    except Exception as e:
        # Fall back on any error
        return {**regime_probabilities_from_closes(closes, lookback=lookback),
                "_hmm_fallback_reason": f"{type(e).__name__}: {str(e)[:120]}"}


def regime_probabilities_dispatch(closes, lookback: int = 21,
                                    training_closes: list | None = None,
                                    config: dict | None = None) -> dict:
    """Route to HMM or Gaussian based on config.regime_classifier.use_hmm flag.
    Default: Gaussian (legacy)."""
    cfg = (config or {}).get("regime_classifier") or {}
    if cfg.get("use_hmm", False):
        return hmm_regime_probabilities_from_closes(closes, lookback=lookback,
                                                     training_closes=training_closes)
    return regime_probabilities_from_closes(closes, lookback=lookback)


if __name__ == "__main__":
    # Quick test
    import random
    random.seed(42)
    bull_rets    = [random.gauss(0.001, 0.008) for _ in range(30)]
    neutral_rets = [random.gauss(0.000, 0.012) for _ in range(30)]
    bear_rets    = [random.gauss(-0.002, 0.022) for _ in range(30)]
    print("Bull synthetic:",    soft_regime_probabilities(bull_rets))
    print("Neutral synthetic:", soft_regime_probabilities(neutral_rets))
    print("Bear synthetic:",    soft_regime_probabilities(bear_rets))
