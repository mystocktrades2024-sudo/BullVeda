#!/usr/bin/env python3
"""institutional_13f_sec.py — SEC EDGAR 13F-HR scraper for top fund holdings."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

UA = "SwingTrade-Research/1.0 (garimella.phaniraj@gmail.com)"

TOP_FUNDS = [
    ("0001067983", "Berkshire Hathaway"),
    ("0001350694", "Bridgewater Associates"),
    ("0001037389", "Citadel Advisors"),
    ("0001061165", "Two Sigma Investments"),
    ("0001135730", "Millennium Management"),
    ("0001423053", "Pershing Square Capital"),
    ("0001656456", "Tiger Global Management"),
    ("0001008474", "BlackRock Inc."),
    ("0001167483", "AQR Capital Management"),
    ("0001112693", "Coatue Management"),
]


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_submissions(cik: str) -> dict | None:
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        return json.loads(_fetch(url).decode("utf-8"))
    except Exception as e:
        print(f"    ! submissions {cik}: {e}")
        return None


def find_latest_13f(submissions: dict) -> tuple[str | None, str | None]:
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    for form, acc, dt in zip(forms, accs, dates):
        if form in ("13F-HR", "13F-HR/A"):
            return acc, dt
    return None, None


def fetch_infotable(cik: str, accession_no: str) -> list[dict]:
    cik_int = cik.lstrip("0") or "0"
    acc_no_clean = accession_no.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_clean}/"
    try:
        idx_html = _fetch(index_url).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    ! index: {e}")
        return []
    info_files = re.findall(r'href="([^"]+(?:infotable|InfoTable)\.xml)"', idx_html)
    if not info_files:
        return []
    info_path = info_files[0]
    info_url = ("https://www.sec.gov" + info_path) if info_path.startswith("/") else info_path
    try:
        xml_bytes = _fetch(info_url)
    except Exception as e:
        print(f"    ! infotable: {e}")
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        print(f"    ! xml parse: {e}")
        return []
    ns = {"i": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    info_elements = root.findall("i:infoTable", ns) if ns else root.findall("infoTable")
    holdings = []
    for it in info_elements:
        def gx(name):
            el = it.find(f"i:{name}", ns) if ns else it.find(name)
            return el.text.strip() if el is not None and el.text else None
        shares_amt = None
        sop = it.find("i:shrsOrPrnAmt", ns) if ns else it.find("shrsOrPrnAmt")
        if sop is not None:
            shares_el = sop.find("i:sshPrnamt", ns) if ns else sop.find("sshPrnamt")
            if shares_el is not None and shares_el.text:
                try: shares_amt = int(shares_el.text.strip())
                except: pass
        try: value = int(gx("value") or 0)
        except: value = None
        holdings.append({
            "name_of_issuer": gx("nameOfIssuer"),
            "cusip": gx("cusip"),
            "value_thousand": value,
            "shares": shares_amt,
            "put_call": gx("putCall"),
        })
    return holdings


def load_ticker_map() -> dict:
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        data = json.loads(_fetch(url).decode("utf-8"))
        name_to_ticker = {}
        for entry in data.values():
            name = (entry.get("title") or "").upper().strip()
            ticker = (entry.get("ticker") or "").upper().strip()
            if name and ticker:
                name_to_ticker[name] = ticker
        return name_to_ticker
    except Exception as e:
        print(f"  ! ticker map: {e}")
        return {}


def best_match_ticker(name: str, name_to_ticker: dict) -> str | None:
    if not name: return None
    name_u = name.upper().strip()
    if name_u in name_to_ticker: return name_to_ticker[name_u]
    for suf in (" INC", " CORP", " CO", " COM", " LTD", " LLC", " HLDGS", " HOLDINGS", " CL A", " CL B", " CLASS A", " CLASS B"):
        if name_u.endswith(suf):
            stub = name_u[:-len(suf)].strip()
            if stub in name_to_ticker: return name_to_ticker[stub]
    first = name_u.split(" ")[0]
    for full, t in name_to_ticker.items():
        if full.startswith(first + " ") and len(first) >= 4:
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-funds", type=int, default=5)
    args = ap.parse_args()

    sb = load_env_and_supabase()
    print(f"Loading SEC ticker map…")
    name_map = load_ticker_map()
    print(f"  loaded {len(name_map):,} ticker entries")

    all_rows = []
    seen_cik = set()
    for cik, fund_name in TOP_FUNDS[:args.max_funds]:
        if cik in seen_cik: continue
        seen_cik.add(cik)
        print(f"\n→ {fund_name} (CIK {cik})")
        subs = fetch_submissions(cik)
        if not subs: continue
        time.sleep(0.2)
        acc, dt = find_latest_13f(subs)
        if not acc:
            print(f"    no 13F-HR found"); continue
        print(f"    latest 13F-HR: {acc} ({dt})")
        time.sleep(0.2)
        holdings = fetch_infotable(cik, acc)
        print(f"    parsed {len(holdings)} holdings")
        mapped = 0
        for h_row in holdings:
            ticker = best_match_ticker(h_row.get("name_of_issuer", ""), name_map)
            if not ticker: continue
            mapped += 1
            all_rows.append({
                "filed_at": (dt or "1970-01-01") + "T00:00:00Z",
                "period_end": dt or "1970-01-01",
                "holder_name": fund_name,
                "holder_cik": cik,
                "ticker": ticker,
                "shares": h_row.get("shares"),
                "market_value": float(h_row.get("value_thousand") or 0) * 1000,
                "source": "sec_edgar_13f_hr",
                "raw_json": json.dumps(h_row),
            })
        print(f"    mapped {mapped} to tickers ({mapped*100//max(len(holdings),1)}%)")
        time.sleep(0.3)

    print(f"\nTotal mappable rows: {len(all_rows):,}")
    if not args.apply:
        print("Dry-run."); return 0
    if not all_rows:
        return 0
    for i, r in enumerate(all_rows):
        r["sync_key"] = h(r["holder_cik"], r["ticker"], r["period_end"], i)
    ok, fail = upsert(sb, "institutional_holdings", all_rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
