"""One-shot migrator: JSON state files → SQLite (data/swingtrade.db).

Idempotent. Skips tables that already have rows. Run manually:
    python3 migrate_json_to_sqlite.py

Preserves original JSON files (not deleted). Falls back to JSON if
SWINGTRADE_USE_SQLITE=0 (see db.py).
"""
import json
import logging
from pathlib import Path
from db import get_conn, transaction, BASE_DIR, init_schema

log = logging.getLogger("migrate_sqlite")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Failed to read {path.name}: {e}")
        return None


def _count(conn, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def migrate_portfolio_state():
    conn = get_conn()
    state = _load_json(BASE_DIR / "data" / "portfolio_state.json")
    if not state:
        return {"portfolio_state": "skipped (no json)"}

    result = {}
    with transaction() as c:
        # Portfolio singleton
        c.execute(
            "UPDATE portfolio_state SET equity=?, cash=?, margin_reserved=?, updated_at=? WHERE id=1",
            (state.get("equity", 5000), state.get("cash", 5000),
             state.get("margin_reserved", 0), state.get("_last_saved", ""))
        )

        # Positions — replace if any exist in JSON
        n_before = _count(c, "positions")
        if n_before == 0:
            for p in state.get("positions", []):
                c.execute(
                    """INSERT INTO positions (ticker, direction, entry_date, entry_price, shares,
                         position_size, stop, trail_stop, trail_active, highest_price, current_price,
                         target1, target2, setup_type, allocation_pct, notes, entry_regime, raw_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p.get("ticker"), p.get("direction", "long"), p.get("entry_date"),
                     p.get("entry_price"), int(p.get("shares", 0)), p.get("position_size"),
                     p.get("stop"), p.get("trail_stop"), int(p.get("trail_active", 0)),
                     p.get("highest_price"), p.get("current_price"),
                     p.get("target1"), p.get("target2"), p.get("setup_type"),
                     p.get("allocation_pct"), p.get("notes"), p.get("entry_regime"),
                     json.dumps(p, default=str)))
        result["positions"] = len(state.get("positions", []))

        # Closed trades
        n_before = _count(c, "closed_trades")
        if n_before == 0:
            for t in state.get("closed_trades", []):
                c.execute(
                    """INSERT INTO closed_trades (ticker, direction, entry_date, exit_date,
                         entry_price, exit_price, shares, pnl_dollars, pnl_pct, win, setup_type,
                         exit_reason, hold_days, mae, mfe, regime, raw_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (t.get("ticker"), t.get("direction", "long"), t.get("entry_date"),
                     t.get("exit_date"), t.get("entry_price"), t.get("exit_price"),
                     int(t.get("shares", 0)), t.get("pnl_dollars", t.get("pnl_dollar")),
                     t.get("pnl_pct"), int(t.get("win", 0)), t.get("setup_type"),
                     t.get("exit_reason"), t.get("hold_days"),
                     t.get("mae"), t.get("mfe"), t.get("regime"),
                     json.dumps(t, default=str)))
        result["closed_trades"] = len(state.get("closed_trades", []))

        # Equity audit
        n_before = _count(c, "equity_audit")
        if n_before == 0:
            for a in state.get("equity_audit", []):
                c.execute(
                    """INSERT INTO equity_audit (timestamp, old_equity, new_equity, old_cash,
                         new_cash, invested, reason) VALUES (?,?,?,?,?,?,?)""",
                    (a.get("timestamp"), a.get("old_equity"), a.get("new_equity"),
                     a.get("old_cash"), a.get("new_cash"), a.get("invested"), a.get("reason")))
        result["equity_audit"] = len(state.get("equity_audit", []))

        # Monthly pnl
        for ym, pnl in state.get("monthly_pnl", {}).items():
            c.execute("INSERT OR REPLACE INTO monthly_pnl (year_month, pnl) VALUES (?, ?)", (ym, pnl))
        result["monthly_pnl"] = len(state.get("monthly_pnl", {}))

    return {"portfolio_state": result}


def migrate_signal_log():
    signals = _load_json(BASE_DIR / "data" / "signal_log.json")
    if not signals:
        return {"signal_log": "skipped (no json)"}

    conn = get_conn()
    if _count(conn, "signal_log") > 0:
        return {"signal_log": "skipped (already populated)"}

    with transaction() as c:
        for s in signals:
            c.execute(
                """INSERT INTO signal_log (date, ticker, strategy, entry_price, stop, target1,
                     target2, rr, stars, score, rs_rank, direction, status, day5_price,
                     day10_price, actual_pnl_pct, result, mae_pct, mfe_pct, outcome_5d,
                     outcome_10d, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.get("date"), s.get("ticker"), s.get("strategy"),
                 s.get("entry_price"), s.get("stop"), s.get("target1"), s.get("target2"),
                 s.get("rr"), s.get("stars"), s.get("score"), s.get("rs_rank"),
                 s.get("direction", "long"), s.get("status", "OPEN"),
                 s.get("day5_price"), s.get("day10_price"), s.get("actual_pnl_pct"),
                 s.get("result"), s.get("mae_pct"), s.get("mfe_pct"),
                 s.get("outcome_5d"), s.get("outcome_10d"),
                 json.dumps(s, default=str)))
    return {"signal_log": len(signals)}


def migrate_custom_tickers():
    data = _load_json(BASE_DIR / "data" / "custom_tracked.json")
    if not data or not data.get("tickers"):
        return {"custom_tickers": "skipped (no json)"}
    conn = get_conn()
    if _count(conn, "custom_tickers") > 0:
        return {"custom_tickers": "skipped (already populated)"}
    with transaction() as c:
        for t in data.get("tickers", []):
            c.execute(
                """INSERT OR IGNORE INTO custom_tickers (ticker, entry_price, entry_date,
                     entry_time, note, added_at, source) VALUES (?,?,?,?,?,?,?)""",
                (t.get("ticker"), t.get("entry_price"), t.get("entry_date"),
                 t.get("entry_time"), t.get("note"), t.get("added_at"),
                 t.get("source", "CUSTOM")))
    return {"custom_tickers": len(data.get("tickers", []))}


def migrate_alert_log():
    data = _load_json(BASE_DIR / "data" / "alert_sent_log.json")
    if not data:
        return {"alert_log": "skipped (no json)"}
    conn = get_conn()
    if _count(conn, "alert_log") > 0:
        return {"alert_log": "skipped (already populated)"}
    with transaction() as c:
        for k, v in data.items():
            c.execute("INSERT OR REPLACE INTO alert_log (alert_key, last_sent_date) VALUES (?, ?)", (k, v))
    return {"alert_log": len(data)}


def migrate_scan_health():
    data = _load_json(BASE_DIR / "data" / "scan_health.json")
    if not data or not data.get("history"):
        return {"scan_health": "skipped (no json)"}
    conn = get_conn()
    if _count(conn, "scan_health") > 0:
        return {"scan_health": "skipped (already populated)"}
    with transaction() as c:
        for h in data.get("history", []):
            c.execute(
                "INSERT INTO scan_health (ts, total, killed, pct) VALUES (?,?,?,?)",
                (h.get("ts"), h.get("total"), h.get("killed"), h.get("pct")))
    return {"scan_health": len(data.get("history", []))}


def migrate_gap_events():
    data = _load_json(BASE_DIR / "data" / "gap_events.json")
    if not data:
        return {"gap_events": "skipped (no json)"}
    events = data if isinstance(data, list) else data.get("events", [])
    if not events:
        return {"gap_events": "skipped (empty)"}
    conn = get_conn()
    if _count(conn, "gap_events") > 0:
        return {"gap_events": "skipped (already populated)"}
    with transaction() as c:
        for e in events:
            c.execute(
                """INSERT INTO gap_events (ts, ticker, prev_close, open_price, gap_pct,
                     direction, severity, action, new_stop) VALUES (?,?,?,?,?,?,?,?,?)""",
                (e.get("ts"), e.get("ticker"), e.get("prev_close"), e.get("open_price"),
                 e.get("gap_pct"), e.get("direction"), e.get("severity"),
                 e.get("action"), e.get("new_stop")))
    return {"gap_events": len(events)}


def migrate_paper_trading_config():
    data = _load_json(BASE_DIR / "data" / "paper_trading_start.json")
    if not data:
        return {"paper_trading_config": "skipped (no json)"}
    conn = get_conn()
    with transaction() as c:
        c.execute(
            """INSERT OR REPLACE INTO paper_trading_config (id, start_date, duration_days,
                 enabled, disabled_at, direction_filter, max_daily_trades)
               VALUES (1, ?, ?, ?, ?, ?, ?)""",
            (data.get("start_date"), data.get("duration_days", 60),
             int(data.get("enabled", 0)), data.get("disabled_at"),
             data.get("direction_filter", "buy_only"),
             data.get("max_daily_trades", 4)))
    return {"paper_trading_config": "ok"}


def migrate_all():
    init_schema()
    result = {}
    result.update(migrate_portfolio_state())
    result.update(migrate_signal_log())
    result.update(migrate_custom_tickers())
    result.update(migrate_alert_log())
    result.update(migrate_scan_health())
    result.update(migrate_gap_events())
    result.update(migrate_paper_trading_config())
    log.info(f"Migration complete: {result}")
    return result


if __name__ == "__main__":
    print(migrate_all())
