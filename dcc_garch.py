"""
V-8: DCC-GARCH(1,1) Portfolio Covariance

Engle (2002) Dynamic Conditional Correlation model:
  1. Fit univariate GARCH(1,1) per ticker → standardized residuals ε_t
  2. DCC layer: Q_t = (1-α-β)·Q̄ + α·ε_{t-1}·ε_{t-1}' + β·Q_{t-1}
  3. Correlation matrix: R_t = diag(Q_t)^{-1/2} · Q_t · diag(Q_t)^{-1/2}

The result is a TIME-VARYING correlation matrix that updates daily — captures
"correlations spike toward 1 during crashes" without static assumptions.

This MVP uses a quasi-MLE estimator for DCC parameters (α, β). The full
multi-stage MLE is in some statsmodels but DCC-specific code is custom here.

Used by build_data.py: compute portfolio covariance for current open positions
+ BUY candidates → enables proper risk-aware portfolio construction.
"""
from __future__ import annotations
import numpy as np
from typing import Optional
import warnings


def _univariate_garch_residuals(returns: np.ndarray) -> Optional[np.ndarray]:
    """Fit GARCH(1,1) and return standardized residuals."""
    try:
        from arch import arch_model
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            am = arch_model(returns * 100, mean="zero", vol="GARCH", p=1, q=1, dist="normal")
            res = am.fit(disp="off", show_warning=False)
        cond_vol = res.conditional_volatility / 100  # back to decimal
        return returns / np.where(cond_vol > 1e-8, cond_vol, 1.0)
    except Exception:
        return None


def _dcc_log_likelihood(params, eps_matrix: np.ndarray) -> float:
    """DCC Engle log-likelihood (negated for minimization)."""
    alpha, beta = params
    if alpha < 0 or beta < 0 or alpha + beta >= 0.999:
        return 1e10
    T_obs, n = eps_matrix.shape
    Q_bar = np.cov(eps_matrix.T)
    if Q_bar.shape == ():
        return 1e10
    Q = Q_bar.copy()
    log_lik = 0.0
    for t in range(T_obs):
        if t > 0:
            eps_prev = eps_matrix[t-1].reshape(-1, 1)
            Q = (1 - alpha - beta) * Q_bar + alpha * (eps_prev @ eps_prev.T) + beta * Q
        d_inv_sqrt = np.diag(1.0 / np.sqrt(np.diag(Q)))
        R = d_inv_sqrt @ Q @ d_inv_sqrt
        eps_t = eps_matrix[t]
        try:
            sign, logdet = np.linalg.slogdet(R)
            if sign <= 0: return 1e10
            R_inv = np.linalg.inv(R)
            log_lik -= 0.5 * (logdet + eps_t @ R_inv @ eps_t)
        except np.linalg.LinAlgError:
            return 1e10
    return -log_lik


def fit_dcc_garch(returns_df, max_tickers: int = 12) -> dict:
    """
    Fit DCC-GARCH on a returns DataFrame.

    Args:
      returns_df: DataFrame, columns = tickers, rows = dates, values = daily returns
      max_tickers: cap to keep optimization tractable (full DCC scales poorly)

    Returns:
      {
        tickers: [str],
        n_obs: int,
        Q_bar: list-of-lists (unconditional correlation),
        R_t: list-of-lists (current dynamic correlation, last day),
        alpha, beta: DCC parameters,
        avg_corr: mean off-diagonal correlation,
        max_corr_pair: ("AAA", "BBB", 0.95),
      }
    """
    import scipy.optimize as opt

    out = {"tickers": [], "n_obs": 0}
    if returns_df is None or len(returns_df.columns) < 2:
        out["error"] = "need ≥2 tickers"
        return out

    # Cap tickers
    tickers = list(returns_df.columns)[:max_tickers]
    rdf = returns_df[tickers].dropna()
    if len(rdf) < 60:
        out["error"] = f"need ≥60 obs, got {len(rdf)}"
        return out

    # Get standardized residuals from per-ticker GARCH(1,1)
    eps_cols = []
    used_tickers = []
    for t in tickers:
        rets = rdf[t].values
        eps = _univariate_garch_residuals(rets)
        if eps is not None and not np.any(np.isnan(eps)):
            eps_cols.append(eps)
            used_tickers.append(t)

    if len(eps_cols) < 2:
        out["error"] = "GARCH fit failed for too many tickers"
        return out

    eps_matrix = np.array(eps_cols).T  # (T, n)
    n_obs, n = eps_matrix.shape

    # Optimize DCC (α, β)
    try:
        res = opt.minimize(
            _dcc_log_likelihood, x0=[0.05, 0.92],
            args=(eps_matrix,),
            bounds=[(0.001, 0.5), (0.5, 0.999)],
            method="L-BFGS-B",
        )
        alpha, beta = float(res.x[0]), float(res.x[1])
    except Exception:
        alpha, beta = 0.05, 0.92  # standard DCC defaults

    # Compute current dynamic correlation matrix
    Q_bar = np.cov(eps_matrix.T)
    Q = Q_bar.copy()
    for t in range(n_obs):
        if t > 0:
            eps_prev = eps_matrix[t-1].reshape(-1, 1)
            Q = (1 - alpha - beta) * Q_bar + alpha * (eps_prev @ eps_prev.T) + beta * Q

    d_inv_sqrt = np.diag(1.0 / np.sqrt(np.diag(Q)))
    R_t = d_inv_sqrt @ Q @ d_inv_sqrt
    R_bar = np.diag(1.0 / np.sqrt(np.diag(Q_bar))) @ Q_bar @ np.diag(1.0 / np.sqrt(np.diag(Q_bar)))

    # Stats
    off_diag_idx = np.where(~np.eye(n, dtype=bool))
    off_diag_corrs = R_t[off_diag_idx]
    avg_corr = float(np.mean(np.abs(off_diag_corrs)))
    avg_corr_static = float(np.mean(np.abs(R_bar[off_diag_idx])))

    # Max correlated pair
    max_pair_idx = np.unravel_index(np.argmax(np.abs(R_t - np.eye(n))), R_t.shape)
    i, j = max_pair_idx
    max_pair = (used_tickers[i], used_tickers[j], round(float(R_t[i, j]), 3))

    return {
        "tickers":       used_tickers,
        "n_obs":         n_obs,
        "alpha":         round(alpha, 4),
        "beta":          round(beta, 4),
        "persistence":   round(alpha + beta, 4),
        "R_t":           [[round(float(R_t[i, j]), 3) for j in range(n)] for i in range(n)],
        "R_bar":         [[round(float(R_bar[i, j]), 3) for j in range(n)] for i in range(n)],
        "avg_corr_now":  round(avg_corr, 3),
        "avg_corr_static": round(avg_corr_static, 3),
        "corr_spike":    round(avg_corr - avg_corr_static, 3),
        "max_corr_pair": max_pair,
        "method":        "engle_dcc_garch_v1",
    }


if __name__ == "__main__":
    import pandas as pd
    np.random.seed(42)
    # Synthetic 3-asset returns with time-varying correlation
    n = 250
    base = np.random.normal(0, 0.012, (n, 3))
    # Inject correlation spike in last 50 days
    spike = np.random.normal(0, 0.018, (50, 1))
    base[-50:, 0] += spike[:, 0] * 0.7
    base[-50:, 1] += spike[:, 0] * 0.6
    base[-50:, 2] += spike[:, 0] * 0.5
    df = pd.DataFrame(base, columns=["AAA", "BBB", "CCC"])
    r = fit_dcc_garch(df)
    import json
    print(json.dumps({k: v for k, v in r.items() if k not in ("R_t", "R_bar")}, indent=2))
    print(f"R_t (current):\n{np.array(r.get('R_t', []))}")
    print(f"R_bar (static):\n{np.array(r.get('R_bar', []))}")
