// subtabs/models/elliott.js — extracted from elite-detail.html (renderElliott 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

// K5/K6 (2026-05-09): render the canonical Wave-3-Impulse Fib-extension card
// at the top of Elliott when canonical_trade_plan.setup.elliott_wave is present.
// This is the new analysis.classify_elliott_wave output (commit 302e9ea00):
// {wave, type, swing_low, swing_high, swing_range, t1_extension, t2_extension, confidence}.
// Distinct from the legacy `T.elliott_wave` schema (wave_number/fib_levels/etc),
// which continues to render as the main body — this card is additive.
function _ctpElliottBannerHTML(T) {
  const ew = T?.canonical_trade_plan?.setup?.elliott_wave;
  if (!ew || !ew.wave) return '';
  const conf = (ew.confidence || 'low').toLowerCase();
  const confCls = conf === 'high' ? 'green' : conf === 'low' ? 'red' : 'warn';
  const typeStr = ew.type || 'incomplete';
  return `
    <div style="background:linear-gradient(90deg,#142a3a,#0e1f2c);border:1px solid #1a4a6a;border-radius:6px;padding:14px 18px;margin-bottom:12px;font-family:var(--mono);">
      <div style="font-size:10px;letter-spacing:0.18em;color:#5eead4;text-transform:uppercase;margin-bottom:8px;">Engine Classification (canonical_trade_plan)</div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--ink-0);">
        <div><span style="color:var(--ink-2)">Wave:</span> <span style="font-weight:600">${ew.wave}</span> <span style="color:var(--ink-2)">(${typeStr})</span></div>
        <div><span style="color:var(--ink-2)">Confidence:</span> <span class="${confCls}" style="font-weight:600">${conf}</span></div>
        ${ew.swing_low != null && ew.swing_high != null ? `<div><span style="color:var(--ink-2)">Swing:</span> $${ew.swing_low} → $${ew.swing_high} <span style="color:var(--ink-2)">(range $${ew.swing_range})</span></div>` : ''}
      </div>
      ${ew.t1_extension != null && ew.t2_extension != null ? `
      <div style="display:flex;gap:18px;font-size:13px;margin-top:8px;color:var(--ink-0);">
        <div><span style="color:var(--ink-2)">T1 (1.272 ext):</span> <span class="green" style="font-weight:600">$${ew.t1_extension}</span></div>
        <div><span style="color:var(--ink-2)">T2 (1.618 ext):</span> <span class="green" style="font-weight:600">$${ew.t2_extension}</span></div>
      </div>` : ''}
    </div>`;
}

// 2026-05-10 — EW Rule Gate v1.0 (spec) banner.
// Distinct from canonical_trade_plan.setup.elliott_wave (which is the legacy
// heuristic classifier). This banner shows the new 8-state classifier output:
// elliott_wave_v1 = { ew_state, ew_bullish, ew_bearish, ew_score, t1, t2,
//                     invalidated, reason, fib_retracement_pct, primary,
//                     intermediate, minor, mtf_alignment }
function _ewV1BannerHTML(T) {
  const v1 = T?.trade_plan?.elliott_wave_v1
           || T?.canonical_trade_plan?.setup?.elliott_wave_v1
           || T?.elliott_wave_v1;
  if (!v1 || v1.ew_state === 'AMBIGUOUS' && v1.ew_score === 0 && !v1.invalidated) {
    return '';
  }

  const stateColors = {
    WAVE3_IMPULSE:     { bg: '#0e2a16', border: '#1a5a32', accent: '#4ade80', label: 'BULLISH · STRONGEST' },
    WAVE5_IMPULSE:     { bg: '#0e2a16', border: '#1a5a32', accent: '#84cc16', label: 'BULLISH · WEAKENING' },
    WAVE2_CORRECTION:  { bg: '#2a230e', border: '#5a4a1a', accent: '#f5b441', label: 'NEUTRAL · POTENTIAL W3 ENTRY' },
    WAVE4_CORRECTION:  { bg: '#2a230e', border: '#5a4a1a', accent: '#f5b441', label: 'NEUTRAL · POTENTIAL W5 ENTRY' },
    WAVE4_TRIANGLE:    { bg: '#2a230e', border: '#5a4a1a', accent: '#f59e0b', label: 'NEUTRAL · W5 THRUST IMMINENT' },
    WAVE_A_CORRECTION: { bg: '#2a0e0e', border: '#5a1a1a', accent: '#f87171', label: 'BEARISH · CORRECTIVE LEG A' },
    WAVE_C_CORRECTION: { bg: '#2a0e0e', border: '#5a1a1a', accent: '#f87171', label: 'BEARISH · FINAL DOWN LEG' },
    AMBIGUOUS:         { bg: '#1a1f24', border: '#3a4350', accent: '#8a929c', label: 'UNCLEAR · WAIT' },
  };
  const c = stateColors[v1.ew_state] || stateColors.AMBIGUOUS;
  const fibPct = v1.fib_retracement_pct != null ? (v1.fib_retracement_pct * 100).toFixed(1) + '%' : '—';
  const mtf = v1.mtf_alignment || {};
  const mtfWarning = mtf.warning ? `<div style="background:rgba(248,113,113,0.12);border:1px solid rgba(248,113,113,0.3);border-radius:4px;padding:6px 10px;margin-top:8px;font-size:11px;color:#fca5a5">⚠ ${mtf.warning}</div>` : '';
  const invalidated = v1.invalidated ? `<div style="background:rgba(248,113,113,0.18);border:1px solid #ef4444;border-radius:4px;padding:6px 10px;margin-top:8px;font-size:11px;color:#fca5a5">✗ INVALIDATED · ${v1.reason}</div>` : '';

  return `
    <div style="background:linear-gradient(90deg, ${c.bg}, ${c.bg}cc);border:1px solid ${c.border};border-radius:6px;padding:14px 18px;margin-bottom:12px;font-family:var(--mono);">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:10px;letter-spacing:0.18em;color:${c.accent};text-transform:uppercase;font-weight:700">EW Rule Gate v1.0 · Intermediate (Daily)</div>
        <div style="font-size:9px;color:var(--ink-3);letter-spacing:0.04em">spec ${v1.spec_version || 'v1.0'}</div>
      </div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--ink-0);align-items:center">
        <div style="font-size:15px;font-weight:700;color:${c.accent};letter-spacing:0.02em">${(v1.ew_state || '').replace(/_/g, ' ')}</div>
        <span style="font-size:10px;color:var(--ink-2);font-weight:500">${c.label}</span>
        <span style="margin-left:auto;background:${c.accent};color:#000;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700">SCORE ${v1.ew_score}/4</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(140px, 1fr));gap:10px;margin-top:10px;font-size:12px;color:var(--ink-1)">
        ${v1.t1 ? `<div><span style="color:var(--ink-2);font-size:10px">T1 (1.618×W1)</span><br><b style="color:${c.accent};font-size:13px">$${v1.t1}</b></div>` : ''}
        ${v1.t2 ? `<div><span style="color:var(--ink-2);font-size:10px">T2 (2.618×W1)</span><br><b style="color:${c.accent};font-size:13px">$${v1.t2}</b></div>` : ''}
        <div><span style="color:var(--ink-2);font-size:10px">W2 retrace</span><br><b style="color:var(--ink-1);font-size:13px">${fibPct}</b></div>
        ${v1.w1_start != null ? `<div><span style="color:var(--ink-2);font-size:10px">W1 swing</span><br><b style="color:var(--ink-1);font-size:11px">$${v1.w1_start} → $${v1.w1_end}</b></div>` : ''}
        <div><span style="color:var(--ink-2);font-size:10px">Bullish / Bearish</span><br><b style="font-size:13px">${v1.ew_bullish ? '<span class="green">✓ BULL</span>' : v1.ew_bearish ? '<span class="red">✗ BEAR</span>' : '<span style="color:var(--warn)">○ NEUTRAL</span>'}</b></div>
        ${mtf.primary_mult != null ? `<div><span style="color:var(--ink-2);font-size:10px">Primary mult</span><br><b style="color:var(--ink-1);font-size:13px">${mtf.primary_mult.toFixed(1)}×</b></div>` : ''}
      </div>
      ${v1.reason && !v1.invalidated ? `<div style="font-size:11px;color:var(--ink-2);margin-top:8px;font-style:italic">${v1.reason}</div>` : ''}
      ${mtfWarning}
      ${invalidated}
    </div>`;
}

export function render() {
  const T = _T();
  const ew = T.elliott_wave || {};
  // Treat "?" / "" / null all as "no clear wave" — backend emits "?" when consolidating
  const wn = ew.wave_number;
  const hasWave = wn != null && wn !== '' && wn !== '?' && wn !== 'unknown';
  if (!hasWave) {
    const swingBase = ew.swing_base, swingTop = ew.swing_top;
    const fibs = ew.fib_levels || {};
    const fibOrder = ['23.6%','38.2%','50.0%','61.8%','78.6%','100%','127.2%','161.8%'];
    const tiles = fibOrder.filter(k => fibs[k] != null).map(k => ({k, v: fibs[k]}));
    $('elliottBody').innerHTML = _ewV1BannerHTML(T) + _ctpElliottBannerHTML(T) + `
      <div class="ew-banner" style="background:linear-gradient(90deg,#3a3414,#2a2510);border:1px solid #5a4d1a">
        <span class="lbl" style="color:#e8c860">Current Structure</span>
        <span class="num-pill" style="background:#5a4d1a;color:#fff8d0">—</span>
      </div>
      <div class="ew-card">
        <div class="ew-row1">
          <div class="ew-num-tile" style="background:#5a4d1a;color:#fff8d0">—</div>
          <div class="ew-meta-stack">
            <div class="ew-title">No Clear Elliott Structure</div>
            <div class="ew-meta-line" style="color:var(--ink-1)">
              <span class="v">↔ Consolidating / Sideways</span>
              ${swingBase != null && swingTop != null ? `<span class="sep">|</span><span>Range: <span class="v">$${px(swingBase)} → $${px(swingTop)}</span></span>` : ''}
            </div>
          </div>
        </div>
        <div class="ew-desc" style="color:var(--ink-1)">Price action shows no impulse or corrective wave pattern. Wait for a breakout above the swing high or breakdown below the swing low to identify the next wave structure.</div>
        ${tiles.length ? `
        <div class="ew-fib-head">Fibonacci Levels (range-based)</div>
        <div class="ew-fib-grid">
          ${tiles.map(t => `<div class="ew-fib-tile"><div class="pct">${t.k}</div><div class="px">$${px(t.v)}</div></div>`).join('')}
        </div>` : ''}
      </div>`;
    return;
  }
  const trend     = (ew.trend || 'bullish').toLowerCase();
  const trendCls  = trend === 'bullish' ? 'green' : trend === 'bearish' ? 'red' : '';
  const trendArrow = trend === 'bullish' ? '⬆' : trend === 'bearish' ? '⬇' : '↔';
  const conf      = (ew.confidence || 'medium').toLowerCase();
  const confCls   = conf === 'high' ? 'green' : conf === 'low' ? 'red' : 'warn';
  const swingBase = ew.swing_base, swingTop = ew.swing_top;
  const fibs      = ew.fib_levels || {};
  const nearest   = ew.nearest_fib || [];
  const fibOrder  = ['23.6%','38.2%','50.0%','61.8%','78.6%','100%','127.2%','161.8%'];
  const tiles     = fibOrder.filter(k => fibs[k] != null).map(k => ({k, v: fibs[k], near: nearest[0] === k}));

  $('elliottBody').innerHTML = _ewV1BannerHTML(T) + _ctpElliottBannerHTML(T) + `
    <div class="ew-banner">
      <span class="lbl">Current Wave</span>
      <span class="num-pill">${ew.wave_number}</span>
    </div>
    <div class="ew-card">
      <div class="ew-row1">
        <div class="ew-num-tile">${ew.wave_number}</div>
        <div class="ew-meta-stack">
          <div class="ew-title">${ew.wave_label || `Wave ${ew.wave_number}`}</div>
          <div class="ew-meta-line">
            <span class="v ${trendCls}">${trendArrow} ${trend.charAt(0).toUpperCase() + trend.slice(1)}</span>
            <span class="sep">|</span>
            <span>Conf: <span class="v ${confCls}">${conf.charAt(0).toUpperCase() + conf.slice(1)}</span></span>
            ${swingBase != null && swingTop != null ? `<span class="sep">|</span><span><span class="v">$${px(swingBase)} → $${px(swingTop)}</span></span>` : ''}
          </div>
        </div>
      </div>
      ${ew.description ? `<div class="ew-desc">${ew.description}</div>` : ''}
      <div class="ew-sub-card">
        <div class="ew-charac-head">
          <span class="pill-num">${ew.wave_number}</span>
          <span class="h">Wave ${ew.wave_number} Characteristics</span>
        </div>
        <div class="ew-charac-body">${waveCharacteristics(ew.wave_number)}</div>
      </div>
      ${swingBase != null && swingTop != null ? `
      <div class="ew-sub-card range">
        <div class="icon">↔</div>
        <div class="body">
          <div class="h">Swing Range</div>
          <div class="t">The wave is measured from the swing base to the swing top. Current price position within this range determines the remaining potential.</div>
        </div>
        <div class="price">$${px(swingBase)} → $${px(swingTop)}</div>
      </div>` : ''}
      ${tiles.length ? `
      <div class="ew-fib-head">Fibonacci Levels</div>
      <div class="ew-fib-grid">
        ${tiles.map(t => `<div class="ew-fib-tile ${t.near ? 'nearest' : ''}"><div class="pct">${t.k}</div><div class="px">$${px(t.v)}</div></div>`).join('')}
      </div>
      ${nearest.length ? `
        <div class="ew-nearest">★ Nearest Fib (<span class="v">$${px(T.price)}</span>) → <span class="v">${nearest[0]} at $${px(nearest[1])}</span></div>` : ''}
      ` : ''}
    </div>`;
}

export function dispose() { /* no-op */ }
