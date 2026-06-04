"""engines/volprofile.py — Volume Profile detector for the BullVeda Patterns lens.

Mechanism (principle 2): price is an auction; the market spends most time at
prices both sides agree on (HVN = fair value = magnet / support). Low-volume
nodes are rejected prices — the auction crosses them quickly (LVN = fast-travel
zone). The POC is the single fairest price in the window; the Value Area (70%
of volume) brackets the accepted range. Price rotating between VA edges is the
primary trade trigger.

Mode-aware: SWING=daily (~300d), POSITION=weekly (~3yr), INVEST=monthly (~12yr).
Window is scaled so the profile covers a meaningful auction period per horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional

from pattern_data import fmt_date, get_bars, mode_meta, norm_mode

NAME  = "volprofile"
LABEL = "Volume Profile"

# ── timeframe-relative windows (bars) ────────────────────────────────────────
_TFW = {
    "Daily":   {"win": 90,  "min": 30,  "bins": 50},
    "Weekly":  {"win": 78,  "min": 24,  "bins": 45},
    "Monthly": {"win": 60,  "min": 18,  "bins": 40},
}

def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── core volume-by-price histogram ───────────────────────────────────────────
def _build_profile(df: pd.DataFrame, n_bins: int = 50) -> Optional[Dict[str, Any]]:
    """
    Distribute each bar's volume across its hi–lo range (uniform spread).
    Returns dict with profile[], poc, vah, val, shape.
    """
    lo_all = float(df["Low"].min())
    hi_all = float(df["High"].max())
    if hi_all <= lo_all:
        return None

    # fixed price grid
    bin_size = (hi_all - lo_all) / n_bins
    edges = np.linspace(lo_all, hi_all, n_bins + 1)
    vol_by_bin = np.zeros(n_bins)

    # vectorised: for each bar distribute its volume uniformly across overlapping bins
    bars_lo = df["Low"].values
    bars_hi = df["High"].values
    bars_vol = df["Volume"].values

    for i in range(len(df)):
        lo_i = bars_lo[i]
        hi_i = bars_hi[i]
        vol_i = bars_vol[i]
        if hi_i <= lo_i or vol_i <= 0:
            continue
        bar_range = hi_i - lo_i
        # bins that overlap [lo_i, hi_i]
        b_lo = max(0, int((lo_i - lo_all) / bin_size))
        b_hi = min(n_bins - 1, int((hi_i - lo_all) / bin_size))
        for b in range(b_lo, b_hi + 1):
            edge_lo = edges[b]
            edge_hi = edges[b + 1]
            overlap = min(hi_i, edge_hi) - max(lo_i, edge_lo)
            if overlap > 0:
                vol_by_bin[b] += vol_i * overlap / bar_range

    if vol_by_bin.max() == 0:
        return None

    bin_prices = 0.5 * (edges[:-1] + edges[1:])  # mid-price of each bin
    poc_idx = int(np.argmax(vol_by_bin))
    poc_price = float(bin_prices[poc_idx])
    max_vol = float(vol_by_bin[poc_idx])

    # value area: expand outward from POC until 70% of total volume captured
    total_vol = float(vol_by_bin.sum())
    va_lo_idx = poc_idx
    va_hi_idx = poc_idx
    acc = vol_by_bin[poc_idx]
    while acc < total_vol * 0.70:
        below = vol_by_bin[va_lo_idx - 1] if va_lo_idx > 0 else -1
        above = vol_by_bin[va_hi_idx + 1] if va_hi_idx < n_bins - 1 else -1
        if below < 0 and above < 0:
            break
        if above >= below:
            va_hi_idx += 1
            acc += vol_by_bin[va_hi_idx]
        else:
            va_lo_idx -= 1
            acc += vol_by_bin[va_lo_idx]

    vah = float(bin_prices[va_hi_idx])
    val = float(bin_prices[va_lo_idx])

    # HVN / LVN classification (relative to POC)
    hvn_thresh = max_vol * 0.42
    lvn_thresh = max_vol * 0.30

    profile: List[Dict] = []
    for b in range(n_bins):
        p   = float(bin_prices[b])
        v   = float(vol_by_bin[b])
        poc = (b == poc_idx)
        hvn = False
        lvn = False
        if not poc and 0 < b < n_bins - 1:
            if v > vol_by_bin[b - 1] and v > vol_by_bin[b + 1] and v > hvn_thresh:
                hvn = True
            elif v < vol_by_bin[b - 1] and v < vol_by_bin[b + 1] and v < lvn_thresh:
                lvn = True
        profile.append({
            "price": round(p, 2),
            "vol":   round(v, 2),
            "poc":   poc,
            "hvn":   hvn,
            "lvn":   lvn,
        })

    # profile shape heuristic
    top_half = vol_by_bin[n_bins // 2:]
    bot_half  = vol_by_bin[:n_bins // 2]
    top_mass = top_half.sum()
    bot_mass  = bot_half.sum()
    skew = (top_mass - bot_mass) / max(total_vol, 1)
    if abs(skew) < 0.10:
        shape = "D · balanced"
    elif skew > 0:
        shape = "P · upward skew"
    else:
        shape = "b · downward skew"

    return {
        "profile": profile,
        "poc":     round(poc_price, 2),
        "vah":     round(vah, 2),
        "val":     round(val, 2),
        "max_vol": max_vol,
        "total_vol": total_vol,
        "shape":   shape,
        "va_lo_idx": va_lo_idx,
        "va_hi_idx": va_hi_idx,
    }


# ── bar payload (windowed, capped) ────────────────────────────────────────────
def _bar_payload(df: pd.DataFrame) -> List[Dict]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(float(r["rvol"]) if np.isfinite(r.get("rvol", 1.0)) else 1.0, 2),
        })
    return out


# ── auction nodes summary (for the VpNodes table) ────────────────────────────
def _extract_nodes(profile: List[Dict], cur_close: float) -> List[Dict]:
    nodes = []
    poc_added = False
    for p in profile:
        if p["poc"]:
            nodes.append({
                "px":   f"{p['price']:.2f}",
                "type": "HVN · POC",
                "role": "Fair value · magnet / acceptance zone",
                "tone": "copper",
                "price_val": p["price"],
            })
            poc_added = True
        elif p["hvn"]:
            nodes.append({
                "px":   f"{p['price']:.2f}",
                "type": "HVN",
                "role": "Secondary acceptance · support/resistance shelf",
                "tone": "cy",
                "price_val": p["price"],
            })
        elif p["lvn"]:
            side = "above VA" if p["price"] > cur_close else "below VA"
            nodes.append({
                "px":   f"{p['price']:.2f}",
                "type": "LVN",
                "role": f"Rejection gap · price travels fast through ({side})",
                "tone": "ink-2",
                "price_val": p["price"],
            })
    # sort by price descending (highest to lowest for the table)
    nodes.sort(key=lambda n: n["price_val"], reverse=True)
    return nodes


# ── auction targets (3 scenarios) ────────────────────────────────────────────
def _compute_targets(poc: float, vah: float, val: float, cur_close: float,
                     profile: List[Dict], confidence: float) -> List[Dict]:
    va_height = vah - val
    lvns_above = sorted([p["price"] for p in profile if p.get("lvn") and p["price"] > vah])
    lvns_below = sorted([p["price"] for p in profile if p.get("lvn") and p["price"] < val], reverse=True)

    targets = []

    if cur_close > vah:
        # acceptance above VA — look for LVN above or project VA-height above
        lvn_above = lvns_above[0] if lvns_above else None
        t1 = lvn_above if lvn_above else round(vah + va_height * 0.5, 2)
        t2 = round(vah + va_height, 2)
        targets.append({"scenario": "Accept > VAH", "basis": "LVN thin zone offers no resistance",
                         "target": f"${t1:.2f}", "conf": round(min(0.70, confidence), 2), "tone": "gn",
                         "scenario_tone": "up"})
        targets.append({"scenario": "VA extension", "basis": "1× value-area height above VAH",
                         "target": f"${t2:.2f}", "conf": round(min(0.50, confidence * 0.80), 2), "tone": "gn",
                         "scenario_tone": "up"})
        targets.append({"scenario": "Reject at VAH", "basis": "Rotation back to POC magnet",
                         "target": f"${poc:.2f}", "conf": round(min(0.35, confidence * 0.55), 2), "tone": "amb",
                         "scenario_tone": "warn"})
        invalidation = (f"Acceptance (2+ closes) back below VAH ${vah:.2f} shifts the auction lower "
                        f"— value migrating down.")
    elif cur_close < val:
        # acceptance below VA — downside scenarios
        lvn_below = lvns_below[0] if lvns_below else None
        t1 = lvn_below if lvn_below else round(val - va_height * 0.5, 2)
        t2 = round(val - va_height, 2)
        targets.append({"scenario": "Accept < VAL", "basis": "LVN thin zone offers no support",
                         "target": f"${t1:.2f}", "conf": round(min(0.70, confidence), 2), "tone": "rd",
                         "scenario_tone": "dn"})
        targets.append({"scenario": "VA extension down", "basis": "1× value-area height below VAL",
                         "target": f"${t2:.2f}", "conf": round(min(0.50, confidence * 0.80), 2), "tone": "rd",
                         "scenario_tone": "dn"})
        targets.append({"scenario": "Reject at VAL", "basis": "Rotation back to POC magnet",
                         "target": f"${poc:.2f}", "conf": round(min(0.35, confidence * 0.55), 2), "tone": "amb",
                         "scenario_tone": "warn"})
        invalidation = (f"Acceptance (2+ closes) back above VAL ${val:.2f} shifts the auction higher "
                        f"— value migrating up.")
    else:
        # inside value area — rotation plays
        t_up   = round(vah + (lvns_above[0] - vah if lvns_above else va_height * 0.5), 2)
        t_down = round(val - (val - lvns_below[0] if lvns_below else va_height * 0.5), 2)
        targets.append({"scenario": "Rotate to VAH", "basis": "Upper VA edge buy-side exhaustion",
                         "target": f"${vah:.2f}", "conf": round(min(0.60, confidence * 0.90), 2), "tone": "gn",
                         "scenario_tone": "up"})
        targets.append({"scenario": "Rotate to VAL", "basis": "Lower VA edge sell-side exhaustion",
                         "target": f"${val:.2f}", "conf": round(min(0.60, confidence * 0.90), 2), "tone": "amb",
                         "scenario_tone": "warn"})
        targets.append({"scenario": "Break above VA", "basis": f"LVN fast-travel to ${t_up:.2f}",
                         "target": f"${t_up:.2f}", "conf": round(min(0.40, confidence * 0.65), 2), "tone": "gn",
                         "scenario_tone": "up"})
        invalidation = (f"Acceptance (2+ closes) below VAL ${val:.2f} or above VAH ${vah:.2f} "
                        f"shifts the auction out of value — follow the direction of acceptance.")

    return targets, invalidation


# ── price-vs-VA read ──────────────────────────────────────────────────────────
def _price_vs_va(cur_close: float, vah: float, val: float, poc: float) -> str:
    if cur_close > vah * 1.005:
        return "above VAH"
    elif cur_close < val * 0.995:
        return "below VAL"
    elif abs(cur_close - poc) / max(poc, 1) < 0.005:
        return "at POC"
    elif cur_close >= poc:
        return "inside VA (upper)"
    else:
        return "inside VA (lower)"


# ── nearest LVN above / below ─────────────────────────────────────────────────
def _nearest_lvn(profile: List[Dict], cur_close: float) -> Dict[str, Optional[float]]:
    above = [p["price"] for p in profile if p.get("lvn") and p["price"] > cur_close]
    below = [p["price"] for p in profile if p.get("lvn") and p["price"] < cur_close]
    return {
        "lvn_above": round(min(above), 2) if above else None,
        "lvn_below": round(max(below), 2) if below else None,
    }


# ── one-sentence read ─────────────────────────────────────────────────────────
def _build_read(cur_close: float, poc: float, vah: float, val: float,
                price_pos: str, shape: str, lvns: Dict) -> str:
    va_range = f"${val:.2f}–${vah:.2f}"
    poc_s    = f"${poc:.2f}"

    if "above VAH" in price_pos:
        lvn = lvns.get("lvn_above")
        fast_zone = f"; next LVN (fast-travel) at ${lvn:.2f}" if lvn else ""
        return (f"Price has accepted above the {va_range} value area — "
                f"auction favours continuation toward the LVN above POC {poc_s}{fast_zone}; "
                f"retest of VAH ${vah:.2f} is the first support shelf on a pullback.")
    elif "below VAL" in price_pos:
        lvn = lvns.get("lvn_below")
        fast_zone = f"; next LVN at ${lvn:.2f}" if lvn else ""
        return (f"Price has accepted below the {va_range} value area — "
                f"auction favours continuation lower{fast_zone}; "
                f"VAL ${val:.2f} is first resistance on any bounce.")
    elif "at POC" in price_pos:
        return (f"Price is sitting on the POC {poc_s} — the highest-volume fair-value price "
                f"in the window. Expect near-term chop as the auction re-balances; "
                f"a break above VAH ${vah:.2f} or below VAL ${val:.2f} resolves direction.")
    else:
        side = "upper half" if "upper" in price_pos else "lower half"
        return (f"Price is inside the value area ({side} of {va_range}) — "
                f"the auction is in balance. POC ${poc:.2f} acts as a magnet; "
                f"VAH ${vah:.2f} / VAL ${val:.2f} are the rotation targets.")


# ── confidence scoring ────────────────────────────────────────────────────────
def _score_confidence(n_bars: int, total_vol: float, n_hvn: int, n_lvn: int) -> float:
    """More bars + richer profile → higher confidence (capped at 0.82)."""
    bar_score = min(1.0, n_bars / 80.0)
    node_score = min(1.0, (n_hvn + n_lvn) / 8.0)
    return round(min(0.82, 0.40 + 0.30 * bar_score + 0.12 * node_score), 2)


# ── public detector ────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str = "") -> Dict[str, Any]:
    """Volume Profile detector.  Never raises."""
    tf   = (meta or {}).get("tf", "Daily")
    base = {"ticker": ticker, "ok": True, "source": "real", "engine": NAME}
    w    = _tfw(tf)

    if df is None or len(df) < w["min"]:
        return {**base, "state": "none",
                "message": f"Not enough {tf.lower()} bars ({len(df) if df is not None else 0}) for a Volume Profile."}

    # window — use up to last win bars (keeps the profile period-relevant)
    window_df = df.iloc[-w["win"]:] if len(df) > w["win"] else df
    cur_close  = round(float(df.iloc[-1]["Close"]), 2)

    prof = _build_profile(window_df, n_bins=w["bins"])
    if prof is None:
        return {**base, "state": "none",
                "message": "No usable volume in the window — cannot build a profile.",
                "cur_close": cur_close}

    profile  = prof["profile"]
    poc      = prof["poc"]
    vah      = prof["vah"]
    val      = prof["val"]
    shape    = prof["shape"]

    n_hvn = sum(1 for p in profile if p.get("hvn"))
    n_lvn = sum(1 for p in profile if p.get("lvn"))
    confidence = _score_confidence(len(window_df), prof["total_vol"], n_hvn, n_lvn)

    price_pos = _price_vs_va(cur_close, vah, val, poc)
    lvns      = _nearest_lvn(profile, cur_close)
    read      = _build_read(cur_close, poc, vah, val, price_pos, shape, lvns)

    nodes = _extract_nodes(profile, cur_close)
    targets, invalidation = _compute_targets(poc, vah, val, cur_close, profile, confidence)

    # chart bars (windowed — last ~100 bars capped)
    chart_df = df.iloc[-min(100, len(df)):]
    bars     = _bar_payload(chart_df)

    stat = {
        "poc":         f"${poc:.2f}",
        "value_area":  f"{val:.2f} – {vah:.2f}",
        "shape":       shape,
        "price_vs_va": price_pos,
        "confidence":  confidence,
        # raw numbers for the JSX numeric renders
        "poc_raw":     poc,
        "vah_raw":     vah,
        "val_raw":     val,
    }

    return {
        **base,
        "state":        "real",
        "confidence":   confidence,
        "bars":         bars,
        "profile":      profile,
        "poc":          poc,
        "vah":          vah,
        "val":          val,
        "shape":        shape,
        "price_vs_va":  price_pos,
        "nodes":        nodes,
        "targets":      targets,
        "invalidation": invalidation,
        "read":         read,
        "stat":         stat,
        "cur_close":    cur_close,
        "lvn_above":    lvns["lvn_above"],
        "lvn_below":    lvns["lvn_below"],
        "n_hvn":        n_hvn,
        "n_lvn":        n_lvn,
        "window_bars":  len(window_df),
    }
