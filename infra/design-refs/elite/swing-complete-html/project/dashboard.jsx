// ─────────────────────────────────────────────────────────
//  SWING DESK · DASHBOARD — The morning brief
//  Three questions: Market? Book? Edge?
// ─────────────────────────────────────────────────────────

const T = {
  bg:     '#07090f',
  s1:     '#0c1018',
  s2:     '#111620',
  s3:     '#181f2e',
  border: 'rgba(255,255,255,0.07)',
  div:    'rgba(255,255,255,0.04)',
  text:   '#e8eef8',
  sub:    '#7a8fa8',
  muted:  '#3d4f66',
  gold:   '#c9a84c',
  cyan:   '#38bdf8',
  bull:   '#34d399',
  bear:   '#f87171',
  warn:   '#fbbf24',
};

const mono = 'JetBrains Mono, monospace';
const sans = 'Inter, system-ui, sans-serif';
const D = window.TICKR_DATA;
const SCAN = window.SCANNER_DATA;

// ── helpers ──────────────────────────────────────────────
const fmt = (n, d=2) => n.toFixed(d);
const pct = n => `${n>=0?'+':''}${n.toFixed(2)}%`;
const usd = n => `$${Math.abs(n).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2})}`;
const sign = n => n >= 0 ? '+' : '−';

// ── mini sparkline svg ───────────────────────────────────
function Spark({ data, w=80, h=28, color, fill=true }) {
  if (!data?.length) return null;
  const min = Math.min(...data), max = Math.max(...data), rng = max - min || 1;
  const pts = data.map((v,i) => [
    (i/(data.length-1))*w,
    h - ((v-min)/rng)*(h*0.85) - h*0.075
  ]);
  const line = pts.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
  const area = `${line}L${w},${h}L0,${h}Z`;
  const up = data[data.length-1] >= data[0];
  const c = color || (up ? T.bull : T.bear);
  return (
    <svg width={w} height={h} style={{display:'block',overflow:'visible'}}>
      {fill && <path d={area} fill={c} fillOpacity="0.12"/>}
      <path d={line} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="2.5" fill={c}/>
    </svg>
  );
}

// ── positions mock data ──────────────────────────────────
const POSITIONS = [
  { ticker:'RTX',  name:'Raytheon Technologies',  entry:108.40, price:114.82, stop:105.20, shares:220, days:12, sector:'Defense',    candles: Array.from({length:20},(_,i)=>105+i*0.48+Math.sin(i)*2.1) },
  { ticker:'SOMA', name:'Soma Aerospace',          entry:87.20,  price:92.34,  stop:84.10,  shares:180, days:7,  sector:'Aerospace',   candles: Array.from({length:20},(_,i)=>86+i*0.32+Math.sin(i*0.8)*1.8) },
  { ticker:'AURA', name:'Aura Dynamics',           entry:61.50,  price:65.80,  stop:59.00,  shares:310, days:4,  sector:'Tech',        candles: Array.from({length:20},(_,i)=>61+i*0.22+Math.cos(i)*1.5) },
  { ticker:'KAIO', name:'Kaio Systems',            entry:142.00, price:148.60, stop:138.50, shares:105, days:9,  sector:'Industrials', candles: Array.from({length:20},(_,i)=>141+i*0.35+Math.sin(i*1.2)*2) },
  { ticker:'NVRA', name:'Novara Semiconductors',   entry:76.30,  price:79.12,  stop:73.80,  shares:260, days:3,  sector:'Semis',       candles: Array.from({length:20},(_,i)=>75+i*0.14+Math.cos(i*0.6)*2.2) },
  { ticker:'AETH', name:'Aether Industrials',      entry:193.00, price:189.40, stop:188.00, shares:82,  days:11, sector:'Industrial',  candles: Array.from({length:20},(_,i)=>196-i*0.18+Math.sin(i)*1.4) },
];

const INDICES = [
  { sym:'SPY',  name:'S&P 500',  price:518.42, chg:+0.84, candles: Array.from({length:40},(_,i)=>508+i*0.28+Math.sin(i*0.4)*3.2) },
  { sym:'QQQ',  name:'Nasdaq',   price:442.18, chg:+1.12, candles: Array.from({length:40},(_,i)=>430+i*0.32+Math.sin(i*0.35)*4) },
  { sym:'IWM',  name:'Russell',  price:201.37, chg:-0.22, candles: Array.from({length:40},(_,i)=>203-i*0.05+Math.sin(i*0.6)*2) },
  { sym:'DIA',  name:'Dow',      price:388.74, chg:+0.61, candles: Array.from({length:40},(_,i)=>382+i*0.18+Math.cos(i*0.3)*2.4) },
  { sym:'GLD',  name:'Gold',     price:234.82, chg:+0.38, candles: Array.from({length:40},(_,i)=>231+i*0.09+Math.sin(i*0.7)*1.8) },
  { sym:'VIX',  name:'Volatility',price:14.82, chg:-0.84, candles: Array.from({length:40},(_,i)=>16.5-i*0.04+Math.sin(i*0.9)*0.8), invert:true },
];

const SECTORS = [
  { name:'Industrials', chg:+1.84 }, { name:'Aerospace & Def', chg:+1.61 },
  { name:'Semiconductors', chg:+1.22 }, { name:'Communication', chg:+0.88 },
  { name:'Health Care', chg:+0.74 }, { name:'Financials', chg:+0.62 },
  { name:'Consumer Disc', chg:+0.44 }, { name:'Technology', chg:+0.38 },
  { name:'Utilities', chg:-0.12 }, { name:'Consumer Staples', chg:-0.28 },
  { name:'Real Estate', chg:-0.51 }, { name:'Energy', chg:-0.76 },
];

const TOP_SETUPS = [...SCAN].sort((a,b)=>b.score-a.score).slice(0,8);

// ─────────────────────────────────────────────────────────
//  STAT STRIP — full-width account hero
// ─────────────────────────────────────────────────────────
function StatStrip() {
  const stats = [
    { label:'Day P&L',    value:'+$2,847',   color:T.bull,  size:52 },
    { label:'Account',    value:'$252,847',  color:T.text,  size:52 },
    { label:'Heat',       value:'3.2%',      color:T.warn,  size:52 },
    { label:'Positions',  value:'8 open',    color:T.text,  size:52 },
    { label:'Buying Power',value:'$68,400',  color:T.sub,   size:52 },
  ];
  return (
    <div style={{
      display:'flex', alignItems:'stretch', borderBottom:`1px solid ${T.border}`,
      background:T.s1,
    }}>
      {stats.map((s,i) => (
        <div key={s.label} style={{
          flex: i===0||i===1 ? '1.4' : '1',
          padding:'28px 32px',
          borderRight: i<stats.length-1 ? `1px solid ${T.border}` : 'none',
        }}>
          <div style={{
            fontSize:9, fontWeight:700, letterSpacing:'0.2em',
            textTransform:'uppercase', color:T.muted, fontFamily:mono, marginBottom:10,
          }}>{s.label}</div>
          <div style={{
            fontSize:s.size, fontWeight:900, color:s.color,
            fontFamily:mono, letterSpacing:'-0.03em', lineHeight:1,
          }}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  MARKET STRIP — index cards
// ─────────────────────────────────────────────────────────
function MarketStrip() {
  return (
    <div style={{
      display:'flex', borderBottom:`1px solid ${T.border}`,
      background:T.bg, overflowX:'auto', scrollbarWidth:'none',
    }}>
      {INDICES.map((idx,i) => {
        const up = idx.chg >= 0;
        const bullish = idx.sym === 'VIX' ? !up : up;
        const color = bullish ? T.bull : T.bear;
        return (
          <div key={idx.sym} style={{
            flex: '0 0 auto', padding:'18px 28px',
            borderRight:`1px solid ${T.border}`,
            display:'flex', gap:16, alignItems:'center', minWidth:200,
          }}>
            <div style={{flex:1}}>
              <div style={{display:'flex',alignItems:'baseline',gap:8,marginBottom:4}}>
                <span style={{fontSize:16,fontWeight:900,color:T.text,fontFamily:mono}}>{idx.sym}</span>
                <span style={{fontSize:10,color:T.muted}}>{idx.name}</span>
              </div>
              <div style={{display:'flex',alignItems:'baseline',gap:8}}>
                <span style={{fontSize:20,fontWeight:800,color:T.text,fontFamily:mono}}>{idx.price.toFixed(2)}</span>
                <span style={{fontSize:12,fontWeight:700,color,fontFamily:mono}}>{pct(idx.chg)}</span>
              </div>
            </div>
            <Spark data={idx.candles} w={72} h={32} color={color}/>
          </div>
        );
      })}
      {/* Regime pill */}
      <div style={{
        flex:'0 0 auto', padding:'18px 28px',
        display:'flex', flexDirection:'column', justifyContent:'center', gap:8, minWidth:180,
      }}>
        <div style={{
          padding:'6px 14px', background:`${T.bull}14`,
          border:`1px solid ${T.bull}30`, borderRadius:100,
          fontSize:11, fontWeight:700, color:T.bull,
          letterSpacing:'0.1em', fontFamily:mono, textAlign:'center',
        }}>RISK-ON · TRENDING</div>
        <div style={{fontSize:10,color:T.muted,textAlign:'center',letterSpacing:'0.08em',fontFamily:mono}}>BREADTH 72% · VIX 14.8</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  POSITION CARD
// ─────────────────────────────────────────────────────────
function PositionCard({ pos, onClick }) {
  const pnl = (pos.price - pos.entry) * pos.shares;
  const pnlPct = ((pos.price / pos.entry) - 1) * 100;
  const up = pnl >= 0;
  const color = up ? T.bull : T.bear;
  const rToStop = ((pos.price - pos.entry) / (pos.entry - pos.stop)).toFixed(1);

  return (
    <div onClick={onClick} style={{
      background:T.s1, border:`1px solid ${T.border}`,
      borderRadius:8, padding:'20px 22px',
      cursor:'pointer', transition:'all 180ms',
      borderTop:`2px solid ${color}`,
      position:'relative', overflow:'hidden',
    }}
    onMouseEnter={e=>{e.currentTarget.style.background=T.s2; e.currentTarget.style.borderColor=color+'60';}}
    onMouseLeave={e=>{e.currentTarget.style.background=T.s1; e.currentTarget.style.borderColor=T.border;}}
    >
      {/* header */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:14}}>
        <div>
          <div style={{fontSize:22,fontWeight:900,color:T.text,fontFamily:mono,lineHeight:1}}>{pos.ticker}</div>
          <div style={{fontSize:10,color:T.muted,marginTop:4}}>{pos.name}</div>
        </div>
        <Spark data={pos.candles} w={88} h={36} color={color}/>
      </div>

      {/* P&L hero */}
      <div style={{marginBottom:16}}>
        <div style={{fontSize:28,fontWeight:900,color,fontFamily:mono,lineHeight:1,letterSpacing:'-0.02em'}}>
          {up?'+':'-'}{usd(pnl)}
        </div>
        <div style={{fontSize:11,color,fontFamily:mono,fontWeight:600,marginTop:4}}>
          {pct(pnlPct)} · {rToStop}R · {pos.days}d held
        </div>
      </div>

      {/* levels */}
      <div style={{display:'flex',gap:12}}>
        {[['ENTRY',pos.entry.toFixed(2),T.sub],['NOW',pos.price.toFixed(2),T.text],['STOP',pos.stop.toFixed(2),T.bear]].map(([l,v,c])=>(
          <div key={l} style={{flex:1}}>
            <div style={{fontSize:8,color:T.muted,letterSpacing:'0.14em',fontFamily:mono,fontWeight:700}}>{l}</div>
            <div style={{fontSize:13,fontWeight:800,color:c,fontFamily:mono,marginTop:3}}>${v}</div>
          </div>
        ))}
        <div style={{flex:1}}>
          <div style={{fontSize:8,color:T.muted,letterSpacing:'0.14em',fontFamily:mono,fontWeight:700}}>SHARES</div>
          <div style={{fontSize:13,fontWeight:800,color:T.sub,fontFamily:mono,marginTop:3}}>{pos.shares}</div>
        </div>
      </div>

      {/* sector tag */}
      <div style={{
        position:'absolute', top:20, right:22,
        fontSize:8, fontWeight:700, letterSpacing:'0.14em',
        color:T.muted, fontFamily:mono,
      }}>{pos.sector.toUpperCase()}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  SETUP ROW — conviction list item
// ─────────────────────────────────────────────────────────
function SetupRow({ r, rank, onClick }) {
  const vColor = {BUY:T.bull, WAIT:T.warn, HOLD:T.cyan, AVOID:T.bear}[r.verdict]||T.sub;
  const scoreColor = r.score>=80 ? T.bull : r.score>=65 ? T.gold : T.warn;
  return (
    <div onClick={onClick} style={{
      padding:'14px 0', borderBottom:`1px solid ${T.div}`,
      display:'grid', gridTemplateColumns:'28px 52px 1fr 80px 52px',
      gap:12, alignItems:'center', cursor:'pointer',
      transition:'all 150ms',
    }}
    onMouseEnter={e=>{e.currentTarget.style.background=T.s2; e.currentTarget.style.paddingLeft='8px';}}
    onMouseLeave={e=>{e.currentTarget.style.background='transparent'; e.currentTarget.style.paddingLeft='0';}}
    >
      <span style={{fontSize:10,color:T.muted,fontFamily:mono,fontWeight:700}}>{String(rank).padStart(2,'0')}</span>
      <div>
        <div style={{fontSize:15,fontWeight:800,color:T.text,fontFamily:mono}}>{r.ticker}</div>
        <div style={{fontSize:10,color:r.changePct>=0?T.bull:T.bear,fontFamily:mono,fontWeight:600,marginTop:1}}>{pct(r.changePct)}</div>
      </div>
      <div style={{minWidth:0}}>
        <div style={{fontSize:11,color:T.sub,overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>{r.setup}</div>
        <div style={{fontSize:10,color:T.muted,marginTop:2}}>{r.sector}</div>
      </div>
      <div style={{textAlign:'right'}}>
        <Spark data={r.candles||Array.from({length:20},(_,i)=>100+i*0.3+Math.sin(i)*2)} w={80} h={24} color={r.changePct>=0?T.bull:T.bear}/>
      </div>
      <div style={{textAlign:'right'}}>
        <div style={{fontSize:20,fontWeight:900,color:scoreColor,fontFamily:mono,lineHeight:1}}>{r.score}</div>
        <div style={{fontSize:9,fontWeight:700,color:vColor,letterSpacing:'0.12em',marginTop:3}}>{r.verdict}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  SECTOR HEATMAP
// ─────────────────────────────────────────────────────────
function SectorHeatmap() {
  const max = Math.max(...SECTORS.map(s=>Math.abs(s.chg)));
  return (
    <div>
      <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between',marginBottom:14}}>
        <div style={{fontSize:9,fontWeight:700,letterSpacing:'0.2em',color:T.muted,fontFamily:mono,textTransform:'uppercase'}}>Sector Performance · Today</div>
        <div style={{fontSize:10,color:T.muted,fontFamily:mono}}>S&P 500 sectors</div>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(6,1fr)',gap:6}}>
        {SECTORS.map(s=>{
          const up = s.chg>=0;
          const intensity = Math.abs(s.chg)/max;
          const bg = up
            ? `rgba(52,211,153,${0.06 + intensity*0.28})`
            : `rgba(248,113,113,${0.06 + intensity*0.28})`;
          const border = up
            ? `rgba(52,211,153,${0.12 + intensity*0.3})`
            : `rgba(248,113,113,${0.12 + intensity*0.3})`;
          const color = up ? T.bull : T.bear;
          return (
            <div key={s.name} style={{
              padding:'12px 14px', borderRadius:5,
              background:bg, border:`1px solid ${border}`,
              cursor:'default',
            }}>
              <div style={{fontSize:10,color:up?T.bull:T.bear,fontWeight:700,fontFamily:mono,lineHeight:1.2}}>
                {s.chg>=0?'+':''}{s.chg.toFixed(2)}%
              </div>
              <div style={{fontSize:9,color:T.sub,marginTop:6,lineHeight:1.3}}>{s.name}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  TOP NAV
// ─────────────────────────────────────────────────────────
function TopNav({ onSearch, onAnalysis }) {
  const [q, setQ] = React.useState('');
  const matches = q.length>0 ? SCAN.filter(r=>r.ticker.toLowerCase().startsWith(q.toLowerCase())||r.name.toLowerCase().includes(q.toLowerCase())).slice(0,5) : [];

  return (
    <div style={{
      height:52, background:T.s1, borderBottom:`1px solid ${T.border}`,
      display:'flex', alignItems:'center', padding:'0 28px', gap:20, flexShrink:0,
      position:'relative', zIndex:10,
    }}>
      {/* Brand */}
      <div style={{display:'flex',alignItems:'center',gap:10,flexShrink:0}}>
        <div style={{
          width:28,height:28,borderRadius:5,
          background:`linear-gradient(135deg,${T.gold},${T.cyan})`,
          display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:13,fontWeight:900,color:T.bg,
        }}>S</div>
        <div style={{fontSize:12,fontWeight:800,letterSpacing:'0.14em',color:T.text,fontFamily:mono}}>SWING DESK</div>
      </div>

      <div style={{width:1,height:24,background:T.border,flexShrink:0}}/>

      {/* Date / time */}
      <div style={{fontSize:11,fontFamily:mono,color:T.muted,flexShrink:0}}>
        APR 25, 2026 &nbsp;·&nbsp; 15:58 ET
      </div>

      {/* Nav */}
      <div style={{display:'flex',gap:2}}>
        {['Dashboard','Scanner','Portfolio','Strategies','Research'].map((l,i)=>(
          <button key={l} style={{
            padding:'6px 14px',fontSize:11,fontWeight:i===0?700:500,
            color:i===0?T.text:T.muted,
            background:i===0?T.s3:'transparent',
            border:i===0?`1px solid ${T.border}`:'1px solid transparent',
            borderRadius:4,cursor:'pointer',letterSpacing:'0.03em',
          }}>{l}</button>
        ))}
      </div>

      {/* Search */}
      <div style={{marginLeft:'auto',position:'relative',width:260}}>
        <span style={{position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',fontSize:10,color:T.muted,fontFamily:mono}}>⌘K</span>
        <input value={q} onChange={e=>setQ(e.target.value)} onBlur={()=>setTimeout(()=>setQ(''),200)}
          placeholder="Search ticker or name..."
          style={{width:'100%',padding:'7px 10px 7px 38px',fontSize:11,background:T.s2,color:T.text,border:`1px solid ${T.border}`,borderRadius:4,outline:'none',boxSizing:'border-box'}}/>
        {matches.length>0&&(
          <div style={{position:'absolute',top:'calc(100%+4px)',left:0,right:0,background:T.s2,border:`1px solid ${T.border}`,borderRadius:4,overflow:'hidden',zIndex:100,boxShadow:'0 8px 32px rgba(0,0,0,0.6)'}}>
            {matches.map(r=>(
              <div key={r.ticker} onMouseDown={()=>{onAnalysis(r.ticker);setQ('');}}
                style={{padding:'10px 14px',cursor:'pointer',display:'flex',justifyContent:'space-between',borderBottom:`1px solid ${T.div}`}}
                onMouseEnter={e=>e.currentTarget.style.background=T.s3}
                onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                <span style={{fontFamily:mono,fontWeight:700,color:T.text,fontSize:12}}>{r.ticker}</span>
                <span style={{fontSize:11,color:T.muted}}>{r.verdict} · {r.score}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Live */}
      <div style={{display:'flex',alignItems:'center',gap:6,fontSize:10,fontFamily:mono,color:T.bull,flexShrink:0}}>
        <span style={{width:6,height:6,borderRadius:'50%',background:T.bull}} className="pulse-dot"/>
        MARKET OPEN
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
//  MAIN APP
// ─────────────────────────────────────────────────────────
function Dashboard() {
  const [analysisTarget, setAnalysisTarget] = React.useState(null);

  if (analysisTarget) {
    return (
      <div style={{width:'100vw',height:'100vh',display:'flex',flexDirection:'column',overflow:'hidden',background:T.bg,color:T.text,fontFamily:sans}}>
        <div style={{height:44,background:T.s1,borderBottom:`1px solid ${T.border}`,display:'flex',alignItems:'center',padding:'0 24px',gap:14,flexShrink:0}}>
          <button onClick={()=>setAnalysisTarget(null)} style={{
            display:'flex',alignItems:'center',gap:8,padding:'7px 14px',
            background:'transparent',border:`1px solid ${T.border}`,borderRadius:4,
            fontSize:11,fontWeight:700,color:T.sub,cursor:'pointer',fontFamily:mono,letterSpacing:'0.06em',
          }}>← DASHBOARD</button>
          <div style={{fontSize:12,color:T.muted,fontFamily:mono}}>Analysis · {analysisTarget}</div>
        </div>
        <iframe src="elite.html" style={{flex:1,border:'none',width:'100%'}}/>
      </div>
    );
  }

  return (
    <div style={{
      width:'100vw',height:'100vh',
      display:'flex',flexDirection:'column',
      overflow:'hidden',background:T.bg,color:T.text,fontFamily:sans,
    }}>
      <TopNav onAnalysis={setAnalysisTarget}/>

      {/* Account stats */}
      <StatStrip/>

      {/* Market strip */}
      <MarketStrip/>

      {/* Main content */}
      <div style={{flex:1,display:'grid',gridTemplateColumns:'1fr 380px',minHeight:0,overflow:'hidden'}}>

        {/* LEFT: Your book + sector heatmap */}
        <div style={{display:'flex',flexDirection:'column',overflow:'hidden',borderRight:`1px solid ${T.border}`}}>

          {/* Book header */}
          <div style={{padding:'20px 28px 0',flexShrink:0}}>
            <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between'}}>
              <div>
                <div style={{fontSize:9,fontWeight:700,letterSpacing:'0.2em',color:T.muted,fontFamily:mono,textTransform:'uppercase'}}>Your Book</div>
                <div style={{fontSize:20,fontWeight:800,color:T.text,marginTop:4,letterSpacing:'-0.01em'}}>Open Positions <span style={{fontSize:13,fontWeight:500,color:T.muted}}>— click any to drill in</span></div>
              </div>
              <div style={{display:'flex',gap:16,fontSize:11,fontFamily:mono}}>
                <span style={{color:T.sub}}>Total exposure: <span style={{color:T.text,fontWeight:700}}>$183,420</span></span>
                <span style={{color:T.bull,fontWeight:700}}>+$8,344 unrealised</span>
              </div>
            </div>
          </div>

          {/* Position grid */}
          <div style={{flex:1,overflowY:'auto',padding:'16px 28px'}} className="dashboard-scroll">
            <div style={{
              display:'grid',
              gridTemplateColumns:'repeat(auto-fill,minmax(290px,1fr))',
              gap:14,marginBottom:28,
            }}>
              {POSITIONS.map(p=>(
                <PositionCard key={p.ticker} pos={p} onClick={()=>setAnalysisTarget(p.ticker)}/>
              ))}
            </div>

            {/* Sector heatmap */}
            <div style={{paddingTop:4,borderTop:`1px solid ${T.border}`,paddingBottom:28}}>
              <SectorHeatmap/>
            </div>
          </div>
        </div>

        {/* RIGHT: Today's edge */}
        <div style={{display:'flex',flexDirection:'column',overflow:'hidden',background:T.s1}}>
          <div style={{padding:'20px 22px 14px',borderBottom:`1px solid ${T.border}`,flexShrink:0}}>
            <div style={{fontSize:9,fontWeight:700,letterSpacing:'0.2em',color:T.muted,fontFamily:mono,textTransform:'uppercase'}}>Today's Edge</div>
            <div style={{fontSize:18,fontWeight:800,color:T.text,marginTop:4,letterSpacing:'-0.01em'}}>Conviction Setups</div>
            <div style={{fontSize:11,color:T.muted,marginTop:4}}>{TOP_SETUPS.filter(r=>r.verdict==='BUY').length} BUY signals · sorted by score</div>
          </div>

          <div style={{flex:1,overflowY:'auto',padding:'4px 22px 16px'}} className="dashboard-scroll">
            {TOP_SETUPS.map((r,i)=>(
              <SetupRow key={r.ticker} r={r} rank={i+1} onClick={()=>setAnalysisTarget(r.ticker)}/>
            ))}

            {/* Market narrative */}
            <div style={{marginTop:24,padding:16,background:T.s2,border:`1px solid ${T.border}`,borderRadius:6}}>
              <div style={{fontSize:9,fontWeight:700,letterSpacing:'0.18em',color:T.gold,fontFamily:mono,marginBottom:10}}>MARKET READ · TODAY</div>
              <p style={{fontSize:12,color:T.sub,lineHeight:1.7,margin:0}}>
                Risk-on pulse with industrials and aero-defense leading. Breadth holding at 72%,
                confirming broad participation. VIX at 14.8 signals low fear — pullbacks are buyable.
                Watch <span style={{color:T.gold,fontWeight:700,cursor:'pointer'}} onClick={()=>setAnalysisTarget('TICKR')}>TICKR</span> Q1
                print May 14 — highest-conviction binary in the book.
              </p>
            </div>

            {/* Quick stats */}
            <div style={{marginTop:16,display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
              {[
                ['BUY signals','12',T.bull],
                ['AVOID','3',T.bear],
                ['Universe','30',T.sub],
                ['Avg score','71',T.gold],
              ].map(([l,v,c])=>(
                <div key={l} style={{padding:'12px',background:T.s2,border:`1px solid ${T.border}`,borderRadius:4}}>
                  <div style={{fontSize:8,color:T.muted,letterSpacing:'0.16em',fontFamily:mono,fontWeight:700}}>{l.toUpperCase()}</div>
                  <div style={{fontSize:22,fontWeight:900,color:c,fontFamily:mono,marginTop:4}}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<Dashboard/>);
