// patterns-td.jsx — TD Sequential (DeMark) sub-tab.
//
// REAL DATA: setup counts (1–9), countdown (1–13), TDST support/resistance
// levels, perfection flag, and per-bar chart markers are computed server-side
// by engines/td.py over live EODHD bars via usePatternModel("td", …).
// SWING=daily / POSITION=weekly / INVESTMENT=monthly all supported.
//
// Mechanism: DeMark's TD Sequential counts exhaustion — a completed 9-setup /
// 13-countdown marks where a trend has run out of incremental buyers/sellers,
// flagging mean-reversion risk. The count is an ordinal clock, not a price
// pattern; it fires ONLY when the strict comparison-bar offset is met.
//
// Fallback: illustrative fixture renders when server is absent or no active
// TD count is found. The source badge says so honestly.

const { useMemo: useMemoTd } = React;

const TD_BARS = 50;

// ── illustrative fixture (fallback only) ────────────────────────────────────
const TD_FIX_ANCHORS = [
  { i: 0, price: 196 }, { i: 8, price: 184 }, { i: 16, price: 195 },
  { i: 24, price: 191 }, { i: 32, price: 202 }, { i: 40, price: 206 },
  { i: 46, price: 211 }, { i: 49, price: 213.4 },
];

const TD_FIX_HLINES = [
  { price: 209.5, label: "TDST resistance 209.5", tone: "rd", dash: "4 4" },
  { price: 196.0, label: "TDST support 196.0",    tone: "cy", dash: "4 4", labelBelow: true },
];

const TD_FIX_MARKERS = [
  { i: 8,  label: "B9✓",  tone: "gn",  place: "below" },
  { i: 32, label: "S1",   tone: "amb", place: "above" },
  { i: 36, label: "S5",   tone: "amb", place: "above" },
  { i: 40, label: "S9✓",  tone: "rd",  place: "above" },
  { i: 46, label: "SC7",  tone: "ink-2", place: "above" },
  { i: 49, label: "SC8",  tone: "rd",  place: "above" },
];

const TD_FIX_STAT = {
  setup:      "Sell Setup 9 of 9",
  countdown:  "Countdown 8 of 13",
  tdst:       "196.0 / 209.5",
  timing:     "exhaustion near",
  confidence: 0.57,
};

const TD_FIX_SETUP_TABLE = [
  { k: "Phase",      v: "Sell Setup",   tone: "amb" },
  { k: "Count",      v: "8 of 9",       tone: "amb" },
  { k: "Rule",       v: "close > close[−4]", tone: "ink-1" },
  { k: "Perfected?", v: "pending bar 9", tone: "ink-2" },
];

const TD_FIX_LADDER = [
  { stage: "Buy Setup 9",     state: "✓ complete (bar 9 at $184)", tone: "gn",   note: "triggered the rally off the low" },
  { stage: "Buy Countdown 13", state: "✓ played out into markup",  tone: "gn",   note: "prior bullish phase" },
  { stage: "Sell Setup",      state: "8 of 9 · in progress",       tone: "amb",  note: "momentum maturing near highs" },
  { stage: "Sell Countdown 13", state: "not started",              tone: "ink-3", note: "begins only after Sell Setup 9" },
];

const TD_FIX_READ = "Every other theory says GO; TD says momentum is maturing. A perfected Sell Setup 9 near $214–216 flags a 1–4 bar pause/pullback — trail stops, don't chase.";

function _buildFixtureBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x4e9;
  return buildSeries({ n: TD_BARS, anchors: TD_FIX_ANCHORS, seed, volSpikes: {} });
}

var TD_FIXTURE_MODEL = {
  bars:        null,   // populated dynamically from ticker seed in the hook
  tdst:        TD_FIX_HLINES,
  markers:     TD_FIX_MARKERS,
  stat:        TD_FIX_STAT,
  setup_table: TD_FIX_SETUP_TABLE,
  ladder:      TD_FIX_LADDER,
  read:        TD_FIX_READ,
  confidence:  0.57,
};

// ── data hook: real → fixture fallback (mode-aware) ──────────────────────────
function useTdModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("td", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const fixtureBars = useMemoTd(() => _buildFixtureBars(ticker), [sym]);

  // Usability test: real data, active state, bars present
  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length > 0
  );

  if (usable) {
    return {
      model: {
        bars:        real.bars,
        tdst:        real.tdst   || [],
        markers:     real.markers || [],
        stat:        real.stat   || TD_FIX_STAT,
        setup_table: real.setup_table || TD_FIX_SETUP_TABLE,
        ladder:      real.ladder  || TD_FIX_LADDER,
        read:        real.read    || "",
        confidence:  real.confidence != null ? real.confidence : 0,
        current:     real.current || {},
      },
      state: "real", sym, tf, usable: true,
      message: null,
    };
  }

  // Real responded but no active structure
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...TD_FIXTURE_MODEL, bars: fixtureBars },
      state: "none", sym, tf, usable: false,
      message: real.message || "No active TD Setup or Countdown found on this timeframe.",
    };
  }

  // Not yet loaded (or server absent) → illustrative fixture
  return {
    model: { ...TD_FIXTURE_MODEL, bars: fixtureBars },
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false, message: null,
  };
}

// ── chart: real bars + TDST hlines + per-bar count markers ────────────────────
function TdChart({ model, ticker, height }) {
  const bars    = (model && model.bars)    || [];
  const hlines  = (model && model.tdst)    || TD_FIX_HLINES;
  const markers = (model && model.markers) || TD_FIX_MARKERS;
  return (
    <CandleChart
      bars={bars}
      height={height || 320}
      hlines={hlines}
      markers={markers}
      accent="amb"
    />
  );
}

// ── stat strip ────────────────────────────────────────────────────────────────
function TdStat({ stat, usable }) {
  const s = stat || TD_FIX_STAT;
  const confVal = s.confidence != null ? s.confidence : 0;
  const timingTone = (s.timing === "exhaustion signal" || s.timing === "countdown complete") ? "rd"
                   : s.timing === "building" ? "amb" : "ink-2";
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">TD Setup</div>
        <div className="pv-stat-v mono warn">{s.setup || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Countdown</div>
        <div className="pv-stat-v mono dim2">{s.countdown || "not started"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">TDST</div>
        <div className="pv-stat-v mono">{s.tdst || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Timing</div>
        <div className={`pv-stat-v mono ${timingTone}`}>{s.timing || "no signal"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v"><ConfBar value={confVal} tone="amb" width={72} /></div>
      </div>
    </div>
  );
}

// ── setup-state table (Phase / Count / Rule / Perfected) ──────────────────────
function TdSetupTable({ rows, dense }) {
  const list = (rows && rows.length) ? rows : TD_FIX_SETUP_TABLE;
  return (
    <MiniTable
      dense={dense}
      cols={[{ h: "TD Setup", k: "k" }, { h: "", k: "v", align: "right" }]}
      rows={list.map(r => ({
        k: <span className="dim2">{r.k}</span>,
        v: <b style={{ color: `var(--${r.tone || "ink-1"})` }}>{r.v}</b>,
      }))}
    />
  );
}

// ── sequence ladder (timeline of completed / in-progress phases) ──────────────
function TdLadder({ ladder }) {
  const list = (ladder && ladder.length) ? ladder : TD_FIX_LADDER;
  return (
    <div className="pv-timeline">
      {list.map((e, k) => (
        <div key={k} className={`pv-tl-row ${e.tone === "amb" || e.tone === "cy" ? "is-current" : ""}`}>
          <div className="pv-tl-rail">
            <span className="pv-tl-dot" style={{ background: `var(--${e.tone || "ink-3"})` }} />
            {k < list.length - 1 && <span className="pv-tl-line" />}
          </div>
          <div className="pv-tl-body">
            <div className="pv-tl-head">
              <span className="pv-tl-code mono" style={{ color: `var(--${e.tone || "ink-3"})` }}>{e.stage}</span>
              <span className="pv-tl-meta mono dim">{e.state}</span>
            </div>
            <div className="pv-tl-note">{e.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── TDST levels table + timing note ──────────────────────────────────────────
function TdLevels({ model, usable }) {
  const tdst   = (model && model.tdst)   || [];
  const read   = (model && model.read)   || TD_FIX_READ;
  const stat   = (model && model.stat)   || TD_FIX_STAT;
  const cur    = (model && model.current) || {};

  // Build rows from tdst hlines
  const rows = tdst.map(h => {
    const isRes = (h.tone === "rd");
    return {
      l: isRes
        ? <b className="rd">TDST resistance</b>
        : <b className="cy">TDST support</b>,
      p: <b>${(h.price || 0).toFixed(2)}</b>,
      u: isRes
        ? <span className="dim2" style={{ fontSize: 11 }}>prior sell-setup high · breaks above = trend strong</span>
        : <span className="dim2" style={{ fontSize: 11 }}>buy-setup base · close below = momentum lost</span>,
    };
  });

  // Add bar-9 / bar-13 risk note if exhaustion near
  const timing = (stat && stat.timing) || "";
  const dirWord = (cur && cur.direction === "buy") ? "Buy" : "Sell";
  const closeVal = model && model.cur_close;

  return (
    <div className="pv-targets">
      {rows.length > 0
        ? <MiniTable
            cols={[
              { h: "Level", k: "l" },
              { h: "Price", k: "p", mono: true, align: "right" },
              { h: "Use", k: "u" },
            ]}
            rows={rows}
          />
        : <div className="pv-empty-sub mono dim2" style={{ padding: "8px 0" }}>No TDST levels yet — needs a completed 9-setup.</div>
      }
      <div className="pv-invalid" style={{ borderColor: "var(--amb-dim)", background: "var(--amb-bg)" }}>
        <span className="label-cap" style={{ color: "var(--amb)" }}>Timing note</span>
        <span className="mono">{read}</span>
      </div>
    </div>
  );
}

// ── honest empty state ───────────────────────────────────────────────────────
function TdNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no active TD count</div>
        <div className="pv-empty-msg">
          {message || `No active TD Setup or Countdown on ${sym || "this name"}'s chart. Price isn't sustaining 9 consecutive closes above/below the close 4 bars earlier.`}
        </div>
        <div className="pv-empty-sub mono dim2">
          TD Sequential requires 9 consecutive directional closes (close vs close[−4]). When a count starts it will populate automatically.
        </div>
      </div>
    </div>
  );
}

// ── main view (3 layout directions) ─────────────────────────────────────────
function TDSequentialView({ ticker, dir, mode }) {
  const { model, state, usable, sym, tf, message } = useTdModel(ticker, mode);

  // Source badge (using shared PatternSrcBadge)
  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tf={tf} />
    </div>
  );

  // Honest empty state when real data returned no count
  if (state === "none") {
    return (
      <div className="pv-view">
        {SrcBar}
        <TdNone sym={sym} message={message} />
      </div>
    );
  }

  const chartH = dir === "C" ? 250 : 330;
  const Chart  = <TdChart model={model} ticker={ticker} height={chartH} />;
  const Stat   = <TdStat  stat={model.stat} usable={usable} />;

  if (dir === "B") {
    // SPLIT — chart left, analysis right
    return (
      <div className="pv-view">
        {SrcBar}
        {Stat}
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="TD Setup / Countdown — annotated" sub="exhaustion counts + TDST levels on real bars" style="minimal" />
            <div className="pv-pad">{Chart}</div>
            <SectionHeader n={2} title="Sequence ladder" style="minimal" />
            <div className="pv-pad"><TdLadder ladder={model.ladder} /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Setup state" style="minimal" />
            <div className="pv-pad"><TdSetupTable rows={model.setup_table} /></div>
            <SectionHeader n={4} title="TDST levels &amp; timing" style="minimal" />
            <div className="pv-pad"><TdLevels model={model} usable={usable} /></div>
          </div>
        </div>
      </div>
    );
  }

  if (dir === "C") {
    // DOSSIER — compact chart, data-dense tables stacked
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        {Stat}
        <div className="pv-pad">{Chart}</div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Sequence ladder</div>
            <TdLadder ladder={model.ladder} />
            <div className="pv-block-h label-cap" style={{ marginTop: 14 }}>Setup state</div>
            <TdSetupTable rows={model.setup_table} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">TDST levels &amp; timing</div>
            <TdLevels model={model} usable={usable} />
          </div>
        </div>
      </div>
    );
  }

  // A — CHART-LED (default)
  return (
    <div className="pv-view">
      {SrcBar}
      {Stat}
      <SectionHeader n={1} title="TD Sequential — Setup &amp; Countdown" sub="DeMark exhaustion timing · TDST levels on real bars" style="minimal" />
      <div className="pv-pad">{Chart}</div>
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Sequence ladder</div>
          <TdLadder ladder={model.ladder} />
          <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>Setup state</div>
          <TdSetupTable rows={model.setup_table} />
        </div>
        <div>
          <div className="pv-block-h label-cap">TDST levels &amp; timing</div>
          <TdLevels model={model} usable={usable} />
        </div>
      </div>
    </div>
  );
}

// ── dynamic "The Read · TD Sequential" line (lens-call) ──────────────────────
function TDReadLine({ ticker, mode }) {
  const { model, state, usable } = useTdModel(ticker, mode);

  if (!usable || state !== "real") {
    // Illustrative fallback copy (original fixture voice)
    return (
      <span className="mono">
        Every other theory says GO; TD says momentum is <b className="warn">maturing</b>. A perfected Sell Setup 9 near <b className="warn">$214–216</b> flags a 1–4 bar pause/pullback — trail stops, don&apos;t chase.
      </span>
    );
  }

  const read = (model && model.read) || "";
  const cur  = (model && model.current) || {};
  const stat = (model && model.stat) || {};
  const dir  = cur.direction === "buy" ? "up" : "dn";
  const tone = cur.direction === "buy" ? "cy" : "amb";

  return (
    <span className="mono">
      {stat.timing && stat.timing !== "no signal"
        ? <><b className={tone}>{stat.timing}</b> — </>
        : null}
      {read}
    </span>
  );
}

Object.assign(window, { TDSequentialView, TDReadLine });
