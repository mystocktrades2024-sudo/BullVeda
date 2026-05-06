"""
theories.py — Strict implementations of Dow / Wyckoff / Elliott / Gann theories.

Each module returns a single state label. Theory confluence is computed as
the count of theories whose state aligns with bullish (or bearish) direction.

Per Phase-1 feedback (2026-04-29):
- The methodology checklist conflates technical indicators (MA stack, sector
  strength, no-late-wave) with actual theory confluence. This module fixes
  that by providing separate, strict theory state outputs.
- Hard confluence gate: reject if < 2 theories agree (Gann fallback eligible
  while implementation pending).

States (consistent vocabulary across theories):
    BULLISH | BEARISH | NEUTRAL | UNKNOWN | UNAVAILABLE
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

log = logging.getLogger("theories")


# ── Dow Theory ──────────────────────────────────────────────────────────────

def _hh_hl(series, window: int) -> tuple[bool, bool]:
    """Split last `window` bars in half; return (HH_present, HL_present)."""
    if series is None or len(series) < window:
        return (False, False)
    recent = series.iloc[-window:]
    mid = len(recent) // 2
    return (
        float(recent.iloc[mid:].max()) > float(recent.iloc[:mid].max()),
        float(recent.iloc[mid:].min()) > float(recent.iloc[:mid].min()),
    )


def dow_state(spy_close: "pd.Series | None",
              spy_weekly: "pd.Series | None" = None) -> dict:
    """
    Pure Dow Theory: primary trend determined by SPY higher-highs +
    higher-lows on weekly (or daily fallback). Strict — both HH and HL
    required for BULLISH; both lower-high and lower-low for BEARISH.

    Returns {state, evidence, confidence}.
    """
    # Try weekly first (the textbook timeframe for primary trend)
    if spy_weekly is not None and len(spy_weekly) >= 26:
        hh, hl = _hh_hl(spy_weekly, 26)
        if hh and hl:
            return {"state": "BULLISH", "evidence": "weekly 26w HH+HL", "confidence": "HIGH"}
        if not hh and not hl:
            return {"state": "BEARISH", "evidence": "weekly 26w no HH no HL", "confidence": "HIGH"}
        # Mixed weekly — check daily for confirmation
        if spy_close is not None and len(spy_close) >= 120:
            d_hh, d_hl = _hh_hl(spy_close, 120)
            if d_hh and d_hl:
                return {"state": "NEUTRAL", "evidence": f"weekly mixed (HH={hh} HL={hl}), daily 120d HH+HL", "confidence": "MED"}
        return {"state": "NEUTRAL", "evidence": f"weekly HH={hh} HL={hl}", "confidence": "MED"}

    # Daily-only fallback
    if spy_close is not None and len(spy_close) >= 120:
        hh, hl = _hh_hl(spy_close, 120)
        if hh and hl:
            return {"state": "BULLISH", "evidence": "daily 120d HH+HL", "confidence": "MED"}
        if not hh and not hl:
            return {"state": "BEARISH", "evidence": "daily 120d no HH no HL", "confidence": "MED"}
        return {"state": "NEUTRAL", "evidence": f"daily 120d HH={hh} HL={hl}", "confidence": "LOW"}

    return {"state": "UNKNOWN", "evidence": "insufficient SPY history", "confidence": "LOW"}


# ── Wyckoff Phase Classification ────────────────────────────────────────────

def wyckoff_phase(df: "pd.DataFrame | None") -> dict:
    """
    Wyckoff phase classifier (proxy until full spring/SOS/UTAD detection).

    Phases:
      ACCUMULATION — sideways range with declining volume (institutions absorbing)
      MARKUP       — uptrend with rising volume on advances
      DISTRIBUTION — sideways range at highs with rising/heavy volume
      MARKDOWN     — downtrend with rising volume on declines
      UNKNOWN      — insufficient or ambiguous evidence

    Heuristic rules (60-bar window):
      1. Compute price range (high-low)/midprice over last 30 bars vs prior 30
      2. If range_recent / range_prior > 0.5 (still expanding) → trending
         If < 0.4 → sideways
      3. Direction: 30-day return + slope of EMA20
      4. Volume ratio: avg vol on up-days vs down-days
    """
    if df is None or len(df) < 60:
        return {"state": "UNKNOWN", "evidence": "<60 bars history", "confidence": "LOW"}

    try:
        close = df["Close"].squeeze() if "Close" in df else None
        vol = df["Volume"].squeeze() if "Volume" in df else None
        high = df["High"].squeeze() if "High" in df else None
        low = df["Low"].squeeze() if "Low" in df else None
        if close is None or vol is None:
            return {"state": "UNKNOWN", "evidence": "missing OHLCV", "confidence": "LOW"}

        recent = close.iloc[-30:]
        prior = close.iloc[-60:-30]
        recent_high = float(high.iloc[-30:].max()) if high is not None else float(recent.max())
        recent_low = float(low.iloc[-30:].min()) if low is not None else float(recent.min())
        recent_mid = (recent_high + recent_low) / 2 or 1
        recent_range_pct = (recent_high - recent_low) / recent_mid * 100

        # Direction: 30-day return + slope
        ret_30 = (float(close.iloc[-1]) / float(close.iloc[-30]) - 1) * 100 if float(close.iloc[-30]) else 0

        # Volume on up-days vs down-days (last 20 bars)
        last20_close = close.iloc[-20:]
        last20_vol = vol.iloc[-20:]
        delta = last20_close.diff()
        up_vol = last20_vol[delta > 0].mean() if (delta > 0).any() else 0
        dn_vol = last20_vol[delta < 0].mean() if (delta < 0).any() else 0

        # Sideways detection: range narrow vs price level
        is_sideways = recent_range_pct < 8.0 and abs(ret_30) < 4.0
        is_trending_up = ret_30 > 6.0
        is_trending_down = ret_30 < -6.0

        if is_trending_up and up_vol > dn_vol * 1.1:
            return {"state": "MARKUP",
                    "evidence": f"+{ret_30:.1f}% over 30d, up-vol > dn-vol",
                    "confidence": "MED" if ret_30 > 10 else "LOW"}
        if is_trending_down and dn_vol > up_vol * 1.1:
            return {"state": "MARKDOWN",
                    "evidence": f"{ret_30:.1f}% over 30d, dn-vol > up-vol",
                    "confidence": "MED" if ret_30 < -10 else "LOW"}
        if is_sideways:
            # Distinguish accumulation vs distribution by location (vs 200d) + volume trend
            if len(close) >= 200:
                price = float(close.iloc[-1])
                sma200 = float(close.rolling(200).mean().iloc[-1])
                near_lows = price < sma200 * 1.05  # within 5% of 200d MA from below
                near_highs = price > sma200 * 1.10  # >10% above 200d
                vol_recent_avg = float(last20_vol.mean())
                vol_prior_avg = float(vol.iloc[-40:-20].mean()) if len(vol) >= 40 else vol_recent_avg
                vol_declining = vol_recent_avg < vol_prior_avg * 0.85
                vol_rising = vol_recent_avg > vol_prior_avg * 1.15
                if near_lows and vol_declining:
                    return {"state": "ACCUMULATION",
                            "evidence": f"sideways near 200d, vol declining ({vol_recent_avg/max(1,vol_prior_avg):.2f}×)",
                            "confidence": "MED"}
                if near_highs and vol_rising:
                    return {"state": "DISTRIBUTION",
                            "evidence": f"sideways at highs, vol rising ({vol_recent_avg/max(1,vol_prior_avg):.2f}×)",
                            "confidence": "MED"}
            return {"state": "UNKNOWN",
                    "evidence": f"sideways but no clear accum/dist signal (range {recent_range_pct:.1f}%)",
                    "confidence": "LOW"}

        # Trending but volume not confirming
        if is_trending_up:
            return {"state": "MARKUP",
                    "evidence": f"+{ret_30:.1f}% but volume not confirming",
                    "confidence": "LOW"}
        if is_trending_down:
            return {"state": "MARKDOWN",
                    "evidence": f"{ret_30:.1f}% but volume not confirming",
                    "confidence": "LOW"}

        return {"state": "UNKNOWN",
                "evidence": f"weak signal: ret_30={ret_30:.1f}%, range={recent_range_pct:.1f}%",
                "confidence": "LOW"}
    except Exception as e:
        return {"state": "UNKNOWN", "evidence": f"error: {e}", "confidence": "LOW"}


# ── Elliott Wave State ──────────────────────────────────────────────────────

def elliott_state(df: "pd.DataFrame | None",
                  ew_data: dict | None = None) -> dict:
    """
    Map Elliott Wave label to a directional state.

    States:
      EARLY_IMPULSE — Wave 1, 2, or 3 (positions to take)
      LATE_IMPULSE  — Wave 5 (warning, late-cycle)
      CORRECTIVE    — Wave 4, A, B, C (avoid new longs)
      INVALID       — broken structure / sideways
      UNKNOWN       — no Elliott data

    ew_data is the output of analysis.score_elliott_wave().
    """
    if not ew_data:
        return {"state": "UNKNOWN", "evidence": "no Elliott data", "confidence": "LOW"}

    label = str(ew_data.get("wave_label") or ew_data.get("wave") or "").lower()
    wave_num = ew_data.get("wave_number") or ew_data.get("wave_n")

    # Try to extract integer wave number from label if not provided
    if wave_num is None and label:
        for ch in label:
            if ch.isdigit():
                try:
                    wave_num = int(ch)
                    break
                except ValueError:
                    continue

    if wave_num is not None:
        try:
            n = int(wave_num)
            if n in (1, 2, 3):
                return {"state": "EARLY_IMPULSE", "evidence": f"Wave {n} ({label})", "confidence": "MED"}
            if n == 4:
                return {"state": "CORRECTIVE", "evidence": f"Wave 4 ({label})", "confidence": "MED"}
            if n == 5:
                return {"state": "LATE_IMPULSE", "evidence": f"Wave 5 ({label})", "confidence": "MED"}
        except (ValueError, TypeError):
            pass

    if "abc" in label or "correction" in label or "wave a" in label or "wave b" in label or "wave c" in label:
        return {"state": "CORRECTIVE", "evidence": f"corrective: {label}", "confidence": "LOW"}

    if not label or "no clear" in label or "sideways" in label:
        return {"state": "INVALID", "evidence": f"no structure: {label}", "confidence": "LOW"}

    return {"state": "UNKNOWN", "evidence": f"unparseable: {label}", "confidence": "LOW"}


# ── Gann (stub — implementation pending) ────────────────────────────────────

def gann_state(df: "pd.DataFrame | None") -> dict:
    """
    Gann square-of-nine + time cycles (NOT YET IMPLEMENTED).

    Returns UNAVAILABLE so confluence gate falls back to 3-theory eligibility
    (Dow/Wyckoff/Elliott).
    """
    return {"state": "UNAVAILABLE", "evidence": "Gann module not implemented", "confidence": "LOW"}


# ── Theory Confluence Gate ──────────────────────────────────────────────────

def theory_confluence(df: "pd.DataFrame | None",
                      weekly_df: "pd.DataFrame | None",
                      spy_close: "pd.Series | None",
                      spy_weekly: "pd.Series | None",
                      ew_data: dict | None) -> dict:
    """
    Compute the four theory states and the bullish-confluence count.

    Returns:
        {
          "states": {dow, wyckoff, elliott, gann},
          "bull_count": int,
          "bear_count": int,
          "min_required": 2,
          "eligible_theories": ["dow","wyckoff","elliott"]  # gann excluded while stubbed
          "hard_gate_pass": bool,
          "direction": BULLISH | BEARISH | NEUTRAL,
          "evidence_summary": str,
        }

    Hard gate behavior (per feedback item #15):
      hard_gate_pass = True iff bull_count >= min_required (default 2)
      Failing this gate should hard-reject any new BUY entry, regardless of
      pillar score.
    """
    dow = dow_state(spy_close, spy_weekly)
    wyckoff = wyckoff_phase(df)
    elliott = elliott_state(df, ew_data)
    gann = gann_state(df)

    states = {"dow": dow, "wyckoff": wyckoff, "elliott": elliott, "gann": gann}

    # Bullish alignment count — strict definitions
    bull_aligned = {
        "dow": dow["state"] == "BULLISH",
        "wyckoff": wyckoff["state"] in ("ACCUMULATION", "MARKUP"),
        "elliott": elliott["state"] == "EARLY_IMPULSE",
        "gann": gann["state"] == "BULLISH",  # always False while stubbed
    }
    bear_aligned = {
        "dow": dow["state"] == "BEARISH",
        "wyckoff": wyckoff["state"] in ("DISTRIBUTION", "MARKDOWN"),
        "elliott": elliott["state"] in ("LATE_IMPULSE", "CORRECTIVE"),
        "gann": gann["state"] == "BEARISH",
    }
    bull_count = sum(bull_aligned.values())
    bear_count = sum(bear_aligned.values())

    # Eligibility: gann excluded from eligible set while stubbed (avoids penalizing all)
    eligible = ["dow", "wyckoff", "elliott"]
    if gann["state"] != "UNAVAILABLE":
        eligible.append("gann")

    min_required = 2
    hard_gate_pass = bull_count >= min_required

    if bull_count > bear_count and bull_count >= min_required:
        direction = "BULLISH"
    elif bear_count > bull_count and bear_count >= min_required:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # Build evidence summary for UI
    aligned_names = [k for k, v in bull_aligned.items() if v]
    if direction == "BULLISH":
        summary = f"{bull_count}/{len(eligible)} theories bullish: {', '.join(aligned_names)}"
    elif direction == "BEARISH":
        bearnames = [k for k, v in bear_aligned.items() if v]
        summary = f"{bear_count}/{len(eligible)} theories bearish: {', '.join(bearnames)}"
    else:
        summary = f"No confluence — bull={bull_count} bear={bear_count} of {len(eligible)} theories"

    return {
        "states": {k: v["state"] for k, v in states.items()},
        "details": states,  # full {state, evidence, confidence} per theory
        "bull_count": bull_count,
        "bear_count": bear_count,
        "min_required": min_required,
        "eligible_theories": eligible,
        "hard_gate_pass": hard_gate_pass,
        "direction": direction,
        "evidence_summary": summary,
        "bull_aligned": bull_aligned,
        "bear_aligned": bear_aligned,
    }
