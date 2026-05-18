#!/usr/bin/env python3
"""Flush in-process EODHD endpoint counters to Supabase `eodhd_quota_usage`.

Designed to be invoked at end of every scan (or by a daily plist tail-step).
Idempotent on (bucket_date, endpoint) — repeated calls overwrite the day's totals.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def main() -> int:
    _load_dotenv()
    sys.path.insert(0, str(ROOT))
    try:
        import eodhd_client
    except Exception as e:
        print(f"eodhd_client import failed: {e}")
        return 1

    stats = eodhd_client.get_endpoint_stats()
    if not stats:
        print("No EODHD endpoint counters in this process — nothing to flush.")
        return 0

    print(f"Flushing {len(stats)} endpoint buckets:")
    for cls, counts in sorted(stats.items()):
        n = counts.get("network", 0)
        c = counts.get("cache_hit", 0)
        print(f"  {cls:20s}  network={n:5d}  cache_hit={c:5d}")

    result = eodhd_client.flush_quota_to_supabase()
    print(f"\nResult: pushed={result['pushed']} failed={result['failed']}")
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
