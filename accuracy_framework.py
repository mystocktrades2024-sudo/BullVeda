"""
Accuracy Framework (P0-B / V-7)

Validates the SwingTrade scoring engine against realized outcomes.

Components (per Vinod's whitepaper):
  A1 — Kupiec POF (Proportion of Failures) test
       Tests whether the actual exception rate matches the expected VaR rate.
       For VaR(95%) we expect ~5% of trades to lose more than the predicted "worst case".

       Threshold (post 2026-05-03 recalibration): exception = realized R ≤ -2R.
       Reason: -1R = stop hit, which is a NORMAL event in swing trading (we deliberately
       accept ~30% stop-out rate when winners run +3-9R). "Tail loss" should mean
       2× our predefined risk budget — i.e., we lost more than we said we would
       (gap-down, stop slippage, or holding past stop). That is statistically a
       95th-percentile event, matching Basel's VaR(95%) framework.

  A2 — Christoffersen conditional coverage test
       Tests whether exceptions are independent (random) or clustered.
       Clustering = model failure mode; randomness = acceptable.

  A3 — Per-regime / per-strategy / per-score-band accuracy breakdowns
       Hit rate · win rate · avg R-multiple · profit factor.

  A4 — Basel III traffic-light zones
       Last-250-trade exception count → Green (0-4) / Yellow (5-9) / Red (10+).
       Auto-flags decay before it shows up in WR.

  A5 — UI surface (separate tab + Accuracy panel) — see dashboard.html

All inputs come from `data/signal_log.json` (closed trades only).
No new data fetch — pure post-hoc analysis.

Built 2026-05-03.
"""
from __future__ import annotations
import math
from collections import defaultdict
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _is_closed(s: dict) -> bool:
    """True if the signal has a realized outcome (CLOSED status or non-pending result)."""
    return s.get("status") == "CLOSED" or s.get("result") in ("WIN_EXPIRED", "TARGET_HIT", "STOPPED", "LOSS_EXPIRED")


def _r_multiple(s: dict) -> Optional[float]:
    """
    Realized R-multiple = pnl / (entry - stop).
    -1R means stop hit · +3R means target1 hit at default 3:1 R:R.
    """
    pnl_pct = s.get("actual_pnl_pct")
    entry   = s.get("entry_price")
    stop    = s.get("stop")
    if pnl_pct is None or entry is None or stop is None:
        return None
    risk_pct = (entry - stop) / entry * 100 if entry else None
    if not risk_pct or risk_pct <= 0:
        return None
    return round(pnl_pct / risk_pct, 3)


def _is_exception(s: dict, threshold_r: float = -2.0) -> bool:
    """
    True if this trade was a VaR exception — realized R worse than threshold.

    Default threshold is -2R = "true tail loss" (lost 2× our predefined risk budget).
    Reason for not using -1R: stops are designed to fire ~30% of the time in our
    swing system; that's not a tail event, that's expected behavior.
    """
    r = _r_multiple(s)
    return r is not None and r <= threshold_r


def _chi2_p_value(lr: float, df: int = 1) -> float:
    """
    Approximate chi-squared p-value for likelihood-ratio statistic `lr` at `df` degrees of freedom.
    Implemented without scipy dependency — uses series expansion of the regularized gamma fn.
    Accurate to ~4 decimal places for our range of LR values (0-30).
    """
    if lr <= 0: return 1.0
    if df != 1 and df != 2:
        # Fallback for other df: bound conservatively
        return 0.05 if lr > 3.841 else 0.5
    # For df=1: P(X^2 > lr) = 1 - erf(sqrt(lr/2))
    if df == 1:
        x = math.sqrt(lr / 2)
        return 1.0 - math.erf(x)
    # For df=2: P(X^2 > lr) = exp(-lr/2)
    return math.exp(-lr / 2)


# ─────────────────────────────────────────────────────────────────────────────
# A1 — Kupiec POF Test
# ─────────────────────────────────────────────────────────────────────────────
def kupiec_pof_test(closed_signals: list, expected_p: float = 0.05, threshold_r: float = -2.0) -> dict:
    """
    Kupiec Proportion-of-Failures test.

    H0: actual exception rate == expected_p (e.g., 5% for VaR-95)
    Reject H0 if LR > 3.841 (chi-square 1df, 95% confidence)

    Returns:
      {n_trades, n_exceptions, actual_rate, expected_rate, lr_stat,
       p_value, accepted, verdict}
    """
    n = len(closed_signals)
    if n == 0:
        return {"n_trades": 0, "verdict": "INSUFFICIENT_DATA"}
    x = sum(1 for s in closed_signals if _is_exception(s, threshold_r))
    actual = x / n
    p = expected_p

    # Likelihood ratio
    if x == 0:
        lr = -2 * (n * math.log(1 - p))
    elif x == n:
        lr = -2 * (n * math.log(p))
    else:
        # LR = -2 * ln(L_null / L_alt)
        ln_null = (n - x) * math.log(1 - p) + x * math.log(p)
        ln_alt  = (n - x) * math.log(1 - actual) + x * math.log(actual)
        lr = -2 * (ln_null - ln_alt)

    p_value = _chi2_p_value(lr, df=1)
    # 95% confidence — accept H0 if p > 0.05
    accepted = p_value > 0.05
    verdict = "MODEL_OK" if accepted else "MODEL_REJECTED"

    return {
        "n_trades":      n,
        "n_exceptions":  x,
        "actual_rate":   round(actual * 100, 2),
        "expected_rate": round(p * 100, 2),
        "lr_stat":       round(lr, 3),
        "p_value":       round(p_value, 4),
        "accepted":      accepted,
        "verdict":       verdict,
        "threshold_r":   threshold_r,
    }


# ─────────────────────────────────────────────────────────────────────────────
# A2 — Christoffersen Conditional Coverage Test
# ─────────────────────────────────────────────────────────────────────────────
def christoffersen_test(closed_signals: list, threshold_r: float = -2.0) -> dict:
    """
    Christoffersen test for INDEPENDENCE of exceptions over time.
    Sorts trades by close date, builds a 0/1 exception sequence, then tests
    whether transition probabilities are independent of the previous state.

    H0: exceptions are independent (P(exc|prev=exc) == P(exc|prev=no-exc))
    Reject H0 if LR > 3.841

    Returns:
      {n_trades, transitions, lr_stat, p_value, accepted, clustering_verdict}
    """
    closed = sorted(closed_signals, key=lambda s: s.get("date") or "")
    seq = [1 if _is_exception(s, threshold_r) else 0 for s in closed]
    n = len(seq)
    if n < 10:
        return {"n_trades": n, "verdict": "INSUFFICIENT_DATA"}

    # Transition counts
    n00 = n01 = n10 = n11 = 0
    for i in range(1, n):
        prev, cur = seq[i-1], seq[i]
        if   prev == 0 and cur == 0: n00 += 1
        elif prev == 0 and cur == 1: n01 += 1
        elif prev == 1 and cur == 0: n10 += 1
        elif prev == 1 and cur == 1: n11 += 1

    # If no exceptions or no consecutive non-exceptions, can't test
    n0 = n00 + n01
    n1 = n10 + n11
    if n0 == 0 or n1 == 0:
        return {
            "n_trades": n,
            "transitions": {"00": n00, "01": n01, "10": n10, "11": n11},
            "verdict": "INSUFFICIENT_TRANSITIONS",
            "clustering_verdict": "—",
        }

    pi    = (n01 + n11) / (n0 + n1)
    pi_01 = n01 / n0 if n0 > 0 else 0
    pi_11 = n11 / n1 if n1 > 0 else 0

    # Likelihood ratio for independence
    def _safe_log(x): return math.log(x) if x > 0 else 0
    ln_null = (n00 + n10) * _safe_log(1 - pi)   + (n01 + n11) * _safe_log(pi)
    ln_alt  = n00 * _safe_log(1 - pi_01)        + n01 * _safe_log(pi_01) \
            + n10 * _safe_log(1 - pi_11)        + n11 * _safe_log(pi_11)
    lr = -2 * (ln_null - ln_alt)

    p_value = _chi2_p_value(lr, df=1)
    accepted = p_value > 0.05
    clustering = "INDEPENDENT" if accepted else "CLUSTERED (model failure mode)"

    return {
        "n_trades":   n,
        "transitions": {"00": n00, "01": n01, "10": n10, "11": n11},
        "pi_uncond":  round(pi, 4),
        "pi_after_no_exc": round(pi_01, 4),
        "pi_after_exc":    round(pi_11, 4),
        "lr_stat":    round(lr, 3),
        "p_value":    round(p_value, 4),
        "accepted":   accepted,
        "clustering_verdict": clustering,
    }


# ─────────────────────────────────────────────────────────────────────────────
# A3 — Per-strategy / per-score-band / per-direction accuracy
# ─────────────────────────────────────────────────────────────────────────────
def basic_metrics(signals: list) -> dict:
    """
    Win rate · avg R · profit factor · expectancy on a list of CLOSED signals.
    """
    closed = [s for s in signals if _is_closed(s)]
    n = len(closed)
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_r": None, "pf": None, "expectancy": None}

    rs = [_r_multiple(s) for s in closed]
    rs = [r for r in rs if r is not None]
    if not rs:
        return {"n": n, "win_rate": None, "avg_r": None, "pf": None, "expectancy": None}

    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    wr = len(wins) / len(rs) if rs else 0
    avg_r = sum(rs) / len(rs)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf') if gross_win > 0 else None
    expectancy = wr * avg_win + (1 - wr) * avg_loss

    return {
        "n":          n,
        "win_rate":   round(wr * 100, 1),
        "avg_r":      round(avg_r, 3),
        "avg_win":    round(avg_win, 3),
        "avg_loss":   round(avg_loss, 3),
        "pf":         round(pf, 2) if pf and pf != float('inf') else None,
        "expectancy": round(expectancy, 3),
    }


def per_strategy_metrics(signals: list) -> dict:
    """Group by strategy field, return basic_metrics per group."""
    groups = defaultdict(list)
    for s in signals:
        if _is_closed(s):
            groups[s.get("strategy") or "Unknown"].append(s)
    return {k: basic_metrics(v) for k, v in sorted(groups.items())}


def per_score_band_metrics(signals: list) -> dict:
    """Group by score band (60-69, 70-79, 80-89, 90-100)."""
    def _band(score):
        if score is None: return "no_score"
        if score >= 90: return "90-100"
        if score >= 80: return "80-89"
        if score >= 70: return "70-79"
        if score >= 60: return "60-69"
        return "<60"
    groups = defaultdict(list)
    for s in signals:
        if _is_closed(s):
            groups[_band(s.get("score"))].append(s)
    return {k: basic_metrics(v) for k, v in groups.items()}


def per_direction_metrics(signals: list) -> dict:
    """Group by direction (long / short)."""
    groups = defaultdict(list)
    for s in signals:
        if _is_closed(s):
            groups[s.get("direction") or "long"].append(s)
    return {k: basic_metrics(v) for k, v in groups.items()}


# ─────────────────────────────────────────────────────────────────────────────
# A4 — Basel III Traffic-Light
# ─────────────────────────────────────────────────────────────────────────────
def basel_traffic_light(closed_signals: list, window: int = 250, threshold_r: float = -2.0) -> dict:
    """
    Classify model state by exception-count vs expected at last `window` trades.

    Threshold is -2R (lost 2× our predefined risk) — true tail event for swing.
    Zone bands are scaled to actual n via the binomial expected count, NOT
    Basel's hardcoded 4/9/10 (which assumes n=250):
      Green:  ≤ 0.5× expected → calibrated, tail losses within tolerance
      Yellow: ≤ 1.5× expected → slightly elevated, monitor
      Red:    > 1.5× expected → genuinely high tail-loss rate; investigate

    Returns:
      {window, n_trades, n_exceptions, expected, zone, color, recommendation}
    """
    # Sort by date desc, take last `window`
    closed = sorted(closed_signals, key=lambda s: s.get("date") or "", reverse=True)[:window]
    n = len(closed)
    if n == 0:
        return {"zone": "INSUFFICIENT_DATA"}

    x = sum(1 for s in closed if _is_exception(s, threshold_r))
    expected_f = n * 0.05
    expected = round(expected_f)

    if x <= expected_f * 0.5:
        zone, color, rec = "GREEN", "var(--pass)", "Calibrated — tail-loss rate within expected 5%."
    elif x <= expected_f * 1.5:
        zone, color, rec = "YELLOW", "var(--warn)", "Slightly elevated tail-loss rate — monitor; investigate which setups are blowing through stops."
    else:
        zone, color, rec = "RED", "var(--fail)", "Tail-loss rate significantly above expected — review filtering on setups that close at ≤-2R."

    return {
        "window":         window,
        "n_trades":       n,
        "n_exceptions":   x,
        "expected":       expected,
        "exception_rate": round(x / n * 100, 2) if n else 0,
        "zone":           zone,
        "color":          color,
        "recommendation": rec,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Combined entry point — single call returns the full accuracy bundle
# ─────────────────────────────────────────────────────────────────────────────
def compute_all_accuracy_metrics(signal_log: list) -> dict:
    """
    Run all 4 components on a signal_log list.

    Returns dict suitable for serialization into v2 bundle (data.json) under `accuracy` key.
    """
    closed = [s for s in signal_log if _is_closed(s)]
    return {
        "summary":       basic_metrics(closed),
        "kupiec_pof":    kupiec_pof_test(closed),
        "christoffersen": christoffersen_test(closed),
        "basel":         basel_traffic_light(closed),
        "by_strategy":   per_strategy_metrics(closed),
        "by_score_band": per_score_band_metrics(closed),
        "by_direction":  per_direction_metrics(closed),
        "n_total":       len(signal_log),
        "n_closed":      len(closed),
        "_computed_at":  __import__("datetime").datetime.now().isoformat(),
    }
