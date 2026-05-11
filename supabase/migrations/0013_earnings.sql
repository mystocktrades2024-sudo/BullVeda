-- ============================================================================
-- 0013 · Earnings · calendar → predictions → outcomes (FK chain restored)
-- ============================================================================
-- Today's bug: earnings_outcomes.jsonl has no FK back to predictions. Fixed
-- here via canonical earnings_events that both predictions and outcomes
-- reference.
-- ============================================================================

create table if not exists public.earnings_events (
  id                       bigserial primary key,
  ticker                   text not null references public.tickers(ticker) on delete cascade,
  report_date              date not null,
  before_after_market      text check (before_after_market in ('BeforeMarket','AfterMarket','During','') or before_after_market is null),
  currency                 text default 'USD',
  fiscal_quarter           text check (fiscal_quarter in ('Q1','Q2','Q3','Q4') or fiscal_quarter is null),
  fiscal_year              integer,
  created_at               timestamptz default now(),
  unique (ticker, report_date)
);
create index earnings_events_date_idx   on public.earnings_events(report_date);
create index earnings_events_ticker_idx on public.earnings_events(ticker, report_date desc);

create table if not exists public.earnings_predictions (
  id                       bigserial primary key,
  earnings_event_id        bigint not null references public.earnings_events(id) on delete cascade,
  predicted_at             timestamptz default now(),
  days_to_earnings         integer,
  beat_score               numeric,
  tier                     text check (tier in ('STRONG','SOLID','MODERATE','WEAK') or tier is null),
  historical_pts           numeric,
  historical_rate          numeric,
  historical_n_quarters    integer,
  runup_10d_pts            numeric,
  runup_10d_value          numeric,
  vol_accum_pts            numeric,
  analyst_upside_pts       numeric,
  analyst_upside_pct       numeric,
  options_pts              numeric,
  options_put_call         numeric,
  options_current_iv       numeric,
  unique (earnings_event_id, predicted_at)
);
create index earnings_pred_tier_idx on public.earnings_predictions(tier);

create table if not exists public.earnings_outcomes (
  id                       bigserial primary key,
  earnings_event_id        bigint not null references public.earnings_events(id) on delete cascade,
  estimate                 numeric,
  actual                   numeric,
  surprise_pct             numeric,
  beat                     text check (beat in ('BEAT','MISS','INLINE') or beat is null),
  reaction_1d_pct          numeric,
  reaction_5d_pct          numeric,
  captured_at              timestamptz default now(),
  unique (earnings_event_id)
);
create index earnings_outcomes_beat_idx on public.earnings_outcomes(beat);

create table if not exists public.analysis_earnings (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  earnings_event_id        bigint references public.earnings_events(id) on delete set null,
  days_to_earnings         integer,
  earnings_risk            text,
  earnings_warning         text
);
