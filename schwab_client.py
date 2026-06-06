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
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
) -> Optional[dict]:
    """
    OHLCV history. Returns {candles: [{open, high, low, close, volume, datetime}]}.

    Default = 1 year of daily bars (what the archive uses).
    For intraday: period_type='day', frequency_type='minute', frequency=30, and pass
    start_date/end_date (epoch MS) for a wider window than the period=10 cap — Schwab
    serves minute history back ~250d+ via explicit dates (free, no EODHD quota).
    """
    params = {
        "symbol":              symbol.upper(),
        "periodType":          period_type,
        "frequencyType":       frequency_type,
        "frequency":           frequency,
        "needExtendedHoursData": str(need_extended).lower(),
    }
    # explicit dates override `period` (Schwab ignores period when startDate is set)
    if start_date is not None:
        params["startDate"] = int(start_date)
        if end_date is not None:
            params["endDate"] = int(end_date)
    else:
        params["period"] = period
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


# In-process cache for /markets response — 24h TTL since calendar doesn't change intraday
_MARKET_HOURS_CACHE: dict = {}

def _market_session(date_iso: Optional[str] = None) -> Optional[dict]:
    """Returns the parsed session-hours for the given date (default today).

    Caches the response in-process. Cache key includes the date so different
    dates don't collide. Falls back gracefully when the API is unreachable —
    callers should treat None as "unknown, use your own heuristic."
    """
    import time as _t
    from datetime import datetime as _dt, timezone as _tz
    if date_iso is None:
        date_iso = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    cached = _MARKET_HOURS_CACHE.get(date_iso)
    if cached and (_t.time() - cached["ts"] < 24 * 3600):
        return cached["data"]
    try:
        resp = get_markethours("equity", date=date_iso) or {}
        eq = resp.get("equity") or {}
        # Schwab nests one level deeper — keys are "EQ" / "BOND" etc per product
        product = (eq.get("EQ") or {}) if isinstance(eq, dict) else {}
        data = {
            "date":             product.get("date"),
            "is_open":          bool(product.get("isOpen")),
            "regular_market":   (product.get("sessionHours") or {}).get("regularMarket") or [],
            "pre_market":       (product.get("sessionHours") or {}).get("preMarket") or [],
            "post_market":      (product.get("sessionHours") or {}).get("postMarket") or [],
        }
        _MARKET_HOURS_CACHE[date_iso] = {"ts": _t.time(), "data": data}
        return data
    except Exception:
        return None


def is_market_open_now(include_extended: bool = False) -> bool:
    """Authoritative check using Schwab calendar. Falls back to weekday + 9:30-16:00 ET.

    include_extended=True extends the OK window to pre-market (4:00am ET) +
    post-market (8:00pm ET) per Schwab's session schedule.
    """
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    today_iso = now_utc.strftime("%Y-%m-%d")
    sess = _market_session(today_iso)
    if not sess or not sess.get("is_open"):
        # Schwab says closed (holiday/weekend) — believe it
        if sess is not None:
            return False
        # Schwab API unreachable — fall back to weekday + ET clock check
        now_et = now_utc.astimezone(timezone(timedelta(hours=-4)))  # approx EDT
        if now_et.weekday() >= 5:
            return False
        minutes = now_et.hour * 60 + now_et.minute
        if include_extended:
            return (4 * 60) <= minutes <= (20 * 60)
        return (9 * 60 + 30) <= minutes <= (16 * 60)

    windows = sess.get("regular_market") or []
    if include_extended:
        windows = (sess.get("pre_market") or []) + windows + (sess.get("post_market") or [])
    for w in windows:
        try:
            start = datetime.fromisoformat(w["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
            end   = datetime.fromisoformat(w["end"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if start <= now_utc <= end:
                return True
        except Exception:
            continue
    return False


def market_session_today() -> dict:
    """Returns {date, is_open, regular_start_pt, regular_end_pt, is_half_day}.

    Half-day = regular session shorter than 6h (default 6.5h). Useful for the
    refresh scheduler to know it should stop earlier than 1:30pm PT on those days.
    """
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    today_iso = now_utc.strftime("%Y-%m-%d")
    sess = _market_session(today_iso) or {}
    rm = sess.get("regular_market") or []
    if not rm:
        return {"date": today_iso, "is_open": False, "regular_start_pt": None,
                "regular_end_pt": None, "is_half_day": False}
    try:
        start_utc = datetime.fromisoformat(rm[0]["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
        end_utc   = datetime.fromisoformat(rm[0]["end"].replace("Z", "+00:00")).astimezone(timezone.utc)
        pt = timezone(timedelta(hours=-7))  # approx PDT
        return {
            "date":              today_iso,
            "is_open":           bool(sess.get("is_open")),
            "regular_start_pt":  start_utc.astimezone(pt).strftime("%H:%M"),
            "regular_end_pt":    end_utc.astimezone(pt).strftime("%H:%M"),
            "is_half_day":       (end_utc - start_utc) < timedelta(hours=6),
        }
    except Exception:
        return {"date": today_iso, "is_open": bool(sess.get("is_open")),
                "regular_start_pt": None, "regular_end_pt": None, "is_half_day": False}


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

    # ── 2026-05-19 · Extra fields previously unused ─────────────────────
    # 6. Today's intraday OHLC + net move (free — recomputing from EODHD wastes a fetch)
    today_open  = q.get("openPrice")
    today_high  = q.get("highPrice")
    today_low   = q.get("lowPrice")
    today_close = q.get("closePrice")
    net_change      = q.get("netChange")
    net_pct_change  = q.get("netPercentChange")

    # 7. Microstructure: depth at NBBO + size of last print
    bid_size  = q.get("bidSize")
    ask_size  = q.get("askSize")
    last_size = q.get("lastSize")
    # Bid/ask imbalance — positive means more demand than supply at the spread
    bid_ask_imbalance = None
    if bid_size and ask_size and (bid_size + ask_size) > 0:
        bid_ask_imbalance = round((bid_size - ask_size) / (bid_size + ask_size), 3)

    # 8. Mark price (cleaner than (bid+ask)/2 for after-hours)
    mark      = q.get("mark")
    mark_chg  = q.get("markChange")
    mark_pct  = q.get("markPercentChange")

    # 9. Regular-session vs extended-hours distinction (matters for stop placement)
    rth_last_price = q.get("regularMarketLastPrice")
    rth_last_size  = q.get("regularMarketLastSize")
    rth_last_time  = q.get("regularMarketTradeTime")

    # 10. Historical volatility — sizing input that complements ATR
    hist_vol = q.get("volatility")

    # 11. Security trading status (Normal / Halted / News Pending / Closed / Deleted)
    # IMPORTANT: "Closed" just means outside market hours — NOT a halt. We only
    # block BUYs on actual halts (Halted, News Pending, Deleted).
    sec_status = q.get("securityStatus") or "Normal"
    _sl = sec_status.lower()
    is_halted = _sl in ("halted", "news pending", "deleted") or "halt" in _sl

    # 12. Programmatic asset classification (replaces hardcoded ETF lists)
    # Schwab returns these at the TOP LEVEL of each ticker blob (assetMainType),
    # not inside the reference sub-object. Check both for safety.
    asset_type      = blob.get("assetType") or r.get("assetType") or q.get("assetType")
    asset_main_type = blob.get("assetMainType") or r.get("assetMainType") or q.get("assetMainType")
    asset_sub_type  = blob.get("assetSubType") or r.get("assetSubType") or q.get("assetSubType")
    is_etf = (asset_main_type == "EQUITY" and "ETF" in (asset_sub_type or "").upper()) or \
             (asset_type == "ETF") or \
             ((asset_sub_type or "").upper() == "ETF") or \
             ((asset_main_type or "").upper() == "ETF")

    # 13. Dividend calendar — avoid surprise ex-div drops
    div_ex_date         = f.get("divExDate")
    div_pay_amount      = f.get("divPayAmount")
    div_pay_date        = f.get("divPayDate")
    div_freq            = f.get("divFreq")
    next_div_ex_date    = f.get("nextDivExDate")
    next_div_pay_date   = f.get("nextDivPayDate")
    declaration_date    = f.get("declarationDate")
    # Days-to-ex-div (negative = passed)
    days_to_ex_div = None
    if next_div_ex_date:
        try:
            ed = _dt.fromisoformat(next_div_ex_date.replace("Z", "+00:00"))
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=_tz.utc)
            days_to_ex_div = (ed - _dt.now(_tz.utc)).days
        except Exception:
            pass

    # 14. 52-week high/low DATES — stale vs fresh-high distinction
    hi52_date = q.get("52WeekHighDate")
    lo52_date = q.get("52WeekLowDate")
    days_since_52w_high = None
    days_since_52w_low  = None
    if hi52_date:
        try:
            hd = _dt.fromisoformat(hi52_date.replace("Z", "+00:00"))
            if hd.tzinfo is None:
                hd = hd.replace(tzinfo=_tz.utc)
            days_since_52w_high = (_dt.now(_tz.utc) - hd).days
        except Exception:
            pass
    if lo52_date:
        try:
            ld = _dt.fromisoformat(lo52_date.replace("Z", "+00:00"))
            if ld.tzinfo is None:
                ld = ld.replace(tzinfo=_tz.utc)
            days_since_52w_low = (_dt.now(_tz.utc) - ld).days
        except Exception:
            pass

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
        # ── 2026-05-19 · Extended Schwab quote fields ──
        # Today's intraday OHLC + move
        "today_open":              today_open,
        "today_high":              today_high,
        "today_low":               today_low,
        "today_close_prev":        today_close,
        "today_net_change":        net_change,
        "today_net_pct":           net_pct_change,
        # Microstructure (NBBO depth)
        "bid_size":                bid_size,
        "ask_size":                ask_size,
        "last_size":               last_size,
        "bid_ask_imbalance":       bid_ask_imbalance,
        # Mark vs last (cleaner mid-price for after-hours)
        "mark":                    mark,
        "mark_change":             mark_chg,
        "mark_pct_change":         mark_pct,
        # Regular-hours-only print (distinguishes RTH from ETH)
        "rth_last_price":          rth_last_price,
        "rth_last_size":           rth_last_size,
        "rth_last_time":           rth_last_time,
        # Historical volatility (Schwab's pre-computed HV)
        "hist_volatility":         hist_vol,
        # Security trading status — Normal/Halted/News Pending/Closed
        "security_status":         sec_status,
        "is_halted":               is_halted,
        # Programmatic asset classification (replaces hardcoded ETF lists)
        "asset_type":              asset_type,
        "asset_main_type":         asset_main_type,
        "asset_sub_type":          asset_sub_type,
        "is_etf":                  is_etf,
        # Dividend calendar
        "div_ex_date":             div_ex_date,
        "div_pay_amount":          div_pay_amount,
        "div_pay_date":            div_pay_date,
        "div_freq":                div_freq,
        "next_div_ex_date":        next_div_ex_date,
        "next_div_pay_date":       next_div_pay_date,
        "declaration_date":        declaration_date,
        "days_to_ex_div":          days_to_ex_div,
        # 52-week dates (stale-high detection)
        "52w_high_date":           hi52_date,
        "52w_low_date":            lo52_date,
        "kpi_days_since_52w_high": days_since_52w_high,
        "kpi_days_since_52w_low":  days_since_52w_low,
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


# ── Option-chain greeks extraction ──────────────────────────────────────
def extract_chain_greeks(chain: dict, max_expirations: int = 3) -> dict:
    """Pull full greeks (Δ Γ Θ ν ρ) + IV + time/intrinsic value per contract.

    Schwab's /chains response is structured as
        callExpDateMap[expirationDateStr][strike] = [contract_blob]
        putExpDateMap[…]
    Each contract_blob has: delta, gamma, theta, vega, rho, volatility (IV),
    timeValue, intrinsicValue, mark, bid, ask, lastPrice, volume, openInterest,
    daysToExpiration, optionDeliverablesList, strikePrice, …

    Returns:
        {
          "underlying_price": float,
          "underlying_iv":    float,   # IV from put-call parity at ATM
          "expirations":      [{
              "expiration": "YYYY-MM-DD",
              "dte":        int,
              "calls":      [{strike, delta, gamma, theta, vega, rho, iv, time_val, intrinsic_val, bid, ask, mark, vol, oi}],
              "puts":       [...],
          }]
        }
    """
    if not chain or not isinstance(chain, dict):
        return {"underlying_price": None, "expirations": []}

    underlying = chain.get("underlying") or {}
    out = {
        "underlying_price": underlying.get("mark") or underlying.get("last") or chain.get("underlyingPrice"),
        "underlying_iv":    underlying.get("volatility"),
        "expirations":      [],
    }

    def _contract(c: dict) -> dict:
        return {
            "strike":         c.get("strikePrice"),
            "delta":          c.get("delta"),
            "gamma":          c.get("gamma"),
            "theta":          c.get("theta"),
            "vega":           c.get("vega"),
            "rho":            c.get("rho"),
            "iv":             c.get("volatility"),
            "time_val":       c.get("timeValue"),
            "intrinsic_val":  c.get("intrinsicValue"),
            "bid":            c.get("bid"),
            "ask":            c.get("ask"),
            "mark":           c.get("mark"),
            "last":           c.get("last"),
            "vol":            c.get("totalVolume"),
            "oi":             c.get("openInterest"),
            "dte":            c.get("daysToExpiration"),
            "in_the_money":   c.get("inTheMoney"),
            "theoretical_optionvalue": c.get("theoreticalOptionValue"),
        }

    # callExpDateMap / putExpDateMap structure: {"YYYY-MM-DD:DTE": {"STRIKE": [contract]}}
    call_map = chain.get("callExpDateMap") or {}
    put_map  = chain.get("putExpDateMap") or {}

    # Collect unique expirations across calls + puts, sorted by DTE ascending
    exp_keys = sorted(set(list(call_map.keys()) + list(put_map.keys())),
                       key=lambda k: int(k.split(":")[-1]) if ":" in k else 0)[:max_expirations]

    for exp_key in exp_keys:
        try:
            exp_date, dte_str = exp_key.split(":")
            dte = int(dte_str)
        except Exception:
            exp_date, dte = exp_key, None

        calls_dict = call_map.get(exp_key) or {}
        puts_dict  = put_map.get(exp_key) or {}

        calls = []
        puts  = []
        for strike, contracts in sorted(calls_dict.items(), key=lambda kv: float(kv[0])):
            for c in (contracts or []):
                calls.append(_contract(c))
        for strike, contracts in sorted(puts_dict.items(), key=lambda kv: float(kv[0])):
            for c in (contracts or []):
                puts.append(_contract(c))

        out["expirations"].append({
            "expiration": exp_date,
            "dte":        dte,
            "calls":      calls,
            "puts":       puts,
        })
    return out


def aggregate_greeks(greeks_data: dict) -> dict:
    """Position-level greeks summary: aggregate across all near-term expirations.

    Returns:
        {net_delta, total_gamma_$, total_theta_$_per_day, total_vega_$_per_vol_pt,
         iv_atm, atm_strike, dte_nearest}
    Useful for the Options-Intelligence panel: shows portfolio-level Greek exposure
    if you tracked open contracts, or just provides macro-view (ATM IV, near-term decay).
    """
    if not greeks_data or not greeks_data.get("expirations"):
        return {}
    px = greeks_data.get("underlying_price")
    if not px:
        return {}

    nearest = greeks_data["expirations"][0]
    calls = nearest.get("calls", [])

    # Find ATM strike (closest to underlying)
    atm = min(calls, key=lambda c: abs((c.get("strike") or 0) - px), default=None) if calls else None

    # Sum gamma, theta, vega across ALL contracts (assumes you'd hold +1 of each
    # at this expiration — purely a "macro view" of decay/vol exposure)
    sum_gamma = sum((c.get("gamma") or 0) for c in calls)
    sum_theta = sum((c.get("theta") or 0) for c in calls)
    sum_vega  = sum((c.get("vega") or 0)  for c in calls)

    return {
        "atm_strike":        atm.get("strike") if atm else None,
        "atm_iv":            atm.get("iv") if atm else None,
        "atm_delta":         atm.get("delta") if atm else None,
        "dte_nearest":       nearest.get("dte"),
        "sum_gamma_strip":   round(sum_gamma, 4),
        "sum_theta_strip":   round(sum_theta, 4),  # negative = decay
        "sum_vega_strip":    round(sum_vega, 4),
        "n_calls":           len(calls),
        "n_puts":            len(nearest.get("puts", [])),
    }


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
