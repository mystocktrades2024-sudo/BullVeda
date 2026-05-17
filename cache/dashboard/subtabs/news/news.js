// subtabs/news/news.js — extracted from elite-detail.html (renderNewsTab 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const polynews = T.news_articles || [];
  const polyscore = T.news_sentiment_score || {};
  const items = polynews.slice(0, 30);
  if (items.length === 0) {
    $('newsBody').innerHTML = `
      <div class="nws-empty">
        <div class="ico">○</div>
        <div class="h">No news articles for ${T.ticker}</div>
        <div class="sub">No EODHD news in the configured window. Try expanding the date range or check that the news endpoint is healthy.</div>
      </div>`;
    return;
  }

  // Decorate each item with sentiment + parsed reasoning
  const decorated = items.map(n => {
    const ts = n.published_utc || n.published || '';
    const dt = ts ? new Date(ts) : null;
    const timeStr = dt ? dt.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
    const insights = n.insights || [];
    const ti = insights.find(i => (i.ticker || '').toUpperCase() === T.ticker);
    const sent = (ti && ti.sentiment) || n.sentiment || 'neutral';
    const reasonRaw = (ti && ti.sentiment_reasoning) || null;
    let reason = '', polarity = null, posPct = null, neuPct = null, negPct = null;
    if (typeof reasonRaw === 'string') {
      reason = reasonRaw;
    } else if (reasonRaw && typeof reasonRaw === 'object') {
      polarity = reasonRaw.polarity;
      posPct = (reasonRaw.pos || 0) * 100;
      neuPct = (reasonRaw.neu || 0) * 100;
      negPct = (reasonRaw.neg || 0) * 100;
    }
    return {
      title: (n.title || n.headline || '').slice(0, 220),
      url:   n.article_url || n.url || '#',
      source: n.publisher?.name || n.source || n.publisher || 'News',
      timeStr, ts: dt,
      sent, reason, polarity, posPct, neuPct, negPct,
    };
  });

  // Counts
  const cBull = decorated.filter(d => d.sent === 'positive').length;
  const cBear = decorated.filter(d => d.sent === 'negative').length;
  const cNeut = decorated.filter(d => d.sent === 'neutral').length;
  const total = decorated.length;
  const momentum = (typeof polyscore === 'object' ? polyscore.momentum : null) || 'neutral';
  const breaking = (typeof polyscore === 'object' ? polyscore.breaking : false);

  let summTone, summEm, summArrow;
  if (cBull > cBear * 1.5) { summTone = 'bull'; summEm = 'BULLISH'; summArrow = '▲'; }
  else if (cBear > cBull * 1.5) { summTone = 'bear'; summEm = 'BEARISH'; summArrow = '▼'; }
  else { summTone = 'neutral'; summEm = 'MIXED'; summArrow = '◆'; }

  $('newsBody').innerHTML = `
    <!-- SUMMARY BANNER -->
    <div class="nws-summary ${summTone}">
      <div class="nws-s-arrow">${summArrow}</div>
      <div class="nws-s-mid">
        <div class="tag">NEWS COVERAGE · ${T.ticker}</div>
        <div class="h">News flow is <span class="em">${summEm}</span>${breaking ? ' · ⚡ BREAKING' : ''}</div>
      </div>
      <div class="nws-s-stat"><div class="v">${total}</div><div class="lbl">Articles</div></div>
      <div class="nws-s-stat"><div class="v pass">${cBull}</div><div class="lbl">Bull</div></div>
      <div class="nws-s-stat"><div class="v fail">${cBear}</div><div class="lbl">Bear</div></div>
    </div>

    <!-- FILTER PILLS -->
    <div class="nws-filters">
      <span class="lbl">Filter</span>
      <span class="nws-filter-pill on" data-flt="all" onclick="nwsFilter('all',this)">All<span class="ct">${total}</span></span>
      <span class="nws-filter-pill" data-flt="positive" onclick="nwsFilter('positive',this)">Bull<span class="ct">${cBull}</span></span>
      <span class="nws-filter-pill" data-flt="negative" onclick="nwsFilter('negative',this)">Bear<span class="ct">${cBear}</span></span>
      <span class="nws-filter-pill" data-flt="neutral" onclick="nwsFilter('neutral',this)">Neutral<span class="ct">${cNeut}</span></span>
      <span style="margin-left:auto;font-size:10px;color:var(--ink-1);font-weight:600">Click an article to open in new tab</span>
    </div>

    <!-- ARTICLES LIST -->
    <div class="nws-list" id="nwsList">
      ${decorated.map(d => {
        const cls = d.sent === 'positive' ? 'bull' : d.sent === 'negative' ? 'bear' : 'neut';
        const tag = d.sent === 'positive' ? 'BULL' : d.sent === 'negative' ? 'BEAR' : 'NEUT';
        const polTxt = d.polarity != null ? `polarity ${d.polarity >= 0 ? '+' : ''}${d.polarity.toFixed(2)}` : '';
        const barSegs = (d.posPct != null && d.negPct != null) ? `
          <div class="nws-item-bar">
            ${d.posPct > 0 ? `<div class="seg pos" style="flex:${d.posPct}" title="${d.posPct.toFixed(0)}% positive"></div>` : ''}
            ${d.neuPct > 0 ? `<div class="seg neu" style="flex:${d.neuPct}" title="${d.neuPct.toFixed(0)}% neutral"></div>` : ''}
            ${d.negPct > 0 ? `<div class="seg neg" style="flex:${d.negPct}" title="${d.negPct.toFixed(0)}% negative"></div>` : ''}
          </div>` : '';
        const reasonText = d.reason ? d.reason.slice(0, 220)
          : (d.posPct != null ? `${d.posPct.toFixed(0)}% positive · ${d.neuPct.toFixed(0)}% neutral · ${d.negPct.toFixed(0)}% negative` : '');
        return `
          <a class="nws-item ${cls}" data-sent="${d.sent}" href="${d.url}" target="_blank" rel="noopener">
            <div class="nws-item-meta">
              <span class="ts">${d.timeStr}</span>
              <span class="src">${d.source}</span>
              <span class="pill ${cls}">${tag}</span>
              ${polTxt ? `<span class="polarity">${polTxt}</span>` : ''}
            </div>
            <div class="nws-item-title">${d.title}</div>
            ${reasonText ? `<div class="nws-item-reason">${reasonText}</div>` : ''}
            ${barSegs}
          </a>`;
      }).join('')}
    </div>`;
}

export function dispose() { /* no-op */ }
