"""
V-3: Forward-Distribution Metrics

Compute distributional risk metrics from historical returns:
  - VaR-95: 5th percentile of forward N-day return distribution
  - CVaR-97.5: average return in worst 2.5% tail
  - P(profit): historical % of N-day windows that ended positive
  - P25 / P50 / P75: quartile forward returns
  - forward_sharpe: mean / std of N-day returns × annualization

NOTE: This is empirical (historical) bootstrapping — NOT Monte Carlo.
It's an MVP that surfaces real distributional risk numbers without
the V-1 GBM/jump-diffusion engine. Future V-1 will replace this with
3,000-path simulation per ticker.

Used by build_data.py to populate per-ticker `forward_dist` field.
"""
from __future__ import annotations
import math
from typing import Optional


def _percentile(sorted_arr, q):
    """Linear-interpolation percentile of sorted array."""
    if not sorted_arr:
        return None
    n = len(sorted_arr)
    if n == 1:
        return sorted_arr[0]
    pos = (n - 1) * q
    floor = int(pos)
    frac = pos - floor
    if floor + 1 < n:
        return sorted_arr[floor] + frac * (sorted_arr[floor + 1] - sorted_arr[floor])
    return sorted_arr[floor]


def forward_distribution_metrics(closes, horizon_days: int = 10,
                                  lookback_windows: int = 250) -> dict:
    """
    Compute forward distribution from historical N-day rolling returns.

    Args:
      closes: list of historical closing prices (oldest → newest)
      horizon_days: forward window length (10 = 2 weeks of trading)
      lookback_windows: max historical N-day windows to sample

    Returns:
      {
        var_95_pct, cvar_975_pct, p_profit, p25_pct, p50_pct, p75_pct,
        mean_pct, std_pct, fwd_sharpe, n_samples, horizon_days
      }
    """
    out = {"horizon_days": horizon_days, "n_samples": 0}
    if not closes or len(closes) < horizon_days + 30:
        out["error"] = f"insufficient history (need ≥{horizon_days + 30}, got {len(closes) if closes else 0})"
        return out

    # Compute all forward N-day returns
    n = len(closes)
    rets = []
    start = max(0, n - lookback_windows - horizon_days)
    for i in range(start, n - horizon_days):
        a, b = closes[i], closes[i + horizon_days]
        if a > 0:
            rets.append((b - a) / a)
    if len(rets) < 20:
        out["error"] = f"only {len(rets)} valid windows"
        return out

    rets_sorted = sorted(rets)
    mean_ret = sum(rets) / len(rets)
    var = sum((r - mean_ret) ** 2 for r in rets) / max(1, len(rets) - 1)
    std_ret = math.sqrt(var)

    # VaR-95: 5th percentile (loss threshold)
    var_95 = _percentile(rets_sorted, 0.05)
    # CVaR-97.5: average of worst 2.5% returns
    n25 = max(1, int(len(rets) * 0.025))
    cvar_975 = sum(rets_sorted[:n25]) / n25 if n25 else None

    # P(profit) — % of windows that finished positive
    p_profit = sum(1 for r in rets if r > 0) / len(rets)

    # Quartiles
    p25 = _percentile(rets_sorted, 0.25)
    p50 = _percentile(rets_sorted, 0.50)
    p75 = _percentile(rets_sorted, 0.75)

    # Forward Sharpe (annualized — assumes daily horizon)
    annualization = math.sqrt(252 / horizon_days)
    fwd_sharpe = (mean_ret / std_ret * annualization) if std_ret > 0 else None

    return {
        "horizon_days":  horizon_days,
        "n_samples":     len(rets),
        "var_95_pct":    round(var_95 * 100, 2) if var_95 is not None else None,
        "cvar_975_pct":  round(cvar_975 * 100, 2) if cvar_975 is not None else None,
        "p_profit":      round(p_profit * 100, 1),
        "p25_pct":       round(p25 * 100, 2) if p25 is not None else None,
        "p50_pct":       round(p50 * 100, 2) if p50 is not None else None,
        "p75_pct":       round(p75 * 100, 2) if p75 is not None else None,
        "mean_pct":      round(mean_ret * 100, 2),
        "std_pct":       round(std_ret * 100, 2),
        "fwd_sharpe":    round(fwd_sharpe, 2) if fwd_sharpe is not None else None,
        "method":        "empirical_bootstrap_v1",
    }


if __name__ == "__main__":
    import random; random.seed(0)
    px = [100.0]
    for _ in range(300):
        px.append(px[-1] * (1 + random.gauss(0.0005, 0.012)))
    r = forward_distribution_metrics(px, horizon_days=10)
    import json
    print(json.dumps(r, indent=2))
