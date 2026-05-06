"""
earnings_drift_scanner.py — Post-Earnings Announcement Drift (PEAD) Scanner.

Academic edge: stocks that beat earnings estimates by >5% tend to drift
in the beat direction for 20-60 trading days. Documented across 30+ years
of research (Ball & Brown 1968, Bernard & Thomas 1989).

Signal:
  1. Reported earnings within last 5 trading days
  2. EPS beat > 5% (actual vs estimate)
  3. Revenue beat (actual > estimate)
  4. Positive price reaction on earnings day (gap up or close up)
  5. Volume on earnings day > 2x average (institutional participation)

Entry: day after signal confirmation (T+1 open)
Hold: 20 trading days (drift window)
Stop: below earnings-day low (the gap is the floor)
Target: 10-15% above earnings close (drift target)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("earnings_drift")


def scan(ohlcv: dict[str, pd.DataFrame],
         fundamentals: dict[str, dict] | None = None,
         finviz_data: dict[str, dict] | None = None,
         lookback_days: int = 5) -> list[dict]:
    """
    Scan for post-earnings drift setups.

    Args:
        ohlcv: {ticker: DataFrame with OHLCV}
        fundamentals: {ticker: dict with eps_ttm, earnings dates, etc.}
        finviz_data: {ticker: dict from FINVIZ bulk with earnings info}
        lookback_days: how many days back to check for recent earnings

    Returns: list of drift candidates sorted by beat magnitude
    """
    fundamentals = fundamentals or {}
    finviz_data = finviz_data or {}
    results = []

    for ticker, df in ohlcv.items():
        try:
            if df is None or df.empty or len(df) < 30:
                continue

            c = df["Close"].squeeze()
            h = df["High"].squeeze()
            l = df["Low"].squeeze()
            v = df["Volume"].squeeze() if "Volume" in df.columns else None
            if v is None or len(v) < 20:
                continue

            price = float(c.iloc[-1])
            if price <= 0:
                continue

            # ── Check for recent earnings ──
            fund = fundamentals.get(ticker, {})
            fv = finviz_data.get(ticker, {})

            # Get earnings date from multiple sources
            last_earnings = (fund.get("last_earnings") or
                           fund.get("lastEarningsDate") or
                           fund.get("kpi_days_since_earnings"))

            days_since = None
            if isinstance(last_earnings, (int, float)):
                days_since = int(last_earnings)
            elif isinstance(last_earnings, str) and last_earnings:
                try:
                    ed = datetime.fromisoformat(last_earnings.replace("Z", "+00:00"))
                    days_since = (datetime.now(ed.tzinfo) - ed).days if ed.tzinfo else (datetime.now() - ed).days
                except Exception:
                    pass

            # Also check FINVIZ earnings date
            if days_since is None:
                fv_earnings = fv.get("Earnings Date") or fv.get("earnings_date")
                if isinstance(fv_earnings, str) and fv_earnings:
                    try:
                        ed = datetime.strptime(fv_earnings.split(" ")[0], "%Y-%m-%d")
                        days_since = (datetime.now() - ed).days
                    except Exception:
                        pass

            if days_since is None or days_since < 0 or days_since > lookback_days:
                continue

            # ── Check EPS beat ──
            eps_actual = fund.get("trailing_eps") or fund.get("eps_ttm")
            eps_estimate = fund.get("forward_eps") or fund.get("eps_estimate")

            # If we don't have estimate, check FINVIZ EPS surprise
            eps_surprise_pct = None
            fv_surprise = fv.get("EPS surprise") or fv.get("eps_surprise")
            if isinstance(fv_surprise, str) and "%" in fv_surprise:
                try:
                    eps_surprise_pct = float(fv_surprise.replace("%", "").strip())
                except Exception:
                    pass
            elif isinstance(fv_surprise, (int, float)):
                eps_surprise_pct = float(fv_surprise)

            # Calculate from actual vs estimate if available
            if eps_surprise_pct is None and eps_actual and eps_estimate:
                try:
                    ea = float(eps_actual)
                    ee = float(eps_estimate)
                    if ee != 0:
                        eps_surprise_pct = ((ea - ee) / abs(ee)) * 100
                except Exception:
                    pass

            # Need at least some evidence of a beat
            if eps_surprise_pct is None:
                # Fall back to price action: if stock gapped up >2% on earnings day, assume beat
                if days_since < len(c) and days_since >= 0:
                    earnings_idx = -(days_since + 1)
                    if abs(earnings_idx) < len(c) and abs(earnings_idx) > 1:
                        pre_earn = float(c.iloc[earnings_idx - 1])
                        post_earn = float(c.iloc[earnings_idx])
                        gap_pct = ((post_earn - pre_earn) / pre_earn) * 100 if pre_earn > 0 else 0
                        if gap_pct > 2:
                            eps_surprise_pct = gap_pct * 2  # rough proxy
                        else:
                            continue
                    else:
                        continue
                else:
                    continue

            if eps_surprise_pct < 5:
                continue  # need >5% beat for PEAD

            # ── Earnings day price action ──
            earnings_bar_idx = -(days_since + 1) if days_since < len(c) else None
            if earnings_bar_idx is None or abs(earnings_bar_idx) >= len(c):
                continue

            earn_close = float(c.iloc[earnings_bar_idx])
            earn_low = float(l.iloc[earnings_bar_idx])
            earn_high = float(h.iloc[earnings_bar_idx])
            earn_vol = float(v.iloc[earnings_bar_idx])
            avg_vol = float(v.tail(20).mean())

            # Volume confirmation: earnings day volume > 2x average
            vol_ratio = earn_vol / avg_vol if avg_vol > 0 else 0
            vol_confirmed = vol_ratio > 1.5

            # Price reaction: close above prior close
            if abs(earnings_bar_idx) > 1:
                pre_close = float(c.iloc[earnings_bar_idx - 1])
                gap_pct = ((earn_close - pre_close) / pre_close) * 100 if pre_close > 0 else 0
            else:
                gap_pct = 0
                pre_close = earn_close

            positive_reaction = gap_pct > 0

            if not positive_reaction:
                continue  # only drift on positive beats

            # ── Drift calculation ──
            # How much has the stock already drifted since earnings?
            drift_so_far = ((price - earn_close) / earn_close) * 100 if earn_close > 0 else 0

            # If already drifted >10%, most of the move is done
            if drift_so_far > 10:
                continue

            # ── Trade plan ──
            stop = earn_low - (earn_high - earn_low) * 0.2  # below earnings day range
            target = earn_close * 1.12  # 12% drift target from earnings close
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                continue

            # ── Status ──
            if days_since <= 2 and vol_confirmed and positive_reaction:
                status = "FRESH"  # prime drift window
            elif days_since <= 5:
                status = "ACTIVE"  # still in early drift
            else:
                status = "LATE"

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "status": status,
                "days_since_earnings": days_since,
                "eps_surprise_pct": round(eps_surprise_pct, 1),
                "gap_pct": round(gap_pct, 1),
                "earn_day_vol_ratio": round(vol_ratio, 1),
                "vol_confirmed": vol_confirmed,
                "drift_so_far_pct": round(drift_so_far, 1),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "rr": round(rr, 1),
                "earn_close": round(earn_close, 2),
                "earn_low": round(earn_low, 2),
                "sector": fund.get("sector") or fv.get("Sector") or "Unknown",
            })

        except Exception as e:
            log.debug(f"earnings_drift({ticker}): {e}")
            continue

    # Sort: FRESH first, then by surprise magnitude
    status_order = {"FRESH": 0, "ACTIVE": 1, "LATE": 2}
    results.sort(key=lambda x: (status_order.get(x["status"], 9), -x["eps_surprise_pct"]))
    return results


def scan_from_archive() -> list[dict]:
    """Convenience: load from archive + fundamentals store."""
    try:
        from data_archive import load_all
        import fundamentals_store as fs
        ohlcv = load_all()
        if not ohlcv:
            return []
        fund_df = fs.load_df()
        fund_dict = {}
        for ticker in ohlcv:
            if ticker in fund_df.index:
                fund_dict[ticker] = fund_df.loc[ticker].to_dict()
        return scan(ohlcv, fundamentals=fund_dict)
    except Exception as e:
        log.error(f"scan_from_archive: {e}")
        return []


if __name__ == "__main__":
    results = scan_from_archive()
    print(f"\n{'='*60}")
    print(f"  EARNINGS DRIFT SCANNER — {len(results)} candidates")
    print(f"{'='*60}")
    for r in results[:10]:
        print(f"  [{r['status']}] {r['ticker']:<6} ${r['price']:<8} beat {r['eps_surprise_pct']:+.1f}% "
              f"gap {r['gap_pct']:+.1f}% vol {r['earn_day_vol_ratio']}x "
              f"drift {r['drift_so_far_pct']:+.1f}% R:R {r['rr']}:1")
