// subtabs/technicals/mtf.js — extracted from elite-detail.html (renderMTF 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  // Synthesize from what we have — daily indicators + lighter signals at 4H/1H/Weekly bias
  const d = {
    weekly:  { trend: T.above_200sma ? 'pass:↑ Bull' : 'fail:↓ Bear', mom: 'pass:Strong', struct: T.above_200sma ? 'pass:HH/HL' : 'fail:LH/LL', stack: T.above_200sma ? 'pass:8>21>50' : 'fail:Inverted', adx: 'dim:—', bias: T.above_200sma ? 'pass:BULL' : 'fail:BEAR' },
    daily:   { trend: T.above_50ema ? 'pass:↑ Bull' : 'warn:Sideways', mom: T.macd_bullish ? 'pass:Bullish' : 'warn:Mixed', struct: T.smc_score >= 6 ? 'pass:OB demand' : 'warn:No structure', stack: T.above_50ema ? 'pass:8>21>50' : 'warn:Flat', adx: 'pass:Trend', bias: T.verdict === 'BUY' ? 'pass:BULL' : 'warn:WAIT' },
    fourH:   { trend: T.rvol > 1.2 ? 'pass:Bull' : 'warn:Sideways', mom: T.rsi > 50 ? 'pass:Healthy' : 'warn:Cooling', struct: 'warn:Pullback', stack: 'warn:8≈21>50', adx: 'dim:—', bias: 'warn:NEUTRAL' },
    oneH:    { trend: 'warn:Sideways', mom: 'warn:RSI ' + fmt(T.rsi,0), struct: T.smc_score > 4 ? 'pass:FVG below' : 'dim:—', stack: 'warn:Flat', adx: 'dim:—', bias: 'warn:WAIT' },
    sectorD: { trend: T.rs_rank >= 80 ? 'pass:↑ Lead' : T.rs_rank >= 50 ? 'warn:Mid' : 'fail:Lag', mom: T.rs_rank >= 80 ? 'pass:RS ' + T.rs_rank : 'warn:RS ' + T.rs_rank, struct: 'pass:Outperf', stack: 'pass:Aligned', adx: 'dim:—', bias: T.rs_rank >= 80 ? 'pass:BULL' : 'warn:NEUTRAL' },
  };
  const cell = (s) => { const [c, txt] = s.split(':'); return `<span class="mtf-cell ${c}">${txt}</span>`; };
  $('mtfBody').innerHTML = `
  <div class="mtf-wrap">
    <table class="mtf-table">
      <thead><tr><th>Timeframe</th><th>Trend</th><th>Momentum</th><th>Structure</th><th>EMA Stack</th><th>ADX</th><th>Bias</th></tr></thead>
      <tbody>
        <tr><td>Weekly</td><td>${cell(d.weekly.trend)}</td><td>${cell(d.weekly.mom)}</td><td>${cell(d.weekly.struct)}</td><td>${cell(d.weekly.stack)}</td><td>${cell(d.weekly.adx)}</td><td>${cell(d.weekly.bias)}</td></tr>
        <tr><td>Daily</td><td>${cell(d.daily.trend)}</td><td>${cell(d.daily.mom)}</td><td>${cell(d.daily.struct)}</td><td>${cell(d.daily.stack)}</td><td>${cell(d.daily.adx)}</td><td>${cell(d.daily.bias)}</td></tr>
        <tr><td>4-Hour</td><td>${cell(d.fourH.trend)}</td><td>${cell(d.fourH.mom)}</td><td>${cell(d.fourH.struct)}</td><td>${cell(d.fourH.stack)}</td><td>${cell(d.fourH.adx)}</td><td>${cell(d.fourH.bias)}</td></tr>
        <tr><td>1-Hour</td><td>${cell(d.oneH.trend)}</td><td>${cell(d.oneH.mom)}</td><td>${cell(d.oneH.struct)}</td><td>${cell(d.oneH.stack)}</td><td>${cell(d.oneH.adx)}</td><td>${cell(d.oneH.bias)}</td></tr>
        <tr><td>Sector D1</td><td>${cell(d.sectorD.trend)}</td><td>${cell(d.sectorD.mom)}</td><td>${cell(d.sectorD.struct)}</td><td>${cell(d.sectorD.stack)}</td><td>${cell(d.sectorD.adx)}</td><td>${cell(d.sectorD.bias)}</td></tr>
      </tbody>
    </table>
  </div>`;
}

export function dispose() { /* no-op */ }
