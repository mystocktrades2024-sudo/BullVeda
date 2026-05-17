#!/usr/bin/env python3
"""
congress_trades.py — Congressional stock trades.

v2: try multiple free sources in order of reliability.

Sources tried (free):
  1. github.com/timothycarambat/all-financial-disclosures (community mirror,
     served via GitHub raw)
  2. github.com/jeremiak/senate-stock-watcher-data (raw GitHub fallback)
  3. SEC EDGAR direct (Form 4 → individual matches)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "Mozilla/5.0 (SwingTrade scraper)"

SOURCES = [
    # GitHub raw is more reliable than the S3 bucket which now requires auth
    "https://raw.githubusercontent.com/jeremiak/senate-stock-watcher-data/main/aggregate/all_transactions.json",
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json",
]


def fetch_senate() -> list[dict]:
    last_err = None
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            print(f"  ✓ source: {url[:70]}...")
            return data
        except Exception as e:
            print(f"  ✗ {url[:70]}: {type(e).__name__}: {str(e)[:80]}")
            last_err = e
            continue
    if last_err:
        raise last_err
    return []


def _parse_amount(band: str) -> tuple[float | None, float | None]:
    """'$1,001 - $15,000' → (1001, 15000)"""
    if not band:
        return None, None
    s = band.replace("$", "").replace(",", "")
    parts = s.split("-")
    try:
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
        return float(parts[0].strip()), float(parts[0].strip())
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    sb = load_env_and_supabase()
    try:
        data = fetch_senate()
    except Exception as e:
        print(f"✗ All sources failed: {e}"); return 1
    print(f"  Fetched {len(data):,} Senate disclosures")

    rows = []
    for d in data:
        ticker = (d.get("ticker") or "").upper().strip()
        if not ticker or ticker == "--" or len(ticker) > 8:
            continue
        amt_min, amt_max = _parse_amount(d.get("amount") or "")
        tx_date = d.get("transaction_date")
        disc_date = d.get("disclosure_date")
        if not (tx_date and disc_date):
            continue
        rows.append({
            "ticker": ticker,
            "member": d.get("senator"),
            "chamber": "senate",
            "transaction_type": d.get("type"),
            "amount_range": d.get("amount"),
            "amount_min": amt_min,
            "amount_max": amt_max,
            "transacted_at": tx_date,
            "reported_at": disc_date,
            "source": "senate_stock_watcher_v2",
            "asset_name": d.get("asset_description"),
            "external_id": d.get("ptr_link") or h("sn", tx_date, ticker, d.get("senator"), d.get("amount")),
            "sync_key": h("sn", tx_date, ticker, d.get("senator"), d.get("type"), d.get("amount")),
            "raw_json": json.dumps(d),
        })

    if args.limit:
        rows = rows[:args.limit]
    print(f"  Filtered to {len(rows):,} ticker-tagged rows")

    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "congressional_trades", rows, "sync_key")
    print(f"  pushed={ok:,}  failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
