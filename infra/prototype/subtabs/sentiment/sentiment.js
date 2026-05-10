// subtabs/sentiment/sentiment.js — extracted from elite-detail.html (renderSentimentTab 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const ins = T.insider || {}, insF = T.insider_full || {};
  const news = T.news || {};
  const polynews = T.news_articles || [];
  const polyscore = T.news_sentiment_score || {};
  const eodhdSent = T.eodhd_sentiment || {};
  const sec = T.sec_filings || {};
  const inst = T.inst_trend || {};
  const sentComp = T.sentiment || {};
  const sentDetails = sentComp.details || {};

  // ─── News article sentiment breakdown ───
  const articleSent = polynews.map(n => {
    const insights = n.insights || [];
    const ti = insights.find(i => (i.ticker || '').toUpperCase() === T.ticker);
    return ti?.sentiment || n.sentiment || 'neutral';
  });
  const newsBull = articleSent.filter(s => s === 'positive').length;
  const newsBear = articleSent.filter(s => s === 'negative').length;
  const newsNeut = articleSent.filter(s => s === 'neutral').length;
  const newsTotal = polynews.length;
  const newsScore = (typeof polyscore === 'object' ? polyscore.score : polyscore) || 0;
  const newsMomentum = (typeof polyscore === 'object' ? polyscore.momentum : null) || 'neutral';
  const newsBreaking = (typeof polyscore === 'object' ? polyscore.breaking : false);

  // ─── Insider summary ───
  const netIns = (insF.net_signal != null) ? insF.net_signal : ((ins.buys || 0) - (ins.sells || 0));
  const insBuyValue = insF.buy_value_30d || ins.buy_value || 0;
  const insSellValue = insF.sell_value_30d || ins.sell_value || 0;

  // ─── EODHD sentiment timeseries ───
  const eodhdLatest = eodhdSent.latest;
  const eodhdAvg7 = eodhdSent.avg_7d;
  const eodhdAvg30 = eodhdSent.avg_30d;
  const eodhdTrend = eodhdSent.trend || 'flat';
  const eodhdHistory = eodhdSent.history || [];

  // ─── Composite tone ───
  const sentBullPts = (newsBull > newsBear ? 1 : 0)
    + (eodhdLatest != null && eodhdLatest > 0.1 ? 1 : 0)
    + (netIns > 0 ? 1 : 0);
  const sentBearPts = (newsBear > newsBull ? 1 : 0)
    + (eodhdLatest != null && eodhdLatest < -0.1 ? 1 : 0)
    + (netIns < 0 ? 1 : 0);
  let tone, hEm, arrow;
  if (sentBullPts > sentBearPts && sentBullPts >= 2) { tone = 'bull'; hEm = 'BULLISH'; arrow = '▲'; }
  else if (sentBearPts > sentBullPts && sentBearPts >= 2) { tone = 'bear'; hEm = 'BEARISH'; arrow = '▼'; }
  else { tone = 'neutral'; hEm = 'NEUTRAL'; arrow = '◆'; }

  const compScore = sentComp.score || 0;
  const compMax = sentComp.max || 10;

  const narr = [];
  if (newsTotal) narr.push(`${newsTotal} news articles in window — ${newsBull} bullish · ${newsBear} bearish · ${newsNeut} neutral`);
  if (newsMomentum && newsMomentum !== 'neutral') narr.push(`news momentum <b>${newsMomentum}</b>`);
  if (eodhdLatest != null) narr.push(`EODHD aggregator ${eodhdLatest >= 0 ? '+' : ''}${eodhdLatest.toFixed(2)} (${eodhdTrend})`);
  if (netIns !== 0) narr.push(`insider ${netIns > 0 ? '+' : ''}${netIns} net (${ins.buys || 0} buys / ${ins.sells || 0} sells)`);

  const fmt2 = v => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2);
  const dollarsM = v => v == null || v === 0 ? '—' : '$' + (v / 1e6).toFixed(2) + 'M';

  // Sparkline SVG for EODHD history
  const sparkSvg = (() => {
    if (eodhdHistory.length < 2) return '';
    const W = 200, H = 40, pad = 2;
    const vals = eodhdHistory.slice(0, 30).reverse().map(r => +r.normalized || 0);
    const minV = Math.min(...vals, -0.1), maxV = Math.max(...vals, 0.1);
    const range = (maxV - minV) || 0.2;
    const xS = i => pad + (i / Math.max(1, vals.length - 1)) * (W - pad*2);
    const yS = v => pad + ((maxV - v) / range) * (H - pad*2);
    const yZero = yS(0);
    const path = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(i).toFixed(1)},${yS(v).toFixed(1)}`).join(' ');
    const fillPath = path + ` L${xS(vals.length-1).toFixed(1)},${yZero.toFixed(1)} L${xS(0).toFixed(1)},${yZero.toFixed(1)} Z`;
    const trendColor = eodhdTrend === 'rising' ? '#4ade80' : eodhdTrend === 'falling' ? '#f87171' : '#94a3b8';
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:40px;display:block">
      <line x1="${pad}" y1="${yZero}" x2="${W-pad}" y2="${yZero}" stroke="rgba(148,163,184,0.3)" stroke-dasharray="2 3"/>
      <path d="${fillPath}" fill="${trendColor}" fill-opacity="0.18"/>
      <path d="${path}" fill="none" stroke="${trendColor}" stroke-width="1.5"/>
    </svg>`;
  })();

  $('sentimentBody').innerHTML = `
    <!-- VERDICT BANNER -->
    <div class="snt-verdict ${tone}">
      <div class="snt-v-arrow">${arrow}</div>
      <div class="snt-v-mid">
        <div class="tag">SENTIMENT POSTURE · ${hEm}</div>
        <div class="h">Sentiment is <span class="em">${hEm}</span></div>
        <div class="narr">${narr.length ? narr.join(' · ') + '.' : 'Limited sentiment data — relying on technical/fundamental signals.'}</div>
      </div>
      <div class="snt-v-r">
        <div class="snt-v-score">${compScore}<span class="frac">/${compMax}</span></div>
        <div class="snt-v-score-lbl">Composite Score</div>
      </div>
    </div>

    <!-- 3 PRIMARY SOURCES -->
    <div class="snt-grid">
      <div class="snt-card">
        <div class="snt-card-h"><span class="ico">📰</span>NEWS SENTIMENT<span class="badge ${newsMomentum === 'bullish' ? 'pass' : newsMomentum === 'bearish' ? 'fail' : 'info'}">${newsMomentum.toUpperCase()}</span></div>
        <div class="snt-bigstat"><span class="v ${newsBull > newsBear ? 'pass' : newsBear > newsBull ? 'fail' : ''}">${newsTotal}</span><span class="u">articles · last ${T.news_window_days || 7}d</span></div>
        ${newsTotal > 0 ? `
        <div class="snt-source-bar"><span class="name">Bullish</span><div class="gauge"><div class="gauge-fill bull" style="width:${(newsBull/newsTotal*100).toFixed(0)}%"></div></div><span class="v">${newsBull}</span><span class="pill-mini bull">${(newsBull/newsTotal*100).toFixed(0)}%</span></div>
        <div class="snt-source-bar"><span class="name">Bearish</span><div class="gauge"><div class="gauge-fill bear" style="width:${(newsBear/newsTotal*100).toFixed(0)}%"></div></div><span class="v">${newsBear}</span><span class="pill-mini bear">${(newsBear/newsTotal*100).toFixed(0)}%</span></div>
        <div class="snt-source-bar"><span class="name">Neutral</span><div class="gauge"><div class="gauge-fill neut" style="width:${(newsNeut/newsTotal*100).toFixed(0)}%"></div></div><span class="v">${newsNeut}</span><span class="pill-mini neut">${(newsNeut/newsTotal*100).toFixed(0)}%</span></div>
        ` : '<div class="snt-empty-line">No news articles in window</div>'}
        <div class="snt-row" style="margin-top:8px"><span class="l">NLP score</span><span class="r ${newsScore >= 2 ? 'pass' : newsScore <= -2 ? 'fail' : ''}">${newsScore >= 0 ? '+' : ''}${newsScore}</span></div>
        ${newsBreaking ? '<div class="snt-row"><span class="l">Breaking news</span><span class="r warn">⚡ ACTIVE</span></div>' : ''}
        <div class="snt-row" style="border-bottom:none"><span class="l">News bias</span><span class="r ${news.bias === 'bullish' ? 'pass' : news.bias === 'bearish' ? 'fail' : ''}">${news.bias || 'neutral'}</span></div>
      </div>

      <div class="snt-card">
        <div class="snt-card-h"><span class="ico">📊</span>EODHD AGGREGATOR<span class="badge ${eodhdTrend === 'rising' ? 'pass' : eodhdTrend === 'falling' ? 'fail' : 'dim'}">${eodhdTrend.toUpperCase()}</span></div>
        ${eodhdLatest != null ? `
        <div class="snt-bigstat"><span class="v ${eodhdLatest > 0.1 ? 'pass' : eodhdLatest < -0.1 ? 'fail' : ''}">${fmt2(eodhdLatest)}</span><span class="u">today's polarity</span></div>
        ${sparkSvg ? `<div style="margin:6px 0 8px">${sparkSvg}<div style="display:flex;justify-content:space-between;font-size:9.5px;color:var(--ink-1);margin-top:2px;font-weight:600"><span>30d ago</span><span>today</span></div></div>` : ''}
        <div class="snt-row"><span class="l">Latest</span><span class="r">${fmt2(eodhdLatest)}</span></div>
        <div class="snt-row"><span class="l">7-day avg</span><span class="r">${fmt2(eodhdAvg7)}</span></div>
        <div class="snt-row"><span class="l">30-day avg</span><span class="r">${fmt2(eodhdAvg30)}</span></div>
        <div class="snt-row" style="border-bottom:none"><span class="l">Article count (30d)</span><span class="r">${eodhdSent.count || 0}</span></div>
        ` : `
        <div class="snt-empty-line" style="padding:24px 0">
          <div style="font-size:24px;opacity:.35;margin-bottom:4px">○</div>
          <div style="font-weight:600;color:var(--ink-1)">EODHD sentiment data not yet populated</div>
          <div style="font-size:10.5px;color:var(--ink-1);margin-top:4px">Will populate after next scan run</div>
        </div>
        `}
      </div>

      <div class="snt-card">
        <div class="snt-card-h"><span class="ico">🐋</span>SMART MONEY<span class="badge ${netIns > 0 || (inst.inst_trend === 'increasing') ? 'pass' : netIns < 0 || (inst.inst_trend === 'decreasing') ? 'fail' : 'info'}">${insF.ceo_buy ? 'CEO ✓' : netIns > 0 ? 'BUYING' : netIns < 0 ? 'SELLING' : 'NEUTRAL'}</span></div>
        <div class="snt-bigstat"><span class="v ${netIns > 0 ? 'pass' : netIns < 0 ? 'fail' : ''}">${netIns >= 0 ? '+' : ''}${netIns}</span><span class="u">net insider txns 30d</span></div>
        <div class="snt-row"><span class="l">Insider buys</span><span class="r pass">${ins.buys || 0}${insBuyValue ? ' · ' + dollarsM(insBuyValue) : ''}</span></div>
        <div class="snt-row"><span class="l">Insider sells</span><span class="r fail">${ins.sells || 0}${insSellValue ? ' · ' + dollarsM(insSellValue) : ''}</span></div>
        <div class="snt-row"><span class="l">C-suite</span><span class="r ${insF.ceo_buy || insF.cfo_buy ? 'pass' : ''}">${insF.ceo_buy ? 'CEO buy ✓' : ''}${insF.cfo_buy ? ' CFO buy ✓' : ''}${!insF.ceo_buy && !insF.cfo_buy ? 'none' : ''}</span></div>
        <div class="snt-row"><span class="l">Inst own%</span><span class="r">${inst.inst_pct != null ? inst.inst_pct.toFixed(1) + '%' : '—'}</span></div>
        <div class="snt-row" style="border-bottom:none"><span class="l">Inst flow trend</span><span class="r ${inst.inst_trend === 'increasing' ? 'pass' : inst.inst_trend === 'decreasing' ? 'fail' : ''}">${inst.inst_trend || '—'}</span></div>
      </div>
    </div>

    <!-- CATALYST + SOCIAL ROW -->
    <div class="snt-grid" style="grid-template-columns:1fr 1fr">
      <div class="snt-card">
        <div class="snt-card-h"><span class="ico">⚡</span>SEC CATALYSTS<span class="badge ${sec.has_material_event ? 'warn' : sec.catalyst_signal === 'positive' ? 'pass' : sec.catalyst_signal === 'negative' ? 'fail' : 'dim'}">${(sec.catalyst_signal || 'none').toUpperCase()}</span></div>
        <div class="snt-row"><span class="l">Catalyst signal</span><span class="r ${sec.catalyst_signal === 'positive' ? 'pass' : sec.catalyst_signal === 'negative' ? 'fail' : ''}">${sec.catalyst_signal || 'none'}</span></div>
        <div class="snt-row"><span class="l">Material 8-K event</span><span class="r ${sec.has_material_event ? 'warn' : ''}">${sec.has_material_event ? '⚡ DETECTED' : 'none'}</span></div>
        <div class="snt-row"><span class="l">Filings (recent)</span><span class="r">${(sec.filings || []).length}</span></div>
        <div class="snt-row" style="border-bottom:none"><span class="l">Insider Form 4 filings</span><span class="r">${sec.insider_filing_count || 0}</span></div>
      </div>

      <div class="snt-card">
        <div class="snt-card-h"><span class="ico">💬</span>SOCIAL FEEDS<span class="badge dim">FEEDS OFFLINE</span></div>
        <div class="snt-row"><span class="l">StockTwits</span><span class="r" style="color:var(--ink-1);font-style:italic;font-family:inherit;font-weight:500">— feed not connected —</span></div>
        <div class="snt-row"><span class="l">Reddit r/wallstreetbets</span><span class="r" style="color:var(--ink-1);font-style:italic;font-family:inherit;font-weight:500">— feed not connected —</span></div>
        <div class="snt-row"><span class="l">Congressional trading</span><span class="r" style="color:var(--ink-1);font-style:italic;font-family:inherit;font-weight:500">— feed not connected —</span></div>
        <div class="snt-empty-line" style="padding:8px 0;text-align:left;border-top:1px dashed var(--rule);margin-top:8px;font-style:normal">News + EODHD + Insider + Inst flow above are the active sentiment sources.</div>
      </div>
    </div>

    <!-- COMPOSITE BREAKDOWN -->
    ${Object.keys(sentDetails).length ? `
    <div class="snt-card" style="margin-bottom:14px">
      <div class="snt-card-h"><span class="ico">🧮</span>COMPOSITE SCORE BREAKDOWN<span class="badge ${compScore >= 7 ? 'pass' : compScore >= 5 ? 'info' : 'warn'}">${compScore}/${compMax}</span></div>
      ${Object.entries(sentDetails).filter(([k, v]) => typeof v === 'string' && !['squeeze_score','squeeze_probability','short_float_pct','days_to_cover'].includes(k)).map(([k, v]) => {
        const m = v.match(/\((\d+)\/(\d+)\)/);
        const cls = m ? (parseInt(m[1]) / parseInt(m[2]) >= 0.7 ? 'pass' : parseInt(m[1]) / parseInt(m[2]) >= 0.4 ? 'warn' : 'fail') : '';
        return `<div class="snt-row"><span class="l">${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span><span class="r ${cls}" style="font-family:inherit;font-weight:500;text-align:right;max-width:75%;font-size:11px">${v.slice(0, 120)}</span></div>`;
      }).join('')}
    </div>` : ''}

    <!-- HORIZON IMPACT -->
    <div class="ins-pat">
      <div class="smc-card-h"><span class="ico">🎯</span>SENTIMENT IMPACT BY HORIZON</div>
      <div class="ins-hz-grid">
        <div class="ins-hz ${tone === 'bull' && newsTotal > 5 ? 'major' : tone === 'bear' ? 'medium' : 'minor'}">
          <div class="ins-hz-h">⚡ SWING<span class="impact">${tone === 'bull' && newsTotal > 5 ? 'MAJOR' : tone === 'bear' ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${tone === 'bull' && newsTotal > 5 ? 'High news flow + bullish bias = catalyst-driven swing setup. Watch for fade if euphoria peaks.' : tone === 'bear' ? 'Negative sentiment near-term — short pullbacks or avoid.' : 'Quiet sentiment — pure technical setup.'}</div>
        </div>
        <div class="ins-hz ${eodhdTrend === 'rising' && tone === 'bull' ? 'major' : eodhdTrend === 'falling' ? 'medium' : 'minor'}">
          <div class="ins-hz-h">📈 POSITION<span class="impact">${eodhdTrend === 'rising' && tone === 'bull' ? 'MAJOR' : eodhdTrend === 'falling' ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${eodhdTrend === 'rising' ? 'Sentiment trend rising over 7d vs 30d — momentum building, supports multi-week hold.' : eodhdTrend === 'falling' ? 'Sentiment cooling — reduce Position size or wait for stabilization.' : 'No clear sentiment trend.'}</div>
        </div>
        <div class="ins-hz ${netIns > 0 || inst.inst_trend === 'increasing' ? 'major' : netIns < 0 || inst.inst_trend === 'decreasing' ? 'medium' : 'minor'}">
          <div class="ins-hz-h">🚀 INVEST<span class="impact">${netIns > 0 || inst.inst_trend === 'increasing' ? 'MAJOR' : netIns < 0 ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${netIns > 0 || inst.inst_trend === 'increasing' ? 'Smart money flow positive — institutional and insider conviction supports long-term hold.' : netIns < 0 || inst.inst_trend === 'decreasing' ? 'Smart money distributing — re-examine fundamental thesis.' : 'No clear smart-money signal.'}</div>
        </div>
      </div>
    </div>

    ${_renderShortPressureCard(T)}`;
}

export function dispose() { /* no-op */ }
