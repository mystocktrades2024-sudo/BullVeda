"""target_engine.py — structural target-computation engine.

Replaces ATR-only T1/T2 with confluence-scored structural targets.
Standalone module: reads OHLCV via fetch_ohlcv_with_failover, emits §8 JSON schema.

Usage:
    python3 target_engine.py ROST swing
    python3 target_engine.py AVGO position --equity 25000
    python3 target_engine.py AAPL invest

Phase 1 sub-modules:
    - Structure Detector (5-bar fractal · swings · BOS/CHoCH)
    - Liquidity Detector (equal-highs clusters · BSL/SSL)
    - Volume Profile (POC · VAH · VAL · HVN · LVN)
    - Anchored VWAP (52w-high · last earnings · YTD-open)
    - ATR guardrail (14-period)
    - Confluence selection + Magnet/Rejection/Mixed classification

Phase 2 (later): OB · FVG · fundamentals · Bayesian/MC blend.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Cache configuration
CACHE_DIR = Path(__file__).parent / "cache" / "target_engine"
CACHE_TTL_SECONDS = 12 * 60 * 60  # 12 hours

# ════════════════════════════════════════════════════════════════════════
# CONFIG · per-mode parameters + source weights
# ════════════════════════════════════════════════════════════════════════
MODES = {
    "swing": {
        "lookback_days": 40,
        "min_r_t1": 1.5,
        "min_r_t2": 2.0,  # bent from 3.0 when next level has much lower conf
        "fractal_window": 5,
        "atr_period": 14,
        "primary_tf": "daily",
        "sources_drop": {"AVWAP_52", "FVG", "FIB"},  # too far for short window
    },
    "position": {
        "lookback_days": 120,
        "min_r_t1": 2.0,
        "min_r_t2": 3.0,
        "fractal_window": 5,
        "atr_period": 14,
        "primary_tf": "daily",
        "sources_drop": set(),
    },
    "invest": {
        "lookback_days": 504,
        "min_r_t1": None,  # IV-based, not R-based
        "min_r_t2": None,
        "fractal_window": 8,
        "atr_period": 21,
        "primary_tf": "daily",
        "sources_drop": {"FVG"},  # FVG too short-term for 1y+
    },
}

SOURCE_WEIGHTS = {
    "BSL": 3.0,         # equal-highs liquidity pool (touches >= 2)
    "HVN": 2.5,         # High Volume Node center
    "SWING": 2.5,       # prior swing high (BOS anchor)
    "VAH": 2.0,         # Value Area High
    "AVWAP_52": 2.0,    # AVWAP from 52w-high
    "AVWAP_EARN": 1.5,  # AVWAP from last earnings
    "FVG": 1.5,         # opposing fair value gap
    "ROUND": 1.0,       # round number cluster ($X00, $X50)
    "FIB": 0.5,         # Fibonacci extension (1.618 / 2.618)
}

# Behavior classifier rules
MAGNET_SOURCES = {"HVN"}              # HVN center, POC
REJECTION_SOURCES = {"VAH", "AVWAP_52", "FVG"}  # mean-revert / overhead supply
MIXED_SOURCES = {"BSL", "SWING"}      # liquidity sweeps go either way


# ════════════════════════════════════════════════════════════════════════
# Project 2 · Milestone 2.3 — Mode completeness helpers
# ════════════════════════════════════════════════════════════════════════
# Known ETF/ETN tickers · graceful-degradation path (lower swing-structure
# floor, broader confidence band). Not exhaustive — extend as needed.
_KNOWN_ETF_TICKERS = {
    # broad market
    "SPY", "QQQ", "DIA", "IWM", "IVV", "VOO", "VTI",
    # sector SPDRs
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC",
    # leveraged / inverse (often used for hedging)
    "SOXL", "SOXS", "TQQQ", "SQQQ", "SPXL", "SPXS", "TNA", "TZA", "TLT", "TBT",
    "UVXY", "VXX", "SVXY", "FAS", "FAZ", "LABU", "LABD",
    # international / sector themes
    "EEM", "EFA", "FXI", "GLD", "SLV", "USO", "UNG", "VNQ", "ARKK", "IBIT",
    # Russell + small-cap
    "IWO", "IWD", "IWF", "VEA", "VWO",
}


def _is_etf(ticker: str) -> bool:
    """Cheap ETF detection · checks known list + common ETF suffix patterns."""
    if not ticker:
        return False
    tk = ticker.upper().strip()
    if tk in _KNOWN_ETF_TICKERS:
        return True
    # Leveraged-ETF naming patterns (heuristic — many 3-4 letter tickers ending
    # in L/U/S/X happen to be leveraged products, but many stocks share the
    # pattern, so we keep the known-list authoritative and only flag obvious
    # patterns like ProShares "PRO*" or Direxion "TQ*", "SQ*" prefixes).
    return False


def _earnings_days_until(ticker: str):
    """Days until next earnings · returns int >=0 or None if unknown/no data.

    Best-effort: pulls EODHD earnings calendar for the next 60 days, filters
    to this ticker. Silent on any failure (network / cache miss / no upcoming).
    """
    if not ticker:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import eodhd_client as _e
        from datetime import date as _date
        start = _date.today()
        end = start + timedelta(days=60)
        result = _e.earnings_calendar(from_date=start.isoformat(),
                                      to_date=end.isoformat(),
                                      symbols=[ticker.upper()],
                                      cache_ttl=43200)
        rows = (result or {}).get("earnings") or []
        for row in rows:
            code = (row.get("code") or "").split(".")[0].upper()
            if code != ticker.upper():
                continue
            rd = row.get("report_date") or row.get("reportDate") or row.get("date")
            if not rd:
                continue
            try:
                report_dt = datetime.strptime(str(rd)[:10], "%Y-%m-%d").date()
                delta = (report_dt - start).days
                if delta >= 0:
                    return delta
            except Exception:
                continue
    except Exception:
        pass
    return None


def _analyst_pt_fallback(ticker: str):
    """Mean analyst price target for INVEST-mode stub when structural targets fail.

    Returns {"mean": float, "high": float | None, "low": float | None,
             "count": int, "source": "eodhd"} or None.
    Honest stub — flags itself so consumers can show a banner.
    """
    if not ticker:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import eodhd_client as _e
        fund = _e.fundamentals(ticker.upper(), cache_ttl=86400) or {}
        analyst = (fund.get("AnalystRatings") or {})
        target_price = analyst.get("TargetPrice")
        if not target_price:
            return None
        return {
            "mean": float(target_price),
            "source": "eodhd_analyst_target_price",
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════
# DATACLASSES · structured outputs
# ════════════════════════════════════════════════════════════════════════
@dataclass
class Swing:
    """A single swing pivot (high or low)."""
    price: float
    date: str
    kind: str  # "high" or "low"
    bar_idx: int


@dataclass
class Source:
    """One structural source backing a candidate price level."""
    type: str          # e.g. "BSL", "HVN", "SWING", "VAH", "AVWAP_52"
    weight: float
    price: float
    detail: dict = field(default_factory=dict)  # touches, anchor_date, vol_pct, etc.


@dataclass
class Candidate:
    """A price level above entry, with all structural sources stacked at it."""
    price: float
    sources: list  # list[Source]
    confluence: float  # sum of source weights within ±0.25 ATR

    @property
    def source_types(self) -> list:
        return [s.type for s in self.sources]


@dataclass
class Target:
    """Final T1 or T2 selection."""
    price: float
    r_multiple: float
    distance_pct: float
    confluence: float
    sources: list  # list[Source]
    behavior: str  # "MAGNET" | "REJECTION" | "MIXED" | "STRUCTURAL"
    action: str    # "trim_33pct_wait_one_bar" | "scale_50pct_on_touch" | ...
    p_reach: float
    p_reach_source: dict  # {analog, mc, bayes, median}


@dataclass
class TradeAnalysis:
    """Top-level engine output · §8 schema."""
    ticker: str
    mode: str
    timestamp: str
    price_at_analysis: float
    direction: str
    decision: str  # "trade" | "reject" | "wait"
    entry: dict
    stop: dict
    t1: Optional[Target]
    t2: Optional[Target]
    sizing: dict
    context: dict
    confidence: dict
    warnings: list
    # M2.3 optional metadata · default empty so existing callers keep working
    is_etf: bool = False
    catalyst: Optional[dict] = None      # {"type": "earnings", "days_until": int}
    invest_stub: bool = False            # True when t1/t2 came from analyst PT fallback


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 1 · ATR (guardrail)
# ════════════════════════════════════════════════════════════════════════
def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Wilder's ATR. Returns final value (single float)."""
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    if len(close) < period + 1:
        return float(np.mean(high - low))

    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    ])
    # Wilder's smoothing
    atr = np.zeros_like(tr, dtype=float)
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return float(atr[-1])


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 2 · Structure Detector (fractal pivots + trend + BOS/CHoCH)
# ════════════════════════════════════════════════════════════════════════
def find_swing_pivots(df: pd.DataFrame, fractal_window: int = 5) -> list:
    """5-bar fractal: bar N is a swing high if H[N] > max(H[N-2], H[N-1], H[N+1], H[N+2]).
    Returns chronological list of Swing pivots.
    """
    half = fractal_window // 2
    swings = []
    highs = df["High"].values
    lows = df["Low"].values
    dates = df.index.strftime("%Y-%m-%d").tolist() if hasattr(df.index, "strftime") else \
            [str(d)[:10] for d in df.index]

    for i in range(half, len(df) - half):
        left = highs[i - half:i]
        right = highs[i + 1:i + 1 + half]
        if len(left) and len(right) and highs[i] > max(left.max(), right.max()):
            swings.append(Swing(price=float(highs[i]), date=dates[i], kind="high", bar_idx=i))

    for i in range(half, len(df) - half):
        left = lows[i - half:i]
        right = lows[i + 1:i + 1 + half]
        if len(left) and len(right) and lows[i] < min(left.min(), right.min()):
            swings.append(Swing(price=float(lows[i]), date=dates[i], kind="low", bar_idx=i))

    swings.sort(key=lambda s: s.bar_idx)
    return swings


def classify_trend(swings: list) -> str:
    """Look at last 4 swings to determine HH/HL or LH/LL pattern."""
    if len(swings) < 4:
        return "unknown"
    recent = swings[-4:]
    highs = [s for s in recent if s.kind == "high"]
    lows = [s for s in recent if s.kind == "low"]
    if len(highs) >= 2 and len(lows) >= 2:
        higher_high = highs[-1].price > highs[-2].price
        higher_low = lows[-1].price > lows[-2].price
        if higher_high and higher_low:
            return "uptrend"
        if not higher_high and not higher_low:
            return "downtrend"
    return "range"


def detect_bos_choch(swings: list, current_price: float) -> dict:
    """Break of Structure: close beyond prior confirmed swing in trend direction.
    Change of Character: close beyond prior confirmed HL (in uptrend) or LH (in downtrend).
    """
    trend = classify_trend(swings)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    bos = None
    choch = None

    if trend == "uptrend" and len(highs) >= 2 and len(lows) >= 1:
        # BOS: close above latest swing high
        if current_price > highs[-1].price:
            bos = {"price": highs[-1].price, "direction": "bullish", "date": highs[-1].date}
        # CHoCH: close below latest swing low
        if lows and current_price < lows[-1].price:
            choch = {"price": lows[-1].price, "direction": "bearish", "date": lows[-1].date}
    elif trend == "downtrend" and len(lows) >= 2 and len(highs) >= 1:
        if current_price < lows[-1].price:
            bos = {"price": lows[-1].price, "direction": "bearish", "date": lows[-1].date}
        if highs and current_price > highs[-1].price:
            choch = {"price": highs[-1].price, "direction": "bullish", "date": highs[-1].date}

    return {"trend": trend, "last_bos": bos, "last_choch": choch}


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 3 · Liquidity Detector (equal-highs / equal-lows)
# ════════════════════════════════════════════════════════════════════════
def find_equal_highs(swings: list, tolerance_pct: float = 0.0015,
                     min_touches: int = 2) -> list:
    """Group swing highs within tolerance_pct of each other.
    Returns list of {price, touch_count, last_touch, swings: [Swing]}
    """
    highs = sorted([s for s in swings if s.kind == "high"], key=lambda s: s.price)
    pools = []
    for s in highs:
        # Try to join an existing pool
        joined = False
        for pool in pools:
            avg = sum(p.price for p in pool["swings"]) / len(pool["swings"])
            if abs(s.price - avg) / avg <= tolerance_pct:
                pool["swings"].append(s)
                joined = True
                break
        if not joined:
            pools.append({"swings": [s]})

    out = []
    for pool in pools:
        if len(pool["swings"]) < min_touches:
            continue
        avg_price = float(np.mean([s.price for s in pool["swings"]]))
        last = max(pool["swings"], key=lambda s: s.bar_idx)
        out.append({
            "price": avg_price,
            "touch_count": len(pool["swings"]),
            "last_touch": last.date,
        })
    return out


def find_equal_lows(swings: list, tolerance_pct: float = 0.0015,
                    min_touches: int = 2) -> list:
    """Mirror of find_equal_highs for sell-side liquidity."""
    lows = sorted([s for s in swings if s.kind == "low"], key=lambda s: s.price)
    pools = []
    for s in lows:
        joined = False
        for pool in pools:
            avg = sum(p.price for p in pool["swings"]) / len(pool["swings"])
            if abs(s.price - avg) / avg <= tolerance_pct:
                pool["swings"].append(s)
                joined = True
                break
        if not joined:
            pools.append({"swings": [s]})
    out = []
    for pool in pools:
        if len(pool["swings"]) < min_touches:
            continue
        avg_price = float(np.mean([s.price for s in pool["swings"]]))
        last = max(pool["swings"], key=lambda s: s.bar_idx)
        out.append({
            "price": avg_price,
            "touch_count": len(pool["swings"]),
            "last_touch": last.date,
        })
    return out


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 4 · Volume Profile (POC / VAH / VAL / HVN / LVN)
# ════════════════════════════════════════════════════════════════════════
def compute_volume_profile(df: pd.DataFrame, n_bins: int = 100,
                           atr: Optional[float] = None) -> dict:
    """Build volume-at-price array. Each bar distributes its volume evenly
    across the bins its range covers (typewriter method).
    Returns {poc, vah, val, hvn_zones, lvn_zones, bins[].volume}.
    """
    if df.empty:
        return {"poc": None, "vah": None, "val": None, "hvn_zones": [], "lvn_zones": []}

    lo = float(df["Low"].min())
    hi = float(df["High"].max())
    if hi <= lo:
        return {"poc": None, "vah": None, "val": None, "hvn_zones": [], "lvn_zones": []}

    # ATR-relative bin sizing: bin_size = 0.1 × ATR, capped at n_bins=100
    if atr is None:
        bin_size = (hi - lo) / n_bins
    else:
        bin_size = max(atr * 0.1, (hi - lo) / n_bins)
    n_bins = max(20, min(int((hi - lo) / bin_size), 200))

    bins = np.linspace(lo, hi, n_bins + 1)
    vol_at_price = np.zeros(n_bins)

    for _, row in df.iterrows():
        bar_lo, bar_hi, vol = row["Low"], row["High"], row["Volume"]
        if not (pd.notna(bar_lo) and pd.notna(bar_hi) and pd.notna(vol) and vol > 0):
            continue
        lo_idx = max(0, int((bar_lo - lo) / bin_size))
        hi_idx = min(n_bins - 1, int((bar_hi - lo) / bin_size))
        if hi_idx < lo_idx:
            continue
        per_bin = vol / (hi_idx - lo_idx + 1)
        vol_at_price[lo_idx:hi_idx + 1] += per_bin

    if vol_at_price.sum() == 0:
        return {"poc": None, "vah": None, "val": None, "hvn_zones": [], "lvn_zones": []}

    poc_idx = int(np.argmax(vol_at_price))
    poc = float((bins[poc_idx] + bins[poc_idx + 1]) / 2)

    # VAH / VAL: expand outward from POC until 70% of total volume
    total = vol_at_price.sum()
    target_vol = 0.70 * total
    left, right = poc_idx, poc_idx
    captured = vol_at_price[poc_idx]
    while captured < target_vol and (left > 0 or right < n_bins - 1):
        left_vol = vol_at_price[left - 1] if left > 0 else 0
        right_vol = vol_at_price[right + 1] if right < n_bins - 1 else 0
        if left_vol >= right_vol and left > 0:
            left -= 1
            captured += left_vol
        elif right < n_bins - 1:
            right += 1
            captured += right_vol
        else:
            break
    val = float(bins[left])
    vah = float(bins[right + 1])

    # HVN: contiguous bins with volume > mean + 1σ
    mean = float(vol_at_price.mean())
    sd = float(vol_at_price.std())
    hvn_thr = mean + sd
    lvn_thr = max(0.0, mean - sd)
    hvn_zones, lvn_zones = [], []
    i = 0
    while i < n_bins:
        if vol_at_price[i] > hvn_thr:
            j = i
            while j < n_bins and vol_at_price[j] > hvn_thr:
                j += 1
            zone_lo = float(bins[i])
            zone_hi = float(bins[j])
            zone_center = (zone_lo + zone_hi) / 2
            vol_pct = float(vol_at_price[i:j].sum() / total)
            hvn_zones.append({"low": zone_lo, "high": zone_hi, "center": zone_center, "vol_pct": vol_pct})
            i = j
        else:
            i += 1
    i = 0
    while i < n_bins:
        if vol_at_price[i] < lvn_thr and vol_at_price[i] > 0:
            j = i
            while j < n_bins and vol_at_price[j] < lvn_thr and vol_at_price[j] > 0:
                j += 1
            zone_lo = float(bins[i])
            zone_hi = float(bins[j])
            lvn_zones.append({"low": zone_lo, "high": zone_hi, "vol_pct": float(vol_at_price[i:j].sum() / total)})
            i = j
        else:
            i += 1

    return {
        "poc": poc, "vah": vah, "val": val,
        "hvn_zones": hvn_zones, "lvn_zones": lvn_zones,
        "total_volume": float(total),
    }


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 5 · Anchored VWAP
# ════════════════════════════════════════════════════════════════════════
def compute_anchored_vwap(df: pd.DataFrame, anchor_date: str) -> Optional[float]:
    """Volume-weighted typical price from anchor_date through end."""
    if df.empty:
        return None
    anchor_ts = pd.to_datetime(anchor_date)
    sub = df.loc[df.index >= anchor_ts]
    if sub.empty:
        return None
    typical = (sub["High"] + sub["Low"] + sub["Close"]) / 3
    weighted = (typical * sub["Volume"]).sum()
    total_vol = sub["Volume"].sum()
    if total_vol == 0:
        return None
    return float(weighted / total_vol)


def find_anchor_dates(df: pd.DataFrame, earnings_dates: Optional[list] = None) -> dict:
    """Identify meaningful anchor dates: 52w-high, last 2 earnings, YTD-open."""
    out = {}
    if df.empty:
        return out
    last_252 = df.tail(252) if len(df) >= 252 else df
    high_idx = last_252["High"].idxmax()
    out["52w_high"] = high_idx.strftime("%Y-%m-%d") if hasattr(high_idx, "strftime") else str(high_idx)[:10]
    low_idx = last_252["Low"].idxmin()
    out["52w_low"] = low_idx.strftime("%Y-%m-%d") if hasattr(low_idx, "strftime") else str(low_idx)[:10]
    # YTD-open
    year = df.index[-1].year if hasattr(df.index[-1], "year") else int(str(df.index[-1])[:4])
    ytd_start = pd.Timestamp(f"{year}-01-01")
    ytd_sub = df.loc[df.index >= ytd_start]
    if not ytd_sub.empty:
        out["ytd_open"] = ytd_sub.index[0].strftime("%Y-%m-%d")
    if earnings_dates:
        for i, ed in enumerate(earnings_dates[:2]):
            out[f"earn_q{i+1}"] = ed
    return out


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 6 · Round number cluster
# ════════════════════════════════════════════════════════════════════════
def round_number_levels(price: float, atr: float, num_above: int = 8) -> list:
    """Generate round-number levels above price.
    Granularity scales with price: $1 round for <$50, $5 round for $50-$500, $10 for $500+.
    """
    if price < 50:
        step = 1.0
    elif price < 500:
        step = 5.0
    else:
        step = 10.0
    start = math.floor(price / step) * step + step
    return [start + i * step for i in range(num_above)]


# ════════════════════════════════════════════════════════════════════════
# SUB-MODULE 7 · Fibonacci extensions
# ════════════════════════════════════════════════════════════════════════
def fib_extensions(swings: list, direction: str = "long") -> list:
    """1.618 / 2.618 of last swing-low to swing-high impulse (for longs)."""
    if len(swings) < 2:
        return []
    if direction == "long":
        # Find latest swing low and the swing high after it
        lows = [s for s in swings if s.kind == "low"]
        highs = [s for s in swings if s.kind == "high"]
        if not lows or not highs:
            return []
        last_low = lows[-1]
        # Find latest high before that low
        prior_highs = [h for h in highs if h.bar_idx < last_low.bar_idx]
        if not prior_highs:
            return []
        prior_high = prior_highs[-1]
        # Impulse leg = prior_high to last_low (down move) — fib extends OFF that
        # For long bias, we extend UP from last_low by impulse size
        impulse = prior_high.price - last_low.price
        if impulse <= 0:
            return []
        return [last_low.price + impulse * 1.618, last_low.price + impulse * 2.618]
    return []


# ════════════════════════════════════════════════════════════════════════
# CONFLUENCE + SELECTION
# ════════════════════════════════════════════════════════════════════════
def build_candidate_levels(
    entry: float, atr: float, direction: str,
    eq_highs: list, eq_lows: list,
    vp: dict, anchors: dict, swings: list,
    df: pd.DataFrame, mode_cfg: dict,
) -> list:
    """Collect ALL structural levels above entry (long) or below (short)."""
    drop = mode_cfg.get("sources_drop", set())
    raw = []

    if direction == "long":
        # Equal highs → BSL
        if "BSL" not in drop:
            for eh in eq_highs:
                if eh["price"] > entry:
                    w = SOURCE_WEIGHTS["BSL"] * min(1.0, eh["touch_count"] / 3.0) * (1.0 if eh["touch_count"] >= 3 else 0.7)
                    raw.append(Source("BSL", w, eh["price"],
                                      {"touches": eh["touch_count"], "last_touch": eh["last_touch"]}))
        # HVN centers (the magnets)
        if "HVN" not in drop:
            for z in vp.get("hvn_zones", []):
                if z["center"] > entry:
                    raw.append(Source("HVN", SOURCE_WEIGHTS["HVN"], z["center"],
                                      {"low": z["low"], "high": z["high"], "vol_pct": z["vol_pct"]}))
        # Prior swing highs above entry (BOS anchors)
        if "SWING" not in drop:
            for s in swings:
                if s.kind == "high" and s.price > entry:
                    raw.append(Source("SWING", SOURCE_WEIGHTS["SWING"], s.price,
                                      {"date": s.date, "bos_anchor": True}))
        # VAH if above entry
        if "VAH" not in drop and vp.get("vah") and vp["vah"] > entry:
            raw.append(Source("VAH", SOURCE_WEIGHTS["VAH"], vp["vah"], {}))
        # AVWAP from 52w-high
        if "AVWAP_52" not in drop and anchors.get("52w_high"):
            av = compute_anchored_vwap(df, anchors["52w_high"])
            if av and av > entry:
                raw.append(Source("AVWAP_52", SOURCE_WEIGHTS["AVWAP_52"], av,
                                  {"anchor": anchors["52w_high"]}))
        # AVWAP from earnings
        if "AVWAP_EARN" not in drop and anchors.get("earn_q1"):
            av = compute_anchored_vwap(df, anchors["earn_q1"])
            if av and av > entry:
                raw.append(Source("AVWAP_EARN", SOURCE_WEIGHTS["AVWAP_EARN"], av,
                                  {"anchor": anchors["earn_q1"]}))
        # Round numbers
        if "ROUND" not in drop:
            for r in round_number_levels(entry, atr):
                if r > entry and r < entry + 5 * atr:  # cap reach
                    raw.append(Source("ROUND", SOURCE_WEIGHTS["ROUND"], r, {}))
        # Fibonacci extensions
        if "FIB" not in drop:
            for f in fib_extensions(swings, direction="long"):
                if f > entry:
                    raw.append(Source("FIB", SOURCE_WEIGHTS["FIB"], f, {}))
    # short direction handled similarly (mirror) — omitted for Phase 1 brevity
    return raw


def cluster_levels_and_score(raw_sources: list, atr: float, cluster_atr: float = 0.25) -> list:
    """Group sources within ±cluster_atr × ATR into candidate price levels.
    Each candidate's confluence = sum of source weights.
    """
    if not raw_sources:
        return []
    cluster_dist = atr * cluster_atr
    # Sort by price
    sources = sorted(raw_sources, key=lambda s: s.price)
    clusters = []
    current = [sources[0]]
    for s in sources[1:]:
        if abs(s.price - current[-1].price) <= cluster_dist:
            current.append(s)
        else:
            clusters.append(current)
            current = [s]
    clusters.append(current)

    candidates = []
    for cluster in clusters:
        # Cluster price = weighted average by source weight
        total_w = sum(s.weight for s in cluster)
        if total_w == 0:
            continue
        cluster_price = sum(s.price * s.weight for s in cluster) / total_w
        candidates.append(Candidate(
            price=float(cluster_price),
            sources=cluster,
            confluence=float(total_w),
        ))
    return candidates


def select_targets(candidates: list, entry: float, stop: float, mode: str) -> tuple:
    """Select T1 (highest confluence in ≥min_r_t1 band) and T2 (≥min_r_t2 band, > T1)."""
    cfg = MODES[mode]
    risk = entry - stop
    if risk <= 0:
        return None, None

    # For invest mode, fall back to IV triangulation (Phase 2 — for now return None)
    if mode == "invest":
        return None, None  # Phase 2 implements IV-based selection

    min_r_t1 = cfg["min_r_t1"]
    min_r_t2 = cfg["min_r_t2"]

    t1_pool = [c for c in candidates if (c.price - entry) / risk >= min_r_t1]
    if not t1_pool:
        return None, None

    # T1: highest confluence within first R-band
    t1 = max(t1_pool, key=lambda c: (c.confluence, -c.price))

    # T2: beyond T1, highest confluence in R-band
    t2_pool = [c for c in candidates if c.price > t1.price and (c.price - entry) / risk >= min_r_t2]
    t2 = max(t2_pool, key=lambda c: (c.confluence, -c.price)) if t2_pool else None

    return t1, t2


def classify_behavior(candidate: Candidate) -> tuple:
    """MAGNET / REJECTION / MIXED / STRUCTURAL based on dominant source type."""
    type_weights = {}
    for s in candidate.sources:
        type_weights[s.type] = type_weights.get(s.type, 0) + s.weight
    if not type_weights:
        return "MIXED", "trim_50pct_wait_one_bar"
    # Categorize
    mag_w = sum(w for t, w in type_weights.items() if t in MAGNET_SOURCES)
    rej_w = sum(w for t, w in type_weights.items() if t in REJECTION_SOURCES)
    mix_w = sum(w for t, w in type_weights.items() if t in MIXED_SOURCES)

    if mag_w >= max(rej_w, mix_w):
        return "MAGNET", "hold_full_size_to_target"
    if rej_w >= max(mag_w, mix_w):
        return "REJECTION", "scale_50pct_on_touch"
    return "MIXED", "trim_33pct_wait_one_bar"


def estimate_p_reach(candidate: Candidate, mode: str) -> dict:
    """Phase 1 heuristic: blend confluence-to-prob mapping with mode-specific decay.
    Phase 2 will replace this with real analog + MC + Bayes blend.
    """
    # Confluence 0-12 → P 0.05-0.85 sigmoid-ish
    conf = candidate.confluence
    base = 1.0 / (1.0 + math.exp(-(conf - 5.0) / 2.0))  # sigmoid centered at conf=5
    base = max(0.05, min(0.85, base))

    # Mode adjustment: SWING has tighter window so probs lower; INVESTMENT longer so higher
    mode_mult = {"swing": 0.7, "position": 1.0, "invest": 1.3}[mode]
    median = max(0.05, min(0.90, base * mode_mult))

    # Stub: report median as if blended (Phase 2 will compute analog/mc/bayes individually)
    return {
        "analog": round(median * 0.95, 3),
        "mc": round(median * 1.05, 3),
        "bayes": round(median, 3),
        "median": round(median, 3),
    }


# ════════════════════════════════════════════════════════════════════════
# STOP CALCULATION (simplified Phase 1 · candidate stops + ATR floor)
# ════════════════════════════════════════════════════════════════════════
def compute_stop(entry: float, atr: float, direction: str,
                 swings: list, vp: dict) -> dict:
    """Phase 1 stop: structural swing low (long) or swing high (short),
    fallback to entry − 1.5 × ATR.
    """
    candidates = {}
    if direction == "long":
        # Nearest swing low below entry
        lows = sorted([s for s in swings if s.kind == "low" and s.price < entry],
                      key=lambda s: s.price, reverse=True)
        if lows:
            candidates["swing"] = lows[0].price - 0.1 * atr
        # VAL if below entry
        if vp.get("val") and vp["val"] < entry:
            candidates["val"] = vp["val"] - 0.1 * atr
        # LVN nearest below entry
        lvns = sorted([z for z in vp.get("lvn_zones", []) if z["high"] < entry],
                      key=lambda z: z["high"], reverse=True)
        if lvns:
            candidates["lvn"] = lvns[0]["low"] - 0.1 * atr
        candidates["atr_floor"] = entry - 1.5 * atr

        valid = [(k, v) for k, v in candidates.items() if v is not None and v < entry]
        if not valid:
            return {"price": entry - 1.5 * atr, "basis": "atr_floor_fallback",
                    "distance_pct": -1.5 * atr / entry * 100, "distance_atr": 1.5,
                    "candidates": candidates}
        # Tightest valid stop = max
        chosen_key, chosen_price = max(valid, key=lambda kv: kv[1])
        distance_atr = (entry - chosen_price) / atr
        # ATR floor: minimum 0.5 ATR
        if distance_atr < 0.5:
            chosen_price = entry - 0.5 * atr
            chosen_key = "atr_floor_widened"
            distance_atr = 0.5
        return {
            "price": round(chosen_price, 2),
            "basis": chosen_key,
            "distance_pct": round((entry - chosen_price) / entry * -100, 2),
            "distance_atr": round(distance_atr, 2),
            "candidates": {k: round(v, 2) for k, v in candidates.items()},
        }
    # Short direction omitted Phase 1
    return {"price": entry * 1.05, "basis": "stub_short", "candidates": {}}


# ════════════════════════════════════════════════════════════════════════
# POSITION SIZING
# ════════════════════════════════════════════════════════════════════════
def compute_sizing(entry: float, stop_price: float, equity: float,
                   risk_pct: float, single_pos_cap_pct: float) -> dict:
    """Risk-based sizing with single-position cap."""
    risk_dollars = equity * risk_pct
    risk_per_share = abs(entry - stop_price)
    if risk_per_share <= 0:
        return {"shares": 0, "reason": "invalid_risk"}
    raw_shares = math.floor(risk_dollars / risk_per_share)
    max_pos_dollars = equity * single_pos_cap_pct
    max_shares = math.floor(max_pos_dollars / entry)
    shares = max(0, min(raw_shares, max_shares))
    return {
        "shares": shares,
        "position_value": round(shares * entry, 2),
        "max_loss_dollars": round(shares * risk_per_share, 2),
        "pct_of_equity": round(shares * entry / equity, 4),
        "size_constrained_by": "single_position_cap" if max_shares < raw_shares else "risk_per_trade",
    }


# ════════════════════════════════════════════════════════════════════════
# TOP-LEVEL ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════
def analyze_trade(ticker: str, direction: str = "long", mode: str = "position",
                  equity: float = 25000.0, current_price: Optional[float] = None,
                  df_override: Optional["pd.DataFrame"] = None) -> TradeAnalysis:
    """Phase 1 top-level: load OHLCV, run sub-modules, select targets, classify, emit schema.

    df_override: optional point-in-time OHLCV frame. When provided, the internal
    fetch_ohlcv_with_failover call is skipped — callers MUST pre-truncate the
    frame to the as-of date to avoid look-ahead leakage. Backtest path uses this.
    Live path leaves it None (engine fetches today's data).
    """
    cfg = MODES[mode]

    # M2.3 · Short-direction gate. Engine math is long-bias (entry/stop/target
    # progression assumes upward direction). Shorts will land in a future phase;
    # for now reject cleanly so callers know to fall back to legacy ATR shorts.
    if direction != "long":
        return _reject(ticker, mode, direction,
                       "short_not_supported_v1 — use legacy ATR engine for shorts")

    # 1. Load OHLCV — either point-in-time override (backtest) or fresh fetch (live)
    if df_override is not None and len(df_override) >= 30:
        df = df_override.copy()
    else:
        sys.path.insert(0, "/Volumes/MyMacDisk/Claude Skills/SwingTrade")
        try:
            from data_fetcher import fetch_ohlcv_with_failover
            df, tier = fetch_ohlcv_with_failover(ticker, days=max(cfg["lookback_days"] * 2, 400))
        except Exception as e:
            return _reject(ticker, mode, direction, f"data_load_failed: {e}")
    if df is None or len(df) < 30:
        return _reject(ticker, mode, direction, "insufficient_bars")

    # Trim to lookback window
    df_full = df.copy()
    df = df.tail(cfg["lookback_days"]).copy()

    # 2. Current price
    entry = float(current_price) if current_price else float(df["Close"].iloc[-1])

    # 3. ATR (guardrail)
    atr = compute_atr(df, period=cfg["atr_period"])
    if atr <= 0:
        return _reject(ticker, mode, direction, "atr_invalid")

    # M2.3 · ETF detection — lower swing-structure floor + emit graceful-degrade
    # warning. ETFs typically have smoothed price action and produce fewer
    # qualifying swings than single-name equities.
    is_etf = _is_etf(ticker)
    pre_warnings = []
    if is_etf:
        pre_warnings.append("etf_degraded — fewer structural pivots expected; "
                            "targets may be wider/less precise than equity counterparts")

    # 4. Structure (swings, BOS/CHoCH)
    swings = find_swing_pivots(df, fractal_window=cfg["fractal_window"])
    # Hard floor of 3 swings for non-ETFs; ETFs degrade to 2 with a warning.
    min_swings = 2 if is_etf else 3
    if len(swings) < min_swings:
        return _reject(ticker, mode, direction, "insufficient_structure")
    structure_info = detect_bos_choch(swings, entry)

    # 5. Liquidity
    eq_highs = find_equal_highs(swings)
    eq_lows = find_equal_lows(swings)

    # 6. Volume profile
    vp = compute_volume_profile(df, atr=atr)

    # 7. Anchored VWAP
    anchors = find_anchor_dates(df_full)

    # 8. Stop
    stop_info = compute_stop(entry, atr, direction, swings, vp)
    stop_price = stop_info["price"]

    # 9. Build candidate levels
    raw_sources = build_candidate_levels(
        entry, atr, direction,
        eq_highs, eq_lows,
        vp, anchors, swings,
        df_full, cfg,
    )

    # 10. Cluster into candidates
    candidates = cluster_levels_and_score(raw_sources, atr)
    candidates.sort(key=lambda c: c.price)

    # 11. Select T1 / T2
    t1_c, t2_c = select_targets(candidates, entry, stop_price, mode)

    # 12. Classify behavior + estimate p_reach
    def cand_to_target(c: Candidate, entry: float, risk: float, stop: float) -> Target:
        beh, action = classify_behavior(c)
        p = estimate_p_reach(c, mode)
        return Target(
            price=round(c.price, 2),
            r_multiple=round((c.price - entry) / risk, 2),
            distance_pct=round((c.price - entry) / entry * 100, 2),
            confluence=round(c.confluence, 2),
            sources=[asdict(s) for s in c.sources],
            behavior=beh,
            action=action,
            p_reach=p["median"],
            p_reach_source=p,
        )

    risk = entry - stop_price
    t1 = cand_to_target(t1_c, entry, risk, stop_price) if t1_c else None
    t2 = cand_to_target(t2_c, entry, risk, stop_price) if t2_c else None

    # 13. Decision logic
    decision = "trade" if t1 else ("reject" if mode != "invest" else "wait")
    warnings = list(pre_warnings)  # carry ETF/etc. warnings forward
    if t1 is None and mode != "invest":
        warnings.append("no_target_meets_minimum_r")
    if stop_info["distance_atr"] > 3.0:
        warnings.append("stop_distance_exceeds_3atr")
    if structure_info.get("last_choch") and structure_info["trend"] == "uptrend":
        warnings.append("choch_against_long")

    # M2.3 · Catalyst (earnings imminent) flag — non-blocking, surfaces context
    # only. Engine logic unchanged in v1; future phases will use implied move +
    # option walls for catalyst-mode targets.
    earn_days = _earnings_days_until(ticker)
    catalyst_info = None
    if earn_days is not None and earn_days <= 7:
        warnings.append(f"earnings_imminent — report in {earn_days}d; "
                        "structural targets may be invalidated by gap")
        catalyst_info = {"type": "earnings", "days_until": int(earn_days)}

    # M2.3 · INVEST interim stub. When invest-mode produces no T1 (no swing-
    # structure target meets criteria), fall back to analyst PT × 1.0/1.3 so
    # the consumer has SOMETHING to render. Flagged so UI can show a banner.
    invest_stub_active = False
    if mode == "invest" and t1 is None:
        pt = _analyst_pt_fallback(ticker)
        if pt and pt.get("mean"):
            _pt = float(pt["mean"])
            if _pt > entry:
                # Synthesise minimal Target objects without weight-based sources
                stub_source = Source(type="ANALYST_PT",
                                     price=_pt,
                                     weight=0.0,
                                     detail={"note": "interim_invest_stub",
                                             "raw_mean": _pt})
                t1 = Target(
                    price=round(_pt, 2),
                    r_multiple=round((_pt - entry) / max(risk, 0.01), 2),
                    distance_pct=round((_pt - entry) / entry * 100, 2),
                    confluence=0.0,
                    sources=[asdict(stub_source)],
                    behavior="STRUCTURAL",
                    action="invest_interim_hold_to_PT",
                    p_reach=None,
                    p_reach_source={},
                )
                t2 = Target(
                    price=round(_pt * 1.30, 2),
                    r_multiple=round((_pt * 1.30 - entry) / max(risk, 0.01), 2),
                    distance_pct=round((_pt * 1.30 - entry) / entry * 100, 2),
                    confluence=0.0,
                    sources=[asdict(stub_source)],
                    behavior="STRUCTURAL",
                    action="invest_interim_stretch",
                    p_reach=None,
                    p_reach_source={},
                )
                decision = "trade"
                invest_stub_active = True
                warnings.append("invest_interim_analyst_pt — targets are "
                                "analyst-consensus PT × 1.0/1.3 (not structural). "
                                "IV-based targets pending Phase 2.")

    # 14. Sizing
    risk_pcts = {"swing": 0.005, "position": 0.004, "invest": 0.0025}
    caps = {"swing": 0.10, "position": 0.12, "invest": 0.20}
    sizing = compute_sizing(entry, stop_price, equity, risk_pcts[mode], caps[mode])

    # 15. Confidence (0-1 score · 4 components)
    conf_components = {
        "trend_alignment": 0.9 if structure_info["trend"] == "uptrend" else 0.4 if structure_info["trend"] == "range" else 0.2,
        "confluence_quality": min(1.0, (t1.confluence / 8.0) if t1 else 0),
        "volume_confirmation": 0.7,  # Phase 2: real RVOL/volume_trend
        "rr_quality": min(1.0, (t1.r_multiple / 3.0) if t1 else 0),
    }
    confidence = {
        "score": round(sum(conf_components.values()) / 4, 2),
        "components": conf_components,
    }

    # 16. Assemble
    return TradeAnalysis(
        ticker=ticker.upper(),
        mode=mode,
        timestamp=datetime.utcnow().isoformat() + "Z",
        price_at_analysis=round(entry, 2),
        direction=direction,
        decision=decision,
        entry={
            "price": round(entry, 2),
            "zone": {"low": round(entry - atr * 0.3, 2), "high": round(entry + atr * 0.1, 2)},
            "basis": "current_price",
            "atr": round(atr, 2),
        },
        stop=stop_info,
        t1=t1,
        t2=t2,
        sizing=sizing,
        context={
            "trend": structure_info["trend"],
            "last_bos": structure_info["last_bos"],
            "last_choch": structure_info["last_choch"],
            "in_value_area": (vp.get("val") or 0) <= entry <= (vp.get("vah") or float("inf")),
            "key_levels": {
                "poc": round(vp["poc"], 2) if vp.get("poc") else None,
                "vah": round(vp["vah"], 2) if vp.get("vah") else None,
                "val": round(vp["val"], 2) if vp.get("val") else None,
                "anchors": anchors,
                "buyside_liquidity": [round(eh["price"], 2) for eh in eq_highs][:5],
                "sellside_liquidity": [round(el["price"], 2) for el in eq_lows][:5],
                "hvn_zones": [{"center": round(z["center"], 2), "vol_pct": round(z["vol_pct"], 3)}
                              for z in vp.get("hvn_zones", [])][:5],
                "lvn_zones": [{"low": round(z["low"], 2), "high": round(z["high"], 2)}
                              for z in vp.get("lvn_zones", [])][:5],
            },
        },
        confidence=confidence,
        warnings=warnings,
        is_etf=is_etf,
        catalyst=catalyst_info,
        invest_stub=invest_stub_active,
    )


def _reject(ticker: str, mode: str, direction: str, reason: str) -> TradeAnalysis:
    return TradeAnalysis(
        ticker=ticker.upper(), mode=mode, timestamp=datetime.utcnow().isoformat() + "Z",
        price_at_analysis=0, direction=direction, decision="reject",
        entry={}, stop={}, t1=None, t2=None, sizing={},
        context={"rejection_reason": reason},
        confidence={"score": 0, "components": {}},
        warnings=[reason],
    )


# ════════════════════════════════════════════════════════════════════════
# JSON serialization helper
# ════════════════════════════════════════════════════════════════════════
def to_json(analysis: TradeAnalysis) -> dict:
    d = asdict(analysis)
    # Convert Target dataclass already converted via asdict
    return d


# ════════════════════════════════════════════════════════════════════════
# CACHE LAYER · 12h TTL JSON file per ticker × mode
# ════════════════════════════════════════════════════════════════════════
def _cache_path(ticker: str, mode: str) -> Path:
    """cache/target_engine/{TICKER}_{MODE}.json"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{ticker.upper()}_{mode}.json"


def _cache_is_fresh(path: Path, ttl: int = CACHE_TTL_SECONDS) -> bool:
    """File exists AND age < ttl seconds."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl


def _cache_read(path: Path) -> Optional[dict]:
    """Load JSON from disk · None if corrupt."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_write(path: Path, payload: dict) -> None:
    """Atomic write via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    tmp.replace(path)


def analyze_trade_cached(ticker: str, direction: str = "long", mode: str = "position",
                         equity: float = 25000.0,
                         force_refresh: bool = False,
                         df_override: Optional["pd.DataFrame"] = None) -> dict:
    """Cached wrapper around analyze_trade · returns dict (JSON-ready).

    - Reads from cache/target_engine/{TICKER}_{MODE}.json if file is < 12h old
    - Otherwise runs the engine, writes to cache, returns
    - force_refresh=True bypasses cache entirely
    - df_override: when set, bypasses cache (point-in-time backtest mode) — the
      cache is keyed only by ticker/mode and would corrupt the live cache if
      mixed with historical results.
    - Always returns a dict (never raises) · errors land in `decision='reject'`
    """
    use_cache = df_override is None
    path = _cache_path(ticker, mode)
    if use_cache and not force_refresh and _cache_is_fresh(path):
        cached = _cache_read(path)
        if cached is not None:
            cached["_cache"] = {"status": "hit", "age_sec": int(time.time() - path.stat().st_mtime)}
            return cached

    # Cache miss (or backtest mode) · run engine
    t0 = time.time()
    try:
        analysis = analyze_trade(ticker, direction=direction, mode=mode,
                                 equity=equity, df_override=df_override)
        payload = to_json(analysis)
    except Exception as e:
        # Engine crashed · return rejection so caller has something coherent
        payload = {
            "ticker": ticker.upper(),
            "mode": mode,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "price_at_analysis": 0,
            "direction": direction,
            "decision": "reject",
            "warnings": [f"engine_exception: {type(e).__name__}: {e}"],
            "_cache": {"status": "miss" if use_cache else "bypass:pit",
                       "computed_in_sec": round(time.time() - t0, 2)},
        }
        return payload

    payload["_cache"] = {"status": "miss" if use_cache else "bypass:pit",
                         "computed_in_sec": round(time.time() - t0, 2)}
    if use_cache:
        _cache_write(path, payload)
    return payload


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Structural target engine · §8 schema output")
    ap.add_argument("ticker", help="ticker symbol (e.g., ROST, AVGO, AAPL)")
    ap.add_argument("mode", choices=["swing", "position", "invest"], help="trading mode")
    ap.add_argument("--equity", type=float, default=25000.0, help="account equity USD")
    ap.add_argument("--direction", choices=["long", "short"], default="long")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    ap.add_argument("--brief", action="store_true", help="print 1-line summary instead of JSON")
    args = ap.parse_args()

    analysis = analyze_trade(args.ticker, direction=args.direction, mode=args.mode, equity=args.equity)
    if args.brief:
        a = to_json(analysis)
        t1 = a.get("t1")
        t2 = a.get("t2")
        print(f"{a['ticker']} {a['mode']:9s} decision={a['decision']:7s} "
              f"px={a['price_at_analysis']:8.2f} "
              f"stop={(a.get('stop') or {}).get('price','-'):>8} "
              f"T1={(t1 or {}).get('price','-'):>8} ({(t1 or {}).get('r_multiple','-')}R conf {(t1 or {}).get('confluence','-')}) "
              f"T2={(t2 or {}).get('price','-'):>8} ({(t2 or {}).get('r_multiple','-')}R conf {(t2 or {}).get('confluence','-')}) "
              f"conf_score={a['confidence'].get('score','-')}")
    else:
        print(json.dumps(to_json(analysis), indent=2 if args.pretty else None, default=str))


if __name__ == "__main__":
    main()
