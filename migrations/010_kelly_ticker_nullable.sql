-- 010_kelly_ticker_nullable.sql
-- kelly_position_size() is portfolio-wide (no ticker arg). Sidecar logs each
-- call; ticker is null for system-level Kelly. Relax the NOT NULL constraint.

ALTER TABLE kelly_size_history ALTER COLUMN ticker DROP NOT NULL;
