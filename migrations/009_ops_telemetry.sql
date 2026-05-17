-- SwingTrade — migration 009: ops telemetry + Postgres optimizations (2026-05-17)
--
-- Adds operational visibility tables, JSONB GIN indexes for raw_json columns,
-- materialized views for hot-path analytics, and equity_audit trigger.

-- =========================================================================
-- eodhd_quota_usage: daily quota consumption per data type
-- =========================================================================
CREATE TABLE IF NOT EXISTS eodhd_quota_usage (
    id              BIGSERIAL PRIMARY KEY,
    bucket_date     DATE NOT NULL,
    endpoint        TEXT NOT NULL,              -- 'eod' / 'fundamentals' / 'options' / 'news' / 'snapshot'
    request_count   INTEGER NOT NULL DEFAULT 0,
    cost_units      INTEGER NOT NULL DEFAULT 0, -- some endpoints cost > 1 unit
    quota_remaining INTEGER,                    -- snapshot at end of day
    rate_limit_hits INTEGER DEFAULT 0,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_bucket ON eodhd_quota_usage(bucket_date, endpoint);

-- =========================================================================
-- launchd_runs: every plist firing with success/failure/duration
-- =========================================================================
CREATE TABLE IF NOT EXISTS launchd_runs (
    id              BIGSERIAL PRIMARY KEY,
    plist_label     TEXT NOT NULL,              -- 'com.swingtrade.morning-briefing' / etc
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    duration_s      DOUBLE PRECISION,
    exit_code       INTEGER,
    success         BOOLEAN,
    stdout_tail     TEXT,                       -- last 2000 chars
    stderr_tail     TEXT,
    host            TEXT DEFAULT 'mac-local',
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_launchd_label_ts ON launchd_runs(plist_label, started_at DESC);

-- =========================================================================
-- data_quality_checks: daily assertions (NULL counts, freshness, ranges)
-- =========================================================================
CREATE TABLE IF NOT EXISTS data_quality_checks (
    id              BIGSERIAL PRIMARY KEY,
    checked_at      TIMESTAMPTZ NOT NULL,
    table_name      TEXT NOT NULL,
    check_name      TEXT NOT NULL,              -- 'null_count' / 'freshness' / 'range_check' / 'duplicate_count'
    passed          BOOLEAN NOT NULL,
    metric_value    DOUBLE PRECISION,
    threshold       DOUBLE PRECISION,
    n_rows_affected INTEGER,
    details         TEXT,
    severity        TEXT DEFAULT 'info',        -- 'critical' / 'warning' / 'info'
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_dq_ts          ON data_quality_checks(checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_dq_failed      ON data_quality_checks(passed, severity) WHERE passed = false;

-- =========================================================================
-- config_history: every config.json change tied to git commit
-- =========================================================================
CREATE TABLE IF NOT EXISTS config_history (
    id              BIGSERIAL PRIMARY KEY,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    git_commit      TEXT,
    author          TEXT,
    config_path     TEXT NOT NULL,              -- 'config/config.json' / 'config/variants/A1.json' / etc
    config_after    JSONB NOT NULL,
    config_diff     JSONB,                      -- jsondiffpatch-style delta
    note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_config_hist_ts ON config_history(changed_at DESC);

-- =========================================================================
-- feature_flag_changes: when each _enabled flag flipped
-- =========================================================================
CREATE TABLE IF NOT EXISTS feature_flag_changes (
    id              BIGSERIAL PRIMARY KEY,
    flipped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flag_path       TEXT NOT NULL,              -- e.g. 'tier1_signals.apply_to_score'
    old_value       JSONB,
    new_value       JSONB,
    git_commit      TEXT,
    note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_flag_ts ON feature_flag_changes(flipped_at DESC);

-- =========================================================================
-- api_latency_metrics: per-endpoint p50/p95/p99 latency
-- =========================================================================
CREATE TABLE IF NOT EXISTS api_latency_metrics (
    id              BIGSERIAL PRIMARY KEY,
    bucket_minute   TIMESTAMPTZ NOT NULL,
    endpoint        TEXT NOT NULL,              -- '/api/portfolio' / '/v2/trade_engine' / etc
    method          TEXT NOT NULL DEFAULT 'GET',
    request_count   INTEGER,
    error_count     INTEGER DEFAULT 0,
    p50_ms          DOUBLE PRECISION,
    p95_ms          DOUBLE PRECISION,
    p99_ms          DOUBLE PRECISION,
    avg_ms          DOUBLE PRECISION,
    max_ms          DOUBLE PRECISION
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_api_lat_bucket ON api_latency_metrics(bucket_minute, endpoint, method);

-- =========================================================================
-- user_audit_log: who did what when (currently exists as JSONL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS user_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    happened_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         TEXT,                       -- 'gari' / 'admin' / 'system'
    action          TEXT NOT NULL,              -- 'login' / 'add_position' / 'close_position' / 'edit_config'
    target_type     TEXT,
    target_id       TEXT,
    ip_address      TEXT,
    user_agent      TEXT,
    payload         JSONB,
    sync_key        TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_uaudit_ts   ON user_audit_log(happened_at DESC);
CREATE INDEX IF NOT EXISTS idx_uaudit_user ON user_audit_log(user_id, happened_at DESC);

-- =========================================================================
-- JSONB GIN indexes — query raw_json fast
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_signal_log_raw_gin     ON signal_log     USING GIN (raw_json);
CREATE INDEX IF NOT EXISTS idx_positions_raw_gin      ON positions      USING GIN (raw_json);
CREATE INDEX IF NOT EXISTS idx_closed_trades_raw_gin  ON closed_trades  USING GIN (raw_json);
CREATE INDEX IF NOT EXISTS idx_picks_raw_gin          ON picks          USING GIN (raw_json);
CREATE INDEX IF NOT EXISTS idx_trades_raw_gin         ON trades         USING GIN (raw_json);
CREATE INDEX IF NOT EXISTS idx_decision_log_raw_gin   ON decision_log   USING GIN (raw_json);

-- =========================================================================
-- equity_audit trigger: auto-write on portfolio_state UPDATE
-- =========================================================================
CREATE OR REPLACE FUNCTION trg_equity_audit() RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.equity IS DISTINCT FROM NEW.equity)
       OR (OLD.cash IS DISTINCT FROM NEW.cash) THEN
        INSERT INTO equity_audit (timestamp, old_equity, new_equity, old_cash, new_cash, invested, reason)
        VALUES (NOW(), OLD.equity, NEW.equity, OLD.cash, NEW.cash,
                COALESCE(NEW.equity - NEW.cash, 0),
                'auto-trigger on portfolio_state UPDATE');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS portfolio_state_audit ON portfolio_state;
CREATE TRIGGER portfolio_state_audit
    AFTER UPDATE ON portfolio_state
    FOR EACH ROW EXECUTE FUNCTION trg_equity_audit();

-- =========================================================================
-- Materialized views — hot-path analytics, refreshed nightly
-- =========================================================================
DROP MATERIALIZED VIEW IF EXISTS mv_setup_x_regime_grid;
CREATE MATERIALIZED VIEW mv_setup_x_regime_grid AS
WITH banded AS (
    SELECT
        COALESCE(setup_family, 'unknown')   AS setup_family,
        COALESCE(regime_at_entry, 'all')    AS regime,
        CASE
            WHEN score >= 90 THEN '90-100'
            WHEN score >= 80 THEN '80-89'
            WHEN score >= 70 THEN '70-79'
            WHEN score >= 60 THEN '60-69'
            ELSE '<60'
        END                                  AS score_band,
        COALESCE(entry_quality, 'unknown')  AS entry_quality,
        result, actual_pnl_pct, r_multiple, mae_pct, mfe_pct, date
    FROM signal_log
    WHERE status = 'CLOSED' AND result IS NOT NULL
)
SELECT
    setup_family,
    regime,
    score_band,
    entry_quality,
    COUNT(*)                            AS n_trades,
    SUM(CASE WHEN result LIKE 'WIN%' THEN 1 ELSE 0 END) AS n_wins,
    AVG(CASE WHEN result LIKE 'WIN%' THEN 1.0 ELSE 0.0 END) AS wr,
    AVG(actual_pnl_pct)                 AS avg_pnl_pct,
    AVG(r_multiple)                     AS avg_r_multiple,
    AVG(mae_pct)                        AS avg_mae,
    AVG(mfe_pct)                        AS avg_mfe,
    MAX(date)                           AS last_trade_at
FROM banded
GROUP BY setup_family, regime, score_band, entry_quality;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_setup_grid
    ON mv_setup_x_regime_grid(setup_family, regime, score_band, entry_quality);

DROP MATERIALIZED VIEW IF EXISTS mv_monthly_pnl_by_setup;
CREATE MATERIALIZED VIEW mv_monthly_pnl_by_setup AS
SELECT
    to_char(exit_date, 'YYYY-MM')      AS year_month,
    COALESCE(setup_family, setup_type, 'unknown') AS setup,
    COUNT(*)                           AS n_trades,
    SUM(CASE WHEN win::text IN ('1','true','t') THEN 1 ELSE 0 END) AS n_wins,
    AVG(CASE WHEN win::text IN ('1','true','t') THEN 1.0 ELSE 0.0 END) AS wr,
    SUM(pnl_dollars)                   AS total_pnl,
    AVG(pnl_pct)                       AS avg_pnl_pct,
    AVG(r_multiple)                    AS avg_r_multiple
FROM closed_trades
WHERE exit_date IS NOT NULL
GROUP BY year_month, setup;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_monthly_setup
    ON mv_monthly_pnl_by_setup(year_month, setup);

INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('009'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
