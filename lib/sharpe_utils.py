"""sharpe_utils.py — shared Sharpe / Sortino / consistency helpers.

Single source of truth used by:
  - scripts/sharpe_screener.py
  - scripts/sharpe_per_regime.py
  - scripts/sharpe_consistency.py
  - scripts/sharpe_attribution.py
  - scripts/sharpe_alert.py
  - infra/prototype/build_data.py (Sharpe column)
  - analysis.py (_detect_momentum_continuation Sharpe gate)

All functions accept either a list of closes OR a list of daily returns; pick
whichever is more natural at the call site.
"""
from __future__ import annotations

import math
from typing import Sequence

TRADING_DAYS_YEAR = 252


def closes_to_returns(closes: Sequence[float]) -> list[float]:
    rets: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev and prev > 0:
            rets.append((closes[i] - prev) / prev)
    return rets


def sharpe_annualized(closes: Sequence[float], lookback: int = 126,
                      risk_free_daily: float = 0.0) -> tuple[float | None, float | None, float | None]:
    """Annualized Sharpe over the trailing `lookback` trading days.

    Returns (sharpe, return_ann_pct, vol_ann_pct) or (None, None, None) if data thin.
    """
    n = len(closes)
    if n < lookback + 1:
        return None, None, None
    sub = list(closes)[-lookback:]
    rets = closes_to_returns(sub)
    if len(rets) < 30:
        return None, None, None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var) if var > 0 else 0
    if std == 0:
        return None, None, None
    sharpe = ((mean - risk_free_daily) / std) * math.sqrt(TRADING_DAYS_YEAR)
    ret_ann = mean * TRADING_DAYS_YEAR * 100
    vol_ann = std * math.sqrt(TRADING_DAYS_YEAR) * 100
    return round(sharpe, 3), round(ret_ann, 2), round(vol_ann, 2)


def sortino_annualized(closes: Sequence[float], lookback: int = 126,
                       risk_free_daily: float = 0.0) -> tuple[float | None, float | None]:
    """Annualized Sortino — downside-only volatility denominator.

    For swing trading, this is arguably more relevant than Sharpe: upside vol
    is the goal, not the punishment.

    Returns (sortino, downside_vol_ann_pct) or (None, None).
    """
    n = len(closes)
    if n < lookback + 1:
        return None, None
    sub = list(closes)[-lookback:]
    rets = closes_to_returns(sub)
    if len(rets) < 30:
        return None, None
    mean = sum(rets) / len(rets)
    downside = [r - risk_free_daily for r in rets if r < risk_free_daily]
    if len(downside) < 5:
        return None, None
    dd_var = sum(d * d for d in downside) / len(downside)
    dd_std = math.sqrt(dd_var) if dd_var > 0 else 0
    if dd_std == 0:
        return None, None
    sortino = ((mean - risk_free_daily) / dd_std) * math.sqrt(TRADING_DAYS_YEAR)
    dd_ann = dd_std * math.sqrt(TRADING_DAYS_YEAR) * 100
    return round(sortino, 3), round(dd_ann, 2)


def rolling_sharpe(closes: Sequence[float], windows: Sequence[int] = (5, 20, 60, 126, 252)
                   ) -> dict[int, float | None]:
    """Compute Sharpe across multiple rolling-window sizes for consistency check.

    Stable Sharpe across all windows = robust edge.
    Volatile Sharpe across windows = regime-dependent / noise.
    """
    out: dict[int, float | None] = {}
    for w in windows:
        s, _, _ = sharpe_annualized(closes, lookback=w)
        out[w] = s
    return out


def consistency_score(rolling: dict[int, float | None]) -> dict:
    """Score the stability of Sharpe across rolling windows.

    Returns:
      {
        'available_windows': N,
        'min': X, 'max': Y, 'spread': Y-X,
        'mean': Z, 'stdev': S,
        'cv': S/|Z|  (coefficient of variation — lower = more stable),
        'verdict': 'stable' | 'mixed' | 'volatile' | 'insufficient'
      }
    """
    vals = [v for v in rolling.values() if v is not None]
    n = len(vals)
    out = {"available_windows": n, "min": None, "max": None, "spread": None,
           "mean": None, "stdev": None, "cv": None, "verdict": "insufficient"}
    if n < 3:
        return out
    out["min"] = round(min(vals), 3)
    out["max"] = round(max(vals), 3)
    out["spread"] = round(out["max"] - out["min"], 3)
    mean = sum(vals) / n
    out["mean"] = round(mean, 3)
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n >= 2 else 0
    stdev = math.sqrt(var) if var > 0 else 0
    out["stdev"] = round(stdev, 3)
    if abs(mean) > 0.05:
        out["cv"] = round(stdev / abs(mean), 3)
    # Verdict heuristics:
    #   stable:  spread ≤ 0.75 AND all values same sign
    #   mixed:   spread 0.75-1.5 OR sign changes
    #   volatile: spread > 1.5
    same_sign = all(v >= 0 for v in vals) or all(v <= 0 for v in vals)
    if out["spread"] <= 0.75 and same_sign:
        out["verdict"] = "stable"
    elif out["spread"] > 1.5 or not same_sign:
        out["verdict"] = "volatile" if out["spread"] > 1.5 else "mixed"
    else:
        out["verdict"] = "mixed"
    return out


def per_trade_sharpe(pnl_pcts: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    """Per-trade Sharpe (no annualization — direction is what matters).

    Returns (sharpe_per_trade, mean_pct, stdev_pct).
    """
    n = len(pnl_pcts)
    if n < 2:
        return None, None, None
    mean = sum(pnl_pcts) / n
    var = sum((p - mean) ** 2 for p in pnl_pcts) / (n - 1)
    stdev = math.sqrt(var) if var > 0 else 0
    if stdev == 0:
        return None, round(mean, 3), 0.0
    return round(mean / stdev, 3), round(mean, 3), round(stdev, 3)


def per_trade_sortino(pnl_pcts: Sequence[float]) -> tuple[float | None, float | None]:
    """Per-trade Sortino (downside-only stdev)."""
    n = len(pnl_pcts)
    if n < 2:
        return None, None
    mean = sum(pnl_pcts) / n
    downside = [p for p in pnl_pcts if p < 0]
    if len(downside) < 2:
        return None, None
    dd_var = sum(d * d for d in downside) / len(downside)
    dd_std = math.sqrt(dd_var) if dd_var > 0 else 0
    if dd_std == 0:
        return None, None
    return round(mean / dd_std, 3), round(dd_std, 3)


def attribution_contribution(per_trade_pnls: Sequence[float], group_indices: Sequence[int]
                             ) -> tuple[float, float]:
    """Contribution of a sub-group of trades to the overall mean/Sharpe.

    Returns (sum_contribution, share_of_total_pnl_pct).
    """
    total = sum(per_trade_pnls) if per_trade_pnls else 0
    sub_sum = sum(per_trade_pnls[i] for i in group_indices) if group_indices else 0
    share = (sub_sum / total * 100.0) if total != 0 else 0
    return round(sub_sum, 3), round(share, 2)
