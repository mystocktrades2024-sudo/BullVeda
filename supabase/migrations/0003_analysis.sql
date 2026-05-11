-- ============================================================================
-- 0003 · Analysis domain: ticker_analyses (central fact) + narrow attribute tables
-- ============================================================================
-- All sub-domains (technicals, smc, options, etc.) attach via analysis_id FK.
-- ON DELETE CASCADE — a deleted analysis nukes all its leaves.
-- ============================================================================

create table if not exists public.ticker_analyses (
  id                  bigserial primary key,
  run_id              bigint not null references public.runs(id) on delete cascade,
  ticker              text   not null references public.tickers(ticker) on delete restrict,
  analyzed_at         timestamptz default now(),
  verdict             text not null check (verdict in ('BUY','WATCH','SHORT','AVOID')),
  direction           text check (direction in ('long','short','neutral')),
  price               numeric,
  score               integer,
  score_raw           numeric,
  star_rating         integer check (star_rating between 0 and 5),
  setup_family        text,
  setup_type          text,
  catalyst_tier       integer check (catalyst_tier in (1,2,3) or catalyst_tier is null),
  entry_quality       text check (entry_quality in ('FRESH','PULLBACK','VALID','EXTENDED','MISSED') or entry_quality is null),
  entry_subtype       text,
  entry_timing        text,
  hold_period_guide   text,
  conviction_tier     text check (conviction_tier in ('T1','T2','T3','WATCH') or conviction_tier is null),
  reject_reason       text,
  ticker_source       text,
  sector_pct_rank     numeric,
  rs_rank             integer,
  rs_63d_pct          numeric,
  mtf_conflict        boolean,
  mtf_label           text,
  created_at          timestamptz default now(),
  unique (run_id, ticker)
);
create index ta_run_idx       on public.ticker_analyses(run_id);
create index ta_ticker_idx    on public.ticker_analyses(ticker, run_id desc);
create index ta_verdict_idx   on public.ticker_analyses(verdict, run_id desc);
create index ta_setup_idx     on public.ticker_analyses(setup_family, conviction_tier);
create index ta_analyzed_idx  on public.ticker_analyses(analyzed_at desc);

-- ---------------------------------------------------------------------------
-- 1:1 narrow tables (analysis_id PK, CASCADE delete)
-- ---------------------------------------------------------------------------
create table if not exists public.analysis_pricing (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  price                numeric,
  prev_close           numeric,
  day_change_pct       numeric,
  volume               bigint,
  avg_volume_20d       bigint,
  rvol                 numeric,
  atr                  numeric,
  atr_pct              numeric,
  price_tier           text,
  quote_age_s          integer,
  spread_bp            numeric,
  post_market_pct      numeric
);

create table if not exists public.analysis_scoring (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  tech_score           numeric,
  cat_score            numeric,
  rs_score             numeric,
  sm_score             numeric,
  qg_score             numeric,
  raw_total            numeric,
  wr_multiplier        numeric,
  bonus_total          numeric,
  entry_rr_score       numeric,
  final_score          numeric,
  raw_score            integer,
  raw_momentum_score   numeric,
  raw_growth_score     numeric,
  raw_value_score      numeric,
  sizing_multiplier    numeric
);

create table if not exists public.analysis_verdict (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  verdict              text not null,
  reject_reason        text,
  decided_by           text,
  hard_gates_passed    boolean,
  decision_state       text,
  decision_label       text,
  in_cloud             boolean,
  no_edge_zone         boolean,
  momentum_slowdown    boolean,
  size_mult_by_zone    numeric,
  caveats_json         jsonb
);

create table if not exists public.analysis_conviction (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  tier                 integer,
  label                text,
  size_mult            numeric,
  description          text,
  wr_size_adj          text
);

create table if not exists public.analysis_thesis (
  analysis_id                    bigint primary key references public.ticker_analyses(id) on delete cascade,
  thesis_text                    text,
  zone_quality_label             text,
  zone_quality_points            integer,
  zone_quality_reasons           text[],
  setup_quality_label            text,
  setup_quality_trend            integer,
  setup_quality_momentum         integer,
  setup_quality_strength         integer,
  setup_quality_groups_passed    integer
);

-- ---------------------------------------------------------------------------
-- 1:N child tables (analysis_id FK only, own surrogate PK)
-- ---------------------------------------------------------------------------
create table if not exists public.analysis_gates (
  id                bigserial primary key,
  analysis_id       bigint not null references public.ticker_analyses(id) on delete cascade,
  gate_name         text not null,
  gate_order        integer,
  passed            boolean,
  reason            text,
  is_hard           boolean default false,
  meta_json         jsonb
);
create index analysis_gates_aid_idx on public.analysis_gates(analysis_id);

create table if not exists public.analysis_catalysts (
  id                bigserial primary key,
  analysis_id       bigint not null references public.ticker_analyses(id) on delete cascade,
  tag               text not null,
  tier              integer,
  expiry_days       integer,
  is_expired        boolean default false
);
create index analysis_catalysts_aid_idx on public.analysis_catalysts(analysis_id);
create index analysis_catalysts_tag_idx on public.analysis_catalysts(tag);

create table if not exists public.analysis_methodology (
  id                bigserial primary key,
  analysis_id       bigint not null references public.ticker_analyses(id) on delete cascade,
  phase             text check (phase in ('pre','post')),
  check_name        text not null,
  passed            boolean,
  detail            text
);
create index analysis_methodology_aid_idx on public.analysis_methodology(analysis_id);
