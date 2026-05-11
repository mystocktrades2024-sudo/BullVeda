// tabs/fields/fields.js — wide tabular field inventory with full picker UX.
//
// 4-Tier control model:
//   Tier 0 — Preset buttons (5 built-in + user-saved customs)
//   Tier 1 — Category chips (bulk-add/remove a column group)
//   Tier 2 — Column Picker modal (per-column control, drag-reorder)
//   Tier 3 — Column header context menu + drag-reorder + sort
//
// State persists in localStorage under `swingtrade.fields.view`.
// CapStudio modular loader 2026-05-10.

import { getData, getTickers, $ } from '../../core/shared.js';

// ── Pure helpers ───────────────────────────────────────────────────────
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

// ── Category definitions ───────────────────────────────────────────────
// Source-of-truth registry: every column the user can choose from.
const CATS = [
  {
    id: 'actionable', label: 'Actionable', color: '#10b981',
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
      { key: 'atr_pct',        label: 'ATR%',       accessor: t => t.atr_pct },
      { key: 'beta',           label: 'β',          accessor: t => t.beta, narrow: true },
      { key: 'rsi',            label: 'RSI',        accessor: t => t.rsi, narrow: true },
      { key: 'adx',            label: 'ADX',        accessor: t => t.adx, narrow: true },
      { key: 'perf_1d',        label: 'Day%',       accessor: t => t.perf_1d || t.pct_chg },
      { key: 'perf_1w',        label: '1w%',        accessor: t => t.perf_1w },
      { key: 'perf_month_pct', label: '1m%',        accessor: t => t.perf_month_pct },
      { key: 'perf_quarter_pct', label: '3m%',      accessor: t => t.perf_quarter_pct },
      { key: 'perf_year_pct',  label: '1y%',        accessor: t => t.perf_year_pct },
      { key: 'week52_high',    label: '52w Hi',     accessor: t => t.week52_high },
      { key: 'week52_low',     label: '52w Lo',     accessor: t => t.week52_low },
      { key: 'float_shares',   label: 'Float',      accessor: t => t.float_shares },
      { key: 'short_pct',      label: 'Short%',     accessor: t => _val(t, 'short_pct', 'short_float_pct') },
    ],
  },
  {
    id: 'setup', label: 'Setup Attribution', color: '#f59e0b',
    columns: [
      { key: 'entry_subtype',         label: 'Subtype',    accessor: t => t.entry_subtype },
      { key: 'hold_period_min',       label: 'Hold Min',   accessor: t => t.hold_period_min },
      { key: 'hold_period_max',       label: 'Hold Max',   accessor: t => t.hold_period_max },
      { key: 'catalyst_tags',         label: 'Catalysts',  accessor: t => t.catalyst_tags },
      { key: 'setup_quality_label',   label: 'Setup Qual', accessor: t => _val(t, 'setup_quality.label') },
      { key: 'setup_size_multiplier', label: 'Sz Mult',    accessor: t => t.setup_size_multiplier, narrow: true },
      { key: 'expected_pullback',     label: 'Exp PB',     accessor: t => t.expected_pullback },
      { key: 'weekly_bull',           label: 'Wkly Bull',  accessor: t => t.weekly_bull, narrow: true },
    ],
  },
  {
    id: 'technicals', label: 'Technicals', color: '#a855f7',
    columns: [
      { key: 'ema_signal',     label: 'EMA',     accessor: t => t.ema_signal },
      { key: 'macd_signal',    label: 'MACD',    accessor: t => t.macd_signal },
      { key: 'above_8ema',     label: '>8E',     accessor: t => t.above_8ema, narrow: true },
      { key: 'above_21ema',    label: '>21E',    accessor: t => t.above_21ema, narrow: true },
      { key: 'above_50ema',    label: '>50E',    accessor: t => t.above_50ema, narrow: true },
      { key: 'above_200sma',   label: '>200S',   accessor: t => t.above_200sma, narrow: true },
      { key: 'squeeze_on',     label: 'Squeeze', accessor: t => t.squeeze_on, narrow: true },
      { key: 'fractal_signal', label: 'Fractal', accessor: t => t.fractal_signal },
      { key: 'fractal_high',   label: 'Frac Hi', accessor: t => t.fractal_high },
      { key: 'fractal_low',    label: 'Frac Lo', accessor: t => t.fractal_low },
      { key: 'fib_382',        label: 'Fib 38',  accessor: t => t.fib_382 },
      { key: 'fib_500',        label: 'Fib 50',  accessor: t => t.fib_500 },
      { key: 'fib_618',        label: 'Fib 62',  accessor: t => t.fib_618 },
      { key: 'vwap',           label: 'VWAP',    accessor: t => _val(t, 'vwap.value', 'vwap') },
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
      { key: 'smc_pts', label: 'SMC pts', accessor: t => t.smc_pts, narrow: true },
      { key: 'smc_max', label: 'SMC max', accessor: t => t.smc_max, narrow: true },
      { key: 'smc_dir', label: 'SMC Dir', accessor: t => _val(t, 'smc.smc_direction') },
      { key: 'smc_bos', label: 'BOS',     accessor: t => _val(t, 'smc.bos_choch.label') },
      { key: 'fvg_n',   label: 'FVG #',   accessor: t => (_val(t, 'smc.fvg_zones') || []).length, narrow: true },
      { key: 'ob_n',    label: 'OB #',    accessor: t => (_val(t, 'smc.order_blocks') || []).length, narrow: true },
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
      { key: 'iv_rank',          label: 'IV Rank',  accessor: t => t.iv_rank },
      { key: 'put_call_ratio',   label: 'P/C',      accessor: t => t.put_call_ratio },
      { key: 'od_current_iv',    label: 'IV',       accessor: t => _val(t, 'options_data.current_iv') },
      { key: 'od_max_pain',      label: 'Max Pain', accessor: t => _val(t, 'options_data.max_pain') },
      { key: 'od_uoa_calls',     label: 'UOA C',    accessor: t => _val(t, 'options_data.uoa_calls'), narrow: true },
      { key: 'od_uoa_puts',      label: 'UOA P',    accessor: t => _val(t, 'options_data.uoa_puts'), narrow: true },
      { key: 'ok_gamma_net',     label: 'γ Net',    accessor: t => _val(t, 'options_kpis.gamma_net') },
      { key: 'ok_skew_25d',      label: 'Skew 25d', accessor: t => _val(t, 'options_kpis.skew_25d') },
      { key: 'ok_iv_percentile', label: 'IV %ile',  accessor: t => _val(t, 'options_kpis.iv_percentile'), narrow: true },
    ],
  },
  {
    id: 'smartmoney', label: 'Smart-Money Flow', color: '#14b8a6',
    columns: [
      { key: 'insider_buys',    label: 'Ins Buy',    accessor: t => t.insider_buys, narrow: true },
      { key: 'insider_sells',   label: 'Ins Sell',   accessor: t => t.insider_sells, narrow: true },
      { key: 'insider_days',    label: 'Days Ago',   accessor: t => t.insider_days, narrow: true },
      { key: 'insider_own_pct', label: 'Ins Own%',   accessor: t => t.insider_own_pct },
      { key: 'insider_recent',  label: 'Recent$',    accessor: t => t.insider_recent },
      { key: 'inst_own_pct',    label: 'Inst Own%',  accessor: t => t.inst_own_pct },
      { key: 'inst_trend',      label: 'Inst Trend', accessor: t => _val(t, 'inst_trend.inst_trend') },
      { key: 'congress_net',    label: 'Congress',   accessor: t => _val(t, 'congressional.net') },
      { key: 'congress_purch',  label: 'Cong Buy',   accessor: t => _val(t, 'congressional.purchases'), narrow: true },
    ],
  },
  {
    id: 'sentiment', label: 'Sentiment', color: '#0891b2',
    columns: [
      { key: 'news_score',      label: 'News Sc',    accessor: t => t.news_score },
      { key: 'news_articles_n', label: '# News',     accessor: t => (t.news_articles || []).length, narrow: true },
      { key: 'st_bull_pct',     label: 'ST Bull%',   accessor: t => _val(t, 'stocktwits.bull_pct') },
      { key: 'st_msg_vol',      label: 'ST Vol',     accessor: t => _val(t, 'stocktwits.message_volume') },
      { key: 'wsb_mentions',    label: 'WSB',        accessor: t => _val(t, 'reddit_wsb.mentions') },
      { key: 'eodhd_sentiment', label: 'EODHD Sent', accessor: t => _val(t, 'eodhd_sentiment.score', 'eodhd_sentiment') },
    ],
  },
  {
    id: 'zacks', label: 'Zacks', color: '#dc2626',
    columns: [
      { key: 'zacks_rank1',         label: 'Rank #1',   accessor: t => t.zacks_rank1, narrow: true },
      { key: 'zacks_sell',          label: 'Sell',      accessor: t => t.zacks_sell, narrow: true },
      { key: 'zacks_grade_vgm',     label: 'VGM',       accessor: t => _val(t, 'zacks_grades.vgm', 'grade_vgm') },
      { key: 'zacks_grade_g',       label: 'Growth',    accessor: t => _val(t, 'zacks_grades.growth', 'grade_growth') },
      { key: 'zacks_grade_m',       label: 'Momentum',  accessor: t => _val(t, 'zacks_grades.momentum', 'grade_momentum') },
      { key: 'zacks_grade_v',       label: 'Value',     accessor: t => _val(t, 'zacks_grades.value', 'grade_value') },
      { key: 'zacks_industry_rank', label: 'Ind Rank',  accessor: t => t.zacks_industry_rank, narrow: true },
      { key: 'zacks_earnings_esp',  label: 'ESP',       accessor: t => t.zacks_earnings_esp },
      { key: 'zacks_lt_growth',     label: 'LT Grw',    accessor: t => t.zacks_lt_growth },
      { key: 'zacks_recommendation', label: 'Zacks Rec', accessor: t => t.zacks_recommendation },
      { key: 'zacks_email_n',       label: '# Emails',  accessor: t => (t.zacks_email_mentions || []).length, narrow: true },
      { key: 'zacks_services_n',    label: '# Services',accessor: t => (t.zacks_held_by_services || []).length, narrow: true },
    ],
  },
  {
    id: 'risk', label: 'Risk & Kelly', color: '#e11d48',
    columns: [
      { key: 'ks_kelly_pct',      label: 'Kelly%',   accessor: t => _val(t, 'kelly_size.kelly_pct') },
      { key: 'ks_half_kelly_pct', label: '½K%',      accessor: t => _val(t, 'kelly_size.half_kelly_pct') },
      { key: 'ks_dollar_risk',    label: 'Risk$',    accessor: t => _val(t, 'kelly_size.dollar_risk') },
      { key: 'ks_regime_mult',    label: 'Reg×',     accessor: t => _val(t, 'kelly_size.regime_mult'), narrow: true },
      { key: 'ks_vix_mult',       label: 'VIX×',     accessor: t => _val(t, 'kelly_size.vix_mult'), narrow: true },
      { key: 'ks_drawdown_mult',  label: 'DD×',      accessor: t => _val(t, 'kelly_size.drawdown_mult'), narrow: true },
      { key: 'ks_drawdown_pct',   label: 'DD%',      accessor: t => _val(t, 'kelly_size.drawdown_pct') },
      { key: 'ks_suggested',      label: 'Shares',   accessor: t => _val(t, 'kelly_size.suggested_shares') },
      { key: 'ks_position_value', label: 'Pos$',     accessor: t => _val(t, 'kelly_size.position_value') },
      { key: 'ks_cvar',           label: 'CVaR%',    accessor: t => _val(t, 'kelly_size.cvar_975_pct') },
      { key: 'sizing_multiplier', label: 'Sz Mult',  accessor: t => t.sizing_multiplier, narrow: true },
      { key: 'monte_carlo_p',     label: 'MC P',     accessor: t => _val(t, 'monte_carlo.p_profit', 'mc_p_profit') },
    ],
  },
  {
    id: 'theory', label: 'Theory Confluence', color: '#7c3aed',
    columns: [
      { key: 'th_dir',  label: 'TC Dir',    accessor: t => _val(t, 'theory_confluence.direction') },
      { key: 'th_bull', label: 'Bull #',    accessor: t => _val(t, 'theory_confluence.bull_count'), narrow: true },
      { key: 'th_bear', label: 'Bear #',    accessor: t => _val(t, 'theory_confluence.bear_count'), narrow: true },
      { key: 'th_gate', label: 'Hard Gate', accessor: t => _val(t, 'theory_confluence.hard_gate_pass'), narrow: true },
    ],
  },
  {
    id: 'tier1', label: 'Tier-1 Signals', color: '#9333ea',
    columns: [
      { key: 't1_active', label: 'T1 Active', accessor: t => _val(t, 'tier1_signals.active_count'), narrow: true },
      { key: 't1_points', label: 'T1 Pts',    accessor: t => _val(t, 'tier1_signals.total_points'), narrow: true },
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
      { key: 'industry',                label: 'Industry',   accessor: t => t.industry },
      { key: 'sector_pct_rank',         label: 'Sec %ile',   accessor: t => t.sector_pct_rank, narrow: true },
      { key: 'market_cap',              label: 'Mkt Cap',    accessor: t => t.market_cap },
      { key: 'cap_bucket',              label: 'Cap',        accessor: t => t.cap_bucket, narrow: true },
      { key: 'tv_rec',                  label: 'TV',         accessor: t => t.tv_rec_str },
      { key: 'rr_inconsistent',         label: 'RR Bad',     accessor: t => t.rr_inconsistent, narrow: true },
    ],
  },
];

// ── Column registry (flat lookup by key) ─────────────────────────────
const COL_REGISTRY = {};
const CAT_BY_COL = {};
CATS.forEach(cat => {
  cat.columns.forEach(col => {
    COL_REGISTRY[col.key] = { ...col, catLabel: cat.label, catColor: cat.color, catId: cat.id };
    CAT_BY_COL[col.key] = cat.id;
  });
});
const ALL_COL_KEYS = Object.keys(COL_REGISTRY);

// ── Presets ────────────────────────────────────────────────────────────
const PRESETS = {
  essentials: {
    label: 'Decision Essentials',
    icon: '◉',
    description: 'Verdict-critical fields only',
    columns: ['verdict', 'stage', 'score', 'regime', 'setup_family', 'entry_quality', 'stop', 'target1', 'rr_ratio', 'alloc_pct', 'reject_reason'],
  },
  trader: {
    label: 'Trader Watch',
    icon: '👁',
    description: 'Pre-entry checklist',
    columns: ['verdict', 'stage', 'score', 'star_rating', 'regime', 'setup_family', 'entry_quality', 'catalyst_tier', 'rs_rank', 'rvol', 'price', 'entry_low', 'entry_high', 'stop', 'target1', 'rr_ratio', 'alloc_pct'],
  },
  risk: {
    label: 'Risk Audit',
    icon: '🛡',
    description: 'Kelly / drawdown / sizing',
    columns: ['verdict', 'score', 'regime', 'ks_kelly_pct', 'ks_half_kelly_pct', 'ks_regime_mult', 'ks_vix_mult', 'ks_drawdown_mult', 'ks_drawdown_pct', 'ks_dollar_risk', 'ks_suggested', 'ks_position_value', 'ks_cvar', 'sizing_multiplier', 'tp_beta_adj', 'monte_carlo_p'],
  },
  sentiment: {
    label: 'Sentiment Sweep',
    icon: '☁',
    description: 'Crowd-vs-system check',
    columns: ['verdict', 'score', 'news_score', 'news_articles_n', 'st_bull_pct', 'st_msg_vol', 'wsb_mentions', 'eodhd_sentiment', 'insider_buys', 'insider_sells', 'insider_days', 'congress_net'],
  },
  earnings: {
    label: 'Earnings Setup',
    icon: '📅',
    description: 'Pre-earnings windowing',
    columns: ['verdict', 'score', 'earn_days', 'earnings_beat', 'esp_play', 'zacks_earnings_esp', 'zacks_grade_g', 'zacks_lt_growth', 'analyst_consensus', 'analyst_target', 'analyst_upside', 'rev_growth'],
  },
};

// ── State (persisted to localStorage) ──────────────────────────────────
const LS_KEY = 'swingtrade.fields.view.v1';
const DEFAULT_PRESET = 'essentials';

function _defaultState() {
  return {
    activePresetId: DEFAULT_PRESET,
    selectedCols: [...PRESETS[DEFAULT_PRESET].columns],
    pinned: [], // additional sticky columns beyond the anchor (ticker is always pinned)
    customPresets: {}, // user-saved: { id: { label, columns, icon } }
    verdictFilter: 'all',
    searchTerm: '',
    sortBy: null, // { col: 'score', dir: 'desc' }
  };
}
function _loadState() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return _defaultState();
    const parsed = JSON.parse(raw);
    return { ..._defaultState(), ...parsed };
  } catch (e) { return _defaultState(); }
}
function _saveState() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(STATE)); } catch (e) { /* quota etc */ }
}
let STATE = _loadState();

// ── Ticker data accessor ───────────────────────────────────────────────
let _TICKERS_ARRAY = null;
async function _loadTickers() {
  if (_TICKERS_ARRAY) return _TICKERS_ARRAY;
  try {
    const raw = await getTickers();
    if (!raw) return [];
    let arr;
    if (Array.isArray(raw)) arr = raw.slice();
    else arr = Object.entries(raw).map(([sym, payload]) => ({ ticker: payload?.ticker || sym, ...payload }));
    _TICKERS_ARRAY = arr;
    return arr;
  } catch (e) {
    console.warn('[fields] getTickers() failed:', e);
    return [];
  }
}

function _filteredTickers(arr) {
  let out = arr.slice();
  if (STATE.searchTerm) {
    const q = STATE.searchTerm.toLowerCase();
    out = out.filter(t => (t.ticker || '').toLowerCase().includes(q) || (t.name || '').toLowerCase().includes(q));
  }
  if (STATE.verdictFilter && STATE.verdictFilter !== 'all') {
    out = out.filter(t => (t.verdict || '').toUpperCase() === STATE.verdictFilter);
  }
  if (STATE.sortBy) {
    const { col, dir } = STATE.sortBy;
    const acc = COL_REGISTRY[col]?.accessor;
    if (acc) {
      const mult = dir === 'asc' ? 1 : -1;
      out.sort((a, b) => {
        const av = acc(a), bv = acc(b);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * mult;
        return String(av).localeCompare(String(bv)) * mult;
      });
      return out;
    }
  }
  const vOrd = { BUY: 0, WATCH: 1, SHORT: 2, AVOID: 3 };
  out.sort((a, b) => {
    const av = vOrd[(a.verdict || '').toUpperCase()] ?? 9;
    const bv = vOrd[(b.verdict || '').toUpperCase()] ?? 9;
    if (av !== bv) return av - bv;
    return (b.score || 0) - (a.score || 0);
  });
  return out;
}

// ── Preset operations ──────────────────────────────────────────────────
function applyPreset(presetId) {
  const builtin = PRESETS[presetId];
  const custom = STATE.customPresets[presetId];
  const p = builtin || custom;
  if (!p) return;
  STATE.activePresetId = presetId;
  STATE.selectedCols = [...p.columns];
  _saveState();
}
function saveCustomPreset(label) {
  if (!label || !label.trim()) return;
  const id = `custom_${Date.now()}`;
  STATE.customPresets[id] = {
    label: label.trim(), icon: '◆',
    description: 'User-saved view',
    columns: [...STATE.selectedCols],
  };
  STATE.activePresetId = id;
  _saveState();
}
function deleteCustomPreset(presetId) {
  if (STATE.customPresets[presetId]) {
    delete STATE.customPresets[presetId];
    if (STATE.activePresetId === presetId) {
      applyPreset(DEFAULT_PRESET);
    }
    _saveState();
  }
}

// ── Category toggle ─────────────────────────────────────────────────────
function toggleCategory(catId) {
  const catCols = (CATS.find(c => c.id === catId)?.columns || []).map(c => c.key);
  const allOn = catCols.every(k => STATE.selectedCols.includes(k));
  if (allOn) {
    STATE.selectedCols = STATE.selectedCols.filter(k => !catCols.includes(k));
  } else {
    catCols.forEach(k => { if (!STATE.selectedCols.includes(k)) STATE.selectedCols.push(k); });
  }
  STATE.activePresetId = null; // user departed from a named preset
  _saveState();
}
function isolateCategory(catId) {
  const catCols = (CATS.find(c => c.id === catId)?.columns || []).map(c => c.key);
  STATE.selectedCols = catCols;
  STATE.activePresetId = null;
  _saveState();
}
function setAllCols(value) {
  if (value === 'all') STATE.selectedCols = [...ALL_COL_KEYS];
  else if (value === 'none') STATE.selectedCols = [];
  else if (value === 'default') applyPreset(DEFAULT_PRESET);
  STATE.activePresetId = (value === 'default') ? DEFAULT_PRESET : null;
  _saveState();
}

// ── Column-level operations ────────────────────────────────────────────
function toggleColumn(colKey) {
  const idx = STATE.selectedCols.indexOf(colKey);
  if (idx >= 0) STATE.selectedCols.splice(idx, 1);
  else STATE.selectedCols.push(colKey);
  STATE.activePresetId = null;
  _saveState();
}
function moveColumn(colKey, dir) {
  const idx = STATE.selectedCols.indexOf(colKey);
  if (idx < 0) return;
  const newIdx = dir === 'left' ? idx - 1 : idx + 1;
  if (newIdx < 0 || newIdx >= STATE.selectedCols.length) return;
  [STATE.selectedCols[idx], STATE.selectedCols[newIdx]] = [STATE.selectedCols[newIdx], STATE.selectedCols[idx]];
  STATE.activePresetId = null;
  _saveState();
}
function moveColumnTo(colKey, targetIdx) {
  const idx = STATE.selectedCols.indexOf(colKey);
  if (idx < 0) return;
  STATE.selectedCols.splice(idx, 1);
  const insertAt = Math.max(0, Math.min(STATE.selectedCols.length, targetIdx));
  STATE.selectedCols.splice(insertAt, 0, colKey);
  STATE.activePresetId = null;
  _saveState();
}
function pinColumn(colKey) {
  if (STATE.pinned.includes(colKey)) {
    STATE.pinned = STATE.pinned.filter(k => k !== colKey);
  } else {
    STATE.pinned.push(colKey);
  }
  _saveState();
}
function setSort(colKey) {
  if (STATE.sortBy?.col === colKey) {
    STATE.sortBy = STATE.sortBy.dir === 'desc' ? { col: colKey, dir: 'asc' } : null;
  } else {
    STATE.sortBy = { col: colKey, dir: 'desc' };
  }
  _saveState();
}

// ── Modal: column picker ───────────────────────────────────────────────
let _modalOpen = false;
let _modalSearch = '';
let _draggedColKey = null;

function openModal() { _modalOpen = true; _modalSearch = ''; render(); }
function closeModal() { _modalOpen = false; render(); }

function _renderModal() {
  if (!_modalOpen) return '';
  // Available (Available pane): all columns grouped by category. Filter by search.
  const q = _modalSearch.toLowerCase();
  const matchesSearch = (col) => !q ||
    col.label.toLowerCase().includes(q) || col.key.toLowerCase().includes(q);

  const availPaneHtml = CATS.map(cat => {
    const visible = cat.columns.filter(matchesSearch);
    if (q && !visible.length) return '';
    const selectedInCat = cat.columns.filter(c => STATE.selectedCols.includes(c.key)).length;
    return `
      <div class="cp-cat" data-cat="${cat.id}" style="margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-1);border-radius:4px;border-left:3px solid ${cat.color};cursor:pointer" class="cp-cat-header">
          <span style="font-weight:700;color:${cat.color};font-size:11px;letter-spacing:.04em;text-transform:uppercase">${_esc(cat.label)}</span>
          <span style="margin-left:auto;font-size:10.5px;color:var(--ink-3);font-family:var(--mono)">${selectedInCat} / ${cat.columns.length}</span>
          <button class="cp-cat-add-all" data-cat="${cat.id}" style="background:transparent;border:1px solid ${cat.color};color:${cat.color};padding:2px 6px;font-size:10px;border-radius:3px;cursor:pointer">+ all</button>
        </div>
        <div style="padding-left:12px">
        ${visible.map(col => {
          const checked = STATE.selectedCols.includes(col.key);
          return `
            <label style="display:flex;align-items:center;gap:8px;padding:4px 8px;font-size:11.5px;color:var(--ink-2);cursor:pointer;border-bottom:1px dashed var(--rule)" class="cp-col-row" data-col="${col.key}">
              <input type="checkbox" ${checked ? 'checked' : ''} class="cp-col-cb" data-col="${col.key}" style="cursor:pointer">
              <span style="flex:1;${checked ? 'font-weight:600;color:var(--ink-0)' : ''}">${_esc(col.label)}</span>
              <code style="font-size:10px;color:var(--ink-3)">${_esc(col.key)}</code>
            </label>`;
        }).join('')}
        </div>
      </div>
    `;
  }).join('');

  // Selected (right pane): list with drag handles + remove + pin
  const selectedPaneHtml = STATE.selectedCols.map((key, i) => {
    const col = COL_REGISTRY[key];
    if (!col) return '';
    const pinned = STATE.pinned.includes(key);
    return `
      <div class="cp-sel-row" draggable="true" data-col="${key}" data-idx="${i}" style="display:flex;align-items:center;gap:6px;padding:5px 8px;font-size:11.5px;border-bottom:1px dashed var(--rule);background:var(--bg-0);cursor:grab">
        <span style="color:var(--ink-3);user-select:none">⋮⋮</span>
        <span style="width:6px;height:6px;border-radius:50%;background:${col.catColor};display:inline-block"></span>
        <span style="flex:1;color:var(--ink-0)">${_esc(col.label)}</span>
        <code style="font-size:10px;color:var(--ink-3)">${_esc(col.catLabel)}</code>
        <button class="cp-sel-pin" data-col="${key}" title="${pinned ? 'Unpin' : 'Pin (sticky left)'}" style="background:transparent;border:none;color:${pinned ? 'var(--accent)' : 'var(--ink-3)'};padding:2px 6px;font-size:13px;cursor:pointer">📌</button>
        <button class="cp-sel-remove" data-col="${key}" title="Remove" style="background:transparent;border:none;color:#ef4444;padding:2px 6px;font-size:13px;cursor:pointer">×</button>
      </div>`;
  }).join('') || '<div style="padding:20px;text-align:center;color:var(--ink-3)">No columns selected. Check items in the left pane.</div>';

  return `
    <div id="fields-modal-overlay" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:9998;display:flex;align-items:center;justify-content:center" onclick="if(event.target.id==='fields-modal-overlay')window._fieldsCloseModal()">
      <div style="background:var(--bg-0);border:1px solid var(--rule);border-radius:8px;width:min(1100px,94vw);max-height:88vh;display:flex;flex-direction:column;box-shadow:0 16px 48px rgba(0,0,0,0.5)">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--rule)">
          <div>
            <div style="font-size:14px;font-weight:700;color:var(--ink-0);letter-spacing:.02em">Column Picker</div>
            <div style="font-size:11px;color:var(--ink-3);margin-top:2px">${STATE.selectedCols.length} of ${ALL_COL_KEYS.length} columns selected · drag rows on right to reorder</div>
          </div>
          <button id="cp-close" style="background:transparent;border:none;color:var(--ink-2);font-size:22px;cursor:pointer;padding:0 6px">×</button>
        </div>
        <div style="padding:10px 18px;border-bottom:1px solid var(--rule);display:flex;gap:10px;align-items:center">
          <input id="cp-search" type="text" placeholder="Search ${ALL_COL_KEYS.length} columns by label or key…" value="${_esc(_modalSearch)}" style="flex:1;background:var(--bg-1);color:var(--ink-0);border:1px solid var(--rule);padding:8px 12px;font-size:12px;border-radius:4px">
          <button id="cp-show-all"   style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:6px 10px;font-size:11px;border-radius:3px;cursor:pointer">Show All</button>
          <button id="cp-show-none"  style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:6px 10px;font-size:11px;border-radius:3px;cursor:pointer">Show None</button>
          <button id="cp-reset"      style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:6px 10px;font-size:11px;border-radius:3px;cursor:pointer">Reset to default</button>
        </div>
        <div style="display:grid;grid-template-columns:1.1fr 1fr;gap:0;flex:1;overflow:hidden">
          <div style="overflow-y:auto;padding:12px 14px;border-right:1px solid var(--rule)">
            <div style="font-size:10.5px;color:var(--ink-3);letter-spacing:.06em;text-transform:uppercase;font-weight:700;margin-bottom:8px">Available (${ALL_COL_KEYS.length} cols across ${CATS.length} categories)</div>
            ${availPaneHtml}
          </div>
          <div style="overflow-y:auto;padding:12px 14px;background:linear-gradient(180deg, rgba(34,197,94,0.02), transparent)">
            <div style="font-size:10.5px;color:var(--ink-3);letter-spacing:.06em;text-transform:uppercase;font-weight:700;margin-bottom:8px">Selected & Ordered (${STATE.selectedCols.length})</div>
            <div id="cp-selected-list">${selectedPaneHtml}</div>
          </div>
        </div>
        <div style="padding:12px 18px;border-top:1px solid var(--rule);display:flex;gap:10px;align-items:center;justify-content:space-between">
          <div style="display:flex;gap:8px;align-items:center">
            <input id="cp-save-name" type="text" placeholder="Save current view as preset…" style="background:var(--bg-1);color:var(--ink-0);border:1px solid var(--rule);padding:6px 10px;font-size:11.5px;border-radius:3px;width:240px">
            <button id="cp-save-btn" style="background:var(--accent);color:var(--bg-0);border:none;padding:6px 14px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border-radius:3px;cursor:pointer">Save Preset</button>
          </div>
          <button id="cp-done" style="background:var(--accent);color:var(--bg-0);border:none;padding:8px 22px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;border-radius:3px;cursor:pointer">Done</button>
        </div>
      </div>
    </div>
  `;
}

function _wireModal() {
  if (!_modalOpen) return;
  const onClose = () => closeModal();
  $('cp-close')?.addEventListener('click', onClose);
  $('cp-done')?.addEventListener('click', onClose);
  $('cp-search')?.addEventListener('input', e => {
    _modalSearch = e.target.value;
    // Light re-render of just the modal (keeps focus)
    document.getElementById('fields-modal-overlay')?.remove();
    document.body.insertAdjacentHTML('beforeend', _renderModal());
    _wireModal();
    setTimeout(() => { const el = $('cp-search'); if (el) { el.focus(); el.selectionStart = el.value.length; } }, 0);
  });

  document.querySelectorAll('.cp-col-cb').forEach(cb => {
    cb.addEventListener('change', () => { toggleColumn(cb.dataset.col); render(); });
  });
  document.querySelectorAll('.cp-cat-add-all').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const cat = CATS.find(c => c.id === btn.dataset.cat);
      cat.columns.forEach(c => { if (!STATE.selectedCols.includes(c.key)) STATE.selectedCols.push(c.key); });
      STATE.activePresetId = null;
      _saveState();
      render();
    });
  });
  document.querySelectorAll('.cp-sel-remove').forEach(btn => {
    btn.addEventListener('click', () => { toggleColumn(btn.dataset.col); render(); });
  });
  document.querySelectorAll('.cp-sel-pin').forEach(btn => {
    btn.addEventListener('click', () => { pinColumn(btn.dataset.col); render(); });
  });
  $('cp-show-all')?.addEventListener('click',  () => { setAllCols('all');     render(); });
  $('cp-show-none')?.addEventListener('click', () => { setAllCols('none');    render(); });
  $('cp-reset')?.addEventListener('click',     () => { setAllCols('default'); render(); });

  $('cp-save-btn')?.addEventListener('click', () => {
    const inp = $('cp-save-name');
    if (inp && inp.value.trim()) {
      saveCustomPreset(inp.value.trim());
      inp.value = '';
      render();
    }
  });

  // Drag-and-drop reordering on right pane
  document.querySelectorAll('.cp-sel-row').forEach(row => {
    row.addEventListener('dragstart', e => {
      _draggedColKey = row.dataset.col;
      row.style.opacity = '0.4';
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => { row.style.opacity = '1'; _draggedColKey = null; });
    row.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
    row.addEventListener('drop', e => {
      e.preventDefault();
      if (!_draggedColKey || _draggedColKey === row.dataset.col) return;
      const targetIdx = parseInt(row.dataset.idx, 10);
      moveColumnTo(_draggedColKey, targetIdx);
      render();
    });
  });
}

// ── Column header context menu (Tier 3) ─────────────────────────────────
let _ctxMenuColKey = null;
function _showCtxMenu(colKey, x, y) {
  _hideCtxMenu();
  const col = COL_REGISTRY[colKey];
  if (!col) return;
  _ctxMenuColKey = colKey;
  const pinned = STATE.pinned.includes(colKey);
  const sortInfo = STATE.sortBy?.col === colKey ? STATE.sortBy.dir : null;
  const html = `
    <div id="fields-ctx-menu" style="position:fixed;top:${y}px;left:${x}px;background:var(--bg-0);border:1px solid var(--rule);border-radius:5px;box-shadow:0 8px 24px rgba(0,0,0,0.4);z-index:9999;min-width:200px;font-size:12px;font-family:var(--mono)">
      <div style="padding:8px 12px;font-size:10.5px;color:var(--ink-3);letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid var(--rule)">${_esc(col.label)}</div>
      <div class="ctx-item" data-action="sort-desc" style="padding:8px 12px;cursor:pointer;color:var(--ink-2)${sortInfo === 'desc' ? ';background:var(--bg-1);color:var(--accent)' : ''}">↓ Sort descending</div>
      <div class="ctx-item" data-action="sort-asc"  style="padding:8px 12px;cursor:pointer;color:var(--ink-2)${sortInfo === 'asc'  ? ';background:var(--bg-1);color:var(--accent)' : ''}">↑ Sort ascending</div>
      <div class="ctx-item" data-action="sort-clear" style="padding:8px 12px;cursor:pointer;color:var(--ink-3);border-bottom:1px solid var(--rule)">Clear sort</div>
      <div class="ctx-item" data-action="pin" style="padding:8px 12px;cursor:pointer;color:var(--ink-2)">${pinned ? '📌 Unpin column' : '📌 Pin (sticky left)'}</div>
      <div class="ctx-item" data-action="move-left"  style="padding:8px 12px;cursor:pointer;color:var(--ink-2)">← Move left</div>
      <div class="ctx-item" data-action="move-right" style="padding:8px 12px;cursor:pointer;color:var(--ink-2)">→ Move right</div>
      <div class="ctx-item" data-action="hide" style="padding:8px 12px;cursor:pointer;color:#ef4444;border-top:1px solid var(--rule)">🅧 Hide column</div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
  document.querySelectorAll('.ctx-item').forEach(it => {
    it.addEventListener('click', () => {
      const action = it.dataset.action;
      if (action === 'sort-desc')      STATE.sortBy = { col: colKey, dir: 'desc' };
      else if (action === 'sort-asc')  STATE.sortBy = { col: colKey, dir: 'asc' };
      else if (action === 'sort-clear') STATE.sortBy = null;
      else if (action === 'pin')        pinColumn(colKey);
      else if (action === 'move-left')  moveColumn(colKey, 'left');
      else if (action === 'move-right') moveColumn(colKey, 'right');
      else if (action === 'hide')       toggleColumn(colKey);
      _saveState();
      _hideCtxMenu();
      render();
    });
    it.addEventListener('mouseenter', () => { it.style.background = 'var(--bg-1)'; });
    it.addEventListener('mouseleave', () => { it.style.background = ''; });
  });
  setTimeout(() => document.addEventListener('click', _hideCtxMenu, { once: true }), 0);
}
function _hideCtxMenu() {
  document.getElementById('fields-ctx-menu')?.remove();
  _ctxMenuColKey = null;
}

// ── Main render ─────────────────────────────────────────────────────────
export async function render() {
  const body = $('fieldsBody');
  if (!body) return;
  if (!_TICKERS_ARRAY) body.innerHTML = '<div class="stub">Loading tickers.json…</div>';

  const all = await _loadTickers();
  if (!all.length) {
    body.innerHTML = `<div class="stub">No tickers available (tickers.json empty or not yet fetched).</div>`;
    return;
  }

  const DATA  = getData();
  const scanDate = (DATA?.run_date || DATA?.scan_date || DATA?._meta?.run_date || new Date().toISOString().slice(0, 10));
  const scanTime = (() => {
    const ts = DATA?.run_timestamp || DATA?.scan_time || DATA?.run_time;
    if (!ts) return '—';
    const m = String(ts).match(/(\d{2}:\d{2})/);
    return m ? m[1] : String(ts).slice(-8);
  })();
  const genTs  = new Date();
  const genStr = genTs.toLocaleString('en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    timeZoneName: 'short', hour12: false,
  });

  const filtered = _filteredTickers(all);
  const counts = { all: all.length, BUY: 0, WATCH: 0, SHORT: 0 };
  all.forEach(t => { const v = (t.verdict || '').toUpperCase(); if (v in counts) counts[v]++; });

  // ── Tier 0 preset chips ────────────────────────────────────────────
  const allPresets = { ...PRESETS, ...STATE.customPresets };
  const presetsHtml = Object.entries(allPresets).map(([id, p]) => {
    const active = STATE.activePresetId === id;
    const isCustom = !PRESETS[id];
    return `
      <div class="fields-preset" data-preset="${id}" title="${_esc(p.description || '')}" style="
        display:flex;align-items:center;gap:6px;padding:7px 14px;border-radius:6px;cursor:pointer;
        font-size:11.5px;font-weight:700;letter-spacing:.04em;
        background:${active ? 'var(--accent)' : 'var(--bg-1)'};
        color:${active ? 'var(--bg-0)' : 'var(--ink-0)'};
        border:1px solid ${active ? 'var(--accent)' : 'var(--rule)'};
        transition:all .15s ease">
        <span style="font-size:13px">${p.icon}</span>
        <span>${_esc(p.label)}</span>
        <span style="opacity:.65;font-weight:500;font-size:10.5px">${p.columns.length}</span>
        ${isCustom ? `<button class="fields-preset-del" data-preset="${id}" title="Delete preset" style="background:transparent;border:none;color:inherit;padding:0 2px;font-size:11px;cursor:pointer;opacity:.6">×</button>` : ''}
      </div>`;
  }).join('');

  // ── Tier 1 category chips ─────────────────────────────────────────
  const chipsHtml = CATS.map(c => {
    const catCols = c.columns.map(x => x.key);
    const on = catCols.every(k => STATE.selectedCols.includes(k));
    const partial = !on && catCols.some(k => STATE.selectedCols.includes(k));
    return `
      <div class="field-cat-chip" data-cat="${c.id}" title="Toggle ${c.columns.length} columns" style="
        position:relative;padding:5px 30px 5px 12px;border-radius:14px;font-size:11px;font-weight:700;cursor:pointer;
        letter-spacing:.04em;border:1.5px solid ${c.color};
        background:${on ? c.color : (partial ? c.color + '40' : 'transparent')};
        color:${on ? '#fff' : c.color};
        transition:all .15s ease">
        ${_esc(c.label)} <span style="opacity:.65;font-weight:500">${c.columns.length}</span>
        <button class="field-cat-isolate" data-cat="${c.id}" title="Only this" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);background:transparent;border:none;color:inherit;padding:0 4px;font-size:10px;cursor:pointer;opacity:.5">only</button>
      </div>`;
  }).join('');

  // ── Active columns (in user-defined order, anchors first) ──────────
  const cols = STATE.selectedCols.map(k => COL_REGISTRY[k]).filter(Boolean);
  // Apply pinning: pinned cols move to the front (after ticker anchor)
  const pinnedSet = new Set(STATE.pinned);
  cols.sort((a, b) => {
    const ap = pinnedSet.has(a.key) ? 0 : 1;
    const bp = pinnedSet.has(b.key) ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return STATE.selectedCols.indexOf(a.key) - STATE.selectedCols.indexOf(b.key);
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

      <!-- TIER 0 — Presets -->
      <div style="margin:10px 0 4px 0">
        <span style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)">Presets</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
        ${presetsHtml}
        <div id="fields-add-cols-btn" style="display:flex;align-items:center;gap:6px;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:11.5px;font-weight:700;letter-spacing:.04em;background:transparent;color:var(--accent);border:1px dashed var(--accent)">
          <span style="font-size:13px">+</span>
          <span>Custom (Column Picker)</span>
        </div>
      </div>

      <!-- Search + verdict + export -->
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:10px 0">
        <label style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-0)">Search:</label>
        <input id="fieldsSearch" type="text" placeholder="ticker or name…" value="${_esc(STATE.searchTerm)}" style="background:var(--bg-1);color:var(--ink-0);border:1px solid var(--rule);padding:5px 9px;font-family:var(--mono);font-size:12px;border-radius:3px;min-width:200px" />

        <label style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-0);margin-left:14px">Verdict:</label>
        <div style="display:flex;gap:4px">
          ${['all', 'BUY', 'WATCH', 'SHORT'].map(v => `
            <div class="fields-verdict-chip" data-verdict="${v}" style="
              padding:5px 12px;border-radius:14px;font-size:11px;font-weight:700;cursor:pointer;
              letter-spacing:.04em;border:1.5px solid var(--rule);
              background:${STATE.verdictFilter === v ? 'var(--accent)' : 'transparent'};
              color:${STATE.verdictFilter === v ? 'var(--bg-0)' : 'var(--ink-2)'}">
              ${v}  ${counts[v] != null ? '<span style="opacity:.7;font-weight:500">' + counts[v] + '</span>' : ''}
            </div>`).join('')}
        </div>

        <button id="fieldsExport" style="margin-left:auto;background:var(--accent);color:var(--bg-0);border:none;padding:6px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;cursor:pointer;border-radius:4px;text-transform:uppercase">Export CSV</button>
      </div>

      <!-- TIER 1 — Category chips + bulk actions -->
      <div style="display:flex;align-items:center;gap:10px;margin:10px 0 6px 0">
        <span style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)">Categories (${CATS.length})</span>
        <div style="display:flex;gap:6px">
          <button class="fields-bulk-btn" data-bulk="all"     style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:3px 9px;font-size:10.5px;border-radius:11px;cursor:pointer">All</button>
          <button class="fields-bulk-btn" data-bulk="none"    style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:3px 9px;font-size:10.5px;border-radius:11px;cursor:pointer">None</button>
          <button class="fields-bulk-btn" data-bulk="default" style="background:transparent;color:var(--ink-2);border:1px solid var(--rule);padding:3px 9px;font-size:10.5px;border-radius:11px;cursor:pointer">Reset to default</button>
        </div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px">${chipsHtml}</div>
    </div>
  `;

  // ── Table ─────────────────────────────────────────────────────────
  const sortGlyph = (k) => STATE.sortBy?.col === k ? (STATE.sortBy.dir === 'desc' ? ' ↓' : ' ↑') : '';
  const headerCells = [
    `<th style="position:sticky;left:0;z-index:3;background:var(--bg-1);text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:70px;border-right:1px solid var(--rule)">Ticker</th>`,
    `<th style="text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:90px">Date</th>`,
    `<th style="text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:70px">Scan Time</th>`,
    ...cols.map((c, ci) => {
      const pinned = pinnedSet.has(c.key);
      const pinStyle = pinned ? `position:sticky;left:${70 + 90 + 70 + ci * 110}px;z-index:2;background:var(--bg-1);box-shadow:inset 2px 0 0 ${c.catColor};` : '';
      return `
        <th class="fields-col-header" data-col="${c.key}" title="${_esc(c.catLabel)} — right-click for options"
            style="${pinStyle};text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);min-width:${c.narrow ? '60' : '110'}px;border-top:2px solid ${c.catColor};cursor:context-menu;user-select:none">
          ${_esc(c.label)}${sortGlyph(c.key)}
        </th>`;
    }),
  ].join('');

  const bodyRows = filtered.map(t => {
    const tk = _esc(t.ticker);
    const cells = [
      `<td style="position:sticky;left:0;z-index:1;background:var(--bg-0);padding:0;border-right:1px solid var(--rule)">
         <a href="elite-detail.html?t=${tk}&from=fields" title="Open ${tk} detail view"
            style="display:block;padding:6px 10px;font-family:var(--mono);font-weight:700;color:var(--accent);text-decoration:none;cursor:pointer"
            onmouseover="this.style.background='var(--bg-1)'"
            onmouseout="this.style.background='var(--bg-0)'">${tk} →</a>
       </td>`,
      `<td style="padding:6px 10px;font-family:var(--mono);color:var(--ink-2);font-size:11px">${_esc(scanDate)}</td>`,
      `<td style="padding:6px 10px;font-family:var(--mono);color:var(--ink-2);font-size:11px">${_esc(scanTime)}</td>`,
      ...cols.map(c => {
        let v; try { v = c.accessor(t); } catch (e) { v = undefined; }
        return `<td style="padding:6px 10px;font-family:var(--mono);font-size:11.5px;color:var(--ink-0);white-space:nowrap">${_esc(_fmt(v))}</td>`;
      }),
    ].join('');
    return `<tr style="border-bottom:1px dashed var(--rule)">${cells}</tr>`;
  }).join('');

  const tableHtml = cols.length === 0 ? `
    <div class="card" style="text-align:center;padding:30px;color:var(--ink-3)">
      No columns selected. Pick a preset above, click a category chip, or open the Column Picker.
    </div>
  ` : `
    <div class="card" style="overflow-x:auto;padding:0">
      <table style="width:max-content;min-width:100%;border-collapse:collapse">
        <thead><tr style="border-bottom:2px solid var(--rule);background:var(--bg-1)">${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;

  body.innerHTML = toolbarHtml + tableHtml;

  // Modal painted into body (outside the tab panel so overlay is correct)
  const oldModal = document.getElementById('fields-modal-overlay');
  if (oldModal) oldModal.remove();
  if (_modalOpen) {
    document.body.insertAdjacentHTML('beforeend', _renderModal());
    _wireModal();
  }

  // ── Wiring ─────────────────────────────────────────────────────────
  $('fieldsSearch').oninput = e => { STATE.searchTerm = e.target.value; _saveState(); render(); };
  document.querySelectorAll('.fields-verdict-chip').forEach(el => {
    el.onclick = () => { STATE.verdictFilter = el.dataset.verdict; _saveState(); render(); };
  });
  document.querySelectorAll('.fields-preset').forEach(el => {
    el.onclick = (e) => {
      if (e.target.classList.contains('fields-preset-del')) return;
      applyPreset(el.dataset.preset);
      render();
    };
  });
  document.querySelectorAll('.fields-preset-del').forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      if (confirm(`Delete preset "${STATE.customPresets[btn.dataset.preset].label}"?`)) {
        deleteCustomPreset(btn.dataset.preset);
        render();
      }
    };
  });
  $('fields-add-cols-btn').onclick = () => openModal();
  document.querySelectorAll('.fields-bulk-btn').forEach(btn => {
    btn.onclick = () => { setAllCols(btn.dataset.bulk); render(); };
  });
  document.querySelectorAll('.field-cat-chip').forEach(el => {
    el.onclick = (e) => {
      if (e.target.classList.contains('field-cat-isolate')) return;
      toggleCategory(el.dataset.cat); render();
    };
  });
  document.querySelectorAll('.field-cat-isolate').forEach(btn => {
    btn.onclick = (e) => { e.stopPropagation(); isolateCategory(btn.dataset.cat); render(); };
  });

  // Column header context menu (right-click + left-click sort)
  document.querySelectorAll('.fields-col-header').forEach(el => {
    el.addEventListener('click', e => {
      if (e.button !== 0) return;
      setSort(el.dataset.col); render();
    });
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      _showCtxMenu(el.dataset.col, e.clientX, e.clientY);
    });
  });

  // Make context-menu close work from outside (escape, click outside) — added as window helper
  window._fieldsCloseModal = closeModal;

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

export function dispose() {
  // Persist user state on tab switch (already happens on every change)
  _hideCtxMenu();
  document.getElementById('fields-modal-overlay')?.remove();
}
