#!/usr/bin/env python3
"""snapshot_eodhd_quota.py — record EODHD's BILLED daily usage to a local history log.

Why: EODHD's /user endpoint only exposes the CURRENT day's apiRequests counter (resets
at 00:00 UTC). Our Supabase eodhd_quota_usage table logs scan HTTP calls, which
undercount billed units ~20-60x (bulk_eod bills ~2,900 per call; non-scan + crashed
scans aren't logged). So we had no reliable per-day BILLED history.

This job polls EODHD's own counter once/day just before the UTC reset (run ~16:50 PT via
com.swingtrade.eodhd-quota-snapshot.plist) and appends one line per UTC day to
data/eodhd_quota_history.jsonl. Idempotent per eodhd_date (last write wins → captures the
near-peak). One EODHD call/day. Read it back with:  python3 scripts/snapshot_eodhd_quota.py --show
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "eodhd_quota_history.jsonl"


def _api_key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if k:
        return k.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("EODHD_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _fetch() -> dict | None:
    key = _api_key()
    if not key:
        print("snapshot_eodhd_quota: no EODHD_API_KEY", file=sys.stderr)
        return None
    url = f"https://eodhd.com/api/user?api_token={key}&fmt=json"
    # Retry transient failures — the host has intermittent DNS blips ("[Errno 8]
    # nodename nor servname") that killed the 06-06/06-07 captures with a single
    # no-retry call. 5 attempts with backoff (and a fresh DNS lookup each time).
    import time as _t
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            if attempt < 4:
                _t.sleep(min(30, 3 * (attempt + 1)))  # 3s,6s,9s,12s
    print(f"snapshot_eodhd_quota: fetch failed after 5 attempts — {last}", file=sys.stderr)
    return None


def snapshot() -> int:
    d = _fetch()
    if not d:
        return 1
    used = d.get("apiRequests")
    limit = d.get("dailyRateLimit", 100000)
    eodhd_date = d.get("apiRequestsDate")  # EODHD's own UTC-day label
    if used is None:
        print("snapshot_eodhd_quota: no apiRequests in response", file=sys.stderr)
        return 1
    rec = {
        "eodhd_date": eodhd_date,
        "used": int(used),
        "limit": int(limit),
        "remaining": int(limit) - int(used),
        "pct_used": round(100.0 * int(used) / int(limit), 1),
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
    }
    # De-dupe per eodhd_date — keep the LAST (highest, near-peak) snapshot for that day.
    HIST.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if HIST.exists():
        for line in HIST.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("eodhd_date") != eodhd_date:
                    rows.append(r)
            except Exception:
                pass
    rows.append(rec)
    rows.sort(key=lambda r: str(r.get("eodhd_date") or ""))
    HIST.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"snapshot_eodhd_quota: {eodhd_date} → {rec['used']:,}/{rec['limit']:,} "
          f"({rec['pct_used']}%) · history now {len(rows)} days")
    return 0


def show(n: int = 14) -> int:
    if not HIST.exists():
        print("no history yet — run the snapshot first")
        return 0
    rows = [json.loads(x) for x in HIST.read_text().splitlines() if x.strip()]
    rows.sort(key=lambda r: str(r.get("eodhd_date") or ""), reverse=True)
    print(f"{'date (UTC)':<12} {'billed used':>12} {'pct':>6} {'remaining':>12}")
    for r in rows[:n]:
        print(f"{str(r.get('eodhd_date')):<12} {r.get('used', 0):>12,} "
              f"{r.get('pct_used', 0):>5}% {r.get('remaining', 0):>12,}")
    return 0


if __name__ == "__main__":
    if "--show" in sys.argv:
        sys.exit(show())
    sys.exit(snapshot())
