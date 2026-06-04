"""engines/gann.py — Gann fan + Square-of-Nine detector for the BullVeda Patterns lens.

Mechanism (principle 2): Gann angles encode a fixed price-per-time rate from a
significant pivot. The 1×1 line is the "balance" between price and time — price
holding above it signals sustained upward momentum; crossing below signals supply
dominance. Square-of-Nine levels are harmonic price targets derived from rotating
around a price spiral; cardinal (90°/180°/270°/360°) and ordinal (45°/135°/225°/315°)
angles cluster at mathematically significant support/resistance. This is an overlay
method — never trade it alone, use as a confluence filter.

Honesty (principle 4): confidence is capped at 0.60. No fabrication when bars
are insufficient. Time-cycle projections are clearly labelled as "calendar estimate".
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME  = "gann"
LABEL = "Gann"

# ── timeframe windows ─────────────────────────────────────────────────────────
_TFW = {
    "Daily":   {"pivot_lookback": 80,  "chart_bars": 90,  "fan_extend": 40,  "cycle_bars": [30, 60, 90]},
    "Weekly":  {"pivot_lookback": 60,  "chart_bars": 70,  "fan_extend": 30,  "cycle_bars": [13, 26, 52]},
    "Monthly": {"pivot_lookback": 40,  "chart_bars": 50,  "fan_extend": 18,  "cycle_bars": [6,  12, 24]},
}

def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── Square-of-Nine helpers ────────────────────────────────────────────────────
def _sq9_root(price: float) -> float:
    """Convert a price to its Square-of-Nine spiral position (root value)."""
    return math.sqrt(max(price, 0.01))


def _sq9_level(root: float, steps: int) -> float:
    """Move `steps` quarter-turns around the Sq-9 spiral from the given root."""
    # Each quarter-turn = 0.25 of a full revolution = addition of 0.5 to the root
    new_root = root + steps * 0.5
    return round(new_root * new_root, 2)


def _sq9_levels_around(price: float) -> List[Dict[str, Any]]:
    """Cardinal (90° multiples) and ordinal (45° multiples) Sq-9 levels around price."""
    root = _sq9_root(price)
    # Fractional position on the spiral: 0.0 at a perfect square, up to 1.0
    frac = root - math.floor(root)  # position within current revolution

    levels = []
    # Search ±4 quarter-turns (=±1 full revolution)
    for q in range(-4, 5):
        lvl = _sq9_level(math.floor(root), q) if frac < 0.25 else _sq9_level(root - frac, q + round(frac / 0.25))
        # simpler, consistent: steps from nearest integer root
        base_root = round(root)
        lvl = _sq9_level(base_root, q)
        if lvl <= 0:
            continue
        # rotation in degrees
        deg = (q % 8) * 45  # 8 quarter-turns = 360°
        # map to 0..360
        deg_norm = ((deg % 360) + 360) % 360
        role_map = {
            0:   ("cardinal", "360°/0° · full square"),
            45:  ("ordinal",  "45° · first octave"),
            90:  ("cardinal", "90° · quarter turn"),
            135: ("ordinal",  "135° · third octave"),
            180: ("cardinal", "180° · price-time square"),
            225: ("ordinal",  "225° · fifth octave"),
            270: ("cardinal", "270° · three-quarter turn"),
            315: ("ordinal",  "315° · seventh octave"),
        }
        kind, label = role_map.get(deg_norm, ("ordinal", f"{deg_norm}°"))
        tone = "violet" if kind == "cardinal" else "cy"
        # relative position to current price
        diff_pct = (lvl - price) / price * 100
        levels.append({
            "price": lvl,
            "rot": f"{deg_norm}°",
            "rot_deg": deg_norm,
            "kind": kind,
            "role": label,
            "tone": tone,
            "diff_pct": round(diff_pct, 1),
        })

    # sort by proximity to price, remove duplicates, return nearest 6
    seen = set()
    out = []
    for lv in sorted(levels, key=lambda x: abs(x["price"] - price)):
        key = lv["price"]
        if key not in seen:
            seen.add(key)
            out.append(lv)
    return out[:6]


# ── pivot detection ───────────────────────────────────────────────────────────
def _find_pivot(df: pd.DataFrame, tf: str) -> Optional[Dict[str, Any]]:
    """Find the most significant recent swing low (accumulation) or high (distribution)."""
    w = _tfw(tf)
    n = len(df)
    lb = min(w["pivot_lookback"], n - 5)
    # Work with positional (integer) indices to avoid Timestamp/int confusion
    start_pos = n - lb
    region = df.iloc[start_pos:]

    # Find swing low: argmin returns integer position within region
    low_rel_pos  = int(region["Low"].values.argmin())
    high_rel_pos = int(region["High"].values.argmax())

    low_abs_pos  = start_pos + low_rel_pos
    high_abs_pos = start_pos + high_rel_pos

    low_price  = float(region["Low"].iloc[low_rel_pos])
    low_close  = float(region["Close"].iloc[low_rel_pos])
    low_atr    = float(region["atr"].iloc[low_rel_pos])
    low_ts     = df.index[low_abs_pos]

    high_price = float(region["High"].iloc[high_rel_pos])
    high_close = float(region["Close"].iloc[high_rel_pos])
    high_ts    = df.index[high_abs_pos]

    cur_close = float(df["Close"].iloc[-1])

    # Bar offset from the end (how many bars ago was the pivot)
    low_bar_offset  = n - 1 - low_abs_pos
    high_bar_offset = n - 1 - high_abs_pos

    # Prefer the low as anchor (bullish bias — more useful for trade planning)
    # unless price is within 5% of the high (might be distributing)
    dist_from_high = abs(cur_close - high_price) / high_price
    if dist_from_high < 0.05 and high_bar_offset > low_bar_offset:
        # Use high as pivot — distribution read
        pivot_type = "high"
        pivot_price = round(high_price, 2)
        pivot_close = round(high_close, 2)
        pivot_bar_offset = high_bar_offset
        pivot_date = fmt_date(high_ts, tf)
        direction = "down"
    else:
        pivot_type = "low"
        pivot_price = round(low_price, 2)
        pivot_close = round(low_close, 2)
        pivot_bar_offset = low_bar_offset
        pivot_date = fmt_date(low_ts, tf)
        direction = "up"

    return {
        "type": pivot_type,
        "price": pivot_price,
        "close": pivot_close,
        "date": pivot_date,
        "bar_offset": pivot_bar_offset,
        "bar_idx": (n - 1) - pivot_bar_offset,  # index in windowed bars
        "direction": direction,
        "atr": round(low_atr, 4),
    }


# ── Gann fan angle computation ────────────────────────────────────────────────
# Angle ratios: 8×1, 4×1, 3×1, 2×1, 1×1, 1×2, 1×3, 1×4, 1×8
_FAN_ANGLES = [
    (8,  1, "8×1",  "82.5°", "gn",    "2 3", 0.6, "extremely steep — parabolic bull"),
    (4,  1, "4×1",  "75°",   "gn",    "3 4", 0.7, "strong bull trend"),
    (2,  1, "2×1",  "63.75°","gn",    "4 4", 0.9, "upper bull channel"),
    (1,  1, "1×1",  "45°",   "copper", None, 1.8, "master line — price/time balance"),
    (1,  2, "1×2",  "26.25°","cy",    "4 4", 0.9, "support — gentle uptrend"),
    (1,  4, "1×4",  "15°",   "ink-2", "3 4", 0.7, "last-ditch support"),
    (1,  8, "1×8",  "7.5°",  "ink-3", "2 4", 0.5, "near-flat — trend exhaustion"),
]


def _compute_unit(df: pd.DataFrame, pivot: dict, tf: str) -> float:
    """
    Derive the Gann price-per-bar 'unit' from the ATR at the pivot.
    The 1×1 should roughly track the dominant trend slope.
    """
    atr = pivot["atr"]
    if atr <= 0:
        atr = float(df["atr"].mean())
    # Scale unit so 1×1 moves ~1 ATR per bar — a natural regime measure
    return round(atr, 4)


def _fan_lines(pivot: dict, unit: float, chart_n: int, extend_bars: int) -> List[Dict[str, Any]]:
    """Build `lines` entries (price-per-bar polylines) for CandleChart."""
    pi = pivot["bar_idx"]      # pivot position in windowed bars
    pp = pivot["price"]
    direction = pivot["direction"]
    sign = 1 if direction == "up" else -1

    end_i = chart_n - 1 + extend_bars   # project beyond last real bar

    lines = []
    for (mul_p, mul_t, label, deg, tone, dash, width, role) in _FAN_ANGLES:
        slope = sign * (mul_p / mul_t) * unit
        # Two points suffice for a line — pivot start + projected end
        pts = [
            {"i": pi,    "price": round(pp, 2)},
            {"i": end_i, "price": round(pp + slope * (end_i - pi), 2)},
        ]
        lines.append({
            "label": label, "deg": deg, "tone": tone, "dash": dash,
            "width": width, "opacity": 1.0 if label == "1×1" else 0.65,
            "pts": pts, "role": role, "slope": round(slope, 4),
            "mul_p": mul_p, "mul_t": mul_t,
        })
    return lines


def _current_angle(cur_close: float, pivot: dict, lines: List[Dict[str, Any]], chart_n: int) -> Dict[str, Any]:
    """Identify which Gann angle price currently sits on / between."""
    pi = pivot["bar_idx"]
    now_i = chart_n - 1
    bars_elapsed = now_i - pi

    # Compute angle price at current bar for each fan line
    angle_vals = []
    for ln in lines:
        slope = ln["slope"]
        val = pivot["price"] + slope * bars_elapsed
        angle_vals.append({"label": ln["label"], "val": round(val, 2),
                           "tone": ln["tone"], "deg": ln["deg"], "role": ln["role"]})

    # Find which two angles the price sits between
    direction = pivot["direction"]
    if direction == "up":
        above = [a for a in angle_vals if a["val"] <= cur_close]
        below = [a for a in angle_vals if a["val"] > cur_close]
        riding = max(above, key=lambda x: x["val"]) if above else None
        next_r = min(below, key=lambda x: x["val"]) if below else None
    else:
        above = [a for a in angle_vals if a["val"] >= cur_close]
        below = [a for a in angle_vals if a["val"] < cur_close]
        riding = min(above, key=lambda x: x["val"]) if above else None
        next_r = max(below, key=lambda x: x["val"]) if below else None

    return {
        "riding": riding,
        "next": next_r,
        "all": angle_vals,
    }


# ── time cycles ───────────────────────────────────────────────────────────────
def _time_cycles(pivot: dict, df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    """Project Gann time cycle windows (30/60/90 bar or equivalent) from the pivot."""
    w = _tfw(tf)
    cycles = w["cycle_bars"]
    pi_loc = pivot["bar_idx"]    # in windowed array (0-based from window start)

    # Map back to absolute df position
    n = len(df)
    chart_bars = min(w["chart_bars"], n)
    df_start   = n - chart_bars
    pivot_abs  = df_start + pi_loc

    results = []
    for c in cycles:
        target_abs = pivot_abs + c
        if target_abs < n:
            ts = df.index[target_abs]
            date_str = fmt_date(ts, tf)
            passed = True
        else:
            # future bar — estimate calendar days
            bars_past = n - 1 - pivot_abs
            bars_left = c - bars_past
            days_per_bar = {"Daily": 1, "Weekly": 7, "Monthly": 30}.get(tf, 1)
            future_ts = df.index[-1] + pd.Timedelta(days=int(bars_left * days_per_bar))
            date_str = fmt_date(future_ts, tf) + " (est)"
            passed = False

        if tf == "Daily":
            label = f"{c}-bar count"
            significance = "major price-time square" if c >= 60 else "minor turn window"
        elif tf == "Weekly":
            label = f"{c}-week cycle"
            significance = "annual cycle" if c == 52 else ("half-year" if c == 26 else "quarter-year")
        else:
            label = f"{c}-month cycle"
            significance = "2-year rhythm" if c == 24 else ("annual" if c == 12 else "semi-annual")

        tone = "copper" if c == cycles[-1] else ("ink-2" if passed else "violet")
        results.append({
            "c": label, "date": date_str, "role": significance,
            "tone": tone, "passed": passed, "bars": c,
        })
    return results


# ── bars array for the chart ──────────────────────────────────────────────────
def _to_bars(df: pd.DataFrame, chart_bars: int) -> List[Dict[str, Any]]:
    window = df.tail(chart_bars)
    out = []
    for _, row in window.iterrows():
        out.append({
            "o":  round(float(row["Open"]),  2),
            "c":  round(float(row["Close"]), 2),
            "hi": round(float(row["High"]),  2),
            "lo": round(float(row["Low"]),   2),
            "v":  round(float(row.get("rvol", 1.0)), 3),
        })
    return out


# ── angle table for the UI ────────────────────────────────────────────────────
def _angle_table(angle_info: dict, pivot: dict, chart_n: int) -> List[Dict[str, Any]]:
    all_angles = angle_info.get("all", [])
    riding = angle_info.get("riding")
    riding_label = riding["label"] if riding else None

    rows = []
    for a in all_angles:
        is_key = (a["label"] == "1×1")
        vs_price = "riding ←" if a["label"] == riding_label else ("above" if a["val"] > all_angles[3]["val"] else "below")
        rows.append({
            "a":   a["label"],
            "deg": a["deg"],
            "now": f"${a['val']:.2f}",
            "role": a["role"],
            "st":  vs_price,
            "tone": a["tone"],
            "is_key": is_key,
        })
    return rows


# ── sq9 table for the UI ──────────────────────────────────────────────────────
def _sq9_table(sq9_levels: List[Dict[str, Any]], cur_close: float) -> List[Dict[str, Any]]:
    rows = []
    for lv in sq9_levels:
        diff_pct = lv["diff_pct"]
        is_above = lv["price"] > cur_close
        role_prefix = "R" if is_above else "S"
        rows.append({
            "lvl":  f"${lv['price']:.2f}",
            "rot":  lv["rot"],
            "role": f"{role_prefix} · {lv['role']}",
            "tone": lv["tone"],
            "price": lv["price"],
            "diff_pct": diff_pct,
        })
    # sort: support closest below first, then resistance closest above
    support = sorted([r for r in rows if r["price"] <= cur_close], key=lambda x: -x["price"])
    resist  = sorted([r for r in rows if r["price"] >  cur_close], key=lambda x:  x["price"])
    return support + resist


# ── nearest support/resistance from sq9 + fan lines ──────────────────────────
def _nearest_sr(sq9_rows: List[Dict], angle_info: dict, cur_close: float) -> Dict[str, Any]:
    all_angles = angle_info.get("all", [])

    # Sq9 support = highest sq9 below price; resistance = lowest sq9 above
    sq9_s = [r for r in sq9_rows if r["price"] < cur_close]
    sq9_r = [r for r in sq9_rows if r["price"] > cur_close]
    sq9_supp = max(sq9_s, key=lambda x: x["price"]) if sq9_s else None
    sq9_res  = min(sq9_r, key=lambda x: x["price"]) if sq9_r else None

    # Fan support = highest fan angle below price; resistance = lowest above
    fan_s = [a for a in all_angles if a["val"] < cur_close]
    fan_r = [a for a in all_angles if a["val"] > cur_close]
    fan_supp = max(fan_s, key=lambda x: x["val"]) if fan_s else None
    fan_res  = min(fan_r, key=lambda x: x["val"]) if fan_r else None

    return {
        "sq9_support":    sq9_supp,
        "sq9_resistance": sq9_res,
        "fan_support":    fan_supp,
        "fan_resistance": fan_res,
    }


# ── price-time square note ────────────────────────────────────────────────────
def _sq_note(pivot: dict, cur_close: float, tf: str) -> str:
    """Produce the Gann 'price = time' squaring note."""
    pp = pivot["price"]
    bars = pivot["bar_offset"]  # bars since pivot
    price_range = abs(cur_close - pp)
    unit = pivot["atr"]
    time_units = bars  # bars elapsed
    price_units = round(price_range / unit, 1) if unit else 0
    sq = "SQUARED" if abs(price_units - time_units) / max(time_units, 1) < 0.15 else "not yet squared"
    return (f"Pivot at ${pp:.2f} ({pivot['date']}), {bars} bars ago. "
            f"Price moved {price_units}× ATR over {time_units} bars — {sq}.")


# ── stat header ───────────────────────────────────────────────────────────────
def _stat(pivot: dict, angle_info: dict, sq9_rows: List, cur_close: float, confidence: float) -> Dict:
    riding = angle_info.get("riding")
    next_r = angle_info.get("next")
    sq9_res = next((r for r in sq9_rows if r["price"] > cur_close), None)
    next_cycle = None  # caller sets this

    return {
        "master_angle": f"{riding['label']} · ${riding['val']:.2f}" if riding else "—",
        "price_vs_1x1": "above" if riding and riding["label"] in ("2×1","8×1","4×1","3×1") else
                         ("below" if riding and riding["label"] in ("1×2","1×4","1×8") else "at 1×1"),
        "next_sq9":     f"${sq9_res['price']:.2f} ({sq9_res['rot']})" if sq9_res else "—",
        "next_fan":     f"{next_r['label']} · ${next_r['val']:.2f}" if next_r else "—",
        "confidence":   round(confidence, 2),
        "pivot_type":   pivot["type"],
        "pivot_price":  pivot["price"],
        "pivot_date":   pivot["date"],
    }


# ── confidence heuristic ──────────────────────────────────────────────────────
def _confidence(df: pd.DataFrame, pivot: dict, angle_info: dict, sq9_rows: List) -> float:
    """
    Cap at 0.60 — Gann is heuristic. Boost slightly for:
    - pivot is clear (large vol spike)
    - price is close to a 1×1 or cardinal sq9 (confluence)
    - pivot is recent enough to be meaningful
    """
    score = 0.30  # base
    cur_close = float(df["Close"].iloc[-1])

    # Pivot recency (more recent = more relevant)
    if pivot["bar_offset"] < 20:
        score += 0.08
    elif pivot["bar_offset"] < 40:
        score += 0.04

    # Price near 1×1
    riding = angle_info.get("riding")
    if riding and riding["label"] == "1×1":
        score += 0.06
    elif riding and riding["label"] in ("2×1", "1×2"):
        score += 0.03

    # Price within 1% of a cardinal sq9 level
    for lv in sq9_rows:
        if lv["rot"] in ("90°", "180°", "270°", "360°"):
            if abs(lv["price"] - cur_close) / cur_close < 0.01:
                score += 0.06
                break
            elif abs(lv["price"] - cur_close) / cur_close < 0.025:
                score += 0.03
                break

    return round(min(score, 0.60), 2)


# ── sq9 hlines for the chart ──────────────────────────────────────────────────
def _sq9_hlines(sq9_rows: List[Dict], cur_close: float) -> List[Dict]:
    hlines = []
    for r in sq9_rows[:4]:   # limit visual clutter
        is_above = r["price"] > cur_close
        tone = "gn" if is_above else "cy"
        hlines.append({
            "price": r["price"],
            "label": f"Sq9 · {r['lvl']} ({r['rot']})",
            "tone": "violet" if r.get("tone") == "violet" else tone,
            "dash": "2 5" if r.get("tone") == "cy" else "5 4",
        })
    return hlines


# ══════════════════════════════════════════════════════════════════════════════
# main detect entry point
# ══════════════════════════════════════════════════════════════════════════════
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Compute Gann fan angles + Square-of-Nine levels from real bars."""
    tf = meta.get("tf", "Daily")
    w = _tfw(tf)
    n = len(df)

    cur_close = round(float(df["Close"].iloc[-1]), 2)

    # Need at least 30 bars for a meaningful pivot + fan
    if n < 30:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Only {n} {tf.lower()} bars available — need ≥30 for Gann analysis.",
            "cur_close": cur_close,
        }

    # Find pivot
    pivot = _find_pivot(df, tf)
    if pivot is None:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": "Could not identify a significant pivot in the available bars.",
            "cur_close": cur_close,
        }

    # Windowed bar array for the chart
    chart_bars = min(w["chart_bars"], n)
    bars = _to_bars(df, chart_bars)

    # Re-index pivot to windowed array (bar_idx is relative to tail window)
    # bar_idx was set as (n-1) - bar_offset, so within the window:
    window_start = n - chart_bars
    pivot_abs = (n - 1) - pivot["bar_offset"]
    pivot_win_idx = max(0, pivot_abs - window_start)
    pivot["bar_idx"] = pivot_win_idx

    # Gann unit (price per bar for 1×1)
    unit = _compute_unit(df, pivot, tf)
    pivot["unit"] = unit

    # Fan lines (including projection)
    fan_extend = w["fan_extend"]
    fan_lines = _fan_lines(pivot, unit, chart_bars, fan_extend)

    # Which angle is price riding?
    angle_info = _current_angle(cur_close, pivot, fan_lines, chart_bars)

    # Square-of-Nine levels
    sq9_raw    = _sq9_levels_around(cur_close)
    sq9_rows   = _sq9_table(sq9_raw, cur_close)

    # Sq9 hlines for chart
    sq9_hlines = _sq9_hlines(sq9_rows, cur_close)

    # Time cycles
    cycles = _time_cycles(pivot, df, tf)

    # Nearest S/R
    sr = _nearest_sr(sq9_rows, angle_info, cur_close)

    # Confidence (honest, ≤0.60)
    confidence = _confidence(df, pivot, angle_info, sq9_rows)

    # Angle table for the UI
    angle_table = _angle_table(angle_info, pivot, chart_bars)

    # Stat header
    stat = _stat(pivot, angle_info, sq9_rows, cur_close, confidence)

    # Price-time square note
    sq_note = _sq_note(pivot, cur_close, tf)

    # Nearest support / resistance
    riding   = angle_info.get("riding")
    next_ang = angle_info.get("next")
    supp_str = (f"Fan {sr['fan_support']['label']} ${sr['fan_support']['val']:.2f}"
                if sr.get("fan_support") else "—")
    res_str  = (f"Fan {sr['fan_resistance']['label']} ${sr['fan_resistance']['val']:.2f}"
                if sr.get("fan_resistance") else "—")
    if sr.get("sq9_support"):
        supp_str += f" · Sq9 ${sr['sq9_support']['price']:.2f}"
    if sr.get("sq9_resistance"):
        res_str  += f" · Sq9 ${sr['sq9_resistance']['price']:.2f}"

    # Human-readable "The Read"
    riding_label = riding["label"] if riding else "no angle"
    riding_price = f"${riding['val']:.2f}" if riding else "—"
    sq9_next = next((r for r in sq9_rows if r["price"] > cur_close), None)
    sq9_next_str = f"${sq9_next['price']:.2f} ({sq9_next['rot']})" if sq9_next else "—"
    next_cycle_str = next((c["date"] for c in cycles if not c["passed"]), "—")

    read = (
        f"Price is riding the {riding_label} angle ({riding_price}) from the "
        f"{pivot['type']} pivot at ${pivot['price']:.2f} ({pivot['date']}). "
        f"Nearest Sq-9 overhead: {sq9_next_str}. "
        f"Next time turn: {next_cycle_str}. "
        f"Use as confluence overlay — Gann confidence: {int(confidence*100)}%."
    )

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "confidence": confidence,
        "bars":       bars,
        "pivot":      pivot,
        "angles":     angle_table,
        "fan_lines":  fan_lines,
        "sq9":        sq9_rows,
        "sq9_hlines": sq9_hlines,
        "cycles":     cycles,
        "sr":         {"support": supp_str, "resistance": res_str},
        "sq_note":    sq_note,
        "read":       read,
        "stat":       stat,
        "cur_close":  cur_close,
    }
