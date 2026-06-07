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

  // "The Read" line is sourced from the active theory's REAL engine output
  // (real.read — a per-ticker narrative the engine computes from this stock's
  // bars: see engines/<theory>.py). Wyckoff has its own live WyckoffReadLine.
  // When the live read isn't loaded (no server / insufficient bars / fetch
  // pending) we fall back to mechanism-only text with NO fabricated price levels.
  const pm = usePatternModel(tab, tk, mode);
  const engineRead = (pm && pm.real && pm.real.state === "real" && typeof pm.real.read === "string" && pm.real.read.trim())
    ? pm.real.read.trim() : null;
  const MECH = {
    ensemble: "Weighted composite across all theories — context → structure → projection. Trade only when the stack aligns; size by the confidence band, not the point estimate.",
    mlforecast: "Meta-model over the theory stack → directional bias, cross-checked against the 3-head AI ensemble. Size by the confidence band, not the point estimate.",
    elliott: "Elliott impulse/correction count — trade with the larger-degree trend; the count voids at its structural invalidation level.",
    fibonacci: "Retracement + extension confluence — the golden pocket is the high-odds reaction zone; stacked ratios mark the target shelves.",
    volprofile: "Auction value — acceptance above the value area is bullish, rotation below it shifts value down; the POC is fair value.",
    ichimoku: "Cloud trend system — above a green Kumo with a bullish TK cross and a free Chikou is a full bullish stack.",
    td: "Exhaustion timing — a completed 9-count flags a 1–4 bar pause; use it to trail and not chase, not as a standalone reversal.",
    classical: "Chart-pattern structure — a measured move off the confirmed pivot; the setup fails on a close back through the breakout level.",
    harmonic: "Harmonic PRZ reversal — the pattern completes at its D-leg ratio and voids beyond the X point.",
    wolfe: "Wolfe Wave — entry at the point-5 sweet spot targeting the EPA line; voids beyond point 5.",
    candles: "Candle confirmation — weight by location + volume, not the glyph alone.",
    altcharts: "Heikin-Ashi / Renko — confirm direction and trail; they don't time entries.",
    gann: "Gann price-time squares — a confluence overlay, not a standalone trigger.",
    montecarlo: "Path simulation — P(reach T1 before stop) summarizes expectancy conditional on the setup holding.",
  };
  const theCall = (tab === "wyckoff" && window.WyckoffReadLine)
    ? <WyckoffReadLine ticker={tk} mode={mode} />
    : engineRead
      ? <span className="mono">{engineRead}</span>
      : <span className="mono">{MECH[tab] || "—"}<span className="dim2"> · live read pending data</span></span>;

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
