// lens-thesis-chart.jsx — Thesis Chart on TradingView Lightweight Charts.
// Real candles + volume + crosshair + zoom/pan + price axis, with thesis overlays:
// plan price-lines, EMA/Bollinger/VWAP/Ichimoku series, SMC markers. Overrides window.LensChart.

const { useMemo: useTC, useState: useTCs, useRef: useTCr, useEffect: useTCe } = React;

// real-candle fetch config per timeframe (/api/ohlcv). 1W: endpoint returns daily → resample.
const TF_FETCH = {
  "1H": { tf: "1H", days: 90 }, "4H": { tf: "4H", days: 250 },
  "1D": { tf: "1D", days: 400 }, "1W": { tf: "1D", days: 1825, resample: "W" },
};
const TF_NOTE = { "1H": "execution timeframe", "4H": "swing-trigger timeframe", "1D": "thesis timeframe", "1W": "context timeframe" };

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
      BV.get(`/api/ohlcv/${encodeURIComponent(sym)}?tf=${cfg.tf}&days=${cfg.days}`).then(res => { if (on) setM(prev => ({ ...prev, [k]: quickBias(_barsFrom(res, cfg)) })); }).catch(() => {});
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

// compute all overlays/indicators from REAL bars (logic unchanged — now fed real data)
function computeIndicators(bars, lv) {
  const ema = (per) => { const k = 2 / (per + 1); let pr = bars[0].close; return bars.map((b, i) => { pr = i === 0 ? b.close : b.close * k + pr * (1 - k); return { time: b.time, value: +pr.toFixed(2) }; }); };
  const e9 = ema(9), e21 = ema(21), e50 = ema(50);
  const bbU = [], bbM = [], bbL = [];
  bars.forEach((b, i) => { const s = Math.max(0, i - 19), w = bars.slice(s, i + 1).map(x => x.close); const m = w.reduce((a, c) => a + c, 0) / w.length; const sd = Math.sqrt(w.reduce((a, c) => a + (c - m) ** 2, 0) / w.length); bbM.push({ time: b.time, value: +m.toFixed(2) }); bbU.push({ time: b.time, value: +(m + 2 * sd).toFixed(2) }); bbL.push({ time: b.time, value: +(m - 2 * sd).toFixed(2) }); });
  const anchor = Math.floor(bars.length * 0.82); let pv = 0, cv = 0; const avwap = [];
  bars.forEach((b, i) => { if (i >= anchor) { const tp = (b.high + b.low + b.close) / 3; pv += tp * b.value; cv += b.value; avwap.push({ time: b.time, value: +(cv ? pv / cv : b.close).toFixed(2) }); } });
  const hh = (per, i) => Math.max(...bars.slice(Math.max(0, i - per + 1), i + 1).map(b => b.high));
  const ll = (per, i) => Math.min(...bars.slice(Math.max(0, i - per + 1), i + 1).map(b => b.low));
  const tenkan = [], kijun = [], spanA = [], spanB = [];
  bars.forEach((b, i) => { const t = (hh(9, i) + ll(9, i)) / 2, k = (hh(26, i) + ll(26, i)) / 2; tenkan.push({ time: b.time, value: +t.toFixed(2) }); kijun.push({ time: b.time, value: +k.toFixed(2) }); spanA.push({ time: b.time, value: +((t + k) / 2).toFixed(2) }); spanB.push({ time: b.time, value: +((hh(52, i) + ll(52, i)) / 2).toFixed(2) }); });
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
  const last = bars[bars.length - 1].close;
  return { spot: last, entry: +(lv.pivot || last).toFixed(2), stop: +(lv.stop || last * 0.94).toFixed(2), t1: +(lv.t1 || last * 1.06).toFixed(2), t2: +(lv.t2 || last * 1.12).toFixed(2), validPlan: !!lv.valid,
    bars, e9, e21, e50, bbU, bbM, bbL, avwap, tenkan, kijun, spanA, spanB, breaks: breaks.slice(-6), obs, vpb, vpMax, poc: vpb[pocI].mid, vah: vpb[vhiI].hi, val: vpb[vloI].lo };
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

function LensChart({ ticker, mode }) {
  const modeTf = mode === "POSITION" ? "1D" : mode === "INVESTMENT" ? "1W" : "4H";
  const [tf, setTf] = useTCs(modeTf);
  // follow the global mode unless the user has manually picked a timeframe
  const [tfTouched, setTfTouched] = useTCs(false);
  React.useEffect(() => { if (!tfTouched) setTf(modeTf); }, [modeTf]);
  const [full, setFull] = useTCs(false);
  const [indMenu, setIndMenu] = useTCs(false);
  const [ind, setInd] = useTCs({ ema:false, bb:false, avwap:false, ichi:false, smc:false, vp:false });
  const togInd = (k) => setInd(s => ({ ...s, [k]: !s[k] }));

  // REAL candles for the active timeframe + multi-timeframe biases + live news
  const barsRaw = useCandles(ticker.symbol, tf);
  const loading = barsRaw === null, failed = barsRaw === false;
  const lv = window.coherentLevels ? window.coherentLevels(ticker) : { price: ticker.price, pivot: ticker.price, stop: ticker.price * 0.94, t1: ticker.price * 1.06, t2: ticker.price * 1.12, valid: false };
  const d = useTC(() => (barsRaw && barsRaw.length >= 5) ? computeIndicators(barsRaw, lv) : null, [barsRaw, lv.pivot, lv.stop, lv.t1, lv.t2]);
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
                {[["ema","EMA 9/21/50"],["bb","Bollinger 20·2"],["avwap","Anchored VWAP"],["ichi","Ichimoku Cloud"],["vp","Volume Profile"],["smc","Smart Money Concepts"]].map(([k,l])=>(
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
        {["1H","4H","1D","1W"].map(k=>(
          <button key={k} className={`tc-tf ${tf===k?"is-on":""}`} onClick={()=>{ setTfTouched(true); setTf(k); }}>
            <span className="mono">{k}</span>
            <span className={`mono kpi-tone--${biasTone(mtf[k])}`}>{mtf[k] || "…"}</span>
          </button>
        ))}
        <div className="tc-tf-read">
          <span className={`tc-tf-tag mono kpi-tone--${tone3(tfx.tone)}`}>{tf} · {tfx.bias}</span>
          <span className="mono tc-tf-txt">{tfx.read}</span>
          <span className="mono dim2 tc-tf-struct">{tfx.struct} · <i>{TF_NOTE[tf]}</i></span>
        </div>
      </div>

      <div className="tc-chart-card">
        {loading ? <div className="tc-lw" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono dim2">loading real {tf} candles…</span></div>
          : (failed || !d) ? <div className="tc-lw" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono dim2">No {tf} candles available for {ticker.symbol}.</span></div>
            : <LWChart d={d} ind={ind} full={full} />}
        {d && <div className="tc-legend mono">
          <span><i className="tc-sw tc-sw--cop"/>{d.validPlan ? "entry" : "~entry"} ${d.entry}</span>
          <span><i className="tc-sw tc-sw--rd"/>stop ${d.stop}</span>
          <span><i className="tc-sw tc-sw--gn"/>T1 ${d.t1} · T2 ${d.t2}</span>
          {ind.ema && <span><i className="tc-sw" style={{background:"var(--cy)"}}/>EMA 9/21/50</span>}
          {ind.bb && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>Bollinger</span>}
          {ind.avwap && <span><i className="tc-sw" style={{background:"var(--amb)"}}/>aVWAP</span>}
          {ind.ichi && <span><i className="tc-sw" style={{background:"var(--gn)"}}/>Ichimoku</span>}
          {ind.smc && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>SMC · BOS/CHoCH/OB</span>}
          {ind.vp && <span><i className="tc-sw tc-sw--cop"/>POC <i className="tc-sw" style={{background:"var(--cy)"}}/>value area · volume profile</span>}
          <span className="dim2">drag to pan · scroll to zoom · hover for OHLC</span>
        </div>}
        <NewsFlags news={news} bars={d ? d.bars : null} />
      </div>

      {!full && <ReplayPractice ticker={ticker} />}

      {!full && d && <div className="lens-call">
        <span className="label-cap">The Read · Chart · {tf}</span>
        <span className="mono"><b className={`kpi-tone--${tone3(tfx.tone)}`}>{tfx.bias}</b> on {tf} — {tfx.read} {d.validPlan ? <>Plan: entry <b className="cy">${d.entry}</b>, stop <b className="dn">${d.stop}</b>, targets <b className="up">${d.t1}/${d.t2}</b>.</> : <>No active scan trade-plan — levels shown are price-estimates.</>}</span>
      </div>}
    </div>
  );
}

function LWChart({ d, ind, full }) {
  const wrap = useTCr(null);
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
    s.candle.setData(d.bars);
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
    if (ind.smc) d.obs.forEach(o => s.priceLines.push(mk(o.price, o.bias==="bull"?"#5b9bf2":"#d97757", o.bias==="bull"?"+OB":"−OB")));

    // overlay line series
    s.overlays.forEach(o => s.chart.removeSeries(o)); s.overlays=[];
    const addLine = (data,color,width=1,style=0) => { const ls=s.chart.addLineSeries({ color, lineWidth:width, lineStyle:style, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }); ls.setData(data); s.overlays.push(ls); };
    if (ind.ema) { addLine(d.e9,"#5dd6d6"); addLine(d.e21,"#fbbf24"); addLine(d.e50,"#a78bfa"); }
    if (ind.bb) { addLine(d.bbU,"#5b9bf2",1,2); addLine(d.bbM,"#5b9bf2",1,1); addLine(d.bbL,"#5b9bf2",1,2); }
    if (ind.avwap) addLine(d.avwap,"#fbbf24",2,2);
    if (ind.ichi) { addLine(d.spanA,"#4ade80"); addLine(d.spanB,"#f87171"); addLine(d.tenkan,"#5b9bf2",1); addLine(d.kijun,"#f87171",1); }

    // SMC structure-break markers
    s.candle.setMarkers(ind.smc ? d.breaks.map(b=>({
      time:b.time, position: b.dir==="bull"?"belowBar":"aboveBar",
      color: b.dir==="bull"?"#4ade80":"#f87171", shape: b.dir==="bull"?"arrowUp":"arrowDown", text:b.tag,
    })) : []);

    s.chart.timeScale().fitContent();
  }, [d, ind]);

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
    draw();
    const ts = s.chart.timeScale();
    const onRange = () => draw();
    ts.subscribeVisibleLogicalRangeChange(onRange);
    return () => { ts.unsubscribeVisibleLogicalRangeChange(onRange); if(svg) svg.remove(); };
  }, [d, ind.vp, full]);

  return <div ref={wrap} className="tc-lw" />;
}
// ─── Replay / Practice mode — step historical bars, place paper entries ──
function ReplayPractice({ ticker }) {
  // REAL historical daily bars — step through actual price action, not a seeded curve
  const raw = useCandles(ticker.symbol, "1D");
  const bars = useTC(() => (raw && raw.length >= 40)
    ? raw.slice(-90).map(b => ({ o: b.open, h: b.high, l: b.low, c: b.close }))
    : null, [raw]);

  const START = 28;
  const [idx, setIdx] = useTCs(START);
  const [playing, setPlaying] = useTCs(false);
  const [entry, setEntry] = useTCs(null);     // { price, i }
  const [trades, setTrades] = useTCs([]);
  const nBars = bars ? bars.length : 0;
  const atEnd = idx >= nBars - 1;

  React.useEffect(() => {
    if (!playing || !nBars) return;
    const t = setInterval(() => setIdx(i => (i >= nBars - 1 ? i : i + 1)), 650);
    return () => clearInterval(t);
  }, [playing, nBars]);
  React.useEffect(() => { if (atEnd) setPlaying(false); }, [atEnd]);

  if (!bars || !bars.length) return (
    <div className="rp"><div className="rp-head"><div className="rp-head-l"><span className="rp-tag mono">PRACTICE · REPLAY</span><span className="rp-sub mono dim2">loading real historical bars…</span></div></div></div>
  );
  const cur = bars[Math.min(idx, bars.length - 1)];
  const livePct = entry ? (cur.c - entry.price) / entry.price * 100 : null;
  const buy = () => setEntry({ price: cur.c, i: idx });
  const sell = () => {
    if (!entry) return;
    const pct = (cur.c - entry.price) / entry.price * 100;
    setTrades(t => [{ entry: entry.price, exit: cur.c, pct: +pct.toFixed(2), held: idx - entry.i, win: pct >= 0 }, ...t].slice(0, 8));
    setEntry(null);
  };
  const reset = () => { setIdx(START); setEntry(null); setPlaying(false); setTrades([]); };
  const step = (d) => { setPlaying(false); setIdx(i => Math.max(START, Math.min(bars.length - 1, i + d))); };

  // chart geometry — full width reserved, reveal up to idx
  const W = 760, H = 196, padL = 8, padR = 46, padT = 10, padB = 8;
  const vis = bars.slice(0, idx + 1);
  const lo = Math.min(...vis.map(b => b.l)), hi = Math.max(...vis.map(b => b.h));
  const x = i => padL + (i / (bars.length - 1)) * (W - padL - padR);
  const y = v => padT + (1 - (v - lo) / ((hi - lo) || 1)) * (H - padT - padB);
  const bw = Math.max(2, (W - padL - padR) / bars.length * 0.62);

  const wins = trades.filter(t => t.win).length;
  const avg = trades.length ? trades.reduce((a, t) => a + t.pct, 0) / trades.length : 0;

  return (
    <div className="rp">
      <div className="rp-head">
        <div className="rp-head-l">
          <span className="rp-tag mono">PRACTICE · REPLAY</span>
          <span className="rp-sub mono dim2">step the bars · place paper entries · see how they'd have worked — no live money</span>
        </div>
        <div className="rp-stats mono">
          <span>Bar <b>{idx - START + 1}</b>/<b>{bars.length - START}</b></span>
          {trades.length > 0 && <><span className="rp-sep">·</span><span>{wins}/{trades.length} wins</span><span className="rp-sep">·</span><span className={avg >= 0 ? "up" : "dn"}>avg {avg >= 0 ? "+" : ""}{avg.toFixed(2)}%</span></>}
        </div>
      </div>

      <div className="rp-chart">
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="rp-svg">
          {entry && <line x1={padL} y1={y(entry.price)} x2={W - padR} y2={y(entry.price)} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.8" />}
          {entry && <text x={W - padR + 3} y={y(entry.price) + 3} fontSize="9" className="mono" fill="var(--copper)">entry ${entry.price.toFixed(2)}</text>}
          {vis.map((b, i) => {
            const up = b.c >= b.o;
            const col = up ? "var(--gn)" : "var(--rd)";
            return (
              <g key={i}>
                <line x1={x(i)} y1={y(b.h)} x2={x(i)} y2={y(b.l)} stroke={col} strokeWidth="1" opacity="0.85" />
                <rect x={x(i) - bw / 2} y={y(Math.max(b.o, b.c))} width={bw} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} fill={col} opacity="0.9" />
              </g>
            );
          })}
          {/* current price marker */}
          <line x1={padL} y1={y(cur.c)} x2={x(idx)} y2={y(cur.c)} stroke="var(--ink-3)" strokeDasharray="1 4" opacity="0.5" />
          <text x={W - padR + 3} y={y(cur.c) + 3} fontSize="9.5" className="mono" fill="var(--ink-1)" fontWeight="700">${cur.c.toFixed(2)}</text>
        </svg>
      </div>

      <div className="rp-bar">
        <div className="rp-ctrls">
          <button className="rp-btn" onClick={reset} title="Reset">⏮</button>
          <button className="rp-btn" onClick={() => step(-1)} disabled={idx <= START} title="Back">◀</button>
          <button className="rp-btn rp-btn--play" onClick={() => setPlaying(p => !p)} disabled={atEnd}>{playing ? "⏸ Pause" : "▶ Play"}</button>
          <button className="rp-btn" onClick={() => step(1)} disabled={atEnd} title="Forward">▶▮</button>
        </div>
        <div className="rp-trade">
          {entry ? (
            <>
              <span className={`rp-live mono ${livePct >= 0 ? "up" : "dn"}`}>{livePct >= 0 ? "+" : ""}{livePct.toFixed(2)}% <span className="dim2">open</span></span>
              <button className="rp-act rp-act--sell" onClick={sell}>Sell at ${cur.c.toFixed(2)}</button>
            </>
          ) : (
            <button className="rp-act rp-act--buy" onClick={buy} disabled={atEnd}>Buy at ${cur.c.toFixed(2)}</button>
          )}
        </div>
      </div>

      {trades.length > 0 && (
        <div className="rp-log mono">
          {trades.map((t, i) => (
            <span key={i} className={`rp-log-row ${t.win ? "up" : "dn"}`}>
              ${t.entry.toFixed(2)}→${t.exit.toFixed(2)} <b>{t.pct >= 0 ? "+" : ""}{t.pct}%</b> <span className="dim2">{t.held}b</span>
            </span>
          ))}
        </div>
      )}
      <div className="rp-foot mono dim2">Practice only — hindsight on past bars to build pattern-reading skill. Not advice; results don't predict the future.</div>
    </div>
  );
}

window.LensChart = LensChart;