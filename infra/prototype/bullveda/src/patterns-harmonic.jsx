// patterns-harmonic.jsx — Harmonic (Fibonacci) patterns theory sub-tab.
// A bullish Gartley XABCD drawn on real bars with the PRZ band, a fib-ratio
// validation table (actual vs ideal + pass/fail), and a target / invalidation
// table with confidence.

const { useMemo: useMemoHm } = React;

// XABCD pivots (price + bar index). D is the completed PRZ low that launched the move.
const HM_PTS = [
  { i: 6,  price: 178.0, label: "X", place: "below", tone: "violet" },
  { i: 22, price: 212.0, label: "A", place: "above", tone: "violet" },
  { i: 34, price: 191.0, label: "B", place: "below", tone: "violet" },
  { i: 44, price: 205.0, label: "C", place: "above", tone: "violet" },
  { i: 56, price: 185.3, label: "D", place: "below", tone: "gn" },
];

function useHarmonic(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x7d2;
  return useMemoHm(() => {
    const anchors = [
      { i: 0, price: 188 }, { i: 6, price: 178 }, { i: 14, price: 198 }, { i: 22, price: 212 },
      { i: 28, price: 199 }, { i: 34, price: 191 }, { i: 39, price: 199 }, { i: 44, price: 205 },
      { i: 50, price: 193 }, { i: 56, price: 185.3 }, { i: 62, price: 200 }, { i: 65, price: 213.4 },
    ];
    const volSpikes = { 6: 1.5, 22: 1.4, 56: 2.1, 57: 1.7 };
    const bars = buildSeries({ n: 66, anchors, seed, volSpikes });
    return { bars };
  }, [seed]);
}

function HarmonicChart({ ticker, height = 320 }) {
  const { bars } = useHarmonic(ticker);
  // XABCD skeleton, then dashed projection from D to current price
  const skeleton = HM_PTS.map(p => ({ i: p.i, price: p.price })).concat([{ i: 65, price: 213.4 }]);
  const zones = [{ lo: 184.0, hi: 187.5, tone: "gn", label: "PRZ 184.0–187.5" }];
  const hlines = [
    { price: 201.8, label: "T2 · 0.618 AD · 201.8", tone: "gn", dash: "5 4" },
    { price: 212.0, label: "T3 · A retest · 212", tone: "gn", dash: "5 4" },
    { price: 178.0, label: "Invalidate < X · 178", tone: "rd", dash: "3 3", labelBelow: true },
  ];
  const markers = HM_PTS.map(p => ({ i: p.i, price: p.price, label: p.label, tone: p.tone, place: p.place }));
  return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers} zones={zones}
                      skeleton={skeleton} skeletonTail={1} accent="violet" span={72} projectFrom={56} />;
}

// fib-ratio validation: actual vs ideal Gartley ratios
const HM_RATIOS = [
  { leg: "AB / XA", actual: "0.618", ideal: "0.618", status: "PASS", tone: "gn" },
  { leg: "BC / AB", actual: "0.667", ideal: "0.382 – 0.886", status: "PASS", tone: "gn" },
  { leg: "CD / BC", actual: "1.46", ideal: "1.272 – 1.618", status: "PASS", tone: "gn" },
  { leg: "AD / XA", actual: "0.786", ideal: "0.786", status: "EXACT", tone: "violet" },
];
function HarmonicRatios({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Leg ratio", k: "leg", mono: true }, { h: "Actual", k: "actual", mono: true, align: "right" },
           { h: "Ideal (Gartley)", k: "ideal", mono: true, align: "right" }, { h: "Status", k: "status", align: "right" }]}
    rows={HM_RATIOS.map(r => ({ leg: r.leg, actual: <b>{r.actual}</b>,
      ideal: <span className="dim2">{r.ideal}</span>, status: <Pill tone={r.tone} small>{r.status}</Pill> }))} />;
}

// XABCD point log
const HM_LOG = [
  { p: "X", role: "Origin low", date: "Mar 03", price: "178.0", note: "Swing low — pattern anchor", tone: "violet" },
  { p: "A", role: "Impulse high", date: "Mar 25", price: "212.0", note: "XA leg defines the structure", tone: "violet" },
  { p: "B", role: "0.618 retr", date: "Apr 09", price: "191.0", note: "Textbook Gartley B at .618 of XA", tone: "violet" },
  { p: "C", role: "Reaction high", date: "Apr 21", price: "205.0", note: "0.667 of AB — within tolerance", tone: "violet" },
  { p: "D", role: "PRZ completion", date: "May 06", price: "185.3", note: "0.786 XA — buy zone, reversed up", tone: "gn" },
];
function HarmonicLog() {
  return (
    <div className="pv-timeline">
      {HM_LOG.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.p === "D" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < HM_LOG.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.p}</span>
              <span className="pv-tl-name">{e.role}</span>
              <span className="pv-tl-meta mono dim">{e.date} · <b>${e.price}</b></span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

const HM_TGT = [
  { label: "T1 · 0.382 AD", basis: "0.382 of the AD leg from D", price: "195.5", rr: "hit ✓", conf: 0.74, tone: "gn" },
  { label: "T2 · 0.618 AD", basis: "0.618 of the AD leg", price: "201.8", rr: "hit ✓", conf: 0.62, tone: "gn" },
  { label: "T3 · A retest", basis: "return to point A", price: "212.0", rr: "testing", conf: 0.48, tone: "amb" },
  { label: "Extension · 1.0 AD", basis: "full AD projected from D", price: "212.0+", rr: "stretch", conf: 0.3, tone: "ink-2" },
];
function HarmonicTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Target", k: "label" }, { h: "Fib basis", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" }, { h: "State", k: "rr", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={HM_TGT.map(t => ({
          label: <b style={{ color: `var(--${t.tone})` }}>{t.label}</b>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>,
          rr: t.rr.includes("hit") ? <span className="up">{t.rr}</span> : <span className="dim">{t.rr}</span>,
          conf: <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">A close below point <b className="dn">X · $178.00</b> voids the Gartley; the structure failed if D breaks before T3.</span>
      </div>
    </div>
  );
}

function HarmonicStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Pattern</div><div className="pv-stat-v mono violet">Bullish Gartley</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Completion</div><div className="pv-stat-v mono up">D confirmed</div></div>
      <div className="pv-stat-cell"><div className="label-cap">PRZ</div><div className="pv-stat-v mono">184.0 – 187.5</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Next target</div><div className="pv-stat-v mono up">$212 (A)</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Pattern confidence</div><div className="pv-stat-v"><ConfBar value={0.69} tone="violet" width={72} /></div></div>
    </div>
  );
}

function HarmonicView({ ticker, dir }) {
  const Chart = <HarmonicChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        <HarmonicStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="XABCD — annotated" sub="Gartley structure + PRZ on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Fib-ratio validation" style="minimal" />
            <div className="pv-pad"><HarmonicRatios dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="XABCD points" style="minimal" />
            <div className="pv-pad"><HarmonicLog /></div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad"><HarmonicTargets /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <HarmonicStat />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">XABCD point log</div>
            <HarmonicLog />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Fib-ratio validation</div>
            <HarmonicRatios dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
            <HarmonicTargets />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led
  return (
    <div className="pv-view">
      <HarmonicStat />
      <SectionHeader n={1} title="Bullish Gartley — annotated" sub="XABCD pivots · PRZ band · fib targets on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">XABCD point log</div>
          <HarmonicLog />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Fib-ratio validation</div>
          <HarmonicRatios />
        </div>
        <div>
          <div className="pv-block-h label-cap">Fib targets &amp; invalidation</div>
          <HarmonicTargets />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { HarmonicView });
