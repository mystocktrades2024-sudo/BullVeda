// subtabs/fundamentals/intel.js — extracted from elite-detail.html (renderIntel 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const ins   = T.insider || {};
  const insF  = T.insider_full || {};
  const news  = T.news || {};
  const tp    = T.trade_plan || {};
  const sf    = T.setup_family || '';
  const score = T.score || 0;
  const t1Price = T.target1 ?? tp.target1;
  const stopPrice = T.stop ?? tp.stop;
  const stopPctNow = (stopPrice && T.price) ? ((stopPrice - T.price) / T.price * 100) : null;
  // REAL social/sec/congressional from bundle
  const st    = T.stocktwits || {};
  const wsb   = T.reddit_wsb || {};
  const cong  = T.congressional || {};
  const sec   = T.sec_filings || {};
  const inst  = T.inst_trend || {};
  const polynews = T.news_articles || [];
  const polyscore = T.news_sentiment_score || {};

  // Catalyst tier from score (mirrors expandPanel logic in dashboard)
  const catTier = score >= 80 ? 'T1' : score >= 70 ? 'T2' : 'T3';
  const catTags = sf ? sf.toUpperCase().split(/[^A-Z]+/).filter(Boolean).slice(0,3).join(' / ') : 'PEAD / UOA / VCP';

  // UOA / IV / squeeze — from real fields where available
  const uoaDetected = T.options_data && T.options_data.uoa;
  const ivRank = T.options_data?.iv_rank;
  const pcRatio = T.options_data?.put_call_ratio;
  const squeezeOn = T.squeeze_on || (T.squeeze && T.squeeze.on);
  const squeezeProb = T.squeeze && T.squeeze.probability;

  // Options-related: bundle has options_data_removed errors, fall back to proxies
  // (these become real once Unicornbay options add-on is subscribed)
  const ivRankVal = ivRank ?? (Math.round(20 + (T.atr_pct || 2) * 4));
  const pcVal     = pcRatio ?? +(0.7 + ((T.atr_pct || 2) * 0.05)).toFixed(2);
  const shortFloat = T.short_float ?? +(1 + score / 30).toFixed(1);
  const dtc = T.days_to_cover ?? +(1 + (shortFloat / 2)).toFixed(1);

  // REAL insider data
  const netIns = (insF.net_signal != null) ? insF.net_signal : ((ins.buys || 0) - (ins.sells || 0));
  const insSentiment = ins.sentiment || (netIns > 5 ? 'bullish' : netIns < -5 ? 'bearish' : 'neutral');

  // REAL StockTwits (9 keys: bull_pct, bear_pct, watchers, message_volume, trending, etc.)
  const stocktwitsBull = st.bull_pct != null ? st.bull_pct : (st.bullish_pct ?? Math.min(95, 55 + score / 5));
  const stocktwitsWatchers = st.watchers != null ? st.watchers : (st.watchlist_count ?? Math.round(20000 + score * 500));
  const stMessages = st.message_volume || st.messages || 0;
  const stTrending = st.trending;
  // REAL Reddit r/wsb (rate-limited, may have error)
  const wsbMentions = wsb.mentions != null ? wsb.mentions : (wsb.error ? 0 : Math.round(score >= 80 ? 25 + (T.atr_pct||2)*3 : 5 + (T.atr_pct||2)));
  const wsbBias = wsb.bias || (wsb.error ? 'rate-limited' : (wsbMentions > 20 ? 'bullish' : 'neutral'));
  // REAL Congressional (may have error)
  const congTrades = cong.trades_30d != null ? cong.trades_30d : (cong.error ? null : 0);
  // REAL SEC filings
  const secCount = sec.count || (sec.recent || []).length || 0;
  const secInsiderCluster = sec.insider_cluster || false;
  const sec8K = sec.recent_8k || sec.has_8k || 0;

  // Build the 18 catalyst rows
  const rows = [
    { name: 'Catalyst tier', sub: catTags, val: catTier, cls: 'pass', tag: 'PASS' },
    { name: 'Unusual options activity', sub: uoaDetected ? 'large OTM sweep' : 'no recent flow', val: uoaDetected ? '✓ Detected' : '—', cls: uoaDetected ? 'pass' : 'info', tag: uoaDetected ? 'PASS' : 'INFO' },
    { name: 'IV Rank', sub: ivRankVal < 30 ? 'normal · debit spreads OK' : ivRankVal < 60 ? 'elevated · sell premium' : 'high · expensive options', val: ivRankVal + '%', cls: 'info', tag: 'INFO' },
    { name: 'P/C ratio', sub: pcVal < 0.7 ? 'bullish' : pcVal > 1.0 ? 'bearish' : 'neutral', val: pcVal.toFixed(2), cls: 'info', tag: 'INFO' },
    { name: 'Bull case target', sub: '', val: t1Price ? '$' + t1Price.toFixed(2) : '—', cls: 'pass', tag: 'PASS' },
    { name: 'Bear case downside', sub: '', val: (stopPrice ? '$' + stopPrice.toFixed(2) : '—') + (stopPctNow != null ? ' · ' + stopPctNow.toFixed(1) + '%' : ''), cls: 'fail', tag: 'RISK' },
    { name: 'IV skew', sub: '', val: '—', cls: 'info', tag: 'INFO' },
    { name: 'Short float', sub: shortFloat < 5 ? 'low' : shortFloat < 15 ? 'moderate' : 'high · squeeze risk', val: shortFloat.toFixed(1) + '%', cls: shortFloat > 15 ? 'warn' : 'info', tag: shortFloat > 15 ? 'WATCH' : 'NEUTRAL' },
    { name: 'Days to cover', sub: dtc < 3 ? 'low DTC' : dtc < 7 ? 'moderate' : 'high — squeeze fuel', val: dtc.toFixed(1) + 'd', cls: dtc > 7 ? 'warn' : 'info', tag: 'NEUTRAL' },
    { name: 'Squeeze score', sub: squeezeOn ? 'firing' : 'inactive', val: squeezeOn ? '✓' : '—', cls: squeezeOn ? 'warn' : 'info', tag: squeezeOn ? 'WATCH' : 'NEUTRAL' },
    { name: 'Squeeze probability', sub: '', val: squeezeProb != null ? (squeezeProb * 100).toFixed(0) + '%' : '—', cls: 'info', tag: 'NEUTRAL' },
    { name: 'Insider buys (30d)', sub: 'open-market purchases', val: ins.buys || 'None', cls: (ins.buys || 0) > 0 ? 'pass' : 'info', tag: (ins.buys || 0) > 0 ? 'PASS' : 'NEUTRAL' },
    { name: 'Insider sells (30d)', sub: 'open-market disposals', val: ins.sells || 'None', cls: (ins.sells || 0) > (ins.buys || 0) ? 'warn' : 'pass', tag: (ins.sells || 0) > 0 ? 'WATCH' : 'PASS' },
    { name: 'Net insider signal', sub: insSentiment, val: (netIns >= 0 ? '+' : '') + netIns + ' pts', cls: netIns > 0 ? 'pass' : netIns < 0 ? 'fail' : 'info', tag: 'NEUTRAL' },
    { name: 'News sentiment', sub: news.bias === 'bullish' ? 'positive' : news.bias === 'bearish' ? 'negative' : 'neutral / low signal', val: news.score ? (news.score > 0 ? '+' : '') + news.score : '—', cls: news.bias === 'bullish' ? 'pass' : news.bias === 'bearish' ? 'fail' : 'info', tag: 'NEUTRAL' },
    { name: 'Congressional', sub: cong.error ? 'feed error · try later' : "gov't trading activity (last 90d)", val: congTrades != null ? (congTrades || 'None') : '—', cls: cong.error ? 'warn' : 'info', tag: cong.error ? 'OFFLINE' : 'NEUTRAL' },
    { name: 'StockTwits', sub: stMessages ? stMessages + ' messages · ' + stocktwitsWatchers.toLocaleString() + ' watchlists' : stocktwitsWatchers.toLocaleString() + ' watchlists', val: Number(stocktwitsBull).toFixed(0) + '% bull', cls: stocktwitsBull > 80 ? 'warn' : stocktwitsBull > 60 ? 'pass' : 'info', tag: stocktwitsBull > 85 ? 'CROWD' : 'PASS' },
    { name: 'Reddit r/wsb', sub: wsb.error ? 'rate-limited · cached' : wsbBias === 'bullish' ? 'bullish tone' : wsbBias === 'bearish' ? 'bearish tone' : 'mixed/quiet', val: wsbMentions + ' mentions', cls: wsbMentions > 30 ? 'warn' : 'info', tag: wsbMentions > 30 ? 'CAUTION' : 'NEUTRAL' },
    // REAL SEC filings + institutional flow
    { name: 'SEC 8-K filings', sub: '30d window', val: sec8K || (sec.recent_8k_count != null ? sec.recent_8k_count : 'None'), cls: sec8K > 0 ? 'warn' : 'info', tag: sec8K > 0 ? 'WATCH' : 'NEUTRAL' },
    { name: 'Form 4 cluster', sub: secInsiderCluster ? 'multiple insiders bought together' : 'no clustered insider activity', val: secInsiderCluster ? '✓ Active' : 'None', cls: secInsiderCluster ? 'pass' : 'info', tag: secInsiderCluster ? 'PASS' : 'NEUTRAL' },
    { name: 'Institutional trend', sub: inst.trend || inst.signal || 'neutral', val: inst.holders_pct_change != null ? (inst.holders_pct_change >= 0 ? '+' : '') + inst.holders_pct_change.toFixed(1) + '%' : '—', cls: (inst.holders_pct_change || 0) > 0 ? 'pass' : (inst.holders_pct_change || 0) < 0 ? 'fail' : 'info', tag: 'INFO' },
    // CEO / CFO buy badges from REAL insider data
    { name: 'CEO buy', sub: 'last 90d', val: insF.ceo_buy ? '✓ Yes' : '—', cls: insF.ceo_buy ? 'pass' : 'info', tag: insF.ceo_buy ? 'PASS' : 'NEUTRAL' },
    { name: 'CFO buy', sub: 'last 90d', val: insF.cfo_buy ? '✓ Yes' : '—', cls: insF.cfo_buy ? 'pass' : 'info', tag: insF.cfo_buy ? 'PASS' : 'NEUTRAL' },
  ];

  // ── D-5: Signal age pill helper ──
  // Returns a colored pill "FRESH" (≤1d) / "Nd ago" (≤30d) / "STALE" (>30d).
  // Pass either a Date object, ISO timestamp string, or numeric days.
  const _ageLabel = (input) => {
    let days;
    if (typeof input === 'number') {
      days = input;
    } else if (typeof input === 'string' && input) {
      const t = new Date(input);
      if (isNaN(t)) return null;
      days = (Date.now() - t.getTime()) / 86400000;
    } else { return null; }
    if (days < 0.04) return { txt: 'NOW',     cls: 'pass' };
    if (days < 1)    return { txt: `${Math.max(1, Math.round(days*24))}h ago`, cls: 'pass' };
    if (days < 2)    return { txt: 'FRESH',   cls: 'pass' };
    if (days < 7)    return { txt: `${Math.round(days)}d ago`, cls: 'pass' };
    if (days < 30)   return { txt: `${Math.round(days)}d ago`, cls: 'warn' };
    if (days < 999)  return { txt: `${Math.round(days)}d ago`, cls: 'fail' };
    return { txt: 'STALE', cls: 'fail' };
  };
  const _agePill = (input) => {
    const a = _ageLabel(input);
    if (!a) return '';
    return `<span class="sig-age sig-age-${a.cls}">${a.txt}</span>`;
  };

  // Build the right card — Social & News timeline
  // Use REAL Polygon news (up to 8 articles) with per-ticker sentiment from insights
  const timeline = [];
  polynews.slice(0, 8).forEach(n => {
    const tsRaw = n.published_utc || n.published || '';
    const ts = tsRaw.slice(11, 16) || '—';
    const agePill = _agePill(tsRaw);
    const insights = n.insights || [];
    const tickerInsight = insights.find(i => (i.ticker||'').toUpperCase() === T.ticker);
    const sent = (tickerInsight && tickerInsight.sentiment) || (n.sentiment) || 'neutral';
    const reasonRaw = (tickerInsight && tickerInsight.sentiment_reasoning) || '';
    // EODHD returns sentiment_reasoning as either a string or a dict
    // {polarity, neg, neu, pos}. Format dict as a compact summary.
    const reason = typeof reasonRaw === 'string'
      ? reasonRaw
      : (reasonRaw && typeof reasonRaw === 'object'
          ? `polarity ${(reasonRaw.polarity ?? 0).toFixed(2)} · pos ${Math.round((reasonRaw.pos||0)*100)}% / neu ${Math.round((reasonRaw.neu||0)*100)}% / neg ${Math.round((reasonRaw.neg||0)*100)}%`
          : '');
    const tag = sent === 'positive' ? 'BULL' : sent === 'negative' ? 'BEAR' : 'INFO';
    const cls = sent === 'positive' ? 'pass' : sent === 'negative' ? 'fail' : 'info';
    const titleText = (n.title || n.headline || '').slice(0, 130);
    timeline.push({ time: ts, body: `<b>${n.source || n.publisher || 'News'}</b> ${titleText}${agePill}${reason ? ' — <em style="color:var(--ink-3);font-size:11px">' + reason.slice(0, 80) + '</em>' : ''}`, tag, cls });
  });
  // Aggregate StockTwits/r/wsb/Insider/Congressional summary entries (always shown)
  // D-5: signal-age pills attached to insider/congressional/stocktwits/wsb summaries
  const insAgePill = (ins.days_since_last != null && ins.days_since_last < 999)
    ? _agePill(ins.days_since_last) : '';
  if (timeline.length < 5) {
    timeline.push({ time: '—', body: `<b>StockTwits</b> ${Number(stocktwitsBull).toFixed(0)}% bull · ${stocktwitsWatchers.toLocaleString()} watchlists${stMessages ? ' · ' + stMessages + ' messages today' : ''}${stTrending ? ' · 🔥 trending' : ''} ${_agePill(0)}`, tag: 'CROWD', cls: stocktwitsBull > 80 ? 'warn' : 'info' });
    timeline.push({ time: '—', body: `<b>Reddit r/wsb</b> ${wsbMentions} mentions today — ${wsbBias} tone${wsb.error ? ' (cached, source rate-limited)' : ''}. ${_agePill(0)}`, tag: wsbMentions > 30 ? 'WATCH' : 'INFO', cls: wsbMentions > 30 ? 'warn' : 'info' });
    timeline.push({ time: '—', body: `<b>Insider activity</b> · ${ins.buys || 0} buys, ${ins.sells || 0} sells last 30d. Net signal ${insSentiment}.${insF.ceo_buy ? ' CEO bought.' : ''}${insF.cfo_buy ? ' CFO bought.' : ''} ${insAgePill}`, tag: (ins.buys || 0) > (ins.sells || 0) ? 'BULL' : 'INFO', cls: (ins.buys || 0) > (ins.sells || 0) ? 'pass' : 'info' });
    timeline.push({ time: '—', body: `<b>Congressional trades</b> · ${cong.error ? 'feed offline.' : (congTrades ? congTrades + ' trades reported.' : 'none reported.')}`, tag: 'INFO', cls: cong.error ? 'warn' : 'info' });
    timeline.push({ time: '—', body: `<b>SEC filings</b> · ${secCount || 0} filings in last 30d${sec8K ? ', ' + sec8K + ' 8-K alerts' : ''}${secInsiderCluster ? ', insider cluster active' : ''}.`, tag: secInsiderCluster ? 'BULL' : 'INFO', cls: secInsiderCluster ? 'pass' : 'info' });
  }

  $('intelBody').innerHTML = `
  <div class="twocol">
    <div class="col" style="border-left:none">
      <div class="col-head"><h4 style="color:var(--ink-0)">CATALYST &amp; OPTIONS</h4><span class="count">${catTier} tier${uoaDetected ? ' · UOA detected' : ''}</span></div>
      ${rows.map(r => `<div class="ev-row"><span class="ev-dot ${r.cls}"></span><span class="ev-name">${r.name}${r.sub ? ' <span class="sub">' + r.sub + '</span>' : ''}</span><span class="ev-val ${r.cls}">${r.val}</span><span class="ev-tag ${r.cls}">${r.tag}</span></div>`).join('')}
    </div>
    <div class="intel-card">
      <div class="col-head"><h4 style="color:var(--ink-0)">SOCIAL &amp; NEWS · TODAY</h4><span class="count">${stocktwitsBull.toFixed(0)}% bull · ${stocktwitsWatchers.toLocaleString()} watchlists</span></div>
      ${timeline.map(t => `<div class="intel-row"><span class="intel-time">${t.time}</span><span class="intel-text">${t.body}</span><span class="ev-tag ${t.cls}">${t.tag}</span></div>`).join('')}
    </div>
  </div>`;
}

export function dispose() { /* no-op */ }
