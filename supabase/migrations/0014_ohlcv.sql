-- ============================================================================
-- 0014 · OHLCV · price bars (EODHD primary)
-- ============================================================================

create table if not exists public.ohlcv_daily (
  ticker               text not null references public.tickers(ticker) on delete cascade,
  bar_date             date not null,
  open                 numeric,
  high                 numeric,
  low                  numeric,
  close                numeric,
  adjusted_close       numeric,
  volume               bigint,
  source               text default 'eodhd',
  primary key (ticker, bar_date)
);
-- BRIN works well for monotonically-increasing time-series + tight clusters per ticker
create index ohlcv_daily_date_brin on public.ohlcv_daily using brin (bar_date);
create index ohlcv_daily_ticker_date_idx on public.ohlcv_daily(ticker, bar_date desc);

create table if not exists public.ohlcv_intraday (
  ticker               text not null references public.tickers(ticker) on delete cascade,
  bar_time             timestamptz not null,
  interval             text not null check (interval in ('1m','5m','15m','30m','1h','4h')),
  open                 numeric,
  high                 numeric,
  low                  numeric,
  close                numeric,
  volume               bigint,
  primary key (ticker, bar_time, interval)
);
create index ohlcv_intraday_time_brin on public.ohlcv_intraday using brin (bar_time);

-- Pre-cached 90-bar slice attached to analysis — speeds up dashboard chart render
create table if not exists public.analysis_ohlcv_window (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  bars_json            jsonb,
  bar_count            integer,
  first_date           date,
  last_date            date
);
