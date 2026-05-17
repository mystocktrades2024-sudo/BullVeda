// tabs/pairs/pairs.js — extracted from dashboard.html (renderPairs 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const sp = DATA.sector_pairs || {};
  const pairs = sp.pairs || [];
  const rsTable = sp.rs_table || {};

  const meta = document.getElementById('pairsMeta');
  const cardMeta = document.getElementById('pairsCardMeta');
  const ctEl = document.getElementById('sbPairsCt');
  if (ctEl) ctEl.textContent = pairs.length;
  if (meta) meta.textContent = `${pairs.length} pair${pairs.length === 1 ? '' : 's'} · spread ≥ 8% · ρ < 0.85${sp.error ? ' · ' + sp.error : ''}`;
  if (cardMeta) cardMeta.textContent = `${pairs.length} pair candidates`;

  const body = document.getElementById('pairsBody');
  if (body) {
    if (pairs.length === 0) {
      body.innerHTML = `<div style="padding:32px;text-align:center;color:var(--paper-3);font-size:13px">${sp.error ? 'Pair data error: ' + sp.error : 'No pair candidates today — sector RS spread is too narrow (need >8% divergence on 21d momentum) or all pairs are too correlated (ρ > 0.85). Pair trades work best in choppy / risk-off regimes; current regime may be too directional.'}</div>`;
    } else {
      body.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:10px 12px">Long / Short</th>
          <th style="text-align:right;padding:10px 12px">Spread 21d</th>
          <th style="text-align:right;padding:10px 12px">Spread 63d</th>
          <th style="text-align:right;padding:10px 12px">ρ</th>
          <th style="text-align:left;padding:10px 12px">Thesis</th>
        </tr></thead><tbody>
        ${pairs.map(p => `<tr style="border-bottom:1px solid var(--line)">
          <td style="padding:10px 12px;font-weight:700">
            <div><span style="color:var(--green);font-family:var(--mono);font-weight:800">▲ ${p.long}</span> <span style="color:var(--ink-2);font-size:11px;font-weight:400">${p.long_name}</span></div>
            <div style="margin-top:4px"><span style="color:var(--red);font-family:var(--mono);font-weight:800">▼ ${p.short}</span> <span style="color:var(--ink-2);font-size:11px;font-weight:400">${p.short_name}</span></div>
          </td>
          <td style="padding:10px 12px;text-align:right;font-family:var(--mono);font-weight:800;color:${p.spread_21d >= 12 ? 'var(--green)' : 'var(--accent)'}">+${p.spread_21d.toFixed(2)}%</td>
          <td style="padding:10px 12px;text-align:right;font-family:var(--mono);color:var(--ink-2)">${p.spread_63d >= 0 ? '+' : ''}${p.spread_63d.toFixed(2)}%</td>
          <td style="padding:10px 12px;text-align:right;font-family:var(--mono);color:${p.correlation < 0.5 ? 'var(--green)' : p.correlation < 0.7 ? 'var(--warn)' : 'var(--red)'};font-weight:700">${p.correlation != null ? p.correlation.toFixed(2) : '—'}</td>
          <td style="padding:10px 12px;font-size:12px;color:var(--ink-1);line-height:1.5">${p.narrative || '—'}</td>
        </tr>`).join('')}
        </tbody></table>`;
    }
  }

  const rsBody = document.getElementById('pairsRsBody');
  if (rsBody) {
    const rsRows = Object.values(rsTable).sort((a, b) => a.rank - b.rank);
    rsBody.innerHTML = rsRows.length === 0 ? '<div style="padding:18px;text-align:center;color:var(--paper-3);font-size:12px">No sector RS data.</div>' : `<table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
        <th style="text-align:left;padding:8px 12px">Rank</th>
        <th style="text-align:left;padding:8px 12px">ETF</th>
        <th style="text-align:left;padding:8px 12px">Sector</th>
        <th style="text-align:right;padding:8px 12px">RS 21d</th>
        <th style="text-align:right;padding:8px 12px">RS 63d</th>
      </tr></thead><tbody>
      ${rsRows.map(r => {
        const cls21 = r.rs_21d > 0 ? 'var(--green)' : 'var(--red)';
        const cls63 = r.rs_63d > 0 ? 'var(--green)' : 'var(--red)';
        return `<tr style="border-bottom:1px solid var(--line)">
          <td style="padding:8px 12px;font-family:var(--mono);font-weight:800;color:${r.rank <= 3 ? 'var(--green)' : r.rank >= rsRows.length - 2 ? 'var(--red)' : 'var(--ink-1)'}">#${r.rank}</td>
          <td style="padding:8px 12px;font-weight:700">${r.ticker}</td>
          <td style="padding:8px 12px;color:var(--ink-2)">${r.name}</td>
          <td style="padding:8px 12px;text-align:right;font-family:var(--mono);font-weight:700;color:${cls21}">${r.rs_21d >= 0 ? '+' : ''}${r.rs_21d.toFixed(2)}%</td>
          <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${cls63}">${r.rs_63d >= 0 ? '+' : ''}${r.rs_63d.toFixed(2)}%</td>
        </tr>`;
      }).join('')}
      </tbody></table>`;
  }
}

export function dispose() { /* no-op */ }
