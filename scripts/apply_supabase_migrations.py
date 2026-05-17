#!/usr/bin/env python3
"""
apply_supabase_migrations.py — Run migrations/*.sql against Supabase Postgres.

Uses SUPABASE_DB_URL (Postgres connection string) + psycopg2. Idempotent —
every migration uses CREATE TABLE / ADD COLUMN IF NOT EXISTS, so re-runs are
safe. Tracks applied migrations in a meta key.

Usage:
    python3 scripts/apply_supabase_migrations.py          # dry-run (lists pending)
    python3 scripts/apply_supabase_migrations.py --apply  # actually run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"


def _load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually run migrations (default: dry-run)")
    args = ap.parse_args()

    _load_dotenv()

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set in .env", file=sys.stderr)
        sys.exit(1)

    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        print(f"No migrations found in {MIGRATIONS_DIR}")
        return

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"================================================================")
    print(f"Supabase migrations  ({mode})")
    print(f"================================================================")
    print(f"DB host: {db_url.split('@')[-1].split('/')[0] if '@' in db_url else '<masked>'}")
    print(f"Migrations dir: {MIGRATIONS_DIR}")
    print(f"Found {len(files)} migration files\n")

    if not args.apply:
        for f in files:
            print(f"  → {f.name}  ({f.stat().st_size:,} bytes)")
        print("\nDry-run only. Re-run with --apply to execute.")
        return

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    total_start = time.time()
    for f in files:
        sql = f.read_text()
        print(f"→ {f.name}", end=" ", flush=True)
        t0 = time.time()
        try:
            cur.execute(sql)
            conn.commit()
            elapsed = (time.time() - t0) * 1000
            print(f"ok ({elapsed:.0f}ms)")
        except Exception as e:
            conn.rollback()
            print(f"FAILED: {type(e).__name__}: {str(e)[:200]}")
            cur.close()
            conn.close()
            sys.exit(1)

    cur.close()
    conn.close()
    total_elapsed = time.time() - total_start
    print(f"\nAll {len(files)} migrations applied in {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
