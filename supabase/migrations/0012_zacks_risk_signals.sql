-- ============================================================================
-- 0012 · Zacks + Risk sizing + Tier-1 signals + MTF
-- ============================================================================

create table if not exists public.zacks_data (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  grade_growth         text check (grade_growth in ('A','B','C','D','F') or grade_growth is null),
  grade_momentum       text check (grade_momentum in ('A','B','C','D','F') or grade_momentum is null),
  grade_value          text check (grade_value    in ('A','B','C','D','F') or grade_value    is null),
  grade_vgm            text check (grade_vgm      in ('A','B','C','D','F') or grade_vgm      is null),
  vgm_verdict          text,
  zacks_rank1          boolean default false,
  zacks_sell           boolean default false,
  gmail_bonus_pts      integer default 0,
  gmail_signal_count   integer default 0,
  gmail_trade_alert    text,
  rank_from_email      text
);

create table if not exists public.zacks_rank_history (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  observed_at          timestamptz default now(),
  rank                 integer check (rank between 1 and 5),
  grade_vgm            text check (grade_vgm in ('A','B','C','D','F') or grade_vgm is null)
);
create index zacks_history_ticker_idx on public.zacks_rank_history(ticker, observed_at desc);

-- ---------------------------------------------------------------------------
-- Risk sizing — full Kelly stack
-- ---------------------------------------------------------------------------
create table if not exists public.risk_sizing (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  kelly_pct                numeric,
  half_kelly_pct           numeric,
  final_alloc_pct          numeric,
  risk_per_trade_pct       numeric,
  dollar_risk              numeric,
  position_value           numeric,
  suggested_shares         integer,
  regime_mult              numeric,
  regime_max_size_pct      numeric,
  effective_regime_cap     numeric,
  vix_mult                 numeric,
  drawdown_mult            numeric,
  drawdown_pct             numeric,
  earnings_mult            numeric,
  earnings_days            integer,
  var_floor_mult           numeric,
  cvar_975_pct             numeric,
  live_stats_used          boolean,
  live_win_rate            numeric,
  stack_note               text,
  mc_p_profit              numeric,
  sizing_multiplier        numeric
);

-- ---------------------------------------------------------------------------
-- Tier-1 signals
-- ---------------------------------------------------------------------------
create table if not exists public.tier1_signals (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  total_points         integer default 0,
  active_count         integer default 0,
  narratives           text[],
  insider_cluster      boolean default false,
  nr7_inside_day       boolean default false,
  volume_dryup         boolean default false,
  obv_divergence       boolean default false,
  mean_reversion       boolean default false,
  beat_and_raise       boolean default false,
  apply_to_score       boolean default false
);

-- ---------------------------------------------------------------------------
-- Multi-timeframe
-- ---------------------------------------------------------------------------
create table if not exists public.mtf_summary (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  mtf_conflict         boolean,
  mtf_label            text,
  lt_score             numeric,
  lt_verdict           text,
  lt_gate_pass         boolean,
  mt_score             numeric,
  mt_verdict           text,
  mt_gate_status       text,
  tf_4h_json           jsonb,
  weekly_aligned       boolean
);
