// tabs/earnings/earnings.js — Earnings tab thin orchestrator.
//
// Sub-modules:
//   data_prep.js — cross-reference helpers (tickerData, beatByT, beatStats, sectors)
//   filters.js   — applyFilters + sortFiltered + filter bar UI + handlers
//   banner.js    — STRONG / SOLID beat-prediction banner
//   rows.js      — row HTML + table-shell wrapper

import { getData } from '../../core/shared.js';
import { buildPortfolioSet, buildTickerData, buildBeatByT,
         buildBeatStats, collectSectors } from './data_prep.js';
import { applyFilters, sortFiltered, buildFilterBar,
         filterChange, search } from './filters.js';
import { buildBeatBanner } from './banner.js';
import { buildTable }      from './rows.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('earnBody');
  const meta = document.getElementById('earnMeta');
  if (!body) return;

  const wl       = (DATA && DATA.earnings_watchlist)      || [];
  const meta_d   = (DATA && DATA.earnings_watchlist_meta) || {};
  const outcomes = (DATA && DATA.earnings_outcomes_30d)   || [];
  const F        = window._earnFilters;

  if (!wl.length) {
    body.innerHTML = `
      <div style="padding:32px 28px; text-align:center; color:var(--ink-2); border:1px dashed var(--rule); border-radius:8px;">
        <div style="font-size:13px; font-weight:600; margin-bottom:6px;">Earnings watchlist not built yet.</div>
        <div style="font-size:11px; color:var(--ink-3); line-height:1.6;">Run <code style="font-family:var(--mono); background:var(--bg-3); padding:1px 5px; border-radius:3px;">python3 build_earnings_watchlist.py</code> or wait for the 5:30am PT cron.</div>
      </div>`;
    if (meta) meta.textContent = '0 entries';
    return;
  }

  const myPositions = buildPortfolioSet(DATA);
  const tickerData  = buildTickerData(DATA);
  const beatByT     = buildBeatByT(DATA);
  const beatStats   = buildBeatStats(outcomes);
  const sectors     = collectSectors(wl, tickerData);

  const inPortfolio = wl.filter(e => myPositions.has(e.ticker)).length;
  const totalUS     = wl.length;

  let filtered = applyFilters(wl, F, tickerData, myPositions, beatByT);
  filtered = sortFiltered(filtered, F, tickerData, beatByT);

  if (meta) meta.textContent = `${filtered.length} of ${totalUS} reporting · ${meta_d.from_date} → ${meta_d.to_date}` +
                                (inPortfolio > 0 ? ` · ⚠ ${inPortfolio} owned` : '');
  const sb = document.getElementById('sbEarnCt'); if (sb) sb.textContent = totalUS;
  const fs = document.getElementById('fsEarnCt'); if (fs) fs.textContent = totalUS;

  body.innerHTML = `
    ${buildBeatBanner(DATA.earnings_beat_predictions || [])}
    ${buildFilterBar(F, sectors, filtered.length, totalUS)}
    ${buildTable(filtered, { tickerData, beatByT, beatStats, myPositions })}
  `;
}

export function dispose() { /* no-op */ }

// Auto-bind handlers to window for inline onchange/oninput callers
if (typeof window !== 'undefined') {
  window.renderEarnings    = render;
  window._earnFilterChange = filterChange;
  window._earnSearch       = search;
}
