"""engines/ichimoku.py — Ichimoku Kinko Hyo detector for the BullVeda Patterns lens.

Mechanism (principle 2): Ichimoku encodes equilibrium across multiple lookbacks at
once; price above a thick, rising cloud with aligned Tenkan > Kijun and a free
Chikou span reflects durable, multi-period trend agreement — the system's "5 bullets
must align" tally provides an objective entry filter that pure candlestick technicals
lack.

Honesty (principle 4): when the cloud is too thin to be meaningful or fewer than
52 bars exist, we return state="none" rather than fabricate signals.

Timeframe-aware (principle 5): standard 9/26/52 periods are used directly — Ichimoku
periods are defined in calendar-market-days, not bars, so on weekly/monthly data we
scale the periods (9→3w, 26→7w, 52→13w is classic; we keep standard but accept lower
min-bar counts because the signal logic remains valid).

CLI: python3 -c "import pattern_engines as pe; import json; d=pe.detect('ichimoku','AAPL','SWING'); print(json.dumps({k:v for k,v in d.items() if k not in ('bars','cloud','lines')},indent=2,default=str))"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pattern_data import fmt_date, mode_meta, norm_mode

NAME = "ichimoku"
LABEL = "Ichimoku"

# Periods — standard classic Ichimoku (Goichi Hosoda, 1969)
_TK = 9
_KJ = 26
_SB = 52
_FWD = 26   # cloud plotted 26 bars ahead; Chikou plotted 26 bars back

# minimum bars required before we claim a usable signal
_MIN_BARS: Dict[str, int] = {
    "Daily": 80,
    "Weekly": 55,
    "Monthly": 35,   # archive typically delivers ~38 monthly bars; 35 avoids spurious none-states
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _rolling_midpoint(h: pd.Series, l: pd.Series, n: int) -> pd.Series:
    """(HH_n + LL_n) / 2 — the Ichimoku equilibrium line for period n."""
    return (h.rolling(n, min_periods=n).max() + l.rolling(n, min_periods=n).min()) / 2


def _bar_payload(df: pd.DataFrame, window: int = 100) -> List[Dict[str, float]]:
    """Last `window` bars as {o, c, hi, lo, v} for the chart."""
    sub = df.iloc[-window:]
    out = []
    for _, r in sub.iterrows():
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(float(r.get("rvol", 1.0)), 3),
        })
    return out


# ── core Ichimoku computation ──────────────────────────────────────────────────

def _compute_ichimoku(df: pd.DataFrame) -> Dict[str, Any]:
    h, l, c = df["High"], df["Low"], df["Close"]
    n = len(df)

    tenkan_raw = _rolling_midpoint(h, l, _TK)
    kijun_raw  = _rolling_midpoint(h, l, _KJ)
    span_a_raw = (tenkan_raw + kijun_raw) / 2          # plotted +26 ahead
    span_b_raw = _rolling_midpoint(h, l, _SB)           # plotted +26 ahead

    # ── chart-index lists for the JSX lines/cloud props ──────────────────────
    # We show only the windowed slice (last ~100 bars) on the chart, so bar-index
    # 0 in the output is the FIRST bar of that window.
    win = min(100, n)
    offset = n - win   # position of window[0] in the full df

    # Tenkan and Kijun — polylines over the window
    tenkan_pts: List[Dict] = []
    kijun_pts:  List[Dict] = []
    chikou_pts: List[Dict] = []

    for wi in range(win):
        fi = offset + wi  # full-df index
        if not np.isnan(tenkan_raw.iloc[fi]):
            tenkan_pts.append({"i": wi, "price": round(float(tenkan_raw.iloc[fi]), 2)})
        if not np.isnan(kijun_raw.iloc[fi]):
            kijun_pts.append({"i": wi, "price": round(float(kijun_raw.iloc[fi]), 2)})
        # Chikou: close plotted _FWD bars BACK — bar fi's close appears at chart index wi - FWD
        # So for chart index wi, chikou value is close at full-df index fi + _FWD
        chi_fi = fi + _FWD
        if chi_fi < n:
            pass  # filled below in reverse

    # Chikou: close at each bar plotted 26 bars BACK
    for wi in range(win):
        fi = offset + wi
        chi_wi = wi - _FWD
        if chi_wi >= 0:
            chikou_pts.append({"i": chi_wi, "price": round(float(c.iloc[fi]), 2)})

    # Cloud (Kumo): span_a and span_b plotted _FWD bars AHEAD
    # Chart bars: 0..win-1 are the historical bars; win..win+_FWD-1 are the projected region.
    # span_a at chart-index wi is span_a_raw at full-df index offset + wi - _FWD
    span_a_pts: List[Dict] = []
    span_b_pts: List[Dict] = []

    # Historical cloud (fills the existing bars area: wi=0..win-1)
    for wi in range(win):
        src = offset + wi - _FWD
        if src >= 0 and not np.isnan(span_a_raw.iloc[src]):
            span_a_pts.append({"i": wi, "price": round(float(span_a_raw.iloc[src]), 2)})
        if src >= 0 and not np.isnan(span_b_raw.iloc[src]):
            span_b_pts.append({"i": wi, "price": round(float(span_b_raw.iloc[src]), 2)})

    # Projected cloud (forward region: chart index win..win+_FWD-1)
    for fw in range(_FWD):
        src = offset + (win - 1) - (_FWD - 1 - fw)
        # span at projected chart-index = span_a_raw at src (the unshifted value)
        proj_src = n - _FWD + fw  # full df index for the un-shifted source
        if 0 <= proj_src < n:
            sa = span_a_raw.iloc[proj_src]
            sb = span_b_raw.iloc[proj_src]
            if not np.isnan(sa):
                span_a_pts.append({"i": win + fw, "price": round(float(sa), 2)})
            if not np.isnan(sb):
                span_b_pts.append({"i": win + fw, "price": round(float(sb), 2)})

    return {
        "tenkan_raw":  tenkan_raw,
        "kijun_raw":   kijun_raw,
        "span_a_raw":  span_a_raw,
        "span_b_raw":  span_b_raw,
        "tenkan_pts":  tenkan_pts,
        "kijun_pts":   kijun_pts,
        "chikou_pts":  chikou_pts,
        "span_a_pts":  span_a_pts,
        "span_b_pts":  span_b_pts,
        "win":         win,
        "offset":      offset,
    }


# ── signal evaluation ──────────────────────────────────────────────────────────

def _eval_signals(df: pd.DataFrame, ich: Dict[str, Any], tf: str) -> Dict[str, Any]:
    """Evaluate the 5 classic Ichimoku alignment signals and return a verdict."""
    n = len(df)
    close_now = float(df["Close"].iloc[-1])
    tenkan_now = ich["tenkan_raw"].iloc[-1]
    kijun_now  = ich["kijun_raw"].iloc[-1]
    span_a_now = ich["span_a_raw"].iloc[-1]
    span_b_now = ich["span_b_raw"].iloc[-1]

    # cloud boundaries at the current bar (unshifted, so THIS is the current cloud)
    cloud_top    = max(span_a_now, span_b_now) if not (np.isnan(span_a_now) or np.isnan(span_b_now)) else None
    cloud_bottom = min(span_a_now, span_b_now) if not (np.isnan(span_a_now) or np.isnan(span_b_now)) else None

    # 1. Price vs cloud
    if cloud_top is None:
        price_vs_cloud = "unknown"
    elif close_now > cloud_top:
        price_vs_cloud = "above"
    elif close_now < cloud_bottom:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "inside"

    # 2. TK cross
    if np.isnan(tenkan_now) or np.isnan(kijun_now):
        tk_cross = "unknown"
    elif tenkan_now > kijun_now:
        tk_cross = "bull"
    elif tenkan_now < kijun_now:
        tk_cross = "bear"
    else:
        tk_cross = "flat"

    # 3. Chikou vs price 26 bars ago
    chi_bar = n - 1 - _FWD
    if chi_bar >= 0:
        price_26ago = float(df["Close"].iloc[chi_bar])
        chikou_close = close_now   # chikou IS the current close plotted 26 back
        chikou_free = chikou_close > price_26ago
        # check if chikou crosses any candles in its lookback window
        if chi_bar >= 5:
            hist_hi = df["High"].iloc[max(0, chi_bar - 5):chi_bar + 1].max()
            hist_lo = df["Low"].iloc[max(0, chi_bar - 5):chi_bar + 1].min()
            chikou_obstructed = (chikou_close >= hist_lo and chikou_close <= hist_hi)
        else:
            chikou_obstructed = False
        chikou_status = "obstructed" if chikou_obstructed else ("free" if chikou_free else "below")
    else:
        chikou_status = "unknown"
        chikou_free = False

    # 4. Future Kumo twist / color — look at _FWD bars ahead span_a vs span_b
    future_idx = n - 1  # the last available future projection is span at n-1 (shifted to n-1+_FWD)
    sa_future = ich["span_a_raw"].iloc[-1]
    sb_future = ich["span_b_raw"].iloc[-1]
    if np.isnan(sa_future) or np.isnan(sb_future):
        future_kumo = "unknown"
    elif sa_future > sb_future:
        future_kumo = "green"
    elif sa_future < sb_future:
        future_kumo = "red"
    else:
        future_kumo = "flat"

    # 5. Price vs Kijun baseline
    price_vs_kijun = "above" if close_now > kijun_now and not np.isnan(kijun_now) else \
                     "below" if close_now < kijun_now and not np.isnan(kijun_now) else "unknown"

    # ── signal tally (5 classic signals) ─────────────────────────────────────
    sig_results = {
        "price_above_cloud": price_vs_cloud == "above",
        "tk_bullish":        tk_cross == "bull",
        "chikou_free":       chikou_status in ("free",),
        "future_kumo_green": future_kumo == "green",
        "price_above_kijun": price_vs_kijun == "above",
    }
    bull_count = sum(sig_results.values())
    bear_count  = 0
    # bear checks: invert the bull signals
    bear_checks = {
        "price_below_cloud": price_vs_cloud == "below",
        "tk_bearish":        tk_cross == "bear",
        "chikou_below":      chikou_status == "below",
        "future_kumo_red":   future_kumo == "red",
        "price_below_kijun": price_vs_kijun == "below",
    }
    bear_count = sum(bear_checks.values())

    # verdict
    if bull_count >= 4:
        verdict = "strong_bull"
    elif bull_count == 3:
        verdict = "bull"
    elif bear_count >= 4:
        verdict = "strong_bear"
    elif bear_count == 3:
        verdict = "bear"
    elif price_vs_cloud == "inside":
        verdict = "inside_cloud"
    else:
        verdict = "neutral"

    # cloud thickness as % of price — below 0.5% = thin/meaningless
    if cloud_top is not None and cloud_bottom is not None and close_now > 0:
        cloud_thickness_pct = (cloud_top - cloud_bottom) / close_now
    else:
        cloud_thickness_pct = 0.0

    return {
        "price_vs_cloud":      price_vs_cloud,
        "tk_cross":            tk_cross,
        "chikou_status":       chikou_status,
        "future_kumo":         future_kumo,
        "price_vs_kijun":      price_vs_kijun,
        "bull_count":          bull_count,
        "bear_count":          bear_count,
        "verdict":             verdict,
        "sig_results":         sig_results,
        "cloud_top":           cloud_top,
        "cloud_bottom":        cloud_bottom,
        "cloud_thickness_pct": cloud_thickness_pct,
        "tenkan_now":          float(tenkan_now) if not np.isnan(tenkan_now) else None,
        "kijun_now":           float(kijun_now)  if not np.isnan(kijun_now)  else None,
        "span_a_now":          float(span_a_now) if not np.isnan(span_a_now) else None,
        "span_b_now":          float(span_b_now) if not np.isnan(span_b_now) else None,
        "close_now":           close_now,
    }


# ── read + target + confidence prose ──────────────────────────────────────────

def _build_read(sig: Dict, ticker: str, tf: str) -> str:
    v = sig["verdict"]
    bull = sig["bull_count"]
    bear = sig["bear_count"]
    tk = sig["tk_cross"]
    cloud = sig["price_vs_cloud"]
    kj = round(sig["kijun_now"] or 0, 2)
    close = round(sig["close_now"], 2)
    if v == "strong_bull":
        return (f"All 5 Ichimoku signals aligned bullish ({bull}/5): price ${close} is above a green cloud, "
                f"Tenkan > Kijun ({tk}), Chikou free, and baseline ${kj} is support.")
    if v == "bull":
        return (f"{bull}/5 Ichimoku signals bullish: price ${close} is {cloud} cloud with a {tk} TK cross; "
                f"Kijun-sen ${kj} acts as dynamic trailing stop.")
    if v == "strong_bear":
        return (f"All 5 Ichimoku signals aligned bearish ({bear}/5): price ${close} is below a red cloud, "
                f"Tenkan < Kijun, Chikou obstructed; Kijun ${kj} is overhead resistance.")
    if v == "bear":
        return (f"{bear}/5 Ichimoku signals bearish: price ${close} is {cloud} cloud with a {tk} TK cross; "
                f"Kijun-sen ${kj} is first resistance to watch.")
    if v == "inside_cloud":
        return (f"Price ${close} is inside the Kumo — trend is contested, no clear edge. "
                f"Wait for a decisive cloud breakout before acting. Kijun ${kj}.")
    return (f"Mixed Ichimoku signals ({bull} bull / {bear} bear): price ${close} is {cloud} cloud. "
            f"System has no strong directional edge right now. Watch for cloud or TK alignment.")


def _build_targets(sig: Dict, df: pd.DataFrame) -> Dict:
    close = sig["close_now"]
    kijun = sig["kijun_now"] or close
    cloud_top = sig["cloud_top"] or close
    cloud_bottom = sig["cloud_bottom"] or close
    cloud_h = abs(cloud_top - cloud_bottom)

    bull = sig["verdict"] in ("strong_bull", "bull")

    if bull:
        kumo_break_tgt = round(cloud_top + cloud_h, 2)
        stop = round(kijun * 0.995, 2)   # just below Kijun
        rr = round((kumo_break_tgt - close) / max(0.01, close - stop), 2) if close > stop else None
        invalidation_note = (
            f"Daily close back inside the Kumo (< ${round(cloud_top,2)}) neutralises the signal; "
            f"below Kijun ${round(kijun,2)} flips bearish."
        )
    else:
        kumo_break_tgt = round(cloud_bottom - cloud_h, 2)
        stop = round(kijun * 1.005, 2)
        rr = round((close - kumo_break_tgt) / max(0.01, stop - close), 2) if close < stop else None
        invalidation_note = (
            f"Daily close back inside the Kumo (> ${round(cloud_bottom,2)}) neutralises the signal; "
            f"above Kijun ${round(kijun,2)} flips bullish."
        )

    return {
        "kumo_target": kumo_break_tgt,
        "kijun_stop":  round(kijun, 2),
        "cloud_top":   round(cloud_top, 2),
        "cloud_bottom": round(cloud_bottom, 2),
        "cloud_height": round(cloud_h, 2),
        "rr":          rr,
        "invalidation_note": invalidation_note,
        "bull":        bull,
    }


def _confidence(sig: Dict) -> float:
    """0–1 confidence based on signal alignment count and cloud thickness."""
    bull = sig["bull_count"]
    bear = sig["bear_count"]
    max_count = max(bull, bear)
    base = max_count / 5.0                   # 0.2 – 1.0
    thickness_bonus = min(0.1, sig["cloud_thickness_pct"] * 2)  # thicker cloud = more reliable
    return round(min(1.0, base + thickness_bonus), 2)


# ── signal rows for the JSX IchSignals component ──────────────────────────────

def _build_signal_rows(sig: Dict) -> List[Dict]:
    cloud = sig["price_vs_cloud"]
    tk    = sig["tk_cross"]
    chikou = sig["chikou_status"]
    future = sig["future_kumo"]
    kijun_v = sig["price_vs_kijun"]

    def _pill(pass_: bool, txt_pass: str, txt_fail: str) -> Dict:
        return {"v": txt_pass if pass_ else txt_fail, "tone": "gn" if pass_ else "rd"}

    return [
        {"s": "Price above the Kumo (cloud)",
         **_pill(cloud == "above",
                 "PASS · above cloud", "FAIL · " + ("inside" if cloud == "inside" else "below"))},
        {"s": "Tenkan > Kijun (bullish TK cross)",
         **_pill(tk == "bull",
                 "PASS · T > K", "FAIL · " + ("bearish" if tk == "bear" else "flat"))},
        {"s": "Chikou span free of price action",
         **_pill(chikou == "free",
                 "PASS · free", "FAIL · " + chikou)},
        {"s": "Future Kumo green (Senkou A > B)",
         **_pill(future == "green",
                 "PASS · green", "FAIL · " + future)},
        {"s": "Price above Kijun baseline",
         **_pill(kijun_v == "above",
                 "PASS · above", "FAIL · below")},
    ]


# ── component lines table rows ─────────────────────────────────────────────────

def _build_line_rows(sig: Dict, df: pd.DataFrame, tf: str) -> List[Dict]:
    """Five Ichimoku component values for the IchLines table."""
    def _r(v):
        return f"{v:.2f}" if v is not None else "—"

    chikou_val = round(sig["close_now"], 2)  # chikou is just the current close
    # determine chikou "above/below price 26 bars ago"
    n = len(df)
    chi_bar = n - 1 - _FWD
    if chi_bar >= 0:
        p26 = float(df["Close"].iloc[chi_bar])
        chi_role = f"lagging close · {'above' if chikou_val > p26 else 'below'} price {_FWD}-bars-ago"
    else:
        chi_role = "lagging close"

    cloud_top = sig["cloud_top"]
    cloud_bottom = sig["cloud_bottom"]

    return [
        {"name": f"Tenkan-sen ({_TK})",    "val": _r(sig["tenkan_now"]), "role": "fast trigger · 9-period midpoint", "tone": "cy"},
        {"name": f"Kijun-sen ({_KJ})",     "val": _r(sig["kijun_now"]),  "role": "trend baseline · dynamic stop",   "tone": "copper"},
        {"name": "Senkou A",               "val": _r(sig["span_a_now"]), "role": "cloud top (leading)",              "tone": "gn"},
        {"name": "Senkou B",               "val": _r(sig["span_b_now"]), "role": "cloud base (leading)",             "tone": "rd"},
        {"name": "Chikou span",            "val": _r(chikou_val),        "role": chi_role,                           "tone": "violet"},
    ]


# ── stat header cells ──────────────────────────────────────────────────────────

def _build_stat(sig: Dict, conf: float) -> Dict:
    cloud   = sig["price_vs_cloud"].replace("_", " ").title()
    tk_lbl  = {"bull": "Bullish", "bear": "Bearish", "flat": "Flat", "unknown": "—"}.get(sig["tk_cross"], "—")
    chikou_lbl = {"free": "Free", "obstructed": "Obstructed", "below": "Below price", "unknown": "—"}.get(sig["chikou_status"], "—")
    future_lbl = {"green": "Green · bullish twist", "red": "Red · bearish twist", "flat": "Flat", "unknown": "—"}.get(sig["future_kumo"], "—")
    return {
        "cloud":       cloud,
        "tk_cross":    tk_lbl,
        "chikou":      chikou_lbl,
        "future_kumo": future_lbl,
        "confidence":  conf,
        "bull_count":  sig["bull_count"],
        "verdict":     sig["verdict"],
    }


# ── main entry point ───────────────────────────────────────────────────────────

def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Ichimoku Kinko Hyo detector. Returns JSON-serialisable dict. MUST NOT raise."""
    tf   = meta.get("tf", "Daily")
    mode = meta.get("mode", "SWING")
    n    = len(df)
    min_bars = _MIN_BARS.get(tf, 80)
    cur_close = round(float(df["Close"].iloc[-1]), 2) if n > 0 else 0.0

    if n < min_bars:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Only {n} {tf.lower()} bars — need ≥{min_bars} for a reliable Ichimoku read.",
            "cur_close": cur_close,
        }

    # ── compute lines ──────────────────────────────────────────────────────────
    ich = _compute_ichimoku(df)
    sig = _eval_signals(df, ich, tf)

    if sig["cloud_top"] is None:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": "Insufficient data to form the Kumo — Ichimoku requires at least 52 valid bars.",
            "cur_close": cur_close,
        }

    conf    = _confidence(sig)
    tgts    = _build_targets(sig, df)
    read    = _build_read(sig, ticker, tf)
    signals = _build_signal_rows(sig)
    lines_t = _build_line_rows(sig, df, tf)
    stat    = _build_stat(sig, conf)

    # ── bars for CandleChart (windowed) ───────────────────────────────────────
    win = ich["win"]
    bars = _bar_payload(df, window=win)

    # ── cloud & lines props for CandleChart ───────────────────────────────────
    cloud = {
        "spanA": ich["span_a_pts"],
        "spanB": ich["span_b_pts"],
    }
    chart_lines = [
        {"pts": ich["tenkan_pts"], "tone": "cy",     "width": 1.4, "opacity": 0.9},
        {"pts": ich["kijun_pts"],  "tone": "copper",  "width": 1.6, "opacity": 0.9},
        {"pts": ich["chikou_pts"], "tone": "violet",  "width": 1.2, "dash": "4 3", "opacity": 0.7},
    ]

    # ── hlines for chart: Kijun as trailing stop, Kumo target ─────────────────
    chart_hlines = []
    if sig["kijun_now"] is not None:
        chart_hlines.append({
            "price": round(sig["kijun_now"], 2),
            "label": f"Kijun {sig['kijun_now']:.2f}",
            "tone":  "copper",
            "dash":  "4 4",
        })
    if tgts["bull"]:
        chart_hlines.append({
            "price": tgts["kumo_target"],
            "label": f"T1 {tgts['kumo_target']:.2f}",
            "tone":  "gn",
            "dash":  "5 4",
        })
    else:
        chart_hlines.append({
            "price": tgts["kumo_target"],
            "label": f"T1 {tgts['kumo_target']:.2f}",
            "tone":  "rd",
            "dash":  "5 4",
        })

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "ticker":     ticker,
        "cur_close":  cur_close,
        "confidence": conf,

        # chart data
        "bars":       bars,
        "cloud":      cloud,
        "lines":      chart_lines,
        "hlines":     chart_hlines,
        "span":       win + _FWD,        # total chart columns including projection
        "projectFrom": win,              # bar index where projection starts

        # rendered components
        "stat":       stat,
        "signals":    signals,           # list[{s, v, tone}]  — 5 rows
        "ich_lines":  lines_t,           # list[{name, val, role, tone}] — 5 rows
        "targets":    tgts,
        "read":       read,

        # scalar fields surfaced by the stat bar
        "tenkan":     sig["tenkan_now"],
        "kijun":      sig["kijun_now"],
        "span_a":     sig["span_a_now"],
        "span_b":     sig["span_b_now"],
        "price_vs_cloud": sig["price_vs_cloud"],
        "tk_cross":   sig["tk_cross"],
        "chikou_status": sig["chikou_status"],
        "future_kumo": sig["future_kumo"],
        "bull_count": sig["bull_count"],
        "verdict":    sig["verdict"],
    }
