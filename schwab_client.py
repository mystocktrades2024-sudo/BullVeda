"""
schwab_client.py — REST wrappers over Schwab Market Data API.

All calls use the access token from schwab_auth.get_access_token() which
auto-refreshes every 30 minutes.

Endpoints wrapped:
  - get_quote(symbol)              — single-symbol quote + fundamentals
  - get_quotes_batch(symbols)      — batch quote (up to 500/call)
  - get_pricehistory(symbol, ...)  — OHLCV bars
  - get_chains(symbol, ...)        — option chain with greeks
  - get_movers(index, ...)         — top movers by index
  - get_markethours(markets, date) — trading hours

Design choices:
  - Fail-soft: network errors return None, caller uses fallback
  - Respectful rate limiting: sleep on 429, exponential backoff
  - Translate Schwab quote schema → our internal get_stock_info contract
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

import requests

import schwab_auth as _sa

log = logging.getLogger("schwab_client")

API_BASE = "https://api.schwabapi.com/marketdata/v1"

# Rate limit: Schwab allows ~120 req/min. We pace to 100/min to leave headroom.
_MIN_GAP_S = 0.55
_LAST_CALL: list[float] = [0.0]


def _throttle() -> None:
    now = time.time()
    gap = now - _LAST_CALL[0]
    if gap < _MIN_GAP_S:
        time.sleep(_MIN_GAP_S - gap)
    _LAST_CALL[0] = time.time()


def _headers() -> dict:
    return {"Authorization": f"Bearer {_sa.get_access_token()}", "Accept": "application/json"}


def _get(path: str, params: Optional[dict] = None, retries: int = 2, timeout: int = 15) -> Optional[dict]:
    url = f"{API_BASE}{path}"
    for attempt in range(retries + 1):
        _throttle()
        try:
            r = requests.get(url, headers=_headers(), params=params or {}, timeout=timeout)
        except requests.RequestException as e:
            log.debug(f"schwab GET {path} network error: {e}")
            if attempt < retries:
                time.sleep(1.5 ** attempt)
                continue
            return None
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code == 429:
            # Rate limited — back off and retry
            retry_after = int(r.headers.get("Retry-After", "2"))
            time.sleep(min(retry_after, 10))
            continue
        if r.status_code == 401:
            # Token likely expired mid-flight — force refresh once
            _sa._refresh_access_token()
            continue
        log.debug(f"schwab GET {path} HTTP {r.status_code}: {r.text[:200]}")
        return None
    return None


# ── Quotes ──────────────────────────────────────────────────────────────
def get_quote(symbol: str) -> Optional[dict]:
    """Single-symbol quote with fundamental. Returns the blob keyed by symbol, or None."""
    data = _get(f"/{symbol}/quotes", params={"fields": "quote,fundamental,reference"})
    if not data:
        return None
    return data.get(symbol.upper()) or next(iter(data.values()), None)


def get_quotes_batch(symbols: Iterable[str], chunk_size: int = 500) -> dict[str, dict]:
    """Batch quotes. Chunks requests at 500 symbols each (Schwab cap)."""
    out: dict[str, dict] = {}
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return out
    for i in range(0, len(syms), chunk_size):
        chunk = syms[i:i + chunk_size]
        data = _get("/quotes", params={"symbols": ",".join(chunk), "fields": "quote,fundamental,reference"})
        if data:
            out.update(data)
    return out


# ── Price history ───────────────────────────────────────────────────────
def get_pricehistory(
    symbol: str,
    period_type: str = "year",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
    need_extended: bool = False,
) -> Optional[dict]:
    """
    OHLCV history. Returns {candles: [{open, high, low, close, volume, datetime}]}.

    Default = 1 year of daily bars (what the archive uses).
    For intraday: period_type='day', period=10, frequency_type='minute', frequency=5.
    """
    params = {
        "symbol":              symbol.upper(),
        "periodType":          period_type,
        "period":              period,
        "frequencyType":       frequency_type,
        "frequency":           frequency,
        "needExtendedHoursData": str(need_extended).lower(),
    }
    return _get("/pricehistory", params=params)


# ── Option chains ───────────────────────────────────────────────────────
def get_chains(
    symbol: str,
    contract_type: str = "ALL",
    strike_count: int = 10,
    include_underlying: bool = True,
    strategy: str = "SINGLE",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Optional[dict]:
    """Option chain. contract_type: CALL, PUT, ALL."""
    params: dict = {
        "symbol":           symbol.upper(),
        "contractType":     contract_type,
        "strikeCount":      strike_count,
        "includeUnderlyingQuote": str(include_underlying).lower(),
        "strategy":         strategy,
    }
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date
    return _get("/chains", params=params)


# ── Movers ──────────────────────────────────────────────────────────────
def get_movers(
    index: str = "$SPX",
    direction: str = "up",
    change: str = "percent",
) -> Optional[list]:
    """
    Top movers. index: $SPX, $COMPX, $DJI, NYSE, NASDAQ.
    direction: up/down. change: value/percent.
    """
    data = _get(f"/movers/{index}", params={"sort": direction.upper(), "frequency": 0})
    if data:
        return data.get("screeners", [])
    return None


# ── Market hours ────────────────────────────────────────────────────────
def get_markethours(markets: str = "equity", date: Optional[str] = None) -> Optional[dict]:
    """markets: equity, option, bond, future, forex. date: YYYY-MM-DD (default today)."""
    params: dict = {"markets": markets}
    if date:
        params["date"] = date
    return _get("/markets", params=params)


# ── Translators — Schwab schema → internal contract ─────────────────────
def translate_quote_to_stock_info(symbol: str, blob: dict) -> dict:
    """
    Convert Schwab /quotes response blob to our get_stock_info dict.
    Fills the same fields yfinance .info would. Missing deep fields (margins,
    growth, D/E, FCF, beta, price-to-book, etc.) stay None so caller can fall
    through to yfinance.

    Schwab fundamental fields (actual set):
      avg10DaysVolume, avg1YearVolume, declarationDate, divAmount, divExDate,
      divFreq, divPayAmount, divPayDate, divYield, eps, fundLeverageFactor,
      lastEarningsDate, nextDivExDate, nextDivPayDate, peRatio, sharesOutstanding.
    52-week range lives in the quote object (52WeekHigh / 52WeekLow).
    """
    q = blob.get("quote") or {}
    f = blob.get("fundamental") or {}
    r = blob.get("reference") or {}
    shares_out = f.get("sharesOutstanding") or 0
    last_price = q.get("lastPrice") or 0
    market_cap = (shares_out * last_price) if (shares_out and last_price) else 0

    # ── KPI derivations (2026-04-15) ─────────────────────────────────────
    import time as _time
    from datetime import datetime as _dt, timezone as _tz

    # 1. Quote freshness (seconds ago)
    qtime_ms = q.get("quoteTime") or q.get("tradeTime") or 0
    quote_age_s = int(_time.time() - qtime_ms / 1000) if qtime_ms else None

    # 2. Bid-ask spread in bp
    bid, ask = q.get("bidPrice") or 0, q.get("askPrice") or 0
    mid = (bid + ask) / 2 if (bid and ask) else 0
    spread_bp = round((ask - bid) / mid * 10_000, 1) if mid > 0 else None

    # 3. Post-market % change
    pm_pct = q.get("postMarketPercentChange")

    # 4. Distance from 52wk high / low
    hi52 = q.get("52WeekHigh") or 0
    lo52 = q.get("52WeekLow") or 0
    dist_from_hi_pct = round((last_price - hi52) / hi52 * 100, 2) if (hi52 and last_price) else None
    dist_from_lo_pct = round((last_price - lo52) / lo52 * 100, 2) if (lo52 and last_price) else None

    # 5. Days since last earnings
    earnings_iso = f.get("lastEarningsDate") or ""
    days_since_earnings = None
    if earnings_iso:
        try:
            ed = _dt.fromisoformat(earnings_iso.replace("Z", "+00:00"))
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=_tz.utc)
            days_since_earnings = (_dt.now(_tz.utc) - ed).days
        except Exception:
            pass

    # Bonus: leverage factor (identifies TQQQ-style 3x ETFs)
    leverage_factor = f.get("fundLeverageFactor") or None
    return {
        "ticker":           symbol,
        "name":             r.get("description", symbol),
        "sector":           r.get("sector") or "Unknown",
        "industry":         r.get("industry") or "Unknown",
        "market_cap":       market_cap,
        "pe_ratio":         f.get("peRatio"),
        "forward_pe":       None,                          # Schwab doesn't provide
        "peg_ratio":        None,                          # Schwab doesn't provide
        "price_to_book":    None,                          # Schwab doesn't provide
        "ps_ratio":         None,                          # Schwab doesn't provide
        "beta":             None,                          # Schwab doesn't provide
        "dividend_yield":   f.get("divYield"),
        "dividend_amount":  f.get("divAmount"),
        "trailing_eps":     f.get("eps"),
        "52w_high":         q.get("52WeekHigh"),
        "52w_low":          q.get("52WeekLow"),
        "avg_volume":       f.get("avg10DaysVolume") or f.get("avg1YearVolume"),
        "shares_float":     shares_out,
        "short_pct":        None,                          # Schwab doesn't provide
        "last_earnings":    f.get("lastEarningsDate"),
        "next_earnings":    None,                          # not exposed on Individual API tier
        # Live price context (not strictly in get_stock_info contract, but useful)
        "_last_price":      q.get("lastPrice"),
        "_bid":             q.get("bidPrice"),
        "_ask":             q.get("askPrice"),
        "_volume":          q.get("totalVolume"),
        "_delayed":         q.get("delayed", False),
        # Fields Schwab doesn't provide — stay None, caller may fill via yfinance
        "revenue_growth":   None,
        "earnings_growth":  None,
        "profit_margin":    None,
        "gross_margin":     None,
        "operating_margin": None,
        "roe":              None,
        "roa":              None,
        "debt_to_equity":   None,
        "current_ratio":    None,
        "free_cashflow":    None,
        "operating_cashflow": None,
        "total_cash":       None,
        "earnings_qoq_growth": None,
        "forward_eps":      None,
        "forward_eps_growth": None,
        "price_to_cashflow": None,
        "target_mean_price": None,
        "target_high_price": None,
        "target_low_price":  None,
        "recommendation":    None,
        "num_analysts":      None,
        "institutional_pct": None,
        "ev_to_ebitda":      None,
        "error":             None,
        "_cache_source":     "schwab",
        # ── KPI fields (2026-04-15, from Schwab live data) ──
        "kpi_quote_age_s":         quote_age_s,
        "kpi_spread_bp":           spread_bp,
        "kpi_post_market_pct":     pm_pct,
        "kpi_dist_from_52wk_high_pct": dist_from_hi_pct,
        "kpi_dist_from_52wk_low_pct":  dist_from_lo_pct,
        "kpi_days_since_earnings": days_since_earnings,
        "kpi_leverage_factor":     leverage_factor,
    }


def pricehistory_to_df(ph: dict):
    """Convert Schwab pricehistory response to a DataFrame matching data_archive format."""
    import pandas as pd
    if not ph or not ph.get("candles"):
        return None
    rows = ph["candles"]
    df = pd.DataFrame(rows)
    # Convert epoch ms → UTC timestamp
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
    df = df.rename(columns={"datetime": "t", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"})
    df = df.set_index("t")
    return df[["Open", "High", "Low", "Close", "Volume"]]


# ── Smoke test CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "quote":
        sym = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        blob = get_quote(sym)
        if blob:
            info = translate_quote_to_stock_info(sym, blob)
            print(json.dumps(info, indent=2, default=str))
        else:
            print("No data")

    elif cmd == "batch":
        syms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["AAPL", "NVDA", "MSFT", "TSLA"]
        t = time.time()
        data = get_quotes_batch(syms)
        print(f"Got {len(data)} quotes in {time.time()-t:.2f}s")
        for s, blob in data.items():
            q = blob.get("quote") or {}
            f = blob.get("fundamental") or {}
            print(f"  {s:<6} ${q.get('lastPrice','?')}  PE={f.get('peRatio','?')}  Mcap=${f.get('marketCap',0):,.0f}")

    elif cmd == "chain":
        sym = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        c = get_chains(sym, strike_count=5)
        if c:
            print(f"Underlying: ${c.get('underlyingPrice','?')}  Puts: {c.get('numberOfContracts','?')}")
            call_map = c.get("callExpDateMap", {})
            for exp, strikes in list(call_map.items())[:2]:
                print(f"  {exp}: {len(strikes)} strikes")

    elif cmd == "movers":
        idx = sys.argv[2] if len(sys.argv) > 2 else "$SPX"
        m = get_movers(idx)
        if m:
            print(f"{idx} movers: {len(m)} items")
            for row in m[:5]:
                print(f"  {row.get('symbol')}  {row.get('description','')[:30]:<30}  {row.get('netPercentChange'):+.2f}%")

    elif cmd == "markets":
        mh = get_markethours()
        print(json.dumps(mh, indent=2, default=str)[:1000])

    elif cmd == "history":
        sym = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        ph = get_pricehistory(sym)
        df = pricehistory_to_df(ph)
        if df is not None:
            print(f"{sym}: {len(df)} bars, last={df.index[-1]}")
            print(df.tail(3))

    else:
        print(__doc__)
