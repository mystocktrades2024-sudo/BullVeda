// patterns-candlesticks.jsx — Japanese candlestick patterns theory sub-tab.
//
// REAL DATA: patterns are detected server-side by engines/candles.py over live
// EODHD bars and fetched via the shared usePatternModel("candles", ...) hook.
// When the server is absent (standalone showcase) or returns no usable patterns,
// we fall back to the illustrative fixture below — and the badge says so.
//
// Mechanism: a candlestick reversal pattern AT a meaningful level (EMA-20,
// support) WITH volume confirmation (rvol > 1.1) signals a real intraday shift
// in supply/demand control. The glyph alone is noise — location + volume = signal.

const { useMemo: useMemoCs } = React;

// ── tiny candlestick glyph (1–3 candles) ────────────────────────────
function CandleGlyph({ candles, w = 44, h = 30 }) {
  if (!candles || !candles.length) return null;
  const vals = candles.flatMap(c => [c.h, c.l]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const y = v => 4 + (h - 8) * (1 - (v - mn) / ((mx - mn) || 1));
  const slot = (w - 8) / candles.length;
  const cw = Math.min(8, slot - 2);
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {candles.map((c, i) => {
        const x = 4 + i * slot + slot / 2;
        const up = c.c >= c.o;
        const col = up ? "var(--gn)" : "var(--rd)";
        return (
          <g key={i}>
            <line x1={x} y1={y(c.h)} x2={x} y2={y(c.l)} stroke={col} strokeWidth="1" />
            <rect x={x - cw / 2} y={y(Math.max(c.o, c.c))} width={cw}
                  height={Math.max(1.2, Math.abs(y(c.o) - y(c.c)))}
                  fill={up ? "var(--bg-1)" : col} stroke={col} strokeWidth="1" />
          </g>
        );
      })}
    </svg>
  );
}

// canonical candle shapes per pattern (used by fixture AND real detected[])
const CS_GLYPH = {
  "Bullish Engulfing":  [{ o: 8, c: 6, h: 8.3, l: 5.7 }, { o: 5.6, c: 9, h: 9.4, l: 5.2 }],
  "Bearish Engulfing":  [{ o: 4, c: 7, h: 7.5, l: 3.7 }, { o: 7.4, c: 3.2, h: 7.8, l: 2.8 }],
  "Hammer":             [{ o: 7.2, c: 7.8, h: 8.2, l: 3.0 }],
  "Shooting Star":      [{ o: 4.6, c: 4.1, h: 9.2, l: 3.8 }],
  "Morning Star":       [{ o: 9, c: 6.4, h: 9.3, l: 6.0 }, { o: 5.6, c: 5.8, h: 6.0, l: 5.2 }, { o: 6.2, c: 9.2, h: 9.5, l: 6.0 }],
  "Evening Star":       [{ o: 3, c: 6.8, h: 7.0, l: 2.7 }, { o: 7.1, c: 6.9, h: 7.5, l: 6.7 }, { o: 6.5, c: 3.2, h: 6.7, l: 2.9 }],
  "Piercing Pattern":   [{ o: 8, c: 5.0, h: 8.3, l: 4.7 }, { o: 4.6, c: 6.7, h: 7.0, l: 4.4 }],
  "Dark Cloud Cover":   [{ o: 4, c: 7.5, h: 7.8, l: 3.7 }, { o: 8.0, c: 5.3, h: 8.3, l: 5.0 }],
  "Bullish Harami":     [{ o: 9, c: 5.2, h: 9.3, l: 5.0 }, { o: 6.3, c: 7.2, h: 7.5, l: 6.0 }],
  "Bearish Harami":     [{ o: 3, c: 7.5, h: 7.8, l: 2.7 }, { o: 6.4, c: 5.5, h: 6.8, l: 5.2 }],
  "Doji":               [{ o: 6.0, c: 6.1, h: 9.0, l: 3.0 }],
  "Bullish Marubozu":   [{ o: 4.0, c: 9.0, h: 9.0, l: 4.0 }],
  "Bearish Marubozu":   [{ o: 9.0, c: 4.0, h: 9.0, l: 4.0 }],
  // legacy glyph keys (fixture fallback compatibility)
  engulf:    [{ o: 8, c: 6, h: 8.6, l: 5.4 }, { o: 5.6, c: 9, h: 9.6, l: 5 }],
  hammer:    [{ o: 7.4, c: 8, h: 8.4, l: 3 }],
  morning:   [{ o: 9, c: 6.4, h: 9.4, l: 6 }, { o: 5.6, c: 5.8, h: 6, l: 5.2 }, { o: 6.2, c: 9, h: 9.4, l: 6 }],
  soldiers:  [{ o: 4, c: 5.6, h: 5.9, l: 3.8 }, { o: 5.4, c: 7.2, h: 7.5, l: 5.2 }, { o: 7, c: 8.8, h: 9.1, l: 6.8 }],
  harami:    [{ o: 9, c: 5.2, h: 9.3, l: 5 }, { o: 6.2, c: 7.2, h: 7.5, l: 6 }],
  tweezer:   [{ o: 7, c: 4.2, h: 7.4, l: 3.6 }, { o: 4.6, c: 7.4, h: 7.8, l: 3.6 }],
  doji:      [{ o: 6, c: 6.15, h: 9, l: 3 }],
  shooting:  [{ o: 4.4, c: 4, h: 9, l: 3.8 }],
};

// helper: get a glyph from either the real detected entry or the key map
function _resolveGlyph(item) {
  if (item && item.glyph && Array.isArray(item.glyph)) return item.glyph;
  if (item && item.glyph && CS_GLYPH[item.glyph]) return CS_GLYPH[item.glyph];
  if (item && item.name && CS_GLYPH[item.name]) return CS_GLYPH[item.name];
  return CS_GLYPH["Doji"];
}

// ── fixture constants (illustrative fallback) ────────────────────────
const CS_FIXTURE_SIGNALS = [
  { name: "Bullish Engulfing", glyph: "engulf", kind: "Reversal ↑", date: "May 28", loc: "at $176 support", vol: "1.8× ✓", reliability: 0.63, status: "CONFIRMED", status_tone: "gn", tone: "gn" },
  { name: "Hammer",            glyph: "hammer", kind: "Reversal ↑", date: "May 22", loc: "spring low retest", vol: "1.4× ✓", reliability: 0.59, status: "CONFIRMED", status_tone: "gn", tone: "gn" },
  { name: "Three White Soldiers", glyph: "soldiers", kind: "Continuation ↑", date: "May 15", loc: "off the base", vol: "1.3× ✓", reliability: 0.61, status: "CONFIRMED", status_tone: "gn", tone: "gn" },
  { name: "Bullish Harami",    glyph: "harami", kind: "Reversal ↑", date: "May 09", loc: "mid-range", vol: "0.7× ✗", reliability: 0.53, status: "WEAK", status_tone: "ink-2", tone: "amb" },
  { name: "Doji",              glyph: "doji",   kind: "Indecision", date: "May 06", loc: "at resistance", vol: "0.9×",  reliability: 0.50, status: "NEUTRAL", status_tone: "ink-2", tone: "ink-2" },
];

const CS_FIXTURE_REL = [
  { name: "Three White Soldiers", glyph: "soldiers", reliability: 0.61, n: 142, ff: "+2.1%", note: "strong with volume" },
  { name: "Bullish Engulfing",    glyph: "engulf",   reliability: 0.63, n: 318, ff: "+1.8%", note: "best at support" },
  { name: "Morning Star",         glyph: "morning",  reliability: 0.65, n: 96,  ff: "+2.4%", note: "highest reliability" },
  { name: "Hammer",               glyph: "hammer",   reliability: 0.59, n: 261, ff: "+1.3%", note: "needs confirmation bar" },
  { name: "Tweezer Bottom",       glyph: "tweezer",  reliability: 0.55, n: 88,  ff: "+1.0%", note: "weak alone" },
  { name: "Doji",                 glyph: "doji",     reliability: 0.50, n: 540, ff: "±0.4%", note: "context-only · no edge alone" },
];

const CS_FIXTURE_STAT = {
  active_signal: "Bull Engulfing",
  location: "at $176 support",
  confirmation: "vol 1.8× ✓",
  reliability: "63% · n=318",
  tone: "gn",
};

const CS_FIXTURE_READ = "Candlesticks are a confirmation layer, not a signal alone — a bullish engulfing at the $176 support shelf on 1.8× volume is high-quality; the same candle mid-range is noise. Always pair the glyph with location + volume, and weight by the pattern's historical win-rate.";

const CS_FIXTURE_CONFIDENCE = 0.63;

// a universal reliability reference (shown in all states)
const CS_REL_STATIC = [
  { name: "Morning Star",         glyph: "morning",  reliability: 0.65, n: 96,  ff: "+2.4%", note: "highest reliability (3-bar)" },
  { name: "Bullish Engulfing",    glyph: "engulf",   reliability: 0.63, n: 318, ff: "+1.8%", note: "best at support · needs vol" },
  { name: "Bearish Engulfing",    glyph: "engulf",   reliability: 0.60, n: 274, ff: "-1.7%", note: "best at resistance" },
  { name: "Three White Soldiers", glyph: "soldiers", reliability: 0.61, n: 142, ff: "+2.1%", note: "strong with volume" },
  { name: "Evening Star",         glyph: "morning",  reliability: 0.63, n: 84,  ff: "-2.1%", note: "3-bar · needs follow-through" },
  { name: "Hammer",               glyph: "hammer",   reliability: 0.59, n: 261, ff: "+1.3%", note: "needs confirmation bar" },
  { name: "Doji",                 glyph: "doji",     reliability: 0.50, n: 540, ff: "±0.4%", note: "context-only · no edge alone" },
];

var CS_FIXTURE_MODEL = {
  isReal: false,
  source: "illustrative",
  bars: [],             // populated by buildMockBars
  detected: CS_FIXTURE_SIGNALS,
  stat: CS_FIXTURE_STAT,
  read: CS_FIXTURE_READ,
  confidence: CS_FIXTURE_CONFIDENCE,
  hlines: [],
  markers: [],
};

// ── mock bar generator ───────────────────────────────────────────────
function buildMockBars(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0xca4d;
  const anchors = [
    { i: 0, price: 190 }, { i: 12, price: 176 }, { i: 20, price: 181 },
    { i: 35, price: 178 }, { i: 48, price: 189 }, { i: 60, price: 195 },
    { i: 75, price: 192 }, { i: 79, price: 194 },
  ];
  const volSpikes = { 12: 1.8, 35: 1.4, 48: 1.3, 60: 0.7 };
  return buildSeries({ n: 80, anchors, seed, volSpikes });
}

// ── data hook ────────────────────────────────────────────────────────
function useCandlesModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("candles", ticker, mode);
  const mockBars = useMemoCs(() => buildMockBars(ticker), [sym]);
  const tf = (real && real.meta && real.meta.tf) || null;

  // real, fully-formed payload?
  const usable = state === "loaded" && real && real.ok &&
                 real.state === "real" && real.bars && real.bars.length > 0;

  if (usable) {
    return {
      model: {
        isReal: true, source: "real", tf, ticker: real.ticker,
        bars: real.bars,
        detected: real.detected || [],
        stat: real.stat || {},
        read: real.read || "",
        confidence: real.confidence || 0,
        hlines: real.hlines || [],
        markers: real.markers || [],
      },
      state: "real", sym, tf, usable: true,
    };
  }
  // real responded but no patterns
  if (state === "loaded" && real && real.ok) {
    return {
      model: { ...CS_FIXTURE_MODEL, bars: mockBars, tf },
      state: "none", sym, tf, usable: false,
      message: real.message || "No notable patterns in recent bars.",
    };
  }
  // loading or server absent
  return {
    model: { ...CS_FIXTURE_MODEL, bars: mockBars },
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── sub-components (all take data as props) ──────────────────────────

function CsStat({ stat, confidence, usable }) {
  const s = stat || CS_FIXTURE_STAT;
  const conf = confidence != null ? confidence : CS_FIXTURE_CONFIDENCE;
  const tone = s.tone || "gn";
  const textColor = tone === "ink-2" ? "var(--ink-2)" : `var(--${tone})`;
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Active signal</div>
        <div className="pv-stat-v mono" style={{ color: textColor }}>{s.active_signal || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Location</div>
        <div className="pv-stat-v mono">{s.location || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confirmation</div>
        <div className="pv-stat-v mono up">{s.confirmation || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Reliability</div>
        <div className="pv-stat-v mono">{s.reliability || "—"}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Confidence</div>
        <div className="pv-stat-v"><ConfBar value={conf} tone={tone === "ink-2" ? "ink-3" : tone} width={72} /></div>
      </div>
    </div>
  );
}

function CsSignals({ detected, dense }) {
  const list = (detected && detected.length) ? detected : CS_FIXTURE_SIGNALS;
  return (
    <table className={`pv-table ${dense ? "is-dense" : ""}`}>
      <thead>
        <tr>
          <th className="label-cap"></th>
          <th className="label-cap">Pattern</th>
          <th className="label-cap">Type</th>
          <th className="label-cap">Location</th>
          <th className="label-cap">Vol</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Reliability</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {list.map((s, i) => {
          const tone = s.tone || "ink-2";
          const textColor = tone === "ink-2" ? "var(--ink-2)" : `var(--${tone})`;
          const sTone = s.status_tone || "ink-2";
          return (
            <tr key={i}>
              <td style={{ width: 48 }}>
                <CandleGlyph candles={_resolveGlyph(s)} />
              </td>
              <td>
                <b>{s.name}</b>
                <br />
                <span className="dim2 mono" style={{ fontSize: 10 }}>{s.date}</span>
              </td>
              <td className="mono" style={{ color: textColor, fontSize: 11 }}>{s.kind}</td>
              <td className="dim2" style={{ fontSize: 11 }}>{s.loc}</td>
              <td className="mono" style={{ fontSize: 11 }}>{s.vol}</td>
              <td style={{ textAlign: "right" }}>
                <ConfBar value={s.reliability || 0.5} tone={tone === "ink-2" ? "ink-3" : tone} width={44} />
              </td>
              <td style={{ textAlign: "right" }}>
                <Pill tone={sTone} small>{s.status}</Pill>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function CsReliability({ dense }) {
  return (
    <table className={`pv-table ${dense ? "is-dense" : ""}`}>
      <thead>
        <tr>
          <th className="label-cap"></th>
          <th className="label-cap">Pattern</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Win rate</th>
          <th className="label-cap" style={{ textAlign: "right" }}>n</th>
          <th className="label-cap" style={{ textAlign: "right" }}>Avg 5d</th>
          <th className="label-cap">Note</th>
        </tr>
      </thead>
      <tbody>
        {CS_REL_STATIC.map((r, i) => (
          <tr key={i}>
            <td style={{ width: 48 }}><CandleGlyph candles={CS_GLYPH[r.glyph] || CS_GLYPH.doji} /></td>
            <td><b>{r.name}</b></td>
            <td style={{ textAlign: "right" }}>
              <span className="mono" style={{
                color: `var(--${r.reliability >= 0.6 ? "gn" : r.reliability >= 0.55 ? "amb" : "ink-2"})`,
                fontWeight: 700
              }}>{(r.reliability * 100).toFixed(0)}%</span>
            </td>
            <td className="mono dim2" style={{ textAlign: "right" }}>{r.n}</td>
            <td className="mono up" style={{ textAlign: "right" }}>{r.ff}</td>
            <td className="dim2" style={{ fontSize: 11 }}>{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CsChart({ model, height }) {
  const bars = model.bars || [];
  if (!bars.length) return null;
  const hlines = model.hlines || [];
  const markers = model.markers || [];
  return (
    <CandleChart
      bars={bars}
      height={height || 280}
      hlines={hlines}
      markers={markers}
      accent="gn"
    />
  );
}

function CsNote({ read, usable }) {
  const text = read || CS_FIXTURE_READ;
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", margin: "0 16px 14px" }}>
      <span className="label-cap">Read</span>
      <span className="mono">{text}</span>
    </div>
  );
}

// ── honest empty state ────────────────────────────────────────────────
function CsNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no candlestick patterns</div>
        <div className="pv-empty-msg">{message || `No notable candlestick patterns in ${sym || "this ticker"}'s recent bars. The glyph detector requires volume-confirmed reversals at a meaningful level (EMA-20 / support / resistance).`}</div>
        <div className="pv-empty-sub mono dim2">The detector scans the last 8–10 bars for engulfing, hammer, shooting star, doji, harami, morning/evening star, piercing/dark-cloud, and marubozu. When one forms at a key level it will populate automatically.</div>
      </div>
    </div>
  );
}

// ── main view (3 layout directions) ──────────────────────────────────
function CandlestickView({ ticker, dir, mode }) {
  const { model, state, sym, tf, usable, message } = useCandlesModel(ticker, mode);

  if (state === "none") {
    return (
      <div className="pv-view">
        <div className="pv-srcbar">
          <PatternSrcBadge state={state} usable={usable} sym={sym} tf={tf} />
        </div>
        <CsNone sym={sym} message={message} />
      </div>
    );
  }

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={model.tier} tf={tf} />
    </div>
  );

  if (dir === "B") {
    // SPLIT — signals left, reliability reference right
    return (
      <div className="pv-view">
        {SrcBar}
        <CsStat stat={model.stat} confidence={model.confidence} usable={usable} />
        <SectionHeader n={1} title="Candlestick chart" sub={`last ${(model.bars || []).length} ${tf || "daily"} bars · EMA-20/50 · detected levels`} style="minimal" />
        <div className="pv-pad"><CsChart model={model} height={220} /></div>
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={2} title="Detected signals" sub="recent patterns · location + volume" style="minimal" />
            <div className="pv-pad"><CsSignals detected={model.detected} dense /></div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Reliability reference" style="minimal" />
            <div className="pv-pad"><CsReliability dense /></div>
          </div>
        </div>
        <CsNote read={model.read} usable={usable} />
      </div>
    );
  }

  if (dir === "C") {
    // DOSSIER — compact, data-dense
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <CsStat stat={model.stat} confidence={model.confidence} usable={usable} />
        <div className="pv-pad"><CsChart model={model} height={200} /></div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Detected signals</div>
            <CsSignals detected={model.detected} dense />
          </div>
          <div>
            <div className="pv-block-h label-cap">Reliability reference</div>
            <CsReliability dense />
          </div>
        </div>
        <CsNote read={model.read} usable={usable} />
      </div>
    );
  }

  // A — CHART-LED (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <CsStat stat={model.stat} confidence={model.confidence} usable={usable} />
      <SectionHeader n={1} title="Candlestick chart" sub={`${tf || "daily"} bars · EMA-20/50 · pattern markers on detected bars`} style="minimal" />
      <div className="pv-pad"><CsChart model={model} height={280} /></div>
      <SectionHeader n={2} title="Detected candlestick signals" sub="pattern · location vs EMA/S&R · volume confirmation · status" style="minimal" />
      <div className="pv-pad"><CsSignals detected={model.detected} /></div>
      <SectionHeader n={3} title="Historical reliability" sub="win-rate + sample size + avg 5-day follow-through — weight every glyph by its real edge" style="minimal" />
      <div className="pv-pad"><CsReliability /></div>
      <CsNote read={model.read} usable={usable} />
    </div>
  );
}

// ── dynamic "The Read · Candles" line (lens-call) ────────────────────
function CandlesReadLine({ ticker, mode }) {
  const { model, state } = useCandlesModel(ticker, mode);
  if (state === "none") {
    return <span className="mono">No notable candlestick patterns in recent bars — stand aside. The detector requires volume-confirmed reversals at a meaningful level.</span>;
  }
  if (state !== "real") {
    return <span className="mono"><b className="up">Bullish engulfing</b> at the <b className="copper">$176 support</b> on 1.8× volume — confirmed reversal candle (63% historical WR, n=318). Confirmation layer; weight by location + volume, not the glyph alone.</span>;
  }
  const s = model.stat || {};
  const r = model.read || "";
  const tone = s.tone || "gn";
  const textColor = tone === "ink-2" ? undefined : `var(--${tone})`;
  return (
    <span className="mono">
      <b style={{ color: textColor }}>{s.active_signal || "Pattern"}</b>{" "}
      at <b className="copper">{s.location || "—"}</b>,{" "}
      {s.confirmation || "—"} — {s.reliability || "—"}. {" "}
      <span className="dim2">{r.split(".")[0]}.</span>
    </span>
  );
}

Object.assign(window, { CandlestickView, CandlesReadLine });
