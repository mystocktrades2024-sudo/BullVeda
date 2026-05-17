// subtabs/smc/smc.js — SMC sub-tab thin orchestrator.
//
// Sub-modules:
//   ladder.js       — price-ladder SVG (OBs / FVGs / fractals / VWAP / NOW)
//   lux_screener.js — D-8 LuxAlgo MTF screener (3 dense tables)
//   cards.js        — verdict banner + structure cards + tables + plan + horizon
//
// Sub-modules are pure functions; no DOM access except via this entry's
// document.getElementById('smcBody'). Fixes a bare `$` reference in the
// original extraction.

import { buildLadderSVG }   from './ladder.js';
import { buildLuxScreener } from './lux_screener.js';
import { buildBody }        from './cards.js';

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;

  const smc       = T.smc || {};
  const px        = +(T.price || 0);
  const bc        = smc.bos_choch || {};
  const obs       = smc.order_blocks || [];
  const fvgs      = smc.fvg_zones || [];
  const liquidity = smc.liquidity_sweeps || [];
  const direction = (smc.smc_direction || 'neutral').toLowerCase();
  const fracHi    = +(T.fractal_high || 0);
  const fracLo    = +(T.fractal_low  || 0);
  const vwap      = T.vwap || {};
  const zq        = T.zone_quality || {};

  // Verdict tone + headline
  let tone, arrow, hLabel, hEm;
  if (direction === 'bullish' || (bc.bos_bullish && !bc.bos_bearish)) {
    tone = 'bull';    arrow = '▲'; hLabel = 'Smart money structure is'; hEm = 'BULLISH';
  } else if (direction === 'bearish' || (bc.bos_bearish && !bc.bos_bullish)) {
    tone = 'bear';    arrow = '▼'; hLabel = 'Smart money structure is'; hEm = 'BEARISH';
  } else {
    tone = 'neutral'; arrow = '◆'; hLabel = 'Smart money structure is'; hEm = 'NEUTRAL';
  }

  const lastStruct  = bc.last_structure || '—';
  const bosBars     = bc.bos_bars_ago;
  const chochBars   = bc.choch_bars_ago;
  const bosEvent    = bc.bos_bullish    ? 'Bullish BOS'   : bc.bos_bearish    ? 'Bearish BOS'   : 'No active BOS';
  const chochEvent  = bc.choch_bullish  ? 'Bullish CHoCH' : bc.choch_bearish  ? 'Bearish CHoCH' : 'No CHoCH';

  // OB stats
  const freshOBs     = obs.filter(o => o.freshness >= 0.7 && o.status !== 'mitigated').length;
  const testedOBs    = obs.filter(o => o.status === 'tested').length;
  const mitigatedOBs = obs.filter(o => o.status === 'mitigated').length;
  const bullOBs      = obs.filter(o => o.type === 'bullish').length;
  const bearOBs      = obs.filter(o => o.type === 'bearish').length;
  const topOBs       = [...obs].sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0)).slice(0, 6);
  const maxStrength  = obs.reduce((m, o) => Math.max(m, o.strength_score || 0), 1);

  // FVG stats
  const openFVGs   = fvgs.filter(f => f.status === 'open');
  const closedFVGs = fvgs.filter(f => f.status === 'closed');

  // Narrative
  let narr = '';
  if      (bc.bos_bullish) narr = `Latest break of structure was bullish ${bosBars != null ? bosBars + ' bars ago' : ''}, last swing structure: ${lastStruct}.`;
  else if (bc.bos_bearish) narr = `Latest break of structure was bearish ${bosBars != null ? bosBars + ' bars ago' : ''}, last swing structure: ${lastStruct}.`;
  else                     narr = `No clear break of structure recently. Last swing structure: ${lastStruct}.`;
  if (freshOBs > 0)         narr += ` ${freshOBs} fresh order block${freshOBs>1?'s':''} active.`;
  if (openFVGs.length > 0)  narr += ` ${openFVGs.length} unfilled FVG${openFVGs.length>1?'s':''}.`;

  // Synthesized SMC-driven trade plan
  const bullishCandidates = obs.filter(o => o.type === 'bullish' && o.price_level < px && o.status !== 'mitigated')
    .sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0));
  const bestBullOB = bullishCandidates[0];
  const planStop   = bestBullOB ? Math.min(bestBullOB.low * 0.98, fracLo > 0 ? fracLo * 0.98 : bestBullOB.low * 0.98) : (fracLo > 0 ? fracLo * 0.98 : px * 0.95);
  const planEntry  = bestBullOB ? bestBullOB.price_level : (fracLo > 0 ? fracLo * 1.005 : px * 0.97);
  const bearishAbove = obs.filter(o => o.type === 'bearish' && o.price_level > px && o.status !== 'mitigated')
    .sort((a, b) => a.price_level - b.price_level)[0];
  const risk       = planEntry - planStop;
  const planTarget = bearishAbove ? bearishAbove.price_level : (fracHi > 0 && fracHi > px ? fracHi : planEntry + risk * 2.0);
  const planRR     = risk > 0 ? (planTarget - planEntry) / risk : 0;

  // Horizon impact
  const hzImpact = (() => {
    const hasOpenFvgBelow = openFVGs.filter(f => f.bottom < px).length;
    const hasFreshBullOB  = bullishCandidates.filter(o => o.freshness >= 0.7).length;
    const dirIsBull       = tone === 'bull';
    return {
      swing:    dirIsBull && hasOpenFvgBelow ? `Tactical pullback into open FVG below = ideal entry. ${hasOpenFvgBelow} unfilled gap${hasOpenFvgBelow>1?'s':''} near price.` : (tone === 'bear' ? 'Bearish structure — short pullbacks to bearish OBs above.' : 'No clear SMC tactical setup.'),
      position: dirIsBull && hasFreshBullOB  ? `Buy pullback to nearest fresh demand OB. ${hasFreshBullOB} candidate${hasFreshBullOB>1?'s':''} below current price.` : (tone === 'bear' ? 'Wait for bullish CHoCH before considering position longs.' : 'No fresh demand zones — wait for new OB formation.'),
      invest:   dirIsBull ? `Higher-timeframe BOS bullish. SMC supports a structural long bias for 12+ months.` : (tone === 'bear' ? `Higher-timeframe BOS bearish. Avoid new positions until structure flips.` : 'Neutral structure — no SMC-driven invest signal.'),
    };
  })();

  const ladderSVG  = buildLadderSVG({ px, obs, fvgs, fracHi, fracLo, vwap });
  const luxSection = buildLuxScreener(T, px, obs, fvgs);
  const body       = buildBody({
    px, smc, tone, arrow, hLabel, hEm, narr,
    obs, fvgs, openFVGs, closedFVGs, liquidity,
    fracHi, fracLo, vwap, zq,
    freshOBs, testedOBs, mitigatedOBs, bullOBs, bearOBs, topOBs, maxStrength,
    lastStruct, bosBars, chochBars, bosEvent, chochEvent,
    ladderSVG,
    bestBullOB, bullishCandidates, bearishAbove,
    planEntry, planStop, planTarget, planRR,
    hzImpact,
  });

  const target = document.getElementById('smcBody');
  if (target) target.innerHTML = luxSection + body;
}

export function dispose() { /* no-op */ }
