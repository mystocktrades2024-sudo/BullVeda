#!/usr/bin/env python3
"""
corporate_actions_eodhd.py — Splits + dividends from EODHD (already paid for).

Populates `corporate_actions` table for tickers in tickers_master OR
the union of (positions, signal_log, custom_tickers). Limits to last 5y.

Usage: python3 scripts/scrapers/corporate_actions_eodhd.py --apply --tickers AAPL,MSFT
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert

EODHD_BASE = "https://eodhd.com/api"


def _api_key() -> str:
    return os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY") or ""


def fetch_splits(ticker: str, since: str) -> list[dict]:
    url = f"{EODHD_BASE}/splits/{ticker}.US?api_token={_api_key()}&from={since}&fmt=json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_dividends(ticker: str, since: str) -> list[dict]:
    url = f"{EODHD_BASE}/div/{ticker}.US?api_token={_api_key()}&from={since}&fmt=json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _parse_split_ratio(s: str) -> float | None:
    # "2.000000/1.000000" → 2.0  ; "1/2" reverse → 0.5
    try:
        if "/" in s:
            num, den = s.split("/", 1)
            return float(num) / float(den)
        return float(s)
    except Exception:
        return None


def get_active_tickers(sb) -> set[str]:
    """Union of tickers actually in our portfolio + signal log + custom."""
    tickers: set[str] = set()
    for table in ["positions", "custom_tickers"]:
        try:
            for r in (sb.table(table).select("ticker").limit(1000).execute().data or []):
                if r.get("ticker"):
                    tickers.add(r["ticker"])
        except Exception:
            pass
    return tickers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tickers", default="", help="Comma-separated; default = active tickers from Supabase")
    ap.add_argument("--years", type=int, default=5)
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not _api_key():
        print("✗ EODHD_API_TOKEN missing in .env"); return 1

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = sorted(get_active_tickers(sb))
    print(f"  Tickers: {len(tickers)}  (first 10: {tickers[:10]})")
    since = (date.today() - timedelta(days=args.years * 365)).isoformat()

    all_rows: list[dict] = []
    for tk in tickers:
        for s in fetch_splits(tk, since):
            ratio = _parse_split_ratio(s.get("split") or "")
            if not s.get("date") or not ratio:
                continue
            all_rows.append({
                "ticker": tk,
                "action_type": "split",
                "ex_date": s["date"],
                "ratio": ratio,
                "source": "eodhd",
                "sync_key": h("ca", tk, "split", s["date"]),
                "raw_json": json.dumps(s),
            })
        for d in fetch_dividends(tk, since):
            if not d.get("date") or d.get("value") is None:
                continue
            all_rows.append({
                "ticker": tk,
                "action_type": "dividend",
                "ex_date": d["date"],
                "record_date": d.get("recordDate"),
                "pay_date": d.get("paymentDate"),
                "cash_amount": float(d.get("value") or 0),
                "currency": d.get("currency") or "USD",
                "source": "eodhd",
                "sync_key": h("ca", tk, "div", d["date"]),
                "raw_json": json.dumps(d),
            })
        time.sleep(0.1)  # rate-limit friendliness

    print(f"  Collected {len(all_rows):,} corporate-action rows")
    if not args.apply:
        print("Dry-run"); return 0
    ok, fail = upsert(sb, "corporate_actions", all_rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
