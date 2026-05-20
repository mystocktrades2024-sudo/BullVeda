-- 0023_equity_audit_schema_fix.sql
-- Reconcile equity_audit schema drift surfaced by migrate_sqlite_to_supabase
-- 2026-05-19/20 supabase-sync runs.
--
-- Symptom: portfolio_state upserts fail with:
--   APIError: column "timestamp" of relation "equity_audit" does not exist
--
-- Root cause: a DB trigger (added historically via the Supabase dashboard or
-- legacy DDL) writes to equity_audit columns timestamp/old_equity/new_equity/
-- old_cash/new_cash/invested/reason — but the table created in 0016 only has
-- occurred_at/event_type/delta/balance_after/note. The trigger was never
-- migrated to match the current columns.
--
-- Fix: ADD the columns the trigger writes (idempotent — IF NOT EXISTS). We
-- DO NOT remove the original columns so existing rows survive.

alter table public.equity_audit
  add column if not exists timestamp   timestamptz,
  add column if not exists old_equity  numeric,
  add column if not exists new_equity  numeric,
  add column if not exists old_cash    numeric,
  add column if not exists new_cash    numeric,
  add column if not exists invested    numeric,
  add column if not exists reason      text,
  add column if not exists sync_key    text;

-- Backfill timestamp from occurred_at on existing rows (best-effort).
update public.equity_audit
   set timestamp = occurred_at
 where timestamp is null
   and occurred_at is not null;

-- Backfill sync_key so future upserts on sync_key work.
update public.equity_audit
   set sync_key = 'ea:' || coalesce(timestamp::text, occurred_at::text, id::text) || ':' || coalesce(reason, event_type, '')
 where sync_key is null;

-- Add unique constraint on sync_key so on_conflict=sync_key upserts work.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'equity_audit_sync_key_key'
  ) then
    alter table public.equity_audit
      add constraint equity_audit_sync_key_key unique (sync_key);
  end if;
end $$;

create index if not exists equity_audit_timestamp_idx on public.equity_audit(timestamp desc);
