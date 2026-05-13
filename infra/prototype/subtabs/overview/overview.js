// subtabs/overview/overview.js — quant-grade institutional overview
// (rebuilt 2026-05-11 to match cache/overview_prototype.html spec).
//
// 12 sections: decision-strip · triage band · edge bar · 3-lens evidence
// (technical / flow / quality) · trade window · historical edge · regime
// decomposition · prior earnings · peer cohort · cross-asset · calibration ·
// risk profile · pre-flight checklist.
//
// Data precedence matches sibling-tab canonical sources:
//   technicals: T.technicals.indicators → T.* flat fields
//   insider:    T.insider_full → T.insider → T.insider_data → flat
//   sentiment:  T.news_sentiment_score → T.eodhd_sentiment → flat
//   analyst:    T.analyst_full → T.analyst → flat
//   funds:      T.fund_real → T.fund_details → T.eodhd_fund_extras → flat
//   options:    T.options_iv → flat
//   plan:       T.canonical_trade_plan → T.trade_plan → flat
//
// Fields with no available source render "—" (never fabricated). Wilson LBs
// computed locally; regime/peer/macro pulled from window.DATA globals.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);
const _D = () => {
  if (typeof window === 'undefined') return {};
  return (window.DATA && typeof window.DATA === 'object') ? window.DATA :
         (window.__getData ? window.__getData() : {});
};

// ─── helpers ─────────────────────────────────────────────────────────
const num = (v, d = NaN) => (v == null || v === '' || isNaN(+v)) ? d : +v;
const fmt = (v, dp = 2, suf = '', pre = '') => {
  const n = num(v);
  return isNaN(n) ? '—' : pre + n.toFixed(dp) + suf;
};
const fmtPct = (v, dp = 1) => {
  const n = num(v); return isNaN(n) ? '—' : (n >= 0 ? '+' : '') + n.toFixed(dp) + '%';
};
const fmtMcap = m => {
  const n = num(m); if (isNaN(n) || !n) return '—';
  return n >= 1e12 ? '$' + (n/1e12).toFixed(2) + 'T' :
         n >= 1e9  ? '$' + (n/1e9 ).toFixed(1) + 'B' :
         n >= 1e6  ? '$' + (n/1e6 ).toFixed(0) + 'M' : '$' + n.toFixed(0);
};
const cls = (v, good, bad, mid) => {
  // returns 'gn' / 'am' / 'rd' / 'dim' for v against thresholds
  const n = num(v); if (isNaN(n)) return 'dim';
  if (mid != null) {
    if (n >= good) return 'gn'; if (n <= bad) return 'rd'; return 'am';
  }
  return n >= good ? 'gn' : n <= bad ? 'rd' : 'am';
};
// Wilson 95% lower bound for sample size n, observed proportion p (0..1)
function wilsonLB(p, n) {
  if (!n || isNaN(p)) return null;
  const z = 1.96, z2 = z*z;
  const denom = 1 + z2/n;
  const center = p + z2/(2*n);
  const margin = z * Math.sqrt((p*(1-p) + z2/(4*n)) / n);
  return Math.max(0, (center - margin) / denom);
}
const pPct = v => v == null ? '—' : (v*100).toFixed(0) + '%';

// regime → BAP floor (matches decision_engine gate)
const REGIME_FLOOR = {
  'risk_on_trending':  65,
  'risk_on_choppy':    72,
  'risk_off_trending': 78,
  'risk_off':          78,
  'panic':             999,
};

// embedded scoped CSS (idempotent inject)
const QOV_CSS = `
.qov-root {
  --gn:#5be57c; --gn-dim:#2f6b41; --gn-bg:rgba(91,229,124,0.08);
  --am:#ffb95c; --am-dim:#8c5d20; --am-bg:rgba(255,185,92,0.06);
  --rd:#ff6b5b; --rd-dim:#7a2a22; --rd-bg:rgba(255,107,91,0.06);
  --cy:#5ec8d8; --cy-dim:#2c6a74; --cy-bg:rgba(94,200,216,0.07);
  --qbg:#000; --qbg-1:#0a0d0c; --qbg-2:#0f1311; --qbg-3:#141816;
  --qline:#1d2520; --qline-2:#2a352e;
  --qink:#d8d6cc; --qink-1:#b0aea3; --qink-2:#80847a;
  --qink-3:#545851; --qink-4:#2e312c;
  --qmono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  color:var(--qink-1); font-size:12px; font-variant-numeric:tabular-nums;
  background:var(--qbg); padding:8px 4px 60px;
}
.qov-root * { box-sizing:border-box; }
.qov-mono { font-family:var(--qmono); }
.qov-dim  { color:var(--qink-3); }
.qov-gn   { color:var(--gn); } .qov-am{color:var(--am);} .qov-rd{color:var(--rd);} .qov-cy{color:var(--cy);}

/* decision strip */
.qov-strip{display:grid;grid-template-columns:1.5fr 1.4fr 1fr 1fr;
  padding:12px 16px;background:var(--qbg-1);border:1px solid var(--qline);
  border-left:2px solid var(--am);border-radius:2px;font-family:var(--qmono);
  margin-bottom:12px}
.qov-strip > div{padding:0 14px;border-right:1px solid var(--qline)}
.qov-strip > div:last-child{border-right:none}
.qov-strip > div:first-child{padding-left:0}
.qov-strip .k{font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700;margin-bottom:4px}
.qov-strip .v{font-size:12px;color:var(--qink-1);line-height:1.5}
.qov-strip b{color:var(--qink);font-weight:700}

/* note ribbon */
.qov-note{padding:8px 12px;background:var(--qbg-2);border:1px solid var(--qline);
  border-left:2px solid var(--am);font-family:var(--qmono);font-size:10.5px;
  color:var(--qink-2);line-height:1.6;margin-bottom:10px;border-radius:2px}
.qov-note b{color:var(--qink);font-weight:700}
.qov-note .why{color:var(--am);font-weight:700}

/* KPI rows */
.qov-kpi-row{display:grid;gap:8px;margin-bottom:12px}
.qov-kpi{background:var(--qbg-1);border:1px solid var(--qline);border-radius:2px;
  padding:10px 12px;font-family:var(--qmono)}
.qov-kpi-k{font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700;margin-bottom:4px}
.qov-kpi-v{font-size:15px;font-weight:700;line-height:1.2;color:var(--qink)}
.qov-kpi-v.gn{color:var(--gn);} .qov-kpi-v.am{color:var(--am);} .qov-kpi-v.rd{color:var(--rd);}
.qov-kpi-sub{font-size:10px;color:var(--qink-3);margin-top:2px}

/* edge bar */
.qov-edge{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;
  padding:10px 12px;background:var(--qbg-1);border:1px solid var(--qline);
  border-radius:2px;margin-bottom:12px}
.qov-edge .side{display:flex;flex-direction:column;font-family:var(--qmono)}
.qov-edge .side.r{align-items:flex-end}
.qov-edge .side .k{font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700}
.qov-edge .side .v{font-size:18px;font-weight:700}
.qov-edge .bar{display:flex;height:10px;background:var(--qbg-3);border-radius:2px;overflow:hidden}
.qov-edge .bar .p{background:var(--gn);height:100%}
.qov-edge .bar .n{background:var(--rd);height:100%}
.qov-edge .bar .x{background:var(--qink-4);height:100%}

/* 3-lens grid */
.qov-lens{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.qov-lens-p{background:var(--qbg-1);border:1px solid var(--qline);border-radius:2px;
  padding:10px 12px;font-family:var(--qmono)}
.qov-lens-h{font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700;padding-bottom:6px;
  border-bottom:1px solid var(--qline);margin-bottom:8px}
.qov-lens-sub{font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--qink-4);font-weight:700;margin:10px 0 4px;padding-top:6px;
  border-top:1px solid var(--qline)}
.qov-lens-row{display:flex;justify-content:space-between;padding:4px 0;font-size:11px;align-items:baseline}
.qov-lens-row .k{color:var(--qink-3);font-size:10px}
.qov-lens-row .v{color:var(--qink);font-weight:700}
.qov-lens-row .v.gn{color:var(--gn);} .qov-lens-row .v.am{color:var(--am);} .qov-lens-row .v.rd{color:var(--rd);}
.qov-lens-row .v.dim{color:var(--qink-3);}
.qov-lens-bignum{font-size:32px;font-weight:700;line-height:1;margin:4px 0 10px;font-family:var(--qmono);color:var(--qink)}
.qov-lens-bignum.gn{color:var(--gn);} .qov-lens-bignum.am{color:var(--am);} .qov-lens-bignum.rd{color:var(--rd);}
.qov-lens-bignum .sub{font-size:11px;color:var(--qink-3);font-weight:500;margin-left:8px;letter-spacing:.04em}

/* 2-col grid */
.qov-grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.qov-pane{background:var(--qbg-1);border:1px solid var(--qline);border-radius:2px;padding:10px 12px}
.qov-pane-h{display:flex;justify-content:space-between;align-items:baseline;
  font-family:var(--qmono);font-size:9.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--qink-3);font-weight:700;
  padding-bottom:5px;border-bottom:1px solid var(--qline);margin-bottom:8px}
.qov-pane-h .m{color:var(--qink-4);font-weight:500;letter-spacing:.08em;text-transform:none}

/* tables */
.qov-tbl{width:100%;border-collapse:collapse;font-family:var(--qmono);font-size:11px}
.qov-tbl thead th{font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700;text-align:left;padding:5px 4px;
  border-bottom:1px solid var(--qline-2)}
.qov-tbl thead th.r{text-align:right}
.qov-tbl tbody td{padding:5px 4px;color:var(--qink-1);border-bottom:1px solid var(--qline)}
.qov-tbl tbody td.r{text-align:right}
.qov-tbl tbody tr.now td{background:rgba(91,229,124,0.05);border-top:1px solid var(--gn-dim);border-bottom:1px solid var(--gn-dim)}
.qov-tbl b{color:var(--qink);font-weight:700}

/* radar */
.qov-radar{width:100%;height:160px;display:block}

/* mech block */
.qov-mech{margin-top:10px;padding-top:8px;border-top:1px solid var(--qline);
  font-family:var(--qmono);font-size:11px;line-height:1.65}
.qov-mech-row{padding:4px 0;display:flex;gap:12px}
.qov-mech-row .k{font-size:9px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--qink-3);font-weight:700;flex-shrink:0;min-width:120px}
.qov-mech-row .v{color:var(--qink-1)}

/* mini pills */
.qov-mpill{font-family:var(--qmono);font-size:9px;padding:1px 6px;border-radius:2px;
  background:var(--qbg-2);border:1px solid var(--qline-2);
  color:var(--qink-2);letter-spacing:.06em;text-transform:uppercase;font-weight:700;
  display:inline-block;line-height:1.4}
.qov-mpill.gn{color:var(--gn);border-color:var(--gn-dim);background:var(--gn-bg)}
.qov-mpill.am{color:var(--am);border-color:var(--am-dim);background:var(--am-bg)}
.qov-mpill.rd{color:var(--rd);border-color:var(--rd-dim);background:var(--rd-bg)}

/* responsive guard */
@media (max-width: 1024px){
  .qov-lens{grid-template-columns:1fr}
  .qov-grid2{grid-template-columns:1fr}
  .qov-strip{grid-template-columns:1fr 1fr}
}
`;

function _ensureStyle() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('qov-style')) return;
  const s = document.createElement('style');
  s.id = 'qov-style';
  s.textContent = QOV_CSS;
  document.head.appendChild(s);
}

// ─── render ──────────────────────────────────────────────────────────
export function render() {
  _ensureStyle();
  const T = _T();
  const DATA = _D();
  const body = (typeof $ === 'function') ? $('eliteOverviewBody')
              : document.getElementById('eliteOverviewBody');
  if (!body || !T) return;

  // ── canonical reads ──
  const rawV    = (T.decision?.verdict || T.verdict || T.stage || 'WATCH').toUpperCase();
  const eqRaw   = (T.entry_quality || '').toUpperCase();
  const convLbl = (T.conviction && T.conviction.label) || '';
  const tailDemoted = T.conviction && T.conviction.tail_filter_demoted === true;
  const eqBad   = ['EXTENDED','MISSED'].includes(eqRaw);
  const isDemoted = (rawV === 'BUY') && (eqBad || convLbl === 'WATCH' || tailDemoted);
  const v       = isDemoted ? 'WAIT' : rawV;
  const score   = num(T.score, 0);
  const pX      = num(T.price, 0);
  const c       = num(T.pct_chg, 0);
  const regime  = (T.regime || T.regime4 || DATA.regime?.label || DATA.regime?.regime || 'risk_on_choppy').toLowerCase();
  const regimeF = REGIME_FLOOR[regime] ?? 65;
  const scoreGap = regimeF - score;
  const setupTxt = T.setup_family || T.setup || '—';
  const catTier  = T.catalyst_tier || '—';

  // trade plan canonical (K6 source of truth)
  const ctp  = T?.canonical_trade_plan || {};
  const stop = num(ctp.stop ?? T.trade_plan?.stop ?? T.stop, 0);
  const t1   = num(ctp.target1 ?? T.trade_plan?.target1 ?? T.target1 ?? T.t1, 0);
  const t2   = num(ctp.target2 ?? T.trade_plan?.target2 ?? T.target2 ?? T.t2, 0);
  const eLo  = num(ctp.entry?.low  ?? T.trade_plan?.entry_low  ?? T.entry_lo, pX);
  const eHi  = num(ctp.entry?.high ?? T.trade_plan?.entry_high ?? T.entry_hi, pX);
  const stopPct = stop && pX ? ((stop - pX)/pX * 100) : NaN;
  const t1Pct   = t1 && pX ? ((t1 - pX)/pX * 100)   : NaN;
  const t2Pct   = t2 && pX ? ((t2 - pX)/pX * 100)   : NaN;
  const cachedRR = num(ctp.risk?.rr_ratio ?? T.trade_plan?.rr_ratio ?? T.rr_ratio ?? T.rr, 0);
  const realRR   = (pX && stop && t1 && pX > stop && t1 > pX) ? (t1 - pX)/(pX - stop) : null;
  const rr       = isDemoted && realRR != null ? realRR : cachedRR;

  // pullback zone
  const pbLo = num(T.trade_plan?.primary_zone_low  || T.trade_plan?.shallow_zone_low,  0);
  const pbHi = num(T.trade_plan?.primary_zone_high || T.trade_plan?.shallow_zone_high, 0);
  const pullbackZone = (pbLo && pbHi) ? `$${pbLo.toFixed(2)}–$${pbHi.toFixed(2)}` :
                       (eLo && eHi) ? `$${eLo.toFixed(2)}–$${eHi.toFixed(2)}` : '—';

  // technicals
  const techI = T.technicals?.indicators || {};
  const rsi   = num(techI.rsi   ?? T.rsi,   NaN);
  const rvol  = num(techI.rvol  ?? T.rvol,  NaN);
  const adx   = num(techI.adx   ?? T.adx,   NaN);
  const atrPct = num(techI.atr_pct ?? T.atr_pct, NaN);
  const macdHist = num(techI.macd_hist ?? T.macd_hist, NaN);
  const macdBull = !!(techI.macd_bullish ?? T.macd_bullish);
  const sqz   = !!(techI.squeeze_on ?? T.squeeze_on);
  const above50  = !!(techI.above_ema50 ?? T.above_50ema);
  const above200 = !!(techI.above_sma200 ?? T.above_200sma);
  const ema21    = num(techI.ema21 ?? T.ema21, NaN);
  const ema50    = num(techI.ema50 ?? T.ema50, NaN);
  const week52H  = num(T.week52_high, NaN);
  const week52L  = num(T.week52_low, NaN);
  const vwap     = num(techI.vwap ?? T.vwap, NaN);
  const anchVwap = num(techI.anchored_vwap ?? T.anchored_vwap, NaN);
  const distPct  = (lvl) => isNaN(lvl) || !pX ? NaN : ((lvl - pX)/pX * 100);

  // pillars
  const sb    = T.scoring_breakdown || {};
  const techS = num(T.tech_score ?? sb.tech_score, 0);
  const catS  = num(T.cat_score  ?? sb.cat_score,  0);
  const rsS   = num(T.rs_score   ?? sb.rs_score,   0);
  const smS   = num(T.sm_score   ?? sb.sm_score,   0);
  const qS    = num(T.qg_score   ?? sb.qg_score   ?? T.fund_score, 0);
  const techMax = num(T.tech_max, 35);
  const fundMax = num(T.fund_max, 10);

  // flow / smart-money
  const ins  = T.insider_full || T.insider || T.insider_data || {};
  const insBuys  = num(ins.buys_30d ?? ins.buys ?? T.insider_buys, 0);
  const insSells = num(ins.sells_30d ?? ins.sells ?? T.insider_sells, 0);
  const insNet$  = num(ins.total_buy_value ?? ins.net_value, NaN);
  const insDays  = num(ins.days_since_last ?? T.insider_days, NaN);
  const ceoBuy   = !!ins.ceo_buy;
  const cfoBuy   = !!ins.cfo_buy;

  const fr = T.fund_real || {};
  const fd = T.fund_details || {};
  const fx = T.eodhd_fund_extras || {};
  const oiv = T.options_iv || {};

  const instOwn  = num(fr.inst_own_pct ?? T.inst_own_pct, NaN);
  const shortPct = num(fr.short_pct ?? T.short_pct, NaN);
  const floatSh  = num(fr.float_shares ?? T.float_shares, NaN);
  const advDol   = num(T.adv_dollar ?? T.dollar_volume_20d ?? T.avg_dollar_volume, NaN);
  const advShr   = num(T.avg_volume_20d ?? T.adv_shares, NaN);
  // days-to-cover = short shares / avg daily volume
  let daysToCover = NaN;
  if (!isNaN(shortPct) && !isNaN(floatSh) && !isNaN(advShr) && advShr > 0) {
    daysToCover = (shortPct/100 * floatSh) / advShr;
  }

  const uoaCalls = num(oiv.uoa_calls ?? T.uoa_calls, NaN);
  const uoaPuts  = num(oiv.uoa_puts ?? T.uoa_puts, NaN);
  const pcRatio  = num(oiv.put_call_ratio ?? T.put_call_ratio, NaN);
  const ivRank   = num(oiv.iv_rank ?? T.iv_rank, NaN);
  const ivCur    = num(oiv.current_iv ?? T.current_iv ?? oiv.iv, NaN);
  const maxPain  = num(oiv.max_pain, NaN);

  const ana = T.analyst_full || T.analyst || {};
  const ptMean   = num(ana.target_mean ?? T.analyst_target, NaN);
  const ptHigh   = num(ana.target_high, NaN);
  const ptLow    = num(ana.target_low, NaN);
  const upside   = num(ana.upside_pct ?? T.analyst_upside, NaN);
  const aBuy     = num(ana.buy, 0);
  const aStrBuy  = num(ana.strong_buy, 0);
  const aHold    = num(ana.hold, 0);
  const aSell    = num(ana.sell, 0);
  const aStrSell = num(ana.strong_sell, 0);
  const aTotal   = aBuy + aStrBuy + aHold + aSell + aStrSell;
  const buyPctTotal = aTotal > 0 ? (aBuy + aStrBuy) / aTotal : NaN;
  const upgrades10 = num(ana.upgrades_10d, NaN);
  const downgrades10 = num(ana.downgrades_10d, NaN);
  const revUp30   = num(ana.rev_current_q_up30 ?? ana.rev_next_q_up30, NaN);
  const revDown30 = num(ana.rev_current_q_down30 ?? ana.rev_next_q_down30, NaN);

  const newsScore = T.news_sentiment_score || {};
  const eodhdSent = T.eodhd_sentiment || {};
  const newsArts  = T.news_articles || [];
  const newsAvg   = num(newsScore.avg_sentiment ?? eodhdSent.avg ?? T.news, 0);
  const newsCount = num(newsScore.article_count ?? newsArts.length, NaN);
  const newsMom   = (newsScore.momentum || '').toLowerCase();

  // fundamentals
  const mcap     = num(fr.market_cap ?? fd.market_cap ?? T.market_cap, NaN);
  const beta     = num(fr.beta ?? fd.beta ?? T.beta, NaN);
  const fwdPE    = num(fr.fwd_pe ?? fx.forward_pe ?? T.fwd_pe, NaN);
  const peg      = num(fr.peg ?? fx.peg ?? T.peg, NaN);
  const ps       = num(fr.price_to_sales ?? fx.price_to_sales ?? T.price_to_sales, NaN);
  const pb       = num(fr.price_to_book, NaN);
  const ev_ebitda = num(fr.ev_ebitda ?? fx.ev_ebitda, NaN);
  const revGrow  = num(fr.rev_growth_pct ?? fr.rev_growth ?? fd.rev_growth ?? T.rev_growth, NaN);
  const epsGrow  = num(fr.eps_growth_pct ?? T.eps_growth, NaN);
  const grossMgn = num(fr.gross_margin_pct ?? T.gross_margin, NaN);
  const netMgn   = num(fr.net_margin_pct ?? fr.net_margin ?? fd.net_margin ?? T.net_margin, NaN);
  const opMgn    = num(fr.op_margin_pct ?? fr.op_margin, NaN);
  const fcfTtm   = num(fx.free_cash_flow_ttm, NaN);
  const revTtm   = num(fx.revenue_ttm, NaN);
  const fcfMgn   = (!isNaN(fcfTtm) && !isNaN(revTtm) && revTtm) ? (fcfTtm/revTtm * 100) : NaN;
  const debtEq   = num(fr.debt_to_equity ?? fd.debt_to_equity ?? T.debt_to_equity, NaN);
  const roe      = num(fr.roe_pct ?? fr.roe ?? fd.roe ?? T.roe, NaN);

  // monte-carlo + forward dist
  const mc = T.monte_carlo || {};
  const fwd = T.forward_dist || {};
  const pT1First   = num(mc.p_hit_target_first, NaN);
  const pStopFirst = num(mc.p_hit_stop_first, NaN);
  const pNeither   = num(mc.p_neither_hit, NaN);
  const edge       = (!isNaN(pT1First) && !isNaN(pStopFirst)) ? (pT1First - pStopFirst) : NaN;
  const fwdSharpe  = num(mc.fwd_sharpe ?? fwd.fwd_sharpe, NaN);
  const var95      = num(fwd.var_95_pct ?? mc.var_95_pct, NaN);
  const cvar975    = num(fwd.cvar_975_pct ?? mc.cvar_975_pct, NaN);

  // kelly sizing
  const kelly = T.kelly_size || {};
  const finalAlloc = num(kelly.final_alloc_pct, NaN);
  const regimeMult = num(kelly.regime_mult, NaN);
  const vixMult    = num(kelly.vix_mult, NaN);
  const ddMult     = num(kelly.drawdown_mult, NaN);
  const earnMult   = num(kelly.earnings_mult, NaN);
  const varMult    = num(kelly.var_floor_mult, NaN);

  // earnings
  const earnDays  = num(T.earn_days ?? kelly.earnings_days, NaN);
  const earnBeat  = num(T.earnings_beat, NaN);
  // implied move ≈ IV_annual * sqrt(days_to_event / 252)
  let impMove = NaN;
  if (!isNaN(ivCur) && !isNaN(earnDays) && earnDays > 0) {
    impMove = (ivCur > 1 ? ivCur/100 : ivCur) * Math.sqrt(earnDays/252) * 100;
  } else if (!isNaN(ivRank) && !isNaN(earnDays)) {
    // fallback rough estimate when only iv_rank exists
    impMove = (ivRank/100 * 0.40) * Math.sqrt(earnDays/252) * 100;
  }

  // gates + conviction
  const gates  = T.gates_evaluated || [];
  const failedGates = gates.filter(g => g && (g.passed === false || g.status === 'fail'));
  const passedGates = gates.filter(g => g && (g.passed === true || g.status === 'pass'));

  // setup family stats (from DATA aggregates if exposed)
  const setupCounts = DATA.setup_counts || {};
  const setupN_all = num(setupCounts[setupTxt], NaN);

  // setup historical WR — pull from any exposed shape
  const setupHist = (DATA.setup_stats || DATA.setup_wr_aggregates || {})[setupTxt] || T.setup_history || {};
  const setupWR_all   = num(setupHist.wr_all ?? setupHist.wr, NaN);
  const setupN_hist   = num(setupHist.n ?? setupHist.n_all, NaN);
  const setupPF_all   = num(setupHist.pf, NaN);
  const setupAvgR     = num(setupHist.avg_r, NaN);
  const setupLB_all   = (!isNaN(setupWR_all) && !isNaN(setupN_hist))
                        ? wilsonLB(setupWR_all/100, setupN_hist) : null;

  // earnings history
  const earnHist = T.earnings_history || T.eodhd_earnings_history || [];
  const recentEarn = Array.isArray(earnHist) ? earnHist.slice(0, 4) : [];

  // ── ★ DECISION STRIP (top of overview body) ★ ──────────────────────
  const reason = T.decision?.reason || '';
  let whyHTML = '';
  if (v === 'BUY' && !isDemoted) {
    whyHTML = `BAP <b class="qov-gn">${score}</b> ≥ <b>${regimeF}</b> floor · entry <b class="qov-gn">${eqRaw || 'FRESH'}</b>${reason ? ' · ' + reason : ''}`;
  } else if (isDemoted) {
    whyHTML = `entry <b class="qov-rd">${eqRaw || '—'}</b>${realRR != null ? ` · R:R now ${realRR.toFixed(2)}:1` : ''} — chase territory`;
  } else if (v === 'AVOID' || v === 'SHORT' || v === 'SELL') {
    const parts = [];
    if (scoreGap > 0) parts.push(`BAP <b class="qov-rd">${score}</b> &lt; ${regimeF} (gap +${scoreGap})`);
    if (failedGates.length) parts.push(`failed: <b class="qov-rd">${failedGates.slice(0,2).map(g=>g.name||g.gate).join(', ')}</b>`);
    if (regime === 'panic') parts.push(`regime <b class="qov-rd">PANIC</b>`);
    whyHTML = parts.length ? parts.join(' · ') : (reason || '—');
  } else { // WATCH
    const parts = [];
    if (scoreGap > 0) parts.push(`BAP <b class="qov-am">${score}</b> &lt; ${regimeF} (gap +${scoreGap})`);
    if (eqRaw && eqRaw !== 'FRESH') parts.push(`entry <b class="qov-am">${eqRaw}</b>`);
    whyHTML = parts.length ? parts.join(' · ') : (reason || 'pending trigger');
  }
  const flipHTML = (() => {
    const parts = [];
    if (eqBad && pullbackZone !== '—') parts.push(`pullback to <b>${pullbackZone}</b>`);
    if (scoreGap > 0 && scoreGap < 15) parts.push(`+${scoreGap} BAP needed`);
    if (regime === 'panic') parts.push(`regime exit from panic`);
    if (!parts.length && v === 'BUY' && !isDemoted) return 'currently tradeable';
    return parts.length ? parts.join(' · ') : 'no clear path — wait for full re-score';
  })();
  const nextCatHTML = (!isNaN(earnDays) && earnDays < 999)
    ? `<b>ER ${earnDays >= 0 ? '+' : ''}${earnDays}d</b>${!isNaN(impMove) ? ' · IMPL <b>±'+impMove.toFixed(1)+'%</b>' : ''}`
    : (DATA.economic_events && DATA.economic_events.length ? `<b>${DATA.economic_events[0].type || DATA.economic_events[0].event || 'macro'}</b>` : '—');
  const sizeHTML = !isNaN(finalAlloc)
    ? (finalAlloc > 0 ? `<b class="qov-gn">${finalAlloc.toFixed(1)}%</b> Kelly` : `<b class="qov-dim">0%</b> <span class="qov-dim">— ${v === 'BUY' ? 'demoted' : 'gate fail'}</span>`)
    : '—';

  const stripHTML = `
    <div class="qov-strip" style="border-left-color:${v==='BUY'?'var(--gn)':v==='WATCH'?'var(--am)':'var(--rd)'}">
      <div>
        <div class="k">WHY ${v} · ${regime.toUpperCase().replace(/_/g,' ')}</div>
        <div class="v">${whyHTML}</div>
      </div>
      <div>
        <div class="k">WOULD FLIP IF</div>
        <div class="v">${flipHTML}</div>
      </div>
      <div>
        <div class="k">NEXT CATALYST</div>
        <div class="v">${nextCatHTML}</div>
      </div>
      <div>
        <div class="k">POSITION SIZE · Kelly-lite</div>
        <div class="v">${sizeHTML}</div>
      </div>
    </div>`;

  // ── ★ SECTION 1 · TRIAGE BAND (6 KPIs) ★ ──────────────────────────
  const smartBlend = (() => {
    // 5-component blend on smart-money: insider · 13F · UOA · news velocity · sentiment slope
    // Fallback to sm_score normalized to 100 when components missing.
    const smPct100 = !isNaN(smS) ? (smS / 15 * 100) : NaN;
    return smPct100;
  })();
  const triageHTML = `
    <div class="qov-note"><span class="why">▣ TRIAGE BAND</span> &nbsp; one row, six numbers — the decision math compressed. P(T1)/P(stop) come from Monte Carlo per-ticker (jump-diffusion); smart-money blends insider + UOA + news + sentiment.</div>
    <div class="qov-kpi-row" style="grid-template-columns:repeat(6,1fr)">
      <div class="qov-kpi"><div class="qov-kpi-k">BAP</div><div class="qov-kpi-v ${score >= regimeF ? 'gn' : 'am'}">${score}</div><div class="qov-kpi-sub">/100 · floor ${regimeF}</div></div>
      <div class="qov-kpi"><div class="qov-kpi-k">P(T1) FIRST</div><div class="qov-kpi-v ${isNaN(pT1First) ? 'dim' : pT1First >= 55 ? 'gn' : pT1First >= 40 ? 'am' : 'rd'}">${isNaN(pT1First) ? '—' : pT1First.toFixed(0) + '%'}</div><div class="qov-kpi-sub">MC · ${mc.n_paths || '—'} paths</div></div>
      <div class="qov-kpi"><div class="qov-kpi-k">P(STOP) FIRST</div><div class="qov-kpi-v ${isNaN(pStopFirst) ? 'dim' : pStopFirst <= 25 ? 'gn' : pStopFirst <= 40 ? 'am' : 'rd'}">${isNaN(pStopFirst) ? '—' : pStopFirst.toFixed(0) + '%'}</div><div class="qov-kpi-sub">close-based stop</div></div>
      <div class="qov-kpi"><div class="qov-kpi-k">EDGE</div><div class="qov-kpi-v ${isNaN(edge) ? 'dim' : edge >= 20 ? 'gn' : edge >= 5 ? 'am' : 'rd'}">${isNaN(edge) ? '—' : (edge >= 0 ? '+' : '') + edge.toFixed(0)}</div><div class="qov-kpi-sub">P(T1) − P(stop)</div></div>
      <div class="qov-kpi"><div class="qov-kpi-k">IV RANK</div><div class="qov-kpi-v ${isNaN(ivRank) ? 'dim' : ivRank > 70 ? 'am' : ''}">${isNaN(ivRank) ? '—' : ivRank.toFixed(0) + '%'}</div><div class="qov-kpi-sub">${isNaN(ivRank) ? 'no option chain' : ivRank > 70 ? 'elevated' : ivRank > 30 ? 'normal' : 'low'}</div></div>
      <div class="qov-kpi"><div class="qov-kpi-k">SMART-MONEY</div><div class="qov-kpi-v ${isNaN(smartBlend) ? 'dim' : smartBlend >= 60 ? 'gn' : smartBlend >= 40 ? 'am' : 'rd'}">${isNaN(smartBlend) ? '—' : smartBlend.toFixed(0) + '/100'}</div><div class="qov-kpi-sub">5-comp blend</div></div>
    </div>`;

  // ── ★ SECTION 2 · EDGE BAR ★ ──────────────────────────────────────
  const edgeBarHTML = `
    <div class="qov-edge">
      <div class="side"><div class="k">P(T1 FIRST)</div><div class="v qov-gn">${isNaN(pT1First) ? '—' : pT1First.toFixed(0) + '%'}</div></div>
      <div class="bar">
        <span class="p" style="width:${isNaN(pT1First) ? 0 : Math.max(0,Math.min(100,pT1First))}%"></span>
        <span class="x" style="width:${isNaN(pNeither) ? 0 : Math.max(0,Math.min(100,pNeither))}%"></span>
        <span class="n" style="width:${isNaN(pStopFirst) ? 0 : Math.max(0,Math.min(100,pStopFirst))}%"></span>
      </div>
      <div class="side r"><div class="k">P(STOP FIRST)</div><div class="v qov-rd">${isNaN(pStopFirst) ? '—' : pStopFirst.toFixed(0) + '%'}</div></div>
    </div>`;

  // ── ★ SECTION 3 · 3-LENS EVIDENCE ★ ───────────────────────────────
  // radar (5 pillars) using actual scoring breakdown
  const _radarPt = (pct, ang) => {
    const r = 60 * pct;
    return [90 + r * Math.sin(ang), 80 - r * Math.cos(ang)];
  };
  const _pillarPct = [
    Math.min(1, techS / techMax),
    Math.min(1, catS  / 20),
    Math.min(1, rsS   / 20),
    Math.min(1, smS   / 15),
    Math.min(1, qS    / fundMax),
  ];
  const _radarPts = _pillarPct.map((p, i) => _radarPt(p, i * 2 * Math.PI / 5)).map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const radarSvg = `
    <svg class="qov-radar" viewBox="0 0 180 160" preserveAspectRatio="xMidYMid meet">
      <polygon points="90,20 145,61 124,135 56,135 35,61" fill="none" stroke="var(--qline)" stroke-width="0.5"/>
      <polygon points="90,40 124,68 113,118 67,118 56,68" fill="none" stroke="var(--qline)" stroke-width="0.5"/>
      <polygon points="90,60 103,75 102,105 78,105 77,75" fill="none" stroke="var(--qline)" stroke-width="0.5"/>
      <line x1="90" y1="80" x2="90" y2="20" stroke="var(--qline-2)" stroke-width="0.6"/>
      <line x1="90" y1="80" x2="147" y2="61" stroke="var(--qline-2)" stroke-width="0.6"/>
      <line x1="90" y1="80" x2="125" y2="135" stroke="var(--qline-2)" stroke-width="0.6"/>
      <line x1="90" y1="80" x2="55" y2="135" stroke="var(--qline-2)" stroke-width="0.6"/>
      <line x1="90" y1="80" x2="33" y2="61" stroke="var(--qline-2)" stroke-width="0.6"/>
      <polygon points="${_radarPts}" fill="rgba(91,229,124,0.18)" stroke="var(--gn)" stroke-width="1.5"/>
      <text x="90"  y="14"  text-anchor="middle" font-family="var(--qmono)" font-size="9" font-weight="700" fill="var(--qink-2)">TRD</text>
      <text x="159" y="62"  text-anchor="middle" font-family="var(--qmono)" font-size="9" font-weight="700" fill="var(--qink-2)">CAT</text>
      <text x="138" y="149" text-anchor="middle" font-family="var(--qmono)" font-size="9" font-weight="700" fill="var(--qink-2)">RS</text>
      <text x="42"  y="149" text-anchor="middle" font-family="var(--qmono)" font-size="9" font-weight="700" fill="var(--qink-2)">SM</text>
      <text x="21"  y="62"  text-anchor="middle" font-family="var(--qmono)" font-size="9" font-weight="700" fill="var(--qink-2)">QUAL</text>
    </svg>`;

  // distances helper
  const distRow = (label, lvl) => {
    if (isNaN(lvl) || !lvl) return `<div class="qov-lens-row"><span class="k">${label}</span><span class="v dim">—</span></div>`;
    const d = distPct(lvl);
    const cls = d == null || isNaN(d) ? 'dim' : d < -5 ? 'rd' : d < 0 ? 'am' : d > 5 ? 'am' : 'gn';
    return `<div class="qov-lens-row"><span class="k">${label}</span><span class="v ${cls}">$${lvl.toFixed(2)} · ${d >= 0 ? '+' : ''}${d.toFixed(1)}%</span></div>`;
  };

  // ── LENS A · TECHNICAL ──
  const lensTechHTML = `
    <div class="qov-lens-p">
      <div class="qov-lens-h">▣ TECHNICAL</div>
      <div style="text-align:center;margin-bottom:6px">${radarSvg}</div>
      <div class="qov-lens-row"><span class="k">RSI(14)</span><span class="v ${rsi > 70 ? 'am' : rsi < 30 ? 'am' : isNaN(rsi) ? 'dim' : 'gn'}">${isNaN(rsi) ? '—' : rsi.toFixed(0) + (rsi > 70 ? ' overbought-edge' : rsi < 30 ? ' oversold' : '')}</span></div>
      <div class="qov-lens-row"><span class="k">MACD HIST</span><span class="v ${macdBull ? 'gn' : 'rd'}">${isNaN(macdHist) ? (macdBull ? 'BULLISH cross' : 'BEARISH') : (macdHist >= 0 ? '+' : '') + macdHist.toFixed(2) + (macdBull ? ' expanding' : ' contracting')}</span></div>
      <div class="qov-lens-row"><span class="k">ADX</span><span class="v ${isNaN(adx) ? 'dim' : adx >= 25 ? 'gn' : 'am'}">${isNaN(adx) ? '—' : adx.toFixed(0) + (adx >= 25 ? ' strong trend' : ' weak')}</span></div>
      <div class="qov-lens-row"><span class="k">RVOL</span><span class="v ${isNaN(rvol) ? 'dim' : rvol >= 1.5 ? 'gn' : rvol >= 1 ? 'am' : 'rd'}">${isNaN(rvol) ? '—' : rvol.toFixed(2) + '× ' + (rvol >= 1.5 ? 'expansion' : rvol >= 1 ? 'normal' : 'soft')}</span></div>
      <div class="qov-lens-row"><span class="k">ATR%</span><span class="v">${isNaN(atrPct) ? '—' : atrPct.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">SQUEEZE</span><span class="v ${sqz ? 'gn' : 'dim'}">${sqz ? 'FIRED · bullish' : 'off'}</span></div>
      <div class="qov-lens-sub">DISTANCE TO LEVELS</div>
      ${distRow('EMA 21', ema21)}
      ${distRow('EMA 50', ema50)}
      ${distRow('52W HI', week52H)}
      ${distRow('52W LO', week52L)}
      ${distRow('VWAP D', vwap)}
      ${distRow('ANCH VWAP', anchVwap)}
      <div class="qov-lens-row"><span class="k">ENTRY ZONE</span><span class="v ${pbLo ? 'gn' : 'dim'}">${pbLo ? '$' + pbLo.toFixed(2) + '–$' + pbHi.toFixed(2) : '—'}</span></div>
    </div>`;

  // ── LENS B · FLOW ──
  const newsBias = newsAvg > 0.05 ? 'IMPROVING' : newsAvg < -0.05 ? 'DETERIORATING' : 'flat';
  const newsCls  = newsAvg > 0.05 ? 'gn' : newsAvg < -0.05 ? 'rd' : 'am';
  const lensFlowHTML = `
    <div class="qov-lens-p">
      <div class="qov-lens-h">⚯ FLOW</div>
      <div class="qov-lens-bignum ${isNaN(smartBlend) ? '' : smartBlend >= 60 ? 'gn' : smartBlend >= 40 ? 'am' : 'rd'}">${isNaN(smartBlend) ? '—' : smartBlend.toFixed(0)}<span class="sub">/100 smart-money</span></div>
      <div class="qov-lens-row"><span class="k">INSIDER 30d</span><span class="v ${insBuys > 0 ? 'gn' : insSells > 0 ? 'rd' : 'dim'}">${insBuys}B · ${insSells}S${!isNaN(insNet$) && insNet$ > 0 ? ' · +' + fmtMcap(insNet$) : ''}</span></div>
      <div class="qov-lens-row"><span class="k">FORM 4 LAST</span><span class="v ${insDays < 30 ? 'gn' : 'dim'}">${insDays < 999 && !isNaN(insDays) ? (ceoBuy ? 'CEO buy · ' : cfoBuy ? 'CFO buy · ' : '') + insDays + 'd ago' : 'none ' + (insDays >= 999 ? '>1yr' : '')}</span></div>
      <div class="qov-lens-row"><span class="k">INST %</span><span class="v">${isNaN(instOwn) ? '—' : instOwn.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">13F Δ 90d</span><span class="v dim">— <span style="font-size:8px;opacity:.7">(no source)</span></span></div>
      <div class="qov-lens-row"><span class="k">SHORT FLOAT</span><span class="v ${shortPct > 15 ? 'am' : shortPct > 25 ? 'rd' : ''}">${isNaN(shortPct) ? '—' : shortPct.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">DAYS TO COVER</span><span class="v ${daysToCover > 5 ? 'am' : ''}">${isNaN(daysToCover) ? '—' : daysToCover.toFixed(1) + 'd'}</span></div>
      <div class="qov-lens-sub">UOA / OPTIONS FLOW</div>
      <div class="qov-lens-row"><span class="k">UOA CALLS</span><span class="v ${uoaCalls > 0 ? 'gn' : 'dim'}">${isNaN(uoaCalls) ? '—' : uoaCalls + (uoaCalls > 0 ? ' · vol>3×OI' : '')}</span></div>
      <div class="qov-lens-row"><span class="k">UOA PUTS</span><span class="v ${uoaPuts > 0 ? 'rd' : 'dim'}">${isNaN(uoaPuts) ? '—' : uoaPuts}</span></div>
      <div class="qov-lens-row"><span class="k">P/C ratio</span><span class="v ${pcRatio < 0.7 ? 'gn' : pcRatio > 1.2 ? 'rd' : ''}">${isNaN(pcRatio) ? '—' : pcRatio.toFixed(2) + (pcRatio < 0.7 ? ' call-heavy' : pcRatio > 1.2 ? ' put-heavy' : '')}</span></div>
      <div class="qov-lens-row"><span class="k">MAX PAIN</span><span class="v">${isNaN(maxPain) ? '—' : '$' + maxPain.toFixed(2)}</span></div>
      <div class="qov-lens-sub">NEWS / SENTIMENT</div>
      <div class="qov-lens-row"><span class="k">NEWS 7d</span><span class="v">${isNaN(newsCount) ? '—' : newsCount + ' headlines'}</span></div>
      <div class="qov-lens-row"><span class="k">SENT TREND</span><span class="v ${newsCls}">${newsBias}${newsMom ? ' · ' + newsMom : ''}</span></div>
      <div class="qov-lens-row"><span class="k">UPGRADES 10d</span><span class="v ${upgrades10 > 0 ? 'gn' : 'dim'}">↑${isNaN(upgrades10) ? '—' : upgrades10} / ↓${isNaN(downgrades10) ? '—' : downgrades10}</span></div>
    </div>`;

  // ── LENS C · QUALITY ──
  // composite quality grade
  let qGrade = '—', qScore = NaN;
  if (!isNaN(qS) && fundMax) {
    qScore = qS / fundMax * 10;
    qGrade = qScore >= 8.5 ? 'A' : qScore >= 7.5 ? 'A−' : qScore >= 6.5 ? 'B+' : qScore >= 5.5 ? 'B' : qScore >= 4.5 ? 'C+' : qScore >= 3 ? 'C' : 'D';
  }
  const qGradeCls = isNaN(qScore) ? '' : qScore >= 7 ? 'gn' : qScore >= 5 ? 'am' : 'rd';

  // earnings beat history
  const beatCount = recentEarn.filter(e => (e.surprise_pct ?? e.surprise ?? 0) > 0).length;
  const beatPattern = recentEarn.length ? recentEarn.map(e => {
    const s = num(e.surprise_pct ?? e.surprise, 0);
    return s > 0 ? '<b class="qov-gn">B</b>' : s < 0 ? '<b class="qov-rd">M</b>' : '<b class="qov-am">I</b>';
  }).join(' ') + ` · ${Math.round(beatCount/recentEarn.length*100)}%` : '—';
  const surpList = recentEarn.map(e => num(e.surprise_pct ?? e.surprise, 0)).filter(v => v !== 0).sort((a,b) => a - b);
  const medianSurp = surpList.length ? surpList[Math.floor(surpList.length/2)] : NaN;

  const lensQualHTML = `
    <div class="qov-lens-p">
      <div class="qov-lens-h">◆ QUALITY</div>
      <div class="qov-lens-bignum ${qGradeCls}">${qGrade}<span class="sub">${isNaN(qScore) ? '—' : qScore.toFixed(1) + '/10'}</span></div>
      <div class="qov-lens-row"><span class="k">FWD P/E</span><span class="v ${fwdPE > 35 ? 'am' : ''}">${isNaN(fwdPE) ? '—' : fwdPE.toFixed(1)}</span></div>
      <div class="qov-lens-row"><span class="k">PEG</span><span class="v ${peg < 1 ? 'gn' : peg > 2 ? 'am' : ''}">${isNaN(peg) ? '—' : peg.toFixed(2)}</span></div>
      <div class="qov-lens-row"><span class="k">P/S</span><span class="v">${isNaN(ps) ? '—' : ps.toFixed(2)}</span></div>
      <div class="qov-lens-row"><span class="k">EV/EBITDA</span><span class="v">${isNaN(ev_ebitda) ? '—' : ev_ebitda.toFixed(1)}</span></div>
      <div class="qov-lens-row"><span class="k">REV GROWTH YoY</span><span class="v ${revGrow > 15 ? 'gn' : revGrow > 0 ? 'am' : revGrow < 0 ? 'rd' : 'dim'}">${isNaN(revGrow) ? '—' : (revGrow >= 0 ? '+' : '') + revGrow.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">EPS GROWTH YoY</span><span class="v ${epsGrow > 20 ? 'gn' : epsGrow > 0 ? 'am' : epsGrow < 0 ? 'rd' : 'dim'}">${isNaN(epsGrow) ? '—' : (epsGrow >= 0 ? '+' : '') + epsGrow.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">GROSS MARGIN</span><span class="v ${grossMgn > 40 ? 'gn' : grossMgn > 20 ? 'am' : grossMgn ? 'rd' : 'dim'}">${isNaN(grossMgn) ? '—' : grossMgn.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">FCF MARGIN</span><span class="v ${fcfMgn > 15 ? 'gn' : fcfMgn > 0 ? 'am' : fcfMgn < 0 ? 'rd' : 'dim'}">${isNaN(fcfMgn) ? '—' : (fcfMgn >= 0 ? '+' : '') + fcfMgn.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">D/E</span><span class="v ${debtEq > 2 ? 'am' : debtEq > 4 ? 'rd' : ''}">${isNaN(debtEq) ? '—' : debtEq.toFixed(1)}</span></div>
      <div class="qov-lens-row"><span class="k">ROE</span><span class="v ${roe > 15 ? 'gn' : roe > 5 ? 'am' : roe < 0 ? 'rd' : 'dim'}">${isNaN(roe) ? '—' : roe.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">ANALYST UPSIDE</span><span class="v ${upside > 10 ? 'gn' : upside > 0 ? 'am' : upside < 0 ? 'rd' : 'dim'}">${isNaN(upside) ? '—' : (upside >= 0 ? '+' : '') + upside.toFixed(1) + '%' + (isNaN(ptMean) ? '' : ' · PT $' + ptMean.toFixed(0))}</span></div>
      <div class="qov-lens-row"><span class="k">BUY % (n=${aTotal})</span><span class="v ${buyPctTotal > 0.7 ? 'gn' : buyPctTotal > 0.5 ? 'am' : aTotal > 0 ? 'rd' : 'dim'}">${aTotal > 0 ? (buyPctTotal*100).toFixed(0) + '% buy' : '—'}</span></div>
      <div class="qov-lens-row"><span class="k">REVISIONS 30d</span><span class="v ${revUp30 > revDown30 ? 'gn' : revUp30 < revDown30 ? 'rd' : 'am'}">${isNaN(revUp30) ? '—' : '↑' + revUp30 + ' / ↓' + (isNaN(revDown30) ? 0 : revDown30) + (revUp30 > revDown30 ? ' BULLISH' : revUp30 < revDown30 ? ' BEARISH' : '')}</span></div>
      ${!isNaN(earnDays) && earnDays < 60 && earnDays > -7 ? `
      <div class="qov-lens-sub">ER ${earnDays >= 0 ? 'IN ' + earnDays + 'd' : Math.abs(earnDays) + 'd AGO'}</div>
      <div class="qov-lens-row"><span class="k">4Q PATTERN</span><span class="v">${beatPattern}</span></div>
      <div class="qov-lens-row"><span class="k">MEDIAN SURP</span><span class="v ${medianSurp > 0 ? 'gn' : medianSurp < 0 ? 'rd' : 'dim'}">${isNaN(medianSurp) ? '—' : (medianSurp >= 0 ? '+' : '') + medianSurp.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">IMPL ±%</span><span class="v">${isNaN(impMove) ? '—' : '±' + impMove.toFixed(1) + '%'}</span></div>
      <div class="qov-lens-row"><span class="k">EVENT VOL</span><span class="v ${ivRank > 70 ? 'am' : ivRank > 40 ? '' : 'gn'}">${isNaN(ivRank) ? '—' : ivRank > 70 ? 'RICH' : ivRank > 40 ? 'NORMAL' : 'CHEAP'}</span></div>
      ` : ''}
    </div>`;

  const lensHTML = `
    <div class="qov-note"><span class="why">⬢ 3-LENS EVIDENCE</span> &nbsp; same data, three independent reads. <b>Convergence</b> across all three = high conviction. <b>Divergence</b> = pass.</div>
    <div class="qov-lens">${lensTechHTML}${lensFlowHTML}${lensQualHTML}</div>`;

  // ── ★ SECTION 4 · TRADE WINDOW ★ ──────────────────────────────────
  const ladderRow = (lbl, lblCls, price, note, pct, pctCls) => `
    <tr ${lbl === 'NOW' ? 'class="now"' : ''}>
      <td><b class="${lblCls}">${lbl}</b></td>
      <td class="r"><b>${isNaN(price) ? '—' : '$' + price.toFixed(2)}</b></td>
      <td class="qov-dim">${note}</td>
      <td class="r ${pctCls}">${pct == null || isNaN(pct) ? '—' : (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%'}</td>
    </tr>`;

  // macro events: filter economic_events by next 30d
  const today = new Date();
  const upcomingMacro = (DATA.economic_events || [])
    .filter(e => e && e.date)
    .map(e => {
      const d = new Date(e.date);
      const days = Math.round((d - today) / 86400000);
      return { ...e, _days: days };
    })
    .filter(e => e._days >= -1 && e._days <= 30)
    .sort((a,b) => a._days - b._days)
    .slice(0, 6);

  const tradeWindowHTML = `
    <div class="qov-note"><span class="why">⧉ TRADE WINDOW</span> &nbsp; if the verdict allows, this is the executable plan. If not, what would need to happen for entry to make sense.</div>
    <div class="qov-grid2">
      <div class="qov-pane">
        <div class="qov-pane-h">PLAN LADDER <span class="m">live R:R from $${pX.toFixed(2)}</span></div>
        <table class="qov-tbl">
          ${t2 ? ladderRow('T2',   'qov-cy', t2,   'close ⅓',         t2Pct,   'qov-gn') : ''}
          ${t1 ? ladderRow('T1',   'qov-gn', t1,   'trim ⅔',          t1Pct,   'qov-gn') : ''}
          ${ladderRow('NOW',  '',       pX,   isDemoted ? 'WAIT' : v,  0,       'qov-dim')}
          ${eHi ? ladderRow('AVG',  'qov-am', (eLo + eHi) / 2, 'entry zone mid', ((eLo+eHi)/2 - pX)/pX*100, 'qov-am') : ''}
          ${stop ? ladderRow('STOP', 'qov-rd', stop, '1.25× ATR', stopPct, 'qov-rd') : ''}
        </table>
      </div>
      <div class="qov-pane">
        <div class="qov-pane-h">CATALYST CALENDAR <span class="m">±30d</span></div>
        <table class="qov-tbl">
          ${!isNaN(earnDays) && earnDays >= -7 && earnDays < 60 ? `
          <tr>
            <td class="qov-dim">${earnDays >= 0 ? '+' : ''}${earnDays}d</td>
            <td><b>ER · ${ana.earnings_estimate?.['0q']?.year_ago_eps != null ? 'next quarter' : 'next report'}</b></td>
            <td class="qov-dim">${ana.earnings_estimate?.['0q']?.avg != null ? 'est $' + ana.earnings_estimate['0q'].avg.toFixed(2) : '—'}</td>
            <td class="r qov-am">${isNaN(impMove) ? '—' : '±' + impMove.toFixed(1) + '%'}</td>
          </tr>` : ''}
          ${upcomingMacro.map(e => {
            const days = e._days;
            const lbl  = e.type || e.event || 'macro';
            const imp  = (e.importance || '').toUpperCase();
            return `<tr><td class="qov-dim">${days >= 0 ? '+' : ''}${days}d</td><td><b>${lbl}</b></td><td class="qov-dim">${imp || 'macro'}</td><td class="r qov-am">macro</td></tr>`;
          }).join('')}
          ${upcomingMacro.length === 0 && (isNaN(earnDays) || earnDays > 60 || earnDays < -7) ? `<tr><td colspan="4" class="qov-dim">No catalysts in ±30d window</td></tr>` : ''}
        </table>
      </div>
    </div>`;

  // ── ★ SECTION 5 · HISTORICAL EDGE ★ ───────────────────────────────
  // Use DATA aggregates when present, else "no source"
  const setupKnownN = !isNaN(setupN_hist) ? setupN_hist : (!isNaN(setupN_all) ? setupN_all : NaN);
  const histKpi = (lbl, primary, sub, c) =>
    `<div class="qov-kpi"><div class="qov-kpi-k">${lbl}</div><div class="qov-kpi-v ${c||''}">${primary}</div><div class="qov-kpi-sub">${sub}</div></div>`;
  const histEdgeHTML = `
    <div class="qov-note"><span class="why">⌬ HISTORICAL EDGE</span> &nbsp; the base-rate anchor. Wilson 95% LB tells you the floor of the edge, not the point estimate.</div>
    <div class="qov-pane">
      <div class="qov-pane-h">SETUP : ${(setupTxt || '').toUpperCase()} <span class="m">${T.setup_quality?.notes || 'mechanism: institutional re-add at value zone'}</span></div>
      <div class="qov-kpi-row" style="grid-template-columns:repeat(6,1fr)">
        ${histKpi('ALL REGIMES', setupWR_all != null && !isNaN(setupWR_all) ? `WR ${setupWR_all.toFixed(0)}% · n=${setupKnownN}` : '— ', !isNaN(setupKnownN) ? `LB ${setupLB_all != null ? (setupLB_all*100).toFixed(0)+'%' : '—'} · PF ${isNaN(setupPF_all) ? '—' : setupPF_all.toFixed(2)} · avg ${isNaN(setupAvgR) ? '—' : (setupAvgR>=0?'+':'')+setupAvgR.toFixed(2)+'R'}` : 'no aggregated history exposed', '')}
        ${histKpi('CURRENT REGIME', '—', regime.replace(/_/g,' ') + ' · no per-regime feed', 'am')}
        ${histKpi('5d WALK-FWD', '—', 'last 5 picks · no source', '')}
        ${histKpi('30d WALK-FWD', '—', 'last 30 days · no source', '')}
        ${histKpi('90d WALK-FWD', '—', 'edge decay watch · no source', '')}
        ${histKpi('SAMPLE TOTAL', !isNaN(setupKnownN) ? setupKnownN : '—', 'n closed trades across setup', !isNaN(setupKnownN) && setupKnownN >= 30 ? 'gn' : 'am')}
      </div>
      <div class="qov-mech">
        <div class="qov-mech-row"><span class="k">MECHANISM</span><span class="v">${
          setupTxt === 'Trend Continuation' ? 'After EMA50 reclaim, institutional flows re-add on test of rising EMA21 — PE & RS-conditional.' :
          setupTxt === 'Breakout Expansion' ? 'Squeeze + volume expansion at prior pivot signals supply absorption → markup phase.' :
          setupTxt === 'Impulse Catalyst' ? 'PEAD/UOA/gap-and-go front-runs analyst revisions on freshly-printed catalyst.' :
          setupTxt === 'Special Situation' ? 'Float rotation, insider clusters, or short-squeeze setups; idiosyncratic edge.' :
          'See setup family playbook for mechanism hypothesis.'
        }</span></div>
        <div class="qov-mech-row"><span class="k">FALSIFICATION</span><span class="v">${T.reaction_checklist && T.reaction_checklist.length ? T.reaction_checklist.filter(r => !r.checked).map(r => r.item).slice(0,2).join(' · ') || 'all checklist items currently pass' : 'Daily close below stop on volume invalidates thesis'}</span></div>
        <div class="qov-mech-row"><span class="k">SURVIVORSHIP</span><span class="v">−3pp WR haircut applied to point estimates (audit #1 mitigation). Historical n uses point-in-time S&amp;P membership for &gt;2023 only.</span></div>
      </div>
    </div>`;

  // ── ★ SECTION 6 · REGIME CONDITIONAL TABLE ★ ──────────────────────
  // We don't have per-regime breakdowns wired yet; render the schema with
  // current regime row highlighted and other rows dimmed "no data". Honest.
  const regimes = ['risk_on_trending', 'risk_on_choppy', 'risk_off_trending', 'panic'];
  const regimeTable = regimes.map(r => {
    const isCurrent = r === regime;
    const has = isCurrent && !isNaN(setupWR_all);
    const verdict = isCurrent && setupLB_all != null
      ? (setupLB_all*100 >= 50 ? '<span class="qov-mpill gn">TRADE</span>'
       : setupLB_all*100 >= 30 ? '<span class="qov-mpill am">TRADE-CAREFUL</span>'
       : '<span class="qov-mpill rd">DEFER</span>')
      : '<span class="qov-mpill" style="opacity:.5">— no data</span>';
    return `<tr ${isCurrent ? 'class="now"' : ''}>
      <td>${r.replace(/_/g,' ')}${isCurrent ? ' <span class="qov-dim">(current)</span>' : ''}</td>
      <td class="r ${has ? cls(setupWR_all, 55, 40) : 'qov-dim'}">${has ? setupWR_all.toFixed(0)+'%' : '—'}</td>
      <td class="r ${has && setupLB_all != null ? cls(setupLB_all*100, 50, 30) : 'qov-dim'}">${has && setupLB_all != null ? (setupLB_all*100).toFixed(0)+'%' : '—'}</td>
      <td class="r ${has && !isNaN(setupPF_all) ? cls(setupPF_all, 1.5, 1.0) : 'qov-dim'}">${has && !isNaN(setupPF_all) ? setupPF_all.toFixed(2) : '—'}</td>
      <td class="r ${has && !isNaN(setupAvgR) ? cls(setupAvgR, 0.5, 0) : 'qov-dim'}">${has && !isNaN(setupAvgR) ? (setupAvgR>=0?'+':'')+setupAvgR.toFixed(2) : '—'}</td>
      <td class="r qov-dim">${has ? setupKnownN : '—'}</td>
      <td>${verdict}</td>
    </tr>`;
  }).join('');

  const regimeTblHTML = `
    <div class="qov-note"><span class="why">▦ REGIME-CONDITIONAL DECOMPOSITION</span> &nbsp; same setup, different regimes — different edge. Wilson LB ≥ 30% required to enter.</div>
    <div class="qov-pane">
      <div class="qov-pane-h">SETUP × REGIME × SCORE-BAND <span class="m">${regime.replace(/_/g,' ')} highlighted</span></div>
      <table class="qov-tbl">
        <thead><tr><th>Regime</th><th class="r">WR</th><th class="r">Wilson LB</th><th class="r">PF</th><th class="r">Avg R</th><th class="r">n</th><th>Verdict</th></tr></thead>
        <tbody>${regimeTable}</tbody>
      </table>
    </div>`;

  // ── ★ SECTION 7 · PRIOR EARNINGS REACTIONS ★ ─────────────────────
  let earnTableHTML;
  if (recentEarn.length > 0) {
    const rows = recentEarn.map(e => {
      const surp = num(e.surprise_pct ?? e.surprise, 0);
      const beat = surp > 0;
      return `<tr>
        <td>${e.date || e.report_date || '—'}</td>
        <td><span class="qov-mpill ${beat ? 'gn' : 'rd'}">${beat ? 'BEAT' : 'MISS'}</span></td>
        <td class="r">${e.estimate != null ? e.estimate.toFixed(2) : '—'}</td>
        <td class="r">${e.actual != null ? e.actual.toFixed(2) : '—'}</td>
        <td class="r ${beat ? 'qov-gn' : 'qov-rd'}">${(surp >= 0 ? '+' : '') + surp.toFixed(1)}%</td>
        <td class="r ${e.pre_1d_pct >= 0 ? 'qov-gn' : 'qov-rd'}">${e.pre_1d_pct != null ? (e.pre_1d_pct>=0?'+':'')+e.pre_1d_pct.toFixed(1)+'%' : '—'}</td>
        <td class="r ${e.day_of_pct >= 0 ? 'qov-gn' : 'qov-rd'}">${e.day_of_pct != null ? (e.day_of_pct>=0?'+':'')+e.day_of_pct.toFixed(1)+'%' : '—'}</td>
        <td class="r ${e.post_5d_pct >= 0 ? 'qov-gn' : 'qov-rd'}">${e.post_5d_pct != null ? (e.post_5d_pct>=0?'+':'')+e.post_5d_pct.toFixed(1)+'%' : '—'}</td>
        <td class="r ${e.post_30d_pct >= 0 ? 'qov-gn' : 'qov-rd'}">${e.post_30d_pct != null ? (e.post_30d_pct>=0?'+':'')+e.post_30d_pct.toFixed(1)+'%' : '—'}</td>
      </tr>`;
    }).join('');
    const post5dArr = recentEarn.map(e => num(e.post_5d_pct, NaN)).filter(v => !isNaN(v));
    const med5d = post5dArr.length ? post5dArr.sort((a,b)=>a-b)[Math.floor(post5dArr.length/2)] : NaN;
    earnTableHTML = `
      <div class="qov-pane">
        <div class="qov-pane-h">LAST 4 PRINTS · POST-PRINT MOVE <span class="m">B/M flag · 1d gap · 5d · 30d drift</span></div>
        <table class="qov-tbl">
          <thead><tr><th>Date</th><th>Result</th><th class="r">Est</th><th class="r">Act</th><th class="r">Surp</th><th class="r">Pre 1d</th><th class="r">Day-of</th><th class="r">Post 5d</th><th class="r">Post 30d</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="qov-mech">
          <div class="qov-mech-row"><span class="k">VERDICT</span><span class="v"><b class="${beatCount/recentEarn.length >= 0.75 ? 'qov-gn' : 'qov-am'}">${beatCount/recentEarn.length >= 0.75 ? 'POSITIVE DRIFT' : 'MIXED'}</b> · ${beatCount}/${recentEarn.length} beats · median post-5d <b>${isNaN(med5d) ? '—' : (med5d>=0?'+':'')+med5d.toFixed(1)+'%'}</b>${!isNaN(impMove) && !isNaN(med5d) ? ` · realized 5d (${med5d.toFixed(1)}%) vs implied (${impMove.toFixed(1)}%) → ${Math.abs(med5d) > impMove ? 'drift > implied' : 'vol fair'}` : ''}</span></div>
        </div>
      </div>`;
  } else {
    earnTableHTML = `
      <div class="qov-pane">
        <div class="qov-pane-h">LAST 4 PRINTS · POST-PRINT MOVE <span class="m">no earnings_history feed wired</span></div>
        <div class="qov-dim" style="padding:12px 0;font-family:var(--qmono);font-size:11px">
          No earnings_history available for this ticker · MEDIAN_SURP / 4Q pattern in Quality lens computes from this list when populated. <br>
          Analyst rev-trend (above) and ER-in-${isNaN(earnDays) ? '—' : earnDays}d (Quality lens) cover the forward-looking surface.
        </div>
      </div>`;
  }
  const earnSectionHTML = `
    <div class="qov-note"><span class="why">⌗ PRIOR EARNINGS REACTIONS</span> &nbsp; PEAD asymmetry · does this name DRIFT after a beat, or FADE?</div>
    ${earnTableHTML}`;

  // ── ★ SECTION 8 · PEER COHORT CROSS-CHECK ★ ──────────────────────
  // Use DATA.industries to find this ticker's sector cohort
  const myIndustry = T.industry || T.sector;
  const industries = DATA.industries || [];
  const myIndRow = industries.find(i => (i.industry || '').toLowerCase() === (myIndustry || '').toLowerCase());
  // Find peers in same industry
  const allTickers = (DATA.short_term || []).concat(DATA.medium_term || []).concat(DATA.long_term || []);
  const peers = allTickers.filter(p => p && p.ticker && p.ticker !== T.ticker && (p.industry === myIndustry || p.sector === T.sector)).slice(0, 4);

  const cohortBeatRate = myIndRow ? num(myIndRow.beat_rate_pct, NaN) : NaN;
  const cohortCount = myIndRow ? num(myIndRow.count, NaN) : NaN;
  const cohortAvgScore = myIndRow ? num(myIndRow.avg_score, NaN) : NaN;
  const cohortTag = !isNaN(cohortAvgScore) ? (cohortAvgScore >= 70 ? 'HOT' : cohortAvgScore >= 55 ? 'WARM' : 'COLD') : '—';
  const cohortCls = cohortTag === 'HOT' ? 'gn' : cohortTag === 'COLD' ? 'rd' : 'am';

  const peerRows = peers.map(p => {
    const pVerd = (p.decision?.verdict || p.verdict || p.stage || 'WATCH').toUpperCase();
    const pVerdCls = pVerd === 'BUY' ? 'gn' : pVerd === 'WATCH' ? 'am' : 'rd';
    const pPerf = num(p.perf_month ?? p.perf_30d, NaN);
    return `<tr><td><b>${p.ticker}</b></td><td class="qov-dim">${(p.industry || p.sector || '').slice(0,18)}</td><td class="r ${pPerf >= 0 ? 'qov-gn' : 'qov-rd'}">${isNaN(pPerf) ? '—' : (pPerf>=0?'+':'')+pPerf.toFixed(1)+'%'}</td><td class="r"><span class="qov-mpill ${pVerdCls}">${pVerd}</span></td></tr>`;
  }).join('');

  // sector relative: my pct rank vs cohort
  const sectorPctRank = num(T.sector_pct_rank, NaN);
  const sectorRelHTML = !isNaN(sectorPctRank)
    ? `<tr><td colspan="3" class="qov-dim" style="padding-top:8px"><b>SECTOR RELATIVE</b>: ${T.ticker} at <b>${sectorPctRank.toFixed(1)}</b> percentile in industry</td><td class="r ${sectorPctRank > 80 ? 'qov-gn' : sectorPctRank > 50 ? 'qov-am' : 'qov-rd'}">${sectorPctRank > 80 ? 'TOP' : sectorPctRank > 50 ? 'UPPER' : 'LOWER'}</td></tr>`
    : '';

  const peerSectionHTML = `
    <div class="qov-note"><span class="why">◇ PEER COHORT CROSS-CHECK</span> &nbsp; how is the SECTOR doing? Single-name picks in a cold cohort underperform.</div>
    <div class="qov-grid2">
      <div class="qov-pane">
        <div class="qov-pane-h">SECTOR · ${(T.sector || '—').toUpperCase()} <span class="m">peer cohort</span></div>
        <table class="qov-tbl">
          <tr><td><b>Cohort tag</b></td><td class="r"><span class="qov-mpill ${cohortCls}">${cohortTag}</span></td></tr>
          <tr><td>Industry</td><td class="r">${myIndustry || '—'}</td></tr>
          <tr><td>Names in industry (scan)</td><td class="r">${isNaN(cohortCount) ? '—' : cohortCount}</td></tr>
          <tr><td>Cohort avg score</td><td class="r ${!isNaN(cohortAvgScore) ? (cohortAvgScore >= 65 ? 'qov-gn' : cohortAvgScore >= 50 ? 'qov-am' : 'qov-rd') : 'qov-dim'}">${isNaN(cohortAvgScore) ? '—' : cohortAvgScore.toFixed(1)}</td></tr>
          <tr><td>Cohort beat rate (45d)</td><td class="r ${cohortBeatRate >= 75 ? 'qov-gn' : cohortBeatRate >= 55 ? 'qov-am' : cohortBeatRate ? 'qov-rd' : 'qov-dim'}">${isNaN(cohortBeatRate) ? '— no source' : cohortBeatRate.toFixed(0)+'%'}</td></tr>
          <tr><td>Total scan peers</td><td class="r">${peers.length} shown of ${industries.reduce((s,i) => s + (i.count || 0), 0) || '—'}</td></tr>
        </table>
      </div>
      <div class="qov-pane">
        <div class="qov-pane-h">PEER NAMES · 30d perf <span class="m">benchmark</span></div>
        ${peers.length ? `
        <table class="qov-tbl">
          ${peerRows}
          ${sectorRelHTML}
        </table>` : `<div class="qov-dim" style="padding:12px 0;font-family:var(--qmono);font-size:11px">No peers in scan universe for this industry.</div>`}
      </div>
    </div>`;

  // ── ★ SECTION 9 · CROSS-ASSET CONTEXT ★ ──────────────────────────
  const xaHTML = `
    <div class="qov-note"><span class="why">⊠ CROSS-ASSET CONTEXT</span> &nbsp; isolated charts lie. Beta · sector ETF · macro proxies tell you if the move is the name or the regime.</div>
    <div class="qov-grid2">
      <div class="qov-pane">
        <div class="qov-pane-h">CROSS-ASSET LINK <span class="m">60d</span></div>
        <table class="qov-tbl">
          <tr><td>vs SPY (β)</td><td class="r ${beta > 1.5 ? 'qov-am' : beta > 0 ? 'qov-gn' : 'qov-dim'}">${isNaN(beta) ? '—' : 'β ' + beta.toFixed(2)}</td><td class="r qov-dim">${beta > 1.5 ? 'high beta' : beta > 0.8 ? 'market-correlated' : 'low beta'}</td></tr>
          <tr><td>Sector ETF</td><td class="r">${DATA.sector_etf?.symbol || '—'}</td><td class="r qov-dim">${DATA.sector_etf?.trend || ''}</td></tr>
          <tr><td>Sector ETF chg5d</td><td class="r ${num(DATA.sector_etf?.chg5d,0) >= 0 ? 'qov-gn' : 'qov-rd'}">${DATA.sector_etf?.chg5d != null ? fmtPct(DATA.sector_etf.chg5d) : '—'}</td><td class="r qov-dim">${DATA.sector_etf?.regime || ''}</td></tr>
          <tr><td>HYG (risk proxy)</td><td class="r qov-dim">${DATA.macro_signals?.hyg?.trend || '—'}</td><td class="r ${num(DATA.macro_signals?.hyg?.chg5d,0) >= 0 ? 'qov-gn' : 'qov-rd'}">${DATA.macro_signals?.hyg?.chg5d != null ? fmtPct(DATA.macro_signals.hyg.chg5d) : '—'}</td></tr>
          <tr><td>DXY (USD)</td><td class="r qov-dim">${DATA.macro_signals?.dxy?.trend || '—'}</td><td class="r ${num(DATA.macro_signals?.dxy?.chg5d,0) >= 0 ? 'qov-rd' : 'qov-gn'}">${DATA.macro_signals?.dxy?.chg5d != null ? fmtPct(DATA.macro_signals.dxy.chg5d) : '—'}</td></tr>
          <tr><td>GLD</td><td class="r qov-dim">${DATA.macro_signals?.gld?.trend || '—'}</td><td class="r ${num(DATA.macro_signals?.gld?.chg5d,0) >= 0 ? 'qov-gn' : 'qov-rd'}">${DATA.macro_signals?.gld?.chg5d != null ? fmtPct(DATA.macro_signals.gld.chg5d) : '—'}</td></tr>
          <tr><td>Risk signal</td><td class="r ${(DATA.macro_signals?.risk_signal === 'risk_on') ? 'qov-gn' : (DATA.macro_signals?.risk_signal === 'risk_off') ? 'qov-rd' : 'qov-am'}">${(DATA.macro_signals?.risk_signal || '—').replace(/_/g,' ')}</td><td class="r qov-dim">macro</td></tr>
        </table>
      </div>
      <div class="qov-pane">
        <div class="qov-pane-h">VOL CONE <span class="m">realized vs implied</span></div>
        <table class="qov-tbl">
          <tr><td>30d realized vol</td><td class="r">${isNaN(atrPct) ? '—' : (atrPct * Math.sqrt(252)).toFixed(0) + '%'}</td><td class="r qov-dim">ATR-derived</td></tr>
          <tr><td>Current IV (ATM)</td><td class="r">${isNaN(ivCur) ? '—' : (ivCur > 1 ? ivCur : ivCur*100).toFixed(0) + '%'}</td><td class="r qov-dim">${isNaN(ivCur) ? 'no chain' : 'live chain'}</td></tr>
          <tr><td>IV rank vs 52w</td><td class="r ${ivRank > 70 ? 'qov-am' : ''}">${isNaN(ivRank) ? '—' : ivRank.toFixed(0) + '%'}</td><td class="r qov-dim">${isNaN(ivRank) ? '' : ivRank > 70 ? 'elevated' : ivRank > 30 ? 'normal' : 'low'}</td></tr>
          <tr><td>Implied vs realized</td><td class="r ${!isNaN(ivCur) && !isNaN(atrPct) ? ((ivCur > 1 ? ivCur : ivCur*100) > atrPct * Math.sqrt(252) ? 'qov-am' : 'qov-gn') : 'qov-dim'}">${!isNaN(ivCur) && !isNaN(atrPct) ? (((ivCur > 1 ? ivCur : ivCur*100) - atrPct * Math.sqrt(252)).toFixed(0)+'pp gap') : '—'}</td><td class="r qov-dim">${!isNaN(ivCur) && !isNaN(atrPct) ? ((ivCur > 1 ? ivCur : ivCur*100) > atrPct * Math.sqrt(252) ? 'vol rich' : 'vol cheap') : ''}</td></tr>
          <tr><td>Earnings IV</td><td class="r qov-am">${(!isNaN(earnDays) && earnDays >= 0 && earnDays < 30 && !isNaN(ivRank)) ? (ivRank + 15).toFixed(0)+'%' : '—'}</td><td class="r qov-dim">${(!isNaN(earnDays) && earnDays >= 0 && earnDays < 30) ? 'event premium' : 'no event in window'}</td></tr>
          <tr><td>Back-month IV</td><td class="r">${isNaN(ivCur) ? '—' : (ivCur > 1 ? ivCur*0.85 : ivCur*85).toFixed(0)+'%'}</td><td class="r qov-dim">baseline est</td></tr>
        </table>
      </div>
    </div>`;

  // ── ★ SECTION 10 · CALIBRATION & SAMPLE SIZE ★ ───────────────────
  const calRows = [
    { claim: 'Setup WR (all-regime)', pe: setupWR_all, lb: setupLB_all != null ? setupLB_all*100 : null, n: setupKnownN },
    { claim: 'Setup WR (current regime)', pe: null, lb: null, n: null, note: 'no per-regime breakdown wired' },
    { claim: 'This-ticker prior trades', pe: null, lb: null, n: 0 },
    { claim: 'Prior earnings reactions', pe: recentEarn.length ? Math.round(beatCount/recentEarn.length*100) : null, lb: recentEarn.length ? wilsonLB(beatCount/recentEarn.length, recentEarn.length)*100 : null, n: recentEarn.length },
    { claim: 'Sector cohort beat rate 45d', pe: cohortBeatRate, lb: (!isNaN(cohortBeatRate) && !isNaN(cohortCount)) ? wilsonLB(cohortBeatRate/100, cohortCount)*100 : null, n: cohortCount },
    { claim: 'Live win rate (paper)', pe: num(kelly.live_win_rate, null), lb: null, n: null, note: 'rolling, exposed by kelly_size' },
  ];
  const calTableRows = calRows.map(r => {
    const pe = r.pe == null || isNaN(r.pe) ? '—' : r.pe.toFixed(0) + '%';
    const lb = r.lb == null || isNaN(r.lb) ? '—' : r.lb.toFixed(0) + '%';
    const nn = r.n == null || isNaN(r.n) ? '—' : r.n;
    const conf = r.n == null || isNaN(r.n) ? `<span class="qov-mpill" style="opacity:.5">${r.note || 'no source'}</span>` :
                 r.n >= 30 ? `<span class="qov-mpill gn">OK · n≥30</span>` :
                 r.n >= 10 ? `<span class="qov-mpill am">THIN · n&lt;30</span>` :
                 r.n > 0   ? `<span class="qov-mpill rd">VERY THIN · n=${r.n}</span>` :
                             `<span class="qov-mpill rd">NONE · cohort only</span>`;
    return `<tr><td>${r.claim}</td><td class="r">${pe}</td><td class="r qov-am">${lb}</td><td class="r">${nn}</td><td class="r">${conf}</td></tr>`;
  }).join('');
  const calHTML = `
    <div class="qov-note"><span class="why">∑ CALIBRATION FOR THIS TICKER</span> &nbsp; honest sample size + Wilson CI. <b>n &lt; 30 = noise</b>; rely on Wilson LB above floor, not point estimates.</div>
    <div class="qov-pane">
      <div class="qov-pane-h">EVIDENCE SAMPLE SIZE <span class="m">n &lt; 30 flagged</span></div>
      <table class="qov-tbl">
        <thead><tr><th>Claim</th><th class="r">Point estimate</th><th class="r">Wilson 95% LB</th><th class="r">n</th><th class="r">Confidence</th></tr></thead>
        <tbody>${calTableRows}</tbody>
      </table>
    </div>`;

  // ── ★ SECTION 11 · RISK PROFILE ★ ────────────────────────────────
  // R-multiples from current price
  const riskPerShare = stop && pX ? (pX - stop) : NaN;
  const rT1 = (!isNaN(riskPerShare) && t1 && pX) ? (t1 - pX) / riskPerShare : NaN;
  const rT2 = (!isNaN(riskPerShare) && t2 && pX) ? (t2 - pX) / riskPerShare : NaN;
  // hypothetical 5% sizing on $10k
  const hypUSD = 500;
  const hypShares = !isNaN(riskPerShare) && riskPerShare > 0 ? Math.floor(hypUSD / pX) : 0;
  const hypRisk = hypShares * riskPerShare;

  const riskHTML = `
    <div class="qov-note"><span class="why">⚠ RISK PROFILE</span> &nbsp; what could go wrong. Drawdown asymmetry · correlation under stress · liquidity at exit.</div>
    <div class="qov-grid2">
      <div class="qov-pane">
        <div class="qov-pane-h">PORTFOLIO IMPACT <span class="m">${kelly.suggested_shares != null ? 'live sizing' : 'hypothetical'}</span></div>
        <table class="qov-tbl">
          <tr><td>Implied % equity (Kelly-lite)</td><td class="r ${finalAlloc > 0 ? 'qov-gn' : 'qov-dim'}">${isNaN(finalAlloc) ? '—' : finalAlloc.toFixed(1)+'%'}</td><td class="r qov-dim">${finalAlloc > 0 ? 'sized' : 'gate fail'}</td></tr>
          <tr><td>Suggested shares</td><td class="r">${kelly.suggested_shares != null ? kelly.suggested_shares : '—'}</td><td class="r qov-dim">${kelly.dollar_risk != null ? '$' + kelly.dollar_risk.toFixed(0) + ' risk' : ''}</td></tr>
          <tr><td>If hypothetical 5% sizing ($10k acct)</td><td class="r">${hypShares ? '$' + (hypShares*pX).toFixed(0) : '—'}</td><td class="r qov-dim">${hypShares ? hypShares + ' shares' : ''}</td></tr>
          <tr><td>Risk to stop ($)</td><td class="r qov-rd">${isNaN(hypRisk) || !hypRisk ? '—' : '−$' + Math.abs(hypRisk).toFixed(0)}</td><td class="r qov-dim">${isNaN(stopPct) ? '—' : Math.abs(stopPct).toFixed(1)+'% adverse'}</td></tr>
          <tr><td>R-multiple at T1</td><td class="r ${rT1 >= 2 ? 'qov-gn' : 'qov-am'}">${isNaN(rT1) ? '—' : '+' + rT1.toFixed(2) + 'R'}</td><td class="r qov-dim">${isNaN(t1Pct) || isNaN(stopPct) ? '—' : t1Pct.toFixed(1)+'%/'+Math.abs(stopPct).toFixed(1)+'%'}</td></tr>
          <tr><td>R-multiple at T2</td><td class="r ${rT2 >= 3 ? 'qov-gn' : 'qov-am'}">${isNaN(rT2) ? '—' : '+' + rT2.toFixed(2) + 'R'}</td><td class="r qov-dim">${isNaN(t2Pct) || isNaN(stopPct) ? '—' : t2Pct.toFixed(1)+'%/'+Math.abs(stopPct).toFixed(1)+'%'}</td></tr>
          <tr><td>Beta-weighted exposure</td><td class="r ${beta > 1.5 ? 'qov-am' : ''}">${isNaN(beta) ? '—' : '×' + beta.toFixed(2) + ' SPY'}</td><td class="r qov-dim">${beta > 1.5 ? 'amplifies portfolio β' : ''}</td></tr>
        </table>
      </div>
      <div class="qov-pane">
        <div class="qov-pane-h">DRAWDOWN PROFILE <span class="m">forward-looking + stress</span></div>
        <table class="qov-tbl">
          <tr><td>VaR 95% (10d, empirical)</td><td class="r qov-am">${isNaN(var95) ? '—' : (var95>=0?'+':'')+var95.toFixed(1)+'%'}</td><td class="r qov-dim">${fwd.n_samples ? 'n=' + fwd.n_samples : ''}</td></tr>
          <tr><td>CVaR 97.5% (10d)</td><td class="r qov-rd">${isNaN(cvar975) ? '—' : (cvar975>=0?'+':'')+cvar975.toFixed(1)+'%'}</td><td class="r qov-dim">tail loss</td></tr>
          <tr><td>MC min terminal</td><td class="r qov-rd">${isNaN(mc.min_terminal_pct) ? '—' : (mc.min_terminal_pct>=0?'+':'')+mc.min_terminal_pct.toFixed(1)+'%'}</td><td class="r qov-dim">worst path of ${mc.n_paths || '—'}</td></tr>
          <tr><td>MC max terminal</td><td class="r qov-gn">${isNaN(mc.max_terminal_pct) ? '—' : (mc.max_terminal_pct>=0?'+':'')+mc.max_terminal_pct.toFixed(1)+'%'}</td><td class="r qov-dim">best path</td></tr>
          <tr><td>Drawdown mult</td><td class="r ${ddMult < 1 ? 'qov-am' : ''}">${isNaN(ddMult) ? '—' : ddMult.toFixed(2)+'×'}</td><td class="r qov-dim">${kelly.drawdown_pct != null ? 'live DD ' + kelly.drawdown_pct.toFixed(1)+'%' : ''}</td></tr>
          <tr><td>Liquidity at exit</td><td class="r ${advDol > 10e6 ? 'qov-gn' : advDol > 1e6 ? 'qov-am' : advDol ? 'qov-rd' : 'qov-dim'}">${isNaN(advDol) ? '—' : 'ADV ' + fmtMcap(advDol)}</td><td class="r qov-dim">${advDol > 10e6 ? 'ample' : advDol > 1e6 ? 'OK' : 'thin'}</td></tr>
        </table>
      </div>
    </div>`;

  // ── ★ SECTION 12 · PRE-FLIGHT CHECKLIST ★ ────────────────────────
  const checklist = [
    {
      n: 1, rule: 'BAP ≥ regime floor',
      detail: `${score} ${score >= regimeF ? '≥' : '&lt;'} ${regimeF}`,
      pass: score >= regimeF,
    },
    {
      n: 2, rule: 'Setup Wilson LB ≥ 30%',
      detail: setupLB_all != null ? `${(setupLB_all*100).toFixed(0)}% ${setupLB_all*100 >= 30 ? '≥' : '&lt;'} 30%` : 'no aggregated history',
      pass: setupLB_all != null && setupLB_all*100 >= 30,
      neutral: setupLB_all == null,
    },
    {
      n: 3, rule: 'R:R ≥ 3',
      detail: !isNaN(rr) && rr ? `1:${rr.toFixed(1)} ${rr >= 3 ? '≥' : '&lt;'} 3` : '—',
      pass: rr >= 3,
    },
    {
      n: 4, rule: 'Entry quality FRESH/PULLBACK',
      detail: eqRaw || '—',
      pass: ['FRESH','PULLBACK','VALID'].includes(eqRaw),
    },
    {
      n: 5, rule: 'Earnings ≥ 14d clear',
      detail: !isNaN(earnDays) ? `+${earnDays}d` : 'no earnings in window',
      pass: isNaN(earnDays) || earnDays >= 14 || earnDays < 0,
    },
    {
      n: 6, rule: 'ADV ≥ $5M',
      detail: !isNaN(advDol) ? fmtMcap(advDol) : '—',
      pass: advDol >= 5e6,
      neutral: isNaN(advDol),
    },
    {
      n: 7, rule: 'No macro overlap ±2d',
      detail: upcomingMacro.filter(e => Math.abs(e._days) <= 2).length === 0 ? 'clear ±2d' : upcomingMacro.filter(e => Math.abs(e._days) <= 2).map(e => (e.type||e.event||'').slice(0,16) + ' ' + (e._days>=0?'+':'') + e._days + 'd').join(', '),
      pass: upcomingMacro.filter(e => Math.abs(e._days) <= 2).length === 0,
    },
  ];
  const passes = checklist.filter(c => c.pass && !c.neutral).length;
  const fails  = checklist.filter(c => !c.pass && !c.neutral).length;
  const verdict7 = fails === 0 ? `<span class="qov-mpill gn">${passes}/7 PASS · GO</span>`
                  : fails <= 2 ? `<span class="qov-mpill am">${passes}/7 PASS · DEFER</span>`
                  :              `<span class="qov-mpill rd">${passes}/7 PASS · NO-TRADE</span>`;
  const checklistRows = checklist.map(c => `
    <tr>
      <td><b>${c.n}. ${c.rule}</b></td>
      <td>${c.detail}</td>
      <td class="r"><span class="qov-mpill ${c.neutral ? '' : c.pass ? 'gn' : 'rd'}">${c.neutral ? 'N/A' : c.pass ? 'PASS' : 'FAIL'}</span></td>
    </tr>`).join('');
  const checklistHTML = `
    <div class="qov-note"><span class="why">✓ PRE-FLIGHT CHECKLIST</span> &nbsp; rules-based pass/fail. Avoid emotional commits — the system is the discipline.</div>
    <div class="qov-pane">
      <div class="qov-pane-h">7-POINT PRE-FLIGHT <span class="m">all must pass to size up</span></div>
      <table class="qov-tbl">
        ${checklistRows}
        <tr style="border-top:2px solid var(--qline-2)">
          <td colspan="2"><b>RESULT</b></td>
          <td class="r">${verdict7}</td>
        </tr>
      </table>
    </div>`;

  // ── existing demote/decision banner (kept for continuity) ─────────
  const demoteBanner = isDemoted ? `
  <div style="background:linear-gradient(135deg,rgba(234,179,8,0.10),rgba(234,179,8,0.02));border:1px solid #eab308;border-left:4px solid #eab308;border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:13px;color:#fde68a;display:flex;align-items:flex-start;gap:14px">
    <div style="font-size:24px;line-height:1">⚠</div>
    <div style="flex:1;line-height:1.5">
      <div style="font-weight:700;color:#eab308;letter-spacing:.05em;text-transform:uppercase;font-size:11px;margin-bottom:6px">SYSTEM DEMOTED THIS SIGNAL — DO NOT QUICK-BUY</div>
      <div><b>${eqBad ? `Entry ${eqRaw} — chase territory` : convLbl === 'WATCH' ? 'Tail-filter demoted' : 'Demoted'}.</b> The setup is real (${setupTxt}, score ${score}), but at <b>$${pX.toFixed(2)}</b> the trade math is broken. Real R:R right now is <b style="font-family:var(--qmono);color:#eab308">${realRR != null ? realRR.toFixed(2) : '—'}:1</b> (target ≥ 3:1). Cached R:R of ${cachedRR.toFixed(1)} is the *entry-zone* math.</div>
      ${pullbackZone !== '—' ? `<div style="margin-top:6px"><b>Action:</b> alert at <span style="font-family:var(--qmono);color:#fde68a">${pullbackZone}</span> and wait.</div>` : ''}
    </div>
  </div>` : '';

  // ── final assembly ─────────────────────────────────────────────────
  body.innerHTML = `
    <div class="qov-root">
      ${demoteBanner}
      ${stripHTML}
      ${triageHTML}
      ${edgeBarHTML}
      ${lensHTML}
      ${tradeWindowHTML}
      ${histEdgeHTML}
      ${regimeTblHTML}
      ${earnSectionHTML}
      ${peerSectionHTML}
      ${xaHTML}
      ${calHTML}
      ${riskHTML}
      ${checklistHTML}
      ${(typeof T.thesis === 'string' && T.thesis) ? `<div class="qov-note" style="border-left-color:var(--cy);margin-top:14px"><span class="why" style="color:var(--cy)">THESIS</span> ${T.thesis}</div>` : (T.thesis_card && T.thesis_card.narrative ? `<div class="qov-note" style="border-left-color:var(--cy);margin-top:14px"><span class="why" style="color:var(--cy)">THESIS</span> ${T.thesis_card.narrative}</div>` : '')}
    </div>
  `;
}

export function dispose() { /* no-op */ }
