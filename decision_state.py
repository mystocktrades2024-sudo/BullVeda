"""
decision_state.py — State-based classification patch (2026-04-15).

Augments the existing verdict/score engine with forward-looking state fields:

    state = {
      setup_quality: STRONG | GOOD | WEAK,
      phase:        BREAKOUT | POST_BREAKOUT_DRIFT | PULLBACK | CONSOLIDATION | RANGE | TREND_CONTINUATION,
      location:     AT_VALUE | ABOVE_VALUE | EXTENDED | NO_EDGE | LOST_STRUCTURE,
      edge:         VALID | NONE,
      action:       BUY | WATCH | WAIT_FOR_PULLBACK | AVOID,
    }

DOES NOT replace existing gates, regime thresholds, or score logic.
Only changes decision-state classification and messaging so the UI stops
showing backward-looking labels like "MISSED" as the primary state.
"""
from __future__ import annotations

from typing import Any


def _safe_min(*vals) -> float | None:
    xs = [v for v in vals if v is not None]
    return min(xs) if xs else None


def _safe_max(*vals) -> float | None:
    xs = [v for v in vals if v is not None]
    return max(xs) if xs else None


def build_value_zones(d: dict) -> dict:
    """
    Expected keys: ema21, ema50, support, vwap, prior_base_low, prior_base_high, atr.
    Returns {primary_zone: (low, high), deep_zone: (low, high)}.
    """
    primary_low  = _safe_min(d.get("ema21"), d.get("support"), d.get("vwap"))
    primary_high = _safe_max(d.get("ema21"), d.get("support"), d.get("vwap"))
    deep_low     = _safe_min(d.get("ema50"), d.get("prior_base_low"))
    deep_high    = _safe_max(d.get("ema50"), d.get("prior_base_low"))

    return {
        "primary_zone": (
            round(primary_low, 2) if primary_low is not None else None,
            round(primary_high, 2) if primary_high is not None else None,
        ),
        "deep_zone": (
            round(deep_low, 2) if deep_low is not None else None,
            round(deep_high, 2) if deep_high is not None else None,
        ),
    }


def classify_phase(d: dict) -> str:
    """
    Requires: breakout_recent, price, recent_high, rvol, divergence_4h, inside_cloud, ema21, rsi.
    Returns phase label.
    """
    price       = d.get("price") or 0
    ema21       = d.get("ema21") or 0
    rvol        = d.get("rvol") or 0
    recent_high = d.get("recent_high") or 0

    if d.get("breakout_recent") and rvol < 1.0 and recent_high and price >= recent_high * 0.97:
        return "POST_BREAKOUT_DRIFT"

    if d.get("breakout_recent") and rvol >= 1.2:
        return "BREAKOUT"

    if ema21 and abs(price - ema21) / ema21 <= 0.015:
        return "PULLBACK"

    if d.get("divergence_4h") and rvol < 1.0:
        return "CONSOLIDATION"

    if d.get("inside_cloud"):
        return "RANGE"

    return "TREND_CONTINUATION"


def classify_location(d: dict, zones: dict) -> str:
    """
    Replaces backward-looking MISSED with current-location state.
    Expected: price, ema21, atr.
    """
    price = d.get("price")
    ema21 = d.get("ema21")
    atr   = d.get("atr") or 0
    if price is None:
        return "NO_EDGE"

    pl, ph = zones["primary_zone"]
    dl, dh = zones["deep_zone"]

    if pl is not None and ph is not None and pl <= price <= ph:
        return "AT_VALUE"

    if dl is not None and dh is not None and dl <= price <= dh:
        return "AT_VALUE"

    # Extended = materially above value (>1.25 ATR above EMA21)
    if ph is not None and ema21 is not None and atr and price > max(ph, ema21 + 1.25 * atr):
        return "EXTENDED"

    if ph is not None and price > ph:
        return "ABOVE_VALUE"

    if dl is not None and price < dl:
        return "LOST_STRUCTURE"

    return "NO_EDGE"


def low_participation_block(d: dict) -> bool:
    rvol = d.get("rvol")
    return rvol is not None and rvol < 0.8


def confirmation_score(d: dict) -> int:
    score = 0
    if d.get("bullish_candle"):       score += 1
    if d.get("volume_expansion"):     score += 1
    if d.get("macd_hist_rising"):     score += 1
    if d.get("price_holding_zone_low"): score += 1
    if d.get("rsi_turning_up"):       score += 1
    return score


def _setup_quality(score: float, buy_min: float, watch_min: float) -> str:
    if score >= buy_min + 5:
        return "STRONG"
    if score >= watch_min:
        return "GOOD"
    return "WEAK"


def patched_trade_decision(
    d: dict,
    score: float,
    buy_min: float,
    watch_min: float,
    rr: float,
    rr_min: float,
) -> dict:
    """
    Returns state dict. Does NOT override existing hard gates — caller
    combines this with the existing verdict.
    """
    zones    = build_value_zones(d)
    phase    = classify_phase(d)
    location = classify_location(d, zones)
    rvol_blk = low_participation_block(d)

    result: dict[str, Any] = {
        "zones":         zones,
        "phase":         phase,
        "location":      location,
        "edge":          "NONE",
        "action":        "AVOID",
        "reason":        None,
        "setup_quality": _setup_quality(score, buy_min, watch_min),
    }

    if score < watch_min:
        result["action"] = "AVOID"
        result["reason"] = "Below watch threshold"
        return result

    if location in ("ABOVE_VALUE", "EXTENDED", "NO_EDGE"):
        result["action"] = "WAIT_FOR_PULLBACK"
        result["reason"] = f"Price not in value zone ({location})"
        return result

    if location == "LOST_STRUCTURE":
        result["action"] = "AVOID"
        result["reason"] = "Structure lost below deep zone"
        return result

    if location == "AT_VALUE":
        cscore = confirmation_score(d)

        if rvol_blk:
            result["action"] = "WATCH"
            result["reason"] = "At value, but participation too weak"
            return result

        if score >= buy_min and rr >= rr_min and cscore >= 2:
            result["edge"]   = "VALID"
            result["action"] = "BUY"
            result["reason"] = "At value with confirmation"
            return result

        result["action"] = "WATCH"
        result["reason"] = "At value, waiting for confirmation"
        return result

    return result


# ── Dashboard-facing labels ─────────────────────────────────────────────
# Map legacy backward-looking entry_quality values to forward-looking ones.
LABEL_MAP = {
    "MISSED":   "ABOVE_VALUE",
    "EXTENDED": "EXTENDED",
    "WATCH":    "WATCH",
    "VALID":    "AT_VALUE",
    "PULLBACK": "AT_VALUE",
    "FRESH":    "AT_VALUE",
}

PHASE_LABEL_MAP = {
    "BREAKOUT_EXPANSION":   "BREAKOUT",
    "POST_BREAKOUT_DRIFT":  "POST_BREAKOUT_DRIFT",
}


def classify_pullback_wait(state: dict, score: float, rs_rank: float,
                           buy_min: float, rs_min: float) -> dict | None:
    """
    Identify extended quality names that need a PULLBACK_WAIT bucket.
    Returns enriched state dict with PULLBACK_WAIT action, or None if doesn't qualify.

    Qualifies when ALL of:
      - score >= buy_min (quality passed)
      - rs_rank >= rs_min (leader confirmed)
      - location = EXTENDED or phase = POST_BREAKOUT_DRIFT
      - entry zone is computable (valid zones)
      - the ONLY blocker is extension (not structural failure)
    """
    if not isinstance(state, dict):
        return None

    quality_passes = score >= buy_min and rs_rank >= rs_min
    if not quality_passes:
        return None

    location = state.get("location", "")
    phase = state.get("phase", "")
    extension_blocker = location in ("EXTENDED", "ABOVE_VALUE") or phase == "POST_BREAKOUT_DRIFT"
    if not extension_blocker:
        return None

    zones = state.get("zones") or {}
    pz = zones.get("primary_zone", (None, None))
    has_valid_zone = isinstance(pz, (list, tuple)) and len(pz) >= 2 and pz[0] is not None
    if not has_valid_zone:
        return None

    # Don't classify as PULLBACK_WAIT if structure is lost
    if location == "LOST_STRUCTURE" or state.get("edge") == "NONE" and location == "NO_EDGE":
        return None

    return {
        **state,
        "action": "PULLBACK_WAIT",
        "reason": "Quality leader, extended — wait for pullback to entry zone",
    }


def compute_distance_to_entry(current_price: float, entry_high: float | None) -> float | None:
    """How far above the entry zone ceiling the current price is (as fraction)."""
    if entry_high is None or current_price is None or current_price <= 0:
        return None
    if current_price <= entry_high:
        return 0.0
    return round((current_price - entry_high) / current_price, 4)


def proximity_bucket(distance_pct: float | None) -> str:
    """Classify distance into imminent / patient / dropped."""
    if distance_pct is None:
        return "unknown"
    if distance_pct <= 0.03:
        return "imminent"
    if distance_pct <= 0.15:
        return "patient"
    return "dropped"


def render_dashboard_message(result: dict) -> str:
    """Forward-looking, not backward-looking."""
    a = result.get("action")
    p = result.get("phase")

    if a == "PULLBACK_WAIT":
        loc = result.get("location", "")
        dist = result.get("distance_to_entry_pct")
        dist_str = f" ({dist*100:.1f}% above entry zone)" if dist else ""
        if p == "POST_BREAKOUT_DRIFT":
            return f"Quality leader in post-breakout drift{dist_str}. Wait for pullback to entry zone."
        return f"Quality leader, extended above value{dist_str}. Set alert at entry zone."

    if a == "BUY":
        return "At value zone with confirmation. Valid swing entry."

    if a == "WATCH":
        r = result.get("reason") or ""
        if "participation" in r.lower():
            return "At value zone, but participation too weak. Hold off."
        return "At value zone, but confirmation is incomplete."

    if a == "WAIT_FOR_PULLBACK":
        if p == "POST_BREAKOUT_DRIFT":
            return "Completed breakout, now above value with weak participation. Wait for pullback."
        loc = result.get("location", "")
        if loc == "EXTENDED":
            return "Price extended beyond value. Wait for pullback to EMA21."
        return "Good setup, but price is above value zone. Wait for pullback."

    if a == "AVOID":
        r = result.get("reason") or ""
        if "structure" in r.lower():
            return "Structure lost below deep zone. No edge."
        return "No current edge."

    return "No current edge."


def extract_indicator_payload(indicators: dict, price: float, setup_type: str = "") -> dict:
    """
    Adapter: build the dict that patched_trade_decision expects from the
    existing analysis.py `indicators` structure. Missing fields default to
    None / False so the phase/location classifiers still return sensibly.
    """
    if not isinstance(indicators, dict):
        indicators = {}

    # Inside-cloud (Ichimoku): require span_a/span_b bracketing price
    span_a = indicators.get("ichi_span_a") or indicators.get("span_a")
    span_b = indicators.get("ichi_span_b") or indicators.get("span_b")
    inside_cloud = False
    if span_a is not None and span_b is not None and price is not None:
        lo, hi = sorted([span_a, span_b])
        inside_cloud = lo <= price <= hi

    # Price-holding-zone-low: last close within 0.5% above primary_low (ema21/support/vwap min)
    ema21 = indicators.get("ema21") or indicators.get("EMA21")
    support = indicators.get("support")
    vwap = indicators.get("vwap") or indicators.get("VWAP")
    primary_low = _safe_min(ema21, support, vwap)
    holding = False
    if primary_low is not None and price is not None:
        holding = primary_low <= price <= primary_low * 1.005

    return {
        "price":           price,
        "ema21":           ema21,
        "ema50":           indicators.get("ema50") or indicators.get("EMA50"),
        "support":         support,
        "vwap":            vwap,
        "atr":             indicators.get("atr") or indicators.get("ATR"),
        "prior_base_low":  indicators.get("prior_base_low"),
        "prior_base_high": indicators.get("prior_base_high"),
        "rvol":            indicators.get("rvol"),
        "rsi":             indicators.get("rsi"),
        "recent_high":     indicators.get("recent_high") or indicators.get("high_52wk"),
        "breakout_recent": bool(indicators.get("breakout_recent") or ("breakout" in (setup_type or "").lower())),
        "divergence_4h":   bool(indicators.get("divergence_4h") or indicators.get("bearish_divergence")),
        "inside_cloud":    inside_cloud,
        "bullish_candle":  bool(indicators.get("bullish_candle") or indicators.get("hammer") or indicators.get("bullish_engulf")),
        "volume_expansion": (indicators.get("rvol") or 0) >= 1.2,
        "macd_hist_rising": bool(indicators.get("macd_hist_rising")),
        "price_holding_zone_low": holding,
        "rsi_turning_up":  bool(indicators.get("rsi_turning_up")),
    }
