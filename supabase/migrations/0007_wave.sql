-- ============================================================================
-- 0007 · Elliott Wave + multi-theory confluence
-- ============================================================================

create table if not exists public.elliott_wave (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  wave_number          integer,
  wave_label           text,
  trend                text,
  confidence           text check (confidence in ('high','medium','low') or confidence is null),
  swing_base           numeric,
  swing_top            numeric,
  bonus                integer,
  description          text,
  fib_levels_json      jsonb,
  nearest_fib          text[]
);

create table if not exists public.elliott_wave_v1 (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  ew_state             text,
  ew_bullish           boolean,
  ew_bearish           boolean,
  ew_score             numeric,
  meta_json            jsonb
);

create table if not exists public.theory_confluence (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  direction            text check (direction in ('BULL','BEAR','NEUTRAL') or direction is null),
  bull_count           integer,
  bear_count           integer,
  min_required         integer,
  hard_gate_pass       boolean,
  evidence_summary     text,
  eligible_theories    text[]
);

create table if not exists public.theory_states (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  theory               text check (theory in ('dow','wyckoff','elliott','gann')),
  state                text,
  bull_aligned         boolean,
  bear_aligned         boolean,
  detail_json          jsonb,
  unique (analysis_id, theory)
);
create index theory_states_aid_idx on public.theory_states(analysis_id);
