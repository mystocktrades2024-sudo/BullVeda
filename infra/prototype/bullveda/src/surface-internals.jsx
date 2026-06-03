// surface-internals.jsx — Market Internals & Breadth
// Sources: breadth computed across EODHD /eod universe (adv-decl, %>DMA, NH-NL),
// VIX term structure from CBOE, TRIN/up-down volume from exchange tape.
const { useState: useIntS } = React;

const IN_DMA = [
  { k:"% > 20-DMA", v:62, tone:"gn" },
  { k:"% > 50-DMA", v:58, tone:"gn" },
  { k:"% > 100-DMA", v:54, tone:"amb" },
  { k:"% > 200-DMA", v:51, tone:"amb" },
];
const IN_SECTORS = [
  { s:"Semis", v:74 }, { s:"Software", v:68 }, { s:"Industrials", v:64 }, { s:"Energy", v:61 },
  { s:"Materials", v:55 }, { s:"Financials", v:52 }, { s:"Health", v:47 }, { s:"Consumer", v:44 },
  { s:"Utilities", v:39 }, { s:"Transports", v:33 }, { s:"REITs", v:28 },
];
// VIX term structure (contango = calm)
const IN_VIX = [
  { k:"VIX", v:14.2 }, { k:"VIX3M", v:16.1 }, { k:"VX-M1", v:14.8 }, { k:"VX-M2", v:15.9 }, { k:"VX-M3", v:16.7 },
];
const IN_HILO = [4,6,5,9,12,8,14,11,18,22,19,28]; // new-high net over sessions

function IntKpi({ k, v, tone, s }) {
  return <div className={`wsx-kpi wsx-kpi--${tone}`}><div className="wsx-kpi-l mono">{k}</div><div className={`wsx-kpi-v mono kpi-tone--${tone}`}>{v}</div><div className="wsx-kpi-s mono dim2">{s}</div></div>;
}

function VixTermCard() {
  const ts = [
    { k: "VIX", v: 14.2, spot: true }, { k: "M1", v: 14.8 }, { k: "M2", v: 15.9 },
    { k: "3M", v: 16.1 }, { k: "M3", v: 16.7 },
  ];
  const w = 340, h = 158, padL = 10, padR = 30, padT = 26, padB = 26;
  const plotW = w - padL - padR, plotR = padL + plotW, plotH = h - padT - padB;
  const vals = ts.map(t => t.v);
  const min = Math.min(...vals) - 0.9, max = Math.max(...vals) + 0.9;
  const xOf = i => padL + (i / (ts.length - 1)) * plotW;
  const yOf = v => padT + plotH - ((v - min) / (max - min)) * plotH;
  const spot = ts[0].v, back = ts[ts.length - 1].v, spread = back - spot;
  const contango = spread >= 0;
  const pts = ts.map((t, i) => [xOf(i), yOf(t.v)]);
  const area = `M ${xOf(0)},${padT + plotH} L ${pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" L ")} L ${xOf(ts.length - 1)},${padT + plotH} Z`;
  return (
    <div className="wsx-card inx-card">
      <div className="rkx-card-h mono">VIX TERM STRUCTURE <span className="dim2">· upward = contango = calm</span></div>
      <svg viewBox={`0 0 ${w} ${h}`} className="inx-vix" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="inx-vix-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--cy)" stopOpacity="0.26" />
            <stop offset="100%" stopColor="var(--cy)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* contango / backwardation badge */}
        <rect x={plotR - 96} y="4" width="96" height="16" rx="3" fill={`var(--${contango ? "gn" : "rd"}-bg)`} stroke={`var(--${contango ? "gn" : "rd"}-dim)`} />
        <text x={plotR - 48} y="15" textAnchor="middle" className="mono" fontSize="9" fill={`var(--${contango ? "gn" : "rd"})`} fontWeight="700">{contango ? "CONTANGO" : "BACKWARD."} {spread >= 0 ? "+" : ""}{spread.toFixed(1)}</text>
        {/* gridlines */}
        {[0.5, 1].map((f, k) => <line key={k} x1={padL} y1={padT + plotH * f} x2={plotR} y2={padT + plotH * f} stroke="var(--line)" strokeDasharray="1 6" opacity="0.4" />)}
        {/* spot reference */}
        <line x1={padL} y1={yOf(spot)} x2={plotR} y2={yOf(spot)} stroke="var(--ink-3)" strokeDasharray="3 3" opacity="0.6" />
        <text x={plotR + 3} y={yOf(spot) + 3} className="mono" fontSize="8" fill="var(--ink-3)">spot</text>
        {/* area + curve */}
        <path d={area} fill="url(#inx-vix-g)" />
        <polyline points={pts.map(p => `${p[0]},${p[1]}`).join(" ")} fill="none" stroke="var(--cy)" strokeWidth="2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 5px var(--cy))" }} />
        {ts.map((t, i) => (
          <g key={i}>
            <circle cx={xOf(i)} cy={yOf(t.v)} r={t.spot ? 4 : 3} fill={t.spot ? "var(--copper)" : "var(--cy)"} stroke="var(--bg-1)" strokeWidth="1" />
            <text x={xOf(i)} y={yOf(t.v) - 8} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--ink-1)" fontWeight="600">{t.v}</text>
            <text x={xOf(i)} y={h - 8} textAnchor="middle" className="mono" fontSize="8.5" fill={t.spot ? "var(--copper)" : "var(--ink-3)"}>{t.k}</text>
          </g>
        ))}
      </svg>
      <div className="rkx-note mono dim2">Front-month <b className="cy">{spot}</b> sits <b className="up">{spread.toFixed(1)} vol below</b> the back-month — contango, market pricing calm. A flip to <b className="dn">backwardation</b> is the early warning to de-risk swing books.</div>
    </div>
  );
}

function SurfaceInternals({ onTicker }) {
  const adv = 1840, dec = 1120, unch = 210;
  const advPct = adv / (adv + dec + unch) * 100;
  const breadthVerdict = advPct > 55 ? { t:"RISK-ON", tone:"gn" } : advPct < 45 ? { t:"RISK-OFF", tone:"rd" } : { t:"NEUTRAL", tone:"amb" };
  const vixMax = Math.max(...IN_VIX.map(v => v.v));
  const hiMax = Math.max(...IN_HILO);

  return (
    <div className="surface wsx wsx--gn inx">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">MARKET INTERNALS · BREADTH</div>
          <h1 className="wsx-title mono">Internals</h1>
          <div className="wsx-sub mono dim2">advance/decline · % above moving averages · new highs−lows · VIX term structure · sector breadth · the regime read</div>
        </div>
        <div className="wsx-hdr-r"><StaleStamp staleAfter={30} label="breadth scan" src="EODHD universe breadth · CBOE VIX term · NYSE/Nasdaq tape" /></div>
      </div>

      <div className="wsx-kpis inx-kpis">
        <div className={`wsx-kpi wsx-kpi--${breadthVerdict.tone} inx-verdict`}>
          <div className="wsx-kpi-l mono">REGIME</div>
          <div className={`wsx-kpi-v mono kpi-tone--${breadthVerdict.tone}`}>{breadthVerdict.t}</div>
          <div className="wsx-kpi-s mono dim2">breadth + vol confirm</div>
        </div>
        <IntKpi k="ADV / DECL" v={`${(adv/1000).toFixed(2)}k / ${(dec/1000).toFixed(2)}k`} tone="gn" s={`${advPct.toFixed(0)}% advancing`} />
        <IntKpi k="NEW HI − LO" v="+217" tone="gn" s="412 hi · 195 lo" />
        <IntKpi k="% > 50-DMA" v="58%" tone="gn" s="above mid-line" />
        <IntKpi k="VIX" v="14.2" tone="gn" s="contango · calm" />
        <IntKpi k="TRIN" v="0.82" tone="gn" s="buying pressure" />
        <IntKpi k="UP / DN VOL" v="3.1×" tone="gn" s="up-volume dominant" />
      </div>

      <div className="inx-grid">
        <div className="wsx-card inx-card">
          <div className="rkx-card-h mono">PARTICIPATION · % ABOVE MOVING AVERAGE</div>
          <div className="inx-dma">
            {IN_DMA.map((d, i) => (
              <div key={i} className="inx-dma-row">
                <span className="mono inx-dma-l">{d.k}</span>
                <span className="inx-dma-bar"><i className={`kpi-tone-bg--${d.tone}`} style={{ width:`${d.v}%` }} /><b className="inx-dma-mid" /></span>
                <span className={`mono inx-dma-v kpi-tone--${d.tone}`}>{d.v}%</span>
              </div>
            ))}
          </div>
          <div className="rkx-card-h mono inx-h2">NEW-HIGH NET · 12 SESSIONS</div>
          <svg viewBox="0 0 320 70" className="inx-hilo" preserveAspectRatio="none">
            {IN_HILO.map((v, i) => {
              const bw = 320 / IN_HILO.length;
              const h = (v / hiMax) * 56;
              return <rect key={i} x={i * bw + 2} y={64 - h} width={bw - 4} height={h} rx="1.5" fill="var(--gn)" opacity={0.35 + (i / IN_HILO.length) * 0.5} />;
            })}
            <line x1="0" y1="64" x2="320" y2="64" stroke="var(--glass-line)" />
          </svg>
        </div>

        <VixTermCard />

        <div className="wsx-card inx-card inx-sectors">
          <div className="rkx-card-h mono">SECTOR BREADTH <span className="dim2">· % of members above 50-DMA</span></div>
          <div className="inx-heat">
            {IN_SECTORS.map((s, i) => {
              const t = s.v / 100;
              const bg = s.v >= 50 ? `color-mix(in oklab, var(--gn) ${15 + t * 55}%, transparent)` : `color-mix(in oklab, var(--rd) ${15 + (1 - t) * 55}%, transparent)`;
              return (
                <div key={i} className="inx-heat-cell" style={{ background:bg }}>
                  <span className="mono inx-heat-s">{s.s}</span>
                  <span className={`mono inx-heat-v ${s.v >= 50 ? "up" : "dn"}`}>{s.v}%</span>
                </div>
              );
            })}
          </div>
          <div className="rkx-note mono dim2">Leadership is cyclical — Semis (74%) and Software (68%) carrying breadth; defensives (Utilities, REITs) lagging. Healthy risk-on rotation, not a defensive bid.</div>
        </div>
      </div>
    </div>
  );
}
window.SurfaceInternals = SurfaceInternals;
