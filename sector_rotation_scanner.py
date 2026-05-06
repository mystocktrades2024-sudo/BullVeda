"""
sector_rotation_scanner.py — Sector ETF Momentum/Rotation Scanner.

Edge: institutional money rotates between sectors. Buy sector ETFs
crossing from lagging→improving. Ride for 2-8 weeks.

Signal:
  1. Sector ETF outperforming SPY over 21 days (RS momentum turning positive)
  2. ETF above its 21-day EMA (trend confirmed)
  3. Not already extended >5% above EMA21 (avoid chasing)

Entry: buy sector ETF directly
Hold: 2-8 weeks
Stop: below EMA21
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
log = logging.getLogger("sector_rotation")

SECTOR_ETFS = ["XLE", "XLF", "XLK", "XLV", "XLU", "XLB", "XLI", "XLC", "XLP", "XLRE", "XBI", "SOXX", "SMH"]


def scan(ohlcv: dict[str, pd.DataFrame], spy_df: pd.DataFrame | None = None) -> list[dict]:
    results = []

    if spy_df is None:
        spy_df = ohlcv.get("SPY")
    if spy_df is None or spy_df.empty or len(spy_df) < 50:
        return []

    spy_c = spy_df["Close"].squeeze()
    spy_21d_ret = (float(spy_c.iloc[-1]) / float(spy_c.iloc[-22]) - 1) * 100 if len(spy_c) >= 22 else 0

    for etf in SECTOR_ETFS:
        try:
            df = ohlcv.get(etf)
            if df is None or df.empty or len(df) < 50:
                continue

            c = df["Close"].squeeze()
            price = float(c.iloc[-1])
            if price <= 0:
                continue

            ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
            ema21_prev = float(c.ewm(span=21, adjust=False).mean().iloc[-6])
            ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1]) if len(c) >= 50 else None

            # 21-day return
            ret_21d = (price / float(c.iloc[-22]) - 1) * 100 if len(c) >= 22 else 0
            # RS vs SPY
            rs_vs_spy = ret_21d - spy_21d_ret

            # Must be outperforming SPY
            if rs_vs_spy <= 0:
                continue

            # Must be above rising EMA21
            if price < ema21 or ema21 <= ema21_prev:
                continue

            # Not too extended
            dist_from_ema = ((price - ema21) / ema21) * 100
            if dist_from_ema > 5:
                continue

            stop = round(ema21 - (price - ema21) * 0.2, 2)
            target = round(price * 1.08, 2)
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                continue

            # Momentum classification
            if rs_vs_spy > 3 and dist_from_ema < 2:
                status = "LEADING"
            elif rs_vs_spy > 1:
                status = "IMPROVING"
            else:
                status = "TURNING"

            results.append({
                "ticker": etf,
                "price": round(price, 2),
                "status": status,
                "ret_21d_pct": round(ret_21d, 1),
                "rs_vs_spy_pct": round(rs_vs_spy, 1),
                "ema21": round(ema21, 2),
                "dist_from_ema_pct": round(dist_from_ema, 1),
                "ema50": round(ema50, 2) if ema50 else None,
                "stop": stop,
                "target": target,
                "rr": round(rr, 1),
                "strategy": "Sector Rotation",
                "icon": "\U0001f504",
            })
        except Exception as e:
            log.debug(f"sector_rotation({etf}): {e}")

    results.sort(key=lambda x: -x.get("rs_vs_spy_pct", 0))
    return results


def scan_from_archive() -> list[dict]:
    try:
        # Sector ETFs via EODHD
        from data_fetcher import fetch_market_data
        ohlcv = fetch_market_data(SECTOR_ETFS + ["SPY"], period="1y")
        if not ohlcv.get("SPY") is not None:
            pass
        if "SPY" not in ohlcv:
            log.warning("No SPY data for sector rotation")
            return []
        return scan(ohlcv)
    except Exception as e:
        log.error(f"scan_from_archive: {e}")
        return []
