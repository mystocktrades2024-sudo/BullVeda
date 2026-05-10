"""
Analysis engine for SwingTrade.
Pre-trade gates, 4-pillar scoring, trade plans, and decision logic.

SCORING_MODE env flag (audit items #2 and #7 — multicollinearity / hardcoded weights):
  "normalized" (default) — equal-pass-through pillar maxes derived as
                 (raw_max / TOTAL_RAW) * 100 (floating-point, not rounded) from
                 RAW_MAXES = {tech:28, cat:30, rs:20, sm:15, fund:30}; TOTAL=123.
                 All pillars get identical 100/123 ≈ 81.3% pass-through. Tech's
                 raw max is reduced from 38 → 28 as a correlation haircut for the
                 known multicollinearity among EMA/MACD/RSI/StochRSI/MFI/OBV
                 (ρ≈0.6-0.8 — same regime counted 3-4x). The 10 reclaimed raw
                 points are redistributed to Catalyst (which carries distinct
                 UOA/PEAD/VCP signals). Sum of pillar maxes = 100.0 (clamped).
  "legacy"     — pre-audit pillar maxes 35/20/20/15/10. Tech pass-through ~92%
                 (raw 38 → pillar 35); Fundamentals pass-through ~33% (raw 30 →
                 pillar 10); over-weights Tech ~2.8x vs Fundamentals. Retained
                 for backward comparison only; opt-in via SCORING_MODE=legacy.

Tier 2 (roadmap, NOT implemented): PCA-collapse correlated momentum sub-indicators
  (EMA8/13/20/50/200, MACD, RSI, StochRSI, MFI are ρ≈0.6-0.8 correlated, same signal
  counted 3-4x). Requires scikit-learn + historical data matrix; fit PCA once, store
  weights, apply in live scoring.

Tier 3 (roadmap, NOT implemented): Regime-conditional weights. Grid search weight
  tuples over walk-forward folds; different weights per regime (bull/bear/chop).
  Currently only one regime-conditional toggle exists (Impulse Catalyst setup type).
  Present weights are GLOBAL (not regime-derived).
"""

from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

log = logging.getLogger("swingtrade.analysis")

# Audit #2/#7 + Swing Optimization: pillar-weight scoring mode.
# "swing_optimized" (DEFAULT) — fundamentals reduced to 8, catalyst boosted to 32.
#     Rationale: 5-15d holds don't benefit from quarterly-metric fundamentals.
#     Catalysts (PEAD/UOA/VCP/squeeze) have the real swing edge.
# "normalized" — equal pass-through (audit #2 fix). Suitable for multi-week holds.
# "legacy" — 35/20/20/15/10 (pre-audit, Tech overweighted). Opt-in for comparison.
SCORING_MODE = os.environ.get("SCORING_MODE", "swing_optimized").lower()
if SCORING_MODE not in ("legacy", "normalized", "swing_optimized"):
    log.warning(f"Unknown SCORING_MODE={SCORING_MODE!r}; falling back to 'swing_optimized'")
    SCORING_MODE = "swing_optimized"

# Pillar raw-maxes. Tech raw max reduced 38 → 28 (correlation haircut — EMA/MACD/RSI/
# StochRSI/MFI/OBV are ρ≈0.6-0.8, effective factor count ~1.5). Reclaimed 10 points
# redistributed to Catalyst (distinct signals: UOA, PEAD, VCP).
RAW_MAXES = {"tech": 28, "cat": 30, "rs": 20, "sm": 15, "fund": 30}
TOTAL_RAW = sum(RAW_MAXES.values())  # 123

# "normalized" mode — equal pass-through floats (sum exactly 100.0)
_PILLAR_TECH_MAX_NORM = (RAW_MAXES["tech"] / TOTAL_RAW) * 100  # 22.764
_PILLAR_CAT_MAX_NORM  = (RAW_MAXES["cat"]  / TOTAL_RAW) * 100  # 24.390
_PILLAR_RS_MAX_NORM   = (RAW_MAXES["rs"]   / TOTAL_RAW) * 100  # 16.260
_PILLAR_SM_MAX_NORM   = (RAW_MAXES["sm"]   / TOTAL_RAW) * 100  # 12.195
_PILLAR_QG_MAX_NORM   = (RAW_MAXES["fund"] / TOTAL_RAW) * 100  # 24.390

# "swing_optimized" mode — fund cut to 8, extra 16 pts to catalyst (swing signals)
_PILLAR_TECH_MAX_SWING = 28.0
_PILLAR_CAT_MAX_SWING  = 32.0
_PILLAR_RS_MAX_SWING   = 20.0
_PILLAR_SM_MAX_SWING   = 12.0
_PILLAR_QG_MAX_SWING   = 8.0
# Sum: 100.0

try:
    from smart_money import score_smc
    _SMC_AVAILABLE = True
except ImportError:
    _SMC_AVAILABLE = False
    def score_smc(df, price, indicators):
        return {"score": 0, "order_blocks": [], "fvg_zones": [], "liquidity_sweeps": [],
                "bos_choch": {}, "ob_entry_zone": None, "ob_stop": None,
                "fvg_target": None, "smc_direction": "neutral", "details": {}}


# ── Star Rating ─────────────────────────────────────────────────────────────

def compute_star_rating(result: dict) -> int:
    """Return 1-5 star quality rating for a trade candidate.

    Combines R:R quality, RS rank, setup type, catalyst tier,
    and decision state into a single intuitive quality score.
    """
    stars = 0.0
    plan = result.get("trade_plan", {})

    # R:R quality (max 1.5 stars)
    rr = plan.get("rr_ratio", 0)
    if rr >= 3.0:
        stars += 1.5
    elif rr >= 2.0:
        stars += 1.0
    elif rr >= 1.5:
        stars += 0.5

    # RS rank (max 1 star)
    rs = result.get("rs_rank", 50)
    if rs >= 90:
        stars += 1.0
    elif rs >= 80:
        stars += 0.75
    elif rs >= 70:
        stars += 0.5

    # Setup quality (max 1 star)
    setup = plan.get("setup_type", "")
    if "VCP" in setup:
        stars += 1.0
    elif "Pullback" in setup or "Continuation" in setup:
        stars += 0.75
    elif "Mean Reversion" in setup or "Pocket Pivot" in setup:
        stars += 0.5
    elif "52wk" in setup:
        stars += 0.25

    # Catalyst (max 0.5 star)
    cat_tier = result.get("catalyst_tier", 3)
    if cat_tier == 1:
        stars += 0.5
    elif cat_tier == 2:
        stars += 0.25

    # Decision state (max 1 star)
    state = result.get("decision_state", {}).get("state", "")
    if state == "CONFIRMED":
        stars += 1.0
    elif state == "AT_ZONE":
        stars += 0.75
    elif state == "APPROACHING":
        stars += 0.5

    return min(5, max(1, round(stars)))


# ── Technical helpers ────────────────────────────────────────────────────────

def _ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def _sma(series, period):
    return series.rolling(window=period).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _macd(close, fast=12, slow=26, signal=9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger_bands(close, period=20, std_dev=2.0):
    sma = _sma(close, period)
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    pct_b = (close - lower) / (upper - lower)
    return upper, lower, sma, pct_b


def _obv(close, volume):
    direction = np.sign(close.diff())
    return (volume * direction).cumsum()


def _volume_profile_full(df, lookback=60, bins=30):
    """Compute full volume profile: POC, Value Area (VAH/VAL), HVN support/resistance, LVN gaps.

    Returns dict with:
      poc          — Point of Control (price level with highest volume)
      vah          — Value Area High (upper bound of 70% volume)
      val          — Value Area Low (lower bound of 70% volume)
      support_vpn  — highest-volume node below price
      resistance_vpn — highest-volume node above price
      lvn_gaps     — list of {low, high} low-volume gaps above price (breakout targets)
    Returns empty dict on failure.
    """
    try:
        recent = df.tail(lookback)
        close  = recent["Close"].squeeze()
        high   = recent["High"].squeeze()
        low    = recent["Low"].squeeze()
        vol    = recent["Volume"].squeeze()
        price  = float(close.iloc[-1])

        lo, hi = float(low.min()), float(high.max())
        if hi <= lo or len(close) < 10:
            return {}

        edges = np.linspace(lo, hi, bins + 1)

        # Vectorized volume distribution — replaces O(bars × bins) Python loop
        # with numpy broadcasting: ~50× faster (1000 tickers: 3min → 4sec)
        bar_lo = low.values.astype(float)
        bar_hi = high.values.astype(float)
        bar_v  = vol.values.astype(float)
        bar_range = bar_hi - bar_lo
        bar_range[bar_range <= 0] = 1e-10  # avoid division by zero

        # edges shape: (bins+1,) → bin boundaries
        # Compute overlap of each bar with each bin using broadcasting
        # bar_lo/bar_hi: (N,) edges: (bins+1,)
        bin_lo = edges[:-1]  # (bins,)
        bin_hi = edges[1:]   # (bins,)

        # overlap[i,b] = max(0, min(bar_hi[i], bin_hi[b]) - max(bar_lo[i], bin_lo[b]))
        overlap = np.maximum(0,
            np.minimum(bar_hi[:, None], bin_hi[None, :]) -
            np.maximum(bar_lo[:, None], bin_lo[None, :])
        )  # (N, bins)

        # weight[i,b] = bar_v[i] * overlap[i,b] / bar_range[i]
        weights = bar_v[:, None] * overlap / bar_range[:, None]
        bin_vol = weights.sum(axis=0)  # (bins,)

        bin_mids = (edges[:-1] + edges[1:]) / 2
        total_vol = bin_vol.sum()

        # POC — bin with the most volume
        poc_idx = int(np.argmax(bin_vol))
        poc = round(float(bin_mids[poc_idx]), 2)

        # Value Area (70% of total volume, expanding outward from POC)
        va_target = total_vol * 0.70
        va_vol = bin_vol[poc_idx]
        va_lo_idx = poc_idx
        va_hi_idx = poc_idx
        while va_vol < va_target and (va_lo_idx > 0 or va_hi_idx < bins - 1):
            expand_lo = bin_vol[va_lo_idx - 1] if va_lo_idx > 0 else 0
            expand_hi = bin_vol[va_hi_idx + 1] if va_hi_idx < bins - 1 else 0
            if expand_lo >= expand_hi and va_lo_idx > 0:
                va_lo_idx -= 1
                va_vol += expand_lo
            elif va_hi_idx < bins - 1:
                va_hi_idx += 1
                va_vol += expand_hi
            else:
                va_lo_idx -= 1
                va_vol += expand_lo
        val_price = round(float(edges[va_lo_idx]), 2)
        vah_price = round(float(edges[va_hi_idx + 1]), 2)

        # HVN support/resistance (highest-volume nodes below/above price)
        below_mask = bin_mids < price
        above_mask = bin_mids > price
        support_vpn = resistance_vpn = None
        if below_mask.any():
            idx = int(np.argmax(bin_vol[below_mask]))
            below_indices = np.where(below_mask)[0]
            support_vpn = round(float(bin_mids[below_indices[idx]]), 2)
        if above_mask.any():
            idx = int(np.argmax(bin_vol[above_mask]))
            above_indices = np.where(above_mask)[0]
            resistance_vpn = round(float(bin_mids[above_indices[idx]]), 2)

        # LVN gaps — low-volume zones above price (breakout targets)
        # A bin is "low volume" if it's below 20% of the average bin volume
        avg_bin_vol = total_vol / bins if bins > 0 else 1
        lvn_threshold = avg_bin_vol * 0.20
        lvn_gaps = []
        in_gap = False
        gap_start = 0
        for b in range(bins):
            if bin_mids[b] <= price:
                continue
            if bin_vol[b] < lvn_threshold:
                if not in_gap:
                    in_gap = True
                    gap_start = float(edges[b])
            else:
                if in_gap:
                    lvn_gaps.append({"low": round(gap_start, 2), "high": round(float(edges[b]), 2)})
                    in_gap = False
        if in_gap:
            lvn_gaps.append({"low": round(gap_start, 2), "high": round(float(edges[bins]), 2)})

        return {
            "poc": poc,
            "vah": vah_price,
            "val": val_price,
            "support_vpn": support_vpn,
            "resistance_vpn": resistance_vpn,
            "lvn_gaps": lvn_gaps[:3],
            "price": round(price, 2),
        }

        return support_vpn, resistance_vpn
    except Exception:
        return None, None


def _support_resistance(df, lookback=60):
    """Compute support/resistance from pivot points, swing highs/lows, and volume profile nodes."""
    recent = df.tail(lookback)
    h, l, c = float(recent["High"].max()), float(recent["Low"].min()), float(df["Close"].iloc[-1])

    pivot = (h + l + c) / 3
    r1 = 2 * pivot - l
    r2 = pivot + (h - l)
    s1 = 2 * pivot - h
    s2 = pivot - (h - l)

    # Volume profile — full: POC, VAH/VAL, HVN support/resistance, LVN gaps
    _vp = _volume_profile_full(df, lookback, bins=30)
    vpn_sup = _vp.get("support_vpn")
    vpn_res = _vp.get("resistance_vpn")

    # Candidate levels
    support_candidates = sorted([s for s in [s1, s2, l, vpn_sup] if s is not None and s < c], reverse=True)
    resist_candidates  = sorted([r for r in [r1, r2, h, vpn_res]  if r is not None and r > c])

    support = support_candidates[0] if support_candidates else s1

    # When price is AT the 60-day high (breakout), skip h as resistance — use r1 (next pivot)
    # Otherwise h ≈ price → R:R ≈ 0, which is wrong for breakout setups
    at_breakout = (h - c) / c < 0.005  # within 0.5% of high = breakout
    if at_breakout:
        resist_above = sorted([r for r in [r1, r2] if r > c])
        resist = resist_above[0] if resist_above else r1
    else:
        resist = resist_candidates[0] if resist_candidates else r1

    # Use ATR-based effective stop for R:R (consistent with trade plan, not raw 60d low)
    # Rough ATR: 14-period average of daily range
    try:
        recent_df = df.tail(lookback)
        atr_est = float((recent_df["High"].squeeze() - recent_df["Low"].squeeze()).tail(14).mean())
    except Exception:
        atr_est = (h - l) / 20
    atr_stop = c - atr_est * 1.5
    effective_support = max(support, atr_stop)  # tighter of: raw support or ATR stop

    rr_ratio = (resist - c) / max(c - effective_support, 0.01) if effective_support < c else 0

    return {
        "support": round(support, 2),
        "resistance": round(resist, 2),
        "pivot": round(pivot, 2),
        "s1": round(s1, 2), "s2": round(s2, 2),
        "r1": round(r1, 2), "r2": round(r2, 2),
        "swing_high": round(h, 2),
        "swing_low": round(l, 2),
        "vpn_support": round(vpn_sup, 2) if vpn_sup else None,
        "vpn_resistance": round(vpn_res, 2) if vpn_res else None,
        "rr_ratio": round(rr_ratio, 2)
    }


def _ttm_squeeze(df, bb_len=20, kc_len=20, kc_mult=1.5):
    """TTM Squeeze: Bollinger Bands inside Keltner Channels + momentum direction."""
    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high  = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low   = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    # Bollinger Bands
    bb_sma = _sma(close, bb_len)
    bb_std = close.rolling(bb_len).std()
    bb_upper = bb_sma + 2 * bb_std
    bb_lower = bb_sma - 2 * bb_std

    # Keltner Channels
    kc_sma = _sma(close, kc_len)
    atr = _atr(high, low, close, kc_len)
    kc_upper = kc_sma + kc_mult * atr
    kc_lower = kc_sma - kc_mult * atr

    squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    in_squeeze = bool(squeeze.iloc[-1]) if not squeeze.empty else False
    if in_squeeze:
        bars_in = 0
        for v in reversed(squeeze.values):
            if v:
                bars_in += 1
            else:
                break
    else:
        bars_in = 0

    # squeeze_fired: was compressed 1-5 bars ago and just released
    squeeze_fired = False
    squeeze_direction = "neutral"  # Phase 4D: momentum direction confirmation
    if not in_squeeze and len(squeeze) >= 3:
        recent = squeeze.iloc[-6:-1] if len(squeeze) >= 6 else squeeze.iloc[:-1]
        if recent.any():
            # Phase 4D: Only confirm squeeze_fired if momentum is expanding in the right direction
            # Use MACD histogram as momentum proxy
            macd_fast = close.ewm(span=12, adjust=False).mean()
            macd_slow = close.ewm(span=26, adjust=False).mean()
            macd_hist = macd_fast - macd_slow
            if len(macd_hist) >= 2:
                _h_now  = float(macd_hist.iloc[-1])
                _h_prev = float(macd_hist.iloc[-2])
                if _h_now > 0 and _h_now > _h_prev:
                    squeeze_fired = True
                    squeeze_direction = "bullish"
                elif _h_now < 0 and _h_now < _h_prev:
                    squeeze_fired = True
                    squeeze_direction = "bearish"
                # If momentum is not expanding, squeeze released but NOT confirmed

    return {"squeeze_on": in_squeeze, "bars_in_squeeze": bars_in,
            "squeeze_fired": squeeze_fired, "squeeze_direction": squeeze_direction}


def _relative_strength_vs_spy(ticker_close, spy_close, period=63):
    """Relative strength vs SPY over ~3 months + RS momentum (improving vs deteriorating)."""
    if len(ticker_close) < period or len(spy_close) < period:
        return {"rs_ratio": 1.0, "rs_rank": 50, "outperforming": False,
                "rs_momentum": "unknown", "rs_63d_pct": 0.0}

    t_ret = (ticker_close.iloc[-1] / ticker_close.iloc[-period]) - 1
    s_ret = (spy_close.iloc[-1] / spy_close.iloc[-period]) - 1

    rs_ratio = (1 + t_ret) / (1 + s_ret) if (1 + s_ret) != 0 else 1.0
    if np.isnan(rs_ratio):
        rs_ratio = 1.0
    rs_rank = min(100, max(0, int((rs_ratio - 0.8) / 0.4 * 100)))
    outperforming = rs_ratio > 1.0

    # Phase 4E: RS momentum — is relative strength improving or deteriorating?
    # Compare 21d RS to 63d RS. If short-term RS > long-term RS, momentum is improving.
    rs_momentum = "stable"
    if len(ticker_close) >= period and len(spy_close) >= period:
        _short_period = min(21, period // 3)
        if len(ticker_close) >= _short_period and len(spy_close) >= _short_period:
            t_ret_short = (ticker_close.iloc[-1] / ticker_close.iloc[-_short_period]) - 1
            s_ret_short = (spy_close.iloc[-1] / spy_close.iloc[-_short_period]) - 1
            rs_short = (1 + t_ret_short) / (1 + s_ret_short) if (1 + s_ret_short) != 0 else 1.0
            if np.isnan(rs_short):
                rs_short = 1.0
            if rs_short > rs_ratio * 1.02:
                rs_momentum = "improving"
            elif rs_short < rs_ratio * 0.98:
                rs_momentum = "deteriorating"

    return {
        "rs_ratio": round(rs_ratio, 3),
        "rs_rank": rs_rank,
        "outperforming": outperforming,
        "rs_momentum": rs_momentum,
        "rs_63d_pct": round(t_ret * 100, 1),
    }


# ── ADX — Trend Strength ─────────────────────────────────────────────────────

def _adx(high, low, close, period: int = 14) -> dict:
    """
    Average Directional Index — measures trend *strength* (not direction).
    ADX > 25 = trending market; ADX > 35 = strong trend; < 20 = choppy/ranging.
    """
    h = high.values if hasattr(high, "values") else np.array(high)
    l = low.values  if hasattr(low,  "values") else np.array(low)
    c = close.values if hasattr(close, "values") else np.array(close)
    n = len(c)

    plus_dm  = np.zeros(n)
    minus_dm = np.zeros(n)
    tr_arr   = np.zeros(n)

    for i in range(1, n):
        h_move = h[i] - h[i - 1]
        l_move = l[i - 1] - l[i]
        if h_move > l_move and h_move > 0:
            plus_dm[i] = h_move
        if l_move > h_move and l_move > 0:
            minus_dm[i] = l_move
        tr_arr[i] = max(h[i] - l[i],
                        abs(h[i] - c[i - 1]),
                        abs(l[i] - c[i - 1]))

    tr_s    = pd.Series(tr_arr).ewm(span=period, adjust=False).mean()
    plus_s  = pd.Series(plus_dm).ewm(span=period, adjust=False).mean()
    minus_s = pd.Series(minus_dm).ewm(span=period, adjust=False).mean()

    plus_di  = 100 * plus_s  / tr_s.replace(0, np.nan)
    minus_di = 100 * minus_s / tr_s.replace(0, np.nan)
    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=period, adjust=False).mean()

    def _safe(s):
        v = float(s.iloc[-1]) if len(s) else np.nan
        return round(v, 1) if not np.isnan(v) else 20.0

    adx_val = _safe(adx)
    pdi_val = _safe(plus_di)
    mdi_val = _safe(minus_di)

    return {
        "adx":          adx_val,
        "plus_di":      pdi_val,
        "minus_di":     mdi_val,
        "trending":     adx_val > 25,
        "strong_trend": adx_val > 35,
    }


# ── Stochastic RSI ────────────────────────────────────────────────────────────

def _stoch_rsi(close, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> dict:
    """
    Stochastic RSI — more sensitive than plain RSI for swing entry timing.
    K < 20 = oversold (entry zone); K > 80 = overbought.
    """
    rsi = _rsi(close, period)
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    stoch = 100 * (rsi - rsi_min) / (rsi_max - rsi_min + 1e-9)
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()

    def _sv(s):
        v = float(s.iloc[-1]) if len(s) else np.nan
        return round(v, 1) if not np.isnan(v) else 50.0

    k_val = _sv(k)
    d_val = _sv(d)
    k_prev = float(k.iloc[-2]) if len(k) > 1 else k_val
    d_prev = float(d.iloc[-2]) if len(d) > 1 else d_val

    return {
        "k":               k_val,
        "d":               d_val,
        "oversold":        k_val < 20,
        "overbought":      k_val > 80,
        "k_above_d":       k_val > d_val,
        "bullish_cross":   k_val > d_val and k_prev <= d_prev,
        "bearish_cross":   k_val < d_val and k_prev >= d_prev,
    }


# ── Money Flow Index ──────────────────────────────────────────────────────────

def _mfi(high, low, close, volume, period: int = 14) -> dict:
    """
    Money Flow Index — volume-weighted RSI.
    Identifies buying/selling pressure including institutional flows.
    """
    tp  = (high + low + close) / 3
    rmf = tp * volume
    pos = rmf.where(tp > tp.shift(1), 0.0)
    neg = rmf.where(tp <= tp.shift(1), 0.0)
    mfr = pos.rolling(period).sum() / neg.rolling(period).sum().replace(0, 1e-9)
    mfi = 100 - 100 / (1 + mfr)

    val = float(mfi.iloc[-1]) if len(mfi) and not np.isnan(float(mfi.iloc[-1])) else 50.0
    return {
        "mfi":        round(val, 1),
        "oversold":   val < 20,
        "overbought": val > 80,
        "bullish":    val > 50,
        "divergence_possible": val < 40 and float(close.iloc[-1]) > float(close.iloc[-5]) if len(close) >= 5 else False,
    }


# ── Chaikin Money Flow ────────────────────────────────────────────────────────

def _cmf(high, low, close, volume, period: int = 20) -> dict:
    """
    Chaikin Money Flow — measures accumulation vs distribution pressure.
    CMF > +0.05 = accumulation; CMF < -0.05 = distribution.
    """
    clv = ((close - low) - (high - close)) / (high - low + 1e-9)
    mfv = clv * volume
    cmf = mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, 1e-9)

    val = float(cmf.iloc[-1]) if len(cmf) and not np.isnan(float(cmf.iloc[-1])) else 0.0
    return {
        "cmf":          round(val, 3),
        "accumulating": val > 0.05,
        "distributing": val < -0.05,
    }


# ── Parabolic SAR ─────────────────────────────────────────────────────────────

def _parabolic_sar(high, low, close, af_start: float = 0.02, af_max: float = 0.20) -> dict:
    """
    Parabolic SAR — dynamic trailing stop. Direction flip signals trend reversal.
    """
    h = high.values  if hasattr(high,  "values") else np.array(high)
    l = low.values   if hasattr(low,   "values") else np.array(low)
    c = close.values if hasattr(close, "values") else np.array(close)
    n = len(c)
    if n < 5:
        return {"bullish": True, "sar": round(float(c[-1]) * 0.97, 2), "flipped": False}

    sar = np.zeros(n)
    ep  = np.zeros(n)
    af  = af_start
    bull = c[1] > c[0]

    sar[0] = l[0] if bull else h[0]
    ep[0]  = h[0] if bull else l[0]
    prev_bull = bull

    for i in range(1, n):
        if bull:
            sar[i] = sar[i - 1] + af * (ep[i - 1] - sar[i - 1])
            sar[i] = min(sar[i], l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar[i]:
                prev_bull = bull; bull = False
                sar[i] = ep[i - 1]; ep[i] = l[i]; af = af_start
            else:
                if h[i] > ep[i - 1]:
                    ep[i] = h[i]; af = min(af + af_start, af_max)
                else:
                    ep[i] = ep[i - 1]
        else:
            sar[i] = sar[i - 1] + af * (ep[i - 1] - sar[i - 1])
            sar[i] = max(sar[i], h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar[i]:
                prev_bull = bull; bull = True
                sar[i] = ep[i - 1]; ep[i] = h[i]; af = af_start
            else:
                if l[i] < ep[i - 1]:
                    ep[i] = l[i]; af = min(af + af_start, af_max)
                else:
                    ep[i] = ep[i - 1]

    # Check for recent flip (last 3 bars)
    flipped = bool(bull) != bool(prev_bull)

    return {
        "bullish": bool(bull),
        "sar":     round(float(sar[-1]), 2),
        "flipped": flipped,
    }


# ── 52-Week Position ──────────────────────────────────────────────────────────

def _52week_position(df: pd.DataFrame) -> dict:
    """
    Measure proximity to 52-week high and low — IBD-style breakout zone detection.
    Near 52w high on strong volume = highest-probability swing entry (Stage 2 breakout).
    """
    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high  = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low   = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    n = min(252, len(df))
    sub_high = high.iloc[-n:]
    sub_low  = low.iloc[-n:]

    high_52  = float(sub_high.max())
    low_52   = float(sub_low.min())
    price    = float(close.iloc[-1])

    pct_from_high = (high_52 - price) / high_52 if high_52 > 0 else 1.0
    pct_from_low  = (price - low_52)  / price   if price  > 0 else 1.0

    return {
        "high_52w":      round(high_52, 2),
        "low_52w":       round(low_52,  2),
        "pct_from_high": round(pct_from_high * 100, 1),
        "pct_from_low":  round(pct_from_low  * 100, 1),
        "near_52w_high": pct_from_high < 0.05,   # within 5% — momentum zone
        "at_breakout":   pct_from_high < 0.02,   # within 2% — breakout imminent
        "near_52w_low":  pct_from_low  < 0.10,   # within 10% below — danger zone
        "stage2":        pct_from_high < 0.05 and pct_from_low > 0.30,  # classic Stage 2
    }


# ── Weekly EMA Alignment ──────────────────────────────────────────────────────

def _weekly_ema_alignment(weekly_df: "pd.DataFrame | None") -> dict:
    """
    Check if the weekly chart EMA stack is aligned with the daily signal.
    Bull-aligned: price > EMA8w > EMA21w — confirms daily uptrend is durable.
    Bear-aligned: price < EMA8w < EMA21w — daily bounce is counter-trend.
    """
    na = {"aligned": False, "bullish": None, "bearish": None,
          "ema8w": None, "ema21w": None, "price_w": None}
    if weekly_df is None or (hasattr(weekly_df, "empty") and weekly_df.empty):
        return na
    try:
        wclose = (weekly_df["Close"].squeeze()
                  if isinstance(weekly_df["Close"], pd.DataFrame)
                  else weekly_df["Close"])
        if len(wclose) < 21:
            return na
        ema8w  = _ema(wclose, 8)
        ema21w = _ema(wclose, 21)
        price_w = float(wclose.iloc[-1])
        e8 = float(ema8w.iloc[-1])  if hasattr(ema8w,  "iloc") else ema8w  or price_w
        e21= float(ema21w.iloc[-1]) if hasattr(ema21w, "iloc") else ema21w or price_w
        bull = price_w > e8 > e21
        bear = price_w < e8 < e21
        return {
            "aligned":  bull or bear,
            "bullish":  bool(bull),
            "bearish":  bool(bear),
            "ema8w":    round(e8,  2),
            "ema21w":   round(e21, 2),
            "price_w":  round(price_w, 2),
        }
    except Exception:
        return na


# ── VWAP + Anchored VWAP ─────────────────────────────────────────────────────

def _vwap(df, window: int = 20) -> dict:
    """
    Rolling VWAP (20-day) + Anchored VWAP from the most recent swing low.
    Returns vwap_20d, avwap_swing_low, above_vwap, above_avwap.
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"],  pd.DataFrame) else df["Close"]
    high   = df["High"].squeeze()  if isinstance(df["High"],   pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],    pd.DataFrame) else df["Low"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    typical = (high + low + close) / 3
    tpv = typical * volume

    vwap_roll = tpv.rolling(window).sum() / volume.rolling(window).sum()
    vwap_val  = float(vwap_roll.iloc[-1]) if not vwap_roll.empty and not np.isnan(vwap_roll.iloc[-1]) else None

    # Anchor to recent swing low (lowest close in last 60 bars, excluding today)
    lookback = min(60, len(close) - 1)
    swing_low_offset = int(close.iloc[-lookback:-1].argmin()) if lookback > 1 else 0
    anchor_start = len(close) - lookback + swing_low_offset
    anchor_tpv = tpv.iloc[anchor_start:]
    anchor_vol = volume.iloc[anchor_start:]
    cum_vol = anchor_vol.cumsum()
    avwap_series = anchor_tpv.cumsum() / cum_vol.replace(0, np.nan)
    avwap_val = float(avwap_series.iloc[-1]) if not avwap_series.empty and not np.isnan(avwap_series.iloc[-1]) else None

    price = float(close.iloc[-1])
    return {
        "vwap_20d":        round(vwap_val, 2) if vwap_val else None,
        "avwap_swing_low": round(avwap_val, 2) if avwap_val else None,
        "above_vwap":      bool(price > vwap_val) if vwap_val else None,
        "above_avwap":     bool(price > avwap_val) if avwap_val else None,
    }


# ── Chart Pattern Detection ───────────────────────────────────────────────────

def _detect_patterns(df) -> dict:
    """
    Algorithmic detection of 6 chart patterns.
    Returns: detected (list), primary (str), confidence (0-4), details (dict).

    Patterns: Bull Flag, Bear Flag, Ascending Triangle, Descending Triangle,
              Cup & Handle, Head & Shoulders.
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high   = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    n = len(close)
    if n < 40:
        return {"detected": [], "primary": None, "confidence": 0, "details": {}}

    price = float(close.iloc[-1])
    avg_p = float(close.mean())
    detected, details = [], {}
    primary_pattern, confidence = None, 0

    def _slope(series, bars):
        y = series.iloc[-bars:].values.astype(float)
        if len(y) < bars:
            return 0.0
        x = np.arange(bars)
        return float(np.polyfit(x, y, 1)[0])

    def _local_peaks(series, window=5):
        peaks = []
        for i in range(window, len(series) - window):
            if float(series.iloc[i]) == float(series.iloc[i - window: i + window + 1].max()):
                peaks.append((i, float(series.iloc[i])))
        return peaks

    # ── Bull Flag ─────────────────────────────────────────────────────────────
    pole_slope = _slope(close.iloc[:-20], 20) if n >= 40 else 0
    flag_ret   = (float(close.iloc[-1]) - float(close.iloc[-20])) / max(float(close.iloc[-20]), 1e-9) if n >= 20 else 0
    flag_slope = _slope(close, 20)
    if pole_slope > 0.002 * avg_p and -0.10 <= flag_ret <= 0.02 and abs(flag_slope) < abs(pole_slope) * 0.5:
        detected.append("Bull Flag")
        details["bull_flag"] = f"Pole +{pole_slope:.3f}/bar, flag {flag_ret:.1%} pullback"
        if confidence < 2: primary_pattern, confidence = "Bull Flag", 2

    # ── Bear Flag ─────────────────────────────────────────────────────────────
    elif pole_slope < -0.002 * avg_p and -0.02 <= flag_ret <= 0.08 and abs(flag_slope) < abs(pole_slope) * 0.5:
        detected.append("Bear Flag")
        details["bear_flag"] = f"Pole {pole_slope:.3f}/bar, flag {flag_ret:.1%} bounce"
        if confidence < 2: primary_pattern, confidence = "Bear Flag", 2

    # ── Ascending Triangle ────────────────────────────────────────────────────
    high_slope = _slope(high, 30) if n >= 30 else 0
    low_slope  = _slope(low, 30)  if n >= 30 else 0
    tol = 0.0015 * avg_p
    if abs(high_slope) < tol and low_slope > tol * 0.5:
        detected.append("Ascending Triangle")
        details["ascending_triangle"] = f"Flat resist (slope {high_slope:.4f}), rising support (slope {low_slope:.4f})"
        if confidence < 3: primary_pattern, confidence = "Ascending Triangle", 3

    # ── Descending Triangle ───────────────────────────────────────────────────
    elif abs(low_slope) < tol and high_slope < -tol * 0.5:
        detected.append("Descending Triangle")
        details["descending_triangle"] = f"Flat support (slope {low_slope:.4f}), descending resistance"
        if confidence < 2: primary_pattern, confidence = "Descending Triangle", 2

    # ── Head & Shoulders ─────────────────────────────────────────────────────
    peaks = _local_peaks(high, window=5)
    if len(peaks) >= 3:
        ls_i, ls_h = peaks[-3]
        hd_i, hd_h = peaks[-2]
        rs_i, rs_h = peaks[-1]
        if (hd_h > ls_h * 1.02 and hd_h > rs_h * 1.02
                and abs(ls_h - rs_h) / max(hd_h, 1e-9) < 0.08 and price < hd_h * 0.97):
            detected.append("Head & Shoulders")
            details["head_shoulders"] = f"LS={ls_h:.2f}, Head={hd_h:.2f}, RS={rs_h:.2f}"
            if confidence < 3: primary_pattern, confidence = "Head & Shoulders", 3

    # ── Cup & Handle ─────────────────────────────────────────────────────────
    if n >= 60:
        cup = close.iloc[-60:-10]
        handle = close.iloc[-10:]
        cup_high = float(cup.max())
        cup_low  = float(cup.min())
        cup_low_i = int(cup.argmin())
        mid_s, mid_e = len(cup) // 3, 2 * len(cup) // 3
        cup_depth = (cup_high - cup_low) / max(cup_high, 1e-9)
        handle_range = (float(handle.max()) - float(handle.min())) / max(float(handle.max()), 1e-9)
        handle_level = float(handle.mean())
        right_rim    = float(cup.iloc[-5:].mean())
        if (mid_s <= cup_low_i <= mid_e and 0.10 <= cup_depth <= 0.45
                and handle_range < cup_depth * 0.65 and handle_level > right_rim * 0.95):
            detected.append("Cup & Handle")
            details["cup_handle"] = f"Cup depth {cup_depth:.1%}, handle {handle_range:.1%}"
            if confidence < 4: primary_pattern, confidence = "Cup & Handle", 4

    return {"detected": detected, "primary": primary_pattern,
            "confidence": confidence, "details": details}


# ── VCP — Volatility Contraction Pattern (Minervini) ─────────────────────────

def _detect_vcp(df) -> dict:
    """
    Mark Minervini's Volatility Contraction Pattern.
    Looks for 2+ sequential bases each progressively narrower.
    Volume should also contract (dry up) during each base.
    High-probability breakout setup when detected.

    Returns vcp=True for classic VCP (2+ contractions with volume dry-up),
    or near_vcp=True for stocks showing 2 tightening ranges even without
    perfect volume contraction (still actionable, lower confidence).
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high   = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    na = {"vcp": False, "near_vcp": False, "contractions": 0, "tightness_pct": None,
          "pivot": None, "vol_dry_up": False}
    if len(close) < 60:
        return na

    price = float(close.iloc[-1])

    # Find swing highs/lows in last 60 bars using 8-bar windows
    def _swings(series, window=8):
        peaks, troughs = [], []
        for i in range(window, len(series) - window):
            sl = float(series.iloc[i])
            if sl == float(series.iloc[i - window: i + window + 1].max()):
                peaks.append((i, sl))
            if sl == float(series.iloc[i - window: i + window + 1].min()):
                troughs.append((i, sl))
        return peaks, troughs

    # Also try a smaller 5-bar window to catch tighter patterns
    def _find_bases(sub_h, sub_l, sub_v, window):
        peaks, _ = _swings(sub_h, window=window)
        _, troughs = _swings(sub_l, window=window)
        if len(peaks) < 2 or len(troughs) < 2:
            return []
        all_swings = [(i, p, "peak") for i, p in peaks] + [(i, p, "trough") for i, p in troughs]
        all_swings.sort(key=lambda x: x[0])
        bases = []
        for j in range(len(all_swings) - 1):
            _, p1, t1 = all_swings[j]
            _, p2, t2 = all_swings[j + 1]
            if t1 == t2:
                continue
            hi = p1 if t1 == "peak" else p2
            lo = p2 if t2 == "trough" else p1
            rng = hi - lo
            start_bar = min(all_swings[j][0], all_swings[j + 1][0])
            end_bar   = max(all_swings[j][0], all_swings[j + 1][0])
            avg_vol   = float(sub_v.iloc[start_bar:end_bar + 1].mean()) if end_bar > start_bar else 0
            if rng > 0:
                bases.append({"range": rng, "high": hi, "low": lo, "avg_vol": avg_vol})
        return bases

    sub_h = high.iloc[-60:]
    sub_l = low.iloc[-60:]
    sub_v = volume.iloc[-60:]

    # Try standard 8-bar window first, then 5-bar for tighter patterns
    bases = _find_bases(sub_h, sub_l, sub_v, window=8)
    if len(bases) < 2:
        bases = _find_bases(sub_h, sub_l, sub_v, window=5)
    if len(bases) < 2:
        return na

    # Check for contracting ranges AND volume
    contractions = 0
    range_only_contractions = 0  # ranges contract but volume may not
    for i in range(len(bases) - 1):
        curr, prev = bases[i], bases[i + 1]
        range_ratio = curr["range"] / prev["range"] if prev["range"] > 0 else 1
        vol_ratio   = curr["avg_vol"] / prev["avg_vol"] if prev["avg_vol"] > 0 else 1
        # Full contraction: range narrows AND volume dries up
        if 0.30 <= range_ratio <= 0.90 and vol_ratio < 1.05:
            contractions += 1
        # Range-only contraction (relaxed): range narrows regardless of volume
        if 0.30 <= range_ratio <= 0.90:
            range_only_contractions += 1

    # Volume dry-up detection: last base volume < 60% of 20-bar average
    vol_20_avg = float(sub_v.iloc[-20:].mean()) if len(sub_v) >= 20 else float(sub_v.mean())
    last_base_vol = bases[-1]["avg_vol"] if bases else 0
    vol_dry_up = last_base_vol < vol_20_avg * 0.60 if vol_20_avg > 0 else False

    # Pivot breakout price = top of the most recent (tightest) base
    pivot = round(bases[-1]["high"] * 1.005, 2)
    tightness = round(bases[-1]["range"] / price * 100, 1)

    # Classic VCP: 2+ full contractions (range + volume)
    if contractions >= 2:
        return {
            "vcp":           True,
            "near_vcp":      False,
            "contractions":  contractions,
            "tightness_pct": tightness,
            "pivot":         pivot,
            "vol_dry_up":    vol_dry_up,
        }

    # Near-VCP: 2+ range contractions even without perfect volume contraction
    # Still actionable — stocks tightening into a range with decreasing volatility
    if range_only_contractions >= 2 and tightness <= 8.0:
        return {
            "vcp":           False,
            "near_vcp":      True,
            "contractions":  range_only_contractions,
            "tightness_pct": tightness,
            "pivot":         pivot,
            "vol_dry_up":    vol_dry_up,
        }

    return na


# ── Power Trend (IBD) ────────────────────────────────────────────────────────

def _power_trend(df) -> dict:
    """
    IBD Power Trend: 10+ consecutive sessions where:
    - Each daily low is above the prior day's low
    - Each daily low is above the 21-day EMA
    - Phase 4B: EMA21 must be rising (not falling/flat)
    - Phase 4B: Price must be above EMA50 (uptrend context)
    Indicates market in systematic institutional accumulation.
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    if len(close) < 50:
        return {"power_trend": False, "power_days": 0}

    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    price = float(close.iloc[-1])

    # Phase 4B: EMA21 must be rising (current > 5 bars ago)
    if len(ema21) >= 6:
        ema21_rising = float(ema21.iloc[-1]) > float(ema21.iloc[-6])
    else:
        ema21_rising = False

    # Phase 4B: price must be above EMA50 (uptrend context)
    if price <= float(ema50.iloc[-1]):
        return {"power_trend": False, "power_days": 0}

    if not ema21_rising:
        return {"power_trend": False, "power_days": 0}

    count = 0
    for i in range(1, min(20, len(low))):
        lv  = float(low.iloc[-i])
        prv = float(low.iloc[-i - 1])
        e21 = float(ema21.iloc[-i])
        if lv > prv and lv > e21:
            count += 1
        else:
            break  # streak broken

    return {
        "power_trend": count >= 10,
        "power_days":  count,
    }


# ── Pocket Pivot (Gil Morales) ────────────────────────────────────────────────

def _pocket_pivot(df) -> dict:
    """
    Gil Morales' Pocket Pivot: today's up-day volume exceeds the highest
    down-day volume in the prior 10 sessions.
    Phase 4A: Require price near EMA21/EMA50 (accumulation base context) and
    at least 2 down days in window. No hardcoded fallbacks.
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    if len(df) < 12:
        return {"pocket_pivot": False, "pp_vol_ratio": 0.0}

    today_up  = float(close.iloc[-1]) > float(close.iloc[-2])
    today_vol = float(volume.iloc[-1])
    price     = float(close.iloc[-1])

    if not today_up:
        return {"pocket_pivot": False, "pp_vol_ratio": 0.0}

    # Phase 4A: require price near EMA21 or EMA50 (within 5%) — accumulation base context
    ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1]) if len(close) >= 50 else ema21
    near_ema = (abs(price - ema21) / price < 0.05) or (abs(price - ema50) / price < 0.05)
    if not near_ema:
        return {"pocket_pivot": False, "pp_vol_ratio": 0.0}

    # Max down-day volume in prior 10 sessions
    prior = df.iloc[-12:-1]
    prior_close = prior["Close"].squeeze()
    if isinstance(prior_close, pd.DataFrame):
        prior_close = prior_close.iloc[:, 0]
    down_mask = prior_close < prior_close.shift(1)
    down_vols = prior["Volume"].squeeze()[down_mask]

    # Phase 4A: require at least 2 down days (no false signal from no-down streaks)
    if down_vols.empty or len(down_vols) < 2:
        return {"pocket_pivot": False, "pp_vol_ratio": 0.0}

    max_down_vol = float(down_vols.max())
    ratio = round(today_vol / max_down_vol, 2) if max_down_vol > 0 else 0.0

    return {
        "pocket_pivot":  today_vol > max_down_vol,
        "pp_vol_ratio":  ratio,
    }


# ── Elliott Wave classification (K5, 2026-05-09) ─────────────────────────────

def classify_elliott_wave(df, lookback: int = 90,
                           fib_extensions: list[float] | None = None,
                           min_swing_pct: float = 0.10) -> dict:
    """K5: Identify Elliott Wave context for target derivation.

    Vinod feedback (HPE 2026-05-09): "we are at a Wave3 (Impulse): T1=50.37, T2=55.75"
    Maps to Fib extensions of the most recent (swing_low → swing_high) impulse:
      T1 = swing_low + 1.272 × (swing_high - swing_low)
      T2 = swing_low + 1.618 × (swing_high - swing_low)

    Heuristic Wave-3 detection (refined 2026-05-09 to use RECENT swings):
      1. Use last `lookback` bars (default 90 = ~4 months) — Elliott Wave
         analysis is about the CURRENT impulse, not all-time history.
      2. Find lowest low → highest high AFTER it (Wave 1 candidate).
      3. If swing range < min_swing_pct, expand lookback once to 180.
      4. If current price has BROKEN above swing_high → Wave 3 Impulse.

    Returns dict with wave/type/swing_low/swing_high/t1_extension/t2_extension/confidence.
    """
    fib_extensions = fib_extensions or [1.272, 1.618]
    out = {
        "wave": None, "type": "incomplete",
        "swing_low": None, "swing_high": None, "swing_range": None,
        "t1_extension": None, "t2_extension": None,
        "confidence": "low",
    }
    if df is None or len(df) < 30:
        return out

    def _try_lookback(window: int) -> dict | None:
        try:
            sub = df.tail(window)
            lows = sub["Low"].squeeze() if hasattr(sub["Low"], "squeeze") else sub["Low"]
            highs = sub["High"].squeeze() if hasattr(sub["High"], "squeeze") else sub["High"]
            closes = sub["Close"].squeeze() if hasattr(sub["Close"], "squeeze") else sub["Close"]

            idx_low = int(lows.values.argmin())
            swing_low = float(lows.iloc[idx_low])

            if idx_low >= len(highs) - 5:
                return None
            post = highs.iloc[idx_low + 1:]
            idx_high_in_post = int(post.values.argmax())
            swing_high = float(post.iloc[idx_high_in_post])

            if swing_high <= swing_low:
                return None
            swing_range = swing_high - swing_low
            if swing_range / max(swing_low, 1) < min_swing_pct:
                return None  # swing too small for this window

            current_price = float(closes.iloc[-1])
            return {
                "swing_low": swing_low, "swing_high": swing_high,
                "swing_range": swing_range, "current_price": current_price,
            }
        except Exception:
            return None

    # Try the requested lookback first; expand if no qualifying swing found
    swing = _try_lookback(lookback) or _try_lookback(min(lookback * 2, 252)) or _try_lookback(252)
    if not swing:
        return out

    swing_low = swing["swing_low"]
    swing_high = swing["swing_high"]
    swing_range = swing["swing_range"]
    current_price = swing["current_price"]

    t1_ext = swing_low + fib_extensions[0] * swing_range
    t2_ext = swing_low + (fib_extensions[1] if len(fib_extensions) > 1 else 1.618) * swing_range

    out["swing_low"] = round(swing_low, 2)
    out["swing_high"] = round(swing_high, 2)
    out["swing_range"] = round(swing_range, 2)
    out["t1_extension"] = round(t1_ext, 2)
    out["t2_extension"] = round(t2_ext, 2)

    if current_price >= swing_high:
        out["wave"] = 3
        out["type"] = "impulse"
        breakout_pct = (current_price - swing_high) / swing_high
        if breakout_pct > 0.05:
            out["confidence"] = "high"
        elif breakout_pct > 0.01:
            out["confidence"] = "medium"
        else:
            out["confidence"] = "low"
    elif current_price >= swing_low + swing_range * 0.5:
        out["wave"] = 2
        out["type"] = "corrective"
        out["confidence"] = "medium"
    elif current_price >= swing_low + swing_range * 0.382:
        out["wave"] = 2
        out["type"] = "corrective"
        out["confidence"] = "low"
    else:
        out["wave"] = 2
        out["type"] = "corrective"
        out["confidence"] = "low"

    return out


# ════════════════════════════════════════════════════════════════════════════
# BHE RULE GATE — Elliott Wave Ruleset v1.0 (May 2026)
# ════════════════════════════════════════════════════════════════════════════
# Engine input documentation: complete machine-implementable EW classifier.
# Implements the 3 absolute impulse rules, 6 corrective patterns, 5 fib-
# retracement levels, 4 fib-extension levels, and 8 engine states. Output
# feeds Gate G3 (quant veto) and the EW sub-score in the Quant Models pillar.
#
# Architecture (3 timeframe degrees, run simultaneously):
#   Primary       — Weekly  — long-term bias modifier
#   Intermediate  — Daily   — drives the trade verdict (primary input)
#   Minor         — 4H      — entry-timing confirmation
#
# Fractal pivot rule: high[i] > high[i±1] AND high[i] > high[i±2] (5-bar).
# Pivots not confirmed in real-time — confirmed 2 bars after the candle.
# ════════════════════════════════════════════════════════════════════════════

# Engine state → score contribution (BHE spec §EW Score Lookup Table)
_BHE_EW_STATE_SCORES = {
    "WAVE3_IMPULSE":     {"score": 4, "bullish": True,  "bearish": False, "verdict_hint": "ENTER"},
    "WAVE5_IMPULSE":     {"score": 2, "bullish": True,  "bearish": False, "verdict_hint": "WATCH"},
    "WAVE4_TRIANGLE":    {"score": 2, "bullish": False, "bearish": False, "verdict_hint": "WATCH"},
    "WAVE2_CORRECTION":  {"score": 1, "bullish": False, "bearish": False, "verdict_hint": "WATCH"},
    "WAVE4_CORRECTION":  {"score": 1, "bullish": False, "bearish": False, "verdict_hint": "WATCH"},
    "WAVE_A_CORRECTION": {"score": 0, "bullish": False, "bearish": True,  "verdict_hint": "AVOID"},
    "WAVE_C_CORRECTION": {"score": 0, "bullish": False, "bearish": True,  "verdict_hint": "AVOID"},
    "AMBIGUOUS":         {"score": 0, "bullish": False, "bearish": False, "verdict_hint": "AMBIGUOUS"},
}

# Fibonacci retracement levels (BHE spec §RET)
_BHE_FIB_RETRACE_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 0.886]
# Fibonacci extension levels (BHE spec §EXT)
_BHE_FIB_EXT_LEVELS    = [1.000, 1.272, 1.618, 2.618, 4.236]


def _bhe_find_fractals(df, n_pivots: int = 8) -> list:
    """Identify confirmed fractal pivots per BHE spec §0.3.

    Fractal High: high[i] > high[i±1] AND high[i] > high[i±2]
    Fractal Low:  low[i]  < low[i±1]  AND low[i]  < low[i±2]

    Pivot is NOT confirmed for the most recent 2 bars (need i+1, i+2).

    Returns a list of pivots (most recent last):
      [{price, type: 'HIGH'|'LOW', index: int}, ...]
    Limited to last n_pivots for Intermediate-degree analysis.
    """
    if df is None or len(df) < 5:
        return []
    try:
        highs = df["High"].squeeze().values if hasattr(df["High"], "squeeze") else df["High"].values
        lows  = df["Low"].squeeze().values  if hasattr(df["Low"], "squeeze")  else df["Low"].values
    except Exception:
        return []

    pivots = []
    # Stop at len-3 because we need i+1 and i+2 for confirmation
    for i in range(2, len(highs) - 2):
        h = highs[i]
        l = lows[i]
        if (h > highs[i-2] and h > highs[i-1] and
            h > highs[i+1] and h > highs[i+2]):
            pivots.append({"price": float(h), "type": "HIGH", "index": i})
        if (l < lows[i-2] and l < lows[i-1] and
            l < lows[i+1] and l < lows[i+2]):
            pivots.append({"price": float(l), "type": "LOW", "index": i})
    # Sort by index, keep most recent n_pivots
    pivots.sort(key=lambda p: p["index"])
    return pivots[-n_pivots:] if len(pivots) > n_pivots else pivots


def _bhe_validate_impulse_rules(w1_start, w1_end, w2_low, w3_high, w4_low) -> tuple[bool, str]:
    """3 absolute impulse rules (BHE spec §Impulse Rules).

    Rule 1: Wave 2 never retraces >100% of Wave 1 (W2 low > W1 start).
    Rule 2: Wave 3 is never the shortest impulse wave.
    Rule 3: Wave 4 never enters Wave 1 price territory (W4 low > W1 high).

    Returns (valid, reason). Any violation → invalid count.
    """
    if w2_low is not None and w1_start is not None and w2_low <= w1_start:
        return False, "RULE_1: Wave 2 retraced >=100% of Wave 1"
    if all(x is not None for x in (w1_start, w1_end, w2_low, w3_high)):
        w1_len = abs(w1_end - w1_start)
        w3_len = abs(w3_high - w2_low)
        if w4_low is not None and len(str(w4_low)):
            # If Wave 5 hasn't formed yet, skip Rule 2
            pass
        # Rule 3: Wave 4 / Wave 1 overlap (only if W4 has formed)
        if w4_low is not None and w4_low <= w1_end:
            return False, "RULE_3: Wave 4 entered Wave 1 territory"
    return True, "rules_ok"


def _bhe_classify_pivots(pivots: list, current_price: float) -> dict:
    """Map a fractal pivot sequence to one of 8 BHE engine states.

    Returns: {ew_state, ew_bullish, ew_bearish, ew_score, t1, t2,
              invalidated, reason, w1_start, w1_end, w2_low}

    Algorithm (BHE spec §Engine Classification):
      1. Need ≥4 pivots (2 lows + 2 highs) for any classification
      2. Determine HH/HL or LH/LL pattern from last 2 swings
      3. Use last_low (W2 low candidate) and prev_low (W1 start candidate)
      4. Extension targets: T1 = w2_low + 1.618×W1_len, T2 = w2_low + 2.618×W1_len
      5. Apply Rule 1 invalidation
    """
    result = {
        "ew_state": "AMBIGUOUS", "ew_bullish": False, "ew_bearish": False,
        "ew_score": 0, "t1": None, "t2": None,
        "invalidated": False, "reason": "",
        "w1_start": None, "w1_end": None, "w2_low": None,
        "fib_retracement_pct": None,
    }
    if not pivots or len(pivots) < 4:
        result["reason"] = "Insufficient pivot history"
        return result

    lows  = [p for p in pivots if p["type"] == "LOW"][-4:]
    highs = [p for p in pivots if p["type"] == "HIGH"][-4:]
    if len(lows) < 2 or len(highs) < 2:
        result["reason"] = "Need >=2 lows and >=2 highs"
        return result

    last_low  = lows[-1]["price"]
    prev_low  = lows[-2]["price"]
    last_high = highs[-1]["price"]
    prev_high = highs[-2]["price"]

    hh = last_high > prev_high
    hl = last_low > prev_low
    lh = last_high < prev_high
    ll = last_low < prev_low

    # Wave 1 = first impulse leg (prev_low → last_high if HH/HL)
    # Wave 2 low = last_low (if HL with retracement)
    w1_start = prev_low
    w1_end   = last_high
    w2_low   = last_low
    w1_len   = w1_end - w1_start
    if w1_len <= 0:
        result["reason"] = "Wave 1 length non-positive"
        return result

    # Rule 1 check
    if w2_low <= w1_start:
        result["invalidated"] = True
        result["reason"] = "RULE_1 violation: W2 low <= W1 start"
        return result

    fib_retrace = (w1_end - w2_low) / w1_len if w1_len > 0 else 0
    result["fib_retracement_pct"] = round(fib_retrace, 4)
    result["w1_start"] = round(w1_start, 4)
    result["w1_end"]   = round(w1_end, 4)
    result["w2_low"]   = round(w2_low, 4)

    # Targets via Fibonacci extension from W2 low (BHE spec §EXT)
    t1 = round(w2_low + (w1_len * 1.618), 4)
    t2 = round(w2_low + (w1_len * 2.618), 4)

    # ── State classification ──
    # WAVE3_IMPULSE: HH + HL pattern, price advancing past last_high (within 3%)
    if hh and hl and current_price > last_high * 0.97:
        if 0.236 <= fib_retrace <= 0.886:
            result.update({
                "ew_state": "WAVE3_IMPULSE",
                "ew_bullish": True, "ew_score": 4,
                "t1": t1, "t2": t2,
                "reason": f"HH+HL, W2 retrace {fib_retrace*100:.1f}% in 23.6-88.6 band, price >97% of last high",
            })
            return result

    # WAVE2_CORRECTION: HH up, then pullback (price < last_high * 0.97)
    if hh and current_price < last_high * 0.97:
        # current_price IS the working W2 low candidate
        cur_retrace = (last_high - current_price) / w1_len if w1_len > 0 else 0
        if 0.382 <= cur_retrace <= 0.886:
            result.update({
                "ew_state": "WAVE2_CORRECTION",
                "ew_bullish": False, "ew_score": 1,
                "t1": round(last_high + (w1_len * 0.618), 4),  # W3 minimum target
                "t2": round(last_high + (w1_len * 1.618), 4),  # W3 typical target
                "reason": f"HH then pullback {cur_retrace*100:.1f}% — Wave 2 corrective in W1 retrace band",
                "fib_retracement_pct": round(cur_retrace, 4),
            })
            return result

    # WAVE_A_CORRECTION: LH + LL, price declining
    if lh and ll:
        result.update({
            "ew_state": "WAVE_A_CORRECTION",
            "ew_bullish": False, "ew_bearish": True, "ew_score": 0,
            "reason": "LH+LL — bearish corrective leg",
        })
        return result

    # WAVE_C_CORRECTION: LH + LL with steeper decline (heuristic — final leg)
    # Not detected without 5-wave sub-count; fall through to AMBIGUOUS
    # WAVE5_IMPULSE: HH+HL but price near last high without breakout (price ≤ last_high)
    # — not implemented here without sub-wave counting; falls to AMBIGUOUS
    # WAVE4_TRIANGLE: requires 5-leg ABCDE detection; not in v1.0 implementation

    result["reason"] = f"AMBIGUOUS — pivots don't match a clean state (HH={hh},HL={hl},LH={lh},LL={ll})"
    return result


def classify_elliott_wave_bhe(df, df_weekly=None, df_4h=None, current_price: float | None = None) -> dict:
    """BHE Rule Gate v1.0 — Elliott Wave classifier (Intermediate degree).

    Implements the BHE specification: 8 engine states, 3 absolute impulse rules,
    Fibonacci retracements 23.6-88.6%, Fibonacci extensions 100-423.6%, multi-
    timeframe alignment (Primary modifier × Intermediate base + Minor confirmation).

    Args:
        df:          Daily OHLCV (Intermediate degree — drives the trade verdict)
        df_weekly:   Optional weekly OHLCV (Primary degree — bias modifier)
        df_4h:       Optional 4H OHLCV (Minor degree — entry timing)
        current_price: Live price; falls back to last close

    Returns dict matching BHE spec §REF outputs:
        {
            "ew_state": str (one of 8 states),
            "ew_bullish": bool,
            "ew_bearish": bool,
            "ew_score": int (0-4),
            "t1": float | None,                   # extension target (price)
            "t2": float | None,
            "invalidated": bool,
            "reason": str,
            "intermediate": {full classification},
            "primary": {weekly classification | None},
            "minor": {4H classification | None},
            "mtf_alignment": {primary_mult, minor_aligned, warning?},
            "fib_retracement_pct": float,
            "spec_version": "BHE-v1.0",
        }
    """
    out = {
        "ew_state": "AMBIGUOUS", "ew_bullish": False, "ew_bearish": False,
        "ew_score": 0, "t1": None, "t2": None,
        "invalidated": False, "reason": "",
        "intermediate": None, "primary": None, "minor": None,
        "mtf_alignment": {}, "fib_retracement_pct": None,
        "spec_version": "BHE-v1.0",
    }
    if df is None or len(df) < 30:
        out["reason"] = "Insufficient daily history (need >=30 bars)"
        return out

    if current_price is None:
        try:
            current_price = float(df["Close"].iloc[-1])
        except Exception:
            out["reason"] = "Cannot determine current price"
            return out

    # ── Intermediate degree (Daily) — drives the verdict ──
    intermediate_pivots = _bhe_find_fractals(df, n_pivots=8)
    intermediate = _bhe_classify_pivots(intermediate_pivots, current_price)
    out["intermediate"] = intermediate

    # Adopt intermediate as the base
    out["ew_state"]    = intermediate["ew_state"]
    out["ew_bullish"]  = intermediate["ew_bullish"]
    out["ew_bearish"]  = intermediate["ew_bearish"]
    out["ew_score"]    = intermediate["ew_score"]
    out["t1"]          = intermediate["t1"]
    out["t2"]          = intermediate["t2"]
    out["invalidated"] = intermediate["invalidated"]
    out["reason"]      = intermediate["reason"]
    out["fib_retracement_pct"] = intermediate.get("fib_retracement_pct")

    # ── Primary degree (Weekly) — bias modifier ──
    if df_weekly is not None and len(df_weekly) >= 20:
        primary_pivots = _bhe_find_fractals(df_weekly, n_pivots=6)
        primary = _bhe_classify_pivots(primary_pivots, current_price)
        out["primary"] = primary

        # Primary bullish states: WAVE3_IMPULSE, WAVE5_IMPULSE, WAVE2_CORRECTION
        primary_bullish = primary["ew_state"] in (
            "WAVE3_IMPULSE", "WAVE5_IMPULSE", "WAVE2_CORRECTION"
        )
        primary_bearish = primary["ew_state"] in (
            "WAVE_A_CORRECTION", "WAVE_C_CORRECTION"
        )
        primary_mult = 1.0 if primary_bullish else 0.5

        if primary_bearish:
            # Trading against primary correction — flag warning
            out["mtf_alignment"]["warning"] = (
                "TREND_CONFLICT: Trading against Primary degree correction"
            )

        out["mtf_alignment"]["primary_mult"]    = primary_mult
        out["mtf_alignment"]["primary_bullish"] = primary_bullish
        out["mtf_alignment"]["primary_bearish"] = primary_bearish
        out["ew_score"] = min(round(out["ew_score"] * primary_mult), 4)

    # ── Minor degree (4H) — entry timing confirmation ──
    if df_4h is not None and len(df_4h) >= 20:
        minor_pivots = _bhe_find_fractals(df_4h, n_pivots=6)
        minor = _bhe_classify_pivots(minor_pivots, current_price)
        out["minor"] = minor
        minor_aligned = minor["ew_state"] in ("WAVE3_IMPULSE", "WAVE4_CORRECTION")
        out["mtf_alignment"]["minor_aligned"] = minor_aligned

    return out


def gate_g3_quant_veto(ew_result: dict, mc_p50: float | None,
                        current_price: float, wyckoff_phase: str = "") -> dict:
    """Gate G3 — Quant Veto (BHE spec §G3).

    Combines EW + Monte Carlo + Wyckoff into a 3-theory consensus check.
    Hard veto fires only when BOTH EW is bearish AND MC P50 is below current
    price. A single bearish theory does NOT block — the verdict is BLOCKED only
    on dual confirmation.

    Args:
        ew_result:      Output of classify_elliott_wave_bhe()
        mc_p50:         Monte Carlo median forward price (None if unavailable)
        current_price:  Live price
        wyckoff_phase:  String (MARKUP / ACCUMULATION_LATE / DISTRIBUTION / etc.)

    Returns:
        {
            "verdict": "PASS" | "BLOCKED" | "SKIP",
            "reason": str,
            "theories_bull": int (0-3),
            "theory_score": int (0-18, max 18 of 20 Quant pts),
            "ew_bullish": bool, "ew_bearish": bool,
            "mc_bearish": bool, "wyckoff_bullish": bool,
        }
    """
    ew_bullish = bool(ew_result.get("ew_bullish"))
    ew_bearish = bool(ew_result.get("ew_bearish"))
    mc_bearish = (mc_p50 is not None and mc_p50 < current_price)
    wyckoff_bullish = (wyckoff_phase or "").upper() in ("MARKUP", "ACCUMULATION_LATE")

    out = {
        "ew_bullish": ew_bullish, "ew_bearish": ew_bearish,
        "mc_bearish": mc_bearish, "wyckoff_bullish": wyckoff_bullish,
    }

    # ── HARD VETO: both EW bearish AND MC bearish ──
    if ew_bearish and mc_bearish:
        out.update({
            "verdict": "BLOCKED",
            "reason": "QUANT_VETO: EW bearish AND MC P50 below price",
            "theories_bull": 0, "theory_score": 0,
        })
        return out

    # ── Confluence: count bullish theories ──
    theories_bullish = sum([ew_bullish, not mc_bearish, wyckoff_bullish])
    if theories_bullish < 2:
        out.update({
            "verdict": "SKIP",
            "reason": f"Only {theories_bullish}/3 theories bullish — minimum 2 required",
            "theories_bull": theories_bullish, "theory_score": 0,
        })
        return out

    # ── PASS: theory score (0-18 of 20 Quant pts) ──
    theory_score = (
        int(ew_result.get("ew_score", 0)) +              # 0-4 from EW
        (6 if wyckoff_bullish else 0) +                   # 0-6 from Wyckoff
        (8 if not mc_bearish else 0)                      # 0-8 from MC
    )
    out.update({
        "verdict": "PASS",
        "reason": f"{theories_bullish}/3 theories bullish — confluence cleared",
        "theories_bull": theories_bullish,
        "theory_score": theory_score,
    })
    return out


# ── Williams Fractals ─────────────────────────────────────────────────────────

def _williams_fractals(df, lookback: int = 60) -> dict:
    """
    Williams Fractals: identify local swing highs/lows.
    Fractal High = bar whose High is the highest of 5 consecutive bars (2 on each side).
    Fractal Low  = bar whose Low  is the lowest  of 5 consecutive bars.
    Returns active (unbroken) fractal levels as dynamic S/R.
    """
    if len(df) < 5:
        return {"recent_highs": [], "recent_lows": [],
                "active_high": None, "active_low": None}

    recent = df.tail(lookback)
    h = recent["High"].squeeze().values if hasattr(recent["High"], "squeeze") else recent["High"].values
    lo = recent["Low"].squeeze().values if hasattr(recent["Low"], "squeeze") else recent["Low"].values

    frac_highs = []   # (bar_index_from_end, price)
    frac_lows  = []

    for i in range(2, len(h) - 2):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            frac_highs.append((lookback - len(h) + i, round(float(h[i]), 2)))
        if lo[i] < lo[i-1] and lo[i] < lo[i-2] and lo[i] < lo[i+1] and lo[i] < lo[i+2]:
            frac_lows.append((lookback - len(h) + i, round(float(lo[i]), 2)))

    price = float(df["Close"].iloc[-1])

    # Active fractal high: most recent unbroken (price still below it)
    active_high = None
    for _, fp in reversed(frac_highs):
        if price < fp:
            active_high = fp
            break

    # Active fractal low: most recent unbroken (price still above it)
    active_low = None
    for _, fp in reversed(frac_lows):
        if price > fp:
            active_low = fp
            break

    return {
        "recent_highs": [p for _, p in frac_highs[-3:]],
        "recent_lows":  [p for _, p in frac_lows[-3:]],
        "active_high":  active_high,
        "active_low":   active_low,
    }


# ── Short Squeeze Setup ───────────────────────────────────────────────────────

def _short_squeeze_setup(info: dict, indicators: dict) -> dict:
    """
    Detect potential short squeeze conditions.
    High short float + price above 50 EMA + rising volume = trapped shorts.
    Score 0-8: >= 5 = squeeze candidate.
    """
    short_float = float(info.get("short_percent_of_float") or 0)
    short_ratio = float(info.get("short_ratio") or 0)        # days-to-cover
    rsi         = float(indicators.get("rsi", 50) or 50)
    rvol        = float(indicators.get("rvol", 1.0) or 1.0)
    trend       = indicators.get("trend_direction", "")
    price_ok    = trend not in ("downtrend",)

    score = 0
    if short_float > 0.20:   score += 3   # >20% float short = heavily shorted
    elif short_float > 0.15: score += 2
    elif short_float > 0.10: score += 1

    if short_ratio > 7:      score += 2   # >7 days to cover = squeezable
    elif short_ratio > 4:    score += 1

    if rvol > 2.0 and price_ok:  score += 2   # volume surge with upward price
    elif rvol > 1.5 and price_ok: score += 1

    if 45 <= rsi <= 70:      score += 1   # momentum building, not overbought

    return {
        "short_float":   round(short_float * 100, 1),
        "short_ratio":   round(short_ratio, 1),
        "squeeze_score": score,
        "squeeze_setup": score >= 5,
    }


# ── Post-Earnings Drift (PEAD) ────────────────────────────────────────────────

def _post_earnings_drift(earnings: dict, df, info: dict) -> dict:
    """
    Post-Earnings Announcement Drift: stocks beating EPS + raising guidance
    statistically continue rising for 2-3 weeks after the gap-up.
    Flags if within 21 days of a strong beat with positive price action.
    """
    na = {"pead": False, "days_since_earnings": None, "eps_surprise_pct": None}

    eps_surprise = info.get("eps_surprise_pct") or info.get("earnings_surprise_pct")
    last_date    = earnings.get("last_earnings_date")

    if eps_surprise is None or last_date is None:
        return na

    try:
        if isinstance(last_date, str):
            import datetime as _dt
            last_date = _dt.datetime.strptime(last_date[:10], "%Y-%m-%d")
        days_since = (pd.Timestamp.now() - pd.Timestamp(last_date)).days
    except Exception:
        return na

    if days_since < 1 or days_since > 21:
        return na

    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    if len(close) < days_since + 2:
        return na

    # Price return from earnings date
    earnings_close = float(close.iloc[-(days_since + 1)])
    current_price  = float(close.iloc[-1])
    post_ret       = (current_price - earnings_close) / max(earnings_close, 0.01)

    pead = (float(eps_surprise) > 0.05   # beat by 5%+
            and post_ret > 0.02           # still positive post-earnings
            and days_since <= 21)

    return {
        "pead":               pead,
        "days_since_earnings": days_since,
        "eps_surprise_pct":   round(float(eps_surprise) * 100, 1),
        "post_ret_pct":       round(post_ret * 100, 1),
    }


# ── Gap Risk ─────────────────────────────────────────────────────────────────

def _gap_risk(df) -> dict:
    """
    Assess overnight gap risk: gap frequency (opens >2% vs prior close) + ATR%.
    Returns: level (low/medium/high), large_gaps_20d, avg_gap_pct, atr_pct.
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    open_  = df["Open"].squeeze()  if isinstance(df["Open"],  pd.DataFrame) else df["Open"]
    high   = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    prev_close = close.shift(1)
    gap_pct = ((open_ - prev_close) / prev_close.replace(0, np.nan)).abs()
    recent  = gap_pct.tail(20)
    large_gaps  = int((recent > 0.02).sum())
    avg_gap_pct = float(recent.mean()) * 100 if not recent.empty else 0

    atr_s   = _atr(high, low, close, 14)
    price   = float(close.iloc[-1])
    atr_pct = float(atr_s.iloc[-1]) / price * 100 if not atr_s.empty and price > 0 else 0

    if large_gaps >= 8 or atr_pct > 5:
        level = "high"
    elif large_gaps >= 4 or atr_pct > 3:
        level = "medium"
    else:
        level = "low"

    return {"level": level, "large_gaps_20d": large_gaps,
            "avg_gap_pct": round(avg_gap_pct, 2), "atr_pct": round(atr_pct, 2)}


# ── Elliott Wave Analysis ────────────────────────────────────────────────────

def _ew_unknown(reason: str) -> dict:
    return {
        "wave_number": "?", "wave_label": reason,
        "description": reason, "trend": "neutral",
        "confidence": "low", "fib_levels": {},
        "nearest_fib": None, "bonus": 0,
        "swing_base": None, "swing_top": None,
    }


def score_elliott_wave(df: pd.DataFrame) -> dict:
    """
    Simplified Elliott Wave counter for swing trading.
    Detects current wave (1–5 or A–B–C), Fibonacci levels, and a score bonus.

    Returns:
        wave_number  — int (1-5) or str ('A','B','C','?')
        wave_label   — e.g. "Wave 3 (Impulse)"
        description  — plain-English interpretation
        trend        — 'bullish' | 'bearish' | 'neutral'
        confidence   — 'high' | 'medium' | 'low'
        fib_levels   — dict {label: price} for key Fibonacci retracement levels
        nearest_fib  — (label, price) closest to current price
        bonus        — int score adjustment (-1 to +1)
        swing_base   — float: base price of the last measured swing
        swing_top    — float: top price of the last measured swing
    """
    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high  = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low   = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]

    if len(close) < 30:
        return _ew_unknown("Insufficient data (<30 bars)")

    price = float(close.iloc[-1])
    n = len(close)
    window = 5

    # ── Step 1: Find raw pivot highs and lows ────────────────────────────────
    raw_highs, raw_lows = [], []
    for i in range(window, n - window):
        h_slice = high.iloc[i - window: i + window + 1]
        l_slice = low.iloc[i - window: i + window + 1]
        if float(high.iloc[i]) >= float(h_slice.max()) - 1e-9:
            raw_highs.append((i, float(high.iloc[i])))
        if float(low.iloc[i]) <= float(l_slice.min()) + 1e-9:
            raw_lows.append((i, float(low.iloc[i])))

    # ── Step 2: Build alternating swing sequence ──────────────────────────────
    all_pts = [(i, p, "H") for i, p in raw_highs] + [(i, p, "L") for i, p in raw_lows]
    all_pts.sort(key=lambda x: x[0])
    swings: list[list] = []
    for idx, pt_price, ptype in all_pts:
        if not swings or swings[-1][2] != ptype:
            swings.append([idx, pt_price, ptype])
        else:
            if (ptype == "H" and pt_price > swings[-1][1]) or \
               (ptype == "L" and pt_price < swings[-1][1]):
                swings[-1] = [idx, pt_price, ptype]

    if len(swings) < 4:
        return _ew_unknown("Pattern still forming")

    # ── Step 3: Determine dominant trend ─────────────────────────────────────
    recent = swings[-min(8, len(swings)):]
    lows_r  = [(i, p) for i, p, t in recent if t == "L"]
    highs_r = [(i, p) for i, p, t in recent if t == "H"]

    bull = (len(highs_r) >= 2 and highs_r[-1][1] > highs_r[0][1] and
            len(lows_r)  >= 2 and lows_r[-1][1]  > lows_r[0][1])
    bear = (len(highs_r) >= 2 and highs_r[-1][1] < highs_r[0][1] and
            len(lows_r)  >= 2 and lows_r[-1][1]  < lows_r[0][1])
    trend = "bullish" if bull else "bearish" if bear else "neutral"

    last_type  = recent[-1][2]
    last_price = recent[-1][1]

    # ── Step 4: Label the current wave ───────────────────────────────────────
    wave_num: int | str = "?"
    wave_label   = "Consolidating"
    description  = "No clear Elliott Wave structure identified. Sideways consolidation."
    confidence   = "low"
    bonus        = 0

    if bull:
        if last_type == "L":
            # Price sitting on a low — wave 2 or 4 just completed
            if len(lows_r) >= 2 and lows_r[-1][1] > lows_r[-2][1]:
                if len(highs_r) >= 2 and highs_r[-1][1] > highs_r[-2][1]:
                    wave_num, wave_label = 3, "Wave 3 (Impulse)"
                    description = ("Wave 2 correction complete — Wave 3 (the power wave) is starting. "
                                   "Strongest momentum expected. High-conviction entry zone.")
                    confidence, bonus = "medium", 1
                else:
                    wave_num, wave_label = 1, "Wave 1 (Impulse Start)"
                    description = ("New uptrend beginning. Wave 1 off confirmed base — "
                                   "early entry before Wave 3 acceleration.")
                    confidence, bonus = "medium", 1
            else:
                wave_num, wave_label = 4, "Wave 4 (Correction)"
                description = ("Corrective pullback — Wave 4 typically retraces 38.2% of Wave 3. "
                               "Wait for Wave 4 completion before entering Wave 5.")
                confidence, bonus = "medium", 0
        else:  # last is a High
            if len(highs_r) >= 2 and highs_r[-1][1] > highs_r[-2][1]:
                # Still making higher highs
                if len(lows_r) >= 2 and lows_r[-1][1] > lows_r[-2][1]:
                    if price >= last_price * 0.96:
                        wave_num, wave_label = 5, "Wave 5 (Final Impulse)"
                        description = ("Final impulse wave. Momentum may be diverging. "
                                       "Monitor for reversal signs — tighten stops.")
                        confidence, bonus = "medium", 1
                    else:
                        wave_num, wave_label = 3, "Wave 3 (Impulse)"
                        description = ("Strong impulse wave underway. Volume and momentum should be "
                                       "expanding. Ride the trend with a trailing stop.")
                        confidence, bonus = "medium", 1
            else:
                wave_num, wave_label = 2, "Wave 2 (Correction)"
                description = ("Wave 2 pullback from Wave 1 high. Look for 38.2–61.8% "
                               "Fibonacci retracement as the ideal Wave 3 entry zone.")
                confidence, bonus = "medium", 1
    elif bear:
        if last_type == "H":
            wave_num, wave_label = "B", "Wave B (Counter-trend Bounce)"
            description = ("Wave B bounce in a corrective structure. Counter-trend — "
                           "likely to resume decline. Shorting opportunity near resistance.")
            confidence, bonus = "medium", -1
        else:
            if len(lows_r) >= 2 and lows_r[-1][1] < lows_r[-2][1]:
                wave_num, wave_label = "C", "Wave C (Corrective Decline)"
                description = ("Wave C decline underway — typically equal to Wave A in length. "
                               "Avoid longs until C-wave target is reached.")
                confidence, bonus = "medium", -1
            else:
                wave_num, wave_label = "A", "Wave A (Initial Decline)"
                description = ("First leg of correction. Wave B bounce likely before Wave C decline. "
                               "Reduce exposure and wait for clearer entry.")
                confidence, bonus = "low", -1

    # ── Step 5: Fibonacci levels ──────────────────────────────────────────────
    swing_base = lows_r[-1][1]  if lows_r  else None
    swing_top  = highs_r[-1][1] if highs_r else None
    fib_levels: dict[str, float] = {}

    if swing_base is not None and swing_top is not None:
        span = abs(swing_top - swing_base)
        if span > 0:
            if bull or trend == "neutral":
                # Retracements down from the high
                for ratio, name in [
                    (0.236, "23.6%"), (0.382, "38.2%"), (0.500, "50.0%"),
                    (0.618, "61.8%"), (0.786, "78.6%"), (1.000, "100%"),
                    (1.272, "127.2%"), (1.618, "161.8%"),
                ]:
                    fib_levels[name] = round(swing_top - ratio * span, 2)
            else:
                # Extensions down from the recent high
                for ratio, name in [
                    (0.236, "23.6%"), (0.382, "38.2%"), (0.500, "50.0%"),
                    (0.618, "61.8%"), (0.786, "78.6%"), (1.000, "100%"),
                    (1.272, "127.2%"), (1.618, "161.8%"),
                ]:
                    fib_levels[name] = round(swing_top + ratio * span, 2)

    nearest_fib = (
        min(fib_levels.items(), key=lambda x: abs(x[1] - price))
        if fib_levels else None
    )

    return {
        "wave_number":  wave_num,
        "wave_label":   wave_label,
        "description":  description,
        "trend":        trend,
        "confidence":   confidence,
        "fib_levels":   fib_levels,
        "nearest_fib":  list(nearest_fib) if nearest_fib else None,
        "bonus":        bonus,
        "swing_base":   round(swing_base, 2) if swing_base else None,
        "swing_top":    round(swing_top,  2) if swing_top  else None,
    }


# ── Pre-Trade Gate ───────────────────────────────────────────────────────────

def pre_trade_gate(ticker: str, df: pd.DataFrame, info: dict,
                   regime: dict, earnings: dict, config: dict,
                   skip_market_gates: bool = False,
                   breadth: dict | None = None) -> dict:
    """
    Hard filter gate. Returns {passed: bool, reasons: [str]}.
    Reject if ANY fail.
    """
    reasons = []
    gates_cfg = config.get("gates", {})
    filters_cfg = config.get("filters", {})

    # Minimum history required for technical analysis (RSI=14, EMA-20, etc.)
    min_bars = gates_cfg.get("min_history_bars", 30)
    if len(df) < min_bars:
        return {"passed": False, "reasons": [f"Insufficient price history ({len(df)} bars < {min_bars} required)"],
                "weak_regime": False, "daily_dollar_vol": 0, "price": 0,
                "drawdown_from_ath": None, "gap_risk": None, "div_warning": None}

    price = float(df["Close"].iloc[-1])
    volume = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else volume

    # Price range
    min_p = filters_cfg.get("min_price", 5)
    max_p = filters_cfg.get("max_price", 250)
    if price < min_p or price > max_p:
        reasons.append(f"Price ${price:.2f} outside ${min_p:.0f}–${max_p:.0f} range")

    # Liquidity: avg daily dollar volume
    daily_dollar_vol = avg_vol * price
    min_liq = gates_cfg.get("min_liquidity_daily", 10_000_000)
    if daily_dollar_vol < min_liq:
        reasons.append(f"Liquidity ${daily_dollar_vol/1e6:.1f}M < ${min_liq/1e6:.0f}M/day")

    # P2.21 — Macro calendar advisory (FOMC/CPI/NFP/PCE day-of and morning-after)
    # SOFT advisory by default — banner warns, picks still visible. Set
    # gates.macro_blackout_hard=true to make it block trades entirely.
    # Toggle gates.macro_blackout_enabled=false to disable both.
    if not skip_market_gates and gates_cfg.get("macro_blackout_enabled", True):
        try:
            import macro_calendar as _mc
            _morning_after = gates_cfg.get("macro_blackout_morning_after", False)
            _macro_blocked, _macro_reason = _mc.is_macro_blackout(morning_after=_morning_after)
            if _macro_blocked:
                # Default: advisory only — surfaces in audit_trail + banner
                if gates_cfg.get("macro_blackout_hard", False):
                    reasons.append(f"HARD: macro blackout — {_macro_reason}")
                # else: silent — system_status banner alerts the user
        except Exception:
            pass

    # Phase 5C: Hard earnings blackout — block within 3 days, soft gate within blackout
    blackout = gates_cfg.get("earnings_blackout_days", 5)
    days_to_earn = earnings.get("days_to_earnings")
    if days_to_earn is not None and isinstance(days_to_earn, (int, float)):
        if days_to_earn <= 3:
            reasons.append(f"HARD BLOCK: Earnings in {days_to_earn} days — no new positions within 3 days of earnings")
        elif days_to_earn <= blackout:
            reasons.append(f"Earnings in {days_to_earn} days (blackout {blackout}d)")
    elif earnings.get("earnings_risk"):
        days = earnings.get("days_to_earnings", "?")
        reasons.append(f"Earnings in {days} days (blackout {blackout}d)")

    # Entry day gate — no new longs when SPY is down >1.5% intraday
    # (skip in backtest mode since we're evaluating hypothetically)
    if not skip_market_gates:
        spy_drop_pct  = float(regime.get("spy_daily_chg", 0))
        spy_drop_gate = gates_cfg.get("entry_day_spy_drop_pct", -1.5)
        if spy_drop_pct <= spy_drop_gate:
            reasons.append(f"SPY down {spy_drop_pct:.1f}% today — entry day gate (no new longs on crash day)")

        # Distribution days gate (IBD) — ≥7 distribution days = no new longs
        dist_days   = int(regime.get("distribution_days", 0))
        dist_no_new = gates_cfg.get("distribution_days_no_new", 7)
        if dist_days >= dist_no_new:
            reasons.append(f"{dist_days} distribution days — IBD threshold: no new longs (>={dist_no_new})")

    # Weak market regime — require higher conviction (handled at scoring level)
    regime_flag = regime.get("regime") == "bear"

    # Max drawdown from ATH — flag stocks >35% below 52w high (not a hard gate)
    drawdown_from_ath = None
    high_52w = info.get("52w_high") if info else None
    if high_52w and price > 0:
        drawdown_from_ath = round((high_52w - price) / high_52w * 100, 1)

    # Market breadth gate — collapse in broad market participation blocks new longs
    if not skip_market_gates and breadth:
        pct_50 = breadth.get("pct_above_50d", 100)
        if pct_50 < 25:
            reasons.append(
                f"Market breadth collapse: only {pct_50:.0f}% of stocks above 50d MA "
                f"— no new longs until breadth recovers above 25%"
            )

    # Dividend ex-date gate — avoid entering a position 1-3 days before ex-dividend
    # The stock drops ~dividend amount on ex-date, distorting the trade
    div_yield = info.get("dividend_yield") or info.get("dividendYield") if info else None
    ex_div_date = info.get("ex_dividend_date") or info.get("exDividendDate") if info else None
    div_warning = None
    if ex_div_date and div_yield and div_yield > 0.005:  # only flag if yield >0.5% (material)
        try:
            import datetime as _dt
            if isinstance(ex_div_date, (int, float)):
                ex_dt = _dt.datetime.utcfromtimestamp(ex_div_date).date()
            else:
                ex_dt = _dt.datetime.strptime(str(ex_div_date)[:10], "%Y-%m-%d").date()
            today = _dt.date.today()
            days_to_ex = (ex_dt - today).days
            if 0 <= days_to_ex <= 3:
                reasons.append(
                    f"Ex-dividend in {days_to_ex}d ({ex_dt}) — stock drops ~{div_yield:.1%} on ex-date, skip entry"
                )
            elif -1 <= days_to_ex < 0:
                div_warning = f"Ex-dividend was yesterday — price gap already happened"
        except Exception:
            pass

    # Phase 5B: Gap risk — now used as soft gate (high gap risk = warning, not hard block)
    gap_risk = _gap_risk(df)
    if gap_risk and gap_risk.get("avg_gap_pct", 0) > 3.0:
        reasons.append(f"High gap risk: avg {gap_risk['avg_gap_pct']:.1f}% gap — use wider stop or reduce size")

    # Bug #1 fix: Wire extended_atr_gate — hard block if price > N× ATR above EMA21
    # Regime-aware: relax in trending bull (stocks ARE extended when trending),
    # keep strict in choppy/bear to prevent chasing.
    try:
        _ext_mult_base = float(gates_cfg.get("extended_atr_gate", 1.5))
        _regime_name_gate = str(regime.get("regime", "neutral")).lower()
        _regime4_gate = str(regime.get("regime4", "") or "").lower()
        if _regime_name_gate == "bull" or _regime4_gate == "risk_on_trending":
            _ext_mult = max(_ext_mult_base, 3.5)  # trending: allow up to 3.5 ATR
        elif _regime_name_gate == "neutral" or "choppy" in _regime4_gate:
            _ext_mult = max(_ext_mult_base, 2.5)  # choppy: moderate tolerance
        else:
            _ext_mult = _ext_mult_base  # bear/risk-off: strict
        import pandas as _pd_eag
        _close = df["Close"].squeeze() if isinstance(df["Close"], _pd_eag.DataFrame) else df["Close"]
        _high = df["High"].squeeze() if isinstance(df["High"], _pd_eag.DataFrame) else df["High"]
        _low = df["Low"].squeeze() if isinstance(df["Low"], _pd_eag.DataFrame) else df["Low"]
        if len(df) >= 22:
            _ema21 = _close.ewm(span=21, adjust=False).mean().iloc[-1]
            _tr = _pd_eag.concat([
                (_high - _low),
                (_high - _close.shift(1)).abs(),
                (_low - _close.shift(1)).abs(),
            ], axis=1).max(axis=1)
            _atr = float(_tr.rolling(14).mean().iloc[-1])
            if _atr > 0 and _ema21 > 0:
                _atr_above = (price - _ema21) / _atr
                if _atr_above > _ext_mult:
                    reasons.append(f"Extended gate: price {_atr_above:.1f} ATR above EMA21 (>{_ext_mult} limit) — no entry")
    except Exception:
        pass

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "weak_regime": regime_flag,
        "daily_dollar_vol": round(daily_dollar_vol / 1e6, 1),
        "price": round(price, 2),
        "drawdown_from_ath": drawdown_from_ath,
        "gap_risk": gap_risk,
        "div_warning": div_warning,
    }


# ── VGM Raw Score Functions ──────────────────────────────────────────────────

def raw_value_score(info: dict) -> float | None:
    """Compute raw Value score 0-100 from fundamental ratios. Returns None if < 3 metrics."""
    pts = 0
    max_pts = 0

    pe = info.get("pe_ratio")
    if pe is not None and pe > 0:
        max_pts += 15
        if pe < 12: pts += 15
        elif pe < 18: pts += 12
        elif pe < 25: pts += 8
        elif pe < 35: pts += 4

    fpe = info.get("forward_pe")
    if fpe is not None and fpe > 0:
        max_pts += 15
        if fpe < 12: pts += 15
        elif fpe < 18: pts += 12
        elif fpe < 25: pts += 8
        elif fpe < 35: pts += 4

    peg = info.get("peg_ratio")
    if peg is not None and peg > 0:
        max_pts += 20
        if peg < 0.8: pts += 20
        elif peg < 1.0: pts += 16
        elif peg < 1.5: pts += 10
        elif peg < 2.0: pts += 5

    pb = info.get("price_to_book")
    if pb is not None and pb > 0:
        max_pts += 10
        if pb < 1.5: pts += 10
        elif pb < 3.0: pts += 7
        elif pb < 5.0: pts += 4
        elif pb < 10.0: pts += 2

    ev = info.get("ev_to_ebitda")
    if ev is not None and ev > 0:
        max_pts += 15
        if ev < 8: pts += 15
        elif ev < 12: pts += 12
        elif ev < 20: pts += 7
        elif ev < 30: pts += 3

    fcf = info.get("free_cashflow")
    mcap = info.get("market_cap")
    if fcf and mcap and mcap > 0:
        yield_ = fcf / mcap
        max_pts += 15
        if yield_ > 0.08: pts += 15
        elif yield_ > 0.05: pts += 12
        elif yield_ > 0.03: pts += 8
        elif yield_ > 0: pts += 4

    ps = info.get("ps_ratio")
    if ps is not None and ps > 0:
        max_pts += 10
        if ps < 2: pts += 10
        elif ps < 5: pts += 7
        elif ps < 10: pts += 4
        elif ps < 20: pts += 1

    if max_pts < 30:
        return None
    return round(pts / max_pts * 100, 1)


def raw_growth_score(info: dict, revenue_qoq: float | None = None) -> float | None:
    """Compute raw Growth score 0-100. Returns None if < 2 metrics."""
    pts = 0
    max_pts = 0

    rg = info.get("revenue_growth")
    if rg is not None:
        max_pts += 25
        if rg > 0.30: pts += 25
        elif rg > 0.20: pts += 20
        elif rg > 0.10: pts += 14
        elif rg > 0.05: pts += 8
        elif rg > 0: pts += 3

    eg = info.get("earnings_growth")
    if eg is not None:
        max_pts += 25
        if eg > 0.30: pts += 25
        elif eg > 0.20: pts += 20
        elif eg > 0.10: pts += 14
        elif eg > 0.05: pts += 8
        elif eg > 0: pts += 3

    feg = info.get("forward_eps_growth")
    if feg is not None:
        max_pts += 20
        if feg > 0.20: pts += 20
        elif feg > 0.10: pts += 15
        elif feg > 0.05: pts += 10
        elif feg > 0: pts += 5

    if revenue_qoq is not None:
        max_pts += 15
        if revenue_qoq > 0.10: pts += 15
        elif revenue_qoq > 0.05: pts += 12
        elif revenue_qoq > 0.02: pts += 8
        elif revenue_qoq > 0: pts += 4

    qeg = info.get("earnings_qoq_growth")
    if qeg is not None:
        max_pts += 15
        if qeg > 0.15: pts += 15
        elif qeg > 0.08: pts += 11
        elif qeg > 0.03: pts += 7
        elif qeg > 0: pts += 3

    if max_pts < 20:
        return None
    return round(pts / max_pts * 100, 1)


def raw_momentum_score(df: pd.DataFrame, indicators: dict) -> float:
    """Compute raw Momentum score 0-100. Always computable from price data."""
    pts = 0
    max_pts = 0
    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]

    if len(close) >= 21:
        ret_1m = float(close.iloc[-1]) / float(close.iloc[-21]) - 1
        max_pts += 25
        if ret_1m > 0.10: pts += 25
        elif ret_1m > 0.05: pts += 20
        elif ret_1m > 0.02: pts += 14
        elif ret_1m > 0: pts += 8
        elif ret_1m > -0.05: pts += 3

    if len(close) >= 63:
        ret_3m = float(close.iloc[-1]) / float(close.iloc[-63]) - 1
        max_pts += 25
        if ret_3m > 0.20: pts += 25
        elif ret_3m > 0.10: pts += 20
        elif ret_3m > 0.05: pts += 14
        elif ret_3m > 0: pts += 8
        elif ret_3m > -0.10: pts += 3

    rs = indicators.get("rs_rank", 50)
    max_pts += 25
    if rs >= 90: pts += 25
    elif rs >= 75: pts += 20
    elif rs >= 60: pts += 14
    elif rs >= 50: pts += 8
    elif rs >= 35: pts += 3

    pct_from_high = indicators.get("pct_from_52w_high", 50)
    max_pts += 25
    if pct_from_high <= 5: pts += 25
    elif pct_from_high <= 10: pts += 20
    elif pct_from_high <= 20: pts += 12
    elif pct_from_high <= 35: pts += 6

    if max_pts == 0:
        return 50.0
    return round(pts / max_pts * 100, 1)


# ── Pillar 1: Fundamentals (0-30) ───────────────────────────────────────────

def _valid_num(val) -> bool:
    """Check if a value is a valid, non-NaN number (not None, not NaN)."""
    if val is None:
        return False
    try:
        return not np.isnan(float(val))
    except (TypeError, ValueError):
        return False


def score_fundamentals(info: dict, zacks: dict | None = None,
                        beat_rate: dict | None = None,
                        extra_fund: dict | None = None,
                        analyst_data: dict | None = None) -> dict:
    """
    Business quality, balance sheet, growth trend, valuation, earnings consistency.
    Returns {score: int, max: 30, details: dict, bull_drivers: [], bear_risks: []}

    Components (30 pts max):
      Revenue growth    0-5
      Profit margins    0-5  (net + operating + gross)
      Balance sheet     0-5  (ROE + ROA + D/E + current ratio)
      Earnings growth   0-4
      Analyst consensus 0-4
      Valuation         0-5  (PEG + FCF yield + P/S + P/E + P/B)
      Beat rate         0-2  (EPS consistency)
    = 30 base  |  Zacks rank: ±5
    """
    score = 0
    details = {}
    bulls = []
    bears = []

    # Revenue Growth (0-5)
    rev_g = info.get("revenue_growth")
    if _valid_num(rev_g):
        if   rev_g > 0.20: pts = 5; bulls.append(f"Revenue +{rev_g:.0%} YoY")
        elif rev_g > 0.10: pts = 4
        elif rev_g > 0.05: pts = 2
        elif rev_g > 0.0:  pts = 1
        else:               pts = 0; bears.append(f"Revenue declining {rev_g:.1%}")
        score += pts
        details["revenue_growth"] = f"{rev_g:.1%} ({pts}/5)"

    # Ranking-flaw #11: QoQ vs YoY acceleration (+1 small bonus).
    # When quarterly growth exceeds yearly by ≥2pp, the business is
    # accelerating — a strong swing-trade signal. Read QoQ from extra_fund
    # (info.revenue_growth is YoY from yfinance). QoQ is stored as a ratio
    # (0.08 = 8%). TODO: wire rev_qoq through from callers (swing_trade.py
    # already computes it via get_quarterly_revenue_growth) — today we only
    # honour it when present in extra_fund.
    _ef_accel = extra_fund or {}
    rev_qoq = _ef_accel.get("revenue_qoq") or _ef_accel.get("rev_qoq")
    if _valid_num(rev_qoq) and _valid_num(rev_g):
        # Both stored as ratios; "+2pp" → 0.02 threshold.
        if rev_qoq > rev_g + 0.02:
            score += 1
            bulls.append(f"Revenue accelerating QoQ {rev_qoq:.1%} > YoY {rev_g:.1%}")
            details["revenue_accel"] = f"QoQ {rev_qoq:.1%} > YoY {rev_g:.1%} — accelerating (+1)"

    # Profit Margins (0-5) — net margin primary; operating + gross add context
    ef = extra_fund or {}
    margin = info.get("profit_margin") or ef.get("profit_margin")
    op_margin = info.get("operating_margin") or info.get("operatingMargins") or ef.get("operating_margin")
    gross_margin = info.get("gross_margin") or info.get("grossMargins") or ef.get("gross_margin")
    if _valid_num(margin):
        if   margin > 0.25: pts = 5; bulls.append(f"High net margin {margin:.0%}")
        elif margin > 0.15: pts = 4
        elif margin > 0.08: pts = 3
        elif margin > 0:    pts = 1
        else:                pts = 0; bears.append(f"Negative net margin {margin:.1%}")
        # Operating margin quality bonus: strong ops even if net is middling
        if op_margin and op_margin > 0.20 and pts < 5:
            pts = min(5, pts + 1)
            bulls.append(f"Strong operating margin {op_margin:.0%}")
        # Gross margin as quality signal
        if gross_margin and gross_margin > 0.60 and pts < 5:
            pts = min(5, pts + 1)
        score += pts
        margin_note = f"net {margin:.1%}"
        if op_margin: margin_note += f", op {op_margin:.1%}"
        if gross_margin: margin_note += f", gross {gross_margin:.1%}"
        details["profit_margin"] = f"{margin_note} ({pts}/5)"
    elif _valid_num(op_margin):
        # Fallback to operating margin if net not available
        if   op_margin > 0.20: pts = 4
        elif op_margin > 0.10: pts = 3
        elif op_margin > 0.05: pts = 2
        elif op_margin > 0:    pts = 1
        else:                   pts = 0; bears.append(f"Negative operating margin {op_margin:.1%}")
        score += pts
        details["profit_margin"] = f"op {op_margin:.1%} ({pts}/5)"

    # Balance Sheet — ROE + ROA + D/E + current ratio (0-5)
    ef = extra_fund or {}
    roe = info.get("roe") or info.get("returnOnEquity") or ef.get("roe")
    roa = info.get("roa") or info.get("returnOnAssets") or ef.get("roa")
    dte = info.get("debt_to_equity") or info.get("debtToEquity")
    cur = info.get("current_ratio") or info.get("currentRatio") or ef.get("current_ratio")
    bs_pts = 0
    if _valid_num(roe):
        if   roe > 0.15: bs_pts += 2; bulls.append(f"Strong ROE {roe:.0%}")
        elif roe > 0.08: bs_pts += 1
        elif roe < 0:    bears.append(f"Negative ROE {roe:.1%}")
    if _valid_num(roa):
        if   roa > 0.06: bs_pts += 1; bulls.append(f"Solid ROA {roa:.0%}")
        elif roa < 0:    bears.append(f"Negative ROA {roa:.1%}")
    if _valid_num(dte):
        if   dte < 80:  bs_pts += 1; bulls.append("Clean balance sheet")
        elif dte > 200: bears.append(f"High D/E {dte:.0f}%")
    if _valid_num(cur):
        if   cur >= 2.0: bs_pts += 1; bulls.append(f"Strong liquidity (current {cur:.1f}x)")
        elif cur < 1.0:  bears.append(f"Liquidity risk (current ratio {cur:.1f}x)")
    bs_pts = min(bs_pts, 5)
    score += bs_pts
    bs_note_parts = []
    if _valid_num(roe): bs_note_parts.append(f"ROE={roe:.1%}")
    if _valid_num(roa): bs_note_parts.append(f"ROA={roa:.1%}")
    if _valid_num(dte): bs_note_parts.append(f"D/E={dte:.0f}")
    if _valid_num(cur): bs_note_parts.append(f"CR={cur:.1f}")
    details["balance_sheet"] = (", ".join(bs_note_parts) or "N/A") + f" ({bs_pts}/5)"

    # Earnings Growth (0-4)
    eg = info.get("earnings_growth")
    # FINVIZ forward EPS growth as additional signal when trailing is missing
    eg_next_yr = ef.get("eps_growth_next_yr")    # from FINVIZ, stored as ratio (0.15 = 15%)
    eg_this_yr = ef.get("eps_growth_this_yr")
    if not _valid_num(eg) and _valid_num(eg_this_yr):
        eg = eg_this_yr  # fall back to FINVIZ current-year EPS growth
    if _valid_num(eg):
        if   eg > 0.30: pts = 4; bulls.append(f"Earnings +{eg:.0%}")
        elif eg > 0.15: pts = 3
        elif eg > 0:    pts = 1
        else:            pts = 0; bears.append(f"Earnings declining {eg:.1%}")
        score += pts
        details["earnings_growth"] = f"{eg:.1%} ({pts}/4)"
    # Forward EPS growth bonus: next year projections add conviction
    if _valid_num(eg_next_yr) and eg_next_yr > 0.20:
        score = min(score + 1, 20)
        bulls.append(f"Forward EPS growth +{eg_next_yr:.0%}")
        details["eps_growth_next_yr"] = f"+{eg_next_yr:.0%} (FINVIZ)"

    # Analyst Consensus (0-4)
    ef = extra_fund or {}
    _ad = analyst_data or {}
    rec = info.get("recommendation", "") or _ad.get("recommendation", "") or ef.get("recommendation", "")
    n_analysts = info.get("num_analysts", 0) or _ad.get("total_analysts", 0) or ef.get("num_analysts", 0)
    if rec:
        rec_l = rec.lower()
        if   "strong" in rec_l and "buy" in rec_l: pts = 4
        elif "buy"    in rec_l:                     pts = 3
        elif "hold"   in rec_l:                     pts = 1
        else:                                        pts = 0
        score += pts
        details["analyst_consensus"] = f"{rec} ({n_analysts} analysts) ({pts}/4)"

    # Valuation — PEG + FCF yield + P/S + P/E + P/B (0-5)
    val_pts = 0
    ef = extra_fund or {}
    peg  = info.get("peg_ratio") or info.get("pegRatio") or ef.get("peg")
    fcf  = info.get("free_cashflow") or info.get("freeCashflow")
    mcap = info.get("market_cap") or info.get("marketCap")
    ps   = info.get("price_to_sales_trailing_12_months") or info.get("ps_ratio") or info.get("priceToSalesTrailing12Months") or ef.get("ps")
    fpe  = info.get("forward_pe") or info.get("forwardPE") or ef.get("forward_pe") or ef.get("fwd_pe")
    pb   = info.get("price_to_book") or info.get("priceToBook") or ef.get("price_to_book")

    if _valid_num(peg) and peg > 0:
        if   peg < 1.0: val_pts += 2; bulls.append(f"Attractive PEG {peg:.1f}")
        elif peg < 2.0: val_pts += 1
        elif peg > 3.0: bears.append(f"Stretched PEG {peg:.1f}")

    if _valid_num(fcf) and _valid_num(mcap) and mcap > 0:
        fcf_yield = fcf / mcap
        if   fcf_yield > 0.06: val_pts += 2; bulls.append(f"High FCF yield {fcf_yield:.1%}")
        elif fcf_yield > 0.03: val_pts += 1
        elif fcf_yield < 0:    bears.append("Negative free cash flow")
        details["fcf_yield"] = f"{fcf_yield:.1%}"

    if _valid_num(ps):
        if   ps < 3:  val_pts += 1
        elif ps > 20: bears.append(f"High P/S {ps:.1f}×")

    # Forward P/E — cheaper than trailing usually implies growth priced in
    if _valid_num(fpe) and fpe > 0:
        if   fpe < 15: val_pts += 1; bulls.append(f"Low fwd P/E {fpe:.1f}")
        elif fpe > 40: bears.append(f"Expensive fwd P/E {fpe:.1f}")
        details["forward_pe"] = f"{fpe:.1f}"

    # Price-to-book — <1 = asset discount, >10 = priced for perfection
    if _valid_num(pb) and pb > 0:
        if   pb < 1.5: val_pts += 1; bulls.append(f"Low P/B {pb:.1f}")
        elif pb > 10:  bears.append(f"High P/B {pb:.1f}")
        details["price_to_book"] = f"{pb:.1f}"

    # EV/EBITDA and P/FCF — supplementary valuation from extra_fund
    ef = extra_fund or {}
    ev_ebitda = info.get("ev_to_ebitda") or ef.get("ev_ebitda")
    if ev_ebitda:
        if   ev_ebitda < 10:  val_pts += 1; bulls.append(f"EV/EBITDA {ev_ebitda:.1f}x — attractive")
        elif ev_ebitda > 40:  bears.append(f"EV/EBITDA {ev_ebitda:.1f}x — expensive")
        details["ev_ebitda"] = f"{ev_ebitda:.1f}x"

    p_fcf = ef.get("p_fcf")
    if p_fcf:
        if   p_fcf < 15: val_pts += 1; bulls.append(f"P/FCF {p_fcf:.1f}x — cheap cash flows")
        elif p_fcf > 50: bears.append(f"P/FCF {p_fcf:.1f}x — expensive")
        details["p_fcf"] = f"{p_fcf:.1f}x"

    val_pts = min(val_pts, 5)
    score += val_pts
    details["valuation"] = (f"PEG={peg:.2f}" if peg else "") + \
                             (f", FCF yield={details.get('fcf_yield','N/A')}" if fcf else "") + \
                             f" ({val_pts}/5)"

    # Estimate revisions — forward vs trailing EPS direction
    est_rev = ef.get("estimate_revision")
    if est_rev == "up_strong":
        score += 2; bulls.append("EPS estimates revised up strongly")
        details["estimate_revision"] = "Up strongly (+2/2)"
    elif est_rev == "up":
        score += 1; bulls.append("EPS estimates revised up")
        details["estimate_revision"] = "Up (+1/2)"
    elif est_rev == "down":
        score -= 1; bears.append("EPS estimates revised down")
        details["estimate_revision"] = "Down (-1/2)"
    elif est_rev == "flat":
        details["estimate_revision"] = "Flat (0/2)"

    # Institutional ownership — high = smart money present
    inst_pct = info.get("institutional_pct") or ef.get("institutional_pct")
    if inst_pct is not None:
        if   inst_pct > 70: score += 1; bulls.append(f"High institutional ownership {inst_pct:.0f}%")
        elif inst_pct < 15: bears.append(f"Very low institutional ownership {inst_pct:.0f}%")
        details["institutional_ownership"] = f"{inst_pct:.0f}%"

    # Active buyback cadence
    bk_yield = ef.get("buyback_yield")
    if bk_yield and bk_yield > 1.0:
        score += 1; bulls.append(f"Buyback {bk_yield:.1f}% of market cap/yr")
        details["buyback_yield"] = f"{bk_yield:.1f}%/yr"

    # EPS Beat Rate (0-2) — consistency of beating analyst estimates
    if beat_rate and beat_rate.get("beat_rate") is not None:
        br = beat_rate["beat_rate"]
        qtrs = beat_rate.get("quarters", 0)
        if qtrs >= 4:
            if   br >= 0.80: pts = 2; bulls.append(f"Beats EPS {br:.0%} of quarters")
            elif br >= 0.60: pts = 1
            else:             pts = 0; bears.append(f"Misses EPS {1-br:.0%} of quarters")
            score += pts
            details["beat_rate"] = f"{br:.0%} ({beat_rate['beats']}/{qtrs}Q) ({pts}/2)"

    # Phase 1: Analyst Revision Momentum (replaces Zacks Rank)
    # Score recent analyst upgrades/downgrades (10-day window) — fresher signal than Zacks
    rev_pts, rev_label = _score_analyst_revisions(analyst_data)
    score += rev_pts
    if rev_pts > 0:
        bulls.append(rev_label)
    elif rev_pts < 0:
        bears.append(rev_label)
    details["analyst_revisions"] = f"{rev_label} ({rev_pts}/5)"

    score = min(score, 20)

    return {
        "score":       score,
        "max":         30,
        "details":     details,
        "bull_drivers": bulls[:3],
        "bear_risks":   bears[:3],
    }


# ── Pillar 2: Optionality (0-20) ────────────────────────────────────────────

def score_optionality(df: pd.DataFrame, info: dict, sr: dict,
                      earnings: dict, news: dict,
                      options_data: dict | None = None,
                      rr_override: float | None = None,
                      options_intelligence: dict | None = None,
                      news_sentiment_score: dict | None = None) -> dict:
    """
    Catalyst presence, reward:risk ratio, upside scenario, options market intelligence.
    Returns {score: int, max: 20, rr_ratio: float, details: dict}

    Components (20 pts max):
      Reward:Risk ratio  0-10
      Catalyst quality   0-8  (earnings, news, analyst targets, true UOA sweeps, IV rank, IV skew)
      Upside scenario    0-4
      Smart money UOA    0-5  (independent of catalyst pool)

    rr_override: when provided (from compute_trade_plan), use plan's R:R instead of S/R estimate
    options_intelligence: rich dict from compute_options_intelligence() — uses FINVIZ chain Greeks
    """
    score = 0
    details = {}
    od = options_data or {}
    oi = options_intelligence or {}  # rich Greeks-derived signals from FINVIZ chain

    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    price = float(close.iloc[-1])
    support = sr.get("support", price * 0.95)
    resist  = sr.get("resistance", price * 1.05)

    # Reward:Risk ratio (0-10) — prefer plan's actual R:R over S/R estimate when available
    rr = rr_override if rr_override is not None else sr.get("rr_ratio", 0)
    if   rr >= 5.0: pts = 10
    elif rr >= 4.0: pts = 8
    elif rr >= 3.0: pts = 7
    elif rr >= 2.0: pts = 4
    elif rr >= 1.5: pts = 2
    else:           pts = 0
    score += pts
    details["reward_risk"] = f"{rr:.1f}:1 ({pts}/10)"

    # ── Catalyst quality ─────────────────────────────────────────────────────
    # UOA is scored separately (smart-money primary signal, not capped with regular catalysts)
    # Regular catalyst pool capped at 8 pts; UOA adds up to 5 independently.
    cat_pts = 0
    catalysts = []

    days_to_e = earnings.get("days_to_earnings")
    if days_to_e is not None and 10 <= days_to_e <= 30:
        cat_pts += 2; catalysts.append(f"Earnings in {days_to_e}d")

    if abs(news.get("score", 0)) >= 2:
        cat_pts += 1; catalysts.append(f"News ({news.get('bias', 'neutral')})")

    # Polygon NLP news momentum — stronger signal than Yahoo RSS
    _pns_opt = news_sentiment_score or {}
    if _pns_opt.get("momentum") == "bullish" and _pns_opt.get("source_score", 0) >= 0.35:
        _pns_pts = 2 if _pns_opt.get("source_score", 0) >= 0.6 else 1
        cat_pts += _pns_pts
        catalysts.append(f"Polygon NLP bullish ({_pns_opt.get('article_count', 0)} articles, {_pns_opt.get('source_score', 0):+.2f})")
    elif _pns_opt.get("momentum") == "bearish" and _pns_opt.get("source_score", 0) <= -0.35:
        cat_pts -= 1
        catalysts.append(f"Polygon NLP bearish ({_pns_opt.get('source_score', 0):+.2f})")

    target = info.get("target_mean_price")
    target_high = info.get("target_high_price")
    if target and target > price * 1.15:
        cat_pts += 1; catalysts.append(f"Analyst PT ${target:.0f}")
    # Analyst high target gives additional upside signal
    if target_high and target_high > price * 1.30 and target_high != target:
        cat_pts += 1; catalysts.append(f"Analyst high PT ${target_high:.0f}")

    # IV Rank: use FINVIZ chain ATM IV if available, else fall back to od.iv_rank
    iv_rank = oi.get("iv_rank_est") or od.get("iv_rank")
    if iv_rank is not None:
        if iv_rank < 30:
            cat_pts += 1; catalysts.append(f"IV {iv_rank:.0f}% (cheap entry)")
            details["iv_rank"] = f"{iv_rank:.0f}% — low, options cheap (+1)"
        elif iv_rank > 70:
            cat_pts -= 1  # expensive options reduce conviction
            details["iv_rank"] = f"{iv_rank:.0f}% — elevated, options expensive (-1)"
        else:
            details["iv_rank"] = f"{iv_rank:.0f}% — normal"

    # IV Skew: OTM put IV / OTM call IV from full chain
    # >1.3 = bearish skew (market pricing downside), <0.85 = bullish skew (upside being bought)
    iv_skew = oi.get("iv_skew", 1.0)
    if iv_skew and iv_skew > 0:
        if iv_skew < 0.85:
            cat_pts += 1; catalysts.append(f"Bullish IV skew ({iv_skew:.2f})")
            details["iv_skew"] = f"{iv_skew:.2f} — calls more bid than puts (bullish)"
        elif iv_skew > 1.3:
            cat_pts -= 1
            details["iv_skew"] = f"{iv_skew:.2f} — puts expensive vs calls (bearish skew)"
        else:
            details["iv_skew"] = f"{iv_skew:.2f} — neutral skew"

    # Put/Call ratio from actual chain volume (more accurate than a single pre-computed number)
    # Prefer chain-derived pc_ratio_vol, fall back to od.pc_ratio
    pc = oi.get("pc_ratio_vol") if oi.get("pc_ratio_vol") is not None else od.get("pc_ratio")
    pc_oi = oi.get("pc_ratio_oi")
    if pc is not None:
        if pc > 1.5:
            cat_pts += 1; catalysts.append(f"P/C flow {pc:.2f} (fear peak — contrarian buy)")
            details["pc_ratio"] = f"vol {pc:.2f}" + (f" / OI {pc_oi:.2f}" if pc_oi else "") + " — elevated fear"
        elif pc < 0.4:
            details["pc_ratio"] = f"vol {pc:.2f}" + (f" / OI {pc_oi:.2f}" if pc_oi else "") + " — complacency"
        else:
            details["pc_ratio"] = f"vol {pc:.2f}" + (f" / OI {pc_oi:.2f}" if pc_oi else "")

    # Gamma wall above: large call OI concentration above current price = breakout magnet
    gwa = oi.get("gamma_wall_above")
    if gwa and price > 0:
        pct_away = gwa.get("pct_away", 999)
        if pct_away is not None and 2 <= pct_away <= 8:
            cat_pts += 1
            catalysts.append(f"Gamma wall ${gwa['strike']} (+{pct_away:.1f}% away)")
            details["gamma_wall"] = f"Call gamma wall ${gwa['strike']} (+{pct_away:.1f}%) — breakout magnet (+1)"
        elif pct_away is not None and pct_away < 2:
            details["gamma_wall"] = f"Gamma wall ${gwa['strike']} very close ({pct_away:.1f}%) — pinning risk"
        elif gwa.get("strike"):
            details["gamma_wall"] = f"Call gamma wall ${gwa['strike']} (+{pct_away:.1f}%)"

    # Max pain proximity: if price trades through max pain expiry week = directional pin
    mp = oi.get("max_pain")
    if mp and price > 0:
        mp_pct = abs(price - mp) / price * 100
        details["max_pain"] = f"Max pain ${mp:.0f} ({'+' if mp > price else '-'}{mp_pct:.1f}% from price)"

    # PEAD as primary catalyst (high base rate — scored independently from UOA)
    pead_data = _post_earnings_drift(earnings, df, info)
    if pead_data.get("pead"):
        # Fix #29: catalyst freshness decay — Day 1 PEAD ≠ Day 5 PEAD
        # Decay multiplier: days 0-1 → 1.0, day 2 → 0.85, day 3 → 0.65, day 4 → 0.45, day 5+ → 0.25
        _dse = pead_data.get("days_since_earnings") or 0
        if _dse <= 1:
            _decay = 1.0
        elif _dse == 2:
            _decay = 0.85
        elif _dse == 3:
            _decay = 0.65
        elif _dse == 4:
            _decay = 0.45
        else:
            _decay = 0.25
        _pead_pts = round(4 * _decay)
        cat_pts += _pead_pts
        catalysts.append(f"PEAD: +{pead_data.get('eps_surprise_pct', 0):.0f}% EPS beat, {_dse}d drift (+{_pead_pts})")
        details["pead_opt"] = (f"Post-earnings drift active — +{pead_data.get('post_ret_pct', 0):.1f}% since beat, day {_dse} (+{_pead_pts}, decay {_decay:.2f})")
        details["pead_freshness"] = _decay

    cat_pts = min(max(cat_pts, 0), 8)  # regular catalyst pool capped at 8
    score += cat_pts

    # UOA scored separately — smart money has an edge, don't cap with regular catalysts
    # Prefer true UOA from chain (volume > 5× OI), fall back to boolean flag
    uoa_opt_pts = 0
    true_uoa_calls = oi.get("true_uoa_calls") or []
    true_uoa_puts  = oi.get("true_uoa_puts") or []
    has_uoa_from_chain = bool(true_uoa_calls)
    if has_uoa_from_chain:
        uoa_opt_pts = 5
        top_sweep = true_uoa_calls[0]
        _sv = top_sweep.get('vol') or 0
        _so = top_sweep.get('oi') or 0
        catalysts.append(f"Call sweep ${top_sweep.get('strike','?')}s ({_sv:.0f} vol/{_so:.0f} OI)")
        details["uoa"] = (f"Confirmed call sweep — ${top_sweep.get('strike','?')} strike, "
                          f"{_sv:.0f} vol vs {_so:.0f} OI (+5)")
    elif od.get("uoa"):
        uoa_opt_pts = 5
        catalysts.append("Unusual options activity (UOA)")
        details["uoa"] = "Detected — large OTM sweep (+5 smart money)"
    elif true_uoa_puts:
        top_put = true_uoa_puts[0]
        _pv = top_put.get('vol') or 0
        _po = top_put.get('oi') or 0
        details["uoa"] = (f"Put sweep detected — ${top_put.get('strike','?')} strike "
                          f"({_pv:.0f} vol vs {_po:.0f} OI — bearish flow, no pts)")
    score += uoa_opt_pts

    # Dominant options flow summary
    dom = oi.get("dominant_flow", "neutral")
    if dom != "neutral":
        details["options_flow"] = (f"Dominant: {dom.upper()} "
                                   f"(call vol {oi.get('call_vol_sum',0):.0f} / put vol {oi.get('put_vol_sum',0):.0f})")

    score = min(score, 20)  # apply overall optionality cap here (not inside catalyst block)
    details["catalysts"] = f"{', '.join(catalysts) if catalysts else 'None'} ({cat_pts}+{uoa_opt_pts} pts)"

    # Earnings surprise magnitude bonus — SKIP if PEAD already scored (avoids double-count)
    # PEAD (+4) already incorporates the beat magnitude; scoring surprise again inflates by 35%
    _pead_already_scored = pead_data.get("pead", False)
    opt_score = score  # alias for clarity in this block
    if not _pead_already_scored:
        try:
            er = earnings or {}
            surprise_pct = er.get("surprise_pct") or er.get("earnings_surprise_pct") or 0
            if isinstance(surprise_pct, (int, float)):
                if surprise_pct >= 20:
                    opt_score += 3   # massive beat → strong PEAD candidate
                elif surprise_pct >= 10:
                    opt_score += 2   # solid beat
                elif surprise_pct >= 5:
                    opt_score += 1   # moderate beat
                elif surprise_pct <= -10:
                    opt_score -= 2   # big miss → negative drift
            score = opt_score
        except Exception:
            pass
    else:
        # PEAD active: still penalize misses but don't add beat bonus (already in PEAD +4)
        try:
            er = earnings or {}
            surprise_pct = er.get("surprise_pct") or er.get("earnings_surprise_pct") or 0
            if isinstance(surprise_pct, (int, float)) and surprise_pct <= -10:
                score = max(0, score - 2)
        except Exception:
            pass

    # Upside scenario (0-4)
    upside_pct   = (resist - price) / price if price > 0 else 0
    downside_pct = (price - support) / price if price > 0 else 0
    if   upside_pct > 0.15: pts = 4
    elif upside_pct > 0.10: pts = 3
    elif upside_pct > 0.05: pts = 2
    else:                    pts = 0
    score += pts
    details["upside_scenario"] = f"+{upside_pct:.1%} to resist, -{downside_pct:.1%} to support ({pts}/4)"

    bull_case = round(resist * 1.05, 2)
    base_case = round(resist, 2)
    bear_case = round(support, 2)

    score = min(score, 20)

    return {
        "score":      score,
        "max":        20,
        "rr_ratio":   rr,
        "details":    details,
        "catalysts":  catalysts,
        "bull_case":  bull_case,
        "base_case":  base_case,
        "bear_case":  bear_case,
    }


# ── Pillar 3: Technicals (0-30) ─────────────────────────────────────────────

_SECTOR_NAME_TO_ETF = {
    "Technology":             "XLK",
    "Financial Services":     "XLF",
    "Healthcare":             "XLV",
    "Consumer Cyclical":      "XLY",
    "Consumer Defensive":     "XLP",
    "Communication Services": "XLC",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Utilities":              "XLU",
    "Basic Materials":        "XLB",
    "Real Estate":            "XLRE",
}


# ── Block H: Location-Aware Volume ──────────────────────────────────────────

def _location_aware_volume(df: pd.DataFrame, indicators: dict) -> dict:
    """
    Score volume spikes based on WHERE they occur relative to support/resistance.
    Volume at a key level = institutional activity. Volume at random price = noise.

    Returns:
        {
            "at_support": bool,      # volume spike within 2% of support
            "at_resistance": bool,   # volume spike within 2% of resistance
            "score": int,            # -2 to +3
            "label": str,            # description
        }
    """
    try:
        close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
        price = float(close.iloc[-1])

        # Get support, resistance, and RVOL from indicators
        support = float(indicators.get("support", price * 0.95))
        resistance = float(indicators.get("resistance", price * 1.05))
        rvol = float(indicators.get("rvol", 1.0))

        # Tolerance: within 2% of level
        support_lower = support * 0.98
        support_upper = support * 1.02
        resist_lower = resistance * 0.98
        resist_upper = resistance * 1.02

        at_support = support_lower <= price <= support_upper
        at_resistance = resist_lower <= price <= resist_upper

        score = 0
        label = ""

        if rvol >= 1.5:
            if at_support:
                score = 3
                label = "Accumulation at support"
            elif at_resistance:
                score = -2
                label = "Distribution at resistance"
            else:
                score = 1
                label = "Volume spike — no level context"
        else:
            score = 0
            label = "Normal volume"

        return {
            "at_support": at_support,
            "at_resistance": at_resistance,
            "score": score,
            "label": label,
        }
    except Exception:
        return {
            "at_support": False,
            "at_resistance": False,
            "score": 0,
            "label": "Unable to compute",
        }


# ── Block I: Enhanced Squeeze Score ─────────────────────────────────────────

def _enhanced_squeeze_score(info: dict, indicators: dict) -> dict:
    """
    Enhanced short squeeze probability score 0-10.
    Combines: short float %, days to cover, momentum direction, SI trend.

    Returns:
        {
            "squeeze_probability": int,  # 0-10
            "components": {
                "short_float_pts": int,      # 0-3
                "days_to_cover_pts": int,    # 0-3
                "momentum_pts": int,         # 0-2
                "si_trend_pts": int,         # 0-2
            },
            "label": str,
        }
    """
    try:
        # Short float percentage
        short_float = float(info.get("short_percent_of_float") or info.get("short_pct") or 0)
        short_float_pts = 0
        if short_float > 0.20:
            short_float_pts = 3
        elif short_float > 0.15:
            short_float_pts = 2
        elif short_float > 0.10:
            short_float_pts = 1

        # Days to cover (from short ratio)
        days_to_cover = float(info.get("short_ratio") or info.get("shortRatio") or 0)
        dtc_pts = 0
        if days_to_cover > 7:
            dtc_pts = 3
        elif days_to_cover > 5:
            dtc_pts = 2
        elif days_to_cover > 3:
            dtc_pts = 1

        # Momentum: RSI 50-70 + MACD bullish = squeeze firing
        rsi = float(indicators.get("rsi", 50))
        macd_bullish = indicators.get("macd_bullish", False)
        momentum_pts = 0
        if 50 <= rsi <= 70 and macd_bullish:
            momentum_pts = 2
        elif rsi > 40:
            momentum_pts = 1

        # SI Trend: if short float is high and volume is spiking, squeeze may fire
        rvol = float(indicators.get("rvol", 1.0))
        si_trend_pts = 0
        if short_float > 0.12 and rvol > 1.5:
            si_trend_pts = 2
        elif short_float > 0.10:
            si_trend_pts = 1

        # Total probability
        squeeze_probability = min(10, short_float_pts + dtc_pts + momentum_pts + si_trend_pts)

        # Label
        if squeeze_probability >= 8:
            label = "High squeeze probability"
        elif squeeze_probability >= 5:
            label = "Moderate squeeze"
        elif squeeze_probability >= 3:
            label = "Low squeeze"
        else:
            label = "No squeeze signal"

        return {
            "squeeze_probability": squeeze_probability,
            "components": {
                "short_float_pts": short_float_pts,
                "days_to_cover_pts": dtc_pts,
                "momentum_pts": momentum_pts,
                "si_trend_pts": si_trend_pts,
            },
            "label": label,
        }
    except Exception:
        return {
            "squeeze_probability": 0,
            "components": {
                "short_float_pts": 0,
                "days_to_cover_pts": 0,
                "momentum_pts": 0,
                "si_trend_pts": 0,
            },
            "label": "Unable to compute",
        }


# ── Block K: Sector Rotation Scoring ────────────────────────────────────────

def _sector_rotation_score(indicators: dict) -> dict:
    """
    Score based on sector money flow direction.
    Entering a sector with outflows = headwind. Inflows = tailwind.

    Returns:
        {
            "score": int,          # -2 to +2
            "sector_trend": str,   # "inflow" | "outflow" | "neutral"
            "label": str,
        }
    """
    try:
        sector_outperforming = indicators.get("sector_outperforming", False)
        sector_vs_spy = float(indicators.get("sector_vs_spy_pct", 0))

        score = 0
        sector_trend = "neutral"
        label = ""

        if sector_outperforming and sector_vs_spy > 3:
            score = 2
            sector_trend = "inflow"
            label = "Strong sector inflow"
        elif sector_outperforming:
            score = 1
            sector_trend = "inflow"
            label = "Sector tailwind"
        elif not sector_outperforming and sector_vs_spy < -3:
            score = -2
            sector_trend = "outflow"
            label = "Sector outflow — headwind"
        elif not sector_outperforming:
            score = -1
            sector_trend = "outflow"
            label = "Sector underperforming"
        else:
            # No sector data
            score = 0
            sector_trend = "neutral"
            label = "No sector data"

        return {
            "score": score,
            "sector_trend": sector_trend,
            "label": label,
        }
    except Exception:
        return {
            "score": 0,
            "sector_trend": "neutral",
            "label": "Unable to compute",
        }


def _candle_patterns(df: pd.DataFrame) -> dict:
    """Detect last-bar candlestick patterns. Returns {patterns: list[str], bias: int}."""
    try:
        o = df["Open"].squeeze() if isinstance(df["Open"], pd.DataFrame) else df["Open"]
        h = df["High"].squeeze() if isinstance(df["High"], pd.DataFrame) else df["High"]
        l = df["Low"].squeeze() if isinstance(df["Low"], pd.DataFrame) else df["Low"]
        c = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
        if len(c) < 3:
            return {"patterns": [], "bias": 0}

        o1, h1, l1, c1 = float(o.iloc[-1]), float(h.iloc[-1]), float(l.iloc[-1]), float(c.iloc[-1])
        o2, h2, l2, c2 = float(o.iloc[-2]), float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2])

        body1       = abs(c1 - o1)
        range1      = h1 - l1
        body2       = abs(c2 - o2)
        lower_wick1 = min(o1, c1) - l1
        upper_wick1 = h1 - max(o1, c1)

        if range1 < 1e-6 or body1 < 1e-9:
            return {"patterns": [], "bias": 0}

        patterns, bias = [], 0

        # Hammer: small body near top, lower wick >= 2× body, tiny upper wick
        if body1 < range1 * 0.35 and lower_wick1 >= body1 * 2.0 and upper_wick1 < body1 * 0.5:
            patterns.append("Hammer"); bias += 2

        # Shooting star: small body near bottom, upper wick >= 2× body, tiny lower wick
        if body1 < range1 * 0.35 and upper_wick1 >= body1 * 2.0 and lower_wick1 < body1 * 0.5:
            patterns.append("Shooting Star"); bias -= 2

        # Inside bar: current range fully inside prior range (coiling)
        if h1 < h2 and l1 > l2:
            patterns.append("Inside Bar"); bias += 1

        # Bullish engulfing: green bar engulfs prior red bar
        if c1 > o1 and c2 < o2 and c1 >= o2 and o1 <= c2:
            patterns.append("Bullish Engulfing"); bias += 2

        # Bearish engulfing: red bar engulfs prior green bar
        if c1 < o1 and c2 > o2 and o1 >= c2 and c1 <= o2:
            patterns.append("Bearish Engulfing"); bias -= 2

        # Doji: near-zero body (indecision / potential reversal)
        if body1 < range1 * 0.08:
            patterns.append("Doji")  # no bias alone, but signals a turning point

        return {"patterns": patterns, "bias": max(-3, min(3, bias))}
    except Exception:
        return {"patterns": [], "bias": 0}


def score_technicals(df: pd.DataFrame, regime: dict,
                     spy_close: "pd.Series | None" = None,
                     weekly_df: "pd.DataFrame | None" = None,
                     sector_etf_data: dict | None = None,
                     ticker: str = "",
                     info_sector: str = "",
                     info: dict | None = None) -> dict:
    """
    Trend (EMA stack + ADX), Volume (RVOL+OBV+CMF), Momentum (RSI+MACD+StochRSI+MFI),
    S/R + 52-week position, Relative Strength vs SPY + weekly alignment.
    Returns {score: int, max: 30, details: dict, indicators: dict}

    Components (30 pts base):
      Trend + ADX        0-10
      Volume + CMF       0-5
      Momentum composite 0-5
      S/R + 52w position 0-5
      RS + weekly        0-5  (legacy mode only — see note)
    = 30 base  |  Weekly alignment: ±2 bonus (capped at 30)
                 TV rating: ±3 bonus (applied in analyze_ticker)

    Audit ranking-flaw #4 — RS double-counting:
      Relative-strength sub-score (rs_pts + sector_rs_bonus, 0-6 pts) is
      intentionally NOT included in the Tech pillar when SCORING_MODE ==
      "normalized". RS is already counted as its own top-level pillar
      (see rs_score_norm). Including it inside score_technicals would
      double-count the same signal. In legacy mode the sub-score is kept
      for backward comparison. The weekly-EMA alignment signal remains
      inside Tech since it is an independent trend-structure indicator.
    """
    close  = df["Close"].squeeze()  if isinstance(df["Close"],  pd.DataFrame) else df["Close"]
    high   = df["High"].squeeze()   if isinstance(df["High"],   pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()    if isinstance(df["Low"],    pd.DataFrame) else df["Low"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    score = 0
    details = {}
    indicators = {}

    price = float(close.iloc[-1])

    # Daily change % — last close vs prior close (displayed on tile)
    try:
        _close_s = close.squeeze() if hasattr(close, "squeeze") else close
        if hasattr(_close_s, "iloc") and len(_close_s) >= 2:
            _prev_c = float(_close_s.iloc[-2])
            indicators["day_change_pct"] = round((price - _prev_c) / _prev_c * 100, 2) if _prev_c else 0.0
            indicators["prev_close"] = round(_prev_c, 2)
    except Exception:
        pass

    # VWAP — computed early so vwap_score block can use it, then scored (0-2)
    vwap_score_pts = 0
    try:
        _vwap_d = _vwap(df)
        if _vwap_d.get("vwap_20d"):
            indicators["vwap"]          = _vwap_d["vwap_20d"]
            indicators["above_vwap"]    = _vwap_d.get("above_vwap")
        if _vwap_d.get("avwap_swing_low"):
            indicators["avwap_swing_low"] = _vwap_d["avwap_swing_low"]
            indicators["above_avwap"]     = _vwap_d.get("above_avwap")

        # Score VWAP as institutional demand proxy:
        # price > 20d VWAP = buyers in control (+1)
        # price > anchored VWAP from swing low = demand from that base (+1)
        if _vwap_d.get("above_vwap"):
            vwap_score_pts += 1
        if _vwap_d.get("above_avwap"):
            vwap_score_pts += 1
        if vwap_score_pts > 0:
            score += vwap_score_pts
            details["vwap"] = (f"Price {'>' if _vwap_d.get('above_vwap') else '<'} VWAP20d "
                               f"{'& > aVWAP' if _vwap_d.get('above_avwap') else ''} "
                               f"(+{vwap_score_pts} institutional demand)")
        else:
            details["vwap"] = f"Price < VWAP — sellers in control (0)"
    except Exception:
        pass

    # ── 1. Trend + ADX (0-10) ────────────────────────────────────────────────
    ema8   = _ema(close, 8)
    ema20  = _ema(close, 20)
    ema21  = _ema(close, 21)
    ema50  = _ema(close, 50)
    ema100 = _ema(close, 100)
    ema200 = _ema(close, 200)
    ema5   = _ema(close, 5)
    ema13  = _ema(close, 13)
    e5   = float(ema5.iloc[-1])
    e8   = float(ema8.iloc[-1])
    e13  = float(ema13.iloc[-1])
    e20  = float(ema20.iloc[-1])
    e21  = float(ema21.iloc[-1])
    e50  = float(ema50.iloc[-1])
    e100 = float(ema100.iloc[-1]) if len(close) >= 100 else None
    e200 = float(ema200.iloc[-1]) if len(close) >= 200 else None

    # EMA stack alignment (5, 8, 13, 20, 50)
    _ema_stack = [e5, e8, e13, e20, e50]
    _bullish_stack = (price >= _ema_stack[0] and
                      all(_ema_stack[i] >= _ema_stack[i + 1]
                          for i in range(len(_ema_stack) - 1)))
    _bearish_stack = (price <= _ema_stack[0] and
                      all(_ema_stack[i] <= _ema_stack[i + 1]
                          for i in range(len(_ema_stack) - 1)))
    _emas_above = sum(1 for v in _ema_stack if price > v)

    if _bullish_stack:
        ema_signal = "BULLISH STACK"
    elif _bearish_stack:
        ema_signal = "BEARISH STACK"
    elif _emas_above >= 4:
        ema_signal = "MOSTLY BULLISH"
    elif _emas_above <= 1:
        ema_signal = "MOSTLY BEARISH"
    else:
        ema_signal = "MIXED"

    # ── 5/13 EMA System (Linda Raschke momentum) ──
    _e5_prev = float(ema5.iloc[-2]) if len(ema5) >= 2 else e5
    _e13_prev = float(ema13.iloc[-2]) if len(ema13) >= 2 else e13
    _ema5_above_13 = e5 > e13
    _ema5_cross_bull = _e5_prev <= _e13_prev and e5 > e13  # bullish cross
    _ema5_cross_bear = _e5_prev >= _e13_prev and e5 < e13  # bearish cross
    _ema5_slope_up = e5 > _e5_prev
    _ema13_slope_up = e13 > _e13_prev
    _price_above_5 = price > e5
    # Fibonacci ribbon: 5/13/21/34/55
    _e34 = float(close.ewm(span=34, adjust=False).mean().iloc[-1]) if len(close) >= 34 else e21
    _e55 = float(close.ewm(span=55, adjust=False).mean().iloc[-1]) if len(close) >= 55 else e50
    _fib_ribbon = [e5, e13, e21, _e34, _e55]
    _ribbon_bull = all(_fib_ribbon[i] >= _fib_ribbon[i+1] for i in range(len(_fib_ribbon)-1))
    _ribbon_bear = all(_fib_ribbon[i] <= _fib_ribbon[i+1] for i in range(len(_fib_ribbon)-1))
    _ribbon_spread = (e5 - _e55) / price * 100 if price > 0 else 0
    _ribbon_state = "EXPANDING" if _ribbon_spread > 3 else "TIGHT" if abs(_ribbon_spread) < 1 else "NORMAL"
    if _ribbon_bull:
        _ribbon_label = "BULL RIBBON"
    elif _ribbon_bear:
        _ribbon_label = "BEAR RIBBON"
    else:
        _ribbon_label = "MIXED"
    # Holy Grail setup (Raschke): ADX > 30, pullback to EMA20, price > prior bar high
    _holy_grail = False  # computed after ADX below

    adx_data = _adx(high, low, close, 14)
    adx_val  = adx_data["adx"]
    trending = adx_data["trending"]   # ADX > 25

    # Holy Grail completion: ADX > 30 + price near EMA20 + bounce
    _holy_grail = (adx_val >= 30 and abs(price - e20) / price < 0.02
                   and price > float(high.iloc[-2]) and _ema5_above_13)

    # ── Trend direction: multi-timeframe aware ──
    # A stock above rising 50 SMA with high RS is in an intermediate UPTREND
    # even if daily EMAs are bearish (pullback). This prevents misclassifying
    # strong pullback setups (like KMI RS 99 at 50 SMA) as "downtrend/short".
    _sma50_rising = False
    if len(close) >= 60:
        _sma50_10d_ago = float(close.iloc[-60:-50].mean()) if len(close) >= 60 else e50
        _sma50_rising = e50 > _sma50_10d_ago * 1.001  # rising by at least 0.1%

    if price > e8 > e21 > e50:
        trend_pts = 10 if trending else 8
        trend_dir = "strong uptrend"
    elif price > e21 > e50:
        trend_pts = 7 if trending else 5
        trend_dir = "uptrend"
    elif price > e50:
        trend_pts = 4
        trend_dir = "above long-term trend"
    elif price > e21:
        trend_pts = 2
        trend_dir = "mixed"
    elif price > e50 * 0.97 and _sma50_rising:
        # Price is near rising 50 SMA (within 3%) — this is a PULLBACK, not downtrend
        trend_pts = 3
        trend_dir = "pullback to rising 50 SMA"
    elif e200 is not None and price > e200 and _sma50_rising:
        # Below 50 SMA but above 200 SMA with rising 50 SMA — intermediate uptrend intact
        trend_pts = 2
        trend_dir = "deep pullback in uptrend"
    else:
        trend_pts = 0
        trend_dir = "downtrend"
    score += trend_pts
    adx_suffix = f", ADX {adx_val:.0f} {'↑trend' if trending else '↓choppy'}"
    details["trend"] = f"{trend_dir}{adx_suffix} ({trend_pts}/10)"
    indicators.update({
        # K4 (2026-05-10): EMA 5 + EMA 13 surfaced for Vinod's faster-stack
        # signal (5/13/21/50). Already computed at line 2775-2779 + driving
        # Holy Grail detection via ema5_above_13. Exposing raw values now so
        # the V2 Technicals tab can display them. Per OPERATING MINDSET
        # principle 7 (no knob-tweaking without evidence): NO score weight
        # added. They influence scoring ONLY through the existing Holy Grail
        # trigger (line 2839). After 30 days of signal data with these
        # logged, run a backtest with explicit score weight to decide.
        "ema5":  round(e5, 2),
        "ema8":  round(e8, 2),
        "ema13": round(e13, 2),
        "ema20": round(e20, 2),
        "ema21": round(e21, 2),
        "ema50": round(e50, 2),
        "ema100": round(e100, 2) if e100 is not None else None,
        "ema200": round(e200, 2) if e200 is not None else None,
        # Boolean flags used by strategies scorecard
        "above_20ema":  bool(price > e20),
        "above_50ema":  bool(price > e50),
        "above_200sma": bool(price > e200) if e200 is not None else False,
        "trend_direction": trend_dir,
        "adx": adx_val, "adx_plus_di": adx_data["plus_di"],
        "adx_minus_di": adx_data["minus_di"], "adx_trending": trending,
    })

    # Parabolic SAR — used for setup detection and displayed in signals
    sar_data = _parabolic_sar(high, low, close)
    indicators["sar"] = sar_data["sar"]
    indicators["sar_bullish"] = sar_data["bullish"]
    indicators["sar_flipped"] = sar_data["flipped"]

    # ── 2. Volume + CMF (0-5) ────────────────────────────────────────────────
    avg_vol  = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
    # Fix: use regular-session volume (today's total) for RVOL, not last-tick volume.
    # After hours, volume.iloc[-1] is often 0 or near-0. Use the most recent
    # bar with meaningful volume (>10% of avg) as "today's volume".
    _last_vol = float(volume.iloc[-1])
    if _last_vol < avg_vol * 0.1 and len(volume) >= 2:
        # Last bar has negligible volume (likely after-hours) — use prior bar
        for _vi in range(2, min(6, len(volume) + 1)):
            _candidate_vol = float(volume.iloc[-_vi])
            if _candidate_vol >= avg_vol * 0.1:
                _last_vol = _candidate_vol
                break
    rvol = _last_vol / avg_vol if avg_vol > 0 else 1.0
    obv      = _obv(close, volume)
    obv_slope = float(obv.iloc[-1] - obv.iloc[-5]) if len(obv) >= 5 else 0
    cmf_data = _cmf(high, low, close, volume, 20)
    cmf_val  = cmf_data["cmf"]
    accumulating = cmf_data["accumulating"]

    if rvol >= 2.0 and obv_slope > 0 and accumulating:    vol_pts = 5
    elif rvol >= 1.5 and obv_slope > 0:                   vol_pts = 4
    elif (rvol >= 1.5 or accumulating) and obv_slope > 0: vol_pts = 3
    elif rvol >= 1.2:                                      vol_pts = 2
    elif obv_slope > 0:                                    vol_pts = 1
    else:                                                  vol_pts = 0
    score += vol_pts
    details["volume"] = (f"RVOL {rvol:.1f}x, OBV {'↑' if obv_slope > 0 else '↓'}, "
                         f"CMF {cmf_val:+.2f} ({'accum' if accumulating else 'distrib' if cmf_data['distributing'] else 'neutral'}) "
                         f"({vol_pts}/5)")
    indicators.update({
        "rvol": round(rvol, 2), "obv_rising": obv_slope > 0,
        "cmf": cmf_val, "cmf_accumulating": accumulating,
    })

    # ── 3. Momentum composite (0-5): RSI + MACD + StochRSI + MFI ────────────
    rsi_s       = _rsi(close, 14)
    rsi_val     = float(rsi_s.iloc[-1]) if not rsi_s.empty else 50
    macd_line, signal_line, hist = _macd(close)
    macd_above  = float(hist.iloc[-1]) > 0 if not hist.empty else False

    # MACD golden/death cross detection — scan last 3 bars
    _gc = False
    _dc = False
    if len(macd_line) >= 4 and len(signal_line) >= 4:
        for _off in range(-3, 0):
            if _off - 1 < -len(macd_line):
                continue
            _mc = float(macd_line.iloc[_off])
            _mp = float(macd_line.iloc[_off - 1])
            _sc = float(signal_line.iloc[_off])
            _sp = float(signal_line.iloc[_off - 1])
            if _mc > _sc and _mp <= _sp:
                _gc = True
            if _mc < _sc and _mp >= _sp:
                _dc = True

    _hist_now  = float(hist.iloc[-1]) if not hist.empty else 0
    _hist_prev = float(hist.iloc[-2]) if len(hist) >= 2 else 0
    _hist_exp  = abs(_hist_now) > abs(_hist_prev)
    _macd_val  = float(macd_line.iloc[-1]) if not macd_line.empty else 0
    _sig_val   = float(signal_line.iloc[-1]) if not signal_line.empty else 0

    if _gc:
        macd_signal = "GOLDEN CROSS"
    elif _dc:
        macd_signal = "DEATH CROSS"
    elif _macd_val > _sig_val and _hist_exp and _hist_now > 0:
        macd_signal = "BULLISH MOMENTUM"
    elif _macd_val > _sig_val:
        macd_signal = "BULLISH"
    elif _macd_val < _sig_val and _hist_exp and _hist_now < 0:
        macd_signal = "BEARISH MOMENTUM"
    elif _macd_val < _sig_val:
        macd_signal = "BEARISH"
    else:
        macd_signal = "NEUTRAL"

    srsi        = _stoch_rsi(close)
    mfi_data    = _mfi(high, low, close, volume)
    mfi_val     = mfi_data["mfi"]

    mom_pts = 0
    # Best zone: RSI 50-70 (trending but not overbought) + MACD bullish + StochRSI confirming
    if 50 <= rsi_val <= 70 and macd_above and srsi["k_above_d"] and mfi_data["bullish"]:
        mom_pts = 5
    elif 50 <= rsi_val <= 70 and macd_above and srsi["k_above_d"]:
        mom_pts = 4
    elif 45 <= rsi_val <= 75 and macd_above:
        mom_pts = 3
    elif srsi["oversold"] and macd_above:
        mom_pts = 3  # Stoch oversold bounce
    elif 40 <= rsi_val <= 60:
        mom_pts = 2
    elif rsi_val > 80 or rsi_val < 25:
        mom_pts = 0
    else:
        mom_pts = 1
    score += mom_pts
    details["momentum"] = (f"RSI {rsi_val:.0f}, MACD {'↑' if macd_above else '↓'}, "
                           f"StochRSI K={srsi['k']:.0f}/D={srsi['d']:.0f}, "
                           f"MFI {mfi_val:.0f} ({mom_pts}/5)")
    indicators.update({
        "rsi": round(rsi_val, 1), "macd_bullish": macd_above,
        "macd_signal": macd_signal,
        "golden_cross": _gc,
        "death_cross": _dc,
        "ema_signal": ema_signal,
        "ema5": round(e5, 2),
        "ema13": round(e13, 2),
        "ema34": round(_e34, 2),
        "ema55": round(_e55, 2),
        "bullish_stack": _bullish_stack,
        "emas_above": _emas_above,
        # 5/13 EMA system (Raschke)
        "ema5_above_13": _ema5_above_13,
        "ema5_cross_bull": _ema5_cross_bull,
        "ema5_cross_bear": _ema5_cross_bear,
        "ema5_slope_up": _ema5_slope_up,
        "ema13_slope_up": _ema13_slope_up,
        "price_above_ema5": _price_above_5,
        "fib_ribbon": _ribbon_label,
        "fib_ribbon_state": _ribbon_state,
        "fib_ribbon_spread": round(_ribbon_spread, 2),
        "holy_grail_setup": _holy_grail,
        "stoch_rsi_k": srsi["k"], "stoch_rsi_d": srsi["d"],
        "stoch_oversold": srsi["oversold"], "stoch_overbought": srsi["overbought"],
        "stoch_k_above_d": srsi["k_above_d"],
        "mfi": mfi_val, "mfi_bullish": mfi_data["bullish"],
    })

    # ── 4. S/R + 52-week position (0-5) ──────────────────────────────────────
    sr = _support_resistance(df)
    pos52 = _52week_position(df)
    frac  = _williams_fractals(df)       # needed for S/R detail below

    sr_dist_support = (price - sr["support"]) / price if price > 0 else 1
    sr_dist_resist  = (sr["resistance"] - price) / price if price > 0 else 1

    sr_pts = 0
    if pos52["at_breakout"]:
        sr_pts = 5  # Within 2% of 52-week high = highest-probability setup (IBD Stage 2)
    elif pos52["near_52w_high"] and sr_dist_support < 0.05:
        sr_pts = 4  # Near 52w high AND near support
    elif sr_dist_support < 0.03 and sr_dist_resist > 0.05:
        sr_pts = 4
    elif pos52["near_52w_high"]:
        sr_pts = 3
    elif sr_dist_support < 0.05:
        sr_pts = 3
    elif sr_dist_resist > 0.08:
        sr_pts = 2
    elif pos52["near_52w_low"]:
        sr_pts = 0  # Near 52w low — danger zone
    else:
        sr_pts = 1

    # Stage 2 breakout bonus label
    stage2_label = " [Stage2 breakout!]" if pos52["stage2"] else ""
    # Williams Fractal annotations for S/R detail (frac already computed at line above)
    frac_note = ""
    if frac.get("active_high"):
        frac_note += f", FracHi ${frac['active_high']}"
    if frac.get("active_low"):
        frac_note += f", FracLo ${frac['active_low']}"
    score += sr_pts
    details["sr_structure"] = (f"Supp ${sr['support']}, Resist ${sr['resistance']}{stage2_label}{frac_note}, "
                               f"52w Hi ${pos52['high_52w']} (-{pos52['pct_from_high']:.1f}%) "
                               f"({sr_pts}/5)")
    indicators.update({
        "support": sr["support"], "resistance": sr["resistance"], "rr_ratio": sr["rr_ratio"],
        "high_52w": pos52["high_52w"], "low_52w": pos52["low_52w"],
        "pct_from_52w_high": pos52["pct_from_high"],
        "near_52w_high": pos52["near_52w_high"],
        "at_52w_breakout": pos52["at_breakout"],
        "near_52w_low": pos52["near_52w_low"],
        "stage2": pos52["stage2"],
    })

    # ── 5. Relative Strength vs SPY + sector ETF + weekly alignment (0-5) ───────
    rs_data = {"rs_rank": 50, "outperforming": False}
    if spy_close is not None and len(spy_close) > 0:
        rs_data = _relative_strength_vs_spy(close, spy_close)

    rs_rank = rs_data["rs_rank"]
    weekly_align = _weekly_ema_alignment(weekly_df)
    weekly_bull  = weekly_align.get("bullish", False)
    weekly_bear  = weekly_align.get("bearish", False)

    # Sector ETF RS: is stock outperforming its own sector? (+1 bonus if yes)
    sector_rs_bonus = 0
    sector_rs_label = ""
    _ticker_sector = info_sector or (info.get("sector", "") if info else "")
    _sector_etf_sym = _SECTOR_NAME_TO_ETF.get(_ticker_sector, "")
    if _sector_etf_sym and sector_etf_data and _sector_etf_sym in sector_etf_data:
        try:
            _etf_d = sector_etf_data[_sector_etf_sym]
            # Compare stock 63d return vs sector ETF 63d return
            _etf_ret = _etf_d.get("ret_63d") or _etf_d.get("vs_spy_pct", 0) or 0
            _stock_ret = rs_data.get("rs_63d_pct", 0) or 0
            if _stock_ret > _etf_ret + 2:   # outperforming sector by >2%
                sector_rs_bonus = 1
                sector_rs_label = f"Beating {_sector_etf_sym} by {_stock_ret - _etf_ret:.1f}%"
                indicators["outperforming_sector"] = True
                indicators["sector_etf"]           = _sector_etf_sym
            else:
                sector_rs_label = f"Lagging {_sector_etf_sym}"
                indicators["outperforming_sector"] = False
                indicators["sector_etf"]           = _sector_etf_sym
        except Exception:
            pass

    if rs_rank >= 80 and weekly_bull:  rs_pts = 5
    elif rs_rank >= 80:                rs_pts = 4
    elif rs_rank >= 65 and weekly_bull:rs_pts = 4
    elif rs_rank >= 65:                rs_pts = 3
    elif rs_rank >= 50 and weekly_bull:rs_pts = 3
    elif rs_rank >= 50:                rs_pts = 2
    else:                              rs_pts = 0
    # Audit ranking-flaw #4: strip RS-derived sub-score from Tech when normalized
    # mode is active — RS is owned by its own pillar (rs_score_norm). Preserve in
    # legacy mode for backward comparison. rs_pts/sector_rs_bonus still computed
    # so the "rel_strength" detail line stays populated for display.
    if SCORING_MODE == "legacy":
        score += rs_pts + sector_rs_bonus

    weekly_label = ""
    if weekly_align["aligned"]:
        weekly_label = f", W-EMA {'✓bull' if weekly_bull else '✗bear'}"
    sector_label = f", {sector_rs_label}" if sector_rs_label else ""
    details["rel_strength"] = (f"RS Rank {rs_rank}"
                                f"{'(outperforming SPY)' if rs_data['outperforming'] else ''}"
                                f"{sector_label}"
                                f"{weekly_label} ({rs_pts}+{sector_rs_bonus}/5)")
    indicators.update({
        "rs_rank": rs_rank, "outperforming_spy": rs_data["outperforming"],
        "rs_63d_pct": rs_data.get("rs_63d_pct", 0),
        "weekly_ema_bullish": weekly_bull, "weekly_ema_bearish": weekly_bear,
        "weekly_ema8":  weekly_align.get("ema8w"),
        "weekly_ema21": weekly_align.get("ema21w"),
    })

    # ── Additional indicators (not scored, displayed in signals tab) ──────────
    atr_s   = _atr(high, low, close, 14)
    atr_val = float(atr_s.iloc[-1]) if not atr_s.empty else 0
    atr_pct = (atr_val / price) * 100 if price > 0 else 0
    indicators["atr"]     = round(atr_val, 2)
    indicators["atr_pct"] = round(atr_pct, 2)

    # ── Supertrend (period=10, multiplier=3.0) ────────────────────────────────
    try:
        _st_period, _st_mult = 10, 3.0
        _hl2   = (df["High"] + df["Low"]) / 2.0
        _atr14 = _atr(df["High"], df["Low"], df["Close"], _st_period)
        _ub    = _hl2 + _st_mult * _atr14
        _lb    = _hl2 - _st_mult * _atr14
        # Final bands (carry-forward logic)
        _fub = _ub.copy(); _flb = _lb.copy()
        # Find first valid ATR bar (period warmup produces NaN)
        _fvi = _atr14.first_valid_index()
        _first_valid = int(_atr14.index.get_loc(_fvi)) if _fvi is not None else _st_period
        for _i in range(max(1, _first_valid + 1), len(df)):
            if pd.isna(_fub.iloc[_i-1]) or pd.isna(_flb.iloc[_i-1]):
                continue
            _fub.iloc[_i] = _ub.iloc[_i] if (not pd.isna(_ub.iloc[_i]) and (_ub.iloc[_i] < _fub.iloc[_i-1] or df["Close"].iloc[_i-1] > _fub.iloc[_i-1])) else _fub.iloc[_i-1]
            _flb.iloc[_i] = _lb.iloc[_i] if (not pd.isna(_lb.iloc[_i]) and (_lb.iloc[_i] > _flb.iloc[_i-1] or df["Close"].iloc[_i-1] < _flb.iloc[_i-1])) else _flb.iloc[_i-1]
        # Direction: 1 = bullish (price above lower band), -1 = bearish
        _st_dir = pd.Series(1, index=df.index)
        _st_val = _flb.copy()
        for _i in range(max(1, _first_valid + 1), len(df)):
            if pd.isna(_flb.iloc[_i]) or pd.isna(_fub.iloc[_i]):
                continue
            if _st_dir.iloc[_i-1] == 1:
                if df["Close"].iloc[_i] < _flb.iloc[_i]:
                    _st_dir.iloc[_i] = -1; _st_val.iloc[_i] = _fub.iloc[_i]
                else:
                    _st_dir.iloc[_i] = 1; _st_val.iloc[_i] = _flb.iloc[_i]
            else:
                if df["Close"].iloc[_i] > _fub.iloc[_i]:
                    _st_dir.iloc[_i] = 1; _st_val.iloc[_i] = _flb.iloc[_i]
                else:
                    _st_dir.iloc[_i] = -1; _st_val.iloc[_i] = _fub.iloc[_i]
        indicators["supertrend_bull"]  = bool(_st_dir.iloc[-1] == 1)
        _st_last = float(_st_val.iloc[-1])
        indicators["supertrend_value"] = round(_st_last, 2) if np.isfinite(_st_last) else None
        # Flip count: how many times direction changed in last 20 bars (stability)
        _flips = int((_st_dir.iloc[-20:].diff().abs() > 0).sum()) if len(df) >= 20 else 0
        indicators["supertrend_flips"] = _flips
    except Exception:
        indicators["supertrend_bull"]  = None
        indicators["supertrend_value"] = None
        indicators["supertrend_flips"] = None

    squeeze = _ttm_squeeze(df)
    indicators["squeeze_on"]      = squeeze["squeeze_on"]
    indicators["bars_in_squeeze"] = squeeze["bars_in_squeeze"]
    indicators["squeeze_fired"]   = squeeze["squeeze_fired"]
    indicators["squeeze_direction"] = squeeze.get("squeeze_direction", "neutral")

    # Phase 2F: Location-aware volume — institutional accumulation/distribution signal
    _lav = _location_aware_volume(df, indicators)
    indicators["lav_score"]     = _lav["score"]
    indicators["lav_label"]     = _lav["label"]
    indicators["at_support"]    = _lav["at_support"]
    indicators["at_resistance"] = _lav["at_resistance"]
    # Apply LAV to score: accumulation at support = +2, distribution at resistance = -2
    if _lav["score"] > 0:
        score += min(2, _lav["score"])
        details["location_volume"] = f"{_lav['label']} (+{min(2, _lav['score'])})"
    elif _lav["score"] < 0:
        score += max(-2, _lav["score"])
        details["location_volume"] = f"{_lav['label']} ({max(-2, _lav['score'])})"

    # Bollinger Band %B
    _, _, _, pct_b = _bollinger_bands(close, 20, 2.0)
    indicators["bb_pct_b"] = round(float(pct_b.iloc[-1]), 2) if not pct_b.empty else 0.5

    # ── VCP, Power Trend, Pocket Pivot (Fractals already computed above) ────
    vcp_data = _detect_vcp(df)
    pt_data  = _power_trend(df)
    pp_data  = _pocket_pivot(df)
    indicators.update({
        "vcp":              vcp_data["vcp"],
        "near_vcp":         vcp_data.get("near_vcp", False),
        "vcp_contractions": vcp_data.get("contractions", 0),
        "vcp_tightness":    vcp_data.get("tightness_pct"),
        "vcp_pivot":        vcp_data.get("pivot"),
        "vcp_vol_dry_up":   vcp_data.get("vol_dry_up", False),
        "power_trend":      pt_data["power_trend"],
        "power_days":       pt_data["power_days"],
        "pocket_pivot":     pp_data["pocket_pivot"],
        "pp_vol_ratio":     pp_data.get("pp_vol_ratio", 0),
        "fractal_high":     frac["active_high"],
        "fractal_low":      frac["active_low"],
        "fractal_highs":    frac["recent_highs"],
        "fractal_lows":     frac["recent_lows"],
    })

    # Fractal signal classification
    _fh = frac.get("active_high")
    _fl = frac.get("active_low")
    if _fh and price > _fh:
        fractal_signal = "BREAKOUT"
    elif _fl and abs(price - _fl) / _fl < 0.02:
        fractal_signal = "SUPPORT TEST"
    elif _fl and price < _fl:
        fractal_signal = "BREAKDOWN"
    elif _fh and _fl:
        fractal_signal = "BETWEEN S/R"
    else:
        fractal_signal = "NO DATA"
    indicators["fractal_signal"] = fractal_signal

    # Score bonuses for premium setups (applied after base score, capped at 30)
    if vcp_data["vcp"] and vcp_data.get("contractions", 0) >= 3:
        score = min(30, score + 2)
        _vdry = " + vol dry-up" if vcp_data.get("vol_dry_up") else ""
        details["vcp_bonus"] = f"+2 VCP ({vcp_data['contractions']} contractions, tight {vcp_data.get('tightness_pct','?')}%{_vdry})"
    elif vcp_data["vcp"]:
        score = min(30, score + 1)
        _vdry = " + vol dry-up" if vcp_data.get("vol_dry_up") else ""
        details["vcp_bonus"] = f"+1 VCP ({vcp_data['contractions']} contractions{_vdry})"
    elif vcp_data.get("near_vcp"):
        score = min(30, score + 1)
        _vdry = " + vol dry-up" if vcp_data.get("vol_dry_up") else ""
        details["vcp_bonus"] = f"+1 Near-VCP ({vcp_data['contractions']} range contractions, tight {vcp_data.get('tightness_pct','?')}%{_vdry})"

    if pt_data["power_trend"]:
        score = min(30, score + 2)
        details["power_trend_bonus"] = f"+2 Power Trend ({pt_data['power_days']}d institutional accumulation)"

    if pp_data["pocket_pivot"]:
        score = min(30, score + 1)
        details["pocket_pivot_bonus"] = f"+1 Pocket Pivot (vol {pp_data.get('pp_vol_ratio','?')}x down-day)"

    # TTM Squeeze breakout: compression just released with bullish price action
    if squeeze["squeeze_fired"] and price > float(indicators.get("ema8", price)):
        score = min(30, score + 2)
        details["squeeze_breakout_bonus"] = "+2 TTM Squeeze breakout (momentum compression released)"
    elif squeeze["squeeze_on"] and squeeze.get("bars_in_squeeze", 0) >= 5:
        # Deep compression building — flag as high-potential setup
        details["squeeze_building"] = f"TTM Squeeze: {squeeze['bars_in_squeeze']} bars compressed (energy building)"

    # Sector ETF context — is this ticker's sector outperforming?
    if sector_etf_data and ticker:
        from data_fetcher import _TICKER_TO_SECTOR
        sector_etf = _TICKER_TO_SECTOR.get(ticker)
        # Fallback: map sector name from yfinance info to ETF symbol
        if not sector_etf and info_sector:
            sector_etf = _SECTOR_NAME_TO_ETF.get(info_sector)
        if sector_etf and sector_etf in sector_etf_data:
            sd = sector_etf_data[sector_etf]
            indicators["sector_etf"]             = sector_etf
            indicators["sector_outperforming"]   = sd.get("outperforming", False)
            indicators["sector_vs_spy_pct"]      = sd.get("vs_spy_pct", 0)
            indicators["sector_rank"]            = sd.get("rank")

            # Fix #5: Sector underperformance penalty — sector ETF return < SPY return by 3%+
            # Uses vs_spy_pct which is (sector_perf - spy_perf); negative = lagging
            _sector_vs_spy = sd.get("vs_spy_pct", 0) or 0
            if _sector_vs_spy < -3.0:
                score = max(0, score - 3)
                details["sector_underperform"] = (
                    f"Sector lagging SPY by {abs(_sector_vs_spy):.1f}% (-3 conviction penalty)"
                )
                indicators["sector_underperform"] = True
            else:
                indicators["sector_underperform"] = False

    # Weekly alignment stored for setup detection
    indicators["weekly_aligned"] = weekly_align.get("aligned", False)

    # ── Block H: Location-aware volume ────────────────────────────────────────
    loc_vol = _location_aware_volume(df, indicators)
    indicators["loc_vol_score"] = loc_vol["score"]
    indicators["loc_vol_label"] = loc_vol["label"]
    indicators["loc_vol_at_support"] = loc_vol["at_support"]
    indicators["loc_vol_at_resistance"] = loc_vol["at_resistance"]

    # ── Block I: Enhanced squeeze score (0-10) ───────────────────────────────
    # Uses real info dict (short float, DTC) when available for accurate squeeze scoring.
    esq = _enhanced_squeeze_score(info or {}, indicators)
    indicators["enhanced_squeeze_probability"] = esq.get("squeeze_probability", 0)
    indicators["enhanced_squeeze_label"] = esq.get("label", "Unable to compute")
    if esq.get("components"):
        indicators["enhanced_squeeze_components"] = esq["components"]

    # Block K removed — sector rotation scoring is handled by B9 below (richer, avoids double-count)
    # Preserve indicators for display only (no score contribution here)
    if "sector_outperforming" in indicators:
        sec_rot = _sector_rotation_score(indicators)
        indicators["sector_rotation_score"] = sec_rot["score"]
        indicators["sector_rotation_label"] = sec_rot["label"]
        indicators["sector_rotation_trend"] = sec_rot["sector_trend"]

    # VWAP will be injected into indicators by analyze_ticker after this call
    score = min(score, 30)

    # ── Weekly alignment bonus: ±2 (applied unconditionally, capped at 30) ────
    if weekly_bull:
        score = min(30, score + 2)
        details["weekly_bonus"] = "+2 (weekly EMA bull-aligned)"
    elif weekly_bear:
        score = max(0, score - 2)
        details["weekly_bonus"] = "-2 (weekly EMA bear-aligned)"

    # B5: Trend Age — score how long the current EMA bull stack has been in place
    trend_age_score = 0
    trend_age_label = ""
    try:
        ema8_s  = close.ewm(span=8,  adjust=False).mean()
        ema21_s = close.ewm(span=21, adjust=False).mean()
        ema50_s = close.ewm(span=50, adjust=False).mean()
        stack_bull = (ema8_s > ema21_s) & (ema21_s > ema50_s) & (close > ema8_s)
        trend_age_bars = 0
        for i in range(len(stack_bull) - 1, -1, -1):
            if stack_bull.iloc[i]:
                trend_age_bars += 1
            else:
                break
        if trend_age_bars >= 3 and trend_age_bars <= 15:
            trend_age_score = 2
            trend_age_label = f"Young trend ({trend_age_bars}d)"
        elif trend_age_bars > 15 and trend_age_bars <= 40:
            trend_age_score = 1
            trend_age_label = f"Maturing trend ({trend_age_bars}d)"
        elif trend_age_bars > 40:
            trend_age_score = -1
            trend_age_label = f"Mature trend ({trend_age_bars}d — late entry risk)"
        indicators["trend_age_bars"]  = trend_age_bars
        indicators["trend_age_label"] = trend_age_label
    except Exception:
        pass
    score += trend_age_score
    details["trend_age"] = trend_age_label

    # B9: Sector rotation momentum (inflows/outflows last 5 days)
    rotation_score = 0
    rotation_label = ""
    if sector_etf_data and info_sector:
        sector_d = None
        for etf, d in sector_etf_data.items():
            if etf == "SPY" or etf.startswith("_"):
                continue
            if (d.get("sector", "").lower() in info_sector.lower()
                    or info_sector.lower() in d.get("sector", "").lower()):
                sector_d = d
                break
        if sector_d:
            vs_spy       = sector_d.get("vs_spy_pct", 0)
            outperforming = sector_d.get("outperforming", False)
            rank          = sector_d.get("rank", 6)
            if outperforming and rank <= 3:
                rotation_score = 2
                rotation_label = f"Sector inflows (rank #{rank} vs SPY +{vs_spy:.1f}%)"
            elif outperforming:
                rotation_score = 1
                rotation_label = f"Sector outperforming SPY +{vs_spy:.1f}%"
            elif vs_spy < -3:
                rotation_score = -2
                rotation_label = f"Sector outflows (vs SPY {vs_spy:.1f}%)"
            elif vs_spy < 0:
                rotation_score = -1
                rotation_label = f"Sector lagging SPY {vs_spy:.1f}%"
            details["sector_rotation"] = rotation_label
    score += rotation_score

    # SMC signals
    smc_result = score_smc(df, float(close.iloc[-1]), indicators)
    score += min(5, max(-2, smc_result["score"]))
    details["smc"]           = smc_result["details"]
    details["smc_direction"] = smc_result["smc_direction"]

    # ── New signal components ─────────────────────────────────────────────────
    rsi_vals = rsi_s  # alias for new signal blocks

    # RSI Divergence detection
    rsi_divergence = 0
    try:
        if len(close) >= 20:
            # Bullish divergence: price lower low, RSI higher low (last 10 bars)
            price_low_recent = float(close.iloc[-5:].min())
            price_low_prior  = float(close.iloc[-15:-5].min())
            rsi_low_recent   = float(rsi_vals.iloc[-5:].min())
            rsi_low_prior    = float(rsi_vals.iloc[-15:-5].min())
            if price_low_recent < price_low_prior and rsi_low_recent > rsi_low_prior + 3:
                rsi_divergence = 3   # bullish divergence: strong signal
            # Bearish divergence: price higher high, RSI lower high
            price_hi_recent  = float(close.iloc[-5:].max())
            price_hi_prior   = float(close.iloc[-15:-5].max())
            rsi_hi_recent    = float(rsi_vals.iloc[-5:].max())
            rsi_hi_prior     = float(rsi_vals.iloc[-15:-5].max())
            if price_hi_recent > price_hi_prior and rsi_hi_recent < rsi_hi_prior - 3:
                rsi_divergence = -3  # bearish divergence: reversal warning
    except Exception:
        pass

    # Breakout volume validation
    breakout_vol_score = 0
    breakout_vol_ratio = 0.0
    try:
        if len(df) >= 21:
            vol_20d_avg = float(df["Volume"].iloc[-21:-1].mean())
            today_vol   = float(df["Volume"].iloc[-1])
            today_close = float(close.iloc[-1])
            today_open  = float(df["Open"].iloc[-1]) if "Open" in df.columns else today_close
            near_52w_high = float(close.max()) * 0.98
            if vol_20d_avg > 0:
                breakout_vol_ratio = round(today_vol / vol_20d_avg, 2)
            # Breakout candle: near 52w high, high volume, closed in upper half
            if today_close >= near_52w_high and vol_20d_avg > 0:
                vol_ratio = today_vol / vol_20d_avg
                candle_range = float(df["High"].iloc[-1]) - float(df["Low"].iloc[-1])
                close_position = (today_close - float(df["Low"].iloc[-1])) / candle_range if candle_range > 0 else 0.5
                if vol_ratio >= 1.5 and close_position >= 0.6:
                    breakout_vol_score = 3   # valid breakout: high volume + strong close
                elif vol_ratio >= 1.5:
                    breakout_vol_score = 1   # volume present but weak close
                elif today_close >= near_52w_high and vol_ratio < 0.8:
                    breakout_vol_score = -2  # fake breakout: near high but low volume
    except Exception:
        pass
    indicators["breakout_vol_ratio"] = breakout_vol_ratio

    # VWAP positioning score
    vwap_score = 0
    try:
        if "vwap" in indicators and indicators["vwap"] and close is not None and len(close) >= 1:
            cur_price = float(close.iloc[-1])
            vwap_val  = float(indicators["vwap"]) if not isinstance(indicators["vwap"], dict) else float(indicators["vwap"].get("current", 0))
            if vwap_val > 0:
                pct_vs_vwap = (cur_price - vwap_val) / vwap_val * 100
                if pct_vs_vwap >= 2.0:
                    vwap_score = 2    # clearly above VWAP
                elif pct_vs_vwap >= 0:
                    vwap_score = 1    # above VWAP
                elif pct_vs_vwap >= -1.5:
                    vwap_score = -1   # slightly below
                else:
                    vwap_score = -2   # clearly below VWAP
    except Exception:
        pass

    # Trend exhaustion: ADX declining + RSI declining + volume declining on rallies
    exhaustion_penalty = 0
    try:
        if len(df) >= 15:
            adx_vals_raw = indicators.get("adx", 20)
            adx_now  = float(adx_vals_raw) if isinstance(adx_vals_raw, (int, float)) else 20.0
            rsi_now  = float(rsi_vals.iloc[-1]) if len(rsi_vals) >= 1 else 50.0
            rsi_5ago = float(rsi_vals.iloc[-6]) if len(rsi_vals) >= 6 else rsi_now
            vol_5d   = float(df["Volume"].iloc[-5:].mean()) if len(df) >= 5 else 0
            vol_10d  = float(df["Volume"].iloc[-15:-5].mean()) if len(df) >= 15 else vol_5d
            price_up = float(close.iloc[-1]) > float(close.iloc[-5]) if len(close) >= 5 else False
            adx_declining = adx_now < 25 and rsi_now < rsi_5ago - 3
            vol_declining_on_rally = price_up and vol_5d < vol_10d * 0.85
            if adx_declining and vol_declining_on_rally:
                exhaustion_penalty = -4   # strong exhaustion signal
            elif adx_declining or vol_declining_on_rally:
                exhaustion_penalty = -2   # partial exhaustion
    except Exception:
        pass

    # Support retest counter — penalize exhausted levels
    retest_penalty = 0
    try:
        if len(close) >= 30:
            support_level = sr.get("support", float(close.iloc[-30:].quantile(0.15)))
            cur = float(close.iloc[-1])
            tolerance = support_level * 0.02  # 2% band
            retests = sum(
                1 for i in range(len(close) - 30, len(close))
                if abs(float(close.iloc[i]) - support_level) <= tolerance
            )
            if retests >= 8:
                retest_penalty = -3
            elif retests >= 5:
                retest_penalty = -2
            elif retests >= 3:
                retest_penalty = -1
    except Exception:
        pass

    # Gap analysis: unfilled gaps above/below act as hard resistance/support
    gap_score = 0
    try:
        if len(df) >= 10:
            cur_price = float(close.iloc[-1])
            # Look for gap up (bullish): previous close much lower than current open
            # Look for gap down (bearish): previous close much higher than current open
            gaps_above = []  # unfilled gaps above current price (resistance)
            gaps_below = []  # unfilled gaps below current price (support)
            for i in range(max(1, len(df)-20), len(df)-1):
                prev_close = float(close.iloc[i-1]) if i > 0 else cur_price
                cur_open   = float(df["Open"].iloc[i]) if "Open" in df.columns else prev_close
                gap_pct    = abs(cur_open - prev_close) / prev_close * 100 if prev_close > 0 else 0
                if gap_pct >= 1.5:  # meaningful gap >= 1.5%
                    gap_mid = (cur_open + prev_close) / 2
                    if gap_mid > cur_price:
                        gaps_above.append(gap_mid)
                    else:
                        gaps_below.append(gap_mid)
            # Nearby unfilled gap above = resistance headwind (negative)
            if gaps_above and min(gaps_above) < cur_price * 1.05:
                gap_score -= 2
            # Nearby unfilled gap below = support cushion (positive)
            if gaps_below and max(gaps_below) > cur_price * 0.96:
                gap_score += 2
    except Exception:
        pass

    # ── Candle pattern scoring ────────────────────────────────────────────────
    candle_data   = _candle_patterns(df)
    candle_score  = candle_data["bias"]  # ±1–3 pts
    candle_labels = candle_data["patterns"]
    indicators["candle_patterns"] = candle_labels

    # ── ADX +DI/-DI directional scoring (±2 pts) ─────────────────────────────
    # Requires ADX > 25 (trending market); pure directional pressure signal
    adx_di_score = 0
    _pdi     = indicators.get("adx_plus_di", 50.0)
    _mdi     = indicators.get("adx_minus_di", 50.0)
    _adx_val = indicators.get("adx", 0.0)   # renamed to avoid shadowing module-level _adx()
    if _adx_val > 25:
        if _pdi > _mdi * 1.25:
            adx_di_score = 2   # strong bull directional pressure
        elif _pdi > _mdi:
            adx_di_score = 1   # mild bull
        elif _mdi > _pdi * 1.25:
            adx_di_score = -2  # strong bear directional pressure
        elif _mdi > _pdi:
            adx_di_score = -1  # mild bear

    # ── Pullback context adjustment ──
    # When a stock is pulling back to a rising 50 SMA, the short-term bearish
    # signals (low RVOL, RSI declining, below VWAP, MACD down) are EXPECTED
    # and should not be penalized. The pullback IS the setup.
    pullback_bonus = 0
    if trend_dir in ("pullback to rising 50 SMA", "deep pullback in uptrend"):
        # Cancel unfair penalties for pullback characteristics
        _unfair_penalties = abs(min(0, vwap_score)) + abs(min(0, exhaustion_penalty)) + abs(min(0, gap_score)) + abs(min(0, adx_di_score))
        pullback_bonus = min(8, _unfair_penalties)  # restore up to 8 pts
        # Bonus for declining volume on pullback (healthy, not distribution)
        if rvol < 0.8:
            pullback_bonus += 2  # volume dry-up = no selling pressure
        # Bonus for RS rank >= 80 in a pullback (strongest names bounce)
        if rs_rank >= 80:
            pullback_bonus += 2
        # Bonus for squeeze building during pullback (energy for breakout)
        if indicators.get("squeeze_on", False):
            pullback_bonus += 1

    # New signal adjustments
    tech_max = 38
    score += (rsi_divergence + breakout_vol_score + vwap_score
              + exhaustion_penalty + retest_penalty + gap_score
              + candle_score + adx_di_score + pullback_bonus)
    score = max(0, min(tech_max, score))

    details["rsi_divergence"]     = rsi_divergence
    details["breakout_vol_score"] = breakout_vol_score
    details["vwap_score"]         = vwap_score
    details["exhaustion_penalty"] = exhaustion_penalty
    details["retest_penalty"]     = retest_penalty
    details["gap_score"]          = gap_score
    details["candle_patterns"]    = f"{', '.join(candle_labels) if candle_labels else 'None'} ({candle_score:+d})"
    details["adx_di_score"]       = f"+DI {_pdi:.0f} / -DI {_mdi:.0f} ADX {_adx_val:.0f} ({adx_di_score:+d})"

    return {
        "score":      score,
        "max":        38,
        "details":    details,
        "indicators": indicators,
        "sr":         sr,
        "smc_result": smc_result,
    }


# ── Pillar 4: Sentiment (0-10) ──────────────────────────────────────────────

def score_sentiment(news: dict, insider: dict, info: dict,
                    stocktwits: dict | None = None,
                    df: "pd.DataFrame | None" = None,
                    indicators: dict | None = None,
                    earnings: dict | None = None,
                    congressional: dict | None = None,
                    reddit_wsb: dict | None = None,
                    borrow_data: dict | None = None,
                    uoa_data: dict | None = None,
                    news_sentiment_score: dict | None = None) -> dict:
    """
    News + StockTwits social sentiment, insider activity, short interest, unusual options.
    Returns {score: int, max: 10, details: dict}

    Components (10 pts max):
      News            0-3  (Polygon NLP-weighted if available, else Yahoo RSS word-match)
      Insider         0-3
      Short interest  0-2
    Bonus (up to cap):
      Unusual Options Activity +2 (call flow) or -1 (put flow)
    polygon_news_score: from compute_news_sentiment_score() — real NLP, source-weighted, recency-decayed
    """
    score = 0
    details = {}

    # News sentiment (0-3) — prefer Polygon per-article NLP (source-weighted, recency-decayed)
    # over simple Yahoo RSS word-matching (low-signal, capped at 1 previously).
    pns = news_sentiment_score or {}
    if pns.get("score") is not None and pns.get("article_count", 0) >= 2:
        # Polygon NLP: real sentiment from Bloomberg, Reuters, CNBC etc.
        poly_score = int(pns["score"])   # -1 to 3
        pts = max(0, poly_score)         # floor at 0 (penalty handled below if heavy negative)
        score += pts
        momentum_tag = f", {pns['momentum']} momentum" if pns.get("momentum") != "neutral" else ""
        breaking_tag = " [BREAKING]" if pns.get("breaking") else ""
        details["news"] = (f"Polygon NLP: {pns.get('article_count',0)} articles, "
                           f"score {poly_score}/3{momentum_tag}{breaking_tag} ({pts}/3) — "
                           f"{pns.get('details','')}")
        # Penalty for heavy negative Polygon sentiment (when score = -1)
        if poly_score < 0:
            score = max(0, score + poly_score)
    else:
        # Fallback: Yahoo RSS word-matching (low-signal — cap at 1 pt)
        news_score = news.get("score", 0)
        pts = 1 if news_score >= 1 else 0
        score += pts
        details["news"] = f"Yahoo RSS: {news.get('bias','neutral')} ({pts}/1) — low signal, Polygon unavailable"

    # StockTwits social sentiment — display only, no scoring (crowd noise)
    st = stocktwits or {}
    bull_pct = st.get("bull_pct", 50)
    st_pts = 0  # no score contribution
    wcount = st.get("watchlist_count", 0)
    trending_label = " 🔥trending" if st.get("trending") else ""
    details["stocktwits"] = (f"{bull_pct:.0f}% bull{trending_label}"
                              f" ({wcount//1000:.0f}K watchlists)" if wcount else
                              f"{bull_pct:.0f}% bull{trending_label}") + " (display only)"

    # Insider activity (0-3) — Phase 1D: CEO/CFO only for max, dollar-weighted, recency-aware
    ins_sent      = insider.get("sentiment", "neutral")
    ins_buys      = insider.get("buys", 0)
    ins_sells     = insider.get("sells", 0)
    ins_ceo_buy   = insider.get("ceo_buy", False) or insider.get("cfo_buy", False)
    ins_total_val = insider.get("total_buy_value", 0) or 0
    ins_max_val   = insider.get("max_single_buy", 0) or 0
    ins_days_ago  = insider.get("days_since_last", 30)  # default 30 when field missing (not same as stale)

    # Phase 1D: Only CEO/CFO buys get max 3 pts; directors capped at 2
    # Require transaction within 14 days for full credit
    if ins_days_ago > 90:
        pts = 0  # stale data — no credit
    elif ins_ceo_buy and ins_max_val >= 100_000:
        pts = 3   # C-suite buying with material $ = highest conviction
    elif ins_ceo_buy:
        pts = 2   # C-suite buy but small amount
    elif ins_sent == "bullish" and ins_total_val >= 250_000:
        pts = 2   # Director/other buying with material value (capped at 2)
    elif ins_sent == "bullish" and ins_buys >= 3:
        pts = 2   # Multiple insider buys (value data may be unavailable from SEC)
    elif ins_sent == "bullish":
        pts = 1   # Bullish sentiment but small/non-exec
    elif ins_sent == "neutral":
        pts = 0   # Phase 1B: neutral = no free points (was 1)
    else:
        pts = 0   # bearish (net selling)
    score += pts
    val_note = f" ${ins_total_val/1000:.0f}K" if ins_total_val >= 10_000 else ""
    ceo_note = " CEO/CFO" if ins_ceo_buy else ""
    age_note = f" {ins_days_ago}d ago" if ins_days_ago < 999 else ""
    details["insider"] = (f"{ins_sent}{ceo_note} (buys:{ins_buys}"
                           f" sells:{ins_sells}{val_note}{age_note}) ({pts}/3)")

    # Short interest (0-2) — Phase 2E: headwind only, no squeeze bonus
    # Low SI = clean sailing; High SI = headwind (shorts are resistance to rally)
    short_pct = info.get("short_pct") or info.get("shortPercentOfFloat")
    if short_pct is None and borrow_data:
        _bd_sf = borrow_data.get("short_float_pct")
        if _bd_sf is not None:
            short_pct = _bd_sf / 100.0 if _bd_sf > 1 else _bd_sf
    if short_pct is not None:
        if   short_pct < 0.03:  pts = 2   # low short interest — clean
        elif short_pct < 0.08:  pts = 1   # moderate — some headwind
        elif short_pct < 0.15:  pts = 0   # elevated — real headwind
        else:                    pts = 0   # high SI — shorts often right, pure headwind
        score += pts
        si_label = "low" if short_pct < 0.05 else "elevated headwind" if short_pct > 0.15 else "moderate"
        details["short_interest"] = f"{short_pct:.1%} ({si_label}) ({pts}/2)"
    else:
        score += 0  # Phase 1B: missing data = no free points
        details["short_interest"] = "N/A (0/2)"

    # Days-to-cover (standalone) — high DTC = forced buying pressure when price rises
    # Separate from squeeze composite score because DTC alone predicts covering velocity
    _dtc_standalone = info.get("short_ratio") or (borrow_data.get("days_to_cover") if borrow_data else None) or 0
    if _dtc_standalone:
        if   _dtc_standalone >= 10: score = min(score + 2, 10); details["dtc_standalone"] = f"DTC {_dtc_standalone:.1f}d — high covering pressure (+2)"
        elif _dtc_standalone >= 5:  score = min(score + 1, 10); details["dtc_standalone"] = f"DTC {_dtc_standalone:.1f}d — moderate covering pressure (+1)"
        else:                        details["dtc_standalone"] = f"DTC {_dtc_standalone:.1f}d — low"

    # B7: Short Squeeze Score — Phase 2E: display only in sentiment, no score bonus
    # Squeeze setup signal belongs in Optionality (requires SI>15% + DTC>5 + momentum up)
    squeeze_prob = 0.0
    if borrow_data:
        squeeze_prob = borrow_data.get("squeeze_probability", 0.0)
        dtc = borrow_data.get("days_to_cover") or 0
        sf  = borrow_data.get("short_float_pct") or (info.get("short_percentage_of_float", 0) * 100)
    else:
        sf  = (info.get("short_percentage_of_float") or 0) * 100
        dtc = info.get("short_ratio") or 0
        squeeze_prob = min(1.0, sf / 30 + min(0.3, dtc / 20))
    squeeze_score_10 = round(squeeze_prob * 10, 1)
    details["squeeze_score"]       = squeeze_score_10
    details["squeeze_probability"] = squeeze_prob
    details["short_float_pct"]     = sf
    details["days_to_cover"]       = dtc
    details["squeeze"] = f"Squeeze score {squeeze_score_10}/10 ({sf:.1f}% float, DTC {dtc:.1f}d) — display only"

    # PEAD lives in score_optionality() only — removed here to avoid double-counting

    # Congressional trading — display only, no scoring (1-2 week lag, single trade noise)
    if congressional and congressional.get("net") == "bullish" and congressional.get("purchases", 0) >= 2:
        details["congressional"] = f"Congress: {congressional['purchases']} purchases (net bullish) — display only"
    elif congressional and congressional.get("net") == "bearish":
        details["congressional"] = f"Congress: {congressional.get('sales',0)} sales (net bearish)"
    else:
        details["congressional"] = "No recent congressional activity"

    # Reddit WSB mentions — display only, no scoring (crowd noise, no decay)
    if reddit_wsb and reddit_wsb.get("mentions", 0) >= 3:
        details["reddit_wsb"] = f"WSB: {reddit_wsb['mentions']} mentions ({reddit_wsb.get('sentiment','neutral')}) — display only"
    else:
        details["reddit_wsb"] = "No significant WSB activity"

    # Unusual Options Activity sentiment (smart money signal)
    if uoa_data and (uoa_data.get("call_flow_score", 0) or uoa_data.get("put_flow_score", 0)):
        call_score = uoa_data.get("call_flow_score", 0)
        put_score = uoa_data.get("put_flow_score", 0)
        dominant = uoa_data.get("dominant_flow", "neutral")

        uoa_pts = 0
        if call_score >= 2:  # moderate or heavy call flow
            uoa_pts = 2
            details["unusual_options"] = f"Unusual call flow: {uoa_data.get('summary', 'detected')} (+2)"
        elif put_score >= 2:  # moderate or heavy put flow
            uoa_pts = -1
            details["unusual_options"] = f"Unusual put flow (caution): {uoa_data.get('summary', 'detected')} (-1)"
        else:
            details["unusual_options"] = f"Light unusual options: {uoa_data.get('summary', 'detected')}"

        score = min(score + uoa_pts, 10)
    else:
        details["unusual_options"] = "No significant unusual options activity"

    score = min(score, 10)

    return {
        "score":   score,
        "max":     10,
        "details": details,
    }


# ── Catalyst Tagging Engine ──────────────────────────────────────────────────

def tag_catalysts(indicators: dict, pead_data: dict,
                  options_data: dict, vcp: bool, squeeze: bool,
                  options_intelligence: dict | None = None,
                  news_sentiment_score: dict | None = None) -> tuple[list[str], int, dict]:
    """
    Tag each candidate with its primary catalyst type(s) and assign tier.
    Returns: (tags, catalyst_tier, catalyst_meta)
    catalyst_meta includes catalyst_age_days and expires_after_days per tag.
    Tier 1: PEAD, UOA (confirmed chain sweep), VCP, at_52w_breakout
    Tier 2: SQUEEZE, PULLBACK_EMA21, PULLBACK_EMA50, MOMENTUM, IV_SKEW_BULLISH, GAMMA_WALL_ABOVE
    Tier 3: NEWS_MOMENTUM, CONTINUATION (default/fallback)
    """
    tags: list[str] = []
    tier = 3  # default minimum
    oi = options_intelligence or {}

    # Tier 1 signals
    if pead_data.get("pead"):
        tags.append("PEAD")
        tier = min(tier, 1)

    # True UOA: prefer confirmed sweep from chain over boolean flag
    true_uoa_calls = oi.get("true_uoa_calls") or []
    legacy_uoa = (options_data or {}).get("uoa", False)
    if true_uoa_calls or legacy_uoa:
        tags.append("UOA")
        tier = min(tier, 1)

    if vcp:
        tags.append("VCP")
        tier = min(tier, 1)
    elif indicators.get("near_vcp"):
        tags.append("NEAR_VCP")
        tier = min(tier, 2)

    if indicators.get("pocket_pivot"):
        tags.append("POCKET_PIVOT")
        tier = min(tier, 1)

    if indicators.get("at_52w_breakout"):
        tags.append("BREAKOUT")
        tier = min(tier, 1)

    # Tier 2 signals
    if squeeze:
        tags.append("SQUEEZE")
        tier = min(tier, 2)

    price = indicators.get("close", 0)
    ema21 = indicators.get("ema21", price)
    ema50 = indicators.get("ema50", price)

    if ema21 and price and abs(price - ema21) / price < 0.03:
        tags.append("PULLBACK_EMA21")
        tier = min(tier, 2)
    elif ema50 and price and abs(price - ema50) / price < 0.04:
        tags.append("PULLBACK_EMA50")
        tier = min(tier, 2)
    elif indicators.get("near_52w_high"):
        tags.append("MOMENTUM")
        tier = min(tier, 2)

    # Options intelligence Tier 2 signals
    iv_skew = oi.get("iv_skew", 1.0)
    if iv_skew and iv_skew < 0.85:
        # Calls bid higher than puts at same delta = market pricing upside, not downside
        tags.append("IV_SKEW_BULLISH")
        tier = min(tier, 2)

    gwa = oi.get("gamma_wall_above")
    if gwa and price > 0:
        pct_away = gwa.get("pct_away", 999)
        if pct_away is not None and 2 <= pct_away <= 8:
            # Concentrated call OI above price = magnetic breakout target
            tags.append("GAMMA_WALL_ABOVE")
            tier = min(tier, 2)

    # Polygon news momentum — upgrade to T2 when strong (3+ articles, bullish, high weighted score)
    pns = news_sentiment_score or {}
    _pns_momentum = pns.get("momentum", "")
    _pns_count = pns.get("article_count", 0)
    _pns_score = pns.get("source_score", 0)
    if _pns_momentum == "bullish" and _pns_count >= 3 and _pns_score >= 0.4:
        tags.append("NEWS_MOMENTUM")
        tier = min(tier, 2)
    elif _pns_momentum == "bullish" and _pns_count >= 2:
        tags.append("NEWS_MOMENTUM")
        # T3 — weaker news signal

    if not tags:
        tags.append("CONTINUATION")

    # Fix #15: Compute catalyst_age_days and expires_after_days per tag
    # Expiry windows by catalyst type (trading days)
    _catalyst_expiry_map = {
        "PEAD": 15, "UOA": 5, "VCP": 30, "NEAR_VCP": 21, "BREAKOUT": 21,
        "POCKET_PIVOT": 14,
        "SQUEEZE": 10, "MOMENTUM": 14, "NEWS_MOMENTUM": 7,
        "PULLBACK_EMA21": 14, "PULLBACK_EMA50": 14,
        "IV_SKEW_BULLISH": 10, "GAMMA_WALL_ABOVE": 10,
        "CONTINUATION": 21,
    }
    catalyst_meta: dict = {"per_tag": {}}
    for tag in tags:
        _expires = _catalyst_expiry_map.get(tag, 14)
        _age = 0  # default: catalyst just detected today
        # PEAD: compute age from earnings date
        if tag == "PEAD" and pead_data.get("earnings_date"):
            try:
                from datetime import datetime as _dt, date as _d
                _ed = pead_data["earnings_date"]
                if isinstance(_ed, str):
                    _ed_dt = _dt.strptime(_ed, "%Y-%m-%d").date()
                else:
                    _ed_dt = _ed if isinstance(_ed, _d) else _d.today()
                _age = max(0, (_d.today() - _ed_dt).days)
                # Convert calendar days to approximate trading days
                _age = int(_age * 5 / 7)
            except Exception:
                pass
        # UOA: typically detected same day, age = 0
        catalyst_meta["per_tag"][tag] = {
            "catalyst_age_days": _age,
            "expires_after_days": _expires,
            "is_expired": _age > _expires,
        }
    # Summary fields
    catalyst_meta["any_expired"] = any(
        v.get("is_expired", False) for v in catalyst_meta["per_tag"].values()
    )
    catalyst_meta["soonest_expiry_days"] = min(
        (v["expires_after_days"] - v["catalyst_age_days"])
        for v in catalyst_meta["per_tag"].values()
    ) if catalyst_meta["per_tag"] else 0

    return tags, tier, catalyst_meta


def classify_setup_family(setup_type: str, catalyst_tags: list, indicators: dict) -> tuple[str, str]:
    """
    Classify setup into one of 4 families with hold period guidance.
    Returns (family_name, hold_period_guide)
    """
    setup_type_lower = (setup_type or "").lower()
    catalyst_str = " ".join([str(t).lower() for t in catalyst_tags]) if catalyst_tags else ""

    # Impulse Catalyst: PEAD, UOA, gap-and-go, Pocket Pivot
    if "pead" in catalyst_str or "uoa" in catalyst_str or "gap" in setup_type_lower:
        return "Impulse Catalyst", "5-8d"
    if "pocket_pivot" in catalyst_str or "pocket pivot" in setup_type_lower:
        return "Impulse Catalyst", "5-10d"

    # Breakout Expansion: VCP, near-VCP, 52wk breakout, squeeze
    if ("vcp" in catalyst_str or "near_vcp" in catalyst_str or "breakout" in catalyst_str or
        indicators.get("at_52w_breakout", False) or indicators.get("squeeze_on", False)):
        return "Breakout Expansion", "7-21d"

    # Trend Continuation: EMA21/50 pullbacks, bounce, rebreak
    if ("bounce" in setup_type_lower or "pullback" in catalyst_str or
        "ema21" in catalyst_str or "ema50" in catalyst_str or
        "tight_range" in setup_type_lower):
        return "Trend Continuation", "7-21d"

    # Special Situation: insider, float rotation, short squeeze
    if ("insider" in catalyst_str or "float_rotation" in catalyst_str or
        "short_squeeze" in catalyst_str or indicators.get("sec_catalyst", False)):
        return "Special Situation", "5-15d"

    # Default fallback
    return "Trend Continuation", "7-21d"


# ── Entry Quality Classifier ─────────────────────────────────────────────────

def classify_entry_quality(price: float, indicators: dict, sr: dict) -> str:
    """
    ATR-relative entry quality classification with EMA21 + EMA50 dual-distance.

    Tightened per user feedback: "GOOD setup + BAD location = WAIT" — the prior
    1.25-ATR-above-EMA21 threshold let stocks like SLB (0.96 ATR above, 3+ ATR
    above EMA50) pass as PULLBACK when they're really LATE-stage breakouts.

    New evaluation (first match wins):
      MISSED   — >2.0 ATR above EMA21 OR price > resistance × 1.02
      EXTENDED — >1.0 ATR above EMA21 OR >3.0 ATR above EMA50 (LATE location)
      FRESH    — within 0.5 ATR of EMA21 AND within 0.5 ATR of support (textbook value)
      PULLBACK — within 1.0 ATR of EMA21 AND within 2.0 ATR of EMA50 (orderly retrace)
      VALID    — fallback when none of above match (acceptable but not preferred)
    """
    ema21      = indicators.get("ema21", price)
    ema50      = indicators.get("ema50", price)
    resistance = sr.get("resistance", price * 1.10)
    support    = sr.get("support",    price * 0.95)
    atr        = indicators.get("atr", price * 0.02)

    if price <= 0 or ema21 <= 0:
        return "VALID"
    if atr <= 0:
        atr = price * 0.02

    dist_ema21    = (price - ema21) / atr          # signed: + = price above EMA21
    dist_ema50    = ((price - ema50) / atr) if ema50 > 0 else 0  # signed
    dist_support  = abs(price - support) / atr     # unsigned

    # MISSED: beyond resistance or >2.0 ATR above EMA21 OR >4.0 ATR above EMA50
    if price > resistance * 1.02 or dist_ema21 > 2.0 or dist_ema50 > 4.0:
        return "MISSED"

    # EXTENDED: LATE location — either EMA21 >1.0 ATR or EMA50 >3.0 ATR
    # This catches the SLB case: 0.96 ATR above EMA21 but 3+ ATR above EMA50.
    if dist_ema21 > 1.0 or dist_ema50 > 3.0:
        return "EXTENDED"

    # FRESH: tight to EMA21 AND tight to support — textbook swing entry
    near_ema21_fresh   = abs(dist_ema21) <= 0.5
    near_support_fresh = dist_support <= 0.5
    if near_ema21_fresh and near_support_fresh:
        return "FRESH"

    # PULLBACK: within 1.0 ATR of EMA21 AND within 2.0 ATR of EMA50
    # Both conditions required — prevents "at EMA21 but miles from EMA50" (still extended)
    near_ema21  = abs(dist_ema21) <= 1.0
    near_ema50  = (abs(dist_ema50) <= 2.0) if ema50 > 0 else True
    near_sup    = dist_support <= 1.0
    if (near_ema21 and near_ema50) or near_sup:
        return "PULLBACK"

    return "VALID"


def _adjust_plan_by_entry_quality(plan: dict, entry_quality: str, indicators: dict,
                                   sr: dict | None = None) -> dict:
    """
    Audit item #10: entry_quality-aware trade plan modifications.

    The 5-state entry_quality classifier (FRESH/PULLBACK/VALID/EXTENDED/MISSED)
    previously only influenced decision verdict for EXTENDED/MISSED (→ WATCH).
    FRESH, PULLBACK, and VALID fell through identically. This function refines
    stop / target / hold to match each quality's risk-reward profile:

      FRESH    — support - 0.5×ATR, +4R, 10d hold
      PULLBACK — support - 0.75×ATR, +3R, 7d hold
      VALID    — EMA50 - 1.0×ATR, +2.5R, 5d hold
      EXTENDED/MISSED — unchanged (demoted to WATCH elsewhere)

    Unknown quality → plan left unchanged. Adds `entry_quality_adj` for debug.
    """
    if entry_quality not in ("FRESH", "PULLBACK", "VALID"):
        return plan

    try:
        atr   = float(indicators.get("atr", 0) or 0)
        ema50 = float(indicators.get("ema50", 0) or 0)
    except (TypeError, ValueError):
        return plan

    # Resolve support: prefer sr["support"], else plan support_level, else current stop
    support = 0.0
    if sr and sr.get("support"):
        try:
            support = float(sr.get("support") or 0)
        except (TypeError, ValueError):
            support = 0.0
    if not support:
        support = float(plan.get("support_level", plan.get("stop", 0)) or 0)

    # Resolve entry: prefer explicit 'entry', else midpoint of entry zone, else price
    entry = plan.get("entry")
    if entry is None:
        lo = plan.get("entry_low")
        hi = plan.get("entry_high")
        if lo is not None and hi is not None:
            try:
                entry = (float(lo) + float(hi)) / 2.0
            except (TypeError, ValueError):
                entry = None
    if entry is None:
        entry = plan.get("price", 0)
    try:
        entry = float(entry or 0)
    except (TypeError, ValueError):
        entry = 0.0

    # 2026-05-08: stops widened +0.25×ATR across all tiers. Backtest 60d/58 trades
    # showed 50% stop-out rate with 0% WR on stop_loss exits. Trailing stops drove
    # all alpha (93.8% WR). Wider initial stops give the trade room to mean-revert
    # before activating the trailing logic at +2%.
    if entry_quality == "FRESH":
        if support and atr:
            plan["stop"] = round(support - 0.75 * atr, 2)
        plan["max_hold_days"]     = 10
        plan["target_r_multiple"] = 4.0
        plan["entry_quality_adj"] = "FRESH: stop 0.75xATR, hold 10d, target 4R"
    elif entry_quality == "PULLBACK":
        if support and atr:
            plan["stop"] = round(support - 1.0 * atr, 2)
        plan["max_hold_days"]     = 7
        plan["target_r_multiple"] = 3.0
        plan["entry_quality_adj"] = "PULLBACK: stop 1.0xATR, hold 7d, target 3R"
    elif entry_quality == "VALID":
        if ema50 and atr:
            plan["stop"] = round(ema50 - 1.25 * atr, 2)
        plan["max_hold_days"]     = 5
        plan["target_r_multiple"] = 2.5
        plan["entry_quality_adj"] = "VALID: stop EMA50-1.25xATR, hold 5d, target 2.5R"

    # Recompute target1 + target2 + risk_per_share + rr_ratio + refresh exit_rules
    # from the new stop. Without this, target2 stays at its pre-EQ value (5R from
    # the OLD risk) and ends up below target1 (2.5R from NEW, larger risk) — the
    # ATEN inversion bug. exit_rules Rule 1 and Rule 3 also embed stale prices.
    if "target_r_multiple" in plan and plan.get("stop") is not None and entry:
        try:
            stop_new = float(plan["stop"])
            risk = abs(entry - stop_new)
            if risk > 0:
                tr_mult = plan["target_r_multiple"]
                direction = plan.get("direction", "long")
                if direction == "long":
                    plan["target1"] = round(entry + risk * tr_mult, 2)
                    # T2 always > T1: keep the +2R buffer used in compute_trade_plan
                    plan["target2"] = round(entry + risk * (tr_mult + 2.0), 2)
                else:
                    plan["target1"] = round(entry - risk * tr_mult, 2)
                    plan["target2"] = round(entry - risk * (tr_mult + 2.0), 2)
                plan["risk_per_share"] = round(risk, 2)
                # rr_ratio = (target1 - entry) / risk  (== target_r_multiple)
                plan["rr_ratio"] = round(tr_mult, 1)

                # Refresh exit_rules so Rule 1 (hard stop) + Rule 3 (T1 partial)
                # show the post-adjustment numbers, not the pre-adjustment ones.
                rules = plan.get("exit_rules")
                if isinstance(rules, list) and rules:
                    t1_p = float(plan["target1"])
                    be_stop = round(entry * 1.005, 2) if direction == "long" else round(entry * 0.995, 2)
                    partial_pct = (plan.get("exit_params") or {}).get("partial_at_t1_pct", 50)
                    for i, r in enumerate(rules):
                        if isinstance(r, str):
                            if r.startswith("Rule 1 —"):
                                if direction == "long":
                                    rules[i] = (f"Rule 1 — Hard Stop: Exit ALL at ${stop_new:.2f} immediately "
                                                f"— no exceptions, no averaging down")
                                else:
                                    rules[i] = f"Rule 1 — Hard Stop: Cover ALL at ${stop_new:.2f} immediately — no exceptions"
                            elif r.startswith("Rule 3 —"):
                                verb = "Sell" if direction == "long" else "Cover"
                                rules[i] = (f"Rule 3 — T1 Partial: {verb} {partial_pct}% at T1 ${t1_p:.2f}, "
                                            f"move stop to breakeven ${be_stop:.2f} on remainder")
                    plan["exit_rules"] = rules
        except (TypeError, ValueError):
            pass

    return plan


def classify_entry_subtype(price: float, indicators: dict, sr: dict,
                            setup_type: str = "") -> str:
    """
    Classify granular entry subtype for attribution tracking.
    Returns one of: Pivot Entry / First Pullback / EMA21 Continuation /
                    EMA50 Continuation / Tight Range Rebreak / Breakout Add
    """
    ema21      = indicators.get("ema21", price)
    ema50      = indicators.get("ema50", price)
    atr        = indicators.get("atr", price * 0.02)
    at_breakout = indicators.get("at_52w_breakout", False)
    vcp         = indicators.get("vcp", False)
    near_vcp    = indicators.get("near_vcp", False)
    tight_range = indicators.get("tight_range", False)
    pocket_pivot = indicators.get("pocket_pivot", False)

    if atr <= 0:
        atr = price * 0.02

    if pocket_pivot:
        return "Pocket Pivot Entry"

    if at_breakout or vcp or near_vcp:
        return "Pivot Entry"

    if tight_range:
        return "Tight Range Rebreak"

    near_ema21 = ema21 > 0 and abs(price - ema21) / atr <= 1.25
    near_ema50 = ema50 > 0 and abs(price - ema50) / atr <= 1.25

    if near_ema21:
        dist_atr = abs(price - ema21) / atr
        return "EMA21 Continuation" if dist_atr <= 0.5 else "First Pullback"

    if near_ema50:
        return "EMA50 Continuation"

    return "Breakout Add"


# ── Options Intelligence Engine ───────────────────────────────────────────────

def compute_options_intelligence(chain: dict, price: float) -> dict:
    """
    Derive actionable signals from a full FINVIZ options chain (116 strikes × Greeks).
    chain: {"calls": [...], "puts": [...]} — each item: strike, iv, delta, gamma, theta, vega, oi, volume

    Returns:
        iv_skew          — OTM put IV / OTM call IV (>1.2 = bearish, <0.85 = bullish)
        pc_ratio_oi      — put OI / call OI (positioning sentiment)
        pc_ratio_vol     — put vol / call vol (today's actual flow)
        max_pain         — strike where total option seller loss is minimized (price magnet)
        gamma_wall_above — strike with peak call gamma × OI above current price (breakout resistance)
        gamma_wall_below — strike with peak put gamma × OI below price (support / dealer hedge)
        true_uoa_calls   — call strikes where volume > 5× OI and volume > 500 (institutional sweeps)
        true_uoa_puts    — put strikes with same criteria (smart money hedging or positioning)
        dominant_flow    — "calls" / "puts" / "neutral" by volume ratio
        iv_rank_est      — ATM implied vol as percentage (proxy for current IV level)
        call_oi_sum, put_oi_sum, call_vol_sum, put_vol_sum
    """
    calls = [c for c in (chain.get("calls") or []) if c.get("strike")]
    puts  = [p for p in (chain.get("puts")  or []) if p.get("strike")]

    result: dict = {
        "iv_skew": 1.0,
        "pc_ratio_oi": None,
        "pc_ratio_vol": None,
        "max_pain": None,
        "gamma_wall_above": None,
        "gamma_wall_below": None,
        "true_uoa_calls": [],
        "true_uoa_puts": [],
        "dominant_flow": "neutral",
        "iv_rank_est": None,
        "call_oi_sum": 0,
        "put_oi_sum": 0,
        "call_vol_sum": 0,
        "put_vol_sum": 0,
    }

    if not calls and not puts:
        return result

    # Aggregate OI and volume
    call_oi  = sum(c.get("oi", 0) or 0 for c in calls)
    put_oi   = sum(p.get("oi", 0) or 0 for p in puts)
    call_vol = sum(c.get("volume", 0) or 0 for c in calls)
    put_vol  = sum(p.get("volume", 0) or 0 for p in puts)
    result.update({"call_oi_sum": call_oi, "put_oi_sum": put_oi,
                   "call_vol_sum": call_vol, "put_vol_sum": put_vol})

    if call_oi > 0:
        result["pc_ratio_oi"] = round(put_oi / call_oi, 2)
    if call_vol > 0:
        result["pc_ratio_vol"] = round(put_vol / call_vol, 2)

    # IV Skew: OTM put IV vs OTM call IV at equal distance from price (5–15% OTM)
    otm_call_ivs = [c["iv"] for c in calls
                    if c.get("iv") and price > 0 and price * 1.05 <= c["strike"] <= price * 1.15]
    otm_put_ivs  = [p["iv"] for p in puts
                    if p.get("iv") and price > 0 and price * 0.85 <= p["strike"] <= price * 0.95]
    if otm_call_ivs and otm_put_ivs:
        avg_c = sum(otm_call_ivs) / len(otm_call_ivs)
        avg_p = sum(otm_put_ivs) / len(otm_put_ivs)
        if avg_c > 0:
            result["iv_skew"] = round(avg_p / avg_c, 3)

    # ATM IV estimate (closest strike to current price)
    if calls and price > 0:
        atm = min(calls, key=lambda c: abs(c.get("strike", 0) - price))
        if atm.get("iv"):
            result["iv_rank_est"] = round(atm["iv"] * 100, 1)

    # True UOA: volume > 5× OI and volume > 500 (sweeps indicate institutional intent)
    UOA_MIN_VOL = 500
    result["true_uoa_calls"] = [
        {"strike": c["strike"], "vol": c.get("volume", 0), "oi": c.get("oi", 0),
         "iv": c.get("iv"), "delta": c.get("delta")}
        for c in calls
        if (c.get("volume") or 0) >= UOA_MIN_VOL
        and (c.get("volume") or 0) > (c.get("oi") or 1) * 5
        and price > 0 and c["strike"] >= price * 0.97   # at or OTM
    ]
    result["true_uoa_puts"] = [
        {"strike": p["strike"], "vol": p.get("volume", 0), "oi": p.get("oi", 0),
         "iv": p.get("iv"), "delta": p.get("delta")}
        for p in puts
        if (p.get("volume") or 0) >= UOA_MIN_VOL
        and (p.get("volume") or 0) > (p.get("oi") or 1) * 5
        and price > 0 and p["strike"] <= price * 1.03   # at or OTM
    ]

    # Gamma walls: strike × gamma × OI = gamma dollar exposure
    calls_above = [c for c in calls if c.get("gamma") and price > 0 and c.get("strike", 0) > price]
    puts_below  = [p for p in puts  if p.get("gamma") and price > 0 and p.get("strike", 0) < price]
    if calls_above:
        gw = max(calls_above, key=lambda c: (c.get("gamma") or 0) * (c.get("oi") or 0))
        result["gamma_wall_above"] = {
            "strike": gw["strike"],
            "gamma_oi": round((gw.get("gamma") or 0) * (gw.get("oi") or 0)),
            "pct_away": round((gw["strike"] - price) / price * 100, 1) if price > 0 else None,
        }
    if puts_below:
        gw = max(puts_below, key=lambda p: (p.get("gamma") or 0) * (p.get("oi") or 0))
        result["gamma_wall_below"] = {
            "strike": gw["strike"],
            "gamma_oi": round((gw.get("gamma") or 0) * (gw.get("oi") or 0)),
            "pct_away": round((price - gw["strike"]) / price * 100, 1) if price > 0 else None,
        }

    # Max pain: strike that minimizes total OI-weighted loss for option buyers
    all_strikes = sorted({c.get("strike", 0) for c in calls} | {p.get("strike", 0) for p in puts})
    if all_strikes:
        min_total, mp_strike = None, None
        for test in all_strikes:
            c_pain = sum((c.get("oi") or 0) * max(0, test - c["strike"]) for c in calls)
            p_pain = sum((p.get("oi") or 0) * max(0, p["strike"] - test) for p in puts)
            total = c_pain + p_pain
            if min_total is None or total < min_total:
                min_total, mp_strike = total, test
        result["max_pain"] = mp_strike

    # Dominant flow
    if call_vol > put_vol * 1.5:
        result["dominant_flow"] = "calls"
    elif put_vol > call_vol * 1.5:
        result["dominant_flow"] = "puts"

    return result


def compute_news_sentiment_score(news_articles: list | None) -> dict:
    """
    Source-weighted, recency-decayed news sentiment from Polygon per-article NLP.
    Each article has insights[].sentiment: positive/negative/neutral (real NLP, not word-matching).

    Scoring (0-3 pts, penalty to -1):
    - Tier-1 publishers (Bloomberg, Reuters, WSJ, CNBC…) get 1.5× weight
    - Recency: < 2h = 2× weight (breaking news), 24h+ = 0.5× weight
    - Momentum: last 3 articles all positive = "bullish" (upgrade signal strength)
    - Breaking bonus: any article < 2h old with positive sentiment = +1 (capped at 3)
    """
    from datetime import datetime, timezone

    EMPTY = {"score": 0, "max": 3, "momentum": "neutral", "breaking": False,
             "source_score": 0.0, "details": "No Polygon news", "article_count": 0}
    if not news_articles:
        return EMPTY

    TIER1 = {
        "Bloomberg", "Reuters", "The Wall Street Journal", "CNBC", "Financial Times",
        "Barron's", "MarketWatch", "Seeking Alpha", "The Motley Fool", "Benzinga",
        "Zacks Investment Research", "Investor's Business Daily", "TheStreet", "Yahoo Finance",
    }

    now = datetime.now(timezone.utc)
    scored: list[dict] = []

    for article in news_articles[:12]:
        try:
            pub = (article.get("published_utc") or "").replace("Z", "+00:00")
            pub_dt = datetime.fromisoformat(pub) if pub else None
            age_h = (now - pub_dt).total_seconds() / 3600 if pub_dt else 48
        except Exception:
            age_h = 48

        recency = 2.0 if age_h < 2 else (1.0 if age_h < 24 else 0.5)
        publisher = (article.get("publisher") or {}).get("name", "")
        src_w = 1.5 if any(t in publisher for t in TIER1) else 1.0

        # Per-article NLP sentiment from Polygon insights[]
        insights = article.get("insights") or []
        sent_vals = []
        for ins in insights:
            s = (ins.get("sentiment") or "").lower()
            if s == "positive":
                sent_vals.append(1.0)
            elif s == "negative":
                sent_vals.append(-1.0)
            # neutral = 0, omit to not dilute

        if not sent_vals:
            # Fallback to ticker_sentiment score if available
            tkr_sents = article.get("ticker_sentiment") or []
            if tkr_sents and isinstance(tkr_sents, list):
                raw = tkr_sents[0].get("sentiment_score") if tkr_sents else None
                sent_vals = [float(raw)] if raw is not None else [0.0]
            else:
                sent_vals = [0.0]

        article_sent = sum(sent_vals) / len(sent_vals)
        scored.append({
            "sentiment": article_sent,
            "weight": recency * src_w,
            "publisher": publisher,
            "age_h": age_h,
            "breaking": age_h < 2,
        })

    if not scored:
        return EMPTY

    total_w = sum(a["weight"] for a in scored)
    weighted = sum(a["sentiment"] * a["weight"] for a in scored) / max(total_w, 0.01)

    # Sentiment momentum: are the 3 most-recent articles all the same direction?
    last3 = [a["sentiment"] for a in scored[:3]]
    if all(s > 0.1 for s in last3):
        momentum = "bullish"
    elif all(s < -0.1 for s in last3):
        momentum = "bearish"
    else:
        momentum = "mixed"

    breaking = any(a["breaking"] for a in scored)

    # Score 0-3 (can go to -1 for heavy negative flow)
    if weighted >= 0.6 and momentum == "bullish":
        score = 3
    elif weighted >= 0.35:
        score = 2
    elif weighted >= 0.1:
        score = 1
    elif weighted <= -0.35:
        score = -1
    else:
        score = 0

    if breaking and weighted > 0.1:
        score = min(score + 1, 3)

    return {
        "score": score,
        "max": 3,
        "momentum": momentum,
        "breaking": breaking,
        "source_score": round(weighted, 3),
        "details": (f"Polygon: {len(scored)} articles, sent {weighted:+.2f}, "
                    f"momentum={momentum}" + (" [BREAKING]" if breaking else "")),
        "article_count": len(scored),
    }


# ── Conviction Tier Assignment ────────────────────────────────────────────────

def assign_conviction_tier(score: float, rr_ratio: float, rs_rank: int,
                            weekly_bull: bool, catalysts: list[str],
                            entry_quality: str,
                            setup_type: str = "",
                            regime_name: str = "neutral",
                            regime4: str = "risk_on_choppy",
                            catalyst_tier: int = 3) -> dict:
    """
    Assign conviction tier based on score, R:R, RS, catalysts, entry quality, regime4.

    T1 (≥88): regime4=risk_on_trending, RS≥85, R:R≥3.5, cat_tier=1, FRESH/PULLBACK
    T2 (≥78): regime4≠panic, RS≥75, R:R≥3.0, cat_tier≤2, FRESH/PULLBACK/VALID
    T3 (≥70): score≥70, R:R≥3.0 — above threshold, smaller size
    WATCH: score 50–69 or missing a T2/T3 gate
    AVOID: below 50

    Size multipliers scaled within each tier band (linear, no cliff effects).
    Win-rate feedback adjusts size_mult for tradeable tiers based on historical edge.
    """
    quality_ok   = entry_quality in ("FRESH", "PULLBACK", "VALID")
    fresh_or_pb  = entry_quality in ("FRESH", "PULLBACK")
    has_primary  = any(c in catalysts for c in ("PEAD", "UOA", "VCP", "NEAR_VCP", "POCKET_PIVOT", "SQUEEZE"))
    is_panic     = regime4 == "panic"
    is_risk_on_trending = regime4 == "risk_on_trending"

    if (score >= 88 and rr_ratio >= 3.5 and rs_rank >= 85
            and is_risk_on_trending and catalyst_tier <= 1 and fresh_or_pb):
        # T1: Full conviction — 0.85 at 88 → 1.0 at 98+ (linear)
        _t1_mult = min(1.0, 0.85 + (score - 88) * 0.015)
        result = {"tier": 1, "label": "T1", "size_mult": round(_t1_mult, 2),
                  "description": "Full size — all gates cleared"}
    elif (score >= 78 and rr_ratio >= 3.0 and rs_rank >= 75
            and not is_panic and catalyst_tier <= 2 and quality_ok):
        # T2: Strong setup — 0.30 at 78 → 0.60 at 87 (linear), Tier1 catalyst adds +0.10
        _t2_base = 0.30 + (score - 78) * 0.033
        _t2_mult = min(0.60, _t2_base + (0.10 if catalyst_tier == 1 else 0))
        result = {"tier": 2, "label": "T2", "size_mult": round(_t2_mult, 2),
                  "description": "Half size — strong setup"}
    elif (score >= 70 and rr_ratio >= 3.0):
        # T3: 0.15 at 70 → 0.30 at 77 (linear)
        _t3_mult = 0.15 + (score - 70) * 0.021
        result = {"tier": 3, "label": "T3", "size_mult": round(min(0.30, _t3_mult), 2),
                  "description": "Quarter size — above threshold"}
    elif score >= 65 and rr_ratio >= 3.0:
        # Legacy T3 band: keeps existing 65-threshold trades alive
        _t3_mult = 0.15 + (score - 65) * 0.010
        result = {"tier": 3, "label": "T3", "size_mult": round(min(0.20, _t3_mult), 2),
                  "description": "Small size — borderline threshold"}
    elif score >= 50:
        return {"tier": 0, "label": "WATCH", "size_mult": 0.0,
                "description": "Monitor — not ready to trade"}
    else:
        return {"tier": -1, "label": "AVOID", "size_mult": 0.0,
                "description": "Pass — weak structure"}

    # Apply historical win-rate sizing adjustment for tradeable tiers (T1–T3 only)
    # Reduces size for low-WR setups; increases for high-WR setups.
    # Does NOT re-apply the score multiplier already applied in the win-rate feedback block.
    if setup_type:
        try:
            from tracker import get_setup_weight_multiplier
            _wr_mult = get_setup_weight_multiplier(setup_type, regime_name)
            if _wr_mult != 1.0:
                result["size_mult"] = round(
                    min(1.0, max(0.1, result["size_mult"] * _wr_mult)), 2
                )
                result["wr_size_adj"] = f"{_wr_mult:.1f}× win-rate ({setup_type}/{regime_name})"
        except Exception:
            pass

    return result


# ── Shared Win-Rate Multiplier Helper (Audit #9) ──────────────────────────────
# Single source of truth: called by BOTH live (analyze_ticker) AND backtest
# (_score_as_of). Ensures backtest scoring path = production scoring path so
# WR claims from backtests translate to live performance.

def apply_setup_wr_multiplier(normalized_score: float,
                              setup_type: str,
                              regime_name: str) -> float:
    """Scale a normalized 0-100 score by historical setup/regime win-rate edge.

    Returns the clamped, rounded score. If tracker data is unavailable or the
    multiplier lookup fails, returns the input score unchanged (safe default).

    Called by:
      - analysis.analyze_ticker()    (live scoring)
      - backtest._score_as_of()      (historical scoring)
    """
    try:
        from tracker import get_setup_weight_multiplier
        mult = get_setup_weight_multiplier(setup_type or "unknown",
                                           regime_name or "unknown")
        try:
            log.debug(
                f"apply_setup_wr_multiplier: setup={setup_type!r} regime={regime_name!r} "
                f"mult={float(mult):.3f} in={float(normalized_score):.2f}"
            )
        except Exception:
            pass
        if mult != 1.0:
            adjusted = round(float(normalized_score) * float(mult), 1)
            return max(0.0, min(100.0, adjusted))
    except Exception:
        pass  # Non-critical: never block a trade decision on feedback loop
    return float(normalized_score)


# ── Unified VIX Mode Resolver (AI-11) ─────────────────────────────────────────

def resolve_vix_mode(vix_current: float, vix_5d_avg: float | None, config: dict) -> dict:
    """AI-11: single source of truth for VIX-driven tighten/kill + sizing.

    Combines:
      - VIX absolute level → vix_multipliers (position sizing)
      - VIX spike % vs 5d avg → kill/tighten mode (verdict + score bar)

    Returns dict:
      kill_longs     (bool) — hard stop on new longs
      score_add      (int)  — additional BUY score threshold needed
      size_mult      (float)— sizing multiplier [0..1]
      mode           (str)  — 'kill' | 'tighten' | 'normal'
      note           (str)  — human-readable explanation
    """
    _gates = config.get("gates", {})
    _vix_mults = config.get("vix_multipliers", {})
    spike_threshold = _gates.get("vix_spike_kill_pct", 30)

    # Size multiplier from VIX level
    if vix_current is None:
        size_mult = 1.0
    elif vix_current < 18:
        size_mult = _vix_mults.get("below_18", 1.0)
    elif vix_current < 22:
        size_mult = _vix_mults.get("18_to_22", 0.9)
    elif vix_current < 25:
        size_mult = _vix_mults.get("22_to_25", 0.75)
    elif vix_current < 30:
        size_mult = _vix_mults.get("25_to_30", 0.5)
    else:
        size_mult = _vix_mults.get("above_30", 0.2)
    size_mult = float(size_mult)

    # Spike detection
    spike_pct = 0.0
    if vix_5d_avg and vix_5d_avg > 0 and vix_current is not None:
        spike_pct = (vix_current - vix_5d_avg) / vix_5d_avg * 100

    if spike_pct >= spike_threshold:
        return {"kill_longs": True, "score_add": 999, "size_mult": 0.0,
                "mode": "kill", "spike_pct": spike_pct,
                "note": f"VIX spike +{spike_pct:.0f}% (>={spike_threshold}%) — no new longs, block all"}

    if spike_pct >= spike_threshold * 0.67:
        # Tighten mode: raise bar AND reduce size (previously only raised bar)
        return {"kill_longs": False, "score_add": 10, "size_mult": min(size_mult, 0.5),
                "mode": "tighten", "spike_pct": spike_pct,
                "note": f"VIX spike +{spike_pct:.0f}% — require score >=75, size capped at 0.5x"}

    return {"kill_longs": False, "score_add": 0, "size_mult": size_mult,
            "mode": "normal", "spike_pct": spike_pct,
            "note": f"VIX {vix_current:.0f} ({'calm' if vix_current < 20 else 'elevated'}), size x{size_mult:.2f}"}


# ── Dynamic Kelly Position Sizer ──────────────────────────────────────────────

def kelly_position_size(stats: dict, regime_name: str, vix: float,
                         conviction_tier: int, portfolio_size: float,
                         risk_per_share: float, price: float,
                         config: dict | None = None,
                         adv_20d: float = 0.0) -> dict:
    """
    Risk-first position sizing model (Fix #5):
      risk_dollars = account_equity * risk_per_trade_pct
      shares = floor(risk_dollars / stop_distance)
      position_value = shares * entry_price

    Then cap by:
      1. max_capital_per_trade_pct (e.g. 10% of equity)
      2. regime max_size_pct (multiplier on calculated size)
      3. liquidity (don't exceed 5% of ADV)

    Uses live tracker stats (Fix #3) when available instead of hard-coded win rates.
    stats: from tracker.compute_stats() — win_rate, avg_win, avg_loss (live data)
    """
    import math

    _cfg = config or {}
    _portfolio_cfg = _cfg.get("portfolio", {})
    risk_per_trade_pct = _portfolio_cfg.get("risk_per_trade_pct", 0.01)
    max_capital_per_trade_pct = _portfolio_cfg.get("max_capital_per_trade_pct", 0.10)

    # ── Live tracker stats (Fix #3) — use actual win rate, not hard-coded ──
    # stats comes from tracker.compute_stats() which returns live performance data.
    # Only use live stats if sufficient data; otherwise fall back to conservative defaults.
    live_win_rate = None
    if stats.get("sufficient_data"):
        live_win_rate = stats.get("win_rate", 50) / 100  # tracker returns as percentage
    win_rate = live_win_rate if live_win_rate is not None else 0.50
    avg_win  = stats.get("avg_win", 3.0)
    avg_loss = abs(stats.get("avg_loss", -1.5))

    # Compute Kelly for informational purposes (not used for sizing directly)
    kelly_pct = 0.0
    half_kelly_pct = 0.0
    if avg_loss > 0 and win_rate > 0 and avg_win > 0:
        kelly_pct = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        half_kelly_pct = max(0.0, kelly_pct / 2)

    # ── Risk-first sizing (Fix #5) ──
    stop_distance = max(risk_per_share, 0.01)
    risk_dollars = portfolio_size * risk_per_trade_pct
    shares_from_risk = math.floor(risk_dollars / stop_distance) if stop_distance > 0 else 0
    position_value = shares_from_risk * price

    # ── Cap 1: max capital per trade ──
    max_position_value = portfolio_size * max_capital_per_trade_pct
    if position_value > max_position_value and price > 0:
        shares_from_risk = math.floor(max_position_value / price)
        position_value = shares_from_risk * price

    # ── Cap 2: regime max_size_pct multiplier ──
    _regime_mults = _cfg.get("regime_multipliers", {})
    _default_regime_mults = {
        "risk_on_trending": 1.0, "risk_on_choppy": 0.7,
        "risk_off_trending": 0.35, "panic": 0.0,
        "bull": 1.0, "neutral": 0.75, "bear": 0.5,
    }
    regime_mult = _regime_mults.get(regime_name.lower(),
                  _default_regime_mults.get(regime_name.lower(), 0.75))

    # Also apply regime4 max_size_pct from config if available
    _rt4 = _cfg.get("regime4_thresholds", {}).get(regime_name, {})
    regime_max_size_pct = _rt4.get("max_size_pct", 100) / 100.0
    effective_regime_cap = min(regime_mult, regime_max_size_pct)

    # AI-11: use resolve_vix_mode (single source of truth for all VIX logic)
    _vix_mode = resolve_vix_mode(vix, None, _cfg)  # pass None for 5d_avg — spike done at pipeline level
    _vix_mult = _vix_mode["size_mult"]
    if _vix_mult < 1.0:
        effective_regime_cap = effective_regime_cap * _vix_mult

    # ── Phase 2: Vol-targeted portfolio sizing ──
    # When portfolio is in drawdown, shrink size proportionally. Reads current
    # drawdown from kwargs (passed by caller with portfolio state); falls back to 1.0
    # when no equity history available (e.g., first-time paper trading activation).
    _vol_cfg = _cfg.get("portfolio_vol_targeting") or {}
    _drawdown_mult = 1.0
    _drawdown_pct = None
    if _vol_cfg.get("_enabled", True):
        # Drawdown is passed in via kwargs as `current_drawdown_pct` (positive number = % below peak)
        _drawdown_pct = _vol_cfg.get("_runtime_drawdown_pct")  # set by orchestrator if available
        if _drawdown_pct is not None and _drawdown_pct > 0:
            _bands = _vol_cfg.get("drawdown_bands") or {}
            if _drawdown_pct <= 3:    _drawdown_mult = _bands.get("down_0_to_3", 1.0)
            elif _drawdown_pct <= 5:  _drawdown_mult = _bands.get("down_3_to_5", 0.85)
            elif _drawdown_pct <= 10: _drawdown_mult = _bands.get("down_5_to_10", 0.65)
            elif _drawdown_pct <= 15: _drawdown_mult = _bands.get("down_10_to_15", 0.40)
            else:                     _drawdown_mult = _bands.get("below_15", 0.20)
            effective_regime_cap = effective_regime_cap * _drawdown_mult

    # ── V-4: Earnings + VaR-floor multipliers (Kelly × Regime × Earnings × VaR stack) ──
    # Earnings_mult: shrink size when earnings imminent (binary risk).
    _earn_days = _cfg.get("portfolio", {}).get("_runtime_earn_days_for_ticker")
    _earn_mult = 1.0
    if _earn_days is not None and _earn_days >= 0 and _earn_days <= 14:
        # 0-3d → 0.4×, 4-7d → 0.6×, 8-14d → 0.8×
        if _earn_days <= 3:  _earn_mult = 0.4
        elif _earn_days <= 7: _earn_mult = 0.6
        else:                 _earn_mult = 0.8

    # VaR-floor: don't size above CVaR-implied risk budget.
    # Reads forward CVaR-97.5 (% loss) when injected by build_data; floors size if exposure > VaR budget.
    _var_floor_mult = 1.0
    _cvar_pct = _cfg.get("portfolio", {}).get("_runtime_cvar_975_pct")
    if _cvar_pct is not None and _cvar_pct < 0:  # cvar is negative (loss)
        _cvar_abs = abs(_cvar_pct) / 100
        # Implied max acceptable position: such that CVaR loss ≤ 2× per-trade risk budget
        max_pos_pct_by_cvar = (risk_per_trade_pct * 2) / _cvar_abs if _cvar_abs > 0 else 1.0
        cur_pos_pct = position_value / portfolio_size if portfolio_size > 0 else 0
        if cur_pos_pct > max_pos_pct_by_cvar:
            _var_floor_mult = max_pos_pct_by_cvar / cur_pos_pct if cur_pos_pct > 0 else 1.0

    effective_regime_cap = effective_regime_cap * _earn_mult * _var_floor_mult
    shares_from_risk = math.floor(shares_from_risk * effective_regime_cap)
    position_value = shares_from_risk * price

    # ── Cap 3: liquidity — don't exceed 5% of ADV ──
    if adv_20d > 0 and price > 0:
        max_shares_liquidity = math.floor((adv_20d * 0.05) / price)
        if shares_from_risk > max_shares_liquidity:
            shares_from_risk = max_shares_liquidity
            position_value = shares_from_risk * price

    final_alloc_pct = (position_value / portfolio_size * 100) if portfolio_size > 0 else 0

    return {
        "kelly_pct":        round(kelly_pct * 100, 1),
        "half_kelly_pct":   round(half_kelly_pct * 100, 1),
        "final_alloc_pct":  round(final_alloc_pct, 1),
        "dollar_risk":      round(risk_dollars * effective_regime_cap, 0),
        "suggested_shares": shares_from_risk,
        "position_value":   round(position_value, 0),
        "regime_mult":      regime_mult,
        "regime_max_size_pct": regime_max_size_pct,
        "vix_mult":         _vix_mult if '_vix_mult' in dir() else 1.0,
        "drawdown_mult":    _drawdown_mult if '_drawdown_mult' in dir() else 1.0,
        "drawdown_pct":     _drawdown_pct if '_drawdown_pct' in dir() else None,
        "earnings_mult":    _earn_mult if '_earn_mult' in dir() else 1.0,
        "earnings_days":    _earn_days if '_earn_days' in dir() else None,
        "var_floor_mult":   _var_floor_mult if '_var_floor_mult' in dir() else 1.0,
        "cvar_975_pct":     _cvar_pct if '_cvar_pct' in dir() else None,
        "effective_regime_cap": round(effective_regime_cap, 3),
        "risk_per_trade_pct": risk_per_trade_pct,
        "live_win_rate":    round(win_rate * 100, 1),
        "live_stats_used":  live_win_rate is not None,
        "stack_note": "V-4 stack: kelly_signal × regime × vix × drawdown × earnings × var_floor → effective_cap",
        "note": "Risk-first model: risk$ = equity * risk_pct, shares = risk$ / stop_distance, capped by max_capital, regime, liquidity, vix, drawdown, earnings, var_floor",
    }


# ── Trade Thesis Generator ────────────────────────────────────────────────────

def generate_trade_thesis(ticker: str, plan: dict, indicators: dict,
                          catalysts: list[str], conviction: dict,
                          entry_quality: str) -> str:
    """
    Generate a structured trade thesis paragraph:
    catalyst → confirmation → entry → stop → target → sizing → invalidation
    """
    direction  = plan.get("direction", "long")
    setup      = plan.get("setup_type", "Continuation")
    entry      = plan.get("entry_low", 0)
    stop       = plan.get("stop", 0)
    t1         = plan.get("target1", 0)
    rr         = plan.get("rr_ratio", 0)
    rps        = plan.get("risk_per_share", 0)
    alloc      = plan.get("allocation_pct", 5)
    trend      = indicators.get("trend_direction", "uptrend")
    ema8       = indicators.get("ema8", 0)

    cat_str    = " + ".join(catalysts) if catalysts else "Technical setup"
    dir_word   = "long" if direction == "long" else "short"
    action     = "Buy" if direction == "long" else "Short"
    exit_word  = "below" if direction == "long" else "above"
    move_word  = "rises" if direction == "long" else "falls"

    thesis = (
        f"{ticker} {conviction['label']} {dir_word} — {setup}. "
        f"Catalyst: {cat_str}. "
        f"Confirmation: {trend} with EMA8 at ${ema8:.2f}. "
        f"Entry: ${entry:.2f} ({entry_quality}), "
        f"Stop: ${stop:.2f} (${rps:.2f}/share risk), "
        f"T1: ${t1:.2f} ({rr:.1f}:1 R:R). "
        f"Size: {alloc:.1f}% — {conviction['description']}. "
        f"Invalidation: close {exit_word} ${stop:.2f} or {move_word} <1% in 5 days."
    )
    return thesis


# ── Trade Plan ───────────────────────────────────────────────────────────────

def _classify_setup_type(price: float, ema21: float, ema50: float, indicators: dict, sr: dict) -> str:
    """
    Classify specific setup type string based on price and indicator state.
    More granular than setup families.

    Priority order (first match wins):
    1. VCP Breakout / Near-VCP Breakout — if VCP or near-VCP detected
    2. Pocket Pivot — if pocket pivot detected (institutional accumulation)
    3. EMA21 Pullback — price pulled back to EMA21 and bouncing
    4. EMA50 Pullback — price pulled back to EMA50 and bouncing
    5. Trend Continuation — uptrend, consolidating near highs (within 5% of 52w high)
    6. Squeeze Expansion — TTM Squeeze firing
    7. 52wk Breakout — genuine new breakout above 52w high in last 5 bars only
    8. Tight Range Rebreak
    9. Bounce off Support (fallback)
    """
    support = sr.get("support", price * 0.95)
    atr = indicators.get("atr", price * 0.02)

    near_support_pct = abs(price - support) / price if price > 0 else 1.0
    at_breakout = indicators.get("at_52w_breakout", False)
    squeeze = indicators.get("squeeze_on", False)
    vcp = indicators.get("vcp", False)
    near_vcp = indicators.get("near_vcp", False)
    tight_range = indicators.get("tight_range", False)
    pocket_pivot = indicators.get("pocket_pivot", False)

    # 1. VCP / Near-VCP — highest-probability pattern, always takes priority
    if vcp:
        return "VCP Breakout"
    if near_vcp:
        return "Near-VCP Breakout"

    # 2. Pocket Pivot — institutional accumulation signal near key EMAs
    if pocket_pivot:
        return "Pocket Pivot"

    # 3. EMA21 Pullback — price near EMA21 in an uptrend (higher priority than 52wk breakout)
    if ema21 > 0 and price > 0 and abs(price - ema21) / price < 0.03:
        # Confirm uptrend: EMA21 > EMA50 (if available)
        if ema50 > 0 and ema21 > ema50:
            return "EMA21 Pullback"
        elif ema50 <= 0:
            return "EMA21 Pullback"

    # 4. EMA50 Pullback — price near EMA50 in a broader uptrend
    if ema50 > 0 and price > 0 and abs(price - ema50) / price < 0.04:
        return "EMA50 Pullback"

    # 5. Trend Continuation — in uptrend, consolidating near highs but not a fresh breakout
    if (indicators.get("near_52w_high", False)
            and ema21 > 0 and ema50 > 0 and ema21 > ema50
            and price > ema21
            and not at_breakout):
        return "Trend Continuation"

    # 6. Squeeze Expansion
    if squeeze:
        return "Squeeze Expansion"

    # 7. 52wk Breakout — only for genuine fresh breakouts (within 2% of 52w high)
    #    Many of these were really pullback/continuation setups misclassified
    if at_breakout:
        return "52wk Breakout"

    # 8. Tight Range Rebreak
    if tight_range:
        return "Tight Range Rebreak"

    # 9. Bounce off Support / fallback
    if near_support_pct < 0.025:
        return "Bounce off Support"

    return "Trend Continuation"


# ── Setup Quality / Decision State / Market Phase (Vinod Review) ─────────────

def classify_setup_quality(indicators: dict, plan: dict) -> dict:
    """
    Deterministic setup quality: GOOD / MODERATE / WEAK
    No vague scores — explicit rule groups.
    """
    # AI-1 fix: wrap all bool coercions with bool() — .get("x", False) returns None
    # when key exists with None value, which breaks sum() downstream (killed ~35% of universe).
    _td = indicators.get("trend_direction", "") or ""
    trend_ok = bool(_td and ("uptrend" in _td or "pullback" in _td))
    ema_bull = bool(indicators.get("above_20ema") or indicators.get("above_50ema"))
    weekly_bull = bool(indicators.get("weekly_ema_bullish"))
    group_a = sum([trend_ok, ema_bull, weekly_bull])

    # Group B: Momentum (must pass 2 of 3)
    rsi_ok = bool(40 <= (indicators.get("rsi", 50) or 50) <= 75)
    macd_ok = bool(indicators.get("macd_bullish"))
    adx_ok = bool((indicators.get("adx", 20) or 20) >= 20)
    group_b = sum([rsi_ok, macd_ok, adx_ok])

    # Group C: Strength (must pass 2 of 3)
    rs_ok = bool((indicators.get("rs_rank", 50) or 50) >= 70)
    rvol_ok = bool((indicators.get("rvol", 1.0) or 1.0) >= 0.8)
    obv_ok = bool(indicators.get("obv_rising"))
    group_c = sum([rs_ok, rvol_ok, obv_ok])

    total_groups_passed = sum([group_a >= 2, group_b >= 2, group_c >= 2])

    if total_groups_passed >= 3:
        label = "GOOD"
    elif total_groups_passed >= 2:
        label = "MODERATE"
    else:
        label = "WEAK"

    return {
        "label": label,
        "groups_passed": total_groups_passed,
        "trend": group_a, "momentum": group_b, "strength": group_c,
        "details": {
            "trend_ok": trend_ok, "ema_bull": ema_bull, "weekly_bull": weekly_bull,
            "rsi_ok": rsi_ok, "macd_ok": macd_ok, "adx_ok": adx_ok,
            "rs_ok": rs_ok, "rvol_ok": rvol_ok, "obv_ok": obv_ok,
        }
    }


def effective_buy_min(
    base_buy_min: int,
    market_cycle: "str | None",
    seasonal_adj: "dict | None",
    breadth: "dict | None",
    direction: str,
) -> tuple:
    """Pure function: apply cycle/seasonality/breadth adjustments to buy_min.

    Returns (final_buy_min, breakdown) where breakdown = {
      'base': int, 'cycle_adj': int, 'seasonality_adj': int, 'breadth_adj': int,
      'final': int, 'notes': [str], 'season_note': str, 'breadth_note': str,
      'watch_bump': int  # extra bump that should also be applied to watch_min
    }

    Extracted from classify_decision_state (checklist 7.1) for testability and
    to make the mutation chain explicit. Callers get both the final number and
    a structured breakdown they can log / render into reason strings.
    """
    base = int(base_buy_min)
    cur = base
    notes: list = []

    # AI-43: market-cycle-aware adjustment
    _mc = (market_cycle or "").lower()
    cycle_adj = 0
    if _mc in ("early_bull", "mid_cycle"):
        cycle_adj = max(60, cur - 2) - cur   # floor at 60
        cur = cur + cycle_adj
        if cycle_adj:
            notes.append(f"{_mc} cycle {cycle_adj:+d}")
    elif _mc in ("topping", "capitulation"):
        cycle_adj = max(60, cur + 3) - cur
        cur = cur + cycle_adj
        if cycle_adj:
            notes.append(f"{_mc} cycle {cycle_adj:+d}")

    # AI-44: seasonality nudge
    season_adj = 0
    season_note = ""
    if isinstance(seasonal_adj, dict) and seasonal_adj.get("buy_min_add"):
        _sa = int(seasonal_adj.get("buy_min_add", 0) or 0)
        if _sa:
            new_cur = max(60, min(90, cur + _sa))
            season_adj = new_cur - cur
            cur = new_cur
            season_note = f" [seasonality {_sa:+d}: {seasonal_adj.get('label', '')}]"
            notes.append(f"seasonality {_sa:+d}")

    # Breadth overlay (long direction only, weak breadth → +5)
    breadth_adj = 0
    watch_bump = 0
    breadth_note = ""
    if breadth and direction == "long":
        pct_50 = breadth.get("pct_above_50d", 100)
        if 25 <= pct_50 < 40:
            breadth_adj = 5
            watch_bump = 5
            cur = cur + 5
            breadth_note = f" [breadth weak {pct_50:.0f}%→+5pt bar]"
            notes.append(f"breadth weak {pct_50:.0f}% +5")

    breakdown = {
        "base": base,
        "cycle_adj": int(cycle_adj),
        "seasonality_adj": int(season_adj),
        "breadth_adj": int(breadth_adj),
        "final": int(cur),
        "notes": notes,
        "season_note": season_note,
        "breadth_note": breadth_note,
        "watch_bump": int(watch_bump),
    }
    return int(cur), breakdown


import atexit as _atexit_52wk

# Checklist 7.2: 52wk elite-breakout hit counter (instrumented 2026-04-15).
# Tracks how often the dedicated 52wk elite-breakout gate fires after Wave 1/2B
# migrated most gate logic to config.setup_gates. If hits stay at 0 for ~7 days
# of scans, the block at ~L5471 can be safely deleted.
_52WK_ELITE_HITS: dict = {"evaluated": 0, "demoted_to_watch": 0, "elite_pass": 0}


def _persist_52wk_elite_hits() -> None:
    """Write the 52wk elite-breakout hit counter to cache/52wk_elite_hits.json.
    Called at end of scan; safe no-op on any error."""
    try:
        import json, os
        from datetime import datetime
        _dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
        os.makedirs(_dir, exist_ok=True)
        _path = os.path.join(_dir, "52wk_elite_hits.json")
        # Append-merge with prior counts (keeps cross-scan totals)
        prior = {"evaluated": 0, "demoted_to_watch": 0, "elite_pass": 0, "history": []}
        if os.path.exists(_path):
            try:
                with open(_path, "r") as f:
                    prior = json.load(f) or prior
            except Exception:
                pass
        prior["evaluated"] = int(prior.get("evaluated", 0)) + int(_52WK_ELITE_HITS.get("evaluated", 0))
        prior["demoted_to_watch"] = int(prior.get("demoted_to_watch", 0)) + int(_52WK_ELITE_HITS.get("demoted_to_watch", 0))
        prior["elite_pass"] = int(prior.get("elite_pass", 0)) + int(_52WK_ELITE_HITS.get("elite_pass", 0))
        hist = prior.get("history") or []
        hist.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "delta": dict(_52WK_ELITE_HITS),
        })
        prior["history"] = hist[-50:]  # cap
        with open(_path, "w") as f:
            json.dump(prior, f, indent=2)
    except Exception:
        pass


# Register exit hook so any scan process (swing_trade.py, backtest, deep_dive)
# persists the counter without requiring explicit call-site changes.
try:
    _atexit_52wk.register(_persist_52wk_elite_hits)
except Exception:
    pass


def classify_decision_state(price: float, plan: dict, indicators: dict) -> dict:
    """Classify the current decision state with mutually exclusive ATR-based states.

    Priority order (first match wins):
      LOST_STRUCTURE → MISSED → EXTENDED → AT_SHALLOW_ZONE → AT_ZONE →
      AT_DEEP_ZONE → APPROACHING → NO_EDGE

    Returns dict with 'state' and 'label'.
    """
    atr = indicators.get("atr", price * 0.02) or price * 0.02
    ema21 = indicators.get("ema21", price)
    ema50 = indicators.get("ema50", price * 0.95)

    if price <= 0 or atr <= 0:
        return {"state": "AT_ZONE", "label": "At zone — watch for confirmation"}

    shallow_high = plan.get("shallow_zone_high", ema21)
    shallow_low = plan.get("shallow_zone_low", ema21 - atr * 0.5)
    primary_high = plan.get("primary_zone_high", ema21)
    primary_low = plan.get("primary_zone_low", ema21 - atr)
    deep_high = plan.get("deep_zone_high", ema50 + atr * 0.5)
    deep_low = plan.get("deep_zone_low", ema50 - atr * 0.5)
    stop = plan.get("stop", deep_low)

    # Vinod fix #1: EMA8 (shallow) zone only valid in strong-momentum trends
    # ADX ≥ 30 AND RVOL ≥ 1.5 AND RSI ≥ 60 — else shallow is just an early/late call, not a zone
    _adx = indicators.get("adx", 0) or 0
    _rvol = indicators.get("rvol", 1.0) or 1.0
    _rsi = indicators.get("rsi", 50) or 50
    _strong_momentum = (_adx >= 30) and (_rvol >= 1.5) and (_rsi >= 60)

    # Vinod fix #2: Inside-cloud uncertainty — treat as range until resolved
    _cloud_top = indicators.get("ichimoku_cloud_top") or indicators.get("senkou_span_a")
    _cloud_bot = indicators.get("ichimoku_cloud_bottom") or indicators.get("senkou_span_b")
    _inside_cloud = False
    if _cloud_top is not None and _cloud_bot is not None:
        _lo, _hi = (min(_cloud_top, _cloud_bot), max(_cloud_top, _cloud_bot))
        _inside_cloud = (_lo <= price <= _hi)

    # Priority order — first match wins
    if price < stop:
        state = "LOST_STRUCTURE"
        label = "Price below stop — structure lost, skip this setup"
    elif price > ema21 + 2.0 * atr:
        state = "MISSED"
        label = "Re-entry not available — wait for pullback to value zone"
    elif price > ema21 + 1.25 * atr:
        # Vinod: POST_BREAKOUT_DRIFT — breakout happened but low participation
        _at_52w = indicators.get("at_52w_breakout", False)
        if _rvol < 0.8 and _at_52w:
            state = "POST_BREAKOUT_DRIFT"
            label = "Breakout happened but low volume drift — wait for pullback with volume"
        else:
            state = "EXTENDED"
            label = "Above value — set alert at primary zone, do not chase"
    elif _inside_cloud:
        state = "INSIDE_CLOUD_UNCERTAINTY"
        label = "Inside Ichimoku cloud — treat as range, wait for cloud break"
    elif shallow_low <= price <= shallow_high:
        if _strong_momentum:
            state = "AT_SHALLOW_ZONE"
            label = "Price at EMA8 — strong momentum (ADX≥30, RVOL≥1.5) — early continuation, size smaller"
        else:
            # EMA8 is not a zone in normal trends — redirect
            if primary_low <= price <= primary_high:
                state = "AT_ZONE"
                label = "Price in primary decision zone — watch for confirmation"
            else:
                state = "APPROACHING"
                label = "Near EMA8 but trend not strong enough — wait for pullback to EMA21/value"
    elif primary_low <= price <= primary_high:
        state = "AT_ZONE"
        label = "Price in primary decision zone — watch for confirmation"
    elif deep_low <= price <= deep_high:
        state = "AT_DEEP_ZONE"
        label = "Price at deep zone (EMA50) — high risk/reward if holds"
    elif price > primary_high and price <= ema21 + 1.25 * atr:
        state = "APPROACHING"
        label = "Price pulling back toward decision zone — prepare alert"
    else:
        state = "NO_EDGE"
        label = "No clear edge — price between zones"

    return {"state": state, "label": label}


def compute_zone_quality(plan: dict, indicators: dict) -> dict:
    """Rate the quality of the decision zone based on confluence of supports."""
    quality_points = 0
    reasons = []

    # EMA confluence (do multiple EMAs converge near the zone?)
    ema21 = indicators.get("ema21") or indicators.get("ema_21")
    ema50 = indicators.get("ema50") or indicators.get("ema_50")
    zone_low = plan.get("primary_zone_low", plan.get("stop", 0))
    zone_high = plan.get("primary_zone_high", plan.get("price", 0))
    zone_mid = (zone_low + zone_high) / 2 if zone_low and zone_high else 0

    if zone_mid > 0:
        if ema21 and abs(ema21 - zone_mid) / zone_mid < 0.02:
            quality_points += 2
            reasons.append("EMA21 at zone")
        if ema50 and abs(ema50 - zone_mid) / zone_mid < 0.03:
            quality_points += 2
            reasons.append("EMA50 at zone")

    # Support level confluence
    support = indicators.get("support")
    if support and zone_mid > 0 and abs(support - zone_mid) / zone_mid < 0.02:
        quality_points += 2
        reasons.append("Support at zone")

    # Volume declining on pullback (healthy)
    rvol = indicators.get("rvol", 1.0)
    if rvol and rvol < 0.8:
        quality_points += 1
        reasons.append("Volume dry-up")

    # VWAP near zone
    vwap = indicators.get("vwap")
    if vwap and zone_mid > 0 and abs(vwap - zone_mid) / zone_mid < 0.015:
        quality_points += 1
        reasons.append("VWAP at zone")

    # Order Block at zone (from SMC)
    smc = indicators.get("smc", {})
    ob_entry = smc.get("ob_entry_zone")
    if ob_entry and zone_mid > 0:
        ob_mid = (ob_entry.get("low", 0) + ob_entry.get("high", 0)) / 2
        if ob_mid > 0 and abs(ob_mid - zone_mid) / zone_mid < 0.03:
            quality_points += 2
            reasons.append("Order Block at zone")

    if quality_points >= 6:
        label = "Strong"
    elif quality_points >= 3:
        label = "Moderate"
    else:
        label = "Weak"

    return {"label": label, "points": quality_points, "reasons": reasons}


def compute_reaction_checklist(indicators: dict) -> list:
    """Generate a checklist of quantified confirmation signals at the zone.

    Each check uses precise mathematical thresholds — no subjective labels.
    """
    checklist = []

    # 1. Bullish candle: close > open AND close in upper 40% of range
    close_val = indicators.get("close", 0)
    open_val = indicators.get("open", 0)
    high_val = indicators.get("high", 0)
    low_val = indicators.get("low", 0)
    range_val = high_val - low_val if high_val and low_val else 0
    body_pos = (close_val - low_val) / range_val if range_val > 0 else 0.5
    bullish_candle = bool(close_val and open_val and close_val > open_val and body_pos >= 0.6)
    # Fallback: also check candle pattern if OHLC not in indicators
    if not bullish_candle:
        candle = indicators.get("candle_pattern", "")
        bullish_candle = any(p in str(candle).lower() for p in ["hammer", "engulf", "morning", "pin bar"])
    checklist.append({"item": "Bullish candle (close in upper 40% of range)", "checked": bullish_candle,
                       "detail": f"Body position {body_pos:.0%}" if range_val > 0 else (
                           str(indicators.get("candle_pattern", "Watch for hammer/engulfing")))})

    # 2. Volume expansion: today's volume > 1.2x 20-day average
    rvol = indicators.get("rvol", 1.0) or 1.0
    vol_expand = rvol >= 1.2
    checklist.append({"item": "Volume expansion (>1.2x 20d avg)", "checked": vol_expand,
                       "detail": f"RVOL {rvol:.1f}x" if vol_expand else f"RVOL {rvol:.1f}x — need 1.2x+"})

    # 3. MACD improving: histogram rising for 2+ bars
    macd_hist = indicators.get("macd_histogram", 0) or 0
    macd_hist_prev = indicators.get("macd_histogram_prev", 0) or 0
    macd_hist_prev2 = indicators.get("macd_histogram_prev2", 0) or 0
    macd_improving = (macd_hist > macd_hist_prev and macd_hist_prev > macd_hist_prev2)
    # Fallback to simple macd_bullish if histogram history unavailable
    if not macd_improving and macd_hist == 0:
        macd_improving = bool(indicators.get("macd_bullish", False))
    checklist.append({"item": "MACD histogram rising 2+ bars", "checked": macd_improving,
                       "detail": f"Hist: {macd_hist_prev2:.3f} → {macd_hist_prev:.3f} → {macd_hist:.3f}" if macd_hist != 0 else (
                           "Expanding" if macd_improving else "Waiting for improvement")})

    # 4. Holds zone: daily close above primary_zone_low
    primary_zone_low = indicators.get("primary_zone_low", 0)
    holds_zone = bool(close_val and primary_zone_low and close_val >= primary_zone_low)
    # Fallback: check above EMA21
    if not primary_zone_low:
        above_ema21 = indicators.get("above_20ema", False) or indicators.get("above_21ema", False)
        holds_zone = bool(above_ema21)
    checklist.append({"item": "Price holding above zone low", "checked": holds_zone,
                       "detail": f"Close ${close_val:.2f} vs zone ${primary_zone_low:.2f}" if (
                           close_val and primary_zone_low) else (
                           "Above EMA21" if holds_zone else "Below key level")})

    # 5. RSI turning: crossed above 40 from below, or RSI > 50 and rising
    rsi = indicators.get("rsi", 50) or 50
    rsi_prev = indicators.get("rsi_prev", rsi) or rsi
    rsi_turning = (rsi >= 40 and rsi_prev < 40) or (rsi > 50 and rsi > rsi_prev)
    checklist.append({"item": "RSI turning up (>40 cross or >50 rising)", "checked": rsi_turning,
                       "detail": f"RSI {rsi:.0f} (prev {rsi_prev:.0f})"})

    return checklist


def classify_market_phase(indicators: dict) -> str:
    """Classify the current market phase for a stock.

    Returns one of: Trend, Pullback, Consolidation, Range.
    """
    ema8  = indicators.get("ema8", 0)
    ema21 = indicators.get("ema21", 0)
    ema50 = indicators.get("ema50", 0)
    adx   = indicators.get("adx", 0) or 0
    rsi   = indicators.get("rsi", 50) or 50
    price = indicators.get("close", 0) or ema8 or ema21
    squeeze_on = indicators.get("squeeze_on", False)
    near_high  = indicators.get("near_52w_high", False)

    if not ema8 or not ema21 or not ema50:
        return "Range"

    ema_stacked = ema8 > ema21 > ema50

    # Trend: EMAs stacked, ADX > 25, price making new highs
    if ema_stacked and adx > 25 and (near_high or price > ema8):
        return "Trend"

    # Pullback: price below EMA21 but above EMA50, RSI declining from >50
    if price < ema21 and price > ema50 and rsi < 55:
        return "Pullback"

    # Consolidation: ADX < 20, squeeze on, narrow range
    if adx < 20 and squeeze_on:
        return "Consolidation"
    if adx < 20 and abs(price - ema21) / max(price, 0.01) < 0.02:
        return "Consolidation"

    # Range: no clear direction
    if not ema_stacked and adx < 25:
        return "Range"

    # Default: if EMAs stacked but ADX moderate, still a trend
    if ema_stacked:
        return "Trend"

    return "Range"


def classify_expected_pullback(indicators: dict) -> str:
    """Classify expected pullback depth: Shallow, Normal, or Deep.

    Based on trend strength, ADX, and relative strength.
    """
    adx     = indicators.get("adx", 20) or 20
    rs_rank = indicators.get("rs_rank", 50) or 50
    ema8    = indicators.get("ema8", 0)
    ema21   = indicators.get("ema21", 0)
    ema50   = indicators.get("ema50", 0)

    ema_stacked = (ema8 > ema21 > ema50) if ema8 and ema21 and ema50 else False

    # Shallow (EMA8-13): Strong trend, ADX > 30, RS > 85
    if adx > 30 and rs_rank > 85 and ema_stacked:
        return "Shallow"

    # Normal (EMA21): Moderate trend, ADX 20-30
    if 20 <= adx <= 30 and ema_stacked:
        return "Normal"

    # Deep (EMA50): Weak trend or transition, ADX < 20
    return "Deep"


def compute_trade_plan(ticker: str, df: pd.DataFrame, sr: dict,
                       indicators: dict, direction: str = "long",
                       beta: float | None = None,
                       config: dict | None = None) -> dict:
    """
    Generate mandatory trade plan: entry, stop, targets, setup type.
    No trade without defined stop. No trade without >= 3:1 R:R.
    stop_atr_multiple from config (default 2.0) — wider than noise, tighter than trend.
    """
    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    price = float(close.iloc[-1])
    atr = indicators.get("atr", price * 0.02)

    # Phase 3B: Adaptive stop width by regime and entry quality
    _cfg = config or {}
    _base_stop_mult = float(_cfg.get("scoring", {}).get("stop_atr_multiple", 1.25))  # Phase 3: tightened to 1.25×ATR
    _regime_name = str(_cfg.get("_regime_name", "neutral")).lower()

    # Phase 3B: regime-based stop adaptation
    if _regime_name == "bear":
        stop_mult = max(1.0, _base_stop_mult - 0.25)  # tighter in downtrends
    else:
        stop_mult = _base_stop_mult

    support = sr.get("support", price * 0.95)
    resistance = sr.get("resistance", price * 1.10)

    # Phase 1 (2026-05-10) — structural target sources accumulator. Populated
    # in the long-direction branch below, then attached to plan after plan = {}.
    _target_sources: dict = {}

    if direction == "long":
        # Entry zone: current price to slightly below (pullback entry)
        entry_low = round(price - atr * 0.3, 2)
        entry_high = round(price + atr * 0.2, 2)
        # Phase 3C: entry midpoint for stop calculation (not current price)
        entry_mid = (entry_low + entry_high) / 2

        # Phase 5F: check entry quality for stop adaptation
        # Fix #13: EXTENDED entries no longer get wider stops — they are pure WATCH
        # with standard parameters. The wider stop was encouraging chasing.
        _eq = classify_entry_quality(price, indicators, sr)
        extended_skip = (_eq == "EXTENDED")

        # Phase 3C: Stop relative to entry midpoint — max 1.25×ATR (tightened from 1.5)
        stop = round(max(support - atr * 0.15, entry_mid - atr * min(stop_mult, 1.25)), 2)

        # K1 (2026-05-09): stop confluence with Fibonacci + EMA 50.
        # Vinod feedback: "Stop loss should be a confluence of Fibonacci levels
        # and EMA 50". Snap stop to the nearest of {Fib retracement level, EMA50}
        # that's BELOW current stop (preserve safety) within tolerance.
        try:
            _conf = (_cfg.get("scoring") or {}).get("stop_confluence") or {}
            if _conf.get("enabled", True):
                _ema50 = float(indicators.get("ema50") or 0)
                _fib_levels = _conf.get("fib_levels", [0.382, 0.5, 0.618])
                _tol_pct = float(_conf.get("snap_tolerance_pct", 1.0)) / 100.0
                _swing_high = float(indicators.get("recent_high") or sr.get("recent_high") or price * 1.10)
                _swing_low = float(indicators.get("recent_low") or sr.get("recent_low") or price * 0.85)
                _swing_range = max(_swing_high - _swing_low, atr * 2)
                # Fib retracements from swing_high (longs retrace TO support)
                _fib_stops = [round(_swing_high - _swing_range * f, 2) for f in _fib_levels]
                _candidates = [s for s in _fib_stops + [round(_ema50, 2)] if s and s < entry_mid and s >= entry_mid * 0.85]
                if _candidates:
                    # Pick highest candidate within tolerance of current stop (preserves R:R)
                    _close_to_stop = [c for c in _candidates if abs(c - stop) / max(stop, 1) <= _tol_pct * 5]
                    if _close_to_stop:
                        stop = max(stop, max(_close_to_stop))  # pull stop up to confluence if very close
                    elif min(_candidates) < stop:
                        # All candidates below stop; widen slightly to nearest
                        _below = [c for c in _candidates if c < stop]
                        stop = round(max(_below), 2)
        except Exception:
            pass  # never fail compute_trade_plan due to confluence math

        # K3 (2026-05-09): stop must be AT or BELOW nearest fractal low.
        # Vinod feedback: "Entry and Stop loss numbers does align with fractal low".
        # If the calculated stop is ABOVE the active fractal low (a key swing low
        # the market has been respecting), the stop is too tight — widen down to
        # just below fractal_low so a normal pullback doesn't get stopped out.
        try:
            _fractal_low = indicators.get("fractal_low")
            if _fractal_low and float(_fractal_low) > 0:
                _fl = float(_fractal_low)
                if stop > _fl and _fl > entry_mid * 0.80:  # sanity: don't widen >20%
                    stop = round(_fl - atr * 0.10, 2)  # just below fractal low (small buffer)
        except Exception:
            pass

        # Phase 3A: Resistance-aware targets
        risk = entry_mid - stop
        _raw_t1 = entry_mid + risk * 3.0  # ideal 3:1
        _upside_to_resist = resistance - price
        # If resistance is closer than 3:1, use resistance as T1 and compute actual R:R
        if _upside_to_resist > 0 and _upside_to_resist < risk * 3.0 and _upside_to_resist > risk * 2.0:
            target1 = round(resistance * 0.99, 2)  # just below resistance
        else:
            target1 = round(_raw_t1, 2)
        target2 = round(entry_mid + risk * 5.0, 2)

        # Determine setup type using the helper
        ema21 = indicators.get("ema21", price)
        ema50 = indicators.get("ema50", price)
        rsi = indicators.get("rsi", 50)

        setup = _classify_setup_type(price, ema21, ema50, indicators, sr)

        rr_ratio = round((target1 - entry_mid) / max(entry_mid - stop, 0.01), 1)

        # EMA21 Pullback: tightened stop per 2026-05-06 signal_tracker analysis.
        # Winners bounce immediately (avg MAE -0.36%); losers crater (avg MAE -7.47%).
        # 1.5% stop kills bad trades fast, preserves winners' +7.15% MFE upside.
        if setup == "EMA21 Pullback":
            stop = round(entry_mid * 0.985, 2)
            risk = entry_mid - stop
            target1 = round(entry_mid + risk * 3.0, 2)
            target2 = round(entry_mid + risk * 5.0, 2)
            rr_ratio = round((target1 - entry_mid) / max(entry_mid - stop, 0.01), 1)

        # K5 (2026-05-09): Elliott Wave Fib-extension targets when Wave 3 Impulse detected.
        # Vinod feedback (HPE): "we are at a Wave3 (Impulse): T1=50.37, T2=55.75"
        # T1/T2 derived from Fib extensions of the most recent (swing_low → swing_high) impulse.
        # Override default ATR/resistance-based targets when Wave 3 is detected with
        # at least medium confidence.
        _ew_data = None
        _ew_bhe = None
        try:
            _ew_cfg = (_cfg.get("scoring") or {}).get("elliott_wave") or {}
            if _ew_cfg.get("enabled", True):
                _ew_fib = _ew_cfg.get("fib_extensions", [1.272, 1.618])
                _ew_data = classify_elliott_wave(df, fib_extensions=_ew_fib)
                if (_ew_data.get("wave") == 3 and _ew_data.get("type") == "impulse"
                        and _ew_data.get("confidence") in ("high", "medium")
                        and _ew_data.get("t1_extension") and _ew_data.get("t2_extension")):
                    _t1_ew = float(_ew_data["t1_extension"])
                    _t2_ew = float(_ew_data["t2_extension"])
                    # Only override if EW targets are higher (more aspirational) than current
                    # and within reason (≤ 50% above current price)
                    if _t1_ew > target1 and _t1_ew <= price * 1.50:
                        target1 = round(_t1_ew, 2)
                    if _t2_ew > target2 and _t2_ew <= price * 2.00:
                        target2 = round(_t2_ew, 2)
                    rr_ratio = round((target1 - entry_mid) / max(entry_mid - stop, 0.01), 1)

            # 2026-05-10 — BHE Rule Gate v1.0 EW classifier (Phase 1, display-only).
            # Runs in parallel to legacy classifier. Output stored on plan as
            # `elliott_wave_v1` for canonical_trade_plan + Models tab display.
            # Does NOT alter target1/target2 in this Phase 1 release.
            try:
                _ew_bhe = classify_elliott_wave_bhe(df, current_price=price)
            except Exception:
                _ew_bhe = None
        except Exception:
            pass  # never fail trade_plan due to EW classifier

        # ── Phase 1 (2026-05-10) — STRUCTURAL TARGET SOURCES ──
        # Aggregate target candidates from multiple objective TA sources WITHOUT
        # changing the actual T1/T2 used by the engine. Display-only field on
        # plan for the Trade Plan strip + canonical_trade_plan.target_sources.
        # Sources by horizon:
        #   short  (2-5d):   fractal_high (above price)
        #   medium (5-15d):  fib extension on swing (4H/Daily — daily here)
        #   long   (15-30d): EW BHE Intermediate (Wave-3 1.618×W1 = T1)
        try:
            # _target_sources dict initialized at outer function scope above
            # (so the post-plan-init assignment can find it).

            # Source 1 — fractal high above current price (short-term magnetic level)
            try:
                _frac = _williams_fractals(df, lookback=60)
                # _williams_fractals returns recent_highs/recent_lows (lists) +
                # active_high/active_low (nearest unbroken). Prefer active_high
                # if present (already unbroken-filtered), else compute manually.
                if _frac.get("active_high") and _frac["active_high"] > price * 1.005:
                    _target_sources["fractal_high"] = {
                        "horizon": "short",
                        "level": round(float(_frac["active_high"]), 2),
                        "rationale": "nearest unbroken fractal high (Williams 5-bar)",
                    }
                else:
                    _frac_highs = _frac.get("recent_highs") or []
                    _above = [h for h in _frac_highs if isinstance(h, (int, float)) and h > price * 1.005]
                    if _above:
                        _target_sources["fractal_high"] = {
                            "horizon": "short",
                            "level": round(min(_above), 2),
                            "rationale": "nearest fractal high above current price",
                        }
            except Exception:
                pass

            # Source 2 — fib extension on swing (medium-term)
            try:
                _swing_high_2 = float(indicators.get("recent_high") or sr.get("recent_high") or 0)
                _swing_low_2  = float(indicators.get("recent_low")  or sr.get("recent_low")  or 0)
                if _swing_high_2 > _swing_low_2 > 0:
                    _swing_range_2 = _swing_high_2 - _swing_low_2
                    # 1.272 fib extension as medium-term target
                    _fib_target = round(_swing_low_2 + _swing_range_2 * 1.272, 2)
                    if _fib_target > price * 1.005:
                        _target_sources["fib_127_extension"] = {
                            "horizon": "medium",
                            "level": _fib_target,
                            "rationale": f"127.2% fib extension of swing {_swing_low_2:.2f}→{_swing_high_2:.2f}",
                        }
                    # 1.618 fib extension
                    _fib_target_2 = round(_swing_low_2 + _swing_range_2 * 1.618, 2)
                    if _fib_target_2 > price * 1.005:
                        _target_sources["fib_162_extension"] = {
                            "horizon": "medium",
                            "level": _fib_target_2,
                            "rationale": f"161.8% fib extension of swing {_swing_low_2:.2f}→{_swing_high_2:.2f}",
                        }
            except Exception:
                pass

            # Source 3 — EW BHE Intermediate-degree targets (medium/long horizon)
            if _ew_bhe and _ew_bhe.get("t1") and _ew_bhe.get("t1") > price * 1.005:
                _target_sources["ew_intermediate_t1"] = {
                    "horizon": "medium",
                    "level": round(float(_ew_bhe["t1"]), 2),
                    "rationale": f"EW BHE {_ew_bhe.get('ew_state','?')} — Wave-3 1.618×W1 from W2 low",
                }
            if _ew_bhe and _ew_bhe.get("t2") and _ew_bhe.get("t2") > price * 1.005:
                _target_sources["ew_intermediate_t2"] = {
                    "horizon": "long",
                    "level": round(float(_ew_bhe["t2"]), 2),
                    "rationale": f"EW BHE {_ew_bhe.get('ew_state','?')} — Wave-3 2.618×W1 from W2 low",
                }

            # Phase 1: target_sources will be attached to `plan` AFTER it's
            # initialized (plan = {...} happens later at line ~6135).
            # We just build the dict here in local scope for the long branch.
        except Exception:
            pass  # phase 1 is informational; never fail plan

        # Phase 3D: Trade plan coherence validation
        if stop >= entry_mid:
            stop = round(entry_mid - atr * 1.0, 2)  # force stop below entry
        if target1 <= entry_mid:
            target1 = round(entry_mid + atr * 2.0, 2)  # force target above entry
            rr_ratio = round((target1 - entry_mid) / max(entry_mid - stop, 0.01), 1)

    else:  # short
        entry_low = round(price - atr * 0.2, 2)
        entry_high = round(price + atr * 0.3, 2)
        entry_mid = (entry_low + entry_high) / 2
        stop = round(min(resistance + atr * 0.3, entry_mid + atr * 1.5), 2)
        risk = stop - entry_mid
        target1 = round(entry_mid - risk * 3.0, 2)
        target2 = round(entry_mid - risk * 5.0, 2)
        setup = "Breakdown"
        rr_ratio = round((entry_mid - target1) / max(stop - entry_mid, 0.01), 1)
        # Phase 3D: coherence
        if stop <= entry_mid:
            stop = round(entry_mid + atr * 1.0, 2)
        if target1 >= entry_mid:
            target1 = round(entry_mid - atr * 2.0, 2)

    # Beta-adjusted position sizing multiplier
    # 1/beta keeps dollar-volatility exposure constant across positions
    beta_val = float(beta) if beta and beta > 0 else 1.0
    beta_adj = round(1.0 / max(beta_val, 0.3), 2)

    # Price tier classification (matches config.json filters.price_tiers)
    if price <= 50:
        price_tier = "$2–$50"
    elif price <= 100:
        price_tier = "$50–$100"
    else:
        price_tier = "$100–$250"

    # Decision Zones (Vinod Review #1) — Multi-factor confluence zones
    # Uses: EMA cluster, support/resistance, Fibonacci retracement, VWAP, Order Blocks
    _ema21_val = indicators.get("ema21", price)
    _ema50_val = indicators.get("ema50", price * 0.95)
    _ema200_val = indicators.get("ema200") or indicators.get("sma200") or (price * 0.90)
    _sup_val   = support
    _vwap_val  = indicators.get("vwap") or indicators.get("vwap_20d") or price

    # Fibonacci retracement of recent swing (last 50 bars)
    _fib_382 = None
    _fib_500 = None
    _fib_618 = None
    try:
        _recent_high = float(df["High"].iloc[-50:].max())
        _recent_low = float(df["Low"].iloc[-50:].min())
        _swing_range = _recent_high - _recent_low
        if _swing_range > 0 and direction == "long":
            _fib_382 = round(_recent_high - _swing_range * 0.382, 2)
            _fib_500 = round(_recent_high - _swing_range * 0.500, 2)
            _fib_618 = round(_recent_high - _swing_range * 0.618, 2)
        elif _swing_range > 0:  # short
            _fib_382 = round(_recent_low + _swing_range * 0.382, 2)
            _fib_500 = round(_recent_low + _swing_range * 0.500, 2)
            _fib_618 = round(_recent_low + _swing_range * 0.618, 2)
    except Exception:
        pass

    # Order Block zone from SMC (if available)
    _ob_zone_low = None
    _ob_zone_high = None
    _smc = indicators.get("smc", {})
    _ob_entry = _smc.get("ob_entry_zone")
    if isinstance(_ob_entry, dict):
        _ob_zone_low = _ob_entry.get("low")
        _ob_zone_high = _ob_entry.get("high")

    # Collect all zone anchor points and cluster them
    _ema8_val = indicators.get("ema8", price)
    _adx_val = indicators.get("adx", 20) or 20
    _rvol_val = indicators.get("rvol", 1.0) or 1.0
    _rsi_val = indicators.get("rsi", 50) or 50

    if direction == "long":
        _zone_anchors = []
        for val, label in [
            (_ema21_val, "EMA21"), (_ema50_val, "EMA50"), (_sup_val, "Support"),
            (_vwap_val, "VWAP"), (_fib_382, "Fib 38.2%"), (_fib_500, "Fib 50%"),
            (_ob_zone_low, "OB Low"), (_ob_zone_high, "OB High"),
        ]:
            if val and val < price * 1.03 and val > price * 0.85:  # within 3% above to 15% below
                _zone_anchors.append((val, label))

        _zone_anchors.sort(key=lambda x: x[0], reverse=True)  # highest first

        # ── Shallow zone: within 0.5 ATR of EMA8 ──
        # Only valid for strong trends (ADX >= 30, RVOL >= 1.5, RSI >= 60)
        _shallow_eligible = (_adx_val >= 30 and _rvol_val >= 1.5 and _rsi_val >= 60)
        if _shallow_eligible and _ema8_val:
            shallow_zone_high = round(_ema8_val + atr * 0.25, 2)
            shallow_zone_low = round(_ema8_val - atr * 0.25, 2)
        else:
            # Not eligible — set shallow zone to a degenerate range (never triggers)
            shallow_zone_high = round(_ema8_val + atr * 0.1, 2) if _ema8_val else round(price, 2)
            shallow_zone_low = round(_ema8_val - atr * 0.1, 2) if _ema8_val else round(price, 2)

        # ── Primary zone: within 1.0 ATR of EMA21 or support (whichever has more confluence) ──
        # Count confluence near EMA21 vs near support
        _ema21_confluence = sum(1 for v, l in _zone_anchors
                                if v and _ema21_val and abs(v - _ema21_val) <= atr * 1.0)
        _sup_confluence = sum(1 for v, l in _zone_anchors
                              if v and _sup_val and abs(v - _sup_val) <= atr * 1.0)
        _primary_anchor = _ema21_val if _ema21_confluence >= _sup_confluence else _sup_val

        if _zone_anchors:
            # Cluster anchors within 1.0 ATR of primary anchor
            _primary_points = [v for v, l in _zone_anchors
                               if abs(v - _primary_anchor) <= atr * 1.0]
            if _primary_points:
                primary_zone_high = round(max(_primary_points) + atr * 0.15, 2)
                primary_zone_low = round(min(_primary_points) - atr * 0.15, 2)
            else:
                primary_zone_high = round(_primary_anchor + atr * 0.5, 2)
                primary_zone_low = round(_primary_anchor - atr * 0.5, 2)

            # ── Deep zone: within 1.0 ATR of EMA50 or structure low ──
            _structure_low = _sup_val if _sup_val < _ema50_val else _ema50_val
            _deep_points = [v for v, l in _zone_anchors
                            if v < primary_zone_low and abs(v - _structure_low) <= atr * 1.0]
            if _deep_points:
                deep_zone_high = round(max(_deep_points) + atr * 0.1, 2)
                deep_zone_low = round(min(_deep_points) - atr * 0.1, 2)
            else:
                deep_zone_high = round(_ema50_val + atr * 0.5, 2)
                deep_zone_low = round(_ema50_val - atr * 0.5, 2)
        else:
            primary_zone_high = round(_ema21_val + atr * 0.5, 2)
            primary_zone_low = round(_ema21_val - atr * 0.5, 2)
            deep_zone_high = round(_ema50_val + atr * 0.5, 2)
            deep_zone_low = round(_ema50_val - atr * 0.5, 2)

        # ── Zone confluence: at least 2 anchors within 1.0 ATR of each other ──
        _zone_reasons = [l for v, l in _zone_anchors
                         if abs(v - (primary_zone_high + primary_zone_low) / 2) <= atr * 1.0]

    else:  # short zones (mirror logic)
        _zone_anchors = []
        for val, label in [
            (_ema21_val, "EMA21"), (_ema50_val, "EMA50"), (resistance, "Resistance"),
            (_vwap_val, "VWAP"), (_fib_382, "Fib 38.2%"), (_fib_500, "Fib 50%"),
        ]:
            if val and val > price and val < price * 1.15:
                _zone_anchors.append((val, label))

        _zone_anchors.sort(key=lambda x: x[0])

        # Shallow zone for shorts (mirror of long)
        shallow_zone_low = round(_ema8_val - atr * 0.25, 2) if _ema8_val else round(price, 2)
        shallow_zone_high = round(_ema8_val + atr * 0.25, 2) if _ema8_val else round(price, 2)

        if _zone_anchors:
            _primary_center = _zone_anchors[0][0]
            _primary_points = [v for v, l in _zone_anchors if abs(v - _primary_center) / price < 0.025]
            primary_zone_low = round(min(_primary_points) - atr * 0.15, 2)
            primary_zone_high = round(max(_primary_points) + atr * 0.15, 2)
            _deep_points = [v for v, l in _zone_anchors if v > primary_zone_high and v < price * 1.15]
            if _deep_points:
                deep_zone_low = round(min(_deep_points) - atr * 0.1, 2)
                deep_zone_high = round(max(_deep_points) + atr * 0.1, 2)
            else:
                deep_zone_low = primary_zone_high
                deep_zone_high = round(primary_zone_high + atr * 0.75, 2)
        else:
            primary_zone_low = round(_ema21_val - atr * 0.15, 2)
            primary_zone_high = round(_ema21_val + atr * 0.5, 2)
            deep_zone_low = primary_zone_high
            deep_zone_high = round(_ema50_val + atr * 0.15, 2)

        _zone_reasons = [l for v, l in _zone_anchors if abs(v - (primary_zone_high + primary_zone_low)/2) / price < 0.03]

    # Ensure zones are valid (low < high)
    if shallow_zone_low >= shallow_zone_high:
        shallow_zone_low = round(shallow_zone_high - atr * 0.2, 2)
    if primary_zone_low >= primary_zone_high:
        primary_zone_low = round(primary_zone_high - atr * 0.3, 2)
    if deep_zone_low >= deep_zone_high:
        deep_zone_low = round(deep_zone_high - atr * 0.3, 2)

    # Expected pullback type (Vinod Review #4)
    expected_pullback = classify_expected_pullback(indicators)

    plan = {
        "ticker": ticker,
        "direction": direction,
        "entry_zone": f"${entry_low} - ${entry_high}",
        "entry_low": entry_low,
        "entry_high": entry_high,
        "shallow_zone_low": shallow_zone_low,
        "shallow_zone_high": shallow_zone_high,
        "primary_zone_low": primary_zone_low,
        "primary_zone_high": primary_zone_high,
        "deep_zone_low": deep_zone_low,
        "deep_zone_high": deep_zone_high,
        "zone_confluence": _zone_reasons if '_zone_reasons' in dir() else [],
        "fib_382": _fib_382,
        "fib_500": _fib_500,
        "fib_618": _fib_618,
        "expected_pullback": expected_pullback,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "setup_type": setup,
        "rr_ratio": rr_ratio,
        "risk_per_share": round(abs(price - stop), 2),
        "price": price,
        "price_tier": price_tier,
        "beta": beta_val,
        "beta_adj_multiplier": beta_adj,
    }

    # Exit Rules Engine — setup-family-specific exits (Fix #19)
    exit_rules = []
    try:
        atr_val  = float(indicators.get("atr", price * 0.02)) if indicators else price * 0.02
        ema8_val = float(indicators.get("ema8", price * 0.98)) if indicators else price * 0.98
        entry_p  = float(plan.get("entry_low", price))
        stop_p   = float(plan.get("stop", price))
        t1_p     = float(plan.get("target1", price))
        be_stop  = round(entry_p * 1.005, 2) if direction == "long" else round(entry_p * 0.995, 2)

        # Resolve setup-family-specific exit parameters from config
        _exit_cfg = (config or {}).get("exit_rules", {})
        # Map setup type to family key
        _setup_lower = setup.lower().replace(" ", "_")
        _family_key = None
        for _fk in ["impulse_catalyst", "breakout_expansion", "trend_continuation", "special_situation"]:
            if _fk.replace("_", " ") in _setup_lower or _fk in _setup_lower:
                _family_key = _fk
                break
        # Fallback: guess from setup characteristics
        if not _family_key:
            if any(kw in _setup_lower for kw in ["catalyst", "pead", "impulse", "earnings", "pocket_pivot", "pocket pivot"]):
                _family_key = "impulse_catalyst"
            elif any(kw in _setup_lower for kw in ["breakout", "vcp", "near-vcp", "near_vcp", "expansion", "cup"]):
                _family_key = "breakout_expansion"
            elif any(kw in _setup_lower for kw in ["continuation", "pullback", "trend", "flag"]):
                _family_key = "trend_continuation"
            else:
                _family_key = "special_situation"

        _family_exit = _exit_cfg.get(_family_key, {})
        _trail_activate = _family_exit.get("trail_activate_pct", 2.0)
        _trail_atr_mult = _family_exit.get("trail_atr_mult", 1.25)
        _partial_pct    = _family_exit.get("partial_at_t1_pct", 50)
        _time_stop_days = _family_exit.get("time_stop_days", 8)

        # Fix #27: Family-specific time stops from config (overrides exit_rules time_stop_days)
        _time_stops_cfg = (config or {}).get("time_stops", {}).get(_family_key, {})
        if _time_stops_cfg:
            _time_stop_days = _time_stops_cfg.get("max_hold", _time_stop_days)
        _flat_exit_after = _time_stops_cfg.get("flat_exit_after", max(3, _time_stop_days // 3))

        # Store family exit params in plan for downstream use
        plan["exit_family"] = _family_key
        plan["exit_params"] = {
            "trail_activate_pct": _trail_activate,
            "trail_atr_mult": _trail_atr_mult,
            "partial_at_t1_pct": _partial_pct,
            "time_stop_days": _time_stop_days,
            "flat_exit_after": _flat_exit_after,
        }

        if direction == "long":
            exit_rules = [
                f"Rule 1 — Hard Stop: Exit ALL at ${stop_p:.2f} immediately — no exceptions, no averaging down",
                f"Rule 2a — Flat Exit: Exit ALL after Day {_flat_exit_after} if position is flat (< +1% from ${entry_p:.2f}) [{_family_key}]",
                f"Rule 2b — Time Stop: Exit ALL by Day {_time_stop_days} regardless of P&L [{_family_key}]",
                f"Rule 3 — T1 Partial: Sell {_partial_pct}% at T1 ${t1_p:.2f}, move stop to breakeven ${be_stop:.2f} on remainder",
                f"Rule 4 — Trailing Stop: Activate at +{_trail_activate:.1f}%, trail by {_trail_atr_mult:.2f}x ATR (${atr_val * _trail_atr_mult:.2f})",
                f"Rule 5 — Trend Break: Exit ALL if daily close below 8 EMA (currently ~${ema8_val:.2f})",
                f"Rule 6 — Reversal Candle: Exit at open if shooting star or bearish engulfing prints at resistance",
                f"Rule 7 — Gap Down: Exit at open if stock gaps down >3% from prior close — news has hit, don't wait for stop",
            ]
        else:
            exit_rules = [
                f"Rule 1 — Hard Stop: Cover ALL at ${stop_p:.2f} immediately — no exceptions",
                f"Rule 2a — Flat Exit: Cover ALL after Day {_flat_exit_after} if flat (< +1% from ${entry_p:.2f}) [{_family_key}]",
                f"Rule 2b — Time Stop: Cover ALL by Day {_time_stop_days} regardless of P&L [{_family_key}]",
                f"Rule 3 — T1 Partial: Cover {_partial_pct}% at T1 ${t1_p:.2f}, move stop to breakeven ${be_stop:.2f}",
                f"Rule 4 — Trailing Stop: Activate at +{_trail_activate:.1f}%, trail by {_trail_atr_mult:.2f}x ATR (${atr_val * _trail_atr_mult:.2f})",
                f"Rule 5 — Bounce Signal: Cover if RSI drops below 35 (oversold — likely snap back)",
                f"Rule 6 — Reversal Candle: Cover at open if hammer or bullish engulfing prints at support",
                f"Rule 7 — Gap Up: Cover at open if stock gaps up >3% from prior close — squeeze may be exhausted",
            ]
    except Exception:
        pass
    plan["exit_rules"] = exit_rules

    # K5 (2026-05-09): expose Elliott Wave dict so Models tab can display it.
    # _ew_data is set inside the long-direction branch above when applicable.
    # 2026-05-10: also expose the BHE Rule Gate v1.0 classifier output
    # (8-state engine, 3 absolute rules, multi-timeframe ready).
    if direction == "long":
        try:
            plan["elliott_wave_v1"] = _ew_bhe   # NEW — BHE Rule Gate v1.0
            # Phase 1 (2026-05-10) — attach structural target sources
            if _target_sources:
                plan["target_sources"] = _target_sources
        except Exception:
            pass
        try:
            plan["elliott_wave"] = _ew_data
        except NameError:
            pass

    # K2 (2026-05-09): VWAP/AVWAP-below-stop validation flag.
    # Vinod feedback: "VWAP & AVWAP are below stop loss" — if either is below
    # the stop, the stop placement is likely wrong (stop is too high). Emit a
    # risk_flag so decision_engine can surface it; do NOT auto-fail (some
    # strategies legitimately have stops above VWAP), but the flag bubbles up.
    try:
        _stop_val = plan.get("stop") or 0
        _vwap_val_check = indicators.get("vwap") or indicators.get("vwap_20d")
        _avwap_val_check = indicators.get("avwap_swing_low") or indicators.get("avwap_anchor_low")
        risk_flags = list(plan.get("risk_flags") or [])
        if direction == "long" and _stop_val:
            if _vwap_val_check and _vwap_val_check < _stop_val:
                risk_flags.append({
                    "name": "vwap_below_stop",
                    "severity": "high",
                    "detail": f"VWAP ${_vwap_val_check:.2f} < stop ${_stop_val:.2f} — stop placement likely too tight"
                })
            if _avwap_val_check and _avwap_val_check < _stop_val:
                risk_flags.append({
                    "name": "avwap_below_stop",
                    "severity": "high",
                    "detail": f"AVWAP ${_avwap_val_check:.2f} < stop ${_stop_val:.2f} — anchored VWAP below stop indicates weak structure"
                })
        if risk_flags:
            plan["risk_flags"] = risk_flags
    except Exception:
        pass

    return plan


# ── Horizon scoring (1-3 month + long-term) ─────────────────────────────────
# Added 2026-04-24 for new Trades sub-tabs. Both scorers run over the full
# post-price-filter universe (all_results + killed), not just BUY candidates,
# because medium/long-term picks are often boring stable names that get
# killed by short-term gates (low RVOL, no near-term catalyst).

def _pct_rank(value: float | None, series) -> float | None:
    """Return percentile rank (0-100) of value within the given series."""
    try:
        import numpy as np
        if value is None or series is None or len(series) < 30:
            return None
        arr = np.asarray(series, dtype=float)
        arr = arr[~np.isnan(arr)]
        if len(arr) < 30:
            return None
        return float((arr < value).sum()) / len(arr) * 100
    except Exception:
        return None


def score_medium_term(df: "pd.DataFrame", info: dict | None,
                      schwab_fund: dict | None, weekly_df: "pd.DataFrame | None",
                      sector_etf_data: dict | None, spy_df: "pd.DataFrame | None") -> dict:
    """Score a ticker for a 1-3 month hold.

    Emphasizes medium-term trend strength + sector rotation + baseline quality.
    Less weight on short-term RVOL/RSI than the main scorer; more weight on
    weekly EMA stack and 63-day relative strength.

    Returns {score 0-100, verdict BUY/WATCH/AVOID, breakdown dict}.
    """
    info = info or {}
    sf   = schwab_fund or {}
    breakdown: dict = {}
    total = 0

    close = df["Close"].squeeze() if df is not None and "Close" in df else None
    if close is None or len(close) < 63:
        return {"score": 0, "verdict": "AVOID", "breakdown": {"gate": "insufficient_history"}}

    # ── 1. 63-day RS vs SPY (25 pts) ──
    try:
        if spy_df is not None and len(spy_df) >= 63:
            stk_ret = float(close.iloc[-1]) / float(close.iloc[-63]) - 1
            spy_ret = float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-63]) - 1
            rs = stk_ret - spy_ret
            if   rs >=  0.15: pts = 25
            elif rs >=  0.08: pts = 20
            elif rs >=  0.03: pts = 15
            elif rs >=  0.00: pts = 8
            else:             pts = 0
            total += pts
            breakdown["rs_63d"] = {"pts": pts, "max": 25, "value": round(rs * 100, 1)}
    except Exception:
        breakdown["rs_63d"] = {"pts": 0, "max": 25, "value": None}

    # ── 2. Weekly EMA21 > EMA50 stack (20 pts) ──
    try:
        wc = weekly_df["Close"].squeeze() if weekly_df is not None and "Close" in weekly_df else None
        if wc is not None and len(wc) >= 50:
            e21 = float(wc.ewm(span=21, adjust=False).mean().iloc[-1])
            e50 = float(wc.ewm(span=50, adjust=False).mean().iloc[-1])
            wprice = float(wc.iloc[-1])
            if wprice > e21 > e50:      pts = 20
            elif wprice > e21 and wprice > e50: pts = 14
            elif wprice > e50:          pts = 8
            else:                        pts = 0
            total += pts
            breakdown["weekly_stack"] = {"pts": pts, "max": 20,
                                          "price": round(wprice, 2), "e21": round(e21, 2), "e50": round(e50, 2)}
    except Exception:
        breakdown["weekly_stack"] = {"pts": 0, "max": 20}

    # ── 3. Sector trend strength (15 pts) ──
    try:
        sector_etf = (info.get("sector_etf") or "").upper()
        sec_info = (sector_etf_data or {}).get(sector_etf, {})
        sec_perf = sec_info.get("perf_3mo") or sec_info.get("perf_63d")
        if sec_perf is None and sec_info.get("breakout"):
            sec_perf = 5.0
        if sec_perf is not None:
            if   sec_perf >= 8: pts = 15
            elif sec_perf >= 4: pts = 10
            elif sec_perf >= 0: pts = 5
            else:               pts = 0
            total += pts
            breakdown["sector_trend"] = {"pts": pts, "max": 15, "sector_perf_3mo": sec_perf}
        else:
            breakdown["sector_trend"] = {"pts": 0, "max": 15}
    except Exception:
        breakdown["sector_trend"] = {"pts": 0, "max": 15}

    # ── 4. Quality composite (15 pts) — Schwab margins + ROE ──
    try:
        roe  = sf.get("roe")
        gm   = sf.get("gross_margin")
        nm   = sf.get("net_margin")
        pts = 0
        if roe is not None and roe >= 15:    pts += 6
        elif roe is not None and roe >= 5:   pts += 3
        if gm is not None and gm >= 40:      pts += 5
        elif gm is not None and gm >= 25:    pts += 3
        if nm is not None and nm >= 10:      pts += 4
        elif nm is not None and nm >= 3:     pts += 2
        total += pts
        breakdown["quality"] = {"pts": pts, "max": 15, "roe": roe, "gross_margin": gm, "net_margin": nm}
    except Exception:
        breakdown["quality"] = {"pts": 0, "max": 15}

    # ── 5. Distance from 50 EMA — prefer within 10% (15 pts) ──
    try:
        price = float(close.iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        dist_pct = (price - ema50) / ema50 * 100
        if -2 <= dist_pct <= 8:   pts = 15   # healthy pullback or modest premium
        elif -5 <= dist_pct < -2: pts = 12
        elif 8 < dist_pct <= 15:  pts = 10
        elif dist_pct < -5:       pts = 5     # under 50 = weak
        else:                     pts = 3     # very extended
        total += pts
        breakdown["dist_ema50"] = {"pts": pts, "max": 15, "dist_pct": round(dist_pct, 1)}
    except Exception:
        breakdown["dist_ema50"] = {"pts": 0, "max": 15}

    # ── 6. EPS growth TTM (10 pts) ──
    try:
        eps_chg = sf.get("eps_change_pct_ttm")
        if eps_chg is None:
            pts = 0
        elif eps_chg >= 20:  pts = 10
        elif eps_chg >= 10:  pts = 7
        elif eps_chg >=  0:  pts = 4
        else:                pts = 0
        total += pts
        breakdown["eps_growth_ttm"] = {"pts": pts, "max": 10, "value": eps_chg}
    except Exception:
        breakdown["eps_growth_ttm"] = {"pts": 0, "max": 10}

    score = max(0, min(100, total))
    # Raw verdict (pre-gate) — the gating function tightens this with hard rules
    raw_verdict = "BUY" if score >= 70 else ("WATCH" if score >= 60 else "AVOID")
    return {"score": score, "verdict": raw_verdict, "breakdown": breakdown}


def apply_position_gates(mt_result: dict, r: dict, cfg: dict | None = None,
                          weekly_df: "pd.DataFrame | None" = None,
                          is_held: bool = False) -> dict:
    """
    Apply hard + soft gates to Position-mode raw score (P1.1, P1.2 from feedback).

    Inputs:
      mt_result — output of score_medium_term {score, verdict, breakdown}
      r         — full ticker result dict (has regime, earnings, trade_plan,
                  entry_quality, sector, etc.)
      cfg       — config dict
      weekly_df — weekly OHLCV for weekly RSI check
      is_held   — True if ticker is in current portfolio (enables ADD verdict)

    Returns:
      {score, verdict, gate_status, gate_reasons[], breakdown}
      verdict ∈ {BUY, ADD, WATCH, AVOID}
        BUY   — clean entry: score≥70 + FRESH/PULLBACK + sector strong + all hard gates pass
        ADD   — held position passing trend + score ≥ 60 (separate stream — pyramid signal)
        WATCH — qualifies on score but failed a soft gate (entry, sector, R:R)
        AVOID — score < 60 OR hard gate failed
    """
    cfg = cfg or {}
    score = mt_result.get("score", 0)
    breakdown = dict(mt_result.get("breakdown", {}))
    pos_cfg = (cfg.get("position_gates") or {})
    reasons: list[str] = []
    soft_fail = False

    # ── HARD GATES — any failure → AVOID regardless of score ────────────────

    # 1. Earnings blackout — block new BUY within 5 trading days of earnings
    earnings = r.get("earnings") or {}
    days_to_earn = earnings.get("days_to_earnings")
    earn_blackout = pos_cfg.get("earnings_blackout_days", 5)
    if days_to_earn is not None and isinstance(days_to_earn, (int, float)):
        if 0 <= days_to_earn <= earn_blackout:
            reasons.append(f"HARD: earnings in {days_to_earn}d (blackout {earn_blackout}d)")
            return _position_verdict_result(score, "AVOID", "earnings_blackout", reasons, breakdown)

    # 2. Regime gate — block BUY in bear/risk-off (allow defensive sectors only)
    regime = r.get("regime") or {}
    regime_label = (regime.get("regime") or "").lower()
    regime4 = (regime.get("regime4") or "").lower()
    sector_etf = ((r.get("info") or {}).get("sector_etf") or "").upper()
    defensive_etfs = {"XLU", "XLP", "XLV", "XLRE"}
    if regime_label == "bear" or "panic" in regime4:
        if sector_etf not in defensive_etfs:
            reasons.append(f"HARD: bear regime ({regime_label}/{regime4}) + non-defensive sector ({sector_etf or 'unknown'})")
            return _position_verdict_result(score, "AVOID", "bear_regime", reasons, breakdown)
        reasons.append(f"bear regime override: defensive sector {sector_etf} allowed")

    # 3. Entry quality — block MISSED, flag EXTENDED
    eq = (r.get("entry_quality") or "").upper()
    if eq == "MISSED":
        reasons.append("HARD: entry quality MISSED — wait for pullback")
        return _position_verdict_result(score, "AVOID", "entry_missed", reasons, breakdown)

    # ── SOFT GATES — failure → cap at WATCH ────────────────────────────────

    # 4. R:R minimum 1.8:1 (looser than swing's 3.0 — held longer, more time to mature)
    rr_min = pos_cfg.get("rr_min", 1.8)
    rr = (r.get("trade_plan") or {}).get("rr_ratio") or r.get("rr_ratio") or 0
    try:
        rr = float(rr)
    except (TypeError, ValueError):
        rr = 0
    if rr > 0 and rr < rr_min:
        reasons.append(f"SOFT: R:R {rr:.1f}:1 below {rr_min}:1 minimum")
        soft_fail = True

    # 5. EXTENDED entry quality — allow BUY only if R:R compensates (≥ 2.5).
    # Otherwise, soft-cap to WATCH. Per feedback item 8 (P1): EXTENDED requires
    # higher R:R to justify the late entry location.
    extended_rr_min = pos_cfg.get("extended_rr_min", 2.5)
    if eq == "EXTENDED":
        if rr < extended_rr_min:
            reasons.append(f"SOFT: entry EXTENDED + R:R {rr:.1f} < {extended_rr_min} required")
            soft_fail = True
        else:
            reasons.append(f"EXTENDED entry allowed: R:R {rr:.1f} ≥ {extended_rr_min}")

    # 6. Weekly RSI ≥ 50 momentum gate
    if weekly_df is not None:
        try:
            wc = weekly_df["Close"].squeeze() if "Close" in weekly_df else None
            if wc is not None and len(wc) >= 14:
                # Wilder RSI on weekly bars
                delta = wc.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
                if loss > 0:
                    rs_w = gain / loss
                    rsi_w = 100 - (100 / (1 + rs_w))
                else:
                    rsi_w = 100
                breakdown["weekly_rsi"] = round(float(rsi_w), 1)
                if rsi_w < 50:
                    reasons.append(f"SOFT: weekly RSI {rsi_w:.0f} below 50")
                    soft_fail = True
        except Exception:
            pass

    # 7. Sector strength — require sector outperforming for BUY (already in scoring,
    #    but enforce here as gate). sector_etf_data is keyed by ETF symbol.
    sed = r.get("sector_etf_data") or {}
    sector_entry = sed.get(sector_etf) if sector_etf else None
    if sector_entry and not sector_entry.get("outperforming"):
        reasons.append(f"SOFT: sector {sector_etf} not outperforming SPY")
        soft_fail = True

    # 8. Distribution-day rule — ≥ 5 distribution days = no new BUY (downgrade to WATCH)
    dist_days = int(regime.get("distribution_days", 0))
    dist_threshold = pos_cfg.get("distribution_days_max", 5)
    if dist_days >= dist_threshold:
        reasons.append(f"SOFT: {dist_days} distribution days ≥ {dist_threshold} threshold")
        soft_fail = True

    # 9. Stop placement — require defined invalidation level (trade_plan.stop)
    stop = (r.get("trade_plan") or {}).get("stop")
    if stop is None or stop == 0:
        reasons.append("SOFT: no defined stop / invalidation level")
        soft_fail = True

    # ── FINAL 4-STATE VERDICT ──────────────────────────────────────────────
    if score < 60:
        verdict = "AVOID"
        status = "below_threshold"
    elif is_held and 60 <= score < 70 and not soft_fail:
        # Held position with intact trend — pyramid signal (separate stream)
        verdict = "ADD"
        status = "pyramid_signal"
    elif score >= 70 and eq in ("FRESH", "PULLBACK", "VALID") and not soft_fail:
        verdict = "BUY"
        status = "all_gates_pass"
    elif score >= 70 and eq == "EXTENDED" and rr >= pos_cfg.get("extended_rr_min", 2.5) and not soft_fail:
        verdict = "BUY"
        status = "extended_with_rr"
    elif score >= 60:
        verdict = "WATCH"
        status = "soft_gate_capped" if soft_fail else "score_60_69"
    else:
        verdict = "AVOID"
        status = "fallthrough"

    return _position_verdict_result(score, verdict, status, reasons, breakdown)


def _position_verdict_result(score, verdict, status, reasons, breakdown) -> dict:
    return {
        "score": score, "verdict": verdict, "gate_status": status,
        "gate_reasons": reasons, "breakdown": breakdown,
    }


def score_long_term(df: "pd.DataFrame", info: dict | None,
                    schwab_fund: dict | None, finviz: dict | None,
                    sector_etf_data: dict | None) -> dict:
    """Score a ticker for a 6-12+ month hold. Fundamentals-heavy.

    Quality screens (soft-failing when data is missing — we don't penalize
    Schwab's coverage gaps, only tickers that explicitly fail a threshold):
      - market cap >= $2B (reject micro-caps; unknown mcap is allowed)
      - gross margin >= 20% (reject low-quality commodity names; missing is OK)
      - debt/equity <= 250 (reject over-leveraged; missing is OK)
      - not explicitly unprofitable (net_margin strictly < -5% fails)

    Returns {score 0-100, verdict BUY/WATCH/AVOID, breakdown dict, gate_pass bool}.
    """
    info = info or {}
    sf   = schwab_fund or {}
    fv   = finviz or {}
    breakdown: dict = {}

    # ── Quality gates (hard filters, data-tolerant) ──
    # Fall back to Finviz bulk when Schwab fundamentals are missing.
    mcap = (info.get("market_cap") or info.get("marketCap")
            or (sf.get("_market_cap")) or 0)
    gm   = sf.get("gross_margin")
    if gm is None:
        gm = fv.get("gross_margin_pct")  # Finviz bulk provides this
    if gm is None:
        gm = info.get("gross_margin")
        if gm is not None and abs(gm) < 1:
            gm = gm * 100   # yfinance returns 0.47 = 47%
    de = sf.get("debt_equity")
    if de is None:
        de = fv.get("debt_to_equity")
    net = sf.get("net_margin")
    if net is None:
        net = info.get("profit_margin")
        if net is not None and abs(net) < 1:
            net = net * 100

    # ── Three-state missing-data model (P1.4 feedback 2026-04-30) ──────────
    # Replace boolean PASS/FAIL with PASS | FAIL | INSUFFICIENT_DATA.
    #   PASS              → field present + meets threshold → full credit
    #   FAIL              → field present + fails threshold → hard reject (AVOID)
    #   INSUFFICIENT_DATA → field missing/None → caps verdict at WATCH (never BUY)
    # Critical fundamentals (mcap, gross margin, D/E, net margin) feed this.
    def _gate_state(value, threshold_test, present_fn=None) -> str:
        """Return PASS / FAIL / INSUFFICIENT for a gate."""
        if value is None or (present_fn and not present_fn(value)):
            return "INSUFFICIENT"
        return "PASS" if threshold_test(value) else "FAIL"

    gates = {
        "market_cap":   _gate_state(mcap if (mcap or 0) > 0 else None,
                                     lambda v: v >= 2_000_000_000),
        "gross_margin": _gate_state(gm, lambda v: v >= 20),
        "debt_equity":  _gate_state(de, lambda v: v <= 250),
        "net_margin":   _gate_state(net, lambda v: v >= -5),
    }
    # Hard reject if ANY gate explicitly FAILed
    fail_keys = [k for k, v in gates.items() if v == "FAIL"]
    if fail_keys:
        return {"score": 0, "verdict": "AVOID", "gate_pass": False,
                "gate_states": gates, "missing_critical": [],
                "breakdown": {"gate_fails": fail_keys,
                              "mcap": mcap, "gross_margin": gm,
                              "debt_equity": de, "net_margin": net}}
    # Track INSUFFICIENT fields — verdict will be capped at WATCH below
    missing_critical = [k for k, v in gates.items() if v == "INSUFFICIENT"]

    total = 0
    close = df["Close"].squeeze() if df is not None and "Close" in df else None

    # ── 1. Revenue growth TTM (15 pts) ──
    rev = sf.get("rev_change_ttm")
    if   rev is None:         pts = 0
    elif rev >= 20:           pts = 15
    elif rev >= 10:           pts = 12
    elif rev >= 5:            pts = 8
    elif rev >= 0:            pts = 4
    else:                     pts = 0
    total += pts
    breakdown["rev_growth_ttm"] = {"pts": pts, "max": 15, "value": rev}

    # ── 2. EPS growth (15 pts) — blend TTM + 1-year change ──
    eps_ttm  = sf.get("eps_change_pct_ttm")
    eps_year = sf.get("eps_change_year")
    eps_blend = None
    if eps_ttm is not None and eps_year is not None:
        eps_blend = (eps_ttm + eps_year) / 2
    elif eps_ttm is not None:
        eps_blend = eps_ttm
    elif eps_year is not None:
        eps_blend = eps_year
    if   eps_blend is None: pts = 0
    elif eps_blend >= 20:   pts = 15
    elif eps_blend >= 10:   pts = 11
    elif eps_blend >= 0:    pts = 5
    else:                   pts = 0
    total += pts
    breakdown["eps_growth"] = {"pts": pts, "max": 15, "blend": eps_blend, "ttm": eps_ttm, "year": eps_year}

    # ── 3. Margin profile (15 pts) — gross + op + net ──
    op   = sf.get("op_margin")
    net  = sf.get("net_margin")
    pts = 0
    if gm  is not None and gm  >= 50: pts += 6
    elif gm is not None and gm >= 35: pts += 4
    elif gm is not None and gm >= 25: pts += 2
    if op  is not None and op  >= 20: pts += 5
    elif op is not None and op >= 10: pts += 3
    if net is not None and net >= 15: pts += 4
    elif net is not None and net >= 8: pts += 2
    total += pts
    breakdown["margin_profile"] = {"pts": pts, "max": 15, "gross": gm, "op": op, "net": net}

    # ── 4. ROE / ROA / ROI (10 pts) ──
    roe = sf.get("roe"); roa = sf.get("roa"); roi = sf.get("roi")
    pts = 0
    if roe is not None and roe >= 20:   pts += 4
    elif roe is not None and roe >= 10: pts += 2
    if roa is not None and roa >= 10:   pts += 3
    elif roa is not None and roa >= 5:  pts += 1
    if roi is not None and roi >= 15:   pts += 3
    elif roi is not None and roi >= 8:  pts += 1
    total += pts
    breakdown["returns"] = {"pts": pts, "max": 10, "roe": roe, "roa": roa, "roi": roi}

    # ── 4b. Valuation framework (15 pts) — P1.5 feedback 2026-04-30 ──
    # FCF yield · EV/Sales sanity · PEG (or Rule-of-40) · earnings yield vs 10y
    val_pts = 0
    val_breakdown: dict = {}
    # FCF yield (TTM FCF / EV) — high yield = cheap on cash flow
    fcf = sf.get("free_cash_flow") or sf.get("fcf_ttm")
    ev = sf.get("enterprise_value") or sf.get("ev")
    if fcf is not None and ev is not None and ev > 0:
        fcf_yield = fcf / ev * 100
        val_breakdown["fcf_yield_pct"] = round(fcf_yield, 2)
        if fcf_yield >= 5:    val_pts += 5
        elif fcf_yield >= 3:  val_pts += 3
        elif fcf_yield >= 1:  val_pts += 1
    # EV/Sales — flag if extreme without revenue growth justification
    ev_sales = sf.get("ev_sales") or sf.get("ev_to_revenue")
    if ev_sales is not None:
        val_breakdown["ev_sales"] = ev_sales
        if ev_sales <= 4:    val_pts += 4
        elif ev_sales <= 8:  val_pts += 2
        elif ev_sales <= 15: val_pts += 1
        # else: pricey, no points (and below we may apply a soft cap)
    # PEG ratio — cheap on growth-adjusted basis
    peg = sf.get("peg_ratio") or sf.get("peg")
    if peg is not None and peg > 0:
        val_breakdown["peg"] = peg
        if peg <= 1.0:    val_pts += 3
        elif peg <= 1.5:  val_pts += 2
        elif peg <= 2.0:  val_pts += 1
    # Earnings yield (1/PE) — vs implied 4% 10y treasury
    pe = sf.get("pe_ratio") or sf.get("trailing_pe")
    if pe is not None and pe > 0:
        ey = 1 / pe * 100
        val_breakdown["earnings_yield_pct"] = round(ey, 2)
        if ey >= 7:    val_pts += 3
        elif ey >= 4:  val_pts += 2
        elif ey >= 2:  val_pts += 1
    val_pts = min(15, val_pts)
    total += val_pts
    breakdown["valuation"] = {"pts": val_pts, "max": 15, **val_breakdown}

    # ── 5. Balance sheet health (10 pts) ──
    cr   = sf.get("current_ratio")
    ic   = sf.get("interest_coverage")
    pts = 0
    if cr is not None and cr >= 1.5:   pts += 4
    elif cr is not None and cr >= 1.0: pts += 2
    if de is not None and de <= 50:    pts += 3   # low debt/equity (pct)
    elif de is not None and de <= 100: pts += 1
    if ic is not None and ic >= 8:     pts += 3
    elif ic is not None and ic >= 3:   pts += 1
    total += pts
    breakdown["balance_sheet"] = {"pts": pts, "max": 10, "current_ratio": cr, "debt_equity": de, "interest_coverage": ic}

    # ── 6. 200-EMA uptrend + slope (15 pts) ──
    try:
        if close is not None and len(close) >= 200:
            price  = float(close.iloc[-1])
            ema200 = close.ewm(span=200, adjust=False).mean()
            e200_now = float(ema200.iloc[-1])
            e200_60d = float(ema200.iloc[-60]) if len(ema200) >= 60 else e200_now
            slope_60d = (e200_now - e200_60d) / e200_60d * 100
            above = price > e200_now
            if above and slope_60d >= 5:     pts = 15
            elif above and slope_60d >= 2:   pts = 11
            elif above and slope_60d >= 0:   pts = 7
            elif above:                      pts = 4
            else:                            pts = 0
            total += pts
            breakdown["ema200_trend"] = {"pts": pts, "max": 15,
                                          "above": above, "slope_60d_pct": round(slope_60d, 2)}
        else:
            breakdown["ema200_trend"] = {"pts": 0, "max": 15, "reason": "insufficient_history"}
    except Exception:
        breakdown["ema200_trend"] = {"pts": 0, "max": 15}

    # ── 7. Dividend signal (5 pts) — yield 1-5% with sustainable payout ──
    dy = sf.get("dividend_yield")
    if   dy is None or dy <= 0: pts = 0
    elif 1 <= dy <= 5:          pts = 5
    elif 0 < dy < 1:            pts = 2
    elif 5 < dy <= 8:           pts = 3   # high yield — may be distressed
    else:                        pts = 0   # >8% yield often signals trouble
    total += pts
    breakdown["dividend"] = {"pts": pts, "max": 5, "yield_pct": dy}

    # ── 8. Not over-extended vs 200 EMA (5 pts) ──
    try:
        if close is not None and len(close) >= 200:
            price  = float(close.iloc[-1])
            e200   = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            ext = (price - e200) / e200 * 100
            if ext <= 20:      pts = 5
            elif ext <= 35:    pts = 3
            elif ext <= 50:    pts = 1
            else:              pts = 0
            total += pts
            breakdown["over_extended"] = {"pts": pts, "max": 5, "ext_pct": round(ext, 1)}
    except Exception:
        breakdown["over_extended"] = {"pts": 0, "max": 5}

    # ── 9. Sector secular leader bonus (10 pts) ──
    try:
        sector_etf = (info.get("sector_etf") or "").upper()
        sec = (sector_etf_data or {}).get(sector_etf, {})
        # Secular-leader sectors: Tech (XLK), Comm (XLC), Health (XLV), Cons. Discretionary (XLY)
        leader_sectors = {"XLK", "XLC", "XLV", "XLY", "XLI"}
        in_leader = sector_etf in leader_sectors
        perf = sec.get("perf_3mo") or sec.get("perf_63d") or 0
        if in_leader and perf >= 5:   pts = 10
        elif in_leader:               pts = 6
        elif perf >= 5:               pts = 4
        else:                          pts = 0
        total += pts
        breakdown["sector_leader"] = {"pts": pts, "max": 10, "sector": sector_etf, "in_leader": in_leader, "perf": perf}
    except Exception:
        breakdown["sector_leader"] = {"pts": 0, "max": 10}

    score = max(0, min(100, total))
    raw_verdict = "BUY" if score >= 55 else ("WATCH" if score >= 40 else "AVOID")
    # Three-state cap — if any critical fundamentals are INSUFFICIENT (missing),
    # cap verdict at WATCH (never BUY). Per P1.4 feedback.
    if missing_critical and raw_verdict == "BUY":
        verdict = "WATCH"
        cap_reason = f"INSUFFICIENT data on critical fields: {', '.join(missing_critical)}"
    else:
        verdict = raw_verdict
        cap_reason = None
    return {"score": score, "verdict": verdict, "gate_pass": True,
            "gate_states": gates, "missing_critical": missing_critical,
            "cap_reason": cap_reason, "breakdown": breakdown}


# ── Bear setup scoring (short trades) ───────────────────────────────────────

def score_bear_setup(df: pd.DataFrame, indicators: dict) -> dict:
    """
    Score the quality of a short-side setup. Only called when direction=="short".
    Returns {score: int, max: 15, details: dict}

    Components (15 pts max):
      EMA breakdown          0-3  (price < EMA21 < EMA50 = full downtrend)
      Momentum / overbought  0-4  (RSI > 70 + bearish MACD cross)
      Distribution volume    0-3  (CMF negative + OBV falling)
      SAR / reversal signal  0-3  (SAR flipped bearish, near 52w high = failed breakout)
      ADX confirmation       0-2  (ADX > 25 with -DI > +DI)
    """
    close  = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high   = df["High"].squeeze()  if isinstance(df["High"],  pd.DataFrame) else df["High"]
    low    = df["Low"].squeeze()   if isinstance(df["Low"],   pd.DataFrame) else df["Low"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    score = 0
    details = {}

    price = float(close.iloc[-1])
    e21 = indicators.get("ema21", price)
    e50 = indicators.get("ema50", price)

    # 1. EMA breakdown (0-3)
    if price < e21 < e50:
        ema_pts = 3
    elif price < e21:
        ema_pts = 2
    elif price < e50:
        ema_pts = 1
    else:
        ema_pts = 0
    score += ema_pts
    details["ema_breakdown"] = f"Price {'<' if price < e21 else '>'} EMA21, {'<' if e21 < e50 else '>'} EMA50 ({ema_pts}/3)"

    # 2. Momentum / overbought (0-4)
    rsi_val  = indicators.get("rsi", 50)
    macd_bull = indicators.get("macd_bullish", True)  # False = bearish
    srsi_k    = indicators.get("stoch_rsi_k", 50)
    if rsi_val > 70 and not macd_bull:
        mom_pts = 4  # Overbought + confirmed MACD bear cross
    elif rsi_val > 70:
        mom_pts = 3  # Overbought alone
    elif rsi_val > 60 and not macd_bull:
        mom_pts = 2  # Elevated + MACD turning
    elif not macd_bull and srsi_k > 70:
        mom_pts = 2  # StochRSI overbought + MACD bearish
    elif not macd_bull:
        mom_pts = 1
    else:
        mom_pts = 0
    score += mom_pts
    details["momentum_bear"] = (f"RSI {rsi_val:.0f}, MACD {'↓bear' if not macd_bull else '↑bull'}, "
                                f"StochRSI K={srsi_k:.0f} ({mom_pts}/4)")

    # 3. Distribution volume (0-3)
    cmf_val  = indicators.get("cmf", 0)
    obv_rise = indicators.get("obv_rising", True)
    rvol     = indicators.get("rvol", 1.0)
    if cmf_val < -0.10 and not obv_rise:
        vol_pts = 3
    elif cmf_val < -0.05 and not obv_rise:
        vol_pts = 2
    elif cmf_val < -0.05 or (not obv_rise and rvol > 1.2):
        vol_pts = 1
    else:
        vol_pts = 0
    score += vol_pts
    details["distribution"] = (f"CMF {cmf_val:+.2f}, OBV {'↓' if not obv_rise else '↑'}, "
                               f"RVOL {rvol:.1f}x ({vol_pts}/3)")

    # 4. SAR / reversal signal (0-3)
    sar_bullish = indicators.get("sar_bullish", True)
    sar_flipped = indicators.get("sar_flipped", False)
    near_52w_high = indicators.get("near_52w_high", False)
    at_breakout   = indicators.get("at_52w_breakout", False)
    if sar_flipped and not sar_bullish and near_52w_high:
        sar_pts = 3  # SAR flipped bearish at top of range — failed breakout
    elif sar_flipped and not sar_bullish:
        sar_pts = 2
    elif not sar_bullish and near_52w_high:
        sar_pts = 2  # Near 52w high with bearish SAR — reversal risk
    elif not sar_bullish:
        sar_pts = 1
    else:
        sar_pts = 0
    score += sar_pts
    sar_label = "SAR bearish" + (" (FLIPPED)" if sar_flipped else "") + (" near 52w high" if near_52w_high else "")
    details["sar_reversal"] = f"{sar_label} ({sar_pts}/3)"

    # 5. ADX confirmation (0-2): strong trend with -DI dominant
    adx_val    = indicators.get("adx", 0)
    plus_di    = indicators.get("adx_plus_di", 50)
    minus_di   = indicators.get("adx_minus_di", 50)
    if adx_val > 25 and minus_di > plus_di:
        adx_pts = 2  # Strong trending move with bears in control
    elif adx_val > 20:
        adx_pts = 1
    else:
        adx_pts = 0
    score += adx_pts
    details["adx_confirm"] = (f"ADX {adx_val:.0f}, +DI {plus_di:.0f} / -DI {minus_di:.0f} ({adx_pts}/2)")

    return {"score": score, "max": 15, "details": details}


# ── Decision ─────────────────────────────────────────────────────────────────

def _compute_state(tech: dict, plan: dict, setup_type: str, score: float, direction: str, config: dict, current_price: float = 0) -> dict | None:
    """
    State-based classification patch (2026-04-15).
    Non-fatal: any failure returns None so the legacy verdict still flows.
    """
    try:
        from decision_state import extract_indicator_payload, patched_trade_decision, render_dashboard_message, LABEL_MAP
        indicators = (tech or {}).get("indicators", {}) if isinstance(tech, dict) else {}
        # Use current_price (from df Close) as primary — plan.entry and indicators.price are often None/0
        price = current_price or (plan or {}).get("entry") or indicators.get("price") or indicators.get("close") or 0
        payload = extract_indicator_payload(indicators, price, setup_type or "")
        decisions_cfg = config.get("decisions", {}) if isinstance(config, dict) else {}
        buy_min   = decisions_cfg.get("buy_min_score", 65)
        watch_min = decisions_cfg.get("watch_min_score", 50)
        rr_min    = decisions_cfg.get("buy_min_rr", 2.0)
        rr        = (plan or {}).get("rr", 0) or 0
        state = patched_trade_decision(payload, score=score, buy_min=buy_min, watch_min=watch_min, rr=rr, rr_min=rr_min)

        # Check for PULLBACK_WAIT — quality name blocked only by extension
        _rs = (tech or {}).get("indicators", {}).get("rs_rank", 0) or 0
        _rs_min = decisions_cfg.get("rs_min", config.get("regime_thresholds", {}).get("bull", {}).get("rs_min", 60))
        pw = classify_pullback_wait(state, score, _rs, buy_min, _rs_min)
        if pw:
            state = pw
            # Compute distance to entry zone
            _entry_high = state.get("zones", {}).get("primary_zone", [None, None])
            _eh = _entry_high[1] if isinstance(_entry_high, (list, tuple)) and len(_entry_high) > 1 else None
            state["distance_to_entry_pct"] = compute_distance_to_entry(current_price, _eh)
            state["proximity"] = proximity_bucket(state["distance_to_entry_pct"])

        state["dashboard_message"] = render_dashboard_message(state)
        state["direction"]         = direction
        return state
    except Exception:
        return None


def compute_mc_p_profit(score: float, rr_ratio: float,
                        entry_quality: str = "VALID",
                        setup_family: str = "",
                        atr_pct: float = 2.0,
                        rs_rank: int = 50,
                        weekly_bull: bool = False) -> float:
    """Closed-form heuristic for P(profit) on a 5-day swing.

    Calibrated to historical 50% baseline win-rate (Apr 2026 backtest median).
    Used as a soft gate (BUY → WATCH if < threshold). Returns float in [0, 1].

    Adjustments are additive on a 0.50 baseline:
      score boost   :  (score - 70) × 0.008    [+0.008/pt above 70]
      R:R balance   :  +0.02 if 2.5 ≤ R:R ≤ 4 ; −0.05 if R:R < 2 ; −0.02 if > 5
      entry quality :  FRESH +0.05, PULLBACK +0.03, EXTENDED −0.10, MISSED −0.15
      setup family  :  impulse_catalyst +0.04, breakout_expansion +0.02,
                       trend_continuation +0.03, special_situation −0.02
      RS rank       :  (rs - 70) × 0.002       [extra weight for leaders]
      weekly bias   :  +0.03 when weekly bull confirms daily
      volatility    :  −0.05 if ATR > 5% ; −0.10 if > 8%

    Output is bounded [0.05, 0.95] to avoid degenerate gating.
    """
    p = 0.50
    p += (float(score) - 70.0) * 0.008
    if 2.5 <= rr_ratio <= 4.0:
        p += 0.02
    elif rr_ratio < 2.0:
        p -= 0.05
    elif rr_ratio > 5.0:
        p -= 0.02
    eq_adj = {"FRESH": 0.05, "PULLBACK": 0.03, "VALID": 0.0,
              "EXTENDED": -0.10, "MISSED": -0.15}
    p += eq_adj.get((entry_quality or "VALID").upper(), 0.0)
    sf_norm = (setup_family or "").lower().replace(" ", "_")
    sf_adj = 0.0
    if "impulse" in sf_norm or "catalyst" in sf_norm or "pead" in sf_norm:
        sf_adj = 0.04
    elif "breakout" in sf_norm or "vcp" in sf_norm or "expansion" in sf_norm:
        sf_adj = 0.02
    elif "continuation" in sf_norm or "pullback" in sf_norm or "trend" in sf_norm:
        sf_adj = 0.03
    elif "special" in sf_norm or "squeeze" in sf_norm:
        sf_adj = -0.02
    p += sf_adj
    p += (float(rs_rank) - 70.0) * 0.002
    if weekly_bull:
        p += 0.03
    if atr_pct > 8.0:
        p -= 0.10
    elif atr_pct > 5.0:
        p -= 0.05
    return max(0.05, min(0.95, p))


def make_decision(total_score: float, rr_ratio: float, config: dict,
                  weak_regime: bool = False,
                  direction: str = "long",
                  bear_score: int = 0,
                  rs_rank: int = 50,
                  vix: float = 20.0,
                  sector_outperforming: bool = False,
                  sector_etf: str = "",
                  has_catalyst: bool = False,
                  rsi: float = 50.0,
                  weekly_bull: bool = False,
                  adx: float = 20.0,
                  regime_name: str = "neutral",
                  breadth: dict | None = None,
                  entry_quality: str = "VALID",
                  regime4: str = "",
                  setup_type: str = "",
                  # Short-specific correctness filters (Vinod expert review):
                  short_float: float = 0.0,
                  # AI-9: days-to-cover for squeeze trap detection
                  days_to_cover: float = 0.0,
                  days_to_earnings: int | None = None,
                  sector_underperforming: bool = False,
                  stock_vs_spy_20d: float = 0.0,
                  # Fix #30: today's gap (most recent open vs prior close)
                  todays_gap_pct: float = 0.0,
                  # Bug #3: TTM squeeze state — shorts must not fire into squeeze setups
                  squeeze_on: bool = False,
                  # AI-8: RVOL used to gate breakout BUYs
                  rvol: float = 1.0,
                  # AI-43: market-cycle-aware score bar adjustment
                  market_cycle: str = "",
                  # AI-44: seasonality adjustment dict from seasonality.seasonality_adjustment()
                  seasonal_adj: dict | None = None,
                  # Hysteresis (3.4): ticker used to look up recent verdicts
                  ticker: str = "",
                  catalyst_tier: int = 3,
                  # BHE Gap 1: Monte Carlo P(profit) — soft gate when below threshold
                  mc_p_profit: float | None = None) -> dict:
    """
    Clean sequential decision ladder (Fix #14):

    Step 1 — Hard gates: SPY crash check, VIX capitulation, breadth collapse -> REJECT
    Step 2 — Regime check: set score/RR/RS thresholds from regime4 or legacy 3-regime config
    Step 3 — Score check: total_score vs regime threshold -> PASS or FAIL (AVOID)
    Step 4 — Entry quality check: EXTENDED/MISSED demoted -> BUY or WATCH
    Step 5 — R:R + RS + weekly + catalyst checks -> final BUY / WATCH / AVOID

    Post-decision overrides in analyze_ticker() (intentional, not redundant):
      - Gate failure override: if pre_trade_gate failed, force AVOID
      - MTF conflict override: if daily bullish but weekly bearish, cap BUY -> WATCH

    LONG path (bull):  BUY score >= 65 AND R:R >= 3:1 AND RS >= 55 (regime-adaptive)
    LONG path (neutral): BUY score >= 72 AND R:R >= 3:1 AND RS >= 60
    LONG path (bear):  Tier 1 — Market Leader: score >= 80, RS >= 70, R:R >= 4:1, weekly bull
                       Tier 2 — Defensive:     score >= 75, RS >= 60, sector leading, R:R >= 3.5:1
                       Hard block: VIX >= 30 (capitulation zone)
    SHORT path:        bear_score threshold from regime_thresholds AND bear regime AND R:R >= 3:1

    AI-43 — market-cycle adjustment (additive on buy_min after regime resolution):
      - early_bull / mid_cycle  : buy_min -= 2  (clean uptrends, slightly more aggressive)
      - late_bull               : no change
      - topping / capitulation  : buy_min += 3  (raise bar, quality-over-quantity)
      Floored at 60 so we never drop below a sane minimum.
    """
    decisions  = config.get("decisions", {})
    gates_cfg  = config.get("gates", {})
    buy_min    = decisions.get("buy_min_score", 75)
    buy_rr     = decisions.get("buy_min_rr", 3.0)
    watch_min  = decisions.get("watch_min_score", 55)

    # Ranking flaw #10: neutral direction means no clear trend — demote to WATCH
    # instead of silently treating as LONG (the legacy default).
    if direction == "neutral":
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"No clear trend (ADX {adx:.0f}) — no directional edge"}

    # Regime-adaptive thresholds — regime4 takes priority over legacy 3-regime
    _rt4 = config.get("regime4_thresholds", {}).get(regime4, {}) if regime4 else {}
    _rt  = _rt4 if _rt4 else config.get("regime_thresholds", {}).get(regime_name, {})
    if _rt:
        # QUANT-3 (2026-05-10): score_band_buy shorthand. When present in the
        # regime config as `score_band_buy: [lo, hi]`, it OVERRIDES both
        # buy_min_score (lo) and buy_max_score (hi). Allows e.g. "buy only
        # 70-89 in choppy regime" — kills both the noise band <70 AND the
        # mania band >89 in one config field.
        # Backward-compatible: separate buy_min_score / buy_max_score still work.
        _band = _rt.get("score_band_buy")
        if isinstance(_band, list) and len(_band) == 2:
            try:
                _band_lo, _band_hi = float(_band[0]), float(_band[1])
                # Inject as buy_min_score / buy_max_score so downstream gate
                # logic at line ~6963/6968 picks them up unchanged.
                _rt = dict(_rt)
                _rt.setdefault("buy_min_score", _band_lo)
                _rt.setdefault("buy_max_score", _band_hi)
            except (TypeError, ValueError):
                pass
        buy_min   = _rt.get("buy_min_score",   buy_min)
        # regime4 thresholds don't have watch_min_score; derive as buy_min - 8
        watch_min = _rt.get("watch_min_score", buy_min - 8 if _rt4 else watch_min)
        buy_rr    = _rt.get("rr_min",          buy_rr)

    # Checklist 7.1: cycle + seasonality adjustments now applied via pure
    # effective_buy_min() function. Breadth adj is folded in below the RR gate
    # (we first call effective_buy_min without breadth, then re-call with it so
    # the RR-family-gate code can run against the pre-breadth buy_min — matches
    # pre-refactor ordering where breadth mutated buy_min later in the flow).
    _pre_breadth_final, _ebm_pre = effective_buy_min(
        base_buy_min=buy_min,
        market_cycle=market_cycle,
        seasonal_adj=seasonal_adj,
        breadth=None,           # breadth applied later (preserves prior sequence)
        direction=direction,
    )
    buy_min = _pre_breadth_final
    _season_note = _ebm_pre.get("season_note", "")

    # Fix #7: Setup-specific minimum R:R — look up by setup family, fall back to default
    # Risk-Off regime override (4.0) still takes priority
    _min_rr_cfg = config.get("technicals", {}).get("min_rr", {})
    if isinstance(_min_rr_cfg, dict) and setup_type:
        _setup_lower = setup_type.lower().replace(" ", "_")
        # Map setup type to family key
        _family_rr_key = None
        for _fk in ("impulse_catalyst", "breakout_expansion", "trend_continuation", "special_situation"):
            if _fk.replace("_", "") in _setup_lower.replace("_", ""):
                _family_rr_key = _fk
                break
        if not _family_rr_key:
            if any(kw in _setup_lower for kw in ["catalyst", "pead", "impulse", "earnings"]):
                _family_rr_key = "impulse_catalyst"
            elif any(kw in _setup_lower for kw in ["breakout", "vcp", "expansion"]):
                _family_rr_key = "breakout_expansion"
            elif any(kw in _setup_lower for kw in ["continuation", "pullback", "trend"]):
                _family_rr_key = "trend_continuation"
            else:
                _family_rr_key = "default"
        _setup_rr = _min_rr_cfg.get(_family_rr_key, _min_rr_cfg.get("default", 3.0))
        # Setup R:R can raise the bar but never lower it below regime/profile minimum
        buy_rr = max(buy_rr, _setup_rr)

    # CRITICAL GATE: RS threshold from regime4 config (falls back to 75)
    _rs_min = int(_rt.get("rs_min", 75)) if _rt else 75
    if direction == "long" and rs_rank < _rs_min:
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"RS {rs_rank} < {_rs_min} — lacks relative strength for {regime4 or regime_name}"}

    # ── Setup exclusion filter (Phase 4 tuning) ──────────────────────────────
    _exclude_setups = _rt.get("exclude_setup_types", []) if _rt else []
    if _exclude_setups and setup_type in _exclude_setups and direction == "long":
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"{setup_type} excluded from BUY in {regime4 or regime_name} regime (Phase 4 backtest filter)"}

    # ── Pullback override: REMOVED ──
    # Was lowering BUY threshold to 55 for pullback setups, causing BUY at 56
    # to rank below WATCH at 70 — confusing and wrong optics.
    # The pullback bonus in score_technicals already boosts the score.
    # If a pullback only scores 56, it's not strong enough for BUY.

    # ── Breadth overlay (checklist 7.1: via effective_buy_min) ─────────
    # pct_above_50d 25-40%: raise threshold by 5 pts (weak breadth = higher bar)
    # pct_above_50d <25%: hard block is in pre_trade_gate; here add WATCH floor
    _ebm_final, _ebm_full = effective_buy_min(
        base_buy_min=buy_min,
        market_cycle=None,        # cycle+season already applied above
        seasonal_adj=None,
        breadth=breadth,
        direction=direction,
    )
    buy_min = _ebm_final
    watch_min += _ebm_full.get("watch_bump", 0)
    _breadth_note = _ebm_full.get("breadth_note", "")

    # ── Phase 2C / Fix #13: EXTENDED entries are always pure WATCH — no special treatment ──
    if direction == "long" and entry_quality == "EXTENDED":
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"Price extended — wait for value zone (>1.25 ATR above EMA21, score {total_score:.0f})"}
    if direction == "long" and entry_quality == "MISSED":
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"Price extended — wait for value zone (broke through resistance, wait for next base)"}

    # Profile-driven entry quality enforcement (e.g. trending_leaders: VALID → WATCH)
    # QUANT-6 (2026-05-10): per-regime entry_quality_rules. When the active
    # regime defines its own entry_quality_rules in regime4_thresholds.<regime>,
    # those OVERRIDE the global entry_quality_rules. Use case: choppy regime
    # may demand FRESH-only entries while trending regime accepts PULLBACK.
    # Falls back to global config.entry_quality_rules when regime-specific
    # rules are not declared.
    _eq_rules_regime = (_rt or {}).get("entry_quality_rules") or {}
    _eq_rules_global = config.get("entry_quality_rules", {})
    _eq_rules = _eq_rules_regime if _eq_rules_regime else _eq_rules_global
    if _eq_rules and direction == "long" and entry_quality:
        _eq_verdict = _eq_rules.get(entry_quality, "")
        if _eq_verdict == "WATCH" and entry_quality not in ("EXTENDED", "MISSED"):
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Entry quality {entry_quality} → WATCH per profile (score {total_score:.0f})"}
        if _eq_verdict == "AVOID":
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#ef4444",
                    "bear_type": "",
                    "reason": f"Entry quality {entry_quality} → AVOID per profile"}

    # ── 52wk Breakout quality filter — Fix #3: conditional, not absolute ──
    # Elite breakouts (RS>=90 + weekly bull + catalyst + entry quality OK) stay eligible for BUY.
    # Everything else demoted to WATCH — low-quality breakouts chase the top.
    #
    # AUDIT 2026-04-15 (checklist 7.2): potentially dead code after setup_gates
    # migration (Wave 1 + Wave 2B generic setup-gates loop at L5702+ now covers
    # rs_min / rvol / weekly_bull via config.setup_gates['52wk_breakout']).
    # Instrumented for 7 days; delete if hit count = 0 in cache/52wk_elite_hits.json.
    if direction == "long" and setup_type == "52wk Breakout":
        try:
            _52WK_ELITE_HITS["evaluated"] = int(_52WK_ELITE_HITS.get("evaluated", 0)) + 1
        except Exception:
            pass
        _elite_breakout = (
            rs_rank >= 90
            and weekly_bull
            and has_catalyst
            and entry_quality in ("VALID", "PULLBACK", "FRESH")
        )
        if _elite_breakout:
            try:
                _52WK_ELITE_HITS["elite_pass"] = int(_52WK_ELITE_HITS.get("elite_pass", 0)) + 1
            except Exception:
                pass
        if not _elite_breakout and rs_rank < 80:
            try:
                _52WK_ELITE_HITS["demoted_to_watch"] = int(_52WK_ELITE_HITS.get("demoted_to_watch", 0)) + 1
            except Exception:
                pass
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"52wk Breakout needs elite quality (RS>=90 + weekly bull + catalyst + clean entry) or RS>=80 — have RS {rs_rank}"}

    # ── Short path ────────────────────────────────────────────────
    if direction == "short":
        # HARD GATE: shorts disabled flag (set in config to go long-only)
        if gates_cfg.get("short_disabled", False):
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": "Shorts disabled (long-only mode active)"}

        # HARD GATE: minimum VIX for shorting (low VIX = too much upward bias, squeeze risk)
        short_min_vix = gates_cfg.get("short_min_vix", 25)
        if vix < short_min_vix:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: VIX {vix:.0f} < {short_min_vix:.0f} (low VIX = squeeze risk; wait for fear)"}

        # HARD GATE: require bear regime for shorts (no override — foot-gun removed)
        if not weak_regime:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": "Short blocked: requires bear/risk-off regime"}

        short_min_rsi = _rt.get("short_min_rsi",        gates_cfg.get("short_min_rsi", 70))
        # Fix #9: bear_score max is 15 (per score_bear_setup), so 16 was unreachable.
        # 12 = 80% of max, requires strong setup across at least 4 of 5 components.
        short_min_bs  = _rt.get("short_min_bear_score",  gates_cfg.get("short_min_bear_score", 12))
        # Never short oversold stocks — they bounce. Short from elevated RSI (distribution zone)
        if rsi < short_min_rsi:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: RSI {rsi:.0f} < {short_min_rsi:.0f} — already oversold (squeeze risk)"}

        # Vinod expert review — 4 correctness filters for shorts
        # 1. Inverse relative strength: only short weak stocks
        short_max_rs = gates_cfg.get("short_max_rs_rank", 30)
        if rs_rank > short_max_rs:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: RS {rs_rank} > {short_max_rs} — stock is not weak, shorting strength fails"}

        # 2. Earnings block — binary event risk on short side (beat-and-raise = squeeze)
        short_earnings_window = gates_cfg.get("short_earnings_block_days", 7)
        if days_to_earnings is not None and 0 <= days_to_earnings <= short_earnings_window:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: earnings in {days_to_earnings}d (beat-and-raise risk)"}

        # 3. Sector-relative: fighting a leading sector destroys short edge
        if not sector_underperforming:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": "Short blocked: sector not underperforming SPY — rotation tailwind fights short"}

        # 4. Short-float cap: high short-interest names are squeeze traps
        short_max_float = gates_cfg.get("short_max_short_float_pct", 15.0)
        if short_float and short_float > short_max_float:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: short float {short_float:.0f}% > {short_max_float:.0f}% (squeeze trap risk)"}

        # AI-9: Days-to-cover gate — DTC > 5 = squeeze risk (takes >5 days of normal vol to close all shorts)
        short_max_dtc = gates_cfg.get("short_max_dtc", 5.0)
        if days_to_cover and days_to_cover > short_max_dtc:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Short blocked: DTC {days_to_cover:.1f}d > {short_max_dtc:.1f}d (shorts concentrated → squeeze risk)"}

        # Bug #3: TTM Squeeze active — direction of expansion is unknown, often breaks UP
        # Never short into an active squeeze. Wait for resolution to the downside first.
        if squeeze_on:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": "Short blocked: TTM Squeeze active — expansion direction unknown, wait for downside break"}

        if bear_score >= short_min_bs and weak_regime and rr_ratio >= buy_rr:
            return {"verdict": "SHORT", "emoji": "arrow_down", "color": "#7c3aed",
                    "bear_type": "",
                    "reason": f"Bear setup {bear_score:.0f}/15, RSI {rsi:.0f}, VIX {vix:.0f}, R:R {rr_ratio:.1f}:1, RS {rs_rank}, sector weak — confirmed short"}
        elif bear_score >= 10:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Bear setup {bear_score:.0f}/15 — needs {short_min_bs}+ and VIX {vix:.0f}>={short_min_vix} for SHORT"}
        else:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "reason": f"Weak bear structure (bear_score {bear_score}/15, need {short_min_bs}+)"}

    # ── Bear regime long path — surgical filters ──────────────────
    if weak_regime:
        gates_cfg     = config.get("gates", {})
        bear_rs_min   = gates_cfg.get("bear_rs_min", 75)
        bear_rr_min   = gates_cfg.get("bear_rr_min", 4.0)
        bear_def_rs   = gates_cfg.get("bear_defensive_rs_min", 65)
        bear_def_rr   = gates_cfg.get("bear_defensive_rr_min", 3.5)
        bear_def_secs = gates_cfg.get("bear_defensive_sectors", ["XLU", "XLP", "XLV", "XLE"])
        vix_cap       = gates_cfg.get("bear_vix_no_longs", 40)

        # Hard block: capitulation zone
        if vix >= vix_cap:
            return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "vix_blocked",
                    "reason": f"VIX {vix:.0f} ≥ {vix_cap:.0f} — capitulation zone, no new longs"}

        # Tier 1 — Market Leader: score bar unchanged, RS gate + elevated R:R + weekly bull
        if (total_score >= buy_min and rs_rank >= bear_rs_min
                and rr_ratio >= bear_rr_min and weekly_bull):
            cat_note = " + catalyst" if has_catalyst else ""
            return {"verdict": "BUY", "emoji": "check", "color": "#059669",
                    "bear_type": "leader",
                    "reason": (f"Bear Market Leader — Score {total_score:.0f}, "
                               f"RS {rs_rank}, weekly ✓, R:R {rr_ratio:.1f}:1{cat_note} | half-size")}

        # Tier 2 — Defensive: leading sector + lower RS/RR bar
        in_def = sector_etf in bear_def_secs
        if (in_def and sector_outperforming
                and total_score >= 72
                and rs_rank >= bear_def_rs
                and rr_ratio >= bear_def_rr):
            return {"verdict": "BUY", "emoji": "check", "color": "#f59e0b",
                    "bear_type": "defensive",
                    "reason": (f"Defensive Bear Play — {sector_etf} leading, "
                               f"RS {rs_rank}, R:R {rr_ratio:.1f}:1 | quarter-size")}

        # Did not clear bear gates — explain why in WATCH reason
        if total_score >= watch_min:
            gaps = []
            if rs_rank < bear_rs_min:
                gaps.append(f"RS {rs_rank} < {bear_rs_min}")
            if rr_ratio < bear_rr_min:
                gaps.append(f"R:R {rr_ratio:.1f} < {bear_rr_min:.1f}")
            if not in_def:
                gaps.append("sector not leading")
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "gated",
                    "reason": f"Score {total_score:.0f}/100 — bear gate: {', '.join(gaps) or 'needs stronger setup'}"}
        return {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                "bear_type": "avoid",
                "reason": f"No edge at current price — score {total_score:.0f}/100, weak structure"}

    # ── Bull / neutral long path ───────────────────────────────────
    # Fix #30: gap >3% on a BUY candidate → demote to WATCH (FOMO protection)
    if direction == "long" and abs(todays_gap_pct) > 3.0 and total_score >= buy_min and rr_ratio >= buy_rr:
        return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"Gap risk: opened {todays_gap_pct:+.1f}% — wait for 30-min opening range before chasing"}

    # BHE Gap 1: Monte Carlo P(profit) gate — demote BUY → WATCH when below threshold.
    # Default threshold 0.55, configurable via config.gates.min_mc_p_profit.
    # Disabled by default (config.gates.require_mc_p_profit=true to enable).
    if (direction == "long" and mc_p_profit is not None
            and gates_cfg.get("require_mc_p_profit", False)
            and total_score >= buy_min and rr_ratio >= buy_rr):
        _mc_min = float(gates_cfg.get("min_mc_p_profit", 0.55))
        if mc_p_profit < _mc_min:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"MC P(profit) {mc_p_profit:.0%} < {_mc_min:.0%} — score qualifies but probability-of-profit too low"}

    # AI-8: Breakout setups (VCP / 52wk) require RVOL >= 1.0 — no-volume breakouts fail
    if direction == "long" and setup_type in ("VCP Breakout", "52wk Breakout") and rvol < 1.0:
        if total_score >= buy_min:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"{setup_type} needs RVOL >= 1.0 — have {rvol:.2f}x (breakout without volume = failed pattern)"}

    # AI-7: Elite-RS override — high-RS stocks with high-quality setup get lower buy bar.
    # Threshold configurable via scoring.elite_rs_override_rank (default 95; swing uses 85).
    _elite_setups = ("Trend Continuation", "VCP Breakout", "EMA21 Pullback", "EMA50 Pullback",
                     "Near-VCP Breakout", "Bounce off Support")
    _elite_rs_rank_min = int(config.get("scoring", {}).get("elite_rs_override_rank", 95))
    _effective_buy_min = buy_min
    if direction == "long" and rs_rank >= _elite_rs_rank_min and setup_type in _elite_setups:
        _effective_buy_min = max(55, buy_min - 5)

    if total_score >= _effective_buy_min and rr_ratio >= buy_rr:
        # Q1-step6 (2026-05-10): per-regime buy_max_score cap. Score band 90+
        # showed n=19, PF 0.32 in Saturday post-kill subset (anti-predictive).
        # Override-shipped pending 250d backtest verification — see
        # config._validations.q1_step6_buy_max_cap audit entry.
        buy_max = _rt.get("buy_max_score")
        if buy_max is not None and total_score > buy_max:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Score {total_score} > buy_max_score {buy_max} (Q1-step6 cap — 90+ band anti-predictive in post-kill subset, n=19 PF 0.32)"}
        long_min_rs    = _rt.get("rs_min",               gates_cfg.get("long_min_rs_rank", 65))
        require_w_bull = _rt.get("weekly_bull_required",  gates_cfg.get("long_require_weekly_bull", True))
        high_vix       = _rt.get("high_vix_threshold",    gates_cfg.get("high_vix_threshold", 22))
        extra          = _rt.get("high_vix_extra_score",  gates_cfg.get("high_vix_extra_score", 10))

        # ── Setup-gates config block (Wave 1 migration) ──
        # Map setup_type string to setup_gates config key. Fall back to "default".
        setup_gates = config.get("setup_gates", {}) or {}
        _setup_key_map = {
            "Pocket Pivot": "pocket_pivot",
            "VCP Breakout": "vcp_breakout",
            "EMA21 Pullback": "ema21_pullback",
            "EMA50 Pullback": "ema50_pullback",
            "Near-VCP Breakout": "near_vcp",
            "52wk Breakout": "52wk_breakout",
            "Trend Continuation": "trend_continuation",
            "Bounce off Support": "bounce",
        }
        _plan_setup_top = setup_type.split(" —")[0].strip() if setup_type else ""
        _setup_key = _setup_key_map.get(_plan_setup_top, "default")
        if "Breakdown" in _plan_setup_top:
            _setup_key = "breakdown"
        _sg = setup_gates.get(_setup_key, setup_gates.get("default", {})) or {}

        # NEW GATE: Skip overbought entries (RSI > cap = exhaustion imminent)
        # Elite leaders keep 80; everyone else 75 (but configurable per-setup)
        _rsi_cap = _sg.get("rsi_cap", 75)
        if setup_type in ("Trend Continuation", "VCP Breakout", "Pocket Pivot") and rs_rank >= 85:
            _rsi_cap = max(_rsi_cap, 80)
        if rsi > _rsi_cap:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Wait for pullback — score {total_score:.0f} qualifies but RSI {rsi:.0f} overbought, need <={_rsi_cap}"}

        # Setup quality gates (Continuation eliminated entirely)
        _plan_setup = setup_type.split(" —")[0].strip() if setup_type else ""

        # BOUNCE OFF SUPPORT: Prefer with RS >= 85 (backtest shows 70% WR at high RS)
        if "Bounce" in _plan_setup and rs_rank < 85:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Bounce setup needs RS >= 85 for confidence (have RS {rs_rank})"}

        # All other setups require higher scores (lower-WR fallback patterns)
        if "Breakdown" in _plan_setup and total_score < 72:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Breakdown setup: need score 72+ (have {total_score:.0f})"}

        # ── Backtest-driven setup tightenings (184-trade sim: 34% WR overall) ──
        # These 4 setups produced 100%+ of the drag. Tightening to preserve only
        # high-conviction instances based on per-setup WR attribution.

        # ── Per-setup gates from config.setup_gates (Wave 1 migration) ──
        # Apply rs_min, rvol_min, weekly_bull_required, score_bonus_required
        # from config instead of hardcoded thresholds. Preserves the same WATCH
        # reason strings but pulls numeric thresholds from config.
        if _setup_key in setup_gates or (_plan_setup and _plan_setup in _setup_key_map):
            _sg_rs_min   = _sg.get("rs_min")
            _sg_rvol_min = _sg.get("rvol_min")
            _sg_w_bull   = _sg.get("weekly_bull_required", False)
            _sg_bonus    = int(_sg.get("score_bonus_required", 0) or 0)

            # Setup-specific rs_min gate
            if _sg_rs_min is not None and rs_rank < _sg_rs_min:
                return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                        "bear_type": "",
                        "reason": f"{_plan_setup or setup_type} needs RS>={_sg_rs_min} (have {rs_rank})"}

            # Setup-specific rvol_min gate
            if _sg_rvol_min is not None and rvol < _sg_rvol_min:
                return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                        "bear_type": "",
                        "reason": f"{_plan_setup or setup_type} needs RVOL>={_sg_rvol_min:.1f} (have {rvol:.1f}x)"}

            # Setup-specific weekly_bull requirement
            if _sg_w_bull and not weekly_bull:
                return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                        "bear_type": "",
                        "reason": f"{_plan_setup or setup_type} needs weekly bull alignment (have weekly_bull={weekly_bull})"}

            # Setup-specific score_bonus requirement (extra conviction on top of buy_min)
            if _sg_bonus and total_score < _effective_buy_min + _sg_bonus:
                return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                        "bear_type": "",
                        "reason": f"{_plan_setup or setup_type} needs extra conviction (score {total_score:.0f} < {_effective_buy_min + _sg_bonus})"}

        # Quality gate 1: RS leadership — don't buy underperformers
        if rs_rank < long_min_rs:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Score {total_score:.0f} qualifies but RS {rs_rank} < {long_min_rs} — wait for relative strength to improve"}

        # Quality gate 2: weekly EMA must be bullish (multi-timeframe confirmation)
        if require_w_bull and not weekly_bull:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Score {total_score:.0f}, RS {rs_rank} ✓ — but weekly EMA not bullish (needs price > W-EMA8 > W-EMA21)"}

        # Quality gate 3: elevated VIX demands higher conviction
        if vix >= high_vix and total_score < buy_min + extra:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"VIX {vix:.0f} elevated — need score {buy_min + extra}+ in volatile market (have {total_score:.0f})"}

        # Profile-driven catalyst tier enforcement (e.g. trending_leaders: T3 → WATCH only)
        _ct_rules = config.get("catalyst_tiers", {})
        if _ct_rules:
            _ct_key = f"T{catalyst_tier}"
            _ct_elig = _ct_rules.get(_ct_key, {}).get("eligible", True)
            if _ct_elig == "watch_only" or _ct_elig is False:
                return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                        "bear_type": "",
                        "reason": f"Catalyst tier {_ct_key} → WATCH per profile (score {total_score:.0f})"}

        # Phase 2A: Catalyst gate — require at least one catalyst to upgrade to BUY
        # Without a catalyst, even a high-scoring setup is a pattern without an activation event
        _cat_offset = config.get("decisions", {}).get("catalyst_override_offset", 15)
        if not has_catalyst and total_score < buy_min + _cat_offset:
            return {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "reason": f"Score {total_score:.0f}/100 — no catalyst (need PEAD/UOA/VCP/POCKET_PIVOT/SQUEEZE or score {buy_min + _cat_offset}+ to override)"}

        cat_note = " + catalyst" if has_catalyst else " (score override)"
        regime_label = f" [{regime_name}]" if regime_name != "neutral" else ""
        _raw_decision = {"verdict": "BUY", "emoji": "check", "color": "#059669",
                "bear_type": "",
                "reason": f"Score {total_score:.0f}/100, RS {rs_rank}, weekly ✓, R:R {rr_ratio:.1f}:1{cat_note}{regime_label}{_breadth_note}{_season_note}"}
    elif total_score >= watch_min:
        _raw_decision = {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                "bear_type": "",
                "reason": f"Wait for pullback — score {total_score:.0f}/100, needs {buy_min}+ [{regime_name} bar], RS {_rt.get('rs_min', gates_cfg.get('long_min_rs_rank',65))}+, weekly EMA bullish"}
    else:
        # Checklist 7.4 split: no_edge_now (monitored) vs hard_reject (AVOID).
        # Supplemental `tier` field: "monitored" flows to watchlist, "rejected"
        # is dropped. Preserves the existing WATCH/AVOID verdict field.
        _avoid_below = config.get("decisions", {}).get("avoid_below", 40)
        if total_score >= _avoid_below:
            _raw_decision = {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                    "bear_type": "",
                    "tier": "monitored",
                    "reason": f"No edge now — monitoring (score {total_score:.0f}/100 >= avoid_below {_avoid_below}, below watch_min {watch_min})"}
        else:
            _raw_decision = {"verdict": "AVOID", "emoji": "no_entry", "color": "#dc2626",
                    "bear_type": "",
                    "tier": "rejected",
                    "reason": f"No edge at current price — score {total_score:.0f}/100, weak structure"}

    # ── Hysteresis (item 3.4) ──
    # Only apply in bull/neutral long path (not bear, not short — those return earlier).
    # Require extra conviction to flip WATCH→BUY, or a clear deterioration to flip BUY→WATCH.
    # Falls back to raw verdict on any error or missing history.
    try:
        if direction == "long" and not weak_regime and ticker:
            from decision_logger import load_recent_decisions
            _recent = load_recent_decisions(days=3) or []
            _last_verdict = None
            for _rec in reversed(_recent):
                if str(_rec.get("ticker") or "").upper() == ticker.upper():
                    _last_verdict = str(_rec.get("verdict") or "").upper()
                    break
            _cur = _raw_decision.get("verdict", "")
            if _cur == "BUY" and _last_verdict == "WATCH":
                if total_score < buy_min + 2:
                    _raw_decision = {"verdict": "WATCH", "emoji": "eye", "color": "#d97706",
                            "bear_type": "",
                            "reason": _raw_decision.get("reason", "") + " [hysteresis held]"}
            elif _cur == "WATCH" and _last_verdict == "BUY":
                if total_score >= buy_min - 2:
                    _raw_decision = {"verdict": "BUY", "emoji": "check", "color": "#059669",
                            "bear_type": "",
                            "reason": _raw_decision.get("reason", "") + " [hysteresis held]"}
    except Exception:
        pass

    return _raw_decision


# ── New Phase 1 Functions ───────────────────────────────────────────────────

def penalize_earnings_risk(ticker: str, earnings_dict: dict | None, hold_days: int = 5) -> int:
    """Penalty if earnings within 5-day hold period (Change 9).
    Swing trades should NOT hold through earnings (binary event risk).
    Returns: penalty points to subtract from score (-15 if within hold period)
    """
    if not earnings_dict or "date" not in earnings_dict:
        return 0

    from datetime import datetime
    try:
        today = datetime.now().date()
        earnings_date = earnings_dict["date"]
        if isinstance(earnings_date, str):
            earnings_date = datetime.strptime(earnings_date, "%Y-%m-%d").date()

        days_to_earnings = (earnings_date - today).days

        # If earnings within hold period, major penalty
        if 0 <= days_to_earnings <= hold_days:
            return -15
        # If earnings within 10 days, light penalty
        elif 5 < days_to_earnings <= 10:
            return -5
    except Exception:
        pass

    return 0


def _score_analyst_revisions(analyst_data: dict | None) -> tuple[int, str]:
    """Score based on recent analyst upgrades/downgrades (10-day window) (Change 10).
    Replace stale Zacks Rank with daily-updated analyst sentiment.
    Returns: (points, label)
    """
    ad = analyst_data or {}
    upgrades = ad.get("upgrades_10d", 0)
    downgrades = ad.get("downgrades_10d", 0)

    pts = 0
    label = ""

    if upgrades >= 3:
        pts = 5
        label = f"Strong revisions up ({upgrades} upgrades)"
    elif upgrades >= 1:
        pts = 3
        label = f"Positive revisions ({upgrades} upgrades)"

    if downgrades >= 3:
        pts -= 5
        label = f"Deteriorating ({downgrades} downgrades)"
    elif downgrades >= 1:
        pts -= 2

    pts = max(0, min(pts, 5))
    return pts, label


def _score_iv_rank(options_data: dict | None) -> int:
    """Score IV rank: higher IV = options expensive. Don't buy expensive calls (Change 11).
    Returns: points (0-3)
    """
    if not options_data:
        return 0

    iv_rank = options_data.get("iv_rank", 50)

    if iv_rank < 30:
        return 0  # IV cheap — don't score for sentiment
    elif iv_rank > 70:
        return 3  # IV expensive — don't buy calls
    else:
        return 1  # IV neutral


def calculate_trade_plan(df: pd.DataFrame, sr: dict, indicators: dict, config: dict) -> dict:
    """Generate entry/stop/targets based on S/R + ATR (Change 13).
    Entry: Retracement to support; Stop: 2 ATR below; Targets: Resistance + 2x risk.
    Returns: trade plan dict with entry/stop/targets and reasoning.
    """
    price = df["Close"].iloc[-1]
    atr = indicators.get("atr", 1.0)
    support = sr.get("support", price * 0.95)
    resistance = sr.get("resistance", price * 1.05)
    ema21 = indicators.get("ema21", price)

    # Entry zone: EMA21 pullback zone (primary) + VP POC / support as floor
    # Fix 3 (2026-04-15): proper entry zone for swing trading
    vp = _volume_profile_full(df, lookback=60, bins=30)
    vp_poc = vp.get("poc") or ema21
    vp_val = vp.get("val") or support

    entry_high = ema21  # buy at or below EMA21 (value zone ceiling)
    entry_low = max(support, vp_val) if vp_val else support  # floor = support or VP-VAL
    entry = (entry_low + entry_high) / 2  # midpoint

    # Fix 6 (2026-04-15): structural stop-loss — use the lowest of:
    #   prior swing low (5-bar), VP-VAL, or EMA50
    # Then add 0.5 ATR buffer below for noise protection
    swing_lows = df["Low"].rolling(5).min()
    prior_swing_low = float(swing_lows.iloc[-2]) if len(swing_lows) >= 2 else entry_low
    ema50 = indicators.get("ema50") or entry_low
    structural_stop = min(prior_swing_low, vp_val or prior_swing_low, ema50)
    stop = structural_stop - (atr * 0.5)  # small buffer below structure

    # Targets: Resistance and 2x risk above entry
    target1 = resistance
    risk = entry - stop
    target2 = entry + (risk * 2.0) if risk > 0 else resistance
    target2 = max(target2, resistance)

    # Calculate R:R ratio
    reward = target2 - entry
    rr_ratio = reward / risk if risk > 0 else 0

    # Setup classification
    if price > resistance * 0.98:
        setup_type = "Breakout Above Resistance"
    elif price < support * 1.02:
        setup_type = "Support Bounce"
    elif indicators.get("ema_signal") == "BULLISH STACK":
        setup_type = "EMA Stack Alignment"
    else:
        setup_type = "Range Breakout"

    return {
        "entry_low": round(entry_low, 2),
        "entry": round(entry, 2),
        "entry_high": round(entry_high, 2),
        "stop": round(stop, 2),
        "target1": round(target1, 2),
        "target2": round(target2, 2),
        "rr_ratio": round(rr_ratio, 2),
        "setup_type": setup_type,
        "atr_used": round(atr, 2),
        "reason": (
            f"{setup_type}: Enter ${entry} (±${entry - entry_low:.2f}), "
            f"Stop ${stop} (2 ATR), Targets ${target1}/${target2}, "
            f"R:R {rr_ratio:.1f}:1"
        )
    }


# ── Methodology Pre-Trade Checklist ──────────────────────────────────────────
# Five booleans matching the spoken methodology: Dow / Wyckoff-proxy / MA stack /
# Sector strength / No-late-wave. Uses only data already computed during the
# scan — no new network calls. The aggregate `passes` count gates the trade
# (need >=3 of 5 to enter; <3 is informational).

def methodology_checklist(df: pd.DataFrame,
                          weekly_df: "pd.DataFrame | None",
                          spy_close: "pd.Series | None",
                          sector_etf_data: dict | None,
                          elliott_wave: dict | None,
                          ticker_sector_etf: str | None = None) -> dict:
    """
    Returns:
        {
          "checks": {
            "dow_uptrend":      {"pass": bool, "reason": str},
            "wyckoff_markup":   {"pass": bool, "reason": str},
            "ma_alignment":     {"pass": bool, "reason": str},
            "sector_strength":  {"pass": bool, "reason": str},
            "no_late_wave":     {"pass": bool, "reason": str},
          },
          "passes": int (0..5),
          "verdict": "STRONG" | "OK" | "WEAK"  (>=4 / 3 / <3),
        }

    sector_etf_data shape: top-level dict keyed by ETF symbol (XLK, XLE, ...)
    where each entry has {sector, perf_pct, vs_spy_pct, outperforming, rank}.
    ticker_sector_etf: the mapped ETF for this ticker (e.g. "XLE" for an oil name).
    """
    checks: dict[str, dict] = {}

    def _hh_hl(series, window: int) -> tuple[bool, bool]:
        """True/False for higher-high and higher-low over the last `window` bars."""
        if series is None or len(series) < window:
            return (False, False)
        recent = series.iloc[-window:]
        mid = len(recent) // 2
        return (
            float(recent.iloc[mid:].max()) > float(recent.iloc[:mid].max()),
            float(recent.iloc[mid:].min()) > float(recent.iloc[:mid].min()),
        )

    # 1) Dow Theory — primary trend confirmed on daily (~120d) OR weekly (~26w).
    # Per spoken methodology: "Higher highs and lows on daily weekly". Either
    # timeframe confirming = pass; both confirming = explicit "STRONG" reason.
    try:
        d_hh, d_hl = _hh_hl(spy_close, 120) if spy_close is not None else (False, False)
        # Build SPY weekly proxy by resampling daily, since spy_weekly isn't passed in
        spy_weekly = None
        if spy_close is not None and len(spy_close) >= 130:
            try:
                spy_weekly = spy_close.resample("W").last().dropna()
            except Exception:
                spy_weekly = None
        w_hh, w_hl = _hh_hl(spy_weekly, 26) if spy_weekly is not None else (False, False)
        daily_ok = d_hh and d_hl
        weekly_ok = w_hh and w_hl
        if daily_ok and weekly_ok:
            checks["dow_uptrend"] = {"pass": True,
                "reason": "SPY HH+HL on both daily (120d) and weekly (26w) — primary trend confirmed"}
        elif daily_ok:
            checks["dow_uptrend"] = {"pass": True,
                "reason": "SPY HH+HL on daily (120d) — daily uptrend confirmed"}
        elif weekly_ok:
            checks["dow_uptrend"] = {"pass": True,
                "reason": "SPY HH+HL on weekly (26w) — weekly uptrend confirmed"}
        elif spy_close is None or len(spy_close) < 60:
            checks["dow_uptrend"] = {"pass": False, "reason": "SPY history unavailable"}
        else:
            checks["dow_uptrend"] = {"pass": False,
                "reason": (
                    f"No HH+HL: daily HH={d_hh} HL={d_hl} (120d), "
                    f"weekly HH={w_hh} HL={w_hl} (26w)"
                )}
    except Exception as e:
        checks["dow_uptrend"] = {"pass": False, "reason": f"Dow check error: {e}"}

    # 2) Wyckoff markup proxy — price rising on volume above 20d avg over last 10 bars
    # (Real Wyckoff phase classifier is gap #1 in the roadmap; this is an interim proxy.)
    try:
        if len(df) >= 30:
            close = df["Close"]
            vol = df["Volume"]
            close_now = float(close.iloc[-1])
            close_10ago = float(close.iloc[-10])
            avg_vol_20 = float(vol.rolling(20).mean().iloc[-1])
            avg_vol_recent = float(vol.iloc[-5:].mean())
            price_rising = close_now > close_10ago
            volume_supporting = avg_vol_recent >= 0.9 * avg_vol_20
            ok = price_rising and volume_supporting
            chg_pct = (close_now / close_10ago - 1) * 100 if close_10ago else 0
            checks["wyckoff_markup"] = {
                "pass": ok,
                "reason": (
                    f"Markup proxy: +{chg_pct:.1f}% over 10d on "
                    f"{'supporting' if volume_supporting else 'thin'} volume"
                    if ok else
                    f"Not in markup: price {chg_pct:+.1f}% over 10d, "
                    f"volume {'OK' if volume_supporting else 'thin'}"
                ),
            }
        else:
            checks["wyckoff_markup"] = {"pass": False, "reason": "<30 bars history"}
    except Exception as e:
        checks["wyckoff_markup"] = {"pass": False, "reason": f"Wyckoff proxy error: {e}"}

    # 3) MA alignment — price > 50d MA > 200d MA
    try:
        if len(df) >= 200:
            close = df["Close"]
            price = float(close.iloc[-1])
            sma50 = float(close.rolling(50).mean().iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1])
            above_50 = price > sma50
            stack = sma50 > sma200
            ok = above_50 and stack
            checks["ma_alignment"] = {
                "pass": ok,
                "reason": (
                    f"Price ${price:.2f} > 50d ${sma50:.2f} > 200d ${sma200:.2f}"
                    if ok else
                    f"Stack broken: price=${price:.2f} 50d=${sma50:.2f} 200d=${sma200:.2f}"
                ),
            }
        else:
            checks["ma_alignment"] = {"pass": False, "reason": f"<200 bars ({len(df)})"}
    except Exception as e:
        checks["ma_alignment"] = {"pass": False, "reason": f"MA check error: {e}"}

    # 4) Sector strength — ticker's sector ETF outperforming SPY (63d lookback).
    # sector_etf_data is keyed by ETF symbol (XLK, XLE, ...). Each entry has
    # {sector, perf_pct, vs_spy_pct, outperforming, rank}.
    try:
        if not (sector_etf_data and isinstance(sector_etf_data, dict)):
            checks["sector_strength"] = {"pass": False, "reason": "No sector ETF data"}
        else:
            etf_key = (ticker_sector_etf or "").upper().strip()
            entry = sector_etf_data.get(etf_key) if etf_key else None
            if not entry or not isinstance(entry, dict):
                checks["sector_strength"] = {
                    "pass": False,
                    "reason": f"No ETF mapping for sector ({etf_key or 'unmapped'})",
                }
            else:
                outperforming = bool(entry.get("outperforming"))
                vs_spy = entry.get("vs_spy_pct")
                perf = entry.get("perf_pct")
                rank = entry.get("rank")
                sector_label = entry.get("sector", etf_key)
                vs_spy_str = f"{float(vs_spy):+.1f}%" if vs_spy is not None else "—"
                perf_str = f"{float(perf):+.1f}%" if perf is not None else "—"
                checks["sector_strength"] = {
                    "pass": outperforming,
                    "reason": (
                        f"{etf_key} ({sector_label}): {perf_str} 63d, {vs_spy_str} vs SPY"
                        + (f", rank #{rank}" if rank else "")
                        + (" — outperforming" if outperforming else " — lagging")
                    ),
                }
    except Exception as e:
        checks["sector_strength"] = {"pass": False, "reason": f"Sector check error: {e}"}

    # 5) No late wave — Elliott Wave is NOT in late wave 4 ending or wave 5
    # (your spoken rule: "no major reversal, like Elliott Wave 4 ending")
    try:
        ew = elliott_wave or {}
        wave_label = str(ew.get("wave_label") or ew.get("wave") or "").strip()
        wave_num = ew.get("wave_number") or ew.get("wave_n")
        # Try to extract a number if not provided directly
        if wave_num is None and wave_label:
            for ch in wave_label:
                if ch.isdigit():
                    try:
                        wave_num = int(ch)
                        break
                    except ValueError:
                        continue
        late_wave = False
        reason = "No late-wave structure detected"
        if wave_num is not None:
            late_wave = int(wave_num) >= 4
            reason = (
                f"In Wave {wave_num} ({wave_label}) — "
                + ("late-cycle, reversal risk" if late_wave else "early/mid-cycle, room to run")
            )
        elif wave_label:
            label_lower = wave_label.lower()
            if "wave 4" in label_lower or "wave 5" in label_lower or "ending" in label_lower:
                late_wave = True
                reason = f"Late-wave label: {wave_label}"
            else:
                reason = f"Wave context: {wave_label}"
        checks["no_late_wave"] = {"pass": not late_wave, "reason": reason}
    except Exception as e:
        checks["no_late_wave"] = {"pass": True, "reason": f"Wave check skipped: {e}"}

    passes = sum(1 for c in checks.values() if c.get("pass"))
    verdict = "STRONG" if passes >= 4 else ("OK" if passes >= 3 else "WEAK")
    return {"checks": checks, "passes": passes, "verdict": verdict}


def _build_audit_trail(ticker: str, score_breakdown: dict | None,
                        gate: dict | None, theory_conf: dict | None,
                        methodology: dict | None, options_kpis: dict | None,
                        trade_plan: dict | None, decision_verdict: str | None,
                        regime: dict | None, earnings: dict | None,
                        info: dict | None) -> dict:
    """
    P4.39 — Build a structured audit trail explaining the verdict.

    Returns:
      {
        ticker, mode, verdict,
        hard_gates_passed: bool,
        gate_failures: [...],
        theory_confluence: {direction, count, gate_pass, states},
        scoring: {total, technicals, catalyst, rs, smart_money, quality},
        risk_reward: float,
        entry_quality: str,
        earnings_risk: str,
        regime: str,
        options_verdict: str,
        why_buy: [str, ...],
        red_flags: [str, ...],
      }
    """
    sb = score_breakdown or {}
    gate = gate or {}
    tc = theory_conf or {}
    mc = methodology or {}
    ok = options_kpis or {}
    tp = trade_plan or {}
    rg = regime or {}
    er = earnings or {}
    inf = info or {}

    why_buy: list[str] = []
    red_flags: list[str] = []

    # Score-driven positives
    score = sb.get("total_score") or sb.get("score") or 0
    if score >= 80:
        why_buy.append(f"Score {score}/100 — high conviction")
    elif score >= 70:
        why_buy.append(f"Score {score}/100 — solid setup")

    # Theory confluence positives
    if tc.get("hard_gate_pass") and tc.get("direction") == "BULLISH":
        bull_aligned = [k for k, v in (tc.get("bull_aligned") or {}).items() if v]
        if bull_aligned:
            why_buy.append(f"Theory confluence ({len(bull_aligned)}/4): {', '.join(bull_aligned)}")
    elif tc.get("hard_gate_pass") is False:
        red_flags.append(f"Theory confluence FAIL: {tc.get('evidence_summary', 'insufficient agreement')}")

    # Methodology checklist
    if mc.get("verdict") == "STRONG":
        why_buy.append(f"Technical confirmation STRONG ({mc.get('passes', 0)}/5 indicators)")
    elif mc.get("verdict") == "WEAK":
        red_flags.append(f"Technical confirmation WEAK ({mc.get('passes', 0)}/5 indicators)")

    # Options flow
    opt_v = (ok.get("verdict") or {}).get("verdict") if ok else None
    if opt_v == "BULLISH":
        why_buy.append(f"Options flow BULLISH (edge {(ok.get('verdict') or {}).get('edge', 0)}/10)")
    elif opt_v == "BEARISH":
        red_flags.append("Options flow BEARISH — institutional hedging")

    # R:R
    rr = tp.get("rr_ratio") or 0
    if rr >= 3.5:
        why_buy.append(f"R:R {rr:.1f}:1 — asymmetric reward")
    elif rr < 2.0:
        red_flags.append(f"R:R {rr:.1f}:1 — thin reward")

    # Entry quality
    eq = tp.get("entry_quality") or ""
    if eq in ("FRESH", "PULLBACK"):
        why_buy.append(f"Entry quality: {eq}")
    elif eq in ("EXTENDED", "MISSED"):
        red_flags.append(f"Entry quality: {eq} — late location")

    # Earnings + regime context
    days_to_earn = er.get("days_to_earnings")
    if days_to_earn is None or days_to_earn > 14:
        earnings_risk = "clear"
    elif days_to_earn <= 5:
        earnings_risk = f"BLACKOUT ({days_to_earn}d)"
        red_flags.append(f"Earnings in {days_to_earn} days")
    else:
        earnings_risk = f"{days_to_earn}d"

    return {
        "ticker": ticker,
        "verdict": decision_verdict or "WATCH",
        "hard_gates_passed": gate.get("passed", False),
        "gate_failures": gate.get("reasons", []),
        "theory_confluence": {
            "direction": tc.get("direction"),
            "count": tc.get("bull_count"),
            "min_required": tc.get("min_required"),
            "gate_pass": tc.get("hard_gate_pass"),
            "states": tc.get("states", {}),
        },
        "scoring": {
            "total": score,
            "tech": sb.get("tech_score"),
            "catalyst": sb.get("cat_score"),
            "rs_sector": sb.get("rs_score"),
            "smart_money": sb.get("sm_score"),
            "quality": sb.get("qg_score") or sb.get("fund_score"),
        },
        "risk_reward": rr,
        "entry_quality": eq,
        "earnings_risk": earnings_risk,
        "regime": rg.get("regime") or rg.get("regime4"),
        "options_verdict": opt_v,
        "why_buy": why_buy,
        "red_flags": red_flags,
    }


# ── Full Analysis Pipeline ───────────────────────────────────────────────────

def analyze_ticker(ticker: str, df: pd.DataFrame, info: dict,
                   regime: dict, earnings: dict, news: dict,
                   insider: dict, spy_close: "pd.Series | None",
                   config: dict, zacks: dict | None = None,
                   tv_rating: dict | None = None,
                   weekly_df: "pd.DataFrame | None" = None,
                   options_data: dict | None = None,
                   beat_rate: dict | None = None,
                   stocktwits: dict | None = None,
                   sector_etf_data: dict | None = None,
                   extra_fund: dict | None = None,
                   congressional: dict | None = None,
                   reddit_wsb: dict | None = None,
                   zacks_sell: bool = False,
                   analyst: dict | None = None,
                   uoa: dict | None = None,
                   borrow: dict | None = None,
                   finnhub: dict | None = None,
                   fmp: dict | None = None,
                   sec: dict | None = None,
                   breadth: dict | None = None,
                   premarket: dict | None = None,
                   inst_trend: dict | None = None,
                   gamma: dict | None = None,
                   eps_trend: dict | None = None,
                   finviz: dict | None = None,
                   quote_snapshot: dict | None = None,
                   news_articles: list | None = None,
                   options_chain: dict | None = None,
                   df_4h: "pd.DataFrame | None" = None) -> dict:
    """
    Run complete analysis pipeline for a single ticker.
    Returns full result dict with gate, scores, plan, decision.
    """
    price = float(df["Close"].iloc[-1])
    volume = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else volume

    # Gate check
    gate = pre_trade_gate(ticker, df, info, regime, earnings, config, breadth=breadth)

    # VWAP + pattern detection
    vwap_data    = _vwap(df)
    pattern_data = _detect_patterns(df)

    # Merge fmp/finnhub supplemental data into extra_fund before scoring
    # (avoids dead fetches — data was collected, now actually used)
    _ef = dict(extra_fund or {})
    if fmp:
        for key in ("ev_ebitda", "fcf_yield", "roe", "roa", "gross_margin",
                    "debt_equity", "current_ratio", "institutional_pct"):
            if fmp.get(key) is not None and _ef.get(key) is None:
                _ef[key] = fmp[key]
    if finnhub:
        # Institutional ownership from finnhub analyst consensus
        fh_buy  = finnhub.get("analyst_buy", 0) or 0
        fh_hold = finnhub.get("analyst_hold", 0) or 0
        fh_sell = finnhub.get("analyst_sell", 0) or 0
        fh_total = fh_buy + fh_hold + fh_sell
        if fh_total > 0 and not _ef.get("analyst_strong_buy_pct"):
            _ef["fh_analyst_buy_pct"] = round(fh_buy / fh_total * 100, 1)
        # Beat rate from finnhub earnings surprises (if beat_rate not already populated)
        if not beat_rate and finnhub.get("earnings_surprises"):
            surprises = finnhub["earnings_surprises"]
            if isinstance(surprises, list) and surprises:
                beats = sum(1 for s in surprises if isinstance(s, dict)
                            and (s.get("actual", 0) or 0) > (s.get("estimate", 0) or 0))
                total_s = len(surprises)
                beat_rate = {"beat_rate": round(beats / total_s, 2), "n": total_s,
                             "source": "finnhub"}

    # FINVIZ enrichment — merge higher-fidelity fundamental + sentiment data into _ef
    if finviz:
        # Fundamentals: EPS growth projections (% already parsed as floats by data_fetcher)
        fvz_eps_this = finviz.get("eps_growth_this_yr")   # e.g. 12.5 means 12.5%
        fvz_eps_next = finviz.get("eps_growth_next_yr")
        if fvz_eps_this is not None and _ef.get("eps_growth_this_yr") is None:
            _ef["eps_growth_this_yr"] = fvz_eps_this / 100.0  # normalize to ratio
        if fvz_eps_next is not None and _ef.get("eps_growth_next_yr") is None:
            _ef["eps_growth_next_yr"] = fvz_eps_next / 100.0

        # Valuation: PEG, forward P/E, P/S
        for fvz_key, ef_key in (("peg", "peg"), ("fwd_pe", "fwd_pe"), ("ps", "ps")):
            v = finviz.get(fvz_key)
            if v is not None and _ef.get(ef_key) is None:
                _ef[ef_key] = v

        # Derive estimate_revision from Finviz EPS growth when analyst data is missing
        if not _ef.get("estimate_revision"):
            _fv_this = finviz.get("eps_growth_this_yr")
            _fv_next = finviz.get("eps_growth_next_yr")
            if _fv_this is not None and _fv_next is not None:
                if _fv_next > _fv_this + 5:
                    _ef["estimate_revision"] = "up_strong"
                elif _fv_next > _fv_this:
                    _ef["estimate_revision"] = "up"
                elif _fv_next < _fv_this - 10:
                    _ef["estimate_revision"] = "down"
                else:
                    _ef["estimate_revision"] = "flat"

        # Balance sheet / quality
        for fvz_key, ef_key in (
            ("roe_pct", "roe"), ("roa_pct", "roa"),
            ("gross_margin_pct", "gross_margin"), ("oper_margin_pct", "operating_margin"),
            ("profit_margin_pct", "profit_margin"), ("current_ratio", "current_ratio"),
        ):
            v = finviz.get(fvz_key)
            if v is not None and _ef.get(ef_key) is None:
                # FINVIZ returns these as percent ints (e.g. 15.3 for 15.3%), normalize
                if fvz_key.endswith("_pct"):
                    _ef[ef_key] = v / 100.0
                else:
                    _ef[ef_key] = v

        # Institutional ownership (FINVIZ is more accurate float data than yfinance)
        inst_own = finviz.get("inst_own_pct")
        if inst_own is not None:
            _ef["institutional_pct"] = inst_own  # already %

        # Short interest — precise float data for squeeze detection
        short_float = finviz.get("short_float_pct")
        short_ratio = finviz.get("short_ratio")
        if short_float is not None:
            _ef["short_float_finviz"] = short_float
        if short_ratio is not None:
            _ef["short_ratio_finviz"] = short_ratio

        # Insider ownership — for conviction signal
        insider_own = finviz.get("insider_own_pct")
        if insider_own is not None:
            _ef["insider_own_pct_finviz"] = insider_own

        # Float shares (used for squeeze calculation — more accurate than info)
        shares_float = finviz.get("shares_float")
        if shares_float is not None:
            _ef["shares_float_finviz"] = shares_float

        # Relative volume from FINVIZ (cross-check with our yfinance calculation)
        fvz_rvol = finviz.get("rel_volume")
        if fvz_rvol is not None and _ef.get("rvol_finviz") is None:
            _ef["rvol_finviz"] = fvz_rvol

        # Earnings date from FINVIZ (more reliable than yfinance)
        fvz_earn_date = finviz.get("earnings_date")
        if fvz_earn_date and not earnings.get("earnings_date"):
            _ef["earnings_date_finviz"] = fvz_earn_date

        # SMA distances (% above/below each SMA) — for Chart tab display
        for _fk, _ek in [("sma20_pct", "sma20_pct"), ("sma50_pct", "sma50_pct"), ("sma200_pct", "sma200_pct")]:
            _v = finviz.get(_fk)
            if _v is not None:
                _ef.setdefault(_ek, _v)

        # Performance periods (weekly/monthly %)
        for _fk, _ek in [("perf_week_pct", "perf_week"), ("perf_month_pct", "perf_month"),
                         ("perf_quart_pct", "perf_quarter"), ("perf_ytd_pct", "perf_ytd")]:
            _v = finviz.get(_fk)
            if _v is not None:
                _ef.setdefault(_ek, _v)

    # Market cap, analyst price target, float, analyst count — yfinance info as final fallback
    if info:
        mc = info.get("market_cap") or info.get("marketCap")
        if mc: _ef.setdefault("market_cap", mc)
        tp = info.get("target_mean_price") or info.get("targetMeanPrice")
        if tp: _ef.setdefault("target_price", tp)
        tph = info.get("target_high_price") or info.get("targetHighPrice")
        if tph: _ef.setdefault("target_price_high", tph)
        tpl = info.get("target_low_price") or info.get("targetLowPrice")
        if tpl: _ef.setdefault("target_price_low", tpl)
        na = info.get("num_analysts") or info.get("numberOfAnalystOpinions")
        if na: _ef.setdefault("num_analysts", na)
        if not _ef.get("shares_float_finviz"):
            sf = info.get("shares_float") or info.get("floatShares")
            if sf: _ef.setdefault("shares_float", sf)
        so = info.get("sharesOutstanding")
        if so: _ef.setdefault("shares_outstanding", so)
        dy = info.get("dividend_yield") or info.get("dividendYield")
        if dy: _ef.setdefault("dividend_yield", dy)
        ps = info.get("ps_ratio") or info.get("priceToSalesTrailing12Months")
        if ps: _ef.setdefault("ps_ratio", ps)
        # institutional_pct fallback from get_stock_info (if finviz/FMP didn't supply it)
        ip = info.get("institutional_pct")
        if ip: _ef.setdefault("institutional_pct", ip)

    # Score all pillars regardless (for display)
    fund = score_fundamentals(info, zacks, beat_rate=beat_rate, extra_fund=_ef,
                              analyst_data=analyst)

    # Zacks Sell List: −5 fundamentals penalty (mirror of Rank #1 +5)
    if zacks_sell:
        fund = dict(fund)
        fund["score"] = max(fund["score"] - 5, 0)
        fund["details"] = dict(fund.get("details", {}))
        fund["details"]["zacks_sell"] = "Zacks Sell List — bearish confirmation (−5 fund pts)"
        fund["bear_risks"] = list(fund.get("bear_risks", [])) + ["Zacks Sell List (Strong Sell)"]
    tech = score_technicals(df, regime, spy_close,
                            weekly_df=weekly_df,
                            sector_etf_data=sector_etf_data,
                            ticker=ticker,
                            info_sector=info.get("sector", "") if info else "",
                            info=info)
    sr   = tech["sr"]
    ew   = score_elliott_wave(df)

    # ── Theory Confluence Gate (P1.3 feedback) ──────────────────────────────
    # Strict Dow/Wyckoff/Elliott/Gann theory states. Hard reject if < 2
    # theories bullish-aligned. This is separate from the methodology
    # checklist (which mixes theories with technical indicators).
    theory_confluence_data: dict = {}
    try:
        from theories import theory_confluence as _theory_conf
        # Build SPY weekly proxy from daily if no separate series available
        spy_weekly_proxy = None
        if spy_close is not None and len(spy_close) >= 130:
            try:
                spy_weekly_proxy = spy_close.resample("W").last().dropna()
            except Exception:
                spy_weekly_proxy = None
        theory_confluence_data = _theory_conf(
            df=df, weekly_df=weekly_df,
            spy_close=spy_close, spy_weekly=spy_weekly_proxy,
            ew_data=ew,
        )
    except Exception as _tc_err:
        log.debug(f"theory_confluence({ticker}) failed: {_tc_err}")
        theory_confluence_data = {"hard_gate_pass": True, "error": str(_tc_err)}

    # Methodology checklist — 5-step pre-trade gate matching spoken methodology
    # (Dow / Wyckoff-proxy / MA / Sector / No-late-wave). Informational; >=3 of 5
    # = OK to enter, >=4 = STRONG conviction. Surfaced in v2 dashboard Plan tab.
    _ticker_sector_etf = (info.get("sector_etf") if info else "") or ""
    if not _ticker_sector_etf:
        # Resolve from sector text (yfinance-style labels) → SPDR sector ETF symbol.
        _sector_text = ((info.get("sector") if info else "") or "").lower()
        _SECTOR_TEXT_TO_ETF = {
            "technology": "XLK", "information technology": "XLK",
            "financial": "XLF", "financials": "XLF", "financial services": "XLF",
            "healthcare": "XLV", "health care": "XLV",
            "energy": "XLE",
            "industrial": "XLI", "industrials": "XLI",
            "basic materials": "XLB", "materials": "XLB",
            "real estate": "XLRE",
            "utilities": "XLU",
            "communication services": "XLC", "communication": "XLC",
            "consumer defensive": "XLP", "consumer staples": "XLP",
            "consumer cyclical": "XLY", "consumer discretionary": "XLY", "consumer disc.": "XLY",
        }
        _ticker_sector_etf = _SECTOR_TEXT_TO_ETF.get(_sector_text, "")
    methodology = methodology_checklist(df, weekly_df, spy_close, sector_etf_data, ew,
                                        ticker_sector_etf=_ticker_sector_etf)

    # Merge UOA data into options_data for optionality scoring
    _od = dict(options_data or {})
    if uoa and uoa.get("call_flow_score", 0) + uoa.get("put_flow_score", 0) > 0:
        _od["uoa"] = True
        _od["uoa_data"] = uoa

    # Schwab options intelligence — elite-tier analysis (IV rank, P/C ratio,
    # UOA, max pain, gamma exposure, skew, term structure, verdict, per-mode
    # overlay). Returns None gracefully if Schwab credentials/tokens missing.
    options_kpis = None
    try:
        import os as _os_oi
        # Schwab credentials may live only in .env (not env vars). Lazy-load.
        if not _os_oi.environ.get("SCHWAB_APP_KEY"):
            try:
                from pathlib import Path as _Path
                _env_path = _Path(__file__).resolve().parent / ".env"
                if _env_path.exists():
                    for _line in _env_path.read_text().splitlines():
                        _line = _line.strip()
                        if _line and not _line.startswith("#") and "=" in _line:
                            _k, _v = _line.split("=", 1)
                            _os_oi.environ.setdefault(_k.strip(), _v.strip())
            except Exception:
                pass
        if _os_oi.environ.get("SCHWAB_APP_KEY") and _os_oi.environ.get("SCHWAB_REFRESH_TOKEN"):
            import options_intelligence as _oi_mod
            options_kpis = _oi_mod.fetch_and_analyze(ticker, last_price=price,
                                                     base_verdicts={"swing": "WATCH"})
    except Exception as _oi_err:
        log.debug(f"options_intelligence({ticker}) failed: {_oi_err}")
    # Promote signals from Schwab analysis into _od so existing scoring uses them
    if options_kpis:
        if options_kpis.get("uoa_calls") and not _od.get("uoa"):
            _od["uoa"] = True
            _od["uoa_data"] = {"detail": options_kpis.get("uoa_call_detail")}
        if options_kpis.get("put_call_ratio") is not None and not _od.get("pc_ratio"):
            _od["pc_ratio"] = options_kpis["put_call_ratio"]
        if options_kpis.get("iv_percentile") is not None and not _od.get("iv_rank"):
            _od["iv_rank"] = options_kpis["iv_percentile"]

    # Compute rich options intelligence from FINVIZ chain (116 strikes × full Greeks)
    _oi: dict = {}
    _poly_opts = options_chain or {}
    if _poly_opts.get("calls") or _poly_opts.get("puts"):
        try:
            _oi = compute_options_intelligence(_poly_opts, price)
            # Back-fill legacy _od fields from chain so downstream code still works
            if _oi.get("true_uoa_calls") and not _od.get("uoa"):
                _od["uoa"] = True
            if _oi.get("pc_ratio_vol") is not None and not _od.get("pc_ratio"):
                _od["pc_ratio"] = _oi["pc_ratio_vol"]
            if _oi.get("iv_rank_est") is not None and not _od.get("iv_rank"):
                _od["iv_rank"] = _oi["iv_rank_est"]
        except Exception as _e:
            import logging as _log
            _log.getLogger(__name__).warning(f"options_intelligence failed for {ticker}: {_e}")

    # Compute source-weighted Polygon news score (real NLP, not Yahoo RSS word-matching)
    _poly_news_score: dict = {}
    if news_articles:
        try:
            _poly_news_score = compute_news_sentiment_score(news_articles)
        except Exception as _e:
            import logging as _log
            _log.getLogger(__name__).warning(f"news_sentiment_score failed for {ticker}: {_e}")

    # P6: Compute direction + preliminary plan before optionality so R:R is consistent
    _trend_dir_early = tech["indicators"].get("trend_direction", "")
    _direction_early = "short" if _trend_dir_early == "downtrend" else "long"
    # Phase 3B: pass regime name to trade plan for adaptive stops
    _plan_cfg = dict(config)
    _plan_cfg["_regime_name"] = str(regime.get("regime", "neutral")).lower()
    _prelim_plan = compute_trade_plan(ticker, df, sr, tech["indicators"], _direction_early,
                                     beta=info.get("beta") if info else None,
                                     config=_plan_cfg)
    opt  = score_optionality(df, info, sr, earnings, news, options_data=_od,
                             rr_override=_prelim_plan["rr_ratio"],
                             options_intelligence=_oi,
                             news_sentiment_score=_poly_news_score)
    # Enrich borrow_data with FINVIZ short interest if borrow_data is sparse
    _borrow = dict(borrow or {})
    if finviz:
        if not _borrow.get("short_float_pct") and finviz.get("short_float_pct") is not None:
            _borrow["short_float_pct"] = finviz["short_float_pct"]
        if not _borrow.get("days_to_cover") and finviz.get("short_ratio") is not None:
            _borrow["days_to_cover"] = finviz["short_ratio"]
        if not _borrow.get("shares_float") and finviz.get("shares_float") is not None:
            _borrow["shares_float"] = finviz["shares_float"]

    sent = score_sentiment(news, insider, info, stocktwits=stocktwits,
                           df=df, indicators=tech["indicators"], earnings=earnings,
                           congressional=congressional,
                           reddit_wsb=reddit_wsb,
                           borrow_data=_borrow,
                           uoa_data=uoa,
                           news_sentiment_score=_poly_news_score)

    # Block 1 — MTF Hard Gate: daily bullish but weekly bearish → cap at WATCH
    mtf_conflict = False
    mtf_label = ""
    if weekly_df is not None and not (hasattr(weekly_df, "empty") and weekly_df.empty):
        try:
            wc = (weekly_df["Close"].squeeze()
                  if isinstance(weekly_df["Close"], pd.DataFrame) else weekly_df["Close"])
            wc = wc.dropna()
            if len(wc) >= 21:
                we21   = float(wc.ewm(span=21, adjust=False).mean().iloc[-1])
                we50   = float(wc.ewm(span=50, adjust=False).mean().iloc[-1])
                wprice = float(wc.iloc[-1])
                weekly_bearish = wprice < we21 or we21 < we50
                _daily_tech_score = tech.get("score", 0)
                _daily_tech_norm  = round(_daily_tech_score / max(tech.get("max", 38), 1) * 30)
                if weekly_bearish and _daily_tech_norm >= 18:
                    mtf_conflict = True
                    mtf_label = "Weekly Headwind"
        except Exception:
            pass

    # Block 2 — SMC OB entry/stop override: use OB entry zone if within 2% of price
    smc_result = tech.get("smc_result", {})
    ob_entry_zone = smc_result.get("ob_entry_zone")
    ob_stop       = smc_result.get("ob_stop")
    if ob_entry_zone is not None and ob_stop is not None:
        try:
            _cur_price = float(df["Close"].iloc[-1])
            _ob_mid    = float(ob_entry_zone) if not isinstance(ob_entry_zone, (list, tuple)) else sum(ob_entry_zone) / 2
            if abs(_ob_mid - _cur_price) / _cur_price <= 0.02:
                # OB entry zone is within 2% — will be applied to plan after plan is computed
                pass  # stored in smc_result for post-plan override below
        except Exception:
            pass

    # TV Rating bonus (applied before normalization, ±3 pts)
    tv_bonus = 0
    if tv_rating:
        rec = tv_rating.get("recommendation", "NEUTRAL")
        if   rec == "STRONG_BUY":  tv_bonus = 3
        elif rec == "BUY":         tv_bonus = 1
        elif rec == "SELL":        tv_bonus = -1
        elif rec == "STRONG_SELL": tv_bonus = -3
        tech["score"] = max(0, min(30, tech["score"] + tv_bonus))
        if tv_bonus > 0:
            tech["details"]["tv_rating"] = f"TV {rec} (+{tv_bonus})"
        elif tv_bonus < 0:
            tech["details"]["tv_rating"] = f"TV {rec} ({tv_bonus})"

    # ── 5-Pillar Scoring (Phase 6) ─────────────────────────────────────────────
    # Tech Structure(35) + Catalyst(20) + RS+Sector(20) + Smart Money(15) + Quality Gate(10) = 100
    _scfg      = config.get("scoring", {})
    _tech_rmax = int(_scfg.get("technicals_max",      38))   # raw max from score_technicals()
    _opt_rmax  = int(_scfg.get("optionality_max",     20))   # raw max from score_optionality()
    _sent_rmax = int(_scfg.get("sentiment_max",       10))   # raw max from score_sentiment()
    _fund_rmax = int(_scfg.get("fundamentals_max",    30))   # raw max from score_fundamentals()

    # Fix #18: Weight decay for short-hold momentum setups
    # Impulse Catalyst (5-8d hold) — reduce fundamentals weight from 10 to 5,
    # redistribute +5 to technicals. Prevents fundamentals from diluting momentum signals.
    #
    # Audit ranking-flaw #1/#2/#3 — pillar maxes chosen per SCORING_MODE:
    #   normalized (default): floating-point pass-through from RAW_MAXES
    #                         (tech=28, cat=30, rs=20, sm=15, fund=30; TOTAL=123)
    #                         → 22.76 / 24.39 / 16.26 / 12.20 / 24.39  (sum 100.0)
    #                         Tech raw 38 → 28: correlation haircut (flaw #3).
    #                         Reclaimed 10 pts → Catalyst (distinct UOA/PEAD/VCP).
    #   legacy:               35 / 20 / 20 / 15 / 10  (tech pass-through 92%, fund 33%)
    if SCORING_MODE == "swing_optimized":
        # DEFAULT: 5-15d hold optimization. Fundamentals cut to 8 (quarterly
        # metrics don't predict weekly price action). Catalyst boosted to 32
        # (PEAD, UOA, VCP, squeeze, pocket_pivot — actual swing signals).
        _pillar_tech_max = _PILLAR_TECH_MAX_SWING
        _pillar_cat_max  = _PILLAR_CAT_MAX_SWING
        _pillar_rs_max   = _PILLAR_RS_MAX_SWING
        _pillar_sm_max   = _PILLAR_SM_MAX_SWING
        _pillar_qg_max   = _PILLAR_QG_MAX_SWING
    elif SCORING_MODE == "normalized":
        _pillar_tech_max = _PILLAR_TECH_MAX_NORM
        _pillar_cat_max  = _PILLAR_CAT_MAX_NORM
        _pillar_rs_max   = _PILLAR_RS_MAX_NORM
        _pillar_sm_max   = _PILLAR_SM_MAX_NORM
        _pillar_qg_max   = _PILLAR_QG_MAX_NORM
    else:  # "legacy"
        _pillar_tech_max = 35
        _pillar_cat_max  = 20
        _pillar_rs_max   = 20
        _pillar_sm_max   = 15
        _pillar_qg_max   = 10

    # Profile-driven scoring weights override (e.g. trending_leaders profile)
    _sw = config.get("scoring_weights", {})
    if _sw:
        _pillar_tech_max = float(_sw.get("trend_structure", _pillar_tech_max))
        _pillar_rs_max   = float(_sw.get("rs_sector", _pillar_rs_max))
        _pillar_cat_max  = float(_sw.get("catalyst_expansion", _pillar_cat_max))
        _pillar_sm_max   = float(_sw.get("smart_money", _pillar_sm_max))
        _pillar_qg_max   = float(_sw.get("quality_fundamentals", _pillar_qg_max))

    _setup_type_lower = (_prelim_plan.get("setup_type", "") or "").lower()

    # Ranking-flaw #15: setup-family weight shifts (previously hardcoded to 4 setups).
    # Configurable substring map → tech/fund pillar adjustments.
    # Short-hold momentum setups (impulse/catalyst/pead/earnings_drift) → +5/-5.
    # Pattern setups (squeeze/pocket_pivot/vcp) → +3/-3 (still want some fundamentals).
    # "52wk_breakout" is intentionally omitted — it still needs strong fundamentals.
    SETUP_WEIGHT_SHIFTS = {
        "impulse":          {"tech": +5, "fund": -5},
        "catalyst":         {"tech": +5, "fund": -5},
        "pead":             {"tech": +5, "fund": -5},
        "earnings_drift":   {"tech": +5, "fund": -5},
        "squeeze":          {"tech": +3, "fund": -3},
        "pocket_pivot":     {"tech": +3, "fund": -3},
        "vcp":              {"tech": +3, "fund": -3},
        # "52wk_breakout" intentionally NOT shifted — still wants strong fundamentals
    }
    _setup_shift = None
    for _sk, _sv in SETUP_WEIGHT_SHIFTS.items():
        if _sk in _setup_type_lower:
            _setup_shift = _sv
            break
    if _setup_shift:
        _pillar_tech_max += _setup_shift["tech"]
        _pillar_qg_max   += _setup_shift["fund"]
        _pillar_qg_max   = max(5, _pillar_qg_max)  # keep fund floor at 5

    # Ranking flaw #12: regime-conditional pillar weight adjustments.
    # CONFIG-DRIVEN as of 2026-04-30 — was hardcoded bear/bull shifts.
    # Reads `regime_weight_shifts` from config.json (Phase 1: walk-forward live wiring).
    # Each regime entry is {tech: ±N, qg: ±N}. Pillar maxes clamped to non-negative.
    # When _enabled=false or regime not in config, falls back to hardcoded behavior
    # for backward compatibility.
    _regime_name_lc = str(regime.get("regime", "neutral")).lower()
    _regime4_lc     = str(regime.get("regime4", "") or "").lower()
    _rw_cfg = config.get("regime_weight_shifts") or {}
    if _rw_cfg.get("_enabled", True):
        # Resolve regime key — prefer regime4 (more granular), fall back to bull/bear
        _regime_key = _regime4_lc if _regime4_lc and _regime4_lc in _rw_cfg else None
        if not _regime_key:
            if _regime_name_lc == "bear" or "risk_off" in _regime4_lc:
                _regime_key = "risk_off_trending"
            elif _regime_name_lc == "bull" or _regime4_lc == "risk_on_trending":
                _regime_key = "risk_on_trending"
        _shift = (_rw_cfg.get(_regime_key) or {}) if _regime_key else {}
        _t_shift = float(_shift.get("tech", 0))
        _qg_shift = float(_shift.get("qg", 0))
        # Apply shifts (negative shifts capped by current pillar size)
        if _t_shift < 0:
            _t_shift = -min(abs(_t_shift), _pillar_tech_max)
        if _qg_shift < 0:
            _qg_shift = -min(abs(_qg_shift), _pillar_qg_max)
        _pillar_tech_max = max(0, _pillar_tech_max + _t_shift)
        _pillar_qg_max   = max(0, _pillar_qg_max + _qg_shift)
    else:
        # Legacy hardcoded behavior — preserved for rollback
        if _regime_name_lc == "bear" or "risk_off" in _regime4_lc:
            _bear_shift = min(5, _pillar_tech_max)
            _pillar_tech_max = max(0, _pillar_tech_max - _bear_shift)
            _pillar_qg_max   = max(0, _pillar_qg_max + _bear_shift)
        elif _regime_name_lc == "bull" or _regime4_lc == "risk_on_trending":
            _bull_shift = min(3, _pillar_qg_max)
            _pillar_tech_max = max(0, _pillar_tech_max + _bull_shift)
            _pillar_qg_max   = max(0, _pillar_qg_max - _bull_shift)

    # Pillar 1 — Tech Structure & Trend
    tech_score_norm = round(tech["score"] / max(tech.get("max", _tech_rmax), 1) * _pillar_tech_max)

    # Pillar 2 — Catalyst & Optionality
    # Ranking-flaw #14: Despite the "catalyst" label, this pillar is primarily
    # driven by optionality signals (UOA, IV rank, P/C ratio). Fundamental
    # catalysts (earnings beats, guidance raises) are currently distributed
    # across Technicals (squeeze, pocket pivot) and Smart Money pillars.
    # Backward-compat: variable name `cat_score_norm` retained — downstream
    # consumers already read this field as the "Catalyst" pillar in result dicts.
    cat_score_norm = round(opt["score"] / max(opt.get("max", _opt_rmax), 1) * _pillar_cat_max)

    # BHE Gap 6: data prep. Cap is applied AFTER direction is resolved (~line 7350).
    _fund_details = (fund or {}).get("details") or {}
    _net_margin = _fund_details.get("net_margin_pct")
    _roe = _fund_details.get("roe") or _fund_details.get("return_on_equity")
    try:
        _bhe6_nm = float(_net_margin) if _net_margin is not None else None
        _bhe6_roe = float(_roe) if _roe is not None else None
    except (TypeError, ValueError):
        _bhe6_nm = _bhe6_roe = None

    # Pillar 3 — RS + Sector Rotation
    # Ranking-flaw #6: sector-outperformance multiplier is configurable via
    # scoring.rs_sector_out_multiplier (default 1.1 preserves legacy behaviour).
    _rs_rank    = int(tech["indicators"].get("rs_rank", 50))
    _sector_out = bool(tech["indicators"].get("sector_outperforming", False))
    _sector_mult = float(_scfg.get("rs_sector_out_multiplier", 1.1))
    rs_score_norm = round(min(_rs_rank / 100.0 * float(_pillar_rs_max) * (_sector_mult if _sector_out else 1.0), _pillar_rs_max))

    # Pillar 4 — Smart Money / Sentiment
    sm_score_norm = round(sent["score"] / max(sent.get("max", _sent_rmax), 1) * _pillar_sm_max)

    # BHE Gap 4: data prep. Floor is applied AFTER direction is resolved (~line 7350).
    _bhe4_uoa = bool((options_data or {}).get("uoa", False) or (opt.get("uoa", False) if isinstance(opt, dict) else False))
    if False and _bhe4_uoa:  # disabled inline; applied below after direction resolves
        _sm_floor = round(_pillar_sm_max * 8.0 / 15.0)
        if sm_score_norm < _sm_floor:
            sm_score_norm = _sm_floor

    # Pillar 5 — Quality Gate / Fundamentals
    # Ranking-flaw #9: beta is now a ranking input (previously sizing-only).
    # Penalise extremes and reward the 0.8–1.3 swing-trade sweet spot via a
    # small ±1 pt adjustment applied before clamping to the pillar max.
    _beta_adj = 0.0
    _beta_val = info.get("beta") if info else None
    if _beta_val is not None:
        try:
            _b = float(_beta_val)
            if   0.8 <= _b <= 1.3: _beta_adj =  1.0   # sweet spot
            elif 1.3 <  _b <= 1.7: _beta_adj =  0.0   # neutral
            elif _b > 2.0:         _beta_adj = -1.0   # too volatile for swing
            elif _b < 0.5:         _beta_adj = -0.5   # too sleepy
        except Exception:
            pass
    qg_score_norm = round(min(_pillar_qg_max,
        (fund["score"] / max(fund.get("max", _fund_rmax), 1) * _pillar_qg_max) + _beta_adj))
    qg_score_norm = max(0, qg_score_norm)

    # Pillar 6 — Entry R:R (only when profile defines entry_rr weight)
    _entry_rr_max = float(_sw.get("entry_rr", 0)) if _sw else 0
    entry_rr_score_norm = 0
    if _entry_rr_max > 0:
        _plan_rr = float(_prelim_plan.get("rr_ratio", 0) or 0)
        _rr_pct = min(_plan_rr / 5.0, 1.0)  # 5:1 = full marks
        entry_rr_score_norm = round(_rr_pct * _entry_rr_max)

    raw_total  = tech_score_norm + cat_score_norm + rs_score_norm + sm_score_norm + qg_score_norm + entry_rr_score_norm
    # Flaw #5 fix: do NOT clamp here. The WR multiplier + unified bonuses are
    # applied first (further down, after plan/regime resolution); the single
    # final 0–100 clamp lives there. Previously this pre-clamp wasted
    # multiplier headroom (e.g. 95 × 1.2 → 114 → clamped to 100, losing 14 pts).
    normalized = float(raw_total)

    # ── Unified bonus collection (Flaw #7/#8: ONE ±5 cap across ALL sources,
    # INCLUDING Elliott Wave which previously bypassed the cap). Values are
    # only collected here; sum → ±5 cap → add to score → final 0-100 clamp
    # happens in one consolidated block after the WR multiplier call.
    _bonuses: dict[str, float] = {}
    _bonus_notes: list[str] = []

    # Pre-market unusual volume: large players accumulating overnight (+1 to +2)
    if premarket:
        _pm_ratio = premarket.get("vol_ratio", 1.0) or 1.0
        _pm_chg   = premarket.get("price_chg_pct", 0) or 0
        if _pm_ratio >= 3.0 and _pm_chg > 0:
            _bonuses["premarket"] = 2.0
            _bonus_notes.append(f"Pre-mkt vol {_pm_ratio:.1f}x avg +{_pm_chg:.1f}% (+2)")
        elif _pm_ratio >= 2.0 and _pm_chg > 0:
            _bonuses["premarket"] = 1.0
            _bonus_notes.append(f"Pre-mkt vol {_pm_ratio:.1f}x avg +{_pm_chg:.1f}% (+1)")
        elif _pm_ratio >= 2.0 and _pm_chg < -1:
            _bonuses["premarket"] = -1.0
            _bonus_notes.append(f"Pre-mkt sell vol {_pm_ratio:.1f}x avg {_pm_chg:.1f}% (-1)")

    # Institutional ownership trend: growing big-money interest (+1 to +2)
    if inst_trend:
        _it = inst_trend.get("inst_trend", "stable")
        _it_chg = inst_trend.get("net_change_pct", 0) or 0
        if _it == "increasing" and _it_chg >= 3:
            _bonuses["inst_trend"] = 2.0
            _bonus_notes.append(f"Institutional ownership growing +{_it_chg:.1f}% (+2)")
        elif _it == "increasing":
            _bonuses["inst_trend"] = 1.0
            _bonus_notes.append(f"Institutional ownership increasing (+1)")
        elif _it == "decreasing" and _it_chg <= -3:
            _bonuses["inst_trend"] = -2.0
            _bonus_notes.append(f"Institutional ownership declining {_it_chg:.1f}% (-2)")
        elif _it == "decreasing":
            _bonuses["inst_trend"] = -1.0

    # Gamma squeeze probability: high OTM call OI + high short float = explosive upside potential
    if gamma:
        _gs = gamma.get("gamma_score", 0) or 0
        _gr = gamma.get("gamma_risk", "low")
        if _gr == "high":
            _bonuses["gamma"] = 2.0
            _bonus_notes.append(f"Gamma squeeze risk HIGH (score {_gs}/100) (+2)")
        elif _gr == "moderate":
            _bonuses["gamma"] = 1.0
            _bonus_notes.append(f"Gamma squeeze potential moderate (score {_gs}/100) (+1)")

    # Earnings estimate trend: rising consensus = analysts seeing acceleration (+1 to +2)
    if eps_trend:
        _et = eps_trend.get("trend", "stable")
        _surprise_hist = eps_trend.get("surprise_history_mean", 0) or 0
        if _et == "rising" and _surprise_hist > 5:
            _bonuses["eps_trend"] = 2.0
            _bonus_notes.append(f"EPS estimates rising, avg beat {_surprise_hist:.1f}% (+2)")
        elif _et == "rising":
            _bonuses["eps_trend"] = 1.0
            _bonus_notes.append(f"EPS estimates rising (+1)")
        elif _et == "falling":
            _bonuses["eps_trend"] = -1.0
            _bonus_notes.append(f"EPS estimates falling (-1)")

    # 2026-05-08 — Performance Decay scoring (Finviz Elite).
    # Stocks with consistent positive trajectory (week → month → quarter all up)
    # tend to keep trending. Trend breaks (strong quarter but red week) flag
    # exhaustion. Uses Finviz Elite pre-computed performance buckets.
    if finviz:
        _pw = finviz.get("perf_week_pct")
        _pm = finviz.get("perf_month_pct")
        _pq = finviz.get("perf_quarter_pct")
        _py = finviz.get("perf_year_pct")
        _ph = finviz.get("perf_half_pct")
        if all(x is not None for x in (_pw, _pm, _pq)):
            # All-positive trajectory (clean trend)
            if _pw > 0 and _pm > 0 and _pq > 0:
                if _pq >= 20 and _pm >= 5 and _pw >= 0:
                    _bonuses["perf_decay"] = 2.0
                    _bonus_notes.append(f"Strong trend: W{_pw:+.1f}% M{_pm:+.1f}% Q{_pq:+.1f}% (+2)")
                else:
                    _bonuses["perf_decay"] = 1.0
                    _bonus_notes.append(f"Trend up: W{_pw:+.1f}% M{_pm:+.1f}% Q{_pq:+.1f}% (+1)")
            # Trend break — strong quarter but red recent week (exhaustion / distribution)
            elif _pq >= 10 and _pw <= -3:
                _bonuses["perf_decay"] = -1.5
                _bonus_notes.append(f"Trend break: Q+{_pq:.1f}% but W{_pw:+.1f}% (-1.5)")
            # Persistent weakness across timeframes (avoid catching falling knife)
            elif _pq <= -10 and _pm <= -5:
                _bonuses["perf_decay"] = -1.0
                _bonus_notes.append(f"Persistent weakness: Q{_pq:.1f}% M{_pm:+.1f}% (-1)")

    # 2026-05-08 — Squeeze candidate detection (Finviz Elite).
    # Heavy short interest + concentrated institutional ownership + unusual volume
    # = high probability of a short squeeze on positive catalyst. Adds bonus AND
    # surfaces a flag downstream so the V2 dashboard can render a squeeze badge.
    _squeeze_flag = None
    _squeeze_score = 0
    if finviz:
        _sf = finviz.get("short_float_pct") or 0
        _io = finviz.get("inst_own_pct") or 0
        _rv = finviz.get("rel_volume") or 0
        _sr = finviz.get("short_ratio") or 0  # days-to-cover
        if _sf >= 15 and _io >= 80 and _rv >= 2:
            _squeeze_flag = "high"
            _squeeze_score = min(100, int(_sf * 3 + _rv * 5 + (_sr * 2)))
            _bonuses["squeeze"] = 2.0
            _bonus_notes.append(f"Squeeze candidate HIGH: SF{_sf:.0f}% IO{_io:.0f}% RV{_rv:.1f}× (+2)")
        elif _sf >= 10 and _io >= 60 and _rv >= 1.5:
            _squeeze_flag = "moderate"
            _squeeze_score = min(100, int(_sf * 2 + _rv * 4 + _sr))
            _bonuses["squeeze"] = 1.0
            _bonus_notes.append(f"Squeeze potential moderate: SF{_sf:.0f}% IO{_io:.0f}% (+1)")
        elif _sf >= 5:
            _squeeze_flag = "low"

    # 2026-05-08 — Finviz Elite Quality enrichment (additive bonus).
    # Clean compounder = high ROE/margin + healthy balance sheet (current ratio).
    # Doesn't replace fund_score (which uses many sources); adds a small bonus
    # when Finviz pre-computed quality metrics align.
    if finviz:
        _roe = finviz.get("roe_pct")
        _pm = finviz.get("profit_margin_pct")
        _cr = finviz.get("current_ratio")
        if _roe is not None and _pm is not None:
            if _roe >= 30 and _pm >= 20:
                _bonuses["fv_quality"] = 1.5
                _bonus_notes.append(f"High-quality compounder: ROE {_roe:.0f}% PM {_pm:.0f}% (+1.5)")
            elif _roe >= 20 and _pm >= 15 and (_cr is None or _cr >= 1.2):
                _bonuses["fv_quality"] = 1.0
                _bonus_notes.append(f"Quality compounder: ROE {_roe:.0f}% PM {_pm:.0f}% (+1)")
            elif _roe < 0 or (_cr is not None and _cr < 1.0):
                _bonuses["fv_quality"] = -1.0
                _bonus_notes.append(f"Balance-sheet concern: ROE {_roe:.0f}% CR {_cr or 'n/a'} (-1)")

    # SEC EDGAR catalyst signals: material 8-K events, insider clusters, activist filings
    if sec:
        _sec_signal = sec.get("catalyst_signal", "none")
        _sec_activist = any(f.get("form", "") in ("SC 13D", "SC 13G")
                            for f in (sec.get("filings") or []))
        _sec_total = 0.0
        if _sec_signal == "material_event":
            _sec_total += 2.0
            _bonus_notes.append("SEC 8-K material event (recent) (+2)")
        elif _sec_signal == "insider_cluster":
            _sec_total += 1.0
            _bonus_notes.append("SEC Form 4 insider cluster (+1)")
        if _sec_activist:
            _sec_total += 1.0
            _bonus_notes.append("SEC 13D/G activist/large holder (+1)")
        if _sec_total:
            _bonuses["sec"] = _sec_total

    # Elliott Wave (Flaw #8 fix: NOW INSIDE the unified ±5 cap).
    ew_bonus = ew.get("bonus", 0)
    if ew_bonus:
        _bonuses["elliott_wave"] = float(ew_bonus)

    # Record raw (pre-cap) bonus breakdown for debugging. Actual application
    # is consolidated further down after the WR multiplier call.
    if _bonus_notes:
        tech["details"]["new_signals"] = "; ".join(_bonus_notes)
    if ew_bonus:
        tech["details"]["ew_bonus"] = (
            f"Elliott Wave {ew.get('wave_label','?')} ({'+' if ew_bonus>0 else ''}{ew_bonus} pts)"
        )

    # Direction: ADX-gated (ranking flaw #10).
    # Previous behavior forced every non-"downtrend" stock to LONG, so "sideways"
    # / "neutral" / "" all silently became LONG. New logic requires ADX>=20 to
    # trust a trend direction; low ADX or explicit sideways/neutral => "neutral"
    # (demoted to WATCH in make_decision). Backward-compat: when ADX data is
    # missing (adx == 0) AND trend_dir is a clear uptrend/downtrend string, keep
    # the legacy long/short mapping so older fixtures don't regress to WATCH.
    trend_dir = str(tech["indicators"].get("trend_direction", "") or "").lower()
    _adx_dir_val = tech["indicators"].get("adx", 0) or 0
    try:
        _adx_dir_val = float(_adx_dir_val)
    except (TypeError, ValueError):
        _adx_dir_val = 0.0
    # Normalize trend_dir — accept "uptrend", "strong uptrend", "weak uptrend"
    # as uptrend; same for downtrend. Previous substring match missed
    # "strong uptrend" → routed high-momentum stocks to SHORT (regression).
    _is_uptrend   = "uptrend" in trend_dir
    _is_downtrend = "downtrend" in trend_dir
    if _is_downtrend and _adx_dir_val >= 20:
        direction = "short"
    elif _is_uptrend and _adx_dir_val >= 20:
        direction = "long"
    elif trend_dir in ("sideways", "neutral", ""):
        direction = "neutral"  # no clear direction — WATCH
    elif _adx_dir_val == 0.0 and (_is_uptrend or _is_downtrend):
        # Backward-compat path: no ADX data provided, trust the trend label.
        direction = "short" if _is_downtrend else "long"
    else:
        # Weak but non-zero ADX — bias toward neutral below 15.
        if _adx_dir_val < 15:
            direction = "neutral"
        else:
            direction = "short" if _is_downtrend else "long"

    # BHE Gap 4 + 6: now that `direction` is resolved, apply pillar caps/floors
    # for long candidates. (See data prep above near pillar normalization.)
    # raw_total + normalized are RE-SUMMED below to reflect the cap/floor.
    if direction == "long":
        _bhe_changed = False
        # Gap 4 — UOA → Smart Money floor at 8/15 of pillar max
        if _bhe4_uoa:
            _sm_floor = round(_pillar_sm_max * 8.0 / 15.0)
            if sm_score_norm < _sm_floor:
                sm_score_norm = _sm_floor
                _bhe_changed = True
        # Gap 6 — weak fundamentals (NetMargin <5% AND ROE <10%) cap Catalyst at 60% of max
        if _bhe6_nm is not None and _bhe6_roe is not None and _bhe6_nm < 5.0 and _bhe6_roe < 10.0:
            _cat_cap = round(_pillar_cat_max * 0.60)
            if cat_score_norm > _cat_cap:
                cat_score_norm = _cat_cap
                _bhe_changed = True
        if _bhe_changed:
            raw_total = tech_score_norm + cat_score_norm + rs_score_norm + sm_score_norm + qg_score_norm + entry_rr_score_norm
            normalized = float(raw_total)

    # Regime name for adaptive thresholds
    regime_name = str(regime.get("regime", "neutral")).lower()
    if regime_name not in ("bull", "neutral", "bear"):
        regime_name = "neutral"

    # Trade plan — reuse preliminary plan (P6: same plan used for optionality R:R scoring)
    plan = _prelim_plan

    # Block 2 — apply SMC OB entry/stop override if OB is within 2% of current price
    try:
        _ob_entry = smc_result.get("ob_entry_zone")
        _ob_stop  = smc_result.get("ob_stop")
        if _ob_entry is not None and _ob_stop is not None and direction == "long":
            _cur_price = float(df["Close"].iloc[-1])
            _ob_mid = float(_ob_entry) if not isinstance(_ob_entry, (list, tuple)) else sum(_ob_entry) / 2
            if abs(_ob_mid - _cur_price) / _cur_price <= 0.02:
                plan["entry_low"]  = round(float(_ob_entry[0]) if isinstance(_ob_entry, (list, tuple)) else _ob_entry, 2)
                plan["entry_high"] = round(float(_ob_entry[1]) if isinstance(_ob_entry, (list, tuple)) else _ob_entry * 1.005, 2)
                plan["entry_zone"] = f"${plan['entry_low']} - ${plan['entry_high']} (SMC OB)"
                plan["stop"]       = round(float(_ob_stop), 2)
                plan["setup_type"] = plan["setup_type"] + " + SMC OB"
                _risk = _cur_price - plan["stop"]
                if _risk > 0:
                    plan["risk_per_share"] = round(_risk, 2)
                    plan["target1"]  = round(_cur_price + _risk * 3.0, 2)
                    plan["target2"]  = round(_cur_price + _risk * 5.0, 2)
                    # Bug fix 2026-05-04: was (_cur_price - entry_low)/risk which is
                    # the entry-zone progression, NOT the trade's reward-to-risk ratio.
                    # Correct: (target1 - entry_mid)/risk_per_share.
                    _entry_mid = (plan.get("entry_low", _cur_price) + plan.get("entry_high", _cur_price)) / 2
                    plan["rr_ratio"] = round((plan["target1"] - _entry_mid) / _risk, 1)
    except Exception:
        pass

    # Conviction-based position sizing (applied to plan after normalization)
    _conv_tiers = config.get("portfolio", {}).get("conviction_tiers", [])
    _alloc = config.get("portfolio", {}).get("min_allocation_pct", 5.0)
    for _tier in sorted(_conv_tiers, key=lambda x: x.get("min_score", 0), reverse=True):
        if normalized >= _tier.get("min_score", 999):
            _alloc = _tier.get("allocation_pct", _alloc)
            break

    # Beta-adjusted position sizing: reduce allocation for high-volatility stocks
    # so that dollar risk is consistent across positions.
    # Target: same $ risk per position regardless of how volatile the stock is.
    # beta 1.0 = baseline (100%), beta 2.0 = 50%, beta 0.5 = keep at 100% (don't over-size)
    _beta = info.get("beta") if info else None
    if _beta is not None:
        try:
            _beta_f = float(_beta)
            if _beta_f > 0.1:
                _beta_adj = round(min(1.0, 1.0 / _beta_f), 2)  # scale down for high-beta
                _alloc = round(_alloc * _beta_adj, 1)
                _alloc = max(config.get("portfolio", {}).get("min_allocation_pct", 5.0),
                             min(_alloc, config.get("portfolio", {}).get("max_allocation_pct", 10.0)))
                plan["beta_adj_note"] = f"β{_beta_f:.1f} → {_beta_adj:.0%} size adj"
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    plan["allocation_pct"] = _alloc

    # Distribution day partial-size scaling:
    # 5-6 distribution days → 50% size (market is under distribution but not yet gated)
    # 7+ days → pre_trade_gate already blocks; this is a safety net for edge cases
    try:
        _dist_days = int(regime.get("distribution_days", 0))
        _dist_gate = config.get("gates", {}).get("distribution_days_no_new", 7)
        if _dist_days >= _dist_gate - 1:   # 6 dist days with default gate=7
            _alloc = round(_alloc * 0.5, 1)
            _alloc = max(config.get("portfolio", {}).get("min_allocation_pct", 5.0), _alloc)
            plan["allocation_pct"] = _alloc
            plan["dist_day_note"] = f"{_dist_days} dist days → 50% position size"
    except Exception:
        pass

    # Catalyst tagging — returns (tags, catalyst_tier, catalyst_meta)
    pead_data = _post_earnings_drift(earnings, df, info)
    catalyst_tags, catalyst_tier, catalyst_meta = tag_catalysts(
        indicators=tech["indicators"],
        pead_data=pead_data,
        options_data=options_data or {},
        vcp=bool(tech["indicators"].get("vcp", False)),
        squeeze=bool(tech["indicators"].get("squeeze_on", False)),
        options_intelligence=_oi,
        news_sentiment_score=_poly_news_score,
    )

    # Entry quality classification (ATR-relative)
    entry_quality = classify_entry_quality(price, tech["indicators"], sr)

    # Decision state, market phase, expected pullback (Vinod Review)
    decision_state = classify_decision_state(price, plan, tech["indicators"])
    market_phase   = classify_market_phase(tech["indicators"])
    # expected_pullback already in plan from compute_trade_plan

    # Zone quality rating (Vinod Review Item 2)
    zone_quality = compute_zone_quality(plan, tech["indicators"])

    # Reaction checklist (Vinod Review Item 6)
    reaction_checklist = compute_reaction_checklist(tech["indicators"])

    # Setup quality (Fix #1: deterministic rule groups)
    setup_quality = classify_setup_quality(tech["indicators"], plan)

    # Audit item #10: entry_quality-aware plan refinement
    # Adapts stop / target / hold for FRESH / PULLBACK / VALID
    # (EXTENDED / MISSED still demote to WATCH in decision logic)
    plan = _adjust_plan_by_entry_quality(plan, entry_quality, tech["indicators"], sr)

    # No Edge Zone detection (Vinod Review Item 7)
    _zone_high = plan.get("primary_zone_high") or plan.get("entry_high", price)
    _resistance = sr.get("resistance") or (price * 1.10)
    no_edge_zone = bool(price > _zone_high * 1.01 and _resistance and price < _resistance * 0.97)
    decision_state["no_edge_zone"] = no_edge_zone

    # Vinod fix #3: Divergence-phase downgrade — bearish RSI divergence + RVOL<1.0 → slowdown
    # Suppress breakout entries when momentum is rolling over with weak participation
    _rsi_div = tech["indicators"].get("rsi_divergence", 0)
    _rvol_now = tech["indicators"].get("rvol", 1.0) or 1.0
    if _rsi_div is not None and _rsi_div < 0 and _rvol_now < 1.0:
        decision_state["momentum_slowdown"] = True
        decision_state["slowdown_note"] = "Bearish RSI divergence + RVOL <1.0 → suppress breakout entries, wait for reset"
        # Phase override: if currently in a bullish-extension state, demote to consolidation
        if decision_state.get("state") in ("EXTENDED", "APPROACHING", "AT_SHALLOW_ZONE"):
            market_phase = dict(market_phase) if isinstance(market_phase, dict) else {"phase": market_phase}
            market_phase["phase"] = "CONSOLIDATION_OR_PULLBACK"
            market_phase["note"] = "Divergence + low RVOL: price drifting, not trending"
    else:
        decision_state["momentum_slowdown"] = False

    # Vinod fix #4: Position sizing scaled by zone depth
    # AT_SHALLOW → 50% (only valid in strong momentum anyway); AT_ZONE → 100%; AT_DEEP → 100% with tighter stop
    _state = decision_state.get("state", "")
    _size_mult = 1.0
    if _state == "AT_SHALLOW_ZONE":
        _size_mult = 0.50
    elif _state == "AT_DEEP_ZONE":
        _size_mult = 1.00  # full size, but managed by tighter stop elsewhere
    elif _state in ("EXTENDED", "MISSED", "POST_BREAKOUT_DRIFT", "APPROACHING",
                    "NO_EDGE", "LOST_STRUCTURE", "INSIDE_CLOUD_UNCERTAINTY"):
        _size_mult = 0.0  # no trade
    decision_state["size_mult_by_zone"] = _size_mult
    if _size_mult < 1.0 and "allocation_pct" in plan:
        try:
            _min_alloc = config.get("portfolio", {}).get("min_allocation_pct", 2.0)
            plan["allocation_pct"] = max(_min_alloc, round(plan["allocation_pct"] * _size_mult, 1)) if _size_mult > 0 else 0.0
            plan["zone_size_note"] = f"Size × {_size_mult:.2f} due to entry state {_state}"
        except Exception:
            pass

    # Ichimoku cloud zone (Vinod Review Item 8)
    _ichi_top = tech["indicators"].get("ichimoku_cloud_top") or tech["indicators"].get("senkou_span_a")
    _ichi_bot = tech["indicators"].get("ichimoku_cloud_bottom") or tech["indicators"].get("senkou_span_b")
    if _ichi_top and _ichi_bot:
        ichimoku_zone_top = max(float(_ichi_top), float(_ichi_bot))
        ichimoku_zone_bottom = min(float(_ichi_top), float(_ichi_bot))
        if ichimoku_zone_bottom <= price <= ichimoku_zone_top:
            decision_state["in_cloud"] = True
        else:
            decision_state["in_cloud"] = False
    else:
        ichimoku_zone_top = None
        ichimoku_zone_bottom = None
        decision_state["in_cloud"] = False
    plan["ichimoku_zone_top"] = ichimoku_zone_top
    plan["ichimoku_zone_bottom"] = ichimoku_zone_bottom

    # Entry timing (Vinod Review Item 9)
    _entry_timing_map = {
        "FRESH": "Value",
        "PULLBACK": "Value",
        "VALID": "Early",
        "EXTENDED": "Late",
        "MISSED": "Late",
    }
    entry_timing = _entry_timing_map.get(entry_quality, "Unknown")

    # Entry subtype (granular entry label)
    entry_subtype = classify_entry_subtype(price, tech["indicators"], sr,
                                           setup_type=plan.get("setup_type", ""))

    # Setup family + hold period guide
    setup_family, hold_period_guide = classify_setup_family(
        setup_type=plan.get("setup_type", ""),
        catalyst_tags=catalyst_tags,
        indicators=tech["indicators"],
    )

    # Regime4 from regime dict (may not be present in older runs)
    regime4 = str(regime.get("regime4", regime_name)).lower()

    # Conviction tier assignment (includes win-rate sizing feedback for tradeable tiers)
    conviction = assign_conviction_tier(
        score=normalized,
        rr_ratio=plan["rr_ratio"],
        rs_rank=int(tech["indicators"].get("rs_rank", 50)),
        weekly_bull=bool(tech["indicators"].get("weekly_ema_bullish", False)),
        catalysts=catalyst_tags,
        entry_quality=entry_quality,
        setup_type=plan.get("setup_type", ""),
        regime_name=regime_name,
        regime4=regime4,
        catalyst_tier=catalyst_tier,
    )

    # Override plan allocation from conviction tier sizing
    if conviction["tier"] > 0:
        base_alloc = config.get("portfolio", {}).get("min_allocation_pct", 5.0)
        max_alloc  = config.get("portfolio", {}).get("max_allocation_pct", 10.0)
        plan["allocation_pct"] = round(
            base_alloc + (max_alloc - base_alloc) * conviction["size_mult"], 1
        )

    # Phase 8: Risk-first position sizing (Fix #3/#5: live tracker stats + risk-first model)
    _vix_early = float((regime.get("vix") or {}).get("vix_current") or 20.0)
    kelly_size: dict = {}

    # ── V-4 wire-up (2026-05-04): inject per-ticker earnings_days + CVaR-975 into config ──
    # This makes earnings_mult and var_floor_mult inside kelly_position_size actually fire.
    try:
        _portfolio_runtime = config.setdefault("portfolio", {})
        _portfolio_runtime["_runtime_earn_days_for_ticker"] = (
            earnings.get("days_to_earnings") if isinstance(earnings, dict) else None
        )
        # Compute per-ticker CVaR-97.5 inline from df closes (10-day horizon)
        try:
            import forward_dist as _fd
            if df is not None and len(df) >= 50:
                _closes = df["close"].astype(float).tolist() if "close" in df else df["Close"].astype(float).tolist()
                _fd_out = _fd.forward_distribution_metrics(_closes, horizon_days=10)
                _portfolio_runtime["_runtime_cvar_975_pct"] = _fd_out.get("cvar_975_pct")
            else:
                _portfolio_runtime["_runtime_cvar_975_pct"] = None
        except Exception:
            _portfolio_runtime["_runtime_cvar_975_pct"] = None
    except Exception:
        pass

    try:
        from tracker import compute_stats as _compute_stats
        _perf_stats = _compute_stats(min_trades=5)
        # Use live stats even if insufficient — the function handles defaults gracefully
        kelly_size = kelly_position_size(
            stats=_perf_stats,
            regime_name=regime4,
            vix=_vix_early,
            conviction_tier=conviction.get("tier", 3),
            portfolio_size=5_000.0,   # $5K account (configurable)
            risk_per_share=float(plan.get("risk_per_share", price * 0.02) or price * 0.02),
            price=price,
            config=config,
            adv_20d=float(avg_vol * price) if avg_vol and price else 0.0,
        )
    except Exception:
        pass

    # ── V-4 wire-up: clear per-ticker runtime fields so they don't leak to next ticker ──
    try:
        _portfolio_runtime.pop("_runtime_earn_days_for_ticker", None)
        _portfolio_runtime.pop("_runtime_cvar_975_pct", None)
    except Exception:
        pass

    # Trade thesis
    trade_thesis = generate_trade_thesis(
        ticker, plan, tech["indicators"], catalyst_tags, conviction, entry_quality
    )

    # Bear setup scoring — always computed so we can detect weak longs and confirm shorts
    bear_setup = score_bear_setup(df, tech["indicators"])

    # Zacks Sell List: boost bear score and lower flip threshold
    if zacks_sell:
        bear_setup = dict(bear_setup)
        bear_setup["score"] = min(bear_setup["score"] + 3, 15)
        bear_setup["details"] = dict(bear_setup.get("details", {}))
        bear_setup["details"]["zacks_sell"] = "Zacks Sell List — bearish confirmation (+3 bear pts)"

    # If a "long" stock has a high bear score, flip to short direction
    # Zacks Sell List stocks flip at 9 instead of 12 (lower bar — already confirmed bearish)
    bear_flip_threshold = 9 if zacks_sell else 12
    if direction == "long" and bear_setup["score"] >= bear_flip_threshold:
        direction = "short"
        plan = compute_trade_plan(ticker, df, sr, tech["indicators"], direction,
                                  beta=info.get("beta") if info else None,
                                  config=_plan_cfg)

    # Checklist 7.3 (2026-04-15 hardening): setup weight multiplier is now
    # SIZING-ONLY — does NOT affect score/threshold. The multiplier is still
    # captured for attribution and surfaced on result['sizing_multiplier']
    # for the sizing path (compute_position_size) to consume.
    #
    # Setup weight multiplier is sizing-only after 2026-04-15 hardening — does
    # NOT affect score/threshold.
    #
    # Historical context (pre-hardening): the multiplier inflated/deflated
    # normalized score (1.2x hot, 0.8x cold). That conflated two concerns:
    # edge estimation (score) and position sizing. Now score stays pure;
    # sizing consumes the multiplier via `result['sizing_multiplier']`.
    try:
        from tracker import get_setup_weight_multiplier as _gwm_capture
        _wr_mult_used = float(_gwm_capture(plan.get("setup_type", "unknown") or "unknown",
                                           regime_name or "unknown"))
    except Exception:
        _wr_mult_used = 1.0
    # NOTE: apply_setup_wr_multiplier() is still called by the backtest path
    # (backtest._score_as_of) — that call site is preserved for backtest parity
    # against historical data. The live scoring path no longer mutates the
    # score; multiplier flows to sizing via `sizing_multiplier` on the result.

    # Flaw #7/#8 fix: apply unified ±5 bonus cap (ALL sources incl. Elliott
    # Wave) AFTER the WR multiplier, then perform the single final 0-100
    # clamp. This replaces the previous per-group bonus adds that each
    # clamped independently (wasting multiplier headroom and letting EW
    # bypass the cap).
    _total_bonus = sum(_bonuses.values()) if _bonuses else 0.0
    _total_bonus = max(-5.0, min(5.0, _total_bonus))
    if _bonuses:
        tech["details"]["bonus_breakdown"] = (
            ", ".join(f"{k}:{v:+g}" for k, v in _bonuses.items())
            + f" (sum={sum(_bonuses.values()):+g}, capped={_total_bonus:+g})"
        )
    normalized = round(float(max(0.0, min(100.0, normalized + _total_bonus))), 1)

    # Phase 1: Apply earnings risk penalty (Change 14)
    # Subtract points if earnings within 5-day hold period (binary event risk)
    earnings_penalty = penalize_earnings_risk(ticker, earnings, hold_days=5)
    if earnings_penalty != 0:
        normalized = max(0, normalized + earnings_penalty)
        earnings_date_str = ""
        if earnings and "date" in earnings:
            earnings_date_str = f" ({earnings['date']})"
        decision_note = f" [Earnings risk {earnings_penalty}pts{earnings_date_str}]"
    else:
        decision_note = ""

    # Decision
    _vix_current  = float((regime.get("vix") or {}).get("vix_current") or 20.0)
    _weekly_bull  = bool(tech["indicators"].get("weekly_ema_bullish", False))
    _adx_val      = float(tech["indicators"].get("adx", 20.0) or 20.0)
    # AI-44: compute seasonality adjustment (calendar-based buy_min nudge)
    try:
        from seasonality import seasonality_adjustment
        _seasonal_adj = seasonality_adjustment()
    except Exception:
        _seasonal_adj = None
    # AI-24: if scanning pre-open, use real pre-market move instead of yesterday's bar
    _todays_gap_pct_val = 0.0
    try:
        from datetime import datetime as _dt
        try:
            import pytz as _pytz
            et = _pytz.timezone("America/New_York")
            now_et = _dt.now(et)
            is_premarket = (4 <= now_et.hour < 9) or (now_et.hour == 9 and now_et.minute < 30)
        except ImportError:
            is_premarket = False
        if is_premarket:
            try:
                from data_fetcher import get_premarket_volume
                pm = get_premarket_volume(ticker)
                pm_chg = pm.get("price_chg_pct", 0.0) if pm else 0.0
                if pm_chg:
                    _todays_gap_pct_val = float(pm_chg)
            except Exception:
                pass
        if _todays_gap_pct_val == 0.0 and len(df) >= 2 and float(df["Close"].iloc[-2]) > 0:
            _todays_gap_pct_val = float((df["Open"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100)
    except Exception:
        _todays_gap_pct_val = 0.0

    # 2026-05-08 — per-setup score multiplier (config-driven). Demotions
    # (mult < 1.0) require statistical backing; promotions (mult > 1.0) need
    # a documented n. The 2026-05-08 audit found bare-config multipliers were
    # acting as back-door kills (4 setups at 0.0 with no Wilson backing).
    #
    # Config schema:
    #   "setup_score_multiplier": {
    #     "_validations": {  # required for any demotion to apply
    #       "VCP Breakout": {"n": 30, "wr_lb": 0.25, "source": "wf_2026Q1"}
    #     },
    #     "Trend Continuation": 1.08
    #   }
    try:
        _setup_mults = (config or {}).get("setup_score_multiplier") or {}
        _validations = _setup_mults.get("_validations") or {}
        _setup_for_mult = (plan.get("setup_type") or setup_family or "").strip()
        _setup_mult = float(_setup_mults.get(_setup_for_mult, 1.0))
        # Demotion gate: require validation entry with n>=30 AND wr_lb<0.30
        if _setup_mult < 1.0:
            _v = _validations.get(_setup_for_mult) or {}
            _vn = int(_v.get("n") or 0)
            _vlb = float(_v.get("wr_lb") or 1.0)
            if _vn < 30 or _vlb >= 0.30:
                _setup_mult = 1.0  # silently revert to no-op (audit trail in config)

        # Variant F (2026-05-10) — regime-conditional override.
        # Agent-4 finding from 250d backtest: TC in bull regime carries 79.5%
        # of all losses (n=85, WR 28.2%, PF 0.55); same setup is profitable
        # in neutral (PF 1.75) and bear (PF 2.68). Global multiplier averages
        # them out. Regime-specific override gives the right size in each.
        #
        # Config schema:
        #   "setup_score_multiplier_by_regime": {
        #     "_validations": {                             # required for any demotion
        #       "Trend Continuation": {
        #         "bull":    {"n": 85, "wr_lb": 0.20, "source": "bt_250d_2026-05-10"}
        #       }
        #     },
        #     "Trend Continuation": {"bull": 0.0, "neutral": 1.0, "bear": 1.5}
        #   }
        #
        # When this block contains an entry, it OVERRIDES the global mult.
        # Same demotion gate applies (n>=30, wr_lb<0.30).
        _by_regime = (config or {}).get("setup_score_multiplier_by_regime") or {}
        if _by_regime:
            _br_validations = _by_regime.get("_validations") or {}
            _setup_overrides = _by_regime.get(_setup_for_mult) or {}
            _regime_key = (regime_name or "neutral").lower()
            if _regime_key in _setup_overrides:
                _regime_mult = float(_setup_overrides[_regime_key])
                # Apply demotion gate to regime-specific too
                if _regime_mult < 1.0:
                    _vbr = (_br_validations.get(_setup_for_mult) or {}).get(_regime_key) or {}
                    _vbn = int(_vbr.get("n") or 0)
                    _vblb = float(_vbr.get("wr_lb") or 1.0)
                    if _vbn < 30 or _vblb >= 0.30:
                        _regime_mult = 1.0  # gate not cleared
                # The regime-specific overrides the global
                _setup_mult = _regime_mult

        if _setup_mult != 1.0 and _setup_mult > 0:
            normalized = float(normalized) * _setup_mult
    except Exception:
        pass

    # Ranking flaw #13: collapse 0.1pp float noise. Keep the full-precision value
    # in `normalized_raw` for debugging; use integer 0-100 for ranking, thresholds,
    # and the public `score` field. Two picks at 68.9 and 69.1 now both display 69.
    normalized_raw = float(max(0.0, min(100.0, float(normalized))))
    normalized = int(round(normalized_raw))

    # BHE Gap 1: heuristic P(profit) computed before make_decision so it can
    # be passed in as a 5th gate input. Always computed (cheap, no I/O); only
    # gated when config.gates.require_mc_p_profit is True.
    _mc_p_profit_val = compute_mc_p_profit(
        score=normalized,
        rr_ratio=plan.get("rr_ratio", 0) or 0,
        entry_quality=entry_quality,
        setup_family=plan.get("setup_type", ""),
        atr_pct=float(tech["indicators"].get("atr_pct", 2.0) or 2.0),
        rs_rank=int(tech["indicators"].get("rs_rank", 50)),
        weekly_bull=_weekly_bull,
    )

    decision = make_decision(
        normalized, plan["rr_ratio"], config,
        weak_regime=gate.get("weak_regime", False),
        direction=direction,
        bear_score=bear_setup["score"],
        rs_rank=int(tech["indicators"].get("rs_rank", 50)),
        vix=_vix_current,
        sector_outperforming=bool(tech["indicators"].get("sector_outperforming", False)),
        sector_etf=str(tech["indicators"].get("sector_etf", "")),
        has_catalyst=len(opt.get("catalysts", [])) > 0 or len(catalyst_tags) > 1 or catalyst_tags[0] not in ("CONTINUATION", "MOMENTUM"),
        rsi=float(tech["indicators"].get("rsi", 50.0) or 50.0),
        weekly_bull=_weekly_bull,
        adx=_adx_val,
        regime_name=regime_name,
        breadth=breadth,
        entry_quality=entry_quality,
        regime4=regime4,
        setup_type=plan.get("setup_type", ""),
        short_float=float(info.get("shortPercentOfFloat", 0.0) or 0.0) * 100.0 if info and isinstance(info.get("shortPercentOfFloat"), (int, float)) else float(tech["indicators"].get("short_float_pct", 0.0) or 0.0),
        # AI-9: DTC from short_interest dict (populated by data_fetcher fetch_short_interest)
        days_to_cover=float((info.get("short_interest") or {}).get("days_to_cover", 0.0) or 0.0) if info else 0.0,
        days_to_earnings=(int((earnings or {}).get("days_to_earnings")) if (earnings and (earnings or {}).get("days_to_earnings") is not None) else None),
        sector_underperforming=bool(tech["indicators"].get("sector_underperforming", not tech["indicators"].get("sector_outperforming", False))),
        stock_vs_spy_20d=float(tech["indicators"].get("stock_vs_spy_20d", 0.0) or 0.0),
        # Fix #30 / AI-24: pre-market gap enforcement when scanning before open
        todays_gap_pct=_todays_gap_pct_val,
        # Bug #3: pass squeeze state so shorts get blocked
        squeeze_on=bool(tech["indicators"].get("squeeze_on", False)),
        # AI-8: pass RVOL for breakout volume gate
        rvol=float(tech["indicators"].get("rvol", 1.0) or 1.0),
        # AI-43: market-cycle-aware score bar adjustment
        market_cycle=regime.get("market_cycle", ""),
        # AI-44: seasonality layer — calendar bias nudge on buy_min
        seasonal_adj=_seasonal_adj,
        # Hysteresis (3.4): pass ticker for recent-verdict lookup
        ticker=ticker,
        catalyst_tier=catalyst_tier,
        mc_p_profit=_mc_p_profit_val,
    )

    # If gate failed, override to AVOID
    if not gate["passed"]:
        decision = {
            "verdict": "AVOID",
            "emoji": "no_entry",
            "color": "#dc2626",
            "bear_type": "",
            "reason": f"Gate failed: {'; '.join(gate['reasons'])}"
        }

    # Block 1 — MTF conflict: cap BUY → WATCH when daily bullish but weekly bearish
    if mtf_conflict and decision.get("verdict") == "BUY":
        decision = {
            "verdict": "WATCH",
            "emoji": "eye",
            "color": "#d97706",
            "bear_type": decision.get("bear_type", ""),
            "reason": decision.get("reason", "") + f" | MTF conflict: {mtf_label}",
        }

    # Block 2 — 4H timeframe analysis: momentum confirmation for entry timing
    _4h_signal = "neutral"
    _4h_details = {}
    if df_4h is not None and len(df_4h) >= 21:
        try:
            _c4 = df_4h["Close"].squeeze() if isinstance(df_4h["Close"], pd.DataFrame) else df_4h["Close"]
            _4h_ema8 = float(_c4.ewm(span=8, adjust=False).mean().iloc[-1])
            _4h_ema21 = float(_c4.ewm(span=21, adjust=False).mean().iloc[-1])
            _4h_price = float(_c4.iloc[-1])
            _4h_rsi = None
            if len(_c4) >= 15:
                _delta4 = _c4.diff()
                _gain4 = _delta4.where(_delta4 > 0, 0).rolling(14).mean().iloc[-1]
                _loss4 = (-_delta4.where(_delta4 < 0, 0)).rolling(14).mean().iloc[-1]
                _4h_rsi = round(100 - 100 / (1 + _gain4 / _loss4), 1) if _loss4 > 0 else 100.0
            _4h_macd_line = float(_c4.ewm(span=12, adjust=False).mean().iloc[-1] - _c4.ewm(span=26, adjust=False).mean().iloc[-1])
            _4h_macd_signal = float((_c4.ewm(span=12, adjust=False).mean() - _c4.ewm(span=26, adjust=False).mean()).ewm(span=9, adjust=False).mean().iloc[-1])
            _4h_macd_bull = _4h_macd_line > _4h_macd_signal

            _4h_bullish = _4h_price > _4h_ema8 > _4h_ema21 and _4h_macd_bull
            _4h_bearish = _4h_price < _4h_ema8 < _4h_ema21 and not _4h_macd_bull
            _4h_signal = "bullish" if _4h_bullish else "bearish" if _4h_bearish else "neutral"

            _4h_details = {
                "signal": _4h_signal,
                "ema8": round(_4h_ema8, 2),
                "ema21": round(_4h_ema21, 2),
                "rsi": _4h_rsi,
                "macd_bullish": _4h_macd_bull,
                "price_above_ema8": _4h_price > _4h_ema8,
            }

            # 4H bearish on a BUY → demote to WATCH (bad entry timing)
            if _4h_signal == "bearish" and decision.get("verdict") == "BUY":
                decision = {
                    "verdict": "WATCH",
                    "emoji": "eye",
                    "color": "#d97706",
                    "bear_type": decision.get("bear_type", ""),
                    "reason": decision.get("reason", "") + " | 4H bearish — wait for momentum",
                }
            # 4H bullish on a WATCH with high score → add note
            elif _4h_signal == "bullish" and decision.get("verdict") == "WATCH":
                decision["reason"] = decision.get("reason", "") + " | 4H bullish — approaching entry"
        except Exception:
            pass

    # OHLCV for Lightweight Charts (last 90 bars, Unix timestamps)
    try:
        n = min(90, len(df))
        _df = df.iloc[-n:]
        _close = _df["Close"].squeeze()
        _open  = _df["Open"].squeeze()
        _high  = _df["High"].squeeze()
        _low   = _df["Low"].squeeze()
        _vol   = _df["Volume"].squeeze()
        ohlcv = [
            {
                "time":   int(pd.Timestamp(idx).timestamp()),
                "open":   round(float(o), 2),
                "high":   round(float(h), 2),
                "low":    round(float(l), 2),
                "close":  round(float(c), 2),
                "volume": int(v),
            }
            for idx, o, h, l, c, v in zip(
                _df.index, _open, _high, _low, _close, _vol
            )
        ]
    except Exception:
        ohlcv = []

    # Earnings proximity warning
    _earnings_warning = None
    try:
        _earn_date = earnings.get("earnings_date") or earnings.get("date")
        if _earn_date:
            from datetime import datetime as _dt_ew, timedelta as _td_ew
            if isinstance(_earn_date, str):
                _earn_dt = _dt_ew.strptime(_earn_date[:10], "%Y-%m-%d")
            else:
                _earn_dt = _earn_date
            _days_to_earn = (_earn_dt - _dt_ew.now()).days
            if 0 <= _days_to_earn <= 7:
                _earnings_warning = {
                    "days": _days_to_earn,
                    "date": _earn_dt.strftime("%Y-%m-%d"),
                    "message": f"Earnings in {_days_to_earn} day{'s' if _days_to_earn != 1 else ''} ({_earn_dt.strftime('%b %d')})"
                }
    except Exception:
        pass

    # ── Tier 1 strategy signals (additive scoring layer) ──
    # 6 detectors: insider cluster, NR7/inside-day, vol dry-up, OBV divergence,
    # mean-reversion, beat-and-raise. Each opt-in via config.
    # Points either boost the canonical score (if apply_to_score=true) or are
    # informational-only (default — for ranking tie-breakers and dashboard display).
    _tier1_result = {"total_points": 0, "signals": {}, "narratives": [], "active_count": 0}
    try:
        from tier1_signals import compute_all_tier1_signals as _t1
        _t1_cfg = (config or {}).get("tier1_signals", {})
        if _t1_cfg.get("_enabled", True):
            _ema21_val = tech["indicators"].get("ema21")
            _ema50_val = tech["indicators"].get("ema50")
            # Use the actual insider param (already passed to analyze_ticker), not info.get
            _t1_insider      = insider if isinstance(insider, dict) else None
            _t1_insider_full = (info.get("insider_data") if isinstance(info, dict) else None)
            if not isinstance(_t1_insider_full, dict): _t1_insider_full = None
            # earnings is a separate kwarg to analyze_ticker — use directly when dict
            _t1_earnings = earnings if isinstance(earnings, dict) else None
            # Estimate revisions for Beat-and-Raise guidance proxy (Zacks per-ticker enrichment)
            _t1_revisions = (info.get("zacks_estimate_revisions") if isinstance(info, dict) else None) \
                            or (info.get("zacks_revision_counts") if isinstance(info, dict) else None)
            if not isinstance(_t1_revisions, dict): _t1_revisions = None
            _tier1_result = _t1(
                df=df,
                insider=_t1_insider,
                insider_full=_t1_insider_full,
                rsi=tech["indicators"].get("rsi"),
                above_200sma=bool(tech["indicators"].get("above_200sma")),
                fund_score=fund.get("score") if isinstance(fund, dict) else None,
                atr_pct=tech["indicators"].get("atr_pct"),
                ema21=_ema21_val,
                ema50=_ema50_val,
                earnings_data=_t1_earnings,
                estimate_revisions=_t1_revisions,
                config=config,
            )
            # Apply points to canonical score only if explicitly opted-in
            if _t1_cfg.get("apply_to_score", False) and _tier1_result["total_points"] != 0:
                _t1_pts = _tier1_result["total_points"]
                # Cap impact to ±8 points to prevent runaway
                _t1_pts = max(-8, min(8, _t1_pts))
                normalized = max(0, min(100, normalized + _t1_pts))
                if "scoring_breakdown" in dir():
                    scoring_breakdown["tier1_points"] = float(_t1_pts)
                    scoring_breakdown["final_score"] = float(normalized)
    except Exception as _t1_err:
        # Fail-safe: tier1 errors never crash scoring
        try:
            log.debug(f"tier1_signals failed for {ticker}: {_t1_err}")
        except Exception:
            pass

    # Star rating — compute once, store in result for HTML rendering
    _star_result_partial = {
        "trade_plan": plan,
        "rs_rank": tech["indicators"].get("rs_rank", 50),
        "catalyst_tier": catalyst_tier,
        "decision_state": decision_state,
    }
    star_rating = compute_star_rating(_star_result_partial)

    # ── Tail-Loss Filter (P0-B follow-up · 2026-05-03) ──────────────────────
    # Backtest of 210 closed trades showed 12 tail losses (≤-2R). Filtering by
    # score≥60 AND stars≥4 eliminates 9 of 12 → Basel GREEN, WR 84.7%, avgR +2.20.
    # Roll back: set tail_loss_filter._enabled = false in config.json.
    _tlf = (config.get("tail_loss_filter") or {})
    if _tlf.get("_enabled", False) and conviction.get("tier", -1) > 0:
        _min_score = _tlf.get("min_score_for_buy", 60)
        _min_stars = _tlf.get("min_stars_for_buy", 4)
        if normalized < _min_score or star_rating < _min_stars:
            _orig_label = conviction.get("label", "")
            conviction = {
                "tier": 0, "label": "WATCH", "size_mult": 0.0,
                "description": f"Demoted by tail-loss filter (score={normalized:.0f}<{_min_score} or stars={star_rating}<{_min_stars}); was {_orig_label}",
                "tail_filter_demoted": True,
                "demoted_from_tier": _orig_label,
            }

    # Audit ranking flaw #16/#17: per-pillar breakdown for regression + correlation
    scoring_breakdown = {
        "tech_score":   float(tech_score_norm),
        "cat_score":    float(cat_score_norm),
        "rs_score":     float(rs_score_norm),
        "sm_score":     float(sm_score_norm),
        "qg_score":     float(qg_score_norm),
        "entry_rr_score": float(entry_rr_score_norm),
        "raw_total":    float(raw_total),          # pre-multiplier, pre-bonus
        "wr_multiplier": float(_wr_mult_used),     # sizing-only after 2026-04-15 (checklist 7.3)
        "bonus_total":  float(_total_bonus),       # post-cap applied (±5)
        "final_score":  float(normalized),         # post-clamp 0-100
    }

    # Checklist 7.3: surface sizing multiplier for downstream position-sizer.
    # This is the ONLY channel by which the setup-weight multiplier influences
    # trading decisions now — it no longer touches the score.
    _sizing_multiplier = float(_wr_mult_used)

    result = {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "price": price,
        "sizing_multiplier": _sizing_multiplier,  # checklist 7.3 — sizing-only

        "star_rating": star_rating,
        "sector": info.get("sector", "Unknown"),
        "congressional": congressional,
        "reddit_wsb":    reddit_wsb,
        "industry": info.get("industry", "Unknown"),
        "catalyst_tags":      catalyst_tags,
        "catalyst_tier":      catalyst_tier,
        "catalyst_meta":      catalyst_meta,
        "entry_quality":      entry_quality,
        "entry_subtype":      entry_subtype,
        "decision_state":     decision_state,
        "market_phase":       market_phase,
        "zone_quality":       zone_quality,
        "setup_quality":      setup_quality,
        "reaction_checklist": reaction_checklist,
        "entry_timing":       entry_timing,
        "setup_family":       setup_family,
        "hold_period_guide":  hold_period_guide,
        "regime4":            regime4,
        "conviction":         conviction,
        "trade_thesis":   trade_thesis,
        "volume": volume,
        "avg_volume": avg_vol,
        "rvol": tech["indicators"].get("rvol", 1.0),
        "beta": info.get("beta") if info else None,
        "price_tier": plan.get("price_tier", ""),
        "gate": gate,
        "fundamentals": fund,
        # Options intelligence — populated by Step 5e from Schwab chains (not here)
        "options_intel": None,
        "volume_profile": _volume_profile_full(df, lookback=60, bins=30),
        # Schwab-powered KPIs surfaced on tile + screener (2026-04-15)
        "kpi": {
            "quote_age_s":            info.get("kpi_quote_age_s"),
            "spread_bp":              info.get("kpi_spread_bp"),
            "post_market_pct":        info.get("kpi_post_market_pct"),
            "dist_from_52wk_high_pct": info.get("kpi_dist_from_52wk_high_pct"),
            "dist_from_52wk_low_pct":  info.get("kpi_dist_from_52wk_low_pct"),
            "days_since_earnings":    info.get("kpi_days_since_earnings"),
            "leverage_factor":        info.get("kpi_leverage_factor"),
            "source":                 info.get("_cache_source"),
        },
        "optionality": opt,
        "technicals": tech,
        "sentiment": sent,
        "raw_score": raw_total,
        "score": normalized,                 # integer 0-100 (ranking flaw #13)
        "score_raw": round(normalized_raw, 2),  # pre-rounding float for debugging
        "tier1_signals": _tier1_result,      # 6 strategy enhancement detectors
        "bear_type": decision.get("bear_type", ""),
        "trade_plan": plan,
        "decision": decision,
        "direction": direction,
        # State-based classification patch (2026-04-15) — forward-looking
        # phase/location/edge/action augmenting the legacy verdict.
        # Failure here is non-fatal: state defaults to None.
        "state": _compute_state(tech, plan, (plan or {}).get("setup_type", ""), normalized, direction, config, current_price=price),
        "earnings": earnings,
        "news_data": news,
        "insider_data": insider,
        "squeeze": tech["indicators"].get("squeeze_on", False),
        "rsi": tech["indicators"].get("rsi", 50),
        "atr_pct": tech["indicators"].get("atr_pct", 0),
        "rs_rank": tech["indicators"].get("rs_rank", 50),
        "macd_signal": tech["indicators"].get("macd_signal", "NO DATA"),
        "ema_signal": tech["indicators"].get("ema_signal", "NO DATA"),
        "fractal_signal": tech["indicators"].get("fractal_signal", "NO DATA"),
        "fractal_high": tech["indicators"].get("fractal_high"),
        "fractal_low": tech["indicators"].get("fractal_low"),
        "tv_rating":    tv_rating or {},
        "elliott_wave": ew,
        "methodology_checklist": methodology,
        "theory_confluence": theory_confluence_data,
        "options_kpis": options_kpis or {},
        "options_data": options_data or {},
        "bear_setup":   bear_setup,
        "kelly_size":   kelly_size,
        "vwap":         vwap_data,
        "patterns":     pattern_data,
        "extra_fund":   _ef,
        "ohlcv":        ohlcv,
        "zacks_sell":   zacks_sell,
        "mtf_conflict": mtf_conflict,
        "mtf_label":    mtf_label,
        "tf_4h":        _4h_details,
        "smc":          smc_result,
        "uoa":              uoa or {},
        "finnhub":          finnhub or {},
        "fmp":              fmp or {},
        "sec_filings":      sec or {},
        "premarket":        premarket or {},
        "inst_trend":       inst_trend or {},
        "gamma":            gamma or {},
        # 2026-05-08 — Finviz Elite-derived squeeze candidate flag.
        # Levels: high (SF≥15% + IO≥80% + RV≥2×), moderate (SF≥10% + IO≥60%),
        # low (SF≥5%), or None. Score 0-100 estimates squeeze severity.
        "squeeze_flag": {
            "level": _squeeze_flag,
            "score": _squeeze_score,
            "short_float_pct": (finviz or {}).get("short_float_pct"),
            "short_ratio":     (finviz or {}).get("short_ratio"),
            "inst_own_pct":    (finviz or {}).get("inst_own_pct"),
            "rel_volume":      (finviz or {}).get("rel_volume"),
        } if _squeeze_flag else {"level": None, "score": 0},
        "eps_trend":        eps_trend or {},
        "quote_snapshot":    quote_snapshot or {},
        "news_articles":        news_articles or [],
        "options_chain":     options_chain or {},
        "options_intelligence": _oi,
        "news_sentiment_score":  _poly_news_score,
        "earnings_warning":    _earnings_warning,
    }
    # Audit ranking flaw #16/#17: attach per-pillar breakdown for regression
    result["scoring_breakdown"] = scoring_breakdown
    # BHE Gap 1: surface MC P(profit) for UI consumption
    result["mc_p_profit"] = round(_mc_p_profit_val, 3)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Exit-state classifier (Wave 2A, checklist item 5.1)
# Appended by wave-2A agent — do not modify existing functions above.
# ═══════════════════════════════════════════════════════════════════════════
def classify_exit_state(position, current_price, indicators, regime4, config):
    """Daily exit verdict for an open position.

    position: {ticker, entry_price, stop, target1, target2, entry_date,
               setup_type, direction, rs_rank_at_entry, ...}
    indicators: {ema21_weekly, rs_rank, mae_pct, ...}
    regime4: one of risk_on_trending | risk_on_choppy | risk_off_trending | panic
    config:  full config dict (reads `exit_rules` block if present; otherwise
             uses sensible defaults).

    Returns: {action: "EXIT"|"TRIM"|"HOLD", reason: str, urgency: "HIGH"|"MEDIUM"|"LOW"}

    Priority order:
      1. EXIT if price <= stop (trail-stop hit)                         [HIGH]
      2. EXIT if thesis invalidated (regime / leadership / weekly EMA)  [HIGH]
      3. TRIM 50% if price >= target1                                   [MEDIUM]
      4. EXIT if held > N trading days AND pnl_pct < min_pnl_pct        [MEDIUM]
      5. EXIT if MAE exceeded mae_mult × initial_risk                   [HIGH]
      6. HOLD otherwise                                                 [LOW]
    """
    from datetime import datetime as _dt, date as _date

    # ── Defaults (if config.exit_rules not present) ────────────────────────
    _defaults = {
        "time_stop_days":      15,
        "time_stop_min_pnl":   3.0,   # pct
        "rs_leadership_min":   40,
        "mae_multiplier":      1.5,
        "bearish_regimes":     ["risk_off_trending", "panic"],
    }
    try:
        _rules = (config or {}).get("exit_rules", {}) or {}
    except Exception:
        _rules = {}
    time_stop_days    = int(_rules.get("time_stop_days",    _defaults["time_stop_days"]))
    time_stop_min_pnl = float(_rules.get("time_stop_min_pnl", _defaults["time_stop_min_pnl"]))
    rs_min            = float(_rules.get("rs_leadership_min", _defaults["rs_leadership_min"]))
    mae_mult          = float(_rules.get("mae_multiplier",   _defaults["mae_multiplier"]))
    bearish_regimes   = _rules.get("bearish_regimes",        _defaults["bearish_regimes"])

    # ── Coerce inputs ─────────────────────────────────────────────────────
    try:
        cur = float(current_price or 0)
    except (TypeError, ValueError):
        cur = 0.0
    pos = position or {}
    ind = indicators or {}
    try:
        entry  = float(pos.get("entry_price") or 0)
        stop   = float(pos.get("stop") or 0)
        tgt1   = float(pos.get("target1") or 0)
    except (TypeError, ValueError):
        entry = stop = tgt1 = 0.0
    direction = str(pos.get("direction", "long")).lower()

    def _verdict(action, reason, urgency="LOW"):
        return {"action": action, "reason": reason, "urgency": urgency}

    if cur <= 0 or entry <= 0:
        return _verdict("HOLD", "insufficient price data", "LOW")

    # P&L % (sign-aware)
    if direction == "short":
        pnl_pct = ((entry - cur) / entry) * 100.0 if entry else 0.0
    else:
        pnl_pct = ((cur - entry) / entry) * 100.0 if entry else 0.0

    # ── Rule 1: trail-stop hit ───────────────────────────────────────────
    if direction == "short":
        stop_hit = (stop > 0 and cur >= stop)
    else:
        stop_hit = (stop > 0 and cur <= stop)
    if stop_hit:
        return _verdict("EXIT", f"stop {stop:.2f} hit at {cur:.2f}", "HIGH")

    # ── Rule 2: thesis invalidated ───────────────────────────────────────
    if regime4 in bearish_regimes:
        return _verdict("EXIT", f"regime flipped to {regime4}", "HIGH")

    rs_cur = ind.get("rs_rank")
    try:
        if rs_cur is not None and float(rs_cur) < rs_min:
            return _verdict("EXIT",
                            f"lost leadership: rs_rank {float(rs_cur):.0f} < {rs_min:.0f}",
                            "HIGH")
    except (TypeError, ValueError):
        pass

    ema21_w = ind.get("ema21_weekly")
    try:
        if ema21_w is not None and direction == "long" and cur < float(ema21_w):
            return _verdict("EXIT",
                            f"weekly EMA21 broken: close {cur:.2f} < ema21w {float(ema21_w):.2f}",
                            "HIGH")
    except (TypeError, ValueError):
        pass

    # ── Rule 3: scale-out at target1 ─────────────────────────────────────
    if tgt1 > 0:
        if direction == "short":
            hit_t1 = cur <= tgt1
        else:
            hit_t1 = cur >= tgt1
        if hit_t1:
            return _verdict("TRIM",
                            f"target1 {tgt1:.2f} reached at {cur:.2f} — scale out 50%",
                            "MEDIUM")

    # ── Rule 4: time stop ─────────────────────────────────────────────────
    entry_date_raw = pos.get("entry_date")
    days_held = 0
    if entry_date_raw:
        try:
            if isinstance(entry_date_raw, _date) and not isinstance(entry_date_raw, _dt):
                ed = entry_date_raw
            else:
                ed = _dt.fromisoformat(str(entry_date_raw)[:10]).date()
            # Approximate trading-day count as 5/7 * calendar days
            cal_days = (_date.today() - ed).days
            days_held = max(0, int(round(cal_days * 5.0 / 7.0)))
        except Exception:
            days_held = 0
    if days_held > time_stop_days and pnl_pct < time_stop_min_pnl:
        return _verdict("EXIT",
                        f"time stop: held {days_held}d (>{time_stop_days}), "
                        f"pnl {pnl_pct:+.2f}% < {time_stop_min_pnl:.1f}%",
                        "MEDIUM")

    # ── Rule 5: MAE exceeds mae_mult × initial risk ──────────────────────
    initial_risk_pct = None
    if entry > 0 and stop > 0:
        if direction == "short":
            initial_risk_pct = ((stop - entry) / entry) * 100.0
        else:
            initial_risk_pct = ((entry - stop) / entry) * 100.0
    mae_pct = ind.get("mae_pct")
    try:
        if (initial_risk_pct is not None and initial_risk_pct > 0
                and mae_pct is not None and float(mae_pct) >= mae_mult * initial_risk_pct):
            return _verdict("EXIT",
                            f"MAE {float(mae_pct):.2f}% >= {mae_mult:g}x initial risk "
                            f"{initial_risk_pct:.2f}%",
                            "HIGH")
    except (TypeError, ValueError):
        pass

    # ── Rule 6: HOLD ──────────────────────────────────────────────────────
    return _verdict("HOLD",
                    f"no exit trigger (pnl {pnl_pct:+.2f}%, held {days_held}d, regime {regime4})",
                    "LOW")
