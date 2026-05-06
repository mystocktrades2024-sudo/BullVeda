"""
Tier 1 strategy enhancements — additive scoring signals.

Each function returns a dict: { "points": int, "detected": bool, "narrative": str, "data": dict }

All detectors are opt-in via config (`tier1_signals.<flag>: true`). Failures
return zero-points / detected=False so they can never crash a scan.

Wired into analysis.py:score_swing() as an additive scoring layer applied
AFTER the 5-pillar score. Surfaced in the bundle under `tier1_signals` field
for v2 dashboard display.

Built 2026-04-30 in response to user request "build all 6 Tier 1 items".
"""
from __future__ import annotations
import math
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# 1. INSIDER CLUSTER scoring
# ─────────────────────────────────────────────────────────────────────────────
def insider_cluster_score(insider, insider_full) -> dict:
    # Defensive: caller may pass list / None / wrong shape
    if not isinstance(insider, dict): insider = None
    if not isinstance(insider_full, dict): insider_full = None
    """
    Detect insider buying clusters — multiple insiders within 30d, with bonus
    for C-suite participation. Higher signal quality than raw net-flow.

    Scoring:
      - 3+ insiders buying in 30d:                  +5 base
      - 5+ insiders:                                +7 base (replaces 5)
      - CEO buying within cluster:                  +3
      - CFO buying within cluster:                  +2
      - Net buy value > $500K:                      +2
      - Concentrated within 7 days (urgency):       +2
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    if not insider:
        return out
    insf = insider_full or {}
    buys = int(insider.get("buys") or 0)
    if buys < 3:
        return out

    points = 5
    parts = [f"{buys} insider buys in 30d"]
    if buys >= 5:
        points = 7
        parts[0] = f"{buys} insider buys in 30d (5+ = strong cluster)"

    ceo_buy = bool(insf.get("ceo_buy"))
    cfo_buy = bool(insf.get("cfo_buy"))
    if ceo_buy:
        points += 3
        parts.append("CEO bought (high-conviction signal)")
    if cfo_buy:
        points += 2
        parts.append("CFO bought")

    buy_value = float(insf.get("buy_value_30d") or insider.get("buy_value") or 0)
    if buy_value > 500_000:
        points += 2
        parts.append(f"${buy_value/1e6:.2f}M total purchases")

    # Urgency bonus — if net buys clustered in last 7 days
    days_window = int(insider.get("days") or insf.get("recent_days") or 30)
    recent_buys = int(insider.get("recent") or insf.get("recent_buys") or 0)
    if recent_buys >= 2 and days_window <= 14:
        points += 2
        parts.append(f"{recent_buys} buys in last {days_window}d (urgency)")

    return {
        "points":    min(points, 12),
        "detected":  True,
        "narrative": " · ".join(parts),
        "data": {
            "buys": buys,
            "ceo_buy": ceo_buy,
            "cfo_buy": cfo_buy,
            "buy_value_usd": buy_value,
            "recent_buys": recent_buys,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. NR7 / Inside Day detector — narrow range volatility expansion setup
# ─────────────────────────────────────────────────────────────────────────────
def nr7_inside_day(df) -> dict:
    """
    NR7 = today's range is the narrowest of the last 7 days.
    Inside Day = today's high < yesterday's high AND today's low > yesterday's low.

    Both signal volatility compression — statistically expand within 3 days.
    Combined NR7 + Inside Day = highest-probability expansion setup.
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    try:
        if df is None or len(df) < 8:
            return out
        # Use last 7 ranges
        last7 = df.iloc[-7:]
        ranges = (last7["high"] - last7["low"]).tolist()
        today_range = ranges[-1]
        is_nr7 = all(today_range <= r + 1e-9 for r in ranges[:-1])

        # Inside day check (today vs yesterday)
        yest = df.iloc[-2]
        today = df.iloc[-1]
        is_inside = today["high"] < yest["high"] and today["low"] > yest["low"]

        if not is_nr7 and not is_inside:
            return out

        points = 0
        parts = []
        if is_nr7:
            points += 2
            parts.append("NR7 (narrowest range of last 7 days)")
        if is_inside:
            points += 2
            parts.append("Inside Day (range inside prior day)")
        if is_nr7 and is_inside:
            points += 2
            parts.append("NR7+Inside combo — highest-probability expansion setup")

        return {
            "points":    points,
            "detected":  True,
            "narrative": " · ".join(parts),
            "data": {
                "is_nr7": is_nr7,
                "is_inside": is_inside,
                "today_range": float(today_range),
                "avg_range_7d": float(sum(ranges) / len(ranges)),
            },
        }
    except Exception:
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. VOLUME DRY-UP at support — institutional accumulation proxy
# ─────────────────────────────────────────────────────────────────────────────
def volume_dryup_at_support(df, ema21: float | None, ema50: float | None) -> dict:
    """
    Volume contraction (last 5d avg < 0.7x of 20d avg) while price
    holds within 1% of EMA21 or EMA50 = sellers exhausted, buyers waiting.

    Often precedes 2-5 day expansion higher.
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    try:
        if df is None or len(df) < 25 or "volume" not in df.columns:
            return out
        vol = df["volume"]
        avg_20 = vol.iloc[-21:-1].mean()
        avg_5 = vol.iloc[-5:].mean()
        if avg_20 <= 0:
            return out
        ratio = avg_5 / avg_20
        if ratio >= 0.7:
            return out  # not dried up

        # Check price near EMA support
        last_close = float(df["close"].iloc[-1])
        near_ema21 = ema21 and abs(last_close - ema21) / ema21 < 0.015
        near_ema50 = ema50 and abs(last_close - ema50) / ema50 < 0.02
        if not near_ema21 and not near_ema50:
            return out

        # Confirm price is NOT in steep decline (don't catch falling knives)
        last5_change = (df["close"].iloc[-1] - df["close"].iloc[-6]) / df["close"].iloc[-6]
        if last5_change < -0.05:
            return out  # 5%+ down in 5 days — too weak

        points = 3
        parts = [f"Volume dry-up: 5d avg {ratio:.2f}× of 20d (sellers exhausted)"]
        if near_ema21:
            parts.append("price holding EMA21")
        elif near_ema50:
            parts.append("price holding EMA50")

        return {
            "points":    points,
            "detected":  True,
            "narrative": " · ".join(parts),
            "data": {
                "vol_ratio_5_to_20": round(ratio, 2),
                "near_ema21": near_ema21,
                "near_ema50": near_ema50,
                "last5_chg_pct": round(last5_change * 100, 2),
            },
        }
    except Exception:
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. OBV DIVERGENCE detector — bullish/bearish divergence
# ─────────────────────────────────────────────────────────────────────────────
def obv_divergence(df, lookback: int = 20) -> dict:
    """
    Bullish divergence: price makes lower low BUT OBV makes higher low.
      → accumulation hidden under weakness, often precedes reversal.
    Bearish divergence: price makes higher high BUT OBV makes lower high.
      → distribution into strength, often precedes top.
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    try:
        if df is None or len(df) < lookback + 5 or "volume" not in df.columns:
            return out
        # Compute OBV
        close = df["close"]
        vol = df["volume"]
        obv_series = []
        cum = 0
        for i in range(len(df)):
            if i == 0:
                obv_series.append(0)
                continue
            if close.iloc[i] > close.iloc[i-1]:
                cum += vol.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                cum -= vol.iloc[i]
            obv_series.append(cum)

        # Look at first half vs second half of lookback window
        recent = obv_series[-lookback:]
        recent_close = close.iloc[-lookback:].tolist()
        if len(recent) < lookback:
            return out

        first_half_low_idx = recent_close[:lookback//2].index(min(recent_close[:lookback//2]))
        second_half_low_idx = recent_close[lookback//2:].index(min(recent_close[lookback//2:])) + lookback//2
        first_half_high_idx = recent_close[:lookback//2].index(max(recent_close[:lookback//2]))
        second_half_high_idx = recent_close[lookback//2:].index(max(recent_close[lookback//2:])) + lookback//2

        # Bullish divergence: second-half price low < first-half price low
        # AND second-half OBV low > first-half OBV low
        price_lower_low = recent_close[second_half_low_idx] < recent_close[first_half_low_idx]
        obv_higher_low = recent[second_half_low_idx] > recent[first_half_low_idx]
        bullish_div = price_lower_low and obv_higher_low

        # Bearish divergence: opposite
        price_higher_high = recent_close[second_half_high_idx] > recent_close[first_half_high_idx]
        obv_lower_high = recent[second_half_high_idx] < recent[first_half_high_idx]
        bearish_div = price_higher_high and obv_lower_high

        if bullish_div:
            return {
                "points":    5,
                "detected":  True,
                "narrative": f"Bullish OBV divergence: price LL but OBV HL ({lookback}d window) — accumulation under weakness",
                "data": {"type": "bullish", "lookback": lookback},
            }
        if bearish_div:
            return {
                "points":    -5,
                "detected":  True,
                "narrative": f"Bearish OBV divergence: price HH but OBV LH ({lookback}d window) — distribution into strength",
                "data": {"type": "bearish", "lookback": lookback},
            }
        return out
    except Exception:
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 5. MEAN REVERSION setup — RSI oversold bounce with quality screen
# ─────────────────────────────────────────────────────────────────────────────
def mean_reversion_setup(rsi: float | None, above_200sma: bool, fund_score: float | None,
                         atr_pct: float | None, last5_close_chg: float | None) -> dict:
    """
    Mean Reversion setup — RSI < 30 (oversold) AND above 200 SMA (Stage 2 still intact)
    AND fundamentals decent (>= 50% of max) AND ATR not too high (avoid falling knives).

    Targets a bounce to EMA21 over 3-7 day hold. Different correlation profile than
    trend setups — adds diversification to the strategy mix.
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}, "setup_subtype": None}
    if rsi is None or rsi >= 35:
        return out
    if not above_200sma:
        return out  # don't catch falling stocks below their 200SMA
    if atr_pct and atr_pct > 6:
        return out  # too volatile — not a clean mean-reversion candidate

    # Quality gate — require at least mediocre fundamentals
    if fund_score is not None and fund_score < 4:
        return out  # too weak fundamentally

    # Don't catch falling knives — limit how much it's already dropped
    if last5_close_chg is not None and last5_close_chg < -0.10:
        return out  # 10%+ drop in 5 days — let it stabilize

    points = 6
    parts = [f"RSI {rsi:.0f} oversold", "above 200 SMA (Stage 2 intact)"]
    if rsi < 25:
        points += 2
        parts.append("deep oversold (<25)")
    if fund_score is not None and fund_score >= 6:
        points += 2
        parts.append("quality gate strong")

    return {
        "points":         min(points, 10),
        "detected":       True,
        "narrative":      " · ".join(parts),
        "setup_subtype":  "mean_reversion_bounce",
        "data": {
            "rsi": rsi,
            "fund_score": fund_score,
            "atr_pct": atr_pct,
            "last5_chg_pct": last5_close_chg * 100 if last5_close_chg is not None else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. EARNINGS BEAT-AND-RAISE filter
# ─────────────────────────────────────────────────────────────────────────────
def beat_and_raise_filter(earnings_data, estimate_revisions=None) -> dict:
    """Detect "Beat & Raise" PEAD — the highest-quality earnings setup.

    EODHD earnings calendar provides actual/estimate/percent beat.
    Guidance change is HARD to source directly — we use estimate-revisions
    direction (Zacks `zacks_estimate_revisions` per-ticker) as a PROXY for guidance:

      * Upward revisions > Downward      → effective "raised" guidance signal
      * Downward revisions >> Upward     → effective "lowered" guidance signal
      * Mixed / unchanged                → "inline" (no signal)

    Defensive on shape: accepts dict (preferred) or coerces to None otherwise.
    """
    if not isinstance(earnings_data, dict):
        earnings_data = None
    out = {"points": 0, "detected": False, "narrative": "", "data": {}, "tier": None}
    if not earnings_data:
        return out

    # ── Beat magnitude — accept multiple field names from EODHD or precomputed ──
    eps_beat = earnings_data.get("eps_beat_pct")
    rev_beat = earnings_data.get("revenue_beat_pct")
    if eps_beat is None:
        # EODHD calendar shape: {actual, estimate, percent}
        if earnings_data.get("percent") is not None:
            eps_beat = float(earnings_data["percent"])
        elif earnings_data.get("eps_actual") is not None and earnings_data.get("eps_estimate"):
            try:
                eps_beat = (float(earnings_data["eps_actual"]) - float(earnings_data["eps_estimate"])) / abs(float(earnings_data["eps_estimate"])) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                eps_beat = None
    if rev_beat is None and earnings_data.get("revenue_actual") is not None and earnings_data.get("revenue_estimate"):
        try:
            rev_beat = (float(earnings_data["revenue_actual"]) - float(earnings_data["revenue_estimate"])) / abs(float(earnings_data["revenue_estimate"])) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            rev_beat = None

    if eps_beat is None and rev_beat is None:
        return out
    eps_beat = eps_beat or 0
    rev_beat = rev_beat or 0

    # ── Guidance change — explicit if given, otherwise infer from estimate revisions ──
    guidance = earnings_data.get("guidance_change")  # explicit if available
    if guidance is None and isinstance(estimate_revisions, dict):
        # Shape from zacks_per_ticker: {up_30d, down_30d, up_60d, down_60d, ...}
        # Or aliases: {revisions_up_30d, revisions_down_30d, ...}
        up = (estimate_revisions.get("up_30d") or
              estimate_revisions.get("revisions_up_30d") or
              estimate_revisions.get("upgrades_30d") or 0)
        down = (estimate_revisions.get("down_30d") or
                estimate_revisions.get("revisions_down_30d") or
                estimate_revisions.get("downgrades_30d") or 0)
        try:
            up_n = int(up); down_n = int(down)
            if up_n >= 3 and up_n > down_n * 2:
                guidance = "raised_proxy"  # upgrades 2x+ more than downgrades + at least 3 analysts
            elif down_n >= 3 and down_n > up_n * 2:
                guidance = "lowered_proxy"
            elif up_n + down_n > 0:
                guidance = "inline"
        except (TypeError, ValueError):
            pass

    # ── Tier classification (full 3:1+ scoring) ──
    raised_signal = guidance in ("raised", "raised_proxy")
    lowered_signal = guidance in ("lowered", "lowered_proxy")

    if eps_beat > 5 and rev_beat > 3 and raised_signal:
        proxy_note = " (revisions proxy)" if guidance == "raised_proxy" else ""
        return {
            "points":    8,
            "detected":  True,
            "narrative": f"Beat & raised: EPS +{eps_beat:.1f}% · Rev +{rev_beat:.1f}% · guidance raised{proxy_note} — premium PEAD setup",
            "tier":      "beat_and_raise",
            "data": {"eps_beat_pct": round(eps_beat, 2), "rev_beat_pct": round(rev_beat, 2), "guidance": guidance},
        }
    if eps_beat > 5 and rev_beat > 3:
        return {
            "points":    4,
            "detected":  True,
            "narrative": f"Strong beat: EPS +{eps_beat:.1f}% · Rev +{rev_beat:.1f}% (guidance: {guidance or 'unknown'})",
            "tier":      "beat_no_guidance",
            "data": {"eps_beat_pct": round(eps_beat, 2), "rev_beat_pct": round(rev_beat, 2), "guidance": guidance},
        }
    if eps_beat > 3 and raised_signal:
        proxy_note = " (revisions proxy)" if guidance == "raised_proxy" else ""
        return {
            "points":    5,
            "detected":  True,
            "narrative": f"EPS beat +{eps_beat:.1f}% with raised guidance{proxy_note} — quality PEAD",
            "tier":      "beat_and_raise_lite",
            "data": {"eps_beat_pct": round(eps_beat, 2), "rev_beat_pct": round(rev_beat, 2), "guidance": guidance},
        }
    if (eps_beat > 0 or rev_beat > 0) and lowered_signal:
        proxy_note = " (revisions proxy)" if guidance == "lowered_proxy" else ""
        return {
            "points":    -3,
            "detected":  True,
            "narrative": f"Beat but lowered{proxy_note}: EPS +{eps_beat:.1f}% / Rev +{rev_beat:.1f}% — bearish PEAD",
            "tier":      "beat_lowered_guidance",
            "data": {"eps_beat_pct": round(eps_beat, 2), "rev_beat_pct": round(rev_beat, 2), "guidance": guidance},
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# S-3: CUP WITH HANDLE SCANNER (O'Neil's flagship continuation pattern)
# ─────────────────────────────────────────────────────────────────────────────
def cup_with_handle(df, min_cup_bars: int = 25, max_cup_bars: int = 130) -> dict:
    """
    Detect Cup-with-Handle continuation pattern (William O'Neil, IBD).

    Required structure:
      1. Cup: U-shape — left lip (high), descending to bottom, ascending to right lip near left lip's level
      2. Cup depth: 12-33% from lip to bottom (deeper = riskier)
      3. Cup duration: 7-65 weeks (~25-325 trading days; we cap at 130 bars for swing)
      4. Handle: pullback of 8-12% from right lip, lasting 5-15 bars, with declining volume
      5. Buy point: just above the handle's high (pivot)

    Returns up to +8 points when all 5 conditions hold:
      - Base: +5 (valid U-shape with handle)
      - +2 if handle volume contracted (declining)
      - +1 if right lip is within 5% of left lip (symmetric cup)
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    if df is None or len(df) < min_cup_bars + 10:
        return out

    try:
        # Use a window the size of max possible cup + handle
        window_size = min(max_cup_bars + 15, len(df))
        recent = df.tail(window_size).reset_index(drop=True)
        n = len(recent)

        # Find candidate left-lip: highest high in first third
        left_third = recent.iloc[:n // 3]
        left_lip_idx = int(left_third["High"].idxmax())
        left_lip = float(left_third.loc[left_lip_idx, "High"])

        # Cup bottom: lowest low between left_lip_idx and right_lip search start
        mid_section = recent.iloc[left_lip_idx + 5 : -10]
        if len(mid_section) < 10:
            return out
        cup_bottom_idx = int(mid_section["Low"].idxmin())
        cup_bottom = float(mid_section.loc[cup_bottom_idx, "Low"])
        cup_depth_pct = (left_lip - cup_bottom) / left_lip * 100
        if not (12 <= cup_depth_pct <= 33):
            return out

        # Right lip: highest high after cup bottom, before last 5 bars (handle area)
        right_section = recent.iloc[cup_bottom_idx + 5 : n - 5]
        if len(right_section) < 5:
            return out
        right_lip_idx = int(right_section["High"].idxmax())
        right_lip = float(right_section.loc[right_lip_idx, "High"])
        # Right lip should be within 8% of left lip (cup roughly symmetric)
        right_lip_diff_pct = abs(right_lip - left_lip) / left_lip * 100
        if right_lip_diff_pct > 8:
            return out

        # Cup duration check
        cup_duration = right_lip_idx - left_lip_idx
        if cup_duration < min_cup_bars:
            return out

        # Handle: pullback from right_lip during the last 5-15 bars
        handle_section = recent.iloc[right_lip_idx + 1 :]
        if len(handle_section) < 3:
            return out
        handle_low = float(handle_section["Low"].min())
        handle_pullback_pct = (right_lip - handle_low) / right_lip * 100
        if not (4 <= handle_pullback_pct <= 15):
            return out

        # Volume contraction in handle vs prior 20 bars
        prior_avg_vol = float(recent.iloc[max(0, right_lip_idx - 20):right_lip_idx]["Volume"].mean())
        handle_avg_vol = float(handle_section["Volume"].mean())
        vol_contracted = handle_avg_vol < prior_avg_vol * 0.85

        # Symmetric cup bonus
        symmetric = right_lip_diff_pct < 5

        # Score
        pts = 5
        if vol_contracted: pts += 2
        if symmetric:      pts += 1

        return {
            "points":    pts,
            "detected":  True,
            "narrative": f"Cup-with-Handle: depth {cup_depth_pct:.1f}% over {cup_duration}d · handle {handle_pullback_pct:.1f}% pullback{', vol contracted' if vol_contracted else ''}{', symmetric' if symmetric else ''}",
            "data": {
                "left_lip":         round(left_lip, 2),
                "cup_bottom":       round(cup_bottom, 2),
                "right_lip":        round(right_lip, 2),
                "cup_depth_pct":    round(cup_depth_pct, 2),
                "cup_duration_bars": cup_duration,
                "handle_pullback_pct": round(handle_pullback_pct, 2),
                "buy_pivot":        round(right_lip, 2),
                "vol_contracted":   vol_contracted,
            },
        }
    except Exception:
        return out


# ─────────────────────────────────────────────────────────────────────────────
# S-5: FAILED BREAKDOWN / WYCKOFF SPRING DETECTOR
# ─────────────────────────────────────────────────────────────────────────────
def failed_breakdown_spring(df, lookback: int = 20) -> dict:
    """
    Detect Failed Breakdown / Wyckoff Spring pattern:
      1. Price broke below a recent support (low) on bar N (within lookback)
      2. Price reclaimed above that support within 1-3 sessions
      3. Volume on the reclaim candle ≥ 1.3× average (confirmation)

    Returns up to +9 points when all 3 conditions hold:
      - Base: +5 (broken low + reclaim within 3 sessions)
      - +2 if reclaim volume ≥ 1.3× avg
      - +2 if reclaim closes ABOVE the high of the breakdown bar (full reversal)

    Reference: Wyckoff "Spring" — failure of supply at a support; bullish reversal.
    """
    out = {"points": 0, "detected": False, "narrative": "", "data": {}}
    if df is None or len(df) < lookback + 5:
        return out

    try:
        recent = df.tail(lookback + 3)
        # Find structural support: rolling 20-bar low BEFORE the last 3 bars
        prior = recent.iloc[:-3]
        support_low = float(prior["Low"].min())
        support_idx = prior["Low"].idxmin()

        last3 = recent.tail(3)
        # Did any of the last 3 bars break below support?
        broke_below = (last3["Low"] < support_low).any()
        if not broke_below:
            return out

        # Find the breakdown bar
        breakdown_bar_idx = last3[last3["Low"] < support_low].index[0]
        breakdown_bar = recent.loc[breakdown_bar_idx]

        # Did price reclaim above the broken support?
        bars_after_break = recent.loc[breakdown_bar_idx:].iloc[1:]
        if len(bars_after_break) == 0:
            return out
        reclaimed = (bars_after_break["Close"] > support_low).any()
        if not reclaimed:
            return out

        # Bars-to-reclaim count (must be ≤ 3 for valid spring)
        reclaim_idx = bars_after_break[bars_after_break["Close"] > support_low].index[0]
        bars_to_reclaim = list(bars_after_break.index).index(reclaim_idx) + 1
        if bars_to_reclaim > 3:
            return out

        # Volume on reclaim
        avg_vol = float(prior["Volume"].mean())
        reclaim_vol = float(bars_after_break.loc[reclaim_idx, "Volume"])
        vol_mult = reclaim_vol / avg_vol if avg_vol > 0 else 1.0

        # Did reclaim close ABOVE breakdown bar high?
        breakdown_high = float(breakdown_bar["High"])
        reclaim_close = float(bars_after_break.loc[reclaim_idx, "Close"])
        full_reversal = reclaim_close > breakdown_high

        # Score
        pts = 5
        if vol_mult >= 1.3: pts += 2
        if full_reversal:   pts += 2

        return {
            "points":    pts,
            "detected":  True,
            "narrative": f"Wyckoff Spring: broke ${support_low:.2f} → reclaimed in {bars_to_reclaim}d on {vol_mult:.1f}× vol{'+full reversal' if full_reversal else ''}",
            "data": {
                "support_low":      round(support_low, 2),
                "bars_to_reclaim":  bars_to_reclaim,
                "reclaim_vol_mult": round(vol_mult, 2),
                "full_reversal":    full_reversal,
            },
        }
    except Exception:
        return out


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED HELPER — call all 6 detectors and bundle results
# ─────────────────────────────────────────────────────────────────────────────
def compute_all_tier1_signals(
    *,
    df=None,
    insider: dict | None = None,
    insider_full: dict | None = None,
    rsi: float | None = None,
    above_200sma: bool = False,
    fund_score: float | None = None,
    atr_pct: float | None = None,
    ema21: float | None = None,
    ema50: float | None = None,
    earnings_data: dict | None = None,
    estimate_revisions: dict | None = None,
    config: dict | None = None,
) -> dict:
    """
    Single entry point — runs all 6 Tier 1 detectors and returns combined result.
    Each detector controlled by config flag `tier1_signals.<name>: true`.

    Returns:
      {
        "total_points":    int,    # net additive points to apply to score
        "signals":         dict,   # per-detector results
        "narratives":      [str],  # combined narrative bullets
        "active_count":    int,    # number of detectors that fired
      }
    """
    cfg = (config or {}).get("tier1_signals", {})
    out = {
        "total_points": 0,
        "signals": {},
        "narratives": [],
        "active_count": 0,
    }
    # 2026-05-04 (S-1 unblock): per-detector apply_to_score override.
    # Validated via tier1_backfill.py — only flip True for detectors with proven edge.
    apply_global = cfg.get("apply_to_score", False)
    apply_per = cfg.get("apply_to_score_per_detector", {}) or {}
    def _should_apply(name: str) -> bool:
        return apply_per.get(name, apply_global) if name in apply_per else apply_global

    # Helper: add detector result with proper apply_to_score gating.
    def _record(det_name: str, r: dict):
        out["signals"][det_name] = r
        if r.get("detected"):
            if _should_apply(det_name):
                out["total_points"] += r.get("points", 0)
            out["narratives"].append(r.get("narrative", ""))
            out["active_count"] += 1

    # All detectors use _record() which gates point-contribution by per-detector
    # apply_to_score (validated via tier1_backfill.py).
    if cfg.get("insider_cluster", True):
        _record("insider_cluster", insider_cluster_score(insider, insider_full))
    if cfg.get("nr7_inside_day", True):
        _record("nr7_inside_day", nr7_inside_day(df))
    if cfg.get("volume_dryup", True):
        _record("volume_dryup", volume_dryup_at_support(df, ema21, ema50))
    if cfg.get("obv_divergence", True):
        _record("obv_divergence", obv_divergence(df))
    if cfg.get("mean_reversion", True):
        last5_chg = None
        if df is not None and len(df) >= 6:
            try:
                last5_chg = float((df["close"].iloc[-1] - df["close"].iloc[-6]) / df["close"].iloc[-6])
            except Exception:
                pass
        _record("mean_reversion", mean_reversion_setup(rsi, above_200sma, fund_score, atr_pct, last5_chg))
    if cfg.get("beat_and_raise", True):
        _record("beat_and_raise", beat_and_raise_filter(earnings_data, estimate_revisions=estimate_revisions))
    if cfg.get("failed_breakdown_spring", True):
        _record("failed_breakdown_spring", failed_breakdown_spring(df))
    if cfg.get("cup_with_handle", True):
        _record("cup_with_handle", cup_with_handle(df))

    return out
