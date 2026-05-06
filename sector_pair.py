"""
S-6: Sector RS Pair Trade Finder (market-neutral)

Generates long/short sector ETF pair candidates for risk-off / panic regimes
when directional longs are blocked.

Methodology:
  1. Pull 11 sector ETFs (XLK / XLE / XLF / XLV / XLU / XLY / XLP / XLI / XLB / XLRE / XLC)
  2. Compute 21d and 63d relative strength (return) for each
  3. Rank by recent (21d) momentum
  4. Pair: long the strongest sector + short the weakest, when:
     - RS spread > 8% (clear divergence)
     - Both have sufficient liquidity (ADV > $50M for sector ETFs always met)
     - Correlation < 0.85 (otherwise pair is just leverage on the spread)

Output structured for v2 dashboard consumption — call from build_data.py
or surface as a separate dashboard tab.

NOTE: This MVP uses simple RS spreads. Future improvements:
  - Cointegration test (Engle-Granger / Johansen) for pair stability
  - Z-score normalization of the spread for entry timing
  - Hedge ratio via OLS regression (currently 1:1 dollar-neutral)
"""
from __future__ import annotations
from typing import Optional
import json
from pathlib import Path

SECTOR_ETFS = {
    "XLK":  "Technology",
    "XLE":  "Energy",
    "XLF":  "Financials",
    "XLV":  "Health Care",
    "XLU":  "Utilities",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLI":  "Industrials",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication",
}


def _pct_return(closes: list, n: int) -> Optional[float]:
    if not closes or len(closes) < n + 1:
        return None
    a, b = closes[-n - 1], closes[-1]
    if a <= 0:
        return None
    return (b - a) / a * 100


def find_sector_pairs(min_spread_pct: float = 8.0,
                      max_correlation: float = 0.85,
                      lookback_short: int = 21,
                      lookback_long: int = 63) -> dict:
    """
    Find sector pair-trade candidates.

    Returns:
      {
        "pairs":   [ { long, short, spread_21d, spread_63d, correlation, narrative, ... } ],
        "rs_table": { ticker: { rs_21d, rs_63d, rank } },
        "n_pairs": int,
        "regime_filter": "all" | "risk_off",
        "computed_at": iso timestamp,
      }
    """
    import datetime as _dt
    out = {
        "pairs": [],
        "rs_table": {},
        "n_pairs": 0,
        "computed_at": _dt.datetime.now().isoformat(),
    }

    try:
        import eodhd_client as _e
    except Exception as e:
        out["error"] = f"eodhd_client unavailable: {e}"
        return out

    # Fetch 90d of EOD for each sector ETF
    histories = {}
    for sym in SECTOR_ETFS:
        try:
            from datetime import date, timedelta
            from_d = (date.today() - timedelta(days=130)).isoformat()
            rows = _e.eod(sym, from_date=from_d)
            if rows and isinstance(rows, list) and len(rows) >= lookback_long + 5:
                closes = [float(r.get("adjusted_close") or r.get("close") or 0) for r in rows if r.get("close") is not None]
                if len(closes) >= lookback_long + 5:
                    histories[sym] = closes
        except Exception:
            continue

    if len(histories) < 2:
        out["error"] = f"Only {len(histories)} sector histories fetched — need ≥2"
        return out

    # Compute RS metrics
    rs_data = []
    for sym, closes in histories.items():
        rs_21 = _pct_return(closes, lookback_short)
        rs_63 = _pct_return(closes, lookback_long)
        if rs_21 is None or rs_63 is None:
            continue
        rs_data.append({"ticker": sym, "name": SECTOR_ETFS[sym],
                        "rs_21d": round(rs_21, 2), "rs_63d": round(rs_63, 2)})

    rs_data.sort(key=lambda x: x["rs_21d"], reverse=True)
    for i, r in enumerate(rs_data):
        r["rank"] = i + 1
        out["rs_table"][r["ticker"]] = r

    # Compute pairwise correlations of daily returns
    def _daily_ret(closes):
        return [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]

    def _corr(a, b):
        n = min(len(a), len(b))
        if n < 20: return None
        a, b = a[-n:], b[-n:]
        ma = sum(a) / n; mb = sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((x - mb) ** 2 for x in b) ** 0.5
        if da == 0 or db == 0: return None
        return num / (da * db)

    # Build pair candidates: top 3 vs bottom 3
    n = len(rs_data)
    if n < 4:
        out["error"] = "Not enough sectors with valid RS data"
        return out

    top3    = rs_data[:3]
    bottom3 = rs_data[-3:]

    for long_t in top3:
        for short_t in bottom3:
            if long_t["ticker"] == short_t["ticker"]:
                continue
            spread_21 = long_t["rs_21d"] - short_t["rs_21d"]
            spread_63 = long_t["rs_63d"] - short_t["rs_63d"]
            if spread_21 < min_spread_pct:
                continue
            corr = _corr(_daily_ret(histories[long_t["ticker"]]),
                          _daily_ret(histories[short_t["ticker"]]))
            if corr is None or corr > max_correlation:
                continue

            out["pairs"].append({
                "long":        long_t["ticker"],
                "long_name":   long_t["name"],
                "short":       short_t["ticker"],
                "short_name":  short_t["name"],
                "spread_21d":  round(spread_21, 2),
                "spread_63d":  round(spread_63, 2),
                "correlation": round(corr, 3) if corr is not None else None,
                "long_rs_21d":  long_t["rs_21d"],
                "short_rs_21d": short_t["rs_21d"],
                "narrative": (
                    f"Long {long_t['ticker']} ({long_t['name']}) / Short {short_t['ticker']} ({short_t['name']}) — "
                    f"21d RS spread {spread_21:.1f}% · ρ={corr:.2f}. "
                    f"Market-neutral exposure: profits if {long_t['name']} continues to outperform "
                    f"{short_t['name']} regardless of broad market direction."
                ),
            })

    out["pairs"].sort(key=lambda p: p["spread_21d"], reverse=True)
    out["n_pairs"] = len(out["pairs"])
    return out


if __name__ == "__main__":
    r = find_sector_pairs()
    print(json.dumps(r, indent=2))
