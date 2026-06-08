// patterns-fibonacci.jsx — Fibonacci sub-tab.
//
// REAL DATA: the dominant swing (fractal/zigzag pivot scan), retracement grid
// (23.6→78.6), extension targets (1.272/1.618/2.0), golden pocket zone, and
// per-level respect counts are computed server-side by engines/fibonacci.py over
// live EODHD bars. The hook reads the cache synchronously and re-renders when
// the real payload resolves. When the server is absent (standalone showcase) or
// returns state="none", the illustrative fixture below is shown — the header
// badge says so, honestly.
//
// Mechanism: institutional orders cluster at Fibonacci retracement/extension
// ratios of the dominant swing, making those prices act as real S/R.

const { useMemo: useMemoFb } = React;

// ── illustrative fixture (fallback only — clearly labelled in the UI) ─────────
const FB_SL = 178.0, FB_SH = 214.0;
const FB_RANGE = FB_SH - FB_SL;
const _retr = p => +(FB_SH - p * FB_RANGE).toFixed(1);
const _ext  = p => +(FB_SL + p * FB_RANGE).toFixed(1);

const FB_FIX_RETR = [
  { ratio: 0.236, label: "0.236", price: _retr(0.236), kind: "retr", role: "support", role_label: "shallow",              status: "untested",        conf: null,  tone: "ink-2", hit: false, respect: 0 },
  { ratio: 0.382, label: "0.382", price: _retr(0.382), kind: "retr", role: "support", role_label: "moderate",             status: "untested",        conf: null,  tone: "cy",   hit: false, respect: 0 },
  { ratio: 0.500, label: "0.500", price: _retr(0.500), kind: "retr", role: "support", role_label: "mid-point",            status: "untested",        conf: null,  tone: "cy",   hit: false, respect: 0 },
  { ratio: 0.618, label: "0.618", price: _retr(0.618), kind: "retr", role: "support", role_label: "golden pocket",        status: "held (prior)",    conf: 0.78,  tone: "amb",  hit: true,  respect: 2 },
  { ratio: 0.786, label: "0.786", price: _retr(0.786), kind: "retr", role: "support", role_label: "deep / last defense",  status: "untested",        conf: 0.60,  tone: "cy",   hit: false, respect: 0 },
];
const FB_FIX_EXT = [
  { ratio: 1.272, label: "1.272", price: _ext(1.272), kind: "ext", role: "resistance", role_label: "T1 · primary objective",  conf: 0.66, tone: "gn" },
  { ratio: 1.618, label: "1.618", price: _ext(1.618), kind: "ext", role: "resistance", role_label: "T2 · golden extension",   conf: 0.47, tone: "gn" },
  { ratio: 2.000, label: "2.000", price: _ext(2.000), kind: "ext", role: "resistance", role_label: "T3 · parabolic stretch",  conf: 0.22, tone: "amb" },
];

const FB_FIX_SWING    = { lo: FB_SL, hi: FB_SH, lo_i: 6, hi_i: 30, direction: "up" };
const FB_FIX_GOLDEN   = { lo: _retr(0.650), hi: _retr(0.618) };
const FB_FIX_CLUSTERS = [
  { kind: "SUPPORT", zone: `$${_retr(0.618).toFixed(1)}–${(_retr(0.618) + 1.5).toFixed(1)}`, factors: ["0.618 retr", "Wyckoff ST", "Gartley B"], strength: 0.86, tone: "gn" },
  { kind: "TARGET",  zone: `$${_ext(1.272).toFixed(1)}–${(_ext(1.272) + 2).toFixed(1)}`,    factors: ["1.272 ext", "Elliott W5", "Wyckoff P&F"],  strength: 0.81, tone: "gn" },
  { kind: "TARGET",  zone: `$${_ext(1.618).toFixed(1)}–${(_ext(1.618) + 1).toFixed(1)}`,    factors: ["1.618 ext", "Classical T2"],                strength: 0.52, tone: "amb" },
];
const FB_FIX_STAT = {
  swing:           `${FB_SL} → ${FB_SH}`,
  golden_pocket:   `${_retr(0.650).toFixed(1)} – ${_retr(0.618).toFixed(1)}`,
  support_cluster: `$${_retr(0.618).toFixed(1)} · 3-hit`,
  next_target:     `$${_ext(1.272).toFixed(1)}`,
};
const FB_FIX_INVALID = {
  price: _retr(0.786),
  note: `Loss of the 0.786 retracement at $${_retr(0.786).toFixed(2)} breaks the swing structure — projection void below the swing low $${FB_SL}.`,
};

// mock bar series — closes pass through the fixture swing pivots
function _buildMockBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x1f5;
  const anchors = [
    { i: 0, price: 198 }, { i: 6, price: FB_SL }, { i: 14, price: 195 }, { i: 22, price: 205 },
    { i: 30, price: FB_SH }, { i: 38, price: 204 }, { i: 44, price: 208 }, { i: 50, price: 213.4 },
  ];
  return buildSeries({ n: 51, anchors, seed, volSpikes: { 6: 1.6, 30: 1.5 } });
}

var FB_FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  swing: FB_FIX_SWING, golden_pocket: FB_FIX_GOLDEN,
  retr_levels: FB_FIX_RETR, ext_levels: FB_FIX_EXT,
  levels: [...FB_FIX_RETR, ...FB_FIX_EXT],
  clusters: FB_FIX_CLUSTERS,
  stat: FB_FIX_STAT, invalidation: FB_FIX_INVALID,
  read: `Major swing ${FB_SL}→${FB_SH}. Support golden pocket $${_retr(0.618).toFixed(1)}–$${(_retr(0.618) + 1.5).toFixed(1)} stacks .618 + Wyckoff ST + Gartley B (3-hit). Upside cluster $${_ext(1.272).toFixed(1)} = 1.272 ext + Elliott W5 + P&F. Void below $${FB_SL}.`,
  confidence: 0.81,
};

// ── data hook: real → fixture fallback (mode-aware) ─────────────────────────
function useFibonacciModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("fibonacci", ticker, mode);
  const mockBars = useMemoFb(() => _buildMockBars(ticker), [sym]);
  const tf = (real && real.meta && real.meta.tf) || null;

  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length &&
    real.swing && real.levels && real.levels.length
  );

  if (usable) {
    const m = real;
    return {
      model: {
        isReal: true, source: "real", tf,
        bars:        m.bars,
        swing:       m.swing,
        golden_pocket: m.golden_pocket || { lo: 0, hi: 0 },
        retr_levels: m.retr_levels || [],
        ext_levels:  m.ext_levels  || [],
        levels:      m.levels      || [],
        clusters:    _buildClusters(m),
        stat:        m.stat        || {},
        invalidation: m.invalidation || {},
        read:        m.read        || "",
        confidence:  m.confidence  || 0,
        current:     m.current     || {},
      },
      state: "real", sym, tf, usable: true,
    };
  }

  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...FB_FIXTURE_MODEL, bars: mockBars, tf },
      state: "none", sym, tf, usable: false,
      message: (real && real.message) || "No usable Fibonacci structure detected.",
    };
  }

  return {
    model: { ...FB_FIXTURE_MODEL, bars: mockBars },
    state: state === "loading" ? "loading" : "mock", sym, tf, usable: false,
  };
}

// Derive confluence clusters from real levels + cross-theory labels
function _buildClusters(real) {
  if (!real || !real.levels) return FB_FIX_CLUSTERS;
  const levels = real.levels || [];
  const swing  = real.swing  || {};
  const lo = swing.lo || 0, hi = swing.hi || 0;
  const rng = hi - lo;
  const clusters = [];

  // golden pocket cluster
  const gp = real.golden_pocket || {};
  if (gp.lo && gp.hi) {
    const gpLv = levels.find(l => l.ratio === 0.618 && l.kind === "retr");
    const gpFactors = ["0.618 retr", "golden pocket"];
    if (gpLv && gpLv.hit && gpLv.respect >= 2) gpFactors.push(`${gpLv.respect}-hit`);
    clusters.push({
      kind: swing.direction === "up" ? "SUPPORT" : "RESISTANCE",
      zone: `$${(+gp.lo).toFixed(2)}–${(+gp.hi).toFixed(2)}`,
      factors: gpFactors,
      strength: Math.min(0.95, 0.55 + (gpLv && gpLv.respect ? gpLv.respect * 0.05 : 0)),
      tone: "amb",
    });
  }

  // T1 extension cluster
  const t1 = levels.find(l => l.ratio === 1.272 && l.kind === "ext");
  if (t1) {
    clusters.push({
      kind: "TARGET",
      zone: `$${(+t1.price - 0.5).toFixed(2)}–${(+t1.price + 0.5).toFixed(2)}`,
      factors: ["1.272 ext", "primary objective"],
      strength: real.confidence ? Math.min(0.88, real.confidence * 0.90) : 0.62,
      tone: "gn",
    });
  }

  // T2 extension cluster
  const t2 = levels.find(l => l.ratio === 1.618 && l.kind === "ext");
  if (t2) {
    clusters.push({
      kind: "TARGET",
      zone: `$${(+t2.price - 0.5).toFixed(2)}–${(+t2.price + 0.5).toFixed(2)}`,
      factors: ["1.618 ext", "golden extension"],
      strength: real.confidence ? Math.min(0.65, real.confidence * 0.65) : 0.44,
      tone: "gn",
    });
  }

  return clusters.length ? clusters : FB_FIX_CLUSTERS;
}

// ── chart ────────────────────────────────────────────────────────────────────
function FibChart({ model, height = 320 }) {
  const bars    = (model && model.bars)   || [];
  const swing   = (model && model.swing)  || {};
  const levels  = (model && model.levels) || [];
  const golden  = (model && model.golden_pocket) || {};

  // swing trendline annotation
  const lines = [];
  if (swing.lo_i != null && swing.hi_i != null && swing.lo != null && swing.hi != null) {
    lines.push({
      pts: [
        { i: swing.direction === "up" ? swing.lo_i : swing.hi_i,
          price: swing.direction === "up" ? swing.lo : swing.hi },
        { i: swing.direction === "up" ? swing.hi_i : swing.lo_i,
          price: swing.direction === "up" ? swing.hi : swing.lo },
      ],
      tone: "ink-2", width: 1.4, dash: "4 3", opacity: 0.55,
    });
  }

  // hlines for every Fibonacci level
  const hlines = levels.map(lv => ({
    price: lv.price,
    label: `${lv.label}  $${(+lv.price).toFixed(2)}`,
    tone: lv.tone || "cy",
    dash: lv.kind === "ext" ? "5 4" : "4 5",
    labelBelow: lv.kind === "ext" && lv.role === "resistance",
  }));

  // golden pocket zone
  const zones = [];
  if (golden.lo && golden.hi) {
    zones.push({
      lo: golden.lo, hi: golden.hi,
      tone: "amb",
      label: `GP ${(+golden.lo).toFixed(2)}–${(+golden.hi).toFixed(2)}`,
    });
  }

  // swing anchor markers
  const markers = [];
  if (swing.lo_i != null && swing.lo != null) {
    markers.push({ i: swing.lo_i, label: swing.direction === "up" ? "SwingLo" : "SwingHi",
                   tone: "ink-2", place: swing.direction === "up" ? "below" : "above" });
  }
  if (swing.hi_i != null && swing.hi != null) {
    markers.push({ i: swing.hi_i, label: swing.direction === "up" ? "SwingHi" : "SwingLo",
                   tone: "ink-2", place: swing.direction === "up" ? "above" : "below" });
  }

  return (
    <CandleChart bars={bars} height={height}
      hlines={hlines} markers={markers} lines={lines}
      zones={zones} accent="amb" />
  );
}

// ── retracement grid table ───────────────────────────────────────────────────
function FibRetrTable({ rows, dense }) {
  const list = (rows && rows.length) ? rows : FB_FIX_RETR;
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Retr.", k: "lvl", mono: true },
        { h: "Price",  k: "price", mono: true, align: "right" },
        { h: "Role",   k: "role" },
        { h: "Status", k: "status" },
        { h: "Conf.",  k: "conf",  align: "right" },
      ]}
      rows={list.map(r => ({
        lvl:    <b style={{ color: `var(--${r.tone})` }}>{r.label}</b>,
        price:  <b>${(+r.price).toFixed(2)}</b>,
        role:   <span className="dim2">{r.role_label || r.role}</span>,
        status: <span className="mono dim2" style={{ fontSize: 11 }}>{r.status || "untested"}</span>,
        conf:   r.conf == null
          ? <span className="dim mono">—</span>
          : <ConfBar value={r.conf} tone={r.tone} width={48} />,
      }))} />
  );
}

// ── extension targets table ──────────────────────────────────────────────────
function FibExtTable({ rows, dense }) {
  const list = (rows && rows.length) ? rows : FB_FIX_EXT;
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Ext.",      k: "lvl",   mono: true },
        { h: "Price",     k: "price",  mono: true, align: "right" },
        { h: "Objective", k: "basis" },
        { h: "Conf.",     k: "conf",   align: "right" },
      ]}
      rows={list.map(r => ({
        lvl:   <b style={{ color: `var(--${r.tone})` }}>{r.label}</b>,
        price: <b>${(+r.price).toFixed(2)}</b>,
        basis: <span className="dim2" style={{ fontSize: 11 }}>{r.role_label || r.role}</span>,
        conf:  r.conf == null
          ? <span className="dim mono">—</span>
          : <ConfBar value={r.conf} tone={r.tone} width={48} />,
      }))} />
  );
}

// ── confluence clusters ──────────────────────────────────────────────────────
function FibClusters({ clusters }) {
  const list = (clusters && clusters.length) ? clusters : FB_FIX_CLUSTERS;
  return (
    <div className="pv-clusters">
      {list.map((c, k) => (
        <div key={k} className={`pv-cluster pv-cluster--${c.tone}`}>
          <div className="pv-cluster-head">
            <Pill tone={c.kind === "SUPPORT" || c.kind === "RESISTANCE" ? "cy" : "gn"} small>
              {c.kind}
            </Pill>
            <span className="pv-cluster-zone mono">{c.zone}</span>
            <span className="pv-cluster-strength mono" style={{ color: `var(--${c.tone})` }}>
              {Math.round((c.strength || 0) * 100)}%
            </span>
          </div>
          <div className="pv-cluster-bar">
            <span style={{ width: `${(c.strength || 0) * 100}%`, background: `var(--${c.tone})` }} />
          </div>
          <div className="pv-cluster-factors">
            {(c.factors || []).map((f, j) => <span key={j} className="pv-chip mono">{f}</span>)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── stat strip ───────────────────────────────────────────────────────────────
function FibStat({ stat, confidence, current }) {
  const s   = stat || FB_FIXTURE_MODEL.stat;
  const cur = current || {};
  const nrs = cur.nearest_support;
  const nrr = cur.nearest_resistance;

  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Major swing</div>
        <div className="pv-stat-v mono">{s.swing || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Golden pocket</div>
        <div className="pv-stat-v mono warn">{s.golden_pocket || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Support cluster</div>
        <div className="pv-stat-v mono cy">{s.support_cluster || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Next target</div>
        <div className="pv-stat-v mono up">{s.next_target || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v">
          <ConfBar value={confidence != null ? confidence : 0.81} tone="amb" width={72} />
        </div>
      </div>
    </div>
  );
}

// ── invalidation ─────────────────────────────────────────────────────────────
function FibInvalid({ invalidation }) {
  const inv = invalidation || FB_FIXTURE_MODEL.invalidation;
  return (
    <div className="pv-invalid" style={{ margin: "0 16px 14px" }}>
      <span className="label-cap">Invalidation</span>
      <span className="mono">{inv.note || "—"}</span>
    </div>
  );
}

// ── honest empty state ────────────────────────────────────────────────────────
function FibNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Fibonacci structure</div>
        <div className="pv-empty-msg">
          {message || `No significant pivot-based swing found on ${sym || "this name"}'s chart. Price is trending uniformly or lacks a clear swing anchor — Fibonacci has no reliable grid here right now.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          The detector requires a prominent swing high + swing low (min 1.5 ATR prominence, min span 10 bars). When a clear swing forms it will populate automatically.
        </div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions, mode-aware) ─────────────────────────────────
function FibonacciView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useFibonacciModel(ticker, mode);
  const real = usable ? model : null;

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <FibNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym}
        tier={real && real.tier} tf={tf} />
    </div>
  );

  const Chart = (
    <FibChart model={model} height={dir === "C" ? 250 : 330} />
  );

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <FibStat stat={model.stat} confidence={model.confidence} current={model.current} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Fib grid — annotated"
              sub="retracements + extensions on the major swing · golden pocket zone" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Confluence clusters" style="minimal" />
            <div className="pv-pad"><FibClusters clusters={model.clusters} /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Retracements" style="minimal" />
            <div className="pv-pad"><FibRetrTable rows={model.retr_levels} dense /></div>
            <SectionHeader n={4} title="Extensions" style="minimal" />
            <div className="pv-pad"><FibExtTable rows={model.ext_levels} dense /></div>
          </div>
        </div>
        <FibInvalid invalidation={model.invalidation} />
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <FibStat stat={model.stat} confidence={model.confidence} current={model.current} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Retracement grid</div>
            <FibRetrTable rows={model.retr_levels} dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Extension targets</div>
            <FibExtTable rows={model.ext_levels} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Confluence clusters</div>
            <FibClusters clusters={model.clusters} />
          </div>
        </div>
        <FibInvalid invalidation={model.invalidation} />
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <FibStat stat={model.stat} confidence={model.confidence} current={model.current} />
      <SectionHeader n={1} title="Fibonacci grid — annotated"
        sub="retracements 23.6→78.6 · extensions 127/161/200 · golden pocket zone" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <SectionHeader n={2} title="Confluence clusters"
        sub="where Fib stacks with structure (the WEFCE projection pillar)" style="minimal" />
      <div className="pv-pad"><FibClusters clusters={model.clusters} /></div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Retracement grid</div>
          <FibRetrTable rows={model.retr_levels} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Extension targets</div>
          <FibExtTable rows={model.ext_levels} />
        </div>
      </div>
      <FibInvalid invalidation={model.invalidation} />
    </div>
  );
}

Object.assign(window, { FibonacciView });
