"""
ticker_snapshots.py — append-only per-ticker per-scan snapshot store.

Goal: enable field-by-field "what changed over time" audit. Every swing_trade
scan appends one row per scored ticker to data/swingtrade.db `ticker_snapshots`.
Storing the FULL payload as raw_json lets the audit reach any field; the
flat columns make common queries (verdict / score / regime over time) fast.

Schema:
  captured_at   TEXT   ISO timestamp, indexed
  run_id        TEXT   "YYYY-MM-DD_HH:MM" — same value for every ticker in a scan
  run_date      TEXT   "YYYY-MM-DD"       — duplicate of run_id's date half, for quick filter
  ticker        TEXT   symbol             — indexed
  verdict       TEXT
  stage         TEXT
  score         REAL
  rs_rank       INTEGER
  regime        TEXT
  setup_family  TEXT
  setup         TEXT
  entry_quality TEXT
  catalyst_tier INTEGER
  rvol          REAL
  price         REAL
  stop          REAL
  target1       REAL
  rr_ratio      REAL
  alloc_pct     REAL
  raw_json      TEXT   full ticker payload (for any field not flattened above)

Append-only — no deletes from this module. Cap retention via a separate
purge script if size grows (each scan = ~77 rows, ~50KB raw_json each →
~4MB/scan; at 6 scans/day = ~24MB/day; reach ~1GB in 6 weeks).

Usage:
    from ticker_snapshots import init_snapshot_table, capture_scan
    init_snapshot_table()              # idempotent; called at module import
    capture_scan(tickers_dict, run_id="2026-05-10_22:23")

Query helpers:
    history_for(ticker)                → list of dicts, oldest → newest
    diff(ticker, fields=None)          → field-level diff between consecutive snapshots
"""
from __future__ import annotations

import gzip
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import db

log = logging.getLogger("swingtrade.ticker_snapshots")
BASE_DIR = Path(__file__).resolve().parent

# ── Flat columns we extract for fast queries / dashboard sparklines ─────
_FLAT_COLS = [
    ("verdict",         "TEXT"),
    ("stage",           "TEXT"),
    ("score",           "REAL"),
    ("rs_rank",         "INTEGER"),
    ("regime",          "TEXT"),
    ("setup_family",    "TEXT"),
    ("setup",           "TEXT"),
    ("entry_quality",   "TEXT"),
    ("catalyst_tier",   "INTEGER"),
    ("rvol",            "REAL"),
    ("price",           "REAL"),
    ("stop",            "REAL"),
    ("target1",         "REAL"),
    ("rr_ratio",        "REAL"),
    ("alloc_pct",       "REAL"),
    # Added 2026-06-18 — the fields the owner queries most (conviction tier, T2,
    # day change, ML p_up, mode). Flat so they don't require decompressing raw_gz.
    ("conviction_tier", "TEXT"),
    ("target2",         "REAL"),
    ("pct_chg",         "REAL"),
    ("p_up",            "REAL"),
    ("mode",            "TEXT"),
]

# Retain the heavy full-payload snapshots for this many days, then purge whole
# rows (owner decision 2026-06-18: "all the runs for last 3 months only").
RETENTION_DAYS = 90


def _coerce(v, kind: str):
    """Coerce value to SQLite-friendly type; None on failure."""
    if v is None:
        return None
    try:
        if kind == "INTEGER":
            return int(v)
        if kind == "REAL":
            return float(v)
        return str(v)
    except (TypeError, ValueError):
        return None


def init_snapshot_table(conn: sqlite3.Connection | None = None) -> None:
    """Create ticker_snapshots table + indexes if not exists. Idempotent."""
    own = conn is None
    if own:
        conn = db.get_conn()

    cols_sql = ",\n            ".join(f"{name} {kind}" for name, kind in _FLAT_COLS)
    ddl = f"""
        CREATE TABLE IF NOT EXISTS ticker_snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at  TEXT NOT NULL,
            run_id       TEXT NOT NULL,
            run_date     TEXT NOT NULL,
            ticker       TEXT NOT NULL,
            {cols_sql},
            raw_json     TEXT,
            raw_gz       BLOB
        )
    """
    conn.execute(ddl)
    # Idempotent migration: the table predates the extra flat columns + raw_gz, so
    # ADD COLUMN any that are missing (SQLite has no ADD COLUMN IF NOT EXISTS).
    have = {r[1] for r in conn.execute("PRAGMA table_info(ticker_snapshots)").fetchall()}
    for name, kind in _FLAT_COLS + [("raw_gz", "BLOB")]:
        if name not in have:
            conn.execute(f"ALTER TABLE ticker_snapshots ADD COLUMN {name} {kind}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tsnap_ticker_date ON ticker_snapshots(ticker, run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tsnap_run_id       ON ticker_snapshots(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tsnap_captured_at  ON ticker_snapshots(captured_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tsnap_run_date     ON ticker_snapshots(run_date)")
    conn.commit()
    if own:
        log.debug("ticker_snapshots table initialized")


def _extract_flat(t: dict) -> dict:
    """Pull flat columns from a ticker payload (handles both v2-flat and last_bundle-nested schemas)."""
    def first(*paths):
        for p in paths:
            cur = t
            for part in p.split("."):
                if cur is None: break
                cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is not None and cur != "":
                return cur
        return None

    return {
        "verdict":       first("verdict"),
        "stage":         first("stage"),
        "score":         first("score"),
        "rs_rank":       first("rs_rank"),
        "regime":        first("regime", "regime4"),
        "setup_family":  first("setup_family"),
        "setup":         first("setup", "trade_plan.setup_type"),
        "entry_quality": first("entry_quality"),
        "catalyst_tier": first("catalyst_tier"),
        "rvol":          first("rvol"),
        "price":         first("price"),
        "stop":          first("stop", "trade_plan.stop"),
        "target1":       first("target1", "t1", "trade_plan.target1"),
        "rr_ratio":      first("rr_ratio", "rr", "trade_plan.rr_ratio"),
        "alloc_pct":     first("alloc_pct", "kelly_size.final_alloc_pct"),
        "conviction_tier": first("conviction_tier", "conviction.label", "conviction_label"),
        "target2":       first("target2", "t2", "trade_plan.target2"),
        "pct_chg":       first("pct_chg", "perf_1d", "change"),
        "p_up":          first("p_up", "ml.direction.p_up"),
        "mode":          first("mode", "_mode"),
    }


def capture_scan(tickers: dict | list, run_id: str | None = None,
                 captured_at: str | None = None) -> int:
    """Append a snapshot row per ticker. Idempotent on (run_id, ticker).

    Args:
      tickers:    dict (sym → payload) OR list of payloads with `ticker` key.
      run_id:     unique scan identifier ("YYYY-MM-DD_HH:MM"). Defaults to now.
      captured_at: ISO timestamp. Defaults to now.

    Returns count of rows actually inserted (de-duplicates on (run_id, ticker)).
    """
    now_iso = captured_at or datetime.now().isoformat(timespec="seconds")
    run_id = run_id or now_iso.replace("T", "_")[:16]
    run_date = run_id.split("_", 1)[0]

    if isinstance(tickers, dict):
        items = list(tickers.items())
    else:
        items = [((t.get("ticker") or ""), t) for t in tickers]

    conn = db.get_conn()
    init_snapshot_table(conn)

    # De-dupe: skip tickers already captured in this run_id
    existing = {
        r[0] for r in conn.execute(
            "SELECT ticker FROM ticker_snapshots WHERE run_id = ?", (run_id,)
        ).fetchall()
    }

    col_names = ["captured_at", "run_id", "run_date", "ticker"] + [c for c, _ in _FLAT_COLS] + ["raw_json", "raw_gz"]
    placeholders = ",".join(["?"] * len(col_names))
    insert_sql = f"INSERT INTO ticker_snapshots ({','.join(col_names)}) VALUES ({placeholders})"

    inserted = 0
    rows = []
    for sym, payload in items:
        sym = (sym or (payload.get("ticker") if isinstance(payload, dict) else "") or "").upper()
        if not sym or sym in existing:
            continue
        if not isinstance(payload, dict):
            continue
        flat = _extract_flat(payload)
        row = [now_iso, run_id, run_date, sym]
        for col, kind in _FLAT_COLS:
            row.append(_coerce(flat.get(col), kind))
        # raw_json: the lightweight queryable subset (kept for back-compat readers).
        SAFE_RAW = {
            k: v for k, v in payload.items()
            if k in {
                "ticker", "name", "sector", "industry", "verdict", "score",
                "stage", "decision_label", "regime", "setup_family", "entry_quality",
                "entry_subtype", "catalyst_tier", "catalyst_tags", "rs_rank",
                "rvol", "atr_pct", "rsi", "beta", "price",
                "entry_low", "entry_high", "stop", "target1", "target2",
                "rr_ratio", "alloc_pct", "audit_trail", "caveats",
                "gates_evaluated", "reject_reason", "conviction_tier",
                "star_rating", "ema_signal", "macd_signal", "weekly_bull",
                "sector_demoted", "sector_demotion_reason",
            }
        }
        row.append(json.dumps(SAFE_RAW, default=str))
        # raw_gz: the FULL payload (every field the scanner produced), gzipped.
        # ~34 KB/row vs 130 KB raw → ~4×. This is "all the details" the owner asked
        # for; RETENTION_DAYS purge keeps the rolling window from filling the disk.
        full = json.dumps(payload, default=str).encode("utf-8")
        row.append(gzip.compress(full, compresslevel=6))
        rows.append(tuple(row))
        inserted += 1

    if rows:
        conn.executemany(insert_sql, rows)
        conn.commit()
        log.info(f"ticker_snapshots: captured {inserted} ticker rows for run_id={run_id}")
        purge_old(conn)  # trim to the rolling RETENTION_DAYS window
    else:
        log.debug(f"ticker_snapshots: nothing to capture for run_id={run_id} (already exists or empty)")

    return inserted


def purge_old(conn: sqlite3.Connection | None = None, days: int = RETENTION_DAYS) -> int:
    """Delete whole snapshot rows older than `days` (rolling retention window).

    Owner decision 2026-06-18: keep all runs for the last 3 months only. Returns
    rows deleted. Best-effort — a purge failure never blocks scan completion.
    """
    own = conn is None
    if own:
        conn = db.get_conn()
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cur = conn.execute("DELETE FROM ticker_snapshots WHERE run_date < ?", (cutoff,))
        n = cur.rowcount or 0
        conn.commit()
        if n:
            log.info(f"ticker_snapshots: purged {n} rows older than {cutoff} ({days}d retention)")
        return n
    except Exception as e:
        log.warning(f"ticker_snapshots purge failed (non-fatal): {e}")
        return 0


def get_full(run_id: str, ticker: str) -> dict | None:
    """Decompress and return the FULL captured payload for (run_id, ticker)."""
    conn = db.get_conn()
    r = conn.execute(
        "SELECT raw_gz FROM ticker_snapshots WHERE run_id = ? AND ticker = ?",
        (run_id, ticker.upper()),
    ).fetchone()
    if not r or r[0] is None:
        return None
    try:
        return json.loads(gzip.decompress(r[0]).decode("utf-8"))
    except Exception:
        return None


def history_for(ticker: str, limit: int = 100) -> list[dict]:
    """Return snapshot history for a ticker, oldest → newest."""
    conn = db.get_conn()
    init_snapshot_table(conn)
    cur = conn.execute(
        "SELECT * FROM ticker_snapshots WHERE ticker = ? ORDER BY captured_at ASC LIMIT ?",
        (ticker.upper(), limit),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def diff(ticker: str, fields: Iterable[str] | None = None) -> list[dict]:
    """For each consecutive snapshot pair, return {field: (prev, curr)} for changed fields.

    Args:
      ticker: symbol
      fields: which flat fields to diff. None = all flat columns.

    Returns: list of {run_id, captured_at, changes: {field: [prev, curr]}}
    """
    rows = history_for(ticker, limit=200)
    if len(rows) < 2:
        return []
    track_cols = list(fields) if fields else [c for c, _ in _FLAT_COLS]
    out = []
    for i in range(1, len(rows)):
        prev, curr = rows[i - 1], rows[i]
        diffs = {}
        for c in track_cols:
            if prev.get(c) != curr.get(c):
                diffs[c] = [prev.get(c), curr.get(c)]
        if diffs:
            out.append({
                "from_run": prev["run_id"], "from_at": prev["captured_at"],
                "to_run": curr["run_id"],   "to_at":   curr["captured_at"],
                "changes": diffs,
            })
    return out


# ── CLI for manual capture / audit ───────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="ticker_snapshots — capture/audit helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_cap = sub.add_parser("capture", help="Capture from infra/prototype/tickers.json")
    p_cap.add_argument("--run-id", default=None)
    p_hist = sub.add_parser("history", help="Show snapshot history for a ticker")
    p_hist.add_argument("ticker")
    p_hist.add_argument("--limit", type=int, default=20)
    p_diff = sub.add_parser("diff", help="Show field-level diffs for a ticker")
    p_diff.add_argument("ticker")
    p_diff.add_argument("--fields", default=None, help="comma-separated field names")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "capture":
        import time as _time
        _t0 = _time.time()
        try:
            tj = json.loads((BASE_DIR / "infra" / "prototype" / "tickers.json").read_text())
            d = json.loads((BASE_DIR / "infra" / "prototype" / "data.json").read_text())
            run_id = args.run_id or d.get("run_timestamp", "").replace(" ", "_")[:16] or None
            n = capture_scan(tj, run_id=run_id)
            print(f"Captured {n} ticker snapshots (run_id={run_id})")
            try:
                from lib.autorun_reporter import report
                report("ticker-snapshots", "success",
                       summary=f"Captured {n} ticker snapshots for run {run_id}",
                       duration_sec=_time.time() - _t0)
            except Exception:
                pass
        except Exception as e:
            try:
                from lib.autorun_reporter import report_failed
                report_failed("ticker-snapshots", str(e), duration_sec=_time.time() - _t0)
            except Exception:
                pass
            raise

    elif args.cmd == "history":
        rows = history_for(args.ticker, limit=args.limit)
        if not rows:
            print(f"No snapshots for {args.ticker}")
        else:
            print(f"{args.ticker} — {len(rows)} snapshots")
            for r in rows:
                print(f"  {r['captured_at']:<19}  {r['run_id']:<17}  verdict={r['verdict']:<6} "
                      f"score={r['score']:<5} stage={r['stage']:<6} setup={r['setup_family']:<22} "
                      f"eq={r['entry_quality']:<10}")

    elif args.cmd == "diff":
        fields = args.fields.split(",") if args.fields else None
        ds = diff(args.ticker, fields=fields)
        if not ds:
            print(f"No diffs for {args.ticker} (need ≥2 snapshots)")
        else:
            print(f"{args.ticker} — {len(ds)} change events")
            for d in ds:
                print(f"\n  {d['from_run']} → {d['to_run']}")
                for f, (prev, curr) in d["changes"].items():
                    print(f"    {f:<16} {prev!r:<24} → {curr!r}")
