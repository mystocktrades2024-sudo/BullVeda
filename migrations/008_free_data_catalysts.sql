-- SwingTrade — migration 008: free-data tables (catalysts + index PIT) (2026-05-17)
--
-- Schema only — scrapers to populate are in scripts/scrapers/* (future work).
-- All data sources are FREE per CLAUDE.md hard constraint (no new paid licenses).

-- =========================================================================
-- tickers_master: per-ticker static + slowly-changing metadata
-- =========================================================================
CREATE TABLE IF NOT EXISTS tickers_master (
    ticker          TEXT PRIMARY KEY,
    name            TEXT,
    exchange        TEXT,                       -- NYSE / NASDAQ / AMEX
    sector          TEXT,
    industry        TEXT,
    gics_sub_industry TEXT,
    listing_date    DATE,
    delisting_date  DATE,                       -- null if active
    market_cap      DOUBLE PRECISION,
    shares_out      DOUBLE PRECISION,
    float_shares    DOUBLE PRECISION,
    avg_volume_20d  DOUBLE PRECISION,
    avg_dollar_volume_20d DOUBLE PRECISION,
    cusip           TEXT,
    isin            TEXT,
    cik             TEXT,                       -- SEC central index key
    is_etf          BOOLEAN DEFAULT false,
    is_adr          BOOLEAN DEFAULT false,
    country         TEXT DEFAULT 'US',
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_tickers_sector  ON tickers_master(sector);
CREATE INDEX IF NOT EXISTS idx_tickers_active  ON tickers_master(delisting_date) WHERE delisting_date IS NULL;

-- =========================================================================
-- index_membership_pit: point-in-time S&P 500 / R1000 / NDX membership
-- Fixes audit flaw #1 (survivorship bias). Free source: Wikipedia revision API.
-- =========================================================================
CREATE TABLE IF NOT EXISTS index_membership_pit (
    id              BIGSERIAL PRIMARY KEY,
    index_name      TEXT NOT NULL,              -- 'sp500' / 'r1000' / 'ndx100'
    ticker          TEXT NOT NULL,
    added_on        DATE NOT NULL,
    removed_on      DATE,                       -- null = currently in index
    source          TEXT,                       -- 'wikipedia_rev_<id>'
    reason          TEXT,                       -- 'addition' / 'merger' / 'delisting' / 'rebalance'
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_imp_index  ON index_membership_pit(index_name);
CREATE INDEX IF NOT EXISTS idx_imp_ticker ON index_membership_pit(ticker);
CREATE INDEX IF NOT EXISTS idx_imp_active ON index_membership_pit(index_name, ticker) WHERE removed_on IS NULL;

-- =========================================================================
-- corporate_actions: splits + special dividends + spinoffs
-- =========================================================================
CREATE TABLE IF NOT EXISTS corporate_actions (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    action_type     TEXT NOT NULL,              -- 'split' / 'dividend' / 'spinoff' / 'rights' / 'ticker_change'
    ex_date         DATE NOT NULL,
    record_date     DATE,
    pay_date        DATE,
    ratio           DOUBLE PRECISION,           -- 2-for-1 split → 2.0
    cash_amount     DOUBLE PRECISION,           -- dividend per share
    currency        TEXT DEFAULT 'USD',
    new_ticker      TEXT,                       -- for ticker_change events
    source          TEXT DEFAULT 'eodhd',
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_corp_ticker_ex ON corporate_actions(ticker, ex_date);
CREATE INDEX IF NOT EXISTS idx_corp_type      ON corporate_actions(action_type);

-- =========================================================================
-- ohlcv_daily: cold storage of daily OHLCV bars
-- Existing schema uses bar_date / adjusted_close — align via ADD COLUMN.
-- =========================================================================
ALTER TABLE ohlcv_daily ADD COLUMN IF NOT EXISTS vwap       DOUBLE PRECISION;
ALTER TABLE ohlcv_daily ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_ohlcv_bar_date ON ohlcv_daily(bar_date);

-- =========================================================================
-- macro_indicators: daily VIX / VIX1D / MOVE / HYG / UUP / GLD / DXY / breadth
-- =========================================================================
CREATE TABLE IF NOT EXISTS macro_indicators (
    observed_at     DATE PRIMARY KEY,
    vix             DOUBLE PRECISION,
    vix1d           DOUBLE PRECISION,
    vix9d           DOUBLE PRECISION,
    vix3m           DOUBLE PRECISION,
    vix6m           DOUBLE PRECISION,
    move            DOUBLE PRECISION,           -- bond vol
    skew            DOUBLE PRECISION,           -- CBOE SKEW index
    hyg_close       DOUBLE PRECISION,
    hyg_pct_change  DOUBLE PRECISION,
    uup_close       DOUBLE PRECISION,
    gld_close       DOUBLE PRECISION,
    dxy             DOUBLE PRECISION,
    spy_close       DOUBLE PRECISION,
    qqq_close       DOUBLE PRECISION,
    iwm_close       DOUBLE PRECISION,
    breadth_above_50d_pct DOUBLE PRECISION,
    breadth_above_200d_pct DOUBLE PRECISION,
    advance_decline DOUBLE PRECISION,
    new_highs_52w   INTEGER,
    new_lows_52w    INTEGER,
    treasury_10y    DOUBLE PRECISION,
    treasury_2y     DOUBLE PRECISION,
    yield_curve_2_10 DOUBLE PRECISION,
    raw_json        JSONB
);

-- =========================================================================
-- insider_transactions: Form 4 filings — align with existing schema
-- (existing uses filer_name / filer_role / value / transacted_at / external_id)
-- =========================================================================
ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS shares_after DOUBLE PRECISION;
ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS filing_url   TEXT;
ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS sync_key     TEXT;
ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS raw_json     JSONB;
CREATE UNIQUE INDEX IF NOT EXISTS uq_insider_sync ON insider_transactions(sync_key);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_transactions(ticker, transacted_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_insider_filed       ON insider_transactions(filed_at DESC NULLS LAST);

-- =========================================================================
-- institutional_holdings: 13F filings (quarterly snapshots)
-- =========================================================================
CREATE TABLE IF NOT EXISTS institutional_holdings (
    id              BIGSERIAL PRIMARY KEY,
    filed_at        TIMESTAMPTZ NOT NULL,
    period_end      DATE NOT NULL,
    holder_name     TEXT NOT NULL,
    holder_cik      TEXT,
    ticker          TEXT NOT NULL,
    shares          DOUBLE PRECISION,
    market_value    DOUBLE PRECISION,
    pct_of_portfolio DOUBLE PRECISION,
    pct_change_qoq  DOUBLE PRECISION,
    source          TEXT DEFAULT 'sec_edgar',
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_inst_ticker_period ON institutional_holdings(ticker, period_end DESC);

-- =========================================================================
-- short_interest_history: bi-monthly SI reports
-- =========================================================================
CREATE TABLE IF NOT EXISTS short_interest_history (
    id              BIGSERIAL PRIMARY KEY,
    settlement_date DATE NOT NULL,
    ticker          TEXT NOT NULL,
    short_shares    BIGINT,
    short_pct_float DOUBLE PRECISION,
    short_pct_outstanding DOUBLE PRECISION,
    days_to_cover   DOUBLE PRECISION,
    source          TEXT DEFAULT 'finra',
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_si_ticker_date ON short_interest_history(ticker, settlement_date);

-- =========================================================================
-- news_events: every news headline with sentiment + source + ticker
-- =========================================================================
CREATE TABLE IF NOT EXISTS news_events (
    id              BIGSERIAL PRIMARY KEY,
    published_at    TIMESTAMPTZ NOT NULL,
    ticker          TEXT,                       -- null = market-wide
    headline        TEXT NOT NULL,
    source          TEXT,
    url             TEXT,
    sentiment_score DOUBLE PRECISION,           -- -1.0 to 1.0
    sentiment_label TEXT,                       -- bullish / bearish / neutral
    relevance       DOUBLE PRECISION,           -- 0-1
    raw_json        JSONB,
    sync_key        TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_news_ts     ON news_events(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_events(ticker, published_at DESC);

-- =========================================================================
-- congressional_trades: align with existing schema
-- (existing uses member / amount_range / transacted_at / reported_at / external_id)
-- =========================================================================
ALTER TABLE congressional_trades ADD COLUMN IF NOT EXISTS asset_name TEXT;
ALTER TABLE congressional_trades ADD COLUMN IF NOT EXISTS amount_min DOUBLE PRECISION;
ALTER TABLE congressional_trades ADD COLUMN IF NOT EXISTS amount_max DOUBLE PRECISION;
ALTER TABLE congressional_trades ADD COLUMN IF NOT EXISTS sync_key   TEXT;
ALTER TABLE congressional_trades ADD COLUMN IF NOT EXISTS raw_json   JSONB;
CREATE UNIQUE INDEX IF NOT EXISTS uq_congress_sync          ON congressional_trades(sync_key);
CREATE INDEX IF NOT EXISTS idx_congress_ticker_date ON congressional_trades(ticker, transacted_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_congress_member      ON congressional_trades(member);

-- =========================================================================
-- fomc_calendar: Fed meeting dates + statement times
-- =========================================================================
CREATE TABLE IF NOT EXISTS fomc_calendar (
    meeting_date    DATE PRIMARY KEY,
    statement_time  TEXT,                       -- '14:00 ET' typically
    presser_time    TEXT,                       -- '14:30 ET' typically
    is_decision_meeting BOOLEAN DEFAULT true,
    rate_decision_bps INTEGER,                  -- backfilled after meeting: -25/0/+25/etc
    actual_rate_pct DOUBLE PRECISION,
    statement_url   TEXT,
    source          TEXT DEFAULT 'fed_ical',
    raw_json        JSONB
);

-- =========================================================================
-- economic_calendar: CPI / NFP / retail / PMI release dates
-- =========================================================================
CREATE TABLE IF NOT EXISTS economic_calendar (
    id              BIGSERIAL PRIMARY KEY,
    release_at      TIMESTAMPTZ NOT NULL,
    event_name      TEXT NOT NULL,              -- 'CPI' / 'NFP' / 'PMI_Manufacturing' / etc
    actual          DOUBLE PRECISION,
    forecast        DOUBLE PRECISION,
    previous        DOUBLE PRECISION,
    impact          TEXT,                       -- 'high' / 'medium' / 'low'
    country         TEXT DEFAULT 'US',
    source          TEXT,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_econ_release ON economic_calendar(release_at DESC);

-- =========================================================================
-- ipo_calendar: upcoming + recent IPOs
-- =========================================================================
CREATE TABLE IF NOT EXISTS ipo_calendar (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT,
    company_name    TEXT NOT NULL,
    expected_date   DATE,
    actual_date     DATE,
    price_low       DOUBLE PRECISION,
    price_high      DOUBLE PRECISION,
    price_offered   DOUBLE PRECISION,
    shares_offered  BIGINT,
    exchange        TEXT,
    underwriter     TEXT,
    sector          TEXT,
    industry        TEXT,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_ipo_date ON ipo_calendar(expected_date);

-- =========================================================================
-- splits_calendar: upcoming + recent splits (denormalized view of corporate_actions)
-- =========================================================================
CREATE TABLE IF NOT EXISTS splits_calendar (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    ex_date         DATE NOT NULL,
    ratio           DOUBLE PRECISION,
    direction       TEXT,                       -- 'forward' / 'reverse'
    announcement_date DATE,
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);

-- =========================================================================
-- fda_calendar: biotech PDUFA dates + adcomm hearings
-- =========================================================================
CREATE TABLE IF NOT EXISTS fda_calendar (
    id              BIGSERIAL PRIMARY KEY,
    event_date      DATE NOT NULL,
    ticker          TEXT,
    company         TEXT,
    drug_name       TEXT,
    indication      TEXT,
    event_type      TEXT,                       -- 'PDUFA' / 'Adcomm' / 'CRL' / 'Approval'
    outcome         TEXT,                       -- 'approved' / 'rejected' / 'delayed' (post-event)
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);

-- =========================================================================
-- earnings_calendar_pit: upcoming earnings dates, vintage-tracked
-- =========================================================================
CREATE TABLE IF NOT EXISTS earnings_calendar_pit (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    expected_date   DATE NOT NULL,
    first_known_at  TIMESTAMPTZ NOT NULL,       -- when was the date first published
    last_confirmed_at TIMESTAMPTZ,
    actual_date     DATE,                       -- backfilled after report
    bmo_amc         TEXT,                       -- 'BMO' (before market open) / 'AMC' (after close)
    eps_estimate    DOUBLE PRECISION,
    eps_estimate_high DOUBLE PRECISION,
    eps_estimate_low DOUBLE PRECISION,
    eps_actual      DOUBLE PRECISION,
    rev_estimate    DOUBLE PRECISION,
    rev_actual      DOUBLE PRECISION,
    source          TEXT DEFAULT 'zacks',
    sync_key        TEXT UNIQUE,
    raw_json        JSONB
);
CREATE INDEX IF NOT EXISTS idx_ecpit_ticker_expected ON earnings_calendar_pit(ticker, expected_date);
CREATE INDEX IF NOT EXISTS idx_ecpit_expected        ON earnings_calendar_pit(expected_date);

INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('008'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
