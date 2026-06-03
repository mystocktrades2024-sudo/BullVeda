// surface-earnings.jsx — Catalyst & Earnings calendar
// Sources: EODHD /calendar/earnings + Nasdaq estimates; expected move derived from
// front-month option IV (Schwab /chains); historical avg move from 8-quarter realized.
const { useState: useErnS } = React;

const ERN_DAYS = ["MON 02", "TUE 03", "WED 04", "THU 05", "FRI 06"];
const ERN = [
  { sym:"VELO", day:0, when:"AMC", exp:9.2, ivr:74, hist:7.8, drift:"+", port:true,  epsE:"1.12", revE:"4.2B" },
  { sym:"NMBS", day:0, when:"BMO", exp:7.1, ivr:61, hist:6.4, drift:"+", port:true,  epsE:"0.48", revE:"1.1B" },
  { sym:"ARCM", day:1, when:"BMO", exp:5.4, ivr:48, hist:4.9, drift:"flat", port:false, epsE:"0.91", revE:"2.0B" },
  { sym:"GENO", day:1, when:"AMC", exp:14.6,ivr:92, hist:12.1,drift:"−", port:false, epsE:"-0.34",revE:"0.3B" },
  { sym:"KOSM", day:2, when:"AMC", exp:11.3,ivr:83, hist:9.7, drift:"+", port:true,  epsE:"0.22", revE:"0.8B" },
  { sym:"PALA", day:2, when:"BMO", exp:6.8, ivr:55, hist:6.0, drift:"+", port:true,  epsE:"1.44", revE:"3.1B" },
  { sym:"MERC", day:3, when:"AMC", exp:8.9, ivr:69, hist:8.2, drift:"−", port:false, epsE:"0.67", revE:"1.9B" },
  { sym:"QBIT", day:3, when:"AMC", exp:12.4,ivr:88, hist:10.5,drift:"+", port:true,  epsE:"0.05", revE:"0.6B" },
  { sym:"LUMA", day:4, when:"BMO", exp:6.2, ivr:52, hist:5.5, drift:"flat", port:false, epsE:"0.38", revE:"0.9B" },
];
const ERN_OTHER = [
  { d:"WED 04", t:"PDUFA", sym:"BIVO", note:"FDA decision · Bivota lead asset", tone:"violet" },
  { d:"THU 05", t:"Investor Day", sym:"ARGN", note:"Argentum capital markets day", tone:"cy" },
  { d:"FRI 06", t:"Ex-Div", sym:"IONX", note:"Ionix ex-dividend · $0.42", tone:"gn" },
  { d:"TUE 03", t:"Product", sym:"VELO", note:"Velocity delivery numbers", tone:"amb" },
];

function ErnKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}
const ernTone = e => e.ivr >= 80 ? "rd" : e.ivr >= 60 ? "amb" : "gn";

function SurfaceEarnings({ onTicker }) {
  const [sel, setSel] = useErnS(null);
  const inPort = ERN.filter(e => e.port).length;
  const avgMove = (ERN.reduce((a, e) => a + e.exp, 0) / ERN.length).toFixed(1);
  const hottest = [...ERN].sort((a, b) => b.ivr - a.ivr)[0];

  return (
    <div className="surface wsx wsx--violet erx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">CATALYSTS · EARNINGS</div>
          <h1 className="wsx-title mono">Catalyst Calendar</h1>
          <div className="wsx-sub mono dim2">earnings · expected move from option IV · IV-rank · post-earnings drift bias · FDA / investor-day / ex-div catalysts</div>
        </div>
        <div className="wsx-hdr-r"><FreshnessPill state="live" age="3m" /><span className="mono dim2">src · EODHD /calendar · Nasdaq est. · exp-move from Schwab /chains IV</span></div>
      </div>

      <div className="wsx-kpis erx-kpis">
        <ErnKpi k="THIS WEEK" v={ERN.length} tone="violet" s="confirmed reports" />
        <ErnKpi k="IN PORTFOLIO" v={inPort} tone="copper" s="positions reporting" />
        <ErnKpi k="AVG EXP MOVE" v={`±${avgMove}%`} tone="amb" s="option-implied" />
        <ErnKpi k="HOTTEST IV-RANK" v={`${hottest.sym} ${hottest.ivr}`} tone="rd" s="rich premium · sell vol?" />
        <ErnKpi k="EVENT CATALYSTS" v={ERN_OTHER.length} tone="cy" s="FDA · ex-div · days" />
      </div>

      <div className="erx-week">
        {ERN_DAYS.map((d, di) => {
          const day = ERN.filter(e => e.day === di);
          return (
            <div key={di} className="erx-col">
              <div className="erx-col-h mono">{d}<span className="dim2">{day.length} rpt</span></div>
              <div className="erx-col-body">
                {day.map(e => (
                  <div key={e.sym} className={`erx-card erx-card--${ernTone(e)} ${e.port ? "is-port" : ""}`} onClick={() => onTicker(e.sym)}>
                    <div className="erx-card-top"><span className="mono erx-sym">{e.sym}</span><span className={`erx-when erx-when--${e.when.toLowerCase()}`}>{e.when}</span></div>
                    <div className="erx-move mono">±{e.exp.toFixed(1)}%<span className="dim2"> exp</span></div>
                    <div className="erx-meta mono dim2">IVR {e.ivr} · hist ±{e.hist}%</div>
                    <div className={`erx-drift erx-drift--${e.drift === "+" ? "gn" : e.drift === "−" ? "rd" : "dim"}`}>{e.drift === "+" ? "↗ drift up" : e.drift === "−" ? "↘ drift down" : "→ no drift"}</div>
                    {e.port && <span className="erx-portflag mono">● HELD</span>}
                  </div>
                ))}
                {!day.length && <div className="erx-empty mono dim2">—</div>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="erx-bottom">
        <div className="wsx-card erx-tblwrap">
          <div className="rkx-card-h mono">DETAIL · EXPECTED MOVE vs HISTORICAL</div>
          <table className="dtable wsx-tbl erx-tbl">
            <thead><tr><th>Sym</th><th>Day</th><th>Time</th><th className="r">EPS est</th><th className="r">Rev est</th><th className="r">Exp move</th><th className="r">Hist move</th><th className="r">IV rank</th><th>Drift</th></tr></thead>
            <tbody>
              {ERN.map(e => (
                <tr key={e.sym} onClick={() => onTicker(e.sym)} style={{ cursor:"pointer" }}>
                  <td className="mono"><b>{e.sym}</b>{e.port && <span className="erx-held-dot" title="held" />}</td>
                  <td className="mono dim2">{ERN_DAYS[e.day].split(" ")[0]}</td>
                  <td className={`mono erx-when-t erx-when--${e.when.toLowerCase()}`}>{e.when}</td>
                  <td className="r mono">{e.epsE}</td>
                  <td className="r mono dim2">{e.revE}</td>
                  <td className={`r mono kpi-tone--${ernTone(e)}`}>±{e.exp.toFixed(1)}%</td>
                  <td className="r mono dim2">±{e.hist}%</td>
                  <td className={`r mono kpi-tone--${ernTone(e)}`}>{e.ivr}</td>
                  <td className={`mono ${e.drift === "+" ? "up" : e.drift === "−" ? "dn" : "dim2"}`}>{e.drift === "+" ? "↗ up" : e.drift === "−" ? "↘ down" : "flat"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="rkx-note mono dim2">Expected move = ATM straddle / spot from front-month IV. When IV-rank is rich (≥80: GENO, QBIT, KOSM) the move is often over-priced — favor defined-risk premium-selling structures over long options.</div>
        </div>
        <div className="wsx-card erx-other">
          <div className="rkx-card-h mono">NON-EARNINGS CATALYSTS</div>
          {ERN_OTHER.map((c, i) => (
            <div key={i} className={`erx-cat erx-cat--${c.tone}`} onClick={() => onTicker(c.sym)}>
              <div className="erx-cat-top"><span className={`erx-cat-tag erx-cat-tag--${c.tone}`}>{c.t}</span><span className="mono dim2">{c.d}</span></div>
              <div className="erx-cat-body"><b className="mono">{c.sym}</b> <span className="dim">{c.note}</span></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
window.SurfaceEarnings = SurfaceEarnings;
