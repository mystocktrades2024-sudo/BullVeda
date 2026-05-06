"""
V-1: Monte Carlo Path Simulator (Merton Jump-Diffusion)

Simulates forward price paths using:
  dS/S = μ dt + σ dW + (Y-1) dN

where dN is a Poisson process with rate λ, and log(Y) ~ N(μ_J, σ_J²).

Inputs: μ (drift), σ (vol), S₀, T (days), n_paths
Optional jumps: λ (annual rate), μ_J (mean log-jump), σ_J (jump vol)

Returns:
  - paths: (n_paths, T+1) array of simulated price paths
  - terminal: (n_paths,) array of S_T values
  - distribution_metrics: VaR-95, CVaR-97.5, P50, P25, P75, P(profit > 0),
    P(hit T1), P(hit stop), forward_sharpe

Numba-JIT compiled for speed: ~3K paths × 63d × 200 tickers = ~5s on M-class CPU.
"""
from __future__ import annotations
import numpy as np
from numba import njit
from typing import Optional


@njit(cache=True)
def _simulate_paths_jit(S0: float, mu: float, sigma: float,
                         T: int, n_paths: int,
                         lambda_jump: float = 0.0,
                         mu_jump: float = 0.0, sigma_jump: float = 0.0,
                         seed: int = 0) -> np.ndarray:
    """
    Numba-jitted GBM with Merton jumps. Returns (n_paths, T+1) array.

    Time-step is 1 day (1/252 of a year for annualized μ/σ).
    Jumps fire as Bernoulli(λ/252) per day; size ~ LogNormal(μ_J, σ_J²).
    """
    np.random.seed(seed)
    dt = 1.0 / 252.0
    sqrt_dt = np.sqrt(dt)
    paths = np.empty((n_paths, T + 1), dtype=np.float64)
    paths[:, 0] = S0

    drift = (mu - 0.5 * sigma * sigma) * dt
    daily_jump_p = lambda_jump * dt

    for p in range(n_paths):
        s = S0
        for t in range(1, T + 1):
            z = np.random.standard_normal()
            log_step = drift + sigma * sqrt_dt * z
            # Jump? Bernoulli per day
            if daily_jump_p > 0 and np.random.random() < daily_jump_p:
                jz = np.random.standard_normal()
                jump_log = mu_jump + sigma_jump * jz
                log_step += jump_log
            s = s * np.exp(log_step)
            paths[p, t] = s
    return paths


def simulate(S0: float, mu_annual: float, sigma_annual: float,
             T: int = 63, n_paths: int = 3000,
             lambda_jump: float = 0.0,
             mu_jump: float = 0.0, sigma_jump: float = 0.0,
             seed: Optional[int] = None) -> dict:
    """
    Run a Monte Carlo simulation and compute distribution metrics.

    Args:
      S0: starting price
      mu_annual: annualized drift (e.g. 0.10 for +10%)
      sigma_annual: annualized volatility (e.g. 0.30 for 30%)
      T: forecast horizon in trading days (63 ≈ 3 months)
      n_paths: number of paths
      lambda_jump: annual jump intensity (0 = no jumps)
      mu_jump, sigma_jump: log-jump parameters
      seed: rng seed (random if None)

    Returns dict with:
      stats: {p5, p25, p50, p75, p95, mean, std}
      probs: {p_profit, p_hit_target_pct, p_hit_stop_pct}
      terminal: numpy array of S_T (n_paths,)
      paths: (n_paths, T+1) — included only if return_paths=True
      summary: dict suitable for JSON
    """
    if seed is None:
        seed = int(np.random.randint(0, 2**31 - 1))

    paths = _simulate_paths_jit(S0, mu_annual, sigma_annual, T, n_paths,
                                  lambda_jump, mu_jump, sigma_jump, seed)
    terminal = paths[:, -1]
    rets = (terminal - S0) / S0

    pct = lambda q: float(np.percentile(rets, q))
    var_95 = pct(5)
    cvar_975 = float(rets[rets <= np.percentile(rets, 2.5)].mean()) if len(rets[rets <= np.percentile(rets, 2.5)]) else var_95

    p50 = pct(50); p25 = pct(25); p75 = pct(75); p5 = var_95; p95 = pct(95)
    mean_r = float(rets.mean()); std_r = float(rets.std(ddof=1))
    p_profit = float((rets > 0).mean())

    # Approximate annualized Sharpe at this horizon
    annualization = np.sqrt(252.0 / T)
    fwd_sharpe = (mean_r / std_r * annualization) if std_r > 0 else None

    return {
        "S0": S0, "T": T, "n_paths": n_paths,
        "mu_annual": mu_annual, "sigma_annual": sigma_annual,
        "lambda_jump": lambda_jump, "mu_jump": mu_jump, "sigma_jump": sigma_jump,
        "stats": {
            "p5_pct":    round(p5 * 100, 2),
            "p25_pct":   round(p25 * 100, 2),
            "p50_pct":   round(p50 * 100, 2),
            "p75_pct":   round(p75 * 100, 2),
            "p95_pct":   round(p95 * 100, 2),
            "mean_pct":  round(mean_r * 100, 2),
            "std_pct":   round(std_r * 100, 2),
        },
        "var_95_pct":     round(var_95 * 100, 2),
        "cvar_975_pct":   round(cvar_975 * 100, 2),
        "p_profit":       round(p_profit * 100, 1),
        "fwd_sharpe":     round(fwd_sharpe, 2) if fwd_sharpe is not None else None,
        "min_terminal_pct":  round(float(rets.min()) * 100, 2),
        "max_terminal_pct":  round(float(rets.max()) * 100, 2),
        "method":         "merton_jump_diffusion_numba_v1",
        "seed":           seed,
    }


def simulate_with_target_stop(S0: float, mu_annual: float, sigma_annual: float,
                                target: float, stop: float,
                                T: int = 63, n_paths: int = 3000,
                                lambda_jump: float = 0.0,
                                mu_jump: float = 0.0, sigma_jump: float = 0.0,
                                seed: Optional[int] = None) -> dict:
    """
    Simulate paths and compute P(hit target before stop), P(hit stop before target).
    Important for trade plan evaluation — what's actually likely to happen.
    """
    if seed is None:
        seed = int(np.random.randint(0, 2**31 - 1))
    paths = _simulate_paths_jit(S0, mu_annual, sigma_annual, T, n_paths,
                                  lambda_jump, mu_jump, sigma_jump, seed)

    n_target_first = 0
    n_stop_first   = 0
    n_neither      = 0
    for p in range(n_paths):
        path = paths[p]
        target_hit_idx = -1
        stop_hit_idx   = -1
        for t in range(1, len(path)):
            if path[t] >= target and target_hit_idx == -1:
                target_hit_idx = t
                break
            if path[t] <= stop and stop_hit_idx == -1:
                stop_hit_idx = t
                break
        if target_hit_idx > -1: n_target_first += 1
        elif stop_hit_idx > -1: n_stop_first += 1
        else: n_neither += 1

    base = simulate(S0, mu_annual, sigma_annual, T, n_paths,
                    lambda_jump, mu_jump, sigma_jump, seed)
    base["p_hit_target_first"] = round(n_target_first / n_paths * 100, 1)
    base["p_hit_stop_first"]   = round(n_stop_first / n_paths * 100, 1)
    base["p_neither_hit"]      = round(n_neither / n_paths * 100, 1)
    return base


if __name__ == "__main__":
    # Smoke test
    import time
    S0, mu, sig, T, n_paths = 100.0, 0.10, 0.30, 63, 3000
    t = time.time()
    r = simulate(S0, mu, sig, T=T, n_paths=n_paths, lambda_jump=2.0, mu_jump=-0.05, sigma_jump=0.10)
    elapsed = time.time() - t
    import json
    print(json.dumps(r, indent=2))
    print(f"\nElapsed: {elapsed*1000:.1f}ms")

    # Test with target/stop
    print("\nWith target $115, stop $95:")
    r2 = simulate_with_target_stop(S0, mu, sig, target=115, stop=95,
                                    T=T, n_paths=n_paths, seed=42)
    print(f"  P(hit target first): {r2['p_hit_target_first']}%")
    print(f"  P(hit stop first):   {r2['p_hit_stop_first']}%")
    print(f"  P(neither):          {r2['p_neither_hit']}%")
