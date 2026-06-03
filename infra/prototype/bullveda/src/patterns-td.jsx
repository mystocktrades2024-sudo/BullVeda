// patterns-td.jsx — TD Sequential (DeMark). TD Setup (1–9) + Countdown (1–13)
// exhaustion timing, TDST support/resistance, perfected-count logic. Timing layer:
// the "when", overlaid on everyone else's "where".

const { useMemo: useMemoTd } = React;

function useTd(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x4e9;
  return useMemoTd(() => {
    const anchors = [
      { i: 0, price: 196 }, { i: 8, price: 184 }, { i: 16, price: 195 }, { i: 24, price: 191 },
      { i: 32, price: 202 }, { i: 40, price: 206 }, { i: 46, price: 211 }, { i: 49, price: 213.4 },
    ];
    const bars = buildSeries({ n: 50, anchors, seed, volSpikes: {} });
    return { bars };
  }, [seed]);
}

function TdChart({ ticker, height = 320 }) {
  const { bars } = useTd(ticker);
  const hlines = [
    { price: 209.5, label: "TDST resistance 209.5", tone: "rd", dash: "4 4" },
    { price: 196.0, label: "TDST support 196.0", tone: "cy", dash: "4 4", labelBelow: true },
  ];
  const markers = [
    { i: 8, price: 184, label: "Buy Setup 9 ✓", tone: "gn", place: "below" },
    { i: 32, price: 202, label: "1", tone: "amb", place: "above" },
    { i: 40, price: 206, label: "5", tone: "amb", place: "above" },
    { i: 46, price: 211, label: "7", tone: "amb", place: "above" },
    { i: 49, price: 213.4, label: "8 ⟳", tone: "rd", place: "above" },
  ];
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} accent="amb" />;
}

const TD_SETUP = [
  { k: "Phase", v: "Sell Setup", tone: "amb" },
  { k: "Count", v: "8 of 9", tone: "amb" },
  { k: "Rule", v: "close > close[−4]", tone: "ink-1" },
  { k: "Perfected?", v: "pending bar 9", tone: "ink-2" },
  { k: "Bar-9 est.", v: "next session", tone: "rd" },
];
function TdSetupTable({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "TD Setup", k: "k" }, { h: "", k: "v", align: "right" }]}
    rows={TD_SETUP.map(r => ({ k: <span className="dim2">{r.k}</span>, v: <b style={{ color: `var(--${r.tone})` }}>{r.v}</b> }))} />;
}

const TD_LADDER = [
  { stage: "Buy Setup 9", state: "✓ complete (bar 9 at $184)", tone: "gn", note: "triggered the rally off the low" },
  { stage: "Buy Countdown 13", state: "✓ played out into markup", tone: "gn", note: "prior bullish phase" },
  { stage: "Sell Setup", state: "8 of 9 · in progress", tone: "amb", note: "momentum maturing near highs" },
  { stage: "Sell Countdown 13", state: "not started", tone: "ink-3", note: "begins only after Sell Setup 9" },
];
function TdLadder() {
  return (
    <div className="pv-timeline">
      {TD_LADDER.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.tone === "amb" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < TD_LADDER.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.stage}</span>
              <span className="pv-tl-meta mono dim">{e.state}</span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function TdTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Level", k: "l" }, { h: "Price", k: "p", mono: true, align: "right" }, { h: "Use", k: "u" }]}
        rows={[
          { l: <b className="rd">TDST resistance</b>, p: <b>$209.5</b>, r: "", u: <span className="dim2" style={{ fontSize: 11 }}>prior setup high · breaks = trend strong</span> },
          { l: <b className="cy">TDST support</b>, p: <b>$196.0</b>, u: <span className="dim2" style={{ fontSize: 11 }}>buy-setup base · fail = momentum lost</span> },
          { l: <b className="amb">Bar-9 risk level</b>, p: <b>$214–216</b>, u: <span className="dim2" style={{ fontSize: 11 }}>exhaustion zone · trail / lighten</span> },
        ]} />
      <div className="pv-invalid" style={{ borderColor: "var(--amb-dim)", background: "var(--amb-bg)" }}>
        <span className="label-cap" style={{ color: "var(--amb)" }}>Timing note</span>
        <span className="mono">Every other theory says GO; TD says momentum is <b className="warn">maturing</b>. A perfected Sell Setup 9 near <b className="warn">$214–216</b> flags a 1–4 bar pause/pullback — trail stops, don't chase.</span>
      </div>
    </div>
  );
}

function TdStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">TD Setup</div><div className="pv-stat-v mono warn">Sell 8/9</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Countdown</div><div className="pv-stat-v mono dim2">not started</div></div>
      <div className="pv-stat-cell"><div className="label-cap">TDST</div><div className="pv-stat-v mono">196 / 209.5</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Timing</div><div className="pv-stat-v mono warn">exhaustion near</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.57} tone="amb" width={72} /></div></div>
    </div>
  );
}

function TDSequentialView({ ticker, dir }) {
  const Chart = <TdChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <TdStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="TD Setup / Countdown — annotated" sub="exhaustion counts + TDST on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Sequence ladder" style="minimal" />
            <div className="pv-pad"><TdLadder /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Setup state" style="minimal" />
            <div className="pv-pad"><TdSetupTable /></div>
            <SectionHeader n={4} title="Levels" style="minimal" />
            <div className="pv-pad"><TdTargets /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <TdStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Sequence ladder</div>
            <TdLadder />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Setup state</div>
            <TdSetupTable dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Levels &amp; timing</div>
            <TdTargets />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pv-view">
      <TdStat />
      <SectionHeader n={1} title="TD Sequential — Setup & Countdown" sub="DeMark exhaustion timing · TDST levels on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Sequence ladder</div>
          <TdLadder />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Setup state</div>
          <TdSetupTable />
        </div>
        <div>
          <div className="pv-block-h label-cap">Levels &amp; timing</div>
          <TdTargets />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { TDSequentialView });
