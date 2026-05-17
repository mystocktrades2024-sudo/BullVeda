// subtabs/technicals/chart.js — extracted from elite-detail.html (renderChart 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const W = 720, H = 360, pL = 52, pR = 64, pT = 20, pB = 36;
  const cW = W - pL - pR, cH = H - pT - pB;
  // Use REAL OHLCV when available; fall back to synthetic for tickers without bars in the bundle
  const realBars = (T.ohlcv && T.ohlcv.length > 0) ? T.ohlcv : null;
  let candles = [];
  if (realBars) {
    candles = realBars.map(b => ({ open: b.o, close: b.c, high: b.h, low: b.l, volume: b.v, date: b.d }));
  } else {
    const seed = (T.ticker||'').split('').reduce((s,c)=>s+c.charCodeAt(0),0)*31 + (T.score||0);
    let s = seed; let close = T.price - 6;
    for (let i = 0; i < 60; i++) {
      s = (s * 9301 + 49297) % 233280;
      const r = (s/233280) - 0.45;
      const open = close, wick = 1.2 + Math.abs(r)*2.4, body = r*1.5 + (i/60)*0.3;
      close = open + body;
      candles.push({open, close, high: Math.max(open,close)+wick*0.7, low: Math.min(open,close)-wick*0.7});
    }
    const last = candles.at(-1).close, off = T.price - last;
    candles.forEach(c => { c.open+=off; c.close+=off; c.high+=off; c.low+=off; });
  }
  const allH = candles.map(c=>c.high), allL = candles.map(c=>c.low);
  const maxP = Math.max(...allH, T.target2 || T.target1)*1.005;
  const minP = Math.min(...allL, T.stop)*0.995;
  const yS = v => pT + ((maxP-v)/(maxP-minP))*cH;
  const xS = i => pL + (i/(candles.length-1))*cW;
  // Save chart state for crosshair handler
  window._chartState = { W, H, pL, pR, pT, pB, cW, cH, candles, maxP, minP };
  const bw = (cW/candles.length)*0.55;
  let html = '';
  for (let i=0;i<=4;i++) {
    const y = pT + (i/4)*cH;
    const price = maxP - (i/4)*(maxP-minP);
    html += `<line x1="${pL}" y1="${y}" x2="${W-pR}" y2="${y}" stroke="oklch(20% 0.012 250)" stroke-dasharray="2 4"/>`;
    html += `<text x="${pL-6}" y="${y+3}" font-size="9.5" fill="oklch(42% 0.01 250)" text-anchor="end" font-family="${getFont()}">${price.toFixed(0)}</text>`;
  }
  // EMA21
  const ema21 = []; const k = 2/22;
  candles.forEach((c,i)=>{ ema21.push(i===0?c.close:c.close*k+ema21[i-1]*(1-k)); });
  const emaPath = ema21.map((v,i)=>`${i===0?'M':'L'}${xS(i).toFixed(1)},${yS(v).toFixed(1)}`).join(' ');
  html += `<path d="${emaPath}" fill="none" stroke="#fbbf24" stroke-width="1.5" opacity="0.8"/>`;
  // candles
  candles.forEach((c,i) => {
    const up = c.close >= c.open, col = up ? '#4ade80' : '#f87171';
    const x = xS(i);
    html += `<line x1="${x}" y1="${yS(c.high)}" x2="${x}" y2="${yS(c.low)}" stroke="${col}" stroke-width="1"/>`;
    html += `<rect x="${(x-bw/2).toFixed(1)}" y="${yS(Math.max(c.open,c.close)).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,Math.abs(yS(c.open)-yS(c.close))).toFixed(1)}" fill="${col}" opacity="${up?0.85:1}"/>`;
  });
  // levels — include REAL fractal high/low + VWAP if present
  const levels = [
    [T.target2 || T.target1, T.target2 ? 'T2' : null, 'oklch(74% 0.12 220)'],
    [T.target1, 'T1', 'oklch(80% 0.15 80)'],
    [T.fractal_high, 'F-HI', 'oklch(72% 0.12 280)'],
    [T.price, '$' + px(T.price), 'oklch(96% 0.005 90)', true],
    [(T.vwap || {}).price, 'VWAP', 'oklch(68% 0.10 200)'],
    [T.entry_low, 'ENT', '#4ade80'],
    [T.fractal_low, 'F-LO', 'oklch(64% 0.18 320)'],
    [T.stop, 'STOP', '#f87171'],
  ].filter(l => l[0] != null && l[1] != null && l[0] >= minP && l[0] <= maxP);
  levels.forEach(([price, label, color, nowLine]) => {
    const y = yS(price);
    html += `<line x1="${pL}" y1="${y}" x2="${W-pR}" y2="${y}" stroke="${color}" stroke-width="${nowLine?1.5:1}" stroke-dasharray="${nowLine?'2 2':'4 4'}" opacity="0.8"/>`;
    const rw = 56, rx = W-pR+2;
    html += `<rect x="${rx}" y="${y-8}" width="${rw}" height="16" fill="${color}" fill-opacity="${nowLine?1:0.18}" rx="2"/>`;
    html += `<text x="${rx+rw/2}" y="${y+4}" font-size="9.5" font-family="${getFont()}" font-weight="${nowLine?700:500}" text-anchor="middle" fill="${nowLine?'oklch(12% 0.008 250)':color}">${label}</text>`;
  });

  // Build evidence list, failures first
  const ev = [
    {grp:'EMA Structure', items:[
      {pass: T.above_50ema, name:'Above EMA50', sub:'price vs trend', val: T.above_50ema ? 'YES' : 'NO', tag: T.above_50ema?'PASS':'FAIL'},
      {pass: T.above_200sma, name:'Above 200 SMA', sub:'long-term', val: T.above_200sma ? 'YES' : 'NO', tag: T.above_200sma?'PASS':'FAIL'},
      {pass: T.ema_signal && (T.ema_signal+'').toLowerCase().includes('bull'), name:'EMA stack', sub:'8>21>50', val: T.ema_signal || '—', tag: 'INFO', kind: 'info'},
    ]},
    {grp:'Momentum', items:[
      {pass: T.rsi != null && T.rsi >= 40 && T.rsi <= 70, name:'RSI 14', sub:'40–70 healthy', val: fmt(T.rsi, 1), tag: T.rsi >= 70 ? 'OB' : T.rsi <= 30 ? 'OS' : 'PASS'},
      {pass: T.macd_bullish, name:'MACD', sub:'histogram trend', val: T.macd_bullish ? 'BULL' : 'BEAR', tag: T.macd_bullish?'PASS':'FAIL'},
    ]},
    {grp:'Volume & Flow', items:[
      {pass: T.rvol > 1.2, name:'RVOL', sub:'≥1.2× threshold', val: T.rvol ? T.rvol.toFixed(2)+'×' : '—', tag: T.rvol > 1.2 ? 'PASS' : 'WATCH'},
      {pass: T.atr_pct != null && T.atr_pct < 5, name:'ATR%', sub:'volatility', val: fmt(T.atr_pct, 2)+'%', tag: T.atr_pct < 3 ? 'PASS' : T.atr_pct < 5 ? 'INFO' : 'WATCH', kind:'info'},
    ]},
    {grp:'Smart Money', items:[
      {pass: T.smc_score >= 6, name:'SMC zones', sub:'order blocks · liquidity', val: (T.smc_score||0)+'/10', tag: T.smc_score >= 6 ? 'PASS' : 'WATCH'},
      ...(((T.smc || {}).order_blocks || []).length ? [{pass: true, name:'Order blocks', sub:'institutional zones', val: (T.smc.order_blocks || []).length, tag: 'INFO', kind:'info'}] : []),
      ...(((T.smc || {}).liquidity_zones || []).length ? [{pass: true, name:'Liquidity zones', sub:'stop hunts targeted', val: (T.smc.liquidity_zones || []).length, tag: 'INFO', kind:'info'}] : []),
      ...((T.smc || {}).structure_break ? [{pass: true, name:'Structure break', sub:'BoS / CHoCH', val: T.smc.structure_break, tag:'PASS'}] : []),
      {pass: (T.squeeze && T.squeeze.on) || T.squeeze_on, name:'Squeeze', sub:'volatility coil', val: ((T.squeeze && T.squeeze.on) || T.squeeze_on) ? 'FIRING' : 'inactive', tag: ((T.squeeze && T.squeeze.on) || T.squeeze_on) ?'PASS':'INFO', kind: ((T.squeeze && T.squeeze.on) || T.squeeze_on) ? 'pass':'info'},
    ]},
    {grp:'Williams Fractals', items:[
      {pass: T.fractal_high != null, name:'Fractal high', sub:'recent swing high', val: T.fractal_high ? '$' + T.fractal_high.toFixed(2) : '—', tag: 'INFO', kind:'info'},
      {pass: T.fractal_low != null, name:'Fractal low', sub:'recent swing low', val: T.fractal_low ? '$' + T.fractal_low.toFixed(2) : '—', tag: 'INFO', kind:'info'},
      {pass: T.fractal_signal && T.fractal_signal.toLowerCase().includes('bull'), name:'Fractal signal', sub:'price vs S/R', val: T.fractal_signal || '—', tag: T.fractal_signal && T.fractal_signal.includes('BULL') ? 'PASS' : T.fractal_signal && T.fractal_signal.includes('BEAR') ? 'FAIL' : 'INFO', kind: T.fractal_signal && T.fractal_signal.includes('BETWEEN') ? 'info' : T.fractal_signal && T.fractal_signal.includes('BULL') ? 'pass' : 'info'},
    ]},
    ...(Object.keys(T.patterns || {}).length ? [{
      grp:'Chart Patterns', items: Object.entries(T.patterns || {})
        .filter(([k, v]) => v && (typeof v === 'string' ? v !== '' : true))
        .map(([k, v]) => {
          const name = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
          const passing = (typeof v === 'string' && v.toLowerCase().includes('bull')) || (typeof v === 'object' && v.confidence > 0.5);
          return { pass: passing, name, sub: typeof v === 'object' ? `confidence ${((v.confidence||0)*100).toFixed(0)}%` : 'detected', val: typeof v === 'object' ? (v.label || '✓') : v, tag: passing ? 'PASS' : 'INFO', kind: passing ? 'pass' : 'info' };
        })
    }] : []),
    {grp:'Context', items:[
      {pass: T.rs_rank >= 80, name:'RS Rank', sub:'63d vs SPX', val: T.rs_rank || '—', tag: T.rs_rank >= 80 ? 'PASS' : T.rs_rank >= 50 ? 'WATCH' : 'FAIL'},
      {pass: T.pct_from_52w_high != null && T.pct_from_52w_high > -10, name:'vs 52W hi', sub:'pullback depth', val: fmt(T.pct_from_52w_high, 1)+'%', tag: T.pct_from_52w_high > -5 ? 'PASS' : 'INFO', kind: T.pct_from_52w_high > -5 ? 'pass':'info'},
      ...((T.vwap || {}).price ? [{pass: T.price > T.vwap.price, name:'VWAP', sub:'volume-weighted avg', val: '$' + T.vwap.price.toFixed(2), tag: T.price > T.vwap.price ? 'PASS' : 'WATCH'}] : []),
      ...(T.market_phase ? [{pass: T.market_phase === 'Trend', name:'Market phase', sub:'Stage 1-4 (Weinstein)', val: T.market_phase, tag: T.market_phase === 'Trend' ? 'PASS' : 'INFO', kind: T.market_phase === 'Trend' ? 'pass' : 'info'}] : []),
    ]},
  ];
  // sort items within each group: failures first
  ev.forEach(g => g.items.sort((a,b) => (a.pass?1:0) - (b.pass?1:0)));

  const evClass = (it) => it.kind === 'info' ? 'info' : it.pass ? 'pass' : (it.tag === 'WATCH' ? 'warn' : 'fail');

  // ─── Extract values from tech_details strings (rich data not at top level) ───
  const td = T.tech_details || {};
  const matchNum = (str, pat) => { const m = (str || '').match(pat); return m ? +m[1] : null; };
  const adx = matchNum(td.trend, /ADX\s*(\d+(?:\.\d+)?)/i);
  const diPlus = matchNum(td.adx_di_score, /\+DI\s*(\d+(?:\.\d+)?)/i);
  const diMinus = matchNum(td.adx_di_score, /-DI\s*(\d+(?:\.\d+)?)/i);
  const stochK = matchNum(td.momentum, /K=\s*(\d+(?:\.\d+)?)/i);
  const stochD = matchNum(td.momentum, /D=\s*(\d+(?:\.\d+)?)/i);
  const mfi = matchNum(td.momentum, /MFI\s*(\d+(?:\.\d+)?)/i);
  const cmf = matchNum(td.volume, /CMF\s*([+-]?\d+(?:\.\d+)?)/i);
  const obvUp = /OBV\s*↑/i.test(td.volume || '');
  const obvDown = /OBV\s*↓/i.test(td.volume || '');
  const supportPx = matchNum(td.sr_structure, /Supp\s*\$?(\d+(?:\.\d+)?)/i);
  const resistPx = matchNum(td.sr_structure, /Resist\s*\$?(\d+(?:\.\d+)?)/i);
  const rsRank = T.rs_rank;
  const trendAge = (td.trend_age || '').replace(/\([^)]*\)/, '').trim();
  const rvol = T.rvol;
  const atrPct = T.atr_pct;
  const rsi = T.rsi;
  const macdBull = T.macd_bullish;
  const px0 = +(T.price || 0);
  const sma200 = matchNum(td.sr_structure, /200d\s*\$?(\d+(?:\.\d+)?)/i);
  const ema50d = T.above_50ema;
  const w52H = T.week52_high;
  const w52L = T.week52_low;
  const vwapPx = (T.vwap || {}).vwap_20d;
  const avwapPx = (T.vwap || {}).avwap_swing_low;

  // ─── Verdict tone ───
  let bullCount = 0, bearCount = 0;
  if (T.above_8ema) bullCount++; else bearCount++;
  if (T.above_21ema) bullCount++; else bearCount++;
  if (T.above_50ema) bullCount++; else bearCount++;
  if (T.above_200sma) bullCount++; else bearCount++;
  if (macdBull) bullCount++; else bearCount++;
  if ((rsi || 50) > 50) bullCount++; else bearCount++;
  if (vwapPx && px0 > vwapPx) bullCount++; else bearCount++;
  if (diPlus != null && diMinus != null && diPlus > diMinus) bullCount++; else if (diMinus != null && diPlus != null) bearCount++;
  let tchTone, tchHEm, tchArrow;
  if (bullCount >= 6) { tchTone = 'bull'; tchHEm = bullCount >= 7 ? 'STRONG BULLISH' : 'BULLISH'; tchArrow = '▲'; }
  else if (bearCount >= 6) { tchTone = 'bear'; tchHEm = bearCount >= 7 ? 'STRONG BEARISH' : 'BEARISH'; tchArrow = '▼'; }
  else { tchTone = 'mixed'; tchHEm = 'MIXED'; tchArrow = '◆'; }

  // Narrative
  const tchNarr = [];
  if (td.trend) {
    const trendKw = (td.trend.match(/(strong\s+\w+|weak\s+\w+|\w+trend)/i) || [])[1];
    if (trendKw) tchNarr.push(trendKw.toLowerCase());
  }
  if (adx != null) tchNarr.push(`ADX ${adx.toFixed(0)} (${adx >= 25 ? 'trending' : 'ranging'})`);
  if (rsi != null) tchNarr.push(`RSI ${rsi.toFixed(0)}${rsi >= 70 ? ' (OB)' : rsi <= 30 ? ' (OS)' : ''}`);
  if (rvol != null) tchNarr.push(`RVOL ${rvol.toFixed(2)}×`);
  if (T.ema_signal) tchNarr.push(T.ema_signal.toLowerCase());
  if (trendAge) tchNarr.push(trendAge.toLowerCase());
  const techScore = T.tech_score || 0;
  const techMax = T.tech_max || 38;

  // ─── Reaction checklist ───
  const reactionList = T.reaction_checklist || [];

  // ─── Performance cells ───
  const perfCells = [
    { lbl: '1D', v: T.perf_1d },
    { lbl: '1W', v: T.perf_1w !== null && T.perf_1w !== undefined ? T.perf_1w : T.perf_week },
    { lbl: '1M', v: T.perf_month !== null && T.perf_month !== undefined ? T.perf_month : T.perf_4h },
    { lbl: '3M', v: null },
    { lbl: 'YTD', v: null },
    { lbl: '52W', v: w52H && w52L ? ((px0 - w52L) / (w52H - w52L) * 100) : null },
  ];

  // ─── Distance map ───
  const distRows = [];
  if (vwapPx) distRows.push({ lbl: 'VWAP 20d', v: vwapPx, pct: (px0 - vwapPx) / vwapPx * 100 });
  if (avwapPx) distRows.push({ lbl: 'AVWAP swing-low', v: avwapPx, pct: (px0 - avwapPx) / avwapPx * 100 });
  if (T.fractal_low) distRows.push({ lbl: 'Fractal Low', v: T.fractal_low, pct: (px0 - T.fractal_low) / T.fractal_low * 100 });
  if (T.fractal_high) distRows.push({ lbl: 'Fractal High', v: T.fractal_high, pct: (px0 - T.fractal_high) / T.fractal_high * 100 });
  if (w52H) distRows.push({ lbl: '52w high', v: w52H, pct: (px0 - w52H) / w52H * 100 });
  if (w52L) distRows.push({ lbl: '52w low', v: w52L, pct: (px0 - w52L) / w52L * 100 });

  // ─── Build ───
  $('chartBody').innerHTML = `
    <!-- VERDICT BANNER -->
    <div class="tch-verdict ${tchTone}">
      <div class="tch-v-arrow">${tchArrow}</div>
      <div class="tch-v-mid">
        <div class="tag">TECHNICAL POSTURE · ${tchHEm}</div>
        <div class="h">Trend posture is <span class="em">${tchHEm}</span></div>
        <div class="narr">${tchNarr.join(' · ')}.${td.sector_rotation ? ' ' + td.sector_rotation + '.' : ''}${td.rel_strength ? ' RS Rank ' + (rsRank || '—') + '.' : ''}</div>
      </div>
      <div class="tch-v-r">
        <div class="tch-v-score">${techScore.toFixed(0)}<span class="frac">/${techMax}</span></div>
        <div class="tch-v-score-lbl">Technical Score</div>
      </div>
    </div>

    <!-- CHART + EMA STACK -->
    <div style="display:grid;grid-template-columns:1fr 280px;gap:12px;margin-bottom:14px">
      <div class="chart-card">
        <div class="card-head"><span class="t">Price · 60D · D1</span><span class="m">EMA 21 · trade levels overlaid</span></div>
        <div class="card-toolbar">
          <button class="chip">1D</button><button class="chip">1W</button><button class="chip on">3M</button><button class="chip">6M</button><button class="chip">1Y</button>
          <span style="flex:1"></span>
          <button class="chip on">CDL</button><button class="chip">LINE</button>
          <button class="chip on">EMA</button><button class="chip on">LEVELS</button>
        </div>
        <div style="height:360px;background:var(--bg-1);position:relative;overflow:hidden" id="chartHostWrap">
          <svg id="chartHost" viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block" onmousemove="_chartCrosshair(event, this)" onmouseleave="_chartHideCrosshair()">${html}
            <line id="chXhV" x1="0" y1="0" x2="0" y2="${H}" stroke="rgba(148,163,184,0.4)" stroke-dasharray="3,3" style="display:none;pointer-events:none"/>
            <line id="chXhH" x1="0" y1="0" x2="${W}" y2="0" stroke="rgba(148,163,184,0.4)" stroke-dasharray="3,3" style="display:none;pointer-events:none"/>
          </svg>
          <div class="ch-tip" id="chTip" style="display:none"></div>
        </div>
      </div>
      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">📐</span>EMA STACK<span class="badge ${T.ema_signal && T.ema_signal.toLowerCase().includes('bull') ? 'pass' : T.ema_signal && T.ema_signal.toLowerCase().includes('bear') ? 'fail' : 'warn'}">${T.ema_signal || '—'}</span></div>
        <div class="tch-ema-stack">
          <div class="tch-ema-row ${T.above_8ema ? 'above' : 'below'}"><span class="lbl">EMA 8</span><span class="ind ${T.above_8ema ? 'pass' : 'fail'}">${T.above_8ema ? 'Price above ✓' : 'Price below ✗'}</span><span class="dist">${T.above_8ema ? '↑' : '↓'}</span></div>
          <div class="tch-ema-row ${T.above_21ema ? 'above' : 'below'}"><span class="lbl">EMA 21</span><span class="ind ${T.above_21ema ? 'pass' : 'fail'}">${T.above_21ema ? 'Price above ✓' : 'Price below ✗'}</span><span class="dist">${T.above_21ema ? '↑' : '↓'}</span></div>
          <div class="tch-ema-row ${T.above_50ema ? 'above' : 'below'}"><span class="lbl">EMA 50</span><span class="ind ${T.above_50ema ? 'pass' : 'fail'}">${T.above_50ema ? 'Price above ✓' : 'Price below ✗'}</span><span class="dist">${T.above_50ema ? '↑' : '↓'}</span></div>
          <div class="tch-ema-row ${T.above_200sma ? 'above' : 'below'}"><span class="lbl">SMA 200</span><span class="ind ${T.above_200sma ? 'pass' : 'fail'}">${T.above_200sma ? 'Price above ✓' : 'Price below ✗'}</span><span class="dist">${T.above_200sma ? '↑' : '↓'}</span></div>
        </div>
        <div class="tch-row" style="margin-top:10px"><span class="l">Trend age</span><span class="r ${trendAge.includes('Young') ? 'pass' : trendAge.includes('Mature') ? 'warn' : ''}">${trendAge || '—'}</span></div>
        <div class="tch-row"><span class="l">Market phase</span><span class="r ${T.market_phase === 'Trend' ? 'pass' : ''}">${T.market_phase || '—'}</span></div>
      </div>
    </div>

    <!-- TREND · MOMENTUM · VOLUME -->
    <div class="tch-grid-3">
      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">📈</span>TREND STRENGTH<span class="badge ${adx >= 40 ? 'info' : adx >= 25 ? 'pass' : adx >= 20 ? 'warn' : 'fail'}">${adx != null ? 'ADX ' + adx.toFixed(0) : 'ADX —'}</span></div>
        <div class="tch-bigstat"><span class="v ${adx >= 40 ? 'pass' : adx >= 25 ? 'pass' : adx >= 20 ? 'warn' : 'fail'}">${adx != null ? adx.toFixed(0) : '—'}</span><span class="u">ADX (${adx >= 50 ? 'very strong' : adx >= 25 ? 'trending' : adx >= 20 ? 'developing' : 'ranging'})</span></div>
        <div class="tch-row"><span class="l">+DI</span><span class="r ${diPlus > diMinus ? 'pass' : ''}">${diPlus != null ? diPlus.toFixed(0) : '—'}</span></div>
        <div class="tch-row"><span class="l">-DI</span><span class="r ${diMinus > diPlus ? 'fail' : ''}">${diMinus != null ? diMinus.toFixed(0) : '—'}</span></div>
        <div class="tch-row"><span class="l">RS Rank vs SPX</span><span class="r ${rsRank >= 80 ? 'pass' : rsRank >= 50 ? '' : 'fail'}">${rsRank || '—'}</span></div>
        <div class="tch-row"><span class="l">Sector rotation</span><span class="r ${(td.sector_rotation || '').toLowerCase().includes('inflows') ? 'pass' : (td.sector_rotation || '').toLowerCase().includes('outflows') ? 'fail' : ''}">${(td.sector_rotation || '—').replace(/\(.*?\)/, '').trim().slice(0, 24)}</span></div>
      </div>

      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">⚡</span>MOMENTUM<span class="badge ${rsi >= 70 ? 'warn' : rsi >= 50 ? 'pass' : rsi <= 30 ? 'warn' : 'info'}">${rsi != null ? 'RSI ' + rsi.toFixed(0) : 'RSI —'}</span></div>
        <div class="tch-osc-row">
          <span class="name">RSI 14</span>
          <div class="gauge"><div class="gauge-zone" style="left:0;width:30%;background:rgba(248,113,113,0.06)"></div><div class="gauge-zone" style="left:70%;right:0;background:rgba(248,113,113,0.06)"></div><div class="gauge-marker" style="left:${(rsi||50).toFixed(0)}%"></div></div>
          <span class="val ${rsi >= 70 ? 'warn' : rsi >= 50 ? 'pass' : rsi <= 30 ? 'warn' : ''}">${rsi != null ? rsi.toFixed(1) : '—'}</span>
        </div>
        <div class="tch-osc-row">
          <span class="name">StochRSI K</span>
          <div class="gauge"><div class="gauge-fill ${stochK >= 80 ? 'warn' : stochK >= 50 ? 'pass' : 'fail'}" style="width:${(stochK||0).toFixed(0)}%"></div></div>
          <span class="val ${stochK >= 80 ? 'warn' : stochK >= 50 ? 'pass' : ''}">${stochK != null ? stochK.toFixed(0) : '—'}</span>
        </div>
        <div class="tch-osc-row">
          <span class="name">StochRSI D</span>
          <div class="gauge"><div class="gauge-fill ${stochD >= 80 ? 'warn' : stochD >= 50 ? 'pass' : 'fail'}" style="width:${(stochD||0).toFixed(0)}%"></div></div>
          <span class="val ${stochD >= 80 ? 'warn' : stochD >= 50 ? 'pass' : ''}">${stochD != null ? stochD.toFixed(0) : '—'}</span>
        </div>
        <div class="tch-osc-row">
          <span class="name">MFI</span>
          <div class="gauge"><div class="gauge-fill ${mfi >= 80 ? 'warn' : mfi >= 50 ? 'pass' : 'fail'}" style="width:${(mfi||0).toFixed(0)}%"></div></div>
          <span class="val ${mfi >= 80 ? 'warn' : mfi >= 50 ? 'pass' : ''}">${mfi != null ? mfi.toFixed(0) : '—'}</span>
        </div>
        <div class="tch-row" style="margin-top:6px"><span class="l">MACD</span><span class="r ${macdBull ? 'pass' : 'fail'}">${T.macd_signal || (macdBull ? 'Bullish' : 'Bearish')}</span></div>
      </div>

      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">📊</span>VOLUME / FLOW<span class="badge ${rvol >= 1.5 ? 'pass' : rvol >= 1.0 ? 'info' : 'warn'}">${rvol != null ? 'RVOL ' + rvol.toFixed(2) + '×' : 'RVOL —'}</span></div>
        <div class="tch-bigstat"><span class="v ${rvol >= 1.5 ? 'pass' : rvol >= 1.0 ? '' : 'warn'}">${rvol != null ? rvol.toFixed(2) + '×' : '—'}</span><span class="u">vs 20d avg volume</span></div>
        <div class="tch-row"><span class="l">OBV trend</span><span class="r ${obvUp ? 'pass' : obvDown ? 'fail' : ''}">${obvUp ? '↑ Rising (accum)' : obvDown ? '↓ Falling (dist)' : '—'}</span></div>
        <div class="tch-row"><span class="l">CMF (20d)</span><span class="r ${cmf > 0.1 ? 'pass' : cmf < -0.1 ? 'fail' : ''}">${cmf != null ? (cmf >= 0 ? '+' : '') + cmf.toFixed(2) + (cmf > 0 ? ' (accum)' : cmf < 0 ? ' (dist)' : '') : '—'}</span></div>
        <div class="tch-row"><span class="l">Above VWAP</span><span class="r ${(T.vwap || {}).above_vwap ? 'pass' : 'fail'}">${(T.vwap || {}).above_vwap ? 'YES' : 'NO'}</span></div>
        <div class="tch-row"><span class="l">Above AVWAP</span><span class="r ${(T.vwap || {}).above_avwap ? 'pass' : 'fail'}">${(T.vwap || {}).above_avwap ? 'YES' : 'NO'}</span></div>
      </div>
    </div>

    <!-- VOLATILITY · PERFORMANCE · DISTANCE -->
    <div class="tch-grid-3">
      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">🌪</span>VOLATILITY<span class="badge ${atrPct >= 5 ? 'warn' : atrPct >= 2 ? 'info' : 'pass'}">${atrPct != null ? 'ATR ' + atrPct.toFixed(2) + '%' : 'ATR —'}</span></div>
        <div class="tch-bigstat"><span class="v ${atrPct >= 5 ? 'warn' : ''}">${atrPct != null ? atrPct.toFixed(2) + '%' : '—'}</span><span class="u">daily ATR</span></div>
        <div class="tch-row"><span class="l">Squeeze (TTM)</span><span class="r ${(T.squeeze || {}).on || T.squeeze_on ? 'warn' : ''}">${(T.squeeze || {}).on || T.squeeze_on ? '🔥 FIRING' : 'Inactive'}</span></div>
        <div class="tch-row"><span class="l">Squeeze breakout bonus</span><span class="r ${(td.squeeze_breakout_bonus || '').includes('+') ? 'pass' : ''}">${td.squeeze_breakout_bonus || '—'}</span></div>
        <div class="tch-row"><span class="l">Beta vs SPY</span><span class="r ${T.beta > 1.5 ? 'warn' : T.beta < 0.7 ? 'info' : ''}">${T.beta != null ? T.beta.toFixed(2) + '×' : '—'}</span></div>
      </div>

      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">⏱</span>PERFORMANCE<span class="badge info">vs SPY</span></div>
        <div class="tch-perf-grid">
          ${perfCells.map(c => {
            const v = c.v;
            const cls = v == null ? '' : v > 0.5 ? 'pass' : v < -0.5 ? 'fail' : '';
            const txt = v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
            return `<div class="tch-perf-cell ${cls}"><div class="lbl">${c.lbl}</div><div class="v">${txt}</div></div>`;
          }).join('')}
        </div>
        <div class="tch-row" style="margin-top:10px"><span class="l">52w position</span><span class="r ${perfCells[5].v >= 80 ? 'pass' : perfCells[5].v >= 50 ? '' : 'warn'}">${perfCells[5].v != null ? perfCells[5].v.toFixed(0) + '% of range' : '—'}</span></div>
      </div>

      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">📍</span>DISTANCE MAP<span class="badge info">$${px0.toFixed(2)} now</span></div>
        ${distRows.map(d => {
          const cls = Math.abs(d.pct) < 1 ? 'warn' : d.pct > 0 ? 'pass' : 'fail';
          return `<div class="tch-row"><span class="l">${d.lbl}</span><span class="r ${cls}">$${d.v.toFixed(2)} <span style="color:var(--ink-2);font-weight:500">(${d.pct >= 0 ? '+' : ''}${d.pct.toFixed(1)}%)</span></span></div>`;
        }).join('')}
      </div>
    </div>

    <!-- S/R STRUCTURE -->
    ${(supportPx || resistPx || T.fractal_low || T.fractal_high) ? `
    <div class="tch-card" style="margin-bottom:14px">
      <div class="tch-card-h"><span class="ico">📏</span>S / R STRUCTURE<span class="badge ${tchTone === 'bull' ? 'pass' : 'info'}">${td.sr_structure ? (td.sr_structure.match(/\((\d+)\/5\)/) || [])[1] + '/5' : ''}</span></div>
      <div class="tch-sr">
        ${supportPx ? `<div class="tch-sr-cell support"><div class="lbl">Support</div><div class="v">$${supportPx.toFixed(2)}</div><div class="sub">${px0 > supportPx ? '+' : ''}${((supportPx - px0) / px0 * 100).toFixed(1)}% from price</div></div>` : ''}
        ${resistPx ? `<div class="tch-sr-cell resistance"><div class="lbl">Resistance</div><div class="v">$${resistPx.toFixed(2)}</div><div class="sub">${px0 > resistPx ? '+' : ''}${((resistPx - px0) / px0 * 100).toFixed(1)}% from price</div></div>` : ''}
        ${T.fractal_low ? `<div class="tch-sr-cell support"><div class="lbl">Fractal Low</div><div class="v">$${T.fractal_low.toFixed(2)}</div><div class="sub">recent swing-low pivot</div></div>` : ''}
        ${T.fractal_high ? `<div class="tch-sr-cell resistance"><div class="lbl">Fractal High</div><div class="v">$${T.fractal_high.toFixed(2)}</div><div class="sub">recent swing-high pivot</div></div>` : ''}
      </div>
    </div>` : ''}

    <!-- REACTION CHECKLIST -->
    ${reactionList.length ? `
    <div class="tch-card" style="margin-bottom:14px">
      <div class="tch-card-h"><span class="ico">✅</span>REACTION CHECKLIST<span class="badge ${reactionList.filter(r => r.checked).length >= 3 ? 'pass' : 'warn'}">${reactionList.filter(r => r.checked).length}/${reactionList.length} confirmed</span></div>
      <div class="tch-checklist">
        ${reactionList.map(r => `
          <div class="tch-check-item ${r.checked ? 'ok' : 'no'}">
            <span class="mark">${r.checked ? '✓' : '✗'}</span>
            <div><div class="what">${r.item}</div>${r.detail ? `<div class="why">${r.detail}</div>` : ''}</div>
          </div>
        `).join('')}
      </div>
    </div>` : ''}

    <!-- HORIZON IMPACT -->
    <div class="ins-pat">
      <div class="smc-card-h"><span class="ico">🎯</span>TECHNICAL IMPACT BY HORIZON</div>
      <div class="ins-hz-grid">
        <div class="ins-hz ${tchTone === 'bull' && rvol >= 1.2 ? 'major' : tchTone === 'bear' ? 'medium' : 'minor'}">
          <div class="ins-hz-h">⚡ SWING<span class="impact">${tchTone === 'bull' && rvol >= 1.2 ? 'MAJOR' : tchTone === 'bear' ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${tchTone === 'bull' ? `${rsi >= 70 ? 'Overbought — wait for pullback or short reversal.' : 'Trend + momentum align for short-hold longs.'} RVOL ${rvol != null ? rvol.toFixed(2) + '×' : '—'}.` : tchTone === 'bear' ? 'Bearish technicals — short pullbacks, avoid longs.' : 'Mixed signals — wait for cleaner setup.'}</div>
        </div>
        <div class="ins-hz ${tchTone === 'bull' && adx >= 25 ? 'major' : tchTone === 'bear' ? 'medium' : 'minor'}">
          <div class="ins-hz-h">📈 POSITION<span class="impact">${tchTone === 'bull' && adx >= 25 ? 'MAJOR' : tchTone === 'bear' ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${tchTone === 'bull' && adx >= 25 ? `Strong trend (ADX ${adx.toFixed(0)}) supports multi-week holds. ${trendAge || ''}.` : tchTone === 'bear' ? 'Bearish trend — Position longs require structure flip first.' : 'No clear directional trend — Position trades risky.'}</div>
        </div>
        <div class="ins-hz ${T.above_200sma && tchTone === 'bull' ? 'major' : !T.above_200sma ? 'medium' : 'minor'}">
          <div class="ins-hz-h">🚀 INVEST<span class="impact">${T.above_200sma && tchTone === 'bull' ? 'MAJOR' : !T.above_200sma ? 'MEDIUM' : 'MINOR'}</span></div>
          <div class="ins-hz-t">${T.above_200sma ? 'Above 200 SMA = Stage 2 long-term uptrend. Technical floor in place for buy-and-hold.' : 'Below 200 SMA = caution for long-term holds. Pair with strong fundamentals or wait for reclaim.'}</div>
        </div>
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }
