"""
supabase_sync.py — Dual-write hooks (Mode 1).

Called by _save_state() and _save_log() to mirror local writes to Supabase.
NEVER raises — Supabase failures are logged but never break a scan or
portfolio operation. Local files remain canonical source of truth in Mode 1.

State file: cache/supabase_sync_state.json — tracks high-water marks for
append-only tables so we don't re-upload signal_log or closed_trades on
every save.

Sync semantics per table:
  - portfolio_state (singleton)   → upsert on id=1
  - monthly_pnl (per year_month)  → upsert on year_month
  - equity_curve (date-indexed)   → append new entries only
  - positions (snapshot)          → DELETE all + INSERT current (small N)
  - closed_trades (append-only)   → INSERT new entries only
  - signal_log (append-only)      → INSERT new entries only

All `sync_*` functions return a dict {ok, n_uploaded, error} for logging
but the caller can ignore the return value entirely.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from supabase_client import sb_client, supabase_mode

ROOT = Path(__file__).parent
SYNC_STATE_PATH = ROOT / "cache" / "supabase_sync_state.json"


def _load_sync_state() -> dict:
    if not SYNC_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SYNC_STATE_PATH.read_text())
    except Exception:
        return {}


def _save_sync_state(state: dict) -> None:
    try:
        SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception:
        pass  # never raise from sync


def _safe_call(fn, *a, **kw):
    """Run fn(*a, **kw); return (ok, value, error)."""
    try:
        return True, fn(*a, **kw), None
    except Exception as e:
        return False, None, f"{type(e).__name__}: {str(e)[:200]}"


# =========================================================================
# Public sync functions — call these from _save_state / _save_log
# =========================================================================

def sync_portfolio_state(state: dict) -> dict:
    """Mirror portfolio_state.json to Supabase. Mode-gated.

    Splits the JSON shape across:
      - portfolio_state (singleton id=1)
      - positions (snapshot replace)
      - closed_trades (append new)
      - equity_curve (append new)
      - monthly_pnl (upsert per year_month)
    """
    if supabase_mode() == 0:
        return {"ok": True, "skipped": True, "reason": "SUPABASE_MODE=0"}

    sb = sb_client()
    if sb is None:
        return {"ok": False, "error": "client unavailable"}

    sync_state = _load_sync_state()
    out = {"ok": True, "tables": {}, "errors": []}

    # 1. portfolio_state singleton
    ok, _, err = _safe_call(
        lambda: sb.table("portfolio_state").upsert({
            "id": 1,
            "equity": float(state.get("equity") or 0),
            "cash": float(state.get("cash") or 0),
            "margin_reserved": float(state.get("margin_reserved") or 0),
            "updated_at": state.get("_last_saved") or datetime.now().isoformat(),
        }, on_conflict="id").execute()
    )
    out["tables"]["portfolio_state"] = {"ok": ok, "error": err}
    if not ok:
        out["errors"].append(f"portfolio_state: {err}")

    # 2. positions — snapshot replace (DELETE all then INSERT current)
    positions = state.get("positions") or []
    pos_payloads = [_position_to_row(p) for p in positions]
    ok, _, err = _safe_call(
        lambda: sb.table("positions").delete().neq("id", -1).execute()
    )
    if ok and pos_payloads:
        ok2, _, err2 = _safe_call(
            lambda: sb.table("positions").insert(pos_payloads).execute()
        )
        out["tables"]["positions"] = {"ok": ok2, "n_uploaded": len(pos_payloads), "error": err2}
        if not ok2:
            out["errors"].append(f"positions insert: {err2}")
    else:
        out["tables"]["positions"] = {"ok": ok, "n_uploaded": 0, "error": err}

    # 3. closed_trades — append-only (high-water mark on count)
    closed = state.get("closed_trades") or []
    last_n = sync_state.get("closed_trades", {}).get("last_count_synced", 0)
    new_closed = closed[last_n:] if len(closed) > last_n else []
    if new_closed:
        payloads = [_closed_trade_to_row(t) for t in new_closed]
        ok, _, err = _safe_call(
            lambda: sb.table("closed_trades").insert(payloads).execute()
        )
        out["tables"]["closed_trades"] = {"ok": ok, "n_uploaded": len(payloads), "error": err}
        if ok:
            sync_state.setdefault("closed_trades", {})["last_count_synced"] = len(closed)
            sync_state["closed_trades"]["last_synced_at"] = datetime.now().isoformat()
        else:
            out["errors"].append(f"closed_trades: {err}")
    else:
        out["tables"]["closed_trades"] = {"ok": True, "n_uploaded": 0, "skipped": True}

    # 4. equity_curve — append new
    eq_curve = state.get("equity_curve") or []
    last_eq = sync_state.get("equity_curve", {}).get("last_count_synced", 0)
    new_eq = eq_curve[last_eq:] if len(eq_curve) > last_eq else []
    if new_eq:
        payloads = [{"date": e.get("date"), "equity": e.get("equity")} for e in new_eq]
        ok, _, err = _safe_call(
            lambda: sb.table("equity_curve").insert(payloads).execute()
        )
        out["tables"]["equity_curve"] = {"ok": ok, "n_uploaded": len(payloads), "error": err}
        if ok:
            sync_state.setdefault("equity_curve", {})["last_count_synced"] = len(eq_curve)
        else:
            out["errors"].append(f"equity_curve: {err}")
    else:
        out["tables"]["equity_curve"] = {"ok": True, "n_uploaded": 0, "skipped": True}

    # 5. monthly_pnl — upsert per year_month
    mpl = state.get("monthly_pnl") or {}
    if mpl:
        payloads = [{"year_month": ym, "pnl": pnl} for ym, pnl in mpl.items()]
        ok, _, err = _safe_call(
            lambda: sb.table("monthly_pnl").upsert(payloads, on_conflict="year_month").execute()
        )
        out["tables"]["monthly_pnl"] = {"ok": ok, "n_uploaded": len(payloads), "error": err}
        if not ok:
            out["errors"].append(f"monthly_pnl: {err}")

    # 6. equity_audit — append new
    audit = state.get("equity_audit") or []
    last_audit = sync_state.get("equity_audit", {}).get("last_count_synced", 0)
    new_audit = audit[last_audit:] if len(audit) > last_audit else []
    if new_audit:
        payloads = [{
            "timestamp": a.get("timestamp"),
            "old_equity": a.get("old_equity"),
            "new_equity": a.get("new_equity"),
            "old_cash": a.get("old_cash"),
            "new_cash": a.get("new_cash"),
            "invested": a.get("invested"),
            "reason": a.get("reason"),
        } for a in new_audit]
        ok, _, err = _safe_call(
            lambda: sb.table("equity_audit").insert(payloads).execute()
        )
        out["tables"]["equity_audit"] = {"ok": ok, "n_uploaded": len(payloads), "error": err}
        if ok:
            sync_state.setdefault("equity_audit", {})["last_count_synced"] = len(audit)
        else:
            out["errors"].append(f"equity_audit: {err}")

    _save_sync_state(sync_state)
    out["ok"] = len(out["errors"]) == 0
    return out


def sync_signal_log(entries: list[dict]) -> dict:
    """Append new signal_log entries to Supabase. Mode-gated.

    Tracks high-water mark in cache/supabase_sync_state.json so re-saves
    don't re-upload the whole 1100-row history.
    """
    if supabase_mode() == 0:
        return {"ok": True, "skipped": True, "reason": "SUPABASE_MODE=0"}

    sb = sb_client()
    if sb is None:
        return {"ok": False, "error": "client unavailable"}

    sync_state = _load_sync_state()
    last_n = sync_state.get("signal_log", {}).get("last_count_synced", 0)
    new_entries = entries[last_n:] if len(entries) > last_n else []

    if not new_entries:
        return {"ok": True, "n_uploaded": 0, "skipped": True}

    payloads = [_signal_to_row(s) for s in new_entries]
    BATCH = 100
    n_uploaded = 0
    errors = []
    for i in range(0, len(payloads), BATCH):
        batch = payloads[i:i+BATCH]
        ok, _, err = _safe_call(lambda: sb.table("signal_log").insert(batch).execute())
        if ok:
            n_uploaded += len(batch)
        else:
            errors.append(f"batch {i}: {err}")
            break

    if n_uploaded > 0:
        sync_state.setdefault("signal_log", {})["last_count_synced"] = last_n + n_uploaded
        sync_state["signal_log"]["last_synced_at"] = datetime.now().isoformat()
        _save_sync_state(sync_state)

    return {"ok": not errors, "n_uploaded": n_uploaded, "errors": errors}


# =========================================================================
# Row shape helpers (JSON dict → Supabase row dict)
# =========================================================================

def _position_to_row(p: dict) -> dict:
    return {
        "ticker": p.get("ticker"),
        "direction": p.get("direction") or "long",
        "entry_date": p.get("entry_date"),
        "entry_price": p.get("entry_price"),
        "shares": p.get("shares"),
        "position_size": p.get("position_size"),
        "stop": p.get("stop"),
        "trail_stop": p.get("trail_stop"),
        "trail_active": int(p.get("trail_active") or 0),
        "highest_price": p.get("highest_price"),
        "current_price": p.get("current_price"),
        "target1": p.get("target1"),
        "target2": p.get("target2"),
        "setup_type": p.get("setup_type"),
        "allocation_pct": p.get("allocation_pct"),
        "notes": p.get("notes"),
        "entry_regime": p.get("entry_regime"),
        "raw_json": p,
    }


def _closed_trade_to_row(t: dict) -> dict:
    return {
        "ticker": t.get("ticker"),
        "direction": t.get("direction"),
        "entry_date": t.get("entry_date"),
        "exit_date": t.get("exit_date"),
        "entry_price": t.get("entry_price"),
        "exit_price": t.get("exit_price"),
        "shares": t.get("shares"),
        "pnl_dollars": t.get("pnl_dollars"),
        "pnl_pct": t.get("pnl_pct"),
        "win": int(t.get("win")) if t.get("win") is not None
               else (1 if (t.get("pnl_dollars") or 0) > 0 else 0),
        "setup_type": t.get("setup_type"),
        "exit_reason": t.get("exit_reason"),
        "hold_days": t.get("hold_days"),
        "mae": t.get("mae"),
        "mfe": t.get("mfe"),
        "regime": t.get("regime"),
        "raw_json": t,
    }


def _signal_to_row(s: dict) -> dict:
    return {
        "date": s.get("date"),
        "ticker": s.get("ticker"),
        "strategy": s.get("strategy"),
        "entry_price": s.get("entry_price"),
        "stop": s.get("stop"),
        "target1": s.get("target1"),
        "target2": s.get("target2"),
        "rr": s.get("rr"),
        "stars": s.get("stars"),
        "score": s.get("score"),
        "rs_rank": s.get("rs_rank"),
        "direction": s.get("direction") or "long",
        "status": s.get("status") or "OPEN",
        "day5_price": s.get("day5_price"),
        "day10_price": s.get("day10_price"),
        "actual_pnl_pct": s.get("actual_pnl_pct"),
        "result": s.get("result"),
        "mae_pct": s.get("mae_pct"),
        "mfe_pct": s.get("mfe_pct"),
        "outcome_5d": s.get("outcome_5d"),
        "outcome_10d": s.get("outcome_10d"),
        "raw_json": s,
    }


def baseline_sync_state_from_supabase() -> dict:
    """One-time helper: read current row counts from Supabase and write them
    as the high-water marks to cache/supabase_sync_state.json. Use this
    immediately after running migrate_sqlite_to_supabase.py so subsequent
    sync_* calls only push deltas."""
    sb = sb_client()
    if sb is None:
        return {"ok": False, "error": "client unavailable"}
    state: dict = {}
    for table in ("signal_log", "closed_trades", "equity_curve", "equity_audit"):
        try:
            r = sb.table(table).select("id", count="exact").limit(0).execute()
            state[table] = {"last_count_synced": r.count or 0,
                            "baseline_at": datetime.now().isoformat()}
        except Exception as e:
            state[table] = {"error": str(e)[:100]}
    _save_sync_state(state)
    return {"ok": True, "state": state}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "baseline":
        print(json.dumps(baseline_sync_state_from_supabase(), indent=2))
    else:
        print("Usage:")
        print("  python3 supabase_sync.py baseline   # set high-water marks from current Supabase counts")
