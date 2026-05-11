"""Load JSON / JSONL sidecar files into Supabase:

  cache/picks_history.json      → public.runs (auto-create) + picks_history_runs
  data/portfolio_state.json     → portfolio_state (overrides SQLite) + closed_trades fallback
  data/earnings_watchlist.json  → earnings_events
  data/earnings_beat_predictions.json → earnings_predictions
  data/earnings_outcomes.jsonl  → earnings_outcomes
  data/signal_log.json          → signal_log (already loaded from SQLite — this is fallback)
  data/decision_log.jsonl       → decision_log (streamed; large file)
  cache/regime_history.json     → regime_history (current state)

All loaders are idempotent. Loader functions return row counts.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn, repo_root  # noqa: E402

ROOT = repo_root()
BATCH = 1000


# ---------------------------------------------------------------------------
def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
def load_picks_history(cur) -> int:
    data = _read_json(ROOT / "cache" / "picks_history.json")
    if not data:
        return 0
    # Collect all distinct tickers and pre-insert into master
    all_tickers = set()
    for run in data.get("runs") or []:
        for p in run.get("picks") or []:
            t = p.get("ticker")
            if t:
                all_tickers.add(t)
    if all_tickers:
        cur.executemany(
            """
            insert into public.tickers (ticker, last_seen)
            values (%s, now())
            on conflict (ticker) do nothing
            """,
            [(t,) for t in all_tickers],
        )

    total = 0
    for run in data.get("runs") or []:
        run_date = run.get("run_date")
        if not run_date:
            continue
        cur.execute(
            """
            insert into public.runs (run_date, num_picks, evaluated)
            values (%s, %s, 1)
            on conflict (run_date) do update set num_picks = excluded.num_picks
            returning id
            """,
            (run_date, run.get("num_picks") or 0),
        )
        run_id = cur.fetchone()[0]
        rows = []
        for p in run.get("picks") or []:
            t = p.get("ticker")
            if not t:
                continue
            rows.append((
                run_id, t, p.get("direction"), p.get("verdict"),
                p.get("score"), p.get("setup_type"), p.get("entry_price"),
                p.get("rr_ratio"), p.get("bear_score"),
            ))
        if rows:
            cur.executemany(
                """
                insert into public.picks_history_runs
                    (run_id, ticker, direction, verdict, score, setup_type,
                     entry_price, rr_ratio, bear_score)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )
            total += len(rows)
    return total


def load_portfolio_state_json(cur) -> int:
    data = _read_json(ROOT / "data" / "portfolio_state.json")
    if not data:
        return 0
    cur.execute(
        """
        insert into public.portfolio_state
            (id, equity, cash, margin_reserved, starting_equity, buying_power,
             alpaca_account, last_alpaca_sync, last_reset)
        values (1, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
            equity           = excluded.equity,
            cash             = excluded.cash,
            margin_reserved  = excluded.margin_reserved,
            starting_equity  = excluded.starting_equity,
            buying_power     = excluded.buying_power,
            alpaca_account   = excluded.alpaca_account,
            last_alpaca_sync = excluded.last_alpaca_sync,
            last_reset       = excluded.last_reset,
            updated_at       = now()
        """,
        (
            data.get("equity"), data.get("cash"), data.get("margin_reserved", 0),
            data.get("starting_equity"), data.get("buying_power"),
            data.get("alpaca_account"), data.get("last_alpaca_sync"),
            data.get("last_reset"),
        ),
    )

    n = 0
    for t in data.get("closed_trades") or []:
        cur.execute(
            """
            insert into public.closed_trades
                (ticker, direction, entry_date, exit_date, entry_price, exit_price,
                 shares, pnl_dollars, pnl_pct, win, setup_type, exit_reason,
                 hold_days, alpaca_buy_order_id, alpaca_sell_order_id)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict do nothing
            """,
            (
                t.get("ticker"), t.get("direction"), t.get("entry_date"), t.get("exit_date"),
                t.get("entry_price"), t.get("exit_price"), t.get("shares"),
                t.get("pnl_dollars"), t.get("pnl_pct"), bool(t.get("win", 0)),
                t.get("setup_type"), t.get("exit_reason"), t.get("hold_days"),
                t.get("alpaca_buy_order_id"), t.get("alpaca_sell_order_id"),
            ),
        )
        n += 1

    for pt in data.get("equity_curve") or []:
        cur.execute(
            """
            insert into public.equity_curve (observed_at, equity)
            values (%s, %s)
            on conflict (observed_at) do update set equity = excluded.equity
            """,
            (pt.get("date") or pt.get("observed_at"), pt.get("equity")),
        )
    return n


def load_earnings(cur) -> tuple[int, int, int]:
    """Load watchlist → events; predictions; outcomes (with FK chain)."""
    wl = _read_json(ROOT / "data" / "earnings_watchlist.json") or {}
    preds_data = _read_json(ROOT / "data" / "earnings_beat_predictions.json") or {}

    # Pre-insert all tickers mentioned anywhere in earnings data
    all_tickers = set()
    for it in (wl.get("watchlist") or []):
        if it.get("ticker"): all_tickers.add(it["ticker"])
    for it in (preds_data.get("predictions") or []):
        if it.get("ticker"): all_tickers.add(it["ticker"])
    for it in _read_jsonl(ROOT / "data" / "earnings_outcomes.jsonl"):
        if it.get("ticker"): all_tickers.add(it["ticker"])
    if all_tickers:
        cur.executemany(
            "insert into public.tickers (ticker, last_seen) values (%s, now()) on conflict (ticker) do nothing",
            [(t,) for t in all_tickers],
        )

    n_events = 0
    for it in wl.get("watchlist") or []:
        ticker = it.get("ticker")
        rdate  = it.get("report_date")
        if not (ticker and rdate):
            continue
        cur.execute(
            """
            insert into public.earnings_events
                (ticker, report_date, before_after_market, currency)
            values (%s, %s, %s, %s)
            on conflict (ticker, report_date) do nothing
            """,
            (ticker, rdate, it.get("before_after_market"), it.get("currency", "USD")),
        )
        n_events += 1

    def _num(v):
        """Coerce JSON values like 'n/a' or '' to None for numeric columns."""
        if v is None: return None
        if isinstance(v, (int, float)): return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("", "n/a", "na", "null", "none", "-"): return None
            try: return float(s)
            except ValueError: return None
        return None

    preds = _read_json(ROOT / "data" / "earnings_beat_predictions.json") or {}
    n_pred = 0
    for p in preds.get("predictions") or []:
        ticker = p.get("ticker")
        rdate  = p.get("report_date")
        if not (ticker and rdate):
            continue
        cur.execute("""
            insert into public.earnings_events (ticker, report_date)
            values (%s, %s)
            on conflict (ticker, report_date) do update set ticker = excluded.ticker
            returning id
        """, (ticker, rdate))
        eid = cur.fetchone()[0]
        bd = p.get("breakdown") or {}
        cur.execute(
            """
            insert into public.earnings_predictions
                (earnings_event_id, days_to_earnings, beat_score, tier,
                 historical_pts, historical_rate, historical_n_quarters,
                 runup_10d_pts, runup_10d_value, vol_accum_pts,
                 analyst_upside_pts, analyst_upside_pct,
                 options_pts, options_put_call, options_current_iv)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (earnings_event_id, predicted_at) do nothing
            """,
            (
                eid, p.get("days_to_earnings"), _num(p.get("beat_score")), p.get("tier"),
                _num((bd.get("historical") or {}).get("pts")),
                _num((bd.get("historical") or {}).get("rate")),
                (bd.get("historical") or {}).get("n_quarters"),
                _num((bd.get("runup_10d") or {}).get("pts")),
                _num((bd.get("runup_10d") or {}).get("value")),
                _num((bd.get("vol_accum") or {}).get("pts")),
                _num((bd.get("analyst_upside") or {}).get("pts")),
                _num((bd.get("analyst_upside") or {}).get("upside_pct")),
                _num((bd.get("options") or {}).get("pts")),
                _num((bd.get("options") or {}).get("put_call")),
                _num((bd.get("options") or {}).get("current_iv")),
            ),
        )
        n_pred += 1

    n_out = 0
    for o in _read_jsonl(ROOT / "data" / "earnings_outcomes.jsonl"):
        ticker = o.get("ticker")
        rdate  = o.get("report_date")
        if not (ticker and rdate):
            continue
        cur.execute("""
            insert into public.earnings_events (ticker, report_date)
            values (%s, %s)
            on conflict (ticker, report_date) do update set ticker = excluded.ticker
            returning id
        """, (ticker, rdate))
        eid = cur.fetchone()[0]
        cur.execute(
            """
            insert into public.earnings_outcomes
                (earnings_event_id, estimate, actual, surprise_pct, beat, captured_at)
            values (%s,%s,%s,%s,%s,%s)
            on conflict (earnings_event_id) do update set
                estimate     = excluded.estimate,
                actual       = excluded.actual,
                surprise_pct = excluded.surprise_pct,
                beat         = excluded.beat,
                captured_at  = excluded.captured_at
            """,
            (eid, o.get("estimate"), o.get("actual"), o.get("surprise_pct"),
             o.get("beat"), o.get("captured_at")),
        )
        n_out += 1

    return n_events, n_pred, n_out


def load_decision_log(cur, max_rows: int | None = None) -> int:
    """Stream decision_log.jsonl. Large (33MB) — use BATCH inserts."""
    path = ROOT / "data" / "decision_log.jsonl"
    if not path.exists():
        return 0

    cur.execute("select public.ensure_decision_log_partitions(12)")

    # Pre-pass: collect distinct tickers and pre-insert into master so the
    # decision_log FK doesn't fail mid-stream.
    seen: set[str] = set()
    for row in _read_jsonl(path):
        t = row.get("ticker")
        if t: seen.add(t)
        if max_rows and len(seen) > max_rows * 2:
            break
    if seen:
        cur.executemany(
            "insert into public.tickers (ticker, last_seen) values (%s, now()) on conflict (ticker) do nothing",
            [(t,) for t in seen],
        )

    # cache run_id by date
    run_cache: dict[str, int] = {}

    def get_run_id(observed_at: str) -> int:
        if observed_at in run_cache:
            return run_cache[observed_at]
        cur.execute("""
            insert into public.runs (run_date) values (%s)
            on conflict (run_date) do update set run_date = excluded.run_date
            returning id
        """, (observed_at,))
        rid = cur.fetchone()[0]
        run_cache[observed_at] = rid
        return rid

    total = 0
    batch = []
    for row in _read_jsonl(path):
        ticker = row.get("ticker")
        d = row.get("date") or row.get("observed_at")
        if not (ticker and d):
            continue
        run_id = get_run_id(d)
        batch.append((
            run_id, ticker, d, row.get("verdict"), row.get("reason"),
            row.get("score"), row.get("rs_rank"), row.get("setup_type"),
            row.get("direction"), row.get("regime4"), row.get("profile"),
            json.dumps(row.get("gates_hit") or []),
            json.dumps(row.get("score_breakdown") or {}),
            row.get("has_catalyst"), row.get("weekly_bull"),
            row.get("rr_ratio"), row.get("entry_price"),
        ))
        if len(batch) >= BATCH:
            cur.executemany(
                """
                insert into public.decision_log
                    (run_id, ticker, observed_at, verdict, reason,
                     score, rs_rank, setup_type, direction, regime4, profile,
                     gates_hit_json, score_breakdown_json,
                     has_catalyst, weekly_bull, rr_ratio, entry_price)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
                """, batch
            )
            total += len(batch)
            batch.clear()
            if max_rows and total >= max_rows:
                break

    if batch:
        cur.executemany(
            """
            insert into public.decision_log
                (run_id, ticker, observed_at, verdict, reason,
                 score, rs_rank, setup_type, direction, regime4, profile,
                 gates_hit_json, score_breakdown_json,
                 has_catalyst, weekly_bull, rr_ratio, entry_price)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
            """, batch
        )
        total += len(batch)
    return total


def load_regime_history(cur) -> int:
    data = _read_json(ROOT / "cache" / "regime_history.json")
    if not data:
        return 0
    cur.execute(
        """
        insert into public.regime_history
            (regime3, regime4, flip_confirmed_date, pending_flip_json)
        values (%s, %s, %s, %s::jsonb)
        """,
        (
            data.get("confirmed_regime"),
            data.get("confirmed_regime4"),
            data.get("flip_confirmed_date"),
            json.dumps(data.get("pending_flip") or {}),
        ),
    )
    return 1


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run only one stage")
    ap.add_argument("--decision-log-max", type=int, default=None,
                    help="cap decision_log rows (for smoke tests)")
    args = ap.parse_args()

    stages = [
        ("regime_history",   lambda c: load_regime_history(c)),
        ("portfolio_state",  lambda c: load_portfolio_state_json(c)),
        ("picks_history",    lambda c: load_picks_history(c)),
        ("earnings",         lambda c: sum(load_earnings(c))),
        ("decision_log",     lambda c: load_decision_log(c, args.decision_log_max)),
    ]

    # Per-stage transaction so one failure doesn't poison the next.
    for name, fn in stages:
        if args.only and args.only != name:
            continue
        conn = pg_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    n = fn(cur)
            print(f"  OK {name:20s} {n:>8d} rows")
        except Exception as e:
            msg = str(e).strip().split('\n')[0][:140]
            print(f"  XX {name:20s} ERROR: {msg}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
