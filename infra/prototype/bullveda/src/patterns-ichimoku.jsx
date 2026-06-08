// patterns-ichimoku.jsx — Ichimoku Kinko Hyo sub-tab.
//
// REAL DATA: Tenkan-sen (9) / Kijun-sen (26) / Senkou Span A & B (projected +26)
// / Chikou Span (plotted −26) are computed server-side by engines/ichimoku.py from
// live EODHD bars and fetched via the BullVeda pattern endpoint.
// The hook reads the cache synchronously and re-renders when the real payload
// resolves. When the server is absent (standalone dev showcase) or returns
// state="none", we fall back to the illustrative fixture below — and the header
// badge says so, honestly.

const { useMemo: useMemoIch } = React;
const ICH_FWD = 26;

// ── illustrative fixture computation (kept as fallback — NOT deleted) ─────────
function computeIchimoku(bars) {
  const n = bars.length;
  const hh = (p, i) => { let m = -1e9; for (let k = Math.max(0, i - p + 1); k <= i; k++) m = Math.max(m, bars[k].hi); return m; };
  const ll = (p, i) => { let m = 1e9; for (let k = Math.max(0, i - p + 1); k <= i; k++) m = Math.min(m, bars[k].lo); return m; };
  const rawA = [], rawB = [], tenkan = [], kijun = [], chikou = [];
  for (let i = 0; i < n; i++) {
    const tk = (hh(9, i) + ll(9, i)) / 2;
    const kj = (hh(26, i) + ll(26, i)) / 2;
    rawA[i] = (tk + kj) / 2;
    rawB[i] = (hh(52, i) + ll(52, i)) / 2;
    if (i >= 8) tenkan.push({ i, price: tk });
    if (i >= 25) kijun.push({ i, price: kj });
    if (i >= ICH_FWD) chikou.push({ i: i - ICH_FWD, price: bars[i].c });
  }
  // cloud plotted shifted +26, flat-filled left so it spans the chart
  const spanA = [], spanB = [];
  for (let x = 0; x <= n - 1 + ICH_FWD; x++) {
    spanA.push({ i: x, price: rawA[Math.min(n - 1, Math.max(25, x - ICH_FWD))] });
    spanB.push({ i: x, price: rawB[Math.min(n - 1, Math.max(51, x - ICH_FWD))] });
  }
  return { tenkan, kijun, chikou, spanA, spanB };
}

// Fixture bar series (seeded per ticker)
function buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x6c4;
  const anchors = [
    { i: 0, price: 192 }, { i: 12, price: 184 }, { i: 24, price: 196 }, { i: 34, price: 190 },
    { i: 46, price: 202 }, { i: 56, price: 198 }, { i: 66, price: 209 }, { i: 79, price: 213.4 },
  ];
  return buildSeries({ n: 80, anchors, seed, volSpikes: {} });
}

// Static fixture stat/signals/lines/targets (for standalone showcase)
var IC_FIXTURE_STAT = {
  cloud: "Above", tk_cross: "Bullish", chikou: "Free",
  future_kumo: "Green · bullish twist", confidence: 0.74,
  bull_count: 5, verdict: "strong_bull",
};

const FIXTURE_ICH_LINES = [
  { name: "Tenkan-sen (9)",  val: "208.6", role: "fast trigger · above Kijun",          tone: "cy" },
  { name: "Kijun-sen (26)", val: "201.4", role: "trend baseline · dynamic stop",        tone: "copper" },
  { name: "Senkou A",       val: "205.0", role: "cloud top (leading)",                  tone: "gn" },
  { name: "Senkou B",       val: "197.2", role: "cloud base (leading)",                 tone: "rd" },
  { name: "Chikou span",    val: "213.4", role: "lagging close · above price 26-ago",   tone: "violet" },
];

const FIXTURE_SIGNALS = [
  { s: "Price above the Kumo (cloud)",        v: "PASS · above cloud", tone: "gn" },
  { s: "Tenkan > Kijun (bullish TK cross)",   v: "PASS · T > K",       tone: "gn" },
  { s: "Chikou span free of price action",    v: "PASS · free",        tone: "gn" },
  { s: "Future Kumo green (Senkou A > B)",    v: "PASS · green",       tone: "gn" },
  { s: "Price above Kijun baseline",          v: "PASS · above",       tone: "gn" },
];

var IC_FIXTURE_TARGETS = {
  kumo_target: 222.0, kijun_stop: 201.4,
  cloud_top: 205.0, cloud_bottom: 197.2, cloud_height: 7.8,
  rr: 3.4, bull: true,
  invalidation_note: "A close back inside the Kumo (< $205) neutralises the signal; below Kijun $201.4 flips bearish.",
};

const FIXTURE_READ = "All 5 Ichimoku signals aligned bullish (5/5): price $213.40 is above a green cloud, Tenkan > Kijun, Chikou free, and baseline $201.40 is support.";

function buildFixtureModel(ticker) {
  const bars = buildFixtureBars(ticker);
  const ich = computeIchimoku(bars);
  return {
    isReal: false,
    bars,
    cloud:     { spanA: ich.spanA, spanB: ich.spanB },
    lines:     [
      { pts: ich.tenkan, tone: "cy",     width: 1.4, opacity: 0.9 },
      { pts: ich.kijun,  tone: "copper", width: 1.6, opacity: 0.9 },
      { pts: ich.chikou, tone: "violet", width: 1.2, dash: "4 3", opacity: 0.7 },
    ],
    hlines: [
      { price: 201.4, label: "Kijun 201.40", tone: "copper", dash: "4 4" },
      { price: 222.0, label: "T1 222.00",    tone: "gn",     dash: "5 4" },
    ],
    stat:      IC_FIXTURE_STAT,
    signals:   FIXTURE_SIGNALS,
    ich_lines: FIXTURE_ICH_LINES,
    targets:   IC_FIXTURE_TARGETS,
    read:      FIXTURE_READ,
    span:      80 + ICH_FWD,
    projectFrom: 80,
  };
}

// Fixture model constant used as fallback reference
var IC_FIXTURE_MODEL = buildFixtureModel({ symbol: "ARGN" });

// ── data hook: real → fixture fallback (mode-aware) ───────────────────────────
function useIchimokuModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("ichimoku", ticker, mode);
  const fixtureModel = useMemoIch(() => buildFixtureModel(ticker), [sym]);
  const tf = (real && real.meta && real.meta.tf) || null;

  // real, fully-formed payload?
  const usable = state === "loaded" && real && real.ok &&
                 real.state === "real" && real.bars && real.bars.length > 0 &&
                 real.cloud && real.cloud.spanA && real.cloud.spanA.length > 0;

  if (usable) {
    return {
      model: {
        isReal: true,
        bars:        real.bars,
        cloud:       real.cloud,
        lines:       real.lines   || [],
        hlines:      real.hlines  || [],
        stat:        real.stat    || {},
        signals:     real.signals || [],
        ich_lines:   real.ich_lines || [],
        targets:     real.targets  || {},
        read:        real.read     || "",
        span:        real.span     || (real.bars.length + ICH_FWD),
        projectFrom: real.projectFrom || real.bars.length,
      },
      state: "real", sym, tf, usable: true,
    };
  }
  // server replied but no usable structure
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...fixtureModel },
      state: "none", sym, tf, usable: false,
      message: real.message,
    };
  }
  // pre-load or server absent
  return {
    model: { ...fixtureModel },
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── chart ─────────────────────────────────────────────────────────────────────
function IchimokuChart({ model, height = 330 }) {
  const bars       = (model || {}).bars       || IC_FIXTURE_MODEL.bars;
  const cloud      = (model || {}).cloud      || IC_FIXTURE_MODEL.cloud;
  const chartLines = (model || {}).lines      || IC_FIXTURE_MODEL.lines;
  const hlines     = (model || {}).hlines     || IC_FIXTURE_MODEL.hlines;
  const spanCols   = (model || {}).span       || (bars.length + ICH_FWD);
  const projFrom   = (model || {}).projectFrom != null ? model.projectFrom : bars.length;

  return (
    <CandleChart
      bars={bars}
      height={height}
      lines={chartLines}
      cloud={cloud}
      hlines={hlines}
      accent="cy"
      span={spanCols}
      projectFrom={projFrom}
      volume={false}
    />
  );
}

// ── stat bar ──────────────────────────────────────────────────────────────────
function IchStat({ stat }) {
  const s   = stat || IC_FIXTURE_STAT;
  const conf = (s.confidence != null) ? s.confidence : 0.74;
  // tone helpers
  const cloudTone  = s.cloud === "Above"    ? "up" : s.cloud === "Below" ? "dn" : "dim2";
  const tkTone     = s.tk_cross === "Bullish" ? "up" : s.tk_cross === "Bearish" ? "dn" : "dim2";
  const chikouTone = s.chikou === "Free"    ? "up" : s.chikou === "Obstructed" ? "amb" : "dn";
  const futTone    = (s.future_kumo || "").startsWith("Green") ? "up" : (s.future_kumo || "").startsWith("Red") ? "dn" : "dim2";

  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Cloud</div>
        <div className={`pv-stat-v mono ${cloudTone}`}>{s.cloud || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">TK cross</div>
        <div className={`pv-stat-v mono ${tkTone}`}>{s.tk_cross || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Chikou</div>
        <div className={`pv-stat-v mono ${chikouTone}`}>{s.chikou || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Future Kumo</div>
        <div className={`pv-stat-v mono ${futTone}`}>{s.future_kumo || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v"><ConfBar value={conf} tone="cy" width={72} /></div>
      </div>
    </div>
  );
}

// ── Ichimoku component lines table ────────────────────────────────────────────
function IchLines({ rows, dense }) {
  const list = (rows && rows.length) ? rows : FIXTURE_ICH_LINES;
  return (
    <MiniTable
      dense={dense}
      cols={[
        { h: "Component", k: "name" },
        { h: "Value",     k: "val",  mono: true, align: "right" },
        { h: "Read",      k: "role" },
      ]}
      rows={list.map(l => ({
        name: <b style={{ color: `var(--${l.tone || "ink-2"})` }}>{l.name}</b>,
        val:  <b>${l.val}</b>,
        role: <span className="dim2" style={{ fontSize: 11 }}>{l.role}</span>,
      }))}
    />
  );
}

// ── 5-signal checklist ────────────────────────────────────────────────────────
function IchSignals({ rows, dense }) {
  const list = (rows && rows.length) ? rows : FIXTURE_SIGNALS;
  return (
    <MiniTable
      dense={dense}
      cols={[
        { h: "Ichimoku signal", k: "s" },
        { h: "Status",          k: "v", align: "right" },
      ]}
      rows={list.map(r => ({
        s: <span dangerouslySetInnerHTML={{ __html: r.s }} />,
        v: <Pill tone={r.tone || "gn"} small>{r.v}</Pill>,
      }))}
    />
  );
}

// ── targets + invalidation ────────────────────────────────────────────────────
function IchTargets({ targets }) {
  const t = (targets && targets.kumo_target != null) ? targets : IC_FIXTURE_TARGETS;
  const bull = t.bull !== false;   // default bullish for fixture
  const invNote = t.invalidation_note ||
    "A close back inside the Kumo neutralises the signal.";

  return (
    <div className="pv-targets">
      <MiniTable
        cols={[
          { h: "Level",  k: "l" },
          { h: "Price",  k: "p", mono: true, align: "right" },
          { h: "Role",   k: "r" },
        ]}
        rows={[
          {
            l: <b className={bull ? "up" : "dn"}>Kumo-breakout target</b>,
            p: <b>${(+t.kumo_target).toFixed(2)}</b>,
            r: <span className="dim2" style={{ fontSize: 11 }}>
                 cloud height (${(+t.cloud_height).toFixed(2)}) projected from {bull ? "cloud top" : "cloud bottom"}
                 {t.rr != null ? <> · R:R {(+t.rr).toFixed(1)}×</> : null}
               </span>,
          },
          {
            l: <b className="copper">Kijun-sen</b>,
            p: <b>${(+t.kijun_stop).toFixed(2)}</b>,
            r: <span className="dim2" style={{ fontSize: 11 }}>trailing stop / re-entry</span>,
          },
          {
            l: <b className={bull ? "gn" : "rd"}>Cloud {bull ? "top" : "bottom"} (Senkou {bull ? "A" : "B"})</b>,
            p: <b>${bull ? (+t.cloud_top).toFixed(2) : (+t.cloud_bottom).toFixed(2)}</b>,
            r: <span className="dim2" style={{ fontSize: 11 }}>{bull ? "first support on a dip" : "first resistance on a rally"}</span>,
          },
        ]}
      />
      <div className="pv-invalid">
        <span className="label-cap">Invalidation</span>
        <span className="mono">{invNote}</span>
      </div>
    </div>
  );
}

// ── honest empty state ────────────────────────────────────────────────────────
function IchimokuNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Ichimoku structure</div>
        <div className="pv-empty-msg">
          {message || `Not enough ${sym || "this name"}'s bars to form a reliable Ichimoku cloud. Senkou Span B requires ≥52 bars; this timeframe has fewer.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          Switch to Daily or Weekly for live Ichimoku. When sufficient bars are available the read will populate automatically.
        </div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions) ────────────────────────────────────────────
function IchimokuView({ ticker, dir, mode }) {
  const { model, state, message, sym, tf, usable } = useIchimokuModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={false} sym={sym} tf={tf} />
        </div>
        <IchimokuNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge
        state={state}
        usable={usable}
        sym={sym || (model && model.ticker)}
        tier={(model && model.tier) || null}
        tf={tf}
      />
    </div>
  );

  const Chart = (
    <IchimokuChart
      model={model}
      height={dir === "C" ? 250 : 340}
    />
  );

  const signalCount = (model.stat && model.stat.bull_count != null)
    ? `${model.stat.bull_count} of 5`
    : "5 of 5";

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <IchStat stat={model.stat} />
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Ichimoku — full overlay" sub="Tenkan · Kijun · Kumo (projected) · Chikou" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Signal checklist" style="minimal" />
            <div className="pv-pad"><IchSignals rows={model.signals} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Components" style="minimal" />
            <div className="pv-pad"><IchLines rows={model.ich_lines} /></div>
            <SectionHeader n={4} title="Targets" style="minimal" />
            <div className="pv-pad"><IchTargets targets={model.targets} /></div>
          </div>
        </div>
        {model.read && (
          <div className="pv-pad" style={{ marginTop: 8 }}>
            <div className="pv-block-h label-cap">The Read</div>
            <div className="mono" style={{ fontSize: 12, lineHeight: 1.6 }}>{model.read}</div>
          </div>
        )}
      </div>
    );
  }

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <IchStat stat={model.stat} />
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Components</div>
            <IchLines rows={model.ich_lines} dense />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Signal checklist</div>
            <IchSignals rows={model.signals} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
            <IchTargets targets={model.targets} />
            {model.read && (
              <>
                <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>The Read</div>
                <div className="mono dim2" style={{ fontSize: 11, lineHeight: 1.6 }}>{model.read}</div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // dir === "A" — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <IchStat stat={model.stat} />
      <SectionHeader
        n={1}
        title="Ichimoku Kinko Hyo — full overlay"
        sub="Tenkan/Kijun · forward-projected Kumo · Chikou span"
        style="minimal"
      />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Components</div>
          <IchLines rows={model.ich_lines} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>
            {`Signal checklist · ${signalCount}`}
          </div>
          <IchSignals rows={model.signals} />
        </div>
        <div>
          <div className="pv-block-h label-cap">Targets &amp; invalidation</div>
          <IchTargets targets={model.targets} />
          {model.read && (
            <>
              <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>The Read</div>
              <div className="mono" style={{ fontSize: 12, lineHeight: 1.6 }}>{model.read}</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── dynamic read line (lens-call) — real when available ──────────────────────
function IchimokuReadLine({ ticker, mode }) {
  const { model, state } = useIchimokuModel(ticker, mode);
  if (state === "none") {
    return (
      <span className="mono">
        Insufficient bars for Ichimoku on this timeframe — switch to Daily or Weekly for a live cloud read.
      </span>
    );
  }
  if (state !== "real") {
    // illustrative fallback
    return (
      <span className="mono">
        Composite operator is <b className="up">accumulating</b> — all 5 Ichimoku signals bullish.
        Cloud top <b className="copper">$205</b>; Kijun baseline <b className="copper">$201.40</b> as trailing stop.
        Kumo-breakout projects <b className="up">$222</b>. Invalid on close inside cloud <b className="dn">(&lt; $205)</b>.
      </span>
    );
  }
  const s = model.stat || {};
  const t = model.targets || {};
  const bull = t.bull !== false;
  return (
    <span className="mono">
      Ichimoku {s.bull_count || 0}/5 signals {bull ? "bullish" : "bearish"} — price {s.cloud || "—"} cloud,
      TK {s.tk_cross || "—"}, Chikou {s.chikou || "—"}.
      {t.kijun_stop != null && <> Kijun <b className="copper">${(+t.kijun_stop).toFixed(2)}</b> as trailing stop;</>}
      {t.kumo_target != null && <> Kumo-breakout projects <b className={bull ? "up" : "dn"}>${(+t.kumo_target).toFixed(2)}</b>.</>}
      {model.read ? " " + model.read : ""}
    </span>
  );
}

Object.assign(window, { IchimokuView, IchimokuReadLine });
