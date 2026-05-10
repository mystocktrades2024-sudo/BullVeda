// tabs/elite/elite.js — Elite Picks v2 thin orchestrator.
//
// Architecture (three-act):
//   ACT 1 — HERO   : top 3 across all 9 cells (hero.js)
//   ACT 2 — TRACKS : per-mode horizontal bands (track.js)
//   ACT 3 — CONTEXT: regime strip + collapsed legend (framing.js)
//
// Sub-modules:
//   helpers.js — tier, stageBadge, modeLabel, money, arc (pure)
//   thesis.js  — plain-English thesis from breakdown + snapshot
//   hero.js    — hero card renderer
//   track.js   — track band + compact row renderers
//   framing.js — regime strip / suppressed banner / empty state / legend

import { getData }         from '../../core/shared.js';
import { renderHeroCard }  from './hero.js';
import { renderTrack }     from './track.js';
import { renderRegimeStrip, renderSuppressedBanner,
         renderEmptyState, renderLegendCollapsed } from './framing.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('elitePicksBody');
  const meta = document.getElementById('elitePicksMeta');
  const sbCt = document.getElementById('sbEliteCt');
  if (!body) return;

  const ep = DATA.elite_picks || {};
  if (ep.error) {
    body.innerHTML = `<div class="ep2-empty">⚠ Elite picks computation error: ${ep.error}</div>`;
    return;
  }

  // Flatten: collect every (mode, stage, pick) tuple across the 9 cells
  const all = [];
  for (const mode of ['Swing', 'Position', 'Invest']) {
    for (const stage of ['BUY', 'WATCH', 'SHORT']) {
      const cell = (ep[mode] || {})[stage] || [];
      cell.forEach((p, i) => all.push({ ...p, _mode: mode, _stage: stage, _rank: i + 1 }));
    }
  }
  if (sbCt) sbCt.textContent = all.length;

  // Meta strip (top header)
  if (meta) {
    if (ep.meta?.blocked) {
      meta.innerHTML = `<span style="color:var(--fail)">SUPPRESSED</span> · ${ep.meta.reason || 'system gate active'}`;
    } else {
      const heroN = Math.min(3, all.length);
      meta.textContent = `${ep.meta?.n_passing_hard_gates ?? 0} passed hard gates · ${heroN} hero · ${all.length} total picks`;
    }
  }

  // Suppressed state — single banner, no grid
  if (ep.meta?.blocked) {
    body.innerHTML = renderSuppressedBanner(ep.meta);
    return;
  }

  // Empty state — nothing qualified
  if (all.length === 0) {
    body.innerHTML = renderEmptyState(ep, DATA);
    return;
  }

  // Pick top 3 globally for the hero band, ranked by elite_score
  const hero = [...all].sort((a, b) => (b.elite_score || 0) - (a.elite_score || 0)).slice(0, 3);

  body.innerHTML = `
    ${renderRegimeStrip(ep, DATA)}

    <div class="ep2-hero-band">
      <div class="ep2-section-h">
        <span class="ep2-section-eyebrow">★ Today's best ideas</span>
        <span class="ep2-section-sub">Top ${hero.length} across all modes & stages, ranked by Elite Score</span>
      </div>
      <div class="ep2-hero-grid">
        ${hero.map(p => renderHeroCard(p)).join('')}
      </div>
    </div>

    ${['Swing', 'Position', 'Invest'].map(mode => renderTrack(mode, ep[mode] || {}, hero)).join('')}

    ${renderLegendCollapsed()}
  `;
}

export function dispose() { /* no-op */ }
