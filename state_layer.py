"""
state_layer.py — Single read shim for SwingTrade canonical state.

The plan from Phase B (Mode 1 → Mode 2 migration): all state reads in the app
funnel through this module. Behind the shim we can flip between JSON-canonical
(today, Mode 1) and Supabase-canonical (Mode 2) without changing a single
caller.

Today (Mode 1):  reads come from JSON. Supabase calls are not invoked.
Mode 2 (later):  reads try Supabase first, fall back to JSON if Supabase is
                  unreachable or returns nothing.

5-second LRU cache reduces hot-path read amplification — `_load_state()` is
called 25+ times per scan in portfolio_tracker.py alone; the cache collapses
those into 1 disk hit (or 1 network hit in Mode 2).

This file is currently UNUSED. It's checked in as scaffolding for Phase B.1.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

# In-process cache: {key: (value, fetched_at_monotonic)}
_CACHE: dict = {}
_LOCK = RLock()
_CACHE_TTL_SECONDS = 5.0


def _cache_get(key: str):
    with _LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        value, fetched_at = entry
        if time.monotonic() - fetched_at > _CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value) -> None:
    with _LOCK:
        _CACHE[key] = (value, time.monotonic())


def cache_invalidate(key: str | None = None) -> None:
    """Drop one cache key, or the whole cache if key is None."""
    with _LOCK:
        if key is None:
            _CACHE.clear()
        else:
            _CACHE.pop(key, None)


def _read_supabase_first() -> bool:
    """Mode 2 flag — currently always False until B.2 lands."""
    return os.environ.get("SUPABASE_MODE", "1") == "2"


# =========================================================================
# Public accessors — every state read in the app should funnel here
# =========================================================================

def load_portfolio_state() -> dict:
    """Return the singleton portfolio_state. Today reads JSON; Mode 2 reads Supabase."""
    cached = _cache_get("portfolio_state")
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                row = sb.table("portfolio_state").select("*").eq("id", 1).execute().data
                if row:
                    state = _supabase_pf_row_to_full_state(row[0])
                    _cache_set("portfolio_state", state)
                    return state
        except Exception:
            pass  # fall through to JSON

    # JSON path (canonical in Mode 1)
    path = DATA_DIR / "portfolio_state.json"
    if path.exists():
        try:
            state = json.loads(path.read_text())
            _cache_set("portfolio_state", state)
            return state
        except Exception:
            pass
    return {"equity": 0, "cash": 0, "margin_reserved": 0, "positions": [], "closed_trades": []}


def load_signal_log(since_id: int | None = None, limit: int | None = None) -> list[dict]:
    """Return signal log entries. Optional filtering by id and limit (Supabase only)."""
    cache_key = f"signal_log:{since_id}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                q = sb.table("signal_log").select("*").order("id")
                if since_id:
                    q = q.gt("id", since_id)
                if limit:
                    q = q.limit(limit)
                rows = q.execute().data or []
                _cache_set(cache_key, rows)
                return rows
        except Exception:
            pass

    path = DATA_DIR / "signal_log.json"
    if path.exists():
        try:
            entries = json.loads(path.read_text())
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []
    else:
        entries = []

    if limit:
        entries = entries[-limit:]
    _cache_set(cache_key, entries)
    return entries


def load_custom_tickers() -> list[str]:
    """Return user's custom-tracked tickers (a flat list of symbols)."""
    cached = _cache_get("custom_tickers")
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                rows = sb.table("custom_tickers").select("ticker").execute().data or []
                tickers = [r["ticker"] for r in rows if r.get("ticker")]
                _cache_set("custom_tickers", tickers)
                return tickers
        except Exception:
            pass

    path = DATA_DIR / "custom_tracked.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            raw = d.get("tickers") or [] if isinstance(d, dict) else []
            # JSON entries can be either bare strings or dicts with {ticker, entry_price, ...}
            tickers = [t if isinstance(t, str) else t.get("ticker") for t in raw]
            tickers = [t for t in tickers if t]  # drop None/empty
            _cache_set("custom_tickers", tickers)
            return tickers
        except Exception:
            pass
    return []


def load_alert_log() -> dict:
    """Return alert dedup log: {alert_key: last_sent_date_str}."""
    cached = _cache_get("alert_log")
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                rows = sb.table("alert_log").select("alert_key,last_sent_date").execute().data or []
                d = {r["alert_key"]: r["last_sent_date"] for r in rows}
                _cache_set("alert_log", d)
                return d
        except Exception:
            pass

    path = DATA_DIR / "alert_sent_log.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            if isinstance(d, dict):
                _cache_set("alert_log", d)
                return d
        except Exception:
            pass
    return {}


def load_scan_health(limit: int = 100) -> list[dict]:
    """Return last N scan_health entries, oldest→newest."""
    cache_key = f"scan_health:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                rows = sb.table("scan_health").select("*").order("id", desc=True).limit(limit).execute().data or []
                rows.reverse()
                _cache_set(cache_key, rows)
                return rows
        except Exception:
            pass

    path = DATA_DIR / "scan_health.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            history = list(d.get("history") or []) if isinstance(d, dict) else []
            history = history[-limit:]
            _cache_set(cache_key, history)
            return history
        except Exception:
            pass
    return []


def load_gap_events() -> list[dict]:
    cached = _cache_get("gap_events")
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                rows = sb.table("gap_events").select("*").execute().data or []
                _cache_set("gap_events", rows)
                return rows
        except Exception:
            pass

    path = DATA_DIR / "gap_events.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            if isinstance(d, list):
                _cache_set("gap_events", d)
                return d
        except Exception:
            pass
    return []


def load_paper_trading_config() -> dict:
    cached = _cache_get("paper_trading_config")
    if cached is not None:
        return cached

    if _read_supabase_first():
        try:
            from supabase_client import sb_client
            sb = sb_client()
            if sb is not None:
                rows = sb.table("paper_trading_config").select("*").eq("id", 1).execute().data or []
                if rows:
                    _cache_set("paper_trading_config", rows[0])
                    return rows[0]
        except Exception:
            pass

    path = DATA_DIR / "paper_trading_start.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            if isinstance(d, dict):
                _cache_set("paper_trading_config", d)
                return d
        except Exception:
            pass
    return {}


# =========================================================================
# Helpers — reconstruct the JSON-shape state from a Supabase row + child tables
# =========================================================================

def _supabase_pf_row_to_full_state(row: dict) -> dict:
    """Build the full portfolio_state dict (matching JSON shape) from Supabase.

    The portfolio_state row is a singleton with equity/cash/etc. The
    positions/closed_trades/equity_curve/equity_audit lists live in their
    own tables and need to be joined back together for the JSON-shape that
    callers expect.
    """
    try:
        from supabase_client import sb_client
        sb = sb_client()
        if sb is None:
            return row

        positions = sb.table("positions").select("*").execute().data or []
        closed = sb.table("closed_trades").select("*").execute().data or []
        eq_curve = sb.table("equity_curve").select("date,equity").order("id").execute().data or []
        audit = sb.table("equity_audit").select("*").order("id").execute().data or []
        mpl = sb.table("monthly_pnl").select("year_month,pnl").execute().data or []

        return {
            "equity": row.get("equity"),
            "cash": row.get("cash"),
            "margin_reserved": row.get("margin_reserved"),
            "_last_saved": row.get("updated_at"),
            "positions": [_drop_pk(p) for p in positions],
            "closed_trades": [_drop_pk(c) for c in closed],
            "equity_curve": eq_curve,
            "equity_audit": audit,
            "monthly_pnl": {m["year_month"]: m["pnl"] for m in mpl},
        }
    except Exception:
        return row


def _drop_pk(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "id"}


def healthcheck() -> dict:
    """Return shim status — useful for /diagnostics endpoint."""
    return {
        "mode": os.environ.get("SUPABASE_MODE", "1"),
        "supabase_first": _read_supabase_first(),
        "cache_ttl_sec": _CACHE_TTL_SECONDS,
        "cache_keys": list(_CACHE.keys()),
    }


if __name__ == "__main__":
    import json as _j
    # Smoke test
    print(_j.dumps(healthcheck(), indent=2))
    print(f"\nportfolio: equity=${load_portfolio_state().get('equity', 0):.2f}")
    print(f"signals (last 5): {len(load_signal_log(limit=5))} rows")
    print(f"custom tickers: {load_custom_tickers()}")
    print(f"scan_health (last 3): {len(load_scan_health(limit=3))} rows")
