-- SwingTrade — backtest results storage (2026-05-08, migration 002)
--
-- Why: every backtest run prints to stdout and vanishes. No historical record,
-- no drift detection, no audit trail. Three new tables fix this:
--   - backtest_runs       (one row per backtest invocation)
--   - backtest_trades     (every simulated trade)
--   - walk_forward_folds  (per-fold metadata for WF runs)

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL UNIQUE,            -- hash or timestamp-based identifier
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    mode            TEXT NOT NULL,                   -- 'portfolio' | 'signal' | 'walk_forward'
    days            INTEGER NOT NULL,                -- backtest window length
    end_date        DATE,                            -- backtest end (default today)
    min_score       INTEGER,
    min_rs          INTEGER,
    -- Summary metrics (NULL until finished)
    n_trades        INTEGER,
    wr_raw          DOUBLE PRECISION,                -- raw win rate (0-1)
    wr_adj          DOUBLE PRECISION,                -- post survivorship-haircut win rate
    profit_factor   DOUBLE PRECISION,
    sharpe          DOUBLE PRECISION,
    max_drawdown    DOUBLE PRECISION,                -- as decimal, e.g. 0.18 = 18%
    total_pnl       DOUBLE PRECISION,
    starting_equity DOUBLE PRECISION,
    final_equity    DOUBLE PRECISION,
    total_return    DOUBLE PRECISION,                -- as decimal
    -- Provenance
    config_snapshot JSONB,                            -- full config.json at run-time
    git_commit      TEXT,                             -- commit hash (if available)
    notes           TEXT,
    raw_stdout      TEXT                              -- complete stdout for debugging
);
CREATE INDEX IF NOT EXISTS idx_btr_started ON backtest_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_btr_mode    ON backtest_runs(mode);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    direction       TEXT NOT NULL DEFAULT 'long',
    entry_date      DATE,
    exit_date       DATE,
    entry_price     DOUBLE PRECISION,
    exit_price      DOUBLE PRECISION,
    shares          INTEGER,
    pnl_dollars     DOUBLE PRECISION,
    pnl_pct         DOUBLE PRECISION,
    win             INTEGER,
    setup_family    TEXT,
    setup_type      TEXT,
    score           INTEGER,
    rs_rank         DOUBLE PRECISION,
    regime          TEXT,
    exit_reason     TEXT,
    hold_days       INTEGER,
    mae_pct         DOUBLE PRECISION,
    mfe_pct         DOUBLE PRECISION,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_btt_run    ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_btt_ticker ON backtest_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_btt_setup  ON backtest_trades(setup_family);

CREATE TABLE IF NOT EXISTS walk_forward_folds (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
    fold_index      INTEGER NOT NULL,
    train_start     DATE,
    train_end       DATE,
    test_start      DATE,
    test_end        DATE,
    -- Tuned params (output of tune_on_train)
    tuned_min_score INTEGER,
    tuned_min_rs    INTEGER,
    tuned_extras    JSONB,            -- any future grid-tuned params (multipliers, weights)
    -- Test-fold metrics (validates the tuned params)
    test_n_trades   INTEGER,
    test_wr         DOUBLE PRECISION,
    test_pf         DOUBLE PRECISION,
    test_sharpe     DOUBLE PRECISION,
    test_max_dd     DOUBLE PRECISION,
    train_n_trades  INTEGER,
    train_wr        DOUBLE PRECISION,
    train_pf        DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_wff_run ON walk_forward_folds(run_id);

-- Mark schema 002
INSERT INTO meta (key, value) VALUES ('schema_version', '002')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
