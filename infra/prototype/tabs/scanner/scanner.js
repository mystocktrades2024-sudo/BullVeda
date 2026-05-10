// tabs/scanner/scanner.js — extracted from dashboard.html (renderFloorScanner 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  if (!DATA) return;
  const all = _fsAllRows();
  let rows = all;
  // Mode filter (SWING / POSITION / INVEST). Default mode is 'swing' — current
  // scoring engine is calibrated for 2–5d holds. POSITION/INVEST engines are
  // pending (Phase B). For now those tabs show the placeholder below.
  const mode = FS_STATE.mode || 'swing';
  if (mode === 'swing') {
    rows = rows.filter(r => !r.mode || r.mode === 'swing');
  } else {
    rows = rows.filter(r => r.mode === mode);
  }
  if (FS_STATE.verdict !== 'ALL') {
    rows = rows.filter(r => (r.stage || r.verdict) === FS_STATE.verdict);
  }
  if (FS_STATE.sector !== 'ALL') {
    rows = rows.filter(r => ((r.sector || '').toUpperCase()).includes(FS_STATE.sector.slice(0, 4)));
  }
  if (FS_STATE.setupFamily !== 'ALL') {
    rows = rows.filter(r => _setupFamilyOf(r.setup || r.setup_family) === FS_STATE.setupFamily);
  }
  if (FS_STATE.tier !== 'ALL') {
    rows = rows.filter(r => {
      const score = r.score || 0;
      const t = r.conviction_tier || (score >= 88 ? 'T1' : score >= 78 ? 'T2' : score >= 70 ? 'T3' : 'WATCH');
      return t === FS_STATE.tier;
    });
  }
  if (FS_STATE.entryQ !== 'ALL') {
    rows = rows.filter(r => (r.entry_quality || '').toUpperCase() === FS_STATE.entryQ);
  }
  if (FS_STATE.perfPattern && FS_STATE.perfPattern !== 'ALL') {
    rows = rows.filter(r => window._matchesPerfPattern(r, FS_STATE.perfPattern));
  }
  if (FS_STATE.capBucket && FS_STATE.capBucket !== 'ALL') {
    rows = rows.filter(r => (r.cap_bucket || '') === FS_STATE.capBucket);
  }
  if (FS_STATE.priceTier && FS_STATE.priceTier !== 'ALL') {
    rows = rows.filter(r => {
      const p = r.price || 0;
      if (FS_STATE.priceTier === 'lt100') return p < 100;
      if (FS_STATE.priceTier === 'lt250') return p >= 100 && p < 250;
      if (FS_STATE.priceTier === 'gt250') return p >= 250;
      return true;
    });
  }
  if (FS_STATE.scoreMin > 0 || FS_STATE.scoreMax < 100) {
    rows = rows.filter(r => {
      const s = r.score || 0;
      return s >= FS_STATE.scoreMin && s <= FS_STATE.scoreMax;
    });
  }
  if (FS_STATE.rrMin > 0) {
    rows = rows.filter(r => (r.rr || 0) >= FS_STATE.rrMin);
  }
  if (FS_STATE.watchOnly) {
    const wl = new Set(_getWatchlist());
    rows = rows.filter(r => wl.has(r.ticker));
  }
  if (FS_STATE.hideEarnings) {
    rows = rows.filter(r => r.earn_days == null || r.earn_days > 7);
  }
  // Sort
  rows = rows.slice().sort((a, b) => {
    const av = a[FS_STATE.sortKey] ?? 0, bv = b[FS_STATE.sortKey] ?? 0;
    const cmp = (typeof av === 'string') ? String(av).localeCompare(String(bv)) : (av - bv);
    return FS_STATE.sortDir === 'desc' ? -cmp : cmp;
  });

  // Header text
  setText('fsScannerCt', `${rows.length} of ${all.length}`);
  setText('fsScannerSub', `last refresh ${new Date(DATA.run_timestamp || Date.now()).toLocaleString('en-US', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}`);
  const fc = document.getElementById('sc2FootCt');
  if (fc) fc.textContent = `Showing ${rows.length} of ${all.length} signals`;

  // Update sort arrow on headers
  document.querySelectorAll('.sc2-th.sortable').forEach(th => {
    const k = th.dataset.sort;
    const arrow = th.querySelector('.sc2-sort');
    if (arrow) {
      arrow.textContent = (k === FS_STATE.sortKey) ? (FS_STATE.sortDir === 'desc' ? '▼' : '▲') : '';
      th.classList.toggle('active', k === FS_STATE.sortKey);
    }
  });

  // Update KPI tiles + active filters chip + density class
  _sc2RenderKpis();
  _sc2RenderActive();
  _sc2UpdateSavedCount();
  _sc2UpdateSeenTickers(rows, DATA.run_timestamp);
  const wrap = document.getElementById('fsScannerWrap');
  if (wrap) {
    wrap.classList.remove('density-compact', 'density-normal', 'density-spacious');
    wrap.classList.add('density-' + (FS_STATE.density || 'normal'));
  }

  // Build rows
  const watched = _getWatchlist();
  const html = rows.map(r => {
    const v = r.stage || r.verdict || 'WATCH';
    const c = r.pct_chg || 0;
    const upDn = c > 0 ? 'up' : c < 0 ? 'dn' : 'dim';
    const rsi = r.rsi;
    const rsiCls = rsi > 70 ? 'rsi-overbought' : rsi < 30 ? 'rsi-oversold' : '';
    const rs = r.rs_rank;
    const rsCls = rs > 80 ? 'rs-leader' : rs < 40 ? 'rs-laggard' : '';
    const rvol = r.rvol;
    const rvolCls = rvol >= 2.5 ? 'rvol-extreme' : rvol > 1.5 ? 'rvol-high' : '';
    const rr = r.rr || 0;
    const rrCls = rr >= 3 ? 'rr-strong' : rr >= 2 ? 'warn' : 'rr-weak';
    const pctCls = c >= 5 ? `${upDn} pct-strong-up` : c <= -5 ? `${upDn} pct-strong-down` : (Math.abs(c) > 0.01 ? upDn : '');
    const atrCls = (r.atr_pct || 0) > 5 ? 'atr-volatile' : 'atr-stable';
    const spark = _fsSparkPath(r.ticker, r.score, c);
    const setupShort = (r.setup || r.setup_family || '').slice(0, 24);
    const setupFamily = _setupFamilyOf(r.setup || r.setup_family);
    const setupIcon = { impulse:'⚡', breakout:'▲', trend:'→', special:'★', other:'·' }[setupFamily];
    const score = r.score || 0;
    const tier = r.conviction_tier || (score >= 88 ? 'T1' : score >= 78 ? 'T2' : score >= 70 ? 'T3' : 'WATCH');
    const eq = (r.entry_quality || '').toUpperCase();
    const isWatched = watched.includes(r.ticker);
    const sectorMain = (r.sector || '').split(/[/]/)[0].trim() || '—';
    const earnWarn = (r.earn_days != null && r.earn_days <= 7) ? `<span class="sc2-earn" title="Earnings in ${r.earn_days}d">⚠ E+${r.earn_days}d</span>` : '';
    // ── Chip builder — compact: abbreviated labels + tooltips for full text ──
    const _chipsHtml = (() => {
      const primary = []; // line 1: verdict, conviction, setup family icon, catalyst tier
      const secondary = []; // line 2: entry quality, entry subtype, pullback, zone, timing, hold
      const stage = (r.stage || v || '').toUpperCase();
      // L1.1 NEW (animated, far left)
      if (window._SC2_NEW_TICKERS && window._SC2_NEW_TICKERS.has(r.ticker)) {
        primary.push(`<span class="rc rc-new" title="New since last scan">NEW</span>`);
      }
      // L1.2 Verdict
      if (stage === 'BUY')        primary.push(`<span class="rc rc-buy" title="BUY signal — pre-trade gates passed, conviction tier assigned">BUY</span>`);
      else if (stage === 'WATCH') primary.push(`<span class="rc rc-watch" title="WATCH list — setup building, no position taken yet">WATCH</span>`);
      else if (stage === 'SELL')  primary.push(`<span class="rc rc-sell" title="SHORT signal — bear setup confirmed">SHORT</span>`);
      // L1.3 Conviction tier (T1/T2/T3)
      if (tier && tier !== 'WATCH') primary.push(`<span class="rc rc-tier rc-tier-${tier.toLowerCase()}" title="Conviction tier — sizing">${tier}</span>`);
      // L1.4 Setup family — icon + short name
      const setupTxt = (r.setup || r.setup_family || '');
      const _sf = (() => {
        const s = setupTxt.toLowerCase();
        if (s.includes('impulse')) return ['⚡','Imp'];
        if (s.includes('breakout')) return ['▲','Bkt'];
        if (s.includes('trend'))    return ['→','Trd'];
        if (s.includes('special'))  return ['★','Spc'];
        return null;
      })();
      if (_sf) primary.push(`<span class="rc rc-fam" title="${setupTxt}">${_sf[0]} ${_sf[1]}</span>`);
      // L1.5 Catalyst tier (use "C" prefix to disambiguate from conviction "T")
      if (r.catalyst_tier) primary.push(`<span class="rc rc-cat${r.catalyst_tier}" title="Catalyst tier">C${r.catalyst_tier}</span>`);
      // L1.6 Hot
      if (score >= 90 && v === 'BUY') primary.push(`<span class="rc rc-hot" title="Score ≥ 90">🔥</span>`);

      // L2.1 Entry quality — abbreviated (FRESH→Fresh, PULLBACK→PB, EXTENDED→Ext)
      if (eq && eq !== 'VALID') {
        const ecls = eq === 'FRESH' || eq === 'PULLBACK' ? 'rc-eq-good' : 'rc-eq-bad';
        const eShort = eq === 'PULLBACK' ? 'PB' : eq === 'EXTENDED' ? 'Ext' : eq === 'MISSED' ? 'Miss' : eq.charAt(0) + eq.slice(1).toLowerCase();
        secondary.push(`<span class="rc ${ecls}" title="${eq}">${eShort}</span>`);
      }
      // L2.2 Entry subtype — short form
      if (r.entry_subtype) {
        const sub = String(r.entry_subtype);
        const subShort = sub.replace('Pocket Pivot Entry','Pocket').replace('Pivot Entry','Pivot').replace('Breakout Add','BO Add').slice(0,12);
        secondary.push(`<span class="rc rc-sub" title="${sub}">${subShort}</span>`);
      }
      // L2.3 Expected pullback (Shallow/Normal/Deep)
      if (r.expected_pullback) {
        const pb = String(r.expected_pullback);
        const pcls = pb === 'Shallow' ? 'rc-pb-good' : pb === 'Deep' ? 'rc-pb-bad' : 'rc-pb-mid';
        secondary.push(`<span class="rc ${pcls}" title="${pb} pullback">${pb}</span>`);
      }
      // L2.4 Zone — abbreviated (Strong→S, Moderate→M, Weak→W)
      const zq = r.zone_quality;
      const zqLabel = (zq && typeof zq === 'object') ? zq.label : (typeof zq === 'string' ? zq : '');
      if (zqLabel) {
        const zcls = zqLabel === 'Strong' ? 'rc-zone-good' : zqLabel === 'Weak' ? 'rc-zone-bad' : 'rc-zone-mid';
        secondary.push(`<span class="rc ${zcls}" title="Zone quality: ${zqLabel}">Z·${zqLabel.charAt(0)}</span>`);
      }
      // L2.5 Timing
      if (r.entry_timing) {
        const t = String(r.entry_timing);
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
    })();
    return `<div class="fs-st-row sc2-row" data-ticker="${r.ticker}" data-verdict="${v}" onclick="_handleRowClick(event, '${r.ticker}')">
      <div class="sc2-cell-score ${v}">
        ${_scoreRing(score, v)}
      </div>
      <div class="sc2-cell-tk">
        <div class="sc2-tk-row">
          ${_logoHtml(r.ticker, 18)}
          <span class="sc2-tk">${r.ticker}</span>
          ${_starsHtml(r.star_rating)}
        </div>
        <div class="sc2-tk-name">
          <span class="sc2-name">${(r.name || '').slice(0, 28) || '—'}</span>
          <span class="sc2-sector">${sectorMain}</span>
        </div>
      </div>
      <div class="sc2-cell-chips">${_chipsHtml || '<span class="sc2-chips-empty">—</span>'}</div>
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
      ${[..._SC2_EXTRA_COLS].map(k => {
        const f = _sc2FmtExtra(k, r);
        const subEl = f.sub ? `<span class="sc2-extra-sub">${f.sub}</span>` : '';
        return `<div class="sc2-cell r ${f.cls} sc2-extra-cell"><span class="sc2-num">${f.txt}</span>${subEl}</div>`;
      }).join('')}
      <div class="sc2-cell sc2-cell-actions" onclick="event.stopPropagation()">
        <button class="sc2-star ${isWatched ? 'watched' : ''}" title="${isWatched ? 'Remove from watchlist (F)' : 'Add to watchlist (F)'}" onclick="_toggleStar(event, '${r.ticker}', this)">${isWatched ? '★' : '☆'}</button>
      </div>
    </div>`;
  }).join('');

  const out = document.getElementById('fsScannerRows');
  if (out) {
    if (rows.length === 0) {
      const m = FS_STATE.mode || 'swing';
      const modeLbl = m === 'position' ? 'Position' : (m === 'invest' ? 'Invest' : 'Swing');
      out.innerHTML = `
        <div class="sc2-empty">
          <div class="sc2-empty-icon">⌕</div>
          <div class="sc2-empty-h">No ${modeLbl} signals match these filters</div>
          <div class="sc2-empty-sub">Try clearing filters, expanding the score range, or switching verdict.</div>
          <button class="btn primary" onclick="sc2Clear()" style="margin-top:14px">⟲ Clear all filters</button>
        </div>`;
    } else {
      out.innerHTML = html;
    }
  }
  if (typeof _wireCtxMenu === 'function') _wireCtxMenu();

  // Restore selection state on the new rows
  document.querySelectorAll('.sc2-row').forEach(row => {
    if (_SC2_SELECTED.has(row.dataset.ticker)) row.classList.add('selected');
  });
  // Inject extra column headers + grid columns
  _sc2InjectExtraHeaders();
  // Apply column visibility
  _sc2ApplyColVisibility();
  // Wire ticker preview hover
  _sc2WireTickerPreview();
  // Inject group divider rows when sorted by ticker (groups by sector)
  if (FS_STATE.sortKey === 'ticker') {
    _sc2InjectGroupDividers();
  }
}

export function dispose() { /* no-op */ }
