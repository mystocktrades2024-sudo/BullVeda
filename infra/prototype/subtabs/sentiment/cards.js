// subtabs/sentiment/cards.js — view layer for the Sentiment sub-tab.
// Verdict banner + 3 primary source cards + Catalyst/Social row +
// Composite breakdown + Horizon impact. Returns one HTML chunk.

import { fmt2, dollarsM } from './aggregate.js';

export function buildBody(T, agg) {
  const { tone, hEm, arrow, compScore, compMax, narr,
          ins, insF, news, sec, inst, sentDetails,
          newsBull, newsBear, newsNeut, newsTotal, newsScore, newsMomentum, newsBreaking,
          netIns, insBuyValue, insSellValue,
          eodhdLatest, eodhdAvg7, eodhdAvg30, eodhdTrend, eodhdCount,
          sparkSvg } = agg;

  return `
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
        <div class="snt-row" style="border-bottom:none"><span class="l">Article count (30d)</span><span class="r">${eodhdCount}</span></div>
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
        const m   = v.match(/\((\d+)\/(\d+)\)/);
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

    ${typeof window._renderShortPressureCard === 'function' ? window._renderShortPressureCard(T) : ''}`;
}
