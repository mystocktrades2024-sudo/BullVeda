"""
calibration.py — Score calibration diagnostics for SwingTrade.

The composite score (0-100) is categorical (BUY / WATCH / AVOID) and is NOT
directly interpretable as a win probability. This module fits an isotonic
regression to the observed score → win-rate mapping so we can report how well
the score ranks real outcomes.

Usage:
    python3 calibration.py        # compute + persist cache/calibration_report.json
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("swingtrade.calibration")

_DEFAULT_REPORT_PATH = "cache/calibration_report.json"


def _empty_report() -> dict:
    return {
        "bins": [],
        "brier_score": None,
        "calibration_slope": None,
        "n_trades": 0,
    }


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Mean squared error of probability predictions.

    Lower = better. 0.25 = random coin (always predicts 0.5 on a 50/50).
    Returns NaN as None if inputs are empty / mismatched.
    """
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return float("nan")
    total = 0.0
    for p, y in zip(predictions, outcomes):
        try:
            pf = float(p)
            yf = float(y)
        except (TypeError, ValueError):
            continue
        total += (pf - yf) ** 2
    return total / len(predictions)


def _extract_score_win_pairs(trades: list[dict]) -> list[tuple[float, int]]:
    """Pull (score, win_bool_as_int) from closed trades.

    Accepts `win: bool`, else derives win from pnl fields when available.
    """
    pairs: list[tuple[float, int]] = []
    for t in trades or []:
        if t is None:
            continue
        score = t.get("score")
        if score is None:
            continue
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            continue

        win = t.get("win")
        if win is None:
            pnl = t.get("pnl_dollar")
            if pnl is None:
                pnl = t.get("pnl_pct")
            if pnl is None:
                # Need a closed outcome; skip.
                continue
            try:
                win = float(pnl) > 0
            except (TypeError, ValueError):
                continue

        pairs.append((score_f, 1 if bool(win) else 0))
    return pairs


def _decile_bins(pairs: list[tuple[float, int]]) -> list[dict]:
    """Fallback binning when sklearn is unavailable: group by score deciles."""
    if not pairs:
        return []
    scores = sorted(p[0] for p in pairs)
    n = len(scores)
    # Build up to 10 quantile edges
    n_bins = min(10, max(1, n // 5))
    edges: list[float] = []
    for i in range(1, n_bins):
        edges.append(scores[int(i * n / n_bins)])
    # Deduplicate edges
    edges = sorted(set(edges))

    bins: list[list[tuple[float, int]]] = [[] for _ in range(len(edges) + 1)]
    for s, y in pairs:
        placed = False
        for idx, edge in enumerate(edges):
            if s < edge:
                bins[idx].append((s, y))
                placed = True
                break
        if not placed:
            bins[-1].append((s, y))

    out = []
    for b in bins:
        if not b:
            continue
        lo = min(p[0] for p in b)
        hi = max(p[0] for p in b)
        wins = sum(p[1] for p in b)
        n_b = len(b)
        actual_wr = wins / n_b
        # "Predicted" WR = mean score / 100 (naive mapping)
        predicted_wr = sum(p[0] for p in b) / n_b / 100.0
        out.append({
            "score_range": [round(lo, 2), round(hi, 2)],
            "n": n_b,
            "actual_wr": round(actual_wr, 4),
            "predicted_wr": round(predicted_wr, 4),
        })
    return out


def _calibration_slope(pairs: list[tuple[float, int]]) -> float:
    """Linear regression of outcome on (score/100). Slope of 1.0 = perfectly
    calibrated in the linear-map sense.
    """
    if len(pairs) < 2:
        return float("nan")
    xs = [p[0] / 100.0 for p in pairs]
    ys = [float(p[1]) for p in pairs]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return float("nan")
    return num / den


def compute_score_calibration(trades: list[dict]) -> dict:
    """Isotonic calibration: score → P(win).

    Input: closed trades with {score, win: bool} (or pnl_dollar for win inference).
    Output:
        {
          'bins': [{'score_range': [60,65], 'n': 12,
                    'actual_wr': 0.58, 'predicted_wr': 0.50}, ...],
          'brier_score': float,
          'calibration_slope': float,   # 1.0 = perfectly calibrated
          'n_trades': int
        }

    Uses sklearn.isotonic.IsotonicRegression when available; falls back to
    decile binning otherwise.
    """
    pairs = _extract_score_win_pairs(trades)
    if not pairs:
        return _empty_report()

    bins: list[dict] = []
    predictions: list[float] = []
    outcomes: list[int] = []

    try:
        from sklearn.isotonic import IsotonicRegression  # type: ignore

        scores = [p[0] for p in pairs]
        wins = [p[1] for p in pairs]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(scores, wins)
        # Build bins on fixed 5-pt score ranges
        lo_score = int(min(scores))
        hi_score = int(max(scores)) + 1
        # Round to nearest 5
        lo_score = (lo_score // 5) * 5
        hi_score = ((hi_score + 4) // 5) * 5
        edges = list(range(lo_score, hi_score + 1, 5))
        if len(edges) < 2:
            edges = [lo_score, lo_score + 5]
        for i in range(len(edges) - 1):
            a, b = edges[i], edges[i + 1]
            members = [(s, y) for s, y in pairs if a <= s < b]
            if not members:
                continue
            actual_wr = sum(y for _, y in members) / len(members)
            midpoint = (a + b) / 2.0
            predicted = float(iso.predict([midpoint])[0])
            bins.append({
                "score_range": [a, b],
                "n": len(members),
                "actual_wr": round(actual_wr, 4),
                "predicted_wr": round(predicted, 4),
            })
        predictions = [float(iso.predict([s])[0]) for s in scores]
        outcomes = wins
    except ImportError:
        log.info("sklearn unavailable; using decile fallback for calibration")
        bins = _decile_bins(pairs)
        # Naive score/100 as the prediction for Brier.
        predictions = [p[0] / 100.0 for p in pairs]
        outcomes = [p[1] for p in pairs]
    except Exception as e:
        log.warning(f"Isotonic calibration failed ({e}); falling back to deciles")
        bins = _decile_bins(pairs)
        predictions = [p[0] / 100.0 for p in pairs]
        outcomes = [p[1] for p in pairs]

    bs = brier_score(predictions, outcomes)
    slope = _calibration_slope(pairs)

    def _round_or_none(x: float) -> Any:
        try:
            if x != x:  # NaN
                return None
            return round(float(x), 4)
        except Exception:
            return None

    return {
        "bins": bins,
        "brier_score": _round_or_none(bs),
        "calibration_slope": _round_or_none(slope),
        "n_trades": len(pairs),
    }


def save_calibration_report(path: str = _DEFAULT_REPORT_PATH) -> None:
    """Compute calibration from tracker.get_full_history() trades and persist it."""
    trades: list[dict] = []
    try:
        import tracker  # type: ignore
        hist = tracker.get_full_history() or {}
        trades = hist.get("trades", []) or []
    except Exception as e:
        log.warning(f"save_calibration_report: cannot load trade history: {e}")

    report = compute_score_calibration(trades)
    # Stamp generation time
    try:
        from datetime import datetime
        report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    except Exception:
        pass

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        log.info(f"Calibration report written to {path} (n={report.get('n_trades')})")
    except Exception as e:
        log.error(f"Failed to write calibration report: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    save_calibration_report()
    print(f"Calibration report saved to {_DEFAULT_REPORT_PATH}")
