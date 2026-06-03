// lens-thesis-chart.jsx — Thesis Chart on TradingView Lightweight Charts.
// Real candles + volume + crosshair + zoom/pan + price axis, with thesis overlays:
// plan price-lines, EMA/Bollinger/VWAP/Ichimoku series, SMC markers. Overrides window.LensChart.

const { useMemo: useTC, useState: useTCs, useRef: useTCr, useEffect: useTCe } = React;

const TF_THESIS = {
  "1H": { bias:"BULL", tone:"up", read:"Intraday uptrend — higher-lows, holding VWAP. Tactical entries on pullbacks to the rising 21-EMA.", struct:"BOS ↑ · OB holding", note:"execution timeframe" },
  "4H": { bias:"BULL", tone:"up", read:"Swing leg intact — clean break of prior 4H range, no CHoCH. MACD above signal.", struct:"BOS ↑ · FVG below", note:"swing trigger timeframe" },
  "1D": { bias:"BULL", tone:"up", read:"Primary trend up — base #2 breakout above pivot on +1.6× RVOL, stacked EMAs, above cloud.", struct:"BOS ↑ · above Kumo", note:"thesis timeframe" },
  "1W": { bias:"NEUTRAL", tone:"amb", read:"Higher-timeframe still basing — range-bound. Bull thesis valid but HTF resistance overhead; size down.", struct:"range · no break", note:"context timeframe" },
};
const TF_CFG = { "1H": {step:3600, n:120, vol:0.004}, "4H": {step:14400, n:120, vol:0.008}, "1D": {step:86400, n:160, vol:0.013}, "1W": {step:604800, n:120, vol:0.028} };

// news-on-chart overlay — sentiment-colored event flags along the timeline
function NewsFlags() {
  const events = [
    { x: 8, tone: "gn", d: "Goldman BUY · PT raise", s: "+0.7" },
    { x: 26, tone: "gn", d: "CFO open-market buy", s: "+0.5" },
    { x: 44, tone: "rd", d: "Sector cycle-peak warning", s: "−0.4" },
    { x: 61, tone: "gn", d: "Capacity expansion update", s: "+0.8" },
    { x: 82, tone: "amb", d: "ER in 11d · implied ±6.4%", s: "ER" },
  ];
  return (
    <div className="tc-news">
      <span className="tc-news-lbl mono dim2">NEWS</span>
      <div className="tc-news-track">
        {events.map((e, i) => (
          <span key={i} className={`tc-news-flag tc-news-flag--${e.tone}`} style={{ left: `${e.x}%` }} title={`${e.d} · sentiment ${e.s}`}>
            <span className="tc-news-dot" />
          </span>
        ))}
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
  const tfx = TF_THESIS[tf];

  const d = useTC(() => {
    const spot = ticker.price;
    const entry = +(spot*1.002).toFixed(2), stop=+(spot*0.943).toFixed(2), t1=+(spot*1.08).toFixed(2), t2=+(spot*1.16).toFixed(2);
    const cfg = TF_CFG[tf];
    const now = Math.floor(Date.now()/1000), start = now - cfg.n*cfg.step;
    const bars=[]; let p = spot*0.80;
    for(let i=0;i<cfg.n;i++){
      const phase = i<cfg.n*0.35?0.004 : i<cfg.n*0.62?-0.0015 : i<cfg.n*0.83?0.0008 : 0.006;
      const noise = (Math.sin(i*0.7)+Math.cos(i*0.33))*cfg.vol;
      p = p*(1+phase+noise);
      const o=p*(1-Math.random()*cfg.vol), c=p*(1+(Math.random()-0.45)*cfg.vol*1.6);
      const hi=Math.max(o,c)*(1+Math.random()*cfg.vol), lo=Math.min(o,c)*(1-Math.random()*cfg.vol);
      const v=(0.5+Math.abs(Math.sin(i*0.5))*0.7+(i>cfg.n*0.82?0.6:0))*1e6;
      bars.push({ time:start+i*cfg.step, open:+o.toFixed(2), high:+hi.toFixed(2), low:+lo.toFixed(2), close:+c.toFixed(2), value:Math.round(v) });
    }
    bars[bars.length-1].close = spot;
    const ema=(per)=>{ const k=2/(per+1); let pr=bars[0].close; return bars.map((b,i)=>{ pr=i===0?b.close:b.close*k+pr*(1-k); return {time:b.time,value:+pr.toFixed(2)}; }); };
    const e9=ema(9),e21=ema(21),e50=ema(50);
    const bbU=[],bbM=[],bbL=[];
    bars.forEach((b,i)=>{ const s=Math.max(0,i-19),w=bars.slice(s,i+1).map(x=>x.close); const m=w.reduce((a,c)=>a+c,0)/w.length; const sd=Math.sqrt(w.reduce((a,c)=>a+(c-m)**2,0)/w.length); bbM.push({time:b.time,value:+m.toFixed(2)}); bbU.push({time:b.time,value:+(m+2*sd).toFixed(2)}); bbL.push({time:b.time,value:+(m-2*sd).toFixed(2)}); });
    const anchor=Math.floor(cfg.n*0.82); let pv=0,cv=0; const avwap=[];
    bars.forEach((b,i)=>{ if(i>=anchor){ const tp=(b.high+b.low+b.close)/3; pv+=tp*b.value; cv+=b.value; avwap.push({time:b.time,value:+(pv/cv).toFixed(2)}); } });
    const hh=(per,i)=>Math.max(...bars.slice(Math.max(0,i-per+1),i+1).map(b=>b.high));
    const ll=(per,i)=>Math.min(...bars.slice(Math.max(0,i-per+1),i+1).map(b=>b.low));
    const tenkan=[],kijun=[],spanA=[],spanB=[];
    bars.forEach((b,i)=>{ const t=(hh(9,i)+ll(9,i))/2,k=(hh(26,i)+ll(26,i))/2; tenkan.push({time:b.time,value:+t.toFixed(2)}); kijun.push({time:b.time,value:+k.toFixed(2)}); spanA.push({time:b.time,value:+((t+k)/2).toFixed(2)}); spanB.push({time:b.time,value:+((hh(52,i)+ll(52,i))/2).toFixed(2)}); });
    // SMC: pivots, BOS/CHoCH markers, order block lines
    const L=5,piv=[]; for(let i=L;i<bars.length-L;i++){ const isH=bars.slice(i-L,i+L+1).every((b,j)=>j===L||bars[i].high>=b.high); const isL=bars.slice(i-L,i+L+1).every((b,j)=>j===L||bars[i].low<=b.low); if(isH)piv.push({i,price:bars[i].high,type:'H'}); else if(isL)piv.push({i,price:bars[i].low,type:'L'}); }
    const breaks=[]; let lH=null,lL=null,tb=0;
    bars.forEach((b,i)=>{ if(lH!=null&&b.close>lH.price){breaks.push({time:b.time,price:lH.price,dir:'bull',tag:tb===-1?'CHoCH':'BOS'});tb=1;lH=null;} if(lL!=null&&b.close<lL.price){breaks.push({time:b.time,price:lL.price,dir:'bear',tag:tb===1?'CHoCH':'BOS'});tb=-1;lL=null;} const ph=piv.find(p=>p.i===i&&p.type==='H');if(ph)lH=ph; const pl=piv.find(p=>p.i===i&&p.type==='L');if(pl)lL=pl; });
    const obs=[]; breaks.slice(-3).forEach(bk=>{ const bi=bars.findIndex(b=>b.time===bk.time); for(let j=bi;j>Math.max(0,bi-10);j--){ if(bk.dir==='bull'&&bars[j].close<bars[j].open){obs.push({price:+((bars[j].high+bars[j].low)/2).toFixed(2),bias:'bull'});break;} if(bk.dir==='bear'&&bars[j].close>bars[j].open){obs.push({price:+((bars[j].high+bars[j].low)/2).toFixed(2),bias:'bear'});break;} } });
    // Volume profile bins over visible bars
    const vlo=Math.min(...bars.map(b=>b.low)), vhi=Math.max(...bars.map(b=>b.high)), VN=22, vbin=(vhi-vlo)/VN;
    const vpb=Array.from({length:VN},(_,i)=>({ lo:vlo+i*vbin, hi:vlo+(i+1)*vbin, mid:vlo+(i+0.5)*vbin, v:0 }));
    bars.forEach(b=>{ const m=(b.high+b.low)/2; const bi=Math.min(VN-1,Math.max(0,Math.floor((m-vlo)/vbin))); vpb[bi].v+=b.value; });
    const vpMax=Math.max(...vpb.map(x=>x.v)); const pocI=vpb.reduce((m,x,i)=>x.v>vpb[m].v?i:m,0);
    const vTot=vpb.reduce((a,x)=>a+x.v,0); let vacc=vpb[pocI].v,vloI=pocI,vhiI=pocI;
    while(vacc<vTot*0.7&&(vloI>0||vhiI<VN-1)){ const dn=vloI>0?vpb[vloI-1].v:-1,up=vhiI<VN-1?vpb[vhiI+1].v:-1; if(up>=dn){vhiI++;vacc+=vpb[vhiI].v;}else{vloI--;vacc+=vpb[vloI].v;} }
    return { spot, entry, stop, t1, t2, bars, e9, e21, e50, bbU, bbM, bbL, avwap, tenkan, kijun, spanA, spanB, breaks: breaks.slice(-6), obs,
      vpb, vpMax, poc:vpb[pocI].mid, vah:vpb[vhiI].hi, val:vpb[vloI].lo };
  }, [ticker, tf]);

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
            <span className={`mono kpi-tone--${TF_THESIS[k].tone==="up"?"gn":"amb"}`}>{TF_THESIS[k].bias}</span>
          </button>
        ))}
        <div className="tc-tf-read">
          <span className={`tc-tf-tag mono kpi-tone--${tfx.tone==="up"?"gn":"amb"}`}>{tf} · {tfx.bias}</span>
          <span className="mono tc-tf-txt">{tfx.read}</span>
          <span className="mono dim2 tc-tf-struct">{tfx.struct} · <i>{tfx.note}</i></span>
        </div>
      </div>

      <div className="tc-chart-card">
        <LWChart d={d} ind={ind} full={full} />
        <div className="tc-legend mono">
          <span><i className="tc-sw tc-sw--cop"/>entry ${d.entry}</span>
          <span><i className="tc-sw tc-sw--rd"/>stop ${d.stop}</span>
          <span><i className="tc-sw tc-sw--gn"/>T1 ${d.t1} · T2 ${d.t2}</span>
          {ind.ema && <span><i className="tc-sw" style={{background:"var(--cy)"}}/>EMA 9/21/50</span>}
          {ind.bb && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>Bollinger</span>}
          {ind.avwap && <span><i className="tc-sw" style={{background:"var(--amb)"}}/>aVWAP</span>}
          {ind.ichi && <span><i className="tc-sw" style={{background:"var(--gn)"}}/>Ichimoku</span>}
          {ind.smc && <span><i className="tc-sw" style={{background:"var(--blue)"}}/>SMC · BOS/CHoCH/OB</span>}
          {ind.vp && <span><i className="tc-sw tc-sw--cop"/>POC <i className="tc-sw" style={{background:"var(--cy)"}}/>value area · volume profile</span>}
          <span className="dim2">drag to pan · scroll to zoom · hover for OHLC</span>
        </div>
        <NewsFlags />
      </div>

      {!full && <ReplayPractice ticker={ticker} />}

      {!full && <div className="lens-call">
        <span className="label-cap">The Read · Chart</span>
        <span className="mono">Price confirms the thesis — breakout above plan entry <b className="cy">${d.entry}</b>, risk to <b className="dn">${d.stop}</b>, reward to <b className="up">${d.t1}/${d.t2}</b>.</span>
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
  const bars = useTC(() => {
    const code = (ticker.symbol?.charCodeAt(0) || 70) + (ticker.symbol?.charCodeAt(1) || 70);
    const rnd = (() => { let s = code * 9301 + 49297; return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; }; })();
    let p = ticker.price * 0.82; const out = [];
    for (let i = 0; i < 72; i++) {
      const drift = Math.sin(i * 0.18 + code) * 0.006 + (i > 48 ? 0.004 : 0.0009);
      const noise = (Math.sin(i * 0.9 + code) + Math.cos(i * 0.5)) * 0.006 + (rnd() - 0.5) * 0.004;
      p = Math.max(1, p * (1 + drift + noise));
      const o = p * (1 - rnd() * 0.006), c = p * (1 + (rnd() - 0.45) * 0.012);
      const h = Math.max(o, c) * (1 + rnd() * 0.006), l = Math.min(o, c) * (1 - rnd() * 0.006);
      out.push({ o: +o.toFixed(2), h: +h.toFixed(2), l: +l.toFixed(2), c: +c.toFixed(2) });
    }
    return out;
  }, [ticker]);

  const START = 28;
  const [idx, setIdx] = useTCs(START);
  const [playing, setPlaying] = useTCs(false);
  const [entry, setEntry] = useTCs(null);     // { price, i }
  const [trades, setTrades] = useTCs([]);
  const atEnd = idx >= bars.length - 1;

  React.useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setIdx(i => (i >= bars.length - 1 ? i : i + 1)), 650);
    return () => clearInterval(t);
  }, [playing, bars.length]);
  React.useEffect(() => { if (atEnd) setPlaying(false); }, [atEnd]);

  const cur = bars[idx];
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