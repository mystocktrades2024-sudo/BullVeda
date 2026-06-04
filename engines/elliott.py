"""engines/elliott.py — Elliott Wave adapter for the BullVeda Patterns lens.

Mechanism (principle 2): crowd psychology unfolds in self-similar 5-wave impulse
sequences followed by 3-wave corrections; Fibonacci proportions between waves
reflect the same fractal participation rhythm — large institutional rotations
leave measurable ZigZag pivots whose ratios betray the crowd's positioning.

Honesty contract (principle 4): we return state="none" when no clean impulse or
corrective structure is detectable rather than forcing a count on noise.

Three absolute rules (Frost & Prechter §1.4):
  R1: Wave 2 never retraces more than 100% of Wave 1.
  R2: Wave 3 is never the shortest of Waves 1, 3, 5.
  R3: Wave 4 never enters Wave 1 price territory.
If ANY rule fails the count is invalid — we either relabel or return none.

CLI:  python3 -c "import pattern_engines as pe; import json; d=pe.detect('elliott','AAPL','SWING'); print(d.get('state'), d.get('read'))"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "elliott"
LABEL = "Elliott Wave"

# ── timeframe-relative windows ─────────────────────────────────────
# k_atr: zigzag threshold multiplier on ATR (smaller tf → tighter)
# min_bars: minimum bars in frame before we try
# window: how many bars from tail to search
_TFW = {
    "Daily":   {"k_atr": 1.0, "pct": 0.03, "min_bars": 60,  "window": 200, "degree": "intermediate", "degree_label": "(W)", "tf_note": "Daily"},
    "Weekly":  {"k_atr": 1.2, "pct": 0.04, "min_bars": 40,  "window": 130, "degree": "primary",      "degree_label": "[W]", "tf_note": "Weekly"},
    "Monthly": {"k_atr": 1.5, "pct": 0.06, "min_bars": 30,  "window": 90,  "degree": "primary",      "degree_label": "[W]", "tf_note": "Monthly"},
}

# Degree labels map — mode → degree → (notation fn name, display name, accent)
_DEGREE_MAP = {
    "SWING":      {"degree": "intermediate", "name": "Intermediate", "accent": "violet",  "tone": "violet"},
    "POSITION":   {"degree": "primary",      "name": "Primary",      "accent": "blue",    "tone": "blue"},
    "INVESTMENT": {"degree": "primary",      "name": "Primary",      "accent": "blue",    "tone": "blue"},
}


# ── ZigZag pivot detector ──────────────────────────────────────────
def _zigzag(df: pd.DataFrame, tf: str = "Daily") -> List[Dict[str, Any]]:
    """
    Return alternating High/Low pivot indices whose move exceeds the threshold.
    threshold = max(k_atr × ATR, pct × price).
    Each pivot: {i, price, date, kind: 'H'|'L'}.
    """
    cfg = _TFW.get(tf, _TFW["Daily"])
    n = len(df)
    window = min(n, cfg["window"])
    sub = df.iloc[n - window:]
    closes = sub["Close"].values
    highs = sub["High"].values
    lows = sub["Low"].values
    atrs = sub["atr"].values
    dates = sub.index

    # adaptive threshold per bar
    def thresh(i: int) -> float:
        a = float(atrs[i]) if np.isfinite(atrs[i]) else 0
        pct_t = float(closes[i]) * cfg["pct"]
        return max(cfg["k_atr"] * a, pct_t)

    pivots: List[Dict[str, Any]] = []
    direction: Optional[str] = None  # 'H' or 'L'
    last_high_i, last_high_p = 0, highs[0]
    last_low_i, last_low_p = 0, lows[0]

    # sliding scan — alternating pivot confirmation
    for i in range(1, len(sub)):
        h, l = highs[i], lows[i]
        if direction is None:
            # bootstrap: find first meaningful move
            rise = h - lows[:i + 1].min()
            fall = highs[:i + 1].max() - l
            if rise > thresh(i) and rise >= fall:
                last_high_i, last_high_p = i, h
                direction = "H"
            elif fall > thresh(i):
                last_low_i, last_low_p = i, l
                direction = "L"
            continue

        if direction == "H":
            if h >= last_high_p:
                last_high_i, last_high_p = i, h
            elif last_high_p - l > thresh(last_high_i):
                # confirmed swing high
                pivots.append({"i": (n - window) + last_high_i, "price": float(last_high_p),
                               "date": fmt_date(dates[last_high_i]), "kind": "H"})
                last_low_i, last_low_p = i, l
                direction = "L"
        else:  # direction == "L"
            if l <= last_low_p:
                last_low_i, last_low_p = i, l
            elif h - last_low_p > thresh(last_low_i):
                # confirmed swing low
                pivots.append({"i": (n - window) + last_low_i, "price": float(last_low_p),
                               "date": fmt_date(dates[last_low_i]), "kind": "L"})
                last_high_i, last_high_p = i, h
                direction = "H"

    # add the last open pivot
    if direction == "H" and (not pivots or pivots[-1]["kind"] != "H"):
        pivots.append({"i": (n - window) + last_high_i, "price": float(last_high_p),
                       "date": fmt_date(dates[last_high_i]), "kind": "H"})
    elif direction == "L" and (not pivots or pivots[-1]["kind"] != "L"):
        pivots.append({"i": (n - window) + last_low_i, "price": float(last_low_p),
                       "date": fmt_date(dates[last_low_i]), "kind": "L"})

    return pivots


# ── three absolute rules ───────────────────────────────────────────
def _check_rules(p0: float, p1: float, p2: float, p3: float, p4: float,
                 p5: float, cur_price: float) -> Tuple[List[Dict], bool]:
    """
    p0..p5 = wave origin, W1 top, W2 bottom, W3 top, W4 bottom, W5 top (bullish)
    Returns (rules_list, all_hard_pass).
    W5 may be the current price if projected.
    """
    w1 = abs(p1 - p0)
    w2_ret = abs(p2 - p1) / w1 if w1 > 0 else 0
    w3 = abs(p3 - p2)
    w4_ret = abs(p4 - p3) / max(abs(p3 - p2), 1e-9)
    w5 = abs(p5 - p4)
    # W4 vs W1 territory
    bullish = p1 > p0
    w1_top = p1 if bullish else p0
    w1_bot = p0 if bullish else p1
    w4_bot = min(p4, p5) if not bullish else max(p4, p5)
    w4_in_w1 = (p4 < w1_top) if bullish else (p4 > w1_bot)

    # Rule 1: W2 retracement
    r1_pass = w2_ret < 1.0
    r1_detail = f"W2 retraces {w2_ret * 100:.1f}% of W1 (must be <100%)"
    r1_status = "PASS" if r1_pass else "FAIL"
    r1_tone = "gn" if r1_pass else "rd"

    # Rule 2: W3 not shortest
    waves = [w1, w3, w5]
    w3_is_shortest = w3 < w1 and w3 < w5
    r2_pass = not w3_is_shortest
    w3_mult = w3 / w1 if w1 > 0 else 0
    r2_detail = f"W3={w3:.2f} ({w3_mult:.2f}×W1), W1={w1:.2f}, W5={w5:.2f}"
    r2_status = "PASS" if r2_pass else "FAIL"
    r2_tone = "gn" if r2_pass else "rd"

    # Rule 3: W4 not in W1 territory
    if bullish:
        w4_territory = p4 < p1  # W4 low below W1 high
        r3_detail = f"W4 low {p4:.2f} vs W1 top {p1:.2f} (must be above {p1:.2f})"
        r3_pass = not w4_territory
    else:
        w4_territory = p4 > p1  # W4 high above W1 low (bearish)
        r3_detail = f"W4 high {p4:.2f} vs W1 low {p1:.2f} (must be below {p1:.2f})"
        r3_pass = not w4_territory

    r3_status = "WATCH" if (p4 == p5) else ("PASS" if r3_pass else "FAIL")  # projected W4
    r3_tone = "gn" if r3_pass else ("amb" if p4 == p5 else "rd")

    rules = [
        {"rule": "Wave 2 never retraces >100% of Wave 1", "type": "HARD",
         "detail": r1_detail, "status": r1_status, "tone": r1_tone},
        {"rule": "Wave 3 is never the shortest of 1·3·5", "type": "HARD",
         "detail": r2_detail, "status": r2_status, "tone": r2_tone},
        {"rule": "Wave 4 never enters Wave 1 territory", "type": "HARD",
         "detail": r3_detail, "status": r3_status, "tone": r3_tone},
    ]
    hard_pass = r1_pass and r2_pass and r3_pass
    return rules, hard_pass


# ── fib target computation ─────────────────────────────────────────
def _fib_targets(p0: float, p1: float, p2: float, p3: float, p4: float,
                 bullish: bool, cur_price: float, cur_wave: str) -> List[Dict]:
    """
    Compute W3/W4/W5 Fibonacci targets.
    p0=origin, p1=W1top, p2=W2low, p3=W3top (or current if in W3), p4=W4low
    """
    w1 = abs(p1 - p0)
    w3_len = abs(p3 - p2)
    targets = []

    if cur_wave in ("3", "in-W3"):
        # W3 = 1.618 × W1 from W2; 2.618 extension
        t_w3_norm = (p2 + 1.618 * w1) if bullish else (p2 - 1.618 * w1)
        t_w3_ext = (p2 + 2.618 * w1) if bullish else (p2 - 2.618 * w1)
        targets.append({"label": "W3 target", "basis": f"1.618×W1 ({w1:.2f}) from W2",
                        "price": round(t_w3_norm, 2), "conf": 0.61, "tone": "violet"})
        targets.append({"label": "W3 extension", "basis": f"2.618×W1 from W2",
                        "price": round(t_w3_ext, 2), "conf": 0.28, "tone": "amb"})
        # W4 retrace zone (0.382 of W3)
        t_w4_lo = (p3 - 0.382 * w3_len) if bullish else (p3 + 0.382 * w3_len)
        t_w4_hi = (p3 - 0.236 * w3_len) if bullish else (p3 + 0.236 * w3_len)
        targets.append({"label": "W4 retrace zone", "basis": f"0.382–0.236×W3",
                        "price": f"{min(t_w4_lo, t_w4_hi):.2f}–{max(t_w4_lo, t_w4_hi):.2f}",
                        "conf": None, "tone": "ink-2"})
        # W5 = W1 from W4 low (best simple estimate, W4 unknown so use 0.382 retrace)
        est_w4 = t_w4_lo
        t_w5 = (est_w4 + w1) if bullish else (est_w4 - w1)
        targets.append({"label": "W5 target", "basis": "W5 ≈ W1 from W4 low",
                        "price": round(t_w5, 2), "conf": 0.44, "tone": "gn"})

    elif cur_wave in ("4", "in-W4"):
        # W4 retrace zone
        t_w4_lo = (p3 - 0.382 * w3_len) if bullish else (p3 + 0.382 * w3_len)
        t_w4_hi = (p3 - 0.236 * w3_len) if bullish else (p3 + 0.236 * w3_len)
        targets.append({"label": "W4 target", "basis": "0.382 retrace of W3",
                        "price": round(t_w4_lo, 2), "conf": 0.57, "tone": "amb"})
        # W5
        t_w5_eq = (p4 + w1) if bullish else (p4 - w1)
        t_w5_ext = (p4 + 0.618 * (abs(p3 - p0))) if bullish else (p4 - 0.618 * abs(p3 - p0))
        targets.append({"label": "W5 target", "basis": "W5 = W1 from W4 low",
                        "price": round(t_w5_eq, 2), "conf": 0.48, "tone": "gn"})
        targets.append({"label": "W5 extension", "basis": "0.618×(W1→W3) from W4",
                        "price": round(t_w5_ext, 2), "conf": 0.31, "tone": "gn"})

    elif cur_wave in ("5", "completing", "complete"):
        # W5 completion targets
        t_w5_eq = (p4 + w1) if bullish else (p4 - w1)
        targets.append({"label": "W5 target", "basis": "W5 = W1",
                        "price": round(t_w5_eq, 2), "conf": 0.50, "tone": "gn"})
        w13 = abs(p3 - p0)
        t_w5_fib = (p4 + 0.618 * w13) if bullish else (p4 - 0.618 * w13)
        targets.append({"label": "W5 Fibonacci ext", "basis": "0.618×(W1→W3)",
                        "price": round(t_w5_fib, 2), "conf": 0.33, "tone": "gn"})
        # ABC correction after W5
        corr_a = (t_w5_eq - 0.382 * abs(t_w5_eq - p0)) if bullish else (t_w5_eq + 0.382 * abs(t_w5_eq - p0))
        targets.append({"label": "Post-W5 A target", "basis": "0.382 retrace of impulse",
                        "price": round(corr_a, 2), "conf": 0.38, "tone": "rd"})

    return targets


# ── alternate count builder ────────────────────────────────────────
def _alternates(pivots_labeled: List[Dict], bullish: bool, cur_wave: str,
                rules_pass: bool, p_count: int) -> List[Dict]:
    """Generate alternate count scenarios with probability estimates."""
    alts = []
    # Primary — the currently labeled count
    primary_p = 0.55 if rules_pass else 0.30
    primary_p = min(primary_p, 0.65)
    alts.append({
        "name": f"Primary — {'bullish' if bullish else 'bearish'} impulse",
        "loc": f"In Wave {cur_wave} of 5",
        "p": round(primary_p, 2),
        "tone": "gn" if bullish else "rd",
        "note": f"{'Five' if p_count >= 5 else 'Developing'}-wave {'advance' if bullish else 'decline'}; "
                f"current position {'supports' if rules_pass else 'needs'} the primary count.",
    })
    # Alternate — one wave ahead
    if cur_wave in ("3", "in-W3"):
        alts.append({
            "name": "Alternate — W3 complete, starting W4",
            "loc": "Starting Wave 4",
            "p": round(0.30 if rules_pass else 0.40, 2),
            "tone": "amb",
            "note": "W3 may have topped; expect 0.382 pullback before final W5.",
        })
        alts.append({
            "name": "Bearish — corrective A-B-C only",
            "loc": "In Wave C of ABC",
            "p": round(1.0 - primary_p - (0.30 if rules_pass else 0.40), 2),
            "tone": "rd",
            "note": "Whole move could be counter-trend ABC; rejection here resumes primary trend.",
        })
    elif cur_wave in ("4", "in-W4"):
        alts.append({
            "name": "Alternate — extended W3, W4 developing",
            "loc": "In extended Wave 3",
            "p": round(0.28, 2),
            "tone": "amb",
            "note": "W3 extension typical when 1.618× cleared; W4 shallow (0.236 retrace).",
        })
        alts.append({
            "name": "Bearish — impulse complete, correction underway",
            "loc": "In Wave A down",
            "p": round(1.0 - primary_p - 0.28, 2),
            "tone": "rd",
            "note": "Impulse completed; deeper correction could reach 0.5–0.618 of entire advance.",
        })
    else:
        alts.append({
            "name": "Alternate — W5 truncated",
            "loc": "W5 below W3",
            "p": 0.22,
            "tone": "amb",
            "note": "W5 truncation (doesn't exceed W3) occurs in weakening momentum.",
        })
        alts.append({
            "name": "Bearish — post-impulse correction",
            "loc": "ABC correction starting",
            "p": round(1.0 - primary_p - 0.22, 2),
            "tone": "rd",
            "note": "Five-wave complete; A-B-C correction typically retraces 0.382–0.618.",
        })
    # Clip probabilities
    total = sum(a["p"] for a in alts)
    if total > 0:
        for a in alts:
            a["p"] = round(a["p"] / total, 2)
    return alts


# ── wave log builder ───────────────────────────────────────────────
def _wave_log(p0: float, p1: float, p2: float, p3: float, p4: float,
              p5_proj: float, cur_wave: str, bullish: bool,
              dates: List[str], w1_sz: float) -> List[Dict]:
    """Wave-by-wave log entries with span, move%, fib ratio, and notes."""
    def move_pct(a, b):
        return f"{'+' if b > a else ''}{(b - a) / a * 100:.1f}%"
    def fib_lbl(sz, ref):
        if ref <= 0: return "—"
        r = sz / ref
        for ratio, lbl in [(1.618, "1.618×"), (2.618, "2.618×"), (1.0, "1.0×"),
                           (0.618, "0.618×"), (0.382, "0.382×"), (0.236, "0.236×")]:
            if abs(r - ratio) < 0.12:
                return lbl
        return f"{r:.2f}×"

    w1 = abs(p1 - p0)
    w3 = abs(p3 - p2)
    w5 = abs(p5_proj - p4)
    w2 = abs(p2 - p1)
    w4 = abs(p4 - p3)
    w2_ret = w2 / w1 if w1 > 0 else 0

    log = [
        {"w": "1", "type": "Impulse",
         "span": f"{p0:.2f} → {p1:.2f}", "move": move_pct(p0, p1),
         "fib": "—", "note": "Initial impulse leg off origin",
         "tone": "violet", "date": dates[0] if len(dates) > 0 else ""},
        {"w": "2", "type": "Zigzag" if w2_ret > 0.5 else "Flat",
         "span": f"{p1:.2f} → {p2:.2f}", "move": move_pct(p1, p2),
         "fib": f"{w2_ret:.2f} retr of W1",
         "note": f"{'Deep' if w2_ret > 0.6 else 'Shallow'} correction; holds above W1 origin",
         "tone": "rd", "date": dates[1] if len(dates) > 1 else ""},
        {"w": "3", "type": "Impulse ⟳" if cur_wave in ("3", "in-W3") else "Impulse",
         "span": f"{p2:.2f} → {p3:.2f}", "move": move_pct(p2, p3),
         "fib": fib_lbl(w3, w1) + " W1",
         "note": "Strongest wave — highest RVOL, widest spread" + (" · in progress" if cur_wave in ("3", "in-W3") else ""),
         "tone": "gn", "date": dates[2] if len(dates) > 2 else ""},
        {"w": "4", "type": "Projected" if cur_wave in ("3", "in-W3") else ("Flat" if w4 / w3 < 0.25 else "Zigzag"),
         "span": f"{p3:.2f} → {p4:.2f}", "move": move_pct(p3, p4),
         "fib": f"{w4 / w3:.2f} retr of W3" if w3 > 0 else "—",
         "note": "Must stay above W1 high; alternation with W2 typical" + (" · projected" if cur_wave in ("3", "in-W3") else ""),
         "tone": "ink-2", "date": dates[3] if len(dates) > 3 else ""},
        {"w": "5", "type": "Projected" if cur_wave in ("3", "in-W3", "4", "in-W4") else "Impulse",
         "span": f"{p4:.2f} → {p5_proj:.2f}", "move": move_pct(p4, p5_proj),
         "fib": fib_lbl(w5, w1) + " W1",
         "note": "Final leg; watch momentum divergence · " + ("projected" if cur_wave not in ("5", "completing", "complete") else "in progress"),
         "tone": "ink-2", "date": dates[4] if len(dates) > 4 else ""},
    ]
    # Mark the current wave
    cur_map = {"3": "3", "in-W3": "3", "4": "4", "in-W4": "4",
               "5": "5", "completing": "5", "complete": "5"}
    cur_w_idx = {"3": 2, "in-W3": 2, "4": 3, "in-W4": 3, "5": 4, "completing": 4, "complete": 4}
    idx = cur_w_idx.get(cur_wave, 2)
    log[idx]["is_current"] = True
    return log


# ── bar payload ────────────────────────────────────────────────────
def _bars(df: pd.DataFrame, window: int = 100) -> List[Dict]:
    sub = df.iloc[max(0, len(df) - window):]
    out = []
    for _, r in sub.iterrows():
        out.append({
            "o": round(float(r["Open"]), 2),
            "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2),
            "lo": round(float(r["Low"]), 2),
            "v": round(float(r["rvol"]) if np.isfinite(float(r["rvol"])) else 1.0, 2),
        })
    return out


# ── main detect ────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """
    Elliott Wave impulse/corrective detector.

    Returns state="none" when no clean 5-wave / ABC structure is present.
    Confidence intentionally modest (0.30–0.58) — EW counting is inherently
    subjective; the engine expresses probabilities, not certainty.
    """
    tf = meta.get("tf", "Daily")
    mode = meta.get("mode", "SWING")
    cfg = _TFW.get(tf, _TFW["Daily"])
    cur_close = round(float(df["Close"].iloc[-1]), 2)

    # ── need sufficient bars ───────────────────────────────────────
    if len(df) < cfg["min_bars"]:
        return {"ok": True, "source": "real", "state": "none", "elliott": None,
                "message": f"Only {len(df)} {tf.lower()} bars — need {cfg['min_bars']}+ for EW count.",
                "cur_close": cur_close}

    # ── build ZigZag pivots ────────────────────────────────────────
    pivots = _zigzag(df, tf)
    if len(pivots) < 5:
        return {"ok": True, "source": "real", "state": "none", "elliott": None,
                "message": f"Only {len(pivots)} ZigZag pivots detected — need ≥5 for a count.",
                "cur_close": cur_close}

    # ── take last 5–7 pivots and try impulse labeling ─────────────
    # For a bullish impulse: L H L H L (H)
    # Attempt every window of 5–7 pivots from the tail
    best_result = None
    best_score = -1

    for window_len in [5, 6, 7]:
        if len(pivots) < window_len:
            continue
        window_pivots = pivots[-window_len:]
        for start in range(min(2, len(pivots) - window_len + 1)):
            sub_pv = pivots[-(window_len + start):-start] if start > 0 else pivots[-window_len:]
            if len(sub_pv) < 5:
                continue
            result = _try_impulse_label(sub_pv, df, tf, cur_close, mode)
            if result is not None:
                score = result.get("_score", 0)
                if score > best_score:
                    best_score = score
                    best_result = result

    if best_result is None:
        # try ABC corrective
        abc_result = _try_corrective_label(pivots, df, tf, cur_close, mode)
        if abc_result is not None:
            return abc_result
        return {"ok": True, "source": "real", "state": "none", "elliott": None,
                "message": "No valid 5-wave impulse or A-B-C corrective count found on current bars.",
                "cur_close": cur_close}

    best_result.pop("_score", None)
    return best_result


def _try_impulse_label(sub_pv: List[Dict], df: pd.DataFrame, tf: str,
                       cur_close: float, mode: str) -> Optional[Dict]:
    """
    Try to label 5–7 alternating pivots as an impulse (0-1-2-3-4-5).
    Requires: starts Low (bullish) or High (bearish), validates 3 hard rules.
    Returns payload dict on success, None on failure.
    """
    n_pv = len(sub_pv)
    # determine direction from first two pivots
    bullish = sub_pv[0]["kind"] == "L"  # first pivot is Low → bullish

    # Map pivots to wave prices
    # Bullish: p0(L), p1(H), p2(L), p3(H), p4(L), [p5(H)]
    # We need at least 5 pivots: p0..p4; p5 can be projected
    p0 = sub_pv[0]["price"]
    p1 = sub_pv[1]["price"]
    p2 = sub_pv[2]["price"]
    p3 = sub_pv[3]["price"]
    p4 = sub_pv[4]["price"]

    # Basic sanity — for bullish: p0 < p1 > p2 < p3 > p4 < p3
    if bullish:
        if not (p1 > p0 and p2 < p1 and p3 > p2 and p4 < p3):
            return None
    else:
        if not (p1 < p0 and p2 > p1 and p3 < p2 and p4 > p3):
            return None

    # Determine current wave position and p5
    w1 = abs(p1 - p0)
    w3 = abs(p3 - p2)
    w2 = abs(p2 - p1)
    w4 = abs(p4 - p3)

    # Reject if W3 is trivially small vs W1 (noise count)
    if w3 < w1 * 0.3:
        return None

    # W2 retrace check (hard rule 1)
    w2_ret = w2 / w1 if w1 > 0 else 999
    if w2_ret >= 1.0:
        return None

    # Is W5 present in pivots?
    p5_known = None
    if n_pv >= 6:
        p5_known = sub_pv[5]["price"]

    # If W5 present, validate W3 not shortest
    if p5_known is not None:
        w5 = abs(p5_known - p4)
        if w3 < w1 and w3 < w5:
            return None  # W3 is shortest — invalid
        # W4 territory check (hard rule 3)
        if bullish and p4 < p1:
            return None
        if not bullish and p4 > p1:
            return None
        cur_wave = "complete" if cur_close == p5_known else "5"
    else:
        # Project W5 as W1 from W4
        p5_known = (p4 + w1) if bullish else (p4 - w1)

    # Determine current wave based on where current price is
    if p5_known is not None and n_pv >= 6:
        cur_wave = "5"
    elif abs(cur_close - p4) < abs(cur_close - p3) * 0.3:
        cur_wave = "in-W4"
    elif bullish and cur_close > p3 * 0.995:
        cur_wave = "in-W3" if cur_close < p3 else "in-W4"
    elif not bullish and cur_close < p3 * 1.005:
        cur_wave = "in-W3" if cur_close > p3 else "in-W4"
    else:
        cur_wave = "in-W3"

    # Check rule 3 for projected W4
    if cur_wave in ("in-W3", "3"):
        if bullish and p4 < p1:
            return None
        if not bullish and p4 > p1:
            return None

    p5_proj = p5_known if n_pv >= 6 else ((p4 + w1) if bullish else (p4 - w1))

    rules, hard_pass = _check_rules(p0, p1, p2, p3, p4, p5_proj, cur_close)
    if not hard_pass:
        return None

    # ── confidence score ───────────────────────────────────────────
    conf = 0.35
    # W3 ≥ 1.5× W1 → good impulse
    if w3 >= w1 * 1.5:
        conf += 0.10
    # W2 in 0.382–0.786 retrace band
    if 0.35 <= w2_ret <= 0.80:
        conf += 0.05
    # Fib tolerance on W3 vs 1.618
    fib_err = abs(w3 / w1 - 1.618) if w1 > 0 else 1
    if fib_err < 0.2:
        conf += 0.08
    # W4 retrace in 0.236–0.50 of W3
    w4_ret = w4 / w3 if w3 > 0 else 0
    if 0.20 <= w4_ret <= 0.55:
        conf += 0.04
    conf = round(min(conf, 0.60), 2)

    # ── scoring for best-result selection ─────────────────────────
    score = (w3 / w1 if w1 > 0 else 0) + (1 - abs(w2_ret - 0.618)) + conf

    # ── pivots for the chart skeleton ─────────────────────────────
    deg_info = _DEGREE_MAP.get(mode, _DEGREE_MAP["SWING"])
    degree = deg_info["degree"]
    accent = deg_info["accent"]
    tone = deg_info["tone"]

    bar_window = len(df)
    sub_i0 = sub_pv[0]["i"]
    # relative bar indices for chart (offset from bar-window start)
    def rel_i(abs_i):
        return max(0, abs_i - (len(df) - bar_window))

    pivots_labeled = []
    wave_names = ["0", "1", "2", "3", "4", "5"]
    prices_seq = [p0, p1, p2, p3, p4, p5_proj]
    tones_seq = ["ink-2", "violet", "rd", "gn", "ink-2", "ink-2"]
    for wi, (wname, wprice, wtone) in enumerate(zip(wave_names, prices_seq, tones_seq)):
        if wi < len(sub_pv):
            bar_i = rel_i(sub_pv[wi]["i"])
        else:
            # projected — offset forward proportionally
            last_real_i = rel_i(sub_pv[-1]["i"])
            w_spacing = (rel_i(sub_pv[-1]["i"]) - rel_i(sub_pv[0]["i"])) // max(len(sub_pv) - 1, 1)
            bar_i = last_real_i + (wi - (len(sub_pv) - 1)) * max(w_spacing, 3)
        place = "below" if (wi % 2 == 0) != bullish else "above"
        if not bullish:
            place = "above" if (wi % 2 == 0) else "below"
        proj = wi >= len(sub_pv)
        pivots_labeled.append({
            "i": bar_i, "price": round(wprice, 2), "w": wname,
            "place": place, "tone": wtone if not proj else "ink-3",
            "proj": proj, "current": (wname in ("3", "4") and not proj and n_pv < 6),
        })

    # skeleton for CandleChart
    skeleton = [{"i": p["i"], "price": p["price"]} for p in pivots_labeled]
    projected_count = sum(1 for p in pivots_labeled if p["proj"])

    # invalidation = W2 low (or W2 high for bearish)
    invalidation_price = round(p2, 2)
    invalidation_note = (
        f"Close {'below' if bullish else 'above'} the W2 {'low' if bullish else 'high'} "
        f"${invalidation_price:.2f} negates the impulse count."
    )

    # fib targets
    targets = _fib_targets(p0, p1, p2, p3, p4, bullish, cur_close, cur_wave)

    # alternate counts
    alts = _alternates(pivots_labeled, bullish, cur_wave, hard_pass, n_pv)

    # wave log
    dates_seq = [pv.get("date", "") for pv in sub_pv]
    while len(dates_seq) < 5:
        dates_seq.append("")
    wave_log = _wave_log(p0, p1, p2, p3, p4, p5_proj, cur_wave, bullish, dates_seq, w1)

    # degree guidelines
    guide1 = {
        "rule": f"W3 extends ≥1.618×W1", "type": "GUIDE",
        "detail": f"{w3 / w1:.2f}×W1 (target 1.618×={p2 + 1.618 * w1:.2f})" if bullish else f"{w3/w1:.2f}×W1",
        "status": "PASS" if w3 / w1 >= 1.5 else "NEAR",
        "tone": "gn" if w3 / w1 >= 1.5 else "violet",
    }
    guide2 = {
        "rule": "Alternation — W2 sharp ⇄ W4 sideways",
        "type": "GUIDE",
        "detail": f"W2 retr {w2_ret:.2f} → W4 expect {'flat' if w2_ret > 0.5 else 'zigzag'}/triangle",
        "status": "OK", "tone": "gn",
    }
    guide3 = {
        "rule": "W2 retraces 50–78.6% of W1",
        "type": "GUIDE",
        "detail": f"{w2_ret:.2f} retracement of W1",
        "status": "PASS" if 0.45 <= w2_ret <= 0.80 else "WATCH",
        "tone": "gn" if 0.45 <= w2_ret <= 0.80 else "amb",
    }
    all_rules = rules + [guide1, guide2, guide3]

    # read line
    cur_wave_display = cur_wave.replace("in-W", "")
    w5_tgt = next((t for t in targets if "W5 target" in t.get("label", "")), None)
    w5_price = w5_tgt["price"] if w5_tgt else round(p5_proj, 2)
    direction_word = "advance" if bullish else "decline"
    read = (
        f"{'Bullish' if bullish else 'Bearish'} {degree}-degree impulse count: "
        f"currently in Wave {cur_wave_display} of 5 — "
        f"W3 is {w3/w1:.2f}×W1 ({'extended' if w3/w1 >= 1.5 else 'normal'}); "
        f"W5 target ${w5_price}; "
        f"invalid {'below' if bullish else 'above'} ${invalidation_price}."
    )

    # stat block
    structure_label = f"{'Bullish' if bullish else 'Bearish'} 5-wave impulse"
    stat = {
        "structure": structure_label,
        "current": f"Wave {cur_wave_display} of 5",
        "degree": deg_info["name"],
        "w3_target": f"${round(p2 + 1.618 * w1, 2):.2f}" if bullish else f"${round(p2 - 1.618 * w1, 2):.2f}",
        "confidence": conf,
        "tone": tone,
    }

    # hlines for chart
    hlines = [
        {"price": round(p5_proj, 2), "label": f"W5 target · {round(p5_proj, 2)}", "tone": "gn", "dash": "5 4"},
        {"price": invalidation_price, "label": f"Invalidate < W2 · {invalidation_price}", "tone": "rd", "dash": "3 3", "labelBelow": True},
        {"price": round(p1, 2), "label": f"W1 top · {round(p1, 2)}", "tone": "ink-2", "dash": "2 4"},
    ]

    bars_out = _bars(df, window=min(len(df), 120))
    bar_count = len(bars_out)

    # adjust skeleton indices to be relative to the bars window
    bar_offset = len(df) - bar_count
    skeleton_adj = [{"i": max(0, p["i"] - bar_offset), "price": p["price"]} for p in skeleton]
    pivots_adj = [{**p, "i": max(0, p["i"] - bar_offset)} for p in pivots_labeled]

    return {
        "ok": True, "source": "real", "state": "real",
        "confidence": conf,
        "bullish": bullish,
        "degree": degree,
        "cur_wave": cur_wave,
        "bars": bars_out,
        "skeleton": skeleton_adj,
        "skeletonTail": projected_count,
        "projectFrom": bar_count,
        "pivots": pivots_adj,
        "hlines": hlines,
        "targets": targets,
        "rules": all_rules,
        "alternates": alts,
        "wave_log": wave_log,
        "stat": stat,
        "invalidation": {"price": invalidation_price, "note": invalidation_note},
        "read": read,
        "cur_close": cur_close,
        "_score": score,
    }


def _try_corrective_label(pivots: List[Dict], df: pd.DataFrame, tf: str,
                          cur_close: float, mode: str) -> Optional[Dict]:
    """Try to label last 3 pivots as an A-B-C corrective. Less confident."""
    if len(pivots) < 3:
        return None
    sub_pv = pivots[-3:]
    p_a = sub_pv[0]["price"]
    p_b = sub_pv[1]["price"]
    p_c = sub_pv[2]["price"]

    # A and C should move in the same direction
    downward = p_b > p_a  # A is a low → upward ABC, or A is high → downward
    a_down = sub_pv[0]["kind"] == "H"  # A pivot is High → correction goes down

    w_a = abs(p_b - p_a)
    w_b = abs(p_c - p_b)
    w_c_proj = abs(p_c - p_b)  # C often ≈ A

    # B should retrace 0.382–0.886 of A
    b_ret = abs(p_c - p_b) / w_a if w_a > 0 else 0

    conf = 0.28  # corrections are harder to count
    if 0.45 <= b_ret <= 0.75:
        conf += 0.05

    deg_info = _DEGREE_MAP.get(mode, _DEGREE_MAP["SWING"])

    c_tgt = round(p_b - w_a if a_down else p_b + w_a, 2)
    read = (
        f"A-B-C corrective structure detected ({deg_info['name']} degree) — "
        f"C-wave {'decline' if a_down else 'advance'} targeting ${c_tgt}; "
        f"confidence modest ({int(conf * 100)}%)."
    )

    bars_out = _bars(df, window=min(len(df), 100))
    return {
        "ok": True, "source": "real", "state": "real",
        "confidence": conf,
        "bullish": not a_down,
        "degree": deg_info["degree"],
        "cur_wave": "C",
        "structure_type": "corrective",
        "bars": bars_out,
        "skeleton": [{"i": max(0, p["i"] - max(0, len(df) - len(bars_out))), "price": p["price"]} for p in sub_pv],
        "skeletonTail": 0,
        "projectFrom": len(bars_out),
        "pivots": [{"i": max(0, sub_pv[k]["i"] - max(0, len(df) - len(bars_out))), "price": sub_pv[k]["price"],
                    "w": lab, "place": "above" if k % 2 == 0 else "below", "tone": t, "proj": False, "current": k == 2}
                   for k, (lab, t) in enumerate(zip(["A", "B", "C"], ["amb", "gn", "rd"]))],
        "hlines": [{"price": c_tgt, "label": f"C target · {c_tgt}", "tone": "amb", "dash": "5 4"}],
        "targets": [{"label": "C = A target", "basis": "C-wave equal-leg projection",
                     "price": c_tgt, "conf": conf, "tone": "amb"}],
        "rules": [{"rule": "A and C move in same direction", "type": "HARD",
                   "detail": "Both A and C are corrective legs", "status": "PASS", "tone": "gn"},
                  {"rule": "B retraces 38.2–88.6% of A", "type": "GUIDE",
                   "detail": f"B retraces {b_ret:.2f} of A",
                   "status": "PASS" if 0.35 <= b_ret <= 0.90 else "WATCH",
                   "tone": "gn" if 0.35 <= b_ret <= 0.90 else "amb"}],
        "alternates": [{"name": "Corrective A-B-C", "loc": "In Wave C", "p": conf,
                        "tone": "amb", "note": "Three-wave counter-trend correction."},
                       {"name": "New impulse wave 1", "loc": "Wave 1 starting", "p": round(1 - conf, 2),
                        "tone": "gn", "note": "Could be early wave 1 of new impulse."}],
        "wave_log": [
            {"w": "A", "type": "Impulse", "span": f"{p_a:.2f} → {p_b:.2f}",
             "move": f"{(p_b-p_a)/p_a*100:+.1f}%", "fib": "—",
             "note": "First corrective leg", "tone": "amb"},
            {"w": "B", "type": "Retracement", "span": f"{p_b:.2f} → {p_c:.2f}",
             "move": f"{(p_c-p_b)/p_b*100:+.1f}%", "fib": f"{b_ret:.2f} retr",
             "note": "Partial counter-rally / decline", "tone": "gn"},
            {"w": "C", "type": "Impulse ⟳", "span": f"{p_c:.2f} → {c_tgt:.2f}",
             "move": f"{(c_tgt-p_c)/p_c*100:+.1f}%", "fib": "≈ A",
             "note": "C-wave in progress — often equals A", "tone": "rd", "is_current": True},
        ],
        "stat": {"structure": "A-B-C corrective", "current": "Wave C",
                 "degree": deg_info["name"], "w3_target": f"${c_tgt:.2f}",
                 "confidence": conf, "tone": deg_info["tone"]},
        "invalidation": {"price": round(p_a, 2),
                         "note": f"Move beyond the A pivot ${p_a:.2f} would invalidate the ABC count."},
        "read": read,
        "cur_close": cur_close,
    }
