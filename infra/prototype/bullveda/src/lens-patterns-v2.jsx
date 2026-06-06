// lens-patterns-v2.jsx — reworked Patterns lens (WEFCE-aligned).
// Tab order: Confluence (cockpit) · Wyckoff · Elliott · Fibonacci · Volume Profile
// · Ichimoku · TD Sequential · Classical · Harmonic · Monte Carlo.
// Persisted layout-direction switch (Chart-led / Split / Dossier). Overrides
// window.LensPatterns.

const { useState: useLP } = React;

const PV_SUBTABS = [
  { id: "ensemble", label: "Confluence", sub: "engine", accent: "gn" },
  { id: "mlforecast", label: "ML Forecast", sub: "meta-model", accent: "violet" },
  { id: "wyckoff", label: "Wyckoff", sub: "context", accent: "copper" },
  { id: "elliott", label: "Elliott Wave", sub: "structure", accent: "violet" },
  { id: "fibonacci", label: "Fibonacci", sub: "projection", accent: "amb" },
  { id: "volprofile", label: "Volume Profile", sub: "auction", accent: "cy" },
  { id: "ichimoku", label: "Ichimoku", sub: "cloud", accent: "cy" },
  { id: "td", label: "TD Sequential", sub: "timing", accent: "amb" },
  { id: "classical", label: "Classical", sub: "VCP base", accent: "cy" },
  { id: "harmonic", label: "Harmonic", sub: "gartley", accent: "violet" },
  { id: "wolfe", label: "Wolfe Wave", sub: "5-point EPA", accent: "violet" },
  { id: "candles", label: "Candlesticks", sub: "confirmation", accent: "gn" },
  { id: "altcharts", label: "Alt Charts", sub: "renko/kagi/HA", accent: "cy" },
  { id: "gann", label: "Gann", sub: "angles/time", accent: "copper" },
  { id: "montecarlo", label: "Monte Carlo", sub: "simulation", accent: "violet" },
];
const PV_IDS = PV_SUBTABS.map(s => s.id);

function usePersistTab() {
  const [tab, setTab] = useLP(() => {
    try { const v = localStorage.getItem("pv-subtab"); return PV_IDS.includes(v) ? v : "ensemble"; }
    catch (e) { return "ensemble"; }
  });
  const set = (t) => { setTab(t); try { localStorage.setItem("pv-subtab", t); } catch (e) {} };
  return [tab, set];
}

function LensPatternsV2({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const [tab, setTab] = usePersistTab();
  const [dir, setDir] = usePatternsDir();
  const tk = ticker || { symbol: "ARGN", price: 213.4, pivot: 213.4 };

  const theCall = {
    ensemble: <span className="mono">Weighted composite <b className="up">{CE_COMPOSITE}/100</b> (≥ {CE_THRESHOLD}) · MTF consensus <b className="up">{CE_CONSENSUS}</b> · P(success) <b className="up">0.84</b>. Context → structure → projection align; TD warns of exhaustion near <b className="warn">$214–216</b>. Trigger above <b className="copper">$213.40</b>.</span>,
    mlforecast: <span className="mono">Meta-model over all 7 theories → <b className="up">BUY bias</b>, P(up) high when 5+ theories stack. Cross-checked against the 3-head AI ensemble; size by the confidence band, not the point estimate.</span>,
    wyckoff: window.WyckoffReadLine ? <WyckoffReadLine ticker={tk} mode={mode} /> : <span className="mono">Composite operator is <b className="copper">accumulating</b> — Phase D after a confirmed Spring + SOS. Mark-up on a close &gt; <b className="copper">$213.40</b>; P&amp;F count projects <b className="up">$221 → $237</b>. Invalid below <b className="dn">$187.60</b>.</span>,
    elliott: <span className="mono">Impulse from $178; in <b className="violet">Wave 3 of 5</b> testing the 1.618× extension at <b className="up">$214.6</b>. W5 objective <b className="up">$221–224</b>. Count voids on a close &lt; <b className="dn">$184.90</b>.</span>,
    fibonacci: <span className="mono">Major swing 178→214. Support <b className="warn">golden pocket $190–192</b> stacks .618 + Wyckoff ST + Gartley B (3-hit). Upside <b className="up">cluster $223–225</b> = 1.272 ext + Elliott W5 + P&amp;F. Void below $178.</span>,
    volprofile: <span className="mono">Auction is <b className="up">accepting above VAH $209</b> with POC fair value at <b className="cy">$204</b>. Thin LVN at 211–212 clears the path to <b className="up">$218 → $224</b>. Rotation back below VAL <b className="dn">$199</b> shifts value down.</span>,
    ichimoku: <span className="mono">Price <b className="up">above a green Kumo</b>, bullish TK cross, Chikou free — <b className="up">5/5 signals</b>. Kijun trails at <b className="copper">$201.4</b>; Kumo-break target <b className="up">$222</b>. Neutral on a close back inside the cloud (&lt;$205).</span>,
    td: <span className="mono"><b className="warn">Sell Setup 8 of 9</b> — momentum maturing. A perfected bar-9 near <b className="warn">$214–216</b> flags a 1–4 bar pause; everyone else is bullish, so <b>trail stops, don't chase</b>. TDST support $196.</span>,
    classical: <span className="mono"><b className="cy">VCP / ascending triangle</b> — 5 contractions into a pivot at <b className="copper">$205.20</b>, broken on 2.2× volume and retested. Measured move targets <b className="up">$225 → $235</b>. Fails below pivot.</span>,
    harmonic: <span className="mono"><b className="violet">Bullish Gartley</b> completed at the PRZ (<b>$184–187.5</b>, 0.786 XA) and reversed up. T1/T2 hit; now testing the A retest at <b className="up">$212</b>. Voids below <b className="dn">$178</b>.</span>,
    wolfe: <span className="mono"><b className="violet">Bullish Wolfe Wave</b> — valid 5-point structure, entry at the point-5 sweet spot <b className="copper">$176</b>. Price rides the 1-4 line to the <b className="up">EPA target $210</b> (R:R ≈ 5.7:1). Voids below <b className="dn">$171</b>.</span>,
    candles: <span className="mono"><b className="up">Bullish engulfing</b> at the <b className="copper">$176 support</b> on 1.8× volume — confirmed reversal candle (63% historical WR, n=318). Confirmation layer; weight by location + volume, not the glyph alone.</span>,
    altcharts: <span className="mono">Heikin-Ashi &amp; Renko show an <b className="up">unbroken uptrend</b>; a reversal needs a $3 down-brick / first filled HA candle. Best for a mechanical <b>trail-stop</b> — they confirm direction, they don't time entries.</span>,
    gann: <span className="mono">Price rides just under the <b className="copper">1×1 master line ($216)</b>; next Square-of-Nine at <b className="violet">$219</b>, and the 60-bar price-time square lands <b>Jul 30</b>. Use as a confluence overlay.</span>,
    montecarlo: <span className="mono">2,000-path simulation: right-skewed, median <b className="up">positive</b>, P(reach T1 before stop) <b className="up">≈58%</b> vs stop-first ≈40% — <b className="up">positive expectancy</b> conditional on the setup holding.</span>,
  }[tab];

  return (
    <div className="lens lens--patterns-v2">
      {window.LensSummaryBar && <LensSummaryBar ticker={ticker} mode={mode} kind="patterns" />}
      {window.QuantQuickCard && <QuantQuickCard d={window.quickDecision(ticker, mode)} title={`Quick Read · Patterns · ${mode}`} />}
      <div className="pv-bar">
        <SubTabs tab={tab} onTab={setTab} items={PV_SUBTABS} />
        <DirSwitch dir={dir} onDir={setDir} />
      </div>

      {tab === "ensemble" && <ConfluenceView ticker={tk} dir={dir} mode={mode} onTab={setTab} />}
      {tab === "mlforecast" && <MLForecastView ticker={tk} dir={dir} mode={mode} />}
      {tab === "wyckoff" && <WyckoffView ticker={tk} dir={dir} mode={mode} />}
      {tab === "elliott" && <ElliottView ticker={tk} dir={dir} mode={mode} />}
      {tab === "fibonacci" && <FibonacciView ticker={tk} dir={dir} mode={mode} />}
      {tab === "volprofile" && <VolumeProfileView ticker={tk} dir={dir} mode={mode} />}
      {tab === "ichimoku" && <IchimokuView ticker={tk} dir={dir} mode={mode} />}
      {tab === "td" && <TDSequentialView ticker={tk} dir={dir} mode={mode} />}
      {tab === "classical" && <ClassicalView ticker={tk} dir={dir} mode={mode} />}
      {tab === "harmonic" && <HarmonicView ticker={tk} dir={dir} mode={mode} />}
      {tab === "wolfe" && <WolfeView ticker={tk} dir={dir} mode={mode} />}
      {tab === "candles" && <CandlestickView ticker={tk} dir={dir} mode={mode} />}
      {tab === "altcharts" && <AltChartsView ticker={tk} dir={dir} mode={mode} />}
      {tab === "gann" && <GannView ticker={tk} dir={dir} mode={mode} />}
      {tab === "montecarlo" && <MonteCarloView ticker={tk} dir={dir} mode={mode} />}

      <div className="lens-call">
        <span className="label-cap">The Read · {PV_SUBTABS.find(s => s.id === tab).label}</span>
        {theCall}
      </div>

      <PatternHorizons ticker={tk} method={PV_SUBTABS.find(s => s.id === tab).label} mode={mode} />
    </div>
  );
}

// per-horizon read — same method across swing / position / investment, computed
// from coherentLevels + modeAdjust (real levels, never hardcoded). Mirrors the
// swing/position/investment split in Vinod's confluence files.
function PatternHorizons({ ticker, method, mode }) {
  const L = window.coherentLevels ? window.coherentLevels(ticker) : null;
  if (!L) return null;
  // base off coherentLevels (live), then apply the same mode multipliers as modeAdjust
  const MULT = { SWING: { s: 1, t1: 1, t2: 1 }, POSITION: { s: 0.96, t1: 1.10, t2: 1.18 }, INVESTMENT: { s: 0.84, t1: 1.32, t2: 1.58 } };
  const rows = [
    ["SWING", "2–15d", "SWING"],
    ["POSITION", "1–6mo", "POSITION"],
    ["INVEST", "1–5yr", "INVESTMENT"],
  ].map(([label, hold, m]) => {
    const k = MULT[m];
    const entry = +(L.pivot * 1.002).toFixed(2);
    const stop = +(L.stop * k.s).toFixed(2);
    const t1 = +(L.t1 * k.t1).toFixed(2);
    const t2 = +(L.t2 * k.t2).toFixed(2);
    const risk = Math.max(0.01, entry - stop);
    const rr = ((t1 - entry) / risk);
    return { label, hold, m, entry, stop, t1, t2, rr, active: m === mode };
  });
  return (
    <div className="ph-strip">
      <div className="ph-strip-h mono"><b className="copper">{method}</b> · read by horizon <span className="dim2">— entry · stop · target · R:R · active = your mode toggle</span></div>
      <div className="ph-cells">
        {rows.map((r) => (
          <div key={r.label} className={`ph-cell ${r.active ? "is-active" : ""}`}>
            <div className="ph-cell-h mono"><b>{r.label}</b><span className="dim2"> · {r.hold}</span>{r.active && <span className="ph-now mono">● ACTIVE</span>}</div>
            <div className="ph-row mono"><span className="dim2">entry</span><span className="copper">${r.entry.toFixed(2)}</span></div>
            <div className="ph-row mono"><span className="dim2">stop</span><span className="dn">${r.stop.toFixed(2)}</span></div>
            <div className="ph-row mono"><span className="dim2">T1 / T2</span><span className="up">${r.t1.toFixed(2)} / ${r.t2.toFixed(2)}</span></div>
            <div className="ph-row mono"><span className="dim2">R:R</span><b className={r.rr >= 2 ? "up" : "warn"}>{r.rr.toFixed(2)}R</b></div>
          </div>
        ))}
      </div>
    </div>
  );
}

window.LensPatterns = LensPatternsV2;

// one-time CSS for the per-horizon strip
(function () {
  if (document.getElementById("ph-strip-css")) return;
  const s = document.createElement("style"); s.id = "ph-strip-css";
  s.textContent = `
  .ph-strip{margin-top:12px;border:1px solid var(--glass-line,#232a37);border-radius:8px;background:var(--glass-bg-1,#0f141b);padding:10px 12px;}
  .ph-strip-h{font-size:10px;letter-spacing:.04em;color:var(--ink-2);margin-bottom:8px;}
  .ph-cells{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
  @media(max-width:760px){.ph-cells{grid-template-columns:1fr;}}
  .ph-cell{border:1px solid var(--glass-line,#232a37);border-radius:6px;background:var(--bg-2,#141a23);padding:8px 10px;}
  .ph-cell-h{font-size:10.5px;color:var(--ink-1);letter-spacing:.04em;margin-bottom:5px;}
  .ph-row{display:flex;justify-content:space-between;gap:8px;font-size:10.5px;padding:1.5px 0;}
  .ph-cell.is-active{border-color:var(--copper,#5dd6d6);background:color-mix(in oklab,var(--copper,#5dd6d6) 10%,var(--bg-2,#141a23));}
  .ph-now{float:right;font-size:8px;font-weight:700;letter-spacing:.08em;color:var(--copper,#5dd6d6);}
  `;
  document.head.appendChild(s);
})();
