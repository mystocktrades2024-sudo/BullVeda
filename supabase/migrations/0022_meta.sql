-- ============================================================================
-- SwingTrade · Supabase migration 0022 · Schema metadata table
-- ============================================================================
-- Key/value sidecar for schema version, build info, last-migration timestamp,
-- and any cross-cutting metadata that doesn't fit a domain-specific table.
--
-- Why: supabase_client.healthcheck() probes `meta` to confirm the schema cache
-- is healthy. Without this table the healthcheck always fails with PGRST205
-- "Could not find the table 'public.meta'", even on a fully-applied schema —
-- a code-vs-schema drift bug. This migration is the canonical fix.
-- ============================================================================

create table if not exists public.meta (
  key         text         primary key,
  value       jsonb        not null,
  updated_at  timestamptz  not null default now()
);

drop trigger if exists tg_meta_updated_at on public.meta;
create trigger tg_meta_updated_at
  before update on public.meta
  for each row execute function public.tg_set_updated_at();

-- Seed schema-version + last-applied so the healthcheck has a row to read.
-- Use jsonb so we can extend without DDL — e.g. add deploy_sha, git_commit etc.
insert into public.meta (key, value) values
  ('schema_version',        jsonb_build_object('version', '0022', 'applied_at', now())),
  ('healthcheck_canary',    jsonb_build_object('ok', true, 'message', 'schema cache reachable'))
on conflict (key) do update
  set value      = excluded.value,
      updated_at = now();
