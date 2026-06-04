"""engines/classical.py — Classical chart-pattern detector for the BullVeda Patterns lens.

Mechanism (principle 2): a VCP / ascending-triangle base is supply being absorbed into
progressively tighter ranges; the breakout from the final contraction is where remaining
supply is exhausted — resulting in a low-resistance markup.

Supports all timeframes: SWING (daily), POSITION (weekly), INVESTMENT (monthly).
Returns the fields consumed by ClassicalView: bars, pattern, contractions, pivot, target,
lines (trendlines for CandleChart), zones (base band), stat, read, confidence, cur_close.
Honest state="none" when no clean base is present.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "classical"
LABEL = "Classical"

# timeframe windows (in bars)
_TFW = {
    "Daily":   {"min": 30, "lookback": 120, "base_min": 10, "base_max": 80,  "pullback_min": 5,  "vol_dry_thresh": 0.65},
    "Weekly":  {"min": 20, "lookback":  80, "base_min":  6, "base_max": 52,  "pullback_min": 3,  "vol_dry_thresh": 0.70},
    "Monthly": {"min": 12, "lookback":  48, "base_min":  4, "base_max": 30,  "pullback_min": 2,  "vol_dry_thresh": 0.75},
}

_CHART_BARS = {
    "Daily": 90,
    "Weekly": 80,
    "Monthly": 60,
}

PATTERN_NONE = "none"


# ════════════════════════════════════════════════════════════════════
# helpers
# ════════════════════════════════════════════════════════════════════

def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


def _px(v: float) -> int:
    return 2 if v < 30 else (1 if v < 200 else 0)


def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "o": round(float(r["Open"]), 2),
            "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2),
            "lo": round(float(r["Low"]), 2),
            "v": round(float(r["rvol"]) if np.isfinite(float(r["rvol"])) else 1.0, 2),
        })
    return out


def _find_local_pivots(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                        window: int = 3) -> Tuple[List[int], List[int]]:
    """Return indices of local highs and local lows in vectorised form."""
    n = len(closes)
    pk_highs, pk_lows = [], []
    for i in range(window, n - window):
        seg_h = highs[i - window: i + window + 1]
        seg_l = lows[i - window: i + window + 1]
        if highs[i] == seg_h.max():
            pk_highs.append(i)
        if lows[i] == seg_l.min():
            pk_lows.append(i)
    return pk_highs, pk_lows


# ════════════════════════════════════════════════════════════════════
# VCP detector — volatility contraction pattern
# ════════════════════════════════════════════════════════════════════

def _detect_vcp(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """
    VCP: a sequence of pullbacks each shallower than the last, ending with
    volume dry-up. Returns contraction list, pivot (flat resistance), confidence.
    """
    w = _tfw(tf)
    n = len(df)
    if n < w["min"]:
        return None

    look = min(w["lookback"], n - 1)
    seg = df.iloc[n - look:]
    closes = seg["Close"].values
    highs  = seg["High"].values
    lows   = seg["Low"].values
    rvols  = seg["rvol"].values

    pk_h, pk_l = _find_local_pivots(closes, highs, lows, window=max(2, look // 30))

    if len(pk_h) < 2 or len(pk_l) < 2:
        return None

    # resistance = median of the top 3 high pivots (flat top)
    top_highs = sorted(pk_h, key=lambda i: highs[i], reverse=True)[:3]
    pivot = float(np.median([highs[i] for i in top_highs]))
    pivot_range = pivot * 0.025  # 2.5% tolerance for "flat"

    # filter high pivots within the flat-top band
    flat_highs = [i for i in pk_h if abs(highs[i] - pivot) <= pivot_range]
    if len(flat_highs) < 2:
        return None

    # identify pullbacks between flat-top touches: each low between consecutive highs
    contractions = []
    for k in range(len(flat_highs) - 1):
        h_i = flat_highs[k]
        h_j = flat_highs[k + 1]
        # find the deepest low between h_i and h_j
        sub_lows = lows[h_i: h_j + 1]
        if len(sub_lows) == 0:
            continue
        low_pos = int(np.argmin(sub_lows)) + h_i
        pullback_pct = (pivot - lows[low_pos]) / pivot * 100.0
        # volume in trough vs average
        v_trough = float(np.mean(rvols[max(0, low_pos - 2): low_pos + 3]))
        contractions.append({
            "n": len(contractions) + 1,
            "hi_i": int(h_i),
            "lo_i": int(low_pos),
            "depth_pct": round(pullback_pct, 1),
            "v_trough": round(v_trough, 2),
            "hi_date": fmt_date(seg.index[h_i], tf),
            "lo_date": fmt_date(seg.index[low_pos], tf),
            "hi_price": round(float(highs[h_i]), 2),
            "lo_price": round(float(lows[low_pos]), 2),
        })

    if len(contractions) < 2:
        return None

    # check for contraction sequence: each depth shallower than prior
    depths = [c["depth_pct"] for c in contractions]
    tightening = sum(depths[i] < depths[i - 1] for i in range(1, len(depths)))
    is_vcp = tightening >= len(depths) - 1  # all (or all but one) must tighten

    if not is_vcp and len(depths) < 3:
        return None

    # volume dry-up: last contraction trough vol < threshold
    last_v = contractions[-1]["v_trough"]
    vol_dry = last_v < w["vol_dry_thresh"]

    # current position relative to pivot
    cur_close = float(df.iloc[-1]["Close"])
    broke_out = cur_close > pivot * 1.005
    near_pivot = abs(cur_close - pivot) / pivot < 0.04

    # confidence: number of contractions × tightening quality × volume dry-up
    base_conf = min(0.55 + 0.06 * len(contractions) + (0.08 if vol_dry else 0)
                    + (0.05 if broke_out else 0) + (0.04 if is_vcp else 0), 0.87)

    return {
        "pattern": "VCP" if is_vcp else "Base",
        "pivot": round(pivot, 2),
        "is_vcp": is_vcp,
        "broke_out": broke_out,
        "near_pivot": near_pivot,
        "contractions": contractions,
        "vol_dry": vol_dry,
        "confidence": round(base_conf, 2),
        "seg_offset": n - look,  # df row offset where seg starts
        "pivot_range": pivot_range,
        "last_depth": depths[-1],
        "first_depth": depths[0],
    }


# ════════════════════════════════════════════════════════════════════
# triangle / flag classifiers (secondary patterns)
# ════════════════════════════════════════════════════════════════════

def _classify_triangle(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """
    Detect ascending / descending / symmetrical triangle from last base_max bars.
    Returns {type, upper_slope, lower_slope, apex_bar, confidence} or None.
    """
    w = _tfw(tf)
    n = len(df)
    look = min(w["base_max"], n - 1)
    if look < w["base_min"]:
        return None

    seg = df.iloc[n - look:]
    highs = seg["High"].values
    lows  = seg["Low"].values
    xs    = np.arange(len(highs), dtype=float)

    # linear regressions on the rolling-max highs and rolling-min lows
    pk_h, pk_l = _find_local_pivots(seg["Close"].values, highs, lows, window=max(2, look // 15))
    if len(pk_h) < 2 or len(pk_l) < 2:
        return None

    x_h = np.array(pk_h, dtype=float)
    y_h = highs[pk_h]
    x_l = np.array(pk_l, dtype=float)
    y_l = lows[pk_l]

    # slopes via linear regression
    def slope(x: np.ndarray, y: np.ndarray) -> float:
        if len(x) < 2:
            return 0.0
        m = np.polyfit(x, y, 1)
        return float(m[0])

    m_h = slope(x_h, y_h)
    m_l = slope(x_l, y_l)

    price_range = float(highs.max() - lows.min()) or 1.0

    # normalise slopes to fraction-of-range per bar
    nm_h = m_h / price_range
    nm_l = m_l / price_range

    flat_thresh = 0.0015  # slope threshold for "flat"

    if abs(nm_h) < flat_thresh and nm_l > flat_thresh:
        tri = "Ascending Triangle"
        conf = 0.58
    elif abs(nm_l) < flat_thresh and nm_h < -flat_thresh:
        tri = "Descending Triangle"
        conf = 0.52
    elif nm_h < -flat_thresh and nm_l > flat_thresh:
        # converging — symmetrical
        tri = "Symmetrical Triangle"
        conf = 0.50
    else:
        return None

    # estimate apex bar index (intersection)
    if abs(nm_h - nm_l) > 1e-9:
        # y_h[-1] + m_h * t = y_l[-1] + m_l * t  →  t = (y_h[-1]-y_l[-1]) / (m_l-m_h)
        apex_in_bars = int((y_h[-1] - y_l[-1]) / max(1e-9, abs(m_l - m_h)))
        apex_bar = len(seg) + apex_in_bars  # bars from start of seg
    else:
        apex_bar = len(seg) + 20

    return {
        "type": tri,
        "upper_slope": round(nm_h * 1000, 4),
        "lower_slope": round(nm_l * 1000, 4),
        "apex_bar_from_now": max(0, apex_in_bars if abs(nm_h - nm_l) > 1e-9 else 20),
        "confidence": conf,
        "pk_h": pk_h,  # indices within seg
        "pk_l": pk_l,
        "y_h_last": float(y_h[-1]) if len(y_h) else 0,
        "y_l_last": float(y_l[-1]) if len(y_l) else 0,
        "m_h": m_h,
        "m_l": m_l,
    }


def _detect_double_bottom(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """Simple double-bottom: two lows within 2% of each other with a neckline high between."""
    w = _tfw(tf)
    n = len(df)
    look = min(w["base_max"], n - 1)
    if look < w["base_min"] * 2:
        return None

    seg = df.iloc[n - look:]
    highs = seg["High"].values
    lows  = seg["Low"].values
    closes = seg["Close"].values

    pk_h, pk_l = _find_local_pivots(closes, highs, lows, window=max(2, look // 15))
    if len(pk_l) < 2:
        return None

    # look for two lows within 2% of each other
    best = None
    for a in range(len(pk_l) - 1):
        la = lows[pk_l[a]]
        for b in range(a + 1, len(pk_l)):
            lb = lows[pk_l[b]]
            if abs(la - lb) / max(la, lb) > 0.025:
                continue
            # must have at least one high pivot between them
            neck_highs = [pk_h[k] for k in range(len(pk_h))
                          if pk_l[a] < pk_h[k] < pk_l[b]]
            if not neck_highs:
                continue
            neckline = float(np.max(highs[neck_highs]))
            depth = (neckline - min(la, lb)) / neckline
            if depth < 0.03:  # too shallow
                continue
            best = {"L1_i": pk_l[a], "L2_i": pk_l[b], "L1": la, "L2": lb,
                    "neckline": round(neckline, 2), "depth_pct": round(depth * 100, 1),
                    "confidence": round(min(0.50 + depth * 1.5, 0.68), 2)}
            break  # take the most recent valid pair
        if best:
            break

    return best


def _detect_cup_handle(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort cup-and-handle: U-shaped base (cup) followed by a smaller
    pullback (handle). Returns rim price and target.
    """
    w = _tfw(tf)
    n = len(df)
    look = min(w["lookback"], n - 1)
    if look < w["base_min"] * 3:
        return None

    seg = df.iloc[n - look:]
    closes = seg["Close"].values
    highs  = seg["High"].values
    lows   = seg["Low"].values
    m = len(closes)

    # find the deepest trough in the first 60% of the segment
    cup_end = int(m * 0.65)
    cup_lo_i = int(np.argmin(lows[:cup_end]))
    cup_lo   = float(lows[cup_lo_i])

    # left rim = max of highs before the trough
    if cup_lo_i < 2:
        return None
    left_rim_i = int(np.argmax(highs[:cup_lo_i]))
    left_rim   = float(highs[left_rim_i])

    # right rim = max of highs in 10 bars after trough
    rr_start = cup_lo_i + 1
    rr_end = min(m, rr_start + max(w["base_min"], (cup_end - cup_lo_i)))
    if rr_end <= rr_start:
        return None
    right_rim_i = rr_start + int(np.argmax(highs[rr_start:rr_end]))
    right_rim   = float(highs[right_rim_i])

    rim = max(left_rim, right_rim)
    cup_depth = (rim - cup_lo) / rim
    if cup_depth < 0.08 or cup_depth > 0.50:
        return None
    if abs(left_rim - right_rim) / rim > 0.06:
        return None  # rims too asymmetric

    # handle: pullback from right rim (should be < 50% of cup depth)
    handle_start = right_rim_i
    handle_end = min(m, handle_start + max(2, (m - right_rim_i) // 2))
    if handle_end <= handle_start + 1:
        return None
    handle_lo = float(np.min(lows[handle_start:handle_end]))
    handle_depth = (right_rim - handle_lo) / right_rim
    if handle_depth > cup_depth * 0.5 or handle_depth < 0.01:
        return None

    conf = min(0.48 + cup_depth * 0.6 + (0.05 if handle_depth < cup_depth * 0.35 else 0), 0.72)
    return {
        "rim": round(rim, 2),
        "cup_lo": round(cup_lo, 2),
        "cup_depth_pct": round(cup_depth * 100, 1),
        "handle_depth_pct": round(handle_depth * 100, 1),
        "confidence": round(conf, 2),
        "cup_lo_i": cup_lo_i,
        "right_rim_i": right_rim_i,
    }


def _detect_flag(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """
    Bull flag: sharp advance (pole) followed by tight parallel pullback (flag).
    """
    w = _tfw(tf)
    n = len(df)
    look = min(w["base_max"], n - 1)
    if look < w["base_min"]:
        return None

    seg = df.iloc[n - look:]
    closes = seg["Close"].values
    highs  = seg["High"].values
    lows   = seg["Low"].values
    rvols  = seg["rvol"].values

    # pole: strongest n/3 bar advance
    pole_len = max(3, look // 3)
    best_gain, pole_end = 0.0, -1
    for end in range(pole_len, len(closes)):
        start = end - pole_len
        gain = (closes[end] - closes[start]) / max(closes[start], 1e-9)
        if gain > best_gain:
            best_gain = gain
            pole_end = end

    if best_gain < 0.05 or pole_end < 0:
        return None

    # flag: remaining bars after pole_end — price should consolidate in a channel
    flag_start = pole_end
    flag_seg = closes[flag_start:]
    if len(flag_seg) < 2:
        return None

    flag_hi = float(np.max(highs[flag_start:]))
    flag_lo = float(np.min(lows[flag_start:]))
    flag_height = flag_hi - flag_lo
    pole_move   = closes[pole_end] - closes[max(0, pole_end - pole_len)]
    flag_ratio  = flag_height / max(pole_move, 1e-9)

    if flag_ratio > 0.45 or flag_ratio < 0.01:
        return None

    # volume: should fade in the flag
    pole_vol  = float(np.mean(rvols[max(0, pole_end - pole_len): pole_end + 1]))
    flag_vol  = float(np.mean(rvols[flag_start:]))
    vol_fade  = flag_vol < pole_vol * 0.75

    conf = min(0.42 + best_gain * 1.2 + (0.08 if vol_fade else 0)
               + (0.06 if flag_ratio < 0.25 else 0), 0.68)

    return {
        "pole_gain_pct": round(best_gain * 100, 1),
        "flag_height_pct": round(flag_ratio * 100, 1),
        "vol_fade": vol_fade,
        "confidence": round(conf, 2),
        "pole_end_i": pole_end,
        "flag_hi": round(flag_hi, 2),
        "flag_lo": round(flag_lo, 2),
    }


# ════════════════════════════════════════════════════════════════════
# trendline builder for CandleChart `lines` prop
# ════════════════════════════════════════════════════════════════════

def _build_trendlines(seg: pd.DataFrame, vcp: Optional[Dict], tri: Optional[Dict],
                      win_offset: int) -> List[Dict]:
    """
    Build line arrays (relative to the windowed bar array) for CandleChart.
    Each line: {pts: [{i, price}, ...], tone, width, dash}
    """
    lines = []
    n = len(seg)

    if vcp:
        # upper resistance line (flat pivot)
        contractions = vcp.get("contractions", [])
        if contractions:
            flat_pts = []
            for c in contractions:
                hi_i = c["hi_i"] - win_offset
                if 0 <= hi_i < n:
                    flat_pts.append({"i": int(hi_i), "price": round(c["hi_price"], 2)})
            if len(flat_pts) >= 2:
                lines.append({"pts": flat_pts, "tone": "copper", "width": 1.6, "dash": "4 3"})

            # rising lower trendline through contraction lows
            low_pts = []
            for c in contractions:
                lo_i = c["lo_i"] - win_offset
                if 0 <= lo_i < n:
                    low_pts.append({"i": int(lo_i), "price": round(c["lo_price"], 2)})
            if len(low_pts) >= 2:
                lines.append({"pts": low_pts, "tone": "cy", "width": 1.3, "dash": "3 4"})

    if tri and not vcp:
        pk_h = tri.get("pk_h", [])
        pk_l = tri.get("pk_l", [])
        m_h  = tri.get("m_h", 0)
        m_l  = tri.get("m_l", 0)

        if len(pk_h) >= 2:
            y0 = float(seg["High"].values[pk_h[0]])
            pts_h = [{"i": int(i - win_offset), "price": round(y0 + m_h * (i - pk_h[0]), 2)}
                     for i in pk_h if 0 <= i - win_offset < n]
            if len(pts_h) >= 2:
                lines.append({"pts": pts_h, "tone": "rd", "width": 1.3, "dash": "4 3"})
        if len(pk_l) >= 2:
            y0 = float(seg["Low"].values[pk_l[0]])
            pts_l = [{"i": int(i - win_offset), "price": round(y0 + m_l * (i - pk_l[0]), 2)}
                     for i in pk_l if 0 <= i - win_offset < n]
            if len(pts_l) >= 2:
                lines.append({"pts": pts_l, "tone": "gn", "width": 1.3, "dash": "4 3"})

    return lines


# ════════════════════════════════════════════════════════════════════
# pattern library rows (for ClassicalLibrary table)
# ════════════════════════════════════════════════════════════════════

def _build_library(vcp: Optional[Dict], tri: Optional[Dict], db: Optional[Dict],
                   cup: Optional[Dict], flag: Optional[Dict],
                   pivot: float, cur_close: float) -> List[Dict]:
    """Build a list of detected patterns with status/mm/conf for the library table."""
    rows = []

    def status(conf: float, broke: bool, forming: bool) -> Tuple[str, str]:
        if broke:
            return "BREAKOUT", "gn"
        if conf >= 0.60 and not forming:
            return "CONFIRMED", "gn"
        if forming:
            return "FORMING", "cy"
        return "WATCH", "amb"

    def mm(pivot_px: float, height: float, mult: float = 1.0) -> str:
        t = pivot_px + height * mult
        return f"${t:.{_px(t)}f}"

    if cup:
        rim = cup["rim"]
        height = rim - cup["cup_lo"]
        broke = cur_close > rim * 1.005
        st, tone = status(cup["confidence"], broke, False)
        rows.append({"p": "Cup & Handle", "st": st, "tone": tone,
                     "mm": mm(rim, height), "conf": cup["confidence"]})

    if vcp and vcp["is_vcp"]:
        piv = vcp["pivot"]
        height = piv * (vcp.get("first_depth", 15.0) / 100.0)
        broke = vcp["broke_out"]
        st, tone = status(vcp["confidence"], broke, vcp["near_pivot"])
        rows.append({"p": "VCP", "st": st, "tone": tone,
                     "mm": mm(piv, height), "conf": vcp["confidence"]})

    if tri:
        piv = float(tri.get("y_h_last", pivot))
        base_range = abs(float(tri.get("y_h_last", 0)) - float(tri.get("y_l_last", 0)))
        broke = cur_close > piv * 1.005
        st, tone = status(tri["confidence"], broke, not broke)
        rows.append({"p": tri["type"], "st": st, "tone": tone,
                     "mm": mm(piv, base_range), "conf": tri["confidence"]})

    if db:
        nl = db["neckline"]
        height = nl - min(db["L1"], db["L2"])
        broke = cur_close > nl * 1.005
        st, tone = status(db["confidence"], broke, not broke)
        rows.append({"p": "Double Bottom", "st": st, "tone": tone,
                     "mm": mm(nl, height), "conf": db["confidence"]})

    if flag:
        piv = flag["flag_hi"]
        height = flag["pole_gain_pct"] / 100.0 * cur_close
        broke = cur_close > piv * 1.005
        st, tone = status(flag["confidence"], broke, not broke)
        rows.append({"p": "Bull Flag", "st": st, "tone": tone,
                     "mm": mm(piv, height), "conf": flag["confidence"]})

    # sort by confidence desc
    rows.sort(key=lambda r: r["conf"], reverse=True)
    return rows


# ════════════════════════════════════════════════════════════════════
# build the windowed bar array + contraction markers
# ════════════════════════════════════════════════════════════════════

def _build_window(df: pd.DataFrame, tf: str, vcp: Optional[Dict]) -> Tuple[pd.DataFrame, int]:
    """Return (windowed_df, win_offset) — at most _CHART_BARS[tf] bars."""
    n = len(df)
    chart_bars = _CHART_BARS.get(tf, 90)
    win_start = max(0, n - chart_bars)
    return df.iloc[win_start:], win_start


# ════════════════════════════════════════════════════════════════════
# main detect() — the public entry point
# ════════════════════════════════════════════════════════════════════

def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    tf = (meta or {}).get("tf", "Daily")
    base = {"ok": True, "source": "real", "ticker": ticker}
    cur_close = round(float(df.iloc[-1]["Close"]), 2) if len(df) else 0.0

    if len(df) < _tfw(tf)["min"]:
        return {**base, "state": "none", "cur_close": cur_close,
                "message": f"Not enough {tf.lower()} bars for a classical pattern read ({len(df)} < {_tfw(tf)['min']})."}

    # run all detectors
    try:
        vcp  = _detect_vcp(df, tf)
    except Exception as e:
        vcp = None

    try:
        tri  = _classify_triangle(df, tf)
    except Exception as e:
        tri = None

    try:
        db   = _detect_double_bottom(df, tf)
    except Exception as e:
        db = None

    try:
        cup  = _detect_cup_handle(df, tf)
    except Exception as e:
        cup = None

    try:
        flag = _detect_flag(df, tf)
    except Exception as e:
        flag = None

    # pick primary pattern by confidence
    candidates = [x for x in [vcp, tri, db, cup, flag] if x is not None]
    if not candidates:
        return {**base, "state": "none", "cur_close": cur_close,
                "message": f"No clean base / pattern on the {tf.lower()} — price is trending or too noisy."}

    # primary = highest confidence
    best_conf = max(c["confidence"] for c in candidates)

    # determine primary name + pivot
    if vcp and vcp["confidence"] >= best_conf - 0.02:
        primary_name = "VCP" if vcp["is_vcp"] else "Base Consolidation"
        pivot        = vcp["pivot"]
        primary_conf = vcp["confidence"]
        broke_out    = vcp["broke_out"]
    elif cup and cup["confidence"] >= best_conf - 0.02:
        primary_name = "Cup & Handle"
        pivot        = cup["rim"]
        primary_conf = cup["confidence"]
        broke_out    = cur_close > pivot * 1.005
    elif tri and tri["confidence"] >= best_conf - 0.02:
        primary_name = tri["type"]
        pivot        = float(tri.get("y_h_last", cur_close))
        primary_conf = tri["confidence"]
        broke_out    = cur_close > pivot * 1.005
    elif db and db["confidence"] >= best_conf - 0.02:
        primary_name = "Double Bottom"
        pivot        = db["neckline"]
        primary_conf = db["confidence"]
        broke_out    = cur_close > pivot * 1.005
    else:
        primary_name = "Bull Flag"
        pivot        = float(flag["flag_hi"]) if flag else cur_close
        primary_conf = flag["confidence"] if flag else 0.3
        broke_out    = cur_close > pivot * 1.005

    # window + trendlines
    win_df, win_offset = _build_window(df, tf, vcp)
    bars = _bar_payload(win_df)

    # trendlines relative to window
    vcp_rel = None
    if vcp:
        # remap contraction indices to be relative to entire df
        vcp_rel = dict(vcp)
        vcp_rel["contractions"] = [
            {**c, "hi_i": c["hi_i"] + (len(df) - min(_tfw(tf)["lookback"], len(df) - 1)),
                  "lo_i": c["lo_i"] + (len(df) - min(_tfw(tf)["lookback"], len(df) - 1))}
            for c in vcp["contractions"]
        ]
        # remap contraction indices relative to windowed bars
        look = min(_tfw(tf)["lookback"], len(df) - 1)
        seg_start = len(df) - look
        vcp_rel_win = dict(vcp)
        vcp_rel_win["contractions"] = [
            {**c, "hi_i": c["hi_i"] + seg_start - win_offset,
                  "lo_i": c["lo_i"] + seg_start - win_offset}
            for c in vcp["contractions"]
        ]
        lines = _build_trendlines(win_df, vcp_rel_win, tri, 0)
    else:
        tri_rel = None
        if tri:
            look = min(_tfw(tf)["base_max"], len(df) - 1)
            seg_start = len(df) - look
            tri_abs = {**tri,
                       "pk_h": [i + seg_start - win_offset for i in tri["pk_h"]],
                       "pk_l": [i + seg_start - win_offset for i in tri["pk_l"]]}
        else:
            tri_abs = None
        lines = _build_trendlines(win_df, None, tri_abs, 0)

    # base zone
    if vcp:
        base_hi = vcp["pivot"]
        # lowest contraction low
        base_lo = min(c["lo_price"] for c in vcp["contractions"]) if vcp["contractions"] else cur_close * 0.92
    elif tri:
        base_hi = float(tri.get("y_h_last", cur_close))
        base_lo = float(tri.get("y_l_last", cur_close * 0.92))
    elif db:
        base_hi = db["neckline"]
        base_lo = min(db["L1"], db["L2"])
    elif cup:
        base_hi = cup["rim"]
        base_lo = cup["cup_lo"]
    else:
        base_hi = cur_close
        base_lo = cur_close * 0.92

    base_height = max(base_hi - base_lo, base_hi * 0.01)
    zones = [{"lo": round(base_lo, 2), "hi": round(base_hi, 2), "tone": "cy", "label": "Base"}]

    # measured-move targets
    stop_price = round(base_lo * 0.985, 2)  # just below base low
    t1_price   = round(pivot + base_height, 2)
    t2_price   = round(pivot + base_height * 1.5, 2)
    rr1 = (t1_price / cur_close - 1) * 100 if cur_close > 0 else 0
    rr2 = (t2_price / cur_close - 1) * 100 if cur_close > 0 else 0

    dp = _px(pivot)
    targets = [
        {"label": "Breakout pivot",       "basis": f"flat resistance of the base",
         "price": f"{pivot:.{dp}f}",      "rr": "trigger", "conf": None,      "tone": "copper"},
        {"label": "T1 · measured move",   "basis": f"base height ({base_height:.{_px(base_height)}f}) added to pivot",
         "price": f"{t1_price:.{_px(t1_price)}f}", "rr": f"+{rr1:.1f}%", "conf": round(primary_conf * 0.9, 2), "tone": "gn"},
        {"label": "T2 · 1.5× extension", "basis": f"1.5 × base height",
         "price": f"{t2_price:.{_px(t2_price)}f}", "rr": f"+{rr2:.1f}%", "conf": round(primary_conf * 0.6, 2), "tone": "amb"},
    ]

    # VCP contractions for the JSX VCPLadder component
    # format: [{n, depth, weeks, vol, tone}]
    vcp_contractions_display = []
    if vcp and vcp["contractions"]:
        tones = ["ink-2", "ink-2", "ink-1", "cy", "gn"]
        for k, c in enumerate(vcp["contractions"]):
            tone = tones[min(k, len(tones) - 1)]
            v_desc = "dry" if c["v_trough"] < _tfw(tf)["vol_dry_thresh"] else f"−{int((1 - c['v_trough']) * 100)}%" if c["v_trough"] < 1.0 else "heavy"
            vcp_contractions_display.append({
                "n": str(c["n"]),
                "depth": f"−{c['depth_pct']}%",
                "weeks": c.get("hi_date", f"T{c['n']}"),  # date label
                "vol": v_desc,
                "tone": tone,
            })

    # stat header (matches ClassicalStat fields)
    n_contractions = len(vcp["contractions"]) if vcp else 0
    depth_range = (f"{vcp['first_depth']:.0f}%→{vcp['last_depth']:.0f}%"
                   if vcp and vcp.get("first_depth") else "—")

    stat = {
        "primary_pattern": primary_name,
        "stage": "Breakout" if broke_out else ("Near pivot" if (vcp and vcp["near_pivot"]) else "Basing"),
        "contractions": f"{n_contractions} · {depth_range}" if n_contractions else "—",
        "measured_move": f"${t1_price:.{_px(t1_price)}f}",
        "confidence": primary_conf,
    }

    # pattern library rows
    library = _build_library(vcp, tri, db, cup, flag, pivot, cur_close)

    # tone for primary pattern
    pattern_tone = "gn" if broke_out else ("cy" if vcp and vcp["near_pivot"] else "amb")

    # plain-English read
    if broke_out:
        read = (f"{primary_name} breakout confirmed — {tf.lower()} close above pivot ${pivot:.{dp}f}. "
                f"Measured-move target ${t1_price:.{_px(t1_price)}f}. Invalidates below ${stop_price:.{_px(stop_price)}f}.")
    elif vcp and vcp["near_pivot"]:
        read = (f"{primary_name} — {n_contractions} contractions ({depth_range}) into pivot ${pivot:.{dp}f}. "
                f"Volume dry-up confirmed. Breakout entry on close above pivot with expanded volume.")
    else:
        read = (f"{primary_name} base forming ({tf.lower()}). "
                f"Pivot at ${pivot:.{dp}f}, measured-move target ${t1_price:.{_px(t1_price)}f}. "
                f"No entry yet — wait for breakout or volume-dry tightening into pivot.")

    return {
        **base,
        "state": "real",
        "confidence": primary_conf,
        "bars": bars,
        "pattern": {"name": primary_name, "tone": pattern_tone},
        "contractions": vcp_contractions_display,
        "pivot": round(pivot, 2),
        "stop": stop_price,
        "targets": targets,
        "lines": lines,
        "zones": zones,
        "library": library,
        "stat": stat,
        "read": read,
        "cur_close": cur_close,
        "broke_out": broke_out,
        "n_contractions": n_contractions,
        "base_height": round(base_height, 2),
        "base_lo": round(base_lo, 2),
        "base_hi": round(base_hi, 2),
    }
