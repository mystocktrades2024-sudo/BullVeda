"""
Data fetching layer for SwingTrade.
Pulls S&P 500 universe, Zacks Rank #1 list, and Yahoo Finance market data.
"""

# Removed def _legacy_get_polygon_options_chain on 2026-04-25 (legacy archive cleanup)
# Removed def _legacy_get_polygon_snapshot on 2026-04-25 (legacy archive cleanup)
# Removed def _legacy_get_polygon_ohlcv on 2026-04-25 (legacy archive cleanup)
# Removed def _legacy_polygon_get on 2026-04-25 (legacy archive cleanup)
# Removed def _legacy_get_unusual_options on 2026-04-25 (legacy archive cleanup)
# Removed def _legacy_get_options_iv_data on 2026-04-25 (legacy archive cleanup)
from __future__ import annotations

import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import time

import numpy as np
import pandas as pd
import requests
import socket
# 2026-05-22 · Hard global socket timeout — prevents Python's TCP/SSL stack
# from blocking indefinitely on a half-open connection.  The yfinance circuit
# breaker (below) prevents NEW yf calls after N slow/failed responses, but it
# does not reclaim already-open sockets in the urllib3 pool.  When the scan
# transitions to atexit / session-close, those orphaned sockets get drained
# via `_ssl.poll()` which has no Python-level timeout, hanging the scan for
# arbitrary minutes.  setdefaulttimeout(30) ensures any socket.read() bails
# after 30s — fast enough that scan-finalization cannot stall.  Increase via
# SWINGTRADE_SOCKET_TIMEOUT env var if real EODHD calls start tripping it.
socket.setdefaulttimeout(float(os.environ.get("SWINGTRADE_SOCKET_TIMEOUT", "30")))
# yfinance — re-enabled as fallback after user request 2026-05-01.
# EODHD is still primary; yfinance is used when EODHD rate-limits (HTTP 402)
# or returns empty data. Specifically wired for news fallback first.
try:
    import yfinance as _yf_real  # type: ignore
    yf = _yf_real
    _YF_AVAILABLE = True
except ImportError:
    # Stub if yfinance isn't installed — keeps imports clean
    class _YfStub:
        @staticmethod
        def download(*args, **kwargs):
            return pd.DataFrame()
        class Ticker:
            def __init__(self, *args, **kwargs):
                self.info = {}
                self.calendar = None
                self.upgrades_downgrades = pd.DataFrame()
                self.recommendations = pd.DataFrame()
                self.recommendations_summary = pd.DataFrame()
                self.analyst_price_targets = {}
                self.options = ()
                self.news = []
                class _FI: last_price = None
                self.fast_info = _FI()
            def history(self, *args, **kwargs):
                return pd.DataFrame()
            def option_chain(self, *args, **kwargs):
                class _Chain:
                    calls = pd.DataFrame()
                    puts = pd.DataFrame()
                return _Chain()
    yf = _YfStub()
    _YF_AVAILABLE = False
from bs4 import BeautifulSoup

# Optional tvDatafeed fallback
try:
    from tvDatafeed import TvDatafeed, Interval as TvInterval
    _tv_feed = TvDatafeed()
    _TV_DATAFEED = True
except Exception:
    _tv_feed = None
    _TV_DATAFEED = False

log = logging.getLogger("swingtrade.data")


# ── Enrichment cache decorator (2026-04-15) ─────────────────────────────
# Wraps per-ticker enricher functions with sqlite caching via enrichment_store.
# TTLs are source-specific (7d for finnhub, 1d for borrow, etc.).
# Pattern: check cache → return if fresh → call original → cache result → return.
def _with_enrichment_cache(source: str):
    """Decorator: cache enricher output in enrichment_store.db with per-source TTL."""
    def decorator(fn):
        def wrapper(ticker, *args, **kwargs):
            try:
                import enrichment_store as _es
                cached = _es.get_cached(ticker, source)
                if cached is not None:
                    return cached
            except Exception:
                pass
            result = fn(ticker, *args, **kwargs)
            if result and isinstance(result, dict) and not result.get("error"):
                try:
                    import enrichment_store as _es
                    _es.set_cached(ticker, source, result)
                except Exception:
                    pass
            return result
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


# ── In-memory TTL cache (prevents redundant API calls within a session) ──────

_mem_cache: dict[str, tuple[float, dict]] = {}

def _mem_cached(ttl_seconds: int = 3600):
    """Decorator: caches function(ticker, ...) → dict in memory for ttl_seconds."""
    def decorator(fn):
        def wrapper(ticker: str, *args, **kwargs):
            key = f"{fn.__name__}_{ticker}"
            now = time.time()
            hit = _mem_cache.get(key)
            if hit and (now - hit[0]) < ttl_seconds:
                return hit[1]
            result = fn(ticker, *args, **kwargs)
            _mem_cache[key] = (now, result)
            return result
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


# ── Degraded mode (connectivity fallback) ────────────────────────────────────
# Set by swing_trade._check_connectivity() when DNS/endpoint checks fail.
# When True, fetch_ohlcv_with_failover() skips live Polygon and goes straight
# to the local archive/yfinance to avoid cascading connection errors.
_DEGRADED_MODE = False


def enable_degraded_mode() -> None:
    """Skip live API calls, use archive first. Set when DNS/connectivity fails."""
    global _DEGRADED_MODE
    _DEGRADED_MODE = True
    log.warning("DEGRADED MODE enabled: network-first calls disabled, archive-only for this scan")


def disable_degraded_mode() -> None:
    """Re-enable live API calls (primarily for tests)."""
    global _DEGRADED_MODE
    _DEGRADED_MODE = False


def is_degraded_mode() -> bool:
    return _DEGRADED_MODE


# ── yfinance circuit breaker ─────────────────────────────────────────────────
# When EODHD's fundamentals endpoint goes degraded (seen 2026-05-11), every
# ticker falls through to yfinance for fundamentals/earnings. yfinance is slow
# (5-10s per ticker) AND noisy (50+ DeprecationWarning lines per call), turning
# a 30 min scan into a 2-3 hour one. This circuit breaker auto-disables yfinance
# for the rest of the scan after N slow/failed calls — accepting some missing
# data in exchange for finishing in reasonable time.
#
# Tuneable via env var YF_CIRCUIT_TRIP_AFTER (default 15 slow calls).
_YF_CIRCUIT_OPEN = False
_YF_SLOW_COUNT = 0
_YF_FAIL_COUNT = 0
_YF_TOTAL_CALLS = 0
_YF_SLOW_THRESHOLD_SEC = float(os.environ.get("YF_SLOW_THRESHOLD_SEC", "3.0"))
_YF_TRIP_AFTER = int(os.environ.get("YF_CIRCUIT_TRIP_AFTER", "15"))


def yf_circuit_open() -> bool:
    """If True, callers should short-circuit and return empty without invoking yfinance."""
    return _YF_CIRCUIT_OPEN


def yf_record_call(elapsed_sec: float, failed: bool = False) -> None:
    """Record a yfinance call's outcome. Auto-trips the breaker if too many slow/failed."""
    global _YF_CIRCUIT_OPEN, _YF_SLOW_COUNT, _YF_FAIL_COUNT, _YF_TOTAL_CALLS
    _YF_TOTAL_CALLS += 1
    if failed:
        _YF_FAIL_COUNT += 1
    if elapsed_sec >= _YF_SLOW_THRESHOLD_SEC:
        _YF_SLOW_COUNT += 1
    if not _YF_CIRCUIT_OPEN and (_YF_SLOW_COUNT >= _YF_TRIP_AFTER
                                  or _YF_FAIL_COUNT >= _YF_TRIP_AFTER * 2):
        _YF_CIRCUIT_OPEN = True
        log.warning(
            f"yfinance circuit OPEN after {_YF_TOTAL_CALLS} calls "
            f"(slow={_YF_SLOW_COUNT}, failed={_YF_FAIL_COUNT}). "
            f"Remaining yfinance fallbacks will return empty for the rest of this scan."
        )


def yf_circuit_stats() -> dict:
    return {
        "open": _YF_CIRCUIT_OPEN,
        "total_calls": _YF_TOTAL_CALLS,
        "slow_calls": _YF_SLOW_COUNT,
        "failed_calls": _YF_FAIL_COUNT,
        "slow_threshold_sec": _YF_SLOW_THRESHOLD_SEC,
        "trip_after": _YF_TRIP_AFTER,
    }


# ── Phase 3: EODHD bulk calendar/trends prewarm cache ────────────────────────
# Module-level dict populated by prewarm_calendar_trends_bulk() at scan start.
# get_earnings_estimate_trend() consults this before falling back to yfinance.
# Format: {ticker.upper(): [row_dicts]}  (one row per fiscal period from EODHD)
_BULK_TRENDS_CACHE: dict = {}


def prewarm_calendar_trends_bulk(tickers: list[str]) -> dict:
    """Pre-fetch EPS trends via bulk calendar/trends; cache for the scan.

    Cuts ~600 yfinance per-ticker calls (each with 50+ DeprecationWarnings) down
    to ~6 bulk EODHD calls. Called once from swing_trade.py before enrichment.
    """
    global _BULK_TRENDS_CACHE
    try:
        import eodhd_client as _eod
        res = _eod.prewarm_calendar_trends(tickers)
        _BULK_TRENDS_CACHE = res.get("data") or {}
        return {
            "ok": True,
            "tickers_warmed": res.get("n_tickers", 0),
            "eodhd_calls": res.get("calls", 0),
            "elapsed_sec": res.get("elapsed_sec", 0),
        }
    except Exception as e:
        log.warning(f"prewarm_calendar_trends_bulk failed (non-fatal): {e}")
        return {"ok": False, "error": str(e)}


def bulk_trends_cache_size() -> int:
    return len(_BULK_TRENDS_CACHE)


# ── Batch retry helper (for snapshot-style calls) ────────────────────────────

def _retry_batch_call(func, args=(), kwargs=None, max_retries=3, base_delay=2, label="batch"):
    """Exponential backoff retry for batch network calls.

    Total wall-clock is bounded to ~ base_delay * (2^max_retries - 1) seconds.
    With defaults (max_retries=3, base_delay=2): 2 + 4 + 8 = 14s max sleep.
    Caller should size max_retries so total stays under 30s per constraints.
    Returns func's result if any attempt succeeds with truthy value, else None.
    """
    if kwargs is None:
        kwargs = {}
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result:
                return result
        except Exception as e:
            log.warning(f"{label} failed (attempt {attempt+1}/{max_retries}): {e}")
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            log.warning(f"{label} retrying in {delay}s...")
            time.sleep(delay)
    log.error(f"{label}: all {max_retries} retries exhausted")
    return None


# ── Disk cache helpers (JSON, TTL in seconds) ────────────────────────────────

def _cache_read(key: str, ttl_seconds: int) -> dict | None:
    """Return cached dict if fresh, else None."""
    fp = BASE_DIR / "cache" / f"_cache_{key}.json"
    try:
        if fp.exists():
            age = time.time() - fp.stat().st_mtime
            if age < ttl_seconds:
                return json.loads(fp.read_text())
    except Exception as e:
        log.debug(f"Cache read failed for {key}: {e}")
    return None


def _cache_write(key: str, data: dict) -> None:
    """Write dict to disk cache.

    Self-pruning for time-bucketed keys: keys ending in "_<digits>" (e.g.
    opts_iv_MSFT_<2h-bucket>) rotate every TTL window and old buckets never expire
    on their own — they piled up to 63k+ files. After writing the current bucket,
    delete the same family's stale buckets so the cache stays bounded.
    """
    try:
        fp = BASE_DIR / "cache" / f"_cache_{key}.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(data))
        base, sep, last = key.rpartition("_")
        if sep and base and last.isdigit():
            for old in fp.parent.glob(f"_cache_{base}_*.json"):
                if old.name != fp.name:
                    try: old.unlink()
                    except OSError: pass
    except Exception as e:
        log.debug(f"Cache write failed for {key}: {e}")


_CONFIG_DEFAULTS = {
    "universe":    {"include_sp500": True, "include_russell1000": True,
                    "zacks_rank1_only": False, "custom_watchlist": []},
    "filters":     {"min_price": 2, "max_price": 250, "min_daily_dollar_volume": 10_000_000},
    "scoring":     {"fundamentals_max": 20, "optionality_max": 25,
                    "technicals_max": 40, "sentiment_max": 15, "raw_total": 100},
    "gates":       {"min_liquidity_daily": 10_000_000, "earnings_blackout_days": 5,
                    "entry_day_spy_drop_pct": -1.5, "distribution_days_no_new": 7},
    "technicals":  {"rsi_period": 14, "ema_fast": 8, "ema_mid": 21, "ema_slow": 50,
                    "sma_200": 200, "atr_period": 14, "min_rr_ratio": 3.0},
    "decisions":   {"buy_min_score": 65, "buy_min_rr": 3.0, "watch_min_score": 50, "avoid_below": 50},
    "portfolio":   {"max_positions": 5, "sector_max_positions": 2},
    "output":      {"top_n_buy": 5, "top_n_sell": 5, "top_n_watch": 5},
    "performance": {"max_enrichment_tickers": 200},
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Merge defaults for any missing top-level sections or keys
    for section, defaults in _CONFIG_DEFAULTS.items():
        if section not in cfg:
            log.warning(f"Config missing section '{section}' — using defaults")
            cfg[section] = dict(defaults)
        else:
            for key, val in defaults.items():
                if key not in cfg[section]:
                    log.debug(f"Config '{section}.{key}' missing — default {val}")
                    cfg[section][key] = val
    return cfg


# ── Universe builders ────────────────────────────────────────────────────────

def _eodhd_universe(index_code: str) -> list[str] | None:
    """Try EODHD index_components first; return None to let caller fall back."""
    try:
        cfg = load_config()
        if not cfg.get("data_sources", {}).get("use_eodhd", True):
            return None
    except Exception:
        pass
    try:
        import eodhd_client as _eod
        comps = _eod.index_components(index_code)
        if comps and len(comps) >= 100:
            log.info(f"EODHD index_components({index_code}): {len(comps)} tickers")
            # Match codebase convention: replace dots with dashes (BRK.B → BRK-B)
            return [t.replace(".", "-") for t in comps]
    except Exception as e:
        log.debug(f"EODHD index_components({index_code}) failed: {e}")
    return None


def get_sp500() -> list[str]:
    """S&P 500 constituents via EODHD."""
    return _eodhd_universe("GSPC") or []


def get_russell1000() -> list[str]:
    """Russell 1000 constituents via EODHD."""
    return _eodhd_universe("RUI") or []


def get_russell2000() -> list[str]:
    """Russell 2000 constituents via EODHD."""
    return _eodhd_universe("RUT") or []


# 2026-05-21 · Tier-1 universe expansion · MID + SML + NDX
# All three are EODHD-native index constituents — cheap (1 call each, cached).
# These fill the structural gap in the existing SP500+R1000+R2000 universe:
#   - MID (S&P MidCap 400): catches mid-caps the curated S&P committee
#     promoted but Russell hasn't included in R1000 yet
#   - SML (S&P SmallCap 600): higher-quality small-cap roster than RUT
#     (which is indiscriminate 1,963 names, many micro-caps and shells)
#   - NDX (NASDAQ-100): catches the ~5% of NDX names that aren't in S&P 500
#     (rare biotech / Chinese ADR / non-eligible names)

def get_sp_midcap_400() -> list[str]:
    """S&P MidCap 400 (~$3-15B cap range). EODHD index code: MID."""
    return _eodhd_universe("MID") or []


def get_sp_smallcap_600() -> list[str]:
    """S&P SmallCap 600 (~$1-6B cap range, curated). EODHD index code: SML.
    Strictly higher-quality than RUT because the S&P committee applies a
    profitability filter (4 consecutive quarters of positive earnings)."""
    return _eodhd_universe("SML") or []


def get_nasdaq_100() -> list[str]:
    """NASDAQ-100 (top 100 non-financial NASDAQ). EODHD index code: NDX.
    Largely overlaps S&P 500 but catches non-S&P names like LIN/EXC/biotech."""
    return _eodhd_universe("NDX") or []


def get_nasdaq_all(top_n: int = 1000, min_dollar_vol: float = 10_000_000) -> list[str]:
    """"NASDAQ 1000" — the top-`top_n` most-liquid NASDAQ-listed equities + ETFs.

    Was the full ~4,805-name exchange list; liquidity-gated 2026-05-30 so the daily
    scan stays fast. One bulk_eod(NASDAQ) call gives last-day close×volume for every
    symbol; we keep Type in {Common Stock, ETF}, filter dollar-volume >= min_dollar_vol,
    rank descending, and return the top `top_n` codes. Most overlap R1000/R2000/NDX100;
    the net-new chunk is off-index liquid NASDAQ small-caps + NASDAQ-listed ETFs.

    Opt-in via config universe.include_nasdaq_all; sized via universe.nasdaq_all_top_n
    + universe.nasdaq_all_min_dollar_vol. Pass top_n<=0 to disable the cap (full
    liquidity-gated list). Returns [] on a bulk hiccup — the index universes still
    cover the liquid NASDAQ names, so this stays purely additive."""
    try:
        import eodhd_client as _eod
        syms = _eod.exchange_symbol_list("NASDAQ") or []
        keep = {"Common Stock", "ETF"}
        eligible = set()
        for s in syms:
            if not isinstance(s, dict):
                continue
            code = (s.get("Code") or "").strip().upper()
            if not code or (s.get("Type") or "") not in keep:
                continue
            if any(code.endswith(sfx) for sfx in ("WS", "U", "R", "P")) and len(code) > 4:
                continue
            eligible.add(code)
        if not eligible:
            return []
        rows = _eod.bulk_eod(exchange="NASDAQ") or []
        if not isinstance(rows, list) or not rows:
            try:
                import logging as _lg; _lg.getLogger("swingtrade.data").warning(
                    "get_nasdaq_all: bulk_eod(NASDAQ) returned no rows — skipping NASDAQ-all (index universes still cover liquid NASDAQ names)")
            except Exception:
                pass
            return []
        ranked = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            code = (r.get("code") or "").strip().upper()
            if code not in eligible:
                continue
            try:
                dv = float(r.get("close") or r.get("adjusted_close") or 0) * float(r.get("volume") or 0)
            except (TypeError, ValueError):
                continue
            if dv >= min_dollar_vol:
                ranked.append((code, dv))
        ranked.sort(key=lambda x: x[1], reverse=True)
        if top_n and top_n > 0:
            ranked = ranked[:top_n]
        return [c for c, _ in ranked]
    except Exception as e:
        try:
            import logging as _lg; _lg.getLogger("swingtrade.data").warning(f"get_nasdaq_all failed: {e}")
        except Exception:
            pass
        return []


def get_universe_as_of(as_of_date: str, include_r1000: bool = True,
                        include_custom: bool = True) -> list[str]:
    """Point-in-time universe = S&P 500 (historical) ∪ R1000 (current) ∪ custom.

    Used by backtest.py to filter the universe to "names that were in the
    index on the test date" — fixes the survivorship bias of using today's
    membership for historical backtests (audit #1, Tier 2).

    Args:
        as_of_date: ISO date "YYYY-MM-DD". Reads
                    data/membership/sp500_YYYY-MM.csv (built by
                    build_membership_snapshots.py from Wikipedia).
                    If snapshot missing, falls back to current S&P 500.
        include_r1000: Add current Russell 1000 (no historical data freely
                       available for R1000 — partial bias remains, but
                       smaller than full survivorship).
        include_custom: Add tickers from data/custom_tracked.json.

    Returns: deduplicated list, dot/dash convention matching get_sp500().
    """
    from pathlib import Path as _P
    yyyy_mm = (as_of_date or "")[:7]
    snap_path = _P(__file__).parent / "data" / "membership" / f"sp500_{yyyy_mm}.csv"
    seen: set[str] = set()
    out: list[str] = []
    if snap_path.exists():
        for line in snap_path.read_text().splitlines():
            t = line.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    else:
        # Fallback: current S&P 500. Logged once per call so the bias is visible.
        log.info(f"get_universe_as_of: no snapshot for {yyyy_mm}, falling back to current S&P 500")
        for t in get_sp500():
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    if include_r1000:
        # 2026-05-18 · point-in-time R1000/R2000 from data/membership/ when
        # available (audit #1 fix · survivorship reduction). Falls back to
        # current EODHD if snapshot missing for that month.
        r1_added = False
        r1_snap = _P(__file__).parent / "data" / "membership" / f"r1000_{yyyy_mm}.csv"
        if r1_snap.exists():
            try:
                for line in r1_snap.read_text().splitlines():
                    t = line.strip()
                    if t and t not in seen:
                        seen.add(t); out.append(t)
                r1_added = True
                log.info(f"get_universe_as_of: r1000 from snapshot {yyyy_mm}")
            except Exception as e:
                log.warning(f"r1000 snapshot read failed: {e}")
        if not r1_added:
            try:
                for t in get_russell1000():
                    if t and t not in seen:
                        seen.add(t)
                        out.append(t)
            except Exception:
                pass
        # R2000 — small caps (point-in-time when snapshot exists)
        r2_snap = _P(__file__).parent / "data" / "membership" / f"r2000_{yyyy_mm}.csv"
        if r2_snap.exists():
            try:
                for line in r2_snap.read_text().splitlines():
                    t = line.strip()
                    if t and t not in seen:
                        seen.add(t); out.append(t)
                log.info(f"get_universe_as_of: r2000 from snapshot {yyyy_mm}")
            except Exception as e:
                log.warning(f"r2000 snapshot read failed: {e}")
    if include_custom:
        try:
            import json as _json
            custom_path = _P(__file__).parent / "data" / "custom_tracked.json"
            if custom_path.exists():
                d = _json.loads(custom_path.read_text())
                raw = d.get("tickers") or [] if isinstance(d, dict) else []
                for entry in raw:
                    t = entry if isinstance(entry, str) else entry.get("ticker")
                    if t and t not in seen:
                        seen.add(t)
                        out.append(t)
        except Exception:
            pass
    return out


def _scrape_zacks_sell_list(driver) -> list[dict]:
    """
    Scrape Zacks sell list with VGM grades.
    Returns list of {ticker, company, value, growth, momentum, vgm} dicts.
    """
    try:
        driver.get("https://www.zacks.com/stocks/sell-list")
        import time as _time
        _time.sleep(3)
        from bs4 import BeautifulSoup

        # Ask DataTables to show all rows (same pattern as buy list)
        try:
            driver.execute_script("""
                document.querySelectorAll('.dataTables_length select').forEach(function(s){
                    s.value='-1';
                    s.dispatchEvent(new Event('change',{bubbles:true}));
                });
            """)
            _time.sleep(2)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        # Try known table IDs for sell list
        table = (soup.find("table", id="stocks_table")
                 or soup.find("table", id="full_one_list_table_full_one_list")
                 or soup.find("table"))
        if not table:
            return []

        # ── Detect VGM column positions by voting on A–F grades ─────────────
        grade_set = {"A", "B", "C", "D", "F", "A+", "B+", "C+", "D+", "A-", "B-", "C-", "D-"}
        grade_col_votes: dict[int, int] = {}
        for tr in table.find_all("tr")[1:10]:
            cells_samp = tr.find_all("td")
            for i, c in enumerate(cells_samp):
                v = c.get_text(strip=True).upper()
                if v in grade_set:
                    grade_col_votes[i] = grade_col_votes.get(i, 0) + 1

        grade_cols = sorted([i for i, cnt in grade_col_votes.items() if cnt >= 2])
        val_idx  = grade_cols[0] if len(grade_cols) > 0 else None
        grow_idx = grade_cols[1] if len(grade_cols) > 1 else None
        mom_idx  = grade_cols[2] if len(grade_cols) > 2 else None
        vgm_idx  = grade_cols[3] if len(grade_cols) > 3 else None
        log.info(f"Sell list VGM columns: val={val_idx} gro={grow_idx} mom={mom_idx} vgm={vgm_idx} "
                 f"(from grade votes: {grade_col_votes})")

        def _grade(idx, cells):
            """Extract grade from cell, checking text and data attributes."""
            if idx is not None and idx < len(cells):
                cell = cells[idx]
                # Try get_text first
                g = cell.get_text(strip=True)
                if g and g.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                    return g
                # Try data attributes
                for attr in ["data-value", "title", "data-grade"]:
                    v = cell.get(attr, "").strip()
                    if v and v.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                        return v
                # Check inner spans
                for span in cell.find_all(["span", "div"]):
                    sv = span.get_text(strip=True)
                    if sv and sv.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                        return sv
                    for attr in ["data-value", "title", "data-grade"]:
                        sv2 = span.get(attr, "").strip()
                        if sv2 and sv2.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                            return sv2
                return g or "—"
            return "—"

        rows = []
        _debug_row_logged = False
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue

            # Extract ticker (first cell, or from a quote link)
            ticker_raw = cells[0].get_text(strip=True)
            if ticker_raw:
                ticker = ticker_raw.split()[0].upper()
            else:
                link = tr.find("a", href=re.compile(r"/stock/quote/"))
                if not link:
                    continue
                m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
                if not m:
                    continue
                ticker = m.group(1).replace(".", "-").upper()

            company = cells[1].get_text(strip=True) if len(cells) > 1 else ""

            # Debug: log all cells for first row
            if not _debug_row_logged:
                cell_map = {i: cells[i].get_text(strip=True)[:30] for i in range(len(cells))}
                log.info(f"Sell list debug row={ticker} ({len(cells)} cells): {cell_map}")
                _debug_row_logged = True

            rows.append({
                "ticker":    ticker,
                "company":   company,
                "value":     _grade(val_idx, cells),
                "growth":    _grade(grow_idx, cells),
                "momentum":  _grade(mom_idx, cells),
                "vgm":       _grade(vgm_idx, cells),
            })

        vgm_hit = sum(1 for r in rows if r.get("vgm", "—") not in ("—", ""))
        log.info(f"Zacks sell list: {len(rows)} tickers, {vgm_hit}/{len(rows)} with VGM grades")
        return rows
    except Exception as e:
        log.warning(f"Sell list scrape failed: {e}")
        return []


def _get_chrome_major_version():
    """Detect installed Chrome major version. Returns int or None if detection fails."""
    import subprocess
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
        "/usr/bin/google-chrome",                                         # Linux
        "/usr/bin/google-chrome-stable",                                  # Linux alt
        "google-chrome",                                                  # PATH
        "chrome",                                                         # PATH alt
    ]
    for path in chrome_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                match = re.search(r"(\d+)\.", result.stdout)
                if match:
                    return int(match.group(1))
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            continue
    return None


_CHROME_VERSION_CACHE = None


def _chrome_version():
    """Return cached Chrome major version, detecting on first call."""
    global _CHROME_VERSION_CACHE
    if _CHROME_VERSION_CACHE is None:
        _CHROME_VERSION_CACHE = _get_chrome_major_version()
        if _CHROME_VERSION_CACHE:
            log.info(f"Detected Chrome version {_CHROME_VERSION_CACHE}")
        else:
            log.warning("Could not detect Chrome version — undetected_chromedriver will auto-match")
    return _CHROME_VERSION_CACHE


def _try_zacks_login(creds_path: str) -> object | None:
    """Attempt Selenium login to Zacks. Returns driver or None."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        log.warning("Selenium not installed — Zacks scraping disabled")
        return None

    creds_file = Path(creds_path)
    if not creds_file.exists():
        log.warning(f"Zacks credentials not found: {creds_path}")
        return None

    with open(creds_file) as f:
        creds = json.load(f)

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    try:
        # Try undetected-chromedriver first (use_subprocess=True prevents window-close crash on macOS)
        try:
            import undetected_chromedriver as uc
            uc_opts = uc.ChromeOptions()
            uc_opts.add_argument("--headless=new")
            uc_opts.add_argument("--no-sandbox")
            uc_opts.add_argument("--disable-dev-shm-usage")
            # 2026-06-03: do NOT pin version_main first. Pinning to the detected major (e.g.
            # 149) makes uc 3.5.5 look for a driver build it can't fetch and poisons its cache,
            # causing SessionNotCreated even on retry (killed the 00:10 scan). Auto-match first
            # (verified working for Chrome 149 — uc downloads the correct driver); pin only as
            # a fallback.
            _v = _chrome_version()
            try:
                driver = uc.Chrome(options=uc_opts, use_subprocess=True)
            except Exception as e:
                log.warning(f"uc.Chrome auto-match failed: {e} — retrying with version_main={_v}")
                kwargs = {"options": uc_opts, "use_subprocess": True}
                if _v:
                    kwargs["version_main"] = _v
                driver = uc.Chrome(**kwargs)
        except Exception:
            driver = webdriver.Chrome(options=opts)
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })

        driver.get("https://www.zacks.com/logout.php")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.ID, "username")))

        # Dismiss cookie banner
        driver.execute_script(
            "try{document.getElementById('accept_cookie').click()}catch(e){}"
        )

        # Fill and submit login form
        driver.execute_script(f"""
            var u = document.getElementById('username');
            var p = document.getElementById('password');
            u.value = '{creds["username"]}';
            p.value = '{creds["password"]}';
            u.dispatchEvent(new Event('input', {{bubbles:true}}));
            p.dispatchEvent(new Event('input', {{bubbles:true}}));
            var btn = document.querySelector('#login form input[type=submit], #login form button[type=submit]');
            if(btn) btn.click();
        """)

        import time
        time.sleep(4)

        url = driver.current_url.lower()
        if "logout" in url or "signin" in url or "registration" in url:
            log.warning("Zacks login failed — session not established")
            driver.quit()
            return None

        log.info("Zacks login successful")
        return driver

    except Exception as e:
        log.warning(f"Zacks login error: {e}")
        return None


def get_zacks_rank1(creds_path: str) -> list[str]:
    """Thin wrapper — buy list is fetched inside fetch_all_zacks_data for efficiency."""
    result = fetch_all_zacks_data(creds_path)
    return result.get("zacks_r1", [])


def fetch_zacks_rank(ticker: str, creds_path: str) -> dict:
    """Fetch Zacks rank for a single ticker via requests (no login needed for basic data)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(
            f"https://www.zacks.com/stock/quote/{ticker}",
            headers=headers, timeout=10
        )
        if resp.status_code != 200:
            return {"rank": None, "error": f"HTTP {resp.status_code}"}

        text = resp.text
        # Extract rank from page
        rank_match = re.search(r'rank_chip.*?(\d)', text)
        if not rank_match:
            rank_match = re.search(r'rankrect_(\d)', text)
        if not rank_match:
            rank_match = re.search(r'Zacks Rank.*?(\d)', text)

        rank = int(rank_match.group(1)) if rank_match else None
        rank_text_map = {1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Sell", 5: "Strong Sell"}

        return {
            "rank": rank,
            "rank_text": rank_text_map.get(rank, "Unknown"),
            "error": None
        }
    except Exception as e:
        return {"rank": None, "error": str(e)}


def _ultimate_login_driver(creds: dict) -> object:
    """Login via the embedded form on the Zacks Ultimate page and return driver."""
    try:
        import undetected_chromedriver as uc
    except ImportError:
        from selenium import webdriver as uc
        return None

    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    driver = uc.Chrome(options=opts, use_subprocess=True, version_main=146)

    driver.get("https://www.zacks.com/ultimate/")
    import time
    time.sleep(4)
    try:
        driver.execute_script(
            "var c=document.getElementById('accept_cookie');if(c)c.click()"
        )
        time.sleep(1)
    except Exception:
        pass

    driver.execute_script(f"""
        var inputs=document.querySelectorAll(
            'input[type=text],input[type=email],input[name*=user],input[name*=email]');
        var pwds=document.querySelectorAll('input[type=password]');
        for(var i=0;i<inputs.length;i++){{
            inputs[i].value='{creds["username"]}';
            inputs[i].dispatchEvent(new Event('input',{{bubbles:true}}));
        }}
        for(var i=0;i<pwds.length;i++){{
            pwds[i].value='{creds["password"]}';
            pwds[i].dispatchEvent(new Event('input',{{bubbles:true}}));
        }}
        var btns=document.querySelectorAll('input[type=submit],button[type=submit]');
        if(btns.length>0)btns[0].click();
    """)
    time.sleep(6)
    return driver


def get_ultimate_content(creds_path: str) -> dict:
    """Thin wrapper — all Zacks data is fetched inside fetch_all_zacks_data."""
    result = fetch_all_zacks_data(creds_path)
    return {
        "overview":   result.get("ultimate_overview", {}),
        "all_trades": result.get("ultimate_all_trades", []),
        "commentary": result.get("ultimate_commentary", []),
        "confidential_commentary": result.get("confidential_commentary", []),
        "error": result.get("error"),
    }


def fetch_all_zacks_data(creds_path: str, force_fresh: bool = False) -> dict:
    """
    Single non-headless browser session fetching all Zacks premium data:
      - Zacks Rank #1 buy list (https://www.zacks.com/stocks/buy-list/)
      - Ultimate top movers 30d + all open trades (top_movers.php)
      - Ultimate commentary (ultimate/commentary.php)
      - Confidential commentary (confidential/commentary.php)

    Uses non-headless UC + Ultimate embedded-form login to bypass Incapsula.
    """
    import time

    empty = {
        "zacks_r1": [],
        "zacks_r1_scores": {},
        "zacks_sell_list": [],
        "ultimate_overview": {},
        "ultimate_all_trades": [],
        "ultimate_commentary": [],
        "ultimate_special_reports": [],
        "tazr_trades": [], "tazr_portfolio_stats": {}, "tazr_commentary": [],
        "bbt_trades": [], "bbt_portfolio_stats": {}, "bbt_commentary": [],
        "counterstrike_trades": [], "counterstrike_portfolio_stats": {}, "counterstrike_commentary": [],
        "headlinetrader_trades": [], "headlinetrader_portfolio_stats": {}, "headlinetrader_commentary": [],
        "alt_energy_trades": [], "alt_energy_portfolio_stats": {}, "alt_energy_commentary": [],
        "blockchain_trades": [], "blockchain_portfolio_stats": {}, "blockchain_commentary": [],
        "tech_innovators_trades": [], "tech_innovators_portfolio_stats": {}, "tech_innovators_commentary": [],
        "confidential_commentary": [],
        "confidential_overview": {},
        "error": None,
    }

    # ── REMOVE ZACKS (2026-06-03): owner disabled Zacks in the scan. The Selenium/
    # undetected-chromedriver path is the system's most fragile dependency (Chrome
    # auto-updates -> driver mismatch -> login crash that killed 2 scans). When
    # config.skip_zacks is true, return the empty result WITHOUT launching a browser.
    # All downstream zacks_data.get(...) callers safely get empty lists/dicts.
    # Re-enable by setting skip_zacks=false. Themes/Zacks-Rank surfaces show empty-state.
    try:
        _cfg_sz = load_config()
        if _cfg_sz.get("skip_zacks", False):
            log.info("Zacks DISABLED (config.skip_zacks=true) — skipping Selenium scrape entirely")
            return dict(empty)
    except Exception:
        pass

    # ── Disk cache: skip Selenium on same-day re-runs (weekend-aware TTL) ───────
    # Weekend: 6h (so Monday morning gets fresh data)
    # Monday pre-market (before 9:30 AM ET): 1h (catch overnight changes)
    # Otherwise: 12h (reduced from legacy 20h for fresher data)
    from zoneinfo import ZoneInfo as _ZI
    _now_et = datetime.now(_ZI("America/New_York"))
    _dow = _now_et.weekday()  # 0=Mon … 6=Sun
    if _dow in (5, 6):                                   # Saturday / Sunday
        _ZACKS_CACHE_TTL = 6 * 3600       # 6 hours
    elif _dow == 0 and (_now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)):
        _ZACKS_CACHE_TTL = 3600           # 1 hour (Monday pre-market)
    else:
        _ZACKS_CACHE_TTL = 12 * 3600      # 12 hours
    if not force_fresh:
        cached = _cache_read("zacks_all", _ZACKS_CACHE_TTL)
        if cached:
            log.info(f"Zacks cache hit — skipping Selenium scrape (use force_fresh=True to override)")
            return cached

    creds_file = Path(creds_path)
    if not creds_file.exists():
        empty["error"] = f"Credentials not found: {creds_path}"
        return empty

    with open(creds_file) as f:
        creds = json.load(f)

    driver = None
    try:
        driver = _ultimate_login_driver(creds)
        if driver is None:
            empty["error"] = "Driver init failed"
            return empty

        # ── Ultimate main page — overview stats + all open trades ────────────
        soup = BeautifulSoup(driver.page_source, "html.parser")
        ultimate_overview  = _parse_ultimate_overview(soup)
        # All open trades are also on the ultimate main page
        ultimate_all_trades = _parse_ultimate_table(soup, "all_trades_sortable")
        # Fallback: top_movers.php has the same all_trades table
        if not ultimate_all_trades:
            try:
                driver.get("https://www.zacks.com/ultimate/top_movers.php")
                time.sleep(3)
                soup_tm = BeautifulSoup(driver.page_source, "html.parser")
                ultimate_all_trades = _parse_ultimate_table(soup_tm, "all_trades_sortable")
            except Exception:
                pass
        log.info(f"Ultimate: {len(ultimate_all_trades)} open trades, "
                 f"overview stats: {len(ultimate_overview.get('stats', {}))} items")

        # ── TAZR — start in background thread immediately so it overlaps ────────
        # TAZR login takes ~22s; by the time the main session finishes its
        # remaining pages (~35s), TAZR will already be done.
        # ── Premium portfolios — all scraped in one Selenium session ────────────
        # TAZR, Black Box Trader, Counterstrike, Headline Trader,
        # Alt Energy Innovators, Blockchain Innovators, Technology Innovators
        _PREMIUM_PORTFOLIOS = [
            # Verified scraping (existing 7)
            ("tazr",                "https://www.zacks.com/tazr/",                        "TAZR"),
            ("bbt",                 "https://www.zacks.com/blackboxtrader/",               "BBT"),
            ("counterstrike",       "https://www.zacks.com/counterstrike/",                "Counterstrike"),
            ("headlinetrader",      "https://www.zacks.com/headlinetrader/",               "Headline Trader"),
            ("alt_energy",          "https://www.zacks.com/alternativeenergyinnovators/",  "Alt Energy"),
            ("blockchain",          "https://www.zacks.com/blockchaininnovators/",         "Blockchain"),
            ("tech_innovators",     "https://www.zacks.com/technologyinnovators/",         "Tech Innovators"),
            # Phase 2 — added 2026-05-01 (5 high-value services)
            ("surprise_trader",     "https://www.zacks.com/surprisetrader/",               "Surprise Trader"),
            ("insider_trader",      "https://www.zacks.com/insidertrader/",                "Insider Trader"),
            ("value_investor",     "https://www.zacks.com/valueinvestor/",                "Value Investor"),
            ("home_run_investor",   "https://www.zacks.com/homeruninvestor/",              "Home Run Investor"),
            ("income_investor",     "https://www.zacks.com/incomeinvestor/",               "Income Investor"),
        ]
        _premium_results: dict = {
            key: {"trades": [], "stats": {}, "commentary": []}
            for key, _, _ in _PREMIUM_PORTFOLIOS
        }

        def _scrape_zacks_portfolio_page(driver_inst, url: str, label: str) -> tuple[list, dict, list]:
            """Scrape a single Zacks premium portfolio page. Returns (trades, stats, commentary)."""
            driver_inst.get(url)
            time.sleep(6)
            try:
                driver_inst.execute_script("""
                    document.querySelectorAll('.dataTables_length select').forEach(function(s){
                        s.value='-1';
                        s.dispatchEvent(new Event('change',{bubbles:true}));
                    });
                """)
                time.sleep(3)
            except Exception:
                pass
            try:
                driver_inst.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                driver_inst.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
            except Exception:
                pass
            page_src = driver_inst.page_source
            soup = BeautifulSoup(page_src, "html.parser")
            trades, stats = _parse_tazr_table(soup)
            commentary = _parse_tazr_commentary(soup)
            log.info(f"{label}: {len(trades)} trades, {len(commentary)} commentary")
            # Debug dump when empty
            if not trades:
                dump_name = f"debug_{label.lower().replace(' ', '_')}_page.html"
                dump_path = str(Path(__file__).parent / "cache" / dump_name)
                try:
                    with open(dump_path, "w", encoding="utf-8") as df:
                        df.write(page_src)
                    log.warning(f"{label}: 0 trades — raw HTML saved to {dump_path}")
                except Exception:
                    pass
            return trades, stats, commentary

        def _premium_portfolio_worker(_creds=creds, _results=_premium_results):
            """Scrape all Zacks premium portfolios in one Selenium session."""
            _td = None
            try:
                _td = _ultimate_login_driver(_creds)
                if not _td:
                    return
                time.sleep(3)
                for key, url, label in _PREMIUM_PORTFOLIOS:
                    try:
                        trades, stats, commentary = _scrape_zacks_portfolio_page(_td, url, label)
                        _results[key]["trades"] = trades
                        _results[key]["stats"] = stats
                        _results[key]["commentary"] = commentary
                    except Exception as _pe:
                        log.warning(f"{label} scrape failed (non-fatal): {_pe}")
            except Exception as _e:
                log.warning(f"Premium portfolios scrape failed (non-fatal): {_e}")
            finally:
                if _td:
                    try: _td.quit()
                    except Exception as _qe: log.debug(f"Premium portfolios driver quit: {_qe}")

        _premium_thread = threading.Thread(target=_premium_portfolio_worker, daemon=True)
        _premium_thread.start()

        # ── Zacks Rank #1 buy list ───────────────────────────────────────────
        driver.get("https://www.zacks.com/stocks/buy-list/")
        time.sleep(3)
        # Ask DataTables to show all rows
        try:
            driver.execute_script("""
                document.querySelectorAll('.dataTables_length select').forEach(function(s){
                    s.value='-1';
                    s.dispatchEvent(new Event('change',{bubbles:true}));
                });
            """)
            time.sleep(2)
        except Exception:
            pass

        soup2 = BeautifulSoup(driver.page_source, "html.parser")
        tickers = []
        zacks_r1_scores: dict[str, dict] = {}  # ticker → {value, growth, momentum, vgm}
        table = soup2.find("table", id="full_one_list_table_full_one_list")
        if table:
            # ── Detect VGM column positions by scanning row data ─────────────
            # Header-based detection is unreliable because "Symbol" and "Company"
            # share one data cell despite being two header columns.
            # Primary: vote on columns that contain A–F grades across 5+ data rows.
            grade_set = {"A", "B", "C", "D", "F", "A+", "B+", "C+", "D+", "A-", "B-", "C-", "D-"}
            grade_col_votes: dict[int, int] = {}
            for tr in table.find_all("tr")[1:10]:
                cells_samp = tr.find_all("td")
                for i, c in enumerate(cells_samp):
                    v = c.get_text(strip=True).upper()
                    if v in grade_set:
                        grade_col_votes[i] = grade_col_votes.get(i, 0) + 1
            grade_cols = sorted([i for i, cnt in grade_col_votes.items() if cnt >= 2])
            val_idx  = grade_cols[0] if len(grade_cols) > 0 else None
            grow_idx = grade_cols[1] if len(grade_cols) > 1 else None
            mom_idx  = grade_cols[2] if len(grade_cols) > 2 else None
            vgm_idx  = grade_cols[3] if len(grade_cols) > 3 else None
            log.info(f"VGM columns: val={val_idx} gro={grow_idx} mom={mom_idx} vgm={vgm_idx} "
                     f"(from grade votes: {grade_col_votes})")

            _debug_row_logged = False
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all("td")
                link = tr.find("a", href=re.compile(r"/stock/quote/"))
                if not link:
                    continue
                m_t = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
                if not m_t:
                    continue
                t = m_t.group(1).replace(".", "-").upper()
                if t not in tickers:
                    tickers.append(t)

                def _grade(idx, _cells=cells):
                    if idx is not None and idx < len(_cells):
                        cell = _cells[idx]
                        # Try get_text first
                        g = cell.get_text(strip=True)
                        if g and g.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                            return g
                        # Try data attributes (some Zacks cells use data-value or title)
                        for attr in ["data-value", "title", "data-grade"]:
                            v = cell.get(attr, "").strip()
                            if v and v.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                                return v
                        # Check inner spans
                        for span in cell.find_all(["span", "div"]):
                            sv = span.get_text(strip=True)
                            if sv and sv.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                                return sv
                            for attr in ["data-value", "title", "data-grade"]:
                                sv2 = span.get(attr, "").strip()
                                if sv2 and sv2.upper() in {"A","A+","A-","B","B+","B-","C","C+","C-","D","D+","D-","F"}:
                                    return sv2
                        return g or "—"
                    return "—"

                # Debug: log ALL cells for first row so we can map header → data
                if not _debug_row_logged:
                    cell_map = {i: cells[i].get_text(strip=True)[:30] for i in range(len(cells))}
                    log.info(f"VGM debug row={t} ({len(cells)} cells): {cell_map}")
                    _debug_row_logged = True

                zacks_r1_scores[t] = {
                    "value":    _grade(val_idx),
                    "growth":   _grade(grow_idx),
                    "momentum": _grade(mom_idx),
                    "vgm":      _grade(vgm_idx),
                }
        # Fallback: any quote link on page (no score data)
        if not tickers:
            for link in soup2.find_all("a", href=re.compile(r"/stock/quote/")):
                m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
                if m:
                    t = m.group(1).replace(".", "-").upper()
                    if t not in tickers:
                        tickers.append(t)
        vgm_hit = sum(1 for v in zacks_r1_scores.values() if v.get("vgm","—") not in ("—",""))
        log.info(f"Zacks Rank #1: {len(tickers)} tickers, {vgm_hit}/{len(zacks_r1_scores)} with VGM grades")

        # ── Ultimate commentary ──────────────────────────────────────────────
        driver.get("https://www.zacks.com/ultimate/commentary.php")
        time.sleep(3)
        soup3 = BeautifulSoup(driver.page_source, "html.parser")
        ultimate_commentary = _parse_ultimate_commentary(soup3)
        log.info(f"Ultimate commentary: {len(ultimate_commentary)} items")

        # ── Ultimate Special Reports ─────────────────────────────────────────
        ultimate_special_reports = []
        try:
            driver.get("https://www.zacks.com/ultimate/special_reports.php")
            time.sleep(3)
            soup_sr = BeautifulSoup(driver.page_source, "html.parser")
            ultimate_special_reports = _parse_ultimate_special_reports(soup_sr)
            log.info(f"Ultimate special reports: {len(ultimate_special_reports)} reports")
        except Exception as _e:
            log.warning(f"Special reports scrape failed (non-fatal): {_e}")

        # ── Confidential commentary ──────────────────────────────────────────
        confidential_commentary = []
        try:
            driver.get("https://www.zacks.com/confidential/commentary.php")
            time.sleep(3)
            soup4 = BeautifulSoup(driver.page_source, "html.parser")
            confidential_commentary = _parse_confidential_commentary(soup4)
            log.info(f"Confidential commentary: {len(confidential_commentary)} items")
        except Exception as _e:
            log.warning(f"Confidential commentary scrape failed (non-fatal): {_e}")

        # ── Confidential overview (main portfolio page) ──────────────────────
        confidential_overview = {}
        try:
            driver.get("https://www.zacks.com/confidential/")
            time.sleep(4)
            soup5 = BeautifulSoup(driver.page_source, "html.parser")
            confidential_overview = _parse_confidential_overview(soup5)
            log.info(
                f"Confidential overview: {len(confidential_overview.get('positions', []))} positions"
            )
        except Exception as _e:
            log.warning(f"Confidential overview scrape failed (non-fatal): {_e}")

        sell_list = []
        try:
            sell_list = _scrape_zacks_sell_list(driver)
            log.info(f"Zacks sell list: {len(sell_list)} tickers")
        except Exception as _e:
            log.warning(f"Sell list scrape failed (non-fatal): {_e}")

        # ── Join premium portfolios background thread ─────────────────────────
        _premium_thread.join(timeout=480)  # 12 portfolios × ~12s each ≈ 144s + buffer (Phase 2 added 5)

        # ── Per-ticker enrichment (Phase 1: Industry Rank, ESP, Revisions, Surprise History, Broker Recs) ──
        # Runs lightweight (requests) for all R1 tickers, premium (Selenium) optional.
        # Cached 6h — repeated scans within the day reuse results.
        per_ticker_enrichment: dict = {}
        try:
            from zacks_per_ticker import fetch_zacks_quote_lightweight
            r1_subset = list(tickers)[:60]  # cap at 60 to avoid quota burn
            for t in r1_subset:
                try:
                    per_ticker_enrichment[t] = fetch_zacks_quote_lightweight(t)
                except Exception as _ze:
                    pass  # non-fatal, skip
            log.info(f"  Zacks per-ticker enrichment (lightweight): {len(per_ticker_enrichment)}/{len(r1_subset)} tickers")
        except Exception as _ee:
            log.debug(f"per-ticker enrichment skipped: {_ee}")

        result = {
            "zacks_r1": tickers,
            "zacks_r1_scores": zacks_r1_scores,
            "zacks_sell_list": sell_list,
            "ultimate_overview": ultimate_overview,
            "ultimate_all_trades": ultimate_all_trades,
            "ultimate_commentary": ultimate_commentary,
            "ultimate_special_reports": ultimate_special_reports,
            "confidential_commentary": confidential_commentary,
            "confidential_overview": confidential_overview,
            # Phase 1 — per-ticker quote-page enrichment (Industry Rank, ESP, Revisions, etc.)
            "zacks_per_ticker": per_ticker_enrichment,
            "error": None,
        }
        # Inject all premium portfolio data into result
        for key, _, _ in _PREMIUM_PORTFOLIOS:
            pr = _premium_results.get(key, {})
            result[f"{key}_trades"]          = pr.get("trades", [])
            result[f"{key}_portfolio_stats"] = pr.get("stats", {})
            result[f"{key}_commentary"]      = pr.get("commentary", [])
        # Save to disk cache for same-day re-runs
        _cache_write("zacks_all", result)
        return result

    except Exception as e:
        log.warning(f"Zacks premium fetch failed: {e}")
        empty["error"] = str(e)
        return empty
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def build_zacks_grade_map(zacks_data: dict) -> dict:
    """
    Build unified ticker → grade dict from buy list + sell list.
    Merges VGM grades from Rank #1 (buy) and sell list into a single map.

    Returns: {ticker: {value, growth, momentum, vgm, list, rank}}
    - list: "buy" or "sell"
    - rank: 1 for buy, 5 for sell
    """
    grade_map = {}

    # Add buy list (Rank #1)
    for ticker, grades in zacks_data.get("zacks_r1_scores", {}).items():
        grade_map[ticker] = {
            "value": grades.get("value", "—"),
            "growth": grades.get("growth", "—"),
            "momentum": grades.get("momentum", "—"),
            "vgm": grades.get("vgm", "—"),
            "list": "buy",
            "rank": 1,
        }

    # Add sell list (Rank 5), overwriting if ticker appears in both
    for row in zacks_data.get("zacks_sell_list", []):
        ticker = row.get("ticker", "")
        if not ticker:
            continue
        grade_map[ticker] = {
            "value": row.get("value", "—"),
            "growth": row.get("growth", "—"),
            "momentum": row.get("momentum", "—"),
            "vgm": row.get("vgm", "—"),
            "list": "sell",
            "rank": 5,
        }

    log.info(f"Built grade map: {len(grade_map)} tickers (buy={sum(1 for g in grade_map.values() if g['list']=='buy')}, "
             f"sell={sum(1 for g in grade_map.values() if g['list']=='sell')})")
    return grade_map


def _parse_ultimate_overview(soup) -> dict:
    """
    Parse the Zacks Ultimate main page (zacks.com/ultimate/).
    Extracts headline performance stats, service description, and any
    portfolio summary metrics shown on the overview page.
    Returns: {description, stats: {label: value}, highlights: [str]}
    """
    description = ""
    stats: dict[str, str] = {}
    highlights: list[str] = []

    # ── Service description / intro text ─────────────────────────────────────
    for tag in soup.find_all(["p", "div"], class_=re.compile(r"intro|desc|about|lead|sub|hero")):
        txt = tag.get_text(strip=True)
        if 40 < len(txt) < 500 and not description:
            description = txt

    # ── Headline stats — look for common patterns ─────────────────────────────
    # Pattern 1: .stat-value / .stat-label pairs
    for container in soup.find_all(["div", "ul", "section"],
                                   class_=re.compile(r"stat|perf|metric|summary|overview|result")):
        labels = container.find_all(class_=re.compile(r"label|name|title|key|caption"))
        values = container.find_all(class_=re.compile(r"value|number|amount|data|figure"))
        for lbl, val in zip(labels, values):
            k = lbl.get_text(strip=True)
            v = val.get_text(strip=True)
            if k and v and len(k) < 80:
                stats[k] = v

    # Pattern 2: dt/dd pairs
    if not stats:
        for dl in soup.find_all("dl"):
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                k = dt.get_text(strip=True)
                v = dd.get_text(strip=True)
                if k and v and len(k) < 80:
                    stats[k] = v

    # Pattern 3: table with 2 columns (label | value)
    if not stats:
        for table in soup.find_all("table"):
            tbl_id  = (table.get("id") or "").lower()
            tbl_cls = " ".join(table.get("class") or []).lower()
            if any(kw in tbl_id + tbl_cls for kw in ["stat", "perf", "summary", "overview"]):
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(cells) == 2 and cells[0] and cells[1]:
                        stats[cells[0]] = cells[1]

    # ── Highlight bullets / feature list ─────────────────────────────────────
    for ul in soup.find_all("ul", class_=re.compile(r"feature|highlight|benefit|list")):
        for li in ul.find_all("li"):
            txt = li.get_text(strip=True)
            if 10 < len(txt) < 300:
                highlights.append(txt)
        if highlights:
            break

    # ── Fallback: scrape any bold number-looking spans on the page ───────────
    if not stats:
        for el in soup.find_all(["span", "strong", "b"],
                                class_=re.compile(r"num|pct|return|gain|rate|win")):
            val = el.get_text(strip=True)
            if re.match(r'^[+\-]?\d[\d,\.]+%?$', val):
                prev = el.find_previous_sibling()
                label = prev.get_text(strip=True) if prev else ""
                if label and len(label) < 80:
                    stats[label] = val

    return {
        "description": description,
        "stats":       stats,
        "highlights":  highlights[:10],
    }


def _parse_ultimate_table(soup, table_id: str) -> list[dict]:
    """Parse a Zacks Ultimate sortable table by id."""
    table = soup.find("table", id=table_id)
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
        # Extract ticker symbol from link
        ticker = ""
        link = tr.find("a", href=re.compile(r"/stock/quote/"))
        if link:
            m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", link["href"])
            ticker = m.group(1).replace(".", "-").upper() if m else ""

        def cell_text(i):
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        company = cell_text(0).replace("Quick Quote", "").replace(ticker, "").strip()[:40]
        trade_type = cell_text(2)  # Long/Short
        date_added = cell_text(3)
        price_add = cell_text(4)
        price_last = cell_text(5)
        pct_chg = cell_text(6)
        service = cell_text(7) if len(cells) > 7 else ""

        if not ticker:
            continue

        rows.append({
            "company": company,
            "ticker": ticker,
            "type": trade_type,
            "date_added": date_added,
            "price_add": price_add,
            "price_last": price_last,
            "pct_chg": pct_chg,
            "service": service
        })
    return rows


def _parse_ultimate_commentary(soup) -> list[dict]:
    """Parse Zacks Ultimate commentary articles using p.ts_post date markers."""
    articles = []

    # Each article has a <p class="ts_post">Posted on M/D/YY</p> element
    # followed by the article title and excerpt text
    date_tags = soup.find_all("p", class_="ts_post")

    for date_tag in date_tags[:5]:
        date_text = date_tag.get_text(strip=True)
        date_m = re.search(r'(\d+/\d+/\d+)', date_text)
        if not date_m:
            continue
        date_str = date_m.group(1)

        # Title is typically in the preceding sibling or parent context
        # Walk backwards to find a heading or the title text
        title = ""
        prev = date_tag.find_previous_sibling()
        while prev:
            txt = prev.get_text(strip=True)
            if txt and len(txt) > 15 and len(txt) < 200:
                title = txt
                break
            prev = prev.find_previous_sibling()

        # Excerpt: text in the next sibling elements
        excerpt_parts = []
        nxt = date_tag.find_next_sibling()
        while nxt and len(excerpt_parts) < 3:
            txt = nxt.get_text(strip=True)
            if txt and len(txt) > 20:
                excerpt_parts.append(txt)
            nxt = nxt.find_next_sibling()
        excerpt = " ".join(excerpt_parts)[:500]

        if date_str and (title or excerpt):
            articles.append({
                "title": title or "Market Commentary",
                "date": date_str,
                "excerpt": excerpt
            })

    return articles


def _parse_confidential_commentary(soup) -> list[dict]:
    """
    Parse Zacks Confidential commentary page.
    Tries p.ts_post date markers first (same structure as Ultimate commentary),
    then falls back to article/div card scanning.
    """
    articles = []

    # Primary: same p.ts_post pattern as Ultimate commentary
    date_tags = soup.find_all("p", class_="ts_post")
    if date_tags:
        for date_tag in date_tags[:8]:
            date_text = date_tag.get_text(strip=True)
            date_m = re.search(r'(\d+/\d+/\d+)', date_text)
            if not date_m:
                continue
            date_str = date_m.group(1)

            title = ""
            prev = date_tag.find_previous_sibling()
            while prev:
                txt = prev.get_text(strip=True)
                if txt and 15 < len(txt) < 200:
                    title = txt
                    break
                prev = prev.find_previous_sibling()

            excerpt_parts = []
            nxt = date_tag.find_next_sibling()
            while nxt and len(excerpt_parts) < 3:
                txt = nxt.get_text(strip=True)
                if txt and len(txt) > 20:
                    excerpt_parts.append(txt)
                nxt = nxt.find_next_sibling()

            if date_str and (title or excerpt_parts):
                articles.append({
                    "title": title or "Confidential Commentary",
                    "date": date_str,
                    "excerpt": " ".join(excerpt_parts)[:500],
                })
    else:
        # Fallback: scan article/div cards
        for card in soup.find_all(["article", "div"], class_=re.compile(r"post|article|entry|ts_")):
            title_tag = card.find(["h1", "h2", "h3", "h4", "a"])
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or len(title) < 10:
                continue

            date_tag = card.find(["span", "p", "time"], class_=re.compile(r"date|time|post"))
            date_text = date_tag.get_text(strip=True) if date_tag else ""
            date_m = re.search(r'(\d+[/-]\d+[/-]\d+)', date_text)
            date_str = date_m.group(1) if date_m else ""

            ps = card.find_all("p")
            excerpt = " ".join(p.get_text(strip=True) for p in ps[:2])[:500]

            articles.append({"title": title, "date": date_str, "excerpt": excerpt})
            if len(articles) >= 8:
                break

    return articles[:8]


def _parse_confidential_overview(soup) -> dict:
    """
    Parse the Zacks Confidential main overview page (https://www.zacks.com/confidential/).
    Extracts:
      - stats: dict of headline performance numbers (total return, win rate, etc.)
      - positions: list of current portfolio positions (ticker, direction, buy date,
                   buy price, current price, gain/loss pct, status)
      - description: brief service description text
    """
    stats: dict[str, str] = {}
    positions: list[dict] = []
    description = ""

    # ── Service description / intro text ─────────────────��───────────────────
    for tag in soup.find_all(["p", "div"], class_=re.compile(r"intro|desc|about|sub")):
        txt = tag.get_text(strip=True)
        if 40 < len(txt) < 400:
            description = txt
            break

    # ── Headline stats (return, win rate, avg gain etc.) ─────────────────────
    # Zacks typically renders these as .stat-value / .stat-label pairs or in a
    # .portfolio-stats / .perf-stats container
    for container in soup.find_all(["div", "ul", "section"],
                                   class_=re.compile(r"stat|perf|metric|summary|overview")):
        labels  = container.find_all(class_=re.compile(r"label|name|title|key"))
        values  = container.find_all(class_=re.compile(r"value|number|amount|data"))
        for lbl, val in zip(labels, values):
            k = lbl.get_text(strip=True)
            v = val.get_text(strip=True)
            if k and v and len(k) < 60:
                stats[k] = v

    # Fallback: dt/dd pairs
    if not stats:
        for dl in soup.find_all("dl"):
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                k = dt.get_text(strip=True)
                v = dd.get_text(strip=True)
                if k and v:
                    stats[k] = v

    # ── Portfolio positions table ─────────────────────────────────────────────
    # Try tables with id/class hinting at portfolio or trades
    for table in soup.find_all("table"):
        tbl_id  = (table.get("id")    or "").lower()
        tbl_cls = " ".join(table.get("class") or []).lower()
        if not any(kw in tbl_id + tbl_cls
                   for kw in ["portfolio", "position", "trade", "open", "hold", "stock"]):
            continue

        headers = [th.get_text(strip=True).lower()
                   for th in table.find_all("th")]

        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not cells or len(cells) < 2:
                continue

            # Map cells to known column names where possible
            def _col(keys):
                for k in keys:
                    for i, h in enumerate(headers):
                        if k in h and i < len(cells):
                            return cells[i]
                # Fallback: positional
                return ""

            # Extract ticker from any cell matching uppercase ticker pattern
            ticker = ""
            for c in cells:
                m = re.search(r'\b([A-Z]{1,5})\b', c)
                if m and m.group(1) not in ("N", "A", "BUY", "SELL", "LONG", "SHORT"):
                    ticker = m.group(1)
                    break

            if not ticker:
                continue

            row = {
                "ticker":      ticker,
                "company":     _col(["company", "name", "stock"]),
                "direction":   "Long"  if any("long"  in c.lower() for c in cells)
                               else "Short" if any("short" in c.lower() for c in cells)
                               else _col(["type", "direction", "side"]) or "Long",
                "date_added":  _col(["date", "added", "bought", "open"]),
                "buy_price":   _col(["buy", "entry", "cost", "price add", "added price"]),
                "current":     _col(["current", "last", "price last", "close"]),
                "pct_chg":     _col(["gain", "return", "chg", "%", "perf"]),
                "status":      _col(["status", "signal"]),
            }
            # Remove empty-string values so downstream can use .get()
            positions.append({k: v for k, v in row.items() if v})

        if positions:
            break   # found one useful table, stop

    # ── If no table found, scan for ticker links ─────────────────────────────���
    if not positions:
        seen: set[str] = set()
        for a in soup.find_all("a", href=re.compile(r"/stock/quote/")):
            m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,6})", a["href"])
            if m:
                t = m.group(1).upper()
                if t not in seen:
                    seen.add(t)
                    positions.append({"ticker": t, "direction": "Long"})

    return {
        "description": description,
        "stats":       stats,
        "positions":   positions,
    }


# ── TAZR parser ──────────────────────────────────────────────────────────────

def _parse_tazr_table(soup) -> tuple[list[dict], dict]:
    """
    Parse the Zacks TAZR Open Portfolio table.
    Returns (rows, portfolio_stats) where portfolio_stats has long_pct, short_pct, cash_pct.

    Columns: Company, Sym, Type, %Val, +Date, Rpt Date, $Add, $Last, %Chg
    The "+Date" cell may contain "Details >>" link text instead of a date.
    """
    rows = []
    portfolio_stats = {}

    # ── Portfolio header stats (e.g. "100.00% Long | 0.00% Short (0.00% Cash Available)") ──
    for el in soup.find_all(string=re.compile(r"\d+\.\d+%\s+Long", re.I)):
        txt = el.strip()
        m_long  = re.search(r'([\d.]+)%\s+Long',  txt, re.I)
        m_short = re.search(r'([\d.]+)%\s+Short', txt, re.I)
        m_cash  = re.search(r'\(([\d.]+)%\s+Cash', txt, re.I)
        if m_long:
            portfolio_stats["long_pct"]  = m_long.group(1)
            portfolio_stats["short_pct"] = m_short.group(1) if m_short else "0.00"
            portfolio_stats["cash_pct"]  = m_cash.group(1)  if m_cash  else "0.00"
            break

    # ── Find the Open Portfolio table ───────────────────────────────────────
    table = (soup.find("table", id=re.compile(r"tazr|port_sort|open.?port|portfolio", re.I))
             or soup.find("table", class_=re.compile(r"tazr|open.?port", re.I)))
    if not table:
        # Fallback 1: Header-based — find table with portfolio-like headers
        for t in soup.find_all("table"):
            hdrs = " ".join(th.get_text(strip=True) for th in t.find_all("th")).lower()
            if "%val" in hdrs or ("sym" in hdrs and "$add" in hdrs) or \
               ("sym" in hdrs and "%chg" in hdrs) or ("$add" in hdrs and "$last" in hdrs):
                table = t
                break
    if not table:
        # Fallback 2: DataTables wrapper — Zacks uses dataTables_wrapper divs
        for wrapper in soup.find_all("div", class_=re.compile(r"dataTables_wrapper", re.I)):
            t = wrapper.find("table")
            if t:
                hdrs = " ".join(th.get_text(strip=True) for th in t.find_all("th")).lower()
                if "sym" in hdrs or "company" in hdrs or "%chg" in hdrs:
                    table = t
                    break
    if not table:
        # Fallback 3: Any table with stock-quote links (most reliable)
        for t in soup.find_all("table"):
            links = t.find_all("a", href=re.compile(r"/stock/quote/"))
            if len(links) >= 3:  # At least 3 stock links = likely the portfolio table
                table = t
                break
    if not table:
        return rows, portfolio_stats

    # ── Map header text → data cell index ────────────────────────────────────
    # Different Zacks portfolios have very different column layouts:
    #   TAZR:  Company, Sym, Type, %Val, +Date, Rpt Date, $Add, $Last, %Chg
    #   CS:    Company, Sym, %Val, +Date, Type, $Add, $Last, %Chg, Rpt Date
    #   BBT:   Company, Sym, +Date, $Add, $Last, %Chg
    #   AEI:   Company, Sym, Segment, $Mkt Cap, +Date, $Add, $Last, %Chg
    # Additionally, data rows often have 1 fewer <td> than <th> (Company missing).
    #
    # Strategy: identify which <th> positions correspond to known fields,
    # detect the header→data offset, and build a position-aware col_map.

    all_th = table.find_all("th")
    headers = [th.get_text(strip=True) for th in all_th]

    # Map each header position to a canonical name (if recognized)
    _KW_MAP = {
        "company": ["company", "name"],
        "sym":     ["sym", "tick"],
        "type":    ["type"],
        "pct_val": ["%val"],
        "date_add":["+ date", "+date", "date add", "added"],
        "rpt_date":["rpt date", "rpt", "report"],
        "price_add":["$add", "add price", "price add", "entry"],
        "price_last":["$last", "last price", "current"],
        "pct_chg": ["%chg", "% chg"],
        "segment": ["segment", "industry"],
        "mkt_cap": ["$mkt", "mkt cap", "market cap"],
    }

    # Build ordered list of recognized headers in the FIRST contiguous block.
    # After the first unrecognized header, remaining <th> are overflow company names.
    real_headers = []  # [(header_idx, canon_name), ...] — only real column headers
    overflow_company_names = []
    in_overflow = False
    for hi, h in enumerate(headers):
        hl = h.lower().strip()
        if not hl:
            continue
        if in_overflow:
            overflow_company_names.append(h)
            continue
        matched_canon = None
        for canon, keywords in _KW_MAP.items():
            if any(kw == hl or (len(kw) > 2 and kw in hl) for kw in keywords):
                matched_canon = canon
                break
        if matched_canon:
            real_headers.append((hi, matched_canon))
        else:
            # First unrecognized header = start of company name overflow
            in_overflow = True
            overflow_company_names.append(h)

    # Find first data row
    first_data_row = None
    tbody = table.find("tbody")
    if tbody:
        first_data_row = tbody.find("tr")
    if not first_data_row:
        for _tr in table.find_all("tr"):
            if _tr.find("td"):
                first_data_row = _tr
                break

    n_data_cols = len(first_data_row.find_all("td")) if first_data_row else len(real_headers)
    n_real_headers = len(real_headers)

    # Offset = how many real headers exceed data cell count (typically 0 or 1)
    col_offset = max(0, n_real_headers - n_data_cols)

    # Build col_map: skip first `col_offset` headers, then map 1:1
    col_map = {}
    data_idx = 0
    for pos_i, (hi, canon) in enumerate(real_headers):
        if pos_i < col_offset:
            continue
        if data_idx >= n_data_cols:
            break
        col_map[canon] = data_idx
        data_idx += 1

    _row_idx = 0

    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        def _cell(canon_name):
            ci = col_map.get(canon_name)
            if ci is not None and 0 <= ci < len(cells):
                return cells[ci].get_text(strip=True)
            return ""

        # Ticker: prefer stock-quote link, then cell text
        ticker = ""
        link = tr.find("a", href=re.compile(r"/stock/quote/"))
        if link:
            m = re.search(r"/stock/quote/([A-Z0-9.\-]{1,10})", link["href"])
            ticker = m.group(1).replace(".", "-").upper() if m else ""
        if not ticker:
            raw_sym = _cell("sym").upper().strip()
            raw_sym = re.sub(r"QUICK\s*QUOTE.*", "", raw_sym, flags=re.I).strip()
            if raw_sym and len(raw_sym) <= 6:
                ticker = raw_sym
        if not ticker:
            continue

        # Company: from data cell, overflow <th> names, or Sym cell text
        company = _cell("company")
        if not company and _row_idx < len(overflow_company_names):
            company = overflow_company_names[_row_idx]
        if not company:
            first_cell_text = cells[0].get_text(strip=True) if cells else ""
            company = re.sub(r"Quick\s*Quote.*", "", first_cell_text, flags=re.I).replace(ticker, "").strip()
        company = re.sub(r"Quick\s*Quote", "", company, flags=re.I).replace(ticker, "").strip()[:45]
        _row_idx += 1

        # +Date: may be "Details >>" link
        date_add_raw = ""
        details_link = ""
        date_ci = col_map.get("date_add")
        if date_ci is not None and 0 <= date_ci < len(cells):
            cell_el = cells[date_ci]
            a_el = cell_el.find("a")
            if a_el:
                href = a_el.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.zacks.com" + href
                details_link = href
                date_add_raw = "Details"
            else:
                date_add_raw = cell_el.get_text(strip=True)

        rows.append({
            "company":      company,
            "ticker":       ticker,
            "type":         _cell("type"),
            "pct_val":      _cell("pct_val"),
            "date_add":     date_add_raw,
            "details_link": details_link,
            "rpt_date":     _cell("rpt_date"),
            "price_add":    _cell("price_add"),
            "price_last":   _cell("price_last"),
            "pct_chg":      _cell("pct_chg"),
        })
    return rows, portfolio_stats


def _parse_tazr_commentary(soup) -> list[dict]:
    """
    Parse TAZR Commentary section.
    Structure: "TAZR Commentary" heading → articles with author photo, bold title,
    "By AuthorName" line, "Posted M/D/YY", then body paragraphs + links.
    Returns list of {title, author, date, body_html, body_text} dicts.
    """
    articles = []

    # Find the TAZR Commentary heading, then scan siblings/children for articles
    commentary_section = None
    for tag in soup.find_all(["h2", "h3", "h4", "div", "b", "strong"]):
        if "tazr commentary" in tag.get_text(strip=True).lower():
            commentary_section = tag
            break

    # Collect article containers after the heading
    # Each article: [img?] [h-tag title] ["By Author"] ["Posted date"] [p paragraphs...]
    article_containers = []
    if commentary_section:
        # Walk next siblings to collect article-like blocks
        sib = commentary_section.find_next_sibling()
        current = {"title": "", "author": "", "date": "", "paras": [], "img_src": ""}
        while sib and len(articles) < 10:
            tag_name = sib.name if sib.name else ""
            txt = sib.get_text(strip=True)

            if tag_name in ("h1", "h2", "h3", "h4") and txt and len(txt) > 10:
                # New article starts
                if current["title"] and (current["paras"] or current["date"]):
                    articles.append(current)
                current = {"title": txt, "author": "", "date": "", "paras": [], "img_src": ""}
            elif re.match(r"^By\s+\w", txt):
                current["author"] = re.sub(r"^By\s+", "", txt).strip()
            elif re.match(r"^Posted\s+\d", txt, re.I):
                dm = re.search(r'(\d+/\d+/\d+)', txt)
                current["date"] = dm.group(1) if dm else txt.replace("Posted ", "")
            elif tag_name == "img":
                current["img_src"] = sib.get("src", "")
            elif tag_name == "p" and txt and len(txt) > 5:
                # Capture paragraph HTML to preserve <a> links
                current["paras"].append(str(sib))
            sib = sib.find_next_sibling()
        if current["title"] and (current["paras"] or current["date"]):
            articles.append(current)

    # Fallback: p.ts_post pattern (used on other Zacks premium pages)
    if not articles:
        date_tags = soup.find_all("p", class_="ts_post")
        for date_tag in date_tags[:8]:
            date_text = date_tag.get_text(strip=True)
            date_m = re.search(r'(\d+/\d+/\d+)', date_text)
            if not date_m:
                continue
            date_str = date_m.group(1)
            title = ""
            prev = date_tag.find_previous_sibling()
            while prev:
                ptxt = prev.get_text(strip=True)
                if ptxt and 15 < len(ptxt) < 200:
                    title = ptxt
                    break
                prev = prev.find_previous_sibling()
            paras = []
            nxt = date_tag.find_next_sibling()
            while nxt and len(paras) < 6:
                ptxt = nxt.get_text(strip=True)
                if ptxt and len(ptxt) > 20:
                    paras.append(str(nxt))
                nxt = nxt.find_next_sibling()
            if date_str and (title or paras):
                articles.append({
                    "title":   title or "TAZR Commentary",
                    "author":  "",
                    "date":    date_str,
                    "paras":   paras,
                    "img_src": "",
                })

    # Normalise: build body_text from paras for plain-text fallback
    result = []
    for a in articles[:8]:
        paras = a.get("paras", [])
        # Strip script/style tags from captured HTML
        body_html = "\n".join(paras)
        body_text = " ".join(
            BeautifulSoup(p, "html.parser").get_text(strip=True) for p in paras
        )
        result.append({
            "title":     a.get("title", ""),
            "author":    a.get("author", ""),
            "date":      a.get("date", ""),
            "img_src":   a.get("img_src", ""),
            "body_html": body_html,
            "body_text": body_text[:2000],
        })
    return result


def _parse_ultimate_special_reports(soup) -> list[dict]:
    """
    Parse Zacks Ultimate Special Reports page.
    Returns list of {title, date, url, description} dicts.
    """
    reports = []
    # Reports are typically in article cards, list items, or table rows
    # Try article/div cards first
    for card in soup.find_all(["article", "div", "li"],
                              class_=re.compile(r"report|post|article|entry|item")):
        title_tag = card.find(["h1", "h2", "h3", "h4", "a"])
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        if not title or len(title) < 10 or len(title) > 300:
            continue
        # URL
        link_tag = card.find("a", href=True)
        href = link_tag["href"] if link_tag else ""
        if href and not href.startswith("http"):
            href = "https://www.zacks.com" + href
        # Date
        date_tag = card.find(["span", "p", "time"],
                             class_=re.compile(r"date|time|post"))
        date_text = date_tag.get_text(strip=True) if date_tag else ""
        date_m = re.search(r'(\d+[/-]\d+[/-]\d+)', date_text)
        date_str = date_m.group(1) if date_m else ""
        # Description
        ps = card.find_all("p")
        desc = " ".join(p.get_text(strip=True) for p in ps[:2])[:400]
        reports.append({
            "title": title,
            "date": date_str,
            "url": href,
            "description": desc,
        })
        if len(reports) >= 20:
            break

    # Fallback: any table rows
    if not reports:
        for table in soup.find_all("table"):
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all("td")
                if len(cells) < 2:
                    continue
                link_tag = tr.find("a", href=True)
                title = cells[0].get_text(strip=True) if cells else ""
                href = link_tag["href"] if link_tag else ""
                if href and not href.startswith("http"):
                    href = "https://www.zacks.com" + href
                date_str = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                if title and len(title) > 5:
                    reports.append({"title": title, "date": date_str, "url": href, "description": ""})
            if reports:
                break
    return reports[:20]


# ── Market data ──────────────────────────────────────────────────────────────

def _yf_ticker_normalize(ticker: str) -> str:
    """Yahoo Finance uses hyphens for class shares (BRK.B → BRK-B)."""
    return ticker.replace(".", "-")


def _tv_exchange_for(ticker: str, yf_exchange: str = "") -> str:
    """Map a yfinance exchange string to a TradingView exchange name."""
    m = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NNM": "NASDAQ",
         "NYQ": "NYSE",   "NYS": "NYSE",   "BTS": "NYSE",
         "PCX": "AMEX",   "ASE": "AMEX"}
    return m.get(yf_exchange, "NASDAQ")


def _fetch_via_tvfeed(ticker: str, n_bars: int = 130) -> pd.DataFrame | None:
    """
    Layer 3: fetch OHLCV from TradingView data feed.
    Tries NASDAQ first, then NYSE. Returns a yfinance-compatible DataFrame
    (columns: Open, High, Low, Close, Volume) or None on failure.
    """
    if not _TV_DATAFEED or _tv_feed is None:
        return None
    yt = _yf_ticker_normalize(ticker)
    for exchange in ("NASDAQ", "NYSE", "AMEX"):
        try:
            df = _tv_feed.get_hist(yt, exchange, interval=TvInterval.in_daily,
                                   n_bars=n_bars)
            if df is not None and not df.empty and len(df) >= 20:
                df = df.rename(columns={"open": "Open", "high": "High",
                                        "low": "Low", "close": "Close",
                                        "volume": "Volume"})
                df.index = pd.to_datetime(df.index)
                return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception:
            pass
    return None


def _ohlcv_cache_path(ticker: str) -> Path:
    p = Path(__file__).parent / "cache" / "ohlcv"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{ticker.replace('/', '_')}.parquet"

def _ohlcv_cache_load(ticker: str, max_age_hours: int = 12) -> "pd.DataFrame | None":
    """Load cached OHLCV if fresh enough — session-aware, weekend-aware.

    Rules:
      1. Basic age check (default 12h, reduced from 20h).
      2. After Friday close, cache expires by Monday 4 AM ET (not 20h later).
      3. If the cached data's last bar date is older than the previous trading
         day, force a refresh regardless of file age.
    """
    cp = _ohlcv_cache_path(ticker)
    if not cp.exists():
        return None
    import time as _t
    from zoneinfo import ZoneInfo as _ZI

    file_mtime = cp.stat().st_mtime
    age_h = (_t.time() - file_mtime) / 3600

    # ── Weekend / Monday-morning override ─────────────────────────────────────
    # If cache was written Friday/Saturday, expire it by Monday 4 AM ET so the
    # first Monday scan always pulls fresh data.
    _now_et = datetime.now(_ZI("America/New_York"))
    _dow = _now_et.weekday()  # 0=Mon … 6=Sun
    _file_dt = datetime.fromtimestamp(file_mtime, tz=_ZI("America/New_York"))

    if _dow == 0 and _now_et.hour >= 4 and _file_dt.weekday() >= 4:
        # It's Monday after 4 AM ET and cache was written Fri/Sat/Sun → stale
        return None

    # ── Standard age check ────────────────────────────────────────────────────
    if age_h > max_age_hours:
        return None

    try:
        df = pd.read_parquet(cp)
    except Exception:
        return None

    # ── Last-bar staleness check ──────────────────────────────────────────────
    # If the most recent OHLCV bar is older than the previous trading day,
    # force refresh (handles holidays, half-days, and gaps).
    if df is not None and len(df) > 0:
        try:
            last_bar = pd.Timestamp(df.index[-1])
            if last_bar.tzinfo is not None:
                last_bar = last_bar.tz_convert("America/New_York").normalize()
            else:
                last_bar = last_bar.normalize()

            # Compute previous trading day (skip weekends)
            prev_td = _now_et.date()
            if _now_et.hour < 16:  # before market close, previous day is "today"
                prev_td -= timedelta(days=1)
            while prev_td.weekday() >= 5:  # skip Sat/Sun
                prev_td -= timedelta(days=1)

            if last_bar.date() < prev_td:
                return None  # cached data is missing the latest trading day
        except Exception:
            pass  # if index is non-datetime, skip this check

    return df

def _ohlcv_cache_save(ticker: str, df: "pd.DataFrame") -> None:
    try:
        df.to_parquet(_ohlcv_cache_path(ticker))
    except Exception:
        pass


# ── EODHD adapters (Phase 1 of migration) ──────────────────────────────────
def _use_eodhd() -> bool:
    """Feature flag: route OHLCV/fundamentals through EODHD before legacy sources."""
    try:
        cfg = load_config()
        return bool(cfg.get("data_sources", {}).get("use_eodhd", True))
    except Exception:
        return True


def _eodhd_period_to_from_date(period: str) -> str | None:
    """Convert legacy period string ('6mo', '1y', etc.) to a from_date for EODHD."""
    from datetime import datetime, timedelta
    days_map = {
        "1mo": 30, "3mo": 92, "6mo": 183, "1y": 365, "2y": 730,
        "5y": 1825, "10y": 3650, "max": 7300,
    }
    days = days_map.get(period, 365)
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _eodhd_eod_to_df(rows: list[dict]) -> "pd.DataFrame | None":
    """Convert EODHD eod() rows → pandas DataFrame matching internal schema."""
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if df.empty or "date" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # EODHD: open, high, low, close, adjusted_close, volume
    # Internal: Open/High/Low/Close (adjusted)/Volume
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "adjusted_close": "Close", "volume": "Volume",
    })
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].astype(float, errors="ignore").dropna(how="all")
    return df if len(df) >= 20 else None


def _eodhd_fetch_ohlcv_layer(tickers: list[str], period: str) -> tuple[dict, list[str]]:
    """
    Try EODHD first for the requested tickers.
    Returns (success_map, still_need) — same shape as the other layers.
    """
    if not _use_eodhd() or not tickers:
        return {}, list(tickers)

    try:
        import eodhd_client as _eod
    except Exception as e:
        log.debug(f"eodhd_client unavailable: {e}")
        return {}, list(tickers)

    from_date = _eodhd_period_to_from_date(period)
    out: dict[str, pd.DataFrame] = {}
    still: list[str] = []

    def _fetch(t: str):
        try:
            rows = _eod.eod(t, from_date=from_date)
            df = _eodhd_eod_to_df(rows) if rows else None
            return t, df
        except Exception as ex:
            log.debug(f"EODHD eod({t}) failed: {ex}")
            return t, None

    # Thread pool — EODHD is fast, but per-ticker calls add up.
    # Lower concurrency lets the in-client rate limiter pace correctly
    # (EODHD has an undocumented per-second burst cap that returns 429).
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_fetch, t): t for t in tickers}
        for f in as_completed(futs):
            t, df = f.result()
            if df is not None:
                out[t] = df
            else:
                still.append(t)
    return out, still


def _eodhd_bulk_eod_layer(tickers: list[str]) -> tuple[dict, list[str]]:
    """
    Single-call bulk EOD for tickers — only fetches LAST day's OHLCV.
    Returns (last_day_dict, still_need). For full history, fall through to per-ticker.
    Use this to pre-warm cache when you only need a current snapshot.
    """
    if not _use_eodhd() or not tickers:
        return {}, list(tickers)
    try:
        import eodhd_client as _eod
        rows = _eod.bulk_eod(exchange="US")
    except Exception as ex:
        log.debug(f"EODHD bulk_eod failed: {ex}")
        return {}, list(tickers)
    if not isinstance(rows, list):
        return {}, list(tickers)

    by_code: dict[str, dict] = {(r.get("code") or "").upper(): r for r in rows if r}
    out: dict[str, dict] = {}
    still: list[str] = []
    for t in tickers:
        rec = by_code.get(t.upper())
        if rec:
            out[t] = rec
        else:
            still.append(t)
    return out, still


def fetch_market_data(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """
    Bulk OHLCV fetch via EODHD (sole provider after migration).

    Flow:
      Layer 0 — EODHD per-ticker EOD (full history)
      Layer 1 — Local Parquet archive cache (only for tickers EODHD doesn't have)
    """
    if not tickers:
        return {}

    result: dict[str, pd.DataFrame] = {}

    # ── Layer 0: EODHD primary ────────────────────────────────────────────────
    eod_hits, needs_fetch = _eodhd_fetch_ohlcv_layer(tickers, period)
    if eod_hits:
        log.info(f"  EODHD: {len(eod_hits)}/{len(tickers)} tickers fetched")
        result.update(eod_hits)

    # ── Layer 1: Local Parquet archive (cache safety net for offline mode) ───
    if needs_fetch:
        try:
            from data_archive import load_ticker as _archive_load
            archive_hits = 0
            still: list[str] = []
            for t in needs_fetch:
                df = _archive_load(t)
                if df is not None and len(df) >= 20:
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                    result[t] = df[cols].dropna(how="all")
                    archive_hits += 1
                else:
                    still.append(t)
            if archive_hits:
                log.info(f"  Archive: {archive_hits} tickers served from local Parquet cache")
            needs_fetch = still
        except Exception as e:
            log.debug(f"Archive layer skipped: {e}")

    if needs_fetch:
        log.warning(
            f"  {len(needs_fetch)} tickers unavailable from EODHD or archive: "
            f"{needs_fetch[:10]}{'...' if len(needs_fetch) > 10 else ''}"
        )

    filled = len(result)
    pct = filled / len(tickers) * 100 if tickers else 0
    log.info(f"Market data: {filled}/{len(tickers)} tickers ({pct:.0f}% fill rate)")
    return result


def get_live_price(ticker: str) -> float | None:
    """Return real-time (15-min delayed) last price via EODHD."""
    try:
        import eodhd_client as _eod
        rt = _eod.real_time(ticker)
        if isinstance(rt, dict):
            for fld in ("close", "previousClose"):
                v = rt.get(fld)
                if v is not None and v != "NA":
                    try:
                        p = float(v)
                        if p > 0:
                            return p
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        log.debug(f"EODHD real_time({ticker}) failed: {e}")
    return None


def _info_cache_path(ticker: str) -> Path:
    """Return path for cached .info JSON file."""
    p = Path(__file__).parent / "cache" / "info"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{ticker.replace('/', '_')}.json"


def _info_cache_load(ticker: str, max_age_days: int = 3):
    """Load cached info if fresh enough (3-day TTL for swing traders). Returns dict or None.

    2026-05-26 · Skip low-quality cached entries (market_cap missing AND sector
    Unknown) so that prior pollution by the finnhub+polygon fallback path
    doesn't shadow a recoverable EODHD result. Without this, once any fallback
    layer writes a degraded entry, every subsequent scan reuses it for 3 days.
    """
    cp = _info_cache_path(ticker)
    try:
        if cp.exists():
            age_hours = (datetime.utcnow() - datetime.utcfromtimestamp(cp.stat().st_mtime)).total_seconds() / 3600
            if age_hours < max_age_days * 24:
                data = json.loads(cp.read_text())
                if data:
                    mc = data.get("market_cap")
                    sec = data.get("sector")
                    if (mc in (0, None)) and (sec in (None, "", "Unknown")):
                        return None  # treat as stale — let upstream lanes retry
                    return data
    except Exception:
        pass
    return None


def _info_cache_save(ticker: str, info: dict) -> None:
    """Save info dict to disk cache.

    2026-05-26 · Refuse to persist a degraded result (market_cap missing AND
    sector Unknown). Otherwise the legacy fallback paths pin a 3-day-stale
    bad entry over a recoverable EODHD result.
    """
    try:
        if not info:
            return
        mc = info.get("market_cap")
        sec = info.get("sector")
        if (mc in (0, None)) and (sec in (None, "", "Unknown")):
            return
        _info_cache_path(ticker).write_text(json.dumps(info))
    except Exception:
        pass


def get_stock_info(ticker: str) -> dict:
    """
    Fetch fundamental data. Lane order (2026-04-15):
      Layer 0: sqlite fundamentals_store (30-day TTL)
      Layer 1: legacy cache/info/*.json  (3-day TTL)
      Layer 2: Schwab /quotes?fields=fundamental — bundles price + PE/EPS/mcap/52wk/div
      Layer 3: yfinance .info — last resort, also provides deep fields Schwab doesn't
    Schwab fills the sqlite cache on every successful call so subsequent scans
    hit Layer 0. Deep fields (margins/growth/D-E/FCF) still come from yfinance.
    """
    # Layer 0: sqlite fundamentals_store (2026-04-15 — 30-day TTL)
    # Skip if sector is missing — let downstream layers (Polygon/Finnhub) fill it
    try:
        import fundamentals_store as _fs
        if not _fs.needs_refresh(ticker, ttl_days=30):
            rec = _fs.get(ticker)
            if rec and rec.get("sector"):
                # Translate sqlite row → get_stock_info contract
                return {
                    "ticker": ticker,
                    "sector":  rec.get("sector") or "Unknown",
                    "industry": rec.get("industry") or "Unknown",
                    "market_cap":       rec.get("market_cap") or 0,
                    "revenue_growth":   rec.get("revenue_growth"),
                    "earnings_growth":  rec.get("eps_growth_qoq"),
                    "profit_margin":    rec.get("profit_margin"),
                    "gross_margin":     rec.get("gross_margin"),
                    "operating_margin": rec.get("operating_margin"),
                    "debt_to_equity":   rec.get("debt_equity"),
                    "pe_ratio":         rec.get("pe_ttm"),
                    "forward_pe":       rec.get("forward_pe"),
                    "beta":             rec.get("beta"),
                    "short_pct":        rec.get("short_float"),
                    "shares_float":     rec.get("shares_out"),
                    "52w_high":         rec.get("week52_high"),
                    "52w_low":          rec.get("week52_low"),
                    "free_cashflow":    rec.get("fcf_ttm"),
                    "trailing_eps":     rec.get("eps_ttm"),
                    "earnings_qoq_growth": rec.get("eps_growth_qoq"),
                    "name": ticker,
                    "error": None,
                    "_cache_source": "sqlite",
                }
    except Exception as _fse:
        log.debug(f"fundamentals_store read failed for {ticker}: {_fse}")

    # Layer 1: legacy JSON cache (3-day TTL)
    cached = _info_cache_load(ticker)
    if cached is not None:
        return cached

    # Layer 2: Schwab /quotes — bundles live price + basic fundamentals (2026-04-15)
    # Schwab fills: sector*, industry*, mcap, pe_ratio, trailing_eps, 52w_high/low,
    # dividend_yield, shares_float, avg_volume. Deep fields remain None → Layer 3.
    # (*sector/industry come only when Schwab returns reference data; often Unknown.)
    # 2026-05-08 cleanup: Polygon SIC-based sector classification removed.
    # `_polygon_get` was deleted on 2026-04-25 during the EODHD migration; the
    # try/except block here was silently failing on every call. Sector/industry/
    # market_cap now come exclusively from EODHD Highlights + Schwab fundamentals
    # (downstream layers). Variables kept as None placeholders for `or` fallbacks
    # at lines below.
    _poly_sector = None
    _poly_industry = None
    _poly_mcap = None

    # Layer 2: EODHD real-time + fundamentals (replaces Schwab+Polygon+Finnhub+FMP)
    try:
        import eodhd_client as _eod
        # 2026-05-26 · `real_time` and `fundamentals` have independent EODHD
        # quota and TTLs. Previously a real_time failure (e.g. HTTP 402 on the
        # quote endpoint) raised and short-circuited the entire lane —
        # including fundamentals, which is the source of market_cap, sector,
        # margins, ratios, etc. Real-time price is only used for `px` here
        # (and has a 52w_high fallback), so isolate its failures.
        try:
            rt = _eod.real_time(ticker) or {}
        except Exception as _rte:
            log.debug(f"eodhd real_time({ticker}) failed (lane continues): {_rte}")
            rt = {}
        sf = get_schwab_fundamentals(ticker)  # Function name kept; now EODHD-backed.

        if isinstance(sf, dict) and not sf.get("error"):
            px = (rt.get("close") if isinstance(rt, dict) else None) or sf.get("high_52w")
            try:
                px = float(px) if px and px != "NA" else None
            except (ValueError, TypeError):
                px = None

            result = {
                "ticker":           ticker,
                "name":             ticker,
                "_last_price":      px,
                "sector":           sf.get("sector") or _poly_sector or "Unknown",
                "industry":         sf.get("industry") or _poly_industry or "Unknown",
                "market_cap":       sf.get("market_cap") or _poly_mcap or 0,
                "beta":             sf.get("beta"),
                "pe_ratio":         sf.get("pe"),
                "peg_ratio":        sf.get("peg"),
                "price_to_book":    sf.get("pb"),
                "ps_ratio":         sf.get("ps"),
                "gross_margin":     sf.get("gross_margin"),
                "operating_margin": sf.get("op_margin"),
                "profit_margin":    sf.get("net_margin"),
                "roe":              sf.get("roe"),
                "roa":              sf.get("roa"),
                "roi":              sf.get("roi"),
                "current_ratio":    sf.get("current_ratio"),
                "quick_ratio":      sf.get("quick_ratio"),
                "interest_coverage": sf.get("interest_coverage"),
                "debt_to_equity":   sf.get("debt_equity"),
                "lt_debt_to_equity": sf.get("lt_debt_equity"),
                "trailing_eps":     sf.get("eps_ttm"),
                "eps_change_pct_ttm": sf.get("eps_change_pct_ttm"),
                "eps_change_year":  sf.get("eps_change_year"),
                "revenue_growth":   (sf.get("rev_change_ttm") or 0) / 100.0 if sf.get("rev_change_ttm") is not None else None,
                "dividend_yield":   (sf.get("dividend_yield") or 0) / 100.0 if sf.get("dividend_yield") is not None else None,
                "dividend_amount":  sf.get("dividend_amount"),
                "52w_high":         sf.get("high_52w"),
                "52w_low":          sf.get("low_52w"),
                "country":          sf.get("country") or "US",
                "_eodhd_fund_applied": True,
            }

            _info_cache_save(ticker, result)
            try:
                import fundamentals_store as _fs
                _fs.upsert(ticker, {
                    "sector":       result.get("sector"),
                    "industry":     result.get("industry"),
                    "market_cap":   result.get("market_cap"),
                    "shares_out":   result.get("shares_float"),
                    "week52_high":  result.get("52w_high"),
                    "week52_low":   result.get("52w_low"),
                    "eps_ttm":      result.get("trailing_eps"),
                    "pe_ttm":       result.get("pe_ratio"),
                    "gross_margin": result.get("gross_margin"),
                    "operating_margin": result.get("operating_margin"),
                    "profit_margin": result.get("profit_margin"),
                    "debt_equity":  result.get("debt_to_equity"),
                    "revenue_growth": result.get("revenue_growth"),
                    "last_earnings": (result.get("last_earnings") or None),
                }, source="eodhd")
            except Exception:
                pass
            return result
    except Exception as _ese:
        log.debug(f"eodhd get_stock_info({ticker}): {_ese}")

    # Layer 2.6: Finnhub + FMP deep fundamentals
    try:
        _fh = get_finnhub_data(ticker)
        if _fh and not _fh.get("error"):
            _deep = {
                "ticker": ticker,
                "sector": _poly_sector or _fh.get("sector") or "Unknown",
                "industry": _poly_industry or _fh.get("industry") or "Unknown",
                "market_cap": _poly_mcap or _fh.get("market_cap", 0),
                "pe_ratio": _fh.get("pe"),
                "beta": _fh.get("beta"),
                "revenue_growth": _fh.get("revenue_growth"),
                "profit_margin": _fh.get("profit_margin") or _fh.get("net_margin"),
                "gross_margin": _fh.get("gross_margin"),
                "operating_margin": _fh.get("operating_margin"),
                "debt_to_equity": _fh.get("debt_equity") or _fh.get("total_debt_to_equity"),
                "trailing_eps": _fh.get("eps"),
                "roe": _fh.get("roe") or _fh.get("return_on_equity"),
                "52w_high": _fh.get("52w_high"),
                "52w_low": _fh.get("52w_low"),
                "error": None,
                "_cache_source": "finnhub+polygon",
            }
            if any(_deep.get(k) for k in ("revenue_growth", "profit_margin", "gross_margin", "debt_to_equity")):
                _info_cache_save(ticker, _deep)
                return _deep
    except Exception:
        pass

    # Skip yfinance for ETFs — they have no fundamentals and yfinance returns 404
    _known_etf_suffixes = ("XLK", "XLF", "XLV", "XLE", "XLI", "XLB", "XLRE", "XLY",
                           "XLP", "XLC", "XLU", "SPY", "QQQ", "IWM", "DIA", "VTI")
    if ticker.upper() in _known_etf_suffixes or ticker.upper().startswith("XL"):
        _etf_result = {
            "ticker": ticker,
            "sector": _poly_sector or "ETF",
            "industry": _poly_industry or "ETF",
            "market_cap": _poly_mcap or 0,
            "error": None,
            "_cache_source": "polygon_etf",
        }
        _info_cache_save(ticker, _etf_result)
        return _etf_result

    # Layer 3: yfinance — last resort, provides deep fields (margins/growth/D-E)
    try:
        import signal as _sig

        def _timeout_handler(signum, frame):
            raise TimeoutError("yfinance info timeout")

        _sig.signal(_sig.SIGALRM, _timeout_handler)
        _sig.alarm(5)  # 5s max per ticker — 401s should fail within 2s
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
        finally:
            _sig.alarm(0)  # cancel alarm
        result = {
            "ticker": ticker,
            "sector": info.get("sector") or _poly_sector or "Unknown",
            "industry": info.get("industry") or _poly_industry or "Unknown",
            "market_cap": info.get("marketCap", 0),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "short_pct": info.get("shortPercentOfFloat"),
            "target_mean_price": info.get("targetMeanPrice"),
            "target_high_price": info.get("targetHighPrice"),
            "target_low_price":  info.get("targetLowPrice"),
            "shares_float":      info.get("floatShares"),
            "recommendation": info.get("recommendationKey"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
            "name": info.get("shortName", ticker),
            "free_cashflow":    info.get("freeCashflow"),
            "ev_to_ebitda":     info.get("enterpriseToEbitda"),
            "price_to_book":    info.get("priceToBook"),
            "institutional_pct": round(info.get("institutionsPercentHeld", 0) * 100, 1) if info.get("institutionsPercentHeld") else None,
            "forward_eps":      info.get("forwardEps"),
            "trailing_eps":     info.get("trailingEps"),
            "ps_ratio":             info.get("priceToSalesTrailing12Months"),
            "operating_cashflow":   info.get("operatingCashflow"),
            "total_cash":           info.get("totalCash"),
            "earnings_qoq_growth":  info.get("earningsQuarterlyGrowth"),
            "forward_eps_growth":   round((info.get("forwardEps", 0) / info.get("trailingEps", 1) - 1), 4) if info.get("trailingEps") and info.get("trailingEps") != 0 else None,
            "price_to_cashflow":    round(info.get("marketCap", 0) / info.get("operatingCashflow", 1), 2) if info.get("operatingCashflow") and info.get("operatingCashflow") > 0 else None,
            "error": None
        }
        _info_cache_save(ticker, result)
        # Mirror to sqlite (2026-04-15)
        try:
            import fundamentals_store as _fs
            _fs.upsert(ticker, {
                "sector":   info.get("sector"),
                "industry": info.get("industry"),
                "market_cap":   info.get("marketCap"),
                "shares_out":   info.get("sharesOutstanding"),
                "beta":         info.get("beta"),
                "week52_high":  info.get("fiftyTwoWeekHigh"),
                "week52_low":   info.get("fiftyTwoWeekLow"),
                "eps_ttm":      info.get("trailingEps"),
                "eps_growth_qoq": info.get("earningsQuarterlyGrowth"),
                "pe_ttm":       info.get("trailingPE"),
                "forward_pe":   info.get("forwardPE"),
                "revenue_ttm":  info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "gross_margin":   info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "debt_equity":   info.get("debtToEquity"),
                "fcf_ttm":       info.get("freeCashflow"),
                "short_float":   info.get("shortPercentOfFloat"),
                "next_earnings": info.get("earningsDate"),
            }, source="yfinance")
        except Exception:
            pass
        return result
    except Exception as e:
        # Try sqlite stale fallback first (2026-04-15)
        try:
            import fundamentals_store as _fs
            rec = _fs.get(ticker)
            if rec:
                return {
                    "ticker": ticker,
                    "sector": rec.get("sector") or "Unknown",
                    "industry": rec.get("industry") or "Unknown",
                    "market_cap":       rec.get("market_cap") or 0,
                    "revenue_growth":   rec.get("revenue_growth"),
                    "earnings_growth":  rec.get("eps_growth_qoq"),
                    "profit_margin":    rec.get("profit_margin"),
                    "gross_margin":     rec.get("gross_margin"),
                    "operating_margin": rec.get("operating_margin"),
                    "debt_to_equity":   rec.get("debt_equity"),
                    "pe_ratio":         rec.get("pe_ttm"),
                    "forward_pe":       rec.get("forward_pe"),
                    "beta":             rec.get("beta"),
                    "short_pct":        rec.get("short_float"),
                    "shares_float":     rec.get("shares_out"),
                    "52w_high":         rec.get("week52_high"),
                    "52w_low":          rec.get("week52_low"),
                    "free_cashflow":    rec.get("fcf_ttm"),
                    "trailing_eps":     rec.get("eps_ttm"),
                    "error": None,
                    "_cache_source": "sqlite_stale",
                }
        except Exception:
            pass
        # Legacy JSON stale fallback (up to 30 days old)
        stale = _info_cache_load(ticker, max_age_days=30)
        if stale:
            return stale
        log.debug(f"get_stock_info({ticker}): {e}")
        return {"ticker": ticker, "error": str(e)}


def get_quarterly_revenue_growth(ticker: str) -> float | None:
    """Fetch QoQ revenue growth from quarterly financials."""
    try:
        t = yf.Ticker(ticker)
        qf = t.quarterly_financials
        if qf is None or qf.empty:
            return None
        rev_row = None
        for label in ["Total Revenue", "Revenue"]:
            if label in qf.index:
                rev_row = qf.loc[label]
                break
        if rev_row is None or len(rev_row) < 2:
            return None
        q1 = float(rev_row.iloc[0])
        q2 = float(rev_row.iloc[1])
        if q2 == 0:
            return None
        return round((q1 / q2 - 1), 4)
    except Exception:
        return None


def get_stock_info_batch(tickers: list[str], max_workers: int = 6) -> dict[str, dict]:
    """Fetch fundamental info for multiple tickers in parallel.

    Optimisations:
    1. Cache-first: serve tickers with a fresh disk cache instantly (no thread overhead).
    2. Only submit uncached tickers to the thread pool.
    3. Higher worker count (16) for the uncached subset — most will hit 401 quickly.
    """
    results = {}

    # ── Pass 1: serve from disk cache immediately ─────────────────────────────
    uncached = []
    for t in tickers:
        cached = _info_cache_load(t)  # 3-day TTL
        if cached is not None:
            results[t] = cached
        else:
            uncached.append(t)

    if not uncached:
        return results

    # ── Pass 2: fetch only the uncached tickers in parallel ───────────────────
    workers = min(16, max(max_workers, len(uncached)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(get_stock_info, t): t for t in uncached}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                results[ticker] = fut.result()
            except Exception as e:
                results[ticker] = {"ticker": ticker, "error": str(e)}
    return results


def get_index_quotes() -> list[dict]:
    """True headline-index quotes for the Home cross-asset tape.

    Indices + 10Y yield from SCHWAB market-data (live, real index symbols —
    $SPX/$COMPX/$DJI/$RUT/$VIX/$TNX); crypto (BTC/ETH) from EODHD .CC feed.
    Schwab is the only source in our (no-new-license) stack that returns the
    real headline index level (EODHD .INDX returns NA for most; GSPC.INDX works
    but Schwab is live + batched in one call). $TNX is yield×10 → /10 to %.

    Returns an ordered list of {key, label, value, chg, suffix} — value is a
    number, chg is daily %, suffix is "%" for yields else "". Failures drop the
    affected tile rather than break the row (feed-honest).
    """
    out: list[dict] = []
    # ── Schwab indices (one batched call) ──
    try:
        import schwab_client as _sc
        SPEC = [
            ("$SPX",   "S&P 500", ""),
            ("$COMPX", "NASDAQ",  ""),
            ("$DJI",   "DOW",     ""),
            ("$RUT",   "RUSSELL", ""),
            ("$VIX",   "VIX",     ""),
            ("$TNX",   "US 10Y",  "%"),
        ]
        blobs = _sc.get_quotes_batch([s for s, _, _ in SPEC]) or {}
        for sym, label, suffix in SPEC:
            b = blobs.get(sym) or blobs.get(sym.upper())
            q = (b or {}).get("quote") or {}
            last = q.get("lastPrice")
            chg = q.get("netPercentChange")
            if last in (None, "", "NA"):
                continue
            try:
                last = float(last)
            except Exception:
                continue
            try:
                chg = float(chg) if chg not in (None, "", "NA") else None
            except Exception:
                chg = None
            if sym == "$TNX":           # CBOE 10Y yield index is quoted ×10
                last = round(last / 10.0, 3)
            out.append({"key": sym.lstrip("$"), "label": label,
                        "value": round(last, 2) if suffix != "%" else last,
                        "chg": (round(chg, 2) if chg is not None else None),
                        "suffix": suffix})
    except Exception:
        pass
    # ── EODHD crypto (Schwab has no crypto) ──
    try:
        import eodhd_client as _eod
        for sym, label in [("BTC-USD.CC", "BTCUSD"), ("ETH-USD.CC", "ETHUSD")]:
            try:
                r = _eod.real_time(sym)
                d = r if isinstance(r, dict) else (r[0] if isinstance(r, list) and r else None)
                if not d:
                    continue
                close, chg = d.get("close"), d.get("change_p")
                if close in (None, "", "NA"):
                    continue
                close = float(close)
                chg = float(chg) if chg not in (None, "", "NA") else None
                out.append({"key": label, "label": label, "value": round(close, 2), "chg": (round(chg, 2) if chg is not None else None), "suffix": ""})
            except Exception:
                continue
    except Exception:
        pass
    return out


def get_market_regime(breadth: dict | None = None) -> dict:
    """
    Assess market regime from SPY + QQQ technicals + VIX + market breadth.
    4-regime classification:
    - risk_on_trending: SPY > 50/200, QQQ > 50, VIX < 18, breadth > 65%
    - risk_on_choppy: SPY > 50, VIX 18-25, breadth 40-65%
    - risk_off_trending: SPY < 50, VIX 25-35, breadth 20-40%
    - panic: VIX > 35 OR breadth < 20%
    Legacy mapping: risk_on_trending→bull, risk_on_choppy→neutral, risk_off→bear, panic→bear
    """
    try:
        # SPY + QQQ via EODHD
        md = fetch_market_data(["SPY", "QQQ"], period="1y")
        _spy_df = md.get("SPY")
        _qqq_df = md.get("QQQ")

        if (_spy_df is None or len(_spy_df) < 10) and (_qqq_df is None or len(_qqq_df) < 10):
            return {"regime": "unknown", "regime4": "unknown", "spy_price": 0}

        close_series = _spy_df["Close"].squeeze().dropna()
        vol_series   = _spy_df["Volume"].squeeze().dropna() if "Volume" in _spy_df.columns else None
        if close_series.empty:
            return {"regime": "unknown", "regime4": "unknown", "spy_price": 0}

        close = close_series.values
        price = float(close[-1])

        ema50  = _ema(close, 50)
        sma200 = _sma(close, 200)

        # Full EMA50 series for consecutive-close confirmation (regime_thresholds.risk_off_consecutive_closes).
        # Cheap — same series used as input to scalar _ema above.
        _ema50_full = pd.Series(close).ewm(span=50, adjust=False).mean().values if len(close) >= 50 else None

        # QQQ technicals
        qqq_close = _qqq_df["Close"].squeeze().dropna().values
        qqq_ema50 = _ema(qqq_close, 50) if len(qqq_close) >= 50 else qqq_close[-1]
        qqq_price = float(qqq_close[-1]) if len(qqq_close) > 0 else 0
        qqq_above_ema50 = qqq_price > qqq_ema50 if qqq_ema50 else False

        # Today's SPY % change (entry day gate)
        spy_daily_chg = ((close[-1] - close[-2]) / close[-2] * 100) if len(close) >= 2 else 0.0

        # SPY 1-month return
        spy_1m_ret = (price / float(close[-21]) - 1) * 100 if len(close) >= 21 else 0

        above_50  = price > ema50  if ema50  else False
        above_200 = price > sma200 if sma200 else False

        # 3-regime for legacy compatibility
        if above_50 and above_200:
            regime = "bull"
        elif not above_50 and not above_200:
            regime = "bear"
        else:
            regime = "neutral"

        # Get VIX and breadth. Track DEGRADED inputs explicitly: VIX and breadth drive
        # the panic / trending edges, and silently defaulting them (VIX→20, breadth→50)
        # masks a data outage as a plausible risk_on_choppy — exactly when the regime
        # signal (principle 18: "regime detection IS the strategy") is blind. Record the
        # gap so the decision layer / dashboard can flag low-confidence regime, instead
        # of trusting a fabricated-neutral classification (audit 2026-06-03).
        _regime_degraded = []
        vix_data   = get_vix_data()
        vix_cur    = (vix_data or {}).get("vix_current")
        if vix_cur is None:
            vix_cur = 20  # fallback so we don't crash — but the gap is recorded below
            _regime_degraded.append("vix")

        # Get market breadth (% of stocks above 50DMA)
        pct_above_50d = 50  # default fallback
        if breadth and isinstance(breadth, dict):
            _b = breadth.get("pct_above_50d")
            if _b is not None:
                pct_above_50d = _b
            else:
                _regime_degraded.append("breadth")
        else:
            _regime_degraded.append("breadth")
        if _regime_degraded:
            log.warning(f"  ⚠ REGIME on DEGRADED inputs {_regime_degraded} (defaulted) — "
                        f"panic/trending edges unreliable until data restored; "
                        f"classification confidence is LOW this scan")

        # 4-regime classification with hysteresis
        # Load previous regime from cache for hysteresis buffer
        _hysteresis_fp = BASE_DIR / "cache" / "regime_hysteresis.json"
        _prev_regime4 = "risk_on_choppy"  # default if no cache
        try:
            if _hysteresis_fp.exists():
                _hyst_data = json.loads(_hysteresis_fp.read_text())
                _prev_regime4 = _hyst_data.get("regime4", "risk_on_choppy")
        except Exception:
            pass

        # Load hysteresis config (buffers to prevent whipsaws)
        _cfg_loaded = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
        _hyst_cfg = _cfg_loaded.get("regime_hysteresis", {})
        _vix_risk_off_enter = _hyst_cfg.get("vix_risk_off_enter", 22)
        _vix_risk_on_return = _hyst_cfg.get("vix_risk_on_return", 18)
        _breadth_bull_enter = _hyst_cfg.get("breadth_bullish_enter", 53)
        _breadth_bear_enter = _hyst_cfg.get("breadth_bearish_enter", 47)

        # Load regime classifier thresholds (V4 backtest 2026-05-10: cache/regime_backtest_latest.json).
        # See config.regime_classifier._validations for the evidence trail.
        # NOTE: separate from config.regime_thresholds (legacy 3-regime score gates)
        # and config.regime4_thresholds (4-regime score/RS/RR gates).
        _thr_cfg = _cfg_loaded.get("regime_classifier", {})
        _panic_vix          = _thr_cfg.get("panic_vix", 35.0)
        _panic_breadth      = _thr_cfg.get("panic_breadth", 20.0)
        _trending_vix       = _thr_cfg.get("trending_vix", 20.0)         # was 18 pre-V4
        _trending_breadth   = _thr_cfg.get("trending_breadth", 60.0)     # was 65 pre-V4
        _risk_off_n_closes  = int(_thr_cfg.get("risk_off_consecutive_closes", 2))  # was 1 pre-V4
        # 2026-05-13 KILLSWITCH flags for the 3 in-classifier regime gates
        _gate_vix_dyn_on    = bool(_thr_cfg.get("gate_vix_dynamics_enabled", True))
        _gate_dist_on       = bool(_thr_cfg.get("gate_distribution_days_enabled", True))
        _gate_hmm_on        = bool(_thr_cfg.get("gate_hmm_blend_enabled", True))

        # Apply hysteresis: use buffered thresholds based on current regime direction
        _is_currently_risk_off = _prev_regime4 in ("risk_off_trending", "panic")
        _is_currently_risk_on = _prev_regime4 in ("risk_on_trending",)

        # VIX hysteresis: harder to enter risk-off, harder to leave it
        _vix_threshold_for_risk_on = _vix_risk_on_return if _is_currently_risk_off else _trending_vix
        _vix_threshold_for_risk_off = _vix_risk_off_enter if not _is_currently_risk_off else 18

        # Breadth hysteresis: require overshoot before flipping
        _breadth_for_bull = _breadth_bull_enter if not _is_currently_risk_on else 50
        _breadth_for_bear = _breadth_bear_enter if _is_currently_risk_on else 50

        # Compute consecutive-close streak below EMA50 (risk_off confirmation).
        # n=1 reproduces legacy single-bar trigger; n=2 (V4 default) requires
        # two consecutive closes below before flipping risk-off.
        _risk_off_confirmed = False
        if _risk_off_n_closes <= 1:
            _risk_off_confirmed = not above_50
        elif _ema50_full is not None and len(close) >= _risk_off_n_closes:
            _risk_off_confirmed = all(
                close[-i] < _ema50_full[-i] for i in range(1, _risk_off_n_closes + 1)
            )
        else:
            # Insufficient history — fall back to single-bar behavior to stay safe
            _risk_off_confirmed = not above_50

        # ── Audit 2026-06-03 regime guards (flag-gated, reversible) ──────────────
        # Fix B (default ON): when VIX/breadth are DEGRADED we cannot confirm the
        #   risk_on_trending criteria (VIX<18, breadth>65) — refuse the risk-on upgrade
        #   and lean defensive instead of trusting the 20/50 defaults. Pure data-integrity
        #   (principle 18); only ever REDUCES risk (trending→choppy).
        # Fix A (default OFF): a sub-EMA50 tape that hasn't yet confirmed risk-off is NOT
        #   "risk-on" — flag it transitioning/defensive so sizing can de-risk, WITHOUT
        #   breaking the 4-regime contract or fighting the risk-off hysteresis. Default OFF
        #   because the audit (n=23 below-50 trades, hit 74%) does NOT clear the n>=30 bar.
        _flag_degraded_no_riskon = bool(_thr_cfg.get("regime_degraded_no_risk_on", True))
        _flag_choppy_above50     = bool(_thr_cfg.get("regime_choppy_requires_above_50", False))
        _defensive_lean = False
        _defensive_reason = None

        _can_trend = (above_50 and above_200 and qqq_above_ema50
                      and vix_cur is not None and vix_cur < _vix_threshold_for_risk_on
                      and pct_above_50d is not None and pct_above_50d > max(_trending_breadth, _breadth_for_bull))
        if _flag_degraded_no_riskon and _regime_degraded and _can_trend:
            _can_trend = False
            _defensive_lean = True
            _defensive_reason = "degraded_inputs_no_risk_on"

        if (vix_cur is not None and vix_cur > _panic_vix) or (pct_above_50d is not None and pct_above_50d < _panic_breadth):
            regime4 = "panic"
        elif _risk_off_confirmed:
            regime4 = "risk_off_trending"
        elif _can_trend:
            regime4 = "risk_on_trending"
        else:
            regime4 = "risk_on_choppy"
            # A sub-EMA50 'choppy' (below 50-day, risk-off not yet confirmed) is the
            # mislabel window — lean defensive when the flag is on.
            if not above_50:
                _defensive_lean = True
                _defensive_reason = _defensive_reason or "below_ema50_unconfirmed"
            if _flag_degraded_no_riskon and _regime_degraded:
                _defensive_lean = True
                _defensive_reason = _defensive_reason or "degraded_inputs"

        # Persist current regime for next run's hysteresis
        try:
            _hysteresis_fp.parent.mkdir(parents=True, exist_ok=True)
            _hysteresis_fp.write_text(json.dumps({
                "regime4": regime4,
                "prev_regime4": _prev_regime4,
                "vix": vix_cur,
                "breadth_50d": pct_above_50d,
            }))
        except Exception:
            pass

        # Map 4-regime back to legacy 3-regime for backward compatibility
        _regime4_to_legacy = {
            "risk_on_trending": "bull",
            "risk_on_choppy": "neutral",
            "risk_off_trending": "bear",
            "panic": "bear",
        }
        _publish_regime_base = _regime4_to_legacy.get(regime4, "neutral")

        # Distribution days: down days on higher volume than prior day (last 25 sessions)
        dist_days = 0
        if vol_series is not None and len(vol_series) >= 26:
            vol = vol_series.values
            c   = close_series.values
            for i in range(-25, 0):
                if c[i] < c[i - 1] and vol[i] > vol[i - 1]:
                    dist_days += 1

        # Distribution state — IBD/CAN-SLIM convention for institutional
        # selling pressure. We already track dist_days for per-stock gates
        # (config.gates.distribution_days_no_new=7); regime classifier
        # ignored it until now. Per quant audit: gap #4 closed.
        # Thresholds (IBD canonical):
        #   0-2: confirmed uptrend (healthy)
        #   3-4: confirmed uptrend with caution
        #   5-6: uptrend under pressure  ← regime downgrade signal
        #   7+:  market in correction    ← strong downgrade signal
        if dist_days >= 7:
            dist_state = "correction"
            dist_downgrade = True
        elif dist_days >= 5:
            dist_state = "under_pressure"
            dist_downgrade = True
        elif dist_days >= 3:
            dist_state = "caution"
            dist_downgrade = False
        else:
            dist_state = "healthy"
            dist_downgrade = False

        # VIX-dynamics regime downgrade (audit gap #3, 2026-05-11).
        # Composite vol_state (level + slope + term structure) drives the
        # downgrade. References:
        #   - VIX backwardation (VIX > VIX3M) precedes 80% of 3%+ SPX selloffs
        #     within 2 weeks (CBOE volatility research 2010-2023)
        #   - VIX slope >25%/5d at rising VIX is leading risk-off regardless
        #     of absolute level (vol-regime velocity gate)
        # Don't touch panic — already at max defensive.
        _vol_state = (vix_data or {}).get("vol_state", "unknown")
        if _gate_vix_dyn_on and _vol_state == "spike_imminent" and regime4 in ("risk_on_trending", "risk_on_choppy"):
            _orig_regime4 = regime4
            regime4 = "risk_off_trending"
            log.info(
                f"  Regime DOWNGRADED by vol term structure: {_orig_regime4} → {regime4} "
                f"(vol_state={_vol_state}, vix={(vix_data or {}).get('vix_current')}, "
                f"ts_ratio={(vix_data or {}).get('term_structure_ratio')})"
            )
        elif _gate_vix_dyn_on and _vol_state == "rising_fast" and regime4 == "risk_on_trending":
            _orig_regime4 = regime4
            regime4 = "risk_on_choppy"
            log.info(
                f"  Regime DOWNGRADED by VIX slope: {_orig_regime4} → {regime4} "
                f"(vol_state={_vol_state}, slope_5d={(vix_data or {}).get('slope_5d')}%)"
            )

        # Distribution-days regime downgrade (audit gap #4, 2026-05-11).
        # IBD rule: 5+ distribution days = market under institutional pressure.
        # Downgrade risk_on_trending → risk_on_choppy (matches CAN-SLIM
        # "uptrend under pressure" state). Risk_on_choppy stays as-is —
        # the dist_state label surfaces the warning to operators.
        # Don't touch risk_off_trending or panic — those are already defensive.
        if _gate_dist_on and dist_downgrade and regime4 == "risk_on_trending":
            _orig_regime4 = regime4
            regime4 = "risk_on_choppy"
            log.info(
                f"  Regime DOWNGRADED by distribution days: {_orig_regime4} → {regime4} "
                f"(dist_days={dist_days}, state={dist_state})"
            )

        # HMM probability blend (audit gap #5, 2026-05-11) — soft regime
        # probabilities computed from SPY 21-day return distribution.
        # The discrete regime4 classifier looks at structural levels (EMAs,
        # VIX, breadth); HMM looks at the SHAPE of recent SPY returns.
        # When the two disagree, surface it. Disagreement most often means
        # the structural classifier is lagging a regime shift the return
        # distribution already detected.
        hmm = {}
        try:
            import regime_hmm as _rh
            # Reuse SPY closes already fetched at top of function.
            _spy_closes = list(close_series.values) if close_series is not None else []
            if len(_spy_closes) >= 22:
                hmm = _rh.regime_probabilities_from_closes(_spy_closes[-60:], lookback=21)
        except Exception as _he:
            log.debug(f"HMM regime compute: {_he}")

        # HMM disagreement gates:
        #   discrete=risk_on_trending + p_bear >= 0.30 → downgrade to choppy
        #     (return distribution shows bearish tail emerging)
        #   discrete=risk_on_trending/choppy + p_bear >= 0.50 → downgrade to risk_off
        #     (HMM strongly bear; structural signals haven't caught up yet)
        #   discrete=risk_off_trending + p_bull >= 0.70 + confidence >= 0.6 → upgrade to choppy
        #     (HMM detects recovery before SPY reclaims EMA50)
        hmm_action = None
        if _gate_hmm_on and hmm and not hmm.get("error"):
            _p_bull = float(hmm.get("p_bull") or 0)
            _p_bear = float(hmm.get("p_bear") or 0)
            _conf   = float(hmm.get("confidence") or 0)

            if regime4 == "risk_on_trending" and _p_bear >= 0.50:
                regime4 = "risk_off_trending"
                hmm_action = f"strong-bear ({_p_bear:.2f}) → risk_off"
            elif regime4 in ("risk_on_trending", "risk_on_choppy") and _p_bear >= 0.50 and _conf >= 0.6:
                if regime4 == "risk_on_trending":
                    regime4 = "risk_off_trending"
                    hmm_action = f"bear-confirmed ({_p_bear:.2f},c{_conf:.2f}) → risk_off"
            elif regime4 == "risk_on_trending" and _p_bear >= 0.30:
                regime4 = "risk_on_choppy"
                hmm_action = f"bear-tail ({_p_bear:.2f}) → choppy"
            elif regime4 == "risk_off_trending" and _p_bull >= 0.70 and _conf >= 0.6:
                regime4 = "risk_on_choppy"
                hmm_action = f"recovery ({_p_bull:.2f},c{_conf:.2f}) → choppy"

            if hmm_action:
                log.info(f"  Regime DOWNGRADED/UPGRADED by HMM: {hmm_action}")

        # Market cycle: four-phase model
        # Early bull: recovering from below 200d, breadth expanding
        # Mid bull: above all MAs, VIX low, cyclicals leading
        # Late bull: above MAs but defensives outperforming
        # Bear/correction: below 200d
        vix_data   = get_vix_data()
        vix_cur    = (vix_data or {}).get("vix_current")
        if vix_cur is None:
            vix_cur = 20  # safe default when VIX fetch failed
        spy_3m_ret = (price / float(close[-63]) - 1) * 100 if len(close) >= 63 else spy_1m_ret

        if not above_200:
            market_cycle = "bear"
        elif above_50 and above_200 and vix_cur is not None and vix_cur < 18 and spy_3m_ret is not None and spy_3m_ret > 5:
            market_cycle = "mid_bull"
        elif above_50 and above_200 and spy_1m_ret is not None and spy_1m_ret > 0:
            market_cycle = "early_bull" if (spy_3m_ret is not None and spy_3m_ret < 5) else "mid_bull"
        elif above_200 and not above_50:
            market_cycle = "late_bull" if (spy_1m_ret is not None and spy_1m_ret < 0) else "neutral"
        else:
            market_cycle = "neutral"

        # ── 2-bar confirmation: require 2 consecutive bars before publishing a regime4 flip ──
        # Prevents whipsaws when SPY briefly crosses EMA50/SMA200 for a single session.
        from datetime import date as _date
        _today_str = str(_date.today())
        _rh_fp = BASE_DIR / "cache" / "regime_history.json"
        try:
            _rh = json.loads(_rh_fp.read_text()) if _rh_fp.exists() else {}
        except Exception:
            _rh = {}

        _confirmed_regime4 = _rh.get("confirmed_regime4", regime4)
        _pending   = _rh.get("pending_flip", {})

        if regime4 == _confirmed_regime4:
            # Sustained regime — clear any stale pending flip
            _rh["confirmed_regime4"] = regime4
            _rh["pending_flip"] = {}
            _publish_regime4 = regime4
        elif _pending.get("regime4") == regime4 and _pending.get("date") != _today_str:
            # Second bar agrees with new regime → confirm the flip
            _rh["confirmed_regime4"] = regime4
            _rh["pending_flip"] = {}
            _rh["flip_confirmed_date"] = _today_str
            _publish_regime4 = regime4
            log.info(f"Market regime4 flip CONFIRMED: {_confirmed_regime4} → {regime4}")
        else:
            # First bar of a different regime → hold prior, store as pending
            if _pending.get("regime4") != regime4:
                log.info(f"Market regime4 flip PENDING: {_confirmed_regime4} → {regime4} (need 2nd bar)")
            _rh["pending_flip"] = {"regime4": regime4, "date": _today_str}
            _publish_regime4 = _confirmed_regime4

        # Legacy 3-regime for backward compatibility (from confirmed regime4)
        _publish_regime = _regime4_to_legacy.get(_publish_regime4, "neutral")

        try:
            _rh_fp.parent.mkdir(parents=True, exist_ok=True)
            _rh_fp.write_text(json.dumps(_rh))
        except Exception as e:
            log.debug(f"Regime history write failed: {e}")

        # Market cycle (4-phase for legacy compatibility)
        spy_3m_ret = (price / float(close[-63]) - 1) * 100 if len(close) >= 63 else spy_1m_ret
        if not above_200:
            market_cycle = "bear"
        elif above_50 and above_200 and vix_cur is not None and vix_cur < 18 and spy_3m_ret is not None and spy_3m_ret > 5:
            market_cycle = "mid_bull"
        elif above_50 and above_200 and spy_1m_ret is not None and spy_1m_ret > 0:
            market_cycle = "early_bull" if (spy_3m_ret is not None and spy_3m_ret < 5) else "mid_bull"
        elif above_200 and not above_50:
            market_cycle = "late_bull" if (spy_1m_ret is not None and spy_1m_ret < 0) else "neutral"
        else:
            market_cycle = "neutral"

        # Max position size based on regime4
        _max_size_pct_map = {
            "risk_on_trending": 100,
            "risk_on_choppy": 70,
            "risk_off_trending": 35,
            "panic": 0,
        }
        max_size_pct = _max_size_pct_map.get(_publish_regime4, 70)

        # Defensive size haircut when the regime is flagged transitioning/blind (audit
        # 2026-06-03). Degraded-input haircut (Fix B) is default-ON but only fires on an
        # actual VIX/breadth outage — normal scans pass real breadth so this is dark.
        # Below-EMA50 haircut (Fix A) only fires when its flag is on (default OFF).
        _defensive_size_mult = 1.0
        if _defensive_lean:
            if _defensive_reason in ("degraded_inputs", "degraded_inputs_no_risk_on") and _flag_degraded_no_riskon:
                _defensive_size_mult = float(_thr_cfg.get("regime_degraded_size_mult", 0.5))
            elif _defensive_reason == "below_ema50_unconfirmed" and _flag_choppy_above50:
                _defensive_size_mult = float(_thr_cfg.get("regime_below50_size_mult", 0.5))
        if _defensive_size_mult != 1.0:
            max_size_pct = int(round(max_size_pct * _defensive_size_mult))

        return {
            # Defensive-lean flags (audit 2026-06-03) — surfaced always (informational);
            # only change max_size_pct when the controlling flag is on (see above).
            "regime_transitioning": _defensive_lean,
            "defensive_reason":     _defensive_reason,
            "defensive_size_mult":  _defensive_size_mult,
            # Data-quality flags — surface degraded regime inputs so the decision layer
            # and dashboard can flag low-confidence regime instead of trusting a
            # fabricated-neutral classification (audit 2026-06-03, principle 18).
            "data_quality":         "degraded" if _regime_degraded else "ok",
            "degraded_inputs":      _regime_degraded,
            # Legacy 3-regime (backward compatible)
            "regime":               _publish_regime,
            "regime_raw":           regime,
            "regime_pending_flip":  _pending.get("regime") if regime != _publish_regime else None,
            # New 4-regime system
            "regime4":              _publish_regime4,
            "regime4_raw":          regime4,
            "qqq_above_ema50":      qqq_above_ema50,
            "qqq_price":            round(qqq_price, 2),
            "breadth_pct_50d":      pct_above_50d,
            "max_size_pct":         max_size_pct,
            # Technical levels
            "spy_price":            round(price, 2),
            "spy_ema50":            round(ema50,  2) if ema50  else None,
            "spy_sma200":           round(sma200, 2) if sma200 else None,
            "above_50ema":          above_50,
            "above_200sma":         above_200,
            # Market data
            "spy_1m_ret":           round(spy_1m_ret, 1),
            "spy_daily_chg":        round(float(spy_daily_chg), 2),
            "distribution_days":    dist_days,
            "distribution_state":   dist_state,
            # HMM probability blend (gap #5)
            "hmm_regime":           hmm,
            "hmm_action":           hmm_action,
            # Composite blended sizing multiplier across all 3 HMM probs.
            # Replaces compute_regime_confidence_modifier()'s p_bull-only
            # logic with a continuous blend that uses the full distribution.
            "hmm_size_mult": (
                round(
                    float(hmm.get("p_bull") or 0) * 1.00 +
                    float(hmm.get("p_neutral") or 0) * 0.70 +
                    float(hmm.get("p_bear") or 0) * 0.40,
                    3,
                ) if (hmm and not hmm.get("error")) else 1.0
            ),
            "market_cycle":         market_cycle,
            "vix":                  vix_data,
            "vix_current":          vix_cur,
            # Item #9 — SPY rolling Sharpe as cross-validation regime signal.
            # Independent of the 4-regime classifier; flags late-stage bull /
            # regime instability when SPY Sharpe < 0.5. Informational only.
            "spy_sharpe": _spy_sharpe_payload(close) if len(close) >= 30 else None,
        }
    except Exception as e:
        log.error(f"Market regime check failed: {e}")
        return {"regime": "unknown", "spy_price": 0}


def _spy_sharpe_payload(spy_closes) -> dict:
    """Cross-validation SPY-Sharpe signal across 20/60/126/252 windows."""
    try:
        from lib.sharpe_utils import sharpe_annualized, rolling_sharpe, consistency_score
        closes = list(map(float, spy_closes))
        sh_126, ret_a, vol_a = sharpe_annualized(closes, lookback=126)
        rolling = rolling_sharpe(closes, windows=(20, 60, 126, 252))
        consistency = consistency_score(rolling)
        # Signal: SPY Sharpe < 0.5 = late-stage / weak market — independent caution flag
        signal = "neutral"
        if sh_126 is not None:
            if sh_126 < 0:
                signal = "RISK_OFF — SPY Sharpe negative"
            elif sh_126 < 0.5:
                signal = "CAUTION — SPY Sharpe weak (<0.5)"
            elif sh_126 > 1.5:
                signal = "STRONG — SPY Sharpe robust (>1.5)"
            else:
                signal = "OK"
        return {
            "sharpe_126d_ann": sh_126,
            "ret_ann_pct": ret_a,
            "vol_ann_pct": vol_a,
            "rolling": {str(k): v for k, v in rolling.items()},
            "consistency": consistency,
            "signal": signal,
        }
    except Exception:
        return {}


def compute_sector_dispersion(sector_etf_data: dict) -> dict:
    """
    Quant-researcher signal: how broad is the rally?

    Narrow leadership (1-2 sectors carrying the index) is a textbook
    fragile-bull / late-cycle marker. Today's scan: SPY +8.6%/1M with
    XLK as the lone leader → regime says risk_on_choppy, but the
    underlying dispersion suggests treating this with more caution.

    Inputs: sector_etf_data from get_sector_etf_data() — 11 sector ETFs
    with vs_spy_pct (63-day) already computed.

    Returns dict with:
      - sectors_outperforming_spy: count of sectors with vs_spy_pct > 0
      - sectors_positive_absolute:  count with perf_pct > 0
      - leadership_breadth:         "broad" / "moderate" / "narrow"
      - top_3_leaders:              [(etf, vs_spy_pct), ...]
      - dispersion_stdev:           stdev of vs_spy_pct across 11 sectors
      - leadership_concentration:   top-3 share of total positive vs_spy_pct
      - rotation_signal:            "offensive" / "defensive" / "mixed"
      - is_tech_only:               XLK or XLC leads with >5pp gap over #3
      - downgrade_regime:           bool — should regime classifier downgrade?

    Thresholds (V1 — to be validated via picks_history per principle 1):
      - "broad":    >=6 sectors outperforming SPY
      - "moderate": 3-5 outperforming
      - "narrow":   <=2 outperforming  ← regime downgrade signal

    Reference: Lowry's NYSE 1996-2008 study — narrow leadership preceded
    every major correction by 4-12 weeks. Sector dispersion has
    significant predictive power above and beyond raw breadth indicators.
    """
    if not sector_etf_data:
        return {
            "leadership_breadth": "unknown",
            "downgrade_regime": False,
            "_error": "no sector data",
        }
    # Filter to actual sector ETFs (skip SPY + sub-dicts like _indices)
    sectors = {
        etf: d for etf, d in sector_etf_data.items()
        if etf not in ("SPY",) and not etf.startswith("_")
        and isinstance(d, dict) and "vs_spy_pct" in d
    }
    if not sectors:
        return {
            "leadership_breadth": "unknown",
            "downgrade_regime": False,
            "_error": "no sector rows with vs_spy_pct",
        }

    vs_spy_vals = [(etf, d.get("vs_spy_pct", 0) or 0) for etf, d in sectors.items()]
    vs_spy_vals.sort(key=lambda x: x[1], reverse=True)

    out_spy = sum(1 for _, v in vs_spy_vals if v > 0)
    pos_abs = sum(1 for _, d in sectors.items() if (d.get("perf_pct", 0) or 0) > 0)

    if out_spy >= 6:
        leadership = "broad"
    elif out_spy >= 3:
        leadership = "moderate"
    else:
        leadership = "narrow"

    # Stdev of vs_spy_pct — wider spread = more dispersion (rotation),
    # tight cluster around zero = consensus / efficient market.
    _vals = [v for _, v in vs_spy_vals]
    _mean = sum(_vals) / len(_vals) if _vals else 0
    _var  = sum((v - _mean) ** 2 for v in _vals) / len(_vals) if _vals else 0
    _stdev = _var ** 0.5

    # Concentration: top-3 vs total
    _top3_sum = sum(v for _, v in vs_spy_vals[:3] if v > 0)
    _total_pos = sum(v for _, v in vs_spy_vals if v > 0) or 1.0
    _concentration = _top3_sum / _total_pos

    # Offensive vs defensive rotation
    _offensive = {"XLK", "XLC", "XLY", "XLF", "XLI", "XLB"}
    _defensive = {"XLP", "XLU", "XLV", "XLRE"}
    _off_leading = sum(1 for etf, v in vs_spy_vals if etf in _offensive and v > 0)
    _def_leading = sum(1 for etf, v in vs_spy_vals if etf in _defensive and v > 0)
    if _off_leading >= 4 and _def_leading <= 1:
        rotation = "offensive"
    elif _def_leading >= 3 and _off_leading <= 2:
        rotation = "defensive"  # late-cycle warning
    else:
        rotation = "mixed"

    # Tech-only leadership detection (XLK/XLC dominant, big gap to #3)
    _top = vs_spy_vals[0] if vs_spy_vals else (None, 0)
    _third = vs_spy_vals[2][1] if len(vs_spy_vals) >= 3 else 0
    is_tech_only = (
        _top[0] in ("XLK", "XLC")
        and _top[1] > 0
        and (_top[1] - _third) > 5.0
        and out_spy <= 3
    )

    # Regime downgrade trigger — narrow leadership OR defensive rotation
    # is sufficient to refuse a risk_on_trending classification.
    downgrade = (leadership == "narrow") or is_tech_only or (rotation == "defensive")

    return {
        "sectors_outperforming_spy":  out_spy,
        "sectors_positive_absolute":  pos_abs,
        "sectors_total":              len(sectors),
        "leadership_breadth":         leadership,
        "top_3_leaders":              [(e, round(v, 2)) for e, v in vs_spy_vals[:3]],
        "bottom_3_laggards":          [(e, round(v, 2)) for e, v in vs_spy_vals[-3:]],
        "dispersion_stdev":           round(_stdev, 2),
        "leadership_concentration":   round(_concentration, 3),
        "rotation_signal":            rotation,
        "offensive_count":            _off_leading,
        "defensive_count":            _def_leading,
        "is_tech_only":               is_tech_only,
        "downgrade_regime":           downgrade,
    }


# Process-wide earnings calendar cache. Built once on first call within a
# ~2-hour window — subsequent get_earnings_date calls hit memory, not EODHD.
# Eliminates the per-ticker earnings_calendar call (was 300 calls/scan).
_EARNINGS_CAL_CACHE: dict = {"ts": 0, "by_ticker": None}

def _load_earnings_calendar_global(ttl_seconds: int = 7200) -> dict:
    """Fetch the full 120-day earnings calendar in ONE EODHD call, index by ticker."""
    import time
    if (time.time() - _EARNINGS_CAL_CACHE["ts"]) < ttl_seconds and _EARNINGS_CAL_CACHE["by_ticker"] is not None:
        return _EARNINGS_CAL_CACHE["by_ticker"]
    try:
        import eodhd_client as _eod
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        ec = _eod.earnings_calendar(
            from_date=today.isoformat(),
            to_date=(today + _td(days=120)).isoformat(),
        )
        rows = ec.get("earnings") if isinstance(ec, dict) else []
        idx: dict[str, dict] = {}
        for r in rows or []:
            code = (r.get("code") or "").upper().split(".")[0]
            if not code:
                continue
            ed_str = r.get("report_date") or r.get("date")
            if not ed_str:
                continue
            try:
                ed_ts = pd.to_datetime(ed_str, utc=True)
                days = (ed_ts - pd.Timestamp.now(tz="UTC")).days
                # Keep the earliest upcoming entry per ticker
                if code in idx and idx[code].get("days_to_earnings", 999) < days:
                    continue
                idx[code] = {
                    "earnings_date": str(ed_ts.date()),
                    "days_to_earnings": max(0, days),
                    "earnings_risk": 0 <= days <= 5,
                }
            except Exception:
                pass
        _EARNINGS_CAL_CACHE["ts"] = time.time()
        _EARNINGS_CAL_CACHE["by_ticker"] = idx
        return idx
    except Exception as e:
        log.debug(f"EODHD earnings_calendar (batch) failed: {e}")
        return {}


def get_earnings_date(ticker: str) -> dict:
    """Earnings proximity via EODHD calendar — batched globally.

    Returns POST-EARNINGS data (PEAD-relevant) when the ticker reported within
    the last 7 days, otherwise upcoming-earnings data.

    Post-earnings dict includes: eps_actual, eps_estimate, eps_surprise_pct,
    post_report_gap_pct (computed from data_archive OHLCV).
    """
    _empty = {"earnings_date": None, "days_to_earnings": None, "earnings_risk": False}
    # Check recent-past first (PEAD window) — 7 days back
    past_idx = _load_recent_earnings_surprises_global()
    past = past_idx.get(ticker.upper())
    if past:
        return past
    # Otherwise check upcoming earnings
    idx = _load_earnings_calendar_global()
    return idx.get(ticker.upper(), _empty)


# Cache for post-earnings surprises (PEAD window, 2h TTL)
_RECENT_EARNINGS_CACHE: dict = {"ts": 0, "by_ticker": None}

def _load_recent_earnings_surprises_global(lookback_days: int = 7,
                                            ttl_seconds: int = 7200) -> dict:
    """Fetch last N days of REPORTED earnings with surprise data + post-report gap.

    Pulls EODHD earnings_calendar for [-lookback_days, today], filters to
    entries with actual EPS populated (= already reported), computes the
    post-report gap-up % from data_archive OHLCV.

    Returns dict keyed by ticker → enriched earnings dict:
      {
        earnings_date, days_to_earnings (negative=past),
        days_since_earnings (positive),
        earnings_risk (False — past report),
        eps_actual, eps_estimate, eps_surprise_pct,
        post_report_gap_pct
      }
    """
    import time
    if (time.time() - _RECENT_EARNINGS_CACHE["ts"]) < ttl_seconds and _RECENT_EARNINGS_CACHE["by_ticker"] is not None:
        return _RECENT_EARNINGS_CACHE["by_ticker"]
    try:
        import eodhd_client as _eod
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        ec = _eod.earnings_calendar(
            from_date=(today - _td(days=lookback_days)).isoformat(),
            to_date=today.isoformat(),
        )
        rows = ec.get("earnings") if isinstance(ec, dict) else []
        idx: dict[str, dict] = {}
        for r in rows or []:
            code = (r.get("code") or "").upper().split(".")[0]
            if not code:
                continue
            actual = r.get("actual")
            estimate = r.get("estimate")
            if actual is None or estimate is None:
                continue  # not yet reported
            ed_str = r.get("report_date") or r.get("date")
            if not ed_str:
                continue
            try:
                ed_ts = pd.to_datetime(ed_str, utc=True)
                days_since = (pd.Timestamp.now(tz="UTC") - ed_ts).days
                if days_since < 0 or days_since > lookback_days:
                    continue
                # Surprise pct — EODHD provides as 'percent', fallback to computed
                eps_surprise_pct = r.get("percent")
                if eps_surprise_pct is None and estimate and float(estimate) != 0:
                    eps_surprise_pct = ((float(actual) - float(estimate)) / abs(float(estimate))) * 100
                # Compute post-report gap from data_archive OHLCV
                gap_pct = _compute_post_report_gap_pct(code, ed_ts.date())
                idx[code] = {
                    "earnings_date": str(ed_ts.date()),
                    "days_to_earnings": -days_since,   # negative = post-report (PEAD)
                    "days_since_earnings": days_since,
                    "earnings_risk": False,             # past report — no binary event ahead
                    "eps_actual": float(actual),
                    "eps_estimate": float(estimate),
                    "eps_surprise_pct": float(eps_surprise_pct) if eps_surprise_pct is not None else None,
                    "post_report_gap_pct": gap_pct,
                    "is_post_report": True,
                }
            except Exception:
                pass
        _RECENT_EARNINGS_CACHE["ts"] = time.time()
        _RECENT_EARNINGS_CACHE["by_ticker"] = idx
        log.info(f"EODHD recent earnings: {len(idx)} reported tickers (last {lookback_days}d)")
        return idx
    except Exception as e:
        log.debug(f"EODHD recent earnings fetch failed: {e}")
        return {}


def _compute_post_report_gap_pct(ticker: str, report_date) -> float | None:
    """Compute (next_day_open - report_day_close) / report_day_close * 100
    from data_archive parquet. Returns None if data unavailable."""
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is None or len(df) < 2:
            return None
        # Find report_date in index (or next nearest trading day)
        rd_str = str(report_date)
        # Build a date-indexed list
        idx = df.index
        # Find rows at or after report_date
        post = df[df.index.date >= report_date]
        pre = df[df.index.date < report_date]
        if len(post) < 1 or len(pre) < 1:
            return None
        report_close = float(pre.iloc[-1]["Close"]) if "Close" in pre.columns else float(pre.iloc[-1]["close"])
        next_open = float(post.iloc[0]["Open"]) if "Open" in post.columns else float(post.iloc[0]["open"])
        if report_close <= 0:
            return None
        return round(((next_open - report_close) / report_close) * 100, 3)
    except Exception:
        return None


@_mem_cached(ttl_seconds=1800)
def get_news_sentiment(ticker: str) -> dict:
    """Simple news sentiment from Yahoo Finance RSS."""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return {"score": 0, "headlines": 0, "bias": "neutral"}

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:10]
        titles = [(it.find("title").text or "") for it in items if it.find("title")]

        # FinBERT (ONNX, local, no torch/LLM) — PRIMARY scorer; lexicon fallback below.
        try:
            import finbert_sentiment as _fb
            _fbres = _fb.score_headlines(titles)
        except Exception:
            _fbres = None
        if _fbres and _fbres.get("n"):
            m = _fbres["score"]
            score = 3 if m > 0.25 else 1 if m > 0.05 else -3 if m < -0.25 else -1 if m < -0.05 else 0
            bias = _fbres["label"]
            try:
                import json as _j, datetime as _dt
                from pathlib import Path as _P
                _lp = _P(__file__).resolve().parent / "cache" / "ml" / "sentiment_log.jsonl"
                _lp.parent.mkdir(parents=True, exist_ok=True)
                with open(_lp, "a") as _f:
                    _f.write(_j.dumps({"asof": _dt.datetime.now().isoformat(), "ticker": ticker,
                                       "finbert": m, "n": _fbres["n"]}) + "\n")
            except Exception:
                pass
            return {"score": score, "headlines": len(titles), "bias": bias,
                    "finbert": round(m, 4), "source": "finbert", "n": _fbres["n"]}

        positive = {"beat", "surge", "upgrade", "bullish", "growth", "profit",
                     "wins", "partnership", "deal", "buyback", "record", "strong",
                     "accelerat", "outperform", "raises", "positive"}
        negative = {"miss", "downgrade", "bearish", "cut", "loss", "lawsuit",
                    "recall", "decline", "warns", "layoff", "weak", "fall",
                    "underperform", "negative", "disappoint", "risk"}

        pos_count, neg_count = 0, 0
        for title in titles:
            tl = title.lower()
            pos_count += sum(1 for w in positive if w in tl)
            neg_count += sum(1 for w in negative if w in tl)

        net = pos_count - neg_count
        if net >= 3:
            score, bias = 3, "bullish"
        elif net >= 1:
            score, bias = 1, "slightly bullish"
        elif net <= -3:
            score, bias = -3, "bearish"
        elif net <= -1:
            score, bias = -1, "slightly bearish"
        else:
            score, bias = 0, "neutral"

        return {"score": score, "headlines": len(titles), "bias": bias,
                "positive": pos_count, "negative": neg_count, "source": "lexicon"}
    except Exception:
        return {"score": 0, "headlines": 0, "bias": "neutral"}


_sec_cik_map: dict[str, str] = {}   # ticker → zero-padded CIK (loaded once)
_sec_cik_loaded = False


def _load_sec_cik_map() -> None:
    """Load SEC company_tickers.json into module-level dict (one-time call, cached 24h)."""
    global _sec_cik_map, _sec_cik_loaded
    if _sec_cik_loaded:
        return
    cache_fp = BASE_DIR / "cache" / "_cache_sec_cik_map.json"
    # Use on-disk cache if fresh (< 24 h)
    if cache_fp.exists() and time.time() - cache_fp.stat().st_mtime < 86400:
        try:
            _sec_cik_map = json.loads(cache_fp.read_text())
            _sec_cik_loaded = True
            return
        except Exception:
            pass
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            timeout=15,
            headers={"User-Agent": "SwingTrade research@swingtradeapp.com"},
        )
        if resp.status_code == 200:
            raw = resp.json()  # {0: {cik_str: "...", ticker: "AAPL", ...}, ...}
            _sec_cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                            for v in raw.values()}
            cache_fp.parent.mkdir(exist_ok=True)
            cache_fp.write_text(json.dumps(_sec_cik_map))
            _sec_cik_loaded = True
    except Exception as e:
        log.debug(f"SEC CIK map load failed: {e}")
        _sec_cik_loaded = True  # don't retry on every call


def get_insider_activity(ticker: str) -> dict:
    """Check recent insider trading via SEC EDGAR submissions API (Form 4 filings).
    Uses data.sec.gov/submissions/{CIK}.json — stable JSON, no scraping."""
    cached = _cache_read(f"insider_{ticker}", ttl_seconds=3600)
    if cached:
        return cached

    _empty = {"buys": 0, "sells": 0, "sentiment": "neutral"}

    # ── Primary: SEC submissions API via CIK ────────────────────────────────
    try:
        _load_sec_cik_map()
        cik = _sec_cik_map.get(ticker.upper())
        if not cik:
            raise ValueError(f"No CIK for {ticker}")

        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, timeout=12, headers={
            "User-Agent": "SwingTrade research@swingtradeapp.com"
        })
        if resp.status_code != 200:
            raise ValueError(f"SEC submissions HTTP {resp.status_code}")

        data = resp.json()
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accnums = filings.get("accessionNumber", [])

        cutoff = datetime.now() - timedelta(days=90)
        buys = sells = 0
        for form, date_str, accn in zip(forms, dates, accnums):
            if form not in ("4", "4/A"):
                continue
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                continue
            if dt < cutoff:
                continue

            # Fetch the actual form XML to determine buy vs sell
            accn_clean = accn.replace("-", "")
            xml_url = (f"https://www.sec.gov/Archives/edgar/data/"
                       f"{int(cik)}/{accn_clean}/{accn}.txt")
            try:
                r2 = requests.get(xml_url, timeout=8, headers={
                    "User-Agent": "SwingTrade research@swingtradeapp.com"
                })
                txt = r2.text.lower()
                # transactionCode: P = purchase, S = sale
                if "transactioncode>p<" in txt or ">p</transactioncode>" in txt:
                    buys += 1
                elif "transactioncode>s<" in txt or ">s</transactioncode>" in txt:
                    sells += 1
            except Exception:
                # If XML fetch fails, use filing count heuristic (all Form 4 = activity)
                buys += 1

        # Stop after checking first 10 recent Form 4s to keep runtime short
        if buys + sells == 0 and len([f for f in forms if f in ("4", "4/A")]) > 0:
            # Couldn't determine direction — use count as proxy for activity
            count_4 = sum(1 for f, d in zip(forms, dates)
                          if f in ("4", "4/A")
                          and datetime.strptime(d[:10], "%Y-%m-%d") > cutoff)
            if count_4 >= 3:
                buys = count_4  # treat unknown as buy (insiders file more on open-market buys)

        # Compute days_since_last from most recent Form 4 filing date
        form4_dates = []
        for form, date_str in zip(forms, dates):
            if form in ("4", "4/A"):
                try:
                    form4_dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
                except Exception:
                    pass
        days_since_last = (datetime.now() - max(form4_dates)).days if form4_dates else 999

        sentiment = ("bullish" if buys > sells + 1
                     else "bearish" if sells > buys + 1
                     else "neutral")
        result = {
            "buys": buys,
            "sells": sells,
            "sentiment": sentiment,
            "days_since_last": days_since_last,
            # Enhanced fields for hierarchy-weighted scoring
            "ceo_buy": False,   # will be enriched by OpenInsider fallback if needed
            "cfo_buy": False,
            "total_buy_value": 0,
            "max_single_buy": 0,
        }
        _cache_write(f"insider_{ticker}", result)
        return result

    except Exception as e:
        log.debug(f"SEC insider {ticker}: {e}")

    # ── Fallback: OpenInsider JSON endpoint with role + value extraction ────────
    try:
        url2 = (f"https://openinsider.com/screener?s={ticker}&o=&pl=&ph=&st=0&fd=90"
                f"&fdr=&td=0&tdr=&fdlyl=&fdlyh=&dtefrom=&dteto=&xp=1&xs=1&vession=3")
        resp2 = requests.get(url2, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        text = resp2.text

        purchases = re.findall(r'Purchase', text)
        sales_list = re.findall(r'(?<![A-Za-z])Sale(?! Disc)', text)
        b = len(purchases)
        s = len(sales_list)

        # CEO/CFO role detection from title column
        ceo_buy = bool(re.search(r'(CEO|Chief Executive|President.*CEO)', text, re.I)
                       and purchases)
        cfo_buy = bool(re.search(r'(CFO|Chief Financial)', text, re.I) and purchases)

        # Extract transaction values from "$X,XXX,XXX" patterns near "Purchase"
        val_matches = re.findall(r'Purchase[^<]{0,200}\$([0-9,]+)', text, re.DOTALL)
        buy_values = []
        for vm in val_matches:
            try:
                buy_values.append(int(vm.replace(",", "")))
            except ValueError:
                pass
        total_buy_value = sum(buy_values)
        max_single_buy  = max(buy_values) if buy_values else 0

        sent = "bullish" if b > s + 2 else "bearish" if s > b + 2 else "neutral"
        # Extract most recent date from OpenInsider page
        _oi_dates = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
        _oi_days = 30  # default: assume recent if OpenInsider returned results
        if _oi_dates:
            try:
                _latest = max(datetime.strptime(d, "%Y-%m-%d") for d in _oi_dates if d > "2020")
                _oi_days = (datetime.now() - _latest).days
            except Exception:
                pass
        return {
            "buys": b, "sells": s, "sentiment": sent,
            "ceo_buy": ceo_buy, "cfo_buy": cfo_buy,
            "total_buy_value": total_buy_value,
            "max_single_buy": max_single_buy,
            "days_since_last": _oi_days,
        }
    except Exception:
        return {**_empty, "ceo_buy": False, "cfo_buy": False,
                "total_buy_value": 0, "max_single_buy": 0,
                "days_since_last": 999}


_TV_EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NNM": "NASDAQ",
    "NYQ": "NYSE",   "NYS": "NYSE",   "BTS": "NYSE",
    "PCX": "AMEX",   "ASE": "AMEX",
}


def get_tv_ratings_batch(tickers: list[str], exchange_map: dict | None = None) -> dict[str, dict]:
    """
    Fetch TradingView technical ratings for multiple tickers via the public scanner API.
    Returns dict: ticker → {recommendation, buy, neutral, sell, rec_value, rsi, macd_bullish}

    Premium membership gives real-time quotes (vs 15-min delayed on free plan).
    """
    if not tickers:
        return {}

    results = {}
    em = exchange_map or {}

    def _format(t):
        ex = _TV_EXCHANGE_MAP.get(em.get(t, ""), "NASDAQ")
        return f"{ex}:{t}"

    columns = [
        "name", "Recommend.All", "Recommend.MA", "Recommend.Other",
        "RSI", "MACD.macd", "MACD.signal", "close",
        "EMA20", "EMA50", "EMA200", "volume",
    ]

    batch_size = 200
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        symbols = [_format(t) for t in batch]
        try:
            resp = requests.post(
                "https://scanner.tradingview.com/america/scan",
                json={
                    "symbols": {"tickers": symbols, "query": {"types": []}},
                    "columns": columns,
                },
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            if resp.status_code != 200:
                log.warning(f"TV scanner HTTP {resp.status_code}")
                continue

            for row in resp.json().get("data", []):
                raw_ticker = row.get("s", "").split(":")[-1].upper()
                d = row.get("d", [])
                if not d or d[1] is None:
                    continue
                rec_val = d[1]  # -1 (strong sell) to +1 (strong buy)
                if   rec_val >= 0.5:  rec = "STRONG_BUY"
                elif rec_val >= 0.1:  rec = "BUY"
                elif rec_val >= -0.1: rec = "NEUTRAL"
                elif rec_val >= -0.5: rec = "SELL"
                else:                 rec = "STRONG_SELL"

                results[raw_ticker] = {
                    "recommendation": rec,
                    "rec_value":      round(rec_val, 3),
                    "ma_rec":         d[2],
                    "osc_rec":        d[3],
                    "rsi":            round(d[4], 1) if d[4] else None,
                    "macd":           round(d[5], 4) if d[5] else None,
                    "macd_signal":    round(d[6], 4) if len(d) > 6 and d[6] else None,
                    "ema20":          round(d[8],  2) if len(d) > 8  and d[8]  else None,
                    "ema50":          round(d[9],  2) if len(d) > 9  and d[9]  else None,
                    "ema200":         round(d[10], 2) if len(d) > 10 and d[10] else None,
                }
        except Exception as e:
            log.warning(f"TV scanner batch {i}–{i+batch_size} failed: {e}")

    log.info(f"TV ratings: {len(results)}/{len(tickers)} tickers")
    return results


_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


# ── Finviz analyst scrape — preferred source (replaces Yahoo quoteSummary) ──

_FINVIZ_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"),
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _finviz_analyst_scrape(ticker: str, out: dict) -> bool:
    """Fill analyst fields on `out` from Finviz's quote page (HTML scrape).
    Returns True if at least one analyst field was populated.

    Finviz publishes per-ticker analyst snapshot:
      - 'Recom'        — 1.0..5.0 consensus (1=StrongBuy, 5=StrongSell)
      - 'Target Price' — mean analyst 12-month target
      - Analyst Ratings table: last ~20 firm actions (Upgrade/Downgrade/Reiterated/Initiated)
        with analyst name, rating change, price target change, date.
    """
    import re as _re
    try:
        r = requests.get("https://finviz.com/quote.ashx", params={"t": ticker},
                         headers=_FINVIZ_HEADERS, timeout=10)
        if r.status_code != 200 or "Analyst" not in r.text:
            return False
        html = r.text

        # Snapshot values — Finviz wraps each cell like:
        #   >Recom</a></div></td><td class="snapshot-td2 …"><div …><a …><b>
        #       <span class="color-text is-positive">1.89</span>
        #     </b></a></div>
        # So: find the anchor-label, then grab the next <b>…<span>VALUE</span></b>.
        snap: dict[str, str] = {}
        for label in ("Recom", "Target Price"):
            idx = html.find(f">{label}</a>")
            if idx < 0:
                continue
            # Next ~500 chars should contain <b>…<span …>VALUE</span>…</b>
            window = html[idx:idx + 500]
            m = _re.search(r"<b>\s*(?:<span[^>]*>)?\s*([-\d.,]+)\s*(?:</span>)?\s*</b>", window)
            if m:
                snap[label] = m.group(1)

        # Recom: Finviz uses 1..5. Map to consensus label + normalize.
        rec_raw = snap.get("Recom", "")
        rec_raw = rec_raw.replace(",", ".")
        consensus_set = False
        try:
            recv = float(rec_raw) if rec_raw and rec_raw.replace('.','').replace('-','').isdigit() else None
        except Exception:
            recv = None
        if recv is not None and 1.0 <= recv <= 5.0:
            if   recv <= 1.5: out["consensus"] = "Strong Buy"
            elif recv <= 2.5: out["consensus"] = "Buy"
            elif recv <= 3.5: out["consensus"] = "Hold"
            elif recv <= 4.5: out["consensus"] = "Sell"
            else:             out["consensus"] = "Strong Sell"
            out["recommendation_mean"] = recv
            consensus_set = True

        # Target price
        tgt_raw = snap.get("Target Price", "").replace(",", "")
        try:
            tgt = float(tgt_raw) if tgt_raw else None
        except Exception:
            tgt = None
        if tgt is not None:
            out["target_mean"] = tgt

        # Analyst Ratings table — inside a js-table-ratings block.
        # Each row is <tr class="styled-row ..."> with 5 <td>s:
        #   Date | Action (<span class="fv-label ...">Upgrade</span>) | Analyst |
        #   Rating Change | Price Target Change
        ar_start = html.find("js-table-ratings")
        if ar_start > 0:
            section = html[ar_start:ar_start + 80_000]
            # Stop at the closing </table> of the ratings table
            table_end = section.find("</table>")
            if table_end > 0:
                section = section[:table_end]
            row_pat = _re.compile(
                r'<tr class="styled-row[^"]*">\s*'
                r'<td[^>]*>\s*([^<]*?)\s*</td>\s*'          # Date
                r'<td[^>]*>\s*(?:<span[^>]*>)?\s*([^<]*?)\s*(?:</span>)?\s*</td>\s*'  # Action
                r'<td[^>]*>\s*([^<]*?)\s*</td>\s*'          # Analyst firm
                r'<td[^>]*>\s*([^<]*?)\s*</td>\s*'          # Rating change
                r'<td[^>]*>\s*([^<]*?)\s*</td>',            # Price target change
                _re.IGNORECASE | _re.DOTALL,
            )
            actions = []
            for date_s, action_s, firm_s, rating_s, target_s in row_pat.findall(section)[:25]:
                date_s = date_s.strip()
                if not _re.match(r"^[A-Z][a-z]{2}-\d{1,2}-\d{2,4}$", date_s):
                    continue
                actions.append({
                    "date":   date_s,
                    "action": action_s.strip(),
                    "firm":   firm_s.strip(),
                    "rating": rating_s.strip().replace("&rarr;", "→").replace("&amp;", "&"),
                    "target": target_s.strip().replace("&rarr;", "→"),
                })
            if actions:
                out["_finviz_actions"] = actions
                # Count upgrades/downgrades in last 10 and 60 days
                try:
                    from datetime import datetime as _dt
                    now = _dt.utcnow()
                    up_tokens   = {"upgrade", "initiated", "resumed"}
                    down_tokens = {"downgrade"}
                    ups10 = dens10 = ups60 = dens60 = 0
                    for a in actions:
                        d = None
                        for fmt in ("%b-%d-%y", "%b-%d-%Y"):
                            try:
                                d = _dt.strptime(a["date"], fmt); break
                            except Exception:
                                pass
                        if d is None:
                            continue
                        age = (now - d).days
                        act = a["action"].lower()
                        if act in up_tokens:
                            if age <= 10: ups10  += 1
                            if age <= 60: ups60  += 1
                        elif act in down_tokens:
                            if age <= 10: dens10 += 1
                            if age <= 60: dens60 += 1
                    # Overwrite with Finviz-sourced counts (Finviz has the actions table)
                    out["upgrades_10d"]      = ups10
                    out["downgrades_10d"]    = dens10
                    out["recent_upgrades"]   = ups60
                    out["recent_downgrades"] = dens60
                    out["latest_actions"]    = actions[:6]
                except Exception:
                    pass

        return consensus_set or (tgt is not None)
    except Exception:
        return False


@_mem_cached(ttl_seconds=3600)
@_with_enrichment_cache('analyst')
def get_analyst_data(ticker: str) -> dict:
    """
    Pull full analyst consensus data:
      - Price targets via yfinance analyst_price_targets
      - Recommendation breakdown via Yahoo Finance quoteSummary API
        (recommendationTrend gives the full 30-40 analyst count, not just the monthly snapshot)
      - Recent upgrades / downgrades via yfinance upgrades_downgrades
    """
    empty = {
        "target_mean": None, "target_high": None, "target_low": None,
        "upside_pct": None,
        "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0,
        "total_analysts": 0, "consensus": "—",
        "recent_upgrades": 0, "recent_downgrades": 0,
        "upgrades_10d": 0, "downgrades_10d": 0,
        "latest_actions": [],
        "trend_history": [],   # last 4 months of analyst counts
        "rev_current_q_up7": 0, "rev_current_q_up30": 0,
        "rev_current_q_down7": 0, "rev_current_q_down30": 0,
        "rev_next_q_up7": 0, "rev_next_q_up30": 0,
        "rev_next_q_down7": 0, "rev_next_q_down30": 0,
        "eps_trend": {}, "earnings_estimate": {},
        "revenue_estimate": {}, "growth_estimates": {},
    }
    try:
        t = yf.Ticker(ticker)

        # ── Price targets ──────────────────────────────────────────────────────
        try:
            pt = t.analyst_price_targets
            if pt and isinstance(pt, dict):
                mean   = pt.get("mean")
                high   = pt.get("high")
                low    = pt.get("low")
                curr   = pt.get("current")
                upside = round((mean - curr) / curr * 100, 1) if mean and curr else None
                empty.update({"target_mean": mean, "target_high": high,
                              "target_low": low, "upside_pct": upside})
        except Exception:
            pass

        # ── Analyst consensus + ratings actions ──────────────────────────────
        # Priority: Finviz quote page (HTML scrape) → yfinance library methods.
        # The direct quoteSummary HTTP call was removed 2026-04-24 — it produced
        # ~931 "Invalid Crumb" 401s per scan (crumb cookie not maintained by
        # raw requests). Both current paths use authenticated/sessioned calls.
        # Finviz scrape is the sole source for consensus + target + actions.
        # It populates: consensus, recommendation_mean, target_mean,
        # latest_actions, upgrades_10d, downgrades_10d, recent_upgrades/downgrades.
        # The yfinance library fallbacks (t.recommendations_summary,
        # t.upgrades_downgrades) were removed 2026-04-24 — they were each
        # driving ~900 HTTP 401 "Invalid Crumb" errors per scan via the
        # library's internal retry flow. Finviz covers the same data.
        fv_ok = _finviz_analyst_scrape(ticker, empty)

        # ── EPS Revisions (7d/30d up/down counts) ─────────────────────────
        try:
            eps_rev = t.get_eps_revisions()
            if eps_rev is not None and not eps_rev.empty:
                for period_key in ['0q', '+1q']:
                    if period_key in eps_rev.index:
                        row = eps_rev.loc[period_key]
                        prefix = 'current_q' if period_key == '0q' else 'next_q'
                        empty[f'rev_{prefix}_up7'] = int(row.get('upLast7days', 0) or 0)
                        empty[f'rev_{prefix}_up30'] = int(row.get('upLast30days', 0) or 0)
                        empty[f'rev_{prefix}_down7'] = int(row.get('downLast7days', 0) or 0)
                        empty[f'rev_{prefix}_down30'] = int(row.get('downLast30days', 0) or 0)
        except Exception:
            pass

        # ── EPS Trend (consensus at 7/30/60/90 days ago) ──────────────────
        try:
            eps_trend = t.get_eps_trend()
            if eps_trend is not None and not eps_trend.empty:
                trend_dict = {}
                for period_key in ['0q', '+1q']:
                    if period_key in eps_trend.index:
                        row = eps_trend.loc[period_key]
                        prefix = 'current_q' if period_key == '0q' else 'next_q'
                        trend_dict[f'{prefix}_current'] = float(row.get('current', 0) or 0)
                        trend_dict[f'{prefix}_7d'] = float(row.get('7daysAgo', 0) or 0)
                        trend_dict[f'{prefix}_30d'] = float(row.get('30daysAgo', 0) or 0)
                        trend_dict[f'{prefix}_60d'] = float(row.get('60daysAgo', 0) or 0)
                        trend_dict[f'{prefix}_90d'] = float(row.get('90daysAgo', 0) or 0)
                empty['eps_trend'] = trend_dict
        except Exception:
            pass

        # ── Earnings Estimate (forward EPS consensus) ─────────────────────
        try:
            ee = t.get_earnings_estimate()
            if ee is not None and not ee.empty:
                est = {}
                for period_key in ['0q', '+1q', '0y', '+1y']:
                    if period_key in ee.index:
                        row = ee.loc[period_key]
                        est[period_key] = {
                            'avg': float(row.get('avg', 0) or 0),
                            'low': float(row.get('low', 0) or 0),
                            'high': float(row.get('high', 0) or 0),
                            'num_analysts': int(row.get('numberOfAnalysts', 0) or 0),
                            'year_ago': float(row.get('yearAgoEps', 0) or 0),
                            'growth': float(row.get('growth', 0) or 0),
                        }
                empty['earnings_estimate'] = est
        except Exception:
            pass

        # ── Revenue Estimate ──────────────────────────────────────────────
        try:
            re_est = t.get_revenue_estimate()
            if re_est is not None and not re_est.empty:
                rev = {}
                for period_key in ['0q', '+1q', '0y', '+1y']:
                    if period_key in re_est.index:
                        row = re_est.loc[period_key]
                        rev[period_key] = {
                            'avg': float(row.get('avg', 0) or 0),
                            'low': float(row.get('low', 0) or 0),
                            'high': float(row.get('high', 0) or 0),
                            'num_analysts': int(row.get('numberOfAnalysts', 0) or 0),
                            'year_ago': float(row.get('yearAgoRevenue', 0) or 0),
                            'growth': float(row.get('growth', 0) or 0),
                        }
                empty['revenue_estimate'] = rev
        except Exception:
            pass

        # ── Growth Estimates vs industry/sector ───────────────────────────
        try:
            ge = t.get_growth_estimates()
            if ge is not None and not ge.empty:
                growth = {}
                for col in ge.columns:
                    col_data = {}
                    for idx in ge.index:
                        val = ge.loc[idx, col]
                        if val is not None and str(val) != 'nan':
                            col_data[str(idx)] = float(val) if isinstance(val, (int, float)) else str(val)
                    growth[str(col)] = col_data
                empty['growth_estimates'] = growth
        except Exception:
            pass

        return empty
    except Exception:
        return empty


@_mem_cached(ttl_seconds=1800)
@_with_enrichment_cache('stocktwits')
def get_stocktwits_data(ticker: str) -> dict:
    """
    Pull social sentiment from StockTwits public API (no auth required).
    Returns bullish/bearish ratio, message volume, recent posts.
    """
    empty = {
        "bullish": 0, "bearish": 0, "neutral": 0,
        "bull_pct": 50, "message_volume": 0,
        "watchlist_count": 0, "trending": False,
        "messages": [], "error": None,
    }
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 404:
            empty["error"] = "symbol not found on StockTwits"
            return empty
        resp.raise_for_status()
        data = resp.json()

        messages = data.get("messages", [])
        bull = 0; bear = 0; neutral = 0
        recent = []
        for m in messages:
            sent_obj = (m.get("entities") or {}).get("sentiment") or {}
            sent = sent_obj.get("basic", "")
            if sent == "Bullish":   bull += 1
            elif sent == "Bearish": bear += 1
            else:                   neutral += 1
            if len(recent) < 8:
                recent.append({
                    "body":      (m.get("body") or "")[:180],
                    "user":      (m.get("user") or {}).get("username", "anon"),
                    "sentiment": sent,
                    "time":      (m.get("created_at") or "")[:16].replace("T", " "),
                })

        total_sentiment = bull + bear
        sym = data.get("symbol") or {}
        wcount = sym.get("watchlist_count", 0) or 0

        return {
            "bullish":        bull,
            "bearish":        bear,
            "neutral":        neutral,
            "bull_pct":       round(bull / total_sentiment * 100) if total_sentiment else 50,
            "message_volume": len(messages),
            "watchlist_count": wcount,
            "trending":       wcount > 50_000,
            "messages":       recent,
            "error":          None,
        }
    except Exception as e:
        empty["error"] = str(e)
        return empty


# ── VIX / Market Fear ────────────────────────────────────────────────────────

def get_vix_data() -> dict:
    """
    Fetch VIX + VIX3M (audit gap #3, 2026-05-11) to capture vol dynamics
    beyond point-in-time level. Returns:
      vix_current, vix_ma20, peak_20d, trend (label)
      slope_5d, slope_20d         — numeric % change (vol regime velocity)
      vix3m, term_structure_ratio — VIX / VIX3M (>1.05 = backwardation = stress)
      term_structure_state        — "contango" / "flat" / "backwardation"
      vol_state                   — composite: complacent/calm/normal/rising/spike/panic
      regime, spike_recovery
    """
    empty = {"vix_current": None, "vix_ma20": None, "trend": "stable",
             "regime": "normal", "spike_recovery": False, "error": None,
             "slope_5d": None, "slope_20d": None, "vix3m": None,
             "term_structure_ratio": None, "term_structure_state": "unknown",
             "vol_state": "unknown"}
    try:
        # VIX via EODHD (VIX.INDX)
        _vix_df = None
        try:
            import eodhd_client as _eod
            from datetime import date as _d, timedelta as _td
            from_date = (_d.today() - _td(days=120)).isoformat()
            rows = _eod.eod("VIX", from_date=from_date)
            if rows:
                _vix_df = pd.DataFrame(rows)
                _vix_df["date"] = pd.to_datetime(_vix_df["date"])
                _vix_df = _vix_df.set_index("date").sort_index()
                _vix_df = _vix_df.rename(columns={"adjusted_close": "Close"})
        except Exception as e:
            log.debug(f"EODHD VIX fetch failed: {e}")
        if _vix_df is None or len(_vix_df) < 10:
            empty["error"] = "No VIX data"
            return empty
        close = _vix_df["Close"]
        current = float(close.iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else current
        peak_20d = float(close.rolling(20).max().iloc[-1]) if len(close) >= 20 else current

        # Trend: compare last 5 days (legacy label)
        trend_val = float(close.iloc[-1]) - float(close.iloc[-5]) if len(close) >= 5 else 0
        trend = "rising" if trend_val > 1.5 else "falling" if trend_val < -1.5 else "stable"

        # NEW (gap #3): numeric slopes — vol regime velocity. A 30% jump
        # in VIX over 5 days at VIX=18 is a different signal than VIX=18
        # holding steady. Captures the FIRST DERIVATIVE of vol.
        slope_5d  = (current / float(close.iloc[-5])  - 1) * 100 if len(close) >= 5  else None
        slope_20d = (current / float(close.iloc[-20]) - 1) * 100 if len(close) >= 20 else None

        # Spike recovery: VIX was elevated but is now declining sharply
        spike_recovery = (peak_20d > 30 and current < peak_20d * 0.80 and trend == "falling")

        if current > 30:
            regime = "fear"
        elif current > 20:
            regime = "elevated"
        elif current < 15:
            regime = "complacency"
        else:
            regime = "normal"

        # NEW (gap #3): VIX3M for term structure. EODHD uses .INDX suffix for
        # CBOE indices. Tries VIX3M.INDX first, VXV.INDX legacy fallback.
        # Missing data → ratio=None, ts_state="unknown" (don't fabricate).
        vix3m_cur = None
        for _t in ("VIX3M.INDX", "VXV.INDX"):
            try:
                _r = _eod.eod(_t, from_date=(_d.today() - _td(days=30)).isoformat())
                if _r:
                    _df = pd.DataFrame(_r)
                    _df["date"] = pd.to_datetime(_df["date"])
                    _df = _df.set_index("date").sort_index()
                    _c = (_df["adjusted_close"] if "adjusted_close" in _df.columns else _df["close"]).dropna()
                    if len(_c) >= 1:
                        vix3m_cur = float(_c.iloc[-1])
                        break
            except Exception as _ve:
                log.debug(f"VIX3M fetch {_t}: {_ve}")

        if vix3m_cur and vix3m_cur > 0:
            ts_ratio = current / vix3m_cur
            if ts_ratio > 1.05:
                ts_state = "backwardation"   # short-vol > long-vol → stress imminent
            elif ts_ratio < 0.95:
                ts_state = "contango"        # normal — long-vol priced higher
            else:
                ts_state = "flat"
        else:
            ts_ratio = None
            ts_state = "unknown"

        # NEW (gap #3): composite vol_state — combines level + slope + term
        # Reference: CBOE volatility research — VIX backwardation precedes
        # 80% of 3%+ SPX selloffs by 0-2 weeks. Slope >25%/5d on rising VIX
        # is itself a leading risk-off signal regardless of absolute level.
        if current > 35:
            vol_state = "panic"
        elif ts_state == "backwardation" and current > 18:
            vol_state = "spike_imminent"  # strong risk-off signal
        elif (slope_5d is not None and slope_5d > 25) and current > 18:
            vol_state = "rising_fast"     # vol regime shifting up
        elif current > 25:
            vol_state = "elevated"
        elif (slope_5d is not None and slope_5d > 10) and current > 16:
            vol_state = "rising"
        elif current < 14 and ts_state == "contango":
            vol_state = "complacent"      # late-cycle complacency
        else:
            vol_state = "calm"

        # Batch 5c — additional CBOE indices for the Eikon vol surface panels.
        # VIX9D · short-term vol (9-day expectation). VIX6M · 6-month vol.
        # SKEW · CBOE tail-risk index (~100 normal, 130+ = high crash hedge demand).
        # VVIX · vol of VIX (>100 = elevated vol uncertainty).
        # Missing data → null (don't fabricate).
        extra_idx = {"vix9d": None, "vix6m": None, "skew": None, "vvix": None}
        for fname, tickers in {
            "vix9d": ("VIX9D.INDX",),
            "vix6m": ("VIX6M.INDX",),
            "skew":  ("SKEW.INDX",  "CBOE_SKEW.INDX"),
            "vvix":  ("VVIX.INDX",),
        }.items():
            for _t in tickers:
                try:
                    _r = _eod.eod(_t, from_date=(_d.today() - _td(days=30)).isoformat())
                    if _r:
                        _df = pd.DataFrame(_r)
                        _df["date"] = pd.to_datetime(_df["date"])
                        _df = _df.set_index("date").sort_index()
                        _c = (_df["adjusted_close"] if "adjusted_close" in _df.columns else _df["close"]).dropna()
                        if len(_c) >= 1:
                            extra_idx[fname] = round(float(_c.iloc[-1]), 2)
                            break
                except Exception as _idx_e:
                    log.debug(f"{_t} fetch failed: {_idx_e}")

        return {
            "vix_current":          round(current, 1),
            "vix_ma20":             round(ma20, 1),
            "peak_20d":             round(peak_20d, 1),
            "trend":                trend,
            "slope_5d":             round(slope_5d, 1)  if slope_5d  is not None else None,
            "slope_20d":            round(slope_20d, 1) if slope_20d is not None else None,
            "vix3m":                round(vix3m_cur, 2) if vix3m_cur is not None else None,
            "term_structure_ratio": round(ts_ratio, 3) if ts_ratio  is not None else None,
            "term_structure_state": ts_state,
            "vol_state":            vol_state,
            "regime":               regime,
            "spike_recovery":       spike_recovery,
            # Batch 5c — extended vol family
            "vix9d":                extra_idx["vix9d"],
            "vix6m":                extra_idx["vix6m"],
            "skew":                 extra_idx["skew"],
            "vvix":                 extra_idx["vvix"],
            "error":                None,
        }
    except Exception as e:
        empty["error"] = str(e)
        return empty


# ── Sector ETF Rotation ───────────────────────────────────────────────────────

_SECTOR_ETFS = {
    "XLK":  "Technology",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLE":  "Energy",
    "XLI":  "Industrials",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
    "XLC":  "Communication Svcs",
    "XLP":  "Consumer Staples",
    "XLY":  "Consumer Disc.",
}

# US market-wide indices tracked alongside sector ETFs
_US_INDICES = {
    "QQQ": "Nasdaq 100",
    "DIA": "Dow Jones",
    "IWM": "Russell 2000",
    "MDY": "S&P MidCap",
    "TLT": "Long Treasury",
    "HYG": "High Yield",
    "GLD": "Gold",
    "UUP": "US Dollar",
}

_TICKER_TO_SECTOR = {
    # Technology
    "NVDA": "XLK", "MSFT": "XLK", "AAPL": "XLK", "AMD": "XLK", "INTC": "XLK",
    "AVGO": "XLK", "QCOM": "XLK", "MU": "XLK", "AMAT": "XLK", "KLAC": "XLK",
    "CRWD": "XLK", "PANW": "XLK", "ZS": "XLK", "NET": "XLK",
    # Healthcare
    "LLY": "XLV", "NVO": "XLV", "ABBV": "XLV", "BMY": "XLV", "MRK": "XLV",
    "AMGN": "XLV", "PFE": "XLV", "JNJ": "XLV", "MDT": "XLV", "UNH": "XLV",
    # Financials
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
    "BLK": "XLF", "V": "XLF", "MA": "XLF", "AXP": "XLF",
    # Communication Services
    "META": "XLC", "GOOGL": "XLC", "GOOG": "XLC", "NFLX": "XLC", "DIS": "XLC",
    "CMCSA": "XLC", "T": "XLC", "VZ": "XLC", "SNAP": "XLC", "PINS": "XLC",
    # Consumer Discretionary
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "DECK": "XLY", "ONON": "XLY", "CMG": "XLY",
    # Energy
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "EOG": "XLE", "SLB": "XLE",
    # Industrials
    "AXON": "XLI", "RTX": "XLI", "LMT": "XLI", "NOC": "XLI", "GD": "XLI",
    "CAT": "XLI", "DE": "XLI", "UNP": "XLI",
    # Materials
    "NEM": "XLB", "FCX": "XLB", "NUE": "XLB",
    # Real Estate
    "AMT": "XLRE", "PLD": "XLRE", "EQIX": "XLRE",
}


def get_sector_etf_data(lookback_days: int = 63) -> dict:
    """
    Fetch performance of all 11 sector ETFs vs SPY over `lookback_days`.
    Results are cached to disk for 1 hour to avoid redundant downloads.
    Returns dict: etf → {sector, perf_pct, vs_spy_pct, outperforming, rank}
    """
    _CACHE_KEY = f"sector_etf_{lookback_days}"
    cached = _cache_read(_CACHE_KEY, ttl_seconds=3600)
    if cached:
        log.debug("Sector ETF data: cache hit")
        return cached

    all_symbols = list(_SECTOR_ETFS.keys()) + list(_US_INDICES.keys()) + ["SPY", "SMH", "USO", "COPX"]
    # All sector ETFs / indices via EODHD
    md = fetch_market_data(all_symbols, period="1y")
    closes = pd.DataFrame({sym: df["Close"] for sym, df in md.items() if df is not None and "Close" in df.columns})
    raw_empty = closes.empty or len(closes.columns) < 8

    if raw_empty:
        return {}

    n = min(lookback_days, len(closes) - 1)

    spy_perf = None
    results  = {}
    # ── Sector ETFs ────────────────────────────────────────────────
    for etf in list(_SECTOR_ETFS.keys()) + ["SPY"]:
        try:
            if etf not in closes.columns:
                continue
            col = closes[etf].dropna()
            if len(col) < n + 1:
                continue
            perf = (float(col.iloc[-1]) / float(col.iloc[-(n+1)]) - 1) * 100
            if etf == "SPY":
                spy_perf = perf
            else:
                results[etf] = {
                    "sector":   _SECTOR_ETFS.get(etf, etf),
                    "perf_pct": round(perf, 2),
                    "price":    round(float(col.iloc[-1]), 2),
                }
        except Exception:
            pass

    if spy_perf is not None:
        perfs = []
        for etf, d in results.items():
            d["vs_spy_pct"]    = round(d["perf_pct"] - spy_perf, 2)
            d["outperforming"] = d["vs_spy_pct"] > 0
            perfs.append((etf, d["vs_spy_pct"]))
        perfs.sort(key=lambda x: x[1], reverse=True)
        for rank, (etf, _) in enumerate(perfs, 1):
            results[etf]["rank"] = rank

    results["SPY"] = {"sector": "S&P 500", "perf_pct": round(spy_perf or 0, 2),
                      "vs_spy_pct": 0.0, "outperforming": False, "rank": 0,
                      "price": round(float(closes["SPY"].dropna().iloc[-1]), 2) if "SPY" in closes.columns else 0}

    # ── US market indices ──────────────────────────────────────────
    indices: dict = {}
    for sym, label in _US_INDICES.items():
        try:
            if sym not in closes.columns:
                continue
            col = closes[sym].dropna()
            if len(col) < n + 1:
                continue
            perf  = (float(col.iloc[-1]) / float(col.iloc[-(n+1)]) - 1) * 100
            price = round(float(col.iloc[-1]), 2)
            vs    = round(perf - (spy_perf or 0), 2)
            indices[sym] = {
                "label":         label,
                "perf_pct":      round(perf, 2),
                "vs_spy_pct":    vs,
                "outperforming": vs > 0,
                "price":         price,
            }
        except Exception:
            pass
    results["_indices"] = indices

    # ── EMA / SMA regime for key indices ──────────────────────────
    regime_syms = ["SPY", "QQQ", "DIA", "IWM", "SMH"]
    idx_regime = {}
    for sym in regime_syms:
        try:
            if sym not in closes.columns:
                continue
            col = closes[sym].dropna()
            if len(col) < 200:
                continue
            price = float(col.iloc[-1])
            ema21  = float(col.ewm(span=21, adjust=False).mean().iloc[-1])
            ema50  = float(col.ewm(span=50, adjust=False).mean().iloc[-1])
            sma200 = float(col.rolling(200).mean().iloc[-1])
            a21 = price > ema21
            a50 = price > ema50
            a200 = price > sma200
            bulls = sum([a21, a50, a200])
            trend = "BULL" if bulls == 3 else "BEAR" if bulls == 0 else "MIXED"
            ret_1m = round((price / float(col.iloc[-21]) - 1) * 100, 1) if len(col) >= 21 else 0
            ret_5d = round((price / float(col.iloc[-5]) - 1) * 100, 1) if len(col) >= 5 else 0
            idx_regime[sym] = {
                "price": round(price, 2), "ema21": round(ema21, 2),
                "ema50": round(ema50, 2), "sma200": round(sma200, 2),
                "above_ema21": a21, "above_ema50": a50, "above_sma200": a200,
                "trend": trend, "ret_1m": ret_1m, "ret_5d": ret_5d,
            }
        except Exception:
            pass
    results["_idx_regime"] = idx_regime

    # ── Extended macro: USO, BTC-USD, COPX, SMH ─────────────────
    ext_macro = {}
    for sym, key in [("USO", "uso"), ("COPX", "copx"), ("SMH", "smh")]:
        try:
            if sym not in closes.columns:
                continue
            col = closes[sym].dropna()
            if len(col) < 20:
                continue
            cur  = float(col.iloc[-1])
            ma20 = float(col.rolling(20).mean().iloc[-1])
            chg5 = round((cur / float(col.iloc[-5]) - 1) * 100, 1) if len(col) >= 5 else 0
            chg20 = round((cur / float(col.iloc[-20]) - 1) * 100, 1) if len(col) >= 20 else 0
            trend = "rising" if chg5 > 0.5 else "falling" if chg5 < -0.5 else "flat"
            ext_macro[key] = {"price": round(cur, 2), "ma20": round(ma20, 2),
                              "chg5d": chg5, "chg20d": chg20, "trend": trend}
        except Exception:
            pass
    results["_ext_macro"] = ext_macro

    # ── Intermarket correlations (60-day) ────────────────────────
    intermarket = {}
    corr_pairs = [("SPY", "TLT", "Stock-Bond"), ("SPY", "UUP", "Equity-Dollar"),
                  ("SPY", "GLD", "Equity-Gold"), ("HYG", "SPY", "Credit-Equity")]
    for t1, t2, label in corr_pairs:
        try:
            if t1 not in closes.columns or t2 not in closes.columns:
                continue
            r1 = closes[t1].dropna().pct_change().tail(60).dropna()
            r2 = closes[t2].dropna().pct_change().tail(60).dropna()
            combined = pd.concat([r1, r2], axis=1).dropna()
            if len(combined) < 30:
                continue
            corr_val = float(combined.iloc[:, 0].corr(combined.iloc[:, 1]))
            intermarket[label] = {"t1": t1, "t2": t2, "corr": round(corr_val, 2)}
        except Exception:
            pass
    results["_intermarket"] = intermarket

    _cache_write(_CACHE_KEY, results)
    return results


# ── Options IV Rank ───────────────────────────────────────────────────────────

@_mem_cached(ttl_seconds=1800)
def get_options_iv_data(ticker: str) -> dict:
    """
    Options IV / chain summary via Schwab Trader API.

    Schwab is the authorized options data provider. Refresh tokens roll every
    7 days; on expiry, callers see HTTP 400 'unsupported_token_type' and
    options panels show NO_DATA — recovery is `python3 schwab_auth.py oauth`
    in a browser-capable session. EODHD options endpoint is not included in
    the user's All-In-One plan, so Schwab is the only working source.

    Returns: {iv_rank, iv_pct, current_iv, put_call_ratio, total_call_oi,
              total_put_oi, total_call_vol, total_put_vol, max_pain,
              uoa_calls, uoa_puts, source, error}

    Skips the call when Schwab credentials are not configured (returns clean
    nulls). No provider gate needed — analysis.py:_options_intelligence and
    other paths already detect Schwab via SCHWAB_APP_KEY presence the same way.
    """
    out = {"iv_rank": None, "iv_pct": None, "current_iv": None,
           "put_call_ratio": None, "total_call_oi": 0, "total_put_oi": 0,
           "total_call_vol": 0, "total_put_vol": 0, "max_pain": None,
           "uoa_calls": 0, "uoa_puts": 0,
           # 2026-05-26 · Quant options block (commit 1 OPTIONS-QUANT-DATA)
           "atm_strike":      None,
           "atm_dte":         None,
           "atm_delta":       None,   # call-side ATM ~30D
           "atm_gamma":       None,
           "atm_theta":       None,
           "atm_vega":        None,
           "atm_iv":          None,   # ATM IV expressed as a fraction (0.32 = 32%)
           "atm_mark":        None,   # ATM call mark (real chain price)
           "atm_bid_ask_pct": None,   # ATM call bid/ask spread as % of mid — liquidity proxy
           # Real second-leg data for spread tickets (no estimation needed)
           "iv_25d_call_strike": None,  "iv_25d_call_mark":  None,
           "iv_25d_put_strike":  None,  "iv_25d_put_mark":   None,
           # Full chain grid for Eikon Chain Montage / Vol Surface — 5 expirations × 7 strikes
           # each, raw bid/ask/mark/IV/Δ/vol/OI per side. ~1.7KB per ticker.
           "chain_grid":      None,
           # Batch 1 quick wins
           "implied_move_pct": None,   # ATM straddle (call_mark + put_mark) / spot × 100
           "vol_of_vol":       None,   # σ of IV across strikes at ATM expiration
           "theta_pct_per_day": None,  # |theta| / atm_mark — premium decay rate
           # Batch 5 — Tier A/B/C extensions
           "atm_dte_trading":  None,   # ATM DTE in trading days (× 5/7 calendar→trading approx)
           "oi_change_total":  None,   # total OI Δ vs prior snapshot (positive = positioning built)
           "oi_change_call":   None,
           "oi_change_put":    None,
           "oi_weighted_strike": None, # Σ(strike × oi) / Σoi — gravity (alt to max_pain)
           "pc_oi_ratio_atm":  None,   # put_OI / call_OI within ±5% of spot
           "net_delta_by_exp": None,   # {dte: Σ(call_oi × call_delta + put_oi × put_delta)}
           "theta_schedule":   None,   # {1d: theta_for_nearest_dte, 7d: ..., 14d: ...}
           "strike_z_outliers": None,  # list of strikes with vol Z-score > 2.5 vs neighbors
           "max_oi_strike":    None,   # strike with highest combined OI
           "hv90":             None,   # 90-day realized vol (set by refresh_options_flow)
           "iv_percentile_1y": None,   # from iv_history.jsonl — set in refresh
           "iv_of_iv":         None,   # σ(IV) over last 30d — set in refresh
           "beta_to_spy":      None,   # 60d log-return regression beta — set in refresh
           "beta_adjusted_delta": None,  # atm_delta × beta_to_spy
           "pin_risk":         None,   # 1 if strikes within 1% of spot at <3 DTE, else 0
           "premium_call_$":  None,   # Σ call vol × mark × 100 (correct $ notional)
           "premium_put_$":   None,
           "premium_total_$": None,
           "cohort_0dte_pct":  None,  # % of total option vol expiring same day
           "cohort_weekly_pct":  None,  # % expiring ≤ 8d
           "cohort_monthly_pct": None,  # % expiring 9-45d
           "cohort_leap_pct":    None,  # % expiring > 45d
           "front_iv":         None,   # ATM IV of nearest expiration
           "back_iv":          None,   # ATM IV of farthest (within fetched expirations)
           "term_ratio":       None,   # front_iv / back_iv (<1 = contango / normal; >1 = stressed)
           "skew_25d":         None,   # 25Δ-call IV − 25Δ-put IV (fraction); >0 = call-skew (upside chase), <0 = put-skew (crash hedge)
           "iv_25d_call":      None,   # IV of the contract closest to delta = +0.25
           "iv_25d_put":       None,   # IV of the contract closest to delta = -0.25
           "uoa_puts":         0,      # number of put strikes with vol > 3× OI (already aggregated, now exposed)
           "source": "unavailable", "error": None}

    # Lazy-load .env so this works whether or not the parent process exported
    # SCHWAB_APP_KEY into os.environ — same pattern as analysis.py uses for
    # options_intelligence. Without this, schwab_auth refresh fails silently
    # and options data never populates per-ticker.
    if not os.environ.get("SCHWAB_APP_KEY"):
        try:
            from pathlib import Path as _Path
            _env_path = _Path(__file__).resolve().parent / ".env"
            if _env_path.exists():
                for _line in _env_path.read_text().splitlines():
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        except Exception:
            pass

    # Bail cleanly if Schwab credentials still missing.
    if not (os.environ.get("SCHWAB_APP_KEY") and os.environ.get("SCHWAB_REFRESH_TOKEN")):
        return out

    cache_key = f"opts_iv_{ticker}_{int(time.time()//7200)}"
    cached = _cache_read(cache_key, 7200)
    if cached is not None:
        return cached

    out["source"] = "schwab"

    try:
        import schwab_client as sc
        # Fetch full chain — strike_count=20 each side gives ~40-strike grid
        ch = sc.get_chains(ticker, contract_type="ALL", strike_count=20,
                           include_underlying=True)
        if not isinstance(ch, dict) or ch.get("status") != "SUCCESS":
            out["error"] = f"chain unavailable: status={ch.get('status') if isinstance(ch, dict) else 'no-data'}"
            _cache_write(cache_key, out)
            return out

        underlying = ch.get("underlying", {}) or {}
        spot = underlying.get("last") or underlying.get("mark")

        # Aggregate stats across nearest 4 expirations
        call_map = ch.get("callExpDateMap", {}) or {}
        put_map  = ch.get("putExpDateMap", {}) or {}

        iv_samples = []   # ATM-bias IV samples for current_iv estimate
        call_oi = call_vol = 0
        put_oi  = put_vol  = 0
        uoa_calls = uoa_puts = 0
        # Strike-level OI for max-pain calc
        strike_pain = {}
        # 2026-05-26 · OPTIONS-QUANT-DATA · per-expiration premium $ + cohort buckets
        cohort_0dte_vol = cohort_weekly_vol = cohort_monthly_vol = cohort_leap_vol = 0
        premium_call_dollars = premium_put_dollars = 0.0
        # Track expirations (DTE → ATM IV) for term-structure ratio
        exp_atm_iv: dict[int, list[float]] = {}
        # ATM call slot for Greeks pick — store the contract closest to the money
        # at the nearest viable expiration ≥ 14d (avoid 0DTE/weekly Greek noise).
        atm_call_best: dict = {}
        # 25Δ skew tracking — find the call closest to |Δ|=0.25 and the put closest
        # to |Δ|=0.25, both at the same viable expiration ≥14d. Skew = call_IV - put_IV.
        skew_25d_call_best: dict = {}
        skew_25d_put_best: dict = {}

        def _aggregate(ex_map, is_put: bool):
            nonlocal call_oi, put_oi, call_vol, put_vol, uoa_calls, uoa_puts
            nonlocal cohort_0dte_vol, cohort_weekly_vol, cohort_monthly_vol, cohort_leap_vol
            nonlocal premium_call_dollars, premium_put_dollars
            # 2026-05-26 · iterate 10 nearest expirations (was 4) so we capture both
            # near-term flow cohorts AND a ≥14d expiration for Greeks extraction.
            # Earlier cap of 4 missed Greek-viable expirations on high-volume names
            # because slots 0-3 are typically 0/1/3/6 DTE (all <14d).
            for exp_key, strikes in list(ex_map.items())[:10]:
                # exp_key format "YYYY-MM-DD:DTE"
                exp_dte = None
                try:
                    exp_dte = int(exp_key.split(":")[-1])
                except Exception:
                    pass
                for strike_str, contracts in strikes.items():
                    try:
                        strike = float(strike_str)
                    except Exception:
                        continue
                    for c in contracts:
                        oi  = int(c.get("openInterest") or 0)
                        vol = int(c.get("totalVolume") or 0)
                        iv  = c.get("volatility")
                        # Schwab encodes "no quote" as volatility = -999.0. IV is a
                        # volatility (always > 0), so null ANY non-positive sentinel here
                        # before it normalizes to -9.99 (= -999/100) and leaks into atm_iv.
                        try:
                            iv = None if iv is None or float(iv) <= 0 else iv
                        except (TypeError, ValueError):
                            iv = None
                        mark = c.get("mark") or c.get("last") or 0
                        try: mark = float(mark)
                        except Exception: mark = 0.0
                        # Premium $ notional — correct math (vol × mark × 100)
                        premium = vol * mark * 100
                        # Expiration cohort bucketing (vol-weighted)
                        if exp_dte is not None and vol > 0:
                            if exp_dte == 0:    cohort_0dte_vol    += vol
                            elif exp_dte <= 8:  cohort_weekly_vol  += vol
                            elif exp_dte <= 45: cohort_monthly_vol += vol
                            else:               cohort_leap_vol    += vol
                        if is_put:
                            put_oi  += oi
                            put_vol += vol
                            premium_put_dollars += premium
                            if oi > 100 and vol > oi * 3:
                                uoa_puts += 1
                            # 25Δ put tracking — put delta is negative; |Δ| ≈ 0.25
                            d = c.get("delta")
                            if d is not None and spot and exp_dte is not None and exp_dte >= 14:
                                try:
                                    d_f = float(d)
                                    if -0.40 <= d_f <= -0.10:  # near 25Δ put band
                                        target_dist = abs(abs(d_f) - 0.25)
                                        dte_pen = max(0, (exp_dte - 30)) / 1000
                                        score = target_dist + dte_pen
                                        prev = skew_25d_put_best.get("_score")
                                        if prev is None or score < prev:
                                            skew_25d_put_best.clear()
                                            skew_25d_put_best.update({
                                                "_score": score, "iv": iv,
                                                "delta":  d_f, "strike": strike,
                                                "dte":    exp_dte,
                                                "mark":   mark,
                                            })
                                except Exception: pass
                        else:
                            call_oi  += oi
                            call_vol += vol
                            premium_call_dollars += premium
                            if oi > 100 and vol > oi * 3:
                                uoa_calls += 1
                            # Track ATM call for Greeks — pick the strike closest
                            # to spot within the nearest expiration ≥ 14d (avoid
                            # 0DTE/weekly Greek noise). Score = |strike-spot|/spot
                            # plus penalty for sub-14d DTE.
                            if spot and exp_dte is not None and exp_dte >= 14:
                                moneyness = abs(strike - spot) / spot
                                if moneyness <= 0.10:  # within ±10%
                                    score = moneyness + max(0, (exp_dte - 30)) / 1000
                                    prev_score = atm_call_best.get("_score")
                                    if prev_score is None or score < prev_score:
                                        atm_call_best.clear()
                                        atm_call_best.update({
                                            "_score":   score,
                                            "strike":   strike,
                                            "dte":      exp_dte,
                                            "delta":    c.get("delta"),
                                            "gamma":    c.get("gamma"),
                                            "theta":    c.get("theta"),
                                            "vega":     c.get("vega"),
                                            "iv":       iv,
                                            "bid":      c.get("bid"),
                                            "ask":      c.get("ask"),
                                            "mark":     mark,
                                        })
                            # 25Δ call tracking — call delta is positive
                            d = c.get("delta")
                            if d is not None and spot and exp_dte is not None and exp_dte >= 14:
                                try:
                                    d_f = float(d)
                                    if 0.10 <= d_f <= 0.40:  # near 25Δ call band
                                        target_dist = abs(d_f - 0.25)
                                        dte_pen = max(0, (exp_dte - 30)) / 1000
                                        score = target_dist + dte_pen
                                        prev = skew_25d_call_best.get("_score")
                                        if prev is None or score < prev:
                                            skew_25d_call_best.clear()
                                            skew_25d_call_best.update({
                                                "_score": score, "iv": iv,
                                                "delta":  d_f, "strike": strike,
                                                "dte":    exp_dte,
                                                "mark":   mark,
                                            })
                                except Exception: pass
                        # Strike-pain weight (calls + puts both contribute)
                        strike_pain[strike] = strike_pain.get(strike, 0) + oi
                        # Sample ATM IV (near-the-money strikes)
                        if iv and spot and 0.95 <= strike / spot <= 1.05:
                            try:
                                iv_samples.append(float(iv))
                                if exp_dte is not None:
                                    exp_atm_iv.setdefault(exp_dte, []).append(float(iv))
                            except Exception: pass

        _aggregate(call_map, is_put=False)
        _aggregate(put_map,  is_put=True)

        out["total_call_oi"]  = call_oi
        out["total_put_oi"]   = put_oi
        out["total_call_vol"] = call_vol
        out["total_put_vol"]  = put_vol
        out["uoa_calls"]      = uoa_calls
        out["uoa_puts"]       = uoa_puts

        # Put/Call ratio (volume-based; OI-based is also reasonable)
        if call_vol > 0:
            out["put_call_ratio"] = round(put_vol / call_vol, 3)

        # Current IV — average of ATM samples
        if iv_samples:
            out["current_iv"] = round(sum(iv_samples) / len(iv_samples), 3)

        # Max pain — strike that minimizes total OI value
        # (simplified: just the strike with the highest combined OI weight)
        if strike_pain:
            out["max_pain"] = max(strike_pain.items(), key=lambda kv: kv[1])[0]

        # IV rank — % of 52w (Finviz fallback returns None; we compute later if HV history exists)
        # For now, use ATR-based proxy (already in the codebase) when current_iv is known
        # Schwab doesn't return historical IV, so iv_rank stays None unless we cache history ourselves
        out["iv_rank"] = None  # placeholder — V-18 will add real-time IV-surface history

        # 2026-05-26 · OPTIONS-QUANT-DATA — surface Greeks + premium $ + cohort + term
        out["premium_call_$"]  = round(premium_call_dollars, 0) if premium_call_dollars else 0
        out["premium_put_$"]   = round(premium_put_dollars, 0)  if premium_put_dollars  else 0
        out["premium_total_$"] = out["premium_call_$"] + out["premium_put_$"]
        cohort_tot = cohort_0dte_vol + cohort_weekly_vol + cohort_monthly_vol + cohort_leap_vol
        if cohort_tot > 0:
            out["cohort_0dte_pct"]    = round(cohort_0dte_vol    / cohort_tot * 100, 1)
            out["cohort_weekly_pct"]  = round(cohort_weekly_vol  / cohort_tot * 100, 1)
            out["cohort_monthly_pct"] = round(cohort_monthly_vol / cohort_tot * 100, 1)
            out["cohort_leap_pct"]    = round(cohort_leap_vol    / cohort_tot * 100, 1)
        # ATM call Greeks (closest strike to spot, ≥14d expiration).
        # Normalize IV: Schwab returns volatility as a percentage (41.755 = 41.755%),
        # so divide by 100 to get the fraction the UI expects (0.32 = 32% IV).
        if atm_call_best:
            atm_call_best.pop("_score", None)
            for k in ("strike", "dte", "delta", "gamma", "theta", "vega", "iv", "mark"):
                v = atm_call_best.get(k)
                if v is None: continue
                try: v = float(v)
                except Exception: continue
                if k == "iv":
                    out["atm_iv"] = round(v / 100, 4)  # → fraction
                elif k == "strike":
                    out["atm_strike"] = round(v, 2)
                elif k == "mark":
                    out["atm_mark"] = round(v, 2)
                else:
                    out[f"atm_{k}"] = round(v, 4)
            # ATM bid/ask spread as % of mid — liquidity proxy
            bid, ask = atm_call_best.get("bid"), atm_call_best.get("ask")
            try:
                bid, ask = float(bid), float(ask)
                mid = (bid + ask) / 2
                if mid > 0:
                    out["atm_bid_ask_pct"] = round((ask - bid) / mid * 100, 2)
            except Exception: pass
        # 25Δ skew · risk-reversal proxy.
        # Skew > 0 = call-skew (calls more bid up than puts → upside chase).
        # Skew < 0 = put-skew (puts paid up → crash hedge / fear).
        # Normalize Schwab percentages → fractions for consistency with atm_iv.
        if skew_25d_call_best and skew_25d_put_best:
            try:
                c_iv = float(skew_25d_call_best.get("iv")) / 100
                p_iv = float(skew_25d_put_best.get("iv"))  / 100
                out["iv_25d_call"] = round(c_iv, 4)
                out["iv_25d_put"]  = round(p_iv, 4)
                out["skew_25d"]    = round(c_iv - p_iv, 4)
                # Real strikes + marks for the spread short leg (no estimation)
                if skew_25d_call_best.get("strike") is not None:
                    out["iv_25d_call_strike"] = round(float(skew_25d_call_best["strike"]), 2)
                if skew_25d_call_best.get("mark") is not None:
                    out["iv_25d_call_mark"]   = round(float(skew_25d_call_best["mark"]), 2)
                if skew_25d_put_best.get("strike") is not None:
                    out["iv_25d_put_strike"]  = round(float(skew_25d_put_best["strike"]), 2)
                if skew_25d_put_best.get("mark") is not None:
                    out["iv_25d_put_mark"]    = round(float(skew_25d_put_best["mark"]), 2)
            except Exception: pass

        # Expose uoa_puts (was tracked but never surfaced)
        out["uoa_puts"] = uoa_puts

        # Batch 1 · derived metrics from chain data we already have:
        #   - implied_move_pct = ATM straddle / spot (market-priced ±%)
        #   - vol_of_vol = stdev(IV across strikes at the ATM expiration)
        #   - theta_pct_per_day = |atm_theta| / atm_mark (rate of premium decay)
        try:
            if atm_call_best.get("mark") is not None and atm_call_best.get("strike") is not None:
                # Need matching put at ATM strike — search the chain
                atm_k = atm_call_best["strike"]
                atm_dte_val = atm_call_best.get("dte")
                put_mark_atm = None
                for exp_key in put_map:
                    try:
                        ex_dte = int(exp_key.split(":")[-1])
                    except Exception:
                        continue
                    if atm_dte_val is not None and abs(ex_dte - atm_dte_val) > 1:
                        continue
                    for k_str, contracts in (put_map.get(exp_key) or {}).items():
                        try:
                            if abs(float(k_str) - atm_k) < 0.01:
                                put_mark_atm = (contracts or [{}])[0].get("mark")
                                break
                        except Exception: pass
                    if put_mark_atm is not None: break
                if put_mark_atm is not None and spot:
                    try:
                        straddle = float(atm_call_best["mark"]) + float(put_mark_atm)
                        out["implied_move_pct"] = round(straddle / spot * 100, 2)
                    except Exception: pass
            # vol_of_vol — stdev of IVs across strikes at the ATM expiration
            if atm_call_best.get("dte") is not None:
                target_dte = atm_call_best["dte"]
                exp_ivs = []
                for exp_key in call_map:
                    try:
                        if int(exp_key.split(":")[-1]) == target_dte:
                            for k_str, contracts in (call_map.get(exp_key) or {}).items():
                                for c in (contracts or []):
                                    iv = c.get("volatility")
                                    if iv is not None:
                                        try: exp_ivs.append(float(iv) / 100)
                                        except Exception: pass
                            break
                    except Exception: pass
                if len(exp_ivs) >= 3:
                    import statistics
                    out["vol_of_vol"] = round(statistics.stdev(exp_ivs), 4)
            # theta_pct_per_day
            if out.get("atm_theta") is not None and out.get("atm_mark"):
                try:
                    out["theta_pct_per_day"] = round(abs(float(out["atm_theta"])) / float(out["atm_mark"]) * 100, 2)
                except Exception: pass
        except Exception: pass

        # 2026-05-26 · EIKON-CHAIN-GRID · build full chain grid for the Eikon
        # preview / Chain Montage panel. 5 nearest expirations × 7 strikes closest
        # to spot. Real chain data per (strike, expiration, side) — no BSM
        # interpolation. ~1.7 KB per ticker.
        if spot:
            grid = []
            for exp_key in list(set(list(call_map.keys()) + list(put_map.keys())))[:5]:
                try:
                    exp_date, dte_str = exp_key.split(":")
                    dte = int(dte_str)
                except Exception:
                    continue
                c_strikes = call_map.get(exp_key, {}) or {}
                p_strikes = put_map.get(exp_key, {}) or {}
                # Collect every unique strike at this expiration
                strike_set = set()
                for k_str in c_strikes:
                    try: strike_set.add(float(k_str))
                    except Exception: pass
                for k_str in p_strikes:
                    try: strike_set.add(float(k_str))
                    except Exception: pass
                if not strike_set: continue
                # Pick 7 strikes closest to spot
                chosen = sorted(sorted(strike_set, key=lambda k: abs(k - spot))[:7])
                rows = []
                for k in chosen:
                    # Find the contract record (key format may vary slightly)
                    c_rec, p_rec = None, None
                    for k_str, contracts in c_strikes.items():
                        try:
                            if abs(float(k_str) - k) < 0.01:
                                c_rec = (contracts or [{}])[0]; break
                        except Exception: pass
                    for k_str, contracts in p_strikes.items():
                        try:
                            if abs(float(k_str) - k) < 0.01:
                                p_rec = (contracts or [{}])[0]; break
                        except Exception: pass
                    def _side(rec):
                        if not rec: return None
                        try: iv_raw = rec.get("volatility")
                        except Exception: iv_raw = None
                        try: iv_frac = round(float(iv_raw) / 100, 4) if iv_raw else None
                        except Exception: iv_frac = None
                        # Last trade time — Schwab returns epoch-ms, convert to ISO
                        lt_raw = rec.get("tradeTimeInLong") or rec.get("tradeDate")
                        last_trade = None
                        if lt_raw:
                            try:
                                from datetime import datetime, timezone
                                last_trade = datetime.fromtimestamp(int(lt_raw)/1000, tz=timezone.utc).isoformat()
                            except Exception: pass
                        return {
                            "bid":   rec.get("bid"),
                            "ask":   rec.get("ask"),
                            "mark":  rec.get("mark"),
                            "iv":    iv_frac,           # fraction
                            "delta": rec.get("delta"),
                            "gamma": rec.get("gamma"),
                            "theta": rec.get("theta"),
                            "vega":  rec.get("vega"),
                            "rho":   rec.get("rho"),                # Tier A #1
                            "theo":  rec.get("theoreticalOptionValue"),  # #2
                            "itm":   bool(rec.get("inTheMoney")),   # #4
                            "settle": rec.get("settlementType"),    # #5 P=PM A=AM
                            "mini":  bool(rec.get("mini")),         # #6
                            "last_trade": last_trade,               # #7
                            "vol":   rec.get("totalVolume") or 0,
                            "oi":    rec.get("openInterest") or 0,
                        }
                    rows.append({
                        "k":    round(k, 2),
                        "call": _side(c_rec),
                        "put":  _side(p_rec),
                    })
                grid.append({"exp": exp_date, "dte": dte, "strikes": rows})
            # Sort by DTE asc
            grid.sort(key=lambda g: g.get("dte", 0))
            out["chain_grid"] = grid[:5]

            # ── Batch 5 derived metrics from chain_grid ──────────────────────────
            try:
                # Trading-days DTE (Mon-Fri × 5/7 of calendar)
                if out.get("atm_dte") is not None:
                    out["atm_dte_trading"] = round(out["atm_dte"] * 5/7, 1)

                # OI-weighted strike (gravity) — better than max_pain for fair-value estimate
                oi_w_num, oi_w_den = 0.0, 0.0
                max_oi_strike, max_oi_val = None, 0
                pc_atm_call_oi, pc_atm_put_oi = 0, 0
                # Aggregate OI per strike across ALL expirations in grid
                strike_oi_call, strike_oi_put = {}, {}
                strike_vol_call = {}
                for exp in grid:
                    for s in exp.get("strikes", []):
                        K = s.get("k"); c = s.get("call") or {}; p = s.get("put") or {}
                        if K is None: continue
                        c_oi = c.get("oi") or 0
                        p_oi = p.get("oi") or 0
                        c_vol = c.get("vol") or 0
                        strike_oi_call[K] = strike_oi_call.get(K, 0) + c_oi
                        strike_oi_put[K]  = strike_oi_put.get(K, 0) + p_oi
                        strike_vol_call[K] = strike_vol_call.get(K, 0) + c_vol
                        total_oi = c_oi + p_oi
                        oi_w_num += K * total_oi
                        oi_w_den += total_oi
                        if total_oi > max_oi_val:
                            max_oi_val = total_oi; max_oi_strike = K
                        if spot and 0.95 <= K/spot <= 1.05:
                            pc_atm_call_oi += c_oi
                            pc_atm_put_oi  += p_oi
                if oi_w_den > 0:
                    out["oi_weighted_strike"] = round(oi_w_num / oi_w_den, 2)
                if max_oi_strike is not None:
                    out["max_oi_strike"] = round(max_oi_strike, 2)
                if pc_atm_call_oi > 0:
                    out["pc_oi_ratio_atm"] = round(pc_atm_put_oi / pc_atm_call_oi, 3)

                # Net Greeks aggregated by expiration: {dte: {delta, gamma, theta, vega}}
                net_by_exp = {}
                theta_schedule = {}
                for exp in grid:
                    dte = exp.get("dte")
                    if dte is None: continue
                    nd = ng = nt = nv = 0.0
                    for s in exp.get("strikes", []):
                        c = s.get("call") or {}; p = s.get("put") or {}
                        for side, sign in [(c, 1), (p, 1)]:  # OI-weighted, both sides positive
                            oi = side.get("oi") or 0
                            if not oi: continue
                            if side.get("delta") is not None: nd += float(side["delta"]) * oi
                            if side.get("gamma") is not None: ng += float(side["gamma"]) * oi
                            if side.get("theta") is not None: nt += float(side["theta"]) * oi
                            if side.get("vega")  is not None: nv += float(side["vega"])  * oi
                    net_by_exp[dte] = {
                        "delta": round(nd, 1), "gamma": round(ng, 3),
                        "theta": round(nt, 1), "vega": round(nv, 1),
                    }
                    # Theta schedule: bucket by DTE
                    if dte <= 1:    theta_schedule["1d"]  = theta_schedule.get("1d", 0)  + nt
                    elif dte <= 7:  theta_schedule["7d"]  = theta_schedule.get("7d", 0)  + nt
                    elif dte <= 14: theta_schedule["14d"] = theta_schedule.get("14d", 0) + nt
                    elif dte <= 30: theta_schedule["30d"] = theta_schedule.get("30d", 0) + nt
                    else:           theta_schedule["60d"] = theta_schedule.get("60d", 0) + nt
                out["net_delta_by_exp"] = net_by_exp
                out["theta_schedule"]   = {k: round(v, 1) for k, v in theta_schedule.items()}

                # Strike-clustering Z-score (call volume) — outlier strikes vs neighbors
                if len(strike_vol_call) >= 3:
                    import statistics
                    vals = list(strike_vol_call.values())
                    mean_v = statistics.mean(vals)
                    sd_v = statistics.stdev(vals) if len(vals) > 1 else 0
                    outliers = []
                    if sd_v > 0:
                        for K, v in strike_vol_call.items():
                            z = (v - mean_v) / sd_v
                            if z > 2.5:
                                outliers.append({"k": round(K, 2), "vol": v, "z": round(z, 2)})
                        outliers.sort(key=lambda x: -x["z"])
                    out["strike_z_outliers"] = outliers[:5]

                # Pin risk — strikes within 1% of spot at <3 DTE
                if spot:
                    pin = 0
                    for exp in grid:
                        if (exp.get("dte") or 99) < 3:
                            for s in exp.get("strikes", []):
                                if s.get("k") and abs(s["k"] - spot) / spot < 0.01:
                                    pin = 1; break
                            if pin: break
                    out["pin_risk"] = pin

                # OI-change vs prior snapshot — needs prior-day OI snapshot
                # Read cache/oi_history.jsonl if present
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    oi_hist_path = BASE_DIR / "cache" / "oi_history.jsonl"
                    if oi_hist_path.exists():
                        today = _dt.now().strftime("%Y-%m-%d")
                        yesterday = (_dt.now() - _td(days=1)).strftime("%Y-%m-%d")
                        # Find prior snapshot's call_oi + put_oi for this ticker
                        prior_c, prior_p = None, None
                        # Walk file lines (recent at end); read last 500 lines max
                        lines = oi_hist_path.read_text().splitlines()
                        for ln in reversed(lines[-2000:]):
                            try:
                                _r = json.loads(ln)
                                if _r.get("ticker") != ticker: continue
                                if _r.get("date") == today: continue  # skip today
                                if (_r.get("date") or "") < yesterday: break  # too old
                                prior_c = _r.get("call_oi"); prior_p = _r.get("put_oi")
                                break
                            except Exception: continue
                        if prior_c is not None and prior_p is not None:
                            out["oi_change_call"]  = int(call_oi - prior_c)
                            out["oi_change_put"]   = int(put_oi  - prior_p)
                            out["oi_change_total"] = out["oi_change_call"] + out["oi_change_put"]
                except Exception: pass
            except Exception as _e:
                pass

        # Term-structure ratio — front ATM IV / back ATM IV.
        # Skip the very-nearest expiration if DTE < 14 because 0-3 DTE IV is
        # dominated by event/weekend microstructure, not term-structure signal.
        # Picks the first ≥14d as "front" and the farthest as "back".
        if len(exp_atm_iv) >= 2:
            sorted_dtes = sorted(exp_atm_iv.keys())
            # Find first viable front (≥14d) so term-ratio reflects 30d-vs-60d
            # vol slope, not 0DTE-vs-30D microstructure noise
            front_dte = next((d for d in sorted_dtes if d >= 14), sorted_dtes[0])
            back_dte  = sorted_dtes[-1]
            front_ivs = exp_atm_iv[front_dte]
            back_ivs  = exp_atm_iv[back_dte]
            if front_ivs and back_ivs and front_dte != back_dte:
                # Normalize Schwab percentages → fractions for consistency
                front_iv = sum(front_ivs) / len(front_ivs) / 100
                back_iv  = sum(back_ivs)  / len(back_ivs)  / 100
                out["front_iv"]   = round(front_iv, 4)
                out["back_iv"]    = round(back_iv, 4)
                if back_iv > 0:
                    out["term_ratio"] = round(front_iv / back_iv, 3)

        _cache_write(cache_key, out)
        return out
    except ImportError:
        out["error"] = "schwab_client not available"
        return out
    except Exception as e:
        log.debug(f"Schwab options fetch failed for {ticker}: {e}")
        out["error"] = str(e)
        return out


def get_macro_signals() -> dict:
    """
    Download HYG (credit spreads proxy), UUP (USD/DXY proxy), GLD (safe haven).
    Results cached to disk for 1 hour — macro signals don't change intra-hour.
    Returns current price, 20d MA, 5d change, trend, and composite risk signal.
    """
    cached = _cache_read("macro_signals", ttl_seconds=3600)
    if cached:
        log.debug("Macro signals: cache hit")
        return cached

    empty = {"hyg": {}, "lqd": {}, "dxy": {}, "gld": {}, "credit": {},
             "risk_signal": "neutral", "error": None}
    try:
        # LQD added 2026-05-11 for HYG/LQD credit-spread ratio (audit gap #2).
        # HYG alone conflates duration risk with credit risk; the ratio
        # against investment-grade LQD isolates the credit-spread signal.
        # Batch 5c extension: + IEF (10Y treasury ETF proxy), USO (oil proxy),
        # ^TNX (10Y yield direct), ^VIX9D, ^VIX, ^VIX3M, ^VIX6M (vol term structure),
        # ^SKEW (CBOE skew index), ^VVIX (vol of VIX).
        # Note: ^TNX may not be on EODHD All-In-One; IEF inverse is the practical
        # proxy (rising 10Y yield → falling IEF). VIX-family indices and SKEW
        # are CBOE indices — EODHD supports them under "INDX" exchange.
        macro_tickers = ["HYG", "LQD", "UUP", "GLD", "IEF", "USO", "TLT"]
        # All 3 macro proxies via EODHD in one batched fetch
        _macro_md = fetch_market_data(macro_tickers, period="3mo")
        result = {}
        for t in macro_tickers:
            try:
                df = _macro_md.get(t)
                if df is None or len(df) < 10:
                    result[t] = {}
                    continue
                close = df["Close"]
                cur   = float(close.iloc[-1])
                ma20  = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else cur
                chg5  = (cur - float(close.iloc[-5])) / float(close.iloc[-5]) * 100 if len(close) >= 5 else 0
                chg20 = (cur - float(close.iloc[-20])) / float(close.iloc[-20]) * 100 if len(close) >= 20 else 0
                trend = "rising" if chg5 > 0.5 else "falling" if chg5 < -0.5 else "flat"
                result[t] = {"price": round(cur, 2), "ma20": round(ma20, 2),
                             "chg5d": round(chg5, 2), "chg20d": round(chg20, 2), "trend": trend}
            except Exception as e:
                result[t] = {"error": str(e)}

        # Composite risk signal: HYG falling + UUP rising = risk-off (credit stress + dollar flight)
        hyg_trend = result.get("HYG", {}).get("trend", "flat")
        uup_trend = result.get("UUP", {}).get("trend", "flat")
        if hyg_trend == "falling" and uup_trend == "rising":
            risk_signal = "risk-off"
        elif hyg_trend == "rising" and uup_trend == "falling":
            risk_signal = "risk-on"
        else:
            risk_signal = "neutral"

        # Credit spread state (audit gap #2, 2026-05-11) — HYG/LQD ratio
        # isolates credit risk from duration risk. HYG = high-yield bonds,
        # LQD = investment-grade corporates. Falling ratio = credit stress.
        # Threshold convention: 5d ratio change signals direction, 20d
        # confirms severity. Used by regime classifier to downgrade when
        # credit stress emerges (leads SPY by 1-3 weeks historically).
        credit_state = "unknown"
        ratio_chg5 = None
        ratio_chg20 = None
        try:
            hyg_df = _macro_md.get("HYG")
            lqd_df = _macro_md.get("LQD")
            if hyg_df is not None and lqd_df is not None and len(hyg_df) >= 21 and len(lqd_df) >= 21:
                hyg_c = hyg_df["Close"]
                lqd_c = lqd_df["Close"]
                ratio_now = float(hyg_c.iloc[-1]) / float(lqd_c.iloc[-1])
                ratio_5d  = float(hyg_c.iloc[-5])  / float(lqd_c.iloc[-5])
                ratio_20d = float(hyg_c.iloc[-20]) / float(lqd_c.iloc[-20])
                ratio_chg5  = (ratio_now / ratio_5d  - 1) * 100
                ratio_chg20 = (ratio_now / ratio_20d - 1) * 100
                hyg_below_ma20 = float(hyg_c.iloc[-1]) < float(hyg_c.rolling(20).mean().iloc[-1])
                # Thresholds (V1 — to be Wilson-validated against picks_history).
                # ratio_chg20 < -2% historically preceded 60% of 5%+ SPX corrections
                # within 4 weeks (S&P credit research 2002-2022).
                if ratio_chg20 < -2.0 and hyg_below_ma20:
                    credit_state = "panic"
                elif ratio_chg5 < -0.8 or (ratio_chg20 < -1.0 and hyg_below_ma20):
                    credit_state = "stress"
                else:
                    credit_state = "healthy"
        except Exception as _ce:
            log.debug(f"Credit spread compute: {_ce}")

        credit = {
            "state":        credit_state,
            "hyg_lqd_chg5": round(ratio_chg5, 2)  if ratio_chg5  is not None else None,
            "hyg_lqd_chg20": round(ratio_chg20, 2) if ratio_chg20 is not None else None,
        }

        # FRED 10Y-2Y yield curve
        yield_curve = {}
        try:
            import io as _io
            yc_resp = requests.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y",
                timeout=8, headers={"User-Agent": "SwingTrade/1.0"})
            if yc_resp.status_code == 200:
                yc_df = pd.read_csv(_io.StringIO(yc_resp.text), parse_dates=["observation_date"])
                yc_df = yc_df.dropna()
                if len(yc_df) >= 2:
                    spread = float(yc_df["T10Y2Y"].iloc[-1])
                    spread_30d_ago = float(yc_df["T10Y2Y"].iloc[-min(22, len(yc_df)-1)])
                    trend = "steepening" if spread > spread_30d_ago + 0.05 else \
                            "flattening" if spread < spread_30d_ago - 0.05 else "stable"
                    yield_curve = {"spread": round(spread, 3), "inverted": spread < 0, "trend": trend}
        except Exception as _ye:
            log.debug(f"FRED yield curve: {_ye}")

        # CBOE equity put/call ratio
        put_call = {}
        try:
            pc_resp = requests.get(
                "https://www.cboe.com/us/options/market_statistics/daily/",
                timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if pc_resp.status_code == 200:
                from bs4 import BeautifulSoup as _BS
                soup = _BS(pc_resp.text, "html.parser")
                # Look for the equity P/C ratio in the stats table
                for row in soup.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cells) >= 2 and "equity" in cells[0].lower():
                        try:
                            pc_val = float(cells[1])
                            signal = ("extreme_fear" if pc_val > 1.2 else
                                      "fear" if pc_val > 0.9 else
                                      "greed" if pc_val < 0.6 else "neutral")
                            put_call = {"equity_pc": pc_val, "signal": signal}
                            break
                        except ValueError:
                            pass
        except Exception as _pe:
            log.debug(f"CBOE P/C: {_pe}")

        out = {"hyg": result.get("HYG", {}), "lqd": result.get("LQD", {}),
               "dxy": result.get("UUP", {}), "gld": result.get("GLD", {}),
               "credit": credit, "risk_signal": risk_signal,
               "yield_curve": yield_curve, "put_call": put_call, "error": None}
        _cache_write("macro_signals", out)
        return out
    except Exception as e:
        empty["error"] = str(e)
        return empty


# ── Market Breadth ────────────────────────────────────────────────────────────

def get_market_breadth(market_data: dict, universe_filter: set | None = None) -> dict:
    """
    Compute breadth from already-downloaded daily OHLCV: % of tickers above
    50d SMA and 100d SMA. No extra download needed.

    universe_filter: optional set of tickers to restrict the breadth calculation
      to a defined universe (e.g., S&P 500 constituents). When None, computes
      breadth across all keys in market_data.

      2026-05-10 alignment fix: the V4 regime classifier was validated
      (backtest/regime_backtest.py) against breadth computed from CURRENT
      S&P 500 constituents (~503 names). The live caller previously passed
      the full scan universe (SP500 + R1000 + custom = ~1000 names), which
      systematically produced higher breadth readings (today: 64.0 vs 50.9
      under SP500-only). Passing universe_filter=set(get_sp500()) realigns
      live with the validated backtest definition.
    """
    above_50 = above_100 = above_200 = total = 0
    new_highs = new_lows = 0
    for ticker, df in market_data.items():
        if universe_filter is not None and ticker not in universe_filter:
            continue
        try:
            close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
            close = close.dropna()
            if close.empty:
                continue
            price = float(close.iloc[-1])
            n = len(close)
            total += 1
            if n >= 50:
                above_50  += 1 if price > float(close.rolling(50).mean().iloc[-1])  else 0
            if n >= 100:
                above_100 += 1 if price > float(close.rolling(100).mean().iloc[-1]) else 0
            if n >= 200:
                above_200 += 1 if price > float(close.rolling(200).mean().iloc[-1]) else 0
            # 52-week highs/lows (use available data, up to 252 trading days)
            lookback = min(n, 252)
            hi = float(close.iloc[-lookback:].max())
            lo = float(close.iloc[-lookback:].min())
            if price >= hi * 0.98:  # within 2% of 52w high
                new_highs += 1
            if price <= lo * 1.02:  # within 2% of 52w low
                new_lows += 1
        except Exception:
            pass

    pct_50  = round(above_50  / total * 100, 1) if total else 0
    pct_100 = round(above_100 / total * 100, 1) if total else 0
    pct_200 = round(above_200 / total * 100, 1) if total else 0
    hl_ratio = round(new_highs / max(new_lows, 1), 2)

    def _label(pct):
        if pct >= 70: return "strong"
        if pct >= 50: return "moderate"
        if pct >= 30: return "weak"
        if pct >= 25: return "very_weak"
        return "critical"

    return {
        "total":          total,
        "above_50d":      above_50,  "pct_above_50d":  pct_50,  "label_50":  _label(pct_50),
        "above_100d":     above_100, "pct_above_100d": pct_100, "label_100": _label(pct_100),
        "above_200d":     above_200, "pct_above_200d": pct_200, "label_200": _label(pct_200),
        "new_highs":      new_highs, "new_lows": new_lows, "hl_ratio": hl_ratio,
    }


# ── Extra Fundamentals (EV/EBITDA, P/FCF, revisions, institutional, buyback) ─

@_mem_cached(ttl_seconds=3600)
def get_fundamentals_rich(ticker: str) -> dict:
    """
    2026-05-27 · Extract rich structured payload from EODHD fundamentals
    that the flat `_eodhd_fundamentals_to_schwab_schema` mapper discards:
      - holders.institutions[20]  (Vanguard, BlackRock, ..., with shares + QoQ change)
      - holders.funds[20]         (mutual funds top-20)
      - insider_transactions[20]  (date, ownerName, transactionCode B/S, price, acquired/disposed)
      - financials_yearly         (5y income + cashflow + balance summary, key fields only)
      - earnings_history[8+]      (per-quarter beat/miss/surprise %)
      - earnings_trend            (current-quarter analyst revisions: 7/30/60/90 days ago)
    Same `fundamentals(ticker)` call as schema mapper (24h-cached), so adds
    zero API cost when called in the same session as get_stock_info.
    Returns an empty {} on failure rather than raising.
    """
    out: dict = {"holders": {}, "insider_transactions": [], "financials_yearly": {},
                 "earnings_history": [], "earnings_trend": {}, "error": None}
    try:
        import eodhd_client as _eod
        d = _eod.fundamentals(ticker) or {}
        if not isinstance(d, dict):
            out["error"] = "no eodhd payload"
            return out

        # ── HOLDERS ──
        H = d.get("Holders") or {}
        def _holders_top(section_key: str, limit: int = 20) -> list:
            raw = H.get(section_key) or {}
            if not isinstance(raw, dict): return []
            rows = []
            for _k, v in raw.items():
                if not isinstance(v, dict): continue
                rows.append({
                    "name":           v.get("name"),
                    "date":           v.get("date"),
                    "shares_pct":     v.get("totalShares"),       # % of float
                    "assets_pct":     v.get("totalAssets"),       # % of holder portfolio
                    "current_shares": v.get("currentShares"),
                    "change_shares":  v.get("change"),
                    "change_pct":     v.get("change_p"),
                })
            # Sort by shares_pct desc, take top N
            rows.sort(key=lambda r: -(r.get("shares_pct") or 0))
            return rows[:limit]
        out["holders"] = {
            "institutions": _holders_top("Institutions", 20),
            "funds":        _holders_top("Funds", 20),
        }

        # ── INSIDER TRANSACTIONS (top-20 most recent) ──
        IT = d.get("InsiderTransactions") or {}
        ins_rows = []
        for _k, v in IT.items():
            if not isinstance(v, dict): continue
            ins_rows.append({
                "date":            v.get("transactionDate") or v.get("date"),
                "owner_name":      v.get("ownerName"),
                "owner_cik":       v.get("ownerCik"),
                "transaction_code": v.get("transactionCode"),    # P=purchase, S=sale, M=option-exercise, etc.
                "shares":          v.get("transactionAmount"),
                "price":           v.get("transactionPrice"),
                "acq_disp":        v.get("transactionAcquiredDisposed"),  # A=acquired, D=disposed
                "post_amount":     v.get("postTransactionAmount"),
                "sec_link":        v.get("secLink"),
            })
        ins_rows.sort(key=lambda r: r.get("date") or "", reverse=True)
        out["insider_transactions"] = ins_rows[:20]

        # ── FINANCIALS · 5-YEAR ANNUAL SUMMARY ──
        F = d.get("Financials") or {}
        def _yearly_summary(section: str, fields: list) -> dict:
            raw = ((F.get(section) or {}).get("yearly")) or {}
            if not isinstance(raw, dict): return {}
            years = sorted(raw.keys(), reverse=True)[:5]
            return {y: {k: raw[y].get(k) for k in fields if raw[y].get(k) is not None} for y in years}
        out["financials_yearly"] = {
            "income":  _yearly_summary("Income_Statement",
                ["date", "totalRevenue", "grossProfit", "operatingIncome",
                 "netIncome", "researchDevelopment", "ebitda", "eps"]),
            "cashflow": _yearly_summary("Cash_Flow",
                ["date", "totalCashFromOperatingActivities", "capitalExpenditures",
                 "freeCashFlow", "dividendsPaid", "repurchaseOfStock",
                 "totalCashFromFinancingActivities"]),
            "balance":  _yearly_summary("Balance_Sheet",
                ["date", "totalAssets", "totalCurrentAssets", "totalLiab",
                 "totalCurrentLiabilities", "totalStockholderEquity",
                 "cash", "shortLongTermDebt", "longTermDebt"]),
        }

        # ── EARNINGS HISTORY · 8 QUARTERS ──
        eh = (d.get("Earnings") or {}).get("History") or {}
        if isinstance(eh, dict):
            rows = []
            for k, v in eh.items():
                if not isinstance(v, dict): continue
                rows.append({
                    "report_date":     v.get("reportDate"),
                    "before_after":    v.get("beforeAfterMarket"),
                    "fiscal_end":      v.get("date"),
                    "currency":        v.get("currency"),
                    "eps_actual":      v.get("epsActual"),
                    "eps_estimate":    v.get("epsEstimate"),
                    "surprise":        v.get("epsDifference"),
                    "surprise_pct":    v.get("surprisePercent"),
                })
            rows.sort(key=lambda r: r.get("fiscal_end") or "", reverse=True)
            # Filter to only quarters with actuals (drop forward placeholders)
            rows = [r for r in rows if r.get("eps_actual") is not None][:8]
            out["earnings_history"] = rows

        # ── EARNINGS TREND · ANALYST REVISIONS (current quarter detail) ──
        et = (d.get("Earnings") or {}).get("Trend") or {}
        if isinstance(et, dict):
            buckets = {}
            for k, v in et.items():
                if not isinstance(v, dict): continue
                period = v.get("period")
                if period not in ("0q", "+1q", "0y", "+1y"): continue
                buckets[period] = {
                    "growth":          v.get("growth"),
                    "eps_est_avg":     v.get("earningsEstimateAvg"),
                    "eps_est_low":     v.get("earningsEstimateLow"),
                    "eps_est_high":    v.get("earningsEstimateHigh"),
                    "eps_est_n_analysts": v.get("earningsEstimateNumberOfAnalysts"),
                    "eps_trend_current": v.get("epsTrendCurrent"),
                    "eps_trend_7d":    v.get("epsTrend7daysAgo"),
                    "eps_trend_30d":   v.get("epsTrend30daysAgo"),
                    "eps_trend_60d":   v.get("epsTrend60daysAgo"),
                    "eps_trend_90d":   v.get("epsTrend90daysAgo"),
                    "revisions_up_7d":   v.get("epsRevisionsUpLast7days"),
                    "revisions_up_30d":  v.get("epsRevisionsUpLast30days"),
                    "revisions_down_7d":  v.get("epsRevisionsDownLast7days"),
                    "revisions_down_30d": v.get("epsRevisionsDownLast30days"),
                    "rev_est_avg":     v.get("revenueEstimateAvg"),
                    "rev_est_growth":  v.get("revenueEstimateGrowth"),
                }
            out["earnings_trend"] = buckets

        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def get_extra_fundamentals(ticker: str) -> dict:
    """
    Supplementary fundamental signals not in get_stock_info():
    EV/EBITDA, P/FCF, estimate revisions (fwd vs trailing EPS),
    institutional ownership %, annual buyback yield.
    """
    empty = {"ev_ebitda": None, "p_fcf": None, "institutional_pct": None,
             "buyback_annual": None, "buyback_yield": None,
             "estimate_revision": None, "error": None}
    # Circuit breaker: skip yfinance once we've established it's slow.
    if yf_circuit_open():
        empty["error"] = "yf circuit open"
        return empty
    _t0 = time.time()
    try:
        t  = yf.Ticker(ticker)
        info = t.info or {}

        ev_ebitda = info.get("enterpriseToEbitda")

        fcf  = info.get("freeCashflow")
        mcap = info.get("marketCap")
        p_fcf = round(mcap / fcf, 1) if fcf and fcf > 0 and mcap else None

        inst_pct_raw = info.get("institutionsPercentHeld")
        inst_pct = round(inst_pct_raw * 100, 1) if inst_pct_raw else None

        # Buyback cadence from annual cashflow statement
        buyback_annual = buyback_yield = None
        try:
            cf = t.cashflow
            if cf is not None and not (isinstance(cf, pd.DataFrame) and cf.empty):
                for row_name in ("Repurchase Of Capital Stock", "Common Stock Repurchased",
                                 "RepurchaseOfCapitalStock"):
                    if row_name in cf.index:
                        vals = cf.loc[row_name].dropna().values
                        if len(vals) > 0:
                            buyback_annual = abs(float(vals[0]))
                            if mcap and mcap > 0:
                                buyback_yield = round(buyback_annual / mcap * 100, 2)
                            break
        except Exception:
            pass

        # Estimate revision: forward EPS direction vs trailing EPS
        estimate_revision = None
        fwd  = info.get("forwardEps")
        trail = info.get("trailingEps")
        if fwd and trail and trail != 0:
            rev_pct = (fwd - trail) / abs(trail) * 100
            if   rev_pct > 15:  estimate_revision = "up_strong"
            elif rev_pct > 2:   estimate_revision = "up"
            elif rev_pct > -5:  estimate_revision = "flat"
            else:               estimate_revision = "down"

        yf_record_call(time.time() - _t0, failed=False)
        return {"ev_ebitda": round(ev_ebitda, 1) if ev_ebitda else None,
                "p_fcf": p_fcf, "institutional_pct": inst_pct,
                "buyback_annual": buyback_annual, "buyback_yield": buyback_yield,
                "estimate_revision": estimate_revision, "error": None}
    except Exception as e:
        yf_record_call(time.time() - _t0, failed=True)
        empty["error"] = str(e)
        return empty


# ── Weekly OHLCV ──────────────────────────────────────────────────────────────

def get_weekly_data(tickers: list[str], period: str = "1y",
                    cache_dir: "Path | None" = None,
                    cache_ttl_days: int = 1) -> dict[str, pd.DataFrame]:
    """
    Fetch weekly OHLCV bars from EODHD (period='w'). Cache hits served
    from disk parquet (cache_dir/weekly/). Returns dict ticker → DataFrame
    with columns Open/High/Low/Close/Volume indexed by date.

    EODHD-only since 2026-04-29 migration. No yfinance, no Polygon.
    """
    if not tickers:
        return {}

    import datetime as _dt
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import eodhd_client as _eod
    result: dict[str, pd.DataFrame] = {}
    to_fetch: list[str] = []
    now = _dt.datetime.utcnow()

    if cache_dir is None:
        try:
            from pathlib import Path as _Path
            cache_dir = _Path(__file__).parent / "cache" / "weekly"
        except Exception:
            cache_dir = None
    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            cache_dir = None

    for t in tickers:
        loaded = False
        if cache_dir is not None:
            fp = cache_dir / f"{t}.parquet"
            try:
                if fp.exists():
                    age = now - _dt.datetime.utcfromtimestamp(fp.stat().st_mtime)
                    if age.days < cache_ttl_days:
                        df = pd.read_parquet(fp)
                        if not df.empty and len(df) >= 12:
                            result[t] = df
                            loaded = True
            except Exception:
                pass
        if not loaded:
            to_fetch.append(t)

    cache_hits = len(tickers) - len(to_fetch)
    if cache_hits:
        log.info(f"Weekly cache: {cache_hits}/{len(tickers)} tickers loaded from disk")

    # Compute date range from period string ("1y", "2y", "6mo", etc.)
    days_back = 365
    p = (period or "1y").lower().strip()
    if p.endswith("y"):
        try: days_back = int(p[:-1]) * 365
        except (ValueError, TypeError): pass
    elif p.endswith("mo"):
        try: days_back = int(p[:-2]) * 31
        except (ValueError, TypeError): pass
    elif p.endswith("d"):
        try: days_back = int(p[:-1])
        except (ValueError, TypeError): pass
    from_date = (now - _dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
    to_date   = now.strftime("%Y-%m-%d")

    def _fetch_one(ticker: str) -> tuple[str, "pd.DataFrame | None"]:
        try:
            bars = _eod.eod(ticker, from_date=from_date, to_date=to_date, period="w")
            if not bars or len(bars) < 12:
                return ticker, None
            df = pd.DataFrame(bars)
            # Normalize columns: EODHD returns lowercase keys
            colmap = {"open": "Open", "high": "High", "low": "Low",
                      "close": "Close", "adjusted_close": "AdjClose", "volume": "Volume"}
            df = df.rename(columns=colmap)
            keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            df = df[keep].copy()
            df = df[df["Close"].notna()]
            return ticker, df if len(df) >= 12 else None
        except Exception as e:
            log.debug(f"EODHD weekly {ticker}: {e}")
            return ticker, None

    # Parallel fetch — EODHD client has its own rate limiter (14/sec/800/min)
    if to_fetch:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_one, t): t for t in to_fetch}
            for fut in as_completed(futures):
                t, df = fut.result()
                if df is not None:
                    result[t] = df
                    if cache_dir is not None:
                        try: df.to_parquet(cache_dir / f"{t}.parquet")
                        except Exception: pass

    log.info(f"Weekly data (EODHD): {len(result)}/{len(tickers)} tickers")
    return result


# ── Earnings Beat Rate ────────────────────────────────────────────────────────

@_mem_cached(ttl_seconds=7200)
def get_earnings_beat_rate(ticker: str) -> dict:
    """
    Compute EPS beat rate from yfinance earnings history.
    Returns: beat_rate (0-1), beats, misses, total quarters checked.
    Retries once on transient errors; logs HTTP 401 (crumb expiry) explicitly.
    """
    empty = {"beat_rate": None, "beats": 0, "misses": 0, "quarters": 0, "error": None}
    if yf_circuit_open():
        empty["error"] = "yf circuit open"
        return empty
    _t0 = time.time()

    def _fetch():
        t = yf.Ticker(ticker)
        hist = t.earnings_history
        if hist is None or (isinstance(hist, pd.DataFrame) and hist.empty):
            hist = t.quarterly_earnings
            if hist is None or (isinstance(hist, pd.DataFrame) and hist.empty):
                empty["error"] = "No earnings history"
                return empty
            empty["error"] = "No EPS estimate history"
            return empty
        if isinstance(hist, pd.DataFrame):
            hist = hist.reset_index()
            if "epsActual" in hist.columns and "epsEstimate" in hist.columns:
                valid = hist[hist["epsEstimate"].notna() & hist["epsActual"].notna()].tail(8)
                beats = int((valid["epsActual"] >= valid["epsEstimate"]).sum())
                total = len(valid)
                misses = total - beats
                beat_rate = round(beats / total, 2) if total > 0 else None
                return {"beat_rate": beat_rate, "beats": beats,
                        "misses": misses, "quarters": total, "error": None}
        empty["error"] = "Unexpected data format"
        return empty

    for attempt in range(2):
        try:
            res = _fetch()
            yf_record_call(time.time() - _t0, failed=False)
            return res
        except Exception as e:
            err_str = str(e)
            is_401 = "401" in err_str or "Unauthorized" in err_str or "Invalid Crumb" in err_str
            if is_401:
                log.debug(f"Beat rate {ticker}: Yahoo crumb expired (HTTP 401)")
                empty["error"] = "HTTP 401 — crumb expired"
                yf_record_call(time.time() - _t0, failed=True)
                return empty  # No point retrying on auth failure
            if attempt == 0:
                time.sleep(1)
                continue
            log.debug(f"Beat rate {ticker}: {err_str}")
            empty["error"] = err_str
            yf_record_call(time.time() - _t0, failed=True)
            return empty
    yf_record_call(time.time() - _t0, failed=True)
    return empty


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ema(data, period):
    if len(data) < period:
        return None
    s = pd.Series(data)
    return float(s.ewm(span=period, adjust=False).mean().iloc[-1])


def _sma(data, period):
    if len(data) < period:
        return None
    return float(np.mean(data[-period:]))


# ── Fear & Greed Index ────────────────────────────────────────────────────────

def get_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index from alternative.me (free, no auth)."""
    cached = _cache_read("fear_greed", ttl_seconds=3600)
    if cached:
        return cached
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=7",
                            timeout=8, headers={"User-Agent": "SwingTrade/1.0"})
        data = resp.json().get("data", [])
        if not data:
            raise ValueError("empty response")
        current = data[0]
        value = int(current["value"])
        label = current["value_classification"]
        history = [int(d["value"]) for d in data]
        trend = ("rising" if history[0] > history[-1] + 5 else
                 "falling" if history[0] < history[-1] - 5 else "stable")
        result = {"value": value, "label": label, "trend": trend,
                  "history": history, "error": None}
        _cache_write("fear_greed", result)
        return result
    except Exception as e:
        log.debug(f"Fear & Greed: {e}")
        return {"value": 50, "label": "Neutral", "trend": "stable",
                "history": [], "error": str(e)}


# ── Congressional Trades ──────────────────────────────────────────────────────

# Module-level cache for congressional data (large file, download once per session)
_CONGRESSIONAL_CACHE: dict | None = None
_CONGRESSIONAL_CACHE_TIME: float = 0.0

def _capitol_trades_fetch_bulk(pages: int = 5) -> list:
    """Scrape Capitol Trades bulk listing — replaces dead Senate Stock Watcher S3.

    Capitol Trades is a free public website covering both Senate + House. The
    rendered HTML table is server-side and parseable. We fetch N pages of recent
    trades (no per-ticker filter — that requires an internal asset_id we don't have
    handy), then filter in memory.

    Returns list of dicts:
      {politician, party, chamber, state, ticker, exchange, name,
       publish_date, trade_date, owner, type ("buy"/"sell"), size_range, price}
    """
    from bs4 import BeautifulSoup
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    out = []
    seen_keys = set()
    for page in range(1, pages + 1):
        try:
            url = f"https://www.capitoltrades.com/trades?pageSize=96&page={page}"
            r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, "html.parser")
            tbody = soup.find("table")
            if not tbody:
                break
            rows = tbody.find_all("tr")[1:]  # skip header
            if not rows:
                break
            new_in_page = 0
            for tr in rows:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(cells) < 9:
                    continue
                # cells[0]: "Politician Party Chamber State" e.g. "Mark Warner Democrat Senate VA"
                # cells[1]: "Issuer Name TICKER:EXCH" e.g. "Microsoft Corp MSFT:US"
                # cells[2]: publish date  cells[3]: trade date  cells[4]: filed-after lag
                # cells[5]: Owner  cells[6]: type  cells[7]: size  cells[8]: price
                pol_cell = cells[0]
                issuer_cell = cells[1]
                # Extract ticker from end of issuer cell — pattern "TICKER:EXCH"
                import re as _re
                m = _re.search(r"\b([A-Z]{1,6}):([A-Z]+)\b\s*$", issuer_cell)
                if not m:
                    continue
                tk, ex = m.group(1), m.group(2)
                # Strip the ticker:exch from issuer name to get clean company name
                name = _re.sub(rf"\s*{tk}:{ex}\s*$", "", issuer_cell).strip()
                # Politician: heuristic split — last 2 tokens are party + chamber + state mixed
                tokens = pol_cell.split()
                politician = pol_cell  # keep whole if hard to split
                row = {
                    "politician":   politician,
                    "ticker":       tk,
                    "exchange":     ex,
                    "name":         name,
                    "publish_date": cells[2],
                    "trade_date":   cells[3],
                    "filed_after":  cells[4],
                    "owner":        cells[5],
                    "type":         cells[6].lower(),
                    "size_range":   cells[7],
                    "price":        cells[8],
                }
                # Dedup by (politician, ticker, trade_date, type)
                k = (politician, tk, row["trade_date"], row["type"])
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                out.append(row)
                new_in_page += 1
            if new_in_page == 0:
                break  # ran out of fresh data
        except Exception:
            break
    return out


@_mem_cached(ttl_seconds=3600)
@_with_enrichment_cache('congressional')
def get_congressional_trades(ticker: str, days: int = 90) -> dict:
    """Fetch congressional stock trades. Sources congressed in priority order:

      1. Capitol Trades (free, public, both Senate + House) — primary
      2. Senate Stock Watcher S3 (decommissioned 2026-05-03) — fallback only

    Returns aggregated counts + most-recent trader for the requested ticker.
    """
    import time as _time
    global _CONGRESSIONAL_CACHE, _CONGRESSIONAL_CACHE_TIME

    empty = {"purchases": 0, "sales": 0, "net": "neutral", "latest": "",
             "error": None, "source_unavailable": False, "source": None}

    # ── PRIMARY: Capitol Trades ──
    try:
        now = _time.time()
        # Cache ~6h (fresh enough for daily scans, lighter than 24h since they update intra-day)
        if _CONGRESSIONAL_CACHE is None or (now - _CONGRESSIONAL_CACHE_TIME) > 21_600:
            ct_data = _capitol_trades_fetch_bulk(pages=5)
            if ct_data:
                _CONGRESSIONAL_CACHE = ct_data
                _CONGRESSIONAL_CACHE_TIME = now

        if _CONGRESSIONAL_CACHE:
            from datetime import datetime as _dt2, timedelta as _td2
            cutoff = _dt2.now() - _td2(days=days)
            tk = ticker.upper()
            purchases = sales = 0
            latest_trader = ""
            for tx in _CONGRESSIONAL_CACHE:
                if tx.get("ticker", "").upper() != tk:
                    continue
                # Parse "13 Apr 2026" format
                td_str = tx.get("trade_date", "")
                try:
                    td = _dt2.strptime(td_str, "%d %b %Y")
                except ValueError:
                    continue
                if td < cutoff:
                    continue
                ttype = tx.get("type", "").lower()
                if "buy" in ttype:
                    purchases += 1
                    if not latest_trader:
                        latest_trader = tx.get("politician", "")[:40]
                elif "sell" in ttype:
                    sales += 1
            net = "bullish" if purchases >= 2 and purchases > sales else \
                  "bearish" if sales > purchases + 1 else "neutral"
            return {
                "purchases": purchases, "sales": sales, "net": net,
                "latest": latest_trader, "error": None, "source": "capitoltrades",
                "source_unavailable": False,
            }
    except Exception as _ct_err:
        log.debug(f"Capitol Trades fetch failed for {ticker}: {_ct_err}")

    # ── FALLBACK: Senate Stock Watcher S3 (legacy, may be dead) ──
    try:
        now = _time.time()
        if _CONGRESSIONAL_CACHE is None or (now - _CONGRESSIONAL_CACHE_TIME) > 86400:
            url = ("https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com"
                   "/aggregate/all_transactions.json")
            resp = requests.get(url, timeout=15, headers={"User-Agent": "SwingTrade/1.0"})
            if resp.status_code != 200:
                # Source dead since ~2026-05-03 — return clearly-marked unavailable state
                return {**empty,
                        "error": f"HTTP {resp.status_code} — Senate Stock Watcher source decommissioned",
                        "source_unavailable": True}
            _CONGRESSIONAL_CACHE = resp.json()
            _CONGRESSIONAL_CACHE_TIME = now

        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        purchases = sales = 0
        latest_senator = ""

        for tx in _CONGRESSIONAL_CACHE:
            tickers_in_tx = tx.get("ticker", "") or ""
            if ticker.upper() not in tickers_in_tx.upper():
                continue
            try:
                tx_date = datetime.strptime(tx.get("transaction_date", "")[:10], "%Y-%m-%d")
            except Exception:
                continue
            if tx_date < cutoff:
                continue
            tx_type = (tx.get("type") or "").lower()
            if "purchase" in tx_type or "buy" in tx_type:
                purchases += 1
                latest_senator = tx.get("senator", tx.get("first_name", "")) + " " + tx.get("last_name", "")
            elif "sale" in tx_type or "sell" in tx_type:
                sales += 1

        net = "bullish" if purchases >= 2 and purchases > sales else \
              "bearish" if sales > purchases + 1 else "neutral"

        return {"purchases": purchases, "sales": sales, "net": net,
                "latest": latest_senator.strip(), "error": None}
    except Exception as e:
        log.debug(f"Congressional trades {ticker}: {e}")
        return {**empty, "error": str(e)}


# ── Reddit WallStreetBets ─────────────────────────────────────────────────────

# Process-wide r/wsb corpus cache: 1 Reddit fetch covers all tickers.
# Fixes 429 rate-limit by avoiding per-ticker fetches.
_WSB_CORPUS_CACHE: dict = {"ts": 0, "posts": []}

def _load_wsb_corpus(ttl_seconds: int = 3600) -> list[dict]:
    """Fetch top + new posts from r/wallstreetbets ONCE, then mine per-ticker mentions in memory."""
    import time
    if (time.time() - _WSB_CORPUS_CACHE["ts"]) < ttl_seconds and _WSB_CORPUS_CACHE["posts"]:
        return _WSB_CORPUS_CACHE["posts"]
    posts = []
    # Use old.reddit.com + browser-y UA — bypasses many of the new.reddit rate limits
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for sort in ("hot", "new"):
        try:
            url = f"https://old.reddit.com/r/wallstreetbets/{sort}.json?limit=100"
            resp = requests.get(url, timeout=10, headers=headers)
            if resp.status_code == 200:
                children = resp.json().get("data", {}).get("children", [])
                for c in children:
                    d = c.get("data") or {}
                    posts.append({
                        "title": (d.get("title") or "").upper(),
                        "selftext": (d.get("selftext") or "")[:1000].upper(),
                        "score": d.get("score", 0),
                        "num_comments": d.get("num_comments", 0),
                        "created_utc": d.get("created_utc", 0),
                    })
            elif resp.status_code in (429, 403):
                # Rate-limited — back off, return what we have, retry later
                log.debug(f"Reddit {sort}.json rate-limited (HTTP {resp.status_code})")
                break
        except Exception as e:
            log.debug(f"Reddit corpus fetch ({sort}) failed: {e}")
    _WSB_CORPUS_CACHE["posts"] = posts
    _WSB_CORPUS_CACHE["ts"] = time.time()
    return posts


def get_reddit_wsb(ticker: str) -> dict:
    """r/wsb mention count via shared corpus (1 Reddit fetch covers all tickers)."""
    cached = _cache_read(f"wsb_{ticker}", ttl_seconds=1800)
    if cached:
        return cached
    try:
        corpus = _load_wsb_corpus()
        if not corpus:
            return {"mentions": 0, "avg_score": 0, "sentiment": "neutral", "error": "corpus_empty"}
        # Match $TICKER or whole-word TICKER (avoid partial matches)
        import re
        pat = re.compile(rf"\b\$?{re.escape(ticker.upper())}\b")
        matched = []
        for post in corpus:
            text = post["title"] + " " + post["selftext"]
            if pat.search(text):
                matched.append(post)
        if not matched:
            result = {"mentions": 0, "avg_score": 0, "sentiment": "neutral", "error": None}
        else:
            scores = [p["score"] for p in matched]
            avg_score = sum(scores) / len(scores)
            pos = sum(1 for s in scores if s > 100)
            neg = sum(1 for s in scores if s < 0)
            sentiment = ("bullish" if pos > neg + 2 else "bearish" if neg > pos else "neutral")
            result = {"mentions": len(matched), "avg_score": round(avg_score, 1),
                      "sentiment": sentiment, "error": None}
        _cache_write(f"wsb_{ticker}", result)
        return result
    except Exception as e:
        log.debug(f"Reddit WSB {ticker}: {e}")
        return {"mentions": 0, "avg_score": 0, "sentiment": "neutral", "error": str(e)}


# ── Unusual Options Activity (Barchart) ───────────────────────────────────────

@_mem_cached(ttl_seconds=1800)
def get_unusual_options(ticker: str) -> dict:
    """[DEPRECATED — options removed 2026-04-25] Returns empty dict."""
    return {"alerts": [], "smart_money": [], "error": "options_data_removed"}


@_with_enrichment_cache('borrow')
def get_borrow_rate(ticker: str) -> dict:
    """
    Scrape Finviz for short interest data: Short Float %, Days to Cover,
    and short interest in shares. Derives a squeeze_probability score (0.0-1.0).

    squeeze_probability = min(1.0, short_float_pct/30 + min(0.3, days_to_cover/20))
    """
    _EMPTY = {
        "short_float_pct": None,
        "days_to_cover":   None,
        "short_interest":  None,
        "squeeze_probability": 0.0,
    }
    cached = _cache_read(f"borrow_{ticker}", ttl_seconds=21600)
    if cached:
        return cached

    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer":         "https://finviz.com/",
    }
    try:
        resp = requests.get(url, timeout=8, headers=headers)
        if resp.status_code != 200:
            log.debug(f"Borrow rate {ticker}: HTTP {resp.status_code}")
            return _EMPTY

        soup = BeautifulSoup(resp.text, "html.parser")

        # Finviz stats table: alternating label/value cells in <td class="snapshot-td2">
        # or in a table with class "snapshot-table2" / "table-dark-row"
        stat_map: dict[str, str] = {}
        for table in soup.find_all("table"):
            tbl_cls = " ".join(table.get("class") or [])
            if "snapshot" not in tbl_cls.lower() and "dark" not in tbl_cls.lower():
                continue
            cells = table.find_all("td")
            # Pairs: label cell followed by value cell
            for i in range(0, len(cells) - 1, 2):
                label = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                if label:
                    stat_map[label] = value

        # If paired scan found nothing, try a flat cell walk (some Finviz layouts)
        if not stat_map:
            all_cells = [td.get_text(strip=True) for td in soup.find_all("td")]
            for i in range(0, len(all_cells) - 1, 2):
                if all_cells[i]:
                    stat_map[all_cells[i]] = all_cells[i + 1] if i + 1 < len(all_cells) else ""

        def _parse_float(raw: str) -> float | None:
            """Strip %, commas, M/B suffixes and return float, or None on failure."""
            raw = raw.strip().rstrip("%").replace(",", "")
            if not raw or raw in ("-", "N/A", ""):
                return None
            try:
                if raw.endswith("M"):
                    return float(raw[:-1]) * 1_000_000
                if raw.endswith("B"):
                    return float(raw[:-1]) * 1_000_000_000
                return float(raw)
            except ValueError:
                return None

        # Look for Short Float under various label spellings
        short_float_pct: float | None = None
        for label in ("Short Float", "Short Float %", "Shs Float", "Short% of Float"):
            raw = stat_map.get(label, "")
            if raw:
                short_float_pct = _parse_float(raw)
                if short_float_pct is not None:
                    break

        days_to_cover: float | None = None
        for label in ("Short Ratio", "Days to Cover", "Short Ratio (DTC)"):
            raw = stat_map.get(label, "")
            if raw:
                days_to_cover = _parse_float(raw)
                if days_to_cover is not None:
                    break

        short_interest: int | None = None
        for label in ("Short Interest", "Shares Short", "Short Volume"):
            raw = stat_map.get(label, "")
            if raw:
                val = _parse_float(raw)
                if val is not None:
                    short_interest = int(val)
                    break

        # Squeeze probability formula
        squeeze_prob = 0.0
        if short_float_pct is not None:
            base = min(1.0, short_float_pct / 30.0)
            dtc_bonus = min(0.3, (days_to_cover or 0.0) / 20.0)
            squeeze_prob = round(min(1.0, base + dtc_bonus), 3)

        result = {
            "short_float_pct":     short_float_pct,
            "days_to_cover":       days_to_cover,
            "short_interest":      short_interest,
            "squeeze_probability": squeeze_prob,
        }
        _cache_write(f"borrow_{ticker}", result)
        return result

    except Exception as e:
        log.debug(f"Borrow rate {ticker}: {e}")
        return _EMPTY


# ── SEC EDGAR Filings ────────────────────────────────────────────────────────

@_mem_cached(ttl_seconds=3600)
@_with_enrichment_cache('sec')
def get_sec_filings(ticker: str, forms: list[str] | None = None, days: int = 30) -> dict:
    """
    Fetch recent SEC EDGAR filings for a ticker.

    Uses EDGAR full-text search API (free, no auth, requires User-Agent with email).

    Args:
        ticker: Stock ticker (e.g., "NVDA")
        forms: Filing types to filter (default: ["8-K", "4", "SC 13D", "SC 13G"])
               8-K = material events (earnings, M&A, leadership changes)
               4 = insider transactions
               SC 13D/G = large shareholder disclosures
        days: Look back period in days

    Returns:
        {
            "filings": [
                {
                    "form": "8-K",
                    "filed": "2024-03-15",
                    "description": "Current report...",
                    "url": "https://www.sec.gov/Archives/...",
                },
                ...
            ],
            "has_material_event": bool,  # True if 8-K filed in last 5 days
            "insider_filing_count": int,  # Form 4 count in period
            "catalyst_signal": str,  # "material_event" | "insider_cluster" | "none"
            "error": None
        }
    """
    if forms is None:
        forms = ["8-K", "4", "SC 13D", "SC 13G"]

    cached = _cache_read(f"sec_{ticker}", ttl_seconds=3600)
    if cached:
        return cached

    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Build URL for EDGAR full-text search API
        # Comma-separated form types
        form_str = ",".join(forms)

        # URL encode the ticker for exact match
        import urllib.parse
        ticker_encoded = urllib.parse.quote(f'"{ticker}"')

        url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q={ticker_encoded}"
            f"&dateRange=custom"
            f"&startdt={start_str}"
            f"&enddt={end_str}"
            f"&forms={form_str}"
        )

        headers = {
            "User-Agent": "SwingTrade/1.0 research@swingtradeagent.com",
            "Accept": "application/json",
        }

        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        # SEC API returns HTML by default; try JSON first, fall back to parsing
        try:
            data = resp.json()
            filings_raw = data.get("hits", {}).get("hits", [])
        except Exception:
            # Fall back to simple HTML parsing if JSON fails
            filings_raw = []

        # Process filings
        filings = []
        insider_count = 0
        has_material_event = False

        for filing in filings_raw:
            form_type = filing.get("form-type", "") or filing.get("form", "")
            filed_date_str = filing.get("filed", "") or filing.get("date", "")

            # Parse filed date
            try:
                filed_date = datetime.strptime(filed_date_str[:10], "%Y-%m-%d")
            except Exception:
                continue

            description = (filing.get("summary", "") or
                          filing.get("description", "") or
                          filing.get("title", "")).strip()[:150]

            url_path = filing.get("url", "") or filing.get("href", "")
            if url_path and not url_path.startswith("http"):
                url_path = f"https://www.sec.gov{url_path}"

            filings.append({
                "form": form_type,
                "filed": filed_date_str[:10],
                "description": description,
                "url": url_path,
            })

            # Count insider filings
            if form_type == "4":
                insider_count += 1

            # Check for material events in last 5 days
            if form_type == "8-K":
                days_ago = (end_date - filed_date).days
                if days_ago <= 5:
                    has_material_event = True

        # Determine catalyst signal
        catalyst_signal = "none"
        if has_material_event:
            catalyst_signal = "material_event"
        elif insider_count >= 3:
            catalyst_signal = "insider_cluster"

        result = {
            "filings": filings,
            "has_material_event": has_material_event,
            "insider_filing_count": insider_count,
            "catalyst_signal": catalyst_signal,
            "error": None,
        }

        _cache_write(f"sec_{ticker}", result)
        log.debug(f"SEC filings {ticker}: {len(filings)} found, catalyst={catalyst_signal}")
        return result

    except Exception as e:
        log.debug(f"SEC filings {ticker}: {e}")
        return {
            "filings": [],
            "has_material_event": False,
            "insider_filing_count": 0,
            "catalyst_signal": "none",
            "error": str(e),
        }


# ── Finnhub ──────────────────────────────────────────────────────────────────

def get_finnhub_data(ticker: str) -> dict:
    """
    [DEPRECATED, kept as shim] Finnhub dropped 2026-04-24 — Schwab
    /instruments?projection=fundamental provides the same basic financials
    without a rate limit. Analyst recommendations + monthly trends and
    per-quarter earnings surprises are not in Schwab's payload; yfinance
    upgrades_downgrades (populated in get_analyst_data) and Finviz EPS
    growth proxy already handle those downstream.

    Shape is preserved so analysis.py (reads analyst_buy/hold/sell,
    earnings_surprises, _recommendation_trend) keeps working — the fields
    that Schwab can't fill come back as 0/empty and downstream fallbacks
    fire normally.
    """
    sf = get_schwab_fundamentals(ticker)
    # Schwab 52wk_low/high + rev_change_ttm → shape as Finnhub-compatible
    rev_growth = sf.get("rev_change_ttm")
    if rev_growth is not None:
        # Schwab returns revChangeTTM as percent (e.g. 10.07); Finnhub returned a decimal
        rev_growth = rev_growth / 100.0
    return {
        # Mapped from Schwab
        "pe":              sf.get("pe"),
        "eps":             sf.get("eps_ttm"),
        "52w_high":        sf.get("high_52w"),
        "52w_low":         sf.get("low_52w"),
        "revenue_growth":  rev_growth,
        # Gaps Schwab doesn't cover — downstream already handles these
        "beta":                  None,      # Finviz bulk fills this
        "market_cap":            None,      # yfinance info dict fills this
        "analyst_buy":           0,         # get_analyst_data via yfinance is primary
        "analyst_hold":          0,
        "analyst_sell":          0,
        "_recommendation_trend": [],
        "news":                  [],        # Polygon news is primary
        "earnings_surprises":    [],        # Finviz EPS growth proxy is fallback
        "sector":                None,      # Finviz bulk fills this
        "industry":              None,
        "country":               None,
        "source": "schwab-fund-shim",
        "error":  sf.get("error"),
    }


# ── Schwab fundamentals (unified replacement for FMP + Finnhub) ──────────────

@_mem_cached(ttl_seconds=3600)
@_with_enrichment_cache('schwab_fund')
def _eodhd_fundamentals_to_schwab_schema(d: dict, ticker: str) -> dict | None:
    """Translate EODHD fundamentals → the Schwab-compatible schema used everywhere."""
    if not isinstance(d, dict) or not d:
        return None
    H  = d.get("Highlights", {})  or {}
    V  = d.get("Valuation", {})   or {}
    T  = d.get("Technicals", {})  or {}
    SD = d.get("SplitsDividends", {}) or {}
    G  = d.get("General", {})     or {}

    # Compute gross margin from RevenueTTM and GrossProfitTTM if available
    gross_margin = None
    rev_ttm = H.get("RevenueTTM")
    gp_ttm  = H.get("GrossProfitTTM")
    if rev_ttm and gp_ttm and rev_ttm != 0:
        try: gross_margin = float(gp_ttm) / float(rev_ttm)
        except Exception: pass

    # EODHD QuarterlyRevenueGrowthYOY is a decimal (0.10 = 10%);
    # the existing Schwab schema returns it as percent (10.07).
    rev_q = H.get("QuarterlyRevenueGrowthYOY")
    rev_change_ttm = (rev_q * 100.0) if isinstance(rev_q, (int, float)) else None

    # EPS change% — use QuarterlyEarningsGrowthYOY when present (decimal → percent)
    eps_q = H.get("QuarterlyEarningsGrowthYOY")
    eps_change_pct_ttm = (eps_q * 100.0) if isinstance(eps_q, (int, float)) else None

    return {
        "pe":                  H.get("PERatio") or V.get("TrailingPE"),
        "peg":                 H.get("PEGRatio"),
        "pb":                  V.get("PriceBookMRQ"),
        "ps":                  V.get("PriceSalesTTM"),
        "pcf":                 None,                          # not in EODHD highlights
        "roe":                 H.get("ReturnOnEquityTTM"),
        "roa":                 H.get("ReturnOnAssetsTTM"),
        "roi":                 None,                          # derive from financials if needed
        "gross_margin":        gross_margin,
        "op_margin":           H.get("OperatingMarginTTM"),
        "net_margin":          H.get("ProfitMargin"),
        "quick_ratio":         None,                          # derive from balance sheet
        "current_ratio":       None,
        "interest_coverage":   None,
        "debt_equity":         None,                          # derive from balance sheet
        "lt_debt_equity":      None,
        "debt_to_capital":     None,
        "eps_ttm":             H.get("DilutedEpsTTM") or H.get("EarningsShare"),
        "eps_change_pct_ttm":  eps_change_pct_ttm,
        "eps_change_year":     None,
        "eps_change":          None,
        "rev_change_ttm":      rev_change_ttm,
        "dividend_yield":      H.get("DividendYield") or SD.get("ForwardAnnualDividendYield"),
        "dividend_amount":     SD.get("ForwardAnnualDividendRate"),
        "dividend_date":       SD.get("ExDividendDate"),
        "high_52w":            T.get("52WeekHigh"),
        "low_52w":             T.get("52WeekLow"),
        # Bonus fields downstream uses for sector/industry/short backfill
        "sector":              G.get("Sector"),
        "industry":            G.get("Industry"),
        # 2026-05-26 · EODHD nests MarketCapitalization under Highlights, not
        # General. The General fallback is kept defensively in case EODHD ever
        # surfaces it there.
        "market_cap":          H.get("MarketCapitalization") or G.get("MarketCapitalization"),
        "beta":                T.get("Beta"),
        "short_pct":           T.get("ShortPercent"),  # decimal: 0.0092 = 0.92%
        "country":             G.get("CountryName") or G.get("CountryISO"),
        "source":              "eodhd",
        "error":               None,
    }


def get_fundamentals(ticker: str) -> dict:
    """
    Fetch per-symbol fundamentals from EODHD.

    Returns a normalized dict — None for fields the source doesn't provide.
    Cached 7 days via @_with_enrichment_cache.
    """
    _EMPTY = {
        "pe": None, "peg": None, "pb": None, "ps": None, "pcf": None,
        "roe": None, "roa": None, "roi": None,
        "gross_margin": None, "op_margin": None, "net_margin": None,
        "quick_ratio": None, "current_ratio": None, "interest_coverage": None,
        "debt_equity": None, "lt_debt_equity": None, "debt_to_capital": None,
        "eps_ttm": None, "eps_change_pct_ttm": None,
        "eps_change_year": None, "eps_change": None,
        "rev_change_ttm": None,
        "dividend_yield": None, "dividend_amount": None, "dividend_date": None,
        "high_52w": None, "low_52w": None,
        "source": "none", "error": None,
    }

    try:
        import eodhd_client as _eod
        d = _eod.fundamentals(ticker)
        if isinstance(d, dict):
            mapped = _eodhd_fundamentals_to_schwab_schema(d, ticker)
            if mapped:
                return mapped
        return {**_EMPTY, "error": "eodhd_no_data"}
    except Exception as e:
        return {**_EMPTY, "error": f"eodhd: {e}"}


# ── FMP (Financial Modeling Prep) ────────────────────────────────────────────

def get_fmp_data(ticker: str) -> dict:
    """
    [DEPRECATED, kept as shim] FMP dropped 2026-04-24 — all fields now come
    from Schwab /instruments?projection=fundamental, which is redundant with
    FMP and has no rate limit. Shape preserved so downstream callers (which
    read keys like pe/ps/pb/roe/roa/gross_margin/debt_equity/current_ratio)
    keep working unchanged. Fields Schwab doesn't provide (ev_ebitda,
    fcf_yield, rev_per_sh, institutional_pct, eps_history, consensus,
    num_analysts) are returned as None/empty.
    """
    sf = get_schwab_fundamentals(ticker)
    return {
        # Mapped from Schwab
        "pe":            sf.get("pe"),
        "ps":            sf.get("ps"),
        "pb":            sf.get("pb"),
        "debt_equity":   sf.get("debt_equity"),
        "current_ratio": sf.get("current_ratio"),
        "roe":           sf.get("roe"),
        "roa":           sf.get("roa"),
        "gross_margin":  sf.get("gross_margin"),
        # Gaps Schwab doesn't cover — downstream already handles None
        "ev_ebitda":         None,
        "fcf_yield":         None,
        "rev_per_sh":        None,
        "market_cap":        None,
        "sector":            "",
        "industry":          "",
        "eps_history":       [],
        "consensus":         None,
        "num_analysts":      0,
        "institutional_pct": None,
        "source": "schwab-fund-shim",
        "error":  sf.get("error"),
    }


# ── Pre-market Volume ────────────────────────────────────────────────────────

@_mem_cached(ttl_seconds=900)
def get_premarket_volume(ticker: str) -> dict:
    """Detect unusual pre-market volume (4am–9:30am) vs 20-day average pre-market volume.

    Uses yfinance 1-minute data for today's pre-market session.
    Returns:
        premarket_vol: shares traded in pre-market today
        avg_premarket_vol: 20-day average pre-market volume
        vol_ratio: ratio of today vs average (>2 = unusual)
        unusual: bool (vol_ratio > 2)
        price_chg_pct: % price change in pre-market
    """
    cache_key = f"premarket_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=1800)  # 30-min cache
    if cached:
        return cached

    _empty = {"premarket_vol": 0, "avg_premarket_vol": 0, "vol_ratio": 1.0,
              "unusual": False, "price_chg_pct": 0.0}
    try:
        import pytz
        eastern = pytz.timezone("America/New_York")
        now_et = datetime.now(eastern)

        # Fetch 5-day 1-minute data (covers pre-market today + prior sessions)
        raw = yf.download(ticker, period="5d", interval="1m", progress=False,
                          auto_adjust=True, prepost=True)
        if raw.empty:
            return _empty

        close = raw["Close"].squeeze() if isinstance(raw["Close"], pd.DataFrame) else raw["Close"]
        vol   = raw["Volume"].squeeze() if isinstance(raw["Volume"], pd.DataFrame) else raw["Volume"]

        # Today's pre-market: 4:00am – 9:29am ET
        today_str = now_et.strftime("%Y-%m-%d")
        pm_start  = pd.Timestamp(f"{today_str} 04:00:00", tz=eastern)
        pm_end    = pd.Timestamp(f"{today_str} 09:29:00", tz=eastern)

        today_pm_mask = (raw.index >= pm_start) & (raw.index <= pm_end)
        today_pm_vol  = float(vol[today_pm_mask].sum()) if today_pm_mask.any() else 0
        today_pm_prices = close[today_pm_mask].dropna()
        pm_price_chg = 0.0
        if len(today_pm_prices) >= 2:
            pm_price_chg = round((float(today_pm_prices.iloc[-1]) - float(today_pm_prices.iloc[0]))
                                 / float(today_pm_prices.iloc[0]) * 100, 2)

        # 20-day average pre-market volume (prior trading days only)
        pm_vols_hist = []
        seen_dates = set()
        for ts, v in zip(raw.index, vol.values):
            try:
                ts_et = ts.astimezone(eastern) if ts.tzinfo else ts
                ds = ts_et.strftime("%Y-%m-%d")
                if ds == today_str or ds in seen_dates:
                    continue
                t_str = ts_et.strftime("%H:%M")
                if "04:00" <= t_str <= "09:29":
                    if ds not in seen_dates:
                        # accumulate per day
                        seen_dates.add(ds)
                        # collect vol for that day
                        day_mask = raw.index.normalize() == pd.Timestamp(ds)
                        pm_day_mask = day_mask & (raw.index.hour < 9) | (
                            day_mask & (raw.index.hour == 9) & (raw.index.minute < 30))
                        day_pm_vol = float(vol[pm_day_mask].sum()) if pm_day_mask.any() else 0
                        if day_pm_vol > 0:
                            pm_vols_hist.append(day_pm_vol)
            except Exception:
                continue

        avg_pm_vol = float(np.mean(pm_vols_hist)) if pm_vols_hist else 0
        vol_ratio  = round(today_pm_vol / avg_pm_vol, 2) if avg_pm_vol > 0 else 1.0
        unusual    = vol_ratio >= 2.0

        result = {
            "premarket_vol":     int(today_pm_vol),
            "avg_premarket_vol": int(avg_pm_vol),
            "vol_ratio":         vol_ratio,
            "unusual":           unusual,
            "price_chg_pct":     pm_price_chg,
        }
        _cache_write(cache_key, result)
        return result
    except Exception as e:
        log.debug(f"Pre-market volume {ticker}: {e}")
        return _empty


# ── Institutional Ownership Trend (13F proxy) ────────────────────────────────

@_mem_cached(ttl_seconds=3600)
def get_institutional_trend(ticker: str) -> dict:
    """Estimate institutional ownership trend from yfinance institutional holders data.

    Returns:
        inst_pct: current institutional ownership %
        inst_trend: "increasing" | "stable" | "decreasing"
        top_holders: list of top 5 holder names
        net_change_pct: estimated change in ownership % (positive = growing)
        total_holders: number of institutional holders
    """
    cache_key = f"inst_trend_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=86400)  # 24-hr cache (quarterly data)
    if cached:
        return cached

    _empty = {"inst_pct": None, "inst_trend": "unknown", "top_holders": [],
              "net_change_pct": 0, "total_holders": 0}
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info if hasattr(t, "fast_info") else {}

        # Current institutional holding %
        inst_pct = None
        try:
            inst_pct = getattr(info, "shares_percent_institutions", None)
            if inst_pct is None:
                full_info = t.info or {}
                inst_pct = full_info.get("heldPercentInstitutions")
        except Exception:
            pass

        # Institutional holders table — check for recent filings trend
        try:
            holders_df = t.institutional_holders
        except Exception:
            holders_df = None

        top_holders = []
        total_holders = 0
        net_change_pct = 0.0
        inst_trend = "stable"

        if holders_df is not None and not holders_df.empty:
            total_holders = len(holders_df)
            top_holders = list(holders_df.get("Holder", holders_df.iloc[:, 0]).head(5))

            # Estimate trend from % Out change column if available
            for col in holders_df.columns:
                if "change" in str(col).lower() or "pct" in str(col).lower():
                    try:
                        changes = holders_df[col].dropna().astype(float)
                        net_change_pct = round(float(changes.mean()) * 100, 2)
                        if net_change_pct > 1:
                            inst_trend = "increasing"
                        elif net_change_pct < -1:
                            inst_trend = "decreasing"
                        break
                    except Exception:
                        pass

        result = {
            "inst_pct":        round(float(inst_pct) * 100, 1) if inst_pct else None,
            "inst_trend":      inst_trend,
            "top_holders":     top_holders,
            "net_change_pct":  net_change_pct,
            "total_holders":   total_holders,
        }
        _cache_write(cache_key, result)
        return result
    except Exception as e:
        log.debug(f"Institutional trend {ticker}: {e}")
        return _empty


# ── Gamma Squeeze Probability ────────────────────────────────────────────────

@_mem_cached(ttl_seconds=1800)
@_with_enrichment_cache('gamma')
def get_gamma_squeeze_data(ticker: str) -> dict:
    """Compute gamma squeeze probability combining options OI and short interest.

    Gamma squeeze occurs when:
    1. Large OTM call open interest (dealers must delta-hedge by buying stock)
    2. High short float (shorts forced to cover as price rises)
    3. Low float (stock is easy to move)
    4. High RVOL (momentum already building)

    Returns:
        gamma_score: 0-100 score
        call_oi_skew: ratio of call OI to total OI
        short_float_pct: % of float sold short
        float_size: shares float in millions
        gamma_risk: "high" | "moderate" | "low"
    """
    cache_key = f"gamma_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=3600)
    if cached:
        return cached

    _empty = {"gamma_score": 0, "call_oi_skew": 0.5, "short_float_pct": 0,
              "float_size_m": 0, "gamma_risk": "low"}
    if yf_circuit_open():
        return _empty
    _t0 = time.time()
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        # Short interest
        short_float = float(info.get("shortPercentOfFloat") or info.get("short_pct") or 0)
        float_shares = float(info.get("floatShares") or 0)
        float_size_m = float_shares / 1_000_000 if float_shares > 0 else 0

        # Options chain — aggregate call vs put OI
        call_oi = put_oi = 0
        try:
            exp_dates = t.options[:3] if t.options else []  # first 3 expiries
            for exp in exp_dates:
                chain = t.option_chain(exp)
                call_oi += int(chain.calls["openInterest"].sum())
                put_oi  += int(chain.puts["openInterest"].sum())
        except Exception:
            pass

        total_oi = call_oi + put_oi
        call_oi_skew = round(call_oi / total_oi, 3) if total_oi > 0 else 0.5

        # Gamma score (0-100)
        score = 0
        # Short float component (max 40)
        if   short_float > 0.30: score += 40
        elif short_float > 0.20: score += 30
        elif short_float > 0.15: score += 20
        elif short_float > 0.10: score += 10

        # Call OI skew component (max 35)
        if   call_oi_skew > 0.75: score += 35
        elif call_oi_skew > 0.65: score += 25
        elif call_oi_skew > 0.55: score += 15

        # Low float multiplier (max 25)
        if   float_size_m < 20:  score += 25   # micro-float = extreme gamma risk
        elif float_size_m < 50:  score += 15
        elif float_size_m < 100: score += 8

        score = min(100, score)
        gamma_risk = "high" if score >= 65 else "moderate" if score >= 35 else "low"

        result = {
            "gamma_score":     score,
            "call_oi_skew":    call_oi_skew,
            "call_oi":         call_oi,
            "put_oi":          put_oi,
            "short_float_pct": round(short_float * 100, 1),
            "float_size_m":    round(float_size_m, 1),
            "gamma_risk":      gamma_risk,
        }
        _cache_write(cache_key, result)
        yf_record_call(time.time() - _t0, failed=False)
        return result
    except Exception as e:
        log.debug(f"Gamma squeeze {ticker}: {e}")
        yf_record_call(time.time() - _t0, failed=True)
        return _empty


# ── Earnings Estimate Trend (30-day consensus direction) ─────────────────────

@_mem_cached(ttl_seconds=3600)
def get_earnings_estimate_trend(ticker: str) -> dict:
    """Track the direction of analyst EPS estimate consensus over the past 30 days.

    Uses yfinance earnings estimate tables to compare current consensus
    vs ~30-day-prior consensus. A rising consensus is a strong bullish signal
    (PEAD tends to be stronger when estimates were revised upward pre-earnings).

    Returns:
        trend: "rising" | "falling" | "stable"
        current_eps_est: current consensus EPS estimate
        prior_eps_est: estimate 30 days ago (proxied from analyst revision counts)
        revision_direction: +1 rising, -1 falling, 0 stable
        surprise_history_mean: avg historical beat %
    """
    cache_key = f"eps_trend_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=86400)  # 24-hr cache
    if cached:
        return cached

    _empty = {"trend": "stable", "current_eps_est": None, "prior_eps_est": None,
              "revision_direction": 0, "surprise_history_mean": 0}

    # Phase 3: EODHD bulk calendar/trends pre-warmer. If we have a prewarmed
    # row for this ticker, build the dict directly without yfinance.
    bulk_rows = _BULK_TRENDS_CACHE.get(ticker.upper()) if _BULK_TRENDS_CACHE else None
    if bulk_rows:
        try:
            # pick the "+1q" (next quarter) row when available
            row = next((r for r in bulk_rows if r.get("period") == "+1q"), None) or bulk_rows[0]
            def _f(v):
                try: return float(v) if v not in (None, "", "null") else None
                except (TypeError, ValueError): return None
            current = _f(row.get("epsTrendCurrent") or row.get("earningsEstimateAvg"))
            prior   = _f(row.get("epsTrend30daysAgo"))
            up7   = int(_f(row.get("epsRevisionsUpLast7days")) or 0)
            up30  = int(_f(row.get("epsRevisionsUpLast30days")) or 0)
            down30= int(_f(row.get("epsRevisionsDownLast30days")) or 0)
            net = up30 - down30
            revision_direction = 1 if net > 1 else (-1 if net < -1 else 0)
            trend = ("rising" if revision_direction > 0 else
                     "falling" if revision_direction < 0 else "stable")
            res = {
                "trend": trend,
                "current_eps_est": current,
                "prior_eps_est": prior,
                "revision_direction": revision_direction,
                "surprise_history_mean": 0,
                "_source": "eodhd_bulk_trends",
            }
            _cache_write(cache_key, res)
            return res
        except Exception:
            pass  # fall through to yfinance

    if yf_circuit_open():
        return _empty
    _t0 = time.time()
    try:
        t = yf.Ticker(ticker)

        # Analyst earnings estimates (current quarter + next quarter)
        try:
            ests = t.earnings_estimate
        except Exception:
            ests = None

        current_eps_est = None
        if ests is not None and not ests.empty:
            try:
                # "0q" = current quarter row
                row = ests.loc["0q"] if "0q" in ests.index else ests.iloc[0]
                avg_col = [c for c in ests.columns if "avg" in str(c).lower()]
                if avg_col:
                    current_eps_est = float(row[avg_col[0]])
                elif len(ests.columns) >= 1:
                    current_eps_est = float(row.iloc[0])
            except Exception:
                pass

        # Earnings history — compute avg beat %
        surprise_history_mean = 0.0
        try:
            hist = t.earnings_history if hasattr(t, "earnings_history") else None
            if hist is None:
                hist = t.quarterly_earnings
            if hist is not None and not hist.empty:
                if "Surprise(%)" in hist.columns:
                    surp = hist["Surprise(%)"].dropna()
                elif "surprisePct" in hist.columns:
                    surp = hist["surprisePct"].dropna()
                else:
                    surp = pd.Series(dtype=float)
                if len(surp) >= 2:
                    surprise_history_mean = round(float(surp.head(4).mean()), 1)
        except Exception:
            pass

        # Estimate revision direction — use analyst upgrade/downgrade proxy from info
        info = t.info or {}
        upgrades_30d   = info.get("upgrades_30d",    info.get("upgrades_10d",   0) or 0)
        downgrades_30d = info.get("downgrades_30d", info.get("downgrades_10d", 0) or 0)

        if upgrades_30d > downgrades_30d:
            trend = "rising"
            revision_direction = 1
        elif downgrades_30d > upgrades_30d:
            trend = "falling"
            revision_direction = -1
        else:
            trend = "stable"
            revision_direction = 0

        # Cross-check: if surprise history is consistently positive, bias toward rising
        if surprise_history_mean > 5 and trend == "stable":
            trend = "rising"
            revision_direction = 1

        result = {
            "trend":                  trend,
            "current_eps_est":        current_eps_est,
            "revision_direction":     revision_direction,
            "surprise_history_mean":  surprise_history_mean,
        }
        _cache_write(cache_key, result)
        yf_record_call(time.time() - _t0, failed=False)
        return result
    except Exception as e:
        log.debug(f"EPS estimate trend {ticker}: {e}")
        yf_record_call(time.time() - _t0, failed=True)
        return _empty


# ── FINVIZ Elite ──────────────────────────────────────────────────────────────

_FINVIZ_BASE = "https://elite.finviz.com"
_FINVIZ_VIEWS = {
    "valuation":    121,   # EPS Growth This/Next Year, PEG, Forward P/E, P/S, P/B, P/C, P/FCF, Dividend Yield
    "ownership":    131,   # Shares Float, Short Float, Short Ratio, Insider Own, Institutional Own
    "performance":  141,   # Perf Week/Month/Quarter/Half/Year, Volatility, Avg Volume, Rel Volume
    "financial":    161,   # ROE, ROA, Gross/Operating/Profit Margin, Current Ratio, Earnings Date
    "technical":    171,   # Beta, ATR, RSI(14), 52W High/Low, SMA 20/50/200
}


def _finviz_token() -> str:
    try:
        from secrets_loader import finviz_token as _ft
        return _ft()
    except Exception:
        return load_config().get("data_sources", {}).get("finviz_token", "")


def _finviz_pct(val: str | None) -> float | None:
    """Parse FINVIZ percentage strings like '12.34%' or '-5.67%' → float or None."""
    if not val or val in ("-", "N/A", ""):
        return None
    try:
        return float(str(val).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _finviz_float(val: str | None) -> float | None:
    """Parse FINVIZ numeric strings like '1.23B', '456.78M', '12.34' → float or None."""
    if not val or val in ("-", "N/A", ""):
        return None
    s = str(val).replace(",", "").strip()
    try:
        if s.endswith("B"):
            return float(s[:-1]) * 1e9
        if s.endswith("M"):
            return float(s[:-1]) * 1e6
        if s.endswith("K"):
            return float(s[:-1]) * 1e3
        return float(s)
    except ValueError:
        return None


def get_finviz_bulk() -> dict[str, dict]:
    """
    Fetch FINVIZ Elite screener data for all S&P 500 + Nasdaq stocks in 5 parallel calls.
    Returns dict keyed by uppercase ticker → merged row from all views.
    Cache TTL: 4 hours (data is intraday-stable for our use case).

    Columns merged per ticker:
      valuation:   eps_growth_this_yr, eps_growth_next_yr, peg, fwd_pe, ps
      ownership:   shares_float, short_float_pct, short_ratio, insider_own_pct, inst_own_pct
      performance: rel_volume, avg_volume, perf_week_pct, perf_month_pct, volatility_w_pct
      financial:   roe_pct, roa_pct, gross_margin_pct, oper_margin_pct, profit_margin_pct,
                   current_ratio, earnings_date
      technical:   beta, atr, rsi14, high_52w, low_52w, sma20_pct, sma50_pct, sma200_pct
    """
    today = datetime.now().strftime("%Y%m%d")
    cache_key = f"finviz_bulk_{today}"
    cached = _cache_read(cache_key, ttl_seconds=4 * 3600)
    if cached:
        return cached

    token = _finviz_token()
    if not token:
        log.warning("FINVIZ: no token configured — skipping bulk fetch")
        return {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/csv,*/*",
        "Referer": "https://elite.finviz.com/screener.ashx",
    }

    def _fetch_view(view_id: int) -> pd.DataFrame | None:
        url = f"{_FINVIZ_BASE}/export.ashx"
        params = {"v": view_id, "auth": token}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code != 200:
                log.warning(f"FINVIZ view {view_id}: HTTP {r.status_code}")
                return None
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            if "Ticker" not in df.columns:
                log.warning(f"FINVIZ view {view_id}: no Ticker column")
                return None
            df["Ticker"] = df["Ticker"].str.upper().str.strip()
            return df.set_index("Ticker")
        except Exception as e:
            log.warning(f"FINVIZ view {view_id}: {e}")
            return None

    # Fetch all 5 views in parallel
    frames: dict[str, pd.DataFrame | None] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch_view, vid): name for name, vid in _FINVIZ_VIEWS.items()}
        for fut in as_completed(futs):
            name = futs[fut]
            frames[name] = fut.result()

    # Column mappings per view
    _col_map: dict[str, dict[str, str]] = {
        "valuation": {
            "EPS Growth This Year": "eps_growth_this_yr",
            "EPS Growth Next Year": "eps_growth_next_yr",
            "PEG":                  "peg",
            "Forward P/E":          "fwd_pe",
            "P/S":                  "ps",
        },
        "ownership": {
            "Shares Float":          "shares_float",
            "Short Float":           "short_float_pct",
            "Short Ratio":           "short_ratio",
            "Insider Ownership":     "insider_own_pct",
            "Institutional Ownership": "inst_own_pct",
        },
        "performance": {
            "Relative Volume":         "rel_volume",
            "Average Volume":          "avg_volume",
            "Performance (Week)":      "perf_week_pct",
            "Performance (Month)":     "perf_month_pct",
            "Performance (Quarter)":   "perf_quarter_pct",
            "Performance (Half Year)": "perf_half_pct",
            "Performance (Year)":      "perf_year_pct",
            "Performance (YTD)":       "perf_ytd_pct",
            "Volatility (Week)":       "volatility_w_pct",
            "Change":                  "change_pct",
            "Gap":                     "gap_pct",
        },
        "financial": {
            "Return on Equity":      "roe_pct",
            "Return on Assets":      "roa_pct",
            "Gross Margin":          "gross_margin_pct",
            "Operating Margin":      "oper_margin_pct",
            "Profit Margin":         "profit_margin_pct",
            "Current Ratio":         "current_ratio",
            "Earnings Date":         "earnings_date",
        },
        "technical": {
            "Beta":                  "beta",
            "Average True Range":    "atr",
            "Relative Strength Index (14)": "rsi14",
            "52-Week High":          "high_52w",
            "52-Week Low":           "low_52w",
            "20-Day Simple Moving Average": "sma20_pct",
            "50-Day Simple Moving Average": "sma50_pct",
            "200-Day Simple Moving Average": "sma200_pct",
        },
    }

    # Merge all views into one dict keyed by ticker
    merged: dict[str, dict] = {}
    for view_name, df in frames.items():
        if df is None:
            continue
        col_map = _col_map.get(view_name, {})
        for ticker, row in df.iterrows():
            if ticker not in merged:
                merged[ticker] = {}
            for src_col, dst_col in col_map.items():
                # Try exact column name first; FINVIZ may add spaces
                val = row.get(src_col)
                if val is None:
                    # Try case-insensitive partial match
                    for c in df.columns:
                        if src_col.lower() in c.lower():
                            val = row.get(c)
                            break
                if val is not None and str(val).strip() not in ("-", "N/A", ""):
                    merged[ticker][dst_col] = str(val).strip()

    # Parse numeric types
    pct_fields = {
        "eps_growth_this_yr", "eps_growth_next_yr", "short_float_pct",
        "insider_own_pct", "inst_own_pct", "perf_week_pct", "perf_month_pct",
        "perf_quarter_pct", "perf_half_pct", "perf_year_pct", "perf_ytd_pct",
        "change_pct", "gap_pct",
        "volatility_w_pct", "roe_pct", "roa_pct", "gross_margin_pct",
        "oper_margin_pct", "profit_margin_pct", "sma20_pct", "sma50_pct", "sma200_pct",
    }
    float_fields = {
        "peg", "fwd_pe", "ps", "shares_float", "short_ratio", "rel_volume",
        "avg_volume", "current_ratio", "beta", "atr", "rsi14", "high_52w", "low_52w",
    }
    for ticker, data in merged.items():
        for f in pct_fields:
            if f in data:
                data[f] = _finviz_pct(data[f])
        for f in float_fields:
            if f in data:
                data[f] = _finviz_float(data[f])

    if merged:
        _cache_write(cache_key, merged)
        log.info(f"FINVIZ bulk: fetched {len(merged)} tickers across {len(frames)} views")
    return merged


def get_finviz_news() -> list[dict]:
    """
    Fetch latest market news from FINVIZ Elite news export.
    Returns list of dicts with keys: title, source, date, url, category.
    Cache TTL: 30 minutes.
    """
    cache_key = "finviz_news"
    cached = _cache_read(cache_key, ttl_seconds=1800)
    if cached:
        return cached

    token = _finviz_token()
    if not token:
        return []

    try:
        url = f"{_FINVIZ_BASE}/news_export.ashx"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://elite.finviz.com/news.ashx",
        }
        r = requests.get(url, params={"v": 1, "auth": token}, headers=headers, timeout=15)
        if r.status_code != 200:
            log.warning(f"FINVIZ news: HTTP {r.status_code}")
            return []

        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        articles = []
        for _, row in df.iterrows():
            articles.append({
                "title":    str(row.get("Title", "")),
                "source":   str(row.get("Source", "")),
                "date":     str(row.get("Date", "")),
                "url":      str(row.get("Url", "")),
                "category": str(row.get("Category", "")),
            })
        _cache_write(cache_key, articles)
        log.info(f"FINVIZ news: fetched {len(articles)} articles")
        return articles
    except Exception as e:
        log.warning(f"FINVIZ news: {e}")
        return []


# [removed 2026-04-25] _legacy_get_schwab_options — Schwab decommissioned
# [removed 2026-04-29] get_schwab_options — was an empty stub, callers now skip it


def get_finviz_options(ticker: str, expiry: str) -> dict:
    """
    Fetch options chain from FINVIZ Elite for a given ticker and expiry.
    expiry format: 'YYYY-MM-DD'
    Returns: {"calls": [...], "puts": [...]} each item has strike, iv, delta, gamma, theta, vega, oi, volume.
    """
    cache_key = f"finviz_opts_{ticker}_{expiry}"
    cached = _cache_read(cache_key, ttl_seconds=3600)
    if cached:
        return cached

    token = _finviz_token()
    if not token:
        return {"calls": [], "puts": []}

    try:
        url = f"{_FINVIZ_BASE}/export/options"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": f"https://elite.finviz.com/quote.ashx?t={ticker}",
        }
        r = requests.get(url, params={"t": ticker, "ty": "oc", "e": expiry, "auth": token},
                         headers=headers, timeout=15)
        if r.status_code != 200:
            log.warning(f"FINVIZ options {ticker} {expiry}: HTTP {r.status_code}")
            return {"calls": [], "puts": []}

        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        if df.empty:
            return {"calls": [], "puts": []}

        def _parse_chain(side: str) -> list[dict]:
            sub = df[df.get("Type", pd.Series()).str.upper() == side.upper()] if "Type" in df.columns else df
            out = []
            for _, row in sub.iterrows():
                out.append({
                    "strike":  _finviz_float(str(row.get("Strike", ""))),
                    "iv":      _finviz_pct(str(row.get("Implied Volatility", ""))),
                    "delta":   _finviz_float(str(row.get("Delta", ""))),
                    "gamma":   _finviz_float(str(row.get("Gamma", ""))),
                    "theta":   _finviz_float(str(row.get("Theta", ""))),
                    "vega":    _finviz_float(str(row.get("Vega", ""))),
                    "oi":      _finviz_float(str(row.get("Open Interest", ""))),
                    "volume":  _finviz_float(str(row.get("Volume", ""))),
                })
            return out

        result = {"calls": _parse_chain("call"), "puts": _parse_chain("put")}
        _cache_write(cache_key, result)
        return result
    except Exception as e:
        log.warning(f"FINVIZ options {ticker}: {e}")
        return {"calls": [], "puts": []}


def get_finviz_quote(ticker: str) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV history from FINVIZ Elite as a yfinance-compatible DataFrame.
    Returns DataFrame with columns [Open, High, Low, Close, Volume] indexed by Date,
    or None on failure. Can be used as fallback if yfinance is unavailable.
    Cache TTL: 24 hours.
    """
    cache_key = f"finviz_quote_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=86400)
    if cached:
        try:
            df = pd.DataFrame(cached)
            df["Date"] = pd.to_datetime(df["Date"])
            return df.set_index("Date")
        except Exception:
            pass

    token = _finviz_token()
    if not token:
        return None

    try:
        url = f"{_FINVIZ_BASE}/quote_export.ashx"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": f"https://elite.finviz.com/quote.ashx?t={ticker}",
        }
        r = requests.get(url, params={"t": ticker, "p": "d", "auth": token},
                         headers=headers, timeout=15)
        if r.status_code != 200:
            log.warning(f"FINVIZ quote {ticker}: HTTP {r.status_code}")
            return None

        from io import StringIO
        df = pd.read_csv(StringIO(r.text), parse_dates=["Date"])
        if df.empty or "Close" not in df.columns:
            return None

        df = df.sort_values("Date").set_index("Date")
        # Cache as serializable list of records
        _cache_write(cache_key, df.reset_index().assign(Date=df.reset_index()["Date"].astype(str)).to_dict("records"))
        return df
    except Exception as e:
        log.warning(f"FINVIZ quote {ticker}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# POLYGON.IO INTEGRATION
# REST API key stored in config["data_sources"]["polygon_api_key"]
# ═══════════════════════════════════════════════════════════════════════════════

# Polygon decommissioned 2026-04-25, dead code removed 2026-05-02.
# `_POLYGON_BASE`, `_polygon_key`, `_polygon_get` deleted — `get_polygon_*`
# function-name aliases (e.g., `get_polygon_news = get_news_articles`) retained
# elsewhere in this file for legacy callers but route to EODHD.

_FAILOVER_COUNTS = {"eodhd": 0, "archive": 0, "yfinance": 0, "failed": 0}


def get_polygon_ohlcv(ticker, days=400, timespan="day", **kwargs):
    """Back-compat shim for callers (backtest.py) that pre-date the EODHD migration.
    Routes to fetch_ohlcv_with_failover and returns just the dataframe.
    timespan param is accepted but ignored (we only do daily)."""
    df, _tier = fetch_ohlcv_with_failover(ticker, days=days)
    return df


def failover_counts() -> dict:
    """Return the current vendor-failover counters (reset via reset_failover_counts())."""
    return dict(_FAILOVER_COUNTS)


def reset_failover_counts() -> None:
    for k in _FAILOVER_COUNTS:
        _FAILOVER_COUNTS[k] = 0


def fetch_ohlcv_with_failover(ticker: str, days: int = 400) -> tuple[pd.DataFrame | None, str]:
    """Vendor failover chain — EODHD → Schwab pricehistory → archive → failed.

    Returns (df, tier_used). tier ∈ {"eodhd","schwab","archive","failed"}.
    Updates module-level _FAILOVER_COUNTS for end-of-scan summary.

    2026-05-19 · Added Schwab pricehistory as 2nd-tier (between EODHD and
    archive). Prevents the 30% scan-fill abort when EODHD rate-limits — Schwab
    has a separate budget (Market Data app) and gives us a 2nd live source.
    """
    import datetime as _dt
    now = _dt.datetime.utcnow()
    from_date = (now - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    # 1) EODHD (primary) — skipped in degraded mode to avoid cascading network errors
    if not _DEGRADED_MODE:
        try:
            import eodhd_client as _eod
            bars = _eod.eod(ticker, from_date=from_date, to_date=to_date, period="d")
            if bars and len(bars) >= 20:
                df = pd.DataFrame(bars)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                df = df.rename(columns={
                    "open": "Open", "high": "High", "low": "Low",
                    "close": "Close", "adjusted_close": "Adj Close", "volume": "Volume",
                })
                _FAILOVER_COUNTS["eodhd"] += 1
                return df, "eodhd"
        except Exception as e:
            log.debug(f"[failover] {ticker}: eodhd error — {e}")
    else:
        log.debug(f"[failover] {ticker}: skipping eodhd (degraded mode)")

    # 2) Schwab pricehistory (2nd-tier live source — separate API budget from EODHD)
    try:
        import schwab_client as _sc
        # Pull ~ceil(days/365) years of daily candles
        years = max(1, (days // 365) + (1 if days % 365 else 0))
        ph = _sc.get_pricehistory(ticker, period_type="year", period=years,
                                   frequency_type="daily", frequency=1)
        if ph and ph.get("candles"):
            df = _sc.pricehistory_to_df(ph)
            if df is not None and len(df) >= 20:
                # Trim to requested window
                cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)
                df_index_naive = df.index.tz_convert(None) if df.index.tz is not None else df.index
                df = df.loc[df_index_naive >= cutoff]
                if len(df) >= 20:
                    _FAILOVER_COUNTS["schwab"] = _FAILOVER_COUNTS.get("schwab", 0) + 1
                    log.info(f"  [failover] {ticker}: schwab pricehistory (eodhd failed)")
                    return df, "schwab"
    except Exception as e:
        log.debug(f"[failover] {ticker}: schwab pricehistory error — {e}")

    # 3) Archive (local parquet) — last-resort fallback (may be 1+ day stale)
    try:
        archive_path = BASE_DIR / "data" / "ohlcv" / f"{ticker}.parquet"
        if archive_path.exists():
            df = pd.read_parquet(archive_path)
            if df is not None and len(df) >= 20:
                _FAILOVER_COUNTS["archive"] += 1
                log.info(f"  [failover] {ticker}: archive fallback (eodhd+schwab failed)")
                return df, "archive"
    except Exception as e:
        log.debug(f"[failover] {ticker}: archive error — {e}")

    _FAILOVER_COUNTS["failed"] += 1
    return None, "failed"


def get_news_articles(ticker: str, limit: int = 10) -> list[dict]:
    """
    Recent news + sentiment for a ticker.
    Primary: EODHD news API.
    Fallback: yfinance Ticker(ticker).news (when EODHD rate-limits or returns empty).
    Returns list of {title, source, published_utc, url, publisher, insights}.
    Cache TTL · conditional (2026-05-15):
      • 4 hours during RTH  (Mon-Fri 06:30 AM – 1:00 PM PT)
      • 12 hours outside RTH (overnight + weekends — near-zero new-article rate)
    Saves ~1500 EODHD calls/day on the same news that wouldn't change anyway.
    """
    import zoneinfo as _zi
    from datetime import datetime as _dtn
    _now = _dtn.now(_zi.ZoneInfo("America/Los_Angeles"))
    _is_weekend = _now.weekday() >= 5
    _mins = _now.hour * 60 + _now.minute
    _in_rth = (not _is_weekend) and (6*60+30) <= _mins <= (13*60)
    NEWS_CACHE_TTL = 14400 if _in_rth else 43200  # 4h RTH / 12h outside
    cache_key = f"news_{ticker}_{int(time.time()//NEWS_CACHE_TTL)}"
    cached = _cache_read(cache_key, NEWS_CACHE_TTL)
    if cached is not None:
        return cached

    articles: list[dict] = []
    eodhd_failed = False

    # ── PRIMARY: EODHD ──
    try:
        import eodhd_client as _eod
        rows = _eod.news(ticker=ticker, limit=limit)
        if isinstance(rows, list):
            for a in rows:
                sent = a.get("sentiment") or {}
                pol  = sent.get("polarity") if isinstance(sent, dict) else None
                insights = []
                if pol is not None:
                    label = "positive" if pol > 0.15 else ("negative" if pol < -0.15 else "neutral")
                    insights.append({"sentiment": label, "ticker": ticker,
                                     "sentiment_reasoning": sent})
                articles.append({
                    "title":         a.get("title", ""),
                    "source":        a.get("source", ""),
                    "published_utc": a.get("date", ""),
                    "url":           a.get("link", ""),
                    "publisher":     {"name": a.get("source", "")},
                    "insights":      insights,
                    "_provider":     "eodhd",
                })
    except Exception as e:
        eodhd_failed = True
        # 402 = rate limit; downgrade to debug to avoid log spam during quota burn
        is_rate_limit = "402" in str(e)
        log.debug(f"EODHD news({ticker}) failed{' [RATE LIMIT]' if is_rate_limit else ''}: {e}")

    # ── FALLBACK: yfinance ── (when EODHD failed OR returned no articles)
    if not articles and _YF_AVAILABLE:
        try:
            yf_news = yf.Ticker(ticker).news or []
            from datetime import datetime as _dtt, timezone as _tzz
            for n in yf_news[:limit]:
                # yfinance shape: {uuid, title, publisher, link, providerPublishTime, type, ...}
                # Newer yfinance (>=0.2.50) wraps in {'content': {...}} — handle both
                content = n.get("content") if isinstance(n.get("content"), dict) else n
                title = content.get("title") or n.get("title") or ""
                pub_name = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else (n.get("publisher") or "")
                url = (content.get("canonicalUrl", {}) or {}).get("url") or n.get("link") or ""
                pub_time = n.get("providerPublishTime") or content.get("pubDate")
                ts_str = ""
                if isinstance(pub_time, (int, float)):
                    ts_str = _dtt.fromtimestamp(pub_time, tz=_tzz.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                elif isinstance(pub_time, str):
                    ts_str = pub_time
                # Yahoo doesn't provide sentiment — leave insights empty so frontend shows neutral
                articles.append({
                    "title":         title,
                    "source":        pub_name,
                    "published_utc": ts_str,
                    "url":           url,
                    "publisher":     {"name": pub_name},
                    "insights":      [],
                    "_provider":     "yahoo",
                })
            if articles:
                log.info(f"  Yahoo fallback used for {ticker}: {len(articles)} articles (EODHD {'rate-limited' if eodhd_failed else 'returned 0'})")
        except Exception as ye:
            log.debug(f"Yahoo news fallback failed for {ticker}: {ye}")

    _cache_write(cache_key, articles)
    return articles


def get_news_articles_legacy(ticker: str, limit: int = 10) -> list[dict]:
    """Legacy 30-min wrapper kept for any caller that explicitly wants short cache."""
    return get_news_articles(ticker, limit)


# 2026-05-08 cleanup: removed get_polygon_technicals + get_polygon_multi_timeframe.
# Both relied on _polygon_get (deleted 2026-04-25 in EODHD migration) and had zero
# callers — the indicator functions live in analysis.py, MTF charts source from
# get_polygon_ohlcv shim → fetch_ohlcv_with_failover → EODHD.

# ── Backward-compat aliases (renamed 2026-04-29; old names kept for callers) ──
# get_schwab_fundamentals → get_fundamentals (Schwab decommissioned, body uses EODHD)
# get_polygon_news        → get_news_articles (Polygon decommissioned, body uses EODHD)
get_schwab_fundamentals = get_fundamentals
get_polygon_news        = get_news_articles


def get_earnings_implied_move(ticker: str, report_date: str) -> dict:
    """
    Compute implied move ±% from the Schwab ATM straddle on the first
    expiry strictly after `report_date`. Earnings-event-specific — answers
    "what % move is the market pricing in for THIS print."

    Logic:
      1. Pull chain (CALL+PUT, 20 strikes each side, include underlying).
      2. Find first expiry date that is > report_date.
      3. Find strike closest to spot (ATM).
      4. Compute straddle = ATM_call_mid + ATM_put_mid.
      5. Implied move % = straddle / spot * 100.

    Returns:
      {
        "implied_move_pct": float | None,   # ±% market-priced move
        "straddle_cost":    float | None,   # $ premium of ATM straddle
        "atm_strike":       float | None,
        "expiry_date":      str | None,     # 'YYYY-MM-DD'
        "spot":             float | None,
        "source":           "schwab" | "unavailable",
        "error":            str | None,
      }

    Cached 2h. Bails cleanly on missing Schwab credentials. No exceptions
    propagate to callers — failure modes return None fields + error string.
    """
    out = {"implied_move_pct": None, "straddle_cost": None,
           "atm_strike": None, "expiry_date": None, "spot": None,
           "source": "unavailable", "error": None}

    # Lazy-load .env for parity with get_options_iv_data
    if not os.environ.get("SCHWAB_APP_KEY"):
        try:
            from pathlib import Path as _Path
            _env_path = _Path(__file__).resolve().parent / ".env"
            if _env_path.exists():
                for _line in _env_path.read_text().splitlines():
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        except Exception:
            pass

    if not (os.environ.get("SCHWAB_APP_KEY") and os.environ.get("SCHWAB_REFRESH_TOKEN")):
        return out

    cache_key = f"impl_move_{ticker}_{report_date}_{int(time.time()//7200)}"
    cached = _cache_read(cache_key, 7200)
    if cached is not None:
        return cached

    out["source"] = "schwab"

    try:
        import schwab_client as sc
        ch = sc.get_chains(ticker, contract_type="ALL", strike_count=20,
                           include_underlying=True)
        if not isinstance(ch, dict) or ch.get("status") != "SUCCESS":
            out["error"] = f"chain status={ch.get('status') if isinstance(ch, dict) else 'no-data'}"
            _cache_write(cache_key, out); return out

        underlying = ch.get("underlying", {}) or {}
        spot = underlying.get("last") or underlying.get("mark") or underlying.get("close")
        if not spot:
            out["error"] = "no spot price"
            _cache_write(cache_key, out); return out
        try: spot = float(spot)
        except (TypeError, ValueError):
            out["error"] = "spot not numeric"
            _cache_write(cache_key, out); return out

        call_map = ch.get("callExpDateMap", {}) or {}
        put_map  = ch.get("putExpDateMap", {}) or {}

        # Find first expiry strictly after report_date.
        # Schwab keys look like "2026-05-16:5" (date:days-to-expiry).
        from datetime import date as _date
        try:
            rd = _date.fromisoformat(report_date)
        except (TypeError, ValueError):
            out["error"] = f"bad report_date={report_date}"
            _cache_write(cache_key, out); return out

        def _parse_exp(k: str):
            try: return _date.fromisoformat(k.split(":")[0])
            except Exception: return None

        candidate_exps = sorted(
            [k for k in call_map.keys()
             if _parse_exp(k) is not None and _parse_exp(k) > rd],
            key=lambda k: _parse_exp(k)
        )
        if not candidate_exps:
            out["error"] = "no expiry after report_date"
            _cache_write(cache_key, out); return out

        chosen_exp_key = candidate_exps[0]
        exp_date = _parse_exp(chosen_exp_key)

        call_strikes = call_map.get(chosen_exp_key, {}) or {}
        put_strikes  = put_map.get(chosen_exp_key,  {}) or {}

        if not call_strikes or not put_strikes:
            out["error"] = f"missing strikes for {chosen_exp_key}"
            _cache_write(cache_key, out); return out

        # Find ATM — closest strike to spot in both maps
        def _closest_strike(strikes_dict, target):
            best = None; best_diff = None
            for k_str in strikes_dict.keys():
                try: k = float(k_str)
                except (TypeError, ValueError): continue
                diff = abs(k - target)
                if best_diff is None or diff < best_diff:
                    best, best_diff = k, diff
            return best

        atm = _closest_strike(call_strikes, spot)
        if atm is None or _closest_strike(put_strikes, spot) != atm:
            atm = _closest_strike(call_strikes, spot)
        if atm is None:
            out["error"] = "no ATM strike"
            _cache_write(cache_key, out); return out

        atm_str_c = f"{atm:.1f}" if f"{atm:.1f}" in call_strikes else f"{atm:.2f}" if f"{atm:.2f}" in call_strikes else str(atm)
        atm_str_p = f"{atm:.1f}" if f"{atm:.1f}" in put_strikes else f"{atm:.2f}" if f"{atm:.2f}" in put_strikes else str(atm)
        # Schwab keys can be either "150.0" or "150.00" — try common formats
        for fmt in ("{:.1f}", "{:.2f}", "{:g}", "{:.0f}"):
            kc = fmt.format(atm)
            if kc in call_strikes: atm_str_c = kc; break
        for fmt in ("{:.1f}", "{:.2f}", "{:g}", "{:.0f}"):
            kp = fmt.format(atm)
            if kp in put_strikes: atm_str_p = kp; break

        call_contracts = call_strikes.get(atm_str_c) or []
        put_contracts  = put_strikes.get(atm_str_p)  or []
        if not call_contracts or not put_contracts:
            out["error"] = f"no contracts at ATM {atm}"
            _cache_write(cache_key, out); return out

        cc = call_contracts[0]; pc = put_contracts[0]
        def _mid(c):
            bid = c.get("bid"); ask = c.get("ask")
            mark = c.get("mark") or c.get("last")
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                return (float(bid) + float(ask)) / 2.0
            if mark is not None:
                try: return float(mark)
                except (TypeError, ValueError): return None
            return None

        c_mid = _mid(cc); p_mid = _mid(pc)
        if c_mid is None or p_mid is None or c_mid <= 0 or p_mid <= 0:
            out["error"] = "no mid prices"
            _cache_write(cache_key, out); return out

        straddle = c_mid + p_mid
        impl_pct = (straddle / spot) * 100.0

        out["implied_move_pct"] = round(impl_pct, 2)
        out["straddle_cost"]    = round(straddle, 2)
        out["atm_strike"]       = atm
        out["expiry_date"]      = exp_date.isoformat()
        out["spot"]             = round(spot, 2)

    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"

    _cache_write(cache_key, out)
    return out
