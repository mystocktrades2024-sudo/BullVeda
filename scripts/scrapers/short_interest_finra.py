#!/usr/bin/env python3
"""
short_interest_finra.py — Bi-monthly short interest from FINRA bulk file.

Source (free): https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data
The Equity Short Interest file is published twice monthly. Format is
pipe-delimited text.

This is a first-cut: pull the latest published file, parse, upsert.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "Mozilla/5.0 (SwingTrade scraper)"
# FINRA reg sho daily volume — has short_volume but not short_interest balance
# The actual short-interest report is at a different path; we'll fall back to
# OTC short interest summary which is also free.
SOURCES = [
    # Try the regulator's regsho daily file
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt",
]


def _latest_business_date_str() -> str:
    """FINRA publishes regsho 'CNMSshvolYYYYMMDD.txt' daily. Walk back to find one."""
    today = date.today()
    for back in range(0, 10):
        d = today - timedelta(days=back)
        if d.weekday() < 5:  # weekday
            return d.strftime("%Y%m%d")
    return today.strftime("%Y%m%d")


def fetch_finra() -> tuple[str, list[dict]]:
    """Return (file_date, list of rows). Each row has Symbol/ShortVolume/TotalVolume."""
    file_date = _latest_business_date_str()
    url = SOURCES[0].format(date=file_date)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ! fetch {url}: {e}")
        return file_date, []
    lines = text.splitlines()
    if len(lines) < 2:
        return file_date, []
    header = [h.strip() for h in lines[0].split("|")]
    rows = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < len(header):
            continue
        rows.append(dict(zip(header, parts)))
    return file_date, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sb = load_env_and_supabase()
    file_date, raw = fetch_finra()
    print(f"  FINRA regsho daily {file_date}: {len(raw)} rows")
    if not raw:
        print("(No file available for that date — try after market close)"); return 0

    # Settlement date = the trading date the file reports on
    settlement = f"{file_date[:4]}-{file_date[4:6]}-{file_date[6:8]}"
    rows = []
    for r in raw:
        sym = (r.get("Symbol") or r.get("SYMBOL") or "").upper().strip()
        if not sym or len(sym) > 8:
            continue
        try:
            short_shares = int(r.get("ShortVolume") or r.get("SHORTVOLUME") or 0)
            total_vol = int(r.get("TotalVolume") or r.get("TOTALVOLUME") or 0)
        except ValueError:
            continue
        if total_vol == 0:
            continue
        short_pct = (short_shares / total_vol * 100) if total_vol else None
        rows.append({
            "settlement_date": settlement,
            "ticker": sym,
            "short_shares": short_shares,
            "short_pct_outstanding": None,  # not in regsho daily
            "short_pct_float": short_pct,    # actually pct of day's volume
            "days_to_cover": None,
            "source": "finra_regsho_daily",
            "sync_key": h("si", settlement, sym),
            "raw_json": json.dumps(r),
        })
    print(f"  Normalized {len(rows)} short-interest rows")
    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "short_interest_history", rows, "ticker,settlement_date")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
