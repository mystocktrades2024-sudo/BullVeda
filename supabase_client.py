"""
supabase_client.py — Single point of contact with Supabase Postgres.

The whole codebase talks to Supabase through this module. Everything else calls
``sb_client()`` to get the singleton client and uses the standard supabase-py
table API: ``sb.table('positions').upsert(...).execute()``.

Modes (env: SUPABASE_MODE):
  0 — disabled. ``sb_client()`` returns None. SQLite remains canonical.
  1 — dual-write. Writes go to both SQLite and Supabase (Supabase failures logged
      but non-fatal — never breaks a scan). Reads still come from SQLite.
  2 — supabase-canonical. Reads + writes from Supabase. SQLite mirrored
      best-effort. Requires migrate_sqlite_to_supabase.py to have been run.

The client is lazy-initialized on first call so importing this module is free.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Lazy state
_CLIENT: Any | None = None
_MODE: int | None = None
_INIT_ATTEMPTED = False


def _load_dotenv_into_os_environ() -> None:
    """Cheap .env reader (avoids requiring python-dotenv as a dep)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        # Only set if not already in env (real env wins over .env)
        if k and k not in os.environ:
            os.environ[k] = v


def supabase_mode() -> int:
    """Return current SUPABASE_MODE as int (0/1/2)."""
    global _MODE
    if _MODE is None:
        _load_dotenv_into_os_environ()
        try:
            _MODE = int(os.environ.get("SUPABASE_MODE", "0"))
        except ValueError:
            _MODE = 0
    return _MODE


def sb_client() -> Any | None:
    """Return the singleton Supabase client, or None if mode==0 or init fails."""
    global _CLIENT, _INIT_ATTEMPTED
    if supabase_mode() == 0:
        return None
    if _CLIENT is not None:
        return _CLIENT
    if _INIT_ATTEMPTED:
        return None  # already failed, don't retry on every call
    _INIT_ATTEMPTED = True

    _load_dotenv_into_os_environ()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None

    try:
        from supabase import create_client
        _CLIENT = create_client(url, key)
        return _CLIENT
    except Exception:
        return None


def safe_upsert(table: str, payload: dict | list[dict], on_conflict: str | None = None) -> bool:
    """Upsert without ever raising. Returns True on success, False otherwise.

    Used by db.py dual-write hooks where Supabase failures must NEVER break a scan.
    """
    sb = sb_client()
    if sb is None:
        return False
    try:
        q = sb.table(table).upsert(payload, on_conflict=on_conflict) if on_conflict else sb.table(table).upsert(payload)
        q.execute()
        return True
    except Exception:
        return False


def safe_insert(table: str, payload: dict | list[dict]) -> bool:
    """Insert without raising. Returns True on success."""
    sb = sb_client()
    if sb is None:
        return False
    try:
        sb.table(table).insert(payload).execute()
        return True
    except Exception:
        return False


def safe_select(table: str, columns: str = "*", filters: dict | None = None, limit: int | None = None) -> list[dict]:
    """Select rows. Returns [] on any failure (caller decides how to handle).

    filters: simple equality filters, e.g. {'ticker': 'AAPL'}.
    """
    sb = sb_client()
    if sb is None:
        return []
    try:
        q = sb.table(table).select(columns)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if limit:
            q = q.limit(limit)
        return q.execute().data or []
    except Exception:
        return []


def healthcheck() -> dict:
    """Probe Supabase connectivity. Returns {ok, mode, url, error}."""
    out: dict = {"mode": supabase_mode(), "ok": False, "url": None, "error": None}
    if out["mode"] == 0:
        out["error"] = "SUPABASE_MODE=0 (disabled)"
        return out
    sb = sb_client()
    if sb is None:
        out["error"] = "client init failed (check SUPABASE_URL + SUPABASE_SERVICE_KEY in .env)"
        return out
    out["url"] = os.environ.get("SUPABASE_URL")
    try:
        sb.table("meta").select("key,value").limit(1).execute()
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


if __name__ == "__main__":
    # Run as script for a quick connectivity test.
    import json as _json
    print(_json.dumps(healthcheck(), indent=2))
