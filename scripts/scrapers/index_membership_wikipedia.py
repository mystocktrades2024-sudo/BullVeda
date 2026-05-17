#!/usr/bin/env python3
"""
index_membership_wikipedia.py — Scrape current S&P 500 / NASDAQ-100 membership
from Wikipedia. Populates index_membership_pit with current-as-of records;
historical PIT requires walking Wikipedia revision history (future enhancement).

Fixes audit flaw #1 (survivorship bias) — first step.

Sources (free):
  - https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
  - https://en.wikipedia.org/wiki/Nasdaq-100

Usage: python3 scripts/scrapers/index_membership_wikipedia.py --apply
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path
from html.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "Mozilla/5.0 (SwingTrade scraper) Python/urllib"


class _SP500Parser(HTMLParser):
    """Pulls ticker symbols from the first table on the SP500 page."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.table_idx = -1
        self.row = []
        self.cell_buf = ""
        self.in_cell = False
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.table_idx += 1
        elif self.in_table and self.table_idx == 0:
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th"):
                self.in_cell = True
                self.cell_buf = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif self.in_table and self.table_idx == 0:
            if tag == "tr" and self.row:
                self.rows.append(self.row)
            elif tag in ("td", "th"):
                self.in_cell = False
                self.row.append(self.cell_buf.strip())

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf += data


def _fetch_wikipedia(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def scrape_sp500() -> list[str]:
    """Return list of current S&P 500 tickers."""
    html = _fetch_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    parser = _SP500Parser()
    parser.feed(html)
    tickers = []
    for row in parser.rows[1:]:  # skip header
        if row and len(row[0]) <= 6 and row[0].isupper():
            tickers.append(row[0].replace(".", "-"))  # BRK.B → BRK-B
    return tickers


def scrape_ndx() -> list[str]:
    """Return list of current NASDAQ-100 tickers."""
    html = _fetch_wikipedia("https://en.wikipedia.org/wiki/Nasdaq-100")
    parser = _SP500Parser()
    parser.feed(html)
    tickers = []
    for row in parser.rows[1:]:
        # NDX page has different layout; symbol is usually col 1 or 2
        for cell in row[:3]:
            if cell and 1 <= len(cell) <= 6 and cell.isupper() and cell.isalpha():
                tickers.append(cell)
                break
    return tickers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not args.apply and sb is None:
        print("No Supabase; dry-run only")

    today = date.today().isoformat()
    sources = [("sp500", scrape_sp500), ("ndx100", scrape_ndx)]

    for index_name, fn in sources:
        try:
            tickers = fn()
        except Exception as e:
            print(f"✗ {index_name}: {type(e).__name__}: {e}")
            continue
        print(f"  {index_name}: {len(tickers)} tickers fetched")
        if not args.apply or sb is None:
            continue
        rows = [{
            "index_name": index_name,
            "ticker": t,
            "added_on": "1900-01-01",  # placeholder until rev history walked
            "removed_on": None,
            "source": "wikipedia_current",
            "reason": "initial_scrape",
            "sync_key": h("imp", index_name, t),
        } for t in tickers]
        ok, fail = upsert(sb, "index_membership_pit", rows, "sync_key")
        print(f"    pushed={ok} failed={fail}")
        time.sleep(1)  # polite rate-limit
    return 0


if __name__ == "__main__":
    sys.exit(main())
