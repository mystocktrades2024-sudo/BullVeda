"""
Pattern Engine
──────────────
Mechanism-honest classical / TA pattern detector. Each method has an
INDEPENDENT classifier (no shared composite vote) and every empirical
claim is bounded by Wilson 95% lower-confidence and a sample-size flag.

Surfaces:
  - Wyckoff phase classifier      (accumulation / markup / distribution / markdown)
  - Classical patterns            (cup-handle, flag, pennant, triangles)
  - Volume Profile                (POC, VAH, VAL, acceptance state)
  - Fibonacci                     (real detected swing pair, 9 levels, current zone)
  - Ichimoku Kinko Hyo            (5-line system + honest cloud/TK classifier)
  - Support / Resistance          (swing-point clustering, touch count, strength)
  - Trendlines                    (auto-detected upper/lower, break status)

Plus Wilson-LB hit rates over ~6mo history:
  fib_0618_bounce · ichi_tk_cross · vp_poc_bounce · sr_level_hold ·
  trendline_break_followthrough · classical_breakout

Per CLAUDE.md hedge-fund mindset (principles 1, 2, 4):
  Wilson LB not point estimates · mechanism articulated per method ·
  every claim has falsification · no shared synthetic vote.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# 0. SHARED UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def wilson_lower_bound(wins: int, total: int, z: float = 1.96) -> float:
    """Wilson 95% lower confidence bound on a proportion."""
    if total == 0:
        return 0.0
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - margin) / denom)


def _sample_flag(n: int) -> str:
    if n >= 30:
        return "INSTITUTIONAL_FLOOR"
    if n >= 10:
        return "BELOW_FLOOR"
    return "INSUFFICIENT"


def _swing_points(df: pd.DataFrame, window: int = 5) -> tuple[list[int], list[int]]:
    """Detect swing highs/lows via window-based fractal."""
    highs, lows = [], []
    if df is None or len(df) < 2 * window + 1:
        return highs, lows
    h = df["High"].values
    l = df["Low"].values
    for i in range(window, len(df) - window):
        if h[i] >= h[i - window:i].max() and h[i] >= h[i + 1:i + window + 1].max():
            highs.append(i)
        if l[i] <= l[i - window:i].min() and l[i] <= l[i + 1:i + window + 1].min():
            lows.append(i)
    return highs, lows


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if df is None or len(df) < period + 1:
        return 0.0
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - c[:-1]),
        np.abs(l[1:] - c[:-1]),
    ])
    return float(np.mean(tr[-period:]))


# ═══════════════════════════════════════════════════════════════════════
# 1. WYCKOFF PHASE CLASSIFIER
#     Accumulation / Markup / Distribution / Markdown / Unclear
#     Mechanism: phase = function of (trend slope, volume-price divergence)
# ═══════════════════════════════════════════════════════════════════════

def detect_wyckoff_phase(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 60:
        return {
            "phase": "unclear", "vote": "NEUTRAL", "confidence": 0.0,
            "rationale": "insufficient history (<60 bars)",
            "falsification": None,
        }

    closes = df["Close"].values
    vols = df["Volume"].values if "Volume" in df.columns else np.ones(len(df))

    # Range bands over last 60 bars
    last60 = df.tail(60)
    rng_hi = float(last60["High"].max())
    rng_lo = float(last60["Low"].min())
    rng_mid = (rng_hi + rng_lo) / 2
    rng_width = max(rng_hi - rng_lo, 1e-9)
    px = float(closes[-1])
    pos_in_range = (px - rng_lo) / rng_width  # 0..1

    # Trend slope: 30d linear regression on closes (log)
    n = 30
    y = np.log(np.maximum(closes[-n:], 1e-9))
    x = np.arange(n)
    slope = float(np.polyfit(x, y, 1)[0])  # log-return per bar
    daily_pct = (math.exp(slope) - 1) * 100  # %/day

    # Volume confirmation: are up-bars higher volume than down-bars (markup) or vice versa?
    closes_arr = df["Close"].values[-30:]
    vols_arr = vols[-30:]
    if len(closes_arr) >= 2:
        deltas = np.diff(closes_arr)
        up_mask = deltas > 0
        dn_mask = deltas < 0
        up_vol = float(vols_arr[1:][up_mask].mean()) if up_mask.any() else 0
        dn_vol = float(vols_arr[1:][dn_mask].mean()) if dn_mask.any() else 0
        vol_skew = (up_vol - dn_vol) / max(up_vol + dn_vol, 1)  # -1..+1
    else:
        vol_skew = 0.0

    # Classification logic:
    #   markup        = uptrend (slope > +0.15%/day) + bullish volume skew
    #   markdown      = downtrend (slope < -0.15%/day) + bearish volume skew
    #   accumulation  = sideways (|slope|<0.1%/day) + lower 50% range + bullish vol skew
    #   distribution  = sideways + upper 50% range + bearish vol skew
    #   unclear       = none of the above
    phase = "unclear"
    vote = "NEUTRAL"
    confidence = 0.5
    rationale = ""
    falsification = ""

    if daily_pct > 0.15 and vol_skew > 0.05:
        phase, vote = "markup", "BULLISH"
        confidence = min(0.95, 0.55 + abs(daily_pct) / 1.0 + max(vol_skew, 0) * 0.5)
        rationale = (
            f"Uptrend (+{daily_pct:.2f}%/day · 30d slope) with up-day volume "
            f"{(vol_skew*100):.0f}% richer than down-day. Demand absorbing supply — "
            f"institutions buying through retail offers."
        )
        falsification = (
            f"30d slope flips negative AND volume skew reverses → markup ends; expect "
            f"distribution phase to follow at a higher level."
        )
    elif daily_pct < -0.15 and vol_skew < -0.05:
        phase, vote = "markdown", "BEARISH"
        confidence = min(0.95, 0.55 + abs(daily_pct) / 1.0 + abs(min(vol_skew, 0)) * 0.5)
        rationale = (
            f"Downtrend ({daily_pct:.2f}%/day · 30d slope) with down-day volume "
            f"{abs(vol_skew*100):.0f}% richer than up-day. Supply exceeds demand — "
            f"institutions distributing into retail bids."
        )
        falsification = (
            f"30d slope flips positive AND volume skew reverses → markdown exhausts; "
            f"watch for accumulation in lower 30% of range."
        )
    elif abs(daily_pct) < 0.10 and pos_in_range < 0.50 and vol_skew > 0:
        phase, vote = "accumulation", "BULLISH"
        confidence = 0.65 + max(vol_skew, 0) * 0.3
        rationale = (
            f"Sideways action ({daily_pct:+.2f}%/day) in lower {(pos_in_range*100):.0f}% of "
            f"60d range with bullish volume skew (+{(vol_skew*100):.0f}%). "
            f"Smart money buying weakness; setup for markup."
        )
        falsification = (
            f"Break below ${rng_lo:.2f} (60d low) on expanding volume invalidates accumulation; "
            f"that's a spring failure / new downtrend."
        )
    elif abs(daily_pct) < 0.10 and pos_in_range > 0.50 and vol_skew < 0:
        phase, vote = "distribution", "BEARISH"
        confidence = 0.65 + abs(min(vol_skew, 0)) * 0.3
        rationale = (
            f"Sideways action ({daily_pct:+.2f}%/day) in upper {(pos_in_range*100):.0f}% of "
            f"60d range with bearish volume skew ({(vol_skew*100):.0f}%). "
            f"Smart money distributing into strength; setup for markdown."
        )
        falsification = (
            f"Break above ${rng_hi:.2f} (60d high) on expanding volume invalidates distribution; "
            f"that's a upthrust failure / continuation."
        )
    else:
        phase, vote = "unclear", "NEUTRAL"
        confidence = 0.3
        rationale = (
            f"No clean phase: slope {daily_pct:+.2f}%/day · "
            f"range position {(pos_in_range*100):.0f}% · "
            f"volume skew {(vol_skew*100):+.0f}%. Wait for clearer alignment."
        )
        falsification = "Re-classify when slope or volume skew becomes decisive."

    # ─── Sub-phase classification: where in the phase are we ─────
    # Early / Mid / Late / Exhaust based on slope intensity + range position.
    sub_phase = None
    sub_phase_rationale = ""
    if phase in ("markup", "markdown"):
        slope_mag = abs(daily_pct)
        if phase == "markup":
            if pos_in_range > 0.95 and slope_mag > 1.0:
                sub_phase = "exhaust"
                sub_phase_rationale = "Slope >1%/day in upper 5% of range — parabolic, fade-risk territory."
            elif pos_in_range > 0.80:
                sub_phase = "late"
                sub_phase_rationale = "Upper 80%+ of range — trend extended, watch for distribution onset."
            elif pos_in_range > 0.40 and slope_mag > 0.20:
                sub_phase = "mid"
                sub_phase_rationale = "Mid-markup — sweet spot for swing entries; trend strong, not stretched."
            else:
                sub_phase = "early"
                sub_phase_rationale = "Early markup — trend just established, room to run."
        else:  # markdown
            if pos_in_range < 0.05 and slope_mag > 1.0:
                sub_phase = "exhaust"
                sub_phase_rationale = "Slope <-1%/day in lower 5% — capitulation territory, watch for accumulation."
            elif pos_in_range < 0.20:
                sub_phase = "late"
                sub_phase_rationale = "Lower 20% of range — markdown extended."
            elif pos_in_range < 0.60 and slope_mag > 0.20:
                sub_phase = "mid"
                sub_phase_rationale = "Mid-markdown — sustained selling."
            else:
                sub_phase = "early"
                sub_phase_rationale = "Early markdown — trend just turning."

    # ─── Transition triggers (3 conditions that flip markup→distribution) ─
    transition_triggers = []
    if phase == "markup":
        # 1. Volume skew reversal
        vskew_status_ok = vol_skew > 0
        transition_triggers.append({
            "name": "Volume skew reverses",
            "threshold": "down-bar vol > up-bar vol",
            "current": f"+{(vol_skew*100):.0f}% bull" if vol_skew > 0 else f"{(vol_skew*100):.0f}% bear",
            "status": "ok" if vskew_status_ok else "triggered",
        })
        # 2. Slope flattening
        slope_ok = daily_pct > 0.15
        transition_triggers.append({
            "name": "30d slope flattens",
            "threshold": "+0.15%/day",
            "current": f"+{daily_pct:.2f}%/day" if daily_pct > 0 else f"{daily_pct:.2f}%/day",
            "status": "ok" if slope_ok else ("warn" if daily_pct > 0 else "triggered"),
        })
        # 3. UTAD / Upthrust check (simple proxy: did last bar spike above range high?)
        utad_spike = False
        try:
            last_high = float(df["High"].iloc[-1])
            if last_high > rng_hi * 1.01:
                utad_spike = True
        except Exception:
            pass
        transition_triggers.append({
            "name": "UTAD (Upthrust After Distribution)",
            "threshold": "spike above range high + rejection candle",
            "current": "spike detected today" if utad_spike else "no UTAD detected",
            "status": "warn" if utad_spike else "ok",
        })

    # ─── Volume-Price Spread series (last 30 sessions for bottom strip) ───
    vps_series = []
    try:
        last30 = df.tail(30)
        closes_30 = last30["Close"].values
        vols_30 = last30["Volume"].values if "Volume" in last30.columns else np.ones(len(last30))
        prev_closes = np.concatenate([[closes_30[0]], closes_30[:-1]])
        for i in range(len(last30)):
            delta = closes_30[i] - prev_closes[i]
            v = float(vols_30[i])
            up_vol = v if delta > 0 else 0.0
            dn_vol = v if delta < 0 else 0.0
            vps_series.append({
                "up_vol": int(up_vol),
                "down_vol": int(dn_vol),
                "net_demand": int(up_vol - dn_vol),
            })
        # Smoothed 5-period EMA of net_demand for the dashed overlay
        net = [r["net_demand"] for r in vps_series]
        if net:
            alpha = 2.0 / 6  # 5-period EMA
            ema = [float(net[0])]
            for x in net[1:]:
                ema.append(alpha * x + (1 - alpha) * ema[-1])
            for i, e in enumerate(ema):
                vps_series[i]["net_demand_ema5"] = int(e)
    except Exception:
        vps_series = []

    return {
        "phase": phase, "vote": vote,
        "confidence": round(confidence, 2),
        "slope_pct_per_day": round(daily_pct, 3),
        "pos_in_range": round(pos_in_range, 2),
        "volume_skew": round(vol_skew, 2),
        "range_high": round(rng_hi, 2),
        "range_low": round(rng_lo, 2),
        "rationale": rationale,
        "falsification": falsification,
        "sub_phase": sub_phase,
        "sub_phase_rationale": sub_phase_rationale,
        "transition_triggers": transition_triggers,
        "vps_series": vps_series,
    }


# ═══════════════════════════════════════════════════════════════════════
# 2. CLASSICAL PATTERNS (cup-handle, flag, pennant, triangles)
#     Bulkowski-style — simple geometric detectors over swing pivots.
# ═══════════════════════════════════════════════════════════════════════

def detect_classical_patterns(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 60:
        return {
            "patterns": [], "active_pattern": None, "vote": "NEUTRAL",
            "rationale": "insufficient history",
            "falsification": None,
        }

    highs_idx, lows_idx = _swing_points(df, window=4)
    if len(highs_idx) < 2 or len(lows_idx) < 2:
        return {
            "patterns": [], "active_pattern": None, "vote": "NEUTRAL",
            "rationale": "not enough swing pivots detected",
            "falsification": None,
        }

    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    px = float(closes[-1])

    patterns = []

    # ── Cup-and-Handle (most discriminating classical pattern) ──
    # 60-90d cup: deep low, recovery to similar high, then 5-15d small pullback (handle)
    if len(df) >= 80:
        win = df.tail(90)
        cup_lo_idx = int(np.argmin(win["Low"].values[:70]))
        cup_lo = float(win["Low"].iloc[cup_lo_idx])
        left_rim = float(win["High"].iloc[:cup_lo_idx].max()) if cup_lo_idx > 5 else 0
        right_rim = float(win["High"].iloc[cup_lo_idx:80].max()) if cup_lo_idx < 70 else 0
        cup_depth = (left_rim - cup_lo) / max(left_rim, 1e-9)
        rim_match = abs(left_rim - right_rim) / max(left_rim, 1e-9) < 0.05
        handle = win.tail(15)
        handle_lo = float(handle["Low"].min())
        handle_pullback = (right_rim - handle_lo) / max(right_rim, 1e-9) if right_rim > 0 else 0
        if (0.12 < cup_depth < 0.35 and rim_match
                and 0.02 < handle_pullback < 0.15
                and px > handle["Open"].iloc[-3]):
            target = right_rim + (right_rim - cup_lo)
            patterns.append({
                "kind": "cup_and_handle",
                "vote": "BULLISH",
                "neckline": round(right_rim, 2),
                "target": round(target, 2),
                "handle_low": round(handle_lo, 2),
                "depth_pct": round(cup_depth * 100, 1),
                "rationale": (
                    f"Cup formed (depth {cup_depth*100:.1f}%) with matching rims at ~${right_rim:.2f}. "
                    f"Handle pullback {handle_pullback*100:.1f}% holds above ${handle_lo:.2f}. "
                    f"Breakout > ${right_rim:.2f} projects to ${target:.2f} (cup depth)."
                ),
                "falsification": f"Close below ${handle_lo:.2f} cancels the handle.",
            })

    # ── Bull Flag (5-15d tight consolidation after sharp +5%+ rally) ──
    if len(df) >= 30:
        prior_run = df.iloc[-25:-12]
        flag_zone = df.iloc[-12:]
        prior_gain = (prior_run["Close"].iloc[-1] - prior_run["Open"].iloc[0]) / max(prior_run["Open"].iloc[0], 1e-9)
        flag_range = (flag_zone["High"].max() - flag_zone["Low"].min()) / max(flag_zone["Close"].mean(), 1e-9)
        if prior_gain > 0.07 and flag_range < 0.06:
            target = float(flag_zone["High"].max()) + (
                float(prior_run["Close"].iloc[-1]) - float(prior_run["Open"].iloc[0])
            )
            patterns.append({
                "kind": "bull_flag",
                "vote": "BULLISH",
                "pole_gain_pct": round(prior_gain * 100, 1),
                "flag_top": round(float(flag_zone["High"].max()), 2),
                "flag_bottom": round(float(flag_zone["Low"].min()), 2),
                "target": round(target, 2),
                "rationale": (
                    f"Sharp +{prior_gain*100:.1f}% pole, then tight consolidation "
                    f"({flag_range*100:.1f}% range). Breakout > ${flag_zone['High'].max():.2f} "
                    f"projects pole-height to ${target:.2f}."
                ),
                "falsification": f"Close below ${flag_zone['Low'].min():.2f} breaks the flag.",
            })
        elif prior_gain < -0.07 and flag_range < 0.06:
            target = float(flag_zone["Low"].min()) - (
                float(prior_run["Open"].iloc[0]) - float(prior_run["Close"].iloc[-1])
            )
            patterns.append({
                "kind": "bear_flag",
                "vote": "BEARISH",
                "pole_gain_pct": round(prior_gain * 100, 1),
                "flag_top": round(float(flag_zone["High"].max()), 2),
                "flag_bottom": round(float(flag_zone["Low"].min()), 2),
                "target": round(target, 2),
                "rationale": (
                    f"Sharp {prior_gain*100:.1f}% drop, then tight consolidation. "
                    f"Breakdown < ${flag_zone['Low'].min():.2f} projects to ${target:.2f}."
                ),
                "falsification": f"Close above ${flag_zone['High'].max():.2f} breaks the flag.",
            })

    # ── Ascending Triangle (flat top + rising lows over 15-30d) ──
    if len(highs_idx) >= 3 and len(lows_idx) >= 3:
        recent_hi = [i for i in highs_idx if len(df) - i < 30][-3:]
        recent_lo = [i for i in lows_idx if len(df) - i < 30][-3:]
        if len(recent_hi) >= 2 and len(recent_lo) >= 2:
            hi_levels = [highs[i] for i in recent_hi]
            lo_levels = [lows[i] for i in recent_lo]
            hi_flat = max(hi_levels) - min(hi_levels) < (hi_levels[0] * 0.02)
            lo_rising = lo_levels[-1] > lo_levels[0] * 1.01
            if hi_flat and lo_rising:
                resistance = float(np.mean(hi_levels))
                target = resistance + (resistance - lo_levels[0])
                patterns.append({
                    "kind": "ascending_triangle",
                    "vote": "BULLISH",
                    "resistance": round(resistance, 2),
                    "target": round(target, 2),
                    "rationale": (
                        f"Flat resistance at ~${resistance:.2f}, lows rising from "
                        f"${lo_levels[0]:.2f} → ${lo_levels[-1]:.2f}. Breakout above "
                        f"${resistance:.2f} projects to ${target:.2f}."
                    ),
                    "falsification": f"Close below ${lo_levels[-1]:.2f} breaks the rising support.",
                })
            elif (max(lo_levels) - min(lo_levels) < lo_levels[0] * 0.02
                  and hi_levels[-1] < hi_levels[0] * 0.99):
                support = float(np.mean(lo_levels))
                target = support - (hi_levels[0] - support)
                patterns.append({
                    "kind": "descending_triangle",
                    "vote": "BEARISH",
                    "support": round(support, 2),
                    "target": round(target, 2),
                    "rationale": (
                        f"Flat support at ~${support:.2f}, highs falling from "
                        f"${hi_levels[0]:.2f} → ${hi_levels[-1]:.2f}. Breakdown below "
                        f"${support:.2f} projects to ${target:.2f}."
                    ),
                    "falsification": f"Close above ${hi_levels[-1]:.2f} breaks the falling resistance.",
                })

    if not patterns:
        return {
            "patterns": [], "active_pattern": None, "vote": "NEUTRAL",
            "rationale": "no high-conviction classical pattern detected in last 90d",
            "falsification": None,
        }

    active = patterns[0]
    return {
        "patterns": patterns,
        "active_pattern": active["kind"],
        "vote": active["vote"],
        "rationale": active["rationale"],
        "falsification": active["falsification"],
        "target": active.get("target"),
    }


# ═══════════════════════════════════════════════════════════════════════
# 3. VOLUME PROFILE
# ═══════════════════════════════════════════════════════════════════════

def detect_volume_profile(df: pd.DataFrame, lookback: int = 60, n_bins: int = 30) -> dict:
    if df is None or len(df) < 30:
        return {
            "poc": 0, "vah": 0, "val": 0, "acceptance": "INSIDE",
            "vote": "NEUTRAL",
            "rationale": "insufficient history",
            "falsification": None,
        }
    win = df.tail(lookback)
    lo = float(win["Low"].min())
    hi = float(win["High"].max())
    step = max((hi - lo) / n_bins, 1e-9)
    bins = np.zeros(n_bins)
    for _, row in win.iterrows():
        mid = (row["High"] + row["Low"]) / 2
        b = int(min(n_bins - 1, max(0, (mid - lo) // step)))
        bins[b] += row.get("Volume", 1)
    tot = bins.sum()
    poc_idx = int(np.argmax(bins))
    poc = float(lo + (poc_idx + 0.5) * step)
    # VAH/VAL = central 70% of volume
    sort_idx = np.argsort(-bins)
    cum = 0.0
    vah_i, val_i = poc_idx, poc_idx
    for i in sort_idx:
        cum += bins[i]
        if i > vah_i:
            vah_i = i
        if i < val_i:
            val_i = i
        if cum / max(tot, 1) >= 0.70:
            break
    vah = float(lo + (vah_i + 1) * step)
    val = float(lo + val_i * step)
    px = float(df["Close"].iloc[-1])
    if px > vah:
        acceptance = "ABOVE"
        vote = "BULLISH"
        rationale = (
            f"Price ${px:.2f} accepted above value area high ${vah:.2f}. POC ${poc:.2f} "
            f"is institutional support on pullback. Auction has migrated higher."
        )
        falsification = f"Two daily closes back inside the value area (< ${vah:.2f}) → breakout failure."
    elif px < val:
        acceptance = "BELOW"
        vote = "BEARISH"
        rationale = (
            f"Price ${px:.2f} broken below value area low ${val:.2f}. POC ${poc:.2f} "
            f"now overhead resistance. Auction has migrated lower."
        )
        falsification = f"Two daily closes back inside the value area (> ${val:.2f}) → breakdown failure."
    else:
        acceptance = "INSIDE"
        vote = "NEUTRAL"
        rationale = (
            f"Price ${px:.2f} inside value area [{val:.2f}–{vah:.2f}]. "
            f"POC ${poc:.2f} is the magnet — wait for break of VAH or VAL with volume."
        )
        falsification = f"Acceptance outside VAH/VAL changes the bias."
    return {
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "acceptance": acceptance,
        "vote": vote,
        "rationale": rationale,
        "falsification": falsification,
    }


# ═══════════════════════════════════════════════════════════════════════
# 4. FIBONACCI — uses DETECTED swing pair (not 52w hi/lo)
# ═══════════════════════════════════════════════════════════════════════

def detect_fibonacci(df: pd.DataFrame, lookback: int = 90) -> dict:
    if df is None or len(df) < 30:
        return {
            "swing_hi": 0, "swing_lo": 0, "levels": {},
            "vote": "NEUTRAL", "rationale": "insufficient history",
            "falsification": None,
        }
    win = df.tail(lookback).reset_index(drop=True)
    hi_pos = int(np.argmax(win["High"].values))
    lo_pos = int(np.argmin(win["Low"].values))
    swing_hi = float(win["High"].max())
    swing_lo = float(win["Low"].min())
    direction = "up" if hi_pos > lo_pos else "down"
    rng = swing_hi - swing_lo
    if rng <= 0:
        return {
            "swing_hi": swing_hi, "swing_lo": swing_lo, "levels": {},
            "vote": "NEUTRAL", "rationale": "flat swing", "falsification": None,
        }
    # For an uptrend swing (low→high): retracements pull back from high
    levels = {
        "r_0000":   round(swing_hi, 2),
        "r_0236":   round(swing_hi - rng * 0.236, 2),
        "r_0382":   round(swing_hi - rng * 0.382, 2),
        "r_0500":   round(swing_hi - rng * 0.500, 2),
        "r_0618":   round(swing_hi - rng * 0.618, 2),  # golden
        "r_0786":   round(swing_hi - rng * 0.786, 2),
        "r_1000":   round(swing_lo, 2),
        "ext_1272": round(swing_hi + rng * 0.272, 2),
        "ext_1618": round(swing_hi + rng * 0.618, 2),
    }
    px = float(df["Close"].iloc[-1])
    # Locate current zone
    if px > levels["r_0000"]:
        zone = "above-1.000 / extension"
    elif px > levels["r_0236"]:
        zone = "0.000–0.236 (shallow)"
    elif px > levels["r_0382"]:
        zone = "0.236–0.382"
    elif px > levels["r_0500"]:
        zone = "0.382–0.500"
    elif px > levels["r_0618"]:
        zone = "0.500–0.618"
    elif px > levels["r_0786"]:
        zone = "0.618–0.786 (deep)"
    else:
        zone = "below-0.786"
    # Vote: bullish if direction=up AND price above 0.618, bearish if below
    if direction == "up" and px > levels["r_0618"]:
        vote = "BULLISH"
        rationale = (
            f"Price ${px:.2f} holding above 0.618 ${levels['r_0618']:.2f} after uptrend swing "
            f"${swing_lo:.2f} → ${swing_hi:.2f}. Targets 1.272 ${levels['ext_1272']:.2f} and "
            f"1.618 ${levels['ext_1618']:.2f}."
        )
        falsification = f"Close below 0.618 (${levels['r_0618']:.2f}) on volume → deep retrace failure."
    elif direction == "up" and px < levels["r_0786"]:
        vote = "BEARISH"
        rationale = (
            f"Price ${px:.2f} below 0.786 ${levels['r_0786']:.2f} — the uptrend swing is invalidating; "
            f"retracement has gone too deep to be a healthy pullback."
        )
        falsification = f"Reclaim of 0.618 ${levels['r_0618']:.2f} restores the uptrend."
    else:
        vote = "NEUTRAL"
        rationale = (
            f"Price ${px:.2f} in zone {zone}. Swing high ${swing_hi:.2f} → low ${swing_lo:.2f}. "
            f"Wait for reaction at 0.618 (${levels['r_0618']:.2f}) or breakout above 0.236 "
            f"(${levels['r_0236']:.2f}) for direction."
        )
        falsification = "Direction commits when price clears 0.618 in either direction."
    return {
        "swing_hi": swing_hi, "swing_lo": swing_lo,
        "direction": direction,
        "levels": levels,
        "current_zone": zone,
        "vote": vote,
        "rationale": rationale,
        "falsification": falsification,
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. ICHIMOKU
# ═══════════════════════════════════════════════════════════════════════

def detect_ichimoku(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 60:
        return {"vote": "NEUTRAL", "rationale": "insufficient history", "falsification": None}
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values

    def _mid(period: int, offset: int = 0) -> float:
        end = len(df) - offset
        start = max(0, end - period)
        if end <= start:
            return float(c[-1])
        return float((h[start:end].max() + l[start:end].min()) / 2)

    tenkan = _mid(9)
    kijun = _mid(26)
    senkou_a_now = (tenkan + kijun) / 2  # plotted +26 forward; "current cloud top" is past
    senkou_b_now = _mid(52)
    # Cloud at current bar is from 26 bars ago projections; approximate using past mid
    cloud_top_at_now = (_mid(9, 26) + _mid(26, 26)) / 2 if len(df) >= 52 else senkou_a_now
    cloud_bot_at_now = _mid(52, 26) if len(df) >= 78 else senkou_b_now
    cloud_top = max(cloud_top_at_now, cloud_bot_at_now)
    cloud_bot = min(cloud_top_at_now, cloud_bot_at_now)
    px = float(c[-1])

    if px > cloud_top:
        cloud_state = "ABOVE"
    elif px < cloud_bot:
        cloud_state = "BELOW"
    else:
        cloud_state = "INSIDE"

    tk_cross = "BULL" if tenkan > kijun else ("BEAR" if tenkan < kijun else "NEUTRAL")
    chikou_clear = px > float(c[-27]) if len(df) >= 27 else True
    future_cloud = "BULLISH" if senkou_a_now > senkou_b_now else "BEARISH"

    # Honest classifier: BULLISH requires 3+ of the 4 confluences
    bull_score = int(cloud_state == "ABOVE") + int(tk_cross == "BULL") + int(chikou_clear) + int(future_cloud == "BULLISH")
    bear_score = int(cloud_state == "BELOW") + int(tk_cross == "BEAR") + int(not chikou_clear) + int(future_cloud == "BEARISH")
    if bull_score >= 3:
        vote = "BULLISH"
        rationale = (
            f"{bull_score}/4 bullish confluences: cloud={cloud_state} · "
            f"TK={tk_cross} · Chikou={'clear' if chikou_clear else 'tangled'} · future cloud={future_cloud}. "
            f"Kijun ${kijun:.2f} is dynamic stop reference."
        )
        falsification = f"Daily close below Kijun ${kijun:.2f} loses the trend frame; close inside cloud breaks the system."
    elif bear_score >= 3:
        vote = "BEARISH"
        rationale = (
            f"{bear_score}/4 bearish confluences: cloud={cloud_state} · TK={tk_cross} · "
            f"Chikou={'clear' if chikou_clear else 'tangled'} · future cloud={future_cloud}."
        )
        falsification = f"Reclaim of Kijun ${kijun:.2f} and TK bull-cross would restore neutral."
    else:
        vote = "NEUTRAL"
        rationale = (
            f"Mixed signals (bull {bull_score}/4 · bear {bear_score}/4). "
            f"Wait for cleaner alignment — Kijun ${kijun:.2f}, cloud ${cloud_bot:.2f}–${cloud_top:.2f}."
        )
        falsification = "3+ aligned confluences resolves the bias."

    return {
        "tenkan": round(tenkan, 2),
        "kijun": round(kijun, 2),
        "cloud_top": round(cloud_top, 2),
        "cloud_bot": round(cloud_bot, 2),
        "price_vs_cloud": cloud_state,
        "tk_cross": tk_cross,
        "chikou_clear": chikou_clear,
        "future_cloud": future_cloud,
        "bull_score": bull_score,
        "bear_score": bear_score,
        "vote": vote,
        "rationale": rationale,
        "falsification": falsification,
    }


# ═══════════════════════════════════════════════════════════════════════
# 6. SUPPORT / RESISTANCE
#    Cluster swing pivots within (0.5 × ATR); strength = touch count.
# ═══════════════════════════════════════════════════════════════════════

def detect_sr_levels(df: pd.DataFrame, lookback: int = 120, max_levels: int = 5) -> dict:
    if df is None or len(df) < 40:
        return {"supports": [], "resistances": [], "vote": "NEUTRAL",
                "rationale": "insufficient history", "falsification": None}
    win = df.tail(lookback)
    highs_idx, lows_idx = _swing_points(win, window=4)
    atr = _atr(win, period=14) or (win["High"].mean() * 0.02)
    cluster_band = atr * 0.6
    px = float(df["Close"].iloc[-1])
    win_high = win["High"].values
    win_low = win["Low"].values

    def cluster(idxs: list[int], values: np.ndarray) -> list[dict]:
        if not idxs:
            return []
        prices = sorted([float(values[i]) for i in idxs])
        clusters = []
        cur = [prices[0]]
        for p in prices[1:]:
            if abs(p - np.mean(cur)) <= cluster_band:
                cur.append(p)
            else:
                clusters.append(cur)
                cur = [p]
        clusters.append(cur)
        return [{"price": round(float(np.mean(c)), 2), "touches": len(c)} for c in clusters]

    high_clusters = cluster(highs_idx, win_high)
    low_clusters = cluster(lows_idx, win_low)
    resistances = sorted([c for c in high_clusters if c["price"] > px], key=lambda x: x["price"])[:max_levels]
    supports = sorted([c for c in low_clusters if c["price"] < px], key=lambda x: -x["price"])[:max_levels]

    nearest_r = resistances[0] if resistances else None
    nearest_s = supports[0] if supports else None

    if nearest_r:
        nearest_r["distance_pct"] = round((nearest_r["price"] - px) / px * 100, 2)
    if nearest_s:
        nearest_s["distance_pct"] = round((px - nearest_s["price"]) / px * 100, 2)

    # Vote based on proximity + strength
    if nearest_s and nearest_s["touches"] >= 3 and nearest_s["distance_pct"] < 3:
        vote = "BULLISH"
        rationale = (
            f"Strong support at ${nearest_s['price']:.2f} ({nearest_s['touches']} touches, "
            f"{nearest_s['distance_pct']:.1f}% away). Near defensible buy zone."
        )
        falsification = f"Close below ${nearest_s['price']:.2f} on volume breaks the level — flip to bearish."
    elif nearest_r and nearest_r["touches"] >= 3 and nearest_r["distance_pct"] < 3:
        vote = "BEARISH"
        rationale = (
            f"Strong resistance at ${nearest_r['price']:.2f} ({nearest_r['touches']} touches, "
            f"{nearest_r['distance_pct']:.1f}% above). Asymmetric risk on long entry here."
        )
        falsification = f"Close above ${nearest_r['price']:.2f} on volume invalidates — breakout setup."
    else:
        vote = "NEUTRAL"
        rationale = (
            f"Mid-range — "
            f"{'support ' + str(nearest_s['price']) + ' (' + str(nearest_s['distance_pct']) + '%)' if nearest_s else ''}"
            f"{' · ' if nearest_s and nearest_r else ''}"
            f"{'resistance ' + str(nearest_r['price']) + ' (' + str(nearest_r['distance_pct']) + '%)' if nearest_r else ''}."
        )
        falsification = "Pattern resolves when price tags either level."

    return {
        "supports": supports,
        "resistances": resistances,
        "nearest_support": nearest_s,
        "nearest_resistance": nearest_r,
        "atr": round(atr, 2),
        "vote": vote,
        "rationale": rationale,
        "falsification": falsification,
    }


# ═══════════════════════════════════════════════════════════════════════
# 7. TRENDLINES (auto-detected)
# ═══════════════════════════════════════════════════════════════════════

def detect_trendlines(df: pd.DataFrame, lookback: int = 90) -> dict:
    if df is None or len(df) < 30:
        return {"upper": None, "lower": None, "vote": "NEUTRAL",
                "rationale": "insufficient history", "falsification": None}
    win = df.tail(lookback).reset_index(drop=True)
    highs_idx, lows_idx = _swing_points(win, window=4)
    px = float(win["Close"].iloc[-1])

    def fit_line(idxs: list[int], values: np.ndarray) -> Optional[dict]:
        if len(idxs) < 2:
            return None
        pts = [(i, float(values[i])) for i in idxs]
        pts = pts[-3:] if len(pts) >= 3 else pts  # use most-recent 3 pivots
        xs = np.array([p[0] for p in pts])
        ys = np.array([p[1] for p in pts])
        if xs.max() - xs.min() < 5:
            return None
        slope, intercept = np.polyfit(xs, ys, 1)
        last_x = len(win) - 1
        projected = float(slope * last_x + intercept)
        return {
            "slope": float(slope),
            "intercept": float(intercept),
            "projected_at_last_bar": round(projected, 2),
            "touches": len(pts),
            "pivots": [(int(p[0]), round(float(p[1]), 2)) for p in pts],
        }

    upper = fit_line(highs_idx, win["High"].values)
    lower = fit_line(lows_idx, win["Low"].values)

    upper_break = False
    lower_break = False
    if upper:
        upper_break = px > upper["projected_at_last_bar"] * 1.005
    if lower:
        lower_break = px < lower["projected_at_last_bar"] * 0.995

    if upper and upper_break and (lower and lower["slope"] > 0):
        vote = "BULLISH"
        rationale = (
            f"Break above descending upper trendline (projected ${upper['projected_at_last_bar']:.2f}) "
            f"with intact rising lower support — trend reversal up."
        )
        falsification = f"Reclaim of trendline (close < ${upper['projected_at_last_bar']:.2f}) is a failure."
    elif lower and lower_break and (upper and upper["slope"] < 0):
        vote = "BEARISH"
        rationale = (
            f"Break below ascending lower trendline (projected ${lower['projected_at_last_bar']:.2f}). "
            f"Trend reversal down."
        )
        falsification = f"Reclaim of trendline (close > ${lower['projected_at_last_bar']:.2f}) is a failure."
    elif upper and upper["slope"] > 0 and lower and lower["slope"] > 0:
        vote = "BULLISH"
        rationale = (
            f"Both trendlines rising — uptrend channel active. "
            f"Upper ${upper['projected_at_last_bar']:.2f} · lower ${lower['projected_at_last_bar']:.2f}."
        )
        falsification = f"Close below lower trendline (${lower['projected_at_last_bar']:.2f}) ends the channel."
    elif upper and upper["slope"] < 0 and lower and lower["slope"] < 0:
        vote = "BEARISH"
        rationale = (
            f"Both trendlines falling — downtrend channel active. "
            f"Upper ${upper['projected_at_last_bar']:.2f} · lower ${lower['projected_at_last_bar']:.2f}."
        )
        falsification = f"Close above upper trendline (${upper['projected_at_last_bar']:.2f}) ends the channel."
    else:
        vote = "NEUTRAL"
        rationale = (
            f"Sideways or ambiguous trend. "
            f"Upper {upper['projected_at_last_bar'] if upper else '—'} · "
            f"lower {lower['projected_at_last_bar'] if lower else '—'}."
        )
        falsification = "Channel resolves when price breaks either trendline."

    return {
        "upper": upper,
        "lower": lower,
        "upper_break": upper_break,
        "lower_break": lower_break,
        "vote": vote,
        "rationale": rationale,
        "falsification": falsification,
    }


# ═══════════════════════════════════════════════════════════════════════
# 8. COMPOSITE — HONEST AGGREGATION
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# 8. ELLIOTT WAVE (mechanical 5-wave impulse detector + deep details)
#     DISCRETIONARY — tracked for confluence, NOT counted in conviction.
#     Uses last 6 swing pivots to attempt a W0→W5 labelling and verify
#     the 3 hard EW rules. Returns "discretionary": True so frontend
#     knows to render violet + exclude from composite gate.
#
#   Deep details (v6.1):
#     - Wave degree label (Primary/Intermediate/Minor/Minute) inferred from span
#     - Sub-waves of W3 (most subdividable wave) if enough sub-pivots exist
#     - Corrective wave A-B-C detection if W5 appears done + 3 retraces follow
#     - Fibonacci relationships (W3/W1, W5/W1 ratios, golden-spiral check)
#     - Wave personality (length × volume) for each wave
# ═══════════════════════════════════════════════════════════════════════

def _ew_degree_from_span(span_bars: int) -> str:
    """Classify wave degree from total impulse span (W0→W5 bar count).
    Standard Elliott degree taxonomy (Frost & Prechter):
      Subminuette: hours · Minuette: <5d · Minute: 5-20d · Minor: 20-50d
      Intermediate: 50-150d · Primary: 150-500d · Cycle: 500-2500d · Supercycle: years
    """
    if span_bars < 10:
        return "Minuette"
    if span_bars < 25:
        return "Minute"
    if span_bars < 60:
        return "Minor"
    if span_bars < 150:
        return "Intermediate"
    return "Primary"


def _ew_fib_ratio(a: float, b: float) -> dict:
    """Compute ratio + nearest Fibonacci relationship."""
    if b == 0 or not (a and b):
        return {"ratio": None, "fib_match": None}
    r = abs(a / b)
    fibs = {0.382: "0.382", 0.500: "0.500", 0.618: "0.618", 1.000: "equality",
            1.272: "1.272", 1.382: "1.382", 1.618: "golden 1.618",
            2.000: "2.000", 2.618: "2.618"}
    nearest = min(fibs.keys(), key=lambda k: abs(r - k))
    deviation = abs(r - nearest) / nearest
    if deviation <= 0.05:
        return {"ratio": round(r, 3), "fib_match": fibs[nearest], "deviation_pct": round(deviation*100, 1)}
    return {"ratio": round(r, 3), "fib_match": None, "deviation_pct": round(deviation*100, 1)}


def _ew_wave_personality(df, start_idx: int, end_idx: int, expected: str) -> dict:
    """Score wave 'personality': length, avg volume, range expansion vs prior wave.
    expected: 'impulse' (W1/W3/W5/B) — should have wider range + higher volume
              'corrective' (W2/W4/A/C) — should have narrower range + lower volume
    Returns {bars, avg_volume, range_pct, personality_match (bool)}.
    """
    if start_idx >= end_idx or end_idx >= len(df):
        return {"bars": 0, "personality_match": None}
    seg = df.iloc[start_idx:end_idx+1]
    bars = len(seg)
    if bars < 2:
        return {"bars": bars, "personality_match": None}
    try:
        avg_vol = float(seg["Volume"].mean()) if "Volume" in seg.columns else 0.0
        rng_pct = float((seg["High"].max() - seg["Low"].min()) / seg["Low"].min() * 100) if seg["Low"].min() > 0 else 0.0
    except Exception:
        avg_vol = 0.0; rng_pct = 0.0
    return {"bars": bars, "avg_volume": int(avg_vol),
            "range_pct": round(rng_pct, 2),
            "personality_match": None}  # match heuristic deferred


def _ew_detect_subwaves(df, w_start_idx: int, w_end_idx: int) -> list[dict]:
    """Look for 5 sub-pivots between w_start and w_end. If found, label them
    as sub-w1..sub-w5 with prices. Returns [] if <5 sub-pivots in the span."""
    if w_start_idx >= w_end_idx or (w_end_idx - w_start_idx) < 10:
        return []
    sub_window = max(2, (w_end_idx - w_start_idx) // 8)
    try:
        sub_highs, sub_lows = _swing_points(df.iloc[w_start_idx:w_end_idx+1], window=sub_window)
        # Adjust idx back to df-global
        sub_highs = [w_start_idx + i for i in sub_highs]
        sub_lows = [w_start_idx + i for i in sub_lows]
    except Exception:
        return []
    pivots = []
    for i in sub_highs:
        pivots.append({"idx": int(i), "type": "H", "price": float(df["High"].iloc[i])})
    for i in sub_lows:
        pivots.append({"idx": int(i), "type": "L", "price": float(df["Low"].iloc[i])})
    pivots.sort(key=lambda p: p["idx"])
    if len(pivots) < 5:
        return []
    # Take the alternating pattern that best fits 5 waves
    pick = pivots[:5]
    return [{"label": f"sub-w{i+1}", "idx": p["idx"], "price": round(p["price"], 2),
             "type": p["type"]} for i, p in enumerate(pick)]


def _ew_detect_corrective(df, w5_idx: int) -> dict | None:
    """After W5 completes, look for A-B-C corrective pattern in subsequent bars.
    Returns {a, b, c} dict if pattern detected, else None."""
    if w5_idx >= len(df) - 5:
        return None
    after = df.iloc[w5_idx:].reset_index(drop=True)
    if len(after) < 8:
        return None
    try:
        h, l = _swing_points(after, window=3)
    except Exception:
        return None
    # Need at least 3 pivots after W5 to label A-B-C
    pivots = [{"idx": i, "type": "H", "price": float(after["High"].iloc[i])} for i in h] + \
             [{"idx": i, "type": "L", "price": float(after["Low"].iloc[i])} for i in l]
    pivots.sort(key=lambda p: p["idx"])
    if len(pivots) < 3:
        return None
    a, b, c = pivots[0], pivots[1], pivots[2]
    # A and C should be in same direction (both lows for bearish correction after bullish impulse)
    if a["type"] != c["type"] or a["type"] == b["type"]:
        return None
    return {
        "A": {"idx": w5_idx + a["idx"], "price": round(a["price"], 2), "type": a["type"]},
        "B": {"idx": w5_idx + b["idx"], "price": round(b["price"], 2), "type": b["type"]},
        "C": {"idx": w5_idx + c["idx"], "price": round(c["price"], 2), "type": c["type"]},
    }


def _ew_deep_details(df, waves: dict, direction: str) -> dict:
    """Compute deep EW metrics: degree, sub-waves of W3, A-B-C corrective,
    Fibonacci relationships, wave personality per major wave."""
    if not waves or len(waves) != 6:
        return {}
    w0, w1, w2, w3, w4, w5 = (waves[k] for k in ["W0", "W1", "W2", "W3", "W4", "W5"])
    span = w5["idx"] - w0["idx"]
    degree = _ew_degree_from_span(span)

    # Wave segment sizes
    w1_size = abs(w1["price"] - w0["price"])
    w2_size = abs(w2["price"] - w1["price"])
    w3_size = abs(w3["price"] - w2["price"])
    w4_size = abs(w4["price"] - w3["price"])
    w5_size = abs(w5["price"] - w4["price"])

    fib_relationships = {
        "W2_retraces_W1":  _ew_fib_ratio(w2_size, w1_size),
        "W3_vs_W1":         _ew_fib_ratio(w3_size, w1_size),
        "W4_retraces_W3":  _ew_fib_ratio(w4_size, w3_size),
        "W5_vs_W1":         _ew_fib_ratio(w5_size, w1_size),
        "W5_vs_W1+W3":     _ew_fib_ratio(w5_size, w1_size + w3_size),
    }

    # Wave personalities
    personalities = {}
    for label, ws, we, kind in [
        ("W1", w0, w1, "impulse"), ("W2", w1, w2, "corrective"),
        ("W3", w2, w3, "impulse"), ("W4", w3, w4, "corrective"),
        ("W5", w4, w5, "impulse"),
    ]:
        personalities[label] = _ew_wave_personality(df, ws["idx"], we["idx"], kind)
        personalities[label]["kind"] = kind  # impulse or corrective

    # Sub-waves of W3 (typically the most subdividable)
    sub_w3 = _ew_detect_subwaves(df, w2["idx"], w3["idx"])

    # Corrective wave A-B-C (if any) after W5
    abc = _ew_detect_corrective(df, w5["idx"])

    return {
        "degree": degree,
        "span_bars": span,
        "wave_sizes": {
            "W1_size": round(w1_size, 2), "W2_size": round(w2_size, 2),
            "W3_size": round(w3_size, 2), "W4_size": round(w4_size, 2),
            "W5_size": round(w5_size, 2),
        },
        "fib_relationships": fib_relationships,
        "wave_personalities": personalities,
        "sub_waves_w3": sub_w3,
        "corrective_abc": abc,
        "wave_3_is_extended": w3_size > max(w1_size, w5_size) * 1.5,
        "wave_3_classification": "extended" if w3_size > max(w1_size, w5_size) * 1.5 else "standard",
    }


# ═══════════════════════════════════════════════════════════════════════
# 8b. WYCKOFF SUB-EVENTS (PS / SC / AR / ST / SOS / Spring / UTAD / LPSY)
#     Identifies signature Wyckoff events from recent swing pivots within
#     the dominant phase. Each event is a labeled price+date+status entry.
# ═══════════════════════════════════════════════════════════════════════

# Wyckoff event taxonomy by phase
WYCKOFF_EVENTS = {
    "accumulation": [
        ("PS",  "Preliminary Support",       "First sign of buying after downtrend"),
        ("SC",  "Selling Climax",            "Panic low + huge volume"),
        ("AR",  "Automatic Rally",            "Sharp rally off SC low"),
        ("ST",  "Secondary Test",             "Retest of SC area on lower volume"),
        ("Spring", "Spring / Shakeout",       "False break below support → reversal"),
        ("SOS", "Sign of Strength",           "Strong rally on volume above resistance"),
        ("LPS", "Last Point of Support",      "Pullback to former resistance now support"),
        ("BU",  "Backup to Edge of Creek",    "Final test before markup"),
    ],
    "markup": [
        ("SOS", "Sign of Strength",           "Continuation breakouts on rising volume"),
        ("LPS", "Last Point of Support",      "Pullback that holds prior breakout level"),
        ("NS",  "Normal Reaction",            "Healthy pullback within trend"),
    ],
    "distribution": [
        ("PSY", "Preliminary Supply",         "First sign of selling after uptrend"),
        ("BC",  "Buying Climax",              "Euphoric high + huge volume"),
        ("AR",  "Automatic Reaction",          "Sharp decline off BC"),
        ("ST",  "Secondary Test",             "Retest of BC high on lower volume"),
        ("UT",  "Upthrust",                   "False break above resistance"),
        ("UTAD","Upthrust After Distribution","Final terminal upthrust"),
        ("SOW", "Sign of Weakness",            "Breakdown on volume below support"),
        ("LPSY","Last Point of Supply",        "Pullback that fails at resistance"),
    ],
    "markdown": [
        ("SOW", "Sign of Weakness",            "Continuation breakdowns on rising volume"),
        ("LPSY","Last Point of Supply",        "Pullback that fails at prior support now resistance"),
        ("NS",  "Normal Reaction",             "Healthy bounce within downtrend"),
    ],
}


def detect_wyckoff_subevents(df: pd.DataFrame, phase: str, range_hi: float, range_lo: float) -> list[dict]:
    """Identify the most recent signature Wyckoff events visible in the chart.
    For each event in the phase's taxonomy, scan recent swing pivots for a
    match. Returns up to 5 most-recent events as a list of dicts."""
    if df is None or len(df) < 30 or not phase or phase == "unclear":
        return []
    phase = phase.lower()
    if phase not in WYCKOFF_EVENTS:
        return []

    events_template = WYCKOFF_EVENTS[phase]
    out: list[dict] = []

    try:
        highs, lows = _swing_points(df.tail(60), window=3)
        # Convert to df-global indices
        offset = len(df) - 60
        highs = [offset + i for i in highs]
        lows = [offset + i for i in lows]
    except Exception:
        return []

    if not (highs or lows):
        return []

    closes = df["Close"].values
    vols = df["Volume"].values if "Volume" in df.columns else np.ones(len(df))
    avg_vol_60 = float(vols[-60:].mean()) if len(vols) >= 60 else float(vols.mean())

    # Phase-specific detection logic
    if phase == "markup":
        # SOS: scan last 10 swing highs (was 5) with relaxed 1.3× threshold (was 1.5×)
        for hi_idx in highs[-10:]:
            v = float(vols[hi_idx]) if hi_idx < len(vols) else 0
            if v > avg_vol_60 * 1.3:
                out.append({
                    "code": "SOS", "name": "Sign of Strength",
                    "date_idx": int(hi_idx),
                    "price": round(float(df["High"].iloc[hi_idx]), 2),
                    "volume_ratio": round(v / max(avg_vol_60, 1), 2),
                    "description": "Strong rally on volume above prior resistance",
                    "status": "confirmed",
                })
        # LPS: recent swing low that held above prior breakout level (last 5, was 3)
        for lo_idx in lows[-5:]:
            lo_px = float(df["Low"].iloc[lo_idx])
            if lo_px > (range_hi + range_lo) / 2:
                out.append({
                    "code": "LPS", "name": "Last Point of Support",
                    "date_idx": int(lo_idx), "price": round(lo_px, 2),
                    "description": "Pullback held above prior breakout level",
                    "status": "confirmed",
                })
        # NS: Normal Reaction — pullback that bounced off Kijun or EMA21
        for lo_idx in lows[-5:]:
            lo_px = float(df["Low"].iloc[lo_idx])
            # Heuristic: low between (range_hi+range_lo)/2 and range_hi*0.85
            mid_band_lo = (range_hi + range_lo) / 2
            mid_band_hi = range_hi * 0.92
            if mid_band_lo < lo_px < mid_band_hi:
                out.append({
                    "code": "NS", "name": "Normal Reaction",
                    "date_idx": int(lo_idx), "price": round(lo_px, 2),
                    "description": "Healthy pullback within trend, bounce zone",
                    "status": "confirmed",
                })

    elif phase == "accumulation":
        # SC: lowest low of last 60 bars on high volume
        if lows:
            sc_idx = min(lows, key=lambda i: float(df["Low"].iloc[i]))
            sc_vol = float(vols[sc_idx]) if sc_idx < len(vols) else 0
            if sc_vol > avg_vol_60 * 1.5:
                out.append({
                    "code": "SC", "name": "Selling Climax",
                    "date_idx": int(sc_idx),
                    "price": round(float(df["Low"].iloc[sc_idx]), 2),
                    "volume_ratio": round(sc_vol / max(avg_vol_60, 1), 2),
                    "description": "Panic low with capitulation volume",
                    "status": "confirmed",
                })
        # Spring: recent low briefly below range_lo then closed back inside
        for lo_idx in lows[-3:]:
            lo_px = float(df["Low"].iloc[lo_idx])
            close_px = float(closes[lo_idx])
            if lo_px < range_lo * 1.005 and close_px > range_lo:
                out.append({
                    "code": "Spring", "name": "Spring / Shakeout",
                    "date_idx": int(lo_idx),
                    "price": round(lo_px, 2),
                    "description": "False break below support, reversed intraday",
                    "status": "confirmed",
                })

    elif phase == "distribution":
        # BC: highest high of last 60 on high volume
        if highs:
            bc_idx = max(highs, key=lambda i: float(df["High"].iloc[i]))
            bc_vol = float(vols[bc_idx]) if bc_idx < len(vols) else 0
            if bc_vol > avg_vol_60 * 1.5:
                out.append({
                    "code": "BC", "name": "Buying Climax",
                    "date_idx": int(bc_idx),
                    "price": round(float(df["High"].iloc[bc_idx]), 2),
                    "volume_ratio": round(bc_vol / max(avg_vol_60, 1), 2),
                    "description": "Euphoric high with climactic volume",
                    "status": "confirmed",
                })
        # UTAD: recent swing high above range_hi, closed below
        for hi_idx in highs[-3:]:
            hi_px = float(df["High"].iloc[hi_idx])
            close_px = float(closes[hi_idx])
            if hi_px > range_hi * 0.995 and close_px < range_hi:
                out.append({
                    "code": "UTAD", "name": "Upthrust After Distribution",
                    "date_idx": int(hi_idx), "price": round(hi_px, 2),
                    "description": "False break above resistance, rejected",
                    "status": "confirmed",
                })

    elif phase == "markdown":
        # SOW: recent swing low on high volume
        for lo_idx in lows[-5:]:
            v = float(vols[lo_idx]) if lo_idx < len(vols) else 0
            if v > avg_vol_60 * 1.3:
                out.append({
                    "code": "SOW", "name": "Sign of Weakness",
                    "date_idx": int(lo_idx),
                    "price": round(float(df["Low"].iloc[lo_idx]), 2),
                    "volume_ratio": round(v / max(avg_vol_60, 1), 2),
                    "description": "Breakdown on volume below prior support",
                    "status": "confirmed",
                })

    # Add "still possible" events from the template that weren't detected
    detected_codes = {e["code"] for e in out}
    for code, name, desc in events_template:
        if code not in detected_codes:
            out.append({
                "code": code, "name": name, "description": desc,
                "status": "not_detected", "price": None, "date_idx": None,
            })

    # Sort by status (confirmed first) then by recency
    out.sort(key=lambda e: (0 if e["status"] == "confirmed" else 1,
                            -(e.get("date_idx") or 0)))
    return out[:10]


# ═══════════════════════════════════════════════════════════════════════
# 8c. MONTE CARLO BLOCK (paths · distribution · P(target/stop))
# ═══════════════════════════════════════════════════════════════════════

def compute_monte_carlo_block(df: pd.DataFrame, target: float | None, stop: float | None,
                               T: int = 10, n_paths: int = 500) -> dict:
    """Run a Merton jump-diffusion sim from current spot, computing:
    - terminal distribution (percentiles)
    - P(target hit first) / P(stop hit first)
    - compressed path samples (50 random paths) for visualization
    - histogram of terminal returns (20 bins)
    """
    base = {"available": False, "rationale": "insufficient OHLCV data"}
    if df is None or len(df) < 40:
        return base
    try:
        import monte_carlo as mc_mod
        import numpy as np
        closes = df["Close"].values
        S0 = float(closes[-1])
        # Annualized drift + vol from last 60 daily log-returns
        rets = np.diff(np.log(closes[-60:]))
        if len(rets) < 20:
            return base
        mu_annual = float(rets.mean() * 252)
        sigma_annual = float(rets.std(ddof=1) * np.sqrt(252))
        # Jump params — light defaults (small jumps)
        lambda_jump = 4.0  # 4 jumps per year
        mu_jump = -0.02
        sigma_jump = 0.05

        if target and stop and target > S0 > stop:
            result = mc_mod.simulate_with_target_stop(
                S0=S0, mu_annual=mu_annual, sigma_annual=sigma_annual,
                target=float(target), stop=float(stop),
                T=T, n_paths=n_paths,
                lambda_jump=lambda_jump, mu_jump=mu_jump, sigma_jump=sigma_jump,
                seed=42,
            )
        else:
            result = mc_mod.simulate(
                S0=S0, mu_annual=mu_annual, sigma_annual=sigma_annual,
                T=T, n_paths=n_paths,
                lambda_jump=lambda_jump, mu_jump=mu_jump, sigma_jump=sigma_jump,
                seed=42,
            )

        # Re-run simulate to get raw paths for path-viz (compressed)
        from monte_carlo import _simulate_paths_jit
        paths_array = _simulate_paths_jit(S0, mu_annual, sigma_annual, T, n_paths,
                                            lambda_jump, mu_jump, sigma_jump, 42)
        # Sample 50 paths for transmission
        sample_indices = np.linspace(0, n_paths - 1, 50, dtype=int)
        sample_paths = [
            [round(float(paths_array[i][j]), 2) for j in range(T + 1)]
            for i in sample_indices
        ]
        # Histogram of terminal returns
        terminal = paths_array[:, -1]
        terminal_returns = ((terminal - S0) / S0 * 100).tolist()
        # 20 bins
        hist, bin_edges = np.histogram(terminal_returns, bins=20)
        histogram = [
            {"bin_low_pct": round(float(bin_edges[i]), 2),
             "bin_high_pct": round(float(bin_edges[i+1]), 2),
             "count": int(hist[i])}
            for i in range(len(hist))
        ]

        result["available"] = True
        result["paths_sample"] = sample_paths  # 50 paths × (T+1) prices
        result["histogram"] = histogram
        result["spot"] = round(S0, 2)
        return result
    except Exception as e:
        return {"available": False, "rationale": f"MC failure: {type(e).__name__}: {str(e)[:80]}"}


# ═══════════════════════════════════════════════════════════════════════
# Original Elliott Wave (extended with deep details below)
# ═══════════════════════════════════════════════════════════════════════

def detect_elliott_wave(df: pd.DataFrame, pivot_window: int = 5) -> dict:
    """Best-fit 5-wave impulse over last 6 swing pivots. Rules enforced:
      R1: W2 cannot retrace >100% of W1 (no overlap)
      R2: W3 cannot be the shortest of W1/W3/W5
      R3: W4 cannot overlap W1's price territory

    Returns NEUTRAL with rationale if rules fail or insufficient pivots.
    Marked discretionary regardless.
    """
    base = {
        "vote": "NEUTRAL",
        "discretionary": True,
        "category": "discretionary",
        "current_wave": None,
        "rules_passed": 0,
        "rules_total": 3,
        "wave_points": [],
        "w5_target_low": None,
        "w5_target_high": None,
        "invalidation_level": None,
        "rationale": "insufficient pivots for wave count",
        "falsification": "Daily close below W4-overlap level invalidates entire count; re-count required.",
        "confidence": 0.0,
    }
    if df is None or len(df) < 60:
        base["rationale"] = "insufficient history (<60 bars)"
        return base

    highs, lows = _swing_points(df, window=pivot_window)
    # Build chronological pivot list: list of {idx, type, price}
    pivots = []
    for i in highs:
        pivots.append({"idx": i, "type": "H", "price": float(df["High"].iloc[i])})
    for i in lows:
        pivots.append({"idx": i, "type": "L", "price": float(df["Low"].iloc[i])})
    pivots.sort(key=lambda p: p["idx"])

    if len(pivots) < 6:
        base["rationale"] = f"only {len(pivots)} pivots — need 6 for W0-W5"
        base["pivot_count"] = len(pivots)
        base["best_effort_pivots"] = [
            {"label": f"p{i}", "idx": p["idx"], "type": p["type"], "price": round(p["price"], 2)}
            for i, p in enumerate(pivots)
        ]
        return base

    # Take the last 6 pivots; assume W0-W5 if they alternate L-H-L-H-L-H
    last6 = pivots[-6:]
    types = "".join(p["type"] for p in last6)
    is_impulse_up = types == "LHLHLH"  # 5-wave up
    is_impulse_dn = types == "HLHLHL"  # 5-wave down

    if not (is_impulse_up or is_impulse_dn):
        # Best-effort interpretation: even when rules fail, show the pivots so user can see
        best_effort = {
            "pivot_count": len(pivots),
            "pivot_sequence": types,
            "best_effort_pivots": [
                {"label": f"p{i}", "idx": p["idx"], "type": p["type"], "price": round(p["price"], 2)}
                for i, p in enumerate(last6)
            ],
        }
        # Heuristic interpretation
        if types in ("HLHLH", "LHLHL"):
            interp = "Possible WXY complex correction or zigzag — not a clean 5-wave impulse"
        elif "HH" in types or "LL" in types:
            interp = "Pivot doubling detected (HH or LL adjacent) — suggests overlapping waves, possibly Wave 4 triangle or terminal diagonal"
        else:
            interp = "Non-impulsive structure — likely corrective phase or sideways consolidation"
        best_effort["interpretation"] = interp

        # Compute Fibonacci ratios on raw wave sizes even if labels are unconventional
        sizes = []
        for i in range(1, len(last6)):
            sizes.append(abs(last6[i]["price"] - last6[i-1]["price"]))
        fib_rel_partial = {}
        if len(sizes) >= 3:
            fib_rel_partial["leg_2_vs_leg_1"] = _ew_fib_ratio(sizes[1], sizes[0])
            fib_rel_partial["leg_3_vs_leg_1"] = _ew_fib_ratio(sizes[2], sizes[0])
        if len(sizes) >= 5:
            fib_rel_partial["leg_4_vs_leg_3"] = _ew_fib_ratio(sizes[3], sizes[2])
            fib_rel_partial["leg_5_vs_leg_1"] = _ew_fib_ratio(sizes[4], sizes[0])

        base["rationale"] = f"Pivot sequence {types} doesn't match clean impulse (LHLHLH or HLHLHL). {interp}"
        base["pivot_count"] = len(pivots)
        base["pivot_sequence"] = types
        base["best_effort_pivots"] = best_effort["best_effort_pivots"]
        base["best_effort_interpretation"] = interp
        base["fib_relationships"] = fib_rel_partial
        # Best-effort wave sizes
        if len(sizes) >= 5:
            base["wave_sizes"] = {f"leg_{i+1}_size": round(s, 2) for i, s in enumerate(sizes)}
        return base

    direction = "up" if is_impulse_up else "down"
    w0, w1, w2, w3, w4, w5 = last6
    waves = {
        "W0": {"idx": int(w0["idx"]), "price": w0["price"]},
        "W1": {"idx": int(w1["idx"]), "price": w1["price"]},
        "W2": {"idx": int(w2["idx"]), "price": w2["price"]},
        "W3": {"idx": int(w3["idx"]), "price": w3["price"]},
        "W4": {"idx": int(w4["idx"]), "price": w4["price"]},
        "W5": {"idx": int(w5["idx"]), "price": w5["price"]},
    }

    # Rule checks
    rules_passed = 0
    rules_failed_msgs = []

    # R1: W2 doesn't retrace >100% of W1
    w1_size = abs(waves["W1"]["price"] - waves["W0"]["price"])
    w2_retrace = abs(waves["W2"]["price"] - waves["W1"]["price"])
    r1_ok = (w2_retrace < w1_size) if w1_size > 1e-9 else False
    if r1_ok:
        rules_passed += 1
    else:
        rules_failed_msgs.append("R1 fail (W2 fully retraced W1)")

    # R2: W3 not the shortest of W1/W3/W5
    w3_size = abs(waves["W3"]["price"] - waves["W2"]["price"])
    w5_size = abs(waves["W5"]["price"] - waves["W4"]["price"])
    r2_ok = w3_size >= min(w1_size, w5_size)
    if r2_ok:
        rules_passed += 1
    else:
        rules_failed_msgs.append("R2 fail (W3 is shortest)")

    # R3: W4 doesn't overlap W1 price territory
    if direction == "up":
        r3_ok = waves["W4"]["price"] > waves["W1"]["price"]
    else:
        r3_ok = waves["W4"]["price"] < waves["W1"]["price"]
    if r3_ok:
        rules_passed += 1
    else:
        rules_failed_msgs.append("R3 fail (W4 overlapped W1)")

    # Determine current wave (W5 is the most recent labeled pivot)
    current_wave = "W5"
    spot = float(df["Close"].iloc[-1])

    # W5 targets: 0.618 × (W1 + W3) extended from W4
    w5_proj_low = waves["W4"]["price"] + 0.618 * (w1_size + w3_size) * (1 if direction == "up" else -1)
    w5_proj_high = waves["W4"]["price"] + 1.000 * (w1_size + w3_size) * (1 if direction == "up" else -1)

    # Invalidation = W1 endpoint (R3 boundary)
    invalidation = waves["W1"]["price"]

    if rules_passed == 3:
        vote = "BULLISH" if direction == "up" else "BEARISH"
        rationale = (
            f"Best-fit {direction}-impulse wave count, all 3 EW rules hold. "
            f"Currently labeled in {current_wave} of {direction}-impulse. "
            f"This is confluence, not signal — two analysts can produce different "
            f"valid counts on the same chart."
        )
        confidence = 0.45  # capped — discretionary
    else:
        vote = "NEUTRAL"
        rationale = (
            f"Wave count attempted but " + ", ".join(rules_failed_msgs) +
            f". Rules {rules_passed}/3."
        )
        confidence = 0.25

    falsification = (
        f"Daily close {'<' if direction == 'up' else '>'} ${invalidation:.2f} "
        f"violates W4-overlap rule and invalidates this wave count entirely. "
        f"Re-count required if violation; do not trade off Elliott alone."
    )

    # Deep details: degree + sub-waves + corrective A-B-C + Fib relationships + personality
    deep = _ew_deep_details(df, waves, direction)

    return {
        "vote": vote,
        "discretionary": True,
        "category": "discretionary",
        "direction": direction,
        "current_wave": current_wave,
        "rules_passed": rules_passed,
        "rules_total": 3,
        "rules_failed": rules_failed_msgs,
        "wave_points": waves,
        "w5_target_low": round(w5_proj_low, 2),
        "w5_target_high": round(w5_proj_high, 2),
        "invalidation_level": round(invalidation, 2),
        "rationale": rationale,
        "falsification": falsification,
        "confidence": confidence,
        # Deep details (v6.1)
        "degree": deep.get("degree"),
        "span_bars": deep.get("span_bars"),
        "wave_sizes": deep.get("wave_sizes", {}),
        "fib_relationships": deep.get("fib_relationships", {}),
        "wave_personalities": deep.get("wave_personalities", {}),
        "sub_waves_w3": deep.get("sub_waves_w3", []),
        "corrective_abc": deep.get("corrective_abc"),
        "wave_3_classification": deep.get("wave_3_classification"),
        "wave_3_is_extended": deep.get("wave_3_is_extended", False),
    }


def compute_composite(votes: dict, discretionary_votes: dict | None = None,
                       method_details: dict | None = None) -> dict:
    """Take per-method votes; produce honest verdict + conviction + narrative.

    Conviction reflects AGREEMENT count, not certainty of any method.
    `discretionary_votes` (e.g. Elliott Wave) are tracked separately — they
    show in the donut but do NOT count toward the BUY/SELL conviction gate.
    `method_details` (optional) is a dict {method: {vote, rationale}} used
    to build the prose narrative.
    """
    counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    for v in votes.values():
        counts[v if v in counts else "NEUTRAL"] += 1
    total = sum(counts.values()) or 1

    if counts["BULLISH"] > counts["BEARISH"] and counts["BULLISH"] >= 4:
        verdict = "BULLISH"
    elif counts["BEARISH"] > counts["BULLISH"] and counts["BEARISH"] >= 4:
        verdict = "BEARISH"
    elif counts["BULLISH"] == counts["BEARISH"]:
        verdict = "NEUTRAL"
    elif counts["BULLISH"] > counts["BEARISH"]:
        verdict = "BULLISH-LEAN"
    else:
        verdict = "BEARISH-LEAN"

    max_agree = max(counts["BULLISH"], counts["BEARISH"])
    if max_agree >= 5:
        conviction = "HIGH"
    elif max_agree >= 4:
        conviction = "MEDIUM"
    else:
        conviction = "LOW"

    tension = (
        "Methods disagree — that disagreement IS the signal. Wait." if max_agree < 3
        else "Most methods aligned." if max_agree >= 4
        else "Slight lean only."
    )

    # Discretionary methods (Elliott Wave) — tracked but excluded from gate
    disc_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    for v in (discretionary_votes or {}).values():
        disc_counts[v if v in disc_counts else "NEUTRAL"] += 1
    discretionary_count = sum(disc_counts.values())

    # Build prose narrative ("Of seven methods, X resolve bullish (...). ...")
    narrative = _build_composite_narrative(verdict, conviction, counts,
                                            disc_counts, method_details or {})

    return {
        "verdict": verdict,
        "conviction": conviction,
        "bull_count": counts["BULLISH"],
        "bear_count": counts["BEARISH"],
        "neutral_count": counts["NEUTRAL"],
        "discretionary_count": discretionary_count,
        "discretionary_bull": disc_counts["BULLISH"],
        "discretionary_bear": disc_counts["BEARISH"],
        "total": total,
        "tension_note": tension,
        "narrative": narrative,
    }


_METHOD_DISPLAY = {
    "wyckoff": "Wyckoff",
    "fibonacci": "Fibonacci",
    "ichimoku": "Ichimoku",
    "trendlines": "Trendlines",
    "volume_profile": "Volume Profile",
    "sr_levels": "S/R",
    "classical": "Classical",
    "elliott_wave": "Elliott Wave (discretionary)",
}


def _build_composite_narrative(verdict: str, conviction: str, counts: dict,
                                 disc_counts: dict, method_details: dict) -> str:
    """Multi-sentence summary like:
       'Of seven independent quant methods, four resolve bullish (Wyckoff markup,
        Fibonacci above 0.618, Ichimoku 4/4 confluence, rising trendlines).
        Three sit neutral — VP at VAH waiting acceptance, S/R no clustered level,
        no classical pattern active. The bullish read is real but un-stretched.'
    """
    bull_methods = []
    bear_methods = []
    neutral_methods = []
    for key, info in method_details.items():
        if key == "elliott_wave":
            continue
        disp = _METHOD_DISPLAY.get(key, key)
        v = info.get("vote", "NEUTRAL") if isinstance(info, dict) else "NEUTRAL"
        if v == "BULLISH":
            bull_methods.append(disp)
        elif v == "BEARISH":
            bear_methods.append(disp)
        else:
            neutral_methods.append(disp)

    quant_total = counts["BULLISH"] + counts["BEARISH"] + counts["NEUTRAL"]
    parts = [f"Of {quant_total} independent quantitative methods,"]

    if counts["BULLISH"]:
        parts.append(
            f" {counts['BULLISH']} resolve bullish"
            + (f" ({', '.join(bull_methods)})" if bull_methods else "")
            + "."
        )
    if counts["BEARISH"]:
        parts.append(
            f" {counts['BEARISH']} resolve bearish"
            + (f" ({', '.join(bear_methods)})" if bear_methods else "")
            + "."
        )
    if counts["NEUTRAL"]:
        parts.append(
            f" {counts['NEUTRAL']} sit neutral"
            + (f" ({', '.join(neutral_methods)})" if neutral_methods else "")
            + "."
        )

    # Closing read
    if verdict == "BULLISH" and conviction == "HIGH":
        parts.append(" Bullish read is well-supported — high-conviction setup.")
    elif verdict == "BULLISH":
        parts.append(" Bullish read is real but un-stretched — wait for next confirmation tag.")
    elif verdict == "BEARISH" and conviction == "HIGH":
        parts.append(" Bearish read is well-supported — high-conviction defensive posture.")
    elif verdict == "BEARISH":
        parts.append(" Bearish lean is real but un-confirmed — protect downside.")
    elif verdict.endswith("-LEAN"):
        parts.append(" Slight lean only — not actionable until majority alignment.")
    else:
        parts.append(" Methods balanced — wait for clearer alignment.")

    # Discretionary footnote
    if disc_counts["BULLISH"] + disc_counts["BEARISH"] + disc_counts["NEUTRAL"] > 0:
        disc_bull = disc_counts["BULLISH"]
        disc_bear = disc_counts["BEARISH"]
        if disc_bull > disc_bear:
            parts.append(" Elliott Wave (discretionary) reads bullish — confluence only.")
        elif disc_bear > disc_bull:
            parts.append(" Elliott Wave (discretionary) reads bearish — confluence only.")

    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# 9. HIT-RATE SWEEP — per-ticker Wilson LB on rule outcomes
# ═══════════════════════════════════════════════════════════════════════

def compute_pattern_hit_rates(df: pd.DataFrame, ticker: str, horizon_days: int = 10) -> dict:
    """Sliding-window historical sweep. For each rule:
    - fib_0618_bounce  : did price reach 1.272 ext within H days after tagging 0.618?
    - ichi_tk_cross    : did price gain 2% within H days after a fresh TK bull-cross?
    - vp_poc_bounce    : did price hold POC (within +1 ATR) within H days after tagging?
    - sr_level_hold    : did a support touch hold (no breach) within H days?
    - trendline_break_followthrough : did a break extend 2% in same direction within H days?
    - classical_breakout : did detected pattern reach target within 30 days?

    Each metric is CONDITIONAL on the event firing — not "did pattern fire AND succeed".
    """
    if df is None or len(df) < 120:
        return _empty_pattern_hit_rates()

    results = {
        "fib_0618_bounce": {"wins": 0, "total": 0},
        "ichi_tk_cross": {"wins": 0, "total": 0},
        "vp_poc_bounce": {"wins": 0, "total": 0},
        "sr_level_hold": {"wins": 0, "total": 0},
        "trendline_break_followthrough": {"wins": 0, "total": 0},
        "classical_breakout": {"wins": 0, "total": 0},
    }

    min_history = 90
    end_buffer = horizon_days + 5
    for t in range(min_history, len(df) - end_buffer, 2):  # step by 2 — covers enough
        window = df.iloc[:t + 1]
        future = df.iloc[t + 1: t + 1 + horizon_days]
        if len(future) < horizon_days:
            continue
        f_high = future["High"].values
        f_low = future["Low"].values
        f_close = future["Close"].values
        px_t = float(window["Close"].iloc[-1])

        # — Fib 0.618 bounce —
        try:
            fib = detect_fibonacci(window)
            lvl = fib.get("levels", {}).get("r_0618")
            ext = fib.get("levels", {}).get("ext_1272")
            if lvl and ext and fib.get("direction") == "up":
                tag = (window["Low"].iloc[-5:].values <= lvl).any()
                if tag:
                    results["fib_0618_bounce"]["total"] += 1
                    if f_high.max() >= ext:
                        results["fib_0618_bounce"]["wins"] += 1
        except Exception:
            pass

        # — Ichimoku TK cross —
        try:
            if len(window) >= 60:
                ichi_now = detect_ichimoku(window)
                ichi_prev = detect_ichimoku(window.iloc[:-2]) if len(window) > 60 else None
                if (ichi_now["tk_cross"] == "BULL" and ichi_prev and ichi_prev["tk_cross"] != "BULL"):
                    results["ichi_tk_cross"]["total"] += 1
                    if (f_close.max() - px_t) / px_t >= 0.02:
                        results["ichi_tk_cross"]["wins"] += 1
        except Exception:
            pass

        # — VP POC bounce —
        try:
            vp = detect_volume_profile(window)
            poc = vp.get("poc")
            if poc:
                tag = ((window["Low"].iloc[-5:].values <= poc * 1.005) & (window["High"].iloc[-5:].values >= poc * 0.995)).any()
                if tag and px_t > poc * 0.98:
                    results["vp_poc_bounce"]["total"] += 1
                    # Win: price held above POC (no close below) over future
                    if (f_close >= poc * 0.99).all():
                        results["vp_poc_bounce"]["wins"] += 1
        except Exception:
            pass

        # — S/R level hold —
        try:
            sr = detect_sr_levels(window)
            ns = sr.get("nearest_support")
            if ns and ns.get("distance_pct", 100) < 3 and ns.get("touches", 0) >= 2:
                results["sr_level_hold"]["total"] += 1
                if (f_low.min() > ns["price"] * 0.99):
                    results["sr_level_hold"]["wins"] += 1
        except Exception:
            pass

        # — Trendline break followthrough —
        try:
            tl = detect_trendlines(window)
            if tl.get("upper_break") or tl.get("lower_break"):
                results["trendline_break_followthrough"]["total"] += 1
                direction = 1 if tl.get("upper_break") else -1
                pct = (f_close.max() - px_t) / px_t if direction > 0 else (px_t - f_close.min()) / px_t
                if pct >= 0.02:
                    results["trendline_break_followthrough"]["wins"] += 1
        except Exception:
            pass

        # — Classical breakout — track at horizon=30
        try:
            if t < len(df) - 30:
                cp = detect_classical_patterns(window)
                tgt = cp.get("target")
                if tgt and cp.get("vote") in ("BULLISH", "BEARISH"):
                    future30 = df.iloc[t + 1: t + 31]
                    if len(future30) >= 30:
                        results["classical_breakout"]["total"] += 1
                        if cp.get("vote") == "BULLISH" and future30["High"].max() >= tgt:
                            results["classical_breakout"]["wins"] += 1
                        elif cp.get("vote") == "BEARISH" and future30["Low"].min() <= tgt:
                            results["classical_breakout"]["wins"] += 1
        except Exception:
            pass

    out = {"ticker": ticker, "horizon_days": horizon_days, "synth": False}
    for k, v in results.items():
        wins, total = v["wins"], v["total"]
        wr = wins / total if total else 0
        wlb = wilson_lower_bound(wins, total)
        out[k] = {
            "wins": wins, "total": total,
            "win_rate": round(wr * 100, 1),
            "wilson_lb": round(wlb * 100, 1),
            "sample_size_flag": _sample_flag(total),
        }
    return out


def _empty_pattern_hit_rates() -> dict:
    rules = [
        "fib_0618_bounce", "ichi_tk_cross", "vp_poc_bounce",
        "sr_level_hold", "trendline_break_followthrough", "classical_breakout",
    ]
    out = {"synth": False}
    for r in rules:
        out[r] = {"wins": 0, "total": 0, "win_rate": 0, "wilson_lb": 0, "sample_size_flag": "INSUFFICIENT"}
    return out


# ═══════════════════════════════════════════════════════════════════════
# 10. PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════

HIT_RATES_PATH = Path(__file__).parent / "data" / "pattern_hit_rates.json"


def load_pattern_hit_rates() -> dict:
    if not HIT_RATES_PATH.exists():
        return {}
    try:
        with open(HIT_RATES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_pattern_hit_rate(ticker: str, hit_rates: dict) -> None:
    HIT_RATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_rates = load_pattern_hit_rates()
    all_rates[ticker] = hit_rates
    with open(HIT_RATES_PATH, "w") as f:
        json.dump(all_rates, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# 11. ATTACH TO RESULT
# ═══════════════════════════════════════════════════════════════════════

def detect_all_patterns(df: pd.DataFrame) -> dict:
    """One-shot orchestrator — runs all 7 quant detectors + Elliott Wave +
    composite + derived helpers (key levels, action ladder, scenarios, ticket)."""
    wy = detect_wyckoff_phase(df)
    cl = detect_classical_patterns(df)
    vp = detect_volume_profile(df)
    fi = detect_fibonacci(df)
    ic = detect_ichimoku(df)
    sr = detect_sr_levels(df)
    tl = detect_trendlines(df)
    ew = detect_elliott_wave(df)

    quant_votes = {
        "wyckoff": wy["vote"],
        "classical": cl["vote"],
        "volume_profile": vp["vote"],
        "fibonacci": fi["vote"],
        "ichimoku": ic["vote"],
        "sr_levels": sr["vote"],
        "trendlines": tl["vote"],
    }
    disc_votes = {"elliott_wave": ew["vote"]}
    method_details = {
        "wyckoff": wy, "classical": cl, "volume_profile": vp,
        "fibonacci": fi, "ichimoku": ic, "sr_levels": sr, "trendlines": tl,
        "elliott_wave": ew,
    }
    composite = compute_composite(quant_votes, disc_votes, method_details)

    pd_dict = {
        "wyckoff": wy,
        "classical": cl,
        "volume_profile": vp,
        "fibonacci": fi,
        "ichimoku": ic,
        "sr_levels": sr,
        "trendlines": tl,
        "elliott_wave": ew,
        "composite": composite,
        "synth": False,
    }
    # Derived helpers — depend on the detector outputs above
    try:
        spot = float(df["Close"].iloc[-1])
    except Exception:
        spot = None
    pd_dict["key_levels"] = build_key_levels(pd_dict, spot)
    pd_dict["action_ladder"] = build_action_ladder(pd_dict, spot)
    pd_dict["scenarios"] = compute_scenarios(pd_dict, spot, df)
    pd_dict["execution_ticket"] = build_entry_zone_and_narrative(pd_dict, spot, df)

    # v6.1 — Wyckoff sub-events + Monte Carlo block
    try:
        pd_dict["wyckoff"]["subevents"] = detect_wyckoff_subevents(
            df, (wy.get("phase") or ""),
            float(wy.get("range_high") or 0),
            float(wy.get("range_low") or 0),
        )
    except Exception:
        pd_dict["wyckoff"]["subevents"] = []

    ticket = pd_dict.get("execution_ticket") or {}
    try:
        pd_dict["monte_carlo"] = compute_monte_carlo_block(
            df,
            target=ticket.get("t1"),
            stop=ticket.get("stop"),
            T=10, n_paths=500,
        )
    except Exception as e:
        pd_dict["monte_carlo"] = {"available": False, "rationale": f"{type(e).__name__}: {e}"}

    return pd_dict


# ═══════════════════════════════════════════════════════════════════════
# 10b. DERIVED HELPERS — key levels, action ladder, scenarios, ticket
# ═══════════════════════════════════════════════════════════════════════

def _atr_value(df: pd.DataFrame, period: int = 14) -> float:
    try:
        return _atr(df, period)
    except Exception:
        return 0.0


def build_key_levels(pd_dict: dict, spot: float | None) -> list[dict]:
    """Unified sorted list (desc by price) of every actionable level pulled
    from the per-method detectors. Each item: {price, source, label, vote}."""
    out: list[dict] = []
    sp = spot or 0.0

    fi = pd_dict.get("fibonacci") or {}
    fi_lev = fi.get("levels") or {}
    if fi_lev:
        for key, label, vote in [
            ("ext_1618", "Fib 1.618 ext · T2 stretch", "BULLISH"),
            ("ext_1272", "Fib 1.272 ext · T1 primary", "BULLISH"),
            ("r_0618",   "Fib 0.618 · golden retrace floor", "BEARISH"),
        ]:
            if key in fi_lev and fi_lev[key]:
                out.append({"price": float(fi_lev[key]), "source": "FIB",
                            "label": label, "vote": vote})
    if fi.get("swing_hi"):
        out.append({"price": float(fi["swing_hi"]), "source": "SWING",
                    "label": "60d swing high · breakout pivot", "vote": "BULLISH"})
    if fi.get("swing_lo"):
        out.append({"price": float(fi["swing_lo"]), "source": "SWING",
                    "label": "Swing low", "vote": "BEARISH"})

    vp = pd_dict.get("volume_profile") or {}
    if vp.get("vah"):
        out.append({"price": float(vp["vah"]), "source": "VP",
                    "label": "VAH · acceptance above = confirm", "vote": "BULLISH"})
    if vp.get("poc"):
        out.append({"price": float(vp["poc"]), "source": "VP",
                    "label": "POC · institutional anchor", "vote": "NEUTRAL"})
    if vp.get("val"):
        out.append({"price": float(vp["val"]), "source": "VP",
                    "label": "VAL · acceptance below = bearish flip", "vote": "BEARISH"})

    ic = pd_dict.get("ichimoku") or {}
    if ic.get("kijun"):
        out.append({"price": float(ic["kijun"]), "source": "ICHI",
                    "label": "Kijun · dynamic stop reference", "vote": "NEUTRAL"})
    if ic.get("tenkan"):
        out.append({"price": float(ic["tenkan"]), "source": "ICHI",
                    "label": "Tenkan", "vote": "NEUTRAL"})

    tl = pd_dict.get("trendlines") or {}
    if tl.get("upper") and tl["upper"].get("now"):
        out.append({"price": float(tl["upper"]["now"]), "source": "TL",
                    "label": "Upper trendline · channel top", "vote": "BULLISH"})
    if tl.get("lower") and tl["lower"].get("now"):
        out.append({"price": float(tl["lower"]["now"]), "source": "TL",
                    "label": "Lower trendline · channel floor", "vote": "BEARISH"})

    if sp:
        out.append({"price": sp, "source": "NOW",
                    "label": "SPOT NOW", "vote": "NEUTRAL"})

    # Hard stop = 1.25 ATR below spot (long) — simple model for now
    atr = _atr_value_safe(pd_dict, sp)
    if sp and atr:
        out.append({"price": round(sp - 1.25 * atr, 2), "source": "STOP",
                    "label": "HARD STOP · 1.25 ATR", "vote": "BEARISH"})

    # EW invalidation / targets
    ew = pd_dict.get("elliott_wave") or {}
    if ew.get("invalidation_level"):
        out.append({"price": float(ew["invalidation_level"]), "source": "EW",
                    "label": "Elliott Wave invalidation (W4-overlap)",
                    "vote": "DISCRETIONARY"})

    # Sort descending by price; tag distance from spot
    out.sort(key=lambda x: -x["price"])
    for r in out:
        r["dist_pct"] = round((r["price"] - sp) / sp * 100, 2) if sp else 0.0
    return out


def _atr_value_safe(pd_dict: dict, spot: float) -> float:
    """Use S/R detector's ATR if available; else estimate from fib swing."""
    sr = pd_dict.get("sr_levels") or {}
    if sr.get("atr"):
        try:
            return float(sr["atr"])
        except Exception:
            pass
    fi = pd_dict.get("fibonacci") or {}
    if fi.get("swing_hi") and fi.get("swing_lo"):
        try:
            return (float(fi["swing_hi"]) - float(fi["swing_lo"])) * 0.06
        except Exception:
            pass
    return spot * 0.025 if spot else 0.0


def build_action_ladder(pd_dict: dict, spot: float | None) -> list[dict]:
    """Derive 'if price tags X, do Y' rows from key_levels. Same source,
    different presentation — action-oriented text."""
    levels = pd_dict.get("key_levels") or []
    sp = spot or 0.0
    out = []
    for lv in levels:
        px = lv["price"]
        src = lv["source"]
        if src == "FIB" and "1.618" in lv.get("label", ""):
            action = "Take T2 · scale fully · close position"
        elif src == "FIB" and "1.272" in lv.get("label", ""):
            action = "Take T1 · scale 50% · trail rest with Kijun"
        elif src == "SWING" and "high" in lv.get("label", "").lower():
            action = "Breakout above swing high — add 25%"
        elif src == "VP" and "VAH" in lv.get("label", ""):
            action = "VAH acceptance — thesis confirm"
        elif src == "NOW":
            action = "SPOT NOW — half-position OK"
        elif src == "FIB" and "0.618" in lv.get("label", ""):
            action = "Below Fib 0.618 — exit fully"
        elif src == "VP" and "POC" in lv.get("label", ""):
            action = "POC tag — high-conviction support test"
        elif src == "VP" and "VAL" in lv.get("label", ""):
            action = "VAL break — bearish acceptance · cut size"
        elif src == "ICHI" and "Kijun" in lv.get("label", ""):
            action = "Kijun tag — dynamic support reference"
        elif src == "ICHI":
            action = "Tenkan tag — momentum check"
        elif src == "TL" and "Upper" in lv.get("label", ""):
            action = "Upper TL tag — channel resistance · trim 25%"
        elif src == "TL" and "Lower" in lv.get("label", ""):
            action = "Lower TL break — channel ended · re-evaluate"
        elif src == "STOP":
            action = "HARD STOP — close below = invalidation"
        elif src == "EW":
            action = "EW invalidation — wave count void · do not act"
        else:
            action = f"{src} tag — review"
        out.append({
            "price": px, "source": src, "action": action,
            "vote": lv.get("vote", "NEUTRAL"),
            "dist_pct": lv.get("dist_pct", 0.0),
        })
    return out


def compute_scenarios(pd_dict: dict, spot: float | None, df: pd.DataFrame) -> dict:
    """Bull/base/bear with probabilities derived from composite conviction.
    Targets pulled from existing detector levels. EV-weighted return computed."""
    composite = pd_dict.get("composite") or {}
    fi = pd_dict.get("fibonacci") or {}
    ic = pd_dict.get("ichimoku") or {}
    vp = pd_dict.get("volume_profile") or {}
    sp = spot or 0.0

    conviction = composite.get("conviction", "LOW")
    if conviction == "HIGH":
        p_bull, p_base, p_bear = 0.60, 0.30, 0.10
    elif conviction == "MEDIUM":
        p_bull, p_base, p_bear = 0.45, 0.35, 0.20
    else:
        p_bull, p_base, p_bear = 0.30, 0.40, 0.30

    bull_target = (fi.get("levels") or {}).get("ext_1272") or (sp * 1.08 if sp else None)
    bear_target = round(sp - 1.25 * _atr_value_safe(pd_dict, sp), 2) if sp else None
    base_target = sp * 1.02 if sp else None
    if vp.get("vah") and sp:
        base_target = max(base_target or 0, float(vp["vah"]))

    def _pct(p):
        return round((p - sp) / sp * 100, 2) if (sp and p) else 0.0

    bull_pct = _pct(bull_target)
    base_pct = _pct(base_target)
    bear_pct = _pct(bear_target)

    ev = p_bull * bull_pct + p_base * base_pct + p_bear * bear_pct

    methods_support = {
        "WYC": pd_dict.get("wyckoff", {}).get("vote", "NEUTRAL"),
        "FIB": pd_dict.get("fibonacci", {}).get("vote", "NEUTRAL"),
        "ICHI": pd_dict.get("ichimoku", {}).get("vote", "NEUTRAL"),
        "TL": pd_dict.get("trendlines", {}).get("vote", "NEUTRAL"),
        "VP": pd_dict.get("volume_profile", {}).get("vote", "NEUTRAL"),
        "SR": pd_dict.get("sr_levels", {}).get("vote", "NEUTRAL"),
        "CLS": pd_dict.get("classical", {}).get("vote", "NEUTRAL"),
    }

    vah_str = f"VAH (${float(vp['vah']):.2f})" if vp.get("vah") else "VAH"
    kijun_str = f"Kijun (${float(ic['kijun']):.2f})" if ic.get("kijun") else "Kijun"
    fib_618 = (fi.get("levels") or {}).get("r_0618")
    fib_618_str = f"Fib 0.618 (${float(fib_618):.2f})" if fib_618 else "Fib 0.618"

    return {
        "ev_weighted_return": round(ev, 2),
        "bull": {
            "probability": p_bull,
            "target_price": round(bull_target, 2) if bull_target else None,
            "target_pct": bull_pct,
            "trigger": f"Two daily closes above {vah_str} on rising volume.",
            "path": f"Tag {vah_str} → hold above for 2d → ride to swing high → measured-move thrust to 1.272 ext.",
            "method_support": methods_support,
            "ev_contrib": round(p_bull * bull_pct, 2),
        },
        "base": {
            "probability": p_base,
            "target_price": round(base_target, 2) if base_target else None,
            "target_pct": base_pct,
            "trigger": f"No {vah_str} acceptance + no breakdown below {kijun_str}. Price ranges awaiting catalyst.",
            "path": "Sideways drift · retests of swing high · pullbacks to Kijun · POC stays as distant anchor.",
            "method_support": methods_support,
            "ev_contrib": round(p_base * base_pct, 2),
        },
        "bear": {
            "probability": p_bear,
            "target_price": bear_target,
            "target_pct": bear_pct,
            "trigger": f"Daily close below {kijun_str} followed by close below {fib_618_str}. Wyckoff slope flips negative.",
            "path": f"Reject from VAH → break Kijun → cascade through Fib 0.618 → stop tagged. Markup → distribution transition.",
            "method_support": methods_support,
            "ev_contrib": round(p_bear * bear_pct, 2),
        },
    }


def build_entry_zone_and_narrative(pd_dict: dict, spot: float | None,
                                     df: pd.DataFrame) -> dict:
    """Compose the execution ticket: entry zone (ATR-banded), stop, T1, T2,
    R:R, narrative."""
    sp = spot or 0.0
    fi = pd_dict.get("fibonacci") or {}
    vp = pd_dict.get("volume_profile") or {}
    ic = pd_dict.get("ichimoku") or {}
    composite = pd_dict.get("composite") or {}
    atr = _atr_value_safe(pd_dict, sp)

    stop = round(sp - 1.25 * atr, 2) if sp else None
    t1 = (fi.get("levels") or {}).get("ext_1272")
    t2 = (fi.get("levels") or {}).get("ext_1618")
    entry_low = round(sp - 0.5 * atr, 2) if sp else None
    entry_high = round(sp + 0.5 * atr, 2) if sp else None

    rr = None
    if sp and stop and t1 and sp > stop:
        risk = sp - stop
        reward = float(t1) - sp
        if risk > 0:
            rr = round(reward / risk, 2)

    conviction = composite.get("conviction", "LOW")
    verdict = composite.get("verdict", "NEUTRAL")
    bull_count = composite.get("bull_count", 0)
    quant_total = sum([composite.get("bull_count", 0),
                       composite.get("bear_count", 0),
                       composite.get("neutral_count", 0)])

    narrative_lines = []
    if rr:
        narrative_lines.append(
            f"Half-position entry now (${entry_low:.2f}–${entry_high:.2f} range) "
            f"with full-position trigger on 2 daily closes above VAH "
            + (f"(${float(vp['vah']):.2f})." if vp.get("vah") else ".")
        )
    narrative_lines.append(
        f"Justification: {bull_count} of {quant_total} methods aligned "
        f"{verdict.lower()} — {conviction} conviction. "
        f"Wyckoff confidence is {(pd_dict.get('wyckoff', {}).get('confidence', 0)*100):.0f}%. "
        f"NEUTRAL methods are missing alignment, not arguing against."
    )
    if stop and t1:
        kijun = ic.get("kijun")
        kijun_phrase = f" sits below the Kijun (${float(kijun):.2f})" if kijun else ""
        narrative_lines.append(
            f"Stop at ${stop:.2f} is 1.25 ATR below entry{kijun_phrase}. "
            f"T1 at ${float(t1):.2f} hits the 1.272 Fibonacci extension. "
            + (f"T2 at ${float(t2):.2f} is the 1.618 stretch." if t2 else "")
        )

    return {
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "stop": stop,
        "t1": round(float(t1), 2) if t1 else None,
        "t2": round(float(t2), 2) if t2 else None,
        "rr_ratio": rr,
        "atr_used": round(atr, 2) if atr else None,
        "narrative": " ".join(narrative_lines),
    }


def attach_pattern_data(result: dict, df: pd.DataFrame, ticker: str,
                         compute_hit_rates: bool = False) -> None:
    """Mutates result in-place:
      result['pattern_data']      = detect_all_patterns output
      result['pattern_hit_rates'] = Wilson LBs (if compute_hit_rates=True; else from cache)
    """
    try:
        result["pattern_data"] = detect_all_patterns(df)
    except Exception as e:
        result["pattern_data"] = {"error": str(e), "synth": False}
    if compute_hit_rates:
        try:
            hr = compute_pattern_hit_rates(df, ticker)
            hr["updated"] = datetime.utcnow().isoformat()
            save_pattern_hit_rate(ticker, hr)
            result["pattern_hit_rates"] = hr
        except Exception:
            result["pattern_hit_rates"] = _empty_pattern_hit_rates()


# ═══════════════════════════════════════════════════════════════════════
# 12. CLI · self-test
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
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
    print(f"\nPattern engine — {ticker} · {len(df)} bars")
    p = detect_all_patterns(df)
    for k in ["wyckoff", "classical", "volume_profile", "fibonacci",
              "ichimoku", "sr_levels", "trendlines"]:
        d = p[k]
        print(f"  {k:18} → {d.get('vote', '—'):<8} · {d.get('rationale', '')[:90]}")
    c = p["composite"]
    print(f"\n  COMPOSITE → {c['verdict']} · {c['conviction']} · "
          f"{c['bull_count']}B {c['bear_count']}S {c['neutral_count']}N")
    print(f"\n  Computing hit rates (sliding-window, may take ~1 min)...")
    hr = compute_pattern_hit_rates(df, ticker)
    for k in ["fib_0618_bounce", "ichi_tk_cross", "vp_poc_bounce",
              "sr_level_hold", "trendline_break_followthrough", "classical_breakout"]:
        d = hr[k]
        print(f"  {k:34} · WL={d['wilson_lb']:5.1f}% · n={d['total']:3} · {d['sample_size_flag']}")
