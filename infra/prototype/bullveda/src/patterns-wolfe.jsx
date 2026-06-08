// patterns-wolfe.jsx — Wolfe Waves theory sub-tab.
//
// REAL DATA: the 5-point structure, channel lines, and the 1-4 EPA (Estimated
// Price at Arrival) target line are computed server-side by engines/wolfe.py
// over live EODHD bars at the mode timeframe (SWING=daily, POSITION=weekly,
// INVESTMENT=monthly).
//
// Mechanism: a Wolfe Wave is a natural equilibrium pattern — five waves where
// 1-3-5 define a converging channel and the 1-4 line projects the EPA where
// supply/demand rebalances. Entry at point-5 (overshoot of the 1-3 sweet-spot
// line) rides the channel back to equilibrium.
//
// Honesty: when no valid 5-point structure exists the engine returns state="none"
// and the view shows the original illustrative fixture, clearly labelled.
// Never white-screens, never throws.

const { useMemo: useMemoWf } = React;

// ── Illustrative fixture (fallback — clearly labelled in the UI) ──────────────
const WF_PTS_FIXTURE = [
  { i: 8,  price: 184, w: "1", place: "below", tone: "violet" },
  { i: 18, price: 199, w: "2", place: "above", tone: "violet" },
  { i: 28, price: 180, w: "3", place: "below", tone: "violet" },
  { i: 38, price: 196, w: "4", place: "above", tone: "violet" },
  { i: 48, price: 176, w: "5", place: "below", tone: "copper" },
];
const WF_EPA_FIXTURE = { i: 74, price: 210 };

const WF_RULES_FIXTURE = [
  { rule: "Waves 3-4 contained within the 1-2 channel", detail: "symmetry holds", status: "PASS", tone: "gn" },
  { rule: "Point 5 overshoots the 1-3 line (sweet spot)", detail: "5 = 176 below 1-3 projection", status: "PASS", tone: "gn" },
  { rule: "Time symmetry · t(1→2) ≈ t(3→4)", detail: "10 ≈ 10 bars", status: "PASS", tone: "gn" },
  { rule: "Point 4 inside the 1-2 price range", detail: "196 < 199 (point 2)", status: "PASS", tone: "gn" },
  { rule: "Entry at 5 · EPA = 1-4 line projection", detail: "target rides the 1-4 line", status: "ACTIVE", tone: "violet" },
];

const WF_LOG_FIXTURE = [
  { w: "1",   role: "Origin low",         date: "", price: "184", note: "start of the wedge", tone: "violet" },
  { w: "2",   role: "First high",          date: "", price: "199", note: "defines upper 2-4 line", tone: "violet" },
  { w: "3",   role: "Lower low",           date: "", price: "180", note: "below point 1 (widening)", tone: "violet" },
  { w: "4",   role: "Lower high",          date: "", price: "196", note: "inside 1-2 range", tone: "violet" },
  { w: "5",   role: "Sweet spot ⟳",        date: "", price: "176", note: "overshoots 1-3 line — the entry", tone: "copper" },
  { w: "EPA", role: "Projected target",    date: "", price: "210", note: "rides the 1-4 line to arrival", tone: "gn" },
];

const WF_TARGETS_FIXTURE = [
  { label: "EPA target",    basis: "1-4 line, est. arrival bar 74 (~26d)", price: "210.00", rr: "R:R ≈ 5.7:1", conf: 0.60, tone: "gn" },
  { label: "Point-5 entry", basis: "sweet-spot reversal zone",              price: "176.00", rr: "entry",       conf: null,  tone: "copper" },
  { label: "Invalidation",  basis: "5 fails to hold / breaks lower",        price: "171.00", rr: "stop",        conf: null,  tone: "rd" },
];

const WF_STAT_FIXTURE = {
  pattern: "Bullish Wolfe Wave", structure: "5-point · valid",
  entry: "$176", epa_target: "$210", confidence: 0.60, tone: "gn",
};

const WF_INV_FIXTURE = {
  price: 171.0,
  note: "A close below $171.00 voids the Wolfe Wave — point-5 holding is the premise.",
};

function _buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x8f3;
  const anchors = [
    { i: 0, price: 190 }, { i: 8, price: 184 }, { i: 13, price: 193 }, { i: 18, price: 199 },
    { i: 23, price: 188 }, { i: 28, price: 180 }, { i: 33, price: 190 }, { i: 38, price: 196 },
    { i: 43, price: 184 }, { i: 48, price: 176 }, { i: 52, price: 187 },
  ];
  const volSpikes = { 18: 1.4, 28: 1.3, 48: 1.9, 49: 1.6 };
  return buildSeries({ n: 53, anchors, seed, volSpikes });
}

// WF_FIXTURE_MODEL — keeps original fixture for standalone showcase
var WF_FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  wfPts: WF_PTS_FIXTURE,
  epa: WF_EPA_FIXTURE,
  skeleton: WF_PTS_FIXTURE.map(p => ({ i: p.i, price: p.price })).concat([{ i: WF_EPA_FIXTURE.i, price: WF_EPA_FIXTURE.price }]),
  lines: [
    { pts: [{ i: 6, price: 184.4 }, { i: 74, price: 170.8 }],  tone: "ink-2", width: 1.2, dash: "3 3", opacity: 0.7 },
    { pts: [{ i: 16, price: 199.3 }, { i: 74, price: 190.6 }], tone: "ink-2", width: 1.2, dash: "3 3", opacity: 0.7 },
    { pts: [{ i: 8, price: 184 }, { i: 74, price: 210.4 }],    tone: "gn",    width: 1.8,               opacity: 0.9 },
  ],
  hlines: [
    { price: WF_EPA_FIXTURE.price, label: `EPA target · ${WF_EPA_FIXTURE.price}`, tone: "gn",     dash: "5 4" },
    { price: 176,                  label: "Point 5 entry · 176",                   tone: "copper", dash: "2 4" },
    { price: 171,                  label: "Invalidate < 171",                      tone: "rd",     dash: "3 3", labelBelow: true },
  ],
  rules:    WF_RULES_FIXTURE,
  log:      WF_LOG_FIXTURE,
  targets:  WF_TARGETS_FIXTURE,
  stat:     WF_STAT_FIXTURE,
  invalidation: WF_INV_FIXTURE,
  isBull: true,
  read: "Bullish Wolfe Wave: entry at point-5 sweet spot $176 (overshoot of 1-3 line). EPA target $210 on the 1-4 line in ~26 bars (R:R ≈ 5.7:1). Void below $171.",
};

// ── Data hook ──────────────────────────────────────────────────────────────────
function useWolfeModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("wolfe", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const fixtureBars = useMemoWf(() => _buildFixtureBars(ticker), [sym]);

  // Usability: real payload with bars + points + wf geometry
  const usable = (
    state === "loaded" && real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length > 0 &&
    real.points && real.points.length >= 5 &&
    real.wf != null
  );

  if (usable) {
    const wf     = real.wf || {};
    const isBull = !!wf.bull;
    const epa    = { i: Math.min(wf.epa_bar || 0, (real.bars.length - 1) + 20), price: wf.epa || 0 };

    // Map real points → wfPts format
    const wfPts = (real.points || []).map(pt => ({
      i:     pt.i,
      price: pt.price,
      w:     pt.w,
      place: pt.w === "2" || pt.w === "4" ? (isBull ? "above" : "below")
                                           : (isBull ? "below" : "above"),
      tone:  pt.tone || (pt.w === "5" ? "copper" : "violet"),
    }));

    // Log: append EPA row
    const log = (real.points || []).map(pt => ({
      w:     pt.w,
      role:  pt.role,
      date:  pt.date || "",
      price: String(pt.price),
      note:  pt.note,
      tone:  pt.tone || (pt.w === "5" ? "copper" : "violet"),
    })).concat([{
      w: "EPA", role: "Projected target",
      date: "", price: String(wf.epa || "—"),
      note: "rides the 1-4 line to equilibrium",
      tone: isBull ? "gn" : "rd",
    }]);

    // Skeleton: wfPts + EPA point (capped to chart width)
    const skeleton = (real.skeleton || wfPts.map(p => ({ i: p.i, price: p.price }))).concat(
      [{ i: epa.i, price: epa.price }]
    );

    const model = {
      isReal: true, source: "real",
      tf, mode, ticker: real.ticker,
      bars: real.bars,
      wfPts,
      epa,
      skeleton,
      lines:   real.lines  || [],
      hlines:  real.hlines || [],
      rules:   (real.rules || []).map(r => ({
        rule: r.rule, detail: r.detail, status: r.status, tone: r.tone,
      })),
      log,
      targets: (real.targets || []).map(t => ({
        label: t.label, basis: t.basis, price: String(t.price),
        rr: t.rr, conf: t.conf, tone: t.tone,
      })),
      stat:         real.stat || {},
      invalidation: real.invalidation || {},
      isBull,
      read: real.read || "",
    };
    return { model, state: "real", sym, tf, usable: true };
  }

  // Real responded but no usable structure
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...WF_FIXTURE_MODEL, bars: fixtureBars },
      state: "none", sym, tf, usable: false, message: real.message,
    };
  }

  // Pre-load / server absent → illustrative fixture
  return {
    model: { ...WF_FIXTURE_MODEL, bars: fixtureBars },
    state: state === "loading" ? "loading" : "mock", sym, tf, usable: false,
  };
}

// ── Chart ─────────────────────────────────────────────────────────────────────
function WolfeChart({ model, ticker, height = 330 }) {
  const bars     = model.bars     || [];
  const skeleton = model.skeleton || [];
  const lines    = model.lines    || [];
  const hlines   = model.hlines   || [];
  const wfPts    = model.wfPts    || [];
  const epa      = model.epa      || {};

  const markers = wfPts.map(p => ({
    i: p.i, price: p.price,
    label: p.w === "5" ? "5 ⟳" : p.w,
    tone: p.tone || (p.w === "5" ? "copper" : "violet"),
    place: p.place,
  })).concat(
    epa.price ? [{ i: epa.i, price: epa.price, label: "EPA", tone: "gn", place: "above" }] : []
  );

  const projFrom = model.isReal ? bars.length : 53;

  return (
    <CandleChart bars={bars} height={height}
                 hlines={hlines} markers={markers}
                 lines={lines} skeleton={skeleton} skeletonTail={1}
                 accent="violet" span={bars.length + 20}
                 projectFrom={projFrom} />
  );
}

// ── Rule table ────────────────────────────────────────────────────────────────
function WolfeRules({ rules, dense }) {
  const list = (rules && rules.length ? rules : WF_RULES_FIXTURE);
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Wolfe rule",   k: "rule" },
        { h: "Measurement",  k: "detail", mono: true },
        { h: "Status",       k: "status", align: "right" },
      ]}
      rows={list.map(r => ({
        rule:   r.rule,
        detail: <span className="dim2" style={{ fontSize: 11 }}>{r.detail}</span>,
        status: <Pill tone={r.tone} small>{r.status}</Pill>,
      }))} />
  );
}

// ── Point timeline (log) ──────────────────────────────────────────────────────
function WolfeLog({ log }) {
  const list = (log && log.length ? log : WF_LOG_FIXTURE);
  const lastW = list.length ? list[list.length - 1].w : null;
  return (
    <div className="pv-timeline">
      {list.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.w === "5" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone || "violet"})` }} />
            {k < list.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone || "violet"})` }}>{e.w}</span>
              <span className="pv-tl-name">{e.role}</span>
              <span className="pv-tl-meta mono dim">
                {e.date && <>{e.date} · </>}<b>${e.price}</b>
              </span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Targets + invalidation ────────────────────────────────────────────────────
function WolfeTargets({ targets, invalidation }) {
  const list = (targets && targets.length ? targets : WF_TARGETS_FIXTURE);
  const inv  = invalidation || WF_INV_FIXTURE;
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[
          { h: "Level",      k: "l" },
          { h: "Basis",      k: "b" },
          { h: "Price",      k: "p", mono: true, align: "right" },
          { h: "R:R / State",k: "rr", mono: true, align: "right" },
          { h: "Conf.",      k: "c", align: "right" },
        ]}
        rows={list.map(t => ({
          l:  <b style={{ color: `var(--${t.tone || "gn"})` }}>{t.label}</b>,
          b:  <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          p:  <b>${t.price}</b>,
          rr: t.rr === "entry"
            ? <span className="copper mono">entry</span>
            : t.rr === "stop"
              ? <span className="rd mono">stop</span>
              : <span className="dim mono">{t.rr}</span>,
          c:  t.conf != null
            ? <ConfBar value={t.conf} tone={t.tone || "gn"} width={48} />
            : <span className="dim mono">—</span>,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">EPA · estimated price at arrival</span>
        <span className="mono">{inv.note || `Close beyond $${inv.price} voids the pattern.`}</span>
      </div>
    </div>
  );
}

// ── Header stat strip ─────────────────────────────────────────────────────────
function WolfeStat({ stat }) {
  const s    = stat || WF_STAT_FIXTURE;
  const tone = (s.tone === "gn" || s.tone === "rd") ? s.tone : "violet";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Pattern</div>
        <div className={`pv-stat-v mono ${tone}`}>{s.pattern || "Bullish Wolfe"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Structure</div>
        <div className="pv-stat-v mono">{s.structure || "5-point · valid"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Entry · point 5</div>
        <div className="pv-stat-v mono copper">{s.entry || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">EPA target</div>
        <div className={`pv-stat-v mono ${tone}`}>{s.epa_target || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v">
          <ConfBar value={s.confidence != null ? s.confidence : 0.60} tone="violet" width={72} />
        </div>
      </div>
    </div>
  );
}

// ── Honest empty state ────────────────────────────────────────────────────────
function WolfeNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Wolfe Wave structure</div>
        <div className="pv-empty-msg">
          {message ||
           `No valid 5-point Wolfe Wave detected on ${sym || "this symbol"}'s chart. The detector requires: point-4 inside the 1-2 range, point-5 overshoot of the 1-3 sweet-spot line, time symmetry between waves 1-2 and 3-4, and channel convergence for the 1-4 EPA projection.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          The detector scans every recent 5-pivot ZigZag for bull (L-H-L-H-L) and bear (H-L-H-L-H) Wolfe structures. When one forms it will populate automatically.
        </div>
      </div>
    </div>
  );
}

// ── View assembler (3 layout directions) ─────────────────────────────────────
function WolfeView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useWolfeModel(ticker, mode);

  // "none": honest empty panel
  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <WolfeNone sym={sym} message={message} />
      </div>
    );
  }

  const Chart  = <WolfeChart model={model} ticker={ticker} height={dir === "C" ? 250 : 330} />;
  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym}
                       tier={usable ? "eodhd" : undefined} tf={tf} />
    </div>
  );

  const patLabel = (model.stat && model.stat.pattern) || "Wolfe Wave";

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <WolfeStat stat={model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title={`${patLabel} — annotated`}
                           sub="5-point structure · 1-3-5 & 2-4 channel · 1-4 EPA target line" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Rule checks" style="minimal" />
            <div className="pv-pad"><WolfeRules rules={model.rules} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Point log" style="minimal" />
            <div className="pv-pad"><WolfeLog log={model.log} /></div>
            <SectionHeader n={4} title="EPA target" style="minimal" />
            <div className="pv-pad"><WolfeTargets targets={model.targets} invalidation={model.invalidation} /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <WolfeStat stat={model.stat} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Point log</div>
            <WolfeLog log={model.log} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Rule checks</div>
            <WolfeRules rules={model.rules} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">EPA target &amp; invalidation</div>
            <WolfeTargets targets={model.targets} invalidation={model.invalidation} />
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <WolfeStat stat={model.stat} />
      <SectionHeader n={1} title={`${patLabel} — annotated`}
                     sub="5-point reversal · 1-3-5 & 2-4 channel · 1-4 EPA target line on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Point-by-point log</div>
          <WolfeLog log={model.log} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Rule checks</div>
          <WolfeRules rules={model.rules} />
        </div>
        <div>
          <div className="pv-block-h label-cap">EPA · estimated price at arrival</div>
          <WolfeTargets targets={model.targets} invalidation={model.invalidation} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { WolfeView });
