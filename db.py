"""SwingTrade SQLite data layer.

Replaces JSON state files with a transactional SQLite store. Stdlib only
(sqlite3 / pathlib / json / logging). The database lives at
``data/swingtrade.db``. WAL mode is enabled for concurrent read/write
safety (scanner + portfolio tracker + executor can all run simultaneously).

Design notes
------------
- Single shared connection per process, ``check_same_thread=False`` so
  the executor's helper threads can use the same handle.
- ``isolation_level=None`` lets us manage transactions explicitly via the
  ``transaction()`` context manager.
- Every row-shaped table that may receive "extra" fields (positions,
  closed_trades, signal_log, picks) has a ``raw_json`` column. The
  canonical columns are first-class, but we preserve the original
  payload for debugging and forward-compat.
- Schema is idempotent (``CREATE TABLE IF NOT EXISTS``) so ``init_schema``
  is safe to call on every startup.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

log = logging.getLogger("db")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "swingtrade.db"
SCHEMA_VERSION = 1

# ── Schema ──────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    equity REAL NOT NULL DEFAULT 5000,
    cash REAL NOT NULL DEFAULT 5000,
    margin_reserved REAL NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'long',
    entry_date TEXT,
    entry_price REAL NOT NULL,
    shares INTEGER NOT NULL,
    position_size REAL,
    stop REAL,
    trail_stop REAL,
    trail_active INTEGER DEFAULT 0,
    highest_price REAL,
    current_price REAL,
    target1 REAL,
    target2 REAL,
    setup_type TEXT,
    allocation_pct REAL,
    notes TEXT,
    entry_regime TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);

CREATE TABLE IF NOT EXISTS closed_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    direction TEXT,
    entry_date TEXT,
    exit_date TEXT,
    entry_price REAL,
    exit_price REAL,
    shares INTEGER,
    pnl_dollars REAL,
    pnl_pct REAL,
    win INTEGER,
    setup_type TEXT,
    exit_reason TEXT,
    hold_days INTEGER,
    mae REAL,
    mfe REAL,
    regime TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_closed_ticker ON closed_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_closed_exit ON closed_trades(exit_date);

CREATE TABLE IF NOT EXISTS equity_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    old_equity REAL,
    new_equity REAL,
    old_cash REAL,
    new_cash REAL,
    invested REAL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS monthly_pnl (
    year_month TEXT PRIMARY KEY,
    pnl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    equity REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    strategy TEXT,
    entry_price REAL,
    stop REAL,
    target1 REAL,
    target2 REAL,
    rr REAL,
    stars INTEGER,
    score REAL,
    rs_rank REAL,
    direction TEXT DEFAULT 'long',
    status TEXT DEFAULT 'OPEN',
    day5_price REAL,
    day10_price REAL,
    actual_pnl_pct REAL,
    result TEXT,
    mae_pct REAL,
    mfe_pct REAL,
    outcome_5d TEXT,
    outcome_10d TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_signal_date ON signal_log(date);
CREATE INDEX IF NOT EXISTS idx_signal_ticker ON signal_log(ticker);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    run_time TEXT,
    regime TEXT,
    num_picks INTEGER,
    evaluated INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);

CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    ticker TEXT NOT NULL,
    direction TEXT,
    verdict TEXT,
    score REAL,
    rs_rank REAL,
    setup_type TEXT,
    setup_family TEXT,
    entry_price REAL,
    stop REAL,
    target1 REAL,
    target2 REAL,
    first_seen_time TEXT,
    last_updated_time TEXT,
    updated_count INTEGER DEFAULT 1,
    raw_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_picks_run ON picks(run_id);
CREATE INDEX IF NOT EXISTS idx_picks_ticker ON picks(ticker);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    run_date TEXT,
    ticker TEXT NOT NULL,
    direction TEXT,
    entry_price REAL,
    exit_price REAL,
    pct_chg REAL,
    win INTEGER,
    score REAL,
    hold_days INTEGER,
    setup_family TEXT,
    regime TEXT,
    regime4 TEXT,
    catalyst_tier INTEGER,
    entry_quality TEXT,
    entry_subtype TEXT,
    sector TEXT,
    industry TEXT,
    conviction_tier TEXT,
    entry_date TEXT,
    exit_date TEXT,
    mae REAL,
    mfe REAL,
    raw_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_run_date ON trades(run_date);

CREATE TABLE IF NOT EXISTS watch_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    triggered_at TEXT,
    run_date TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch_ticker ON watch_triggers(ticker);

CREATE TABLE IF NOT EXISTS custom_tickers (
    ticker TEXT PRIMARY KEY,
    entry_price REAL,
    entry_date TEXT,
    entry_time TEXT,
    note TEXT,
    added_at TEXT,
    source TEXT DEFAULT 'CUSTOM',
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS alert_log (
    alert_key TEXT PRIMARY KEY,
    last_sent_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    total INTEGER,
    killed INTEGER,
    pct REAL,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS gap_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    prev_close REAL,
    open_price REAL,
    gap_pct REAL,
    direction TEXT,
    severity TEXT,
    action TEXT,
    new_stop REAL,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_gap_ticker ON gap_events(ticker);

CREATE TABLE IF NOT EXISTS paper_trading_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    start_date TEXT,
    duration_days INTEGER,
    enabled INTEGER DEFAULT 0,
    disabled_at TEXT,
    direction_filter TEXT DEFAULT 'buy_only',
    max_daily_trades INTEGER DEFAULT 4
);

-- HTML snapshot archive (2026-05-14): store dashboard.html and other
-- key HTML outputs per scan for easy retrieval.
-- Compressed via zlib when content > 100KB; gzipped flag in `meta`.
CREATE TABLE IF NOT EXISTS html_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                 -- ISO timestamp at save
    kind TEXT NOT NULL,                -- 'dashboard' | 'pead' | 'sleeve_radar' | other
    label TEXT,                        -- 'dashboard 2026-05-14' or similar
    size_bytes INTEGER,                -- pre-compression size
    compressed INTEGER DEFAULT 0,      -- 1 = zlib-compressed
    html_blob BLOB NOT NULL,           -- HTML content (compressed if compressed=1)
    meta_json TEXT                     -- optional JSON metadata
);
CREATE INDEX IF NOT EXISTS idx_html_snapshots_kind_ts ON html_snapshots(kind, ts);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        # WAL can fail on some network filesystems — fall back silently.
        pass
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


_CONN: sqlite3.Connection | None = None
_CONN_PATH: Path | None = None


def get_conn() -> sqlite3.Connection:
    """Return the process-wide connection, opening/initialising if needed.

    Re-opens if DB_PATH has been reassigned (useful in tests that point the
    path at a temp file via monkeypatch).
    """
    global _CONN, _CONN_PATH
    if _CONN is None or _CONN_PATH != DB_PATH:
        if _CONN is not None:
            try:
                _CONN.close()
            except Exception:
                pass
        _CONN = _connect(DB_PATH)
        _CONN_PATH = DB_PATH
        init_schema(_CONN)
    return _CONN


def _add_breakdown_columns(conn: sqlite3.Connection) -> None:
    """Audit ranking flaw #16/#17: per-pillar breakdown columns for
    closed_trades and signal_log. Uses ALTER TABLE ADD COLUMN which is
    not idempotent in SQLite, so each ALTER is wrapped in try/except —
    re-running init_schema is safe.
    """
    cols = [
        ("tech_score",    "REAL"),
        ("cat_score",     "REAL"),
        ("rs_score",      "REAL"),
        ("sm_score",      "REAL"),
        ("qg_score",      "REAL"),
        ("raw_total",     "REAL"),
        ("wr_multiplier", "REAL"),
        ("bonus_total",   "REAL"),
    ]
    for table in ("closed_trades", "signal_log", "trades"):
        for col_name, col_type in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                # Column already exists — idempotent no-op
                pass
            except Exception as e:
                log.debug(f"_add_breakdown_columns: {table}.{col_name}: {e}")


def init_schema(conn: sqlite3.Connection | None = None) -> None:
    conn = conn or get_conn()
    conn.executescript(SCHEMA_SQL)
    # Audit ranking flaw #16/#17: idempotent per-pillar column migration
    _add_breakdown_columns(conn)
    # Seed portfolio_state singleton row if absent.
    cur = conn.execute("SELECT COUNT(*) FROM portfolio_state WHERE id=1")
    if cur.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO portfolio_state (id, equity, cash, margin_reserved, updated_at) "
            "VALUES (1, 5000, 5000, 0, ?)",
            (datetime.now().isoformat(),),
        )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )


@contextmanager
def transaction():
    """Explicit BEGIN/COMMIT/ROLLBACK wrapper."""
    conn = get_conn()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


# ── Column introspection helpers ────────────────────────────────────────

def table_columns(table: str) -> list[str]:
    conn = get_conn()
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r["name"] for r in cur.fetchall()]


def split_known_extras(d: dict, known_cols: set[str]) -> tuple[dict, dict]:
    """Split a dict into (canonical-column-values, extras-for-raw_json)."""
    main = {k: v for k, v in d.items() if k in known_cols}
    extras = {k: v for k, v in d.items() if k not in known_cols}
    return main, extras


def row_to_dict_with_extras(row: sqlite3.Row) -> dict:
    """Convert a Row into a dict, merging any stored raw_json extras."""
    if row is None:
        return {}
    d = dict(row)
    raw = d.pop("raw_json", None)
    if raw:
        try:
            extras = json.loads(raw)
            if isinstance(extras, dict):
                # Canonical columns win over raw_json fallback.
                for k, v in extras.items():
                    d.setdefault(k, v)
        except (json.JSONDecodeError, TypeError):
            pass
    # Drop internal auto-id for the "dict like the old JSON" callers.
    d.pop("id", None)
    return d


# ── HTML snapshot helpers (2026-05-14) ──────────────────────────────────────

def save_html_snapshot(kind: str, html_content: str, label: str | None = None,
                       meta: dict | None = None) -> int:
    """Save an HTML snapshot to the html_snapshots table.

    kind:    'dashboard' | 'pead' | 'sleeve_radar' | other
    label:   optional display name; defaults to '<kind> <timestamp>'
    meta:    optional JSON metadata (any dict)

    Returns the inserted row's id. Compresses with zlib if content > 100KB.
    """
    import zlib
    from datetime import datetime

    if not html_content:
        return -1

    size_bytes = len(html_content.encode("utf-8"))
    compressed = 0
    blob = html_content.encode("utf-8")
    if size_bytes > 100_000:
        blob = zlib.compress(blob, level=6)
        compressed = 1

    ts = datetime.now().isoformat(timespec="seconds")
    if not label:
        label = f"{kind} {ts}"

    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO html_snapshots (ts, kind, label, size_bytes, compressed, html_blob, meta_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ts, kind, label, size_bytes, compressed, blob,
         json.dumps(meta) if meta else None)
    )
    return cur.lastrowid or -1


def load_html_snapshot(snapshot_id: int) -> str | None:
    """Load HTML by snapshot id. Returns the decompressed HTML string or None."""
    import zlib
    conn = get_conn()
    row = conn.execute(
        "SELECT html_blob, compressed FROM html_snapshots WHERE id = ?",
        (snapshot_id,)
    ).fetchone()
    if not row:
        return None
    blob = row["html_blob"]
    compressed = bool(row["compressed"])
    if compressed:
        blob = zlib.decompress(blob)
    return blob.decode("utf-8")


def list_html_snapshots(kind: str | None = None, limit: int = 50) -> list[dict]:
    """List snapshots (most recent first). Returns metadata only, not the blob."""
    conn = get_conn()
    q = """SELECT id, ts, kind, label, size_bytes, compressed, meta_json
           FROM html_snapshots"""
    params: tuple = ()
    if kind:
        q += " WHERE kind = ?"
        params = (kind,)
    q += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("meta_json"):
            try:
                d["meta"] = json.loads(d["meta_json"])
            except Exception:
                pass
            d.pop("meta_json", None)
        out.append(d)
    return out


def prune_html_snapshots(keep_last_n: int = 200) -> int:
    """Keep only the most recent N snapshots. Returns count deleted."""
    conn = get_conn()
    n_rows = conn.execute("SELECT COUNT(*) AS n FROM html_snapshots").fetchone()["n"]
    if n_rows <= keep_last_n:
        return 0
    to_delete = n_rows - keep_last_n
    conn.execute(
        """DELETE FROM html_snapshots WHERE id IN (
           SELECT id FROM html_snapshots ORDER BY id ASC LIMIT ?
        )""", (to_delete,)
    )
    return to_delete
