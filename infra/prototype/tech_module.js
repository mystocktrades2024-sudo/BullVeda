// ════════════════════════════════════════════════════════════════════════
// tech_module.js — RichTechChart namespace
// ════════════════════════════════════════════════════════════════════════
// Ported from kairos-detail-rebuild.html on 2026-05-13. Wrapped as a single
// global `window.RichTechChart` so kairos.html Detail page → Technicals
// sub-tab can call .init(containerId, ticker, options) after innerHTML
// commits — matches the post-render pattern used by Patterns sub-tab.
// ════════════════════════════════════════════════════════════════════════

window.RichTechChart = (function() {
  'use strict';

  // ─── Indicator math · pure functions · zero deps ──────────────────────
  function emaSeries(bars, period) {
    if (!bars || !bars.length) return [];
    const k = 2 / (period + 1);
    let ema = bars[0].c;
    const out = [];
    for (const b of bars) { ema = b.c * k + ema * (1 - k); out.push(+ema.toFixed(4)); }
    return out;
  }
  function smaSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    let sum = 0;
    for (let i = 0; i < bars.length; i++) {
      sum += bars[i].c;
      if (i >= period) sum -= bars[i - period].c;
      if (i >= period - 1) out[i] = +(sum / period).toFixed(4);
    }
    return out;
  }
  function atrSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    const trs = bars.map((b, i) => {
      if (i === 0) return b.h - b.l;
      const pc = bars[i - 1].c;
      return Math.max(b.h - b.l, Math.abs(b.h - pc), Math.abs(b.l - pc));
    });
    let sum = 0;
    for (let i = 0; i < trs.length; i++) {
      if (i < period) { sum += trs[i]; if (i === period - 1) out[i] = sum / period; }
      else            { out[i] = (out[i - 1] * (period - 1) + trs[i]) / period; }
    }
    return out;
  }
  function bbSeries(bars, period, mult) {
    const mid = smaSeries(bars, period);
    const upper = new Array(bars.length).fill(null);
    const lower = new Array(bars.length).fill(null);
    for (let i = period - 1; i < bars.length; i++) {
      let sumSq = 0;
      for (let j = i - period + 1; j <= i; j++) sumSq += Math.pow(bars[j].c - mid[i], 2);
      const sd = Math.sqrt(sumSq / period);
      upper[i] = mid[i] + mult * sd;
      lower[i] = mid[i] - mult * sd;
    }
    return { mid, upper, lower };
  }
  function keltnerSeries(bars, period, mult) {
    const mid = emaSeries(bars, period);
    const atr = atrSeries(bars, period);
    const upper = mid.map((m, i) => atr[i] != null ? m + mult * atr[i] : null);
    const lower = mid.map((m, i) => atr[i] != null ? m - mult * atr[i] : null);
    return { mid, upper, lower };
  }
  function donchianSeries(bars, period) {
    const upper = new Array(bars.length).fill(null);
    const lower = new Array(bars.length).fill(null);
    const mid   = new Array(bars.length).fill(null);
    for (let i = period - 1; i < bars.length; i++) {
      let hi = -Infinity, lo = Infinity;
      for (let j = i - period + 1; j <= i; j++) {
        if (bars[j].h > hi) hi = bars[j].h;
        if (bars[j].l < lo) lo = bars[j].l;
      }
      upper[i] = hi; lower[i] = lo; mid[i] = (hi + lo) / 2;
    }
    return { upper, lower, mid };
  }
  function ichimokuSeries(bars) {
    const N = bars.length;
    const tenkan = new Array(N).fill(null);
    const kijun  = new Array(N).fill(null);
    const senkouA = new Array(N + 26).fill(null);
    const senkouB = new Array(N + 26).fill(null);
    const chikou = new Array(N).fill(null);
    const periodMid = (i, p) => {
      if (i < p - 1) return null;
      let hi = -Infinity, lo = Infinity;
      for (let j = i - p + 1; j <= i; j++) {
        if (bars[j].h > hi) hi = bars[j].h;
        if (bars[j].l < lo) lo = bars[j].l;
      }
      return (hi + lo) / 2;
    };
    for (let i = 0; i < N; i++) {
      tenkan[i] = periodMid(i, 9);
      kijun[i]  = periodMid(i, 26);
      if (tenkan[i] != null && kijun[i] != null) senkouA[i + 26] = (tenkan[i] + kijun[i]) / 2;
      const sb = periodMid(i, 52);
      if (sb != null) senkouB[i + 26] = sb;
      if (i + 26 < N) chikou[i] = bars[i + 26] ? bars[i + 26].c : null;
    }
    return { tenkan, kijun, senkouA, senkouB, chikou };
  }
  function rsiSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    let avgGain = 0, avgLoss = 0;
    for (let i = 1; i < bars.length; i++) {
      const ch = bars[i].c - bars[i - 1].c;
      const gain = ch > 0 ? ch : 0, loss = ch < 0 ? -ch : 0;
      if (i <= period) { avgGain += gain; avgLoss += loss;
        if (i === period) { avgGain /= period; avgLoss /= period;
          out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss); }
      } else {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
      }
    }
    return out;
  }
  function macdSeries(bars) {
    const fast = emaSeries(bars, 12);
    const slow = emaSeries(bars, 26);
    const macd = bars.map((_, i) => fast[i] - slow[i]);
    const k = 2 / 10, sig = new Array(macd.length).fill(0);
    sig[0] = macd[0];
    for (let i = 1; i < macd.length; i++) sig[i] = macd[i] * k + sig[i - 1] * (1 - k);
    const hist = macd.map((m, i) => m - sig[i]);
    return { macd, signal: sig, hist };
  }
  function stochRsiSeries(bars, period) {
    const rsi = rsiSeries(bars, period);
    const out = new Array(bars.length).fill(null);
    for (let i = period * 2; i < bars.length; i++) {
      let hi = -Infinity, lo = Infinity;
      for (let j = i - period + 1; j <= i; j++) {
        if (rsi[j] == null) continue;
        if (rsi[j] > hi) hi = rsi[j];
        if (rsi[j] < lo) lo = rsi[j];
      }
      if (hi !== -Infinity && lo !== Infinity && hi > lo) out[i] = (rsi[i] - lo) / (hi - lo) * 100;
    }
    return out;
  }
  function vwapSession(bars) {
    const out = new Array(bars.length).fill(null);
    let cumPV = 0, cumV = 0;
    for (let i = 0; i < bars.length; i++) {
      const tp = (bars[i].h + bars[i].l + bars[i].c) / 3;
      cumPV += tp * bars[i].v; cumV += bars[i].v;
      out[i] = cumPV / cumV;
    }
    return out;
  }
  function supertrendSeries(bars, period, mult) {
    const atr = atrSeries(bars, period);
    const upper = new Array(bars.length).fill(null);
    const lower = new Array(bars.length).fill(null);
    const dir   = new Array(bars.length).fill(1);
    const st    = new Array(bars.length).fill(null);
    for (let i = 0; i < bars.length; i++) {
      if (atr[i] == null) continue;
      const hl2 = (bars[i].h + bars[i].l) / 2;
      upper[i] = hl2 + mult * atr[i];
      lower[i] = hl2 - mult * atr[i];
      if (i > 0 && upper[i - 1] != null) {
        if (bars[i - 1].c > upper[i - 1]) upper[i] = Math.min(upper[i], upper[i - 1]);
        if (bars[i - 1].c < lower[i - 1]) lower[i] = Math.max(lower[i], lower[i - 1]);
        dir[i] = bars[i].c > upper[i - 1] ? 1 : (bars[i].c < lower[i - 1] ? -1 : dir[i - 1]);
      }
      st[i] = dir[i] === 1 ? lower[i] : upper[i];
    }
    return { st, dir };
  }
  function psarSeries(bars, step, max) {
    const sar = new Array(bars.length).fill(null);
    let trend = 1, ep = bars[0].h, af = step, prevSar = bars[0].l;
    for (let i = 1; i < bars.length; i++) {
      let s = prevSar + af * (ep - prevSar);
      if (trend === 1) {
        if (bars[i].l < s) { trend = -1; s = ep; ep = bars[i].l; af = step; }
        else if (bars[i].h > ep) { ep = bars[i].h; af = Math.min(max, af + step); }
      } else {
        if (bars[i].h > s) { trend = 1; s = ep; ep = bars[i].h; af = step; }
        else if (bars[i].l < ep) { ep = bars[i].l; af = Math.min(max, af + step); }
      }
      sar[i] = s; prevSar = s;
    }
    return sar;
  }
  function obvSeries(bars) {
    const out = [0];
    for (let i = 1; i < bars.length; i++) {
      const prev = out[i - 1];
      out.push(bars[i].c > bars[i - 1].c ? prev + bars[i].v : bars[i].c < bars[i - 1].c ? prev - bars[i].v : prev);
    }
    return out;
  }
  function cmfSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    for (let i = period - 1; i < bars.length; i++) {
      let mfv = 0, vSum = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const b = bars[j];
        if (b.h === b.l) continue;
        mfv += ((b.c - b.l - (b.h - b.c)) / (b.h - b.l)) * b.v;
        vSum += b.v;
      }
      out[i] = vSum ? mfv / vSum : null;
    }
    return out;
  }
  function adxSeries(bars, period) {
    const N = bars.length;
    const tr = new Array(N).fill(0);
    const pdm = new Array(N).fill(0);
    const ndm = new Array(N).fill(0);
    for (let i = 1; i < N; i++) {
      const upMove = bars[i].h - bars[i - 1].h;
      const dnMove = bars[i - 1].l - bars[i].l;
      pdm[i] = upMove > dnMove && upMove > 0 ? upMove : 0;
      ndm[i] = dnMove > upMove && dnMove > 0 ? dnMove : 0;
      tr[i]  = Math.max(bars[i].h - bars[i].l, Math.abs(bars[i].h - bars[i - 1].c), Math.abs(bars[i].l - bars[i - 1].c));
    }
    const smooth = (arr) => {
      const out = new Array(N).fill(null);
      let sum = 0;
      for (let i = 1; i <= period; i++) sum += arr[i];
      out[period] = sum;
      for (let i = period + 1; i < N; i++) out[i] = out[i - 1] - out[i - 1] / period + arr[i];
      return out;
    };
    const trS = smooth(tr), pdmS = smooth(pdm), ndmS = smooth(ndm);
    const dx = new Array(N).fill(null);
    for (let i = period; i < N; i++) {
      if (!trS[i]) continue;
      const pdi = 100 * pdmS[i] / trS[i];
      const ndi = 100 * ndmS[i] / trS[i];
      dx[i] = (pdi + ndi) ? 100 * Math.abs(pdi - ndi) / (pdi + ndi) : null;
    }
    const adx = new Array(N).fill(null);
    let sum = 0;
    for (let i = period; i < N && i < period * 2; i++) sum += (dx[i] || 0);
    adx[period * 2 - 1] = sum / period;
    for (let i = period * 2; i < N; i++) adx[i] = (adx[i - 1] * (period - 1) + (dx[i] || 0)) / period;
    return adx;
  }
  function cciSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    const tp = bars.map(b => (b.h + b.l + b.c) / 3);
    for (let i = period - 1; i < bars.length; i++) {
      let mean = 0; for (let j = i - period + 1; j <= i; j++) mean += tp[j]; mean /= period;
      let md = 0;   for (let j = i - period + 1; j <= i; j++) md   += Math.abs(tp[j] - mean); md /= period;
      out[i] = md ? (tp[i] - mean) / (0.015 * md) : null;
    }
    return out;
  }
  function mfiSeries(bars, period) {
    const out = new Array(bars.length).fill(null);
    const tp = bars.map(b => (b.h + b.l + b.c) / 3);
    for (let i = period; i < bars.length; i++) {
      let pf = 0, nf = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const rmf = tp[j] * bars[j].v;
        if (tp[j] > tp[j - 1]) pf += rmf; else if (tp[j] < tp[j - 1]) nf += rmf;
      }
      out[i] = nf === 0 ? 100 : 100 - 100 / (1 + pf / nf);
    }
    return out;
  }
  function linregChannel(bars, period) {
    if (bars.length < period) return null;
    const start = bars.length - period;
    let sx = 0, sy = 0, sxy = 0, sxx = 0;
    for (let i = 0; i < period; i++) { sx += i; sy += bars[start + i].c; sxy += i * bars[start + i].c; sxx += i * i; }
    const slope = (period * sxy - sx * sy) / (period * sxx - sx * sx);
    const intercept = (sy - slope * sx) / period;
    let sse = 0;
    for (let i = 0; i < period; i++) { const e = bars[start + i].c - (slope * i + intercept); sse += e * e; }
    const se = Math.sqrt(sse / period);
    return { startIdx: start, slope, intercept, se };
  }
  function swingPivots(bars, lookback) {
    const lb = lookback || 3;
    const pivots = [];
    for (let i = lb; i < bars.length - lb; i++) {
      let isHigh = true, isLow = true;
      for (let j = 1; j <= lb; j++) {
        if (bars[i - j].h >= bars[i].h || bars[i + j].h >= bars[i].h) isHigh = false;
        if (bars[i - j].l <= bars[i].l || bars[i + j].l <= bars[i].l) isLow  = false;
      }
      if (isHigh) pivots.push({ idx: i, type: 'high', price: bars[i].h });
      if (isLow)  pivots.push({ idx: i, type: 'low',  price: bars[i].l });
    }
    let lastHi = null, lastLo = null;
    for (const p of pivots) {
      if (p.type === 'high') { p.tag = lastHi == null ? 'H' : (p.price > lastHi ? 'HH' : 'LH'); lastHi = p.price; }
      else                    { p.tag = lastLo == null ? 'L' : (p.price > lastLo ? 'HL' : 'LL'); lastLo = p.price; }
    }
    return pivots;
  }

  // ─── Synthetic OHLC fallback (anchored to ticker spot + 52w range) ────
  function generateSyntheticOHLC(ticker, spot, wkHi, wkLo) {
    let seed = 0;
    for (let i = 0; i < (ticker || '').length; i++) seed = (seed * 31 + ticker.charCodeAt(i)) % 100000;
    const rng = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
    const data = [];
    const today = new Date();
    const peakIdx = 48, troughIdx = 70;
    const peak = wkHi * 0.99;
    const trough = wkLo + (peak - wkLo) * 0.45;
    let last = wkLo + (rng() - 0.5) * 2;
    for (let i = 89; i >= 0; i--) {
      const d = new Date(today); d.setDate(today.getDate() - i);
      const idx = 89 - i;
      let target;
      if (idx < peakIdx)        target = wkLo + (peak - wkLo) * (idx / peakIdx);
      else if (idx < troughIdx) target = peak - (peak - trough) * ((idx - peakIdx) / (troughIdx - peakIdx));
      else                       target = trough + (spot - trough) * ((idx - troughIdx) / (89 - troughIdx));
      const noise = (rng() - 0.5) * (spot * 0.012);
      const c = +(target + noise).toFixed(2);
      const o = +(last + (rng() - 0.5) * (spot * 0.008)).toFixed(2);
      const h = +(Math.max(o, c) + rng() * (spot * 0.008) + 0.2).toFixed(2);
      const l = +(Math.min(o, c) - rng() * (spot * 0.008) - 0.2).toFixed(2);
      const v = Math.round(20e6 + rng() * 50e6 + (Math.abs(c - o) > spot * 0.008 ? 20e6 : 0));
      data.push({ d: d.toISOString().slice(0, 10), o, h, l, c, v });
      last = c;
    }
    return data;
  }

  // ─── Default overlay state ────────────────────────────────────────────
  function defaultOverlays() {
    return {
      ema8: true, ema13: true, ema20: true, ema50: true, ema100: true, ema200: true,
      sma50: false, sma200: false,
      bb: false, keltner: false, donchian: false, atrband: false, squeeze: false,
      tenkan: false, kijun: false, cloud: false, chikou: false,
      supertrend: false, psar: false, linreg: false,
      ob: true, obBear: true, fvg: true, liquidity: false, bos: false, hhll: false,
      vwap: false, avwapYtd: true, avwapER: true, avwap52L: true,
      pivWk: true, pivCam: false, pivFib: false,
      fib: true, fibExt: false, fibTime: false,
      rsi: false, macd: false, stochrsi: false, adx: false, cci: false, mfi: false,
      vol: true, volProf: false, obv: false, cmf: false,
    };
  }

  // ─── Main render — produces inline SVG into the container ─────────────
  function renderRichLadder(state) {
    const host = state.host;
    if (!host) return;
    const bars = state.bars;
    if (!bars || !bars.length) { host.innerHTML = ''; return; }
    const O = state.overlays;

    const oscEnabled = ['rsi','macd','stochrsi','adx','cci','mfi'].filter(k => O[k]);
    const oscPaneH   = oscEnabled.length ? Math.min(280, oscEnabled.length * 90) : 0;
    const W = host.clientWidth || 880;
    const padL = 8, padR = 82, padT = 12, padB = 28;
    const volH = O.vol ? 70 : 0;
    const priceH = 480;
    const H = padT + priceH + (volH ? volH + 8 : 0) + (oscPaneH ? oscPaneH + 8 : 0) + padB;
    const priceTop = padT;
    const priceBot = padT + priceH;
    const volTop = priceBot + 8;
    const volBot = volTop + volH;
    const oscTop = (volH ? volBot : priceBot) + 8;
    const oscBot = oscTop + oscPaneH;
    const plotW = W - padL - padR;

    let priceMin = Math.min(...bars.map(b => b.l));
    let priceMax = Math.max(...bars.map(b => b.h));
    const plan = state.plan;
    [plan.t1, plan.t2, plan.stop, plan.entryLo, plan.entryHi].forEach(p => {
      if (p != null && p > 0) {
        if (p < priceMin) priceMin = p;
        if (p > priceMax) priceMax = p;
      }
    });
    const pad = (priceMax - priceMin) * 0.04;
    priceMin -= pad; priceMax += pad;

    const volMax = Math.max(...bars.map(b => b.v));
    const xOf = i => padL + (plotW / bars.length) * (i + 0.5);
    const yOfPrice = p => priceTop + (priceMax - p) / (priceMax - priceMin) * priceH;
    const yOfVol = v => volBot - (v / volMax) * volH;
    const barW = plotW / bars.length;
    const bodyW = Math.max(2, barW * 0.7);

    const ind = {
      ema8:  emaSeries(bars, 8),
      ema13: emaSeries(bars, 13),
      ema20: emaSeries(bars, 20),
      ema50: emaSeries(bars, 50),
      ema100: emaSeries(bars, 100),
      ema200: emaSeries(bars, 200),
      sma50: smaSeries(bars, 50),
      sma200: smaSeries(bars, 200),
      bb: (O.bb || O.squeeze) ? bbSeries(bars, 20, 2) : null,
      kc: (O.keltner || O.squeeze) ? keltnerSeries(bars, 20, 1.5) : null,
      dc: O.donchian ? donchianSeries(bars, 20) : null,
      atr: atrSeries(bars, 14),
      ichi: (O.tenkan || O.kijun || O.cloud || O.chikou) ? ichimokuSeries(bars) : null,
      st: O.supertrend ? supertrendSeries(bars, 10, 3) : null,
      psar: O.psar ? psarSeries(bars, 0.02, 0.2) : null,
      vwap: O.vwap ? vwapSession(bars) : null,
      obv: O.obv ? obvSeries(bars) : null,
      cmf: O.cmf ? cmfSeries(bars, 20) : null,
      rsi: O.rsi ? rsiSeries(bars, 14) : null,
      macd: O.macd ? macdSeries(bars) : null,
      stoch: O.stochrsi ? stochRsiSeries(bars, 14) : null,
      adx: O.adx ? adxSeries(bars, 14) : null,
      cci: O.cci ? cciSeries(bars, 20) : null,
      mfi: O.mfi ? mfiSeries(bars, 14) : null,
      pivots: O.hhll || O.bos || O.liquidity ? swingPivots(bars, 3) : null,
      linreg: O.linreg ? linregChannel(bars, 30) : null,
    };

    const lastClose = bars[bars.length - 1].c;
    const avwaps = state.avwaps || [
      { key: 'avwapYtd', price: lastClose * 0.92, color: '#22d3ee', label: 'aVWAP YTD' },
      { key: 'avwapER',  price: lastClose * 0.88, color: '#60a5fa', label: 'aVWAP last ER' },
      { key: 'avwap52L', price: lastClose * 0.78, color: '#818cf8', label: 'aVWAP 52w-low' },
    ];
    const orderBlocks = state.orderBlocks || [
      { type: 'bullish', low: lastClose * 0.88, high: lastClose * 0.90, status: 'fresh',  label: 'Bull OB' },
      { type: 'bullish', low: lastClose * 0.85, high: lastClose * 0.86, status: 'tested', label: 'Bull OB · swept' },
      { type: 'bearish', low: lastClose * 1.03, high: lastClose * 1.04, status: 'fresh',  label: 'Bear OB · 52W' },
    ];
    const fvgs = state.fvgs || [
      { low: lastClose * 0.93, high: lastClose * 0.94, label: 'FVG above' },
      { low: lastClose * 0.89, high: lastClose * 0.895, label: 'FVG below · OB cluster' },
    ];
    const wkPivots = state.wkPivots || [
      { key: 'pivWk', price: lastClose * 1.025, label: 'Wk R1', color: '#5d6878' },
      { key: 'pivWk', price: lastClose * 0.985, label: 'Wk Pivot', color: '#7a8693' },
      { key: 'pivWk', price: lastClose * 0.935, label: 'Wk S1', color: '#5d6878' },
    ];

    const fibHi = Math.max(...bars.map(b => b.h));
    const fibLo = Math.min(...bars.map(b => b.l));
    const fibRet = [
      { f: 0.236, color: 'rgba(167,139,250,0.45)' },
      { f: 0.382, color: 'rgba(167,139,250,0.85)', star: true },
      { f: 0.500, color: 'rgba(167,139,250,0.85)', star: true },
      { f: 0.618, color: 'rgba(167,139,250,0.85)', star: true },
      { f: 0.786, color: 'rgba(167,139,250,0.45)' },
    ];

    const polyLine = (pts, color, w = 1.5, opacity = 0.95, dash = '') =>
      `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="${w}" opacity="${opacity}" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
    const seriesPath = (series, color, w = 1.5, opacity = 0.95, startFrom = 0, dash = '') => {
      const pts = [];
      for (let i = startFrom; i < bars.length; i++) {
        if (series[i] == null || !isFinite(series[i])) continue;
        pts.push(`${xOf(i)},${yOfPrice(series[i])}`);
      }
      if (pts.length < 2) return '';
      return polyLine(pts, color, w, opacity, dash);
    };

    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" xmlns="http://www.w3.org/2000/svg" style="display:block">`;
    svg += `<rect width="${W}" height="${H}" fill="#0f1318"/>`;

    for (let t = 0; t <= 6; t++) {
      const price = priceMax - (priceMax - priceMin) * (t / 6);
      const y = priceTop + (priceH * t / 6);
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#1f2733" stroke-width="0.5"/>`;
      svg += `<text x="${W - padR + 4}" y="${y + 4}" font-family="ui-monospace,Menlo" font-size="10" fill="#5d6878">$${price.toFixed(2)}</text>`;
    }
    for (let i = 0; i < bars.length; i += 10) {
      const x = xOf(i);
      svg += `<line x1="${x}" y1="${priceTop}" x2="${x}" y2="${oscPaneH ? oscBot : (volH ? volBot : priceBot)}" stroke="#1f2733" stroke-width="0.5"/>`;
      svg += `<text x="${x}" y="${H - 6}" text-anchor="middle" font-family="ui-monospace,Menlo" font-size="9" fill="#5d6878">${(bars[i].d || '').slice(5)}</text>`;
    }

    if (O.fib) {
      fibRet.forEach(({ f, color, star }) => {
        const price = fibHi - (fibHi - fibLo) * f;
        const y = yOfPrice(price);
        svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${color}" stroke-width="${star ? 1.2 : 0.8}" stroke-dasharray="3,4"/>`;
        svg += `<text x="${padL + 4}" y="${y - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#a78bfa" font-weight="${star ? '700' : '400'}">Fib ${f.toFixed(3)} $${price.toFixed(2)}${star ? ' *' : ''}</text>`;
      });
    }
    if (O.fibExt) {
      [-0.272, -0.618].forEach(f => {
        const price = fibHi - (fibHi - fibLo) * f;
        const y = yOfPrice(price);
        if (y < priceTop || y > priceBot) return;
        const lbl = f === -0.272 ? '1.272' : '1.618';
        svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(167,139,250,0.75)" stroke-width="1" stroke-dasharray="6,3"/>`;
        svg += `<text x="${padL + 4}" y="${y - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#a78bfa" font-weight="700">${lbl} ext $${price.toFixed(2)}</text>`;
      });
    }

    if (O.bb && ind.bb) {
      svg += seriesPath(ind.bb.upper, '#34d399', 1, 0.6, 19);
      svg += seriesPath(ind.bb.mid,   '#34d399', 1, 0.4, 19, '3,3');
      svg += seriesPath(ind.bb.lower, '#34d399', 1, 0.6, 19);
    }
    if (O.keltner && ind.kc) {
      svg += seriesPath(ind.kc.upper, '#fb923c', 1, 0.6, 19);
      svg += seriesPath(ind.kc.lower, '#fb923c', 1, 0.6, 19);
    }
    if (O.donchian && ind.dc) {
      svg += seriesPath(ind.dc.upper, '#94a3b8', 1, 0.7, 19, '4,2');
      svg += seriesPath(ind.dc.lower, '#94a3b8', 1, 0.7, 19, '4,2');
    }
    if (O.atrband && ind.atr) {
      const last = ind.atr[ind.atr.length - 1];
      const ref = bars[bars.length - 1].c;
      if (last != null) {
        const yU = yOfPrice(ref + 1.25 * last);
        const yL = yOfPrice(ref - 1.25 * last);
        svg += `<line x1="${padL}" y1="${yU}" x2="${W - padR}" y2="${yU}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="4,2" opacity="0.85"/>`;
        svg += `<text x="${padL + 4}" y="${yU - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#f59e0b">+1.25 ATR $${(ref + 1.25 * last).toFixed(2)}</text>`;
        svg += `<line x1="${padL}" y1="${yL}" x2="${W - padR}" y2="${yL}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="4,2" opacity="0.85"/>`;
        svg += `<text x="${padL + 4}" y="${yL - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#f59e0b">-1.25 ATR $${(ref - 1.25 * last).toFixed(2)}</text>`;
      }
    }
    if (O.squeeze && ind.bb && ind.kc) {
      for (let i = 19; i < bars.length; i++) {
        if (ind.bb.upper[i] < ind.kc.upper[i] && ind.bb.lower[i] > ind.kc.lower[i]) {
          svg += `<rect x="${xOf(i) - barW / 2}" y="${priceTop}" width="${barW}" height="${priceH}" fill="rgba(253,230,138,0.06)"/>`;
        }
      }
    }
    if (O.cloud && ind.ichi) {
      const A = ind.ichi.senkouA, B = ind.ichi.senkouB;
      for (let i = 0; i < bars.length - 1; i++) {
        if (A[i] == null || B[i] == null) continue;
        const y1 = yOfPrice(A[i]);
        const y2 = yOfPrice(B[i]);
        const color = A[i] > B[i] ? 'rgba(74,222,128,0.10)' : 'rgba(248,113,113,0.10)';
        svg += `<rect x="${xOf(i) - barW/2}" y="${Math.min(y1, y2)}" width="${barW}" height="${Math.abs(y1 - y2)}" fill="${color}"/>`;
      }
      svg += seriesPath(A.slice(0, bars.length), 'rgba(74,222,128,0.7)', 1, 0.7, 0);
      svg += seriesPath(B.slice(0, bars.length), 'rgba(248,113,113,0.7)', 1, 0.7, 0, '3,3');
    }
    if (O.tenkan && ind.ichi) svg += seriesPath(ind.ichi.tenkan, '#fbbf24', 1.4, 0.95, 8);
    if (O.kijun  && ind.ichi) svg += seriesPath(ind.ichi.kijun,  '#22d3ee', 1.4, 0.95, 25);
    if (O.chikou && ind.ichi) svg += seriesPath(ind.ichi.chikou, '#a78bfa', 1, 0.65, 0, '5,3');

    if (O.ob || O.obBear) {
      orderBlocks.forEach(ob => {
        const isBull = ob.type === 'bullish';
        if (isBull && !O.ob) return;
        if (!isBull && !O.obBear) return;
        const isFresh = ob.status === 'fresh';
        const fill = isBull ? `rgba(74,222,128,${isFresh ? 0.20 : 0.12})` : `rgba(248,113,113,${isFresh ? 0.22 : 0.12})`;
        const stroke = isBull ? '#4ade80' : '#f87171';
        const yHi = yOfPrice(ob.high);
        const yLo = yOfPrice(ob.low);
        svg += `<rect x="${padL}" y="${yHi}" width="${plotW}" height="${yLo - yHi}" fill="${fill}" stroke="${stroke}" stroke-width="0.6" stroke-dasharray="3,3"/>`;
        svg += `<text x="${padL + 6}" y="${yHi + 11}" font-family="ui-monospace,Menlo" font-size="9" fill="${stroke}" font-weight="700">${isBull ? '▲' : '▼'} ${ob.label || (isBull ? 'Bull OB' : 'Bear OB')} $${ob.low.toFixed(2)}-${ob.high.toFixed(2)}</text>`;
      });
    }
    if (O.fvg) {
      fvgs.forEach(f => {
        const yHi = yOfPrice(f.high);
        const yLo = yOfPrice(f.low);
        svg += `<rect x="${padL}" y="${yHi}" width="${plotW}" height="${yLo - yHi}" fill="rgba(167,139,250,0.16)" stroke="rgba(167,139,250,0.6)" stroke-width="0.6"/>`;
        svg += `<text x="${W - padR - 130}" y="${(yHi + yLo) / 2 + 3}" font-family="ui-monospace,Menlo" font-size="8.5" fill="#a78bfa" font-weight="700">◇ ${f.label}</text>`;
      });
    }
    if (O.liquidity && ind.pivots) {
      const tol = (priceMax - priceMin) * 0.008;
      const highs = ind.pivots.filter(p => p.type === 'high');
      const lows  = ind.pivots.filter(p => p.type === 'low');
      const findEq = (arr, kind) => {
        for (let i = 0; i < arr.length - 1; i++) {
          for (let j = i + 1; j < arr.length; j++) {
            if (Math.abs(arr[i].price - arr[j].price) <= tol) {
              const y = yOfPrice(arr[i].price);
              svg += `<line x1="${xOf(arr[i].idx)}" y1="${y}" x2="${xOf(arr[j].idx)}" y2="${y}" stroke="#fb923c" stroke-width="1.2" stroke-dasharray="2,2"/>`;
              svg += `<text x="${xOf(arr[j].idx) + 4}" y="${y - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#fb923c" font-weight="700">${kind} liq $${arr[i].price.toFixed(2)}</text>`;
              i = j; break;
            }
          }
        }
      };
      findEq(highs, 'EQH'); findEq(lows, 'EQL');
    }
    if (O.bos && ind.pivots) {
      const highs = ind.pivots.filter(p => p.type === 'high');
      let lastH = null;
      highs.forEach(p => {
        if (lastH && p.price > lastH.price) {
          for (let i = lastH.idx + 1; i < bars.length; i++) {
            if (bars[i].c > lastH.price) {
              const y = yOfPrice(lastH.price);
              svg += `<line x1="${xOf(lastH.idx)}" y1="${y}" x2="${xOf(i)}" y2="${y}" stroke="#10b981" stroke-width="1.5" stroke-dasharray="3,2"/>`;
              svg += `<text x="${xOf(i) + 2}" y="${y - 4}" font-family="ui-monospace,Menlo" font-size="9" fill="#10b981" font-weight="700">BoS ↑</text>`;
              break;
            }
          }
        }
        lastH = p;
      });
    }
    if (O.hhll && ind.pivots) {
      ind.pivots.forEach(p => {
        const y = yOfPrice(p.price);
        const x = xOf(p.idx);
        const color = p.tag.startsWith('H') ? '#4ade80' : '#f87171';
        svg += `<text x="${x}" y="${y + (p.type === 'high' ? -6 : 12)}" text-anchor="middle" font-family="ui-monospace,Menlo" font-size="9" fill="${color}" font-weight="700">${p.tag}</text>`;
      });
    }

    if (O.vwap && ind.vwap) svg += seriesPath(ind.vwap, '#facc15', 1.3, 0.85);
    avwaps.forEach(av => {
      if (!O[av.key]) return;
      const y = yOfPrice(av.price);
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${av.color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.7"/>`;
      svg += `<text x="${W - padR - 180}" y="${y - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="${av.color}">${av.label} $${av.price.toFixed(2)}</text>`;
    });
    wkPivots.forEach(pv => {
      if (!O[pv.key]) return;
      const y = yOfPrice(pv.price);
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${pv.color}" stroke-width="0.8" stroke-dasharray="1,4"/>`;
      svg += `<text x="${W - padR - 110}" y="${y - 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#8b96a3">${pv.label} $${pv.price.toFixed(2)}</text>`;
    });

    if (O.vol) {
      bars.forEach((b, i) => {
        const x = xOf(i) - bodyW / 2;
        const y = yOfVol(b.v);
        const color = b.c >= b.o ? 'rgba(74,222,128,0.45)' : 'rgba(248,113,113,0.45)';
        svg += `<rect x="${x}" y="${y}" width="${bodyW}" height="${volBot - y}" fill="${color}"/>`;
      });
      svg += `<line x1="${padL}" y1="${volBot}" x2="${W - padR}" y2="${volBot}" stroke="#2a3441" stroke-width="1"/>`;
      svg += `<text x="${padL + 4}" y="${volTop + 11}" font-family="ui-monospace,Menlo" font-size="9" fill="#5d6878" letter-spacing="0.12em">VOLUME</text>`;
    }
    if (O.volProf) {
      const NBINS = 24;
      const lo = Math.min(...bars.map(b => b.l));
      const hi = Math.max(...bars.map(b => b.h));
      const step = (hi - lo) / NBINS;
      const bins = new Array(NBINS).fill(0);
      bars.forEach(b => {
        const mid = (b.h + b.l) / 2;
        const idx = Math.max(0, Math.min(NBINS - 1, Math.floor((mid - lo) / step)));
        bins[idx] += b.v;
      });
      const maxBin = Math.max(...bins);
      const pocIdx = bins.indexOf(maxBin);
      const pocPx  = lo + (pocIdx + 0.5) * step;
      const vpWidth = 56;
      for (let i = 0; i < NBINS; i++) {
        const price = lo + (i + 0.5) * step;
        const y = yOfPrice(price);
        const w = (bins[i] / maxBin) * vpWidth;
        const color = i === pocIdx ? 'rgba(212,144,96,0.7)' : 'rgba(212,144,96,0.30)';
        svg += `<rect x="${W - padR - w}" y="${y - (priceH / NBINS / 2)}" width="${w}" height="${priceH / NBINS}" fill="${color}"/>`;
      }
      const yPoc = yOfPrice(pocPx);
      svg += `<text x="${W - padR - 4}" y="${yPoc + 3}" text-anchor="end" font-family="ui-monospace,Menlo" font-size="9" fill="#d49060" font-weight="700">POC $${pocPx.toFixed(2)}</text>`;
    }

    const maCfg = [
      { key: 'ema8', period: 8, color: '#22d3ee', series: ind.ema8 },
      { key: 'ema13', period: 13, color: '#60a5fa', series: ind.ema13 },
      { key: 'ema20', period: 20, color: '#818cf8', series: ind.ema20 },
      { key: 'ema50', period: 50, color: '#fbbf24', series: ind.ema50 },
      { key: 'ema100', period: 100, color: '#a78bfa', series: ind.ema100 },
      { key: 'ema200', period: 200, color: '#f87171', series: ind.ema200 },
      { key: 'sma50', period: 50, color: '#fbbf24', series: ind.sma50, dash: '4,2' },
      { key: 'sma200', period: 200, color: '#f87171', series: ind.sma200, dash: '4,2' },
    ];
    maCfg.forEach(m => {
      if (!O[m.key] || !m.series) return;
      const startIdx = m.period - 1;
      const pts = [];
      for (let i = startIdx; i < bars.length; i++) {
        if (m.series[i] == null) continue;
        pts.push(`${xOf(i)},${yOfPrice(m.series[i])}`);
      }
      if (pts.length < 2) return;
      svg += polyLine(pts, m.color, 1.5, 0.9, m.dash || '');
      const lastVal = m.series[m.series.length - 1];
      if (lastVal != null) {
        const lastY = yOfPrice(lastVal);
        const lbl = m.key.startsWith('sma') ? `SMA${m.period}` : `EMA${m.period}`;
        svg += `<text x="${W - padR + 4}" y="${lastY + 3}" font-family="ui-monospace,Menlo" font-size="8.5" fill="${m.color}" font-weight="700">${lbl} ${lastVal.toFixed(2)}</text>`;
      }
    });

    if (O.supertrend && ind.st) {
      const upPts = [], dnPts = [];
      for (let i = 0; i < bars.length; i++) {
        if (ind.st.st[i] == null) continue;
        const pt = `${xOf(i)},${yOfPrice(ind.st.st[i])}`;
        if (ind.st.dir[i] === 1) upPts.push(pt); else dnPts.push(pt);
      }
      if (upPts.length > 1) svg += polyLine(upPts, '#10b981', 1.5, 0.9);
      if (dnPts.length > 1) svg += polyLine(dnPts, '#ef4444', 1.5, 0.9);
    }
    if (O.psar && ind.psar) {
      bars.forEach((_, i) => {
        if (ind.psar[i] == null) return;
        svg += `<circle cx="${xOf(i)}" cy="${yOfPrice(ind.psar[i])}" r="1.5" fill="#a78bfa"/>`;
      });
    }
    if (O.linreg && ind.linreg) {
      const lr = ind.linreg;
      const x1 = xOf(lr.startIdx);
      const y1 = yOfPrice(lr.intercept);
      const x2 = xOf(bars.length - 1);
      const y2 = yOfPrice(lr.intercept + lr.slope * (bars.length - 1 - lr.startIdx));
      svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#60a5fa" stroke-width="1" opacity="0.85"/>`;
      const offset = 2 * lr.se;
      const yOff = (idx, off) => yOfPrice(lr.intercept + lr.slope * (idx - lr.startIdx) + off);
      svg += `<line x1="${x1}" y1="${yOff(lr.startIdx, offset)}" x2="${x2}" y2="${yOff(bars.length - 1, offset)}" stroke="#60a5fa" stroke-width="0.8" stroke-dasharray="4,3" opacity="0.55"/>`;
      svg += `<line x1="${x1}" y1="${yOff(lr.startIdx, -offset)}" x2="${x2}" y2="${yOff(bars.length - 1, -offset)}" stroke="#60a5fa" stroke-width="0.8" stroke-dasharray="4,3" opacity="0.55"/>`;
    }

    bars.forEach((b, i) => {
      const x = xOf(i);
      const isUp = b.c >= b.o;
      const color = isUp ? '#4ade80' : '#f87171';
      svg += `<line x1="${x}" y1="${yOfPrice(b.h)}" x2="${x}" y2="${yOfPrice(b.l)}" stroke="${color}" stroke-width="1"/>`;
      const yTop = yOfPrice(Math.max(b.o, b.c));
      const yBot = yOfPrice(Math.min(b.o, b.c));
      svg += `<rect x="${x - bodyW/2}" y="${yTop}" width="${bodyW}" height="${Math.max(1, yBot - yTop)}" fill="${color}"/>`;
    });

    const drawPlanLine = (price, color, dashStyle, label) => {
      if (price == null || !isFinite(price) || price <= 0) return;
      const y = yOfPrice(price);
      const dash = dashStyle === 'dashed' ? 'stroke-dasharray="6,3"' : dashStyle === 'dotted' ? 'stroke-dasharray="2,3"' : '';
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${color}" stroke-width="2" ${dash}/>`;
      svg += `<rect x="${W - padR + 2}" y="${y - 8}" width="76" height="14" fill="${color}" rx="2"/>`;
      svg += `<text x="${W - padR + 6}" y="${y + 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#0a0c0f" font-weight="800">${label}</text>`;
    };
    if (plan) {
      drawPlanLine(plan.t2, '#4ade80', 'dashed', `T2 $${plan.t2}`);
      drawPlanLine(plan.t1, '#4ade80', 'dashed', `T1 $${plan.t1}`);
      drawPlanLine(plan.entryHi, '#fbbf24', 'dotted', `EHi $${plan.entryHi}`);
      drawPlanLine(plan.entryLo, '#fbbf24', 'dotted', `ELo $${plan.entryLo}`);
      drawPlanLine(plan.stop, '#f87171', 'solid', `STOP $${plan.stop}`);
    }

    const lastY = yOfPrice(lastClose);
    svg += `<line x1="${padL}" y1="${lastY}" x2="${W - padR}" y2="${lastY}" stroke="#e8edf3" stroke-width="1" stroke-dasharray="1,3" opacity="0.7"/>`;
    svg += `<rect x="${W - padR + 2}" y="${lastY - 8}" width="76" height="14" fill="#e8edf3" rx="2"/>`;
    svg += `<text x="${W - padR + 6}" y="${lastY + 3}" font-family="ui-monospace,Menlo" font-size="9" fill="#0a0c0f" font-weight="800">NOW $${lastClose.toFixed(2)}</text>`;

    if (oscEnabled.length) {
      const perH = oscPaneH / oscEnabled.length;
      oscEnabled.forEach((key, idx) => {
        const top = oscTop + perH * idx;
        const bot = top + perH;
        svg += `<rect x="${padL}" y="${top}" width="${plotW}" height="${perH}" fill="rgba(15,19,24,0.6)" stroke="#1f2733" stroke-width="0.5"/>`;
        svg += `<text x="${padL + 4}" y="${top + 11}" font-family="ui-monospace,Menlo" font-size="9" fill="#5d6878" letter-spacing="0.12em">${key.toUpperCase()}</text>`;
        const yScale = (v, lo, hi) => top + (hi - v) / (hi - lo) * (perH - 4) + 2;
        if (key === 'rsi' && ind.rsi) {
          [30, 50, 70].forEach(level => {
            const y = yScale(level, 0, 100);
            svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${level === 50 ? '#5d6878' : level === 70 ? '#f87171' : '#4ade80'}" stroke-width="0.5" stroke-dasharray="${level === 50 ? '4,2' : '2,2'}" opacity="0.6"/>`;
          });
          const pts = [];
          for (let i = 0; i < bars.length; i++) if (ind.rsi[i] != null) pts.push(`${xOf(i)},${yScale(ind.rsi[i], 0, 100)}`);
          svg += polyLine(pts, '#a78bfa', 1.4, 0.95);
        } else if (key === 'macd' && ind.macd) {
          const all = [...ind.macd.macd, ...ind.macd.signal, ...ind.macd.hist].filter(v => v != null);
          const lo = Math.min(...all), hi = Math.max(...all);
          const zeroY = yScale(0, lo, hi);
          svg += `<line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#5d6878" stroke-width="0.5" stroke-dasharray="2,2"/>`;
          bars.forEach((_, i) => {
            if (ind.macd.hist[i] == null) return;
            const y = yScale(ind.macd.hist[i], lo, hi);
            const color = ind.macd.hist[i] >= 0 ? 'rgba(74,222,128,0.55)' : 'rgba(248,113,113,0.55)';
            svg += `<rect x="${xOf(i) - barW/2}" y="${Math.min(y, zeroY)}" width="${barW * 0.6}" height="${Math.abs(y - zeroY)}" fill="${color}"/>`;
          });
          svg += polyLine(ind.macd.macd.map((v, i) => v != null ? `${xOf(i)},${yScale(v, lo, hi)}` : null).filter(Boolean), '#22d3ee', 1.3, 0.95);
          svg += polyLine(ind.macd.signal.map((v, i) => v != null ? `${xOf(i)},${yScale(v, lo, hi)}` : null).filter(Boolean), '#f59e0b', 1.3, 0.95);
        } else if (key === 'stochrsi' && ind.stoch) {
          [20, 50, 80].forEach(level => {
            const y = yScale(level, 0, 100);
            svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${level === 50 ? '#5d6878' : level === 80 ? '#f87171' : '#4ade80'}" stroke-width="0.5" stroke-dasharray="${level === 50 ? '4,2' : '2,2'}" opacity="0.6"/>`;
          });
          const pts = [];
          for (let i = 0; i < bars.length; i++) if (ind.stoch[i] != null) pts.push(`${xOf(i)},${yScale(ind.stoch[i], 0, 100)}`);
          svg += polyLine(pts, '#fb923c', 1.4, 0.95);
        } else if (key === 'adx' && ind.adx) {
          const y = yScale(25, 0, 60);
          svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#5d6878" stroke-width="0.5" stroke-dasharray="2,2"/>`;
          const pts = [];
          for (let i = 0; i < bars.length; i++) if (ind.adx[i] != null) pts.push(`${xOf(i)},${yScale(Math.min(60, ind.adx[i]), 0, 60)}`);
          svg += polyLine(pts, '#f87171', 1.4, 0.95);
        } else if (key === 'cci' && ind.cci) {
          [-100, 0, 100].forEach(level => {
            const y = yScale(level, -200, 200);
            svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#5d6878" stroke-width="0.5" stroke-dasharray="2,2"/>`;
          });
          const pts = [];
          for (let i = 0; i < bars.length; i++) if (ind.cci[i] != null) pts.push(`${xOf(i)},${yScale(Math.max(-200, Math.min(200, ind.cci[i])), -200, 200)}`);
          svg += polyLine(pts, '#10b981', 1.4, 0.95);
        } else if (key === 'mfi' && ind.mfi) {
          [20, 50, 80].forEach(level => {
            const y = yScale(level, 0, 100);
            svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${level === 50 ? '#5d6878' : level === 80 ? '#f87171' : '#4ade80'}" stroke-width="0.5" stroke-dasharray="${level === 50 ? '4,2' : '2,2'}" opacity="0.6"/>`;
          });
          const pts = [];
          for (let i = 0; i < bars.length; i++) if (ind.mfi[i] != null) pts.push(`${xOf(i)},${yScale(ind.mfi[i], 0, 100)}`);
          svg += polyLine(pts, '#60a5fa', 1.4, 0.95);
        }
      });
    }

    svg += `</svg>`;
    host.innerHTML = svg;

    // Update legend values
    const setVal = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.textContent = v; };
    const prefix = state.idPrefix || '';
    setVal(prefix + 'ind-ema8',  '$' + ind.ema8[ind.ema8.length - 1].toFixed(2));
    setVal(prefix + 'ind-ema13', '$' + ind.ema13[ind.ema13.length - 1].toFixed(2));
    setVal(prefix + 'ind-ema20', '$' + ind.ema20[ind.ema20.length - 1].toFixed(2));
    setVal(prefix + 'ind-ema50', '$' + ind.ema50[ind.ema50.length - 1].toFixed(2));
    setVal(prefix + 'ind-ema100','$' + ind.ema100[ind.ema100.length - 1].toFixed(2));
    setVal(prefix + 'ind-ema200','$' + ind.ema200[ind.ema200.length - 1].toFixed(2));
    if (ind.sma50[ind.sma50.length - 1] != null) setVal(prefix + 'ind-sma50', '$' + ind.sma50[ind.sma50.length - 1].toFixed(2));
    if (ind.sma200[ind.sma200.length - 1] != null) setVal(prefix + 'ind-sma200', '$' + ind.sma200[ind.sma200.length - 1].toFixed(2));
    if (ind.bb) setVal(prefix + 'ind-bb', '$' + ind.bb.upper[ind.bb.upper.length - 1].toFixed(2));
    if (ind.kc) setVal(prefix + 'ind-kc', '$' + ind.kc.upper[ind.kc.upper.length - 1].toFixed(2));
    if (ind.dc) setVal(prefix + 'ind-dc', '$' + ind.dc.upper[ind.dc.upper.length - 1].toFixed(2));
    if (ind.atr) { const a = ind.atr[ind.atr.length - 1]; if (a) setVal(prefix + 'ind-atr', '±$' + (a * 1.25).toFixed(2)); }
    if (ind.ichi) {
      const tk = ind.ichi.tenkan[ind.ichi.tenkan.length - 1];
      const kj = ind.ichi.kijun[ind.ichi.kijun.length - 1];
      if (tk) setVal(prefix + 'ind-tk', '$' + tk.toFixed(2));
      if (kj) setVal(prefix + 'ind-kj', '$' + kj.toFixed(2));
    }
    if (ind.st) { const s = ind.st.st[ind.st.st.length - 1]; if (s) setVal(prefix + 'ind-st', '$' + s.toFixed(2)); }
    if (ind.psar) { const p = ind.psar[ind.psar.length - 1]; if (p) setVal(prefix + 'ind-psar', '$' + p.toFixed(2)); }
    if (ind.vwap) setVal(prefix + 'ind-vwap', '$' + ind.vwap[ind.vwap.length - 1].toFixed(2));
    if (ind.rsi) { const r = ind.rsi[ind.rsi.length - 1]; if (r != null) setVal(prefix + 'ind-rsi', r.toFixed(1)); }
    if (ind.macd) { const h = ind.macd.hist[ind.macd.hist.length - 1]; if (h != null) setVal(prefix + 'ind-macd', (h >= 0 ? '+' : '') + h.toFixed(3)); }
    if (ind.stoch) { const s = ind.stoch[ind.stoch.length - 1]; if (s != null) setVal(prefix + 'ind-stoch', s.toFixed(1)); }
    if (ind.adx) { const a = ind.adx[ind.adx.length - 1]; if (a != null) setVal(prefix + 'ind-adx', a.toFixed(1)); }
    if (ind.cci) { const c = ind.cci[ind.cci.length - 1]; if (c != null) setVal(prefix + 'ind-cci', c.toFixed(0)); }
    if (ind.mfi) { const m = ind.mfi[ind.mfi.length - 1]; if (m != null) setVal(prefix + 'ind-mfi', m.toFixed(1)); }
  }

  // ─── Public API ───────────────────────────────────────────────────────
  function init(chartContainerId, panelContainerId, ticker, options) {
    const host = document.getElementById(chartContainerId);
    const panel = document.getElementById(panelContainerId);
    if (!host) return null;

    const bars = (Array.isArray(ticker.ohlc_90d) && ticker.ohlc_90d.length >= 30)
      ? ticker.ohlc_90d.map(b => ({
          d: b.d || b.date || (b.time ? new Date(b.time * 1000).toISOString().slice(0, 10) : ''),
          o: +b.o || +b.open, h: +b.h || +b.high, l: +b.l || +b.low, c: +b.c || +b.close, v: +b.v || +b.volume || 0,
        }))
      : generateSyntheticOHLC(ticker.ticker || 'XXX',
                              +ticker.price || 100,
                              +ticker.week52_high || (+ticker.price || 100) * 1.15,
                              +ticker.week52_low  || (+ticker.price || 100) * 0.85);

    const plan = {
      entryLo: +ticker.entry_low || null,
      entryHi: +ticker.entry_high || null,
      stop:    +ticker.stop || null,
      t1:      +ticker.target1 || +ticker.t1 || null,
      t2:      +ticker.target2 || +ticker.t2 || null,
    };

    const overlays = Object.assign(defaultOverlays(), options && options.overlays || {});
    const state = {
      host, panel, bars, plan, overlays,
      idPrefix: (options && options.idPrefix) || '',
      avwaps:  options && options.avwaps,
      orderBlocks: options && options.orderBlocks,
      fvgs: options && options.fvgs,
      wkPivots: options && options.wkPivots,
    };
    state._defaults = Object.assign({}, overlays);

    renderRichLadder(state);

    // Wire panel toggle clicks
    if (panel) {
      panel.querySelectorAll('.qd-ind-row[data-ovr]').forEach(row => {
        const key = row.dataset.ovr;
        if (state.overlays[key] == null) state.overlays[key] = row.dataset.on === '1';
        row.dataset.on = state.overlays[key] ? '1' : '0';
        row.addEventListener('click', () => {
          state.overlays[key] = !state.overlays[key];
          row.dataset.on = state.overlays[key] ? '1' : '0';
          renderRichLadder(state);
        });
      });
      panel.querySelectorAll('.qd-ind-act').forEach(btn => {
        btn.addEventListener('click', () => {
          const act = btn.dataset.act;
          panel.querySelectorAll('.qd-ind-row[data-ovr]').forEach(row => {
            const key = row.dataset.ovr;
            if (act === 'all-on')  state.overlays[key] = true;
            if (act === 'all-off') state.overlays[key] = false;
            if (act === 'reset')   state.overlays[key] = !!state._defaults[key];
            row.dataset.on = state.overlays[key] ? '1' : '0';
          });
          renderRichLadder(state);
        });
      });
    }

    // Re-render on resize (debounced)
    let resizeTimer = null;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => renderRichLadder(state), 150); };
    window.addEventListener('resize', onResize);
    state._destroyResize = () => window.removeEventListener('resize', onResize);

    return state;
  }

  return { init, defaultOverlays, generateSyntheticOHLC, renderRichLadder };
})();
