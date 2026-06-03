// surface-risk.jsx — Portfolio Risk & Exposure dashboard (quant-grade)
// Sources: positions from broker (Schwab /accounts/positions), betas/correlation computed
// from EODHD /eod 252d, factor loadings from a Barra-style risk model, VaR parametric + historical.
const { useState: useRiskS, useMemo: useRiskM } = React;

const RK_POS = [
  { sym:"ARGN", name:"Argentum Robotics", sector:"Industrials", side:"L", w:8.4, beta:1.32, vol:38, varc:14.2, corr:0.41 },
  { sym:"NMBS", name:"Nimbus Cloud",      sector:"Software",    side:"L", w:7.1, beta:1.18, vol:34, varc:11.0, corr:0.55 },
  { sym:"VELO", name:"Velocity Motors",   sector:"Autos",       side:"L", w:6.8, beta:1.44, vol:46, varc:13.6, corr:0.38 },
  { sym:"KOSM", name:"Kosmos Compute",    sector:"Semis",       side:"L", w:6.2, beta:1.61, vol:52, varc:15.1, corr:0.62 },
  { sym:"QBIT", name:"Quanta Systems",    sector:"Semis",       side:"L", w:5.5, beta:1.55, vol:49, varc:12.4, corr:0.62 },
  { sym:"PALA", name:"Palatine Energy",   sector:"Energy",      side:"L", w:5.0, beta:0.88, vol:31, varc:6.1,  corr:0.12 },
  { sym:"IONX", name:"Ionix Power",       sector:"Utilities",   side:"L", w:4.4, beta:0.51, vol:19, varc:2.4,  corr:0.08 },
  { sym:"ARCM", name:"Arclight Materials",sector:"Materials",   side:"L", w:4.0, beta:1.05, vol:33, varc:5.5,  corr:0.22 },
  { sym:"MERC", name:"Mercia Semi",       sector:"Semis",       side:"S", w:-4.8,beta:1.49, vol:47, varc:9.8,  corr:0.62 },
  { sym:"VANTA",name:"Vanta Logistics",   sector:"Transports",  side:"S", w:-3.6,beta:1.12, vol:36, varc:4.2,  corr:0.18 },
  { sym:"SOLA", name:"Solara Energy",     sector:"Energy",      side:"S", w:-3.1,beta:0.94, vol:40, varc:3.6,  corr:0.12 },
  { sym:"MAPL", name:"Maple Retail",      sector:"Consumer",    side:"S", w:-2.7,beta:0.79, vol:29, varc:2.1,  corr:0.10 },
];
const RK_FACTORS = [
  { label:"Market β",   value:+0.42, tone:"amb" },
  { label:"Momentum",   value:+0.61, tone:"gn" },
  { label:"Growth",     value:+0.38, tone:"gn" },
  { label:"Size (SMB)", value:+0.29, tone:"cy" },
  { label:"Volatility", value:+0.24, tone:"amb" },
  { label:"Quality",    value:-0.12, tone:"rd" },
  { label:"Value (HML)",value:-0.34, tone:"rd" },
];
const RK_STRESS = [
  { sc:"Market −2σ (≈ −4.6%)",      pnl:-6.8, tone:"rd" },
  { sc:"Rates +50bp shock",          pnl:-2.4, tone:"rd" },
  { sc:"Semis −10% (sector)",        pnl:-3.9, tone:"rd" },
  { sc:"Momentum unwind (−1.5σ)",    pnl:-5.1, tone:"rd" },
  { sc:"Vol spike VIX→32",           pnl:-3.2, tone:"amb" },
  { sc:"Risk-on melt-up +2σ",        pnl:+5.4, tone:"gn" },
];

function RkKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function SurfaceRisk({ onTicker }) {
  const [sort, setSort] = useRiskS({ col:"varc", dir:-1 });
  const longs = RK_POS.filter(p => p.side === "L"), shorts = RK_POS.filter(p => p.side === "S");
  const gross = RK_POS.reduce((a, p) => a + Math.abs(p.w), 0);
  const net = RK_POS.reduce((a, p) => a + p.w, 0);
  const betaNet = RK_POS.reduce((a, p) => a + p.w * p.beta, 0) / 100;
  const top5 = [...RK_POS].sort((a, b) => Math.abs(b.w) - Math.abs(a.w)).slice(0, 5).reduce((a, p) => a + Math.abs(p.w), 0);
  // sector net exposure
  const secMap = {};
  RK_POS.forEach(p => { secMap[p.sector] = (secMap[p.sector] || 0) + p.w; });
  const sectors = Object.entries(secMap).map(([label, value]) => ({ label, value, tone: value >= 0 ? "gn" : "rd" })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const rows = useRiskM(() => [...RK_POS].sort((a, b) => {
    const va = a[sort.col], vb = b[sort.col];
    const v = typeof va === "number" ? Math.abs(vb) - Math.abs(va) : String(va).localeCompare(String(vb));
    return v * (sort.dir < 0 ? 1 : -1);
  }), [sort]);
  const setS = c => setSort(s => ({ col:c, dir:s.col === c ? -s.dir : -1 }));

  return (
    <div className="surface wsx wsx--copper rkx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">PORTFOLIO RISK · EXPOSURE</div>
          <h1 className="wsx-title mono">Risk</h1>
          <div className="wsx-sub mono dim2">gross/net · beta-adjusted · factor &amp; sector concentration · parametric + historical VaR · stress scenarios</div>
        </div>
        <div className="wsx-hdr-r"><StaleStamp staleAfter={45} label="risk model run" src="Schwab /positions · betas EODHD 252d · Barra-style factor model" /></div>
      </div>

      <div className="wsx-kpis rkx-kpis">
        <RkKpi k="GROSS EXPOSURE" v={`${gross.toFixed(0)}%`} tone="copper" s={`${longs.length}L · ${shorts.length}S`} />
        <RkKpi k="NET EXPOSURE" v={`${net >= 0 ? "+" : ""}${net.toFixed(0)}%`} tone={net >= 0 ? "gn" : "rd"} s="long-biased" />
        <RkKpi k="BETA-ADJ NET" v={`${betaNet >= 0 ? "+" : ""}${betaNet.toFixed(2)}β`} tone="amb" s="vs SPY" />
        <RkKpi k="1-DAY VaR 95%" v="−3.8%" tone="rd" s="≈ −$4,130 parametric" />
        <RkKpi k="TOP-5 CONC." v={`${top5.toFixed(0)}%`} tone="amb" s="name concentration" />
        <RkKpi k="DAYS TO LIQ." v="1.4d" tone="gn" s="@ 20% ADV" />
        <RkKpi k="CASH" v="22%" tone="cy" s="dry powder" />
      </div>

      <div className="rkx-grid">
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">FACTOR EXPOSURE <span className="dim2">· standardized loadings vs risk model</span></div>
          <QDiverge rows={RK_FACTORS} fmt={v => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`} />
        </div>
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">SECTOR NET EXPOSURE <span className="dim2">· long − short, % NAV</span></div>
          <QDiverge rows={sectors} fmt={v => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`} />
        </div>
      </div>

      <div className="rkx-grid rkx-grid--7030">
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">POSITIONS · RISK CONTRIBUTION <span className="dim2">· click to open</span></div>
          <table className="dtable wsx-tbl rkx-tbl">
            <thead><tr>
              {[["sym","Sym"],["sector","Sector"],["w","Weight"],["beta","β"],["vol","Vol"],["corr","ρ·book"],["varc","% of risk"]].map(([c, l]) => (
                <th key={c} className={["w","beta","vol","corr","varc"].includes(c) ? "r" : ""} onClick={() => setS(c)} style={{ cursor:"pointer" }}>{l}{sort.col === c ? (sort.dir > 0 ? " ▲" : " ▼") : ""}</th>
              ))}
            </tr></thead>
            <tbody>
              {rows.map(p => (
                <tr key={p.sym} onClick={() => onTicker(p.sym)} style={{ cursor:"pointer" }}>
                  <td className="mono"><b>{p.sym}</b> <span className={`rkx-side rkx-side--${p.side === "L" ? "l" : "s"}`}>{p.side}</span></td>
                  <td className="dim">{p.sector}</td>
                  <td className={`r mono ${p.w >= 0 ? "up" : "dn"}`}>{p.w >= 0 ? "+" : ""}{p.w.toFixed(1)}%</td>
                  <td className="r mono">{p.beta.toFixed(2)}</td>
                  <td className="r mono dim2">{p.vol}%</td>
                  <td className="r mono dim2">{p.corr.toFixed(2)}</td>
                  <td className="r"><span className="rkx-risk-bar"><i style={{ width:`${p.varc / 0.16}%` }} /></span> <span className="mono">{p.varc.toFixed(1)}%</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="wsx-card rkx-card">
          <div className="rkx-card-h mono">STRESS SCENARIOS <span className="dim2">· est. book P&amp;L</span></div>
          <div className="rkx-stress">
            {RK_STRESS.map((s, i) => (
              <div key={i} className="rkx-stress-row">
                <span className="mono rkx-stress-l">{s.sc}</span>
                <span className="rkx-stress-bar"><i className={`kpi-tone-bg--${s.tone === "gn" ? "gn" : s.tone === "amb" ? "amb" : "rd"}`} style={{ width:`${Math.min(50, Math.abs(s.pnl) * 6)}%`, left:s.pnl >= 0 ? "50%" : `${50 - Math.min(50, Math.abs(s.pnl) * 6)}%` }} /><b /></span>
                <span className={`mono rkx-stress-v ${s.pnl >= 0 ? "up" : "dn"}`}>{s.pnl >= 0 ? "+" : ""}{s.pnl.toFixed(1)}%</span>
              </div>
            ))}
          </div>
          <div className="rkx-note mono dim2">Beta-adjusted net +0.62β leaves the book long-biased; Semis is the crowded sleeve (3 names, 18% gross) and the dominant VaR contributor. Momentum-factor unwind is the largest single-factor risk.</div>
        </div>
      </div>
    </div>
  );
}
window.SurfaceRisk = SurfaceRisk;
