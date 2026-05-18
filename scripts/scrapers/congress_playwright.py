#!/usr/bin/env python3
"""
congress_playwright.py — Headless-browser scrape of capitoltrades.com.

capitoltrades.com is JS-rendered; static HTML returns 1-row template. We use
playwright + chromium to load the page, wait for the trade table to populate,
then extract rows. Replaces the dead Senate Stock Watcher endpoints.

URL: https://www.capitoltrades.com/trades?txDate=last-90-days
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

URL = "https://www.capitoltrades.com/trades?sortBy=-pubDate&pageSize=100&page=1"


def _parse_amount_range(s: str) -> tuple[float | None, float | None]:
    if not s:
        return None, None
    s2 = re.sub(r'[\$,\s]', '', s)
    m = re.match(r'([\d.]+)([KMB]?)[–\-](?:[\$])?([\d.]+)([KMB]?)', s2)
    if not m:
        return None, None
    def conv(v, suf):
        try:
            return float(v) * {"K": 1e3, "M": 1e6, "B": 1e9}.get(suf, 1)
        except Exception:
            return None
    return conv(m.group(1), m.group(2)), conv(m.group(3), m.group(4))


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return None


def fetch_rows(max_wait_s: int = 25) -> list[list[str]]:
    """Launch chromium, navigate, wait for table to populate, extract rows."""
    from playwright.sync_api import sync_playwright
    rows: list[list[str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=max_wait_s * 1000)
            # Wait for the data table — capitoltrades uses <table> with trade rows
            try:
                page.wait_for_selector("table tbody tr", timeout=max_wait_s * 1000)
            except Exception:
                pass
            # Give React a moment to fully populate
            time.sleep(3)
            # Extract all visible table rows as arrays of cell text
            rows = page.eval_on_selector_all(
                "table tbody tr",
                "(rows) => rows.map(r => Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim()))",
            )
        finally:
            browser.close()
    return rows


def normalize_rows(raw_rows: list[list[str]]) -> list[dict]:
    out = []
    for cells in raw_rows:
        if len(cells) < 5:
            continue
        joined = " ".join(cells)
        # Ticker: find 1-5 uppercase letters that look like a stock symbol
        ticker = None
        for c in cells:
            for m in re.finditer(r'\b([A-Z]{1,5})\b', c):
                t = m.group(1)
                if t not in ("USD", "OTC", "ETF", "BOND", "PUT", "CALL", "NYSE", "NASDAQ",
                              "I", "II", "III", "ETF", "USA", "INC", "LLC", "CORP", "LP", "USA"):
                    if 1 <= len(t) <= 5:
                        ticker = t
                        break
            if ticker:
                break
        if not ticker:
            continue
        # Member name
        member = ""
        for c in cells:
            if re.search(r'\b(Sen\.?|Rep\.?|Senator|Representative)\b', c):
                member = c
                break
            if not member and re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+', c):
                member = c
        # Date
        date_str = None
        for c in cells:
            d = _parse_date(c)
            if d:
                date_str = d
                break
        # Transaction type
        tx_type = ""
        cl = joined.lower()
        if "buy" in cl or "purchase" in cl:
            tx_type = "purchase"
        elif "sell" in cl or "sale" in cl:
            tx_type = "sale"
        elif "exchange" in cl:
            tx_type = "exchange"
        # Amount range
        amt_min, amt_max = None, None
        for c in cells:
            if "$" in c and ("–" in c or "-" in c.replace("–", "-")):
                amt_min, amt_max = _parse_amount_range(c)
                if amt_min:
                    break
        # Party (R / D / I)
        party = ""
        m = re.search(r'\b([RDI])(?:em|ep|nd)?\b', joined)
        if m and m.group(1) in ("R", "D", "I"):
            party = m.group(1)
        chamber = "senate" if ("sen" in (member or "").lower() or "senator" in (member or "").lower()) else "house"

        out.append({
            "ticker": ticker, "member": member, "party": party, "chamber": chamber,
            "transaction_type": tx_type,
            "amount_range": (" ".join(cells[:6]))[:200],
            "amount_min": amt_min, "amount_max": amt_max,
            "transacted_at": date_str, "reported_at": date_str,
            "source": "capitoltrades_playwright",
            "asset_name": None,
            "external_id": h("cp", date_str or "", ticker, member or ""),
            "sync_key": h("cp", date_str or "", ticker, member or "", tx_type or ""),
            "raw_json": json.dumps({"cells": cells}),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sb = load_env_and_supabase()
    try:
        raw = fetch_rows()
    except Exception as e:
        print(f"✗ Fetch failed: {type(e).__name__}: {e}"); return 1
    print(f"  Fetched {len(raw)} raw rows (chromium)")
    rows = normalize_rows(raw)
    print(f"  Normalized to {len(rows)} congressional_trades rows")
    if not args.apply: return 0
    if not rows: return 0
    # Make sync_key + external_id unique per row (was colliding because
    # multiple distinct trades can share ticker+date+member+type from this site)
    for i, r in enumerate(rows):
        r["sync_key"] = h(r["sync_key"], i)
        r["external_id"] = r["sync_key"]
    ok, fail = upsert(sb, "congressional_trades", rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
