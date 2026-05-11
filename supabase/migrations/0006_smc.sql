-- ============================================================================
-- 0006 · Smart Money Concepts (SMC) domain
-- ============================================================================

create table if not exists public.smc_summary (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  score                numeric,
  smc_direction        text,
  fvg_target           numeric,
  ob_entry_zone        numeric,
  ob_stop              numeric
);

create table if not exists public.smc_order_blocks (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  idx                  integer,
  direction            text check (direction in ('bullish','bearish') or direction is null),
  top                  numeric,
  bottom               numeric,
  bar_offset           integer,
  mitigated            boolean default false,
  broken               boolean default false
);
create index smc_ob_aid_idx on public.smc_order_blocks(analysis_id);

create table if not exists public.smc_fvg_zones (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  idx                  integer,
  direction            text check (direction in ('bullish','bearish') or direction is null),
  top                  numeric,
  bottom               numeric,
  mid                  numeric,
  filled               boolean default false
);
create index smc_fvg_aid_idx on public.smc_fvg_zones(analysis_id);

create table if not exists public.smc_liquidity_sweeps (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  direction            text,
  level                numeric,
  bar_offset           integer
);
create index smc_sweep_aid_idx on public.smc_liquidity_sweeps(analysis_id);

create table if not exists public.smc_bos_choch (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  bos_bullish          boolean,
  bos_bearish          boolean,
  choch_bullish        boolean,
  choch_bearish        boolean,
  last_swing_high      numeric,
  last_swing_low       numeric
);
