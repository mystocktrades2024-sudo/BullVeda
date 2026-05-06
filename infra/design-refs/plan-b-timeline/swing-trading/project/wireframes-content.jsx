/* global React, ReactDOM, DesignCanvas, DCSection, DCArtboard */
const { Fragment } = React;

/* ────────────────────────────────────────────────────────────────────
   Small reusable sketchy bits
─────────────────────────────────────────────────────────────────────*/
const Box = ({ children, style, className = "", dashed, thick, thin }) => (
  <div className={`sketch ${dashed?'sketch--dashed':''} ${thick?'sketch--thick':''} ${thin?'sketch--thin':''} ${className}`} style={style}>
    {children}
  </div>
);

const Pill = ({ children, kind = "grey" }) => <span className={`pill tag-${kind}`}>{children}</span>;

const Spark = ({ down, w = 60, h = 16 }) => (
  <span className={`spark ${down ? 'spark--down' : ''}`} style={{ width: w, height: h, display: 'inline-block' }} />
);

const Candles = ({ down }) => {
  const heights = down ? [10, 14, 8, 16, 12, 18, 11, 20, 15, 22] : [22, 16, 20, 12, 18, 10, 16, 8, 14, 6];
  return (
    <span className="candle-mini">
      {heights.map((h, i) => <i key={i} style={{ height: h, background: i % 3 === 0 ? '#c0432a' : '#1a1a1a' }} />)}
    </span>
  );
};

const Gauge = ({ val = 72, label = "BAP" }) => {
  const deg = Math.round((val / 100) * 280);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <div className="gauge-wrap">
        <div className="gauge" style={{ '--g': `${deg}deg` }} />
        <div className="gauge-num">{val}</div>
      </div>
      <div className="mono" style={{ opacity: 0.8 }}>{label}</div>
    </div>
  );
};

const Ruler = ({ stop = 18, entry = [22, 30], t1 = 50, t2 = 78, price = 35 }) => (
  <div style={{ position: 'relative' }}>
    <div className="ruler">
      <i className="ruler-stop" style={{ width: `${stop}%` }} />
      <i className="ruler-entry" style={{ width: `${entry[1] - stop}%` }} />
      <i className="ruler-target" style={{ width: `${100 - entry[1]}%` }} />
      <span className="ruler-dot" style={{ left: `${price}%` }} />
    </div>
    <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, fontSize: 10 }}>
      <span style={{ color: '#c0432a' }}>STOP $182</span>
      <span style={{ color: '#4a8a3a' }}>ENTRY $189-194</span>
      <span>T1 $208</span>
      <span>T2 $224</span>
    </div>
  </div>
);

const Arrow = ({ from = [0, 0], to = [40, 40], label, side = "right" }) => {
  const [x1, y1] = from, [x2, y2] = to;
  const w = Math.abs(x2 - x1) + 80;
  const h = Math.abs(y2 - y1) + 60;
  const left = Math.min(x1, x2) - 20;
  const top = Math.min(y1, y2) - 20;
  const sx = x1 - left, sy = y1 - top, ex = x2 - left, ey = y2 - top;
  return (
    <div className="arrow" style={{ left, top, width: w, height: h }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <path d={`M ${sx} ${sy} Q ${(sx+ex)/2 + 20} ${(sy+ey)/2 - 20}, ${ex} ${ey}`} fill="none" stroke="#d97a3c" strokeWidth="1.5" strokeDasharray="3 3"/>
        <polygon points={`${ex},${ey} ${ex-6},${ey-3} ${ex-6},${ey+3}`} fill="#d97a3c"/>
      </svg>
      {label && <span style={{ position: 'absolute', left: side === 'right' ? sx + 10 : sx - 90, top: sy - 18, width: 90, fontSize: 15 }}>{label}</span>}
    </div>
  );
};

const Annot = ({ children, style }) => <span className="annot" style={style}>{children}</span>;

const Header = ({ name, subtitle }) => (
  <div className="header-strip">
    <div>
      <div className="title-strip">{name}</div>
      <div className="mono" style={{ opacity: 0.6 }}>{subtitle}</div>
    </div>
    <div className="mono" style={{ opacity: 0.6 }}>2026-04-25 · 14:00 ET · MKT OPEN</div>
  </div>
);

/* ────────────────────────────────────────────────────────────────────
   DASHBOARD WIREFRAMES (4 directions)
─────────────────────────────────────────────────────────────────────*/

/* A — Hero + Dense Rows (magazine) */
const DashA = () => (
  <div className="wf-art" style={{ width: 1280, height: 880 }}>
    <Header name="Dashboard A — HERO + DENSE ROWS" subtitle="MAGAZINE LAYOUT · #1 setup featured · everything else as scannable rows" />
    {/* macro strip */}
    <Box dashed style={{ padding: 8, marginBottom: 12 }}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="mono"><b>SPX</b> 5,847 <span style={{ color: '#4a8a3a' }}>+0.42%</span></span>
        <span className="mono"><b>NDX</b> 20,512 <span style={{ color: '#4a8a3a' }}>+0.61%</span></span>
        <span className="mono"><b>VIX</b> 14.2 <span style={{ color: '#4a8a3a' }}>-3.1%</span></span>
        <span className="mono"><b>DXY</b> 102.4</span>
        <span className="mono"><b>10Y</b> 4.21%</span>
        <Pill kind="green">REGIME · RISK ON</Pill>
        <Pill kind="amber">BREADTH 68%</Pill>
        <span className="mono" style={{ marginLeft: 'auto' }}>Earnings season · WK 2 of 4</span>
      </div>
    </Box>

    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 12 }}>
      {/* HERO */}
      <Box thick style={{ padding: 14, position: 'relative' }}>
        <span className="corner-fold" />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
          <div>
            <div style={{ fontFamily: 'Caveat, cursive', fontSize: 26, fontWeight: 700 }}>#1 SETUP — NVDA</div>
            <div className="mono" style={{ opacity: 0.7 }}>NVIDIA · Semis · Mega Cap</div>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <Gauge val={88} label="BAP" />
            <Gauge val={74} label="TECH" />
            <Gauge val={91} label="FUND" />
          </div>
        </div>
        <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
          <Box thin style={{ height: 200, padding: 8 }} className="scribble">
            <span className="mono">CANDLE CHART · 6mo · Ichimoku</span>
            <Annot style={{ position: 'absolute', right: 14, bottom: 14 }}>↗ trending</Annot>
          </Box>
          <div className="col">
            <div className="mono" style={{ fontSize: 13 }}><b>$192.40</b> <span style={{ color: '#4a8a3a' }}>+1.84%</span></div>
            <Ruler />
            <div className="pill-row">
              <Pill kind="green">BUY ZONE</Pill>
              <Pill kind="amber">EARNINGS 12d</Pill>
              <Pill kind="blue">HIGH VOL</Pill>
            </div>
            <div className="mono" style={{ fontSize: 11, opacity: 0.75 }}>R/R 1:3.2 · Risk $7/sh · Size 142 sh · Risk $1k</div>
          </div>
        </div>
        <div className="note" style={{ position: 'absolute', right: -8, top: 30, transform: 'rotate(4deg)' }}>HERO MOMENT →<br/>biggest, boldest card</div>
      </Box>

      {/* sector heatmap + intel */}
      <div className="col">
        <Box style={{ padding: 8 }}>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Sector Treemap</div>
          <div className="heat">
            <div style={{ background: '#b5d4a3' }}>SEMIS<br/><span className="mono">+1.8%</span></div>
            <div style={{ background: '#cee3c0' }}>SOFTWARE +0.9%</div>
            <div style={{ background: '#e8e1d2' }}>FINANCE 0.0%</div>
            <div style={{ background: '#e6a596' }}>ENERGY -1.4%</div>
            <div style={{ background: '#f0c8b8' }}>UTIL -0.6%</div>
            <div style={{ background: '#d4cfc4' }}>STAPLES +0.1%</div>
          </div>
          <Annot style={{ display: 'block', marginTop: 4 }}>← tap a tile to filter watchlist</Annot>
        </Box>
        <Box style={{ padding: 8, flex: 1 }}>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Intel feed</div>
          <div className="mono" style={{ fontSize: 11, lineHeight: 1.6 }}>
            <div>● 13:42 · NVDA · upgrade $215 PT <Pill kind="green">+</Pill></div>
            <div>● 12:15 · AMD · supply chain note <Pill kind="amber">~</Pill></div>
            <div>● 11:30 · CPI inline · risk-on <Pill kind="green">+</Pill></div>
            <div>● 10:14 · TSLA · delivery miss <Pill kind="red">−</Pill></div>
            <div className="placeholder">… 12 more</div>
          </div>
        </Box>
      </div>
    </div>

    {/* dense rows */}
    <Box style={{ marginTop: 12, padding: 0 }}>
      <table className="wf">
        <thead>
          <tr>
            <th>#</th><th>TICKER</th><th>SETUP</th><th>BAP</th><th>PRICE</th><th>CHG</th><th>SPARK</th><th>RULER</th><th>ZONE</th><th>R:R</th><th>EARN</th>
          </tr>
        </thead>
        <tbody>
          {[
            ['2','AVGO','Bull flag · D1',82,'$1,742','+0.9%',false,'green','BUY','1:2.8','—'],
            ['3','META','Pullback to 50',79,'$612','+0.4%',false,'amber','WATCH','1:2.1','+8d'],
            ['4','PANW','Cup & handle',76,'$382','-0.2%',false,'amber','WATCH','1:3.0','+22d'],
            ['5','SHOP','Breakout retest',74,'$98','+1.1%',false,'green','BUY','1:2.4','—'],
            ['6','TSLA','Failed breakout',38,'$248','-2.1%',true,'red','AVOID','—','—'],
            ['7','XOM','Distribution',32,'$104','-1.4%',true,'red','AVOID','—','—'],
          ].map((r, i) => (
            <tr key={i}>
              <td className="mono">{r[0]}</td>
              <td><b>{r[1]}</b></td>
              <td>{r[2]}</td>
              <td><span className="mono"><b>{r[3]}</b></span></td>
              <td className="mono">{r[4]}</td>
              <td className="mono" style={{ color: r[5].startsWith('+') ? '#4a8a3a' : '#c0432a' }}>{r[5]}</td>
              <td><Spark down={r[6]} w={70}/></td>
              <td><div style={{ width: 110 }}><Ruler /></div></td>
              <td><Pill kind={r[7]}>{r[8]}</Pill></td>
              <td className="mono">{r[9]}</td>
              <td className="mono">{r[10]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  </div>
);

/* B — Dense Bloomberg Table */
const DashB = () => (
  <div className="wf-art" style={{ width: 1280, height: 880 }}>
    <Header name="Dashboard B — DENSE TABLE" subtitle="BLOOMBERG-STYLE · maximum tickers visible · sparklines inline · click to expand" />
    <Box dashed style={{ padding: 6, marginBottom: 8 }}>
      <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }} className="mono">
        <span><b>MACRO</b> SPX +0.4 · NDX +0.6 · VIX 14.2 · DXY 102 · 10Y 4.21</span>
        <Pill kind="green">RISK ON</Pill>
        <span style={{ marginLeft: 'auto' }}>Filters: <Pill kind="grey">All Sectors</Pill> <Pill kind="grey">BAP &gt; 60</Pill> <Pill kind="grey">No Earnings</Pill></span>
      </div>
    </Box>

    <Box style={{ padding: 0 }}>
      <table className="wf" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            {['#','SYM','SECT','SETUP','BAP','TECH','FUND','SMC','PX','%','5D','20D','RVOL','SPARK 1M','RULER','ENT','STOP','T1','RR','EARN','NEWS'].map(h =>
              <th key={h} className="mono" style={{ fontSize: 10 }}>{h}</th>
            )}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 14 }).map((_, i) => {
            const sym = ['NVDA','AVGO','META','PANW','SHOP','MSFT','GOOGL','CRWD','NOW','UBER','LLY','COIN','MARA','TSLA'][i];
            const bap = [88,82,79,76,74,72,70,68,66,64,62,55,42,38][i];
            const down = i >= 12;
            return (
              <tr key={i}>
                <td className="mono">{i+1}</td>
                <td><b>{sym}</b></td>
                <td className="mono" style={{ fontSize: 10 }}>SEMI</td>
                <td style={{ fontSize: 11 }}>Bull flag</td>
                <td className="mono"><b style={{ color: bap > 70 ? '#4a8a3a' : bap > 50 ? '#d97a3c' : '#c0432a' }}>{bap}</b></td>
                <td className="mono">{bap-4}</td>
                <td className="mono">{bap-2}</td>
                <td className="mono">{bap-8}</td>
                <td className="mono">$192</td>
                <td className="mono" style={{ color: down ? '#c0432a' : '#4a8a3a' }}>{down ? '-1.2' : '+0.8'}</td>
                <td className="mono" style={{ color: down ? '#c0432a' : '#4a8a3a' }}>{down ? '-3.4' : '+4.2'}</td>
                <td className="mono" style={{ color: down ? '#c0432a' : '#4a8a3a' }}>{down ? '-8.1' : '+11'}</td>
                <td className="mono">1.4×</td>
                <td><Spark down={down} w={60} h={14}/></td>
                <td><div style={{ width: 80 }}><Ruler /></div></td>
                <td className="mono">$189</td>
                <td className="mono">$182</td>
                <td className="mono">$208</td>
                <td className="mono">1:{(2 + i*0.1).toFixed(1)}</td>
                <td className="mono">{i % 4 === 0 ? '+12d' : '—'}</td>
                <td>{i % 3 === 0 ? <Pill kind="green">+</Pill> : i % 5 === 0 ? <Pill kind="red">−</Pill> : ''}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Box>

    <div style={{ position: 'absolute', right: 18, top: 90 }}>
      <div className="note">21 columns. Mono everywhere.<br/>Click row → drawer below.</div>
    </div>
    <div style={{ position: 'absolute', left: 18, bottom: 14, right: 18 }}>
      <Box dashed style={{ padding: 8 }}>
        <span className="mono" style={{ opacity: 0.6 }}>↳ EXPANDED ROW DRAWER · slides down with chart + plan + intel · keyboard ↑↓ to walk rows</span>
      </Box>
    </div>
  </div>
);

/* C — Kanban by Setup Stage */
const DashC = () => (
  <div className="wf-art" style={{ width: 1280, height: 880 }}>
    <Header name="Dashboard C — KANBAN BY STAGE" subtitle="WORKFLOW VIEW · Watching → Ready → In Trade → Cooling · drag between columns" />
    <Box dashed style={{ padding: 8, marginBottom: 12 }}>
      <span className="mono">REGIME RISK-ON · BREADTH 68% · VIX 14.2 · 4 active positions · $4.2k risk in market</span>
    </Box>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, height: 720 }}>
      {[
        { name: 'WATCHING', tone: 'grey', count: 12, items: [
          ['CRWD',62,'Base building'], ['NOW',58,'Wait for trigger'], ['UBER',54,'Above 200'], ['LLY',60,'Cooling'], ['COIN',48,'Choppy']
        ] },
        { name: 'READY', tone: 'amber', count: 5, items: [
          ['NVDA',88,'Buy zone HOT'], ['AVGO',82,'Bull flag'], ['META',79,'Pullback 50'], ['PANW',76,'C&H neckline'], ['SHOP',74,'Retest']
        ] },
        { name: 'IN TRADE', tone: 'green', count: 3, items: [
          ['MSFT',72,'+4.2% · T1 hit'], ['GOOGL',70,'+1.1% · trail'], ['ANET',68,'-0.4% · stop $312']
        ] },
        { name: 'COOLING', tone: 'red', count: 4, items: [
          ['TSLA',38,'Avoid · failed'], ['XOM',32,'Distribution'], ['MARA',42,'Wait reset'], ['AAPL',45,'Sideways']
        ] }
      ].map((col, ci) => (
        <Box key={ci} thick style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>{col.name}</span>
            <Pill kind={col.tone}>{col.count}</Pill>
          </div>
          {col.items.map((it, i) => (
            <Box key={i} thin style={{ padding: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <b>{it[0]}</b>
                <Gauge val={it[1]} label="" />
              </div>
              <div className="mono" style={{ fontSize: 10.5, opacity: 0.8, marginTop: 2 }}>{it[2]}</div>
              <Spark down={ci === 3} w="100%" h={14}/>
              <div style={{ marginTop: 4 }}><Ruler /></div>
            </Box>
          ))}
          {ci === 0 && (
            <div className="placeholder mono" style={{ fontSize: 10 }}>… +7 more</div>
          )}
        </Box>
      ))}
    </div>
    <div style={{ position: 'absolute', right: 18, top: 100 }}>
      <div className="note">Stage-based mental model.<br/>Tickers move L→R as setups mature.</div>
    </div>
  </div>
);

/* D — Split: Watchlist + Persistent Detail */
const DashD = () => (
  <div className="wf-art" style={{ width: 1280, height: 880 }}>
    <Header name="Dashboard D — SPLIT VIEW" subtitle="LEFT RAIL = list · RIGHT = persistent detail · keyboard-driven · IDE feel" />
    <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 10, height: 770 }}>
      {/* left rail */}
      <Box style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="mono" style={{ display: 'flex', justifyContent: 'space-between' }}><b>WATCHLIST · 24</b> <span>↕ BAP</span></div>
        <input className="mono sketch" style={{ padding: '4px 8px', fontFamily: 'inherit' }} placeholder="/ search..." />
        {['NVDA','AVGO','META','PANW','SHOP','MSFT','GOOGL','CRWD','NOW','UBER','LLY','COIN','MARA','TSLA'].map((s, i) => (
          <Box key={s} thin style={{ padding: 6, background: i === 0 ? '#f5e2c8' : 'transparent', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="mono" style={{ width: 14, opacity: 0.5 }}>{i+1}</span>
            <b style={{ width: 50 }}>{s}</b>
            <Spark down={i >= 12} w={60} h={14}/>
            <span className="mono" style={{ marginLeft: 'auto', color: i >= 12 ? '#c0432a' : '#4a8a3a' }}>{[88,82,79,76,74,72,70,68,66,64,62,55,42,38][i]}</span>
          </Box>
        ))}
      </Box>
      {/* right detail */}
      <Box thick style={{ padding: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div>
            <span style={{ fontFamily: 'Caveat, cursive', fontSize: 32, fontWeight: 700 }}>NVDA</span>
            <span className="mono" style={{ marginLeft: 12, opacity: 0.7 }}>NVIDIA · Semis · $4.7T</span>
          </div>
          <div className="mono"><b>$192.40</b> <span style={{ color: '#4a8a3a' }}>+1.84%</span></div>
        </div>
        <div className="tabs">
          <span className="on">Overview</span><span>Chart+</span><span>TradingView</span><span>Fund+</span><span>Intel</span><span>SMC</span><span>Plan</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
          <div className="col">
            <Box thin style={{ height: 280, padding: 8 }} className="scribble">
              <span className="mono">CANDLE CHART · 6mo · MA20/50/200 · Ichimoku</span>
            </Box>
            <Box thin style={{ padding: 8 }}>
              <div className="mono" style={{ fontSize: 11, marginBottom: 4, fontWeight: 600 }}>PRICE MAP</div>
              <Ruler />
            </Box>
          </div>
          <div className="col">
            <Box thin style={{ padding: 8 }}>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'space-around' }}>
                <Gauge val={88} label="BAP" />
                <Gauge val={74} label="TECH" />
                <Gauge val={91} label="FUND" />
              </div>
            </Box>
            <Box thin style={{ padding: 8 }}>
              <div className="mono" style={{ fontSize: 11, fontWeight: 600 }}>TRADE PLAN</div>
              <div className="mono" style={{ fontSize: 11, lineHeight: 1.7 }}>
                <div>Setup · Bull flag · D1</div>
                <div>Entry · $189 - $194</div>
                <div>Stop · $182 (-3.6%)</div>
                <div>T1 · $208 · 1:2.6</div>
                <div>T2 · $224 · 1:4.5</div>
                <div>Size · 142 sh ($1k risk)</div>
              </div>
            </Box>
            <Box thin style={{ padding: 8 }}>
              <div className="mono" style={{ fontSize: 11, fontWeight: 600 }}>INTEL · 4 today</div>
              <div className="mono" style={{ fontSize: 10.5, lineHeight: 1.5 }}>
                <div>13:42 · upgrade PT $215 <Pill kind="green">+</Pill></div>
                <div>11:30 · CPI inline <Pill kind="green">+</Pill></div>
                <div>09:55 · CES keynote <Pill kind="amber">~</Pill></div>
              </div>
            </Box>
          </div>
        </div>
      </Box>
    </div>
    <div style={{ position: 'absolute', right: 18, top: 60 }}>
      <div className="note">↑↓ walks list. Detail updates instantly. No modals.</div>
    </div>
  </div>
);

/* ────────────────────────────────────────────────────────────────────
   TICKER DETAIL WIREFRAMES
─────────────────────────────────────────────────────────────────────*/

const TickerA = () => (
  <div className="wf-art" style={{ width: 1280, height: 860 }}>
    <Header name="Ticker A — TABBED CLASSIC" subtitle="Existing pattern, refined · 7 tabs across the top · Overview is default" />
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 8 }}>
      <span style={{ fontFamily: 'Caveat, cursive', fontSize: 38, fontWeight: 700 }}>NVDA</span>
      <span className="mono" style={{ opacity: 0.7 }}>NVIDIA Corp · Semiconductors · $4.7T</span>
      <span className="mono" style={{ marginLeft: 'auto', fontSize: 18 }}><b>$192.40</b> <span style={{ color: '#4a8a3a' }}>+$3.48 (+1.84%)</span></span>
    </div>
    <div className="tabs">
      <span className="on">OVERVIEW</span><span>CHART+</span><span>TRADINGVIEW</span><span>FUND+</span><span>INTEL</span><span>SMC</span><span>PLAN</span>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
      <Box style={{ padding: 8, gridColumn: '1 / 3' }}>
        <div style={{ height: 320 }} className="scribble" />
        <div style={{ marginTop: 6 }}><Ruler /></div>
      </Box>
      <div className="col">
        <Box style={{ padding: 8, display: 'flex', justifyContent: 'space-around' }}>
          <Gauge val={88} label="BAP" />
          <Gauge val={74} label="TECH" />
          <Gauge val={91} label="FUND" />
        </Box>
        <Box style={{ padding: 8 }}>
          <div className="mono" style={{ fontWeight: 600 }}>SUB-SCORES</div>
          {['Trend','Momentum','Volume','Pattern','Relative Str'].map((s, i) => (
            <div key={s} className="mono" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
              <span style={{ width: 92 }}>{s}</span>
              <div style={{ flex: 1, height: 6, background: '#e8e1d2', border: '1px solid var(--ink)' }}>
                <div style={{ width: `${[80,72,90,68,75][i]}%`, height: '100%', background: '#4a8a3a' }} />
              </div>
              <span>{[80,72,90,68,75][i]}</span>
            </div>
          ))}
        </Box>
        <Box style={{ padding: 8 }}>
          <div className="mono" style={{ fontWeight: 600 }}>PLAN</div>
          <div className="mono" style={{ fontSize: 11 }}>Entry $189-194 · Stop $182 · T1 $208 · T2 $224 · 1:3.2</div>
        </Box>
      </div>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 10 }}>
      <Box style={{ padding: 8 }}>
        <div className="mono" style={{ fontWeight: 600 }}>INTEL · 4 TODAY</div>
        <div className="mono" style={{ fontSize: 11, lineHeight: 1.7 }}>
          <div>13:42 · Citi raises PT to $215 <Pill kind="green">+</Pill></div>
          <div>11:30 · CPI inline · risk-on <Pill kind="green">+</Pill></div>
          <div>09:55 · CES keynote details <Pill kind="amber">~</Pill></div>
          <div>08:14 · TSMC capex up <Pill kind="green">+</Pill></div>
        </div>
      </Box>
      <Box style={{ padding: 8 }}>
        <div className="mono" style={{ fontWeight: 600 }}>FUNDAMENTAL PILLARS</div>
        {['Growth','Profitability','Quality','Valuation','Momentum'].map((p, i) => (
          <div key={p} className="mono" style={{ display: 'flex', gap: 6, fontSize: 11, alignItems: 'center' }}>
            <span style={{ width: 80 }}>{p}</span>
            <div style={{ flex: 1, height: 6, background: '#e8e1d2', border: '1px solid var(--ink)' }}>
              <div style={{ width: `${[92,88,85,55,90][i]}%`, height: '100%', background: i === 3 ? '#d97a3c' : '#4a8a3a' }} />
            </div>
            <span>{[92,88,85,55,90][i]}/100</span>
          </div>
        ))}
      </Box>
    </div>
  </div>
);

const TickerB = () => (
  <div className="wf-art" style={{ width: 1280, height: 860 }}>
    <Header name="Ticker B — SCROLLING SINGLE PAGE" subtitle="No tabs · everything flows top-to-bottom · sticky nav rail on left" />
    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 10 }}>
      <Box dashed style={{ padding: 6, position: 'sticky', top: 12, height: 'fit-content' }}>
        <div className="mono" style={{ fontSize: 10, lineHeight: 2 }}>
          <div><b>● HEADER</b></div>
          <div>○ SCORES</div>
          <div>○ CHART</div>
          <div>○ PLAN</div>
          <div>○ FUND</div>
          <div>○ TECH</div>
          <div>○ SMC</div>
          <div>○ INTEL</div>
          <div>○ NOTES</div>
        </div>
      </Box>
      <div className="col">
        <Box style={{ padding: 10 }}>
          <div className="mono" style={{ opacity: 0.5, fontSize: 10 }}># HEADER</div>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 38, fontWeight: 700 }}>NVDA <span className="mono" style={{ fontSize: 16, fontWeight: 400 }}>$192.40 +1.84%</span></div>
        </Box>
        <Box style={{ padding: 10 }}>
          <div className="mono" style={{ opacity: 0.5, fontSize: 10 }}># SCORES</div>
          <div style={{ display: 'flex', gap: 18 }}>
            <Gauge val={88} label="BAP" />
            <Gauge val={74} label="TECH" />
            <Gauge val={91} label="FUND" />
            <Gauge val={68} label="SMC" />
            <Gauge val={82} label="INTEL" />
          </div>
        </Box>
        <Box style={{ padding: 10, height: 230 }} className="scribble">
          <div className="mono" style={{ opacity: 0.5, fontSize: 10 }}># CHART</div>
        </Box>
        <Box style={{ padding: 10 }}>
          <div className="mono" style={{ opacity: 0.5, fontSize: 10 }}># PLAN</div>
          <Ruler />
          <div className="mono" style={{ marginTop: 6, fontSize: 11 }}>Entry $189-194 · Stop $182 · T1 $208 · T2 $224 · Size 142 sh · Risk $1k</div>
        </Box>
        <Box style={{ padding: 10 }}>
          <div className="mono" style={{ opacity: 0.5, fontSize: 10 }}># FUND PILLARS</div>
          <span className="placeholder mono">…content scrolls below…</span>
        </Box>
      </div>
    </div>
    <div className="note" style={{ position: 'absolute', right: 18, top: 60 }}>One linear story. Spacebar scrolls. ⌘F finds anything.</div>
  </div>
);

const TickerC = () => (
  <div className="wf-art" style={{ width: 1280, height: 860 }}>
    <Header name="Ticker C — DASHBOARD GRID" subtitle="No tabs, no scroll — every panel visible at once · widget grid · 1 screen" />
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 8 }}>
      <span style={{ fontFamily: 'Caveat, cursive', fontSize: 32, fontWeight: 700 }}>NVDA</span>
      <span className="mono" style={{ marginLeft: 'auto', fontSize: 16 }}><b>$192.40</b> <span style={{ color: '#4a8a3a' }}>+1.84%</span></span>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'repeat(3, 220px)', gap: 8 }}>
      <Box style={{ gridColumn: 'span 2', gridRow: 'span 2', padding: 8 }} className="scribble">
        <div className="mono" style={{ fontWeight: 600 }}>CHART (large)</div>
      </Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>SCORES</div><div style={{ display: 'flex', justifyContent: 'space-around', marginTop: 12 }}><Gauge val={88} label="BAP"/><Gauge val={74} label="T"/></div></Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>PLAN</div><Ruler /><div className="mono" style={{ fontSize: 10, marginTop: 4 }}>R:R 1:3.2 · 142 sh</div></Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>FUND PILLARS</div><div className="mono" style={{ fontSize: 10 }}>Growth 92 · Prof 88 · Qual 85 · Val 55 · Mom 90</div></Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>SMC</div><div className="mono" style={{ fontSize: 10 }}>BOS · OB at $185 · FVG $190-192</div></Box>
      <Box style={{ padding: 8, gridColumn: 'span 2' }}><div className="mono" style={{ fontWeight: 600 }}>INTEL</div><div className="mono" style={{ fontSize: 10, lineHeight: 1.7 }}><div>13:42 · upgrade PT $215 +</div><div>11:30 · CPI inline +</div></div></Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>VOLUME</div><Spark w="100%" h={70} /></Box>
      <Box style={{ padding: 8 }}><div className="mono" style={{ fontWeight: 600 }}>RVOL/RSI</div><div className="mono" style={{ fontSize: 10 }}>RVOL 1.4× · RSI 64 · ADX 28</div></Box>
    </div>
    <div className="note" style={{ position: 'absolute', right: 18, top: 60 }}>Cockpit. Drag to rearrange.</div>
  </div>
);

/* ────────────────────────────────────────────────────────────────────
   TRADE PLAN WIREFRAMES
─────────────────────────────────────────────────────────────────────*/

const PlanA = () => (
  <div className="wf-art" style={{ width: 1100, height: 720 }}>
    <Header name="Plan A — LADDER VIEW" subtitle="Vertical price ladder · stop / entry / T1 / T2 stacked visually · big picture" />
    <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 14 }}>
      <Box thick style={{ padding: 14 }}>
        <div style={{ fontFamily: 'Caveat, cursive', fontSize: 24, fontWeight: 700 }}>NVDA · TRADE LADDER</div>
        <div style={{ position: 'relative', height: 480, marginTop: 12 }}>
          {[
            ['$224', 'T2 — TARGET 2', '+16.6%', '#4a8a3a', 6],
            ['$208', 'T1 — TARGET 1', '+8.3%', '#4a8a3a', 110],
            ['$194', 'ENTRY HIGH', '0%', '#1a1a1a', 220],
            ['$189', 'ENTRY LOW', '-2.6%', '#1a1a1a', 290],
            ['$182', 'STOP', '-6.3%', '#c0432a', 410]
          ].map((r, i) => (
            <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: r[4], display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="mono" style={{ width: 60, fontWeight: 700, color: r[3] }}>{r[0]}</span>
              <div style={{ flex: 1, height: 0, borderTop: `1.5px ${i === 2 || i === 3 ? 'dashed' : 'solid'} ${r[3]}` }} />
              <span className="mono" style={{ fontSize: 11 }}>{r[1]}</span>
              <span className="mono" style={{ width: 50, textAlign: 'right', color: r[3] }}>{r[2]}</span>
            </div>
          ))}
          <div style={{ position: 'absolute', left: 64, top: 250, right: 100, height: 60, background: 'rgba(74,138,58,0.12)', border: '1.5px solid #4a8a3a', borderRadius: 3 }}>
            <span className="mono" style={{ position: 'absolute', right: 6, top: 4, fontSize: 10, color: '#4a8a3a', fontWeight: 600 }}>BUY ZONE</span>
          </div>
          <div style={{ position: 'absolute', left: 64, top: 360, right: 100, height: 50, background: 'repeating-linear-gradient(45deg, rgba(192,67,42,0.08) 0 4px, rgba(192,67,42,0.16) 4px 8px)', border: '1.5px dashed #c0432a', borderRadius: 3 }}>
            <span className="mono" style={{ position: 'absolute', right: 6, top: 4, fontSize: 10, color: '#c0432a', fontWeight: 600 }}>NO-GO</span>
          </div>
          {/* current price marker */}
          <div style={{ position: 'absolute', left: -10, top: 198, width: 'calc(100% + 20px)' }}>
            <div style={{ background: '#d97a3c', height: 2 }} />
            <span className="mono" style={{ position: 'absolute', right: -6, top: -10, background: '#d97a3c', color: '#fff', padding: '1px 6px', fontSize: 10, fontWeight: 700 }}>$192.40 NOW</span>
          </div>
        </div>
      </Box>
      <div className="col">
        <Box style={{ padding: 10 }}>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>SIZING</div>
          <div className="mono" style={{ fontSize: 12, lineHeight: 2 }}>
            <div>Account · $200,000</div>
            <div>Risk per trade · 0.5% = $1,000</div>
            <div>Risk per share · $7 (entry $189 → stop $182)</div>
            <div><b>Position size · 142 shares</b></div>
            <div>Notional · $26,838 (13.4% of acct)</div>
          </div>
        </Box>
        <Box style={{ padding: 10 }}>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>R:R</div>
          <div style={{ display: 'flex', gap: 14, marginTop: 4 }}>
            <Gauge val={32} label="R 1:3.2" />
            <Gauge val={45} label="R 1:4.5" />
          </div>
        </Box>
        <Box style={{ padding: 10 }}>
          <div style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>EXIT RULES</div>
          <div className="mono" style={{ fontSize: 11, lineHeight: 1.7 }}>
            <div>1. Hard stop · close below $182 (D1)</div>
            <div>2. T1 · sell 50% · trail rest to entry</div>
            <div>3. T2 · sell 30% · trail 20MA</div>
            <div>4. Time stop · 6 weeks</div>
          </div>
        </Box>
      </div>
    </div>
  </div>
);

const PlanB = () => (
  <div className="wf-art" style={{ width: 1100, height: 720 }}>
    <Header name="Plan B — TIMELINE FLOW" subtitle="Horizontal flow · setup → trigger → entry → manage → exit · stage-by-stage" />
    <div style={{ display: 'flex', gap: 0, alignItems: 'stretch', height: 240 }}>
      {[
        ['1. SETUP','grey','Bull flag forming · 18d base · vol drying · D1 close above 50MA'],
        ['2. TRIGGER','amber','Daily close > $192 with vol > 1.3× avg · check breadth'],
        ['3. ENTRY','green','Buy $189-194 · 142 sh · risk $1k · alert set'],
        ['4. MANAGE','blue','Trail stop weekly · scale 50% at T1 · book profits'],
        ['5. EXIT','red','T2 hit OR stop hit OR 6w time stop · log result']
      ].map((s, i, arr) => (
        <Fragment key={i}>
          <Box thick style={{ padding: 10, flex: 1, position: 'relative' }}>
            <Pill kind={s[1]}>{s[0]}</Pill>
            <div className="mono" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>{s[2]}</div>
            {i === 2 && <Annot style={{ position: 'absolute', bottom: 6, right: 6 }}>← we are here</Annot>}
          </Box>
          {i < arr.length - 1 && <div style={{ width: 28, display: 'grid', placeItems: 'center', fontFamily: 'Caveat, cursive', fontSize: 30, color: '#d97a3c' }}>→</div>}
        </Fragment>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10, marginTop: 14 }}>
      <Box style={{ padding: 10 }}>
        <div style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>PRICE MAP</div>
        <Ruler />
      </Box>
      <Box style={{ padding: 10 }}>
        <div style={{ fontFamily: 'Caveat, cursive', fontSize: 22, fontWeight: 700 }}>NUMBERS</div>
        <div className="mono" style={{ fontSize: 11, lineHeight: 1.7 }}>
          <div>Entry $189 · Stop $182 · T1 $208 · T2 $224</div>
          <div>R:R · 1:3.2 / 1:4.5</div>
          <div>Size · 142 sh · $26.8k · 13.4%</div>
        </div>
      </Box>
    </div>
    <Box dashed style={{ padding: 10, marginTop: 10 }}>
      <span className="mono" style={{ fontSize: 11 }}>JOURNAL · "Setup looks clean. Worried about earnings 12d out — may scale at T1 first." — 2026-04-25 09:14</span>
    </Box>
  </div>
);

/* ────────────────────────────────────────────────────────────────────
   APP / ARRANGEMENT
─────────────────────────────────────────────────────────────────────*/

function App() {
  return (
    <DesignCanvas
      title="Swing Trading — Wireframes"
      subtitle="Lo-fi exploration. Pick a direction and I'll build the polished hi-fi version."
    >
      <DCSection id="dash" title="Dashboard / Watchlist — pick a direction">
        <DCArtboard id="dash-a" label="A · Hero + Dense Rows" width={1280} height={880}><DashA /></DCArtboard>
        <DCArtboard id="dash-b" label="B · Bloomberg Dense Table" width={1280} height={880}><DashB /></DCArtboard>
        <DCArtboard id="dash-c" label="C · Kanban by Stage" width={1280} height={880}><DashC /></DCArtboard>
        <DCArtboard id="dash-d" label="D · Split: List + Detail" width={1280} height={880}><DashD /></DCArtboard>
      </DCSection>

      <DCSection id="ticker" title="Ticker detail — three approaches">
        <DCArtboard id="t-a" label="A · Tabbed (refined existing)" width={1280} height={860}><TickerA /></DCArtboard>
        <DCArtboard id="t-b" label="B · Single Scrolling Page" width={1280} height={860}><TickerB /></DCArtboard>
        <DCArtboard id="t-c" label="C · Cockpit Grid (no tabs)" width={1280} height={860}><TickerC /></DCArtboard>
      </DCSection>

      <DCSection id="plan" title="Trade plan — two approaches">
        <DCArtboard id="p-a" label="A · Vertical Ladder" width={1100} height={720}><PlanA /></DCArtboard>
        <DCArtboard id="p-b" label="B · Timeline / Flow" width={1100} height={720}><PlanB /></DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
