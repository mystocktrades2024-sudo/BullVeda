/* global React, ReactDOM, window */
const { useState, useEffect, useMemo, useRef } = React;
const { WATCHLIST, INTEL, PILLARS, genSpark, genCandles } = window.ST_DATA;
const { Sparkline, MiniRuler, BigRuler, Gauge, HeroChart, Tape, MacroStrip, Heatmap, IntelFeed } = window;
const { TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakToggle, TweakSelect } = window;

const DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "density": "normal",
  "accent": "amber",
  "showSparklines": true,
  "showRulers": true,
  "showGauges": true
}/*EDITMODE-END*/;

const ACCENT_MAP = {
  amber:  'oklch(78% 0.16 75)',
  cyan:   'oklch(76% 0.13 215)',
  violet: 'oklch(72% 0.18 320)',
  green:  'oklch(72% 0.18 145)',
};

/* ─── Top bar ─── */
function TopBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  const fmt = now.toLocaleTimeString('en-US', { hour12: false, timeZone: 'America/New_York' });
  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">G</div>
        <div>
          <div className="brand-name">GARI · SWING</div>
          <div className="brand-sub">TERMINAL v2.6 · 2026-04-25</div>
        </div>
      </div>
      <Tape />
      <div className="topbar-right">
        <span className="clock-dot" />
        <span>{fmt} ET</span>
        <span className="dim2">·</span>
        <span style={{color:'var(--green)'}}>MKT OPEN</span>
        <span className="dim2">·</span>
        <span>2h 14m to close</span>
      </div>
    </div>
  );
}

/* ─── Side rail ─── */
function Rail({ view, setView }) {
  const items = [
    { id:'dash',   label:'Dashboard', icon:'M3 3h7v7H3zm11 0h7v7h-7zm0 11h7v7h-7zM3 14h7v7H3z' },
    { id:'watch',  label:'Watch',     icon:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9a3 3 0 100 6 3 3 0 000-6z' },
    { id:'plan',   label:'Plan',      icon:'M3 5h12v3H3zm0 5h18v3H3zm0 5h9v3H3z' },
    { id:'intel',  label:'Intel',     icon:'M3 4h18v4H3zm0 6h18v4H3zm0 6h12v4H3z' },
    { id:'sect',   label:'Sectors',   icon:'M4 4h7v9H4zm9 0h7v5h-7zm0 7h7v9h-7zm-9 4h7v5H4z' },
    { id:'jrnl',   label:'Journal',   icon:'M4 3h11l5 5v13H4z M14 3v6h6' },
  ];
  return (
    <nav className="rail">
      {items.map(it => (
        <button key={it.id} title={it.label} className={`rail-btn ${view === it.id ? 'on' : ''}`} onClick={() => setView(it.id)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d={it.icon} /></svg>
        </button>
      ))}
      <div className="rail-spacer" />
    </nav>
  );
}

/* ─── Hero (#1 setup) ─── */
function Hero({ row, onOpen }) {
  const candles = useMemo(() => genCandles(80, 13, row.px), [row.sym]);
  return (
    <div className="hero" onClick={() => onOpen(row)}>
      <div className="hero-stripe" />
      <div className="hero-head">
        <div>
          <div className="hero-title">
            <span className="hero-rank">RANK #1 · TOP SETUP</span>
            <span className="hero-sym">{row.sym}</span>
            <span className="hero-name">{row.name} · {row.sect} · MCAP {row.cap}</span>
          </div>
          <div className="hero-meta">
            <span className="tag amber">{row.setup}</span>
            <span className="tag green">BUY ZONE</span>
            {row.earn != null && <span className="tag amber">EARN +{row.earn}d</span>}
            <span className="tag blue">RVOL {row.rvol.toFixed(1)}×</span>
            <span className="tag dim">D5 +{row.d5}%</span>
            <span className="tag dim">D20 +{row.d20}%</span>
          </div>
        </div>
        <div className="hero-price">
          <div className="hero-price-val num">${row.px.toFixed(2)}</div>
          <div className={`hero-price-chg ${row.chg >= 0 ? 'up' : 'down'}`}>
            {row.chg >= 0 ? '▲ +' : '▼ '}{row.chg.toFixed(2)}% &nbsp;·&nbsp; +${(row.px * row.chg / 100).toFixed(2)}
          </div>
        </div>
      </div>
      <div className="hero-body">
        <div className="chart-card" style={{ height: 240, padding: 0 }}>
          <HeroChart candles={candles} levels={{ stop: row.stop, entry: row.entry, t1: row.t1, t2: row.t2 }} />
        </div>
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          <div className="gauges">
            <Gauge val={row.bap}  label="BAP" />
            <Gauge val={row.tech} label="TECH" />
            <Gauge val={row.fund} label="FUND" />
          </div>
          <BigRuler lo={row.lo} hi={row.hi} stop={row.stop} entry={row.entry} t1={row.t1} t2={row.t2} px={row.px} />
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginTop:4 }}>
            <div><span className="lbl">R:R T1</span><div className="num" style={{fontWeight:600,fontSize:14,color:'var(--accent)'}}>1 : {((row.t1 - row.entry[0]) / (row.entry[0] - row.stop)).toFixed(1)}</div></div>
            <div><span className="lbl">R:R T2</span><div className="num" style={{fontWeight:600,fontSize:14,color:'var(--accent-2)'}}>1 : {((row.t2 - row.entry[0]) / (row.entry[0] - row.stop)).toFixed(1)}</div></div>
            <div><span className="lbl">SIZE</span><div className="num" style={{fontWeight:600,fontSize:14}}>142 sh</div></div>
            <div><span className="lbl">RISK</span><div className="num" style={{fontWeight:600,fontSize:14,color:'var(--red)'}}>$1,000</div></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Watchlist table ─── */
function Watchlist({ rows, onOpen, activeSym, showSparklines, showRulers }) {
  const [tab, setTab]   = useState('all');
  const [sort, setSort] = useState('rank');
  const [q, setQ]       = useState('');

  const filtered = useMemo(() => {
    let r = rows.filter(x =>
      (tab === 'all' || x.stage === ({ ready:'READY', trade:'IN TRADE', watch:'WATCH', cooling:'COOLING' }[tab])) &&
      (q === '' || x.sym.toLowerCase().includes(q.toLowerCase()) || x.name.toLowerCase().includes(q.toLowerCase()))
    );
    r = [...r].sort((a, b) => {
      if (sort === 'bap') return b.bap - a.bap;
      if (sort === 'chg') return b.chg - a.chg;
      if (sort === 'rvol') return b.rvol - a.rvol;
      return a.rank - b.rank;
    });
    return r;
  }, [tab, sort, q, rows]);

  return (
    <div className="watchlist">
      <div className="wl-head">
        <div className="wl-tabs">
          {[
            ['all','ALL · 22'],
            ['ready','READY · 5'],
            ['trade','IN TRADE · 3'],
            ['watch','WATCH · 8'],
            ['cooling','COOLING · 6']
          ].map(([k, l]) => (
            <button key={k} className={`wl-tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
        <div className="wl-filters">
          <input className="wl-search" placeholder="/  search ticker, name…" value={q} onChange={e => setQ(e.target.value)} />
          <button className="chip">⛚ FILTERS</button>
          <button className="chip">⊟ EXPORT</button>
        </div>
      </div>
      <div style={{ overflow:'auto', maxHeight: '52vh' }}>
        <table className="wl">
          <thead>
            <tr>
              <th onClick={() => setSort('rank')} className={sort==='rank'?'sorted':''}>#</th>
              <th>SYM</th>
              <th>SECT</th>
              <th>SETUP</th>
              <th onClick={() => setSort('bap')} style={{textAlign:'right'}} className={sort==='bap'?'sorted':''}>BAP</th>
              <th>STAGE</th>
              <th style={{textAlign:'right'}}>PRICE</th>
              <th onClick={() => setSort('chg')} style={{textAlign:'right'}} className={sort==='chg'?'sorted':''}>%</th>
              <th style={{textAlign:'right'}}>D5</th>
              <th style={{textAlign:'right'}}>D20</th>
              <th onClick={() => setSort('rvol')} style={{textAlign:'right'}} className={sort==='rvol'?'sorted':''}>RVOL</th>
              {showSparklines && <th>1M</th>}
              {showRulers && <th>RULER</th>}
              <th style={{textAlign:'right'}}>R:R</th>
              <th style={{textAlign:'right'}}>EARN</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => {
              const pts = genSpark(r.rank * 7 + 13, 30, r.chg > 0 ? 0.3 : r.chg < -1 ? -0.4 : 0);
              const sparkCol = r.d20 >= 0 ? 'var(--green)' : 'var(--red)';
              const bapCol = r.bap >= 75 ? 'var(--green)' : r.bap >= 55 ? 'var(--accent)' : 'var(--red)';
              const stageCol = { 'READY':'amber','IN TRADE':'green','WATCH':'blue','COOLING':'red' }[r.stage];
              const rr = ((r.t1 - r.entry[0]) / (r.entry[0] - r.stop));
              return (
                <tr key={r.sym} className={activeSym === r.sym ? 'active' : ''} onClick={() => onOpen(r)}>
                  <td className="dim2">{r.rank}</td>
                  <td><span className="wl-sym">{r.sym}</span></td>
                  <td className="wl-sect">{r.sect}</td>
                  <td style={{color:'var(--ink-1)'}}>{r.setup}</td>
                  <td style={{textAlign:'right'}}>
                    <span className="wl-bap" style={{color:bapCol}}>{r.bap}</span>
                    <span className="bap-bar"><span className="bap-bar-fill" style={{width:`${r.bap}%`,background:bapCol}} /></span>
                  </td>
                  <td><span className={`tag ${stageCol}`}>{r.stage}</span></td>
                  <td style={{textAlign:'right'}}>${r.px < 100 ? r.px.toFixed(2) : r.px.toLocaleString(undefined,{maximumFractionDigits:2})}</td>
                  <td style={{textAlign:'right'}} className={r.chg >= 0 ? 'up' : 'down'}>{r.chg >= 0 ? '+' : ''}{r.chg.toFixed(2)}</td>
                  <td style={{textAlign:'right'}} className={r.d5 >= 0 ? 'up' : 'down'}>{r.d5 >= 0 ? '+' : ''}{r.d5.toFixed(1)}</td>
                  <td style={{textAlign:'right'}} className={r.d20 >= 0 ? 'up' : 'down'}>{r.d20 >= 0 ? '+' : ''}{r.d20.toFixed(1)}</td>
                  <td style={{textAlign:'right'}}>{r.rvol.toFixed(1)}×</td>
                  {showSparklines && <td className="spark-cell"><Sparkline pts={pts} w={80} h={20} color={sparkCol} fill /></td>}
                  {showRulers && <td><MiniRuler lo={r.lo} hi={r.hi} stop={r.stop} entry={r.entry} t1={r.t1} t2={r.t2} px={r.px} /></td>}
                  <td style={{textAlign:'right',color: rr>=2.5 ? 'var(--green)' : rr>=1.5 ? 'var(--accent)' : 'var(--red)'}}>1:{rr.toFixed(1)}</td>
                  <td style={{textAlign:'right'}} className="dim">{r.earn != null ? `+${r.earn}d` : '—'}</td>
                  <td>{r.news === 'up' ? <span className="up">▲</span> : r.news === 'dn' ? <span className="down">▼</span> : <span className="dim2">·</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Detail overlay ─── */
function Detail({ row, onClose }) {
  const [tab, setTab] = useState('overview');
  const candles = useMemo(
    () => row ? genCandles(120, row.rank * 11, row.px) : [],
    [row?.sym]
  );
  if (!row) return null;
  const rr1 = ((row.t1 - row.entry[0]) / (row.entry[0] - row.stop));
  const rr2 = ((row.t2 - row.entry[0]) / (row.entry[0] - row.stop));

  /* Ladder scale: stop at bottom, t2 at top */
  const ladderTop = row.t2 * 1.04, ladderBot = row.stop * 0.94;
  const lspan = ladderTop - ladderBot;
  const lY = v => ((ladderTop - v) / lspan) * 100;

  return (
    <div className={`detail ${row ? 'open' : ''}`}>
      <div className="detail-head">
        <button className="detail-back" onClick={onClose}>← BACK · ESC</button>
        <div>
          <div className="detail-sym">{row.sym}</div>
          <div className="detail-name">{row.name} · {row.sect} · MCAP {row.cap}</div>
        </div>
        <div />
        <div className="detail-price">
          <div className="num" style={{fontSize:24, fontWeight:600}}>${row.px.toFixed(2)}</div>
          <div className={`num ${row.chg >= 0 ? 'up' : 'down'}`} style={{fontSize:12}}>{row.chg >= 0 ? '+' : ''}{row.chg.toFixed(2)}% · +${(row.px*row.chg/100).toFixed(2)}</div>
        </div>
        <div style={{display:'flex',gap:8}}>
          <span className={`tag ${row.stage === 'READY' ? 'amber' : row.stage === 'IN TRADE' ? 'green' : row.stage === 'COOLING' ? 'red' : 'blue'}`}>{row.stage}</span>
          <button className="chip accent">＋ ADD ALERT</button>
        </div>
      </div>
      <div className="detail-tabs">
        {[['overview','OVERVIEW'],['chart','CHART+'],['fund','FUND+'],['smc','SMC'],['intel','INTEL'],['plan','PLAN']].map(([k,l]) => (
          <button key={k} className={`detail-tab ${tab===k?'on':''}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div className="detail-body">
        {tab === 'overview' && (
          <div style={{display:'grid', gridTemplateColumns:'1.6fr 1fr', gap:14}}>
            <div className="panel">
              <div className="panel-head"><span className="panel-title">Price · 6mo</span><span className="panel-meta">D · CDL · MA20/50/200</span></div>
              <div className="panel-body" style={{padding:0, height:340}}>
                <HeroChart candles={candles} levels={{ stop: row.stop, entry: row.entry, t1: row.t1, t2: row.t2 }} />
              </div>
              <div style={{padding:'10px 14px', borderTop:'1px solid var(--rule)'}}>
                <BigRuler lo={row.lo} hi={row.hi} stop={row.stop} entry={row.entry} t1={row.t1} t2={row.t2} px={row.px} />
              </div>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:14}}>
              <div className="panel">
                <div className="panel-head"><span className="panel-title">Composite Scores</span><span className="panel-meta">BAP {row.bap}/100</span></div>
                <div className="panel-body" style={{display:'flex',justifyContent:'space-around',padding:'14px 8px'}}>
                  <Gauge val={row.bap} label="BAP" />
                  <Gauge val={row.tech} label="TECH" />
                  <Gauge val={row.fund} label="FUND" />
                  <Gauge val={row.smc} label="SMC" />
                  <Gauge val={row.intel} label="INTEL" />
                </div>
              </div>
              <div className="panel">
                <div className="panel-head"><span className="panel-title">Trade Plan</span><span className="panel-meta">R:R 1:{rr1.toFixed(1)} / 1:{rr2.toFixed(1)}</span></div>
                <div className="panel-body" style={{padding:'10px 14px'}}>
                  <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,fontSize:12,fontFamily:'JetBrains Mono'}}>
                    <div><div className="lbl">SETUP</div>{row.setup}</div>
                    <div><div className="lbl">EARN</div>{row.earn != null ? `+${row.earn}d` : 'none scheduled'}</div>
                    <div><div className="lbl">ENTRY</div><span className="up">${row.entry[0]} – ${row.entry[1]}</span></div>
                    <div><div className="lbl">STOP</div><span className="down">${row.stop.toFixed(2)} (-{((row.entry[0]-row.stop)/row.entry[0]*100).toFixed(1)}%)</span></div>
                    <div><div className="lbl">T1 · 50%</div><span style={{color:'var(--accent)'}}>${row.t1.toFixed(2)}</span></div>
                    <div><div className="lbl">T2 · 30%</div><span style={{color:'var(--accent-2)'}}>${row.t2.toFixed(2)}</span></div>
                    <div><div className="lbl">SIZE</div>142 sh · $26,8k</div>
                    <div><div className="lbl">RISK</div><span className="down">$1,000 · 0.5%</span></div>
                  </div>
                </div>
              </div>
              <div className="panel">
                <div className="panel-head"><span className="panel-title">Intel · {INTEL.filter(i=>i.sym===row.sym).length} for {row.sym}</span></div>
                <div className="panel-body" style={{padding:'4px 14px'}}>
                  <IntelFeed rows={INTEL.filter(i=>i.sym===row.sym).concat(INTEL.filter(i=>i.sym!==row.sym).slice(0,3))} max={5} />
                </div>
              </div>
            </div>
          </div>
        )}
        {tab === 'chart' && (
          <div className="panel">
            <div className="panel-head"><span className="panel-title">Chart+ · Multi-timeframe</span><span className="panel-meta">D · W · 4H</span></div>
            <div className="panel-body" style={{padding:0, height: 540}}>
              <HeroChart candles={candles} levels={{ stop: row.stop, entry: row.entry, t1: row.t1, t2: row.t2 }} />
            </div>
          </div>
        )}
        {tab === 'fund' && (
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
            <div className="panel">
              <div className="panel-head"><span className="panel-title">Fund Pillars · {row.fund}/100</span></div>
              <div className="panel-body">
                {PILLARS.FUND.map(p => {
                  const pct = (p.pts/p.max)*100;
                  const c = pct>=80?'var(--green)':pct>=55?'var(--accent)':'var(--red)';
                  return (
                    <div key={p.name} className="pillar">
                      <span className="pillar-name">{p.name}</span>
                      <span className="pillar-val num">{p.val}</span>
                      <div className="pillar-bar"><div className="pillar-fill" style={{width:`${pct}%`,background:c}} /></div>
                      <span className="pillar-pts">{p.pts}/{p.max}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="panel">
              <div className="panel-head"><span className="panel-title">Tech Pillars · {row.tech}/100</span></div>
              <div className="panel-body">
                {PILLARS.TECH.map(p => {
                  const pct = (p.pts/p.max)*100;
                  const c = pct>=80?'var(--green)':pct>=55?'var(--accent)':'var(--red)';
                  return (
                    <div key={p.name} className="pillar">
                      <span className="pillar-name">{p.name}</span>
                      <span className="pillar-val num">{p.val}</span>
                      <div className="pillar-bar"><div className="pillar-fill" style={{width:`${pct}%`,background:c}} /></div>
                      <span className="pillar-pts">{p.pts}/{p.max}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
        {tab === 'smc' && (
          <div className="panel">
            <div className="panel-head"><span className="panel-title">Smart Money Concepts</span><span className="panel-meta">SMC {row.smc}/100</span></div>
            <div className="panel-body">
              {PILLARS.SMC.map(p => {
                const pct = (p.pts/p.max)*100;
                const c = pct>=80?'var(--green)':pct>=55?'var(--accent)':'var(--red)';
                return (
                  <div key={p.name} className="pillar">
                    <span className="pillar-name">{p.name}</span>
                    <span className="pillar-val num">{p.val}</span>
                    <div className="pillar-bar"><div className="pillar-fill" style={{width:`${pct}%`,background:c}} /></div>
                    <span className="pillar-pts">{p.pts}/{p.max}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {tab === 'intel' && (
          <div className="panel">
            <div className="panel-head"><span className="panel-title">Intel feed · all sources</span></div>
            <div className="panel-body"><IntelFeed rows={INTEL} max={20} /></div>
          </div>
        )}
        {tab === 'plan' && (
          <div style={{display:'grid', gridTemplateColumns:'400px 1fr', gap:14}}>
            <div className="panel">
              <div className="panel-head"><span className="panel-title">Trade Ladder</span><span className="panel-meta">{row.sym}</span></div>
              <div className="panel-body" style={{padding:'18px 18px 22px'}}>
                <div className="ladder">
                  <div className="ladder-zone buy" style={{ top: `${lY(row.entry[1])}%`, height: `${lY(row.entry[0]) - lY(row.entry[1])}%` }}>
                    <span className="ladder-zone-lbl up">BUY ZONE</span>
                  </div>
                  <div className="ladder-zone nogo" style={{ top: `${lY(row.stop)}%`, height: `${100 - lY(row.stop)}%` }}>
                    <span className="ladder-zone-lbl down">NO-GO</span>
                  </div>
                  {[
                    { v: row.t2,       lbl: 'T2 · TARGET',   pct: ((row.t2-row.entry[0])/row.entry[0]*100).toFixed(1)+'%', col: 'var(--accent-2)' },
                    { v: row.t1,       lbl: 'T1 · TARGET',   pct: ((row.t1-row.entry[0])/row.entry[0]*100).toFixed(1)+'%', col: 'var(--accent)'   },
                    { v: row.entry[1], lbl: 'ENTRY HIGH',     pct: '0.0%', col: 'var(--green)', dashed: true },
                    { v: row.entry[0], lbl: 'ENTRY LOW',      pct: ((row.entry[0]-row.entry[1])/row.entry[1]*100).toFixed(1)+'%', col: 'var(--green)', dashed: true },
                    { v: row.stop,     lbl: 'STOP',           pct: ((row.stop-row.entry[0])/row.entry[0]*100).toFixed(1)+'%', col: 'var(--red)' },
                  ].map((rg, i) => (
                    <div key={i} className="ladder-rung" style={{ top: `${lY(rg.v)}%` }}>
                      <span className="ladder-px" style={{color: rg.col}}>${rg.v < 100 ? rg.v.toFixed(2) : rg.v.toFixed(0)}</span>
                      <div className={`ladder-line ${rg.dashed?'dashed':''}`} style={{borderColor: rg.col}} />
                      <span className="ladder-tag">{rg.lbl}</span>
                      <span className="ladder-pct" style={{color: rg.col}}>{rg.pct}</span>
                    </div>
                  ))}
                  <div className="ladder-now" style={{ top: `${lY(row.px)}%` }}>
                    <span className="ladder-now-tag">NOW · ${row.px.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:14}}>
              <div className="panel">
                <div className="panel-head"><span className="panel-title">Sizing</span><span className="panel-meta">Account $200,000</span></div>
                <div className="panel-body">
                  <div style={{display:'grid',gridTemplateColumns:'auto 1fr',gap:'8px 18px',fontFamily:'JetBrains Mono',fontSize:12}}>
                    <div className="lbl">RISK / TRADE</div><div>0.5% = <span className="num down">$1,000</span></div>
                    <div className="lbl">RISK / SHARE</div><div className="num">${(row.entry[0] - row.stop).toFixed(2)} (entry → stop)</div>
                    <div className="lbl">POSITION</div><div className="num" style={{fontWeight:700,color:'var(--accent)'}}>{Math.floor(1000/(row.entry[0]-row.stop))} shares</div>
                    <div className="lbl">NOTIONAL</div><div className="num">${(Math.floor(1000/(row.entry[0]-row.stop)) * row.entry[0]).toLocaleString()}</div>
                    <div className="lbl">% OF ACCT</div><div className="num">{((Math.floor(1000/(row.entry[0]-row.stop)) * row.entry[0]) / 200000 * 100).toFixed(1)}%</div>
                    <div className="lbl">R:R</div><div className="num">1:{rr1.toFixed(1)} (T1) · 1:{rr2.toFixed(1)} (T2)</div>
                  </div>
                </div>
              </div>
              <div className="panel">
                <div className="panel-head"><span className="panel-title">Exit Rules</span></div>
                <div className="panel-body" style={{fontSize:12.5,lineHeight:1.7,color:'var(--ink-1)'}}>
                  <div>1. <b>Hard stop</b> on D1 close below <span className="num down">${row.stop.toFixed(2)}</span></div>
                  <div>2. <b>T1</b> · sell <span className="num">50%</span> at <span className="num" style={{color:'var(--accent)'}}>${row.t1.toFixed(2)}</span> · trail rest to entry</div>
                  <div>3. <b>T2</b> · sell <span className="num">30%</span> at <span className="num" style={{color:'var(--accent-2)'}}>${row.t2.toFixed(2)}</span> · trail 20MA</div>
                  <div>4. <b>Time stop</b> · exit if no progress in 6 weeks</div>
                  {row.earn != null && <div className="down">5. <b>Earnings</b> in {row.earn}d — consider scaling at T1 first</div>}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Tweaks panel ─── */
function Tweaks({ tweaks, setTweak }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection title="Theme">
        <TweakRadio value={tweaks.theme} onChange={v => setTweak('theme', v)} options={[['dark','Dark'],['light','Light']]} />
      </TweakSection>
      <TweakSection title="Density">
        <TweakRadio value={tweaks.density} onChange={v => setTweak('density', v)} options={[['compact','Compact'],['normal','Normal'],['comfortable','Comfortable']]} />
      </TweakSection>
      <TweakSection title="Accent">
        <TweakRadio value={tweaks.accent} onChange={v => setTweak('accent', v)} options={[['amber','Amber'],['cyan','Cyan'],['violet','Violet'],['green','Green']]} />
      </TweakSection>
      <TweakSection title="Display">
        <TweakToggle label="Sparklines" value={tweaks.showSparklines} onChange={v => setTweak('showSparklines', v)} />
        <TweakToggle label="Price rulers" value={tweaks.showRulers} onChange={v => setTweak('showRulers', v)} />
        <TweakToggle label="Score gauges" value={tweaks.showGauges} onChange={v => setTweak('showGauges', v)} />
      </TweakSection>
    </TweaksPanel>
  );
}

/* ─── App ─── */
function App() {
  const [tweaks, setTweak] = useTweaks(DEFAULTS);
  const [view, setView] = useState('dash');
  const [active, setActive] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-density', tweaks.density);
    document.documentElement.style.setProperty('--accent', ACCENT_MAP[tweaks.accent] || ACCENT_MAP.amber);
  }, [tweaks.theme, tweaks.density, tweaks.accent]);

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') setActive(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const hero = WATCHLIST[0];

  return (
    <div>
      <TopBar />
      <MacroStrip />
      <div className="shell">
        <Rail view={view} setView={setView} />
        <main>
          <div className="grid-top">
            <Hero row={hero} onOpen={setActive} />
            <div className="right-stack">
              <div className="panel">
                <div className="panel-head">
                  <span className="panel-title">Sector Heatmap</span>
                  <span className="panel-meta">11 sectors · 1D %</span>
                </div>
                <div className="panel-body np"><Heatmap onPick={() => {}} /></div>
              </div>
              <div className="panel" style={{flex:1}}>
                <div className="panel-head">
                  <span className="panel-title">Intel · Today</span>
                  <span className="panel-meta">{INTEL.length} items · live</span>
                </div>
                <div className="panel-body" style={{padding:'4px 14px', maxHeight: 280, overflow:'auto'}}>
                  <IntelFeed rows={INTEL} max={9} />
                </div>
              </div>
            </div>
          </div>

          <Watchlist
            rows={WATCHLIST}
            onOpen={setActive}
            activeSym={active?.sym}
            showSparklines={tweaks.showSparklines}
            showRulers={tweaks.showRulers}
          />
        </main>
      </div>
      <div className="statusbar">
        <span>● <span className="sb-ok">LIVE</span></span>
        <span>22 tickers · 5 ready · 3 in trade · $4.2k risk</span>
        <span style={{flex:1}} />
        <span><kbd>↑↓</kbd> walk</span>
        <span><kbd>/</kbd> search</span>
        <span><kbd>⌘K</kbd> command</span>
        <span><kbd>esc</kbd> close</span>
        <span className="sb-warn">Earnings season · Wk 2</span>
      </div>
      <Detail row={active} onClose={() => setActive(null)} />
      <Tweaks tweaks={tweaks} setTweak={setTweak} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
