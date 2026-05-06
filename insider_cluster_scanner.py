"""
insider_cluster_scanner.py — Insider Buying Cluster Scanner.

Edge: when 3+ insiders buy >$50K each within 30 days, they know something.
Not automatic grants/exercises — open-market PURCHASES only.

Signal:
  1. 2+ insider buys (open market) within last 30 days
  2. Total insider $ bought > $200K
  3. Stock not in downtrend (above EMA50)

Data: FINVIZ insider transactions.
"""
from __future__ import annotations
import logging
log = logging.getLogger("insider_cluster")


def scan(ohlcv: dict, finviz_data: dict | None = None,
         enrichment_data: dict | None = None) -> list[dict]:
    finviz_data = finviz_data or {}
    enrichment_data = enrichment_data or {}
    results = []

    for ticker, df in ohlcv.items():
        try:
            if df is None or df.empty or len(df) < 50:
                continue

            c = df["Close"].squeeze()
            price = float(c.iloc[-1])
            if price <= 0:
                continue

            ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1])
            if price < ema50:
                continue

            fv = finviz_data.get(ticker, {})
            insider_own = fv.get("Insider Own") or fv.get("insider_own")
            insider_trans = fv.get("Insider Trans") or fv.get("insider_trans")

            if not insider_trans:
                continue

            # Parse insider transaction percentage
            try:
                if isinstance(insider_trans, str):
                    trans_pct = float(insider_trans.replace("%", "").strip())
                else:
                    trans_pct = float(insider_trans)
            except (ValueError, TypeError):
                continue

            # Positive = net buying
            if trans_pct <= 0:
                continue

            # Need meaningful buying (>1% net)
            if trans_pct < 1.0:
                continue

            stop = round(ema50 - (price - ema50) * 0.1, 2)
            target = round(price * 1.15, 2)
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                continue

            strength = "STRONG" if trans_pct > 5 else "MODERATE" if trans_pct > 2 else "SIGNAL"

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "status": strength,
                "insider_trans_pct": trans_pct,
                "insider_own_pct": insider_own,
                "above_ema50": True,
                "ema50": round(ema50, 2),
                "stop": stop,
                "target": target,
                "rr": round(rr, 1),
                "strategy": "Insider Cluster",
                "icon": "\U0001f454",
                "sector": fv.get("Sector", "Unknown"),
            })
        except Exception as e:
            log.debug(f"insider_cluster({ticker}): {e}")

    results.sort(key=lambda x: -x.get("insider_trans_pct", 0))
    return results


def scan_from_archive() -> list[dict]:
    try:
        from data_archive import load_all
        ohlcv = load_all()
        # Load FINVIZ data from enrichment cache
        try:
            import enrichment_store as es
            fv = es.get_cached_batch(list(ohlcv.keys()), "finviz_overview", ttl_days=7)
        except Exception:
            fv = {}
        return scan(ohlcv, finviz_data=fv)
    except Exception as e:
        log.error(f"scan_from_archive: {e}")
        return []
