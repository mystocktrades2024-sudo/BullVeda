"""
SMC level computation — single source of truth for VWAP / Anchored VWAP / fractals
used by the SMC sub-tab (infra/prototype/subtabs/smc/redesign.html).

Computes directly from the trimmed OHLCV array embedded in tickers.json
(`r['ohlcv']` — list of {d, o, h, l, c, v} dicts, ~90 daily bars). This
guarantees coverage for every ticker that has bars (~99% of universe),
not just BUY/WATCH candidates that go through deep technical analysis.

Fields produced (under `vwap` dict + ticker root):
  vwap_20d            — 20-bar rolling VWAP (last bar)
  vwap_band_upper     — vwap_20d + 1σ of (close − vwap_20d)
  vwap_band_lower     — vwap_20d − 1σ
  avwap_swing_low     — VWAP anchored to most recent 60d swing low
  avwap_er            — VWAP anchored to last past earnings date
  avwap_fomc          — VWAP anchored to last past FOMC announcement date
  above_vwap, above_avwap — bool helpers

Root fields (mirror analysis.py contract):
  fractal_high        — 20-day rolling max(high)  (Bill Williams style — see note)
  fractal_low         — 20-day rolling min(low)
  fractal_signal      — short status note

NOTE on fractal_high: the existing analysis.py `_williams_fractals()` returns
the most recent *unbroken* fractal level (price still below it). That makes
`fractal_high` None for tickers at new highs (IONQ, AAPL). The SMC widget
needs a *level* to render, so when no unbroken Williams fractal exists,
we fall back to the 20-day rolling max(high). Same for fractal_low.

The 2026 FOMC dates are hardcoded — they're rate-decision announcement days.
This avoids any new data dependency (per the no-new-paid-licenses rule in
CLAUDE.md). Update FOMC_DATES_2026 / 2027 annually.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


# FOMC rate-decision announcement dates (publicly published by the Fed)
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES_2025 = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
]
FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
FOMC_DATES = FOMC_DATES_2025 + FOMC_DATES_2026


def _to_date(s: str) -> date | None:
    if not s:
        return None
    try:
        # Accept 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


def _typical(b: dict) -> float:
    h = float(b.get("h") or b.get("high") or 0)
    l = float(b.get("l") or b.get("low") or 0)
    c = float(b.get("c") or b.get("close") or 0)
    return (h + l + c) / 3.0 if (h and l and c) else c


def _vol(b: dict) -> float:
    return float(b.get("v") or b.get("volume") or 0)


def _close(b: dict) -> float:
    return float(b.get("c") or b.get("close") or 0)


def _high(b: dict) -> float:
    return float(b.get("h") or b.get("high") or 0)


def _low(b: dict) -> float:
    return float(b.get("l") or b.get("low") or 0)


def _bar_date(b: dict) -> date | None:
    return _to_date(b.get("d") or b.get("date") or "")


def _vwap_from_anchor(bars: list[dict], anchor_idx: int) -> float | None:
    """Cumulative VWAP starting at anchor_idx (inclusive) through end of bars."""
    if anchor_idx < 0 or anchor_idx >= len(bars):
        return None
    sum_tpv = 0.0
    sum_vol = 0.0
    for b in bars[anchor_idx:]:
        v = _vol(b)
        if v <= 0:
            continue
        sum_tpv += _typical(b) * v
        sum_vol += v
    if sum_vol <= 0:
        return None
    return sum_tpv / sum_vol


def _rolling_vwap(bars: list[dict], window: int = 20) -> float | None:
    if len(bars) < 2:
        return None
    w = bars[-window:] if len(bars) >= window else bars
    sum_tpv = 0.0
    sum_vol = 0.0
    for b in w:
        v = _vol(b)
        if v <= 0:
            continue
        sum_tpv += _typical(b) * v
        sum_vol += v
    if sum_vol <= 0:
        return None
    return sum_tpv / sum_vol


def _find_anchor_idx_for_date(bars: list[dict], target: date) -> int | None:
    """Find the latest bar with date <= target (event-anchored start)."""
    if not target:
        return None
    best = None
    for i, b in enumerate(bars):
        d = _bar_date(b)
        if d and d <= target:
            best = i
    return best


def _last_past_earnings_date(earnings_history: Any) -> date | None:
    """Find the most recent earnings reportDate that is <= today."""
    if not isinstance(earnings_history, list) or not earnings_history:
        return None
    today = date.today()
    candidates = []
    for e in earnings_history:
        if not isinstance(e, dict):
            continue
        d = _to_date(e.get("reportDate") or e.get("date") or "")
        if d and d <= today:
            candidates.append(d)
    return max(candidates) if candidates else None


def _last_past_fomc_date(bars_last_date: date | None = None) -> date | None:
    """Most recent FOMC date <= today (or <= last bar date if provided)."""
    cutoff = bars_last_date or date.today()
    past = [_to_date(s) for s in FOMC_DATES]
    past = [d for d in past if d and d <= cutoff]
    return max(past) if past else None


def _round_or_none(v: float | None, digits: int = 2) -> float | None:
    if v is None or not isinstance(v, (int, float)) or math.isnan(v):
        return None
    return round(float(v), digits)


def compute_smc_levels(
    ohlcv: list[dict],
    earnings_history: list[dict] | None = None,
    *,
    window: int = 20,
    swing_lookback: int = 60,
) -> dict:
    """
    Compute VWAP/AVWAP/fractal level bundle from a list of daily bars.

    Parameters
    ----------
    ohlcv : list of {d, o, h, l, c, v} dicts (most recent last)
    earnings_history : list from EODHD-shaped earnings_history (newest first)
    window : rolling VWAP window (default 20)
    swing_lookback : bars to scan for most-recent swing low (default 60)

    Returns
    -------
    dict with keys: vwap (dict), fractal_high, fractal_low, fractal_signal
    """
    if not isinstance(ohlcv, list) or len(ohlcv) < 5:
        return {
            "vwap": {
                "vwap_20d": None, "avwap_swing_low": None,
                "avwap_er": None, "avwap_fomc": None,
                "vwap_band_upper": None, "vwap_band_lower": None,
                "above_vwap": None, "above_avwap": None,
            },
            "fractal_high": None,
            "fractal_low": None,
            "fractal_signal": None,
        }

    bars = ohlcv
    last_close = _close(bars[-1])
    last_date = _bar_date(bars[-1])

    # ── Rolling 20d VWAP ─────────────────────────────────────────────
    vwap_20d = _rolling_vwap(bars, window=window)

    # ── ±1σ band of (close − vwap_20d) over the same window ──────────
    band_upper = band_lower = None
    if vwap_20d is not None and len(bars) >= 5:
        w = bars[-window:] if len(bars) >= window else bars
        diffs = [_close(b) - vwap_20d for b in w if _close(b)]
        if diffs:
            mean = sum(diffs) / len(diffs)
            var = sum((x - mean) ** 2 for x in diffs) / len(diffs)
            sigma = math.sqrt(var)
            band_upper = vwap_20d + sigma
            band_lower = vwap_20d - sigma

    # ── Anchored VWAP from recent swing low ──────────────────────────
    lookback = min(swing_lookback, len(bars) - 1)
    avwap_swing_low = None
    if lookback > 1:
        recent = bars[-lookback:-1]  # exclude today (mirrors analysis._vwap)
        if recent:
            lo_idx_in_recent = min(range(len(recent)), key=lambda i: _low(recent[i]))
            anchor_idx = len(bars) - lookback + lo_idx_in_recent
            avwap_swing_low = _vwap_from_anchor(bars, anchor_idx)

    # ── Anchored VWAP from last past earnings date ───────────────────
    avwap_er = None
    er_date = _last_past_earnings_date(earnings_history)
    if er_date:
        er_idx = _find_anchor_idx_for_date(bars, er_date)
        if er_idx is not None and er_idx < len(bars) - 1:
            avwap_er = _vwap_from_anchor(bars, er_idx)

    # ── Anchored VWAP from last past FOMC date ───────────────────────
    avwap_fomc = None
    fomc_date = _last_past_fomc_date(last_date)
    if fomc_date:
        fomc_idx = _find_anchor_idx_for_date(bars, fomc_date)
        if fomc_idx is not None and fomc_idx < len(bars) - 1:
            avwap_fomc = _vwap_from_anchor(bars, fomc_idx)

    # ── Fractal levels: 20d rolling max(high) / min(low) ─────────────
    # (analysis.py uses unbroken Williams fractals → None when at new highs;
    #  for the SMC widget we always want a *level* to render, so we use the
    #  simpler rolling-extreme definition. Matches the widget's bars_daily
    #  fallback formula already in redesign.html.)
    w_frac = bars[-window:] if len(bars) >= window else bars
    highs = [_high(b) for b in w_frac if _high(b)]
    lows = [_low(b) for b in w_frac if _low(b)]
    fractal_high = max(highs) if highs else None
    fractal_low = min(lows) if lows else None

    # ── Fractal signal note ──────────────────────────────────────────
    frac_signal = None
    if fractal_high and fractal_low and last_close:
        if last_close >= fractal_high * 0.995:
            frac_signal = f"At {window}d high ${round(fractal_high,2)}"
        elif last_close <= fractal_low * 1.005:
            frac_signal = f"At {window}d low ${round(fractal_low,2)}"
        else:
            frac_signal = f"In range ${round(fractal_low,2)}–${round(fractal_high,2)}"

    return {
        "vwap": {
            "vwap_20d":        _round_or_none(vwap_20d),
            "avwap_swing_low": _round_or_none(avwap_swing_low),
            "avwap_er":        _round_or_none(avwap_er),
            "avwap_fomc":      _round_or_none(avwap_fomc),
            "vwap_band_upper": _round_or_none(band_upper),
            "vwap_band_lower": _round_or_none(band_lower),
            "above_vwap":      bool(last_close > vwap_20d) if vwap_20d else None,
            "above_avwap":     bool(last_close > avwap_swing_low) if avwap_swing_low else None,
            "er_anchor_date":  er_date.isoformat() if er_date else None,
            "fomc_anchor_date": fomc_date.isoformat() if fomc_date else None,
        },
        "fractal_high":   _round_or_none(fractal_high),
        "fractal_low":    _round_or_none(fractal_low),
        "fractal_signal": frac_signal,
    }


# ════════════════════════════════════════════════════════════════════════
# SMC ZONE DETECTORS — Order Blocks, FVGs, BSL/SSL liquidity, Breakers
# ════════════════════════════════════════════════════════════════════════
# All detectors take the same `ohlcv` list (~60-90 daily bars; most recent
# last) and return list[dict] suitable for `t.smc_data.<kind>` consumption.
#
# Discipline notes (CLAUDE.md principles 1, 2, 7, 20):
#   • Mechanism comments per detector — no "this just works"
#   • Synthetic regime hit-rates / Wilson LB are flagged `n_synth: True`
#   • Heuristic thresholds (1.5×ATR impulse, 0.3% equal-high tolerance,
#     etc.) are GUESSES — documented as such, not pretended-tuned
#   • Insufficient bars (< 20) ⇒ empty list, NOT synthesized data
# ════════════════════════════════════════════════════════════════════════

# Heuristic thresholds (untuned guesses — pending A/B against future
# real SMC backtest data). Document, don't pretend these are evidence-based.
_OB_IMPULSE_BARS = 3              # impulse length after potential OB
_OB_IMPULSE_ATR_MULT = 1.5        # cumulative impulse must exceed N×ATR
_OB_LOOKBACK = 60                 # daily bars to scan
_FVG_LOOKBACK = 60
_LIQ_LOOKBACK = 20                # equal-highs/lows sliding window
_LIQ_TOLERANCE_PCT = 0.003        # 0.3% — "equal" highs/lows cluster width
_PIVOT_NEIGHBOR_BARS = 2          # swing high/low neighbor count

# Synthetic research-backed regime hit-rates (institutional SMC literature
# average; NOT calibrated to our backtest). Flagged `n_synth: True` so the
# widget renders the [synth] chip per convention.
_OB_REGIME_HITRATES = {
    "bull": {"trending": 76, "choppy": 68, "risk_off": 52, "panic": 34},
    "bear": {"trending": 42, "choppy": 58, "risk_off": 71, "panic": 79},
}
_OB_WILSON_LB = {"bull": 64, "bear": 56}  # synth — placeholder until backtest
_BREAKER_REGIME_HITRATES = {
    "trending": 78, "choppy": 74, "risk_off": 62, "panic": 51,
}
_BREAKER_WILSON_LB = 57           # synth — support-becomes-resistance lit ~57%


def _ohlcv_arrays(bars: list[dict]) -> dict:
    """Materialize parallel arrays for fast scans. Skips missing rows."""
    opens, highs, lows, closes, vols, dates = [], [], [], [], [], []
    for b in bars:
        o = float(b.get("o") or b.get("open") or 0)
        h = _high(b)
        l = _low(b)
        c = _close(b)
        v = _vol(b)
        d = _bar_date(b)
        if not (h and l and c and d):
            continue
        opens.append(o or c)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        vols.append(v)
        dates.append(d)
    return {"o": opens, "h": highs, "l": lows, "c": closes, "v": vols, "d": dates}


def _atr_simple(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Wilder-ish ATR using simple-moving-average of TR (good enough for zone scoring)."""
    if len(closes) < 2:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if not trs:
        return 0.0
    tail = trs[-period:]
    return sum(tail) / max(len(tail), 1)


def _find_pivots(highs: list, lows: list, neighbors: int = 2) -> tuple[list[int], list[int]]:
    """Return (pivot_high_indices, pivot_low_indices) — strict > / < neighbors."""
    n = len(highs)
    ph, pl = [], []
    for i in range(neighbors, n - neighbors):
        is_ph = all(highs[i] > highs[i - k] for k in range(1, neighbors + 1)) and \
                all(highs[i] > highs[i + k] for k in range(1, neighbors + 1))
        is_pl = all(lows[i] < lows[i - k] for k in range(1, neighbors + 1)) and \
                all(lows[i] < lows[i + k] for k in range(1, neighbors + 1))
        if is_ph:
            ph.append(i)
        if is_pl:
            pl.append(i)
    return ph, pl


def _round_box(lo: float, hi: float) -> tuple[float, float]:
    """Ensure lo ≤ hi, round to 2dp."""
    if lo > hi:
        lo, hi = hi, lo
    return round(lo, 2), round(hi, 2)


def _pct_vs_spot(mid: float, spot: float) -> float:
    if not spot:
        return 0.0
    return round(((mid - spot) / spot) * 100, 2)


def _detect_order_blocks(
    bars: list[dict],
    spot: float,
    vwap_dict: dict | None = None,
    fractal_dict: dict | None = None,
    ema21: float | None = None,
) -> list[dict]:
    """
    Order Blocks — last opposing candle before an impulse move.

    Mechanism: institutional limit orders absorb supply at the candle that
    "anchored" the move. On revisit, the same flow re-engages — until the
    zone is consumed (status progresses fresh → tested-held → fully-mit
    → breached).

    Bullish OB: last RED candle before ≥3 green candles whose cumulative
    range > 1.5×ATR. Zone = [low, max(open, close)].
    Bearish OB: mirror.
    """
    if len(bars) < _OB_IMPULSE_BARS + 5:
        return []
    arr = _ohlcv_arrays(bars)
    if len(arr["c"]) < _OB_IMPULSE_BARS + 5:
        return []

    opens, highs, lows, closes, vols, dates = arr["o"], arr["h"], arr["l"], arr["c"], arr["v"], arr["d"]
    n = len(closes)
    start = max(0, n - _OB_LOOKBACK)
    atr = _atr_simple(highs, lows, closes, period=14) or (sum(highs[-14:]) - sum(lows[-14:])) / 14
    if atr <= 0:
        return []

    # 20-day rolling avg volume for HVN-proxy confluence
    vol_window = vols[-20:] if len(vols) >= 20 else vols
    avg_vol = sum(vol_window) / max(len(vol_window), 1) if vol_window else 0

    raw: list[dict] = []
    # Scan candles that have at least IMPULSE_BARS bars after them
    for i in range(start, n - _OB_IMPULSE_BARS):
        # Check next IMPULSE_BARS for impulse direction + magnitude
        imp_lo = i + 1
        imp_hi = i + _OB_IMPULSE_BARS
        imp_closes = closes[imp_lo:imp_hi + 1]
        imp_opens = opens[imp_lo:imp_hi + 1]
        if len(imp_closes) < _OB_IMPULSE_BARS:
            continue
        all_up = all(imp_closes[k] > imp_opens[k] for k in range(len(imp_closes)))
        all_down = all(imp_closes[k] < imp_opens[k] for k in range(len(imp_closes)))
        if not (all_up or all_down):
            continue
        impulse_move = closes[imp_hi] - closes[i]
        if abs(impulse_move) < _OB_IMPULSE_ATR_MULT * atr:
            continue
        # Bullish OB
        if all_up and closes[i] < opens[i]:
            zone_lo, zone_hi = _round_box(lows[i], max(opens[i], closes[i]))
            kind = "bull"
        elif all_down and closes[i] > opens[i]:
            zone_lo, zone_hi = _round_box(min(opens[i], closes[i]), highs[i])
            kind = "bear"
        else:
            continue
        if zone_hi <= 0 or zone_lo <= 0:
            continue

        # Status — scan bars AFTER the impulse for tests
        status = "fresh"
        scan_from = imp_hi + 1
        mid = (zone_lo + zone_hi) / 2.0
        partial_seen = False
        for j in range(scan_from, n):
            bh, bl, bc = highs[j], lows[j], closes[j]
            # Touch detection (low entered zone for bull, high entered for bear)
            touched = (kind == "bull" and bl <= zone_hi and bh >= zone_lo) or \
                      (kind == "bear" and bh >= zone_lo and bl <= zone_hi)
            if not touched:
                continue
            # For bull: closed back ABOVE zone_hi = held; below mid = fully-mit; below lo = breached
            # For bear: mirror
            if kind == "bull":
                if bc < zone_lo:
                    status = "breached"
                    break
                elif bc < mid:
                    status = "fully-mit"
                elif bc < zone_hi:
                    if not partial_seen:
                        status = "partial-mit"
                        partial_seen = True
                else:
                    if status == "fresh":
                        status = "tested-held"
            else:  # bear
                if bc > zone_hi:
                    status = "breached"
                    break
                elif bc > mid:
                    status = "fully-mit"
                elif bc > zone_lo:
                    if not partial_seen:
                        status = "partial-mit"
                        partial_seen = True
                else:
                    if status == "fresh":
                        status = "tested-held"

        # Confluence scoring (0-5)
        score = 0
        tags = []
        if fractal_dict:
            fh = fractal_dict.get("fractal_high")
            fl = fractal_dict.get("fractal_low")
            if (fl and zone_lo <= fl <= zone_hi) or (fh and zone_lo <= fh <= zone_hi):
                score += 1
                tags.append("FRAC")
        if vwap_dict:
            vbl = vwap_dict.get("vwap_band_lower")
            vbu = vwap_dict.get("vwap_band_upper")
            if (vbl and abs(mid - vbl) / mid < 0.02) or (vbu and abs(mid - vbu) / mid < 0.02):
                score += 1
                tags.append("VWAP")
            for aw_key in ("avwap_swing_low", "avwap_er", "avwap_fomc"):
                aw = vwap_dict.get(aw_key)
                if aw and abs(mid - aw) / mid < 0.02:
                    score += 1
                    tags.append("AVWAP")
                    break
        # HVN proxy: formation bar volume > 1.5× 20d avg
        formation_vol_x = (vols[i] / avg_vol) if avg_vol > 0 else 0
        if formation_vol_x >= 1.5:
            score += 1
            tags.append("HVN")
        # EMA21 proximity
        if ema21 and ema21 > 0 and abs(mid - ema21) / mid < 0.03:
            score += 1
            tags.append("EMA21")
        score = min(score, 5)

        hr = _OB_REGIME_HITRATES[kind]
        raw.append({
            "low": zone_lo,
            "high": zone_hi,
            "kind": kind,
            "date": dates[i].isoformat(),
            "status": status,
            "vs_spot_pct": _pct_vs_spot(mid, spot),
            "confluence_score": score,
            "confluence_tags": tags,
            "formation_volume_x": round(formation_vol_x, 2),
            "regime_hit_rates": dict(hr),
            "wilson_lb": _OB_WILSON_LB[kind],
            "n": 0,  # explicit: no live sample yet
            "n_synth": True,
            # Internal scoring fields (for ranking; widget ignores these)
            "_mid": mid,
            "_age_idx": n - 1 - i,
            "_breached": status == "breached",
        })

    # Split breached → reserve for breaker detector; active → top 8 by score
    active = [r for r in raw if not r["_breached"]]
    # Rank: recency (lower age better) × confluence × inverse proximity
    def _rank(r):
        recency = 1.0 / (1 + r["_age_idx"] / 30.0)
        confl = 1 + r["confluence_score"]
        prox = 1.0 / (1 + abs(r["vs_spot_pct"]) / 5.0)
        return recency * confl * prox
    active.sort(key=_rank, reverse=True)
    out = active[:8]
    # Strip internal fields before returning
    for r in out:
        r.pop("_mid", None)
        r.pop("_age_idx", None)
        r.pop("_breached", None)
    return out


def _detect_fvgs(bars: list[dict], spot: float) -> list[dict]:
    """
    Fair Value Gap — 3-candle imbalance where candle 1's wick doesn't
    overlap candle 3's wick. Candle 2's body fills the void.

    Mechanism: fast-fill price-discovery zones; markets tend to revisit
    untraded prices ("inefficiency mean-reversion").

    Bullish FVG: c1.high < c3.low → gap [c1.high, c3.low].
    Bearish FVG: c1.low > c3.high → gap [c3.high, c1.low].
    """
    if len(bars) < 5:
        return []
    arr = _ohlcv_arrays(bars)
    highs, lows, closes, dates = arr["h"], arr["l"], arr["c"], arr["d"]
    n = len(closes)
    if n < 5:
        return []
    start = max(0, n - _FVG_LOOKBACK)
    raw: list[dict] = []
    for i in range(start, n - 2):
        c1_hi, c1_lo = highs[i], lows[i]
        c3_hi, c3_lo = highs[i + 2], lows[i + 2]
        kind = None
        zone_lo = zone_hi = None
        if c1_hi < c3_lo:
            kind = "bull"
            zone_lo, zone_hi = c1_hi, c3_lo
        elif c1_lo > c3_hi:
            kind = "bear"
            zone_lo, zone_hi = c3_hi, c1_lo
        else:
            continue
        zone_lo, zone_hi = _round_box(zone_lo, zone_hi)
        if zone_hi - zone_lo < 0.01:
            continue
        # Fill detection: any later bar wicked into the zone
        fill_date = None
        status = "unfilled"
        formation_idx = i + 1  # candle 2 is the formation bar
        for j in range(i + 3, n):
            bh, bl = highs[j], lows[j]
            if bh >= zone_lo and bl <= zone_hi:
                fill_date = dates[j].isoformat()
                status = "filled"
                break
        mid = (zone_lo + zone_hi) / 2.0
        raw.append({
            "low": zone_lo,
            "high": zone_hi,
            "kind": kind,
            "date": dates[formation_idx].isoformat(),
            "status": status,
            "fill_date": fill_date,
            "vs_spot_pct": _pct_vs_spot(mid, spot),
            "_age_idx": n - 1 - formation_idx,
            "_unfilled": status == "unfilled",
        })

    # Sort: unfilled first, then by recency
    raw.sort(key=lambda r: (not r["_unfilled"], r["_age_idx"]))
    out = raw[:6]
    for r in out:
        r.pop("_age_idx", None)
        r.pop("_unfilled", None)
    return out


def _detect_liquidity(bars: list[dict], spot: float) -> list[dict]:
    """
    BSL / SSL liquidity — stops cluster above equal highs (BSL) / below
    equal lows (SSL). HFT algos hunt these for fills.

    Mechanism: retail breakout stops + protective shorts cluster within
    a tight band of obvious pivots. Institutional flow targets these for
    cheap fills, then often reverses.

    Detection:
      • Find pivot highs/lows over the lookback window
      • Cluster any two pivots within _LIQ_TOLERANCE_PCT (0.3%)
      • Status: swept if a later bar's high (BSL) or low (SSL) breached
        the cluster price; sweep_type = clean (close beyond) / partial (wick only)
    """
    if len(bars) < 10:
        return []
    arr = _ohlcv_arrays(bars)
    highs, lows, closes, dates = arr["h"], arr["l"], arr["c"], arr["d"]
    n = len(closes)
    if n < 10:
        return []
    start = max(0, n - 90)  # widen lookback for sweep history
    sub_highs = highs[start:]
    sub_lows = lows[start:]
    sub_closes = closes[start:]
    sub_dates = dates[start:]
    ph, pl = _find_pivots(sub_highs, sub_lows, neighbors=_PIVOT_NEIGHBOR_BARS)

    def _cluster(pivot_idxs: list[int], prices: list[float], kind: str) -> list[dict]:
        clusters = []
        used = set()
        for ai, a in enumerate(pivot_idxs):
            if a in used:
                continue
            members = [a]
            ap = prices[a]
            for b in pivot_idxs[ai + 1:]:
                if abs(prices[b] - ap) / max(ap, 0.01) <= _LIQ_TOLERANCE_PCT:
                    members.append(b)
            if len(members) >= 2:
                for m in members:
                    used.add(m)
                avg_price = sum(prices[m] for m in members) / len(members)
                first_idx = min(members)
                last_idx = max(members)
                clusters.append({
                    "kind": kind,
                    "price": round(avg_price, 2),
                    "_first_idx": first_idx,
                    "_last_idx": last_idx,
                    "_n_pivots": len(members),
                })
        return clusters

    bsl_clusters = _cluster(ph, sub_highs, "BSL")
    ssl_clusters = _cluster(pl, sub_lows, "SSL")

    # Status: scan bars after _last_idx for sweep
    def _resolve_status(cl: dict) -> dict:
        kind = cl["kind"]
        price = cl["price"]
        last_idx = cl["_last_idx"]
        cl["swept"] = False
        cl["swept_date"] = None
        cl["swept_time"] = None
        cl["sweep_type"] = None
        for j in range(last_idx + 1, len(sub_dates)):
            bh, bl, bc = sub_highs[j], sub_lows[j], sub_closes[j]
            if kind == "BSL" and bh >= price * 1.0005:
                cl["swept"] = True
                cl["swept_date"] = sub_dates[j].isoformat()
                cl["swept_time"] = sub_dates[j].isoformat()
                cl["sweep_type"] = "clean" if bc > price else "partial"
                break
            elif kind == "SSL" and bl <= price * 0.9995:
                cl["swept"] = True
                cl["swept_date"] = sub_dates[j].isoformat()
                cl["swept_time"] = sub_dates[j].isoformat()
                cl["sweep_type"] = "clean" if bc < price else "partial"
                break
        return cl

    bsl_clusters = [_resolve_status(c) for c in bsl_clusters]
    ssl_clusters = [_resolve_status(c) for c in ssl_clusters]

    # Sort by absolute distance to spot, label L1/L2/L3 per kind
    def _finalize(clusters: list[dict]) -> list[dict]:
        clusters.sort(key=lambda c: abs(c["price"] - spot))
        out = []
        for idx, c in enumerate(clusters[:3]):
            mid = c["price"]
            out.append({
                "kind": c["kind"],
                "level": f"L{idx + 1}",
                "price": c["price"],
                "vs_spot_pct": _pct_vs_spot(mid, spot),
                "swept": c["swept"],
                "swept_date": c["swept_date"],
                "swept_time": c["swept_time"],
                "sweep_type": c["sweep_type"],
                "n_pivots": c["_n_pivots"],
            })
        return out

    return _finalize(bsl_clusters) + _finalize(ssl_clusters)


def _detect_breakers(
    bars: list[dict],
    spot: float,
    vwap_dict: dict | None = None,
    fractal_dict: dict | None = None,
    ema21: float | None = None,
) -> list[dict]:
    """
    Breaker — OB that failed (price closed through, invalidating it).
    When price returns AND reclaims, the zone acts in the opposite role.

    Mechanism: "support becomes resistance" (or reverse). The original
    institutional flow at the zone was overwhelmed; on reclaim, the
    opposite-side participants are now defending the zone.

    Workflow:
      1. Scan for OB candidates (same impulse rule as _detect_order_blocks)
      2. Identify those that broke (status='breached')
      3. Check if price has since RECLAIMED — closed back above (for
         broken bull OB) or below (for broken bear OB)
      4. Active breaker = broken AND reclaimed
    """
    if len(bars) < _OB_IMPULSE_BARS + 5:
        return []
    arr = _ohlcv_arrays(bars)
    if len(arr["c"]) < _OB_IMPULSE_BARS + 5:
        return []
    opens, highs, lows, closes, vols, dates = arr["o"], arr["h"], arr["l"], arr["c"], arr["v"], arr["d"]
    n = len(closes)
    start = max(0, n - _OB_LOOKBACK)
    atr = _atr_simple(highs, lows, closes, period=14)
    if atr <= 0:
        return []

    breakers = []
    for i in range(start, n - _OB_IMPULSE_BARS):
        imp_lo = i + 1
        imp_hi = i + _OB_IMPULSE_BARS
        imp_closes = closes[imp_lo:imp_hi + 1]
        imp_opens = opens[imp_lo:imp_hi + 1]
        if len(imp_closes) < _OB_IMPULSE_BARS:
            continue
        all_up = all(imp_closes[k] > imp_opens[k] for k in range(len(imp_closes)))
        all_down = all(imp_closes[k] < imp_opens[k] for k in range(len(imp_closes)))
        if not (all_up or all_down):
            continue
        impulse_move = closes[imp_hi] - closes[i]
        if abs(impulse_move) < _OB_IMPULSE_ATR_MULT * atr:
            continue
        if all_up and closes[i] < opens[i]:
            zone_lo, zone_hi = _round_box(lows[i], max(opens[i], closes[i]))
            kind = "bull"
        elif all_down and closes[i] > opens[i]:
            zone_lo, zone_hi = _round_box(min(opens[i], closes[i]), highs[i])
            kind = "bear"
        else:
            continue
        # Look for BREAK followed by RECLAIM
        break_idx = reclaim_idx = None
        for j in range(imp_hi + 1, n):
            bc = closes[j]
            if kind == "bull" and bc < zone_lo:
                break_idx = j
                # Now look for reclaim (close back above zone_lo)
                for k in range(j + 1, n):
                    if closes[k] > zone_lo:
                        reclaim_idx = k
                        break
                break
            elif kind == "bear" and bc > zone_hi:
                break_idx = j
                for k in range(j + 1, n):
                    if closes[k] < zone_hi:
                        reclaim_idx = k
                        break
                break
        if break_idx is None or reclaim_idx is None:
            continue
        # Active breaker — role inversion
        if kind == "bull":
            current_role = "SUPPORT (RECLAIMED)"
        else:
            current_role = "RESISTANCE (RECLAIMED)"
        mid = (zone_lo + zone_hi) / 2.0
        breakers.append({
            "low": zone_lo,
            "high": zone_hi,
            "original_date": dates[i].isoformat(),
            "break_date": dates[break_idx].isoformat(),
            "reclaim_date": dates[reclaim_idx].isoformat(),
            "current_role": current_role,
            "vs_spot_pct": _pct_vs_spot(mid, spot),
            "regime_hit_rates": dict(_BREAKER_REGIME_HITRATES),
            "wilson_lb": _BREAKER_WILSON_LB,
            "n": 0,
            "n_synth": True,
            "_reclaim_idx": reclaim_idx,
        })

    # Sort by recency of reclaim, top 3
    breakers.sort(key=lambda b: b["_reclaim_idx"], reverse=True)
    out = breakers[:3]
    for b in out:
        b.pop("_reclaim_idx", None)
    return out


def merge_smc_levels_into_ticker(ticker_entry: dict) -> dict:
    """
    Compute SMC levels for a ticker entry (in-place merge).
    Preserves any pre-existing vwap subkeys not produced by this module.
    Returns the updated entry.
    """
    if not isinstance(ticker_entry, dict):
        return ticker_entry
    ohlcv = ticker_entry.get("ohlcv")
    er_hist = ticker_entry.get("earnings_history")
    out = compute_smc_levels(ohlcv, er_hist)

    # Merge VWAP dict — keep existing keys, overlay new ones
    existing_vwap = ticker_entry.get("vwap") or {}
    if not isinstance(existing_vwap, dict):
        existing_vwap = {}
    merged_vwap = {**existing_vwap, **{k: v for k, v in out["vwap"].items() if v is not None}}
    # Ensure new structural keys exist even if None (so the widget can
    # distinguish "computed but empty" from "missing")
    for k in ("vwap_20d", "avwap_swing_low", "avwap_er", "avwap_fomc",
              "vwap_band_upper", "vwap_band_lower"):
        if k not in merged_vwap:
            merged_vwap[k] = out["vwap"][k]
    ticker_entry["vwap"] = merged_vwap

    # Fractals — only overwrite if current value is None (preserve any
    # upstream Williams fractal that was computed for BUY candidates)
    if ticker_entry.get("fractal_high") is None and out["fractal_high"] is not None:
        ticker_entry["fractal_high"] = out["fractal_high"]
    if ticker_entry.get("fractal_low") is None and out["fractal_low"] is not None:
        ticker_entry["fractal_low"] = out["fractal_low"]
    if ticker_entry.get("fractal_signal") is None and out["fractal_signal"]:
        ticker_entry["fractal_signal"] = out["fractal_signal"]

    # Also expose avwap_er/avwap_fomc at root for backward-compat widget paths
    if out["vwap"]["avwap_er"] is not None:
        ticker_entry["avwap_er"] = out["vwap"]["avwap_er"]
    if out["vwap"]["avwap_fomc"] is not None:
        ticker_entry["avwap_fomc"] = out["vwap"]["avwap_fomc"]

    # ── SMC ZONE DETECTION ───────────────────────────────────────────
    # Resolve current spot price from ticker payload (price ladder fallback)
    spot = float(
        ticker_entry.get("price")
        or ticker_entry.get("close")
        or ticker_entry.get("last_price")
        or (ohlcv[-1].get("c") if isinstance(ohlcv, list) and ohlcv else 0)
        or 0
    )
    if isinstance(ohlcv, list) and len(ohlcv) >= 20 and spot > 0:
        ema21 = ticker_entry.get("ema21")
        try:
            ema21 = float(ema21) if ema21 else None
        except Exception:
            ema21 = None
        vwap_for_score = ticker_entry.get("vwap") or {}
        fractal_for_score = {
            "fractal_high": ticker_entry.get("fractal_high"),
            "fractal_low": ticker_entry.get("fractal_low"),
        }
        try:
            obs = _detect_order_blocks(ohlcv, spot, vwap_for_score, fractal_for_score, ema21)
            fvgs = _detect_fvgs(ohlcv, spot)
            liq = _detect_liquidity(ohlcv, spot)
            brk = _detect_breakers(ohlcv, spot, vwap_for_score, fractal_for_score, ema21)
        except Exception:
            obs, fvgs, liq, brk = [], [], [], []
        existing_smc = ticker_entry.get("smc_data") or {}
        if not isinstance(existing_smc, dict):
            existing_smc = {}
        existing_smc.update({
            "order_blocks": obs,
            "fvgs": fvgs,
            "liquidity": liq,
            "breakers": brk,
        })
        ticker_entry["smc_data"] = existing_smc

    return ticker_entry
