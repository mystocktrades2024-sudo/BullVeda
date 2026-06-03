// surface-lab.jsx — Research Lab (Admin tier 5).
// Quant R&D bench: hypothesis backtester, factor IC lab, model registry,
// regime explorer, scan-tuning sandbox. Shaped from EODHD history + internal stores.

const { useState: useLab, useMemo: useLabm } = React;

function SurfaceLab({ onTicker }) {
  const [tab, setTab] = useLab("backtest");
  const tabs = [
    ["backtest", "Hypothesis Backtester"],
    ["factor",   "Factor IC Lab"],
    ["models",   "Model Registry"],
    ["regime",   "Regime Explorer"],
    ["sandbox",  "Scan-Tuning Sandbox"],
  ];
  return (
    <div className="surface wsx wsx--violet lab">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">RESEARCH LAB · ADMIN · INTERNAL</div>
          <h1 className="wsx-title mono">Research Lab</h1>
          <div className="wsx-sub mono dim2">strategy R&D bench · walk-forward · IC · model registry · ⚠ off-production sandbox</div>
        </div>
        <div className="wsx-hdr-r"><Pill tone="violet" small>TIER 5 · ADMIN</Pill><FreshnessPill state="live" age="2m" /></div>
      </div>

      <div className="wsx-kpis">
        <div className="wsx-kpi wsx-kpi--violet"><div className="wsx-kpi-l mono">EXPERIMENTS</div><div className="wsx-kpi-v mono kpi-tone--violet">38</div><div className="wsx-kpi-s mono dim2">12 promoted</div></div>
        <div className="wsx-kpi wsx-kpi--gn"><div className="wsx-kpi-l mono">BEST OOS SHARPE</div><div className="wsx-kpi-v mono kpi-tone--gn">2.41</div><div className="wsx-kpi-s mono dim2">VCP·regime-cond</div></div>
        <div className="wsx-kpi wsx-kpi--amb"><div className="wsx-kpi-l mono">AVG DECAY</div><div className="wsx-kpi-v mono kpi-tone--amb">−6%/yr</div><div className="wsx-kpi-s mono dim2">edge half-life</div></div>
        <div className="wsx-kpi wsx-kpi--cy"><div className="wsx-kpi-l mono">MODELS LIVE</div><div className="wsx-kpi-v mono kpi-tone--cy">3</div><div className="wsx-kpi-s mono dim2">1 staging</div></div>
      </div>

      <div className="lab-tabs">
        {tabs.map(([id, l]) => (
          <button key={id} className={`lab-tab ${tab === id ? "is-on" : ""}`} onClick={() => setTab(id)}>{l}</button>
        ))}
      </div>

      <div className="lab-body">
        {tab === "backtest" && <LabBacktest />}
        {tab === "factor" && <LabFactor />}
        {tab === "models" && <LabModels />}
        {tab === "regime" && <LabRegime />}
        {tab === "sandbox" && <LabSandbox />}
      </div>
    </div>
  );
}

// ── Hypothesis Backtester ──
function LabBacktest() {
  const data = useLabm(() => {
    const m = [], b = []; let mv = 0, bv = 0;
    for (let i = 0; i < 60; i++) { mv += 0.22 + (Math.sin(i*0.3)+Math.cos(i*0.5))*0.4 + (Math.random()-0.44)*0.6; bv += 0.06 + (Math.random()-0.5)*0.5; m.push(mv); b.push(bv); }
    return { m, b };
  }, []);
  const w = 620, h = 200, pad = 20;
  const all = [...data.m, ...data.b]; const min = Math.min(...all, -2), max = Math.max(...all, 22);
  const x = i => pad + (i / 59) * (w - pad * 2);
  const y = v => h - pad - ((v - min) / (max - min)) * (h - pad * 2);
  return (
    <div className="lab-grid-2">
      <div className="lab-card">
        <div className="lab-card-h mono">HYPOTHESIS · "VCP + RS≥80 in bull regime"</div>
        <div className="lab-form">
          <LabField k="Universe" v="US ≥ $500M · 4,800" />
          <LabField k="Window" v="2016 → 2026 · walk-fwd" />
          <LabField k="Entry" v="VCP confirmed · RS≥80" />
          <LabField k="Exit" v="T1 ½ · trail ATR×2.2 · 14d stop" />
          <LabField k="Slices" v="train 60 · val 20 · holdout 20" />
        </div>
        <svg viewBox={`0 0 ${w} ${h}`} className="lab-svg" preserveAspectRatio="xMidYMid meet">
          <defs><linearGradient id="lab-eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.3"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0"/></linearGradient></defs>
          <line x1={pad} y1={y(0)} x2={w-pad} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
          <path d={`M ${pad} ${y(0)} L ${data.m.map((v,i)=>`${x(i)},${y(v)}`).join(" L ")} L ${w-pad} ${y(0)} Z`} fill="url(#lab-eq)" />
          <polyline points={data.b.map((v,i)=>`${x(i)},${y(v)}`).join(" ")} stroke="var(--ink-3)" strokeWidth="1.2" fill="none" />
          <polyline points={data.m.map((v,i)=>`${x(i)},${y(v)}`).join(" ")} stroke="var(--gn)" strokeWidth="1.8" fill="none" style={{filter:"drop-shadow(0 0 5px var(--gn))"}} />
        </svg>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">WALK-FORWARD RESULTS</div>
        <div className="lab-stats">
          <LabStat k="OOS Sharpe" v="2.41" tone="gn" />
          <LabStat k="OOS WR" v="61.3%" tone="gn" />
          <LabStat k="Profit factor" v="1.92" tone="gn" />
          <LabStat k="Max DD" v="−8.4%" tone="rd" />
          <LabStat k="IS vs OOS gap" v="0.06" tone="gn" sub="no overfit" />
          <LabStat k="Trades" v="1,284" tone="ink" />
          <LabStat k="Avg hold" v="6.8d" tone="ink" />
          <LabStat k="t-stat" v="3.84" tone="gn" sub="p<0.001" />
        </div>
        <div className="lab-verdict mono"><span className="up">▲ PROMOTE</span> — edge survives holdout, low IS/OOS gap, t-stat significant. Stage to paper.</div>
      </div>
    </div>
  );
}

// ── Factor IC Lab ──
function LabFactor() {
  const factors = [
    ["RVOL × pivot-dist", 0.061, 0.58, "gn"], ["RS rank 63d", 0.048, 0.54, "gn"],
    ["Insider net 90d (z)", 0.034, 0.51, "gn"], ["Earnings drift", 0.029, 0.49, "amb"],
    ["IV rank", -0.018, 0.46, "rd"], ["Short interest Δ", 0.022, 0.48, "amb"],
    ["VCP tightness", 0.044, 0.53, "gn"], ["Sector RS", 0.038, 0.52, "gn"],
  ];
  return (
    <div className="lab-card">
      <div className="lab-card-h mono">INFORMATION COEFFICIENT · 10-day forward · rolling 3y</div>
      <table className="dtable wsx-tbl">
        <thead><tr><th>Factor</th><th className="r">IC</th><th className="r">Hit-rate</th><th>Decile spread</th><th>Read</th></tr></thead>
        <tbody>{factors.map(([f, ic, hr, tone], i) => (
          <tr key={i}>
            <td className="mono">{f}</td>
            <td className={`r mono tabular ${ic>=0.03?"up":ic<0?"dn":"warn"}`}>{ic>=0?"+":""}{ic.toFixed(3)}</td>
            <td className="r mono tabular">{(hr*100).toFixed(0)}%</td>
            <td><span className="lab-icbar"><span style={{width:`${Math.abs(ic)*900}%`,background:`var(--${tone})`,marginLeft:ic<0?"auto":0}}/></span></td>
            <td><Pill tone={tone} small>{tone==="gn"?"KEEP":tone==="amb"?"WATCH":"DROP"}</Pill></td>
          </tr>
        ))}</tbody>
      </table>
      <div className="lab-verdict mono dim2">IC = rank-correlation of factor vs 10d forward return. &gt;0.03 is tradeable; negative = inverse signal.</div>
    </div>
  );
}

// ── Model Registry ──
function LabModels() {
  const rows = [
    ["edge-v4.2","ensemble · 3-head","LIVE","2026-05-20","0.21","61.7%","0.08","gn"],
    ["edge-v4.3","+ regime feature","STAGING","2026-05-27","0.19","62.4%","0.05","amb"],
    ["edge-v4.1","prev prod","ARCHIVED","2026-04-18","0.23","60.1%","0.14","ink"],
    ["magnitude-v2","quantile reg","LIVE","2026-05-12","—","—","0.09","gn"],
  ];
  return (
    <div className="lab-card">
      <div className="lab-card-h mono">MODEL REGISTRY · versioned · rollback-able</div>
      <table className="dtable wsx-tbl">
        <thead><tr><th>Model</th><th>Architecture</th><th>Status</th><th>Trained</th><th className="r">Brier</th><th className="r">OOS WR</th><th className="r">Drift KS</th><th></th></tr></thead>
        <tbody>{rows.map(([m, a, st, tr, br, wr, ks, tone], i) => (
          <tr key={i}>
            <td className="mono"><b>{m}</b></td><td className="mono dim">{a}</td>
            <td><Pill tone={st==="LIVE"?"gn":st==="STAGING"?"amb":"ink"} small>{st}</Pill></td>
            <td className="mono dim2">{tr}</td>
            <td className="r mono tabular">{br}</td><td className="r mono tabular">{wr}</td>
            <td className={`r mono tabular ${parseFloat(ks)<0.1?"up":"warn"}`}>{ks}</td>
            <td className="r"><button className="lab-mini-btn mono">{st==="LIVE"?"rollback":st==="STAGING"?"promote":"restore"}</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// ── Regime Explorer ──
function LabRegime() {
  const regimes = [
    ["Bull · trending","RISK ON",71,2.4,"current","gn"],
    ["Bull · choppy","RISK ON",58,1.6,"",  "amb"],
    ["Bear · trending","RISK OFF",42,0.9,"","rd"],
    ["Panic","RISK OFF",31,0.4,"","rd"],
  ];
  return (
    <div className="lab-grid-2">
      <div className="lab-card">
        <div className="lab-card-h mono">SETUP WIN-RATE × REGIME</div>
        <table className="dtable wsx-tbl">
          <thead><tr><th>Regime</th><th>State</th><th className="r">WR</th><th className="r">PF</th><th></th></tr></thead>
          <tbody>{regimes.map(([r, s, wr, pf, now, tone], i) => (
            <tr key={i} className={now?"is-current":""}>
              <td className="mono">{r}</td><td><Pill tone={s==="RISK ON"?"gn":"rd"} small>{s}</Pill></td>
              <td className={`r mono tabular kpi-tone--${tone}`}>{wr}%</td><td className="r mono tabular">{pf}</td>
              <td className="mono copper">{now?"● NOW":""}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="lab-card">
        <div className="lab-card-h mono">REGIME TRANSITION MATRIX · monthly</div>
        <div className="lab-matrix">
          {["B·T","B·C","Br·T","Pan"].map((c,i)=>(<div key={i} className="lab-mx-h mono">{c}</div>))}
          {[[62,28,8,2],[24,54,18,4],[6,22,56,16],[2,8,34,56]].map((row,r)=>row.map((v,c)=>(
            <div key={`${r}-${c}`} className="lab-mx-cell mono" style={{background:`color-mix(in oklab, var(--${r===c?"gn":"rd"}) ${v*0.7}%, transparent)`}}>{v}</div>
          )))}
        </div>
        <div className="lab-verdict mono dim2">P(next-month regime | current). Diagonal = persistence; bull-trending is sticky (62%).</div>
      </div>
    </div>
  );
}

// ── Scan-Tuning Sandbox ──
function LabSandbox() {
  return (
    <div className="lab-card">
      <div className="lab-card-h mono">SCAN-TUNING SANDBOX · ⚠ off-production · does not affect live bundle</div>
      <div className="lab-knobs">
        <LabKnob k="Score floor (BUY)" v="65" sub="↑ fewer, higher-conviction" />
        <LabKnob k="Wilson LB gate" v="45%" sub="↑ stricter edge proof" />
        <LabKnob k="R:R floor" v="3.0" sub="asymmetry minimum" />
        <LabKnob k="Min RVOL" v="1.30×" sub="breakout confirmation" />
        <LabKnob k="Max correl-to-book" v="0.55" sub="diversification cap" />
        <LabKnob k="Regime cap (panic)" v="0%" sub="hard no-trade" />
      </div>
      <div className="lab-sandbox-out">
        <LabStat k="Names passing" v="612 → 418" tone="amb" sub="at current knobs" />
        <LabStat k="Backtest Sharpe" v="2.1 → 2.4" tone="gn" sub="stricter = better OOS" />
        <LabStat k="Avg trades/wk" v="14 → 9" tone="ink" />
      </div>
      <div className="lab-actions">
        <button className="btn btn--primary">DRY-RUN BACKTEST</button>
        <button className="btn">SAVE PRESET</button>
        <button className="btn">PROMOTE TO STAGING</button>
      </div>
    </div>
  );
}

// helpers
function LabField({ k, v }) { return <div className="lab-field"><span className="mono dim2">{k}</span><span className="mono">{v}</span></div>; }
function LabStat({ k, v, tone, sub }) { return <div className="lab-stat"><div className="lab-stat-l mono dim2">{k}</div><div className={`lab-stat-v mono kpi-tone--${tone}`}>{v}</div>{sub && <div className="lab-stat-s mono dim2">{sub}</div>}</div>; }
function LabKnob({ k, v, sub }) { return <div className="lab-knob"><div className="lab-knob-k mono dim2">{k}</div><div className="lab-knob-v mono copper">{v}</div><div className="lab-knob-s mono dim2">{sub}</div></div>; }

window.SurfaceLab = SurfaceLab;
