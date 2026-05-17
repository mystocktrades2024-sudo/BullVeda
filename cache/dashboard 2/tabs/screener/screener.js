// tabs/screener/screener.js — extracted from dashboard.html (renderScreener 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const rows = DATA.screener || [];
  $('screenerMeta').textContent = `${rows.length} top by score · from ${DATA.scan_count || 0} universe`;
  $('screenerBody').innerHTML = `
    <table class="simple"><thead><tr><th>#</th><th>SYM</th><th>SECTOR</th><th>SETUP</th><th>STG</th><th class="r">SCORE</th><th class="r">PRICE</th><th class="r">RVOL</th><th class="r">RS</th><th class="r">R:R</th></tr></thead><tbody>
    ${rows.map((r,i) => `
      <tr>
        <td class="dim">${i+1}</td>
        <td><span class="sym" style="display:inline-flex;align-items:center;gap:6px">${_logoHtml(r.ticker, 18)}${r.ticker}</span></td>
        <td style="font-size:10.5px;color:var(--ink-2);text-transform:uppercase">${(r.sector||'').slice(0,18)}</td>
        <td style="font-size:11px">${r.setup || '—'}</td>
        <td><span style="font-size:10px;padding:2px 7px;border-radius:3px;letter-spacing:0.1em;font-weight:700;color:${r.stage==='BUY'?'var(--green)':r.stage==='WATCH'?'var(--accent)':r.stage==='SELL'?'var(--red)':'var(--ink-3)'};background:color-mix(in oklch,${r.stage==='BUY'?'var(--green)':r.stage==='WATCH'?'var(--accent)':r.stage==='SELL'?'var(--red)':'var(--ink-3)'} 16%,transparent)">${r.stage}</span></td>
        <td class="r" style="color:${r.score>=80?'var(--green)':r.score>=70?'var(--accent)':'var(--ink-1)'};font-weight:700">${r.score}</td>
        <td class="r">${r.price ? '$'+r.price.toFixed(2) : '—'}</td>
        <td class="r" style="color:${(r.rvol||0)>1.2?'var(--accent)':'var(--ink-1)'}">${r.rvol ? r.rvol.toFixed(1)+'×' : '—'}</td>
        <td class="r">${r.rs_rank ?? '—'}</td>
        <td class="r" style="color:${(r.rr||0)>=2.5?'var(--green)':'var(--ink-1)'};font-weight:700">${r.rr ? '1:'+r.rr.toFixed(1) : '—'}</td>
      </tr>
    `).join('')}
    </tbody></table>
  `;
}

export function dispose() { /* no-op */ }
