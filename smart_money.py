"""
smart_money.py — Smart Money Concepts (SMC) signal engine for SwingTrade.

Implements four core SMC building blocks:
  1. Order Blocks (OB)      — institutional supply/demand zones
  2. Fair Value Gaps (FVG)  — imbalance zones price tends to fill
  3. Liquidity Sweeps       — stop-hunt detection above/below equal highs/lows
  4. Break of Structure / Change of Character (BOS / CHoCH)

All functions accept a pandas DataFrame with columns:
  Open, High, Low, Close, Volume  (capitalised, as returned by yfinance)

Entry point: score_smc(df, price, indicators) → composite dict used by analysis.py
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("swingtrade.smart_money")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _squeeze(s: pd.Series) -> pd.Series:
    """Flatten a potential MultiIndex / DataFrame column to a plain Series."""
    if isinstance(s, pd.DataFrame):
        return s.iloc[:, 0]
    return s.squeeze() if hasattr(s, "squeeze") else s


def _safe_float(val) -> Optional[float]:
    """Return float or None on any conversion failure."""
    try:
        v = float(val)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _prep_df(df: pd.DataFrame, lookback: int) -> Optional[pd.DataFrame]:
    """
    Return the last `lookback` rows of df as a clean, reset-indexed DataFrame.
    Returns None when df is too short or missing required columns.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or not required.issubset(df.columns):
        return None
    sub = df.tail(lookback).copy()
    if len(sub) < 5:
        return None
    for col in required:
        sub[col] = _squeeze(sub[col])
    sub = sub.reset_index(drop=True)
    return sub


def _swing_highs_lows(df: pd.DataFrame, window: int = 5) -> tuple[list[int], list[int]]:
    """
    Identify swing-high and swing-low bar indices using a simple local-extremum
    check over ±`window` bars.

    Returns (swing_high_indices, swing_low_indices).
    """
    highs: list[int] = []
    lows: list[int] = []
    n = len(df)
    for i in range(window, n - window):
        h = float(df["High"].iloc[i])
        lo = float(df["Low"].iloc[i])
        # Swing high: highest point in surrounding window
        if h == df["High"].iloc[i - window: i + window + 1].max():
            highs.append(i)
        # Swing low: lowest point in surrounding window
        if lo == df["Low"].iloc[i - window: i + window + 1].min():
            lows.append(i)
    return highs, lows


# ─────────────────────────────────────────────────────────────────────────────
# Weekly resampling helper for higher-timeframe OB detection (2026-05-12)
# ─────────────────────────────────────────────────────────────────────────────

def _resample_weekly(df: pd.DataFrame) -> "pd.DataFrame | None":
    """Resample daily OHLCV to weekly bars (Fri-anchored).

    Returns weekly df with Open/High/Low/Close/Volume columns, or None if
    inputs aren't suitable (no DatetimeIndex, too few bars, etc.).

    Used by detect_weekly_order_blocks() to give an institutional-timeframe
    OB read alongside the daily one. Weekly OBs carry materially more weight
    for position/invest-horizon decisions.
    """
    try:
        if df is None or len(df) < 30:
            return None
        # Try to ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            for col in ("Date", "date", "Datetime", "datetime"):
                if col in df.columns:
                    df = df.set_index(pd.to_datetime(df[col]))
                    break
            else:
                # If no date column, fabricate a synthetic daily index ending today
                df = df.copy()
                df.index = pd.date_range(end=pd.Timestamp.today().normalize(),
                                         periods=len(df), freq="B")
        # Resample to Fri-anchored weekly bars
        agg = {"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}
        cols = [c for c in agg if c in df.columns]
        if len(cols) < 5:
            return None
        weekly = df[cols].resample("W-FRI").agg({c: agg[c] for c in cols}).dropna()
        return weekly if len(weekly) >= 8 else None
    except Exception:
        log.debug("_resample_weekly error", exc_info=True)
        return None


def detect_weekly_order_blocks(df: pd.DataFrame, lookback: int = 26) -> list[dict]:
    """Weekly-timeframe OB detection — 26-week (~6mo) lookback by default.

    Pure higher-timeframe wrapper over detect_order_blocks(). Weekly OBs are
    informational-only at this stage: they appear in T.smc.weekly_order_blocks
    for the dashboard to render but DO NOT mutate any scoring weights or trade
    plans (Principle 7 — knob changes require backtest validation; weekly OB
    impact on edge has not been Wilson-tested).

    Returns same shape as detect_order_blocks() with an added `timeframe: 'W'`
    field on each OB so consumers can distinguish weekly from daily.
    """
    try:
        weekly_df = _resample_weekly(df)
        if weekly_df is None:
            return []
        # Reuse the same daily detection logic on weekly bars
        weekly_obs = detect_order_blocks(weekly_df, lookback=min(lookback, len(weekly_df)))
        for ob in weekly_obs:
            ob["timeframe"] = "W"
            # bars_since on weekly = weeks; convert to approximate daily age for UI
            ob["weeks_since"] = ob.get("bars_since")
        return weekly_obs
    except Exception:
        log.debug("detect_weekly_order_blocks error", exc_info=True)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 1. Order Blocks
# ─────────────────────────────────────────────────────────────────────────────

def detect_order_blocks(df: pd.DataFrame, lookback: int = 100) -> list[dict]:
    """
    Detect bullish and bearish Order Blocks in the last `lookback` bars.

    Bullish OB : last bearish candle (close < open) that immediately precedes a
                 bullish impulse of ≥1 % within the next 1–3 bars.
    Bearish OB : last bullish candle (close > open) that immediately precedes a
                 bearish impulse of ≥1 % within the next 1–3 bars.

    Status:
      "fresh"     — price has not re-entered the OB zone since formation
      "tested"    — price touched the zone but closed outside
      "mitigated" — price closed inside the zone (zone consumed)

    Strength score = (volume_at_ob / avg_volume) × impulse_size_pct × freshness_decay
      freshness_decay = max(0.3, 1.0 − bars_since / 50)

    Returns a list of dicts.
    """
    try:
        sub = _prep_df(df, lookback)
        if sub is None:
            return []

        open_  = sub["Open"].values.astype(float)
        high   = sub["High"].values.astype(float)
        low    = sub["Low"].values.astype(float)
        close  = sub["Close"].values.astype(float)
        volume = sub["Volume"].values.astype(float)
        n      = len(sub)

        avg_vol = np.nanmean(volume) if np.nansum(volume) > 0 else 1.0
        if avg_vol <= 0:
            avg_vol = 1.0

        current_price = close[-1]
        blocks: list[dict] = []

        for i in range(n - 4):  # need at least 3 forward bars to check impulse
            ob_open  = open_[i]
            ob_close = close[i]
            ob_high  = high[i]
            ob_low   = low[i]
            ob_vol   = volume[i]

            is_bearish_candle = ob_close < ob_open   # candidate bullish OB
            is_bullish_candle = ob_close > ob_open   # candidate bearish OB

            if not (is_bearish_candle or is_bullish_candle):
                continue  # doji — skip

            # --- Check for impulse in next 1–3 bars ---
            impulse_found   = False
            impulse_size    = 0.0
            ob_type         = None

            for fwd in range(1, min(4, n - i)):
                fwd_close = close[i + fwd]
                fwd_open  = open_[i + fwd]
                if ob_open == 0:
                    continue
                move_pct = (fwd_close - ob_open) / abs(ob_open)

                if is_bearish_candle and move_pct >= 0.01:   # bullish impulse ≥1%
                    ob_type = "bullish"
                    impulse_size = move_pct
                    impulse_found = True
                    break
                if is_bullish_candle and move_pct <= -0.01:  # bearish impulse ≥1%
                    ob_type = "bearish"
                    impulse_size = abs(move_pct)
                    impulse_found = True
                    break

            if not impulse_found or ob_type is None:
                continue

            # --- Determine zone boundaries ---
            zone_high = ob_high
            zone_low  = ob_low

            # --- Status: scan subsequent bars for price interaction ---
            bars_since = n - 1 - i
            status = "fresh"
            for j in range(i + 1, n):
                j_high  = high[j]
                j_low   = low[j]
                j_close = close[j]

                entered_zone = j_low <= zone_high and j_high >= zone_low

                if entered_zone:
                    closed_inside = zone_low <= j_close <= zone_high
                    if closed_inside:
                        status = "mitigated"
                        break
                    else:
                        status = "tested"
                        # Don't break — a later bar might still mitigate

            # --- Strength score ---
            vol_ratio       = (ob_vol / avg_vol) if avg_vol > 0 else 1.0
            freshness_decay = max(0.3, 1.0 - bars_since / 50.0)
            strength_score  = round(vol_ratio * impulse_size * 100 * freshness_decay, 4)

            blocks.append({
                "type"          : ob_type,
                "index"         : int(i),
                "high"          : round(float(zone_high), 4),
                "low"           : round(float(zone_low),  4),
                "open"          : round(float(ob_open),   4),
                "close"         : round(float(ob_close),  4),
                "volume"        : round(float(ob_vol),    2),
                "impulse_size"  : round(float(impulse_size), 4),
                "freshness"     : round(float(freshness_decay), 4),
                "status"        : status,
                "strength_score": round(float(strength_score), 4),
                "price_level"   : round(float((zone_high + zone_low) / 2), 4),
                "bars_since"    : int(bars_since),
            })

        # Sort by strength descending
        blocks.sort(key=lambda x: x["strength_score"], reverse=True)
        return blocks

    except Exception:
        log.debug("detect_order_blocks error", exc_info=True)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fair Value Gaps
# ─────────────────────────────────────────────────────────────────────────────

def detect_fvg(df: pd.DataFrame, lookback: int = 60) -> list[dict]:
    """
    Detect Fair Value Gaps (FVG / imbalance zones) in the last `lookback` bars.

    3-candle pattern centred on candle i:
      Bullish FVG : df["High"].iloc[i-1]  <  df["Low"].iloc[i+1]
                    (gap between candle i-1 top and candle i+1 bottom)
      Bearish FVG : df["Low"].iloc[i-1]   >  df["High"].iloc[i+1]

    Size filter: gap must be ≥ 0.15 % of the reference price.

    Status:
      "open"    — current price has not entered the gap
      "partial" — price entered but has not fully filled
      "closed"  — price has filled through the entire gap

    Returns a list of dicts.
    """
    try:
        sub = _prep_df(df, lookback)
        if sub is None:
            return []

        high   = sub["High"].values.astype(float)
        low    = sub["Low"].values.astype(float)
        close  = sub["Close"].values.astype(float)
        n      = len(sub)
        current_price = close[-1]

        gaps: list[dict] = []

        for i in range(1, n - 1):
            # ---- Bullish FVG ----
            gap_bottom = high[i - 1]
            gap_top    = low[i + 1]
            if gap_bottom < gap_top:
                size_pct = (gap_top - gap_bottom) / gap_bottom if gap_bottom > 0 else 0
                if size_pct >= 0.0015:   # ≥0.15%
                    # Determine status from bars after formation
                    status     = "open"
                    age_bars   = n - 1 - i
                    for j in range(i + 2, n):
                        j_low   = low[j]
                        j_high  = high[j]
                        j_close = close[j]
                        entered = j_low <= gap_top and j_high >= gap_bottom
                        if entered:
                            # Fully closed: closed below gap_bottom
                            if j_close <= gap_bottom:
                                status = "closed"
                                break
                            else:
                                status = "partial"
                    gaps.append({
                        "type"    : "bullish",
                        "index"   : int(i),
                        "top"     : round(float(gap_top),    4),
                        "bottom"  : round(float(gap_bottom), 4),
                        "size_pct": round(float(size_pct),   6),
                        "status"  : status,
                        "age_bars": int(age_bars),
                    })

            # ---- Bearish FVG ----
            gap_top2    = low[i - 1]
            gap_bottom2 = high[i + 1]
            if gap_top2 > gap_bottom2:
                size_pct = (gap_top2 - gap_bottom2) / gap_top2 if gap_top2 > 0 else 0
                if size_pct >= 0.0015:
                    status     = "open"
                    age_bars   = n - 1 - i
                    for j in range(i + 2, n):
                        j_low   = low[j]
                        j_high  = high[j]
                        j_close = close[j]
                        entered = j_high >= gap_bottom2 and j_low <= gap_top2
                        if entered:
                            if j_close >= gap_top2:
                                status = "closed"
                                break
                            else:
                                status = "partial"
                    gaps.append({
                        "type"    : "bearish",
                        "index"   : int(i),
                        "top"     : round(float(gap_top2),    4),
                        "bottom"  : round(float(gap_bottom2), 4),
                        "size_pct": round(float(size_pct),    6),
                        "status"  : status,
                        "age_bars": int(age_bars),
                    })

        # Sort by size descending so the most significant gaps surface first
        gaps.sort(key=lambda x: x["size_pct"], reverse=True)
        return gaps

    except Exception:
        log.debug("detect_fvg error", exc_info=True)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Liquidity Sweeps
# ─────────────────────────────────────────────────────────────────────────────

def detect_liquidity_sweeps(df: pd.DataFrame, lookback: int = 60) -> list[dict]:
    """
    Detect liquidity sweeps (stop hunts) in the last `lookback` bars.

    Step 1 — Find equal highs / equal lows over the lookback window:
      Equal highs : 2+ swing highs within 0.15 % of each other.
      Equal lows  : 2+ swing lows  within 0.15 % of each other.

    Step 2 — Sweep detection (within the last 5 bars only for recency):
      High sweep : wick above equal-high level  AND  close below the level
                   → stop hunt of shorts / longs stopped out → bullish signal
      Low  sweep : wick below equal-low level   AND  close above the level
                   → stop hunt of longs / shorts stopped out → bullish (for longs)

    Returns a list of dicts.
    """
    try:
        sub = _prep_df(df, lookback)
        if sub is None:
            return []

        high   = sub["High"].values.astype(float)
        low    = sub["Low"].values.astype(float)
        close  = sub["Close"].values.astype(float)
        open_  = sub["Open"].values.astype(float)
        n      = len(sub)

        # --- Swing highs / lows (5-bar window) ---
        sh_idx, sl_idx = _swing_highs_lows(sub, window=5)

        # Only consider swing points from the first n-5 bars (leave last 5 for sweep check)
        sh_levels = [float(high[i]) for i in sh_idx if i < n - 5]
        sl_levels = [float(low[i])  for i in sl_idx if i < n - 5]

        EQ_TOL = 0.0015   # 0.15% tolerance for "equal" levels

        def cluster_levels(levels: list[float]) -> list[float]:
            """Merge levels within EQ_TOL into a single representative level."""
            if not levels:
                return []
            levels_s = sorted(levels)
            clusters: list[list[float]] = []
            cur = [levels_s[0]]
            for lv in levels_s[1:]:
                ref = cur[0]
                if ref > 0 and abs(lv - ref) / ref <= EQ_TOL:
                    cur.append(lv)
                else:
                    if len(cur) >= 2:
                        clusters.append(cur)
                    cur = [lv]
            if len(cur) >= 2:
                clusters.append(cur)
            return [float(np.mean(c)) for c in clusters]

        eq_highs = cluster_levels(sh_levels)
        eq_lows  = cluster_levels(sl_levels)

        sweeps: list[dict] = []
        recency_window = 5   # only report sweeps in last 5 bars

        for bar_idx in range(max(0, n - recency_window), n):
            h   = high[bar_idx]
            lo  = low[bar_idx]
            c   = close[bar_idx]
            o   = open_[bar_idx]
            bars_ago = (n - 1) - bar_idx

            # ---- High sweep (bullish signal — longs swept out, reversal likely) ----
            for level in eq_highs:
                if h > level and c < level:
                    wick_pct = (h - level) / level if level > 0 else 0
                    sweeps.append({
                        "type"          : "high_sweep",
                        "index"         : int(bar_idx),
                        "level"         : round(float(level), 4),
                        "wick_pct"      : round(float(wick_pct), 6),
                        "close_rejected": True,
                        "bars_ago"      : int(bars_ago),
                        "bullish_signal": True,   # rejection after sweep = long setup
                    })

            # ---- Low sweep (bullish signal — shorts swept, smart money absorbs) ----
            for level in eq_lows:
                if lo < level and c > level:
                    wick_pct = (level - lo) / level if level > 0 else 0
                    sweeps.append({
                        "type"          : "low_sweep",
                        "index"         : int(bar_idx),
                        "level"         : round(float(level), 4),
                        "wick_pct"      : round(float(wick_pct), 6),
                        "close_rejected": True,
                        "bars_ago"      : int(bars_ago),
                        "bullish_signal": True,
                    })

        # Sort most-recent first
        sweeps.sort(key=lambda x: x["bars_ago"])
        return sweeps

    except Exception:
        log.debug("detect_liquidity_sweeps error", exc_info=True)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Break of Structure / Change of Character
# ─────────────────────────────────────────────────────────────────────────────

def detect_bos_choch(df: pd.DataFrame, lookback: int = 40) -> dict:
    """
    Detect Break of Structure (BOS) and Change of Character (CHoCH) signals.

    Uses swing highs/lows identified over a 5-bar local-extremum window.
    Classifies the last two consecutive structures to label trend context:

      BOS bullish  — new higher high breaks above last swing high in a prior downtrend
      BOS bearish  — new lower low breaks below last swing low in a prior uptrend
      CHoCH bullish — after a series of lower lows, price prints a higher low (potential reversal)
      CHoCH bearish — after higher highs, price prints a lower high (warning sign)

    last_structure: "HH", "HL", "LH", or "LL"

    Returns a dict with boolean flags + recency metrics.
    """
    _default: dict = {
        "bos_bullish"   : False,
        "bos_bearish"   : False,
        "choch_bullish" : False,
        "choch_bearish" : False,
        "bos_bars_ago"  : None,
        "choch_bars_ago": None,
        "last_structure": None,
    }
    try:
        sub = _prep_df(df, lookback)
        if sub is None:
            return _default

        sh_idx, sl_idx = _swing_highs_lows(sub, window=5)

        if len(sh_idx) < 2 and len(sl_idx) < 2:
            return _default

        high  = sub["High"].values.astype(float)
        low   = sub["Low"].values.astype(float)
        n     = len(sub)

        # Build a combined, time-ordered list of swing points with their values
        swing_events: list[dict] = []
        for i in sh_idx:
            swing_events.append({"idx": i, "kind": "H", "val": float(high[i])})
        for i in sl_idx:
            swing_events.append({"idx": i, "kind": "L", "val": float(low[i])})
        swing_events.sort(key=lambda x: x["idx"])

        if len(swing_events) < 3:
            return _default

        # Separate swing highs and lows in order
        swing_highs_vals = [(e["idx"], e["val"]) for e in swing_events if e["kind"] == "H"]
        swing_lows_vals  = [(e["idx"], e["val"]) for e in swing_events if e["kind"] == "L"]

        result = dict(_default)

        # --- Analyse last two swing highs ---
        bos_bull_bars  = None
        choch_bear_bars = None
        if len(swing_highs_vals) >= 2:
            prev_hi_idx, prev_hi_val = swing_highs_vals[-2]
            last_hi_idx, last_hi_val = swing_highs_vals[-1]

            if last_hi_val > prev_hi_val:
                # Higher High — BOS bullish if we were in a down-structure
                result["bos_bullish"]  = True
                result["last_structure"] = "HH"
                bos_bull_bars = n - 1 - last_hi_idx
            else:
                # Lower High — CHoCH bearish warning
                result["choch_bearish"] = True
                result["last_structure"] = "LH"
                choch_bear_bars = n - 1 - last_hi_idx

        # --- Analyse last two swing lows ---
        bos_bear_bars   = None
        choch_bull_bars = None
        if len(swing_lows_vals) >= 2:
            prev_lo_idx, prev_lo_val = swing_lows_vals[-2]
            last_lo_idx, last_lo_val = swing_lows_vals[-1]

            if last_lo_val < prev_lo_val:
                # Lower Low — BOS bearish if prior trend was up
                result["bos_bearish"]  = True
                if result["last_structure"] is None:
                    result["last_structure"] = "LL"
                bos_bear_bars = n - 1 - last_lo_idx
            else:
                # Higher Low — CHoCH bullish (potential reversal after down-trend)
                result["choch_bullish"] = True
                if result["last_structure"] is None:
                    result["last_structure"] = "HL"
                choch_bull_bars = n - 1 - last_lo_idx

        # Combine BOS bars_ago (take the most recent BOS signal)
        bos_options   = [v for v in [bos_bull_bars, bos_bear_bars]   if v is not None]
        choch_options = [v for v in [choch_bear_bars, choch_bull_bars] if v is not None]
        result["bos_bars_ago"]   = int(min(bos_options))   if bos_options   else None
        result["choch_bars_ago"] = int(min(choch_options)) if choch_options else None

        return result

    except Exception:
        log.debug("detect_bos_choch error", exc_info=True)
        return _default


# ─────────────────────────────────────────────────────────────────────────────
# 5. Composite SMC Score
# ─────────────────────────────────────────────────────────────────────────────

_SMC_OB_CONFLUENCE_CFG: dict = {"v": None}


def _smc_ob_confluence_cfg() -> dict:
    """Cached loader for scoring.smc_ob_confluence (flag-gated OB confluence bonus)."""
    if _SMC_OB_CONFLUENCE_CFG["v"] is not None:
        return _SMC_OB_CONFLUENCE_CFG["v"]
    out = {"_enabled": False, "bos_bonus": 0.5, "fvg_bonus": 0.5,
           "max_bonus": 1.0, "require_both": False}
    try:
        import json as _j
        from pathlib import Path as _P
        _p = _P(__file__).resolve().parent / "config" / "config.json"
        blk = (_j.loads(_p.read_text()).get("scoring") or {}).get("smc_ob_confluence") or {}
        for k in out:
            if k in blk:
                out[k] = blk[k]
    except Exception:
        pass
    _SMC_OB_CONFLUENCE_CFG["v"] = out
    return out


def score_smc(df: pd.DataFrame, price: float, indicators: dict) -> dict:
    """
    Main entry point.  Calls all four SMC detectors and computes a composite
    score (max 5 pts) that can be added as a bonus to the Technicals pillar.

    Scoring:
      +1.5  BOS bullish (confirmed up-structure break)
      +1.5  Fresh bullish OB within 3% below current price (strongest entry signal)
      +0.5  Open bullish FVG within 5% above price (price target zone)
      +1.0  Liquidity sweep (high or low) within last 3 bars
      −1.0  CHoCH bearish (structural deterioration warning for longs)
      −0.5  Bearish OB overhead within 2% above price (resistance)

    Additional outputs for trade planning:
      ob_entry_zone : {low, high} of nearest fresh bullish OB within 3% below price
                      (caller can use this to replace ATR-based entry zone)
      ob_stop       : OB low − 0.1% buffer  (replaces ATR-based stop)
      fvg_target    : top of nearest open bullish FVG above price
      smc_direction : "bullish" | "bearish" | "neutral"

    Parameters
    ----------
    df         : OHLCV DataFrame
    price      : current price (float)
    indicators : dict of pre-computed indicators from analysis.py (unused in
                 the core logic but reserved for future confluence checks)

    Returns
    -------
    Full result dict — safe defaults returned on any error.
    """
    _default: dict = {
        "score"           : 0.0,
        "order_blocks"    : [],
        "fvg_zones"       : [],
        "liquidity_sweeps": [],
        "bos_choch"       : {
            "bos_bullish": False, "bos_bearish": False,
            "choch_bullish": False, "choch_bearish": False,
            "bos_bars_ago": None, "choch_bars_ago": None,
            "last_structure": None,
        },
        "ob_entry_zone"   : None,
        "ob_stop"         : None,
        "fvg_target"      : None,
        "smc_direction"   : "neutral",
        "ob_confluence"   : {"has_ob": False, "bos_confirmed": False,
                             "fvg_confirmed": False, "factors": [], "bonus_applied": 0.0},
        "details"         : {},
        "weekly_order_blocks": [],
    }

    try:
        if df is None or len(df) < 10:
            return _default

        price = _safe_float(price)
        if price is None or price <= 0:
            return _default

        # ── Run all four detectors ────────────────────────────────────────────
        order_blocks     = detect_order_blocks(df,  lookback=100)
        fvg_zones        = detect_fvg(df,           lookback=60)
        liquidity_sweeps = detect_liquidity_sweeps(df, lookback=60)
        bos_choch        = detect_bos_choch(df,     lookback=40)
        # 2026-05-12 — Higher-timeframe OB layer. Informational only at this
        # stage (does NOT enter the score below). Weekly OBs are the level
        # institutional desks actually track; surfacing them in the data lets
        # the dashboard show MTF confluence without changing live scoring.
        # If Wilson backtest later proves weekly-OB-confluence boosts edge,
        # then-and-only-then add to the score per Principle 7.
        weekly_order_blocks = detect_weekly_order_blocks(df, lookback=26)

        score        = 0.0
        details: dict = {}

        # ── BOS bullish  +1.5 ────────────────────────────────────────────────
        if bos_choch.get("bos_bullish"):
            score += 1.5
            details["bos_bullish"] = f"+1.5 | BOS bullish (bars ago: {bos_choch.get('bos_bars_ago')})"

        # ── Fresh bullish OB within 3% below price  +1.5 ────────────────────
        ob_entry_zone: Optional[dict] = None
        ob_stop: Optional[float]      = None
        best_ob_score = -1.0

        for ob in order_blocks:
            if ob["type"] != "bullish":
                continue
            if ob["status"] == "mitigated":
                continue   # consumed zone, no edge
            ob_mid = ob["price_level"]
            # Must be within 3% below current price
            if ob_mid <= price and (price - ob_mid) / price <= 0.03:
                if ob["strength_score"] > best_ob_score:
                    best_ob_score = ob["strength_score"]
                    ob_entry_zone = {"low": ob["low"], "high": ob["high"]}
                    ob_stop       = round(ob["low"] * (1.0 - 0.001), 4)  # OB low − 0.1%

        if ob_entry_zone is not None:
            score += 1.5
            details["bullish_ob_entry"] = (
                f"+1.5 | Fresh bullish OB @ {ob_entry_zone['low']:.2f}–"
                f"{ob_entry_zone['high']:.2f}"
            )

        # ── Open bullish FVG within 5% above price  +0.5 ────────────────────
        fvg_target: Optional[float] = None
        nearest_fvg_dist = float("inf")

        for fvg in fvg_zones:
            if fvg["type"] != "bullish":
                continue
            if fvg["status"] == "closed":
                continue
            fvg_bottom = fvg["bottom"]
            # FVG must be above current price and within 5%
            if fvg_bottom >= price and (fvg_bottom - price) / price <= 0.05:
                dist = fvg_bottom - price
                if dist < nearest_fvg_dist:
                    nearest_fvg_dist = dist
                    fvg_target = fvg["top"]

        if fvg_target is not None:
            score += 0.5
            details["bullish_fvg"] = f"+0.5 | Open bullish FVG target @ {fvg_target:.2f}"

        # ── BOS + FVG confluence on the fresh bullish OB (FLAG-GATED) ─────────
        # Thesis: a fresh bullish OB is higher-probability when the impulse that
        # formed it ALSO broke structure (BOS) and left a Fair Value Gap right off
        # the zone (displacement). Tags are ALWAYS computed (so the lens + the
        # validation harness can read them); the SCORE bonus is applied only when
        # scoring.smc_ob_confluence._enabled is true. Validate the Wilson-LB lift on
        # the OB∩BOS∩FVG intersection (n≥30, ≥5pp) via validate_ob_confluence.py
        # BEFORE enabling — Principle 7. 2026-06-13 baseline: parts negative, OFF.
        ob_confluence = {
            "has_ob": ob_entry_zone is not None,
            "bos_confirmed": bool(bos_choch.get("bos_bullish")),
            "fvg_confirmed": False,
            "factors": [], "bonus_applied": 0.0,
        }
        if ob_entry_zone is not None:
            # FVG-off-the-OB: an open bullish FVG whose gap sits between the OB high
            # and ~3% above price (the imbalance left by the displacement off the OB).
            _ob_hi = ob_entry_zone["high"]
            for fvg in fvg_zones:
                if fvg.get("type") != "bullish" or fvg.get("status") == "closed":
                    continue
                _fb = fvg.get("bottom")
                if _fb is not None and _ob_hi <= _fb <= price * 1.03:
                    ob_confluence["fvg_confirmed"] = True
                    break
            if ob_confluence["bos_confirmed"]:
                ob_confluence["factors"].append("BOS")
            if ob_confluence["fvg_confirmed"]:
                ob_confluence["factors"].append("FVG")
            _conf = _smc_ob_confluence_cfg()
            _ok = (len(ob_confluence["factors"]) == 2) if _conf.get("require_both") else bool(ob_confluence["factors"])
            if _conf.get("_enabled") and _ok:
                bonus = 0.0
                if "BOS" in ob_confluence["factors"]:
                    bonus += float(_conf.get("bos_bonus", 0.5))
                if "FVG" in ob_confluence["factors"]:
                    bonus += float(_conf.get("fvg_bonus", 0.5))
                bonus = min(bonus, float(_conf.get("max_bonus", 1.0)))
                score += bonus
                ob_confluence["bonus_applied"] = round(bonus, 4)
                details["ob_confluence"] = f"+{bonus:.2f} | OB confluence: {'+'.join(ob_confluence['factors'])}"

        # ── Liquidity sweep within last 3 bars  +1.0 ─────────────────────────
        recent_sweeps = [s for s in liquidity_sweeps if s.get("bars_ago", 99) <= 3]
        if recent_sweeps:
            score += 1.0
            sweep_types = list({s["type"] for s in recent_sweeps})
            details["liquidity_sweep"] = f"+1.0 | Sweep(s): {', '.join(sweep_types)}"

        # ── CHoCH bearish  −1.0 ───────────────────────────────────────────────
        if bos_choch.get("choch_bearish"):
            score -= 1.0
            details["choch_bearish"] = (
                f"-1.0 | CHoCH bearish (bars ago: {bos_choch.get('choch_bars_ago')})"
            )

        # ── Bearish OB overhead within 2%  −0.5 ──────────────────────────────
        for ob in order_blocks:
            if ob["type"] != "bearish":
                continue
            if ob["status"] == "mitigated":
                continue
            ob_mid = ob["price_level"]
            if ob_mid > price and (ob_mid - price) / price <= 0.02:
                score -= 0.5
                details["bearish_ob_overhead"] = (
                    f"-0.5 | Bearish OB overhead @ {ob_mid:.2f}"
                )
                break   # only penalise once

        # ── Direction label ───────────────────────────────────────────────────
        if score >= 1.5:
            smc_direction = "bullish"
        elif score <= -0.5:
            smc_direction = "bearish"
        else:
            smc_direction = "neutral"

        # Clamp score to a sensible range
        score = round(max(-2.0, min(5.0, score)), 4)

        return {
            "score"           : score,
            "order_blocks"    : order_blocks,
            "fvg_zones"       : fvg_zones,
            "liquidity_sweeps": liquidity_sweeps,
            "bos_choch"       : bos_choch,
            "ob_entry_zone"   : ob_entry_zone,
            "ob_stop"         : ob_stop,
            "fvg_target"      : fvg_target,
            "smc_direction"   : smc_direction,
            "ob_confluence"   : ob_confluence,
            "details"         : details,
            # 2026-05-12 — weekly OBs (informational, not scored — see comment
            # above near detect_weekly_order_blocks call)
            "weekly_order_blocks": weekly_order_blocks,
        }

    except Exception:
        log.debug("score_smc error", exc_info=True)
        return _default


# ─────────────────────────────────────────────────────────────────────────────
# 6. Multi-Timeframe SMC Matrix
# ─────────────────────────────────────────────────────────────────────────────

_TF_CONFIGS = {
    "30m": {"multiplier": 30, "timespan": "minute", "days": 15,  "pivot_window": 3},
    "1H":  {"multiplier": 1,  "timespan": "hour",   "days": 30,  "pivot_window": 3},
    "4H":  {"multiplier": 4,  "timespan": "hour",   "days": 60,  "pivot_window": 5},
    "1W":  {"multiplier": 1,  "timespan": "week",   "days": 730, "pivot_window": 5},
    "1M":  {"multiplier": 1,  "timespan": "week",   "days": 1825, "pivot_window": 5},
}

_TF_ORDER = ["30m", "1H", "4H", "1W", "1M"]


def _compute_momentum(df: pd.DataFrame) -> dict:
    """Compute momentum & flow indicators for a single timeframe DataFrame."""
    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    volume = df["Volume"].values.astype(float)
    n = len(close)

    result: dict = {}

    # ── EMA Signal ──
    if n >= 50:
        ema8 = pd.Series(close).ewm(span=8, adjust=False).mean().iloc[-1]
        ema21 = pd.Series(close).ewm(span=21, adjust=False).mean().iloc[-1]
        ema50 = pd.Series(close).ewm(span=50, adjust=False).mean().iloc[-1]
        if ema8 > ema21 > ema50:
            result["signal"] = "Strong Bullish"
        elif ema8 > ema21:
            result["signal"] = "Bullish"
        elif ema8 < ema21 < ema50:
            result["signal"] = "Strong Bearish"
        elif ema8 < ema21:
            result["signal"] = "Bearish"
        else:
            result["signal"] = "Neutral"
    elif n >= 21:
        ema8 = pd.Series(close).ewm(span=8, adjust=False).mean().iloc[-1]
        ema21 = pd.Series(close).ewm(span=21, adjust=False).mean().iloc[-1]
        result["signal"] = "Bullish" if ema8 > ema21 else "Bearish" if ema8 < ema21 else "Neutral"
    else:
        result["signal"] = "Neutral"

    # ── RSI(14) ──
    if n >= 15:
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_val = 100 - (100 / (1 + rs))
        result["rsi"] = round(float(rsi_val.iloc[-1]), 1) if not np.isnan(rsi_val.iloc[-1]) else 50.0
    else:
        result["rsi"] = 50.0

    # ── MACD(12,26,9) ──
    if n >= 35:
        s = pd.Series(close)
        ema12 = s.ewm(span=12, adjust=False).mean()
        ema26 = s.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        h_now = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])
        if h_now > 0 and h_now > h_prev:
            result["macd"] = "Bullish"
        elif h_now < 0 and h_now < h_prev:
            result["macd"] = "Bearish"
        elif h_now > h_prev:
            result["macd"] = "Turning Up"
        else:
            result["macd"] = "Turning Down"
    else:
        result["macd"] = "Neutral"

    # ── Squeeze (BB inside KC) ──
    if n >= 20:
        s = pd.Series(close)
        sma20 = s.rolling(20).mean()
        std20 = s.rolling(20).std()
        bb_upper = sma20 + 2.0 * std20
        bb_lower = sma20 - 2.0 * std20
        tr = pd.DataFrame({
            "hl": pd.Series(high) - pd.Series(low),
            "hc": abs(pd.Series(high) - s.shift(1)),
            "lc": abs(pd.Series(low) - s.shift(1)),
        }).max(axis=1)
        atr20 = tr.rolling(20).mean()
        kc_upper = sma20 + 1.5 * atr20
        kc_lower = sma20 - 1.5 * atr20
        squeeze_on = bool(bb_upper.iloc[-1] < kc_upper.iloc[-1] and bb_lower.iloc[-1] > kc_lower.iloc[-1])
        # Momentum direction from MACD histogram or linear regression
        mom_dir = "positive" if result.get("macd") in ("Bullish", "Turning Up") else "negative"
        if squeeze_on:
            result["squeeze"] = "on"
        else:
            # Check if squeeze just released (was on 1 bar ago)
            prev_squeeze = bool(bb_upper.iloc[-2] < kc_upper.iloc[-2] and bb_lower.iloc[-2] > kc_lower.iloc[-2])
            if prev_squeeze:
                result["squeeze"] = "firing"
            else:
                result["squeeze"] = "off"
        result["squeeze_momentum"] = mom_dir
    else:
        result["squeeze"] = "off"
        result["squeeze_momentum"] = "neutral"

    # ── CMF(20) — Money Flow ──
    if n >= 20:
        mfm = ((close - low) - (high - close)) / np.where(high - low == 0, 1, high - low)
        mfv = mfm * volume
        cmf = float(pd.Series(mfv).rolling(20).sum().iloc[-1] / pd.Series(volume).rolling(20).sum().iloc[-1])
        if np.isnan(cmf):
            cmf = 0.0
        result["money_flow"] = round(cmf, 4)
        result["money_flow_label"] = "Inflow" if cmf > 0.05 else "Outflow" if cmf < -0.05 else "Neutral"
    else:
        result["money_flow"] = 0.0
        result["money_flow_label"] = "Neutral"

    # ── RVOL — Volume Sentiment ──
    if n >= 20:
        vol_sma = float(pd.Series(volume).rolling(20).mean().iloc[-1])
        rvol = float(volume[-1] / vol_sma) if vol_sma > 0 else 1.0
        result["rvol"] = round(rvol, 2)
        result["volume_sentiment"] = "High" if rvol > 1.5 else "Low" if rvol < 0.7 else "Normal"
    else:
        result["rvol"] = 1.0
        result["volume_sentiment"] = "Normal"

    # ── RSI Divergence ──
    result["divergence"] = "None"
    if n >= 30:
        rsi_series = pd.Series(close).diff()
        gain = rsi_series.clip(lower=0).rolling(14).mean()
        loss = (-rsi_series.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_s = 100 - (100 / (1 + rs))
        rsi_vals = rsi_s.values

        sub_df = pd.DataFrame({"High": high, "Low": low, "Close": close})
        sh_idx, sl_idx = _swing_highs_lows(sub_df, window=3)

        # Bearish divergence: higher price high, lower RSI high
        if len(sh_idx) >= 2:
            i1, i2 = sh_idx[-2], sh_idx[-1]
            if high[i2] > high[i1] and rsi_vals[i2] < rsi_vals[i1]:
                result["divergence"] = "Bearish Div"

        # Bullish divergence: lower price low, higher RSI low
        if result["divergence"] == "None" and len(sl_idx) >= 2:
            i1, i2 = sl_idx[-2], sl_idx[-1]
            if low[i2] < low[i1] and rsi_vals[i2] > rsi_vals[i1]:
                result["divergence"] = "Bullish Div"

    # ── ADX(14) — Trend Strength ──
    if n >= 28:
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        tr_arr = np.zeros(n)
        for i in range(1, n):
            h_diff = high[i] - high[i - 1]
            l_diff = low[i - 1] - low[i]
            plus_dm[i] = h_diff if h_diff > l_diff and h_diff > 0 else 0
            minus_dm[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0
            tr_arr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        atr14 = pd.Series(tr_arr).rolling(14).mean()
        plus_di = 100 * pd.Series(plus_dm).rolling(14).mean() / atr14.replace(0, np.nan)
        minus_di = 100 * pd.Series(minus_dm).rolling(14).mean() / atr14.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()
        adx_val = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 20.0
        result["trend_strength"] = round(adx_val, 1)
        result["trend_strength_label"] = "Strong" if adx_val > 25 else "Weak" if adx_val < 20 else "Moderate"
    else:
        result["trend_strength"] = 20.0
        result["trend_strength_label"] = "Moderate"

    # ── Reversal candle patterns (last 3 bars) ──
    result["reversals"] = "None"
    if n >= 3:
        o2, h2, l2, c2 = float(df["Open"].iloc[-2]), high[-2], low[-2], close[-2]
        o1, h1, l1, c1 = float(df["Open"].iloc[-1]), high[-1], low[-1], close[-1]
        body1 = abs(c1 - o1)
        body2 = abs(c2 - o2)
        # Bullish engulfing
        if c2 < o2 and c1 > o1 and c1 > o2 and o1 < c2 and body1 > body2:
            result["reversals"] = "Bullish Engulf"
        # Bearish engulfing
        elif c2 > o2 and c1 < o1 and c1 < o2 and o1 > c2 and body1 > body2:
            result["reversals"] = "Bearish Engulf"
        else:
            # Pin bar (hammer / shooting star)
            range1 = h1 - l1
            if range1 > 0:
                upper_wick = h1 - max(o1, c1)
                lower_wick = min(o1, c1) - l1
                if lower_wick > 2 * body1 and lower_wick > 0.6 * range1:
                    result["reversals"] = "Pin Bar Up"
                elif upper_wick > 2 * body1 and upper_wick > 0.6 * range1:
                    result["reversals"] = "Pin Bar Down"

    return result


def _compute_tf_row(df: pd.DataFrame, pivot_window: int, price: float) -> dict:
    """Compute a full row of the SMC MTF matrix for one timeframe."""
    if df is None or len(df) < 10:
        return {"error": "Insufficient data"}

    n = len(df)
    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)

    # ── SMC Structure detectors ──
    obs = detect_order_blocks(df, lookback=min(100, n))
    fvgs = detect_fvg(df, lookback=min(60, n))
    sweeps = detect_liquidity_sweeps(df, lookback=min(60, n))
    bos = detect_bos_choch(df, lookback=min(40, n))

    # ── Structure label ──
    if bos.get("bos_bullish") and bos.get("bos_bearish"):
        structure = "BOS" if bos["bos_bars_ago"] is not None else "Range"
        bos_count = 1
    elif bos.get("bos_bullish"):
        bos_count = 1
        structure = f"BOS ({bos_count})"
    elif bos.get("bos_bearish"):
        bos_count = 1
        structure = f"BOS ({bos_count})"
    elif bos.get("choch_bullish") or bos.get("choch_bearish"):
        structure = "CHoCH"
        bos_count = 0
    else:
        structure = "Range"
        bos_count = 0

    structure_direction = "bullish" if bos.get("bos_bullish") or bos.get("choch_bullish") else \
                          "bearish" if bos.get("bos_bearish") or bos.get("choch_bearish") else "neutral"

    # ── Order Block (nearest relevant) ──
    best_ob = None
    ob_status = "Outside"
    ob_volume = 0
    ob_level = None
    for ob in obs:
        if ob["status"] == "mitigated":
            continue
        zone_mid = ob["price_level"]
        if ob["low"] <= price <= ob["high"]:
            ob_status = "Inside"
            best_ob = ob
            break
        if best_ob is None or abs(zone_mid - price) < abs(best_ob["price_level"] - price):
            best_ob = ob
    if best_ob:
        ob_volume = best_ob["volume"]
        ob_level = best_ob["price_level"]
        if ob_status != "Inside":
            ob_status = "Outside"
    if any(ob["status"] == "mitigated" for ob in obs) and not best_ob:
        ob_status = "Mitigated"

    # ── FVG (most recent unfilled) ──
    fvg_label = "None"
    for fvg in fvgs:
        if fvg["status"] == "closed":
            continue
        fvg_label = "Bullish" if fvg["type"] == "bullish" else "Bearish"
        if fvg["status"] == "partial":
            fvg_label = "Mitigated"
        break
    if fvg_label == "None" and any(f["status"] in ("closed", "partial") for f in fvgs):
        fvg_label = "Mitigated"

    # ── Premium & Discount zones ──
    sh_idx, sl_idx = _swing_highs_lows(df, window=pivot_window)
    swing_high = max((high[i] for i in sh_idx), default=high[-1]) if sh_idx else float(high.max())
    swing_low = min((low[i] for i in sl_idx), default=low[-1]) if sl_idx else float(low.min())
    swing_range = swing_high - swing_low
    equilibrium = swing_low + swing_range * 0.5 if swing_range > 0 else price
    if price > equilibrium * 1.005:
        pg_zone = "Above Equilibrium"
    elif price < equilibrium * 0.995:
        pg_zone = "Below Equilibrium"
    else:
        pg_zone = "At Equilibrium"

    # ── Liquidity sweep ──
    recent_sweeps = [s for s in sweeps if s.get("bars_ago", 99) <= 5]
    if recent_sweeps:
        has_high_sweep = any(s["type"] == "high_sweep" for s in recent_sweeps)
        has_low_sweep = any(s["type"] == "low_sweep" for s in recent_sweeps)
        if has_high_sweep:
            liquidity = "Bearish"
        elif has_low_sweep:
            liquidity = "Bullish"
        else:
            liquidity = "None"
    else:
        liquidity = "None"

    # ── EQH/EQL ──
    EQ_TOL = 0.003
    sh_vals = [float(high[i]) for i in sh_idx] if sh_idx else []
    sl_vals = [float(low[i]) for i in sl_idx] if sl_idx else []

    def has_equal_levels(levels: list[float]) -> bool:
        if len(levels) < 2:
            return False
        levels_s = sorted(levels)
        for i in range(len(levels_s) - 1):
            if levels_s[i] > 0 and abs(levels_s[i + 1] - levels_s[i]) / levels_s[i] <= EQ_TOL:
                return True
        return False

    has_eqh = has_equal_levels(sh_vals)
    has_eql = has_equal_levels(sl_vals)
    if has_eqh and has_eql:
        eqhl = "Both"
    elif has_eqh:
        eqhl = "EQH"
    elif has_eql:
        eqhl = "EQL"
    else:
        eqhl = "None"

    # ── Momentum indicators ──
    momentum = _compute_momentum(df)

    # ── Rating (composite) ──
    bull_pts = 0
    bear_pts = 0

    # Structure contribution
    if structure_direction == "bullish":
        bull_pts += 2
    elif structure_direction == "bearish":
        bear_pts += 2

    # Momentum signal
    sig = momentum.get("signal", "Neutral")
    if "Bullish" in sig:
        bull_pts += 2 if "Strong" in sig else 1
    elif "Bearish" in sig:
        bear_pts += 2 if "Strong" in sig else 1

    # RSI
    rsi = momentum.get("rsi", 50)
    if rsi > 60:
        bull_pts += 1
    elif rsi < 40:
        bear_pts += 1

    # Money flow
    mf = momentum.get("money_flow_label", "Neutral")
    if mf == "Inflow":
        bull_pts += 1
    elif mf == "Outflow":
        bear_pts += 1

    # MACD
    macd = momentum.get("macd", "Neutral")
    if macd in ("Bullish", "Turning Up"):
        bull_pts += 1
    elif macd in ("Bearish", "Turning Down"):
        bear_pts += 1

    net = bull_pts - bear_pts
    if net >= 4:
        rating = "Strong Bullish"
    elif net >= 2:
        rating = "Bullish"
    elif net <= -4:
        rating = "Strong Bearish"
    elif net <= -2:
        rating = "Bearish"
    else:
        rating = "Neutral"

    # ── Confluence score (1-5) ──
    confluence_signals = []
    if structure_direction == "bullish":
        confluence_signals.append("bull")
    elif structure_direction == "bearish":
        confluence_signals.append("bear")
    if ob_status == "Inside" and best_ob:
        confluence_signals.append("bull" if best_ob["type"] == "bullish" else "bear")
    if fvg_label in ("Bullish",):
        confluence_signals.append("bull")
    elif fvg_label in ("Bearish",):
        confluence_signals.append("bear")
    if "Bullish" in sig:
        confluence_signals.append("bull")
    elif "Bearish" in sig:
        confluence_signals.append("bear")
    if mf == "Inflow":
        confluence_signals.append("bull")
    elif mf == "Outflow":
        confluence_signals.append("bear")

    bull_agree = confluence_signals.count("bull")
    bear_agree = confluence_signals.count("bear")
    confluence = max(bull_agree, bear_agree)
    if confluence >= 4:
        confluence_label = "Strong"
    elif confluence >= 3:
        confluence_label = "Moderate"
    elif bull_agree > 0 and bear_agree > 0:
        confluence_label = "Mixed"
    else:
        confluence_label = "Weak"

    return {
        "rating": rating,
        "structure": structure,
        "structure_direction": structure_direction,
        "order_block": ob_status,
        "ob_volume": round(float(ob_volume), 2),
        "ob_level": round(float(ob_level), 2) if ob_level else None,
        "ob_type": best_ob["type"] if best_ob else None,
        "fvg": fvg_label,
        "pg_zone": pg_zone,
        "liquidity": liquidity,
        "eqhl": eqhl,
        "signal": momentum.get("signal", "Neutral"),
        "rsi": momentum.get("rsi", 50.0),
        "macd": momentum.get("macd", "Neutral"),
        "squeeze": momentum.get("squeeze", "off"),
        "squeeze_momentum": momentum.get("squeeze_momentum", "neutral"),
        "money_flow": momentum.get("money_flow", 0.0),
        "money_flow_label": momentum.get("money_flow_label", "Neutral"),
        "volume_sentiment": momentum.get("volume_sentiment", "Normal"),
        "rvol": momentum.get("rvol", 1.0),
        "divergence": momentum.get("divergence", "None"),
        "trend_strength": momentum.get("trend_strength", 20.0),
        "trend_strength_label": momentum.get("trend_strength_label", "Moderate"),
        "reversals": momentum.get("reversals", "None"),
        "confluence": confluence,
        "confluence_label": confluence_label,
    }


def _aggregate_bias(rows: list[dict]) -> str:
    """Aggregate bias from one or more timeframe rows."""
    bull = 0
    bear = 0
    for r in rows:
        rating = r.get("rating", "Neutral")
        if "Strong Bullish" == rating:
            bull += 2
        elif "Bullish" == rating:
            bull += 1
        elif "Strong Bearish" == rating:
            bear += 2
        elif "Bearish" == rating:
            bear += 1
    net = bull - bear
    if net >= 2:
        return "Bullish"
    elif net <= -2:
        return "Bearish"
    elif net > 0:
        return "Lean Bullish"
    elif net < 0:
        return "Lean Bearish"
    return "Neutral"


def compute_smc_mtf_matrix(ticker: str) -> dict:
    """
    Compute the full SMC multi-timeframe analysis matrix.

    Fetches 5 timeframes (30m, 1H, 4H, 1W, 1M) via Polygon.io,
    runs all SMC detectors + momentum indicators per timeframe,
    and returns the matrix + confluence summary.

    Returns a JSON-serialisable dict matching the spec in smc_mtf_prompt.md.
    """
    import concurrent.futures
    from data_fetcher import get_polygon_ohlcv, get_polygon_snapshot

    # ── Fetch current price ──
    snap = get_polygon_snapshot([ticker])
    snap_data = snap.get(ticker, {})
    price = snap_data.get("price") or snap_data.get("close") or 0.0
    change_pct = snap_data.get("change_pct", 0.0)

    # ── Fetch all timeframes in parallel ──
    dfs: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        for tf in _TF_ORDER:
            cfg = _TF_CONFIGS[tf]
            # Monthly: fetch weekly bars, resample to monthly
            futures[pool.submit(
                get_polygon_ohlcv, ticker,
                days=cfg["days"],
                timespan=cfg["timespan"],
                multiplier=cfg["multiplier"],
            )] = tf
        for fut in concurrent.futures.as_completed(futures):
            tf = futures[fut]
            try:
                dfs[tf] = fut.result()
            except Exception:
                dfs[tf] = None

    # ── Resample weekly bars to monthly for 1M timeframe ──
    if dfs.get("1M") is not None:
        try:
            monthly = dfs["1M"].resample("MS").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna()
            if len(monthly) >= 10:
                dfs["1M"] = monthly
        except Exception:
            pass  # keep weekly bars as fallback

    # ── If price is 0, try to get it from a daily-like df ──
    if not price:
        for tf in ("4H", "1H", "1W"):
            if dfs.get(tf) is not None and len(dfs[tf]) > 0:
                price = float(dfs[tf]["Close"].iloc[-1])
                break

    # ── Compute each TF row in parallel ──
    timeframes: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        row_futures = {}
        for tf in _TF_ORDER:
            df = dfs.get(tf)
            pw = _TF_CONFIGS[tf]["pivot_window"]
            row_futures[pool.submit(_compute_tf_row, df, pw, price)] = tf
        for fut in concurrent.futures.as_completed(row_futures):
            tf = row_futures[fut]
            try:
                timeframes[tf] = fut.result()
            except Exception as e:
                timeframes[tf] = {"error": str(e)}

    # ── Confluence Summary ──
    htf_rows = [timeframes.get(tf, {}) for tf in ("1W", "1M") if "error" not in timeframes.get(tf, {})]
    itf_rows = [timeframes.get("4H", {})] if "error" not in timeframes.get("4H", {}) else []
    ltf_rows = [timeframes.get(tf, {}) for tf in ("30m", "1H") if "error" not in timeframes.get(tf, {})]

    htf_bias = _aggregate_bias(htf_rows)
    itf_bias = _aggregate_bias(itf_rows)
    ltf_bias = _aggregate_bias(ltf_rows)

    findings = []

    # Structure breaks on HTF
    for tf in ("1W", "1M"):
        row = timeframes.get(tf, {})
        structure = row.get("structure", "")
        if "BOS" in structure:
            findings.append(f"BOS on {tf}")
        if "CHoCH" in structure:
            findings.append(f"CHoCH on {tf} — potential reversal")

    # Squeeze firing
    for tf in _TF_ORDER:
        row = timeframes.get(tf, {})
        if row.get("squeeze") == "firing":
            findings.append(f"Squeeze firing on {tf}")

    # Divergences on HTF
    for tf in ("4H", "1W", "1M"):
        row = timeframes.get(tf, {})
        div = row.get("divergence", "None")
        if div != "None":
            findings.append(f"{div} on {tf}")

    # Order block proximity
    for tf in ("1H", "4H", "1W"):
        row = timeframes.get(tf, {})
        if row.get("order_block") == "Inside":
            ob_lv = row.get("ob_level")
            findings.append(f"Inside {tf} Order Block" + (f" at ${ob_lv:.2f}" if ob_lv else ""))

    # FVG unfilled
    for tf in ("1H", "4H", "1W"):
        row = timeframes.get(tf, {})
        fvg_val = row.get("fvg", "None")
        if fvg_val in ("Bullish", "Bearish"):
            findings.append(f"{fvg_val} FVG unfilled on {tf}")

    # Verdict
    hb = htf_bias.replace("Lean ", "")
    lb = ltf_bias.replace("Lean ", "")
    ib = itf_bias.replace("Lean ", "")

    if "Bullish" in hb and "Bullish" in ib and "Bullish" in lb:
        verdict = "BUY — Full alignment across all timeframes"
    elif "Bullish" in hb and "Bullish" not in lb:
        verdict = "WAIT — HTF bullish but LTF not confirmed, wait for reclaim"
    elif "Bearish" in hb and "Bearish" in lb:
        verdict = "SHORT candidate — Full bearish alignment"
    elif "Bearish" in hb and "Bullish" in lb:
        verdict = "FADE RISK — Counter-trend bounce, not a swing entry"
    else:
        verdict = "NO TRADE — Mixed signals, wait for clarity"

    # Confluence score
    bull_count = sum(1 for tf in _TF_ORDER if timeframes.get(tf, {}).get("rating", "") in ("Bullish", "Strong Bullish"))
    bear_count = sum(1 for tf in _TF_ORDER if timeframes.get(tf, {}).get("rating", "") in ("Bearish", "Strong Bearish"))

    return {
        "ticker": ticker,
        "price": round(float(price), 2) if price else 0.0,
        "change_pct": round(float(change_pct), 2) if change_pct else 0.0,
        "timeframes": timeframes,
        "summary": {
            "htf_bias": htf_bias,
            "itf_bias": itf_bias,
            "ltf_bias": ltf_bias,
            "confluence_score": max(bull_count, bear_count),
            "findings": findings,
            "verdict": verdict,
        },
    }
