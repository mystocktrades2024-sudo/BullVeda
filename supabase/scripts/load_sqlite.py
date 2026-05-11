"""Lift SQLite tables → Supabase Postgres.

Maps:
  data/swingtrade.db
    portfolio_state, positions, closed_trades, equity_curve, equity_audit,
    monthly_pnl, signal_log, watch_triggers, custom_tickers, alert_log,
    scan_health, gap_events, runs, picks, trades

  data/fundamentals.db
    fundamentals → public.ticker_fundamentals

  data/enrichment_cache.db
    enrichment (left in SQLite — not lifted by default; pass --with-enrichment)

Idempotent via ON CONFLICT.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn, repo_root  # noqa: E402

ROOT = repo_root()


# ---------------------------------------------------------------------------
# Generic copy helper
# ---------------------------------------------------------------------------
def copy_table(sqlite_path: Path, src_table: str, pg_cur, dest_table: str,
               column_map: dict[str, str], upsert_cols: list[str] | None = None,
               where: str | None = None) -> int:
    """Copy SQLite rows → Postgres, mapping column names.

    column_map: {sqlite_col: pg_col}
    upsert_cols: PG cols that form the conflict target (omit → INSERT only)
    """
    if not sqlite_path.exists():
        print(f"  · skip {src_table}: {sqlite_path} missing")
        return 0
    con = sqlite3.connect(str(sqlite_path))
    con.row_factory = sqlite3.Row
    sql = f"select * from {src_table}"
    if where:
        sql += f" where {where}"
    rows = con.execute(sql).fetchall()
    con.close()
    if not rows:
        return 0

    src_cols = list(column_map.keys())
    pg_cols  = list(column_map.values())
    placeholders = ",".join(["%s"] * len(pg_cols))

    if upsert_cols:
        upd = ", ".join(
            f"{c} = excluded.{c}" for c in pg_cols if c not in upsert_cols
        )
        on_conflict = (
            f"on conflict ({', '.join(upsert_cols)}) "
            + (f"do update set {upd}" if upd else "do nothing")
        )
    else:
        on_conflict = "on conflict do nothing"

    insert_sql = (
        f"insert into public.{dest_table} ({', '.join(pg_cols)}) "
        f"values ({placeholders}) {on_conflict}"
    )

    batch = []
    for r in rows:
        d = dict(r)
        tup = tuple(d.get(c) for c in src_cols)
        batch.append(tup)

    pg_cur.executemany(insert_sql, batch)
    return len(batch)


# ---------------------------------------------------------------------------
# swingtrade.db lifters
# ---------------------------------------------------------------------------
SWING = ROOT / "data" / "swingtrade.db"
FUNDS = ROOT / "data" / "fundamentals.db"


def load_portfolio_state(cur) -> int:
    if not SWING.exists():
        return 0
    con = sqlite3.connect(str(SWING))
    con.row_factory = sqlite3.Row
    r = con.execute("select * from portfolio_state limit 1").fetchone()
    con.close()
    if not r:
        return 0
    cur.execute(
        """
        insert into public.portfolio_state (id, equity, cash, margin_reserved, updated_at)
        values (1, %s, %s, %s, now())
        on conflict (id) do update set
            equity          = excluded.equity,
            cash            = excluded.cash,
            margin_reserved = excluded.margin_reserved,
            updated_at      = now()
        """,
        (r["equity"], r["cash"], r["margin_reserved"]),
    )
    return 1


def load_positions(cur) -> int:
    return copy_table(
        SWING, "positions", cur, "positions",
        column_map={
            "ticker":"ticker","direction":"direction","entry_date":"entry_date",
            "entry_price":"entry_price","shares":"shares","position_size":"position_size",
            "stop":"stop","trail_stop":"trail_stop","trail_active":"trail_active",
            "highest_price":"highest_price","current_price":"current_price",
            "target1":"target1","target2":"target2","setup_type":"setup_type",
            "allocation_pct":"allocation_pct","entry_regime":"entry_regime","notes":"notes",
        },
    )


def load_closed_trades(cur) -> int:
    return copy_table(
        SWING, "closed_trades", cur, "closed_trades",
        column_map={
            "ticker":"ticker","direction":"direction","entry_date":"entry_date","exit_date":"exit_date",
            "entry_price":"entry_price","exit_price":"exit_price","shares":"shares",
            "pnl_dollars":"pnl_dollars","pnl_pct":"pnl_pct","win":"win",
            "setup_type":"setup_type","exit_reason":"exit_reason","hold_days":"hold_days",
            "mae":"mae","mfe":"mfe","regime":"regime",
            "tech_score":"tech_score","cat_score":"cat_score","rs_score":"rs_score",
            "sm_score":"sm_score","qg_score":"qg_score","raw_total":"raw_total",
            "wr_multiplier":"wr_multiplier","bonus_total":"bonus_total","raw_json":"raw_json",
        },
    )


def load_equity_curve(cur) -> int:
    return copy_table(
        SWING, "equity_curve", cur, "equity_curve",
        column_map={"observed_at":"observed_at","equity":"equity"},
        upsert_cols=["observed_at"],
    )


def load_signal_log(cur) -> int:
    return copy_table(
        SWING, "signal_log", cur, "signal_log",
        column_map={
            "date":"observed_at","ticker":"ticker","strategy":"strategy",
            "entry_price":"entry_price","stop":"stop","target1":"target1","target2":"target2",
            "rr":"rr","stars":"stars","score":"score","rs_rank":"rs_rank",
            "direction":"direction","status":"status",
            "day5_price":"day5_price","day10_price":"day10_price",
            "actual_pnl_pct":"actual_pnl_pct","result":"result",
            "mae_pct":"mae_pct","mfe_pct":"mfe_pct",
            "outcome_5d":"outcome_5d","outcome_10d":"outcome_10d",
            "tech_score":"tech_score","cat_score":"cat_score","rs_score":"rs_score",
            "sm_score":"sm_score","qg_score":"qg_score","raw_total":"raw_total",
            "wr_multiplier":"wr_multiplier","bonus_total":"bonus_total","raw_json":"raw_json",
        },
    )


def load_runs(cur) -> int:
    return copy_table(
        SWING, "runs", cur, "runs",
        column_map={
            "run_date":"run_date","run_time":"run_time","regime":"regime",
            "num_picks":"num_picks","evaluated":"evaluated",
        },
        upsert_cols=["run_date"],
    )


def load_monthly_pnl(cur) -> int:
    if not SWING.exists():
        return 0
    con = sqlite3.connect(str(SWING))
    con.row_factory = sqlite3.Row
    rows = con.execute("select * from monthly_pnl").fetchall()
    con.close()
    if not rows:
        return 0
    cur.executemany(
        """
        insert into public.monthly_pnl (year_month, pnl)
        values (%s, %s)
        on conflict (year_month) do update set pnl = excluded.pnl
        """,
        [(r["year_month"] if "year_month" in r.keys() else r.keys()[0], r[1] if len(r.keys()) > 1 else 0)
         for r in rows],
    )
    return len(rows)


def load_fundamentals(cur) -> int:
    # Ensure tickers master has every ticker we're about to insert fundamentals for
    if FUNDS.exists():
        con = sqlite3.connect(str(FUNDS))
        con.row_factory = sqlite3.Row
        all_t = con.execute(
            "select ticker, sector, industry from fundamentals where ticker is not null"
        ).fetchall()
        con.close()
        if all_t:
            cur.executemany(
                """
                insert into public.tickers (ticker, sector, industry, last_seen)
                values (%s, %s, %s, now())
                on conflict (ticker) do update set
                    sector    = coalesce(excluded.sector, public.tickers.sector),
                    industry  = coalesce(excluded.industry, public.tickers.industry),
                    last_seen = now()
                """,
                [(r["ticker"], r["sector"], r["industry"]) for r in all_t],
            )
    return copy_table(
        FUNDS, "fundamentals", cur, "ticker_fundamentals",
        column_map={
            "ticker":"ticker","fetched_at":"fetched_at","source":"source",
            "last_earnings":"last_earnings","next_earnings":"next_earnings",
            "sector":"sector","industry":"industry","market_cap":"market_cap",
            "shares_out":"shares_out","beta":"beta",
            "week52_high":"week52_high","week52_low":"week52_low",
            "eps_ttm":"eps_ttm","eps_growth_qoq":"eps_growth_qoq",
            "pe_ttm":"pe_ttm","forward_pe":"forward_pe",
            "revenue_ttm":"revenue_ttm","revenue_growth":"revenue_growth",
            "gross_margin":"gross_margin","operating_margin":"operating_margin",
            "profit_margin":"profit_margin","debt_equity":"debt_equity",
            "fcf_ttm":"fcf_ttm","short_float":"short_float",
            "short_float_fetched":"short_float_fetched","raw_json":"raw_json",
        },
        upsert_cols=["ticker"],
    )


def load_custom_tickers(cur) -> int:
    return copy_table(
        SWING, "custom_tickers", cur, "custom_tickers",
        column_map={"ticker":"ticker","added_at":"added_at","note":"note"},
        upsert_cols=["ticker"],
    )


def load_alert_log(cur) -> int:
    return copy_table(
        SWING, "alert_log", cur, "alert_log",
        column_map={"sent_at":"sent_at","channel":"channel","ticker":"ticker",
                    "subject":"subject","body":"body","status":"status"},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="Run only this stage (e.g. fundamentals)")
    args = ap.parse_args()

    stages = [
        ("runs",             load_runs),
        ("portfolio_state",  load_portfolio_state),
        ("positions",        load_positions),
        ("closed_trades",    load_closed_trades),
        ("equity_curve",     load_equity_curve),
        ("signal_log",       load_signal_log),
        ("monthly_pnl",      load_monthly_pnl),
        ("custom_tickers",   load_custom_tickers),
        ("alert_log",        load_alert_log),
        ("fundamentals",     load_fundamentals),
    ]

    conn = pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                for name, fn in stages:
                    if args.only and args.only != name:
                        continue
                    try:
                        n = fn(cur)
                        print(f"  ✓ {name:20s} {n:>6d} rows")
                    except Exception as e:
                        print(f"  ✗ {name:20s} ERROR: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
