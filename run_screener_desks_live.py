#!/usr/bin/env python3
"""run_screener_desks_live.py — Schwab live-quote overlay for the Screener Desks tab.

Runs every 5 min via launchd (com.swingtrade.screener-desks-live). Self-gates to
market hours; one Schwab batch quote covers every ticker shown across all desks →
ZERO EODHD quota cost. Writes infra/prototype/screener_desks_live.json, which
/api/screener_desks merges as the live price/zone overlay (its file-mtime is folded
into the endpoint cache key, so a new overlay invalidates the cached books).

Overlay shape:
  {"refreshed_at": "<UTC ISO>", "n": <int>, "quotes": {TICKER: {price, prev_close}}}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "infra" / "prototype" / "screener_desks_live.json"


def main() -> None:
    try:
        from position_alerts import _is_market_hours, _get_schwab_batch
    except Exception as e:  # pragma: no cover
        print(f"import failed: {e}")
        return

    force = False
    import sys
    if "--force" in sys.argv:  # for manual testing off-hours
        force = True
    if not force and not _is_market_hours():
        print("off-hours — no-op")
        return

    try:
        import screener_desks as sd
        payload = sd.build_from_disk()
        tickers = sd.desk_tickers(payload)
    except Exception as e:
        print(f"desk build failed: {e}")
        return
    if not tickers:
        print("no desk tickers")
        return

    # Richer extraction than _get_schwab_batch: also grab totalVolume so the desks
    # can compute a time-adjusted LIVE RVOL (Breakout/Momentum volume checks).
    quotes = {}
    try:
        import schwab_client as _sc
        raw = _sc.get_quotes_batch(tickers[:500]) or {}
        for sym, blob in raw.items():
            if not isinstance(blob, dict):
                continue
            qb = blob.get("quote") or {}
            last = qb.get("lastPrice")
            if last is None:
                continue
            try:
                rec = {"price": round(float(last), 2)}
                pc = qb.get("closePrice")
                if pc is not None:
                    rec["prev_close"] = round(float(pc), 2)
                tv = qb.get("totalVolume")
                if tv is not None:
                    rec["volume"] = float(tv)
                quotes[sym.upper()] = rec
            except (TypeError, ValueError):
                continue
    except Exception as e:
        print(f"schwab fetch failed ({e}); falling back to price-only")
        quotes = _get_schwab_batch(tickers) or {}
    if not quotes:
        print("no Schwab quotes (market closed / token?)")
        return

    out = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(quotes),
        "quotes": quotes,
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(OUT)  # atomic swap
    print(f"wrote {len(quotes)}/{len(tickers)} live quotes → {OUT.name}")


if __name__ == "__main__":
    main()
