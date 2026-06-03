// patterns-classical.jsx — Classical chart-patterns theory sub-tab.
// Annotated base/triangle on real bars (trendlines + neckline + breakout),
// the multi-method detection matrix, a VCP contraction ladder, and a
// measured-move target / invalidation table with confidence.

const { useMemo: useMemoCl } = React;

const CL_BARS = 70;
const CL_PIVOT = 205.2;     // flat resistance / breakout pivot
const CL_STOP = 198.0;

function useClassical(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x3c1;
  return useMemoCl(() => {
    // ascending base: flat top ~205, rising lows, breakout, mark-up
    const anchors = [
      { i: 0, price: 198 }, { i: 6, price: 186 }, { i: 12, price: 203 }, { i: 18, price: 190 },
      { i: 24, price: 204 }, { i: 30, price: 195 }, { i: 38, price: 204 }, { i: 44, price: 199 },
      { i: 50, price: 204 }, { i: 55, price: 201 }, { i: 58, price: 207 }, { i: 63, price: 210 },
      { i: 69, price: 213.4 },
    ];
    const volSpikes = { 6: 1.6, 58: 2.2, 59: 1.9 };
    const bars = buildSeries({ n: CL_BARS, anchors, seed, volSpikes });
    return { bars };
  }, [seed]);
}

function ClassicalChart({ ticker, height = 320 }) {
  const { bars } = useClassical(ticker);
  // rising lower trendline of the base + breakout marker
  const lines = [
    { pts: [{ i: 6, price: 186 }, { i: 18, price: 190 }, { i: 30, price: 195 }, { i: 44, price: 199 }, { i: 55, price: 201 }], tone: "cy", width: 1.4, dash: "4 3" },
  ];
  const hlines = [
    { price: CL_PIVOT, label: `Pivot / resistance ${CL_PIVOT}`, tone: "copper", dash: "5 4" },
    { price: 225.0, label: "Measured move 225", tone: "gn", dash: "5 4" },
    { price: CL_STOP, label: `Stop ${CL_STOP}`, tone: "rd", dash: "3 3", labelBelow: true },
  ];
  const markers = [
    { i: 6, price: 186, label: "Base low", tone: "ink-2", place: "below" },
    { i: 24, price: 204, label: "Lower high", tone: "ink-2", place: "above" },
    { i: 58, price: 207, label: "Breakout", tone: "gn", place: "above" },
    { i: 63, price: 210, label: "Retest ✓", tone: "gn", place: "below" },
  ];
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} lines={lines} accent="cy" />;
}

// VCP contraction ladder
const CL_VCP = [
  { n: "1", depth: "−18%", weeks: "5w", vol: "heavy", tone: "ink-2" },
  { n: "2", depth: "−12%", weeks: "4w", vol: "−32%", tone: "ink-2" },
  { n: "3", depth: "−8%", weeks: "3w", vol: "−24%", tone: "ink-1" },
  { n: "4", depth: "−5%", weeks: "2w", vol: "−41%", tone: "cy" },
  { n: "5", depth: "−3%", weeks: "1w", vol: "dry", tone: "gn" },
];
function VCPLadder() {
  return (
    <div className="pv-vcp">
      {CL_VCP.map((c, k) => (
        <div key={k} className="pv-vcp-cell" style={{ borderColor: `var(--${c.tone})` }}>
          <div className="pv-vcp-n mono" style={{ color: `var(--${c.tone})` }}>T{c.n}</div>
          <div className="pv-vcp-d mono">{c.depth}</div>
          <div className="pv-vcp-m mono dim2">{c.weeks} · vol {c.vol}</div>
        </div>
      ))}
    </div>
  );
}

const CL_TGT = [
  { label: "Breakout pivot", basis: "flat resistance of the base", price: "205.2", rr: "trigger", conf: null, tone: "copper" },
  { label: "T1 · measured move", basis: "base height (20) added to pivot", price: "225.0", rr: "+5.5%", conf: 0.64, tone: "gn" },
  { label: "T2 · 1.5× extension", basis: "1.5 × base height", price: "235.0", rr: "+10.2%", conf: 0.41, tone: "amb" },
];
function ClassicalTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Objective", k: "label" }, { h: "Basis", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" }, { h: "R:R", k: "rr", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={CL_TGT.map(t => ({
          label: <b style={{ color: `var(--${t.tone})` }}>{t.label}</b>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>,
          rr: t.rr === "trigger" ? <span className="dim mono">trigger</span> : <span className="up">{t.rr}</span>,
          conf: t.conf == null ? <span className="dim mono">—</span> : <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">Close back below the pivot <b className="dn">$205.20</b> (failed breakout) or under the last contraction low — stand aside.</span>
      </div>
    </div>
  );
}

function ClassicalStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Primary pattern</div><div className="pv-stat-v mono cy">VCP · Asc. triangle</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Stage</div><div className="pv-stat-v mono up">Breakout +retest</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Contractions</div><div className="pv-stat-v mono">5 · 18%→3%</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Measured move</div><div className="pv-stat-v mono up">$225</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.64} tone="cy" width={72} /></div></div>
    </div>
  );
}

function ClassicalView({ ticker, dir }) {
  const Chart = <ClassicalChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <ClassicalStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Base — annotated" sub="trendlines · pivot · breakout on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="VCP contraction ladder" style="minimal" />
            <div className="pv-pad"><VCPLadder /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Detected patterns" style="minimal" />
            <div className="pv-pad"><PatternMatrix /><div className="pv-block-h label-cap" style={{ padding: "12px 0 6px" }}>Pattern library</div><ClassicalLibrary dense /></div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad"><ClassicalTargets /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <ClassicalStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-pad" style={{ paddingTop: 0 }}><VCPLadder /></div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Detected patterns</div>
            <PatternMatrix />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Pattern library</div>
            <ClassicalLibrary dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Measured-move targets</div>
            <ClassicalTargets />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led
  return (
    <div className="pv-view">
      <ClassicalStat />
      <SectionHeader n={1} title="Base structure — annotated" sub="ascending triangle / VCP · pivot · breakout + retest" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <SectionHeader n={2} title="VCP contraction ladder" sub="tightening price · drying volume" style="minimal" />
      <div className="pv-pad"><VCPLadder /></div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Detected patterns · 6 detectors</div>
          <PatternMatrix />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Classical pattern library · measured moves</div>
          <ClassicalLibrary />
        </div>
        <div>
          <div className="pv-block-h label-cap">Measured-move targets &amp; invalidation</div>
          <ClassicalTargets />
        </div>
      </div>
    </div>
  );
}

const CL_LIB = [
  { p: "Cup & Handle", st: "CONFIRMED", mm: "$232", conf: 0.66, tone: "gn" },
  { p: "Ascending Triangle", st: "BREAKOUT", mm: "$225", conf: 0.64, tone: "gn" },
  { p: "Double Bottom", st: "CONFIRMED", mm: "$221", conf: 0.61, tone: "gn" },
  { p: "Bull Flag", st: "FORMING", mm: "$224", conf: 0.58, tone: "cy" },
  { p: "Falling Wedge", st: "FORMING", mm: "$228", conf: 0.55, tone: "cy" },
  { p: "Inverse H&S", st: "WATCH", mm: "$238", conf: 0.49, tone: "amb" },
  { p: "Rectangle / Range", st: "RANGE", mm: "$230", conf: 0.44, tone: "ink" },
  { p: "Broadening / Megaphone", st: "CAUTION", mm: "—", conf: 0.32, tone: "rd" },
  { p: "Diamond", st: "RARE", mm: "—", conf: 0.30, tone: "ink" },
];
function ClassicalLibrary({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Pattern", k: "p" }, { h: "Status", k: "st", align: "center" }, { h: "Measured move", k: "mm", mono: true, align: "right" }, { h: "Conf.", k: "c", align: "right" }]}
    rows={CL_LIB.map(r => ({ p: <b>{r.p}</b>, st: <Pill tone={r.tone} small>{r.st}</Pill>, mm: <b className={r.mm === "—" ? "dim" : "up"}>{r.mm}</b>, c: <ConfBar value={r.conf} tone={r.tone === "ink" ? "ink-3" : r.tone} width={44} /> }))} />;
}

Object.assign(window, { ClassicalView });
