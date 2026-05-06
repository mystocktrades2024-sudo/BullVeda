"""
V-11: CVaR-Constrained Portfolio Optimizer (Rockafellar-Uryasev LP)

Given N candidate trades with simulated forward returns (from V-1 Monte Carlo),
find weights {w_i} that maximize expected return subject to:
  - CVaR-α(portfolio) ≤ CVaR_budget
  - sum(w_i) ≤ max_gross_exposure
  - 0 ≤ w_i ≤ max_per_position
  - sector concentration cap

Rockafellar-Uryasev (2000) reformulation makes CVaR a tractable LP:
  CVaR_α(L) = min_{ζ} {ζ + (1/((1-α) * S)) * sum_s max(0, L_s - ζ)}

where L_s is portfolio loss in scenario s.

Used for portfolio construction when you have N candidate trades and need
to pick the optimal subset + weights — replaces eyeball heuristics like
"max 5 positions, equal weight."
"""
from __future__ import annotations
import numpy as np
from typing import Optional


def optimize_cvar_portfolio(
    expected_returns: np.ndarray,
    return_scenarios: np.ndarray,
    sectors: Optional[list] = None,
    alpha: float = 0.95,
    cvar_budget_pct: float = 5.0,
    max_gross: float = 0.80,
    max_per_position: float = 0.10,
    max_per_sector: float = 0.30,
    long_only: bool = True,
) -> dict:
    """
    Args:
      expected_returns: (N,) — expected return per candidate (decimal)
      return_scenarios: (S, N) — Monte Carlo or historical return scenarios per asset
      sectors: list of sector labels per asset (for concentration cap)
      alpha: CVaR confidence level (0.95 = worst 5% tail)
      cvar_budget_pct: max acceptable CVaR loss (decimal *100)
      max_gross: max sum of position weights (e.g. 0.80 = 80% of capital deployed)
      max_per_position: max single-position weight
      max_per_sector: max sector concentration

    Returns:
      {
        weights: optimal weights per asset
        expected_return_pct: portfolio E[R]
        cvar_pct: portfolio CVaR_α
        var_pct: portfolio VaR_α
        gross_exposure_pct: sum of weights
        n_positions: number of non-zero positions
        status: cvxpy solver status
      }
    """
    import cvxpy as cp

    out = {}
    N = len(expected_returns)
    if N < 1:
        out["error"] = "no candidates"; return out
    S = return_scenarios.shape[0]
    if return_scenarios.shape[1] != N:
        out["error"] = f"shape mismatch: scenarios {return_scenarios.shape}, expected_ret ({N},)"
        return out

    cvar_budget = cvar_budget_pct / 100.0

    # Decision variables
    w = cp.Variable(N, nonneg=long_only)
    zeta = cp.Variable()  # VaR auxiliary
    u = cp.Variable(S, nonneg=True)  # excess loss aux

    # Portfolio loss in each scenario: -w' · r_s (loss = negative return)
    # Excess loss above VaR: u_s ≥ -w'r_s - ζ
    losses = -return_scenarios @ w  # (S,) — vector of portfolio losses
    constraints = [
        u >= losses - zeta,
        cp.sum(w) <= max_gross,
        w <= max_per_position,
    ]
    if not long_only:
        constraints.append(w >= -max_per_position)

    # Sector concentration
    if sectors and len(sectors) == N:
        sector_set = set(sectors)
        for sec in sector_set:
            mask = np.array([1 if s == sec else 0 for s in sectors])
            constraints.append(mask @ w <= max_per_sector)

    # CVaR budget: ζ + (1/((1-α)·S)) · sum(u_s) ≤ cvar_budget
    cvar_expr = zeta + (1.0 / ((1 - alpha) * S)) * cp.sum(u)
    constraints.append(cvar_expr <= cvar_budget)

    # Maximize expected return: w' · μ
    objective = cp.Maximize(expected_returns @ w)
    prob = cp.Problem(objective, constraints)

    try:
        prob.solve(solver="CLARABEL", verbose=False)
    except Exception:
        try:
            prob.solve(solver="SCS", verbose=False)
        except Exception as e:
            out["error"] = f"all solvers failed: {e}"
            return out

    if prob.status not in ("optimal", "optimal_inaccurate"):
        out["error"] = f"infeasible or solver failure: {prob.status}"
        return out

    weights = np.array(w.value).flatten()
    weights[weights < 1e-5] = 0.0  # threshold tiny weights

    portfolio_return = float(np.dot(expected_returns, weights))
    portfolio_losses = -return_scenarios @ weights
    sorted_losses = np.sort(portfolio_losses)
    var_idx = int(np.ceil(alpha * S)) - 1
    var_val = float(sorted_losses[var_idx]) if var_idx >= 0 else 0.0
    cvar_tail = sorted_losses[var_idx:] if var_idx < S else sorted_losses[-1:]
    cvar_val = float(np.mean(cvar_tail))

    return {
        "weights":           [round(float(x), 4) for x in weights],
        "n_positions":       int(np.sum(weights > 0.0001)),
        "expected_return_pct": round(portfolio_return * 100, 2),
        "var_pct":           round(var_val * 100, 2),
        "cvar_pct":          round(cvar_val * 100, 2),
        "gross_exposure_pct": round(float(np.sum(weights)) * 100, 2),
        "status":            prob.status,
        "method":            "rockafellar_uryasev_lp_v1",
    }


if __name__ == "__main__":
    np.random.seed(42)
    N = 8
    S = 500
    expected_rets = np.array([0.05, 0.08, 0.03, 0.12, 0.06, 0.04, 0.09, 0.07])
    # Synthetic scenarios with mixed correlations
    base = np.random.normal(0, 0.10, (S, N))
    # Inject some correlation
    factor = np.random.normal(0, 0.05, (S, 1))
    scenarios = base + factor + expected_rets / 252  # tiny daily drift
    sectors = ["tech", "tech", "energy", "tech", "fin", "fin", "energy", "consumer"]

    r = optimize_cvar_portfolio(expected_rets, scenarios, sectors=sectors)
    import json
    print(json.dumps(r, indent=2))
