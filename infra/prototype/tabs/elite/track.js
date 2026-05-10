// tabs/elite/track.js — Per-mode track band + compact pick rows.
// Three tracks render below the hero band (Swing/Position/Invest).

import { tier, stageBadge, modeLabel, money, arc } from './helpers.js';
import { thesisLine } from './thesis.js';

export function renderTrack(mode, modeData, heroPicks) {
  const heroSet = new Set(heroPicks.map(h => h.ticker));
  const stages  = ['BUY', 'WATCH', 'SHORT'];

  const allInMode = stages.flatMap(s =>
    (modeData[s] || []).map((p, i) => ({ ...p, _stage: s, _rank: i + 1 }))
  );
  const total = allInMode.length;

  // Empty mode: render an informative one-liner instead of a placeholder card
  if (total === 0) {
    return `<div class="ep2-track ep2-track-empty">
      <div class="ep2-track-h">
        <span class="ep2-track-mode">${modeLabel(mode).toUpperCase()}</span>
        <span class="ep2-track-empty-msg">No qualifying picks in this horizon.</span>
      </div>
    </div>`;
  }

  // Avg score for the mode (track-level KPI)
  const avg = total ? Math.round(allInMode.reduce((s, p) => s + (p.elite_score || 0), 0) / total) : 0;
  const t   = tier(avg);

  return `<div class="ep2-track">
    <div class="ep2-track-h">
      <span class="ep2-track-mode">${modeLabel(mode).toUpperCase()}</span>
      <span class="ep2-track-count">${total} pick${total === 1 ? '' : 's'}</span>
      <span class="ep2-track-avg">avg score <b style="color:${t.color}">${avg}</b></span>
      ${stages.filter(s => (modeData[s] || []).length).map(s => {
        const sb = stageBadge(s);
        return `<span class="ep2-track-stage" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${(modeData[s] || []).length} ${sb.label}</span>`;
      }).join('')}
    </div>
    <div class="ep2-track-rows">
      ${allInMode.map(p => _renderTrackRow(p, heroSet.has(p.ticker))).join('')}
    </div>
  </div>`;
}

// Compact row — one per pick within a track. Click → elite-detail.
function _renderTrackRow(p, isHero) {
  const t   = tier(p.elite_score);
  const sb  = stageBadge(p._stage);
  const snap = p.snapshot || {};
  const thesis  = thesisLine(p);
  const winProb = snap.p_target != null ? `${snap.p_target}%` : '—';

  return `<div class="ep2-row${isHero ? ' ep2-row-hero' : ''}" onclick="window.location.href='elite-detail.html?t=${p.ticker}&from=elite'">
    <div class="ep2-row-rank">#${p._rank}</div>
    <div class="ep2-row-arc">${arc(p.elite_score, t.color, 40, 14)}</div>
    <div class="ep2-row-id">
      <div class="ep2-row-ticker-line">
        <span class="ep2-row-ticker">${p.ticker}</span>
        ${isHero ? '<span class="ep2-row-star" title="In Hero">★</span>' : ''}
        <span class="ep2-row-tier" style="color:${t.color}">${t.label}</span>
        <span class="ep2-row-stage" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${sb.label}</span>
      </div>
      <div class="ep2-row-thesis">${thesis}</div>
    </div>
    <div class="ep2-row-kpis">
      <div class="ep2-row-kpi">
        <div class="ep2-row-kpi-l">Win</div>
        <div class="ep2-row-kpi-v" style="color:${snap.p_target >= 60 ? 'var(--green)' : 'var(--ink-0)'}">${winProb}</div>
      </div>
      <div class="ep2-row-kpi">
        <div class="ep2-row-kpi-l">R:R</div>
        <div class="ep2-row-kpi-v">1:${(snap.rr || 0).toFixed(1)}</div>
      </div>
      <div class="ep2-row-kpi ep2-row-kpi-px">
        <div class="ep2-row-kpi-l">Entry</div>
        <div class="ep2-row-kpi-v">${money((snap.entry||[])[0])}</div>
      </div>
      <div class="ep2-row-kpi ep2-row-kpi-px">
        <div class="ep2-row-kpi-l">Stop · T1</div>
        <div class="ep2-row-kpi-v"><span style="color:var(--red)">${money(snap.stop)}</span> · <span style="color:var(--green)">${money(snap.target1)}</span></div>
      </div>
    </div>
    <div class="ep2-row-chevron">›</div>
  </div>`;
}
