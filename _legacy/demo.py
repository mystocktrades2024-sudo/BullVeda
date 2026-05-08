"""
Demo dashboard generator — injects realistic mock data into build_dashboard
so you can preview all tabs without running a live scan.

Usage:
    cd SwingTrade && python3 demo.py
"""
import math, time
from html_generator import build_dashboard
from pathlib import Path

def mk_ohlcv(price, n=60, volatility=0.025, trend=0.001):
    """Generate synthetic OHLCV data ending at `price`."""
    bars = []
    p = price * (1 - trend * n)
    now = int(time.time()) - n * 86400
    for i in range(n):
        r = (1 + trend + (0.5 - __import__('random').random()) * volatility)
        o = p
        p = round(p * r, 2)
        h = round(max(o, p) * (1 + abs(__import__('random').gauss(0, volatility/3))), 2)
        l = round(min(o, p) * (1 - abs(__import__('random').gauss(0, volatility/3))), 2)
        bars.append({"time": now + i*86400, "open": o, "high": h, "low": l, "close": p, "volume": int(1e6 * (1 + abs(__import__('random').gauss(0, 0.5))))})
    return bars

# ── helpers ───────────────────────────────────────────────────────────────────

def _fund_details(f, rsi, analyst_n, analyst_consensus, zacks1):
    """Generate realistic fundamentals detail strings from pillar score."""
    rev_g_val  = 122.0 if f >= 24 else 14.5 if f >= 18 else 3.2 if f >= 10 else -4.1
    rev_g_pts  = 6 if rev_g_val > 20 else 4 if rev_g_val > 10 else 2 if rev_g_val > 0 else 0
    mg_val     = 24.3 if f >= 24 else 13.8 if f >= 18 else 4.6 if f >= 10 else -2.1
    mg_pts     = 5 if mg_val > 20 else 3 if mg_val > 10 else 1 if mg_val > 0 else 0
    roe_val    = 38.5 if f >= 22 else 18.2 if f >= 16 else 7.1
    dte_val    = 12 if f >= 22 else 65 if f >= 16 else 145
    bs_pts     = min(6, (3 if roe_val > 20 else 2 if roe_val > 10 else 1) + (3 if dte_val < 50 else 2 if dte_val < 100 else 1))
    eg_val     = 45.2 if f >= 24 else 17.8 if f >= 18 else 3.1 if f >= 10 else -8.4
    eg_pts     = 5 if eg_val > 25 else 3 if eg_val > 10 else 1 if eg_val > 0 else 0
    rec_lower  = analyst_consensus.lower()
    ac_pts     = 4 if "strong" in rec_lower and "buy" in rec_lower else 3 if "buy" in rec_lower else 1 if "hold" in rec_lower else 0
    peg_val    = 0.82 if f >= 24 else 1.35 if f >= 18 else 2.1 if f >= 10 else 3.4
    peg_pts    = 4 if peg_val < 1 else 3 if peg_val < 1.5 else 1 if peg_val < 2.5 else 0
    d = {
        "revenue_growth":    f"{rev_g_val:.1f}% ({rev_g_pts}/6)",
        "profit_margin":     f"{mg_val:.1f}% ({mg_pts}/5)",
        "balance_sheet":     f"ROE={roe_val:.1f}%, D/E={dte_val:.0f} ({bs_pts}/6)",
        "earnings_growth":   f"{eg_val:.1f}% ({eg_pts}/5)",
        "analyst_consensus": f"{analyst_consensus} ({analyst_n} analysts) ({ac_pts}/4)",
        "peg_ratio":         f"{peg_val:.2f} ({peg_pts}/4)",
    }
    if zacks1:
        d["zacks_rank"] = "Rank 1 — Strong Buy (+5)"
    return d


def _tech_details(t, rsi, rvol, rs, stop, t1, price, squeeze):
    """Generate realistic technicals detail strings from pillar score."""
    if t >= 27:   trend_str, trend_pts = "strong uptrend", 10
    elif t >= 22: trend_str, trend_pts = "uptrend", 7
    elif t >= 16: trend_str, trend_pts = "above long-term trend", 4
    else:         trend_str, trend_pts = "mixed", 2
    obv_rising = rvol >= 1.5
    vol_pts = 5 if rvol >= 2.0 and obv_rising else 4 if rvol >= 1.5 and obv_rising else 2 if rvol >= 1.2 else 1
    macd_bull = rsi >= 50
    mom_pts = 5 if 50 <= rsi <= 70 and macd_bull else 4 if 45 <= rsi <= 75 and macd_bull else 2 if 40 <= rsi <= 60 else 0
    sr_pts = 5 if (price - stop) / price < 0.04 else 3 if (price - stop) / price < 0.06 else 2
    rs_pts = 5 if rs >= 80 else 3 if rs >= 65 else 1 if rs >= 50 else 0
    tv_bonus = 3 if t >= 28 else 1 if t >= 24 else 0
    d = {
        "trend":        f"{trend_str} ({trend_pts}/10)",
        "volume":       f"RVOL {rvol:.1f}x, OBV {'rising' if obv_rising else 'falling'} ({vol_pts}/5)",
        "momentum":     f"RSI {rsi:.0f}, MACD {'bullish' if macd_bull else 'bearish'} ({mom_pts}/5)",
        "sr_structure": f"Support ${stop:.2f}, Resist ${t1:.2f} ({sr_pts}/5)",
        "rel_strength": f"RS Rank {rs} {'(outperforming)' if rs > 50 else ''} ({rs_pts}/5)",
    }
    if tv_bonus != 0:
        d["tv_rating"] = f"TV {'STRONG_BUY' if tv_bonus == 3 else 'BUY'} (+{tv_bonus})"
    return d


def _opt_details(o, rr, earn_days, price, t1, stop):
    rr_pts = 10 if rr >= 5 else 8 if rr >= 4 else 7 if rr >= 3 else 4 if rr >= 2 else 2 if rr >= 1.5 else 0
    cat_pts = 4 if earn_days and 10 <= earn_days <= 30 else 2 if o >= 16 else 0
    cats = []
    if earn_days and 10 <= earn_days <= 30: cats.append(f"Earnings in {earn_days}d")
    if o >= 16: cats.append("News momentum (positive)")
    upside = (t1 - price) / price
    up_pts = 5 if upside > 0.15 else 3 if upside > 0.10 else 2 if upside > 0.05 else 0
    dn = (price - stop) / price
    return {
        "reward_risk":     f"{rr:.1f}:1 ({rr_pts}/10)",
        "catalysts":       f"{', '.join(cats) if cats else 'None'} ({cat_pts}/5)",
        "upside_scenario": f"+{upside:.1%} to resist, -{dn:.1%} to support ({up_pts}/5)",
    }


def _elliott_wave_mock(ticker, score, price, stop, t1):
    """Generate deterministic mock Elliott Wave data."""
    seed = sum(ord(c) for c in ticker)
    # High-scoring stocks are more likely in Wave 3; low scorers in corrections
    if score >= 78:
        wave_num, wave_label = 3, "Wave 3 (Impulse)"
        desc = ("Wave 2 correction complete — Wave 3 (the power wave) is starting. "
                "Strongest momentum expected. High-conviction entry zone.")
        trend, conf, bonus = "bullish", "medium", 3
    elif score >= 65:
        choices = [(1, "Wave 1 (Impulse Start)", "bullish", "medium", 2),
                   (3, "Wave 3 (Impulse)",        "bullish", "medium", 2)]
        w = choices[seed % 2]
        wave_num, wave_label, trend, conf, bonus = w
        desc = ("New uptrend beginning — early entry opportunity before Wave 3 acceleration."
                if wave_num == 1 else
                "Strong impulse wave underway. Volume and momentum expanding. Ride with trailing stop.")
    elif score >= 50:
        choices = [(2, "Wave 2 (Correction)",  "bullish", "medium",  1),
                   (4, "Wave 4 (Correction)",  "bullish", "medium",  0),
                   (5, "Wave 5 (Final Impulse)","bullish","medium",  1)]
        w = choices[seed % 3]
        wave_num, wave_label, trend, conf, bonus = w
        descs = {2: "Wave 2 pullback. Look for 38.2–61.8% Fib retracement as Wave 3 entry zone.",
                 4: "Corrective pullback. Wait for Wave 4 completion before entering Wave 5.",
                 5: "Final impulse wave — momentum may be diverging. Tighten stops."}
        desc = descs[wave_num]
    else:
        choices = [("A","Wave A (Initial Decline)", "bearish","low",  -1),
                   ("B","Wave B (Counter-trend Bounce)","bearish","medium",-1),
                   ("C","Wave C (Corrective Decline)", "bearish","medium",-2)]
        w = choices[seed % 3]
        wave_num, wave_label, trend, conf, bonus = w
        descs = {"A": "First leg of correction. Wave B bounce likely before Wave C decline.",
                 "B": "Counter-trend bounce. Likely to resume downtrend near resistance.",
                 "C": "Wave C decline underway — typically equals Wave A. Avoid longs."}
        desc = descs[wave_num]

    # Fibonacci levels (retracement from t1 down to stop)
    span = t1 - stop
    fibs = {}
    for ratio, lbl in [(0.236,"23.6%"),(0.382,"38.2%"),(0.500,"50.0%"),
                       (0.618,"61.8%"),(0.786,"78.6%"),(1.000,"100%"),
                       (1.272,"127.2%"),(1.618,"161.8%")]:
        fibs[lbl] = round(t1 - ratio * span, 2)

    nearest = min(fibs.items(), key=lambda x: abs(x[1] - price))
    return {
        "wave_number":  wave_num,
        "wave_label":   wave_label,
        "description":  desc,
        "trend":        trend,
        "confidence":   conf,
        "fib_levels":   fibs,
        "nearest_fib":  list(nearest),
        "bonus":        bonus,
        "swing_base":   round(stop, 2),
        "swing_top":    round(t1, 2),
    }


def _stocktwits_mock(ticker, score):
    """Generate deterministic mock StockTwits data from ticker + score."""
    seed = sum(ord(c) for c in ticker)
    # Sentiment correlates with score
    if score >= 75:
        bull_pct = 58 + (seed % 20)          # 58–77%
    elif score >= 60:
        bull_pct = 45 + (seed % 15)          # 45–59%
    elif score >= 45:
        bull_pct = 36 + (seed % 12)          # 36–47%
    else:
        bull_pct = 20 + (seed % 14)          # 20–33%
    bear_pct    = max(8, 30 - (seed % 17))   # 13–30%
    if bull_pct + bear_pct > 95:
        bear_pct = 95 - bull_pct
    neutral_pct = 100 - bull_pct - bear_pct
    msg_vol     = 1100 + (seed % 2500) if score >= 70 else 250 + (seed % 900)
    watchlist   = (80 + seed % 110) * 1000  if score >= 70 else (10 + seed % 45) * 1000

    bull_pool = [
        f"${ticker} breaking out on volume — targeting +12% from here. Chart is pristine.",
        f"Loading up ${ticker} calls. Institutional accumulation undeniable. 🚀",
        f"${ticker} textbook pullback to EMA20, perfect entry zone, R:R looks great",
        f"Held ${ticker} through the dip, now up 14%. Adding more on this strength.",
    ]
    bear_pool = [
        f"${ticker} fading fast. Support not holding — watching for lower lows.",
        f"Trimmed half my ${ticker} position. Macro environment too uncertain here.",
        f"${ticker} broken structure below key S/R level. Staying patient on sidelines.",
    ]
    neutral_pool = [
        f"${ticker} on my watchlist. Waiting for a clean pullback before entry.",
        f"Watching ${ticker} into close. Needs volume confirmation to get excited.",
    ]

    msgs = []
    users = ["TraderJoe_X", "SwingKing23", "MomentumMike", "ChartNinja_", "WallStrWolf"]
    hours = [1, 3, 5, 8, 12]
    if bull_pct >= 55:
        pool = bull_pool[:2] + neutral_pool[:1]
        sents = ["Bullish", "Bullish", None]
    else:
        pool = bear_pool[:2] + neutral_pool[:1]
        sents = ["Bearish", "Bearish", None]
    for i, (body, sent) in enumerate(zip(pool, sents)):
        msgs.append({"body": body, "user": users[i % 5], "sentiment": sent, "time": f"{hours[i]}h ago"})

    return {
        "bull_pct":       bull_pct,
        "bear_pct":       bear_pct,
        "neutral_pct":    neutral_pct,
        "message_volume": msg_vol,
        "watchlist_count": watchlist,
        "trending":       watchlist > 50_000,
        "messages":       msgs,
    }


def _sent_details(s, score):
    news_bias = "positive" if score >= 70 else "neutral" if score >= 50 else "negative"
    news_pts  = 5 if news_bias == "positive" else 2 if news_bias == "neutral" else 0
    ins_sent  = "bullish" if s >= 9 else "neutral"
    ins_pts   = 3 if ins_sent == "bullish" else 1
    si_pct    = 1.2 if s >= 9 else 4.5 if s >= 7 else 9.2
    si_pts    = 2 if si_pct < 3 else 1 if si_pct < 8 else 0
    return {
        "news":           f"{news_bias} ({news_pts}/5)",
        "insider":        f"{ins_sent} (buys:{3 if ins_sent=='bullish' else 0} sells:{0 if ins_sent=='bullish' else 2}) ({ins_pts}/3)",
        "short_interest": f"{si_pct:.1f}% ({si_pts}/2)",
    }


def mk(ticker, name, price, score, verdict,
       f, o, t, s,           # pillar raw scores
       entry, stop, t1, t2, rr,
       setup, sector, industry,
       rsi=55, rvol=1.6, rs=70,
       squeeze=False, zacks1=False,
       bears=None, bulls=None,
       earn_days=None, direction="long",
       analyst_consensus="Buy", analyst_n=18, analyst_pt=None, analyst_up=2, analyst_dn=0,
       iv_rank=None, beat_rate=None, weekly_bull=True, sector_etf=None,
       adx=28, cmf=0.10, mfi=58, stoch_k=38, stoch_d=32):
    seed = sum(ord(c) for c in ticker)
    risk = round(price - stop, 2) if direction == "long" else round(stop - price, 2)
    pt   = analyst_pt or round(t1 * 1.05, 2)
    upside = round((pt - price) / price * 100, 1) if pt else None
    liq_vol = round(price * 2_500_000 / 1e6, 1)  # synthetic daily dollar vol in $M
    return {
        "ticker": ticker, "name": name, "price": price, "score": score,
        "direction": direction,
        "sector": sector, "industry": industry,
        "rsi": rsi, "rvol": rvol, "atr_pct": 3.1, "rs_rank": rs,
        "squeeze": squeeze, "zacks_rank1": zacks1,
        "fundamentals": {
            "score": f,
            "bull_drivers": bulls or ["Strong revenue growth", "Expanding margins", "Analyst upgrades"],
            "bear_risks":   bears or ["Elevated P/E", "Macro headwinds"],
            "details": {
                **_fund_details(f, rsi, analyst_n, analyst_consensus, zacks1),
                "valuation": f"PEG={1.1 if f>=22 else 2.1:.2f}, FCF yield={4.2 if f>=22 else 1.8:.1f}% ({3 if f>=22 else 1}/5)",
                "fcf_yield": f"{4.2 if f>=22 else 1.8:.1f}%",
                **({"beat_rate": f"{beat_rate:.0%} ({int(beat_rate*8)}/8Q) (2/2)"} if beat_rate is not None else
                   {"beat_rate": f"{'87%' if f>=22 else '62%'} ({7 if f>=22 else 5}/8Q) ({'2' if f>=22 else '1'}/2)"}),
            },
        },
        "optionality": {
            "score": o,
            "bull_case": t2 or t1 * 1.08,
            "base_case": t1,
            "bear_case": stop,
            "details": _opt_details(o, rr, earn_days, price, t1, stop),
        },
        "technicals": {
            "score": t,
            "details": _tech_details(t, rsi, rvol, rs, stop, t1, price, squeeze),
            "indicators": {
                "ema8":  round(price*0.99, 2), "ema21": round(price*0.97, 2),
                "ema50": round(price*0.93, 2),
                "rvol": rvol, "rsi": rsi, "rs_rank": rs, "atr_pct": 3.1,
                "support": stop, "resistance": t1, "rr_ratio": rr,
                "macd_bullish": rsi >= 50, "obv_rising": rvol >= 1.3,
                "squeeze_on": squeeze, "outperforming_spy": rs > 50,
                "trend_direction": "strong uptrend" if t >= 27 else "uptrend" if t >= 22 else "mixed",
                # New indicators
                "adx": adx, "adx_trending": adx >= 25, "adx_strong_trend": adx >= 35,
                "adx_plus_di": round(adx * 0.7, 1), "adx_minus_di": round(adx * 0.3, 1),
                "cmf": cmf, "cmf_accumulating": cmf > 0.05,
                "mfi": mfi, "mfi_bullish": mfi > 50,
                "stoch_rsi_k": stoch_k, "stoch_rsi_d": stoch_d,
                "stoch_oversold": stoch_k < 20, "stoch_overbought": stoch_k > 80,
                "stoch_k_above_d": stoch_k > stoch_d,
                "bb_pct_b": 0.55 if rsi >= 50 else 0.30,
                "high_52w": round(t1 * 1.02, 2),
                "low_52w":  round(stop * 0.75, 2),
                "pct_from_52w_high": round((t1 * 1.02 - price) / (t1 * 1.02) * 100, 1),
                "near_52w_high": price >= t1 * 0.97,
                "at_52w_breakout": price >= t1 * 0.99,
                "near_52w_low": False,
                "stage2": score >= 75 and price >= t1 * 0.97,
                "sar": round(stop * 0.99, 2), "sar_bullish": rsi >= 45, "sar_flipped": False,
                "weekly_ema_bullish": weekly_bull, "weekly_ema_bearish": not weekly_bull and t < 20,
                "weekly_ema8": round(price * 0.96, 2), "weekly_ema21": round(price * 0.93, 2),
                "weekly_aligned": weekly_bull,
                "sector_etf": sector_etf,
                "sector_outperforming": True if sector_etf in ("XLK","XLV","XLI") else False,
                "sector_vs_spy_pct": 3.2 if sector_etf in ("XLK","XLV","XLI") else -1.5,
                "sector_rank": 2 if sector_etf in ("XLK","XLV","XLI") else 8,
            },
        },
        "sentiment": {
            "score": s,
            "details": _sent_details(s, score),
        },
        "decision": {
            "verdict": verdict,
            "reason": (
                f"Score {score}/100, R:R {rr:.1f}:1 — {setup.lower()}" if verdict == "BUY"
                else f"Score {score}/100 — weak structure, below key MAs"
            ),
        },
        "trade_plan": {
            "setup_type":   setup,
            "entry_zone":   f"${price - 0.5:.2f}–${price + 0.8:.2f}",
            "entry_low":    round(price - 0.5, 2),
            "entry_high":   round(price + 0.8, 2),
            "stop":         stop,
            "target1":      t1,
            "target2":      t2,
            "rr_ratio":     rr,
            "risk_per_share": risk,
            "beta":         round(0.7 + (seed % 18) / 10, 2),
            "beta_adj_multiplier": round(1.0 / max(0.7 + (seed % 18) / 10, 0.3), 2),
            "price_tier":   ("$5–$50" if price <= 50 else "$50–$100" if price <= 100 else ">$100"),
        },
        "price_tier": ("$5–$50" if price <= 50 else "$50–$100" if price <= 100 else ">$100"),
        "beta": round(0.7 + (seed % 18) / 10, 2),
        "earnings": {
            "earnings_date": None,
            "days_to_earnings": earn_days,
            "earnings_risk": earn_days is not None and earn_days <= 5,
        },
        "analyst": {
            "consensus": analyst_consensus, "total_analysts": analyst_n,
            "target_mean": pt, "target_high": round(pt*1.12,2), "target_low": round(pt*0.88,2),
            "upside_pct": upside,
            "strong_buy": max(0, analyst_n - analyst_n//3 - 2),
            "buy": analyst_n//3, "hold": 2, "sell": analyst_dn, "strong_sell": 0,
            "recent_upgrades": analyst_up, "recent_downgrades": analyst_dn,
            "latest_actions": [
                {"firm": "Morgan Stanley", "to": "Overweight", "from": "Equal Weight", "action": "up"},
                {"firm": "Goldman Sachs",  "to": "Buy",        "from": "Neutral",      "action": "up"},
            ],
        },
        "tv_rating": {
            "recommendation": "STRONG_BUY" if score >= 78 else "BUY" if score >= 65 else "NEUTRAL",
            "rec_value": 0.72 if score >= 78 else 0.3,
            "rsi": rsi, "ema20": round(price*0.97,2), "ema50": round(price*0.93,2), "ema200": round(price*0.85,2),
        },
        "ohlcv": mk_ohlcv(price, volatility=0.028 if score >= 75 else 0.02,
                           trend=0.004 if score >= 75 else -0.002),
        "news_data": {
            "bias": "positive" if score >= 70 else "neutral",
            "headlines": [
                f"{ticker}: Strong earnings beat, raised guidance for FY2026",
                f"Wall Street upgrades {ticker} on improving margin trajectory",
                f"{name} reports record revenue in latest quarter",
            ] if score >= 70 else [
                f"{ticker} faces headwinds from slowing demand",
                f"Analysts cautious on {ticker} ahead of upcoming earnings",
            ],
        },
        "stocktwits":   _stocktwits_mock(ticker, score),
        "elliott_wave": _elliott_wave_mock(ticker, score, price, stop, t1),
        "options_data": {
            "iv_rank":      iv_rank if iv_rank is not None else (15 + (seed % 60)),
            "iv_pct_label": "Low (cheap options)" if (iv_rank or 30) < 30 else "Normal",
            "pc_ratio":     round(0.5 + (seed % 100) / 200, 2),
            "uoa":          score >= 78 and seed % 3 == 0,
            "iv_current":   round(20 + (seed % 40), 1),
            "gamma_wall":   round(t1 * 1.01, 2) if score >= 75 else None,
            "error":        None,
        },
        "vwap": {
            "vwap_20d":        round(price * (0.97 if score >= 70 else 1.02), 2),
            "avwap_swing_low": round(price * (0.94 if score >= 70 else 1.05), 2),
            "above_vwap":      score >= 70,
            "above_avwap":     score >= 75,
        },
        "patterns": {
            "primary":    ("bull_flag" if score >= 78 else
                           "ascending_triangle" if score >= 72 else
                           "cup_and_handle" if score >= 68 else
                           "none"),
            "detected":   (["bull_flag", "ascending_triangle"] if score >= 78 else
                           ["ascending_triangle"] if score >= 72 else
                           ["cup_and_handle"] if score >= 68 else []),
            "confidence": (4 if score >= 82 else 3 if score >= 75 else 2 if score >= 68 else 0),
        },
        "extra_fund": {
            "ev_ebitda":          round(8.5 + (seed % 30), 1) if score >= 70 else round(35 + (seed % 20), 1),
            "p_fcf":              round(12 + (seed % 20), 1) if score >= 70 else round(45 + (seed % 30), 1),
            "institutional_pct":  round(65 + (seed % 25), 1) if score >= 70 else round(20 + (seed % 30), 1),
            "buyback_yield":      round(1.5 + (seed % 20) / 10, 1) if score >= 70 else round(0.2, 1),
            "estimate_revision":  ("up_strong" if score >= 82 else
                                   "up" if score >= 72 else
                                   "flat" if score >= 60 else "down"),
            "error": None,
        },
        "gate": {
            "passed": True, "reasons": [],
            "daily_dollar_vol": liq_vol, "weak_regime": False,
            "drawdown_from_ath": round((1 - price / (t1 * 1.03)) * 100, 1),
            "gap_risk": {
                "level":          "low" if score >= 75 else "medium" if score >= 60 else "high",
                "large_gaps_20d": 1 if score >= 75 else 3 if score >= 60 else 6,
                "avg_gap_pct":    0.008 if score >= 75 else 0.025,
                "atr_pct":        3.1,
            },
        },
    }


# ── BUY candidates ─────────────────────────────────────────────────────────────

buy_candidates = [
    mk("NVDA", "NVIDIA Corporation",    127.45, 86, "BUY",
       f=25, o=18, t=27, s=9,
       entry=126.0, stop=120.50, t1=139.00, t2=152.00, rr=3.8,
       setup="Stage 2 Breakout (52w high)", sector="Technology", industry="Semiconductors",
       rsi=62, rvol=2.8, rs=91, squeeze=True, zacks1=True,
       bulls=["Revenue +122% YoY", "Zacks Rank #1 (Strong Buy)", "AI data-centre demand surge"],
       bears=["P/E 55x — rich valuation"],
       analyst_consensus="Strong Buy", analyst_n=42, analyst_pt=148.00, analyst_up=5, analyst_dn=0,
       iv_rank=22, beat_rate=0.875, weekly_bull=True, sector_etf="XLK",
       adx=38, cmf=0.18, mfi=65, stoch_k=42, stoch_d=35),

    mk("META", "Meta Platforms Inc",     82.30, 82, "BUY",
       f=23, o=17, t=26, s=9,
       entry=81.5, stop=77.00, t1=92.00, t2=100.00, rr=3.5,
       setup="Pullback to EMA21", sector="Communication Services", industry="Internet Content",
       rsi=48, rvol=1.9, rs=84, squeeze=False, zacks1=True,
       bulls=["Reels monetisation accelerating", "Cost-cutting boosting EPS", "Zacks Rank #1"],
       bears=["Regulatory overhang in EU"],
       analyst_consensus="Strong Buy", analyst_n=38, analyst_pt=98.00, analyst_up=4, analyst_dn=1,
       iv_rank=28, beat_rate=0.75, weekly_bull=True, sector_etf="XLC",
       adx=31, cmf=0.12, mfi=58, stoch_k=35, stoch_d=30),

    mk("LLY",  "Eli Lilly and Company",  95.10, 80, "BUY",
       f=24, o=16, t=24, s=8,
       entry=94.0, stop=89.50, t1=104.00, t2=113.00, rr=3.3,
       setup="Near 52w High — Momentum", sector="Healthcare", industry="Drug Manufacturers",
       rsi=55, rvol=1.6, rs=88, squeeze=False, zacks1=False,
       bulls=["GLP-1 pipeline dominant", "Strong earnings beat streak", "High RS vs SPY"],
       bears=["Pricing pressure risk from IRA"],
       analyst_consensus="Buy", analyst_n=24, analyst_pt=107.00, analyst_up=3, analyst_dn=0,
       iv_rank=18, beat_rate=1.0, weekly_bull=True, sector_etf="XLV",
       adx=29, cmf=0.14, mfi=62, stoch_k=48, stoch_d=41),

    mk("DECK", "Deckers Outdoor Corp",   78.90, 78, "BUY",
       f=21, o=16, t=26, s=8,
       entry=78.0, stop=73.80, t1=87.00, t2=95.00, rr=3.1,
       setup="Squeeze Breakout", sector="Consumer Cyclical", industry="Footwear",
       rsi=58, rvol=2.1, rs=79, squeeze=True,
       bulls=["UGG + HOKA dual growth", "Margin expansion", "TTM Squeeze fired"],
       bears=["Consumer discretionary risk"],
       analyst_consensus="Buy", analyst_n=14, analyst_pt=91.00, analyst_up=2, analyst_dn=0,
       iv_rank=35, beat_rate=0.875, weekly_bull=True, sector_etf="XLY",
       adx=33, cmf=0.09, mfi=60, stoch_k=55, stoch_d=48),

    mk("AXON", "Axon Enterprise Inc",    88.20, 77, "BUY",
       f=20, o=16, t=25, s=7,
       entry=87.5, stop=83.00, t1=97.00, t2=105.00, rr=3.0,
       setup="Trend Continuation", sector="Industrials", industry="Security & Protection",
       rsi=61, rvol=1.7, rs=76,
       bulls=["Taser + software bundle growth", "Government contract momentum"],
       bears=["High valuation", "Earnings in 9 days"], earn_days=9,
       analyst_consensus="Buy", analyst_n=16, analyst_pt=102.00, analyst_up=3, analyst_dn=1,
       iv_rank=42, beat_rate=0.75, weekly_bull=True, sector_etf="XLI",
       adx=27, cmf=0.11, mfi=56, stoch_k=52, stoch_d=44),
]

# ── SELL / EXIT candidates ─────────────────────────────────────────────────────

sell_candidates = [
    mk("INTC", "Intel Corporation",      18.45, 38, "AVOID",
       f=8, o=6, t=11, s=7,
       entry=18.9, stop=20.50, t1=16.00, t2=14.00, rr=1.2,
       setup="Distribution", sector="Technology", industry="Semiconductors",
       rsi=36, rvol=1.1, rs=12,
       bears=["Market share loss to AMD/NVDA", "Below SMA50 and SMA200", "Earnings cut risk"]),

    mk("PFE",  "Pfizer Inc",             26.80, 36, "AVOID",
       f=9, o=6, t=10, s=6,
       entry=27.2, stop=29.50, t1=23.00, t2=21.00, rr=1.5,
       setup="Distribution", sector="Healthcare", industry="Drug Manufacturers",
       rsi=42, rvol=0.9, rs=18,
       bears=["COVID revenue normalisation", "Pipeline struggles post-Paxlovid", "Below all major MAs"]),

    mk("PARA", "Paramount Global",       12.10, 34, "AVOID",
       f=7, o=5, t=12, s=6,
       entry=12.5, stop=13.80, t1=10.00, t2=8.50, rr=1.1,
       setup="Downtrend", sector="Communication Services", industry="Entertainment",
       rsi=38, rvol=0.8, rs=8,
       bears=["Streaming losses ongoing", "Merger uncertainty", "Dividend cut risk"]),

    mk("FMC",  "FMC Corporation",        51.20, 37, "AVOID",
       f=10, o=7, t=11, s=5,
       entry=51.8, stop=55.50, t1=46.00, t2=42.00, rr=1.3,
       setup="Failed Breakout", sector="Basic Materials", industry="Agricultural Inputs",
       rsi=44, rvol=1.0, rs=22,
       bears=["Channel inventory glut", "FX headwinds in LatAm", "Guidance cut Q3"]),

    mk("DXC",  "DXC Technology",         19.70, 35, "AVOID",
       f=8, o=5, t=11, s=7,
       entry=20.0, stop=22.00, t1=17.00, t2=15.00, rr=1.2,
       setup="Deterioration", sector="Technology", industry="IT Services",
       rsi=40, rvol=0.9, rs=15,
       bears=["Revenue declining YoY", "Multiple contract losses", "Management turnover"]),
]

# ── Watch list ──────────────────────────────────────────────────────────────────

watch_list = [
    mk("CRWD", "CrowdStrike Holdings",   97.50, 71, "WATCH",
       f=19, o=14, t=22, s=7,
       entry=97.0, stop=91.50, t1=107.00, t2=115.00, rr=2.8,
       setup="Consolidating at Resistance", sector="Technology", industry="Software",
       rsi=57, rvol=1.3, rs=72,
       bulls=["Best-of-breed endpoint security", "ARR growth 35%+"],
       bears=["Needs volume surge to confirm breakout"]),

    mk("GLD",  "SPDR Gold Shares ETF",   58.40, 68, "WATCH",
       f=16, o=13, t=22, s=8,
       entry=58.0, stop=55.20, t1=63.00, t2=67.00, rr=2.6,
       setup="Safe Haven Momentum", sector="Commodity", industry="Precious Metals",
       rsi=64, rvol=1.4, rs=85,
       bulls=["Geopolitical safe haven bid", "Central bank buying"],
       bears=["Overbought short-term, awaiting pullback"]),
]

# ── Industries ──────────────────────────────────────────────────────────────────

industries = [
    {"industry": "Semiconductors",             "avg_score": 74, "count": 8,  "tickers": ["NVDA","AMD","AVGO","QCOM","MRVL","MU","AMAT","KLAC"]},
    {"industry": "Software — Infrastructure",  "avg_score": 68, "count": 12, "tickers": ["CRWD","PANW","ZS","FTNT","NET","OKTA","DDOG","SNOW","MDB","CFLT"]},
    {"industry": "Drug Manufacturers",         "avg_score": 65, "count": 6,  "tickers": ["LLY","NVO","ABBV","BMY","MRK","AMGN"]},
    {"industry": "Aerospace & Defense",        "avg_score": 62, "count": 5,  "tickers": ["LMT","RTX","NOC","GD","AXON"]},
    {"industry": "Internet Content",           "avg_score": 61, "count": 4,  "tickers": ["META","GOOGL","SNAP","PINS"]},
    {"industry": "Footwear",                   "avg_score": 59, "count": 3,  "tickers": ["DECK","NKE","ONON"]},
    {"industry": "Precious Metals",            "avg_score": 57, "count": 4,  "tickers": ["GLD","GDX","NEM","GOLD"]},
    {"industry": "Financial Data & Exchanges", "avg_score": 55, "count": 3,  "tickers": ["MSCI","ICE","CME"]},
    {"industry": "Consumer Electronics",       "avg_score": 52, "count": 4,  "tickers": ["AAPL","SNE","SONO","HPQ"]},
    {"industry": "Electric Utilities",         "avg_score": 48, "count": 5,  "tickers": ["NEE","SO","DUK","AEP","EXC"]},
    {"industry": "IT Services",                "avg_score": 42, "count": 6,  "tickers": ["DXC","IBM","CTSH","ACN","INFY","WIT"]},
    {"industry": "Drug Manufacturers — Generics","avg_score": 38, "count": 3,"tickers": ["PFE","MYL","TEVA"]},
]

# ── All scored (combine buy + watch + sell + extras) ──────────────────────────

extra_scores = [
    # ── $50–$100 range ──
    mk("AMD",   "Advanced Micro Devices", 68.20, 64, "WATCH",  f=17,o=13,t=20,s=7, entry=67.5, stop=63.0, t1=75.0, t2=82.0, rr=2.5, setup="Testing Resistance",    sector="Technology",            industry="Semiconductors",  rsi=53, rvol=1.3, rs=74),
    mk("AAPL",  "Apple Inc",              53.10, 52, "AVOID",  f=14,o=10,t=16,s=6, entry=53.5, stop=56.0, t1=50.0, t2=47.0, rr=1.2, setup="Distribution",          sector="Technology",            industry="Consumer Electronics", rsi=45, rvol=0.8, rs=42),
    mk("TSLA",  "Tesla Inc",              62.80, 47, "AVOID",  f=11,o=9, t=14,s=7, entry=63.0, stop=67.5, t1=57.0, t2=53.0, rr=1.3, setup="Bearish Continuation",  sector="Consumer Cyclical",     industry="Auto",            rsi=38, rvol=1.1, rs=28),
    mk("AMZN",  "Amazon.com Inc",         88.40, 60, "WATCH",  f=16,o=12,t=19,s=7, entry=88.0, stop=84.0, t1=96.0, t2=103.0,rr=2.4, setup="Accumulation",          sector="Consumer Cyclical",     industry="Internet Retail",  rsi=51, rvol=1.1, rs=66),
    mk("GOOGL", "Alphabet Inc",           78.60, 57, "WATCH",  f=15,o=12,t=17,s=6, entry=78.0, stop=74.0, t1=86.0, t2=93.0, rr=2.2, setup="Range Bound",           sector="Communication Services",industry="Internet Content",  rsi=49, rvol=1.0, rs=58),
    # ── $5–$50 range — WATCH/BUY candidates ──
    mk("ON",    "ON Semiconductor",       44.10, 76, "BUY",    f=19,o=16,t=23,s=8, entry=43.5, stop=40.5, t1=53.5, t2=60.0, rr=3.1, setup="Pullback to EMA21",     sector="Technology",            industry="Semiconductors",  rsi=52, rvol=1.6, rs=71, zacks1=True, iv_rank=28),
    mk("FANG",  "Diamondback Energy",     45.80, 74, "WATCH",  f=19,o=15,t=22,s=7, entry=45.0, stop=41.5, t1=54.0, t2=61.0, rr=2.9, setup="Near 52w High",         sector="Energy",                industry="Oil & Gas E&P",   rsi=57, rvol=1.5, rs=78),
    mk("STLD",  "Steel Dynamics",         33.20, 72, "WATCH",  f=18,o=14,t=22,s=7, entry=32.8, stop=30.0, t1=39.5, t2=45.0, rr=2.8, setup="Squeeze Breakout",      sector="Basic Materials",        industry="Steel",            rsi=54, rvol=1.7, rs=69, squeeze=True),
    mk("EXAS",  "Exact Sciences",         28.40, 70, "WATCH",  f=17,o=14,t=21,s=7, entry=28.0, stop=25.5, t1=34.0, t2=39.0, rr=2.8, setup="Consolidation",         sector="Healthcare",            industry="Diagnostics",      rsi=50, rvol=1.4, rs=66),
    mk("HWM",   "Howmet Aerospace",       38.60, 69, "WATCH",  f=17,o=13,t=21,s=7, entry=38.0, stop=35.0, t1=44.5, t2=50.0, rr=2.5, setup="Trend Continuation",    sector="Industrials",           industry="Aerospace",        rsi=55, rvol=1.3, rs=65),
    # ── >$100 range — WATCH candidates ──
    mk("MSFT",  "Microsoft Corp",        148.20, 79, "BUY",    f=23,o=17,t=24,s=8, entry=147.0,stop=139.0,t1=169.0,t2=185.0,rr=3.1, setup="Stage 2 Breakout",      sector="Technology",            industry="Software",         rsi=60, rvol=1.9, rs=85, zacks1=True, iv_rank=20),
    mk("COST",  "Costco Wholesale",      195.80, 77, "BUY",    f=22,o=16,t=23,s=8, entry=194.0,stop=184.0,t1=222.0,t2=242.0,rr=3.0, setup="Near 52w High",         sector="Consumer Defensive",    industry="Discount Stores",  rsi=58, rvol=1.6, rs=82),
    mk("UNH",   "UnitedHealth Group",    117.40, 73, "WATCH",  f=21,o=15,t=22,s=8, entry=116.0,stop=108.0,t1=133.0,t2=148.0,rr=2.7, setup="Pullback to EMA50",     sector="Healthcare",            industry="Health Insurance",  rsi=48, rvol=1.3, rs=70),
    mk("V",     "Visa Inc",              141.60, 71, "WATCH",  f=20,o=14,t=22,s=7, entry=140.0,stop=132.5,t1=158.0,t2=172.0,rr=2.6, setup="Accumulation",          sector="Financial Services",    industry="Credit Services",  rsi=51, rvol=1.2, rs=67),
    mk("MA",    "Mastercard Inc",        138.90, 70, "WATCH",  f=20,o=14,t=22,s=7, entry=137.5,stop=130.0,t1=155.0,t2=170.0,rr=2.5, setup="Range Bound",           sector="Financial Services",    industry="Credit Services",  rsi=50, rvol=1.1, rs=65),
]

all_scored = buy_candidates + watch_list + extra_scores + sell_candidates
all_scored.sort(key=lambda x: x["score"], reverse=True)

# ── Killed (pre-trade gate failures) ─────────────────────────────────────────

killed = [
    {**mk("F",    "Ford Motor Company",    12.40, 31, "AVOID",  f=7,o=5,t=10,s=5, entry=12.5,stop=14.0,t1=11.0,t2=9.5, rr=1.0, setup="Downtrend", sector="Consumer Cyclical", industry="Auto", rsi=38, rvol=0.7, rs=11),
     "gate": {"passed": False, "reasons": ["Earnings in 3 days — blackout window", "Avg daily volume $8.1M below $10M minimum"]}},
    {**mk("GME",  "GameStop Corp",          18.20, 22, "AVOID",  f=4,o=4,t=7, s=5, entry=18.5,stop=21.0,t1=15.5,t2=13.0,rr=0.9, setup="Meme Volatility", sector="Consumer Cyclical", industry="Specialty Retail", rsi=72, rvol=4.2, rs=5),
     "gate": {"passed": False, "reasons": ["RSI 72 — overbought", "Meme stock — no fundamental support"]}},
]

# ── Zacks #1 tab ──────────────────────────────────────────────────────────────

zacks_tab = [r for r in all_scored if r.get("zacks_rank1")]
# add a few extra Zacks #1 that scored lower
for extra_zk in [
    mk("ON",   "ON Semiconductor",      44.10, 63, "WATCH", f=17,o=12,t=20,s=7, entry=43.5,stop=40.0,t1=50.0,t2=55.0,rr=2.7, setup="Consolidation", sector="Technology", industry="Semiconductors", rsi=54, rvol=1.4, rs=68, zacks1=True),
    mk("SMCI", "Super Micro Computer",  38.70, 58, "WATCH", f=16,o=11,t=18,s=6, entry=38.0,stop=35.0,t1=43.0,t2=47.0,rr=2.1, setup="Recovery", sector="Technology", industry="Computer Hardware", rsi=50, rvol=1.2, rs=62, zacks1=True),
]:
    zacks_tab.append(extra_zk)
zacks_tab.sort(key=lambda x: x["score"], reverse=True)

# ── Ultimate data ──────────────────────────────────────────────────────────────

ultimate_data = {
    "top_movers_30d": [
        {"company": "NVIDIA Corp",         "ticker": "NVDA", "type": "Long", "date_added": "1/12/26", "price_add": "$89.40",  "price_last": "$127.45", "pct_chg": "+42.6%", "service": "ZACKS Ultimate"},
        {"company": "Eli Lilly Co",        "ticker": "LLY",  "type": "Long", "date_added": "2/03/26", "price_add": "$71.20",  "price_last": "$95.10",  "pct_chg": "+33.6%", "service": "ZACKS Ultimate"},
        {"company": "Axon Enterprise",     "ticker": "AXON", "type": "Long", "date_added": "1/28/26", "price_add": "$67.80",  "price_last": "$88.20",  "pct_chg": "+30.1%", "service": "ZACKS Ultimate"},
        {"company": "Meta Platforms",      "ticker": "META", "type": "Long", "date_added": "2/14/26", "price_add": "$66.00",  "price_last": "$82.30",  "pct_chg": "+24.7%", "service": "ZACKS Ultimate"},
        {"company": "Deckers Outdoor",     "ticker": "DECK", "type": "Long", "date_added": "3/01/26", "price_add": "$67.50",  "price_last": "$78.90",  "pct_chg": "+16.9%", "service": "ZACKS Ultimate"},
        {"company": "CrowdStrike Holdings","ticker": "CRWD", "type": "Long", "date_added": "2/20/26", "price_add": "$85.40",  "price_last": "$97.50",  "pct_chg": "+14.2%", "service": "ZACKS Ultimate"},
        {"company": "ON Semiconductor",    "ticker": "ON",   "type": "Long", "date_added": "3/10/26", "price_add": "$39.10",  "price_last": "$44.10",  "pct_chg": "+12.8%", "service": "ZACKS Premium"},
        {"company": "SPDR Gold Shares",    "ticker": "GLD",  "type": "Long", "date_added": "1/05/26", "price_add": "$52.30",  "price_last": "$58.40",  "pct_chg": "+11.7%", "service": "ZACKS Ultimate"},
        {"company": "Intel Corporation",   "ticker": "INTC", "type": "Short","date_added": "1/20/26", "price_add": "$24.50",  "price_last": "$18.45",  "pct_chg": "+24.7%", "service": "ZACKS Premium"},
        {"company": "Pfizer Inc",          "ticker": "PFE",  "type": "Short","date_added": "2/01/26", "price_add": "$32.10",  "price_last": "$26.80",  "pct_chg": "+16.5%", "service": "ZACKS Ultimate"},
    ],
    "all_trades": [
        {"company": "NVIDIA Corp",         "ticker": "NVDA", "type": "Long", "date_added": "1/12/26", "price_add": "$89.40",  "price_last": "$127.45", "pct_chg": "+42.6%", "service": "ZACKS Ultimate"},
        {"company": "Tesla Inc",           "ticker": "TSLA", "type": "Short","date_added": "11/14/25","price_add": "$95.00",  "price_last": "$62.80",  "pct_chg": "+33.9%", "service": "ZACKS Premium"},
        {"company": "Eli Lilly Co",        "ticker": "LLY",  "type": "Long", "date_added": "2/03/26", "price_add": "$71.20",  "price_last": "$95.10",  "pct_chg": "+33.6%", "service": "ZACKS Ultimate"},
        {"company": "Intel Corporation",   "ticker": "INTC", "type": "Short","date_added": "1/20/26", "price_add": "$24.50",  "price_last": "$18.45",  "pct_chg": "+24.7%", "service": "ZACKS Premium"},
        {"company": "Meta Platforms",      "ticker": "META", "type": "Long", "date_added": "2/14/26", "price_add": "$66.00",  "price_last": "$82.30",  "pct_chg": "+24.7%", "service": "ZACKS Ultimate"},
        {"company": "Pfizer Inc",          "ticker": "PFE",  "type": "Short","date_added": "2/01/26", "price_add": "$32.10",  "price_last": "$26.80",  "pct_chg": "+16.5%", "service": "ZACKS Ultimate"},
        {"company": "Deckers Outdoor",     "ticker": "DECK", "type": "Long", "date_added": "3/01/26", "price_add": "$67.50",  "price_last": "$78.90",  "pct_chg": "+16.9%", "service": "ZACKS Ultimate"},
        {"company": "CrowdStrike Holdings","ticker": "CRWD", "type": "Long", "date_added": "2/20/26", "price_add": "$85.40",  "price_last": "$97.50",  "pct_chg": "+14.2%", "service": "ZACKS Ultimate"},
        {"company": "ON Semiconductor",    "ticker": "ON",   "type": "Long", "date_added": "3/10/26", "price_add": "$39.10",  "price_last": "$44.10",  "pct_chg": "+12.8%", "service": "ZACKS Premium"},
        {"company": "SPDR Gold Shares",    "ticker": "GLD",  "type": "Long", "date_added": "1/05/26", "price_add": "$52.30",  "price_last": "$58.40",  "pct_chg": "+11.7%", "service": "ZACKS Ultimate"},
        {"company": "Axon Enterprise",     "ticker": "AXON", "type": "Long", "date_added": "1/28/26", "price_add": "$67.80",  "price_last": "$88.20",  "pct_chg": "+30.1%", "service": "ZACKS Ultimate"},
        {"company": "Amazon.com Inc",      "ticker": "AMZN", "type": "Long", "date_added": "3/15/26", "price_add": "$83.00",  "price_last": "$88.40",  "pct_chg": "+6.5%",  "service": "ZACKS Premium"},
        {"company": "Alphabet Inc",        "ticker": "GOOGL","type": "Long", "date_added": "3/20/26", "price_add": "$75.00",  "price_last": "$78.60",  "pct_chg": "+4.8%",  "service": "ZACKS Ultimate"},
        {"company": "Paramount Global",    "ticker": "PARA", "type": "Short","date_added": "2/10/26", "price_add": "$16.50",  "price_last": "$12.10",  "pct_chg": "+26.7%", "service": "ZACKS Premium"},
        {"company": "DXC Technology",      "ticker": "DXC",  "type": "Short","date_added": "2/25/26", "price_add": "$25.80",  "price_last": "$19.70",  "pct_chg": "+23.6%", "service": "ZACKS Premium"},
    ],
    "commentary": [
        {
            "title": "Bear Market Playbook: How to Navigate April 2026",
            "date": "4/02/26",
            "excerpt": (
                "With SPY now 14% off its all-time high and trading below both the 50-day EMA and 200-day SMA, "
                "our regime filter has flipped to BEAR. In bear markets, we raise our score threshold from 70 to 75 "
                "and require R:R of at least 3:1 before initiating new longs. "
                "Current focus: defensive names in Healthcare and Gold, with selective short setups in Technology. "
                "Patience is a position — cash is a valid allocation when the market lacks conviction."
            ),
        },
        {
            "title": "NVDA Deep Dive: AI Tailwinds vs. Tariff Headwinds",
            "date": "3/28/26",
            "excerpt": (
                "NVIDIA remains the highest-scoring name in our universe at 86/100. "
                "The AI infrastructure buildout is accelerating with Blackwell production ramping ahead of schedule. "
                "Key risk: new tariffs on semiconductor imports from Taiwan could pressure Q2 margins by 200–300bps. "
                "Our base case still calls for $139 with a stop at $120.50, giving a 3.8:1 reward-to-risk."
            ),
        },
        {
            "title": "Gold Breakout: Is This Time Different?",
            "date": "3/25/26",
            "excerpt": (
                "GLD has cleared $57.50 resistance on above-average volume for three consecutive sessions. "
                "Central bank demand from China and India continues to underpin the physical market. "
                "Geopolitical premium is being priced in as macro uncertainty rises. "
                "Our target is $63, stop $55.20."
            ),
        },
    ],
    "confidential_commentary": [
        {
            "title": "The One Trade We're Most Excited About Heading Into Q2",
            "date": "4/01/26",
            "excerpt": (
                "Our Confidential service focuses on high-conviction setups the broader market hasn't priced in. "
                "This week's top pick: NVDA's Blackwell GPU production ramp is running 6 weeks ahead of schedule — "
                "a detail confirmed in our proprietary channel checks. Data-centre orders for H200 and B100 are "
                "accelerating, with three hyperscalers expanding capex guidance. We see $139 by end of Q2. "
                "Position sizing: 8% of portfolio, stop at $120.50 on a daily close basis."
            ),
        },
        {
            "title": "Macro Alert: Tariff Shock + Credit Spread Widening",
            "date": "3/31/26",
            "excerpt": (
                "Two macro signals are flashing caution simultaneously. "
                "1) The new 25% tariff on semiconductor and pharmaceutical imports effective April 5 adds meaningful "
                "cost pressure across two of our highest-weight sectors. "
                "2) Investment-grade credit spreads widened 18bps in March — historically a 6-week leading indicator "
                "for equity drawdowns. We are reducing gross exposure from 85% to 65% and building a short basket "
                "in the most vulnerable names: INTC, PFE, PARA."
            ),
        },
        {
            "title": "Earnings Season Preview: Who's Built to Beat in This Environment",
            "date": "3/28/26",
            "excerpt": (
                "With Q1 earnings starting in 10 days, we have screened our universe for companies with "
                "(a) low tariff exposure, (b) pricing power, and (c) a track record of EPS beats in uncertain macro. "
                "Top names: LLY (domestic revenue >80%), AXON (government contracts locked in), "
                "GLD (macro hedge, not correlated to earnings). "
                "Names to avoid into prints: TSLA, INTC, PFE — all face guidance risk."
            ),
        },
    ],
    "error": None,
    "confidential_overview": {
        "description": (
            "Zacks Confidential delivers our highest-conviction, non-consensus trade ideas — "
            "institutional-grade picks before Wall Street catches on. Updated daily with entry, stop, and target. "
            "Lifetime track record: +847% vs S&P 500 +312% since inception."
        ),
        "stats": {
            "Total Return":     "+847%",
            "Win Rate":         "74%",
            "Avg Gain/Win":     "+22.3%",
            "Avg Loss":         "-5.1%",
            "Profit Factor":    "4.2×",
            "Open Positions":   "8",
            "Closed YTD":       "31",
            "Streak (current)": "4 wins",
        },
        "positions": [
            {"ticker": "NVDA", "company": "NVIDIA Corporation",    "direction": "Long",  "date_added": "1/12/26", "buy_price": "$89.40",  "current": "$127.45", "pct_chg": "+42.6%", "status": "Open"},
            {"ticker": "LLY",  "company": "Eli Lilly Co",          "direction": "Long",  "date_added": "2/03/26", "buy_price": "$71.20",  "current": "$95.10",  "pct_chg": "+33.6%", "status": "Open"},
            {"ticker": "AXON", "company": "Axon Enterprise",       "direction": "Long",  "date_added": "1/28/26", "buy_price": "$67.80",  "current": "$88.20",  "pct_chg": "+30.1%", "status": "Open"},
            {"ticker": "META", "company": "Meta Platforms",        "direction": "Long",  "date_added": "2/14/26", "buy_price": "$66.00",  "current": "$82.30",  "pct_chg": "+24.7%", "status": "Open"},
            {"ticker": "INTC", "company": "Intel Corporation",     "direction": "Short", "date_added": "1/20/26", "buy_price": "$24.50",  "current": "$18.45",  "pct_chg": "+24.7%", "status": "Open"},
            {"ticker": "PARA", "company": "Paramount Global",      "direction": "Short", "date_added": "2/10/26", "buy_price": "$16.50",  "current": "$12.10",  "pct_chg": "+26.7%", "status": "Open"},
            {"ticker": "GLD",  "company": "SPDR Gold Shares ETF",  "direction": "Long",  "date_added": "1/05/26", "buy_price": "$52.30",  "current": "$58.40",  "pct_chg": "+11.7%", "status": "Open"},
            {"ticker": "DXC",  "company": "DXC Technology",        "direction": "Short", "date_added": "2/25/26", "buy_price": "$25.80",  "current": "$19.70",  "pct_chg": "+23.6%", "status": "Open"},
        ],
    },
}

# ── Portfolio ──────────────────────────────────────────────────────────────────

portfolio = {
    "open_positions": 3,
    "closed_trades":  14,
    "open_pnl_dollars":    1842.50,
    "closed_pnl_dollars":  6210.00,
    "total_allocation_pct": 22.5,
    "win_rate": 71.4,
    "wins": 10,
    "losses": 4,
    "positions": [
        {
            "id": 1, "ticker": "NVDA", "direction": "long",
            "entry": 114.20, "shares": 50, "stop": 108.00, "target1": 130.00, "target2": 145.00,
            "setup": "Momentum Breakout", "allocation_pct": 7.5, "notes": "Strong AI tailwinds",
            "entry_date": "2026-03-18", "status": "open",
            "current_price": 127.45,
            "unrealized_pnl_pct": 11.6, "unrealized_pnl_dollars": 1662.50,
            "last_updated": "2026-04-02 09:32",
            "stop_hit": False, "t1_hit": False, "t2_hit": False,
        },
        {
            "id": 2, "ticker": "LLY", "direction": "long",
            "entry": 88.50, "shares": 40, "stop": 83.00, "target1": 100.00, "target2": 110.00,
            "setup": "Base Breakout", "allocation_pct": 7.5, "notes": "GLP-1 pipeline strength",
            "entry_date": "2026-03-22", "status": "open",
            "current_price": 95.10,
            "unrealized_pnl_pct": 7.5, "unrealized_pnl_dollars": 264.00,
            "last_updated": "2026-04-02 09:32",
            "stop_hit": False, "t1_hit": False, "t2_hit": False,
        },
        {
            "id": 3, "ticker": "GLD", "direction": "long",
            "entry": 54.80, "shares": 80, "stop": 52.00, "target1": 62.00, "target2": 68.00,
            "setup": "Safe Haven Breakout", "allocation_pct": 7.5, "notes": "Geo hedge",
            "entry_date": "2026-03-28", "status": "open",
            "current_price": 58.40,
            "unrealized_pnl_pct": 6.6, "unrealized_pnl_dollars": 288.00,
            "last_updated": "2026-04-02 09:32",
            "stop_hit": False, "t1_hit": False, "t2_hit": False,
        },
    ],
    "closed": [
        {"id": 4, "ticker": "AXON", "direction": "long", "entry": 71.00, "exit_price": 88.20, "shares": 50, "pnl_pct": 24.2, "pnl_dollars": 860.00, "win": True,  "exit_date": "2026-03-15", "setup": "Trend Continuation"},
        {"id": 5, "ticker": "META", "direction": "long", "entry": 61.50, "exit_price": 82.30, "shares": 60, "pnl_pct": 33.8, "pnl_dollars": 1248.00,"win": True,  "exit_date": "2026-03-20", "setup": "Pullback Entry"},
        {"id": 6, "ticker": "INTC", "direction": "short","entry": 24.50, "exit_price": 18.45, "shares": 100,"pnl_pct": 24.7, "pnl_dollars": 605.00, "win": True,  "exit_date": "2026-03-28", "setup": "Distribution"},
        {"id": 7, "ticker": "TSLA", "direction": "short","entry": 95.00, "exit_price": 62.80, "shares": 40, "pnl_pct": 33.9, "pnl_dollars": 1288.00,"win": True,  "exit_date": "2026-03-30", "setup": "Bearish Continuation"},
        {"id": 8, "ticker": "AMZN", "direction": "long", "entry": 92.00, "exit_price": 88.00, "shares": 30, "pnl_pct": -4.3, "pnl_dollars": -120.00,"win": False, "exit_date": "2026-03-25", "setup": "Failed Breakout"},
    ],
}

# ── Stats ──────────────────────────────────────────────────────────────────────

stats = {
    "sufficient_data": True,
    "win_rate": 71.4,
    "profit_factor": 4.2,
    "avg_win":  18.7,
    "avg_loss":  5.1,
    "total_trades": 14,
    "best_streak": 6,
    "best_trade":  {"ticker": "META", "pct_chg": 33.8},
    "worst_trade": {"ticker": "AMZN", "pct_chg": -4.3},
    "recent": [
        {"ticker": "TSLA", "pct_chg": 33.9,  "win": True,  "exit_date": "2026-03-30"},
        {"ticker": "INTC", "pct_chg": 24.7,  "win": True,  "exit_date": "2026-03-28"},
        {"ticker": "AMZN", "pct_chg": -4.3,  "win": False, "exit_date": "2026-03-25"},
        {"ticker": "META", "pct_chg": 33.8,  "win": True,  "exit_date": "2026-03-20"},
        {"ticker": "AXON", "pct_chg": 24.2,  "win": True,  "exit_date": "2026-03-15"},
    ],
}

# ── Regime ────────────────────────────────────────────────────────────────────

regime = {
    "regime": "bull",      # show bull for demo to see green badges
    "spy_price": 558.40,
    "above_50ema":  True,
    "above_200sma": True,
    "spy_change_pct": 0.8,
    "spy_1m_ret": 4.2,
    "vix": {
        "vix_current": 16.8,
        "vix_ma20":    18.2,
        "peak_20d":    22.5,
        "trend":       "falling",
        "regime":      "normal",
        "spike_recovery": True,
        "error":       None,
    },
}

# ── Sector ETF Rotation mock data ─────────────────────────────────────────────

sector_etf_data = {
    "XLK":  {"name": "Technology",             "perf_63d": 8.4,  "vs_spy_pct":  3.1, "outperforming": True,  "rank": 1},
    "XLV":  {"name": "Healthcare",             "perf_63d": 6.1,  "vs_spy_pct":  0.8, "outperforming": True,  "rank": 2},
    "XLI":  {"name": "Industrials",            "perf_63d": 5.8,  "vs_spy_pct":  0.5, "outperforming": True,  "rank": 3},
    "XLC":  {"name": "Communication Services", "perf_63d": 5.2,  "vs_spy_pct": -0.1, "outperforming": False, "rank": 4},
    "XLY":  {"name": "Consumer Discretionary", "perf_63d": 4.9,  "vs_spy_pct": -0.4, "outperforming": False, "rank": 5},
    "XLF":  {"name": "Financials",             "perf_63d": 4.3,  "vs_spy_pct": -1.0, "outperforming": False, "rank": 6},
    "XLB":  {"name": "Materials",              "perf_63d": 3.1,  "vs_spy_pct": -2.2, "outperforming": False, "rank": 7},
    "XLP":  {"name": "Consumer Staples",       "perf_63d": 2.8,  "vs_spy_pct": -2.5, "outperforming": False, "rank": 8},
    "XLE":  {"name": "Energy",                 "perf_63d": 1.4,  "vs_spy_pct": -3.9, "outperforming": False, "rank": 9},
    "XLRE": {"name": "Real Estate",            "perf_63d": 0.6,  "vs_spy_pct": -4.7, "outperforming": False, "rank": 10},
    "XLU":  {"name": "Utilities",              "perf_63d": -0.8, "vs_spy_pct": -6.1, "outperforming": False, "rank": 11},
    "SPY":  {"perf_63d": 5.3},
}

# ── Assemble bundle ────────────────────────────────────────────────────────────

# ── Zacks #1 full list + exclusion reasons (mock) ─────────────────────────────

# Tickers that appeared in Zacks #1 but were excluded before scoring
zacks_r1_missing = {
    "MSFT":  "Price $412.30 outside $5–$100 range",
    "GOOGL": "Price $168.50 outside $5–$100 range",
    "AMZN":  "Price $189.20 outside $5–$100 range",
    "TSLA":  "Price $172.80 outside $5–$100 range",
    "COST":  "Price $891.00 outside $5–$100 range",
    "NFLX":  "Price $628.40 outside $5–$100 range",
    "ADBE":  "Price $437.10 outside $5–$100 range",
    "ORCL":  "Price $138.60 outside $5–$100 range",
    "SBUX":  "No market data (Yahoo + tvDatafeed both failed)",
    "MRVL":  "No market data (Yahoo + tvDatafeed both failed)",
    "MU":    "Volume $6.2M/day below $10M minimum",
    "HPE":   "Volume $4.8M/day below $10M minimum",
    "NUE":   "Price $102.50 outside $5–$100 range",
    "AMAT":  "Price $155.30 outside $5–$100 range",
    "KLAC":  "Price $712.00 outside $5–$100 range",
}

# Full Zacks #1 list (analyzed + excluded)
zacks_r1_full = [r["ticker"] for r in zacks_tab] + list(zacks_r1_missing.keys())

bundle = {
    "run_date":          "2026-04-02 (DEMO)",
    "regime":            regime,
    "buy_candidates":    buy_candidates,
    "sell_candidates":   sell_candidates,
    "watch_list":        watch_list,
    "all_scored":        all_scored,
    "killed":            killed,
    "industries":        industries,
    "zacks_tab":         zacks_tab,
    "zacks_r1_full":     zacks_r1_full,
    "zacks_r1_missing":  zacks_r1_missing,
    "ultimate":          ultimate_data,
    "portfolio":         portfolio,
    "stats":             stats,
    "sector_etf_data":   sector_etf_data,
    "market_breadth": {
        "total": 486, "above_50d": 219, "pct_above_50d": 45.1, "label_50": "weak",
        "above_100d": 171, "pct_above_100d": 35.2, "label_100": "oversold",
    },
    "macro_signals": {
        "hyg": {"price": 76.42, "ma20": 77.18, "chg5d": -1.3, "trend": "falling"},
        "dxy": {"price": 22.15, "ma20": 21.80, "chg5d": 1.8,  "trend": "rising"},
        "gld": {"price": 191.50, "ma20": 188.20, "chg5d": 2.1, "trend": "rising"},
        "risk_signal": "risk-off",
        "error": None,
    },
    "portfolio_risk": {
        "sector_concentration": [
            {"sector": "Technology",              "count": 48, "pct": 28.6},
            {"sector": "Healthcare",              "count": 31, "pct": 18.5},
            {"sector": "Consumer Cyclical",       "count": 22, "pct": 13.1},
            {"sector": "Communication Services",  "count": 18, "pct": 10.7},
            {"sector": "Industrials",             "count": 15, "pct": 8.9},
        ],
        "avg_beta": 1.22,
        "beta_count": 5,
        "correlation_matrix": [
            {"t1": "NVDA", "t2": "META",  "corr": 0.78, "level": "high"},
            {"t1": "NVDA", "t2": "AXON",  "corr": 0.51, "level": "med"},
            {"t1": "META", "t2": "LLY",   "corr": 0.32, "level": "low"},
            {"t1": "DECK", "t2": "AXON",  "corr": 0.44, "level": "med"},
        ],
        "drawdown_flags": [
            {"ticker": "DECK", "drawdown_pct": 42.5},
        ],
        "gap_flags": [],
    },
    "price_tier_results": [
        {
            "label": "$5–$50",
            "min": 5, "max": 50,
            "picks": [r for r in all_scored if 5 <= r["price"] <= 50
                      and r["decision"]["verdict"] in ("BUY","WATCH")][:5],
        },
        {
            "label": "$50–$100",
            "min": 50, "max": 100,
            "picks": [r for r in all_scored if 50 < r["price"] <= 100
                      and r["decision"]["verdict"] in ("BUY","WATCH")][:5],
        },
        {
            "label": ">$100",
            "min": 100, "max": 9999,
            "picks": [r for r in all_scored if r["price"] > 100
                      and r["decision"]["verdict"] in ("BUY","WATCH")][:5],
        },
    ],
    "config":            {"filters": {"min_price": 5, "max_price": 9999}},
    "total_scanned":     524,
    "total_passed":      286,
}

out = Path(__file__).parent / "cache" / "demo_dashboard.html"
path = build_dashboard(bundle, out)
print(f"Demo dashboard: {path}")

import subprocess
subprocess.run(["open", path])
