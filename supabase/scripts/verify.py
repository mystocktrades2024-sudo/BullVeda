"""Compare row counts: local SQLite/JSON sources vs Supabase Postgres.

Reports a per-table diff so you can spot loaders that under- or over-loaded.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn, repo_root  # noqa: E402

ROOT = repo_root()


def sqlite_count(db: Path, table: str) -> int:
    if not db.exists():
        return -1
    try:
        con = sqlite3.connect(str(db))
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        con.close()
        return n
    except Exception:
        return -1


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return -1
    with path.open() as f:
        return sum(1 for line in f if line.strip())


def json_array_count(path: Path, key: str) -> int:
    if not path.exists():
        return -1
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and key in data:
        v = data[key]
        if isinstance(v, list):
            return len(v)
    return -1


def pg_count(cur, table: str) -> int:
    try:
        cur.execute(f"select count(*) from public.{table}")
        return cur.fetchone()[0]
    except Exception:
        return -1


COMPARISONS = [
    # (label, source_n_lambda, pg_table)
    ("portfolio_state",       lambda: sqlite_count(ROOT/"data/swingtrade.db", "portfolio_state"),       "portfolio_state"),
    ("positions",             lambda: sqlite_count(ROOT/"data/swingtrade.db", "positions"),             "positions"),
    ("closed_trades(SQLite)", lambda: sqlite_count(ROOT/"data/swingtrade.db", "closed_trades"),         "closed_trades"),
    ("equity_curve",          lambda: sqlite_count(ROOT/"data/swingtrade.db", "equity_curve"),          "equity_curve"),
    ("signal_log(SQLite)",    lambda: sqlite_count(ROOT/"data/swingtrade.db", "signal_log"),            "signal_log"),
    ("runs",                  lambda: sqlite_count(ROOT/"data/swingtrade.db", "runs"),                  "runs"),
    ("fundamentals",          lambda: sqlite_count(ROOT/"data/fundamentals.db", "fundamentals"),        "ticker_fundamentals"),
    ("custom_tickers",        lambda: sqlite_count(ROOT/"data/swingtrade.db", "custom_tickers"),       "custom_tickers"),
    ("alert_log",             lambda: sqlite_count(ROOT/"data/swingtrade.db", "alert_log"),             "alert_log"),
    ("earnings_watchlist",    lambda: json_array_count(ROOT/"data/earnings_watchlist.json", "watchlist"), "earnings_events"),
    ("earnings_predictions",  lambda: json_array_count(ROOT/"data/earnings_beat_predictions.json", "predictions"), "earnings_predictions"),
    ("earnings_outcomes",     lambda: jsonl_count(ROOT/"data/earnings_outcomes.jsonl"),                "earnings_outcomes"),
    ("decision_log",          lambda: jsonl_count(ROOT/"data/decision_log.jsonl"),                     "decision_log"),
    ("signal_log(JSON)",      lambda: json_array_count(ROOT/"data/signal_log.json", "_"),              "signal_log"),
]


def main():
    conn = pg_conn()
    print(f"{'Source':28s} {'Local':>10s} {'Supabase':>10s} {'Diff':>10s}   Verdict")
    print("-" * 80)
    try:
        with conn.cursor() as cur:
            for label, src_fn, pg_table in COMPARISONS:
                src = src_fn()
                dst = pg_count(cur, pg_table)
                diff = (dst - src) if src >= 0 and dst >= 0 else None
                if src < 0:
                    verdict = "no-source"
                elif dst < 0:
                    verdict = "no-target"
                elif src == dst:
                    verdict = "✓ match"
                elif dst == 0:
                    verdict = "✗ NOT LOADED"
                elif dst < src:
                    verdict = "△ under-loaded"
                else:
                    verdict = "△ over-loaded (dupes?)"
                print(f"{label:28s} {src:>10} {dst:>10} {('' if diff is None else f'{diff:+d}'):>10}   {verdict}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
