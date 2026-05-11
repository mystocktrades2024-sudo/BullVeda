#!/usr/bin/env python3
"""Apply every SQL migration in supabase/migrations/ to the configured Postgres.

Usage:
    python3 supabase/apply.py                  # apply all migrations
    python3 supabase/apply.py --dry-run        # parse but don't execute
    python3 supabase/apply.py --only 0019      # apply only the file starting with 0019

Migrations are applied inside ONE transaction per file. Idempotent: SQL uses
`create table if not exists`, `create index if not exists`, `on conflict do nothing`.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from _client import pg_conn, repo_root  # noqa: E402


def find_migrations(filt: str | None = None) -> list[Path]:
    base = repo_root() / "supabase" / "migrations"
    files = sorted(p for p in base.glob("*.sql") if p.is_file())
    if filt:
        files = [p for p in files if p.name.startswith(filt)]
    return files


def apply_one(path: Path, dry: bool) -> tuple[bool, float, str]:
    sql = path.read_text()
    t0 = time.time()
    if dry:
        return True, 0.0, f"DRY-RUN ({len(sql)} chars)"
    conn = pg_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql)
        return True, time.time() - t0, "OK"
    except Exception as e:
        return False, time.time() - t0, f"FAIL: {e}"
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="parse & list only")
    ap.add_argument("--only",    default=None,        help="apply only files matching prefix (e.g. 0019)")
    args = ap.parse_args()

    files = find_migrations(args.only)
    if not files:
        print("No migration files found.")
        return

    print(f"Found {len(files)} migration file(s)")
    print("-" * 70)
    ok = 0
    for p in files:
        success, dur, msg = apply_one(p, args.dry_run)
        flag = "✓" if success else "✗"
        print(f"  {flag} {p.name:48s} {dur:6.2f}s  {msg}")
        if success:
            ok += 1
        else:
            print(f"\nABORTED after {ok} files. Fix the error above and re-run.")
            sys.exit(1)
    print("-" * 70)
    print(f"Done: {ok}/{len(files)} migration(s) applied.")


if __name__ == "__main__":
    main()
