"""
SMC (Smart Money Concepts) Engine
─────────────────────────────────
Detects:
  - Order Blocks (bull/bear)        — last opposing candle before impulse
  - Fair Value Gaps (FVG)           — 3-candle imbalance
  - Breaker Blocks                  — failed OB that flipped role
  - BoS (Break of Structure)        — trend-continuation confirmation
  - CHoCH (Change of Character)     — trend-reversal first signal
  - Liquidity sweeps (BSL/SSL)      — equal-highs / equal-lows clusters
  - Multi-TF structure              — HH/HL or LH/LL per TF

Also computes:
  - 60d OHLC bars for TV chart      — `attach_bars_daily(df, n=60)`
  - Per-ticker Wilson LB hit rates  — backtest sweep over historical zones

Per CLAUDE.md hedge-fund mindset:
  - Wilson 95% lower bound, not point estimates
  - Sample size flagged (n<30 caveat)
  - No look-ahead bias (only data available at zone-formation time)
  - Honest naming — "breaker" exposed as "S/R role reversal"
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# 1. BARS DAILY · for TV lightweight-charts in renderSMC
# ═══════════════════════════════════════════════════════════════════════

def attach_bars_daily(df: pd.DataFrame, n: int = 60) -> list[dict]:
    """
    Return last n bars in TV-lightweight-charts format:
      [{time:'YYYY-MM-DD', open, high, low, close, volume}, ...]
    Time is date string (UTC date), values are floats rounded to 2dp.
    """
    if df is None or len(df) == 0:
        return []
    tail = df.tail(n).copy()
    if isinstance(tail.index, pd.DatetimeIndex):
        dates = tail.index.strftime("%Y-%m-%d").tolist()
    else:
        # Fallback: try Date column or numeric index
        if "Date" in tail.columns:
            dates = pd.to_datetime(tail["Date"]).dt.strftime("%Y-%m-%d").tolist()
        else:
            base = datetime.utcnow().date() - timedelta(days=len(tail))
            dates = [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(len(tail))]
    bars = []
    for i, d in enumerate(dates):
        try:
            bars.append({
                "time": d,
                "open":  round(float(tail["Open"].iloc[i]),  2),
                "high":  round(float(tail["High"].iloc[i]),  2),
                "low":   round(float(tail["Low"].iloc[i]),   2),
                "close": round(float(tail["Close"].iloc[i]), 2),
                "volume": int(tail["Volume"].iloc[i]) if "Volume" in tail.columns else 0,
            })
        except Exception:
            continue
    return bars


# ═══════════════════════════════════════════════════════════════════════
# 2. SMC ZONE DETECTOR · core entry point
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Zone:
    """A price zone (rectangle): low → high, with formation date + status."""
    kind: str               # 'bull_ob' | 'bear_ob' | 'fvg_up' | 'fvg_down' | 'breaker'
    low: float
    high: float
    date: str               # formation date YYYY-MM-DD
    bar_idx: int            # index in the input df
    status: str = "untested"   # 'untested' | 'partial' | 'tested-held' | 'tested-breached'
    volume_at_formation: float = 0
    confluence_factors: list[str] = field(default_factory=list)


@dataclass
class StructureEvent:
    """A market-structure event (BoS, CHoCH, sweep)."""
    kind: str               # 'bos_up' | 'bos_dn' | 'choch_up' | 'choch_dn' | 'bsl_sweep' | 'ssl_sweep'
    date: str
    bar_idx: int
    price: float
    note: str = ""


def _swing_points(df: pd.DataFrame, window: int = 5) -> tuple[list[int], list[int]]:
    """Detect swing highs/lows. Returns (high_indices, low_indices) into df.
    A swing high at i: df.High[i] > df.High[i-window..i-1] AND > df.High[i+1..i+window]"""
    highs, lows = [], []
    if len(df) < 2 * window + 1:
        return highs, lows
    h_arr = df["High"].values
    l_arr = df["Low"].values
    for i in range(window, len(df) - window):
        if h_arr[i] >= h_arr[i-window:i].max() and h_arr[i] >= h_arr[i+1:i+window+1].max():
            highs.append(i)
        if l_arr[i] <= l_arr[i-window:i].min() and l_arr[i] <= l_arr[i+1:i+window+1].min():
            lows.append(i)
    return highs, lows


def _detect_order_blocks(df: pd.DataFrame, lookback: int = 60, max_zones: int = 5,
                          impulse_atr_mult: float = 1.2) -> list[Zone]:
    """
    Bullish OB: last RED candle before a strong UP impulse (≥`impulse_atr_mult`× ATR move).
    Bearish OB: last GREEN candle before a strong DOWN impulse.
    Returns OBs found in the last `lookback` bars, sorted oldest → newest.

    Indexing: bar_idx is the position WITHIN df (full series), so callers can
    slice df.iloc[bar_idx:] safely.
    """
    if len(df) < 20:
        return []
    # Work in absolute df indices to avoid reset_index headaches
    n_total = len(df)
    start = max(0, n_total - lookback - 5)
    closes = df["Close"].values
    opens  = df["Open"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    vols   = df["Volume"].values if "Volume" in df.columns else np.ones(n_total)
    dates  = (df.index.strftime("%Y-%m-%d").values
              if isinstance(df.index, pd.DatetimeIndex)
              else [""] * n_total)
    # ATR(14) per bar
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    # Pad to align with closes (tr[0] corresponds to bar 1's true range)
    atr = np.full(n_total, float("nan"))
    if len(tr) >= 14:
        atr_series = pd.Series(tr).rolling(14).mean().values
        atr[1:1+len(atr_series)] = atr_series
    zones: list[Zone] = []
    # Look-forward window — impulse can develop over 1-5 bars
    forward = 5
    for i in range(max(start, 14), n_total - forward):
        a = atr[i] if not np.isnan(atr[i]) else (atr[~np.isnan(atr)][-1] if (~np.isnan(atr)).any() else 0)
        if a == 0:
            continue
        is_red   = closes[i] < opens[i]
        is_green = closes[i] > opens[i]
        date_str = str(dates[i])[:10]
        avg_vol = float(vols[max(0, i-20):i].mean() or 1)
        rel_vol = float(vols[i]) / avg_vol
        # Multi-bar impulse: did price move ≥ impulse_atr_mult * ATR within next `forward` bars?
        post_high = highs[i+1:i+1+forward].max() if i+1+forward <= n_total else highs[i+1:].max()
        post_low  = lows[i+1:i+1+forward].min()  if i+1+forward <= n_total else lows[i+1:].min()
        impulse_up = (post_high - highs[i]) > impulse_atr_mult * a
        impulse_dn = (lows[i]  - post_low) > impulse_atr_mult * a
        if impulse_up and is_red:
            zones.append(Zone(
                kind="bull_ob", low=float(lows[i]), high=float(highs[i]),
                date=date_str, bar_idx=i,
                volume_at_formation=round(rel_vol, 2),
            ))
        if impulse_dn and is_green:
            zones.append(Zone(
                kind="bear_ob", low=float(lows[i]), high=float(highs[i]),
                date=date_str, bar_idx=i,
                volume_at_formation=round(rel_vol, 2),
            ))

    # Mark status based on bars AFTER the OB
    for z in zones:
        if z.bar_idx + 2 >= n_total:
            z.status = "untested"
            continue
        post_highs = highs[z.bar_idx + 2:]
        post_lows  = lows[z.bar_idx + 2:]
        if z.kind == "bull_ob":
            tagged  = ((post_lows <= z.high) & (post_lows >= z.low)).any()
            breached = (post_lows < z.low).any()
            z.status = "tested-breached" if breached else ("tested-held" if tagged else "untested")
        else:
            tagged  = ((post_highs >= z.low) & (post_highs <= z.high)).any()
            breached = (post_highs > z.high).any()
            z.status = "tested-breached" if breached else ("tested-held" if tagged else "untested")

    zones.sort(key=lambda z: z.bar_idx)
    return zones[-max_zones:]


def _detect_fvgs(df: pd.DataFrame, lookback: int = 60, max_zones: int = 5,
                  min_gap_pct: float = 0.002) -> list[Zone]:
    """
    FVG (Fair Value Gap):
      Up FVG:   candle[i-1].high < candle[i+1].low  (a gap between the wicks)
      Down FVG: candle[i-1].low  > candle[i+1].high

    Only keeps FVGs where the gap is ≥ min_gap_pct of price (default 0.2%) to
    avoid noisy tiny gaps.
    """
    if len(df) < 4:
        return []
    n_total = len(df)
    start = max(1, n_total - lookback - 1)
    highs = df["High"].values
    lows  = df["Low"].values
    closes = df["Close"].values
    dates = (df.index.strftime("%Y-%m-%d").values
             if isinstance(df.index, pd.DatetimeIndex) else [""] * n_total)
    zones: list[Zone] = []
    for i in range(start, n_total - 1):
        cur_px = closes[i]
        # Up FVG
        if highs[i-1] < lows[i+1]:
            gap = lows[i+1] - highs[i-1]
            if gap / max(cur_px, 1) >= min_gap_pct:
                zones.append(Zone(
                    kind="fvg_up", low=float(highs[i-1]), high=float(lows[i+1]),
                    date=str(dates[i+1])[:10], bar_idx=i+1,
                ))
        # Down FVG
        if lows[i-1] > highs[i+1]:
            gap = lows[i-1] - highs[i+1]
            if gap / max(cur_px, 1) >= min_gap_pct:
                zones.append(Zone(
                    kind="fvg_down", low=float(highs[i+1]), high=float(lows[i-1]),
                    date=str(dates[i+1])[:10], bar_idx=i+1,
                ))
    # Mark fill status using bars after each FVG
    for z in zones:
        if z.bar_idx + 1 >= n_total:
            z.status = "untested"
            continue
        post_highs = highs[z.bar_idx + 1:]
        post_lows  = lows[z.bar_idx + 1:]
        if z.kind == "fvg_up":
            z.status = "tested-held" if (post_lows <= z.low).any() else "untested"
        else:
            z.status = "tested-held" if (post_highs >= z.high).any() else "untested"
    return zones[-max_zones:]


def _detect_breakers(obs: list[Zone], df: pd.DataFrame) -> list[Zone]:
    """
    Breaker: a Bull OB that got breached (price closed below) and then reclaimed.
    Or a Bear OB that got breached (price closed above) and reclaimed.
    """
    breakers: list[Zone] = []
    if len(df) == 0:
        return breakers
    cur_close = float(df["Close"].iloc[-1])
    for ob in obs:
        if ob.kind == "bull_ob" and ob.status == "tested-breached" and cur_close > ob.high:
            breakers.append(Zone(
                kind="breaker", low=ob.low, high=ob.high, date=ob.date,
                bar_idx=ob.bar_idx, status="reclaimed",
                confluence_factors=["was Bull OB · breached · reclaimed = S→R→S"],
            ))
        if ob.kind == "bear_ob" and ob.status == "tested-breached" and cur_close < ob.low:
            breakers.append(Zone(
                kind="breaker", low=ob.low, high=ob.high, date=ob.date,
                bar_idx=ob.bar_idx, status="reclaimed",
                confluence_factors=["was Bear OB · breached · reclaimed = R→S→R"],
            ))
    return breakers


def _detect_structure_events(df: pd.DataFrame, lookback: int = 90) -> list[StructureEvent]:
    """
    BoS: close above prior swing high (in an up trend) — confirms continuation.
    CHoCH: first lower-high after an up trend — signals reversal.
    """
    events: list[StructureEvent] = []
    if len(df) < 30:
        return events
    df_slice = df.tail(lookback + 5).reset_index(drop=False)
    if "Date" not in df_slice.columns and isinstance(df.index, pd.DatetimeIndex):
        df_slice["Date"] = df.tail(lookback + 5).index.strftime("%Y-%m-%d").values
    high_idx, low_idx = _swing_points(df_slice, window=3)
    closes = df_slice["Close"].values

    # Walk forward · track last swing high/low and detect BoS / CHoCH
    last_swing_high = None
    last_swing_low  = None
    trend = None  # 'up' | 'dn' | None
    all_swings = sorted([(i, "H") for i in high_idx] + [(i, "L") for i in low_idx])
    for swing_i, swing_type in all_swings:
        date_str = str(df_slice.get("Date", pd.Series([""])).iloc[swing_i] if "Date" in df_slice else "")[:10]
        if swing_type == "H":
            cur_high = float(df_slice["High"].iloc[swing_i])
            if last_swing_high is not None and cur_high > last_swing_high:
                if trend == "dn":
                    events.append(StructureEvent("choch_up", date_str, swing_i,
                                                  cur_high, "Higher high · trend flip UP"))
                else:
                    events.append(StructureEvent("bos_up", date_str, swing_i,
                                                  cur_high, "Higher high · trend up confirmed"))
                trend = "up"
            elif last_swing_high is not None and cur_high < last_swing_high and trend == "up":
                events.append(StructureEvent("choch_dn", date_str, swing_i,
                                              cur_high, "Lower high · character changed"))
                trend = "dn"
            last_swing_high = cur_high
        else:
            cur_low = float(df_slice["Low"].iloc[swing_i])
            if last_swing_low is not None and cur_low < last_swing_low and trend == "up":
                events.append(StructureEvent("choch_dn", date_str, swing_i,
                                              cur_low, "Lower low · trend flip DOWN"))
                trend = "dn"
            elif last_swing_low is not None and cur_low < last_swing_low and trend != "up":
                events.append(StructureEvent("bos_dn", date_str, swing_i,
                                              cur_low, "Lower low · trend down confirmed"))
                trend = "dn"
            last_swing_low = cur_low
    return events[-6:]   # most recent 6


def _detect_liquidity_levels(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    BSL: clustered equal-highs above current price.
    SSL: clustered equal-lows below current price.
    Returns dict with 'bsl' and 'ssl' lists (each: price · count · last_date · armed_or_swept).
    """
    if len(df) < 20:
        return {"bsl": [], "ssl": []}
    tail = df.tail(lookback)
    cur = float(tail["Close"].iloc[-1])
    highs = tail["High"].values
    lows  = tail["Low"].values
    # Histogram-style equal-level clustering
    def cluster_levels(arr, tol_pct=0.003):
        levels = []
        for v in arr:
            placed = False
            for L in levels:
                if abs(L["price"] - v) / max(L["price"], 0.01) < tol_pct:
                    L["price"] = (L["price"] * L["count"] + v) / (L["count"] + 1)
                    L["count"] += 1
                    placed = True
                    break
            if not placed:
                levels.append({"price": float(v), "count": 1})
        return [L for L in levels if L["count"] >= 2]
    high_clusters = cluster_levels(highs)
    low_clusters  = cluster_levels(lows)
    # BSL = clusters ABOVE current price (above-spot equal-highs are where stops live)
    bsl = sorted([L for L in high_clusters if L["price"] > cur], key=lambda x: x["price"])[:3]
    ssl = sorted([L for L in low_clusters if L["price"] < cur], key=lambda x: -x["price"])[:3]
    # Mark swept (price wicked above BSL or below SSL recently)
    last_5_high = highs[-5:].max()
    last_5_low  = lows[-5:].min()
    for L in bsl:
        L["status"] = "swept" if last_5_high > L["price"] else "armed"
    for L in ssl:
        L["status"] = "swept" if last_5_low < L["price"] else "armed"
    return {"bsl": bsl, "ssl": ssl}


def _multi_tf_structure(df_daily: pd.DataFrame, weekly_df: Optional[pd.DataFrame] = None,
                        df_4h: Optional[pd.DataFrame] = None) -> dict:
    """
    Compute HH/HL or LH/LL across timeframes.
    Returns: {weekly: 'up'|'dn'|'chop', daily: ..., '4h': ..., '1h': '—'}
    """
    def classify(df, window=20):
        if df is None or len(df) < window + 5:
            return "chop"
        recent = df.tail(window + 5)
        highs = recent["High"].values
        lows  = recent["Low"].values
        h_idx, l_idx = _swing_points(recent, window=3)
        if not h_idx or not l_idx:
            return "chop"
        last_2_h = [highs[i] for i in h_idx[-2:]]
        last_2_l = [lows[i] for i in l_idx[-2:]]
        if len(last_2_h) == 2 and last_2_h[1] > last_2_h[0] and len(last_2_l) == 2 and last_2_l[1] > last_2_l[0]:
            return "up"
        if len(last_2_h) == 2 and last_2_h[1] < last_2_h[0] and len(last_2_l) == 2 and last_2_l[1] < last_2_l[0]:
            return "dn"
        return "chop"
    return {
        "weekly": classify(weekly_df) if weekly_df is not None else classify(df_daily.iloc[::5]) if df_daily is not None and len(df_daily) >= 100 else "—",
        "daily":  classify(df_daily),
        "4h":     classify(df_4h) if df_4h is not None else "—",
        "1h":     "—",  # not currently fetched
    }


def detect_smc_zones(df: pd.DataFrame, weekly_df: Optional[pd.DataFrame] = None,
                     df_4h: Optional[pd.DataFrame] = None,
                     df_1h: Optional[pd.DataFrame] = None) -> dict:
    """
    Main entry point.
    Returns a dict matching the renderSMC schema:
      {
        order_blocks: [Zone, ...],
        fvgs: [Zone, ...],
        breakers: [Zone, ...],
        structure_events: [StructureEvent, ...],
        liquidity: {bsl: [...], ssl: [...]},
        multi_tf: {weekly, daily, 4h, 1h},
        bars_daily: [{time, o, h, l, c, v}, ...],
      }
    """
    if df is None or len(df) < 10:
        return {
            "order_blocks": [],
            "fvgs": [],
            "breakers": [],
            "structure_events": [],
            "liquidity": {"bsl": [], "ssl": []},
            "multi_tf": {"weekly": "—", "daily": "—", "4h": "—", "1h": "—"},
            "bars_daily": [],
            "synth": False,
        }
    obs = _detect_order_blocks(df)
    fvgs = _detect_fvgs(df)
    breakers = _detect_breakers(obs, df)
    structure = _detect_structure_events(df)
    liquidity = _detect_liquidity_levels(df)
    mtf = _multi_tf_structure(df, weekly_df, df_4h)
    bars = attach_bars_daily(df, n=60)
    # 2026-05-17 · Multi-TF bars for swing traders (all timeframes wired)
    bars_1h = _attach_intraday_bars(df_1h, n=200) if df_1h is not None else []
    bars_4h = _attach_intraday_bars(df_4h, n=120) if df_4h is not None else []
    bars_weekly = attach_bars_daily(weekly_df, n=104) if weekly_df is not None else _resample_weekly_bars(df, n=104)
    return {
        "order_blocks":     [asdict(z) for z in obs],
        "fvgs":             [asdict(z) for z in fvgs],
        "breakers":         [asdict(z) for z in breakers],
        "structure_events": [asdict(e) for e in structure],
        "liquidity":        liquidity,
        "multi_tf":         mtf,
        "bars_daily":       bars,
        "bars_1h":          bars_1h,
        "bars_4h":          bars_4h,
        "bars_weekly":      bars_weekly,
        "synth":            False,
    }


def _attach_intraday_bars(df: pd.DataFrame, n: int = 200) -> list[dict]:
    """Like attach_bars_daily but uses UNIX timestamp (TV requires UTCTimestamp for intraday)."""
    if df is None or len(df) == 0:
        return []
    tail = df.tail(n).copy()
    if not isinstance(tail.index, pd.DatetimeIndex):
        return []
    out = []
    for ix, row in tail.iterrows():
        try:
            out.append({
                "time": int(ix.timestamp()),   # UNIX seconds for intraday
                "open":  round(float(row["Open"]),  2),
                "high":  round(float(row["High"]),  2),
                "low":   round(float(row["Low"]),   2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row.index else 0,
            })
        except Exception:
            continue
    return out


def _resample_weekly_bars(df: pd.DataFrame, n: int = 104) -> list[dict]:
    """Resample daily df to weekly OHLC bars (Mon-Fri group)."""
    if df is None or len(df) < 5:
        return []
    try:
        if not isinstance(df.index, pd.DatetimeIndex):
            return []
        w = df.resample("W").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last",
            "Volume": "sum" if "Volume" in df.columns else "max",
        }).dropna()
        return attach_bars_daily(w, n=n)
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════
# 3. WILSON LB · per-ticker historical hit rate per concept · per regime
# ═══════════════════════════════════════════════════════════════════════

def wilson_lower_bound(wins: int, total: int, z: float = 1.96) -> float:
    """Wilson 95% lower confidence bound on a proportion."""
    if total == 0:
        return 0.0
    p = wins / total
    denom = 1 + z*z / total
    centre = p + z*z / (2*total)
    margin = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))
    return max(0.0, (centre - margin) / denom)


def compute_smc_hit_rates(df: pd.DataFrame, ticker: str,
                           horizon_days: int = 10,
                           regimes: Optional[list] = None) -> dict:
    """
    Sweep historical df, detect each OB / FVG / breaker, track outcomes.
    A 'win' = price tagged the zone and held (didn't breach) within `horizon_days`.

    Returns:
      {
        order_blocks: {wins, total, win_rate, wilson_lb, sample_size_flag},
        fvgs: {...},
        breakers: {...},
        synth: false,
      }

    Sample size flag:
      - 'INSTITUTIONAL_FLOOR' if n>=30
      - 'BELOW_FLOOR' if 10<=n<30
      - 'INSUFFICIENT' if n<10
    """
    if df is None or len(df) < 90:
        return _empty_hit_rates()

    results = {
        "order_blocks": {"wins": 0, "total": 0},
        "fvgs": {"wins": 0, "total": 0},
        "breakers": {"wins": 0, "total": 0},
    }

    # Sliding window: at each historical anchor t, detect zones formed at t,
    # then check outcome over t+1 to t+horizon_days.
    #
    # CONDITIONAL hit rate: only counts zones that WERE TAGGED. The metric we
    # want is "given price returned to this zone, did it hold?" — not "did
    # price return AND hold". A zone that's never retested isn't a 'miss',
    # it's just N/A for the question.
    min_history = 60
    end_buffer = horizon_days + 5
    for t_anchor in range(min_history, len(df) - end_buffer):
        window = df.iloc[:t_anchor + 1]
        future = df.iloc[t_anchor + 1: t_anchor + 1 + horizon_days]
        if len(future) < horizon_days:
            continue
        zones = detect_smc_zones(window)
        future_highs = future["High"].values
        future_lows  = future["Low"].values
        # OBs formed in last 5 bars of window
        for ob in zones["order_blocks"]:
            if t_anchor - ob.get("bar_idx", t_anchor) > 5:
                continue
            if ob["kind"] == "bull_ob":
                tagged   = (future_lows  <= ob["high"]).any()
                if not tagged: continue
                breached = (future_lows  <  ob["low"]).any()
            else:
                tagged   = (future_highs >= ob["low"]).any()
                if not tagged: continue
                breached = (future_highs >  ob["high"]).any()
            results["order_blocks"]["total"] += 1
            if not breached:
                results["order_blocks"]["wins"] += 1
        # FVGs (the question is just "did it fill" — that's the only one supported)
        for fvg in zones["fvgs"]:
            if t_anchor - fvg.get("bar_idx", t_anchor) > 3:
                continue
            results["fvgs"]["total"] += 1
            if fvg["kind"] == "fvg_up":
                if (future_lows  <= fvg["low"]).any():
                    results["fvgs"]["wins"] += 1
            else:
                if (future_highs >= fvg["high"]).any():
                    results["fvgs"]["wins"] += 1
        # Breakers — conditional on tag
        for brk in zones["breakers"]:
            cur = float(window["Close"].iloc[-1])
            if cur > brk["high"]:
                tagged = (future_lows <= brk["high"]).any()
                if not tagged: continue
                breached = (future_lows <  brk["low"]).any()
            else:
                tagged = (future_highs >= brk["low"]).any()
                if not tagged: continue
                breached = (future_highs >  brk["high"]).any()
            results["breakers"]["total"] += 1
            if not breached:
                results["breakers"]["wins"] += 1

    # Compute stats
    out = {"ticker": ticker, "horizon_days": horizon_days, "synth": False}
    for k, v in results.items():
        wins, total = v["wins"], v["total"]
        wr = wins / total if total else 0
        wlb = wilson_lower_bound(wins, total)
        flag = "INSTITUTIONAL_FLOOR" if total >= 30 else "BELOW_FLOOR" if total >= 10 else "INSUFFICIENT"
        out[k] = {
            "wins": wins, "total": total,
            "win_rate": round(wr * 100, 1),
            "wilson_lb": round(wlb * 100, 1),
            "sample_size_flag": flag,
        }
    return out


def _empty_hit_rates() -> dict:
    return {
        "order_blocks": {"wins": 0, "total": 0, "win_rate": 0, "wilson_lb": 0, "sample_size_flag": "INSUFFICIENT"},
        "fvgs":         {"wins": 0, "total": 0, "win_rate": 0, "wilson_lb": 0, "sample_size_flag": "INSUFFICIENT"},
        "breakers":     {"wins": 0, "total": 0, "win_rate": 0, "wilson_lb": 0, "sample_size_flag": "INSUFFICIENT"},
        "synth": False,
    }


# ═══════════════════════════════════════════════════════════════════════
# 4. PERSISTENCE · cached hit rates
# ═══════════════════════════════════════════════════════════════════════

HIT_RATES_PATH = Path(__file__).parent / "data" / "smc_hit_rates.json"


def load_hit_rates() -> dict:
    if not HIT_RATES_PATH.exists():
        return {}
    try:
        with open(HIT_RATES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_hit_rate(ticker: str, hit_rates: dict) -> None:
    HIT_RATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_rates = load_hit_rates()
    all_rates[ticker] = hit_rates
    with open(HIT_RATES_PATH, "w") as f:
        json.dump(all_rates, f, indent=2)


def get_or_compute_hit_rates(df: pd.DataFrame, ticker: str,
                              max_age_days: int = 30) -> dict:
    """Return cached hit rates if fresh, else recompute and persist."""
    all_rates = load_hit_rates()
    rec = all_rates.get(ticker)
    if rec:
        try:
            updated = datetime.fromisoformat(rec.get("updated", "1970-01-01"))
            if (datetime.utcnow() - updated).days < max_age_days:
                return rec
        except Exception:
            pass
    rates = compute_smc_hit_rates(df, ticker)
    rates["updated"] = datetime.utcnow().isoformat()
    save_hit_rate(ticker, rates)
    return rates


# ═══════════════════════════════════════════════════════════════════════
# 5. ATTACH TO RESULT · single hook from analysis.py
# ═══════════════════════════════════════════════════════════════════════

def attach_smc_data(result: dict, df: pd.DataFrame, ticker: str,
                     weekly_df: Optional[pd.DataFrame] = None,
                     df_4h: Optional[pd.DataFrame] = None,
                     df_1h: Optional[pd.DataFrame] = None,
                     compute_hit_rates: bool = False) -> None:
    """
    Mutates `result` in-place to add:
      result['smc_data']    = detect_smc_zones output (zones, events, liquidity, mtf, bars)
      result['smc_hit_rates'] = wilson_lb hit rates (if compute_hit_rates=True)
    """
    try:
        result["smc_data"] = detect_smc_zones(df, weekly_df=weekly_df, df_4h=df_4h, df_1h=df_1h)
    except Exception as e:
        result["smc_data"] = {"error": str(e), "synth": False}
    if compute_hit_rates:
        try:
            result["smc_hit_rates"] = get_or_compute_hit_rates(df, ticker)
        except Exception as e:
            result["smc_hit_rates"] = _empty_hit_rates()


# ═══════════════════════════════════════════════════════════════════════
# 6. CLI · self-test against a sample ticker
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AVGO"
    try:
        from data_fetcher import fetch_ohlcv_with_failover
        result = fetch_ohlcv_with_failover(ticker, days=180)
        df = result[0] if isinstance(result, tuple) else result
    except Exception as e:
        print(f"fetch failed: {e}")
        sys.exit(1)
    if df is None or len(df) == 0:
        print(f"no data for {ticker}")
        sys.exit(1)
    print(f"\nSMC zones for {ticker} ({len(df)} bars):")
    smc = detect_smc_zones(df)
    print(f"  bull OBs : {len([z for z in smc['order_blocks'] if z['kind']=='bull_ob'])}")
    print(f"  bear OBs : {len([z for z in smc['order_blocks'] if z['kind']=='bear_ob'])}")
    print(f"  FVGs     : {len(smc['fvgs'])}")
    print(f"  breakers : {len(smc['breakers'])}")
    print(f"  events   : {len(smc['structure_events'])}")
    print(f"  BSL/SSL  : {len(smc['liquidity']['bsl'])} / {len(smc['liquidity']['ssl'])}")
    print(f"  MTF      : W={smc['multi_tf']['weekly']} · D={smc['multi_tf']['daily']}")
    print(f"  bars     : {len(smc['bars_daily'])}")
    print(f"\nComputing hit rates (this may take a moment)...")
    hr = compute_smc_hit_rates(df, ticker)
    for k in ["order_blocks", "fvgs", "breakers"]:
        v = hr[k]
        print(f"  {k:15s}: WR {v['win_rate']:5.1f}% · LB {v['wilson_lb']:5.1f}% · n={v['total']:4d} · {v['sample_size_flag']}")
