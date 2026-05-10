// tabs/scanner/filters.js — apply the 13-filter chain from FS_STATE to the
// flattened all-rows list. Pure function — no DOM, no side effects beyond
// the input array. Filters checked in priority order so the first kill cuts
// search space fastest.
//
// Inputs:
//   rows     — array from _fsAllRows() (short_term + medium_term + long_term)
//   FS_STATE — the global filter-state object (FS_STATE.mode/verdict/sector/…)
//   helpers  — { setupFamilyOf, getWatchlist, matchesPerfPattern } resolved
//              from window globals by the entry orchestrator
//
// Output: filtered array.

export function applyFilters(rows, FS_STATE, helpers) {
  const { setupFamilyOf, getWatchlist, matchesPerfPattern } = helpers;

  // 1. Mode (Swing / Position / Invest) — default 'swing'
  const mode = FS_STATE.mode || 'swing';
  if (mode === 'swing') {
    rows = rows.filter(r => !r.mode || r.mode === 'swing');
  } else {
    rows = rows.filter(r => r.mode === mode);
  }

  // 2. Verdict (BUY / WATCH / SELL / ALL)
  if (FS_STATE.verdict !== 'ALL') {
    rows = rows.filter(r => (r.stage || r.verdict) === FS_STATE.verdict);
  }

  // 3. Sector — prefix-match (first 4 chars)
  if (FS_STATE.sector !== 'ALL') {
    rows = rows.filter(r => ((r.sector || '').toUpperCase()).includes(FS_STATE.sector.slice(0, 4)));
  }

  // 4. Setup family (impulse / breakout / trend / special)
  if (FS_STATE.setupFamily !== 'ALL') {
    rows = rows.filter(r => setupFamilyOf(r.setup || r.setup_family) === FS_STATE.setupFamily);
  }

  // 5. Conviction tier (T1 / T2 / T3 / WATCH)
  if (FS_STATE.tier !== 'ALL') {
    rows = rows.filter(r => {
      const score = r.score || 0;
      const t = r.conviction_tier || (score >= 88 ? 'T1' : score >= 78 ? 'T2' : score >= 70 ? 'T3' : 'WATCH');
      return t === FS_STATE.tier;
    });
  }

  // 6. Entry quality (FRESH / PULLBACK / VALID / EXTENDED / MISSED)
  if (FS_STATE.entryQ !== 'ALL') {
    rows = rows.filter(r => (r.entry_quality || '').toUpperCase() === FS_STATE.entryQ);
  }

  // 7. Finviz Elite performance pattern (STEADY / PULLBACK / BREAKOUT / …)
  if (FS_STATE.perfPattern && FS_STATE.perfPattern !== 'ALL') {
    rows = rows.filter(r => matchesPerfPattern(r, FS_STATE.perfPattern));
  }

  // 8. Cap bucket (Mega / Large / Mid / Small / Micro)
  if (FS_STATE.capBucket && FS_STATE.capBucket !== 'ALL') {
    rows = rows.filter(r => (r.cap_bucket || '') === FS_STATE.capBucket);
  }

  // 9. Price tier (lt100 / lt250 / gt250)
  if (FS_STATE.priceTier && FS_STATE.priceTier !== 'ALL') {
    rows = rows.filter(r => {
      const p = r.price || 0;
      if (FS_STATE.priceTier === 'lt100') return p < 100;
      if (FS_STATE.priceTier === 'lt250') return p >= 100 && p < 250;
      if (FS_STATE.priceTier === 'gt250') return p >= 250;
      return true;
    });
  }

  // 10. Score range slider
  if (FS_STATE.scoreMin > 0 || FS_STATE.scoreMax < 100) {
    rows = rows.filter(r => {
      const s = r.score || 0;
      return s >= FS_STATE.scoreMin && s <= FS_STATE.scoreMax;
    });
  }

  // 11. R:R minimum
  if (FS_STATE.rrMin > 0) {
    rows = rows.filter(r => (r.rr || 0) >= FS_STATE.rrMin);
  }

  // 12. Watchlist-only toggle
  if (FS_STATE.watchOnly) {
    const wl = new Set(getWatchlist());
    rows = rows.filter(r => wl.has(r.ticker));
  }

  // 13. Hide-imminent-earnings toggle (≤ 7 days)
  if (FS_STATE.hideEarnings) {
    rows = rows.filter(r => r.earn_days == null || r.earn_days > 7);
  }

  return rows;
}

// Sort by FS_STATE.sortKey + FS_STATE.sortDir. Strings → localeCompare,
// numbers → numeric. Returns a NEW array (does not mutate input).
export function sortRows(rows, FS_STATE) {
  return rows.slice().sort((a, b) => {
    const av = a[FS_STATE.sortKey] ?? 0;
    const bv = b[FS_STATE.sortKey] ?? 0;
    const cmp = (typeof av === 'string') ? String(av).localeCompare(String(bv)) : (av - bv);
    return FS_STATE.sortDir === 'desc' ? -cmp : cmp;
  });
}
