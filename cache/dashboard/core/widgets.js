// core/widgets.js — cross-cutting render widgets used by multiple tabs.
// _renderPerfStrip and _renderSqueezeBadge appear on Elite Picks tiles + Scanner row tiles.
// Loaded eagerly by core/shell.js on boot; auto-binds to window so inline
// callers (`_renderPerfStrip(td)`) resolve at call time.
// (CapStudio sub-helpers fold 2026-05-09)

function _renderPerfStrip(td) {
  if (!td) return '';
  const fv = td.finviz_elite || {};
  const periods = [
    ['W', fv.perf_week_pct],
    ['M', fv.perf_month_pct],
    ['Q', fv.perf_quarter_pct],
    ['H', fv.perf_half_pct],
    ['Y', fv.perf_year_pct],
  ];
  if (!periods.some(p => typeof p[1] === 'number')) return '';
  // Bar height: cap |pct| at 50%, map to 4-22px
  const barHeight = (pct) => {
    if (typeof pct !== 'number') return 0;
    const m = Math.min(Math.abs(pct), 50);
    return Math.round(4 + (m / 50) * 18);
  };
  const barColor = (pct) => {
    if (typeof pct !== 'number') return 'var(--ink-3)';
    if (pct > 5) return 'var(--pass)';
    if (pct > 0) return 'color-mix(in oklch, var(--pass) 70%, var(--ink-3))';
    if (pct > -5) return 'color-mix(in oklch, var(--warn) 70%, var(--ink-3))';
    return 'var(--fail)';
  };
  const cells = periods.map(([label, pct]) => {
    const h = barHeight(pct);
    const c = barColor(pct);
    const tip = (typeof pct === 'number') ? `${label}: ${pct.toFixed(1)}%` : `${label}: —`;
    return `<div title="${tip}" style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;">
      <div style="width:6px;height:22px;display:flex;align-items:flex-end;justify-content:center;">
        ${typeof pct === 'number' ? `<div style="width:6px;height:${h}px;background:${c};border-radius:1px;"></div>` : '<div style="width:6px;height:1px;background:var(--ink-3);"></div>'}
      </div>
      <span style="font-size:8px;color:var(--ink-3);font-family:var(--mono);">${label}</span>
    </div>`;
  }).join('');
  return `<div style="margin-top:8px;padding-top:6px;border-top:1px dashed color-mix(in oklch, var(--rule-2) 50%, transparent);">
    <div style="display:flex;gap:4px;align-items:flex-end;">${cells}</div>
  </div>`;
}

function _renderSqueezeBadge(td) {
  if (!td) return '';
  const sf = td.squeeze_flag || {};
  if (!sf.level || sf.level === 'low') return '';
  const color = sf.level === 'high' ? 'var(--warn)' : 'color-mix(in oklch, var(--warn) 60%, var(--ink-3))';
  const txt = sf.level === 'high' ? `🔥 SQUEEZE ${sf.score}` : `SQUEEZE ${sf.score}`;
  return `<div style="margin-top:4px;display:inline-block;background:${color};color:var(--bg-0);font-size:9px;font-weight:800;padding:2px 6px;border-radius:3px;letter-spacing:0.06em;">${txt}</div>`;
}


// Auto-bind exports to window for inline-HTML onclick / cross-script callers
if (typeof window !== 'undefined') {
  window._renderPerfStrip = _renderPerfStrip;
  window._renderSqueezeBadge = _renderSqueezeBadge;
}
