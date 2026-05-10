// tabs/scanner/row.js — per-ticker row HTML builder.
// One row = score arc + ticker block + 2-line chip stack + price + Δ% + R:R +
// setup + sparkline + extra columns + star toggle.
// Returns an HTML string per row; the entry orchestrator joins them.

import { buildSparkPath } from './sparkline.js';

export function buildRowHtml(r, ctx) {
  const {
    watched, tier, eq,
    setupFamilyOf, scoreRing, logoHtml, starsHtml,
    SC2_EXTRA_COLS, sc2FmtExtra,
  } = ctx;

  const v = r.stage || r.verdict || 'WATCH';
  const c = r.pct_chg || 0;
  const upDn = c > 0 ? 'up' : c < 0 ? 'dn' : 'dim';
  const rr = r.rr || 0;
  const rrCls = rr >= 3 ? 'rr-strong' : rr >= 2 ? 'warn' : 'rr-weak';
  const pctCls = c >= 5 ? `${upDn} pct-strong-up`
              : c <= -5 ? `${upDn} pct-strong-down`
              : (Math.abs(c) > 0.01 ? upDn : '');
  const spark = buildSparkPath(r.ticker, r.score, c);
  const setupShort  = (r.setup || r.setup_family || '').slice(0, 24);
  const setupFamily = setupFamilyOf(r.setup || r.setup_family);
  const setupIcon   = { impulse: '⚡', breakout: '▲', trend: '→', special: '★', other: '·' }[setupFamily];
  const score       = r.score || 0;
  const isWatched   = watched.includes(r.ticker);
  const sectorMain  = (r.sector || '').split(/[/]/)[0].trim() || '—';

  const chipsHtml = _buildChips(r, v, tier, eq, score);

  return `<div class="fs-st-row sc2-row" data-ticker="${r.ticker}" data-verdict="${v}" onclick="_handleRowClick(event, '${r.ticker}')">
    <div class="sc2-cell-score ${v}">
      ${scoreRing(score, v)}
    </div>
    <div class="sc2-cell-tk">
      <div class="sc2-tk-row">
        ${logoHtml(r.ticker, 18)}
        <span class="sc2-tk">${r.ticker}</span>
        ${starsHtml(r.star_rating)}
      </div>
      <div class="sc2-tk-name">
        <span class="sc2-name">${(r.name || '').slice(0, 28) || '—'}</span>
        <span class="sc2-sector">${sectorMain}</span>
      </div>
    </div>
    <div class="sc2-cell-chips">${chipsHtml || '<span class="sc2-chips-empty">—</span>'}</div>
    <div class="sc2-cell r"><span class="sc2-num" title="${(() => { const d = (c/100)*(r.price||0); return (d>=0?'+$':'−$') + Math.abs(d).toFixed(2); })()}">$${(r.price || 0).toFixed(2)}</span></div>
    <div class="sc2-cell r ${pctCls}"><span class="sc2-num">${c >= 0 ? '+' : ''}${c.toFixed(2)}%</span></div>
    <div class="sc2-cell r ${rrCls}"><span class="sc2-num"><b>${rr.toFixed(1)}</b>:1${r._rr_inconsistent ? ' <span title="R:R math inconsistent — see Plan tab" style="color:var(--fail);font-weight:800;margin-left:3px">⚠</span>' : ''}</span></div>
    <div class="sc2-cell sc2-cell-setup"><span class="sc2-setup-icon" data-family="${setupFamily}">${setupIcon}</span><span class="sc2-setup-text">${setupShort || '—'}</span></div>
    <div class="sc2-cell sc2-cell-spark"><svg viewBox="0 0 60 22" preserveAspectRatio="none" class="sc2-spark sc2-spark-${spark.dir}">
      <defs><linearGradient id="spark-grad-${r.ticker}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity="0.35"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>
      <path class="area" d="${spark.areaPath}" fill="url(#spark-grad-${r.ticker})"/>
      <polyline class="line" points="${spark.points}"/>
      <circle class="dot" cx="${spark.lastX.toFixed(1)}" cy="${spark.lastY.toFixed(1)}" r="2"/>
    </svg></div>
    ${[...SC2_EXTRA_COLS].map(k => {
      const f = sc2FmtExtra(k, r);
      const subEl = f.sub ? `<span class="sc2-extra-sub">${f.sub}</span>` : '';
      return `<div class="sc2-cell r ${f.cls} sc2-extra-cell"><span class="sc2-num">${f.txt}</span>${subEl}</div>`;
    }).join('')}
    <div class="sc2-cell sc2-cell-actions" onclick="event.stopPropagation()">
      <button class="sc2-star ${isWatched ? 'watched' : ''}" title="${isWatched ? 'Remove from watchlist (F)' : 'Add to watchlist (F)'}" onclick="_toggleStar(event, '${r.ticker}', this)">${isWatched ? '★' : '☆'}</button>
    </div>
  </div>`;
}

// Build the 2-line chip stack: primary (verdict / conviction / setup family /
// catalyst / hot) + secondary (entry quality / subtype / pullback / zone /
// timing / hold / earnings warning).
function _buildChips(r, v, tier, eq, score) {
  const primary   = [];
  const secondary = [];
  const stage = (r.stage || v || '').toUpperCase();

  // L1.1 NEW (animated, far left)
  if (window._SC2_NEW_TICKERS && window._SC2_NEW_TICKERS.has(r.ticker)) {
    primary.push(`<span class="rc rc-new" title="New since last scan">NEW</span>`);
  }
  // L1.2 Verdict
  if      (stage === 'BUY')   primary.push(`<span class="rc rc-buy" title="BUY signal — pre-trade gates passed, conviction tier assigned">BUY</span>`);
  else if (stage === 'WATCH') primary.push(`<span class="rc rc-watch" title="WATCH list — setup building, no position taken yet">WATCH</span>`);
  else if (stage === 'SELL')  primary.push(`<span class="rc rc-sell" title="SHORT signal — bear setup confirmed">SHORT</span>`);
  // L1.3 Conviction tier
  if (tier && tier !== 'WATCH') primary.push(`<span class="rc rc-tier rc-tier-${tier.toLowerCase()}" title="Conviction tier — sizing">${tier}</span>`);
  // L1.4 Setup family — icon + short name
  const setupTxt = (r.setup || r.setup_family || '');
  const _sf = (() => {
    const s = setupTxt.toLowerCase();
    if (s.includes('impulse'))  return ['⚡', 'Imp'];
    if (s.includes('breakout')) return ['▲', 'Bkt'];
    if (s.includes('trend'))    return ['→', 'Trd'];
    if (s.includes('special'))  return ['★', 'Spc'];
    return null;
  })();
  if (_sf) primary.push(`<span class="rc rc-fam" title="${setupTxt}">${_sf[0]} ${_sf[1]}</span>`);
  // L1.5 Catalyst tier
  if (r.catalyst_tier) primary.push(`<span class="rc rc-cat${r.catalyst_tier}" title="Catalyst tier">C${r.catalyst_tier}</span>`);
  // L1.6 Hot
  if (score >= 90 && v === 'BUY') primary.push(`<span class="rc rc-hot" title="Score ≥ 90">🔥</span>`);

  // L2.1 Entry quality
  if (eq && eq !== 'VALID') {
    const ecls   = eq === 'FRESH' || eq === 'PULLBACK' ? 'rc-eq-good' : 'rc-eq-bad';
    const eShort = eq === 'PULLBACK' ? 'PB' : eq === 'EXTENDED' ? 'Ext' : eq === 'MISSED' ? 'Miss' : eq.charAt(0) + eq.slice(1).toLowerCase();
    secondary.push(`<span class="rc ${ecls}" title="${eq}">${eShort}</span>`);
  }
  // L2.2 Entry subtype
  if (r.entry_subtype) {
    const sub      = String(r.entry_subtype);
    const subShort = sub.replace('Pocket Pivot Entry', 'Pocket').replace('Pivot Entry', 'Pivot').replace('Breakout Add', 'BO Add').slice(0, 12);
    secondary.push(`<span class="rc rc-sub" title="${sub}">${subShort}</span>`);
  }
  // L2.3 Expected pullback
  if (r.expected_pullback) {
    const pb   = String(r.expected_pullback);
    const pcls = pb === 'Shallow' ? 'rc-pb-good' : pb === 'Deep' ? 'rc-pb-bad' : 'rc-pb-mid';
    secondary.push(`<span class="rc ${pcls}" title="${pb} pullback">${pb}</span>`);
  }
  // L2.4 Zone quality
  const zq = r.zone_quality;
  const zqLabel = (zq && typeof zq === 'object') ? zq.label : (typeof zq === 'string' ? zq : '');
  if (zqLabel) {
    const zcls = zqLabel === 'Strong' ? 'rc-zone-good' : zqLabel === 'Weak' ? 'rc-zone-bad' : 'rc-zone-mid';
    secondary.push(`<span class="rc ${zcls}" title="Zone quality: ${zqLabel}">Z·${zqLabel.charAt(0)}</span>`);
  }
  // L2.5 Timing
  if (r.entry_timing) {
    const t    = String(r.entry_timing);
    const tcls = t === 'Value' ? 'rc-tim-good' : t === 'Late' ? 'rc-tim-bad' : 'rc-tim-mid';
    secondary.push(`<span class="rc ${tcls}" title="Entry timing: ${t}">T·${t.charAt(0)}</span>`);
  }
  // L2.6 Hold period
  if (r.hold_period_min != null && r.hold_period_max != null) {
    secondary.push(`<span class="rc rc-hold" title="Hold guide">${r.hold_period_min}-${r.hold_period_max}d</span>`);
  }
  // L2.7 Earnings warning
  if (r.earn_days != null && r.earn_days <= 7) {
    secondary.push(`<span class="rc rc-earn" title="Earnings in ${r.earn_days} days">⚠${r.earn_days}d</span>`);
  }

  const l1 = primary.length   ? `<div class="sc2-chiprow">${primary.join('')}</div>`   : '';
  const l2 = secondary.length ? `<div class="sc2-chiprow">${secondary.join('')}</div>` : '';
  return l1 + l2;
}
