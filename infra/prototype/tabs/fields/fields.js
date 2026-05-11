// tabs/fields/fields.js — wide tabular field inventory.
//
// Layout: rows = tickers, columns = fields. Anchor columns (Ticker | Date |
// Scan Time) always shown. Category chips toggle column groups. Actionable
// columns shown by default; click chips to add Smart-Money Flow / Elliott
// Wave / etc. Search filters tickers by symbol. Export CSV writes the
// currently visible matrix.
//
// CapStudio modular loader 2026-05-10.

import { getData, getTickers, $ } from '../../core/shared.js';

// ── Helpers ────────────────────────────────────────────────────────────
function _get(o, path) {
  const parts = path.split('.');
  let v = o;
  for (const p of parts) { if (v == null) return undefined; v = v[p]; }
  return v;
}
function _val(t, ...paths) {
  for (const p of paths) {
    const v = _get(t, p);
    if (v !== null && v !== undefined && v !== '') return v;
  }
  return undefined;
}
function _fmt(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(Math.abs(v) < 1 ? 4 : 2);
  }
  if (typeof v === 'boolean') return v ? '✓' : '✗';
  if (Array.isArray(v)) {
    if (v.length === 0) return '[]';
    if (v.length <= 4 && v.every(x => typeof x === 'string' || typeof x === 'number')) {
      return v.join(', ');
    }
    return `[${v.length}]`;
  }
  if (typeof v === 'object') {
    const keys = Object.keys(v);
    return keys.length ? `{${keys.slice(0, 2).join(',')}${keys.length > 2 ? '+' : ''}}` : '{}';
  }
  const s = String(v);
  return s.length > 40 ? s.slice(0, 37) + '…' : s;
}
function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// ── Column definitions ─────────────────────────────────────────────────
// Each category has columns [{ key, label, accessor }]. accessor returns
// the cell value for a given ticker. Width defaults are managed by CSS;
// `narrow: true` flag shrinks the column.
const CATS = [
  {
    id: 'actionable', default: true, label: 'Actionable', color: '#10b981',
    columns: [
      { key: 'verdict',         label: 'Verdict',     accessor: t => t.verdict },
      { key: 'stage',           label: 'Stage',       accessor: t => t.stage },
      { key: 'score',           label: 'Score',       accessor: t => t.score },
      { key: 'star_rating',     label: '★',           accessor: t => t.star_rating, narrow: true },
      { key: 'regime',          label: 'Regime',      accessor: t => _val(t, 'regime', 'regime4') },
      { key: 'setup_family',    label: 'Setup',       accessor: t => t.setup_family },
      { key: 'entry_quality',   label: 'Entry Q',     accessor: t => t.entry_quality },
      { key: 'catalyst_tier',   label: 'Cat·Tier',    accessor: t => t.catalyst_tier, narrow: true },
      { key: 'rs_rank',         label: 'RS',          accessor: t => t.rs_rank, narrow: true },
      { key: 'rvol',            label: 'RVol',        accessor: t => t.rvol, narrow: true },
      { key: 'price',           label: 'Price',       accessor: t => t.price },
      { key: 'entry_low',       label: 'Entry Lo',    accessor: t => _val(t, 'entry_low', 'entry_lo') },
      { key: 'entry_high',      label: 'Entry Hi',    accessor: t => _val(t, 'entry_high', 'entry_hi') },
      { key: 'stop',            label: 'Stop',        accessor: t => t.stop },
      { key: 'target1',         label: 'T1',          accessor: t => _val(t, 'target1', 't1') },
      { key: 'target2',         label: 'T2',          accessor: t => _val(t, 'target2', 't2') },
      { key: 'rr_ratio',        label: 'R:R',         accessor: t => _val(t, 'rr_ratio', 'rr') },
      { key: 'alloc_pct',       label: 'Alloc%',      accessor: t => _val(t, 'alloc_pct', 'kelly_size.final_alloc_pct') },
      { key: 'reject_reason',   label: 'Reject',      accessor: t => t.reject_reason },
    ],
  },
  {
    id: 'pricing', label: 'Pricing & Volume', color: '#3b82f6',
    columns: [
      { key: 'atr_pct',       label: 'ATR%',       accessor: t => t.atr_pct },
      { key: 'beta',          label: 'β',          accessor: t => t.beta, narrow: true },
      { key: 'rsi',           label: 'RSI',        accessor: t => t.rsi, narrow: true },
      { key: 'adx',           label: 'ADX',        accessor: t => t.adx, narrow: true },
      { key: 'perf_1d',       label: 'Day%',       accessor: t => t.perf_1d || t.pct_chg },
      { key: 'perf_1w',       label: '1w%',        accessor: t => t.perf_1w },
      { key: 'perf_month_pct',label: '1m%',        accessor: t => t.perf_month_pct },
      { key: 'perf_quarter_pct',label: '3m%',      accessor: t => t.perf_quarter_pct },
      { key: 'perf_year_pct', label: '1y%',        accessor: t => t.perf_year_pct },
      { key: 'week52_high',   label: '52w Hi',     accessor: t => t.week52_high },
      { key: 'week52_low',    label: '52w Lo',     accessor: t => t.week52_low },
      { key: 'float_shares',  label: 'Float',      accessor: t => t.float_shares },
      { key: 'short_pct',     label: 'Short%',     accessor: t => _val(t, 'short_pct', 'short_float_pct') },
    ],
  },
  {
    id: 'setup', label: 'Setup Attribution', color: '#f59e0b',
    columns: [
      { key: 'entry_subtype',     label: 'Subtype',       accessor: t => t.entry_subtype },
      { key: 'hold_period_min',   label: 'Hold Min',      accessor: t => t.hold_period_min },
      { key: 'hold_period_max',   label: 'Hold Max',      accessor: t => t.hold_period_max },
      { key: 'catalyst_tags',     label: 'Catalysts',     accessor: t => t.catalyst_tags },
      { key: 'setup_quality_label', label: 'Setup Qual',  accessor: t => _val(t, 'setup_quality.label') },
      { key: 'setup_size_multiplier', label: 'Sz Mult',   accessor: t => t.setup_size_multiplier, narrow: true },
      { key: 'expected_pullback', label: 'Exp PB',        accessor: t => t.expected_pullback },
      { key: 'weekly_bull',       label: 'Wkly Bull',     accessor: t => t.weekly_bull, narrow: true },
    ],
  },
  {
    id: 'technicals', label: 'Technicals', color: '#a855f7',
    columns: [
      { key: 'ema_signal',     label: 'EMA',          accessor: t => t.ema_signal },
      { key: 'macd_signal',    label: 'MACD',         accessor: t => t.macd_signal },
      { key: 'above_8ema',     label: '>8E',          accessor: t => t.above_8ema, narrow: true },
      { key: 'above_21ema',    label: '>21E',         accessor: t => t.above_21ema, narrow: true },
      { key: 'above_50ema',    label: '>50E',         accessor: t => t.above_50ema, narrow: true },
      { key: 'above_200sma',   label: '>200S',        accessor: t => t.above_200sma, narrow: true },
      { key: 'squeeze_on',     label: 'Squeeze',      accessor: t => t.squeeze_on, narrow: true },
      { key: 'fractal_signal', label: 'Fractal',      accessor: t => t.fractal_signal },
      { key: 'fractal_high',   label: 'Frac Hi',      accessor: t => t.fractal_high },
      { key: 'fractal_low',    label: 'Frac Lo',      accessor: t => t.fractal_low },
      { key: 'fib_382',        label: 'Fib 38.2',     accessor: t => t.fib_382 },
      { key: 'fib_500',        label: 'Fib 50',       accessor: t => t.fib_500 },
      { key: 'fib_618',        label: 'Fib 61.8',     accessor: t => t.fib_618 },
      { key: 'vwap',           label: 'VWAP',         accessor: t => _val(t, 'vwap.value', 'vwap') },
    ],
  },
  {
    id: 'tradeplan', label: 'Trade Plan (zones)', color: '#06b6d4',
    columns: [
      { key: 'primary_zone_low',  label: 'P Zone Lo', accessor: t => t.primary_zone_low },
      { key: 'primary_zone_high', label: 'P Zone Hi', accessor: t => t.primary_zone_high },
      { key: 'deep_zone_low',     label: 'D Zone Lo', accessor: t => t.deep_zone_low },
      { key: 'deep_zone_high',    label: 'D Zone Hi', accessor: t => t.deep_zone_high },
      { key: 'shallow_zone_low',  label: 'S Zone Lo', accessor: t => t.shallow_zone_low },
      { key: 'shallow_zone_high', label: 'S Zone Hi', accessor: t => t.shallow_zone_high },
      { key: 'max_hold_days',     label: 'Max Hold',  accessor: t => t.max_hold_days, narrow: true },
      { key: 'tp_setup_type',     label: 'TP setup',  accessor: t => _val(t, 'trade_plan.setup_type') },
      { key: 'tp_exit_family',    label: 'Exit Fam',  accessor: t => _val(t, 'trade_plan.exit_family') },
      { key: 'tp_risk_per_share', label: 'Risk/Sh',   accessor: t => _val(t, 'trade_plan.risk_per_share') },
      { key: 'tp_beta_adj',       label: 'β-Adj',     accessor: t => _val(t, 'trade_plan.beta_adj_multiplier'), narrow: true },
    ],
  },
  {
    id: 'scoring', label: 'Scoring (5-pillar)', color: '#22c55e',
    columns: [
      { key: 'tech_score', label: 'Tech',  accessor: t => t.tech_score, narrow: true },
      { key: 'fund_score', label: 'Fund',  accessor: t => t.fund_score, narrow: true },
      { key: 'smc_score',  label: 'SMC',   accessor: t => t.smc_score, narrow: true },
      { key: 'sent_score', label: 'Sent',  accessor: t => t.sent_score, narrow: true },
      { key: 'fund_real',  label: 'Fund R',accessor: t => t.fund_real, narrow: true },
      { key: 'fund_pts',   label: 'F pts', accessor: t => t.fund_pts, narrow: true },
      { key: 'fund_total', label: 'F tot', accessor: t => t.fund_total, narrow: true },
      { key: 'sb_wr_mult', label: 'WR×',   accessor: t => _val(t, 'scoring_breakdown.wr_multiplier'), narrow: true },
      { key: 'sb_bonus',   label: 'Bonus', accessor: t => _val(t, 'scoring_breakdown.bonus_total'), narrow: true },
      { key: 'sb_final',   label: 'Final', accessor: t => _val(t, 'scoring_breakdown.final_score'), narrow: true },
    ],
  },
  {
    id: 'verdict', label: 'Verdict Engine', color: '#84cc16',
    columns: [
      { key: 'decision_label', label: 'Decision Label',  accessor: t => t.decision_label },
      { key: 'ds_state',       label: 'Zone State',      accessor: t => _val(t, 'decision_state.state') },
      { key: 'ds_size_mult',   label: 'Zone Sz×',        accessor: t => _val(t, 'decision_state.size_mult_by_zone'), narrow: true },
      { key: 'ds_in_cloud',    label: 'In Cloud',        accessor: t => _val(t, 'decision_state.in_cloud'), narrow: true },
      { key: 'audit_pass',     label: 'Gates Pass',      accessor: t => _val(t, 'audit_trail.hard_gates_passed'), narrow: true },
      { key: 'sector_demoted', label: 'Sec Demote',      accessor: t => t.sector_demoted, narrow: true },
      { key: 'sector_demotion_reason', label: 'Demote Reason', accessor: t => t.sector_demotion_reason },
      { key: 'caveats_count',  label: '# Caveats',       accessor: t => (t.caveats || []).length, narrow: true },
    ],
  },
  {
    id: 'smc', label: 'SMC', color: '#d946ef',
    columns: [
      { key: 'smc_pts',   label: 'SMC pts',    accessor: t => t.smc_pts, narrow: true },
      { key: 'smc_max',   label: 'SMC max',    accessor: t => t.smc_max, narrow: true },
      { key: 'smc_dir',   label: 'SMC Dir',    accessor: t => _val(t, 'smc.smc_direction') },
      { key: 'smc_bos',   label: 'BOS',        accessor: t => _val(t, 'smc.bos_choch.label') },
      { key: 'fvg_n',     label: 'FVG #',      accessor: t => (_val(t, 'smc.fvg_zones') || []).length, narrow: true },
      { key: 'ob_n',      label: 'OB #',       accessor: t => (_val(t, 'smc.order_blocks') || []).length, narrow: true },
    ],
  },
  {
    id: 'elliott', label: 'Elliott Wave', color: '#ec4899',
    columns: [
      { key: 'ew_wave',    label: 'EW Wave',    accessor: t => _val(t, 'elliott_wave.wave_label', 'elliott_wave.wave_number') },
      { key: 'ew_conf',    label: 'EW Conf',    accessor: t => _val(t, 'elliott_wave.confidence') },
      { key: 'ew_trend',   label: 'EW Trend',   accessor: t => _val(t, 'elliott_wave.trend') },
      { key: 'ew_low',     label: 'EW Low',     accessor: t => _val(t, 'elliott_wave.swing_base') },
      { key: 'ew_high',    label: 'EW High',    accessor: t => _val(t, 'elliott_wave.swing_top') },
      { key: 'ewv1_wave',  label: 'EW v1 Wave', accessor: t => _val(t, 'trade_plan.elliott_wave_v1.wave_label', 'trade_plan.elliott_wave_v1.wave_number') },
      { key: 'ewv1_conf',  label: 'EW v1 Conf', accessor: t => _val(t, 'trade_plan.elliott_wave_v1.confidence') },
    ],
  },
  {
    id: 'fundamentals', label: 'Fundamentals', color: '#f97316',
    columns: [
      { key: 'analyst_consensus', label: 'Consensus', accessor: t => t.analyst_consensus },
      { key: 'analyst_target',    label: 'PT',        accessor: t => t.analyst_target },
      { key: 'analyst_upside',    label: 'Upside%',   accessor: t => t.analyst_upside },
      { key: 'analyst_buy',       label: 'Buy#',      accessor: t => t.analyst_buy, narrow: true },
      { key: 'analyst_strong_buy',label: 'SB#',       accessor: t => t.analyst_strong_buy, narrow: true },
      { key: 'rev_growth',        label: 'Rev Grw%',  accessor: t => t.rev_growth },
      { key: 'net_margin',        label: 'Net Mgn',   accessor: t => t.net_margin },
      { key: 'peg',               label: 'PEG',       accessor: t => t.peg, narrow: true },
      { key: 'fv_gross_margin',   label: 'Gross Mgn', accessor: t => t.fv_gross_margin },
      { key: 'fv_oper_margin',    label: 'Op Mgn',    accessor: t => t.fv_oper_margin },
      { key: 'fv_profit_margin',  label: 'Profit Mgn',accessor: t => t.fv_profit_margin },
      { key: 'fv_roa_pct',        label: 'ROA',       accessor: t => t.fv_roa_pct },
      { key: 'fv_roe_pct',        label: 'ROE',       accessor: t => t.fv_roe_pct },
      { key: 'fv_current_ratio',  label: 'CurRatio',  accessor: t => t.fv_current_ratio },
    ],
  },
  {
    id: 'options', label: 'Options', color: '#eab308',
    columns: [
      { key: 'iv_rank',           label: 'IV Rank',  accessor: t => t.iv_rank },
      { key: 'put_call_ratio',    label: 'P/C',      accessor: t => t.put_call_ratio },
      { key: 'od_current_iv',     label: 'IV',       accessor: t => _val(t, 'options_data.current_iv') },
      { key: 'od_max_pain',       label: 'Max Pain', accessor: t => _val(t, 'options_data.max_pain') },
      { key: 'od_uoa_calls',      label: 'UOA C',    accessor: t => _val(t, 'options_data.uoa_calls'), narrow: true },
      { key: 'od_uoa_puts',       label: 'UOA P',    accessor: t => _val(t, 'options_data.uoa_puts'), narrow: true },
      { key: 'ok_gamma_net',      label: 'γ Net',    accessor: t => _val(t, 'options_kpis.gamma_net') },
      { key: 'ok_skew_25d',       label: 'Skew 25d', accessor: t => _val(t, 'options_kpis.skew_25d') },
      { key: 'ok_iv_percentile',  label: 'IV %ile',  accessor: t => _val(t, 'options_kpis.iv_percentile'), narrow: true },
    ],
  },
  {
    id: 'smartmoney', label: 'Smart-Money Flow', color: '#14b8a6',
    columns: [
      { key: 'insider_buys',    label: 'Ins Buy',   accessor: t => t.insider_buys, narrow: true },
      { key: 'insider_sells',   label: 'Ins Sell',  accessor: t => t.insider_sells, narrow: true },
      { key: 'insider_days',    label: 'Days Ago',  accessor: t => t.insider_days, narrow: true },
      { key: 'insider_own_pct', label: 'Ins Own%',  accessor: t => t.insider_own_pct },
      { key: 'insider_recent',  label: 'Recent$',   accessor: t => t.insider_recent },
      { key: 'inst_own_pct',    label: 'Inst Own%', accessor: t => t.inst_own_pct },
      { key: 'inst_trend',      label: 'Inst Trend',accessor: t => _val(t, 'inst_trend.inst_trend') },
      { key: 'congress_net',    label: 'Congress',  accessor: t => _val(t, 'congressional.net') },
      { key: 'congress_purch',  label: 'Cong Buy',  accessor: t => _val(t, 'congressional.purchases'), narrow: true },
    ],
  },
  {
    id: 'sentiment', label: 'Sentiment', color: '#0891b2',
    columns: [
      { key: 'news_score',          label: 'News Sc',     accessor: t => t.news_score },
      { key: 'news_articles_n',     label: '# News',      accessor: t => (t.news_articles || []).length, narrow: true },
      { key: 'st_bull_pct',         label: 'ST Bull%',    accessor: t => _val(t, 'stocktwits.bull_pct') },
      { key: 'st_msg_vol',          label: 'ST Vol',      accessor: t => _val(t, 'stocktwits.message_volume') },
      { key: 'wsb_mentions',        label: 'WSB',         accessor: t => _val(t, 'reddit_wsb.mentions') },
      { key: 'eodhd_sentiment',     label: 'EODHD Sent',  accessor: t => _val(t, 'eodhd_sentiment.score', 'eodhd_sentiment') },
    ],
  },
  {
    id: 'zacks', label: 'Zacks', color: '#dc2626',
    columns: [
      { key: 'zacks_rank1',          label: 'Rank #1',   accessor: t => t.zacks_rank1, narrow: true },
      { key: 'zacks_sell',           label: 'Sell',      accessor: t => t.zacks_sell, narrow: true },
      { key: 'zacks_grade_vgm',      label: 'VGM',       accessor: t => _val(t, 'zacks_grades.vgm', 'grade_vgm') },
      { key: 'zacks_grade_g',        label: 'Growth',    accessor: t => _val(t, 'zacks_grades.growth', 'grade_growth') },
      { key: 'zacks_grade_m',        label: 'Momentum',  accessor: t => _val(t, 'zacks_grades.momentum', 'grade_momentum') },
      { key: 'zacks_grade_v',        label: 'Value',     accessor: t => _val(t, 'zacks_grades.value', 'grade_value') },
      { key: 'zacks_industry_rank', label: 'Ind Rank',   accessor: t => t.zacks_industry_rank, narrow: true },
      { key: 'zacks_earnings_esp',  label: 'ESP',        accessor: t => t.zacks_earnings_esp },
      { key: 'zacks_lt_growth',     label: 'LT Grw',     accessor: t => t.zacks_lt_growth },
      { key: 'zacks_recommendation', label: 'Zacks Rec', accessor: t => t.zacks_recommendation },
      { key: 'zacks_email_n',        label: '# Emails',  accessor: t => (t.zacks_email_mentions || []).length, narrow: true },
      { key: 'zacks_services_n',     label: '# Services',accessor: t => (t.zacks_held_by_services || []).length, narrow: true },
    ],
  },
  {
    id: 'risk', label: 'Risk & Kelly', color: '#e11d48',
    columns: [
      { key: 'ks_kelly_pct',       label: 'Kelly%',    accessor: t => _val(t, 'kelly_size.kelly_pct') },
      { key: 'ks_half_kelly_pct',  label: '½K%',       accessor: t => _val(t, 'kelly_size.half_kelly_pct') },
      { key: 'ks_dollar_risk',     label: 'Risk$',     accessor: t => _val(t, 'kelly_size.dollar_risk') },
      { key: 'ks_regime_mult',     label: 'Reg×',      accessor: t => _val(t, 'kelly_size.regime_mult'), narrow: true },
      { key: 'ks_vix_mult',        label: 'VIX×',      accessor: t => _val(t, 'kelly_size.vix_mult'), narrow: true },
      { key: 'ks_drawdown_mult',   label: 'DD×',       accessor: t => _val(t, 'kelly_size.drawdown_mult'), narrow: true },
      { key: 'ks_drawdown_pct',    label: 'DD%',       accessor: t => _val(t, 'kelly_size.drawdown_pct') },
      { key: 'ks_suggested',       label: 'Shares',    accessor: t => _val(t, 'kelly_size.suggested_shares') },
      { key: 'ks_position_value',  label: 'Pos$',      accessor: t => _val(t, 'kelly_size.position_value') },
      { key: 'ks_cvar',            label: 'CVaR%',     accessor: t => _val(t, 'kelly_size.cvar_975_pct') },
      { key: 'sizing_multiplier',  label: 'Sz Mult',   accessor: t => t.sizing_multiplier, narrow: true },
      { key: 'monte_carlo_p',      label: 'MC P',      accessor: t => _val(t, 'monte_carlo.p_profit', 'mc_p_profit') },
    ],
  },
  {
    id: 'theory', label: 'Theory Confluence', color: '#7c3aed',
    columns: [
      { key: 'th_dir',     label: 'TC Dir',    accessor: t => _val(t, 'theory_confluence.direction') },
      { key: 'th_bull',    label: 'Bull #',    accessor: t => _val(t, 'theory_confluence.bull_count'), narrow: true },
      { key: 'th_bear',    label: 'Bear #',    accessor: t => _val(t, 'theory_confluence.bear_count'), narrow: true },
      { key: 'th_gate',    label: 'Hard Gate', accessor: t => _val(t, 'theory_confluence.hard_gate_pass'), narrow: true },
    ],
  },
  {
    id: 'tier1', label: 'Tier-1 Signals', color: '#9333ea',
    columns: [
      { key: 't1_active',  label: 'T1 Active', accessor: t => _val(t, 'tier1_signals.active_count'), narrow: true },
      { key: 't1_points',  label: 'T1 Pts',    accessor: t => _val(t, 'tier1_signals.total_points'), narrow: true },
    ],
  },
  {
    id: 'mtf', label: 'Multi-Timeframe', color: '#4f46e5',
    columns: [
      { key: 'mt_score',   label: 'MT Score',   accessor: t => t.medium_term_score, narrow: true },
      { key: 'mt_verdict', label: 'MT Verdict', accessor: t => t.medium_term_verdict },
      { key: 'lt_score',   label: 'LT Score',   accessor: t => t.long_term_score, narrow: true },
      { key: 'lt_verdict', label: 'LT Verdict', accessor: t => t.long_term_verdict },
      { key: 'perf_4h',    label: '4h Perf',    accessor: t => t.perf_4h, narrow: true },
    ],
  },
  {
    id: 'earnings', label: 'Earnings', color: '#1d4ed8',
    columns: [
      { key: 'earn_days',     label: 'Days to E', accessor: t => t.earn_days, narrow: true },
      { key: 'earnings_beat', label: 'Beat',      accessor: t => t.earnings_beat, narrow: true },
      { key: 'esp_play',      label: 'ESP Play',  accessor: t => t.esp_play, narrow: true },
    ],
  },
  {
    id: 'bookkeeping', label: 'Bundle Bookkeeping', color: '#64748b',
    columns: [
      { key: 'industry',    label: 'Industry',     accessor: t => t.industry },
      { key: 'sector_pct_rank', label: 'Sec %ile', accessor: t => t.sector_pct_rank, narrow: true },
      { key: 'market_cap',  label: 'Mkt Cap',      accessor: t => t.market_cap },
      { key: 'cap_bucket',  label: 'Cap',          accessor: t => t.cap_bucket, narrow: true },
      { key: 'tv_rec',      label: 'TV',           accessor: t => t.tv_rec_str },
      { key: 'rr_inconsistent', label: 'RR Bad',   accessor: t => t.rr_inconsistent, narrow: true },
    ],
  },
];

// ── State ──────────────────────────────────────────────────────────────
let _enabledCats = new Set(CATS.filter(c => c.default).map(c => c.id));
let _searchTerm  = '';
let _verdictFilter = 'all';   // 'all' | 'BUY' | 'WATCH' | 'SHORT'

let _TICKERS_ARRAY = null;
async function _loadTickers() {
  if (_TICKERS_ARRAY) return _TICKERS_ARRAY;
  try {
    const raw = await getTickers();
    if (!raw) return [];
    let arr;
    if (Array.isArray(raw)) arr = raw.slice();
    else arr = Object.entries(raw).map(([sym, payload]) => ({
      ticker: payload?.ticker || sym, ...payload,
    }));
    _TICKERS_ARRAY = arr;
    return arr;
  } catch (e) {
    console.warn('[fields] _getTickers() failed:', e);
    return [];
  }
}

function _activeColumns() {
  // Order: anchors → categories in their definition order, columns inside cat in their order
  const cols = [];
  for (const cat of CATS) {
    if (!_enabledCats.has(cat.id)) continue;
    for (const col of cat.columns) {
      cols.push({ ...col, catLabel: cat.label, catColor: cat.color });
    }
  }
  return cols;
}

function _filteredTickers(arr) {
  let out = arr.slice();
  if (_searchTerm) {
    const q = _searchTerm.toLowerCase();
    out = out.filter(t => (t.ticker || '').toLowerCase().includes(q) ||
                          (t.name || '').toLowerCase().includes(q));
  }
  if (_verdictFilter && _verdictFilter !== 'all') {
    out = out.filter(t => (t.verdict || '').toUpperCase() === _verdictFilter);
  }
  // Sort: BUYs first, then WATCH, then SHORT/AVOID; by score desc within group
  const vOrd = { BUY: 0, WATCH: 1, SHORT: 2, AVOID: 3 };
  out.sort((a, b) => {
    const av = vOrd[(a.verdict || '').toUpperCase()] ?? 9;
    const bv = vOrd[(b.verdict || '').toUpperCase()] ?? 9;
    if (av !== bv) return av - bv;
    return (b.score || 0) - (a.score || 0);
  });
  return out;
}

// ── Render ─────────────────────────────────────────────────────────────
export async function render() {
  const body = $('fieldsBody');
  if (!body) return;
  body.innerHTML = '<div class="stub">Loading tickers.json…</div>';

  const all = await _loadTickers();
  if (!all.length) {
    body.innerHTML = `<div class="stub">No tickers available (tickers.json empty or not yet fetched).</div>`;
    return;
  }

  const DATA  = getData();
  const scanDate = (DATA?.run_date || DATA?.scan_date || DATA?._meta?.run_date ||
                   DATA?.regime?.run_date || new Date().toISOString().slice(0, 10));
  // run_timestamp from build_data.py is the scan run's clock time. Per-ticker
  // capture timestamps land in v2 once ticker_snapshots is wired.
  const scanTime = (() => {
    const ts = DATA?.run_timestamp || DATA?.scan_time || DATA?.run_time;
    if (!ts) return '—';
    // "2026-05-10 22:23" → "22:23 PDT" for readability
    const m = String(ts).match(/(\d{2}:\d{2})/);
    return m ? m[1] : String(ts).slice(-8);
  })();

  const genTs  = new Date();
  const genStr = genTs.toLocaleString('en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    timeZoneName: 'short', hour12: false,
  });

  const cols = _activeColumns();
  const filtered = _filteredTickers(all);

  // Pre-compute counts by verdict for filter chips
  const counts = { all: all.length, BUY: 0, WATCH: 0, SHORT: 0 };
  all.forEach(t => {
    const v = (t.verdict || '').toUpperCase();
    if (v in counts) counts[v]++;
  });

  // ── Toolbar HTML ──────────────────────────────────────────────────
  const toolbarHtml = `
    <div class="card" style="margin-bottom:14px">
      <div class="card-h">Field Inventory <span class="meta">${filtered.length} of ${all.length} tickers · ${cols.length + 3} columns visible</span></div>

      <div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin:6px 0 10px 0;font-size:11px;color:var(--ink-2)">
        <span><span style="color:var(--ink-3)">Scan as-of:</span> <strong style="color:var(--ink-0);font-family:var(--mono)">${scanDate}</strong></span>
        <span><span style="color:var(--ink-3)">Scan time:</span> <strong style="color:var(--ink-0);font-family:var(--mono)">${scanTime}</strong></span>
        <span><span style="color:var(--ink-3)">View generated:</span> <strong style="color:var(--ink-0);font-family:var(--mono)">${genStr}</strong></span>
      </div>

      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:10px 0">
        <label style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-0)">Search:</label>
        <input id="fieldsSearch" type="text" placeholder="ticker or name…" value="${_esc(_searchTerm)}" style="background:var(--bg-1);color:var(--ink-0);border:1px solid var(--rule);padding:5px 9px;font-family:var(--mono);font-size:12px;border-radius:3px;min-width:200px" />

        <label style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-0);margin-left:14px">Verdict:</label>
        <div style="display:flex;gap:4px">
          ${['all', 'BUY', 'WATCH', 'SHORT'].map(v => `
            <div class="fields-verdict-chip" data-verdict="${v}" style="
              padding:5px 12px;border-radius:14px;font-size:11px;font-weight:700;cursor:pointer;
              letter-spacing:.04em;border:1.5px solid var(--rule);
              background:${_verdictFilter === v ? 'var(--accent)' : 'transparent'};
              color:${_verdictFilter === v ? 'var(--bg-0)' : 'var(--ink-2)'}">
              ${v}  ${counts[v] != null ? '<span style="opacity:.7;font-weight:500">' + counts[v] + '</span>' : ''}
            </div>`).join('')}
        </div>

        <button id="fieldsExport" style="margin-left:auto;background:var(--accent);color:var(--bg-0);border:none;padding:6px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;cursor:pointer;border-radius:4px;text-transform:uppercase">Export CSV</button>
      </div>

      <div style="margin:14px 0 6px 0">
        <span style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-2)">Column groups (${_enabledCats.size} of ${CATS.length} on):</span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px">
        ${CATS.map(c => `
          <div class="field-cat-chip" data-cat="${c.id}" style="
              padding:5px 12px;border-radius:14px;font-size:11px;font-weight:700;cursor:pointer;
              letter-spacing:.04em;border:1.5px solid ${c.color};
              background:${_enabledCats.has(c.id) ? c.color : 'transparent'};
              color:${_enabledCats.has(c.id) ? '#fff' : c.color};
              transition:all .15s ease">
            ${c.label} <span style="opacity:.65;font-weight:500">${c.columns.length}</span>
          </div>`).join('')}
      </div>
    </div>
  `;

  // ── Table HTML ─────────────────────────────────────────────────────
  const headerCells = [
    `<th style="position:sticky;left:0;z-index:2;background:var(--bg-1);text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:70px;border-right:1px solid var(--rule)">Ticker</th>`,
    `<th style="text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:90px">Date</th>`,
    `<th style="text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:70px">Scan Time</th>`,
    ...cols.map(c => `
      <th title="${_esc(c.catLabel)}" style="text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:${c.narrow ? '60' : '110'}px;border-top:2px solid ${c.catColor}">
        ${_esc(c.label)}
      </th>`),
  ].join('');

  const bodyRows = filtered.map(t => {
    const cells = [
      `<td style="position:sticky;left:0;z-index:1;background:var(--bg-0);padding:6px 10px;font-family:var(--mono);font-weight:700;color:var(--ink-0);border-right:1px solid var(--rule)">${_esc(t.ticker)}</td>`,
      `<td style="padding:6px 10px;font-family:var(--mono);color:var(--ink-2);font-size:11px">${_esc(scanDate)}</td>`,
      `<td style="padding:6px 10px;font-family:var(--mono);color:var(--ink-2);font-size:11px">${_esc(scanTime)}</td>`,
      ...cols.map(c => {
        let v;
        try { v = c.accessor(t); } catch (e) { v = undefined; }
        return `<td style="padding:6px 10px;font-family:var(--mono);font-size:11.5px;color:var(--ink-0);white-space:nowrap">${_esc(_fmt(v))}</td>`;
      }),
    ].join('');
    return `<tr style="border-bottom:1px dashed var(--rule)">${cells}</tr>`;
  }).join('');

  const tableHtml = `
    <div class="card" style="overflow-x:auto;padding:0">
      <table style="width:max-content;min-width:100%;border-collapse:collapse">
        <thead><tr style="border-bottom:2px solid var(--rule);background:var(--bg-1)">${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;

  body.innerHTML = toolbarHtml + tableHtml;

  // ── Wiring ─────────────────────────────────────────────────────────
  $('fieldsSearch').oninput = e => { _searchTerm = e.target.value; render(); };
  document.querySelectorAll('.fields-verdict-chip').forEach(el => {
    el.onclick = () => { _verdictFilter = el.dataset.verdict; render(); };
  });
  document.querySelectorAll('.field-cat-chip').forEach(el => {
    el.onclick = () => {
      const id = el.dataset.cat;
      if (_enabledCats.has(id)) _enabledCats.delete(id); else _enabledCats.add(id);
      render();
    };
  });
  $('fieldsExport').onclick = () => {
    const headers = ['Ticker', 'Date', 'Scan Time', ...cols.map(c => c.label)];
    const lines = [headers.map(h => `"${String(h).replace(/"/g, '""')}"`).join(',')];
    filtered.forEach(t => {
      const row = [
        t.ticker || '',
        scanDate,
        scanTime,
        ...cols.map(c => {
          let v; try { v = c.accessor(t); } catch (e) { v = ''; }
          return String(_fmt(v)).replace(/"/g, '""');
        }),
      ];
      lines.push(row.map(c => `"${c}"`).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fields_${scanDate}_${(new Date().toISOString().slice(11,19)).replace(/:/g,'')}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };
}

export function dispose() { /* persist user state across tab switches */ }
