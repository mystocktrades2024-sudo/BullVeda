#!/usr/bin/env python3
"""
ipo_calendar_nasdaq.py — Upcoming + recent IPOs.

PRIMARY source (free, no auth): https://api.nasdaq.com/api/ipo/calendar
FALLBACK source (free, no auth): SEC EDGAR full-text search
    https://efts.sec.gov/LATEST/search-index  (forms 424B4 = priced IPO
    final prospectus, S-1 = new registration / upcoming).

The NASDAQ endpoint is Akamai-fronted and intermittently times out / bot-walls
(open item DATA-BROKEN-IPO-CALENDAR). When it returns nothing this run, we fall
back to SEC EDGAR — an official, keyless, rate-limited (10 req/s) full-text
search that lists every IPO prospectus the day it is filed. Both are free per
the no-paid-data policy in CLAUDE.md.

Pulls the current month's IPO calendar; rotate plist daily to keep fresh.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "Mozilla/5.0 (SwingTrade scraper)"
# SEC requires a descriptive UA with contact per its fair-access policy.
SEC_UA = "SwingTrade IPO calendar (garimella.phaniraj@gmail.com)"


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


_EDGAR_TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,5})\)")


def fetch_ipo_edgar(days_back: int = 30, max_retries: int = 3) -> list[dict]:
    """FREE fallback — recent IPO filings from SEC EDGAR full-text search.

    424B4 = final prospectus filed at pricing (a *priced* IPO).
    S-1    = initial registration statement (an *upcoming* / filed IPO).

    Returns already-normalized rows in the same shape main() upserts, so it can be
    merged/substituted directly. No API key; SEC allows 10 req/s with a UA + contact.
    """
    import time
    import gzip
    end = date.today()
    start = end - timedelta(days=days_back)
    out: list[dict] = []
    for form, deal_type in (("424B4", "Priced"), ("S-1", "Filed")):
        url = ("https://efts.sec.gov/LATEST/search-index?"
               f"forms={form}&startdt={start.isoformat()}&enddt={end.isoformat()}")
        j = None
        for attempt in range(max_retries):
            if attempt > 0:
                time.sleep(2 ** attempt)
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": SEC_UA,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                })
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
            print(f"  ! EDGAR {form}: {last_err} (after {max_retries} retries)")
            continue
        hits = (((j or {}).get("hits") or {}).get("hits")) or []
        for hit in hits:
            src = hit.get("_source") or {}
            names = src.get("display_names") or []
            if not names:
                continue
            disp = names[0]  # "Company Name  (TICKER)  (CIK 0000000000)"
            name = re.sub(r"\s*\(.*", "", disp).strip()
            tkm = _EDGAR_TICKER_RE.search(disp)
            ticker = tkm.group(1) if tkm else None
            if ticker and ticker.upper().startswith("CIK"):
                ticker = None
            fdate = src.get("file_date")
            adsh = (src.get("adsh") or "").replace("-", "")
            cik = (src.get("ciks") or [""])[0].lstrip("0")
            src_url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/"
                       if cik and adsh else "")
            if not name:
                continue
            out.append({
                "ticker": (ticker or "").upper() or None,
                "company_name": name,
                "expected_date": fdate,
                "price_low": None,
                "price_high": None,
                "shares_offered": None,
                "exchange": None,
                "sync_key": h("ipo", name, fdate or ""),
                "raw_json": json.dumps({"form": form, "deal_type": deal_type,
                                        "source": "sec_edgar_fts",
                                        "source_url": src_url,
                                        "_source": src}, default=str),
            })
    # newest first; dedup by sync_key (424B4 wins over S-1 for the same deal)
    seen, dedup = set(), []
    for r in sorted(out, key=lambda x: (x["expected_date"] or ""), reverse=True):
        if r["sync_key"] in seen:
            continue
        seen.add(r["sync_key"])
        dedup.append(r)
    return dedup


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

    print(f"  Normalized {len(rows)} ipo_calendar rows from NASDAQ")

    # ── FREE fallback / augment: SEC EDGAR full-text search ──────────────────
    # If NASDAQ timed out (0 rows) fall back entirely to EDGAR; otherwise merge
    # EDGAR-only tickers so a partial NASDAQ response is still backfilled.
    edgar_rows = fetch_ipo_edgar(days_back=30 * max(args.months, 1))
    print(f"  EDGAR full-text search returned {len(edgar_rows)} IPO filings")
    if not rows:
        print("  NASDAQ empty — using SEC EDGAR as primary this run")
        rows = edgar_rows
    else:
        have = {r["sync_key"] for r in rows}
        added = [r for r in edgar_rows if r["sync_key"] not in have]
        rows.extend(added)
        print(f"  merged {len(added)} EDGAR-only rows (total {len(rows)})")

    if not args.apply:
        print("Dry-run"); return 0
    if not rows: return 0
    ok, fail = upsert(sb, "ipo_calendar", rows, "sync_key")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
