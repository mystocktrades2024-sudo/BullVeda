// subtabs/smc/smc.js — extracted from elite-detail.html (renderSMC 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const smc = T.smc || {};
  const px = +(T.price || 0);
  const bc = smc.bos_choch || {};
  const obs = smc.order_blocks || [];
  const fvgs = smc.fvg_zones || [];
  const liquidity = smc.liquidity_sweeps || [];
  const direction = (smc.smc_direction || 'neutral').toLowerCase();
  const fracHi = +(T.fractal_high || 0);
  const fracLo = +(T.fractal_low || 0);
  const vwap = T.vwap || {};
  const zq = T.zone_quality || {};

  // ── Determine verdict tone + headline ──
  let tone, arrow, hLabel, hEm;
  if (direction === 'bullish' || (bc.bos_bullish && !bc.bos_bearish)) {
    tone = 'bull'; arrow = '▲'; hLabel = 'Smart money structure is'; hEm = 'BULLISH';
  } else if (direction === 'bearish' || (bc.bos_bearish && !bc.bos_bullish)) {
    tone = 'bear'; arrow = '▼'; hLabel = 'Smart money structure is'; hEm = 'BEARISH';
  } else {
    tone = 'neutral'; arrow = '◆'; hLabel = 'Smart money structure is'; hEm = 'NEUTRAL';
  }

  const lastStruct = bc.last_structure || '—';
  const bosBars = bc.bos_bars_ago;
  const chochBars = bc.choch_bars_ago;
  const bosEvent = bc.bos_bullish ? 'Bullish BOS' : bc.bos_bearish ? 'Bearish BOS' : 'No active BOS';
  const chochEvent = bc.choch_bullish ? 'Bullish CHoCH' : bc.choch_bearish ? 'Bearish CHoCH' : 'No CHoCH';

  // OB stats
  const freshOBs = obs.filter(o => o.freshness >= 0.7 && o.status !== 'mitigated').length;
  const testedOBs = obs.filter(o => o.status === 'tested').length;
  const mitigatedOBs = obs.filter(o => o.status === 'mitigated').length;
  const bullOBs = obs.filter(o => o.type === 'bullish').length;
  const bearOBs = obs.filter(o => o.type === 'bearish').length;
  const topOBs = [...obs].sort((a,b) => (b.strength_score||0) - (a.strength_score||0)).slice(0, 6);
  const maxStrength = obs.reduce((m,o) => Math.max(m, o.strength_score||0), 1);

  // FVG stats
  const openFVGs = fvgs.filter(f => f.status === 'open');
  const closedFVGs = fvgs.filter(f => f.status === 'closed');

  // Narrative
  let narr = '';
  if (bc.bos_bullish) narr = `Latest break of structure was bullish ${bosBars != null ? bosBars + ' bars ago' : ''}, last swing structure: ${lastStruct}.`;
  else if (bc.bos_bearish) narr = `Latest break of structure was bearish ${bosBars != null ? bosBars + ' bars ago' : ''}, last swing structure: ${lastStruct}.`;
  else narr = `No clear break of structure recently. Last swing structure: ${lastStruct}.`;
  if (freshOBs > 0) narr += ` ${freshOBs} fresh order block${freshOBs>1?'s':''} active.`;
  if (openFVGs.length > 0) narr += ` ${openFVGs.length} unfilled FVG${openFVGs.length>1?'s':''}.`;

  // ── Build the price ladder SVG ──
  // Collect all price levels of interest
  const levels = [];
  obs.slice(0, 12).forEach(o => levels.push({ price: o.price_level, type: 'ob', subtype: o.type, status: o.status, freshness: o.freshness, strength: o.strength_score }));
  fvgs.slice(0, 8).forEach(f => levels.push({ price: (f.top + f.bottom) / 2, top: f.top, bottom: f.bottom, type: 'fvg', subtype: f.type, status: f.status, age: f.age_bars }));
  if (fracHi > 0) levels.push({ price: fracHi, type: 'fractal', subtype: 'high', label: 'Fractal High' });
  if (fracLo > 0) levels.push({ price: fracLo, type: 'fractal', subtype: 'low', label: 'Fractal Low' });
  if (vwap.vwap_20d) levels.push({ price: +vwap.vwap_20d, type: 'vwap', subtype: 'vwap', label: 'VWAP 20d' });
  if (vwap.avwap_swing_low) levels.push({ price: +vwap.avwap_swing_low, type: 'vwap', subtype: 'avwap', label: 'AVWAP swing-low' });

  // Determine viewport: ±15% around price, but expand to fit all levels within reason
  const allP = [px, ...levels.map(l => l.price).filter(p => p != null)].filter(p => p > 0);
  const padding = px * 0.18;
  const minP = Math.max(Math.min(...allP) - padding * 0.15, px - padding);
  const maxP = Math.min(Math.max(...allP) + padding * 0.15, px + padding);
  const range = Math.max(maxP - minP, px * 0.05);
  const W = 360, H = 360, padT = 14, padB = 14, padL = 14, padR = 130;
  const yScale = p => padT + ((maxP - p) / range) * (H - padT - padB);
  const cWidth = W - padL - padR;

  // Build ladder elements
  const yPx = yScale(px);
  let ladderSVG = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="smc-ladder-svg" xmlns="http://www.w3.org/2000/svg">`;
  // Background grid (10 lines)
  for (let i = 0; i <= 8; i++) {
    const y = padT + (i / 8) * (H - padT - padB);
    const p = maxP - (i / 8) * range;
    ladderSVG += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#222" stroke-dasharray="2 3" stroke-width="0.5"/>`;
    ladderSVG += `<text x="${W - padR + 8}" y="${y + 3}" font-size="9" fill="#7a818c" font-family="var(--mono)">$${p.toFixed(2)}</text>`;
  }
  // OB rectangles (left half of ladder)
  obs.slice(0, 12).forEach((o, i) => {
    const yT = yScale(o.high), yB = yScale(o.low);
    const isBull = o.type === 'bullish';
    const opacity = o.status === 'mitigated' ? 0.18 : o.status === 'tested' ? 0.5 : 0.85;
    const fill = isBull ? `rgba(74, 222, 128, ${opacity * 0.5})` : `rgba(248, 113, 113, ${opacity * 0.5})`;
    const stroke = isBull ? `rgba(74, 222, 128, ${opacity})` : `rgba(248, 113, 113, ${opacity})`;
    ladderSVG += `<rect x="${padL + 4}" y="${Math.min(yT, yB)}" width="${cWidth * 0.5}" height="${Math.max(2, Math.abs(yB - yT))}" fill="${fill}" stroke="${stroke}" stroke-width="1" rx="2"/>`;
  });
  // FVG bands (right half)
  fvgs.slice(0, 8).forEach((f, i) => {
    const yT = yScale(f.top), yB = yScale(f.bottom);
    const isBull = f.type === 'bullish';
    const opacity = f.status === 'closed' ? 0.18 : 0.6;
    const fill = isBull ? `rgba(74, 222, 128, ${opacity * 0.4})` : `rgba(248, 113, 113, ${opacity * 0.4})`;
    const stroke = isBull ? `rgba(74, 222, 128, ${opacity})` : `rgba(248, 113, 113, ${opacity})`;
    ladderSVG += `<rect x="${padL + cWidth * 0.55}" y="${Math.min(yT, yB)}" width="${cWidth * 0.45}" height="${Math.max(2, Math.abs(yB - yT))}" fill="${fill}" stroke="${stroke}" stroke-width="1" stroke-dasharray="3 2" rx="2"/>`;
  });
  // Fractal levels (lines spanning full width)
  if (fracHi > 0) {
    const y = yScale(fracHi);
    ladderSVG += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 3"/>`;
    ladderSVG += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#94a3b8" font-weight="700">FH $${fracHi.toFixed(2)}</text>`;
  }
  if (fracLo > 0) {
    const y = yScale(fracLo);
    ladderSVG += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 3"/>`;
    ladderSVG += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#94a3b8" font-weight="700">FL $${fracLo.toFixed(2)}</text>`;
  }
  // VWAP / AVWAP
  if (vwap.vwap_20d) {
    const y = yScale(+vwap.vwap_20d);
    ladderSVG += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#a78bfa" stroke-width="1.2"/>`;
    ladderSVG += `<text x="${padL + 4}" y="${y - 3}" font-size="9" fill="#a78bfa" font-weight="700">VWAP $${(+vwap.vwap_20d).toFixed(2)}</text>`;
  }
  if (vwap.avwap_swing_low) {
    const y = yScale(+vwap.avwap_swing_low);
    ladderSVG += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#a78bfa" stroke-width="1" stroke-dasharray="3 2"/>`;
    ladderSVG += `<text x="${padL + 4}" y="${y + 10}" font-size="9" fill="#a78bfa" font-weight="700">AVWAP $${(+vwap.avwap_swing_low).toFixed(2)}</text>`;
  }
  // Current price marker (highlighted)
  ladderSVG += `<line x1="${padL}" y1="${yPx}" x2="${W - padR}" y2="${yPx}" stroke="#fbbf24" stroke-width="2"/>`;
  ladderSVG += `<rect x="${W - padR - 70}" y="${yPx - 8}" width="60" height="16" fill="#fbbf24" rx="2"/>`;
  ladderSVG += `<text x="${W - padR - 40}" y="${yPx + 4}" font-size="10" fill="#0a0e14" text-anchor="middle" font-weight="800" font-family="var(--mono)">NOW $${px.toFixed(2)}</text>`;
  ladderSVG += `</svg>`;

  // ── SMC-driven trade plan (synthesized from data) ──
  // Find best bullish OB (fresh, near price, high strength)
  const bullishCandidates = obs.filter(o => o.type === 'bullish' && o.price_level < px && o.status !== 'mitigated')
    .sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0));
  const bestBullOB = bullishCandidates[0];
  // Stop = below fractal low or below the OB low
  const planStop = bestBullOB ? Math.min(bestBullOB.low * 0.98, fracLo > 0 ? fracLo * 0.98 : bestBullOB.low * 0.98) : (fracLo > 0 ? fracLo * 0.98 : px * 0.95);
  const planEntry = bestBullOB ? bestBullOB.price_level : (fracLo > 0 ? fracLo * 1.005 : px * 0.97);
  // Target = nearest open bearish OB above, or fractal high, or 1.618x risk
  const bearishAbove = obs.filter(o => o.type === 'bearish' && o.price_level > px && o.status !== 'mitigated')
    .sort((a, b) => a.price_level - b.price_level)[0];
  const risk = planEntry - planStop;
  const planTarget = bearishAbove ? bearishAbove.price_level : (fracHi > 0 && fracHi > px ? fracHi : planEntry + risk * 2.0);
  const planRR = risk > 0 ? (planTarget - planEntry) / risk : 0;

  // ── Horizon impact ──
  const hzImpact = (() => {
    const hasOpenFvgBelow = openFVGs.filter(f => f.bottom < px).length;
    const hasFreshBullOB = bullishCandidates.filter(o => o.freshness >= 0.7).length;
    const dirIsBull = tone === 'bull';
    return {
      swing: dirIsBull && hasOpenFvgBelow ? `Tactical pullback into open FVG below = ideal entry. ${hasOpenFvgBelow} unfilled gap${hasOpenFvgBelow>1?'s':''} near price.` : (tone === 'bear' ? 'Bearish structure — short pullbacks to bearish OBs above.' : 'No clear SMC tactical setup.'),
      position: dirIsBull && hasFreshBullOB ? `Buy pullback to nearest fresh demand OB. ${hasFreshBullOB} candidate${hasFreshBullOB>1?'s':''} below current price.` : (tone === 'bear' ? 'Wait for bullish CHoCH before considering position longs.' : 'No fresh demand zones — wait for new OB formation.'),
      invest: dirIsBull ? `Higher-timeframe BOS bullish. SMC supports a structural long bias for 12+ months.` : (tone === 'bear' ? `Higher-timeframe BOS bearish. Avoid new positions until structure flips.` : 'Neutral structure — no SMC-driven invest signal.'),
    };
  })();

  // ── D-8: LuxAlgo MTF Screener (MVP) ── 3 dense tables: PA / S&R / Osc ──
  // _toneDot returns a <td>-wrapped span so it can be dropped directly into <tr>.
  const _toneDot = (s) => {
    if (s == null) return '<td style="text-align:center"><span style="color:var(--ink-3)">—</span></td>';
    const cls = s === 'bull' || s === 'pass' ? 'pass' : s === 'bear' || s === 'fail' ? 'fail' : 'warn';
    const t = { bull:'▲', bear:'▼', wait:'◆', pass:'✓', fail:'✗', warn:'~', dim:'—' }[s] || s;
    return `<td style="text-align:center"><span class="lux-dot ${cls}">${t}</span></td>`;
  };
  const _rsi = T.rsi || 50, _macd = T.macd_bullish, _stoch = T.stoch_rsi;
  const _above50 = T.above_50ema, _above200 = T.above_200sma;
  const _rsRank = T.rs_rank || 50;
  const _rvol = T.rvol || 1;
  const _luxPriceAction = `
    <table class="lux-tbl">
      <thead><tr><th>TF</th><th>Trend</th><th>Structure</th><th>Stack</th><th class="r">RVOL</th><th>Bias</th></tr></thead>
      <tbody>
        <tr><td><span class="lux-tf">1H</span></td>${_toneDot('warn')}${_toneDot('warn')}${_toneDot('warn')}<td class="r mono">${_rvol.toFixed(2)}×</td>${_toneDot('wait')}</tr>
        <tr><td><span class="lux-tf">4H</span></td>${_toneDot(_rvol > 1.2 ? 'bull' : 'wait')}${_toneDot('warn')}${_toneDot('warn')}<td class="r mono">${_rvol.toFixed(2)}×</td>${_toneDot(_rvol > 1.2 ? 'bull' : 'wait')}</tr>
        <tr><td><span class="lux-tf">D1</span></td>${_toneDot(_above50 ? 'bull' : 'bear')}${_toneDot(T.smc_score >= 6 ? 'bull' : 'wait')}${_toneDot(_above50 ? 'bull' : 'wait')}<td class="r mono">${_rvol.toFixed(2)}×</td>${_toneDot(T.verdict === 'BUY' ? 'bull' : T.verdict === 'WATCH' ? 'wait' : 'bear')}</tr>
        <tr><td><span class="lux-tf">W</span></td>${_toneDot(_above200 ? 'bull' : 'bear')}${_toneDot(_above200 ? 'bull' : 'bear')}${_toneDot(_above200 ? 'bull' : 'bear')}<td class="r mono" style="color:var(--ink-3)">—</td>${_toneDot(_above200 ? 'bull' : 'bear')}</tr>
      </tbody>
    </table>`;

  const _luxLevels = (() => {
    const levels = [];
    const _validPrice = (p) => typeof p === 'number' && isFinite(p) && p > 0;
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
    if (_validPrice(T.entry_low)) levels.push({ tf: 'PLN', kind: 'Entry', price: T.entry_low, dist: ((T.entry_low/px - 1)*100), src: 'Plan' });
    if (_validPrice(T.target1))   levels.push({ tf: 'PLN', kind: 'T1',    price: T.target1,   dist: ((T.target1/px - 1)*100),   src: 'Plan' });
    if (_validPrice(T.stop))      levels.push({ tf: 'PLN', kind: 'Stop',  price: T.stop,      dist: ((T.stop/px - 1)*100),      src: 'Plan' });
    levels.sort((a,b) => Math.abs(a.dist) - Math.abs(b.dist));
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
  })();

  const _luxOsc = `
    <table class="lux-tbl">
      <thead><tr><th>Indicator</th><th class="r">1H</th><th class="r">4H</th><th class="r">D1</th><th>Verdict</th></tr></thead>
      <tbody>
        <tr><td>RSI(14)</td><td class="r mono" style="color:var(--ink-3)">—</td><td class="r mono" style="color:var(--ink-3)">—</td><td class="r mono">${_rsi.toFixed(0)}</td>${_toneDot(_rsi > 70 ? 'fail' : _rsi < 30 ? 'pass' : _rsi >= 50 ? 'bull' : 'warn')}</tr>
        <tr><td>MACD</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td>${_toneDot(_macd ? 'bull' : 'bear')}${_toneDot(_macd ? 'bull' : 'bear')}</tr>
        <tr><td>Stoch RSI</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${_stoch != null ? _stoch.toFixed(0) : '—'}</td>${_toneDot(_stoch == null ? 'wait' : _stoch < 20 ? 'pass' : _stoch > 80 ? 'fail' : _stoch >= 50 ? 'bull' : 'warn')}</tr>
        <tr><td>RS rank</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${_rsRank}</td>${_toneDot(_rsRank >= 80 ? 'bull' : _rsRank >= 50 ? 'wait' : 'bear')}</tr>
        <tr><td>RVOL</td><td class="r" style="color:var(--ink-3)">—</td><td class="r" style="color:var(--ink-3)">—</td><td class="r mono">${_rvol.toFixed(2)}×</td>${_toneDot(_rvol > 1.5 ? 'bull' : _rvol > 1.0 ? 'wait' : 'warn')}</tr>
      </tbody>
    </table>`;

  const _luxScreener = `
    <div class="lux-wrap">
      <div class="lux-h"><span style="font-size:14px">⌬</span> MULTI-TIMEFRAME SCREENER <span class="lux-meta">LuxAlgo-style · 3 dense tables · 1 glance</span></div>
      <div class="lux-grid">
        <div class="lux-card"><div class="lux-card-h">PRICE ACTION</div>${_luxPriceAction}</div>
        <div class="lux-card"><div class="lux-card-h">KEY LEVELS</div>${_luxLevels}</div>
        <div class="lux-card"><div class="lux-card-h">OSCILLATORS</div>${_luxOsc}</div>
      </div>
    </div>
  `;

  $('smcBody').innerHTML = `
    ${_luxScreener}
    <!-- VERDICT BANNER -->
    <div class="smc-verdict ${tone}">
      <div class="smc-v-arrow">${arrow}</div>
      <div class="smc-v-mid">
        <div class="tag">SMC STRUCTURE · ${(smc.smc_direction || 'neutral').toUpperCase()}</div>
        <div class="h">${hLabel} <span class="em">${hEm}</span></div>
        <div class="narr">${narr}</div>
      </div>
      <div class="smc-v-r">
        <div class="smc-v-score">${(+(smc.score || 0)).toFixed(1)}</div>
        <div class="smc-v-score-lbl">SMC Score</div>
      </div>
    </div>

    <!-- PRICE LADDER + RIGHT COLUMN -->
    <div class="smc-main">
      <div class="smc-ladder">
        <div class="smc-ladder-h"><span class="ico">📊</span>PRICE LADDER · LEVELS AROUND $${px.toFixed(2)}</div>
        ${ladderSVG}
        <div class="smc-ladder-legend">
          <span class="item"><span class="swatch" style="background:rgba(74,222,128,0.5);border:1px solid rgba(74,222,128,0.85)"></span>Bullish OB</span>
          <span class="item"><span class="swatch" style="background:rgba(248,113,113,0.5);border:1px solid rgba(248,113,113,0.85)"></span>Bearish OB</span>
          <span class="item"><span class="swatch" style="background:rgba(74,222,128,0.3);border:1px dashed rgba(74,222,128,0.7)"></span>Bull FVG</span>
          <span class="item"><span class="swatch" style="background:rgba(248,113,113,0.3);border:1px dashed rgba(248,113,113,0.7)"></span>Bear FVG</span>
          <span class="item"><span class="swatch" style="background:#a78bfa"></span>VWAP</span>
          <span class="item"><span class="swatch" style="background:#fbbf24"></span>NOW</span>
        </div>
      </div>

      <div class="smc-rcol">
        <div class="smc-pgrid">
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">🏗</span>MARKET STRUCTURE</div>
            <div class="smc-card-row"><span class="l">Last swing</span><span class="r ${lastStruct === 'HH' || lastStruct === 'HL' ? 'pass' : lastStruct === 'LH' || lastStruct === 'LL' ? 'fail' : ''}">${lastStruct}</span></div>
            <div class="smc-card-row"><span class="l">Break of Structure</span><span class="r ${bc.bos_bullish ? 'pass' : bc.bos_bearish ? 'fail' : ''}">${bosEvent}${bosBars != null ? ` · ${bosBars}b ago` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Change of Character</span><span class="r ${bc.choch_bullish ? 'pass' : bc.choch_bearish ? 'fail' : ''}">${chochEvent}${chochBars != null ? ` · ${chochBars}b ago` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Direction</span><span class="r ${tone === 'bull' ? 'pass' : tone === 'bear' ? 'fail' : ''}">${(smc.smc_direction || 'neutral').toUpperCase()}</span></div>
          </div>
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">📍</span>VWAP & FRACTALS</div>
            <div class="smc-card-row"><span class="l">VWAP 20d</span><span class="r ${vwap.above_vwap ? 'pass' : 'fail'}">${vwap.vwap_20d ? '$' + (+vwap.vwap_20d).toFixed(2) : '—'}${vwap.above_vwap != null ? (vwap.above_vwap ? ' · ABOVE' : ' · BELOW') : ''}</span></div>
            <div class="smc-card-row"><span class="l">AVWAP swing-low</span><span class="r ${vwap.above_avwap ? 'pass' : 'fail'}">${vwap.avwap_swing_low ? '$' + (+vwap.avwap_swing_low).toFixed(2) : '—'}</span></div>
            <div class="smc-card-row"><span class="l">Fractal high</span><span class="r">${fracHi > 0 ? '$' + fracHi.toFixed(2) : '—'}${fracHi > 0 ? ` · +${((fracHi-px)/px*100).toFixed(1)}%` : ''}</span></div>
            <div class="smc-card-row"><span class="l">Fractal low</span><span class="r">${fracLo > 0 ? '$' + fracLo.toFixed(2) : '—'}${fracLo > 0 ? ` · ${((fracLo-px)/px*100).toFixed(1)}%` : ''}</span></div>
          </div>
        </div>
        <div class="smc-pgrid">
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">🟩</span>ORDER BLOCKS<span class="meta">${obs.length} total</span></div>
            <div class="smc-bigstat"><span class="v ${freshOBs > 0 ? 'pass' : ''}">${freshOBs}</span><span class="u">fresh · active demand zones</span></div>
            <div class="smc-card-row"><span class="l">Bullish OBs</span><span class="r pass">${bullOBs}</span></div>
            <div class="smc-card-row"><span class="l">Bearish OBs</span><span class="r fail">${bearOBs}</span></div>
            <div class="smc-status-pills">
              <span class="smc-status-pill fresh">${freshOBs} fresh</span>
              <span class="smc-status-pill tested">${testedOBs} tested</span>
              <span class="smc-status-pill mitigated">${mitigatedOBs} mitigated</span>
            </div>
          </div>
          <div class="smc-card">
            <div class="smc-card-h"><span class="ico">⚡</span>FAIR VALUE GAPS<span class="meta">${fvgs.length} total</span></div>
            <div class="smc-bigstat"><span class="v ${openFVGs.length > 0 ? 'pass' : ''}">${openFVGs.length}</span><span class="u">open · unfilled magnets</span></div>
            <div class="smc-card-row"><span class="l">Open</span><span class="r pass">${openFVGs.length}</span></div>
            <div class="smc-card-row"><span class="l">Closed</span><span class="r">${closedFVGs.length}</span></div>
            <div class="smc-card-row"><span class="l">Liquidity sweeps</span><span class="r ${liquidity.length > 0 ? 'warn' : ''}">${liquidity.length}</span></div>
          </div>
        </div>
        ${zq.label ? `
        <div class="smc-card">
          <div class="smc-card-h"><span class="ico">⭐</span>ZONE QUALITY<span class="meta">${zq.points || 0} confluence pts</span></div>
          <div class="smc-bigstat"><span class="v ${zq.label === 'Strong' ? 'pass' : zq.label === 'Weak' ? 'fail' : ''}">${zq.label}</span><span class="u">at the demand zone</span></div>
          <div class="smc-zq-reasons">${(zq.reasons || []).map(r => `<span class="chip">${r}</span>`).join('')}</div>
        </div>` : ''}
      </div>
    </div>

    <!-- TOP ORDER BLOCKS TABLE -->
    ${topOBs.length ? `
    <div class="smc-card" style="padding:0; margin-bottom:14px;">
      <div class="smc-card-h" style="padding:14px 16px 8px"><span class="ico">📋</span>TOP ORDER BLOCKS BY STRENGTH</div>
      <table class="smc-table">
        <thead><tr><th>Type</th><th class="r">Price</th><th class="r">Range</th><th>Status</th><th>Freshness</th><th>Strength</th><th class="r">Bars ago</th></tr></thead>
        <tbody>
          ${topOBs.map(o => {
            const isBull = o.type === 'bullish';
            const sCls = o.status === 'mitigated' ? 'mitigated' : o.status === 'tested' ? 'tested' : 'fresh';
            const strengthPct = ((o.strength_score || 0) / maxStrength) * 100;
            return `<tr>
              <td><span class="ob-pill ${isBull ? 'demand' : 'supply'}">${isBull ? 'DEMAND' : 'SUPPLY'}</span></td>
              <td class="num px">$${(+o.price_level).toFixed(2)}</td>
              <td class="num">$${(+o.low).toFixed(2)} – $${(+o.high).toFixed(2)}</td>
              <td><span class="smc-status-pill ${sCls}">${(o.status || 'fresh').toUpperCase()}</span></td>
              <td>${(o.freshness * 100).toFixed(0)}%</td>
              <td><div class="strength-bar"><div class="strength-bar-f ${isBull ? '' : 'bear'}" style="width:${strengthPct.toFixed(0)}%"></div></div></td>
              <td class="num">${o.bars_since}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : ''}

    <!-- TOP FVG TABLE -->
    ${openFVGs.length ? `
    <div class="smc-card" style="padding:0; margin-bottom:14px;">
      <div class="smc-card-h" style="padding:14px 16px 8px"><span class="ico">⚡</span>OPEN FAIR VALUE GAPS — UNFILLED MAGNETS</div>
      <table class="smc-table">
        <thead><tr><th>Type</th><th class="r">Top</th><th class="r">Bottom</th><th class="r">Size</th><th class="r">Distance</th><th class="r">Age</th></tr></thead>
        <tbody>
          ${openFVGs.slice(0, 8).map(f => {
            const mid = (f.top + f.bottom) / 2;
            const distPct = ((mid - px) / px * 100);
            return `<tr>
              <td><span class="ob-pill ${f.type === 'bullish' ? 'demand' : 'supply'}">${(f.type || '').toUpperCase()}</span></td>
              <td class="num px">$${(+f.top).toFixed(2)}</td>
              <td class="num px">$${(+f.bottom).toFixed(2)}</td>
              <td class="num">${(f.size_pct * 100).toFixed(2)}%</td>
              <td class="num" style="color:${Math.abs(distPct) < 2 ? 'var(--warn)' : 'var(--ink-1)'}">${distPct >= 0 ? '+' : ''}${distPct.toFixed(1)}%</td>
              <td class="num">${f.age_bars}b</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : ''}

    <!-- SMC-DRIVEN TRADE PLAN -->
    ${tone !== 'neutral' && bestBullOB ? `
    <div class="smc-plan">
      <div class="smc-plan-h">SMC-DRIVEN TRADE PLAN — ${tone === 'bull' ? 'LONG SETUP' : 'SHORT SETUP'}</div>
      <div class="smc-plan-grid">
        <div class="smc-plan-tile entry"><div class="lbl">Entry</div><div class="v">$${planEntry.toFixed(2)}</div><div class="sub">Bull OB · strength ${bestBullOB.strength_score.toFixed(1)}</div></div>
        <div class="smc-plan-tile stop"><div class="lbl">Stop</div><div class="v">$${planStop.toFixed(2)}</div><div class="sub">Below OB low or fractal low</div></div>
        <div class="smc-plan-tile target"><div class="lbl">Target</div><div class="v">$${planTarget.toFixed(2)}</div><div class="sub">${bearishAbove ? 'Nearest bearish OB' : 'Fractal high · 2× risk'}</div></div>
        <div class="smc-plan-tile rr"><div class="lbl">R:R</div><div class="v">${planRR.toFixed(1)}×</div><div class="sub">${planRR >= 3 ? 'Strong' : planRR >= 2 ? 'Acceptable' : 'Sub-par'}</div></div>
      </div>
    </div>
    ` : ''}

    <!-- HORIZON IMPACT -->
    <div class="ins-pat" style="margin-top:14px;">
      <div class="smc-card-h"><span class="ico">🎯</span>SMC IMPACT BY HORIZON</div>
      <div class="ins-hz-grid">
        <div class="ins-hz ${tone === 'bull' && openFVGs.filter(f => f.bottom < px).length > 0 ? 'major' : tone === 'neutral' ? 'minor' : 'medium'}">
          <div class="ins-hz-h">⚡ SWING<span class="impact">${tone === 'bull' && openFVGs.filter(f => f.bottom < px).length > 0 ? 'MAJOR' : tone === 'neutral' ? 'MINOR' : 'MEDIUM'}</span></div>
          <div class="ins-hz-t">${hzImpact.swing}</div>
        </div>
        <div class="ins-hz ${tone === 'bull' && bullishCandidates.filter(o => o.freshness >= 0.7).length > 0 ? 'major' : tone === 'neutral' ? 'minor' : 'medium'}">
          <div class="ins-hz-h">📈 POSITION<span class="impact">${tone === 'bull' && bullishCandidates.filter(o => o.freshness >= 0.7).length > 0 ? 'MAJOR' : tone === 'neutral' ? 'MINOR' : 'MEDIUM'}</span></div>
          <div class="ins-hz-t">${hzImpact.position}</div>
        </div>
        <div class="ins-hz ${tone === 'bull' ? 'major' : tone === 'bear' ? 'major' : 'minor'}">
          <div class="ins-hz-h">🚀 INVEST<span class="impact">${tone === 'bull' ? 'MAJOR' : tone === 'bear' ? 'MAJOR' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${hzImpact.invest}</div>
        </div>
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }
