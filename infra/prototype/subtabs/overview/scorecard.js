// subtabs/overview/scorecard.js — extracted from elite-detail.html (renderScorecard 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const tier = (s, max=100) => {
    const pct = s/max*100;
    return pct >= 70 ? 'pass' : pct >= 50 ? 'warn' : 'fail';
  };
  const pillars = [
    { name:'Tech Structure', score:T.tech_score, max:T.tech_max || 35,
      summary:`${T.above_50ema ? 'EMA stacked.' : 'Below EMA50.'} ${T.macd_bullish ? 'MACD bullish.' : 'MACD weak.'} RSI ${fmt(T.rsi, 1)}. ${T.rvol > 1.2 ? `RVOL ${T.rvol.toFixed(1)}× confirms.` : 'RVOL light.'}`,
      tier: tier(T.tech_score || 0, T.tech_max || 35) },
    { name:'Fundamentals', score:T.fund_score, max:T.fund_max || 10,
      summary:`Quality gate score ${T.fund_score || 0}/${T.fund_max || 10}. ${T.earn_days != null && T.earn_days <= 14 ? `Earnings binary in ${T.earn_days}d.` : 'No imminent earnings.'}`,
      tier: tier(T.fund_score || 0, T.fund_max || 10) },
    { name:'Sentiment', score:T.sent_score, max:T.sent_max || 15,
      summary:`News ${T.news_score > 0 ? 'positive' : T.news_score < 0 ? 'negative' : 'neutral'}. Insider ${T.insider_buys || 0} buys / ${T.insider_sells || 0} sells.`,
      tier: tier(T.sent_score || 0, T.sent_max || 15) },
    { name:'Smart Money', score:T.smc_score, max:10,
      summary:`SMC zones ${T.smc_score || 0}/10. ${T.above_200sma ? 'Above 200 SMA — Stage 2.' : 'Below 200 SMA.'}`,
      tier: tier(T.smc_score || 0, 10) },
    { name:'Quality Gate', score: T.score >= 70 ? 4 : T.score >= 50 ? 3 : 2, max:5,
      summary:`${T.score >= 70 ? '4/5 hard rules clear' : T.score >= 50 ? '3/5 rules — partial pass' : '2/5 rules — gated'}. Liquidity OK, RR ${(T.rr_ratio||0).toFixed(1)}.`,
      tier: T.score >= 70 ? 'pass' : T.score >= 50 ? 'warn' : 'fail' },
  ];
  $('scorecardBody').innerHTML = `
  <div class="pillars">
    ${pillars.map(p => `
      <div class="pillar ${p.tier}">
        <div class="pillar-head"><span class="pillar-name">${p.name}</span></div>
        <div class="pillar-score">${p.score || 0}<s>/${p.max}</s></div>
        <div class="pillar-bar"><div class="fill" style="width:${Math.min(100, (p.score||0)/p.max*100)}%"></div></div>
        <div class="pillar-summary">${p.summary}</div>
        <div class="pillar-link"><span>view evidence</span></div>
      </div>`).join('')}
  </div>`;
}

export function dispose() { /* no-op */ }
