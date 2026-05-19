// tabs/premarket/premarket.js — extracted from dashboard.html (_renderPremarket 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render() {
  const DATA = getData();
  const body = document.getElementById('pmBody');
  const meta = document.getElementById('pmMeta');
  if (!body) return;
  body.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">Loading…</div>';
  const minGap = parseFloat(document.getElementById('pmMinGap')?.value || '2.0');
  try {
    const r = await fetch(`/api/premarket/movers?min_gap_pct=${minGap}&limit=50`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const movers = d.movers || [];
    if (meta) meta.textContent = `${movers.length} movers · gap ≥ ${minGap}%`;
    if (movers.length === 0) {
      body.innerHTML = `<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No tickers gapping ≥${minGap}% pre-market right now.</div>`;
      return;
    }
    body.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:8px 12px">Ticker</th>
          <th style="text-align:left;padding:8px 12px">Sector</th>
          <th style="text-align:right;padding:8px 12px">Price</th>
          <th style="text-align:right;padding:8px 12px">Gap %</th>
          <th style="text-align:right;padding:8px 12px">Vol Ratio</th>
          <th style="text-align:right;padding:8px 12px">Score</th>
        </tr></thead>
        <tbody>
          ${movers.map(m => {
            const gapCls = m.gap_pct > 0 ? 'up' : 'dn';
            return `<tr style="border-bottom:1px solid var(--line);cursor:pointer" onclick="window.setDetailTicker && window.setDetailTicker('${m.ticker}')">
              <td style="padding:8px 12px;font-weight:700;color:var(--paper)"><span style="display:inline-flex;align-items:center;gap:8px">${_logoHtml(m.ticker, 20)}${m.ticker}</span></td>
              <td style="padding:8px 12px;color:var(--paper-3);font-size:11px">${(m.sector || '—').slice(0, 30)}</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${m.price ? '$' + m.price.toFixed(2) : '—'}</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700" class="${gapCls}">${m.gap_pct >= 0 ? '+' : ''}${m.gap_pct.toFixed(2)}%</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${m.vol_ratio.toFixed(2)}×</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${m.score || 0}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    body.innerHTML = `<div style="padding:30px;color:var(--watch);text-align:center;font-size:13px">Pre-market data unavailable: ${e.message}</div>`;
  }
}

export function dispose() { /* no-op */ }
