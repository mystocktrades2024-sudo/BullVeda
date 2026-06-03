// patterns-elliott.jsx — Elliott sub-tab: impulse 1-2-3-4-5 + projected A-B-C
// drawn on real bars with a wave skeleton, fib target/extension table, alternate
// counts with probabilities, wave-rule checks, and a wave-by-wave log.

const { useMemo: useMemoEw, useState: useStateEw } = React;

// degree notation — each degree labels its waves differently (ruleset §D2)
const EW_NOTATE = {
  primary: (w) => `[${w}]`,
  intermediate: (w) => `(${w})`,
  minor: (w) => `${w}`,
};

// per-degree structure: own bars (different TF), wave pivots, targets.
// Self-similar — each degree is currently in its wave 3.
const EW_DEG_CFG = {
  primary: {
    tf: "Weekly", accent: "blue",
    anchors: [{ i: 0, price: 128 }, { i: 6, price: 120 }, { i: 16, price: 156 }, { i: 22, price: 165 }, { i: 30, price: 140 }, { i: 40, price: 186 }, { i: 46, price: 204 }, { i: 52, price: 213.4 }],
    nReal: 53, span: 82, projectFrom: 53,
    pivots: [
      { i: 6, price: 120, w: "0", place: "below" },
      { i: 22, price: 165, w: "1", place: "above" },
      { i: 30, price: 140, w: "2", place: "below", tone: "rd" },
      { i: 52, price: 213.4, w: "3", current: true, place: "above" },
      { i: 64, price: 188, w: "4", proj: true, place: "below" },
      { i: 78, price: 242, w: "5", proj: true, place: "above" },
    ],
    hlines: [
      { price: 242, label: "[5] target · 242", tone: "gn", dash: "5 4" },
      { price: 140, label: "Invalidate < [2] · 140", tone: "rd", dash: "3 3", labelBelow: true },
      { price: 165, label: "[1] top · 165", tone: "ink-2", dash: "2 4" },
    ],
  },
  intermediate: {
    tf: "Daily", accent: "violet",
    anchors: [{ i: 0, price: 188 }, { i: 8, price: 178 }, { i: 13, price: 188 }, { i: 18, price: 196 }, { i: 23, price: 189 }, { i: 28, price: 185 }, { i: 36, price: 200 }, { i: 41, price: 207 }, { i: 46, price: 213.4 }],
    nReal: 47, span: 86, projectFrom: 47,
    pivots: [
      { i: 8, price: 178, w: "0", place: "below" },
      { i: 18, price: 196, w: "1", place: "above" },
      { i: 28, price: 184.9, w: "2", place: "below", tone: "rd" },
      { i: 46, price: 213.4, w: "3", current: true, place: "above" },
      { i: 54, price: 203.5, w: "4", proj: true, place: "below" },
      { i: 66, price: 224.0, w: "5", proj: true, place: "above" },
    ],
    abc: [{ i: 71, price: 210, w: "A" }, { i: 76, price: 219, w: "B" }, { i: 82, price: 204, w: "C" }],
    hlines: [
      { price: 214.6, label: "(3) = 1.618×(1) · 214.6", tone: "violet", dash: "5 4" },
      { price: 224.0, label: "(5) target · 224", tone: "gn", dash: "5 4" },
      { price: 184.9, label: "Invalidate < (2) · 184.9", tone: "rd", dash: "3 3", labelBelow: true },
      { price: 196.0, label: "(1) top · 196", tone: "ink-2", dash: "2 4" },
    ],
  },
  minor: {
    tf: "4-Hour", accent: "copper",
    anchors: [{ i: 0, price: 189 }, { i: 6, price: 184.9 }, { i: 14, price: 196 }, { i: 22, price: 190 }, { i: 30, price: 203 }, { i: 36, price: 208 }, { i: 40, price: 213.4 }],
    nReal: 41, span: 62, projectFrom: 41,
    pivots: [
      { i: 6, price: 184.9, w: "0", place: "below" },
      { i: 14, price: 196, w: "1", place: "above" },
      { i: 22, price: 190, w: "2", place: "below", tone: "rd" },
      { i: 40, price: 213.4, w: "3", current: true, place: "above" },
      { i: 48, price: 206, w: "4", proj: true, place: "below" },
      { i: 58, price: 222, w: "5", proj: true, place: "above" },
    ],
    hlines: [
      { price: 222, label: "5 target · 222", tone: "gn", dash: "5 4" },
      { price: 184.9, label: "Invalidate < 2 · 184.9", tone: "rd", dash: "3 3", labelBelow: true },
      { price: 196, label: "1 top · 196", tone: "ink-2", dash: "2 4" },
    ],
  },
};

function useEWBars(ticker, degree) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x5a1;
  const cfg = EW_DEG_CFG[degree];
  return useMemoEw(() => buildSeries({ n: cfg.nReal, anchors: cfg.anchors, seed: seed ^ degree.length }), [seed, degree]);
}

// degree selector — redraws the wave pattern at the chosen degree
function ElliottDegreeSel({ deg, onDeg }) {
  const opts = [["primary", "Primary", "[W]"], ["intermediate", "Intermediate", "(D)"], ["minor", "Minor", "4H"]];
  return (
    <div className="pv-degsel">
      <span className="pv-degsel-cap label-cap">Draw degree</span>
      {opts.map(([id, nm, tf]) => (
        <button key={id} className={`pv-degsel-btn pv-degsel-btn--${EW_DEG_CFG[id].accent} ${deg === id ? "is-on" : ""}`} onClick={() => onDeg(id)}>
          {nm} <span className="pv-degsel-tf mono">{tf}</span>
        </button>
      ))}
    </div>
  );
}

function ElliottChart({ ticker, degree = "intermediate", height = 330 }) {
  const cfg = EW_DEG_CFG[degree];
  const bars = useEWBars(ticker, degree);
  const note = EW_NOTATE[degree];
  const abc = cfg.abc || [];
  const skeleton = cfg.pivots.map(p => ({ i: p.i, price: p.price })).concat(abc.map(p => ({ i: p.i, price: p.price })));
  const tail = cfg.pivots.filter(p => p.proj).length + abc.length;
  const markers = cfg.pivots.map(p => ({
    i: p.i, price: p.price,
    label: p.w === "0" ? "0" : (p.current ? `${note(p.w)} ⟳` : note(p.w)),
    tone: p.proj ? "ink-3" : (p.tone || cfg.accent), place: p.place,
  })).concat(abc.map(p => ({ i: p.i, price: p.price, label: note(p.w), tone: "amb", place: p.w === "B" ? "above" : "below" })));
  return <CandleChart bars={bars} height={height} hlines={cfg.hlines} markers={markers}
                      skeleton={skeleton} skeletonTail={tail} accent={cfg.accent} span={cfg.span} projectFrom={cfg.projectFrom} />;
}

// ── fib targets / extensions ────────────────────────────────────
const EW_TGT = [
  { label: "W3 target", basis: "1.618 × W1 (18.0) from W2 low", price: "214.6", note: "primary", conf: 0.61, tone: "violet" },
  { label: "W3 extension", basis: "2.618 × W1 from W2 low", price: "232.0", note: "if W3 extends", conf: 0.28, tone: "amb" },
  { label: "W4 retrace", basis: "0.382 × W3 (zone)", price: "203–205", note: "must stay > 196", conf: null, tone: "ink-2" },
  { label: "W5 target", basis: "W5 = W1 from W4 low", price: "221.4", note: "min objective", conf: 0.47, tone: "gn" },
  { label: "W5 extension", basis: "0.618 × (W1→W3)", price: "228.0", note: "stretch", conf: 0.31, tone: "gn" },
];
function ElliottTargets() {
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Level", k: "label" }, { h: "Fib basis", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={EW_TGT.map(t => ({
          label: <span><b style={{ color: `var(--${t.tone})` }}>{t.label}</b><br /><span className="dim" style={{ fontSize: 10 }}>{t.note}</span></span>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>{t.price.includes("–") ? t.price : `$${t.price}`}</b>,
          conf: t.conf == null ? <span className="dim mono">zone</span> : <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">Close below the W2 low <b className="dn">$184.90</b> negates the impulse count (W2 cannot exceed 100% of W1).</span>
      </div>
    </div>
  );
}

// ── alternate counts w/ probabilities ───────────────────────────
const EW_ALT = [
  { name: "Primary — bullish impulse", loc: "In Wave 3 of 5", p: 0.58, tone: "gn",
    note: "Five-wave advance from 178; W3 testing 1.618× extension, 4 & 5 to follow." },
  { name: "Alternate — W3 complete", loc: "Starting Wave 4", p: 0.27, tone: "amb",
    note: "W3 topped at 213.4; expect a 0.382 pullback toward 203–205 before W5." },
  { name: "Bearish — corrective", loc: "In Wave C of ABC", p: 0.15, tone: "rd",
    note: "Whole advance is a counter-trend ABC; rejection here resumes the down-trend." },
];
function ElliottAlts() {
  return (
    <div className="pv-alts">
      {EW_ALT.map((a, k) => (
        <div key={k} className={`pv-alt pv-alt--${a.tone}`}>
          <div className="pv-alt-head">
            <span className="pv-alt-name">{a.name}</span>
            <span className="pv-alt-p mono" style={{ color: `var(--${a.tone})` }}>{Math.round(a.p * 100)}%</span>
          </div>
          <div className="pv-alt-bar"><span style={{ width: `${a.p * 100}%`, background: `var(--${a.tone})` }} /></div>
          <div className="pv-alt-loc mono dim2">{a.loc}</div>
          <div className="pv-alt-note">{a.note}</div>
        </div>
      ))}
    </div>
  );
}

// ── wave-rule checks — 3 ABSOLUTE (hard) rules + guidelines (per ruleset v2) ──
const EW_RULES = [
  { rule: "Wave 2 never retraces > 100% of Wave 1", type: "HARD", detail: "W2 low 184.9 > W1 origin 178.0", status: "PASS", tone: "gn" },
  { rule: "Wave 3 is never the shortest of 1·3·5", type: "HARD", detail: "W3 ≈ 28.5 > W1 18.0 (W5 pending)", status: "PASS", tone: "gn" },
  { rule: "Wave 4 never enters Wave 1 territory", type: "HARD", detail: "W4 must hold above W1 high 196.0", status: "WATCH", tone: "amb" },
  { rule: "Wave 3 extends ≥ 1.618 × W1", type: "GUIDE", detail: "1.55× now → extension target 214.6", status: "NEAR", tone: "violet" },
  { rule: "Alternation — W2 sharp ⇄ W4 sideways", type: "GUIDE", detail: "W2 zigzag (.62) → W4 expect flat/triangle (.382)", status: "OK", tone: "gn" },
  { rule: "Wave 2 retraces 50–78.6% of W1", type: "GUIDE", detail: ".62 within band", status: "PASS", tone: "gn" },
];
function ElliottRules({ dense }) {
  return <MiniTable dense={dense}
    cols={[{ h: "Rule / guideline", k: "rule" }, { h: "Type", k: "type", align: "center" },
           { h: "Measurement", k: "detail", mono: true }, { h: "Status", k: "status", align: "right" }]}
    rows={EW_RULES.map(r => ({
      rule: r.rule,
      type: <Pill tone={r.type === "HARD" ? "rd" : "ink"} small outline>{r.type === "HARD" ? "HARD" : "GUIDE"}</Pill>,
      detail: <span className="dim2" style={{ fontSize: 11 }}>{r.detail}</span>,
      status: <Pill tone={r.tone} small>{r.status}</Pill>,
    }))} />;
}

// per-degree headline meta (drives the stat block, engine tag, degrees-table highlight)
const EW_DEG_META = {
  primary:      { id: "primary",      name: "Primary",      tone: "blue",   tol: "±5%",   w5: "$242",   w3: "$213.4" },
  intermediate: { id: "intermediate", name: "Intermediate", tone: "violet", tol: "±3.5%", w5: "$224.0", w3: "$214.6" },
  minor:        { id: "minor",        name: "Minor",        tone: "copper", tol: "±2.5%", w5: "$222",   w3: "$208" },
};

// ── the 9 degrees of Elliott Wave (engine tracks Primary/Intermediate/Minor) ──
const EW_DEGREES = [
  { n: 1, deg: "Grand Supercycle", note: "((I))–((V))", tf: "Monthly", dur: "50–100+ yr", tol: "±8%", mult: "—", live: false },
  { n: 2, deg: "Supercycle", note: "(I)–(V)", tf: "Monthly", dur: "5–20 yr", tol: "±7%", mult: "—", live: false },
  { n: 3, deg: "Cycle", note: "I–V", tf: "Weekly", dur: "1–5 yr", tol: "±6%", mult: "—", live: false },
  { n: 4, deg: "Primary", id: "primary", note: "[1]–[5]", tf: "Weekly", dur: "6–24 mo", tol: "±5%", mult: "0.4–1.0×", live: true, tone: "blue" },
  { n: 5, deg: "Intermediate", id: "intermediate", note: "(1)–(5)", tf: "Daily", dur: "2–6 mo", tol: "±3.5%", mult: "1.0× full", live: true, tone: "violet" },
  { n: 6, deg: "Minor", id: "minor", note: "1–5", tf: "4-Hour", dur: "2–8 wk", tol: "±2.5%", mult: "±0.1× adj", live: true, tone: "copper" },
  { n: 7, deg: "Minute", note: "i–v", tf: "1-Hour", dur: "1–3 wk", tol: "±2%", mult: "—", live: false },
  { n: 8, deg: "Minuette", note: "[i]–[v]", tf: "15-Min", dur: "days", tol: "±1.5%", mult: "—", live: false },
  { n: 9, deg: "Subminuette", note: "(i)–(v)", tf: "5-Min", dur: "hours", tol: "±1%", mult: "—", live: false },
];
function ElliottDegrees({ dense, deg = "intermediate" }) {
  const note = EW_NOTATE[deg] || EW_NOTATE.intermediate;
  return (
    <table className={`pv-table pv-degtbl ${dense ? "is-dense" : ""}`}>
      <thead><tr>
        <th className="label-cap" style={{ textAlign: "right" }}>#</th>
        <th className="label-cap">Degree</th>
        <th className="label-cap">Labels</th>
        <th className="label-cap">TF</th>
        <th className="label-cap">Duration</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Fib tol</th>
        <th className="label-cap" style={{ textAlign: "right" }}>Score ×</th>
        <th className="label-cap" style={{ textAlign: "center" }}>Engine</th>
      </tr></thead>
      <tbody>
        {EW_DEGREES.map((d) => {
          const isCur = d.id === deg;
          return (
            <tr key={d.n} className={isCur ? "pv-deg-cur" : d.live ? "pv-deg-live" : ""}>
              <td className="mono dim2" style={{ textAlign: "right" }}>{d.n}</td>
              <td>
                <b style={{ color: d.live ? `var(--${d.tone})` : "var(--ink-2)" }}>{d.deg}</b>
                {isCur && <span className="pv-deg-now mono"> ● now · {note("3")}</span>}
              </td>
              <td className="mono dim2">{d.note}</td>
              <td className="mono">{d.tf}</td>
              <td className="mono dim2">{d.dur}</td>
              <td className="mono" style={{ textAlign: "right" }}>{d.tol}</td>
              <td className="mono dim2" style={{ textAlign: "right" }}>{d.mult}</td>
              <td style={{ textAlign: "center" }}>
                {d.live ? <Pill tone="gn" small>LIVE</Pill> : <span className="dim mono" style={{ fontSize: 10 }}>ctx</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ── engine classification (ruleset score multipliers) ──────────
function EngineState({ deg = "intermediate" }) {
  const m = EW_DEG_META[deg] || EW_DEG_META.intermediate;
  return (
    <div className="pv-engine">
      <div className="pv-engine-state">
        <span className="label-cap">Engine classification</span>
        <span className="pv-engine-tag mono">WAVE3_IMPULSE</span>
      </div>
      <div className="pv-engine-meta mono dim2">
        score multiplier <b className="up">×1.00</b> · bias <b className="up">BULLISH</b> · Fib tolerance {m.tol} ({m.name.toLowerCase()}) · degree-aware validator
      </div>
    </div>
  );
}

// ── wave-by-wave log ────────────────────────────────────────────
const EW_LOG = [
  { w: "1", type: "Impulse", span: "178.0 → 196.0", move: "+10.1%", fib: "—", note: "Initial leg up off the low", tone: "violet" },
  { w: "2", type: "Zigzag", span: "196.0 → 184.9", move: "−5.7%", fib: "0.62 retr", note: "Deep but holds above W1 origin", tone: "rd" },
  { w: "3", type: "Impulse ⟳", span: "184.9 → 213.4", move: "+15.4%", fib: "1.55× W1", note: "In progress — extension target 214.6", tone: "gn" },
  { w: "4", type: "Projected", span: "213.4 → ~204", move: "−4.4%", fib: "0.38 retr", note: "Shallow flat/triangle; floor 196", tone: "ink-2" },
  { w: "5", type: "Projected", span: "~204 → 224", move: "+9.8%", fib: "= W1", note: "Final leg; watch momentum divergence", tone: "ink-2" },
];
function ElliottLog() {
  return (
    <div className="pv-timeline">
      {EW_LOG.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.w === "3" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < EW_LOG.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>W{e.w}</span>
              <span className="pv-tl-name">{e.type}</span>
              <span className="pv-tl-meta mono dim">{e.span} · <b className={e.move.startsWith("+") ? "up" : "dn"}>{e.move}</b> · {e.fib}</span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ElliottStat({ deg = "intermediate" }) {
  const m = EW_DEG_META[deg] || EW_DEG_META.intermediate;
  const note = EW_NOTATE[deg] || EW_NOTATE.intermediate;
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Structure</div><div className="pv-stat-v mono">5-wave impulse</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Current</div><div className="pv-stat-v mono" style={{ color: `var(--${m.tone})` }}>Wave {note("3")} of {note("5")}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Degree</div><div className="pv-stat-v mono">{m.name}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">W3 target</div><div className="pv-stat-v mono up">{m.w3}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Count confidence</div><div className="pv-stat-v"><ConfBar value={0.58} tone={m.tone} width={72} /></div></div>
    </div>
  );
}

function ElliottView({ ticker, dir }) {
  const [deg, setDeg] = useStateEw("intermediate");
  const Chart = (
    <>
      <ElliottDegreeSel deg={deg} onDeg={setDeg} />
      <ElliottChart ticker={ticker} degree={deg} height={dir === "C" ? 250 : 330} />
    </>
  );

  if (dir === "B") {
    return (
      <div className="pv-view">
        <ElliottStat deg={deg} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Impulse count — annotated" sub="1-2-3-4-5 + projected A on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState deg={deg} /></div>
            <SectionHeader n={2} title="Rules check · 3 absolute + guidelines" style="minimal" />
            <div className="pv-pad"><ElliottRules dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="9 wave degrees" style="minimal" />
            <div className="pv-pad"><ElliottDegrees dense deg={deg} /></div>
            <SectionHeader n={4} title="Alternate counts" style="minimal" />
            <div className="pv-pad"><ElliottAlts /></div>
            <SectionHeader n={5} title="Fib targets" style="minimal" />
            <div className="pv-pad"><ElliottTargets /></div>
          </div>
        </div>
        <SectionHeader n={6} title="Wave-by-wave log" style="minimal" />
        <div className="pv-pad"><ElliottLog /></div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <ElliottStat deg={deg} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState deg={deg} /></div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Wave log</div>
            <ElliottLog />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Rules · 3 absolute + guidelines</div>
            <ElliottRules dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">9 wave degrees</div>
            <ElliottDegrees dense deg={deg} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Fib targets &amp; extensions</div>
            <ElliottTargets />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Alternate counts</div>
            <ElliottAlts />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led
  return (
    <div className="pv-view">
      <ElliottStat deg={deg} />
      <SectionHeader n={1} title="Impulse count — annotated" sub="1-2-3-4-5 + projected A-B-C · fib levels on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState deg={deg} /></div>
      <SectionHeader n={2} title="The 9 degrees of Elliott Wave" sub="engine tracks 3 live — Primary · Intermediate · Minor — the other 6 give context · Fib tolerance narrows with degree" style="minimal" />
      <div className="pv-pad"><ElliottDegrees deg={deg} /></div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Wave-by-wave log</div>
          <ElliottLog />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Rules check · 3 absolute + guidelines</div>
          <ElliottRules />
        </div>
        <div>
          <div className="pv-block-h label-cap">Fib targets &amp; extensions</div>
          <ElliottTargets />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Alternate counts &amp; probabilities</div>
          <ElliottAlts />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ElliottView });
