#!/usr/bin/env python3
"""
ipo_calendar_nasdaq.py — Upcoming + recent IPOs from NASDAQ.

Source (free, no auth): https://api.nasdaq.com/api/ipo/calendar

Pulls the current month's IPO calendar; rotate plist daily to keep fresh.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "Mozilla/5.0 (SwingTrade scraper)"


def fetch_ipo_month(yyyymm: str, max_retries: int = 3) -> list[dict]:
    url = f"https://api.nasdaq.com/api/ipo/calendar?date={yyyymm}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/market-activity/ipos",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    import time
    import gzip
    last_err = None
    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(2 ** attempt)  # 2s, 4s, 8s exponential backoff
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                j = json.loads(raw.decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            continue
    else:
        print(f"  ! {yyyymm}: {last_err} (after {max_retries} retries)")
        return []
    data = (j.get("data") or {})
    out: list[dict] = []
    for section in ("priced", "upcoming", "filed", "withdrawn"):
        sec = data.get(section) or {}
        rows = sec.get("rows") if isinstance(sec, dict) else None
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict):
                    r["_section"] = section
                    out.append(r)
    return out


def _parse_money(s):
    if not s: return None
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--months", type=int, default=3)
    args = ap.parse_args()
    sb = load_env_and_supabase()

    today = date.today()
    months = set()
    for back in range(args.months):
        m = today.month - back
        y = today.year
        while m < 1:
            m += 12; y -= 1
        months.add(f"{y}-{m:02d}")
    months = sorted(months)

    all_ipos: list[dict] = []
    for ym in months:
        ipos = fetch_ipo_month(ym)
        print(f"  {ym}: {len(ipos)} entries")
        all_ipos.extend(ipos)

    rows = []
    for ipo in all_ipos:
        ticker = (ipo.get("proposedTickerSymbol") or ipo.get("symbol") or "").upper().strip() or None
        name = ipo.get("companyName") or ipo.get("name")
        if not name:
            continue
        # Date can be in various fields
        expected = ipo.get("expectedPriceDate") or ipo.get("filedDate") or ipo.get("pricedDate")
        # NASDAQ uses MM/DD/YYYY
        if expected and "/" in expected:
            try:
                mm, dd, yy = expected.split("/")
                expected = f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
            except Exception:
                expected = None
        rows.append({
            "ticker": ticker,
            "company_name": name,
            "expected_date": expected,
            "price_low": _parse_money((ipo.get("proposedSharePrice") or "").split("-")[0] if "-" in str(ipo.get("proposedSharePrice","")) else ipo.get("proposedSharePrice")),
            "price_high": _parse_money((ipo.get("proposedSharePrice") or "").split("-")[-1] if "-" in str(ipo.get("proposedSharePrice","")) else ipo.get("proposedSharePrice")),
            "shares_offered": (lambda v: int(v) if v is not None else None)(_parse_money(ipo.get("sharesOffered"))),
            "exchange": ipo.get("proposedExchange"),
            "sync_key": h("ipo", name, expected or ""),
            "raw_json": json.dumps(ipo, default=str),
        })

    print(f"  Normalized {len(rows)} ipo_calendar rows")
    if not args.apply:
        print("Dry-run"); return 0
    if not rows: return 0
    ok, fail = upsert(sb, "ipo_calendar", rows, "sync_key")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
