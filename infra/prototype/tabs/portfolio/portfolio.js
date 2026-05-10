// tabs/portfolio/portfolio.js — Portfolio tab renderer.
//
// Extracted from dashboard.html:7487-7687. Behavior preserved verbatim.
// Tab-private helpers (factor-exposure heatmap, cross-mode-exposure tile)
// stay in this module — they're not used by any other tab.

import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const p   = DATA.portfolio || {};
  const pos = p.positions || [];
  const cls = p.closed || [];

  const totalUnrealized = pos.reduce((s, x) => s + (x.unrealized_pnl_dollars || 0), 0);
  const winningOpen = pos.filter(x => (x.unrealized_pnl_pct || 0) > 0).length;
  const losingOpen  = pos.filter(x => (x.unrealized_pnl_pct || 0) < 0).length;
  const totalRealized = cls.reduce((s, x) => s + (x.pnl_dollars || 0), 0);

  $('portfolioMeta').textContent = `${pos.length} open · ${cls.length} closed · last update ${(pos[0]?.last_updated || '—')}`;

  $('pfSummary').innerHTML = `
    <div class="stat-tile"><div class="lbl">Equity</div><div class="v">${p.equity != null ? '$' + Number(p.equity).toLocaleString('en-US', {maximumFractionDigits: 2}) : '—'}</div><div class="sub">total account</div></div>
    <div class="stat-tile"><div class="lbl">Cash</div><div class="v" style="font-size:18px">${p.cash != null ? '$' + Number(p.cash).toLocaleString('en-US', {maximumFractionDigits: 0}) : '—'}</div><div class="sub">available</div></div>
    <div class="stat-tile ${totalUnrealized >= 0 ? 'ok' : 'bad'}"><div class="lbl">Unrealized P&L</div><div class="v">${totalUnrealized >= 0 ? '+' : '−'}$${Math.abs(totalUnrealized).toFixed(0)}</div><div class="sub">${winningOpen} win / ${losingOpen} loss open</div></div>
    <div class="stat-tile ${totalRealized >= 0 ? 'ok' : 'bad'}"><div class="lbl">Realized P&L</div><div class="v">${totalRealized >= 0 ? '+' : '−'}$${Math.abs(totalRealized).toFixed(0)}</div><div class="sub">${cls.length} closed trades</div></div>
    <div class="stat-tile"><div class="lbl">Positions</div><div class="v">${pos.length}</div><div class="sub">${pos.filter(x => x.direction === 'long').length} long · ${pos.filter(x => x.direction === 'short').length} short</div></div>
  `;

  // ── D-4: Factor Exposure heatmap (MVP) ──
  const _allBuys = [
    ...(DATA.short_term  || []).filter(r => r.stage === 'BUY'),
    ...(DATA.medium_term || []).filter(r => r.stage === 'BUY'),
  ];
  const _avg = (arr) => arr.length ? arr.reduce((a,b) => a+b, 0) / arr.length : null;
  const _momRanks   = _allBuys.map(r => r.rs_rank).filter(v => v != null);
  const _qualPts    = _allBuys.map(r => r.fund_pts).filter(v => v != null);
  const _qualMax    = _allBuys.map(r => r.fund_max || 30).filter(v => v != null);
  const _fwdPes     = _allBuys.map(r => r.fwd_pe).filter(v => v != null && v > 0);
  const _avgFwdPe   = _avg(_fwdPes);
  const _factors = {
    momentum: { v: _avg(_momRanks),  scale: 100,  n: _momRanks.length, lbl: 'Momentum',
                tip: 'Avg RS rank vs SPY across BUY candidates' },
    quality:  { v: _qualPts.length && _avg(_qualMax) ? (_avg(_qualPts) / _avg(_qualMax) * 100) : null,
                scale: 100, n: _qualPts.length, lbl: 'Quality',
                tip: 'Avg quality-gate pillar score (margins, balance sheet, growth)' },
    value:    { v: _avgFwdPe ? Math.max(0, Math.min(100, 100 - (_avgFwdPe - 8) * 2)) : null,
                scale: 100, n: _fwdPes.length, lbl: 'Value',
                tip: 'Inverse fwd P/E — higher score = cheaper. PE 8 = 100, PE 33+ = 0' },
  };
  const _facEl = document.getElementById('factorHeatmap');
  if (_facEl) {
    const _row = (key) => {
      const f = _factors[key];
      if (f.v == null) {
        return `<div class="fac-row">
          <div class="fac-name">${f.lbl}</div>
          <div class="fac-bar"><div class="fac-fill dim" style="width:0%"></div></div>
          <div class="fac-val dim">limited data</div>
          <div class="fac-n">${f.n}/${_allBuys.length}</div>
        </div>`;
      }
      const cls = f.v >= 70 ? 'pass' : f.v >= 40 ? 'warn' : 'fail';
      return `<div class="fac-row" title="${f.tip}">
        <div class="fac-name">${f.lbl}</div>
        <div class="fac-bar"><div class="fac-fill ${cls}" style="width:${Math.min(100, f.v)}%"></div></div>
        <div class="fac-val ${cls}">${Math.round(f.v)}</div>
        <div class="fac-n">${f.n}/${_allBuys.length}</div>
      </div>`;
    };
    _facEl.innerHTML = _allBuys.length === 0 ? `
      <div style="padding:18px;text-align:center;color:var(--ink-3);font-size:12px">No BUY candidates to compute factor exposure.</div>
    ` : `
      <div class="cme-h">
        <span class="cme-title">FACTOR EXPOSURE</span>
        <span class="cme-meta">Across ${_allBuys.length} BUY candidates · ${_avgFwdPe ? 'avg fwd P/E ' + _avgFwdPe.toFixed(1) : 'fwd P/E sparse'}</span>
      </div>
      <div class="fac-grid">
        ${_row('momentum')}${_row('quality')}${_row('value')}
      </div>
      <div class="fac-foot">Bars are 0–100 normalized. <b>n/total</b> shows data coverage — sparse coverage means metric is unreliable.</div>
    `;
  }

  // ── D-1: Cross-Mode Exposure tile ──
  const _crossModeRows = [
    ...(DATA.short_term  || []).filter(r => r.stage === 'BUY' && r.sector).map(r => ({mode: 'Swing',    ticker: r.ticker, sector: r.sector})),
    ...(DATA.medium_term || []).filter(r => r.stage === 'BUY' && r.sector).map(r => ({mode: 'Position', ticker: r.ticker, sector: r.sector})),
    ...(DATA.long_term   || []).filter(r => r.stage === 'BUY' && r.sector).map(r => ({mode: 'Invest',   ticker: r.ticker, sector: r.sector})),
  ];
  const _sectorTallies = {};
  _crossModeRows.forEach(r => {
    if (!_sectorTallies[r.sector]) _sectorTallies[r.sector] = { count: 0, modes: { Swing: 0, Position: 0, Invest: 0 }, tickers: [] };
    _sectorTallies[r.sector].count++;
    _sectorTallies[r.sector].modes[r.mode]++;
    if (_sectorTallies[r.sector].tickers.length < 6 && !_sectorTallies[r.sector].tickers.includes(r.ticker)) {
      _sectorTallies[r.sector].tickers.push(r.ticker);
    }
  });
  const _totalAcrossModes = _crossModeRows.length || 1;
  const _topSectors = Object.entries(_sectorTallies).sort((a,b) => b[1].count - a[1].count).slice(0, 6);
  const _maxConc = _topSectors[0] ? Math.round(_topSectors[0][1].count / _totalAcrossModes * 100) : 0;
  const _concAlert = _maxConc >= 30 ? 'fail' : _maxConc >= 20 ? 'warn' : 'ok';
  const _concEl = document.getElementById('crossModeExposure');
  if (_concEl) {
    _concEl.innerHTML = _topSectors.length === 0 ? `
      <div style="padding:18px;text-align:center;color:var(--ink-3);font-size:12px">No BUY candidates across modes yet — run a scan to populate.</div>
    ` : `
      <div class="cme-h">
        <span class="cme-title">CROSS-MODE EXPOSURE</span>
        <span class="cme-meta">${_crossModeRows.length} BUY candidates across Swing + Position + Invest · top sector <b class="${_concAlert === 'fail' ? 'fail' : _concAlert === 'warn' ? 'warn' : 'pass'}">${_topSectors[0][0]} ${_maxConc}%</b></span>
      </div>
      <div class="cme-grid">
        ${_topSectors.map(([sec, t]) => {
          const pct = Math.round(t.count / _totalAcrossModes * 100);
          const cls = pct >= 30 ? 'fail' : pct >= 20 ? 'warn' : 'pass';
          return `<div class="cme-row">
            <div class="cme-sec">${sec}</div>
            <div class="cme-bar"><div class="cme-fill ${cls}" style="width:${Math.min(100, pct*2)}%"></div><span class="cme-pct">${pct}%</span></div>
            <div class="cme-modes">
              <span class="cme-pill swing"  title="Swing">${t.modes.Swing}S</span>
              <span class="cme-pill pos"    title="Position">${t.modes.Position}P</span>
              <span class="cme-pill invest" title="Invest">${t.modes.Invest}I</span>
            </div>
            <div class="cme-tickers">${t.tickers.join(' · ')}${t.count > t.tickers.length ? ' +' + (t.count - t.tickers.length) : ''}</div>
          </div>`;
        }).join('')}
      </div>
      ${_maxConc >= 30 ? `<div class="cme-warn">⚠ <b>${_topSectors[0][0]}</b> is ${_maxConc}% of cross-mode BUY signals. If you take every BUY at equal weight, you'll be heavily concentrated in this sector across all horizons.</div>` : ''}
    `;
  }

  $('openPosMeta').textContent = `${pos.length} positions`;
  $('openPosBody').innerHTML = pos.length === 0 ? `
    <div class="stub" style="padding:30px"><div class="ico">◯</div><div class="title">No open positions</div><div class="desc">Positions opened via the production server will appear here.</div></div>
  ` : `
    <table class="simple"><thead><tr><th>SYM</th><th>DIR</th><th>SETUP</th><th class="r">SHARES</th><th class="r">ENTRY</th><th class="r">NOW</th><th class="r">STOP</th><th class="r">T1</th><th class="r">P&amp;L %</th><th class="r">P&amp;L $</th><th>VERDICT</th><th class="c">ACTIONS</th></tr></thead><tbody>
    ${pos.map(x => {
      const pnlPct = x.unrealized_pnl_pct;
      const pnlD   = x.unrealized_pnl_dollars;
      const cls    = (pnlPct || 0) >= 0 ? 'pnl-up' : 'pnl-dn';
      const verdict = (x.last_exit_verdict || {});
      const _entry  = (x.entry_price || x.entry || 0);
      const _shares = (x.shares || 0);
      const _dir    = (x.direction || 'long').toLowerCase();
      const _stop   = (x.stop || 0);
      const _now    = (x.current_price || 0);
      return `<tr data-pos-ticker="${x.ticker}" data-pos-entry="${_entry}" data-pos-shares="${_shares}" data-pos-dir="${_dir}" data-pos-stop="${_stop}" data-pos-t1="${x.target1 || ''}">
        <td><span class="sym">${x.ticker}</span><div style="font-size:10.5px;color:var(--ink-1)">${x.entry_date || ''}</div></td>
        <td><span class="pf-pill ${_dir}">${_dir.toUpperCase()}</span></td>
        <td style="font-size:11.5px;color:var(--ink-0)">${x.setup_type || x.setup || '—'}</td>
        <td class="r">${_shares}</td>
        <td class="r">$${_entry.toFixed(2)}</td>
        <td class="r" data-pos-now style="font-weight:700">$${_now.toFixed(2)}</td>
        <td class="r" style="color:var(--red)">$${_stop.toFixed(2)}</td>
        <td class="r" style="color:var(--accent)">${x.target1 ? '$' + x.target1.toFixed(2) : '—'}</td>
        <td class="r ${cls}" data-pos-pnl-pct>${pnlPct != null ? (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%' : '—'}</td>
        <td class="r ${cls}" data-pos-pnl-d>${pnlD != null ? (pnlD >= 0 ? '+$' : '−$') + Math.abs(pnlD).toFixed(0) : '—'}</td>
        <td style="min-width:240px"><span class="pf-pill ${verdict.action === 'HOLD' ? 'hold' : verdict.action === 'EXIT' ? 'short' : 'long'}">${verdict.action || '—'}</span><div title="${(verdict.reason || '').replace(/"/g,'&quot;')}" style="font-size:11px;color:var(--ink-1);margin-top:3px;line-height:1.35;white-space:normal;word-break:break-word">${verdict.reason || ''}</div></td>
        <td class="c" style="white-space:nowrap">
          <button class="pos-act-btn pos-act-be"    onclick="posMoveToBE('${x.ticker}', event)"    title="Move stop to break-even (entry price)">B/E</button>
          <button class="pos-act-btn pos-act-trail" onclick="posTrailStop('${x.ticker}', ${_now}, event)" title="Trail stop with current price">Trail</button>
          <button class="pos-act-btn pos-act-close" onclick="posClosePosition('${x.ticker}', ${_shares}, ${_now}, event)" title="Close position at market">Close</button>
        </td>
      </tr>`;
    }).join('')}
    </tbody></table>
  `;

  $('closedPosMeta').textContent = `${cls.length} trades`;
  $('closedPosBody').innerHTML = cls.length === 0 ? `
    <div style="padding:30px;text-align:center;color:var(--ink-3);font-size:12px">No closed trades yet.</div>
  ` : `
    <table class="simple"><thead><tr><th>SYM</th><th>SETUP</th><th class="r">ENTRY</th><th class="r">EXIT</th><th class="r">P&amp;L %</th><th class="r">P&amp;L $</th><th>WHY</th></tr></thead><tbody>
    ${cls.map(x => `
      <tr>
        <td><span class="sym">${x.ticker}</span><div style="font-size:10px;color:var(--ink-3)">${x.entry_date} → ${x.exit_date}</div></td>
        <td style="font-size:11px;color:var(--ink-2)">${x.setup_type || x.setup || '—'}</td>
        <td class="r">$${(x.entry_price || 0).toFixed(2)}</td>
        <td class="r" style="font-weight:700">$${(x.exit_price || 0).toFixed(2)}</td>
        <td class="r ${(x.pnl_pct||0) >= 0 ? 'pnl-up' : 'pnl-dn'}">${x.pnl_pct != null ? (x.pnl_pct >= 0 ? '+' : '') + x.pnl_pct.toFixed(2) + '%' : '—'}</td>
        <td class="r ${(x.pnl_dollars||0) >= 0 ? 'pnl-up' : 'pnl-dn'}">${(x.pnl_dollars||0) >= 0 ? '+$' : '−$'}${Math.abs(x.pnl_dollars || 0).toFixed(0)}</td>
        <td style="font-size:11px;color:var(--ink-2)">${x.exit_reason || '—'}</td>
      </tr>
    `).join('')}
    </tbody></table>
  `;

  const monthly = p.monthly_pnl || {};
  const months = Object.entries(monthly).sort();
  $('monthlyPnlBody').innerHTML = months.length === 0 ? `
    <div style="padding:20px;text-align:center;color:var(--ink-3);font-size:12px">No monthly data yet.</div>
  ` : `
    ${months.map(([m, v]) => {
      const realized = (v.realized_pnl != null) ? v.realized_pnl : (typeof v === 'number' ? v : 0);
      const trades   = v.trades || v.closed_count || 0;
      return `<div class="hc-row" style="grid-template-columns:80px 1fr 80px 60px">
        <div style="font-size:12px;font-weight:700">${m}</div>
        <div class="hc-bar"><div class="hc-bar-fill" style="width:${Math.min(100, Math.abs(realized)/100)}%;background:${realized >= 0 ? 'var(--green)' : 'var(--red)'}"></div></div>
        <div class="hc-pct ${realized >= 0 ? 'pnl-up' : 'pnl-dn'}">${realized >= 0 ? '+$' : '−$'}${Math.abs(realized).toFixed(0)}</div>
        <div style="font-size:10.5px;color:var(--ink-3);text-align:right">${trades} trade${trades === 1 ? '' : 's'}</div>
      </div>`;
    }).join('')}
  `;
}

export function dispose() { /* no-op — Portfolio holds no timers/listeners */ }
