// surface-portfolio.jsx — Portfolio · Positions cockpit (PM-grade).
// P&L hero + equity curve + open positions (R/heat) + factor & sector exposure + risk + closed journal.

const { useState: usePF, useMemo: usePFm } = React;

const PF_OPEN = [
  { sym:"BORA", name:"Bora Industries",   sector:"Industrials", qty:240, entry:28.40, last:31.10, stop:27.20, t1:34.50, sleeve:"Cont. BO", days:8,  beta:1.12 },
  { sym:"FLNX", name:"Felinex Tech",      sector:"Tech",        qty:60,  entry:162.00,last:168.40,stop:154.0, t1:182.0, sleeve:"Pullback", days:12, beta:1.38 },
  { sym:"INPR", name:"Inpera Capital",    sector:"Finance",     qty:180, entry:41.20, last:39.80, stop:38.40, t1:46.0,  sleeve:"Range",    days:4,  beta:0.86 },
  { sym:"ARCM", name:"Arclight Materials",sector:"Materials",   qty:110, entry:66.18, last:67.42, stop:62.40, t1:72.80, sleeve:"Cont. BO", days:1,  beta:1.18 },
  { sym:"DRSH", name:"Druseh Energy",     sector:"Energy",      qty:140, entry:54.00, last:56.10, stop:51.50, t1:61.0,  sleeve:"Breakout", days:6,  beta:1.05 },
];

const PF_CLOSED = [
  { sym:"ARGN", r:"+1.84", pnl:"+$1,210", days:9,  sleeve:"Cont. BO", win:true },
  { sym:"VLCT", r:"−1.00", pnl:"−$420",   days:3,  sleeve:"Pullback", win:false },
  { sym:"ZOTR", r:"+2.10", pnl:"+$1,480", days:14, sleeve:"Flag",     win:true },
  { sym:"MERC", r:"−0.60", pnl:"−$252",   days:5,  sleeve:"Range",    win:false },
  { sym:"NVRH", r:"+0.41", pnl:"+$320",   days:7,  sleeve:"Pullback", win:true },
];

function SurfacePortfolio({ onTicker }) {
  const [tab, setTab] = usePF("open");

  const pos = usePFm(() => PF_OPEN.map(p => {
    const d = new Date(Date.now() - p.days * 86400000);
    const opened = d.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "2-digit" });
    const mv = p.qty * p.last, cost = p.qty * p.entry;
    const pnl = mv - cost, pnlPct = (p.last/p.entry - 1) * 100;
    const risk = p.qty * (p.entry - p.stop);
    const openR = (p.last - p.entry) / (p.entry - p.stop);
    const stopDist = (p.last - p.stop) / p.last * 100;
    const erDays = 4 + (p.sym.charCodeAt(0) % 40);
    return { ...p, opened, mv, cost, pnl, pnlPct, risk, openR, stopDist, erDays };
  }), []);

  const nav = 108420;
  const deployed = pos.reduce((s,p)=>s+p.mv,0);
  const openPnl = pos.reduce((s,p)=>s+p.pnl,0);
  const totalRisk = pos.reduce((s,p)=>s+Math.max(0,p.risk),0);
  const heat = pos.reduce((s,p)=>s+Math.max(0,p.openR),0);
  const bookBeta = (pos.reduce((s,p)=>s+p.beta*p.mv,0)/deployed);

  const sectors = usePFm(()=>{
    const m={}; pos.forEach(p=>{ m[p.sector]=(m[p.sector]||0)+p.mv; });
    return Object.entries(m).map(([k,v])=>({k,v,pct:v/deployed*100})).sort((a,b)=>b.v-a.v);
  },[pos,deployed]);
  const SEC_C = { Tech:"var(--cy)", Finance:"var(--blue)", Materials:"var(--copper)", Energy:"var(--amb)", Industrials:"var(--ink-2)", Healthcare:"var(--violet)", Consumer:"var(--gn)" };

  const factors = [
    ["Momentum", 0.80, "amb"], ["Quality", 0.41, "gn"], ["Value", -0.08, "rd"],
    ["Low-Vol", 0.22, "amb"], ["Size", -0.16, "gn"], ["Growth", 0.34, "gn"],
  ];

  return (
    <div className="surface wsx wsx--copper pf2">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">PORTFOLIO · POSITIONS · BOOK RISK</div>
          <h1 className="wsx-title mono">Portfolio</h1>
          <div className="wsx-sub mono dim2">P&L · open positions · factor &amp; sector exposure · book risk · closed journal</div>
        </div>
        <div className="wsx-hdr-r">
          <div className="seg">{["PAPER","LIVE"].map((m,i)=><button key={m} className={`seg-btn ${i===0?"is-on":""}`}>{m}</button>)}</div>
          <FreshnessPill state="live" age="3s" />
        </div>
      </div>

      {/* P&L hero */}
      <div className="pf-hero2">
        <div className="pf-hero-main">
          <div className="pf-hero-eyebrow mono dim2">TOTAL P&L · TODAY</div>
          <div className="pf-hero-num mono up">+$1,284</div>
          <div className="pf-hero-sub mono">+1.20% · <span className="dim2">vs SPY +0.42% ·</span> <span className="up">+78bp α</span></div>
          <PfEquity />
        </div>
        <div className="pf-hero-tiles">
          <PfTile l="NAV" v="$108,420" s="paper account" tone="ink" />
          <PfTile l="Deployed" v={`${(deployed/nav*100).toFixed(1)}%`} s={`$${(deployed/1000).toFixed(1)}k · ${pos.length} pos`} tone="copper" />
          <PfTile l="Open P&L" v={`${openPnl>=0?"+":""}$${openPnl.toFixed(0)}`} s={`${heat.toFixed(1)}R open heat`} tone={openPnl>=0?"gn":"rd"} />
          <PfTile l="Cash" v={`$${((nav-deployed)/1000).toFixed(1)}k`} s={`${(100-deployed/nav*100).toFixed(0)}% dry powder`} tone="gn" />
          <PfTile l="$ at risk" v={`$${totalRisk.toFixed(0)}`} s={`${(totalRisk/nav*100).toFixed(2)}% NAV to stops`} tone="amb" />
          <PfTile l="Book β" v={bookBeta.toFixed(2)} s="vs SPY · within cap" tone="ink" />
          <PfTile l="Sharpe" v="1.84" s="60d rolling" tone="gn" />
          <PfTile l="Max DD" v="−2.1%" s="trough · 30d" tone="rd" />
        </div>
      </div>

      <div className="lab-tabs">
        {[["open",`Open · ${pos.length}`],["expo","Exposure"],["attrib","Attribution"],["risk","Book Risk"],["orders","Pending"],["closed","Closed Journal"]].map(([id,l])=>(
          <button key={id} className={`lab-tab ${tab===id?"is-on":""}`} onClick={()=>setTab(id)}>{l}</button>
        ))}
      </div>

      {tab==="open" && (
        <div className="wsx-body">
          <table className="dtable wsx-tbl pf-tbl">
            <thead><tr>
              <th>Sym</th><th>Opened</th><th>Sleeve</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Last</th>
              <th className="r">Mkt Val</th><th className="r">P&L</th><th className="r">P&L %</th><th className="r">Open R</th>
              <th>R progress</th><th className="r">Stop dist</th><th className="r">Days</th><th className="r">ER</th><th>Manage</th>
            </tr></thead>
            <tbody>{pos.map(p=>(
              <tr key={p.sym} onClick={()=>onTicker(p.sym)}>
                <td><b>{p.sym}</b><div className="pf-name dim2">{p.name}</div></td>
                <td className="mono dim2">{p.opened}</td>
                <td className="dim2">{p.sleeve}</td>
                <td className="r tabular">{p.qty}</td>
                <td className="r tabular dim">${p.entry.toFixed(2)}</td>
                <td className="r tabular">${p.last.toFixed(2)}</td>
                <td className="r tabular">${(p.mv/1000).toFixed(1)}k</td>
                <td className={`r tabular ${p.pnl>=0?"up":"dn"}`}><b>{p.pnl>=0?"+":""}${p.pnl.toFixed(0)}</b></td>
                <td className={`r tabular ${p.pnlPct>=0?"up":"dn"}`}>{p.pnlPct>=0?"+":""}{p.pnlPct.toFixed(1)}%</td>
                <td className={`r tabular ${p.openR>=0?"up":"dn"}`}>{p.openR>=0?"+":""}{p.openR.toFixed(2)}R</td>
                <td><div className="pf-rbar"><div className="pf-rbar-axis" /><div className={`pf-rbar-fill ${p.openR>=0?"pos":"neg"}`} style={{width:`${Math.min(50,Math.abs(p.openR)*25)}%`, marginLeft: p.openR>=0?"50%":`${50-Math.min(50,Math.abs(p.openR)*25)}%`}} /></div></td>
                <td className={`r tabular ${p.stopDist<5?"amb":"gn"}`}>{p.stopDist.toFixed(1)}%</td>
                <td className="r tabular dim">{p.days}</td>
                <td className="r">{p.erDays<=10 ? <span className="pf-er mono">ER {p.erDays}d</span> : <span className="dim">—</span>}</td>
                <td onClick={e=>e.stopPropagation()}><div className="pf-acts"><button className="pf-act" title="Add">＋</button><button className="pf-act" title="Trim">½</button><button className="pf-act pf-act--rd" title="Close">✕</button></div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab==="expo" && (
        <div className="pf-expo">
          <div className="lab-card">
            <div className="lab-card-h mono">SECTOR ALLOCATION</div>
            <div className="pf-secbar">{sectors.map((s,i)=>(<div key={i} className="pf-secseg" style={{width:`${s.pct}%`, background:SEC_C[s.k]||"var(--ink-3)"}} title={`${s.k} ${s.pct.toFixed(0)}%`} />))}</div>
            <div className="pf-seclegend">{sectors.map((s,i)=>(
              <div key={i} className="pf-secrow"><span className="pf-secdot" style={{background:SEC_C[s.k]||"var(--ink-3)"}} /><span className="pf-secn">{s.k}</span><span className="mono dim2">${(s.v/1000).toFixed(1)}k</span><span className="mono">{s.pct.toFixed(0)}%</span></div>
            ))}</div>
          </div>
          <div className="lab-card">
            <div className="lab-card-h mono">FACTOR EXPOSURE · net book betas</div>
            <div className="pf-factors">{factors.map(([f,v,tone],i)=>(
              <div key={i} className="pf-frow"><span className="pf-fl">{f}</span>
                <div className="pf-fbar"><div className="pf-faxis" /><div className={`pf-ffill kpi-tone--${tone}`} style={{width:`${Math.min(50,Math.abs(v)*50)}%`, marginLeft:v>=0?"50%":`${50-Math.min(50,Math.abs(v)*50)}%`, background:`var(--${tone})`}} /></div>
                <span className={`mono pf-fv kpi-tone--${tone}`}>{v>=0?"+":""}{v.toFixed(2)}</span></div>
            ))}</div>
            <div className="lab-verdict mono dim2">Momentum-tilted (+0.80), quality-positive, value-light. A momentum unwind is the book's biggest single-factor risk.</div>
          </div>
        </div>
      )}

      {tab==="attrib" && (
        <div className="pf-expo">
          <div className="lab-card">
            <div className="lab-card-h mono">P&L ATTRIBUTION · by sleeve</div>
            <div className="pf-attr">
              {[["Cont. BO","+$1,840","gn",62],["Pullback","+$344","gn",18],["Breakout","+$294","gn",14],["Range","−$252","rd",-12]].map((r,i)=>(
                <div key={i} className="pf-attr-row"><span className="pf-attr-l">{r[0]}</span><div className="pf-attr-bar"><div className="pf-attr-ax" /><div className={`pf-attr-f kpi-tone--${r[2]}`} style={{width:`${Math.min(50,Math.abs(r[3]))}%`,marginLeft:r[3]>=0?"50%":`${50-Math.min(50,Math.abs(r[3]))}%`,background:`var(--${r[2]})`}} /></div><span className={`mono pf-attr-v kpi-tone--${r[2]}`}>{r[1]}</span></div>
              ))}
            </div>
          </div>
          <div className="lab-card">
            <div className="lab-card-h mono">P&L ATTRIBUTION · by sector</div>
            <div className="pf-attr">
              {[["Industrials","+$648","gn",34],["Tech","+$384","gn",20],["Materials","+$136","gn",8],["Energy","+$294","gn",16],["Finance","−$252","rd",-13]].map((r,i)=>(
                <div key={i} className="pf-attr-row"><span className="pf-attr-l">{r[0]}</span><div className="pf-attr-bar"><div className="pf-attr-ax" /><div className={`pf-attr-f`} style={{width:`${Math.min(50,Math.abs(r[3]))}%`,marginLeft:r[3]>=0?"50%":`${50-Math.min(50,Math.abs(r[3]))}%`,background:`var(--${r[2]})`}} /></div><span className={`mono pf-attr-v kpi-tone--${r[2]}`}>{r[1]}</span></div>
              ))}
            </div>
          </div>
          <div className="lab-card pf-wide">
            <div className="lab-card-h mono">POSITION CORRELATION MATRIX · 60d</div>
            <CorrMatrix syms={pos.map(p=>p.sym)} />
            <div className="lab-verdict mono dim2">High pairwise correlation (&gt;0.6) = positions that fall together in a shock. FLNX↔ARCM run hottest; size accordingly.</div>
          </div>
          <div className="lab-card pf-wide">
            <div className="lab-card-h mono">PERIODIC RETURNS</div>
            <table className="dtable wsx-tbl pf-mini">
              <thead><tr><th>Period</th><th className="r">Book</th><th className="r">SPY</th><th className="r">α</th><th className="r">Realized</th><th className="r">Unrealized</th></tr></thead>
              <tbody>{[["Today","+1.20%","+0.42%","+0.78%","+$420","+$864"],["WTD","+2.68%","+1.10%","+1.58%","+$1,240","+$1,600"],["MTD","+4.04%","+2.30%","+1.74%","+$2,800","+$1,410"],["YTD","+12.27%","+9.42%","+2.85%","+$9,200","+$2,660"]].map((r,i)=>(
                <tr key={i}><td className="mono">{r[0]}</td><td className="r tabular up">{r[1]}</td><td className="r tabular dim">{r[2]}</td><td className="r tabular" style={{color:"var(--copper)"}}>{r[3]}</td><td className="r tabular up">{r[4]}</td><td className="r tabular up">{r[5]}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}

      {tab==="orders" && (
        <div className="wsx-body">
          <table className="dtable wsx-tbl pf-tbl">
            <thead><tr><th>Sym</th><th>Type</th><th>Side</th><th className="r">Limit/Stop</th><th className="r">Qty</th><th>TIF</th><th>Status</th><th>Placed</th></tr></thead>
            <tbody>{[
              ["GENO","BUY-STOP LMT","BUY","$30.20","165","GTC","working","06:12","amb"],
              ["ARCM","OCO · T1 sell","SELL","$72.80","55","GTC","armed","yesterday","gn"],
              ["ARCM","OCO · stop","SELL","$62.40","110","GTC","armed","yesterday","rd"],
              ["NVRH","LIMIT","BUY","$138.00","70","DAY","working","08:30","amb"],
              ["DRSH","TRAIL stop","SELL","ATR×2.2","140","GTC","trailing","6d ago","cy"],
            ].map((r,i)=>(
              <tr key={i} onClick={()=>onTicker(r[0])}>
                <td><b>{r[0]}</b></td><td className="mono dim2">{r[1]}</td>
                <td><span className={r[2]==="BUY"?"up":"dn"}>{r[2]}</span></td>
                <td className="r tabular">{r[3]}</td><td className="r tabular">{r[4]}</td>
                <td className="mono dim2">{r[5]}</td>
                <td><span className={`pf-ord pf-ord--${r[8]}`}>{r[6]}</span></td>
                <td className="dim2">{r[7]}</td>
              </tr>
            ))}</tbody>
          </table>
          <div className="pf-note mono dim2">Resting orders &amp; OCO brackets from broker · trailing stops re-priced intraday off ATR. Cancel/modify from the per-ticker Plan lens.</div>
        </div>
      )}

      {tab==="risk" && (
        <div className="pf-expo">
          <div className="lab-card">
            <div className="lab-card-h mono">BOOK RISK · live limits</div>
            <div className="pf-risk">
              {[["NAV deployed",`${(deployed/nav*100).toFixed(1)}%`,deployed/nav*100,60,"gn"],["Gross exposure","22%",22,100,"cy"],["$ at risk to stops",`${(totalRisk/nav*100).toFixed(2)}%`,totalRisk/nav*100,3,"amb"],["Open heat",`${heat.toFixed(1)}R`,heat*10,40,"gn"],["Book β",bookBeta.toFixed(2),bookBeta*60,73,"cy"],["Max position correl","0.42",42,55,"amb"]].map((r,i)=>(
                <div key={i} className="pf-rrow"><span className="pf-rl mono dim2">{r[0]}</span><div className="pf-rtrack"><div className={`pf-rfill kpi-tone--${r[4]}`} style={{width:`${Math.min(100,r[2])}%`,background:`var(--${r[4]})`}} /><div className="pf-rcap" style={{left:`${Math.min(100,r[3])}%`}} /></div><span className={`mono pf-rv kpi-tone--${r[4]}`}>{r[1]}</span></div>
              ))}
            </div>
            <div className="lab-verdict mono dim2">▏ marker = policy cap. All metrics within limits · sleep score A−.</div>
          </div>
          <div className="lab-card">
            <div className="lab-card-h mono">STRESS · book P&L under shocks</div>
            <table className="dtable wsx-tbl pf-mini">
              <thead><tr><th>Scenario</th><th className="r">Book P&L</th><th className="r">% NAV</th><th>Worst name</th></tr></thead>
              <tbody>{[["−3σ market gap","−$3,180","−2.9%","FLNX","rd"],["Sector rotation","−$1,840","−1.7%","BORA","amb"],["Momentum unwind","−$2,610","−2.4%","FLNX","rd"],["Rates +50bp","−$920","−0.8%","INPR","amb"],["Vol spike VIX→30","−$1,420","−1.3%","ARCM","amb"]].map((r,i)=>(
                <tr key={i}><td className="mono">{r[0]}</td><td className={`r tabular kpi-tone--${r[4]}`}>{r[1]}</td><td className={`r tabular kpi-tone--${r[4]}`}>{r[2]}</td><td className="mono dim2">{r[3]}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}

      {tab==="closed" && (
        <div className="wsx-body">
          <div className="pf-closed-kpis">
            <PfTile l="Win rate" v="60%" s="3 / 5 trades" tone="gn" />
            <PfTile l="Avg win" v="+1.45R" s="vs −0.80R avg loss" tone="gn" />
            <PfTile l="Profit factor" v="2.31" s="gross gain ÷ loss" tone="gn" />
            <PfTile l="Expectancy" v="+0.63R" s="per trade" tone="copper" />
          </div>
          <table className="dtable wsx-tbl pf-tbl">
            <thead><tr><th>Sym</th><th>Sleeve</th><th className="r">R-multiple</th><th className="r">P&L</th><th className="r">Days held</th><th>Result</th></tr></thead>
            <tbody>{PF_CLOSED.map((c,i)=>(
              <tr key={i} onClick={()=>onTicker(c.sym)}>
                <td><b>{c.sym}</b></td><td className="dim2">{c.sleeve}</td>
                <td className={`r tabular ${c.win?"up":"dn"}`}>{c.r}R</td>
                <td className={`r tabular ${c.win?"up":"dn"}`}>{c.pnl}</td>
                <td className="r tabular dim">{c.days}</td>
                <td><span className={`pf-result pf-result--${c.win?"win":"loss"}`}>{c.win?"WIN":"LOSS"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      <div className="pf-note mono dim2">
        Positions &amp; fills from <b>portfolio_state</b> · live prices <b>Schwab /quotes</b> (3s) · factor betas from rolling 126d regression ·
        stress shocks from the risk engine · R-multiples normalize size. Click any row → 14-lens detail.
      </div>
    </div>
  );
}

function PfTile({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}

function CorrMatrix({ syms }) {
  const corr = (a, b) => {
    if (a === b) return 1;
    const h = (a.charCodeAt(0) + b.charCodeAt(0) + a.charCodeAt(1) + b.charCodeAt(1));
    return Math.round(((h % 90) / 100 + 0.05) * 100) / 100;
  };
  const cell = (v) => {
    if (v >= 0.99) return { bg: "var(--bg-3)", c: "var(--ink-3)" };
    if (v >= 0.6) return { bg: `rgba(248,113,113,${0.2 + v * 0.4})`, c: "#fde4e4" };
    if (v >= 0.3) return { bg: `rgba(251,191,36,${0.15 + v * 0.3})`, c: "#1a1a1a" };
    return { bg: `rgba(74,222,128,${0.1 + (1 - v) * 0.2})`, c: "#dffce6" };
  };
  return (
    <div className="pf-corr">
      <table className="pf-corr-tbl mono">
        <thead><tr><th></th>{syms.map(s => <th key={s}>{s}</th>)}</tr></thead>
        <tbody>{syms.map(r => (
          <tr key={r}><th>{r}</th>{syms.map(c => { const v = corr(r, c); const st = cell(v); return <td key={c} style={{ background: st.bg, color: st.c }}>{v.toFixed(2)}</td>; })}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function PfEquity() {
  const data = usePFm(()=>{ const a=[]; let v=0; for(let i=0;i<40;i++){ v+=0.32+(Math.sin(i*0.4)+Math.cos(i*0.7))*0.35+(Math.random()-0.45)*0.5; a.push(v);} return a; },[]);
  const w=440,h=72,min=Math.min(...data,-1),max=Math.max(...data,14);
  const x=i=>(i/(data.length-1))*w, y=v=>h-((v-min)/(max-min))*(h-6)-3;
  return (<svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="pf-eq">
    <defs><linearGradient id="pfeq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.3"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0"/></linearGradient></defs>
    <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3"/>
    <path d={`M 0 ${y(0)} L ${data.map((v,i)=>`${x(i)},${y(v)}`).join(" L ")} L ${w} ${y(0)} Z`} fill="url(#pfeq)"/>
    <polyline points={data.map((v,i)=>`${x(i)},${y(v)}`).join(" ")} fill="none" stroke="var(--gn)" strokeWidth="1.8" style={{filter:"drop-shadow(0 0 4px var(--gn))"}}/>
    <circle cx={x(data.length-1)} cy={y(data[data.length-1])} r="3.5" fill="var(--gn)" style={{filter:"drop-shadow(0 0 6px var(--gn))"}}/>
  </svg>);
}

window.SurfacePortfolio = SurfacePortfolio;

// ── Automated Trade — wraps Positions · Watchlist · Risk · Alerts as sub-tabs ──
function SurfaceAutomatedTrade({ onTicker }) {
  const [tab, setTab] = usePF("positions");
  const tabs = [
    ["positions", "Positions", "open book · P&L · R/heat"],
    ["performance", "Performance", "equity · attribution"],
    ["journal", "Trade Journal", "log · R-analytics"],
    ["watchlist", "Watchlist", "★ starred + manual"],
    ["risk", "Risk · Exposure", "VaR · Kelly · stress"],
    ["execution", "Execution", "blotter · algos · TCA"],
    ["alerts", "Alerts", "real-time triggers"],
  ];
  return (
    <div className="etfs-wrap">
      <div className="etfs-tabbar">
        <div className="etfs-tabs">
          {tabs.map(([id, l, s]) => (
            <button key={id} className={`etfs-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>
              <span className="etfs-tab-l">{l}</span>
              <span className="etfs-tab-s mono dim2">{s}</span>
            </button>
          ))}
        </div>
      </div>
      {tab === "positions" ? <SurfacePortfolio onTicker={onTicker} />
        : tab === "performance" ? (window.SurfacePerformance ? <SurfacePerformance onTicker={onTicker} /> : null)
        : tab === "journal" ? (window.SurfaceJournal ? <SurfaceJournal onTicker={onTicker} /> : null)
        : tab === "watchlist" ? (window.SurfaceWatchlist ? <SurfaceWatchlist onTicker={onTicker} /> : null)
        : tab === "risk" ? (window.SurfaceRisk ? <SurfaceRisk onTicker={onTicker} /> : null)
        : tab === "execution" ? <ExecutionBlotter onTicker={onTicker} />
        : (window.SurfaceAlerts ? <SurfaceAlerts onTicker={onTicker} /> : null)}
    </div>
  );
}
window.SurfaceAutomatedTrade = SurfaceAutomatedTrade;

// ── Execution: OMS working blotter + execution algos + TCA ──────────────
const EB_ORDERS = [
  { sym: "ARGN", side: "BUY", qty: 1400, filled: 1400, algo: "VWAP", venue: "NYSE", arrival: 212.10, avg: 212.46, vwap: 212.55, status: "DONE" },
  { sym: "NVRH", side: "BUY", qty: 800, filled: 520, algo: "POV 12%", venue: "ARCA", arrival: 141.30, avg: 141.62, vwap: 141.55, status: "WORKING" },
  { sym: "BIVO", side: "SELL", qty: 1200, filled: 1200, algo: "TWAP", venue: "NSDQ", arrival: 72.90, avg: 72.71, vwap: 72.68, status: "DONE" },
  { sym: "KARO", side: "BUY", qty: 600, filled: 0, algo: "IS", venue: "SMART", arrival: 124.60, avg: 0, vwap: 124.60, status: "QUEUED" },
  { sym: "VLCT", side: "SELL", qty: 350, filled: 210, algo: "VWAP", venue: "SMART", arrival: 198.40, avg: 198.02, vwap: 198.18, status: "WORKING" },
];
function ExecutionBlotter({ onTicker }) {
  const fmtbps = v => `${v >= 0 ? "+" : ""}${v.toFixed(1)} bps`;
  // TCA: slippage vs arrival (implementation shortfall) and vs VWAP, signed by side
  const rows = EB_ORDERS.map(o => {
    const dir = o.side === "BUY" ? 1 : -1;
    const isBps = o.avg ? -dir * (o.avg - o.arrival) / o.arrival * 1e4 : 0;   // +=savings
    const vwapBps = o.avg ? -dir * (o.avg - o.vwap) / o.vwap * 1e4 : 0;
    return { ...o, isBps, vwapBps, pct: o.qty ? o.filled / o.qty * 100 : 0 };
  });
  const done = rows.filter(r => r.status === "DONE");
  const avgIs = done.length ? done.reduce((s, r) => s + r.isBps, 0) / done.length : 0;
  const avgVwap = done.length ? done.reduce((s, r) => s + r.vwapBps, 0) / done.length : 0;
  const working = rows.filter(r => r.status === "WORKING").length;
  const queued = rows.filter(r => r.status === "QUEUED").length;
  const stTone = s => s === "DONE" ? "gn" : s === "WORKING" ? "amb" : "ink";
  return (
    <div className="wsx-body eb">
      <div className="brk-tiles" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Working orders</div><div className="brk-tile-v mono kpi-tone--amb">{working}</div><div className="brk-tile-s mono dim">{queued} queued</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Avg IS vs arrival</div><div className={`brk-tile-v mono kpi-tone--${avgIs >= 0 ? "gn" : "rd"}`}>{fmtbps(avgIs)}</div><div className="brk-tile-s mono dim">implementation shortfall</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Avg vs VWAP</div><div className={`brk-tile-v mono kpi-tone--${avgVwap >= 0 ? "gn" : "rd"}`}>{fmtbps(avgVwap)}</div><div className="brk-tile-s mono dim">benchmark slippage</div></div>
        <div className="brk-tile"><div className="brk-tile-l mono dim2">Fills today</div><div className="brk-tile-v mono">{done.length}/{rows.length}</div><div className="brk-tile-s mono dim">orders complete</div></div>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">SYSTEM BLOTTER · autonomous fills · algos &amp; routing <span className="dim2" style={{ letterSpacing: ".04em", textTransform: "none" }}>· PAPER</span></div>
        <table className="dtable brk-tbl">
          <thead><tr><th>Sym</th><th>Side</th><th className="r">Qty</th><th className="r">Fill</th><th>Algo</th><th>Venue</th><th className="r">Avg px</th><th className="r">IS</th><th className="r">vs VWAP</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((o, i) => (
              <tr key={i} className="brk-row" onClick={() => onTicker && onTicker(o.sym)}>
                <td className="mono"><b>{o.sym}</b></td>
                <td className={`mono ${o.side === "BUY" ? "gn-c" : "rd-c"}`}>{o.side}</td>
                <td className="r mono">{o.qty.toLocaleString()}</td>
                <td className="r mono dim2">{o.pct.toFixed(0)}%</td>
                <td className="mono">{o.algo}</td>
                <td className="mono dim2">{o.venue}</td>
                <td className="r mono">{o.avg ? `$${o.avg.toFixed(2)}` : "—"}</td>
                <td className={`r mono ${o.avg ? (o.isBps >= 0 ? "gn-c" : "rd-c") : "dim2"}`}>{o.avg ? fmtbps(o.isBps) : "—"}</td>
                <td className={`r mono ${o.avg ? (o.vwapBps >= 0 ? "gn-c" : "rd-c") : "dim2"}`}>{o.avg ? fmtbps(o.vwapBps) : "—"}</td>
                <td><span className={`eb-status kpi-tone--${stTone(o.status)}`}>{o.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="lab-verdict mono dim2">IS = implementation shortfall vs the arrival price when the <b>system</b> sent the order; +bps = price improvement, −bps = slippage. VWAP column benchmarks each fill against the interval VWAP. These are <b>autonomous, paper</b> fills — the engine routes and works orders itself (VWAP/TWAP/POV/IS) per each name's liquidity; this panel polices its execution quality. Demo OMS.</div>
      </div>
    </div>
  );
}
window.ExecutionBlotter = ExecutionBlotter;
(function () {
  if (document.getElementById("eb-css")) return;
  const st = document.createElement("style"); st.id = "eb-css";
  st.textContent = `.eb .brk-tiles{margin:14px 0 12px;} .eb-status{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:20px;} .eb .gn-c{color:var(--gn);} .eb .rd-c{color:var(--rd);}`;
  document.head.appendChild(st);
})();
