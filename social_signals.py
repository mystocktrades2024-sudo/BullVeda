"""
social_signals.py — Free Twitter/X ticker extraction via Nitter RSS

Scrapes 50 curated financial handles from nitter.net RSS feeds.
Extracts $TICKER cashtags with recency-weighted buzz scoring.
No API key required.

Cache: cache/_cache_social_signals.json (60-min TTL)
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("social_signals")

BASE_DIR   = Path(__file__).parent
CACHE_FILE = BASE_DIR / "cache" / "_cache_social_signals.json"
CACHE_TTL  = 3600          # 1 hour
NITTER_BASE = "https://nitter.net"
MAX_WORKERS = 10

# ── Curated handle list ────────────────────────────────────────────
HANDLES: list[str] = [
    "WOLF_Financial",   "TheETFTracker",    "WOLF_TradingX",   "AceTheKid",
    "stocktalkweekly",  "SawyerMerritt",    "WolfRyan",        "MapleStax",
    "Sam_Badawi",       "amitisinvesting",  "MonetiveWealth",  "JaguarAnalytics",
    "PaperGainsInc",    "KCTrades777",      "adampatti",       "Futurenvesting",
    "Mr_Derivatives",   "wallstengine",     "JRupena",         "wliang",
    "sunxliao",         "faststocknewss",   "LeverageETFs",    "greg16676935420",
    "WOLF_Bitcoin_",    "TickerSymbolYOU",  "Wolf_Defense_",   "stocksnipa",
    "ralliesarena",     "oliwalkerjones",   "OptionsMike",     "GavBlaxberg",
    "RedDogT3",         "eliano",           "LowBeta",         "BullTradeFinder",
    "ThemesETFs",       "WillOHara131",     "wholemars",       "SpecialSitsNews",
    "teslaownersSV",    "Kross_Roads",      "KrisPatel99",     "TomLeeTracker",
    "Coolmark482",      "ParikPatelCFA",    "hamids",          "AlexFinn",
    "TreasuryEdge",     "StockSavvyShay",
]

# Cashtag: $NVDA, $BRK.B — captures 1–5 uppercase letters (+ optional .X suffix)
_TICKER_RE = re.compile(r'\$([A-Z]{1,5})(?:\.[A-Z]{1,2})?(?=[^A-Z]|$)')

# Words that look like tickers but aren't
_BLACKLIST: frozenset[str] = frozenset({
    "A", "I", "AM", "PM", "US", "OR", "IT", "TO", "BY", "AS", "AT",
    "BE", "DO", "GO", "IF", "IN", "IS", "NO", "OF", "ON", "SO", "UP",
    "WE", "AN", "ANY", "ARE", "CAN", "CEO", "CFO", "COO", "CTO",
    "IPO", "ETF", "IRS", "GDP", "CPI", "PCE", "DXY", "AI", "ML",
    "EV", "VC", "PE", "FY", "Q1", "Q2", "Q3", "Q4", "YOY", "QOQ",
    "EPS", "YTD", "TTM", "ATH", "ATL", "THE", "FOR", "AND", "ALL",
    "NEW", "NOW", "GET", "SET", "YES", "NOT", "TOO", "ITS", "HAS",
    "HAD", "DID", "OUT", "BUT", "USE", "DAY", "ONE", "TWO",
})

_BULL_WORDS: frozenset[str] = frozenset({
    "bull", "buy", "long", "breakout", "strong", "rally", "up", "growth",
    "beat", "raised", "upgrade", "surge", "record", "opportunity", "target",
    "outperform", "overweight", "upside", "gain", "high", "rise",
})
_BEAR_WORDS: frozenset[str] = frozenset({
    "bear", "sell", "short", "breakdown", "weak", "crash", "down", "cut",
    "miss", "downgrade", "drop", "decline", "risk", "warning", "caution",
    "underperform", "underweight", "downside", "loss", "low", "fall",
})


# ── RSS helpers ────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text).strip()


def _extract_tickers(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for t in _TICKER_RE.findall(text.upper()):
        if t not in _BLACKLIST and t not in seen and len(t) >= 2:
            seen.add(t)
            result.append(t)
    return result


def _fetch_rss(handle: str) -> list[dict]:
    """Fetch nitter RSS and return parsed tweet items."""
    url = f"{NITTER_BASE}/{handle}/rss"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 SwingTradeBot/1.0"})
        with urlopen(req, timeout=12) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        channel = root.find("channel")
        if channel is None:
            return []

        items: list[dict] = []
        for item in channel.findall("item"):
            title   = (item.findtext("title")       or "").strip()
            desc    = (item.findtext("description")  or "").strip()
            link    = (item.findtext("link")         or "").strip()
            pub_str = (item.findtext("pubDate")      or "").strip()

            try:
                pub_dt   = parsedate_to_datetime(pub_str)
                pub_date = pub_dt.strftime("%Y-%m-%d")
                pub_ts   = pub_dt.timestamp()
            except Exception:
                pub_date = datetime.now().strftime("%Y-%m-%d")
                pub_ts   = time.time()

            clean = _clean_html(desc) or _clean_html(title)
            full  = f"{title} {clean}"
            tickers = _extract_tickers(full)

            if tickers:
                items.append({
                    "handle": handle,
                    "text":   clean[:280].strip(),
                    "tickers": tickers,
                    "date":   pub_date,
                    "ts":     pub_ts,
                    "link":   link,
                })

        return items

    except (URLError, HTTPError, ET.ParseError, Exception) as e:
        log.debug(f"RSS fetch failed [{handle}]: {e}")
        return []


# ── Scoring helpers ────────────────────────────────────────────────

def _buzz_score(mentions: list[dict]) -> int:
    """Recency-weighted mention score (0–100). 10 fresh mentions today = 100."""
    now_ts = time.time()
    DAY    = 86_400
    w_sum  = 0.0
    for m in mentions:
        age = (now_ts - m["ts"]) / DAY
        w_sum += 1.0 if age < 1 else (0.7 if age < 2 else (0.4 if age < 3 else 0.1))
    return min(100, int(w_sum * 10))


def _sentiment(texts: list[str]) -> str:
    b = s = 0
    for txt in texts:
        words = set(txt.lower().split())
        b += len(words & _BULL_WORDS)
        s += len(words & _BEAR_WORDS)
    if b > s + 1:
        return "bullish"
    if s > b + 1:
        return "bearish"
    return "neutral"


# ── Main public function ───────────────────────────────────────────

def get_social_signals(force_refresh: bool = False) -> dict:
    """
    Return social buzz data for all configured handles.
    Result is cached for CACHE_TTL seconds.
    """
    # Cache check
    if not force_refresh and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            age = time.time() - cached.get("fetch_ts", 0)
            if age < CACHE_TTL:
                log.info(f"Social signals: cache hit ({age / 60:.0f}m old, "
                         f"{cached.get('total_tickers', 0)} tickers)")
                return cached
        except Exception:
            pass

    log.info(f"Social signals: fetching {len(HANDLES)} handles from {NITTER_BASE}…")
    t0 = time.time()

    # Parallel RSS fetch
    all_items:     list[dict]       = []
    handle_status: dict[str, str]   = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_rss, h): h for h in HANDLES}
        for fut in as_completed(futures):
            h = futures[fut]
            try:
                items = fut.result()
                all_items.extend(items)
                handle_status[h] = "ok" if items else "empty"
            except Exception as e:
                handle_status[h] = f"error: {e}"

    elapsed = round(time.time() - t0, 1)
    log.info(f"Social signals: {len(all_items)} items in {elapsed}s | "
             f"{sum(1 for s in handle_status.values() if s == 'ok')} active handles")

    # ── Aggregate by ticker ────────────────────────────────────────
    raw: dict[str, dict] = {}

    for item in all_items:
        for ticker in item["tickers"]:
            if ticker not in raw:
                raw[ticker] = {"ticker": ticker, "mentions": [], "by_handle": {}}
            td = raw[ticker]
            td["mentions"].append(item)

            h = item["handle"]
            if h not in td["by_handle"]:
                td["by_handle"][h] = {
                    "handle":    h,
                    "count":     0,
                    "texts":     [],
                    "last_date": item["date"],
                    "link":      item["link"],
                }
            hd = td["by_handle"][h]
            hd["count"]  += 1
            hd["texts"].append(item["text"])
            if item["date"] > hd["last_date"]:
                hd["last_date"] = item["date"]
                hd["link"]      = item["link"]

    # ── Enrich each ticker ─────────────────────────────────────────
    enriched: dict[str, dict] = {}
    for ticker, td in raw.items():
        mentions = td["mentions"]
        handle_list = sorted(
            td["by_handle"].values(),
            key=lambda x: (x["last_date"], x["count"]),
            reverse=True,
        )
        all_texts = [m["text"] for m in mentions]
        enriched[ticker] = {
            "ticker":        ticker,
            "mention_count": len(mentions),
            "handle_count":  len(td["by_handle"]),
            "buzz_score":    _buzz_score(mentions),
            "sentiment":     _sentiment(all_texts),
            "last_seen":     max(m["date"] for m in mentions),
            "first_seen":    min(m["date"] for m in mentions),
            "handles":       handle_list,
        }

    top_tickers = sorted(
        enriched.keys(),
        key=lambda t: (enriched[t]["buzz_score"], enriched[t]["mention_count"]),
        reverse=True,
    )

    # ── Batch price fetch for top tickers ─────────────────────────
    for ticker in enriched:
        enriched[ticker]["price"] = None
    try:
        from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
        tlist = top_tickers[:100]
        if tlist:
            df = yf.download(tlist, period="1d", progress=False, auto_adjust=True)
            if not df.empty and "Close" in df.columns:
                close = df["Close"]
                last  = close.iloc[-1]
                for t in tlist:
                    try:
                        if hasattr(last, "__getitem__") and t in last.index:
                            v = last[t]
                            enriched[t]["price"] = round(float(v), 2) if v == v else None
                        elif t == tlist[0] and isinstance(last, (int, float)):
                            enriched[t]["price"] = round(float(last), 2)
                    except Exception:
                        pass
    except Exception as pe:
        log.debug(f"Social price fetch: {pe}")

    # ── Per-handle summary ─────────────────────────────────────────
    handle_summary: dict[str, dict] = {}
    for h in HANDLES:
        h_items = [i for i in all_items if i["handle"] == h]
        seen: set[str] = set()
        ordered: list[str] = []
        for i in h_items:
            for t in i["tickers"]:
                if t not in seen:
                    ordered.append(t)
                    seen.add(t)
        handle_summary[h] = {
            "handle":       h,
            "status":       handle_status.get(h, "unknown"),
            "post_count":   len(h_items),
            "ticker_count": len(seen),
            "tickers":      ordered[:30],
            "last_fetch":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    result = {
        "run_date":       datetime.now().strftime("%Y-%m-%d"),
        "fetch_ts":       time.time(),
        "fetch_elapsed":  elapsed,
        "total_handles":  len(HANDLES),
        "active_handles": sum(1 for s in handle_status.values() if s == "ok"),
        "total_posts":    len(all_items),
        "total_tickers":  len(enriched),
        "tickers":        enriched,
        "top_tickers":    top_tickers[:100],
        "handles":        handle_summary,
    }

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(result, default=str), encoding="utf-8")
    log.info(f"Social signals: cached {len(enriched)} tickers → {CACHE_FILE.name}")
    return result
