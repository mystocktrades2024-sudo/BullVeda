// patterns-wolfe.jsx — Wolfe Waves theory sub-tab.
// 5-point reversal structure with the 1-3-5 + 2-4 channel lines and the
// 1-4 "EPA" (Estimated Price at Arrival) target line projected forward.

const { useMemo: useMemoWf } = React;

// bullish Wolfe: 1(low) 2(high) 3(low) 4(high) 5(low=entry) → rally to EPA on the 1-4 line
const WF_PTS = [
  { i: 8,  price: 184, w: "1", place: "below" },
  { i: 18, price: 199, w: "2", place: "above" },
  { i: 28, price: 180, w: "3", place: "below" },
  { i: 38, price: 196, w: "4", place: "above" },
  { i: 48, price: 176, w: "5", place: "below", tone: "copper" },
];
const WF_EPA = { i: 74, price: 210 };

function useWolfe(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x8f3;
  return useMemoWf(() => {
    const anchors = [
      { i: 0, price: 190 }, { i: 8, price: 184 }, { i: 13, price: 193 }, { i: 18, price: 199 },
      { i: 23, price: 188 }, { i: 28, price: 180 }, { i: 33, price: 190 }, { i: 38, price: 196 },
      { i: 43, price: 184 }, { i: 48, price: 176 }, { i: 52, price: 187 },
    ];
    const volSpikes = { 18: 1.4, 28: 1.3, 48: 1.9, 49: 1.6 };
    const bars = buildSeries({ n: 53, anchors, seed, volSpikes });
    return { bars };
  }, [seed]);
}

function WolfeChart({ ticker, height = 330 }) {
  const { bars } = useWolfe(ticker);
  const skeleton = WF_PTS.map(p => ({ i: p.i, price: p.price })).concat([{ i: WF_EPA.i, price: WF_EPA.price }]);
  const lines = [
    { pts: [{ i: 6, price: 184.4 }, { i: 74, price: 170.8 }], tone: "ink-2", width: 1.2, dash: "3 3", opacity: 0.7 }, // 1-3-5 sweet-spot line
    { pts: [{ i: 16, price: 199.3 }, { i: 74, price: 190.6 }], tone: "ink-2", width: 1.2, dash: "3 3", opacity: 0.7 }, // 2-4 line
    { pts: [{ i: 8, price: 184 }, { i: 74, price: 210.4 }], tone: "gn", width: 1.8, opacity: 0.9 }, // 1-4 EPA target line
  ];
  const hlines = [
    { price: WF_EPA.price, label: `EPA target · ${WF_EPA.price}`, tone: "gn", dash: "5 4" },
    { price: 176, label: "Point 5 entry · 176", tone: "copper", dash: "2 4" },
    { price: 171, label: "Invalidate < 171", tone: "rd", dash: "3 3", labelBelow: true },
  ];
  const markers = WF_PTS.map(p => ({
    i: p.i, price: p.price, label: p.w === "5" ? "5 ⟳" : p.w,
    tone: p.tone || "violet", place: p.place,
  })).concat([{ i: WF_EPA.i, price: WF_EPA.price, label: "EPA", tone: "gn", place: "above" }]);
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} lines={lines}
                      skeleton={skeleton} skeletonTail={1} accent="violet" span={80} projectFrom={53} />;
}

const WF_RULES = [
  { rule: "Waves 3-4 contained within the 1-2 channel", detail: "symmetry holds", status: "PASS", tone: "gn" },
  { rule: "Point 5 overshoots the 1-3 line (sweet spot)", detail: "5 = 176 below 1-3 projection", status: "PASS", tone: "gn" },
  { rule: "Time symmetry · t(1→2) ≈ t(3→4)", detail: "10 ≈ 10 bars", status: "PASS", tone: "gn" },
  { rule: "Point 4 inside the 1-2 price range", detail: "196 < 199 (point 2)", status: "PASS", tone: "gn" },
  { rule: "Entry at 5 · EPA = 1-4 line projection", detail: "target rides the 1-4 line", status: "ACTIVE", tone: "violet" },
];
function WolfeRules({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Wolfe rule", k: "rule" }, { h: "Measurement", k: "detail", mono: true }, { h: "Status", k: "status", align: "right" }]}
    rows={WF_RULES.map(r => ({ rule: r.rule, detail: <span className="dim2" style={{ fontSize: 11 }}>{r.detail}</span>, status: <Pill tone={r.tone} small>{r.status}</Pill> }))} />;
}

function WolfeTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Level", k: "l" }, { h: "Basis", k: "b" }, { h: "Price", k: "p", mono: true, align: "right" }, { h: "Conf.", k: "c", align: "right" }]}
        rows={[
          { l: <b className="gn">EPA target</b>, b: <span className="dim2" style={{ fontSize: 11 }}>1-4 line, est. arrival bar 74 (~26d)</span>, p: <b>$210</b>, c: <ConfBar value={0.6} tone="gn" width={48} /> },
          { l: <b className="copper">Point-5 entry</b>, b: <span className="dim2" style={{ fontSize: 11 }}>sweet-spot reversal zone</span>, p: <b>$176</b>, c: <span className="dim mono">filled</span> },
          { l: <b className="rd">Invalidation</b>, b: <span className="dim2" style={{ fontSize: 11 }}>5 fails to hold / breaks lower</span>, p: <b>$171</b>, c: <span className="dim mono">stop</span> },
        ]} />
      <div className="pv-invalid">
        <span className="label-cap">EPA · estimated price at arrival</span>
        <span className="mono">Long from the point-5 sweet spot <b className="copper">$176</b> → rides the 1-4 line to <b className="up">$210</b> (R:R ≈ 5.7:1). Voids on a close below <b className="dn">$171</b>.</span>
      </div>
    </div>
  );
}

function WolfeLog() {
  const rows = [
    { w: "1", role: "Origin low", span: "→ 184", note: "start of the wedge", tone: "violet" },
    { w: "2", role: "First high", span: "184 → 199", note: "defines upper 2-4 line", tone: "violet" },
    { w: "3", role: "Lower low", span: "199 → 180", note: "below point 1 (widening)", tone: "violet" },
    { w: "4", role: "Lower high", span: "180 → 196", note: "inside 1-2 range", tone: "violet" },
    { w: "5", role: "Sweet spot ⟳", span: "196 → 176", note: "overshoots 1-3 line — the entry", tone: "copper" },
    { w: "EPA", role: "Projected", span: "176 → 210", note: "rides the 1-4 line to arrival", tone: "gn" },
  ];
  return (
    <div className="pv-timeline">
      {rows.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.w === "5" ? "is-current" : ""}`}>
          <div className="pv-tl-rail"><span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />{k < rows.length - 1 && <span className="pv-tl-line" />}</div>
          <div className="pv-tl-body">
            <div className="pv-tl-head"><span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.w}</span><span className="pv-tl-name">{e.role}</span><span className="pv-tl-meta mono dim">{e.span}</span></div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function WolfeStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Pattern</div><div className="pv-stat-v mono violet">Bullish Wolfe</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Structure</div><div className="pv-stat-v mono">5-point · valid</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Entry · point 5</div><div className="pv-stat-v mono copper">$176</div></div>
      <div className="pv-stat-cell"><div className="label-cap">EPA target</div><div className="pv-stat-v mono up">$210</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.6} tone="violet" width={72} /></div></div>
    </div>
  );
}

function WolfeView({ ticker, dir }) {
  const Chart = <WolfeChart ticker={ticker} height={dir === "C" ? 250 : 330} />;
  if (dir === "B") {
    return (
      <div className="pv-view">
        <WolfeStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Wolfe Wave — annotated" sub="5-point structure · channel lines · 1-4 EPA target" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Rule checks" style="minimal" />
            <div className="pv-pad"><WolfeRules dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Point log" style="minimal" />
            <div className="pv-pad"><WolfeLog /></div>
            <SectionHeader n={4} title="EPA target" style="minimal" />
            <div className="pv-pad"><WolfeTargets /></div>
          </div>
        </div>
      </div>
    );
  }
  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <WolfeStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div><div className="pv-block-h label-cap">Point log</div><WolfeLog /><div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Rule checks</div><WolfeRules dense /></div>
          <div><div className="pv-block-h label-cap">EPA target &amp; invalidation</div><WolfeTargets /></div>
        </div>
      </div>
    );
  }
  return (
    <div className="pv-view">
      <WolfeStat />
      <SectionHeader n={1} title="Wolfe Wave — annotated" sub="5-point reversal · 1-3-5 & 2-4 channel · 1-4 EPA target line on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div><div className="pv-block-h label-cap">Point-by-point log</div><WolfeLog /><div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Rule checks</div><WolfeRules /></div>
        <div><div className="pv-block-h label-cap">EPA · estimated price at arrival</div><WolfeTargets /></div>
      </div>
    </div>
  );
}

Object.assign(window, { WolfeView });
