// surface-social.jsx — Social Sentiment surface · REDESIGN v2 (quant-grade, divergence-led)
// Headline idea: social is a CONTRARIAN input. The hero is a sentiment × price
// divergence map; the leaderboard is sorted by divergence (the alpha), not raw mentions.
const { useState: useSocS, useMemo: useSocM } = React;

// ── enriched universe ──────────────────────────────────────────────
// sent      crowd tone  −1..+1
// sentPct   percentile of THIS name's own 90d sentiment history (extremity)
// d24       24h tone change
// px5        5-day price strength (%)  ← the price dimension the old screen lacked
// pxPct     percentile of 5d price strength vs universe
// mult      mention volume as a multiple of the name's own 30d baseline
// vel        24h mention velocity
// src        [reddit, x, stocktwits] share %
// crowd     who is driving it: retail / mixed / pro
// trend     16-pt sentiment trajectory (for sparkline)
function socGen(end, start, n = 16, jit = 0.05) {
  const a = []; for (let i = 0; i < n; i++) { const t = i / (n - 1); a.push(start + (end - start) * t + (Math.sin(i * 1.7) * jit)); } return a;
}
const SOC_RAW = [
  { sym:"GRVT", name:"Graviton AI",        sector:"Software",    sent:+0.66, sentPct:94, d24:+0.41, px5:-1.2, pxPct:42, mentions:5120, mult:4.6, vel:+88, src:[52,38,10], crowd:"retail",
    read:"Most-hyped name on the tape, and price won't confirm — peak crowding. Classic blow-off; fade strength, don't chase." },
  { sym:"ARGN", name:"Argentum Robotics",  sector:"Industrials", sent:+0.62, sentPct:88, d24:+0.18, px5:+5.2, pxPct:90, mentions:4820, mult:3.1, vel:+38, src:[40,46,14], crowd:"mixed",
    read:"Sentiment and tape aligned and extreme — momentum confirm. Trail risk; late-stage crowding." },
  { sym:"VELO", name:"Velocity Motors",    sector:"Autos",       sent:+0.58, sentPct:86, d24:+0.22, px5:+2.1, pxPct:68, mentions:4210, mult:2.9, vel:+44, src:[44,42,14], crowd:"mixed" },
  { sym:"GENO", name:"Genoa Biosystems",   sector:"Biotech",     sent:+0.55, sentPct:91, d24:+0.31, px5:-3.1, pxPct:24, mentions:3640, mult:4.2, vel:+74, src:[58,34,8],  crowd:"retail",
    read:"Crowd euphoric while the tape rolls over — textbook distribution. Strength is for selling, not chasing." },
  { sym:"NMBS", name:"Nimbus Cloud",       sector:"Software",    sent:+0.36, sentPct:70, d24:+0.11, px5:+3.8, pxPct:82, mentions:3120, mult:2.1, vel:+19, src:[25,58,17], crowd:"mixed" },
  { sym:"HELX", name:"Helix Therapeutics", sector:"Biotech",     sent:+0.49, sentPct:84, d24:+0.27, px5:-2.4, pxPct:30, mentions:2980, mult:3.4, vel:+52, src:[55,33,12], crowd:"retail",
    read:"Crowd loading a name the tape is rejecting — wide divergence. Treat rallies as exits until price turns." },
  { sym:"QBIT", name:"Quanta Systems",     sector:"Semis",       sent:+0.47, sentPct:80, d24:+0.29, px5:+5.9, pxPct:92, mentions:2730, mult:3.6, vel:+61, src:[40,46,14], crowd:"retail" },
  { sym:"BIVO", name:"Bivota Pharma",      sector:"Biotech",     sent:-0.51, sentPct:8,  d24:-0.34, px5:+0.6, pxPct:55, mentions:2470, mult:3.8, vel:+41, src:[64,28,8],  crowd:"retail",
    read:"Bearish chatter spiking while price holds the line — squeeze watch. Fade the panic, don't join it." },
  { sym:"ARCM", name:"Arclight Materials", sector:"Materials",   sent:+0.41, sentPct:66, d24:+0.09, px5:+1.4, pxPct:62, mentions:2110, mult:1.6, vel:+12, src:[30,50,20], crowd:"mixed",
    read:"Mild bullish bias confirmed by a constructive tape — in-trend, nothing extreme. Standard continuation." },
  { sym:"MERC", name:"Mercia Semi",        sector:"Semis",       sent:-0.38, sentPct:14, d24:-0.22, px5:+2.6, pxPct:74, mentions:1890, mult:1.4, vel:+9,  src:[22,60,18], crowd:"pro",
    read:"Crowd bearish into a rising tape — disbelief rally. Short fuel for a squeeze, not a short." },
  { sym:"MAPL", name:"Maple Retail",       sector:"Consumer",    sent:-0.47, sentPct:10, d24:-0.26, px5:+0.9, pxPct:56, mentions:1760, mult:2.8, vel:+29, src:[60,30,10], crowd:"retail",
    read:"Retail piling into shorts while price refuses to break — squeeze fuel building. Don't add to the bear case here." },
  { sym:"PALA", name:"Palatine Energy",    sector:"Energy",      sent:+0.44, sentPct:78, d24:+0.19, px5:-1.8, pxPct:38, mentions:1640, mult:2.7, vel:+33, src:[48,38,14], crowd:"retail" },
  { sym:"TANG", name:"Tangent Networks",   sector:"Software",    sent:-0.34, sentPct:17, d24:-0.15, px5:+4.1, pxPct:86, mentions:1450, mult:1.6, vel:+14, src:[24,56,20], crowd:"pro",
    read:"Strong tape, doubtful crowd — the widest squeeze setup on the board. Bears are the fuel." },
  { sym:"LUMA", name:"Lumina Display",     sector:"Tech",        sent:+0.39, sentPct:72, d24:+0.14, px5:+1.0, pxPct:58, mentions:1390, mult:1.9, vel:+16, src:[34,46,20], crowd:"mixed" },
  { sym:"VANTA",name:"Vanta Logistics",    sector:"Transports",  sent:-0.44, sentPct:11, d24:-0.12, px5:-5.5, pxPct:6,  mentions:1320, mult:1.9, vel:+6,  src:[36,40,24], crowd:"mixed",
    read:"Crowd bearish and tape confirming weakness — no edge. Sentiment merely echoes price. Avoid." },
  { sym:"CRYO", name:"Cryotech Labs",      sector:"Biotech",     sent:+0.33, sentPct:64, d24:+0.06, px5:-0.9, pxPct:47, mentions:1180, mult:1.3, vel:+8,  src:[38,40,22], crowd:"retail" },
  { sym:"SOLA", name:"Solara Energy",      sector:"Energy",      sent:-0.41, sentPct:13, d24:-0.19, px5:-4.8, pxPct:9,  mentions:1020, mult:1.5, vel:+7,  src:[34,42,24], crowd:"mixed" },
  { sym:"DRSH", name:"Druseh Energy",      sector:"Energy",      sent:+0.28, sentPct:61, d24:+0.04, px5:-4.2, pxPct:14, mentions:980,  mult:1.2, vel:-3,  src:[20,38,42], crowd:"retail",
    read:"Bag-holder hope: crowd still bullish as price bleeds. Divergence says fade the bounce." },
  { sym:"THRM", name:"Thermo Dynamics",    sector:"Industrials", sent:-0.31, sentPct:19, d24:-0.09, px5:+2.8, pxPct:76, mentions:930,  mult:1.3, vel:+6,  src:[28,50,22], crowd:"pro" },
  { sym:"ORYX", name:"Oryx Mining",        sector:"Materials",   sent:-0.29, sentPct:22, d24:-0.08, px5:-3.6, pxPct:16, mentions:870,  mult:1.1, vel:+4,  src:[30,40,30], crowd:"mixed" },
  { sym:"ZEPH", name:"Zephyr Air",         sector:"Transports",  sent:-0.36, sentPct:16, d24:-0.13, px5:-3.9, pxPct:12, mentions:810,  mult:1.4, vel:+5,  src:[32,42,26], crowd:"mixed" },
  { sym:"KOSM", name:"Kosmos Compute",     sector:"Semis",       sent:+0.18, sentPct:58, d24:+0.21, px5:+6.8, pxPct:96, mentions:760,  mult:2.4, vel:+27, src:[28,54,18], crowd:"pro",
    read:"Price leading sentiment — pros early, crowd not yet loud. Often the cleanest confirm setups." },
  { sym:"AXIO", name:"Axiom Defense",      sector:"Defense",     sent:-0.22, sentPct:28, d24:-0.05, px5:+1.2, pxPct:60, mentions:740,  mult:1.2, vel:+5,  src:[26,52,22], crowd:"pro" },
  { sym:"IONX", name:"Ionix Power",        sector:"Utilities",   sent:+0.27, sentPct:60, d24:+0.05, px5:+3.2, pxPct:78, mentions:690,  mult:1.4, vel:+11, src:[22,48,30], crowd:"pro" },
  { sym:"FERA", name:"Fera Foods",         sector:"Consumer",    sent:+0.21, sentPct:56, d24:+0.03, px5:+0.4, pxPct:52, mentions:560,  mult:1.0, vel:+2,  src:[30,40,30], crowd:"mixed" },
];
// templated read for names without a curated one
function socReadAuto(r) {
  const k = socQuad(r).k, dv = socDiv(r);
  if (k === "fade")    return `Crowd ${r.sent > 0.45 ? "euphoric" : "leaning bullish"} while the tape lags (+${dv} gap) — treat strength as a fade until price confirms.`;
  if (k === "squeeze") return `Bearish chatter into a firm tape (${dv} gap) — disbelief setup. Short fuel for a squeeze, not a short.`;
  if (k === "confirm") return `Sentiment and price aligned${r.pxPct > r.sentPct ? ", price out front" : ""} — in-trend continuation, no contrarian edge.`;
  return `Crowd bearish and price confirming weakness — sentiment merely echoes the tape. No edge.`;
}

// quadrant from raw signs of sentiment & price
function socQuad(r) {
  if (r.sent >= 0 && r.px5 >= 0) return { k:"confirm", tone:"gn",  label:"CONFIRM" };
  if (r.sent >= 0 && r.px5 <  0) return { k:"fade",    tone:"rd",  label:"FADE" };
  if (r.sent <  0 && r.px5 >= 0) return { k:"squeeze", tone:"amb", label:"SQUEEZE" };
  return { k:"avoid", tone:"ink", label:"AVOID" };
}
// plain-language definition of each setup — surfaced as tooltips + a legend
const SOC_SETUP_DEF = {
  confirm: { tone:"gn",  what:"Crowd bullish + price rising",   read:"Sentiment confirms the trend — in-trend continuation, no contrarian edge." },
  fade:    { tone:"rd",  what:"Crowd bullish but price falling", read:"Crowd is ahead of the tape — treat strength as a fade until price confirms." },
  squeeze: { tone:"amb", what:"Crowd bearish but price rising",  read:"Disbelief rally — the crowd's shorts are squeeze fuel, not a short signal." },
  avoid:   { tone:"ink", what:"Crowd bearish + price falling",   read:"Sentiment just echoes the tape — no divergence, no edge." },
};
const socTagTip = k => `${k.toUpperCase()} · ${SOC_SETUP_DEF[k].what}. ${SOC_SETUP_DEF[k].read}`;
// signed divergence: how far crowd tone sits ABOVE/BELOW where price says it should
const socDiv = r => r.sentPct - r.pxPct;

const SOC_UNIV = SOC_RAW.map(r => ({ ...r, read: r.read || socReadAuto(r), trend: socGen(r.sent, r.sent - r.d24 * 1.6) }));

// ── inline sparkline (no load-order dependency) ─────────────────────
function SocSpark({ data, tone, w = 64, h = 22 }) {
  const min = Math.min(...data), max = Math.max(...data), r = (max - min) || 1;
  const x = i => (i / (data.length - 1)) * w;
  const y = v => h - ((v - min) / r) * (h - 4) - 2;
  const pts = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const gid = `ss-${Math.random().toString(36).slice(2, 7)}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display:"block" }}>
      <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={`var(--${tone})`} stopOpacity="0.30" /><stop offset="100%" stopColor={`var(--${tone})`} stopOpacity="0" />
      </linearGradient></defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill={`url(#${gid})`} />
      <polyline points={pts} fill="none" stroke={`var(--${tone})`} strokeWidth="1.5" />
      <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r="2" fill={`var(--${tone})`} />
    </svg>
  );
}

// ── divergence scatter (the hero) ───────────────────────────────────
function SocScatter({ rows, onTicker, hover, setHover }) {
  const W = 680, H = 300, padL = 40, padR = 16, padT = 22, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  const XMAX = 7, YMAX = 0.72;                    // tightened so dots fill the frame
  const px = v => padL + ((Math.max(-XMAX, Math.min(XMAX, v)) + XMAX) / (2 * XMAX)) * iw;
  const py = v => padT + (1 - (Math.max(-YMAX, Math.min(YMAX, v)) + YMAX) / (2 * YMAX)) * ih;
  const cx0 = px(0), cy0 = py(0);
  const x1 = px(XMAX), y1 = py(-YMAX);
  const maxM = Math.max(...rows.map(r => r.mentions));
  const rad = m => 5 + (m / maxM) * 9;
  const quadFill = { gn:"var(--gn)", rd:"var(--rd)", amb:"var(--amb)", ink:"var(--ink-3)" };
  // with a full universe, only label the most-divergent names (+ hovered) to avoid clutter
  const labelSet = new Set([...rows].sort((a, b) => Math.abs(socDiv(b)) - Math.abs(socDiv(a))).slice(0, 9).map(r => r.sym));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="sx-scatter-svg" preserveAspectRatio="xMidYMid meet">
      {/* quadrant tints (faint) */}
      <rect x={cx0} y={padT}  width={x1-cx0} height={cy0-padT} fill="var(--gn)"   opacity="0.045" />
      <rect x={padL} y={padT} width={cx0-padL} height={cy0-padT} fill="var(--rd)" opacity="0.05" />
      <rect x={cx0} y={cy0}   width={x1-cx0} height={y1-cy0}   fill="var(--amb)"  opacity="0.045" />
      <rect x={padL} y={cy0}  width={cx0-padL} height={y1-cy0} fill="var(--ink-4)" opacity="0.06" />
      {/* frame + axes */}
      <rect x={padL} y={padT} width={iw} height={ih} fill="none" stroke="var(--glass-line)" strokeWidth="1" />
      <line x1={padL} y1={cy0} x2={x1} y2={cy0} stroke="var(--glass-line-2)" strokeWidth="1" strokeDasharray="3 3" />
      <line x1={cx0} y1={padT} x2={cx0} y2={y1} stroke="var(--glass-line-2)" strokeWidth="1" strokeDasharray="3 3" />
      {/* corner quadrant tags — word only, clean */}
      <text x={x1-7}   y={padT+14} textAnchor="end"   className="sx-q-lbl" fill="var(--gn)">CONFIRM</text>
      <text x={padL+7} y={padT+14} textAnchor="start" className="sx-q-lbl" fill="var(--rd)">FADE</text>
      <text x={x1-7}   y={y1-8}    textAnchor="end"   className="sx-q-lbl" fill="var(--amb)">SQUEEZE</text>
      <text x={padL+7} y={y1-8}    textAnchor="start" className="sx-q-lbl" fill="var(--ink-3)">AVOID</text>
      {/* axis scale ticks */}
      <text x={padL+2} y={y1+11} textAnchor="start" className="sx-ax">−{XMAX}%</text>
      <text x={cx0} y={y1+11} textAnchor="middle" className="sx-ax">5D PRICE</text>
      <text x={x1-2} y={y1+11} textAnchor="end" className="sx-ax">+{XMAX}%</text>
      <text x={padL-5} y={padT+8} textAnchor="end" className="sx-ax">bull</text>
      <text x={padL-5} y={y1} textAnchor="end" className="sx-ax">bear</text>
      {/* dots */}
      {rows.map(r => {
        const q = socQuad(r), cx = px(r.px5), cy = py(r.sent), rr = rad(r.mentions);
        const on = hover === r.sym;
        const right = cx < x1 - 64;
        const nearTop = cy < padT + 26, nearBot = cy > y1 - 22;
        const lx = right ? cx + rr + 4 : cx - rr - 4;
        const ly = nearTop ? cy + rr + 11 : nearBot ? cy - rr - 6 : cy + 3.4;
        return (
          <g key={r.sym} style={{ cursor:"pointer" }} onClick={() => onTicker(r.sym)}
             onMouseEnter={() => setHover(r.sym)} onMouseLeave={() => setHover(null)} opacity={hover && !on ? 0.35 : 1}>
            <circle cx={cx} cy={cy} r={rr} fill={quadFill[q.tone]} opacity={on ? 0.34 : 0.2} />
            <circle cx={cx} cy={cy} r={rr} fill="none" stroke={quadFill[q.tone]} strokeWidth={on ? 1.8 : 1.3}
                    style={{ filter: on ? `drop-shadow(0 0 6px ${quadFill[q.tone]})` : "none" }} />
            <circle cx={cx} cy={cy} r="1.8" fill={quadFill[q.tone]} />
            {(labelSet.has(r.sym) || on) && (
              <text x={lx} y={ly} textAnchor={right ? "start" : "end"}
                    className="sx-dot-lbl" fill={on ? "var(--ink)" : "var(--ink-2)"} fontWeight={on ? 700 : 500}>{r.sym}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── ranked diverging-bar view — every name labeled, sorted by divergence ──
function SocRanked({ rows, onTicker, hover, setHover }) {
  const ranked = [...rows].sort((a, b) => socDiv(b) - socDiv(a));
  const cap = Math.max(...rows.map(r => Math.abs(socDiv(r))), 1);
  return (
    <div className="sx-rank">
      <div className="sx-rank-axis"><span className="dn">◂ crowd ahead of tape · FADE</span><span className="dim">divergence</span><span className="up">price ahead · SQUEEZE/CONFIRM ▸</span></div>
      {ranked.map(r => {
        const q = socQuad(r), dv = socDiv(r), on = hover === r.sym;
        const w = (Math.abs(dv) / cap) * 50;
        return (
          <div key={r.sym} className={`sx-rank-row ${on ? "is-hot" : ""}`} onClick={() => onTicker(r.sym)}
               onMouseEnter={() => setHover(r.sym)} onMouseLeave={() => setHover(null)}>
            <span className="sx-rank-sym mono"><b>{r.sym}</b></span>
            <span className={`sx-tag sx-tag--${q.tone} sx-rank-tag`} title={socTagTip(q.k)}>{q.label}</span>
            <span className="sx-rank-bar">
              <i className={`sx-bar-f ${dv >= 0 ? "kpi-tone-bg--rd" : "kpi-tone-bg--gn"}`} style={{ width:`${w}%`, left:dv >= 0 ? "50%" : `${50 - w}%` }} />
              <b className="sx-bar-ax" />
            </span>
            <span className={`sx-rank-v mono ${dv >= 0 ? "dn" : "up"}`}>{dv >= 0 ? "+" : ""}{dv}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── heatmap view — sector-grouped tiles, colored by divergence, sized by mentions ──
function SocHeatmap({ rows, onTicker, hover, setHover }) {
  const cap = Math.max(...rows.map(r => Math.abs(socDiv(r))), 1);
  const maxM = Math.max(...rows.map(r => r.mentions));
  const bySector = {};
  rows.forEach(r => { (bySector[r.sector] = bySector[r.sector] || []).push(r); });
  const sectors = Object.entries(bySector)
    .map(([s, items]) => ({ s, items: [...items].sort((a, b) => Math.abs(socDiv(b)) - Math.abs(socDiv(a))), m: items.reduce((a, r) => a + r.mentions, 0) }))
    .sort((a, b) => b.m - a.m);
  const tint = r => {
    const dv = socDiv(r), t = Math.min(1, Math.abs(dv) / cap);
    if (Math.abs(dv) < 8) return `color-mix(in oklab, var(--ink-4) ${18 + t * 10}%, var(--glass-bg-2))`;
    const c = dv > 0 ? "var(--rd)" : "var(--gn)";
    return `color-mix(in oklab, ${c} ${16 + t * 50}%, var(--glass-bg-2))`;
  };
  return (
    <div className="sx-heat">
      <div className="sx-heat-legend mono">
        <span className="dn">■ crowd ahead · fade</span>
        <span className="dim">■ in line</span>
        <span className="up">■ price ahead · squeeze / confirm</span>
        <span className="sx-heat-legend-sz dim2">tile ∝ mentions</span>
      </div>
      <div className="sx-heat-grid">
        {sectors.map(({ s, items, m }) => (
          <div key={s} className="sx-heat-sector" style={{ flexGrow: Math.max(1, Math.round(m / maxM * 4)) }}>
            <div className="sx-heat-sec-h mono">{s}<span className="dim2">{(m / 1000).toFixed(1)}k</span></div>
            <div className="sx-heat-tiles">
              {items.map(r => {
                const dv = socDiv(r), q = socQuad(r), on = hover === r.sym;
                return (
                  <div key={r.sym} className={`sx-heat-tile ${on ? "is-hot" : ""}`} title={`${r.name} · ${q.label} · divergence ${dv >= 0 ? "+" : ""}${dv}`}
                       style={{ background: tint(r), flexGrow: Math.max(1, Math.round(r.mentions / maxM * 6)), borderColor: on ? "var(--ink-1)" : "transparent" }}
                       onClick={() => onTicker(r.sym)} onMouseEnter={() => setHover(r.sym)} onMouseLeave={() => setHover(null)}>
                    <span className="mono sx-heat-sym">{r.sym}</span>
                    <span className={`mono sx-heat-dv ${dv >= 0 ? "dn" : "up"}`}>{dv >= 0 ? "+" : ""}{dv}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SurfaceSocial({ onTicker, tabs }) {
  const [view, setView] = useSocS("map");                   // map · ranked · heatmap
  const [sort, setSort] = useSocS({ col:"div", dir:-1 });   // default: most-divergent first
  const [hover, setHover] = useSocS(null);
  const net = SOC_UNIV.reduce((a, r) => a + r.sent, 0) / SOC_UNIV.length;
  const breadth = Math.round(SOC_UNIV.filter(r => r.sent >= 0).length / SOC_UNIV.length * 100);
  const fadeN = SOC_UNIV.filter(r => socQuad(r).k === "fade").length;
  const squeezeN = SOC_UNIV.filter(r => socQuad(r).k === "squeeze").length;
  const velLead = [...SOC_UNIV].sort((a, b) => b.vel - a.vel)[0];
  const totalMentions = SOC_UNIV.reduce((a, r) => a + r.mentions, 0);

  const rows = useSocM(() => {
    const get = (r) => sort.col === "div" ? socDiv(r) : sort.col === "quad" ? socQuad(r).k : r[sort.col];
    return [...SOC_UNIV].sort((a, b) => {
      const va = get(a), vb = get(b);
      const v = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
      return v * sort.dir;
    });
  }, [sort]);
  const setS = c => setSort(s => ({ col:c, dir:s.col === c ? -s.dir : -1 }));
  const arrow = c => sort.col === c ? (sort.dir > 0 ? " ▲" : " ▼") : "";

  const cols = [["sym","Name"],["quad","Setup"],["sent","Crowd tone"],["trend","14d"],["px5","5d price"],["div","Divergence"],["mult","Vol ×base"],["vel","Velocity"],["crowd","Driven by"]];

  return (
    <div className="surface sx-surface">
      {/* header */}
      <div className="sx-hdr">
        <div>
          <div className="sx-eyebrow">SOCIAL SENTIMENT · CROWD POSITIONING</div>
          <h1 className="sx-title">Crowd net <span className={net >= 0 ? "up" : "dn"}>{net >= 0 ? "+" : ""}{net.toFixed(2)}</span>
            <span className="sx-title-div"> · </span>
            <span className="sx-title-sub">{breadth}% of names net-bullish · read as a <span className="amb">contrarian</span> input</span>
          </h1>
        </div>
        <div className="sx-hdr-r">
          <FreshnessPill state="live" age="42s" />
          <div className="sx-prov">Reddit · X · StockTwits · spam-filtered (18%) · velocity-weighted</div>
        </div>
      </div>

      {tabs}

      {/* KPI strip */}
      <div className="sx-kpis">
        <SxKpi tone="amb"    l="DIVERGENCE ALERTS" v={fadeN + squeezeN} s={`${fadeN} fade · ${squeezeN} squeeze`} big />
        <SxKpi tone={net >= 0 ? "gn" : "rd"} l="NET TONE" v={`${net >= 0 ? "+" : ""}${net.toFixed(2)}`} s={`breadth ${breadth}%`} />
        <SxKpi tone="cy"     l="VELOCITY LEADER" v={velLead.sym} s={`+${velLead.vel}% mentions 24h`} />
        <SxKpi tone="violet" l="MENTIONS 24h" v={`${(totalMentions / 1000).toFixed(1)}k`} s="+28% vs 7d avg" />
        <SxKpi tone="ink"    l="BOT-FILTERED" v="18%" s="spam removed pre-score" />
      </div>

      {/* hero: scatter + reads */}
      <div className="sx-hero">
        <div className="sx-card sx-scatter">
          <div className="sx-card-h">CROWD × TAPE DIVERGENCE {view === "map" ? "MAP" : view === "ranked" ? "RANK" : "HEATMAP"}
            <span className="sx-card-sub">{view === "map" ? "where the crowd sits vs. where price is going · bubble = mentions · click to open" : view === "ranked" ? "every name, sorted by crowd-vs-tape gap · click to open" : "grouped by sector · tile size = mentions · color = divergence · click to open"}</span>
            <span className="sx-seg">
              <button className={view === "map" ? "is-on" : ""} onClick={() => setView("map")}>Map</button>
              <button className={view === "ranked" ? "is-on" : ""} onClick={() => setView("ranked")}>Ranked</button>
              <button className={view === "heatmap" ? "is-on" : ""} onClick={() => setView("heatmap")}>Heatmap</button>
            </span>
          </div>
          {view === "map"
            ? <SocScatter rows={SOC_UNIV} onTicker={onTicker} hover={hover} setHover={setHover} />
            : view === "ranked"
            ? <SocRanked rows={SOC_UNIV} onTicker={onTicker} hover={hover} setHover={setHover} />
            : <SocHeatmap rows={SOC_UNIV} onTicker={onTicker} hover={hover} setHover={setHover} />}
        </div>
        <div className="sx-reads">
          <div className="sx-card-h">ACTIONABLE READS</div>
          {[...SOC_UNIV].sort((a, b) => Math.abs(socDiv(b)) - Math.abs(socDiv(a))).slice(0, 4).map(r => {
            const q = socQuad(r);
            return (
              <div key={r.sym} className={`sx-read sx-read--${q.tone} ${hover === r.sym ? "is-hot" : ""}`}
                   onMouseEnter={() => setHover(r.sym)} onMouseLeave={() => setHover(null)}
                   onClick={() => onTicker(r.sym)}>
                <div className="sx-read-top">
                  <span className="sx-read-sym">{r.sym}</span>
                  <span className={`sx-tag sx-tag--${q.tone}`} title={socTagTip(q.k)}>{q.label}</span>
                  <span className={`sx-read-div mono ${socDiv(r) >= 0 ? "dn" : "up"}`}>{socDiv(r) >= 0 ? "+" : ""}{socDiv(r)}</span>
                </div>
                <div className="sx-read-txt">{r.read}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* leaderboard */}
      <div className="sx-card sx-tblwrap">
        <div className="sx-card-h">DIVERGENCE LEADERBOARD
          <span className="sx-card-sub">sorted by crowd-vs-tape gap — the contrarian alpha, not raw volume</span>
        </div>
        <div className="sx-setup-key">
          <span className="sx-setup-key-l mono dim2">SETUP</span>
          {["confirm","fade","squeeze","avoid"].map(k => (
            <span key={k} className="sx-setup-key-item" title={socTagTip(k)}>
              <span className={`sx-tag sx-tag--${SOC_SETUP_DEF[k].tone}`}>{k.toUpperCase()}</span>
              <span className="mono dim2">{SOC_SETUP_DEF[k].what}</span>
            </span>
          ))}
        </div>
        <table className="dtable sx-tbl">
          <thead><tr>
            {cols.map(([c, l]) => (
              <th key={c} className={["sent","px5","div","mult","vel"].includes(c) ? "r" : ""} onClick={() => setS(c)} style={{ cursor:"pointer" }}>{l}{arrow(c)}</th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map(r => {
              const q = socQuad(r), dv = socDiv(r);
              return (
                <tr key={r.sym} onClick={() => onTicker(r.sym)} onMouseEnter={() => setHover(r.sym)} onMouseLeave={() => setHover(null)}
                    className={hover === r.sym ? "is-hot" : ""} style={{ cursor:"pointer" }}>
                  <td><div className="sx-name"><b className="mono">{r.sym}</b><span className="dim sx-name-sub">{r.name} · {r.sector}</span></div></td>
                  <td><span className={`sx-tag sx-tag--${q.tone}`} title={socTagTip(q.k)}>{q.label}</span></td>
                  <td className="r">
                    <div className="sx-tone-cell">
                      <span className={`sx-pct sx-pct--${r.sentPct >= 80 || r.sentPct <= 20 ? "ext" : "norm"}`}>{r.sentPct >= 80 ? "P" + r.sentPct : r.sentPct <= 20 ? "P" + r.sentPct : "P" + r.sentPct}</span>
                      <span className="sx-bar"><i className={`sx-bar-f kpi-tone-bg--${r.sent >= 0 ? "gn" : "rd"}`} style={{ width:`${Math.abs(r.sent) * 50}%`, left:r.sent >= 0 ? "50%" : `${50 - Math.abs(r.sent) * 50}%` }} /><b className="sx-bar-ax" /></span>
                      <span className={`mono kpi-tone--${r.sent >= 0 ? "gn" : "rd"}`}>{r.sent >= 0 ? "+" : ""}{r.sent.toFixed(2)}</span>
                    </div>
                  </td>
                  <td><SocSpark data={r.trend} tone={r.sent >= 0 ? "gn" : "rd"} /></td>
                  <td className={`r mono ${r.px5 >= 0 ? "up" : "dn"}`}>{r.px5 >= 0 ? "+" : ""}{r.px5.toFixed(1)}%</td>
                  <td className="r">
                    <div className="sx-div-cell">
                      <span className="sx-bar sx-bar--wide"><i className={`sx-bar-f ${dv >= 0 ? "kpi-tone-bg--rd" : "kpi-tone-bg--gn"}`} style={{ width:`${Math.min(50, Math.abs(dv) / 1.4)}%`, left:dv >= 0 ? "50%" : `${50 - Math.min(50, Math.abs(dv) / 1.4)}%` }} /><b className="sx-bar-ax" /></span>
                      <span className={`mono ${dv >= 0 ? "dn" : "up"}`}>{dv >= 0 ? "+" : ""}{dv}</span>
                    </div>
                  </td>
                  <td className="r mono">{r.mult.toFixed(1)}×</td>
                  <td className={`r mono ${r.vel > 0 ? "up" : r.vel < 0 ? "dn" : "dim2"}`}>{r.vel > 0 ? "+" : ""}{r.vel}%</td>
                  <td><span className={`sx-crowd sx-crowd--${r.crowd}`}>{r.crowd}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="sx-foot">
          <span className="sx-foot-k">Divergence</span> = crowd-tone percentile − price-strength percentile.
          <span className="dn"> +ve</span> = crowd ahead of the tape (fade risk); <span className="up">−ve</span> = price ahead of the crowd (early confirm).
          Source provenance &amp; bot-scoring: social-feed aggregator, recomputed every 42s.
        </div>
      </div>
    </div>
  );
}

function SxKpi({ tone, l, v, s, big }) {
  return (
    <div className={`sx-kpi sx-kpi--${tone} ${big ? "sx-kpi--big" : ""}`}>
      <div className="sx-kpi-l">{l}</div>
      <div className={`sx-kpi-v mono kpi-tone--${tone}`}>{v}</div>
      <div className="sx-kpi-s">{s}</div>
    </div>
  );
}

window.SurfaceSocial = SurfaceSocial;
