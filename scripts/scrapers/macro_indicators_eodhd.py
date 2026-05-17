#!/usr/bin/env python3
"""
macro_indicators_eodhd.py — Daily macro snapshot (VIX, SPY/QQQ/IWM,
HYG, UUP, GLD, treasury yields) from EODHD into macro_indicators.

Source (free with EODHD): /eod/{TICKER}.INDX or /eod/{TICKER}.US

Usage: python3 scripts/scrapers/macro_indicators_eodhd.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, upsert

EODHD_BASE = "https://eodhd.com/api"

INDICATORS = {
    "vix":         "VIX.INDX",
    "spy":         "SPY.US",
    "qqq":         "QQQ.US",
    "iwm":         "IWM.US",
    "hyg":         "HYG.US",
    "uup":         "UUP.US",
    "gld":         "GLD.US",
    "treasury_10y": "US10Y.INDX",
    "treasury_2y":  "US2Y.INDX",
}


def _key():
    return os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY") or ""


def fetch_eod(symbol: str, since: str) -> list[dict]:
    url = f"{EODHD_BASE}/eod/{symbol}?api_token={_key()}&from={since}&fmt=json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ! {symbol}: {e}")
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not _key():
        print("✗ EODHD_API_TOKEN missing"); return 1

    since = (date.today() - timedelta(days=args.days)).isoformat()
    # Build a {date: row} dict, fill in each indicator
    by_date: dict[str, dict] = {}
    for col, sym in INDICATORS.items():
        bars = fetch_eod(sym, since)
        print(f"  {col:15s} {sym:12s} {len(bars)} bars")
        for b in bars:
            d = b.get("date")
            if not d:
                continue
            row = by_date.setdefault(d, {"observed_at": d})
            if col == "vix":
                row["vix"] = b.get("close")
            elif col == "treasury_10y":
                row["treasury_10y"] = b.get("close")
            elif col == "treasury_2y":
                row["treasury_2y"] = b.get("close")
            elif col == "spy":
                row["spy_close"] = b.get("close")
            elif col == "qqq":
                row["qqq_close"] = b.get("close")
            elif col == "iwm":
                row["iwm_close"] = b.get("close")
            elif col == "hyg":
                row["hyg_close"] = b.get("close")
            elif col == "uup":
                row["uup_close"] = b.get("close")
            elif col == "gld":
                row["gld_close"] = b.get("close")
    # Compute yield curve where both legs present
    for d, row in by_date.items():
        if row.get("treasury_10y") and row.get("treasury_2y"):
            row["yield_curve_2_10"] = row["treasury_10y"] - row["treasury_2y"]

    rows = list(by_date.values())
    print(f"\n  {len(rows)} daily macro rows ready")
    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "macro_indicators", rows, "observed_at")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
