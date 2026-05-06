"""
pullback_scanner.py — Minervini/O'Neil Pullback Scanner.

Simple rules, no scoring:
  1. Stock hit 52-week high in last 20 trading days
  2. Currently pulled back 3-8% from that high
  3. Price within 1 ATR of rising EMA21
  4. Volume below 20-day average (low-volume pullback = healthy)
  5. TRIGGER: daily close > prior day's high AND volume > 20d avg

Returns list of candidates with status: WAITING / TRIGGERED / MISSED
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("pullback_scanner")


def scan(ohlcv: dict[str, pd.DataFrame], min_pullback: float = 0.03,
         max_pullback: float = 0.10, lookback_high: int = 20) -> list[dict]:
    """
    Scan universe for pullback setups.

    Args:
        ohlcv: {ticker: DataFrame with Open/High/Low/Close/Volume columns}
        min_pullback: minimum pullback from 52wk high (default 3%)
        max_pullback: maximum pullback (default 10% — beyond this, trend may be broken)
        lookback_high: days to check for 52wk high recency (default 20)

    Returns: list of dicts sorted by status (TRIGGERED first, then WAITING)
    """
    results = []

    for ticker, df in ohlcv.items():
        try:
            if df is None or df.empty or len(df) < 60:
                continue

            c = df["Close"].squeeze()
            h = df["High"].squeeze()
            l = df["Low"].squeeze()
            v = df["Volume"].squeeze() if "Volume" in df.columns else None

            if len(c) < 60:
                continue

            price = float(c.iloc[-1])
            if price <= 0:
                continue

            # ── Criterion 1: 52-week high in last N days ──
            high_252 = float(h.tail(252).max()) if len(h) >= 252 else float(h.max())
            # When was the high hit? Find the most recent bar within 2% of 52wk high
            recent_bars = h.tail(lookback_high)
            hit_near_high = any(float(bar) >= high_252 * 0.98 for bar in recent_bars)
            if not hit_near_high:
                continue

            # ── Criterion 2: Pulled back 3-8% from high ──
            pullback_pct = (high_252 - price) / high_252
            if pullback_pct < min_pullback or pullback_pct > max_pullback:
                continue

            # ── Criterion 3: Price near rising EMA21 ──
            ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
            ema21_prev = float(c.ewm(span=21, adjust=False).mean().iloc[-6])
            ema21_rising = ema21 > ema21_prev

            if not ema21_rising:
                continue

            atr_14 = float((h - l).tail(14).mean())
            dist_from_ema = abs(price - ema21)
            if dist_from_ema > atr_14 * 1.5:
                continue

            # ── Criterion 4: Low volume pullback ──
            if v is None or len(v) < 20:
                continue
            avg_vol = float(v.tail(20).mean())
            today_vol = float(v.iloc[-1])
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0

            # ── Criterion 5: Trigger check ──
            prior_high = float(h.iloc[-2]) if len(h) >= 2 else price
            triggered = price > prior_high and vol_ratio > 1.0

            # Low volume on pullback (avg of last 5 days vs 20-day avg)
            recent_vol_avg = float(v.tail(5).mean())
            pullback_low_vol = (recent_vol_avg / avg_vol) < 0.9 if avg_vol > 0 else False

            # ── Pullback low (for stop) ──
            pullback_bars = c.tail(lookback_high)
            pullback_low = float(l.tail(lookback_high).min())

            # ── Status ──
            if triggered:
                status = "TRIGGERED"
            elif pullback_pct < min_pullback + 0.01:
                status = "MISSED"  # barely pulled back, might have already bounced
            elif not pullback_low_vol:
                status = "WATCHING"  # volume not yet dried up
            else:
                status = "WAITING"

            # ── R:R calculation ──
            stop = pullback_low - atr_14 * 0.3  # small buffer below pullback low
            target = high_252  # retest of 52-week high
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                continue  # not enough reward

            # ── EMA50 check (trend health) ──
            ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1]) if len(c) >= 50 else None
            above_ema50 = price > ema50 if ema50 else None

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "high_52w": round(high_252, 2),
                "pullback_pct": round(pullback_pct * 100, 1),
                "ema21": round(ema21, 2),
                "ema21_dist_pct": round((price - ema21) / ema21 * 100, 1),
                "ema21_rising": ema21_rising,
                "ema50": round(ema50, 2) if ema50 else None,
                "above_ema50": above_ema50,
                "atr": round(atr_14, 2),
                "vol_ratio": round(vol_ratio, 2),
                "pullback_vol_ratio": round(recent_vol_avg / avg_vol, 2) if avg_vol > 0 else None,
                "status": status,
                "triggered": triggered,
                "prior_high": round(prior_high, 2),
                "trigger_price": round(prior_high, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "rr": round(rr, 1),
                "risk_dollars": round(risk, 2),
                "pullback_low": round(pullback_low, 2),
                "criteria": {
                    "new_high_20d": True,
                    "pullback_3_8pct": True,
                    "near_ema21": True,
                    "ema21_rising": True,
                    "low_vol_pullback": pullback_low_vol,
                    "volume_trigger": triggered,
                    "above_ema50": above_ema50,
                },
            })

        except Exception as e:
            log.debug(f"pullback_scanner({ticker}): {e}")
            continue

    # Sort: TRIGGERED first, then WAITING, then others. Within each, by R:R desc.
    status_order = {"TRIGGERED": 0, "WAITING": 1, "WATCHING": 2, "MISSED": 3}
    results.sort(key=lambda x: (status_order.get(x["status"], 9), -x["rr"]))

    return results


def scan_from_archive() -> list[dict]:
    """Convenience: load OHLCV from data archive and run scan."""
    try:
        from data_archive import load_all
        ohlcv = load_all()
        if not ohlcv:
            log.warning("No archive data available")
            return []
        return scan(ohlcv)
    except Exception as e:
        log.error(f"scan_from_archive failed: {e}")
        return []


if __name__ == "__main__":
    results = scan_from_archive()
    print(f"\n{'='*70}")
    print(f"  PULLBACK SCANNER — {len(results)} candidates")
    print(f"{'='*70}\n")

    triggered = [r for r in results if r["status"] == "TRIGGERED"]
    waiting = [r for r in results if r["status"] == "WAITING"]

    if triggered:
        print(f"  🟢 TRIGGERED ({len(triggered)}) — BUY at next open\n")
        for r in triggered:
            print(f"    {r['ticker']:<6} ${r['price']:<8} off high {r['pullback_pct']}%  "
                  f"vol {r['vol_ratio']}x  R:R {r['rr']}:1")
            print(f"           Stop: ${r['stop']}  Target: ${r['target']} (52w high)")

    if waiting:
        print(f"\n  ⏳ WAITING ({len(waiting)}) — watch for volume trigger\n")
        for r in waiting[:10]:
            print(f"    {r['ticker']:<6} ${r['price']:<8} off high {r['pullback_pct']}%  "
                  f"vol {r['vol_ratio']}x  R:R {r['rr']}:1")
            print(f"           Trigger: close > ${r['trigger_price']} on vol > 1.0x")
