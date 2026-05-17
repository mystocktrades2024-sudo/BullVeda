// tabs/earnings/data_prep.js — Cross-reference helpers (pure transforms).
// Walks portfolio + scan sections + beat-prediction array to build lookup
// maps used by the row renderer + filter bar.

export function buildPortfolioSet(DATA) {
  const set = new Set();
  try {
    const ps = (DATA && DATA.portfolio && DATA.portfolio.positions) || [];
    ps.forEach(p => { if (p.status === 'OPEN') set.add((p.ticker || '').toUpperCase()); });
  } catch (_) {}
  return set;
}

// Map ticker → first matching scan row (priority: short_term > medium_term > long_term).
// Used to surface verdict / score / setup / sector for each earnings ticker.
export function buildTickerData(DATA) {
  const out = {};
  for (const sec of ['short_term', 'medium_term', 'long_term']) {
    for (const r of (DATA[sec] || [])) {
      if (r.ticker && !out[r.ticker]) out[r.ticker] = r;
    }
  }
  return out;
}

// Map ticker → beat-prediction record (from earnings_beat_predictions[]).
export function buildBeatByT(DATA) {
  const out = {};
  for (const p of (DATA.earnings_beat_predictions || [])) {
    if (p.ticker) out[p.ticker] = p;
  }
  return out;
}

// Aggregate prior 30-day BEAT/MISS/INLINE counts per ticker.
export function buildBeatStats(outcomes) {
  const out = {};
  outcomes.forEach(o => {
    const t = o.ticker;
    if (!out[t]) out[t] = { beats: 0, misses: 0, inline: 0, total: 0 };
    out[t].total++;
    if      (o.beat === 'BEAT') out[t].beats++;
    else if (o.beat === 'MISS') out[t].misses++;
    else                        out[t].inline++;
  });
  return out;
}

export function collectSectors(wl, tickerData) {
  const set = new Set();
  wl.forEach(e => {
    const sec = (tickerData[e.ticker] || {}).sector;
    if (sec && sec !== 'Unknown') set.add(sec);
  });
  return [...set].sort();
}
