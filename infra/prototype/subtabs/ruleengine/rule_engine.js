// subtabs/ruleengine/rule_engine.js — Why-this-is-X · Rule Engine sub-tab.
// Thin orchestrator. Sub-modules:
//
//   helpers.js        — getT, fmtScore, pct, toneFromPct, stateBadge
//   tab_consensus.js  — buildTabVerdicts(T) → 12-tab BULL/BEAR/WAIT/NA verdicts
//   pipeline.js       — buildPipeline(T, ctx) → 10-stage pipeline HTML

import { getT } from './helpers.js';
import { buildTabVerdicts } from './tab_consensus.js';
import { buildPipeline }    from './pipeline.js';

export function render() {
  const T = getT();
  if (!T) return;

  const verdict  = (T.verdict || T.decision?.verdict || '—').toString().toUpperCase();
  const score    = +(T.score || 0);
  const rrRatio  = +(T.rr_ratio || T.rr || 0);
  const tone     = ['BUY','STRONG BUY'].includes(verdict)   ? 'buy'
                 : ['SELL','SHORT','AVOID'].includes(verdict) ? 'short'
                 : 'watch';
  const tIcon    = tone === 'buy' ? '✓' : tone === 'short' ? '✗' : '◆';

  const gate     = T.gate || {};
  const gatePass = !!gate.passed;
  const gateReasons = (gate.reasons || []).slice(0, 8);

  const tech    = T.tech_score, techMax = T.tech_max || 35;
  const cat     = (T.scoring_breakdown || {}).cat_score, catMax = 20;
  const rs      = (T.scoring_breakdown || {}).rs_score,  rsMax  = 20;
  const sm      = T.sent_score, smMax = T.sent_max || 15;
  const qg      = T.fund_score, qgMax = T.fund_max || 10;
  const rawTotal = +((T.scoring_breakdown || {}).raw_total  || 0);
  const bonusTot = +((T.scoring_breakdown || {}).bonus_total || 0);

  const setupFamily  = T.setup_family || T.setup || '—';
  const catalystTier = T.catalyst_tier || (T.catalyst_meta || {}).tier;
  const catalystTags = T.catalyst_tags || [];
  const conviction   = T.conviction_tier || (T.conviction || {}).tier || '—';
  const entryQ       = T.entry_quality || T.decision_state || '—';

  const tc       = T.theory_confluence || {};
  const tcStates = tc.states || {};
  const tcDir    = tc.direction;
  const mc       = T.methodology_checklist || {};
  const mcChecks = mc.checks || {};
  const mcPasses = mc.passes;

  const sectorPctRank = T.sector_pct_rank;
  const sectorN       = T.sector_n;
  const sectorDemoted = (T.decision || {}).sector_demotion_reason;

  const tier1         = T.tier1_signals || {};
  const tier1Sigs     = tier1.signals || {};
  const tier1ActiveCt = tier1.active_count || 0;
  const tier1Points   = tier1.total_points || 0;

  const macroBlock = (T.system_status || {}).macro_calendar || {};
  const earnDays   = T.earn_days;
  const isEarnBlock = (earnDays != null && earnDays <= 7);

  // Verdict banner narrative
  let narrative = '';
  if      (verdict === 'BUY')                       narrative = `Final score ${score} qualifies as BUY · ${setupFamily} setup · R:R ${rrRatio.toFixed(1)}× · conviction ${conviction}.`;
  else if (verdict === 'WATCH')                     narrative = `Score ${score} below BUY threshold or gates partial. Setup recognized but not actionable until conditions tighten.`;
  else if (['SELL','SHORT'].includes(verdict))      narrative = `Score ${score} indicates sell/short bias. Bear setup confirmed.`;
  else if (verdict === 'AVOID')                     narrative = `Score ${score} fails one or more hard gates. Skip entirely.`;
  else                                              narrative = `Final score ${score}.`;

  // Per-Tab Consensus + tally
  const tabVerdicts = buildTabVerdicts(T);
  const tally = { bull: 0, bear: 0, wait: 0, na: 0 };
  tabVerdicts.forEach(t => { tally[t.kind] = (tally[t.kind] || 0) + 1; });
  const totalActive = tabVerdicts.length - tally.na;
  const bullPct = totalActive > 0 ? (tally.bull / totalActive * 100) : 0;
  const bearPct = totalActive > 0 ? (tally.bear / totalActive * 100) : 0;

  // D-9: Concordance score — "X of N tabs agree on direction"
  const dominantKind = tally.bull > tally.bear && tally.bull > tally.wait ? 'bull'
                     : tally.bear > tally.bull && tally.bear > tally.wait ? 'bear'
                     : tally.wait >= tally.bull && tally.wait >= tally.bear ? 'wait'
                     : 'mixed';
  const dominantCount = dominantKind === 'mixed' ? Math.max(tally.bull, tally.bear, tally.wait) : tally[dominantKind];
  const concordancePct   = totalActive > 0 ? Math.round(dominantCount / totalActive * 100) : 0;
  const concordanceLabel = concordancePct >= 80 ? 'UNANIMOUS' : concordancePct >= 65 ? 'STRONG' : concordancePct >= 50 ? 'MIXED' : 'DIVIDED';
  const concordanceTone  = concordancePct >= 65 ? (dominantKind === 'bull' ? 'pass' : dominantKind === 'bear' ? 'fail' : 'warn')
                         : concordancePct >= 50 ? 'warn' : 'fail';
  const concordanceNarr  = concordancePct >= 80 ? `All ${dominantCount} active lenses agree — strong directional confidence`
                         : concordancePct >= 65 ? `${dominantCount} of ${totalActive} lenses agree — solid signal, follow with confidence`
                         : concordancePct >= 50 ? `${dominantCount} of ${totalActive} lenses agree — partial consensus, manage size`
                         : `Lenses split — wait for clearer alignment before sizing up`;

  // Counterfactuals — what would change verdict?
  const counters = [];
  const buyMin   = (T.regime || {}).buy_min_score || 70;
  const watchMin = 60;
  if (verdict === 'WATCH' && score < buyMin)    counters.push(`Score gap to BUY: <b>+${buyMin - score} pts</b> needed (currently ${score}, BUY requires ≥${buyMin})`);
  if (entryQ === 'MISSED' || entryQ === 'EXTENDED') counters.push(`Entry quality <b>${entryQ}</b> — pullback to fresh entry zone would re-enable entry`);
  if (rrRatio > 0 && rrRatio < 3)                counters.push(`R:R ${rrRatio.toFixed(1)}× below 3.0 minimum — needs target raise or stop tightening`);
  if (sectorDemoted)                              counters.push(`Sector ranking demoted: <b>${sectorDemoted}</b>`);
  if (isEarnBlock)                                counters.push(`Earnings in ${earnDays}d — soft gate; will lift after report`);
  if (mcPasses != null && mcPasses < 4)           counters.push(`Methodology checklist ${mcPasses}/5 — need at least 4 for STRONG verdict`);

  const ctx = {
    tone, verdict, narrative,
    gatePass, gateReasons,
    tech, techMax, cat, catMax, rs, rsMax, sm, smMax, qg, qgMax,
    rawTotal, bonusTot,
    setupFamily, catalystTier, catalystTags, conviction, entryQ,
    tcStates, tcDir, mcChecks, mcPasses,
    sectorPctRank, sectorN, sectorDemoted,
    tier1Sigs, tier1ActiveCt, tier1Points,
    macroBlock,
  };

  document.getElementById('ruleEngineBody').innerHTML = `
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

    <!-- D-9: CONCORDANCE BANNER -->
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

    ${buildPipeline(T, ctx)}

    ${counters.length ? `
    <div class="re-counter">
      <div class="re-counter-h">⤷ WHAT WOULD CHANGE THE VERDICT</div>
      <ul>${counters.map(c => `<li>${c}</li>`).join('')}</ul>
    </div>` : ''}`;
}

export function dispose() { /* no-op */ }
