// patterns-elliott.jsx — Elliott Wave sub-tab: impulse 1-2-3-4-5 + A-B-C
// drawn on REAL bars with a wave skeleton, fib target/extension table, alternate
// counts with probabilities, wave-rule checks, and a wave-by-wave log.
//
// REAL DATA: detector runs server-side (engines/elliott.py) over live EODHD bars
// via usePatternModel("elliott", ticker, mode). When the server is absent or
// returns state:"none" we fall back to the illustrative fixture below — clearly
// labelled in the source badge.

const { useMemo: useMemoEw, useState: useStateEw } = React;

// ── degree notation (ruleset §D2) ──────────────────────────────────
const EW_NOTATE = {
  primary: (w) => `[${w}]`,
  intermediate: (w) => `(${w})`,
  minor: (w) => `${w}`,
};

// ── illustrative fixture (fallback — clearly labelled) ─────────────
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

const EW_TGT_FIXTURE = [
  { label: "W3 target", basis: "1.618 × W1 (18.0) from W2 low", price: "214.6", note: "primary", conf: 0.61, tone: "violet" },
  { label: "W3 extension", basis: "2.618 × W1 from W2 low", price: "232.0", note: "if W3 extends", conf: 0.28, tone: "amb" },
  { label: "W4 retrace", basis: "0.382 × W3 (zone)", price: "203–205", note: "must stay > 196", conf: null, tone: "ink-2" },
  { label: "W5 target", basis: "W5 = W1 from W4 low", price: "221.4", note: "min objective", conf: 0.47, tone: "gn" },
  { label: "W5 extension", basis: "0.618 × (W1→W3)", price: "228.0", note: "stretch", conf: 0.31, tone: "gn" },
];

const EW_ALT_FIXTURE = [
  { name: "Primary — bullish impulse", loc: "In Wave 3 of 5", p: 0.58, tone: "gn",
    note: "Five-wave advance from 178; W3 testing 1.618× extension, 4 & 5 to follow." },
  { name: "Alternate — W3 complete", loc: "Starting Wave 4", p: 0.27, tone: "amb",
    note: "W3 topped at 213.4; expect a 0.382 pullback toward 203–205 before W5." },
  { name: "Bearish — corrective", loc: "In Wave C of ABC", p: 0.15, tone: "rd",
    note: "Whole advance is a counter-trend ABC; rejection here resumes the down-trend." },
];

const EW_RULES_FIXTURE = [
  { rule: "Wave 2 never retraces > 100% of Wave 1", type: "HARD", detail: "W2 low 184.9 > W1 origin 178.0", status: "PASS", tone: "gn" },
  { rule: "Wave 3 is never the shortest of 1·3·5", type: "HARD", detail: "W3 ≈ 28.5 > W1 18.0 (W5 pending)", status: "PASS", tone: "gn" },
  { rule: "Wave 4 never enters Wave 1 territory", type: "HARD", detail: "W4 must hold above W1 high 196.0", status: "WATCH", tone: "amb" },
  { rule: "Wave 3 extends ≥ 1.618 × W1", type: "GUIDE", detail: "1.55× now → extension target 214.6", status: "NEAR", tone: "violet" },
  { rule: "Alternation — W2 sharp ⇄ W4 sideways", type: "GUIDE", detail: "W2 zigzag (.62) → W4 expect flat/triangle (.382)", status: "OK", tone: "gn" },
  { rule: "Wave 2 retraces 50–78.6% of W1", type: "GUIDE", detail: ".62 within band", status: "PASS", tone: "gn" },
];

const EW_LOG_FIXTURE = [
  { w: "1", type: "Impulse", span: "178.0 → 196.0", move: "+10.1%", fib: "—", note: "Initial leg up off the low", tone: "violet" },
  { w: "2", type: "Zigzag", span: "196.0 → 184.9", move: "−5.7%", fib: "0.62 retr", note: "Deep but holds above W1 origin", tone: "rd" },
  { w: "3", type: "Impulse ⟳", span: "184.9 → 213.4", move: "+15.4%", fib: "1.55× W1", note: "In progress — extension target 214.6", tone: "gn" },
  { w: "4", type: "Projected", span: "213.4 → ~204", move: "−4.4%", fib: "0.38 retr", note: "Shallow flat/triangle; floor 196", tone: "ink-2" },
  { w: "5", type: "Projected", span: "~204 → 224", move: "+9.8%", fib: "= W1", note: "Final leg; watch momentum divergence", tone: "ink-2" },
];

const EW_STAT_FIXTURE = {
  structure: "5-wave impulse", current: "Wave (3) of (5)",
  degree: "Intermediate", w3_target: "$214.6", confidence: 0.58, tone: "violet",
};

const EW_INV_FIXTURE = {
  price: 184.9,
  note: "Close below the W2 low $184.90 negates the impulse count (W2 cannot exceed 100% of W1).",
};

// canonical fixture model for standalone showcase / fallback
var FIXTURE_MODEL = {
  isReal: false,
  stat: EW_STAT_FIXTURE,
  rules: EW_RULES_FIXTURE,
  targets: EW_TGT_FIXTURE,
  alternates: EW_ALT_FIXTURE,
  wave_log: EW_LOG_FIXTURE,
  invalidation: EW_INV_FIXTURE,
  hlines: null,   // fixture uses per-degree cfg hlines
  skeleton: null, // fixture uses per-degree cfg pivots
  skeletonTail: null,
  projectFrom: null,
  pivots: null,
  bars: null,     // fixture draws via useEWBars per degree
  degree: "intermediate",
  cur_wave: "3",
  bullish: true,
};

// ── map mode → default degree ───────────────────────────────────────
function modeToDefaultDeg(mode) {
  if (!mode) return "intermediate";
  const m = (mode || "").toUpperCase();
  if (m === "POSITION" || m === "INVESTMENT") return "primary";
  return "intermediate";
}

// ── real data hook ──────────────────────────────────────────────────
function useElliottModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("elliott", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;

  const usable = (
    state === "loaded" &&
    real &&
    real.ok &&
    real.state === "real" &&
    real.bars &&
    real.bars.length > 0 &&
    real.pivots &&
    real.pivots.length >= 3
  );

  if (usable) {
    return {
      model: {
        isReal: true,
        stat: real.stat || EW_STAT_FIXTURE,
        rules: real.rules || EW_RULES_FIXTURE,
        targets: real.targets || EW_TGT_FIXTURE,
        alternates: real.alternates || EW_ALT_FIXTURE,
        wave_log: real.wave_log || EW_LOG_FIXTURE,
        invalidation: real.invalidation || EW_INV_FIXTURE,
        hlines: real.hlines || null,
        skeleton: real.skeleton || null,
        skeletonTail: real.skeletonTail || 0,
        projectFrom: real.projectFrom || null,
        pivots: real.pivots || [],
        bars: real.bars,
        degree: real.degree || "intermediate",
        cur_wave: real.cur_wave || "3",
        bullish: real.bullish !== false,
        read: real.read || "",
        confidence: real.confidence || 0.40,
      },
      state: "real", sym, tf, usable: true,
    };
  }
  if (state === "loaded" && real && real.ok) {
    return {
      model: FIXTURE_MODEL, state: "none", sym, tf, usable: false,
      message: real.message || `No clean Elliott Wave count on ${sym || "this name"}'s ${tf || "daily"} chart.`,
    };
  }
  return {
    model: FIXTURE_MODEL,
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── degree selector ────────────────────────────────────────────────
function ElliottDegreeSel({ deg, onDeg }) {
  const opts = [["primary", "Primary", "[W]"], ["intermediate", "Intermediate", "(D)"], ["minor", "Minor", "4H"]];
  return (
    <div className="pv-degsel">
      <span className="pv-degsel-cap label-cap">Draw degree</span>
      {opts.map(([id, nm, tf]) => {
        const accent = id === "primary" ? "blue" : id === "intermediate" ? "violet" : "copper";
        return (
          <button key={id} className={`pv-degsel-btn pv-degsel-btn--${accent} ${deg === id ? "is-on" : ""}`} onClick={() => onDeg(id)}>
            {nm} <span className="pv-degsel-tf mono">{tf}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── chart: real data or fixture ─────────────────────────────────────
function ElliottChart({ model, ticker, degree = "intermediate", height = 330 }) {
  const cfg = EW_DEG_CFG[degree] || EW_DEG_CFG.intermediate;
  const fixtureBars = useEWBars(ticker, degree);
  const note = EW_NOTATE[degree] || EW_NOTATE.intermediate;

  if (model.isReal && model.bars && model.bars.length) {
    // Real data path
    const bars = model.bars;
    const pivots = model.pivots || [];
    const skeleton = model.skeleton && model.skeleton.length ? model.skeleton : null;
    const skeletonTail = model.skeletonTail || 0;
    const projectFrom = model.projectFrom || null;
    const hlines = model.hlines || cfg.hlines;
    const accent = model.degree === "primary" ? "blue" : model.degree === "minor" ? "copper" : "violet";

    const markers = pivots.map(p => {
      const wlabel = p.proj
        ? (note(p.w) + " →")
        : (p.current ? `${note(p.w)} ⟳` : (p.w === "0" ? "0" : note(p.w)));
      return { i: p.i, price: p.price, label: wlabel, tone: p.tone || accent, place: p.place || "above" };
    });

    return <CandleChart bars={bars} height={height} hlines={hlines} markers={markers}
                        skeleton={skeleton} skeletonTail={skeletonTail}
                        accent={accent} span={bars.length + 20} projectFrom={projectFrom} />;
  }

  // Fixture path
  const abc = cfg.abc || [];
  const skeleton = cfg.pivots.map(p => ({ i: p.i, price: p.price })).concat(abc.map(p => ({ i: p.i, price: p.price })));
  const tail = cfg.pivots.filter(p => p.proj).length + abc.length;
  const markers = cfg.pivots.map(p => ({
    i: p.i, price: p.price,
    label: p.w === "0" ? "0" : (p.current ? `${note(p.w)} ⟳` : note(p.w)),
    tone: p.proj ? "ink-3" : (p.tone || cfg.accent), place: p.place,
  })).concat(abc.map(p => ({ i: p.i, price: p.price, label: note(p.w), tone: "amb", place: p.w === "B" ? "above" : "below" })));
  return <CandleChart bars={fixtureBars} height={height} hlines={cfg.hlines} markers={markers}
                      skeleton={skeleton} skeletonTail={tail} accent={cfg.accent}
                      span={cfg.span} projectFrom={cfg.projectFrom} />;
}

// ── fib targets ──────────────────────────────────────────────────────
function ElliottTargets({ targets }) {
  const rows = (targets && targets.length) ? targets : EW_TGT_FIXTURE;
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Level", k: "label" }, { h: "Fib basis", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={rows.map(t => {
          const priceStr = t.price != null ? String(t.price) : "—";
          const priceCell = priceStr.includes("–") ? priceStr : (priceStr.startsWith("$") ? priceStr : `$${priceStr}`);
          const noteStr = t.note || "";
          return {
            label: <span><b style={{ color: `var(--${t.tone || "violet"})` }}>{t.label || ""}</b>
                     {noteStr && <><br /><span className="dim" style={{ fontSize: 10 }}>{noteStr}</span></>}</span>,
            basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis || ""}</span>,
            price: <b>{priceCell}</b>,
            conf: t.conf == null ? <span className="dim mono">zone</span> : <ConfBar value={t.conf} tone={t.tone || "violet"} />,
          };
        })} />
    </div>
  );
}

// ── invalidation block ───────────────────────────────────────────────
function ElliottInvalidation({ invalidation }) {
  const inv = invalidation || EW_INV_FIXTURE;
  return (
    <div className="pv-invalid">
      <span className="label-cap">Invalidation</span>
      <span className="mono">{inv.note || `Close below $${inv.price} negates the count.`}</span>
    </div>
  );
}

// ── alternate counts ─────────────────────────────────────────────────
function ElliottAlts({ alternates }) {
  const alts = (alternates && alternates.length) ? alternates : EW_ALT_FIXTURE;
  return (
    <div className="pv-alts">
      {alts.map((a, k) => (
        <div key={k} className={`pv-alt pv-alt--${a.tone || "gn"}`}>
          <div className="pv-alt-head">
            <span className="pv-alt-name">{a.name}</span>
            <span className="pv-alt-p mono" style={{ color: `var(--${a.tone || "gn"})` }}>{Math.round((a.p || 0) * 100)}%</span>
          </div>
          <div className="pv-alt-bar"><span style={{ width: `${(a.p || 0) * 100}%`, background: `var(--${a.tone || "gn"})` }} /></div>
          <div className="pv-alt-loc mono dim2">{a.loc}</div>
          <div className="pv-alt-note">{a.note}</div>
        </div>
      ))}
    </div>
  );
}

// ── wave-rule checks ─────────────────────────────────────────────────
function ElliottRules({ rules, dense }) {
  const rows = (rules && rules.length) ? rules : EW_RULES_FIXTURE;
  return <MiniTable dense={dense}
    cols={[{ h: "Rule / guideline", k: "rule" }, { h: "Type", k: "type", align: "center" },
           { h: "Measurement", k: "detail", mono: true }, { h: "Status", k: "status", align: "right" }]}
    rows={rows.map(r => ({
      rule: r.rule,
      type: <Pill tone={(r.type || "HARD") === "HARD" ? "rd" : "ink"} small outline>{(r.type || "HARD") === "HARD" ? "HARD" : "GUIDE"}</Pill>,
      detail: <span className="dim2" style={{ fontSize: 11 }}>{r.detail || ""}</span>,
      status: <Pill tone={r.tone || "gn"} small>{r.status || "?"}</Pill>,
    }))} />;
}

// ── 9 degrees table ──────────────────────────────────────────────────
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

// ── engine state strip ───────────────────────────────────────────────
function EngineState({ model }) {
  const stat = (model && model.stat) || EW_STAT_FIXTURE;
  const deg = (model && model.degree) || "intermediate";
  const degName = deg === "primary" ? "Primary" : deg === "minor" ? "Minor" : "Intermediate";
  const tol = deg === "primary" ? "±5%" : deg === "minor" ? "±2.5%" : "±3.5%";
  const conf = model && model.confidence != null ? model.confidence : 0.40;
  const cur = (stat.current || "Wave 3").replace("Wave ", "W").replace(" of 5", "/5");
  const tag = (stat.structure || "5-wave impulse").toUpperCase().replace(/ /g, "_");
  return (
    <div className="pv-engine">
      <div className="pv-engine-state">
        <span className="label-cap">Engine classification</span>
        <span className="pv-engine-tag mono">{cur} · {tag}</span>
      </div>
      <div className="pv-engine-meta mono dim2">
        confidence <b className={conf >= 0.5 ? "up" : "dim2"}>{Math.round(conf * 100)}%</b> ·
        degree <b>{degName}</b> · Fib tolerance {tol} · ZigZag pivot detector
      </div>
    </div>
  );
}

// ── wave-by-wave log ─────────────────────────────────────────────────
function ElliottLog({ wave_log }) {
  const log = (wave_log && wave_log.length) ? wave_log : EW_LOG_FIXTURE;
  return (
    <div className="pv-timeline">
      {log.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.is_current ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone || "ink-2"})` }} />
            {k < log.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone || "ink-2"})` }}>W{e.w}</span>
              <span className="pv-tl-name">{e.type}</span>
              <span className="pv-tl-meta mono dim">
                {e.span} · <b className={(e.move || "").startsWith("+") ? "up" : "dn"}>{e.move}</b> · {e.fib}
              </span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── stat strip (top summary) ─────────────────────────────────────────
function ElliottStat({ model, deg }) {
  const stat = (model && model.stat) || EW_STAT_FIXTURE;
  const useDeg = deg || (model && model.degree) || "intermediate";
  const note = EW_NOTATE[useDeg] || EW_NOTATE.intermediate;
  const conf = model && model.confidence != null ? model.confidence : stat.confidence || 0.40;
  const tone = stat.tone || "violet";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Structure</div><div className="pv-stat-v mono">{stat.structure || "5-wave impulse"}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Current</div>
        <div className="pv-stat-v mono" style={{ color: `var(--${tone})` }}>{stat.current || `Wave ${note("3")} of ${note("5")}`}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Degree</div><div className="pv-stat-v mono">{stat.degree || "Intermediate"}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">W3 / C target</div><div className="pv-stat-v mono up">{stat.w3_target || "—"}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Count confidence</div><div className="pv-stat-v"><ConfBar value={conf} tone={tone} width={72} /></div></div>
    </div>
  );
}

// ── empty state (real feed, no structure) ────────────────────────────
function ElliottNone({ sym, message, tf }) {
  return (
    <div className="pv-empty">
      <div className="pv-empty-i mono">— no Elliott Wave count</div>
      <div className="pv-empty-msg">
        {message || `No clean 5-wave impulse or A-B-C corrective structure on ${sym || "this name"}'s ${tf || "daily"} chart. Price structure is ambiguous — forcing a count here would be fabrication.`}
      </div>
      <div className="pv-empty-sub mono dim2">
        The detector requires at least 5 alternating ZigZag pivots with valid Fibonacci proportions. When a count forms it will populate automatically.
      </div>
    </div>
  );
}

// ── main view (3 layout directions) ─────────────────────────────────
function ElliottView({ ticker, dir, mode }) {
  // default degree from mode; user can override with degree selector
  const defaultDeg = modeToDefaultDeg(mode);
  const [deg, setDeg] = useStateEw(defaultDeg);

  // update default when mode changes
  React.useEffect(() => { setDeg(modeToDefaultDeg(mode)); }, [mode]);

  const { model, state, message, sym, tf, usable } = useElliottModel(ticker, mode);

  // For the chart: real data uses model.degree; fixture uses UI selector
  const chartDeg = (usable && model.degree) ? model.degree : deg;
  const accent = chartDeg === "primary" ? "blue" : chartDeg === "minor" ? "copper" : "violet";

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={null} tf={tf} />
    </div>
  );

  const DegreeSel = (
    <ElliottDegreeSel deg={usable ? chartDeg : deg} onDeg={usable ? () => {} : setDeg} />
  );

  const Chart = (
    <>
      {DegreeSel}
      <ElliottChart model={model} ticker={ticker} degree={chartDeg} height={dir === "C" ? 250 : 330} />
    </>
  );

  if (state === "none") {
    return (
      <div className="pv-view">
        {SrcBar}
        <ElliottNone sym={sym} message={message} tf={tf} />
      </div>
    );
  }

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <ElliottStat model={model} deg={chartDeg} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Impulse count — annotated" sub="1-2-3-4-5 + projected A on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState model={model} /></div>
            <SectionHeader n={2} title="Rules check · 3 absolute + guidelines" style="minimal" />
            <div className="pv-pad"><ElliottRules rules={model.rules} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="9 wave degrees" style="minimal" />
            <div className="pv-pad"><ElliottDegrees dense deg={chartDeg} /></div>
            <SectionHeader n={4} title="Alternate counts" style="minimal" />
            <div className="pv-pad"><ElliottAlts alternates={model.alternates} /></div>
            <SectionHeader n={5} title="Fib targets" style="minimal" />
            <div className="pv-pad">
              <ElliottTargets targets={model.targets} />
              <ElliottInvalidation invalidation={model.invalidation} />
            </div>
          </div>
        </div>
        <SectionHeader n={6} title="Wave-by-wave log" style="minimal" />
        <div className="pv-pad"><ElliottLog wave_log={model.wave_log} /></div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <ElliottStat model={model} deg={chartDeg} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState model={model} /></div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Wave log</div>
            <ElliottLog wave_log={model.wave_log} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Rules · 3 absolute + guidelines</div>
            <ElliottRules rules={model.rules} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">9 wave degrees</div>
            <ElliottDegrees dense deg={chartDeg} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Fib targets &amp; extensions</div>
            <ElliottTargets targets={model.targets} />
            <ElliottInvalidation invalidation={model.invalidation} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Alternate counts</div>
            <ElliottAlts alternates={model.alternates} />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <ElliottStat model={model} deg={chartDeg} />
      <SectionHeader n={1} title="Impulse count — annotated" sub="1-2-3-4-5 + projected A-B-C · fib levels on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-pad" style={{ paddingTop: 0 }}><EngineState model={model} /></div>
      <SectionHeader n={2} title="The 9 degrees of Elliott Wave" sub="engine tracks 3 live — Primary · Intermediate · Minor — the other 6 give context · Fib tolerance narrows with degree" style="minimal" />
      <div className="pv-pad"><ElliottDegrees deg={chartDeg} /></div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Wave-by-wave log</div>
          <ElliottLog wave_log={model.wave_log} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Rules check · 3 absolute + guidelines</div>
          <ElliottRules rules={model.rules} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Fib targets &amp; extensions</div>
          <ElliottTargets targets={model.targets} />
          <ElliottInvalidation invalidation={model.invalidation} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Alternate counts &amp; probabilities</div>
          <ElliottAlts alternates={model.alternates} />
        </div>
      </div>
    </div>
  );
}

// ── dynamic read line (lens-call integration) ────────────────────────
function ElliottReadLine({ ticker, mode }) {
  const { model, state, usable } = useElliottModel(ticker, mode);
  if (state === "none") {
    return <span className="mono">No clean Elliott Wave count on the {(model && model.stat && model.stat.degree) || "intermediate"}-degree chart — structure is ambiguous. Stand aside until a clear 5-wave or A-B-C count forms.</span>;
  }
  if (!usable) {
    return <span className="mono">Composite operator is <b className="copper">accumulating</b> — Phase D after a confirmed Spring + SOS. Mark-up on a close &gt; <b className="copper">$213.40</b>; P&amp;F count projects <b className="up">$221 → $237</b>. Invalid below <b className="dn">$187.60</b>.</span>;
  }
  const read = model.read || "";
  return <span className="mono">{read}</span>;
}

Object.assign(window, { ElliottView, ElliottReadLine });
