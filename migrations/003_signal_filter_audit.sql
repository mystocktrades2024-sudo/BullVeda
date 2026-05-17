-- SwingTrade — signal_filter audit trail (2026-05-09, migration 003)
--
-- Why: A2 ships signal_filter.py which demotes BUY → WATCH for non-whitelisted
-- (setup × regime × score_band × entry_quality) combinations. Need a live audit
-- log so we can:
--   1. See which sub-strategies are firing in production
--   2. Detect drift (live demotion rate vs. backtest expected rate)
--   3. Justify whitelist changes with evidence
--
-- One row per filter decision (allow OR demote). Insert from signal_filter.py
-- after the gate evaluates each ticker.

CREATE TABLE IF NOT EXISTS signal_filter_decisions (
    id              BIGSERIAL PRIMARY KEY,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticker          TEXT NOT NULL,
    setup_type      TEXT,
    setup_family    TEXT,
    regime          TEXT,
    score           INTEGER,
    score_band      TEXT,                            -- '60-69' / '70-79' / '80-89' / '90-100'
    entry_quality   TEXT,                            -- FRESH/PULLBACK/VALID/EXTENDED/MISSED
    -- Decision
    allow           BOOLEAN NOT NULL,                -- True = filter let it through; False = demoted
    matched_rule_id TEXT,                            -- whitelist rule key, if matched
    reason          TEXT,                            -- demote_reason or "whitelisted" or "filter_disabled"
    -- Provenance
    config_hash     TEXT,                            -- sha1 of signal_filter config block at decision time
    git_commit      TEXT,
    raw_context     JSONB                            -- full ticker analysis dict for replay
);

CREATE INDEX IF NOT EXISTS idx_sfd_decided_at ON signal_filter_decisions(decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_sfd_ticker     ON signal_filter_decisions(ticker);
CREATE INDEX IF NOT EXISTS idx_sfd_setup      ON signal_filter_decisions(setup_type);
CREATE INDEX IF NOT EXISTS idx_sfd_allow      ON signal_filter_decisions(allow);
CREATE INDEX IF NOT EXISTS idx_sfd_rule       ON signal_filter_decisions(matched_rule_id);

-- View: rolling 30-day demotion rate per setup × regime — feeds the drift
-- dashboard tile (A7) so we can spot whitelist staleness fast.
CREATE OR REPLACE VIEW signal_filter_drift_30d AS
SELECT
    setup_type,
    regime,
    score_band,
    COUNT(*)                                              AS n_decisions,
    SUM(CASE WHEN allow THEN 1 ELSE 0 END)                AS n_allowed,
    SUM(CASE WHEN NOT allow THEN 1 ELSE 0 END)            AS n_demoted,
    ROUND(
      AVG(CASE WHEN allow THEN 1.0 ELSE 0.0 END)::numeric, 3
    )                                                     AS allow_rate,
    MIN(decided_at)                                       AS first_decision,
    MAX(decided_at)                                       AS last_decision
FROM signal_filter_decisions
WHERE decided_at >= NOW() - INTERVAL '30 days'
GROUP BY setup_type, regime, score_band;

-- Mark schema 003 (meta.value is JSONB)
INSERT INTO meta (key, value) VALUES ('schema_version', to_jsonb('003'::text))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
