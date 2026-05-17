#!/usr/bin/env python3
"""
insider_openinsider.py — Scrape openinsider.com for Form 4 insider transactions.

Much simpler than SEC EDGAR XBRL — openinsider already aggregates Form 4 filings
into HTML tables. We just parse them and push to insider_transactions.

URL format: http://openinsider.com/latest-insider-transactions
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

URL = "http://openinsider.com/latest-insider-transactions"
UA = "Mozilla/5.0 (X11; Linux x86_64; SwingTrade)"


class _OITableParser(HTMLParser):
    """Pull rows from the first <table class="tinytable"> on the page."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.table_count = 0
        self.in_row = False
        self.in_cell = False
        self.cell_buf = ""
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "tinytable" in (a.get("class") or ""):
            self.in_table = True
            self.table_count += 1
        elif self.in_table:
            if tag == "tr":
                self.row = []
                self.in_row = True
            elif tag in ("td", "th") and self.in_row:
                self.in_cell = True
                self.cell_buf = ""

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        elif self.in_table:
            if tag in ("td", "th") and self.in_cell:
                self.row.append(self.cell_buf.strip())
                self.in_cell = False
            elif tag == "tr" and self.in_row:
                if self.row and len(self.row) >= 10:
                    self.rows.append(self.row)
                self.in_row = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf += data


def fetch_openinsider() -> list[list[str]]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", errors="ignore")
    parser = _OITableParser()
    parser.feed(html)
    return parser.rows


def _parse_money(s):
    if not s:
        return None
    s = re.sub(r'[\$,+]', '', s).strip()
    if not s or s in ('-', '—'):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _parse_date(s):
    """Try multiple date formats common in openinsider."""
    if not s or s in ('-', '—'):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            continue
    return None


def normalize_rows(raw_rows: list[list[str]]) -> list[dict]:
    """OpenInsider table columns (typical):
    X | Filing Date | Trade Date | Ticker | Insider Name | Title | Trade Type |
    Price | Qty | Owned | ΔOwn | Value | other
    Indices may vary; we map by position with safety checks.
    """
    out = []
    for row in raw_rows:
        if len(row) < 12:
            continue
        try:
            filing_date = _parse_date(row[1])
            transacted_at = _parse_date(row[2])
            ticker = (row[3] or "").upper().strip()
            insider_name = (row[4] or "").strip()
            title = (row[5] or "").strip()
            trade_type = (row[6] or "").strip()
            price = _parse_money(row[7])
            qty = _parse_money(row[8])
            owned = _parse_money(row[9])
            value = _parse_money(row[11])
        except Exception:
            continue
        if not (ticker and transacted_at):
            continue
        if not (1 <= len(ticker) <= 6):
            continue
        out.append({
            "ticker": ticker,
            "filer_name": insider_name,
            "filer_role": title,
            "transaction_type": trade_type,
            "shares": int(qty) if qty is not None else None,
            "price": price,
            "value": value,
            "filed_at": filing_date,
            "transacted_at": transacted_at,
            "shares_after": int(owned) if owned is not None else None,
            "source": "openinsider",
            "filing_url": None,
            "external_id": h("oi", transacted_at, ticker, insider_name, trade_type, price),
            "sync_key": h("oi", transacted_at, ticker, insider_name, trade_type, price, qty),
            "raw_json": json.dumps({"row": row}),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    try:
        raw = fetch_openinsider()
    except Exception as e:
        print(f"✗ Fetch failed: {e}"); return 1
    print(f"  Fetched {len(raw)} rows from openinsider")
    rows = normalize_rows(raw)
    print(f"  Normalized to {len(rows)} insider_transactions rows")
    if not args.apply:
        print("Dry-run"); return 0
    if not rows:
        return 0
    ok, fail = upsert(sb, "insider_transactions", rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
