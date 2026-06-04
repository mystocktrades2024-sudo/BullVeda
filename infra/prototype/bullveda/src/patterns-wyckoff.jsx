// patterns-wyckoff.jsx — Wyckoff sub-tab.
//
// REAL DATA: the schematic (events / phases / range / P&F targets / effort-vs-
// result / confidence) is computed server-side by wyckoff_engine.detect_wyckoff
// over live EODHD daily bars and fetched via /api/wyckoff/{sym} (BV.fetchWyckoff).
// The hook reads the cache synchronously and re-renders when the real payload
// resolves. When the server is absent (standalone dev showcase) or returns
// schematic="none", we fall back to the illustrative fixture below — and the
// header badge says so, honestly.

const { useMemo: useMemoWy, useState: useStateWy, useEffect: useEffWy } = React;

const WY_BARS = 78;

// ── illustrative fixture (fallback only — clearly labelled in the UI) ──────────
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

const WY_ER = [
  { ev: "SC",     name: "Selling Climax",       effort: "3.1× vol", result: "wide ▼, closes mid-bar", read: "Demand absorbs climactic supply", tone: "gn" },
  { ev: "AR",     name: "Automatic Rally",      effort: "1.5× vol", result: "wide ▲ off the low", read: "Buyers in control — defines TR top", tone: "gn" },
  { ev: "ST",     name: "Secondary Test",       effort: "0.6× vol", result: "narrow, higher low", read: "Supply diminishing on the test", tone: "gn" },
  { ev: "Spring", name: "Spring / Shakeout",    effort: "1.9× vol", result: "undercut then reclaim", read: "Effort to push down → no result", tone: "gn" },
  { ev: "SOS",    name: "Sign of Strength",     effort: "2.3× vol", result: "widest ▲, closes high", read: "Effort = result — markup confirmed", tone: "gn" },
  { ev: "LPS",    name: "Last Point of Support", effort: "0.55× vol", result: "shallow pullback holds", read: "No supply on the reaction", tone: "gn" },
];

const WY_TGT = [
  { label: "T1 · conservative", basis: "TR height (16) added to 205", price: "221.0", rr: "+3.6%", conf: 0.72, tone: "gn" },
  { label: "T2 · measured",     basis: "1.6× count → 205 + 26",       price: "231.0", rr: "+8.2%", conf: 0.54, tone: "gn" },
  { label: "T3 · full count",   basis: "2.0× count → 205 + 32",       price: "237.0", rr: "+11.1%", conf: 0.38, tone: "amb" },
];

const WY_INVALID = { price: 187.60, note: "Daily close back below the Spring low $187.60 — re-distribution, stand aside." };

const WY_STAT = { schematic: "Accumulation", phase: "D · mark-up", range: "189 – 205", operator: "ACCUMULATING", confidence: 0.71 };

// mock bar series — closes pass through the fixture event prices
function buildMockBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x9e3;
  const anchors = [
    { i: 0, price: 224 }, { i: 6, price: 206 }, { i: 10, price: 190 }, { i: 16, price: 205 },
    { i: 24, price: 193 }, { i: 30, price: 200 }, { i: 36, price: 194 }, { i: 40, price: 191 },
    { i: 46, price: 197 }, { i: 54, price: 209 }, { i: 60, price: 206 }, { i: 64, price: 210 },
    { i: 70, price: 215 }, { i: 77, price: 213.4 },
  ];
  const volSpikes = { 10: 3.1, 16: 1.5, 24: 0.6, 40: 1.9, 54: 2.3, 60: 0.55, 64: 0.7 };
  const wicks = {}; WY_EVENTS.forEach(e => { if (e.wick) wicks[e.i] = e.wick; });
  return buildSeries({ n: WY_BARS, anchors, seed, volSpikes, wicks });
}

const WY_MOCK_MODEL = {
  schematic: "accumulation", isReal: false, source: "illustrative",
  events: WY_EVENTS, phases: WY_PHASES, range: WY_RANGE,
  effort: WY_ER, targets: WY_TGT, invalidation: WY_INVALID, stat: WY_STAT,
};

// ── data hook: real → fixture fallback (mode-aware) ───────────────
function useWyckoffModel(ticker, mode) {
  const { real, state, sym, mode: md } = usePatternModel("wyckoff", ticker, mode);
  const mockBars = useMemoWy(() => buildMockBars(ticker), [sym]);
  const tf = (real && real.meta && real.meta.tf) || null;

  // real, fully-formed payload?
  if (state === "loaded" && real.ok && real.schematic && real.schematic !== "none" && real.bars && real.bars.length) {
    return {
      model: {
        schematic: real.schematic, isReal: true, source: "real",
        tier: real.tier, ticker: real.ticker, tf, mode: md,
        bars: real.bars, events: real.events || [], phases: real.phases || [],
        range: real.range || {}, effort: real.effort || [], targets: real.targets || [],
        invalidation: real.invalidation || null, stat: real.stat || null,
        broke_out: real.broke_out, phase: real.phase,
      },
      state: "real", sym, tf,
    };
  }
  // real responded but no structure → honest empty state
  if (state === "loaded" && real.ok) {
    return { model: { ...WY_MOCK_MODEL, bars: mockBars, tf, mode: md }, state: "none", message: real.message, sym, tf };
  }
  // not yet loaded (or server absent) → illustrative fixture
  return { model: { ...WY_MOCK_MODEL, bars: mockBars, mode: md }, state: state === "loading" ? "loading" : "mock", sym, tf };
}

// ── source badge ──────────────────────────────────────────────────
function WySourceBadge({ state, sym, tier, tf }) {
  if (state === "real") {
    return <span className="wy-src wy-src--real mono" title={`computed from live ${tf || "daily"} bars · ${tier || "eodhd"}`}>● REAL · {sym || ""}{tf ? " · " + tf : ""}</span>;
  }
  if (state === "loading") {
    return <span className="wy-src wy-src--load mono">◌ loading live structure…</span>;
  }
  if (state === "none") {
    return <span className="wy-src wy-src--none mono" title="no climactic base detected on the daily">— no structure · illustrative</span>;
  }
  return <span className="wy-src wy-src--mock mono" title="standalone showcase — connect to :7432 for live structure">◑ illustrative</span>;
}

// ── chart: builds bands / markers / hlines from the model ─────────
function WyckoffChart({ model, ticker, height = 320 }) {
  const bars = model.bars || [];
  const bands = (model.phases || []).map(p => ({
    from: p.from, to: p.to, label: p.id, tone: p.current ? "copper" : "ink-3",
  }));
  const r = model.range || {};
  const hlines = [];
  if (r.resistance) hlines.push({ price: r.resistance, label: `Resistance ${(+r.resistance).toFixed(r.resistance < 20 ? 2 : 0)}`, tone: "ink-2", dash: "2 4" });
  if (r.support) hlines.push({ price: r.support, label: `Support ${(+r.support).toFixed(r.support < 20 ? 2 : 0)}`, tone: "ink-2", dash: "2 4" });
  const t1 = (model.targets || [])[0];
  if (t1 && t1.price) hlines.push({ price: parseFloat(t1.price), label: `T1 ${t1.price}`, tone: model.schematic === "distribution" ? "rd" : "gn", dash: "5 4" });
  const inv = model.invalidation;
  if (inv && inv.price) hlines.push({ price: +inv.price, label: `Invalidate ${(+inv.price).toFixed(2)}`, tone: "rd", dash: "3 3", labelBelow: true });
  const markers = (model.events || []).map(e => ({ i: e.i, label: e.code, tone: e.tone, place: e.place }));
  const accent = model.schematic === "distribution" ? "rd" : "copper";
  return <CandleChart bars={bars} height={height} bands={bands} hlines={hlines} markers={markers} accent={accent} />;
}

// ── A–E phase track ─────────────────────────────────────────────
function WyckoffPhases({ phases }) {
  const list = phases && phases.length ? phases : WY_PHASES;
  return (
    <div className="pv-phases">
      {list.map(p => (
        <div key={p.id} className={`pv-phase ${p.current ? "is-current" : p.done ? "is-done" : "is-future"}`}>
          <div className="pv-phase-top">
            <span className="pv-phase-id mono">{p.id}</span>
            {p.current ? <Pill tone="copper" small>NOW</Pill> : p.done ? <span className="pv-phase-check">✓</span> : <span className="pv-phase-dot" />}
          </div>
          <div className="pv-phase-label mono">{(p.label || "").replace(/^[A-E] · /, "")}</div>
          <div className="pv-phase-note">{p.note}</div>
        </div>
      ))}
    </div>
  );
}

// ── event timeline (detailed log) ───────────────────────────────
function WyckoffTimeline({ events }) {
  const list = events && events.length ? events : WY_EVENTS;
  const lastCode = list.length ? list[list.length - 1].code : null;
  return (
    <div className="pv-timeline">
      {list.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.code === lastCode ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone})` }} />
            {k < list.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone})` }}>{e.code}</span>
              <span className="pv-tl-name">{e.name}</span>
              <span className="pv-tl-meta mono dim">Ph {e.phase} · {e.date} · <b>${(+e.price).toFixed(2)}</b></span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── effort-vs-result reads ──────────────────────────────────────
function WyckoffEffort({ rows, dense }) {
  const list = rows && rows.length ? rows : WY_ER;
  return <MiniTable dense={dense}
    cols={[{ h: "Event", k: "ev" }, { h: "Effort (vol)", k: "effort", mono: true },
           { h: "Result (spread/close)", k: "result" }, { h: "Read", k: "read" }]}
    rows={list.map(r => ({ ...r, ev: <span><b style={{ color: `var(--${r.tone})` }}>{r.name}</b> <span className="dim mono" style={{ fontSize: 10 }}>{r.ev}</span></span> }))} />;
}

// ── point-&-figure targets + invalidation ───────────────────────
function WyckoffTargets({ targets, invalidation }) {
  const list = targets && targets.length ? targets : WY_TGT;
  const inv = invalidation || WY_INVALID;
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Objective", k: "label" }, { h: "Basis (cause → effect)", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" }, { h: "R:R", k: "rr", mono: true, align: "right" },
               { h: "Confidence", k: "conf", align: "right" }]}
        rows={list.map(t => ({
          label: <span><b style={{ color: `var(--${t.tone})` }}>{(t.label || "").split(" · ")[0]}</b> <span className="dim">· {(t.label || "").split(" · ")[1]}</span></span>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>, rr: <span className={(t.rr || "").startsWith("-") ? "dn" : "up"}>{t.rr}</span>,
          conf: t.conf == null ? <span className="dim mono">—</span> : <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">{inv.note}</span>
      </div>
    </div>
  );
}

// ── header strip (verdict) ──────────────────────────────────────
function WyckoffStat({ stat }) {
  const s = stat || WY_STAT;
  const opTone = s.operator === "DISTRIBUTING" ? "dn" : s.operator === "NEUTRAL" ? "dim2" : "up";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Schematic</div><div className="pv-stat-v mono">{s.schematic}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Phase</div><div className="pv-stat-v mono copper">{s.phase}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Range</div><div className="pv-stat-v mono">{s.range}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Composite Operator</div><div className={`pv-stat-v mono ${opTone}`}>{s.operator}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={s.confidence} tone="copper" width={72} /></div></div>
    </div>
  );
}

// ── honest empty state (real feed, no structure) ────────────────
function WyckoffNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Wyckoff structure</div>
        <div className="pv-empty-msg">{message || `No climactic accumulation/distribution base on ${sym || "this name"}'s daily chart. Price is trending or unstructured — Wyckoff has no edge here right now.`}</div>
        <div className="pv-empty-sub mono dim2">The detector requires a volume-climax → trading-range → spring/SOS sequence on real bars. When one forms it will populate automatically.</div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions) ───────────────────────────────
function WyckoffView({ ticker, dir, mode }) {
  const { model, state, message, sym } = useWyckoffModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar"><WySourceBadge state={state} sym={sym} /></div>
        <WyckoffNone sym={sym} message={message} />
      </div>
    );
  }

  const Chart = <WyckoffChart model={model} ticker={ticker} height={dir === "C" ? 250 : 330} />;
  const SrcBar = <div className="pv-srcbar"><WySourceBadge state={state} sym={sym || model.ticker} tier={model.tier} tf={model.tf} /></div>;

  if (dir === "B") {
    // SPLIT — chart left, stacked analysis right
    return (
      <div className="pv-view">
        {SrcBar}
        <WyckoffStat stat={model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Accumulation — annotated" sub="events pinned to real bars · A–E phase bands" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Effort vs Result" sub="volume against spread & close" style="minimal" />
            <div className="pv-pad"><WyckoffEffort rows={model.effort} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Phase track" style="minimal" />
            <div className="pv-pad"><WyckoffPhases phases={model.phases} /></div>
            <SectionHeader n={4} title="P&F targets" style="minimal" />
            <div className="pv-pad"><WyckoffTargets targets={model.targets} invalidation={model.invalidation} /></div>
          </div>
        </div>
        <SectionHeader n={5} title="Event timeline" sub="schematic, dated & scored" style="minimal" />
        <div className="pv-pad"><WyckoffTimeline events={model.events} /></div>
      </div>
    );
  }

  if (dir === "C") {
    // DOSSIER — compact chart, data-dense tables stacked
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <WyckoffStat stat={model.stat} />
        <div className="pv-pad">{Chart}</div>
        <WyckoffPhases phases={model.phases} />
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Event log</div>
            <WyckoffTimeline events={model.events} />
          </div>
          <div>
            <div className="pv-block-h label-cap">Effort vs result</div>
            <WyckoffEffort rows={model.effort} dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Targets &amp; invalidation</div>
            <WyckoffTargets targets={model.targets} invalidation={model.invalidation} />
          </div>
        </div>
      </div>
    );
  }

  // A — CHART-LED (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <WyckoffStat stat={model.stat} />
      <SectionHeader n={1} title={`${model.stat ? model.stat.schematic : "Accumulation"} schematic — annotated`} sub="PS · SC · AR · ST · Spring · Test · SOS · LPS on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <WyckoffPhases phases={model.phases} />
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Event timeline</div>
          <WyckoffTimeline events={model.events} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Effort vs result</div>
          <WyckoffEffort rows={model.effort} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>P&amp;F targets &amp; invalidation</div>
          <WyckoffTargets targets={model.targets} invalidation={model.invalidation} />
        </div>
      </div>
    </div>
  );
}

// ── dynamic "The Read · Wyckoff" line (lens-call) — real when available ──
function WyckoffReadLine({ ticker, mode }) {
  const { model, state } = useWyckoffModel(ticker, mode);
  if (state === "none") {
    return <span className="mono">No climactic accumulation/distribution base on the daily — Wyckoff is <b className="dim2">stand-aside</b> here. Wait for a volume-climax → range → spring/SOS sequence to form.</span>;
  }
  if (state !== "real") {
    // illustrative fallback (showcase / pre-load) — keep the original copy
    return <span className="mono">Composite operator is <b className="copper">accumulating</b> — Phase D after a confirmed Spring + SOS. Mark-up on a close &gt; <b className="copper">$213.40</b>; P&amp;F count projects <b className="up">$221 → $237</b>. Invalid below <b className="dn">$187.60</b>.</span>;
  }
  const st = model.stat || {};
  const accum = model.schematic === "accumulation";
  const tgts = model.targets || [];
  const t1 = tgts[0] && tgts[0].price, t3 = tgts[tgts.length - 1] && tgts[tgts.length - 1].price;
  const inv = model.invalidation && model.invalidation.price;
  const r = model.range || {};
  const trigger = accum ? r.resistance : r.support;
  const evCodes = (model.events || []).map(e => e.code);
  const seq = evCodes.length ? evCodes.slice(-3).join(" → ") : "—";
  return (
    <span className="mono">
      Composite operator is <b className={accum ? "up" : "dn"}>{(st.operator || "").toLowerCase()}</b> —
      Phase <b className="copper">{model.phase || st.phase}</b> ({seq}).
      {trigger != null && <> {accum ? "Mark-up" : "Mark-down"} on a close {accum ? "above" : "below"} <b className="copper">${(+trigger).toFixed(2)}</b>;</>}
      {t1 && <> P&amp;F count projects <b className={accum ? "up" : "dn"}>${t1}{t3 && t3 !== t1 ? ` → $${t3}` : ""}</b>;</>}
      {inv != null && <> invalid {accum ? "below" : "above"} <b className="dn">${(+inv).toFixed(2)}</b>.</>}
    </span>
  );
}

Object.assign(window, { WyckoffView, WyckoffReadLine });
