// core/drawer.js — inline expand-row drawer (the keystone shared widget).
//
// Used by 3 surfaces: Portfolio row-expand, OptionsFlow row-expand, and
// Scanner row-expand. Extracted from dashboard.html:4137-4566 (430 lines).
//
// Dependencies (resolved via window — these are function declarations in
// classic scripts that auto-bind to window):
//   - _logoHtml(ticker, size)   → ticker logo
//   - _starsHtml(rating)        → star-rating widget
//   - _toggleStar(...)          → window onclick handler in mini buttons
//   - renderFloorScanner()      → re-render scanner after star toggle
//   - _OPEN_DRAWER_TICKER       → window state (mutated by Close button)
//
// (CapStudio modular loader 2026-05-09 — keystone extraction)

const _logoHtml  = (...a) => (window._logoHtml  ? window._logoHtml(...a)  : '');
const _starsHtml = (...a) => (window._starsHtml ? window._starsHtml(...a) : '');

export function renderInlineDrawer(T) {
  const v = T.verdict || 'WATCH';
  const tier = T.conviction_tier || (T.score >= 88 ? 'T1' : T.score >= 78 ? 'T2' : T.score >= 70 ? 'T3' : 'WATCH');
  const eq = (T.entry_quality || '').toUpperCase();
  const px = T.price || 0, c = T.pct_chg || 0;
  const upDn = c > 0 ? 'up' : c < 0 ? 'dn' : 'flat';
  const score = T.score || 0;
  const stop = T.stop || 0, t1 = T.target1 || T.t1 || 0, t2 = T.target2 || T.t2 || 0;
  const eLo = T.entry_low || T.entry_lo || px;
  const eHi = T.entry_high || T.entry_hi || px;
  const stopPct = stop ? ((stop - px) / px * 100) : 0;
  const t1Pct = t1 ? ((t1 - px) / px * 100) : 0;
  const t2Pct = t2 ? ((t2 - px) / px * 100) : 0;
  const reaction = T.reaction_checklist || [];
  const tierMax = { tech_max: T.tech_max || 35, fund_max: T.fund_max || 10, sent_max: T.sent_max || 15, smc_max: T.smc_max || 15 };
  const techS = T.tech_score || 0, fundS = T.fund_score || 0, smcS = T.smc_score || 0;
  const adx = T.adx || 0;
  const setupFam = T.setup_family || T.setup || '';
  const setupShort = setupFam.split(' —')[0].trim();
  const sectorMain = (T.sector || '').split(/[/]/)[0].trim();
  const sectorSub = (T.sector || '').split(/[/]/).slice(1).join(' / ').trim() || (T.industry || '');

  const _zoneQ = (() => {
    const z = T.zone_quality;
    if (!z) return '';
    if (typeof z === 'string') return z;
    if (typeof z === 'object') return String(z.label || z.rating || '').trim();
    return '';
  })();
  const _setupQ = (() => {
    const s = T.setup_quality;
    if (!s) return '';
    if (typeof s === 'string') return s;
    if (typeof s === 'object') return String(s.label || '').trim();
    return '';
  })();
  const _entrySub = (() => {
    const e = T.entry_subtype;
    if (!e) return '';
    if (typeof e === 'string') return e;
    if (typeof e === 'object') return String(e.label || e.type || '').trim();
    return '';
  })();
  const _entryQ = String(T.entry_quality || '').toUpperCase();
  const _marketPhase = (() => {
    const m = T.market_phase;
    if (!m) return '';
    if (typeof m === 'string') return m;
    if (typeof m === 'object') return String(m.phase || m.label || '').trim();
    return '';
  })();
  const _catTags = (() => {
    const c = T.catalyst_tags;
    if (!Array.isArray(c)) return [];
    return c.map(x => typeof x === 'string' ? x : (x.tag || x.label || x.name || '')).filter(Boolean);
  })();

  const planMax = t2 ? t2 : t1 * 1.05;
  const planMin = stop * 0.98;
  const planRange = Math.max(0.01, planMax - planMin);
  const ppx = (val) => Math.max(0, Math.min(100, ((val - planMin) / planRange) * 100));
  const passedReactions = reaction.filter(r => r.checked).length;
  const totalReactions = reaction.length;

  const vColor = v === 'BUY' ? 'var(--pass)' : v === 'WATCH' ? 'var(--warn)' : v === 'SELL' ? 'var(--fail)' : 'var(--ink-2)';
  const vLabel = v === 'SELL' ? 'SHORT' : v;
  return `
  <button class="ex-close" onclick="event.stopPropagation();this.closest('.fs-drawer').remove();_OPEN_DRAWER_TICKER=null" title="Close (Esc)">×</button>
  <div class="ex-card3">
    <div class="ex-col ex-col-id" style="--ex-accent:${vColor}">
      <div class="ex-id-line ex-id-l1">
        ${_logoHtml(T.ticker, 24)}
        <span class="ex-id-tk">${T.ticker}</span>
        <span class="ex-id-score-pill" style="background:color-mix(in oklch, ${vColor} 14%, transparent); border-color:${vColor}; color:${vColor}">${score} · ${vLabel}${tier !== 'WATCH' ? ' · ' + tier : ''}</span>
      </div>
      <div class="ex-id-line ex-id-l2">
        <span class="ex-id-name">${(T.name && T.name !== T.ticker) ? T.name : sectorMain}</span>
        <span class="ex-id-sec">${sectorMain}${sectorSub ? ' · ' + sectorSub.slice(0,18) : ''}</span>
      </div>
      <div class="ex-id-line ex-id-l3">
        <span class="ex-id-px">$${px.toFixed(2)}</span>
        <span class="ex-id-chg ${upDn}">${c >= 0 ? '+' : ''}${c.toFixed(2)}%</span>
        <span class="ex-id-stars">${_starsHtml(T.star_rating)}</span>
        ${setupShort ? `<span class="ex-id-setup">⚡ ${setupShort.slice(0,18)}</span>` : ''}
      </div>
    </div>

    <div class="ex-col ex-col-plan">
      <div class="ex-col-h">TRADE PLAN</div>
      <div class="ex-plan-grid">
        <div class="ex-pl-cell">
          <div class="ex-pl-l">ENTRY</div>
          <div class="ex-pl-v">$${eLo.toFixed(2)} – $${eHi.toFixed(2)}</div>
        </div>
        <div class="ex-pl-cell">
          <div class="ex-pl-l">STOP</div>
          <div class="ex-pl-v" style="color:var(--fail)">$${stop.toFixed(2)} <span class="ex-pl-s">${stopPct.toFixed(1)}%</span></div>
        </div>
        <div class="ex-pl-cell">
          <div class="ex-pl-l">T1 · T2</div>
          <div class="ex-pl-v" style="color:var(--pass)">$${t1.toFixed(2)} · ${t2 ? '$' + t2.toFixed(2) : '—'} <span class="ex-pl-s">+${t1Pct.toFixed(1)}%${t2 ? ' · +' + t2Pct.toFixed(1) + '%' : ''}</span></div>
        </div>
        <div class="ex-pl-cell ex-pl-meta">
          <span><b>${(T.rr_ratio || T.rr || 0).toFixed(1)}:1</b> R:R</span>
          <span>${(T.alloc_pct || 0).toFixed(0)}% size</span>
          <span>${(T.hold_period_min != null && T.hold_period_max != null) ? T.hold_period_min + '-' + T.hold_period_max + 'd hold' : 'hold —'}</span>
        </div>
      </div>
    </div>

    <div class="ex-col ex-col-signals">
      <div class="ex-col-h">SIGNALS</div>
      <div class="ex-sig-grid">
        <div class="ex-sig"><div class="ex-sig-l">RSI</div><div class="ex-sig-v">${T.rsi ? T.rsi.toFixed(0) : '—'}</div></div>
        <div class="ex-sig"><div class="ex-sig-l">RVOL</div><div class="ex-sig-v ${(T.rvol||0) > 1.5 ? 'up' : ''}">${T.rvol ? T.rvol.toFixed(2) + '×' : '—'}</div></div>
        <div class="ex-sig"><div class="ex-sig-l">RS</div><div class="ex-sig-v">${T.rs_rank || '—'}</div></div>
        <div class="ex-sig"><div class="ex-sig-l">ATR</div><div class="ex-sig-v">${T.atr_pct ? T.atr_pct.toFixed(1) + '%' : '—'}</div></div>
        <div class="ex-sig"><div class="ex-sig-l">MACD</div><div class="ex-sig-v ${T.macd_bullish ? 'up' : 'dn'}">${T.macd_bullish ? '↑' : '↓'}</div></div>
        <div class="ex-sig"><div class="ex-sig-l">EMA50</div><div class="ex-sig-v ${T.above_50ema ? 'up' : 'dn'}">${T.above_50ema ? '↑' : '↓'}</div></div>
      </div>
      <div class="ex-plan-divider"></div>
      <div class="ex-sig-line"><span class="ex-plan-l">Analyst</span><span class="${(T.analyst_consensus || '').toLowerCase().includes('buy') ? 'up' : (T.analyst_consensus || '').toLowerCase().includes('sell') ? 'dn' : ''}">${T.analyst_consensus && T.analyst_consensus !== '—' ? T.analyst_consensus : '—'}</span><span class="ex-plan-s">${T.analyst_target ? '$' + T.analyst_target.toFixed(2) : ''}${T.analyst_upside != null ? ' · ' + (T.analyst_upside >= 0 ? '+' : '') + T.analyst_upside.toFixed(0) + '%' : ''}</span></div>
      <div class="ex-sig-line"><span class="ex-plan-l">Checklist</span><span title="${reaction.map(i => (i.checked ? '✓ ' : '✗ ') + (i.item || '')).join('  ·  ')}">${reaction.map(i => `<span class="ex-rb-dot ${i.checked ? 'on' : 'off'}"></span>`).join('')} <b>${passedReactions}/${totalReactions}</b></span></div>
      <div class="ex-sig-line"><span class="ex-plan-l">Earnings</span><span class="${T.earn_days != null && T.earn_days <= 7 ? 'dn' : ''}">${T.earn_days != null && T.earn_days <= 7 ? '⚠ ' + T.earn_days + 'd' : T.earn_days != null ? T.earn_days + 'd' : 'no earnings'}</span></div>
    </div>

  </div>

  ${(() => {
    const sb = T.scoring_breakdown || {};
    const techS = T.tech_score || sb.tech_score || 0;
    const catS  = T.cat_score  || sb.cat_score  || 0;
    const rsS   = T.rs_score   || sb.rs_score   || 0;
    const smS   = T.sm_score   || sb.sm_score   || 0;
    const qS    = T.qg_score   || sb.qg_score   || 0;
    const rrR   = T.rr_ratio || T.rr || 0;

    const why = [];
    if (techS >= 25) why.push(`Strong technicals — ${techS}/35${T.macd_bullish ? ': MACD bullish' : ''}${T.above_50ema ? ', above EMA50' : ''}${T.rvol > 1.5 ? `, RVOL ${T.rvol.toFixed(1)}×` : ''}`);
    if (rsS  >= 14)  why.push(`RS leader vs SPY — rank ${T.rs_rank || '?'}/100`);
    if (catS >= 10)  why.push(`Catalyst tier ${T.catalyst_tier || '?'}: ${(T.catalyst_tags || []).slice(0,3).join(' · ') || 'setup confirmed'}`);
    if (T.entry_quality === 'FRESH' || T.entry_quality === 'PULLBACK') why.push(`${T.entry_quality.toLowerCase()} entry${T.entry_subtype ? ' — ' + T.entry_subtype : ''}`);
    if (rrR >= 3)    why.push(`R:R ${rrR.toFixed(1)}:1 (≥3 required)`);
    if (qS  >= 7)    why.push(`Quality fundamentals — ${qS}/10`);
    if (smS >= 10)   why.push(`Smart-money signal active (${smS}/15)`);

    const whyNot = [];
    if (techS < 18)  whyNot.push(`Weak technicals — only ${techS}/35`);
    if (rsS < 8)     whyNot.push(`Lagging RS (rank ${T.rs_rank || '?'}/100)`);
    if (rrR < 3)     whyNot.push(`R:R ${rrR.toFixed(1)}:1 below 3:1 threshold`);
    if (T.entry_quality === 'EXTENDED') whyNot.push(`Extended from entry zone — chasing risk`);
    if (T.entry_quality === 'MISSED')   whyNot.push(`Entry already missed — outside risk band`);
    if (T.earn_days != null && T.earn_days <= 7) whyNot.push(`Earnings in ${T.earn_days}d — gap risk`);
    if (qS <= 2)     whyNot.push(`Weak fundamentals (${qS}/10) — speculative`);
    if (smS <= 4)    whyNot.push(`Smart-money signal absent (${smS}/15)`);
    if (T.expected_pullback === 'Deep') whyNot.push(`Deep pullback expected — wider stop needed`);
    if (T.market_phase === 'Range')     whyNot.push(`Sideways regime — choppy fills likely`);
    if (T.short_pct && T.short_pct > 20) whyNot.push(`High short interest ${T.short_pct.toFixed(0)}% — squeeze risk`);

    const suggestion = (() => {
      if (v === 'BUY') {
        if (T.entry_quality === 'FRESH' || T.entry_quality === 'PULLBACK') {
          return `Enter at <b>$${eLo.toFixed(2)}–$${eHi.toFixed(2)}</b>, stop <b>$${stop.toFixed(2)}</b>. Size ${(T.alloc_pct || 5).toFixed(0)}% (~$${(25000 * (T.alloc_pct || 5) / 100).toFixed(0)} on $25K). Scale 50% at T1 <b>$${t1.toFixed(2)}</b>${t2 ? `, trail to T2 $${t2.toFixed(2)}` : ''}.`;
        }
        return `BUY but entry is ${T.entry_quality || 'unclear'}. Wait for pullback to <b>$${eLo.toFixed(2)}</b> (${(((eLo - px) / px) * 100).toFixed(1)}% from current).`;
      }
      if (v === 'WATCH') {
        return `Setup building. Wait for: ${T.decision_label ? T.decision_label.slice(0, 120) : 'price reclaim of $' + eLo.toFixed(2) + ' on RVOL > 1.5×'}.`;
      }
      if (v === 'SELL' || v === 'SHORT') {
        return `Short at <b>$${px.toFixed(2)}</b>, stop above <b>$${(stop || px * 1.05).toFixed(2)}</b>, cover T1 <b>$${(t1 || px * 0.92).toFixed(2)}</b>. Verify VIX > 25 + bear regime first.`;
      }
      return `Skip — fails gates. ${T.reject_reason ? T.reject_reason.slice(0, 120) : 'Score below threshold for current regime.'}`;
    })();

    return `<div class="ex-verdict-row">
      <div class="ex-vd-tile ex-vd-why">
        <div class="ex-vd-l">WHY</div>
        ${why.length ? `<ul>${why.slice(0,5).map(x=>`<li>${x}</li>`).join('')}</ul>` : '<div class="ex-vd-empty">No strong positive signals.</div>'}
      </div>
      <div class="ex-vd-tile ex-vd-whynot">
        <div class="ex-vd-l">WHY NOT</div>
        ${whyNot.length ? `<ul>${whyNot.slice(0,5).map(x=>`<li>${x}</li>`).join('')}</ul>` : '<div class="ex-vd-empty">No major risk flags.</div>'}
      </div>
      <div class="ex-vd-tile ex-vd-sug">
        <div class="ex-vd-l">SUGGESTION · ${vLabel}</div>
        <div class="ex-vd-sug-body">${suggestion}</div>
        <div class="ex-actions">
          <button class="btn primary ex-act-primary" onclick="event.stopPropagation();window.location.href='elite-detail.html?t=${T.ticker}&from=expand'">Full Analysis →</button>
          <div class="ex-act-mini">
            <button class="ex-mini-btn" onclick="event.stopPropagation();_toggleStar(event,'${T.ticker}',null);renderFloorScanner();" title="Watch">★</button>
            <button class="ex-mini-btn" onclick="event.stopPropagation();window.open('https://www.tradingview.com/symbols/${T.ticker}/','_blank')" title="TradingView">TV ↗</button>
          </div>
        </div>
      </div>
    </div>`;
  })()}

  <div class="ex-row2">
    <div class="ex-col ex-chart-wrap">
      <div class="ex-col-h">PRICE · 60 DAYS <span class="ex-chart-legend"><span class="lg-stop">stop</span> <span class="lg-entry">entry</span> <span class="lg-t1">T1</span> <span class="lg-t2">T2</span></span></div>
      ${(() => {
        const bars = T.ohlcv || T.bars || [];
        if (!Array.isArray(bars) || bars.length < 5) {
          return '<div class="ex-chart-empty">No chart data</div>';
        }
        const closes = bars.slice(-60).map(b => b.c || b.close).filter(v => v != null);
        if (closes.length < 5) return '<div class="ex-chart-empty">No chart data</div>';
        const maxRng = Math.max(...closes, t1, t2 || 0, eHi);
        const minRng = Math.min(...closes, stop, eLo);
        const rng = (maxRng - minRng) || 1;
        const pad = 4;
        const W = 100, H = 100;
        const yFor = v => H - pad - ((v - minRng) / rng) * (H - pad * 2);
        const xs = closes.map((_, i) => (i / (closes.length - 1)) * W);
        const pts = closes.map((c, i) => `${xs[i].toFixed(2)},${yFor(c).toFixed(2)}`).join(' ');
        const last = closes[closes.length - 1];
        const up = last >= closes[0];
        const lineColor = up ? 'var(--pass)' : 'var(--fail)';
        const lvlLine = (val, color, label) => {
          const y = yFor(val);
          if (y < pad || y > H - pad) return '';
          return `<line x1="0" x2="${W}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}" stroke="${color}" stroke-width="0.5" stroke-dasharray="1.5 1.5" opacity="0.7"/>`;
        };
        return `<svg class="ex-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
          <defs>
            <linearGradient id="exg-${T.ticker}" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <polygon fill="url(#exg-${T.ticker})" points="0,${H} ${pts} ${W},${H}"/>
          <polyline fill="none" stroke="${lineColor}" stroke-width="1.2" stroke-linejoin="round" points="${pts}"/>
          ${lvlLine(stop, 'var(--fail)')}
          ${lvlLine(eLo, 'var(--info)')}
          ${eHi !== eLo ? lvlLine(eHi, 'var(--info)') : ''}
          ${t1 ? lvlLine(t1, 'var(--pass)') : ''}
          ${t2 ? lvlLine(t2, 'var(--pass)') : ''}
          <circle cx="${xs[xs.length - 1].toFixed(2)}" cy="${yFor(last).toFixed(2)}" r="1.6" fill="${lineColor}"/>
        </svg>`;
      })()}
    </div>

    <div class="ex-col ex-score-breakdown">
      <div class="ex-col-h">SCORE BREAKDOWN</div>
      ${(() => {
        const sb = T.scoring_breakdown || {};
        const pillars = [
          { l: 'Technicals', v: T.tech_score || sb.tech_score || 0, m: T.tech_max || 35, c: 'var(--pass)' },
          { l: 'Catalyst',   v: T.cat_score  || sb.cat_score  || 0, m: 20, c: 'var(--info)' },
          { l: 'RS',         v: T.rs_score   || sb.rs_score   || 0, m: 20, c: 'var(--info)' },
          { l: 'Smart $',    v: T.sm_score   || sb.sm_score   || 0, m: 15, c: 'var(--warn)' },
          { l: 'Quality',    v: T.qg_score   || sb.qg_score   || (T.fund_score || 0), m: T.fund_max || 10, c: 'var(--warn)' },
        ];
        return `<div class="ex-pillars">${pillars.map(p => {
          const pct = Math.max(0, Math.min(100, (p.v / p.m) * 100));
          return `<div class="ex-pill"><span class="ex-pill-l">${p.l}</span><div class="ex-pill-bar"><div class="ex-pill-fill" style="width:${pct.toFixed(0)}%;background:${p.c}"></div></div><span class="ex-pill-v">${p.v}<span style="opacity:0.5;font-weight:500"> /${p.m}</span></span></div>`;
        }).join('')}</div>`;
      })()}
    </div>
  </div>

  ${T.thesis ? `<div class="ex-thesis"><span class="ex-thesis-l">THESIS</span> ${T.thesis}</div>` : ''}`;
}
