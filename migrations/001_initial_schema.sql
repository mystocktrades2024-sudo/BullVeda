-- SwingTrade — Supabase initial schema (2026-05-08)
-- Translates the 18 SQLite tables in db.py to Postgres.
-- Idempotent: uses CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- Paste this entire file into the Supabase SQL Editor and click Run.
--
-- After this lands, run: python3 migrate_sqlite_to_supabase.py
-- to port your existing data/swingtrade.db rows into these tables.

-- =========================================================================
-- meta — schema version + arbitrary key/value
-- =========================================================================
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- =========================================================================
-- portfolio_state — singleton account state
-- =========================================================================
CREATE TABLE IF NOT EXISTS portfolio_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    equity          DOUBLE PRECISION NOT NULL DEFAULT 5000,
    cash            DOUBLE PRECISION NOT NULL DEFAULT 5000,
    margin_reserved DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ
);

-- =========================================================================
-- positions — open positions
-- =========================================================================
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    direction       TEXT NOT NULL DEFAULT 'long',
    entry_date      TIMESTAMPTZ,
    entry_price     DOUBLE PRECISION NOT NULL,
    shares          INTEGER NOT NULL,
    position_size   DOUBLE PRECISION,
    stop            DOUBLE PRECISION,
    trail_stop      DOUBLE PRECISION,
    trail_active    INTEGER DEFAULT 0,
    highest_price   DOUBLE PRECISION,
    current_price   DOUBLE PRECISION,
    target1         DOUBLE PRECISION,
    target2         DOUBLE PRECISION,
    setup_type      TEXT,
    allocation_pct  DOUBLE PRECISION,
    notes           TEXT,
    entry_regime    TEXT,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);

-- =========================================================================
-- closed_trades — historical exits
-- =========================================================================
CREATE TABLE IF NOT EXISTS closed_trades (
    id           BIGSERIAL PRIMARY KEY,
    ticker       TEXT NOT NULL,
    direction    TEXT,
    entry_date   TIMESTAMPTZ,
    exit_date    TIMESTAMPTZ,
    entry_price  DOUBLE PRECISION,
    exit_price   DOUBLE PRECISION,
    shares       INTEGER,
    pnl_dollars  DOUBLE PRECISION,
    pnl_pct      DOUBLE PRECISION,
    win          INTEGER,
    setup_type   TEXT,
    exit_reason  TEXT,
    hold_days    INTEGER,
    mae          DOUBLE PRECISION,
    mfe          DOUBLE PRECISION,
    regime       TEXT,
    raw_json     JSONB
);
CREATE INDEX IF NOT EXISTS idx_closed_ticker ON closed_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_closed_exit   ON closed_trades(exit_date);

-- =========================================================================
-- equity_audit — every change to equity/cash, with reason
-- =========================================================================
CREATE TABLE IF NOT EXISTS equity_audit (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    old_equity  DOUBLE PRECISION,
    new_equity  DOUBLE PRECISION,
    old_cash    DOUBLE PRECISION,
    new_cash    DOUBLE PRECISION,
    invested    DOUBLE PRECISION,
    reason      TEXT
);

-- =========================================================================
-- monthly_pnl — pre-aggregated month-by-month P&L
-- =========================================================================
CREATE TABLE IF NOT EXISTS monthly_pnl (
    year_month TEXT PRIMARY KEY,
    pnl        DOUBLE PRECISION NOT NULL DEFAULT 0
);

-- =========================================================================
-- equity_curve — daily equity snapshots
-- =========================================================================
CREATE TABLE IF NOT EXISTS equity_curve (
    id     BIGSERIAL PRIMARY KEY,
    date   DATE NOT NULL,
    equity DOUBLE PRECISION NOT NULL
);

-- =========================================================================
-- signal_log — every signal issued (canonical journal)
-- =========================================================================
CREATE TABLE IF NOT EXISTS signal_log (
    id              BIGSERIAL PRIMARY KEY,
    date            TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    strategy        TEXT,
    entry_price     DOUBLE PRECISION,
    stop            DOUBLE PRECISION,
    target1         DOUBLE PRECISION,
    target2         DOUBLE PRECISION,
    rr              DOUBLE PRECISION,
    stars           INTEGER,
    score           DOUBLE PRECISION,
    rs_rank         DOUBLE PRECISION,
    direction       TEXT DEFAULT 'long',
    status          TEXT DEFAULT 'OPEN',
    day5_price      DOUBLE PRECISION,
    day10_price     DOUBLE PRECISION,
    actual_pnl_pct  DOUBLE PRECISION,
    result          TEXT,
    mae_pct         DOUBLE PRECISION,
    mfe_pct         DOUBLE PRECISION,
    outcome_5d      TEXT,
    outcome_10d     TEXT,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_signal_date   ON signal_log(date);
CREATE INDEX IF NOT EXISTS idx_signal_ticker ON signal_log(ticker);

-- =========================================================================
-- runs — one row per scan run
-- =========================================================================
CREATE TABLE IF NOT EXISTS runs (
    id        BIGSERIAL PRIMARY KEY,
    run_date  DATE NOT NULL,
    run_time  TIMESTAMPTZ,
    regime    TEXT,
    num_picks INTEGER,
    evaluated INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);

-- =========================================================================
-- picks — every pick from every scan, linked to runs.id
-- =========================================================================
CREATE TABLE IF NOT EXISTS picks (
    id                BIGSERIAL PRIMARY KEY,
    run_id            BIGINT REFERENCES runs(id) ON DELETE CASCADE,
    ticker            TEXT NOT NULL,
    direction         TEXT,
    verdict           TEXT,
    score             DOUBLE PRECISION,
    rs_rank           DOUBLE PRECISION,
    setup_type        TEXT,
    setup_family      TEXT,
    entry_price       DOUBLE PRECISION,
    stop              DOUBLE PRECISION,
    target1           DOUBLE PRECISION,
    target2           DOUBLE PRECISION,
    first_seen_time   TIMESTAMPTZ,
    last_updated_time TIMESTAMPTZ,
    updated_count     INTEGER DEFAULT 1,
    raw_json          JSONB
);
CREATE INDEX IF NOT EXISTS idx_picks_run    ON picks(run_id);
CREATE INDEX IF NOT EXISTS idx_picks_ticker ON picks(ticker);

-- =========================================================================
-- trades — backtest trade ledger (per scan)
-- =========================================================================
CREATE TABLE IF NOT EXISTS trades (
    id                BIGSERIAL PRIMARY KEY,
    run_id            BIGINT REFERENCES runs(id) ON DELETE CASCADE,
    run_date          DATE,
    ticker            TEXT NOT NULL,
    direction         TEXT,
    entry_price       DOUBLE PRECISION,
    exit_price        DOUBLE PRECISION,
    pct_chg           DOUBLE PRECISION,
    win               INTEGER,
    score             DOUBLE PRECISION,
    hold_days         INTEGER,
    setup_family      TEXT,
    regime            TEXT,
    regime4           TEXT,
    catalyst_tier     INTEGER,
    entry_quality     TEXT,
    entry_subtype     TEXT,
    sector            TEXT,
    industry          TEXT,
    conviction_tier   TEXT,
    entry_date        TIMESTAMPTZ,
    exit_date         TIMESTAMPTZ,
    mae               DOUBLE PRECISION,
    mfe               DOUBLE PRECISION,
    raw_json          JSONB
);
CREATE INDEX IF NOT EXISTS idx_trades_ticker   ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_run_date ON trades(run_date);

-- =========================================================================
-- watch_triggers — watchlist alerts that fired
-- =========================================================================
CREATE TABLE IF NOT EXISTS watch_triggers (
    id            BIGSERIAL PRIMARY KEY,
    ticker        TEXT NOT NULL,
    triggered_at  TIMESTAMPTZ,
    run_date      DATE,
    raw_json      JSONB
);
CREATE INDEX IF NOT EXISTS idx_watch_ticker ON watch_triggers(ticker);

-- =========================================================================
-- custom_tickers — user-added tickers
-- =========================================================================
CREATE TABLE IF NOT EXISTS custom_tickers (
    ticker      TEXT PRIMARY KEY,
    entry_price DOUBLE PRECISION,
    entry_date  DATE,
    entry_time  TEXT,
    note        TEXT,
    added_at    TIMESTAMPTZ,
    source      TEXT DEFAULT 'CUSTOM',
    raw_json    JSONB
);

-- =========================================================================
-- alert_log — dedup keys for sent alerts
-- =========================================================================
CREATE TABLE IF NOT EXISTS alert_log (
    alert_key       TEXT PRIMARY KEY,
    last_sent_date  DATE NOT NULL
);

-- =========================================================================
-- scan_health — per-scan health stats
-- =========================================================================
CREATE TABLE IF NOT EXISTS scan_health (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL,
    total     INTEGER,
    killed    INTEGER,
    pct       DOUBLE PRECISION,
    raw_json  JSONB
);

-- =========================================================================
-- gap_events — overnight gap events + actions taken
-- =========================================================================
CREATE TABLE IF NOT EXISTS gap_events (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    ticker      TEXT NOT NULL,
    prev_close  DOUBLE PRECISION,
    open_price  DOUBLE PRECISION,
    gap_pct     DOUBLE PRECISION,
    direction   TEXT,
    severity    TEXT,
    action      TEXT,
    new_stop    DOUBLE PRECISION,
    raw_json    JSONB
);
CREATE INDEX IF NOT EXISTS idx_gap_ticker ON gap_events(ticker);

-- =========================================================================
-- paper_trading_config — singleton paper-trading state
-- =========================================================================
CREATE TABLE IF NOT EXISTS paper_trading_config (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    start_date          DATE,
    duration_days       INTEGER,
    enabled             INTEGER DEFAULT 0,
    disabled_at         TIMESTAMPTZ,
    direction_filter    TEXT DEFAULT 'buy_only',
    max_daily_trades    INTEGER DEFAULT 4
);

-- =========================================================================
-- Row-Level Security: OFF for now (single-user system).
-- Phase 4 will add policies when multi-user support lands.
-- =========================================================================
-- To enable later:
-- ALTER TABLE positions       ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY positions_owner_rw ON positions
--   FOR ALL USING (auth.uid() = owner_id) WITH CHECK (auth.uid() = owner_id);
-- (requires adding owner_id UUID column referencing auth.users)

-- Mark schema version
INSERT INTO meta (key, value) VALUES ('schema_version', '001')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
