// tabs/earnings/filters.js — Filter logic + sort + filter bar UI + handlers.
// Owns: window._earnFilterChange + window._earnSearch (bound at module load).
// _earnFilters state is a window-level object initialized in dashboard.html.

export function applyFilters(wl, F, tickerData, myPositions, beatByT) {
  return wl.filter(e => {
    if (F.days !== 'all' && e.days_to_earnings > parseInt(F.days, 10)) return false;
    const td = tickerData[e.ticker] || {};
    const v  = (td.verdict || td.stage || '').toUpperCase();
    if (F.verdict === 'BUY'        && v !== 'BUY')                          return false;
    if (F.verdict === 'WATCH'      && v !== 'WATCH')                        return false;
    if (F.verdict === 'has_signal' && !v)                                   return false;
    if (F.ownership === 'owned'    && !myPositions.has(e.ticker))           return false;
    if (F.sector !== 'all'         && td.sector !== F.sector)               return false;
    const bp = beatByT[e.ticker];
    if (F.beat === 'STRONG'   && (!bp || bp.tier !== 'STRONG'))             return false;
    if (F.beat === 'SOLID'    && (!bp || !['STRONG','SOLID'].includes(bp.tier))) return false;
    if (F.beat === 'has_pred' && !bp)                                       return false;
    if (F.search              && !e.ticker.includes(F.search))              return false;
    return true;
  });
}

export function sortFiltered(filtered, F, tickerData, beatByT) {
  if (F.sort === 'score') {
    filtered.sort((a, b) => ((tickerData[b.ticker] || {}).score || 0) - ((tickerData[a.ticker] || {}).score || 0));
  } else if (F.sort === 'ticker') {
    filtered.sort((a, b) => a.ticker.localeCompare(b.ticker));
  } else if (F.sort === 'beat') {
    filtered.sort((a, b) => ((beatByT[b.ticker] || {}).beat_score || 0) - ((beatByT[a.ticker] || {}).beat_score || 0));
  } else {
    filtered.sort((a, b) => a.days_to_earnings - b.days_to_earnings || a.ticker.localeCompare(b.ticker));
  }
  return filtered;
}

export function buildFilterBar(F, sectors, filteredCount, totalUS) {
  const sectorOptions = ['<option value="all">All sectors</option>']
    .concat(sectors.map(s => `<option value="${s}" ${F.sector === s ? 'selected' : ''}>${s}</option>`))
    .join('');
  return `
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:0 0 12px;font-size:11.5px;">
      <input type="text" placeholder="Search ticker…" value="${F.search}" oninput="_earnSearch(this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;width:130px;">
      <select onchange="_earnFilterChange('days', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all" ${F.days==='all'?'selected':''}>All days</option>
        <option value="1"   ${F.days==='1'  ?'selected':''}>≤ 1 day (urgent)</option>
        <option value="3"   ${F.days==='3'  ?'selected':''}>≤ 3 days</option>
        <option value="5"   ${F.days==='5'  ?'selected':''}>≤ 5 days</option>
        <option value="10"  ${F.days==='10' ?'selected':''}>≤ 10 days</option>
      </select>
      <select onchange="_earnFilterChange('verdict', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all"        ${F.verdict==='all'       ?'selected':''}>Any verdict</option>
        <option value="BUY"        ${F.verdict==='BUY'       ?'selected':''}>BUY only</option>
        <option value="WATCH"      ${F.verdict==='WATCH'     ?'selected':''}>WATCH only</option>
        <option value="has_signal" ${F.verdict==='has_signal'?'selected':''}>Any signal</option>
      </select>
      <select onchange="_earnFilterChange('ownership', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all"   ${F.ownership==='all'  ?'selected':''}>All</option>
        <option value="owned" ${F.ownership==='owned'?'selected':''}>⚠ Owned only</option>
      </select>
      <select onchange="_earnFilterChange('sector', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;max-width:160px;">
        ${sectorOptions}
      </select>
      <select onchange="_earnFilterChange('beat', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="all"      ${F.beat==='all'     ?'selected':''}>Any beat-score</option>
        <option value="STRONG"   ${F.beat==='STRONG'  ?'selected':''}>🎯 STRONG only</option>
        <option value="SOLID"    ${F.beat==='SOLID'   ?'selected':''}>STRONG + SOLID</option>
        <option value="has_pred" ${F.beat==='has_pred'?'selected':''}>Has prediction</option>
      </select>
      <select onchange="_earnFilterChange('sort', this.value)"
        style="padding:7px 10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:11.5px;">
        <option value="days"   ${F.sort==='days'  ?'selected':''}>Sort: Days asc</option>
        <option value="beat"   ${F.sort==='beat'  ?'selected':''}>Sort: Beat-score desc</option>
        <option value="score"  ${F.sort==='score' ?'selected':''}>Sort: Score desc</option>
        <option value="ticker" ${F.sort==='ticker'?'selected':''}>Sort: Ticker A-Z</option>
      </select>
      <span style="margin-left:auto;color:var(--ink-3);font-size:11px;">
        showing <b style="color:var(--ink-1)">${filteredCount}</b> / ${totalUS}
      </span>
    </div>`;
}

// ─── Handlers (bound to window for inline onchange/oninput callers) ───

export function filterChange(key, val) {
  window._earnFilters[key] = val;
  if (typeof window.renderEarnings === 'function') window.renderEarnings();
}

export function search(val) {
  window._earnFilters.search = (val || '').trim().toUpperCase();
  clearTimeout(window._earnSearchTimer);
  window._earnSearchTimer = setTimeout(() => {
    if (typeof window.renderEarnings === 'function') window.renderEarnings();
  }, 200);
}
