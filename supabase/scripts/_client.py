"""Shared Supabase / Postgres client init.

Reads `.env` from the SwingTrade repo root and exposes:
  - PG_DSN          : full Postgres connection string (psycopg2 / asyncpg)
  - SUPABASE_URL    : REST endpoint
  - SUPABASE_KEY    : service-role key (bypasses RLS — required for ETL)

Both psycopg2 (preferred for bulk loads + COPY) and supabase-py (preferred
for typed table access) clients are returned on demand.

Required env vars (.env at repo root — same file used by EODHD/Alpaca/Slack):

  SUPABASE_DB_URL            full postgres connection string from Supabase
                             dashboard → Settings → Database (preferred form)
  SUPABASE_URL               https://xxxxx.supabase.co
  SUPABASE_SERVICE_KEY       service_role JWT from Supabase → Settings → API

Legacy fallback (still works if SUPABASE_DB_URL isn't set):
  SUPABASE_DB_HOST / _PORT / _NAME / _USER / _PASSWORD
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]   # supabase/scripts/_client.py → repo root


def _load_dotenv() -> None:
    """Minimal .env loader (no python-dotenv dep). Lines like KEY=VALUE."""
    for candidate in (REPO_ROOT / ".env", REPO_ROOT / "supabase" / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


_load_dotenv()


def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"ERROR: missing required env var: {key}", file=sys.stderr)
        print(f"  → add it to {REPO_ROOT}/.env or supabase/.env", file=sys.stderr)
        sys.exit(2)
    return val


@lru_cache(maxsize=1)
def pg_dsn() -> str:
    # Preferred: single SUPABASE_DB_URL string (Supabase dashboard hands you this)
    direct = os.environ.get("SUPABASE_DB_URL")
    if direct:
        # ensure sslmode=require is present
        if "sslmode=" not in direct:
            direct += ("&" if "?" in direct else "?") + "sslmode=require"
        return direct
    # Legacy: split form
    host = _required("SUPABASE_DB_HOST")
    port = os.environ.get("SUPABASE_DB_PORT", "5432")
    name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    user = os.environ.get("SUPABASE_DB_USER", "postgres")
    pw   = _required("SUPABASE_DB_PASSWORD")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}?sslmode=require"


@lru_cache(maxsize=1)
def supabase_url() -> str:
    return _required("SUPABASE_URL")


@lru_cache(maxsize=1)
def supabase_service_key() -> str:
    return _required("SUPABASE_SERVICE_KEY")


def pg_conn():
    """Return a fresh psycopg2 connection. Caller owns lifecycle."""
    try:
        import psycopg2  # type: ignore
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip3 install psycopg2-binary", file=sys.stderr)
        sys.exit(2)
    return psycopg2.connect(pg_dsn())


def supabase_client():
    """Return a supabase-py client configured with service-role key (bypasses RLS)."""
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("ERROR: supabase-py not installed. Run: pip3 install supabase", file=sys.stderr)
        sys.exit(2)
    return create_client(supabase_url(), supabase_service_key())


def repo_root() -> Path:
    return REPO_ROOT
