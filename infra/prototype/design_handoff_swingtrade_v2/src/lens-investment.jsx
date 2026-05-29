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
        <SectionHeader n={1} title="Value Gap"
          sub="bear · fair · target · bull · with margin-of-safety"
          style={headerStyle} right={<StateToggle name="iv-1" />} />
        <StateWrap state={s1.value} source="DCF + multiples · 3-scenario">
          <div className="lens-pad"><ValueScale ticker={ticker} /></div>
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
        <span className="label-cap">The Call · Investment</span>
        <span className="mono">
          <b className="copper">MoS 6%</b> · quality A− · prefer to buy on pullback to{' '}
          <b>${(ticker.price * 0.93).toFixed(2)}</b>. Outright BUY only if ER catalyst clears.
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
            Fair value $64.00 · target $75.00 · bull $92.00 · bear $52.00. Current ${cur.toFixed(2)} sits
            ~5% above fair.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── §1 Value scale ─────────────────────────────────────────────────
function ValueScale({ ticker }) {
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
  return (
    <table className="dtable peers">
      <thead>
        <tr>
          <th>Peer</th><th>Name</th>
          <th className="r">P/E</th>
          <th className="r">Fwd P/E</th>
          <th className="r">ROIC</th>
          <th className="r">5y Grow</th>
          <th className="r">$M cap</th>
        </tr>
      </thead>
      <tbody>
        {peers.map(p => (
          <tr key={p.sym} className={p.current ? "is-current" : ""}>
            <td className="mono"><b>{p.sym}</b></td>
            <td className="dim">{p.name}</td>
            <td className="r mono tabular">{p.pe.toFixed(1)}</td>
            <td className="r mono tabular">{p.fwdPe.toFixed(1)}</td>
            <td className={`r mono tabular ${p.roic > 15 ? "up" : "dim2"}`}>{p.roic.toFixed(1)}%</td>
            <td className={`r mono tabular ${p.grow > 10 ? "up" : "dim2"}`}>{p.grow.toFixed(1)}%</td>
            <td className="r mono tabular">{p.mcap.toFixed(2)}B</td>
          </tr>
        ))}
      </tbody>
    </table>
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
