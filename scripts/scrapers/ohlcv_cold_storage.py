#!/usr/bin/env python3
"""
ohlcv_cold_storage.py — Nightly batch of EODHD per-ticker daily bars.

Pulls last N years for active tickers (positions + signal_log union) and
writes to ohlcv_daily. Idempotent via PK (ticker, bar_date).

Active-tickers-only keeps the EODHD quota in check. For full universe,
pass --universe sp500.
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
from _lib import load_env_and_supabase, upsert


def _key():
    return os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY") or ""


def fetch_eod(ticker: str, since: str) -> list[dict]:
    url = f"https://eodhd.com/api/eod/{ticker}.US?api_token={_key()}&from={since}&fmt=json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ! {ticker}: {e}")
        return []


def get_active_tickers(sb, universe: str) -> list[str]:
    tickers: set[str] = set()
    if universe in ("active", "all"):
        for table in ["positions", "custom_tickers"]:
            try:
                for r in (sb.table(table).select("ticker").limit(2000).execute().data or []):
                    if r.get("ticker") and len(r["ticker"]) <= 6:
                        tickers.add(r["ticker"])
            except Exception:
                pass
    if universe in ("sp500", "all"):
        try:
            for r in (sb.table("index_membership_pit").select("ticker").eq("index_name", "sp500").limit(600).execute().data or []):
                tickers.add(r["ticker"])
        except Exception:
            pass
    return sorted(tickers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--universe", choices=["active", "sp500", "all"], default="active")
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--max-tickers", type=int, default=50, help="Quota guardrail")
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not _key():
        print("✗ EODHD_API_TOKEN missing"); return 1
    tickers = get_active_tickers(sb, args.universe)
    if args.max_tickers and len(tickers) > args.max_tickers:
        print(f"  Capping at {args.max_tickers} (was {len(tickers)} — pass --max-tickers 0 to disable cap)")
        tickers = tickers[:args.max_tickers]
    print(f"  Universe: {args.universe} → {len(tickers)} tickers")
    since = (date.today() - timedelta(days=args.years * 365)).isoformat()

    total_bars = total_ok = total_fail = 0
    for tk in tickers:
        bars = fetch_eod(tk, since)
        if not bars:
            continue
        rows = []
        for b in bars:
            d = b.get("date")
            if not d:
                continue
            rows.append({
                "ticker": tk,
                "bar_date": d,
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "adjusted_close": b.get("adjusted_close"),
                "volume": b.get("volume"),
                "source": "eodhd",
            })
        ok, fail = upsert(sb, "ohlcv_daily", rows, "ticker,bar_date") if args.apply else (len(rows), 0)
        total_bars += len(rows); total_ok += ok; total_fail += fail
        if args.apply:
            time.sleep(0.05)
    print(f"\n  Total bars: {total_bars:,} · pushed: {total_ok:,} · failed: {total_fail:,}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
