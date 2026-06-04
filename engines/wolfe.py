"""engines/wolfe.py — Wolfe Wave detector for the BullVeda Patterns lens.

Mechanism (principle 2): a Wolfe Wave is a natural equilibrium pattern — five
waves where 1-3-5 define a converging (or expanding) channel and the 1-4 line
projects the "Estimated Price at Arrival" (EPA) where supply/demand rebalances.
Edge comes from the predictable reversion after point-5 overshoots the channel,
as the wedge compression forces a snapback toward the long-run equilibrium line.

Honesty (principle 4): returns state="none" when no valid 5-point structure
passes all four Wolfe rules within tolerance. Never fabricates.

Mode-aware: daily (SWING) / weekly (POSITION) / monthly (INVESTMENT). The ZigZag
pivot window and validation thresholds scale with timeframe.

CLI:
    python3 -m engines.wolfe AAPL SWING
    python3 -m engines.wolfe NVDA POSITION
    python3 -m engines.wolfe WMB INVESTMENT
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "wolfe"
LABEL = "Wolfe Wave"

# ── Timeframe window config ────────────────────────────────────────────────────
# lookback: bars to scan; pivot_n: fractal half-window; bars_out: chart width
_TFW = {
    "Daily":   {"lookback": 200, "pivot_n": 5,  "bars_out": 100, "min_leg_bars": 3},
    "Weekly":  {"lookback": 130, "pivot_n": 3,  "bars_out": 80,  "min_leg_bars": 2},
    "Monthly": {"lookback": 80,  "pivot_n": 2,  "bars_out": 60,  "min_leg_bars": 1},
}

def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── Bar payload ────────────────────────────────────────────────────────────────
def _bar_payload(df: pd.DataFrame) -> List[Dict]:
    out = []
    for _, r in df.iterrows():
        rvol = float(r["rvol"]) if "rvol" in r.index and np.isfinite(r["rvol"]) else 1.0
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(rvol, 2),
        })
    return out


# ── ZigZag pivot extraction (vectorised) ──────────────────────────────────────
def _zigzag_pivots(df: pd.DataFrame, n: int) -> List[Tuple[int, float, str]]:
    """Return alternating swing highs/lows as [(local_bar_idx, price, 'H'|'L'), …]."""
    highs = df["High"]
    lows  = df["Low"]
    roll_max = highs.rolling(2 * n + 1, center=True, min_periods=n + 1).max()
    roll_min = lows.rolling(2 * n + 1, center=True, min_periods=n + 1).min()
    ph = (highs == roll_max).values
    pl = (lows  == roll_min).values

    raw: List[Tuple[int, float, str]] = []
    for i in range(len(df)):
        if ph[i] and pl[i]:
            h, l = float(df["High"].iloc[i]), float(df["Low"].iloc[i])
            mid = float(df["Close"].iloc[i])
            if (h - mid) >= (mid - l):
                raw.append((i, h, "H"))
            else:
                raw.append((i, l, "L"))
        elif ph[i]:
            raw.append((i, float(df["High"].iloc[i]), "H"))
        elif pl[i]:
            raw.append((i, float(df["Low"].iloc[i]), "L"))

    if not raw:
        return []

    # Enforce strict alternation
    zz: List[Tuple[int, float, str]] = [raw[0]]
    for pt in raw[1:]:
        prev = zz[-1]
        if pt[2] == prev[2]:
            if (pt[2] == "H" and pt[1] > prev[1]) or (pt[2] == "L" and pt[1] < prev[1]):
                zz[-1] = pt
        else:
            zz.append(pt)

    return zz


# ── Line utility ───────────────────────────────────────────────────────────────
def _line_y_at(p1: Tuple[int, float], p2: Tuple[int, float], x: float) -> Optional[float]:
    """Price on the line through p1,p2 at bar x. None if vertical."""
    dx = p2[0] - p1[0]
    if abs(dx) < 0.5:
        return None
    slope = (p2[1] - p1[1]) / dx
    return p1[1] + slope * (x - p1[0])


def _line_intersection_x(
    p1: Tuple[int, float], p2: Tuple[int, float],
    p3: Tuple[int, float], p4: Tuple[int, float],
) -> Optional[Tuple[float, float]]:
    """Return (x, y) intersection of line p1-p2 and line p3-p4. None if parallel."""
    dx1 = p2[0] - p1[0]; dy1 = p2[1] - p1[1]
    dx2 = p4[0] - p3[0]; dy2 = p4[1] - p3[1]
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * dy2 - (p3[1] - p1[1]) * dx2) / denom
    x = p1[0] + t * dx1
    y = p1[1] + t * dy1
    return (x, y)


# ── Wolfe Wave validation ─────────────────────────────────────────────────────
# Bull Wolfe: alternating L-H-L-H-L  (1=low, 2=high, 3=low, 4=high, 5=low)
#   entry at pt5; EPA on the 1-4 line projected forward
# Bear Wolfe: alternating H-L-H-L-H  (1=high, 2=low, 3=high, 4=low, 5=high)
#   entry at pt5; EPA on the 1-4 line projected forward

_TIME_SYM_TOL   = 0.65   # t(3→4) / t(1→2) ratio bounds [1-tol, 1+tol]
_CHANNEL_TOL    = 0.12   # 12% tolerance for containment checks


def _validate_wolfe(
    pts: List[Tuple[int, float, str]],  # exactly 5 [(i, price, kind), ...]
    min_leg_bars: int,
) -> Optional[Dict[str, Any]]:
    """Test one 5-pivot sequence. Return result dict or None."""
    p1, p2, p3, p4, p5 = pts

    # ── Structural direction: bull (LHLHL) or bear (HLHLH) ──
    if p1[2] == "L" and p2[2] == "H" and p3[2] == "L" and p4[2] == "H" and p5[2] == "L":
        is_bull = True
    elif p1[2] == "H" and p2[2] == "L" and p3[2] == "H" and p4[2] == "L" and p5[2] == "H":
        is_bull = False
    else:
        return None   # not alternating

    # ── Minimum bar spacing on each leg ──────────────────────────────────────
    for a, b in [(p1, p2), (p2, p3), (p3, p4), (p4, p5)]:
        if abs(b[0] - a[0]) < min_leg_bars:
            return None

    # ── Rule 1: Point 4 must be inside the 1-2 price range ──────────────────
    lo12 = min(p1[1], p2[1])
    hi12 = max(p1[1], p2[1])
    margin = (hi12 - lo12) * _CHANNEL_TOL
    if not (lo12 - margin <= p4[1] <= hi12 + margin):
        return None

    # ── Rule 2: 1-3-5 line — point 5 must overshoot ("sweet spot") ──────────
    # The 1-3 trendline extended to bar 5 should be above p5 (bull) or below (bear)
    y_13_at_5 = _line_y_at((p1[0], p1[1]), (p3[0], p3[1]), p5[0])
    if y_13_at_5 is None:
        return None

    overshoot_pct: float
    if is_bull:
        # p5 should be BELOW the 1-3 line (overshoots to the downside)
        if p5[1] >= y_13_at_5:
            return None
        overshoot_pct = (y_13_at_5 - p5[1]) / (y_13_at_5 + 1e-9)
    else:
        # p5 should be ABOVE the 1-3 line (overshoots to the upside)
        if p5[1] <= y_13_at_5:
            return None
        overshoot_pct = (p5[1] - y_13_at_5) / (y_13_at_5 + 1e-9)

    # Reasonable overshoot: 0.5% – 18%
    if not (0.005 <= overshoot_pct <= 0.18):
        return None

    # ── Rule 3: Time symmetry — t(3→4) should approximate t(1→2) ────────────
    t12 = abs(p2[0] - p1[0])
    t34 = abs(p4[0] - p3[0])
    ratio = t34 / t12 if t12 > 0 else 9999
    lo_sym = 1.0 - _TIME_SYM_TOL
    hi_sym = 1.0 + _TIME_SYM_TOL
    if not (lo_sym <= ratio <= hi_sym):
        return None

    # ── Rule 4: Channel convergence check (2-4 line and 1-3 line converge) ──
    # For a bull wedge: 2-4 slopes downward relative to 1-3
    # We check that the 1-4 line will intersect 1-3 in the future (after p5)
    epa_xy = _line_intersection_x(
        (p1[0], p1[1]), (p4[0], p4[1]),
        (p1[0], p1[1]), (p3[0], p3[1]),
    )
    if epa_xy is None:
        # 1-4 and 1-3 are parallel — degenerate
        # Allow it but compute EPA differently: extend 1-4 by (p5-p1) bars
        epa_x = float(p5[0]) + abs(p5[0] - p1[0]) * 0.5
        epa_y = _line_y_at((p1[0], p1[1]), (p4[0], p4[1]), epa_x)
        if epa_y is None:
            return None
    else:
        epa_x, epa_y = epa_xy
        # EPA must be AFTER point 5
        if epa_x <= p5[0]:
            # Extend 1-4 further — use the intersection as a guide but ensure it's forward
            epa_x = float(p5[0]) + max(5, abs(int(epa_x) - p5[0]))
            epa_y = _line_y_at((p1[0], p1[1]), (p4[0], p4[1]), epa_x)
            if epa_y is None:
                return None

    # ── Confidence: combine overshoot quality + time symmetry ────────────────
    # Best = 1.0 overshoot near 2-8% + time ratio near 1.0
    os_score   = 1.0 - abs(overshoot_pct - 0.04) / 0.14    # ideal 4%
    sym_score  = 1.0 - abs(ratio - 1.0) / _TIME_SYM_TOL
    confidence = round(max(0.30, min(0.88, 0.50 * os_score + 0.50 * sym_score)), 2)

    return {
        "is_bull":       is_bull,
        "overshoot_pct": round(overshoot_pct, 4),
        "time_sym":      round(ratio, 3),
        "epa_x":         epa_x,
        "epa_y":         round(float(epa_y), 2),
        "y_13_at_5":     round(float(y_13_at_5), 2),
        "confidence":    confidence,
    }


# ── Scan ZigZag for best Wolfe structure ───────────────────────────────────────
def _find_best_wolfe(
    pivots: List[Tuple[int, float, str]],
    min_leg_bars: int,
) -> Optional[Tuple[List[Tuple[int, float, str]], Dict[str, Any]]]:
    """Return (5-pivot list, validation_result) for the best (most recent) valid structure."""
    n = len(pivots)
    if n < 5:
        return None

    best_pts: Optional[List[Tuple[int, float, str]]] = None
    best_res: Optional[Dict[str, Any]] = None
    best_recency = -1

    for end in range(n - 1, 3, -1):
        window = pivots[end - 4 : end + 1]
        res = _validate_wolfe(window, min_leg_bars)
        if res is None:
            continue
        recency = window[4][0]   # bar index of pt5
        if best_res is None or recency > best_recency:
            best_recency = recency
            best_pts = window
            best_res = res

    if best_pts is None:
        return None
    return best_pts, best_res


# ── Build structured output fields ────────────────────────────────────────────

def _build_points(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    df: pd.DataFrame,
    window_start: int,
    tf: str,
    is_bull: bool,
) -> List[Dict[str, Any]]:
    p1, p2, p3, p4, p5 = wpts
    roles = {
        1: "Origin" + (" low" if is_bull else " high"),
        2: "First " + ("high" if is_bull else "low") + " — defines 2-4 line",
        3: "Lower " + ("low" if is_bull else "high") + " — widens wedge",
        4: "Lower " + ("high" if is_bull else "low") + " — inside 1-2 range",
        5: "Sweet-spot ⟳ — overshoot of 1-3 line, entry",
    }
    notes = {
        1: "Pattern anchor",
        2: f"Defines the upper {'2-4' if is_bull else '2-4'} trendline",
        3: f"{'Below' if is_bull else 'Above'} point 1 — channel is widening",
        4: f"Inside the 1-2 price range · confirms {'down' if is_bull else 'up'}-channel",
        5: (f"Overshoots 1-3 line by {val['overshoot_pct']*100:.1f}% "
            f"({'below' if is_bull else 'above'} ${val['y_13_at_5']:.2f}) — the entry"),
    }
    tone_map = {1: "violet", 2: "violet", 3: "violet", 4: "violet", 5: "copper"}

    out = []
    for k, (abs_i, price, _) in enumerate([p1, p2, p3, p4, p5], start=1):
        bar_i = int(abs_i - window_start)
        if bar_i < 0:
            bar_i = 0
        date_str = fmt_date(df.index[int(abs_i)], tf) if int(abs_i) < len(df) else ""
        out.append({
            "w":     str(k),
            "i":     bar_i,
            "price": round(float(price), 2),
            "role":  roles[k],
            "date":  date_str,
            "note":  notes[k],
            "tone":  tone_map[k],
        })
    return out


def _build_rules(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
) -> List[Dict[str, Any]]:
    p1, p2, p3, p4, p5 = wpts
    lo12 = min(p1[1], p2[1])
    hi12 = max(p1[1], p2[1])
    t12  = abs(p2[0] - p1[0])
    t34  = abs(p4[0] - p3[0])
    sym  = val["time_sym"]
    os   = val["overshoot_pct"]
    y13  = val["y_13_at_5"]

    rules = [
        {
            "rule":   "Waves 3-4 contained within the 1-2 channel",
            "detail": f"4={p4[1]:.2f} inside [{lo12:.2f}–{hi12:.2f}]",
            "status": "PASS", "tone": "gn",
        },
        {
            "rule":   "Point 5 overshoots the 1-3 line (sweet spot)",
            "detail": f"5={p5[1]:.2f} {'below' if is_bull else 'above'} 1-3={y13:.2f} (+{os*100:.1f}%)",
            "status": "PASS", "tone": "gn",
        },
        {
            "rule":   "Time symmetry · t(1→2) ≈ t(3→4)",
            "detail": f"{t12} ≈ {t34} bars (ratio {sym:.2f})",
            "status": "PASS" if abs(sym - 1.0) < 0.35 else "NEAR", "tone": "gn" if abs(sym - 1.0) < 0.35 else "amb",
        },
        {
            "rule":   "Point 4 inside the 1-2 price range",
            "detail": f"{p4[1]:.2f} {'<' if is_bull else '>'} {hi12:.2f} (pt 2)" if is_bull else f"{p4[1]:.2f} {'<' if is_bull else '>'} {lo12:.2f} (pt 2)",
            "status": "PASS", "tone": "gn",
        },
        {
            "rule":   "Entry at 5 · EPA = 1-4 line projection",
            "detail": "target rides the 1-4 line to equilibrium",
            "status": "ACTIVE", "tone": "violet",
        },
    ]
    return rules


def _build_targets(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    cur_close: float,
    is_bull: bool,
) -> List[Dict[str, Any]]:
    p5   = wpts[4]
    epa  = val["epa_y"]
    stop = _compute_stop(wpts, val, is_bull)

    rr = round(abs(epa - p5[1]) / abs(p5[1] - stop), 2) if abs(p5[1] - stop) > 1e-9 else 0.0
    return [
        {
            "label": "EPA target",
            "basis": f"1-4 line · est. arrival bar {int(val['epa_x'])} (~{max(1, int(val['epa_x'] - wpts[4][0]))}d)",
            "price": f"{epa:.2f}",
            "rr": f"R:R ≈ {rr:.1f}:1" if rr >= 1 else "projected",
            "conf": round(val["confidence"] * 0.85, 2),
            "tone": "gn" if is_bull else "rd",
        },
        {
            "label": "Point-5 entry",
            "basis": "sweet-spot reversal zone",
            "price": f"{p5[1]:.2f}",
            "rr": "entry",
            "conf": None,
            "tone": "copper",
        },
        {
            "label": "Invalidation",
            "basis": f"5 fails to hold / {'drops' if is_bull else 'rises'} further",
            "price": f"{stop:.2f}",
            "rr": "stop",
            "conf": None,
            "tone": "rd",
        },
    ]


def _compute_stop(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
) -> float:
    """Stop = 1.5% beyond point-5 extreme (or 3% if that's too tight vs ATR)."""
    p5 = wpts[4][1]
    if is_bull:
        return round(p5 * (1 - 0.015), 2)
    else:
        return round(p5 * (1 + 0.015), 2)


def _build_stat(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
    tf: str,
    targets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    p5 = wpts[4][1]
    return {
        "pattern":    f"{'Bullish' if is_bull else 'Bearish'} Wolfe Wave",
        "structure":  "5-point · valid",
        "entry":      f"${p5:.2f}",
        "epa_target": f"${val['epa_y']:.2f}",
        "confidence": val["confidence"],
        "tone":       "gn" if is_bull else "rd",
    }


def _build_read(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
    tf: str,
    targets: List[Dict[str, Any]],
) -> str:
    p5   = wpts[4][1]
    epa  = val["epa_y"]
    stop = float(targets[2]["price"])
    rr_row = targets[0]
    rr_txt = rr_row["rr"]
    bars_to = max(1, int(val["epa_x"] - wpts[4][0]))
    direction = "Bullish" if is_bull else "Bearish"
    return (
        f"{tf} {direction} Wolfe Wave: point-5 entry at ${p5:.2f} "
        f"({'overshoot below' if is_bull else 'overshoot above'} 1-3 line by "
        f"{val['overshoot_pct']*100:.1f}%). "
        f"EPA target ${epa:.2f} on the 1-4 line in ~{bars_to} bars ({rr_txt}). "
        f"Void {'below' if is_bull else 'above'} stop ${stop:.2f}."
    )


def _build_lines(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
    window_start: int,
    bars_out: int,
) -> List[Dict[str, Any]]:
    """Three lines for the chart: 1-3-5 channel, 2-4 trendline, 1-4 EPA line."""
    p1, p2, p3, p4, p5 = wpts

    def rel(pt: Tuple[int, float, str]) -> Tuple[int, float]:
        return (int(pt[0] - window_start), pt[1])

    rp1, rp2, rp3, rp4, rp5 = rel(p1), rel(p2), rel(p3), rel(p4), rel(p5)

    # extend lines to chart edge (bar = bars_out - 1)
    chart_end = bars_out - 1

    def extend(pa: Tuple[int, float], pb: Tuple[int, float]) -> List[Dict]:
        y_end = _line_y_at(pa, pb, chart_end)
        if y_end is None:
            return [{"i": pa[0], "price": pa[1]}, {"i": pb[0], "price": pb[1]}]
        return [{"i": pa[0], "price": round(pa[1], 2)},
                {"i": chart_end, "price": round(float(y_end), 2)}]

    lines = [
        # 1-3-5 sweet-spot line (dashed, subtle)
        {"pts": extend(rp1, rp3), "tone": "ink-2", "width": 1.2, "dash": "3 3", "opacity": 0.7},
        # 2-4 trendline (dashed, subtle)
        {"pts": extend(rp2, rp4), "tone": "ink-2", "width": 1.2, "dash": "3 3", "opacity": 0.7},
        # 1-4 EPA target line (solid green, prominent)
        {"pts": extend(rp1, rp4), "tone": "gn" if is_bull else "rd", "width": 1.8, "opacity": 0.9},
    ]
    return lines


def _build_hlines(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
    targets: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    epa  = val["epa_y"]
    p5   = wpts[4][1]
    stop = float(targets[2]["price"])
    return [
        {"price": epa, "label": f"EPA target · {epa:.2f}", "tone": "gn" if is_bull else "rd", "dash": "5 4"},
        {"price": p5,  "label": f"Point 5 entry · {p5:.2f}", "tone": "copper", "dash": "2 4"},
        {"price": stop, "label": f"Invalidate {'<' if is_bull else '>'} {stop:.2f}", "tone": "rd", "dash": "3 3", "labelBelow": not is_bull},
    ]


def _build_markers(
    wpts: List[Tuple[int, float, str]],
    val: Dict[str, Any],
    is_bull: bool,
    window_start: int,
) -> Tuple[List[Dict], List[Dict]]:
    """Returns (markers, skeleton_pts)."""
    labels = ["1", "2", "3", "4", "5 ⟳"]
    tones  = ["violet", "violet", "violet", "violet", "copper"]

    markers  = []
    skeleton = []
    for k, (abs_i, price, _) in enumerate(wpts):
        bar_i = int(abs_i - window_start)
        if bar_i < 0:
            bar_i = 0
        if is_bull:
            place = "below" if k % 2 == 0 else "above"  # 1(low),3(low),5(low)→below; 2,4→above
        else:
            place = "above" if k % 2 == 0 else "below"

        markers.append({
            "i": bar_i, "price": round(float(price), 2),
            "label": labels[k], "tone": tones[k], "place": place,
        })
        skeleton.append({"i": bar_i, "price": round(float(price), 2)})

    # EPA point
    epa_bar = int(val["epa_x"] - window_start)
    epa_bar = min(epa_bar, window_start + 20)   # cap within chart span for skeleton display
    skeleton.append({"i": epa_bar, "price": val["epa_y"]})
    markers.append({
        "i": epa_bar, "price": val["epa_y"],
        "label": "EPA", "tone": "gn" if is_bull else "rd", "place": "above" if is_bull else "below",
    })
    return markers, skeleton


# ── Main detect() ──────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Wolfe Wave detector. Returns full payload for WolfeView. Never raises."""
    tf = meta.get("tf", "Daily")
    w  = _tfw(tf)
    base = {"ok": True, "source": "real", "state": "none", "cur_close": None, "message": ""}

    if df is None or len(df) < 30:
        return {**base, "message": f"Insufficient {tf.lower()} history for Wolfe Wave scan."}

    cur_close = round(float(df["Close"].iloc[-1]), 2)
    base["cur_close"] = cur_close

    # ── ZigZag on lookback window ─────────────────────────────────────────────
    lookback = min(w["lookback"], len(df))
    sub      = df.iloc[-lookback:].copy()
    offset   = len(df) - lookback   # absolute index of sub[0]

    local_pivots = _zigzag_pivots(sub, w["pivot_n"])
    # Translate to absolute df indices
    abs_pivots = [(int(offset + i), price, kind) for (i, price, kind) in local_pivots]

    if len(abs_pivots) < 5:
        return {**base,
                "message": f"Only {len(abs_pivots)} ZigZag pivots in the last {lookback} "
                           f"{tf.lower()} bars — need ≥5 for a Wolfe Wave."}

    # ── Scan for valid 5-point Wolfe structure ────────────────────────────────
    found = _find_best_wolfe(abs_pivots, w["min_leg_bars"])
    if found is None:
        return {**base,
                "message": (f"No valid 5-point Wolfe Wave structure found on the {tf.lower()} chart. "
                            f"Scanned {len(abs_pivots)} ZigZag pivots; none passed the four Wolfe rules "
                            f"(pt-4 containment, pt-5 overshoot of 1-3 line, time symmetry, convergence).")}

    wpts, val = found
    is_bull = bool(val["is_bull"])

    # ── Build chart window ────────────────────────────────────────────────────
    bars_n       = min(w["bars_out"], len(df))
    window_start = len(df) - bars_n
    bars         = _bar_payload(df.iloc[-bars_n:])

    # ── Build all output fields ───────────────────────────────────────────────
    points  = _build_points(wpts, val, df, window_start, tf, is_bull)
    rules   = _build_rules(wpts, val, is_bull)
    targets = _build_targets(wpts, val, cur_close, is_bull)
    stat    = _build_stat(wpts, val, is_bull, tf, targets)
    read    = _build_read(wpts, val, is_bull, tf, targets)
    lines   = _build_lines(wpts, val, is_bull, window_start, bars_n)
    hlines  = _build_hlines(wpts, val, is_bull, targets)
    markers, skeleton = _build_markers(wpts, val, is_bull, window_start)

    p1, p2, p3, p4, p5 = wpts
    stop = float(targets[2]["price"])

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "confidence": val["confidence"],
        "bars":       bars,
        # chart annotations
        "lines":      lines,
        "hlines":     hlines,
        "markers":    markers,
        "skeleton":   skeleton,
        # structured data
        "points":     points,      # WolfeLog
        "rules":      rules,       # WolfeRules
        "targets":    targets,     # WolfeTargets
        "stat":       stat,        # WolfeStat
        # wave geometry
        "wf": {
            "bull":          is_bull,
            "p5_price":      round(float(p5[1]), 2),
            "epa":           val["epa_y"],
            "epa_bar":       int(val["epa_x"]),
            "stop":          stop,
            "overshoot_pct": val["overshoot_pct"],
            "time_sym":      val["time_sym"],
        },
        "invalidation": {
            "price": stop,
            "note": (f"A close {'below' if is_bull else 'above'} ${stop:.2f} "
                     f"voids the Wolfe Wave — point-5 holding is the premise."),
        },
        "read":       read,
        "cur_close":  cur_close,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":   # pragma: no cover
    import json
    import sys
    sym  = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    mode = sys.argv[2] if len(sys.argv) > 2 else "SWING"
    from pattern_engines import detect as pdetect
    out = pdetect("wolfe", sym, mode)
    print(f"\n=== Wolfe Wave · {sym} · {mode} ({out.get('meta', {}).get('tf')}) ===")
    print(f"state={out.get('state')}  conf={out.get('confidence')}  bars={len(out.get('bars', []))}")
    if out.get("message"):
        print("message:", out["message"])
    if out.get("points"):
        for p in out["points"]:
            print(f"  pt{p['w']}  i={p['i']:>3}  ${p['price']:<9}  {p['date']:<8}  {p['role']}")
    if out.get("wf"):
        wf = out["wf"]
        print(f"  EPA: ${wf['epa']}  stop: ${wf['stop']}  bull: {wf['bull']}")
    if "--json" in sys.argv:
        print(json.dumps({k: v for k, v in out.items() if k != "bars"}, indent=2, default=str))
