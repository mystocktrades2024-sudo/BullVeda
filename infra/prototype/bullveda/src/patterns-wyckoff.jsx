// patterns-wyckoff.jsx — Wyckoff sub-tab: accumulation schematic annotated on
// real bars, A–E phase track, full event timeline, effort-vs-result reads, and
// a P&F target / invalidation table with confidence.

const { useMemo: useMemoWy } = React;

const WY_BARS = 78;

// event anchors drive both the chart and the timeline (single source of truth)
const WY_EVENTS = [
  { i: 6,  code: "PS",     name: "Preliminary Support",  date: "Mar 03", price: 206.0, phase: "A", place: "above", tone: "ink-2",
    note: "First sizeable buying after the down-move — supply still dominant." },
  { i: 10, code: "SC",     name: "Selling Climax",       date: "Mar 09", price: 190.0, phase: "A", place: "below", tone: "gn", wick: 186.4,
    note: "Panic low on extreme volume; wide bar closes off the lows — demand appears." },
  { i: 16, code: "AR",     name: "Automatic Rally",      date: "Mar 17", price: 205.0, phase: "A", place: "above", tone: "gn",
    note: "Supply exhausted; rally defines the top of the trading range." },
  { i: 24, code: "ST",     name: "Secondary Test",       date: "Mar 27", price: 193.0, phase: "B", place: "below", tone: "gn",
    note: "Re-tests SC zone on lighter volume / narrower spread — supply diminishing." },
  { i: 40, code: "Spring", name: "Spring (Shakeout)",    date: "Apr 18", price: 191.0, phase: "C", place: "below", tone: "copper", wick: 187.6,
    note: "Undercuts range low then snaps back inside — last supply absorbed." },
  { i: 46, code: "Test",   name: "Test of Spring",       date: "Apr 26", price: 197.0, phase: "C", place: "below", tone: "gn",
    note: "Higher low on the lowest volume of the base — no sellers left." },
  { i: 54, code: "SOS",    name: "Sign of Strength",     date: "May 07", price: 209.0, phase: "D", place: "above", tone: "gn",
    note: "Wide-spread advance on expanding volume clears the AR / range top." },
  { i: 60, code: "LPS",    name: "Last Point of Support", date: "May 15", price: 206.0, phase: "D", place: "below", tone: "gn",
    note: "Pullback holds above resistance-turned-support on light volume." },
  { i: 64, code: "BU",     name: "Back-Up to Edge",      date: "May 21", price: 210.0, phase: "D", place: "above", tone: "copper",
    note: "Final re-accumulation before mark-up — current location." },
];

const WY_PHASES = [
  { id: "A", label: "A · Stopping action", from: 4,  to: 17, done: true,  note: "PS · SC · AR — the down-move is halted" },
  { id: "B", label: "B · Building cause",  from: 17, to: 38, done: true,  note: "ST · ranging — cause accumulates" },
  { id: "C", label: "C · Test",            from: 38, to: 48, done: true,  note: "Spring + Test — supply removed" },
  { id: "D", label: "D · Mark-up begins",  from: 48, to: 66, done: false, current: true, note: "SOS · LPS · BU — demand in control" },
  { id: "E", label: "E · Trend",           from: 66, to: 77, done: false, note: "Mark-up out of the range" },
];

const WY_RANGE = { support: 189.0, resistance: 205.0 };

function useWyckoff(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x9e3;
  return useMemoWy(() => {
    const anchors = [
      { i: 0, price: 224 }, { i: 6, price: 206 }, { i: 10, price: 190 }, { i: 16, price: 205 },
      { i: 24, price: 193 }, { i: 30, price: 200 }, { i: 36, price: 194 }, { i: 40, price: 191 },
      { i: 46, price: 197 }, { i: 54, price: 209 }, { i: 60, price: 206 }, { i: 64, price: 210 },
      { i: 70, price: 215 }, { i: 77, price: 213.4 },
    ];
    const volSpikes = { 10: 3.1, 16: 1.5, 24: 0.6, 40: 1.9, 54: 2.3, 60: 0.55, 64: 0.7 };
    const wicks = {}; WY_EVENTS.forEach(e => { if (e.wick) wicks[e.i] = e.wick; });
    const bars = buildSeries({ n: WY_BARS, anchors, seed, volSpikes, wicks });
    return { bars };
  }, [seed]);
}

// ── chart with phase bands + events + range lines ───────────────
function WyckoffChart({ ticker, height = 320 }) {
  const { bars } = useWyckoff(ticker);
  const bands = WY_PHASES.map(p => ({ from: p.from, to: p.to, label: p.id, tone: p.current ? "copper" : "ink-3" }));
  const hlines = [
    { price: WY_RANGE.resistance, label: `Resistance ${WY_RANGE.resistance.toFixed(0)}`, tone: "ink-2", dash: "2 4" },
    { price: WY_RANGE.support, label: `Support ${WY_RANGE.support.toFixed(0)}`, tone: "ink-2", dash: "2 4" },
    { price: 221, label: "T1 P&F 221", tone: "gn", dash: "5 4" },
    { price: 187.6, label: "Invalidate 187.6", tone: "rd", dash: "3 3", labelBelow: true },
  ];
  const markers = WY_EVENTS.map(e => ({ i: e.i, label: e.code, tone: e.tone, place: e.place }));
  return <CandleChart bars={bars} height={height} bands={bands} hlines={hlines} markers={markers} accent="copper" />;
}

// ── A–E phase track ─────────────────────────────────────────────
function WyckoffPhases() {
  return (
    <div className="pv-phases">
      {WY_PHASES.map(p => (
        <div key={p.id} className={`pv-phase ${p.current ? "is-current" : p.done ? "is-done" : "is-future"}`}>
          <div className="pv-phase-top">
            <span className="pv-phase-id mono">{p.id}</span>
            {p.current ? <Pill tone="copper" small>NOW</Pill> : p.done ? <span className="pv-phase-check">✓</span> : <span className="pv-phase-dot" />}
          </div>
          <div className="pv-phase-label mono">{p.label.replace(/^[A-E] · /, "")}</div>
          <div className="pv-phase-note">{p.note}</div>
        </div>
      ))}
    </div>
  );
}

// ── event timeline (detailed log) ───────────────────────────────
function WyckoffTimeline() {
  return (
    <div className="pv-timeline">
      {WY_EVENTS.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.code === "BU" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < WY_EVENTS.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.code}</span>
              <span className="pv-tl-name">{e.name}</span>
              <span className="pv-tl-meta mono dim">Ph {e.phase} · {e.date} · <b>${e.price.toFixed(1)}</b></span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── effort-vs-result reads ──────────────────────────────────────
const WY_ER = [
  { ev: "SC",     name: "Selling Climax",       effort: "3.1× vol", result: "wide ▼, closes mid-bar", read: "Demand absorbs climactic supply", tone: "gn" },
  { ev: "AR",     name: "Automatic Rally",      effort: "1.5× vol", result: "wide ▲ off the low", read: "Buyers in control — defines TR top", tone: "gn" },
  { ev: "ST",     name: "Secondary Test",       effort: "0.6× vol", result: "narrow, higher low", read: "Supply diminishing on the test", tone: "gn" },
  { ev: "Spring", name: "Spring / Shakeout",    effort: "1.9× vol", result: "undercut then reclaim", read: "Effort to push down → no result", tone: "gn" },
  { ev: "SOS",    name: "Sign of Strength",     effort: "2.3× vol", result: "widest ▲, closes high", read: "Effort = result — markup confirmed", tone: "gn" },
  { ev: "LPS",    name: "Last Point of Support", effort: "0.55× vol", result: "shallow pullback holds", read: "No supply on the reaction", tone: "gn" },
];
function WyckoffEffort({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Event", k: "ev" }, { h: "Effort (vol)", k: "effort", mono: true },
           { h: "Result (spread/close)", k: "result" }, { h: "Read", k: "read" }]}
    rows={WY_ER.map(r => ({ ...r, ev: <span><b style={{ color: `var(--${r.tone})` }}>{r.name}</b> <span className="dim mono" style={{ fontSize: 10 }}>{r.ev}</span></span> }))} />;
}

// ── point-&-figure targets + invalidation ───────────────────────
const WY_TGT = [
  { label: "T1 · conservative", basis: "TR height (16) added to 205", price: "221.0", rr: "+3.6%", conf: 0.72, tone: "gn" },
  { label: "T2 · measured",     basis: "1.6× count → 205 + 26",       price: "231.0", rr: "+8.2%", conf: 0.54, tone: "gn" },
  { label: "T3 · full count",   basis: "2.0× count → 205 + 32",       price: "237.0", rr: "+11.1%", conf: 0.38, tone: "amb" },
];
function WyckoffTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Objective", k: "label" }, { h: "Basis (cause → effect)", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" }, { h: "R:R", k: "rr", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={WY_TGT.map(t => ({
          label: <span><b style={{ color: `var(--${t.tone})` }}>{t.label.split(" · ")[0]}</b> <span className="dim">· {t.label.split(" · ")[1]}</span></span>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>, rr: <span className="up">{t.rr}</span>,
          conf: <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">Daily close back below the Spring low <b className="dn">$187.60</b> — re-distribution, stand aside.</span>
      </div>
    </div>
  );
}

// ── header strip (verdict) ──────────────────────────────────────
function WyckoffStat() {
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Schematic</div><div className="pv-stat-v mono">Accumulation #1</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Phase</div><div className="pv-stat-v mono copper">D · mark-up</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Range</div><div className="pv-stat-v mono">189 – 205</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Composite Operator</div><div className="pv-stat-v mono up">ACCUMULATING</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={0.71} tone="copper" width={72} /></div></div>
    </div>
  );
}

// ── view assembler (3 directions) ───────────────────────────────
function WyckoffView({ ticker, dir }) {
  const Chart = <WyckoffChart ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    // SPLIT — chart left, stacked analysis right
    return (
      <div className="pv-view">
        <WyckoffStat />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Accumulation — annotated" sub="events pinned to real bars · A–E phase bands" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Effort vs Result" sub="volume against spread & close" style="minimal" />
            <div className="pv-pad"><WyckoffEffort dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Phase track" style="minimal" />
            <div className="pv-pad"><WyckoffPhases /></div>
            <SectionHeader n={4} title="P&F targets" style="minimal" />
            <div className="pv-pad"><WyckoffTargets /></div>
          </div>
        </div>
        <SectionHeader n={5} title="Event timeline" sub="schematic, dated & scored" style="minimal" />
        <div className="pv-pad"><WyckoffTimeline /></div>
      </div>
    );
  }

  if (dir === "C") {
    // DOSSIER — compact chart, data-dense tables stacked
    return (
      <div className="pv-view pv-view--dossier">
        <WyckoffStat />
        <div className="pv-pad">{Chart}</div>
        <WyckoffPhases />
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Event log</div>
            <WyckoffTimeline />
          </div>
          <div>
            <div className="pv-block-h label-cap">Effort vs result</div>
            <WyckoffEffort dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Targets &amp; invalidation</div>
            <WyckoffTargets />
          </div>
        </div>
      </div>
    );
  }

  // A — CHART-LED (default)
  return (
    <div className="pv-view">
      <WyckoffStat />
      <SectionHeader n={1} title="Accumulation schematic — annotated" sub="PS · SC · AR · ST · Spring · Test · SOS · LPS · BU on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <WyckoffPhases />
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Event timeline</div>
          <WyckoffTimeline />
        </div>
        <div>
          <div className="pv-block-h label-cap">Effort vs result</div>
          <WyckoffEffort />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>P&amp;F targets &amp; invalidation</div>
          <WyckoffTargets />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { WyckoffView });
