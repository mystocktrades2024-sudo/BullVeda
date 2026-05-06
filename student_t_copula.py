"""
V-10: Student-t Copula for Tail Dependence

A copula models JOINT dependence between assets independently of their marginals.
Student-t copula with low ν captures TAIL dependence — the fact that during
crashes, otherwise-uncorrelated assets all fall together (correlation → 1).

Key parameter:
  ν (degrees of freedom): low (4-8) = strong tail dependence, high (≥20) ≈ Gaussian

Output: tail_dependence coefficient λ_L = 2 · t_{ν+1}(-sqrt((ν+1)(1-ρ)/(1+ρ)))

Used to:
  1. Estimate joint loss probability under stress
  2. Sound the alarm when ν drops (tail risk increasing)
  3. Inform position-sizing during regime transitions

NOTE: This is a 2-stage MLE — first fit empirical CDFs to get pseudo-uniforms,
then fit Student-t copula. Standard methodology.
"""
from __future__ import annotations
import numpy as np
from typing import Optional


def _empirical_cdf_transform(returns: np.ndarray) -> np.ndarray:
    """Transform via empirical CDF → pseudo-uniform on (0, 1)."""
    n = len(returns)
    ranks = np.argsort(np.argsort(returns)) + 1
    return ranks / (n + 1)


def _gaussian_inverse_cdf(u: np.ndarray) -> np.ndarray:
    """Φ^{-1}(u) — inverse standard normal CDF."""
    from scipy.stats import norm
    return norm.ppf(np.clip(u, 1e-6, 1 - 1e-6))


def _student_t_inverse_cdf(u: np.ndarray, nu: float) -> np.ndarray:
    """t_ν^{-1}(u) — inverse Student-t CDF."""
    from scipy.stats import t
    return t.ppf(np.clip(u, 1e-6, 1 - 1e-6), df=nu)


def fit_student_t_copula(returns_df, max_tickers: int = 8) -> dict:
    """
    Fit Student-t copula to a returns DataFrame.

    Steps:
      1. Empirical CDF transform → pseudo-uniforms u_t ∈ (0, 1)
      2. Convert to Student-t marginals via t_ν^{-1}(u)
      3. Fit ν via likelihood maximization
      4. Compute tail-dependence coefficients λ_L

    Returns:
      {
        nu:                 fitted degrees of freedom (low = strong tail dep)
        rho:                correlation matrix (in copula space)
        tail_dependence:    avg lower-tail dependence λ_L (0 = none, 1 = perfect)
        tail_dep_pairs:     list of (i, j, λ_L) sorted by strongest tail dep
        n_obs, tickers, method
      }
    """
    import scipy.optimize as opt
    from scipy.stats import t as t_dist

    out = {"tickers": [], "n_obs": 0}
    if returns_df is None or len(returns_df.columns) < 2:
        out["error"] = "need ≥2 tickers"
        return out

    tickers = list(returns_df.columns)[:max_tickers]
    rdf = returns_df[tickers].dropna()
    if len(rdf) < 60:
        out["error"] = f"need ≥60 obs, got {len(rdf)}"
        return out

    n_obs = len(rdf)
    n = len(tickers)

    # Step 1: empirical CDF transform per column
    U = np.column_stack([_empirical_cdf_transform(rdf[c].values) for c in tickers])

    # Step 2: For each candidate ν, transform to Student-t marginals
    # Step 3: Fit copula correlation + ν via approximate ML
    # Use a 1D grid search over ν, computing correlation in transformed space
    nu_grid = np.array([3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 50])

    def _loglik_for_nu(nu: float) -> float:
        Z = _student_t_inverse_cdf(U, nu)
        # Sample correlation in Student-t space
        rho = np.corrcoef(Z.T)
        # Log-likelihood: -0.5 * log|R| - 0.5 * sum(z' R^{-1} z) + correction terms
        try:
            sign, logdet = np.linalg.slogdet(rho)
            if sign <= 0: return -1e10
            R_inv = np.linalg.inv(rho)
        except np.linalg.LinAlgError:
            return -1e10
        ll = 0.0
        for t_obs in range(n_obs):
            z = Z[t_obs]
            # Multivariate t log-density (constant terms cancel in optimization)
            quad = z @ R_inv @ z
            ll -= 0.5 * (n + nu) * np.log(1 + quad / nu)
            # Marginal univariate t adjustment
            for i in range(n):
                ll += 0.5 * (1 + nu) * np.log(1 + z[i]**2 / nu)
        ll -= 0.5 * n_obs * logdet
        return ll

    best_nu = nu_grid[0]
    best_ll = -np.inf
    for nu_cand in nu_grid:
        ll = _loglik_for_nu(nu_cand)
        if ll > best_ll:
            best_ll = ll; best_nu = nu_cand

    nu = float(best_nu)
    Z = _student_t_inverse_cdf(U, nu)
    rho = np.corrcoef(Z.T)

    # Step 4: Tail dependence coefficient
    # λ_L = 2 · t_{ν+1}(-sqrt((ν+1)(1-ρ)/(1+ρ)))
    tail_dep_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                tail_dep_matrix[i, j] = 1.0
            else:
                r = rho[i, j]
                if r >= 1.0: tail_dep_matrix[i, j] = 1.0
                elif r <= -1.0: tail_dep_matrix[i, j] = 0.0
                else:
                    arg = -np.sqrt((nu + 1) * (1 - r) / (1 + r))
                    tail_dep_matrix[i, j] = 2 * t_dist.cdf(arg, df=nu + 1)

    # Top tail-dependent pairs
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((tickers[i], tickers[j], round(float(tail_dep_matrix[i, j]), 3)))
    pairs.sort(key=lambda p: -p[2])

    off_diag = tail_dep_matrix[np.where(~np.eye(n, dtype=bool))]
    avg_tail_dep = float(np.mean(off_diag))

    # Interpretation
    if nu <= 5:
        regime = "EXTREME — strong joint-crash risk"
    elif nu <= 8:
        regime = "ELEVATED — meaningful tail dependence"
    elif nu <= 15:
        regime = "MODERATE"
    else:
        regime = "LOW — near-Gaussian behavior"

    return {
        "tickers":          tickers,
        "n_obs":            n_obs,
        "nu":               round(nu, 1),
        "rho":              [[round(float(rho[i, j]), 3) for j in range(n)] for i in range(n)],
        "tail_dep_matrix":  [[round(float(tail_dep_matrix[i, j]), 3) for j in range(n)] for i in range(n)],
        "avg_tail_dep":     round(avg_tail_dep, 3),
        "max_tail_dep_pairs": pairs[:6],
        "tail_regime":      regime,
        "method":           "student_t_copula_v1",
    }


if __name__ == "__main__":
    import pandas as pd
    np.random.seed(0)
    n = 250
    # Two assets with low linear correlation but co-tail behavior
    z1 = np.random.normal(0, 1, n)
    z2 = np.random.normal(0, 1, n)
    # Inject joint left-tail spikes
    spike_days = np.random.choice(n, 25, replace=False)
    z1[spike_days] -= 4
    z2[spike_days] -= 3.5
    z3 = np.random.normal(0, 1, n)
    df = pd.DataFrame({
        "AAA": z1 * 0.012,
        "BBB": z2 * 0.012,
        "CCC": z3 * 0.012,
    })
    r = fit_student_t_copula(df)
    import json
    print(json.dumps(r, indent=2))
