#!/usr/bin/env python3
"""Nightly congressional-flow refresh.

Rebuilds cache/congressional_trades.json + cache/congressional_picks.json from the
multi-source cascade in congress_trades.py (Quiver beta + Capitol Trades + House
Clerk / Senate eFD provenance). Congress data moves slowly (45-day STOCK Act
disclosure lag) so once-daily is ample — scheduled via
infra/launchd/com.swingtrade.congress-refresh.plist (07:00 PT).

Exit non-zero only if NO ticker-level source resolved (so launchd surfaces a real
outage); a degraded run where Quiver works but Capitol/Senate are walled is a
SUCCESS — that is the whole point of never-single-sourcing.

Run manually:  python3 scripts/refresh_congress.py [lookback_days]
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import congress_trades  # noqa: E402


def main() -> int:
    lookback = 90
    if len(sys.argv) > 1:
        try:
            lookback = int(sys.argv[1])
        except ValueError:
            pass
    out = congress_trades.build(lookback_days=lookback, verbose=True)
    meta = out.get("_meta", {})
    if not meta.get("ticker_level_ok"):
        print("[refresh_congress] FAIL — no ticker-level source resolved", file=sys.stderr)
        return 1
    print(f"[refresh_congress] OK — {meta.get('n_tickers')} tickers, "
          f"{meta.get('n_transactions_recent')} recent txns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
