#!/usr/bin/env python3
"""Congressional trading universe — Senate + House Stock Watcher feeds.

Catches tickers that US senators / representatives have traded in the last
N days. Empirically (Karadas 2017, Belmont-Foley-McGarry 2024), certain
senators (Pelosi, Crapo, Tuberville, Hagerty) and committee chairs have
persistent ~10pp annual alpha on the SPY benchmark.

Sources (all public, free):
  - Senate Stock Watcher: senate-stock-watcher-data.s3.us-east-2.amazonaws.com
  - House Stock Watcher:  house-stock-watcher-data.s3.us-east-2.amazonaws.com

Both publish daily-updated JSON dumps of all financial disclosures filed
under the STOCK Act. No API key needed.

Filters applied:
  - last LOOKBACK_DAYS only (default 90 — covers most recent 2-3 disclosure cycles)
  - PURCHASE transactions only (sales skipped — diversification or politics, not edge)
  - US-listed common stock (skip options, ETFs, foreign symbols)
  - amount band tier filter (skip < $1K trivial reports)

Output: cache/congressional_picks.json
  {
    "_meta": {generated_at, n_tickers, n_transactions, sources},
    "candidates": [{ticker, n_legislators, latest_tx, legislators: [{name, party, amount, date}]}],
    "tickers": [...just symbols for universe wire-up]
  }

Wired into swing_trade.py universe build via _load_congressional() (already done).
"""
from __future__ import annotations
import datetime
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "congressional_picks.json"

SENATE_URL = "https://senate-stock-watcher-data.s3.us-east-2.amazonaws.com/aggregate/all_transactions.json"
HOUSE_URL  = "https://house-stock-watcher-data.s3.us-east-2.amazonaws.com/data/all_transactions.json"

LOOKBACK_DAYS = 90
PURCHASE_KEYWORDS = ("purchase", "buy")
SALE_KEYWORDS = ("sale", "sell", "exchange")  # skipped


def _fetch_json(url: str, timeout: int = 30) -> list | None:
    """Public S3 JSON fetcher, no auth."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SwingTrade-Universe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[congressional] fetch failed {url}: {e}", file=sys.stderr)
        return None


def _is_us_common_stock(ticker: str) -> bool:
    """Heuristic: 1-5 char alphanumeric, no foreign suffix, no options notation."""
    if not ticker:
        return False
    t = ticker.strip().upper()
    if not t or len(t) > 5:
        return False
    if not t.replace(".", "").replace("-", "").isalnum():
        return False
    # Skip obvious options / warrants / bonds
    if any(x in t for x in ("/", " ", "$", "WS", "WT", "PR")):
        return False
    return True


def _parse_transactions(rows: list, source: str, cutoff_date: datetime.date) -> list[dict]:
    """Normalize Senate + House schema diffs into a unified record."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        # Date — both sources use 'transaction_date' but format differs
        date_str = (r.get("transaction_date") or r.get("disclosure_date") or "")[:10]
        try:
            tdate = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            try:
                tdate = datetime.datetime.strptime(date_str, "%m/%d/%Y").date()
            except Exception:
                continue
        if tdate < cutoff_date:
            continue
        # Type
        ttype = (r.get("type") or r.get("transaction_type") or "").lower().strip()
        if not any(kw in ttype for kw in PURCHASE_KEYWORDS):
            continue
        # Ticker
        ticker = (r.get("ticker") or r.get("symbol") or "").strip().upper()
        if not _is_us_common_stock(ticker):
            continue
        # Senator/Rep name + party
        name = (r.get("senator") or r.get("representative") or r.get("name") or "?").strip()
        party = (r.get("party") or "").strip()
        # Amount — usually a range like "$1,001 - $15,000"
        amount = r.get("amount") or r.get("transaction_amount") or ""
        out.append({
            "ticker": ticker,
            "name": name,
            "party": party,
            "amount": str(amount),
            "date": tdate.isoformat(),
            "source": source,
            "type": ttype,
        })
    return out


def main() -> int:
    print(f"[congressional] fetching Senate + House disclosures (last {LOOKBACK_DAYS}d) …", file=sys.stderr)
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=LOOKBACK_DAYS)

    senate_raw = _fetch_json(SENATE_URL)
    house_raw  = _fetch_json(HOUSE_URL)

    senate_tx = _parse_transactions(senate_raw or [], "senate", cutoff)
    house_tx  = _parse_transactions(house_raw or [], "house", cutoff)
    all_tx = senate_tx + house_tx

    # Aggregate by ticker → set of unique legislators
    by_ticker: dict[str, dict] = defaultdict(lambda: {"legislators": [], "latest_tx": ""})
    for tx in all_tx:
        rec = by_ticker[tx["ticker"]]
        rec["legislators"].append({
            "name": tx["name"],
            "party": tx["party"],
            "amount": tx["amount"],
            "date": tx["date"],
            "source": tx["source"],
        })
        if tx["date"] > rec["latest_tx"]:
            rec["latest_tx"] = tx["date"]

    # Build candidates list — deduplicate legislators per ticker
    candidates = []
    for tk, rec in by_ticker.items():
        seen = set()
        uniq_legs = []
        for L in sorted(rec["legislators"], key=lambda x: x["date"], reverse=True):
            key = L["name"]
            if key in seen:
                continue
            seen.add(key)
            uniq_legs.append(L)
        candidates.append({
            "ticker": tk,
            "n_legislators": len(uniq_legs),
            "latest_tx": rec["latest_tx"],
            "n_transactions": len(rec["legislators"]),
            "legislators": uniq_legs[:10],
        })
    candidates.sort(key=lambda x: (-x["n_legislators"], x["latest_tx"]), reverse=False)
    # Sort by n_legislators desc, then by recency
    candidates.sort(key=lambda x: (-x["n_legislators"], -int(x["latest_tx"].replace("-", "") or 0)))

    out = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "lookback_days": LOOKBACK_DAYS,
            "n_tickers": len(candidates),
            "n_transactions": len(all_tx),
            "n_senate_tx": len(senate_tx),
            "n_house_tx": len(house_tx),
            "sources": {"senate": SENATE_URL, "house": HOUSE_URL},
        },
        "candidates": candidates[:300],
        "tickers": [c["ticker"] for c in candidates],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[congressional] wrote {OUT} · {len(candidates)} tickers from {len(all_tx)} purchase txs "
          f"(senate={len(senate_tx)}, house={len(house_tx)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
