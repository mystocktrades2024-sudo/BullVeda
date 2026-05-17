-- SwingTrade — schema alignment with db.py (2026-05-17, migration 004)
--
-- Why: 001 was applied to Supabase in 2026-05-08 but db.py has evolved since.
-- The migrate_sqlite_to_supabase.py push fails because Supabase tables are
-- missing columns added later in db.py (raw_json, date, source, alert_key,
-- killed, action) and paper_trading_config doesn't exist at all.
--
-- Idempotent: every change wrapped in IF NOT EXISTS / IF EXISTS guards.

-- positions: add raw_json
ALTER TABLE positions ADD COLUMN IF NOT EXISTS raw_json JSONB;

-- closed_trades: add raw_json (just in case)
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS raw_json JSONB;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS mae DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS mfe DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS regime TEXT;

-- equity_curve: ensure date + equity columns
ALTER TABLE equity_curve ADD COLUMN IF NOT EXISTS date DATE;
ALTER TABLE equity_curve ADD COLUMN IF NOT EXISTS equity DOUBLE PRECISION;

-- signal_log: ensure all expected columns exist
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS date           TIMESTAMPTZ;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS strategy       TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS entry_price    DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS stop           DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS target1        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS target2        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS rr             DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS stars          INTEGER;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS score          DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS rs_rank        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS direction      TEXT DEFAULT 'long';
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS status         TEXT DEFAULT 'OPEN';
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS day5_price     DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS day10_price    DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS actual_pnl_pct DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS result         TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS mae_pct        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS mfe_pct        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS outcome_5d     TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS outcome_10d    TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS raw_json       JSONB;

-- custom_tickers: source + raw_json
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS source   TEXT DEFAULT 'CUSTOM';
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS raw_json JSONB;
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ;
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS note     TEXT;
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS entry_time TEXT;

-- alert_log: ensure alert_key + last_sent_date schema (recreate if shape wrong)
-- If the table exists with the wrong PK, the safest move is ADD COLUMN
-- and then a unique index. Drop-and-recreate is too destructive.
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS alert_key      TEXT;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS last_sent_date DATE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_log_alert_key ON alert_log(alert_key);

-- scan_health: ts + killed + pct + raw_json
ALTER TABLE scan_health ADD COLUMN IF NOT EXISTS ts       TIMESTAMPTZ;
ALTER TABLE scan_health ADD COLUMN IF NOT EXISTS total    INTEGER;
ALTER TABLE scan_health ADD COLUMN IF NOT EXISTS killed   INTEGER;
ALTER TABLE scan_health ADD COLUMN IF NOT EXISTS pct      DOUBLE PRECISION;
ALTER TABLE scan_health ADD COLUMN IF NOT EXISTS raw_json JSONB;

-- gap_events: full column set
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS ts         TIMESTAMPTZ;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS ticker     TEXT;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS prev_close DOUBLE PRECISION;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS open_price DOUBLE PRECISION;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS gap_pct    DOUBLE PRECISION;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS direction  TEXT;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS severity   TEXT;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS action     TEXT;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS new_stop   DOUBLE PRECISION;
ALTER TABLE gap_events ADD COLUMN IF NOT EXISTS raw_json   JSONB;

-- paper_trading_config: full table (was missing entirely)
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
-- supabase_sync_state: per-table sync ledger (NEW for status dashboard)
-- =========================================================================
CREATE TABLE IF NOT EXISTS supabase_sync_state (
    table_name      TEXT PRIMARY KEY,
    last_sync_at    TIMESTAMPTZ,
    source_rows     INTEGER DEFAULT 0,
    pushed          INTEGER DEFAULT 0,
    failed          INTEGER DEFAULT 0,
    error_msg       TEXT,
    duration_ms     INTEGER
);

-- Mark schema 004 (meta.value is JSONB in Supabase, so cast)
INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('004'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
