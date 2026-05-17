// subtabs/smc/lux_screener.js — D-8 LuxAlgo-style multi-timeframe screener.
// 3 dense tables in one card: PRICE ACTION, KEY LEVELS, OSCILLATORS.
// Pure function — returns HTML string.

const _toneDot = (s) => {
  if (s == null) return '<td style="text-align:center"><span style="color:var(--ink-3)">—</span></td>';
  const cls = s === 'bull' || s === 'pass' ? 'pass' : s === 'bear' || s === 'fail' ? 'fail' : 'warn';
  const t   = { bull: '▲', bear: '▼', wait: '◆', pass: '✓', fail: '✗', warn: '~', dim: '—' }[s] || s;
  return `<td style="text-align:center"><span class="lux-dot ${cls}">${t}</span></td>`;
};

const _validPrice = (p) => typeof p === 'number' && isFinite(p) && p > 0;

function _priceAction(T, rvol) {
  const above50  = T.above_50ema;
  const above200 = T.above_200sma;
  return `
    <table class="lux-tbl">
      <thead><tr><th>TF</th><th>Trend</th><th>Structure</th><th>Stack</th><th class="r">RVOL</th><th>Bias</th></tr></thead>
      <tbody>
        <tr><td><span class="lux-tf">1H</span></td>${_toneDot('warn')}${_toneDot('warn')}${_toneDot('warn')}<td class="r mono">${rvol.toFixed(2)}×</td>${_toneDot('wait')}</tr>
        <tr><td><span class="lux-tf">4H</span></td>${_toneDot(rvol > 1.2 ? 'bull' : 'wait')}${_toneDot('warn')}${_toneDot('warn')}<td class="r mono">${rvol.toFixed(2)}×</td>${_toneDot(rvol > 1.2 ? 'bull' : 'wait')}</tr>
        <tr><td><span class="lux-tf">D1</span></td>${_toneDot(above50 ? 'bull' : 'bear')}${_toneDot(T.smc_score >= 6 ? 'bull' : 'wait')}${_toneDot(above50 ? 'bull' : 'wait')}<td class="r mono">${rvol.toFixed(2)}×</td>${_toneDot(T.verdict === 'BUY' ? 'bull' : T.verdict === 'WATCH' ? 'wait' : 'bear')}</tr>
        <tr><td><span class="lux-tf">W</span></td>${_toneDot(above200 ? 'bull' : 'bear')}${_toneDot(above200 ? 'bull' : 'bear')}${_toneDot(above200 ? 'bull' : 'bear')}<td class="r mono" style="color:var(--ink-3)">—</td>${_toneDot(above200 ? 'bull' : 'bear')}</tr>
      </tbody>
    </table>`;
}

function _keyLevels(T, px, obs, fvgs) {
  const levels = [];
  if (_validPrice(T.fractal_high)) levels.push({ tf: 'D1', kind: 'Resistance', price: T.fractal_high, dist: ((T.fractal_high/px - 1)*100), src: 'Fractal high' });
  if (_validPrice(T.fractal_low))  levels.push({ tf: 'D1', kind: 'Support',    price: T.fractal_low,  dist: ((T.fractal_low/px - 1)*100),  src: 'Fractal low'  });
  obs.slice(0, 4).forEach(o => {
    const obPrice = o.mid_price || (o.high && o.low ? (o.high + o.low) / 2 : (o.high || o.low));
    if (!_validPrice(obPrice)) return;
    levels.push({ tf: 'D1', kind: o.type === 'bullish' ? 'Demand OB' : 'Supply OB', price: obPrice, dist: (obPrice/px - 1)*100, src: o.status || 'fresh' });
  });
  fvgs.slice(0, 3).forEach(f => {
    const fvgPrice = _validPrice(f.mid) ? f.mid
                   : (_validPrice(f.high) && _validPrice(f.low)) ? (f.high + f.low) / 2
                   : (_validPrice(f.high) ? f.high : (_validPrice(f.low) ? f.low : null));
    if (!_validPrice(fvgPrice)) return;
    levels.push({ tf: 'D1', kind: f.type === 'bullish' ? 'Bull FVG' : 'Bear FVG', price: fvgPrice, dist: (fvgPrice/px - 1)*100, src: f.status || 'open' });
  });

  // K8: trade-plan levels read canonical_trade_plan first (Vinod feedback —
  // SMC plan and Overview plan must be identical, sourced from one place).
  const ctp     = T?.canonical_trade_plan;
  const tpEntry = ctp?.entry?.low ?? T.entry_low;
  const tpT1    = ctp?.target1   ?? T.target1;
  const tpStop  = ctp?.stop      ?? T.stop;
  if (_validPrice(tpEntry)) levels.push({ tf: 'PLN', kind: 'Entry', price: tpEntry, dist: ((tpEntry/px - 1)*100), src: 'Plan' });
  if (_validPrice(tpT1))    levels.push({ tf: 'PLN', kind: 'T1',    price: tpT1,    dist: ((tpT1/px - 1)*100),    src: 'Plan' });
  if (_validPrice(tpStop))  levels.push({ tf: 'PLN', kind: 'Stop',  price: tpStop,  dist: ((tpStop/px - 1)*100),  src: 'Plan' });

  levels.sort((a, b) => Math.abs(a.dist) - Math.abs(b.dist));

  return `<table class="lux-tbl">
    <thead><tr><th>TF</th><th>Type</th><th class="r">Level</th><th class="r">Dist %</th><th>Source</th></tr></thead>
    <tbody>
    ${levels.slice(0, 10).map(l => {
      const cls = Math.abs(l.dist) < 1 ? 'pass' : Math.abs(l.dist) < 3 ? 'warn' : 'fail';
      return `<tr>
        <td><span class="lux-tf">${l.tf}</span></td>
        <td>${l.kind}</td>
        <td class="r mono">$${l.price.toFixed(2)}</td>
        <td class="r mono ${cls}">${l.dist >= 0 ? '+' : ''}${l.dist.toFixed(2)}%</td>
        <td style="font-size:11px;color:var(--ink-2)">${l.src}</td>
      </tr>`;
    }).join('')}
    ${levels.length === 0 ? '<tr><td colspan="5" style="text-align:center;color:var(--ink-3);padding:14px">No structural levels detected</td></tr>' : ''}
    </tbody></table>`;
}

function _oscillators(T, rsi, macd, stoch, rsRank, rvol) {
  return `
    <table class="lux-tbl">
      <thead><tr><th>Indicator</th><th class="r">1H</th><th class="r">4H</th><th class="r">D1</th><th>Verdict</th></tr></thead>
      <tbody>
        <tr><td>RSI(14)</td><td class="r mono" style="color:var(--ink-3)">—</td><td class="r mono" style="color:var(--ink-3)">—</td><td class="r mono">${rsi.toFixed(0)}</td>${_toneDot(rsi > 70 ? 'fail' : rsi < 30 ? 'pass' : rsi >= 50 ? 'bull' : 'warn')}</tr>
        <tr><td>MACD</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td>${_toneDot(macd ? 'bull' : 'bear')}${_toneDot(macd ? 'bull' : 'bear')}</tr>
        <tr><td>Stoch RSI</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${stoch != null ? stoch.toFixed(0) : '—'}</td>${_toneDot(stoch == null ? 'wait' : stoch < 20 ? 'pass' : stoch > 80 ? 'fail' : stoch >= 50 ? 'bull' : 'warn')}</tr>
        <tr><td>RS rank</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${rsRank}</td>${_toneDot(rsRank >= 80 ? 'bull' : rsRank >= 50 ? 'wait' : 'bear')}</tr>
        <tr><td>RVOL</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${rvol.toFixed(2)}×</td>${_toneDot(rvol > 1.5 ? 'bull' : rvol > 1.0 ? 'wait' : 'warn')}</tr>
      </tbody>
    </table>`;
}

export function buildLuxScreener(T, px, obs, fvgs) {
  const rsi    = T.rsi || 50;
  const macd   = T.macd_bullish;
  const stoch  = T.stoch_rsi;
  const above50 = T.above_50ema, above200 = T.above_200sma;
  const rsRank = T.rs_rank || 50;
  const rvol   = T.rvol    || 1;

  return `
    <div class="lux-wrap">
      <div class="lux-h"><span style="font-size:14px">⌬</span> MULTI-TIMEFRAME SCREENER <span class="lux-meta">LuxAlgo-style · 3 dense tables · 1 glance</span></div>
      <div class="lux-grid">
        <div class="lux-card"><div class="lux-card-h">PRICE ACTION</div>${_priceAction(T, rvol)}</div>
        <div class="lux-card"><div class="lux-card-h">KEY LEVELS</div>${_keyLevels(T, px, obs, fvgs)}</div>
        <div class="lux-card"><div class="lux-card-h">OSCILLATORS</div>${_oscillators(T, rsi, macd, stoch, rsRank, rvol)}</div>
      </div>
    </div>
  `;
}
