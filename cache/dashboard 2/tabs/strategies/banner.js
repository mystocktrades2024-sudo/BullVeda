// tabs/strategies/banner.js — Hero banner + leaderboard + filter chip bar.
// Returns the HTML string for #strategiesBanner.

import { REGIME_META } from './constants.js';

export function buildBanner(strategies, active, planned, totalActiveInRegime, regKey) {
  const blendedWR = (() => {
    const wrs = active.map(s => {
      const m = (s.wr || '').match(/(\d+)-(\d+)%/);
      return m ? (parseInt(m[1]) + parseInt(m[2])) / 2 : null;
    }).filter(x => x != null);
    return wrs.length ? (wrs.reduce((a, b) => a + b, 0) / wrs.length).toFixed(0) : '—';
  })();
  const blendedPF = (() => {
    const pfs = active.filter(s => s.pf != null).map(s => s.pf);
    return pfs.length ? (pfs.reduce((a, b) => a + b, 0) / pfs.length).toFixed(2) : '—';
  })();
  const totalSamples = active.reduce((s, x) => s + (x.n || 0), 0);
  const t1Count      = active.filter(s => s.edge === 'T1').length;

  const ranked = active.map(s => {
    const m = (s.wr || '').match(/(\d+)-(\d+)%/);
    return { s, mid: m ? (parseInt(m[1]) + parseInt(m[2])) / 2 : 0 };
  }).sort((a, b) => b.mid - a.mid);
  const best  = ranked[0]?.s;
  const worst = ranked[ranked.length - 1]?.s;

  return `
    <div class="se-hero">
      <div class="se-hero-top">
        <div>
          <div class="se-hero-tag">STRATEGY ENGINE · ${active.length} ACTIVE · ${planned.length} PLANNED</div>
          <div class="se-hero-h">Multi-strategy alpha across <b style="color:var(--info)">${totalActiveInRegime}</b> scanners active in current ${REGIME_META[regKey]?.label || 'regime'}</div>
          <div class="se-hero-narr">Each scanner is independently scored, sized, and tracked. The dashboard lets you sort by edge, regime fit, family, or recent picks.</div>
        </div>
        <div class="se-hero-stats">
          <div class="se-hs"><div class="v pass">${blendedWR}%</div><div class="lbl">Blended WR</div></div>
          <div class="se-hs"><div class="v">${blendedPF}</div><div class="lbl">Avg PF</div></div>
          <div class="se-hs"><div class="v">${totalSamples}</div><div class="lbl">Total n</div></div>
          <div class="se-hs"><div class="v info">${t1Count}</div><div class="lbl">T1 Edge</div></div>
        </div>
      </div>
      ${best && worst ? `
      <div class="se-hero-leaders">
        <div class="se-leader best">
          <span class="lbl">⭐ Best edge</span>
          <span class="name">${best.name}</span>
          <span class="meta">${best.wr} · n=${best.n} · ${best.family}</span>
        </div>
        <div class="se-leader worst">
          <span class="lbl">⚠ Thinnest sample</span>
          <span class="name">${worst.name}</span>
          <span class="meta">${worst.wr} · n=${worst.n} · ${worst.family}</span>
        </div>
      </div>` : ''}
    </div>
    <div class="se-filterbar">
      <span class="se-fb-label">FILTER:</span>
      <button class="se-chip on" data-filter="all"        onclick="seFilterStrategies('all',this)">All <span class="ct">${strategies.length}</span></button>
      <button class="se-chip"     data-filter="active-now" onclick="seFilterStrategies('active-now',this)">Active in Regime <span class="ct">${totalActiveInRegime}</span></button>
      <button class="se-chip"     data-filter="t1"         onclick="seFilterStrategies('t1',this)">T1 Edge <span class="ct">${t1Count}</span></button>
      <button class="se-chip"     data-filter="planned"    onclick="seFilterStrategies('planned',this)">Planned <span class="ct">${planned.length}</span></button>
      <span class="se-fb-sep"></span>
      <span class="se-fb-label">FAMILY:</span>
      ${[...new Set(strategies.map(s => s.family))].map(f => `<button class="se-chip" data-filter="family:${f}" onclick="seFilterStrategies('family:${f}',this)">${f}</button>`).join('')}
    </div>`;
}

// Chip click handler — bound to window for inline onclick callers
export function filterStrategies(filter, btn) {
  document.querySelectorAll('.se-chip').forEach(b => b.classList.toggle('on', b === btn));
  document.querySelectorAll('.se-card').forEach(c => {
    const tags = (c.dataset.tags || '').split(' ');
    c.style.display = (filter === 'all' || tags.includes(filter)) ? '' : 'none';
  });
}
