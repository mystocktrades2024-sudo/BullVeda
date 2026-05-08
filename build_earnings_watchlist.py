#!/usr/bin/env python3
"""
build_earnings_watchlist.py — pre-earnings watchlist builder.

For each US ticker reporting in the next 10 days, captures:
  ticker, report_date, days_to_earnings, before_after_market, estimate

Output: data/earnings_watchlist.json (overwritten daily).

Wired into swing_trade.py pre-screen so these tickers are GUARANTEED
inclusion in the analysis universe regardless of pre-screen score.
This catches names like INOD that were consolidating in the pre-screen
ranking but had a known catalyst within 10 days.

Schedule:
  Daily 5:30am PT via launchd, before the morning scan.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "earnings_watchlist.log"
OUT_FILE = BASE / "data" / "earnings_watchlist.json"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [earnings_watchlist] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _is_us_ticker(code: str) -> bool:
    """EODHD codes are 'AAPL.US', 'TITAN.BSE', 'V02.F', etc.
    US tickers either have .US suffix or no suffix at all."""
    if not code:
        return False
    if "." not in code:
        return True
    suffix = code.rsplit(".", 1)[1].upper()
    return suffix in ("US",)


def _strip_suffix(code: str) -> str:
    return code.split(".")[0].upper() if code else ""


def main(days_ahead: int = 10) -> int:
    # Lazy-load .env so SCHWAB_APP_KEY etc. are present (not used here, but
    # keeps the env consistent with other scripts).
    for line in (BASE / ".env").read_text().splitlines() if (BASE / ".env").exists() else []:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    today = date.today()
    end   = today + timedelta(days=days_ahead)

    log.info(f"Fetching EODHD earnings calendar {today} → {end} ({days_ahead}d)")
    import eodhd_client as e
    raw = e.earnings_calendar(from_date=str(today), to_date=str(end))
    if not isinstance(raw, dict):
        log.error(f"earnings_calendar returned non-dict: {type(raw)}")
        return 1
    entries = raw.get("earnings") or raw.get("data") or []
    log.info(f"Total earnings entries (global): {len(entries)}")

    # Filter to US + dedupe (some symbols appear multiple times)
    seen: set[str] = set()
    out: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code", "")
        if not _is_us_ticker(code):
            continue
        ticker = _strip_suffix(code)
        if ticker in seen or not ticker:
            continue
        seen.add(ticker)
        rep_date = entry.get("report_date")
        if not rep_date:
            continue
        try:
            d_to = (datetime.strptime(rep_date, "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if d_to < 0 or d_to > days_ahead:
            continue
        out.append({
            "ticker":              ticker,
            "report_date":         rep_date,
            "days_to_earnings":    d_to,
            "before_after_market": entry.get("before_after_market") or "",
            "estimate":            entry.get("estimate"),
            "actual":              entry.get("actual"),
            "currency":            entry.get("currency") or "USD",
        })

    out.sort(key=lambda x: (x["days_to_earnings"], x["ticker"]))
    payload = {
        "generated_at":    datetime.now().isoformat(),
        "window_days":     days_ahead,
        "from_date":       str(today),
        "to_date":         str(end),
        "total_us":        len(out),
        "watchlist":       out,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2, default=str))

    log.info(f"Wrote {OUT_FILE.name}: {len(out)} US tickers reporting in next {days_ahead}d")
    log.info(f"  by day-bucket: {dict([(d, sum(1 for x in out if x['days_to_earnings'] == d)) for d in range(0, days_ahead + 1)])}")
    if out:
        next5 = ", ".join("{}({}d)".format(x["ticker"], x["days_to_earnings"]) for x in out[:5])
        log.info(f"  next 5 reporting: {next5}")
    return 0


if __name__ == "__main__":
    sys.exit(main(days_ahead=10))
