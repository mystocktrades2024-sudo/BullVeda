// tabs/killed/killed.js — extracted from dashboard.html (_renderKilledTab 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  // ── D-3: Correlation drops sub-card ──
  // Parses decision_reason for "corr gate" pattern across all mode lists.
  const corrBody = document.getElementById('corrDropBody');
  const corrMeta = document.getElementById('corrDropMeta');
  if (corrBody && DATA) {
    const allRows = [
      ...(DATA.short_term  || []),
      ...(DATA.medium_term || []),
      ...(DATA.long_term   || []),
      ...(DATA.killed      || []),
    ];
    const corrDrops = [];
    allRows.forEach(r => {
      const txt = String(r.decision_reason || r.reason || '');
      // Match "corr gate: 0.85 correlation with open NVDA > 0.80"
      const m = txt.match(/corr(?:elation)? gate:\s*(-?[\d.]+)\s*correlation with(?:\s+open)?\s+([A-Z.\-]+)/i);
      if (m) {
        corrDrops.push({
          ticker: r.ticker, sector: r.sector,
          score: r.score, price: r.price,
          correlated_with: m[2], corr: parseFloat(m[1]),
          reason_full: txt.slice(0, 240),
        });
      }
    });
    if (corrDrops.length === 0) {
      corrBody.innerHTML = '<div style="padding:18px;color:var(--paper-3);text-align:center;font-size:12px">No tickers dropped for correlation today. Gate fires only when a BUY candidate has > 0.80 correlation with an existing open position.</div>';
      if (corrMeta) corrMeta.textContent = '0 drops · 0.80 threshold';
    } else {
      if (corrMeta) corrMeta.textContent = `${corrDrops.length} drop${corrDrops.length === 1 ? '' : 's'} · 0.80 threshold`;
      corrBody.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:8px 12px">Dropped</th>
          <th style="text-align:left;padding:8px 12px">Correlated With</th>
          <th style="text-align:right;padding:8px 12px">ρ</th>
          <th style="text-align:right;padding:8px 12px">Score</th>
          <th style="text-align:left;padding:8px 12px">Sector</th>
          <th style="text-align:left;padding:8px 12px">Why dropped</th>
        </tr></thead><tbody>
        ${corrDrops.map(d => `<tr style="border-bottom:1px solid var(--line); cursor:pointer" onclick="window.location.href='elite-detail.html?t=${d.ticker}&from=killed'">
          <td style="padding:8px 12px;font-weight:700">${d.ticker}</td>
          <td style="padding:8px 12px;color:var(--accent);font-weight:600">${d.correlated_with}</td>
          <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${Math.abs(d.corr) > 0.9 ? 'var(--red)' : 'var(--warn)'};font-weight:700">${d.corr.toFixed(2)}</td>
          <td style="padding:8px 12px;text-align:right">${d.score || '—'}</td>
          <td style="padding:8px 12px;color:var(--paper-3)">${d.sector || '—'}</td>
          <td style="padding:8px 12px;color:var(--ink-1);font-size:11px">Already long ${d.correlated_with} — adding ${d.ticker} = false diversification (one concentrated bet)</td>
        </tr>`).join('')}
        </tbody></table>`;
    }
  }

  // ── F-3: Sector Demotions sub-card ──
  // Tickers that hit BUY threshold but were demoted to WATCH due to low sector_pct_rank.
  const sdBody = document.getElementById('sectorDemoteBody');
  const sdMeta = document.getElementById('sectorDemoteMeta');
  if (sdBody && DATA) {
    const all = [...(DATA.short_term || []), ...(DATA.medium_term || []), ...(DATA.long_term || [])];
    const demotes = all.filter(r => r.sector_demoted && r.sector_demotion_reason);
    if (demotes.length === 0) {
      sdBody.innerHTML = '<div style="padding:18px;color:var(--paper-3);text-align:center;font-size:12px">No tickers demoted by sector ranking today. Gate fires when a candidate sits below the 60th percentile of its sector\'s scores (config: <code>sector_relative_ranking.min_sector_percentile_for_buy</code>).</div>';
      if (sdMeta) sdMeta.textContent = '0 demotions · 60th-percentile gate';
    } else {
      // Group by sector
      const bySector = {};
      demotes.forEach(d => {
        const s = d.sector || 'Unknown';
        if (!bySector[s]) bySector[s] = [];
        bySector[s].push(d);
      });
      if (sdMeta) sdMeta.textContent = `${demotes.length} demotion${demotes.length === 1 ? '' : 's'} across ${Object.keys(bySector).length} sector${Object.keys(bySector).length === 1 ? '' : 's'}`;
      sdBody.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:8px 12px">Ticker</th>
          <th style="text-align:left;padding:8px 12px">Sector</th>
          <th style="text-align:right;padding:8px 12px">Score</th>
          <th style="text-align:right;padding:8px 12px">Sector %ile</th>
          <th style="text-align:left;padding:8px 12px">Reason</th>
        </tr></thead><tbody>
        ${demotes.sort((a,b) => (b.score||0) - (a.score||0)).map(d => `<tr style="border-bottom:1px solid var(--line); cursor:pointer" onclick="window.location.href='elite-detail.html?t=${d.ticker}&from=killed'">
          <td style="padding:8px 12px;font-weight:700">${d.ticker}</td>
          <td style="padding:8px 12px;color:var(--paper-3)">${d.sector || '—'}</td>
          <td style="padding:8px 12px;text-align:right;font-family:var(--mono);font-weight:700">${d.score || '—'}</td>
          <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${(d.sector_pct_rank || 0) < 30 ? 'var(--red)' : 'var(--warn)'}">${d.sector_pct_rank != null ? d.sector_pct_rank.toFixed(0) + '%' : '—'}</td>
          <td style="padding:8px 12px;font-size:11px;color:var(--ink-1)">${d.sector_demotion_reason || '—'}</td>
        </tr>`).join('')}
        </tbody></table>
        <div style="padding:11px 16px;border-top:1px dashed var(--rule);font-size:11px;color:var(--ink-2);line-height:1.55">
          <b style="color:var(--ink-0)">Why this matters:</b> a high absolute score in a weak sector is often a value trap — the entire sector is being avoided. The Phase 3 gate forces relative-strength selection. Demoted tickers <i>can</i> still be valid trades if you have a strong sector-rotation thesis, but the system won't allocate capital to them automatically.
        </div>`;
    }
  }

  const body = document.getElementById('killedBody');
  const meta = document.getElementById('killedCardMeta');
  if (!body || !DATA) return;
  const killed = DATA.killed || [];
  if (meta) meta.textContent = `${killed.length} rejected`;
  if (killed.length === 0) {
    body.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No tickers killed by gates today.</div>';
    return;
  }
  // Group by reason
  const byReason = {};
  killed.forEach(r => {
    const reason = r.reject_reason || r.kill_reason || r.reason || 'unspecified';
    (byReason[reason] = byReason[reason] || []).push(r);
  });
  const reasons = Object.keys(byReason).sort((a, b) => byReason[b].length - byReason[a].length);
  body.innerHTML = `
    <div style="padding:10px 14px;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;background:var(--ink-3)">
      ${reasons.map(rsn => `<span class="ev-tag warn" style="font-size:10px">${rsn} · ${byReason[rsn].length}</span>`).join('')}
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
        <th style="text-align:left;padding:8px 12px">Ticker</th>
        <th style="text-align:left;padding:8px 12px">Sector</th>
        <th style="text-align:right;padding:8px 12px">Price</th>
        <th style="text-align:right;padding:8px 12px">% chg</th>
        <th style="text-align:right;padding:8px 12px">Score</th>
        <th style="text-align:left;padding:8px 12px">Reason</th>
      </tr></thead>
      <tbody>
        ${killed.slice(0, 500).map(r => {
          const c = r.pct_chg || 0;
          const upDn = c > 0 ? 'up' : c < 0 ? 'dn' : 'dim';
          return `<tr style="border-bottom:1px solid var(--line);cursor:pointer" onclick="window.location.href='elite-detail.html?t=${r.ticker}&from=killed'">
            <td style="padding:8px 12px;font-weight:700;color:var(--paper)"><span style="display:inline-flex;align-items:center;gap:8px">${_logoHtml(r.ticker, 20)}${r.ticker}</span></td>
            <td style="padding:8px 12px;color:var(--paper-3)">${(r.sector || '—').slice(0, 35)}</td>
            <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${r.price ? '$' + r.price.toFixed(2) : '—'}</td>
            <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums" class="${upDn}">${r.pct_chg != null ? (c >= 0 ? '+' : '') + c.toFixed(2) + '%' : '—'}</td>
            <td style="padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums">${r.score || 0}</td>
            <td style="padding:8px 12px;color:var(--watch);font-size:11px">${r.reject_reason || r.kill_reason || r.reason || 'unspecified'}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
    ${killed.length > 500 ? `<div style="padding:10px;text-align:center;color:var(--paper-3);font-size:11px">Showing 500 of ${killed.length}</div>` : ''}`;
}

export function dispose() { /* no-op */ }
