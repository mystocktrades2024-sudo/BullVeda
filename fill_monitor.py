#!/usr/bin/env python3
"""AI-27: Order fill monitor — cancels unfilled orders after a time window.

Reads Alpaca open orders; for any submitted by executor.py that hasn't
filled within --max-minutes of submission, cancels it and logs a
"missed entry" row to cache/orders.jsonl.

Intended to run on a short cron (~every 5 min) during market hours.

Usage:
  python3 fill_monitor.py                      # default 5-min window
  python3 fill_monitor.py --max-minutes 10
  python3 fill_monitor.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent
_ORDERS_LOG = _ROOT / "cache" / "orders.jsonl"


def _fail(msg: str, code: int = 2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _make_client():
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        _fail("alpaca-py SDK not installed. pip install alpaca-py")
    try:
        from secrets_loader import alpaca_key, alpaca_secret
        k, s = alpaca_key(), alpaca_secret()
    except Exception as e:
        _fail(f"secrets_loader failed: {e}")
    if not k or not s:
        _fail("Alpaca keys missing from .env")
    return TradingClient(k, s, paper=True)


def _log(entry: dict) -> None:
    _ORDERS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _ORDERS_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=int, default=5,
                    help="Cancel orders older than this (default 5 min)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be canceled without canceling")
    args = ap.parse_args()

    client = _make_client()
    try:
        orders = client.get_orders()
    except Exception as e:
        _fail(f"Alpaca get_orders failed: {e}")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=args.max_minutes)
    canceled = expired = 0
    for o in orders:
        status = str(getattr(o, "status", "")).lower()
        if "filled" in status or status in ("canceled", "expired", "rejected"):
            continue
        created = getattr(o, "created_at", None) or getattr(o, "submitted_at", None)
        if not created:
            continue
        # Normalize to aware datetime
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_min = (now - created).total_seconds() / 60
        if created <= cutoff:
            expired += 1
            symbol = getattr(o, "symbol", "?")
            action = "WOULD_CANCEL" if args.dry_run else "CANCEL"
            print(f"  {action} {symbol:6s} age {age_min:.1f}min status={status}")
            if not args.dry_run:
                try:
                    client.cancel_order_by_id(getattr(o, "id", ""))
                    canceled += 1
                    _log({
                        "timestamp":  now.isoformat(),
                        "ticker":     symbol,
                        "action":     "canceled_unfilled",
                        "alpaca_order_id": str(getattr(o, "id", "")),
                        "age_minutes": round(age_min, 1),
                        "reason":     f"unfilled after {args.max_minutes} min",
                    })
                except Exception as e:
                    print(f"    ERROR canceling: {e}")

    print(f"\n{canceled} canceled, {expired} expired" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
