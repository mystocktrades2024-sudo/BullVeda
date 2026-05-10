// tabs/status/status.js — extracted from dashboard.html (renderStatus 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const dh = DATA.data_health || {};
  const checks = dh.checks || [];
  $('hcMeta').textContent = `${checks.filter(c => c.status === 'ok').length}/${checks.length} ok · scan ${DATA.run_timestamp || '—'}`;
  $('healthBody').innerHTML = checks.map(c => `
    <div class="hc-row">
      <div><b style="font-size:12.5px">${c.label}</b><div style="font-size:10px;color:var(--ink-3);margin-top:2px">${c.source || '—'}</div></div>
      <div class="hc-bar"><div class="hc-bar-fill" style="width:${c.pct||0}%;background:${c.status==='ok'?'var(--green)':c.status==='warn'?'var(--accent)':'var(--red)'}"></div></div>
      <div class="hc-pct">${(c.pct||0).toFixed(1)}%</div>
      <div class="hc-status ${c.status}">${c.status}</div>
    </div>
  `).join('');
}

export function dispose() { /* no-op */ }
