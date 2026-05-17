#!/usr/bin/env python3
"""
fomc_ical.py — Federal Reserve FOMC meeting dates from federalreserve.gov ical.

Source (free): https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, upsert

URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
UA = "Mozilla/5.0 (SwingTrade scraper)"


def fetch_fomc_dates() -> list[date]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="ignore")
    # Pattern: "<h4>2026</h4>" then panels like "January 27-28"
    # Simple regex pass — production should use HTMLParser
    out: list[date] = []
    year_blocks = re.split(r'<h[34][^>]*>(\d{4})</h[34]>', html)
    # year_blocks alternates: [preamble, year, block, year, block, ...]
    for i in range(1, len(year_blocks), 2):
        try:
            yr = int(year_blocks[i])
            block = year_blocks[i+1]
        except (IndexError, ValueError):
            continue
        # Find Month name + day pattern like "January 27-28" or "January 27"
        for m in re.finditer(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:[\-–](\d{1,2}))?', block):
            month_name = m.group(1)
            end_day = int(m.group(3) or m.group(2))  # use last day of multi-day meeting
            try:
                from datetime import datetime
                d = datetime.strptime(f"{yr} {month_name} {end_day}", "%Y %B %d").date()
                out.append(d)
            except Exception:
                pass
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    try:
        dates = fetch_fomc_dates()
    except Exception as e:
        print(f"✗ Fetch failed: {e}"); return 1
    print(f"  Parsed {len(dates)} FOMC meeting dates: {dates[:6]}{'...' if len(dates)>6 else ''}")

    rows = [{
        "meeting_date": d.isoformat(),
        "statement_time": "14:00 ET",
        "presser_time": "14:30 ET",
        "is_decision_meeting": True,
        "source": "fed_html_calendar",
    } for d in dates]

    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "fomc_calendar", rows, "meeting_date")
    print(f"  pushed={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
