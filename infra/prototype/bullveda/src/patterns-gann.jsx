// patterns-gann.jsx — W.D. Gann theory sub-tab.
// Gann fan (1×1, 2×1, 1×2…) from a pivot, Square-of-Nine price levels, and
// time-cycle turn dates. Price/time squaring — the one method that projects
// TIME, not just price.

const { useMemo: useMemoGn } = React;

const GN_PIVOT = { i: 8, price: 180 };
const GN_K = 0.6; // 1×1 = 0.6 price / bar (chart-scaled)

function useGann(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x3b9;
  return useMemoGn(() => {
    const anchors = [
      { i: 0, price: 188 }, { i: 8, price: 180 }, { i: 20, price: 192 }, { i: 30, price: 198 },
      { i: 42, price: 205 }, { i: 52, price: 213.4 },
    ];
    const bars = buildSeries({ n: 53, anchors, seed, volSpikes: {} });
    return { bars };
  }, [seed]);
}

function GannChart({ ticker, height = 330 }) {
  const { bars } = useGann(ticker);
  const end = 74;
  const fan = (mult, tone, dash) => ({ pts: [{ i: GN_PIVOT.i, price: GN_PIVOT.price }, { i: end, price: GN_PIVOT.price + GN_K * mult * (end - GN_PIVOT.i) }], tone, dash, width: mult === 1 ? 1.8 : 1.2, opacity: mult === 1 ? 0.95 : 0.6 });
  const lines = [
    fan(2, "gn", "4 4"),     // 2×1 steep
    fan(1, "copper", null),  // 1×1 key
    fan(0.5, "cy", "4 4"),   // 1×2 shallow
    fan(0.25, "ink-2", "3 4"), // 1×4
  ];
  const hlines = [
    { price: 219, label: "Sq9 · 219 (90°)", tone: "violet", dash: "2 5" },
    { price: 207, label: "Sq9 · 207 (45°)", tone: "violet", dash: "2 5" },
    { price: 232, label: "Sq9 · 232 (180°)", tone: "gn", dash: "5 4" },
  ];
  const markers = [{ i: GN_PIVOT.i, price: GN_PIVOT.price, label: "Pivot", tone: "copper", place: "below" }];
  const bands = [{ from: 37, to: 39, label: "T30", tone: "ink-3" }, { from: 67, to: 69, label: "T60", tone: "copper" }];
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} lines={lines} bands={bands} accent="copper" span={80} projectFrom={53} />;
}

const GN_ANGLES = [
  { a: "2×1", deg: "63.75°", now: "$252", role: "steep · only in strong trends", st: "above px", tone: "gn" },
  { a: "1×1", deg: "45°", now: "$216", role: "the master line · trend pivot", st: "px just below", tone: "copper" },
  { a: "1×2", deg: "26.25°", now: "$198", role: "support · shallow uptrend", st: "below px", tone: "cy" },
  { a: "1×4", deg: "15°", now: "$192", role: "last-ditch support", st: "below px", tone: "ink-2" },
];
function GannAngles({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Angle", k: "a", mono: true }, { h: "Slope", k: "deg", mono: true }, { h: "Value now", k: "now", mono: true, align: "right" }, { h: "Role", k: "role" }, { h: "vs price", k: "st", align: "right" }]}
    rows={GN_ANGLES.map(r => ({ a: <b style={{ color: `var(--${r.tone})` }}>{r.a}</b>, deg: <span className="dim2">{r.deg}</span>, now: <b>{r.now}</b>, role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span>, st: <Pill tone={r.tone === "ink-2" ? "ink" : r.tone} small>{r.st}</Pill> }))} />;
}

const GN_SQ9 = [
  { lvl: "$207", rot: "45°", role: "first resistance · cleared", tone: "gn" },
  { lvl: "$219", rot: "90°", role: "next overhead · cardinal", tone: "violet" },
  { lvl: "$232", rot: "180°", role: "measured Gann target", tone: "gn" },
  { lvl: "$196", rot: "315°", role: "support on a pullback", tone: "cy" },
];
function GannSq9({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Sq-9 level", k: "lvl", mono: true }, { h: "Rotation", k: "rot", mono: true }, { h: "Role", k: "role" }]}
    rows={GN_SQ9.map(r => ({ lvl: <b style={{ color: `var(--${r.tone})` }}>{r.lvl}</b>, rot: <span className="dim2">{r.rot}</span>, role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span> }))} />;
}

const GN_TIME = [
  { c: "30-bar count", date: "Jun 18", role: "minor turn window", tone: "ink-2" },
  { c: "60-bar count", date: "Jul 30", role: "major cycle · price-time square", tone: "copper" },
  { c: "90° in time", date: "Aug 14", role: "anniversary of pivot low", tone: "violet" },
];
function GannTime({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Time cycle", k: "c" }, { h: "Turn date", k: "date", mono: true }, { h: "Significance", k: "role" }]}
    rows={GN_TIME.map(r => ({ c: <b style={{ color: `var(--${r.tone})` }}>{r.c}</b>, date: <b>{r.date}</b>, role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span> }))} />;
}

function GannStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Master angle</div><div className="pv-stat-v mono copper">1×1 · $216</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Price vs 1×1</div><div className="pv-stat-v mono up">just below</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Next Sq9</div><div className="pv-stat-v mono violet">$219 (90°)</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Next time turn</div><div className="pv-stat-v mono">Jun 18</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.48} tone="amb" width={72} /></div></div>
    </div>
  );
}

function GannView({ ticker, dir }) {
  const Chart = <GannChart ticker={ticker} height={dir === "C" ? 250 : 330} />;
  if (dir === "B") {
    return (
      <div className="pv-view">
        <GannStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Gann fan + Sq-9 — annotated" sub="angles from pivot · square-of-nine levels · time cycles" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Gann angles" style="minimal" />
            <div className="pv-pad"><GannAngles dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Square of Nine" style="minimal" />
            <div className="pv-pad"><GannSq9 /></div>
            <SectionHeader n={4} title="Time cycles" style="minimal" />
            <div className="pv-pad"><GannTime /></div>
          </div>
        </div>
      </div>
    );
  }
  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <GannStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div><div className="pv-block-h label-cap">Gann angles</div><GannAngles dense /><div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Square of Nine</div><GannSq9 dense /></div>
          <div><div className="pv-block-h label-cap">Time cycles · turn dates</div><GannTime dense /></div>
        </div>
      </div>
    );
  }
  return (
    <div className="pv-view">
      <GannStat />
      <SectionHeader n={1} title="Gann fan + Square of Nine — annotated" sub="1×1 master line · price angles from the pivot · Sq-9 levels · time-cycle turns" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div><div className="pv-block-h label-cap">Gann angles</div><GannAngles /><div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Square of Nine levels</div><GannSq9 /></div>
        <div>
          <div className="pv-block-h label-cap">Time cycles · projected turns</div><GannTime />
          <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", margin: "12px 16px" }}>
            <span className="label-cap">Read</span>
            <span className="mono">Price rides just under the <b className="copper">1×1 master line ($216)</b>; holding above 1×2 keeps the uptrend intact. Gann's edge is <b>time</b> — the 60-bar count (Jul 30) squares price &amp; time and is the higher-probability turn window. Polarizing method — use as a confluence overlay, not a standalone trigger.</span>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GannView });
