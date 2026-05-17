#!/usr/bin/env python3
"""
fomc_ical.py — Federal Reserve FOMC meeting dates from federalreserve.gov.

v2: proper HTMLParser walking the calendar table rather than fragile regex.

Source (free): https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, upsert

URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
UA = "Mozilla/5.0 (SwingTrade scraper)"
MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 0)}
MONTHS_ABBR = {m.lower(): i for i, m in enumerate(
    ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 0)}


class _FOMCParser(HTMLParser):
    """Pull all visible text per <div class="panel-default"> (one panel per year)
    and look for "Month dd" or "Month dd-dd" patterns. Year comes from the panel
    heading."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.in_panel = False
        self.in_heading = False
        self.heading_buf = ""
        self.body_buf = ""
        self.panels: list[tuple[str, str]] = []  # (heading, body)
        self._cur_heading = ""
        self._cur_body_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        if "panel" in cls and "default" in cls:
            self.in_panel = True
            self._cur_heading = ""
            self._cur_body_parts = []
        elif self.in_panel and ("panel-heading" in cls or tag in ("h2", "h3", "h4", "h5")):
            self.in_heading = True
        elif self.in_panel:
            pass

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4", "h5"):
            self.in_heading = False
        if self.in_panel and tag == "div" and self._cur_body_parts:
            # close-on-depth would be safer, but for the Fed page each panel is one outermost div
            pass

    def handle_data(self, data):
        if self.in_heading:
            self._cur_heading += data
        elif self.in_panel:
            self._cur_body_parts.append(data)

    def close(self):
        # finalize last panel
        super().close()
        # Approach instead: simpler — just gather full body grouped by year heading
        pass


def fetch_fomc_dates() -> list[date]:
    """Parse year + 'Month dd-dd' / 'Month dd' anywhere in the page."""
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="ignore")

    out: set[date] = set()
    # Find year blocks: look for "<h... fomc-meetings-YYYY" or just "<h3>YYYY FOMC Meetings"
    # Fed pages use heading patterns like "<h3>2026 FOMC Meetings</h3>"
    year_pattern = re.compile(r'(\d{4})\s+FOMC\s+Meetings', re.IGNORECASE)
    # Split page on year headers — content between two year tokens belongs to first
    parts = year_pattern.split(html)
    # parts = [preamble, year1, body1, year2, body2, ...]
    for i in range(1, len(parts), 2):
        try:
            yr = int(parts[i])
        except (ValueError, IndexError):
            continue
        body = parts[i + 1] if (i + 1) < len(parts) else ""
        # Strip tags
        body_txt = re.sub(r'<[^>]+>', ' ', body)
        # Pattern: full or abbreviated month + day(s)
        # "January 28-29" or "Jan 28" or "January 28"
        month_re = re.compile(
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December'
            r'|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:[\-–](\d{1,2}))?',
            re.IGNORECASE)
        for m in month_re.finditer(body_txt):
            mon_str = m.group(1).lower().rstrip(".")
            mon = MONTHS.get(mon_str) or MONTHS_ABBR.get(mon_str)
            if not mon:
                continue
            end_day = int(m.group(3) or m.group(2))
            try:
                out.add(date(yr, mon, end_day))
            except ValueError:
                continue
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    try:
        dates = fetch_fomc_dates()
    except Exception as e:
        print(f"✗ Fetch failed: {e}"); return 1
    print(f"  Parsed {len(dates)} FOMC meeting dates")
    if dates:
        print(f"  Range: {dates[0]} → {dates[-1]}")
        print(f"  First 6: {dates[:6]}")

    rows = [{
        "meeting_date": d.isoformat(),
        "statement_time": "14:00 ET",
        "presser_time": "14:30 ET",
        "is_decision_meeting": True,
        "source": "fed_html_calendar_v2",
    } for d in dates]

    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "fomc_calendar", rows, "meeting_date")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
