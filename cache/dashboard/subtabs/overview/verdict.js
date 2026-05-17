// subtabs/overview/verdict.js — extracted from elite-detail.html (renderVerdict 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const v = T.verdict || 'WATCH';
  // Honor tail-filter / entry-quality demotion (set by fdPopulateHeader)
  const isDemoted = window.__T_DEMOTED;
  const demoteReason = window.__T_DEMOTE_REASON || '';
  const effectiveV = (isDemoted && v === 'BUY') ? 'WAIT' : v;
  const isBuy = effectiveV === 'BUY';
  const cardCls = isBuy ? '' : 'warn';
  const accent = isBuy ? 'var(--pass)' : 'var(--warn)';
  // K-extra (2026-05-09): canonical_trade_plan first, then T fields. Re-bind onto
  // T so the dozens of references downstream auto-pick canonical numbers without
  // per-line rewrites. Keeps the audit trail tight.
  const ctp = T?.canonical_trade_plan;
  if (ctp) {
    if (ctp.stop != null)        T.stop       = ctp.stop;
    if (ctp.target1 != null)     T.target1    = ctp.target1;
    if (ctp.target2 != null)     T.target2    = ctp.target2;
    if (ctp.entry?.low != null)  T.entry_low  = ctp.entry.low;
    if (ctp.entry?.high != null) T.entry_high = ctp.entry.high;
    if (ctp.risk?.rr_ratio != null) T.rr_ratio = ctp.risk.rr_ratio;
  }
  // Compute real R:R from CURRENT price (not cached entry_low)
  const curPrice = T.price || T.entry_low || 0;
  const realRR = (curPrice && T.stop && T.target1 && curPrice > T.stop && T.target1 > curPrice)
    ? (T.target1 - curPrice) / (curPrice - T.stop) : null;
  const cachedRR = T.rr_ratio || 0;
  const rrMismatch = realRR != null && cachedRR && Math.abs(realRR - cachedRR) / cachedRR > 0.15;
  const headlines = {
    BUY:   `<span class="accent">BUY</span> — entry zone live around $${px(T.entry_low)}.`,
    WAIT:  `<span class="accent" style="color:#eab308">WAIT</span> — ${demoteReason}. Setup is real but entry timing is wrong.`,
    WATCH: `<span class="accent">WATCH</span> — wait for confirmation at $${px(T.entry_low)}.`,
    AVOID: `<span class="accent">AVOID</span> — gates not clear today.`,
    SELL:  `<span class="accent">SELL</span> — bearish setup.`,
  };
  const headline = headlines[effectiveV] || `<span class="accent">${effectiveV}</span> — review.`;
  const sub = `${T.setup_family || 'Setup'} · ${T.sector || ''}. Score ${T.score}/100 with ${T.tech_score || 0}+${T.fund_score || 0}+${T.sent_score || 0}+${T.smc_score || 0} pillar split. ${T.above_50ema ? 'Trend stacked above EMA50.' : 'Below EMA50 — context risk.'} ${T.earn_days != null && T.earn_days <= 14 ? `Earnings ${T.earn_days}d out — size to survive a miss.` : 'No imminent earnings.'}`;

  // Demoted: flip the action plan from "enter now" to "wait for pullback"
  const pullbackZone = (T.primary_zone_low && T.primary_zone_high)
    ? `$${px(T.primary_zone_low)}–$${px(T.primary_zone_high)}`
    : (T.shallow_zone_low && T.shallow_zone_high) ? `$${px(T.shallow_zone_low)}–$${px(T.shallow_zone_high)}`
    : `$${px(T.entry_low)}`;
  const actions = isDemoted ? [
    {n:1, what:`<b>DO NOT BUY at $${px(curPrice)}</b> — entry too extended`, meta:`Real R:R at current price: ${(realRR ?? 0).toFixed(2)} : 1 (target ≥ 3:1)`, go:'WAIT'},
    {n:2, what:`Set price alert at <b>${pullbackZone}</b> — preferred re-entry zone`, meta:'ALERT · wait for pullback', go:'WATCH'},
    {n:3, what:`If pullback hits: re-evaluate (regime, news, earnings) before entering`, meta:'RE-CHECK · don\'t blindly enter on touch', go:'PLAN'},
    {n:4, what:`If price runs to $${px(T.target1)} without pullback: <b>missed it</b> — let it go`, meta:'DISCIPLINE · no FOMO entries', go:'PASS'},
  ] : [
    {n:1, what:`Enter limit at <b>$${px((T.entry_low + T.entry_high)/2)}</b> — inside entry zone $${px(T.entry_low)}–$${px(T.entry_high)}`, meta:`LIMIT · zone · ${cachedRR?.toFixed(1) || '—'} R:R restored`, go:'STAGE'},
    {n:2, what:`Hard stop at <b>$${px(T.stop)}</b> immediately on fill`, meta:'STOP · GTC · non-negotiable', go:'SET'},
    {n:3, what:`Trim 50% at T1 <b>$${px(T.target1)}</b>, move stop to BE`, meta:`LIMIT · lock partial · realize +${(((T.target1 - T.entry_low)/(T.entry_low - T.stop))).toFixed(1)}R`, go:'PLAN'},
    {n:4, what:`Watch ${T.earn_days != null && T.earn_days <= 14 ? `earnings in +${T.earn_days}d` : 'sector RS vs SPY'} before entry`, meta: T.earn_days != null && T.earn_days <= 14 ? 'BINARY · earn date · trim plan ready' : 'CONTEXT · regime watch', go:'CHECK'},
  ];

  // Demotion banner if applicable
  const demoteBanner = isDemoted ? `
    <div style="background:rgba(234,179,8,0.08);border:1px solid #eab308;border-left:4px solid #eab308;border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:13px;color:#fde68a">
      <div style="font-weight:700;color:#eab308;letter-spacing:.05em;text-transform:uppercase;font-size:11px;margin-bottom:6px">⚠ System Demoted This Signal</div>
      <div style="line-height:1.5"><b>${demoteReason}.</b> The setup quality is real (score ${T.score || 0}, ${T.setup_family || 'setup'}), but the system says <b style="color:#fde68a">do not buy at current price</b>. ${T.primary_zone_low && T.primary_zone_high ? `Wait for pullback to <b style="color:#fde68a;font-family:var(--mono)">$${px(T.primary_zone_low)}–$${px(T.primary_zone_high)}</b> for proper entry.` : 'Wait for pullback to a better price.'}</div>
      ${realRR != null && rrMismatch ? `<div style="margin-top:8px;padding-top:8px;border-top:1px dashed rgba(234,179,8,0.3);font-size:12px"><b style="color:#fde68a">Real R:R at current price ($${px(curPrice)}):</b> <span style="font-family:var(--mono);color:#eab308">${realRR.toFixed(2)} : 1</span> (cached shows ${cachedRR.toFixed(2)} — that's the entry-zone R:R, not what you'd actually get)</div>` : ''}
    </div>` : '';

  $('verdictBody').innerHTML = `
  ${demoteBanner}
  <div class="verdict-grid">
    <div class="verdict-card ${cardCls}">
      <div class="verdict-eyebrow">
        <span class="lbl">Conviction</span>
        <span class="verdict-score"><b>${T.score || 0}</b><s>/100</s></span>
        <span class="lbl" style="color:var(--ink-3)">·</span>
        <span class="lbl" style="color:${accent}">${effectiveV}</span>
      </div>
      <h1 class="verdict-headline">${headline}</h1>
      <p class="verdict-sub">${sub}</p>
      <div class="verdict-meta">
        <div class="cell"><span class="lbl">R:R ${realRR != null ? '(real, now)' : 'to T1'}</span><span class="v ${(realRR ?? cachedRR) >= 2.5 ? 'pass' : (realRR ?? cachedRR) >= 1.5 ? 'warn' : 'fail'}">${(realRR ?? cachedRR ?? 0).toFixed(2)} : 1</span></div>
        <div class="cell"><span class="lbl">RS Rank</span><span class="v ${T.rs_rank >= 80 ? 'pass' : T.rs_rank >= 50 ? 'warn' : 'fail'}">${T.rs_rank || '—'}</span></div>
        <div class="cell"><span class="lbl">Entry quality</span><span class="v ${isBuy ? 'pass' : 'warn'}">${T.entry_quality || (isBuy ? 'Optimal' : 'Wait')}</span></div>
        <div class="cell"><span class="lbl">RVOL</span><span class="v ${T.rvol >= 1.2 ? 'pass' : 'warn'}">${T.rvol ? T.rvol.toFixed(2) + '×' : '—'}</span></div>
      </div>
    </div>
    <div class="actions-card">
      <h3>What to do next</h3>
      ${actions.map(a => `
        <div class="action-row">
          <span class="num-circle">${a.n}</span>
          <div class="action-body"><div class="what">${a.what}</div><div class="meta">${a.meta}</div></div>
          <span class="go">${a.go}</span>
        </div>`).join('')}
    </div>
  </div>
  ${_renderDecisionEnginePanels()}`;
}

export function dispose() { /* no-op */ }
