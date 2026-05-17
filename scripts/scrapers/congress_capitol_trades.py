#!/usr/bin/env python3
"""
congress_capitol_trades.py — Scrape capitoltrades.com for congressional trades.

Replaces the dead Senate Stock Watcher endpoints.
capitoltrades.com publishes Senate + House STOCK Act disclosures in a clean
HTML table — easier to scrape than SEC EDGAR.

URL: https://www.capitoltrades.com/trades?txDate=last-90-days
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

URL = "https://www.capitoltrades.com/trades?txDate=last-90-days&pageSize=100"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class _CTParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.cell_buf = ""
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif self.in_row and tag in ("td", "th"):
            self.in_cell = True
            self.cell_buf = ""

    def handle_endtag(self, tag):
        if tag == "tr" and self.in_row:
            if len(self.row) >= 5:
                self.rows.append(self.row)
            self.in_row = False
        elif self.in_row and tag in ("td", "th") and self.in_cell:
            self.row.append(self.cell_buf.strip())
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf += data


def fetch_capitol() -> list[list[str]]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA,
                                                "Accept": "text/html,application/xhtml+xml",
                                                "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", errors="ignore")
    parser = _CTParser()
    parser.feed(html)
    return parser.rows


def _parse_amount_range(s: str) -> tuple[float | None, float | None]:
    if not s:
        return None, None
    s2 = re.sub(r'[\$,\s]', '', s)
    m = re.match(r'([\d.]+)([KMB]?)[–\-](?:[\$])?([\d.]+)([KMB]?)', s2)
    if not m:
        return None, None
    def conv(v, suf):
        try:
            n = float(v)
            return n * {"K": 1e3, "M": 1e6, "B": 1e9}.get(suf, 1)
        except Exception:
            return None
    return conv(m.group(1), m.group(2)), conv(m.group(3), m.group(4))


def _parse_date_ct(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return None


def normalize_rows(raw_rows: list[list[str]]) -> list[dict]:
    out = []
    for cells in raw_rows:
        if len(cells) < 5:
            continue
        ticker = None
        for c in cells:
            m = re.search(r'\b([A-Z]{2,5})\b', c)
            if m and len(m.group(1)) <= 5 and m.group(1) not in ("USD","OTC","ETF","BOND","PUT","CALL","NYSE","NASD"):
                ticker = m.group(1)
                break
        if not ticker:
            continue
        member = ""
        for c in cells:
            if re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+', c) or "Sen" in c or "Rep" in c:
                if not member:
                    member = c
        date_str = None
        for c in cells:
            d = _parse_date_ct(c)
            if d:
                date_str = d
                break
        tx_type = ""
        for c in cells:
            cl = c.lower()
            if "buy" in cl or "purchase" in cl:
                tx_type = "purchase"; break
            elif "sell" in cl or "sale" in cl:
                tx_type = "sale"; break
            elif "exchange" in cl:
                tx_type = "exchange"; break
        amt_min, amt_max = None, None
        for c in cells:
            if "$" in c and ("–" in c or "-" in c):
                amt_min, amt_max = _parse_amount_range(c)
                if amt_min: break
        chamber = "senate" if ("sen" in (member or "").lower() or "senator" in (member or "").lower()) else "house"
        out.append({
            "ticker": ticker, "member": member, "party": "", "chamber": chamber,
            "transaction_type": tx_type,
            "amount_range": " ".join(cells[:6])[:200],
            "amount_min": amt_min, "amount_max": amt_max,
            "transacted_at": date_str, "reported_at": date_str,
            "source": "capitoltrades", "asset_name": None,
            "external_id": h("ct", date_str or "", ticker, member or ""),
            "sync_key": h("ct", date_str or "", ticker, member or "", tx_type or ""),
            "raw_json": json.dumps({"cells": cells}),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sb = load_env_and_supabase()
    try:
        raw = fetch_capitol()
    except Exception as e:
        print(f"✗ Fetch failed: {e}"); return 1
    print(f"  Fetched {len(raw)} raw table rows")
    rows = normalize_rows(raw)
    print(f"  Normalized to {len(rows)} congressional_trades rows")
    if not args.apply: return 0
    if not rows: return 0
    ok, fail = upsert(sb, "congressional_trades", rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
