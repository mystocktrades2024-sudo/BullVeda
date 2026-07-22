"""
Zacks per-ticker enrichment scraper.

Pulls fields not available on the basic /stock/quote/[T] page that require
either Selenium (JS-rendered) or login (Ultimate-protected):
  - Industry Rank (X / 254)
  - Earnings ESP (Expected Surprise Prediction)
  - Estimate Revisions trend (7d / 30d / 60d / 90d up vs down counts)
  - Last 4 quarter EPS surprise history
  - Long-term EPS growth estimate (3-5yr)
  - Brokerage recommendation breakdown

Strategy:
  - Pass 1 (lightweight): requests + BeautifulSoup against the public quote page
    for Industry Rank + ESP (visible without login).
  - Pass 2 (Selenium, only if needed): for revisions trend + brokerage detail
    (requires JS render and/or login).

Caching: 6 hours (these don't change intraday).

Wired into data_fetcher.fetch_all_zacks_data() per-ticker enrichment loop.
"""
from __future__ import annotations
import re
import time
from typing import Any
from pathlib import Path
import json

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    requests = None
    BeautifulSoup = None

# Reuse data_fetcher's cache layer — keep enrichment cached 6h
try:
    from data_fetcher import _cache_read, _cache_write, log
except Exception:
    log = None
    def _cache_read(key, ttl):
        return None
    def _cache_write(key, val):
        pass


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def _safe_int(s):
    if s is None: return None
    m = re.search(r'-?\d+', str(s))
    return int(m.group()) if m else None


def _safe_float(s):
    if s is None: return None
    m = re.search(r'-?\d+(?:\.\d+)?', str(s))
    return float(m.group()) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# PASS 1 — lightweight requests scrape (Industry Rank, ESP, basic fields)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_zacks_quote_lightweight(ticker: str, cache_ttl: int = 6 * 3600) -> dict:
    """
    Hit /stock/quote/[ticker] via plain requests and parse the visible fields:
      - rank (1-5)
      - vgm + style grades (when present in HTML)
      - industry_rank (X / Y)
      - long_term_growth_pct
      - sector_rank

    Some fields will be None if the public page hides them (e.g., Earnings ESP
    sometimes requires login). The Selenium pass picks those up.
    """
    if not requests or not BeautifulSoup:
        return {"error": "requests/bs4 not available"}

    cache_key = f"zacks_per_ticker_lite_{ticker}"
    cached = _cache_read(cache_key, cache_ttl)
    if cached is not None:
        return cached

    out: dict = {"ticker": ticker, "error": None}
    try:
        # PRIMARY rank source: Zacks' own JSON quote-feed. The HTML rank regexes
        # matched the 5-box education legend, not the CURRENT rank (returned e.g.
        # 2 when MRVL was actually 3). The feed is authoritative + gives forward
        # PE / yield / next-earnings for free. No login.
        feed = {}
        try:
            fr = requests.get(f"https://quote-feed.zacks.com/index?t={ticker}",
                              headers={**_HEADERS, "Referer": "https://www.zacks.com/"},
                              timeout=12)
            if fr.status_code == 200 and fr.text.strip():
                feed = (fr.json() or {}).get(ticker.upper(), {}) or {}
        except Exception:
            feed = {}

        url = f"https://www.zacks.com/stock/quote/{ticker}"
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}"
            return out
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")

        # Zacks Rank — feed first, then the rank_view / "N-Text" HTML fallbacks
        # (both give the CURRENT rank, unlike the old rank_chip/rankrect legend).
        rank = None
        try:
            rank = int(feed.get("zacks_rank")) if feed.get("zacks_rank") else None
        except (TypeError, ValueError):
            rank = None
        if rank is None:
            m = re.search(r'rank_view[^>]*>\s*(\d)\b', text) or \
                re.search(r'(\d)-(?:Strong Buy|Buy|Hold|Sell|Strong Sell)', text)
            rank = int(m.group(1)) if m else None
        out["rank"] = rank
        out["rank_text"] = feed.get("zacks_rank_text") or {1: "Strong Buy", 2: "Buy",
                            3: "Hold", 4: "Sell", 5: "Strong Sell"}.get(rank)
        # Reliable feed extras (all JSON, no scrape fragility)
        try:
            out["fwd_pe"] = round(float(feed["pe_f1"]), 1) if feed.get("pe_f1") not in (None, "", "NA") else None
        except (TypeError, ValueError):
            out["fwd_pe"] = None
        try:
            out["dividend_yield"] = round(float(feed["dividend_yield"]), 2) if feed.get("dividend_yield") not in (None, "", "NA", "0") else None
        except (TypeError, ValueError):
            out["dividend_yield"] = None
        out["next_earnings_ts"] = feed.get("expected_reporting_date") or None
        out["company_name"] = feed.get("ap_short_name") or feed.get("company_short_name")

        # Industry Rank — rendered as "Top 19% (47 out of 247)".
        ir_match = re.search(r'Top\s+(\d+)%\s*\((\d+)\s+out of\s+(\d+)\)', text)
        if ir_match:
            out["industry_pct"]   = int(ir_match.group(1))     # "Top X%"
            out["industry_rank"]  = int(ir_match.group(2))
            out["industry_total"] = int(ir_match.group(3))
        else:
            out["industry_rank"] = out["industry_total"] = out["industry_pct"] = None
        # Industry name — "Industry: Electronics - Semiconductors"
        inm = re.search(r'Industry:\s*(?:<[^>]*>\s*)*([A-Za-z][A-Za-z0-9 &,/\-]+?)\s*<', text)
        out["industry_name"] = inm.group(1).strip() if inm else None

        # Style Scores (V/G/M/VGM) are JS-rendered on the quote page — the static
        # HTML only carries a tooltip EXAMPLE (which the old regex matched, giving
        # bogus grades). Left as None rather than shipping wrong data; a JS/Premium
        # source (the daily Selenium buy-list) can backfill these later.
        out["style_value"] = out["style_growth"] = out["style_momentum"] = out["style_vgm"] = None

        # Long-term growth estimate — "Long-Term Growth ... 12.5%"
        ltg = re.search(r'Long[-\s]Term\s+Growth[^0-9-]*(-?\d+(?:\.\d+)?)\s*%', text)
        out["long_term_growth_pct"] = float(ltg.group(1)) if ltg else None

        # Earnings ESP — sometimes visible as "Earnings ESP: +1.23%" / "ESP: -0.50%"
        esp = re.search(r'Earnings\s+ESP[:\s]*[<>]?\s*([+-]?\d+(?:\.\d+)?)\s*%', text)
        out["earnings_esp_pct"] = float(esp.group(1)) if esp else None

        # Recommendation (separate from Rank — Zacks aggregated broker rec)
        rec = re.search(r'Brokerage\s+Recommendations?[^<]*<[^>]*>\s*([A-Za-z\s]+?)\s*<', text)
        out["recommendation"] = rec.group(1).strip() if rec else None

        # Days until next earnings (when present)
        ed = re.search(r'Next\s+Earnings\s+Date[^0-9]*(\d{1,2}/\d{1,2}/\d{2,4})', text)
        out["next_earnings_date"] = ed.group(1) if ed else None

        _cache_write(cache_key, out)
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# PASS 2 — Selenium scrape (only when lightweight pass missed key fields)
# Reuses the logged-in driver from fetch_all_zacks_data's premium worker.
# ─────────────────────────────────────────────────────────────────────────────
def fetch_zacks_quote_premium(driver, ticker: str, cache_ttl: int = 6 * 3600) -> dict:
    """
    Use a Selenium driver (typically the already-logged-in Ultimate session)
    to scrape JS-rendered + auth-protected sections:
      - Estimate Revisions table (Current Q / Next Q / Current Y / Next Y)
        Each row: # of analysts revising up vs down at 7d / 30d / 60d / 90d
      - Last 4 quarter EPS surprise history
      - Brokerage recommendations breakdown by tier
      - Detailed style scores (raw 0-100 values)

    Pass-through: returns dict with raw parsed fields, None when not found.
    """
    if BeautifulSoup is None or driver is None:
        return {"error": "selenium/bs4 not available"}

    cache_key = f"zacks_per_ticker_premium_{ticker}"
    cached = _cache_read(cache_key, cache_ttl)
    if cached is not None:
        return cached

    out: dict = {"ticker": ticker, "error": None}

    # ── Estimate Revisions ──
    try:
        url_de = f"https://www.zacks.com/stock/quote/{ticker}/detailed-estimates"
        driver.get(url_de)
        time.sleep(4)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # The table typically looks like:
        # Period | # Analysts | 7 Days Ago | 30 Days Ago | 60 Days Ago | 90 Days Ago
        # Current Q | 12 | $0.85 | $0.84 | $0.80 | $0.78
        revisions = {}
        # Find tables containing "Detailed Estimates"
        for tbl in soup.find_all("table"):
            header = tbl.find("th") or tbl.find("thead")
            if not header: continue
            header_text = (tbl.find("thead").get_text(" ", strip=True) if tbl.find("thead") else "").lower()
            if "current" in header_text and ("quarter" in header_text or "year" in header_text):
                rows = tbl.find_all("tr")
                for tr in rows[1:]:
                    tds = tr.find_all("td")
                    if len(tds) < 2: continue
                    label = tds[0].get_text(" ", strip=True)
                    cells = [_safe_float(td.get_text(strip=True)) for td in tds[1:]]
                    if len(cells) >= 4:
                        revisions[label] = {
                            "current":   cells[0] if len(cells) > 0 else None,
                            "7d_ago":    cells[1] if len(cells) > 1 else None,
                            "30d_ago":   cells[2] if len(cells) > 2 else None,
                            "60d_ago":   cells[3] if len(cells) > 3 else None,
                            "90d_ago":   cells[4] if len(cells) > 4 else None,
                        }
                break
        out["estimate_revisions"] = revisions

        # # Up / # Down analysts in last 7d / 30d
        # Zacks usually displays "Magnitude" and "Surprise" sections too
        ups_downs = {}
        for window in ("7", "30", "60", "90"):
            ups_match = re.search(rf'Last\s+{window}\s+Days[^0-9]*(\d+)\s+Up', driver.page_source, re.IGNORECASE)
            downs_match = re.search(rf'Last\s+{window}\s+Days[^0-9]*(\d+)\s+Down', driver.page_source, re.IGNORECASE)
            if ups_match or downs_match:
                ups_downs[f"{window}d"] = {
                    "up":   int(ups_match.group(1)) if ups_match else 0,
                    "down": int(downs_match.group(1)) if downs_match else 0,
                }
        out["estimate_revision_counts"] = ups_downs
    except Exception as e:
        out["estimate_revisions"] = {}
        out["estimate_revisions_error"] = str(e)

    # ── EPS Surprise history (last 4 quarters) ──
    try:
        url_es = f"https://www.zacks.com/stock/quote/{ticker}/earnings-eps-surprise"
        driver.get(url_es)
        time.sleep(4)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        surprises = []
        # Look for table with reporting date, estimate, actual, surprise%
        for tbl in soup.find_all("table"):
            header_text = (tbl.find("thead").get_text(" ", strip=True) if tbl.find("thead") else "").lower()
            if "report" in header_text and ("estimate" in header_text or "actual" in header_text):
                rows = tbl.find_all("tr")
                for tr in rows[1:5]:  # last 4 quarters
                    tds = tr.find_all("td")
                    if len(tds) < 4: continue
                    surprises.append({
                        "report_date":  tds[0].get_text(strip=True),
                        "period":       tds[1].get_text(strip=True) if len(tds) > 1 else None,
                        "estimate":     _safe_float(tds[2].get_text(strip=True)) if len(tds) > 2 else None,
                        "actual":       _safe_float(tds[3].get_text(strip=True)) if len(tds) > 3 else None,
                        "surprise":     _safe_float(tds[4].get_text(strip=True)) if len(tds) > 4 else None,
                        "surprise_pct": _safe_float(tds[5].get_text(strip=True)) if len(tds) > 5 else None,
                    })
                break
        out["eps_surprise_history"] = surprises

        # Also try to extract Earnings ESP from this page (more reliable than quote page)
        esp = re.search(r'Earnings\s+ESP[^0-9-]*([+-]?\d+(?:\.\d+)?)\s*%', driver.page_source)
        if esp and out.get("earnings_esp_pct") is None:
            out["earnings_esp_pct"] = float(esp.group(1))
    except Exception as e:
        out["eps_surprise_history"] = []
        out["eps_surprise_error"] = str(e)

    # ── Brokerage recommendations breakdown ──
    try:
        url_br = f"https://www.zacks.com/stock/quote/{ticker}/brokerage-recommendations"
        driver.get(url_br)
        time.sleep(4)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        broker = {"strong_buy": None, "buy": None, "hold": None, "sell": None, "strong_sell": None,
                  "average_rec": None, "current_count": None}
        # Often rendered in a chart with raw numbers in a sibling table
        for label, key in [("Strong Buy", "strong_buy"), ("Buy", "buy"), ("Hold", "hold"),
                           ("Sell", "sell"), ("Strong Sell", "strong_sell")]:
            m = re.search(rf'>{re.escape(label)}<[^0-9]*(\d+)', driver.page_source)
            if m:
                broker[key] = int(m.group(1))
        # Average rec (e.g., 1.84)
        ar = re.search(r'Average\s+Brokerage\s+Recommendation[^0-9.-]*(\d+(?:\.\d+)?)', driver.page_source)
        if ar:
            broker["average_rec"] = float(ar.group(1))
        out["brokerage_recommendations"] = broker
    except Exception as e:
        out["brokerage_recommendations"] = {}
        out["brokerage_error"] = str(e)

    _cache_write(cache_key, out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED ENTRY POINT — used by data_fetcher.fetch_all_zacks_data
# ─────────────────────────────────────────────────────────────────────────────
def fetch_zacks_per_ticker(ticker: str, driver=None, use_premium: bool = True) -> dict:
    """
    Combined enrichment fetch — runs lightweight pass always, premium pass when
    a logged-in driver is provided.

    Returns merged dict with all fields, never raises.
    """
    out: dict = {}
    try:
        lite = fetch_zacks_quote_lightweight(ticker)
        out.update({k: v for k, v in lite.items() if v is not None and k != "error"})
    except Exception as e:
        out.setdefault("errors", []).append(f"lite: {e}")

    if use_premium and driver is not None:
        try:
            premium = fetch_zacks_quote_premium(driver, ticker)
            out.update({k: v for k, v in premium.items() if v is not None and k != "error"})
        except Exception as e:
            out.setdefault("errors", []).append(f"premium: {e}")

    return out
