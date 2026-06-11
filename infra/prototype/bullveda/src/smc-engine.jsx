// smc-engine.jsx — Smart Money Concepts, LuxAlgo algorithm ported to JS
// ---------------------------------------------------------------------
// Faithful port of the LuxAlgo "Smart Money Concepts" Pine v5 indicator
// (CC BY-NC-SA 4.0, © LuxAlgo). Pure compute — no rendering. Consumed by
// the Chart lens (BigChart) which draws the primitives onto its own SVG.
//
//   leg() / getCurrentStructure()  -> swing + internal pivots
//   displayStructure()             -> BOS / CHoCH (swing + internal trends)
//   storeOrderBlock()/deleteOB()   -> volatility-parsed OB boxes + mitigation
//   drawFairValueGaps()            -> 3-candle FVG + mitigation
//   EQH / EQL, trailing extremes (Strong/Weak H-L), premium/discount zones
//
// bars: array of { o|open, hi|high, lo|low, c|close } — newest LAST.
// opts: { swingLen, intLen, eqLen, eqThresh, obMitClose, eq, swings }
// returns: { swingStruct, intStruct, swingPts, equal, swingOB, intOB, fvg,
//            candTrend, trailing, swTrend, inTrend, atr }

const SMC_BULLISH_LEG = 1, SMC_BEARISH_LEG = 0;
const SMC_BULLISH = 1, SMC_BEARISH = -1;
const SMC_BOS = "BOS", SMC_CHOCH = "CHoCH";

function computeSMC(bars, opt) {
  opt = opt || {};
  const swingLen = opt.swingLen || 20;
  const intLen = opt.intLen || 5;
  const eqLen = opt.eqLen || 3;
  const eqThresh = opt.eqThresh != null ? opt.eqThresh : 0.1;
  const obMitClose = !!opt.obMitClose;
  const wantEq = opt.eq !== false;
  const wantSwings = !!opt.swings;

  const n = bars.length;
  const out = {
    swingStruct: [], intStruct: [], swingPts: [], equal: [],
    swingOB: [], intOB: [], fvg: [], candTrend: new Array(n).fill(0),
    trailing: null, swTrend: 0, inTrend: 0, atr: [], ok: false
  };
  if (n < swingLen + 3) return out;

  const O = bars.map(b => +(b.o != null ? b.o : b.open));
  const H = bars.map(b => +(b.hi != null ? b.hi : b.high));
  const L = bars.map(b => +(b.lo != null ? b.lo : b.low));
  const C = bars.map(b => +(b.c != null ? b.c : b.close));

  // ── volatility measure: ATR(min(200,n)) (simple TR mean) ──
  const atrWin = Math.min(200, n);
  const TR = new Array(n);
  for (let i = 0; i < n; i++) {
    TR[i] = i === 0 ? H[i] - L[i]
      : Math.max(H[i] - L[i], Math.abs(H[i] - C[i - 1]), Math.abs(L[i] - C[i - 1]));
  }
  const atr = new Array(n).fill(0);
  { let run = 0; for (let i = 0; i < n; i++) { run += TR[i]; if (i >= atrWin) run -= TR[i - atrWin]; atr[i] = run / Math.min(i + 1, atrWin); } }
  out.atr = atr;

  // ── volatility-parsed highs/lows (LuxAlgo inverts on high-vol bars) ──
  const pHigh = new Array(n), pLow = new Array(n);
  for (let i = 0; i < n; i++) {
    const hv = (H[i] - L[i]) >= 2 * atr[i];
    pHigh[i] = hv ? L[i] : H[i];
    pLow[i] = hv ? H[i] : L[i];
  }

  // ── leg series: high[size] > highest(size) → bearish leg, etc. ──
  function legSeries(size) {
    const leg = new Array(n).fill(0); let cur = 0;
    for (let i = 0; i < n; i++) {
      if (i >= size) {
        let hh = -Infinity, ll = Infinity;
        for (let j = i - size + 1; j <= i; j++) { if (H[j] > hh) hh = H[j]; if (L[j] < ll) ll = L[j]; }
        if (H[i - size] > hh) cur = SMC_BEARISH_LEG;
        else if (L[i - size] < ll) cur = SMC_BULLISH_LEG;
      }
      leg[i] = cur;
    }
    return leg;
  }
  const swingLeg = legSeries(swingLen);
  const intLeg = legSeries(intLen);
  const eqLeg = wantEq ? legSeries(eqLen) : null;

  // ── pivot state ──
  const mk = () => ({ level: NaN, last: NaN, crossed: false, idx: -1, prevLevel: NaN });
  const swH = mk(), swL = mk(), inH = mk(), inL = mk(), eqH = mk(), eqL = mk();
  let swTrend = 0, inTrend = 0;
  const trailing = { top: H[0], bottom: L[0], idx: 0, topIdx: 0, botIdx: 0 };

  function pushOB(list, ob) { list.unshift(ob); if (list.length > 120) list.pop(); }
  function storeOB(list, pivotIdx, bias, internal) {
    if (pivotIdx < 0 || pivotIdx >= n) return;
    let chosen = pivotIdx, best = bias === SMC_BEARISH ? -Infinity : Infinity;
    for (let j = pivotIdx; j < n; j++) {
      if (bias === SMC_BEARISH) { if (pHigh[j] > best) { best = pHigh[j]; chosen = j; } }
      else { if (pLow[j] < best) { best = pLow[j]; chosen = j; } }
    }
    pushOB(list, { high: pHigh[chosen], low: pLow[chosen], idx: chosen, bias, internal, mitIdx: -1 });
  }

  // getCurrentStructure: record pivots + (swing) labels + trailing reset
  function structureUpdate(i, leg, pHi, pLo, internal, equalMode) {
    if (i === 0) return;
    const change = leg[i] - leg[i - 1];
    if (change === 0) return;
    const size = equalMode ? eqLen : (internal ? intLen : swingLen);
    const pIdx = i - size; if (pIdx < 0) return;
    if (change === +1) { // start of bullish leg → pivot LOW
      const lvl = L[pIdx];
      if (equalMode) {
        if (!isNaN(pLo.level) && Math.abs(pLo.level - lvl) < eqThresh * atr[i])
          out.equal.push({ fromIdx: pLo.idx, toIdx: pIdx, level: lvl, tag: "EQL" });
      }
      pLo.last = pLo.level; pLo.level = lvl; pLo.crossed = false; pLo.idx = pIdx;
      if (!internal && !equalMode) {
        trailing.bottom = lvl; trailing.botIdx = pIdx; trailing.idx = pIdx;
        if (wantSwings) out.swingPts.push({ idx: pIdx, level: lvl, tag: lvl < pLo.last ? "LL" : "HL", up: true });
      }
    } else if (change === -1) { // start of bearish leg → pivot HIGH
      const lvl = H[pIdx];
      if (equalMode) {
        if (!isNaN(pHi.level) && Math.abs(pHi.level - lvl) < eqThresh * atr[i])
          out.equal.push({ fromIdx: pHi.idx, toIdx: pIdx, level: lvl, tag: "EQH" });
      }
      pHi.last = pHi.level; pHi.level = lvl; pHi.crossed = false; pHi.idx = pIdx;
      if (!internal && !equalMode) {
        trailing.top = lvl; trailing.topIdx = pIdx; trailing.idx = pIdx;
        if (wantSwings) out.swingPts.push({ idx: pIdx, level: lvl, tag: lvl > pHi.last ? "HH" : "LH", up: false });
      }
    }
  }

  // displayStructure: ta.crossover/under on pivot levels → BOS/CHoCH + OB
  function detectBreak(i, pHi, pLo, internal) {
    if (i === 0) return;
    if (!isNaN(pHi.level) && !pHi.crossed) {
      const crossed = C[i] > pHi.level && C[i - 1] <= pHi.prevLevel;
      const extra = internal ? (inH.level !== swH.level) : true;
      if (crossed && extra) {
        const tag = (internal ? inTrend : swTrend) === SMC_BEARISH ? SMC_CHOCH : SMC_BOS;
        pHi.crossed = true;
        if (internal) inTrend = SMC_BULLISH; else swTrend = SMC_BULLISH;
        (internal ? out.intStruct : out.swingStruct).push({ fromIdx: pHi.idx, level: pHi.level, toIdx: i, tag, dir: "up", internal });
        storeOB(internal ? out.intOB : out.swingOB, pHi.idx, SMC_BULLISH, internal);
      }
    }
    if (!isNaN(pLo.level) && !pLo.crossed) {
      const crossed = C[i] < pLo.level && C[i - 1] >= pLo.prevLevel;
      const extra = internal ? (inL.level !== swL.level) : true;
      if (crossed && extra) {
        const tag = (internal ? inTrend : swTrend) === SMC_BULLISH ? SMC_CHOCH : SMC_BOS;
        pLo.crossed = true;
        if (internal) inTrend = SMC_BEARISH; else swTrend = SMC_BEARISH;
        (internal ? out.intStruct : out.swingStruct).push({ fromIdx: pLo.idx, level: pLo.level, toIdx: i, tag, dir: "down", internal });
        storeOB(internal ? out.intOB : out.swingOB, pLo.idx, SMC_BEARISH, internal);
      }
    }
    pHi.prevLevel = pHi.level; pLo.prevLevel = pLo.level;
  }

  function mitigateOB(list, i) {
    const srcHi = obMitClose ? C[i] : H[i];
    const srcLo = obMitClose ? C[i] : L[i];
    for (let k = list.length - 1; k >= 0; k--) {
      const ob = list[k]; if (ob.mitIdx >= 0) continue;
      if (ob.bias === SMC_BEARISH && srcHi > ob.high) ob.mitIdx = i;
      else if (ob.bias === SMC_BULLISH && srcLo < ob.low) ob.mitIdx = i;
    }
  }

  function detectFVG(i) {
    const bull = L[i] > H[i - 2] && C[i - 1] > H[i - 2];
    const bear = H[i] < L[i - 2] && C[i - 1] < L[i - 2];
    if (bull) out.fvg.push({ top: L[i], bottom: H[i - 2], bias: SMC_BULLISH, idx: i, mitIdx: -1 });
    if (bear) out.fvg.push({ top: H[i - 2], bottom: L[i], bias: SMC_BEARISH, idx: i, mitIdx: -1 });
    for (const g of out.fvg) {
      if (g.mitIdx >= 0) continue;
      if (g.bias === SMC_BULLISH && L[i] < g.bottom) g.mitIdx = i;
      else if (g.bias === SMC_BEARISH && H[i] > g.top) g.mitIdx = i;
    }
  }

  // ── main bar loop ──
  for (let i = 0; i < n; i++) {
    structureUpdate(i, swingLeg, swH, swL, false, false);
    structureUpdate(i, intLeg, inH, inL, true, false);
    if (wantEq) structureUpdate(i, eqLeg, eqH, eqL, false, true);

    detectBreak(i, swH, swL, false);
    detectBreak(i, inH, inL, true);

    if (H[i] >= trailing.top) { trailing.top = H[i]; trailing.topIdx = i; }
    if (L[i] <= trailing.bottom) { trailing.bottom = L[i]; trailing.botIdx = i; }

    mitigateOB(out.swingOB, i);
    mitigateOB(out.intOB, i);
    if (opt.fvg !== false && i >= 2) detectFVG(i);

    out.candTrend[i] = inTrend;
  }

  out.swTrend = swTrend; out.inTrend = inTrend; out.trailing = trailing; out.ok = true;
  return out;
}

window.computeSMC = computeSMC;
