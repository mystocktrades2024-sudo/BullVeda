// surface-themes.jsx — Themes · narrative baskets with momentum + rotation.
// Two views: BASKETS (curated RS-weighted snapshot, period-toggled, top-10 drill)
// and ROTATION (RRG-style leadership map + ranked momentum-of-momentum table).
// Crowding flags surface names that sit in 2+ baskets (concentration risk).
// Data shaped as curated baskets + EODHD /eod multi-period + flow model.

const { useState: useThm, useMemo: useThmm } = React;

// Each basket: multi-period return (1W/1M/3M), RS rank now + 4-wk-ago (→ rotation),
// breadth now + prior (→ trend), net 5d flow ($M), and top-10 constituents [sym, 1D%, RS].
// Tickers are real; RS / breadth / flow figures are illustrative (curated-basket mock).
// `abbr` is the short tag used on the rotation map.
const THEME_BASKETS = [
  { k: "AI Power & Energy", tag: "utilities · gas turbines · fuel cells", tone: "amb", abbr: "PWR", members: 24, lead: "VST", flow: 1450,
    chg1w: +3.2, chg1m: +9.4, chg3m: +28.1, rs: 90, rsPrev: 82, breadth: 80, breadthPrev: 70,
    curve: [0, 1.5, 2.4, 3.8, 3.2, 5.6, 6.8, 8.4, 9.4],
    cons: [["VST", 2.1, 92], ["CEG", 1.8, 90], ["GEV", 2.6, 88], ["TLN", 1.4, 86], ["OKLO", 4.2, 83], ["VRT", 1.9, 81], ["BE", 3.1, 79], ["NEE", 0.6, 74], ["EOSE", 2.8, 58], ["AMPX", 3.4, 54]] },
  { k: "Semiconductors", tag: "logic · foundry · equipment", tone: "cy", abbr: "CHIP", members: 31, lead: "NVDA", flow: 2100,
    chg1w: +2.1, chg1m: +6.8, chg3m: +22.4, rs: 94, rsPrev: 90, breadth: 82, breadthPrev: 78,
    curve: [0, 1.8, 1.4, 3.2, 2.8, 4.4, 5.1, 6.2, 6.8],
    cons: [["NVDA", 2.4, 96], ["AVGO", 1.8, 93], ["TSM", 1.2, 90], ["AMD", 2.9, 86], ["ASML", 0.9, 84], ["MU", 3.2, 81], ["MRVL", 2.1, 82], ["LRCX", 1.4, 79], ["AMAT", 1.1, 77], ["ARM", 2.6, 75]] },
  { k: "Data Center Infrastructure", tag: "neoclouds · networking · cooling", tone: "blue", abbr: "DC", members: 28, lead: "ORCL", flow: 1680,
    chg1w: +3.8, chg1m: +11.2, chg3m: +34.0, rs: 88, rsPrev: 79, breadth: 76, breadthPrev: 68,
    curve: [0, 2.1, 3.4, 5.2, 4.6, 7.8, 9.1, 10.4, 11.2],
    cons: [["ORCL", 1.6, 88], ["ANET", 2.2, 85], ["VRT", 1.9, 83], ["ALAB", 3.4, 78], ["CRWV", 4.8, 80], ["NBIS", 3.9, 76], ["IREN", 5.2, 74], ["SMCI", 2.8, 72], ["CIFR", 4.1, 68], ["DLR", 0.8, 66]] },
  { k: "Hyperscalers & AI Models", tag: "platform owners · frontier labs", tone: "violet", abbr: "MODL", members: 18, lead: "MSFT", flow: 1920,
    chg1w: +1.4, chg1m: +4.6, chg3m: +15.2, rs: 84, rsPrev: 88, breadth: 72, breadthPrev: 75,
    curve: [0, 1.6, 2.8, 4.0, 3.4, 3.0, 3.8, 4.4, 4.6],
    cons: [["MSFT", 1.2, 86], ["GOOGL", 1.6, 84], ["META", 1.9, 82], ["AMZN", 1.4, 80], ["ORCL", 1.6, 78], ["AAPL", 0.7, 72], ["IBM", 0.9, 64], ["SAP", 0.6, 62], ["CRM", 1.1, 60], ["BIDU", 2.1, 55]] },
  { k: "AI Software & Apps", tag: "control · security · observability", tone: "gn", abbr: "APP", members: 34, lead: "PLTR", flow: 540,
    chg1w: -1.2, chg1m: +1.8, chg3m: +6.2, rs: 70, rsPrev: 76, breadth: 54, breadthPrev: 61,
    curve: [0, 1.4, 2.6, 3.4, 2.8, 2.2, 1.9, 1.8, 1.8],
    cons: [["PLTR", 2.8, 84], ["CRWD", 1.6, 75], ["NET", 2.1, 73], ["NOW", 1.2, 72], ["PANW", 1.1, 70], ["SHOP", 1.4, 68], ["DDOG", -0.8, 64], ["SNOW", -1.2, 60], ["TEAM", -0.9, 58], ["MDB", -1.6, 55]] },
  { k: "Critical Minerals", tag: "rare earths · lithium · antimony", tone: "copper", abbr: "MIN", members: 22, lead: "MP", flow: 880,
    chg1w: +5.4, chg1m: +14.2, chg3m: +41.0, rs: 86, rsPrev: 71, breadth: 70, breadthPrev: 55,
    curve: [0, 2.6, 4.8, 6.2, 8.4, 10.1, 12.0, 13.4, 14.2],
    cons: [["MP", 4.6, 90], ["USAR", 6.2, 84], ["UUUU", 5.1, 80], ["UEC", 4.4, 78], ["ALB", 2.1, 66], ["LAC", 3.2, 64], ["UAMY", 7.8, 62], ["TMC", 5.6, 58], ["CRML", 6.4, 56], ["SGML", 2.8, 54]] },
  { k: "Nuclear & SMR", tag: "reactors · enrichment · uranium", tone: "amb", abbr: "NUC", members: 16, lead: "OKLO", flow: 760,
    chg1w: +4.1, chg1m: +12.6, chg3m: +38.4, rs: 91, rsPrev: 84, breadth: 74, breadthPrev: 66,
    curve: [0, 2.2, 4.1, 6.0, 7.4, 9.2, 10.8, 12.0, 12.6],
    cons: [["OKLO", 4.2, 91], ["CEG", 1.8, 88], ["SMR", 3.8, 86], ["VST", 2.1, 84], ["LEU", 5.2, 82], ["CCJ", 1.4, 80], ["BWXT", 1.1, 76], ["UEC", 4.4, 74], ["NNE", 6.1, 70], ["UUUU", 5.1, 68]] },
  { k: "Memory & Storage", tag: "DRAM · NAND · HDD · arrays", tone: "cy", abbr: "MEM", members: 19, lead: "MU", flow: 620,
    chg1w: +4.8, chg1m: +13.1, chg3m: +29.0, rs: 79, rsPrev: 64, breadth: 68, breadthPrev: 52,
    curve: [0, 2.4, 4.6, 6.1, 8.0, 9.8, 11.4, 12.6, 13.1],
    cons: [["MU", 3.2, 88], ["WDC", 2.8, 82], ["STX", 2.1, 80], ["SMCI", 2.8, 76], ["SNDK", 4.1, 74], ["PSTG", 1.6, 72], ["DELL", 1.2, 68], ["NTAP", 0.9, 66], ["SIMO", 1.8, 58], ["HPE", 0.6, 54]] },
  { k: "Defense & Drones", tag: "primes · autonomy · C4ISR", tone: "gn", abbr: "DEF", members: 26, lead: "PLTR", flow: 410,
    chg1w: +1.8, chg1m: +3.4, chg3m: +9.6, rs: 57, rsPrev: 49, breadth: 58, breadthPrev: 51,
    curve: [0, 0.6, 1.4, 1.0, 2.0, 2.6, 3.0, 3.2, 3.4],
    cons: [["PLTR", 2.8, 78], ["KTOS", 3.2, 70], ["AVAV", 2.1, 66], ["ONDS", 6.4, 62], ["LDOS", 1.1, 58], ["RTX", 0.8, 56], ["OSS", 4.8, 54], ["LMT", 0.6, 52], ["NOC", 0.4, 50], ["GD", 0.5, 48]] },
  { k: "Quantum Computing", tag: "qubit · error-correction", tone: "blue", abbr: "QTM", members: 14, lead: "IONQ", flow: -120,
    chg1w: -3.6, chg1m: -6.2, chg3m: +11.8, rs: 48, rsPrev: 58, breadth: 40, breadthPrev: 52,
    curve: [0, 2.1, 1.4, 2.6, 0.8, -1.4, -3.2, -5.1, -6.2],
    cons: [["GOOGL", 1.6, 66], ["IBM", 0.9, 64], ["IONQ", -2.6, 58], ["HON", 0.4, 55], ["RGTI", -3.8, 52], ["QBTS", -4.2, 50], ["QUBT", -3.1, 46], ["ARQQ", -2.8, 42], ["LAES", -3.6, 40], ["QMCO", -5.1, 38]] },
  { k: "Space", tag: "launch · satellites · direct-to-cell", tone: "violet", abbr: "SPC", members: 21, lead: "RKLB", flow: 340,
    chg1w: +2.6, chg1m: +7.8, chg3m: +19.4, rs: 58, rsPrev: 47, breadth: 60, breadthPrev: 48,
    curve: [0, 1.2, 2.4, 3.6, 4.8, 6.0, 7.0, 7.6, 7.8],
    cons: [["RKLB", 3.2, 72], ["ASTS", 4.8, 68], ["FLY", 4.2, 62], ["LUNR", 3.6, 60], ["PL", 2.1, 58], ["RDW", 2.8, 54], ["BKSY", 3.1, 52], ["SATL", 5.1, 50], ["KULR", 2.4, 46], ["MNTS", 1.8, 42]] },
  { k: "Optical & Photonics", tag: "transceivers · lasers · interconnect", tone: "cy", abbr: "OPT", members: 23, lead: "COHR", flow: 510,
    chg1w: +3.1, chg1m: +9.8, chg3m: +26.2, rs: 82, rsPrev: 75, breadth: 70, breadthPrev: 62,
    curve: [0, 1.8, 3.4, 5.0, 6.2, 7.8, 8.9, 9.5, 9.8],
    cons: [["COHR", 2.6, 84], ["MRVL", 2.1, 82], ["LITE", 2.1, 80], ["FN", 1.4, 78], ["AAOI", 4.8, 74], ["CIEN", 1.6, 72], ["GLW", 0.9, 70], ["POET", 4.1, 56], ["AXTI", 3.8, 58], ["LWLG", 5.2, 54]] },
  { k: "Robotics & Automation", tag: "humanoids · industrial · surgical", tone: "copper", abbr: "ROB", members: 20, lead: "SYM", flow: 290,
    chg1w: +1.2, chg1m: +3.8, chg3m: +11.2, rs: 54, rsPrev: 47, breadth: 52, breadthPrev: 46,
    curve: [0, 0.8, 1.6, 2.2, 2.8, 3.2, 3.6, 3.7, 3.8],
    cons: [["TSLA", 2.6, 74], ["ISRG", 1.2, 72], ["AMZN", 1.4, 70], ["SYM", 3.8, 68], ["TER", 2.1, 66], ["SERV", 5.2, 64], ["ROK", 0.8, 58], ["NDSN", 0.6, 54], ["PATH", -1.4, 52], ["IRBT", 3.1, 44]] },
];

const PERIODS = [["chg1w", "1W"], ["chg1m", "1M"], ["chg3m", "3M"]];

// rotation quadrant — RS level (x) × RS momentum / 4-wk Δ (y), pivot at RS 65
function rotQuad(t) {
  const rsD = t.rs - t.rsPrev;
  const strong = t.rs >= 65, up = rsD >= 0;
  if (strong && up)  return { k: "leading",   tone: "gn",  label: "LEADING",   note: "ride · strongest + improving" };
  if (strong && !up) return { k: "weakening", tone: "amb", label: "WEAKENING", note: "trim · strong but rolling over" };
  if (!strong && up) return { k: "improving", tone: "cy",  label: "IMPROVING", note: "watch · basing, RS turning up" };
  return { k: "lagging", tone: "rd", label: "LAGGING", note: "avoid · weak + still falling" };
}

function ThemeSpark({ data, tone }) {
  const w = 200, h = 44, min = Math.min(...data, 0), max = Math.max(...data, 0.5);
  const x = i => (i / (data.length - 1)) * w, y = v => h - ((v - min) / (max - min || 1)) * (h - 4) - 2;
  const up = data[data.length - 1] >= 0;
  const c = up ? tone : "rd";
  const gid = `ts-${Math.random().toString(36).slice(2, 7)}`;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--${c})`} stopOpacity="0.25" /><stop offset="100%" stopColor={`var(--${c})`} stopOpacity="0" /></linearGradient></defs>
      <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
      <path d={`M 0 ${y(0)} L ${data.map((v, i) => `${x(i)},${y(v)}`).join(" L ")} L ${w} ${y(0)} Z`} fill={`url(#${gid})`} />
      <polyline points={data.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={`var(--${c})`} strokeWidth="1.6" />
    </svg>
  );
}

// breadth-trend chip: level + directional arrow
function BreadthTrend({ now, prev }) {
  const d = now - prev;
  const dir = d > 2 ? "up" : d < -2 ? "dn" : "dim2";
  const arr = d > 2 ? "▲" : d < -2 ? "▼" : "▸";
  return (
    <span className="mono"><span className="dim2">BREADTH</span> <b>{now}%</b> <span className={`q-bdelta ${dir}`}>{arr}{d >= 0 ? "+" : ""}{d}</span></span>
  );
}

// ── ROTATION: RRG-style leadership scatter ──────────────────────────
function ThemeRRG({ baskets, sel, onSelect }) {
  const W = 460, H = 360, pad = 36;
  const iw = W - pad * 2, ih = H - pad * 2;
  const XC = 65, XR = 33;       // RS centered at 65 (= quadrant pivot), ±33 → 32..98
  const YR = 16;                // RS Δ range ±16
  const px = v => pad + ((Math.max(XC - XR, Math.min(XC + XR, v)) - (XC - XR)) / (2 * XR)) * iw;
  const py = v => pad + (1 - (Math.max(-YR, Math.min(YR, v)) + YR) / (2 * YR)) * ih;
  const cx0 = px(XC), cy0 = py(0);
  const maxFlow = Math.max(...baskets.map(b => Math.abs(b.flow)), 1);
  const rad = f => 13 + (Math.abs(f) / maxFlow) * 10;
  const qFill = { leading: "var(--gn)", weakening: "var(--amb)", improving: "var(--cy)", lagging: "var(--rd)" };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="q-rrg-svg" preserveAspectRatio="xMidYMid meet">
      {/* quadrant tints */}
      <rect x={cx0} y={pad}  width={px(XC + XR) - cx0} height={cy0 - pad} fill="var(--gn)"  opacity="0.05" />
      <rect x={cx0} y={cy0}  width={px(XC + XR) - cx0} height={py(-YR) - cy0} fill="var(--amb)" opacity="0.05" />
      <rect x={pad} y={pad}  width={cx0 - pad} height={cy0 - pad} fill="var(--cy)" opacity="0.05" />
      <rect x={pad} y={cy0}  width={cx0 - pad} height={py(-YR) - cy0} fill="var(--rd)" opacity="0.06" />
      {/* frame + crosshair */}
      <rect x={pad} y={pad} width={iw} height={ih} fill="none" stroke="var(--glass-line)" />
      <line x1={cx0} y1={pad} x2={cx0} y2={py(-YR)} stroke="var(--glass-line-2)" strokeDasharray="3 3" />
      <line x1={pad} y1={cy0} x2={px(XC + XR)} y2={cy0} stroke="var(--glass-line-2)" strokeDasharray="3 3" />
      {/* quadrant labels */}
      <text x={px(XC + XR) - 8} y={pad + 15} textAnchor="end"   className="q-rrg-q" fill="var(--gn)">LEADING</text>
      <text x={pad + 8}        y={pad + 15} textAnchor="start" className="q-rrg-q" fill="var(--cy)">IMPROVING</text>
      <text x={px(XC + XR) - 8} y={py(-YR) - 8} textAnchor="end"   className="q-rrg-q" fill="var(--amb)">WEAKENING</text>
      <text x={pad + 8}        y={py(-YR) - 8} textAnchor="start" className="q-rrg-q" fill="var(--rd)">LAGGING</text>
      {/* axis labels */}
      <text x={(pad + px(XC + XR)) / 2} y={H - 8} textAnchor="middle" className="q-rrg-ax">→ RS rank (relative strength)</text>
      <text x={14} y={(pad + py(-YR)) / 2} textAnchor="middle" className="q-rrg-ax" transform={`rotate(-90 14 ${(pad + py(-YR)) / 2})`}>→ RS momentum (4-wk Δ)</text>
      {/* bubbles — abbreviation sits inside the dot so labels never collide */}
      {baskets.map(t => {
        const rsD = t.rs - t.rsPrev, q = rotQuad(t), cx = px(t.rs), cy = py(rsD), rr = rad(t.flow);
        const on = sel === t.k;
        return (
          <g key={t.k} style={{ cursor: "pointer" }} onClick={() => onSelect(t.k)}>
            <title>{`${t.k} · RS ${t.rs} (${rsD >= 0 ? "+" : ""}${rsD} 4w) · ${q.label}`}</title>
            <circle cx={cx} cy={cy} r={rr} fill={qFill[q.k]} opacity={on ? 0.34 : 0.16} />
            <circle cx={cx} cy={cy} r={rr} fill="none" stroke={qFill[q.k]} strokeWidth={on ? 2.2 : 1.4}
                    style={{ filter: on ? `drop-shadow(0 0 7px ${qFill[q.k]})` : "none" }} />
            <text x={cx} y={cy + 3.2} textAnchor="middle" className="q-rrg-lbl" fill={on ? "var(--ink)" : "var(--ink-1)"} fontWeight={on ? 800 : 700}>{t.abbr}</text>
          </g>
        );
      })}
    </svg>
  );
}

function ThemeRotation({ baskets, sel, onSelect, onTicker }) {
  const ranked = [...baskets].sort((a, b) => (b.rs - b.rsPrev) - (a.rs - a.rsPrev));
  const counts = baskets.reduce((m, t) => { const k = rotQuad(t).k; m[k] = (m[k] || 0) + 1; return m; }, {});
  const cur = baskets.find(t => t.k === sel) || baskets[0];
  const curQ = rotQuad(cur);
  return (
    <>
      <div className="q-kpis q-kpis--4">
        {[["LEADING", counts.leading || 0, "gn", "ride"], ["IMPROVING", counts.improving || 0, "cy", "watch for entry"],
          ["WEAKENING", counts.weakening || 0, "amb", "trim / tighten"], ["LAGGING", counts.lagging || 0, "rd", "avoid"]].map((k, i) => (
          <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
            <div className="q-kpi-l mono">{k[0]}</div>
            <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
            <div className="q-kpi-s mono dim2">{k[3]}</div>
          </div>
        ))}
      </div>

      <div className="q-rot-grid">
        <div className="lab-card">
          <div className="lab-card-h mono">ROTATION MAP · RS LEVEL × RS MOMENTUM <span className="dim2">· bubble ∝ net flow · click a theme</span></div>
          <ThemeRRG baskets={baskets} sel={sel} onSelect={onSelect} />
          <div className="q-rrg-note mono dim2">Clockwise drift is the normal lifecycle: <b className="cy">Improving</b> → <b className="up">Leading</b> → <b className="amb">Weakening</b> → <b className="dn">Lagging</b>. Capital is rotating <b className="up">into {ranked[0].k}</b> (RS +{ranked[0].rs - ranked[0].rsPrev}) and <b className="dn">out of {ranked[ranked.length - 1].k}</b>.</div>
        </div>

        <div className="lab-card">
          <div className="lab-card-h mono">MOMENTUM RANK · 4-WEEK Δ</div>
          <table className="dtable wsx-tbl q-rot-tbl">
            <thead><tr><th>Theme</th><th className="r">RS</th><th className="r">Δ 4w</th><th className="r">1M</th><th>Phase</th></tr></thead>
            <tbody>{ranked.map(t => {
              const rsD = t.rs - t.rsPrev, q = rotQuad(t);
              return (
                <tr key={t.k} className={sel === t.k ? "is-sel" : ""} onClick={() => onSelect(t.k)} style={{ cursor: "pointer" }}>
                  <td><b>{t.k}</b></td>
                  <td className="r mono tabular"><b>{t.rs}</b></td>
                  <td className={`r mono tabular ${rsD >= 0 ? "up" : "dn"}`}>{rsD >= 0 ? "▲+" : "▼"}{rsD}</td>
                  <td className={`r mono tabular ${t.chg1m >= 0 ? "up" : "dn"}`}>{t.chg1m >= 0 ? "+" : ""}{t.chg1m}%</td>
                  <td><span className={`q-phase q-phase--${q.k}`}>{q.label}</span></td>
                </tr>
              );
            })}</tbody>
          </table>
          <div className="q-rot-verdict mono dim2"><b className={`kpi-tone--${curQ.tone}`}>{cur.k} · {curQ.label}</b> — {curQ.note}. Trade phase, not just price: a Leading theme with breadth still expanding is the cleanest tailwind; a Weakening one is a distribution tell even while it prints green.</div>
        </div>
      </div>
    </>
  );
}

function SurfaceThemes({ onTicker }) {
  const [view, setView] = useThm("baskets");      // baskets · rotation
  const [period, setPeriod] = useThm("chg1m");
  const [sel, setSel] = useThm(THEME_BASKETS[0].k);
  const cur = THEME_BASKETS.find(t => t.k === sel) || THEME_BASKETS[0];
  const perLabel = PERIODS.find(p => p[0] === period)[1];

  // crowding map — which baskets each ticker appears in
  const crowd = useThmm(() => {
    const m = {};
    THEME_BASKETS.forEach(t => t.cons.forEach(c => { (m[c[0]] = m[c[0]] || []).push(t.k); }));
    return m;
  }, []);
  const crowdedCount = Object.values(crowd).filter(a => a.length >= 2).length;
  const hottest = [...THEME_BASKETS].sort((a, b) => b[period] - a[period])[0];
  const netFlow = THEME_BASKETS.reduce((a, t) => a + t.flow, 0);

  return (
    <div className="surface wsx wsx--violet q-themes">
      <div className="wsx-hdr">
        <div className="wsx-hdr-l">
          <div className="wsx-eyebrow mono">NARRATIVE BASKETS · MOMENTUM · RS-WEIGHTED</div>
          <h1 className="wsx-title mono">Themes</h1>
          <div className="wsx-sub mono dim2">curated baskets · multi-period return · relative strength · breadth trend · rotation map · crowding · drill to top-10</div>
        </div>
        <div className="wsx-hdr-r">
          <FreshnessPill state="live" age="eod + 18s" />
          <span className="mono dim2">src · curated baskets · EODHD /eod · flow model</span>
        </div>
      </div>

      <div className="lab-tabs q-tabs">
        <button className={`lab-tab ${view === "baskets" ? "is-on" : ""}`} onClick={() => setView("baskets")}>Baskets</button>
        <button className={`lab-tab ${view === "rotation" ? "is-on" : ""}`} onClick={() => setView("rotation")}>Rotation</button>
        {view === "baskets" && (
          <div className="seg q-period">
            {PERIODS.map(([id, l]) => <button key={id} className={`seg-btn ${period === id ? "is-on" : ""}`} onClick={() => setPeriod(id)}>{l}</button>)}
          </div>
        )}
      </div>

      {view === "rotation"
        ? <ThemeRotation baskets={THEME_BASKETS} sel={sel} onSelect={setSel} onTicker={onTicker} />
        : (
        <>
          <div className="q-kpis q-kpis--4">
            {[["ACTIVE THEMES", THEME_BASKETS.length, "violet", "tracked"],
              ["HOTTEST · " + perLabel, `${hottest.k.split(" ")[0]} ${hottest[period] >= 0 ? "+" : ""}${hottest[period]}%`, "gn", `RS ${hottest.rs} leader`],
              ["CROWDED NAMES", crowdedCount, "amb", "in 2+ baskets"],
              ["NET 5D FLOW", `+$${(netFlow / 1000).toFixed(1)}B`, "gn", "into baskets"]].map((k, i) => (
              <div key={i} className={`q-kpi q-kpi--${k[2]}`}>
                <div className="q-kpi-l mono">{k[0]}</div>
                <div className={`q-kpi-v mono kpi-tone--${k[2]}`}>{k[1]}</div>
                <div className="q-kpi-s mono dim2">{k[3]}</div>
              </div>
            ))}
          </div>

          {/* theme cards */}
          <div className="q-theme-grid">
            {THEME_BASKETS.map(t => {
              const chg = t[period], q = rotQuad(t);
              const nCrowd = t.cons.filter(c => crowd[c[0]].length >= 2).length;
              return (
                <div key={t.k} className={`q-theme-card ${sel === t.k ? "is-sel" : ""}`} style={{ "--tc": `var(--${t.tone})` }} onClick={() => setSel(t.k)}>
                  <div className="q-tc-head">
                    <div>
                      <div className="q-tc-name">{t.k}</div>
                      <div className="q-tc-tag mono dim2">{t.tag}</div>
                    </div>
                    <div className={`q-tc-chg mono ${chg >= 0 ? "up" : "dn"}`}><span className="q-tc-chg-v">{chg >= 0 ? "+" : ""}{chg}%</span><span className="q-tc-chg-l mono dim2">{perLabel}</span></div>
                  </div>
                  <ThemeSpark data={t.curve} tone={t.tone} />
                  <div className="q-tc-tags">
                    <span className={`q-phase q-phase--${q.k}`}>{q.label}</span>
                    {nCrowd > 0 && <span className="q-crowd-chip" title={`${nCrowd} constituents also appear in other themes`}>⋈ {nCrowd} crowded</span>}
                  </div>
                  <div className="q-tc-meta">
                    <span className="mono"><span className="dim2">RS</span> <b className={t.rs >= 70 ? "up" : t.rs >= 50 ? "warn" : "dn"}>{t.rs}</b> <span className={`q-bdelta ${t.rs - t.rsPrev >= 0 ? "up" : "dn"}`}>{t.rs - t.rsPrev >= 0 ? "+" : ""}{t.rs - t.rsPrev}</span></span>
                    <BreadthTrend now={t.breadth} prev={t.breadthPrev} />
                    <span className="mono"><span className="dim2">FLOW</span> <b className={t.flow >= 0 ? "up" : "dn"}>{t.flow >= 0 ? "+" : "−"}${Math.abs(t.flow)}M</b></span>
                    <span className="mono"><span className="dim2">NAMES</span> <b>{t.members}</b></span>
                  </div>
                  <div className="q-tc-chips">
                    {t.cons.map(c => {
                      const crowded = crowd[c[0]].length >= 2, isLead = c[0] === t.lead;
                      return (
                        <button key={c[0]} className={`q-tc-chip mono ${isLead ? "q-tc-chip--lead" : ""} ${crowded ? "q-tc-chip--crowd" : ""}`}
                                title={`${c[0]} · RS ${c[2]}${isLead ? " · basket leader" : ""}${crowded ? " · also in " + crowd[c[0]].filter(k => k !== t.k).length + " other theme(s)" : ""}`}
                                onClick={(e) => { e.stopPropagation(); onTicker(c[0]); }}>{c[0]}</button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* constituents drill-down — top 10 */}
          <div className="lab-card">
            <div className="lab-card-h mono">{cur.k.toUpperCase()} · TOP 10 CONSTITUENTS · {cur.members} names total · RS-weighted</div>
            <table className="dtable wsx-tbl q-cons-tbl">
              <thead><tr><th>#</th><th>Sym</th><th className="r">1D %</th><th className="r">RS rank</th><th>RS vs SPX</th><th>Role</th><th>Crowding</th></tr></thead>
              <tbody>{cur.cons.map((c, i) => {
                const others = crowd[c[0]].filter(k => k !== cur.k);
                return (
                  <tr key={i} onClick={() => onTicker(c[0])}>
                    <td className="mono dim2">{String(i + 1).padStart(2, "0")}</td>
                    <td><b className="mono">{c[0]}</b></td>
                    <td className={`r tabular ${c[1] >= 0 ? "up" : "dn"}`}>{c[1] >= 0 ? "+" : ""}{c[1]}%</td>
                    <td className="r tabular"><b>{c[2]}</b></td>
                    <td><div className="q-rs-bar"><div className="q-rs-fill" style={{ width: `${c[2]}%`, background: c[2] >= 70 ? "var(--gn)" : c[2] >= 50 ? "var(--amb)" : "var(--rd)" }} /></div></td>
                    <td>{c[0] === cur.lead ? <Pill tone="copper" small>LEADER</Pill> : c[2] >= 60 ? <Pill tone="gn" small>strong</Pill> : c[2] >= 45 ? <Pill tone="amb" small>inline</Pill> : <Pill tone="rd" small>laggard</Pill>}</td>
                    <td>{others.length ? <span className="q-crowd-chip q-crowd-chip--sm" title={`Also in: ${others.join(", ")}`}>⋈ {others.map(o => o.split(" ")[0]).join(", ")}</span> : <span className="dim2 mono">—</span>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
            <div className="lab-verdict mono dim2">Trade the <b className="copper">leaders</b>, not the basket — RS dispersion within a hot theme is wide. {cur.lead} carries {cur.k}; laggards (&lt;45 RS) are sympathy risk. <b className="amb">⋈ crowded</b> names sit in multiple themes — sizing them as separate bets understates concentration.</div>
          </div>
        </>
        )}
      <div className="pf-note mono dim2">Baskets are curated and RS-weighted — a theme's print is the weighted basket return, but entries are screened name-by-name through the same 10 gates. Rotation map plots RS level against its 4-week change to show where capital is moving. Flows estimate net premium into constituents over 5 sessions. Click any name → 14-lens detail.</div>
    </div>
  );
}

window.SurfaceThemes = SurfaceThemes;
