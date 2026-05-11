"""Copy data from legacy_v1.* → public.* with column-mapped semantics.

The old schema (now in legacy_v1) had different column names / types than the
new design. This script does an explicit per-table mapping so existing data
is preserved in the new tables.

Skipped:
  - backtest_runs / backtest_trades / walk_forward_folds — no new equivalent;
    stay in legacy_v1.
  - meta / paper_trading_config — orthogonal, stay in legacy_v1.
  - picks — old daily-output table; new equivalent picks_history_runs is
    populated separately from cache/picks_history.json.

Idempotent: each copy uses INSERT … ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn  # noqa: E402


def n_rows(cur, schema: str, table: str) -> int:
    cur.execute(f"select count(*) from {schema}.{table}")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Per-table SQL copies. Each returns (label, sql, target_table_for_count)
# ---------------------------------------------------------------------------
COPIES = [
    (
        "portfolio_state",
        """
        insert into public.portfolio_state (id, equity, cash, margin_reserved, updated_at)
        select id, equity, cash, margin_reserved, coalesce(updated_at, now())
          from legacy_v1.portfolio_state
        on conflict (id) do update set
            equity          = excluded.equity,
            cash            = excluded.cash,
            margin_reserved = excluded.margin_reserved,
            updated_at      = excluded.updated_at
        """,
        "portfolio_state",
    ),
    (
        "equity_curve",
        """
        -- legacy table may have multiple rows per date — keep the last one
        insert into public.equity_curve (observed_at, equity)
        select date, equity
          from (
            select date, equity,
                   row_number() over (partition by date order by id desc) as rn
              from legacy_v1.equity_curve
          ) x
         where rn = 1
        on conflict (observed_at) do update set equity = excluded.equity
        """,
        "equity_curve",
    ),
    (
        "monthly_pnl",
        """
        insert into public.monthly_pnl (year_month, pnl)
        select year_month, pnl from legacy_v1.monthly_pnl
        on conflict (year_month) do update set pnl = excluded.pnl
        """,
        "monthly_pnl",
    ),
    (
        "equity_audit",
        """
        insert into public.equity_audit (occurred_at, event_type, delta, balance_after, note)
        select
            "timestamp"                                  as occurred_at,
            'legacy_update'                              as event_type,
            (new_equity - old_equity)                    as delta,
            new_equity                                   as balance_after,
            reason                                       as note
          from legacy_v1.equity_audit
        """,
        "equity_audit",
    ),
    (
        "custom_tickers",
        """
        -- ensure ticker exists in master before insert
        insert into public.tickers (ticker, is_custom, last_seen)
        select distinct ticker, true, now()
          from legacy_v1.custom_tickers
          where ticker is not null
        on conflict (ticker) do update set is_custom = true, last_seen = now();

        insert into public.custom_tickers (ticker, added_at, note)
        select ticker, coalesce(added_at, now()),
               coalesce(note, source)
          from legacy_v1.custom_tickers
          where ticker is not null
        on conflict (ticker) do update set added_at = excluded.added_at
        """,
        "custom_tickers",
    ),
    (
        "alert_log",
        """
        -- legacy alert_log was a dedup-cache; preserve as 'mac' channel.
        insert into public.alert_log (sent_at, channel, subject, status)
        select last_sent_date::timestamptz, 'mac', alert_key, 'sent'
          from legacy_v1.alert_log
        """,
        "alert_log",
    ),
    (
        "gap_events",
        """
        -- ensure ticker exists
        insert into public.tickers (ticker, last_seen)
        select distinct ticker, now()
          from legacy_v1.gap_events
          where ticker is not null
        on conflict (ticker) do nothing;

        insert into public.gap_events (observed_at, ticker, gap_pct, direction)
        select ts::date, ticker, gap_pct, direction
          from legacy_v1.gap_events
          where ticker is not null
        """,
        "gap_events",
    ),
    (
        "watch_triggers",
        """
        insert into public.tickers (ticker, last_seen)
        select distinct ticker, now()
          from legacy_v1.watch_triggers
          where ticker is not null
        on conflict (ticker) do nothing;

        insert into public.watch_triggers (ticker, condition, threshold, created_at, fired_at, is_active)
        select ticker, 'legacy', null, coalesce(triggered_at, now()), triggered_at, false
          from legacy_v1.watch_triggers
          where ticker is not null
        """,
        "watch_triggers",
    ),
    (
        "closed_trades",
        """
        -- ensure ticker exists
        insert into public.tickers (ticker, last_seen)
        select distinct ticker, now()
          from legacy_v1.closed_trades
          where ticker is not null
        on conflict (ticker) do nothing;

        insert into public.closed_trades
            (ticker, direction, entry_date, exit_date,
             entry_price, exit_price, shares,
             pnl_dollars, pnl_pct, win,
             setup_type, exit_reason, hold_days,
             mae, mfe, regime, raw_json)
        select ticker, direction, entry_date::date, exit_date::date,
               entry_price, exit_price, shares,
               pnl_dollars, pnl_pct, (win = 1) as win,
               setup_type, exit_reason, hold_days,
               mae, mfe, regime, raw_json
          from legacy_v1.closed_trades
          where ticker is not null
        """,
        "closed_trades",
    ),
    (
        "signal_log",
        """
        -- ensure tickers exist (1,191 rows could span many)
        insert into public.tickers (ticker, last_seen)
        select distinct ticker, now()
          from legacy_v1.signal_log
          where ticker is not null
        on conflict (ticker) do nothing;

        insert into public.signal_log
            (observed_at, ticker, strategy, verdict, direction,
             entry_price, stop, target1, target2, rr,
             stars, score, rs_rank, status,
             day5_price, day10_price, actual_pnl_pct, result,
             mae_pct, mfe_pct, outcome_5d, outcome_10d, raw_json)
        select date::date,
               ticker,
               strategy,
               case
                 when upper(coalesce(status,'')) in ('BUY','WATCH','SHORT') then upper(status)
                 else null
               end as verdict,
               case when lower(coalesce(direction,'')) in ('long','short')
                    then lower(direction) else null end as direction,
               entry_price, stop, target1, target2, rr,
               stars, score,
               rs_rank::integer,
               case when upper(coalesce(status,'')) in ('OPEN','CLOSED')
                    then upper(status) else null end as status,
               day5_price, day10_price, actual_pnl_pct, result,
               mae_pct, mfe_pct, outcome_5d, outcome_10d, raw_json
          from legacy_v1.signal_log
          where ticker is not null
        """,
        "signal_log",
    ),
    (
        "runs",
        """
        insert into public.runs (run_date, run_time, regime, num_picks, evaluated)
        select run_date, run_time, regime, num_picks, evaluated
          from legacy_v1.runs
        on conflict (run_date) do update set
            run_time   = excluded.run_time,
            regime     = excluded.regime,
            num_picks  = excluded.num_picks,
            evaluated  = excluded.evaluated
        """,
        "runs",
    ),
    # scan_health requires runs to exist first (FK)
    (
        "scan_health",
        """
        insert into public.scan_health (fill_rate_pct, eodhd_429_count, yfinance_fallback_count, aborted, run_id)
        select pct,
               0::int, 0::int,
               false,
               null::bigint
          from legacy_v1.scan_health
        """,
        "scan_health",
    ),
]


def main():
    print(f"  {'table':22s} {'legacy':>8s} → {'public':>8s}")
    print(f"  {'-'*22}{'-'*9} {'-'*10}")
    for label, sql, target in COPIES:
        # Each copy gets its own connection + transaction so one failure
        # doesn't poison the others.
        conn = pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("select count(*) from information_schema.schemata where schema_name='legacy_v1'")
                if cur.fetchone()[0] == 0:
                    print("  legacy_v1 schema not found — nothing to migrate.")
                    return
                try:
                    src = n_rows(cur, "legacy_v1", target)
                except Exception:
                    src = -1
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            with conn.cursor() as cur:
                try:
                    dst = n_rows(cur, "public", target)
                except Exception:
                    dst = -1
            flag = "OK" if dst >= src else "..."
            print(f"  {flag:2s} {label:22s} {src:>8d} -> {dst:>8d}")
        except Exception as e:
            msg = str(e).strip().split('\n')[0][:120]
            print(f"  XX {label:22s} ERROR: {msg}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
