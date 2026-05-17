"""
migrate_sqlite_to_supabase.py — One-shot port of SwingTrade state → Supabase.

Reads from canonical JSON files (data/*.json) primarily, with SQLite as fallback
for tables that only live in the DB. JSON is canonical because most state
accumulated there before the SQLite migration was complete (signal_log.json
has 1106+ signals; SQLite signal_log has 17).

Idempotent: uses upsert with table-specific on-conflict keys. Safe to re-run.

Usage:
    python3 migrate_sqlite_to_supabase.py            # dry-run (counts only)
    python3 migrate_sqlite_to_supabase.py --apply    # actually write to Supabase
    python3 migrate_sqlite_to_supabase.py --apply --tables positions,signal_log

Pre-reqs:
    1. Run migrations/001_initial_schema.sql in the Supabase SQL Editor first.
    2. .env populated with SUPABASE_URL + SUPABASE_SERVICE_KEY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def _hash_key(*parts) -> str:
    """Deterministic sha1 of row content → used as sync_key for idempotent upsert."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]

# Force-enable mode 1 for the migration regardless of .env setting
os.environ["SUPABASE_MODE"] = "1"

from supabase_client import sb_client, healthcheck  # noqa: E402

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "swingtrade.db"
DATA_DIR = ROOT / "data"
BATCH_SIZE = 100


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# =========================================================================
# Per-table source extractors. Each returns list[dict] in the *Supabase*
# column shape (clean keys, no extras the schema doesn't have).
# =========================================================================

def _src_meta(conn) -> list[dict]:
    """meta: simple key/value, sourced from SQLite."""
    try:
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
        return [{"key": r["key"], "value": r["value"]} for r in rows]
    except sqlite3.OperationalError:
        return []


def _src_portfolio_state(conn) -> list[dict]:
    """Singleton row. Prefers data/portfolio_state.json (canonical)."""
    j = _load_json(DATA_DIR / "portfolio_state.json")
    if j and isinstance(j, dict):
        return [{
            "id": 1,
            "equity": float(j.get("equity") or 0),
            "cash": float(j.get("cash") or 0),
            "margin_reserved": float(j.get("margin_reserved") or 0),
            "updated_at": j.get("_last_saved"),
        }]
    try:
        rows = conn.execute("SELECT id, equity, cash, margin_reserved, updated_at FROM portfolio_state").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _src_positions(conn) -> list[dict]:
    """Open positions. JSON canonical."""
    j = _load_json(DATA_DIR / "portfolio_state.json")
    rows: list[dict] = []
    if j and isinstance(j, dict):
        for p in (j.get("positions") or []):
            rows.append({
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
                "sync_key": _hash_key("pos", p.get("ticker"), p.get("entry_date"), p.get("entry_price"), p.get("shares")),
                "raw_json": p,
            })
        return rows
    return []


def _src_closed_trades(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "portfolio_state.json")
    rows: list[dict] = []
    if j and isinstance(j, dict):
        for t in (j.get("closed_trades") or []):
            rows.append({
                "ticker": t.get("ticker"),
                "direction": t.get("direction"),
                "entry_date": t.get("entry_date"),
                "exit_date": t.get("exit_date"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "shares": t.get("shares"),
                "pnl_dollars": t.get("pnl_dollars"),
                "pnl_pct": t.get("pnl_pct"),
                "win": int(t.get("win")) if t.get("win") is not None else (1 if (t.get("pnl_dollars") or 0) > 0 else 0),
                "setup_type": t.get("setup_type"),
                "exit_reason": t.get("exit_reason"),
                "hold_days": t.get("hold_days"),
                "mae": t.get("mae"),
                "mfe": t.get("mfe"),
                "regime": t.get("regime"),
                "sync_key": _hash_key("ct", t.get("ticker"), t.get("entry_date"), t.get("exit_date")),
                "raw_json": t,
            })
    return rows


def _src_equity_curve(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "portfolio_state.json")
    rows: list[dict] = []
    if j and isinstance(j, dict):
        for ec in (j.get("equity_curve") or []):
            rows.append({
                "date": ec.get("date"),
                "equity": ec.get("equity"),
                "sync_key": _hash_key("ec", ec.get("date")),
            })
    return rows


def _src_equity_audit(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "portfolio_state.json")
    rows: list[dict] = []
    if j and isinstance(j, dict):
        for a in (j.get("equity_audit") or []):
            rows.append({
                "timestamp": a.get("timestamp"),
                "old_equity": a.get("old_equity"),
                "new_equity": a.get("new_equity"),
                "old_cash": a.get("old_cash"),
                "new_cash": a.get("new_cash"),
                "invested": a.get("invested"),
                "reason": a.get("reason"),
                "sync_key": _hash_key("ea", a.get("timestamp"), a.get("reason")),
            })
    return rows


def _src_monthly_pnl(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "portfolio_state.json")
    rows: list[dict] = []
    if j and isinstance(j, dict):
        for ym, pnl in (j.get("monthly_pnl") or {}).items():
            rows.append({"year_month": ym, "pnl": pnl})
    return rows


def _src_signal_log(conn) -> list[dict]:
    """The big one — signal_log.json has ~1100 entries."""
    j = _load_json(DATA_DIR / "signal_log.json")
    rows: list[dict] = []
    if isinstance(j, list):
        for s in j:
            rows.append({
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
                "setup_family": s.get("setup_family") or s.get("strategy"),
                "regime_at_entry": s.get("regime_at_entry") or s.get("regime4") or s.get("regime"),
                "entry_quality": s.get("entry_quality"),
                "catalyst_tier": s.get("catalyst_tier"),
                "conviction_tier": s.get("conviction_tier"),
                "sector": s.get("sector"),
                "industry": s.get("industry"),
                "r_multiple": s.get("r_multiple"),
                "sync_key": _hash_key("sl", s.get("date"), s.get("ticker"), s.get("strategy"), s.get("entry_price")),
                "raw_json": s,
            })
    return rows


def _src_runs(conn) -> list[dict]:
    try:
        rows = conn.execute("SELECT run_date, run_time, regime, num_picks, evaluated FROM runs").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sync_key"] = _hash_key("run", d.get("run_date"), d.get("run_time"))
            out.append(d)
        return out
    except sqlite3.OperationalError:
        return []


def _src_picks(conn) -> list[dict]:
    try:
        cols = "run_id,ticker,direction,verdict,score,rs_rank,setup_type,setup_family,entry_price,stop,target1,target2,first_seen_time,last_updated_time,updated_count,raw_json"
        rows = conn.execute(f"SELECT {cols} FROM picks").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("raw_json") and isinstance(d["raw_json"], str):
                try:
                    d["raw_json"] = json.loads(d["raw_json"])
                except Exception:
                    pass
            d["sync_key"] = _hash_key("pick", d.get("run_id"), d.get("ticker"), d.get("first_seen_time"))
            out.append(d)
        return out
    except sqlite3.OperationalError:
        return []


def _src_trades(conn) -> list[dict]:
    try:
        rows = conn.execute("SELECT * FROM trades").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("id", None)
            if d.get("raw_json") and isinstance(d["raw_json"], str):
                try:
                    d["raw_json"] = json.loads(d["raw_json"])
                except Exception:
                    pass
            d["sync_key"] = _hash_key("trade", d.get("run_id"), d.get("ticker"), d.get("entry_date"))
            out.append(d)
        return out
    except sqlite3.OperationalError:
        return []


def _src_watch_triggers(conn) -> list[dict]:
    try:
        rows = conn.execute("SELECT ticker, triggered_at, run_date, raw_json FROM watch_triggers").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("raw_json") and isinstance(d["raw_json"], str):
                try:
                    d["raw_json"] = json.loads(d["raw_json"])
                except Exception:
                    pass
            d["sync_key"] = _hash_key("wt", d.get("ticker"), d.get("triggered_at"))
            out.append(d)
        return out
    except sqlite3.OperationalError:
        return []


def _src_custom_tickers(conn) -> list[dict]:
    """custom_tracked.json: {tickers: [...]} (just a list of strings)."""
    j = _load_json(DATA_DIR / "custom_tracked.json")
    rows: list[dict] = []
    if isinstance(j, dict):
        for ticker in (j.get("tickers") or []):
            rows.append({"ticker": ticker, "source": "CUSTOM"})
    return rows


def _src_alert_log(conn) -> list[dict]:
    """alert_sent_log.json: {alert_key: date_str}."""
    j = _load_json(DATA_DIR / "alert_sent_log.json")
    if isinstance(j, dict):
        return [{"alert_key": k, "last_sent_date": v} for k, v in j.items()]
    return []


def _src_scan_health(conn) -> list[dict]:
    """scan_health.json: {history: [...], max_keep: N}."""
    j = _load_json(DATA_DIR / "scan_health.json")
    rows: list[dict] = []
    if isinstance(j, dict):
        for h in (j.get("history") or []):
            rows.append({
                "ts": h.get("ts"),
                "total": h.get("total"),
                "killed": h.get("killed"),
                "pct": h.get("pct"),
                "sync_key": _hash_key("sh", h.get("ts")),
                "raw_json": h,
            })
    return rows


def _src_gap_events(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "gap_events.json")
    rows: list[dict] = []
    if isinstance(j, list):
        for g in j:
            rows.append({
                "ts": g.get("ts"),
                "ticker": g.get("ticker"),
                "prev_close": g.get("prev_close"),
                "open_price": g.get("open_price"),
                "gap_pct": g.get("gap_pct"),
                "direction": g.get("direction"),
                "severity": g.get("severity"),
                "action": g.get("action"),
                "new_stop": g.get("new_stop"),
                "sync_key": _hash_key("gap", g.get("ts"), g.get("ticker")),
                "raw_json": g,
            })
    return rows


def _src_paper_trading_config(conn) -> list[dict]:
    j = _load_json(DATA_DIR / "paper_trading_start.json")
    if isinstance(j, dict):
        return [{
            "id": 1,
            "start_date": j.get("start_date"),
            "duration_days": j.get("duration_days"),
            "enabled": int(j.get("enabled") or 0),
            "direction_filter": j.get("direction_filter") or "buy_only",
            "max_daily_trades": j.get("max_daily_trades") or 4,
        }]
    return []


# (table_name, source_fn, on_conflict_column_or_None)
# on_conflict now uses sync_key for insert-only tables → idempotent re-runs (no more dups)
TABLES = [
    ("meta",                 _src_meta,                 "key"),
    ("portfolio_state",      _src_portfolio_state,      "id"),
    ("positions",            _src_positions,            "sync_key"),
    ("closed_trades",        _src_closed_trades,        "sync_key"),
    ("equity_audit",         _src_equity_audit,         "sync_key"),
    ("monthly_pnl",          _src_monthly_pnl,          "year_month"),
    ("equity_curve",         _src_equity_curve,         "sync_key"),
    ("signal_log",           _src_signal_log,           "sync_key"),
    ("runs",                 _src_runs,                 "sync_key"),
    ("picks",                _src_picks,                "sync_key"),
    ("trades",               _src_trades,               "sync_key"),
    ("watch_triggers",       _src_watch_triggers,       "sync_key"),
    ("custom_tickers",       _src_custom_tickers,       "ticker"),
    ("alert_log",            _src_alert_log,            "alert_key"),
    ("scan_health",          _src_scan_health,          "sync_key"),
    ("gap_events",           _src_gap_events,           "sync_key"),
    ("paper_trading_config", _src_paper_trading_config, "id"),
]


def _migrate_one(sb, table: str, payloads: list[dict], on_conflict: str | None,
                 dry_run: bool) -> dict:
    out = {"table": table, "n_source": len(payloads), "n_pushed": 0, "n_failed": 0,
           "errors": [], "duration_ms": 0}
    if not payloads or dry_run:
        return out
    # Dedup within source by on_conflict key (last-write-wins) to avoid
    # PG21000 "ON CONFLICT DO UPDATE cannot affect row a second time".
    if on_conflict:
        keys_seen: dict = {}
        for r in payloads:
            k = r.get(on_conflict)
            try:
                hash(k)
            except TypeError:
                k = json.dumps(k, sort_keys=True, default=str)
            keys_seen[k] = r
        payloads = list(keys_seen.values())
    t0 = time.time()
    for batch_start in range(0, len(payloads), BATCH_SIZE):
        batch = payloads[batch_start:batch_start + BATCH_SIZE]
        try:
            if on_conflict:
                sb.table(table).upsert(batch, on_conflict=on_conflict).execute()
            else:
                sb.table(table).insert(batch).execute()
            out["n_pushed"] += len(batch)
        except Exception as e:
            out["n_failed"] += len(batch)
            err = f"batch {batch_start}-{batch_start+len(batch)}: {type(e).__name__}: {str(e)[:300]}"
            out["errors"].append(err)
            break
    out["duration_ms"] = int((time.time() - t0) * 1000)
    return out


def _write_sync_state(sb, results: list[dict], total_elapsed: float, mode: str) -> None:
    """Write per-table sync state to both data/supabase_sync_state.json AND
    Supabase's supabase_sync_state table. Drives the kairos.html Supabase tab.
    """
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    state = {
        "_last_full_sync": now_iso,
        "_mode": mode,
        "_total_elapsed_s": round(total_elapsed, 2),
        "_total_source": sum(r["n_source"] for r in results),
        "_total_pushed": sum(r["n_pushed"] for r in results),
        "_total_failed": sum(r["n_failed"] for r in results),
        "tables": {},
    }
    ledger_rows = []
    for r in results:
        ok = (r["n_failed"] == 0)
        error_msg = (r["errors"][0] if r["errors"] else None)
        state["tables"][r["table"]] = {
            "last_sync_at": now_iso,
            "source_rows": r["n_source"],
            "pushed": r["n_pushed"],
            "failed": r["n_failed"],
            "duration_ms": r.get("duration_ms", 0),
            "ok": ok,
            "error": error_msg,
        }
        ledger_rows.append({
            "table_name": r["table"],
            "last_sync_at": now_iso,
            "source_rows": r["n_source"],
            "pushed": r["n_pushed"],
            "failed": r["n_failed"],
            "error_msg": error_msg,
            "duration_ms": r.get("duration_ms", 0),
        })

    out_path = DATA_DIR / "supabase_sync_state.json"
    out_path.write_text(json.dumps(state, indent=2))

    # Best-effort push to Supabase ledger (don't fail the migration over this)
    if mode == "APPLY" and sb is not None:
        try:
            sb.table("supabase_sync_state").upsert(ledger_rows, on_conflict="table_name").execute()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to Supabase (default: dry-run, counts only)")
    parser.add_argument("--tables", default="",
                        help="Comma-separated subset of tables (default: all)")
    args = parser.parse_args()

    print("=" * 64)
    print(f"JSON+SQLite → Supabase migration  {'(DRY RUN)' if not args.apply else '(APPLY)'}")
    print("=" * 64)

    hc = healthcheck()
    print(f"Supabase healthcheck: ok={hc['ok']} url={hc['url']}")
    if not hc["ok"]:
        print(f"  ERROR: {hc['error']}")
        return 2

    conn = sqlite3.connect(str(DB_PATH)) if DB_PATH.exists() else None
    if conn:
        conn.row_factory = sqlite3.Row

    sb = sb_client()
    table_filter = set(args.tables.split(",")) if args.tables else None
    results: list[dict] = []
    start = time.time()

    for table, src_fn, on_conflict in TABLES:
        if table_filter and table not in table_filter:
            continue
        payloads = src_fn(conn)
        print(f"\n→ {table:24s} (on_conflict={on_conflict or 'insert'})  {len(payloads):>5d} rows from source")
        r = _migrate_one(sb, table, payloads, on_conflict, dry_run=not args.apply)
        results.append(r)
        if args.apply:
            print(f"   pushed={r['n_pushed']}  failed={r['n_failed']}")
            for err in r["errors"][:2]:
                print(f"   ! {err}")

    print("\n" + "=" * 64)
    elapsed = time.time() - start
    total_src = sum(r["n_source"] for r in results)
    total_pushed = sum(r["n_pushed"] for r in results)
    total_failed = sum(r["n_failed"] for r in results)
    print(f"Total source rows: {total_src}")
    if args.apply:
        print(f"Total pushed:      {total_pushed}")
        print(f"Total failed:      {total_failed}")
    print(f"Elapsed: {elapsed:.1f}s")

    # Always write sync-state ledger (even on dry-run, so the dashboard tab
    # can show the "would have pushed" preview).
    _write_sync_state(sb, results, elapsed, "APPLY" if args.apply else "DRY_RUN")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to actually migrate.")
    elif total_failed > 0:
        print("\n⚠ Some rows failed. Review and re-run (idempotent).")
        return 1
    else:
        print("\n✓ Migration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
