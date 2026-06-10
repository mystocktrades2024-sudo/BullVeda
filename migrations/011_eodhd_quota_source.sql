-- =========================================================================
-- 011_eodhd_quota_source.sql  (2026-06-10)
-- Add a `source` dimension to eodhd_quota_usage so daily quota consumption can
-- be attributed PER JOB (morning scan vs ml_predict vs options vs precompute vs
-- server). Previously the upsert keyed on (bucket_date, endpoint) only, so every
-- one of the ~15 daily jobs overwrote the same row — the table reflected the LAST
-- flusher, not the day's total. Adding source to the unique key gives each job
-- its own row; SUM over source = the true daily per-endpoint total.
-- =========================================================================

ALTER TABLE eodhd_quota_usage
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'unknown';
    -- source = entry-point job name (swing_trade / server / ml_predict /
    -- precompute_targets / options_executor / ...), from EODHD_QUOTA_SOURCE env
    -- or basename(sys.argv[0]).

-- Widen the uniqueness so different jobs no longer clobber each other.
DROP INDEX IF EXISTS uq_quota_bucket;
CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_bucket_src
    ON eodhd_quota_usage(bucket_date, endpoint, source);

-- Helpful for "who blew the quota today" queries.
CREATE INDEX IF NOT EXISTS idx_quota_source_date
    ON eodhd_quota_usage(bucket_date, source);
