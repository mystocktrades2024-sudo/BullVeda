-- SwingTrade — migration 006: orphan-store tables (2026-05-17, v2)
--
-- Several tables already exist with prior schemas (decision_log, earnings_outcomes,
-- regime_history). For those we ADD COLUMN IF NOT EXISTS instead of CREATE TABLE.
-- For genuinely-new tables (exit_signals, iv_history, orders, eod_actions, etc.)
-- we CREATE TABLE IF NOT EXISTS as normal.

-- =========================================================================
-- decision_log: align existing table with quant-DB shape (ADD COLUMN pattern)
-- =========================================================================
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS decided_at      TIMESTAMPTZ;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS scan_id         TEXT;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS setup_family    TEXT;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS regime          TEXT;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS gates_passed    JSONB;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS gates_failed    JSONB;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS reject_reason   TEXT;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS sync_key        TEXT;
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS raw_json        JSONB;

-- decision_log is a partitioned table on observed_at — unique must include partition key
CREATE UNIQUE INDEX IF NOT EXISTS uq_decision_log_sync ON decision_log(observed_at, sync_key);
CREATE INDEX IF NOT EXISTS idx_decision_log_ts     ON decision_log(decided_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_decision_log_ticker ON decision_log(ticker);
CREATE INDEX IF NOT EXISTS idx_decision_log_setup  ON decision_log(setup_family);
CREATE INDEX IF NOT EXISTS idx_decision_log_regime ON decision_log(regime);

-- =========================================================================
-- exit_signals: NEW table (147 lines in JSONL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS exit_signals (
    id              BIGSERIAL PRIMARY KEY,
    flagged_at      TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    direction       TEXT,
    entry_price     DOUBLE PRECISION,
    current_price   DOUBLE PRECISION,
    reason          TEXT,
    confidence      DOUBLE PRECISION,
    setup_family    TEXT,
    days_held       INTEGER,
    unrealized_pnl_pct DOUBLE PRECISION,
    acted_on        BOOLEAN,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_exit_signals_ts     ON exit_signals(flagged_at DESC);
CREATE INDEX IF NOT EXISTS idx_exit_signals_ticker ON exit_signals(ticker);

-- =========================================================================
-- earnings_outcomes: align existing table (ADD COLUMN pattern)
-- =========================================================================
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS report_date      DATE;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS ticker           TEXT;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS predicted_tier   TEXT;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS predicted_prob   DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS eps_estimate     DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS eps_actual       DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS eps_surprise_pct DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS rev_estimate     DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS rev_actual       DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS beat             BOOLEAN;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS gap_open_pct     DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS close_5d_pct     DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS close_10d_pct    DOUBLE PRECISION;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS sector           TEXT;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS sync_key         TEXT;
ALTER TABLE earnings_outcomes ADD COLUMN IF NOT EXISTS raw_json         JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS uq_earn_outcomes_sync ON earnings_outcomes(sync_key);
CREATE INDEX IF NOT EXISTS idx_earn_outcomes_date   ON earnings_outcomes(report_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_earn_outcomes_ticker ON earnings_outcomes(ticker);

-- =========================================================================
-- iv_history: NEW (1,226 lines in JSONL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS iv_history (
    id              BIGSERIAL PRIMARY KEY,
    observed_at     TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    iv30            DOUBLE PRECISION,
    iv60            DOUBLE PRECISION,
    iv_rank         DOUBLE PRECISION,
    iv_percentile   DOUBLE PRECISION,
    hv30            DOUBLE PRECISION,
    iv_hv_ratio     DOUBLE PRECISION,
    call_volume     INTEGER,
    put_volume      INTEGER,
    call_put_ratio  DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_iv_history_ts     ON iv_history(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_iv_history_ticker ON iv_history(ticker);

-- =========================================================================
-- orders: NEW (63 lines in JSONL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    submitted_at    TIMESTAMPTZ NOT NULL,
    broker          TEXT NOT NULL DEFAULT 'alpaca_paper',
    order_id        TEXT,
    client_order_id TEXT,
    ticker          TEXT NOT NULL,
    direction       TEXT,
    side            TEXT,
    order_type      TEXT,
    qty             DOUBLE PRECISION,
    limit_price     DOUBLE PRECISION,
    stop_price      DOUBLE PRECISION,
    status          TEXT,
    filled_qty      DOUBLE PRECISION,
    filled_avg_price DOUBLE PRECISION,
    expected_price  DOUBLE PRECISION,
    slippage_pct    DOUBLE PRECISION,
    extended_hours  BOOLEAN,
    time_in_force   TEXT,
    canceled_at     TIMESTAMPTZ,
    filled_at       TIMESTAMPTZ,
    rejection_reason TEXT,
    setup_type      TEXT,
    signal_id       BIGINT,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_orders_ts     ON orders(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- =========================================================================
-- eod_actions: NEW (13 lines in JSONL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS eod_actions (
    id              BIGSERIAL PRIMARY KEY,
    acted_at        TIMESTAMPTZ NOT NULL,
    action_type     TEXT NOT NULL,
    ticker          TEXT,
    position_id     BIGINT,
    qty             DOUBLE PRECISION,
    new_stop        DOUBLE PRECISION,
    reason          TEXT,
    auto            BOOLEAN,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_eod_actions_ts     ON eod_actions(acted_at DESC);
CREATE INDEX IF NOT EXISTS idx_eod_actions_ticker ON eod_actions(ticker);

-- =========================================================================
-- regime_history: align existing table (ADD COLUMN pattern)
-- =========================================================================
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS regime          TEXT;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS spy_ema50_pct   DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS spy_ema200_pct  DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS qqq_ema50_pct   DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS vix_pct_change  DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS breadth_pct     DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS hyg_pct         DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS uup_pct         DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS gld_pct         DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS confidence      DOUBLE PRECISION;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS universe        TEXT;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS sync_key        TEXT;
ALTER TABLE regime_history ADD COLUMN IF NOT EXISTS raw_json        JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS uq_regime_history_sync ON regime_history(sync_key);
CREATE INDEX IF NOT EXISTS idx_regime_history_ts ON regime_history(observed_at DESC);

-- =========================================================================
-- regime_transitions: NEW
-- =========================================================================
CREATE TABLE IF NOT EXISTS regime_transitions (
    id              BIGSERIAL PRIMARY KEY,
    transitioned_at TIMESTAMPTZ NOT NULL,
    regime_from     TEXT NOT NULL,
    regime_to       TEXT NOT NULL,
    bars_at_target  INTEGER,
    vix_at_flip     DOUBLE PRECISION,
    breadth_at_flip DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_regime_trans_ts ON regime_transitions(transitioned_at DESC);

-- =========================================================================
-- rolling_sharpe_history: NEW
-- =========================================================================
CREATE TABLE IF NOT EXISTS rolling_sharpe_history (
    id              BIGSERIAL PRIMARY KEY,
    observed_at     TIMESTAMPTZ NOT NULL,
    window_days     INTEGER NOT NULL DEFAULT 126,
    sharpe          DOUBLE PRECISION,
    sortino         DOUBLE PRECISION,
    calmar          DOUBLE PRECISION,
    max_drawdown    DOUBLE PRECISION,
    n_trades        INTEGER,
    win_rate        DOUBLE PRECISION,
    profit_factor   DOUBLE PRECISION,
    avg_r_multiple  DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rolling_sharpe ON rolling_sharpe_history(observed_at, window_days);

-- =========================================================================
-- smc_hit_rates: NEW
-- =========================================================================
CREATE TABLE IF NOT EXISTS smc_hit_rates (
    id              BIGSERIAL PRIMARY KEY,
    observed_at     TIMESTAMPTZ NOT NULL,
    block_type      TEXT NOT NULL,
    timeframe       TEXT,
    n_observations  INTEGER,
    n_hits          INTEGER,
    hit_rate        DOUBLE PRECISION,
    avg_r_multiple  DOUBLE PRECISION,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);

-- =========================================================================
-- fundamentals_pit: NEW (folds data/fundamentals.db)
-- =========================================================================
CREATE TABLE IF NOT EXISTS fundamentals_pit (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    period_end      DATE NOT NULL,
    report_date     DATE,
    fetched_at      TIMESTAMPTZ NOT NULL,
    eps_basic       DOUBLE PRECISION,
    eps_diluted     DOUBLE PRECISION,
    eps_ttm         DOUBLE PRECISION,
    revenue         DOUBLE PRECISION,
    revenue_ttm     DOUBLE PRECISION,
    gross_margin    DOUBLE PRECISION,
    operating_margin DOUBLE PRECISION,
    net_margin      DOUBLE PRECISION,
    fcf             DOUBLE PRECISION,
    debt_to_equity  DOUBLE PRECISION,
    current_ratio   DOUBLE PRECISION,
    roe             DOUBLE PRECISION,
    roa             DOUBLE PRECISION,
    revenue_growth_yoy DOUBLE PRECISION,
    eps_growth_yoy  DOUBLE PRECISION,
    shares_out      DOUBLE PRECISION,
    market_cap      DOUBLE PRECISION,
    sector          TEXT,
    industry        TEXT,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_fund_pit_ticker_period ON fundamentals_pit(ticker, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_fund_pit_report        ON fundamentals_pit(report_date DESC NULLS LAST);

-- =========================================================================
-- ticker_enrichment_snapshot: NEW (folds data/enrichment_cache.db)
-- =========================================================================
CREATE TABLE IF NOT EXISTS ticker_enrichment_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    source          TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    ttl_seconds     INTEGER DEFAULT 21600,
    payload         JSONB NOT NULL,
    sync_key        TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_enrich_ticker  ON ticker_enrichment_snapshot(ticker);
CREATE INDEX IF NOT EXISTS idx_enrich_fetched ON ticker_enrichment_snapshot(fetched_at DESC);

INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('006'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
