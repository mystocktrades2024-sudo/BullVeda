-- ============================================================================
-- 0018 · Cross-table indexes + jsonb GINs for queryable nested data
-- ============================================================================
-- Most per-table indexes were defined inline; this file adds higher-cardinality
-- or jsonb-search indexes that benefit dashboards / analytics.
-- ============================================================================

-- ticker_analyses · multi-column hot paths for dashboard
create index if not exists ta_run_verdict_idx
  on public.ticker_analyses(run_id, verdict);

create index if not exists ta_ticker_verdict_idx
  on public.ticker_analyses(ticker, verdict, run_id desc);

create index if not exists ta_conviction_idx
  on public.ticker_analyses(conviction_tier, score desc)
  where conviction_tier in ('T1','T2','T3');

-- analysis_verdict · find all BUYs in a regime
create index if not exists av_hardgate_idx
  on public.analysis_verdict(hard_gates_passed)
  where hard_gates_passed;

-- closed_trades · perf-tab aggregates
create index if not exists ct_win_setup_regime_idx
  on public.closed_trades(setup_type, regime, win);

-- options_kpis · UOA scanner
create index if not exists okpis_uoa_idx
  on public.options_kpis(uoa_calls, uoa_puts)
  where uoa_calls or uoa_puts;

-- earnings_predictions · "show me upcoming STRONG"
create index if not exists ep_tier_days_idx
  on public.earnings_predictions(tier, days_to_earnings)
  where tier in ('STRONG','SOLID');

-- decision_log · "all AVOIDS for this ticker last 30d"
create index if not exists dl_ticker_verdict_idx
  on public.decision_log(ticker, verdict, observed_at desc);

-- ---------------------------------------------------------------------------
-- jsonb GIN indexes — only on fields we actually query into
-- ---------------------------------------------------------------------------
create index if not exists runs_data_health_gin
  on public.runs using gin (data_health_json jsonb_path_ops);

create index if not exists analysis_gates_meta_gin
  on public.analysis_gates using gin (meta_json jsonb_path_ops);

create index if not exists decision_log_gates_hit_gin
  on public.decision_log using gin (gates_hit_json jsonb_path_ops);

create index if not exists config_snapshots_gin
  on public.config_snapshots using gin (config_json jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- BRIN indexes on append-only time-series (cheap, tiny, good enough)
-- ---------------------------------------------------------------------------
create index if not exists signal_log_observed_brin
  on public.signal_log using brin (observed_at);

create index if not exists closed_trades_exit_brin
  on public.closed_trades using brin (exit_date);

create index if not exists equity_curve_observed_brin
  on public.equity_curve using brin (observed_at);

-- ---------------------------------------------------------------------------
-- pg_trgm for fuzzy ticker / name search
-- ---------------------------------------------------------------------------
create index if not exists tickers_ticker_trgm
  on public.tickers using gin (ticker gin_trgm_ops);
