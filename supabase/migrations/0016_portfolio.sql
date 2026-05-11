-- ============================================================================
-- 0016 · Portfolio · positions · trades · equity · alerts
-- ============================================================================
-- Lift-and-shift of swingtrade.db tables, with FK back to ticker_analyses
-- where applicable.
-- ============================================================================

-- Singleton: enforce single row via CHECK
create table if not exists public.portfolio_state (
  id                   integer primary key check (id = 1),
  equity               numeric not null default 5000,
  cash                 numeric not null default 5000,
  margin_reserved      numeric not null default 0,
  starting_equity      numeric,
  buying_power         numeric,
  alpaca_account       text,
  last_alpaca_sync     timestamptz,
  last_reset           date,
  updated_at           timestamptz default now()
);
create trigger portfolio_state_updated before update on public.portfolio_state
  for each row execute function public.tg_set_updated_at();

create table if not exists public.positions (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete restrict,
  direction            text check (direction in ('long','short')),
  entry_date           date,
  entry_price          numeric not null,
  shares               integer not null,
  position_size        numeric,
  stop                 numeric,
  trail_stop           numeric,
  trail_active         boolean default false,
  highest_price        numeric,
  current_price        numeric,
  target1              numeric,
  target2              numeric,
  setup_type           text,
  allocation_pct       numeric,
  entry_regime         text,
  entry_analysis_id    bigint references public.ticker_analyses(id) on delete set null,
  alpaca_order_id      text,
  notes                text,
  created_at           timestamptz default now(),
  updated_at           timestamptz default now()
);
create index positions_ticker_idx on public.positions(ticker);
create trigger positions_set_updated before update on public.positions
  for each row execute function public.tg_set_updated_at();

create table if not exists public.closed_trades (
  id                       bigserial primary key,
  ticker                   text not null references public.tickers(ticker) on delete restrict,
  direction                text check (direction in ('long','short')),
  entry_date               date,
  exit_date                date,
  entry_price              numeric,
  exit_price               numeric,
  shares                   integer,
  pnl_dollars              numeric,
  pnl_pct                  numeric,
  win                      boolean,
  setup_type               text,
  exit_reason              text,
  hold_days                integer,
  mae                      numeric,
  mfe                      numeric,
  regime                   text,
  tech_score               numeric,
  cat_score                numeric,
  rs_score                 numeric,
  sm_score                 numeric,
  qg_score                 numeric,
  raw_total                numeric,
  wr_multiplier            numeric,
  bonus_total              numeric,
  entry_analysis_id        bigint references public.ticker_analyses(id) on delete set null,
  alpaca_buy_order_id      text,
  alpaca_sell_order_id     text,
  raw_json                 jsonb,
  created_at               timestamptz default now()
);
create index closed_trades_ticker_idx on public.closed_trades(ticker, exit_date desc);
create index closed_trades_exit_idx   on public.closed_trades(exit_date desc);
create index closed_trades_setup_idx  on public.closed_trades(setup_type, regime);

create table if not exists public.equity_curve (
  id                   bigserial primary key,
  observed_at          date not null unique,
  equity               numeric not null,
  cash                 numeric,
  margin_reserved      numeric,
  open_positions       integer
);
create index equity_curve_observed_idx on public.equity_curve(observed_at desc);

create table if not exists public.equity_audit (
  id                   bigserial primary key,
  occurred_at          timestamptz default now(),
  event_type           text,
  delta                numeric,
  balance_after        numeric,
  note                 text
);
create index equity_audit_occurred_idx on public.equity_audit(occurred_at desc);

create table if not exists public.monthly_pnl (
  year_month           text primary key,
  pnl                  numeric not null,
  trade_count          integer,
  win_rate             numeric
);

create table if not exists public.signal_log (
  id                   bigserial primary key,
  observed_at          date not null,
  ticker               text not null references public.tickers(ticker) on delete restrict,
  strategy             text,
  verdict              text check (verdict in ('BUY','WATCH','SHORT') or verdict is null),
  direction            text check (direction in ('long','short') or direction is null),
  entry_price          numeric,
  stop                 numeric,
  target1              numeric,
  target2              numeric,
  rr                   numeric,
  stars                integer,
  score                numeric,
  rs_rank              integer,
  status               text check (status in ('OPEN','CLOSED') or status is null) default 'OPEN',
  day5_price           numeric,
  day10_price          numeric,
  actual_pnl_pct       numeric,
  result               text,
  mae_pct              numeric,
  mfe_pct              numeric,
  outcome_5d           text,
  outcome_10d          text,
  tech_score           numeric,
  cat_score            numeric,
  rs_score             numeric,
  sm_score             numeric,
  qg_score             numeric,
  raw_total            numeric,
  wr_multiplier        numeric,
  bonus_total          numeric,
  analysis_id          bigint references public.ticker_analyses(id) on delete set null,
  raw_json             jsonb
);
create index signal_log_ticker_idx     on public.signal_log(ticker, observed_at desc);
create index signal_log_observed_idx   on public.signal_log(observed_at desc);
create index signal_log_status_idx     on public.signal_log(status);

create table if not exists public.picks_history_runs (
  id                   bigserial primary key,
  run_id               bigint references public.runs(id) on delete set null,
  ticker               text not null references public.tickers(ticker) on delete restrict,
  direction            text,
  verdict              text,
  score                numeric,
  setup_type           text,
  entry_price          numeric,
  rr_ratio             numeric,
  bear_score           numeric,
  outcome_status       text,
  outcome_5d_pct       numeric,
  outcome_10d_pct      numeric,
  created_at           timestamptz default now()
);
create index picks_hist_run_idx    on public.picks_history_runs(run_id);
create index picks_hist_ticker_idx on public.picks_history_runs(ticker, run_id desc);

create table if not exists public.watch_triggers (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  condition            text not null,
  threshold            numeric,
  created_at           timestamptz default now(),
  fired_at             timestamptz,
  is_active            boolean default true
);
create index watch_triggers_active_idx on public.watch_triggers(ticker) where is_active;

create table if not exists public.custom_tickers (
  ticker               text primary key references public.tickers(ticker) on delete cascade,
  added_at             timestamptz default now(),
  added_by             uuid,
  note                 text
);

create table if not exists public.alert_log (
  id                   bigserial primary key,
  sent_at              timestamptz default now(),
  channel              text check (channel in ('slack','email','mac','sms') or channel is null),
  ticker               text,
  subject              text,
  body                 text,
  status               text check (status in ('queued','sent','failed') or status is null)
);
create index alert_log_sent_idx on public.alert_log(sent_at desc);

create table if not exists public.scan_health (
  id                       bigserial primary key,
  run_id                   bigint references public.runs(id) on delete cascade,
  fill_rate_pct            numeric,
  eodhd_429_count          integer default 0,
  yfinance_fallback_count  integer default 0,
  aborted                  boolean default false
);
create index scan_health_run_idx on public.scan_health(run_id);

create table if not exists public.gap_events (
  id                   bigserial primary key,
  observed_at          date not null,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  gap_pct              numeric,
  direction            text check (direction in ('up','down') or direction is null)
);
create index gap_events_ticker_idx on public.gap_events(ticker, observed_at desc);
