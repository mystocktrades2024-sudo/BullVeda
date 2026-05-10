// tabs/audit/audit.js — Audit tab renderer.
//
// Extracted from dashboard.html:7947-8132 (2026-05-09).
// Helpers (_auditLivePoll, _tradingDaysSince, auditToggleExpand,
// _renderAuditDetailPanel, AUDIT_*_COLS) STAY in dashboard.html — they're
// referenced via inline onclick handlers and the polling timer is global.
// Module's dispose() clears the poll interval to prevent leaks across tab
// switches.

import { getData } from '../../core/shared.js';

const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

export function render() {
  const DATA = getData();
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];

  // Populate filter dropdowns once
  if (!window._auditFiltersInit) {
    window._auditFiltersInit = true;
    const monthSel = document.getElementById('auditFilterMonth');
    const stratSel = document.getElementById('auditFilterStrategy');
    const months = new Set(), strats = new Set();
    trail.forEach(s => {
      if (s.date) months.add(s.date.slice(0, 7));
      if (s.strategy) strats.add(s.strategy);
    });
    [...months].sort().reverse().forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      monthSel && monthSel.appendChild(opt);
    });
    [...strats].sort().forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      stratSel && stratSel.appendChild(opt);
    });
  }

  const fSym = (document.getElementById('auditFilterSymbol').value || '').trim().toUpperCase();
  const fFrom = document.getElementById('auditFilterDateFrom').value;
  const fTo = document.getElementById('auditFilterDateTo').value;
  const fMonth = document.getElementById('auditFilterMonth').value;
  const fStatus = document.getElementById('auditFilterStatus').value;
  const fVerdict = (document.getElementById('auditFilterVerdict') || {value:''}).value;
  const fPnl = document.getElementById('auditFilterPnl').value;
  const fMode = document.getElementById('auditFilterMode')?.value || '';
  const fRegime = document.getElementById('auditFilterRegime')?.value || '';
  const fConviction = document.getElementById('auditFilterConviction')?.value || '';
  const fExit = document.getElementById('auditFilterExitReason')?.value || '';
  const fElite = document.getElementById('auditFilterElite')?.value || '';
  const fStrat = document.getElementById('auditFilterStrategy').value;

  const filtered = trail.filter(s => {
    const verdict = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    if (fSym && !(s.ticker || '').toUpperCase().includes(fSym)) return false;
    if (fFrom && (s.date || '') < fFrom) return false;
    if (fTo && (s.date || '') > fTo) return false;
    if (fMonth && !(s.date || '').startsWith(fMonth)) return false;
    if (fStatus && (s.status || '').toUpperCase() !== fStatus) return false;
    if (fVerdict && verdict !== fVerdict) return false;
    if (fStrat && s.strategy !== fStrat) return false;
    if (fMode && (s.mode || 'Swing') !== fMode) return false;
    if (fRegime && (s.regime4 || '') !== fRegime) return false;
    if (fConviction && (s.conviction_label || '') !== fConviction) return false;
    if (fExit) {
      if (fExit === 'open' && s.status !== 'OPEN') return false;
      if (fExit !== 'open' && (s.exit_reason || '') !== fExit) return false;
    }
    if (fElite === 'elite' && !s.is_elite) return false;
    if (fElite === 'non_elite' && s.is_elite) return false;
    if (fPnl) {
      const p = s.pct_now;
      if (p == null) return false;
      if (fPnl === 'gain' && p <= 0) return false;
      if (fPnl === 'loss' && p >= 0) return false;
      if (fPnl === 'big-gain' && p < 10) return false;
      if (fPnl === 'big-loss' && p > -10) return false;
    }
    return true;
  });

  setText('auditMeta', `${filtered.length} of ${trail.length} signals shown`);
  setText('fsAuditCt', trail.length);
  setText('sbAuditCt', trail.length);

  const hasWatchOrShort = trail.some(s => s.verdict === 'WATCH' || s.verdict === 'SHORT');
  const notice = document.getElementById('auditCoverageNotice');
  if (notice) notice.style.display = (trail.length > 0 && !hasWatchOrShort) ? 'block' : 'none';

  const enriched = filtered.filter(s => s.pct_now != null);
  const avgPct = enriched.length ? enriched.reduce((a,b) => a + b.pct_now, 0) / enriched.length : 0;
  const winCount = enriched.filter(s => s.pct_now > 0).length;
  const wrPct = enriched.length ? (winCount / enriched.length) * 100 : 0;
  const best = enriched.length ? enriched.reduce((a,b) => b.pct_now > a.pct_now ? b : a) : null;
  const worst = enriched.length ? enriched.reduce((a,b) => b.pct_now < a.pct_now ? b : a) : null;
  const pctByVerdict = { BUY: { sum: 0, n: 0 }, WATCH: { sum: 0, n: 0 }, SHORT: { sum: 0, n: 0 } };
  enriched.forEach(s => {
    const v = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    if (pctByVerdict[v]) { pctByVerdict[v].sum += s.pct_now; pctByVerdict[v].n++; }
  });
  const avgFor = (v) => v.n ? (v.sum / v.n) : null;
  const fmtPct = (p) => p == null ? '—' : (p >= 0 ? '+' : '') + p.toFixed(2) + '%';
  document.getElementById('auditSummary').innerHTML = `
    <div class="stat-tile ${avgPct >= 0 ? 'ok' : 'bad'}"><div class="lbl">Avg % Return (Live)</div><div class="v" style="font-family:var(--mono); color:${avgPct >= 0 ? 'var(--green)' : 'var(--red)'};">${fmtPct(avgPct)}</div><div class="sub">${enriched.length} signals · ${wrPct.toFixed(0)}% positive</div></div>
    <div class="stat-tile"><div class="lbl">Avg % By Alert Type</div><div class="v" style="font-size:12px; line-height:1.5; font-family:var(--mono);">
      <div><span style="color:var(--green); font-weight:700;">${fmtPct(avgFor(pctByVerdict.BUY))}</span> <span style="color:var(--paper-3); font-size:10px;">BUY · ${pctByVerdict.BUY.n}</span></div>
      <div><span style="color:var(--accent); font-weight:700;">${fmtPct(avgFor(pctByVerdict.WATCH))}</span> <span style="color:var(--paper-3); font-size:10px;">WATCH · ${pctByVerdict.WATCH.n}</span></div>
      <div><span style="color:var(--red); font-weight:700;">${fmtPct(avgFor(pctByVerdict.SHORT))}</span> <span style="color:var(--paper-3); font-size:10px;">SHORT · ${pctByVerdict.SHORT.n}</span></div>
    </div><div class="sub">${pctByVerdict.WATCH.n === 0 && pctByVerdict.SHORT.n === 0 ? 'WATCH/SHORT after next scan' : 'across alert types'}</div></div>
    <div class="stat-tile ok"><div class="lbl">Best Signal</div><div class="v" style="font-size:15px;color:var(--green); font-family:var(--mono);">${best ? best.ticker : '—'}<br><span style="font-size:13px;">${best ? fmtPct(best.pct_now) : ''}</span></div><div class="sub">${best ? best.date + ' · ' + (best.mode || 'Swing') : ''}</div></div>
    <div class="stat-tile bad"><div class="lbl">Worst Signal</div><div class="v" style="font-size:15px;color:var(--red); font-family:var(--mono);">${worst ? worst.ticker : '—'}<br><span style="font-size:13px;">${worst ? fmtPct(worst.pct_now) : ''}</span></div><div class="sub">${worst ? worst.date + ' · ' + (worst.mode || 'Swing') : ''}</div></div>
  `;

  const thead = document.getElementById('auditThead');
  const headBg = 'background:var(--ink); color:var(--paper-3); font-size:10px; letter-spacing:.08em; text-transform:uppercase; font-weight:700; padding:10px 8px; border-bottom:2px solid var(--paper-5);';
  const AUDIT_DAY_COLS   = window.AUDIT_DAY_COLS;
  const AUDIT_WEEK_COLS  = window.AUDIT_WEEK_COLS;
  const AUDIT_MONTH_COLS = window.AUDIT_MONTH_COLS;
  thead.innerHTML = `
    <tr>
      <th style="${headBg}; text-align:left; min-width:60px; position:sticky; left:0; background:var(--ink);">Ticker</th>
      <th style="${headBg}; text-align:left; min-width:80px;">Mode</th>
      <th style="${headBg}; text-align:left; min-width:90px;">Date</th>
      <th style="${headBg}; text-align:left; min-width:140px;">Setup</th>
      <th style="${headBg}; text-align:right; min-width:50px;">Score</th>
      <th style="${headBg}; text-align:right; min-width:70px;">Entry</th>
      <th style="${headBg}; text-align:center; min-width:70px;">Alert</th>
      <th style="${headBg}; text-align:right; min-width:70px;">Today</th>
      <th style="${headBg}; text-align:right; min-width:70px; color:var(--accent);">%Δ</th>
      ${AUDIT_DAY_COLS.map(c => `<th style="${headBg}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      ${AUDIT_WEEK_COLS.map(c => `<th style="${headBg}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      ${AUDIT_MONTH_COLS.map(c => `<th style="${headBg}; text-align:right; min-width:60px; color:var(--paper-3);">${c}</th>`).join('')}
      <th style="${headBg}; text-align:left; min-width:80px;">Status</th>
    </tr>
  `;

  const tbody = document.getElementById('auditTbody');
  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="26" style="padding:30px; text-align:center; color:var(--paper-3); font-size:13px;">No signals match filters.</td></tr>`;
    return;
  }

  const cellPct = (v, klass = '') => {
    const cls = klass ? ` class="${klass}"` : '';
    if (v == null) return `<td${cls} style="padding:7px 8px; text-align:right; color:var(--paper-5);">—</td>`;
    const c = v > 0 ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--paper-3)';
    const bg = v > 0 ? `background:color-mix(in oklch, var(--green) ${Math.min(20, Math.abs(v))}%, transparent);`
             : v < 0 ? `background:color-mix(in oklch, var(--red) ${Math.min(20, Math.abs(v))}%, transparent);` : '';
    return `<td${cls} style="padding:7px 8px; text-align:right; color:${c}; font-weight:600; ${bg}">${v >= 0 ? '+' : ''}${v.toFixed(1)}</td>`;
  };

  tbody.innerHTML = filtered.slice(0, 5000).map(s => {
    const pctNowColor = s.pct_now == null ? 'var(--paper-5)' : s.pct_now > 0 ? 'var(--green)' : s.pct_now < 0 ? 'var(--red)' : 'var(--paper-3)';
    const statusColor = s.status === 'OPEN' ? 'var(--accent)' : s.status === 'CLOSED' ? 'var(--paper-3)' : s.status === 'TARGET_HIT' ? 'var(--green)' : s.status === 'STOPPED' ? 'var(--red)' : 'var(--paper-3)';
    const verdict = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    const verdictColor = verdict === 'BUY' ? 'var(--green)' : verdict === 'WATCH' ? 'var(--accent)' : verdict === 'SHORT' ? 'var(--red)' : 'var(--paper-3)';
    const ent = s.entry_price || 0;
    const mode = s.mode || 'Swing';
    const modeColor = mode === 'Swing' ? 'var(--accent)' : mode === 'Position' ? 'var(--info)' : mode === 'Invest' ? 'var(--green)' : 'var(--paper-3)';
    const rowKey = `${s.ticker}__${s.date}__${mode}`;
    return `
      <tr data-ticker="${s.ticker}" data-entry="${ent}" data-date="${s.date || ''}" data-rowkey="${rowKey}" class="audit-row" style="border-bottom:1px dashed var(--line); cursor:pointer;" onclick="auditToggleExpand('${rowKey}', event)" onmouseover="this.style.background='var(--surf-elev)'" onmouseout="this.style.background=''">
        <td style="padding:7px 8px; font-weight:700; color:var(--paper); position:sticky; left:0; background:var(--surf-card);"><a href="elite-detail.html?t=${s.ticker}" onclick="event.stopPropagation()" style="color:var(--paper); text-decoration:none;">${s.ticker || '—'}</a>${s.is_elite ? ` <span title="Elite pick · #${s.elite_rank}/5 · ${s.elite_score}/100" style="color:var(--accent);font-weight:800;font-size:10px;margin-left:3px">⌬${s.elite_score?.toFixed(0) || '?'}</span>` : ''} <span class="audit-row-arrow" style="color:var(--paper-4); font-size:10px; margin-left:4px; transition:transform 0.15s ease; display:inline-block;">▶</span></td>
        <td style="padding:7px 8px;"><span style="display:inline-block; padding:2px 8px; border-radius:3px; background:color-mix(in oklch, ${modeColor} 14%, transparent); color:${modeColor}; border:1px solid color-mix(in oklch, ${modeColor} 40%, transparent); font-weight:700; font-size:10px; letter-spacing:0.06em;">${mode}</span></td>
        <td style="padding:7px 8px; color:var(--paper-2);">${s.date || '—'}</td>
        <td style="padding:7px 8px; color:var(--paper-2);">${(s.strategy || '—').slice(0, 22)}</td>
        <td style="padding:7px 8px; text-align:right; color:var(--paper); font-weight:600;">${s.score || '—'}</td>
        <td style="padding:7px 8px; text-align:right; color:var(--paper);">$${ent.toFixed(2)}</td>
        <td style="padding:7px 8px; text-align:center;"><span style="display:inline-block; padding:2px 8px; border-radius:3px; background:color-mix(in oklch, ${verdictColor} 18%, transparent); color:${verdictColor}; border:1px solid ${verdictColor}; font-weight:700; font-size:10px; letter-spacing:0.06em;">${verdict}</span></td>
        <td class="audit-today" style="padding:7px 8px; text-align:right; color:var(--paper);">${s.today != null ? '$' + s.today.toFixed(2) : '—'}</td>
        <td class="audit-pctnow" style="padding:7px 8px; text-align:right; color:${pctNowColor}; font-weight:800; font-size:12.5px;">${s.pct_now != null ? (s.pct_now >= 0 ? '+' : '') + s.pct_now.toFixed(1) + '%' : '—'}</td>
        ${AUDIT_DAY_COLS.map((c, i) => cellPct(s[`${c}_pct`], `audit-d${i+1}-pct`)).join('')}
        ${AUDIT_WEEK_COLS.map(c => cellPct(s[`${c}_pct`])).join('')}
        ${AUDIT_MONTH_COLS.map(c => cellPct(s[`${c}_pct`])).join('')}
        <td style="padding:7px 8px; color:${statusColor}; font-size:10px; font-weight:700; letter-spacing:0.05em;">${s.status || 'OPEN'}</td>
      </tr>
    `;
  }).join('');

  if (filtered.length > 5000) {
    tbody.innerHTML += `<tr><td colspan="26" style="padding:14px; text-align:center; color:var(--paper-3); font-size:12px;">Showing first 5,000 of ${filtered.length.toLocaleString()} — narrow filters to see more.</td></tr>`;
  }

  if (typeof window._auditLivePoll === 'function') window._auditLivePoll();
}

export function dispose() { /* no-op — _auditPollIntervalId is module-private in dashboard.html. Existing behavior leaves the poller running across tab switches; matches pre-extraction behavior. */ }


// ─── Helpers folded from dashboard.html (CapStudio sub-helpers fold 2026-05-09) ───
async function _auditLivePoll() {
  try {
    const tbody = document.getElementById('auditTbody');
    if (!tbody) return;
    const rows = [...tbody.querySelectorAll('tr[data-ticker]')];
    if (rows.length === 0) return;

    // Two pools of tickers:
    //   1. Recent rows (entry within last 7 trading days) — ALWAYS update,
    //      because their D1-D5 cells are still actively being filled.
    //   2. The first 100 visible rows that aren't already in pool 1 —
    //      keeps the visible-area Today + %Δ cells live for browsing.
    // Combined cap: 250 tickers per poll, chunked into 2 requests of 125
    // to stay under Schwab's batch quote limit.
    const recentTickers = new Set();
    const otherTickers = [];
    rows.forEach(row => {
      const t = row.dataset.ticker;
      if (!t) return;
      const date = row.dataset.date;  // YYYY-MM-DD entry date
      const tdSince = _tradingDaysSince(date);
      if (tdSince != null && tdSince <= 7) {
        recentTickers.add(t);
      } else if (otherTickers.length < 100 && !recentTickers.has(t)) {
        otherTickers.push(t);
      }
    });
    const tickers = [...new Set([...recentTickers, ...otherTickers])].slice(0, 250);
    if (tickers.length === 0) return;

    // Chunk into 125-ticker batches to fit Schwab batch limits
    const CHUNK = 125;
    const batches = [];
    for (let i = 0; i < tickers.length; i += CHUNK) {
      batches.push(tickers.slice(i, i + CHUNK));
    }
    const results = await Promise.all(batches.map(batch =>
      fetch(`/api/live/quote?tickers=${batch.join(',')}`, { signal: AbortSignal.timeout(6000) })
        .then(r => r.ok ? r.json() : null)
        .catch(() => null)
    ));
    const prices = {};
    let source = 'unknown';
    for (const d of results) {
      if (!d) continue;
      Object.assign(prices, d.prices || {});
      if (d.source) source = d.source;
    }

    rows.forEach(row => {
      const t = row.dataset.ticker;
      const entry = parseFloat(row.dataset.entry || 0);
      const px = prices[t];
      if (px == null || !entry) return;
      const pct = (px / entry - 1) * 100;
      const c = pct > 0 ? 'var(--green)' : pct < 0 ? 'var(--red)' : 'var(--paper-3)';

      // Update Today + pct_now
      const todayCell = row.querySelector('.audit-today');
      const pctCell = row.querySelector('.audit-pctnow');
      if (todayCell) todayCell.textContent = '$' + px.toFixed(2);
      if (pctCell) {
        pctCell.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
        pctCell.style.color = c;
      }

      // Synthesize the right DN_pct cell from live price. For a signal that
      // entered N trading days ago, today's price IS the DN close. Without
      // this, parquet-only enrichment leaves DN blank until the EOD archive
      // catches up overnight.
      const tdSince = _tradingDaysSince(row.dataset.date);
      if (tdSince != null && tdSince >= 1 && tdSince <= 5) {
        const dCell = row.querySelector(`.audit-d${tdSince}-pct`);
        if (dCell) {
          dCell.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
          dCell.style.color = c;
          dCell.dataset.synthetic = '1';  // marker — debug
        }
      }
    });
    // Show source pill in audit meta
    const meta = document.getElementById('auditMeta');
    if (meta && source) {
      const srcLabel = source === 'schwab' ? '🟢 SCHWAB · LIVE' : source === 'eodhd' ? '🟡 EODHD · 15m' : source === 'cache' ? '🔘 CACHED' : source;
      const baseTxt = meta.textContent.split(' · ')[0];
      meta.textContent = `${baseTxt} · ${srcLabel} · ${recentTickers.size} recent`;
    }
  } catch (e) { /* silent */ }
}

function _tradingDaysSince(entryISO) {
  if (!entryISO) return null;
  const entry = new Date(entryISO + 'T00:00:00');
  const today = new Date();
  let n = 0;
  const cur = new Date(entry);
  while (cur < today) {
    cur.setDate(cur.getDate() + 1);
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) n++;  // skip Sat/Sun
  }
  return n;
}

function auditToggleExpand(rowKey, event) {
  if (event && (event.target.tagName === 'A' || event.target.closest('a'))) return;
  const tbody = document.getElementById('auditTbody');
  if (!tbody) return;
  const row = tbody.querySelector(`tr[data-rowkey="${rowKey}"]`);
  if (!row) return;
  const arrow = row.querySelector('.audit-row-arrow');

  // If already expanded — collapse
  const next = row.nextElementSibling;
  if (next && next.classList.contains('audit-expand')) {
    next.remove();
    if (arrow) arrow.style.transform = 'rotate(0deg)';
    return;
  }
  // Collapse any other open expand rows first
  tbody.querySelectorAll('tr.audit-expand').forEach(r => r.remove());
  tbody.querySelectorAll('.audit-row-arrow').forEach(a => { a.style.transform = 'rotate(0deg)'; });

  // Find signal data
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];
  const sig = trail.find(s => `${s.ticker}__${s.date}__${s.mode || 'Swing'}` === rowKey);
  if (!sig) return;

  const tr = document.createElement('tr');
  tr.className = 'audit-expand';
  tr.innerHTML = `<td colspan="100" style="padding:0; background:var(--ink); border-bottom:1px solid var(--paper-5);">
    ${_renderAuditDetailPanel(sig)}
  </td>`;
  row.after(tr);
  if (arrow) arrow.style.transform = 'rotate(90deg)';
}

function _renderAuditDetailPanel(s) {
  const fmt = (v, suffix='', dp=2) => v == null ? '<span style="color:var(--paper-4)">—</span>' : (typeof v === 'number' ? v.toFixed(dp) + suffix : v + suffix);
  const fmtPct = v => v == null ? '<span style="color:var(--paper-4)">—</span>' : `<span style="color:${v >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:700">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
  const fmtRMult = v => v == null ? '<span style="color:var(--paper-4)">—</span>' : `<span style="color:${v >= 1 ? 'var(--green)' : v >= 0 ? 'var(--accent)' : 'var(--red)'};font-weight:700">${v >= 0 ? '+' : ''}${v.toFixed(2)}R</span>`;
  const regimeColor = (r) => r === 'risk_on_trending' ? 'var(--green)' : r === 'risk_on_choppy' ? 'var(--accent)' : r === 'risk_off_trending' ? 'var(--warn)' : r === 'panic' ? 'var(--red)' : 'var(--paper-3)';
  const convColor = (c) => c === 'T1' ? 'var(--green)' : c === 'T2' ? 'var(--accent)' : c === 'T3' ? 'var(--warn)' : 'var(--paper-3)';
  const eqColor = (e) => e === 'FRESH' ? 'var(--green)' : e === 'PULLBACK' ? 'var(--accent)' : e === 'VALID' ? 'var(--accent)' : e === 'EXTENDED' ? 'var(--warn)' : 'var(--red)';
  const exitColor = (e) => e === 'target_hit' ? 'var(--green)' : e === 'stop_hit' ? 'var(--red)' : e && e.includes('time_stop') ? 'var(--warn)' : 'var(--paper-3)';

  const pill = (text, color) => text ? `<span style="display:inline-block;padding:2px 8px;border-radius:3px;background:color-mix(in oklch, ${color} 18%, transparent);color:${color};border:1px solid color-mix(in oklch, ${color} 45%, transparent);font-weight:700;font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;">${text}</span>` : '<span style="color:var(--paper-4)">—</span>';

  const cell = (label, val) => `<div style="padding:6px 0; border-bottom:1px dashed var(--paper-5); display:flex; justify-content:space-between; align-items:center; font-size:11.5px;"><span style="color:var(--paper-3); letter-spacing:0.04em;">${label}</span><span style="font-family:var(--mono); font-weight:600; color:var(--paper);">${val}</span></div>`;

  return `
    <div style="padding:18px 22px; background:linear-gradient(180deg, color-mix(in oklch, var(--accent) 4%, var(--ink)) 0%, var(--ink) 50%); border-left:3px solid var(--accent);">
      <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:24px;">

        <!-- 1. Regime context at signal time -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">REGIME @ SIGNAL</div>
          ${cell('Regime4', pill(s.regime4 || '—', regimeColor(s.regime4)))}
          ${cell('VIX', fmt(s.vix_at_signal, '', 1))}
          ${cell('HMM Bull', s.hmm_p_bull != null ? `<span style="color:var(--green)">${(s.hmm_p_bull*100).toFixed(0)}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('HMM Neutral', s.hmm_p_neutral != null ? `<span style="color:var(--accent)">${(s.hmm_p_neutral*100).toFixed(0)}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('HMM Bear', s.hmm_p_bear != null ? `<span style="color:var(--red)">${(s.hmm_p_bear*100).toFixed(0)}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
        </div>

        <!-- 2. Conviction + Setup -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">CONVICTION + SETUP</div>
          ${cell('Conviction', pill(s.conviction_label || '—', convColor(s.conviction_label)))}
          ${cell('Entry Quality', pill(s.entry_quality || '—', eqColor(s.entry_quality)))}
          ${cell('Setup Family', s.setup_family || s.strategy || '<span style="color:var(--paper-4)">—</span>')}
          ${cell('Stars', `${s.stars || 0}/5`)}
          ${cell('Tail Filter', s.tail_filter_demoted ? '<span style="color:var(--red);font-weight:800">✗ DEMOTED</span>' : '<span style="color:var(--green);font-weight:800">✓ CLEARED</span>')}
        </div>

        <!-- 3. Forward predictions (V-1 + V-3) -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">FORWARD PREDICTIONS</div>
          ${cell('MC P(profit)', s.mc_p_profit != null ? `<span style="color:${s.mc_p_profit >= 60 ? 'var(--green)' : s.mc_p_profit >= 45 ? 'var(--accent)' : 'var(--red)'}">${s.mc_p_profit}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('MC P(T1 first)', s.mc_p_target_first != null ? `<span style="color:var(--green)">${s.mc_p_target_first}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('MC P(stop first)', s.mc_p_stop_first != null ? `<span style="color:var(--red)">${s.mc_p_stop_first}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('VaR-95', s.fd_var_95_pct != null ? `<span style="color:var(--red)">${s.fd_var_95_pct}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('CVaR-97.5', s.fd_cvar_975_pct != null ? `<span style="color:var(--red)">${s.fd_cvar_975_pct}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
        </div>

        <!-- 4. Outcome (when closed) + alpha vs SPY -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">OUTCOME ${s.status === 'CLOSED' ? '· CLOSED' : '· OPEN'}</div>
          ${cell('Exit Reason', pill(s.exit_reason || (s.status === 'OPEN' ? 'still open' : '—'), exitColor(s.exit_reason)))}
          ${cell('Days to T1', fmt(s.days_to_first_target_hit, 'd', 0))}
          ${cell('Days to Stop', fmt(s.days_to_stop_hit, 'd', 0))}
          ${cell('Realized R', fmtRMult(s.actual_r_multiple))}
          ${cell('SPY return', fmtPct(s.spy_return_over_hold))}
          ${cell('Alpha vs SPY', s.alpha_vs_spy != null ? `<span style="color:${s.alpha_vs_spy > 0 ? 'var(--green)' : s.alpha_vs_spy < 0 ? 'var(--red)' : 'var(--paper-3)'};font-weight:800">${s.alpha_vs_spy >= 0 ? '+' : ''}${s.alpha_vs_spy}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
        </div>

      </div>

      ${s.live ? `<div style="margin-top:14px; padding:8px 12px; background:color-mix(in oklch, var(--accent) 12%, transparent); border:1px solid color-mix(in oklch, var(--accent) 35%, transparent); border-radius:4px; font-size:11.5px; color:var(--paper-2); display:flex; align-items:center; gap:8px;">
        <span style="color:var(--accent); font-weight:800;">●  LIVE</span>
        <span>This pick is from today's bundle — not yet persisted to <code style="color:var(--accent)">signal_log.json</code>. Will be logged next time <code style="color:var(--accent)">swing_trade.py</code> runs.</span>
      </div>` : ''}

      <div style="margin-top:12px; display:flex; gap:8px; align-items:center; font-size:11px; color:var(--paper-3);">
        <span>Trade plan:</span>
        <span style="color:var(--paper-2)">Entry <b style="color:var(--paper)">$${(s.entry_price||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">Stop <b style="color:var(--red)">$${(s.stop||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">T1 <b style="color:var(--green)">$${(s.target1||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">R:R <b style="color:var(--paper)">1:${(s.rr||0).toFixed(1)}</b></span>
        <span style="margin-left:auto;">
          <a href="elite-detail.html?t=${s.ticker}" style="color:var(--accent); text-decoration:none; font-weight:700;">Open Full Analysis →</a>
        </span>
      </div>
    </div>
  `;
}

function _startAuditPolling() {
  if (_auditPollIntervalId) return;
  _auditPollIntervalId = setInterval(() => {
    if (document.visibilityState !== 'hidden') _auditLivePoll();
  }, 5000);
}

function auditClearFilters() {
  ['auditFilterSymbol','auditFilterDateFrom','auditFilterDateTo'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['auditFilterMonth','auditFilterVerdict','auditFilterStatus','auditFilterPnl','auditFilterMode','auditFilterRegime','auditFilterConviction','auditFilterExitReason','auditFilterElite','auditFilterStrategy'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  renderAudit();
}

function auditExportCsv() {
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];
  const cols = ['ticker','mode','date','strategy','verdict','score','entry_price','today','pct_now',
    ...AUDIT_DAY_COLS.map(c => c+'_pct'),
    ...AUDIT_WEEK_COLS.map(c => c+'_pct'),
    ...AUDIT_MONTH_COLS.map(c => c+'_pct'),
    'status'];
  const csv = [cols.join(',')]
    .concat(trail.map(s => cols.map(c => {
      if (c === 'mode') return `"${s.mode || 'Swing'}"`;
      if (c === 'verdict') {
        return s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
      }
      return s[c] != null ? `"${s[c]}"` : '';
    }).join(',')))
    .join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `audit_trail_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

function auditPresetRange(days) {
  const today = new Date();
  const past = new Date(today.getTime() - days * 86400000);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('auditFilterDateFrom').value = fmt(past);
  document.getElementById('auditFilterDateTo').value = fmt(today);
  _markPresetActive(days + 'd');
  renderAudit();
}

function auditPresetYtd() {
  const today = new Date();
  const ytd = new Date(today.getFullYear(), 0, 1);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('auditFilterDateFrom').value = fmt(ytd);
  document.getElementById('auditFilterDateTo').value = fmt(today);
  _markPresetActive('YTD');
  renderAudit();
}

function auditPresetAll() {
  document.getElementById('auditFilterDateFrom').value = '';
  document.getElementById('auditFilterDateTo').value = '';
  _markPresetActive('All');
  renderAudit();
}

function _markPresetActive(label) {
  document.querySelectorAll('.audit-preset').forEach(b => {
    b.classList.toggle('on', b.textContent.trim() === label);
  });
}


// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window._auditLivePoll = _auditLivePoll;
  window._tradingDaysSince = _tradingDaysSince;
  window.auditToggleExpand = auditToggleExpand;
  window._renderAuditDetailPanel = _renderAuditDetailPanel;
  window._startAuditPolling = _startAuditPolling;
  window.auditClearFilters = auditClearFilters;
  window.auditExportCsv = auditExportCsv;
  window.auditPresetRange = auditPresetRange;
  window.auditPresetYtd = auditPresetYtd;
  window.auditPresetAll = auditPresetAll;
  window._markPresetActive = _markPresetActive;
}


// Auto-start the polling interval on module load (was a top-level call in
// dashboard.html; moved here to fire after the helper is defined).
if (typeof _startAuditPolling === 'function') {
  try { _startAuditPolling(); } catch (e) { console.warn('[audit] _startAuditPolling failed:', e); }
}
