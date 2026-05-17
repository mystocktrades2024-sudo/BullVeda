// tabs/strategies/cards.js — Per-strategy card renderer.
// Returns the HTML string for #strategiesList (a stack of <div class="se-card">).

import { REGIME_META, STRATEGY_ALIASES } from './constants.js';

function _tickerChip(t) {
  const sc  = t.score || 0;
  const cls = sc >= 80 ? 'high' : sc >= 70 ? 'med' : '';
  return `<span class="strat-chip ${cls}" title="${t.ticker} · score ${sc} · RS ${t.rs_rank || '—'} · entry $${t.entry_price ?? '—'} · stop $${t.stop ?? '—'} · ${t.date || ''}" onclick="window.location.href='elite-detail.html?t=${t.ticker}&from=strat'"><span class="sym">${t.ticker}</span><span class="sc">${sc}</span></span>`;
}

export function buildCards(strategies, tbs, isStrategyActive, regKey) {
  return strategies.map(s => {
    const aliases = STRATEGY_ALIASES[s.name] || [s.name];
    let tickers = [];
    aliases.forEach(a => { if (tbs[a]) tickers = tickers.concat(tbs[a]); });
    const seen = new Set();
    tickers = tickers.filter(t => seen.has(t.ticker) ? false : (seen.add(t.ticker), true)).slice(0, 12);

    const isActiveInRegime = isStrategyActive(s);
    const statusPill = s.status === 'PLANNED' ? `<span class="se-status planned">PLANNED</span>`
                     : isActiveInRegime       ? `<span class="se-status active">ACTIVE</span>`
                     :                          `<span class="se-status deferred" title="Regime gate: this strategy is paused outside its preferred regimes">DEFERRED</span>`;
    const edgePill = `<span class="se-edge ${s.edge.toLowerCase()}">${s.edge}</span>`;
    const regimePills = s.regimes.map(r => {
      const meta      = REGIME_META[r] || { label: r, cls: 'info' };
      const isCurrent = r === regKey;
      return `<span class="se-reg-pill ${meta.cls} ${isCurrent ? 'now' : ''}" title="${meta.label}${isCurrent ? ' (current regime)' : ''}">${r}</span>`;
    }).join('');

    const roster = s.status === 'PLANNED' ? `
        <div class="se-planned-note">
          <span class="ico">⚙</span>
          <div>Catalogued, code stub only. Source: <code>${s.src}</code>. Not yet wired into nightly scan.</div>
        </div>`
      : tickers.length > 0 ? `
        <div class="strat-roster">
          <div class="strat-roster-h"><span>Recent Picks</span><span class="ct">${tickers.length} ticker${tickers.length === 1 ? '' : 's'}</span></div>
          <div class="strat-tickers">${tickers.map(_tickerChip).join('')}</div>
        </div>`
      : `
        <div class="strat-roster">
          <div class="strat-roster-h"><span>Recent Picks</span></div>
          <div class="strat-empty">No recent picks logged for this scanner yet.</div>
        </div>`;

    const filterTags = [
      'all',
      s.status === 'ACTIVE' ? 'active' : 'planned',
      isActiveInRegime      ? 'active-now' : '',
      s.edge === 'T1'       ? 't1' : '',
      `family:${s.family}`,
    ].filter(Boolean).join(' ');

    return `
      <div class="se-card ${s.status.toLowerCase()}" data-tags="${filterTags}" style="border-left-color:${s.color}">
        <div class="se-card-top">
          <span class="se-num" style="background:color-mix(in oklch, ${s.color} 18%, transparent);color:${s.color}">#${s.num}</span>
          <div class="se-card-titles">
            <div class="se-card-name">${s.name}</div>
            <div class="se-card-family">${s.family}</div>
          </div>
          ${statusPill}
          ${edgePill}
        </div>
        <div class="se-card-stats">
          <div class="se-stat"><div class="lbl">Win Rate</div><div class="v ${s.edge === 'T1' ? 'pass' : ''}">${s.wr}</div></div>
          <div class="se-stat"><div class="lbl">Profit Factor</div><div class="v ${s.pf >= 1.6 ? 'pass' : s.pf >= 1.3 ? 'warn' : ''}">${s.pf != null ? s.pf.toFixed(2) : '—'}</div></div>
          <div class="se-stat"><div class="lbl">Hold</div><div class="v">${s.hold}</div></div>
          <div class="se-stat"><div class="lbl">R:R Min</div><div class="v">${s.rr}</div></div>
          <div class="se-stat"><div class="lbl">Sample n</div><div class="v ${s.n >= 50 ? 'pass' : s.n >= 20 ? 'warn' : 'fail'}">${s.n || '—'}</div></div>
        </div>
        <div class="se-card-regimes">
          <span class="se-rl">FITS:</span>${regimePills}
        </div>
        <div class="se-card-desc">${s.desc}</div>
        ${roster}
        <div class="se-card-foot">
          <span class="se-src-l">SOURCE</span>
          <code>${s.src}</code>
        </div>
      </div>`;
  }).join('');
}
