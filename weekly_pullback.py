"""
weekly_pullback.py — Pullback to Rising 10-Week MA strategy.

The simplest and most reliable swing setup: buy strong stocks when they
pull back to their rising 10-week (50-day) moving average.

Rules:
  1. Stock is above 200 SMA (long-term uptrend intact)
  2. 50 SMA is rising (slope positive over 10 days)
  3. Price touched or came within 1.5% of the 50 SMA
  4. RS rank >= 70 (only strong names)
  5. Volume declining on pullback (not distribution)

Entry: At or near the 50 SMA
Stop: 3% below the 50 SMA (if it breaks, trend is over)
Target 1: Recent swing high
Target 2: 2x the risk above entry
Hold: 7-14 days

Family: Trend Continuation
Historical WR: ~65% (Minervini, O'Neil, proven across decades)

Usage:
    python3 weekly_pullback.py
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd

log = logging.getLogger("swingtrade.weekly_pullback")


def scan_weekly_pullback():
    """
    Scan the data archive for stocks pulling back to their rising 50 SMA.
    Returns sorted list of candidates.
    """
    from data_archive import load_all

    log.info("Scanning for 10-week pullback candidates...")
    all_data = load_all()
    log.info(f"Scanning {len(all_data)} tickers from archive...")

    candidates = []

    for ticker, df in all_data.items():
        try:
            result = score_weekly_pullback(ticker, df)
            if result and result.get("score", 0) >= 50:
                candidates.append(result)
        except Exception:
            continue

    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    log.info(f"Found {len(candidates)} pullback candidates")
    return candidates


def score_weekly_pullback(ticker: str, df: pd.DataFrame):
    """
    Score a stock for the 10-week pullback setup.
    Returns dict with score, trade plan, and breakdown. None if not a candidate.
    """
    if df is None or len(df) < 60:
        return None

    close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    high = df["High"].squeeze() if isinstance(df["High"], pd.DataFrame) else df["High"]
    low = df["Low"].squeeze() if isinstance(df["Low"], pd.DataFrame) else df["Low"]
    volume = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

    close = close.astype(float)
    high = high.astype(float)
    low = low.astype(float)
    volume = volume.astype(float)

    price = float(close.iloc[-1])
    if price < 2 or price > 250:
        return None

    # ── Compute indicators ──
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if len(close) >= 200 else None
    ema21 = close.ewm(span=21, adjust=False).mean()

    sma50_now = float(sma50.iloc[-1])
    sma200_now = float(sma200.iloc[-1]) if sma200 is not None and len(sma200.dropna()) > 0 else None

    if np.isnan(sma50_now):
        return None

    # ── FILTER 1: Price above 200 SMA (long-term uptrend) ──
    if sma200_now is not None and price < sma200_now:
        return None

    # ── FILTER 2: 50 SMA must be rising (slope positive) ──
    sma50_10d_ago = float(sma50.iloc[-10]) if len(sma50) >= 10 else sma50_now
    sma50_slope = (sma50_now - sma50_10d_ago) / sma50_10d_ago * 100
    if sma50_slope < 0.1:  # Must be rising at least 0.1% over 10 days
        return None

    # ── FILTER 3: Price near 50 SMA (within 2% above, or touched it) ──
    dist_to_50 = (price - sma50_now) / sma50_now * 100
    # Must be within 2% above OR have touched it in last 3 days
    touched_recently = False
    for i in range(-3, 0):
        if len(low) >= abs(i):
            day_low = float(low.iloc[i])
            if day_low <= sma50_now * 1.005:  # Within 0.5% of 50 SMA
                touched_recently = True
                break

    if dist_to_50 > 2.0 and not touched_recently:
        return None
    if dist_to_50 > 5.0:  # Too far even if touched
        return None

    # ── FILTER 4: RS rank >= 70 ──
    # Compute simple RS vs SPY
    from data_archive import load_ticker
    spy_df = load_ticker("SPY")
    rs_rank = 50  # default
    if spy_df is not None and len(spy_df) >= 63:
        spy_close = spy_df["Close"].squeeze().astype(float)
        if len(close) >= 63 and len(spy_close) >= 63:
            stock_ret = (float(close.iloc[-1]) / float(close.iloc[-63]) - 1) * 100
            spy_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-63]) - 1) * 100
            # Simple percentile estimate
            rs_rank = min(99, max(1, int(50 + (stock_ret - spy_ret) * 3)))

    if rs_rank < 70:
        return None

    # ── FILTER 5: Volume declining on pullback ──
    vol_avg = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
    vol_recent = float(volume.iloc[-3:].mean()) if len(volume) >= 3 else vol_avg
    vol_declining = vol_recent < vol_avg * 1.1  # Not heavy selling

    # ── SCORE (0-100) ──
    total = 0
    breakdown = {}

    # Proximity to 50 SMA (30 pts) — closer = better
    if dist_to_50 <= 0.5 or touched_recently:
        prox_pts = 30
    elif dist_to_50 <= 1.0:
        prox_pts = 25
    elif dist_to_50 <= 1.5:
        prox_pts = 20
    elif dist_to_50 <= 2.0:
        prox_pts = 15
    else:
        prox_pts = 10
    breakdown["proximity_to_50sma"] = prox_pts
    total += prox_pts

    # 50 SMA slope strength (20 pts) — steeper rise = stronger trend
    if sma50_slope >= 1.0:
        slope_pts = 20
    elif sma50_slope >= 0.5:
        slope_pts = 15
    elif sma50_slope >= 0.2:
        slope_pts = 10
    else:
        slope_pts = 5
    breakdown["sma50_slope"] = slope_pts
    total += slope_pts

    # RS rank (20 pts)
    if rs_rank >= 90:
        rs_pts = 20
    elif rs_rank >= 80:
        rs_pts = 15
    elif rs_rank >= 70:
        rs_pts = 10
    else:
        rs_pts = 5
    breakdown["rs_rank"] = rs_pts
    total += rs_pts

    # Volume pattern (15 pts) — declining volume on pullback = healthy
    if vol_declining and vol_recent < vol_avg * 0.7:
        vol_pts = 15  # Volume dry-up — ideal
    elif vol_declining:
        vol_pts = 10
    else:
        vol_pts = 3  # Heavy volume on pullback = possible distribution
    breakdown["volume_pattern"] = vol_pts
    total += vol_pts

    # Price structure (15 pts)
    ema21_now = float(ema21.iloc[-1])
    struct_pts = 0
    if price > ema21_now and ema21_now > sma50_now:
        struct_pts = 15  # Full bull alignment
    elif price > sma50_now:
        struct_pts = 10
    else:
        struct_pts = 5
    breakdown["price_structure"] = struct_pts
    total += struct_pts

    total = min(100, total)

    # ── TRADE PLAN ──
    entry = round(price, 2)

    # Stop: use the LOWER of 3% below 50 SMA or 3% below entry price
    # This prevents the stop from being too close when price is below 50 SMA
    stop_sma = round(sma50_now * 0.97, 2)
    stop_price = round(price * 0.97, 2)
    # Also check recent swing low (last 10 bars)
    stop_swing = round(float(low.iloc[-10:].min()) * 0.99, 2) if len(low) >= 10 else stop_price
    stop = round(min(stop_sma, stop_price, stop_swing), 2)

    # Minimum risk: at least 2% of entry price (prevents R:R distortion)
    min_risk = entry * 0.02
    if entry - stop < min_risk:
        stop = round(entry - min_risk, 2)

    # Target 1: recent swing high, capped at +15% above entry.
    # 2026-05-10 fix: was uncapped, which let an anomalous intraday spike
    # poison the target. CAR's 04-22 spike to $847 (entry ~$170) produced 9
    # straight losing entries with target1 = $847.70 (target +400%, RR 10),
    # because high.iloc[-20:].max() kept finding the spike. 15% cap aligns
    # with 7-14d hold horizon (1-2 ATR upside is realistic; +400% is not).
    recent_high = float(high.iloc[-20:].max()) if len(high) >= 20 else price * 1.05
    target1 = round(min(recent_high, entry * 1.15), 2)

    # Target 2: 2x risk above entry
    risk = entry - stop
    target2 = round(entry + risk * 2, 2)

    # Ensure targets are above price
    if target1 <= price:
        target1 = round(price * 1.04, 2)
    if target2 <= target1:
        target2 = round(target1 * 1.03, 2)

    rr_ratio = round((target1 - entry) / risk, 2) if risk > 0 else 0
    # Cap R:R at 10 to prevent display distortion
    rr_ratio = min(rr_ratio, 10.0)

    # RSI for context
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_val = round(float(rsi.iloc[-1]), 1) if not np.isnan(rsi.iloc[-1]) else 50.0

    return {
        "ticker": ticker,
        "score": total,
        "price": entry,
        "sma50": round(sma50_now, 2),
        "dist_to_50_pct": round(dist_to_50, 1),
        "sma50_slope_pct": round(sma50_slope, 2),
        "rs_rank": rs_rank,
        "rsi": rsi_val,
        "vol_declining": vol_declining,
        "touched_50sma": touched_recently,
        "trade_plan": {
            "direction": "long",
            "entry": entry,
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "rr_ratio": rr_ratio,
            "risk_per_share": round(abs(risk), 2),
            "setup_type": "10-Week Pullback",
            "family": "Trend Continuation",
            "hold_days": "7-14",
        },
        "breakdown": breakdown,
    }


def run_scan():
    """Run full scan and print results."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    candidates = scan_weekly_pullback()

    print("\n" + "=" * 60)
    print("10-WEEK PULLBACK SCAN")
    print("=" * 60)
    print("Strategy: Buy strong stocks pulling back to rising 50 SMA")
    print("Criteria: Above 200 SMA, 50 SMA rising, within 2%, RS >= 70")
    print(f"\nFound {len(candidates)} candidates:\n")

    if not candidates:
        print("No candidates found.")
        return

    print(f"{'Ticker':<8} {'Score':>5} {'Price':>8} {'50SMA':>8} {'Dist%':>6} {'Slope':>6} {'RS':>4} {'RSI':>5} {'R:R':>5} {'Vol':>8}")
    print("-" * 75)

    for c in candidates[:20]:
        plan = c["trade_plan"]
        vol_flag = "Dry-up" if c["vol_declining"] else "Heavy"
        print(f"{c['ticker']:<8} {c['score']:>5} ${c['price']:>7.2f} ${c['sma50']:>7.2f} {c['dist_to_50_pct']:>+5.1f}% {c['sma50_slope_pct']:>5.2f}% {c['rs_rank']:>3} {c['rsi']:>5.1f} {plan['rr_ratio']:>5.2f} {vol_flag:>8}")

    # Top 3 trade plans
    print(f"\n{'=' * 60}")
    print("TRADE PLANS (Top 3)")
    print("=" * 60)

    for c in candidates[:3]:
        p = c["trade_plan"]
        print(f"\n{c['ticker']} — Score: {c['score']}/100")
        print(f"  Setup: {p['setup_type']} (50 SMA slope +{c['sma50_slope_pct']:.2f}%)")
        print(f"  Entry: ${p['entry']:.2f} (50 SMA at ${c['sma50']:.2f}, {c['dist_to_50_pct']:+.1f}% away)")
        print(f"  Stop:  ${p['stop']:.2f} (3% below 50 SMA, risk ${p['risk_per_share']:.2f}/share)")
        print(f"  T1:    ${p['target1']:.2f} (recent swing high)")
        print(f"  T2:    ${p['target2']:.2f} (2x risk)")
        print(f"  R:R:   {p['rr_ratio']:.2f}")
        print(f"  Hold:  {p['hold_days']} days")
        bd = c["breakdown"]
        print(f"  Score: proximity={bd['proximity_to_50sma']}, slope={bd['sma50_slope']}, "
              f"RS={bd['rs_rank']}, volume={bd['volume_pattern']}, structure={bd['price_structure']}")


if __name__ == "__main__":
    run_scan()
