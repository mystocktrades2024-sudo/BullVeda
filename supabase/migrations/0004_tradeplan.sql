-- ============================================================================
-- 0004 · Trade plan domain (K6 canonical_trade_plan)
-- ============================================================================

create table if not exists public.trade_plans (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  schema_version           integer default 1,
  direction                text,
  verdict                  text,
  conviction_tier          text,
  hold_period_days         integer,
  shares                   integer,
  position_size_pct        numeric,
  allocation_pct           numeric,
  stop                     numeric,
  target1                  numeric,
  target2                  numeric,
  risk_per_share           numeric,
  rr_ratio                 numeric,
  mechanism_hypothesis     text,
  decided_at               timestamptz default now(),
  git_commit               text,
  config_snapshot_hash     text references public.config_snapshots(hash) on delete set null
);

create table if not exists public.trade_plan_entries (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  entry_low                numeric,
  entry_mid                numeric,
  entry_high               numeric,
  shallow_zone_low         numeric,
  shallow_zone_high        numeric,
  primary_zone_low         numeric,
  primary_zone_high        numeric,
  deep_zone_low            numeric,
  deep_zone_high           numeric,
  fib_382                  numeric,
  fib_500                  numeric,
  fib_618                  numeric,
  ichimoku_zone_top        numeric,
  ichimoku_zone_bottom     numeric,
  expected_pullback        text
);

create table if not exists public.trade_plan_risk (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  max_loss_pct             numeric,
  max_loss_dollars         numeric,
  rr_ratio                 numeric,
  beta_adjusted_size_pct   numeric,
  beta_adj_multiplier      numeric,
  beta_adj_note            text,
  cvar_975_pct             numeric,
  drawdown_haircut_pct     numeric
);

create table if not exists public.trade_plan_exit_rules (
  id                       bigserial primary key,
  analysis_id              bigint not null references public.ticker_analyses(id) on delete cascade,
  rule_order               integer,
  rule_text                text,
  exit_family              text,
  trail_activate_pct       numeric,
  trail_atr_mult           numeric,
  partial_at_t1_pct        numeric,
  time_stop_days           integer
);
create index tp_exit_rules_aid_idx on public.trade_plan_exit_rules(analysis_id);

create table if not exists public.trade_plan_zone_confluence (
  id                       bigserial primary key,
  analysis_id              bigint not null references public.ticker_analyses(id) on delete cascade,
  factor                   text,
  price_level              numeric
);
create index tp_zone_aid_idx on public.trade_plan_zone_confluence(analysis_id);

create table if not exists public.trade_plan_risk_flags (
  id                       bigserial primary key,
  analysis_id              bigint not null references public.ticker_analyses(id) on delete cascade,
  flag_code                text,
  severity                 text check (severity in ('low','medium','high','critical') or severity is null),
  message                  text
);
create index tp_riskflag_aid_idx on public.trade_plan_risk_flags(analysis_id);
