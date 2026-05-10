// tabs/events/events.js — extracted from dashboard.html (_renderEvents 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render(kind = 'ipos') {
  const DATA = getData();
  const eventType = kind;  // alias — original was named 'kind' arg, body uses eventType
  const body = document.getElementById('evBody');
  const meta = document.getElementById('evMeta');
  const cardH = document.getElementById('evCardH');
  if (!body) return;
  document.querySelectorAll('[data-evtype]').forEach(b => b.classList.toggle('on', b.dataset.evtype === eventType));
  if (cardH) cardH.textContent = eventType === 'ipos' ? 'Upcoming IPOs' : eventType === 'splits' ? 'Stock Splits' : 'Earnings Trends';
  body.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">Loading…</div>';
  try {
    const r = await fetch(`/api/events/financial?event_type=${eventType}&days_ahead=30`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const events = d.events || [];
    if (meta) meta.textContent = `${events.length} upcoming · ${eventType}`;
    if (events.length === 0) {
      body.innerHTML = `<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No upcoming ${eventType}.</div>`;
      return;
    }
    if (eventType === 'ipos') {
      body.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
            <th style="text-align:left;padding:8px 12px">Date</th>
            <th style="text-align:left;padding:8px 12px">Symbol</th>
            <th style="text-align:left;padding:8px 12px">Company</th>
            <th style="text-align:left;padding:8px 12px">Exchange</th>
            <th style="text-align:right;padding:8px 12px">Price Range</th>
            <th style="text-align:right;padding:8px 12px">Shares</th>
          </tr></thead>
          <tbody>
            ${events.map(e => {
              const t = e.code || e.symbol || '';
              return `
              <tr style="border-bottom:1px solid var(--line)">
                <td style="padding:8px 12px;font-variant-numeric:tabular-nums">${e.start_date || e.ipo_date || e.date || '—'}</td>
                <td style="padding:8px 12px;font-weight:700;color:var(--paper)"><span style="display:inline-flex;align-items:center;gap:8px">${t ? _logoHtml(t, 20) : ''}${t || '—'}</span></td>
                <td style="padding:8px 12px;color:var(--paper-1)">${e.name || e.company || '—'}</td>
                <td style="padding:8px 12px;color:var(--paper-3);font-size:11px">${e.exchange || '—'}</td>
                <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${e.price_from && e.price_to ? '$' + e.price_from + '–' + e.price_to : (e.offer_price ? '$' + e.offer_price : '—')}</td>
                <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${e.shares ? e.shares.toLocaleString() : '—'}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`;
    } else if (eventType === 'splits') {
      body.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
            <th style="text-align:left;padding:8px 12px">Date</th>
            <th style="text-align:left;padding:8px 12px">Symbol</th>
            <th style="text-align:left;padding:8px 12px">Ratio</th>
          </tr></thead>
          <tbody>
            ${events.map(e => {
              const t = e.code || e.symbol || '';
              return `
              <tr style="border-bottom:1px solid var(--line)">
                <td style="padding:8px 12px;font-variant-numeric:tabular-nums">${e.split_date || e.date || '—'}</td>
                <td style="padding:8px 12px;font-weight:700;color:var(--paper)"><span style="display:inline-flex;align-items:center;gap:8px">${t ? _logoHtml(t, 20) : ''}${t || '—'}</span></td>
                <td style="padding:8px 12px;color:var(--accent)">${e.split_ratio || e.ratio || '—'}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`;
    } else {
      body.innerHTML = `<pre style="padding:14px;font-size:11px;color:var(--paper-1);overflow:auto">${JSON.stringify(events.slice(0, 20), null, 2)}</pre>`;
    }
  } catch (e) {
    body.innerHTML = `<div style="padding:30px;color:var(--watch);text-align:center;font-size:13px">Events unavailable: ${e.message}</div>`;
  }
}

export function dispose() { /* no-op */ }
