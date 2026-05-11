-- ============================================================================
-- 0021 · Field schema · master field catalog
-- ============================================================================
-- One row per (table, field_path) describing what each column carries.
-- This is the canonical "Schema · Fields" reference — used by docs/ER viewer
-- and surfaced in the dashboard so consumers know what every column means.
-- ============================================================================

create table if not exists public.field_schema (
  id                bigserial primary key,
  category          text,            -- top-level domain (Identity / Pricing / Scoring / Verdict / Setup / Technicals / SMC / Fundamentals / Options / Smart Money / Sentiment / Zacks / Risk / Theory / Tier1 / Multi-TF / Earnings / Bookkeeping)
  sub_group         text,            -- sub-category (EMA Ladder / Momentum / Pattern / Trend Signal / etc.)
  field_path        text not null,   -- the original key, e.g. 'technicals.indicators.ema100'
  table_name        text,            -- where it now lives, e.g. 'technicals_ema'
  column_name       text,            -- column in that table, e.g. 'ema100'
  data_type         text,            -- inferred type: float / int / bool / str / dict / list
  sample_value      text,            -- redacted/truncated example value
  source            text,            -- where data originates: computed / EODHD / Schwab / yfinance / Zacks / etc.
  description       text,            -- one-line human description
  is_active         boolean default true,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now(),
  unique (field_path)
);

create index if not exists field_schema_category_idx on public.field_schema(category);
create index if not exists field_schema_table_idx    on public.field_schema(table_name);
create index if not exists field_schema_source_idx   on public.field_schema(source);
create index if not exists field_schema_path_trgm    on public.field_schema using gin (field_path gin_trgm_ops);

create trigger field_schema_set_updated before update on public.field_schema
  for each row execute function public.tg_set_updated_at();

-- RLS: read for any member, write admin-only
alter table public.field_schema enable row level security;
drop policy if exists field_schema_read on public.field_schema;
create policy field_schema_read on public.field_schema
  for select using (public.is_authenticated_member());
drop policy if exists field_schema_write on public.field_schema;
create policy field_schema_write on public.field_schema
  for all using (public.is_admin()) with check (public.is_admin());
