// patterns-gann.jsx — W.D. Gann theory sub-tab.
//
// REAL DATA: Gann fan angles (1×1, 2×1, 1×2…) + Square-of-Nine price levels +
// time-cycle turn windows are computed server-side by engines/gann.py from live
// EODHD bars and fetched via the shared usePatternModel("gann", ticker, mode)
// hook. The hook is mode-aware: SWING=daily, POSITION=weekly, INVEST=monthly.
//
// When the server is absent (standalone dev showcase) or the engine returns no
// structure, we fall back to the illustrative fixture below — the badge says so.
//
// Mechanism: Gann angles encode a fixed price-per-time rate from a significant
// pivot. The 1×1 line is the "balance" between price and time. Square-of-Nine
// levels are harmonic spiral targets. Treat as a CONFLUENCE OVERLAY only.

const { useMemo: useMemoGn } = React;

// ── illustrative fixture (fallback only — clearly labelled in the UI) ─────────
const GN_FIXTURE_PIVOT = { i: 8, price: 180 };
const GN_FIXTURE_K = 0.6; // 1×1 = 0.6 price / bar (chart-scaled)

function _buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x3b9;
  const anchors = [
    { i: 0, price: 188 }, { i: 8, price: 180 }, { i: 20, price: 192 }, { i: 30, price: 198 },
    { i: 42, price: 205 }, { i: 52, price: 213.4 },
  ];
  return buildSeries({ n: 53, anchors, seed, volSpikes: {} });
}

function _buildFixtureLines() {
  const end = 74;
  const fan = (mult, tone, dash) => ({
    pts: [{ i: GN_FIXTURE_PIVOT.i, price: GN_FIXTURE_PIVOT.price },
          { i: end, price: GN_FIXTURE_PIVOT.price + GN_FIXTURE_K * mult * (end - GN_FIXTURE_PIVOT.i) }],
    tone, dash, width: mult === 1 ? 1.8 : 1.2, opacity: mult === 1 ? 0.95 : 0.6,
  });
  return [
    fan(2, "gn", "4 4"),
    fan(1, "copper", null),
    fan(0.5, "cy", "4 4"),
    fan(0.25, "ink-2", "3 4"),
  ];
}

var GN_FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  bars: null, // filled lazily per-ticker in useGannModel
  fan_lines: _buildFixtureLines(),
  sq9_hlines: [
    { price: 219, label: "Sq9 · 219 (90°)",  tone: "violet", dash: "2 5" },
    { price: 207, label: "Sq9 · 207 (45°)",  tone: "violet", dash: "2 5" },
    { price: 232, label: "Sq9 · 232 (180°)", tone: "gn",     dash: "5 4" },
  ],
  pivot_marker: { i: GN_FIXTURE_PIVOT.i, price: GN_FIXTURE_PIVOT.price, label: "Pivot", tone: "copper", place: "below" },
  pivot_bands:  [{ from: 37, to: 39, label: "T30", tone: "ink-3" }, { from: 67, to: 69, label: "T60", tone: "copper" }],
  span: 80, projectFrom: 53,
  angles: [
    { a: "2×1", deg: "63.75°", now: "$252", role: "steep · only in strong trends", st: "above px",   tone: "gn" },
    { a: "1×1", deg: "45°",    now: "$216", role: "the master line · trend pivot",  st: "px just below", tone: "copper" },
    { a: "1×2", deg: "26.25°", now: "$198", role: "support · shallow uptrend",      st: "below px",  tone: "cy" },
    { a: "1×4", deg: "15°",    now: "$192", role: "last-ditch support",             st: "below px",  tone: "ink-2" },
  ],
  sq9: [
    { lvl: "$207", rot: "45°",  role: "first resistance · cleared",  tone: "gn" },
    { lvl: "$219", rot: "90°",  role: "next overhead · cardinal",    tone: "violet" },
    { lvl: "$232", rot: "180°", role: "measured Gann target",        tone: "gn" },
    { lvl: "$196", rot: "315°", role: "support on a pullback",       tone: "cy" },
  ],
  cycles: [
    { c: "30-bar count", date: "Jun 18", role: "minor turn window",            tone: "ink-2" },
    { c: "60-bar count", date: "Jul 30", role: "major cycle · price-time sq.", tone: "copper" },
    { c: "90° in time",  date: "Aug 14", role: "anniversary of pivot low",    tone: "violet" },
  ],
  stat: {
    master_angle:  "1×1 · $216",
    price_vs_1x1:  "just below",
    next_sq9:      "$219 (90°)",
    next_turn:     "Jun 18",
    confidence:    0.48,
  },
  read: "Price rides just under the 1×1 master line ($216); next Sq-9 at $219. Next time turn: Jun 18. Confluence overlay only.",
  sq_note: "Illustrative fixture — connect to :7432 for real Gann analysis.",
};

// ── data hook: real → fixture fallback ────────────────────────────────────────
function useGannModel(ticker, mode) {
  const { real, state, sym, mode: md } = usePatternModel("gann", ticker, mode);
  const fixtureBars = useMemoGn(() => _buildFixtureBars(ticker), [sym]);
  const tf = (real && real.meta && real.meta.tf) || null;

  // Usability gate: need bars + angles + sq9
  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length > 0 &&
    real.angles && real.angles.length > 0
  );

  if (usable) {
    // Map server payload → shape sub-components expect
    const srv = real;
    const st = srv.stat || {};
    // Build next turn from cycles
    const nextTurn = ((srv.cycles || []).find(c => !c.passed) || (srv.cycles || [])[srv.cycles.length - 1] || {}).date || "—";
    return {
      model: {
        isReal: true, source: "real",
        tier: srv.tier, ticker: srv.ticker, tf, mode: md,
        bars:         srv.bars,
        fan_lines:    (srv.fan_lines || []).map(ln => ({
          pts:     ln.pts,
          tone:    ln.tone,
          dash:    ln.dash,
          width:   ln.width,
          opacity: ln.opacity != null ? ln.opacity : 0.75,
        })),
        sq9_hlines:   srv.sq9_hlines || [],
        pivot_marker: srv.pivot ? {
          i: (srv.pivot.bar_idx != null ? srv.pivot.bar_idx : 0),
          price: srv.pivot.price,
          label: "Pivot " + (srv.pivot.date || ""),
          tone: "copper",
          place: srv.pivot.direction === "up" ? "below" : "above",
        } : null,
        pivot_bands:  [], // real mode: no synthetic phase bands on fan
        span:         (srv.bars || []).length + (((srv.fan_lines || [])[0] || {}).pts || []).reduce((m, p) => Math.max(m, p.i), 0) - (srv.bars || []).length,
        projectFrom:  (srv.bars || []).length,
        angles:       (srv.angles || []).map(a => ({
          a:    a.a,
          deg:  a.deg,
          now:  a.now,
          role: a.role,
          st:   a.st,
          tone: a.tone,
        })),
        sq9:    (srv.sq9 || []).map(s => ({
          lvl:  s.lvl,
          rot:  s.rot,
          role: s.role,
          tone: s.tone || (s.price > (srv.cur_close || 0) ? "gn" : "cy"),
        })),
        cycles: (srv.cycles || []).map(c => ({
          c:    c.c,
          date: c.date,
          role: c.role,
          tone: c.tone,
        })),
        sr:    srv.sr || {},
        stat: {
          master_angle: st.master_angle || "—",
          price_vs_1x1: st.price_vs_1x1 || "—",
          next_sq9:     st.next_sq9 || "—",
          next_turn:    nextTurn,
          confidence:   st.confidence != null ? st.confidence : 0.40,
        },
        read:    srv.read || "",
        sq_note: srv.sq_note || "",
      },
      state: "real", sym, tf, usable: true,
    };
  }

  // Real responded but no structure → honest "none"
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...GN_FIXTURE_MODEL, bars: fixtureBars, tf, mode: md },
      state: "none", message: real.message, sym, tf, usable: false,
    };
  }

  // Not yet loaded or server absent → illustrative fixture
  return {
    model: { ...GN_FIXTURE_MODEL, bars: fixtureBars, mode: md },
    state: state === "loading" ? "loading" : "mock", sym, tf, usable: false,
  };
}

// ── chart sub-component ───────────────────────────────────────────────────────
function GannChart({ model, ticker, height = 330 }) {
  const bars    = model.bars || [];
  const lines   = model.fan_lines || [];
  const hlines  = model.sq9_hlines || [];
  const markers = model.pivot_marker ? [model.pivot_marker] : [];
  const bands   = model.pivot_bands || [];
  const span    = (model.span > 0) ? (bars.length + model.span) : null;
  const projFrom = model.projectFrom || bars.length;

  return (
    <CandleChart
      bars={bars} height={height}
      lines={lines} hlines={hlines} markers={markers}
      bands={bands} accent="copper"
      span={span} projectFrom={projFrom}
    />
  );
}

// ── angle table ───────────────────────────────────────────────────────────────
function GannAngles({ angles, dense }) {
  const list = (angles && angles.length) ? angles : GN_FIXTURE_MODEL.angles;
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Angle",     k: "a",    mono: true },
        { h: "Slope",     k: "deg",  mono: true },
        { h: "Value now", k: "now",  mono: true, align: "right" },
        { h: "Role",      k: "role" },
        { h: "vs price",  k: "st",   align: "right" },
      ]}
      rows={list.map(r => ({
        a:    <b style={{ color: `var(--${r.tone})` }}>{r.a}</b>,
        deg:  <span className="dim2">{r.deg}</span>,
        now:  <b>{r.now}</b>,
        role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span>,
        st:   <Pill tone={r.tone === "ink-2" ? "ink" : r.tone} small>{r.st}</Pill>,
      }))}
    />
  );
}

// ── sq9 table ─────────────────────────────────────────────────────────────────
function GannSq9({ sq9, dense }) {
  const list = (sq9 && sq9.length) ? sq9 : GN_FIXTURE_MODEL.sq9;
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Sq-9 level", k: "lvl",  mono: true },
        { h: "Rotation",   k: "rot",  mono: true },
        { h: "Role",       k: "role" },
      ]}
      rows={list.map(r => ({
        lvl:  <b style={{ color: `var(--${r.tone})` }}>{r.lvl}</b>,
        rot:  <span className="dim2">{r.rot}</span>,
        role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span>,
      }))}
    />
  );
}

// ── time cycles table ─────────────────────────────────────────────────────────
function GannTime({ cycles, dense }) {
  const list = (cycles && cycles.length) ? cycles : GN_FIXTURE_MODEL.cycles;
  return (
    <MiniTable dense={dense}
      cols={[
        { h: "Time cycle",   k: "c" },
        { h: "Turn date",    k: "date", mono: true },
        { h: "Significance", k: "role" },
      ]}
      rows={list.map(r => ({
        c:    <b style={{ color: `var(--${r.tone})` }}>{r.c}</b>,
        date: <b>{r.date}</b>,
        role: <span className="dim2" style={{ fontSize: 11 }}>{r.role}</span>,
      }))}
    />
  );
}

// ── stat header strip ─────────────────────────────────────────────────────────
function GannStat({ stat }) {
  const s = stat || GN_FIXTURE_MODEL.stat;
  const confTone = (s.confidence || 0) >= 0.50 ? "copper" : "amb";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Master angle</div>
        <div className="pv-stat-v mono copper">{s.master_angle || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Price vs 1×1</div>
        <div className="pv-stat-v mono up">{s.price_vs_1x1 || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Next Sq9</div>
        <div className="pv-stat-v mono violet">{s.next_sq9 || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Next time turn</div>
        <div className="pv-stat-v mono">{s.next_turn || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v">
          <ConfBar value={s.confidence != null ? s.confidence : 0.40} tone={confTone} width={72} />
        </div>
      </div>
    </div>
  );
}

// ── "The Read" box ────────────────────────────────────────────────────────────
function GannReadBox({ model }) {
  const read   = (model && model.read)    || GN_FIXTURE_MODEL.read;
  const sqNote = (model && model.sq_note) || GN_FIXTURE_MODEL.sq_note;
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", margin: "12px 16px" }}>
      <span className="label-cap">Read</span>
      <span className="mono">{read}</span>
      {sqNote && (
        <div className="mono dim2" style={{ fontSize: 10, marginTop: 5 }}>{sqNote}</div>
      )}
    </div>
  );
}

// ── honest "none" state ───────────────────────────────────────────────────────
function GannNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Gann structure</div>
        <div className="pv-empty-msg">
          {message || `Not enough bars to compute Gann fan angles for ${sym || "this name"}.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          Gann analysis requires ≥30 bars and a significant pivot. The detector will populate automatically once data is available.
        </div>
      </div>
    </div>
  );
}

// ── main view (3 directions) ──────────────────────────────────────────────────
function GannView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useGannModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <GannNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={model && model.tier} tf={tf} />
    </div>
  );

  const Chart = <GannChart model={model} ticker={ticker} height={dir === "C" ? 250 : 330} />;

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <GannStat stat={model && model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Gann fan + Sq-9 — annotated"
              sub="angles from pivot · square-of-nine levels · time cycles" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Gann angles" style="minimal" />
            <div className="pv-pad"><GannAngles angles={model && model.angles} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Square of Nine" style="minimal" />
            <div className="pv-pad"><GannSq9 sq9={model && model.sq9} /></div>
            <SectionHeader n={4} title="Time cycles" style="minimal" />
            <div className="pv-pad"><GannTime cycles={model && model.cycles} /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <GannStat stat={model && model.stat} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Gann angles</div>
            <GannAngles angles={model && model.angles} dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Square of Nine</div>
            <GannSq9 sq9={model && model.sq9} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Time cycles · turn dates</div>
            <GannTime cycles={model && model.cycles} dense />
          </div>
        </div>
      </div>
    );
  }

  // dir === "A" — Chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <GannStat stat={model && model.stat} />
      <SectionHeader n={1} title="Gann fan + Square of Nine — annotated"
        sub="1×1 master line · price angles from the pivot · Sq-9 levels · time-cycle turns" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Gann angles</div>
          <GannAngles angles={model && model.angles} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Square of Nine levels</div>
          <GannSq9 sq9={model && model.sq9} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Time cycles · projected turns</div>
          <GannTime cycles={model && model.cycles} />
          <GannReadBox model={model} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GannView });
