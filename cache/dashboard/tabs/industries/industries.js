// tabs/industries/industries.js — extracted from dashboard.html (renderIndustries 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const sectors = DATA.sector_etf || {};
  const rows = Object.entries(sectors)
    .map(([sym, s]) => ({ sym, ...s }))
    .sort((a, b) => (a.rank || 99) - (b.rank || 99));
  $('sectorEtfBody').innerHTML = `
    <table class="simple"><thead><tr><th>#</th><th>ETF</th><th>SECTOR</th><th class="r">PRICE</th><th class="r">PERF %</th><th class="r">vs SPY</th></tr></thead><tbody>
    ${rows.map((r,i) => `
      <tr>
        <td class="dim">${r.rank || i+1}</td>
        <td><span class="sym">${r.sym}</span></td>
        <td style="font-size:11px;color:var(--ink-2)">${r.sector || '—'}</td>
        <td class="r">$${(r.price||0).toFixed(2)}</td>
        <td class="r ${chgClass2(r.perf_pct)}">${fmt(r.perf_pct, 2)}%</td>
        <td class="r ${chgClass2(r.vs_spy_pct)}">${fmt(r.vs_spy_pct, 2)}%</td>
      </tr>
    `).join('')}
    </tbody></table>
  `;

  const inds = DATA.industries || [];
  $('industriesBody').innerHTML = `
    <table class="simple"><thead><tr><th>#</th><th>INDUSTRY</th><th class="r">N</th><th class="r">AVG SCORE</th><th>TOP TICKERS</th></tr></thead><tbody>
    ${inds.slice(0, 20).map((r,i) => `
      <tr>
        <td class="dim">${i+1}</td>
        <td style="font-size:11.5px">${r.industry || '—'}</td>
        <td class="r">${r.count}</td>
        <td class="r" style="color:${(r.avg_score||0) >= 75 ? 'var(--green)' : (r.avg_score||0) >= 60 ? 'var(--accent)' : 'var(--ink-2)'};font-weight:700">${(r.avg_score||0).toFixed(1)}</td>
        <td style="font-size:11px;color:var(--ink-1)">${(r.tickers || []).slice(0,5).join(', ')}</td>
      </tr>
    `).join('')}
    </tbody></table>
  `;
  $('indMeta').textContent = `${inds.length} industries · ${rows.length} sector ETFs`;
}

export function dispose() { /* no-op */ }
