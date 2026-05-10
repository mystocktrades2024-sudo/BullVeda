// subtabs/ruleengine/rule_engine.js — extracted from elite-detail.html (renderRuleEngine 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const verdict = (T.verdict || T.decision?.verdict || '—').toString().toUpperCase();
  const score = +(T.score || 0);
  const rrRatio = +(T.rr_ratio || T.rr || 0);
  const tone = ['BUY','STRONG BUY'].includes(verdict) ? 'buy'
             : ['SELL','SHORT','AVOID'].includes(verdict) ? 'short'
             : 'watch';
  const tIcon = tone === 'buy' ? '✓' : tone === 'short' ? '✗' : '◆';

  const gate = T.gate || {};
  const gatePass = !!gate.passed;
  const gateReasons = (gate.reasons || []).slice(0, 8);

  const tech = T.tech_score, techMax = T.tech_max || 35;
  const cat  = (T.scoring_breakdown || {}).cat_score, catMax = 20;
  const rs   = (T.scoring_breakdown || {}).rs_score,  rsMax = 20;
  const sm   = T.sent_score,  smMax = T.sent_max || 15;
  const qg   = T.fund_score,  qgMax = T.fund_max || 10;
  const rawTotal  = +((T.scoring_breakdown || {}).raw_total || 0);
  const bonusTot  = +((T.scoring_breakdown || {}).bonus_total || 0);
  const finalScore = score;

  const setupFamily = T.setup_family || T.setup || '—';
  const catalystTier = T.catalyst_tier || (T.catalyst_meta || {}).tier;
  const catalystTags = T.catalyst_tags || [];
  const conviction = T.conviction_tier || (T.conviction || {}).tier || '—';
  const entryQ = T.entry_quality || T.decision_state || '—';

  const tc = T.theory_confluence || {};
  const tcStates = tc.states || {};
  const tcDir = tc.direction;
  const mc = T.methodology_checklist || {};
  const mcChecks = mc.checks || {};
  const mcPasses = mc.passes;
  const mcVerdict = mc.verdict;

  const sectorPctRank = T.sector_pct_rank;
  const sectorN = T.sector_n;
  const sectorDemoted = (T.decision || {}).sector_demotion_reason;

  const tier1 = T.tier1_signals || {};
  const tier1Sigs = tier1.signals || {};
  const tier1ActiveCt = tier1.active_count || 0;
  const tier1Points = tier1.total_points || 0;

  const macroBlock = (T.system_status || {}).macro_calendar || {};
  const earnDays = T.earn_days;
  const isEarnBlock = (earnDays != null && earnDays <= 7);

  // Helpers
  const _fmtScore = (s, max) => s != null ? `${s.toFixed ? s.toFixed(0) : s}/${max}` : `—/${max}`;
  const _pct = (s, max) => s != null && max > 0 ? (s/max*100).toFixed(0) + '%' : '—';
  const _toneFromPct = (s, max) => { if (s == null || max <= 0) return 'low'; const r = s/max; return r >= 0.7 ? 'high' : r >= 0.4 ? 'med' : 'low'; };
  const stateBadge = (state) => {
    const m = {BULLISH:'pass',MARKUP:'pass',ACCUMULATION:'pass',EARLY_IMPULSE:'pass',
               BEARISH:'fail',MARKDOWN:'fail',DISTRIBUTION:'fail',LATE_IMPULSE:'fail',CORRECTIVE:'fail',
               NEUTRAL:'warn',UNKNOWN:'info',UNAVAILABLE:'info',INVALID:'info'};
    return m[state] || 'info';
  };

  // Build narrative for verdict banner
  let narrative = '';
  if (verdict === 'BUY') narrative = `Final score ${score} qualifies as BUY · ${setupFamily} setup · R:R ${rrRatio.toFixed(1)}× · conviction ${conviction}.`;
  else if (verdict === 'WATCH') narrative = `Score ${score} below BUY threshold or gates partial. Setup recognized but not actionable until conditions tighten.`;
  else if (['SELL','SHORT'].includes(verdict)) narrative = `Score ${score} indicates sell/short bias. Bear setup confirmed.`;
  else if (verdict === 'AVOID') narrative = `Score ${score} fails one or more hard gates. Skip entirely.`;
  else narrative = `Final score ${score}.`;

  // ─── Per-Tab Consensus Matrix ───
  // Map each FD tab to a BULL/BEAR/WAIT/NA verdict + confidence + 1-line evidence
  const tabVerdicts = (() => {
    const out = [];
    const _v = (kind, conf, ev) => ({ kind, conf, ev });

    // 1. Overview — uses canonical verdict
    out.push({ tab: 'Overview', icon: '📋', ...(() => {
      const v = (verdict || '').toUpperCase();
      if (v === 'BUY' || v === 'STRONG BUY') return _v('bull', 'high', `Score ${score} · R:R ${rrRatio.toFixed(1)}× · ${setupFamily}`);
      if (v === 'WATCH' || v === 'HOLD') return _v('wait', 'med', `Score ${score} · awaiting trigger`);
      if (['SHORT','SELL','AVOID'].includes(v)) return _v('bear', 'high', `Score ${score} · ${T.bear_type || 'bearish'}`);
      return _v('na', 'low', '—');
    })() });

    // 2. Plan — same verdict + entry quality
    out.push({ tab: 'Plan', icon: '🎯', ...(() => {
      const eq = (T.entry_quality || '').toUpperCase();
      const v = (verdict || '').toUpperCase();
      if (v === 'BUY' && (eq === 'FRESH' || eq === 'PULLBACK' || eq === 'VALID')) return _v('bull', 'high', `${eq} entry · stop $${(T.stop||0).toFixed(2)}`);
      if (v === 'BUY' && eq === 'EXTENDED') return _v('wait', 'med', `EXTENDED — wait for pullback`);
      if (v === 'BUY' && eq === 'MISSED') return _v('wait', 'low', `MISSED — re-entry blocked`);
      if (['SHORT','SELL'].includes(v)) return _v('bear', 'high', `Short plan · stop ${(T.stop||0).toFixed(2)}`);
      return _v('wait', 'low', `${eq || 'no plan'} `);
    })() });

    // 3. Technicals — pillar score + EMA stack + RSI/MACD
    out.push({ tab: 'Technicals', icon: '📈', ...(() => {
      const tcr = T.tech_score || 0, tcrm = T.tech_max || 35;
      const stackBull = !!T.above_50ema && !!T.above_200sma;
      const macdBull = !!T.macd_bullish;
      const rsi = T.rsi;
      const tcRatio = tcr / tcrm;
      if (tcRatio >= 0.7 && stackBull && macdBull) return _v('bull', 'high', `${tcr.toFixed(0)}/${tcrm} · stack bull · MACD↑ · RSI ${rsi?.toFixed(0)}`);
      if (tcRatio >= 0.5 && stackBull) return _v('bull', 'med', `${tcr.toFixed(0)}/${tcrm} · stack bull`);
      if (!stackBull && tcRatio < 0.4) return _v('bear', 'high', `${tcr.toFixed(0)}/${tcrm} · below 50EMA · weak`);
      if (rsi >= 70) return _v('wait', 'med', `RSI ${rsi.toFixed(0)} overbought`);
      if (rsi <= 30) return _v('wait', 'med', `RSI ${rsi.toFixed(0)} oversold`);
      return _v('wait', 'med', `${tcr.toFixed(0)}/${tcrm} · mixed signals`);
    })() });

    // 4. Models — theory_confluence direction
    out.push({ tab: 'Models', icon: '🧠', ...(() => {
      const dir = (tcDir || '').toUpperCase();
      const bull = tc.bull_count || 0;
      const ct = (tc.eligible_theories || []).length || 3;
      if (dir === 'BULLISH') return _v('bull', bull >= 3 ? 'high' : 'med', `Confluence ${bull}/${ct} bullish · ${tcStates.wyckoff || 'NA'}`);
      if (dir === 'BEARISH') return _v('bear', 'high', `Confluence bearish · ${tcStates.wyckoff || 'NA'}`);
      return _v('wait', 'low', `${bull}/${ct} aligned · no confluence`);
    })() });

    // 5. TradingView — uses tv_rec_str
    out.push({ tab: 'TradingView', icon: '📊', ...(() => {
      const tv = (T.tv_rec_str || '').toUpperCase();
      if (tv === 'STRONG_BUY') return _v('bull', 'high', `TV consensus STRONG BUY`);
      if (tv === 'BUY') return _v('bull', 'med', `TV consensus BUY`);
      if (tv === 'HOLD' || tv === 'NEUTRAL') return _v('wait', 'med', `TV consensus HOLD`);
      if (tv === 'SELL') return _v('bear', 'med', `TV consensus SELL`);
      if (tv === 'STRONG_SELL') return _v('bear', 'high', `TV consensus STRONG SELL`);
      return _v('na', 'low', 'no TV rating');
    })() });

    // 6. SMC — smc_direction + bos_choch
    out.push({ tab: 'SMC', icon: '🏦', ...(() => {
      const smc = T.smc || {};
      const dir = (smc.smc_direction || '').toLowerCase();
      const bc = smc.bos_choch || {};
      if (dir === 'bullish' || bc.bos_bullish) return _v('bull', 'high', `${bc.last_structure || 'HH/HL'} · ${bc.bos_bullish ? 'BOS bull' : 'markup'}`);
      if (dir === 'bearish' || bc.bos_bearish) return _v('bear', 'high', `${bc.last_structure || 'LH/LL'} · BOS bear ${bc.bos_bars_ago != null ? bc.bos_bars_ago + 'b ago' : ''}`);
      return _v('wait', 'low', 'no clear structure');
    })() });

    // 7. Fundamentals — long_term_score + Zacks VGM
    out.push({ tab: 'Fundamentals', icon: '💰', ...(() => {
      const lt = T.long_term_score;
      const vgm = (T.zacks_grades || {}).vgm;
      const upPct = (T.analyst_full || T.analyst || {}).upside_pct;
      if (lt >= 80 || vgm === 'A') return _v('bull', 'high', `Score ${lt?.toFixed(0)} · VGM ${vgm || 'B+'} · ${upPct ? `+${upPct.toFixed(1)}%` : 'strong'}`);
      if (lt >= 60 || vgm === 'B') return _v('wait', 'med', `Score ${lt?.toFixed(0)} · VGM ${vgm}`);
      if (lt < 50 || vgm === 'F') return _v('bear', 'med', `Score ${lt?.toFixed(0)} · VGM ${vgm} · weak quality`);
      return _v('wait', 'low', `Score ${lt?.toFixed(0)}`);
    })() });

    // 8. Sentiment — composite + insider net
    out.push({ tab: 'Sentiment', icon: '💬', ...(() => {
      const sentScore = (T.sentiment || {}).score;
      const sentMax = (T.sentiment || {}).max || 10;
      const ins = T.insider_full || T.insider || {};
      const netIns = ins.net_signal != null ? ins.net_signal : ((ins.buys || 0) - (ins.sells || 0));
      const newsMom = (T.news_sentiment_score || {}).momentum;
      if (sentScore >= 7 && (newsMom === 'bullish' || netIns > 2)) return _v('bull', 'high', `Sent ${sentScore}/10 · news ${newsMom || 'bull'} · ins +${netIns}`);
      if (sentScore <= 3 || newsMom === 'bearish' || netIns < -3) return _v('bear', 'med', `Sent ${sentScore}/10 · news ${newsMom || 'weak'} · ins ${netIns}`);
      return _v('wait', 'low', `Sent ${sentScore}/${sentMax}`);
    })() });

    // 9. Options — options_kpis.verdict
    out.push({ tab: 'Options', icon: '📞', ...(() => {
      const k = T.options_kpis || {};
      const v = (k.verdict || {}).verdict || k.verdict;
      const conf = ((k.verdict || {}).confidence || '').toUpperCase();
      const vs = (typeof v === 'string' ? v : '').toUpperCase();
      const confKey = conf === 'HIGH' ? 'high' : conf === 'MED' ? 'med' : 'low';
      if (vs === 'BULLISH') return _v('bull', confKey, `IV ${k.iv_rank?.toFixed(0) || '?'} · UOA ${k.uoa_calls || 0}c/${k.uoa_puts || 0}p`);
      if (vs === 'BEARISH') return _v('bear', confKey, `Skew bear · UOA ${k.uoa_calls || 0}c/${k.uoa_puts || 0}p`);
      if (vs === 'MIXED') return _v('wait', confKey, `Mixed flow`);
      return _v('na', 'low', 'no options data');
    })() });

    // 10. News — news momentum + article count
    out.push({ tab: 'News', icon: '📰', ...(() => {
      const polynews = T.news_articles || T.polygon_news || [];
      const polyscore = T.news_sentiment_score || T.polygon_news_score || {};
      const ct = polynews.length;
      if (ct === 0) return _v('na', 'low', 'no recent news');
      const articleSent = polynews.map(n => {
        const i = (n.insights || []).find(x => (x.ticker || '').toUpperCase() === T.ticker);
        return i?.sentiment || n.sentiment || 'neutral';
      });
      const bull = articleSent.filter(s => s === 'positive').length;
      const bear = articleSent.filter(s => s === 'negative').length;
      const mom = (typeof polyscore === 'object' ? polyscore.momentum : null) || 'neutral';
      if (mom === 'bullish' || bull > bear * 1.5) return _v('bull', bull >= 5 ? 'high' : 'med', `${bull}↑ ${bear}↓ · ${mom}`);
      if (mom === 'bearish' || bear > bull * 1.5) return _v('bear', 'med', `${bull}↑ ${bear}↓ · ${mom}`);
      return _v('wait', 'low', `${bull}↑ ${bear}↓ neutral · ${ct} articles`);
    })() });

    // 11. Insider — net flow + C-suite
    out.push({ tab: 'Insider', icon: '🥷', ...(() => {
      const ins = T.insider_full || T.insider || {};
      const netIns = ins.net_signal != null ? ins.net_signal : ((ins.buys || 0) - (ins.sells || 0));
      const ceoBuy = !!ins.ceo_buy;
      const cfoBuy = !!ins.cfo_buy;
      if ((netIns >= 3 && ceoBuy) || (netIns >= 5 && cfoBuy)) return _v('bull', 'high', `Net +${netIns} · CEO ${ceoBuy ? '✓' : '·'} · CFO ${cfoBuy ? '✓' : '·'}`);
      if (netIns >= 2) return _v('bull', 'med', `Net +${netIns} (${ins.buys || 0}↑/${ins.sells || 0}↓)`);
      if (netIns <= -3) return _v('bear', 'med', `Net ${netIns} (${ins.buys || 0}↑/${ins.sells || 0}↓)`);
      return _v('wait', 'low', `Net ${netIns >= 0 ? '+' : ''}${netIns}`);
    })() });

    // 12. Institution — composite of Zacks + inst_trend + smart-money signals
    out.push({ tab: 'Institution', icon: '🏛', ...(() => {
      const inst = T.inst_trend || {};
      const trend = (inst.inst_trend || '').toLowerCase();
      const instPct = inst.inst_pct;
      const zr = T.zacks_rank1;
      const zsell = T.zacks_sell;
      if (zr && (trend === 'increasing' || instPct >= 70)) return _v('bull', 'high', `Zacks #1 · inst ${trend} · ${instPct?.toFixed(0)}% own`);
      if (zr) return _v('bull', 'med', `Zacks Rank #1 · inst ${trend || 'stable'}`);
      if (zsell || trend === 'decreasing') return _v('bear', 'med', `${zsell ? 'Zacks #5' : 'inst outflow'} · ${instPct?.toFixed(0)}% own`);
      if (instPct >= 50) return _v('wait', 'med', `Inst ${instPct?.toFixed(0)}% · ${trend || 'stable'}`);
      return _v('wait', 'low', `${trend || 'stable'} · ${instPct ? instPct.toFixed(0) + '%' : 'limited data'}`);
    })() });

    return out;
  })();

  // Tally verdicts for the agreement summary
  const tally = { bull: 0, bear: 0, wait: 0, na: 0 };
  tabVerdicts.forEach(t => { tally[t.kind] = (tally[t.kind] || 0) + 1; });
  const totalActive = tabVerdicts.length - tally.na;
  const bullPct = totalActive > 0 ? (tally.bull / totalActive * 100) : 0;
  const bearPct = totalActive > 0 ? (tally.bear / totalActive * 100) : 0;

  // ── D-9: Concordance score — "X of N tabs agree on direction" ──
  const dominantKind = tally.bull > tally.bear && tally.bull > tally.wait ? 'bull'
                     : tally.bear > tally.bull && tally.bear > tally.wait ? 'bear'
                     : tally.wait >= tally.bull && tally.wait >= tally.bear ? 'wait'
                     : 'mixed';
  const dominantCount = dominantKind === 'mixed' ? Math.max(tally.bull, tally.bear, tally.wait) : tally[dominantKind];
  const concordancePct = totalActive > 0 ? Math.round(dominantCount / totalActive * 100) : 0;
  const concordanceLabel = concordancePct >= 80 ? 'UNANIMOUS' : concordancePct >= 65 ? 'STRONG' : concordancePct >= 50 ? 'MIXED' : 'DIVIDED';
  const concordanceTone = concordancePct >= 65 ? (dominantKind === 'bull' ? 'pass' : dominantKind === 'bear' ? 'fail' : 'warn')
                        : concordancePct >= 50 ? 'warn' : 'fail';
  const concordanceNarr = concordancePct >= 80 ? `All ${dominantCount} active lenses agree — strong directional confidence`
                        : concordancePct >= 65 ? `${dominantCount} of ${totalActive} lenses agree — solid signal, follow with confidence`
                        : concordancePct >= 50 ? `${dominantCount} of ${totalActive} lenses agree — partial consensus, manage size`
                        : `Lenses split — wait for clearer alignment before sizing up`;

  // Counterfactuals — what would change verdict?
  const counters = [];
  const buyMin = (T.regime || {}).buy_min_score || 70;
  const watchMin = 60;
  if (verdict === 'WATCH' && score < buyMin) counters.push(`Score gap to BUY: <b>+${buyMin - score} pts</b> needed (currently ${score}, BUY requires ≥${buyMin})`);
  if (entryQ === 'MISSED' || entryQ === 'EXTENDED') counters.push(`Entry quality <b>${entryQ}</b> — pullback to fresh entry zone would re-enable entry`);
  if (rrRatio > 0 && rrRatio < 3) counters.push(`R:R ${rrRatio.toFixed(1)}× below 3.0 minimum — needs target raise or stop tightening`);
  if (sectorDemoted) counters.push(`Sector ranking demoted: <b>${sectorDemoted}</b>`);
  if (isEarnBlock) counters.push(`Earnings in ${earnDays}d — soft gate; will lift after report`);
  if (mcPasses != null && mcPasses < 4) counters.push(`Methodology checklist ${mcPasses}/5 — need at least 4 for STRONG verdict`);

  $('ruleEngineBody').innerHTML = `
    <!-- VERDICT BANNER -->
    <div class="re-verdict ${tone}">
      <div class="re-v-icon">${tIcon}</div>
      <div class="re-v-mid">
        <div class="tag">FINAL VERDICT</div>
        <div class="h">${verdict}</div>
        <div class="narr">${narrative}</div>
      </div>
      <div class="re-v-r">
        <div class="v ${score >= buyMin ? 'pass' : score >= watchMin ? 'warn' : 'fail'}">${score}</div>
        <div class="lbl">Final Score</div>
      </div>
    </div>

    <!-- D-9: CONCORDANCE BANNER — single-number agreement score -->
    <div class="re-concord ${concordanceTone}">
      <div class="re-concord-l">
        <div class="lbl">TAB AGREEMENT</div>
        <div class="v">${concordancePct}%</div>
      </div>
      <div class="re-concord-mid">
        <div class="state">${concordanceLabel} ${dominantKind === 'bull' ? 'BULL' : dominantKind === 'bear' ? 'BEAR' : dominantKind === 'wait' ? 'WAIT' : 'MIXED'} CONSENSUS</div>
        <div class="narr">${concordanceNarr}</div>
        <div class="bar"><div class="seg bull" style="flex:${tally.bull}"></div><div class="seg bear" style="flex:${tally.bear}"></div><div class="seg wait" style="flex:${tally.wait}"></div><div class="seg na" style="flex:${tally.na}"></div></div>
      </div>
      <div class="re-concord-r">
        <span class="re-tag bull">${tally.bull} BULL</span>
        <span class="re-tag bear">${tally.bear} BEAR</span>
        <span class="re-tag wait">${tally.wait} WAIT</span>
        <span class="re-tag na">${tally.na} N/A</span>
      </div>
    </div>

    <!-- PER-TAB CONSENSUS MATRIX -->
    <div class="re-consensus">
      <div class="re-consensus-h">
        <span style="font-size:14px">📊</span>
        PER-TAB CONSENSUS — verdict from each analysis lens
        <span class="meta">${tally.bull} bull · ${tally.bear} bear · ${tally.wait} wait · ${tally.na} no-data</span>
      </div>
      <div class="re-consensus-grid">
        ${tabVerdicts.map(t => {
          const pillTxt = t.kind === 'bull' ? 'BUY' : t.kind === 'bear' ? 'SELL' : t.kind === 'wait' ? 'WAIT' : 'N/A';
          const confDot = t.conf === 'high' ? '●●●' : t.conf === 'med' ? '●●○' : '●○○';
          return `<div class="re-tab-row ${t.kind}">
            <span class="ico">${t.icon}</span>
            <span class="name">${t.tab}</span>
            <span class="pill ${t.kind}">${pillTxt}</span>
            <span class="ev" title="${t.ev || ''}">${t.ev || '—'} · <span style="opacity:.6;font-family:var(--mono)">${confDot}</span></span>
          </div>`;
        }).join('')}
      </div>
      <div class="re-agreement">
        <div class="re-agree-tile bull">
          <div class="lbl">Bullish Tabs</div>
          <div class="v bull">${tally.bull}</div>
          <div class="sub">${bullPct.toFixed(0)}% of ${totalActive} active</div>
        </div>
        <div class="re-agree-tile wait">
          <div class="lbl">Waiting Tabs</div>
          <div class="v wait">${tally.wait}</div>
          <div class="sub">no clear edge</div>
        </div>
        <div class="re-agree-tile bear">
          <div class="lbl">Bearish Tabs</div>
          <div class="v bear">${tally.bear}</div>
          <div class="sub">${bearPct.toFixed(0)}% of ${totalActive} active</div>
        </div>
      </div>
    </div>

    <!-- PIPELINE -->
    <div class="re-pipeline">

      <!-- STAGE 1: Universe + price/vol filter -->
      <div class="re-stage pass">
        <div class="re-stage-h">
          <span class="re-stage-num">1</span>
          <span class="re-stage-title">Universe Inclusion</span>
          <span class="re-stage-pill pass">QUALIFIED</span>
        </div>
        <div class="re-stage-body">
          ${T.ticker} passed price ($${(T.price||0).toFixed(2)}), liquidity, and S&P 500 / Russell 1000 / custom watchlist filters. ${T.zacks_rank1 ? '<b>Zacks Rank #1</b> — guaranteed inclusion.' : ''}
        </div>
      </div>

      <!-- STAGE 2: Pre-trade gate -->
      <div class="re-stage ${gatePass ? 'pass' : 'fail'}">
        <div class="re-stage-h">
          <span class="re-stage-num">2</span>
          <span class="re-stage-title">Pre-trade Gate</span>
          <span class="re-stage-pill ${gatePass ? 'pass' : 'fail'}">${gatePass ? 'PASSED' : 'KILLED'}</span>
        </div>
        <div class="re-stage-body">
          ${gatePass
            ? `All hard gates cleared (liquidity · earnings blackout · regime · entry quality).`
            : `Gate failed with ${gateReasons.length} reason${gateReasons.length===1?'':'s'}:`}
          ${gateReasons.length ? `<div class="re-stage-checks">${gateReasons.map(r => `
            <div class="re-check ${String(r).startsWith('HARD') ? 'fail' : 'warn'}">
              <span class="mark">${String(r).startsWith('HARD') ? '✗' : '⚠'}</span>
              <span class="name">${r}</span>
              <span class="val"></span>
            </div>`).join('')}</div>` : ''}
        </div>
      </div>

      <!-- STAGE 3: 5-Pillar Scoring -->
      <div class="re-stage info">
        <div class="re-stage-h">
          <span class="re-stage-num">3</span>
          <span class="re-stage-title">5-Pillar Scoring</span>
          <span class="re-stage-pill info">${rawTotal.toFixed(0)}/100 raw</span>
        </div>
        <div class="re-stage-body">
          Each pillar scored independently · regime weights applied · setup-family shifts · bonus cap ±5.
          <div class="re-pillars">
            <div class="re-pillar ${_toneFromPct(tech, techMax)}"><div class="lbl">Tech</div><div class="v ${tech >= techMax*0.7 ? 'pass' : tech >= techMax*0.4 ? 'warn' : 'fail'}">${_fmtScore(tech, techMax)}</div><div class="frac">${_pct(tech, techMax)}</div></div>
            <div class="re-pillar ${_toneFromPct(cat, catMax)}"><div class="lbl">Catalyst</div><div class="v ${cat >= catMax*0.7 ? 'pass' : cat >= catMax*0.4 ? 'warn' : 'fail'}">${_fmtScore(cat, catMax)}</div><div class="frac">${_pct(cat, catMax)}</div></div>
            <div class="re-pillar ${_toneFromPct(rs, rsMax)}"><div class="lbl">RS+Sector</div><div class="v ${rs >= rsMax*0.7 ? 'pass' : rs >= rsMax*0.4 ? 'warn' : 'fail'}">${_fmtScore(rs, rsMax)}</div><div class="frac">${_pct(rs, rsMax)}</div></div>
            <div class="re-pillar ${_toneFromPct(sm, smMax)}"><div class="lbl">Smart Money</div><div class="v ${sm >= smMax*0.7 ? 'pass' : sm >= smMax*0.4 ? 'warn' : 'fail'}">${_fmtScore(sm, smMax)}</div><div class="frac">${_pct(sm, smMax)}</div></div>
            <div class="re-pillar ${_toneFromPct(qg, qgMax)}"><div class="lbl">Quality</div><div class="v ${qg >= qgMax*0.7 ? 'pass' : qg >= qgMax*0.4 ? 'warn' : 'fail'}">${_fmtScore(qg, qgMax)}</div><div class="frac">${_pct(qg, qgMax)}</div></div>
          </div>
          <div class="re-stage-checks" style="margin-top:8px">
            <div class="re-check"><span class="mark">∑</span><span class="name">Raw pillar total</span><span class="val">${rawTotal.toFixed(1)}</span></div>
            <div class="re-check"><span class="mark">+</span><span class="name">Bonuses (Elliott Wave, squeeze breakout, weekly bonus)</span><span class="val">${bonusTot >= 0 ? '+' : ''}${bonusTot.toFixed(1)}</span></div>
          </div>
        </div>
      </div>

      <!-- STAGE 4: Setup classification -->
      <div class="re-stage ${setupFamily !== '—' ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">4</span>
          <span class="re-stage-title">Setup Classification</span>
          <span class="re-stage-pill ${catalystTier === 1 ? 'pass' : catalystTier === 2 ? 'warn' : 'info'}">T${catalystTier || '?'}</span>
        </div>
        <div class="re-stage-body">
          Family: <b>${setupFamily}</b> · Catalyst tier <b>T${catalystTier || '?'}</b> · Entry quality <b>${entryQ}</b>.
          ${catalystTags.length ? `<div class="re-stage-checks">${catalystTags.slice(0,5).map(c => `
            <div class="re-check pass"><span class="mark">⚡</span><span class="name">${c}</span><span class="val"></span></div>`).join('')}</div>` : ''}
        </div>
      </div>

      <!-- STAGE 5: Theory confluence + methodology -->
      <div class="re-stage ${tcDir === 'BULLISH' ? 'pass' : tcDir === 'BEARISH' ? 'fail' : 'warn'}">
        <div class="re-stage-h">
          <span class="re-stage-num">5</span>
          <span class="re-stage-title">Theory &amp; Methodology Check</span>
          <span class="re-stage-pill ${tcDir === 'BULLISH' ? 'pass' : tcDir === 'BEARISH' ? 'fail' : 'warn'}">${tcDir || 'NEUTRAL'} · ${mcPasses != null ? mcPasses : '—'}/5</span>
        </div>
        <div class="re-stage-body">
          Dow / Wyckoff / Elliott / Gann states + 5-check methodology sanity.
          <div class="re-stage-checks" style="margin-top:8px">
            ${['dow','wyckoff','elliott','gann'].map(k => {
              const s = tcStates[k] || 'UNKNOWN';
              const cls = stateBadge(s);
              return `<div class="re-check ${cls === 'pass' || cls === 'fail' || cls === 'warn' ? cls : 'info'}">
                <span class="mark">${cls === 'pass' ? '✓' : cls === 'fail' ? '✗' : '·'}</span>
                <span class="name">${k.toUpperCase()}</span>
                <span class="val">${s}</span>
              </div>`;
            }).join('')}
            ${Object.entries(mcChecks).slice(0, 5).map(([key, v]) => {
              const passed = (v && (v.pass === true || v === true));
              return `<div class="re-check ${passed ? 'pass' : 'fail'}">
                <span class="mark">${passed ? '✓' : '✗'}</span>
                <span class="name">${key.replace(/_/g, ' ')}</span>
                <span class="val">${typeof v === 'object' ? (v.reason || '').slice(0, 50) : ''}</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>

      <!-- STAGE 6: Sector ranking -->
      <div class="re-stage ${sectorDemoted ? 'fail' : sectorPctRank != null ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">6</span>
          <span class="re-stage-title">Cross-Sectional Sector Ranking</span>
          <span class="re-stage-pill ${sectorDemoted ? 'fail' : sectorPctRank != null ? 'pass' : 'info'}">${sectorDemoted ? 'DEMOTED' : sectorPctRank != null ? `${sectorPctRank.toFixed(0)}th %ile` : 'SKIPPED'}</span>
        </div>
        <div class="re-stage-body">
          ${sectorPctRank != null
            ? `Ranked <b>${sectorPctRank.toFixed(0)}th percentile</b> within <b>${T.sector || 'sector'}</b> (${sectorN || '?'} candidates). ${sectorDemoted ? `<br><span style="color:var(--fail)">${sectorDemoted}</span>` : 'Top decile of sector — relative-strength selection.'}`
            : 'Insufficient sector candidates (<3) — ranking skipped, no demotion possible.'}
        </div>
      </div>

      <!-- STAGE 7: Tier 1 strategy signals -->
      <div class="re-stage ${tier1ActiveCt > 0 ? 'pass' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">7</span>
          <span class="re-stage-title">Tier 1 Strategy Signals</span>
          <span class="re-stage-pill ${tier1Points > 5 ? 'pass' : tier1Points > 0 ? 'warn' : tier1Points < 0 ? 'fail' : 'info'}">${tier1ActiveCt} active · ${tier1Points >= 0 ? '+' : ''}${tier1Points} pts</span>
        </div>
        <div class="re-stage-body">
          6 additive detectors: Insider Cluster · NR7 · Vol Dry-Up · OBV Div · Mean Reversion · Beat&amp;Raise. <em>Currently informational (apply_to_score=false)</em>.
          ${tier1ActiveCt > 0 ? `<div class="re-stage-checks">${Object.entries(tier1Sigs).filter(([k,v]) => v && v.detected).slice(0, 6).map(([k, v]) => `
            <div class="re-check ${v.points > 0 ? 'pass' : v.points < 0 ? 'fail' : 'warn'}">
              <span class="mark">${v.points > 0 ? '+' : v.points < 0 ? '−' : '·'}</span>
              <span class="name">${k.replace(/_/g, ' ')}</span>
              <span class="val">${v.points >= 0 ? '+' : ''}${v.points} · ${(v.narrative || '').slice(0, 60)}</span>
            </div>`).join('')}</div>` : '<div style="color:var(--ink-1);font-style:italic;margin-top:6px">No detectors fired — not unusual for non-catalyst setups.</div>'}
        </div>
      </div>

      <!-- STAGE 8: Conviction tier + sizing -->
      <div class="re-stage ${conviction === 'T1' ? 'pass' : conviction === 'T2' ? 'warn' : 'info'}">
        <div class="re-stage-h">
          <span class="re-stage-num">8</span>
          <span class="re-stage-title">Conviction Tier &amp; Sizing</span>
          <span class="re-stage-pill ${conviction === 'T1' ? 'pass' : conviction === 'T2' ? 'warn' : 'info'}">${conviction}</span>
        </div>
        <div class="re-stage-body">
          ${conviction === 'T1' ? '<b>Full size (T1)</b> — score ≥88, RS ≥85, R:R ≥3.5, T1 catalyst, entry FRESH/PULLBACK.'
            : conviction === 'T2' ? '<b>Half size (T2)</b> — score ≥78, RS ≥75, R:R ≥3.0, T1-T2 catalyst.'
            : conviction === 'T3' ? '<b>Quarter size (T3)</b> — minimum bar (score ≥70, R:R ≥3.0).'
            : conviction === 'WATCH' ? '<b>WATCH</b> — score 60–69, no capital allocated yet.'
            : 'Conviction tier not assigned (typically because gate failed).'}
          <div class="re-stage-checks" style="margin-top:8px">
            <div class="re-check info"><span class="mark">$</span><span class="name">Suggested allocation</span><span class="val">${T.alloc_pct ? T.alloc_pct.toFixed(1) + '%' : '—'}</span></div>
            <div class="re-check info"><span class="mark">∽</span><span class="name">Sizing multiplier</span><span class="val">${T.sizing_multiplier ? T.sizing_multiplier.toFixed(2) + '×' : '—'}</span></div>
            <div class="re-check info"><span class="mark">📊</span><span class="name">Half-Kelly</span><span class="val">${(T.kelly_size || {}).half_kelly_pct ? (T.kelly_size.half_kelly_pct).toFixed(1) + '%' : '—'}</span></div>
          </div>
        </div>
      </div>

      <!-- STAGE 9: Macro context -->
      ${macroBlock.blackout_today ? `
      <div class="re-stage warn">
        <div class="re-stage-h">
          <span class="re-stage-num">9</span>
          <span class="re-stage-title">Macro Calendar Override</span>
          <span class="re-stage-pill warn">ADVISORY</span>
        </div>
        <div class="re-stage-body">
          <b>${macroBlock.blackout_reason || 'Macro event today'}</b> — soft advisory active. New entries should be cautious; gate is informational unless <code>gates.macro_blackout_hard=true</code>.
        </div>
      </div>` : ''}

      <!-- STAGE 10: Final Verdict -->
      <div class="re-stage ${tone === 'buy' ? 'pass' : tone === 'short' ? 'fail' : 'warn'}">
        <div class="re-stage-h">
          <span class="re-stage-num">${macroBlock.blackout_today ? '10' : '9'}</span>
          <span class="re-stage-title">Final Verdict</span>
          <span class="re-stage-pill ${tone === 'buy' ? 'pass' : tone === 'short' ? 'fail' : 'warn'}">${verdict}</span>
        </div>
        <div class="re-stage-body">
          ${narrative}
          ${(typeof T.thesis === 'string' && T.thesis) ? `<div style="margin-top:8px;padding:8px 10px;background:var(--bg-2);border-radius:4px;font-size:11.5px;color:var(--ink-1);font-style:italic">${T.thesis.slice(0, 280)}</div>` : ''}
        </div>
      </div>

    </div><!-- /.re-pipeline -->

    <!-- COUNTERFACTUALS — what would change verdict -->
    ${counters.length ? `
    <div class="re-counter">
      <div class="re-counter-h">⤷ WHAT WOULD CHANGE THE VERDICT</div>
      <ul>${counters.map(c => `<li>${c}</li>`).join('')}</ul>
    </div>` : ''}`;
}

export function dispose() { /* no-op */ }
