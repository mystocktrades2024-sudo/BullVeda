"""engines/montecarlo.py — Monte Carlo path-simulation engine for the BullVeda
Patterns lens.

Mechanism (principle 2): bootstrapping the asset's own recent return distribution
forward gives a path-dependent probability of reaching a target before a stop —
honest positive-expectancy evidence conditional on the setup holding, because it
uses the stock's actual fat-tailed, autocorrelated return process rather than the
geometric-Brownian-motion approximation.

Block bootstrap of historical log-returns is preferred (preserves short-run
autocorrelation and fat tails). GBM fallback is used only when the window is too
short to bootstrap meaningfully.

IMPORTANT: RNG is seeded from hash(ticker+mode) → fully deterministic and
cache-safe — two calls for the same (ticker, mode) return identical paths.

Outputs shape (mirrors the existing JSX fixture contract):
  start, t1, stop, numPaths, numDays, skew,
  bands  { p10, p25, p50, p75, p90 }   per-day percentile price arrays,
  p      { p5, p25, p50, p75, p95 }    terminal percentile prices,
  hist   [ float counts ],  histLo, histHi,
  t1First, stopFirst   (probabilities),
  median (float), read (str), confidence (0-1), stat { ... },
  bars   [ {o,c,hi,lo,v} ]   windowed recent candles for CandleChart.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME  = "montecarlo"
LABEL = "Monte Carlo"

# ── horizon: how many trading-period bars to simulate ──────────────────────────
_HORIZON = {
    "Daily":   10,   # SWING ≈ 2 weeks
    "Weekly":  13,   # POSITION ≈ 1 quarter
    "Monthly": 12,   # INVESTMENT ≈ 1 year
}
# bars fed to the chart (lookback window for CandleChart)
_CHART_BARS = {
    "Daily":   80,
    "Weekly":  80,
    "Monthly": 60,
}
# block bootstrap block size (in bars)
_BLOCK = {
    "Daily":   5,    # 1 week
    "Weekly":  4,    # 1 month
    "Monthly": 3,    # 1 quarter
}

N_PATHS = 2000
N_HIST_BINS = 22

# ATR multiples for target and stop when no structure is available
ATR_T1_MULT   = 2.5
ATR_STOP_MULT = 1.5


def _seed(ticker: str, mode: str) -> int:
    h = hashlib.md5(f"{ticker}|{mode}".encode()).digest()
    return int.from_bytes(h[:4], "little")


def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(float(r.get("rvol", 1.0)), 2),
        })
    return out


def _skewness(arr: np.ndarray) -> float:
    """Sample skewness (Pearson)."""
    n = len(arr)
    if n < 3:
        return 0.0
    m = arr.mean()
    s = arr.std(ddof=1)
    if s == 0:
        return 0.0
    return float(((arr - m) ** 3).mean() / (s ** 3))


def _block_bootstrap(log_rets: np.ndarray, n_days: int, n_paths: int,
                     block: int, rng: np.random.Generator) -> np.ndarray:
    """Return (n_paths, n_days) matrix of log returns via block bootstrap."""
    n = len(log_rets)
    if n < block * 2:
        # fall back to IID draw
        return rng.choice(log_rets, size=(n_paths, n_days), replace=True)
    n_blocks = int(np.ceil(n_days / block))
    # draw random starting positions (with replacement)
    starts = rng.integers(0, n - block + 1, size=(n_paths, n_blocks))
    # build index matrix: each row is a sequence of bar indices
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_paths, -1)[:, :n_days]
    return log_rets[idx]


def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Monte Carlo simulation over the asset's own bootstrapped log-return history."""
    tf   = meta.get("tf", "Daily")
    mode = meta.get("mode", "SWING")

    n_days  = _HORIZON.get(tf, 10)
    n_chart = _CHART_BARS.get(tf, 80)
    block   = _BLOCK.get(tf, 5)

    if df is None or len(df) < 30:
        return {
            "ok": True, "source": "real", "montecarlo": None,
            "state": "none", "message": "Insufficient bar history for simulation.",
            "cur_close": None,
        }

    cur_close = round(float(df["Close"].iloc[-1]), 2)
    atr_val   = float(df["atr"].iloc[-1]) if "atr" in df.columns else cur_close * 0.015

    # ── compute targets from ATR ────────────────────────────────────────────────
    t1   = round(cur_close + ATR_T1_MULT   * atr_val, 2)
    stop = round(cur_close - ATR_STOP_MULT * atr_val, 2)

    # ── log returns ────────────────────────────────────────────────────────────
    closes    = df["Close"].values.astype(float)
    log_rets  = np.diff(np.log(closes))
    log_rets  = log_rets[np.isfinite(log_rets)]
    if len(log_rets) < 20:
        return {
            "ok": True, "source": "real", "montecarlo": None,
            "state": "none", "message": "Too few finite returns for simulation.",
            "cur_close": cur_close,
        }

    drift = float(log_rets.mean())
    vol   = float(log_rets.std(ddof=1))

    # ── seeded RNG ─────────────────────────────────────────────────────────────
    seed = _seed(ticker, mode)
    rng  = np.random.default_rng(seed)

    # ── simulate N_PATHS × n_days block-bootstrapped log returns ───────────────
    drawn = _block_bootstrap(log_rets, n_days, N_PATHS, block, rng)   # (N_PATHS, n_days)

    # price paths: shape (N_PATHS, n_days+1)  — col 0 = cur_close
    cumlog = np.cumsum(drawn, axis=1)
    price_paths = cur_close * np.exp(cumlog)                          # (N_PATHS, n_days)
    full_paths  = np.hstack([np.full((N_PATHS, 1), cur_close), price_paths])  # (N_PATHS, n_days+1)

    # ── first-hit probabilities ────────────────────────────────────────────────
    t1_hit   = np.zeros(N_PATHS, dtype=bool)
    stop_hit = np.zeros(N_PATHS, dtype=bool)
    for d in range(n_days):
        col = price_paths[:, d]
        t1_now   = col >= t1
        stop_now = col <= stop
        newly_t1   = t1_now   & ~t1_hit & ~stop_hit
        newly_stop = stop_now & ~t1_hit & ~stop_hit
        t1_hit   |= newly_t1
        stop_hit |= newly_stop

    p_t1   = float(t1_hit.sum())   / N_PATHS
    p_stop = float(stop_hit.sum()) / N_PATHS

    # ── terminal distribution ──────────────────────────────────────────────────
    terminal = full_paths[:, -1]
    terminal_sorted = np.sort(terminal)

    def pct(q: float) -> float:
        return float(terminal_sorted[min(N_PATHS - 1, int(q * N_PATHS))])

    median_px = pct(0.5)
    skew      = round(_skewness(terminal), 3)

    # percentile bands per day (for the cone)
    qs = [0.10, 0.25, 0.50, 0.75, 0.90]
    bands_arr = np.quantile(full_paths, qs, axis=0)   # (5, n_days+1)

    bands = {
        "p10": [round(float(v), 2) for v in bands_arr[0]],
        "p25": [round(float(v), 2) for v in bands_arr[1]],
        "p50": [round(float(v), 2) for v in bands_arr[2]],
        "p75": [round(float(v), 2) for v in bands_arr[3]],
        "p90": [round(float(v), 2) for v in bands_arr[4]],
    }

    # histogram (22 buckets across terminal range)
    t_lo, t_hi = float(terminal_sorted[0]), float(terminal_sorted[-1])
    bw = (t_hi - t_lo) / N_HIST_BINS if t_hi > t_lo else 1.0
    hist_counts, _ = np.histogram(terminal, bins=N_HIST_BINS,
                                  range=(t_lo - 1e-9, t_hi + 1e-9))
    hist = [int(c) for c in hist_counts]

    # ── confidence: based on sample size and whether edge is positive ──────────
    edge_pct = p_t1 * (t1 / cur_close - 1.0) - p_stop * (1.0 - stop / cur_close)
    sample_conf  = min(1.0, len(log_rets) / 200)
    edge_conf    = min(1.0, max(0.0, (edge_pct + 0.02) / 0.08))
    confidence   = round(float(sample_conf * 0.5 + edge_conf * 0.5), 2)

    # ── bars for CandleChart ───────────────────────────────────────────────────
    window_df = df.tail(n_chart)
    bars      = _bar_payload(window_df)

    # ── read sentence ──────────────────────────────────────────────────────────
    med_ret_pct = round((median_px / cur_close - 1.0) * 100, 1)
    direction   = "right" if skew > 0.1 else ("left" if skew < -0.1 else "symmetric")
    read = (
        f"Over {n_days} {tf.lower()} bars, median terminal {'+' if med_ret_pct >= 0 else ''}{med_ret_pct}%; "
        f"P(T1 first) {round(p_t1 * 100)}% vs P(stop first) {round(p_stop * 100)}% — "
        f"{'positive' if edge_pct > 0 else 'negative'} expectancy "
        f"({direction}-skewed distribution). "
        f"Block-bootstrapped from {len(log_rets)} historical {tf.lower()} returns."
    )

    # ── stat block (mirrors MCStat in JSX) ────────────────────────────────────
    rr_ratio = round((t1 - cur_close) / max(cur_close - stop, 0.01), 2)
    stat = {
        "median_ret_pct": med_ret_pct,
        "p_t1":           round(p_t1,   3),
        "p_stop":         round(p_stop, 3),
        "edge_pct":       round(edge_pct * 100, 2),
        "rr_ratio":       rr_ratio,
        "drift_ann":      round(float(drift * (252 if tf == "Daily" else 52 if tf == "Weekly" else 12)), 3),
        "vol_ann":        round(float(vol   * np.sqrt(252 if tf == "Daily" else 52 if tf == "Weekly" else 12)), 3),
        "skew":           skew,
        "n_obs":          len(log_rets),
    }

    return {
        "ok":        True,
        "source":    "real",
        "state":     "real",
        "confidence": confidence,
        # price anchors
        "start":    cur_close,
        "t1":       t1,
        "stop":     stop,
        "cur_close": cur_close,
        # simulation outputs
        "numPaths": N_PATHS,
        "numDays":  n_days,
        "skew":     skew,
        "median":   round(median_px, 2),
        "bands":    bands,
        "p": {
            "p5":  round(pct(0.05), 2),
            "p25": round(pct(0.25), 2),
            "p50": round(pct(0.50), 2),
            "p75": round(pct(0.75), 2),
            "p95": round(pct(0.95), 2),
        },
        "t1First":  round(p_t1,   3),
        "stopFirst": round(p_stop, 3),
        "hist":     hist,
        "histLo":   round(t_lo, 2),
        "histHi":   round(t_hi, 2),
        # view helpers
        "bars":      bars,
        "read":      read,
        "stat":      stat,
    }
