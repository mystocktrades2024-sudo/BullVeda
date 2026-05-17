// tabs/scanner/scanner.js — Signal Scanner tab thin orchestrator.
//
// Architecture (post MOD-1, 2026-05-10):
//   filters.js   — applyFilters() + sortRows() (pure, 13-filter chain)
//   row.js       — buildRowHtml(r, ctx) + chip-stack builder (per-row template)
//   sparkline.js — buildSparkPath() (deterministic ticker-hashed mini chart)
//   sectors.js   — buildSectorChips() (DOM injector for filter chip group)
//
// Window dependencies (live in dashboard.html, accessed via globalThis):
//   FS_STATE                   — exposed via window.FS_STATE (MOD-1 fix)
//   _SC2_EXTRA_COLS            — extra-column Set
//   _SC2_NEW_TICKERS           — Set of new-since-last-scan tickers (read by row builder)
//   _SC2_SELECTED              — Set of currently-selected tickers (selection restore)
//   _setupFamilyOf, _scoreRing, _logoHtml, _starsHtml,
//   _getWatchlist, _matchesPerfPattern, _sc2FmtExtra,
//   _sc2RenderKpis, _sc2RenderActive, _sc2UpdateSavedCount,
//   _sc2UpdateSeenTickers, _sc2InjectExtraHeaders, _sc2ApplyColVisibility,
//   _sc2WireTickerPreview, _sc2InjectGroupDividers, _wireCtxMenu,
//   setText                    — function declarations (auto-bound to window)
//
// All side effects target dashboard-html DOM IDs:
//   #fsScannerCt, #fsScannerSub, #fsScannerWrap, #fsScannerRows, #sc2FootCt
//   plus header sort-arrow updates on .sc2-th.sortable

import { getData }        from '../../core/shared.js';
import { applyFilters, sortRows } from './filters.js';
import { buildRowHtml }   from './row.js';

function _allRows(DATA) {
  return [...(DATA.short_term || []), ...(DATA.medium_term || []), ...(DATA.long_term || [])];
}

export function render() {
  const DATA = getData();
  if (!DATA) return;

  // Window deps resolved once per render. Bare references would also work
  // (function decls hoist to globalThis), but explicit is safer for modules.
  const FS_STATE = window.FS_STATE;
  if (!FS_STATE) {
    console.warn('[scanner] window.FS_STATE not bound — dashboard.html init incomplete');
    return;
  }

  // 1. Filter + sort
  const all      = _allRows(DATA);
  const filtered = applyFilters(all, FS_STATE, {
    setupFamilyOf:      window._setupFamilyOf,
    getWatchlist:       window._getWatchlist,
    matchesPerfPattern: window._matchesPerfPattern,
  });
  const rows = sortRows(filtered, FS_STATE);

  // 2. Header counts + last-refresh stamp
  window.setText('fsScannerCt', `${rows.length} of ${all.length}`);
  window.setText('fsScannerSub',
    `last refresh ${new Date(DATA.run_timestamp || Date.now()).toLocaleString('en-US', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}`);
  const fc = document.getElementById('sc2FootCt');
  if (fc) fc.textContent = `Showing ${rows.length} of ${all.length} signals`;

  // 3. Sort arrow on header cells
  document.querySelectorAll('.sc2-th.sortable').forEach(th => {
    const k     = th.dataset.sort;
    const arrow = th.querySelector('.sc2-sort');
    if (arrow) {
      arrow.textContent = (k === FS_STATE.sortKey) ? (FS_STATE.sortDir === 'desc' ? '▼' : '▲') : '';
      th.classList.toggle('active', k === FS_STATE.sortKey);
    }
  });

  // 4. KPI tiles + active filters chip + density class + new-tickers tracking
  if (typeof window._sc2RenderKpis        === 'function') window._sc2RenderKpis();
  if (typeof window._sc2RenderActive      === 'function') window._sc2RenderActive();
  if (typeof window._sc2UpdateSavedCount  === 'function') window._sc2UpdateSavedCount();
  if (typeof window._sc2UpdateSeenTickers === 'function') window._sc2UpdateSeenTickers(rows, DATA.run_timestamp);
  const wrap = document.getElementById('fsScannerWrap');
  if (wrap) {
    wrap.classList.remove('density-compact', 'density-normal', 'density-spacious');
    wrap.classList.add('density-' + (FS_STATE.density || 'normal'));
  }

  // 5. Build row HTML
  const watched = window._getWatchlist();
  const rowCtx  = {
    watched,
    tier: null, eq: null,  // recomputed per-row inside the loop below
    setupFamilyOf: window._setupFamilyOf,
    scoreRing:     window._scoreRing,
    logoHtml:      window._logoHtml,
    starsHtml:     window._starsHtml,
    SC2_EXTRA_COLS: window._SC2_EXTRA_COLS || new Set(),
    sc2FmtExtra:    window._sc2FmtExtra,
  };
  const html = rows.map(r => {
    const score = r.score || 0;
    rowCtx.tier = r.conviction_tier || (score >= 88 ? 'T1' : score >= 78 ? 'T2' : score >= 70 ? 'T3' : 'WATCH');
    rowCtx.eq   = (r.entry_quality || '').toUpperCase();
    return buildRowHtml(r, rowCtx);
  }).join('');

  // 6. Inject + empty-state
  const out = document.getElementById('fsScannerRows');
  if (out) {
    if (rows.length === 0) {
      const m       = FS_STATE.mode || 'swing';
      const modeLbl = m === 'position' ? 'Position' : (m === 'invest' ? 'Invest' : 'Swing');
      out.innerHTML = `
        <div class="sc2-empty">
          <div class="sc2-empty-icon">⌕</div>
          <div class="sc2-empty-h">No ${modeLbl} signals match these filters</div>
          <div class="sc2-empty-sub">Try clearing filters, expanding the score range, or switching verdict.</div>
          <button class="btn primary" onclick="sc2Clear()" style="margin-top:14px">⟲ Clear all filters</button>
        </div>`;
    } else {
      out.innerHTML = html;
    }
  }

  // 7. Post-render wiring (context menu, selection restore, header injection,
  //    column visibility, ticker hover preview, group dividers when sorted by ticker)
  if (typeof window._wireCtxMenu === 'function') window._wireCtxMenu();
  const selSet = window._SC2_SELECTED;
  if (selSet) {
    document.querySelectorAll('.sc2-row').forEach(row => {
      if (selSet.has(row.dataset.ticker)) row.classList.add('selected');
    });
  }
  if (typeof window._sc2InjectExtraHeaders   === 'function') window._sc2InjectExtraHeaders();
  if (typeof window._sc2ApplyColVisibility   === 'function') window._sc2ApplyColVisibility();
  if (typeof window._sc2WireTickerPreview    === 'function') window._sc2WireTickerPreview();
  if (FS_STATE.sortKey === 'ticker' && typeof window._sc2InjectGroupDividers === 'function') {
    window._sc2InjectGroupDividers();
  }
}

export function dispose() { /* no-op */ }
