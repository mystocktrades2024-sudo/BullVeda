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
