// ════════════════════════════════════════════════════════════════════════
// qd_checklist.js · QDChecklist namespace · live BUY-decision audit overlay
// ════════════════════════════════════════════════════════════════════════
// Adds a slide-out right panel that evaluates ~50 rules against the active
// ticker and renders pass/amber/fail/n-a pills with the actual values.
// Final tally maps to FULL / HALF / WATCH / SKIP size recommendation.
//
// Usage from kairos.html:
//     window.QDChecklist.open(currentTickerObject)
// Keyboard:  Shift+C   to toggle from anywhere
// ════════════════════════════════════════════════════════════════════════

window.QDChecklist = (function() {
  'use strict';

  // ─── Field accessors (defensive against missing/null) ─────────────────
  const _num = (t, ...paths) => {
    for (const p of paths) {
      const parts = p.split('.');
      let v = t;
      for (const k of parts) { if (v == null) break; v = v[k]; }
      if (v != null && v !== '' && isFinite(+v)) return +v;
    }
    return null;
  };
  const _str = (t, ...paths) => {
    for (const p of paths) {
      const parts = p.split('.');
      let v = t;
      for (const k of parts) { if (v == null) break; v = v[k]; }
      if (v != null && v !== '') return String(v);
    }
    return null;
  };

  // Status helpers — every evaluator returns {status, value, detail?}
  const PASS  = (value, detail) => ({ status: 'pass',  value, detail });
  const AMBER = (value, detail) => ({ status: 'amber', value, detail });
  const FAIL  = (value, detail) => ({ status: 'fail',  value, detail });
  const NA    = (note)         => ({ status: 'na',    value: '—', detail: note || 'needs data' });

  // Regime-conditional score floor
  const _regimeFloor = (t) => {
    const reg = (_str(t, 'regime', 'decision.regime') || '').toLowerCase();
    if (reg.includes('panic')) return 999;
    if (reg.includes('risk_off')) return 78;
    if (reg.includes('chop')) return 72;
    return 65;
  };

  // ─── RULES · 50+ evaluators · grouped by tab ──────────────────────────
  const RULES = [
    // ═══════ 1 · Overview ═══════
    { tab: 'overview', kbd: '1', label: 'Verdict pill',
      threshold: 'BUY',
      evaluate: (t) => {
        const v = (_str(t, 'decision.verdict', 'verdict') || '').toUpperCase();
        if (v === 'BUY') return PASS(v);
        if (v === 'WATCH') return AMBER(v, 'pipeline says wait');
        if (v === 'AVOID' || v === 'SHORT' || v === 'SELL') return FAIL(v, 'pipeline says no');
        return NA('no verdict in payload');
      }},
    { tab: 'overview', kbd: '1', label: 'Composite score',
      threshold: '≥ regime floor',
      evaluate: (t) => {
        const sc = _num(t, 'score') || 0;
        const fl = _regimeFloor(t);
        if (sc === 0) return NA('no score');
        if (fl === 999) return FAIL(`${sc} (PANIC regime)`, 'no longs in panic');
        if (sc >= fl) return PASS(`${sc.toFixed(0)} ≥ ${fl}`);
        return FAIL(`${sc.toFixed(0)} < ${fl}`, `below ${fl} floor for current regime`);
      }},
    { tab: 'overview', kbd: '1', label: 'Conviction tier',
      threshold: 'T1 or T2',
      evaluate: (t) => {
        const ct = _str(t, 'conviction_tier', 'tier') || '';
        if (ct === 'T1') return PASS('T1', 'full size');
        if (ct === 'T2') return PASS('T2', 'half size');
        if (ct === 'T3') return AMBER('T3', 'monitor only');
        if (ct === 'WATCH') return AMBER('WATCH');
        return NA('not classified');
      }},
    { tab: 'overview', kbd: '1', label: 'Setup family named',
      threshold: 'mechanism-based',
      evaluate: (t) => {
        const sf = _str(t, 'setup_family', 'setup') || '';
        const trusted = /vcp|pead|pullback|squeeze|breakout|trend.continu|impulse/i.test(sf);
        if (!sf) return AMBER('—', 'unclassified');
        if (trusted) return PASS(sf.replace(/_/g, ' '));
        return AMBER(sf.replace(/_/g, ' '), 'generic setup');
      }},
    { tab: 'overview', kbd: '1', label: 'Regime',
      threshold: 'risk_on_*',
      evaluate: (t) => {
        const r = (_str(t, 'regime', 'decision.regime') || '').toLowerCase();
        if (!r) return NA('no regime');
        if (r.includes('panic')) return FAIL('PANIC', 'no longs');
        if (r.includes('risk_off')) return AMBER('RISK_OFF', 'reduce size');
        if (r.includes('risk_on')) return PASS(r.toUpperCase().replace(/_/g, ' '));
        return AMBER(r);
      }},

    // ═══════ 2 · Plan · Ticket ═══════
    { tab: 'plan', kbd: '2', label: 'R-multiple to T1',
      threshold: '≥ 2.0R',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const stop = _num(t, 'stop') || 0;
        const t1 = _num(t, 'target1', 't1') || 0;
        if (!px || !stop || !t1 || stop >= px) return NA('missing levels');
        const r = (t1 - px) / (px - stop);
        if (r >= 2) return PASS(`+${r.toFixed(2)}R`);
        if (r >= 1.5) return AMBER(`+${r.toFixed(2)}R`, 'thin');
        return FAIL(`+${r.toFixed(2)}R`, '< 2R math broken');
      }},
    { tab: 'plan', kbd: '2', label: 'R-multiple to T2',
      threshold: '≥ 3.0R',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const stop = _num(t, 'stop') || 0;
        const t2 = _num(t, 'target2', 't2') || 0;
        if (!px || !stop || !t2 || stop >= px) return NA();
        const r = (t2 - px) / (px - stop);
        if (r >= 3) return PASS(`+${r.toFixed(2)}R`);
        if (r >= 2.5) return AMBER(`+${r.toFixed(2)}R`);
        return FAIL(`+${r.toFixed(2)}R`, '< 3R');
      }},
    { tab: 'plan', kbd: '2', label: 'Stop distance %',
      threshold: '≤ 8%',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const stop = _num(t, 'stop') || 0;
        if (!px || !stop) return NA();
        const pct = ((px - stop) / px) * 100;
        if (pct <= 5) return PASS(`−${pct.toFixed(1)}%`);
        if (pct <= 8) return AMBER(`−${pct.toFixed(1)}%`, 'wide');
        return FAIL(`−${pct.toFixed(1)}%`, 'stop too wide');
      }},
    { tab: 'plan', kbd: '2', label: 'Kelly-lite size %',
      threshold: '≥ 4% (T1) / ≥ 2% (T2)',
      evaluate: (t) => {
        const sz = _num(t, 'kelly_size.size_pct_equity', 'earnings_beat_prediction.breakdown.kelly_sizing.size_pct_equity');
        if (sz == null) return NA();
        const pct = sz * 100;
        if (pct >= 4) return PASS(`${pct.toFixed(2)}%`);
        if (pct >= 2) return AMBER(`${pct.toFixed(2)}%`, 'half-size territory');
        if (pct >= 1) return AMBER(`${pct.toFixed(2)}%`, 'sub-threshold');
        return FAIL(`${pct.toFixed(2)}%`, 'no edge');
      }},
    { tab: 'plan', kbd: '2', label: 'Hold window',
      threshold: '5–21 days',
      evaluate: (t) => {
        const d = _num(t, 'max_hold_days', 'trade_plan.max_hold_days') || 0;
        if (!d) return NA();
        if (d >= 5 && d <= 21) return PASS(`${d}d`);
        if (d > 21) return AMBER(`${d}d`, 'long for swing');
        return AMBER(`${d}d`, 'short window');
      }},
    { tab: 'plan', kbd: '2', label: 'Entry quality',
      threshold: 'FRESH / PULLBACK / VALID',
      evaluate: (t) => {
        const eq = (_str(t, 'entry_quality') || '').toUpperCase();
        if (eq === 'FRESH') return PASS('FRESH', 'optimal');
        if (eq === 'PULLBACK' || eq === 'VALID') return PASS(eq);
        if (eq === 'EXTENDED') return AMBER('EXTENDED', 'reduce size');
        if (eq === 'MISSED') return FAIL('MISSED', 'wait for pullback');
        return NA();
      }},

    // ═══════ 3 · Technicals ═══════
    { tab: 'chart', kbd: '3', label: 'EMA stack bullish',
      threshold: 'EMA8 > 21 > 50 > 200',
      evaluate: (t) => {
        const e8  = _num(t, 'technicals.indicators.ema8', 'ema8');
        const e21 = _num(t, 'technicals.indicators.ema21', 'ema21');
        const e50 = _num(t, 'technicals.indicators.ema50', 'ema50');
        const e200= _num(t, 'technicals.indicators.ema200', 'ema200');
        if (!e8 || !e21 || !e50 || !e200) return NA();
        if (e8 > e21 && e21 > e50 && e50 > e200) return PASS(`${e8.toFixed(2)} > ${e21.toFixed(2)} > ${e50.toFixed(2)} > ${e200.toFixed(2)}`);
        if (e50 > e200) return AMBER('partial · EMA50 > EMA200');
        return FAIL('inverted', 'trend not intact');
      }},
    { tab: 'chart', kbd: '3', label: 'Price above EMA50',
      threshold: 'spot > EMA50',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const e50 = _num(t, 'technicals.indicators.ema50', 'ema50');
        if (!px || !e50) return NA();
        const dist = ((px - e50) / e50) * 100;
        if (px > e50) return PASS(`+${dist.toFixed(1)}%`);
        return FAIL(`${dist.toFixed(1)}%`, 'below EMA50 = no long');
      }},
    { tab: 'chart', kbd: '3', label: 'RSI(14) momentum zone',
      threshold: '50–75',
      evaluate: (t) => {
        const r = _num(t, 'technicals.indicators.rsi', 'rsi');
        if (r == null) return NA();
        if (r >= 50 && r <= 75) return PASS(r.toFixed(1));
        if (r > 75 && r <= 80) return AMBER(r.toFixed(1), 'getting hot');
        if (r > 80) return FAIL(r.toFixed(1), 'overbought');
        if (r >= 40) return AMBER(r.toFixed(1), 'no momentum');
        return FAIL(r.toFixed(1), 'weak');
      }},
    { tab: 'chart', kbd: '3', label: 'ADX trending',
      threshold: '≥ 25',
      evaluate: (t) => {
        const a = _num(t, 'technicals.indicators.adx', 'adx');
        if (a == null) return NA();
        if (a >= 25) return PASS(a.toFixed(1));
        if (a >= 20) return AMBER(a.toFixed(1), 'developing');
        return FAIL(a.toFixed(1), 'range/chop');
      }},
    { tab: 'chart', kbd: '3', label: 'ATR % tradeable',
      threshold: '1.5–4%',
      evaluate: (t) => {
        const a = _num(t, 'technicals.indicators.atr_pct', 'atr_pct');
        if (a == null) return NA();
        if (a >= 1.5 && a <= 4) return PASS(`${a.toFixed(2)}%`);
        if (a < 1.5) return AMBER(`${a.toFixed(2)}%`, 'too tight');
        if (a > 6) return FAIL(`${a.toFixed(2)}%`, 'too volatile');
        return AMBER(`${a.toFixed(2)}%`, 'high vol');
      }},
    { tab: 'chart', kbd: '3', label: 'RVOL (relative volume)',
      threshold: '≥ 1.5×',
      evaluate: (t) => {
        const rv = _num(t, 'technicals.indicators.rvol', 'rvol');
        if (rv == null) return NA();
        if (rv >= 1.5) return PASS(`${rv.toFixed(2)}×`);
        if (rv >= 1.0) return AMBER(`${rv.toFixed(2)}×`, 'normal');
        return FAIL(`${rv.toFixed(2)}×`, 'dry-up');
      }},
    { tab: 'chart', kbd: '3', label: 'MACD bullish',
      threshold: 'histogram > 0',
      evaluate: (t) => {
        const h = _num(t, 'technicals.indicators.macd_hist', 'macd_hist');
        const b = t.technicals?.indicators?.macd_bullish ?? t.macd_bullish;
        if (h == null && b == null) return NA();
        if (b === true || (h != null && h > 0)) return PASS('BULL');
        return FAIL('BEAR');
      }},
    { tab: 'chart', kbd: '3', label: 'RS rank',
      threshold: '≥ 70',
      evaluate: (t) => {
        const r = _num(t, 'technicals.indicators.rs_rank', 'rs_rank');
        if (r == null) return NA();
        if (r >= 80) return PASS(r.toFixed(0), 'leader');
        if (r >= 70) return PASS(r.toFixed(0));
        if (r >= 50) return AMBER(r.toFixed(0), 'middling');
        return FAIL(r.toFixed(0), 'laggard');
      }},

    // ═══════ V · Investment · Value ═══════
    { tab: 'value', kbd: 'V', label: 'Forward P/E',
      threshold: '≤ 30 growth · ≤ 20 value',
      evaluate: (t) => {
        const pe = _num(t, 'forward_pe', 'fund_details.forward_pe');
        if (pe == null) return NA();
        if (pe <= 25) return PASS(pe.toFixed(1));
        if (pe <= 50) return AMBER(pe.toFixed(1), 'rich');
        return FAIL(pe.toFixed(1), 'expensive');
      }},
    { tab: 'value', kbd: 'V', label: 'PEG ratio',
      threshold: '≤ 1.5',
      evaluate: (t) => {
        const p = _num(t, 'fund_details.peg', 'peg');
        if (p == null) return NA();
        if (p <= 1.0) return PASS(p.toFixed(2));
        if (p <= 1.5) return PASS(p.toFixed(2));
        if (p <= 2.0) return AMBER(p.toFixed(2), 'paying ahead');
        return FAIL(p.toFixed(2));
      }},
    { tab: 'value', kbd: 'V', label: 'Revenue growth YoY',
      threshold: '≥ 15%',
      evaluate: (t) => {
        const g = _num(t, 'rev_growth', 'fund_details.revenue_growth');
        if (g == null) return NA();
        const p = g >= 1 ? g : g * 100;
        if (p >= 25) return PASS(`+${p.toFixed(1)}%`, 'strong');
        if (p >= 15) return PASS(`+${p.toFixed(1)}%`);
        if (p >= 5)  return AMBER(`+${p.toFixed(1)}%`, 'moderate');
        return FAIL(`${p.toFixed(1)}%`, 'weak');
      }},
    { tab: 'value', kbd: 'V', label: 'ROE',
      threshold: '≥ 15%',
      evaluate: (t) => {
        const r = _num(t, 'fund_details.roe', 'roe');
        if (r == null) return NA();
        const p = r >= 1 ? r : r * 100;
        if (p >= 20) return PASS(`${p.toFixed(1)}%`, 'compounder');
        if (p >= 15) return PASS(`${p.toFixed(1)}%`);
        if (p >= 8)  return AMBER(`${p.toFixed(1)}%`);
        if (p > 0)   return FAIL(`${p.toFixed(1)}%`, 'sub-par');
        return FAIL(`${p.toFixed(1)}%`, 'destroying value');
      }},
    { tab: 'value', kbd: 'V', label: 'Gross margin',
      threshold: '≥ 40%',
      evaluate: (t) => {
        const m = _num(t, 'fund_details.gross_margin', 'gross_margin');
        if (m == null) return NA();
        const p = m >= 1 ? m : m * 100;
        if (p >= 50) return PASS(`${p.toFixed(1)}%`, 'pricing power');
        if (p >= 40) return PASS(`${p.toFixed(1)}%`);
        if (p >= 25) return AMBER(`${p.toFixed(1)}%`);
        return FAIL(`${p.toFixed(1)}%`, 'commoditized');
      }},
    { tab: 'value', kbd: 'V', label: 'Debt / Equity',
      threshold: '≤ 1.5',
      evaluate: (t) => {
        const d = _num(t, 'fund_details.debt_to_equity', 'debt_to_equity');
        if (d == null) return NA();
        if (d <= 1.0) return PASS(d.toFixed(2));
        if (d <= 1.5) return PASS(d.toFixed(2));
        if (d <= 3.0) return AMBER(d.toFixed(2), 'leveraged');
        return FAIL(d.toFixed(2), 'over-leveraged');
      }},
    { tab: 'value', kbd: 'V', label: 'Analyst upside %',
      threshold: '≥ 10%',
      evaluate: (t) => {
        const u = _num(t, 'analyst_full.upside_pct', 'analyst.upside_pct', 'analyst_upside');
        if (u == null) return NA();
        if (u >= 15) return PASS(`+${u.toFixed(1)}%`);
        if (u >= 10) return PASS(`+${u.toFixed(1)}%`);
        if (u >= 0)  return AMBER(`+${u.toFixed(1)}%`, 'thin');
        return FAIL(`${u.toFixed(1)}%`, 'below consensus');
      }},

    // ═══════ R · Risk ═══════
    { tab: 'risk', kbd: 'R', label: 'CVaR 5d (forward dist)',
      threshold: '≥ −15%',
      evaluate: (t) => {
        const c = _num(t, 'forward_dist.cvar_975_pct', 'forward_dist.tail_loss_pct');
        if (c == null) return NA();
        if (c >= -8) return PASS(`${c.toFixed(1)}%`);
        if (c >= -15) return AMBER(`${c.toFixed(1)}%`);
        return FAIL(`${c.toFixed(1)}%`, 'un-survivable tail');
      }},
    { tab: 'risk', kbd: 'R', label: 'VaR 5d (95%)',
      threshold: '≥ −8%',
      evaluate: (t) => {
        const v = _num(t, 'forward_dist.var_95_pct', 'forward_dist.var_95');
        if (v == null) return NA();
        if (v >= -5) return PASS(`${v.toFixed(1)}%`);
        if (v >= -8) return PASS(`${v.toFixed(1)}%`);
        return AMBER(`${v.toFixed(1)}%`, 'wide');
      }},
    { tab: 'risk', kbd: 'R', label: 'Beta',
      threshold: '≤ 1.5',
      evaluate: (t) => {
        const b = _num(t, 'beta');
        if (b == null) return NA();
        if (b <= 1.5) return PASS(b.toFixed(2));
        if (b <= 2.0) return AMBER(b.toFixed(2), 'high-beta');
        return FAIL(b.toFixed(2), 'amplifies portfolio β');
      }},
    { tab: 'risk', kbd: 'R', label: 'ADV liquidity',
      threshold: '≥ $5M',
      evaluate: (t) => {
        const a = _num(t, 'adv_dollar', 'dollar_volume_avg', 'adv') || _num(t, 'avg_volume') * (_num(t, 'price') || 0);
        if (!a) return NA();
        if (a >= 50e6) return PASS('$' + (a/1e6).toFixed(0) + 'M', 'ample');
        if (a >= 10e6) return PASS('$' + (a/1e6).toFixed(0) + 'M');
        if (a >= 5e6)  return AMBER('$' + (a/1e6).toFixed(0) + 'M');
        return FAIL('$' + (a/1e6).toFixed(1) + 'M', 'thin');
      }},

    // ═══════ E · Earnings ═══════
    { tab: 'er_lab', kbd: 'E', label: 'ER blackout window',
      threshold: '> 14d or post-ER',
      evaluate: (t) => {
        const d = _num(t, 'earn_days');
        if (d == null) return NA('no ER date');
        if (d > 14) return PASS(`+${d}d`);
        if (d < -1) return PASS(`${d}d (post-ER)`, 'PEAD window');
        if (d >= 0 && d <= 14) return FAIL(`+${d}d`, 'BLOCKED · swing blackout');
        return AMBER(`${d}d`);
      }},
    { tab: 'er_lab', kbd: 'E', label: 'Zacks ESP',
      threshold: '≥ +1.0',
      evaluate: (t) => {
        const e = _num(t, 'zacks_earnings_esp');
        if (e == null) return NA();
        if (e >= 1) return PASS(`+${e.toFixed(2)}`);
        if (e >= 0) return AMBER(`+${e.toFixed(2)}`, 'thin');
        return FAIL(e.toFixed(2), 'negative surprise odds');
      }},
    { tab: 'er_lab', kbd: 'E', label: '8q beat rate',
      threshold: '≥ 75%',
      evaluate: (t) => {
        const b = _num(t, 'earnings_beat', 'earnings_beat_prediction.breakdown.historical.rate');
        if (b == null) return NA();
        if (b >= 75) return PASS(`${b.toFixed(0)}%`);
        if (b >= 50) return AMBER(`${b.toFixed(0)}%`);
        return FAIL(`${b.toFixed(0)}%`);
      }},
    { tab: 'er_lab', kbd: 'E', label: 'EPS revision trend',
      threshold: 'BULLISH',
      evaluate: (t) => {
        const dir = _str(t, 'earnings_beat_prediction.breakdown.revision_trend.direction');
        if (!dir) return NA();
        if (dir === 'BULLISH') return PASS(dir);
        if (dir === 'NEUTRAL') return AMBER(dir);
        return FAIL(dir, 'analysts cutting');
      }},

    // ═══════ O · Options ═══════
    { tab: 'options', kbd: 'O', label: 'IV rank (52w)',
      threshold: '30–70',
      evaluate: (t) => {
        const i = _num(t, 'iv_rank', 'options_kpis.iv_percentile');
        if (i == null) return NA();
        if (i >= 30 && i <= 70) return PASS(`${i.toFixed(0)}%`);
        if (i < 30) return PASS(`${i.toFixed(0)}%`, 'cheap · directional');
        if (i <= 80) return AMBER(`${i.toFixed(0)}%`, 'elevated');
        return AMBER(`${i.toFixed(0)}%`, 'expensive');
      }},
    { tab: 'options', kbd: 'O', label: 'P/C ratio (OI)',
      threshold: '≤ 1.0',
      evaluate: (t) => {
        const p = _num(t, 'put_call_oi', 'options_kpis.put_call_ratio');
        if (p == null) return NA();
        if (p <= 0.85) return PASS(p.toFixed(2), 'call-lean');
        if (p <= 1.0)  return PASS(p.toFixed(2));
        if (p <= 1.3)  return AMBER(p.toFixed(2));
        return FAIL(p.toFixed(2), 'hedging dominant');
      }},
    { tab: 'options', kbd: 'O', label: 'UOA calls',
      threshold: '≥ 3 strikes',
      evaluate: (t) => {
        const c = _num(t, 'uoa_calls', 'options_kpis.uoa_calls');
        if (c == null) return NA();
        if (c >= 3) return PASS(`${c} strikes`);
        if (c >= 1) return AMBER(`${c} strikes`);
        return AMBER('0', 'no unusual flow');
      }},
    { tab: 'options', kbd: 'O', label: 'UOA puts',
      threshold: '≤ 2 strikes (for bull)',
      evaluate: (t) => {
        const p = _num(t, 'uoa_puts', 'options_kpis.uoa_puts');
        if (p == null) return NA();
        if (p <= 1) return PASS(`${p} strikes`);
        if (p <= 2) return AMBER(`${p} strikes`);
        return FAIL(`${p} strikes`, 'institutional shorts');
      }},
    { tab: 'options', kbd: 'O', label: 'Expected move vs stop',
      threshold: 'EM ≤ stop distance',
      evaluate: (t) => {
        const im = _num(t, 'implied_move_pct', 'options_kpis.implied_move_pct');
        const px = _num(t, 'price') || 0;
        const stop = _num(t, 'stop') || 0;
        if (im == null || !px || !stop) return NA();
        const stopPct = ((px - stop) / px) * 100;
        if (im <= stopPct) return PASS(`±${im.toFixed(1)}% ≤ stop ${stopPct.toFixed(1)}%`);
        return AMBER(`±${im.toFixed(1)}% > stop ${stopPct.toFixed(1)}%`, 'vol exceeds risk budget');
      }},

    // ═══════ P · Portfolio ═══════
    { tab: 'portfolio', kbd: 'P', label: 'Position size sanity',
      threshold: 'Kelly ≤ 10%',
      evaluate: (t) => {
        const sz = _num(t, 'kelly_size.size_pct_equity');
        if (sz == null) return NA();
        const pct = sz * 100;
        if (pct <= 10) return PASS(`${pct.toFixed(2)}%`);
        return AMBER(`${pct.toFixed(2)}%`, 'large');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Correlation w/ existing book',
      threshold: 'avg ρ ≤ 0.60',
      evaluate: (t) => NA('needs portfolio.json wire') },
    { tab: 'portfolio', kbd: 'P', label: 'Sleep test',
      threshold: 'GREEN',
      evaluate: (t) => NA('subjective · review') },

    // ═══════ I · Tape · Flow ═══════
    { tab: 'intel', kbd: 'I', label: 'Insider net buying (30d)',
      threshold: 'positive OR no major selling',
      evaluate: (t) => {
        const b = _num(t, 'insider_full.recent_buys', 'earnings_beat_prediction.breakdown.insider.buy_count');
        const s = _num(t, 'insider_full.recent_sells', 'earnings_beat_prediction.breakdown.insider.sell_count');
        const netD = _num(t, 'earnings_beat_prediction.breakdown.insider.net_dollars');
        if (b == null && s == null && netD == null) return NA();
        if (netD != null) {
          if (netD > 0) return PASS(`+$${(netD/1000).toFixed(0)}k`, 'accumulating');
          if (netD > -1e6) return AMBER(`$${(netD/1000).toFixed(0)}k`, 'minor selling');
          return FAIL(`$${(netD/1000).toFixed(0)}k`, 'major distribution');
        }
        if ((b || 0) > (s || 0)) return PASS(`${b}B · ${s||0}S`);
        return AMBER(`${b||0}B · ${s}S`);
      }},
    { tab: 'intel', kbd: 'I', label: 'Institutional ownership %',
      threshold: '60–85%',
      evaluate: (t) => {
        const p = _num(t, 'institutional.percent_institutions', 'percent_institutions');
        if (p == null) return NA();
        if (p >= 60 && p <= 85) return PASS(`${p.toFixed(1)}%`);
        if (p > 85) return AMBER(`${p.toFixed(1)}%`, 'crowded');
        if (p >= 40) return AMBER(`${p.toFixed(1)}%`, 'thin');
        return FAIL(`${p.toFixed(1)}%`, 'retail-driven');
      }},
    { tab: 'intel', kbd: 'I', label: 'News sentiment trend',
      threshold: 'IMPROVING',
      evaluate: (t) => {
        const dir = _str(t, 'eodhd_sentiment.trend');
        if (!dir) return NA();
        if (dir === 'IMPROVING') return PASS(dir);
        if (dir === 'STABLE') return AMBER(dir);
        if (dir === 'DETERIORATING') return FAIL(dir);
        return AMBER(dir);
      }},
    { tab: 'intel', kbd: 'I', label: 'Short float %',
      threshold: '5–15%',
      evaluate: (t) => {
        const s = _num(t, 'short_pct_float', 'fund_details.short_pct_float');
        if (s == null) return NA();
        if (s >= 5 && s <= 15) return PASS(`${s.toFixed(1)}%`, 'squeeze fuel');
        if (s < 5) return AMBER(`${s.toFixed(1)}%`, 'no squeeze');
        if (s <= 20) return AMBER(`${s.toFixed(1)}%`, 'elevated');
        return FAIL(`${s.toFixed(1)}%`, 'overcrowded short');
      }},

    // ═══════ 7 · Track Record · Edge ═══════
    { tab: 'edge', kbd: '7', label: 'Setup win rate',
      threshold: '≥ 55%',
      evaluate: (t) => {
        const w = _num(t, '_setup_wr');
        if (w == null) return NA();
        const p = w * 100;
        if (p >= 60) return PASS(`${p.toFixed(0)}%`);
        if (p >= 55) return PASS(`${p.toFixed(0)}%`);
        if (p >= 50) return AMBER(`${p.toFixed(0)}%`, 'borderline');
        return FAIL(`${p.toFixed(0)}%`);
      }},
    { tab: 'edge', kbd: '7', label: 'Wilson 95% LB',
      threshold: '≥ 50%',
      evaluate: (t) => {
        const lb = _num(t, '_setup_wilson_lb');
        if (lb == null) return NA();
        const p = lb * 100;
        if (p >= 55) return PASS(`${p.toFixed(0)}%`);
        if (p >= 50) return PASS(`${p.toFixed(0)}%`);
        if (p >= 40) return AMBER(`${p.toFixed(0)}%`);
        return FAIL(`${p.toFixed(0)}%`, 'below honest floor');
      }},
    { tab: 'edge', kbd: '7', label: 'N trades (sample)',
      threshold: '≥ 30',
      evaluate: (t) => {
        const n = _num(t, '_setup_n');
        if (n == null) return NA();
        if (n >= 30) return PASS(`n=${n}`);
        if (n >= 10) return AMBER(`n=${n}`, 'thin');
        return FAIL(`n=${n}`, 'too noisy');
      }},
    { tab: 'edge', kbd: '7', label: 'Profit factor',
      threshold: '≥ 1.5',
      evaluate: (t) => {
        const pf = _num(t, '_setup_pf');
        if (pf == null) return NA();
        if (pf >= 2.0) return PASS(pf.toFixed(2), 'strong');
        if (pf >= 1.5) return PASS(pf.toFixed(2));
        if (pf >= 1.2) return AMBER(pf.toFixed(2));
        return FAIL(pf.toFixed(2), 'no edge');
      }},
    { tab: 'edge', kbd: '7', label: 'Drift status',
      threshold: 'STABLE',
      evaluate: (t) => {
        const d = t._setup_drift;
        if (d == null) return NA();
        if (!d) return PASS('STABLE');
        return AMBER('WATCH', 'edge eroding');
      }},

    // ═══════════════════════════════════════════════════════════════════
    // V2 ADDITIONS (2026-05-14) · 55 more rules · P0 + P1 priority
    // ═══════════════════════════════════════════════════════════════════

    // ─── Overview (4 more) ───
    { tab: 'overview', kbd: '1', label: 'Hard-gate cascade',
      threshold: 'all PASS',
      evaluate: (t) => {
        const gates = _str(t, 'decision.gates_evaluated') ? null : (t.decision?.gates_evaluated || t.gates_evaluated);
        if (!Array.isArray(gates) || gates.length === 0) return NA('no gate audit');
        const total = gates.length;
        const passed = gates.filter(g => g.passed || g.pass).length;
        if (passed === total) return PASS(`${passed}/${total}`, 'all pass');
        if (passed >= total - 1) return AMBER(`${passed}/${total}`, '1 gate fail');
        return FAIL(`${passed}/${total}`, 'multiple gate fails');
      }},
    { tab: 'overview', kbd: '1', label: 'Rejection reasons',
      threshold: '0 active',
      evaluate: (t) => {
        const rr = t.decision?.rejection_reasons || t.rejection_reasons || t._rejected_static || [];
        if (!Array.isArray(rr)) return NA();
        if (rr.length === 0) return PASS('0', 'no concerns');
        if (rr.length === 1) return AMBER(`${rr.length}`, 'one concern');
        return FAIL(`${rr.length}`, 'multiple');
      }},
    { tab: 'overview', kbd: '1', label: 'Pre-mortem populated',
      threshold: '≥ 3 invalidations',
      evaluate: (t) => {
        const mech = _str(t, '_mechanism', 'mechanism');
        const fals = _str(t, '_falsification', 'falsification');
        if (!fals && !mech) return NA('not populated');
        if (fals) return PASS('defined');
        return AMBER('partial', 'mechanism only');
      }},
    { tab: 'overview', kbd: '1', label: 'Sector RS',
      threshold: 'sector outperforming SPY',
      evaluate: (t) => {
        const srank = _num(t, 'sector_rs_rank', 'industry_rs_rank');
        if (srank == null) return NA();
        if (srank >= 70) return PASS(`${srank.toFixed(0)}`, 'leading sector');
        if (srank >= 50) return AMBER(`${srank.toFixed(0)}`);
        return FAIL(`${srank.toFixed(0)}`, 'lagging sector');
      }},

    // ─── Plan (3 more) ───
    { tab: 'plan', kbd: '2', label: 'Total $ risk vs account',
      threshold: '≤ 1% of $25K ref',
      evaluate: (t) => {
        const refEq = 25000;
        const sz = _num(t, 'kelly_size.size_pct_equity');
        const px = _num(t, 'price') || 0;
        const stop = _num(t, 'stop') || 0;
        if (sz == null || !px || !stop) return NA();
        const dollarsDeployed = refEq * sz;
        const sharesBought = Math.floor(dollarsDeployed / px);
        const totalRisk = sharesBought * (px - stop);
        const pctOfAccount = (Math.abs(totalRisk) / refEq) * 100;
        if (pctOfAccount <= 1.0) return PASS(`${pctOfAccount.toFixed(2)}%`, 'within 1% rule');
        if (pctOfAccount <= 1.5) return AMBER(`${pctOfAccount.toFixed(2)}%`);
        return FAIL(`${pctOfAccount.toFixed(2)}%`, 'over 1% ruin rule');
      }},
    { tab: 'plan', kbd: '2', label: 'Falsification conditions',
      threshold: 'thesis-killer defined',
      evaluate: (t) => {
        const fals = _str(t, '_falsification', 'falsification', 'trade_plan.invalidation');
        if (!fals) return AMBER('—', 'no explicit kill criteria');
        return PASS('defined');
      }},
    { tab: 'plan', kbd: '2', label: 'Time stop defined',
      threshold: 'max_hold_days set',
      evaluate: (t) => {
        const d = _num(t, 'max_hold_days', 'trade_plan.max_hold_days');
        if (!d) return AMBER('—', 'no time-stop');
        return PASS(`flat after ${d}d`);
      }},

    // ─── Technicals (6 more) ───
    { tab: 'chart', kbd: '3', label: 'Price above EMA200',
      threshold: 'long-term trend filter',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const e200 = _num(t, 'technicals.indicators.ema200', 'ema200');
        if (!px || !e200) return NA();
        const dist = ((px - e200) / e200) * 100;
        if (px > e200) return PASS(`+${dist.toFixed(1)}%`);
        return FAIL(`${dist.toFixed(1)}%`, 'below EMA200 = trend broken');
      }},
    { tab: 'chart', kbd: '3', label: '52w distance from high',
      threshold: '≥ −10%',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const hi = _num(t, 'week52_high', 'high_52w');
        if (!px || !hi) return NA();
        const dist = ((px - hi) / hi) * 100;
        if (dist >= -5) return PASS(`${dist.toFixed(1)}%`, 'at 52w');
        if (dist >= -10) return PASS(`${dist.toFixed(1)}%`);
        if (dist >= -20) return AMBER(`${dist.toFixed(1)}%`, 'corrective phase');
        return FAIL(`${dist.toFixed(1)}%`, 'deep correction');
      }},
    { tab: 'chart', kbd: '3', label: 'TTM Squeeze state',
      threshold: 'FIRED or ON',
      evaluate: (t) => {
        const fired = t.technicals?.indicators?.squeeze_fired ?? t.squeeze_fired;
        const on = t.technicals?.indicators?.squeeze_on ?? t.squeeze_on;
        if (fired == null && on == null) return NA();
        if (fired) return PASS('FIRED', 'expansion underway');
        if (on) return PASS('ON', 'compressing');
        return AMBER('OFF', 'no vol edge');
      }},
    { tab: 'chart', kbd: '3', label: 'StochRSI momentum zone',
      threshold: '50–80',
      evaluate: (t) => {
        const s = _num(t, 'technicals.indicators.stoch_rsi', 'stoch_rsi');
        if (s == null) return NA();
        if (s >= 50 && s <= 80) return PASS(s.toFixed(0));
        if (s > 80) return AMBER(s.toFixed(0), 'overbought');
        if (s >= 30) return AMBER(s.toFixed(0));
        return FAIL(s.toFixed(0), 'weak');
      }},
    { tab: 'chart', kbd: '3', label: 'CMF accumulation',
      threshold: '> 0',
      evaluate: (t) => {
        const c = _num(t, 'technicals.indicators.cmf', 'cmf');
        if (c == null) return NA();
        if (c > 0.10) return PASS(c.toFixed(3), 'strong accumulation');
        if (c > 0) return PASS(c.toFixed(3));
        if (c > -0.05) return AMBER(c.toFixed(3));
        return FAIL(c.toFixed(3), 'distribution');
      }},
    { tab: 'chart', kbd: '3', label: 'OBV trend (5d)',
      threshold: 'rising',
      evaluate: (t) => {
        const slope = _num(t, 'technicals.indicators.obv_slope_5d', 'obv_slope_5d');
        if (slope == null) return NA();
        if (slope > 0) return PASS(`+${slope.toFixed(2)}`, 'volume confirms');
        return FAIL(slope.toFixed(2), 'volume diverging');
      }},

    // ─── Value (9 more) ───
    { tab: 'value', kbd: 'V', label: 'Margin of safety (IV)',
      threshold: 'MoS ≥ 15%',
      evaluate: (t) => {
        const px = _num(t, 'price') || 0;
        const iv = _num(t, 'intrinsic_value', 'analyst_target', 'analyst_full.target_mean');
        if (!px || !iv) return NA();
        const mos = ((iv - px) / iv) * 100;
        if (mos >= 25) return PASS(`+${mos.toFixed(1)}%`, 'deep MoS');
        if (mos >= 15) return PASS(`+${mos.toFixed(1)}%`);
        if (mos >= 0) return AMBER(`+${mos.toFixed(1)}%`, 'thin MoS');
        return FAIL(`${mos.toFixed(1)}%`, 'above fair value');
      }},
    { tab: 'value', kbd: 'V', label: 'ROIC vs WACC',
      threshold: 'ROIC > WACC',
      evaluate: (t) => {
        const roic = _num(t, 'fund_details.roic', 'roic');
        const wacc = _num(t, 'fund_details.wacc', 'wacc');
        if (roic == null) return NA();
        const r = roic >= 1 ? roic : roic * 100;
        const w = wacc == null ? 9 : (wacc >= 1 ? wacc : wacc * 100);  // 9% default
        const spread = r - w;
        if (spread >= 5) return PASS(`${r.toFixed(1)}% vs ${w.toFixed(1)}%`, 'compounder');
        if (spread >= 0) return PASS(`${r.toFixed(1)}% vs ${w.toFixed(1)}%`);
        return FAIL(`${r.toFixed(1)}% vs ${w.toFixed(1)}%`, 'destroying value');
      }},
    { tab: 'value', kbd: 'V', label: 'FCF yield',
      threshold: '≥ 3%',
      evaluate: (t) => {
        const y = _num(t, 'fund_details.fcf_yield', 'fcf_yield');
        if (y == null) return NA();
        const p = y >= 1 ? y : y * 100;
        if (p >= 5) return PASS(`${p.toFixed(1)}%`, 'strong cash gen');
        if (p >= 3) return PASS(`${p.toFixed(1)}%`);
        if (p >= 1) return AMBER(`${p.toFixed(1)}%`);
        return FAIL(`${p.toFixed(1)}%`, 'cash-thin');
      }},
    { tab: 'value', kbd: 'V', label: 'Operating margin',
      threshold: '≥ 15%',
      evaluate: (t) => {
        const m = _num(t, 'fund_details.operating_margin', 'operating_margin');
        if (m == null) return NA();
        const p = m >= 1 ? m : m * 100;
        if (p >= 20) return PASS(`${p.toFixed(1)}%`, 'strong');
        if (p >= 15) return PASS(`${p.toFixed(1)}%`);
        if (p >= 8) return AMBER(`${p.toFixed(1)}%`);
        return FAIL(`${p.toFixed(1)}%`);
      }},
    { tab: 'value', kbd: 'V', label: 'Net margin',
      threshold: '≥ 10%',
      evaluate: (t) => {
        const m = _num(t, 'fund_details.net_margin', 'net_margin', 'profit_margin');
        if (m == null) return NA();
        const p = m >= 1 ? m : m * 100;
        if (p >= 15) return PASS(`${p.toFixed(1)}%`);
        if (p >= 10) return PASS(`${p.toFixed(1)}%`);
        if (p >= 5) return AMBER(`${p.toFixed(1)}%`);
        return FAIL(`${p.toFixed(1)}%`);
      }},
    { tab: 'value', kbd: 'V', label: 'Current ratio',
      threshold: '≥ 1.5',
      evaluate: (t) => {
        const c = _num(t, 'fund_details.current_ratio', 'current_ratio');
        if (c == null) return NA();
        if (c >= 2.0) return PASS(c.toFixed(2), 'strong liquidity');
        if (c >= 1.5) return PASS(c.toFixed(2));
        if (c >= 1.0) return AMBER(c.toFixed(2), 'tight');
        return FAIL(c.toFixed(2), 'illiquid');
      }},
    { tab: 'value', kbd: 'V', label: 'EV/EBITDA',
      threshold: '≤ 18',
      evaluate: (t) => {
        const e = _num(t, 'fund_details.ev_to_ebitda', 'ev_to_ebitda');
        if (e == null) return NA();
        if (e <= 12) return PASS(e.toFixed(1), 'cheap');
        if (e <= 18) return PASS(e.toFixed(1));
        if (e <= 25) return AMBER(e.toFixed(1), 'rich');
        return FAIL(e.toFixed(1), 'expensive');
      }},
    { tab: 'value', kbd: 'V', label: 'Quality grade composite',
      threshold: 'A or B',
      evaluate: (t) => {
        const q = _num(t, 'qg_score', 'fund_score', 'scoring_breakdown.qg_score');
        if (q == null) return NA();
        if (q >= 8) return PASS('A', `${q.toFixed(1)}/10`);
        if (q >= 6) return PASS('B', `${q.toFixed(1)}/10`);
        if (q >= 4) return AMBER('C', `${q.toFixed(1)}/10`);
        return FAIL(q >= 2 ? 'D' : 'F', `${q.toFixed(1)}/10`);
      }},
    { tab: 'value', kbd: 'V', label: 'EPS growth YoY',
      threshold: '≥ 15%',
      evaluate: (t) => {
        const g = _num(t, 'eps_growth', 'fund_details.eps_growth');
        if (g == null) return NA();
        const p = g >= 1 ? g : g * 100;
        if (p >= 25) return PASS(`+${p.toFixed(1)}%`, 'accelerating');
        if (p >= 15) return PASS(`+${p.toFixed(1)}%`);
        if (p >= 0) return AMBER(`+${p.toFixed(1)}%`, 'flat');
        return FAIL(`${p.toFixed(1)}%`);
      }},

    // ─── Risk (5 more) ───
    { tab: 'risk', kbd: 'R', label: 'Max Drawdown 3y',
      threshold: '≥ −40%',
      evaluate: (t) => {
        const dd = _num(t, 'max_drawdown_3y', 'fund_details.max_drawdown_3y');
        if (dd == null) return NA();
        const p = dd >= 0 ? -dd : dd;
        if (p >= -25) return PASS(`${p.toFixed(1)}%`, 'mild');
        if (p >= -40) return PASS(`${p.toFixed(1)}%`);
        if (p >= -55) return AMBER(`${p.toFixed(1)}%`, 'high beta');
        return FAIL(`${p.toFixed(1)}%`, 'extreme volatility');
      }},
    { tab: 'risk', kbd: 'R', label: 'Sharpe ratio (3y)',
      threshold: '≥ 1.0',
      evaluate: (t) => {
        const s = _num(t, 'sharpe_ratio', 'fund_details.sharpe_3y');
        if (s == null) return NA();
        if (s >= 1.5) return PASS(s.toFixed(2), 'strong');
        if (s >= 1.0) return PASS(s.toFixed(2));
        if (s >= 0.5) return AMBER(s.toFixed(2));
        return FAIL(s.toFixed(2), 'risk-not-paying');
      }},
    { tab: 'risk', kbd: 'R', label: 'Position vs 1% of ADV',
      threshold: '≤ 1% of avg daily $-vol',
      evaluate: (t) => {
        const refEq = 25000;
        const sz = _num(t, 'kelly_size.size_pct_equity');
        const adv = _num(t, 'adv_dollar', 'dollar_volume_avg', 'adv') ||
                    (_num(t, 'avg_volume') || 0) * (_num(t, 'price') || 0);
        if (!sz || !adv) return NA();
        const posDollars = refEq * sz;
        const pctOfAdv = (posDollars / adv) * 100;
        if (pctOfAdv <= 0.5) return PASS(`${pctOfAdv.toFixed(2)}% of ADV`, 'no slippage');
        if (pctOfAdv <= 1.0) return PASS(`${pctOfAdv.toFixed(2)}% of ADV`);
        if (pctOfAdv <= 2.0) return AMBER(`${pctOfAdv.toFixed(2)}% of ADV`, 'slippage rising');
        return FAIL(`${pctOfAdv.toFixed(2)}% of ADV`, 'liquidity-constrained');
      }},
    { tab: 'risk', kbd: 'R', label: 'Calmar ratio',
      threshold: '≥ 0.5',
      evaluate: (t) => {
        const c = _num(t, 'calmar_ratio', 'fund_details.calmar_3y');
        if (c == null) return NA();
        if (c >= 1.0) return PASS(c.toFixed(2), 'strong');
        if (c >= 0.5) return PASS(c.toFixed(2));
        if (c >= 0.3) return AMBER(c.toFixed(2));
        return FAIL(c.toFixed(2), 'pain not paying');
      }},
    { tab: 'risk', kbd: 'R', label: 'Drawdown multiplier active',
      threshold: 'no haircut',
      evaluate: (t) => {
        const m = _num(t, 'kelly_size.drawdown_mult');
        if (m == null) return NA();
        if (m >= 1.0) return PASS(`${m.toFixed(2)}×`, 'full size');
        if (m >= 0.5) return AMBER(`${m.toFixed(2)}×`, 'DD haircut active');
        return FAIL(`${m.toFixed(2)}×`, 'major haircut');
      }},

    // ─── Earnings (5 more) ───
    { tab: 'er_lab', kbd: 'E', label: 'Implied Move %',
      threshold: '≤ 10%',
      evaluate: (t) => {
        const im = _num(t, 'implied_move_pct', 'earnings_beat_prediction.breakdown.implied_move.implied_move_pct');
        if (im == null) return NA();
        if (im <= 7) return PASS(`±${im.toFixed(1)}%`);
        if (im <= 10) return PASS(`±${im.toFixed(1)}%`);
        if (im <= 15) return AMBER(`±${im.toFixed(1)}%`, 'high-vol event');
        return FAIL(`±${im.toFixed(1)}%`, 'binary event');
      }},
    { tab: 'er_lab', kbd: 'E', label: 'Guidance direction',
      threshold: 'RAISED or AFFIRMED',
      evaluate: (t) => {
        const g = _str(t, 'last_guidance_direction', 'guidance_trend');
        if (!g) return NA('not parsed');
        const u = g.toUpperCase();
        if (u === 'RAISED' || u === 'RAISE') return PASS('RAISED');
        if (u === 'AFFIRMED' || u === 'INLINE') return PASS('AFFIRMED');
        if (u === 'LOWERED' || u === 'CUT') return FAIL('LOWERED');
        return AMBER(g);
      }},
    { tab: 'er_lab', kbd: 'E', label: 'PEAD drift profile',
      threshold: 'positive 5d drift on beats',
      evaluate: (t) => {
        const d = _num(t, 'earnings_beat_prediction.breakdown.pead.median_drift_pct_5d',
                          'earnings_beat_prediction.breakdown.pead.drift_pct',
                          'pead_drift_5d');
        if (d == null) return NA();
        if (d >= 2) return PASS(`+${d.toFixed(1)}% 5d`, 'PEAD-eligible');
        if (d >= 0) return AMBER(`+${d.toFixed(1)}%`, 'thin drift');
        return FAIL(`${d.toFixed(1)}%`, 'fades after beat');
      }},
    { tab: 'er_lab', kbd: 'E', label: '4Q pattern',
      threshold: '≥ 3 beats of 4',
      evaluate: (t) => {
        const p = _str(t, 'earnings_beat_prediction.breakdown.historical.pattern');
        if (!p) return NA();
        const beats = (p.match(/B/g) || []).length;
        const total = p.length;
        if (beats >= total) return PASS(p, 'perfect');
        if (beats >= 3) return PASS(p, `${beats}/${total} beats`);
        if (beats >= 2) return AMBER(p, `${beats}/${total}`);
        return FAIL(p, `only ${beats}/${total}`);
      }},
    { tab: 'er_lab', kbd: 'E', label: 'Sector cohort',
      threshold: 'HOT or NEUTRAL',
      evaluate: (t) => {
        const tag = _str(t, 'earnings_beat_prediction.breakdown.sector_cohort.tag', 'sector_cohort.tag');
        if (!tag) return NA();
        if (tag === 'HOT') return PASS(tag, 'peer tailwind');
        if (tag === 'NEUTRAL') return AMBER(tag);
        if (tag === 'COLD') return FAIL(tag, 'peer headwind');
        return NA(tag);
      }},

    // ─── Options (6 more) ───
    { tab: 'options', kbd: 'O', label: 'IV / HV ratio',
      threshold: '0.80–1.30 (fair)',
      evaluate: (t) => {
        const ivCur = _num(t, 'iv_current', 'options_kpis.iv_current', 'atm_iv');
        const atrPct = _num(t, 'technicals.indicators.atr_pct', 'atr_pct');
        if (ivCur == null || atrPct == null) return NA();
        const ivDec = ivCur > 1 ? ivCur / 100 : ivCur;
        const hvDec = (atrPct / 100) * Math.sqrt(252);
        if (hvDec === 0) return NA();
        const r = ivDec / hvDec;
        if (r >= 0.80 && r <= 1.30) return PASS(`${r.toFixed(2)}×`, 'fair');
        if (r < 0.80) return PASS(`${r.toFixed(2)}×`, 'cheap · buy directional');
        if (r <= 1.50) return AMBER(`${r.toFixed(2)}×`, 'rich');
        return AMBER(`${r.toFixed(2)}×`, 'sell premium / fade');
      }},
    { tab: 'options', kbd: 'O', label: 'Term structure',
      threshold: 'CONTANGO',
      evaluate: (t) => {
        const ts = _str(t, 'options_kpis.term_structure.structure', 'term_structure.structure');
        if (!ts) return NA();
        const u = ts.toUpperCase();
        if (u === 'CONTANGO' || u === 'FLAT') return PASS(u);
        if (u === 'BACKWARDATION') return FAIL(u, 'stress imminent');
        return AMBER(u);
      }},
    { tab: 'options', kbd: 'O', label: '25Δ skew',
      threshold: '≤ +3',
      evaluate: (t) => {
        const s = _num(t, 'options_kpis.skew_25d', 'skew_25d');
        if (s == null) return NA();
        if (s <= 1) return PASS(s.toFixed(1), 'balanced');
        if (s <= 3) return PASS(s.toFixed(1));
        if (s <= 5) return AMBER(s.toFixed(1), 'fear premium');
        return FAIL(s.toFixed(1), 'institutional fear');
      }},
    { tab: 'options', kbd: 'O', label: 'Max pain vs spot',
      threshold: '± 5%',
      evaluate: (t) => {
        const mp = _num(t, 'max_pain', 'options_kpis.max_pain');
        const px = _num(t, 'price') || 0;
        if (!mp || !px) return NA();
        const pct = ((mp - px) / px) * 100;
        if (Math.abs(pct) <= 2) return AMBER(`${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`, 'magnet pin');
        if (Math.abs(pct) <= 5) return PASS(`${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`);
        return AMBER(`${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`, 'directional pull');
      }},
    { tab: 'options', kbd: 'O', label: 'Net gamma · dealer pos',
      threshold: 'positive · stabilizing',
      evaluate: (t) => {
        const g = _num(t, 'options_kpis.gamma_net', 'gamma_net');
        if (g == null) return NA();
        if (g > 0) return PASS(`+${(g/1e6).toFixed(1)}M`, 'dealers stabilize · range-bound');
        return AMBER(`${(g/1e6).toFixed(1)}M`, 'dealers amplify · trend-prone');
      }},
    { tab: 'options', kbd: 'O', label: 'ATM IV level',
      threshold: 'reasonable',
      evaluate: (t) => {
        const iv = _num(t, 'atm_iv', 'options_kpis.iv_current');
        if (iv == null) return NA();
        const v = iv > 1 ? iv : iv * 100;
        if (v <= 35) return PASS(`${v.toFixed(0)}%`, 'low-vol regime');
        if (v <= 60) return PASS(`${v.toFixed(0)}%`);
        if (v <= 85) return AMBER(`${v.toFixed(0)}%`, 'elevated');
        return AMBER(`${v.toFixed(0)}%`, 'extreme');
      }},

    // ─── Portfolio (7 more — most needed real wire-up) ───
    { tab: 'portfolio', kbd: 'P', label: 'Cap usage post-trade',
      threshold: '≤ 100%',
      evaluate: (t) => {
        const existing = _num(t, 'portfolio_cap_used_pct') || 0;
        const sz = _num(t, 'kelly_size.size_pct_equity');
        if (sz == null) return NA();
        const post = existing + sz * 100;
        if (post <= 70) return PASS(`${post.toFixed(0)}%`, 'cash buffer');
        if (post <= 100) return PASS(`${post.toFixed(0)}%`);
        return FAIL(`${post.toFixed(0)}%`, 'over-allocated');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Active position count',
      threshold: '≤ 5 system cap',
      evaluate: (t) => {
        const n = _num(t, 'active_position_count', 'portfolio.active_count');
        if (n == null) return NA('needs portfolio.json wire');
        if (n < 5) return PASS(`${n} active`, `${5-n} slot${5-n!==1?'s':''} open`);
        if (n === 5) return AMBER('5', 'at cap');
        return FAIL(`${n}`, 'over cap');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Sector exposure post-trade',
      threshold: '≤ 30% any sector',
      evaluate: (t) => {
        const sectExp = _num(t, 'portfolio_sector_exposure_post_pct');
        if (sectExp == null) return NA('needs portfolio wire');
        if (sectExp <= 20) return PASS(`${sectExp.toFixed(0)}%`);
        if (sectExp <= 30) return PASS(`${sectExp.toFixed(0)}%`);
        return AMBER(`${sectExp.toFixed(0)}%`, 'sector-concentrated');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Goal alignment',
      threshold: 'matches investor goal',
      evaluate: (t) => {
        const g = _str(t, 'investor_goal');
        if (!g) return NA('goal not set');
        return PASS(g);
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Already holding?',
      threshold: 'no existing position OR scaling-in OK',
      evaluate: (t) => {
        const h = _num(t, 'existing_position_shares', 'portfolio_position_size');
        if (h == null) return NA();
        if (h === 0) return PASS('new');
        return AMBER(`holding ${h} sh`, 'review scaling');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Account drawdown',
      threshold: 'above DD-halve threshold',
      evaluate: (t) => {
        const dd = _num(t, 'account_drawdown_pct', 'portfolio.drawdown_pct');
        if (dd == null) return NA();
        const p = dd >= 0 ? -dd : dd;
        if (p >= -5) return PASS(`${p.toFixed(1)}%`);
        if (p >= -10) return AMBER(`${p.toFixed(1)}%`, 'haircut active');
        if (p >= -20) return AMBER(`${p.toFixed(1)}%`, 'half-size');
        return FAIL(`${p.toFixed(1)}%`, 'stop trading · review');
      }},
    { tab: 'portfolio', kbd: 'P', label: 'Suitability',
      threshold: 'risk × horizon match',
      evaluate: (t) => NA('manual review') },

    // ─── Intel · Tape · Flow (6 more) ───
    { tab: 'intel', kbd: 'I', label: 'Smart-money composite',
      threshold: '≥ 60 / 100',
      evaluate: (t) => {
        const s = _num(t, 'smart_money_score', 'intel.smart_money_score');
        if (s == null) return NA();
        if (s >= 75) return PASS(`${s.toFixed(0)}`, 'high conviction');
        if (s >= 60) return PASS(`${s.toFixed(0)}`);
        if (s >= 40) return AMBER(`${s.toFixed(0)}`);
        return FAIL(`${s.toFixed(0)}`, 'retail-driven');
      }},
    { tab: 'intel', kbd: 'I', label: 'Material headline (5d)',
      threshold: 'no DOJ/SEC/FDA reject',
      evaluate: (t) => {
        const news = t.news_articles || [];
        if (!Array.isArray(news) || news.length === 0) return NA();
        const recent = news.filter(a => {
          const ts = a.published_utc || a.publishedDate;
          if (!ts) return false;
          const date = new Date(ts);
          const daysAgo = (Date.now() - date.getTime()) / 86400000;
          return daysAgo <= 5;
        });
        const flag = recent.some(a => {
          const ttl = (a.title || '').toLowerCase();
          return /doj|sec |fda reject|miss guid|cut guid|lawsuit|fraud|investigat|recall|warning letter/.test(ttl);
        });
        if (flag) return FAIL('NEGATIVE 5d', 'material headline');
        return PASS('clear', `${recent.length} headlines · no triggers`);
      }},
    { tab: 'intel', kbd: 'I', label: 'Sentiment 7d avg',
      threshold: '≥ +0.20',
      evaluate: (t) => {
        const s = _num(t, 'eodhd_sentiment.avg_7d', 'sentiment_7d_avg');
        if (s == null) return NA();
        if (s >= 0.30) return PASS(s.toFixed(2), 'strong');
        if (s >= 0.20) return PASS(s.toFixed(2));
        if (s >= 0) return AMBER(s.toFixed(2), 'neutral');
        return FAIL(s.toFixed(2), 'negative');
      }},
    { tab: 'intel', kbd: 'I', label: 'Days to cover (short)',
      threshold: '≤ 5d',
      evaluate: (t) => {
        const d = _num(t, 'short_ratio', 'days_to_cover');
        if (d == null) return NA();
        if (d >= 5) return AMBER(`${d.toFixed(1)}d`, 'squeeze fuel');
        if (d >= 2) return PASS(`${d.toFixed(1)}d`);
        return PASS(`${d.toFixed(1)}d`, 'easy cover');
      }},
    { tab: 'intel', kbd: 'I', label: '13F net direction',
      threshold: 'institutional adds',
      evaluate: (t) => {
        const dir = _str(t, 'institutional.q_change_direction', 'inst_13f_direction');
        if (!dir) return NA();
        const u = dir.toUpperCase();
        if (u === 'ADD' || u === 'ACCUMULATING') return PASS(u);
        if (u === 'NEUTRAL' || u === 'FLAT') return AMBER(u);
        if (u === 'DISTRIBUTE' || u === 'DISTRIBUTION') return FAIL(u, 'inst selling');
        return NA(dir);
      }},
    { tab: 'intel', kbd: 'I', label: 'News count (recency)',
      threshold: '≥ 5 in 7d',
      evaluate: (t) => {
        const news = t.news_articles || [];
        if (!Array.isArray(news)) return NA();
        if (news.length >= 10) return PASS(`${news.length} headlines`, 'high coverage');
        if (news.length >= 5) return PASS(`${news.length}`);
        if (news.length >= 1) return AMBER(`${news.length}`, 'thin coverage');
        return AMBER('0', 'silent name');
      }},

    // ─── Track Record · Edge (5 more) ───
    { tab: 'edge', kbd: '7', label: 'Forward Distribution mean',
      threshold: '≥ +1.5% over horizon',
      evaluate: (t) => {
        const m = _num(t, 'forward_dist.mean_pct', 'forward_dist.expected_return_pct');
        if (m == null) return NA();
        if (m >= 2.5) return PASS(`+${m.toFixed(2)}%`, 'strong expectancy');
        if (m >= 1.5) return PASS(`+${m.toFixed(2)}%`);
        if (m >= 0) return AMBER(`+${m.toFixed(2)}%`, 'thin');
        return FAIL(`${m.toFixed(2)}%`, 'negative expectancy');
      }},
    { tab: 'edge', kbd: '7', label: 'Monte Carlo P(T1)',
      threshold: '≥ 55%',
      evaluate: (t) => {
        const p = _num(t, 'mc_paths.p_t1_hit', 'monte_carlo.prob_t1_hit', 'forward_dist.p_t1_hit');
        if (p == null) return NA();
        if (p >= 65) return PASS(`${p.toFixed(0)}%`);
        if (p >= 55) return PASS(`${p.toFixed(0)}%`);
        if (p >= 45) return AMBER(`${p.toFixed(0)}%`);
        return FAIL(`${p.toFixed(0)}%`, 'low T1 odds');
      }},
    { tab: 'edge', kbd: '7', label: 'Monte Carlo P(stop)',
      threshold: '≤ 45%',
      evaluate: (t) => {
        const p = _num(t, 'mc_paths.p_stop_hit', 'monte_carlo.prob_stop_hit', 'forward_dist.p_stop_hit');
        if (p == null) return NA();
        if (p <= 30) return PASS(`${p.toFixed(0)}%`, 'low stop odds');
        if (p <= 45) return PASS(`${p.toFixed(0)}%`);
        if (p <= 55) return AMBER(`${p.toFixed(0)}%`);
        return FAIL(`${p.toFixed(0)}%`, 'high stop odds');
      }},
    { tab: 'edge', kbd: '7', label: 'HMM regime state',
      threshold: 'BULL / RISK_ON',
      evaluate: (t) => {
        const s = _str(t, 'hmm.state', 'hmm.regime_label', 'hmm_state');
        if (!s) return NA();
        const u = s.toUpperCase();
        if (u.includes('BULL') || u.includes('RISK_ON_TREND')) return PASS(s);
        if (u.includes('CHOPPY') || u.includes('NEUTRAL') || u.includes('RISK_ON')) return AMBER(s);
        if (u.includes('PANIC')) return FAIL(s, 'no longs');
        if (u.includes('BEAR') || u.includes('RISK_OFF')) return FAIL(s, 'bear state');
        return AMBER(s);
      }},
    { tab: 'edge', kbd: '7', label: 'Avg R-multiple (setup)',
      threshold: '≥ +0.5R realized',
      evaluate: (t) => {
        const r = _num(t, '_setup_avg_r', 'setup_avg_r');
        if (r == null) return NA();
        if (r >= 1.0) return PASS(`+${r.toFixed(2)}R`, 'strong');
        if (r >= 0.5) return PASS(`+${r.toFixed(2)}R`);
        if (r >= 0) return AMBER(`+${r.toFixed(2)}R`, 'thin');
        return FAIL(`${r.toFixed(2)}R`, 'losing setup');
      }},
  ];

  // ─── Tally + size recommendation ──────────────────────────────────────
  function evaluateAll(t) {
    return RULES.map(r => ({ ...r, result: r.evaluate(t) }));
  }

  function tally(results, t) {
    const pass  = results.filter(r => r.result.status === 'pass').length;
    const amber = results.filter(r => r.result.status === 'amber').length;
    const fail  = results.filter(r => r.result.status === 'fail').length;
    const na    = results.filter(r => r.result.status === 'na').length;
    const usable = pass + amber + fail;
    const total = results.length;
    const passPct = usable ? (pass / usable) * 100 : 0;
    const coverage = total ? (usable / total) * 100 : 0;

    // ─────────────────────────────────────────────────────────────────────
    // FINAL CALL = SCREENER VERDICT · checklist is a context-supplier, not
    // a re-judger. The pipeline already weighted setup × pillars × gates ×
    // multipliers — surfacing its decision verbatim respects the system.
    // The pass/warn/fail count below shows what to REVIEW, not override.
    // ─────────────────────────────────────────────────────────────────────
    const verdict = (_str(t || {}, 'decision.verdict', 'verdict') || '').toUpperCase();
    const conviction = (_str(t || {}, 'conviction_tier', 'tier') || '').toUpperCase();
    const kellyPct = _num(t || {}, 'kelly_size.size_pct_equity');

    let size, color, label, note;
    if (verdict === 'BUY') {
      // Map conviction tier to position size — these are the system's own bands
      if (conviction === 'T1') {
        size = 'BUY · FULL'; color = 'gn';
        label = kellyPct != null ? `${(kellyPct*100).toFixed(1)}% equity (T1 · system Kelly)` : '5–10% equity (T1)';
      } else if (conviction === 'T2') {
        size = 'BUY · HALF'; color = 'am';
        label = kellyPct != null ? `${(kellyPct*100).toFixed(1)}% equity (T2 · system Kelly)` : '2–4% equity (T2)';
      } else if (conviction === 'T3') {
        size = 'BUY · LIGHT'; color = 'am';
        label = '15–30% of half-size (T3)';
      } else {
        size = 'BUY'; color = 'gn';
        label = kellyPct != null ? `${(kellyPct*100).toFixed(1)}% Kelly equity` : 'screener: BUY';
      }
      note = `screener verdict · ${pass} confirms · ${amber} warns · ${fail} concerns to review`;
    } else if (verdict === 'WATCH') {
      size = 'WATCH'; color = 'info';
      label = 'screener: WATCH · not actionable yet';
      note = 'wait for trigger · set price alert at entry-zone low';
    } else if (verdict === 'AVOID' || verdict === 'SHORT' || verdict === 'SELL') {
      size = 'SKIP'; color = 'rd';
      label = `screener: ${verdict}`;
      note = 'pipeline rejected this candidate';
    } else {
      size = 'NO VERDICT'; color = 'info';
      label = 'screener has not classified this ticker';
      note = 'no verdict field in payload';
    }

    // killSwitch retained for display only — surfaces the flagged concerns
    // but does NOT override the screener's call. User reviews and decides.
    const killSwitch = [];
    results.forEach(r => {
      const lbl = (r.label || '').toLowerCase();
      const val = (r.result.value || '').toString().toLowerCase();
      if (r.result.status !== 'fail') return;
      if (/regime/i.test(lbl) && /panic/i.test(val)) killSwitch.push('PANIC regime');
      if (/blackout/i.test(lbl)) killSwitch.push('ER blackout');
      if (/hmm.*regime/i.test(lbl) && /(bear|panic)/i.test(val)) killSwitch.push('HMM bear/panic');
      if (/material headline/i.test(lbl)) killSwitch.push('material negative headline (5d)');
    });

    return { pass, amber, fail, na, total, usable, passPct, coverage, size, label, color, note, killSwitch, verdict, conviction };
  }

  // ─── Render ───────────────────────────────────────────────────────────
  function _statusPill(s) {
    const lbl = s.status === 'pass' ? 'PASS' : s.status === 'amber' ? 'WARN' : s.status === 'fail' ? 'FAIL' : '—';
    const cls = s.status === 'pass' ? 'gn' : s.status === 'amber' ? 'am' : s.status === 'fail' ? 'rd' : 'dim';
    return `<span class="qdchk-pill qdchk-pill-${cls}">${lbl}</span>`;
  }
  function _tabBadge(kbd, tab) {
    return `<button class="qdchk-tabjump" data-tab="${tab}" data-kbd="${kbd}" title="Jump to ${tab} tab">${kbd}</button>`;
  }

  function _renderRowsByTab(results) {
    const groups = {};
    results.forEach(r => {
      if (!groups[r.tab]) groups[r.tab] = { kbd: r.kbd, rows: [] };
      groups[r.tab].rows.push(r);
    });
    const TAB_ORDER = ['overview','plan','chart','value','risk','er_lab','options','portfolio','intel','edge'];
    const TAB_NAMES = {
      overview:'Overview', plan:'Plan · Ticket', chart:'Technicals', value:'Investment · Value',
      risk:'Risk', er_lab:'Earnings · ER Lab', options:'Options', portfolio:'Portfolio',
      intel:'Tape · Flow', edge:'Track Record · Edge'
    };
    let html = '';
    TAB_ORDER.forEach(tab => {
      const g = groups[tab];
      if (!g) return;
      const passC  = g.rows.filter(r => r.result.status === 'pass').length;
      const amberC = g.rows.filter(r => r.result.status === 'amber').length;
      const failC  = g.rows.filter(r => r.result.status === 'fail').length;
      html += `<div class="qdchk-group">
        <div class="qdchk-group-h">
          ${_tabBadge(g.kbd, tab)}
          <span class="qdchk-group-name">${TAB_NAMES[tab] || tab}</span>
          <span class="qdchk-group-tally">
            <span class="qdchk-tally-gn">${passC}</span>·<span class="qdchk-tally-am">${amberC}</span>·<span class="qdchk-tally-rd">${failC}</span>
          </span>
        </div>
        <div class="qdchk-rows">
          ${g.rows.map(r => `
            <div class="qdchk-row qdchk-row-${r.result.status}">
              ${_statusPill(r.result)}
              <div class="qdchk-row-body">
                <div class="qdchk-row-label">${r.label} <span class="qdchk-row-thr">${r.threshold || ''}</span></div>
                <div class="qdchk-row-val">${r.result.value}${r.result.detail ? ` <span class="qdchk-row-detail">· ${r.result.detail}</span>` : ''}</div>
              </div>
            </div>`).join('')}
        </div>
      </div>`;
    });
    return html;
  }

  function _renderPanel(t) {
    const results = evaluateAll(t);
    const stats = tally(results, t);
    const tk = (t.ticker || '—').toUpperCase();
    const px = _num(t, 'price') || 0;
    const verdict = (_str(t, 'decision.verdict', 'verdict') || '—').toUpperCase();
    const verdCls = verdict === 'BUY' ? 'gn' : verdict === 'WATCH' ? 'am' : 'rd';

    const sizeColor = stats.color === 'gn' ? 'var(--gn)' :
                       stats.color === 'am' ? 'var(--amb)' :
                       stats.color === 'info' ? 'var(--info, #60a5fa)' : 'var(--rd)';

    return `
      <div class="qdchk-header">
        <div class="qdchk-head-l">
          <div class="qdchk-head-tk">${tk}</div>
          <div class="qdchk-head-px">$${px.toFixed(2)}</div>
          <span class="qdchk-pill qdchk-pill-${verdCls}">${verdict}</span>
        </div>
        <button class="qdchk-close" title="Close (Esc)">×</button>
      </div>
      <div class="qdchk-verdict" style="border-left-color:${sizeColor}">
        <div class="qdchk-verdict-row">
          <span class="qdchk-verdict-k">Screener call</span>
          <span class="qdchk-verdict-v" style="color:${sizeColor}">${stats.size}</span>
        </div>
        <div class="qdchk-verdict-sub">${stats.label}</div>
        ${stats.note ? `<div class="qdchk-verdict-note">${stats.note}</div>` : ''}
        <div class="qdchk-verdict-tally">
          <span class="qdchk-tally-gn">✓ ${stats.pass} confirms</span>
          <span class="qdchk-tally-am">⚠ ${stats.amber} warns</span>
          <span class="qdchk-tally-rd">✗ ${stats.fail} concerns</span>
          <span class="qdchk-tally-dim">— ${stats.na} N/A</span>
          <span class="qdchk-tally-cov">${stats.coverage.toFixed(0)}% cov</span>
        </div>
        ${stats.killSwitch.length ? `<div class="qdchk-killsw"><b>FLAGGED (review):</b> ${stats.killSwitch.join(' · ')}</div>` : ''}
        <div class="qdchk-verdict-foot">Below: per-tab pass/fail breakdown · use to find the ${stats.fail || stats.amber} concern${(stats.fail + stats.amber) !== 1 ? 's' : ''} before committing.</div>
      </div>
      <div class="qdchk-body">
        ${_renderRowsByTab(results)}
      </div>
      <div class="qdchk-foot">
        <div class="qdchk-foot-note">Live audit · ${stats.pass}/${stats.usable} pass · ${stats.passPct.toFixed(0)}%</div>
      </div>
    `;
  }

  // ─── Show / Hide ──────────────────────────────────────────────────────
  let _panel = null;

  function open(t) {
    if (!t) {
      if (window._currentT) t = window._currentT;
      else if (window.QuantDetail && window.__getDetailTicker) t = window.__getDetailTicker();
      if (!t) { console.warn('[QDChecklist] no ticker'); return; }
    }
    if (!_panel) {
      _panel = document.createElement('div');
      _panel.className = 'qdchk-panel';
      _panel.id = 'qdchk-panel';
      document.body.appendChild(_panel);
    }
    _panel.innerHTML = _renderPanel(t);
    _panel.classList.add('qdchk-on');

    // Wire close + jumps
    _panel.querySelector('.qdchk-close')?.addEventListener('click', close);
    _panel.querySelectorAll('.qdchk-tabjump').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        if (window.QuantDetail && window.QuantDetail.switchSub) {
          window.QuantDetail.switchSub(tab);
          close();
        }
      });
    });
  }

  function close() {
    if (_panel) _panel.classList.remove('qdchk-on');
  }

  function toggle() {
    if (_panel && _panel.classList.contains('qdchk-on')) close();
    else open();
  }

  // Keyboard: Shift+C
  document.addEventListener('keydown', (e) => {
    if (e.shiftKey && (e.key === 'C' || e.key === 'c') && !e.metaKey && !e.ctrlKey) {
      const tag = (document.activeElement || {}).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      e.preventDefault();
      toggle();
    }
    if (e.key === 'Escape' && _panel && _panel.classList.contains('qdchk-on')) {
      close();
    }
  });

  return { open, close, toggle, evaluateAll, tally };
})();
