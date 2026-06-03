// surface-sector.jsx — Sector ETF rotation cockpit.
// 11-sector heatmap + RRG rotation quadrant + leadership + breadth + earnings velocity.
// Shaped from EODHD sector-ETF EOD + /calendar + Schwab quotes.

const { useState: useSec, useMemo: useSecm } = React;

const SEC_DATA = [
  ["XLK","Technology",     +1.8, 88, 92, 76, "leading",   "accel",  6],
  ["XLB","Materials",      +1.2, 84, 80, 64, "leading",   "accel",  3],
  ["XLE","Energy",         +2.9, 82, 71, 58, "leading",   "steady", 2],
  ["XLI","Industrials",    +0.6, 61, 55, 52, "weakening", "fade",   5],
  ["XLV","Healthcare",     +0.4, 58, 49, 61, "improving", "accel",  8],
  ["XLC","Communications", +0.2, 54, 52, 48, "weakening", "steady", 4],
  ["XLY","Consumer Disc.", -0.3, 49, 44, 55, "lagging",   "fade",   3],
  ["XLP","Staples",        -0.1, 44, 41, 38, "improving", "steady", 2],
  ["XLF","Financials",     -0.4, 41, 38, 44, "lagging",   "fade",   7],
  ["XLU","Utilities",      -0.5, 38, 34, 31, "lagging",   "steady", 1],
  ["XLRE","Real Estate",   -0.7, 32, 30, 28, "lagging",   "fade",   2],
];

function SurfaceSector({ onTicker }) {
  const [period, setPeriod] = useSec("1D");
  const leaders = SEC_DATA.filter(s => s[6] === "leading");
  const laggards = SEC_DATA.filter(s => s[6] === "lagging");
  const riskOn = SEC_DATA.filter(s => s[5] >= 50).length;

  // RRG quadrant: x = RS-ratio (rel strength), y = RS-momentum
  const rrgPt = (s) => {
    const rsr = s[3], mom = s[7] === "accel" ? 70 : s[7] === "steady" ? 50 : 30;
    return { x: rsr, y: mom, q: s[6] };
  };

  return (
    <div className="surface wsx wsx--cy sec">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">SECTOR ROTATION COCKPIT · 11 GICS SPDRs</div>
          <h1 className="wsx-title mono">Sector ETFs</h1>
          <div className="wsx-sub mono dim2">heatmap · RRG rotation quadrant · leadership vs SPY · breadth · earnings velocity</div>
        </div>
        <div className="wsx-hdr-r">
          <div className="seg">{["1D","5D","1M","3M"].map(p => <button key={p} className={`seg-btn ${period===p?"is-on":""}`} onClick={()=>setPeriod(p)}>{p}</button>)}</div>
          <FreshnessPill state="live" age="18s" />
        </div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">LEADER</div><div className="wsx-kpi-v mono kpi-tone--gn">XLE +2.9%</div><div className="wsx-kpi-s mono dim2">energy</div></div>
        <div className="wsx-kpi wsx-kpi--rd"><div className="wsx-kpi-l mono">LAGGARD</div><div className="wsx-kpi-v mono kpi-tone--rd">XLRE −0.7%</div><div className="wsx-kpi-s mono dim2">real estate</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">RISK-ON</div><div className="wsx-kpi-v mono kpi-tone--cy">{riskOn} / 11</div><div className="wsx-kpi-s mono dim2">above 50-DMA</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">ROTATION</div><div className="wsx-kpi-v mono kpi-tone--amb">CYCLICAL</div><div className="wsx-kpi-s mono dim2">into Tech/Mat/Engy</div></div>
      </div>

      <div className="sec-grid">
        {/* Heatmap */}
        <div className="lab-card">
          <div className="lab-card-h mono">11-SECTOR HEATMAP · {period} perf · sized equal, colored by perf</div>
          <div className="sec-heat">
            {SEC_DATA.map((s,i)=>{
              const c = s[2] >= 1 ? "rgba(74,222,128,0.42)" : s[2] >= 0 ? "rgba(74,222,128,0.18)" : s[2] >= -0.5 ? "rgba(248,113,113,0.20)" : "rgba(248,113,113,0.40)";
              return (
                <button key={i} className="sec-cell" style={{ background: c }} onClick={()=>onTicker(s[0])}>
                  <div className="sec-cell-sym mono">{s[0]}</div>
                  <div className={`sec-cell-chg mono ${s[2]>=0?"up":"dn"}`}>{s[2]>=0?"+":""}{s[2]}%</div>
                  <div className="sec-cell-name mono dim2">{s[1]}</div>
                  <div className="sec-cell-rs mono dim2">RS {s[3]} · #{i+1}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* RRG rotation quadrant */}
        <div className="lab-card">
          <div className="lab-card-h mono">RRG · ROTATION QUADRANT</div>
          <svg viewBox="0 0 260 240" className="sec-rrg" preserveAspectRatio="xMidYMid meet">
            <rect x="20" y="10" width="110" height="110" fill="color-mix(in oklab, var(--blue) 7%, transparent)" />
            <rect x="130" y="10" width="110" height="110" fill="color-mix(in oklab, var(--gn) 8%, transparent)" />
            <rect x="20" y="120" width="110" height="110" fill="color-mix(in oklab, var(--rd) 8%, transparent)" />
            <rect x="130" y="120" width="110" height="110" fill="color-mix(in oklab, var(--amb) 7%, transparent)" />
            <line x1="130" y1="10" x2="130" y2="230" stroke="var(--glass-line)" /><line x1="20" y1="120" x2="240" y2="120" stroke="var(--glass-line)" />
            <text x="135" y="22" fontSize="8" className="mono" fill="var(--gn)">LEADING</text>
            <text x="25" y="22" fontSize="8" className="mono" fill="var(--blue)">IMPROVING</text>
            <text x="135" y="226" fontSize="8" className="mono" fill="var(--amb)">WEAKENING</text>
            <text x="25" y="226" fontSize="8" className="mono" fill="var(--rd)">LAGGING</text>
            {SEC_DATA.map((s,i)=>{
              const p = rrgPt(s);
              const cx = 20 + (p.x/100)*220, cy = 230 - (p.y/100)*220;
              const col = p.q==="leading"?"var(--gn)":p.q==="improving"?"var(--blue)":p.q==="weakening"?"var(--amb)":"var(--rd)";
              return <g key={i}><circle cx={cx} cy={cy} r="4" fill={col} style={{filter:`drop-shadow(0 0 4px ${col})`}} /><text x={cx+6} y={cy+3} fontSize="8" className="mono" fill="var(--ink-1)">{s[0]}</text></g>;
            })}
          </svg>
        </div>
      </div>

      <div className="sec-grid">
        {/* Leadership table */}
        <div className="lab-card">
          <div className="lab-card-h mono">SECTOR LEADERSHIP · vs SPY · breadth · flows</div>
          <table className="dtable wsx-tbl sec-tbl">
            <thead><tr><th>ETF</th><th>Sector</th><th className="r">{period} %</th><th className="r">RS</th><th className="r">vs SPY</th><th>Quadrant</th><th className="r">Breadth</th><th className="r">Earn 7d</th></tr></thead>
            <tbody>{SEC_DATA.map((s,i)=>(
              <tr key={i} onClick={()=>onTicker(s[0])}>
                <td className="mono"><b>{s[0]}</b></td><td className="dim">{s[1]}</td>
                <td className={`r mono tabular ${s[2]>=0?"up":"dn"}`}>{s[2]>=0?"+":""}{s[2]}%</td>
                <td className="r mono tabular"><b>{s[3]}</b></td>
                <td className={`r mono tabular ${s[4]>=50?"up":"dn"}`}>{s[4]>=50?"+":""}{(s[4]-50)/5}%</td>
                <td><span className={`pm-taxon pm-tax--${s[6]==="leading"?"gn":s[6]==="improving"?"ink":s[6]==="weakening"?"amb":"rd"}`}>{s[6]}</span></td>
                <td className={`r mono tabular ${s[5]>=50?"up":"dn"}`}>{s[5]}%</td>
                <td className={`r mono tabular ${s[8]>=5?"amb":"dim"}`}>{s[8]}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>

        {/* Earnings velocity */}
        <div className="lab-card">
          <div className="lab-card-h mono">EARNINGS VELOCITY · next 7d by sector</div>
          <div className="sec-velocity">
            {[...SEC_DATA].sort((a,b)=>b[8]-a[8]).slice(0,7).map((s,i)=>(
              <div key={i} className="sec-vel-row">
                <span className="mono sec-vel-etf">{s[0]}</span>
                <span className="mono dim2 sec-vel-name">{s[1]}</span>
                <div className="sec-vel-bar"><div style={{width:`${s[8]*11}%`,background:s[8]>=5?"var(--amb)":"var(--cy)"}}/></div>
                <span className="mono sec-vel-n">{s[8]}</span>
              </div>
            ))}
          </div>
          <div className="lab-verdict mono dim2">Sectors with clustered reporters face sympathy moves &amp; dispersion — size around the catalyst density. Source: EODHD /calendar.</div>
        </div>
      </div>

      <div className="lab-card">
        <div className="lab-card-h mono">CROSS-ASSET · STYLE · THEMATIC ETFs</div>
        <div className="sec-xa">
          {[
            ["Style","SPY",+0.4,"gn"],["Style","QQQ",+0.6,"gn"],["Style","IWM",-0.2,"rd"],["Style","MTUM",+0.8,"gn"],["Style","VLUE",-0.1,"rd"],["Style","RSP",+0.2,"ink"],
            ["Bonds","TLT",-0.5,"rd"],["Bonds","HYG",+0.1,"ink"],["Bonds","LQD",-0.2,"rd"],["Bonds","TIP",+0.0,"ink"],
            ["Commod","GLD",+0.3,"gn"],["Commod","USO",-0.9,"rd"],["Commod","SLV",+0.5,"gn"],["Commod","DBC",-0.4,"rd"],
            ["Thematic","SMH",+1.9,"gn"],["Thematic","ARKK",+2.4,"gn"],["Thematic","XBI",-0.6,"rd"],["Thematic","TAN",+1.1,"gn"],
            ["Intl","EEM",+0.7,"gn"],["Intl","EFA",+0.3,"gn"],["Intl","FXI",+1.4,"gn"],["Intl","EWJ",-0.2,"rd"],
          ].map((e,i)=>(
            <button key={i} className={`sec-xa-cell sec-xa--${e[3]}`} onClick={()=>onTicker(e[1])}>
              <span className="sec-xa-grp mono dim2">{e[0]}</span>
              <span className="sec-xa-sym mono">{e[1]}</span>
              <span className={`sec-xa-chg mono kpi-tone--${e[3]}`}>{e[2]>=0?"+":""}{e[2]}%</span>
            </button>
          ))}
        </div>
        <div className="lab-verdict mono dim2">Beyond the 11 GICS sectors: style/factor (MTUM·VLUE·RSP), bonds (TLT·HYG), commodities (GLD·USO), thematic (SMH·ARKK·XBI), international (EEM·FXI). The full ETF rotation universe.</div>
      </div>

      <div className="pm-note mono dim2">
        Heatmap + RS from <b>EODHD /eod</b> sector SPDRs · RRG quadrant = RS-ratio × RS-momentum (the canonical rotation read: improving → leading → weakening → lagging) ·
        breadth = % members above 50-DMA · earnings velocity from <b>EODHD /calendar</b> · live prices <b>Schwab /markets/quotes</b>.
      </div>
    </div>
  );
}

window.SurfaceSector = SurfaceSector;
