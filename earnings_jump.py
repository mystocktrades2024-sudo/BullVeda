"""
V-5: Per-Ticker Earnings Jump Calibration

Calibrates Merton jump-diffusion parameters from historical earnings-day moves:
  λ (intensity):    annual rate of earnings events (4 quarterly + special events)
  μ_J (mean jump):  log-mean of earnings-day return
  σ_J (jump vol):   log-std of earnings-day returns

These parameters feed into V-1 Monte Carlo when an earnings event lies within
the simulation horizon — gives much more realistic forecast distributions than
plain GBM (which assumes Gaussian-only).

Two calibration paths:
  1. From OHLCV + earnings_calendar: identify days within ±1 of earnings reports,
     compute log-returns of those days, fit Gaussian.
  2. Fallback: industry/sector defaults from research literature (~3% mean magnitude,
     ~5% std for typical large-cap; higher for small/biotech).

Used by build_data.py per ticker; jumps then feed monte_carlo.simulate().
"""
from __future__ import annotations
import numpy as np
from typing import Optional


# Sector-default jump parameters (from public earnings-move studies)
_SECTOR_DEFAULTS = {
    "Health Care":     {"sigma_J": 0.085, "mu_J": -0.005, "events_per_year": 5},
    "Technology":      {"sigma_J": 0.062, "mu_J":  0.002, "events_per_year": 4},
    "Communication":   {"sigma_J": 0.055, "mu_J":  0.000, "events_per_year": 4},
    "Consumer Discretionary": {"sigma_J": 0.058, "mu_J": -0.001, "events_per_year": 4},
    "Consumer Staples": {"sigma_J": 0.038, "mu_J": 0.001, "events_per_year": 4},
    "Industrials":     {"sigma_J": 0.045, "mu_J": -0.001, "events_per_year": 4},
    "Energy":          {"sigma_J": 0.052, "mu_J":  0.000, "events_per_year": 4},
    "Materials":       {"sigma_J": 0.048, "mu_J":  0.000, "events_per_year": 4},
    "Financials":      {"sigma_J": 0.044, "mu_J": -0.002, "events_per_year": 4},
    "Real Estate":     {"sigma_J": 0.035, "mu_J":  0.000, "events_per_year": 4},
    "Utilities":       {"sigma_J": 0.028, "mu_J":  0.000, "events_per_year": 4},
}


def calibrate_from_history(closes: list, dates: list, earnings_dates: list) -> Optional[dict]:
    """
    Empirical calibration when we have OHLCV + earnings calendar.

    Args:
      closes: list of float close prices
      dates: list of ISO date strings (one per close)
      earnings_dates: list of ISO date strings (past earnings reports)

    Returns dict with calibrated (λ, μ_J, σ_J) or None if insufficient data.
    """
    if not closes or not dates or not earnings_dates:
        return None
    if len(closes) != len(dates) or len(closes) < 5:
        return None

    # Build date → close index map
    date_idx = {d: i for i, d in enumerate(dates)}
    earn_returns = []
    for ed in earnings_dates:
        if ed in date_idx:
            i = date_idx[ed]
            if 0 < i < len(closes) - 1:
                # Take the day-of return (open-to-close gap is typical earnings move,
                # but we don't have intraday — use close-to-close as proxy)
                r = np.log(closes[i] / closes[i - 1])
                earn_returns.append(r)

    if len(earn_returns) < 3:
        return None

    arr = np.array(earn_returns)
    mu_J = float(arr.mean())
    sigma_J = float(arr.std(ddof=1)) if len(arr) > 1 else float(abs(mu_J))
    lambda_J = len(arr) * (252 / len(closes)) * 252 / 252  # annual rate proxy

    return {
        "lambda_J":    round(lambda_J, 2),
        "mu_J":        round(mu_J, 4),
        "sigma_J":     round(sigma_J, 4),
        "n_events":    len(arr),
        "method":      "empirical_from_earnings_dates",
        "biggest_move_pct": round(max(arr.max(), abs(arr.min())) * 100, 2),
    }


def calibrate_from_outliers(closes: list, threshold_sigma: float = 3.0) -> Optional[dict]:
    """
    When earnings dates aren't available, estimate from outlier returns.
    Days with |return| > 3σ are likely earnings or news jumps.
    """
    if not closes or len(closes) < 30:
        return None
    rets = np.array([np.log(closes[i] / closes[i-1]) for i in range(1, len(closes)) if closes[i-1] > 0])
    if len(rets) < 30:
        return None

    sigma_baseline = float(np.std(rets, ddof=1))
    threshold = threshold_sigma * sigma_baseline
    outliers = rets[np.abs(rets) > threshold]
    if len(outliers) < 2:
        # No clear jumps — use minimal default
        return {
            "lambda_J":  0.0,
            "mu_J":      0.0,
            "sigma_J":   0.0,
            "n_events":  0,
            "method":    "no_jumps_detected",
        }

    return {
        "lambda_J":    round(len(outliers) / len(rets) * 252, 2),
        "mu_J":        round(float(outliers.mean()), 4),
        "sigma_J":     round(float(outliers.std(ddof=1)) if len(outliers) > 1 else float(abs(outliers.mean())), 4),
        "n_events":    int(len(outliers)),
        "method":      "outlier_detection",
        "biggest_move_pct": round(float(np.abs(outliers).max()) * 100, 2),
    }


def calibrate_from_sector(sector: str) -> dict:
    """Fallback: use sector-default jump parameters."""
    p = _SECTOR_DEFAULTS.get(sector or "", {"sigma_J": 0.050, "mu_J": 0.000, "events_per_year": 4})
    return {
        "lambda_J":  float(p["events_per_year"]),
        "mu_J":      float(p["mu_J"]),
        "sigma_J":   float(p["sigma_J"]),
        "n_events":  None,
        "method":    f"sector_default_{sector}",
    }


def calibrate(ticker: str, closes: list, dates: Optional[list] = None,
              earnings_dates: Optional[list] = None,
              sector: Optional[str] = None) -> dict:
    """
    Best-available calibration with fallback chain:
      1. Empirical from earnings dates (highest fidelity)
      2. Outlier detection from returns
      3. Sector defaults
    """
    out = None
    if dates and earnings_dates:
        out = calibrate_from_history(closes, dates, earnings_dates)
    if out is None:
        out = calibrate_from_outliers(closes)
    if out is None or out.get("n_events", 0) == 0:
        out = calibrate_from_sector(sector or "")
    out["ticker"] = ticker
    return out


if __name__ == "__main__":
    # Test outlier path
    np.random.seed(0)
    closes = [100.0]
    for _ in range(252):
        closes.append(closes[-1] * np.exp(np.random.normal(0.0005, 0.012)))
    # Inject 4 earnings-style jumps
    for inject_idx in [50, 110, 180, 230]:
        closes[inject_idx] *= np.exp(np.random.normal(-0.04, 0.06))
    print("Outlier-based:", calibrate("TEST", closes))
    print("Sector default Health Care:", calibrate_from_sector("Health Care"))
    print("Sector default Tech:", calibrate_from_sector("Technology"))
