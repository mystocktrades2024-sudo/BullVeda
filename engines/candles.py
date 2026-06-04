"""engines/candles.py — Japanese candlestick pattern detector for the BullVeda Patterns lens.

Mechanism (principle 2): a candlestick reversal pattern at a meaningful level
(EMA-20, recent support/resistance) with above-average volume signals a real
intraday shift in supply/demand control; the glyph alone is noise — location +
volume confirmation (rvol > 1.1) transform it into a probabilistic edge.

Auto-discovered by pattern_engines.py via the NAME / detect() interface.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "candles"
LABEL = "Candlesticks"

# ── timeframe-aware scan windows ────────────────────────────────────
_TFW = {
    "Daily":   {"look": 10, "support_range": 20, "bars": 80},
    "Weekly":  {"look": 10, "support_range": 15, "bars": 60},
    "Monthly": {"look":  8, "support_range": 12, "bars": 48},
}


def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── historical reliability reference (static, research-based) ───────
_RELIABILITY = {
    "Bullish Engulfing":   {"wr": 0.63, "n": 318, "ff": "+1.8%", "note": "best at support · needs vol"},
    "Bearish Engulfing":   {"wr": 0.60, "n": 274, "ff": "-1.7%", "note": "best at resistance"},
    "Hammer":              {"wr": 0.59, "n": 261, "ff": "+1.3%", "note": "needs confirmation bar"},
    "Shooting Star":       {"wr": 0.57, "n": 198, "ff": "-1.2%", "note": "needs vol confirmation"},
    "Morning Star":        {"wr": 0.65, "n": 96,  "ff": "+2.4%", "note": "highest reliability (3-bar)"},
    "Evening Star":        {"wr": 0.63, "n": 84,  "ff": "-2.1%", "note": "3-bar · needs follow-through"},
    "Piercing Pattern":    {"wr": 0.58, "n": 112, "ff": "+1.5%", "note": "close > midpoint of prior"},
    "Dark Cloud Cover":    {"wr": 0.57, "n": 103, "ff": "-1.4%", "note": "close < midpoint of prior"},
    "Bullish Harami":      {"wr": 0.53, "n": 241, "ff": "+0.9%", "note": "weak alone · needs context"},
    "Bearish Harami":      {"wr": 0.52, "n": 218, "ff": "-0.8%", "note": "weak alone · needs context"},
    "Doji":                {"wr": 0.50, "n": 540, "ff": "±0.4%", "note": "context-only · no edge alone"},
    "Bullish Marubozu":    {"wr": 0.61, "n": 156, "ff": "+1.9%", "note": "full-body bull control"},
    "Bearish Marubozu":    {"wr": 0.59, "n": 143, "ff": "-1.7%", "note": "full-body bear control"},
}

# glyph canonical shapes for CandleGlyph component (o/c/h/l on arbitrary scale)
_GLYPH = {
    "Bullish Engulfing": [{"o": 8, "c": 6, "h": 8.3, "l": 5.7}, {"o": 5.6, "c": 9, "h": 9.4, "l": 5.2}],
    "Bearish Engulfing": [{"o": 4, "c": 7, "h": 7.5, "l": 3.7}, {"o": 7.4, "c": 3.2, "h": 7.8, "l": 2.8}],
    "Hammer":            [{"o": 7.2, "c": 7.8, "h": 8.2, "l": 3.0}],
    "Shooting Star":     [{"o": 4.6, "c": 4.1, "h": 9.2, "l": 3.8}],
    "Morning Star":      [{"o": 9, "c": 6.4, "h": 9.3, "l": 6.0}, {"o": 5.6, "c": 5.8, "h": 6.0, "l": 5.2}, {"o": 6.2, "c": 9.2, "h": 9.5, "l": 6.0}],
    "Evening Star":      [{"o": 3, "c": 6.8, "h": 7.0, "l": 2.7}, {"o": 7.1, "c": 6.9, "h": 7.5, "l": 6.7}, {"o": 6.5, "c": 3.2, "h": 6.7, "l": 2.9}],
    "Piercing Pattern":  [{"o": 8, "c": 5.0, "h": 8.3, "l": 4.7}, {"o": 4.6, "c": 6.7, "h": 7.0, "l": 4.4}],
    "Dark Cloud Cover":  [{"o": 4, "c": 7.5, "h": 7.8, "l": 3.7}, {"o": 8.0, "c": 5.3, "h": 8.3, "l": 5.0}],
    "Bullish Harami":    [{"o": 9, "c": 5.2, "h": 9.3, "l": 5.0}, {"o": 6.3, "c": 7.2, "h": 7.5, "l": 6.0}],
    "Bearish Harami":    [{"o": 3, "c": 7.5, "h": 7.8, "l": 2.7}, {"o": 6.4, "c": 5.5, "h": 6.8, "l": 5.2}],
    "Doji":              [{"o": 6.0, "c": 6.1, "h": 9.0, "l": 3.0}],
    "Bullish Marubozu":  [{"o": 4.0, "c": 9.0, "h": 9.0, "l": 4.0}],
    "Bearish Marubozu":  [{"o": 9.0, "c": 4.0, "h": 9.0, "l": 4.0}],
}


# ── pattern detection helpers ────────────────────────────────────────

def _body(o: float, c: float) -> float:
    return abs(c - o)


def _range(h: float, l: float) -> float:
    return h - l if h > l else 1e-9


def _is_bullish_engulfing(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    if pc >= po:
        return False  # prev must be bearish
    if cc <= co:
        return False  # curr must be bullish
    body_p = _body(po, pc)
    body_c = _body(co, cc)
    return co <= pc and cc >= po and body_c > body_p * 1.0


def _is_bearish_engulfing(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    if pc <= po:
        return False  # prev must be bullish
    if cc >= co:
        return False  # curr must be bearish
    body_p = _body(po, pc)
    body_c = _body(co, cc)
    return co >= pc and cc <= po and body_c > body_p * 1.0


def _is_hammer(row) -> bool:
    o, c, h, l = row["Open"], row["Close"], row["High"], row["Low"]
    body = _body(o, c)
    rng = _range(h, l)
    if rng < 1e-9:
        return False
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # body small (< 35% of range), lower wick >= 2× body, upper wick tiny
    return body / rng < 0.35 and lower_wick >= 2.0 * max(body, rng * 0.01) and upper_wick < body * 0.6


def _is_shooting_star(row) -> bool:
    o, c, h, l = row["Open"], row["Close"], row["High"], row["Low"]
    body = _body(o, c)
    rng = _range(h, l)
    if rng < 1e-9:
        return False
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return body / rng < 0.35 and upper_wick >= 2.0 * max(body, rng * 0.01) and lower_wick < body * 0.6


def _is_doji(row) -> bool:
    o, c, h, l = row["Open"], row["Close"], row["High"], row["Low"]
    rng = _range(h, l)
    body = _body(o, c)
    return rng > 1e-9 and body / rng < 0.10


def _is_bullish_harami(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    if pc >= po:
        return False  # prev bearish
    if cc <= co:
        return False  # curr bullish
    body_p = _body(po, pc)
    body_c = _body(co, cc)
    # curr body fully inside prev body
    return co >= min(po, pc) and cc <= max(po, pc) and body_c < body_p * 0.6


def _is_bearish_harami(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    if pc <= po:
        return False  # prev bullish
    if cc >= co:
        return False  # curr bearish
    body_p = _body(po, pc)
    body_c = _body(co, cc)
    return co <= max(po, pc) and cc >= min(po, pc) and body_c < body_p * 0.6


def _is_morning_star(b0, b1, b2) -> bool:
    o0, c0 = b0["Open"], b0["Close"]
    o1, c1 = b1["Open"], b1["Close"]
    o2, c2 = b2["Open"], b2["Close"]
    rng0 = _range(b0["High"], b0["Low"])
    rng2 = _range(b2["High"], b2["Low"])
    if rng0 < 1e-9 or rng2 < 1e-9:
        return False
    body1 = _body(o1, c1)
    rng1 = _range(b1["High"], b1["Low"])
    star = rng1 > 1e-9 and body1 / rng1 < 0.35
    # bar0 bearish, bar1 small body (star), bar2 bullish closing > midpoint bar0
    return (c0 < o0 and star and c2 > o2 and
            c2 > (o0 + c0) / 2 and
            _body(o0, c0) / rng0 > 0.4)


def _is_evening_star(b0, b1, b2) -> bool:
    o0, c0 = b0["Open"], b0["Close"]
    o1, c1 = b1["Open"], b1["Close"]
    o2, c2 = b2["Open"], b2["Close"]
    rng0 = _range(b0["High"], b0["Low"])
    rng2 = _range(b2["High"], b2["Low"])
    if rng0 < 1e-9 or rng2 < 1e-9:
        return False
    body1 = _body(o1, c1)
    rng1 = _range(b1["High"], b1["Low"])
    star = rng1 > 1e-9 and body1 / rng1 < 0.35
    return (c0 > o0 and star and c2 < o2 and
            c2 < (o0 + c0) / 2 and
            _body(o0, c0) / rng0 > 0.4)


def _is_piercing(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    mid = (po + pc) / 2
    rng_p = _range(prev["High"], prev["Low"])
    if rng_p < 1e-9:
        return False
    return (pc < po and cc > co and  # prev bear, curr bull
            co < pc and              # gap down open
            cc > mid and cc < po)    # close > midpoint but < prev open


def _is_dark_cloud(prev, curr) -> bool:
    po, pc = prev["Open"], prev["Close"]
    co, cc = curr["Open"], curr["Close"]
    mid = (po + pc) / 2
    rng_p = _range(prev["High"], prev["Low"])
    if rng_p < 1e-9:
        return False
    return (pc > po and cc < co and  # prev bull, curr bear
            co > pc and              # gap up open
            cc < mid and cc > po)    # close < midpoint but > prev open


def _is_bullish_marubozu(row) -> bool:
    o, c, h, l = row["Open"], row["Close"], row["High"], row["Low"]
    rng = _range(h, l)
    if rng < 1e-9:
        return False
    body = _body(o, c)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return (c > o and body / rng > 0.90 and
            upper_wick < rng * 0.05 and lower_wick < rng * 0.05)


def _is_bearish_marubozu(row) -> bool:
    o, c, h, l = row["Open"], row["Close"], row["High"], row["Low"]
    rng = _range(h, l)
    if rng < 1e-9:
        return False
    body = _body(o, c)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return (c < o and body / rng > 0.90 and
            upper_wick < rng * 0.05 and lower_wick < rng * 0.05)


# ── location vs key levels ──────────────────────────────────────────

def _location_label(close: float, ema20: float, ema50: float,
                    sup: float, res: float, atr: float) -> str:
    atr = max(atr, close * 0.002)
    parts = []
    if abs(close - ema20) < atr * 0.8:
        parts.append("EMA-20")
    elif abs(close - ema50) < atr * 0.8:
        parts.append("EMA-50")
    if sup and abs(close - sup) < atr * 1.2:
        parts.append(f"${sup:.2f} support")
    elif res and abs(close - res) < atr * 1.2:
        parts.append(f"${res:.2f} resist")
    return " + ".join(parts) if parts else "mid-range"


def _support_resistance(df: pd.DataFrame, n: int) -> tuple:
    """Simple swing high/low support/resistance from last n bars."""
    sub = df.iloc[-n:]
    lo = sub["Low"].min()
    hi = sub["High"].max()
    return round(lo, 2), round(hi, 2)


# ── build the detected[] list ───────────────────────────────────────

def _scan_patterns(df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    """Return detected patterns over the last look-window, newest first."""
    w = _tfw(tf)
    look = w["look"]
    sr_n = w["support_range"]
    n = len(df)
    if n < 4:
        return []

    # support/resistance anchor from prior window (not look itself)
    sup, res = _support_resistance(df.iloc[:max(4, n - look)], sr_n)

    detected: List[Dict[str, Any]] = []
    start = max(2, n - look - 1)  # need at least 2 bars of context for 3-bar patterns

    dates = df.index.tolist()

    for i in range(start, n):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        prev2 = df.iloc[i - 2] if i >= 2 else None

        close = float(row["Close"])
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        atr = float(row["atr"])
        rvol = float(row["rvol"]) if np.isfinite(row["rvol"]) else 1.0
        bar_i = i  # absolute index in full df (used for chart marker)
        date_str = fmt_date(dates[i], tf)

        loc = _location_label(close, ema20, ema50, sup, res, atr)
        vol_ok = rvol >= 1.1
        vol_lbl = f"{rvol:.1f}× {'✓' if vol_ok else '✗'}"

        def _det(name: str, tone: str, kind: str):
            rel_info = _RELIABILITY.get(name, {})
            wr = rel_info.get("wr", 0.50)
            n_sample = rel_info.get("n", 0)
            note = rel_info.get("note", "")
            # confidence = base wr boosted by vol confirmation + meaningful location
            conf = wr
            if vol_ok:
                conf = min(conf + 0.06, 0.95)
            if loc != "mid-range":
                conf = min(conf + 0.04, 0.95)
            status = "CONFIRMED" if vol_ok and loc != "mid-range" else ("WEAK" if not vol_ok else "LIKELY")
            status_tone = "gn" if status == "CONFIRMED" else ("amb" if status == "LIKELY" else "ink-2")
            detected.append({
                "name": name,
                "glyph": _GLYPH.get(name, _GLYPH.get("Doji")),
                "date": date_str,
                "bar_i": bar_i,
                "tone": tone,
                "kind": kind,
                "loc": loc,
                "rvol": round(rvol, 2),
                "vol": vol_lbl,
                "note": note,
                "reliability": round(wr, 2),
                "confidence": round(conf, 2),
                "status": status,
                "status_tone": status_tone,
                "n": n_sample,
                "ff": rel_info.get("ff", ""),
            })

        # ── 3-bar patterns (require prev2) ──────────────────────────
        if prev2 is not None:
            if _is_morning_star(prev2, prev, row):
                _det("Morning Star", "gn", "Reversal ↑")
                continue
            if _is_evening_star(prev2, prev, row):
                _det("Evening Star", "rd", "Reversal ↓")
                continue

        # ── 2-bar patterns ──────────────────────────────────────────
        if _is_bullish_engulfing(prev, row):
            _det("Bullish Engulfing", "gn", "Reversal ↑")
            continue
        if _is_bearish_engulfing(prev, row):
            _det("Bearish Engulfing", "rd", "Reversal ↓")
            continue
        if _is_bullish_harami(prev, row):
            _det("Bullish Harami", "gn", "Reversal ↑")
            continue
        if _is_bearish_harami(prev, row):
            _det("Bearish Harami", "rd", "Reversal ↓")
            continue
        if _is_piercing(prev, row):
            _det("Piercing Pattern", "gn", "Reversal ↑")
            continue
        if _is_dark_cloud(prev, row):
            _det("Dark Cloud Cover", "rd", "Reversal ↓")
            continue

        # ── 1-bar patterns ──────────────────────────────────────────
        if _is_bullish_marubozu(row):
            _det("Bullish Marubozu", "gn", "Continuation ↑")
            continue
        if _is_bearish_marubozu(row):
            _det("Bearish Marubozu", "rd", "Continuation ↓")
            continue
        if _is_hammer(row):
            _det("Hammer", "gn", "Reversal ↑")
            continue
        if _is_shooting_star(row):
            _det("Shooting Star", "rd", "Reversal ↓")
            continue
        if _is_doji(row):
            _det("Doji", "ink-2", "Indecision")
            # don't continue — still detect other 1-bar (doji is least specific)

    # newest first
    return detected[::-1]


# ── bar payload ──────────────────────────────────────────────────────

def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        rv = float(r["rvol"]) if np.isfinite(r["rvol"]) else 1.0
        out.append({
            "o": round(float(r["Open"]), 2),
            "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2),
            "lo": round(float(r["Low"]), 2),
            "v": round(rv, 2),
        })
    return out


# ── main entry point ─────────────────────────────────────────────────

def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Detect candlestick patterns from real OHLCV bars.

    Returns a JSON-serializable dict matching the CandlestickView contract.
    Never raises — returns state='none' with a message on any failure.
    """
    tf = meta.get("tf", "Daily")
    w = _tfw(tf)
    n = len(df)
    cur_close = round(float(df["Close"].iloc[-1]), 2) if n > 0 else 0.0

    if n < 5:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Insufficient {tf.lower()} bars ({n}) — need ≥5.",
            "cur_close": cur_close,
        }

    # windowed bars for chart (last w["bars"])
    chart_n = min(w["bars"], n)
    chart_df = df.iloc[-chart_n:]
    bars = _bar_payload(chart_df)

    # scan patterns in the look window
    detected = _scan_patterns(df, tf)

    # pick the most significant detected pattern (highest confidence, newest tie-break)
    significant = [d for d in detected if d["status"] in ("CONFIRMED", "LIKELY")]
    best = significant[0] if significant else (detected[0] if detected else None)

    if not detected:
        # nothing notable — honest none
        return {
            "ok": True, "source": "real", "state": "none",
            "bars": bars,
            "detected": [],
            "message": f"No notable candlestick patterns in the last {w['look']} {tf.lower()} bars.",
            "cur_close": cur_close,
        }

    # build stat header from best pattern
    if best:
        b = best
        stat = {
            "active_signal": b["name"],
            "location": b["loc"],
            "confirmation": b["vol"],
            "reliability": f"{int(b['reliability']*100)}% · n={b['n']}",
            "tone": b["tone"],
        }
        # overall read / confidence
        is_bull = "↑" in b.get("kind", "")
        is_bear = "↓" in b.get("kind", "")
        if is_bull:
            read = (
                f"{b['name']} on {b['date']} at {b['loc']} "
                f"({b['vol']}) — {int(b['reliability']*100)}% historical WR (n={b['n']}). "
                f"{b['note'].capitalize() if b['note'] else 'Bullish reversal signal.'}. "
                f"Confirmation layer: valid only with location + volume context."
            )
        elif is_bear:
            read = (
                f"{b['name']} on {b['date']} at {b['loc']} "
                f"({b['vol']}) — {int(b['reliability']*100)}% historical WR (n={b['n']}). "
                f"{b['note'].capitalize() if b['note'] else 'Bearish reversal signal.'}. "
                f"Glyph alone is noise — pair with location and volume."
            )
        else:
            read = (
                f"{b['name']} on {b['date']}: indecision at {b['loc']}. "
                f"Context-only signal — no edge without follow-through confirmation."
            )
        confidence = b["confidence"]
    else:
        stat = {
            "active_signal": detected[0]["name"] if detected else "—",
            "location": detected[0]["loc"] if detected else "—",
            "confirmation": detected[0]["vol"] if detected else "—",
            "reliability": "—",
            "tone": "ink-2",
        }
        read = "Patterns detected but none meet location + volume confirmation threshold."
        confidence = 0.30

    # add chart markers for detected bars (offset within chart window)
    chart_offset = n - chart_n
    for d in detected:
        bi = d["bar_i"] - chart_offset
        if 0 <= bi < chart_n:
            d["chart_i"] = bi
        else:
            d["chart_i"] = None

    # hlines: EMA20 + recent support/resistance for context
    last = df.iloc[-1]
    ema20 = round(float(last["ema20"]), 2)
    ema50 = round(float(last["ema50"]), 2)
    sr_n = w["support_range"]
    sup_raw, res_raw = _support_resistance(df.iloc[:-w["look"]] if n > w["look"] else df, sr_n)

    hlines = [
        {"price": ema20, "label": f"EMA20 {ema20}", "tone": "cy", "dash": "3 3"},
        {"price": ema50, "label": f"EMA50 {ema50}", "tone": "ink-3", "dash": "3 5"},
    ]
    if sup_raw and abs(sup_raw - cur_close) / max(cur_close, 1) < 0.15:
        hlines.append({"price": sup_raw, "label": f"Sup {sup_raw}", "tone": "gn", "dash": "2 4"})
    if res_raw and abs(res_raw - cur_close) / max(cur_close, 1) < 0.15:
        hlines.append({"price": res_raw, "label": f"Res {res_raw}", "tone": "rd", "dash": "2 4"})

    # markers for chart — only detected patterns with a valid chart_i
    markers = []
    for d in detected:
        ci = d.get("chart_i")
        if ci is not None and 0 <= ci < len(bars):
            is_bull_pat = "↑" in d["kind"]
            markers.append({
                "i": ci,
                "label": d["name"][:3].upper(),
                "tone": d["tone"] if d["tone"] != "ink-2" else "ink-3",
                "place": "above" if not is_bull_pat else "below",
            })

    return {
        "ok": True,
        "source": "real",
        "state": "real",
        "confidence": round(confidence, 2),
        "bars": bars,
        "hlines": hlines,
        "markers": markers,
        "detected": detected,
        "stat": stat,
        "read": read,
        "cur_close": cur_close,
    }
