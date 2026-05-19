// tabs/optionsflow/optionsflow.js — Options Flow (UOA imbalance) tab.
//
// Extracted from dashboard.html:5593-5690. Behavior preserved verbatim.
// Reads DATA.options_flow_top30 (built by build_data.py from optionsflow_scanner output).

import { getData } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('opFlowBody');
  const meta = document.getElementById('opFlowMeta');
  const flow = (DATA && DATA.options_flow_top30) || [];
  if (!body) return;

  if (!flow.length) {
    body.innerHTML = `
      <div style="padding:32px 28px; text-align:center; color:var(--ink-2); border:1px dashed var(--rule); border-radius:8px;">
        <div style="font-size:13px; font-weight:600; margin-bottom:6px;">No live options flow signals right now.</div>
        <div style="font-size:11px; color:var(--ink-3); line-height:1.6;">
          Either the universe shows no UOA imbalance (P/C &lt; 0.5 + ≥1000 vol + ≥$1M est. dollar volume) or
          options data hasn't been refreshed this scan. Re-run the scan after Schwab re-auth to populate.
        </div>
      </div>`;
    if (meta) meta.textContent = '0 candidates';
    return;
  }

  const strongCt = flow.filter(x => x.status === 'STRONG').length;
  const modCt    = flow.filter(x => x.status === 'MODERATE').length;
  const weakCt   = flow.filter(x => x.status === 'WEAK').length;

  if (meta) meta.textContent = `${flow.length} candidates · STRONG ${strongCt} · MOD ${modCt} · WEAK ${weakCt}`;
  const sb = document.getElementById('sbOpFlowCt'); if (sb) sb.textContent = flow.length;
  const fs = document.getElementById('fsOpFlowCt'); if (fs) fs.textContent = flow.length;

  const statusColor = s => ({STRONG: 'var(--pass)', MODERATE: 'var(--warn)', WEAK: 'var(--ink-3)'})[s] || 'var(--ink-2)';
  const fmtNum = n => {
    if (n == null) return '—';
    if (Math.abs(n) >= 1e6) return (n/1e6).toFixed(1) + 'M';
    if (Math.abs(n) >= 1e3) return (n/1e3).toFixed(0) + 'K';
    return Number(n).toFixed(0);
  };
  const fmtPct = (v, d=2) => v == null ? '—' : Number(v).toFixed(d);
  const fmtPx  = v => v == null ? '—' : '$' + Number(v).toFixed(2);

  const rows = flow.map(f => {
    const sc = statusColor(f.status);
    const tk = f.ticker || '';
    const px = fmtPx(f.price);
    const pcr = fmtPct(f.put_call_ratio);
    const uoaTag = f.uoa_calls ? '<span style="color:var(--pass); font-weight:700;">✓ UOA</span>' : '<span style="color:var(--ink-3);">—</span>';
    const sec = f.sector || '—';
    return `
      <tr style="border-bottom:1px solid var(--rule);">
        <td style="padding:9px 12px; font-family:var(--mono); font-weight:700;">
          <a href="#" onclick="window.setDetailTicker && window.setDetailTicker('${tk}'); return false;" style="color:var(--ink-0); text-decoration:none;">${tk}</a>
        </td>
        <td style="padding:9px 12px;">
          <span style="color:${sc}; font-weight:700; font-size:10px; letter-spacing:0.06em;">${f.status || '—'}</span>
        </td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${px}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono); color:${f.put_call_ratio < 0.3 ? 'var(--pass)' : 'var(--ink-1)'};">${pcr}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtNum(f.call_volume)}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtNum(f.put_volume)}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtNum(f.call_oi)}</td>
        <td style="padding:9px 12px; text-align:center;">${uoaTag}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtPct(f.iv_percentile, 0)}${f.iv_percentile != null ? '%' : ''}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtPx(f.max_pain)}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtPx(f.stop)}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono);">${fmtPx(f.target)}</td>
        <td style="padding:9px 12px; text-align:right; font-family:var(--mono); color:${f.rr >= 2 ? 'var(--pass)' : 'var(--ink-1)'};">${f.rr || '—'}</td>
        <td style="padding:9px 12px; font-size:11px; color:var(--ink-2);">${sec}</td>
      </tr>`;
  }).join('');

  body.innerHTML = `
    <div style="padding:0 0 14px; color:var(--ink-2); font-size:11.5px; line-height:1.55;">
      Daily call/put dollar-volume imbalance scanner. <b style="color:var(--pass)">STRONG</b> = P/C &lt; 0.2 AND UOA confirmed.
      <b style="color:var(--warn)">MODERATE</b> = P/C &lt; 0.3 OR UOA. Earnings within 3 days excluded (flow may be hedging).
      Entry: next day open · Stop: −3% · Target: +7% · Hold: 5–10 days.
    </div>
    <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:11.5px;">
        <thead>
          <tr style="background:var(--bg-2); color:var(--ink-3); text-align:left; border-bottom:1px solid var(--rule-2);">
            <th style="padding:9px 12px; font-weight:600; letter-spacing:0.04em; font-size:10px;">TICKER</th>
            <th style="padding:9px 12px; font-weight:600; letter-spacing:0.04em; font-size:10px;">SIGNAL</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">PRICE</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">P/C</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">CALL VOL</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">PUT VOL</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">CALL OI</th>
            <th style="padding:9px 12px; text-align:center; font-weight:600; letter-spacing:0.04em; font-size:10px;">UOA</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">IV %</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">MAX PAIN</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">STOP</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">TARGET</th>
            <th style="padding:9px 12px; text-align:right; font-weight:600; letter-spacing:0.04em; font-size:10px;">R:R</th>
            <th style="padding:9px 12px; font-weight:600; letter-spacing:0.04em; font-size:10px;">SECTOR</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

export function dispose() { /* no-op */ }
