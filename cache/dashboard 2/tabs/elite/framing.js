// tabs/elite/framing.js — Page-level framing pieces around the hero + tracks.
// Regime context strip (top), suppressed banner (when circuit breaker is on),
// empty state (no qualifying picks), and the collapsible factor legend (bottom).
// All return HTML strings.

export function renderRegimeStrip(ep, DATA) {
  const r       = DATA.regime || {};
  const rg      = r.regime || r.label || 'unknown';
  const conf    = r.confidence != null ? Math.round(r.confidence * 100) + '%' : null;
  const breadth = r.breadth_score != null ? Math.round(r.breadth_score * 100) + '%' : (r.breadth || null);
  const meta    = ep.meta || {};
  return `<div class="ep2-regime-strip">
    <span class="ep2-regime-l">REGIME</span>
    <span class="ep2-regime-v"><b>${rg}</b>${conf ? ` · ${conf} conf` : ''}${breadth ? ` · breadth ${breadth}` : ''}</span>
    <span class="ep2-regime-sep">·</span>
    <span class="ep2-regime-meta">${meta.n_candidates_evaluated || 0} candidates · ${meta.n_passing_hard_gates ?? 0} passed gates · 8 weighted factors</span>
    <span class="ep2-regime-r">${meta.computed_at?.slice(11, 16) || ''}</span>
  </div>`;
}

export function renderSuppressedBanner(meta) {
  return `<div class="ep2-suppressed">
    <div class="ep2-suppressed-icon">🔴</div>
    <div class="ep2-suppressed-h">Picks suppressed — circuit breaker active</div>
    <div class="ep2-suppressed-note"><b>${meta.note || 'System gate'}</b></div>
    <div class="ep2-suppressed-reason">${meta.reason || 'all picks gated until risk normalizes'}</div>
  </div>`;
}

export function renderEmptyState(ep, DATA) {
  const r    = DATA.regime || {};
  const rg   = r.regime || r.label || 'unknown';
  const meta = ep.meta || {};
  return `<div class="ep2-empty-state">
    <div class="ep2-empty-icon">○</div>
    <div class="ep2-empty-h">No qualifying picks in any cell today</div>
    <div class="ep2-empty-sub">
      ${meta.n_candidates_evaluated || 0} candidates evaluated, ${meta.n_passing_hard_gates ?? 0} passed hard gates,
      but none survived the multi-factor critic in any (mode × stage) cell.
    </div>
    <div class="ep2-empty-context">
      <div><b>Current regime:</b> ${rg}</div>
      <div><b>Why this can happen:</b> regime mismatch (HMM probability misaligned with stage), score band underperformance,
      or all candidates failed entry-quality gates (extended off basis, R:R inconsistent, earnings ≤ 3d).</div>
      <div><b>What to do:</b> check the Scanner tab for raw signal counts, the Audit Trail for which gate fired, or wait for the next intraday rescore.</div>
    </div>
  </div>`;
}

export function renderLegendCollapsed() {
  return `<details class="ep2-legend">
    <summary>Show factor weights & hard-gate rules</summary>
    <div class="ep2-legend-grid">
      <div><b>Score Band · 20pts</b><br><span>band's historical WR from accuracy framework</span></div>
      <div><b>Forward Edge · 25pts</b><br><span>MC P(target first) − P(stop first)</span></div>
      <div><b>HMM Regime · 10pts</b><br><span>regime probability matches direction</span></div>
      <div><b>Cross-Asset · 5pts</b><br><span>risk-on/off matches stage</span></div>
      <div><b>Tier-1 Stack · 10pts</b><br><span>validated detectors firing (Spring weighted full)</span></div>
      <div><b>Sector Rank · 10pts</b><br><span>sector_pct_rank percentile</span></div>
      <div><b>Conviction · 10pts</b><br><span>T1=10 / T2=7 / T3=4</span></div>
      <div><b>Entry Quality · 10pts</b><br><span>FRESH=10 / PULLBACK=8 / VALID=5 / EXTENDED=0</span></div>
    </div>
    <div class="ep2-legend-foot"><b>Hard gates (auto-disqualify):</b> R:R inconsistent · earnings ≤ 3d · stop ≥ entry · score < 50 · tail-loss filter demoted (BUY) · stage-filter mismatch</div>
  </details>`;
}
