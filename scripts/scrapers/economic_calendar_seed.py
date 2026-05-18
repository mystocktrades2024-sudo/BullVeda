#!/usr/bin/env python3
"""economic_calendar_seed.py — Generate US economic data release calendar
from recurring schedule (no API key required)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_env_and_supabase, h, upsert


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _nth_business_day(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    count = 0
    while count < n:
        if d.weekday() < 5:
            count += 1
            if count == n: return d
        d += timedelta(days=1)
    return d


def _last_friday(year: int, month: int) -> date:
    next_m = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = next_m - timedelta(days=1)
    while last.weekday() != 4:
        last -= timedelta(days=1)
    return last


def _mid_month(year: int, month: int, target_day: int = 15) -> date:
    d = date(year, month, target_day)
    while d.weekday() != 3:  # bias to Thursday
        d += timedelta(days=1)
    return d


def generate_events(months_ahead: int = 4) -> list[dict]:
    today = date.today()
    out = []
    for m_off in range(months_ahead):
        year = today.year
        month = today.month + m_off
        while month > 12:
            month -= 12; year += 1
        out.append({"name": "NFP", "label": "Nonfarm Payrolls",
                    "date": _first_friday(year, month), "time": "8:30 ET", "impact": "high"})
        cpi = _nth_business_day(year, month, 8)
        out.append({"name": "CPI", "label": "Consumer Price Index",
                    "date": cpi, "time": "8:30 ET", "impact": "high"})
        out.append({"name": "PPI", "label": "Producer Price Index",
                    "date": cpi + timedelta(days=1), "time": "8:30 ET", "impact": "medium"})
        out.append({"name": "RetailSales", "label": "Retail Sales",
                    "date": _mid_month(year, month, 14), "time": "8:30 ET", "impact": "high"})
        out.append({"name": "PCE", "label": "PCE Price Index",
                    "date": _last_friday(year, month), "time": "8:30 ET", "impact": "high"})
        out.append({"name": "ISM_Mfg", "label": "ISM Manufacturing PMI",
                    "date": _nth_business_day(year, month, 1), "time": "10:00 ET", "impact": "high"})
        out.append({"name": "ISM_Svc", "label": "ISM Services PMI",
                    "date": _nth_business_day(year, month, 3), "time": "10:00 ET", "impact": "high"})
        if month in (1, 4, 7, 10):
            gdp = date(year, month, 28)
            while gdp.weekday() != 3:
                gdp += timedelta(days=1)
            out.append({"name": "GDP", "label": "GDP (Advance Estimate)",
                        "date": gdp, "time": "8:30 ET", "impact": "high"})
    return [e for e in out if e["date"] >= today]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--months", type=int, default=4)
    args = ap.parse_args()
    sb = load_env_and_supabase()
    events = generate_events(args.months)
    print(f"  Generated {len(events)} upcoming events ({args.months} months ahead)")
    rows = []
    for e in events:
        hour, minute = e["time"].split()[0].split(":")
        release_dt = datetime.combine(e["date"], datetime.min.time()).replace(
            hour=int(hour), minute=int(minute), tzinfo=timezone.utc)
        rows.append({
            "release_at": release_dt.isoformat(),
            "event_name": e["name"],
            "actual": None, "forecast": None, "previous": None,
            "impact": e["impact"], "country": "US",
            "source": "seed_recurring_schedule",
            "sync_key": h("ec", e["date"].isoformat(), e["name"]),
            "raw_json": json.dumps({"name": e["name"], "label": e["label"],
                                     "date": e["date"].isoformat()}),
        })
    if not args.apply:
        for r in rows[:5]:
            print(f"  · {r['release_at'][:10]}  {r['event_name']:12s}  {r['impact']}")
        print(f"  ... and {len(rows)-5} more events (dry-run)")
        return 0
    ok, fail = upsert(sb, "economic_calendar", rows, "sync_key")
    print(f"  pushed={ok:,} failed={fail:,}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
