-- ============================================================================
-- 0005 · Technicals domain (14 tables, one per indicator family)
-- ============================================================================
-- All 1:1 with ticker_analyses except chart_patterns (1:N).
-- ============================================================================

create table if not exists public.technicals_ema (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  ema5                 numeric,
  ema8                 numeric,
  ema13                numeric,
  ema20                numeric,
  ema21                numeric,
  ema34                numeric,
  ema50                numeric,
  ema55                numeric,
  ema100               numeric,
  ema200               numeric,
  weekly_ema8          numeric,
  weekly_ema21         numeric,
  weekly_ema_bullish   boolean,
  weekly_ema_bearish   boolean,
  ema5_slope_up        boolean,
  ema13_slope_up       boolean,
  ema5_above_13        boolean,
  ema5_cross_bull      boolean,
  ema5_cross_bear      boolean,
  price_above_ema5     boolean,
  emas_above           integer,
  ema_signal           text
);

create table if not exists public.technicals_momentum (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  rsi                  numeric,
  macd_signal          text,
  macd_bullish         boolean,
  stoch_rsi_k          numeric,
  stoch_rsi_d          numeric,
  stoch_k_above_d      boolean,
  stoch_overbought     boolean,
  stoch_oversold       boolean,
  mfi                  numeric,
  mfi_bullish          boolean,
  cmf                  numeric,
  cmf_accumulating     boolean,
  adx                  numeric,
  adx_plus_di          numeric,
  adx_minus_di         numeric,
  adx_trending         boolean
);

create table if not exists public.technicals_volatility (
  analysis_id                       bigint primary key references public.ticker_analyses(id) on delete cascade,
  atr                               numeric,
  atr_pct                           numeric,
  bb_pct_b                          numeric,
  squeeze_on                        boolean,
  squeeze_fired                     boolean,
  squeeze_direction                 text,
  bars_in_squeeze                   integer,
  enhanced_squeeze_label            text,
  enhanced_squeeze_probability      integer,
  enh_short_float_pts               integer,
  enh_days_to_cover_pts             integer,
  enh_momentum_pts                  integer,
  enh_si_trend_pts                  integer
);

create table if not exists public.technicals_pattern (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  vcp                  boolean,
  near_vcp             boolean,
  vcp_pivot            numeric,
  vcp_contractions     integer,
  vcp_tightness        numeric,
  vcp_vol_dry_up       boolean,
  pocket_pivot         boolean,
  holy_grail_setup     boolean,
  stage2               boolean,
  fractal_high         numeric,
  fractal_low          numeric,
  fractal_highs        numeric[],
  fractal_lows         numeric[],
  fractal_signal       text,
  candle_patterns      text[]
);

create table if not exists public.technicals_trend (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  golden_cross         boolean,
  death_cross          boolean,
  supertrend_bull      boolean,
  supertrend_value     numeric,
  supertrend_flips     integer,
  sar                  numeric,
  sar_bullish          boolean,
  sar_flipped          boolean,
  bullish_stack        boolean,
  fib_ribbon           text,
  fib_ribbon_spread    numeric,
  fib_ribbon_state     text,
  trend_direction      text,
  trend_age_bars       integer,
  trend_age_label      text
);

create table if not exists public.technicals_volume_flow (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  obv_rising           boolean,
  power_days           integer,
  power_trend          boolean,
  rvol                 numeric,
  breakout_vol_ratio   numeric,
  pp_vol_ratio         numeric
);

create table if not exists public.technicals_position (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  above_200sma         boolean,
  above_50ema          boolean,
  above_20ema          boolean,
  price_above_ema5     boolean,
  prev_close           numeric,
  day_change_pct       numeric
);

create table if not exists public.technicals_52w (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  high_52w             numeric,
  low_52w              numeric,
  near_52w_high        boolean,
  near_52w_low         boolean,
  at_52w_breakout      boolean,
  pct_from_52w_high    numeric
);

create table if not exists public.technicals_relative_strength (
  analysis_id              bigint primary key references public.ticker_analyses(id) on delete cascade,
  rs_rank                  integer,
  rs_63d_pct               numeric,
  sector_rank              integer,
  sector_etf               text,
  sector_vs_spy_pct        numeric,
  outperforming_sector     boolean,
  outperforming_spy        boolean,
  sector_outperforming     boolean,
  sector_underperform      boolean,
  sector_rotation_score    integer,
  sector_rotation_label    text,
  sector_rotation_trend    text
);

create table if not exists public.technicals_sr_vwap (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  support              numeric,
  resistance           numeric,
  vwap                 numeric,
  avwap_swing_low      numeric,
  above_vwap           boolean,
  above_avwap          boolean
);

create table if not exists public.technicals_loc_volume (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  at_resistance        boolean,
  at_support           boolean,
  loc_vol_label        text,
  loc_vol_score        integer
);

create table if not exists public.volume_profile (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  poc                  numeric,
  vah                  numeric,
  val                  numeric,
  hvn_levels           numeric[],
  lvn_levels           numeric[],
  support_vpn          numeric,
  resistance_vpn       numeric
);

create table if not exists public.technicals_premarket (
  analysis_id          bigint primary key references public.ticker_analyses(id) on delete cascade,
  premarket_vol        bigint,
  avg_premarket_vol    bigint,
  vol_ratio            numeric,
  premarket_pct        numeric,
  unusual              boolean
);

create table if not exists public.chart_patterns (
  id                   bigserial primary key,
  analysis_id          bigint not null references public.ticker_analyses(id) on delete cascade,
  pattern              text,
  is_primary           boolean default false,
  confidence           numeric,
  details_json         jsonb
);
create index chart_patterns_aid_idx on public.chart_patterns(analysis_id);
