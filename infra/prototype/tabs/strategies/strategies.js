// tabs/strategies/strategies.js — Strategy Engine tab.
// Extracted from dashboard.html:6526-6728 (2026-05-09).
// STRATEGIES const + seFilterStrategies stay in dashboard.html.

import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const STRATEGIES = window.STRATEGIES;
  const REGIME_META = {
    RoT: { label: 'Risk-On Trending', cls: 'pass' },
    RoC: { label: 'Risk-On Choppy',   cls: 'info' },
    Off: { label: 'Risk-Off',         cls: 'warn' },
    Panic: { label: 'Panic',          cls: 'fail' },
  };
  const STRATEGY_ALIASES = {
    'Core Swing Engine':  [],
    '10-Week Pullback':   ['10-Week Pullback'],
    'Mean Reversion':     ['Mean Reversion'],
    'Sector Rotation':    ['Sector Rotation'],
    'VCP Breakout':       ['VCP Breakout'],
    'Pocket Pivot':       ['Pocket Pivot'],
    'RS New High':        ['52wk Breakout', 'RS New High'],
    'Insider Buying':     ['Insider Buying'],
    'Insider Cluster':    ['Insider Cluster'],
    'Gap Holds':          ['Gap Holds', 'Gap Hold'],
    'Short Squeeze':      ['Short Squeeze', 'Breakdown'],
    'Earnings Run-Up':    ['Earnings Run-Up'],
    'Golden Cross':       ['Golden Cross', 'Trend Continuation'],
    'Bull Flag':          ['Bull Flag', 'Squeeze Expansion'],
    'Volume Breakout':    ['Volume Breakout', 'EMA21 Pullback'],
    'NR7 / Inside Day':   ['NR7', 'Inside Day'],
    'Volume Dry-Up':      ['Volume Dry-Up'],
    'OBV Divergence':     ['OBV Divergence', 'OBV Bull Div'],
    'Beat & Raise PEAD':  ['PEAD', 'Beat and Raise'],
  };
  const tbs = (DATA.performance && DATA.performance.tickers_by_strategy) || {};
  const currentRegime = (DATA.regime?.regime4 || '').toLowerCase();
  const REGIME_KEY_MAP = { 'risk_on_trending':'RoT', 'risk_on_choppy':'RoC', 'risk_off_trending':'Off', 'panic':'Panic' };
  const regKey = REGIME_KEY_MAP[currentRegime];
  const isStrategyActive = s => s.status === 'ACTIVE' && (!regKey || s.regimes.includes(regKey));

  const active = STRATEGIES.filter(s => s.status === 'ACTIVE');
  const planned = STRATEGIES.filter(s => s.status === 'PLANNED');
  const blendedWR = (() => {
    const wrs = active.map(s => {
      const m = (s.wr || '').match(/(\d+)-(\d+)%/);
      return m ? (parseInt(m[1]) + parseInt(m[2])) / 2 : null;
    }).filter(x => x != null);
    return wrs.length ? (wrs.reduce((a,b) => a+b, 0) / wrs.length).toFixed(0) : '—';
  })();
  const blendedPF = (() => {
    const pfs = active.filter(s => s.pf != null).map(s => s.pf);
    return pfs.length ? (pfs.reduce((a,b) => a+b, 0) / pfs.length).toFixed(2) : '—';
  })();
  const totalSamples = active.reduce((s,x) => s + (x.n || 0), 0);
  const t1Count = active.filter(s => s.edge === 'T1').length;
  const totalActiveInRegime = active.filter(isStrategyActive).length;

  const ranked = active.map(s => {
    const m = (s.wr || '').match(/(\d+)-(\d+)%/);
    return { s, mid: m ? (parseInt(m[1]) + parseInt(m[2])) / 2 : 0 };
  }).sort((a,b) => b.mid - a.mid);
  const best = ranked[0]?.s, worst = ranked[ranked.length-1]?.s;

  $('strategiesBanner').innerHTML = `
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
      <button class="se-chip on" data-filter="all" onclick="seFilterStrategies('all',this)">All <span class="ct">${STRATEGIES.length}</span></button>
      <button class="se-chip" data-filter="active-now" onclick="seFilterStrategies('active-now',this)">Active in Regime <span class="ct">${totalActiveInRegime}</span></button>
      <button class="se-chip" data-filter="t1" onclick="seFilterStrategies('t1',this)">T1 Edge <span class="ct">${t1Count}</span></button>
      <button class="se-chip" data-filter="planned" onclick="seFilterStrategies('planned',this)">Planned <span class="ct">${planned.length}</span></button>
      <span class="se-fb-sep"></span>
      <span class="se-fb-label">FAMILY:</span>
      ${[...new Set(STRATEGIES.map(s => s.family))].map(f => `<button class="se-chip" data-filter="family:${f}" onclick="seFilterStrategies('family:${f}',this)">${f}</button>`).join('')}
    </div>`;

  function chipFor(t) {
    const sc = t.score || 0;
    const cls = sc >= 80 ? 'high' : sc >= 70 ? 'med' : '';
    return `<span class="strat-chip ${cls}" title="${t.ticker} · score ${sc} · RS ${t.rs_rank || '—'} · entry $${t.entry_price ?? '—'} · stop $${t.stop ?? '—'} · ${t.date || ''}" onclick="window.location.href='elite-detail.html?t=${t.ticker}&from=strat'"><span class="sym">${t.ticker}</span><span class="sc">${sc}</span></span>`;
  }

  $('strategiesList').innerHTML = STRATEGIES.map(s => {
    const aliases = STRATEGY_ALIASES[s.name] || [s.name];
    let tickers = [];
    aliases.forEach(a => { if (tbs[a]) tickers = tickers.concat(tbs[a]); });
    const seen = new Set();
    tickers = tickers.filter(t => seen.has(t.ticker) ? false : (seen.add(t.ticker), true)).slice(0, 12);

    const isActive = s.status === 'ACTIVE';
    const isActiveInRegime = isStrategyActive(s);
    const statusPill = s.status === 'PLANNED' ? `<span class="se-status planned">PLANNED</span>`
                     : isActiveInRegime ? `<span class="se-status active">ACTIVE</span>`
                     : `<span class="se-status deferred" title="Regime gate: this strategy is paused outside its preferred regimes">DEFERRED</span>`;
    const edgePill = `<span class="se-edge ${s.edge.toLowerCase()}">${s.edge}</span>`;
    const regimePills = s.regimes.map(r => {
      const meta = REGIME_META[r] || { label: r, cls: 'info' };
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
          <div class="strat-tickers">${tickers.map(chipFor).join('')}</div>
        </div>` : `
        <div class="strat-roster">
          <div class="strat-roster-h"><span>Recent Picks</span></div>
          <div class="strat-empty">No recent picks logged for this scanner yet.</div>
        </div>`;

    const filterTags = [
      'all',
      s.status === 'ACTIVE' ? 'active' : 'planned',
      isActiveInRegime ? 'active-now' : '',
      s.edge === 'T1' ? 't1' : '',
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

  const sc = DATA.setup_counts || {};
  const vc = DATA.verdict_counts || {};
  const total = Object.values(sc).reduce((a,b) => a+b, 0) || 1;
  const setups = Object.entries(sc).sort((a,b) => b[1]-a[1]);
  const verdicts = Object.entries(vc).sort((a,b) => b[1]-a[1]);
  $('setupCountsBody').innerHTML = setups.map(([k,v]) => `
    <div class="hc-row" style="grid-template-columns:1fr 1fr 50px 60px">
      <div style="font-size:12px">${k}</div>
      <div class="hc-bar"><div class="hc-bar-fill" style="width:${v/total*100}%;background:var(--accent)"></div></div>
      <div class="hc-pct">${v}</div>
      <div class="hc-pct" style="color:var(--ink-3);font-size:10.5px">${(v/total*100).toFixed(1)}%</div>
    </div>
  `).join('');
  const totalV = Object.values(vc).reduce((a,b) => a+b, 0) || 1;
  $('verdictCountsBody').innerHTML = verdicts.map(([k,v]) => `
    <div class="hc-row" style="grid-template-columns:1fr 1fr 50px 60px">
      <div style="font-size:12px;color:${k==='BUY'?'var(--green)':k==='WATCH'?'var(--accent)':k==='SHORT'?'var(--red)':'var(--ink-2)'};font-weight:700">${k}</div>
      <div class="hc-bar"><div class="hc-bar-fill" style="width:${v/totalV*100}%;background:${k==='BUY'?'var(--green)':k==='WATCH'?'var(--accent)':k==='SHORT'?'var(--red)':'var(--ink-3)'}"></div></div>
      <div class="hc-pct">${v}</div>
      <div class="hc-pct" style="color:var(--ink-3);font-size:10.5px">${(v/totalV*100).toFixed(1)}%</div>
    </div>
  `).join('');
}

export function dispose() { /* no-op */ }


// ─── Helpers folded from dashboard.html (CapStudio sub-helpers fold 2026-05-09) ───
function seFilterStrategies(filter, btn) {
  document.querySelectorAll('.se-chip').forEach(b => b.classList.toggle('on', b === btn));
  document.querySelectorAll('.se-card').forEach(c => {
    const tags = (c.dataset.tags || '').split(' ');
    c.style.display = (filter === 'all' || tags.includes(filter)) ? '' : 'none';
  });
}


// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window.seFilterStrategies = seFilterStrategies;
}
