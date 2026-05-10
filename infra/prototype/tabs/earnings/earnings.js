// tabs/earnings/earnings.js — Earnings watchlist tab.
// Extracted from dashboard.html:5792-6048 (2026-05-09).
// _earnFilters state and _earnSearch/_earnFilterChange handlers stay in
// dashboard.html (referenced by inline onchange/oninput in the rendered HTML).

import { getData } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('earnBody');
  const meta = document.getElementById('earnMeta');
  if (!body) return;
  const wl = (DATA && DATA.earnings_watchlist) || [];
  const meta_d = (DATA && DATA.earnings_watchlist_meta) || {};
  const outcomes = (DATA && DATA.earnings_outcomes_30d) || [];
  const F = window._earnFilters;
  if (!wl.length) {
    body.innerHTML = `
      <div style="padding:32px 28px; text-align:center; color:var(--ink-2); border:1px dashed var(--rule); border-radius:8px;">
        <div style="font-size:13px; font-weight:600; margin-bottom:6px;">Earnings watchlist not built yet.</div>
        <div style="font-size:11px; color:var(--ink-3); line-height:1.6;">Run <code style="font-family:var(--mono); background:var(--bg-3); padding:1px 5px; border-radius:3px;">python3 build_earnings_watchlist.py</code> or wait for the 5:30am PT cron.</div>
      </div>`;
    if (meta) meta.textContent = '0 entries';
    return;
  }

  const myPositions = new Set();
  try {
    const ps = (DATA && DATA.portfolio && DATA.portfolio.positions) || [];
    ps.forEach(p => { if (p.status === 'OPEN') myPositions.add((p.ticker || '').toUpperCase()); });
  } catch (_) {}

  const tickerData = {};
  for (const sec of ['short_term','medium_term','long_term']) {
    for (const r of (DATA[sec] || [])) {
      if (r.ticker && !tickerData[r.ticker]) tickerData[r.ticker] = r;
    }
  }

  const beatByT = {};
  for (const p of (DATA.earnings_beat_predictions || [])) {
    if (p.ticker) beatByT[p.ticker] = p;
  }

  const beatStats = {};
  outcomes.forEach(o => {
    const t = o.ticker;
    if (!beatStats[t]) beatStats[t] = {beats: 0, misses: 0, inline: 0, total: 0};
    beatStats[t].total++;
    if (o.beat === 'BEAT') beatStats[t].beats++;
    else if (o.beat === 'MISS') beatStats[t].misses++;
    else beatStats[t].inline++;
  });

  const inPortfolio = wl.filter(e => myPositions.has(e.ticker)).length;
  const totalUS = wl.length;

  const sectorSet = new Set();
  wl.forEach(e => {
    const sec = (tickerData[e.ticker] || {}).sector;
    if (sec && sec !== 'Unknown') sectorSet.add(sec);
  });
  const sectors = [...sectorSet].sort();

  let filtered = wl.filter(e => {
    if (F.days !== 'all' && e.days_to_earnings > parseInt(F.days, 10)) return false;
    const td = tickerData[e.ticker] || {};
    const v = (td.verdict || td.stage || '').toUpperCase();
    if (F.verdict === 'BUY' && v !== 'BUY') return false;
    if (F.verdict === 'WATCH' && v !== 'WATCH') return false;
    if (F.verdict === 'has_signal' && !v) return false;
    if (F.ownership === 'owned' && !myPositions.has(e.ticker)) return false;
    if (F.sector !== 'all' && td.sector !== F.sector) return false;
    const bp = beatByT[e.ticker];
    if (F.beat === 'STRONG' && (!bp || bp.tier !== 'STRONG')) return false;
    if (F.beat === 'SOLID' && (!bp || !['STRONG','SOLID'].includes(bp.tier))) return false;
    if (F.beat === 'has_pred' && !bp) return false;
    if (F.search && !e.ticker.includes(F.search)) return false;
    return true;
  });

  if (F.sort === 'score') {
    filtered.sort((a, b) => ((tickerData[b.ticker] || {}).score || 0) - ((tickerData[a.ticker] || {}).score || 0));
  } else if (F.sort === 'ticker') {
    filtered.sort((a, b) => a.ticker.localeCompare(b.ticker));
  } else if (F.sort === 'beat') {
    filtered.sort((a, b) => ((beatByT[b.ticker] || {}).beat_score || 0) - ((beatByT[a.ticker] || {}).beat_score || 0));
  } else {
    filtered.sort((a, b) => a.days_to_earnings - b.days_to_earnings || a.ticker.localeCompare(b.ticker));
  }

  if (meta) meta.textContent = `${filtered.length} of ${totalUS} reporting · ${meta_d.from_date} → ${meta_d.to_date}` +
                                (inPortfolio > 0 ? ` · ⚠ ${inPortfolio} owned` : '');
  const sb = document.getElementById('sbEarnCt'); if (sb) sb.textContent = totalUS;
  const fs = document.getElementById('fsEarnCt'); if (fs) fs.textContent = totalUS;

  const fmtPx = v => v == null || isNaN(v) ? '—' : Number(v).toFixed(2);
  const rows = filtered.map(e => {
    const t = e.ticker;
    const td = tickerData[t] || {};
    const ownsTag = myPositions.has(t)
      ? `<span style="background:var(--fail);color:#fff;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700;">⚠ OWNED</span>` : '';
    const when = e.before_after_market === 'BeforeMarket' ? 'BMO'
              : e.before_after_market === 'AfterMarket' ? 'AMC' : '—';
    const days = e.days_to_earnings;
    const daysStyle = days <= 1 ? 'color:var(--fail);font-weight:700'
                    : days <= 3 ? 'color:var(--warn);font-weight:700'
                    : days <= 5 ? 'color:var(--accent)' : 'color:var(--ink-2)';
    const setup = td.setup_family || td.setup || '';
    const score = td.score != null ? td.score.toFixed(0) : '—';
    const verdict = td.verdict || td.stage || '';
    const verdictColor = verdict === 'BUY' ? 'var(--green)' : verdict === 'WATCH' ? 'var(--accent)' : 'var(--ink-3)';
    const sector = td.sector || '—';
    const stats = beatStats[t];
    const beatTag = stats && stats.total > 0
      ? `<span style="color:var(--ink-3);font-size:10px;" title="${stats.total} prior reports">${stats.beats}B/${stats.misses}M/${stats.inline}I</span>`
      : '<span style="color:var(--ink-3);font-size:10px;">—</span>';

    const bp = beatByT[t] || {};
    const bs = bp.beat_score;
    const tier = bp.tier;
    let beatScoreCell;
    if (bs == null) {
      beatScoreCell = '<span style="color:var(--ink-3);font-size:10px">—</span>';
    } else {
      const tColor = tier === 'STRONG' ? 'var(--green)'
                  : tier === 'SOLID' ? 'var(--accent)'
                  : tier === 'MODERATE' ? 'var(--ink-1)' : 'var(--ink-3)';
      const tooltip = bp.breakdown
        ? `H${bp.breakdown.historical?.pts || 0}/Run${bp.breakdown.runup_10d?.pts || 0}/Vol${bp.breakdown.vol_accum?.pts || 0}/An${bp.breakdown.analyst_upside?.pts || 0}/Op${bp.breakdown.options?.pts || 0}/Sec${bp.breakdown.sector_beats?.pts || 0}` : '';
      const tierIcon = tier === 'STRONG' ? '🎯 ' : '';
      beatScoreCell = `<span style="color:${tColor};font-weight:700;font-size:11.5px;" title="${tooltip}">${tierIcon}${bs.toFixed(0)}</span>`;
    }
    return `
      <tr style="border-bottom:1px solid var(--rule);">
        <td style="padding:8px 12px;font-family:var(--mono);font-weight:700;">
          <a href="elite-detail.html?t=${encodeURIComponent(t)}" style="color:var(--ink-0);text-decoration:none;">${t}</a> ${ownsTag}
        </td>
        <td style="padding:8px 12px;${daysStyle};font-family:var(--mono);">${days}d</td>
        <td style="padding:8px 12px;color:var(--ink-2);">${e.report_date}</td>
        <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${when}</td>
        <td style="padding:8px 12px;text-align:center;">${score !== '—' ? `<b>${score}</b>` : '<span style="color:var(--ink-3)">—</span>'}</td>
        <td style="padding:8px 12px;text-align:center;">
          ${verdict ? `<span style="color:${verdictColor};font-weight:700;font-size:10px;">${verdict}</span>` : '<span style="color:var(--ink-3)">—</span>'}
        </td>
        <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${setup}</td>
        <td style="padding:8px 12px;text-align:right;font-family:var(--mono);">${e.estimate != null ? fmtPx(e.estimate) : '—'}</td>
        <td style="padding:8px 12px;text-align:center;">${beatTag}</td>
        <td style="padding:8px 12px;text-align:center;">${beatScoreCell}</td>
        <td style="padding:8px 12px;color:var(--ink-2);font-size:11px;">${sector.slice(0, 24)}</td>
      </tr>`;
  }).join('');

  const strongPicks = (DATA.earnings_beat_predictions || []).filter(p => p.tier === 'STRONG');
  const solidPicks = (DATA.earnings_beat_predictions || []).filter(p => p.tier === 'SOLID');
  const strongBanner = strongPicks.length > 0 ? `
    <div style="margin-bottom:14px;padding:14px 18px;background:linear-gradient(90deg, color-mix(in oklch, var(--green) 18%, var(--bg-1)) 0%, var(--bg-1) 70%);border:1px solid var(--green);border-left:4px solid var(--green);border-radius:8px;">
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
        <span style="font-size:18px;">🎯</span>
        <div style="flex:1;min-width:200px;">
          <div style="font-weight:700;color:var(--green);font-size:13px;letter-spacing:0.04em;">${strongPicks.length} STRONG beat-prediction${strongPicks.length>1?'s':''}</div>
          <div style="color:var(--ink-2);font-size:11.5px;margin-top:3px;">
            ${strongPicks.map(p => `<a href="elite-detail.html?t=${p.ticker}" style="color:var(--ink-0);text-decoration:none;font-weight:700;">${p.ticker}</a>(${p.beat_score.toFixed(0)}, ${p.days_to_earnings}d)`).join(' · ')}
          </div>
        </div>
        <button onclick="_earnFilterChange('beat','STRONG')" style="padding:7px 14px;background:var(--green);border:none;border-radius:5px;color:var(--bg-0);font-weight:700;cursor:pointer;font-family:DM Sans;font-size:11px;letter-spacing:0.06em;">FILTER →</button>
      </div>
    </div>` : (solidPicks.length > 0 ? `
    <div style="margin-bottom:14px;padding:12px 16px;background:color-mix(in oklch, var(--accent) 10%, var(--bg-1));border:1px solid color-mix(in oklch, var(--accent) 40%, var(--rule));border-radius:8px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:14px;color:var(--accent);">◆</span>
        <span style="color:var(--ink-2);font-size:11.5px;">No STRONG beat predictions today, but <b style="color:var(--accent)">${solidPicks.length} SOLID</b> candidates are close. </span>
        <button onclick="_earnFilterChange('beat','SOLID')" style="margin-left:auto;padding:5px 11px;background:transparent;border:1px solid var(--accent);border-radius:4px;color:var(--accent);font-weight:700;cursor:pointer;font-family:DM Sans;font-size:11px;">VIEW SOLID</button>
      </div>
    </div>` : '');

  const sectorOptions = ['<option value="all">All sectors</option>']
    .concat(sectors.map(s => `<option value="${s}" ${F.sector === s ? 'selected' : ''}>${s}</option>`))
    .join('');
  const filterBar = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:0 0 12px;font-size:11.5px;">
      <input type="text" placeholder="Search ticker…" value="${F.search}" oninput="_earnSearch(this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;width:130px;">
      <select onchange="_earnFilterChange('days', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all" ${F.days==='all'?'selected':''}>All days</option>
        <option value="1" ${F.days==='1'?'selected':''}>≤ 1 day (urgent)</option>
        <option value="3" ${F.days==='3'?'selected':''}>≤ 3 days</option>
        <option value="5" ${F.days==='5'?'selected':''}>≤ 5 days</option>
        <option value="10" ${F.days==='10'?'selected':''}>≤ 10 days</option>
      </select>
      <select onchange="_earnFilterChange('verdict', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all" ${F.verdict==='all'?'selected':''}>Any verdict</option>
        <option value="BUY" ${F.verdict==='BUY'?'selected':''}>BUY only</option>
        <option value="WATCH" ${F.verdict==='WATCH'?'selected':''}>WATCH only</option>
        <option value="has_signal" ${F.verdict==='has_signal'?'selected':''}>Any signal</option>
      </select>
      <select onchange="_earnFilterChange('ownership', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all" ${F.ownership==='all'?'selected':''}>All</option>
        <option value="owned" ${F.ownership==='owned'?'selected':''}>⚠ Owned only</option>
      </select>
      <select onchange="_earnFilterChange('sector', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;max-width:160px;">
        ${sectorOptions}
      </select>
      <select onchange="_earnFilterChange('beat', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all" ${F.beat==='all'?'selected':''}>Any beat-score</option>
        <option value="STRONG" ${F.beat==='STRONG'?'selected':''}>🎯 STRONG only</option>
        <option value="SOLID" ${F.beat==='SOLID'?'selected':''}>STRONG + SOLID</option>
        <option value="has_pred" ${F.beat==='has_pred'?'selected':''}>Has prediction</option>
      </select>
      <select onchange="_earnFilterChange('sort', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="days" ${F.sort==='days'?'selected':''}>Sort: Days asc</option>
        <option value="beat" ${F.sort==='beat'?'selected':''}>Sort: Beat-score desc</option>
        <option value="score" ${F.sort==='score'?'selected':''}>Sort: Score desc</option>
        <option value="ticker" ${F.sort==='ticker'?'selected':''}>Sort: Ticker A-Z</option>
      </select>
      <span style="margin-left:auto;color:var(--ink-3);font-size:11px;">
        showing <b style="color:var(--ink-1)">${filtered.length}</b> / ${totalUS}
      </span>
    </div>`;

  body.innerHTML = `
    ${strongBanner}
    ${filterBar}
    <div style="padding:0 0 14px;color:var(--ink-2);font-size:11.5px;line-height:1.55;">
      <b style="color:var(--fail)">Red days = ≤1d</b> (highest risk) · <b style="color:var(--warn)">Yellow = ≤3d</b> · <b style="color:var(--accent)">Amber = ≤5d</b>.
      <b>BEAT/MISS/INLINE</b> column = last 30 days of prior reports for that ticker (pattern hint, not promise).
      <b>OWNED</b> tag = currently in your portfolio.
    </div>
    <div style="overflow-x:auto;max-height:70vh;overflow-y:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead style="position:sticky;top:0;z-index:5;">
          <tr style="background:var(--bg-2);color:var(--ink-3);text-align:left;border-bottom:1px solid var(--rule-2);">
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">TICKER</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">DAYS</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">REPORT</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">WHEN</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;">SCORE</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;">VERDICT</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">SETUP</th>
            <th style="padding:9px 12px;text-align:right;font-weight:600;letter-spacing:0.04em;font-size:10px;">EPS EST</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;" title="BEAT / MISS / INLINE — last 30d of prior reports">PRIOR</th>
            <th style="padding:9px 12px;text-align:center;font-weight:600;letter-spacing:0.04em;font-size:10px;" title="Composite beat-probability score 0-100 — historical beat rate + price runup + volume accumulation + analyst sentiment + options flow + sector co-movers">BEAT %</th>
            <th style="padding:9px 12px;font-weight:600;letter-spacing:0.04em;font-size:10px;">SECTOR</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

export function dispose() { /* no-op */ }


// ─── Helpers folded from dashboard.html (CapStudio sub-helpers fold 2026-05-09) ───
function _earnFilterChange(key, val) {
  window._earnFilters[key] = val;
  renderEarnings();
}

function _earnSearch(val) {
  window._earnFilters.search = (val || '').trim().toUpperCase();
  // Debounce
  clearTimeout(window._earnSearchTimer);
  window._earnSearchTimer = setTimeout(() => renderEarnings(), 200);
}


// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window._earnFilterChange = _earnFilterChange;
  window._earnSearch = _earnSearch;
}
