-- ============================================================================
-- 0002 · Core domain: tickers, runs, regime_history
-- ============================================================================

-- ---------------------------------------------------------------------------
-- tickers · master registry. Slow-changing identity.
-- ---------------------------------------------------------------------------
create table if not exists public.tickers (
  ticker          text primary key,
  name            text,
  sector          text,
  industry        text,
  beta            numeric,
  market_cap      numeric,
  shares_out      bigint,
  is_active       boolean default true,
  in_sp500        boolean default false,
  in_r1000        boolean default false,
  in_r2000        boolean default false,
  is_custom       boolean default false,
  first_seen      timestamptz default now(),
  last_seen       timestamptz default now(),
  updated_at      timestamptz default now()
);
create index tickers_sector_idx   on public.tickers(sector);
create index tickers_industry_idx on public.tickers(industry);
create index tickers_active_idx   on public.tickers(is_active) where is_active;
create index tickers_name_trgm    on public.tickers using gin (name gin_trgm_ops);
create trigger tickers_set_updated before update on public.tickers
  for each row execute function public.tg_set_updated_at();

-- ---------------------------------------------------------------------------
-- config_snapshots · versioned config blobs (every run links to one)
-- ---------------------------------------------------------------------------
create table if not exists public.config_snapshots (
  hash           text primary key,
  saved_at       timestamptz default now(),
  config_json    jsonb not null,
  git_commit     text,
  note           text
);
create index config_snapshots_saved_idx on public.config_snapshots(saved_at desc);

-- ---------------------------------------------------------------------------
-- runs · one row per swing_trade.py invocation
-- ---------------------------------------------------------------------------
create table if not exists public.runs (
  id                          bigserial primary key,
  run_date                    date not null,
  run_time                    timestamptz default now(),
  regime                      text check (regime in ('bull','neutral','bear','panic') or regime is null),
  regime4                     text check (regime4 in ('risk_on_trending','risk_on_choppy','risk_off_trending','panic') or regime4 is null),
  market_phase                text,
  vix                         numeric,
  breadth_pct_above_50d       numeric,
  spy_above_ema50             boolean,
  total_scanned               integer default 0,
  total_passed                integer default 0,
  num_picks                   integer default 0,
  evaluated                   integer default 0,
  config_snapshot_hash        text references public.config_snapshots(hash) on delete set null,
  git_commit                  text,
  duration_sec                numeric,
  data_health_json            jsonb,
  decision_engine_version     text,
  created_at                  timestamptz default now()
);
create unique index runs_run_date_uq on public.runs(run_date);
create index runs_regime4_idx  on public.runs(regime4);
create index runs_run_time_idx on public.runs(run_time desc);

-- ---------------------------------------------------------------------------
-- regime_history · historical regime state with hysteresis tracking
-- ---------------------------------------------------------------------------
create table if not exists public.regime_history (
  id                     bigserial primary key,
  observed_at            timestamptz not null default now(),
  regime3                text check (regime3 in ('bull','neutral','bear','panic') or regime3 is null),
  regime4                text check (regime4 in ('risk_on_trending','risk_on_choppy','risk_off_trending','panic') or regime4 is null),
  flip_confirmed_date    date,
  pending_flip_json      jsonb,
  confidence_json        jsonb,
  vix                    numeric,
  breadth_pct            numeric,
  spy_above_ema50        boolean,
  qqq_above_ema50        boolean
);
create index regime_history_observed_idx on public.regime_history(observed_at desc);
create index regime_history_regime4_idx  on public.regime_history(regime4, observed_at desc);
