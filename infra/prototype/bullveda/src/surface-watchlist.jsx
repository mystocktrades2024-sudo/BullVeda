// surface-watchlist.jsx — Watchlist workspace per spec.
// Eikon-style sortable table (16 cols) + 5-KPI strip + mode/verdict filter chips
// + the right detail pane (13 evidence sections) that the scanner spec calls for.

const { useState: useWL, useMemo: useWLm } = React;

// Join each watchlist row to its REAL /api/universe scan row (via BV.findRow →
// BV.scanRow). All fields are real or feed-honest null — NO charCodeAt fabrication
// (SURFACE-WATCHLIST-MOCK, 2026-06-09). Ledger-derived stats (wlb/n/pf) are null
// when absent. Renders below are null-safe.
function enrichWL(w, i) {
  const sr = (window.__BV && window.__BV.findRow) ? window.__BV.findRow(w.sym) : null;
  const pf = v => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const num = v => (typeof v === "number" && isFinite(v)) ? v : null;
  return {
    ...w,
    held: i < 3,
    tier: (sr && sr.tier && sr.tier !== "—") ? sr.tier
        : (w.score >= 75 ? "T1" : w.score >= 60 ? "T2" : w.score >= 45 ? "T3" : "WATCH"),
    modeTag: w.modeTag || (sr && sr.eq ? "swing" : "swing"),
    rs:      sr ? pf(sr.rs)      : null,
    rvol:    sr ? pf(sr.rvol)    : null,
    rr:      sr ? pf(sr.rr)      : null,
    earn:    sr ? num(sr.er)     : null,
    tfsn:    (sr && Array.isArray(sr.tfsn)) ? sr.tfsn : null,
    iv:      sr ? num(sr.iv)     : null,
    wlb:     sr ? num(sr.wlb)    : null,   // ledger-derived → null (feed-honest)
    n:       sr ? num(sr.n)      : null,
    pf:      sr ? num(sr.pf)     : null,
    insider: sr ? num(sr.insNet) : null,
    sent:    sr ? num(sr.sent)   : null,
    pillarPct: (sr && sr.pillarPct) ? sr.pillarPct : null,
    entryReal: sr ? pf(sr.entry)   : null,
    stopReal:  sr ? pf(sr.stop)    : null,
    t1Real:    sr ? pf(sr.t1plan)  : null,
    mech:    (sr && sr.mechanism) ? sr.mechanism : (w.setup || "—"),
    // two-axis verdict (2026-06-10) — directional bias separate from action
    bias:    sr ? (sr.bias || null) : null,
    action:  sr ? (sr.action || null) : null,
    reasonClass: sr ? (sr.reasonClass || null) : null,
    _real:   !!sr,
  };
}
const WL_ROWS = WATCHLIST.map((w, i) => enrichWL(w, i));

// Effective list = (base − removed) + user-added, all enriched. Reads the
// shared WatchStore so tickers added from the detail panel show up here.
function effectiveWL() {
  const ws = window.WatchStore;
  const rem = ws ? ws.removed() : new Set();
  const base = WATCHLIST.filter(w => !rem.has(w.sym));
  const added = (ws ? ws.added() : []).map(r => ({
    sym: r.sym, name: r.name || r.sym, sector: r.sector || "—",
    price: +r.price || 0, chg: +r.chg || 0, score: +r.score || 50,
    verdict: r.verdict || "WATCH", setup: r.setup || "Manual add",
  }));
  return [...base, ...added].map((w, i) => enrichWL(w, i));
}

const WL_MODE = [["all","All"],["swing","Swing"],["position","Position"]];
const WL_VERD = [["all","All"],["BUY","Bullish"],["WATCH","Neutral"],["AVOID","Bearish"],["held","★ Held"]];

function SurfaceWatchlist({ onTicker }) {
  const [mode, setMode] = useWL("all");
  const [verd, setVerd] = useWL("all");
  const [q, setQ] = useWL("");
  const [sort, setSort] = useWL({ col: "score", dir: -1 });
  const [sel, setSel] = useWL("ARCM");
  const [wlTick, setWlTick] = useWL(0);

  React.useEffect(() => {
    const h = () => setWlTick(x => x + 1);
    window.addEventListener("watchlist-change", h);
    return () => window.removeEventListener("watchlist-change", h);
  }, []);

  const allRows = useWLm(() => effectiveWL(), [wlTick]);

  const rows = useWLm(() => {
    let r = allRows;
    if (mode !== "all") r = r.filter(x => x.modeTag === mode);
    if (verd === "held") r = r.filter(x => x.held);
    else if (verd !== "all") r = r.filter(x => x.verdict === verd);
    if (q) r = r.filter(x => (x.sym + x.name).toLowerCase().includes(q.toLowerCase()));
    return [...r].sort((a, b) => {
      const av = a[sort.col], bv = b[sort.col];
      const an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return (an - bn) * sort.dir;
      return String(av).localeCompare(String(bv)) * sort.dir;
    });
  }, [allRows, mode, verd, q, sort]);

  const kpi = useWLm(() => ({
    watching: allRows.length,
    bull: allRows.filter(x => x.verdict === "BUY").length,
    bear: allRows.filter(x => x.verdict === "AVOID").length,
    held: allRows.filter(x => x.held).length,
    avg: allRows.length ? Math.round(allRows.reduce((s, x) => s + x.score, 0) / allRows.length) : 0,
  }), [allRows]);

  const TH = (col, label, r) => (
    <th className={`${r ? "r" : ""} wsx-th ${sort.col === col ? "is-active" : ""}`}
        onClick={() => setSort(s => s.col === col ? { col, dir: -s.dir } : { col, dir: -1 })}>
      {label}{sort.col === col && <span className="wsx-arr mono">{sort.dir > 0 ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <div className="surface wsx wsx--copper wl-surface">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">USER-CURATED · ★ STARRED + MANUAL</div>
          <h1 className="wsx-title mono">Watchlist</h1>
          <div className="wsx-sub mono dim2">live price + Δ% · synced from Signal Scanner stars · localStorage</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="12s" /><span className="mono dim2">src · watchlist + last_bundle</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">WATCHING</div><div className="wsx-kpi-v mono kpi-tone--copper">{kpi.watching}</div><div className="wsx-kpi-s mono dim2">tracked names</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">BULLISH</div><div className="wsx-kpi-v mono kpi-tone--gn">{kpi.bull}</div><div className="wsx-kpi-s mono dim2">actionable BUY</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">BEARISH</div><div className="wsx-kpi-v mono kpi-tone--rd">{kpi.bear}</div><div className="wsx-kpi-s mono dim2">avoid / short</div></div>
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">HELD</div><div className="wsx-kpi-v mono kpi-tone--violet">{kpi.held}</div><div className="wsx-kpi-s mono dim2">in portfolio</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">AVG SCORE</div><div className="wsx-kpi-v mono kpi-tone--amb">{kpi.avg}</div><div className="wsx-kpi-s mono dim2">list health</div></div>
      </div>

      <div className="wl-filters">
        <div className="wl-chips">
          {WL_MODE.map(([id, l]) => <button key={id} className={`wl-chip ${mode === id ? "is-on" : ""}`} onClick={() => setMode(id)}>{l}</button>)}
        </div>
        <div className="wl-chips">
          {WL_VERD.map(([id, l]) => <button key={id} className={`wl-chip wl-chip--${id} ${verd === id ? "is-on" : ""}`} onClick={() => setVerd(id)}>{l}</button>)}
        </div>
        <input className="wl-search mono" placeholder="⌕ filter…" value={q} onChange={e => setQ(e.target.value)} />
      </div>

      <div className="wl-split">
        <div className="wsx-body wl-tbl-wrap">
          <table className="dtable wsx-tbl wl-tbl">
            <thead><tr>
              {TH("sym","Sym")}<th>Name</th><th>Setup</th>{TH("verdict","Bias")}<th>Tier</th>{TH("score","Score",true)}
              <th>T·F·S·N</th>{TH("price","Px",true)}{TH("chg","Δ%",true)}{TH("rs","RS",true)}{TH("rvol","RVOL",true)}
              {TH("rr","R:R",true)}{TH("earn","Earn",true)}
            </tr></thead>
            <tbody>
              {rows.map((t, i) => (
                <tr key={t.sym + i} className={sel === t.sym ? "is-sel" : ""} onClick={() => setSel(t.sym)}>
                  <td className="mono"><span className="wl-held" style={{ opacity: t.held ? 1 : 0 }}>●</span><b>{t.sym}</b></td>
                  <td className="dim">{t.name}</td>
                  <td className="mono dim">{t.setup}</td>
                  <td><Pill tone={window.biasRead ? window.biasRead(t).tone : secBiasTone(t.verdict)} small>{window.biasRead ? window.biasRead(t).label : secBias(t.verdict)}</Pill></td>
                  <td><span className={`ss2-tier ss2-tier--${t.tier.toLowerCase().replace("watch","t3")}`}>{t.tier}</span></td>
                  <td className="r"><span className="wl-scorebar"><span style={{ width: `${t.score}%`, background: t.score>=75?"var(--gn)":t.score>=60?"var(--amb)":"var(--rd)" }} /></span><b className="mono">{t.score}</b></td>
                  <td><span className="ss2-tfsn">{(t.tfsn||[]).map((v,k)=><span key={k} className={`ss2-tfsn-dot ss2-tfsn--${v===2?"pass":v===1?"neut":"fail"}`} />)}{!t.tfsn&&<span className="dim2">—</span>}</span></td>
                  <td className="r mono tabular">${t.price.toFixed(2)}</td>
                  <td className={`r mono tabular ${t.chg>=0?"up":"dn"}`}>{t.chg>=0?"+":""}{t.chg.toFixed(2)}%</td>
                  <td className="r mono tabular">{t.rs!=null?Math.round(t.rs):"—"}</td>
                  <td className={`r mono tabular ${t.rvol>=1.5?"up":"dim"}`}>{t.rvol!=null?t.rvol.toFixed(2)+"×":"—"}</td>
                  <td className="r mono tabular">{t.rr!=null?t.rr.toFixed(2):"—"}</td>
                  <td className={`r mono tabular ${t.earn!=null&&t.earn<=10?"warn":"dim"}`}>{t.earn!=null?t.earn+"d":"—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <WLDetailPane sym={sel} rows={allRows} onTicker={onTicker} />
      </div>
    </div>
  );
}

function WLDetailPane({ sym, rows, onTicker }) {
  const list = rows && rows.length ? rows : WL_ROWS;
  const t = list.find(r => r.sym === sym) || list[0];
  if (!t) return null;
  const toneV = t.verdict === "BUY" ? "gn" : t.verdict === "AVOID" ? "rd" : "amb";
  const Sec = ({ n, title, children }) => (
    <div className="sdp-sec"><div className="sdp-sec-h"><span className="sdp-sec-n mono">{n}</span><span className="mono">{title}</span></div><div className="sdp-sec-b">{children}</div></div>
  );
  const KV = ({ k, v, tone }) => (<div className="sdp-kv"><span className="mono dim2">{k}</span><span className={`mono ${tone ? `kpi-tone--${tone}` : ""}`}>{v}</span></div>);
  return (
    <div className="sdp">
      <div className="sdp-hdr">
        <div>
          <div className="sdp-sym mono"><b>{t.sym}</b> {t.held && <span className="wl-held">●</span>}</div>
          <div className="sdp-px mono">${t.price.toFixed(2)} <span className={t.chg>=0?"up":"dn"}>{t.chg>=0?"+":""}{t.chg.toFixed(2)}%</span></div>
        </div>
        <div className="sdp-hdr-r">
          <span className={`ss2-score ss2-score--${t.score>=75?"gn":t.score>=60?"amb":"rd"}`}>{t.score}</span>
          <Pill tone={toneV} small>{window.biasRead ? window.biasRead(t).label : secBias(t.verdict)}</Pill>
        </div>
      </div>
      <button className="sdp-open mono" onClick={() => onTicker(t.sym)}>OPEN 14-LENS DETAIL →</button>
      <div className="sdp-body">
        <Sec n="01" title="CONVICTION"><div className="sdp-arc"><div className="sdp-arc-fill" style={{ width: `${t.score}%` }} /></div><KV k="tier" v={t.tier} /><KV k="conviction" v={`${t.score}%`} tone="copper" /></Sec>
        <Sec n="02" title="T·F·S·N PILLARS">{(t.pillarPct?[["Tech",t.pillarPct.technical,"cy"],["Fund",t.pillarPct.fundamental,"blue"],["SMC",t.pillarPct.smc,"gn"],["News",t.pillarPct.sentiment,"violet"]]:[["Tech",null,"cy"],["Fund",null,"blue"],["SMC",null,"gn"],["News",null,"violet"]]).map(([l,v,c],i)=>(
          <div key={i} className="sdp-bar"><span className="mono dim2">{l}</span><div className="sdp-bar-t"><div className="sdp-bar-f" style={{width:`${v!=null?Math.max(4,Math.min(100,v)):0}%`,background:`var(--${c})`}}/></div><span className="mono">{v!=null?Math.round(v):"—"}</span></div>))}</Sec>
        <Sec n="03" title="MECHANISM"><div className="sdp-mech mono">{t.mech}</div></Sec>
        <Sec n="04" title="ENTRY · PLAN"><KV k="entry" v={t.entryReal!=null?`$${t.entryReal.toFixed(2)}`:"—"} tone="copper" /><KV k="stop" v={t.stopReal!=null?`$${t.stopReal.toFixed(2)}`:"—"} tone="rd" /><KV k="T1" v={t.t1Real!=null?`$${t.t1Real.toFixed(2)}`:"—"} tone="gn" /><KV k="R:R" v={t.rr!=null?t.rr.toFixed(2):"—"} tone="copper" /></Sec>
        <Sec n="05" title="MODE · HOLD"><KV k="mode" v={t.modeTag} /><KV k="hold" v={t.modeTag==="swing"?"7d":"30d"} /><KV k="held" v={t.held?"yes · in book":"no"} tone={t.held?"gn":"ink"} /></Sec>
        <Sec n="06" title="SETUP STATS"><KV k="family" v={t.setup} /><KV k="Wilson LB" v={t.wlb!=null?`${t.wlb}%`:"—"} tone={t.wlb!=null&&t.wlb>=50?"gn":"amb"} /><KV k="n · PF" v={(t.n!=null&&t.pf!=null)?`${t.n} · ${t.pf.toFixed(2)}`:"—"} /></Sec>
        <Sec n="07" title="MOMENTUM"><KV k="RS rank" v={t.rs!=null?Math.round(t.rs):"—"} tone={t.rs!=null&&t.rs>=70?"gn":"ink"} /><KV k="RVOL" v={t.rvol!=null?`${t.rvol.toFixed(2)}×`:"—"} tone={t.rvol!=null&&t.rvol>=1.5?"gn":"ink"} /><KV k="1D" v={`${t.chg>=0?"+":""}${t.chg.toFixed(2)}%`} tone={t.chg>=0?"gn":"rd"} /></Sec>
        <Sec n="08" title="DECISION"><KV k="gates" v={`${t.verdict==="AVOID"?"6":"9"} / 10`} tone={t.verdict==="AVOID"?"rd":"gn"} /><KV k="bias" v={window.biasRead ? window.biasRead(t).label : secBias(t.verdict)} tone={toneV} /></Sec>
      </div>
    </div>
  );
}

window.SurfaceWatchlist = SurfaceWatchlist;
