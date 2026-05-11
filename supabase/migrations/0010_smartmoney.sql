-- ============================================================================
-- 0010 · Smart Money · insiders · congressional · institutional · SEC filings
-- ============================================================================

create table if not exists public.insider_summary (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  buys                 integer default 0,
  sells                integer default 0,
  ceo_buy              boolean default false,
  cfo_buy              boolean default false,
  sentiment            text check (sentiment in ('bullish','neutral','bearish') or sentiment is null),
  days_since_last      integer,
  max_single_buy       bigint,
  total_buy_value      bigint
);

-- insider_transactions is a MASTER ticker-level table (not analysis-scoped).
-- Many trades per ticker over time. Source: SEC EDGAR + EODHD.
create table if not exists public.insider_transactions (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  filer_name           text,
  filer_role           text,
  transaction_type     text check (transaction_type in ('P','S','A','D','M','G','F','I','O','X') or transaction_type is null),
  shares               bigint,
  price                numeric,
  value                numeric,
  filed_at             timestamptz,
  transacted_at        date,
  source               text check (source in ('sec_edgar','eodhd') or source is null),
  external_id          text,
  unique (source, external_id)
);
create index insider_tx_ticker_idx     on public.insider_transactions(ticker, filed_at desc);
create index insider_tx_filed_idx      on public.insider_transactions(filed_at desc);
create index insider_tx_transacted_idx on public.insider_transactions(transacted_at desc);

create table if not exists public.congressional_summary (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  purchases            integer default 0,
  sales                integer default 0,
  net                  text check (net in ('bullish','neutral','bearish') or net is null),
  latest_member        text,
  source               text,
  source_unavailable   boolean default false
);

create table if not exists public.congressional_trades (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  member               text,
  party                text,
  chamber              text check (chamber in ('House','Senate') or chamber is null),
  state                text,
  transaction_type     text,
  amount_range         text,
  transacted_at        date,
  reported_at          date,
  source               text,
  external_id          text,
  unique (source, external_id)
);
create index cong_trades_ticker_idx   on public.congressional_trades(ticker, reported_at desc);
create index cong_trades_reported_idx on public.congressional_trades(reported_at desc);

create table if not exists public.institutional_trend (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  inst_pct             numeric,
  inst_trend           text check (inst_trend in ('increasing','decreasing','stable') or inst_trend is null),
  net_change_pct       numeric,
  total_holders        integer
);

create table if not exists public.institutional_holders (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  holder_name          text,
  shares               bigint,
  pct_of_float         numeric,
  change_qoq           bigint,
  as_of_date           date,
  unique (ticker, holder_name, as_of_date)
);
create index inst_holders_ticker_idx on public.institutional_holders(ticker, as_of_date desc);

create table if not exists public.sec_filings (
  id                   bigserial primary key,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  filing_type          text,
  filed_at             timestamptz,
  has_material_event   boolean default false,
  catalyst_signal      text,
  url                  text,
  summary              text,
  external_id          text,
  unique (external_id)
);
create index sec_filings_ticker_idx on public.sec_filings(ticker, filed_at desc);
create index sec_filings_filed_idx  on public.sec_filings(filed_at desc);
