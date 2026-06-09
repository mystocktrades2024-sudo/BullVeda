"""eod_freshness.py — confirm EODHD has posted TODAY's EOD bar before the
EOD precompute heavy lift runs (Daily-Clock Open Risk #3).

Structural targets (T1/T2/T3) are a deterministic function of the FINAL daily
bar. If we compute them on a STALE bar (yesterday's close, because EODHD hasn't
posted today's EOD yet) every downstream target is wrong-by-one-day. This guard
refuses to run the EOD precompute until the bar is confirmed fresh.

Design constraints:
  - ~1 cheap EODHD call per poll (a single liquid ticker — SPY — via
    eodhd_client.eod with a short TTL). NOT bulk_eod (that's a full-exchange
    pull and would be wasteful on a 15-min poll loop).
  - "Fresh" == the last bar's date == today's US/Eastern *trading* date.
    On weekends/holidays the most recent trading date is the last weekday with
    a posted bar; we only ever poll on Mon-Fri (launchd Weekday gate), so the
    expected date is simply today's Eastern calendar date.
  - Never block forever: caller polls up to a max window, then skips cleanly.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_EASTERN = ZoneInfo("America/New_York")

# Probe ticker — most-liquid, always-posted, single bar.
FRESH_PROBE_TICKER = "SPY"


def expected_trading_date(now_et: datetime | None = None) -> str:
    """The trading date we expect EODHD to have a bar for, as 'YYYY-MM-DD'.

    On a weekday this is today's Eastern calendar date. On Sat/Sun (the loop
    shouldn't run then, but be defensive) we roll back to the prior Friday so
    a manual run doesn't spin forever waiting for a bar that will never post.
    Holidays are NOT special-cased — on a holiday no fresh bar posts and the
    poller will correctly time out and skip (don't run on a stale bar).
    """
    et = now_et or datetime.now(_EASTERN)
    d = et.date()
    wd = d.weekday()  # Mon=0 .. Sun=6
    if wd == 5:        # Saturday → Friday
        d = d - timedelta(days=1)
    elif wd == 6:      # Sunday → Friday
        d = d - timedelta(days=2)
    return d.isoformat()


def _last_bar_date(ticker: str = FRESH_PROBE_TICKER) -> str | None:
    """Most-recent posted EOD bar date for `ticker` ('YYYY-MM-DD') or None.

    Uses a SHORT cache TTL so a poll loop sees genuinely fresh data rather than
    a 12h-stale cached bar. One EODHD unit per uncached call.
    """
    import eodhd_client as eod
    # 90s TTL: short enough that successive 15-min polls always re-fetch, but
    # non-zero so a same-minute double-call (probe + a retry) is free.
    bars = eod.eod(ticker, cache_ttl=90)
    if not isinstance(bars, list) or not bars:
        return None
    last = bars[-1]
    if not isinstance(last, dict):
        return None
    d = last.get("date")
    return str(d) if d else None


def eod_bar_is_fresh(ticker: str = FRESH_PROBE_TICKER,
                     now_et: datetime | None = None,
                     verbose: bool = True) -> bool:
    """True iff EODHD's latest bar for `ticker` is dated == today's ET trading date.

    Costs ~1 EODHD call. Returns False (not fresh) when the bar is missing,
    unreadable, or still showing a prior date.
    """
    want = expected_trading_date(now_et)
    got = _last_bar_date(ticker)
    fresh = (got is not None and got == want)
    if verbose:
        et = (now_et or datetime.now(_EASTERN)).strftime("%Y-%m-%d %H:%M:%S %Z")
        state = "FRESH" if fresh else "STALE"
        print(f"  [eod-freshness] {et} · probe={ticker} "
              f"expected={want} got={got or 'none'} → {state}")
    return fresh


def wait_for_fresh_bar(ticker: str = FRESH_PROBE_TICKER,
                       poll_seconds: int = 900,
                       max_seconds: int = 10800,
                       sleep_fn=time.sleep) -> bool:
    """Poll every `poll_seconds` (default 15 min) until the EOD bar is fresh,
    up to `max_seconds` (default 3h). Returns True once fresh, False on timeout.

    ~1 EODHD call per poll. `sleep_fn` is injectable for tests.
    """
    # Bound by BOTH a max poll count and wall-clock, whichever comes first.
    # The count bound (ceil(max/poll)) makes the loop deterministic+testable and
    # immune to a clock that doesn't advance (e.g. a mocked sleep); the wall-clock
    # bound is the real-world cap in production.
    max_polls = max(1, -(-max_seconds // poll_seconds))  # ceil division
    deadline = time.time() + max_seconds
    poll = 0
    while True:
        poll += 1
        if eod_bar_is_fresh(ticker):
            print(f"  [eod-freshness] bar fresh on poll #{poll} — proceeding")
            return True
        if poll >= max_polls or time.time() + poll_seconds > deadline:
            elapsed = int(max_seconds / 60)
            print(f"  [eod-freshness] EOD bar not posted after ~{elapsed} min "
                  f"({poll} polls) — skipping (won't run on a stale bar)")
            return False
        print(f"  [eod-freshness] not fresh (poll #{poll}); sleeping "
              f"{poll_seconds // 60} min …")
        sleep_fn(poll_seconds)
