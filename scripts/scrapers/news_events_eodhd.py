#!/usr/bin/env python3
"""
news_events_eodhd.py — Pull recent news + sentiment per ticker from EODHD.

Source: EODHD /news (already paid). Active tickers only to respect quota.
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


def _key():
    return os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY") or ""


def fetch_news(ticker: str, since: str, limit: int = 50) -> list[dict]:
    url = f"https://eodhd.com/api/news?s={ticker}.US&api_token={_key()}&from={since}&limit={limit}&fmt=json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ! {ticker}: {e}")
        return []


def get_active_tickers(sb) -> list[str]:
    tickers: set[str] = set()
    for table in ["positions", "custom_tickers"]:
        try:
            for r in (sb.table(table).select("ticker").limit(500).execute().data or []):
                if r.get("ticker") and len(r["ticker"]) <= 6:
                    tickers.add(r["ticker"])
        except Exception:
            pass
    return sorted(tickers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max-tickers", type=int, default=30)
    args = ap.parse_args()

    sb = load_env_and_supabase()
    if not _key():
        print("✗ EODHD_API_TOKEN missing"); return 1
    tickers = get_active_tickers(sb)[:args.max_tickers]
    print(f"  Tickers: {len(tickers)}")
    since = (date.today() - timedelta(days=args.days)).isoformat()

    all_rows = []
    for tk in tickers:
        items = fetch_news(tk, since)
        for n in items:
            published = n.get("date") or n.get("publishedDate")
            headline = n.get("title")
            if not (published and headline):
                continue
            sent = n.get("sentiment") or {}
            polarity = None
            label = None
            if isinstance(sent, dict):
                polarity = sent.get("polarity")
                if polarity is not None:
                    try:
                        polarity = float(polarity)
                        label = "bullish" if polarity > 0.1 else "bearish" if polarity < -0.1 else "neutral"
                    except Exception:
                        polarity = None
            all_rows.append({
                "published_at": published,
                "ticker": tk,
                "headline": headline,
                "source": n.get("source") or "eodhd",
                "url": n.get("link"),
                "sentiment_score": polarity,
                "sentiment_label": label,
                "sync_key": h("nw", tk, published, headline[:40]),
                "raw_json": json.dumps(n, default=str),
            })
        time.sleep(0.05)

    print(f"  Collected {len(all_rows):,} news rows")
    if not args.apply:
        print("Dry-run"); return 0
    if not all_rows: return 0
    ok, fail = upsert(sb, "news_events", all_rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
