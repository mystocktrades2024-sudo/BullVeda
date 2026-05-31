#!/usr/bin/env python3
"""
edgar_fundamentals_nightly.py — nightly SEC EDGAR statement refresh.

Sources POINT-IN-TIME financial-statement fundamentals from SEC XBRL companyfacts
(free) and UPSERTs ONLY the statement columns into data/fundamentals.db:
    revenue_ttm, revenue_growth, eps_ttm, eps_growth_qoq  (+ source, fetched_at)

HARD SCOPE: market-derived columns (market_cap, beta, pe_ttm, forward_pe,
week52_high/low, shares_out, sector, industry, ...) are NEVER touched — they stay
EODHD-sourced. We do a column-scoped UPDATE on existing rows and a partial INSERT
on new tickers, so EODHD-owned columns are preserved via COALESCE / non-mention.

Usage:
    python3 scripts/edgar_fundamentals_nightly.py                  # all db tickers
    python3 scripts/edgar_fundamentals_nightly.py --tickers NVDA AAPL MSFT
    python3 scripts/edgar_fundamentals_nightly.py --limit 50       # first N
    python3 scripts/edgar_fundamentals_nightly.py --universe       # scan universe
    python3 scripts/edgar_fundamentals_nightly.py --dry-run        # no db writes

This is the nightly job. To automate, add a launchd plist mirroring
infra/launchd/com.swingtrade.weekly-diagnostics.plist (suggested: nightly ~02:00 PT,
AFTER the EODHD nightly so EODHD market columns are populated first).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import edgar_client as ec  # noqa: E402

DB_PATH = BASE_DIR / "data" / "fundamentals.db"

# Statement columns EDGAR is allowed to write. Nothing else.
STATEMENT_COLS = ("revenue_ttm", "revenue_growth", "eps_ttm", "eps_growth_qoq")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _db_tickers(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT ticker FROM fundamentals ORDER BY ticker")]


def _scan_universe() -> list[str]:
    try:
        import data_fetcher as df
        u = set()
        for fn in ("get_sp500_universe", "get_russell1000_universe"):
            f = getattr(df, fn, None)
            if f:
                try:
                    u.update(f() or [])
                except Exception:
                    pass
        return sorted(u)
    except Exception as e:
        print(f"  ! universe load failed ({e}); falling back to db tickers")
        return []


def _existing_row(conn: sqlite3.Connection, ticker: str) -> dict | None:
    cur = conn.execute("SELECT * FROM fundamentals WHERE ticker=?", (ticker,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def upsert_statements(conn: sqlite3.Connection, ticker: str, st: dict) -> str:
    """
    UPSERT only the statement columns + source/fetched_at. Returns 'update' | 'insert'.
    Market columns are preserved: UPDATE names only statement columns; INSERT for a
    brand-new ticker leaves market columns NULL (EODHD nightly fills them later).
    """
    now = _now_iso()
    # Merge source provenance: if a row already had an eodhd source, mark edgar+eodhd.
    existing = _existing_row(conn, ticker)
    if existing is not None:
        prev_src = (existing.get("source") or "").lower()
        if prev_src and "eodhd" in prev_src and "edgar" not in prev_src:
            new_src = "edgar+eodhd"
        elif prev_src and "edgar" in prev_src:
            new_src = existing.get("source")  # keep (edgar or edgar+eodhd)
        elif prev_src:
            new_src = f"edgar+{existing.get('source')}"
        else:
            new_src = "edgar"
        conn.execute(
            """UPDATE fundamentals
               SET revenue_ttm=?, revenue_growth=?, eps_ttm=?, eps_growth_qoq=?,
                   source=?, fetched_at=?
               WHERE ticker=?""",
            (st.get("revenue_ttm"), st.get("revenue_growth"),
             st.get("eps_ttm"), st.get("eps_growth_qoq"),
             new_src, now, ticker),
        )
        return "update"
    else:
        conn.execute(
            """INSERT INTO fundamentals
                   (ticker, fetched_at, source,
                    revenue_ttm, revenue_growth, eps_ttm, eps_growth_qoq)
               VALUES (?,?,?,?,?,?,?)""",
            (ticker, now, "edgar",
             st.get("revenue_ttm"), st.get("revenue_growth"),
             st.get("eps_ttm"), st.get("eps_growth_qoq")),
        )
        return "insert"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", help="explicit ticker list")
    ap.add_argument("--universe", action="store_true",
                    help="use scan universe instead of db tickers")
    ap.add_argument("--limit", type=int, default=0, help="cap to first N tickers")
    ap.add_argument("--dry-run", action="store_true", help="no db writes")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"! fundamentals.db not found at {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))

    if args.tickers:
        tickers = [t.upper().strip() for t in args.tickers]
    elif args.universe:
        tickers = _scan_universe() or _db_tickers(conn)
    else:
        tickers = _db_tickers(conn)

    if args.limit > 0:
        tickers = tickers[: args.limit]

    print(f"EDGAR nightly: {len(tickers)} tickers · dry_run={args.dry_run}")
    t0 = time.time()
    n_ok = n_update = n_insert = n_none = n_nocik = 0

    for i, t in enumerate(tickers, 1):
        if not ec.cik_for(t):
            n_nocik += 1
            continue
        st = ec.statements(t)
        if not st or (st.get("revenue_ttm") is None and st.get("eps_ttm") is None):
            n_none += 1
            continue
        n_ok += 1
        if not args.dry_run:
            action = upsert_statements(conn, t, st)
            n_update += action == "update"
            n_insert += action == "insert"
            if i % 50 == 0:
                conn.commit()
        if i % 100 == 0:
            print(f"  …{i}/{len(tickers)} ok={n_ok} none={n_none} nocik={n_nocik}")

    if not args.dry_run:
        conn.commit()
    conn.close()

    dt = time.time() - t0
    print(f"\nDone in {dt:.0f}s · processed={len(tickers)}")
    print(f"  statements derived : {n_ok}")
    print(f"  db updates         : {n_update}")
    print(f"  db inserts         : {n_insert}")
    print(f"  no statements      : {n_none}  (ETFs/ADRs/shells with no companyfacts)")
    print(f"  no CIK             : {n_nocik}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
