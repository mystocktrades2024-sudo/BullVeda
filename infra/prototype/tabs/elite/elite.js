// tabs/elite/elite.js — Elite Picks v2 (2026-05-09 redesign).
//
// Architecture: three-act structure.
//   ACT 1 — HERO: top 3 picks across all 9 cells, prominent cards
//   ACT 2 — TRACKS: per-mode horizontal bands with compact pick rows
//   ACT 3 — CONTEXT: regime + factor legend (collapsed by default)
//
// Replaces the dense 3×3 grid that wasted space on empty SHORT cells in
// bullish regimes and showed each ticker in 3+ places. Plain-English
// thesis synthesized from breakdown + snapshot — no more raw arithmetic
// ("+ MC P(T1 first) 57% – P(stop first) 43% = ++15% edge → 16.2/25").

import { getData } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('elitePicksBody');
  const meta = document.getElementById('elitePicksMeta');
  const sbCt = document.getElementById('sbEliteCt');
  if (!body) return;

  const ep = DATA.elite_picks || {};
  if (ep.error) {
    body.innerHTML = `<div class="ep2-empty">⚠ Elite picks computation error: ${ep.error}</div>`;
    return;
  }

  // Flatten: collect every (mode, stage, pick) tuple across the 9 cells.
  const all = [];
  for (const mode of ['Swing', 'Position', 'Invest']) {
    for (const stage of ['BUY', 'WATCH', 'SHORT']) {
      const cell = (ep[mode] || {})[stage] || [];
      cell.forEach((p, i) => all.push({ ...p, _mode: mode, _stage: stage, _rank: i + 1 }));
    }
  }
  if (sbCt) sbCt.textContent = all.length;

  // Meta strip (top header)
  if (meta) {
    if (ep.meta?.blocked) {
      meta.innerHTML = `<span style="color:var(--fail)">SUPPRESSED</span> · ${ep.meta.reason || 'system gate active'}`;
    } else {
      const heroN = Math.min(3, all.length);
      meta.textContent = `${ep.meta?.n_passing_hard_gates ?? 0} passed hard gates · ${heroN} hero · ${all.length} total picks`;
    }
  }

  // Suppressed state — single banner, no grid
  if (ep.meta?.blocked) {
    body.innerHTML = _renderSuppressedBanner(ep.meta);
    return;
  }

  // Empty state — nothing qualified at all
  if (all.length === 0) {
    body.innerHTML = _renderEmptyState(ep, DATA);
    return;
  }

  // Pick top 3 globally for the hero band, ranked by elite_score
  const hero = [...all].sort((a, b) => (b.elite_score || 0) - (a.elite_score || 0)).slice(0, 3);

  body.innerHTML = `
    ${_renderRegimeStrip(ep, DATA)}

    <div class="ep2-hero-band">
      <div class="ep2-section-h">
        <span class="ep2-section-eyebrow">★ Today's best ideas</span>
        <span class="ep2-section-sub">Top ${hero.length} across all modes & stages, ranked by Elite Score</span>
      </div>
      <div class="ep2-hero-grid">
        ${hero.map(p => _renderHeroCard(p)).join('')}
      </div>
    </div>

    ${['Swing', 'Position', 'Invest'].map(mode => _renderTrack(mode, ep[mode] || {}, hero)).join('')}

    ${_renderLegendCollapsed(ep)}
  `;
}

export function dispose() { /* no-op */ }

// ── Helpers ────────────────────────────────────────────────────────────

function _tier(score) {
  if (score >= 80) return { label: 'ELITE',     color: 'var(--green)',   bg: 'color-mix(in oklch, var(--green) 12%, transparent)' };
  if (score >= 65) return { label: 'HIGH',      color: 'var(--info)',    bg: 'color-mix(in oklch, var(--info) 12%, transparent)' };
  if (score >= 50) return { label: 'MARGINAL',  color: 'var(--ink-1)',   bg: 'var(--bg-2)' };  // neutral gray (was yellow — washed out)
  return                  { label: 'WEAK',      color: 'var(--paper-3)', bg: 'var(--bg-2)' };
}

function _stageBadge(stage) {
  if (stage === 'BUY')   return { label: 'BUY',   color: 'var(--green)', icon: '▲' };
  if (stage === 'SHORT') return { label: 'SHORT', color: 'var(--red)',   icon: '▼' };
  return                       { label: 'WATCH', color: 'var(--accent)', icon: '◆' };
}

function _modeLabel(mode) {
  return mode === 'Swing' ? 'Swing · 2-14d' : mode === 'Position' ? 'Position · 3-8w' : 'Invest · 12+mo';
}

function _money(v)   { return v != null ? '$' + (+v).toFixed(2) : '—'; }
function _safe(v, d) { return v != null ? v : d; }

// Synthesize plain-English thesis from breakdown + snapshot — no raw arithmetic.
function _thesisLine(p) {
  const snap = p.snapshot || {};
  const bd = p.breakdown || {};
  const pTarget = snap.p_target;
  const pStop = snap.p_stop;
  const rr = snap.rr;
  const sharpe = snap.fwd_sharpe;
  const tier = _tier(p.elite_score).label;

  // Top-line synthesis chooses the strongest one or two factors to feature
  const phrases = [];
  if (pTarget != null && pStop != null) {
    const edge = pTarget - pStop;
    if (edge >= 25) phrases.push(`Strong forward edge: ${pTarget}% target vs ${pStop}% stop`);
    else if (edge >= 10) phrases.push(`Positive edge: ${pTarget}%/${pStop}% (target/stop)`);
    else if (edge >= 0) phrases.push(`Marginal edge: ${pTarget}%/${pStop}%`);
    else phrases.push(`Tight: ${pTarget}%/${pStop}%`);
  }
  if (rr != null && rr >= 2.5) phrases.push(`R:R 1:${rr.toFixed(1)}`);
  else if (rr != null) phrases.push(`R:R 1:${rr.toFixed(1)} (light)`);
  if (sharpe != null && sharpe >= 1.5) phrases.push(`Sharpe ${sharpe.toFixed(1)}`);

  // Pick one factor highlight from breakdown
  const factorWin = _findFactorHighlight(bd);
  if (factorWin) phrases.push(factorWin);

  // Earnings warning supersedes all
  if (snap.earn_days != null && snap.earn_days <= 7) {
    return `⚠ Earnings in ${snap.earn_days}d — ${phrases.slice(0, 2).join(' · ')}`;
  }

  return phrases.slice(0, 3).join(' · ') || (p.verdict_line || `${tier} pick`);
}

function _findFactorHighlight(bd) {
  const factors = [
    { key: 'sector_rank',     max: 12, label: pct => `Top ${100 - Math.round(pct * 100 / 12)}% sector` },
    { key: 'tier1_stack',     max: 11, label: pct => 'Tier-1 stack firing' },
    { key: 'conviction_tier', max: 12, label: pct => 'High-conviction setup' },
    { key: 'entry_quality',   max: 12, label: pct => 'Fresh entry zone' },
    { key: 'hmm_regime',      max: 11, label: pct => 'Regime aligned' },
  ];
  // Find one factor at >=80% of max — that's a real strength worth showing
  for (const f of factors) {
    const pts = (bd[f.key] || {}).adj_pts || 0;
    if (pts / f.max >= 0.8) return f.label(pts);
  }
  return null;
}

// Hero card — one of the top 3 across all cells. Three columns: identity, KPIs, plan.
function _renderHeroCard(p) {
  const t = _tier(p.elite_score);
  const sb = _stageBadge(p._stage);
  const snap = p.snapshot || {};
  const thesis = _thesisLine(p);

  // MC win prob is the headline — promote to big number if present
  const winProb = snap.p_target != null ? `${snap.p_target}%` : '—';
  const winSub = snap.p_stop != null ? `${snap.p_stop}% stop first` : '';
  const rrStr = snap.rr != null ? `1 : ${snap.rr.toFixed(1)}` : '—';

  return `<div class="ep2-hero-card" style="--tier-color:${t.color}" onclick="window.location.href='elite-detail.html?t=${p.ticker}&from=elite'">
    <div class="ep2-hero-top">
      <div class="ep2-hero-id">
        <div class="ep2-hero-ticker">${p.ticker}</div>
        <div class="ep2-hero-name">${(p.name || '').slice(0, 36)}</div>
      </div>
      <div class="ep2-hero-arc">${_arc(p.elite_score, t.color, 76, 22)}</div>
    </div>

    <div class="ep2-hero-tags">
      <span class="ep2-tag" style="color:${t.color};border-color:${t.color}">${t.label}</span>
      <span class="ep2-tag" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${sb.label}</span>
      <span class="ep2-tag ep2-tag-mode">${_modeLabel(p._mode)}</span>
      ${p.sector ? `<span class="ep2-tag ep2-tag-sector">${p.sector}</span>` : ''}
    </div>

    <div class="ep2-hero-thesis">${thesis}</div>

    <div class="ep2-hero-kpis">
      <div class="ep2-kpi ep2-kpi-hero">
        <div class="ep2-kpi-l">MC win prob (T1 first)</div>
        <div class="ep2-kpi-v" style="color:${snap.p_target >= 60 ? 'var(--green)' : snap.p_target >= 50 ? 'var(--accent)' : 'var(--ink-1)'}">${winProb}</div>
        <div class="ep2-kpi-sub">${winSub}</div>
      </div>
      <div class="ep2-kpi">
        <div class="ep2-kpi-l">R : R</div>
        <div class="ep2-kpi-v">${rrStr}</div>
      </div>
      <div class="ep2-kpi">
        <div class="ep2-kpi-l">Score</div>
        <div class="ep2-kpi-v">${Math.round(p.elite_score || 0)}<span class="ep2-kpi-vu">/100</span></div>
      </div>
    </div>

    <div class="ep2-hero-plan">
      <div class="ep2-plan-row"><span class="ep2-plan-l">Entry</span><span class="ep2-plan-v">${_money((snap.entry||[])[0])} – ${_money((snap.entry||[])[1])}</span></div>
      <div class="ep2-plan-row"><span class="ep2-plan-l">Stop</span><span class="ep2-plan-v" style="color:var(--red)">${_money(snap.stop)}</span></div>
      <div class="ep2-plan-row"><span class="ep2-plan-l">Target T1</span><span class="ep2-plan-v" style="color:var(--green)">${_money(snap.target1)}</span></div>
      ${snap.cvar != null ? `<div class="ep2-plan-row"><span class="ep2-plan-l">CVaR-97.5</span><span class="ep2-plan-v" style="color:var(--red)">${snap.cvar}%</span></div>` : ''}
    </div>

    <div class="ep2-hero-cta">→ Open full analysis</div>
  </div>`;
}

// Mode track — collapsible band per mode showing picks as compact rows
function _renderTrack(mode, modeData, heroPicks) {
  const heroSet = new Set(heroPicks.map(h => h.ticker));
  const stages = ['BUY', 'WATCH', 'SHORT'];

  const allInMode = stages.flatMap(s => (modeData[s] || []).map((p, i) => ({ ...p, _stage: s, _rank: i + 1 })));
  const total = allInMode.length;

  // Empty mode: don't render a placeholder card — render an informative one-liner
  if (total === 0) {
    return `<div class="ep2-track ep2-track-empty">
      <div class="ep2-track-h">
        <span class="ep2-track-mode">${_modeLabel(mode).toUpperCase()}</span>
        <span class="ep2-track-empty-msg">No qualifying picks in this horizon.</span>
      </div>
    </div>`;
  }

  // Avg score for the mode (to surface as a track-level KPI)
  const avg = total ? Math.round(allInMode.reduce((s, p) => s + (p.elite_score || 0), 0) / total) : 0;
  const tier = _tier(avg);

  return `<div class="ep2-track">
    <div class="ep2-track-h">
      <span class="ep2-track-mode">${_modeLabel(mode).toUpperCase()}</span>
      <span class="ep2-track-count">${total} pick${total === 1 ? '' : 's'}</span>
      <span class="ep2-track-avg">avg score <b style="color:${tier.color}">${avg}</b></span>
      ${stages.filter(s => (modeData[s] || []).length).map(s => {
        const sb = _stageBadge(s);
        return `<span class="ep2-track-stage" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${(modeData[s] || []).length} ${sb.label}</span>`;
      }).join('')}
    </div>
    <div class="ep2-track-rows">
      ${allInMode.map(p => _renderTrackRow(p, heroSet.has(p.ticker))).join('')}
    </div>
  </div>`;
}

// Compact row — one per pick within a track. Click → elite-detail.
function _renderTrackRow(p, isHero) {
  const t = _tier(p.elite_score);
  const sb = _stageBadge(p._stage);
  const snap = p.snapshot || {};
  const thesis = _thesisLine(p);
  const winProb = snap.p_target != null ? `${snap.p_target}%` : '—';

  return `<div class="ep2-row${isHero ? ' ep2-row-hero' : ''}" onclick="window.location.href='elite-detail.html?t=${p.ticker}&from=elite'">
    <div class="ep2-row-rank">#${p._rank}</div>
    <div class="ep2-row-arc">${_arc(p.elite_score, t.color, 40, 14)}</div>
    <div class="ep2-row-id">
      <div class="ep2-row-ticker-line">
        <span class="ep2-row-ticker">${p.ticker}</span>
        ${isHero ? '<span class="ep2-row-star" title="In Hero">★</span>' : ''}
        <span class="ep2-row-tier" style="color:${t.color}">${t.label}</span>
        <span class="ep2-row-stage" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${sb.label}</span>
      </div>
      <div class="ep2-row-thesis">${thesis}</div>
    </div>
    <div class="ep2-row-kpis">
      <div class="ep2-row-kpi">
        <div class="ep2-row-kpi-l">Win</div>
        <div class="ep2-row-kpi-v" style="color:${snap.p_target >= 60 ? 'var(--green)' : 'var(--ink-0)'}">${winProb}</div>
      </div>
      <div class="ep2-row-kpi">
        <div class="ep2-row-kpi-l">R:R</div>
        <div class="ep2-row-kpi-v">1:${(snap.rr || 0).toFixed(1)}</div>
      </div>
      <div class="ep2-row-kpi ep2-row-kpi-px">
        <div class="ep2-row-kpi-l">Entry</div>
        <div class="ep2-row-kpi-v">${_money((snap.entry||[])[0])}</div>
      </div>
      <div class="ep2-row-kpi ep2-row-kpi-px">
        <div class="ep2-row-kpi-l">Stop · T1</div>
        <div class="ep2-row-kpi-v"><span style="color:var(--red)">${_money(snap.stop)}</span> · <span style="color:var(--green)">${_money(snap.target1)}</span></div>
      </div>
    </div>
    <div class="ep2-row-chevron">›</div>
  </div>`;
}

// Score arc SVG — reusable, sized via params
function _arc(score, color, size = 68, font = 18) {
  const r = (size - 12) / 2;
  const C = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const cx = size / 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex-shrink:0">
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="3"/>
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"
            transform="rotate(-90 ${cx} ${cx})"/>
    <text x="${cx}" y="${cx}" text-anchor="middle" dominant-baseline="central"
          font-size="${font}" font-weight="800" font-family="var(--mono)" fill="${color}">${Math.round(score)}</text>
  </svg>`;
}

// Regime context strip — one line at the top explaining what's filtering
function _renderRegimeStrip(ep, DATA) {
  const r = DATA.regime || {};
  const rg = r.regime || r.label || 'unknown';
  const conf = r.confidence != null ? Math.round(r.confidence * 100) + '%' : null;
  const breadth = r.breadth_score != null ? Math.round(r.breadth_score * 100) + '%' : (r.breadth || null);
  const meta = ep.meta || {};
  return `<div class="ep2-regime-strip">
    <span class="ep2-regime-l">REGIME</span>
    <span class="ep2-regime-v"><b>${rg}</b>${conf ? ` · ${conf} conf` : ''}${breadth ? ` · breadth ${breadth}` : ''}</span>
    <span class="ep2-regime-sep">·</span>
    <span class="ep2-regime-meta">${meta.n_candidates_evaluated || 0} candidates · ${meta.n_passing_hard_gates ?? 0} passed gates · 8 weighted factors</span>
    <span class="ep2-regime-r">${meta.computed_at?.slice(11, 16) || ''}</span>
  </div>`;
}

function _renderSuppressedBanner(meta) {
  return `<div class="ep2-suppressed">
    <div class="ep2-suppressed-icon">🔴</div>
    <div class="ep2-suppressed-h">Picks suppressed — circuit breaker active</div>
    <div class="ep2-suppressed-note"><b>${meta.note || 'System gate'}</b></div>
    <div class="ep2-suppressed-reason">${meta.reason || 'all picks gated until risk normalizes'}</div>
  </div>`;
}

function _renderEmptyState(ep, DATA) {
  const r = DATA.regime || {};
  const rg = r.regime || r.label || 'unknown';
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

function _renderLegendCollapsed(ep) {
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
