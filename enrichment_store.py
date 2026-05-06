"""
enrichment_store.py — Generic sqlite cache for all per-ticker enrichment sources.

One table, keyed by (ticker, source). Each row stores the full JSON response
with a fetched_at timestamp. Source-specific TTLs control when to re-fetch.

Default TTLs:
  finnhub:       7 days   (metrics update weekly)
  fmp:           7 days
  sec:           30 days  (filings are quarterly)
  congressional: 7 days   (disclosure lag)
  borrow:        1 day    (short rates change daily)
  gamma:         1 day
  uoa:           4 hours
  premarket:     0        (always fresh)
  analyst:       7 days

Usage:
    from enrichment_store import get_cached, set_cached, needs_refresh

    cached = get_cached(ticker, 'finnhub')
    if cached is not None:
        return cached   # skip API call

    data = _fetch_from_finnhub(ticker)  # actual API call
    set_cached(ticker, 'finnhub', data)
    return data
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "enrichment_cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS enrichment (
    ticker     TEXT NOT NULL,
    source     TEXT NOT NULL,
    data       TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (ticker, source)
);
CREATE INDEX IF NOT EXISTS enr_source ON enrichment(source);
CREATE INDEX IF NOT EXISTS enr_fetched ON enrichment(fetched_at);
"""

DEFAULT_TTL: dict[str, float] = {
    "finnhub":       7,
    "fmp":           7,
    "sec":           30,
    "congressional": 7,
    "borrow":        1,
    "gamma":         1,
    "uoa":           0.17,   # ~4 hours
    "premarket":     0,      # always fresh
    "analyst":       7,
    "options_intel":  1,
    "stocktwits":    0.5,    # 12 hours
    "reddit_wsb":    1,
}

_initialized = False


@contextmanager
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _init():
    global _initialized
    if not _initialized:
        with _conn() as con:
            con.executescript(_SCHEMA)
        _initialized = True


def get_cached(ticker: str, source: str, ttl_days: Optional[float] = None) -> Optional[dict]:
    """Return cached data if fresh, else None."""
    _init()
    if ttl_days is None:
        ttl_days = DEFAULT_TTL.get(source, 7)
    if ttl_days <= 0:
        return None  # always fresh = never cache
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM enrichment WHERE ticker=? AND source=? AND fetched_at>=?",
            (ticker.upper(), source, cutoff)
        ).fetchone()
    if row:
        try:
            return json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def get_cached_batch(tickers: list[str], source: str, ttl_days: Optional[float] = None) -> dict[str, dict]:
    """Batch lookup. Returns {ticker: data} for cache hits only."""
    _init()
    if ttl_days is None:
        ttl_days = DEFAULT_TTL.get(source, 7)
    if ttl_days <= 0:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
    out: dict[str, dict] = {}
    uppers = [t.upper() for t in tickers]
    # sqlite IN clause with parameterized query
    with _conn() as con:
        placeholders = ",".join("?" * len(uppers))
        rows = con.execute(
            f"SELECT ticker, data FROM enrichment WHERE source=? AND fetched_at>=? AND ticker IN ({placeholders})",
            [source, cutoff] + uppers
        ).fetchall()
    for row in rows:
        try:
            out[row["ticker"]] = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def set_cached(ticker: str, source: str, data: Any) -> None:
    """Write or update one cache entry."""
    _init()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    blob = json.dumps(data, default=str)[:500_000]
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO enrichment (ticker, source, data, fetched_at) VALUES (?,?,?,?)",
            (ticker.upper(), source, blob, now)
        )


def set_cached_batch(rows: list[tuple[str, str, Any]]) -> int:
    """Batch insert. rows = [(ticker, source, data), ...]. Returns count."""
    _init()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    with _conn() as con:
        for ticker, source, data in rows:
            blob = json.dumps(data, default=str)[:500_000]
            con.execute(
                "INSERT OR REPLACE INTO enrichment (ticker, source, data, fetched_at) VALUES (?,?,?,?)",
                (ticker.upper(), source, blob, now)
            )
            n += 1
    return n


def needs_refresh(ticker: str, source: str, ttl_days: Optional[float] = None) -> bool:
    """True if ticker+source needs a fresh fetch."""
    return get_cached(ticker, source, ttl_days) is None


def stats() -> dict:
    """Cache summary for Settings UI."""
    _init()
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM enrichment").fetchone()[0]
        by_source = dict(con.execute(
            "SELECT source, COUNT(*) FROM enrichment GROUP BY source"
        ).fetchall())
        oldest = con.execute("SELECT MIN(fetched_at) FROM enrichment").fetchone()[0]
        newest = con.execute("SELECT MAX(fetched_at) FROM enrichment").fetchone()[0]
    return {
        "total_rows": total,
        "by_source": by_source,
        "oldest": oldest,
        "newest": newest,
        "db_size_kb": round(DB_PATH.stat().st_size / 1024) if DB_PATH.exists() else 0,
    }


def prune(max_age_days: int = 90) -> int:
    """Delete entries older than max_age_days. Returns count deleted."""
    _init()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    with _conn() as con:
        n = con.execute("DELETE FROM enrichment WHERE fetched_at < ?", (cutoff,)).rowcount
    return n
