// tabs/alerts/alerts.js — extracted from dashboard.html (_renderAlertsTab 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const alerts = JSON.parse(localStorage.getItem('floor_alerts') || '[]');
  const body = document.getElementById('alertsBody');
  const meta = document.getElementById('alertsCardMeta');
  if (meta) meta.textContent = `${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`;
  if (!body) return;
  if (alerts.length === 0) {
    body.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No alerts set. Open any ticker detail page and click "+ Alert" to set one.</div>';
    return;
  }
  // Latest prices from DATA
  const priceMap = {};
  if (DATA) [...(DATA.short_term || []), ...(DATA.medium_term || []), ...(DATA.long_term || [])].forEach(r => { priceMap[r.ticker] = r.price; });
  body.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
        <th style="text-align:left;padding:8px 12px">Ticker</th>
        <th style="text-align:right;padding:8px 12px">Alert price</th>
        <th style="text-align:right;padding:8px 12px">Current</th>
        <th style="text-align:right;padding:8px 12px">Distance</th>
        <th style="text-align:right;padding:8px 12px">Created</th>
        <th style="padding:8px 12px"></th>
      </tr></thead>
      <tbody>
        ${alerts.map((a, i) => {
          const cur = priceMap[a.ticker];
          const dist = cur ? ((cur - a.price) / a.price * 100) : null;
          const fired = cur && Math.abs((cur - a.price) / a.price) < 0.005;
          return `<tr style="border-bottom:1px solid var(--line);${fired ? 'background:var(--watch-bg)' : ''}">
            <td style="padding:10px 12px;font-weight:700">
              <a href="elite-detail.html?t=${a.ticker}&from=alerts" style="color:var(--paper);text-decoration:none;display:inline-flex;align-items:center;gap:8px">${_logoHtml(a.ticker, 20)}<span>${a.ticker}</span></a>
              ${fired ? '<span class="ev-tag warn" style="margin-left:8px">FIRED</span>' : ''}
            </td>
            <td style="padding:10px 12px;text-align:right;font-variant-numeric:tabular-nums">$${a.price.toFixed(2)}</td>
            <td style="padding:10px 12px;text-align:right;font-variant-numeric:tabular-nums">${cur ? '$' + cur.toFixed(2) : '—'}</td>
            <td style="padding:10px 12px;text-align:right;font-variant-numeric:tabular-nums" class="${dist > 0 ? 'up' : dist < 0 ? 'dn' : 'dim'}">${dist != null ? (dist >= 0 ? '+' : '') + dist.toFixed(2) + '%' : '—'}</td>
            <td style="padding:10px 12px;text-align:right;color:var(--paper-3);font-size:10px">${a.created ? new Date(a.created).toLocaleDateString() : '—'}</td>
            <td style="padding:10px 12px;text-align:right">
              <button onclick="_removeAlert(${i})" style="background:none;border:1px solid var(--line);color:var(--paper-3);cursor:pointer;padding:3px 8px;border-radius:3px;font-size:10px">REMOVE</button>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

export function dispose() { /* no-op */ }
