// subtabs/overview/overview.js — extracted from elite-detail.html (renderEliteOverview 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const body = $('eliteOverviewBody');
  if (!body || !T) return;
  const rawV = (T.decision?.verdict || T.verdict || T.stage || 'WATCH').toUpperCase();
  // ── DEMOTION DETECTION ── (kept consistent with fdPopulateHeader)
  const eqRaw = (T.entry_quality || '').toUpperCase();
  const convLbl = (T.conviction && T.conviction.label) || '';
  const tailDemoted = T.conviction && T.conviction.tail_filter_demoted === true;
  const eqBad = ['EXTENDED','MISSED'].includes(eqRaw);
  const isDemoted = (rawV === 'BUY') && (eqBad || convLbl === 'WATCH' || tailDemoted);
  const demoteReason = eqBad ? `Entry ${eqRaw} — chase territory`
                     : convLbl === 'WATCH' ? 'Tail-filter demoted'
                     : tailDemoted ? 'Tail-filter demoted' : '';
  const v = isDemoted ? 'WAIT' : rawV;
  const vColor = isDemoted ? 'var(--warn)' :
                 v === 'BUY' ? 'var(--pass)' :
                 v === 'WATCH' ? 'var(--warn)' : 'var(--fail)';
  const score = +T.score || 0;
  // Use conviction label from data if present (it already reflects demotion)
  const tier = (T.conviction && T.conviction.label) || T.conviction_tier ||
               (score >= 88 ? 'T1' : score >= 78 ? 'T2' : score >= 70 ? 'T3' : 'WATCH');
  const c = +T.pct_chg || 0, upDn = c > 0 ? 'up' : c < 0 ? 'dn' : '';
  const pX = +T.price || 0;
  // K-extra (2026-05-09): canonical_trade_plan first, then legacy fields. The
  // Overview tab is the source from which Vinod calibrates other tabs — must
  // surface identical numbers as Plan/Thesis/SMC/Models.
  const _ctp = T?.canonical_trade_plan;
  const stop = +(_ctp?.stop ?? T.trade_plan?.stop ?? T.stop ?? 0);
  const t1   = +(_ctp?.target1 ?? T.trade_plan?.target1 ?? T.target1 ?? T.t1 ?? 0);
  const t2   = +(_ctp?.target2 ?? T.trade_plan?.target2 ?? T.target2 ?? T.t2 ?? 0);
  const eLo  = +(_ctp?.entry?.low  ?? T.trade_plan?.entry_low  ?? T.entry_lo ?? pX);
  const eHi  = +(_ctp?.entry?.high ?? T.trade_plan?.entry_high ?? T.entry_hi ?? pX);
  const stopPct = stop && pX ? ((stop - pX) / pX * 100) : 0;
  const t1Pct   = t1 && pX ? ((t1 - pX) / pX * 100) : 0;
  const t2Pct   = t2 && pX ? ((t2 - pX) / pX * 100) : 0;
  const cachedRR = +(_ctp?.risk?.rr_ratio ?? T.trade_plan?.rr_ratio ?? T.rr_ratio ?? T.rr ?? 0);
  // Compute real R:R from CURRENT price (not entry-zone midpoint)
  const realRR = (pX && stop && t1 && pX > stop && t1 > pX)
                 ? (t1 - pX) / (pX - stop) : null;
  const rr = isDemoted && realRR != null ? realRR : cachedRR;
  const rrLabel = isDemoted && realRR != null ? `R:R ${realRR.toFixed(2)}:1 NOW` : `R:R ${cachedRR.toFixed(1)}:1`;
  // Pullback zone from trade_plan
  const pbLo = +(T.trade_plan?.primary_zone_low || T.trade_plan?.shallow_zone_low || 0);
  const pbHi = +(T.trade_plan?.primary_zone_high || T.trade_plan?.shallow_zone_high || 0);
  const pullbackZone = (pbLo && pbHi) ? `$${pbLo.toFixed(2)}–$${pbHi.toFixed(2)}` :
                       (eLo) ? `$${eLo.toFixed(2)} or below` : '';
  const sb = T.scoring_breakdown || {};
  const techS = +(T.tech_score || sb.tech_score || 0);
  const catS  = +(T.cat_score  || sb.cat_score  || 0);
  const rsS   = +(T.rs_score   || sb.rs_score   || 0);
  const smS   = +(T.sm_score   || sb.sm_score   || 0);
  const qS    = +(T.qg_score   || sb.qg_score   || T.fund_score || 0);
  // ── 2026-05-10: align Overview reads with sibling-tab canonical sources ──
  // Technicals: read T.technicals.indicators FIRST (matches subtabs/technicals/chart.js)
  const techI = T.technicals?.indicators || {};
  const rsi = +(techI.rsi ?? T.rsi ?? 0);
  const rvol = +(techI.rvol ?? T.rvol ?? 0);
  const adx = +(techI.adx ?? T.adx ?? 0);
  const atrPct = +(techI.atr_pct ?? T.atr_pct ?? 0);
  const above50 = !!(techI.above_ema50 ?? T.above_50ema);
  const above200 = !!(techI.above_sma200 ?? T.above_200sma);
  const macdBull = !!(techI.macd_bullish ?? T.macd_bullish);
  const sqz = !!(techI.squeeze_on ?? T.squeeze_on);
  const rsRank = T.rs_rank || 0;
  const setupTxt = T.setup_family || T.setup || '';
  const catTags = (T.catalyst_tags || []).slice(0, 6);

  // Insider: read T.insider_full FIRST (matches subtabs/insider/aggregate.js precedence)
  const ins  = T.insider_full || T.insider || T.insider_data || {};

  // Sentiment: pull from canonical objects matching subtabs/sentiment/aggregate.js
  const ana       = T.analyst_full || T.analyst || {};
  const eodhdSent = T.eodhd_sentiment || {};
  const newsScore = T.news_sentiment_score || {};
  const newsArts  = T.news_articles || [];

  // Fundamentals: pull from T.fund_details / T.fund_real / T.eodhd_fund_extras
  // FIRST (matches subtabs/fundamentals/fundamentals.js); fall back to flat fields.
  const fd  = T.fund_details || {};
  const fr  = T.fund_real || {};
  const fx  = T.eodhd_fund_extras || {};

  // Options: pull from T.options_iv FIRST (matches subtabs/options/*)
  const oiv = T.options_iv || {};
  const fmtMcap = m => !m ? '—' : m >= 1e12 ? '$' + (m/1e12).toFixed(2) + 'T' : m >= 1e9 ? '$' + (m/1e9).toFixed(1) + 'B' : '$' + (m/1e6).toFixed(0) + 'M';

  // SVG score arc
  const arcPct = Math.max(0, Math.min(100, score)) / 100;
  const r = 30, C = 2 * Math.PI * r;
  const arc = `<svg class="ov-score-ring" viewBox="0 0 70 70">
    <circle cx="35" cy="35" r="${r}" fill="none" stroke="var(--bg-2)" stroke-width="5"/>
    <circle cx="35" cy="35" r="${r}" fill="none" stroke="${vColor}" stroke-width="5" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - arcPct)}"
            transform="rotate(-90 35 35)"/>
    <text x="35" y="35" text-anchor="middle" dominant-baseline="central"
          font-size="20" font-weight="800" fill="${vColor}">${score}</text>
  </svg>`;

  // Chart sparkline (60-bar with stop/T1/T2 levels)
  const bars = T.ohlcv || T.bars || [];
  let chartSvg = '<div style="height:80px;display:flex;align-items:center;color:var(--paper-3);font-size:11px">No chart data</div>';
  if (Array.isArray(bars) && bars.length >= 5) {
    const closes = bars.slice(-60).map(b => b.c || b.close).filter(x => x != null);
    if (closes.length >= 5) {
      const maxR = Math.max(...closes, t1, t2 || 0, eHi);
      const minR = Math.min(...closes, stop, eLo);
      const rng = (maxR - minR) || 1;
      const W = 100, H = 80, pad = 4;
      const yFor = vv => H - pad - ((vv - minR) / rng) * (H - pad * 2);
      const xs = closes.map((_, i) => (i / (closes.length - 1)) * W);
      const pts = closes.map((cc, i) => `${xs[i].toFixed(2)},${yFor(cc).toFixed(2)}`).join(' ');
      const last = closes[closes.length - 1];
      const lc = last >= closes[0] ? 'var(--pass)' : 'var(--fail)';
      const lvl = (val, color) => {
        const y = yFor(val);
        if (y < pad || y > H - pad) return '';
        return `<line x1="0" x2="${W}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}" stroke="${color}" stroke-width="0.4" stroke-dasharray="1.5 1.5" opacity="0.7"/>`;
      };
      chartSvg = `<svg class="ov-chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <defs><linearGradient id="ov-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="${lc}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="${lc}" stop-opacity="0"/>
        </linearGradient></defs>
        <polygon fill="url(#ov-grad)" points="0,${H} ${pts} ${W},${H}"/>
        <polyline fill="none" stroke="${lc}" stroke-width="1" stroke-linejoin="round" points="${pts}"/>
        ${lvl(stop, 'var(--fail)')}${lvl(eLo, 'var(--info)')}${eHi !== eLo ? lvl(eHi, 'var(--info)') : ''}
        ${t1 ? lvl(t1, 'var(--pass)') : ''}${t2 ? lvl(t2, 'var(--pass)') : ''}
        <circle cx="${xs[xs.length-1].toFixed(2)}" cy="${yFor(last).toFixed(2)}" r="1.5" fill="${lc}"/>
      </svg>`;
    }
  }

  // Pillar bars
  const pillars = [
    {l: 'TECH',  v: techS, m: T.tech_max || 35, c: 'var(--pass)'},
    {l: 'CAT',   v: catS,  m: 20,                c: 'var(--info)'},
    {l: 'RS',    v: rsS,   m: 20,                c: 'var(--info)'},
    {l: 'SM$',   v: smS,   m: 15,                c: 'var(--warn)'},
    {l: 'QUAL',  v: qS,    m: T.fund_max || 10,  c: 'var(--warn)'},
  ];
  const pillarsHtml = `<div class="ov-pillars">${pillars.map(p => {
    const pct = Math.max(0, Math.min(100, (p.v / p.m) * 100));
    return `<div class="ov-pillar"><span class="l">${p.l}</span><div class="bar"><div class="fill" style="width:${pct.toFixed(0)}%;background:${p.c}"></div></div><span class="v">${p.v}<span style="opacity:0.5;font-weight:500">/${p.m}</span></span></div>`;
  }).join('')}</div>`;

  // Demotion banner — shows above the entire Overview grid when system says wait
  const demoteBanner = isDemoted ? `
  <div style="background:linear-gradient(135deg,rgba(234,179,8,0.10),rgba(234,179,8,0.02));border:1px solid #eab308;border-left:4px solid #eab308;border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:13px;color:#fde68a;display:flex;align-items:flex-start;gap:14px">
    <div style="font-size:24px;line-height:1">⚠</div>
    <div style="flex:1;line-height:1.5">
      <div style="font-weight:700;color:#eab308;letter-spacing:.05em;text-transform:uppercase;font-size:11px;margin-bottom:6px">SYSTEM DEMOTED THIS SIGNAL — DO NOT QUICK-BUY</div>
      <div><b>${demoteReason}.</b> The setup is real (${T.setup_family || 'setup'}, score ${score}, RS ${rsRank}), but at <b>$${pX.toFixed(2)}</b> the trade math is broken. Real R:R right now is <b style="font-family:var(--mono);color:#eab308">${realRR != null ? realRR.toFixed(2) : '—'}:1</b> (target ≥ 3:1). Cached R:R of ${cachedRR.toFixed(1)} is the *entry-zone* math, not what you'd actually get clicking buy now.</div>
      ${pullbackZone ? `<div style="margin-top:6px"><b>Action:</b> set price alert at <span style="font-family:var(--mono);color:#fde68a">${pullbackZone}</span> and wait. If it runs to <span style="font-family:var(--mono)">$${t1.toFixed(2)}</span> without pulling back — missed it, move on.</div>` : ''}
    </div>
  </div>` : '';

  body.innerHTML = `
  ${demoteBanner}
  <!-- ROW 1 — Verdict + Score · Price + Δ · Trade Plan strip · Mini chart -->
  <div class="elite-ov">
    <div class="elite-ov-tile">
      <div class="elite-ov-h">VERDICT <span class="badge" style="border-color:${vColor};color:${vColor}">${tier}</span></div>
      <div class="ov-verdict">
        ${arc}
        <div>
          <div class="ov-verdict-label ${v}" style="${isDemoted ? 'color:var(--warn)' : ''}">${isDemoted ? 'WAIT' : (v === 'SELL' ? 'SHORT' : v)}</div>
          <div class="ov-sub">${isDemoted ? demoteReason : (setupTxt.slice(0,28) || '—')}</div>
        </div>
      </div>
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">PRICE <span class="badge">LIVE</span></div>
      <div class="ov-big">$${pX.toFixed(2)}</div>
      <div class="ov-sub ${upDn}">${c >= 0 ? '+' : ''}${c.toFixed(2)}% today</div>
      <div class="ov-mini4" style="margin-top:auto">
        <div><div class="l">52W H</div><div class="v">${T.week52_high ? '$' + (+T.week52_high).toFixed(2) : '—'}</div></div>
        <div><div class="l">52W L</div><div class="v">${T.week52_low ? '$' + (+T.week52_low).toFixed(2) : '—'}</div></div>
      </div>
    </div>

    <div class="elite-ov-tile span-2">
      <div class="elite-ov-h">TRADE PLAN <span class="badge" style="${isDemoted ? 'border-color:var(--warn);color:var(--warn)' : ''}">${rrLabel}</span></div>
      <div class="ov-plan-strip">
        <div><span class="l">ENTRY</span><span class="v">$${eLo.toFixed(2)}–$${eHi.toFixed(2)}</span><span class="s">zone</span></div>
        <div><span class="l">STOP</span><span class="v" style="color:var(--fail)">$${stop.toFixed(2)}</span><span class="s dn">${stopPct.toFixed(1)}%</span></div>
        <div><span class="l">T1</span><span class="v" style="color:var(--pass)">$${t1.toFixed(2)}</span><span class="s up">+${t1Pct.toFixed(1)}%</span></div>
        <div><span class="l">T2</span><span class="v" style="color:var(--pass)">${t2 ? '$' + t2.toFixed(2) : '—'}</span><span class="s up">${t2 ? '+' + t2Pct.toFixed(1) + '%' : ''}</span></div>
      </div>
    </div>
  </div>

  <!-- ROW 2 — Technicals cluster · Score breakdown · Catalyst & Setup · Chart -->
  <div class="elite-ov">
    <div class="elite-ov-tile">
      <div class="elite-ov-h">TECHNICALS</div>
      <div class="ov-mini4">
        <div><div class="l">RSI</div><div class="v ${rsi > 70 ? 'warn' : rsi < 30 ? 'warn' : ''}">${rsi.toFixed(0) || '—'}</div></div>
        <div><div class="l">RVOL</div><div class="v ${rvol >= 1.5 ? 'up' : ''}">${rvol ? rvol.toFixed(2)+'×' : '—'}</div></div>
        <div><div class="l">ADX</div><div class="v ${adx >= 25 ? 'up' : ''}">${adx ? adx.toFixed(0) : '—'}</div></div>
        <div><div class="l">ATR</div><div class="v">${atrPct ? atrPct.toFixed(1) + '%' : '—'}</div></div>
      </div>
      <div class="ov-mini4" style="margin-top:6px">
        <div><div class="l">EMA50</div><div class="v ${above50 ? 'up' : 'dn'}">${above50 ? '↑' : '↓'}</div></div>
        <div><div class="l">SMA200</div><div class="v ${above200 ? 'up' : 'dn'}">${above200 ? '↑' : '↓'}</div></div>
        <div><div class="l">MACD</div><div class="v ${macdBull ? 'up' : 'dn'}">${macdBull ? '↑' : '↓'}</div></div>
        <div><div class="l">SQUEEZE</div><div class="v ${sqz ? 'warn' : ''}">${sqz ? 'ON' : 'off'}</div></div>
      </div>
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">SCORE BREAKDOWN</div>
      ${pillarsHtml}
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">CATALYSTS <span class="badge">T${T.catalyst_tier || '?'}</span></div>
      <div class="ov-tags">
        ${catTags.length ? catTags.map(t => `<span class="ov-tag">${t}</span>`).join('') : '<span class="ov-sub">No catalysts tagged</span>'}
      </div>
      <div class="ov-stat-grid" style="margin-top:auto">
        <div><span class="l">Setup</span><span class="v">${setupTxt.slice(0,18) || '—'}</span></div>
        <div><span class="l">RS rank</span><span class="v ${rsRank > 80 ? 'up' : rsRank < 30 ? 'dn' : ''}">${rsRank}/100</span></div>
      </div>
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">PRICE · 60D <span class="badge">stop · T1 · T2</span></div>
      ${chartSvg}
    </div>
  </div>

  <!-- ROW 3 — Fundamentals · Smart Money · Sentiment + Earnings -->
  <div class="elite-ov">
    <div class="elite-ov-tile">
      <div class="elite-ov-h">FUNDAMENTALS</div>
      <!-- 2026-05-10: pull from T.fund_details / T.fund_real / T.eodhd_fund_extras
           FIRST so Overview matches the Fundamentals tab's numbers exactly.
           Falls back to flat T.* fields only when objects missing. -->
      <div class="ov-mini4">
        <div><div class="l">MCAP</div><div class="v">${fmtMcap(fr.market_cap ?? fd.market_cap ?? T.market_cap)}</div></div>
        <div><div class="l">BETA</div><div class="v">${(fr.beta ?? fd.beta ?? T.beta) != null ? (+(fr.beta ?? fd.beta ?? T.beta)).toFixed(2) : '—'}</div></div>
        <div><div class="l">FWD P/E</div><div class="v">${(fr.fwd_pe ?? fx.forward_pe ?? T.fwd_pe) != null ? (+(fr.fwd_pe ?? fx.forward_pe ?? T.fwd_pe)).toFixed(1) : '—'}</div></div>
        <div><div class="l">PEG</div><div class="v">${(fr.peg ?? fx.peg ?? T.peg) != null ? (+(fr.peg ?? fx.peg ?? T.peg)).toFixed(2) : '—'}</div></div>
      </div>
      <div class="ov-mini4" style="margin-top:6px">
        <div><div class="l">REV GR</div><div class="v ${((fr.rev_growth ?? fd.rev_growth ?? T.rev_growth) || 0) > 10 ? 'up' : ((fr.rev_growth ?? fd.rev_growth ?? T.rev_growth) || 0) < 0 ? 'dn' : ''}">${(fr.rev_growth ?? fd.rev_growth ?? T.rev_growth) != null ? (+(fr.rev_growth ?? fd.rev_growth ?? T.rev_growth)).toFixed(1)+'%' : '—'}</div></div>
        <div><div class="l">NET MGN</div><div class="v">${(fr.net_margin ?? fd.net_margin ?? T.net_margin) != null ? (+(fr.net_margin ?? fd.net_margin ?? T.net_margin)).toFixed(1)+'%' : '—'}</div></div>
        <div><div class="l">ROE</div><div class="v">${(fr.roe ?? fd.roe ?? T.roe) != null ? (+(fr.roe ?? fd.roe ?? T.roe)).toFixed(1)+'%' : '—'}</div></div>
        <div><div class="l">DEBT/E</div><div class="v">${(fr.debt_to_equity ?? fd.debt_to_equity ?? T.debt_to_equity) != null ? (+(fr.debt_to_equity ?? fd.debt_to_equity ?? T.debt_to_equity)).toFixed(1) : '—'}</div></div>
      </div>
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">SMART MONEY</div>
      <!-- 2026-05-10: insider counts from T.insider_full first (matches Insider tab);
           options metrics from T.options_iv (matches Options tab). -->
      <div class="ov-mini4">
        <div><div class="l">INSIDER ↑</div><div class="v ${(ins.buys_30d ?? ins.buys ?? T.insider_buys ?? 0) > 0 ? 'up' : ''}">${ins.buys_30d ?? ins.buys ?? T.insider_buys ?? 0}</div></div>
        <div><div class="l">INSIDER ↓</div><div class="v ${(ins.sells_30d ?? ins.sells ?? T.insider_sells ?? 0) > 0 ? 'dn' : ''}">${ins.sells_30d ?? ins.sells ?? T.insider_sells ?? 0}</div></div>
        <div><div class="l">SHORT %</div><div class="v ${(fr.short_pct ?? T.short_pct ?? 0) > 20 ? 'warn' : ''}">${(fr.short_pct ?? T.short_pct) != null ? (+(fr.short_pct ?? T.short_pct)).toFixed(1)+'%' : '—'}</div></div>
        <div><div class="l">INST OWN</div><div class="v">${(fr.inst_own_pct ?? T.inst_own_pct) != null ? (+(fr.inst_own_pct ?? T.inst_own_pct)).toFixed(0)+'%' : '—'}</div></div>
      </div>
      <div class="ov-mini4" style="margin-top:6px">
        <div><div class="l">FLOAT</div><div class="v">${(fr.float_shares ?? T.float_shares) ? fmtMcap(fr.float_shares ?? T.float_shares).replace('$','') : '—'}</div></div>
        <div><div class="l">UOA</div><div class="v ${(oiv.uoa_calls ?? T.uoa_score ?? 0) > 0 ? 'up' : ''}">${oiv.uoa_calls ?? T.uoa_score ?? '—'}</div></div>
        <div><div class="l">IV RANK</div><div class="v">${(oiv.iv_rank ?? T.iv_rank) != null ? (+(oiv.iv_rank ?? T.iv_rank)).toFixed(0) : '—'}</div></div>
        <div><div class="l">P/C</div><div class="v">${(oiv.put_call_ratio ?? T.put_call_ratio) != null ? (+(oiv.put_call_ratio ?? T.put_call_ratio)).toFixed(2) : '—'}</div></div>
      </div>
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">SENTIMENT</div>
      <!-- 2026-05-10: news bias from T.news_sentiment_score / T.eodhd_sentiment
           (matches Sentiment + News tabs); analyst from T.analyst_full. -->
      ${(() => {
        // Resolve news bias: prefer aggregate score from T.news_sentiment_score,
        // then EODHD aggregate, then legacy T.news. Same precedence as Sentiment tab.
        const newsAvg = newsScore.avg_sentiment != null ? +newsScore.avg_sentiment :
                        eodhdSent.avg != null ? +eodhdSent.avg :
                        +(T.news || 0);
        const newsBias = newsAvg > 0.05 ? 'Bullish' : newsAvg < -0.05 ? 'Bearish' : 'Neutral';
        const newsClass = newsAvg > 0.05 ? 'up' : newsAvg < -0.05 ? 'dn' : '';
        const newsCount = newsArts.length || newsScore.n_articles || '—';
        const consensus = ana.consensus || ana.recommendation || T.analyst_consensus || '—';
        const ptMean    = ana.target_mean ?? ana.targetMeanPrice ?? T.analyst_target;
        const upside    = ana.upside_pct ?? T.analyst_upside;
        return `
        <div class="ov-stat-grid">
          <div><span class="l">News</span><span class="v ${newsClass}">${newsBias}${newsCount !== '—' ? ` <span style="opacity:.6;font-size:10px">(${newsCount})</span>` : ''}</span></div>
          <div><span class="l">Analyst</span><span class="v ${(consensus||'').toLowerCase().includes('buy') ? 'up' : (consensus||'').toLowerCase().includes('sell') ? 'dn' : ''}">${consensus !== '—' ? consensus : '—'}</span></div>
          <div><span class="l">PT mean</span><span class="v">${ptMean ? '$' + (+ptMean).toFixed(2) : '—'}</span></div>
          <div><span class="l">Upside</span><span class="v ${(upside||0) > 0 ? 'up' : 'dn'}">${upside != null ? (+upside).toFixed(0)+'%' : '—'}</span></div>
        </div>`;
      })()}
    </div>

    <div class="elite-ov-tile">
      <div class="elite-ov-h">EARNINGS / RISK</div>
      <div class="ov-stat-grid">
        <div><span class="l">Days</span><span class="v ${T.earn_days != null && T.earn_days <= 7 ? 'dn' : ''}">${T.earn_days != null ? T.earn_days + 'd' : 'no earn'}</span></div>
        <div><span class="l">Beat rate</span><span class="v">${T.earnings_beat != null ? (+T.earnings_beat * 100).toFixed(0) + '%' : '—'}</span></div>
        <div><span class="l">Hold</span><span class="v">${T.hold_period_min != null && T.hold_period_max != null ? T.hold_period_min + '-' + T.hold_period_max + 'd' : '—'}</span></div>
        <div><span class="l">Alloc</span><span class="v">${T.alloc_pct ? (+T.alloc_pct).toFixed(0) + '%' : '—'}</span></div>
      </div>
    </div>
  </div>

  <!-- ROW 4 — Forward Risk: V-1 Monte Carlo · V-3 Forward Dist · V-2 HMM · V-11 CVaR -->
  ${(() => {
    const mc = T.monte_carlo || {};
    const fd = T.forward_dist || {};
    const ga = (typeof DATA !== 'undefined' && DATA) ? DATA : {};
    const hmm = ga.hmm_regime || (window.GLOBAL_REGIME && window.GLOBAL_REGIME.hmm_regime) || {};
    // Look up this ticker in CVaR optimizer holdings
    const cvar = ga.cvar_portfolio || {};
    const myWeight = (cvar.holdings || []).find(h => h.ticker === T.ticker);
    // Tail-loss filter demotion (set by analysis.py when score<60 OR stars<4)
    const conv = T.conviction || {};
    const tlf  = conv.tail_filter_demoted;

    // Format helpers
    const colorR = (v, good, bad) => v == null ? '' : v >= good ? 'up' : v <= bad ? 'dn' : 'warn';
    const sgn = v => (v == null) ? '—' : (v >= 0 ? '+' : '') + v + '%';

    const mcMissing = mc.error || !mc.stats;
    const fdMissing = fd.error;
    const hmmMissing = hmm.error || hmm.regime == null;

    return `
    <div class="elite-ov">
      <!-- V-1 Monte Carlo -->
      <div class="elite-ov-tile">
        <div class="elite-ov-h">MONTE CARLO <span class="badge">V-1 · ${mc.n_paths || '3K'} paths · ${mc.T || 63}d</span></div>
        ${mcMissing ? `<div class="ov-sub" style="padding:8px 0">${mc.error || 'simulation pending'}</div>` : `
        <div class="ov-mini4">
          <div><div class="l">P50</div><div class="v ${colorR(mc.stats?.p50_pct, 0, -10)}">${sgn(mc.stats?.p50_pct)}</div></div>
          <div><div class="l">P25</div><div class="v ${colorR(mc.stats?.p25_pct, 0, -10)}">${sgn(mc.stats?.p25_pct)}</div></div>
          <div><div class="l">P75</div><div class="v ${colorR(mc.stats?.p75_pct, 10, 0)}">${sgn(mc.stats?.p75_pct)}</div></div>
          <div><div class="l">P(profit)</div><div class="v ${colorR(mc.p_profit, 60, 45)}">${mc.p_profit != null ? mc.p_profit + '%' : '—'}</div></div>
        </div>
        ${mc.p_hit_target_first != null ? `
        <div class="ov-mini4" style="margin-top:6px">
          <div><div class="l">P(T1 1st)</div><div class="v up">${mc.p_hit_target_first}%</div></div>
          <div><div class="l">P(stop 1st)</div><div class="v dn">${mc.p_hit_stop_first}%</div></div>
          <div><div class="l">λ jumps</div><div class="v">${(mc.lambda_jump || 0).toFixed(1)}/y</div></div>
          <div><div class="l">Sharpe</div><div class="v ${colorR(mc.fwd_sharpe, 1, 0)}">${mc.fwd_sharpe ?? '—'}</div></div>
        </div>` : ''}`}
      </div>

      <!-- V-3 Forward Distribution -->
      <div class="elite-ov-tile">
        <div class="elite-ov-h">FORWARD DIST <span class="badge">V-3 · ${fd.horizon_days || 10}d empirical</span></div>
        ${fdMissing ? `<div class="ov-sub" style="padding:8px 0">${fd.error || 'no history'}</div>` : `
        <div class="ov-mini4">
          <div><div class="l">VaR-95</div><div class="v ${colorR(fd.var_95_pct, -3, -8)}">${sgn(fd.var_95_pct)}</div></div>
          <div><div class="l">CVaR-97</div><div class="v ${colorR(fd.cvar_975_pct, -5, -12)}">${sgn(fd.cvar_975_pct)}</div></div>
          <div><div class="l">P(profit)</div><div class="v ${colorR(fd.p_profit, 60, 45)}">${fd.p_profit != null ? fd.p_profit + '%' : '—'}</div></div>
          <div><div class="l">N samples</div><div class="v">${fd.n_samples || '—'}</div></div>
        </div>
        <div class="ov-mini4" style="margin-top:6px">
          <div><div class="l">Mean</div><div class="v ${colorR(fd.mean_pct, 0, -2)}">${sgn(fd.mean_pct)}</div></div>
          <div><div class="l">Std</div><div class="v">${fd.std_pct != null ? fd.std_pct + '%' : '—'}</div></div>
          <div><div class="l">Sharpe</div><div class="v ${colorR(fd.fwd_sharpe, 1, 0)}">${fd.fwd_sharpe ?? '—'}</div></div>
          <div><div class="l">P50</div><div class="v">${sgn(fd.p50_pct)}</div></div>
        </div>`}
      </div>

      <!-- V-2 HMM Regime + Tail-Loss Filter -->
      <div class="elite-ov-tile">
        <div class="elite-ov-h">REGIME <span class="badge">V-2 HMM · 21d window</span></div>
        ${hmmMissing ? `<div class="ov-sub" style="padding:8px 0">${hmm.error || 'regime unknown'}</div>` : `
        <div class="ov-stat-grid">
          <div><span class="l">P(Bull)</span><span class="v up">${((hmm.p_bull || 0) * 100).toFixed(1)}%</span></div>
          <div><span class="l">P(Neutral)</span><span class="v warn">${((hmm.p_neutral || 0) * 100).toFixed(1)}%</span></div>
          <div><span class="l">P(Bear)</span><span class="v dn">${((hmm.p_bear || 0) * 100).toFixed(1)}%</span></div>
          <div><span class="l">Confidence</span><span class="v">${((hmm.confidence || 0) * 100).toFixed(0)}%</span></div>
        </div>
        <div class="ov-stat-grid" style="margin-top:6px;border-top:1px dashed var(--rule);padding-top:8px">
          <div><span class="l">Tail filter</span><span class="v ${tlf ? 'dn' : 'up'}">${tlf ? '✗ DEMOTED' : '✓ CLEARED'}</span></div>
          <div><span class="l">Was tier</span><span class="v">${tlf ? (conv.demoted_from_tier || '—') : (conv.label || '—')}</span></div>
          <div><span class="l">Stars</span><span class="v">${T.star_rating || '—'}/5</span></div>
          <div><span class="l">Score band</span><span class="v">${(T.score || 0) >= 90 ? '90-100' : (T.score || 0) >= 80 ? '80-89' : (T.score || 0) >= 70 ? '70-79' : (T.score || 0) >= 60 ? '60-69' : '<60'}</span></div>
        </div>`}
      </div>

      <!-- V-11 CVaR Portfolio Allocation -->
      <div class="elite-ov-tile">
        <div class="elite-ov-h">CVAR PORTFOLIO <span class="badge">V-11 · LP optimal</span></div>
        <div class="ov-stat-grid">
          <div><span class="l">Optimal weight</span><span class="v ${myWeight ? 'up' : ''}">${myWeight ? myWeight.weight_pct + '%' : 'not held'}</span></div>
          <div><span class="l">Port E[R]</span><span class="v ${cvar.expected_return_pct >= 0 ? 'up' : 'dn'}">${cvar.expected_return_pct != null ? sgn(cvar.expected_return_pct) : '—'}</span></div>
          <div><span class="l">Port CVaR</span><span class="v dn">${cvar.cvar_pct != null ? sgn(cvar.cvar_pct) : '—'}</span></div>
          <div><span class="l">Port positions</span><span class="v">${cvar.n_positions != null ? cvar.n_positions : '—'}</span></div>
        </div>
        <div class="ov-stat-grid" style="margin-top:6px;border-top:1px dashed var(--rule);padding-top:8px">
          <div><span class="l">Drawdown mult</span><span class="v">${T.kelly_size?.drawdown_mult != null ? (+T.kelly_size.drawdown_mult).toFixed(2) + '×' : '—'}</span></div>
          <div><span class="l">Earnings mult</span><span class="v ${T.kelly_size?.earnings_mult < 1 ? 'warn' : ''}">${T.kelly_size?.earnings_mult != null ? (+T.kelly_size.earnings_mult).toFixed(2) + '×' : '—'}</span></div>
          <div><span class="l">VaR floor</span><span class="v ${T.kelly_size?.var_floor_mult < 1 ? 'warn' : ''}">${T.kelly_size?.var_floor_mult != null ? (+T.kelly_size.var_floor_mult).toFixed(2) + '×' : '—'}</span></div>
          <div><span class="l">Final alloc</span><span class="v">${T.kelly_size?.final_alloc_pct != null ? (+T.kelly_size.final_alloc_pct).toFixed(1) + '%' : '—'}</span></div>
        </div>
      </div>
    </div>`;
  })()}

  <!-- THESIS at bottom (full sentence) — guard against object (thesis_card) -->
  ${(typeof T.thesis === 'string' && T.thesis) ? `<div class="ex-thesis"><span class="ex-thesis-l">THESIS</span> ${T.thesis}</div>` : (T.thesis_card && T.thesis_card.narrative ? `<div class="ex-thesis"><span class="ex-thesis-l">THESIS</span> ${T.thesis_card.narrative}</div>` : '')}
  `;
}

export function dispose() { /* no-op */ }
