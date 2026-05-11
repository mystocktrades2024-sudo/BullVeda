"""
mean_reversion.py — Mean Reversion strategy module for SwingTrade.

Strong stocks (RS >= 60, above 200 SMA) that temporarily dip to oversold
levels (RSI < 30 or 3-day pullback > 5%) tend to bounce back quickly.
This is NOT bottom-fishing weak stocks — it's buying temporary weakness
in strong names.

Family: Special Situation
Hold period: 3-7 days

Usage:
    python3 mean_reversion.py               # Scan for current candidates
    python3 mean_reversion.py scan          # Same as above
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("swingtrade.mean_reversion")


# ── Technical helpers ────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Returns (upper, lower, middle) Bollinger Bands."""
    middle = _sma(close, period)
    std = close.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, lower, middle


def _relative_strength_rank(ticker_close: pd.Series, spy_close: pd.Series,
                            period: int = 63) -> int:
    """Compute RS rank (0-100) of a stock vs SPY over `period` days."""
    if len(ticker_close) < period or len(spy_close) < period:
        return 50
    t_ret = (float(ticker_close.iloc[-1]) / float(ticker_close.iloc[-period])) - 1
    s_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-period])) - 1
    rs_ratio = (1 + t_ret) / (1 + s_ret) if (1 + s_ret) != 0 else 1.0
    if np.isnan(rs_ratio):
        return 50
    return min(100, max(0, int((rs_ratio - 0.8) / 0.4 * 100)))


def _swing_low(low_series: pd.Series, window: int = 5) -> Optional[float]:
    """Find the most recent swing low within the last `window*3` bars."""
    n = len(low_series)
    search_range = min(n, window * 3)
    for i in range(n - 1 - window, max(n - 1 - search_range, window - 1), -1):
        lo = float(low_series.iloc[i])
        start = max(0, i - window)
        end = min(n, i + window + 1)
        if lo == float(low_series.iloc[start:end].min()):
            return lo
    return None


# ── Core functions ───────────────────────────────────────────────────────────

def scan_mean_reversion() -> list[dict]:
    """
    Scan for mean reversion candidates across the archived universe.

    Criteria:
      - Price is above 200 SMA (long-term uptrend intact)
      - RS rank >= 60 (not a fundamentally weak name)
      - RSI(14) < 30 OR 3-day pullback > 5% OR price touched lower Bollinger Band
      - Volume on the pullback is declining (not distribution)

    Returns list of dicts:
        {ticker, rsi, pullback_pct, distance_to_200sma, setup_type}
    """
    from data_archive import load_all, load_ticker

    log.info("Scanning for mean reversion candidates...")

    # Load SPY for RS calculation
    spy_df = load_ticker("SPY")
    spy_close = None
    if spy_df is not None:
        spy_close = spy_df["Close"].squeeze().dropna()

    # Load universe from archive
    all_data = load_all()
    if not all_data:
        log.warning("No data in archive. Run: python3 data_archive.py download")
        return []

    log.info(f"Scanning {len(all_data)} tickers from archive...")

    candidates = []

    for ticker, df in all_data.items():
        try:
            if ticker in ("SPY", "QQQ", "IWM", "VIX"):
                continue  # Skip indices

            close = df["Close"].squeeze().dropna()
            vol = df["Volume"].squeeze().dropna()

            if len(close) < 200:
                continue

            price = float(close.iloc[-1])

            # 1. Must be above 200 SMA (long-term uptrend)
            sma200 = float(_sma(close, 200).iloc[-1])
            if np.isnan(sma200) or price <= sma200:
                continue

            # 2. RS rank >= 60
            rs_rank = 50
            if spy_close is not None:
                rs_rank = _relative_strength_rank(close, spy_close)
            if rs_rank < 60:
                continue

            # 3. Oversold trigger: RSI < 30, 3-day pullback > 5%, or lower BB touch
            rsi_val = float(_rsi(close).iloc[-1])
            pullback_pct = 0.0
            if len(close) >= 4:
                recent_high = float(close.iloc[-4:-1].max())
                if recent_high > 0:
                    pullback_pct = (recent_high - price) / recent_high * 100

            _, bb_lower, _ = _bollinger_bands(close)
            bb_lower_val = float(bb_lower.iloc[-1]) if not np.isnan(bb_lower.iloc[-1]) else 0
            touched_lower_bb = price <= bb_lower_val * 1.005  # Within 0.5% of lower band

            rsi_oversold = rsi_val < 30
            pullback_trigger = pullback_pct > 5.0
            bb_trigger = touched_lower_bb

            if not (rsi_oversold or pullback_trigger or bb_trigger):
                continue

            # 4. Volume declining on pullback (not distribution)
            if len(vol) >= 5:
                vol_today = float(vol.iloc[-1])
                vol_3d_avg = float(vol.iloc[-4:-1].mean())
                avg_vol_20 = float(vol.rolling(20).mean().iloc[-1])

                # Volume should be declining relative to recent average
                # (selling is drying up, not accelerating)
                if avg_vol_20 > 0 and vol_today > avg_vol_20 * 1.8:
                    # Heavy volume on down day = distribution, skip
                    if price < float(close.iloc[-2]):
                        continue

            # Determine setup type
            triggers = []
            if rsi_oversold:
                triggers.append(f"RSI={rsi_val:.0f}")
            if pullback_trigger:
                triggers.append(f"Pullback {pullback_pct:.1f}%")
            if bb_trigger:
                triggers.append("BB Touch")

            setup_type = "Mean Reversion: " + " + ".join(triggers)

            distance_to_200sma = round((price / sma200 - 1) * 100, 2)

            candidates.append({
                "ticker": ticker,
                "rsi": round(rsi_val, 1),
                "pullback_pct": round(pullback_pct, 1),
                "distance_to_200sma": distance_to_200sma,
                "setup_type": setup_type,
                "price": round(price, 2),
                "sma200": round(sma200, 2),
                "rs_rank": rs_rank,
                "touched_bb": touched_lower_bb,
            })

        except Exception as e:
            log.debug(f"Error scanning {ticker}: {e}")

    # Sort: most oversold first (lowest RSI)
    candidates.sort(key=lambda x: x["rsi"])
    log.info(f"Found {len(candidates)} mean reversion candidates")
    return candidates


def score_mean_reversion(ticker: str, df: pd.DataFrame) -> dict:
    """
    Score a mean reversion candidate 0-100.

    Components:
      - Oversold depth (25 pts): RSI < 25 = 25, < 30 = 20, < 35 = 15
      - Trend strength (25 pts): above 200 SMA AND 50 SMA = 25, above 200 only = 15
      - Volume pattern (20 pts): declining volume on pullback = 20 (not distribution)
      - Support proximity (15 pts): near EMA50 or EMA200 or key support = 15
      - Bollinger Band (15 pts): touched lower band = 15

    Args:
        ticker: Stock ticker symbol
        df: DataFrame with OHLCV data (Open, High, Low, Close, Volume)

    Returns dict with:
        {score, breakdown, trade_plan}
    """
    if df is None or len(df) < 200:
        return {"score": 0, "breakdown": {}, "trade_plan": None}

    close = df["Close"].squeeze().dropna()
    high = df["High"].squeeze().dropna()
    low = df["Low"].squeeze().dropna()
    vol = df["Volume"].squeeze().dropna()
    price = float(close.iloc[-1])

    breakdown = {}
    total = 0

    # 1. Oversold depth (25 pts)
    rsi_val = float(_rsi(close).iloc[-1])
    oversold_pts = 0
    if rsi_val < 25:
        oversold_pts = 25
    elif rsi_val < 30:
        oversold_pts = 20
    elif rsi_val < 35:
        oversold_pts = 15
    elif rsi_val < 40:
        oversold_pts = 8
    breakdown["oversold_depth"] = oversold_pts
    total += oversold_pts

    # 2. Trend strength (25 pts)
    trend_pts = 0
    sma200 = float(_sma(close, 200).iloc[-1])
    sma50 = float(_sma(close, 50).iloc[-1])
    ema21 = float(_ema(close, 21).iloc[-1])

    if price > sma200 and price > sma50:
        trend_pts = 25  # Above both = strong trend
    elif price > sma200:
        trend_pts = 15  # Above 200 only
    elif sma50 > sma200:
        trend_pts = 8   # 50 above 200 (trend intact, price just dipped below)
    breakdown["trend_strength"] = trend_pts
    total += trend_pts

    # 3. Volume pattern (20 pts) — declining volume on pullback = healthy
    vol_pts = 0
    if len(vol) >= 5:
        avg_vol_20 = float(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else float(vol.mean())

        if avg_vol_20 > 0:
            # Check if volume has been declining over the last 3 days
            vol_recent = vol.iloc[-3:]
            vol_declining = True
            for i in range(1, len(vol_recent)):
                if float(vol_recent.iloc[i]) > float(vol_recent.iloc[i - 1]) * 1.1:
                    vol_declining = False
                    break

            # Also check that recent volume is below average (selling drying up)
            vol_ratio = float(vol.iloc[-1]) / avg_vol_20

            if vol_declining and vol_ratio < 0.8:
                vol_pts = 20  # Volume clearly drying up
            elif vol_declining:
                vol_pts = 15  # Volume declining but still around average
            elif vol_ratio < 1.0:
                vol_pts = 10  # Below average volume (not heavy selling)
            # Heavy volume on a down day = distribution = 0 pts
    breakdown["volume_pattern"] = vol_pts
    total += vol_pts

    # 4. Support proximity (15 pts)
    support_pts = 0
    ema50 = float(_ema(close, 50).iloc[-1])

    # Distance to key support levels
    dist_to_ema50 = abs(price - ema50) / price * 100
    dist_to_sma200 = abs(price - sma200) / price * 100

    # Find recent swing low
    recent_swing_low = _swing_low(low)

    if dist_to_ema50 < 1.5:
        support_pts = 15  # Right at EMA50 support
    elif dist_to_sma200 < 2.0:
        support_pts = 15  # Right at SMA200 support
    elif recent_swing_low and abs(price - recent_swing_low) / price * 100 < 2.0:
        support_pts = 12  # Near recent swing low
    elif dist_to_ema50 < 3.0:
        support_pts = 8   # Close to EMA50
    elif dist_to_sma200 < 4.0:
        support_pts = 6   # Somewhat close to SMA200
    breakdown["support_proximity"] = support_pts
    total += support_pts

    # 5. Bollinger Band (15 pts)
    bb_pts = 0
    _, bb_lower, _ = _bollinger_bands(close)
    bb_lower_val = float(bb_lower.iloc[-1])

    if price <= bb_lower_val:
        bb_pts = 15  # Below lower band
    elif price <= bb_lower_val * 1.01:
        bb_pts = 12  # Within 1% of lower band
    elif price <= bb_lower_val * 1.02:
        bb_pts = 8   # Within 2% of lower band
    breakdown["bollinger_band"] = bb_pts
    total += bb_pts

    total = min(100, total)

    # Build trade plan
    # Stop: tight 2-3% max from entry. Mean reversion trades either bounce
    # fast (2-4 days) or they're not mean reversion — they're broken.
    # Priority: recent swing low (if within 3%), else hard 3% below entry.
    if recent_swing_low and recent_swing_low < price:
        swing_low_pct = (price - recent_swing_low) / price * 100
        if swing_low_pct <= 3.0:
            stop = round(recent_swing_low * 0.998, 2)  # Just below swing low
        else:
            stop = round(price * 0.97, 2)  # Hard 3% stop
    else:
        stop = round(price * 0.97, 2)  # Hard 3% stop
    # Never set stop below 5% — that's not a swing trade
    max_stop = round(price * 0.95, 2)
    if stop < max_stop:
        stop = max_stop

    # Targets: EMA21 (first), recent swing high capped at +10% (second).
    # 2026-05-10 fix: target2 was uncapped 20-bar max high — same class of bug
    # as weekly_pullback (CAR's anomalous spike to $847 produced unreachable
    # targets for 9 straight days). Mean reversion trades are short-horizon;
    # +10% cap aligns with documented bounce horizon.
    target1 = round(ema21, 2)  # Mean reversion first target
    if len(high) >= 20:
        target2 = round(min(float(high.iloc[-20:].max()), price * 1.10), 2)
    else:
        target2 = round(price * 1.08, 2)

    # Ensure target1 is above price (if EMA21 is below, use EMA50 or a % target)
    if target1 <= price:
        target1 = round(price * 1.03, 2)  # 3% bounce target
    if target2 <= target1:
        target2 = round(target1 * 1.03, 2)

    risk = price - stop
    rr_ratio = round((target1 - price) / risk, 2) if risk > 0 else 0

    trade_plan = {
        "direction": "long",
        "entry_low": round(price, 2),
        "entry_high": round(price * 1.005, 2),  # Tight entry zone (oversold = immediate)
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "rr_ratio": rr_ratio,
        "setup_type": "Mean Reversion",
        "family": "Special Situation",
        "hold_days": "3-7",
        "risk_per_share": round(abs(risk), 2),
        "price": price,
        "reason": (
            f"Mean Reversion: RSI {rsi_val:.0f}, "
            f"{'above' if price > sma200 else 'near'} 200 SMA. "
            f"Enter ${price:.2f} (oversold = immediate), "
            f"stop ${stop}, T1 ${target1} (EMA21), T2 ${target2} (swing high)."
        ),
    }

    return {
        "score": total,
        "breakdown": breakdown,
        "rsi": round(rsi_val, 1),
        "trade_plan": trade_plan,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def run_scan():
    """Full mean reversion scan: find oversold strong stocks."""
    from data_archive import load_ticker

    print("\n" + "=" * 60)
    print("MEAN REVERSION SCAN")
    print("=" * 60)
    print("Strategy: Buy temporary weakness in strong names")
    print("Criteria: Above 200 SMA, RS >= 60, RSI < 30 / 5%+ pullback / BB touch")
    print()

    candidates = scan_mean_reversion()

    if not candidates:
        print("No mean reversion candidates found.")
        print("This is normal in strongly trending markets with few pullbacks.")
        return []

    print(f"Found {len(candidates)} candidates:\n")
    print(f"{'Ticker':<7} {'RSI':>5} {'Pull%':>6} {'Dist200':>8} {'RS':>4} {'Price':>8} {'Setup'}")
    print("-" * 75)

    scored = []
    for c in candidates[:20]:  # Score top 20 by RSI
        df = load_ticker(c["ticker"])
        if df is None:
            continue

        result = score_mean_reversion(c["ticker"], df)
        c["score"] = result["score"]
        c["trade_plan"] = result.get("trade_plan")
        c["breakdown"] = result.get("breakdown", {})
        scored.append(c)

        print(f"{c['ticker']:<7} {c['rsi']:>5.1f} {c['pullback_pct']:>5.1f}% "
              f"{c['distance_to_200sma']:>+7.1f}% {c['rs_rank']:>4} "
              f"${c['price']:>7.2f} {c['setup_type'][:35]}")

    if scored:
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        print(f"\n{'=' * 60}")
        print(f"TOP MEAN REVERSION CANDIDATES (sorted by score)")
        print(f"{'=' * 60}")
        print(f"{'Ticker':<7} {'Score':>6} {'RSI':>5} {'RS':>4} {'Entry':>8} {'Stop':>8} {'T1':>8} {'R:R':>5}")
        print("-" * 60)

        for c in scored[:10]:
            plan = c.get("trade_plan", {})
            if plan:
                print(f"{c['ticker']:<7} {c['score']:>6} {c['rsi']:>5.1f} "
                      f"{c['rs_rank']:>4} ${plan.get('price', 0):>7.2f} "
                      f"${plan.get('stop', 0):>7.2f} "
                      f"${plan.get('target1', 0):>7.2f} "
                      f"{plan.get('rr_ratio', 0):>5.2f}")

        # Print detailed plans for top 3
        print(f"\n{'=' * 60}")
        print("DETAILED TRADE PLANS (Top 3)")
        print(f"{'=' * 60}")
        for c in scored[:3]:
            plan = c.get("trade_plan", {})
            bd = c.get("breakdown", {})
            if not plan:
                continue
            print(f"\n{c['ticker']} — Score: {c['score']}/100")
            print(f"  Setup: {c['setup_type']}")
            print(f"  Entry: ${plan.get('price', 0):.2f} (immediate — oversold)")
            print(f"  Stop:  ${plan.get('stop', 0):.2f} (risk ${plan.get('risk_per_share', 0):.2f}/share)")
            print(f"  T1:    ${plan.get('target1', 0):.2f} (EMA21)")
            print(f"  T2:    ${plan.get('target2', 0):.2f} (swing high)")
            print(f"  R:R:   {plan.get('rr_ratio', 0):.2f}")
            print(f"  Hold:  {plan.get('hold_days', '3-7')} days")
            print(f"  Score breakdown: oversold={bd.get('oversold_depth', 0)}, "
                  f"trend={bd.get('trend_strength', 0)}, "
                  f"volume={bd.get('volume_pattern', 0)}, "
                  f"support={bd.get('support_proximity', 0)}, "
                  f"BB={bd.get('bollinger_band', 0)}")

    return scored


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        run_scan()
    else:
        print(f"Usage: python3 mean_reversion.py [scan]")
