"""engines/fibonacci.py — Fibonacci retracement/extension detector for the
BullVeda Patterns lens.

Mechanism (principle 2): institutional order-flow clusters at Fibonacci
retracement/extension ratios of the dominant swing because portfolio managers
build positions at pre-calculated price targets derived from the same ratios,
creating self-reinforcing support and resistance.

Mode-aware: daily (SWING) / weekly (POSITION) / monthly (INVESTMENT) bars.
Uses a fractal/zigzag pivot scan — window size scales with timeframe so the
"dominant swing" remains meaningful across all three horizons.

Honesty (principle 4): returns state="none" when no clear swing is detectable
(e.g. too few bars, perfectly flat price action, or swing prominence < floor).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple

NAME = "fibonacci"
LABEL = "Fibonacci"

# ── Fibonacci ratios ─────────────────────────────────────────────────
RETR_RATIOS = [0.0, 0.236, 0.382, 0.500, 0.618, 0.786, 1.0]
EXT_RATIOS  = [1.272, 1.618, 2.000]
GOLDEN_LO   = 0.618
GOLDEN_HI   = 0.650   # golden pocket zone

# ── timeframe windows (bar counts) ──────────────────────────────────
_TFW = {
    "Daily":   {"pivot_n": 5,  "lookback": 120, "bars_out": 100, "min_swing_bars": 10},
    "Weekly":  {"pivot_n": 3,  "lookback": 90,  "bars_out": 80,  "min_swing_bars": 6},
    "Monthly": {"pivot_n": 2,  "lookback": 60,  "bars_out": 60,  "min_swing_bars": 4},
}


def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── bar payload for the chart ────────────────────────────────────────
def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        rvol = float(r["rvol"]) if "rvol" in r.index and np.isfinite(r["rvol"]) else 1.0
        out.append({
            "o": round(float(r["Open"]),  2),
            "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2),
            "lo": round(float(r["Low"]),  2),
            "v": round(rvol, 2),
        })
    return out


# ── fractal pivot detection (vectorised) ────────────────────────────
def _find_pivots(df: pd.DataFrame, n: int
                 ) -> Tuple[pd.Series, pd.Series]:
    """Return boolean Series for swing highs and swing lows (fractal rule).

    A bar at index i is a pivot HIGH when its High is the highest in the
    surrounding 2n+1 window (n bars each side). Vectorised via rolling max/min.
    """
    highs = df["High"]
    lows  = df["Low"]
    roll_max = highs.rolling(2 * n + 1, center=True, min_periods=n + 1).max()
    roll_min = lows.rolling(2 * n + 1, center=True, min_periods=n + 1).min()
    ph = highs == roll_max          # pivot highs
    pl = lows  == roll_min          # pivot lows
    return ph, pl


# ── dominant swing identification ────────────────────────────────────
def _find_dominant_swing(
    df: pd.DataFrame, tf: str
) -> Optional[Dict[str, Any]]:
    """Find the most significant (hi, lo) swing pair in the lookback window.

    Strategy:
    1. Locate all fractal pivot highs and lows within the TF lookback.
    2. Enumerate all valid (swing_low, swing_high) or (swing_high, swing_low)
       adjacent pairs.
    3. Pick the pair with the largest absolute price range *relative to the ATR*
       (prominence) that covers at least min_swing_bars.
    4. Determine direction: up-swing = lo precedes hi; down-swing = hi precedes lo.
    """
    w = _tfw(tf)
    lookback = min(w["lookback"], len(df))
    sub = df.iloc[-lookback:].copy()
    sub_i = list(range(len(sub)))          # local indices within sub
    # absolute index offset into full df (for bar chart alignment)
    abs_offset = len(df) - lookback

    ph, pl = _find_pivots(sub, w["pivot_n"])

    highs_idx = [i for i, v in enumerate(ph.values) if v]
    lows_idx  = [i for i, v in enumerate(pl.values) if v]

    if not highs_idx or not lows_idx:
        return None

    atr_mean = float(sub["atr"].mean()) if "atr" in sub.columns else 1.0
    if atr_mean <= 0:
        atr_mean = 1.0

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0

    # Try every (low, high) pair (upswing) and (high, low) pair (downswing)
    # within a reasonable recency window (last 2/3 of lookback)
    recency_start = lookback // 3

    def _try_pair(i_lo: int, i_hi: int, direction: str) -> None:
        nonlocal best, best_score
        bar_span = abs(i_hi - i_lo)
        if bar_span < w["min_swing_bars"]:
            return
        # ensure both pivots are within the recency window
        if min(i_lo, i_hi) < recency_start and max(i_lo, i_hi) < recency_start:
            return
        lo_price = float(sub["Low"].iloc[i_lo])
        hi_price = float(sub["High"].iloc[i_hi])
        rng = hi_price - lo_price
        if rng <= 0:
            return
        prominence = rng / atr_mean         # swing size in ATR units
        # Prefer recent, large, and prominent swings
        recency_bonus = (max(i_lo, i_hi) / lookback) ** 1.5
        score = prominence * recency_bonus
        if score > best_score:
            best_score = score
            best = {
                "direction": direction,
                "lo_price": lo_price,
                "hi_price": hi_price,
                "lo_i": i_lo,   # local index in sub
                "hi_i": i_hi,
                "lo_abs": abs_offset + i_lo,  # bar index for chart
                "hi_abs": abs_offset + i_hi,
                "bar_span": bar_span,
                "prominence": round(prominence, 2),
            }

    for i_lo in lows_idx:
        for i_hi in highs_idx:
            if i_lo < i_hi:          # up-swing: lo before hi
                _try_pair(i_lo, i_hi, "up")

    for i_hi in highs_idx:
        for i_lo in lows_idx:
            if i_hi < i_lo:          # down-swing: hi before lo
                _try_pair(i_lo, i_hi, "down")

    return best


# ── level respect (how cleanly price bounced at a level) ─────────────
def _count_respect(df: pd.DataFrame, price: float, atr: float,
                   since_bar: int = 0) -> int:
    """Count bars where Low came within 0.5 ATR of the level and Close ended above it."""
    sub = df.iloc[since_bar:]
    touch = (sub["Low"] <= price + 0.5 * atr) & (sub["Low"] >= price - 1.5 * atr)
    respected = touch & (sub["Close"] >= price - 0.25 * atr)
    return int(respected.sum())


# ── build levels list ────────────────────────────────────────────────
def _build_levels(swing: Dict[str, Any], cur_close: float,
                  df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    lo = swing["lo_price"]
    hi = swing["hi_price"]
    rng = hi - lo
    direction = swing["direction"]

    atr_val = float(df["atr"].iloc[-1]) if "atr" in df.columns else rng * 0.02
    levels: List[Dict[str, Any]] = []

    # Retracement levels (price pulls back FROM the swing completion)
    for ratio in [0.236, 0.382, 0.500, 0.618, 0.786]:
        if direction == "up":
            price = hi - ratio * rng
            role = "support"
        else:
            price = lo + ratio * rng
            role = "resistance"

        price = round(price, 2)
        dist = abs(cur_close - price)
        # respect: count bounces at this level in the tail of df after swing start
        respect = _count_respect(df, price, atr_val, since_bar=swing["lo_abs"] if direction == "up" else swing["hi_abs"])
        levels.append({
            "ratio": ratio,
            "label": f"{ratio:.3f}",
            "price": price,
            "kind": "retr",
            "role": role,
            "hit": respect > 0,
            "respect": respect,
            "dist_atr": round(dist / atr_val, 2) if atr_val > 0 else None,
        })

    # Extension levels
    for ratio in EXT_RATIOS:
        if direction == "up":
            price = hi + (ratio - 1.0) * rng
            role = "resistance"
        else:
            price = lo - (ratio - 1.0) * rng
            role = "support"

        price = round(price, 2)
        levels.append({
            "ratio": ratio,
            "label": f"{ratio:.3f}",
            "price": price,
            "kind": "ext",
            "role": role,
            "hit": False,
            "respect": 0,
            "dist_atr": None,
        })

    return levels


# ── nearest level to current price ───────────────────────────────────
def _nearest_level(levels: List[Dict[str, Any]], cur: float,
                   role_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
    candidates = [lv for lv in levels if role_filter is None or lv["role"] == role_filter]
    if not candidates:
        return None
    return min(candidates, key=lambda lv: abs(lv["price"] - cur))


# ── golden pocket ────────────────────────────────────────────────────
def _golden_pocket(swing: Dict[str, Any]) -> Dict[str, float]:
    lo, hi, rng = swing["lo_price"], swing["hi_price"], swing["hi_price"] - swing["lo_price"]
    if swing["direction"] == "up":
        gp_hi = round(hi - GOLDEN_LO * rng, 2)
        gp_lo = round(hi - GOLDEN_HI * rng, 2)
    else:
        gp_lo = round(lo + GOLDEN_LO * rng, 2)
        gp_hi = round(lo + GOLDEN_HI * rng, 2)
    return {"lo": gp_lo, "hi": gp_hi}


# ── confidence score ─────────────────────────────────────────────────
def _compute_confidence(swing: Dict[str, Any], levels: List[Dict[str, Any]]) -> float:
    """Confidence from swing prominence and level respect count."""
    prom_score = min(1.0, swing["prominence"] / 15.0)        # 15 ATR = full score
    span_score = min(1.0, swing["bar_span"] / 30.0)           # 30 bars = full score
    respected   = sum(1 for lv in levels if lv.get("hit") and lv["kind"] == "retr")
    resp_score  = min(1.0, respected / 3.0)                   # 3 respected = full
    # weighted
    conf = 0.45 * prom_score + 0.25 * span_score + 0.30 * resp_score
    return round(min(0.95, max(0.10, conf)), 2)


# ── plain-English read ───────────────────────────────────────────────
def _build_read(swing: Dict[str, Any], levels: List[Dict[str, Any]],
                golden: Dict[str, float], cur_close: float, tf: str) -> str:
    lo = swing["lo_price"]
    hi = swing["hi_price"]
    direction = swing["direction"]
    gp_str = f"${golden['lo']:.2f}–${golden['hi']:.2f}"

    nearest_sup = _nearest_level(levels, cur_close, "support")
    nearest_res = _nearest_level(levels, cur_close, "resistance")
    ext_t1 = next((lv for lv in levels if lv["kind"] == "ext" and lv["ratio"] == 1.272), None)
    ext_t2 = next((lv for lv in levels if lv["kind"] == "ext" and lv["ratio"] == 1.618), None)

    if direction == "up":
        sup_str = f"${nearest_sup['price']:.2f} ({nearest_sup['label']} retr)" if nearest_sup else "—"
        res_str = f"${ext_t1['price']:.2f} (1.272 ext)" if ext_t1 else (f"${nearest_res['price']:.2f}" if nearest_res else "—")
        return (
            f"{tf} swing ${lo:.2f}→${hi:.2f}; golden pocket {gp_str}. "
            f"Nearest support {sup_str}; primary target {res_str}"
            + (f", extension {ext_t2['price']:.2f} (1.618)" if ext_t2 else "") + "."
        )
    else:
        res_str = f"${nearest_res['price']:.2f} ({nearest_res['label']} retr)" if nearest_res else "—"
        ext_t1_str = f"${ext_t1['price']:.2f} (1.272 ext)" if ext_t1 else "—"
        return (
            f"{tf} swing ${hi:.2f}→${lo:.2f} (downtrend); resistance pocket {gp_str}. "
            f"Nearest resistance {res_str}; downside target {ext_t1_str}."
        )


# ── stat block (mirrors FibStat) ─────────────────────────────────────
def _build_stat(swing: Dict[str, Any], golden: Dict[str, float],
                levels: List[Dict[str, Any]], cur_close: float) -> Dict[str, Any]:
    lo, hi = swing["lo_price"], swing["hi_price"]
    direction = swing["direction"]

    # nearest support cluster (most-respected retracement)
    retr_levels = [lv for lv in levels if lv["kind"] == "retr"]
    hit_levels  = sorted([lv for lv in retr_levels if lv.get("hit")], key=lambda l: -l["respect"])
    best_hit = hit_levels[0] if hit_levels else None

    ext_t1 = next((lv for lv in levels if lv["kind"] == "ext" and lv["ratio"] == 1.272), None)
    ext_t2 = next((lv for lv in levels if lv["kind"] == "ext" and lv["ratio"] == 1.618), None)

    swing_label = f"${lo:.2f} → ${hi:.2f}" if direction == "up" else f"${hi:.2f} → ${lo:.2f}"
    gp_label = f"${golden['lo']:.2f} – ${golden['hi']:.2f}"

    cluster_label = f"${best_hit['price']:.2f} · {best_hit['respect']}-hit" if best_hit else "no confirmed cluster"
    next_tgt = f"${ext_t1['price']:.2f}" if ext_t1 else (f"${ext_t2['price']:.2f}" if ext_t2 else "—")

    return {
        "swing":            swing_label,
        "golden_pocket":    gp_label,
        "support_cluster":  cluster_label,
        "next_target":      next_tgt,
    }


# ── level enrichment for JSX rendering ──────────────────────────────
def _enrich_levels_for_jsx(levels: List[Dict[str, Any]],
                            cur_close: float) -> List[Dict[str, Any]]:
    """Add tone, status text, conf numeric for the React tables."""
    out = []
    for lv in levels:
        ratio = lv["ratio"]
        kind  = lv["kind"]

        # tone
        if kind == "ext":
            tone = "gn"
        elif ratio == 0.618:
            tone = "amb"
        elif ratio in (0.382, 0.500, 0.786):
            tone = "cy"
        else:
            tone = "ink-2"

        # role label
        if kind == "retr":
            if ratio == 0.236:
                role = "shallow"
            elif ratio == 0.382:
                role = "moderate"
            elif ratio == 0.500:
                role = "mid-point"
            elif ratio == 0.618:
                role = "golden pocket"
            else:
                role = "deep / last defense"
        else:
            if ratio == 1.272:
                role = "T1 · primary objective"
            elif ratio == 1.618:
                role = "T2 · golden extension"
            else:
                role = "T3 · parabolic stretch"

        # status text
        if kind == "ext":
            # check if already reached
            if lv["role"] == "resistance" and cur_close >= lv["price"]:
                status = "exceeded"
            elif lv["role"] == "support" and cur_close <= lv["price"]:
                status = "exceeded"
            else:
                status = "projected"
        else:
            if lv.get("hit") and lv["respect"] >= 2:
                status = f"held ({lv['respect']}-hit)"
            elif lv.get("hit"):
                status = "touched"
            else:
                status = "untested"

        # confidence for retr levels
        if kind == "retr":
            if lv.get("hit") and lv["respect"] >= 3:
                conf = round(min(0.92, 0.55 + lv["respect"] * 0.08), 2)
            elif lv.get("hit"):
                conf = round(0.45 + lv["respect"] * 0.1, 2)
            else:
                conf = None
        else:
            # extension: decreasing confidence
            if ratio == 1.272:
                conf = 0.62
            elif ratio == 1.618:
                conf = 0.44
            else:
                conf = 0.22

        enriched = dict(lv)
        enriched.update({"tone": tone, "role_label": role, "status": status, "conf": conf})
        out.append(enriched)

    return out


# ────────────────────────────────────────────────────────────────────
# main detect()
# ────────────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Fibonacci retracement/extension detector.

    Returns the full payload consumed by FibonacciView. Never raises.
    """
    tf = meta.get("tf", "Daily")
    w  = _tfw(tf)

    # ── guard: need enough bars ──────────────────────────────────────
    if df is None or len(df) < 30:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Insufficient {tf.lower()} history ({len(df) if df is not None else 0} bars < 30 needed).",
            "cur_close": None,
        }

    cur_close = round(float(df["Close"].iloc[-1]), 2)

    # ── find dominant swing ──────────────────────────────────────────
    swing = _find_dominant_swing(df, tf)
    if swing is None:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"No significant pivot-based swing found in the last {w['lookback']} {tf.lower()} bars.",
            "cur_close": cur_close,
        }

    # minimum prominence gate — suppress noise
    if swing["prominence"] < 1.5:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Swing prominence {swing['prominence']:.1f} ATR is too small (min 1.5) — no meaningful Fib structure.",
            "cur_close": cur_close,
        }

    lo  = swing["lo_price"]
    hi  = swing["hi_price"]

    # ── compute levels ───────────────────────────────────────────────
    levels_raw = _build_levels(swing, cur_close, df, tf)
    golden     = _golden_pocket(swing)
    confidence = _compute_confidence(swing, levels_raw)
    read       = _build_read(swing, levels_raw, golden, cur_close, tf)
    stat       = _build_stat(swing, golden, levels_raw, cur_close)
    levels_jsx = _enrich_levels_for_jsx(levels_raw, cur_close)

    # ── invalidation: close beyond the swing extreme ─────────────────
    if swing["direction"] == "up":
        inv_price = round(lo * 0.995, 2)
        inv_note  = (f"Daily close below the swing low ${lo:.2f} breaks the "
                     f"Fibonacci structure — projections void.")
    else:
        inv_price = round(hi * 1.005, 2)
        inv_note  = (f"Daily close above the swing high ${hi:.2f} breaks the "
                     f"Fibonacci structure — downside projections void.")

    # ── windowed bars for the chart ──────────────────────────────────
    bars_n = min(w["bars_out"], len(df))
    bars   = _bar_payload(df.iloc[-bars_n:])

    # ── chart annotation helpers ─────────────────────────────────────
    # swing lo/hi indices relative to the windowed bars slice
    full_len  = len(df)
    lo_i_chart = swing["lo_abs"] - (full_len - bars_n)
    hi_i_chart = swing["hi_abs"] - (full_len - bars_n)

    # ── split levels by kind for JSX tables ─────────────────────────
    retr_levels = [lv for lv in levels_jsx if lv["kind"] == "retr"]
    ext_levels  = [lv for lv in levels_jsx if lv["kind"] == "ext"]

    return {
        "ok": True,
        "source": "real",
        "state": "real",
        "confidence": confidence,
        "bars": bars,
        "swing": {
            "lo":   lo,
            "hi":   hi,
            "lo_i": max(0, lo_i_chart),
            "hi_i": max(0, hi_i_chart),
            "direction": swing["direction"],
            "prominence": swing["prominence"],
            "bar_span": swing["bar_span"],
        },
        "levels": levels_jsx,          # all levels (used for chart hlines)
        "retr_levels": retr_levels,     # retracement grid table
        "ext_levels":  ext_levels,      # extension targets table
        "golden_pocket": golden,        # {lo, hi}
        "current": {
            "close": cur_close,
            "nearest_support":    _nearest_level(levels_raw, cur_close, "support"),
            "nearest_resistance": _nearest_level(levels_raw, cur_close, "resistance"),
        },
        "stat": stat,
        "invalidation": {"price": inv_price, "note": inv_note},
        "read": read,
        "cur_close": cur_close,
    }
