// surface-insider.jsx — Insider Trading · open-market net-buy board.
// REAL DATA: window.__BV.scanRows() carries a per-name insider field on every
// scan row — `insNet` (net open-market buys = buys − sells, from EODHD Form-4)
// and `insUsd` ($M of insider open-market buys). We mirror home.jsx
// resolveDiscovery's "INSIDER" group: take rows with insNet>0, sort desc,
// intersect with the audit log (HR.inAudit), and surface ticker · net buys ·
// $ size · score · sector. The alpha is CLUSTERS — names with the largest net
// insider accumulation, audit-tracked so every clickable symbol also exists in
// Track Record.
//
// Served-aware: window.__BV present → real data or honest-empty. Demo sample
// only behind !window.__BV (standalone showcase / server down).
const { useState: useIns, useMemo: useInsm } = React;

// ── HR shim: replicate the small bits of home.jsx's REAL-DATA layer we need.
// (home.jsx defines `HR`; if it's already in scope we reuse it, else rebuild.)
const INS_HR = (typeof HR !== "undefined" && HR) || (function () {
  const num = (v, d) => (typeof v === "number" && isFinite(v)) ? v : d;
  const sym0 = (s) => String(s || "").split(".")[0].toUpperCase();
  function rows() {
    const BV = window.__BV;
    return (BV && BV.ready && BV.scanRows) ? BV.scanRows() : [];
  }
  function ledgerSet() {
    const SL = window.SigLedger;
    if (!SL || !SL.SIGNALS || !SL.SIGNALS.length) return null;
    return new Set(SL.SIGNALS.map(s => s.sym));
  }
  function ledgerReal() { return !!(window.SigLedger && window.SigLedger.real); }
  function inAudit(sym) {
    const set = ledgerSet();
    if (!set || !ledgerReal()) return true;
    return set.has(sym0(sym));
  }
  return { num, sym0, rows, inAudit, has: () => rows().length > 0 };
})();

// ── DEMO sample — ONLY rendered when window.__BV is absent (standalone showcase).
// Real symbols from the public S&P (not fabricated demo-only tickers).
const INS_DEMO = [
  { sym:"COST", insNet:42000,  insUsd:34.1, score:84, sector:"Cons Staples", verdict:"BUY",   chg:+1.2 },
  { sym:"WMB",  insNet:31000,  insUsd:1.4,  score:88, sector:"Energy",       verdict:"BUY",   chg:+0.6 },
  { sym:"KMI",  insNet:120000, insUsd:2.9,  score:71, sector:"Energy",       verdict:"WATCH", chg:-0.4 },
  { sym:"ROST", insNet:9500,   insUsd:1.3,  score:76, sector:"Cons Disc",    verdict:"WATCH", chg:+0.9 },
  { sym:"MO",   insNet:18000,  insUsd:1.1,  score:69, sector:"Cons Staples", verdict:"WATCH", chg:+0.3 },
];

const fmtVal = v => v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}K` : `$${Math.round(v)}`;
const fmtUsdM = m => m >= 1 ? `$${m.toFixed(1)}M` : m > 0 ? `$${Math.round(m * 1000)}K` : "—";

// ── Build the REAL insider board from scan rows (mirrors home.jsx resolveDiscovery).
// Returns rows with insNet>0, audit-intersected, sorted by net buys desc.
function buildInsiderBoard() {
  const rows = INS_HR.rows();
  if (!rows.length) return [];
  return rows
    .filter(r => INS_HR.num(r.insNet, 0) > 0 && INS_HR.inAudit(r.sym))
    .map(r => ({
      sym: r.sym,
      insNet: INS_HR.num(r.insNet, 0),
      insUsd: INS_HR.num(r.insUsd, 0),
      score: INS_HR.num(r.score, null),
      sector: r.sector || "—",
      verdict: String(r.verdict || "").toUpperCase(),
      chg: INS_HR.num(r.chg, null),
    }))
    .sort((a, b) => b.insNet - a.insNet);
}

// ── conviction score 0–100 — net-buy accumulation × engine score × tape.
// Insider net buys (size of open-market accumulation) is the primary signal;
// the engine composite score corroborates; same-day strength is a small tilt.
function insConviction(t) {
  const net = INS_HR.num(t.insNet, 0);
  if (net <= 0) {
    // net seller → low conviction (scaled by magnitude)
    const mag = Math.min(1, Math.abs(net) / 50000);
    return Math.round(Math.max(6, 38 - mag * 24));
  }
  const sizeC = Math.min(1, net / 50000);                       // net-buy size
  const usdC = Math.min(1, INS_HR.num(t.insUsd, 0) / 10);       // $M size
  const sco = INS_HR.num(t.score, null);
  const scoreC = sco != null ? Math.min(1, Math.max(0, (sco - 50) / 40)) : 0.4; // engine corroboration
  const dipC = (t.chg != null && t.chg <= 0) ? 1 : 0.6;         // buying into weakness
  const raw = sizeC * 0.42 + usdC * 0.18 + scoreC * 0.28 + dipC * 0.12;
  return Math.round(44 + raw * 56); // buys land 44–100
}
function insConvTone(s) { return s >= 80 ? "gn" : s >= 65 ? "cy" : s >= 50 ? "amb" : "rd"; }

function insSignal(t) {
  const net = INS_HR.num(t.insNet, 0);
  const sco = INS_HR.num(t.score, null);
  if (net <= 0) return { tone:"rd", label:"NET SELL" };
  if (sco != null && sco >= 80) return { tone:"gn", label:"STRONG BUY" };
  if (net >= 30000) return { tone:"gn", label:"CLUSTER BUY" };
  if (sco != null && sco >= 65) return { tone:"cy", label:"CONFIRMED BUY" };
  return { tone:"amb", label:"INSIDER BUY" };
}

// Per-ticker insider edge — read a single name from the live scan row.
// Exposed for the Overview lens confluence chip.
function insiderEdge(sym) {
  const s = INS_HR.sym0(sym);
  const board = (window.__BV ? buildInsiderBoard() : INS_DEMO);
  const row = board.find(t => INS_HR.sym0(t.sym) === s)
    || (window.__BV && INS_HR.rows().map(r => ({ sym: r.sym, insNet: INS_HR.num(r.insNet, 0), insUsd: INS_HR.num(r.insUsd, 0), score: INS_HR.num(r.score, null), chg: INS_HR.num(r.chg, null) })).find(r => INS_HR.sym0(r.sym) === s));
  if (!row) return null;
  const net = INS_HR.num(row.insNet, 0);
  if (net === 0 && INS_HR.num(row.insUsd, 0) === 0) return null;
  const score = insConviction(row);
  let verdict = "NEUTRAL", tone = "ink";
  if (net > 0) {
    if (net >= 30000 || score >= 80) { verdict = "CLUSTER BUY"; tone = "gn"; }
    else if (score >= 65) { verdict = "INSIDER BUY"; tone = "cy"; }
    else { verdict = "INSIDER BUY"; tone = "amb"; }
  } else if (net < 0) { verdict = "INSIDER SELLING"; tone = "rd"; }
  return { sym: s, verdict, tone, score, net, usd: INS_HR.num(row.insUsd, 0) };
}

function SurfaceInsider({ onTicker }) {
  const [sort, setSort] = useIns({ col: "conv", dir: -1 });

  const served = !!window.__BV;
  const board = useInsm(() => (served ? buildInsiderBoard() : INS_DEMO), [served]);

  const rows = useInsm(() => {
    return board.map(t => ({ ...t, conv: insConviction(t) }))
      .sort((a, b) => { const v = (a[sort.col] < b[sort.col] ? -1 : 1); return v * sort.dir; });
  }, [board, sort]);

  // aggregate KPIs (real, derived from the board)
  const buyers = board.length;
  const totalNet = board.reduce((a, t) => a + INS_HR.num(t.insNet, 0), 0);
  const totalUsd = board.reduce((a, t) => a + INS_HR.num(t.insUsd, 0), 0);
  const clusters = board.filter(t => INS_HR.num(t.insNet, 0) >= 30000);
  const strong = board.filter(t => t.score != null && t.score >= 80);
  const largest = board.length ? [...board].sort((a, b) => INS_HR.num(b.insUsd, 0) - INS_HR.num(a.insUsd, 0))[0] : null;

  const setS = c => setSort(s => ({ col: c, dir: s.col === c ? -s.dir : -1 }));
  const TH = (c, l, r) => <th className={`${r ? "r" : ""} wsx-th ${sort.col === c ? "is-active" : ""}`} onClick={() => setS(c)} style={{ cursor:"pointer" }}>{l}{sort.col === c && <span className="wsx-arr mono">{sort.dir > 0 ? "▲" : "▼"}</span>}</th>;

  const empty = served && board.length === 0;

  return (
    <div className="surface wsx wsx--cy insx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">INSIDER TRADING · OPEN-MARKET NET BUYS</div>
          <h1 className="wsx-title mono">Insider Trading</h1>
          <div className="wsx-sub mono dim2">net open-market buys (buys−sells) per name · ranked by accumulation size · engine-score corroborated · audit-tracked · the strongest smart-money signal</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state={served ? "live" : "demo"} age={served ? "scan feed" : "sample"} /><span className="mono dim2">src · EODHD Form-4 net (scan feed · r.insNet)</span></div>
      </div>

      {empty ? (
        <div className="wsx-body">
          <div className="pm-note mono dim2" style={{ textAlign:"center", padding:"48px 24px", fontSize:"15px" }}>
            No insider clusters in today's scan.
            <div className="dim2" style={{ marginTop:8, fontSize:"12px" }}>No scan row carries net open-market insider buys right now (today's scan may be empty or quota-limited). This board populates from EODHD Form-4 net buys on the live scan universe.</div>
          </div>
        </div>
      ) : (
      <React.Fragment>
      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">CLUSTER SIGNALS</div><div className="wsx-kpi-v mono kpi-tone--gn">{clusters.length}</div><div className="wsx-kpi-s mono dim2">net buys ≥ 30K sh</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">NAMES BUYING</div><div className="wsx-kpi-v mono kpi-tone--gn">{buyers}</div><div className="wsx-kpi-s mono dim2">net insider buyers</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">SCORE-CONFIRMED</div><div className="wsx-kpi-v mono kpi-tone--cy">{strong.length}</div><div className="wsx-kpi-s mono dim2">engine score ≥ 80</div></div>
        <div className="wsx-kpi wsx-kpi--copper"><div className="wsx-kpi-l mono">LARGEST $ BUY</div><div className="wsx-kpi-v mono kpi-tone--copper">{largest && largest.insUsd > 0 ? fmtUsdM(largest.insUsd) : "—"}</div><div className="wsx-kpi-s mono dim2">{largest ? largest.sym : "—"}{largest && largest.sector ? " · " + largest.sector : ""}</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">NET SHARES</div><div className="wsx-kpi-v mono kpi-tone--amb">{(totalNet / 1000).toFixed(0)}K</div><div className="wsx-kpi-s mono dim2">{totalUsd > 0 ? fmtUsdM(totalUsd) + " total" : "open-market net"}</div></div>
      </div>

      {/* cluster highlight — names with the largest net accumulation */}
      {clusters.length > 0 && (
        <div className="insx-clusters">
          {clusters.slice(0, 8).map(c => (
            <div key={c.sym} className="insx-cluster" onClick={() => onTicker(c.sym)}>
              <div className="insx-cl-top">
                <span className="insx-cl-sym mono">{c.sym}</span>
                <span className="insx-cl-tag">⛓ NET BUY · {(c.insNet / 1000).toFixed(0)}K sh</span>
              </div>
              <div className="insx-cl-val mono kpi-tone--gn">{c.insUsd > 0 ? fmtUsdM(c.insUsd) : "+" + c.insNet.toLocaleString() + " net"}</div>
              <div className="insx-cl-roles mono dim2">{c.sector}{c.score != null ? " · score " + c.score : ""}</div>
            </div>
          ))}
        </div>
      )}

      <div className="wsx-body">
        <table className="dtable wsx-tbl insx-tbl">
          <thead><tr>{TH("conv","Conviction",true)}{TH("sym","Sym")}<th>Sector</th><th>Txn</th>{TH("insNet","Net Buys (sh)",true)}{TH("insUsd","$ Size",true)}{TH("score","Score",true)}<th className="r">Day %</th><th>Signal</th><th></th></tr></thead>
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
                <td className="mono"><b>{t.sym}</b></td>
                <td className="mono dim2">{t.sector}</td>
                <td><span className={`insx-txn insx-txn--${t.insNet>=0?"buy":"sell"}`}>{t.insNet>=0?"BUY":"SELL"}</span></td>
                <td className={`r mono tabular ${t.insNet>=0?"up":"dn"}`}>{t.insNet>=0?"+":""}{t.insNet.toLocaleString()}</td>
                <td className="r mono tabular up">{t.insUsd>0?fmtUsdM(t.insUsd):"—"}</td>
                <td className="r mono tabular dim">{t.score!=null?t.score:"—"}</td>
                <td className={`r mono tabular ${t.chg!=null?(t.chg>=0?"up":"dn"):"dim2"}`}>{t.chg!=null?(t.chg>=0?"+":"")+t.chg+"%":"—"}</td>
                <td><span className={`insx-sig insx-sig--${sig.tone}`}>{sig.label}</span></td>
                <td className="r mono dim">›</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>

      <div className="of-playbook mono">
        <span className="of-pb-tag" style={{color:"var(--gn)"}}>CONVICTION SCORE</span>
        <span className="of-pb-txt">Every name is scored <b>0–100</b> on one scale: net open-market accumulation size (buys−sells) × $ size × engine composite score × buying-into-weakness. <b className="up">80+</b> = act-on cluster buys; <b style={{color:"var(--cy)"}}>65–79</b> = score-confirmed buy; <b style={{color:"var(--amb)"}}>50–64</b> = watch; <b className="dn">&lt;50</b> = net selling. Sort by Conviction to rank what to buy.</span>
      </div>

      <div className="pm-note mono dim2">
        Net open-market insider buys per name via <b>EODHD Form-4</b> (SEC EDGAR backbone), carried on every scan row as <b>r.insNet</b> (net shares) and <b>r.insUsd</b> ($ size). Cluster detection flags names with ≥30K net shares accumulated; the engine composite score corroborates. Board is intersected with the audit log so every clickable symbol is also in Track Record. Click any row → 14-lens detail (Insider lens). <b>Not advice</b> — a conviction signal, not a trade.
      </div>
      </React.Fragment>
      )}
    </div>
  );
}

window.SurfaceInsider = SurfaceInsider;
window.insiderEdge = insiderEdge;
window.insConviction = insConviction;
