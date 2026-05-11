-- ============================================================================
-- 0019 · Row Level Security · enable RLS + default policies for all tables
-- ============================================================================
-- Policy model:
--   service_role  → bypass (default in Postgres for service role)
--   admin         → full read/write everywhere
--   trader        → read all + write portfolio/positions/closed_trades/watchlist
--   quant         → read all (no writes — analytics-only)
--   viewer        → read all (no writes — dashboards-only)
--   anon          → no access
--
-- Helper functions defined in 0001: is_admin(), is_trader_or_admin(),
-- is_authenticated_member(), current_user_role().
-- ============================================================================

-- Enable RLS on every public table. Done in one block via dynamic SQL.
do $$
declare r record;
begin
  for r in
    select tablename from pg_tables
    where schemaname = 'public'
      and tablename not like 'decision_log_%'   -- skip partitions (inherit from parent)
  loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Generic READ policies — all authenticated members can SELECT
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select tablename from pg_tables
    where schemaname = 'public'
      and tablename not like 'decision_log_%'
  loop
    execute format($p$
      drop policy if exists "%1$s_read_member" on public.%1$I;
      create policy "%1$s_read_member" on public.%1$I
        for select using (public.is_authenticated_member());
    $p$, r.tablename);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Admin-only WRITE on most reference / system tables
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
  admin_tables text[] := array[
    'tickers','runs','config_snapshots','regime_history',
    'roles','users','capability_registry','role_capabilities','open_items',
    'ohlcv_daily','ohlcv_intraday'
  ];
begin
  foreach t in array admin_tables loop
    execute format($p$
      drop policy if exists "%1$s_write_admin" on public.%1$I;
      create policy "%1$s_write_admin" on public.%1$I
        for all using (public.is_admin()) with check (public.is_admin());
    $p$, t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Trader+admin WRITE on portfolio / personal-watchlist / trades
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
  trader_tables text[] := array[
    'portfolio_state','positions','closed_trades','equity_curve','equity_audit',
    'monthly_pnl','signal_log','picks_history_runs',
    'watch_triggers','custom_tickers','alert_log','scan_health','gap_events'
  ];
begin
  foreach t in array trader_tables loop
    execute format($p$
      drop policy if exists "%1$s_write_trader" on public.%1$I;
      create policy "%1$s_write_trader" on public.%1$I
        for all using (public.is_trader_or_admin()) with check (public.is_trader_or_admin());
    $p$, t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- ANALYSIS-domain tables: written ONLY by service role (ETL) — no human writes.
-- Apply WITH CHECK (false) to block authenticated UPSERT.
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
  etl_tables text[] := array[
    'ticker_analyses','analysis_pricing','analysis_scoring','analysis_verdict',
    'analysis_conviction','analysis_thesis','analysis_gates','analysis_catalysts',
    'analysis_methodology',
    'trade_plans','trade_plan_entries','trade_plan_risk','trade_plan_exit_rules',
    'trade_plan_zone_confluence','trade_plan_risk_flags',
    'technicals_ema','technicals_momentum','technicals_volatility',
    'technicals_pattern','technicals_trend','technicals_volume_flow',
    'technicals_position','technicals_52w','technicals_relative_strength',
    'technicals_sr_vwap','technicals_loc_volume','volume_profile',
    'technicals_premarket','chart_patterns',
    'smc_summary','smc_order_blocks','smc_fvg_zones','smc_liquidity_sweeps','smc_bos_choch',
    'elliott_wave','elliott_wave_v1','theory_confluence','theory_states',
    'ticker_fundamentals','fundamentals_extra','analyst_summary',
    'eps_estimates','revenue_estimates','analyst_actions','fundamentals_pillar',
    'options_snapshot','options_intelligence','options_kpis','options_per_mode',
    'option_uoa_alerts','option_chain','gamma_exposure',
    'insider_summary','insider_transactions',
    'congressional_summary','congressional_trades',
    'institutional_trend','institutional_holders','sec_filings',
    'news_articles','article_tickers','news_sentiment_snapshot',
    'reddit_wsb_snapshot','stocktwits_snapshot','stocktwits_messages',
    'sentiment_pillar','tv_rating',
    'zacks_data','zacks_rank_history',
    'risk_sizing','tier1_signals','mtf_summary',
    'earnings_events','earnings_predictions','earnings_outcomes','analysis_earnings',
    'analysis_ohlcv_window',
    'decision_log','gates_evaluated'
  ];
begin
  foreach t in array etl_tables loop
    -- block writes from authenticated users (service role bypasses RLS, can still write)
    execute format($p$
      drop policy if exists "%1$s_block_writes" on public.%1$I;
      create policy "%1$s_block_writes" on public.%1$I
        for insert with check (public.is_admin());
      drop policy if exists "%1$s_block_updates" on public.%1$I;
      create policy "%1$s_block_updates" on public.%1$I
        for update using (public.is_admin()) with check (public.is_admin());
      drop policy if exists "%1$s_block_deletes" on public.%1$I;
      create policy "%1$s_block_deletes" on public.%1$I
        for delete using (public.is_admin());
    $p$, t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Users table: a user can read/update their own row; admins can do anything.
-- Override the generic "read_member" policy.
-- ---------------------------------------------------------------------------
drop policy if exists "users_read_member" on public.users;
create policy "users_read_self_or_admin" on public.users
  for select using (id = auth.uid() or public.is_admin());

drop policy if exists "users_write_admin" on public.users;
create policy "users_write_admin" on public.users
  for all using (public.is_admin()) with check (public.is_admin());

create policy "users_update_self" on public.users
  for update using (id = auth.uid()) with check (id = auth.uid());
