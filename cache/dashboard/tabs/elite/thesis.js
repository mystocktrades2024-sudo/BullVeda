// tabs/elite/thesis.js — Plain-English thesis synthesizer.
// Picks the strongest 2-3 factors from breakdown + snapshot and renders them
// as a single sentence. No raw arithmetic — replaces the old format like
// "+ MC P(T1 first) 57% – P(stop first) 43% = ++15% edge → 16.2/25".

import { tier } from './helpers.js';

export function thesisLine(p) {
  const snap = p.snapshot || {};
  const bd   = p.breakdown || {};
  const pTarget = snap.p_target;
  const pStop   = snap.p_stop;
  const rr      = snap.rr;
  const sharpe  = snap.fwd_sharpe;
  const tierLbl = tier(p.elite_score).label;

  const phrases = [];
  if (pTarget != null && pStop != null) {
    const edge = pTarget - pStop;
    if (edge >= 25)      phrases.push(`Strong forward edge: ${pTarget}% target vs ${pStop}% stop`);
    else if (edge >= 10) phrases.push(`Positive edge: ${pTarget}%/${pStop}% (target/stop)`);
    else if (edge >= 0)  phrases.push(`Marginal edge: ${pTarget}%/${pStop}%`);
    else                 phrases.push(`Tight: ${pTarget}%/${pStop}%`);
  }
  if (rr != null && rr >= 2.5) phrases.push(`R:R 1:${rr.toFixed(1)}`);
  else if (rr != null)         phrases.push(`R:R 1:${rr.toFixed(1)} (light)`);
  if (sharpe != null && sharpe >= 1.5) phrases.push(`Sharpe ${sharpe.toFixed(1)}`);

  const factorWin = _findFactorHighlight(bd);
  if (factorWin) phrases.push(factorWin);

  // Earnings warning supersedes all other thesis text
  if (snap.earn_days != null && snap.earn_days <= 7) {
    return `⚠ Earnings in ${snap.earn_days}d — ${phrases.slice(0, 2).join(' · ')}`;
  }

  return phrases.slice(0, 3).join(' · ') || (p.verdict_line || `${tierLbl} pick`);
}

function _findFactorHighlight(bd) {
  const factors = [
    { key: 'sector_rank',     max: 12, label: pct => `Top ${100 - Math.round(pct * 100 / 12)}% sector` },
    { key: 'tier1_stack',     max: 11, label: pct => 'Tier-1 stack firing' },
    { key: 'conviction_tier', max: 12, label: pct => 'High-conviction setup' },
    { key: 'entry_quality',   max: 12, label: pct => 'Fresh entry zone' },
    { key: 'hmm_regime',      max: 11, label: pct => 'Regime aligned' },
  ];
  for (const f of factors) {
    const pts = (bd[f.key] || {}).adj_pts || 0;
    if (pts / f.max >= 0.8) return f.label(pts);
  }
  return null;
}
