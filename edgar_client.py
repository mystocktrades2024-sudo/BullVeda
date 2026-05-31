"""
edgar_client.py — SEC EDGAR XBRL companyfacts client.

POINT-IN-TIME financial-statement fundamentals (free) for SwingTrade.
Fixes audit #1 (survivorship) and audit #4 (fundamental look-ahead) by sourcing
financial STATEMENTS directly from SEC filings, with a filing-date guard so
backtests can query "what was known as of date D" with no look-ahead.

HARD SCOPE: EDGAR covers financial STATEMENTS ONLY. This module populates ONLY
these fundamentals.db columns:
    revenue_ttm, revenue_growth, eps_ttm, eps_growth_qoq  (+ source, fetched_at)
It does NOT touch market-derived columns (market_cap, beta, pe_ttm, forward_pe,
week52_high/low, shares_out) — those stay EODHD-sourced. Additive only.

Module shape mirrors eodhd_client.py:
  - cik_for(ticker)
  - companyfacts(ticker, cache_ttl=...)        — fetch + disk-cache (DAYS)
  - statements(ticker)                          — latest TTM/YoY/QoQ derived values
  - fundamentals_as_of(ticker, as_of_date)      — POINT-IN-TIME (backtest, no look-ahead)

SEC requires a descriptive User-Agent with contact email and <=10 req/sec.
All errors / missing CIK / no facts → return None. Never throws.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("swingtrade.edgar")

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
_CIK_MAP_PATH = BASE_DIR / "cache" / "_cache_sec_cik_map.json"
_CACHE_DIR = BASE_DIR / "cache" / "edgar"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# SEC requires a descriptive UA with contact email. Throttle to <=10 req/sec.
USER_AGENT = "SwingTrade research garimella.phaniraj@gmail.com"
_THROTTLE_SEC = 0.15  # ~6-7 req/sec, well under SEC's 10/sec ceiling
DEFAULT_TIMEOUT = 30

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# XBRL tag fallback chains (first available wins) ─────────────────────────────
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
]
NET_INCOME_TAGS = ["NetIncomeLoss"]
EPS_TAGS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
# Balance-sheet tags (pulled for margins/balance-sheet even if not all written yet)
ASSETS_TAGS = ["Assets"]
LIABILITIES_TAGS = ["Liabilities"]
EQUITY_TAGS = ["StockholdersEquity"]
CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue"]
LTDEBT_TAGS = ["LongTermDebtNoncurrent"]

# ── Throttle (global, thread-safe) ────────────────────────────────────────────
_throttle_lock = threading.Lock()
_last_request_ts = [0.0]

# In-process CIK map cache
_cik_map: Optional[dict] = None
_cik_map_lock = threading.Lock()


def _throttled_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """GET with SEC User-Agent + global throttle. Returns bytes or None on error."""
    with _throttle_lock:
        elapsed = time.time() - _last_request_ts[0]
        if elapsed < _THROTTLE_SEC:
            time.sleep(_THROTTLE_SEC - elapsed)
        _last_request_ts[0] = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        log.debug("edgar GET failed %s: %s", url, e)
        return None


def _load_cik_map() -> dict:
    """Load the cached CIK map {TICKER: '0001045810'} (zero-padded)."""
    global _cik_map
    with _cik_map_lock:
        if _cik_map is not None:
            return _cik_map
        try:
            _cik_map = json.loads(_CIK_MAP_PATH.read_text())
        except Exception:
            _cik_map = {}
        return _cik_map


def _refresh_cik_for(ticker: str) -> Optional[str]:
    """Ticker missing from cached map → pull the live SEC company_tickers map once."""
    raw = _throttled_get(COMPANY_TICKERS_URL)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    global _cik_map
    found = None
    with _cik_map_lock:
        m = _cik_map if _cik_map is not None else {}
        for entry in data.values():
            t = (entry.get("ticker") or "").upper().strip()
            cik = entry.get("cik_str")
            if not t or cik is None:
                continue
            padded = str(cik).zfill(10)
            m[t] = padded
            if t == ticker.upper().strip():
                found = padded
        _cik_map = m
    # Best-effort persist the enriched map back to disk
    try:
        _CIK_MAP_PATH.write_text(json.dumps(m))
    except Exception:
        pass
    return found


def cik_for(ticker: str) -> Optional[str]:
    """Return zero-padded 10-digit CIK for ticker, or None. Refreshes if missing."""
    if not ticker:
        return None
    key = ticker.upper().strip()
    m = _load_cik_map()
    cik = m.get(key)
    if cik:
        return str(cik).zfill(10)
    # Missing — try one live refresh
    return _refresh_cik_for(key)


# ── companyfacts (disk-cached for DAYS) ───────────────────────────────────────
def _cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"companyfacts_{ticker.upper().strip()}.json"


def companyfacts(ticker: str, cache_ttl: int = 86400 * 3) -> Optional[dict]:
    """
    Fetch SEC XBRL companyfacts JSON for ticker, disk-cached for cache_ttl seconds
    (default 3 days — SEC data changes only quarterly). Returns parsed JSON or None.
    """
    cik = cik_for(ticker)
    if not cik:
        return None
    fp = _cache_path(ticker)
    # Serve from cache if fresh
    if fp.exists():
        try:
            if time.time() - fp.stat().st_mtime <= cache_ttl:
                return json.loads(fp.read_text())
        except Exception:
            pass
    url = COMPANYFACTS_URL.format(cik=cik)
    raw = _throttled_get(url)
    if not raw:
        # Fall back to a stale cache copy if a fetch fails (better than nothing)
        if fp.exists():
            try:
                return json.loads(fp.read_text())
            except Exception:
                return None
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    try:
        fp.write_text(json.dumps(data))
    except Exception:
        pass
    return data


# ── statement extraction helpers ──────────────────────────────────────────────
def _facts_for_tags(facts: dict, tags: list[str], unit: str) -> list[dict]:
    """Return the raw fact list for the first tag in `tags` that has data under `unit`."""
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    for tag in tags:
        node = us_gaap.get(tag)
        if not node:
            continue
        units = node.get("units") or {}
        series = units.get(unit)
        if series:
            return series
    return []


def _best_flow_series(facts: dict, tags: list[str], unit: str,
                      want_quarterly: bool) -> list[dict]:
    """
    Pick the BEST tag in the fallback chain for a flow metric.

    A naive "first tag with any data" is wrong: a company can carry a stale tag
    (e.g. AAPL's legacy `Revenues`, last filed 2018) alongside its current tag
    (`RevenueFromContractWithCustomerExcludingAssessedTax`). We clean each tag's
    series and choose the one whose most-recent period `end` is latest — i.e. the
    tag the company actually reports under today.
    """
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    best: list[dict] = []
    best_end = ""
    for tag in tags:
        node = us_gaap.get(tag)
        if not node:
            continue
        series = (node.get("units") or {}).get(unit)
        if not series:
            continue
        cleaned = _clean_period_facts(series, want_quarterly=want_quarterly)
        if not cleaned:
            continue
        latest_end = cleaned[-1]["end"]
        if latest_end > best_end:
            best, best_end = cleaned, latest_end
    return best


def _clean_period_facts(series: list[dict], want_quarterly: bool) -> list[dict]:
    """
    Filter a raw XBRL fact series to usable, deduped period observations.

    want_quarterly=True  → ~quarterly durations (10-Q, 60-100 day spans)
    want_quarterly=False → ~annual durations (10-K, 330-400 day spans)

    Each returned row: {start, end, val, fy, fp, form, filed}. Deduped by `end`,
    keeping the most recently `filed` value (handles restatements/amendments).
    """
    by_end: dict[str, dict] = {}
    for f in series:
        end = f.get("end")
        val = f.get("val")
        filed = f.get("filed")
        form = f.get("form") or ""
        if end is None or val is None or filed is None:
            continue
        start = f.get("start")
        # Flow facts (revenue, NI, EPS) have a start→end duration; filter by span.
        if start:
            try:
                d0 = datetime.strptime(start, "%Y-%m-%d").date()
                d1 = datetime.strptime(end, "%Y-%m-%d").date()
                span = (d1 - d0).days
            except Exception:
                continue
            if want_quarterly and not (55 <= span <= 110):
                continue
            if (not want_quarterly) and not (330 <= span <= 400):
                continue
        # 10-K / 10-Q only (and their amendments); skip 8-K segment snippets etc.
        if form not in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            continue
        prev = by_end.get(end)
        if prev is None or filed > prev.get("filed", ""):
            by_end[end] = {
                "start": start, "end": end, "val": val,
                "fy": f.get("fy"), "fp": f.get("fp"),
                "form": form, "filed": filed,
            }
    return sorted(by_end.values(), key=lambda r: r["end"])


def _instant_facts(series: list[dict]) -> list[dict]:
    """Balance-sheet (instant) facts: deduped by `end`, latest `filed` wins."""
    by_end: dict[str, dict] = {}
    for f in series:
        end = f.get("end")
        val = f.get("val")
        filed = f.get("filed")
        form = f.get("form") or ""
        if end is None or val is None or filed is None:
            continue
        if form not in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            continue
        prev = by_end.get(end)
        if prev is None or filed > prev.get("filed", ""):
            by_end[end] = {"end": end, "val": val, "form": form,
                           "filed": filed, "fy": f.get("fy"), "fp": f.get("fp")}
    return sorted(by_end.values(), key=lambda r: r["end"])


def _ttm_from_quarters(quarters: list[dict]) -> Optional[float]:
    """Sum the last 4 quarterly values (most recent 4 by end date)."""
    if len(quarters) < 4:
        return None
    last4 = quarters[-4:]
    try:
        return float(sum(q["val"] for q in last4))
    except Exception:
        return None


def _pct_growth(curr: Optional[float], prior: Optional[float]) -> Optional[float]:
    if curr is None or prior is None or prior == 0:
        return None
    try:
        return round((curr - prior) / abs(prior), 4)
    except Exception:
        return None


def _derive_flow(facts: dict, tags: list[str], unit: str) -> dict:
    """
    Derive {ttm, growth_yoy, qoq, latest_q_end, latest_filed, annual} for a flow metric.
    Prefers quarterly 10-Q sums (true TTM); falls back to latest 10-K annual.
    """
    out = {"ttm": None, "growth_yoy": None, "qoq": None,
           "latest_q_end": None, "latest_filed": None, "annual_latest": None}
    quarters = _best_flow_series(facts, tags, unit, want_quarterly=True)
    annuals = _best_flow_series(facts, tags, unit, want_quarterly=False)
    if not quarters and not annuals:
        return out

    if annuals:
        out["annual_latest"] = annuals[-1]["val"]

    if len(quarters) >= 4:
        ttm = _ttm_from_quarters(quarters)
        out["ttm"] = ttm
        out["latest_q_end"] = quarters[-1]["end"]
        out["latest_filed"] = quarters[-1]["filed"]
        # YoY: current TTM vs TTM one year prior (quarters[-8:-4])
        if len(quarters) >= 8:
            prior_ttm = _ttm_from_quarters(quarters[-8:-4])
            out["growth_yoy"] = _pct_growth(ttm, prior_ttm)
        # QoQ: latest quarter vs prior quarter
        if len(quarters) >= 2:
            out["qoq"] = _pct_growth(quarters[-1]["val"], quarters[-2]["val"])
    elif annuals:
        # No quarterly granularity — use latest annual as the TTM proxy.
        out["ttm"] = annuals[-1]["val"]
        out["latest_q_end"] = annuals[-1]["end"]
        out["latest_filed"] = annuals[-1]["filed"]
        if len(annuals) >= 2:
            out["growth_yoy"] = _pct_growth(annuals[-1]["val"], annuals[-2]["val"])
    return out


def statements(ticker: str) -> Optional[dict]:
    """
    Latest derived statement values for ticker from SEC XBRL companyfacts.

    Returns a dict (or None if no facts):
      revenue_ttm, revenue_growth, eps_ttm, eps_growth_qoq, net_income_ttm,
      net_margin, assets, liabilities, equity, cash, long_term_debt,
      latest_period_end, latest_filed, source
    """
    facts = companyfacts(ticker)
    if not facts:
        return None

    rev = _derive_flow(facts, REVENUE_TAGS, "USD")
    ni = _derive_flow(facts, NET_INCOME_TAGS, "USD")
    eps = _derive_flow(facts, EPS_TAGS, "USD/shares")

    # Balance-sheet (instant) — latest observation
    def _latest_instant(tags):
        f = _instant_facts(_facts_for_tags(facts, tags, "USD"))
        return f[-1]["val"] if f else None

    assets = _latest_instant(ASSETS_TAGS)
    liabilities = _latest_instant(LIABILITIES_TAGS)
    equity = _latest_instant(EQUITY_TAGS)
    cash = _latest_instant(CASH_TAGS)
    ltdebt = _latest_instant(LTDEBT_TAGS)

    net_margin = None
    if ni["ttm"] is not None and rev["ttm"]:
        try:
            net_margin = round(ni["ttm"] / rev["ttm"], 4)
        except Exception:
            net_margin = None

    # Latest known period/filed across the flow metrics (for provenance)
    ends = [x for x in (rev["latest_q_end"], eps["latest_q_end"]) if x]
    fileds = [x for x in (rev["latest_filed"], eps["latest_filed"]) if x]

    return {
        "ticker": ticker.upper().strip(),
        "revenue_ttm": rev["ttm"],
        "revenue_growth": rev["growth_yoy"],
        "eps_ttm": eps["ttm"],
        "eps_growth_qoq": eps["qoq"],
        "net_income_ttm": ni["ttm"],
        "net_margin": net_margin,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "cash": cash,
        "long_term_debt": ltdebt,
        "latest_period_end": max(ends) if ends else None,
        "latest_filed": max(fileds) if fileds else None,
        "source": "edgar",
    }


# ── POINT-IN-TIME (backtest, no look-ahead) ───────────────────────────────────
def _to_date(d: Any) -> Optional[date]:
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return datetime.strptime(d[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _flow_as_of(facts: dict, tags: list[str], unit: str, as_of: date) -> dict:
    """
    Point-in-time flow derivation: use ONLY facts whose period `end` <= as_of AND
    `filed` <= as_of (no look-ahead on either the period or the disclosure date).
    """
    out = {"ttm": None, "growth_yoy": None, "qoq": None}
    quarters = [
        q for q in _best_flow_series(facts, tags, unit, want_quarterly=True)
        if (_to_date(q["end"]) and _to_date(q["end"]) <= as_of)
        and (_to_date(q["filed"]) and _to_date(q["filed"]) <= as_of)
    ]
    annuals = [
        a for a in _best_flow_series(facts, tags, unit, want_quarterly=False)
        if (_to_date(a["end"]) and _to_date(a["end"]) <= as_of)
        and (_to_date(a["filed"]) and _to_date(a["filed"]) <= as_of)
    ]
    if not quarters and not annuals:
        return out
    if len(quarters) >= 4:
        ttm = _ttm_from_quarters(quarters)
        out["ttm"] = ttm
        if len(quarters) >= 8:
            out["growth_yoy"] = _pct_growth(ttm, _ttm_from_quarters(quarters[-8:-4]))
        if len(quarters) >= 2:
            out["qoq"] = _pct_growth(quarters[-1]["val"], quarters[-2]["val"])
    elif annuals:
        out["ttm"] = annuals[-1]["val"]
        if len(annuals) >= 2:
            out["growth_yoy"] = _pct_growth(annuals[-1]["val"], annuals[-2]["val"])
    return out


def fundamentals_as_of(ticker: str, as_of_date: Any) -> Optional[dict]:
    """
    POINT-IN-TIME statement values as they were KNOWN on `as_of_date`.

    Uses only filings whose period `end` <= as_of_date AND whose `filed` (disclosure)
    date <= as_of_date. This is the audit #1 / #4 value: no look-ahead leakage in
    backtests. Returns the same statement keys as statements(), or None.
    """
    as_of = _to_date(as_of_date)
    if as_of is None:
        return None
    facts = companyfacts(ticker)
    if not facts:
        return None

    rev = _flow_as_of(facts, REVENUE_TAGS, "USD", as_of)
    ni = _flow_as_of(facts, NET_INCOME_TAGS, "USD", as_of)
    eps = _flow_as_of(facts, EPS_TAGS, "USD/shares", as_of)

    def _instant_as_of(tags):
        f = [
            x for x in _instant_facts(_facts_for_tags(facts, tags, "USD"))
            if (_to_date(x["end"]) and _to_date(x["end"]) <= as_of)
            and (_to_date(x["filed"]) and _to_date(x["filed"]) <= as_of)
        ]
        return f[-1]["val"] if f else None

    if rev["ttm"] is None and eps["ttm"] is None:
        return None  # nothing was known as of that date

    net_margin = None
    if ni["ttm"] is not None and rev["ttm"]:
        try:
            net_margin = round(ni["ttm"] / rev["ttm"], 4)
        except Exception:
            net_margin = None

    return {
        "ticker": ticker.upper().strip(),
        "as_of": as_of.isoformat(),
        "revenue_ttm": rev["ttm"],
        "revenue_growth": rev["growth_yoy"],
        "eps_ttm": eps["ttm"],
        "eps_growth_qoq": eps["qoq"],
        "net_income_ttm": ni["ttm"],
        "net_margin": net_margin,
        "assets": _instant_as_of(ASSETS_TAGS),
        "liabilities": _instant_as_of(LIABILITIES_TAGS),
        "equity": _instant_as_of(EQUITY_TAGS),
        "cash": _instant_as_of(CASH_TAGS),
        "long_term_debt": _instant_as_of(LTDEBT_TAGS),
        "source": "edgar",
    }
