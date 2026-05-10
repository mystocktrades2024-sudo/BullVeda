// subtabs/fundamentals/fundamentals.js — extracted from elite-detail.html (renderFund 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const fd  = T.fund_details || {};
  const fr  = T.fund_real || {};
  const ana = T.analyst_full || T.analyst || {};
  const ins = T.insider_full || T.insider || {};
  const zg  = T.zacks_grades || {};
  const fx  = T.eodhd_fund_extras || {};
  const ltb = T.long_term_breakdown || {};
  const realBull = fr.bull_drivers || [];
  const realBear = fr.bear_risks || [];
  const px = +(T.price || 0);
  const mcap = +(T.market_cap || 0);
  const ltScore = +(T.long_term_score || 0);
  const fundTotal = T.fund_total || { score: 0, max: 30 };

  // ── Verdict tone ──
  let tone, hLabel, hEm, narrative;
  if (ltScore >= 80) {
    tone = 'high'; hLabel = 'Fundamental quality is'; hEm = 'STRONG';
  } else if (ltScore >= 60) {
    tone = 'mid'; hLabel = 'Fundamental quality is'; hEm = 'MIDDLING';
  } else {
    tone = 'low'; hLabel = 'Fundamental quality is'; hEm = 'WEAK';
  }
  // Narrative based on actual numbers
  const narrParts = [];
  if (fr.rev_growth_pct != null) {
    if (fr.rev_growth_pct >= 15) narrParts.push(`Revenue +${fr.rev_growth_pct.toFixed(1)}% YoY (strong growth)`);
    else if (fr.rev_growth_pct >= 5) narrParts.push(`Revenue +${fr.rev_growth_pct.toFixed(1)}% YoY (modest growth)`);
    else if (fr.rev_growth_pct >= 0) narrParts.push(`Revenue ${fr.rev_growth_pct.toFixed(1)}% YoY (flat)`);
    else narrParts.push(`Revenue ${fr.rev_growth_pct.toFixed(1)}% YoY (declining)`);
  }
  if (fr.net_margin_pct != null) {
    if (fr.net_margin_pct >= 20) narrParts.push(`net margin ${fr.net_margin_pct.toFixed(1)}% (premium)`);
    else if (fr.net_margin_pct >= 10) narrParts.push(`net margin ${fr.net_margin_pct.toFixed(1)}% (healthy)`);
    else if (fr.net_margin_pct >= 5) narrParts.push(`net margin ${fr.net_margin_pct.toFixed(1)}% (thin)`);
    else narrParts.push(`net margin ${fr.net_margin_pct.toFixed(1)}% (low)`);
  }
  if (fr.roe_pct != null) narrParts.push(`ROE ${fr.roe_pct.toFixed(1)}%`);
  if (fr.peg != null) {
    if (fr.peg < 1) narrParts.push(`PEG ${fr.peg.toFixed(2)} (cheap on growth)`);
    else if (fr.peg < 2) narrParts.push(`PEG ${fr.peg.toFixed(2)} (fair)`);
    else narrParts.push(`PEG ${fr.peg.toFixed(2)} (rich)`);
  }
  narrative = narrParts.join(' · ') + '.';
  if (zg.vgm) narrative += ` Zacks composite VGM grade ${zg.vgm}.`;
  if (ltb.gate_fails && ltb.gate_fails.length) narrative += ` Quality gate fails: ${ltb.gate_fails.join(', ')}.`;

  // Letter grade equivalent for the long-term score
  const letterGrade = ltScore >= 90 ? 'A' : ltScore >= 80 ? 'A−' : ltScore >= 70 ? 'B' : ltScore >= 60 ? 'C' : ltScore >= 50 ? 'D' : 'F';

  // ── 6-pillar gauge breakdown ──
  const parsePillar = (str) => {
    const m = (str || '').match(/\((\d+)\/(\d+)\)/);
    if (!m) return null;
    return { score: +m[1], max: +m[2] };
  };
  const pillars = [
    { name: 'Revenue Growth', detail: fd.revenue_growth, ctx: fr.rev_growth_pct != null ? `${fr.rev_growth_pct.toFixed(1)}% YoY · TTM rev $${fx.revenue_ttm ? (fx.revenue_ttm/1e9).toFixed(1)+'B' : '—'}` : '' },
    { name: 'Profit Margin', detail: fd.profit_margin, ctx: fr.net_margin_pct != null ? `gross ${fr.gross_margin_pct?.toFixed(1)||'—'}% · op ${fr.op_margin_pct?.toFixed(1)||'—'}% · net ${fr.net_margin_pct.toFixed(1)}%` : '' },
    { name: 'Balance Sheet', detail: fd.balance_sheet, ctx: fr.roe_pct != null ? `ROE ${fr.roe_pct.toFixed(1)}% · ROA ${fr.roa_pct?.toFixed(1)||'—'}%` : '' },
    { name: 'Valuation', detail: fd.valuation, ctx: fr.peg != null ? `PEG ${fr.peg.toFixed(2)}${fd.price_to_book ? ' · P/B '+fd.price_to_book : ''}` : '' },
    { name: 'Analyst Revisions', detail: fd.analyst_revisions, ctx: ana.upgrades_10d != null ? `${ana.upgrades_10d}↑ ${ana.downgrades_10d || 0}↓ in last 10d` : '' },
  ];

  // ── Cash flow story ──
  const ocf = fx.operating_cash_flow_ttm;
  const capex = fx.capex_ttm;
  const fcf = fx.free_cash_flow_ttm;
  const div = fx.dividends_paid_ttm;
  const fcfMargin = (fcf != null && fx.revenue_ttm) ? (fcf / fx.revenue_ttm * 100) : null;
  const fcfYield = (fcf != null && mcap > 0) ? (fcf / mcap * 100) : null;
  const divCoverage = (fcf != null && div != null && div > 0) ? (fcf / div) : null;

  // ── Bull / Bear ──
  const bull = [];
  realBull.forEach(d => bull.push([d, '']));
  if (zg.vgm === 'A' || zg.vgm === 'B') bull.push([`Zacks VGM ${zg.vgm}`, 'Composite Value+Growth+Momentum strong']);
  if (T.zacks_rank1) bull.push([`Zacks Rank #1`, 'Strong Buy on Zacks 1-5 scale']);
  if ((ana.upgrades_10d || 0) > (ana.downgrades_10d || 0) && ana.upgrades_10d) bull.push([`${ana.upgrades_10d} analyst upgrade${ana.upgrades_10d>1?'s':''}`, `vs ${ana.downgrades_10d || 0} downgrades in last 10d`]);
  if (fcfYield != null && fcfYield > 5) bull.push([`FCF yield ${fcfYield.toFixed(1)}%`, 'Above-average cash returns relative to market cap']);
  if (fr.peg != null && fr.peg < 1) bull.push([`PEG ${fr.peg.toFixed(2)}`, 'Trading cheap relative to growth rate']);
  if (fr.gross_margin_pct >= 50) bull.push([`Gross margin ${fr.gross_margin_pct.toFixed(0)}%`, 'High pricing power / capital-light economics']);
  if (fr.roe_pct >= 20) bull.push([`ROE ${fr.roe_pct.toFixed(0)}%`, 'Above-market return on equity']);

  const bear = [];
  realBear.forEach(d => bear.push([d, '']));
  if (zg.vgm === 'D' || zg.vgm === 'F') bear.push([`Zacks VGM ${zg.vgm}`, 'Composite weakness across V/G/M']);
  if (zg.growth === 'F') bear.push([`Growth grade F`, 'Bottom-quintile growth metrics']);
  if (zg.value === 'F') bear.push([`Value grade F`, 'Trading expensive on traditional value metrics']);
  if ((ana.downgrades_10d || 0) > (ana.upgrades_10d || 0) && ana.downgrades_10d) bear.push([`${ana.downgrades_10d} analyst downgrade${ana.downgrades_10d>1?'s':''}`, `vs ${ana.upgrades_10d || 0} upgrades in last 10d`]);
  if (fr.rev_growth_pct != null && fr.rev_growth_pct < 0) bear.push([`Revenue declining`, `${fr.rev_growth_pct.toFixed(1)}% YoY — top-line shrinking`]);
  if (fr.net_margin_pct != null && fr.net_margin_pct < 5) bear.push([`Thin net margin`, `${fr.net_margin_pct.toFixed(1)}% — operating leverage limited`]);
  if (ltb.gate_fails && ltb.gate_fails.length) bear.push([`Quality gate: ${ltb.gate_fails.join(', ')} fail`, 'Long-term scoring blocked at gate']);
  const upPct = ana.upside_pct;
  if (upPct != null && upPct < -2) bear.push([`Below analyst PT`, `${upPct.toFixed(1)}% downside to consensus $${ana.target_mean?.toFixed(2) || '—'}`]);

  // ── Build ──
  const fmtMoney = v => v == null ? '—' : v >= 1e9 ? '$' + (v/1e9).toFixed(2) + 'B' : v >= 1e6 ? '$' + (v/1e6).toFixed(0) + 'M' : '$' + v.toLocaleString();
  const consUp = ana.upside_pct;
  const ptCls = consUp != null ? (consUp >= 10 ? 'pass' : consUp >= 0 ? 'warn' : 'fail') : 'warn';

  $('fundBody').innerHTML = `
    <!-- VERDICT BANNER -->
    <div class="fnd-verdict ${tone}">
      <div class="fnd-v-grade">${letterGrade}</div>
      <div class="fnd-v-mid">
        <div class="tag">FUNDAMENTAL QUALITY · ${hEm}</div>
        <div class="h">${hLabel} <span class="em">${hEm}</span></div>
        <div class="narr">${narrative}</div>
      </div>
      <div class="fnd-v-r">
        <div class="fnd-v-score">${ltScore.toFixed(0)}<span style="font-size:14px;color:var(--ink-1);font-weight:600">/100</span></div>
        <div class="fnd-v-score-lbl">Long-Term Score</div>
      </div>
    </div>

    <!-- ZACKS VGM STRIP -->
    ${zg.growth || zg.value || zg.momentum || zg.vgm ? `
    <div class="fnd-grade-strip">
      <span class="l">Zacks VGM</span>
      ${zg.growth ? `<span class="fnd-grade-pill ${zg.growth}"><span class="lbl">Growth</span><span class="grade">${zg.growth}</span></span>` : ''}
      ${zg.value ? `<span class="fnd-grade-pill ${zg.value}"><span class="lbl">Value</span><span class="grade">${zg.value}</span></span>` : ''}
      ${zg.momentum ? `<span class="fnd-grade-pill ${zg.momentum}"><span class="lbl">Momentum</span><span class="grade">${zg.momentum}</span></span>` : ''}
      ${zg.vgm ? `<span class="fnd-grade-pill ${zg.vgm}"><span class="lbl">Composite</span><span class="grade">${zg.vgm}</span></span>` : ''}
      ${zg.verdict ? `<span class="verdict">Verdict<b>${zg.verdict}</b></span>` : ''}
      ${T.zacks_rank1 ? `<span class="fnd-grade-pill A" style="margin-left:8px"><span class="lbl">⭐ Zacks Rank</span><span class="grade">#1</span></span>` : ''}
    </div>` : ''}

    <!-- 6-PILLAR GAUGE BREAKDOWN -->
    <div class="fnd-pillars">
      <div class="fnd-pillars-h">📊 QUALITY PILLARS<span class="meta">${fundTotal.score}/${fundTotal.max} composite pts</span></div>
      ${pillars.map(p => {
        const sc = parsePillar(p.detail);
        if (!sc) return '';
        const pct = (sc.score / sc.max) * 100;
        const cls = sc.score >= 4 ? 'pass' : sc.score >= 3 ? 'info' : sc.score >= 2 ? 'warn' : 'fail';
        return `<div class="fnd-pillar-row">
          <div class="name">${p.name}</div>
          <div class="gauge"><div class="gauge-fill ${cls}" style="width:${pct.toFixed(0)}%"></div></div>
          <div class="pts">${sc.score}/${sc.max}</div>
          ${p.ctx ? `<div class="ctx">${p.ctx}</div>` : ''}
        </div>`;
      }).join('')}
    </div>

    <!-- 3-PANEL: GROWTH · PROFITABILITY · BALANCE -->
    <div class="fnd-grid">
      <div class="fnd-card">
        <div class="fnd-card-h"><span class="ico">📈</span>GROWTH<span class="badge ${fr.rev_growth_pct >= 15 ? 'pass' : fr.rev_growth_pct >= 5 ? 'info' : fr.rev_growth_pct >= 0 ? 'warn' : 'fail'}">${fr.rev_growth_pct != null ? (fr.rev_growth_pct >= 0 ? '+' : '') + fr.rev_growth_pct.toFixed(1) + '%' : '—'}</span></div>
        <div class="fnd-bigstat"><span class="v ${fr.rev_growth_pct >= 15 ? 'pass' : fr.rev_growth_pct >= 0 ? '' : 'fail'}">${fr.rev_growth_pct != null ? (fr.rev_growth_pct >= 0 ? '+' : '') + fr.rev_growth_pct.toFixed(1) + '%' : '—'}</span><span class="u">YoY revenue</span></div>
        <div class="fnd-row"><span class="l">Revenue (TTM)</span><span class="r">${fmtMoney(fx.revenue_ttm)}</span></div>
        <div class="fnd-row"><span class="l">Trend</span><span class="r ${fr.rev_growth_pct < 0 ? 'fail' : fr.rev_growth_pct >= 15 ? 'pass' : ''}">${fr.rev_growth_pct < 0 ? 'Declining' : fr.rev_growth_pct >= 15 ? 'Strong' : fr.rev_growth_pct >= 5 ? 'Modest' : 'Flat'}</span></div>
        <div class="fnd-row"><span class="l">Shares out</span><span class="r">${fx.shares_outstanding ? (fx.shares_outstanding/1e6).toFixed(0) + 'M' : '—'}</span></div>
      </div>
      <div class="fnd-card">
        <div class="fnd-card-h"><span class="ico">💰</span>PROFITABILITY<span class="badge ${fr.net_margin_pct >= 20 ? 'pass' : fr.net_margin_pct >= 10 ? 'info' : fr.net_margin_pct >= 5 ? 'warn' : 'fail'}">${fr.net_margin_pct != null ? fr.net_margin_pct.toFixed(1) + '%' : '—'}</span></div>
        <div class="fnd-bigstat"><span class="v ${fr.net_margin_pct >= 20 ? 'pass' : fr.net_margin_pct >= 10 ? '' : fr.net_margin_pct >= 5 ? 'warn' : 'fail'}">${fr.net_margin_pct != null ? fr.net_margin_pct.toFixed(1) + '%' : '—'}</span><span class="u">net margin</span></div>
        <div class="fnd-row"><span class="l">Gross margin</span><span class="r ${fr.gross_margin_pct >= 50 ? 'pass' : fr.gross_margin_pct >= 30 ? '' : 'warn'}">${fr.gross_margin_pct?.toFixed(1) || '—'}%</span></div>
        <div class="fnd-row"><span class="l">Operating margin</span><span class="r">${fr.op_margin_pct?.toFixed(1) || '—'}%</span></div>
        <div class="fnd-row"><span class="l">Net margin</span><span class="r">${fr.net_margin_pct?.toFixed(1) || '—'}%</span></div>
      </div>
      <div class="fnd-card">
        <div class="fnd-card-h"><span class="ico">⚖</span>BALANCE / RETURNS<span class="badge ${fr.roe_pct >= 20 ? 'pass' : fr.roe_pct >= 10 ? 'info' : 'warn'}">${fr.roe_pct != null ? fr.roe_pct.toFixed(1) + '%' : '—'}</span></div>
        <div class="fnd-bigstat"><span class="v ${fr.roe_pct >= 20 ? 'pass' : fr.roe_pct >= 10 ? '' : 'warn'}">${fr.roe_pct != null ? fr.roe_pct.toFixed(1) + '%' : '—'}</span><span class="u">ROE</span></div>
        <div class="fnd-row"><span class="l">Return on Assets</span><span class="r">${fr.roa_pct?.toFixed(1) || '—'}%</span></div>
        <div class="fnd-row"><span class="l">Debt / Equity</span><span class="r ${ltb.debt_equity != null && ltb.debt_equity > 1 ? 'fail' : ltb.debt_equity != null && ltb.debt_equity > 0.5 ? 'warn' : ltb.debt_equity != null ? 'pass' : ''}">${ltb.debt_equity != null ? ltb.debt_equity.toFixed(2) : '—'}</span></div>
        <div class="fnd-row"><span class="l">Market cap</span><span class="r">${fmtMoney(mcap)}</span></div>
      </div>
    </div>

    <!-- CASH FLOW STORY -->
    ${(ocf != null || fcf != null) ? `
    <div class="fnd-card" style="margin-bottom:14px">
      <div class="fnd-card-h"><span class="ico">💵</span>CASH FLOW STORY (TTM)<span class="badge ${fcfYield != null && fcfYield >= 5 ? 'pass' : fcfYield != null && fcfYield >= 2 ? 'info' : 'warn'}">${fcfYield != null ? 'FCF yield ' + fcfYield.toFixed(1) + '%' : 'no yield data'}</span></div>
      <div class="fnd-cf-bar">
        <div class="fnd-cf-flow">
          <div class="fnd-cf-step"><div class="lbl">Operating CF</div><div class="val">${fmtMoney(ocf)}</div></div>
          <div class="fnd-cf-arrow">−</div>
          <div class="fnd-cf-step capex"><div class="lbl">CapEx</div><div class="val">${capex != null ? fmtMoney(capex) : '—'}</div></div>
          <div class="fnd-cf-arrow">=</div>
          <div class="fnd-cf-step fcf"><div class="lbl">Free Cash Flow</div><div class="val">${fmtMoney(fcf)}</div></div>
          <div class="fnd-cf-arrow">→</div>
          <div class="fnd-cf-step"><div class="lbl">Dividends</div><div class="val">${div != null ? fmtMoney(div) : '—'}</div></div>
        </div>
      </div>
      <div class="fnd-grid-2" style="margin-top:10px;margin-bottom:0">
        <div class="fnd-row" style="border-bottom:none"><span class="l">FCF margin</span><span class="r ${fcfMargin >= 15 ? 'pass' : fcfMargin >= 8 ? '' : 'warn'}">${fcfMargin != null ? fcfMargin.toFixed(1) + '%' : '—'}</span></div>
        <div class="fnd-row" style="border-bottom:none"><span class="l">Dividend coverage</span><span class="r ${divCoverage >= 2 ? 'pass' : divCoverage >= 1.2 ? '' : 'warn'}">${divCoverage != null ? divCoverage.toFixed(1) + '×' : '—'}</span></div>
      </div>
    </div>` : ''}

    <!-- VALUATION + ANALYST CONSENSUS -->
    <div class="fnd-grid-2">
      <div class="fnd-card">
        <div class="fnd-card-h"><span class="ico">💎</span>VALUATION ANCHORS<span class="badge ${fr.peg != null && fr.peg < 1 ? 'pass' : fr.peg != null && fr.peg < 2 ? 'info' : 'warn'}">${fr.peg != null ? 'PEG ' + fr.peg.toFixed(2) : '—'}</span></div>
        <div class="fnd-row"><span class="l">PEG ratio</span><span class="r ${fr.peg < 1 ? 'pass' : fr.peg > 3 ? 'fail' : ''}">${fr.peg != null ? fr.peg.toFixed(2) : '—'}</span></div>
        <div class="fnd-row"><span class="l">Price / Book</span><span class="r">${fd.price_to_book || '—'}</span></div>
        <div class="fnd-row"><span class="l">FCF yield</span><span class="r ${fcfYield >= 5 ? 'pass' : ''}">${fcfYield != null ? fcfYield.toFixed(1) + '%' : '—'}</span></div>
        <div class="fnd-row"><span class="l">Current price</span><span class="r">$${px.toFixed(2)}</span></div>
        <div class="fnd-row"><span class="l">52-week low (floor)</span><span class="r">${T.week52_low ? '$' + T.week52_low.toFixed(2) : '—'}</span></div>
      </div>
      <div class="fnd-card">
        <div class="fnd-card-h"><span class="ico">🎯</span>ANALYST CONSENSUS<span class="badge ${ptCls}">${consUp != null ? (consUp >= 0 ? '+' : '') + consUp.toFixed(1) + '%' : (ana.consensus || '—')}</span></div>
        <div class="fnd-row"><span class="l">Price target</span><span class="r ${consUp >= 10 ? 'pass' : consUp < 0 ? 'fail' : ''}">${ana.target_mean ? '$' + ana.target_mean.toFixed(2) : '—'}</span></div>
        <div class="fnd-row"><span class="l">Consensus</span><span class="r ${(ana.consensus||'').toLowerCase().includes('buy') ? 'pass' : (ana.consensus||'').toLowerCase().includes('sell') ? 'fail' : ''}">${ana.consensus || '—'}</span></div>
        <div class="fnd-row"><span class="l">Upgrades / Downgrades (10d)</span><span class="r ${(ana.upgrades_10d||0) > (ana.downgrades_10d||0) ? 'pass' : (ana.downgrades_10d||0) > 0 ? 'fail' : ''}">${ana.upgrades_10d || 0}↑ / ${ana.downgrades_10d || 0}↓</span></div>
        <div class="fnd-row"><span class="l">Coverage</span><span class="r">${ana.total_analysts || 0} analyst${(ana.total_analysts||0)===1?'':'s'}</span></div>
      </div>
    </div>

    <!-- BULL / BEAR THESIS -->
    <div class="fnd-thesis">
      <div class="fnd-thesis-col bull">
        <div class="fnd-thesis-h"><h4>BULL DRIVERS</h4><span class="count">${bull.length} supporting</span></div>
        ${bull.length ? bull.map(([w, why]) => `<div class="fnd-thesis-item"><span class="tk">+</span><div class="body"><div class="what">${w}</div>${why ? `<div class="why">${why}</div>` : ''}</div></div>`).join('') : '<div class="fnd-thesis-item"><span class="tk" style="color:var(--ink-2)">○</span><div class="body"><div class="what" style="color:var(--ink-1);font-style:italic">No bullish drivers from fundamentals.</div></div></div>'}
      </div>
      <div class="fnd-thesis-col bear">
        <div class="fnd-thesis-h"><h4>BEAR RISKS</h4><span class="count">${bear.length} against</span></div>
        ${bear.length ? bear.map(([w, why]) => `<div class="fnd-thesis-item"><span class="tk">−</span><div class="body"><div class="what">${w}</div>${why ? `<div class="why">${why}</div>` : ''}</div></div>`).join('') : '<div class="fnd-thesis-item"><span class="tk" style="color:var(--ink-2)">○</span><div class="body"><div class="what" style="color:var(--ink-1);font-style:italic">No fundamental bear risks flagged.</div></div></div>'}
      </div>
    </div>

    <!-- HORIZON IMPACT -->
    <div class="ins-pat" style="margin-top:14px">
      <div class="smc-card-h"><span class="ico">🎯</span>FUNDAMENTAL IMPACT BY HORIZON</div>
      <div class="ins-hz-grid">
        <div class="ins-hz minor">
          <div class="ins-hz-h">⚡ SWING<span class="impact">MINOR</span></div>
          <div class="ins-hz-t">Fundamentals rarely move price in 2–14 day windows. Quality is a tiebreaker on otherwise-equal setups.</div>
        </div>
        <div class="ins-hz ${ltScore >= 80 ? 'medium' : ltScore >= 60 ? 'medium' : 'minor'}">
          <div class="ins-hz-h">📈 POSITION<span class="impact">${ltScore >= 80 ? 'MEDIUM' : ltScore >= 60 ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${ltScore >= 80 ? 'Strong fundamentals support multi-week holds. Margin/growth combo provides tailwind through chop.' : ltScore >= 60 ? 'Decent fundamentals — won\'t hurt a Position trade but won\'t carry it on its own.' : 'Weak fundamentals — Position trades require pure-technical conviction.'}</div>
        </div>
        <div class="ins-hz ${ltScore >= 80 ? 'major' : ltScore >= 60 ? 'medium' : 'major'}">
          <div class="ins-hz-h">🚀 INVEST<span class="impact">${ltScore >= 80 ? 'MAJOR' : ltScore >= 60 ? 'MEDIUM' : 'MAJOR'}</span></div>
          <div class="ins-hz-t">${ltScore >= 80 ? 'Premium fundamentals — high-conviction long-term hold. Compounding works in your favor.' : ltScore >= 60 ? 'Middling quality — only worth holding 12+ months if technical/valuation thesis is exceptionally strong.' : `Weak quality — long-term hold ${ltb.gate_fails && ltb.gate_fails.length ? 'gated by '+ltb.gate_fails.join(', ') : 'not advised'}. Demands a clear catalyst or turnaround thesis.`}</div>
        </div>
      </div>
    </div>

    ${_renderFvQualityKPIs(T)}`;
}

export function dispose() { /* no-op */ }
