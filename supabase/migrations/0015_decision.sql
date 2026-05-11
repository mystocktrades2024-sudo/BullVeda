-- ============================================================================
-- 0015 · Decision log · gates evaluated · audit trail
-- ============================================================================
-- decision_log holds EVERY verdict on EVERY scanned ticker (incl AVOID).
-- Today it's 33MB JSONL. Partitioned monthly here for retention + perf.
-- ============================================================================

create table if not exists public.decision_log (
  id                   bigserial,
  run_id               bigint not null references public.runs(id) on delete cascade,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  observed_at          date not null,
  verdict              text not null check (verdict in ('BUY','WATCH','SHORT','AVOID')),
  reason               text,
  score                numeric,
  rs_rank              integer,
  setup_type           text,
  direction            text,
  regime4              text,
  profile              text,
  gates_hit_json       jsonb,
  score_breakdown_json jsonb,
  has_catalyst         boolean,
  weekly_bull          boolean,
  rr_ratio             numeric,
  entry_price          numeric,
  primary key (observed_at, id)
) partition by range (observed_at);

-- Default partition (covers anything not in a specific monthly partition)
create table if not exists public.decision_log_default
  partition of public.decision_log default;

-- Auto-create monthly partitions for the current + next 6 months.
-- Call this periodically (or wire to a cron). Idempotent.
create or replace function public.ensure_decision_log_partitions(months_ahead int default 6)
returns void language plpgsql as $$
declare
  m   int;
  st  date;
  en  date;
  nm  text;
begin
  for m in 0..months_ahead loop
    st := date_trunc('month', current_date + (m || ' months')::interval)::date;
    en := (st + interval '1 month')::date;
    nm := 'decision_log_' || to_char(st, 'YYYY_MM');
    execute format(
      'create table if not exists public.%I partition of public.decision_log for values from (%L) to (%L)',
      nm, st, en
    );
  end loop;
end $$;

select public.ensure_decision_log_partitions(6);

create index decision_log_run_idx     on public.decision_log(run_id);
create index decision_log_ticker_idx  on public.decision_log(ticker, observed_at desc);
create index decision_log_verdict_idx on public.decision_log(verdict, observed_at desc);

-- ---------------------------------------------------------------------------
-- gates_evaluated · 8-gate cascade per analysis (decision_engine output)
-- ---------------------------------------------------------------------------
create table if not exists public.gates_evaluated (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  gate_code            text,
  gate_name            text,
  cascade_order        integer,
  passed               boolean,
  is_hard              boolean default false,
  reason               text,
  evaluator            text
);
create index gates_evaluated_aid_idx on public.gates_evaluated(analysis_id);
