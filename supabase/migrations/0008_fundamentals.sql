-- ============================================================================
-- 0008 · Fundamentals (per-ticker, NOT per-run — slow-changing, daily refresh)
-- ============================================================================

create table if not exists public.ticker_fundamentals (
  ticker                 text primary key references public.tickers(ticker) on delete cascade,
  fetched_at             timestamptz default now(),
  source                 text,
  last_earnings          date,
  next_earnings          date,
  sector                 text,
  industry               text,
  market_cap             numeric,
  shares_out             bigint,
  beta                   numeric,
  week52_high            numeric,
  week52_low             numeric,
  eps_ttm                numeric,
  eps_growth_qoq         numeric,
  pe_ttm                 numeric,
  forward_pe             numeric,
  revenue_ttm            numeric,
  revenue_growth         numeric,
  gross_margin           numeric,
  operating_margin       numeric,
  profit_margin          numeric,
  debt_equity            numeric,
  fcf_ttm                numeric,
  short_float            numeric,
  short_float_fetched    timestamptz,
  raw_json               jsonb
);
create index tf_fetched_idx       on public.ticker_fundamentals(fetched_at desc);
create index tf_next_earnings_idx on public.ticker_fundamentals(next_earnings) where next_earnings is not null;
create index tf_source_idx        on public.ticker_fundamentals(source);

create table if not exists public.fundamentals_extra (
  ticker               text primary key references public.tickers(ticker) on delete cascade,
  fetched_at           timestamptz default now(),
  ev_ebitda            numeric,
  p_fcf                numeric,
  fcf_yield            numeric,
  roa                  numeric,
  roe                  numeric,
  gross_margin         numeric,
  ps_ratio             numeric,
  pb                   numeric,
  institutional_pct    numeric,
  buyback_annual       numeric,
  buyback_yield        numeric,
  dividend_yield       numeric,
  estimate_revision    numeric
);

create table if not exists public.analyst_summary (
  ticker               text primary key references public.tickers(ticker) on delete cascade,
  fetched_at           timestamptz default now(),
  target_mean          numeric,
  target_high          numeric,
  target_low           numeric,
  upside_pct           numeric,
  total_analysts       integer,
  strong_buy           integer default 0,
  buy                  integer default 0,
  hold                 integer default 0,
  sell                 integer default 0,
  strong_sell          integer default 0,
  consensus            text,
  recent_upgrades      integer default 0,
  recent_downgrades    integer default 0,
  upgrades_10d         integer default 0,
  downgrades_10d       integer default 0
);

create table if not exists public.eps_estimates (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  horizon              text not null check (horizon in ('current_q','next_q','current_y','next_y')),
  estimate             numeric,
  est_7d_ago           numeric,
  est_30d_ago          numeric,
  est_60d_ago          numeric,
  revisions_up_7d      integer default 0,
  revisions_down_7d    integer default 0,
  revisions_up_30d     integer default 0,
  revisions_down_30d   integer default 0,
  fetched_at           timestamptz default now(),
  unique (ticker, horizon)
);

create table if not exists public.revenue_estimates (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  horizon              text not null check (horizon in ('current_q','next_q','current_y','next_y')),
  estimate             numeric,
  fetched_at           timestamptz default now(),
  unique (ticker, horizon)
);

create table if not exists public.analyst_actions (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  firm                 text,
  action               text check (action in ('upgrade','downgrade','initiated','reiterated','suspended') or action is null),
  from_rating          text,
  to_rating            text,
  price_target_old     numeric,
  price_target_new     numeric,
  announced_at         timestamptz not null
);
create index analyst_actions_ticker_idx on public.analyst_actions(ticker, announced_at desc);
create index analyst_actions_at_idx     on public.analyst_actions(announced_at desc);

create table if not exists public.fundamentals_pillar (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  score                integer,
  max                  integer,
  bull_drivers         text[],
  bear_risks           text[],
  details_json         jsonb
);
