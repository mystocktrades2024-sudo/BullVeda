-- SwingTrade — migration 005: schema completeness (2026-05-17)
--
-- Adds: missing picks + trades tables; typed columns extracted from raw_json;
-- sync_key column on insert-only tables (fixes duplicate-on-resync bug);
-- created_at/updated_at audit columns on mutation tables.
--
-- Idempotent.

-- =========================================================================
-- picks: per-pick rows per scan run (was missing entirely in Supabase)
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
    sync_key          TEXT UNIQUE,
    raw_json          JSONB
);
CREATE INDEX IF NOT EXISTS idx_picks_run    ON picks(run_id);
CREATE INDEX IF NOT EXISTS idx_picks_ticker ON picks(ticker);

-- =========================================================================
-- trades: simulated/backtest trades per scan (was missing entirely)
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
    sync_key          TEXT UNIQUE,
    raw_json          JSONB
);
CREATE INDEX IF NOT EXISTS idx_trades_ticker   ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_run_date ON trades(run_date);

-- =========================================================================
-- Add sync_key (deterministic row-hash) to insert-only tables to dedup re-runs
-- =========================================================================
ALTER TABLE signal_log      ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE positions       ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE closed_trades   ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE equity_audit    ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE equity_curve    ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE runs            ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE watch_triggers  ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE scan_health     ADD COLUMN IF NOT EXISTS sync_key TEXT;
ALTER TABLE gap_events      ADD COLUMN IF NOT EXISTS sync_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_log_sync     ON signal_log(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_sync      ON positions(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_closed_trades_sync  ON closed_trades(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_equity_audit_sync   ON equity_audit(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_equity_curve_sync   ON equity_curve(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_sync           ON runs(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_watch_triggers_sync ON watch_triggers(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_scan_health_sync    ON scan_health(sync_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gap_events_sync     ON gap_events(sync_key);

-- =========================================================================
-- signal_log: extract analytical columns from raw_json
-- =========================================================================
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS entry_quality     TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS catalyst_tier     INTEGER;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS conviction_tier   TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS score_band        TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS setup_family      TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS gates_passed      JSONB;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS gates_failed      JSONB;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS wilson_lb_at_entry DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS expected_wr       DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS expected_pf       DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS kelly_mult        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS vix_at_entry      DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS regime_at_entry   TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS sector_rs_at_entry DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS sector            TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS industry          TEXT;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS expected_hold_days INTEGER;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS actual_hold_days  INTEGER;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS exit_price        DOUBLE PRECISION;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS mae_date          DATE;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS mfe_date          DATE;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS breakeven_stop_hit BOOLEAN;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS trailed           BOOLEAN;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS partial_taken     BOOLEAN;
ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS r_multiple        DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_signal_setup_family ON signal_log(setup_family);
CREATE INDEX IF NOT EXISTS idx_signal_regime       ON signal_log(regime_at_entry);
CREATE INDEX IF NOT EXISTS idx_signal_conviction   ON signal_log(conviction_tier);

-- =========================================================================
-- closed_trades: per-trade calibration columns
-- =========================================================================
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS score_at_entry   DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS rs_rank_at_entry DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS regime_at_entry  TEXT;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS catalyst_tier    INTEGER;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS conviction_tier  TEXT;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS entry_quality    TEXT;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS setup_family     TEXT;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS sector           TEXT;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS r_multiple       DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS slippage_entry_pct DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS slippage_exit_pct  DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS commission_dollars DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS borrow_fee_dollars DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS time_in_loss_pct   DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS time_to_breakeven_days INTEGER;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS time_to_target1_days   INTEGER;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS max_dd_during_hold_pct DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS max_gap_overnight_pct  DOUBLE PRECISION;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS earnings_during_hold   BOOLEAN;
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS news_events_during_hold INTEGER;

CREATE INDEX IF NOT EXISTS idx_closed_setup_family ON closed_trades(setup_family);
CREATE INDEX IF NOT EXISTS idx_closed_regime       ON closed_trades(regime);

-- =========================================================================
-- positions: live risk telemetry columns
-- =========================================================================
ALTER TABLE positions ADD COLUMN IF NOT EXISTS risk_dollars             DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS risk_pct_of_portfolio    DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS correlation_to_portfolio DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS beta_to_spy              DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sector_concentration_pct DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS days_held                INTEGER;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS expected_target_date     DATE;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS unrealized_pnl_high      DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS unrealized_pnl_low       DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS wilson_lb_at_entry       DOUBLE PRECISION;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sector                   TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS industry                 TEXT;

-- =========================================================================
-- backtest_runs: institutional metrics
-- =========================================================================
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS calmar_ratio        DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS sortino_ratio       DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS omega_ratio         DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS var_95              DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS cvar_95             DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS downside_deviation  DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS mar_ratio           DOUBLE PRECISION;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS recovery_time_avg_days INTEGER;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS consecutive_losses_max INTEGER;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS monte_carlo_summary JSONB;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS regime_breakdown    JSONB;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS setup_breakdown     JSONB;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS equity_curve_array  JSONB;

-- =========================================================================
-- runs: scan telemetry columns
-- =========================================================================
ALTER TABLE runs ADD COLUMN IF NOT EXISTS scan_duration_s     DOUBLE PRECISION;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS data_fill_rate      DOUBLE PRECISION;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS eodhd_quota_used    INTEGER;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tickers_evaluated   INTEGER;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tickers_killed      INTEGER;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tickers_passed_gates INTEGER;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS git_commit          TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS config_hash         TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS regime_at_open      TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS regime_at_close     TEXT;

-- =========================================================================
-- created_at / updated_at on mutation tables
-- =========================================================================
ALTER TABLE positions     ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE positions     ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE closed_trades ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE custom_tickers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('005'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
