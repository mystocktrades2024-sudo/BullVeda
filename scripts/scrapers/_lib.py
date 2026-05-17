"""Shared utilities for free-data scrapers — env loading, supabase client, dedup hash."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def load_env_and_supabase():
    """Populate os.environ from .env, return supabase client."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck
    hc = healthcheck()
    if not hc.get("ok"):
        print(f"Supabase healthcheck failed: {hc.get('error')}")
        return None
    return sb_client()


def h(*parts) -> str:
    """Deterministic sync_key."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def chunked(seq, n):
    """Yield n-sized batches from seq."""
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def upsert(sb, table: str, rows: list[dict], on_conflict: str) -> tuple[int, int]:
    """Batch-upsert rows with within-batch dedup. Returns (ok, fail).
    Supports composite keys (comma-separated, e.g. 'ticker,bar_date')."""
    keys = [k.strip() for k in on_conflict.split(",")]
    seen: dict = {}
    for r in rows:
        # Build composite key tuple
        composite = tuple(r.get(k) for k in keys)
        seen[composite] = r
    rows = list(seen.values())
    ok = fail = 0
    for batch in chunked(rows, 200):
        try:
            sb.table(table).upsert(batch, on_conflict=on_conflict).execute()
            ok += len(batch)
        except Exception as e:
            print(f"  ! upsert {table}: {type(e).__name__}: {str(e)[:200]}")
            fail += len(batch)
    return ok, fail
