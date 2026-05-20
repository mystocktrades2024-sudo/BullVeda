#!/usr/bin/env python3
"""Fetch upcoming IPOs + stock splits from EODHD calendar endpoints.

Writes cache/corporate_events.json which is then plumbed into the v2 dashboard
bundle (data.corporate_events) by infra/prototype/build_data.py. Frontend tab
'IPO · Splits' (renderEvents in kairos.html MarketsV2) reads from there.

Runs once per day. Idempotent. Failures don't break the scan.
"""
from __future__ import annotations
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "corporate_events.json"
sys.path.insert(0, str(BASE))


def fetch(days_ahead: int = 30) -> dict:
    """Fetch IPO + splits calendars from EODHD. Returns:

    {
      "_meta": {"generated_at": iso, "days_ahead": 30, "n_ipos": N, "n_splits": N},
      "ipos":   [...filtered to US-listed, sorted by start_date asc],
      "splits": [...filtered to US-listed, sorted by split_date asc],
    }
    """
    import eodhd_client as ec

    today = datetime.date.today().isoformat()
    end = (datetime.date.today() + datetime.timedelta(days=days_ahead)).isoformat()

    ipos_raw = ec.financial_events(from_date=today, to_date=end, event_type="ipos") or {}
    splits_raw = ec.financial_events(from_date=today, to_date=end, event_type="splits") or {}

    ipos = ipos_raw.get("ipos") if isinstance(ipos_raw, dict) else ipos_raw
    splits = splits_raw.get("splits") if isinstance(splits_raw, dict) else splits_raw

    # Filter to US-listed (code ends in .US or no exchange suffix)
    def is_us(row: dict) -> bool:
        code = (row.get("code") or "").upper()
        ex = (row.get("exchange") or "").upper()
        # IPO rows have explicit exchange field (NYSE/NASDAQ); splits rely on
        # the code suffix.
        if ex in ("NYSE", "NASDAQ", "NYSE ARCA", "BATS", "AMEX"):
            return True
        if code.endswith(".US"):
            return True
        # Plain US tickers without suffix
        if "." not in code:
            return True
        return False

    ipos_us = [r for r in (ipos or []) if is_us(r)]
    splits_us = [r for r in (splits or []) if is_us(r)]

    # Sort
    ipos_us.sort(key=lambda r: r.get("start_date") or r.get("filing_date") or "")
    splits_us.sort(key=lambda r: r.get("split_date") or "")

    # Annotate split ratio for convenience (new/old, e.g., 2-for-1)
    for r in splits_us:
        old = r.get("old_shares") or 0
        new = r.get("new_shares") or 0
        if old and new:
            r["_ratio"] = f"{new}-for-{old}"
            r["_is_reverse"] = old > new
        else:
            r["_ratio"] = None
            r["_is_reverse"] = False

    # Annotate IPO deal size for convenience
    for r in ipos_us:
        shares = r.get("shares") or 0
        offer = r.get("offer_price") or r.get("price_to") or r.get("price_from") or 0
        r["_deal_size_m"] = round(shares * offer / 1e6, 1) if shares and offer else None

    return {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "days_ahead": days_ahead,
            "n_ipos": len(ipos_us),
            "n_splits": len(splits_us),
            "source": "eodhd.calendar.ipos+splits",
        },
        "ipos": ipos_us[:60],
        "splits": splits_us[:120],
    }


def main(argv: list[str]) -> int:
    days = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 30
    try:
        out = fetch(days)
    except Exception as e:
        print(f"[corporate_events] fetch failed: {e}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    m = out["_meta"]
    print(f"[corporate_events] wrote {OUT} · {m['n_ipos']} IPOs · {m['n_splits']} splits · {days}d window")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
