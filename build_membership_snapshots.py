"""
build_membership_snapshots.py — point-in-time S&P 500 membership snapshots.

Scrapes Wikipedia's "List of S&P 500 companies" page (current constituents
table + historical changes table), then walks backward from today's
membership to reconstruct who was in the index on the 1st of each month
from 2023-01 through current month.

Output: data/membership/sp500_YYYY-MM.csv (one ticker per line, sorted).

Source: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
Limitations:
  - Russell 1000 historical: not available freely; backtest falls back to
    current R1000 for pre-today dates (smaller bias than full survivorship).
  - Wikipedia changes table covers ~50 years but our window starts 2023-01.

Run:
    python3 build_membership_snapshots.py             # rebuild all snapshots
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "membership"
WINDOW_START = date(2023, 1, 1)
WIKI_URL = "https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies&format=json&prop=text"


def _fetch_html() -> str:
    req = urllib.request.Request(WIKI_URL, headers={"User-Agent": "SwingTrade-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["parse"]["text"]["*"]


def _extract_table(html: str, table_id: str) -> str:
    m = re.search(rf'<table[^>]*id="{table_id}"[^>]*>(.*?)</table>', html, re.DOTALL)
    return m.group(1) if m else ""


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return text.strip()


def _parse_constituents(table_html: str) -> list[str]:
    """First column is ticker. Returns list with codebase convention (BRK.B → BRK-B)."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
    out = []
    for row in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL)
        if not cells:
            continue
        t = _clean(cells[0])
        if re.match(r"^[A-Z][A-Z\.\-]{0,7}$", t):
            out.append(t.replace(".", "-"))
    return out


def _parse_changes(table_html: str) -> list[dict]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
    months = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}
    out = []
    for row in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL)
        if len(cells) < 5:
            continue
        date_text = _clean(cells[0])
        m = re.match(r"(\w+)\s+(\d+),\s+(\d{4})", date_text)
        if not m or m.group(1) not in months:
            continue
        iso = f"{int(m.group(3)):04d}-{months[m.group(1)]:02d}-{int(m.group(2)):02d}"
        added = _clean(cells[1])
        removed = _clean(cells[3])
        out.append({
            "date": iso,
            "added": added.replace(".", "-") if re.match(r"^[A-Z][A-Z\.\-]{0,7}$", added) else "",
            "removed": removed.replace(".", "-") if re.match(r"^[A-Z][A-Z\.\-]{0,7}$", removed) else "",
        })
    return out


def build_snapshots() -> dict:
    html = _fetch_html()
    current = _parse_constituents(_extract_table(html, "constituents"))
    changes = _parse_changes(_extract_table(html, "changes"))
    print(f"Wikipedia parse: {len(current)} current tickers, {len(changes)} change events")

    # Walk backward from today's membership.
    membership = set(current)
    snapshots: dict[str, set[str]] = {}

    target_dates: list[date] = []
    today = date.today()
    y, m = WINDOW_START.year, WINDOW_START.month
    while date(y, m, 1) <= today:
        target_dates.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    target_dates.sort(reverse=True)

    changes_sorted = sorted(changes, key=lambda c: c["date"], reverse=True)
    idx = 0
    for target in target_dates:
        target_str = target.isoformat()
        while idx < len(changes_sorted):
            c = changes_sorted[idx]
            if c["date"] >= target_str:
                if c["added"] and c["added"] in membership:
                    membership.discard(c["added"])
                if c["removed"]:
                    membership.add(c["removed"])
                idx += 1
            else:
                break
        snapshots[target_str] = set(membership)
    return snapshots


def write_snapshots(snapshots: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for d, mem in sorted(snapshots.items()):
        yyyy_mm = d[:7]
        (OUT_DIR / f"sp500_{yyyy_mm}.csv").write_text("\n".join(sorted(mem)) + "\n")
        n += 1
    print(f"Wrote {n} snapshots to {OUT_DIR}/")


if __name__ == "__main__":
    snaps = build_snapshots()
    write_snapshots(snaps)
    total = set()
    for mem in snaps.values():
        total |= mem
    print(f"Total unique tickers across all snapshots: {len(total)}")
