// patterns-fibonacci.jsx — Fibonacci theory sub-tab (the projection pillar).
// Retracement grid (23.6→78.6) + extensions (127/161/261) drawn on the major
// swing, the golden-pocket zone, and CONFLUENCE CLUSTERS where Fib levels stack
// with Wyckoff / Elliott / Harmonic structure.

const { useMemo: useMemoFb } = React;

const FB_SL = 178.0, FB_SH = 214.0;          // major swing low / high
const FB_RANGE = FB_SH - FB_SL;
const retr = p => +(FB_SH - p * FB_RANGE).toFixed(1);
const ext  = p => +(FB_SL + p * FB_RANGE).toFixed(1);

function useFib(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x1f5;
  return useMemoFb(() => {
    const anchors = [
      { i: 0, price: 198 }, { i: 6, price: 178 }, { i: 14, price: 195 }, { i: 22, price: 205 },
      { i: 30, price: 214 }, { i: 38, price: 204 }, { i: 44, price: 208 }, { i: 50, price: 213.4 },
    ];
    const volSpikes = { 6: 1.6, 30: 1.5 };
    const bars = buildSeries({ n: 51, anchors, seed, volSpikes });
    return { bars };
  }, [seed]);
}

function FibChart({ ticker, height = 320 }) {
  const { bars } = useFib(ticker);
  const lines = [
    { pts: [{ i: 6, price: FB_SL }, { i: 30, price: FB_SH }], tone: "ink-2", width: 1.4, dash: "4 3", opacity: 0.6 },
  ];
  const hlines = [
    { price: retr(0.382), label: `.382 ${retr(0.382)}`, tone: "cy", dash: "4 5" },
    { price: retr(0.5),   label: `.500 ${retr(0.5)}`,   tone: "cy", dash: "4 5" },
    { price: retr(0.618), label: `.618 golden ${retr(0.618)}`, tone: "amb", dash: "5 4" },
    { price: retr(0.786), label: `.786 ${retr(0.786)}`, tone: "cy", dash: "4 5", labelBelow: true },
    { price: ext(1.272),  label: `1.272 ext ${ext(1.272)}`, tone: "gn", dash: "5 4" },
    { price: ext(1.618),  label: `1.618 ext ${ext(1.618)}`, tone: "gn", dash: "5 4" },
  ];
  const markers = [
    { i: 6, price: FB_SL, label: "Swing low", tone: "ink-2", place: "below" },
    { i: 30, price: FB_SH, label: "Swing high", tone: "ink-2", place: "above" },
  ];
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} lines={lines} accent="amb" />;
}

// retracement grid
const FB_RETR = [
  { lvl: "0.236", price: retr(0.236), role: "shallow", status: "untested", conf: null, tone: "ink-2" },
  { lvl: "0.382", price: retr(0.382), role: "moderate", status: "untested", conf: null, tone: "cy" },
  { lvl: "0.500", price: retr(0.5),   role: "mid-point", status: "untested", conf: null, tone: "cy" },
  { lvl: "0.618", price: retr(0.618), role: "golden pocket", status: "held (prior)", conf: 0.78, tone: "amb" },
  { lvl: "0.786", price: retr(0.786), role: "deep / last defense", status: "untested", conf: 0.6, tone: "cy" },
];
function FibRetrTable({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Retr.", k: "lvl", mono: true }, { h: "Price", k: "price", mono: true, align: "right" },
           { h: "Role", k: "role" }, { h: "Status", k: "status" }, { h: "Conf.", k: "conf", align: "right" }]}
    rows={FB_RETR.map(r => ({
      lvl: <b style={{ color: `var(--${r.tone})` }}>{r.lvl}</b>,
      price: <b>${r.price}</b>, role: <span className="dim2">{r.role}</span>,
      status: <span className="mono dim2" style={{ fontSize: 11 }}>{r.status}</span>,
      conf: r.conf == null ? <span className="dim mono">—</span> : <ConfBar value={r.conf} tone={r.tone} width={48} />,
    }))} />;
}

const FB_EXT = [
  { lvl: "1.272", price: ext(1.272), basis: "T1 · primary objective", conf: 0.66, tone: "gn" },
  { lvl: "1.618", price: ext(1.618), basis: "T2 · golden extension", conf: 0.47, tone: "gn" },
  { lvl: "2.618", price: ext(2.618), basis: "T3 · parabolic stretch", conf: 0.24, tone: "amb" },
];
function FibExtTable({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Ext.", k: "lvl", mono: true }, { h: "Price", k: "price", mono: true, align: "right" },
           { h: "Objective", k: "basis" }, { h: "Conf.", k: "conf", align: "right" }]}
    rows={FB_EXT.map(r => ({
      lvl: <b style={{ color: `var(--${r.tone})` }}>{r.lvl}</b>, price: <b>${r.price}</b>,
      basis: <span className="dim2" style={{ fontSize: 11 }}>{r.basis}</span>,
      conf: <ConfBar value={r.conf} tone={r.tone} width={48} />,
    }))} />;
}

// confluence clusters — where Fib stacks with structure (the key WEFCE idea)
const FB_CLUSTERS = [
  { kind: "SUPPORT", zone: "$190–192", factors: ["0.618 retr", "Wyckoff ST", "Gartley B"], strength: 0.86, tone: "gn" },
  { kind: "TARGET", zone: "$223–225", factors: ["1.272 ext", "Elliott W5", "Wyckoff P&F"], strength: 0.81, tone: "gn" },
  { kind: "TARGET", zone: "$235–236", factors: ["1.618 ext", "Classical T2"], strength: 0.52, tone: "amb" },
];
function FibClusters() {
  return (
    <div className="pv-clusters">
      {FB_CLUSTERS.map((c, k) => (
        <div key={k} className={`pv-cluster pv-cluster--${c.tone}`}>
          <div className="pv-cluster-head">
            <Pill tone={c.kind === "SUPPORT" ? "cy" : "gn"} small>{c.kind}</Pill>
            <span className="pv-cluster-zone mono">{c.zone}</span>
            <span className="pv-cluster-strength mono" style={{ color: `var(--${c.tone})` }}>{Math.round(c.strength * 100)}%</span>
          </div>
          <div className="pv-cluster-bar"><span style={{ width: `${c.strength * 100}%`, background: `var(--${c.tone})` }} /></div>
          <div className="pv-cluster-factors">
            {c.factors.map((f, j) => <span key={j} className="pv-chip mono">{f}</span>)}
          </div>
        </div>
      ))}
    </div>
  );
}

function FibStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Major swing</div><div className="pv-stat-v mono">178 → 214</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Golden pocket</div><div className="pv-stat-v mono warn">190.6 – 191.8</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Support cluster</div><div className="pv-stat-v mono cy">$191 · 3-hit</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Next target</div><div className="pv-stat-v mono up">$223.8</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Cluster confidence</div><div className="pv-stat-v"><ConfBar value={0.81} tone="amb" width={72} /></div></div>
    </div>
  );
}

function FibInvalid() {
  return (
    <div className="pv-invalid" style={{ margin: "0 16px 14px" }}>
      <span className="label-cap">Invalidation</span>
      <span className="mono">Loss of the 0.786 retracement at <b className="dn">$185.70</b> breaks the swing structure — projection void below the swing low <b className="dn">$178.00</b>.</span>
    </div>
  );
}

function FibonacciView({ ticker, dir }) {
  const Chart = <FibChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <FibStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Fib grid — annotated" sub="retracements + extensions on the major swing" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Confluence clusters" style="minimal" />
            <div className="pv-pad"><FibClusters /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Retracements" style="minimal" />
            <div className="pv-pad"><FibRetrTable dense /></div>
            <SectionHeader n={4} title="Extensions" style="minimal" />
            <div className="pv-pad"><FibExtTable dense /></div>
          </div>
        </div>
        <FibInvalid />
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <FibStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Retracement grid</div>
            <FibRetrTable dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Extension targets</div>
            <FibExtTable dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Confluence clusters</div>
            <FibClusters />
          </div>
        </div>
        <FibInvalid />
      </div>
    );
  }

  // A — chart-led
  return (
    <div className="pv-view">
      <FibStat />
      <SectionHeader n={1} title="Fibonacci grid — annotated" sub="retracements 23.6→78.6 · extensions 127/161/261 · golden pocket" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <SectionHeader n={2} title="Confluence clusters" sub="where Fib stacks with Wyckoff · Elliott · Harmonic structure" style="minimal" />
      <div className="pv-pad"><FibClusters /></div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Retracement grid</div>
          <FibRetrTable />
        </div>
        <div>
          <div className="pv-block-h label-cap">Extension targets</div>
          <FibExtTable />
        </div>
      </div>
      <FibInvalid />
    </div>
  );
}

Object.assign(window, { FibonacciView });
