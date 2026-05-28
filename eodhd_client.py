"""
EODHD client — single entry point for all EODHD API calls.

Replaces Polygon, Schwab data, Finnhub, FMP, Finviz, yfinance fallbacks.
All adapter functions in data_fetcher.py route through this module.

Key mode:
  - EODHD_API_KEY env var → real key (recommended)
  - missing                → falls back to public demo key (AAPL.US/MSFT.US/AMZN.US only)

Symbol convention (EODHD requires suffix):
  AAPL    → AAPL.US
  BRK-B   → BRK-B.US      (NOT BRK.B; EODHD uses dash)
  VIX     → VIX.INDX
  BTC     → BTC-USD.CC    (crypto)
  EURUSD  → EURUSD.FOREX

Use to_eodhd_symbol() — never hard-code suffixes at call sites.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("swingtrade.eodhd")

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://eodhd.com/api"
DEMO_KEY = "OeAFFmMliFG5orCUuwAKQ8l4WWFQ67YX"  # public demo, AAPL/MSFT/AMZN only
DEFAULT_TIMEOUT = 20  # seconds per HTTP call

# All-In-One plan limits: 100,000 calls/day, 1,000 calls/min.
# Plus an undocumented per-second burst cap that triggers 429s when many threads
# fire concurrently. Margins: 17/sec, 950/min, 95,000/day (bumped 2026-05-21
# from 14/800/90K to give the 16-worker pool more headroom — was bottlenecked
# at 14/sec which negated worker count increases).
_RATE_PER_SEC = 17
_RATE_PER_MIN = 950
_RATE_PER_DAY = 95_000

BASE_DIR = Path(__file__).resolve().parent
_CACHE_DIR = BASE_DIR / "cache" / "eodhd"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_api_key() -> str:
    """Read EODHD_API_KEY from environment or .env. Falls back to demo."""
    key = os.environ.get("EODHD_API_KEY")
    if key:
        return key.strip()
    # Try .env directly so we don't force python-dotenv as a dep
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("EODHD_API_KEY="):
                    return line.split("=", 1)[1].strip()
        except Exception as e:
            log.debug(f"Could not parse .env for EODHD_API_KEY: {e}")
    log.warning("EODHD_API_KEY not set — falling back to demo key (AAPL.US only)")
    return DEMO_KEY


_API_KEY = _load_api_key()


def is_demo() -> bool:
    """True when running on the public demo key (limited to AAPL/MSFT/AMZN)."""
    return _API_KEY == DEMO_KEY


# ── Symbol translation ────────────────────────────────────────────────────────
# Index aliases — system uses bare symbols, EODHD uses suffixed format
_INDEX_MAP = {
    "VIX":  "VIX.INDX",
    "GSPC": "GSPC.INDX",   # S&P 500 spot
    "SPX":  "GSPC.INDX",
    "IXIC": "IXIC.INDX",   # NASDAQ Composite
    "DJI":  "DJI.INDX",
    "RUT":  "RUT.INDX",
    "TNX":  "TNX.INDX",    # 10y treasury
}

# Class-share normalization: codebase uses "BRK-B", EODHD wants "BRK-B.US" — same dash
_KNOWN_CRYPTO = {"BTC", "ETH", "SOL", "DOGE", "ADA", "DOT", "MATIC", "AVAX", "LINK",
                 "XRP", "LTC", "BCH", "ATOM", "UNI", "ALGO", "NEAR", "FIL", "ICP",
                 "VET", "TRX", "AAVE", "MKR", "SAND", "MANA", "AXS", "GRT", "FTM",
                 "EGLD", "THETA", "RUNE", "KAVA", "FLOW", "HBAR", "XLM", "XMR"}


def to_eodhd_symbol(ticker: str, asset_class: str | None = None) -> str:
    """
    Translate an internal ticker to EODHD format.

      ticker="AAPL"            → "AAPL.US"
      ticker="BRK-B"           → "BRK-B.US"
      ticker="VIX"             → "VIX.INDX"
      ticker="BTC", crypto     → "BTC-USD.CC"
      asset_class="forex"      → "{ticker}.FOREX"
    """
    if not ticker:
        return ticker
    t = ticker.strip().upper()

    # Already suffixed
    if "." in t and t.split(".")[-1] in {"US", "INDX", "CC", "FOREX", "TO", "L", "DE"}:
        return t

    if asset_class == "forex":
        return f"{t}.FOREX"

    if asset_class == "crypto" or t in _KNOWN_CRYPTO:
        # EODHD uses {SYMBOL}-USD.CC for spot
        if "-" not in t:
            return f"{t}-USD.CC"
        return f"{t}.CC"

    if asset_class == "index" or t in _INDEX_MAP:
        return _INDEX_MAP.get(t, f"{t}.INDX")

    # Default: US equity
    return f"{t}.US"


def from_eodhd_symbol(symbol: str) -> str:
    """Inverse of to_eodhd_symbol — strip the suffix for downstream code."""
    if not symbol:
        return symbol
    return symbol.split(".", 1)[0]


# ── Rate limiter (token bucket — minute and day) ─────────────────────────────
class _RateLimiter:
    def __init__(self, per_sec: int, per_min: int, per_day: int):
        self.per_sec = per_sec
        self.per_min = per_min
        self.per_day = per_day
        self._second = deque()  # timestamps in last 1s
        self._minute = deque()  # timestamps in last 60s
        self._day = deque()     # timestamps in last 86400s
        self._lock = threading.Lock()

    def acquire(self):
        # Loop with re-acquire — multiple threads may need to wait
        while True:
            with self._lock:
                now = time.time()
                # Trim windows
                while self._second and self._second[0] < now - 1.0:
                    self._second.popleft()
                while self._minute and self._minute[0] < now - 60:
                    self._minute.popleft()
                while self._day and self._day[0] < now - 86400:
                    self._day.popleft()

                # Daily — hard abort
                if len(self._day) >= self.per_day:
                    wait_d = self._day[0] + 86400 - now
                    raise RuntimeError(
                        f"EODHD daily limit exhausted ({self.per_day}). "
                        f"Reset in {wait_d/3600:.1f}h."
                    )

                # Per-second — most likely the 429 source
                if len(self._second) >= self.per_sec:
                    wait = self._second[0] + 1.0 - now + 0.01
                # Per-minute
                elif len(self._minute) >= self.per_min:
                    wait = self._minute[0] + 60 - now + 0.05
                else:
                    self._second.append(now)
                    self._minute.append(now)
                    self._day.append(now)
                    return
            # Sleep without holding the lock
            time.sleep(max(0.01, wait))

    def stats(self) -> dict:
        with self._lock:
            return {
                "second_used": len(self._second),
                "second_cap":  self.per_sec,
                "minute_used": len(self._minute),
                "minute_cap": self.per_min,
                "day_used": len(self._day),
                "day_cap": self.per_day,
            }


_limiter = _RateLimiter(_RATE_PER_SEC, _RATE_PER_MIN, _RATE_PER_DAY)


# ── HTTP session with retry ───────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({"User-Agent": "SwingTrade/1.0 (eodhd_client)"})

# Connection-pool sizing (2026-05-11): default urllib3 pool is 10 connections, but
# the enrichment pool runs 14 concurrent workers + the prewarm script runs 14.
# Bumping pool size to 32 prevents "Connection pool is full, discarding connection"
# warnings and avoids the TCP handshake cost of opening/closing connections.
from requests.adapters import HTTPAdapter as _HTTPAdapter
_pool_adapter = _HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
_session.mount("https://", _pool_adapter)
_session.mount("http://", _pool_adapter)


# ── Cache helper (disk JSON, TTL) ─────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return _CACHE_DIR / f"{safe}.json"


def _cache_read(key: str, ttl_seconds: int) -> Any:
    fp = _cache_path(key)
    if not fp.exists():
        return None
    if time.time() - fp.stat().st_mtime > ttl_seconds:
        return None
    try:
        return json.loads(fp.read_text())
    except Exception as e:
        log.debug(f"Cache read failed {key}: {e}")
        return None


def _cache_write(key: str, data: Any) -> None:
    try:
        _cache_path(key).write_text(json.dumps(data))
    except Exception as e:
        log.debug(f"Cache write failed {key}: {e}")


# ── Core HTTP wrapper ─────────────────────────────────────────────────────────
class EODHDError(Exception):
    """Raised when EODHD returns an unrecoverable error."""


# Per-process EODHD call counter — for budget audit + duplicate-scan detection
_CALL_COUNTER = {"network": 0, "cache_hit": 0, "errors": 0}

# Per-endpoint call counter (v6 ops telemetry → eodhd_quota_usage table)
# Buckets: endpoint type (eod, fundamentals, options, news, snapshot, etc.)
_ENDPOINT_COUNTER: dict[str, dict[str, int]] = {}


def _endpoint_class(endpoint: str) -> str:
    """Map a raw endpoint path to a bucket class for quota tracking."""
    e = endpoint.lower().lstrip("/")
    if e.startswith("eod/"):                       return "eod"
    if e.startswith("intraday/"):                  return "intraday"
    if e.startswith("real-time/"):                 return "real_time"
    if e.startswith("fundamentals/"):              return "fundamentals"
    if e.startswith("options/"):                   return "options"
    if e.startswith("news"):                       return "news"
    if e.startswith("div/"):                       return "dividends"
    if e.startswith("splits/"):                    return "splits"
    if "exchange" in e:                            return "exchange_symbols"
    if e.startswith("calendar/"):                  return "calendar"
    if e.startswith("technical/"):                 return "technical"
    if e.startswith("sentiments"):                 return "sentiment"
    return "other"


def _bump_endpoint(endpoint: str, kind: str = "network") -> None:
    """kind: 'network' | 'cache_hit' | 'rate_limit'"""
    cls = _endpoint_class(endpoint)
    b = _ENDPOINT_COUNTER.setdefault(cls, {"network": 0, "cache_hit": 0, "rate_limit": 0})
    b[kind] = b.get(kind, 0) + 1


def get_call_stats() -> dict:
    """Return per-process EODHD call statistics. Reset at process start."""
    return dict(_CALL_COUNTER)


def get_endpoint_stats() -> dict:
    """Return per-endpoint counts (eod / fundamentals / options / news / ...)."""
    return {k: dict(v) for k, v in _ENDPOINT_COUNTER.items()}


def reset_call_stats() -> None:
    _CALL_COUNTER["network"] = 0
    _CALL_COUNTER["cache_hit"] = 0
    _CALL_COUNTER["errors"] = 0
    _ENDPOINT_COUNTER.clear()


def flush_quota_to_supabase() -> dict:
    """Best-effort write of today's per-endpoint counts to eodhd_quota_usage.
    Safe to call anytime — wraps all Supabase work in try/except.
    Returns a summary dict {pushed, failed, endpoints_seen}."""
    import os
    from datetime import date
    summary = {"pushed": 0, "failed": 0, "endpoints_seen": len(_ENDPOINT_COUNTER)}
    try:
        os.environ.setdefault("SUPABASE_MODE", "1")
        from supabase_client import sb_client
        sb = sb_client()
        if sb is None:
            return summary
        today = date.today().isoformat()
        rows = []
        for cls, counts in _ENDPOINT_COUNTER.items():
            rows.append({
                "bucket_date": today,
                "endpoint": cls,
                "request_count": counts.get("network", 0),
                "cost_units": counts.get("network", 0),  # 1 unit per request baseline
                "rate_limit_hits": counts.get("rate_limit", 0),
            })
        if rows:
            sb.table("eodhd_quota_usage").upsert(
                rows, on_conflict="bucket_date,endpoint"
            ).execute()
            summary["pushed"] = len(rows)
    except Exception:
        summary["failed"] = len(_ENDPOINT_COUNTER)
    return summary


def _request(
    endpoint: str,
    params: dict | None = None,
    *,
    cache_key: str | None = None,
    cache_ttl: int = 0,
    max_retries: int = 3,
    base_delay: float = 1.5,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Core EODHD HTTP wrapper.

      endpoint:  path under /api, e.g., "eod/AAPL.US"
      params:    query params (api_token + fmt=json injected automatically)
      cache_key: if set, cache the JSON response on disk for cache_ttl seconds
      Retries on 429 / 5xx with exponential backoff.
      Raises EODHDError on persistent failure or 4xx (other than 429).
    """
    if cache_key and cache_ttl > 0:
        cached = _cache_read(cache_key, cache_ttl)
        if cached is not None:
            _CALL_COUNTER["cache_hit"] += 1
            _bump_endpoint(endpoint, "cache_hit")
            return cached

    full_params = dict(params or {})
    full_params.setdefault("api_token", _API_KEY)
    full_params.setdefault("fmt", "json")

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            _limiter.acquire()
            _CALL_COUNTER["network"] += 1  # tally every network call (incl. retries)
            _bump_endpoint(endpoint, "network")
            resp = _session.get(url, params=full_params, timeout=timeout)

            # 200: success
            if resp.status_code == 200:
                # Some endpoints return CSV by default — guard
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct or resp.text.lstrip().startswith(("{", "[")):
                    data = resp.json()
                else:
                    data = resp.text
                if cache_key and cache_ttl > 0:
                    _cache_write(cache_key, data)
                return data

            # 401 / 403: bad key — fail fast, don't retry
            if resp.status_code in (401, 403):
                raise EODHDError(
                    f"EODHD auth failed (HTTP {resp.status_code}) on {endpoint}. "
                    f"Check EODHD_API_KEY in .env."
                )

            # 404: ticker not found — return None, don't retry
            if resp.status_code == 404:
                log.debug(f"EODHD 404 on {endpoint} — ticker likely unsupported")
                return None

            # 429 / 5xx: retry
            if resp.status_code == 429 or resp.status_code >= 500:
                delay = base_delay * (2 ** attempt)
                log.warning(
                    f"EODHD HTTP {resp.status_code} on {endpoint} "
                    f"(attempt {attempt+1}/{max_retries}) — retrying in {delay:.1f}s"
                )
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    continue

            # Anything else
            raise EODHDError(
                f"EODHD HTTP {resp.status_code} on {endpoint}: "
                f"{resp.text[:200]}"
            )

        except requests.RequestException as e:
            last_err = e
            delay = base_delay * (2 ** attempt)
            log.warning(
                f"EODHD network error on {endpoint} "
                f"(attempt {attempt+1}/{max_retries}): {e} — retrying in {delay:.1f}s"
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue

    raise EODHDError(f"EODHD: all {max_retries} retries exhausted on {endpoint}: {last_err}")


# ── Public adapter functions ─────────────────────────────────────────────────
# Phase-0 surface area: the minimum needed to validate auth + smoke-test.
# Phase-1 will expand to fundamentals, options, news, etc. (Task #2)

def eod(ticker: str, from_date: str | None = None, to_date: str | None = None,
        period: str = "d", cache_ttl: int = 43200) -> list[dict] | None:
    # cache_ttl bumped 14400→43200 (4h→12h) on 2026-05-01 — EOD bars only update once
    # at market close. Daily TTL would be even safer, but 12h gives some flexibility for
    # post-close updates while still cutting bulk-fetch calls by 67% during market hours.
    """
    EOD (daily) OHLCV history.

      ticker:    bare or suffixed ("AAPL" or "AAPL.US")
      from_date: "YYYY-MM-DD"
      to_date:   "YYYY-MM-DD"
      period:    "d" (daily), "w" (weekly), "m" (monthly)
    Returns list[{date, open, high, low, close, adjusted_close, volume}] or None on 404.
    """
    sym = to_eodhd_symbol(ticker)
    params = {"period": period}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"eod_{sym}_{from_date}_{to_date}_{period}"
    return _request(f"eod/{sym}", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def real_time(tickers: list[str] | str, cache_ttl: int = 300) -> dict | list[dict] | None:
    """
    Real-time (15-min delayed) quote for one or many tickers.
    Single ticker → returns dict. Multiple → returns list (uses ?s=... batch).
    """
    if isinstance(tickers, str):
        sym = to_eodhd_symbol(tickers)
        return _request(f"real-time/{sym}", cache_key=f"rt_{sym}", cache_ttl=cache_ttl)
    syms = [to_eodhd_symbol(t) for t in tickers]
    if not syms:
        return []
    head = syms[0]
    rest = ",".join(syms[1:])
    params = {"s": rest} if rest else None
    cache_key = f"rt_batch_{','.join(syms[:5])}_{len(syms)}"
    return _request(f"real-time/{head}", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def fundamentals(ticker: str, cache_ttl: int = 604800) -> dict | None:
    """Fundamentals API — financials, ratios, sector, dividends, etc.
    2026-05-28: TTL 24h → 7 days. Fundamentals (P/E, margins, balance sheet)
    change quarterly, not daily — re-fetching every scan was pure quota waste.
    The earnings *event* (beat/miss, dates) is captured by the shorter-TTL
    earnings/news endpoints, so the 7-day snapshot cache is safe. Raising TTL
    reduces quota (opposite of the 'don't lower TTL' guardrail)."""
    sym = to_eodhd_symbol(ticker)
    return _request(f"fundamentals/{sym}", cache_key=f"fund_{sym}", cache_ttl=cache_ttl)


def bulk_fundamentals(symbols: list[str], exchange: str = "US",
                      cache_ttl: int = 604800) -> dict | None:
    """Bulk fundamentals — 1 EODHD call returns simplified fundamentals for up
    to ~100 tickers. Replaces per-ticker /fundamentals/X calls for cold-cache
    scans (Phase 3 optimization).

    Returns dict keyed by EODHD code, e.g. {"AAPL": {...}, "MSFT": {...}}.
    Each value has the same shape as `fundamentals()` but with a SUBSET of
    fields (General, Highlights, Valuation, Technicals, SharesStats — no full
    Financials / Earnings history / Cashflow). Use this to pre-warm the
    per-ticker cache; deep-field consumers still need fundamentals(ticker).

    EODHD enforces ~100 symbols per call. Caller is responsible for chunking.
    """
    if not symbols:
        return {}
    symbols = symbols[:100]
    syms_param = ",".join(to_eodhd_symbol(s) for s in symbols)
    # Deterministic cache key (sort symbols so reordered calls share cache)
    # SHA1-hashed — filesystem ENAMETOOLONG when 100 tickers concatenated as filename.
    import hashlib as _hl
    _key_src = f"{exchange}|{','.join(sorted(symbols)).upper()}"
    cache_key = f"fund_bulk_{exchange}_{_hl.sha1(_key_src.encode()).hexdigest()[:16]}"
    return _request(
        f"fundamentals-bulk/{exchange}",
        params={"symbols": syms_param},
        cache_key=cache_key,
        cache_ttl=cache_ttl,
    )


def prewarm_fundamentals(tickers: list[str], exchange: str = "US",
                         chunk_size: int = 100, cache_ttl: int = 604800) -> dict:
    """Pre-populate per-ticker fundamentals cache from bulk_fundamentals.

    Splits `tickers` into chunks of 100, calls bulk_fundamentals on each,
    then writes each per-ticker payload to the same cache key that
    `fundamentals(ticker)` would consult. Subsequent fundamentals(t) calls
    are O(1) cache hits.

    Returns {ok: n, missing: list, calls: int, elapsed_sec: float}.
    """
    import time as _time
    if not tickers:
        return {"ok": 0, "missing": [], "calls": 0, "elapsed_sec": 0.0}

    t0 = _time.time()
    n_ok = 0
    n_calls = 0
    missing: list[str] = []
    seen: set = set()
    # Dedupe while preserving order
    uniq = [t for t in tickers if not (t in seen or seen.add(t))]

    for i in range(0, len(uniq), chunk_size):
        chunk = uniq[i:i + chunk_size]
        try:
            bulk = bulk_fundamentals(chunk, exchange=exchange, cache_ttl=cache_ttl)
            n_calls += 1
        except Exception:
            missing.extend(chunk)
            continue
        if not bulk or not isinstance(bulk, dict):
            missing.extend(chunk)
            continue
        # bulk_fundamentals returns {SYMBOL.EXCHANGE: data} OR {SYMBOL: data}
        # depending on EODHD response. Normalize both.
        for t in chunk:
            sym = to_eodhd_symbol(t)
            data = bulk.get(sym) or bulk.get(t) or bulk.get(t.upper())
            if not data:
                # try matching by Code field
                for k, v in bulk.items():
                    if isinstance(v, dict) and (v.get("General") or {}).get("Code", "").upper() == t.upper():
                        data = v
                        break
            if data:
                _cache_write(f"fund_{sym}", data)
                n_ok += 1
            else:
                missing.append(t)

    return {
        "ok": n_ok,
        "missing": missing,
        "calls": n_calls,
        "elapsed_sec": round(_time.time() - t0, 2),
    }


def search(query: str, limit: int = 15, cache_ttl: int = 86400,
           prefer_us: bool = True) -> list[dict] | None:
    """Symbol/company search.

    Q-1 (2026-05-03): EODHD's `search` endpoint sometimes returns foreign listings
    ahead of the US ADR (e.g., INFY → "INFY.NSE" before "INFY.US"). When `prefer_us`
    is True (default), results are reordered so US-exchange matches come first.
    Pass `prefer_us=False` to bypass — useful for explicit foreign-symbol searches.
    """
    raw = _request(
        f"search/{query}",
        params={"limit": limit},
        cache_key=f"search_{query}_{limit}",
        cache_ttl=cache_ttl,
    )
    if not raw or not isinstance(raw, list) or not prefer_us:
        return raw
    # Stable-sort: US listings first, then by query-position match strength
    us_codes = {"US", "NYSE", "NASDAQ", "AMEX", "BATS", "ARCA"}
    q_upper = (query or "").strip().upper()

    def _us_priority(item: dict) -> tuple[int, int]:
        ex = (item.get("Exchange") or "").upper()
        code = (item.get("Code") or "").upper()
        # 0 = US exact-code match (best), 1 = US, 2 = foreign exact-code, 3 = foreign
        if code == q_upper and ex in us_codes:
            return (0, 0)
        if ex in us_codes:
            return (1, 0)
        if code == q_upper:
            return (2, 0)
        return (3, 0)

    return sorted(raw, key=_us_priority)


def bulk_eod(date: str | None = None, exchange: str = "US",
             cache_ttl: int = 7200) -> list[dict] | None:
    """
    Bulk EOD — fetches last EOD for ALL tickers on an exchange in one call.
    The killer endpoint that replaces 1000s of per-ticker fetches.

      date: "YYYY-MM-DD" or None (last trading day)
      exchange: "US", "NASDAQ", "NYSE", "LSE", etc.
    Returns list[{code, exchange_short_name, date, open, high, low, close,
                  adjusted_close, volume}].
    """
    params = {}
    if date:
        params["date"] = date
    cache_key = f"bulk_eod_{exchange}_{date or 'last'}"
    return _request(
        f"eod-bulk-last-day/{exchange}",
        params=params,
        cache_key=cache_key,
        cache_ttl=cache_ttl,
    )


def intraday(ticker: str, interval: str = "1h",
             from_ts: int | None = None, to_ts: int | None = None,
             cache_ttl: int = 600) -> list[dict] | None:
    """
    Intraday OHLCV bars.
      interval: "1m" | "5m" | "1h"
      from_ts / to_ts: unix timestamps (optional)
    """
    sym = to_eodhd_symbol(ticker)
    params: dict[str, Any] = {"interval": interval}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts
    cache_key = f"intra_{sym}_{interval}_{from_ts}_{to_ts}"
    return _request(f"intraday/{sym}", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def options_chain(ticker: str, from_date: str | None = None,
                  to_date: str | None = None, cache_ttl: int = 7200) -> dict | None:
    # cache_ttl bumped 1800→7200 (30min→2h) on 2026-05-01 — options chain doesn't move
    # that much intraday and we don't actively trade options yet.
    """
    Options chain with Greeks + IV per contract.

    Returns dict:
      {data: [{expirationDate, options: {CALL: [...], PUT: [...]}}, ...]}
    Each option: strike, lastPrice, bid, ask, volume, openInterest,
                 impliedVolatility, delta, gamma, theta, vega, rho.
    """
    sym = to_eodhd_symbol(ticker)
    params: dict[str, Any] = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"opt_{sym}_{from_date}_{to_date}"
    return _request(f"options/{sym}", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def news(ticker: str | None = None, query: str | None = None,
         limit: int = 50, from_date: str | None = None,
         to_date: str | None = None, cache_ttl: int = 14400) -> list[dict] | None:
    # cache_ttl bumped 7200→14400 (2h→4h) on 2026-05-01 to reduce quota burn during hourly scans
    """
    News + sentiment feed.
      ticker: filter by ticker (uses ?s=AAPL.US)
      query: free-text search (?t=...)
    Returns list[{date, title, content, link, symbols, tags, sentiment}].
    """
    params: dict[str, Any] = {"limit": limit}
    if ticker:
        params["s"] = to_eodhd_symbol(ticker)
    if query:
        params["t"] = query
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"news_{ticker or 'q'}_{query or ''}_{limit}_{from_date}_{to_date}"
    return _request("news", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def sentiments(tickers: list[str] | str, from_date: str | None = None,
               to_date: str | None = None, cache_ttl: int = 43200) -> dict | None:
    # cache_ttl bumped 21600→43200 (6h→12h) on 2026-05-01 — sentiment scores update slowly
    """
    Aggregate news sentiment scores per ticker.
    Returns dict {ticker_with_suffix: [{date, count, normalized}, ...]}.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    syms = ",".join(to_eodhd_symbol(t) for t in tickers)
    params: dict[str, Any] = {"s": syms}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"sent_{syms[:60]}_{from_date}_{to_date}"
    return _request("sentiments", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def bulk_calendar_trends(symbols: list[str], cache_ttl: int = 21600) -> dict | None:
    """Bulk EPS-estimate trends for up to ~100 tickers in 1 call.

    Returns dict shaped:
        { "type": "Trends", "symbols": "...",
          "trends": [ [ {code, date, period, growth, earningsEstimate*, epsTrend*,
                         epsRevisionsUp*, revenueEstimate*}, ... ], ... ] }

    Each ticker has multiple rows (current Q, next Q, current Y, next Y). Used
    to replace per-ticker yfinance get_earnings_estimate_trend() calls in the
    scan enrichment phase.

    EODHD enforces ~100 symbols per call. Caller chunks via prewarm_calendar_trends.
    """
    if not symbols:
        return None
    symbols = symbols[:100]
    syms_param = ",".join(to_eodhd_symbol(s) for s in symbols)
    cache_key = f"trends_bulk_{','.join(sorted(symbols)).upper()}"
    return _request(
        "calendar/trends",
        params={"symbols": syms_param},
        cache_key=cache_key,
        cache_ttl=cache_ttl,
    )


def bulk_calendar_earnings(symbols: list[str], from_date: str | None = None,
                           to_date: str | None = None,
                           cache_ttl: int = 21600) -> dict | None:
    """Bulk upcoming earnings dates for up to ~100 tickers in 1 call.

    Replaces per-ticker get_earnings_date() with one call returning all
    scheduled earnings reports.
    """
    if not symbols:
        return None
    symbols = symbols[:100]
    params = {"symbols": ",".join(to_eodhd_symbol(s) for s in symbols)}
    if from_date: params["from"] = from_date
    if to_date:   params["to"]   = to_date
    cache_key = f"earn_bulk_{from_date or 'na'}_{to_date or 'na'}_{','.join(sorted(symbols)).upper()}"
    return _request(
        "calendar/earnings",
        params=params,
        cache_key=cache_key,
        cache_ttl=cache_ttl,
    )


def prewarm_calendar_trends(tickers: list[str], chunk_size: int = 100) -> dict:
    """Pre-fetch calendar trends for many tickers; flatten into per-ticker dict.

    Returns {ticker: list_of_period_rows}. The list has rows for each fiscal
    period (current Q, next Q, current Y, next Y). Consumers can pick which
    period they need (typically +1q for the next reporting quarter).
    """
    import time as _time
    if not tickers:
        return {}
    t0 = _time.time()
    n_calls = 0
    out: dict[str, list] = {}
    seen: set = set()
    uniq = [t for t in tickers if not (t in seen or seen.add(t))]
    for i in range(0, len(uniq), chunk_size):
        chunk = uniq[i:i + chunk_size]
        try:
            resp = bulk_calendar_trends(chunk)
            n_calls += 1
        except Exception:
            continue
        if not resp:
            continue
        # response shape: {"trends": [ [rows for ticker 1], [rows for ticker 2], ...]}
        groups = resp.get("trends") or []
        for grp in groups:
            if not isinstance(grp, list) or not grp:
                continue
            code = (grp[0].get("code") or "").split(".")[0].upper()
            if code:
                out[code] = grp
    return {
        "data": out,
        "calls": n_calls,
        "n_tickers": len(out),
        "elapsed_sec": round(_time.time() - t0, 2),
    }


def earnings_calendar(from_date: str | None = None, to_date: str | None = None,
                      symbols: list[str] | None = None,
                      cache_ttl: int = 7200) -> dict | None:
    """
    Earnings calendar — replaces Finviz earnings date backfill.
      from_date / to_date: window
      symbols: optional list to filter
    """
    params: dict[str, Any] = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if symbols:
        params["symbols"] = ",".join(to_eodhd_symbol(s) for s in symbols)
    cache_key = f"earn_cal_{from_date}_{to_date}_{(symbols and symbols[0]) or 'all'}"
    return _request("calendar/earnings", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def economic_events(from_date: str | None = None, to_date: str | None = None,
                    country: str = "US", cache_ttl: int = 3600) -> list[dict] | None:
    """Macro / economic calendar (CPI, FOMC, NFP, etc.)."""
    params: dict[str, Any] = {"country": country}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"macro_{country}_{from_date}_{to_date}"
    return _request("economic-events", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def index_components(index: str = "SP500", cache_ttl: int = 86400) -> list[str] | None:
    """
    Index constituents — replaces Wikipedia/iShares scrapers.
      index: "SP500" | "GSPC" | "RUI" (Russell 1000) | "RUT" (Russell 2000) | "NDX"
    Returns plain ticker list (suffix stripped).
    """
    # EODHD encodes constituents inside fundamentals of the index symbol
    sym = to_eodhd_symbol(index, asset_class="index")
    data = _request(
        f"fundamentals/{sym}",
        cache_key=f"idx_{sym}",
        cache_ttl=cache_ttl,
    )
    if not isinstance(data, dict):
        return None
    comps = data.get("Components") or {}
    out: list[str] = []
    for v in comps.values():
        code = (v or {}).get("Code") or ""
        if code:
            out.append(code.upper())
    return out


def insider_transactions(ticker: str, from_date: str | None = None,
                         to_date: str | None = None,
                         cache_ttl: int = 86400) -> list[dict] | None:
    """Insider Form 4 transactions — alternative to direct SEC EDGAR."""
    sym = to_eodhd_symbol(ticker)
    params: dict[str, Any] = {"code": sym}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"insider_{sym}_{from_date}_{to_date}"
    return _request("insider-transactions", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def exchange_symbol_list(exchange: str = "US",
                         cache_ttl: int = 86400) -> list[dict] | None:
    """All tradable symbols on an exchange — universe enumeration."""
    return _request(
        f"exchange-symbol-list/{exchange}",
        cache_key=f"sym_list_{exchange}",
        cache_ttl=cache_ttl,
    )


def screener(filters: list | None = None, signals: str | None = None,
             sort: str | None = None, limit: int = 50,
             offset: int = 0, cache_ttl: int = 1800) -> dict | None:
    """
    Screener API — pre-screened stock lists.
      filters: list of [field, op, value], e.g.
               [["market_capitalization", ">", 1e9], ["sector", "=", "Technology"]]
      signals: comma-separated, e.g. "50d_new_lo,bookvalue_neg"
      sort:    field.asc|desc
    """
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if filters:
        params["filters"] = json.dumps(filters)
    if signals:
        params["signals"] = signals
    if sort:
        params["sort"] = sort
    cache_key = f"scr_{(filters and str(filters)[:60]) or signals or ''}_{limit}_{offset}"
    return _request("screener", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def financial_events(from_date: str | None = None, to_date: str | None = None,
                     event_type: str = "ipos",
                     cache_ttl: int = 7200) -> list[dict] | None:
    """Financial events calendar — IPOs, secondary offerings, splits.

    event_type: 'ipos' | 'splits' | 'trends'
    """
    endpoint_map = {
        "ipos": "calendar/ipos",
        "splits": "calendar/splits",
        "trends": "calendar/trends",
    }
    endpoint = endpoint_map.get(event_type, "calendar/ipos")
    params: dict[str, Any] = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    cache_key = f"fin_events_{event_type}_{from_date}_{to_date}"
    return _request(endpoint, params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def exchange_details(exchange: str = "US",
                     cache_ttl: int = 86400) -> dict | None:
    """Exchange details — name, code, country, currency, timezone, **trading hours**."""
    return _request(
        f"exchange-details/{exchange}",
        cache_key=f"exch_det_{exchange}",
        cache_ttl=cache_ttl,
    )


def technicals(ticker: str, function: str = "sma",
               period: int = 20, cache_ttl: int = 1800) -> list[dict] | None:
    """Pre-computed technical indicators — sma, ema, wma, rsi, atr, bbands, macd, etc.

    function: indicator name (eodhd has 30+ supported)
    period:   lookback period for the indicator
    Returns: list of {date, <function>: value}
    """
    sym = to_eodhd_symbol(ticker)
    params: dict[str, Any] = {"function": function, "period": period}
    cache_key = f"tech_{sym}_{function}_{period}"
    return _request(f"technical/{sym}", params=params, cache_key=cache_key, cache_ttl=cache_ttl)


def technicals_to_series(ticker: str, function: str, period: int = 14,
                         cache_ttl: int = 1800):
    """Compatibility wrapper: returns a pandas Series indexed by date.

    Drop-in for local _ema/_rsi/_atr/_macd/_bbands when
    config.gates.use_eodhd_technicals=true. Falls back to None on failure
    so the caller can default to local computation.
    """
    try:
        import pandas as _pd
        rows = technicals(ticker, function=function, period=period, cache_ttl=cache_ttl) or []
        if not rows:
            return None
        idx, vals = [], []
        for r in rows:
            d = r.get("date") or r.get("Date")
            v = r.get(function) or r.get(function.upper()) or r.get("value")
            if d is None or v is None:
                continue
            idx.append(d)
            vals.append(float(v))
        if not vals:
            return None
        s = _pd.Series(vals, index=_pd.to_datetime(idx))
        s.name = function
        return s
    except Exception:
        return None


def etf_fundamentals(ticker: str, cache_ttl: int = 86400) -> dict | None:
    """ETF-specific fundamentals — holdings, AUM, expense ratio, sector breakdown.

    EODHD returns full ETF object via fundamentals() with ETF-only sub-keys:
      - General.Type == 'ETF'
      - ETF_Data.{NetAssets, ExpenseRatio, Holdings_Count, Sector_Weights, Top_10_Holdings}
    """
    f = fundamentals(ticker, cache_ttl=cache_ttl)
    if not f:
        return None
    if (f.get("General") or {}).get("Type") != "ETF":
        return None
    return f


def stats() -> dict:
    """Current rate-limit usage + key info."""
    s = _limiter.stats()
    s["api_key_mode"] = "demo" if is_demo() else "production"
    return s


# ── Smoke test (run as: python3 eodhd_client.py) ─────────────────────────────
def _smoke_test() -> None:
    """Validates auth + adapter wiring against demo or real key."""
    print(f"=== EODHD smoke test ===")
    print(f"API key mode: {'demo (limited)' if is_demo() else 'production'}")
    print()

    print("1. to_eodhd_symbol() translation:")
    for t, ac in [("AAPL", None), ("BRK-B", None), ("VIX", None),
                  ("BTC", "crypto"), ("EURUSD", "forex"), ("AAPL.US", None)]:
        print(f"   {t:<10} ({ac or 'auto'}) → {to_eodhd_symbol(t, ac)}")
    print()

    print("2. EOD AAPL last 5 days:")
    try:
        data = eod("AAPL", from_date="2026-04-15", to_date="2026-04-25")
        if data:
            for row in data[-5:]:
                print(f"   {row.get('date')}  close={row.get('close')}  "
                      f"adj={row.get('adjusted_close')}  vol={row.get('volume')}")
        else:
            print("   (empty response)")
    except Exception as e:
        print(f"   ERROR: {e}")
    print()

    print("3. Real-time AAPL:")
    try:
        rt = real_time("AAPL")
        if isinstance(rt, dict):
            print(f"   code={rt.get('code')}  close={rt.get('close')}  "
                  f"change_p={rt.get('change_p')}  ts={rt.get('timestamp')}")
        else:
            print(f"   {rt}")
    except Exception as e:
        print(f"   ERROR: {e}")
    print()

    print("4. Search 'apple':")
    try:
        results = search("apple", limit=3)
        if results:
            for r in results[:3]:
                print(f"   {r.get('Code'):<8} {r.get('Exchange'):<6} {r.get('Name')}")
    except Exception as e:
        print(f"   ERROR: {e}")
    print()

    print("5. Rate limiter stats:")
    s = stats()
    print(f"   minute: {s['minute_used']}/{s['minute_cap']}  "
          f"day: {s['day_used']}/{s['day_cap']}  mode: {s['api_key_mode']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    _smoke_test()
