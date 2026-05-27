"""
fundamentals_store.py — sqlite-backed fundamentals cache with in-memory read layer.

Design:
  - sqlite (data/fundamentals.db) is source of truth (persistent across runs)
  - Scan loads all rows into a pandas DataFrame at startup (~50 MB, ~ms lookups)
  - Writes go to sqlite in batches at end of fetch cycle
  - Differential refresh: only re-fetch if cache is stale/missing, earnings just
    passed, or short-float refresh day

Fields cached (STATIC — updates quarterly):
  eps_ttm, eps_growth_qoq, revenue_ttm, revenue_growth, gross_margin,
  operating_margin, debt_equity, fcf_ttm, shares_out, short_float,
  sector, industry, market_cap (snapshot), beta, 52wk_high, 52wk_low

Derived at scan time (never cached — depends on live price):
  pe_ttm = price / eps_ttm
  market_cap_live = price * shares_out
  distance_from_high = (price - 52wk_high) / 52wk_high

Source-of-data column tracks which vendor populated each row so we can
measure hit rates per source.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "fundamentals.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fundamentals (
  ticker              TEXT PRIMARY KEY,
  fetched_at          TEXT NOT NULL,
  source              TEXT,
  last_earnings       TEXT,
  next_earnings       TEXT,
  sector              TEXT,
  industry            TEXT,
  market_cap          REAL,
  shares_out          REAL,
  beta                REAL,
  week52_high         REAL,
  week52_low          REAL,
  eps_ttm             REAL,
  eps_growth_qoq      REAL,
  pe_ttm              REAL,
  forward_pe          REAL,
  revenue_ttm         REAL,
  revenue_growth      REAL,
  gross_margin        REAL,
  operating_margin    REAL,
  profit_margin       REAL,
  debt_equity         REAL,
  fcf_ttm             REAL,
  short_float         REAL,
  short_float_fetched TEXT,
  raw_json            TEXT
);
CREATE INDEX IF NOT EXISTS fund_fetched_at ON fundamentals(fetched_at);
CREATE INDEX IF NOT EXISTS fund_next_earnings ON fundamentals(next_earnings);
CREATE INDEX IF NOT EXISTS fund_source ON fundamentals(source);
"""

# Fields populated by full fetch (anything dict-keyed on yf info / finnhub / FMP)
_MAPPABLE_FIELDS = (
    "last_earnings", "next_earnings", "sector", "industry", "market_cap",
    "shares_out", "beta", "week52_high", "week52_low",
    "eps_ttm", "eps_growth_qoq", "pe_ttm", "forward_pe",
    "revenue_ttm", "revenue_growth",
    "gross_margin", "operating_margin", "profit_margin",
    "debt_equity", "fcf_ttm",
    "short_float", "short_float_fetched",
)


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


def init() -> None:
    """Create schema if missing. Idempotent."""
    with _conn() as con:
        con.executescript(_SCHEMA)


def upsert(ticker: str, data: dict, source: str = "unknown") -> None:
    """Insert or replace one ticker's fundamentals."""
    if not ticker:
        return
    init()
    row = {"ticker": ticker.upper(),
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": source,
           "raw_json": json.dumps(data, default=str)[:200_000]}
    for f in _MAPPABLE_FIELDS:
        v = data.get(f)
        # Stringify dates, preserve strings for sector/industry, coerce numeric cols
        # 2026-05-26 · Bug fix: previously sector/industry (TEXT columns in the
        # schema) were sent through the numeric branch and float() coerced them
        # to None, silently dropping every value. Result: all 2,169 cached rows
        # had sector=None, which made get_stock_info skip the sqlite layer 0
        # entirely (since the layer checks `rec.get("sector")` before returning).
        if f in ("last_earnings", "next_earnings", "short_float_fetched"):
            row[f] = str(v)[:19] if v else None
        elif f in ("sector", "industry"):
            row[f] = str(v) if v not in (None, "", "N/A") else None
        else:
            try:
                row[f] = float(v) if v not in (None, "", "N/A") else None
            except (ValueError, TypeError):
                row[f] = None

    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with _conn() as con:
        con.execute(f"INSERT OR REPLACE INTO fundamentals ({cols}) VALUES ({placeholders})", row)


def upsert_batch(rows: Iterable[tuple[str, dict, str]]) -> int:
    """Batch insert. rows = [(ticker, data_dict, source), ...]. Returns count."""
    init()
    n = 0
    with _conn() as con:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for ticker, data, source in rows:
            if not ticker:
                continue
            row: dict[str, Any] = {"ticker": ticker.upper(), "fetched_at": now,
                                    "source": source,
                                    "raw_json": json.dumps(data, default=str)[:200_000]}
            for f in _MAPPABLE_FIELDS:
                v = data.get(f)
                # Mirror upsert() — preserve strings for sector/industry.
                if f in ("last_earnings", "next_earnings", "short_float_fetched"):
                    row[f] = str(v)[:19] if v else None
                elif f in ("sector", "industry"):
                    row[f] = str(v) if v not in (None, "", "N/A") else None
                else:
                    try:
                        row[f] = float(v) if v not in (None, "", "N/A") else None
                    except (ValueError, TypeError):
                        row[f] = None
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            con.execute(f"INSERT OR REPLACE INTO fundamentals ({cols}) VALUES ({placeholders})", row)
            n += 1
    return n


def load_df() -> pd.DataFrame:
    """Load ALL fundamentals into a DataFrame indexed by ticker. Fast in-memory reads."""
    init()
    with _conn() as con:
        df = pd.read_sql_query("SELECT * FROM fundamentals", con)
    if df.empty:
        return pd.DataFrame().set_index(pd.Index([], name="ticker"))
    df["ticker"] = df["ticker"].str.upper()
    return df.set_index("ticker")


def get(ticker: str) -> dict | None:
    """Single-ticker lookup. Returns dict or None if missing."""
    init()
    with _conn() as con:
        row = con.execute("SELECT * FROM fundamentals WHERE ticker = ?", (ticker.upper(),)).fetchone()
    return dict(row) if row else None


def needs_refresh(ticker: str, ttl_days: int = 30) -> bool:
    """
    True if ticker should be re-fetched. Criteria:
      - not in cache
      - fetched_at older than ttl_days
      - next_earnings has passed since last fetch (stock just reported)
    """
    rec = get(ticker)
    if rec is None:
        return True
    fetched = rec.get("fetched_at")
    if not fetched:
        return True
    try:
        fd = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        if fd.tzinfo is None:
            fd = fd.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    age = datetime.now(timezone.utc) - fd
    if age > timedelta(days=ttl_days):
        return True
    # Did earnings pass since last fetch?
    ne = rec.get("next_earnings")
    if ne:
        try:
            ne_dt = datetime.fromisoformat(ne[:10]).date()
            if ne_dt <= date.today() and fd.date() < ne_dt:
                return True
        except Exception:
            pass
    return False


def tickers_needing_refresh(tickers: Iterable[str], ttl_days: int = 30) -> list[str]:
    """Batch version of needs_refresh — returns only the tickers that need a fetch."""
    tickers = [t.upper() for t in tickers if t]
    if not tickers:
        return []
    df = load_df()
    if df.empty:
        return tickers
    existing = set(df.index)
    out: list[str] = []
    today_iso = date.today().isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
    for t in tickers:
        if t not in existing:
            out.append(t); continue
        row = df.loc[t]
        fetched = row.get("fetched_at") or ""
        if fetched < cutoff:
            out.append(t); continue
        ne = row.get("next_earnings") or ""
        if ne and ne[:10] <= today_iso and fetched[:10] < ne[:10]:
            out.append(t)
    return out


def stats() -> dict:
    """Cache summary — for Settings tab display."""
    init()
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
        sources = dict(con.execute(
            "SELECT source, COUNT(*) FROM fundamentals GROUP BY source").fetchall())
        freshness = {}
        for label, days in [("1d", 1), ("7d", 7), ("30d", 30), ("90d", 90)]:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            freshness[label] = con.execute(
                "SELECT COUNT(*) FROM fundamentals WHERE fetched_at >= ?", (cutoff,)).fetchone()[0]
        oldest = con.execute("SELECT MIN(fetched_at) FROM fundamentals").fetchone()[0]
        newest = con.execute("SELECT MAX(fetched_at) FROM fundamentals").fetchone()[0]
    return {
        "total_rows":   total,
        "sources":      sources,
        "fresh_within": freshness,
        "oldest":       oldest,
        "newest":       newest,
        "db_size_kb":   round(DB_PATH.stat().st_size / 1024) if DB_PATH.exists() else 0,
    }


def migrate_from_json_cache(info_dir: Path | None = None) -> dict:
    """
    One-time migration: read cache/info/*.json into sqlite.
    Each file holds yfinance .info dict. Returns stats.
    """
    info_dir = info_dir or (BASE_DIR / "cache" / "info")
    if not info_dir.exists():
        return {"scanned": 0, "migrated": 0, "skipped": 0}

    init()
    scanned = migrated = skipped = 0
    rows: list[tuple[str, dict, str]] = []

    for p in info_dir.glob("*.json"):
        scanned += 1
        ticker = p.stem.upper()
        try:
            info = json.loads(p.read_text())
        except Exception:
            skipped += 1; continue
        if not isinstance(info, dict):
            skipped += 1; continue

        # Translate yfinance-style keys to our schema
        d = {
            "sector":         info.get("sector"),
            "industry":       info.get("industry"),
            "market_cap":     info.get("marketCap"),
            "shares_out":     info.get("sharesOutstanding"),
            "beta":           info.get("beta"),
            "week52_high":    info.get("fiftyTwoWeekHigh"),
            "week52_low":     info.get("fiftyTwoWeekLow"),
            "eps_ttm":        info.get("trailingEps"),
            "pe_ttm":         info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "revenue_ttm":    info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "eps_growth_qoq": info.get("earningsQuarterlyGrowth"),
            "gross_margin":   info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "profit_margin":  info.get("profitMargins"),
            "debt_equity":    info.get("debtToEquity"),
            "fcf_ttm":        info.get("freeCashflow"),
            "short_float":    info.get("shortPercentOfFloat"),
            "next_earnings":  info.get("earningsDate"),
        }
        # Use file mtime as fetched_at approximation (preserves age)
        mtime_iso = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        rows.append((ticker, d, "json_cache_migrated"))

    # Bulk insert preserving mtime requires custom path — do one-at-a-time with overridden fetched_at
    with _conn() as con:
        for ticker, d, source in rows:
            mtime_iso = datetime.fromtimestamp(
                (info_dir / f"{ticker.lower()}.json").stat().st_mtime
                if (info_dir / f"{ticker.lower()}.json").exists()
                else (info_dir / f"{ticker}.json").stat().st_mtime,
                tz=timezone.utc).isoformat(timespec="seconds")
            row = {"ticker": ticker, "fetched_at": mtime_iso, "source": source,
                   "raw_json": json.dumps(d, default=str)[:200_000]}
            for f in _MAPPABLE_FIELDS:
                v = d.get(f)
                if f in ("last_earnings", "next_earnings", "short_float_fetched"):
                    row[f] = str(v)[:19] if v else None
                else:
                    try:
                        row[f] = float(v) if v not in (None, "", "N/A") else None
                    except (ValueError, TypeError):
                        row[f] = None
            cols = ", ".join(row.keys())
            ph = ", ".join(f":{k}" for k in row.keys())
            con.execute(f"INSERT OR REPLACE INTO fundamentals ({cols}) VALUES ({ph})", row)
            migrated += 1

    return {"scanned": scanned, "migrated": migrated, "skipped": skipped}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("migrate")
    sub.add_parser("stats")
    args = ap.parse_args()

    if args.cmd == "init":
        init(); print(f"Schema ready at {DB_PATH}")
    elif args.cmd == "migrate":
        t = time.time()
        r = migrate_from_json_cache()
        print(f"Migration in {time.time()-t:.1f}s:", r)
    elif args.cmd == "stats":
        import pprint; pprint.pprint(stats())
