#!/usr/bin/env python3
"""
tickers_master_eodhd.py — One-shot pull of every US-listed symbol + metadata.

Source: EODHD /exchange-symbol-list/US (already paid for).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, upsert


def _key():
    return os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY") or ""


def fetch_us_symbols() -> list[dict]:
    url = f"https://eodhd.com/api/exchange-symbol-list/US?api_token={_key()}&fmt=json"
    req = urllib.request.Request(url, headers={"User-Agent": "SwingTrade"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not _key():
        print("✗ EODHD_API_TOKEN missing"); return 1
    try:
        data = fetch_us_symbols()
    except Exception as e:
        print(f"✗ Fetch failed: {e}"); return 1
    print(f"  Fetched {len(data):,} US symbols")

    rows = []
    for s in data:
        ticker = (s.get("Code") or "").upper().strip()
        if not ticker:
            continue
        rows.append({
            "ticker": ticker,
            "name": s.get("Name"),
            "exchange": s.get("Exchange"),
            "country": s.get("Country") or "US",
            "is_etf": (s.get("Type") == "ETF"),
            "is_adr": (s.get("Type") == "ADR"),
            "cusip": s.get("Isin"),  # EODHD returns ISIN not CUSIP
            "isin": s.get("Isin"),
            "raw_json": json.dumps(s),
        })

    print(f"  Normalized to {len(rows):,} rows")
    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "tickers_master", rows, "ticker")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
