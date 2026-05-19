// tabs/audit/rows.js — Per-signal grid <thead> + <tbody> renderer.
// Owns DOM: #auditThead and #auditTbody. Truncates body to first 5,000 rows.
// AUDIT_DAY_COLS / AUDIT_WEEK_COLS / AUDIT_MONTH_COLS are window globals owned
// by dashboard.html.

const HEAD_BG = 'background:var(--ink); color:var(--paper-3); font-size:10px; letter-spacing:.08em; text-transform:uppercase; font-weight:700; padding:10px 8px; border-bottom:2px solid var(--paper-5);';

function _cellPct(v, klass = '') {
  const cls = klass ? ` class="${klass}"` : '';
  if (v == null) return `<td${cls} style="padding:7px 8px; text-align:right; color:var(--paper-5);">—</td>`;
  const c  = v > 0 ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--paper-3)';
  const bg = v > 0 ? `background:color-mix(in oklch, var(--green) ${Math.min(20, Math.abs(v))}%, transparent);`
           : v < 0 ? `background:color-mix(in oklch, var(--red)   ${Math.min(20, Math.abs(v))}%, transparent);` : '';
  return `<td${cls} style="padding:7px 8px; text-align:right; color:${c}; font-weight:600; ${bg}">${v >= 0 ? '+' : ''}${v.toFixed(1)}</td>`;
}

export function renderHead() {
  const thead = document.getElementById('auditThead');
  if (!thead) return;
  const dayCols   = window.AUDIT_DAY_COLS   || [];
  const weekCols  = window.AUDIT_WEEK_COLS  || [];
  const monthCols = window.AUDIT_MONTH_COLS || [];
  thead.innerHTML = `
    <tr>
      <th style="${HEAD_BG}; text-align:left; min-width:60px; position:sticky; left:0; background:var(--ink);">Ticker</th>
      <th style="${HEAD_BG}; text-align:left; min-width:80px;">Mode</th>
      <th style="${HEAD_BG}; text-align:left; min-width:90px;">Date</th>
      <th style="${HEAD_BG}; text-align:left; min-width:140px;">Setup</th>
      <th style="${HEAD_BG}; text-align:right; min-width:50px;">Score</th>
      <th style="${HEAD_BG}; text-align:right; min-width:70px;">Entry</th>
      <th style="${HEAD_BG}; text-align:center; min-width:70px;">Alert</th>
      <th style="${HEAD_BG}; text-align:right; min-width:70px;">Today</th>
      <th style="${HEAD_BG}; text-align:right; min-width:70px; color:var(--accent);">%Δ</th>
      ${dayCols.map(c   => `<th style="${HEAD_BG}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      ${weekCols.map(c  => `<th style="${HEAD_BG}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      ${monthCols.map(c => `<th style="${HEAD_BG}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      <th style="${HEAD_BG}; text-align:left; min-width:80px;">Status</th>
    </tr>
  `;
}

export function renderBody(filtered) {
  const tbody = document.getElementById('auditTbody');
  if (!tbody) return;
  const dayCols   = window.AUDIT_DAY_COLS   || [];
  const weekCols  = window.AUDIT_WEEK_COLS  || [];
  const monthCols = window.AUDIT_MONTH_COLS || [];

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="26" style="padding:30px; text-align:center; color:var(--paper-3); font-size:13px;">No signals match filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.slice(0, 5000).map(s => {
    const pctNowColor  = s.pct_now == null ? 'var(--paper-5)' : s.pct_now > 0 ? 'var(--green)' : s.pct_now < 0 ? 'var(--red)' : 'var(--paper-3)';
    const statusColor  = s.status === 'OPEN' ? 'var(--accent)' : s.status === 'CLOSED' ? 'var(--paper-3)' : s.status === 'TARGET_HIT' ? 'var(--green)' : s.status === 'STOPPED' ? 'var(--red)' : 'var(--paper-3)';
    const verdict      = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    const verdictColor = verdict === 'BUY' ? 'var(--green)' : verdict === 'WATCH' ? 'var(--accent)' : verdict === 'SHORT' ? 'var(--red)' : 'var(--paper-3)';
    const ent          = s.entry_price || 0;
    const mode         = s.mode || 'Swing';
    const modeColor    = mode === 'Swing' ? 'var(--accent)' : mode === 'Position' ? 'var(--info)' : mode === 'Invest' ? 'var(--green)' : 'var(--paper-3)';
    const rowKey       = `${s.ticker}__${s.date}__${mode}`;
    return `
      <tr data-ticker="${s.ticker}" data-entry="${ent}" data-date="${s.date || ''}" data-rowkey="${rowKey}" class="audit-row" style="border-bottom:1px dashed var(--line); cursor:pointer;" onclick="auditToggleExpand('${rowKey}', event)" onmouseover="this.style.background='var(--surf-elev)'" onmouseout="this.style.background=''">
        <td style="padding:7px 8px; font-weight:700; color:var(--paper); position:sticky; left:0; background:var(--surf-card);"><a href="#" onclick="event.stopPropagation(); window.setDetailTicker && window.setDetailTicker('${s.ticker}'); return false;" style="color:var(--paper); text-decoration:none;">${s.ticker || '—'}</a>${s.is_elite ? ` <span title="Elite pick · #${s.elite_rank}/5 · ${s.elite_score}/100" style="color:var(--accent);font-weight:800;font-size:10px;margin-left:3px">⌬${s.elite_score?.toFixed(0) || '?'}</span>` : ''} <span class="audit-row-arrow" style="color:var(--paper-4); font-size:10px; margin-left:4px; transition:transform 0.15s ease; display:inline-block;">▶</span></td>
        <td style="padding:7px 8px;"><span style="display:inline-block; padding:2px 8px; border-radius:3px; background:color-mix(in oklch, ${modeColor} 14%, transparent); color:${modeColor}; border:1px solid color-mix(in oklch, ${modeColor} 40%, transparent); font-weight:700; font-size:10px; letter-spacing:0.06em;">${mode}</span></td>
        <td style="padding:7px 8px; color:var(--paper-2);">${s.date || '—'}</td>
        <td style="padding:7px 8px; color:var(--paper-2);">${(s.strategy || '—').slice(0, 22)}</td>
        <td style="padding:7px 8px; text-align:right; color:var(--paper); font-weight:600;">${s.score || '—'}</td>
        <td style="padding:7px 8px; text-align:right; color:var(--paper);">$${ent.toFixed(2)}</td>
        <td style="padding:7px 8px; text-align:center;"><span style="display:inline-block; padding:2px 8px; border-radius:3px; background:color-mix(in oklch, ${verdictColor} 18%, transparent); color:${verdictColor}; border:1px solid ${verdictColor}; font-weight:700; font-size:10px; letter-spacing:0.06em;">${verdict}</span></td>
        <td class="audit-today" style="padding:7px 8px; text-align:right; color:var(--paper);">${s.today != null ? '$' + s.today.toFixed(2) : '—'}</td>
        <td class="audit-pctnow" style="padding:7px 8px; text-align:right; color:${pctNowColor}; font-weight:800; font-size:12.5px;">${s.pct_now != null ? (s.pct_now >= 0 ? '+' : '') + s.pct_now.toFixed(1) + '%' : '—'}</td>
        ${dayCols.map((c, i) => _cellPct(s[`${c}_pct`], `audit-d${i+1}-pct`)).join('')}
        ${weekCols.map(c     => _cellPct(s[`${c}_pct`])).join('')}
        ${monthCols.map(c    => _cellPct(s[`${c}_pct`])).join('')}
        <td style="padding:7px 8px; color:${statusColor}; font-size:10px; font-weight:700; letter-spacing:0.05em;">${s.status || 'OPEN'}</td>
      </tr>
    `;
  }).join('');

  if (filtered.length > 5000) {
    tbody.innerHTML += `<tr><td colspan="26" style="padding:14px; text-align:center; color:var(--paper-3); font-size:12px;">Showing first 5,000 of ${filtered.length.toLocaleString()} — narrow filters to see more.</td></tr>`;
  }
}
