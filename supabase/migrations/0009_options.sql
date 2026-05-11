-- ============================================================================
-- 0009 · Options · IV · UOA
-- ============================================================================
-- Source: Schwab Trader API (re-activated 2026-05-03). 2h cache.
-- ============================================================================

create table if not exists public.options_snapshot (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  source               text default 'schwab',
  current_iv           numeric,
  iv_rank              numeric,
  iv_pct               numeric,
  put_call_ratio       numeric,
  total_call_oi        bigint,
  total_call_vol       bigint,
  total_put_oi         bigint,
  total_put_vol        bigint,
  max_pain             numeric,
  uoa_calls            integer default 0,
  uoa_puts             integer default 0,
  error                text
);

create table if not exists public.options_intelligence (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  iv_skew              numeric,
  pc_ratio_oi          numeric,
  pc_ratio_vol         numeric,
  gamma_wall_above     numeric,
  gamma_wall_below     numeric,
  max_pain             numeric,
  dominant_flow        text check (dominant_flow in ('calls','puts','balanced') or dominant_flow is null),
  iv_rank_est          numeric,
  call_oi_sum          bigint,
  call_vol_sum         bigint,
  put_oi_sum           bigint,
  put_vol_sum          bigint
);

create table if not exists public.options_kpis (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  iv_percentile        numeric,
  iv_current           numeric,
  put_call_ratio       numeric,
  uoa_calls            boolean,
  uoa_puts             boolean,
  uoa_call_detail      text,
  uoa_put_detail       text,
  gamma_net            bigint,
  skew_25d             numeric,
  max_pain             numeric,
  term_structure       text check (term_structure in ('contango','backwardation','flat') or term_structure is null),
  term_front_iv        numeric,
  term_back_iv         numeric,
  verdict              text,
  verdict_confidence   numeric,
  narrative            text
);

create table if not exists public.options_per_mode (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  mode                 text check (mode in ('swing','position','invest')),
  kpi_json             jsonb,
  unique (analysis_id, mode)
);

create table if not exists public.option_uoa_alerts (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  side                 text check (side in ('call','put')),
  strike               numeric,
  expiry               date,
  volume               bigint,
  open_interest        bigint,
  vol_oi_ratio         numeric,
  premium_dollars      numeric,
  is_smart_money       boolean default false
);
create index uoa_aid_idx on public.option_uoa_alerts(analysis_id);

create table if not exists public.option_chain (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  side                 text check (side in ('call','put')),
  strike               numeric,
  expiry               date,
  open_interest        bigint,
  volume               bigint,
  iv                   numeric,
  delta                numeric,
  gamma                numeric,
  theta                numeric,
  vega                 numeric,
  bid                  numeric,
  ask                  numeric
);
create index option_chain_aid_idx on public.option_chain(analysis_id);

create table if not exists public.gamma_exposure (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  gamma_score          numeric,
  call_oi_skew         numeric,
  short_float_pct      numeric,
  float_size_m         numeric
);
