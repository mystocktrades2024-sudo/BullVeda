// tabs/elite/elite.js — Elite Picks (3 modes × 3 stages = 9-cell grid).
// Extracted from dashboard.html:5397-5586 (2026-05-09).

import { getData } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const body = document.getElementById('elitePicksBody');
  const meta = document.getElementById('elitePicksMeta');
  const sbCt = document.getElementById('sbEliteCt');
  if (!body) return;

  const ep = DATA.elite_picks || {};
  if (ep.error) {
    body.innerHTML = `<div class="ep-empty">⚠ Elite picks computation error: ${ep.error}</div>`;
    return;
  }
  const totalPicks = ['Swing','Position','Invest'].reduce((s, m) =>
    s + ['BUY','WATCH','SHORT'].reduce((s2, st) => s2 + ((ep[m] || {})[st] || []).length, 0), 0);
  if (sbCt) sbCt.textContent = totalPicks;
  if (meta) {
    if (ep.meta?.blocked) {
      meta.innerHTML = `<span style="color:var(--fail)">🔴 SUPPRESSED</span> · ${ep.meta.reason || 'system gate active'}`;
    } else {
      meta.textContent = `${ep.meta?.n_passing_hard_gates ?? 0} passed hard gates · ${totalPicks} picks across 9 cells · top 5 each`;
    }
  }

  const verdictColor = (eliteScore) => eliteScore >= 80 ? 'var(--green)' : eliteScore >= 65 ? 'var(--accent)' : eliteScore >= 50 ? 'var(--warn)' : 'var(--paper-3)';
  const verdictTier = (s) => s >= 80 ? 'ELITE' : s >= 65 ? 'HIGH' : s >= 50 ? 'MARGINAL' : 'WEAK';

  const arc = (score, color) => {
    const r = 28, C = 2 * Math.PI * r;
    const pct = Math.max(0, Math.min(100, score)) / 100;
    return `<svg width="68" height="68" viewBox="0 0 68 68" style="flex-shrink:0">
      <circle cx="34" cy="34" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="4"/>
      <circle cx="34" cy="34" r="${r}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round"
              stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"
              transform="rotate(-90 34 34)"/>
      <text x="34" y="34" text-anchor="middle" dominant-baseline="central"
            font-size="18" font-weight="800" font-family="var(--mono)" fill="${color}">${Math.round(score)}</text>
    </svg>`;
  };

  const factorBar = (breakdown) => {
    const order = ['score_band','forward_edge','hmm_regime','cross_asset','tier1_stack','sector_rank','conviction_tier','entry_quality'];
    const colors = {
      score_band: 'var(--info)', forward_edge: 'var(--green)', hmm_regime: 'var(--accent)',
      cross_asset: 'var(--accent)', tier1_stack: 'var(--info)', sector_rank: 'var(--info)',
      conviction_tier: 'var(--green)', entry_quality: 'var(--green)',
    };
    return `<div class="ep-fbar">
      ${order.map(k => {
        const f = breakdown[k] || {pts:0, adj_pts:0};
        const max = {score_band:24, forward_edge:30, hmm_regime:11, cross_asset:5, tier1_stack:11, sector_rank:12, conviction_tier:12, entry_quality:12}[k];
        const pct = Math.max(2, Math.min(100, (f.adj_pts || 0) / max * 100));
        return `<div class="ep-fseg" title="${k.replace(/_/g,' ')}: ${f.adj_pts || 0}/${max}" style="flex:${pct}; background:${colors[k]}; opacity:${0.3 + ((f.adj_pts || 0) / max) * 0.7}"></div>`;
      }).join('')}
    </div>`;
  };

  const renderPickCard = (p, idx) => {
    const color = verdictColor(p.elite_score);
    const tier  = verdictTier(p.elite_score);
    const snap  = p.snapshot || {};
    const px = (v) => v != null ? '$' + (+v).toFixed(2) : '—';
    return `<div class="ep-card" onclick="window.location.href='elite-detail.html?t=${p.ticker}&from=elite'">
      <div class="ep-card-l">
        <div class="ep-rank">#${idx + 1}</div>
        ${arc(p.elite_score, color)}
        <div class="ep-tier-badge" style="color:${color};border-color:${color}">${tier}</div>
      </div>

      <div class="ep-card-mid">
        <div class="ep-ticker-row">
          <span class="ep-ticker">${p.ticker}</span>
          <span class="ep-name">${(p.name || '').slice(0, 30)}</span>
          <span class="ep-sector">${(p.sector || '—')}</span>
        </div>

        <div class="ep-verdict-line">${p.verdict_line || ''}</div>

        ${factorBar(p.breakdown || {})}

        <div class="ep-narrative-grid">
          <div class="ep-narr-bull">
            <div class="ep-narr-h">Why I'm confident</div>
            ${(p.why_confident || []).slice(0, 3).map(x => `<div class="ep-narr-bullet">+ ${x}</div>`).join('') || '<div class="ep-narr-empty">—</div>'}
          </div>
          <div class="ep-narr-bear">
            <div class="ep-narr-h">Watch out</div>
            ${(p.watch_out || []).length ? p.watch_out.map(x => `<div class="ep-narr-bullet">⚠ ${x}</div>`).join('') : '<div class="ep-narr-empty">All factors strong — no flags</div>'}
          </div>
        </div>
      </div>

      <div class="ep-card-r">
        <div class="ep-stat">
          <div class="ep-stat-l">Entry</div>
          <div class="ep-stat-v">${px((snap.entry||[])[0])}–${px((snap.entry||[])[1])}</div>
        </div>
        <div class="ep-stat">
          <div class="ep-stat-l">Stop · T1</div>
          <div class="ep-stat-v"><span style="color:var(--red)">${px(snap.stop)}</span> · <span style="color:var(--green)">${px(snap.target1)}</span></div>
        </div>
        <div class="ep-stat">
          <div class="ep-stat-l">R:R</div>
          <div class="ep-stat-v" style="font-weight:800">1:${(snap.rr||0).toFixed(1)}</div>
        </div>
        ${snap.p_target != null ? `<div class="ep-stat ep-stat-mc">
          <div class="ep-stat-l">MC: T1 vs Stop</div>
          <div class="ep-stat-v"><span style="color:var(--green)">${snap.p_target}%</span> / <span style="color:var(--red)">${snap.p_stop}%</span></div>
        </div>` : ''}
        ${snap.cvar != null ? `<div class="ep-stat">
          <div class="ep-stat-l">CVaR-97.5</div>
          <div class="ep-stat-v" style="color:var(--red)">${snap.cvar}%</div>
        </div>` : ''}
        ${snap.fwd_sharpe != null ? `<div class="ep-stat">
          <div class="ep-stat-l">Fwd Sharpe</div>
          <div class="ep-stat-v" style="color:${snap.fwd_sharpe >= 1 ? 'var(--green)' : 'var(--warn)'}">${snap.fwd_sharpe}</div>
        </div>` : ''}
        ${snap.earn_days != null && snap.earn_days <= 14 ? `<div class="ep-stat ep-stat-warn">
          <div class="ep-stat-l">⚠ Earnings</div>
          <div class="ep-stat-v" style="color:var(--warn)">${snap.earn_days}d</div>
        </div>` : ''}
      </div>
    </div>`;
  };

  const renderCell = (mode, stage, picks) => {
    const stageColor = stage === 'BUY' ? 'var(--green)' : stage === 'SHORT' ? 'var(--red)' : 'var(--accent)';
    const stageIcon  = stage === 'BUY' ? '▲' : stage === 'SHORT' ? '▼' : '◆';
    const modeLabel = mode === 'Swing' ? 'SWING · 2-14d' : mode === 'Position' ? 'POSITION · 3-8w' : 'INVEST · 12+mo';
    return `<div class="ep-cell">
      <div class="ep-cell-h">
        <span class="ep-cell-mode">${modeLabel}</span>
        <span class="ep-cell-stage" style="color:${stageColor};border-color:${stageColor}">${stageIcon} ${stage}</span>
        <span class="ep-cell-count">${picks.length}/5</span>
      </div>
      ${picks.length === 0 ? (
        ep.meta?.blocked ? `
        <div class="ep-cell-empty cb-block">
          <div class="ep-cell-empty-icon" style="color:var(--fail)">🔴</div>
          <div class="ep-cell-empty-h" style="color:var(--fail)">Picks suppressed</div>
          <div class="ep-cell-empty-sub" style="color:var(--ink-1)"><b>${ep.meta.note || 'System circuit breaker active'}</b></div>
          <div class="ep-cell-empty-sub" style="margin-top:6px">${ep.meta.reason || ''}</div>
        </div>
      ` : `
        <div class="ep-cell-empty">
          <div class="ep-cell-empty-icon">${stageIcon}</div>
          <div class="ep-cell-empty-h">No qualifying ${stage.toLowerCase()} picks</div>
          <div class="ep-cell-empty-sub">${stage === 'SHORT' ? 'Current regime is bullish — shorts gated. Need bearish HMM probability + RSI > 75 + score ≤ 50.' : stage === 'WATCH' ? 'No tickers in the 55-75 score band passed all gates.' : 'No tickers passed both score≥60 AND multi-factor checks. Either regime mismatch, weak entry, or all candidates failed hard gates.'}</div>
        </div>
      `) : picks.map((p, i) => renderPickCard(p, i)).join('')}
    </div>`;
  };

  body.innerHTML = `
    <div class="ep-meta-bar"${ep.meta?.blocked ? ' style="border-color:var(--fail);background:color-mix(in oklch, var(--fail) 8%, var(--bg-2))"' : ''}>
      <span class="ep-meta-l"${ep.meta?.blocked ? ' style="color:var(--fail)"' : ''}>${ep.meta?.blocked ? 'SUPPRESSED' : 'FRAMEWORK'}</span>
      <span>${ep.meta?.blocked
        ? `🔴 <b>${ep.meta.note || 'Circuit breaker active'}</b> — ${ep.meta.reason || 'all picks gated until risk normalizes'}`
        : `8 weighted factors · hard gates filter inconsistent plans · mode-specific multipliers · ${ep.meta?.n_candidates_evaluated || 0} evaluated`}</span>
      <span class="ep-meta-r">${ep.meta?.computed_at?.slice(11, 16) || ''}</span>
    </div>

    <div class="ep-grid">
      ${['Swing','Position','Invest'].map(mode => `
        <div class="ep-col">
          ${['BUY','WATCH','SHORT'].map(stage => renderCell(mode, stage, (ep[mode] || {})[stage] || [])).join('')}
        </div>
      `).join('')}
    </div>

    <div class="ep-legend">
      <div class="ep-legend-h">Factor weights — out of 100 raw, mode-multipliers can boost above</div>
      <div class="ep-legend-grid">
        <div><b>Score Band</b><br><span>20pts · band's historical WR from accuracy framework</span></div>
        <div><b>Forward Edge</b><br><span>25pts · MC P(target first) − P(stop first)</span></div>
        <div><b>HMM Regime</b><br><span>10pts · regime probability matches direction</span></div>
        <div><b>Cross-Asset</b><br><span>5pts · risk-on/off matches stage</span></div>
        <div><b>Tier-1 Stack</b><br><span>10pts · validated detectors firing (Spring weighted full)</span></div>
        <div><b>Sector Rank</b><br><span>10pts · sector_pct_rank percentile</span></div>
        <div><b>Conviction</b><br><span>10pts · T1=10 / T2=7 / T3=4</span></div>
        <div><b>Entry Quality</b><br><span>10pts · FRESH=10 / PULLBACK=8 / VALID=5 / EXTENDED=0</span></div>
      </div>
      <div class="ep-legend-foot"><b>Hard gates (auto-disqualify):</b> R:R inconsistent · earnings ≤ 3d · stop ≥ entry · score < 50 · tail-loss filter demoted (BUY) · stage-filter mismatch</div>
    </div>
  `;
}

export function dispose() { /* no-op */ }
