// tabs/elite/hero.js — Hero card renderer (top 3 across all 9 cells).
// Prominent 3-column layout: identity / KPIs / plan. Returns HTML string.

import { tier, stageBadge, modeLabel, money, arc } from './helpers.js';
import { thesisLine } from './thesis.js';

export function renderHeroCard(p) {
  const t   = tier(p.elite_score);
  const sb  = stageBadge(p._stage);
  const snap = p.snapshot || {};
  const thesis = thesisLine(p);

  const winProb = snap.p_target != null ? `${snap.p_target}%` : '—';
  const winSub  = snap.p_stop   != null ? `${snap.p_stop}% stop first` : '';
  const rrStr   = snap.rr       != null ? `1 : ${snap.rr.toFixed(1)}` : '—';

  return `<div class="ep2-hero-card" style="--tier-color:${t.color}" onclick="window.location.href='elite-detail.html?t=${p.ticker}&from=elite'">
    <div class="ep2-hero-top">
      <div class="ep2-hero-id">
        <div class="ep2-hero-ticker">${p.ticker}</div>
        <div class="ep2-hero-name">${(p.name || '').slice(0, 36)}</div>
      </div>
      <div class="ep2-hero-arc">${arc(p.elite_score, t.color, 76, 22)}</div>
    </div>

    <div class="ep2-hero-tags">
      <span class="ep2-tag" style="color:${t.color};border-color:${t.color}">${t.label}</span>
      <span class="ep2-tag" style="color:${sb.color};border-color:${sb.color}">${sb.icon} ${sb.label}</span>
      <span class="ep2-tag ep2-tag-mode">${modeLabel(p._mode)}</span>
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
      <div class="ep2-plan-row"><span class="ep2-plan-l">Entry</span><span class="ep2-plan-v">${money((snap.entry||[])[0])} – ${money((snap.entry||[])[1])}</span></div>
      <div class="ep2-plan-row"><span class="ep2-plan-l">Stop</span><span class="ep2-plan-v" style="color:var(--red)">${money(snap.stop)}</span></div>
      <div class="ep2-plan-row"><span class="ep2-plan-l">Target T1</span><span class="ep2-plan-v" style="color:var(--green)">${money(snap.target1)}</span></div>
      ${snap.cvar != null ? `<div class="ep2-plan-row"><span class="ep2-plan-l">CVaR-97.5</span><span class="ep2-plan-v" style="color:var(--red)">${snap.cvar}%</span></div>` : ''}
    </div>

    <div class="ep2-hero-cta">→ Open full analysis</div>
  </div>`;
}
