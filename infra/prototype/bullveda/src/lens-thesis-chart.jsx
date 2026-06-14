// lens-thesis-chart.jsx — Thesis Chart on TradingView Lightweight Charts.
// Real candles + volume + crosshair + zoom/pan + price axis, with thesis overlays:
// plan price-lines, EMA/Bollinger/VWAP/Ichimoku series, SMC markers. Overrides window.LensChart.

const { useMemo: useTC, useState: useTCs, useRef: useTCr, useEffect: useTCe } = React;

// real-candle fetch config per timeframe (/api/ohlcv). 1W: endpoint returns daily → resample.
const TF_FETCH = {
  "5m": { tf: "5m", days: 10 }, "15m": { tf: "15m", days: 25 }, "30m": { tf: "30m", days: 45 },
  "1H": { tf: "1H", days: 90 }, "4H": { tf: "4H", days: 250 },
  "1D": { tf: "1D", days: 400 }, "1W": { tf: "1D", days: 1825, resample: "W" },
};
const TF_NOTE = { "5m": "scalp timeframe", "15m": "intraday timeframe", "30m": "intraday-swing timeframe", "1H": "execution timeframe", "4H": "swing-trigger timeframe", "1D": "thesis timeframe", "1W": "context timeframe" };

function resampleWeekly(bars) {
  const wk = {};
  bars.forEach(b => {
    const dt = new Date(b.time * 1000);
    const key = dt.getUTCFullYear() + "-W" + Math.floor((Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()) / 86400000 + 4) / 7);
    const w = wk[key];
    if (!w) wk[key] = { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, value: b.value || 0 };
    else { w.high = Math.max(w.high, b.high); w.low = Math.min(w.low, b.low); w.close = b.close; w.value += (b.value || 0); }
  });
  return Object.values(wk).sort((a, b) => a.time - b.time);
}
function _emaLast(bars, per) { const k = 2 / (per + 1); let v = bars[0].close; for (let i = 1; i < bars.length; i++) v = bars[i].close * k + v * (1 - k); return v; }
function quickBias(bars) {
  if (!bars || bars.length < 25) return null;
  const last = bars[bars.length - 1].close, e9 = _emaLast(bars, 9), e21 = _emaLast(bars, 21), e50 = _emaLast(bars, 50);
  if (e9 >= e21 && e21 >= e50 && last >= e21) return "BULL";
  if (e9 <= e21 && e21 <= e50 && last <= e21) return "BEAR";
  return "NEUTRAL";
}
// Traders Trend Dashboard (TTD): EMA(len) slope direction on a timeframe's bars
function emaDir(bars, len = 50) {
  if (!bars || bars.length < len + 2) return { dir: null, ema: null };
  const k = 2 / (len + 1); let e = bars[0].close, prev = e;
  for (let i = 1; i < bars.length; i++) { prev = e; e = bars[i].close * k + e * (1 - k); }
  return { dir: e > prev ? "up" : e < prev ? "down" : "flat", ema: +e.toFixed(2) };
}
// RSI (Wilder, length 14) — [{time, value}]
function computeRSI(bars, len = 14) {
  const out = []; if (!bars || bars.length < len + 1) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= len; i++) { const ch = bars[i].close - bars[i - 1].close; gain += Math.max(ch, 0); loss += Math.max(-ch, 0); }
  gain /= len; loss /= len;
  const push = (i) => { const v = loss === 0 ? 100 : gain === 0 ? 0 : 100 - 100 / (1 + gain / loss); out.push({ time: bars[i].time, value: +v.toFixed(2) }); };
  push(len);
  for (let i = len + 1; i < bars.length; i++) { const ch = bars[i].close - bars[i - 1].close; gain = (gain * (len - 1) + Math.max(ch, 0)) / len; loss = (loss * (len - 1) + Math.max(-ch, 0)) / len; push(i); }
  return out;
}
// MACD (12/26/9 EMA) — [{time, macd, signal, hist}]
function computeMACD(bars, f = 12, s = 26, sig = 9) {
  const ema = (arr, len) => { const k = 2 / (len + 1); let e = arr[0]; const o = [e]; for (let i = 1; i < arr.length; i++) { e = arr[i] * k + e * (1 - k); o.push(e); } return o; };
  const cl = bars.map(b => b.close); const ef = ema(cl, f), es = ema(cl, s);
  const macdArr = cl.map((_, i) => ef[i] - es[i]); const sigArr = ema(macdArr, sig);
  return bars.map((b, i) => ({ time: b.time, macd: macdArr[i], signal: sigArr[i], hist: macdArr[i] - sigArr[i] }));
}
// ── Super Trend V (AlexFuch) helpers ──
function _emaArr(a, len) { const k = 2 / (len + 1); const o = new Array(a.length); let e = a[0]; for (let i = 0; i < a.length; i++) { e = i === 0 ? a[0] : a[i] * k + e * (1 - k); o[i] = e; } return o; }
function _smaArr(a, len) { const o = new Array(a.length).fill(null); let sum = 0; for (let i = 0; i < a.length; i++) { sum += a[i]; if (i >= len) sum -= a[i - len]; if (i >= len - 1) o[i] = sum / len; } return o; }
function _rollStd(a, len) { const o = new Array(a.length).fill(null); for (let i = len - 1; i < a.length; i++) { let m = 0, c = 0; for (let j = i - len + 1; j <= i; j++) if (isFinite(a[j])) { m += a[j]; c++; } if (!c) continue; m /= c; let s = 0; for (let j = i - len + 1; j <= i; j++) if (isFinite(a[j])) s += (a[j] - m) ** 2; o[i] = Math.sqrt(s / c); } return o; }
function _atrW(bars, period) { const n = bars.length, tr = new Array(n); for (let i = 0; i < n; i++) tr[i] = i === 0 ? bars[i].high - bars[i].low : Math.max(bars[i].high - bars[i].low, Math.abs(bars[i].high - bars[i - 1].close), Math.abs(bars[i].low - bars[i - 1].close)); const o = new Array(n); let a = tr[0]; for (let i = 0; i < n; i++) { a = i === 0 ? tr[0] : (a * (period - 1) + tr[i]) / period; o[i] = a; } return o; }
// timeframe → Super Trend V `len` (Pine: intraday 720/mult*7, else 7)
function stvLen(tf) { const mult = { "5m": 5, "15m": 15, "30m": 30, "1H": 60, "4H": 240 }[tf]; return mult ? Math.max(1, Math.round(720 / mult * 7)) : 7; }
// Super Trend V — VPT "shadow" EMA + ATR SuperTrend + buy/sell + regression TP
function computeSuperTrend(bars, len, stMult = 1, stPeriod = 10) {
  const n = bars.length; if (n < Math.max(len, 28, stPeriod) + 5) return null;
  const H = bars.map(b => b.high), L = bars.map(b => b.low), O = bars.map(b => b.open), C = bars.map(b => b.close), V = bars.map(b => b.value || 0), T = bars.map(b => b.time);
  const spreadvol = bars.map((b, i) => { const hl = (H[i] - L[i]) * 100; const vol = hl !== 0 ? V[i] / hl : 0; return (C[i] - O[i]) * 100 * vol; });
  let run = 0; const v = spreadvol.map(s => { run += s; return s + run; });        // VPT-style
  const smooth = _smaArr(v, 14);
  const v_spread = _rollStd(v.map((x, i) => smooth[i] == null ? NaN : x - smooth[i]), 28);
  const price_spread = _rollStd(bars.map((b, i) => H[i] - L[i]), 28);
  const out = bars.map((b, i) => { if (smooth[i] == null || !v_spread[i] || price_spread[i] == null) return C[i]; const sh = (v[i] - smooth[i]) / v_spread[i] * price_spread[i]; return sh > 0 ? H[i] + sh : L[i] + sh; });
  const c = _emaArr(out, len), o = _emaArr(O, len), vpt = c, atr = _atrW(bars, stPeriod);
  const upT = new Array(n), dnT = new Array(n), trend = new Array(n);
  for (let i = 0; i < n; i++) {
    const upLev = vpt[i] - stMult * atr[i], dnLev = vpt[i] + stMult * atr[i];
    upT[i] = (i > 0 && C[i - 1] > upT[i - 1]) ? Math.max(upLev, upT[i - 1]) : upLev;
    dnT[i] = (i > 0 && C[i - 1] < dnT[i - 1]) ? Math.min(dnLev, dnT[i - 1]) : dnLev;
    trend[i] = i === 0 ? 1 : (C[i] > dnT[i - 1] ? 1 : C[i] < upT[i - 1] ? -1 : trend[i - 1]);
  }
  const st = trend.map((t, i) => t === 1 ? upT[i] : dnT[i]);
  const stUp = trend.map((t, i) => t === 1 ? { time: T[i], value: +st[i].toFixed(2) } : { time: T[i] });
  const stDn = trend.map((t, i) => t === -1 ? { time: T[i], value: +st[i].toFixed(2) } : { time: T[i] });
  const cLine = c.map((x, i) => ({ time: T[i], value: +x.toFixed(2) })), oLine = o.map((x, i) => ({ time: T[i], value: +x.toFixed(2) }));
  // buy/sell at SuperTrend crossovers (filtered by the blue `o` line)
  const markers = [];
  for (let i = 1; i < n; i++) {
    if (C[i] > st[i] && C[i - 1] <= st[i - 1] && C[i] > o[i]) markers.push({ time: T[i], position: "belowBar", color: "#22c55e", shape: "arrowUp", text: "Buy" });
    if (C[i] < st[i] && C[i - 1] >= st[i - 1] && C[i] < o[i]) markers.push({ time: T[i], position: "aboveBar", color: "#ef4444", shape: "arrowDown", text: "Sell" });
  }
  // regression TP band (len5 = 150) → TP exit markers
  const len5 = 150, mult = 2;
  if (n >= len5 + 2) {
    const reg = (i) => { let sx = 0, sy = 0, sxx = 0, sxy = 0; for (let k = 1; k <= len5; k++) { const val = C[i - len5 + k], per = k + 1; sx += per; sy += val; sxx += per * per; sxy += val * per; } const slope = (len5 * sxy - sx * sy) / (len5 * sxx - sx * sx); const avg = sy / len5; const inter = avg - slope * sx / len5 + slope; return inter + slope * len5; };
    const sd = _rollStd(C, len5);
    const vw = new Array(n).fill(null); for (let i = len5; i < n; i++) vw[i] = reg(i);
    for (let i = len5 + 1; i < n; i++) {
      if (vw[i] == null || vw[i - 1] == null || sd[i] == null) continue;
      const bot = vw[i] - mult * sd[i], top = vw[i] + mult * sd[i], bot1 = vw[i - 1] - mult * sd[i - 1], top1 = vw[i - 1] + mult * sd[i - 1];
      if (C[i] > bot && C[i - 1] <= bot1) markers.push({ time: T[i], position: "belowBar", color: "#ef4444", shape: "arrowUp", text: "TP" });
      if (C[i] < top && C[i - 1] >= top1) markers.push({ time: T[i], position: "aboveBar", color: "#22c55e", shape: "arrowDown", text: "TP" });
    }
  }
  return { c: cLine, o: oLine, stUp, stDn, markers };
}
function _barsFrom(res, cfg) {
  const candles = (res && res.candles) || [], volArr = (res && res.volume) || [];
  let b = candles.map((c, i) => { const vv = volArr[i]; const v = (vv && typeof vv === "object") ? (vv.value || 0) : (typeof vv === "number" ? vv : 0); return { time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, value: v }; });
  if (cfg.resample === "W") b = resampleWeekly(b);
  return b;
}
function useCandles(sym, tfKey) {
  const [bars, setBars] = useTCs(null);
  useTCe(() => {
    const BV = window.__BV; if (!BV || !BV.get || !sym) { setBars(false); return; }
    const cfg = TF_FETCH[tfKey] || TF_FETCH["1D"]; let on = true; setBars(null);
    BV.get(`/api/ohlcv/${encodeURIComponent(sym)}?tf=${cfg.tf}&days=${cfg.days}`).then(res => { if (!on) return; const b = _barsFrom(res, cfg); setBars(b.length >= 5 ? b : false); }).catch(() => { if (on) setBars(false); });
    return () => { on = false; };
  }, [sym, tfKey]);
  return bars;
}
function useMtfBias(sym) {
  const [m, setM] = useTCs({});
  useTCe(() => {
    const BV = window.__BV; if (!BV || !BV.get || !sym) { setM({}); return; } let on = true; setM({});
    Object.keys(TF_FETCH).forEach(k => { const cfg = TF_FETCH[k];
      BV.get(`/api/ohlcv/${encodeURIComponent(sym)}?tf=${cfg.tf}&days=${cfg.days}`).then(res => { if (on) { const bb = _barsFrom(res, cfg); setM(prev => ({ ...prev, [k]: { bias: quickBias(bb), ...emaDir(bb, 50) } })); } }).catch(() => {});
    });
    return () => { on = false; };
  }, [sym]);
  return m;
}
function useChartNews(sym) {
  const [n, setN] = useTCs([]);
  useTCe(() => {
    const BV = window.__BV; if (!BV || !BV.get || !sym) { setN([]); return; } let on = true;
    BV.get(`/api/news?t=${encodeURIComponent(sym)}`).then(res => { if (on) setN((res && res.articles) || []); }).catch(() => { if (on) setN([]); });
    return () => { on = false; };
  }, [sym]);
  return n;
}

// MTF previous-period High/Low (LuxAlgo SMC "Highs & Lows MTF"): bucket the loaded
// bars by calendar day / week / month and take the last COMPLETED bucket of each.
// Pure derivation from bars already on hand — no extra fetch.
function computeMTFLevels(bars) {
  if (!bars || bars.length < 2) return null;
  const g = { day: {}, week: {}, month: {} }, order = { day: [], week: [], month: [] };
  bars.forEach(b => {
    const dt = new Date(b.time * 1000);
    const keys = { day: dt.getUTCFullYear() * 10000 + dt.getUTCMonth() * 100 + dt.getUTCDate(),
                   week: Math.floor(b.time / 86400 / 7), month: dt.getUTCFullYear() * 12 + dt.getUTCMonth() };
    ["day", "week", "month"].forEach(p => { const k = keys[p];
      if (!g[p][k]) { g[p][k] = { hi: b.high, lo: b.low }; order[p].push(k); }
      else { if (b.high > g[p][k].hi) g[p][k].hi = b.high; if (b.low < g[p][k].lo) g[p][k].lo = b.low; } });
  });
  const prev = p => { const o = order[p]; return o.length >= 2 ? g[p][o[o.length - 2]] : null; };
  const pd = prev("day"), pw = prev("week"), pm = prev("month");
  const lvls = [];
  if (pd) { lvls.push({ tag: "PDH", level: pd.hi, kind: "day" }, { tag: "PDL", level: pd.lo, kind: "day" }); }
  if (pw) { lvls.push({ tag: "PWH", level: pw.hi, kind: "week" }, { tag: "PWL", level: pw.lo, kind: "week" }); }
  if (pm) { lvls.push({ tag: "PMH", level: pm.hi, kind: "month" }, { tag: "PML", level: pm.lo, kind: "month" }); }
  return lvls.length ? lvls : null;
}

// compute all overlays/indicators from REAL bars (logic unchanged — now fed real data)
function computeIndicators(bars, lv, tf, smcSwing) {
  const ema = (per) => { const k = 2 / (per + 1); let pr = bars[0].close; return bars.map((b, i) => { pr = i === 0 ? b.close : b.close * k + pr * (1 - k); return { time: b.time, value: +pr.toFixed(2) }; }); };
  const e9 = ema(9), e21 = ema(21), e50 = ema(50);
  const bbU = [], bbM = [], bbL = [];
  bars.forEach((b, i) => { const s = Math.max(0, i - 19), w = bars.slice(s, i + 1).map(x => x.close); const m = w.reduce((a, c) => a + c, 0) / w.length; const sd = Math.sqrt(w.reduce((a, c) => a + (c - m) ** 2, 0) / w.length); bbM.push({ time: b.time, value: +m.toFixed(2) }); bbU.push({ time: b.time, value: +(m + 2 * sd).toFixed(2) }); bbL.push({ time: b.time, value: +(m - 2 * sd).toFixed(2) }); });
  const anchor = Math.floor(bars.length * 0.82); let pv = 0, cv = 0; const avwap = [];
  bars.forEach((b, i) => { if (i >= anchor) { const tp = (b.high + b.low + b.close) / 3; pv += tp * b.value; cv += b.value; avwap.push({ time: b.time, value: +(cv ? pv / cv : b.close).toFixed(2) }); } });
  const hh = (per, i) => Math.max(...bars.slice(Math.max(0, i - per + 1), i + 1).map(b => b.high));
  const ll = (per, i) => Math.min(...bars.slice(Math.max(0, i - per + 1), i + 1).map(b => b.low));
  // Ichimoku (official TradingView spec): conversion 9, base 26, span B 52,
  // displacement 26 (offset = displacement − 1) for cloud forward + lagging back.
  const ICH_DISP = 26 - 1;
  const n = bars.length;
  const tenkan = [], kijun = [], spanARaw = [], spanBRaw = [];
  bars.forEach((b, i) => {
    const t = (hh(9, i) + ll(9, i)) / 2, k = (hh(26, i) + ll(26, i)) / 2;
    tenkan.push({ time: b.time, value: +t.toFixed(2) });
    kijun.push({ time: b.time, value: +k.toFixed(2) });
    spanARaw.push(+((t + k) / 2).toFixed(2));
    spanBRaw.push(+((hh(52, i) + ll(52, i)) / 2).toFixed(2));
  });
  // forward time projection for the displaced cloud (median bar interval)
  const _diffs = []; for (let i = Math.max(1, n - 10); i < n; i++) _diffs.push(bars[i].time - bars[i - 1].time);
  _diffs.sort((a, b) => a - b);
  const _step = _diffs.length ? (_diffs[Math.floor(_diffs.length / 2)] || 86400) : 86400;
  const dispTime = (i) => { const j = i + ICH_DISP; return j < n ? bars[j].time : bars[n - 1].time + (j - (n - 1)) * _step; };
  const spanA = bars.map((b, i) => ({ time: dispTime(i), value: spanARaw[i] }));
  const spanB = bars.map((b, i) => ({ time: dispTime(i), value: spanBRaw[i] }));
  // lagging span (Chikou): close plotted ICH_DISP bars back
  const chikou = []; for (let i = ICH_DISP; i < n; i++) chikou.push({ time: bars[i - ICH_DISP].time, value: bars[i].close });
  const L = 5, piv = []; for (let i = L; i < bars.length - L; i++) { const isH = bars.slice(i - L, i + L + 1).every((b, j) => j === L || bars[i].high >= b.high); const isL = bars.slice(i - L, i + L + 1).every((b, j) => j === L || bars[i].low <= b.low); if (isH) piv.push({ i, price: bars[i].high, type: 'H' }); else if (isL) piv.push({ i, price: bars[i].low, type: 'L' }); }
  const breaks = []; let lH = null, lL = null, tb = 0;
  bars.forEach((b, i) => { if (lH != null && b.close > lH.price) { breaks.push({ time: b.time, price: lH.price, dir: 'bull', tag: tb === -1 ? 'CHoCH' : 'BOS' }); tb = 1; lH = null; } if (lL != null && b.close < lL.price) { breaks.push({ time: b.time, price: lL.price, dir: 'bear', tag: tb === 1 ? 'CHoCH' : 'BOS' }); tb = -1; lL = null; } const ph = piv.find(p => p.i === i && p.type === 'H'); if (ph) lH = ph; const pl = piv.find(p => p.i === i && p.type === 'L'); if (pl) lL = pl; });
  const obs = []; breaks.slice(-3).forEach(bk => { const bi = bars.findIndex(b => b.time === bk.time); for (let j = bi; j > Math.max(0, bi - 10); j--) { if (bk.dir === 'bull' && bars[j].close < bars[j].open) { obs.push({ price: +((bars[j].high + bars[j].low) / 2).toFixed(2), bias: 'bull' }); break; } if (bk.dir === 'bear' && bars[j].close > bars[j].open) { obs.push({ price: +((bars[j].high + bars[j].low) / 2).toFixed(2), bias: 'bear' }); break; } } });
  const vlo = Math.min(...bars.map(b => b.low)), vhi = Math.max(...bars.map(b => b.high)), VN = 22, vbin = (vhi - vlo) / VN || 1;
  const vpb = Array.from({ length: VN }, (_, i) => ({ lo: vlo + i * vbin, hi: vlo + (i + 1) * vbin, mid: vlo + (i + 0.5) * vbin, v: 0 }));
  bars.forEach(b => { const m = (b.high + b.low) / 2; const bi = Math.min(VN - 1, Math.max(0, Math.floor((m - vlo) / vbin))); vpb[bi].v += b.value; });
  const vpMax = Math.max(...vpb.map(x => x.v), 1); const pocI = vpb.reduce((m, x, i) => x.v > vpb[m].v ? i : m, 0);
  const vTot = vpb.reduce((a, x) => a + x.v, 0); let vacc = vpb[pocI].v, vloI = pocI, vhiI = pocI;
  while (vacc < vTot * 0.7 && (vloI > 0 || vhiI < VN - 1)) { const dn = vloI > 0 ? vpb[vloI - 1].v : -1, up = vhiI < VN - 1 ? vpb[vhiI + 1].v : -1; if (up >= dn) { vhiI++; vacc += vpb[vhiI].v; } else { vloI--; vacc += vpb[vloI].v; } }
  // ── Money Flow Profile (LuxAlgo-style): same price bins, but each bar's money
  //    flow (volume × typical price) is split into bullish (close≥open) vs bearish.
  //    Row total width = money flow at that level; the green/red split = sentiment;
  //    the widest node is the money-flow POC. Mirrors LuxAlgo's combined Volume/
  //    Money-Flow + Sentiment profile, reusing this chart's mid-bin convention. ──
  const mfb = Array.from({ length: VN }, (_, i) => ({ lo: vlo + i * vbin, hi: vlo + (i + 1) * vbin, mid: vlo + (i + 0.5) * vbin, bull: 0, bear: 0, mf: 0 }));
  bars.forEach(b => { const m = (b.high + b.low) / 2; const bi = Math.min(VN - 1, Math.max(0, Math.floor((m - vlo) / vbin))); const tp = (b.high + b.low + b.close) / 3; const flow = (b.value || 0) * tp; if (b.close >= b.open) mfb[bi].bull += flow; else mfb[bi].bear += flow; mfb[bi].mf += flow; });
  const mfMax = Math.max(...mfb.map(x => x.mf), 1); const mfpI = mfb.reduce((m, x, i) => x.mf > mfb[m].mf ? i : m, 0);
  const last = bars[bars.length - 1].close;

  // ── LuxAlgo Smart Money Concepts (window.computeSMC) — internal+swing structure,
  //    volatility-parsed order blocks w/ mitigation, FVG, EQH/EQL, trailing strong/weak,
  //    premium/discount. Indices mapped to bar time for the Lightweight chart. ──
  let smc = null;
  if (window.computeSMC) {
    const lux = window.computeSMC(bars.map(b => ({ o: b.open, hi: b.high, lo: b.low, c: b.close, v: b.value })),
      { swingLen: smcSwing || 20, intLen: 5, eq: true, swings: true, fvg: true });
    if (lux && lux.ok) {
      const T = i => (bars[i] ? bars[i].time : null);
      const ev = s => ({ time: T(s.toIdx), fromTime: T(s.fromIdx), level: s.level, tag: s.tag, dir: s.dir, internal: s.internal });
      smc = {
        struct: lux.swingStruct.map(ev).filter(e => e.time),
        intStruct: lux.intStruct.map(ev).filter(e => e.time),
        swingOB: lux.swingOB.filter(o => o.mitIdx < 0).slice(0, 5).map(o => ({ time: T(o.idx), high: o.high, low: o.low, bias: o.bias, internal: false, buyVol: o.buyVol, sellVol: o.sellVol, vol: o.vol })).filter(o => o.time),
        intOB: lux.intOB.filter(o => o.mitIdx < 0).slice(0, 8).map(o => ({ time: T(o.idx), high: o.high, low: o.low, bias: o.bias, internal: true, buyVol: o.buyVol, sellVol: o.sellVol, vol: o.vol })).filter(o => o.time),
        fvg: lux.fvg.filter(g => g.mitIdx < 0).slice(0, 12).map(g => ({ time: T(Math.max(0, g.idx - 1)), top: g.top, bottom: g.bottom, bias: g.bias })).filter(g => g.time),
        equal: lux.equal.slice(-6).map(e => ({ fromTime: T(e.fromIdx), toTime: T(e.toIdx), level: e.level, tag: e.tag })).filter(e => e.fromTime && e.toTime),
        swingPts: (lux.swingPts || []).map(p => ({ time: T(p.idx), level: p.level, tag: p.tag, up: p.up })).filter(p => p.time),
        candTrend: lux.candTrend || null,
        trailing: lux.trailing ? { top: lux.trailing.top, bottom: lux.trailing.bottom, topTime: T(lux.trailing.topIdx), botTime: T(lux.trailing.botIdx), startTime: T(lux.trailing.idx), swTrend: lux.swTrend, inTrend: lux.inTrend } : null,
      };
    }
  }

  // ── LuxAlgo Fair Value Gap (standalone): 3-candle imbalance, +extend bars, mitigation ──
  const _N = bars.length, FVG_EXT = 20;
  const _fd = []; for (let i = Math.max(1, _N - 10); i < _N; i++) _fd.push(bars[i].time - bars[i - 1].time);
  _fd.sort((a, b) => a - b); const _fstep = _fd.length ? (_fd[Math.floor(_fd.length / 2)] || 86400) : 86400;
  const _ftime = (idx) => idx < _N ? bars[idx].time : bars[_N - 1].time + (idx - (_N - 1)) * _fstep;
  const _fvgL = [];
  for (let i = 2; i < _N; i++) {
    const h2 = bars[i - 2].high, l2 = bars[i - 2].low;
    if (bars[i].low > h2 && bars[i - 1].close > h2) _fvgL.push({ left: i - 2, right: i + FVG_EXT, top: bars[i].low, bottom: h2, bias: 1, mit: -1 });
    else if (bars[i].high < l2 && bars[i - 1].close < l2) _fvgL.push({ left: i - 2, right: i + FVG_EXT, top: l2, bottom: bars[i].high, bias: -1, mit: -1 });
  }
  for (const g of _fvgL) for (let j = g.left + 3; j < _N; j++) { if (g.bias > 0 && bars[j].close < g.bottom) { g.mit = j; break; } if (g.bias < 0 && bars[j].close > g.top) { g.mit = j; break; } }
  const fvgLux = _fvgL.filter(g => g.mit < 0).map(g => ({ t0: bars[g.left].time, t1: _ftime(g.right), top: g.top, bottom: g.bottom, bias: g.bias }));

  // ── RSI(14) + MACD(12,26,9) for oscillator sub-panes ──
  const rsi = computeRSI(bars, 14);
  const macd = computeMACD(bars, 12, 26, 9);
  // ── Super Trend V (timeframe-adaptive len) ──
  const stv = computeSuperTrend(bars, stvLen(tf || "1D"), 1, 10);

  return { spot: last, entry: +(lv.pivot || last).toFixed(2), stop: +(lv.stop || last * 0.94).toFixed(2), t1: +(lv.t1 || last * 1.06).toFixed(2), t2: +(lv.t2 || last * 1.12).toFixed(2), validPlan: !!lv.valid,
    bars, e9, e21, e50, bbU, bbM, bbL, avwap, tenkan, kijun, spanA, spanB, chikou, breaks: breaks.slice(-6), obs, vpb, vpMax, poc: vpb[pocI].mid, vah: vpb[vhiI].hi, val: vpb[vloI].lo, mfb, mfMax, mfpoc: mfb[mfpI].mid, smc, mtfLevels: computeMTFLevels(bars), fvgLux, rsi, macd, stv };
}

// per-timeframe thesis derived from the REAL EMA stack + most recent structure break
function tfThesis(d) {
  if (!d || !d.bars || d.bars.length < 20) return { bias: "—", tone: "amb", read: "Not enough history on this timeframe.", struct: "—" };
  const last = d.bars[d.bars.length - 1].close;
  const e9 = d.e9[d.e9.length - 1].value, e21 = d.e21[d.e21.length - 1].value, e50 = d.e50[d.e50.length - 1].value;
  const above = [e9, e21, e50].filter(m => last >= m).length;
  const lb = d.breaks.length ? d.breaks[d.breaks.length - 1] : null;
  const struct = lb ? `${lb.tag} ${lb.dir === "bull" ? "↑" : "↓"} @ $${lb.price}` : "no recent structure break";
  if (e9 >= e21 && e21 >= e50 && last >= e21) return { bias: "BULL", tone: "up", read: "Stacked EMAs with price leading — uptrend intact here; pullbacks to the rising 21-EMA are the spots.", struct };
  if (e9 <= e21 && e21 <= e50 && last <= e21) return { bias: "BEAR", tone: "dn", read: "EMAs rolling down with price below — downtrend here; rallies into the falling 21-EMA tend to fail.", struct };
  return { bias: "NEUTRAL", tone: "amb", read: `${above}/3 EMAs below price · no clean stack — choppy / range on this timeframe; wait for a decisive break.`, struct };
}

// real news flags positioned along the chart timeline by article date + sentiment
function NewsFlags({ news, bars }) {
  if (!bars || !bars.length) return null;
  const t0 = bars[0].time, t1 = bars[bars.length - 1].time, span = (t1 - t0) || 1;
  const flags = (news || []).map(a => {
    const t = Date.parse(a.date) / 1000; if (!isFinite(t)) return null;
    if (t < t0 - span * 0.08) return null;             // far older than the chart window → skip
    const x = Math.max(1, Math.min(99, (t - t0) / span * 100));  // recent news clamps to the right edge
    const pol = typeof a.polarity === "number" ? a.polarity : 0;
    return { x, tone: pol > 0.05 ? "gn" : pol < -0.05 ? "rd" : "amb", d: a.title, s: pol >= 0 ? "+" + pol.toFixed(2) : pol.toFixed(2), url: a.url };
  }).filter(Boolean).slice(0, 12).sort((a, b) => a.x - b.x);
  for (let i = 1; i < flags.length; i++) if (flags[i].x - flags[i - 1].x < 2.5) flags[i].x = Math.min(99, flags[i - 1].x + 2.5);   // de-cluster
  return (
    <div className="tc-news">
      <span className="tc-news-lbl mono dim2">NEWS</span>
      <div className="tc-news-track">
        {flags.length ? flags.map((e, i) => (
          <a key={i} className={`tc-news-flag tc-news-flag--${e.tone}`} style={{ left: `${e.x}%` }} href={e.url} target="_blank" rel="noopener noreferrer" title={`${e.d} · sentiment ${e.s}`}><span className="tc-news-dot" /></a>
        )) : <span className="mono dim2" style={{ fontSize: 10, paddingLeft: 8 }}>no headlines within this window</span>}
      </div>
    </div>
  );
}

// LuxAlgo SMC sub-feature toggles (mirror the standalone prototype) + labels
const SMC_SUB = [["swing","Swing"],["internal","Internal"],["swingOB","Swing OB"],["intOB","Int OB"],["fvg","FVG"],["eq","EQH/EQL"],["hl","Strong/Weak"],["zones","Prem/Disc"],["swings","Swings"],["mtf","MTF Levels"],["vol","OB Volume"],["color","Color"]];
const SMC_SUB_DEFAULT = { swing:true, internal:true, swingOB:false, intOB:true, fvg:false, eq:true, hl:true, zones:false, swings:false, mtf:true, vol:true, color:false };

function LensChart({ ticker, mode }) {
  const modeTf = mode === "POSITION" ? "1D" : mode === "INVESTMENT" ? "1W" : "1D";
  const [tf, setTf] = useTCs(modeTf);
  // follow the global mode unless the user has manually picked a timeframe
  const [tfTouched, setTfTouched] = useTCs(false);
  React.useEffect(() => { if (!tfTouched) setTf(modeTf); }, [modeTf]);
  const [full, setFull] = useTCs(false);
  const [indMenu, setIndMenu] = useTCs(false);
  const [ind, setInd] = useTCs({ ema:false, bb:false, avwap:false, ichi:false, smc:false, smcLux:false, vp:false, mfp:false, fvgLux:false, rsi:true, macd:true, ttd:true, stv:false });
  const togInd = (k) => setInd(s => ({ ...s, [k]: !s[k] }));
  const [smcSub, setSmcSub] = useTCs(SMC_SUB_DEFAULT);
  const togSub = (k) => setSmcSub(s => ({ ...s, [k]: !s[k] }));
  const [smcSwing, setSmcSwing] = useTCs(20);   // LuxAlgo SMC swing-structure length

  // REAL candles for the active timeframe + multi-timeframe biases + live news
  const barsRaw = useCandles(ticker.symbol, tf);
  const loading = barsRaw === null, failed = barsRaw === false;
  const lv = window.coherentLevels ? window.coherentLevels(ticker) : { price: ticker.price, pivot: ticker.price, stop: ticker.price * 0.94, t1: ticker.price * 1.06, t2: ticker.price * 1.12, valid: false };
  const d = useTC(() => (barsRaw && barsRaw.length >= 5) ? computeIndicators(barsRaw, lv, tf, smcSwing) : null, [barsRaw, lv.pivot, lv.stop, lv.t1, lv.t2, tf, smcSwing]);
  const mtf = useMtfBias(ticker.symbol);
  const news = useChartNews(ticker.symbol);
  const tfx = tfThesis(d);
  const tone3 = t => t === "up" ? "gn" : t === "dn" ? "rd" : "amb";
  const biasTone = b => b === "BULL" ? "gn" : b === "BEAR" ? "rd" : "amb";

  return (
    <div className={`lens lens--tc ${full?"tc-full":""}`}>
      <div className="tc-head">
        <div className="tc-head-l">
          <span className="tc-eyebrow mono">THESIS CHART</span>
          <span className="tc-sub mono dim2">interactive · crosshair · zoom · plan levels + indicators</span>
        </div>
        <div className="tc-toggles">
          <div className="tc-ind-wrap">
            <button className={`tc-tog tc-ind-btn ${indMenu?"is-open":""}`} onClick={()=>setIndMenu(v=>!v)}>+ Indicators ▾</button>
            {indMenu && (
              <div className="tc-ind-menu">
                {[["ema","EMA 9/21/50"],["bb","Bollinger 20·2"],["avwap","Anchored VWAP"],["ichi","Ichimoku Cloud"],["vp","Volume Profile"],["mfp","Money Flow Profile"],["smc","Smart Money Concepts"],["smcLux","Smart Money Concepts · LuxAlgo"],["fvgLux","Fair Value Gap · LuxAlgo"],["stv","Super Trend V"],["rsi","RSI (14)"],["macd","MACD (12,26,9)"],["ttd","Traders Trend Dashboard"]].map(([k,l])=>(
                  <button key={k} className={`tc-ind-item ${ind[k]?"is-on":""}`} onClick={()=>togInd(k)}>
                    <span className="tc-ind-chk">{ind[k]?"✓":""}</span>{l}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button className="tc-tog tc-full-btn" onClick={()=>setFull(f=>!f)}>{full?"⤢ Exit":"⤢ Full"}</button>
        </div>
      </div>

      <div className="tc-mtf">
        {["5m","15m","30m","1H","4H","1D","1W"].map(k=>(
          <button key={k} className={`tc-tf ${tf===k?"is-on":""}`} onClick={()=>{ setTfTouched(true); setTf(k); }}>
            <span className="mono">{k}</span>
            <span className={`mono kpi-tone--${biasTone(mtf[k] && mtf[k].bias)}`}>{(mtf[k] && mtf[k].bias) || "…"}</span>
          </button>
        ))}
        <div className="tc-tf-read">
          <span className={`tc-tf-tag mono kpi-tone--${tone3(tfx.tone)}`}>{tf} · {tfx.bias}</span>
          <span className="mono tc-tf-txt">{tfx.read}</span>
          <span className="mono dim2 tc-tf-struct">{tfx.struct} · <i>{TF_NOTE[tf]}</i></span>
        </div>
      </div>

      {/* LuxAlgo SMC sub-feature toggles — visible only while that layer is on */}
      {ind.smcLux && (
        <div className="tc-smc-sub" style={{ display: "flex", flexWrap: "wrap", gap: "5px 7px", alignItems: "center", padding: "2px 2px 0" }}>
          <span className="label-cap mono" style={{ fontSize: 9.5, color: "var(--ink-3)", letterSpacing: ".1em", marginRight: 2 }}>SMC · LUXALGO</span>
          {SMC_SUB.map(([k, l]) => (
            <button key={k} onClick={() => togSub(k)} className="mono"
              style={{ fontSize: 10.5, padding: "3px 8px", borderRadius: 6, cursor: "pointer",
                background: smcSub[k] ? "color-mix(in oklab, var(--blue) 22%, var(--bg-2))" : "var(--bg-2)",
                border: "1px solid " + (smcSub[k] ? "color-mix(in oklab, var(--blue) 45%, transparent)" : "var(--ink-2)"),
                color: smcSub[k] ? "var(--ink-0)" : "var(--ink-3)" }}>{l}</button>
          ))}
          <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 4 }}>swing</span>
          <input type="number" min={5} max={100} step={5} value={smcSwing}
            onChange={e => { const v = Math.max(5, Math.min(100, +e.target.value || 20)); setSmcSwing(v); }}
            className="mono" style={{ width: 46, fontSize: 10.5, padding: "2px 4px", borderRadius: 6,
              background: "var(--bg-2)", border: "1px solid var(--ink-2)", color: "var(--ink-0)" }} />
        </div>
      )}

      <div className="tc-chart-card" style={{ position: "relative" }}>
        {loading ? <div className="tc-lw" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono dim2">loading real {tf} candles…</span></div>
          : (failed || !d) ? <div className="tc-lw" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono dim2">No {tf} candles available for {ticker.symbol}.</span></div>
            : <LWChart d={d} ind={ind} smcSub={smcSub} full={full} />}
        <TrendDash mtf={mtf} show={ind.ttd} ema1={50} />
        {d && <div className="tc-legend mono">
          <span><i className="tc-sw tc-sw--cop"/>{d.validPlan ? "entry" : "~entry"} ${d.entry}</span>
          <span><i className="tc-sw tc-sw--rd"/>stop ${d.stop}</span>
          <span><i className="tc-sw tc-sw--gn"/>T1 ${d.t1} · T2 ${d.t2}</span>
          {ind.ema && <span><i className="tc-sw" style={{background:"var(--cy)"}}/>EMA 9/21/50</span>}
          {ind.bb && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>Bollinger</span>}
          {ind.avwap && <span><i className="tc-sw" style={{background:"var(--amb)"}}/>aVWAP</span>}
          {ind.ichi && <span><i className="tc-sw" style={{background:"#43A047"}}/>Ichimoku · cloud + lagging span</span>}
          {ind.smc && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>SMC · BOS/CHoCH/OB</span>}
          {ind.smcLux && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>SMC · LuxAlgo · BOS/CHoCH · volumetric OB · FVG · EQH/EQL · MTF <i className="tc-sw" style={{background:"#5b9bf2"}}/>PD <i className="tc-sw" style={{background:"#f59e0b"}}/>PW <i className="tc-sw" style={{background:"#a78bfa"}}/>PM</span>}
          {ind.vp && <span><i className="tc-sw tc-sw--cop"/>POC <i className="tc-sw" style={{background:"var(--cy)"}}/>value area · volume profile</span>}
          {ind.mfp && <span>money flow profile · sentiment <i className="tc-sw" style={{background:"#26a69a"}}/>buy <i className="tc-sw" style={{background:"#ef5350"}}/>sell · nodes <i className="tc-sw" style={{background:"#ffeb3b"}}/>high <i className="tc-sw" style={{background:"#2962ff"}}/>avg <i className="tc-sw" style={{background:"#f23645"}}/>low</span>}
          {ind.fvgLux && <span><i className="tc-sw" style={{background:"#089981"}}/>FVG · LuxAlgo (extend + mitigation)</span>}
          {ind.stv && <span><i className="tc-sw" style={{background:"#22c55e"}}/>Super Trend V · Buy/Sell + TP</span>}
          {ind.rsi && <span><i className="tc-sw" style={{background:"#7E57C2"}}/>RSI 14 · pane</span>}
          {ind.macd && <span><i className="tc-sw" style={{background:"#2962FF"}}/>MACD 12/26/9 · pane</span>}
          <span className="dim2">drag to pan · scroll to zoom · hover for OHLC</span>
        </div>}
        <NewsFlags news={news} bars={d ? d.bars : null} />
      </div>

      {!full && d && <div className="lens-call">
        <span className="label-cap">The Read · Chart · {tf}</span>
        <span className="mono"><b className={`kpi-tone--${tone3(tfx.tone)}`}>{tfx.bias}</b> on {tf} — {tfx.read} {d.validPlan ? <>Plan: entry <b className="cy">${d.entry}</b>, stop <b className="dn">${d.stop}</b>, targets <b className="up">${d.t1}/${d.t2}</b>.</> : <>No active scan trade-plan — levels shown are price-estimates.</>}</span>
      </div>}
    </div>
  );
}

// Traders Trend Dashboard — MTF EMA(50)-slope table (corner panel)
function TrendDash({ mtf, show }) {
  if (!show) return null;
  const ROWS = [["5m", "5m"], ["15m", "15m"], ["30m", "30m"], ["1H", "1h"], ["4H", "4h"], ["1D", "D"], ["1W", "W"]];
  const dot = d => d === "up" ? "🟢" : d === "down" ? "🔴" : d === "flat" ? "⚫️" : "…";
  const bg = d => d === "up" ? "rgba(76,175,80,.22)" : d === "down" ? "rgba(255,82,82,.22)" : d === "flat" ? "rgba(120,123,134,.22)" : "transparent";
  return (
    <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", zIndex: 5,
      border: "1px solid var(--ink-2)", borderRadius: 8, overflow: "hidden", background: "rgba(13,17,16,.78)", backdropFilter: "blur(4px)", minWidth: 86 }}>
      <div className="mono" style={{ fontSize: 9, letterSpacing: ".1em", color: "var(--ink-3)", textAlign: "center", padding: "3px 0 2px", borderBottom: "1px solid rgba(255,255,255,.06)" }}>TTD · EMA50</div>
      {ROWS.map(([k, lbl]) => {
        const dir = mtf[k] && mtf[k].dir;
        return (
          <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "3px 10px", background: bg(dir), borderBottom: "1px solid rgba(255,255,255,.05)" }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--ink-1)" }}>{lbl}</span>
            <span style={{ fontSize: 11, lineHeight: 1 }}>{dot(dir)}</span>
          </div>
        );
      })}
    </div>
  );
}

function LWChart({ d, ind, smcSub, full }) {
  const ss = smcSub || {};
  const wrap = useTCr(null);
  const rsiWrap = useTCr(null);
  const macdWrap = useTCr(null);
  const chartRef = useTCr(null);
  const seriesRef = useTCr({});

  // create chart once
  useTCe(() => {
    if (!wrap.current || !window.LightweightCharts) return;
    const cssv = (n,f) => (getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f);
    const chart = window.LightweightCharts.createChart(wrap.current, {
      autoSize: true,
      layout: { background:{ color:"transparent" }, textColor: cssv("--ink-2","#8590a3"), fontFamily:"inherit" },
      grid: { vertLines:{ color:"rgba(255,255,255,0.04)" }, horzLines:{ color:"rgba(255,255,255,0.04)" } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor:"rgba(255,255,255,0.10)" },
      timeScale: { borderColor:"rgba(255,255,255,0.10)", timeVisible:false, rightOffset:6 },
    });
    chartRef.current = chart;
    const candle = chart.addCandlestickSeries({
      upColor:"#4ade80", downColor:"#f87171", borderUpColor:"#4ade80", borderDownColor:"#f87171",
      wickUpColor:"#4ade80", wickDownColor:"#f87171",
    });
    const vol = chart.addHistogramSeries({ priceFormat:{ type:"volume" }, priceScaleId:"vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins:{ top:0.82, bottom:0 } });
    seriesRef.current = { chart, candle, vol, overlays:[], priceLines:[] };
    return () => { chart.remove(); chartRef.current=null; seriesRef.current={}; };
  }, []);

  // feed candles + volume + plan lines + markers + overlays on data/ind change
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    // color candles by internal SMC trend when that LuxAlgo sub-toggle is on
    const colorCandles = ind.smcLux && ss.color && d.smc && d.smc.candTrend;
    s.candle.setData(colorCandles
      ? d.bars.map((b, i) => { const tr = d.smc.candTrend[i]; const c = tr > 0 ? "#4ade80" : tr < 0 ? "#f87171" : "#8590a3"; return { ...b, color: c, borderColor: c, wickColor: c }; })
      : d.bars);
    s.vol.setData(d.bars.map(b=>({ time:b.time, value:b.value, color: b.close>=b.open ? "rgba(74,222,128,0.4)" : "rgba(248,113,113,0.4)" })));

    // plan price lines
    s.priceLines.forEach(pl => s.candle.removePriceLine(pl));
    const mk = (price,color,title) => s.candle.createPriceLine({ price, color, lineWidth:1, lineStyle:2, axisLabelVisible:true, title });
    s.priceLines = [
      mk(d.entry, "#d97757", "ENTRY"),
      mk(d.stop, "#f87171", "STOP"),
      mk(d.t1, "#4ade80", "T1"),
      mk(d.t2, "#4ade80", "T2"),
    ];
    // SMC (lightweight): order-block price lines
    if (ind.smc) d.obs.forEach(o => s.priceLines.push(mk(o.price, o.bias === "bull" ? "#5b9bf2" : "#d97757", o.bias === "bull" ? "+OB" : "−OB")));
    // SMC (LuxAlgo): trailing strong/weak high-low + EQH/EQL as price lines
    // (order blocks / FVG / premium-discount drawn as boxes in the SVG overlay below)
    if (ind.smcLux && d.smc) {
      const sm = d.smc;
      if (ss.hl && sm.trailing) {
        s.priceLines.push(mk(sm.trailing.top, "#f87171", sm.trailing.swTrend < 0 ? "Strong High" : "Weak High"));
        s.priceLines.push(mk(sm.trailing.bottom, "#4ade80", sm.trailing.swTrend > 0 ? "Strong Low" : "Weak Low"));
      }
      // EQH/EQL now drawn as paired connector lines in the SVG overlay (see below)
    }

    // overlay line series
    s.overlays.forEach(o => s.chart.removeSeries(o)); s.overlays=[];
    const addLine = (data,color,width=1,style=0) => { const ls=s.chart.addLineSeries({ color, lineWidth:width, lineStyle:style, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }); ls.setData(data); s.overlays.push(ls); };
    if (ind.ema) { addLine(d.e9,"#5dd6d6"); addLine(d.e21,"#fbbf24"); addLine(d.e50,"#a78bfa"); }
    if (ind.bb) { addLine(d.bbU,"#5b9bf2",1,2); addLine(d.bbM,"#5b9bf2",1,1); addLine(d.bbL,"#5b9bf2",1,2); }
    if (ind.avwap) addLine(d.avwap,"#fbbf24",2,2);
    if (ind.ichi) {
      addLine(d.tenkan, "#2962FF", 1);   // Conversion Line
      addLine(d.kijun, "#B71C1C", 1);     // Base Line
      addLine(d.spanA, "#A5D6A7", 1);     // Leading Span A (displaced +26)
      addLine(d.spanB, "#EF9A9A", 1);     // Leading Span B (displaced +26)
      addLine(d.chikou, "#43A047", 1);    // Lagging Span (displaced −26)
    }
    if (ind.stv && d.stv) {
      addLine(d.stv.o, "#2962FF", 1);     // blue EMA(open)
      addLine(d.stv.c, "#f23645", 1);     // red EMA(shadow)
      addLine(d.stv.stUp, "#22c55e", 2);  // SuperTrend — uptrend (green)
      addLine(d.stv.stDn, "#ef4444", 2);  // SuperTrend — downtrend (red)
    }

    // SMC structure-break markers — legacy (lightweight) and/or LuxAlgo, mergeable
    const m = [];
    if (ind.stv && d.stv) d.stv.markers.forEach(x => m.push(x));
    if (ind.smc) d.breaks.forEach(b => m.push({ time: b.time, position: b.dir === "bull" ? "belowBar" : "aboveBar",
      color: b.dir === "bull" ? "#4ade80" : "#f87171", shape: b.dir === "bull" ? "arrowUp" : "arrowDown", text: b.tag }));
    if (ind.smcLux && d.smc) {
      // swing/internal BOS·CHoCH now drawn as labeled break-lines in the SVG overlay
      if (ss.swings && d.smc.swingPts) d.smc.swingPts.forEach(p => m.push({ time: p.time, position: p.up ? "belowBar" : "aboveBar",
        color: "#8590a3", shape: "circle", text: p.tag }));
    }
    const seen = {}; const mm = [];
    m.sort((a, b) => a.time - b.time).forEach(x => { const k = x.time + x.position; if (!seen[k]) { seen[k] = 1; mm.push(x); } });
    s.candle.setMarkers(mm);

    s.chart.timeScale().fitContent();
  }, [d, ind, smcSub]);

  // refit on fullscreen toggle
  useTCe(() => { const s=seriesRef.current; if(s.chart) setTimeout(()=>s.chart.timeScale().fitContent(),60); }, [full]);

  // Volume Profile overlay (re-aligns to price axis on zoom/pan)
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    let svg = host.querySelector(".tc-vp-ov");
    const draw = () => {
      if (svg) svg.remove(), svg=null;
      if (!ind.vp || !d.vpb) return;
      const W = host.clientWidth, H = host.clientHeight;
      svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
      svg.setAttribute("class","tc-vp-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:3;`;
      const maxW = W * 0.26;
      d.vpb.forEach(b=>{
        const yT = s.candle.priceToCoordinate(b.hi), yB = s.candle.priceToCoordinate(b.lo);
        if (yT==null || yB==null) return;
        const h = Math.max(1, Math.abs(yB-yT)-1);
        const inVA = b.mid<=d.vah && b.mid>=d.val, isPoc = Math.abs(b.mid-d.poc) < (d.vah-d.val)/40;
        const r = document.createElementNS("http://www.w3.org/2000/svg","rect");
        r.setAttribute("x", 0); r.setAttribute("y", Math.min(yT,yB));
        r.setAttribute("width", Math.max(1, b.v/d.vpMax*maxW)); r.setAttribute("height", h);
        r.setAttribute("fill", isPoc?"#d97757":inVA?"#5dd6d6":"#8590a3");
        r.setAttribute("opacity", isPoc?0.5:inVA?0.28:0.16);
        svg.appendChild(r);
      });
      host.appendChild(svg);
    };
    // continuous follow-loop — redraws only when the chart transform actually
    // changes (covers zoom animation, price auto-scale, manual price-drag, resize, fullscreen)
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.vp && d.vpb) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.vp, full]);

  // Money Flow Profile overlay — faithful LuxAlgo-style two-sided profile, anchored
  // to the RIGHT margin (just left of the price axis):
  //   • center  : price-level label boxes
  //   • right    : total money-flow node, tier-colored (yellow high / blue avg / red low) + USD(%)
  //   • left     : sentiment delta — green net-buying / red net-selling + (%)
  //   • POC zone : widest-flow row highlighted with a full-width band
  // Re-aligns to the price axis on zoom/pan/resize via the follow-loop.
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    let svg = host.querySelector(".tc-mfp-ov");
    const SVGNS = "http://www.w3.org/2000/svg";
    const fmtUSD = v => { const a = Math.abs(v); const sgn = v < 0 ? "-" : ""; if (a >= 1e9) return sgn + (a / 1e9).toFixed(2) + "B"; if (a >= 1e6) return sgn + (a / 1e6).toFixed(1) + "M"; if (a >= 1e3) return sgn + (a / 1e3).toFixed(0) + "K"; return sgn + a.toFixed(0); };
    const draw = () => {
      if (svg) svg.remove(), svg = null;
      if (!ind.mfp || !d.mfb) return;
      const W = host.clientWidth, H = host.clientHeight;
      let psw = 56; try { psw = s.chart.priceScale("right").width() || 56; } catch (e) {}
      const plotR = W - psw - 2;
      const labelW = 50, volMaxW = Math.min(150, Math.max(90, W * 0.15)), sentMaxW = Math.min(150, Math.max(90, W * 0.15));
      const labelX = plotR - volMaxW - labelW;     // left edge of price-label box
      const volX0 = labelX + labelW;               // money-flow bars start here, extend right
      if (labelX - sentMaxW < W * 0.30) { /* too narrow; still draw, clamp */ }
      const totMF = d.mfb.reduce((a, x) => a + x.mf, 0) || 1;
      let maxAbsNet = 0; d.mfb.forEach(x => { const n = Math.abs(x.bull - x.bear); if (n > maxAbsNet) maxAbsNet = n; }); maxAbsNet = maxAbsNet || 1;
      svg = document.createElementNS(SVGNS, "svg");
      svg.setAttribute("class", "tc-mfp-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:3;font-family:var(--mono,monospace);`;
      const rect = (x, y, w, h, fill, op, stroke) => { const r = document.createElementNS(SVGNS, "rect"); r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", Math.max(0.5, w)); r.setAttribute("height", Math.max(0.5, h)); if (fill) r.setAttribute("fill", fill); else r.setAttribute("fill", "none"); r.setAttribute("opacity", op); if (stroke) { r.setAttribute("stroke", stroke); r.setAttribute("stroke-width", 1); } svg.appendChild(r); return r; };
      const txt = (x, y, str, fill, anchor, sz) => { const t = document.createElementNS(SVGNS, "text"); t.setAttribute("x", x); t.setAttribute("y", y); t.setAttribute("fill", fill); t.setAttribute("text-anchor", anchor); t.setAttribute("dominant-baseline", "central"); t.setAttribute("font-size", (sz || 9)); t.textContent = str; svg.appendChild(t); };
      d.mfb.forEach(b => {
        if (b.mf <= 0) return;
        const yT = s.candle.priceToCoordinate(b.hi), yB = s.candle.priceToCoordinate(b.lo);
        if (yT == null || yB == null) return;
        const y = Math.min(yT, yB), h = Math.max(1, Math.abs(yB - yT) - 1.5), yc = y + h / 2;
        const ratio = b.mf / d.mfMax;
        const isPoc = Math.abs(b.mid - d.mfpoc) < 1e-9;
        // POC zone band across the whole chart
        if (isPoc) rect(0, y, plotR, h + 1.5, "#ffeb3b", 0.09);
        // ── money-flow node (right of label), tier-colored ──
        const volFill = ratio > 0.53 ? "#ffeb3b" : ratio > 0.37 ? "#2962ff" : "#f23645";
        const volW = Math.max(1, ratio * volMaxW);
        rect(volX0, y, volW, h, volFill, isPoc ? 0.5 : 0.32);
        if (h >= 11 && volW > 46) txt(volX0 + 4, yc, fmtUSD(b.mf) + " (" + (b.mf / totMF * 100).toFixed(1) + "%)", "#e7ebf2", "start", 8.5);
        // ── sentiment delta (left of label) ──
        const net = b.bull - b.bear;
        const sentW = Math.max(1, Math.abs(net) / maxAbsNet * sentMaxW);
        const sentFill = net >= 0 ? "#26a69a" : "#ef5350";
        rect(labelX - sentW, y, sentW, h, sentFill, isPoc ? 0.55 : 0.34);
        if (h >= 11 && sentW > 46) txt(labelX - 4, yc, fmtUSD(net) + " (" + (Math.abs(net) / b.mf * 100).toFixed(0) + "%)", "#e7ebf2", "end", 8.5);
        // ── price-level label box (center) ──
        rect(labelX, y + Math.max(0, (h - 14) / 2), labelW, Math.min(14, h), "rgba(20,26,32,0.78)", 0.92, "rgba(120,140,170,0.45)");
        if (h >= 9) txt(labelX + labelW / 2, yc, b.mid.toFixed(2), "#cfd6e0", "middle", 8.5);
      });
      host.appendChild(svg);
    };
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.mfp && d.mfb) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.mfp, full]);

  // SMC zones overlay — LuxAlgo order blocks / FVG / premium-discount as boxes,
  // anchored to bar-time and extended right; re-aligns to the axes on zoom/pan.
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    let svg = host.querySelector(".tc-smc-ov");
    const draw = () => {
      if (svg) { svg.remove(); svg = null; }
      if (!ind.smcLux || !d.smc) return;
      const sm = d.smc, W = host.clientWidth, H = host.clientHeight;
      const ts = s.chart.timeScale();
      const xOf = t => ts.timeToCoordinate(t);
      const yOf = p => s.candle.priceToCoordinate(p);
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "tc-smc-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:2;`;
      const SVGNS2 = "http://www.w3.org/2000/svg";
      let psw = 56; try { psw = s.chart.priceScale("right").width() || 56; } catch (e) {}
      const rightEdge = W - psw - 2;
      const box = (x0, yT, yB, fill, op, stroke) => {
        if (x0 == null || yT == null || yB == null) return;
        const x = Math.max(0, x0), r = document.createElementNS(SVGNS2, "rect");
        r.setAttribute("x", x); r.setAttribute("y", Math.min(yT, yB));
        r.setAttribute("width", Math.max(2, W - x)); r.setAttribute("height", Math.max(1, Math.abs(yB - yT)));
        r.setAttribute("fill", fill); r.setAttribute("opacity", op);
        if (stroke) { r.setAttribute("stroke", stroke); r.setAttribute("stroke-opacity", "0.5"); r.setAttribute("stroke-width", "1"); }
        svg.appendChild(r);
      };
      const line = (x1, y1, x2, y2, color, dash, w) => { if ([x1, y1, x2, y2].some(v => v == null)) return; const ln = document.createElementNS(SVGNS2, "line"); ln.setAttribute("x1", x1); ln.setAttribute("y1", y1); ln.setAttribute("x2", x2); ln.setAttribute("y2", y2); ln.setAttribute("stroke", color); ln.setAttribute("stroke-width", w || 1); if (dash) ln.setAttribute("stroke-dasharray", dash); ln.setAttribute("opacity", 0.92); svg.appendChild(ln); };
      const rectEl = (x, y, w, h, fill, op) => { const r = document.createElementNS(SVGNS2, "rect"); r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", Math.max(0.5, w)); r.setAttribute("height", Math.max(0.5, h)); r.setAttribute("fill", fill); r.setAttribute("opacity", op); svg.appendChild(r); };
      const label = (x, y, str, color, anchor) => { const t = document.createElementNS(SVGNS2, "text"); t.setAttribute("x", x); t.setAttribute("y", y); t.setAttribute("fill", color); t.setAttribute("text-anchor", anchor || "start"); t.setAttribute("dominant-baseline", "central"); t.setAttribute("font-size", 9.5); t.setAttribute("font-family", "var(--mono,monospace)"); t.textContent = str; svg.appendChild(t); };
      const fmtVol = v => { const a = Math.abs(v); if (a >= 1e9) return (a / 1e9).toFixed(1) + "B"; if (a >= 1e6) return (a / 1e6).toFixed(1) + "M"; if (a >= 1e3) return (a / 1e3).toFixed(0) + "K"; return a.toFixed(0); };
      // premium / discount / equilibrium bands (anchored at last swing extreme)
      if (ss.zones && sm.trailing && sm.trailing.startTime != null) {
        const x0 = xOf(sm.trailing.startTime), tp = sm.trailing.top, bt = sm.trailing.bottom;
        if (x0 != null) {
          box(x0, yOf(tp), yOf(0.95 * tp + 0.05 * bt), "#f87171", 0.07);
          box(x0, yOf(0.525 * tp + 0.475 * bt), yOf(0.525 * bt + 0.475 * tp), "#8590a3", 0.07);
          box(x0, yOf(0.95 * bt + 0.05 * tp), yOf(bt), "#4ade80", 0.07);
        }
      }
      // order blocks (swing = bordered, internal = lighter fill) — each gated
      const obs = [...(ss.swingOB ? sm.swingOB : []), ...(ss.intOB ? sm.intOB : [])];
      obs.forEach(o => {
        const x0 = xOf(o.time), yT = yOf(o.high), yB = yOf(o.low);
        box(x0, yT, yB, o.bias > 0 ? "#5b9bf2" : "#f87171", o.internal ? 0.10 : 0.16, o.internal ? null : (o.bias > 0 ? "#5b9bf2" : "#f87171"));
        // volumetric: buy/sell split bar + total-volume label at the OB's left edge
        if (ss.vol && o.vol > 0 && x0 != null && yT != null && yB != null) {
          const y = Math.min(yT, yB), h = Math.abs(yB - yT), bx = Math.max(0, x0);
          const buyFrac = Math.max(0, Math.min(1, o.buyVol / o.vol));
          rectEl(bx, y, 4, h * (1 - buyFrac), "#ef5350", 0.85);
          rectEl(bx, y + h * (1 - buyFrac), 4, h * buyFrac, "#26a69a", 0.85);
          if (h >= 12) label(bx + 7, y + h / 2, fmtVol(o.vol) + " · " + Math.round(buyFrac * 100) + "%▲", "#dfe5ee", "start");
        }
      });
      // fair value gaps
      if (ss.fvg) sm.fvg.forEach(g => box(xOf(g.time), yOf(g.top), yOf(g.bottom), g.bias > 0 ? "#4ade80" : "#f87171", 0.09));
      // swing / internal structure as labeled BOS·CHoCH break-lines
      const drawStruct = (arr, solid) => arr.forEach(b => { const x1 = xOf(b.fromTime), x2 = xOf(b.time), y = yOf(b.level); if (x1 == null || x2 == null || y == null) return; const col = b.dir === "up" ? "#4ade80" : "#f87171"; line(x1, y, x2, y, col, solid ? null : "2 3", solid ? 1.4 : 1); label(x2 + 3, y, b.tag, col, "start"); });
      if (ss.swing) drawStruct(sm.struct.slice(-8), true);
      if (ss.internal) drawStruct(sm.intStruct.slice(-10), false);
      // EQH / EQL as paired connector lines between the two equal pivots
      if (ss.eq) sm.equal.forEach(e => { const x1 = xOf(e.fromTime), x2 = xOf(e.toTime), y = yOf(e.level); if (x1 == null || x2 == null || y == null) return; const col = e.tag === "EQH" ? "#f0a35e" : "#5fb0e0"; line(x1, y, x2, y, col, "1 2", 1.2); label(x2 + 3, y, e.tag, col, "start"); });
      // MTF previous-period High/Low levels (PD/PW/PM) as dashed rays + labels
      if (ss.mtf && d.mtfLevels) {
        const colOf = { day: "#5b9bf2", week: "#f59e0b", month: "#a78bfa" };
        d.mtfLevels.forEach(Lv => { const y = yOf(Lv.level); if (y == null) return; const c = colOf[Lv.kind] || "#8590a3"; line(0, y, rightEdge, y, c, "5 4", 1); label(rightEdge - 4, y, Lv.tag + " " + Lv.level.toFixed(2), c, "end"); });
      }
      host.appendChild(svg);
    };
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.smcLux && d.smc) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.smcLux, smcSub, full]);

  // Ichimoku Kumo cloud fill — green where Span A ≥ Span B, red otherwise.
  // Filled per-segment between the displaced spans; re-aligns on zoom/pan.
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    const NS = "http://www.w3.org/2000/svg";
    let svg = host.querySelector(".tc-kumo-ov");
    const draw = () => {
      if (svg) { svg.remove(); svg = null; }
      if (!ind.ichi || !d.spanA || !d.spanB) return;
      const A = d.spanA, B = d.spanB, W = host.clientWidth, H = host.clientHeight;
      const ts = s.chart.timeScale();
      const xOf = t => ts.timeToCoordinate(t);
      const yOf = p => s.candle.priceToCoordinate(p);
      svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "tc-kumo-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:1;`;
      for (let i = 1; i < A.length; i++) {
        const x0 = xOf(A[i - 1].time), x1 = xOf(A[i].time);
        if (x0 == null || x1 == null) continue;
        const a0 = yOf(A[i - 1].value), a1 = yOf(A[i].value), b0 = yOf(B[i - 1].value), b1 = yOf(B[i].value);
        if (a0 == null || a1 == null || b0 == null || b1 == null) continue;
        const bull = (A[i - 1].value + A[i].value) >= (B[i - 1].value + B[i].value);
        const poly = document.createElementNS(NS, "polygon");
        poly.setAttribute("points", `${x0},${a0} ${x1},${a1} ${x1},${b1} ${x0},${b0}`);
        poly.setAttribute("fill", bull ? "rgba(67,160,71,0.16)" : "rgba(244,67,54,0.16)");
        svg.appendChild(poly);
      }
      host.appendChild(svg);
    };
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.ichi && d.spanA && d.spanB) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.ichi, full]);

  // FVG · LuxAlgo box overlay — green/red gaps from formation to +extend, mitigated removed
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    const NS = "http://www.w3.org/2000/svg";
    let svg = host.querySelector(".tc-fvg-ov");
    const draw = () => {
      if (svg) { svg.remove(); svg = null; }
      if (!ind.fvgLux || !d.fvgLux || !d.fvgLux.length) return;
      const W = host.clientWidth, H = host.clientHeight, ts = s.chart.timeScale();
      svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "tc-fvg-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:2;`;
      for (const g of d.fvgLux) {
        const x0 = ts.timeToCoordinate(g.t0), x1 = ts.timeToCoordinate(g.t1);
        const yT = s.candle.priceToCoordinate(g.top), yB = s.candle.priceToCoordinate(g.bottom);
        if (x0 == null || x1 == null || yT == null || yB == null) continue;
        const r = document.createElementNS(NS, "rect");
        r.setAttribute("x", Math.min(x0, x1)); r.setAttribute("y", Math.min(yT, yB));
        r.setAttribute("width", Math.max(2, Math.abs(x1 - x0))); r.setAttribute("height", Math.max(1, Math.abs(yB - yT)));
        r.setAttribute("fill", g.bias > 0 ? "rgba(8,153,129,0.30)" : "rgba(242,54,69,0.30)");
        svg.appendChild(r);
      }
      host.appendChild(svg);
    };
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.fvgLux && d.fvgLux) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.fvgLux, full]);

  // Super Trend V trend-cloud fill — green where c ≥ o (blue EMA), orange otherwise
  useTCe(() => {
    const s = seriesRef.current; if (!s.chart) return;
    const host = wrap.current; if (!host) return;
    const NS = "http://www.w3.org/2000/svg";
    let svg = host.querySelector(".tc-stv-ov");
    const draw = () => {
      if (svg) { svg.remove(); svg = null; }
      if (!ind.stv || !d.stv) return;
      const C = d.stv.c, O = d.stv.o, W = host.clientWidth, H = host.clientHeight, ts = s.chart.timeScale();
      svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "tc-stv-ov");
      svg.style.cssText = `position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;z-index:1;`;
      for (let i = 1; i < C.length; i++) {
        const x0 = ts.timeToCoordinate(C[i - 1].time), x1 = ts.timeToCoordinate(C[i].time);
        if (x0 == null || x1 == null) continue;
        const c0 = s.candle.priceToCoordinate(C[i - 1].value), c1 = s.candle.priceToCoordinate(C[i].value);
        const o0 = s.candle.priceToCoordinate(O[i - 1].value), o1 = s.candle.priceToCoordinate(O[i].value);
        if (c0 == null || c1 == null || o0 == null || o1 == null) continue;
        const up = (C[i - 1].value + C[i].value) >= (O[i - 1].value + O[i].value);
        const poly = document.createElementNS(NS, "polygon");
        poly.setAttribute("points", `${x0},${c0} ${x1},${c1} ${x1},${o1} ${x0},${o0}`);
        poly.setAttribute("fill", up ? "rgba(50,205,50,0.16)" : "rgba(255,165,0,0.16)");
        svg.appendChild(poly);
      }
      host.appendChild(svg);
    };
    draw();
    let _raf = 0, _sig = "", _pMin = Infinity, _pMax = -Infinity;
    for (const bb of d.bars) { if (bb.low < _pMin) _pMin = bb.low; if (bb.high > _pMax) _pMax = bb.high; }
    const _ts = s.chart.timeScale();
    const _sigOf = () => `${host.clientWidth}x${host.clientHeight}|${s.candle.priceToCoordinate(_pMin)}|${s.candle.priceToCoordinate(_pMax)}|${_ts.timeToCoordinate(d.bars[0].time)}|${_ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const _loop = () => { const ns = _sigOf(); if (ns !== _sig) { _sig = ns; draw(); } _raf = requestAnimationFrame(_loop); };
    if (ind.stv && d.stv) _loop();
    return () => { if (_raf) cancelAnimationFrame(_raf); if (svg) svg.remove(); };
  }, [d, ind.stv, full]);

  // RSI(14) sub-pane — SVG synced to the main chart's time axis via the follow-loop
  useTCe(() => {
    const s = seriesRef.current; const host = rsiWrap.current;
    if (!host || !s.chart) return;
    const ts = s.chart.timeScale();
    const draw = () => {
      if (!ind.rsi || !d.rsi || !d.rsi.length) { host.innerHTML = ""; return; }
      const W = host.clientWidth, H = host.clientHeight, padR = 46, padT = 6, padB = 6, ph = H - padT - padB;
      const yOf = v => padT + ph * (1 - v / 100);
      let pts = ""; for (const p of d.rsi) { const x = ts.timeToCoordinate(p.time); if (x == null) continue; pts += `${x.toFixed(1)},${yOf(p.value).toFixed(1)} `; }
      const hl = (v, dash) => `<line x1="0" y1="${yOf(v).toFixed(1)}" x2="${(W - padR).toFixed(1)}" y2="${yOf(v).toFixed(1)}" stroke="#787B86" stroke-opacity="0.5" stroke-dasharray="${dash}"/><text x="${(W - padR + 4).toFixed(1)}" y="${(yOf(v) + 3).toFixed(1)}" fill="#787B86" font-size="9" font-family="monospace">${v}</text>`;
      host.innerHTML = `<svg width="${W}" height="${H}" style="display:block"><rect x="0" y="${yOf(70).toFixed(1)}" width="${(W - padR).toFixed(1)}" height="${(yOf(30) - yOf(70)).toFixed(1)}" fill="rgba(126,87,194,0.08)"/>${hl(70, "2 2")}${hl(50, "1 3")}${hl(30, "2 2")}<polyline points="${pts.trim()}" fill="none" stroke="#7E57C2" stroke-width="1.4"/><text x="4" y="12" fill="#7E57C2" font-size="10" font-family="monospace" font-weight="600">RSI 14</text></svg>`;
    };
    draw();
    let raf = 0, sig = "";
    const sigOf = () => `${host.clientWidth}x${host.clientHeight}|${ts.timeToCoordinate(d.bars[0].time)}|${ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const loop = () => { const ns = sigOf(); if (ns !== sig) { sig = ns; draw(); } raf = requestAnimationFrame(loop); };
    if (ind.rsi) loop();
    return () => { if (raf) cancelAnimationFrame(raf); host.innerHTML = ""; };
  }, [d, ind.rsi, full]);

  // MACD(12,26,9) sub-pane — histogram + MACD/signal lines, synced to main time axis
  useTCe(() => {
    const s = seriesRef.current; const host = macdWrap.current;
    if (!host || !s.chart) return;
    const ts = s.chart.timeScale();
    const draw = () => {
      if (!ind.macd || !d.macd || !d.macd.length) { host.innerHTML = ""; return; }
      const W = host.clientWidth, H = host.clientHeight, padR = 46, padT = 6, padB = 6, ph = H - padT - padB;
      let mx = 0; for (const p of d.macd) mx = Math.max(mx, Math.abs(p.macd), Math.abs(p.signal), Math.abs(p.hist)); mx = mx || 1;
      const yOf = v => padT + ph * (0.5 - 0.5 * (v / mx)); const zeroY = yOf(0);
      let cols = "", mp = "", sp = ""; const bw = 2;
      for (let i = 0; i < d.macd.length; i++) { const p = d.macd[i], x = ts.timeToCoordinate(p.time); if (x == null) continue;
        const prev = i > 0 ? d.macd[i - 1].hist : p.hist;
        const col = p.hist >= 0 ? (p.hist > prev ? "#26a69a" : "#b2dfdb") : (p.hist > prev ? "#ffcdd2" : "#ff5252");
        const y = yOf(p.hist); cols += `<rect x="${(x - bw / 2).toFixed(1)}" y="${Math.min(y, zeroY).toFixed(1)}" width="${bw}" height="${Math.abs(y - zeroY).toFixed(1)}" fill="${col}"/>`;
        mp += `${x.toFixed(1)},${yOf(p.macd).toFixed(1)} `; sp += `${x.toFixed(1)},${yOf(p.signal).toFixed(1)} `;
      }
      host.innerHTML = `<svg width="${W}" height="${H}" style="display:block"><line x1="0" y1="${zeroY.toFixed(1)}" x2="${(W - padR).toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="#787B86" stroke-opacity="0.5"/>${cols}<polyline points="${mp.trim()}" fill="none" stroke="#2962FF" stroke-width="1.3"/><polyline points="${sp.trim()}" fill="none" stroke="#ff6d00" stroke-width="1.3"/><text x="4" y="12" fill="#9aa6a1" font-size="10" font-family="monospace" font-weight="600">MACD 12/26/9</text></svg>`;
    };
    draw();
    let raf = 0, sig = "";
    const sigOf = () => `${host.clientWidth}x${host.clientHeight}|${ts.timeToCoordinate(d.bars[0].time)}|${ts.timeToCoordinate(d.bars[d.bars.length - 1].time)}`;
    const loop = () => { const ns = sigOf(); if (ns !== sig) { sig = ns; draw(); } raf = requestAnimationFrame(loop); };
    if (ind.macd) loop();
    return () => { if (raf) cancelAnimationFrame(raf); host.innerHTML = ""; };
  }, [d, ind.macd, full]);

  return (
    <>
      <div ref={wrap} className="tc-lw" />
      {ind.macd && <div ref={macdWrap} className="tc-osc" style={{ width: "100%", height: 120, position: "relative", borderTop: "1px solid var(--glass-line)", marginTop: 2 }} />}
      {ind.rsi && <div ref={rsiWrap} className="tc-osc" style={{ width: "100%", height: 120, position: "relative", borderTop: "1px solid var(--glass-line)", marginTop: 2 }} />}
    </>
  );
}
window.LensChart = LensChart;