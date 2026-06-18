"""
nas_pg.py — connection + sync to the self-hosted Postgres on the Synology NAS.

Architecture (decided 2026-06-18):
  • Local SQLite (data/swingtrade.db) = HOT operational store, 90-day retention.
  • NAS Postgres (DS1520+, 192.168.1.25:5433) = DEEP audit store, FULL retention.

The NAS box removes the local-disk limit (162 GB free, 89% full), so the deep
store can keep snapshots for as long as we want. The active scan never depends
on the NAS — every call here is best-effort and swallows errors so a NAS outage
can never break a scan.

Connection comes from NAS_PG_URL in .env (gitignored):
  NAS_PG_URL=postgresql://swing:****@192.168.1.25:5433/swingtrade

Public API:
  enabled()                         -> bool (URL configured)
  get_conn()                        -> psycopg2 connection (or None)
  init_schema()                     -> create deep-store tables
  upsert_snapshots(rows, cols)      -> push snapshot rows (ON CONFLICT do nothing)
  count()                           -> row count in the NAS ticker_snapshots
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("swingtrade.nas_pg")
ROOT = Path(__file__).resolve().parent


def _load_url() -> str | None:
    url = os.environ.get("NAS_PG_URL")
    if url:
        return url
    # fall back to parsing .env (the app doesn't always load dotenv globally)
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("NAS_PG_URL="):
                return line.split("=", 1)[1].strip()
    return None


def enabled() -> bool:
    return bool(_load_url())


def get_conn():
    """Return a psycopg2 connection to the NAS Postgres, or None (best-effort)."""
    url = _load_url()
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url, connect_timeout=5)
    except Exception as e:
        log.debug(f"nas_pg connect failed (non-fatal): {e}")
        return None


# Deep-store schema — mirrors the SQLite ticker_snapshots flat columns + the FULL
# gzipped payload as bytea. PK (run_id, ticker) makes the sync idempotent.
_DDL = """
CREATE TABLE IF NOT EXISTS ticker_snapshots (
    captured_at    TEXT,
    run_id         TEXT NOT NULL,
    run_date       TEXT NOT NULL,
    ticker         TEXT NOT NULL,
    verdict        TEXT,
    stage          TEXT,
    score          DOUBLE PRECISION,
    rs_rank        INTEGER,
    regime         TEXT,
    setup_family   TEXT,
    setup          TEXT,
    entry_quality  TEXT,
    catalyst_tier  INTEGER,
    rvol           DOUBLE PRECISION,
    price          DOUBLE PRECISION,
    stop           DOUBLE PRECISION,
    target1        DOUBLE PRECISION,
    rr_ratio       DOUBLE PRECISION,
    alloc_pct      DOUBLE PRECISION,
    conviction_tier TEXT,
    target2        DOUBLE PRECISION,
    pct_chg        DOUBLE PRECISION,
    p_up           DOUBLE PRECISION,
    mode           TEXT,
    raw_json       TEXT,
    raw_gz         BYTEA,
    PRIMARY KEY (run_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_pg_tsnap_ticker_date ON ticker_snapshots(ticker, run_date);
CREATE INDEX IF NOT EXISTS idx_pg_tsnap_run_date    ON ticker_snapshots(run_date);
CREATE INDEX IF NOT EXISTS idx_pg_tsnap_setup       ON ticker_snapshots(setup_family);

CREATE TABLE IF NOT EXISTS audit_live_vs_baseline (
    generated_at TEXT,
    setup        TEXT,
    family       TEXT,
    live_n       INTEGER,
    live_wr      DOUBLE PRECISION,
    live_wilson_lb DOUBLE PRECISION,
    live_pf      DOUBLE PRECISION,
    base_wr      DOUBLE PRECISION,
    base_pf      DOUBLE PRECISION,
    base_pf_haircut DOUBLE PRECISION,
    pf_gap       DOUBLE PRECISION,
    verdict      TEXT,
    PRIMARY KEY (generated_at, setup)
);
"""

# Columns synced, in order (must match the SQLite SELECT in the sync).
SYNC_COLS = [
    "captured_at", "run_id", "run_date", "ticker", "verdict", "stage", "score",
    "rs_rank", "regime", "setup_family", "setup", "entry_quality", "catalyst_tier",
    "rvol", "price", "stop", "target1", "rr_ratio", "alloc_pct", "conviction_tier",
    "target2", "pct_chg", "p_up", "mode", "raw_json", "raw_gz",
]


def init_schema() -> bool:
    conn = get_conn()
    if not conn:
        return False
    try:
        with conn, conn.cursor() as cur:
            cur.execute(_DDL)
        return True
    except Exception as e:
        log.warning(f"nas_pg init_schema failed: {e}")
        return False
    finally:
        conn.close()


def upsert_snapshots(rows: list[tuple]) -> int:
    """Insert snapshot rows (tuples in SYNC_COLS order). Idempotent on (run_id,ticker)."""
    if not rows:
        return 0
    conn = get_conn()
    if not conn:
        return 0
    try:
        from psycopg2.extras import execute_values
        ph = "(" + ",".join(["%s"] * len(SYNC_COLS)) + ")"
        sql = (f"INSERT INTO ticker_snapshots ({','.join(SYNC_COLS)}) VALUES %s "
               f"ON CONFLICT (run_id, ticker) DO NOTHING")
        with conn, conn.cursor() as cur:
            execute_values(cur, sql, rows, template=ph, page_size=500)
        return len(rows)
    except Exception as e:
        log.warning(f"nas_pg upsert_snapshots failed (non-fatal): {e}")
        return 0
    finally:
        conn.close()


def count() -> int | None:
    conn = get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ticker_snapshots")
            return cur.fetchone()[0]
    except Exception:
        return None
    finally:
        conn.close()
