// subtabs/plan/backtest.js — extracted from elite-detail.html (renderBacktest 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const stats = ({
    'Trend Continuation': { wr: 64.8, exp: 0.78, pf: 1.84, sharpe: 1.62, avgWin: 2.14, avgLoss: -1.0, hold: 11.2, n: 142 },
    '52wk Breakout':      { wr: 60.0, exp: 0.84, pf: 2.01, sharpe: 1.71, avgWin: 2.42, avgLoss: -1.0, hold: 9.4,  n: 86 },
    'EMA21 Pullback':     { wr: 100.0, exp: 1.21, pf: 3.40, sharpe: 1.95, avgWin: 1.92, avgLoss: -0.0, hold: 6.8, n: 12 },
    'VCP Breakout':       { wr: 58.0, exp: 0.74, pf: 1.68, sharpe: 1.42, avgWin: 2.08, avgLoss: -1.0, hold: 13.6, n: 64 },
    'Squeeze Expansion':  { wr: 100.0, exp: 1.45, pf: 4.20, sharpe: 2.10, avgWin: 2.20, avgLoss: 0.0, hold: 8.0, n: 14 },
  })[T.setup_family] || { wr: 55.0, exp: 0.62, pf: 1.45, sharpe: 1.28, avgWin: 1.86, avgLoss: -1.0, hold: 12.0, n: 50 };

  const months = [
    ['MAY', +8.4],['JUN', +3.2],['JUL', -1.8],['AUG', +11.2],['SEP', +2.1],['OCT', -4.4],
    ['NOV', +14.8],['DEC', +3.8],['JAN', -2.2],['FEB', +6.4],['MAR', +9.1],['APR', +2.8],
  ];

  // Verdict tone
  let bktTone, bktEm, bktI;
  if (stats.wr >= 60 && stats.exp >= 0.8 && stats.pf >= 1.8) { bktTone = 'strong'; bktEm = 'EDGE CONFIRMED'; bktI = '▲'; }
  else if (stats.wr >= 50 && stats.exp >= 0.4 && stats.pf >= 1.3) { bktTone = 'decent'; bktEm = 'POSITIVE EXPECTANCY'; bktI = '◆'; }
  else { bktTone = 'weak'; bktEm = 'MARGINAL EDGE'; bktI = '○'; }

  const winMonths = months.filter(([_, v]) => v > 0).length;
  const yearReturn = months.reduce((s, [_, v]) => s + v, 0);
  const maxDD = Math.min(...months.map(([_, v]) => v));
  const bestMonth = Math.max(...months.map(([_, v]) => v));

  $('backtestBody').innerHTML = `
    <!-- VERDICT BANNER -->
    <div class="bkt-verdict ${bktTone}">
      <div class="bkt-v-i">${bktI}</div>
      <div class="bkt-v-mid">
        <div class="tag">SETUP FAMILY · ${T.setup_family || 'Generic'}</div>
        <div class="h">Historical edge is <span class="em">${bktEm}</span></div>
        <div class="narr">${stats.n} historical trades · ${stats.wr.toFixed(0)}% win rate · ${stats.exp >= 0 ? '+' : ''}${stats.exp.toFixed(2)}R expectancy · ${stats.pf.toFixed(2)} profit factor. ${bktTone === 'strong' ? 'Statistically robust — full conviction sizing justified.' : bktTone === 'decent' ? 'Acceptable edge — moderate sizing recommended.' : 'Thin edge — reduce size or wait for better setups.'} <span style="opacity:.6;font-style:italic">Synthetic data — wire to tracker.compute_stats_by_setup() for live.</span></div>
      </div>
      <div class="bkt-v-r">
        <div class="v">${stats.wr.toFixed(0)}%</div>
        <div class="lbl">Win Rate · n=${stats.n}</div>
      </div>
    </div>

    <!-- 8 STAT TILES (2 rows) -->
    <div class="bkt-stats">
      <div class="bkt-stat-tile"><div class="lbl">Win Rate</div><div class="v ${stats.wr >= 60 ? 'pass' : stats.wr >= 50 ? 'warn' : 'fail'}">${stats.wr.toFixed(1)}%</div><div class="sub">${stats.n} trades</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Expectancy</div><div class="v ${stats.exp >= 0.8 ? 'pass' : stats.exp >= 0.4 ? 'warn' : 'fail'}">+${stats.exp.toFixed(2)}R</div><div class="sub">avg per trade</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Profit Factor</div><div class="v ${stats.pf >= 2.0 ? 'pass' : stats.pf >= 1.5 ? 'warn' : 'fail'}">${stats.pf.toFixed(2)}</div><div class="sub">gross W ÷ gross L</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Sharpe</div><div class="v ${stats.sharpe >= 1.5 ? 'pass' : stats.sharpe >= 1.0 ? 'warn' : 'fail'}">${stats.sharpe.toFixed(2)}</div><div class="sub">risk-adj returns</div></div>
    </div>
    <div class="bkt-stats">
      <div class="bkt-stat-tile"><div class="lbl">Avg Win</div><div class="v pass">+${stats.avgWin.toFixed(2)}R</div><div class="sub">winning trades</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Avg Loss</div><div class="v fail">${stats.avgLoss.toFixed(2)}R</div><div class="sub">losing trades</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Avg Hold (Win)</div><div class="v">${stats.hold.toFixed(1)}d</div><div class="sub">days to target</div></div>
      <div class="bkt-stat-tile"><div class="lbl">Sample Size</div><div class="v ${stats.n >= 50 ? 'pass' : stats.n >= 20 ? 'warn' : 'fail'}">${stats.n}</div><div class="sub">${stats.n >= 50 ? 'reliable' : stats.n >= 20 ? 'moderate' : 'thin'}</div></div>
    </div>

    <!-- MONTHLY RETURNS HEATMAP -->
    <div class="bkt-mo-card">
      <div class="bkt-mo-h"><span class="ico">📅</span>MONTHLY RETURNS · LAST 12 MONTHS<span class="meta">${winMonths}/12 winning · ${yearReturn >= 0 ? '+' : ''}${yearReturn.toFixed(1)}% total · best ${bestMonth >= 0 ? '+' : ''}${bestMonth.toFixed(1)}% / worst ${maxDD.toFixed(1)}%</span></div>
      <div class="bkt-mo-grid">
        ${months.map(([m, v]) => {
          const isPos = v >= 0;
          const c = isPos ? 'var(--pass)' : 'var(--fail)';
          const intensity = Math.min(28, Math.abs(v) * 1.6);
          return `<div class="bkt-mo-cell" style="background:color-mix(in oklch, ${c} ${intensity}%, var(--bg-1));border:1px solid color-mix(in oklch, ${c} ${intensity + 8}%, var(--rule))"><div class="name">${m}</div><div class="pct" style="color:${c}">${isPos ? '+' : ''}${v.toFixed(1)}%</div></div>`;
        }).join('')}
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }
