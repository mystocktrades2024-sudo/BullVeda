// tabs/macro/macro.js — extracted from dashboard.html (_renderMacroTab 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render() {
  const DATA = getData();
  const tilesEl = document.getElementById('macroTiles');
  const evBody = document.getElementById('macroEvBody');
  const evCt = document.getElementById('macroEvCt');
  const sigBody = document.getElementById('macroSignalsBody');
  if (!tilesEl) return;

  // Use economic_events already in DATA (faster) + augment via /api/macro/events for fresh
  let events = DATA?.economic_events || [];
  try {
    const r = await fetch('/api/macro/events?days_ahead=14');
    if (r.ok) {
      const d = await r.json();
      if (d.events?.length) events = d.events;
    }
  } catch (_) {}

  // Find next high-impact event
  const isHigh = (e) => {
    const lbl = (e.event || e.type || '').toLowerCase();
    return lbl.includes('fomc') || lbl.includes('cpi') || lbl.includes('payroll')
        || lbl.includes('nfp') || lbl.includes('pmi') || lbl.includes('rate decision')
        || lbl.includes('unemployment') || lbl.includes('gdp');
  };
  const high = events.filter(isHigh).slice(0, 6);
  const macro = DATA?.macro_signals || {};
  const yc = macro.yield_curve || {};
  const regime = DATA?.regime || {};
  const vix = (regime.vix && typeof regime.vix === 'object') ? regime.vix.vix_current : (regime.vix || 0);

  // Tiles
  const fmtEv = (e) => {
    const d = e.date || e.scheduled || '';
    const dt = d ? new Date(d) : null;
    const diffH = dt ? Math.floor((dt.getTime() - Date.now()) / 3600000) : null;
    const lbl = !diffH ? '' : diffH < 1 ? 'NOW' : diffH < 24 ? `IN ${diffH}H` : `+${Math.floor(diffH/24)}D`;
    return { name: (e.event || e.type || '').slice(0, 28), date: d.slice(0, 10), lbl, raw: e };
  };
  const nextHigh = high[0] ? fmtEv(high[0]) : null;
  tilesEl.innerHTML = `
    <div class="stat-tile">
      <div class="lbl">Next high-impact</div>
      <div class="v" style="font-size:13px">${nextHigh ? nextHigh.name : '—'}</div>
      <div class="sub">${nextHigh ? nextHigh.lbl + ' · ' + nextHigh.date : ''}</div>
    </div>
    <div class="stat-tile ${yc.inverted ? 'bad' : 'ok'}">
      <div class="lbl">Yield Curve (10y–2y)</div>
      <div class="v">${yc.spread != null ? (yc.spread >= 0 ? '+' : '') + yc.spread.toFixed(2) + '%' : '—'}</div>
      <div class="sub">${yc.inverted ? '⚠ INVERTED — recession signal' : 'Normal — expansionary'}</div>
    </div>
    <div class="stat-tile ${vix < 18 ? 'ok' : vix < 25 ? 'warn' : 'bad'}">
      <div class="lbl">VIX</div>
      <div class="v">${vix ? vix.toFixed(1) : '—'}</div>
      <div class="sub">${vix < 18 ? 'risk-on' : vix < 25 ? 'elevated' : 'panic'}</div>
    </div>
    <div class="stat-tile">
      <div class="lbl">Events This Week</div>
      <div class="v">${events.length}</div>
      <div class="sub">${high.length} high-impact</div>
    </div>`;

  // Events list
  if (evCt) evCt.textContent = `${events.length} events`;
  if (events.length === 0) {
    evBody.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No upcoming events.</div>';
  } else {
    evBody.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:8px 12px">Date</th>
          <th style="text-align:left;padding:8px 12px">Event</th>
          <th style="text-align:left;padding:8px 12px">Country</th>
          <th style="text-align:right;padding:8px 12px">Actual</th>
          <th style="text-align:right;padding:8px 12px">Forecast</th>
          <th style="text-align:right;padding:8px 12px">Previous</th>
          <th style="text-align:left;padding:8px 12px">Impact</th>
        </tr></thead>
        <tbody>
          ${events.slice(0, 30).map(e => {
            const dt = e.date || e.scheduled || '';
            const dtFmt = dt ? new Date(dt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
            const high = isHigh(e);
            return `<tr style="border-bottom:1px solid var(--line)${high ? ';background:color-mix(in oklch,var(--watch) 5%,transparent)' : ''}">
              <td style="padding:8px 12px;font-size:11px;color:var(--paper-3);font-variant-numeric:tabular-nums">${dtFmt}</td>
              <td style="padding:8px 12px;color:var(--paper);font-weight:${high ? 700 : 500}">${e.event || e.type || '—'}</td>
              <td style="padding:8px 12px;font-size:11px;color:var(--paper-3)">${e.country || 'US'}</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${e.actual ?? '—'}</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums;color:var(--paper-3)">${e.forecast ?? e.estimate ?? '—'}</td>
              <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums;color:var(--paper-3)">${e.previous ?? '—'}</td>
              <td style="padding:8px 12px"><span class="ev-tag ${high ? 'warn' : 'info'}">${high ? 'HIGH' : 'LOW'}</span></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  // Macro signals (yield curve + sector ETFs + breadth)
  const breadth = DATA?.market_breadth || {};
  sigBody.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px">
      <div><div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--paper-3);margin-bottom:6px">10y–2y Spread</div><div style="font-size:22px;font-weight:800;color:${yc.inverted ? 'var(--red)' : 'var(--green)'}">${yc.spread != null ? (yc.spread >= 0 ? '+' : '') + yc.spread.toFixed(2) : '—'}</div><div style="font-size:11px;color:var(--paper-3)">trend: ${yc.trend || '—'}</div></div>
      <div><div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--paper-3);margin-bottom:6px">Breadth (above 50d)</div><div style="font-size:22px;font-weight:800">${breadth.pct_above_50d != null ? breadth.pct_above_50d.toFixed(0) + '%' : '—'}</div><div style="font-size:11px;color:var(--paper-3)">${breadth.label_50 || ''}</div></div>
      <div><div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--paper-3);margin-bottom:6px">Distribution Days</div><div style="font-size:22px;font-weight:800">${regime.distribution_days || 0}</div><div style="font-size:11px;color:var(--paper-3)">${(regime.distribution_days || 0) >= 5 ? '⚠ near IBD threshold' : 'within tolerance'}</div></div>
    </div>`;
}

export function dispose() { /* no-op */ }
