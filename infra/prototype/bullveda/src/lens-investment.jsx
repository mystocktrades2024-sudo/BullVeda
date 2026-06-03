// lens-investment.jsx — Investment · Value
// Value-gap hero, quality scorecard, peer cohort, 5-yr statements,
// capital allocation, bull-vs-bear, long-horizon catalyst calendar.

function LensInvestment({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("iv-1"); const s2 = useStateToggle("iv-2");
  const s3 = useStateToggle("iv-3"); const s4 = useStateToggle("iv-4");
  const s5 = useStateToggle("iv-5"); const s6 = useStateToggle("iv-6");
  const s7 = useStateToggle("iv-7");

  return (
    <div className="lens lens--inv">
      <ValueHero ticker={ticker} mode={mode} />

      <div className="lens-section">
        <SectionHeader n={1} title="Price vs Intrinsic Value · 5-Year"
          sub="price vs rolling bear / base / bull fair-value bands · the gap closes near tops, widens near bottoms"
          style={headerStyle} right={<StateToggle name="iv-1" />} />
        <StateWrap state={s1.value} source="DCF + multiples · 3-scenario · 5y rolling">
          <div className="lens-pad">
            <div className="iv-split">
              <div className="iv-split-main"><ValueBands5Y ticker={ticker} /></div>
              <div className="iv-split-side"><ValueScale ticker={ticker} /><MarginOfSafety ticker={ticker} /></div>
            </div>
          </div>
        </StateWrap>
      </div>      <div className="lens-section">
        <SectionHeader n={2} title="Quality Scorecard"
          sub="business · balance-sheet · operator · trend"
          style={headerStyle} right={<StateToggle name="iv-2" />} />
        <StateWrap state={s2.value} source="EODHD · Highlights + Fundamentals">
          <div className="lens-pad"><QualityCard /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Peer Cohort"
          sub="6 closest specialty-materials peers · normalized"
          style={headerStyle} right={<StateToggle name="iv-3" />} />
        <StateWrap state={s3.value} source="cohort engine · same-GIC peers">
          <div className="lens-pad"><PeerCohort /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="5-Year Statements"
          sub="revenue · GP · NI · FCF · buybacks · with sparklines"
          style={headerStyle} right={<StateToggle name="iv-4" />} />
        <StateWrap state={s4.value} source="EODHD · Financials_5y">
          <div className="lens-pad"><Statements /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Capital Allocation"
          sub="where every dollar of FCF went · 5y window"
          style={headerStyle} right={<StateToggle name="iv-5" />} />
        <StateWrap state={s5.value} source="EODHD · Capital_Flow">
          <div className="lens-pad"><CapAlloc /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Bull · Bear"
          sub="strongest case both ways · pre-mortem · written before entry"
          style={headerStyle} right={<StateToggle name="iv-6" />} />
        <StateWrap state={s6.value} source="thesis library · per-ticker">
          <div className="lens-pad"><BullBear /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Long-Horizon Catalysts"
          sub="next 12 months · earnings · capacity · regulatory"
          style={headerStyle} right={<StateToggle name="iv-7" />} />
        <StateWrap state={s7.value} source="EODHD · calendar + analyst trend">
          <div className="lens-pad"><CatCal /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="violet" cells={[
            { lens: "Value",      verdict: "MARG.", tone: "amb", note: "MoS 6% · slight premium" },
            { lens: "Quality",    verdict: "A−",    tone: "gn",  note: "ROIC 18% · low debt" },
            { lens: "Earnings",   verdict: "BEAT?", tone: "amb", note: "ESP +4.1% · 11d out" },
            { lens: "Risk",       verdict: "OK",    tone: "gn",  note: "VaR(1d) −2.1%" },
            { lens: "Tape",       verdict: "+12 ins", tone: "gn", note: "net insider buys 90d" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Investment</span>
        <span className="mono">
          <b className="copper">MoS 6%</b> · quality A− · valuation is more attractive on a pullback to{' '}
          <b>${(ticker.price * 0.93).toFixed(2)}</b>. Bias stays Neutral until an ER catalyst clears.
        </span>
      </div>
    </div>
  );
}

// ─── Hero ──────────────────────────────────────────────────────────
function ValueHero({ ticker, mode }) {
  const cur = ticker.price;
  return (
    <div className="hero value-hero">
      <div className="vh-top">
        <div>
          <div className="label-cap">Master verdict · INVESTMENT mode</div>
          <div className="vh-verdict">
            <span className="vh-tag">WATCH</span>
            <span className="vh-score mono">71<span className="th-score-unit">/100</span></span>
            <Pill tone="amb" small>MoS 6%</Pill>
          </div>
          <div className="vh-line mono dim2">
            Fair ${(cur * 0.95).toFixed(0)} · target ${(cur * 1.06).toFixed(0)}–${(cur * 1.16).toFixed(0)} · bull ${(cur * 1.40).toFixed(0)} · bear ${(cur * 0.78).toFixed(0)}. Current <b>${cur.toFixed(2)}</b> sits ~5% above fair.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── §1 · Price vs intrinsic-value bands · 5-year ───────────────────
function ivSmooth(pts) {
  if (pts.length < 3) return "M " + pts.map(p => p.join(",")).join(" L ");
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

function ValueBands5Y({ ticker }) {
  const cur = ticker.price;
  const uid = React.useId();
  const [ref, w] = useWidth(900);
  const data = React.useMemo(() => {
    const out = [];
    for (let i = 0; i < 60; i++) {
      const t = i / 59;
      const fair = 0.62 + t * 0.50 + Math.sin(i * 0.32) * 0.012;        // rising fair (× cur scale)
      const cyc = Math.sin(i * 0.26) * 0.6 + Math.sin(i * 0.12) * 0.7;   // valuation cycle
      const widen = 0.16 + (1 - (cyc + 1.3) / 2.6) * 0.20;              // band wide at lows
      out.push({ fair, bear: fair * (1 - widen), bull: fair * (1 + widen + 0.05), price: fair * (1 + cyc * widen * 0.92), cyc });
    }
    // normalise so "now" price = cur
    const k = 1 / out[59].price;
    out.forEach(d => { d.fair *= k * cur; d.bear *= k * cur; d.bull *= k * cur; d.price *= k * cur; d.gap = (d.price - d.fair) / d.fair * 100; });
    out[59].price = cur; out[59].gap = (cur - out[59].fair) / out[59].fair * 100;
    return out;
  }, [cur]);

  const padL = 6, padR = 54, padT = 14;
  const priceH = 168, gapH = 46, gapGap = 16;
  const h = padT + priceH + gapGap + gapH + 14;
  const plotW = w - padL - padR, plotR = padL + plotW;
  const all = data.flatMap(d => [d.bear, d.bull, d.price]);
  const min = Math.min(...all) * 0.97, max = Math.max(...all) * 1.03;
  const xOf = i => padL + (i / 59) * plotW;
  const yOf = v => padT + priceH - ((v - min) / (max - min)) * priceH;
  const pl = key => data.map((d, i) => [xOf(i), yOf(d[key])]);
  const envelope = `${ivSmooth(pl("bull"))} L ${data.map((d, i) => `${xOf(59 - i).toFixed(1)},${yOf(data[59 - i].bear).toFixed(1)}`).join(" L ")} Z`;
  const priceArea = `${ivSmooth(pl("price"))} L ${xOf(59).toFixed(1)},${(padT + priceH).toFixed(1)} L ${xOf(0).toFixed(1)},${(padT + priceH).toFixed(1)} Z`;
  // touches: price near/under bear (value) or near/over bull (rich)
  const touches = data.map((d, i) => ({ i, d })).filter(({ d }) => d.price <= d.bear * 1.01 || d.price >= d.bull * 0.99)
    .filter((_, idx) => idx % 2 === 0);
  const gapMax = Math.max(...data.map(d => Math.abs(d.gap)), 8);
  const gapTop = padT + priceH + gapGap;
  const yGap = g => gapTop + gapH / 2 - (g / gapMax) * (gapH / 2);
  const nowGap = data[59].gap;
  const premium = nowGap >= 0;

  return (
    <div className="iv-bands" ref={ref}>
      <svg width={w} height={h}>
        <defs>
          <linearGradient id={`iv-env-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.16" />
            <stop offset="48%" stopColor="var(--ink-2)" stopOpacity="0.05" />
            <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.16" />
          </linearGradient>
          <linearGradient id={`iv-px-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--copper)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* fair-value envelope */}
        <path d={envelope} fill={`url(#iv-env-${uid})`} />
        {[0.25, 0.5, 0.75].map((f, k) => <line key={k} x1={padL} y1={padT + priceH * f} x2={plotR} y2={padT + priceH * f} stroke="var(--line)" strokeDasharray="1 6" opacity="0.4" />)}

        {/* bull / fair / bear curves */}
        <path d={ivSmooth(pl("bull"))} fill="none" stroke="var(--gn)" strokeWidth="1.1" strokeDasharray="5 4" opacity="0.7" />
        <path d={ivSmooth(pl("fair"))} fill="none" stroke="var(--ink-2)" strokeWidth="1.3" strokeDasharray="2 3" opacity="0.8" />
        <path d={ivSmooth(pl("bear"))} fill="none" stroke="var(--rd)" strokeWidth="1.1" strokeDasharray="5 4" opacity="0.7" />

        {/* price */}
        <path d={priceArea} fill={`url(#iv-px-${uid})`} />
        <path d={ivSmooth(pl("price"))} fill="none" stroke="var(--copper)" strokeWidth="2.2" style={{ filter: "drop-shadow(0 0 5px color-mix(in oklab, var(--copper) 60%, transparent))" }} />

        {/* historical value / rich touches */}
        {touches.map(({ i, d }, k) => {
          const value = d.price <= d.bear * 1.01;
          return <circle key={k} cx={xOf(i)} cy={yOf(d.price)} r="3" fill={value ? "var(--gn)" : "var(--rd)"} stroke="var(--bg-1)" strokeWidth="1.2" opacity="0.9" />;
        })}

        {/* now dot + tag */}
        <circle cx={xOf(59)} cy={yOf(cur)} r="4" fill="var(--copper)" stroke="var(--bg-1)" strokeWidth="1.4" />
        <line x1={padL} y1={yOf(cur)} x2={plotR} y2={yOf(cur)} stroke="var(--copper)" strokeDasharray="2 3" opacity="0.4" />
        {[["bull", "gn"], ["fair", "ink-2"], ["bear", "rd"]].map(([k, t], i) => (
          <text key={i} x={plotR + 5} y={yOf(data[59][k]) + 3} fontSize="9.5" className="mono" fill={`var(--${t})`}>{data[59][k].toFixed(0)}</text>
        ))}
        <g transform={`translate(${plotR + 1}, ${yOf(cur) - 8})`}>
          <rect width={padR - 2} height="16" rx="2.5" fill="var(--copper)" />
          <text x={(padR - 2) / 2} y="11.5" fontSize="9.5" textAnchor="middle" className="mono" fill="var(--bg-0)" style={{ fontWeight: 700 }}>{cur.toFixed(0)}</text>
        </g>

        {/* discount / premium oscillator (the gap) */}
        <text x={padL} y={gapTop - 4} fontSize="8.5" className="mono" fill="var(--ink-3)" style={{ letterSpacing: "0.1em" }}>PREMIUM / DISCOUNT vs FAIR (%)</text>
        <line x1={padL} y1={yGap(0)} x2={plotR} y2={yGap(0)} stroke="var(--ink-3)" opacity="0.6" />
        {data.map((d, i) => {
          const y0 = yGap(0), y1 = yGap(d.gap);
          return <rect key={i} x={xOf(i) - 1.4} y={Math.min(y0, y1)} width="2.8" height={Math.abs(y1 - y0)} fill={`var(--${d.gap >= 0 ? "rd" : "gn"})`} opacity="0.55" />;
        })}
        <text x={plotR + 5} y={yGap(nowGap) + 3} fontSize="9.5" className="mono" fill={`var(--${premium ? "rd" : "gn"})`}>{nowGap >= 0 ? "+" : ""}{nowGap.toFixed(0)}%</text>

        {/* year axis */}
        {[0, 12, 24, 36, 48, 59].map((i, k, arr) => (
          <text key={`y${k}`} x={xOf(i)} y={h - 3} fontSize="9" className="mono" fill="var(--ink-3)" textAnchor={k === 0 ? "start" : k === arr.length - 1 ? "end" : "middle"}>{k === arr.length - 1 ? "now" : `${5 - Math.round(i / 12)}y`}</text>
        ))}
      </svg>
      <div className="iv-bands-leg mono dim2">
        <span><span className="iv-dot" style={{ background: "var(--copper)" }} /> price</span>
        <span><span className="iv-dot" style={{ background: "var(--gn)" }} /> bull FV</span>
        <span><span className="iv-dot" style={{ background: "var(--ink-2)" }} /> base / fair</span>
        <span><span className="iv-dot" style={{ background: "var(--rd)" }} /> bear FV</span>
        <span className="iv-bands-read">Trading at a <b className={premium ? "dn" : "up"}>{premium ? "premium" : "discount"} of {Math.abs(nowGap).toFixed(0)}%</b> to base fair value — {premium ? "upper" : "lower"} half of the band.</span>
      </div>
    </div>
  );
}

// ─── §1 · Margin of safety vs fair value (methodology ladder) ───────
function MarginOfSafety({ ticker }) {
  const cur = ticker.price;
  const methods = [
    { m: "Analyst PT · mean", sub: "consensus target", mos: 8.1 },
    { m: "DCF · 10y · 9% WACC · 3% g", sub: "discounted cash flow", mos: 5.5 },
    { m: "P/FCF · 5y avg reversion", sub: "cash-flow multiple", mos: 7.3 },
    { m: "EV/EBITDA · peer reversion", sub: "enterprise multiple", mos: 3.1 },
    { m: "Peer P/E reversion", sub: "relative earnings", mos: -2.4 },
    { m: "Graham Number", sub: "√(22.5·EPS·BV)", mos: -5.6 },
  ];
  const wts = [0.30, 0.30, 0.12, 0.10, 0.08, 0.10];
  const blended = methods.reduce((s, x, i) => s + x.mos * wts[i], 0);
  const tone = v => v >= 4 ? "gn" : v <= -4 ? "rd" : "amb";
  const Bar = ({ v }) => {
    const cap = Math.max(-25, Math.min(25, v));
    const half = Math.abs(cap) / 25 * 50;
    return (
      <div className="iv-mos-bar-cell">
        <span className="mono dim2">−25%</span>
        <div className="iv-mos-track">
          <span className="zero" />
          <div className={`iv-mos-fill ${tone(v)}`} style={v >= 0 ? { left: "50%", width: `${half}%` } : { left: `${50 - half}%`, width: `${half}%` }} />
        </div>
        <span className="mono dim2">+25%</span>
      </div>
    );
  };
  return (
    <div className="iv-mos">
      <div className="iv-mos-hd">
        <div className="iv-mos-blend">
          <div className="label-cap">Margin of Safety · vs fair value</div>
          <div className={`iv-mos-blend-v mono kpi-tone--${tone(blended)}`}>{blended >= 0 ? "+" : ""}{blended.toFixed(1)}%</div>
          <div className="mono dim2">blended across {methods.length} independent lenses · weighted</div>
        </div>
        <Pill tone={tone(blended)} small>{blended >= 4 ? "MARGIN" : blended <= -4 ? "PREMIUM" : "FAIR ± "}{Math.abs(blended).toFixed(0)}%</Pill>
      </div>
      <table className="pv-table iv-mos-tbl">
        <thead><tr>
          <th className="label-cap">Methodology</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Fair value</th>
          <th className="label-cap" style={{ textAlign: "right" }}>MoS</th>
          <th className="label-cap">−25% · spot · +25%</th>
        </tr></thead>
        <tbody>
          {methods.map((x, i) => (
            <tr key={i}>
              <td><b>{x.m}</b><br /><span className="dim2" style={{ fontSize: 10 }}>{x.sub}</span></td>
              <td className="mono" style={{ textAlign: "right" }}>${(cur * (1 + x.mos / 100)).toFixed(0)}</td>
              <td className="mono" style={{ textAlign: "right", color: `var(--${tone(x.mos)})`, fontWeight: 700 }}>{x.mos >= 0 ? "+" : ""}{x.mos}%</td>
              <td><Bar v={x.mos} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <DcfSensitivity ticker={ticker} />
    </div>
  );
}

// DCF sensitivity — fair value across WACC × terminal-growth, shaded by MoS vs spot
function DcfSensitivity({ ticker }) {
  const cur = ticker.price;
  const waccs = [0.08, 0.09, 0.10, 0.11];
  const grows = [0.02, 0.03, 0.04, 0.05];
  // base DCF fair value at 9% WACC / 3% g ≈ spot × (1 + 5.5% MoS); back out implied FCF stream
  const base = cur * 1.055, baseW = 0.09, baseG = 0.03;
  const fv = (w, g) => base * ((baseW - baseG) / (w - g));   // Gordon-style sensitivity
  const tone = mos => mos >= 8 ? "gn" : mos >= 0 ? "amb" : "rd";
  return (
    <div className="dcf-sens">
      <div className="label-cap" style={{ marginBottom: 8 }}>DCF Sensitivity · fair value by WACC × terminal growth <span className="dim2">(spot ${cur.toFixed(0)})</span></div>
      <table className="dtable dcf-grid">
        <thead><tr><th className="dim2">WACC ↓ · g →</th>{grows.map(g => <th key={g} className="r">{(g*100).toFixed(0)}%</th>)}</tr></thead>
        <tbody>
          {waccs.map(w => (
            <tr key={w}>
              <td className="mono dim2">{(w*100).toFixed(0)}%</td>
              {grows.map(g => {
                const val = fv(w, g); const mos = (val / cur - 1) * 100;
                return <td key={g} className={`r mono dcf-cell kpi-tone--${tone(mos)}`} title={`MoS ${mos >= 0 ? "+" : ""}${mos.toFixed(0)}%`} style={{ background: `color-mix(in oklab, var(--${tone(mos)}) ${Math.min(22, Math.abs(mos))}%, transparent)` }}>${val.toFixed(0)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 6 }}>Each cell = intrinsic value at that discount rate &amp; perpetual growth; green = trades below fair (margin), red = premium. The base case (<b>9% / 3%</b>) sits near spot — the thesis only holds if you believe WACC ≤ 9% <i>and</i> growth ≥ 3%.</div>
    </div>
  );
}

// ─── §1 Value scale · bear / fair / target range / bull ─────────────
function ValueScale({ ticker }) {
  const cur = ticker.price;
  // levels derived from current price so the scale is sensible for any ticker
  const bear = cur * 0.78, fair = cur * 0.95, tgtLo = cur * 1.06, tgtHi = cur * 1.16, bull = cur * 1.40;
  const pos = v => Math.max(0, Math.min(100, ((v - bear) / (bull - bear)) * 100));
  const fmt = v => `$${v.toFixed(0)}`;
  return (
    <div className="vh-scale">
      <div className="vh-scale-cap">
        <span className="label-cap">Value scale</span>
        <span className="mono dim2">bear · fair · target range · bull</span>
      </div>
      <div className="vh-scale-track">
        <div className="vh-scale-fill" />
        <div className="vh-scale-range" style={{ left: `${pos(tgtLo)}%`, width: `${pos(tgtHi) - pos(tgtLo)}%` }}>
          <span className="vh-scale-range-lbl mono">target range</span>
        </div>
        <div className="vh-scale-marker vh-bear" style={{ left: "0%" }}>
          <div className="vh-scale-px mono">{fmt(bear)}</div><div className="label-cap">bear</div>
        </div>
        <div className="vh-scale-marker vh-fair" style={{ left: `${pos(fair)}%` }}>
          <div className="vh-scale-px mono">{fmt(fair)}</div><div className="label-cap">fair</div>
        </div>
        <div className="vh-scale-marker vh-target" style={{ left: `${pos((tgtLo + tgtHi) / 2)}%` }}>
          <div className="vh-scale-px mono">{fmt(tgtLo)}–{fmt(tgtHi)}</div><div className="label-cap">target</div>
        </div>
        <div className="vh-scale-marker vh-bull" style={{ left: "100%" }}>
          <div className="vh-scale-px mono">{fmt(bull)}</div><div className="label-cap">bull</div>
        </div>
        <div className="vh-scale-current" style={{ left: `${pos(cur)}%` }}>
          <div className="vh-cur-px mono">${cur.toFixed(2)}</div>
        </div>
      </div>
    </div>
  );
}

// ─── (legacy hardcoded scale, unused) ───────────────────────────────
function ValueScaleStatic({ ticker }) {
  const cur = ticker.price;
  const bear = 52, fair = 64, target = 75, bull = 92;
  const x = ((cur - bear) / (bull - bear)) * 100;
  const xFair = ((fair - bear) / (bull - bear)) * 100;
  const xTarget = ((target - bear) / (bull - bear)) * 100;
  return (
    <div className="vh-scale">
      <div className="vh-scale-track">
        <div className="vh-scale-fill" />
        <div className="vh-scale-marker vh-bear" style={{ left: "0%" }}>
          <div className="vh-scale-px mono">$52</div>
          <div className="label-cap">bear</div>
        </div>
        <div className="vh-scale-marker vh-fair" style={{ left: `${xFair}%` }}>
          <div className="vh-scale-px mono">$64</div>
          <div className="label-cap">fair</div>
        </div>
        <div className="vh-scale-marker vh-target" style={{ left: `${xTarget}%` }}>
          <div className="vh-scale-px mono">$75</div>
          <div className="label-cap">target</div>
        </div>
        <div className="vh-scale-marker vh-bull" style={{ left: "100%" }}>
          <div className="vh-scale-px mono">$92</div>
          <div className="label-cap">bull</div>
        </div>
        <div className="vh-scale-current" style={{ left: `${x}%` }}>
          <div className="vh-cur-px mono">${cur.toFixed(2)}</div>
        </div>
      </div>
    </div>
  );
}

// ─── §2 Quality scorecard ────────────────────────────────────────────
function QualityCard() {
  const cats = [
    { cat: "Business",   grade: "A",  metrics: [
      { k: "ROIC (5y avg)", v: "18.2%", tone: "gn" },
      { k: "Gross margin",   v: "42.1%", tone: "gn" },
      { k: "Op margin",      v: "16.4%", tone: "gn" },
    ]},
    { cat: "Balance",    grade: "A-", metrics: [
      { k: "Net-debt / EBITDA", v: "0.81×", tone: "gn" },
      { k: "Interest cover",    v: "12.4×", tone: "gn" },
      { k: "Current ratio",     v: "2.10",  tone: "gn" },
    ]},
    { cat: "Operator",   grade: "B+", metrics: [
      { k: "Insider own",     v: "4.2%",   tone: "amb" },
      { k: "Buybacks (5y)",   v: "$640M",  tone: "gn" },
      { k: "Dilution (5y)",   v: "−2.1%",  tone: "gn" },
    ]},
    { cat: "Trend",      grade: "B",  metrics: [
      { k: "Rev CAGR 5y",     v: "11.4%", tone: "gn" },
      { k: "FCF CAGR 5y",     v: "9.8%",  tone: "gn" },
      { k: "Margin trend",    v: "FLAT",  tone: "amb" },
    ]},
  ];
  return (
    <div className="quality">
      {cats.map((c, i) => (
        <div key={i} className="qual-cat">
          <div className="qual-hdr">
            <span className="label-cap">{c.cat}</span>
            <span className={`qual-grade mono ${c.grade.startsWith("A") ? "up" : c.grade.startsWith("B") ? "warn" : "dn"}`}>
              {c.grade}
            </span>
          </div>
          {c.metrics.map((m, j) => (
            <div key={j} className="qual-metric">
              <span className="mono dim2">{m.k}</span>
              <span className={`mono kpi-tone--${m.tone}`}>{m.v}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ─── §3 Peer cohort ──────────────────────────────────────────────────
function PeerCohort() {
  const peers = [
    { sym: "ARCM", name: "Arclight (US)",  pe: 22.4, fwdPe: 18.9, roic: 18.2, grow: 11.4, mcap: 4.82, current: true },
    { sym: "TURM", name: "Turmaline",       pe: 24.1, fwdPe: 21.0, roic: 14.1, grow: 7.8,  mcap: 3.20 },
    { sym: "WLDA", name: "Welda Specialty", pe: 28.0, fwdPe: 23.5, roic: 12.0, grow: 5.4,  mcap: 2.40 },
    { sym: "KOPL", name: "Kopolymer",       pe: 19.5, fwdPe: 16.8, roic: 16.5, grow: 9.1,  mcap: 1.80 },
    { sym: "BRMA", name: "Bromax",          pe: 31.2, fwdPe: 26.0, roic: 11.4, grow: 13.2, mcap: 5.10 },
    { sym: "RUST", name: "Rusticum",        pe: 14.8, fwdPe: 13.2, roic: 8.4,  grow: 2.1,  mcap: 1.10 },
  ];
  // composite quality score → percentile rank within the cohort
  const scored = peers.map(p => ({ ...p, q: p.roic * 1.4 + p.grow * 1.1 - p.fwdPe * 0.5 }));
  const sortedQ = scored.map(p => p.q).sort((a, b) => a - b);
  scored.forEach(p => { p.pct = Math.round((sortedQ.filter(q => q <= p.q).length - 1) / (sortedQ.length - 1) * 100); });
  const cur = scored.find(p => p.current);
  return (
    <>
    <table className="dtable peers">
      <thead>
        <tr>
          <th>Peer</th><th>Name</th>
          <th className="r">P/E</th>
          <th className="r">Fwd P/E</th>
          <th className="r">ROIC</th>
          <th className="r">5y Grow</th>
          <th className="r">$M cap</th>
          <th className="r">Cohort %ile</th>
        </tr>
      </thead>
      <tbody>
        {scored.map(p => (
          <tr key={p.sym} className={p.current ? "is-current" : ""}>
            <td className="mono"><b>{p.sym}</b></td>
            <td className="dim">{p.name}</td>
            <td className="r mono tabular">{p.pe.toFixed(1)}</td>
            <td className="r mono tabular">{p.fwdPe.toFixed(1)}</td>
            <td className={`r mono tabular ${p.roic > 15 ? "up" : "dim2"}`}>{p.roic.toFixed(1)}%</td>
            <td className={`r mono tabular ${p.grow > 10 ? "up" : "dim2"}`}>{p.grow.toFixed(1)}%</td>
            <td className="r mono tabular">{p.mcap.toFixed(2)}B</td>
            <td className="r mono tabular"><span className={`peer-pct kpi-tone--${p.pct >= 66 ? "gn" : p.pct >= 40 ? "amb" : "rd"}`}>{p.pct}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
    <div className="lab-verdict mono dim2" style={{ marginTop: 8 }}><b className="copper">{cur.sym}</b> ranks in the <b className={cur.pct >= 66 ? "up" : ""}>{cur.pct}th percentile</b> of its 6-name cohort on a quality composite (ROIC + growth − valuation) — {cur.pct >= 66 ? "best-in-cohort fundamentals" : cur.pct >= 40 ? "middle of the pack" : "lagging peers on quality"}.</div>
    </>
  );
}

// ─── §4 5-yr statements ──────────────────────────────────────────────
function Statements() {
  const rows = [
    { line: "Revenue",   vals: [620, 712, 824, 919, 1042], unit: "M", tone: "ink" },
    { line: "Gross Pft", vals: [264, 304, 351, 388, 438],  unit: "M", tone: "ink" },
    { line: "Op Inc",    vals: [86, 112, 130, 148, 171],   unit: "M", tone: "ink" },
    { line: "Net Inc",   vals: [62, 82, 96, 108, 124],     unit: "M", tone: "ink" },
    { line: "FCF",       vals: [54, 78, 88, 101, 118],     unit: "M", tone: "gn" },
    { line: "Buyback",   vals: [40, 80, 120, 180, 220],    unit: "M cum", tone: "copper" },
    { line: "Sh out",    vals: [82.1, 81.4, 80.6, 79.8, 79.0], unit: "M", tone: "gn", neg: true },
  ];
  return (
    <table className="dtable statements">
      <thead>
        <tr>
          <th>Line</th>
          <th className="r">2022</th>
          <th className="r">2023</th>
          <th className="r">2024</th>
          <th className="r">2025</th>
          <th className="r">TTM</th>
          <th>Trend</th>
          <th className="r">5y</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const first = r.vals[0];
          const last = r.vals[r.vals.length - 1];
          const cagr = ((Math.pow(last/first, 1/4) - 1) * 100).toFixed(1);
          const good = r.neg ? Number(cagr) < 0 : Number(cagr) > 0;
          return (
            <tr key={i}>
              <td className="mono">{r.line}</td>
              {r.vals.map((v, j) => (
                <td key={j} className="r mono tabular">{v.toLocaleString()}</td>
              ))}
              <td><Sparkline data={r.vals} color={`var(--${good ? "gn" : "rd"})`} w={60} h={18} /></td>
              <td className={`r mono tabular ${good ? "up" : "dn"}`}>{cagr}%</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── §5 Capital allocation ───────────────────────────────────────────
function CapAlloc() {
  const items = [
    { use: "Buybacks",      amt: 220, pct: 0.40, tone: "copper" },
    { use: "Reinvestment",  amt: 178, pct: 0.32, tone: "gn" },
    { use: "Dividends",     amt:  62, pct: 0.11, tone: "ink" },
    { use: "Debt paydown",  amt:  56, pct: 0.10, tone: "ink" },
    { use: "M&A",           amt:  38, pct: 0.07, tone: "amb" },
  ];
  return (
    <div className="cap-alloc">
      <div className="cap-bar">
        {items.map((it, i) => (
          <div key={i} className={`cap-seg cap-${it.tone}`} style={{ width: `${it.pct * 100}%` }}
               title={`${it.use}: $${it.amt}M`} />
        ))}
      </div>
      <div className="cap-legend">
        {items.map((it, i) => (
          <div key={i} className="cap-row">
            <span className={`cap-sw cap-${it.tone}`} />
            <span className="cap-use mono">{it.use}</span>
            <span className="cap-amt mono dim2">${it.amt}M</span>
            <span className="cap-pct mono">{(it.pct * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
      <div className="cap-note mono dim">
        Last 5 years of FCF deployment. Owner-friendly: 40% repurchases at avg $54.20 (currently above).
      </div>
    </div>
  );
}

// ─── §6 Bull vs Bear ─────────────────────────────────────────────────
function BullBear() {
  const bull = [
    "Capacity expansion at Akron plant ships H2 — +18% volume.",
    "Specialty-coatings mix at 38% of revenue · structurally higher GM.",
    "Insider buying 9 of last 12 weeks · $4.2M net.",
    "China decoupling tailwind for US specialty-chem reshoring.",
  ];
  const bear = [
    "Specialty-chem cycle peaks 12–18m ahead of broad market — top-call risk.",
    "Top-2 customer = 31% of revenue (concentration).",
    "EBITDA margin trend flat 3 quarters · pricing power thesis fading.",
    "ER in 11d · last 4 quarters: 3 beats / 1 in-line · trapped on guide?",
  ];
  return (
    <div className="bullbear">
      <div className="bb-col bb-col--bull">
        <div className="bb-hdr">
          <Pill tone="gn" dot>BULL CASE</Pill>
          <span className="mono dim2">why this works</span>
        </div>
        {bull.map((p, i) => (
          <div key={i} className="bb-row">
            <span className="bb-num mono">{String(i+1).padStart(2,"0")}</span>
            <span className="bb-pt">{p}</span>
          </div>
        ))}
      </div>
      <div className="bb-col bb-col--bear">
        <div className="bb-hdr">
          <Pill tone="rd" dot>BEAR CASE</Pill>
          <span className="mono dim2">what kills the thesis</span>
        </div>
        {bear.map((p, i) => (
          <div key={i} className="bb-row">
            <span className="bb-num mono">{String(i+1).padStart(2,"0")}</span>
            <span className="bb-pt">{p}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── §7 Long-horizon catalyst calendar ───────────────────────────────
function CatCal() {
  const events = [
    { when: "Jun 09 · 11d",    label: "Q1 ER",                       tone: "amb",   imp: "high" },
    { when: "Jun 27",          label: "Industry conf (BMO Materials)", tone: "ink",   imp: "med" },
    { when: "Aug 12 · 78d",    label: "Capacity ribbon-cut · Akron", tone: "gn",    imp: "high" },
    { when: "Sep 30",          label: "Q2 ER",                       tone: "amb",   imp: "high" },
    { when: "Nov 06",          label: "Investor day · 5-yr LRP",     tone: "copper",imp: "high" },
    { when: "2027 H1",         label: "Specialty-coatings JV close", tone: "violet",imp: "med" },
  ];
  return (
    <div className="catcal">
      {events.map((e, i) => (
        <div key={i} className={`cat-row cat-${e.tone}`}>
          <span className="cat-when mono">{e.when}</span>
          <span className="cat-label">{e.label}</span>
          <Pill tone={e.imp === "high" ? "amb" : "ink"} small>{e.imp}</Pill>
        </div>
      ))}
    </div>
  );
}

window.LensInvestment = LensInvestment;
