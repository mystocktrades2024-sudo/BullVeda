// tabs/audit/summary.js — Top 4 stat tiles: Avg %, By Alert Type, Best, Worst.
// Owns DOM: #auditSummary innerHTML.

const fmtPct = (p) => p == null ? '—' : (p >= 0 ? '+' : '') + p.toFixed(2) + '%';

export function renderSummary(filtered) {
  const enriched = filtered.filter(s => s.pct_now != null);
  const avgPct   = enriched.length ? enriched.reduce((a, b) => a + b.pct_now, 0) / enriched.length : 0;
  const winCount = enriched.filter(s => s.pct_now > 0).length;
  const wrPct    = enriched.length ? (winCount / enriched.length) * 100 : 0;
  const best     = enriched.length ? enriched.reduce((a, b) => b.pct_now > a.pct_now ? b : a) : null;
  const worst    = enriched.length ? enriched.reduce((a, b) => b.pct_now < a.pct_now ? b : a) : null;

  const pctByVerdict = { BUY: { sum: 0, n: 0 }, WATCH: { sum: 0, n: 0 }, SHORT: { sum: 0, n: 0 } };
  enriched.forEach(s => {
    const v = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    if (pctByVerdict[v]) { pctByVerdict[v].sum += s.pct_now; pctByVerdict[v].n++; }
  });
  const avgFor = (v) => v.n ? (v.sum / v.n) : null;

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
}
