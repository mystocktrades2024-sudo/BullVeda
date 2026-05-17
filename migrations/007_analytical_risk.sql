-- SwingTrade — migration 007: analytical / risk schemas (2026-05-17)
--
-- Adds the tables required for institutional risk management, model lifecycle
-- tracking, and per-sub-strategy attribution. All schemas; population is via
-- daily/scan-time writes once the analytics layer is wired.

-- =========================================================================
-- position_risk_snapshot: per-position VaR/CVaR/beta/sector daily
-- =========================================================================
CREATE TABLE IF NOT EXISTS position_risk_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_at     TIMESTAMPTZ NOT NULL,
    position_id     BIGINT,                     -- soft FK to positions.id
    ticker          TEXT NOT NULL,
    market_value    DOUBLE PRECISION,
    notional_pct_portfolio DOUBLE PRECISION,
    risk_dollars    DOUBLE PRECISION,           -- (entry - stop) × shares
    risk_pct_portfolio DOUBLE PRECISION,
    var_95_1d       DOUBLE PRECISION,           -- 1-day 95% Value-at-Risk
    cvar_95_1d      DOUBLE PRECISION,           -- expected loss beyond VaR
    var_99_1d       DOUBLE PRECISION,
    beta_to_spy     DOUBLE PRECISION,
    correlation_to_portfolio DOUBLE PRECISION,
    sector          TEXT,
    sector_concentration_pct DOUBLE PRECISION,
    unrealized_pnl_pct DOUBLE PRECISION,
    unrealized_pnl_dollars DOUBLE PRECISION,
    days_held       INTEGER,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_pos_risk_ts     ON position_risk_snapshot(snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_pos_risk_ticker ON position_risk_snapshot(ticker);

-- =========================================================================
-- portfolio_risk_history: portfolio-level daily risk metrics
-- =========================================================================
CREATE TABLE IF NOT EXISTS portfolio_risk_history (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_at     TIMESTAMPTZ NOT NULL,
    n_positions     INTEGER,
    total_exposure_pct DOUBLE PRECISION,
    gross_exposure_pct DOUBLE PRECISION,
    net_exposure_pct   DOUBLE PRECISION,
    portfolio_beta  DOUBLE PRECISION,
    portfolio_var_95_1d DOUBLE PRECISION,
    portfolio_cvar_95_1d DOUBLE PRECISION,
    largest_position_pct DOUBLE PRECISION,
    top3_concentration_pct DOUBLE PRECISION,
    sector_max_pct  DOUBLE PRECISION,
    sharpe_126d     DOUBLE PRECISION,
    sortino_126d    DOUBLE PRECISION,
    max_dd_252d     DOUBLE PRECISION,
    correlation_to_spy_30d DOUBLE PRECISION,
    drawdown_current_pct DOUBLE PRECISION,
    days_in_drawdown INTEGER,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_risk_day ON portfolio_risk_history(snapshot_at);

-- =========================================================================
-- kelly_size_history: per-entry kelly multiplier breakdown
-- =========================================================================
CREATE TABLE IF NOT EXISTS kelly_size_history (
    id              BIGSERIAL PRIMARY KEY,
    decided_at      TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    signal_id       BIGINT,                     -- soft FK signal_log.id
    base_kelly      DOUBLE PRECISION,
    drawdown_mult   DOUBLE PRECISION,
    regime_mult     DOUBLE PRECISION,
    vix_mult        DOUBLE PRECISION,
    earnings_mult   DOUBLE PRECISION,
    var_floor_mult  DOUBLE PRECISION,
    sharpe_mult     DOUBLE PRECISION,
    final_kelly     DOUBLE PRECISION,
    final_size_pct  DOUBLE PRECISION,
    final_size_dollars DOUBLE PRECISION,
    final_shares    INTEGER,
    reason          TEXT,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_kelly_ts ON kelly_size_history(decided_at DESC);

-- =========================================================================
-- wilson_ci_snapshot: daily snapshot of every sub-strategy's Wilson LB
-- =========================================================================
CREATE TABLE IF NOT EXISTS wilson_ci_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL,
    setup_family    TEXT NOT NULL,
    regime          TEXT,
    score_band      TEXT,
    entry_quality   TEXT,
    n_trades        INTEGER,
    n_wins          INTEGER,
    wr              DOUBLE PRECISION,
    wilson_lb_95    DOUBLE PRECISION,
    wilson_ub_95    DOUBLE PRECISION,
    profit_factor   DOUBLE PRECISION,
    avg_r_multiple  DOUBLE PRECISION,
    sharpe          DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wilson_cell ON wilson_ci_snapshot(snapshot_date, setup_family, regime, score_band, entry_quality);

-- =========================================================================
-- model_predictions: 3-headed model forecasts per ticker per day
-- =========================================================================
CREATE TABLE IF NOT EXISTS model_predictions (
    id              BIGSERIAL PRIMARY KEY,
    predicted_at    TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    model_id        TEXT NOT NULL,              -- 'mledge_v3' / 'pead_xgb' / etc
    model_version   TEXT,
    horizon_days    INTEGER NOT NULL,           -- 5 / 10 / 20
    predicted_return DOUBLE PRECISION,
    predicted_prob_up DOUBLE PRECISION,
    confidence      DOUBLE PRECISION,
    feature_hash    TEXT,                       -- sha1 of feature vector for replay
    realized_return DOUBLE PRECISION,           -- backfilled when horizon passes
    realized_at     TIMESTAMPTZ,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_model_pred_ts     ON model_predictions(predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_pred_ticker ON model_predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_model_pred_model  ON model_predictions(model_id);

-- =========================================================================
-- model_calibration: predicted-vs-realized Brier scores
-- =========================================================================
CREATE TABLE IF NOT EXISTS model_calibration (
    id              BIGSERIAL PRIMARY KEY,
    evaluated_at    TIMESTAMPTZ NOT NULL,
    model_id        TEXT NOT NULL,
    model_version   TEXT,
    horizon_days    INTEGER,
    window_days     INTEGER,                    -- evaluation window
    n_predictions   INTEGER,
    brier_score     DOUBLE PRECISION,
    mae             DOUBLE PRECISION,
    rmse            DOUBLE PRECISION,
    calibration_curve JSONB,                    -- decile bins: predicted_avg, realized_avg
    auc             DOUBLE PRECISION,
    log_loss        DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);

-- =========================================================================
-- strategy_pnl_attribution: daily $ PnL split by sleeve
-- =========================================================================
CREATE TABLE IF NOT EXISTS strategy_pnl_attribution (
    id              BIGSERIAL PRIMARY KEY,
    attribution_date DATE NOT NULL,
    sleeve          TEXT NOT NULL,              -- 'momentum' / 'pead' / 'insider' / etc
    n_positions     INTEGER,
    n_closes        INTEGER,
    realized_pnl    DOUBLE PRECISION,
    unrealized_pnl  DOUBLE PRECISION,
    total_pnl       DOUBLE PRECISION,
    win_count       INTEGER,
    loss_count      INTEGER,
    avg_r_multiple  DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pnl_attr ON strategy_pnl_attribution(attribution_date, sleeve);

-- =========================================================================
-- stop_levels_history: every stop adjustment with reason
-- =========================================================================
CREATE TABLE IF NOT EXISTS stop_levels_history (
    id              BIGSERIAL PRIMARY KEY,
    adjusted_at     TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    position_id     BIGINT,
    old_stop        DOUBLE PRECISION,
    new_stop        DOUBLE PRECISION,
    delta_pct       DOUBLE PRECISION,
    reason          TEXT,                       -- TRAIL / BREAKEVEN / REGIME_FLIP / MANUAL / GAP_RESET
    triggered_by    TEXT,                       -- system / user / executor
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_stop_hist_ts     ON stop_levels_history(adjusted_at DESC);
CREATE INDEX IF NOT EXISTS idx_stop_hist_ticker ON stop_levels_history(ticker);

-- =========================================================================
-- slippage_realized: actual entry/exit slippage per fill
-- =========================================================================
CREATE TABLE IF NOT EXISTS slippage_realized (
    id              BIGSERIAL PRIMARY KEY,
    filled_at       TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    order_id        TEXT,                       -- soft FK orders.order_id
    side            TEXT,                       -- entry / exit
    expected_price  DOUBLE PRECISION,
    filled_price    DOUBLE PRECISION,
    slippage_dollars DOUBLE PRECISION,
    slippage_pct    DOUBLE PRECISION,
    slippage_bps    DOUBLE PRECISION,
    adv_pct         DOUBLE PRECISION,           -- order qty / 20d ADV
    atr_pct         DOUBLE PRECISION,           -- order qty × ATR / equity
    sync_key        TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_slip_ts     ON slippage_realized(filled_at DESC);
CREATE INDEX IF NOT EXISTS idx_slip_ticker ON slippage_realized(ticker);

-- =========================================================================
-- var_breaches: when realized loss exceeded VaR estimate (model calibration)
-- =========================================================================
CREATE TABLE IF NOT EXISTS var_breaches (
    id              BIGSERIAL PRIMARY KEY,
    breached_at     TIMESTAMPTZ NOT NULL,
    scope           TEXT NOT NULL,              -- 'position' / 'portfolio'
    ticker          TEXT,                       -- null if portfolio-scope
    var_estimate    DOUBLE PRECISION,
    realized_loss   DOUBLE PRECISION,
    breach_magnitude DOUBLE PRECISION,          -- realized / var
    confidence_level DOUBLE PRECISION,          -- typically 0.95
    days_breached_30d INTEGER,                  -- how many breaches in last 30d
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);

INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('007'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
