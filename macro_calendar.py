"""
macro_calendar.py — Block new entries on major macro release days.

Per Phase-2 feedback (2026-04-30) item #21: don't open new Swing positions
day-of FOMC, CPI, NFP, PCE releases. The market often gaps unpredictably
on these prints, making 1.25× ATR stops meaningless.

Hardcoded calendar covers Q2 2026 forward. Refresh quarterly via FRED API
or Bureau of Labor Statistics calendar (manual update for now).

Public API:
    is_macro_blackout(date=None) -> tuple[bool, str | None]
    next_macro_event(date=None) -> dict | None
    macro_events_in_range(start, end) -> list[dict]

Usage in pre_trade_gate:
    blocked, reason = macro_calendar.is_macro_blackout()
    if blocked:
        reasons.append(f"HARD: macro blackout — {reason}")
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

# ── Hardcoded calendar (refresh quarterly) ──────────────────────────────────
# Source: Federal Reserve, BLS, BEA published calendars (verify before each
# quarter). All dates US Eastern (FOMC announcements typically 2pm ET).

_MACRO_EVENTS_2026: list[dict] = [
    # FOMC rate decisions (8 per year, scheduled Tue/Wed)
    {"date": "2026-01-28", "type": "FOMC", "label": "Fed rate decision (Jan)"},
    {"date": "2026-03-18", "type": "FOMC", "label": "Fed rate decision (Mar)"},
    {"date": "2026-04-29", "type": "FOMC", "label": "Fed rate decision (Apr)"},
    {"date": "2026-06-17", "type": "FOMC", "label": "Fed rate decision (Jun)"},
    {"date": "2026-07-29", "type": "FOMC", "label": "Fed rate decision (Jul)"},
    {"date": "2026-09-16", "type": "FOMC", "label": "Fed rate decision (Sep)"},
    {"date": "2026-11-04", "type": "FOMC", "label": "Fed rate decision (Nov)"},
    {"date": "2026-12-16", "type": "FOMC", "label": "Fed rate decision (Dec)"},

    # CPI releases (monthly, ~10-15th)
    {"date": "2026-01-13", "type": "CPI", "label": "CPI (Dec data)"},
    {"date": "2026-02-11", "type": "CPI", "label": "CPI (Jan data)"},
    {"date": "2026-03-12", "type": "CPI", "label": "CPI (Feb data)"},
    {"date": "2026-04-10", "type": "CPI", "label": "CPI (Mar data)"},
    {"date": "2026-05-13", "type": "CPI", "label": "CPI (Apr data)"},
    {"date": "2026-06-11", "type": "CPI", "label": "CPI (May data)"},
    {"date": "2026-07-15", "type": "CPI", "label": "CPI (Jun data)"},
    {"date": "2026-08-12", "type": "CPI", "label": "CPI (Jul data)"},
    {"date": "2026-09-10", "type": "CPI", "label": "CPI (Aug data)"},
    {"date": "2026-10-14", "type": "CPI", "label": "CPI (Sep data)"},
    {"date": "2026-11-12", "type": "CPI", "label": "CPI (Oct data)"},
    {"date": "2026-12-10", "type": "CPI", "label": "CPI (Nov data)"},

    # NFP / Jobs report (first Friday of month)
    {"date": "2026-01-02", "type": "NFP", "label": "Non-Farm Payrolls (Dec)"},
    {"date": "2026-02-06", "type": "NFP", "label": "Non-Farm Payrolls (Jan)"},
    {"date": "2026-03-06", "type": "NFP", "label": "Non-Farm Payrolls (Feb)"},
    {"date": "2026-04-03", "type": "NFP", "label": "Non-Farm Payrolls (Mar)"},
    {"date": "2026-05-01", "type": "NFP", "label": "Non-Farm Payrolls (Apr)"},
    {"date": "2026-06-05", "type": "NFP", "label": "Non-Farm Payrolls (May)"},
    {"date": "2026-07-02", "type": "NFP", "label": "Non-Farm Payrolls (Jun)"},
    {"date": "2026-08-07", "type": "NFP", "label": "Non-Farm Payrolls (Jul)"},
    {"date": "2026-09-04", "type": "NFP", "label": "Non-Farm Payrolls (Aug)"},
    {"date": "2026-10-02", "type": "NFP", "label": "Non-Farm Payrolls (Sep)"},
    {"date": "2026-11-06", "type": "NFP", "label": "Non-Farm Payrolls (Oct)"},
    {"date": "2026-12-04", "type": "NFP", "label": "Non-Farm Payrolls (Nov)"},

    # PCE inflation (monthly, end of month)
    {"date": "2026-01-30", "type": "PCE", "label": "PCE inflation (Dec)"},
    {"date": "2026-02-27", "type": "PCE", "label": "PCE inflation (Jan)"},
    {"date": "2026-03-27", "type": "PCE", "label": "PCE inflation (Feb)"},
    {"date": "2026-04-30", "type": "PCE", "label": "PCE inflation (Mar)"},
    {"date": "2026-05-29", "type": "PCE", "label": "PCE inflation (Apr)"},
    {"date": "2026-06-26", "type": "PCE", "label": "PCE inflation (May)"},
    {"date": "2026-07-31", "type": "PCE", "label": "PCE inflation (Jun)"},
    {"date": "2026-08-28", "type": "PCE", "label": "PCE inflation (Jul)"},
    {"date": "2026-09-25", "type": "PCE", "label": "PCE inflation (Aug)"},
    {"date": "2026-10-30", "type": "PCE", "label": "PCE inflation (Sep)"},
    {"date": "2026-11-25", "type": "PCE", "label": "PCE inflation (Oct)"},
    {"date": "2026-12-23", "type": "PCE", "label": "PCE inflation (Nov)"},
]


def _today() -> _dt.date:
    return _dt.date.today()


def _parse(d) -> _dt.date:
    if isinstance(d, _dt.date):
        return d
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, str):
        return _dt.datetime.strptime(d[:10], "%Y-%m-%d").date()
    raise ValueError(f"unsupported date type: {type(d)}")


def is_macro_blackout(date: Optional["_dt.date | str"] = None,
                       lookahead_days: int = 0,
                       morning_after: bool = True) -> tuple[bool, Optional[str]]:
    """
    Returns (blocked, reason). True if `date` (default today) is on a major
    macro release day OR — if morning_after=True — the trading day immediately
    after a major release (gap risk persists).

    lookahead_days: extend window forward (e.g. 1 = also block day-before).
    """
    target = _parse(date) if date else _today()

    # Blackout window: same day, optionally morning after, and lookahead
    blackout_dates: dict[_dt.date, dict] = {}
    for ev in _MACRO_EVENTS_2026:
        ev_date = _parse(ev["date"])
        # Same-day = blackout
        blackout_dates[ev_date] = ev
        # Morning-after = next calendar day (rough — should use trading day)
        if morning_after:
            next_day = ev_date + _dt.timedelta(days=1)
            if next_day not in blackout_dates:
                blackout_dates[next_day] = {**ev, "label": ev["label"] + " (morning after)"}
        # Lookahead
        for n in range(1, lookahead_days + 1):
            d = ev_date - _dt.timedelta(days=n)
            if d not in blackout_dates:
                blackout_dates[d] = {**ev, "label": ev["label"] + f" (T-{n})"}

    if target in blackout_dates:
        ev = blackout_dates[target]
        return True, f"{ev['type']}: {ev['label']}"
    return False, None


def next_macro_event(date: Optional["_dt.date | str"] = None) -> Optional[dict]:
    """Return the next upcoming macro event after `date` (default today)."""
    target = _parse(date) if date else _today()
    upcoming = [
        ev for ev in _MACRO_EVENTS_2026
        if _parse(ev["date"]) >= target
    ]
    if not upcoming:
        return None
    upcoming.sort(key=lambda e: _parse(e["date"]))
    nxt = dict(upcoming[0])
    nxt["days_until"] = (_parse(nxt["date"]) - target).days
    return nxt


def macro_events_in_range(start: "_dt.date | str",
                          end: "_dt.date | str") -> list[dict]:
    """List events in [start, end] inclusive."""
    s = _parse(start)
    e = _parse(end)
    return [ev for ev in _MACRO_EVENTS_2026 if s <= _parse(ev["date"]) <= e]
