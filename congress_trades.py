#!/usr/bin/env python3
"""Multi-source congressional / political trade aggregator.

The free feeds we historically relied on went dark in 2026:
  - Senate / House Stock Watcher S3 buckets  → 301 / 403 (decommissioned)
  - Capitol Trades public site               → Vercel bot-wall (429 / 503)

This module re-establishes a **never-single-sourced** cascade using only free,
no-key public endpoints (per the no-paid-data policy in CLAUDE.md):

  TICKER-LEVEL transactions (politician × ticker × buy/sell):
    1. Quiver Quantitative beta live endpoint  — PRIMARY  (both chambers, JSON, no key)
    2. Capitol Trades bulk scrape              — best-effort tertiary (often walled)

  OFFICIAL PROVENANCE (corroboration + freshness, so we are never blind if a
  scraped aggregator changes shape):
    3. House Clerk bulk FD ZIP  (disclosures-clerk.house.gov)  — official PTR filing index
    4. Senate eFD search        (efdsearch.senate.gov)         — official filing index

  Sources 3-4 give filer + filing-date + document-id (NOT tickers — those live in
  PDFs that would need OCR, a documented follow-up). They are used to PROVE the
  data is fresh and to flag staleness if the ticker-level spine ever dies.

Outputs (both under cache/):
  congressional_trades.json  — normalized full transaction list (raw)
  congressional_picks.json   — aggregates: leaderboard + per-ticker rollup + feed
                               (keeps legacy `candidates`/`tickers` keys for the
                                universe wire-up in swing_trade.py)

Mechanism / why this has (informational) edge: Karadas 2017, Belmont-Foley-McGarry
2024 document persistent ~10pp annual alpha for certain committee chairs. BUT the
STOCK Act allows up to a 45-day disclosure lag, so by the time a trade is public it
is a *crowded* signal (CLAUDE.md principle 12). This data is surfaced as CONTEXT,
never as a scoring gate.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests

BASE = Path(__file__).resolve().parent
CACHE = BASE / "cache"
RAW_OUT = CACHE / "congressional_trades.json"
AGG_OUT = CACHE / "congressional_picks.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

QUIVER_URL = "https://api.quiverquant.com/beta/live/congresstrading"
HOUSE_ZIP_TMPL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.ZIP"
SENATE_HOME = "https://efdsearch.senate.gov/search/home/"
SENATE_DATA = "https://efdsearch.senate.gov/search/report/data/"

LOOKBACK_DAYS = 90


# ──────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────
def _norm_party(p: Optional[str]) -> str:
    if not p:
        return ""
    p = str(p).strip().lower()
    if p.startswith("d"):
        return "D"
    if p.startswith("r"):
        return "R"
    if p.startswith("i"):
        return "I"
    return p.upper()[:1]


def _norm_type(raw: Optional[str]) -> str:
    t = (raw or "").lower()
    if "purchase" in t or "buy" in t:
        return "buy"
    if "sale" in t or "sell" in t:
        return "sell"
    return "other"


def _to_float(x) -> float:
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0


def _amount_min_from_range(rng: str) -> float:
    """'$1,001 - $15,000' -> 1001.0 (lower bound of disclosed band)."""
    if not rng:
        return 0.0
    m = re.search(r"\$?([\d,]+)", rng)
    return _to_float(m.group(1)) if m else 0.0


def _is_us_common_stock(ticker: str) -> bool:
    if not ticker:
        return False
    t = ticker.strip().upper()
    if not t or len(t) > 5:
        return False
    if not t.replace(".", "").replace("-", "").isalnum():
        return False
    if any(x in t for x in ("/", " ", "$", "WS", "WT", "PR")):
        return False
    return True


def _parse_date(s: str) -> Optional[_dt.date]:
    s = (s or "")[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────
# SOURCE 1 — Quiver beta live (PRIMARY, ticker-level, both chambers)
# ──────────────────────────────────────────────────────────────────────────
def fetch_quiver(retries: int = 3) -> tuple[list[dict], dict]:
    status = {"name": "quiver", "ok": False, "n": 0, "error": None}
    rows = None
    # The free beta endpoint intermittently 401/429s — retry with backoff before
    # declaring it down (a transient 401 must not be allowed to wipe a good cache).
    for attempt in range(retries):
        try:
            r = requests.get(QUIVER_URL, headers={"User-Agent": UA, "Accept": "application/json"},
                             timeout=25)
            if r.status_code == 200:
                rows = r.json()
                break
            status["error"] = f"HTTP {r.status_code}"
            if r.status_code not in (401, 403, 429, 503) or attempt == retries - 1:
                return [], status
            import time as _t
            _t.sleep(1.5 * (attempt + 1))
        except Exception as e:  # pragma: no cover - network
            status["error"] = str(e)[:120]
            if attempt == retries - 1:
                return [], status
            import time as _t
            _t.sleep(1.5 * (attempt + 1))
    if rows is None:
        return [], status
    try:
        out = []
        for d in rows or []:
            tk = (d.get("Ticker") or "").strip().upper()
            if not _is_us_common_stock(tk):
                continue
            out.append({
                "politician":   (d.get("Representative") or "").strip(),
                "party":        _norm_party(d.get("Party")),
                "chamber":      (d.get("House") or "").strip(),
                "ticker":       tk,
                "type":         _norm_type(d.get("Transaction")),
                "size_range":   (d.get("Range") or "").strip(),
                "amount_min":   _to_float(d.get("Amount")) or _amount_min_from_range(d.get("Range") or ""),
                "trade_date":   (d.get("TransactionDate") or "")[:10],
                "publish_date": (d.get("ReportDate") or "")[:10],
                "source":       "quiver",
            })
        status.update(ok=True, n=len(out))
        return out, status
    except Exception as e:  # pragma: no cover - network
        status["error"] = str(e)[:120]
        return [], status


# ──────────────────────────────────────────────────────────────────────────
# SOURCE 2 — Capitol Trades bulk scrape (best-effort, often bot-walled)
# ──────────────────────────────────────────────────────────────────────────
def fetch_capitol_trades(pages: int = 5) -> tuple[list[dict], dict]:
    status = {"name": "capitoltrades", "ok": False, "n": 0, "error": None}
    try:
        # Reuse the existing scraper in data_fetcher (handles HTML parse + dedup).
        import data_fetcher as _df
        raw = _df._capitol_trades_fetch_bulk(pages=pages)
        out = []
        for d in raw or []:
            tk = (d.get("ticker") or "").strip().upper()
            if not _is_us_common_stock(tk):
                continue
            out.append({
                "politician":   (d.get("politician") or "").strip(),
                "party":        _norm_party(d.get("party")),
                "chamber":      (d.get("chamber") or "").strip(),
                "ticker":       tk,
                "type":         _norm_type(d.get("type")),
                "size_range":   (d.get("size_range") or "").strip(),
                "amount_min":   _amount_min_from_range(d.get("size_range") or ""),
                "trade_date":   _iso_or_blank(d.get("trade_date")),
                "publish_date": _iso_or_blank(d.get("publish_date")),
                "source":       "capitoltrades",
            })
        status.update(ok=bool(out), n=len(out),
                      error=None if out else "0 rows (likely bot-walled)")
        return out, status
    except Exception as e:
        status["error"] = str(e)[:120]
        return [], status


def _iso_or_blank(s: str) -> str:
    """Capitol Trades uses '13 Apr 2026' — normalize to ISO."""
    s = (s or "").strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return ""


# ──────────────────────────────────────────────────────────────────────────
# SOURCE 3 — House Clerk bulk FD ZIP (OFFICIAL provenance — filing index only)
# ──────────────────────────────────────────────────────────────────────────
def fetch_house_clerk_filings(year: Optional[int] = None) -> tuple[list[dict], dict]:
    """Official House PTR filing index. Gives filer + date + DocID (no tickers —
    those are in per-filing PDFs). Used for freshness corroboration."""
    status = {"name": "house_clerk", "ok": False, "n": 0, "error": None}
    year = year or _dt.date.today().year
    try:
        url = HOUSE_ZIP_TMPL.format(year=year)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            status["error"] = f"HTTP {r.status_code}"
            return [], status
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        # ZIP holds {year}FD.xml (filing index) + {year}FD.txt
        xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not xml_name:
            status["error"] = "no XML index in ZIP"
            return [], status
        import xml.etree.ElementTree as ET
        root = ET.fromstring(zf.read(xml_name))
        out = []
        for mem in root.findall(".//Member"):
            def _g(tag):
                el = mem.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""
            ftype = _g("FilingType")  # 'P' = Periodic Transaction Report (a trade)
            if ftype.upper() != "P":
                continue
            out.append({
                "politician": f"{_g('First')} {_g('Last')}".strip(),
                "filing_type": ftype,
                "state_dst": _g("StateDst"),
                "filing_date": _iso_or_blank(_g("FilingDate")),
                "doc_id": _g("DocID"),
                "chamber": "House",
                "source": "house_clerk",
            })
        status.update(ok=True, n=len(out))
        return out, status
    except Exception as e:
        status["error"] = str(e)[:120]
        return [], status


# ──────────────────────────────────────────────────────────────────────────
# SOURCE 4 — Senate eFD (OFFICIAL provenance — best-effort filing index)
# ──────────────────────────────────────────────────────────────────────────
def fetch_senate_efd_filings(limit: int = 100) -> tuple[list[dict], dict]:
    """Official Senate eFD recent PTR filings. Requires a terms-accept session
    (CSRF cookie + POST). Best-effort — returns [] on any handshake failure."""
    status = {"name": "senate_efd", "ok": False, "n": 0, "error": None}
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA})
        home = sess.get(SENATE_HOME, timeout=20)
        token = sess.cookies.get("csrftoken")
        if not token:
            m = re.search(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)", home.text)
            token = m.group(1) if m else None
        if not token:
            status["error"] = "no csrf token"
            return [], status
        # Accept the prohibition-of-commercial-use agreement
        sess.post(SENATE_HOME, data={"csrfmiddlewaretoken": token, "prohibition_agreement": "1"},
                  headers={"Referer": SENATE_HOME}, timeout=20)
        payload = {
            "start": "0", "length": str(limit),
            "report_types": "[11]",          # 11 = Periodic Transaction Report
            "filer_types": "[]", "submitted_start_date": "", "submitted_end_date": "",
            "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "",
            "last_name": "", "csrfmiddlewaretoken": token,
            "draw": "1", "order[0][column]": "1", "order[0][dir]": "desc",
        }
        r = sess.post(SENATE_DATA, data=payload,
                      headers={"Referer": SENATE_HOME,
                               "X-Requested-With": "XMLHttpRequest"}, timeout=25)
        if r.status_code != 200:
            status["error"] = f"HTTP {r.status_code}"
            return [], status
        rows = r.json().get("data", [])
        out = []
        for row in rows:
            # row = [first, last, office, report_link_html, date]
            try:
                first, last = row[0], row[1]
                link = re.search(r'href="([^"]+)"', row[3] or "")
                date = _iso_or_blank(row[4])
            except Exception:
                continue
            out.append({
                "politician": f"{first} {last}".strip(),
                "filing_type": "P",
                "filing_date": date,
                "doc_id": (link.group(1) if link else ""),
                "chamber": "Senate",
                "source": "senate_efd",
            })
        status.update(ok=True, n=len(out))
        return out, status
    except Exception as e:
        status["error"] = str(e)[:120]
        return [], status


# ──────────────────────────────────────────────────────────────────────────
# aggregation
# ──────────────────────────────────────────────────────────────────────────
def _dedup(txs: list[dict]) -> list[dict]:
    """Merge ticker-level sources; dedup by (politician, ticker, trade_date, type).
    Quiver wins ties (richer fields) because it is appended first."""
    seen = set()
    out = []
    for tx in txs:
        k = (tx["politician"].lower(), tx["ticker"], tx["trade_date"], tx["type"])
        if k in seen:
            continue
        seen.add(k)
        out.append(tx)
    return out


def aggregate(txs: list[dict], lookback_days: int = LOOKBACK_DAYS) -> dict:
    cutoff = _dt.date.today() - _dt.timedelta(days=lookback_days)
    recent = []
    for tx in txs:
        d = _parse_date(tx["trade_date"]) or _parse_date(tx["publish_date"])
        if d and d >= cutoff:
            recent.append(tx)

    by_ticker: dict[str, dict] = defaultdict(lambda: {
        "buy_tx": 0, "sell_tx": 0, "buyers": [], "sellers": [],
        "party": defaultdict(int), "chambers": defaultdict(int),
        "total_amount_min": 0.0, "latest_trade_date": "", "latest_publish_date": "",
    })
    for tx in recent:
        rec = by_ticker[tx["ticker"]]
        if tx["type"] == "buy":
            rec["buy_tx"] += 1
            rec["buyers"].append(tx)
            rec["party"][tx["party"] or "?"] += 1
            rec["chambers"][tx["chamber"] or "?"] += 1
            rec["total_amount_min"] += tx["amount_min"]
        elif tx["type"] == "sell":
            rec["sell_tx"] += 1
            rec["sellers"].append(tx)
        if tx["trade_date"] > rec["latest_trade_date"]:
            rec["latest_trade_date"] = tx["trade_date"]
        if tx["publish_date"] > rec["latest_publish_date"]:
            rec["latest_publish_date"] = tx["publish_date"]

    leaderboard = []
    by_ticker_rollup = {}
    for tk, rec in by_ticker.items():
        n_buyers = len({b["politician"].lower() for b in rec["buyers"]})
        n_sellers = len({s["politician"].lower() for s in rec["sellers"]})
        net = "bullish" if n_buyers >= 2 and rec["buy_tx"] > rec["sell_tx"] else \
              "bearish" if rec["sell_tx"] > rec["buy_tx"] + 1 else "neutral"
        # unique buyers, most recent first
        seen, uniq_buyers = set(), []
        for b in sorted(rec["buyers"], key=lambda x: x["trade_date"], reverse=True):
            if b["politician"].lower() in seen:
                continue
            seen.add(b["politician"].lower())
            uniq_buyers.append({
                "politician": b["politician"], "party": b["party"],
                "chamber": b["chamber"], "size_range": b["size_range"],
                "trade_date": b["trade_date"], "publish_date": b["publish_date"],
                "source": b["source"],
            })
        entry = {
            "ticker": tk,
            "n_buyers": n_buyers, "n_sellers": n_sellers,
            "buy_tx": rec["buy_tx"], "sell_tx": rec["sell_tx"],
            "net": net,
            "total_amount_min": round(rec["total_amount_min"]),
            "party_split": dict(rec["party"]),
            "chambers": dict(rec["chambers"]),
            "latest_trade_date": rec["latest_trade_date"],
            "latest_publish_date": rec["latest_publish_date"],
            "buyers": uniq_buyers[:12],
        }
        leaderboard.append(entry)
        # per-ticker rollup (Intel tile ② shape — superset of legacy get_congressional_trades)
        by_ticker_rollup[tk] = {
            "purchases": rec["buy_tx"], "sales": rec["sell_tx"], "net": net,
            "n_buyers": n_buyers, "n_sellers": n_sellers,
            "latest": uniq_buyers[0]["politician"] if uniq_buyers else "",
            "latest_date": rec["latest_trade_date"],
            "total_amount_min": round(rec["total_amount_min"]),
            "buyers": uniq_buyers[:6],
            "error": None, "source_unavailable": False, "source": "multi",
        }

    # most-bought first: # unique buyers, then $ committed, then recency
    leaderboard.sort(key=lambda x: (
        -x["n_buyers"], -x["total_amount_min"],
        -int((x["latest_trade_date"] or "0").replace("-", "") or 0)))

    # live feed — most recent transactions (buys + sells), newest first
    feed = sorted(recent, key=lambda x: (x["publish_date"] or x["trade_date"]),
                  reverse=True)[:200]

    return {"leaderboard": leaderboard, "by_ticker": by_ticker_rollup,
            "feed": feed, "n_recent": len(recent)}


# ──────────────────────────────────────────────────────────────────────────
# build — fetch all sources, aggregate, write both caches
# ──────────────────────────────────────────────────────────────────────────
def build(lookback_days: int = LOOKBACK_DAYS, verbose: bool = True) -> dict:
    sources = []

    quiver_tx, s1 = fetch_quiver()
    sources.append(s1)
    capitol_tx, s2 = fetch_capitol_trades()
    sources.append(s2)
    house_filings, s3 = fetch_house_clerk_filings()
    sources.append(s3)
    senate_filings, s4 = fetch_senate_efd_filings()
    sources.append(s4)

    # Quiver first so it wins dedup ties
    all_tx = _dedup(quiver_tx + capitol_tx)
    agg = aggregate(all_tx, lookback_days)

    # official-provenance freshness (corroboration that aggregator isn't stale)
    def _latest(filings):
        ds = [f["filing_date"] for f in filings if f.get("filing_date")]
        return max(ds) if ds else ""
    provenance = {
        "house_clerk": {"reachable": s3["ok"], "n_ptr_filings": s3["n"],
                        "latest_filing": _latest(house_filings)},
        "senate_efd":  {"reachable": s4["ok"], "n_ptr_filings": s4["n"],
                        "latest_filing": _latest(senate_filings)},
    }

    meta = {
        "generated_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lookback_days": lookback_days,
        "n_transactions_total": len(all_tx),
        "n_transactions_recent": agg["n_recent"],
        "n_tickers": len(agg["leaderboard"]),
        "sources": sources,
        "provenance": provenance,
        "ticker_level_ok": s1["ok"] or s2["ok"],
    }

    # legacy candidates/tickers (universe wire-up backward compat)
    candidates = [{
        "ticker": e["ticker"], "n_legislators": e["n_buyers"],
        "latest_tx": e["latest_trade_date"], "n_transactions": e["buy_tx"],
        "legislators": [{"name": b["politician"], "party": b["party"],
                         "amount": b["size_range"], "date": b["trade_date"],
                         "source": b["source"]} for b in e["buyers"]],
    } for e in agg["leaderboard"] if e["n_buyers"] >= 1]

    agg_out = {
        "_meta": meta,
        "leaderboard": agg["leaderboard"],
        "feed": agg["feed"],
        "by_ticker": agg["by_ticker"],
        "candidates": candidates[:300],
        "tickers": [c["ticker"] for c in candidates],
    }
    raw_out = {"_meta": meta, "transactions": all_tx,
               "house_filings": house_filings[:200],
               "senate_filings": senate_filings[:200]}

    # ── PRESERVE-ON-DEGRADE ──────────────────────────────────────────────
    # A transient ticker-source outage (Quiver 401/429, Capitol bot-wall) must
    # NEVER clobber a good cache with an empty board. If we got no ticker-level
    # data this run but a prior good cache exists, keep it and only stamp it
    # stale (records the failed attempt + which official sources are still live).
    CACHE.mkdir(parents=True, exist_ok=True)
    if not meta["ticker_level_ok"] and AGG_OUT.exists():
        try:
            prior = json.loads(AGG_OUT.read_text())
            if prior.get("leaderboard"):
                pm = prior.setdefault("_meta", {})
                pm["last_refresh_attempt"] = meta["generated_at"]
                pm["last_refresh_failed"] = True
                pm["last_refresh_sources"] = sources
                pm["provenance"] = provenance          # official freshness still updates
                pm["stale"] = True
                AGG_OUT.write_text(json.dumps(prior, indent=2))
                if verbose:
                    print("  [preserve] ticker sources down — kept prior good cache, "
                          f"stamped stale (had {len(prior['leaderboard'])} tickers)", file=sys.stderr)
                return prior
        except Exception:
            pass  # prior unreadable — fall through and write the (empty) honest state

    AGG_OUT.write_text(json.dumps(agg_out, indent=2))
    RAW_OUT.write_text(json.dumps(raw_out, indent=2))

    if verbose:
        for s in sources:
            print(f"  [{s['name']:14s}] ok={s['ok']} n={s['n']} "
                  f"err={s['error'] or '-'}", file=sys.stderr)
        print(f"[congress] {len(all_tx)} txs · {len(agg['leaderboard'])} tickers · "
              f"top buy: {agg['leaderboard'][0]['ticker'] if agg['leaderboard'] else '-'}",
              file=sys.stderr)
    return agg_out


if __name__ == "__main__":
    lb = LOOKBACK_DAYS
    if len(sys.argv) > 1:
        try:
            lb = int(sys.argv[1])
        except ValueError:
            pass
    build(lookback_days=lb)
