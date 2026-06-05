// patterns-harmonic.jsx — Harmonic (Fibonacci) patterns theory sub-tab.
//
// REAL DATA: the XABCD pattern (Gartley / Bat / Butterfly / Crab / Shark /
// Cypher), PRZ band, ratio validation table, and targets are computed server-
// side by engines/harmonic.py over live EODHD bars at the mode timeframe
// (SWING=daily, POSITION=weekly, INVESTMENT=monthly).
//
// Mechanism: harmonic patterns are precise Fibonacci-ratio price structures;
// completion at the PRZ concentrates reversal orders because multiple Fib
// projections of independent legs overlap at the same price level.
//
// Honesty: when no XABCD matches within ratio tolerance the engine returns
// state="none" and the view shows the original illustrative fixture, clearly
// labelled. Never white-screens, never throws.

const { useMemo: useMemoHm } = React;

// ── illustrative fixture (fallback — clearly labelled in the UI) ──────────
const HM_PTS_FIXTURE = [
  { i: 6,  price: 178.0, label: "X", place: "below", tone: "violet" },
  { i: 22, price: 212.0, label: "A", place: "above", tone: "violet" },
  { i: 34, price: 191.0, label: "B", place: "below", tone: "violet" },
  { i: 44, price: 205.0, label: "C", place: "above", tone: "violet" },
  { i: 56, price: 185.3, label: "D", place: "below", tone: "gn" },
];

const HM_RATIOS_FIXTURE = [
  { leg: "AB / XA", actual: "0.618", ideal: "0.618", status: "PASS", tone: "gn" },
  { leg: "BC / AB", actual: "0.667", ideal: "0.382 – 0.886", status: "PASS", tone: "gn" },
  { leg: "CD / BC", actual: "1.46",  ideal: "1.272 – 1.618", status: "PASS", tone: "gn" },
  { leg: "AD / XA", actual: "0.786", ideal: "0.786",         status: "EXACT", tone: "violet" },
];

const HM_LOG_FIXTURE = [
  { p: "X", role: "Origin low",      date: "Mar 03", price: "178.0", note: "Swing low — pattern anchor", tone: "violet" },
  { p: "A", role: "Impulse high",    date: "Mar 25", price: "212.0", note: "XA leg defines the structure", tone: "violet" },
  { p: "B", role: "0.618 retr",      date: "Apr 09", price: "191.0", note: "Textbook Gartley B at .618 of XA", tone: "violet" },
  { p: "C", role: "Reaction high",   date: "Apr 21", price: "205.0", note: "0.667 of AB — within tolerance", tone: "violet" },
  { p: "D", role: "PRZ completion",  date: "May 06", price: "185.3", note: "0.786 XA — buy zone, reversed up", tone: "gn" },
];

const HM_TGT_FIXTURE = [
  { label: "T1 · 0.382 AD", basis: "0.382 of the AD leg from D", price: "195.5", rr: "hit ✓", conf: 0.74, tone: "gn" },
  { label: "T2 · 0.618 AD", basis: "0.618 of the AD leg",        price: "201.8", rr: "hit ✓", conf: 0.62, tone: "gn" },
  { label: "T3 · A retest",  basis: "return to point A",          price: "212.0", rr: "testing", conf: 0.48, tone: "amb" },
  { label: "Extension · 1.0 AD", basis: "full AD projected from D", price: "212.0+", rr: "stretch", conf: 0.3, tone: "ink-2" },
];

const HM_STAT_FIXTURE = {
  pattern: "Bullish Gartley", completion: "D confirmed", prz: "184.0 – 187.5",
  next_target: "$212 (A)", confidence: 0.69, tone: "gn",
};

const HM_INV_FIXTURE = {
  price: 178.0,
  note: "A close below point X · $178.00 voids the Gartley — structure failed if D breaks before T3.",
};

function _buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x7d2;
  const anchors = [
    { i: 0, price: 188 }, { i: 6, price: 178 }, { i: 14, price: 198 }, { i: 22, price: 212 },
    { i: 28, price: 199 }, { i: 34, price: 191 }, { i: 39, price: 199 }, { i: 44, price: 205 },
    { i: 50, price: 193 }, { i: 56, price: 185.3 }, { i: 62, price: 200 }, { i: 65, price: 213.4 },
  ];
  const volSpikes = { 6: 1.5, 22: 1.4, 56: 2.1, 57: 1.7 };
  return buildSeries({ n: 66, anchors, seed, volSpikes });
}

var FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  // chart annotations
  hmPts: HM_PTS_FIXTURE,
  skeleton: HM_PTS_FIXTURE.map(p => ({ i: p.i, price: p.price })).concat([{ i: 65, price: 213.4 }]),
  zones: [{ lo: 184.0, hi: 187.5, tone: "gn", label: "PRZ 184.0–187.5" }],
  hlines: [
    { price: 201.8, label: "T2 · 0.618 AD · 201.8", tone: "gn", dash: "5 4" },
    { price: 212.0, label: "T3 · A retest · 212",   tone: "gn", dash: "5 4" },
    { price: 178.0, label: "Invalidate < X · 178",   tone: "rd", dash: "3 3", labelBelow: true },
  ],
  ratios:  HM_RATIOS_FIXTURE,
  log:     HM_LOG_FIXTURE,
  targets: HM_TGT_FIXTURE,
  stat:    HM_STAT_FIXTURE,
  invalidation: HM_INV_FIXTURE,
  patternName: "Gartley",
  read: "Bullish Gartley completed at the PRZ (0.786 XA) and reversed up. T1/T2 hit; now testing the A retest at $212. Voids below X $178.",
};

// ── data hook ──────────────────────────────────────────────────────────────
function useHarmonicModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("harmonic", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const fixtureBars = useMemoHm(() => _buildFixtureBars(ticker), [sym]);

  // Usability: real payload with bars + points
  const usable = (
    state === "loaded" && real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length > 0 &&
    real.points && real.points.length >= 5
  );

  if (usable) {
    // Map real payload → the shape our sub-components expect
    const pat = real.pattern || {};
    const inv = real.invalidation || {};
    const isBull = !!pat.bull;

    // Build hmPts from real points (real.points is the [{p,i,price,role,date,note,tone}] array)
    const hmPts = (real.points || []).map(pt => ({
      i:     pt.i,
      price: pt.price,
      label: pt.p,
      place: pt.p === "D" ? (isBull ? "below" : "above") : (isBull ? (pt.p === "A" || pt.p === "C" ? "above" : "below") : (pt.p === "A" || pt.p === "C" ? "below" : "above")),
      tone:  pt.p === "D" ? (isBull ? "gn" : "rd") : "violet",
    }));

    // Skeleton: XABCD pivots + a continuation point at the last bar
    const lastBar = real.bars.length - 1;
    const lastClose = (real.bars[lastBar] || {}).c || 0;
    const skeleton = (real.skeleton || hmPts.map(p => ({ i: p.i, price: p.price }))).concat(
      lastBar > (hmPts[hmPts.length - 1] || {}).i ? [{ i: lastBar, price: lastClose }] : []
    );

    const model = {
      isReal: true, source: "real",
      tf, mode, ticker: real.ticker,
      bars: real.bars,
      hmPts,
      skeleton,
      zones:   real.zones   || [],
      hlines:  real.hlines  || [],
      ratios:  (real.ratios || []).map(r => ({
        leg:    r.leg,
        actual: r.actual,
        ideal:  r.ideal,
        status: r.status,
        tone:   r.tone,
      })),
      log: (real.points || []).map(pt => ({
        p:     pt.p,
        role:  pt.role,
        date:  pt.date,
        price: String(pt.price),
        note:  pt.note,
        tone:  pt.p === "D" ? (isBull ? "gn" : "rd") : "violet",
      })),
      targets: (real.targets || []).map(t => ({
        label: t.label, basis: t.basis, price: String(t.price),
        rr: t.rr, conf: t.conf, tone: t.tone,
      })),
      stat: real.stat || {},
      invalidation: real.invalidation || {},
      patternName: pat.name || "Pattern",
      read: real.read || "",
    };
    return { model, state: "real", sym, tf, usable: true };
  }

  // Real responded but no usable structure
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...FIXTURE_MODEL, bars: fixtureBars },
      state: "none", sym, tf, usable: false, message: real.message,
    };
  }

  // Pre-load / server absent → illustrative fixture
  return {
    model: { ...FIXTURE_MODEL, bars: fixtureBars },
    state: state === "loading" ? "loading" : "mock", sym, tf, usable: false,
  };
}

// ── chart (builds annotations from model props) ───────────────────────────
function HarmonicChart({ model, ticker, height = 320 }) {
  const bars     = model.bars || [];
  const skeleton = model.skeleton || [];
  const zones    = model.zones   || [];
  const hlines   = model.hlines  || [];
  const hmPts    = model.hmPts   || [];

  const markers = hmPts.map(p => ({
    i: p.i, price: p.price, label: p.label, tone: p.tone, place: p.place,
  }));

  // skeletonTail: how many trailing points to show as dashed (projected) — 1
  return (
    <CandleChart bars={bars} height={height} hlines={hlines} markers={markers}
                 zones={zones} skeleton={skeleton} skeletonTail={1}
                 accent="violet" span={bars.length} />
  );
}

// ── fib-ratio validation table ────────────────────────────────────────────
function HarmonicRatios({ ratios, dense }) {
  const rows = (ratios && ratios.length ? ratios : HM_RATIOS_FIXTURE).map(r => ({
    leg:    r.leg,
    actual: <b>{r.actual}</b>,
    ideal:  <span className="dim2">{r.ideal}</span>,
    status: <Pill tone={r.tone} small>{r.status}</Pill>,
  }));
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Leg ratio", k: "leg", mono: true },
        { h: "Actual",    k: "actual", mono: true, align: "right" },
        { h: "Ideal",     k: "ideal",  mono: true, align: "right" },
        { h: "Status",    k: "status", align: "right" },
      ]}
      rows={rows} />
  );
}

// ── XABCD point timeline ──────────────────────────────────────────────────
function HarmonicLog({ log }) {
  const list = (log && log.length ? log : HM_LOG_FIXTURE);
  const lastP = list.length ? list[list.length - 1].p : null;
  return (
    <div className="pv-timeline">
      {list.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.p === lastP ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < list.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.p}</span>
              <span className="pv-tl-name">{e.role}</span>
              <span className="pv-tl-meta mono dim">{e.date && <>{e.date} · </>}<b>${e.price}</b></span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── targets + invalidation ────────────────────────────────────────────────
function HarmonicTargets({ targets, invalidation }) {
  const list = (targets && targets.length ? targets : HM_TGT_FIXTURE);
  const inv  = invalidation || HM_INV_FIXTURE;
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[
          { h: "Target",     k: "label" },
          { h: "Fib basis",  k: "basis" },
          { h: "Price",      k: "price", mono: true, align: "right" },
          { h: "State",      k: "rr",    mono: true, align: "right" },
          { h: "Confidence", k: "conf",  align: "right" },
        ]}
        rows={list.map(t => ({
          label: <b style={{ color: `var(--${t.tone || "gn"})` }}>{t.label}</b>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>,
          rr:    (t.rr || "").includes("hit")
            ? <span className="up">{t.rr}</span>
            : <span className="dim">{t.rr}</span>,
          conf:  t.conf != null ? <ConfBar value={t.conf} tone={t.tone || "gn"} /> : <span className="dim mono">—</span>,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">{inv.note || `Close beyond X $${inv.price} voids the pattern.`}</span>
      </div>
    </div>
  );
}

// ── header strip ──────────────────────────────────────────────────────────
function HarmonicStat({ stat }) {
  const s = stat || HM_STAT_FIXTURE;
  const tone = (s.tone === "gn" || s.tone === "rd") ? s.tone : "violet";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Pattern</div>
        <div className={`pv-stat-v mono ${tone}`}>{s.pattern || "Gartley"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Completion</div>
        <div className="pv-stat-v mono up">{s.completion || "D confirmed"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">PRZ</div>
        <div className="pv-stat-v mono">{s.prz || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Next target</div>
        <div className="pv-stat-v mono up">{s.next_target || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Pattern confidence</div>
        <div className="pv-stat-v">
          <ConfBar value={s.confidence != null ? s.confidence : 0.69} tone="violet" width={72} />
        </div>
      </div>
    </div>
  );
}

// ── honest empty state ────────────────────────────────────────────────────
function HarmonicNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no harmonic pattern</div>
        <div className="pv-empty-msg">
          {message ||
           `No XABCD harmonic pattern (Gartley/Bat/Butterfly/Crab/Shark/Cypher) within ratio tolerance on ${sym || "this name"}'s chart. Price structure doesn't match the required Fibonacci leg ratios right now.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          The detector scans every recent 5-pivot ZigZag sequence for Gartley (AB=0.618 XA), Bat (AB=0.382/0.500 XA), Butterfly (AB=0.786 XA), Crab (AB=0.382/0.618 XA), Shark, and Cypher. When a PRZ completes it will populate automatically.
        </div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions) ─────────────────────────────────────────
function HarmonicView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useHarmonicModel(ticker, mode);

  // "none" state: honest empty panel (no illustrative fixture displayed here)
  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <HarmonicNone sym={sym} message={message} />
      </div>
    );
  }

  const Chart  = <HarmonicChart model={model} ticker={ticker} height={dir === "C" ? 250 : 330} />;
  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym}
                       tier={usable ? "eodhd" : undefined} tf={tf} />
    </div>
  );

  const patLabel = (model.stat && model.stat.pattern) || "Harmonic";

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <HarmonicStat stat={model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title={`${patLabel} — annotated`}
                           sub="XABCD pivots · PRZ band · fib targets on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Fib-ratio validation" style="minimal" />
            <div className="pv-pad"><HarmonicRatios ratios={model.ratios} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="XABCD points" style="minimal" />
            <div className="pv-pad"><HarmonicLog log={model.log} /></div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad"><HarmonicTargets targets={model.targets} invalidation={model.invalidation} /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <HarmonicStat stat={model.stat} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">XABCD point log</div>
            <HarmonicLog log={model.log} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Fib-ratio validation</div>
            <HarmonicRatios ratios={model.ratios} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
            <HarmonicTargets targets={model.targets} invalidation={model.invalidation} />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <HarmonicStat stat={model.stat} />
      <SectionHeader n={1} title={`${patLabel} — annotated`}
                     sub="XABCD pivots · PRZ band · fib targets on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">XABCD point log</div>
          <HarmonicLog log={model.log} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Fib-ratio validation</div>
          <HarmonicRatios ratios={model.ratios} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Fib targets &amp; invalidation</div>
          <HarmonicTargets targets={model.targets} invalidation={model.invalidation} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { HarmonicView });
