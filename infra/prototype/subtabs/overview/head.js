// subtabs/overview/head.js — extracted from elite-detail.html (renderHead 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  // Top row 1 — ticker block
  $('sym').textContent = T.ticker;
  // Ticker logo from EODHD (graceful fallback if not found)
  const logoEl = $('tickerLogo');
  if (logoEl) {
    const logoUrl = `https://eodhd.com/img/logos/US/${T.ticker}.png`;
    logoEl.src = logoUrl;
    logoEl.style.display = 'block';
    logoEl.onerror = () => { logoEl.style.display = 'none'; };
  }
  // Hide redundant name when it's just the ticker (no real company name resolved)
  const _hasRealName = T.name && T.name !== T.ticker && T.name.length > 4;
  $('name').textContent = _hasRealName ? `· ${T.name}` : '';
  // Build sector · industry chain, skip empties cleanly
  const _sectInd = [T.sector, T.industry].filter(s => s && s !== '—').join(' · ') || '—';
  $('sect').textContent = _sectInd;
  const stars = Math.min(5, Math.max(1, Math.round((T.score || 0) / 20)));
  $('stars').innerHTML = '★'.repeat(stars) + '<span style="color:var(--ink-3)">' + '☆'.repeat(5 - stars) + '</span>';

  // Verdict tile
  const v = T.verdict || T.stage || 'AVOID';
  $('verdictV').textContent = v;
  $('verdictTile').className = 'verdict-tile ' + v.toLowerCase();

  // Score tile
  const sc = T.score || 0;
  const scEl = $('scoreV');
  scEl.textContent = sc;
  scEl.className = 'v ' + (sc >= 75 ? 'high' : sc >= 60 ? 'med' : 'low');

  // Price + change (live-updateable)
  _renderHeaderPrice(T.price, T.pct_chg);

  // Tags row
  const tags = [];
  if (T.setup_family)      tags.push(`<span class="pill">${T.setup_family}</span>`);
  if (T.rs_rank != null)   tags.push(`<span class="pill ${T.rs_rank >= 80 ? 'pass' : T.rs_rank >= 50 ? 'warn' : ''}">RS ${T.rs_rank}</span>`);
  if (T.earn_days != null && T.earn_days <= 14) {
    tags.push(`<span class="pill ${T.earn_days <= 7 ? 'fail' : 'warn'}">EARN +${T.earn_days}d</span>`);
  }
  if (T.regime) tags.push(`<span class="pill">${T.regime.replace(/_/g,' ').toUpperCase()}</span>`);
  $('tags').innerHTML = tags.join('');

  // Action button
  const isBuy = v === 'BUY';
  $('armBtn').textContent = `${v} · ${sc}`;
  $('armBtn').classList.toggle('primary', isBuy);

  // Top row 2 — dense data strip
  const tp = T.trade_plan || {};
  const stop = T.stop ?? tp.stop;
  const t1 = T.target1 ?? tp.target1;
  const t2 = T.target2 ?? tp.target2;
  const eLo = T.entry_low ?? tp.entry_low;
  const eHi = T.entry_high ?? tp.entry_high;
  const rrT1 = (t1 && eLo && stop) ? ((t1 - eLo) / Math.max(0.01, eLo - stop)) : null;
  const stopPct = (stop && eLo) ? (((stop - eLo) / eLo) * 100) : null;
  const t1Pct   = (t1 && eLo)   ? (((t1   - eLo) / eLo) * 100) : null;
  const t2Pct   = (t2 && eLo)   ? (((t2   - eLo) / eLo) * 100) : null;
  const fr = T.fund_real || {};
  const ana = T.analyst || {};
  const ins = T.insider || {};
  const inZone = T.price && eLo && eHi && T.price >= eLo && T.price <= eHi;
  const fmt = (v, d=2) => v == null ? '—' : Number(v).toFixed(d);
  const fmtP = (v, d=1) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const cls = (cond, t='up', f='dn') => cond ? t : f;
  $('dataStrip').innerHTML = `
    <div class="strip-item"><span class="lbl">Entry</span><span class="v ${inZone ? 'up' : 'warn'}">$${fmt(eLo)}–${fmt(eHi)}</span><span class="sub">${inZone ? 'IN ZONE' : T.price > eHi ? 'extended' : 'approaching'}</span></div>
    <div class="strip-item"><span class="lbl">Stop</span><span class="v dn">$${fmt(stop)}</span><span class="sub">${fmtP(stopPct)}</span></div>
    <div class="strip-item"><span class="lbl">T1</span><span class="v warn">$${fmt(t1)}</span><span class="sub">${fmtP(t1Pct)}</span></div>
    <div class="strip-item"><span class="lbl">T2</span><span class="v" style="color:var(--info)">${t2 ? '$'+fmt(t2) : '—'}</span><span class="sub">${fmtP(t2Pct)}</span></div>
    <div class="strip-item"><span class="lbl">R:R T1</span><span class="v ${rrT1 == null ? 'dim' : rrT1 >= 3 ? 'up' : rrT1 >= 2 ? 'warn' : 'dn'}">${rrT1 ? '1:' + rrT1.toFixed(1) : '—'}</span><span class="sub">${rrT1 >= 3 ? 'strong' : rrT1 >= 2 ? 'OK' : 'weak'}</span></div>
    <div class="strip-item"><span class="lbl">RVOL</span><span class="v ${T.rvol > 1.2 ? 'up' : 'dim'}">${T.rvol ? T.rvol.toFixed(1) + '×' : '—'}</span><span class="sub">${T.rvol > 1.2 ? 'expansion' : 'normal'}</span></div>
    <div class="strip-item"><span class="lbl">RSI</span><span class="v ${T.rsi == null ? 'dim' : T.rsi > 70 ? 'warn' : T.rsi < 30 ? 'warn' : T.rsi >= 50 ? 'up' : 'dim'}">${T.rsi ? T.rsi.toFixed(0) : '—'}</span><span class="sub">${T.rsi > 70 ? 'overbought' : T.rsi < 30 ? 'oversold' : 'neutral'}</span></div>
    <div class="strip-item"><span class="lbl">ATR</span><span class="v">${T.atr_pct ? T.atr_pct.toFixed(1) + '%' : '—'}</span><span class="sub">daily range</span></div>
    <div class="strip-item"><span class="lbl">Rev</span><span class="v ${fr.rev_growth_pct == null ? 'dim' : fr.rev_growth_pct >= 8 ? 'up' : 'warn'}">${fmtP(fr.rev_growth_pct)}</span><span class="sub">YoY</span></div>
    <div class="strip-item"><span class="lbl">Margin</span><span class="v ${fr.net_margin_pct == null ? 'dim' : fr.net_margin_pct >= 10 ? 'up' : 'warn'}">${fmtP(fr.net_margin_pct)}</span><span class="sub">net</span></div>
    <div class="strip-item"><span class="lbl">PT</span><span class="v">${ana.target_mean ? '$'+ana.target_mean.toFixed(2) : '—'}</span><span class="sub ${ana.upside_pct >= 0 ? 'up' : 'dn'}">${fmtP(ana.upside_pct)}</span></div>
    <div class="strip-item"><span class="lbl">Insider</span><span class="v ${(ins.buys||0) > (ins.sells||0) ? 'up' : (ins.sells||0) > (ins.buys||0) ? 'dn' : 'dim'}">${ins.buys || 0}↑ ${ins.sells || 0}↓</span><span class="sub">${ins.sentiment || 'neutral'}</span></div>
    <div class="strip-item"><span class="lbl">Tech</span><span class="v warn">${T.tech_score != null ? T.tech_score : '—'}</span><span class="sub">/${T.tech_max || 38}</span></div>
    <div class="strip-item"><span class="lbl">Fund</span><span class="v warn">${T.fund_score != null ? T.fund_score : '—'}</span><span class="sub">/${T.fund_max || 30}</span></div>
    ${T.beta != null ? `<div class="strip-item"><span class="lbl">Beta</span><span class="v ${T.beta > 1.5 ? 'warn' : 'dim'}">${T.beta.toFixed(2)}</span><span class="sub">vs SPX</span></div>` : ''}
    ${T.market_cap != null ? `<div class="strip-item"><span class="lbl">Mkt Cap</span><span class="v">${T.market_cap >= 1e9 ? '$' + (T.market_cap/1e9).toFixed(1) + 'B' : '$' + (T.market_cap/1e6).toFixed(0) + 'M'}</span><span class="sub">${T.float_shares ? (T.float_shares/1e6).toFixed(0) + 'M float' : ''}</span></div>` : ''}
    ${T.week52_high != null ? `<div class="strip-item"><span class="lbl">52W</span><span class="v dim">$${T.week52_low?.toFixed(2)} – $${T.week52_high?.toFixed(2)}</span><span class="sub">${T.price && T.week52_high ? ((T.price/T.week52_high - 1)*100).toFixed(1) + '% from hi' : ''}</span></div>` : ''}
  `;
}

export function dispose() { /* no-op */ }
