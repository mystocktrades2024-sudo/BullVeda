// tabs/status/status.js — extracted from dashboard.html (renderStatus 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
//
// A7 (2026-05-09): drift alert tile — fetches /api/drift-alerts and renders
// rolling live-vs-backtest WR drift status. Powered by daily cron at
// LaunchAgents/com.swingtrade.driftalert.plist (writes data/drift_alerts.jsonl).
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

  // A7 — drift alert tile (additive — renders only if #driftBody exists in DOM)
  _renderDriftTile();
}

async function _renderDriftTile() {
  const host = document.getElementById('driftBody');
  if (!host) return;
  host.innerHTML = '<div style="color:var(--ink-3);font-size:11px;padding:10px">Loading drift alerts…</div>';
  try {
    const resp = await fetch('/api/drift-alerts?limit=10', { credentials: 'include' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!data.log_exists || (data.alerts || []).length === 0) {
      host.innerHTML = `<div style="color:var(--ink-3);font-size:11px;padding:10px">No drift alerts yet. Cron runs daily at 4:30pm PT.${data.log_exists ? '' : '<br>Log: data/drift_alerts.jsonl'}</div>`;
      return;
    }
    const latest = data.alerts[0] || {};
    const drifted = (latest.drifted_setups || []).filter(s => s.delta_pp != null);
    const status = drifted.length === 0 ? 'ok' : (drifted.length >= 3 ? 'fail' : 'warn');
    const color = status === 'ok' ? 'var(--green)' : (status === 'warn' ? 'var(--accent)' : 'var(--red)');
    host.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-bottom:1px solid var(--rule);margin-bottom:8px">
        <span style="background:${color};color:#000;padding:2px 8px;border-radius:3px;font-size:10px;font-family:var(--mono);font-weight:600">${status.toUpperCase()}</span>
        <div style="font-size:12px;color:var(--ink-1)">Last check: ${latest.checked_at || '—'} · ${data.count} total alerts</div>
      </div>
      ${drifted.length === 0 ? `<div style="color:var(--green);font-size:12px;padding:6px 10px">✓ No setups drifting beyond threshold. Live WR tracking backtest.</div>` : `
        <div style="font-size:11px;color:var(--ink-3);margin:0 10px 4px">${drifted.length} setup${drifted.length === 1 ? '' : 's'} drifted. Δ = live WR − backtest WR (pp).</div>
        ${drifted.slice(0, 6).map(s => `<div style="display:flex;justify-content:space-between;padding:4px 10px;font-size:12px;border-bottom:1px solid var(--rule-2)"><span style="font-family:var(--mono)">${s.setup}</span><span style="color:${s.delta_pp < 0 ? 'var(--red)' : 'var(--green)'};font-family:var(--mono)">Δ ${s.delta_pp >= 0 ? '+' : ''}${s.delta_pp.toFixed(1)}pp · live WR ${s.live_wr ? (s.live_wr * 100).toFixed(0) : '—'}% (n=${s.live_n || 0})</span></div>`).join('')}
      `}
    `;
  } catch (e) {
    host.innerHTML = `<div style="color:var(--red);font-size:11px;padding:10px">Drift API unavailable: ${e.message}</div>`;
  }
}

export function dispose() { /* no-op */ }
