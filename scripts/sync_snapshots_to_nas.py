#!/usr/bin/env python3
"""
sync_snapshots_to_nas.py — push SQLite ticker_snapshots → NAS Postgres (deep store).

SQLite is the hot 90-day operational store; the NAS Postgres keeps FULL retention
for audit. This pushes any local rows not yet on the NAS (idempotent — ON CONFLICT
(run_id,ticker) DO NOTHING). Safe to run repeatedly; best-effort (NAS down = no-op).

  python3 scripts/sync_snapshots_to_nas.py            # incremental (since last sync)
  python3 scripts/sync_snapshots_to_nas.py --full     # re-scan all local rows
  python3 scripts/sync_snapshots_to_nas.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
import nas_pg


def _latest_nas_run_date() -> str | None:
    conn = nas_pg.get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(run_date) FROM ticker_snapshots")
            r = cur.fetchone()
            return r[0] if r else None
    except Exception:
        return None
    finally:
        conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sync_snapshots_to_nas.py")
    ap.add_argument("--full", action="store_true", help="re-scan ALL local rows")
    ap.add_argument("--since", default=None, help="only rows with run_date >= this (YYYY-MM-DD)")
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args(argv)

    if not nas_pg.enabled():
        print("NAS_PG_URL not set — nothing to sync"); return
    if not nas_pg.init_schema():
        print("NAS schema init failed (NAS unreachable?) — aborting"); return

    since = args.since
    if not since and not args.full:
        since = _latest_nas_run_date()  # incremental from where the NAS left off
    where = "WHERE run_date >= ?" if since else ""
    params = (since,) if since else ()
    print(f"sync mode: {'FULL' if args.full else ('since ' + since if since else 'ALL')}")

    import psycopg2  # for Binary wrapping of the gzipped blob
    sconn = db.get_conn()
    sel = (f"SELECT {','.join(nas_pg.SYNC_COLS)} FROM ticker_snapshots {where} "
           f"ORDER BY run_date, run_id")
    cur = sconn.execute(sel, params)

    t0 = time.time(); total = 0; pushed = 0
    batch = []
    blob_idx = nas_pg.SYNC_COLS.index("raw_gz")
    for row in cur:
        row = list(row)
        if row[blob_idx] is not None:
            row[blob_idx] = psycopg2.Binary(row[blob_idx])  # bytes → bytea
        batch.append(tuple(row))
        if len(batch) >= args.batch:
            pushed += nas_pg.upsert_snapshots(batch); total += len(batch); batch = []
            print(f"  …{total} rows scanned, {pushed} sent · {time.time()-t0:.0f}s")
    if batch:
        pushed += nas_pg.upsert_snapshots(batch); total += len(batch)

    nas_n = nas_pg.count()
    print(f"✓ done · {total} local rows scanned, {pushed} upserted · "
          f"NAS now holds {nas_n} rows · {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
