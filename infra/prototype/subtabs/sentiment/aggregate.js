// subtabs/sentiment/aggregate.js — pure data transforms for the Sentiment sub-tab.
// Walks polynews + insider + EODHD timeseries + composite scoring, returns
// the data + sparkline SVG the view needs. No DOM, no fetch.

const fmt2     = v => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2);
const dollarsM = v => v == null || v === 0 ? '—' : '$' + (v / 1e6).toFixed(2) + 'M';

export { fmt2, dollarsM };

export function aggregate(T) {
  const ins        = T.insider || {};
  const insF       = T.insider_full || {};
  const news       = T.news || {};
  const polynews   = T.news_articles || [];
  const polyscore  = T.news_sentiment_score || {};
  const eodhdSent  = T.eodhd_sentiment || {};
  const sec        = T.sec_filings || {};
  const inst       = T.inst_trend || {};
  const sentComp   = T.sentiment || {};
  const sentDetails = sentComp.details || {};

  // News article sentiment breakdown
  const articleSent = polynews.map(n => {
    const insights = n.insights || [];
    const ti       = insights.find(i => (i.ticker || '').toUpperCase() === T.ticker);
    return ti?.sentiment || n.sentiment || 'neutral';
  });
  const newsBull     = articleSent.filter(s => s === 'positive').length;
  const newsBear     = articleSent.filter(s => s === 'negative').length;
  const newsNeut     = articleSent.filter(s => s === 'neutral').length;
  const newsTotal    = polynews.length;
  const newsScore    = (typeof polyscore === 'object' ? polyscore.score : polyscore) || 0;
  const newsMomentum = (typeof polyscore === 'object' ? polyscore.momentum : null) || 'neutral';
  const newsBreaking = (typeof polyscore === 'object' ? polyscore.breaking : false);

  // Insider summary
  const netIns       = (insF.net_signal != null) ? insF.net_signal : ((ins.buys || 0) - (ins.sells || 0));
  const insBuyValue  = insF.buy_value_30d  || ins.buy_value  || 0;
  const insSellValue = insF.sell_value_30d || ins.sell_value || 0;

  // EODHD sentiment timeseries
  const eodhdLatest  = eodhdSent.latest;
  const eodhdAvg7    = eodhdSent.avg_7d;
  const eodhdAvg30   = eodhdSent.avg_30d;
  const eodhdTrend   = eodhdSent.trend || 'flat';
  const eodhdHistory = eodhdSent.history || [];
  const eodhdCount   = eodhdSent.count || 0;

  // Composite tone
  const sentBullPts = (newsBull > newsBear ? 1 : 0)
    + (eodhdLatest != null && eodhdLatest > 0.1 ? 1 : 0)
    + (netIns > 0 ? 1 : 0);
  const sentBearPts = (newsBear > newsBull ? 1 : 0)
    + (eodhdLatest != null && eodhdLatest < -0.1 ? 1 : 0)
    + (netIns < 0 ? 1 : 0);
  let tone, hEm, arrow;
  if (sentBullPts > sentBearPts && sentBullPts >= 2) { tone = 'bull';    hEm = 'BULLISH'; arrow = '▲'; }
  else if (sentBearPts > sentBullPts && sentBearPts >= 2) { tone = 'bear'; hEm = 'BEARISH'; arrow = '▼'; }
  else                                                { tone = 'neutral'; hEm = 'NEUTRAL'; arrow = '◆'; }

  const compScore = sentComp.score || 0;
  const compMax   = sentComp.max   || 10;

  // Narrative bullets
  const narr = [];
  if (newsTotal)                                      narr.push(`${newsTotal} news articles in window — ${newsBull} bullish · ${newsBear} bearish · ${newsNeut} neutral`);
  if (newsMomentum && newsMomentum !== 'neutral')     narr.push(`news momentum <b>${newsMomentum}</b>`);
  if (eodhdLatest != null)                            narr.push(`EODHD aggregator ${eodhdLatest >= 0 ? '+' : ''}${eodhdLatest.toFixed(2)} (${eodhdTrend})`);
  if (netIns !== 0)                                   narr.push(`insider ${netIns > 0 ? '+' : ''}${netIns} net (${ins.buys || 0} buys / ${ins.sells || 0} sells)`);

  return {
    ins, insF, news, polynews, polyscore, eodhdSent, sec, inst, sentComp, sentDetails,
    newsBull, newsBear, newsNeut, newsTotal, newsScore, newsMomentum, newsBreaking,
    netIns, insBuyValue, insSellValue,
    eodhdLatest, eodhdAvg7, eodhdAvg30, eodhdTrend, eodhdHistory, eodhdCount,
    tone, hEm, arrow, compScore, compMax, narr,
    sparkSvg: buildSpark(eodhdHistory, eodhdTrend),
  };
}

function buildSpark(history, trend) {
  if (history.length < 2) return '';
  const W = 200, H = 40, pad = 2;
  const vals = history.slice(0, 30).reverse().map(r => +r.normalized || 0);
  const minV = Math.min(...vals, -0.1);
  const maxV = Math.max(...vals,  0.1);
  const range = (maxV - minV) || 0.2;
  const xS = i => pad + (i / Math.max(1, vals.length - 1)) * (W - pad*2);
  const yS = v => pad + ((maxV - v) / range) * (H - pad*2);
  const yZero = yS(0);
  const path  = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(i).toFixed(1)},${yS(v).toFixed(1)}`).join(' ');
  const fillPath = path + ` L${xS(vals.length-1).toFixed(1)},${yZero.toFixed(1)} L${xS(0).toFixed(1)},${yZero.toFixed(1)} Z`;
  const trendColor = trend === 'rising' ? '#4ade80' : trend === 'falling' ? '#f87171' : '#94a3b8';
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:40px;display:block">
    <line x1="${pad}" y1="${yZero}" x2="${W-pad}" y2="${yZero}" stroke="rgba(148,163,184,0.3)" stroke-dasharray="2 3"/>
    <path d="${fillPath}" fill="${trendColor}" fill-opacity="0.18"/>
    <path d="${path}" fill="none" stroke="${trendColor}" stroke-width="1.5"/>
  </svg>`;
}
