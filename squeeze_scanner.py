"""
squeeze_scanner.py — Short Squeeze Setup Scanner.

Edge: high short interest + stock starting to rise = shorts trapped.
Forced covering creates self-reinforcing rally.

Signal:
  1. Short float > 15% (heavily shorted)
  2. Days to cover > 3 (takes days to unwind)
  3. RSI turning up from below 40 (momentum shift)
  4. Volume expanding (squeeze starting)
  5. Price above EMA21 or reclaiming it

Entry: when RSI crosses above 40 on volume
Hold: 5-15 days (squeezes are fast and violent)
Stop: below recent swing low
Target: +15-25% (squeezes overshoot)
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
log = logging.getLogger("squeeze_scanner")


def scan(ohlcv: dict[str, pd.DataFrame],
         fundamentals: dict[str, dict] | None = None,
         finviz_data: dict[str, dict] | None = None) -> list[dict]:
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

            # ── Short float data ──
            fund = fundamentals.get(ticker, {})
            fv = finviz_data.get(ticker, {})

            short_float = None
            for src in [fund.get("short_float"), fund.get("short_pct"),
                       fv.get("Short Float"), fv.get("short_float")]:
                if src:
                    try:
                        sf = str(src).replace("%", "").strip()
                        short_float = float(sf)
                        if short_float > 1:  # already percentage
                            pass
                        else:
                            short_float *= 100  # convert decimal to pct
                        break
                    except (ValueError, TypeError):
                        continue

            if short_float is None or short_float < 15:
                continue

            # ── RSI calculation ──
            delta = c.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi_now = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50
            rsi_prev = float(rsi.iloc[-2]) if len(rsi) >= 2 and not np.isnan(rsi.iloc[-2]) else 50

            # RSI turning up from low level
            rsi_turning = rsi_now > rsi_prev and rsi_now < 60

            if not rsi_turning:
                continue

            # ── Volume expansion ──
            avg_vol = float(v.tail(20).mean())
            recent_vol = float(v.tail(3).mean())
            vol_expanding = (recent_vol / avg_vol) > 1.2 if avg_vol > 0 else False

            # ── EMA21 check ──
            ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
            near_ema = abs(price - ema21) / ema21 < 0.03

            # ── Trade plan ──
            swing_low = float(l.tail(10).min())
            stop = round(swing_low - (price - swing_low) * 0.1, 2)
            target = round(price * 1.20, 2)  # 20% squeeze target
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 2.0:
                continue

            # ── Status ──
            if vol_expanding and rsi_turning and near_ema:
                status = "SETUP"
            elif vol_expanding and rsi_turning:
                status = "BUILDING"
            else:
                status = "EARLY"

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "status": status,
                "short_float_pct": round(short_float, 1),
                "rsi": round(rsi_now, 1),
                "rsi_turning": rsi_turning,
                "vol_expanding": vol_expanding,
                "vol_ratio": round(recent_vol / avg_vol, 2) if avg_vol > 0 else 0,
                "near_ema21": near_ema,
                "ema21": round(ema21, 2),
                "stop": stop,
                "target": target,
                "rr": round(rr, 1),
                "strategy": "Short Squeeze",
                "icon": "\U0001f680",
                "sector": fund.get("sector") or fv.get("Sector", "Unknown"),
            })
        except Exception as e:
            log.debug(f"squeeze_scanner({ticker}): {e}")

    results.sort(key=lambda x: ({"SETUP": 0, "BUILDING": 1, "EARLY": 2}.get(x["status"], 9), -x["short_float_pct"]))
    return results


def scan_from_archive() -> list[dict]:
    try:
        from data_archive import load_all
        import fundamentals_store as fs
        ohlcv = load_all()
        fund_df = fs.load_df()
        fund_dict = {t: fund_df.loc[t].to_dict() for t in ohlcv if t in fund_df.index}

        # Also try FINVIZ bulk data for short float (fundamentals_store often lacks it)
        fv = {}
        try:
            from data_fetcher import get_finviz_bulk
            fv_raw = get_finviz_bulk(["overview"])
            if fv_raw:
                for t, data in fv_raw.items():
                    if data.get("Short Float"):
                        fund_dict.setdefault(t, {})["short_float"] = data["Short Float"]
        except Exception:
            pass

        return scan(ohlcv, fundamentals=fund_dict, finviz_data=fv)
    except Exception as e:
        log.error(f"scan_from_archive: {e}")
        return []
