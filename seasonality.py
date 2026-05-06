#!/usr/bin/env python3
"""AI-44 — Seasonality layer.

Well-known calendar biases applied as small, transparent nudges to the BUY
score bar:

  - May–Oct: "sell in May" — slightly raise BUY bar     (buy_min_add = +2)
  - Nov–Apr: seasonally stronger — slightly lower bar    (buy_min_add = -2)
  - Santa rally (last 5 trading days of Dec + first 2    (buy_min_add = -4)
    trading days of Jan): compounds, does NOT add
  - Halloween transition (last 3 trading days of Oct):   (buy_min_add =  0)
  - First 5 sessions after a major US holiday:           (buy_min_add = -1)
    earnings-season kickoff tailwind (applied additively
    to the monthly bias within clamp bounds)

The single public entry point is ``seasonality_adjustment()`` which returns
a small dict consumed by ``analysis.make_decision``.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# Major US market holidays (observed) used to flag the "5-session kickoff"
# tailwind. Dates are picked to cover the current + adjacent year so the
# helper is self-contained without pulling in pandas_market_calendars.
_MAJOR_HOLIDAYS: list[date] = [
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 5, 25), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1),
]


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _last_n_trading_days_of_month(year: int, month: int, n: int) -> list[date]:
    """Return the last n weekdays of the given month (approximate trading days)."""
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    out: list[date] = []
    d = first_next - timedelta(days=1)
    while len(out) < n:
        if _is_weekday(d):
            out.append(d)
        d -= timedelta(days=1)
    return out


def _first_n_trading_days_of_month(year: int, month: int, n: int) -> list[date]:
    out: list[date] = []
    d = date(year, month, 1)
    while len(out) < n:
        if _is_weekday(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _within_n_sessions_after_holiday(today: date, n: int = 5) -> bool:
    for h in _MAJOR_HOLIDAYS:
        if h > today:
            continue
        # count weekdays strictly after holiday up to and including today
        sessions = 0
        d = h + timedelta(days=1)
        while d <= today:
            if _is_weekday(d):
                sessions += 1
            d += timedelta(days=1)
        if 1 <= sessions <= n:
            return True
    return False


def seasonality_adjustment(today: Optional[date] = None) -> dict:
    """Return ``{'buy_min_add': int, 'label': str, 'bias': str}``.

    ``bias`` is one of ``'bullish' | 'bearish' | 'neutral'``.
    """
    if today is None:
        today = date.today()

    m = today.month
    y = today.year

    # Santa rally — last 5 trading days of Dec OR first 2 of Jan (compounds)
    santa_days = set(_last_n_trading_days_of_month(y, 12, 5))
    santa_days |= set(_first_n_trading_days_of_month(y, 1, 2))
    # Also cover Jan-of-this-year window when today is early January
    if m == 1:
        santa_days |= set(_last_n_trading_days_of_month(y - 1, 12, 5))
    if today in santa_days:
        return {"buy_min_add": -4, "label": "Santa rally (+bullish)", "bias": "bullish"}

    # Halloween transition — last 3 trading days of October
    if m == 10 and today in set(_last_n_trading_days_of_month(y, 10, 3)):
        return {"buy_min_add": 0, "label": "Halloween transition (neutral)", "bias": "neutral"}

    # Monthly bias
    if m in (11, 12, 1, 2, 3, 4):
        base_add, bias, label = -2, "bullish", "Nov-Apr strong season (bullish)"
    else:
        base_add, bias, label = +2, "bearish", "Sell-in-May period (bearish)"

    # Post-holiday kickoff tailwind — additive nudge, clamp to +/-4
    if _within_n_sessions_after_holiday(today, n=5):
        base_add -= 1
        label += " + post-holiday kickoff"
        if bias == "bearish" and base_add <= 0:
            bias = "neutral"
    base_add = max(-4, min(4, base_add))

    return {"buy_min_add": base_add, "label": label, "bias": bias}


if __name__ == "__main__":
    import json
    adj = seasonality_adjustment()
    print(json.dumps({"today": str(date.today()), **adj}, indent=2))
