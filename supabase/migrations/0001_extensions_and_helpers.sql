-- ============================================================================
-- SwingTrade · Supabase migration 0001 · Extensions + helpers
-- ============================================================================
-- Single-user paper-trading system; service-role does all ETL; authenticated
-- users come in via Supabase Auth and are gated by role in public.users.
-- ============================================================================

create extension if not exists "uuid-ossp";
create extension if not exists "pg_trgm";        -- fuzzy search on tickers/news
create extension if not exists "btree_gin";      -- jsonb + gin combined

-- ---------------------------------------------------------------------------
-- Auto-bump updated_at trigger function (shared)
-- ---------------------------------------------------------------------------
create or replace function public.tg_set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------------------
-- Convenience: current user role lookup (used by RLS policies)
-- Returns 'service' for service-role; 'anon' for unauthenticated;
-- 'viewer'/'trader'/'quant'/'admin' for authenticated.
-- ---------------------------------------------------------------------------
-- plpgsql (not sql) so the public.users reference is resolved at call time,
-- letting these functions exist before migration 0017 creates the table.
create or replace function public.current_user_role()
returns text language plpgsql stable as $$
declare r text;
begin
  begin
    select role into r from public.users where id = auth.uid();
  exception
    when undefined_table then return 'anon';
  end;
  return coalesce(r, 'anon');
end $$;

create or replace function public.is_admin()
returns boolean language plpgsql stable as $$
begin return public.current_user_role() = 'admin'; end $$;

create or replace function public.is_trader_or_admin()
returns boolean language plpgsql stable as $$
begin return public.current_user_role() in ('trader','admin'); end $$;

create or replace function public.is_authenticated_member()
returns boolean language plpgsql stable as $$
begin return public.current_user_role() in ('viewer','trader','quant','admin'); end $$;
