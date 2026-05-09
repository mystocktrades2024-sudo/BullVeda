"""
hedge_fund_enhancers.py — statistical rigor + risk overlays + position-level
controls used by hedge funds.

Pure functions, no I/O. Imported by hedge_fund_report.py for report sections
and by backtest.py for portfolio-level overlays. Safe to call from anywhere.

Modules:
  • permutation_test()             — does the system beat random pick selection?
  • bayesian_setup_pool()          — borrow strength across setups (sparse-data fix)
  • information_ratio()            — alpha vs benchmark / tracking error
  • concentration_violation()      — sector/name position-cap check
  • macro_trend_filter()           — SPY 50/200 trend-following gate
  • correlation_regime()           — when picks move together (factor risk)
  • chandelier_exit()              — volatility-aware trailing stop
  • supertrend_levels()            — trend-following stop alternative
  • realistic_slippage_bps()       — bid-ask + size-impact modeling
  • backtest_vs_live_drift()       — alert on model divergence

Citations:
  - Wilson interval: Wilson 1927
  - Permutation test: Politis & Romano 1994 stationary bootstrap
  - Bayesian hierarchical: Gelman BDA3 ch. 5 (partial pooling)
  - Information ratio: Goodwin 1998
  - Chandelier exit: Chuck LeBeau 1990s
"""
from __future__ import annotations

import math
import random
import statistics
from typing import Iterable, Sequence


# ─── Statistical rigor (#1) ──────────────────────────────────────────────────

def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound for binomial proportion."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - spread) / denom)


def bootstrap_pf_ci(trade_returns: Sequence[float], n_iter: int = 2000,
                     ci_pct: float = 95.0, seed: int = 42) -> dict:
    """Bootstrap confidence interval for profit factor.

    Resamples trades WITH REPLACEMENT n_iter times. Computes PF, WR, total
    return on each resample. Reports point estimate + N% CI.

    PF is permutation-invariant (sums don't change under reorder), so a
    permutation test on PF is structurally void. Bootstrap is the right tool:
    it answers "if we had drawn n trades from this distribution, how stable
    is the PF estimate?".

    Args:
      trade_returns: list of pnl_pct from each trade
      n_iter: bootstrap samples (2000 is standard for stable tail estimates)
      ci_pct: confidence interval coverage (95 → 2.5/97.5 percentiles)

    Returns: {pf_point, pf_lo, pf_hi, wr_point, wr_lo, wr_hi, total_lo, total_hi,
              n_iter, interpretation}
    """
    if not trade_returns or len(trade_returns) < 5:
        return {"pf_point": None, "pf_lo": None, "pf_hi": None,
                "n_iter": 0, "interpretation": "insufficient sample"}
    rng = random.Random(seed)
    n = len(trade_returns)
    rets = list(trade_returns)
    pfs, wrs, totals = [], [], []
    for _ in range(n_iter):
        sample = [rng.choice(rets) for _ in range(n)]
        gw = sum(r for r in sample if r > 0)
        gl = abs(sum(r for r in sample if r <= 0))
        pf = gw / gl if gl > 0 else 999
        wr = sum(1 for r in sample if r > 0) / n * 100
        pfs.append(min(pf, 999))
        wrs.append(wr)
        totals.append(sum(sample))
    pfs.sort(); wrs.sort(); totals.sort()
    lo_idx = int((100 - ci_pct) / 2 / 100 * n_iter)
    hi_idx = int((100 - (100 - ci_pct) / 2) / 100 * n_iter)
    # Point estimate from the actual data
    gw_obs = sum(r for r in trade_returns if r > 0)
    gl_obs = abs(sum(r for r in trade_returns if r <= 0))
    pf_point = gw_obs / gl_obs if gl_obs > 0 else 999
    wr_point = sum(1 for r in trade_returns if r > 0) / n * 100
    # Interpretation
    pf_lo = pfs[lo_idx]
    pf_hi = pfs[hi_idx]
    if pf_lo > 1.5:
        verdict = "robust edge (CI above 1.5)"
    elif pf_lo > 1.0:
        verdict = "real edge (CI above 1.0)"
    elif pf_lo > 0.8:
        verdict = "marginal — CI straddles breakeven"
    else:
        verdict = "no provable edge (CI below 1.0)"
    return {
        "pf_point": round(pf_point, 3),
        "pf_lo":    round(pf_lo, 3),
        "pf_hi":    round(min(pf_hi, 10), 3),
        "wr_point": round(wr_point, 1),
        "wr_lo":    round(wrs[lo_idx], 1),
        "wr_hi":    round(wrs[hi_idx], 1),
        "total_lo": round(totals[lo_idx], 2),
        "total_hi": round(totals[hi_idx], 2),
        "n_iter":   n_iter,
        "ci_pct":   ci_pct,
        "interpretation": verdict,
    }


def permutation_test_random_picks(actual_trade_returns: Sequence[float],
                                    universe_returns: Sequence[float],
                                    n_iter: int = 1000, seed: int = 42) -> dict:
    """Random-pick permutation: does the system beat random ticker selection?

    For each iteration, draw N=len(actual) returns at random from universe_returns.
    Compute PF. p-value = fraction of random portfolios with PF ≥ observed.

    True null hypothesis test: "the system has no skill at picking tickers."

    Args:
      actual_trade_returns: pnl_pct from system's picks
      universe_returns: pnl_pct from ALL tickers over same period (random-pickable)
      n_iter: bootstrap samples
    """
    if not actual_trade_returns or not universe_returns or n_iter < 10:
        return {"p_value": None, "n_iter": 0, "interpretation": "insufficient data"}
    rng = random.Random(seed)
    n = len(actual_trade_returns)
    obs_gw = sum(r for r in actual_trade_returns if r > 0)
    obs_gl = abs(sum(r for r in actual_trade_returns if r <= 0))
    obs_pf = obs_gw / obs_gl if obs_gl > 0 else 999
    universe = list(universe_returns)
    n_better_or_equal = 0
    for _ in range(n_iter):
        sample = [rng.choice(universe) for _ in range(n)]
        gw = sum(r for r in sample if r > 0)
        gl = abs(sum(r for r in sample if r <= 0))
        pf = gw / gl if gl > 0 else 999
        if pf >= obs_pf:
            n_better_or_equal += 1
    p = n_better_or_equal / n_iter
    return {
        "p_value": round(p, 4),
        "observed_pf": round(obs_pf, 3),
        "universe_size": len(universe),
        "n_iter": n_iter,
        "interpretation": ("real edge (p<0.05)"           if p < 0.05  else
                           "weak edge (0.05<=p<0.20)"     if p < 0.20  else
                           "no edge vs random (p>=0.20)"),
    }


def bayesian_setup_pool(setup_data: dict[str, dict],
                         family_priors: dict[str, tuple[int, int]] | None = None
                         ) -> dict[str, dict]:
    """Hierarchical Bayes: shrink each setup's WR estimate toward family prior.

    Sparse setups (n=3 Pocket Pivot) borrow strength from family prior. Reduces
    overconfidence on small samples without ignoring them.

    Beta-Binomial conjugate update:
      posterior ~ Beta(prior_wins + observed_wins, prior_losses + observed_losses)
      posterior_mean = (prior_wins + obs_wins) / (prior_wins + prior_losses + obs_n)

    Args:
      setup_data: {setup_name: {wins: int, n: int, family: str (optional)}}
      family_priors: {family_name: (prior_wins, prior_losses)} — informative
                     defaults: pullback (4,6), breakout (5,5), continuation (5,5),
                     reversal (3,7). None → uniform prior (1,1).

    Returns: {setup_name: {posterior_wr, prior_wr, raw_wr, n, shrinkage}}
    """
    default_family_priors = {
        "pullback":     (4, 6),  # historically harder
        "breakout":     (5, 5),  # neutral
        "continuation": (5, 5),  # neutral
        "reversal":     (3, 7),  # historically hardest
        "default":      (1, 1),  # uniform
    }
    fp = family_priors or default_family_priors
    out = {}
    for setup, info in setup_data.items():
        wins = info.get("wins", 0)
        n = info.get("n", 0)
        family = info.get("family", "default")
        prior_w, prior_l = fp.get(family, fp["default"])
        prior_wr = prior_w / (prior_w + prior_l)
        raw_wr = wins / n if n else 0.0
        # Posterior = Beta(prior_w + wins, prior_l + (n-wins))
        post_w = prior_w + wins
        post_l = prior_l + (n - wins)
        post_wr = post_w / (post_w + post_l)
        # Shrinkage = how much the posterior moved toward prior
        shrinkage = abs(post_wr - raw_wr)
        out[setup] = {
            "posterior_wr": round(post_wr * 100, 1),
            "prior_wr":     round(prior_wr * 100, 1),
            "raw_wr":       round(raw_wr * 100, 1),
            "n":            n,
            "shrinkage_pp": round(shrinkage * 100, 1),
            "family":       family,
        }
    return out


# ─── Risk dimensions (#2) ────────────────────────────────────────────────────

def information_ratio(strategy_returns: Sequence[float],
                       benchmark_returns: Sequence[float]) -> dict:
    """Information ratio = alpha / tracking error.

    Both inputs should be aligned daily returns (same length). IR > 0.5 = good,
    IR > 1.0 = excellent. Negative IR means strategy underperforms benchmark.
    """
    n = min(len(strategy_returns), len(benchmark_returns))
    if n < 5:
        return {"ir": 0, "alpha_annual": 0, "tracking_error_annual": 0, "n": n}
    excess = [strategy_returns[i] - benchmark_returns[i] for i in range(n)]
    alpha_daily = statistics.mean(excess)
    te_daily = statistics.stdev(excess) if n > 1 else 0
    if te_daily == 0:
        return {"ir": 0, "alpha_annual": 0, "tracking_error_annual": 0, "n": n}
    ir = alpha_daily / te_daily * math.sqrt(252)
    return {
        "ir": round(ir, 2),
        "alpha_annual_pct": round(alpha_daily * 252 * 100, 2),
        "tracking_error_annual_pct": round(te_daily * math.sqrt(252) * 100, 2),
        "n": n,
    }


def pain_index(drawdown_series: Sequence[float]) -> float:
    """Pain Index — average of |drawdown|. drawdown_series in decimals."""
    if not drawdown_series:
        return 0.0
    return statistics.mean(abs(d) for d in drawdown_series)


def ulcer_index(drawdown_series: Sequence[float]) -> float:
    """Ulcer Index — sqrt(mean(dd^2)). Penalizes deep drawdowns more than shallow."""
    if not drawdown_series:
        return 0.0
    return math.sqrt(statistics.mean(d * d for d in drawdown_series))


# ─── Position-level controls (#4) ────────────────────────────────────────────

def concentration_violation(open_positions: list[dict],
                             new_pick: dict,
                             sector_cap_pct: float = 0.30,
                             name_cap_pct: float = 0.05,
                             total_equity: float = 1.0) -> tuple[bool, str]:
    """Check if adding new_pick would breach sector or per-name caps.

    Args:
      open_positions: list of {ticker, sector, position_value}
      new_pick: {ticker, sector, position_value}
      sector_cap_pct: max % of equity in any single sector (default 30%)
      name_cap_pct: max % of equity in any single name (default 5%)
      total_equity: account size (default 1.0 → cap_pct interpreted as fraction)

    Returns: (would_breach, reason). Reason empty string if no breach.
    """
    cap_dollar_sector = sector_cap_pct * total_equity
    cap_dollar_name = name_cap_pct * total_equity
    new_value = new_pick.get("position_value", 0)
    if new_value > cap_dollar_name:
        return True, f"name cap: ${new_value:.0f} > {name_cap_pct*100:.0f}% of equity"
    sector_total = new_value + sum(
        p.get("position_value", 0) for p in open_positions
        if p.get("sector") == new_pick.get("sector")
    )
    if sector_total > cap_dollar_sector:
        return True, f"sector cap: {new_pick.get('sector')} ${sector_total:.0f} > {sector_cap_pct*100:.0f}% of equity"
    return False, ""


# ─── Macro overlays (#5) ─────────────────────────────────────────────────────

def macro_trend_filter(spy_close_50d_ago: float, spy_close_200d_ago: float,
                        spy_close_today: float) -> dict:
    """SPY golden-cross trend-following filter. SMA50 > SMA200 = long bias.

    Note: this is the simple regime filter, not the full HMM. Use with backtest
    counterfactual: with vs without the filter.
    """
    bullish = spy_close_50d_ago > spy_close_200d_ago and spy_close_today > spy_close_200d_ago
    death_cross = spy_close_50d_ago < spy_close_200d_ago
    return {
        "bullish": bullish,
        "death_cross": death_cross,
        "regime": "bull_above_50_above_200" if bullish else
                  "bear_below_200" if death_cross and spy_close_today < spy_close_200d_ago else
                  "neutral",
        "block_longs": death_cross and spy_close_today < spy_close_50d_ago,
    }


def correlation_regime(returns_matrix: list[list[float]]) -> dict:
    """Average pairwise correlation across all picks — high = factor risk.

    >0.6 = picks moving together (no diversification benefit, factor exposed).
    <0.3 = good diversification.

    Args: returns_matrix — N tickers × T days of daily returns
    """
    n = len(returns_matrix)
    if n < 2 or len(returns_matrix[0]) < 5:
        return {"avg_correlation": 0, "regime": "insufficient_data", "n": n}
    correlations = []
    for i in range(n):
        for j in range(i + 1, n):
            r1, r2 = returns_matrix[i], returns_matrix[j]
            t = min(len(r1), len(r2))
            if t < 5:
                continue
            try:
                m1 = statistics.mean(r1[:t]); m2 = statistics.mean(r2[:t])
                num = sum((r1[k] - m1) * (r2[k] - m2) for k in range(t))
                den1 = math.sqrt(sum((r1[k] - m1) ** 2 for k in range(t)))
                den2 = math.sqrt(sum((r2[k] - m2) ** 2 for k in range(t)))
                if den1 == 0 or den2 == 0:
                    continue
                correlations.append(num / (den1 * den2))
            except Exception:
                continue
    if not correlations:
        return {"avg_correlation": 0, "regime": "insufficient_data", "n": n}
    avg = statistics.mean(correlations)
    return {
        "avg_correlation": round(avg, 3),
        "regime": ("high_correlation_factor_risk" if avg > 0.6 else
                   "moderate_correlation"        if avg > 0.3 else
                   "low_correlation_diversified"),
        "n": n,
        "pairs": len(correlations),
    }


# ─── Position exits (Chandelier / SuperTrend) ────────────────────────────────

def chandelier_exit(highs: Sequence[float], atr: float,
                     multiplier: float = 3.0, lookback: int = 22) -> float:
    """LeBeau's Chandelier exit — trails N×ATR below the highest-high in lookback.

    Volatility-aware. Wider in choppy markets, tighter in trending. Use as
    alternative to fixed-% trailing stop.

    Returns: stop level (long-side).
    """
    if not highs or len(highs) < 2 or atr <= 0:
        return 0
    window = highs[-lookback:] if len(highs) >= lookback else highs
    return max(window) - multiplier * atr


def supertrend_levels(highs: Sequence[float], lows: Sequence[float],
                       closes: Sequence[float], atr: float,
                       multiplier: float = 3.0) -> dict:
    """SuperTrend indicator — trend-following stop alternative.

    For long position: stop = midpoint(high+low)/2 − multiplier*ATR.
    Flips when price crosses below the level.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < 2 or atr <= 0:
        return {"upper": 0, "lower": 0, "trend": "unknown"}
    hl2 = (highs[-1] + lows[-1]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    return {
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "trend": "long" if closes[-1] > lower else "short",
    }


# ─── Realistic execution modeling (#9) ───────────────────────────────────────

def realistic_slippage_bps(price: float, atr_pct: float, dollar_volume: float,
                            position_dollar: float, side: str = "buy") -> float:
    """Estimate realistic slippage in basis points.

    Three components:
      - Spread cost (proxied by ATR%, capped at 30bps for liquid names)
      - Size impact: position_dollar / daily_dollar_volume × 50bps coefficient
      - Side asymmetry: market buys pay slightly more (5bps adder)

    Returns: slippage in bps (basis points).
    """
    if price <= 0 or dollar_volume <= 0:
        return 30.0  # default for missing data
    spread_bps = min(30, atr_pct * 5)  # rough proxy: tighter ATR → tighter spread
    size_impact_bps = (position_dollar / dollar_volume) * 50 * 100  # daily vol participation
    size_impact_bps = min(80, size_impact_bps)  # cap at 80bps
    side_bps = 5 if side.lower() == "buy" else 0
    return round(spread_bps + size_impact_bps + side_bps, 1)


# ─── Edge-decay tracking (#10) ───────────────────────────────────────────────

def backtest_vs_live_drift(live_trades: list[dict], backtest_metrics: dict,
                            window_days: int = 30) -> dict:
    """Compare last N days of live trades to most-recent backtest summary.

    Args:
      live_trades: list of {entry_date, win} from signal_log (closed only)
      backtest_metrics: {wr_pct, profit_factor} from portfolio_backtest.json
      window_days: rolling lookback (30 default)

    Returns: {live_wr, backtest_wr, delta_pp, alert (bool), n_live}
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=window_days)
    recent = []
    for t in live_trades:
        entry = t.get("entry_date") or t.get("exit_date")
        if not entry:
            continue
        try:
            d = datetime.fromisoformat(str(entry)[:10])
        except Exception:
            continue
        if d >= cutoff:
            recent.append(t)
    if not recent:
        return {"live_wr": None, "backtest_wr": backtest_metrics.get("wr_pct"),
                "delta_pp": None, "alert": False, "n_live": 0}
    n = len(recent)
    wins = sum(1 for t in recent if t.get("win"))
    live_wr = wins / n * 100
    bt_wr = backtest_metrics.get("wr_pct", 0)
    delta = live_wr - bt_wr
    return {
        "live_wr": round(live_wr, 1),
        "backtest_wr": round(bt_wr, 1),
        "delta_pp": round(delta, 1),
        "alert": delta < -5,  # live underperforming backtest by >5pp
        "n_live": n,
        "window_days": window_days,
    }


# ─── #1.1 Train/Test/Holdout split ──────────────────────────────────────────

def train_test_holdout_split(trades_sorted_by_date: list[dict],
                              ratios: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> dict:
    """Time-ordered 70/15/15 split. Reports WR/PF for each segment.

    OVERFIT DETECTION: if train.PF >> test.PF, the system is over-fit to early data.
    test.PF and holdout.PF should be within ~20% of train.PF for confidence.
    """
    n = len(trades_sorted_by_date)
    if n < 30:
        return {"available": False, "reason": f"need ≥30 trades, have {n}"}
    n_train = int(n * ratios[0])
    n_test = int(n * ratios[1])
    train = trades_sorted_by_date[:n_train]
    test = trades_sorted_by_date[n_train:n_train + n_test]
    holdout = trades_sorted_by_date[n_train + n_test:]

    def _stats(items):
        if not items:
            return {"n": 0, "wr_pct": 0, "pf": 0, "total_pct": 0, "avg_pct": 0}
        n_ = len(items)
        wins = sum(1 for t in items if t.get("win"))
        rets = [t.get("pnl_pct", 0) for t in items]
        gw = sum(r for r in rets if r > 0)
        gl = abs(sum(r for r in rets if r <= 0))
        return {
            "n": n_,
            "wr_pct": round(wins / n_ * 100, 1),
            "pf": round(gw / gl, 2) if gl > 0 else 999,
            "total_pct": round(sum(rets), 2),
            "avg_pct": round(sum(rets) / n_, 2),
        }

    train_s = _stats(train); test_s = _stats(test); holdout_s = _stats(holdout)
    # Overfit verdict: test.PF / train.PF
    pf_ratio_test = test_s["pf"] / train_s["pf"] if train_s["pf"] else 0
    pf_ratio_holdout = holdout_s["pf"] / train_s["pf"] if train_s["pf"] else 0
    overfit = pf_ratio_test < 0.5 or pf_ratio_holdout < 0.5
    return {
        "available": True,
        "train": train_s, "test": test_s, "holdout": holdout_s,
        "pf_ratio_test_vs_train": round(pf_ratio_test, 2),
        "pf_ratio_holdout_vs_train": round(pf_ratio_holdout, 2),
        "overfit_detected": overfit,
        "interpretation": ("⚠ OVERFIT — test/holdout PF much lower than train"
                           if overfit else
                           "stable — train/test/holdout consistent"),
    }


# ─── #1.2 K-fold time-series CV ──────────────────────────────────────────────

def kfold_timeseries_cv(trades_sorted_by_date: list[dict], k: int = 5) -> dict:
    """K-fold time-series CV. Reports per-fold WR/PF + variance across folds.

    Stability indicator: if CV std(PF) is large relative to mean(PF), edge isn't
    consistent. Mean ± 2σ should ideally NOT include 1.0.
    """
    n = len(trades_sorted_by_date)
    if n < k * 5:
        return {"available": False, "reason": f"need ≥{k*5} trades for {k}-fold, have {n}"}
    fold_size = n // k
    fold_results = []
    for i in range(k):
        start = i * fold_size
        end = start + fold_size if i < k - 1 else n
        items = trades_sorted_by_date[start:end]
        n_ = len(items)
        wins = sum(1 for t in items if t.get("win"))
        rets = [t.get("pnl_pct", 0) for t in items]
        gw = sum(r for r in rets if r > 0)
        gl = abs(sum(r for r in rets if r <= 0))
        pf = gw / gl if gl > 0 else 999
        fold_results.append({
            "fold": i + 1, "n": n_,
            "date_start": (items[0].get("entry_date") or "")[:10] if items else "",
            "date_end": (items[-1].get("exit_date") or "")[:10] if items else "",
            "wr_pct": round(wins / n_ * 100, 1),
            "pf": round(min(pf, 999), 2),
            "total_pct": round(sum(rets), 2),
        })
    pfs = [f["pf"] for f in fold_results if f["pf"] < 999]
    wrs = [f["wr_pct"] for f in fold_results]
    mean_pf = statistics.mean(pfs) if pfs else 0
    std_pf = statistics.stdev(pfs) if len(pfs) > 1 else 0
    mean_wr = statistics.mean(wrs) if wrs else 0
    std_wr = statistics.stdev(wrs) if len(wrs) > 1 else 0
    # Stability: CV (coefficient of variation) — std/mean
    cv = std_pf / mean_pf if mean_pf else 999
    if cv < 0.20:
        verdict = "very stable"
    elif cv < 0.40:
        verdict = "stable"
    elif cv < 0.70:
        verdict = "moderate variance — edge regime-dependent"
    else:
        verdict = "high variance — edge inconsistent across time"
    return {
        "available": True,
        "folds": fold_results,
        "mean_pf": round(mean_pf, 2),
        "std_pf":  round(std_pf, 2),
        "mean_wr": round(mean_wr, 1),
        "std_wr":  round(std_wr, 1),
        "cv":      round(cv, 2),
        "interpretation": verdict,
    }


# ─── #1.4 White's Reality Check (Bonferroni-corrected multi-strategy) ────────

def whites_reality_check(strategies: dict[str, list[float]],
                          benchmark_pf: float = 1.0,
                          n_iter: int = 1000, seed: int = 42) -> dict:
    """Bonferroni-corrected p-value across multiple competing strategies.

    When you test K strategies and pick the best, the naïve p-value is
    inflated by data snooping. Bonferroni correction divides α by K. Reports
    per-strategy p-value AND Bonferroni threshold for K-strategy comparison.

    Strategies: {strategy_name: list of pnl_pct returns}
    """
    if not strategies:
        return {"available": False, "reason": "no strategies"}
    rng = random.Random(seed)
    K = len(strategies)
    bonferroni_alpha = 0.05 / K  # adjusted significance threshold
    results = []
    for name, returns in strategies.items():
        if not returns or len(returns) < 5:
            continue
        gw = sum(r for r in returns if r > 0)
        gl = abs(sum(r for r in returns if r <= 0))
        obs_pf = gw / gl if gl > 0 else 999
        # Bootstrap p-value
        n_better = 0
        rets = list(returns)
        for _ in range(n_iter):
            sample = [rng.choice(rets) * rng.choice([-1, 1]) for _ in range(len(rets))]
            s_gw = sum(r for r in sample if r > 0)
            s_gl = abs(sum(r for r in sample if r <= 0))
            sim_pf = s_gw / s_gl if s_gl > 0 else 999
            if sim_pf >= obs_pf:
                n_better += 1
        p_raw = n_better / n_iter
        results.append({
            "strategy": name,
            "n_trades": len(returns),
            "observed_pf": round(min(obs_pf, 999), 2),
            "p_raw": round(p_raw, 4),
            "p_bonferroni_corrected": round(min(p_raw * K, 1.0), 4),
            "passes_naive_alpha":      p_raw < 0.05,
            "passes_bonferroni":       p_raw < bonferroni_alpha,
        })
    return {
        "available": True,
        "n_strategies": K,
        "bonferroni_threshold_alpha": round(bonferroni_alpha, 4),
        "strategies": results,
        "n_iter": n_iter,
    }


# ─── #3.1 Setup × score-band stability over time quartiles ───────────────────

def signal_stability_quartiles(trades_sorted_by_date: list[dict]) -> dict:
    """Partition trades into time quartiles, recompute WR per setup per quartile.

    Reveals whether Trend Continuation's 44% WR is stable or whether it spiked
    in Q3 and faded. If WR oscillates Q1→Q2→Q3→Q4 by >15pp, edge is NOT durable.
    """
    n = len(trades_sorted_by_date)
    if n < 16:
        return {"available": False, "reason": f"need ≥16 trades for quartile stability"}
    q_size = n // 4
    quartiles = {
        "Q1": trades_sorted_by_date[:q_size],
        "Q2": trades_sorted_by_date[q_size:q_size*2],
        "Q3": trades_sorted_by_date[q_size*2:q_size*3],
        "Q4": trades_sorted_by_date[q_size*3:],
    }
    # Per setup, per quartile WR
    setups = set(t.get("setup_type") or "?" for t in trades_sorted_by_date)
    rows = []
    for setup in setups:
        cells = {"setup": setup}
        wrs = []
        for qname, q_trades in quartiles.items():
            items = [t for t in q_trades if (t.get("setup_type") or "?") == setup]
            n_ = len(items)
            if n_ < 2:
                cells[qname] = {"n": n_, "wr": None}
                continue
            wins = sum(1 for t in items if t.get("win"))
            wr = wins / n_ * 100
            cells[qname] = {"n": n_, "wr": round(wr, 1)}
            wrs.append(wr)
        if len(wrs) >= 2:
            cells["wr_range"] = round(max(wrs) - min(wrs), 1)
            cells["wr_stdev"] = round(statistics.stdev(wrs) if len(wrs) > 1 else 0, 1)
            cells["stable"]   = (max(wrs) - min(wrs)) < 15
        else:
            cells["wr_range"] = None
            cells["stable"] = None
        rows.append(cells)
    return {"available": True, "rows": rows,
            "quartile_dates": {q: {"start": (lst[0].get("entry_date") or "")[:10] if lst else "",
                                     "end":   (lst[-1].get("exit_date") or "")[:10] if lst else "",
                                     "n": len(lst)}
                                for q, lst in quartiles.items()}}


# ─── #7.4 VIX size-halving counterfactual ────────────────────────────────────

def vix_size_halving_cf(trades: list[dict],
                          vix_lookup_fn,
                          vix_threshold: float = 25.0,
                          size_haircut: float = 0.5) -> dict:
    """What if we'd halved size when entering during VIX > threshold?

    Args:
      vix_lookup_fn: callable(date_str) -> float (VIX value at trade entry)
      vix_threshold: trades entered above this get reduced size
      size_haircut: multiplier (0.5 = half size)

    Returns: {original_total, modified_total, n_affected, delta_pct}
    """
    original_total = sum(t.get("pnl_pct", 0) for t in trades)
    modified = []
    n_affected = 0
    for t in trades:
        try:
            vix = vix_lookup_fn(t.get("entry_date") or "")
        except Exception:
            vix = None
        ret = t.get("pnl_pct", 0)
        if vix is not None and vix >= vix_threshold:
            modified.append(ret * size_haircut)
            n_affected += 1
        else:
            modified.append(ret)
    modified_total = sum(modified)
    return {
        "vix_threshold": vix_threshold,
        "size_haircut": size_haircut,
        "n_affected": n_affected,
        "n_total": len(trades),
        "original_total_pct": round(original_total, 2),
        "modified_total_pct": round(modified_total, 2),
        "delta_pct": round(modified_total - original_total, 2),
    }


if __name__ == "__main__":
    # Smoke tests
    import json
    from pathlib import Path
    p = Path(__file__).parent / "cache" / "portfolio_backtest.json"
    if p.exists():
        d = json.loads(p.read_text())
        trades = d.get("trades", [])
        rets = [t["pnl_pct"] for t in trades]
        pf = d.get("profit_factor", 0)
        print("=== Bootstrap PF confidence interval ===")
        result = bootstrap_pf_ci(rets, n_iter=2000)
        for k, v in result.items():
            print(f"  {k}: {v}")
        print("\n=== Bayesian setup pool ===")
        from collections import Counter
        setups = Counter()
        wins_by = Counter()
        for t in trades:
            s = t.get("setup_type") or "?"
            setups[s] += 1
            if t.get("win"): wins_by[s] += 1
        sd = {s: {"wins": wins_by[s], "n": setups[s],
                  "family": "pullback" if "Pullback" in s else
                            "breakout" if "Breakout" in s or "Pivot" in s else
                            "continuation" if "Continuation" in s else "default"}
              for s in setups}
        for setup, m in bayesian_setup_pool(sd).items():
            print(f"  {setup}: raw {m['raw_wr']}% → posterior {m['posterior_wr']}% (shrunk by {m['shrinkage_pp']}pp, family={m['family']})")
