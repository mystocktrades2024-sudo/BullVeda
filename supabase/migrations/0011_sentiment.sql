-- ============================================================================
-- 0011 · Sentiment · news · social
-- ============================================================================

-- Master article table — many-to-many with tickers
create table if not exists public.news_articles (
  id                   bigserial primary key,
  external_id          text,
  title                text,
  summary              text,
  url                  text,
  source               text,
  provider             text check (provider in ('eodhd','yahoo','polygon') or provider is null),
  published_at         timestamptz,
  sentiment_score      numeric,
  sentiment_label      text,
  created_at           timestamptz default now(),
  unique (provider, external_id)
);
create index news_articles_pub_idx    on public.news_articles(published_at desc);
create index news_articles_source_idx on public.news_articles(source);
create index news_articles_title_trgm on public.news_articles using gin (title gin_trgm_ops);

create table if not exists public.article_tickers (
  article_id           bigint not null references public.news_articles(id) on delete cascade,
  ticker               text not null references public.tickers(ticker) on delete cascade,
  mention_type         text check (mention_type in ('primary','secondary') or mention_type is null),
  primary key (article_id, ticker)
);
create index article_tickers_ticker_idx on public.article_tickers(ticker);

create table if not exists public.news_sentiment_snapshot (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  score                integer,
  max                  integer,
  momentum             text check (momentum in ('bullish','neutral','bearish') or momentum is null),
  breaking             boolean default false,
  article_count        integer default 0,
  source_score         numeric,
  details              text
);

create table if not exists public.reddit_wsb_snapshot (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  mentions             integer default 0,
  avg_score            numeric,
  sentiment            text check (sentiment in ('bullish','neutral','bearish') or sentiment is null)
);

create table if not exists public.stocktwits_snapshot (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  bullish              integer default 0,
  bearish              integer default 0,
  neutral              integer default 0,
  bull_pct             numeric,
  message_volume       integer default 0,
  watchlist_count      integer,
  trending             boolean default false
);

create table if not exists public.stocktwits_messages (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  message_id           text,
  body                 text,
  sentiment            text,
  created_at           timestamptz
);
create index stocktwits_msg_aid_idx on public.stocktwits_messages(analysis_id);

create table if not exists public.sentiment_pillar (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  score                integer,
  max                  integer,
  details_json         jsonb
);

create table if not exists public.tv_rating (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  overall              text,
  ma                   text,
  osc                  text,
  buy_count            integer,
  sell_count           integer,
  neutral_count        integer
);
