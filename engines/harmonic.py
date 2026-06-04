"""engines/harmonic.py — XABCD harmonic pattern detector for the BullVeda
Patterns lens.

Mechanism (principle 2): harmonic patterns are precise Fibonacci-ratio price
structures (Gartley, Bat, Butterfly, Crab, Shark, Cypher); completion at the
PRZ (Potential Reversal Zone) concentrates reversal orders because multiple
independent Fib projections overlap at the same price level, making the zone
statistically significant rather than random noise.

Honesty (principle 4): returns state="none" when no 5-pivot XABCD sequence
matches any canonical ratio set within tolerance. Never forces a pattern.

Mode-aware: daily bars (SWING) / weekly (POSITION) / monthly (INVESTMENT).
ZigZag pivot window scales with timeframe so the "dominant 5-pivot sequence"
is always meaningful.

CLI:
    python3 -m engines.harmonic AAPL SWING
    python3 -m engines.harmonic NVDA POSITION
    python3 -m engines.harmonic WMB INVESTMENT
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "harmonic"
LABEL = "Harmonic"

# ── Canonical ratio sets ──────────────────────────────────────────────────────
# Each entry: (pattern_name, bull/bear, AB/XA, BC/AB_lo, BC/AB_hi, CD/BC_lo, CD/BC_hi, AD/XA, tolerance_multiplier)
# Sources: Carney (2004), Pesavento & Shapiro
#
# Keys:
#   xab  = AB retracement of XA (exact or small range)
#   abc_lo/hi = BC retracement of AB (range)
#   bcd_lo/hi = CD extension of BC (range)
#   axd  = AD retracement of XA (the defining ratio)
#
_PATTERNS = [
    # name          xab      abc_lo  abc_hi  bcd_lo  bcd_hi  axd     tol_mult
    ("Gartley",     0.618,   0.382,  0.886,  1.272,  1.618,  0.786,  1.0),
    ("Bat",         0.382,   0.382,  0.886,  1.618,  2.618,  0.886,  1.0),
    ("Bat",         0.500,   0.382,  0.886,  1.618,  2.618,  0.886,  1.0),
    ("Butterfly",   0.786,   0.382,  0.886,  1.618,  2.618,  1.272,  1.0),
    ("Butterfly",   0.786,   0.382,  0.886,  1.618,  2.618,  1.618,  1.0),
    ("Crab",        0.382,   0.382,  0.886,  2.618,  3.618,  1.618,  1.0),
    ("Crab",        0.618,   0.382,  0.886,  2.618,  3.618,  1.618,  1.0),
    ("Shark",       0.446,   1.130,  1.130,  1.618,  2.236,  0.886,  1.2),  # CD is BC ext
    ("Shark",       0.618,   1.130,  1.130,  1.618,  2.236,  1.130,  1.2),
    ("Cypher",      0.382,   1.272,  1.414,  0.786,  0.786,  0.786,  1.2),
    ("Cypher",      0.618,   1.272,  1.414,  0.786,  0.786,  0.786,  1.2),
]

# Base tolerance (fraction) — pattern passes when ratio_error / ideal < BASE_TOL
_BASE_TOL = 0.065   # 6.5%

# ── timeframe window config ───────────────────────────────────────────────────
_TFW = {
    "Daily":   {"lookback": 200, "pivot_n": 5,  "bars_out": 100, "min_leg_bars": 3},
    "Weekly":  {"lookback": 130, "pivot_n": 3,  "bars_out": 80,  "min_leg_bars": 2},
    "Monthly": {"lookback": 80,  "pivot_n": 2,  "bars_out": 60,  "min_leg_bars": 1},
}


def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── bar payload ───────────────────────────────────────────────────────────────
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


# ── ZigZag pivot extraction (vectorised) ─────────────────────────────────────
def _zigzag_pivots(df: pd.DataFrame, n: int) -> List[Tuple[int, float, str]]:
    """Return alternating swing highs/lows as [(abs_bar_idx, price, 'H'|'L'), …].

    Uses a fractal pivot rule: a High pivot at i when df['High'][i] equals the
    rolling max over a 2n+1 window centred on i; same for lows. Then builds an
    alternating ZigZag by always keeping the higher of consecutive highs or the
    lower of consecutive lows.
    """
    highs = df["High"]
    lows  = df["Low"]
    roll_max = highs.rolling(2 * n + 1, center=True, min_periods=n + 1).max()
    roll_min = lows.rolling(2 * n + 1, center=True, min_periods=n + 1).min()
    ph = (highs == roll_max).values
    pl = (lows  == roll_min).values

    # Collect raw pivots (may have consecutive same-direction)
    raw: List[Tuple[int, float, str]] = []
    for i in range(len(df)):
        if ph[i] and pl[i]:
            # bar is both — use whichever deviation from centre is larger
            h, l = float(df["High"].iloc[i]), float(df["Low"].iloc[i])
            if h - float(df["Close"].iloc[i]) >= float(df["Close"].iloc[i]) - l:
                raw.append((i, h, "H"))
            else:
                raw.append((i, l, "L"))
        elif ph[i]:
            raw.append((i, float(df["High"].iloc[i]), "H"))
        elif pl[i]:
            raw.append((i, float(df["Low"].iloc[i]), "L"))

    if not raw:
        return []

    # Enforce strict alternation: keep best (highest H / lowest L) between consecutive sames
    zz: List[Tuple[int, float, str]] = [raw[0]]
    for pt in raw[1:]:
        prev = zz[-1]
        if pt[2] == prev[2]:
            # same direction — keep the more extreme
            if (pt[2] == "H" and pt[1] > prev[1]) or (pt[2] == "L" and pt[1] < prev[1]):
                zz[-1] = pt
        else:
            zz.append(pt)

    return zz


# ── ratio helpers ─────────────────────────────────────────────────────────────
def _ratio(a: float, b: float) -> Optional[float]:
    """Safe ratio a / b. None when b ≈ 0."""
    if abs(b) < 1e-9:
        return None
    return a / b


def _pct_err(actual: float, ideal: float) -> float:
    """Fractional error |actual - ideal| / ideal."""
    if ideal == 0:
        return 9999.0
    return abs(actual - ideal) / abs(ideal)


# ── test one XABCD sequence against all canonical patterns ────────────────────
def _test_sequence(
    x_price: float, a_price: float, b_price: float,
    c_price: float, d_price: float,
    tol: float,
) -> Optional[Dict[str, Any]]:
    """Return the best-matching pattern dict or None."""

    xa = a_price - x_price          # XA leg (signed)
    ab = b_price - a_price          # AB leg (signed)
    bc = c_price - b_price          # BC leg (signed)
    cd = d_price - c_price          # CD leg (signed)

    if abs(xa) < 1e-9:
        return None

    # Only valid if XA and AB have opposite signs (B retraces XA), etc.
    if (ab * xa) >= 0:   # AB must retrace XA → opposite sign
        return None
    if (bc * ab) >= 0:   # BC must retrace AB → opposite sign
        return None
    if (cd * bc) >= 0:   # CD must retrace/extend BC → opposite sign
        return None

    xab_ratio = abs(ab / xa)
    abc_ratio = abs(bc / ab) if abs(ab) > 1e-9 else None
    bcd_ratio = abs(cd / bc) if abs(bc) > 1e-9 else None
    axd_ratio = abs((d_price - x_price) / xa) if abs(xa) > 1e-9 else None

    if None in (abc_ratio, bcd_ratio, axd_ratio):
        return None

    best_match = None
    best_error = 9999.0

    for (name, xab_ideal, abc_lo, abc_hi, bcd_lo, bcd_hi, axd_ideal, tol_mult) in _PATTERNS:
        effective_tol = tol * tol_mult

        # XAB ratio check — moderately strict: pattern signature leg
        xab_err = _pct_err(xab_ratio, xab_ideal)
        if xab_err > effective_tol * 1.2:
            continue

        # ABC retracement check (range) — allow tolerance to expand the range bounds
        abc_mid = (abc_lo + abc_hi) / 2
        abc_half = (abc_hi - abc_lo) / 2 + effective_tol * abc_mid
        abc_err = max(0.0, abs(abc_ratio - abc_mid) - abc_half) / abc_mid if abc_mid > 0 else 9999

        # BCD extension check (range) — same expansion
        bcd_mid = (bcd_lo + bcd_hi) / 2
        bcd_half = (bcd_hi - bcd_lo) / 2 + effective_tol * bcd_mid
        bcd_err = max(0.0, abs(bcd_ratio - bcd_mid) - bcd_half) / bcd_mid if bcd_mid > 0 else 9999

        # AXD — the defining D completion ratio; allow moderate slack
        axd_err = _pct_err(axd_ratio, axd_ideal)

        total_err = xab_err + abc_err + bcd_err + axd_err
        # Each individual leg must not exceed 1.5× the effective tolerance
        if abc_err > effective_tol * 1.5 or bcd_err > effective_tol * 1.5 or axd_err > effective_tol * 1.2:
            continue

        if total_err < best_error:
            best_error = total_err
            best_match = {
                "name":     name,
                "xab_ideal": xab_ideal,
                "abc_lo":   abc_lo,
                "abc_hi":   abc_hi,
                "bcd_lo":   bcd_lo,
                "bcd_hi":   bcd_hi,
                "axd_ideal": axd_ideal,
                "xab_actual": round(xab_ratio, 4),
                "abc_actual": round(abc_ratio, 4),
                "bcd_actual": round(bcd_ratio, 4),
                "axd_actual": round(axd_ratio, 4),
                "xab_err":  round(xab_err, 4),
                "abc_err":  round(abc_err, 4),
                "bcd_err":  round(bcd_err, 4),
                "axd_err":  round(axd_err, 4),
                "total_err": round(total_err, 4),
            }

    return best_match


# ── scan all 5-pivot windows in the ZigZag ───────────────────────────────────
def _find_best_harmonic(
    pivots: List[Tuple[int, float, str]],
    df: pd.DataFrame,
    tol: float,
    min_leg_bars: int,
) -> Optional[Dict[str, Any]]:
    """Scan every consecutive 5-pivot window. Return the best-matching pattern."""
    n = len(pivots)
    if n < 5:
        return None

    best: Optional[Dict[str, Any]] = None
    best_err = 9999.0
    best_recency = -1

    # scan from the most recent back, preferring recent patterns
    for end in range(n - 1, 3, -1):
        x_pt, a_pt, b_pt, c_pt, d_pt = pivots[end - 4], pivots[end - 3], pivots[end - 2], pivots[end - 1], pivots[end]

        # Basic validity: legs must have minimum bar span
        if any(abs(pivots[i][0] - pivots[i - 1][0]) < min_leg_bars
               for i in [end - 3, end - 2, end - 1, end]):
            continue

        match = _test_sequence(x_pt[1], a_pt[1], b_pt[1], c_pt[1], d_pt[1], tol)
        if match is None:
            continue

        # Prefer: lower error, then more recent (larger d_pt bar index)
        recency = d_pt[0]
        if match["total_err"] < best_err or (match["total_err"] == best_err and recency > best_recency):
            best_err = match["total_err"]
            best_recency = recency
            best = {
                "pattern": match,
                "pivots": {
                    "X": x_pt, "A": a_pt, "B": b_pt, "C": c_pt, "D": d_pt,
                },
            }

    return best


# ── PRZ calculation ───────────────────────────────────────────────────────────
def _compute_prz(hit: Dict[str, Any]) -> Tuple[float, float]:
    """Return (prz_lo, prz_hi) based on the AD ratio and the BC extension at D."""
    pts = hit["pivots"]
    x, a, b, c, d = pts["X"][1], pts["A"][1], pts["B"][1], pts["C"][1], pts["D"][1]

    xa = a - x
    bc = c - b

    pat = hit["pattern"]
    # D from XA perspective
    d_xa = x + pat["axd_ideal"] * xa

    # D from BC extension perspective (use midpoint of bcd range)
    bcd_mid = (pat["bcd_lo"] + pat["bcd_hi"]) / 2
    d_bc = b + bcd_mid * (-bc)  # BC was already signed, CD reverses

    # Also actual D
    lo = min(d, d_xa, d_bc)
    hi = max(d, d_xa, d_bc)

    # Give minimum width of 0.5% to avoid degenerate bands
    mid = (lo + hi) / 2
    half = max((hi - lo) / 2, mid * 0.005)
    return round(mid - half, 2), round(mid + half, 2)


# ── confidence from ratio errors ──────────────────────────────────────────────
def _compute_confidence(hit: Dict[str, Any]) -> float:
    pat = hit["pattern"]
    # Start at 0.90; penalise by error magnitude (each 1% error → −0.04 conf)
    total_penalty = pat["total_err"] * 4.0
    conf = max(0.20, min(0.92, 0.90 - total_penalty))
    return round(conf, 2)


# ── targets from the pattern ──────────────────────────────────────────────────
def _compute_targets(
    hit: Dict[str, Any], cur_close: float, d_price: float, a_price: float
) -> List[Dict[str, Any]]:
    """Standard harmonic targets: 0.382 and 0.618 of the AD leg from D, then A-retest."""
    pts = hit["pivots"]
    d = pts["D"][1]
    a = pts["A"][1]
    x = pts["X"][1]
    ad = a - d   # AD signed distance

    t1 = round(d + 0.382 * ad, 2)
    t2 = round(d + 0.618 * ad, 2)
    t3 = round(float(a), 2)    # A retest

    targets = []
    for lbl, px, basis, conf, tone in [
        ("T1 · 0.382 AD", t1, "0.382 retracement of the AD leg from D", 0.72, "gn"),
        ("T2 · 0.618 AD", t2, "0.618 retracement of the AD leg from D", 0.55, "gn"),
        ("T3 · A retest",  t3, "return to point A (full AD completion)", 0.40, "amb"),
    ]:
        rr_pct = (px - cur_close) / abs(cur_close) * 100 if cur_close > 0 else 0
        state_txt = "projected"
        if ad > 0:  # bullish — D is low
            if cur_close >= px:
                state_txt = "hit ✓"
        else:       # bearish — D is high
            if cur_close <= px:
                state_txt = "hit ✓"

        targets.append({
            "label":  lbl,
            "basis":  basis,
            "price":  f"{px:.2f}",
            "rr":     state_txt,
            "conf":   conf,
            "tone":   tone if state_txt == "projected" else "gn",
        })

    return targets


# ── assemble bar-window chart annotations ────────────────────────────────────
def _chart_annotations(
    hit: Dict[str, Any],
    df: pd.DataFrame,
    window_start: int,
    prz_lo: float,
    prz_hi: float,
    targets: List[Dict[str, Any]],
    inv_price: float,
    tf: str,
    is_bull: bool,
) -> Tuple[List, List, List, List]:
    """Returns (skeleton, zones, markers, hlines)."""
    pts = hit["pivots"]
    label_order = ["X", "A", "B", "C", "D"]
    tone_map = {"D": "gn", **{k: "violet" for k in ["X", "A", "B", "C"]}}
    place_map: Dict[str, str] = {}

    skeleton = []
    markers  = []
    for lbl in label_order:
        abs_i, price, _ = pts[lbl]
        bar_i = int(abs_i - window_start)
        if bar_i < 0:
            bar_i = 0
        skeleton.append({"i": bar_i, "price": round(float(price), 2)})

        # place: X is below in bull (X is the low), A above, then alternating
        if is_bull:
            place = "below" if lbl in ("X", "B", "D") else "above"
        else:
            place = "above" if lbl in ("X", "B", "D") else "below"

        markers.append({
            "i": bar_i, "price": round(float(price), 2),
            "label": lbl, "tone": tone_map.get(lbl, "violet"), "place": place,
        })

    zones = [{"lo": prz_lo, "hi": prz_hi, "tone": "gn" if is_bull else "rd",
              "label": f"PRZ {prz_lo:.2f}–{prz_hi:.2f}"}]

    hlines = []
    if targets:
        t1 = targets[0]
        hlines.append({"price": float(t1["price"]), "label": t1["label"],
                       "tone": "gn", "dash": "5 4"})
    if len(targets) >= 2:
        t2 = targets[1]
        hlines.append({"price": float(t2["price"]), "label": t2["label"],
                       "tone": "gn", "dash": "5 4"})
    hlines.append({"price": inv_price, "label": f"Invalidate < X · {inv_price:.2f}" if is_bull else f"Invalidate > X · {inv_price:.2f}",
                   "tone": "rd", "dash": "3 3", "labelBelow": not is_bull})

    return skeleton, zones, markers, hlines


# ── point log (like WY_LOG / HM_LOG) ─────────────────────────────────────────
def _build_points(
    hit: Dict[str, Any], df: pd.DataFrame,
    window_start: int, tf: str, is_bull: bool,
) -> List[Dict[str, Any]]:
    pts = hit["pivots"]
    pat = hit["pattern"]

    role_map = {
        "X": "Origin" + (" low" if is_bull else " high"),
        "A": "Impulse " + ("high" if is_bull else "low"),
        "B": "0.618 retracement",
        "C": "Reaction " + ("high" if is_bull else "low"),
        "D": "PRZ completion",
    }
    note_map = {
        "X": "Pattern anchor — defines the XA leg",
        "A": f"XA leg drives the structure ({abs(pts['A'][1] - pts['X'][1]):.2f}pt)",
        "B": f"{pat['xab_actual']:.3f} XA retracement — {'✓ within' if pat['xab_err'] < _BASE_TOL else '⚠ outside'} ideal",
        "C": f"{pat['abc_actual']:.3f} AB retracement — range {pat['abc_lo']:.3f}–{pat['abc_hi']:.3f}",
        "D": f"{pat['axd_actual']:.3f} XA completion — {'✓ confirmed' if pat['axd_err'] < _BASE_TOL else '≈ near'} {pat['axd_ideal']:.3f} ideal",
    }
    tone_map = {"D": "gn", **{k: "violet" for k in ["X", "A", "B", "C"]}}

    out = []
    for lbl in ["X", "A", "B", "C", "D"]:
        abs_i, price, _ = pts[lbl]
        bar_i = int(abs_i - window_start)
        if bar_i < 0:
            bar_i = 0
        date_str = fmt_date(df.index[int(abs_i)], tf) if int(abs_i) < len(df) else ""
        out.append({
            "p":     lbl,
            "i":     bar_i,
            "price": round(float(price), 2),
            "role":  role_map.get(lbl, lbl),
            "date":  date_str,
            "note":  note_map.get(lbl, ""),
            "tone":  tone_map.get(lbl, "violet"),
        })

    return out


# ── ratio validation table ────────────────────────────────────────────────────
def _build_ratios(hit: Dict[str, Any]) -> List[Dict[str, Any]]:
    pat = hit["pattern"]

    def status(err: float) -> Tuple[str, str]:
        if err < 0.01:
            return "EXACT", "violet"
        if err < _BASE_TOL:
            return "PASS", "gn"
        if err < _BASE_TOL * 1.5:
            return "NEAR", "amb"
        return "WIDE", "rd"

    rows = [
        {
            "leg":    "AB / XA",
            "actual": f"{pat['xab_actual']:.3f}",
            "ideal":  f"{pat['xab_ideal']:.3f}",
            "err":    pat["xab_err"],
        },
        {
            "leg":    "BC / AB",
            "actual": f"{pat['abc_actual']:.3f}",
            "ideal":  f"{pat['abc_lo']:.3f} – {pat['abc_hi']:.3f}",
            "err":    pat["abc_err"],
        },
        {
            "leg":    "CD / BC",
            "actual": f"{pat['bcd_actual']:.3f}",
            "ideal":  f"{pat['bcd_lo']:.3f} – {pat['bcd_hi']:.3f}",
            "err":    pat["bcd_err"],
        },
        {
            "leg":    "AD / XA",
            "actual": f"{pat['axd_actual']:.3f}",
            "ideal":  f"{pat['axd_ideal']:.3f}",
            "err":    pat["axd_err"],
        },
    ]

    out = []
    for r in rows:
        s, t = status(r["err"])
        out.append({"leg": r["leg"], "actual": r["actual"], "ideal": r["ideal"],
                    "status": s, "tone": t})
    return out


# ── stat block ────────────────────────────────────────────────────────────────
def _build_stat(
    hit: Dict[str, Any], prz_lo: float, prz_hi: float,
    is_bull: bool, conf: float, targets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    pat = hit["pattern"]
    pts = hit["pivots"]
    tone = "gn" if is_bull else "rd"
    direction = "Bullish" if is_bull else "Bearish"
    d_price = pts["D"][1]
    cur_prz = f"{prz_lo:.2f} – {prz_hi:.2f}"
    next_t = targets[0]["price"] if targets else "—"

    # Completion status: is D confirmed (price has moved away from PRZ)?
    return {
        "pattern":    f"{direction} {pat['name']}",
        "completion": "D confirmed",
        "prz":        cur_prz,
        "next_target": f"${next_t}",
        "confidence": conf,
        "tone":       tone,
    }


# ── plain-English read ────────────────────────────────────────────────────────
def _build_read(hit: Dict[str, Any], prz_lo: float, prz_hi: float,
                inv_price: float, is_bull: bool, targets: List, tf: str) -> str:
    pat = hit["pattern"]
    direction = "Bullish" if is_bull else "Bearish"
    t1 = targets[0]["price"] if targets else "—"
    t3 = targets[-1]["price"] if targets else "—"
    return (
        f"{tf} {direction} {pat['name']}: D completed at PRZ ${prz_lo:.2f}–${prz_hi:.2f} "
        f"({pat['axd_ideal']:.3f} XA, {pat['axd_actual']:.3f} actual). "
        f"Targets ${t1} → ${t3}; void {'below' if is_bull else 'above'} X ${inv_price:.2f}."
    )


# ── main detect() ─────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """XABCD harmonic detector. Returns full payload for HarmonicView. Never raises."""
    tf = meta.get("tf", "Daily")
    w  = _tfw(tf)
    base = {"ok": True, "source": "real", "state": "none",
            "cur_close": None, "message": ""}

    # ── guard ────────────────────────────────────────────────────────────────
    if df is None or len(df) < 30:
        return {**base, "message": f"Insufficient {tf.lower()} history for a harmonic read."}

    cur_close = round(float(df["Close"].iloc[-1]), 2)
    base["cur_close"] = cur_close

    # ── ZigZag on the lookback window ────────────────────────────────────────
    lookback = min(w["lookback"], len(df))
    sub = df.iloc[-lookback:].copy()
    offset = len(df) - lookback   # absolute bar index of sub[0]

    pivots = _zigzag_pivots(sub, w["pivot_n"])

    # Translate local indices to absolute df indices
    pivots_abs = [(int(offset + i), price, kind) for (i, price, kind) in pivots]

    if len(pivots_abs) < 5:
        return {**base,
                "message": f"Only {len(pivots_abs)} ZigZag pivots in the last {lookback} {tf.lower()} bars — need ≥5 for XABCD."}

    # ── scan for harmonic pattern ─────────────────────────────────────────────
    hit = _find_best_harmonic(pivots_abs, df, _BASE_TOL, w["min_leg_bars"])
    if hit is None:
        return {**base,
                "message": f"No XABCD harmonic pattern (Gartley/Bat/Butterfly/Crab/Shark/Cypher) "
                           f"within {int(_BASE_TOL*100)}% ratio tolerance on the {tf.lower()} chart."}

    # ── pattern found — build output ──────────────────────────────────────────
    pts     = hit["pivots"]
    x_price = float(pts["X"][1])
    a_price = float(pts["A"][1])
    d_price = float(pts["D"][1])

    # bullish: XA goes up (a > x), D is a low
    is_bull = bool(a_price > x_price)

    prz_lo, prz_hi = _compute_prz(hit)
    conf           = _compute_confidence(hit)
    targets        = _compute_targets(hit, cur_close, d_price, a_price)
    inv_price      = round(float(x_price) * (0.995 if is_bull else 1.005), 2)

    # Windowed bars (last bars_out)
    bars_n       = min(w["bars_out"], len(df))
    window_start = len(df) - bars_n
    bars         = _bar_payload(df.iloc[-bars_n:])

    skeleton, zones, markers, hlines = _chart_annotations(
        hit, df, window_start, prz_lo, prz_hi, targets, inv_price, tf, is_bull
    )

    points = _build_points(hit, df, window_start, tf, is_bull)
    ratios = _build_ratios(hit)
    stat   = _build_stat(hit, prz_lo, prz_hi, is_bull, conf, targets)
    read   = _build_read(hit, prz_lo, prz_hi, inv_price, is_bull, targets, tf)

    pat = hit["pattern"]

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "confidence": conf,
        "bars":       bars,
        # chart annotations
        "skeleton":   skeleton,
        "zones":      zones,
        "markers":    markers,
        "hlines":     hlines,
        # structured data
        "points":     points,     # XABCD point log (for HarmonicLog)
        "ratios":     ratios,     # ratio validation table (for HarmonicRatios)
        "targets":    targets,    # target rows (for HarmonicTargets)
        "stat":       stat,       # header strip (for HarmonicStat)
        "pattern": {
            "name":       pat["name"],
            "bull":       is_bull,
            "tone":       "gn" if is_bull else "rd",
            "xab":        pat["xab_actual"],
            "abc":        pat["abc_actual"],
            "bcd":        pat["bcd_actual"],
            "axd":        pat["axd_actual"],
            "total_err":  pat["total_err"],
        },
        "prz":        {"lo": prz_lo, "hi": prz_hi},
        "invalidation": {"price": inv_price,
                         "note": (f"A close {'below' if is_bull else 'above'} X ${x_price:.2f} "
                                  f"voids the {pat['name']} — structure failed.")},
        "read":       read,
        "cur_close":  cur_close,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":   # pragma: no cover
    import json
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    mode = sys.argv[2] if len(sys.argv) > 2 else "SWING"
    from pattern_data import get_bars
    from pattern_engines import detect as pdetect
    out = pdetect("harmonic", sym, mode)
    print(f"\n=== Harmonic · {sym} · {mode} ({out.get('meta', {}).get('tf')}) ===")
    print(f"state={out.get('state')} conf={out.get('confidence')} "
          f"bars={len(out.get('bars', []))} pattern={out.get('pattern', {}).get('name')}")
    if out.get("message"):
        print("message:", out["message"])
    if out.get("points"):
        for p in out["points"]:
            print(f"  {p['p']}  i={p['i']:>3}  ${p['price']:<9}  {p['date']:<8}  {p['role']}")
    if out.get("ratios"):
        for r in out["ratios"]:
            print(f"  {r['leg']:<12}  actual={r['actual']:<8}  ideal={r['ideal']:<12}  {r['status']}")
    if "--json" in sys.argv:
        print(json.dumps({k: v for k, v in out.items() if k != "bars"}, indent=2, default=str))
