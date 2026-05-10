// tabs/themes/themes.js — extracted from dashboard.html (renderThemes 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const themes = DATA.themes || {};
  const order = [
    ['ultimate', 'Ultimate'],
    ['alt_energy', 'Alt Energy'],
    ['blockchain', 'Blockchain'],
    ['tech_innovators', 'Tech Innovators'],
    ['counterstrike', 'CounterStrike'],
    ['headlinetrader', 'HeadlineTrader'],
    ['tazr', 'TAZR'],
    ['bbt', 'BBT'],
  ];
  const cards = order.map(([key, label]) => {
    const rows = themes[key] || [];
    if (!rows.length) return '';
    return `
      <div class="card">
        <div class="card-h">${label} <span class="meta">${rows.length} positions</span></div>
        <table class="simple"><thead><tr><th>SYM</th><th>NAME</th><th class="r">ADDED</th><th class="r">LAST</th><th class="r">RET</th></tr></thead><tbody>
        ${rows.slice(0, 10).map(r => `
          <tr>
            <td><span class="sym" style="display:inline-flex;align-items:center;gap:6px">${_logoHtml(r.ticker, 18)}${r.ticker}</span></td>
            <td style="font-size:11px;color:var(--ink-2);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.company || '—'}</td>
            <td class="r" style="font-size:10.5px;color:var(--ink-3)">${r.price_add ? '$'+r.price_add : '—'}</td>
            <td class="r">${r.price_last ? '$'+r.price_last : '—'}</td>
            <td class="r" style="color:${(r.pct_chg||'').startsWith('-') ? 'var(--red)' : 'var(--green)'};font-weight:700">${r.pct_chg || '—'}</td>
          </tr>
        `).join('')}
        </tbody></table>
      </div>`;
  }).filter(Boolean).join('');
  $('themesBody').innerHTML = `<div class="grid-2">${cards}</div>`;
}

export function dispose() { /* no-op */ }
