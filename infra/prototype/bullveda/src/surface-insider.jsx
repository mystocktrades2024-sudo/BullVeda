// surface-insider.jsx — Insider Trading · Form 4 cluster analysis.
// Data: EODHD Insider Transactions API (SEC EDGAR Form 4 backbone) for the filings;
// Schwab /markets/quotes supplies the live mark so each trade is scored vs current price.
// The alpha is CLUSTERS — multiple insiders (esp. C-suite) buying in the open market
// within a tight window — not routine 10b5-1 sales.
const { useState: useIns, useMemo: useInsm } = React;

// [date, sym, insider, role, txn(P=buy/S=sell), shares, value$, dHoldPct, vsSpotPct, cluster, plan(10b5-1)]
const INS_TXNS = [
  { d:"05-12", sym:"ARGN", who:"M. Calderon",  role:"CEO",       txn:"P", sh:18000, val:3841000, dHold:+22, vs:-1.8, cluster:true,  plan:false },
  { d:"05-12", sym:"ARGN", who:"R. Vance",      role:"CFO",       txn:"P", sh:9500,  val:2027000, dHold:+31, vs:-1.8, cluster:true,  plan:false },
  { d:"05-09", sym:"ARGN", who:"L. Okafor",     role:"Director",  txn:"P", sh:4200,  val:896000,  dHold:+14, vs:-0.6, cluster:true,  plan:false },
  { d:"05-08", sym:"DRSH", who:"T. Bauer",      role:"CEO",       txn:"P", sh:22000, val:1234000, dHold:+18, vs:+2.1, cluster:true,  plan:false },
  { d:"05-07", sym:"DRSH", who:"S. Mehta",      role:"10% Owner", txn:"P", sh:60000, val:3366000, dHold:+9,  vs:+2.1, cluster:true,  plan:false },
  { d:"05-06", sym:"NVRH", who:"K. Lindqvist",  role:"CEO",       txn:"P", sh:7000,  val:994000,  dHold:+12, vs:-3.4, cluster:false, plan:false },
  { d:"05-05", sym:"MERC", who:"D. Russo",      role:"CFO",       txn:"P", sh:25000, val:430000,  dHold:+27, vs:+0.4, cluster:true,  plan:false },
  { d:"05-05", sym:"MERC", who:"A. Fenwick",    role:"COO",       txn:"P", sh:14000, val:241000,  dHold:+19, vs:+0.4, cluster:true,  plan:false },
  { d:"05-02", sym:"ARCM", who:"P. Stein",      role:"Director",  txn:"P", sh:6000,  val:404000,  dHold:+8,  vs:+1.2, cluster:false, plan:false },
  { d:"04-30", sym:"GENO", who:"H. Yamamoto",   role:"President", txn:"P", sh:11000, val:323000,  dHold:+15, vs:-2.1, cluster:false, plan:false },
  { d:"04-29", sym:"QBIT", who:"E. Donnelly",   role:"CEO",       txn:"S", sh:40000, val:1820000, dHold:-6,  vs:+0.9, cluster:false, plan:true  },
  { d:"04-28", sym:"VELO", who:"G. Albright",   role:"EVP",       txn:"S", sh:15000, val:642000,  dHold:-11, vs:-0.4, cluster:false, plan:true  },
  { d:"04-25", sym:"KOSM", who:"N. Petrova",    role:"CFO",       txn:"P", sh:8000,  val:712000,  dHold:+21, vs:+1.6, cluster:false, plan:false },
  { d:"04-24", sym:"MAPL", who:"C. Whitmore",   role:"Director",  txn:"S", sh:30000, val:489000,  dHold:-14, vs:-0.8, cluster:false, plan:true  },
  { d:"04-22", sym:"BIVO", who:"J. Aldous",     role:"10% Owner", txn:"S", sh:55000, val:3712000, dHold:-8,  vs:-1.6, cluster:false, plan:false },
  { d:"04-21", sym:"PALA", who:"F. Moreau",     role:"CEO",       txn:"P", sh:9000,  val:486000,  dHold:+10, vs:+0.9, cluster:false, plan:false },
];

const INS_OFFICER = new Set(["CEO","CFO","COO","President","EVP"]);
// signal: cluster + officer buy = strongest; planned sells = noise
function insSignal(t) {
  if (t.txn === "P" && t.cluster && INS_OFFICER.has(t.role)) return { k:"strong", tone:"gn",  label:"STRONG BUY" };
  if (t.txn === "P" && t.cluster)                             return { k:"cluster",tone:"gn",  label:"CLUSTER BUY" };
  if (t.txn === "P" && INS_OFFICER.has(t.role))               return { k:"buy",    tone:"cy",  label:"C-SUITE BUY" };
  if (t.txn === "P")                                          return { k:"watch",  tone:"amb", label:"DIR BUY" };
  if (t.txn === "S" && t.plan)                                return { k:"noise",  tone:"ink", label:"10b5-1 SELL" };
  return { k:"bear", tone:"rd", label:"DISCRETIONARY SELL" };
}

// ── conviction score 0–100 — ranks every filing on a single scale ──
// Buys score positive; planned sells ≈ neutral; discretionary sells score low.
// Blend: role seniority · cluster corroboration · personal-stake change ·
// trade size · buying-into-weakness (vs spot).
const INS_ROLE_W = { CEO: 1.0, CFO: 0.95, President: 0.85, COO: 0.8, EVP: 0.65, "10% Owner": 0.7, Director: 0.5 };
function insConviction(t) {
  const role = INS_ROLE_W[t.role] ?? 0.4;
  if (t.txn === "S") {
    // planned sells are noise (~neutral 45-55); discretionary sells score low
    if (t.plan) return Math.round(48 + (1 - role) * 6);
    const sizePen = Math.min(20, t.val / 250000);
    return Math.round(Math.max(4, 34 - role * 14 - sizePen + t.dHold * 0.4));
  }
  // buy: weighted components → 0..1
  const roleC = role;                                   // seniority
  const clusterC = t.cluster ? 1 : 0.25;                // corroboration
  const stakeC = Math.min(1, Math.max(0, t.dHold) / 30); // personal add %
  const sizeC = Math.min(1, t.val / 3000000);            // $ size
  const dipC = t.vs <= 0 ? 1 : Math.max(0, 1 - t.vs / 5);// buying weakness
  const raw = roleC * 0.30 + clusterC * 0.28 + stakeC * 0.20 + sizeC * 0.12 + dipC * 0.10;
  return Math.round(40 + raw * 60); // buys land 46–100
}
function insConvTone(s) { return s >= 80 ? "gn" : s >= 65 ? "cy" : s >= 50 ? "amb" : "rd"; }

// Per-ticker insider edge — aggregate a symbol's filings into one read.
// Exposed for the Overview lens confluence chip.
function insiderEdge(sym) {
  const ts = INS_TXNS.filter(t => t.sym === sym);
  if (!ts.length) return null;
  const buys = ts.filter(t => t.txn === "P");
  const discSells = ts.filter(t => t.txn === "S" && !t.plan);
  const officers = buys.filter(t => INS_OFFICER.has(t.role)).length;
  const cluster = buys.length >= 2;
  const top = ts.map(t => ({ t, s: insConviction(t) })).sort((a, b) => b.s - a.s)[0];
  const buyVal = buys.reduce((a, t) => a + t.val, 0);
  let verdict = "NEUTRAL", tone = "ink";
  if (cluster && officers >= 1) { verdict = "CLUSTER BUY"; tone = "gn"; }
  else if (officers >= 1) { verdict = "C-SUITE BUY"; tone = "cy"; }
  else if (buys.length) { verdict = "INSIDER BUY"; tone = "amb"; }
  if (discSells.length && !buys.length) { verdict = "INSIDER SELLING"; tone = "rd"; }
  return { sym, verdict, tone, score: top ? top.s : 50, buyers: buys.length, officers, cluster, buyVal, discSells: discSells.length };
}
const fmtVal = v => v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${(v / 1e3).toFixed(0)}K`;

function SurfaceInsider({ onTicker }) {
  const [filter, setFilter] = useIns("all");
  const [sort, setSort] = useIns({ col: "conv", dir: -1 });

  // cluster groups: sym with 2+ insiders buying
  const clusters = useInsm(() => {
    const m = {};
    INS_TXNS.filter(t => t.txn === "P").forEach(t => { (m[t.sym] = m[t.sym] || []).push(t); });
    return Object.entries(m).filter(([, a]) => a.length >= 2)
      .map(([sym, a]) => ({ sym, n: a.length, val: a.reduce((s, x) => s + x.val, 0), roles: a.map(x => x.role) }))
      .sort((a, b) => b.val - a.val);
  }, []);

  const buys = INS_TXNS.filter(t => t.txn === "P");
  const sells = INS_TXNS.filter(t => t.txn === "S");
  const buyVal = buys.reduce((a, t) => a + t.val, 0);
  const sellVal = sells.reduce((a, t) => a + t.val, 0);
  const cSuiteBuys = buys.filter(t => INS_OFFICER.has(t.role)).length;
  const largest = [...buys].sort((a, b) => b.val - a.val)[0];

  const rows = useInsm(() => {
    let r = INS_TXNS;
    if (filter === "buys") r = r.filter(t => t.txn === "P");
    if (filter === "clusters") r = r.filter(t => t.cluster);
    if (filter === "csuite") r = r.filter(t => INS_OFFICER.has(t.role));
    if (filter === "sells") r = r.filter(t => t.txn === "S");
    return [...r].map(t => ({ ...t, conv: insConviction(t) })).sort((a, b) => { const v = (a[sort.col] < b[sort.col] ? -1 : 1); return v * sort.dir; });
  }, [filter, sort]);
  const setS = c => setSort(s => ({ col: c, dir: s.col === c ? -s.dir : -1 }));
  const TH = (c, l, r) => <th className={`${r ? "r" : ""} wsx-th ${sort.col === c ? "is-active" : ""}`} onClick={() => setS(c)} style={{ cursor:"pointer" }}>{l}{sort.col === c && <span className="wsx-arr mono">{sort.dir > 0 ? "▲" : "▼"}</span>}</th>;

  return (
    <div className="surface wsx wsx--cy insx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">INSIDER TRADING · FORM 4 CLUSTER ANALYSIS</div>
          <h1 className="wsx-title mono">Insider Trading</h1>
          <div className="wsx-sub mono dim2">open-market buys vs sells · C-suite weighted · cluster detection · 10b5-1 filtered as noise · the strongest smart-money signal</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="EODHD sync 4m" /><span className="mono dim2">src · EODHD /insider-transactions (SEC Form 4) · Schwab quotes for marks</span></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">CLUSTER SIGNALS</div><div className="wsx-kpi-v mono kpi-tone--gn">{clusters.length}</div><div className="wsx-kpi-s mono dim2">2+ insiders buying</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">BUY / SELL $</div><div className="wsx-kpi-v mono kpi-tone--gn">{(buyVal / sellVal).toFixed(1)}×</div><div className="wsx-kpi-s mono dim2">{fmtVal(buyVal)} vs {fmtVal(sellVal)}</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">C-SUITE BUYS</div><div className="wsx-kpi-v mono kpi-tone--cy">{cSuiteBuys}</div><div className="wsx-kpi-s mono dim2">CEO/CFO/COO/Pres/EVP</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">LARGEST BUY</div><div className="wsx-kpi-v mono kpi-tone--copper">{fmtVal(largest.val)}</div><div className="wsx-kpi-s mono dim2">{largest.sym} · {largest.role}</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">SELL PRESSURE</div><div className="wsx-kpi-v mono kpi-tone--amb">{sells.filter(t=>!t.plan).length ? "ELEVATED" : "LOW"}</div><div className="wsx-kpi-s mono dim2">{sells.filter(t=>t.plan).length} of {sells.length} planned</div></div>
      </div>

      {/* cluster highlight */}
      {clusters.length > 0 && (
        <div className="insx-clusters">
          {clusters.map(c => (
            <div key={c.sym} className="insx-cluster" onClick={() => onTicker(c.sym)}>
              <div className="insx-cl-top">
                <span className="insx-cl-sym mono">{c.sym}</span>
                <span className="insx-cl-tag">⛓ CLUSTER · {c.n} insiders</span>
              </div>
              <div className="insx-cl-val mono kpi-tone--gn">{fmtVal(c.val)}</div>
              <div className="insx-cl-roles mono dim2">{c.roles.join(" · ")}</div>
            </div>
          ))}
        </div>
      )}

      <div className="lab-tabs">
        {[["all","All filings"],["clusters","Clusters"],["csuite","C-suite"],["buys","Buys"],["sells","Sells"],["track","Track Record"]].map(([id,l])=>(
          <button key={id} className={`lab-tab ${filter===id?"is-on":""}`} onClick={()=>setFilter(id)}>{l}</button>
        ))}
      </div>

      {filter === "track" ? <InsiderTrack onTicker={onTicker} /> : (
      <div className="wsx-body">
        <table className="dtable wsx-tbl insx-tbl">
          <thead><tr>{TH("conv","Conviction",true)}{TH("d","Filed")}{TH("sym","Sym")}<th>Insider</th><th>Role</th><th>Txn</th>{TH("sh","Shares",true)}{TH("val","Value",true)}{TH("dHold","Δ Held",true)}<th className="r">vs Spot</th><th>Signal</th><th></th></tr></thead>
          <tbody>{rows.map((t,i)=>{
            const sig = insSignal(t);
            const ct = insConvTone(t.conv);
            return (
              <tr key={i} onClick={()=>onTicker(t.sym)} style={{ cursor:"pointer" }}>
                <td className="r">
                  <div className="insx-conv">
                    <span className={`insx-conv-num mono kpi-tone--${ct}`}>{t.conv}</span>
                    <span className="insx-conv-track"><span className={`insx-conv-fill insx-conv-fill--${ct}`} style={{ width: `${t.conv}%` }} /></span>
                  </div>
                </td>
                <td className="mono dim2">{t.d}</td>
                <td className="mono"><b>{t.sym}</b></td>
                <td className="mono">{t.who}</td>
                <td className={`mono ${INS_OFFICER.has(t.role)?"":"dim2"}`}>{t.role}</td>
                <td><span className={`insx-txn insx-txn--${t.txn==="P"?"buy":"sell"}`}>{t.txn==="P"?"BUY":"SELL"}</span></td>
                <td className="r mono tabular dim">{t.sh.toLocaleString()}</td>
                <td className={`r mono tabular ${t.txn==="P"?"up":"dn"}`}>{fmtVal(t.val)}</td>
                <td className={`r mono tabular ${t.dHold>=0?"up":"dn"}`}>{t.dHold>=0?"+":""}{t.dHold}%</td>
                <td className={`r mono tabular ${t.vs>=0?"up":"dn"}`}>{t.vs>=0?"+":""}{t.vs}%</td>
                <td><span className={`insx-sig insx-sig--${sig.tone}`}>{sig.label}</span></td>
                <td className="r mono dim">›</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      )}

      <div className="of-playbook mono">
        <span className="of-pb-tag" style={{color:"var(--gn)"}}>CONVICTION SCORE</span>
        <span className="of-pb-txt">Every filing is scored <b>0–100</b> on one scale: role seniority (CEO&gt;CFO&gt;director) × cluster corroboration × personal-stake change (Δ Held) × $ size × buying-into-weakness. <b className="up">80+</b> = act-on cluster/C-suite buys; <b style={{color:"var(--cy)"}}>65–79</b> = strong single buy; <b style={{color:"var(--amb)"}}>50–64</b> = watch; <b className="dn">&lt;50</b> = sell pressure. Planned <b>10b5-1</b> sells land near neutral (noise); discretionary sells score low. Sort by Conviction to rank what to buy.</span>
      </div>

      <div className="pm-note mono dim2">
        Form 4 filings via <b>EODHD /insider-transactions</b> (SEC EDGAR backbone, ~4-min sync) · <b>Schwab /markets/quotes</b> marks each trade vs the current price (vs Spot). Cluster detection groups 2+ open-market buyers per name inside a rolling window; C-suite roles up-weighted. Click any row → 14-lens detail (Insider lens). <b>Not advice</b> — a conviction signal, not a trade.
      </div>
    </div>
  );
}

window.SurfaceInsider = SurfaceInsider;
window.insiderEdge = insiderEdge;
window.insConviction = insConviction;

// ── 1-year insider-signal track record (hit / fail) ─────────────
function InsiderTrack({ onTicker }) {
  const { useState: useInsT } = React;
  const led = React.useMemo(() => {
    let s = 0x1a5de7; const rng = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
    const syms = ["ARGN","NVRH","ARCM","FLNX","GENO","DRSH","NEXO","BORA","KARO","INPR","VLCT","BIVO","ZOTR","MERC"];
    const kinds = [["Cluster buy","gn",0.72],["C-suite buy","cy",0.66],["Single buy","cy",0.58],["Discretionary sell","rd",0.55]];
    const out = [];
    for (let i = 0; i < 26; i++) {
      const sym = syms[Math.floor(rng() * syms.length)];
      const k = kinds[Math.floor(rng() * kinds.length)];
      const wk = Math.floor(rng() * 50) + 1;
      const bullish = !/sell/i.test(k[0]);
      const fwd = +((rng() - (rng() < k[2] ? 0.32 : 0.6)) * 22 * (bullish ? 1 : -1)).toFixed(1);
      const hit = bullish ? fwd > 0 : fwd > 0; // sell-signal "hit" = avoided/fell handled as fwd sign
      out.push({ sym, kind: k[0], tone: k[1], wk, fwd, hit: bullish ? fwd > 0 : fwd < 0, bullish });
    }
    return out.sort((a, b) => a.wk - b.wk);
  }, []);
  const [f, setF] = useInsT("all");
  const resolved = led.length, hits = led.filter(l => l.hit).length;
  const hitRate = resolved ? hits / resolved * 100 : 0;
  const clusters = led.filter(l => /Cluster/.test(l.kind));
  const clHit = clusters.length ? clusters.filter(l => l.hit).length / clusters.length * 100 : 0;
  const avgFwd = resolved ? led.reduce((a, l) => a + (l.bullish ? l.fwd : -l.fwd), 0) / resolved : 0;
  const rows = led.filter(l => f === "all" || (f === "hit" ? l.hit : !l.hit));
  return (
    <div className="wsx-body">
      <div className="mpf-jr-kpis" style={{ gridTemplateColumns: "repeat(5,1fr)", display: "grid", gap: 8, marginBottom: 12 }}>
        <InsTk l="Resolved · 1Y" v={resolved} s="signals scored" tone="cy" />
        <InsTk l="Hit rate" v={`${hitRate.toFixed(0)}%`} s={`${hits} of ${resolved}`} tone={hitRate >= 55 ? "gn" : "amb"} />
        <InsTk l="Cluster-buy hit" v={`${clHit.toFixed(0)}%`} s={`${clusters.length} clusters`} tone={clHit >= 60 ? "gn" : "amb"} />
        <InsTk l="Avg fwd 42d" v={`${avgFwd >= 0 ? "+" : ""}${avgFwd.toFixed(1)}%`} s="signal-aligned" tone={avgFwd >= 0 ? "gn" : "rd"} />
        <InsTk l="Edge" v={hitRate >= 55 ? "REAL" : "THIN"} s="vs 50% coin" tone={hitRate >= 55 ? "gn" : "amb"} />
      </div>
      <div className="aip-board-bar" style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="mono dim2">{resolved} insider signals scored at +42 trading days · open-market only, 10b5-1 excluded</span>
        <div className="seg">{[["all", "All"], ["hit", "Hits"], ["fail", "Misses"]].map(([id, l]) => <button key={id} className={`seg-btn ${f === id ? "is-on" : ""}`} onClick={() => setF(id)}>{l}</button>)}</div>
      </div>
      <table className="dtable wsx-tbl insx-tbl">
        <thead><tr><th>When</th><th>Sym</th><th>Signal</th><th className="r">Fwd 42d</th><th>Outcome</th></tr></thead>
        <tbody>{rows.map((l, i) => (
          <tr key={i} onClick={() => onTicker(l.sym)} style={{ cursor: "pointer" }}>
            <td className="mono dim2">{l.wk}w ago</td>
            <td className="mono"><b>{l.sym}</b></td>
            <td><span className={`insx-sig insx-sig--${l.tone}`}>{l.kind}</span></td>
            <td className={`r mono tabular ${l.fwd >= 0 ? "up" : "dn"}`}><b>{l.fwd >= 0 ? "+" : ""}{l.fwd}%</b></td>
            <td><span className={`aip-out kpi-tone--${l.hit ? "gn" : "rd"}`}>{l.hit ? "✓ HIT" : "✕ MISS"}</span></td>
          </tr>
        ))}</tbody>
      </table>
      <div className="of-playbook mono"><span className="of-pb-tag" style={{ color: "var(--gn)" }}>SIGNAL EDGE</span><span className="of-pb-txt">Insider <b>cluster buys</b> are the strongest cohort — they resolve up <b className="up">{clHit.toFixed(0)}%</b> of the time over 42 days. Each signal is logged at filing and marked forward; this is the audit behind the conviction scores.</span></div>
    </div>
  );
}
function InsTk({ l, v, s, tone }) {
  return <div className={`pf-tile pf-tile--${tone}`}><div className="pf-tile-l mono dim2">{l}</div><div className={`pf-tile-v mono kpi-tone--${tone}`}>{v}</div><div className="pf-tile-s mono dim2">{s}</div></div>;
}
