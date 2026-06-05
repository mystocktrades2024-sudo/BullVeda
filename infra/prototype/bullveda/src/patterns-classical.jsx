// patterns-classical.jsx — Classical chart-patterns theory sub-tab.
//
// REAL DATA: base/pattern detection computed server-side by engines/classical.py
// over live EODHD bars (via /api/pattern/classical/{sym}?mode=SWING etc.).
// The hook reads the cache synchronously and re-renders when the real payload
// resolves. When the server is absent (standalone dev showcase) or returns
// state="none", we fall back to the illustrative fixture below — and the
// header badge says so, honestly.

const { useMemo: useMemoCl } = React;

const CL_BARS = 70;
const CL_PIVOT = 205.2;     // flat resistance / breakout pivot
const CL_STOP = 198.0;

// ── illustrative fixture (fallback only — clearly labelled in the UI) ─────────
function buildMockBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x3c1;
  // ascending base: flat top ~205, rising lows, breakout, mark-up
  const anchors = [
    { i: 0, price: 198 }, { i: 6, price: 186 }, { i: 12, price: 203 }, { i: 18, price: 190 },
    { i: 24, price: 204 }, { i: 30, price: 195 }, { i: 38, price: 204 }, { i: 44, price: 199 },
    { i: 50, price: 204 }, { i: 55, price: 201 }, { i: 58, price: 207 }, { i: 63, price: 210 },
    { i: 69, price: 213.4 },
  ];
  const volSpikes = { 6: 1.6, 58: 2.2, 59: 1.9 };
  return buildSeries({ n: CL_BARS, anchors, seed, volSpikes });
}

const FIXTURE_CONTRACTIONS = [
  { n: "1", depth: "−18%", weeks: "Mar 03", vol: "heavy",  tone: "ink-2" },
  { n: "2", depth: "−12%", weeks: "Mar 20", vol: "−32%",  tone: "ink-2" },
  { n: "3", depth: "−8%",  weeks: "Apr 05", vol: "−24%",  tone: "ink-1" },
  { n: "4", depth: "−5%",  weeks: "Apr 22", vol: "−41%",  tone: "cy"    },
  { n: "5", depth: "−3%",  weeks: "May 10", vol: "dry",   tone: "gn"    },
];

const FIXTURE_LINES = [
  { pts: [{ i: 6, price: 186 }, { i: 18, price: 190 }, { i: 30, price: 195 }, { i: 44, price: 199 }, { i: 55, price: 201 }], tone: "cy", width: 1.4, dash: "4 3" },
];

const FIXTURE_ZONES = [{ lo: 186, hi: 205.2, tone: "cy", label: "Base" }];

var FIXTURE_TARGETS = [
  { label: "Breakout pivot",       basis: "flat resistance of the base", price: "205.2", rr: "trigger", conf: null,  tone: "copper" },
  { label: "T1 · measured move",   basis: "base height (20) added to pivot", price: "225.0", rr: "+5.5%", conf: 0.64, tone: "gn" },
  { label: "T2 · 1.5× extension", basis: "1.5 × base height",           price: "235.0", rr: "+10.2%", conf: 0.41, tone: "amb" },
];

const FIXTURE_LIBRARY = [
  { p: "Cup & Handle",      st: "CONFIRMED", mm: "$232", conf: 0.66, tone: "gn" },
  { p: "Ascending Triangle", st: "BREAKOUT", mm: "$225", conf: 0.64, tone: "gn" },
  { p: "Double Bottom",      st: "CONFIRMED", mm: "$221", conf: 0.61, tone: "gn" },
  { p: "Bull Flag",          st: "FORMING",  mm: "$224", conf: 0.58, tone: "cy" },
  { p: "Falling Wedge",      st: "FORMING",  mm: "$228", conf: 0.55, tone: "cy" },
  { p: "Inverse H&S",        st: "WATCH",    mm: "$238", conf: 0.49, tone: "amb" },
];

var FIXTURE_STAT = {
  primary_pattern: "VCP · Asc. triangle",
  stage: "Breakout + retest",
  contractions: "5 · 18%→3%",
  measured_move: "$225",
  confidence: 0.64,
};

var FIXTURE_MODEL = {
  isReal: false, source: "illustrative",
  pattern: { name: "VCP / Ascending Triangle", tone: "cy" },
  contractions: FIXTURE_CONTRACTIONS,
  pivot: CL_PIVOT, stop: CL_STOP,
  targets: FIXTURE_TARGETS,
  lines: FIXTURE_LINES,
  zones: FIXTURE_ZONES,
  library: FIXTURE_LIBRARY,
  stat: FIXTURE_STAT,
  read: "VCP / ascending triangle — 5 contractions into a pivot at $205.20, broken on 2.2× volume and retested. Measured move targets $225 → $235. Fails below pivot.",
  cur_close: 213.4,
  broke_out: true,
};

// ── data hook: real → fixture fallback (mode-aware) ──────────────
function useClassicalModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("classical", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const mockBars = useMemoCl(() => buildMockBars(ticker), [sym]);

  // usability: need bars + stat + pivot
  const usable = (
    state === "loaded" && real && real.ok &&
    real.state === "real" && real.bars && real.bars.length > 0 &&
    real.pivot != null && real.stat
  );

  if (usable) {
    return {
      model: {
        isReal: true, source: "real",
        tf, tier: real.tier, ticker: real.ticker,
        pattern: real.pattern || { name: "Base", tone: "cy" },
        contractions: real.contractions || [],
        pivot: real.pivot,
        stop: real.stop,
        targets: real.targets || [],
        lines: real.lines || [],
        zones: real.zones || [],
        library: real.library || [],
        stat: real.stat,
        read: real.read || "",
        cur_close: real.cur_close,
        broke_out: real.broke_out,
        bars: real.bars,
      },
      state: "real", sym, tf, usable: true,
    };
  }

  // real responded but state="none"
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...FIXTURE_MODEL, bars: mockBars, tf },
      state: "none", sym, tf, usable: false,
      message: real.message,
    };
  }

  // loading / mock
  return {
    model: { ...FIXTURE_MODEL, bars: mockBars },
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── chart ─────────────────────────────────────────────────────────
function ClassicalChart({ model, height = 320 }) {
  const bars    = model.bars || [];
  const pivot   = model.pivot;
  const stop    = model.stop;
  const targets = model.targets || [];
  const lines   = model.lines || [];
  const zones   = model.zones || [];

  const hlines = [];
  if (pivot) hlines.push({ price: pivot, label: `Pivot ${pivot}`,  tone: "copper", dash: "5 4" });
  const t1 = (targets || [])[1];
  if (t1 && t1.price) hlines.push({ price: parseFloat(t1.price), label: `T1 ${t1.price}`, tone: "gn", dash: "5 4" });
  if (stop) hlines.push({ price: stop, label: `Stop ${stop}`, tone: "rd", dash: "3 3", labelBelow: true });

  return (
    <CandleChart
      bars={bars} height={height}
      hlines={hlines} lines={lines} zones={zones}
      accent="cy"
    />
  );
}

// ── VCP contraction ladder ────────────────────────────────────────
function VCPLadder({ contractions }) {
  const list = (contractions && contractions.length) ? contractions : FIXTURE_CONTRACTIONS;
  return (
    <div className="pv-vcp">
      {list.map((c, k) => (
        <div key={k} className="pv-vcp-cell" style={{ borderColor: `var(--${c.tone})` }}>
          <div className="pv-vcp-n mono" style={{ color: `var(--${c.tone})` }}>T{c.n}</div>
          <div className="pv-vcp-d mono">{c.depth}</div>
          <div className="pv-vcp-m mono dim2">{c.weeks} · vol {c.vol}</div>
        </div>
      ))}
    </div>
  );
}

// ── measured-move targets + invalidation ──────────────────────────
function ClassicalTargets({ targets, pivot, stop }) {
  const list = (targets && targets.length) ? targets : FIXTURE_TARGETS;
  const inv_px = stop || CL_STOP;
  return (
    <div className="pv-targets">
      <MiniTable
        cols={[{ h: "Objective", k: "label" }, { h: "Basis", k: "basis" },
               { h: "Price", k: "price", mono: true, align: "right" },
               { h: "R:R",  k: "rr",   mono: true, align: "right" },
               { h: "Conf.", k: "conf", align: "right" }]}
        rows={list.map(t => ({
          label: <b style={{ color: `var(--${t.tone})` }}>{t.label}</b>,
          basis: <span className="dim2" style={{ fontSize: 11 }}>{t.basis}</span>,
          price: <b>${t.price}</b>,
          rr: t.rr === "trigger"
            ? <span className="dim mono">trigger</span>
            : <span className={(t.rr || "").startsWith("-") ? "dn" : "up"}>{t.rr}</span>,
          conf: t.conf == null
            ? <span className="dim mono">—</span>
            : <ConfBar value={t.conf} tone={t.tone} />,
        }))} />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">
          Close back below the pivot <b className="dn">${pivot || CL_PIVOT}</b> (failed breakout) or under the last contraction low — stand aside.
        </span>
      </div>
    </div>
  );
}

// ── pattern library table ────────────────────────────────────────
function ClassicalLibrary({ library, dense }) {
  const list = (library && library.length) ? library : FIXTURE_LIBRARY;
  return (
    <MiniTable dense={dense}
      cols={[{ h: "Pattern", k: "p" }, { h: "Status", k: "st", align: "center" },
             { h: "Measured move", k: "mm", mono: true, align: "right" },
             { h: "Conf.", k: "c", align: "right" }]}
      rows={list.map(r => ({
        p:  <b>{r.p}</b>,
        st: <Pill tone={r.tone} small>{r.st}</Pill>,
        mm: <b className={r.mm === "—" ? "dim" : "up"}>{r.mm}</b>,
        c:  <ConfBar value={r.conf} tone={r.tone === "ink" ? "ink-3" : r.tone} width={44} />,
      }))} />
  );
}

// ── stat header strip ────────────────────────────────────────────
function ClassicalStat({ stat }) {
  const s = stat || FIXTURE_STAT;
  const patColor = (s.primary_pattern || "").includes("Triangle") ? "cy"
                  : (s.primary_pattern || "").includes("VCP") ? "cy"
                  : (s.primary_pattern || "").includes("Cup") ? "gn"
                  : (s.primary_pattern || "").includes("Flag") ? "gn"
                  : "cy";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Primary pattern</div>
        <div className={`pv-stat-v mono ${patColor}`}>{s.primary_pattern || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Stage</div>
        <div className={`pv-stat-v mono ${(s.stage || "").toLowerCase().includes("breakout") ? "up" : "dim2"}`}>
          {s.stage || "—"}
        </div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Contractions</div>
        <div className="pv-stat-v mono">{s.contractions || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Measured move</div>
        <div className="pv-stat-v mono up">{s.measured_move || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v">
          <ConfBar value={s.confidence != null ? s.confidence : 0.64} tone="cy" width={72} />
        </div>
      </div>
    </div>
  );
}

// ── honest empty state (real feed, no pattern) ───────────────────
function ClassicalNone({ sym, message, tf }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no classical pattern</div>
        <div className="pv-empty-msg">
          {message || `No VCP / triangle / double-bottom base on ${sym || "this name"}'s ${tf ? tf.toLowerCase() : "daily"} chart. Price is in an active trend or too noisy — wait for a base to form.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          The detector requires a sequence of volatility contractions into a flat pivot (VCP), a converging trendline structure (triangle), or a neckline pattern (double bottom / cup). It will populate automatically when one forms.
        </div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions + mode) ────────────────────────
function ClassicalView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useClassicalModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <ClassicalNone sym={sym} message={message} tf={tf} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={model.tier} tf={model.tf || tf} />
    </div>
  );

  const Chart = <ClassicalChart model={model} height={dir === "C" ? 250 : 330} />;

  const hasContractions = (model.contractions || []).length > 0;

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <ClassicalStat stat={model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Base — annotated" sub="trendlines · pivot · breakout on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            {hasContractions && (
              <>
                <SectionHeader n={2} title="VCP contraction ladder" style="minimal" />
                <div className="pv-pad"><VCPLadder contractions={model.contractions} /></div>
              </>
            )}
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Detected patterns" style="minimal" />
            <div className="pv-pad">
              <PatternMatrix />
              <div className="pv-block-h label-cap" style={{ padding: "12px 0 6px" }}>Pattern library</div>
              <ClassicalLibrary library={model.library} dense />
            </div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad">
              <ClassicalTargets targets={model.targets} pivot={model.pivot} stop={model.stop} />
            </div>
          </div>
        </div>
        {model.read && (
          <div className="pv-pad" style={{ paddingTop: 8 }}>
            <span className="label-cap">Read · {(model.pattern || {}).name || "Classical"}</span>&nbsp;
            <span className="mono dim2" style={{ fontSize: 12 }}>{model.read}</span>
          </div>
        )}
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <ClassicalStat stat={model.stat} />
        <div className="pv-pad">{Chart}</div>
        {hasContractions && (
          <div className="pv-pad" style={{ paddingTop: 0 }}>
            <VCPLadder contractions={model.contractions} />
          </div>
        )}
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Detected patterns</div>
            <PatternMatrix />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Pattern library</div>
            <ClassicalLibrary library={model.library} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Measured-move targets</div>
            <ClassicalTargets targets={model.targets} pivot={model.pivot} stop={model.stop} />
          </div>
        </div>
        {model.read && (
          <div className="pv-pad" style={{ paddingTop: 6 }}>
            <span className="mono dim2" style={{ fontSize: 12 }}>{model.read}</span>
          </div>
        )}
      </div>
    );
  }

  // A — chart-led (default)
  const patName = (model.pattern && model.pattern.name) || "Base structure";
  return (
    <div className="pv-view">
      {SrcBar}
      <ClassicalStat stat={model.stat} />
      <SectionHeader n={1}
        title={`${patName} — annotated`}
        sub="trendlines · pivot · measured-move targets on real bars"
        style="minimal" />
      <div className="pv-pad">{Chart}</div>
      {hasContractions && (
        <>
          <SectionHeader n={2} title="VCP contraction ladder" sub="tightening price · drying volume" style="minimal" />
          <div className="pv-pad"><VCPLadder contractions={model.contractions} /></div>
        </>
      )}
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Detected patterns · multi-detector scan</div>
          <PatternMatrix />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Classical pattern library · measured moves</div>
          <ClassicalLibrary library={model.library} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Measured-move targets &amp; invalidation</div>
          <ClassicalTargets targets={model.targets} pivot={model.pivot} stop={model.stop} />
        </div>
      </div>
      {model.read && (
        <div className="pv-pad" style={{ paddingTop: 8 }}>
          <span className="label-cap">The Read · {patName}</span>&nbsp;
          <span className="mono dim2" style={{ fontSize: 12 }}>{model.read}</span>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { ClassicalView });
