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
# Schema version — bump whenever the serialized payload shape changes so all
# pre-existing on-disk cache files are treated as stale automatically (avoids
# manually deleting the regenerable cache dir). N=2 added t3 + new sources +
# reachability (Phase 1 upgrade). A cache file missing _schema or carrying an
# older _schema is regenerated on next analyze_trade_cached call.
CACHE_SCHEMA_VERSION = 2

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
        # FIB un-dropped 2026-06-08 (elevated to bull-stretch weight); AVWAP_52
        # stays out (anchor too far for a 2-5d hold), FVG stays out (noise).
        "sources_drop": {"AVWAP_52", "FVG"},
        # Horizon-conditional NEW anchors that build for this mode. See
        # _gather_horizon_sources(). swing draws on near-term supply + 4H Fib +
        # intermediate-degree EW only.
        "extra_sources": {"OB", "EW_INT", "FIB_4H"},
        # expected bars over a typical hold — feeds the reachability volatility
        # budget (ATR × expected_bars vs distance-to-target).
        "expected_bars": 5,
        "ew_mode": "SWING",     # pattern_engines.detect degree key
        # Horizon reach cap (3-tier): a source must sit within
        #   max(ATR×max_reach_atr, entry×min_reach_pct)   [volatility-aware floor]
        # but NEVER beyond entry×hard_reach_pct            [absolute ceiling].
        # The floor lets low-ATR names still reach a structural level; the hard
        # ceiling stops a high-ATR name (INTC, 8.6%/day) from anchoring a 20%+
        # swing target. Together they kill the +169%/+281% legacy poisoning.
        # Volatility-aware floor caps low-ATR names near ~3 ATR; the hard ceiling
        # (20%) prevents stale far-out swing/52w highs from anchoring a target.
        # 20% looks high vs a calm name but for a 8.6%-daily-ATR name (INTC) it is
        # only ~2.3 ATR over a 5-bar hold — reachable. The legacy bug was +169%.
        "max_reach_atr": 3.0,    # ~3 daily ATR over a 2-5d hold
        "min_reach_pct": 0.06,   # always allow at least 6%
        "hard_reach_pct": 0.20,  # SOFT reach cap — swing rarely reaches >20%
        # POISON ceiling (two-tier guard, 2026-06-08): a TRUE outlier is a stale
        # high-spike far above the soft cap (NFLX +1115%, INTC +281%). Sources
        # above the poison ceiling are dropped unconditionally; sources between
        # the soft cap and the poison ceiling are KEPT-NEAREST only when nothing
        # survives the soft cap (so real structure still anchors a T1 on a
        # high-vol/extended name). Ceiling = max(entry×poison_mult, entry+poison_atr×ATR).
        "poison_mult": 1.60,     # +60% — anything beyond is a stale spike
        "poison_atr": 6.0,       # or 6 ATR, whichever is farther
    },
    "position": {
        "lookback_days": 120,
        "min_r_t1": 2.0,
        "min_r_t2": 3.0,
        "fractal_window": 5,
        "atr_period": 14,
        "primary_tf": "daily",
        "sources_drop": set(),
        # position: multi-TF Fib (4H + daily) + OB + intermediate EW (+ major if
        # the weekly count yields one) on top of the existing structure stack.
        "extra_sources": {"OB", "EW_INT", "EW_MAJ", "FIB_4H"},
        "expected_bars": 20,
        "ew_mode": "POSITION",
        "max_reach_atr": 10.0,    # 1-6mo hold has room to run
        "min_reach_pct": 0.15,
        "hard_reach_pct": 0.60,   # 60% SOFT reach cap for position
        "poison_mult": 2.20,      # +120% — beyond is a stale spike for a 1-6mo hold
        "poison_atr": 18.0,
    },
    "invest": {
        "lookback_days": 504,
        "min_r_t1": None,  # IV-based, not R-based
        "min_r_t2": None,
        "fractal_window": 8,
        "atr_period": 21,
        "primary_tf": "daily",
        "sources_drop": {"FVG"},  # FVG too short-term for 1y+
        # invest: long-horizon gravity — EW major (Primary degree) + Fib ext on
        # top of the existing HVN/VAH/AVWAP/BSL/SWING stack. No 4H (irrelevant).
        "extra_sources": {"EW_INT", "EW_MAJ"},
        "expected_bars": 120,
        "ew_mode": "INVESTMENT",
        # invest reaches farther but a 504-bar lookback can catch an anomalous
        # old high (NFLX $998 from a pre-split era) → +1000% nonsense. Generous
        # floor, finite hard ceiling to drop those poisoned levels.
        "max_reach_atr": 35.0,
        "min_reach_pct": 0.40,
        "hard_reach_pct": 1.20,   # 120% SOFT reach cap — long-horizon, not absurd
        # invest poison ceiling: 504-bar lookback can catch a pre-split / pre-era
        # high (NFLX $998) → +1000% nonsense. 4× entry is generous for a 1y+ hold
        # yet still kills the stale-spike poison.
        "poison_mult": 4.00,      # +300% absolute outlier ceiling for invest
        "poison_atr": 60.0,
    },
}

SOURCE_WEIGHTS = {
    "BSL": 3.0,         # equal-highs liquidity pool (touches >= 2)
    "OB": 2.5,          # bear order block = institutional supply (scaled by Wilson LB)
    "EW_MAJ": 2.5,      # Elliott primary-degree wave objective (long-horizon gravity)
    "HVN": 2.5,         # High Volume Node center
    "SWING": 2.5,       # prior swing high (BOS anchor)
    "VAH": 2.0,         # Value Area High
    "AVWAP_52": 2.0,    # AVWAP from 52w-high
    "EW_INT": 2.0,      # Elliott intermediate-degree wave objective
    "FIB_4H": 1.5,      # 4H Fibonacci extension (intraday-refined upside)
    "AVWAP_EARN": 1.5,  # AVWAP from last earnings
    "FVG": 1.5,         # opposing fair value gap
    "FIB": 1.5,         # daily Fibonacci extension (1.618 / 2.618) — bull-stretch
    "FIB_D": 1.0,       # explicit daily Fib (alias-band for multi-TF clustering)
    "ROUND": 1.0,       # round number cluster ($X00, $X50)
}

# Behavior classifier rules
MAGNET_SOURCES = {"HVN", "EW_INT", "EW_MAJ"}  # HVN center / POC + EW wave objectives
REJECTION_SOURCES = {"VAH", "AVWAP_52", "FVG", "OB"}  # mean-revert / overhead supply
MIXED_SOURCES = {"BSL", "SWING", "FIB", "FIB_4H", "FIB_D"}  # liquidity / fib go either way

# ── Overhead-supply gate (2026-06-14) ────────────────────────────────────────
# Path-order principle: T1 is the FIRST unbroken supply price must clear — the
# engine must never leapfrog a nearer wall to a higher-R level (the FTNT bug:
# T1 jumped past the $150 double top to a stale VAH at $165). HARD_SUPPLY_TYPES
# are the source types that constitute a genuine wall (prior committed supply):
#   BSL   = equal-highs (double/triple top — the strongest cap)
#   SWING = prior swing high
#   OB    = bear order block (institutional supply)
#   VAH   = value-area high
# HVN (magnet, price gravitates not rejects), Fib/Round/AVWAP (projections, not
# committed supply) are intentionally excluded. When the nearest such wall sits
# BELOW the min-R T1 floor, it still becomes T1 with its honest (often sub-floor)
# R:R — which flows into confidence.rr_quality so the score reflects the wall,
# never a leapfrogged target (Option 3 — cap-and-reflect, not hard-reject).
HARD_SUPPLY_TYPES = {"BSL", "SWING", "OB", "VAH"}


def _overhead_gate_enabled() -> bool:
    """Read config/config.json → overhead_supply_gate._enabled once (default ON).
    Reversible kill-switch without code changes; never fails the engine.
    """
    cached = getattr(_overhead_gate_enabled, "_cache", None)
    if cached is not None:
        return cached
    val = True
    try:
        import json as _json, os as _os
        _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                           "config", "config.json")
        with open(_p) as _f:
            _c = _json.load(_f)
        val = bool((_c.get("overhead_supply_gate") or {}).get("_enabled", True))
    except Exception:
        val = True  # default ON — the leapfrog is a correctness bug, not an opt-in
    _overhead_gate_enabled._cache = val
    return val


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
    t3: Optional[Target]          # bull-stretch (Fib 1.618/2.618 or EW W5 ext) — armed only on momentum + reachability
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
# SUB-MODULE 1b · Momentum confirmers (LOCAL) — MACD + Wilder RSI
# ════════════════════════════════════════════════════════════════════════
# These are REACHABILITY confirmers, NOT structural anchors. They never define a
# target PRICE — they only adjust p_reach and a confidence component, per the
# horizon-conditional design (confirmers gate "can we get there", not "where").
# Hand-rolled with pandas/numpy only — no new deps (ta is not imported here).
def _ema(series: "pd.Series", span: int) -> "pd.Series":
    return series.ewm(span=span, adjust=False).mean()


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
                 signal: int = 9) -> dict:
    """MACD(12,26,9). Returns {hist, hist_prev, line, signal, rising} on the
    last bar. `rising` = histogram slope over last bar > 0. Empty/short → zeros.
    """
    close = df["Close"]
    if len(close) < slow + signal:
        return {"hist": 0.0, "hist_prev": 0.0, "line": 0.0, "signal": 0.0, "rising": False}
    line = _ema(close, fast) - _ema(close, slow)
    sig = _ema(line, signal)
    hist = (line - sig)
    h0 = float(hist.iloc[-1])
    h1 = float(hist.iloc[-2]) if len(hist) >= 2 else h0
    return {"hist": h0, "hist_prev": h1, "line": float(line.iloc[-1]),
            "signal": float(sig.iloc[-1]), "rising": h0 > h1}


def compute_rsi(df: pd.DataFrame, period: int = 14) -> dict:
    """Wilder RSI(14). Returns {rsi, bearish_divergence} on the last bar.
    bearish_divergence: price made a higher high over the last `period` bars but
    RSI made a lower high — a classic far-target-reachability penalty.
    """
    close = df["Close"]
    if len(close) < period + 2:
        return {"rsi": 50.0, "bearish_divergence": False}
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing via ewm(alpha=1/period)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.fillna(100.0)
    cur_rsi = float(rsi.iloc[-1])

    # bearish divergence over the last `period` bars
    bearish_div = False
    try:
        win = min(period, len(close) - 1)
        px = close.iloc[-win:]
        rs_win = rsi.iloc[-win:]
        half = win // 2
        if half >= 2:
            px_recent_hi = float(px.iloc[half:].max())
            px_prior_hi = float(px.iloc[:half].max())
            rsi_recent_hi = float(rs_win.iloc[half:].max())
            rsi_prior_hi = float(rs_win.iloc[:half].max())
            if px_recent_hi > px_prior_hi and rsi_recent_hi < rsi_prior_hi:
                bearish_div = True
    except Exception:
        bearish_div = False
    return {"rsi": cur_rsi, "bearish_divergence": bearish_div}


def compute_reachability(df: pd.DataFrame, entry: float, target_price: float,
                         atr: float, mode: str) -> dict:
    """Probability-style multiplier (0..1) that an upside target is reachable
    within the mode's typical hold, blending three confirmers:

      1. Volatility budget  — ATR × expected_bars(mode) vs distance(entry→target).
         budget_ratio = budget / distance ; squashed so 1× budget ≈ 0.5, far
         targets decay toward 0, near targets saturate toward 1.
      2. MACD(12,26,9)      — positive/rising histogram supports upside;
         negative/falling penalizes.
      3. RSI(14)            — mid-range (45-65) ideal for continuation; >75 or a
         bearish divergence penalizes the reachability of FAR targets.

    Returns {score, budget, budget_ratio, macd_factor, rsi_factor,
             vol_factor, macd, rsi}. The caller MULTIPLIES p_reach by `score`
    and feeds it into a `momentum_reachability` confidence component. It NEVER
    changes a target price (design contract).
    """
    cfg = MODES.get(mode, MODES["position"])
    expected_bars = cfg.get("expected_bars", 20)
    dist = max(1e-9, abs(target_price - entry))
    budget = max(1e-9, atr * expected_bars)
    budget_ratio = budget / dist

    # Volatility factor — logistic on budget_ratio centred at ~1.0 budget.
    # ratio 1.0 → ~0.5, ratio 2.0 → ~0.78, ratio 0.4 → ~0.21.
    vol_factor = 1.0 / (1.0 + math.exp(-1.6 * (budget_ratio - 1.0)))
    vol_factor = max(0.05, min(0.97, vol_factor))

    macd = compute_macd(df)
    rsi = compute_rsi(df)

    # MACD factor — supportive when hist>0, extra credit when also rising.
    if macd["hist"] > 0:
        macd_factor = 1.10 if macd["rising"] else 1.00
    else:
        macd_factor = 0.80 if macd["rising"] else 0.65

    # RSI factor — band logic. Far targets get the overbought/divergence penalty;
    # near targets (already inside budget) are less sensitive.
    r = rsi["rsi"]
    far = budget_ratio < 1.0  # target sits beyond the typical volatility budget
    if 45.0 <= r <= 65.0:
        rsi_factor = 1.05
    elif 65.0 < r <= 75.0:
        rsi_factor = 0.95
    elif r > 75.0:
        rsi_factor = 0.70 if far else 0.85
    elif 35.0 <= r < 45.0:
        rsi_factor = 0.90
    else:  # r < 35 — washed out; bounce possible but momentum not confirming up
        rsi_factor = 0.80
    if rsi["bearish_divergence"] and far:
        rsi_factor *= 0.80

    score = vol_factor * macd_factor * rsi_factor
    score = max(0.03, min(1.0, score))
    return {
        "score": round(score, 3),
        "budget": round(budget, 2),
        "budget_ratio": round(budget_ratio, 2),
        "vol_factor": round(vol_factor, 3),
        "macd_factor": round(macd_factor, 3),
        "rsi_factor": round(rsi_factor, 3),
        "macd": {"hist": round(macd["hist"], 4), "rising": macd["rising"]},
        "rsi": {"rsi": round(rsi["rsi"], 1), "bearish_divergence": rsi["bearish_divergence"]},
    }


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
def _align_ts_to_index(ts: "pd.Timestamp", index) -> "pd.Timestamp":
    """Localize/strip a Timestamp so it can be compared against `index` without
    raising "Invalid comparison between dtype=datetime64[ns, UTC] and Timestamp"
    when the DataFrame index is tz-aware (EODHD frames arrive UTC-aware)."""
    idx_tz = getattr(index, "tz", None)
    if idx_tz is not None and ts.tzinfo is None:
        return ts.tz_localize(idx_tz)
    if idx_tz is None and ts.tzinfo is not None:
        return ts.tz_localize(None)
    return ts


def compute_anchored_vwap(df: pd.DataFrame, anchor_date: str) -> Optional[float]:
    """Volume-weighted typical price from anchor_date through end."""
    if df.empty:
        return None
    anchor_ts = _align_ts_to_index(pd.to_datetime(anchor_date), df.index)
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
    ytd_start = _align_ts_to_index(pd.Timestamp(f"{year}-01-01"), df.index)
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
# SUB-MODULE 8 · Horizon-conditional anchor sources (NEW — 2026-06-08)
# ════════════════════════════════════════════════════════════════════════
# Each helper wraps an external sub-engine in try/except and returns a list of
# Source objects (upside levels > entry for longs). analyze_trade appends these
# to raw_sources BEFORE clustering, so they flow through the SAME confluence
# engine as the base structural sources. ALL guarded — a sub-engine failure must
# never crash analyze_trade; it degrades to base behavior + a warning.

def gather_ob_sources(df_full: "pd.DataFrame", entry: float,
                      weekly_df: Optional["pd.DataFrame"] = None) -> tuple:
    """Bear order blocks above entry → upside supply targets (REJECTION).

    Returns (sources, bull_ob_stops, warning):
      - sources       : list[Source] for bear_ob centers above entry
      - bull_ob_stops : list[float] of bull_ob highs BELOW entry (demand zones —
                        fed into compute_stop as extra structural stop candidates)
      - warning       : str | None

    OB source weight is scaled by the zone-type Wilson lower-bound win-rate when
    historical stats are available (validated supply weighs more): weight =
    base × max(0.3, wilson_lb_fraction). If stats unavailable, flat base weight.
    """
    sources: list = []
    bull_stops: list = []
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import smc_engine as _smc
        zones = _smc.detect_smc_zones(df_full, weekly_df=weekly_df)
        obs = zones.get("order_blocks", []) or []

        # Wilson-LB scaling (best-effort — heavy sweep, guarded + size-gated).
        ob_wlb = None
        try:
            if df_full is not None and len(df_full) >= 90:
                hr = _smc.compute_smc_hit_rates(df_full, "TE")
                ob_stat = (hr or {}).get("order_blocks", {})
                if ob_stat.get("total", 0) >= 10:
                    ob_wlb = float(ob_stat.get("wilson_lb", 0.0)) / 100.0
        except Exception:
            ob_wlb = None
        weight_scale = max(0.3, ob_wlb) if ob_wlb is not None else 1.0
        base_w = SOURCE_WEIGHTS["OB"] * weight_scale

        for ob in obs:
            kind = ob.get("kind")
            lo = ob.get("low")
            hi = ob.get("high")
            if lo is None or hi is None:
                continue
            center = (float(lo) + float(hi)) / 2.0
            if kind == "bear_ob" and center > entry:
                sources.append(Source("OB", base_w, center,
                                      {"kind": kind, "low": float(lo), "high": float(hi),
                                       "date": ob.get("date"),
                                       "wilson_lb": round(ob_wlb, 3) if ob_wlb is not None else None}))
            elif kind == "bull_ob" and float(hi) < entry:
                bull_stops.append(float(hi))
        return sources, bull_stops, None
    except Exception as e:
        return [], [], f"ob_source_failed: {type(e).__name__}: {e}"


def gather_ew_sources(ticker: str, entry: float, mode_cfg: dict,
                      extra: set) -> tuple:
    """Elliott Wave wave-objective targets above entry → MAGNET sources.

    Uses pattern_engines.detect('elliott', ticker, ew_mode). Honesty contract:
    when state != 'real' (no clean count) we emit NO EW source. Degree drives
    the source type: intermediate → EW_INT, primary → EW_MAJ. Only the EW types
    enabled in mode_cfg['extra_sources'] are kept.

    Returns (sources, warning).
    """
    sources: list = []
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import pattern_engines as _pe
        ew = _pe.detect("elliott", ticker, mode_cfg.get("ew_mode", "SWING")) or {}
        if ew.get("state") != "real":
            return [], None  # honest skip — no clean count
        degree = ew.get("degree", "intermediate")
        if degree == "primary":
            stype, sweight = "EW_MAJ", SOURCE_WEIGHTS["EW_MAJ"]
        else:
            stype, sweight = "EW_INT", SOURCE_WEIGHTS["EW_INT"]
        if stype not in extra:
            return [], None
        for t in (ew.get("targets") or []):
            price = t.get("price")
            # _fib_targets prices are floats for point targets, strings for
            # zones ("12.3–14.5"). Keep only numeric upside levels.
            if not isinstance(price, (int, float)):
                continue
            if float(price) <= entry:
                continue
            sources.append(Source(stype, sweight, float(price),
                                  {"label": t.get("label"), "basis": t.get("basis"),
                                   "degree": degree, "ew_conf": t.get("conf")}))
        return sources, None
    except Exception as e:
        return [], f"ew_source_failed: {type(e).__name__}: {e}"


def _fib_ext_from_bars(df: "pd.DataFrame", entry: float, fractal_window: int = 5) -> list:
    """Run the existing swing detector + fib_extensions on an arbitrary-TF frame.
    Returns numeric extension prices above entry (list[float])."""
    out: list = []
    try:
        if df is None or len(df) < (2 * fractal_window + 2):
            return out
        sw = find_swing_pivots(df, fractal_window=fractal_window)
        for f in fib_extensions(sw, direction="long"):
            if f > entry:
                out.append(float(f))
    except Exception:
        return out
    return out


def gather_fib_4h_sources(ticker: str, entry: float) -> tuple:
    """4H Fibonacci extensions above entry → MIXED (bull-stretch) sources.

    Pulls Schwab 4H bars via pattern_data.get_bars(mode='SWING_4H'). Schwab-only,
    no failover — empty/None degrades gracefully (no source, warning surfaced).

    Returns (sources, warning).
    """
    sources: list = []
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import pattern_data as _pd
        df4, tier, _meta = _pd.get_bars(ticker, mode="SWING_4H", enriched=False)
        if df4 is None or getattr(df4, "empty", True):
            return [], f"fib_4h_unavailable: 4H bars not available ({tier})"
        for f in _fib_ext_from_bars(df4, entry, fractal_window=5):
            sources.append(Source("FIB_4H", SOURCE_WEIGHTS["FIB_4H"], f, {"tf": "4h"}))
        return sources, None
    except Exception as e:
        return [], f"fib_4h_failed: {type(e).__name__}: {e}"


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


def select_targets(candidates: list, entry: float, stop: float, mode: str,
                   atr: Optional[float] = None) -> tuple:
    """Select T1 / T2 / T3 from clustered candidates.

    Returns (t1, t2, t3) Candidate objects (any may be None).
      - T1 : highest confluence in the ≥min_r_t1 R-band
      - T2 : beyond T1, highest confluence in the ≥min_r_t2 R-band
      - T3 : beyond T2, the bull-stretch — the candidate whose source stack
             includes a stretch anchor (Fib ext or EW W5/extension); if no such
             stretch candidate exists, the highest-priced candidate beyond T2.
             T3 is only ARMED later (analyze_trade) on momentum + reachability.

    INVEST mode is now R-band-driven too: stops ARE defined (compute_stop runs
    for all long modes), so a fixed mild R floor produces real structural targets
    from the EW-major / Fib stack. The analyst-PT stub is the final fallback in
    analyze_trade only when this yields nothing.
    """
    cfg = MODES[mode]
    risk = entry - stop
    if risk <= 0:
        return None, None, None

    # INVEST has no R floor in config (was IV-based stub). Use mild structural
    # floors so long-horizon EW/Fib targets qualify without forcing the 2-3R
    # swing/position discipline onto a 1-5yr horizon.
    min_r_t1 = cfg["min_r_t1"] if cfg["min_r_t1"] is not None else 1.0
    min_r_t2 = cfg["min_r_t2"] if cfg["min_r_t2"] is not None else 2.0

    # ── Overhead-supply gate — targets follow PATH ORDER, never leapfrog a wall ─
    # The nearest unbroken HARD_SUPPLY level above entry is T1; the next is T2 —
    # even when they sit below the min-R floors. entry == current price, so any
    # level above it is by definition unbroken supply. The (often sub-floor) R:R
    # is intentional and flows into confidence.rr_quality, so the score reflects
    # the wall rather than a leapfrogged target (Option 3 — cap-and-reflect).
    #
    # Meaningful-distance floor: a wall within ~0.25 ATR of entry means price is
    # AT that level (not a forward target) — skip it and look to the next wall.
    # Falls back to a fraction of risk when ATR isn't passed.
    min_gap = (atr * 0.25) if (atr and atr > 0) else (risk * 0.15)
    walls = []
    if _overhead_gate_enabled():
        walls = [c for c in candidates
                 if c.price > entry + min_gap
                 and any(s.type in HARD_SUPPLY_TYPES for s in c.sources)]
        # Horizon scaling: a 2-15d SWING genuinely cannot ignore a wall 0.3R
        # overhead, so swing honors sub-floor walls. POSITION (1-6mo) / INVEST
        # (1-5yr) look THROUGH near-term supply — they only respect a wall that
        # already clears the horizon's min-R floor (a significant level), and
        # otherwise fall through to the R-band / projection stack.
        if mode != "swing":
            walls = [w for w in walls if (w.price - entry) / risk >= min_r_t1]
        walls.sort(key=lambda c: c.price)

    # ── T1 — nearest unbroken wall (path order); else R-band selection (blue-sky
    #         / breakout extension — reaching up to a projection level is correct).
    if walls:
        t1 = walls[0]
    else:
        t1_pool = [c for c in candidates if (c.price - entry) / risk >= min_r_t1]
        if not t1_pool:
            return None, None, None
        t1 = max(t1_pool, key=lambda c: (c.confluence, -c.price))

    # ── T2 — next unbroken wall beyond T1 (path order); else highest-confluence
    #         candidate in the ≥min_r_t2 R-band.
    next_walls = [w for w in walls if w.price > t1.price]
    if next_walls:
        t2 = next_walls[0]
    else:
        t2_pool = [c for c in candidates if c.price > t1.price and (c.price - entry) / risk >= min_r_t2]
        t2 = max(t2_pool, key=lambda c: (c.confluence, -c.price)) if t2_pool else None

    # T3: bull-stretch beyond T2 (or beyond T1 if T2 absent). Prefer candidates
    # whose source stack carries a stretch anchor (Fib extension or EW objective).
    anchor = t2.price if t2 else t1.price
    t3_pool = [c for c in candidates if c.price > anchor]
    t3 = None
    if t3_pool:
        STRETCH_TYPES = {"FIB", "FIB_4H", "FIB_D", "EW_INT", "EW_MAJ"}
        stretch_cands = [c for c in t3_pool
                         if any(s.type in STRETCH_TYPES for s in c.sources)]
        if stretch_cands:
            # nearest stretch candidate beyond the anchor (don't over-reach)
            t3 = min(stretch_cands, key=lambda c: c.price)
        else:
            # no dedicated stretch source — take the highest-confluence far level
            t3 = max(t3_pool, key=lambda c: (c.confluence, -c.price))

    return t1, t2, t3


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
                 swings: list, vp: dict, bull_ob_stops: Optional[list] = None,
                 mode: str = "position") -> dict:
    """Phase 1 stop: structural swing low (long) or swing high (short),
    with a MODE-SCALED minimum distance (fallback to entry − min_atr × ATR).

    bull_ob_stops: optional list of bull order-block highs below entry (demand
    zones). The nearest one below entry is added as a structural stop candidate —
    institutional demand is a natural close-below invalidation level.

    mode: stop width must scale with horizon — a 2-5d swing stop (~1 ATR) is
    nonsensical on a 1-5yr invest hold (normal noise stops you out). Each mode
    enforces a minimum stop distance and prefers the tightest STRUCTURAL level
    that already clears that floor (2026-06-08 fix — Overview audit).
    """
    MODE_MIN_ATR = {"swing": 1.0, "position": 2.0, "invest": 2.5}
    # Cap the stop distance per mode so a deep multi-year structural low can't blow
    # out R:R (AAPL invest picked a $193 low = 37% — too extreme; and an over-wide
    # invest stop pushes its R-band targets past the reach cap, forcing the stub).
    MODE_MAX_PCT = {"swing": 0.08, "position": 0.12, "invest": 0.14}
    min_atr = MODE_MIN_ATR.get(mode, 1.0)
    max_pct = MODE_MAX_PCT.get(mode, 0.12)
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
        # Bull order block (demand) nearest below entry
        if bull_ob_stops:
            below = sorted([p for p in bull_ob_stops if p < entry], reverse=True)
            if below:
                candidates["bull_ob"] = below[0] - 0.1 * atr
        candidates["atr_floor"] = entry - min_atr * atr

        valid = [(k, v) for k, v in candidates.items() if v is not None and v < entry]
        if not valid:
            return {"price": round(entry - min_atr * atr, 2), "basis": f"atr_floor_{mode}",
                    "distance_pct": round(-min_atr * atr / entry * 100, 2), "distance_atr": min_atr,
                    "candidates": candidates}
        # Prefer the TIGHTEST structural stop that already clears the mode floor;
        # if none is deep enough, widen to the mode's min-ATR floor.
        deep = [(k, v) for k, v in valid if (entry - v) / atr >= min_atr]
        if deep:
            chosen_key, chosen_price = max(deep, key=lambda kv: kv[1])
        else:
            chosen_key, chosen_price = f"atr_floor_{mode}", entry - min_atr * atr
        # Cap: never wider than the mode's max-% (keeps R:R sane on deep structural lows)
        min_allowed = entry * (1.0 - max_pct)
        if chosen_price < min_allowed:
            chosen_price = min_allowed
            chosen_key = f"{chosen_key}_capped_{int(max_pct*100)}pct"
        distance_atr = (entry - chosen_price) / atr
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

    # 8b. Horizon-conditional NEW anchor sources (2026-06-08). Gathered BEFORE
    # the stop so bull-OB demand zones can feed compute_stop. Every gatherer is
    # try/except-wrapped and returns a warning string on failure — analyze_trade
    # degrades to base behavior, never crashes. Which sources build per horizon
    # is gated by cfg["extra_sources"].
    extra = cfg.get("extra_sources", set())
    horizon_sources: list = []
    horizon_warnings: list = []
    bull_ob_stops: list = []

    # Order blocks (swing + position): bear OB above entry = supply target;
    # bull OB below entry = demand stop candidate.
    if "OB" in extra:
        ob_src, bull_ob_stops, ob_warn = gather_ob_sources(df_full, entry,
                                                            weekly_df=None)
        horizon_sources.extend(ob_src)
        if ob_warn:
            horizon_warnings.append(ob_warn)

    # Elliott Wave objectives (intermediate and/or major depending on horizon).
    if "EW_INT" in extra or "EW_MAJ" in extra:
        ew_src, ew_warn = gather_ew_sources(ticker, entry, cfg, extra)
        horizon_sources.extend(ew_src)
        if ew_warn:
            horizon_warnings.append(ew_warn)

    # 4H Fibonacci extensions (swing + position) — Schwab-only, degrades quietly.
    if "FIB_4H" in extra:
        fib4_src, fib4_warn = gather_fib_4h_sources(ticker, entry)
        horizon_sources.extend(fib4_src)
        if fib4_warn:
            horizon_warnings.append(fib4_warn)

    # 8. Stop (now demand-zone aware)
    stop_info = compute_stop(entry, atr, direction, swings, vp,
                             bull_ob_stops=bull_ob_stops, mode=mode)
    stop_price = stop_info["price"]

    # 9. Build base candidate levels (unchanged contract)
    raw_sources = build_candidate_levels(
        entry, atr, direction,
        eq_highs, eq_lows,
        vp, anchors, swings,
        df_full, cfg,
    )
    # 9b. Append the horizon sources so they flow through the SAME confluence
    # engine (cluster + weight) as the base structural sources.
    raw_sources.extend(horizon_sources)

    # 9c. Horizon reach cap (TWO-TIER guard, 2026-06-08) — replaces the old
    # blanket "drop everything beyond reach_cap" which threw away legitimate
    # structural levels on high-vol/extended names, leaving the UI to fall back
    # to a synthetic 3R/5R that was often WIDER than the dropped level (backwards).
    #
    #   reach_cap (SOFT)     = entry + min( max(ATR×max_reach_atr, entry×min_reach_pct),
    #                                       entry×hard_reach_pct )
    #   poison_ceiling (HARD)= entry + max( entry×poison_mult, poison_atr×ATR )
    #
    # Filter logic (longs — upside targets):
    #   • s.price > poison_ceiling  → TRUE outlier (stale spike). DROP always.
    #     This IS the NFLX +1115% / INTC +281% poison guard — preserved.
    #   • s.price <= reach_cap      → in-budget. KEEP (behaves as before).
    #   • reach_cap < s.price <= poison_ceiling → "extended". Only KEEP the
    #     single NEAREST one (smallest price>entry) AND only if NOTHING survived
    #     the soft cap above entry — so a real structural T1 still anchors instead
    #     of falling to the synthetic fallback. If the soft cap already left a
    #     candidate above entry, the extended ones stay dropped (old behavior).
    max_reach_atr = cfg.get("max_reach_atr")
    min_reach_pct = cfg.get("min_reach_pct")
    hard_reach_pct = cfg.get("hard_reach_pct")
    poison_mult = cfg.get("poison_mult")
    poison_atr = cfg.get("poison_atr")
    warnings_capped = 0
    warnings_kept_nearest = 0
    if max_reach_atr is not None and hard_reach_pct is not None:
        vol_floor = max(atr * max_reach_atr, entry * (min_reach_pct or 0.0))
        reach_cap = entry + min(vol_floor, entry * hard_reach_pct)
        # Poison ceiling — generous floor so real structure on a high-vol name is
        # not poison; falls back to the soft cap if no poison config present.
        if poison_mult is not None or poison_atr is not None:
            poison_ceiling = entry + max(entry * (poison_mult or 0.0),
                                         atr * (poison_atr or 0.0))
            # never let the poison ceiling fall below the soft cap
            poison_ceiling = max(poison_ceiling, reach_cap)
        else:
            poison_ceiling = reach_cap

        n_before = len(raw_sources)
        # Drop true outliers (poison) unconditionally.
        outliers = [s for s in raw_sources if s.price > poison_ceiling]
        survivors = [s for s in raw_sources if s.price <= poison_ceiling]
        # Partition survivors into in-budget (<=soft cap) vs extended (soft<..<=poison)
        in_budget = [s for s in survivors if s.price <= reach_cap]
        extended = [s for s in survivors if s.price > reach_cap]
        # Does the in-budget set already give us an upside anchor?
        has_upside_in_budget = any(s.price > entry for s in in_budget)
        if has_upside_in_budget or not extended:
            # Old behavior: use the in-budget set; extended ones stay dropped.
            raw_sources = in_budget
            warnings_capped = len(extended) + len(outliers)
        else:
            # Relaxed: nothing in-budget anchors upside — keep the NEAREST single
            # extended structural source so a real T1 exists instead of a wider
            # synthetic fallback. Drop the rest of the extended ones + all poison.
            extended_up = sorted((s for s in extended if s.price > entry),
                                 key=lambda s: s.price)
            keep_one = extended_up[:1]
            raw_sources = in_budget + keep_one
            warnings_kept_nearest = len(keep_one)
            warnings_capped = (len(extended) - len(keep_one)) + len(outliers)

    # 10. Cluster into candidates
    candidates = cluster_levels_and_score(raw_sources, atr)
    candidates.sort(key=lambda c: c.price)

    # 11. Select T1 / T2 / T3
    t1_c, t2_c, t3_c = select_targets(candidates, entry, stop_price, mode, atr=atr)

    # 12. Classify behavior + estimate p_reach (× momentum reachability)
    def cand_to_target(c: Candidate, entry: float, risk: float, stop: float) -> Target:
        beh, action = classify_behavior(c)
        p = estimate_p_reach(c, mode)
        # Reachability confirmer (volatility budget + MACD + RSI) MULTIPLIES the
        # structural p_reach. It NEVER changes the price (design contract).
        reach = compute_reachability(df, entry, c.price, atr, mode)
        p_final = round(max(0.02, min(0.95, p["median"] * reach["score"])), 3)
        p_src = dict(p)
        p_src["reachability"] = reach
        return Target(
            price=round(c.price, 2),
            r_multiple=round((c.price - entry) / risk, 2),
            distance_pct=round((c.price - entry) / entry * 100, 2),
            confluence=round(c.confluence, 2),
            sources=[asdict(s) for s in c.sources],
            behavior=beh,
            action=action,
            p_reach=p_final,
            p_reach_source=p_src,
        )

    risk = entry - stop_price
    t1 = cand_to_target(t1_c, entry, risk, stop_price) if t1_c else None
    t2 = cand_to_target(t2_c, entry, risk, stop_price) if t2_c else None

    # Fallback T2 — when no structural level qualifies for T2 but T1 exists,
    # synthesize an R-multiple T2 so the ladder ALWAYS shows a second target (matches
    # canonical compute_trade_plan, which always emits target2). Honest source tag.
    # Capped at the mode reach cap. (2026-06-08 Overview audit — swing T2 was missing
    # on some tickers.)
    if t2 is None and t1 is not None and risk > 0:
        _t2_r = max((cfg.get("min_r_t2") or 2.0), (t1.r_multiple or 1.0) + 1.0)
        _t2_price = entry + risk * _t2_r
        _mra, _hrp = cfg.get("max_reach_atr"), cfg.get("hard_reach_pct")
        if _mra is not None and _hrp is not None:
            _cap = entry + min(max(atr * _mra, entry * (cfg.get("min_reach_pct") or 0.0)),
                               entry * _hrp)
            _t2_price = min(_t2_price, _cap)
        if _t2_price > t1.price:
            t2 = Target(
                price=round(_t2_price, 2),
                r_multiple=round((_t2_price - entry) / risk, 2),
                distance_pct=round((_t2_price - entry) / entry * 100, 2),
                confluence=0.0,
                sources=[asdict(Source(type="R_MULTIPLE", price=_t2_price, weight=0.0,
                                       detail={"note": "synthetic_r_multiple_t2"}))],
                behavior="STRUCTURAL",
                action="scale_out_partial",
                p_reach=round(max(0.02, (t1.p_reach or 0.4) * 0.7), 3),
                p_reach_source={"note": "synthetic_t2_derate_of_t1"},
            )

    # T3 bull-stretch: ARM only when reachability(entry→t3) ≥ 0.45 AND momentum
    # confirms (MACD hist > 0). Otherwise t3 = None (additive, never blocks t1/t2).
    t3 = None
    if t3_c is not None:
        t3_reach = compute_reachability(df, entry, t3_c.price, atr, mode)
        macd_confirms = t3_reach["macd"]["hist"] > 0
        if t3_reach["score"] >= 0.45 and macd_confirms:
            t3 = cand_to_target(t3_c, entry, risk, stop_price)
            t3.action = "stretch_runner_trail_only"

    # 13. Decision logic
    decision = "trade" if t1 else ("reject" if mode != "invest" else "wait")
    warnings = list(pre_warnings)  # carry ETF/etc. warnings forward
    warnings.extend(horizon_warnings)  # surface sub-engine degradation
    if warnings_kept_nearest:
        warnings.append(
            f"extended_kept_nearest — nothing within the {mode} soft reach cap; "
            f"kept the nearest structural source between the soft cap and the "
            f"poison ceiling so a real T1 anchors")
    if warnings_capped:
        warnings.append(
            f"outlier_dropped — dropped {warnings_capped} far-out source(s) "
            f"beyond the {mode} poison ceiling (stale-spike guard)")
    if t3 is None and t3_c is not None:
        warnings.append("t3_stretch_unarmed — reachability/momentum did not confirm bull-stretch")
    if t1 is None and mode != "invest":
        warnings.append("no_target_meets_minimum_r")
    # Overhead-supply cap surfaced: T1 is the nearest unbroken wall and sits below
    # the mode's min-R floor — honest "buying into resistance, poor R:R to first
    # obstacle" signal. The sub-floor R:R already drags confidence.rr_quality.
    _min_r_t1 = cfg.get("min_r_t1")  # None for invest → guard excludes it
    if (t1 is not None and _min_r_t1 is not None and t1.r_multiple is not None
            and t1.r_multiple < _min_r_t1):
        warnings.append(
            f"overhead_supply_cap — T1 ${t1.price:.2f} is the nearest unbroken "
            f"resistance at {t1.r_multiple:.2f}R (below {_min_r_t1:.1f}R floor); "
            f"price must clear it to continue. R:R reflects the first obstacle, "
            f"not a leapfrogged target.")
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

    # 15. Confidence (0-1 score · 5 components, incl. momentum reachability)
    # momentum_reachability = the reachability score of the PRIMARY target (T1),
    # i.e. does volatility budget + MACD + RSI support getting there? Falls back
    # to 0.5 (neutral) when T1 is absent.
    t1_reach = None
    if t1 and isinstance(t1.p_reach_source, dict):
        t1_reach = (t1.p_reach_source.get("reachability") or {}).get("score")
    conf_components = {
        "trend_alignment": 0.9 if structure_info["trend"] == "uptrend" else 0.4 if structure_info["trend"] == "range" else 0.2,
        "confluence_quality": min(1.0, (t1.confluence / 8.0) if t1 else 0),
        "volume_confirmation": 0.7,  # Phase 2: real RVOL/volume_trend
        "rr_quality": min(1.0, (t1.r_multiple / 3.0) if t1 else 0),
        "momentum_reachability": round(float(t1_reach), 3) if t1_reach is not None else 0.5,
    }
    confidence = {
        "score": round(sum(conf_components.values()) / len(conf_components), 2),
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
        t3=t3,
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
        entry={}, stop={}, t1=None, t2=None, t3=None, sizing={},
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
    """File exists AND age < ttl seconds AND schema matches current version.

    A pre-Phase-1 cache file (no `_schema` key, or an older version) is reported
    stale so analyze_trade_cached regenerates it with t3 + new sources +
    reachability. This makes the whole cache dir self-invalidate on a schema bump
    without a manual delete.
    """
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    if age >= ttl:
        return False
    # Schema-version gate
    cached = _cache_read(path)
    if cached is None:
        return False
    if cached.get("_schema") != CACHE_SCHEMA_VERSION:
        return False
    return True


def _cache_read(path: Path) -> Optional[dict]:
    """Load JSON from disk · None if corrupt."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_write(path: Path, payload: dict) -> None:
    """Atomic write via temp file + rename. Stamps current schema version."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "_schema": CACHE_SCHEMA_VERSION}
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
