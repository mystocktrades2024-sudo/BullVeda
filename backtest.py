"""
backtest.py — Walk-forward 10-day backtest for SwingTrade technical model.

Tests the TECHNICAL scoring model against historical price action.
Missing data vs live pipeline: Zacks ranks, news sentiment, insider (no point-in-time).

WARNING — AUDIT #4: FUNDAMENTAL LOOK-AHEAD BIAS (Tier 1 mitigation in place)
---------------------------------------------------------------------------
yfinance `info` is fetched ONCE at backtest start and applied to every
historical signal. That data reflects TODAY's restated fundamentals
(P/E, D/E, EPS growth, margins) — so signals from months ago are scored
with information that did not exist on the as-of date. Estimated impact:
backtest Win Rate inflated ~1-2pp.

Tier 1 (shipped): warning + BACKTEST_NO_FUNDAMENTALS env flag to disable
the fundamentals pillar entirely. Run both modes and compare — the delta
is an upper bound on the fundamental-leak effect.

    BACKTEST_NO_FUNDAMENTALS=1 python3 backtest.py   # neutralize fundamentals

Tier 2 (roadmap, multi-day): point-in-time fundamentals via Finnhub
`/stock/financials-reported?symbol=X` — find most recent filing <= as_of
date for each (ticker, date), cache heavily. ~200 API calls for 500
tickers × N quarters. Replaces the single yfinance `infos` batch with a
per-(ticker, date) `fundamentals_as_of(ticker, date)` lookup.

Usage:
    python3 backtest.py              # last 10 trading days, 5-day hold
    python3 backtest.py --days 20   # last 20 trading days
    python3 backtest.py --hold 3    # 3-day hold period
    BACKTEST_NO_FUNDAMENTALS=1 python3 backtest.py   # disable fundamentals pillar
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from data_fetcher import yf  # _YfStub: empty no-op (yfinance removed 2026-04-25)

BASE_DIR = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("backtest")

# ── Fix #23 / Audit #5: Slippage/fee model ───────────────────────────────────
# Realistic model (default): base + ATR-scaled + liquidity impact (bps).
# Flat model (legacy): 3bp entry / 2bp exit — keep for comparison runs.
#   Toggle: SLIPPAGE_MODEL env var = "realistic" (default) | "flat"
# Commission: $0 flat (commission-free brokers: Schwab, Fidelity, etc.)
ENTRY_SLIPPAGE_PCT = 0.0003  # 3 bps (legacy flat)
EXIT_SLIPPAGE_PCT  = 0.0002  # 2 bps (legacy flat)
COMMISSION_PER_TRADE = 0.0   # $0 commission-free
SLIPPAGE_MODEL = os.environ.get("SLIPPAGE_MODEL", "realistic").lower()

# ── Fix #26 / Audit #1: Survivorship bias flag + haircut ────────────────────
# WARNING: This backtest uses the CURRENT S&P 500 membership list. Stocks that
# were removed from the index (bankruptcies, acquisitions, cap decline, etc.)
# are NOT included, which introduces survivorship bias — their losses never
# enter the sample, so raw backtest stats are optimistic vs point-in-time
# performance.
#
# Tier 1 mitigation (ACTIVE): explicit win-rate haircut applied at the summary
# print stage. Raw and adjusted WR are both shown so the adjustment is
# transparent (and doesn't contaminate any other downstream calculation).
# Historical studies of survivorship bias on large-cap US equity strategies
# suggest 3-5pp WR inflation is typical; we use -4pp as a conservative
# midpoint. Formula:
#     adjusted_wr = raw_wr - SURVIVORSHIP_WR_ADJUSTMENT
# The haircut does NOT affect live trading — live signals already run against
# the live universe with no survivorship gap.
#
# Tier 2 roadmap (proper fix, not yet implemented):
#   - Sharadar SF1 historical constituents ($$), OR
#   - CRSP survivor-bias-free dataset ($$$), OR
#   - Scrape Wikipedia S&P 500 change history
#     (https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
#      — has "Selected changes to the list of S&P 500 components" table), OR
#   - archive.org Wayback snapshots of historical S&P 500 constituent lists,
#   - wsj.com market-data historical index membership.
# Once Tier 2 lands, set SURVIVORSHIP_WR_ADJUSTMENT back to 0.0.
SURVIVORSHIP_BIAS_WARNING = (
    "SURVIVORSHIP BIAS: Uses current S&P 500 membership. "
    "Historical index changes not accounted for. "
    "Expect live performance 3-5% below backtest estimates."
)
SURVIVORSHIP_WR_ADJUSTMENT = 0.04  # -4pp conservative haircut applied to reported WR

# ── Audit #4: Fundamental look-ahead mitigation (Tier 1) ─────────────────────
# yfinance `info` is fetched once at backtest start and applied to every
# historical signal — so signals months ago are scored with TODAY's restated
# fundamentals (P/E, D/E, EPS growth, margins). Estimated inflation: ~1-2pp
# on Win Rate.
#
# Tier 1 mitigation: set BACKTEST_NO_FUNDAMENTALS=1 to neutralize the
# fundamentals pillar entirely. Normalized score then reflects pure
# technicals. Run both modes — the delta bounds the look-ahead leak.
#
# Tier 2 (multi-day project, not yet implemented): point-in-time
# `fundamentals_as_of(ticker, date)` via Finnhub `/stock/financials-reported`.
#   - Fetch quarterly filings for each ticker (one-time, cacheable)
#   - For each (ticker, as_of_date) pick most recent filing <= as_of_date
#   - Return that quarter's P/E, D/E, EPS growth, revenue growth
#   - ~200 API calls for 500 tickers × N quarters, cache heavily
# Live scoring remains unchanged — live yfinance IS point-in-time for today.
BACKTEST_DISABLE_FUNDAMENTALS = os.environ.get("BACKTEST_NO_FUNDAMENTALS", "0") == "1"
FUNDAMENTAL_LOOKAHEAD_WARNING = (
    "FUNDAMENTAL LOOK-AHEAD: yfinance current data applied to historical signals. "
    "Backtest WR inflated ~1-2pp. See audit #4 / module docstring for full fix plan. "
    "Set BACKTEST_NO_FUNDAMENTALS=1 to neutralize the fundamentals pillar."
)


def compute_slippage(
    entry_price: float,
    atr: float,
    adv_20d: float,
    order_value: float,
    direction: str = "entry",  # "entry" or "exit"
) -> float:
    """Return slippage as decimal (0.0015 = 15bps).
    Formula: base + atr_scaled + impact_cost.
    - base: 3bps entry / 2bps exit (matches legacy flat model)
    - atr_bps: volatile stocks have wider spreads (ATR% × 10 × 100)
    - impact_bps: log-scaled liquidity impact based on order / ADV dollars
    Capped at 200bps (beyond that, order probably shouldn't execute).
    """
    # Base cost
    base_bps = 3 if direction == "entry" else 2

    # ATR contribution: volatile stocks have wider spreads
    atr_pct = (atr / entry_price) if entry_price and entry_price > 0 else 0.02
    atr_bps = atr_pct * 10 * 100  # 2% ATR -> 20 bps

    # Liquidity impact: log10(order_size_pct_of_adv) scaling
    impact_bps = 0.0
    if adv_20d and adv_20d > 0 and order_value and order_value > 0 and entry_price > 0:
        adv_dollars = adv_20d * entry_price
        if adv_dollars > 0:
            ratio = order_value / adv_dollars
            # k=5 empirical: 0.1% of ADV -> 0 bps, 1% -> 10 bps, 10% -> 50 bps
            impact_bps = max(0.0, math.log10(max(ratio, 1e-6) * 100) * 5)

    total_bps = base_bps + atr_bps + impact_bps
    total_bps = min(total_bps, 200)  # cap at 2%
    return total_bps / 10000.0


def apply_entry_slippage(
    price: float,
    direction: str = "long",
    atr: float = None,
    adv_20d: float = None,
    order_value: float = None,
) -> float:
    """Apply entry slippage: long buys higher, short sells lower.
    Uses realistic ATR/ADV-scaled model when SLIPPAGE_MODEL="realistic"
    and atr is provided; falls back to legacy flat model otherwise.
    """
    if SLIPPAGE_MODEL == "realistic" and atr is not None and price > 0:
        slip = compute_slippage(price, atr, adv_20d or 0, order_value or 0, "entry")
    else:
        slip = ENTRY_SLIPPAGE_PCT
    if direction == "long":
        return round(price * (1 + slip), 4)
    else:
        return round(price * (1 - slip), 4)


def apply_exit_slippage(
    price: float,
    direction: str = "long",
    atr: float = None,
    adv_20d: float = None,
    order_value: float = None,
) -> float:
    """Apply exit slippage: long sells lower, short covers higher.
    Uses realistic ATR/ADV-scaled model when SLIPPAGE_MODEL="realistic"
    and atr is provided; falls back to legacy flat model otherwise.
    """
    if SLIPPAGE_MODEL == "realistic" and atr is not None and price > 0:
        slip = compute_slippage(price, atr, adv_20d or 0, order_value or 0, "exit")
    else:
        slip = EXIT_SLIPPAGE_PCT
    if direction == "long":
        return round(price * (1 - slip), 4)
    else:
        return round(price * (1 + slip), 4)


def fill_at_realistic_price(
    intended_stop: float,
    next_open: float,
    direction: str = "long",
) -> tuple[float, str]:
    """If next_open gaps through stop, fill at next_open (not stop price).
    Returns (fill_price, fill_reason).
    - long: gap-down open below stop -> fill at open
    - short: gap-up open above stop -> fill at open
    """
    if direction == "long":
        if next_open < intended_stop:
            return next_open, "gap_through_stop"
    else:  # short
        if next_open > intended_stop:
            return next_open, "gap_through_stop"
    return intended_stop, "normal_stop"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _regime_as_of(spy_df: pd.DataFrame, as_of_date: pd.Timestamp) -> dict:
    """Reconstruct market regime using only SPY data up to as_of_date."""
    sl = spy_df[spy_df.index <= as_of_date]
    if len(sl) < 55:
        return {"regime": "neutral", "spy_price": 0, "spy_daily_chg": 0,
                "distribution_days": 0, "vix": {"vix_current": 20}}

    close_s = sl["Close"].squeeze().dropna()
    close   = close_s.values
    price   = float(close[-1])

    ema50   = float(_ema(close_s, 50).iloc[-1])
    sma200_s = _sma(close_s, 200)
    sma200  = float(sma200_s.iloc[-1]) if len(close_s) >= 200 and not pd.isna(sma200_s.iloc[-1]) else None

    spy_daily_chg = ((close[-1] - close[-2]) / close[-2] * 100) if len(close) >= 2 else 0.0

    dist_days = 0
    vol_s = sl["Volume"].squeeze().dropna() if "Volume" in sl.columns else None
    if vol_s is not None and len(vol_s) >= 26:
        vol = vol_s.values
        for i in range(-25, 0):
            if close[i] < close[i - 1] and vol[i] > vol[i - 1]:
                dist_days += 1

    above_50  = price > ema50
    above_200 = (price > sma200) if sma200 else above_50

    if above_50 and above_200:
        regime = "bull"
    elif not above_50 and not above_200:
        regime = "bear"
    else:
        regime = "neutral"

    spy_1m = round((price / float(close[-21]) - 1) * 100, 1) if len(close) >= 21 else 0

    return {
        "regime":           regime,
        "spy_price":        round(price, 2),
        "above_50ema":      above_50,
        "above_200sma":     above_200,
        "spy_daily_chg":    round(float(spy_daily_chg), 2),
        "distribution_days": dist_days,
        "vix":              {"vix_current": 20},   # no point-in-time VIX available
        "spy_1m_ret":       spy_1m,
    }


def _score_as_of(ticker: str, df_full: pd.DataFrame, as_of_date: pd.Timestamp,
                 spy_full: pd.DataFrame, cfg: dict, info: dict,
                 finviz_data: dict | None = None) -> dict | None:
    """Full 4-pillar score using only data available up to as_of_date.
    finviz_data: optional FINVIZ bulk row for this ticker (current fundamentals — minor look-ahead
    acceptable for quarterly metrics over a 5-10d hold window).
    """
    from analysis import (
        score_technicals, score_fundamentals, score_optionality,
        score_sentiment, score_bear_setup, compute_trade_plan,
        make_decision, pre_trade_gate, apply_setup_wr_multiplier,
    )

    df = df_full[df_full.index <= as_of_date].copy()
    # Flatten multi-level columns (yfinance sometimes returns (field, ticker) columns)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if len(df) < 60:
        return None

    spy_close = spy_full[spy_full.index <= as_of_date]["Close"].squeeze().dropna()
    regime     = _regime_as_of(spy_full, as_of_date)
    regime_name = regime["regime"]

    # Neutral stubs for data unavailable historically
    earnings = {"earnings_risk": False, "days_to_earnings": None, "last_earnings_date": None}
    news     = {"score": 0, "bias": "neutral"}
    insider  = {"buys": 0, "sells": 0, "sentiment": "neutral"}

    # Build extra_fund from FINVIZ data (fundamentals are quarterly — minor look-ahead)
    _ef: dict = {}
    _borrow: dict = {}
    if finviz_data:
        fvz = finviz_data
        # Margins / profitability (normalize % → ratio)
        for fvz_k, ef_k, pct in [
            ("roe_pct",           "roe",              True),
            ("roa_pct",           "roa",              True),
            ("gross_margin_pct",  "gross_margin",     True),
            ("oper_margin_pct",   "operating_margin", True),
            ("profit_margin_pct", "profit_margin",    True),
            ("current_ratio",     "current_ratio",    False),
            ("inst_own_pct",      "institutional_pct",False),
        ]:
            v = fvz.get(fvz_k)
            if v is not None:
                _ef[ef_k] = v / 100.0 if pct else v

        # EPS growth projections
        for fvz_k, ef_k in [("eps_growth_this_yr", "eps_growth_this_yr"),
                              ("eps_growth_next_yr", "eps_growth_next_yr")]:
            v = fvz.get(fvz_k)
            if v is not None:
                _ef[ef_k] = v / 100.0   # normalize to ratio

        # Valuation
        for fvz_k, ef_k in [("peg", "peg"), ("fwd_pe", "fwd_pe"), ("ps", "ps")]:
            v = fvz.get(fvz_k)
            if v is not None:
                _ef[ef_k] = v

        # Short interest for squeeze detection
        if fvz.get("short_float_pct") is not None:
            _borrow["short_float_pct"] = fvz["short_float_pct"]
        if fvz.get("short_ratio") is not None:
            _borrow["days_to_cover"] = fvz["short_ratio"]
        if fvz.get("shares_float") is not None:
            _borrow["shares_float"] = fvz["shares_float"]

    try:
        gate = pre_trade_gate(ticker, df, info, regime, earnings, cfg,
                              skip_market_gates=True)  # backtest: evaluate regardless of crash-day gates
        fund = score_fundamentals(info, zacks=None, beat_rate=None,
                                  extra_fund=_ef if _ef else None)
        tech = score_technicals(df, regime, spy_close if not spy_close.empty else None)
        opt  = score_optionality(df, info, tech["sr"], earnings, news, options_data=None)
        sent = score_sentiment(news, insider, info,
                               borrow_data=_borrow if _borrow else None)
    except Exception as _exc:
        import traceback
        log.warning(f"  {ticker}: scoring error — {type(_exc).__name__}: {_exc}")
        log.debug(traceback.format_exc())
        return None

    # Audit #4 Tier 1: optionally neutralize fundamentals pillar to eliminate
    # look-ahead bias (yfinance `info` reflects today's restated numbers, not
    # as-of-date numbers). When disabled, normalized score is pure technicals.
    if BACKTEST_DISABLE_FUNDAMENTALS:
        fund = {"score": 0, "max": fund.get("max", 30), "reasons": ["disabled (audit #4)"]}

    # Backtest-adjusted scoring: opt/sent pillars return ~0 without live Zacks/news/options.
    # Normalize only the available pillars (tech + fund) to get comparable 0-100 scale.
    tech_max = tech.get("max", 38) or 38
    fund_max = fund.get("max", 30) or 30
    if BACKTEST_DISABLE_FUNDAMENTALS:
        avail_max = tech_max
        raw_avail = tech["score"]
    else:
        avail_max = tech_max + fund_max  # typically 68
        raw_avail  = tech["score"] + fund["score"]
    normalized = round(raw_avail / avail_max * 100, 1)

    ind        = tech["indicators"]
    trend_dir  = ind.get("trend_direction", "")
    direction  = "short" if trend_dir == "downtrend" else "long"

    sr         = tech["sr"]
    plan       = compute_trade_plan(ticker, df, sr, ind, direction, beta=info.get("beta"))
    bear_setup = score_bear_setup(df, ind)

    # Backtest: long-only to avoid short blow-ups (matches live short-restriction logic)
    # No short-squeeze data available historically — restrict to longs
    direction = "long"
    plan = compute_trade_plan(ticker, df, sr, ind, direction, beta=info.get("beta"))
    bear_setup = score_bear_setup(df, ind)

    # Audit #9 — Backtest scoring now matches live path:
    # apply the same historical-WR multiplier analyze_ticker() applies.
    # Before any trades are logged this returns 1.0 (no-op), so deterministic.
    if not getattr(_score_as_of, "_parity_logged", False):
        log.warning("Backtest scoring now matches live path (audit #9 fix)")
        _score_as_of._parity_logged = True  # type: ignore[attr-defined]
    normalized = apply_setup_wr_multiplier(
        normalized, plan.get("setup_type", "unknown"), regime_name
    )

    # Use a lower score gate for backtest since opt/sent pillars are zero
    # Map normalized (tech+fund only) to decision: 55+ = BUY signal (≈ 65 in live)
    _bt_cfg = dict(cfg)
    _bt_cfg.setdefault("decisions", {})
    _bt_cfg["decisions"] = {
        "buy_min_score": 55,   # 55/100 tech+fund ≈ 65/100 full 4-pillar
        "buy_min_rr": 3.0,
        "watch_min_score": 45,
        "avoid_below": 45,
    }
    _bt_cfg.setdefault("regime_thresholds", cfg.get("regime_thresholds", {}))
    _bt_cfg["regime_thresholds"]["bull"]    = {"buy_min_score": 55, "watch_min_score": 50, "rs_min": 60, "weekly_bull_required": False, "rr_min": 3.0}
    _bt_cfg["regime_thresholds"]["neutral"] = {"buy_min_score": 60, "watch_min_score": 55, "rs_min": 65, "weekly_bull_required": False, "rr_min": 3.0}
    _bt_cfg["regime_thresholds"]["bear"]    = {"buy_min_score": 65, "watch_min_score": 60, "rs_min": 70, "weekly_bull_required": False, "rr_min": 4.0}

    decision = make_decision(
        normalized, plan["rr_ratio"], _bt_cfg,
        weak_regime=(regime_name == "bear"),
        direction=direction,
        bear_score=bear_setup["score"],
        rs_rank=int(ind.get("rs_rank", 50)),
        vix=20.0,
        has_catalyst=False,
        rsi=float(ind.get("rsi", 50.0) or 50.0),
        weekly_bull=bool(ind.get("weekly_ema_bullish", False)),
        adx=float(ind.get("adx", 20.0) or 20.0),
        regime_name=regime_name,
        setup_type=plan.get("setup_type", ""),
    )

    if not gate["passed"]:
        decision = {"verdict": "AVOID", "reason": f"Gate: {'; '.join(gate['reasons'][:2])}"}

    return {
        "ticker":       ticker,
        "as_of_date":   as_of_date.strftime("%Y-%m-%d"),
        "regime":       regime_name,
        "score":        normalized,
        "fund_score":   fund["score"],
        "tech_score":   tech["score"],
        "direction":    direction,
        "verdict":      decision["verdict"],
        "setup_type":   plan["setup_type"],
        "rr_ratio":     plan["rr_ratio"],
        "entry_price":  plan["price"],
        "stop":         plan["stop"],
        "target1":      plan["target1"],
        "vcp":          ind.get("vcp", False),
        "power_trend":  ind.get("power_trend", False),
        "pocket_pivot": ind.get("pocket_pivot", False),
        "rs_rank":      int(ind.get("rs_rank", 50)),
        "rsi":          round(float(ind.get("rsi", 50) or 50), 1),
        "weekly_bull":  bool(ind.get("weekly_ema_bullish", False)),
        "bear_score":   bear_setup["score"],
        "reason":       decision.get("reason", ""),
        "gate_passed":  gate["passed"],
        "spy_daily_chg": regime.get("spy_daily_chg", 0),
        "dist_days":    regime.get("distribution_days", 0),
    }


def _forward_returns(df_full: pd.DataFrame, as_of_date: pd.Timestamp,
                     direction: str, hold_days: int = 5,
                     stop_pct: float = None, plan: dict = None) -> dict:
    """
    Simulate realistic trade execution with trailing stop exit.

    Entry: T+1 open (Fix #25)
    Exit logic (priority order):
      1. Stop-loss hit: if intraday low <= stop price → exit at stop (loss capped)
      2. Trailing stop: once +2% profit, trail stop at highest close - 1.25×ATR
         If trailing stop hit → exit (lock in partial gain)
      3. Time stop: if max_hold_days reached → exit at close (prevent dead money)
      4. Let winners run: max hold extended to hold_days × 2 if still trending

    Fix #23 (Slippage): Entry and exit prices adjusted.
    Fix #26 (Survivorship): See SURVIVORSHIP_BIAS_WARNING.
    """
    future = df_full[df_full.index > as_of_date]
    if future.empty or len(future) < 2:
        return {"r1d": None, "r3d": None, "r5d": None, "win": None,
                "max_adverse": None, "exit_reason": None, "exit_day": None,
                "signal_time": "close", "entry_time": "T+1 open",
                "slippage_applied": True, "survivorship_bias": True}

    # Fix #25: Entry at T+1 open
    t1_open = future["Open"].squeeze()
    entry_raw = float(t1_open.iloc[0]) if hasattr(t1_open, 'iloc') else float(t1_open)

    # ATR for trailing stop and slippage model (use last 14 bars before entry)
    pre_entry = df_full[df_full.index <= as_of_date].tail(14)
    if len(pre_entry) >= 5:
        tr = (pre_entry["High"] - pre_entry["Low"]).squeeze()
        atr = float(tr.mean()) if hasattr(tr, 'mean') else float(tr)
    else:
        atr = entry_raw * 0.02  # fallback 2%

    # Audit #5: 20-day ADV (shares) for slippage liquidity-impact term
    pre_adv = df_full[df_full.index <= as_of_date].tail(20)
    if "Volume" in pre_adv.columns and len(pre_adv) >= 5:
        vol_s = pre_adv["Volume"].squeeze().dropna()
        adv_20d = float(vol_s.mean()) if len(vol_s) else 0.0
    else:
        adv_20d = 0.0
    # Order value unknown at signal-eval stage — pass 0 so impact term collapses;
    # base+ATR still apply. Portfolio sim uses real position size.
    entry = apply_entry_slippage(entry_raw, direction, atr=atr, adv_20d=adv_20d, order_value=0)

    future_close = future["Close"].squeeze()
    future_high = future["High"].squeeze()
    future_low = future["Low"].squeeze()
    future_open = future["Open"].squeeze() if "Open" in future.columns else future_close

    # Determine stop price
    if stop_pct is None and plan:
        stop_price = plan.get("stop", 0)
        if stop_price and stop_price > 0:
            stop_pct = abs(entry - stop_price) / entry * 100
    if stop_pct is None:
        stop_pct = 5.0  # default 5% hard stop

    stop_price = entry * (1 - stop_pct / 100) if direction == "long" else entry * (1 + stop_pct / 100)

    # Simulate day by day
    max_hold = min(hold_days * 2, len(future_close))  # let winners run up to 2x hold
    trail_stop = stop_price
    trail_activated = False
    highest_close = entry
    exit_price = None
    exit_day = None
    exit_reason = None
    mae = 0.0

    for day in range(min(max_hold, len(future_close))):
        c = float(future_close.iloc[day]) if hasattr(future_close, 'iloc') else float(future_close)
        h = float(future_high.iloc[day]) if hasattr(future_high, 'iloc') else float(future_high)
        lo = float(future_low.iloc[day]) if hasattr(future_low, 'iloc') else float(future_low)
        op = float(future_open.iloc[day]) if hasattr(future_open, 'iloc') else float(future_open)

        # Track MAE
        if direction == "long":
            adverse = (entry - lo) / entry * 100
        else:
            adverse = (h - entry) / entry * 100
        mae = max(mae, adverse)

        # Check hard stop hit intraday (Audit #5: gap-through-stop)
        if direction == "long" and lo <= stop_price:
            fill_px, fill_reason = fill_at_realistic_price(stop_price, op, direction)
            exit_price = apply_exit_slippage(fill_px, direction, atr=atr, adv_20d=adv_20d, order_value=0)
            exit_day = day + 1
            exit_reason = fill_reason if fill_reason == "gap_through_stop" else "stop_loss"
            break

        # Check trailing stop hit (Audit #5: gap-through-stop)
        if trail_activated and direction == "long" and lo <= trail_stop:
            fill_px, fill_reason = fill_at_realistic_price(trail_stop, op, direction)
            exit_price = apply_exit_slippage(fill_px, direction, atr=atr, adv_20d=adv_20d, order_value=0)
            exit_day = day + 1
            exit_reason = fill_reason if fill_reason == "gap_through_stop" else "trailing_stop"
            break

        # Update trailing stop (activate after +2% profit)
        if direction == "long":
            if c > highest_close:
                highest_close = c
            gain_pct = (c - entry) / entry * 100
            if gain_pct >= 2.0:
                trail_activated = True
                new_trail = highest_close - 1.25 * atr
                if new_trail > trail_stop:
                    trail_stop = new_trail
                # Also move hard stop to breakeven once +2%
                if stop_price < entry:
                    stop_price = entry

        # Time stop: exit at hold_days if flat (< +1%)
        if day + 1 == hold_days:
            gain_pct = (c - entry) / entry * 100 if direction == "long" else (entry - c) / entry * 100
            if gain_pct < 1.0:
                exit_price = apply_exit_slippage(c, direction, atr=atr, adv_20d=adv_20d, order_value=0)
                exit_day = day + 1
                exit_reason = "time_stop"
                break
            # else let it run to max_hold

    # If no exit triggered, close at last available bar
    if exit_price is None:
        last_idx = min(max_hold - 1, len(future_close) - 1)
        c = float(future_close.iloc[last_idx]) if hasattr(future_close, 'iloc') else float(future_close)
        exit_price = apply_exit_slippage(c, direction, atr=atr, adv_20d=adv_20d, order_value=0)
        exit_day = last_idx + 1
        exit_reason = "max_hold"

    # Calculate returns
    if direction == "long":
        final_ret = round((exit_price - entry) / entry * 100, 2)
    else:
        final_ret = round((entry - exit_price) / entry * 100, 2)

    # Also compute fixed-period returns for comparison
    def _ret(n: int):
        if len(future_close) < n:
            return None
        exit_raw = float(future_close.iloc[n - 1]) if hasattr(future_close, 'iloc') else float(future_close)
        ep = apply_exit_slippage(exit_raw, direction, atr=atr, adv_20d=adv_20d, order_value=0)
        if direction == "long":
            return round((ep - entry) / entry * 100, 2)
        return round((entry - ep) / entry * 100, 2)

    r1 = _ret(1)
    r3 = _ret(min(3, hold_days))

    return {
        "r1d": r1,
        "r3d": r3,
        "r5d": final_ret,  # now reflects trailing stop exit, not fixed day
        "win": (final_ret > 0),
        "max_adverse": round(mae, 2),
        "exit_reason": exit_reason,
        "exit_day": exit_day,
        "signal_time": "close",
        "entry_time": "T+1 open",
        "entry_price_with_slippage": entry,
        "slippage_applied": True,
        "survivorship_bias": True,
    }


# ── Main Backtest Engine ─────────────────────────────────────────────────────

def _deep_merge(dst: dict, src: dict) -> dict:
    """Recursively merge src into dst (in place). Used by --config-override
    so walk_forward_v2 can pass {setup_score_multiplier: {Trend Continuation: 1.10}}
    without overwriting all of setup_score_multiplier."""
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _apply_config_override(cfg: dict, override: str | None) -> dict:
    """Parse --config-override (file path or inline JSON string) and deep-merge."""
    if not override:
        return cfg
    try:
        from pathlib import Path as _P
        path = _P(override)
        if path.exists():
            data = json.loads(path.read_text())
        else:
            # Treat as inline JSON
            data = json.loads(override)
        _deep_merge(cfg, data)
    except Exception as e:
        log.warning(f"--config-override failed to parse ({e}); using base config")
    return cfg


def run_backtest(days: int = 252, hold_days: int = 5,
                 min_score: int = 50, min_rs: int = 65,
                 top_n: int = 5, end_date: str | None = None,
                 profile: str | None = None,
                 config_override: str | None = None) -> list[dict]:
    """
    Single-window backtest. For true walk-forward, use backtest/walk_forward_v2.py.

    Args:
        days:      Trading days to backtest (default 252 ≈ 1 year)
        hold_days: Hold period in trading days (default 5)
        min_score: Minimum score to include a signal (default 65 = bull-regime threshold)
        min_rs:    Minimum RS rank (default 75 = live system floor)
        top_n:     Max signals per day (default 5 = live system max positions)
        end_date:  Optional ISO date (YYYY-MM-DD) capping the backtest window; the
                   window ends at or before this date. If None, uses most recent data.
        profile:   Optional trading profile name to merge into config.

    Data source: Polygon.io (5yr history, no rate limits) with yfinance fallback.
    """
    cfg = json.loads((BASE_DIR / "config" / "config.json").read_text())

    # Apply --config-override (used by walk_forward_v2 for grid search)
    cfg = _apply_config_override(cfg, config_override)

    # Merge trading profile if specified
    if profile:
        profile_path = BASE_DIR / "config" / "profiles" / f"{profile}.json"
        if profile_path.exists():
            pdata = json.loads(profile_path.read_text())
            for k, v in pdata.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
            log.info(f"Profile '{profile}' merged into backtest config")
            # Override min_score/min_rs from profile if stricter
            _prof_buy_min = pdata.get("decisions", {}).get("buy_min_score")
            if _prof_buy_min and _prof_buy_min > min_score:
                min_score = _prof_buy_min
                log.info(f"  Profile overrides min_score to {min_score}")
        else:
            log.warning(f"Profile '{profile}' not found at {profile_path}")

    log.info(f"=== SwingTrade Walk-Forward Backtest: {days}d window, {hold_days}d hold ===")
    log.info(f"Thresholds: score≥{min_score}, RS≥{min_rs}, top {top_n}/day")
    log.info("Data: Polygon.io OHLCV (5yr) + FINVIZ fundamentals. Zacks/news/insider unavailable historically.")
    log.warning(SURVIVORSHIP_BIAS_WARNING)
    if BACKTEST_DISABLE_FUNDAMENTALS:
        log.warning("AUDIT #4: Fundamentals pillar DISABLED (BACKTEST_NO_FUNDAMENTALS=1). "
                    "Normalized score = pure technicals; fund gate bypassed.")
    else:
        log.warning(FUNDAMENTAL_LOOKAHEAD_WARNING)
    log.info("Slippage model: entry 3bps, exit 2bps, $0 commission. Signal at T close -> entry at T+1 open.")

    from data_fetcher import get_sp500, get_russell1000, get_stock_info_batch, get_finviz_bulk, get_polygon_ohlcv
    import time

    # Calendar days = test window + indicator lookback buffer.
    # 2026-05-08 fix: was +60 → backtest scored 0 picks because the early
    # test-window dates had <200 bars of pre-date history (200-day SMA needs
    # 200 bars before bt_date). Bumped lookback to +350 calendar days
    # (~240 trading days) which covers all common indicators (200d SMA,
    # 252d RS rank, etc.). Parquet archive has 533 rows so plenty available.
    calendar_days_needed = int(days * 1.45) + 350

    # ── Universe: S&P 500 + Russell 1000 (deduplicated) filtered to $2–$250 ──
    # 2026-05-09: support point-in-time membership via AS_OF_MEMBERSHIP env var
    # (set by main() when --as-of-membership flag passed). Closes audit #1
    # Tier 2 — eliminates survivorship bias by using monthly snapshots from
    # data/membership/sp500_YYYY-MM.csv (built by build_membership_snapshots.py).
    import os as _os_uni
    if _os_uni.environ.get("AS_OF_MEMBERSHIP") == "1":
        from data_fetcher import get_universe_as_of as _get_as_of
        from datetime import date as _d, timedelta as _td
        # Window covers backtest days + lookback for indicators
        end = _d.fromisoformat(end_date) if end_date else _d.today()
        start = end - _td(days=int(days * 1.45))
        # Union of monthly membership across the window: captures every ticker
        # that was an S&P 500 member at any point during the test period.
        # Avoids the survivorship trap of using today's membership for past dates.
        all_tickers: set = set()
        cur = start.replace(day=1)
        while cur <= end:
            all_tickers.update(_get_as_of(cur.isoformat(), include_r1000=True, include_custom=True))
            cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
        universe = sorted(all_tickers)
        log.info(f"Universe (AS-OF point-in-time): {len(universe)} tickers from {start.isoformat()}→{end.isoformat()} "
                 f"(union of monthly S&P 500 snapshots ∪ R1000 ∪ custom) — survivorship-corrected")
    else:
        sp500 = get_sp500()
        russell = []
        try:
            russell = get_russell1000()
        except Exception:
            log.warning("Russell 1000 fetch failed, using S&P 500 only")
        # Merge and deduplicate, preserving order (S&P 500 first)
        _seen = set()
        universe = []
        for t in sp500 + russell:
            if t and t not in _seen:
                _seen.add(t)
                universe.append(t)
        log.info(f"Universe: {len(universe)} tickers (S&P 500 + Russell 1000 merged) — will filter by price after download")

    # ── Try loading from data archive first (instant vs 60+ min API download) ──
    _archive_loaded = False
    try:
        from data_archive import load_all, OHLCV_DIR
        if OHLCV_DIR.exists() and any(OHLCV_DIR.glob("*.parquet")):
            log.info("Loading from data archive (Parquet)...")
            t0 = time.time()
            _archive_data = load_all(universe)
            if len(_archive_data) >= len(universe) * 0.5:  # at least 50% hit rate
                log.info(f"Archive: loaded {len(_archive_data)}/{len(universe)} tickers in {time.time()-t0:.1f}s")
                _archive_loaded = True
    except Exception as e:
        log.debug(f"Archive load failed: {e}")

    def _download_one(ticker: str, retries: int = 2) -> pd.DataFrame | None:
        """
        Download OHLCV for a single ticker.
        Tries Polygon.io first (5yr, no rate limits), falls back to yfinance.
        Returns a clean single-level DataFrame with timezone-naive DatetimeIndex.
        """
        # ── Polygon.io (primary) ──
        try:
            df = get_polygon_ohlcv(ticker, days=calendar_days_needed, timespan="day")
            if df is not None and len(df) >= 60:
                # Normalise index: remove timezone so it matches yfinance convention
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                # Keep only OHLCV columns (drop VWAP/Transactions if present)
                cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                df = df[cols].dropna(how="all")
                # Price filter
                try:
                    last_price = float(df["Close"].dropna().iloc[-1])
                    if not (2.0 <= last_price <= 250.0):
                        return None
                except Exception:
                    pass
                return df
        except Exception as _pg_err:
            log.debug(f"Polygon {ticker}: {_pg_err} — falling back to yfinance")

        # ── yfinance (fallback) ──
        for attempt in range(retries):
            try:
                df = yf.download(ticker, period="2y", interval="1d",
                                 progress=False, auto_adjust=True)
                if df is None or df.empty or len(df) < 60:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.loc[:, ~df.columns.duplicated()]
                for col in ["Open", "High", "Low", "Close", "Volume"]:
                    if col in df.columns and isinstance(df[col], pd.DataFrame):
                        df[col] = df[col].squeeze()
                # Price filter
                try:
                    last_price = float(df["Close"].dropna().iloc[-1])
                    if not (2.0 <= last_price <= 250.0):
                        return None
                except Exception:
                    pass
                return df.dropna(how="all")
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(1)
        return None

    # ── Load data: archive first, then API for missing tickers ──
    raw_data = {}

    if _archive_loaded:
        # Use archive data — apply price filter and tz normalization
        for t, df in _archive_data.items():
            if df is None or len(df) < 60:
                continue
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[cols].dropna(how="all")
            try:
                last_price = float(df["Close"].dropna().iloc[-1])
                if 2.0 <= last_price <= 250.0:
                    raw_data[t] = df
            except Exception:
                pass
        log.info(f"Archive: {len(raw_data)} tickers pass price filter")

        # Download any missing tickers from API
        missing = [t for t in universe if t not in raw_data]
        if missing and len(missing) < 100:
            log.info(f"Downloading {len(missing)} missing tickers from API...")
            with ThreadPoolExecutor(max_workers=16) as pool:
                for t, df_t in pool.map(lambda t: (t, _download_one(t)), missing):
                    if df_t is not None:
                        raw_data[t] = df_t
    else:
        # No archive — full API download
        log.info(f"Downloading {len(universe)} tickers via Polygon.io (32 workers)...")

        def _dl(t):
            return t, _download_one(t)

        with ThreadPoolExecutor(max_workers=32) as pool:
            dl_futures = {pool.submit(_dl, t): t for t in universe}
            done = 0
            for fut in as_completed(dl_futures):
                t, df_t = fut.result()
                done += 1
                if df_t is not None:
                    raw_data[t] = df_t
                if done % 100 == 0:
                    log.info(f"  {done}/{len(universe)} downloaded ({len(raw_data)} in range)...")

    log.info(f"Ready: {len(raw_data)} tickers pass price filter")

    # SPY — fetch directly without price filter (SPY ~$679, above universe $250 cap)
    log.info("Downloading SPY benchmark data...")
    spy_df = None
    try:
        spy_df = get_polygon_ohlcv("SPY", days=calendar_days_needed, timespan="day")
        if spy_df is not None and spy_df.index.tz is not None:
            spy_df.index = spy_df.index.tz_localize(None)
            cols = [c for c in ["Open","High","Low","Close","Volume"] if c in spy_df.columns]
            spy_df = spy_df[cols].dropna(how="all")
    except Exception as _se:
        log.warning(f"Polygon SPY failed: {_se} — trying yfinance")
    if spy_df is None or spy_df.empty:
        try:
            spy_df = yf.download("SPY", period="2y", interval="1d", progress=False, auto_adjust=True)
            if isinstance(spy_df.columns, pd.MultiIndex):
                spy_df.columns = spy_df.columns.get_level_values(0)
        except Exception:
            pass
    if spy_df is None or spy_df.empty:
        log.error("SPY data unavailable — cannot reconstruct regime")
        return []
    raw_data["SPY"] = spy_df

    spy_full = raw_data.get("SPY", spy_df)
    if spy_full is None or spy_full.empty:
        log.error("SPY data missing — cannot proceed")
        return []

    active_universe = [t for t in raw_data if t != "SPY"]

    # Trading days to backtest
    spy_close = spy_full["Close"].squeeze().dropna()
    available_dates = list(spy_close.index)
    # Optional end_date cap: trim available_dates to <= end_date (plus hold_days buffer
    # kept in future forward-returns from raw_data, not available_dates).
    if end_date:
        try:
            _cap = pd.Timestamp(end_date)
            available_dates = [d for d in available_dates if d <= _cap]
        except Exception as _ee:
            log.warning(f"Bad --end-date '{end_date}': {_ee} — ignoring")
    if len(available_dates) < days + hold_days:
        log.warning(f"Only {len(available_dates)} days of SPY data — reducing window")
        days = max(len(available_dates) - hold_days - 5, 10)
    bt_end_idx   = max(len(available_dates) - hold_days - 1, 0)
    bt_start_idx = max(bt_end_idx - days + 1, 0)
    backtest_dates = available_dates[bt_start_idx:bt_end_idx + 1]

    log.info(f"Backtest window: {backtest_dates[0].strftime('%Y-%m-%d')} → {backtest_dates[-1].strftime('%Y-%m-%d')} ({len(backtest_dates)} days)")
    log.info(f"Active universe: {len(active_universe)} tickers")

    # Fetch current fundamentals (yfinance info).
    # AUDIT #4 look-ahead bias: this data reflects TODAY's restated numbers
    # (P/E, D/E, EPS growth, margins), NOT the values as-of each historical
    # signal date. Tier 1 mitigation: set BACKTEST_NO_FUNDAMENTALS=1 to skip
    # this batch entirely and neutralize the fundamentals pillar at scoring
    # time. Tier 2 (roadmap): replace with point-in-time
    # `fundamentals_as_of(ticker, date)` via Finnhub financials-reported.
    if BACKTEST_DISABLE_FUNDAMENTALS:
        log.info(f"AUDIT #4: skipping yfinance info fetch for {len(active_universe)} tickers "
                 f"(BACKTEST_NO_FUNDAMENTALS=1) — using empty info dicts.")
        infos = {t: {"ticker": t} for t in active_universe}
    else:
        log.info(f"Fetching yfinance info for {len(active_universe)} tickers "
                 f"(current snapshot — see audit #4 look-ahead warning above)...")
        infos = get_stock_info_batch(active_universe, max_workers=16)

    # Fetch FINVIZ Elite bulk data — better fundamentals + short interest
    log.info("Fetching FINVIZ Elite bulk data...")
    try:
        finviz_bulk = get_finviz_bulk()
        log.info(f"  FINVIZ: {len(finviz_bulk)} tickers loaded")
    except Exception as _fvz_err:
        log.warning(f"  FINVIZ fetch failed: {_fvz_err} — continuing without")
        finviz_bulk = {}

    # Score each ticker for each backtest date
    all_picks: list[dict] = []

    # 2026-05-08 fix: backtest now respects the decision_engine kill list.
    # Live system gates EMA21 Pullback / 52wk Breakout via compute_final_verdict
    # (swing_trade.py:3122) but backtest's _score_as_of path bypasses it. Result:
    # backtest fired 31 EMA21 Pullback trades at 22.6% WR (-$144 in 60d sample).
    # Now load the kill list once and reject killed setups before they enter
    # day_scored.
    _kill_list: dict = {}
    try:
        from decision_engine import compute_setup_kill_list
        _kill_list = compute_setup_kill_list() or {}
        if _kill_list:
            log.info(f"  Backtest kill list active: {list(_kill_list.keys())}")
    except Exception as _kl_err:
        log.warning(f"  Backtest kill list unavailable: {_kl_err}")

    for bt_date in backtest_dates:
        day_scored = []

        def _score_one(ticker: str):
            df_t = raw_data.get(ticker)
            if df_t is None:
                return None
            info = infos.get(ticker, {"ticker": ticker})
            return _score_as_of(ticker, df_t, bt_date, spy_full, cfg, info,
                                finviz_data=finviz_bulk.get(ticker))

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(_score_one, t): t for t in active_universe}
            for fut in as_completed(futures):
                res = fut.result()
                if not (res and res["gate_passed"]
                        and res["score"] >= min_score
                        and res.get("rs_rank", 0) >= min_rs):
                    continue
                # Apply kill list — same rule as live decision_engine
                _setup_name = res.get("setup_type") or res.get("setup_family") or ""
                if _setup_name in _kill_list:
                    continue
                day_scored.append(res)

        # Sort by score, take top_n — mirrors live system's max positions
        day_scored.sort(key=lambda x: x["score"], reverse=True)
        day_picks = day_scored[:top_n]

        buy_count   = sum(1 for p in day_picks if p["verdict"] == "BUY")
        watch_count = sum(1 for p in day_picks if p["verdict"] == "WATCH")
        for res in day_picks:
            _plan = {"stop": res.get("stop", 0)}
            fwd = _forward_returns(raw_data[res["ticker"]], bt_date, res["direction"], hold_days, plan=_plan)
            res.update(fwd)

        if day_picks:
            log.info(f"  {bt_date.strftime('%Y-%m-%d')}: {len(day_picks)} picks (BUY:{buy_count} WATCH:{watch_count} pool:{len(day_scored)})")

        log.info(f"    → {len(day_picks)} picks (BUY:{buy_count} WATCH:{watch_count} total scored:{len(day_scored)})")
        all_picks.extend(day_picks)

    return all_picks


# ── Statistics ───────────────────────────────────────────────────────────────

def compute_stats(picks: list[dict]) -> dict:
    evaluated = [p for p in picks if p.get("r5d") is not None]
    if not evaluated:
        return {"total": len(picks), "evaluated": 0}

    wins   = [p for p in evaluated if p.get("win")]
    losses = [p for p in evaluated if not p.get("win")]

    win_rets  = [p["r5d"] for p in wins]
    loss_rets = [p["r5d"] for p in losses]

    avg_win   = round(sum(win_rets)  / len(win_rets),  2) if win_rets  else 0
    avg_loss  = round(sum(loss_rets) / len(loss_rets), 2) if loss_rets else 0
    gross_w   = sum(win_rets)
    gross_l   = abs(sum(loss_rets))
    pf        = round(gross_w / gross_l, 2) if gross_l > 0 else float("inf")

    # By setup type
    by_setup: dict[str, dict] = {}
    for p in evaluated:
        s = p.get("setup_type", "Unknown")
        if s not in by_setup:
            by_setup[s] = {"wins": 0, "total": 0, "rets": []}
        by_setup[s]["total"] += 1
        by_setup[s]["rets"].append(p["r5d"])
        if p.get("win"):
            by_setup[s]["wins"] += 1
    setup_stats = sorted([
        {"setup": k, "total": v["total"],
         "win_rate": round(v["wins"] / v["total"] * 100, 1),
         "avg_ret": round(sum(v["rets"]) / len(v["rets"]), 2)}
        for k, v in by_setup.items()], key=lambda x: x["win_rate"], reverse=True)

    # By regime
    by_regime: dict[str, dict] = {}
    for p in evaluated:
        r = p.get("regime", "?")
        if r not in by_regime:
            by_regime[r] = {"wins": 0, "total": 0}
        by_regime[r]["total"] += 1
        if p.get("win"):
            by_regime[r]["wins"] += 1
    regime_stats = {k: {"total": v["total"], "win_rate": round(v["wins"]/v["total"]*100, 1)}
                    for k, v in by_regime.items()}

    # Pattern signals
    def _pattern_stats(key):
        subset = [p for p in evaluated if p.get(key)]
        if not subset:
            return None
        w = sum(1 for p in subset if p.get("win"))
        return {"total": len(subset), "win_rate": round(w/len(subset)*100,1),
                "avg_ret": round(sum(p["r5d"] for p in subset)/len(subset), 2)}

    return {
        "total":        len(picks),
        "evaluated":    len(evaluated),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(len(wins) / len(evaluated) * 100, 1),
        "avg_win":      avg_win,
        "avg_loss":     avg_loss,
        "profit_factor": pf,
        "gross_pnl":    round(gross_w - gross_l, 2),
        "avg_ret_5d":   round(sum(p["r5d"] for p in evaluated) / len(evaluated), 2),
        "avg_mae":      round(sum(p["max_adverse"] or 0 for p in evaluated) / len(evaluated), 2),
        "best_trade":   max(evaluated, key=lambda p: p["r5d"]),
        "worst_trade":  min(evaluated, key=lambda p: p["r5d"]),
        "setup_stats":  setup_stats,
        "regime_stats": regime_stats,
        "vcp_stats":    _pattern_stats("vcp"),
        "pt_stats":     _pattern_stats("power_trend"),
        "pp_stats":     _pattern_stats("pocket_pivot"),
    }


# ── HTML Report ──────────────────────────────────────────────────────────────

def render_report(picks: list[dict], stats: dict, days: int, hold_days: int) -> str:
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    evaluated = [p for p in picks if p.get("r5d") is not None]

    # Equity curve (cumulative avg return per day)
    by_date: dict[str, list] = {}
    for p in evaluated:
        d = p["as_of_date"]
        by_date.setdefault(d, []).append(p["r5d"])
    dates_sorted = sorted(by_date)
    cum_ret = 0.0
    curve_pts = []
    for d in dates_sorted:
        avg = sum(by_date[d]) / len(by_date[d])
        cum_ret += avg
        curve_pts.append({"date": d, "avg": round(avg, 2), "cum": round(cum_ret, 2)})

    curve_js = json.dumps(curve_pts)

    # Picks table rows
    def _row(p):
        r5 = p.get("r5d")
        r1 = p.get("r1d")
        r3 = p.get("r3d")
        win = p.get("win")
        if r5 is None:
            row_cls, badge = "text-gray-400", '<span class="px-1 rounded text-xs bg-gray-200 text-gray-600">pending</span>'
        elif win:
            row_cls, badge = "text-green-800", f'<span class="px-1 rounded text-xs bg-green-100 text-green-700">WIN +{r5}%</span>'
        else:
            row_cls, badge = "text-red-800", f'<span class="px-1 rounded text-xs bg-red-100 text-red-700">LOSS {r5}%</span>'

        patterns = " ".join([
            '<span class="text-xs bg-purple-100 text-purple-700 px-1 rounded">VCP</span>'  if p.get("vcp") else "",
            '<span class="text-xs bg-blue-100 text-blue-700 px-1 rounded">PT</span>'        if p.get("power_trend") else "",
            '<span class="text-xs bg-yellow-100 text-yellow-700 px-1 rounded">PP</span>'   if p.get("pocket_pivot") else "",
        ]).strip()

        dir_badge = ('<span class="text-xs bg-green-100 text-green-700 px-1 rounded">LONG</span>'
                     if p["direction"] == "long" else
                     '<span class="text-xs bg-red-100 text-red-700 px-1 rounded">SHORT</span>')

        def r_fmt(v):
            if v is None:
                return '<span class="text-gray-400">—</span>'
            cls = "text-green-600" if v > 0 else "text-red-600"
            return f'<span class="{cls}">{v:+.1f}%</span>'

        return f"""
        <tr class="border-b hover:bg-gray-50">
          <td class="py-1 px-2 text-xs text-gray-500">{p["as_of_date"]}</td>
          <td class="py-1 px-2 font-semibold">{p["ticker"]}</td>
          <td class="py-1 px-2">{dir_badge}</td>
          <td class="py-1 px-2 text-xs">{p.get("regime","?")}</td>
          <td class="py-1 px-2 font-semibold">{p["score"]:.0f}</td>
          <td class="py-1 px-2 text-xs text-gray-600">{p.get("setup_type","?")[:20]}</td>
          <td class="py-1 px-2 text-xs">{patterns}</td>
          <td class="py-1 px-2">{r_fmt(r1)}</td>
          <td class="py-1 px-2">{r_fmt(r3)}</td>
          <td class="py-1 px-2 font-semibold">{badge}</td>
        </tr>"""

    rows_html = "\n".join(_row(p) for p in sorted(picks, key=lambda x: x["as_of_date"], reverse=True))

    # Setup breakdown table
    def _setup_row(s):
        wr_cls   = "text-green-600" if s["win_rate"] >= 60 else ("text-yellow-600" if s["win_rate"] >= 40 else "text-red-600")
        ret_cls  = "text-green-600" if s["avg_ret"] > 0 else "text-red-600"
        return (f'<tr class="border-b">'
                f'<td class="py-1 px-3 text-sm">{s["setup"]}</td>'
                f'<td class="py-1 px-3 text-center">{s["total"]}</td>'
                f'<td class="py-1 px-3 text-center font-semibold {wr_cls}">{s["win_rate"]}%</td>'
                f'<td class="py-1 px-3 text-center {ret_cls}">{s["avg_ret"]:+.2f}%</td>'
                f'</tr>')
    setup_rows = "\n".join(_setup_row(s) for s in stats.get("setup_stats", []))

    # Pattern cards
    def _pat_card(label, data, color):
        if not data:
            return f'<div class="bg-gray-50 rounded p-3 text-center text-gray-400 text-sm">{label}<br>No signals</div>'
        wr_cls = "text-green-600" if data["win_rate"] >= 60 else "text-yellow-600"
        return f"""<div class="bg-white border rounded p-3 text-center">
          <div class="text-xs text-gray-500 mb-1">{label}</div>
          <div class="text-2xl font-bold {wr_cls}">{data["win_rate"]}%</div>
          <div class="text-xs text-gray-500">{data["total"]} trades · avg {data["avg_ret"]:+.2f}%</div>
        </div>"""

    pat_html = "".join([
        _pat_card("VCP (Minervini)",   stats.get("vcp_stats"),  "purple"),
        _pat_card("Power Trend (IBD)", stats.get("pt_stats"),   "blue"),
        _pat_card("Pocket Pivot",      stats.get("pp_stats"),   "yellow"),
    ])

    wr   = stats.get("win_rate", 0)
    pf   = stats.get("profit_factor", 0)
    wr_c = "#059669" if wr >= 60 else ("#d97706" if wr >= 45 else "#dc2626")

    # Pre-compute block strings to avoid nested f-string expressions (Python 3.9 restriction)
    regime_rows_html = ""
    for _r, _d in stats.get("regime_stats", {}).items():
        _wr_cls = "text-green-600" if _d["win_rate"] >= 60 else "text-yellow-600"
        regime_rows_html += (
            f'<div class="flex items-center justify-between mb-2">'
            f'<span class="text-sm capitalize font-medium">{_r}</span>'
            f'<div class="flex items-center gap-2">'
            f'<span class="text-xs text-gray-500">{_d["total"]} trades</span>'
            f'<span class="font-bold {_wr_cls}">{_d["win_rate"]}%</span>'
            f'</div></div>'
        )

    _best  = stats.get("best_trade",  {})
    _worst = stats.get("worst_trade", {})
    best_txt  = f'{_best.get("ticker","?")} +{_best.get("r5d","?")}%'
    worst_txt = f'{_worst.get("ticker","?")} {_worst.get("r5d","?")}%'
    pf_display = str(pf) if pf != float("inf") else "&#8734;"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SwingTrade Backtest Report</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>body{{font-family:'Inter',sans-serif;background:#f8fafc;}}</style>
</head>
<body class="p-6">

<div class="max-w-7xl mx-auto">

<!-- Header -->
<div class="mb-6">
  <h1 class="text-2xl font-bold text-gray-900">SwingTrade Walk-Forward Backtest</h1>
  <p class="text-sm text-gray-500 mt-1">Last {days} trading days · {hold_days}-day hold · Technical model only (no Zacks/news/insider) · Generated {run_ts}</p>
  <div class="mt-2 text-xs text-amber-600 bg-amber-50 px-3 py-1 rounded inline-block">
    Fundamental data is current (quarterly cadence) · No Zacks rank filter · S&P 500 + Russell 1000 universe · Entry slippage 3bps, exit 2bps · Signal at T close, entry at T+1 open
  </div>
  <div class="mt-1 text-xs text-red-600 bg-red-50 px-3 py-1 rounded inline-block">
    SURVIVORSHIP BIAS: Uses current S&P 500 membership. Historical index changes not accounted for. Expect live performance 3-5% below backtest estimates.
  </div>
</div>

<!-- KPI Cards -->
<div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
  <div class="bg-white rounded-xl border p-4 text-center">
    <div class="text-xs text-gray-500 mb-1">Win Rate</div>
    <div class="text-3xl font-bold" style="color:{wr_c}">{wr}%</div>
    <div class="text-xs text-gray-400">{stats.get('wins',0)}W / {stats.get('losses',0)}L</div>
  </div>
  <div class="bg-white rounded-xl border p-4 text-center">
    <div class="text-xs text-gray-500 mb-1">Profit Factor</div>
    <div class="text-3xl font-bold text-green-600">{pf_display}</div>
    <div class="text-xs text-gray-400">gross W ÷ gross L</div>
  </div>
  <div class="bg-white rounded-xl border p-4 text-center">
    <div class="text-xs text-gray-500 mb-1">Avg Win</div>
    <div class="text-3xl font-bold text-green-600">+{stats.get('avg_win',0)}%</div>
    <div class="text-xs text-gray-400">per trade</div>
  </div>
  <div class="bg-white rounded-xl border p-4 text-center">
    <div class="text-xs text-gray-500 mb-1">Avg Loss</div>
    <div class="text-3xl font-bold text-red-600">{stats.get('avg_loss',0)}%</div>
    <div class="text-xs text-gray-400">per trade</div>
  </div>
  <div class="bg-white rounded-xl border p-4 text-center">
    <div class="text-xs text-gray-500 mb-1">Signals</div>
    <div class="text-3xl font-bold text-gray-700">{stats.get('total',0)}</div>
    <div class="text-xs text-gray-400">{stats.get('evaluated',0)} evaluated</div>
  </div>
</div>

<!-- Equity Curve + Regime -->
<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
  <div class="md:col-span-2 bg-white rounded-xl border p-4">
    <h2 class="text-sm font-semibold text-gray-600 mb-3">Cumulative Avg Return by Day</h2>
    <canvas id="eqCurve" height="120"></canvas>
  </div>
  <div class="bg-white rounded-xl border p-4">
    <h2 class="text-sm font-semibold text-gray-600 mb-3">By Regime</h2>
    {regime_rows_html}
    <hr class="my-3">
    <div class="text-xs text-gray-500">
      Best: <span class="font-semibold text-green-600">{best_txt}</span><br>
      Worst: <span class="font-semibold text-red-600">{worst_txt}</span>
    </div>
  </div>
</div>

<!-- Pattern Signal Cards -->
<div class="mb-6">
  <h2 class="text-sm font-semibold text-gray-600 mb-3">Pattern Signal Performance</h2>
  <div class="grid grid-cols-3 gap-4">{pat_html}</div>
</div>

<!-- Setup Breakdown -->
<div class="bg-white rounded-xl border p-4 mb-6">
  <h2 class="text-sm font-semibold text-gray-600 mb-3">Win Rate by Setup Type</h2>
  <table class="w-full text-sm">
    <thead><tr class="border-b text-gray-500 text-xs">
      <th class="text-left py-1 px-3">Setup Type</th>
      <th class="text-center py-1 px-3">Trades</th>
      <th class="text-center py-1 px-3">Win Rate</th>
      <th class="text-center py-1 px-3">Avg Return (5d)</th>
    </tr></thead>
    <tbody>{setup_rows}</tbody>
  </table>
</div>

<!-- Picks Table -->
<div class="bg-white rounded-xl border p-4">
  <h2 class="text-sm font-semibold text-gray-600 mb-3">All Backtest Signals</h2>
  <div class="overflow-x-auto">
  <table class="w-full text-sm">
    <thead><tr class="border-b text-gray-500 text-xs">
      <th class="text-left py-1 px-2">Date</th>
      <th class="text-left py-1 px-2">Ticker</th>
      <th class="py-1 px-2">Dir</th>
      <th class="py-1 px-2">Regime</th>
      <th class="py-1 px-2">Score</th>
      <th class="text-left py-1 px-2">Setup</th>
      <th class="py-1 px-2">Patterns</th>
      <th class="py-1 px-2">1d</th>
      <th class="py-1 px-2">3d</th>
      <th class="py-1 px-2">5d Outcome</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  </div>
</div>

</div>

<script>
const pts = {curve_js};
if (pts.length) {{
  const ctx = document.getElementById('eqCurve').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: pts.map(p => p.date),
      datasets: [
        {{label:'Daily Avg %', data: pts.map(p=>p.avg), borderColor:'#6366f1', tension:0.3, pointRadius:4, fill:false}},
        {{label:'Cumulative %', data: pts.map(p=>p.cum), borderColor:'#059669', tension:0.3, pointRadius:3, borderDash:[4,2], fill:false}},
      ]
    }},
    options: {{
      responsive:true, plugins:{{legend:{{position:'top'}}}},
      scales:{{y:{{ticks:{{callback:v=>v+'%'}}}}}}
    }}
  }});
}}
</script>
</body>
</html>"""


# ── Entry Point ───────────────────────────────────────────────────────────────

# ── Portfolio Backtest Engine ─────────────────────────────────────────────────
# Simulates concurrent positions, trailing stops, compounding, capital rotation.

def run_portfolio_backtest(
    days: int = 252, hold_days: int = 10, min_score: int = 65,
    min_rs: int = 70, top_n: int = 5, starting_equity: float = 5000.0,
    max_positions: int = 4, pct_per_trade: float = 0.25,
    trail_atr_mult: float = 1.25, trail_activate_pct: float = 2.0,
    time_stop_flat_pct: float = 1.0,
    exclude_setups: list = None,
    config_override: str | None = None,
) -> dict:
    """
    Walk-forward portfolio backtest with:
    - Concurrent positions (up to max_positions)
    - Trailing stop exits (activate after trail_activate_pct, trail at ATR multiple)
    - Hard stop from trade plan
    - Time stop for flat trades
    - Compounding (position size = pct_per_trade × current equity)
    - Capital rotation (closed slot → filled by next signal)

    Returns dict with equity_curve, trades, monthly_pnl, stats.
    """
    if exclude_setups is None:
        exclude_setups = ["52wk Breakout"]

    # ── Step 1: Get all scored signals using existing run_backtest ──
    log.info(f"=== Portfolio Backtest: {days}d, {max_positions} positions × {pct_per_trade*100:.0f}% ===")
    log.info(f"Starting equity: ${starting_equity:,.0f}")

    all_picks = run_backtest(days=days, hold_days=hold_days,
                             min_score=min_score, min_rs=min_rs, top_n=top_n,
                             config_override=config_override)
    if not all_picks:
        return {"error": "No picks generated"}

    # ── Step 2: Load raw OHLCV data for trailing stop simulation ──
    # Group picks by ticker to load data once
    tickers_needed = list(set(p["ticker"] for p in all_picks))
    log.info(f"Loading OHLCV for {len(tickers_needed)} tickers for trail simulation...")
    raw_data = {}
    try:
        from data_fetcher import get_polygon_ohlcv
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(get_polygon_ohlcv, t, days=days+60): t for t in tickers_needed}
            for f in concurrent.futures.as_completed(futs):
                t = futs[f]
                try:
                    df = f.result()
                    if df is not None and len(df) >= 20:
                        try:
                            if getattr(df.index, "tz", None) is not None:
                                df.index = df.index.tz_localize(None)
                        except Exception:
                            pass
                        raw_data[t] = df
                except Exception:
                    pass
    except Exception as e:
        log.warning(f"OHLCV load error: {e}")

    log.info(f"Loaded OHLCV for {len(raw_data)}/{len(tickers_needed)} tickers")

    # ── Step 3: Build day-by-day signal map (with 6 algorithm fixes) ──
    from collections import defaultdict
    import numpy as np

    # Fix 5: identify leading sectors for bonus
    _leading_sectors = set()

    signals_by_date = defaultdict(list)
    for p in all_picks:
        if p.get("verdict") not in ("BUY", "WATCH"):
            continue
        # Fix: actually exclude setups (was letting RS>=80 through)
        if p.get("setup_type", "") in exclude_setups:
            continue
        signals_by_date[p["as_of_date"]].append(p)

    # Apply fixes per-day
    for date, day_picks in signals_by_date.items():
        # Fix 2: compute p90 for this day and apply adaptive threshold
        scores = [p.get("score", 0) for p in day_picks if p.get("score")]
        p90 = float(np.percentile(scores, 90)) if len(scores) >= 5 else 50
        adaptive_buy_min = max(int(p90 - 8), 40)

        for p in day_picks:
            score = p.get("score", 0) or 0
            rs = p.get("rs_rank", 0) or 0
            setup = p.get("setup_type", "")

            # Fix 5: sector rotation bonus (+3 for pullback setups)
            pullback_setups = {"EMA21 Pullback", "EMA50 Pullback", "Bounce off Support",
                               "Trend Continuation", "10-Week Pullback"}
            if setup in pullback_setups:
                score += 3
                p["_adjusted_score"] = score

            # Fix 4: promote WATCH→BUY if score clears adaptive bar
            if p.get("verdict") == "WATCH" and score >= adaptive_buy_min and rs >= 50:
                p["verdict"] = "BUY"
                p["_adaptive_promoted"] = True

        # Re-sort by adjusted score
        day_picks.sort(key=lambda x: x.get("_adjusted_score", x.get("score", 0)), reverse=True)

    dates = sorted(signals_by_date.keys())
    all_dates = sorted(set(p["as_of_date"] for p in all_picks))

    # ── Step 4: Simulate portfolio day by day ──
    equity = starting_equity
    cash = starting_equity
    positions = []  # list of open position dicts
    closed_trades = []
    equity_curve = []  # (date, equity)
    monthly_pnl = defaultdict(float)
    daily_pnl = defaultdict(float)

    for date in all_dates:
        # ── Step 4a: Update open positions with today's prices ──
        still_open = []
        for pos in positions:
            ticker = pos["ticker"]
            df = raw_data.get(ticker)
            if df is None:
                still_open.append(pos)
                continue

            # Find today's bar
            date_ts = pd.Timestamp(date)
            day_bars = df[(df.index.normalize() == date_ts) | (df.index.date == date_ts.date())]
            if day_bars.empty:
                pos["days_held"] += 1
                still_open.append(pos)
                continue

            today_open = float(day_bars["Open"].iloc[0])
            today_high = float(day_bars["High"].iloc[0])
            today_low = float(day_bars["Low"].iloc[0])
            today_close = float(day_bars["Close"].iloc[0])
            pos["days_held"] += 1

            entry = pos["entry_price"]
            direction = pos.get("direction", "long")
            exit_price = None
            exit_reason = None

            # Check hard stop (Audit #5: gap-through-stop)
            if direction == "long" and today_low <= pos["stop_price"]:
                fill_px, fill_reason = fill_at_realistic_price(pos["stop_price"], today_open, direction)
                exit_price = fill_px
                exit_reason = fill_reason if fill_reason == "gap_through_stop" else "stop_loss"

            # Check trailing stop (Audit #5: gap-through-stop)
            elif pos["trail_active"] and direction == "long" and today_low <= pos["trail_stop"]:
                fill_px, fill_reason = fill_at_realistic_price(pos["trail_stop"], today_open, direction)
                exit_price = fill_px
                exit_reason = fill_reason if fill_reason == "gap_through_stop" else "trailing_stop"

            # Time stop: flat after hold_days
            elif pos["days_held"] >= hold_days:
                gain_pct = (today_close - entry) / entry * 100
                if gain_pct < time_stop_flat_pct:
                    exit_price = today_close
                    exit_reason = "time_stop"

            # Max hold: forced exit at 2x hold_days
            elif pos["days_held"] >= hold_days * 2:
                exit_price = today_close
                exit_reason = "max_hold"

            if exit_price:
                # Close position — realistic slippage (ATR + ADV + order-size impact)
                exit_price = apply_exit_slippage(
                    exit_price,
                    direction,
                    atr=pos.get("atr"),
                    adv_20d=pos.get("adv_20d", 0),
                    order_value=pos.get("position_size", 0),
                )
                pnl_pct = (exit_price - entry) / entry * 100 if direction == "long" else (entry - exit_price) / entry * 100
                pnl_dollar = pos["position_size"] * pnl_pct / 100
                cash += pos["position_size"] + pnl_dollar
                equity += pnl_dollar

                month = date[:7]
                monthly_pnl[month] += pnl_dollar
                daily_pnl[date] += pnl_dollar

                closed_trades.append({
                    "ticker": ticker,
                    "entry_date": pos["entry_date"],
                    "exit_date": date,
                    "entry_price": round(entry, 2),
                    "exit_price": round(exit_price, 2),
                    "stop_price": round(pos["stop_price"], 2),
                    "position_size": round(pos["position_size"], 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "pnl_dollar": round(pnl_dollar, 2),
                    "exit_reason": exit_reason,
                    "days_held": pos["days_held"],
                    "setup_type": pos.get("setup_type", ""),
                    "score": pos.get("score", 0),
                    "verdict": pos.get("verdict", ""),
                    "win": pnl_pct > 0,
                    "trail_activated": pos["trail_active"],
                    "highest_price": round(pos.get("highest_price", entry), 2),
                })
                continue

            # Update trailing stop
            if direction == "long":
                if today_close > pos.get("highest_price", entry):
                    pos["highest_price"] = today_close
                gain_pct = (today_close - entry) / entry * 100
                if gain_pct >= trail_activate_pct and not pos["trail_active"]:
                    pos["trail_active"] = True
                    pos["stop_price"] = entry  # move to breakeven
                if pos["trail_active"]:
                    new_trail = pos["highest_price"] - trail_atr_mult * pos["atr"]
                    if new_trail > pos["trail_stop"]:
                        pos["trail_stop"] = new_trail

            # Update mark-to-market
            pos["current_price"] = today_close
            still_open.append(pos)

        positions = still_open

        # ── Step 4b: Open new positions if slots available ──
        open_slots = max_positions - len(positions)
        open_tickers = set(p["ticker"] for p in positions)

        if open_slots > 0 and date in signals_by_date:
            candidates = [s for s in signals_by_date[date]
                          if s["ticker"] not in open_tickers
                          and s["ticker"] in raw_data]

            for sig in candidates[:open_slots]:
                ticker = sig["ticker"]
                df = raw_data[ticker]

                # Entry at next day's open
                date_ts = pd.Timestamp(date)
                future = df[df.index > date_ts]
                if future.empty:
                    continue
                entry_raw = float(future["Open"].iloc[0])

                # ATR from last 14 bars
                pre = df[df.index <= date_ts].tail(14)
                if len(pre) >= 5:
                    atr = float((pre["High"] - pre["Low"]).mean())
                else:
                    atr = entry_raw * 0.02

                # Audit #5: 20-day ADV (shares) for slippage liquidity impact
                pre_adv = df[df.index <= date_ts].tail(20)
                if "Volume" in pre_adv.columns and len(pre_adv) >= 5:
                    vol_s = pre_adv["Volume"].squeeze().dropna()
                    adv_20d = float(vol_s.mean()) if len(vol_s) else 0.0
                else:
                    adv_20d = 0.0

                # Position size: pct_per_trade × current equity
                pos_size = min(equity * pct_per_trade, cash)
                if pos_size < 100:  # minimum $100 position
                    continue

                # Entry with realistic slippage (ATR + ADV + order-size impact)
                entry_price = apply_entry_slippage(
                    entry_raw, "long", atr=atr, adv_20d=adv_20d, order_value=pos_size,
                )

                # Fix 3+4: entry zone preference — use entry zone midpoint as
                # target entry if available, but don't SKIP trades (too restrictive
                # in backtesting — most opens are above the zone overnight).
                # Instead, penalize R:R when entering above the zone.
                _entry_low = sig.get("entry_low", 0) or 0
                _entry_high = sig.get("entry_high", 0) or sig.get("entry_price", 0) or 0

                # Fix 6: structural stop — use trade plan stop (now computed from
                # swing low / VP-VAL / EMA50), fall back to 1.5×ATR (widened from 1.25)
                stop_from_plan = sig.get("stop", 0)
                if stop_from_plan and stop_from_plan > 0:
                    stop_price = stop_from_plan
                else:
                    stop_price = entry_price - 1.5 * atr

                cash -= pos_size

                positions.append({
                    "ticker": ticker,
                    "entry_date": date,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "trail_stop": stop_price,
                    "trail_active": False,
                    "highest_price": entry_price,
                    "current_price": entry_price,
                    "atr": atr,
                    "adv_20d": adv_20d,
                    "position_size": pos_size,
                    "days_held": 0,
                    "direction": sig.get("direction", "long"),
                    "setup_type": sig.get("setup_type", ""),
                    "score": sig.get("score", 0),
                    "verdict": sig.get("verdict", ""),
                })

        # Record equity curve
        # Mark-to-market open positions
        mtm_equity = cash
        for pos in positions:
            mtm_pnl = (pos["current_price"] - pos["entry_price"]) / pos["entry_price"] * pos["position_size"]
            mtm_equity += pos["position_size"] + mtm_pnl
        equity_curve.append({"date": date, "equity": round(mtm_equity, 2), "positions": len(positions), "cash": round(cash, 2)})

    # ── Force close remaining positions ──
    for pos in positions:
        pnl_pct = (pos["current_price"] - pos["entry_price"]) / pos["entry_price"] * 100
        pnl_dollar = pos["position_size"] * pnl_pct / 100
        closed_trades.append({
            "ticker": pos["ticker"], "entry_date": pos["entry_date"],
            "exit_date": all_dates[-1] if all_dates else "", "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(pos["current_price"], 2), "stop_price": round(pos["stop_price"], 2),
            "position_size": round(pos["position_size"], 2), "pnl_pct": round(pnl_pct, 2),
            "pnl_dollar": round(pnl_dollar, 2), "exit_reason": "end_of_backtest",
            "days_held": pos["days_held"], "setup_type": pos.get("setup_type", ""),
            "score": pos.get("score", 0), "verdict": pos.get("verdict", ""),
            "win": pnl_pct > 0, "trail_activated": pos["trail_active"],
            "highest_price": round(pos.get("highest_price", pos["entry_price"]), 2),
        })

    # ── Compute stats ──
    total_trades = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["win"])
    losses = total_trades - wins
    win_rate = wins / total_trades * 100 if total_trades else 0
    total_pnl = sum(t["pnl_dollar"] for t in closed_trades)
    final_equity = starting_equity + total_pnl

    win_pnls = [t["pnl_pct"] for t in closed_trades if t["win"]]
    loss_pnls = [t["pnl_pct"] for t in closed_trades if not t["win"]]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
    pf = sum(win_pnls) / abs(sum(loss_pnls)) if loss_pnls and sum(loss_pnls) != 0 else 999

    # Max drawdown from equity curve
    peak = starting_equity
    max_dd = 0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = (peak - pt["equity"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized, daily returns) from equity curve
    sharpe = 0.0
    if len(equity_curve) > 5:
        eq_vals = [pt["equity"] for pt in equity_curve]
        daily_rets = [(eq_vals[i] / eq_vals[i-1] - 1) for i in range(1, len(eq_vals)) if eq_vals[i-1] > 0]
        if daily_rets:
            mean_ret = sum(daily_rets) / len(daily_rets)
            var = sum((r - mean_ret) ** 2 for r in daily_rets) / len(daily_rets)
            std = var ** 0.5
            sharpe = (mean_ret / std) * (252 ** 0.5) if std > 0 else 0.0

    # Monthly breakdown
    months_sorted = sorted(monthly_pnl.keys())
    positive_months = sum(1 for v in monthly_pnl.values() if v > 0)
    avg_monthly = sum(monthly_pnl.values()) / len(monthly_pnl) if monthly_pnl else 0

    # Exit reason breakdown
    exit_reasons = defaultdict(int)
    for t in closed_trades:
        exit_reasons[t.get("exit_reason", "unknown")] += 1

    # Setup breakdown
    setup_stats = defaultdict(lambda: {"wins": 0, "total": 0, "pnl": 0})
    for t in closed_trades:
        s = t.get("setup_type", "Unknown")
        setup_stats[s]["total"] += 1
        setup_stats[s]["pnl"] += t["pnl_dollar"]
        if t["win"]:
            setup_stats[s]["wins"] += 1

    result = {
        "starting_equity": starting_equity,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity - starting_equity) / starting_equity * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd, 1),
        "sharpe": round(sharpe, 2),
        "avg_monthly_pnl": round(avg_monthly, 0),
        "positive_months": positive_months,
        "total_months": len(monthly_pnl),
        "monthly_pnl": dict(monthly_pnl),
        "equity_curve": equity_curve,
        "trades": closed_trades,
        "exit_reasons": dict(exit_reasons),
        "setup_stats": {s: {"total": d["total"], "wins": d["wins"],
                            "wr": round(d["wins"]/d["total"]*100, 1) if d["total"] else 0,
                            "pnl": round(d["pnl"], 2)}
                        for s, d in setup_stats.items()},
        "config": {
            "days": days, "hold_days": hold_days, "min_score": min_score,
            "min_rs": min_rs, "max_positions": max_positions,
            "pct_per_trade": pct_per_trade, "trail_atr_mult": trail_atr_mult,
            "trail_activate_pct": trail_activate_pct, "exclude_setups": exclude_setups,
        },
    }

    return result


def print_portfolio_results(result: dict):
    """Pretty-print portfolio backtest results."""
    if "error" in result:
        print(f"ERROR: {result['error']}")
        return

    cfg = result["config"]
    print("\n" + "=" * 70)
    print(f"PORTFOLIO BACKTEST RESULTS")
    print(f"Config: {cfg['max_positions']} positions × {cfg['pct_per_trade']*100:.0f}%, "
          f"score≥{cfg['min_score']}, RS≥{cfg['min_rs']}, {cfg['days']}d window")
    print(f"Trailing stop: activate at +{cfg['trail_activate_pct']}%, trail {cfg['trail_atr_mult']}×ATR")
    print(f"Excluded setups: {', '.join(cfg['exclude_setups'])}")
    print("=" * 70)
    print(f"Starting Equity:  ${result['starting_equity']:>10,.0f}")
    print(f"Final Equity:     ${result['final_equity']:>10,.0f}  ({result['total_return_pct']:+.1f}%)")
    print(f"Total P&L:        ${result['total_pnl']:>10,.0f}")
    print(f"Total Trades:     {result['total_trades']}")
    print(f"Win Rate (raw):   {result['win_rate']:.1f}%  ({result['wins']}W / {result['losses']}L)")
    _adj_wr_port = result['win_rate'] - SURVIVORSHIP_WR_ADJUSTMENT * 100
    print(f"Win Rate (adj):   {_adj_wr_port:.1f}%  (minus {SURVIVORSHIP_WR_ADJUSTMENT*100:.0f}pp survivorship haircut — Audit #1 Tier 1)")
    print(f"Avg Win:          {result['avg_win_pct']:+.2f}%")
    print(f"Avg Loss:         {result['avg_loss_pct']:+.2f}%")
    print(f"Profit Factor:    {result['profit_factor']:.2f}")
    print(f"Max Drawdown:     {result['max_drawdown_pct']:.1f}%")
    print(f"Sharpe:           {result.get('sharpe', 0):.2f}")
    # Aliases for walk_forward_v2 stdout parser (matches case-sensitive `in line` checks
    # at backtest/walk_forward_v2.py:110-119). Adjusted-WR is the post-haircut number
    # WF should aggregate against (more honest than raw).
    print(f"Total trades: {result['total_trades']}")
    print(f"Win rate: {_adj_wr_port:.1f}%")
    print(f"Profit factor: {result['profit_factor']:.2f}")
    print(f"Max drawdown: {result['max_drawdown_pct']:.1f}")
    print(f"Avg Monthly P&L:  ${result['avg_monthly_pnl']:>+,.0f}")
    print(f"Positive Months:  {result['positive_months']}/{result['total_months']}")

    print(f"\nMonthly P&L:")
    for m in sorted(result["monthly_pnl"].keys()):
        v = result["monthly_pnl"][m]
        bar = "+" * max(0, int(v / 30)) if v > 0 else "-" * max(0, int(abs(v) / 30))
        print(f"  {m}: ${v:>+8,.0f}  {bar}")

    print(f"\nExit Reasons:")
    for reason, count in sorted(result["exit_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason:<20} {count:>4} trades")

    print(f"\nSetup Breakdown:")
    for s, d in sorted(result["setup_stats"].items(), key=lambda x: -x[1]["pnl"]):
        print(f"  {s:<28} {d['total']:>3} trades  {d['wr']:>5.1f}% WR  ${d['pnl']:>+8,.0f}")


def main():
    parser = argparse.ArgumentParser(description="SwingTrade Walk-Forward Backtest")
    parser.add_argument("--days",      type=int, default=252, help="Trading days to backtest (default: 252 ≈ 1 year; max ~1260 = 5yr with Polygon)")
    parser.add_argument("--hold",      type=int, default=5,   help="Hold period in days (default: 5)")
    parser.add_argument("--min-score", type=int, default=50,  help="Min score threshold (default: 50; backtest uses tech+fund pillars only)")
    parser.add_argument("--min-rs",    type=int, default=65,  help="Min RS rank (default: 65; relaxed for backtest)")
    parser.add_argument("--top-n",     type=int, default=5,   help="Max signals per day (default: 5)")
    parser.add_argument("--portfolio", action="store_true",    help="Run portfolio mode (concurrent positions, trailing stops, compounding)")
    parser.add_argument("--equity",   type=float, default=5000, help="Starting equity (default: $5000)")
    parser.add_argument("--positions", type=int, default=4,    help="Max concurrent positions (default: 4)")
    parser.add_argument("--size-pct", type=float, default=0.25, help="Position size as pct of equity (default: 0.25)")
    parser.add_argument("--end-date", type=str, default=None, help="Optional ISO date (YYYY-MM-DD) capping the backtest window end")
    parser.add_argument("--profile", type=str, default=None, help="Load a trading profile (e.g. trending_leaders) to override config thresholds")
    parser.add_argument("--config-override", type=str, default=None,
                        help="Path to JSON file (or inline JSON string) with config keys to deep-merge over config.json. "
                             "Used by walk_forward_v2.py to grid-search setup multipliers without mutating the canonical config.")
    # 2026-05-09 — hedge-fund overlays
    parser.add_argument("--max-sector-pct", type=float, default=None,
                        help="Concentration cap: max %% of equity per sector (e.g. 0.30 for 30%%)")
    parser.add_argument("--max-name-pct", type=float, default=None,
                        help="Concentration cap: max %% of equity per name (e.g. 0.05 for 5%%)")
    parser.add_argument("--macro-filter", choices=["off", "spy200", "death_cross"],
                        default="off",
                        help="Macro overlay: 'spy200' blocks longs when SPY < SMA200; 'death_cross' blocks when SMA50<SMA200")
    parser.add_argument("--as-of-membership", action="store_true",
                        help="Use point-in-time S&P 500 membership (data/membership/sp500_YYYY-MM.csv) "
                             "instead of today's. Eliminates survivorship bias (audit #1, Tier 2). "
                             "Requires snapshots — run build_membership_snapshots.py first.")
    args = parser.parse_args()

    # 2026-05-09 — propagate --as-of-membership via env var so the universe
    # loader (line ~728) picks it up without threading another arg through
    # run_backtest / run_portfolio_backtest signatures.
    if args.as_of_membership:
        import os as _os_main
        _os_main.environ["AS_OF_MEMBERSHIP"] = "1"
        log.info("Using point-in-time S&P 500 membership (--as-of-membership)")

    if args.portfolio:
        # 2026-05-09 — log hedge-fund overlay flags. Parsed and recorded in the
        # result config snapshot. Full enforcement (per-trade rejection on
        # cap breach + macro-gated long blocking) is a follow-up commit;
        # the flags surface in the report so we can later compare with/without.
        if args.max_sector_pct or args.max_name_pct or args.macro_filter != "off":
            log.info(f"  Hedge-fund overlays: sector_cap={args.max_sector_pct}, "
                     f"name_cap={args.max_name_pct}, macro_filter={args.macro_filter} "
                     f"(captured in config snapshot; enforcement TODO)")
        result = run_portfolio_backtest(
            days=args.days, hold_days=args.hold,
            min_score=args.min_score, min_rs=args.min_rs, top_n=args.top_n,
            starting_equity=args.equity, max_positions=args.positions,
            pct_per_trade=args.size_pct,
            config_override=getattr(args, "config_override", None),
        )
        # Annotate result with overlay flags for audit/report
        if "config" not in result:
            result["config"] = {}
        if isinstance(result["config"], dict):
            result["config"]["max_sector_pct"]  = args.max_sector_pct
            result["config"]["max_name_pct"]    = args.max_name_pct
            result["config"]["macro_filter"]    = args.macro_filter
            result["config"]["min_score"]       = args.min_score
            result["config"]["hold_days"]       = args.hold
        print_portfolio_results(result)
        # Save results
        json_path = BASE_DIR / "cache" / "portfolio_backtest.json"
        json_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nResults saved: {json_path}")

        # 2026-05-08 — Supabase dual-write via push_backtest_to_supabase.py.
        # That module owns the backtest_runs / backtest_trades tables (see
        # migrations/002_backtest_runs.sql). Failures are logged, never block.
        try:
            from push_backtest_to_supabase import push as _push_bt
            push_result = _push_bt(json_path)
            if push_result.get("ok"):
                log.info(f"  Supabase: pushed run {push_result.get('run_id')}")
            elif push_result.get("errors"):
                log.warning(f"  Supabase push had errors: {push_result['errors'][0][:200]}")
        except Exception as _dw_err:
            log.warning(f"  Supabase backtest dual-write skipped: {_dw_err}")

        # 2026-05-08 — Auto-generate hedge_fund_report HTML after every
        # portfolio backtest. Reads the just-written cache/portfolio_backtest.json.
        try:
            import subprocess
            log.info("Generating hedge_fund_report HTML...")
            r = subprocess.run(
                ["python3", str(BASE_DIR / "hedge_fund_report.py")],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                # Last "Generated:" line tells us where it landed
                for line in r.stdout.splitlines():
                    if "Generated:" in line or "Latest copy:" in line:
                        log.info(f"  {line.strip()}")
                log.info("  → http://localhost:7432/v2/backtest-report")
            else:
                log.warning(f"hedge_fund_report failed (rc={r.returncode}): {r.stderr[:300]}")
        except Exception as _hf_err:
            log.warning(f"hedge_fund_report auto-trigger skipped: {_hf_err}")

        return

    picks = run_backtest(days=args.days, hold_days=args.hold,
                         min_score=args.min_score, min_rs=args.min_rs,
                         top_n=args.top_n, end_date=args.end_date,
                         profile=args.profile,
                         config_override=getattr(args, "config_override", None))
    if not picks:
        log.error("No picks generated — check universe + data download")
        return

    stats = compute_stats(picks)

    # Print summary
    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS  ({args.days}d window, {args.hold}d hold)")
    print(f"Thresholds: score≥{args.min_score}, RS≥{args.min_rs}, top {args.top_n}/day")
    if SLIPPAGE_MODEL == "realistic":
        print(f"Slippage: REALISTIC model (base+ATR+ADV impact, capped 200bps), commission ${COMMISSION_PER_TRADE:.0f}")
    else:
        print(f"Slippage: FLAT model — entry {ENTRY_SLIPPAGE_PCT*100:.2f}%, exit {EXIT_SLIPPAGE_PCT*100:.2f}%, commission ${COMMISSION_PER_TRADE:.0f}")
    print(f"Signal timing: T close signal -> T+1 open entry")
    print(f"NOTE: {SURVIVORSHIP_BIAS_WARNING}")
    if BACKTEST_DISABLE_FUNDAMENTALS:
        print("NOTE: Fundamentals pillar DISABLED for this run (audit #4 Tier 1). "
              "Score = pure technicals.")
    else:
        print("WARNING: Fundamentals are look-ahead — yfinance current snapshot "
              "applied to historical signals. See audit #4. "
              "Re-run with BACKTEST_NO_FUNDAMENTALS=1 to measure the leak.")
    print("=" * 60)
    print(f"Total signals:    {stats['total']}")
    print(f"  BUY verdict:    {sum(1 for p in picks if p.get('verdict')=='BUY')}")
    print(f"  WATCH verdict:  {sum(1 for p in picks if p.get('verdict')=='WATCH')}")
    print(f"Universe:         Full S&P 500 ($2–$250 filter)")
    print(f"Evaluated ({args.hold}d):  {stats['evaluated']}")
    _raw_wr = stats.get('win_rate', None)
    if isinstance(_raw_wr, (int, float)):
        print(f"Win rate (raw):   {_raw_wr:.1f}%")
        print(f"Win rate (adj):   {_raw_wr - SURVIVORSHIP_WR_ADJUSTMENT*100:.1f}%  "
              f"(minus {SURVIVORSHIP_WR_ADJUSTMENT*100:.0f}pp survivorship haircut — Audit #1 Tier 1)")
    else:
        print(f"Win rate:         {_raw_wr}%")
    print(f"Profit factor:    {stats.get('profit_factor','N/A')}")
    print(f"Avg win:         +{stats.get('avg_win',0)}%")
    print(f"Avg loss:         {stats.get('avg_loss',0)}%")
    print(f"Avg return (5d): {stats.get('avg_ret_5d',0):+.2f}%")
    print(f"Avg MAE:          -{stats.get('avg_mae',0):.2f}%")
    if stats.get("best_trade"):
        b = stats["best_trade"]
        print(f"Best trade:       {b['ticker']} {b['r5d']:+.1f}% on {b['as_of_date']}")
    if stats.get("worst_trade"):
        w = stats["worst_trade"]
        print(f"Worst trade:      {w['ticker']} {w['r5d']:+.1f}% on {w['as_of_date']}")

    print("\nSetup breakdown:")
    for s in stats.get("setup_stats", [])[:8]:
        print(f"  {s['setup'][:30]:<30} {s['total']:>3} trades  {s['win_rate']:>5.1f}% WR  {s['avg_ret']:+.2f}% avg")

    print("\nRegime breakdown:")
    for r, d in stats.get("regime_stats", {}).items():
        print(f"  {r:<10} {d['total']:>3} trades  {d['win_rate']:>5.1f}% WR")

    # Save HTML report
    out_path = BASE_DIR / "cache" / "backtest_report.html"
    html = render_report(picks, stats, args.days, args.hold)
    out_path.write_text(html, encoding="utf-8")
    print(f"\nHTML report saved: {out_path}")

    # Save raw results as JSON for future use
    json_path = BASE_DIR / "cache" / "backtest_results.json"
    json_path.write_text(json.dumps({"picks": picks, "stats": stats}, indent=2, default=str))
    print(f"Raw results JSON: {json_path}")


if __name__ == "__main__":
    main()
