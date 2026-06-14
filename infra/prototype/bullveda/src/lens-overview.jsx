// lens-overview.jsx — quant overview (overrides the in-file LensOverview)
// Loaded AFTER detail-panel.jsx so window.LensOverview = this one.


// ════════════════════════════════════════════════════════════════════
// DecisionHero — THE one canonical answer. Merges the composite verdict,
// the trade ticket, and the desk-read edge metrics into a single block so
// trade levels / score / expectancy each live in exactly ONE place.
// Consumer reads top-to-bottom: verdict → edge → the trade → act.
// ════════════════════════════════════════════════════════════════════
(function () {
  const css = `
  .dh{ background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:10px; padding:0; margin-bottom:14px; overflow:hidden; }
  .dh--gn{ border-left:3px solid var(--gn); } .dh--amb{ border-left:3px solid var(--amb); } .dh--rd{ border-left:3px solid var(--rd); }
  .dh-top{ display:grid; grid-template-columns:auto 1fr; gap:20px; padding:16px 18px 14px; align-items:center; }
  .dh-vis{ flex:none; display:flex; flex-direction:column; align-items:center; gap:6px; }
  .dh-main{ display:flex; flex-direction:column; gap:9px; min-width:0; }
  .dh-eyebrow{ display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .dh-eyebrow-l{ font-size:10px; letter-spacing:.16em; color:var(--ink-3); }
  .dh-verdict{ display:flex; align-items:baseline; gap:13px; flex-wrap:wrap; }
  .dh-bias{ font-size:25px; font-weight:700; letter-spacing:.01em; line-height:1; }
  .dh-bias--gn{ color:var(--gn); } .dh-bias--amb{ color:var(--amb); } .dh-bias--rd{ color:var(--rd); }
  .dh-net{ font-family:var(--mono); font-size:27px; font-weight:600; line-height:1; color:var(--ink-1); }
  .dh-net-of{ font-size:13px; color:var(--ink-3); }
  .dh-conf{ font-family:var(--mono); font-size:10.5px; color:var(--ink-2); }
  .dh-counts{ display:flex; gap:6px; }
  .dh-cnt{ font-family:var(--mono); font-size:9.5px; font-weight:700; letter-spacing:.05em; padding:2px 8px; border-radius:20px; }
  .dh-cnt--gn{ color:var(--gn); background:color-mix(in oklab,var(--gn) 14%,transparent); }
  .dh-cnt--amb{ color:var(--amb); background:color-mix(in oklab,var(--amb) 14%,transparent); }
  .dh-cnt--rd{ color:var(--rd); background:color-mix(in oklab,var(--rd) 14%,transparent); }
  .dh-setup{ font-family:var(--mono); font-size:12px; color:var(--ink-2); }
  .dh-setup b{ color:var(--ink-1); }
  .dh-read{ font-size:13px; line-height:1.5; color:var(--ink-1); text-wrap:pretty; }
  .dh-dissent{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; font-family:var(--mono); font-size:10.5px; }
  .dh-diss-pill{ font-family:var(--mono); font-size:10.5px; color:var(--ink-1); background:var(--glass-bg-2); border:1px solid var(--glass-line); border-radius:5px; padding:2px 8px; cursor:pointer; }
  .dh-diss-pill:hover{ border-color:var(--copper); color:var(--copper); }
  /* canonical trade ticket strip */
  .dh-ticket{ display:grid; grid-template-columns:repeat(6,1fr); border-top:1px solid var(--glass-line); background:var(--glass-bg-2); }
  .dh-tk{ padding:10px 13px; border-right:1px solid var(--glass-line); display:flex; flex-direction:column; gap:3px; min-width:0; }
  .dh-tk:last-child{ border-right:none; }
  .dh-tk-l{ font-size:8.5px; letter-spacing:.1em; color:var(--ink-3); text-transform:uppercase; }
  .dh-tk-v{ font-family:var(--mono); font-size:16px; font-weight:600; color:var(--ink-1); white-space:nowrap; }
  .dh-tk-v.copper{ color:var(--copper); } .dh-tk-v.up{ color:var(--gn); } .dh-tk-v.dn{ color:var(--rd); }
  .dh-tk-sub{ font-family:var(--mono); font-size:9.5px; color:var(--ink-2); white-space:nowrap; }
  /* hero grid · verdict + ladder (left) · chart (right) */
  .dh-grid{ display:grid; grid-template-columns:minmax(330px,0.9fr) minmax(0,1.1fr); align-items:stretch; }
  .dh-left{ display:flex; flex-direction:column; min-width:0; border-right:1px solid var(--glass-line); }
  .dh-chart{ padding:11px 14px 11px; min-width:0; display:flex; flex-direction:column; }
  .dh-chart-h{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:5px; }
  .dh-chart-h .label-cap{ font-size:8.5px; }
  .dh-chart-hr{ display:flex; align-items:center; gap:10px; flex:none; }
  .dh-ema-leg{ font-size:9px; }
  .dh-chart-toggle{ display:inline-flex; border:1px solid var(--glass-line); border-radius:6px; overflow:hidden; }
  .dh-chart-toggle button{ font-family:var(--mono); font-size:9px; letter-spacing:.04em; padding:3px 9px; background:transparent; color:var(--ink-3); border:none; cursor:pointer; }
  .dh-chart-toggle button:first-child{ border-right:1px solid var(--glass-line); }
  .dh-chart-toggle button.is-on{ background:color-mix(in oklab,var(--copper) 18%,transparent); color:var(--copper); }
  .dh-chart-toggle button:hover:not(.is-on){ color:var(--ink-1); }
  .dh-chart-svg{ display:block; width:100%; height:auto; max-height:128px; }
  .dh-lw{ width:100%; height:auto; flex:1 1 auto; min-height:300px; }
  .dh-rail-stats{ display:flex; border-top:1px solid var(--glass-line); border-bottom:1px solid var(--glass-line); margin-top:3px; }
  .dh-rs{ flex:1; padding:6px 9px; border-right:1px solid var(--glass-line); display:flex; flex-direction:column; gap:1px; min-width:0; }
  .dh-rs:last-child{ border-right:none; }
  .dh-rs-l{ font-size:8px; letter-spacing:.09em; color:var(--ink-3); }
  .dh-rs-v{ font-size:14px; font-weight:600; color:var(--ink-1); }
  .dh-rs-sub{ font-size:8.5px; color:var(--ink-2); white-space:nowrap; }
  .dh-ladder{ padding:11px 14px 11px; display:flex; flex-direction:column; gap:7px; min-width:0; border-top:1px solid var(--glass-line); }
  .dh-state{ display:flex; align-items:center; gap:9px; }
  .dh-state-badge{ font-family:var(--mono); font-size:11px; font-weight:700; letter-spacing:.06em; padding:3px 10px; border-radius:6px; border:1px solid currentColor; }
  .dh-state--gn{ color:var(--gn); background:color-mix(in oklab,var(--gn) 12%,transparent); }
  .dh-state--amb{ color:var(--amb); background:color-mix(in oklab,var(--amb) 12%,transparent); }
  .dh-state--rd{ color:var(--rd); background:color-mix(in oklab,var(--rd) 12%,transparent); }
  .dh-state-note{ font-family:var(--mono); font-size:10.5px; color:var(--ink-2); }
  .dh-rungs{ display:flex; flex-direction:column; gap:2px; }
  .dh-rung{ display:grid; grid-template-columns:54px 1fr auto; align-items:center; gap:9px; padding:3px 8px; border-radius:5px; font-family:var(--mono); font-size:11px; }
  .dh-rung-k{ font-size:8.5px; letter-spacing:.08em; color:var(--ink-3); }
  .dh-rung-v{ font-weight:600; color:var(--ink-1); }
  .dh-rung-d{ font-size:10px; color:var(--ink-2); text-align:right; }
  .dh-rung--now{ background:var(--glass-bg-2); border:1px solid color-mix(in oklab,var(--copper) 40%,var(--glass-line)); }
  .dh-rung--now .dh-rung-k{ color:var(--copper); } .dh-rung--now .dh-rung-v{ color:var(--copper); }
  .dh-rung--t .dh-rung-v{ color:var(--gn); } .dh-rung--stop .dh-rung-v{ color:var(--rd); } .dh-rung--trig .dh-rung-v{ color:var(--copper); }
  /* T3 bull-stretch rung — momentum-confirmed extension above T2 */
  .dh-rung--stretch{ background:color-mix(in oklab,var(--violet) 9%,transparent); border:1px dashed color-mix(in oklab,var(--violet) 38%,var(--glass-line)); }
  .dh-rung--stretch .dh-rung-v{ color:var(--violet); }
  .dh-rung--stretch .dh-rung-k{ color:var(--violet); }
  /* provenance + reachability metadata under each target rung value */
  .dh-rung-meta{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; grid-column:2 / 4; font-size:8.5px; letter-spacing:.02em; color:var(--ink-3); margin-top:1px; padding-bottom:1px; }
  .dh-rung-src{ color:var(--ink-2); }
  .dh-rung-reach{ padding:0 5px; border-radius:4px; border:1px solid var(--glass-line); background:var(--glass-bg-2); color:var(--ink-2); font-weight:600; }
  .dh-rung-reach--lo{ color:var(--amb); border-color:color-mix(in oklab,var(--amb) 35%,var(--glass-line)); }
  .dh-rung-reach--hi{ color:var(--gn); border-color:color-mix(in oklab,var(--gn) 35%,var(--glass-line)); }
  .dh-rung-badge{ font-size:7.5px; font-weight:700; letter-spacing:.07em; padding:1px 5px; border-radius:4px; color:var(--violet); border:1px solid color-mix(in oklab,var(--violet) 40%,var(--glass-line)); background:color-mix(in oklab,var(--violet) 12%,transparent); }
  /* let target rungs wrap to two lines (value row + meta row) */
  .dh-rung--t, .dh-rung--stretch{ row-gap:0; }
  .dh-fit{ display:flex; align-items:center; gap:7px; flex-wrap:wrap; padding-top:6px; margin-top:1px; border-top:1px solid var(--glass-line); font-family:var(--mono); font-size:10px; color:var(--ink-2); }
  .dh-fit-chip{ padding:2px 7px; border-radius:5px; background:var(--glass-bg-2); border:1px solid var(--glass-line); color:var(--ink-1); }
  .dh-actions{ display:flex; gap:8px; flex-wrap:wrap; padding:12px 14px; border-top:1px solid var(--glass-line); }
  .dh-act{ font-family:var(--mono); font-size:11.5px; font-weight:600; padding:8px 15px; border-radius:7px; border:1px solid var(--glass-line); background:var(--glass-bg-2); color:var(--ink-1); cursor:pointer; transition:all .15s; }
  .dh-act:hover{ border-color:var(--copper); }
  .dh-act--primary{ background:color-mix(in oklab,var(--gn) 18%,transparent); border-color:color-mix(in oklab,var(--gn) 45%,transparent); color:var(--gn); }
  .dh-act--primary:hover{ background:color-mix(in oklab,var(--gn) 26%,transparent); border-color:var(--gn); }
  .dh-act--rd{ color:var(--rd); border-color:color-mix(in oklab,var(--rd) 35%,transparent); }
  .dh-act--rd:hover{ border-color:var(--rd); }
  .dh-act--spacer{ margin-left:auto; }
  @media (max-width:980px){ .dh-top{ grid-template-columns:1fr; } .dh-vis{ flex-direction:row; align-self:flex-start; } .dh-grid{ grid-template-columns:1fr; } .dh-left{ border-right:none; } .dh-chart{ border-top:1px solid var(--glass-line); } .dh-lw{ min-height:280px; } .dh-ticket{ grid-template-columns:repeat(3,1fr); } .dh-tk:nth-child(3n){ border-right:none; } .dh-tk:nth-child(-n+3){ border-bottom:1px solid var(--glass-line); } }
  @media (max-width:520px){ .dh-ticket{ grid-template-columns:repeat(2,1fr); } .dh-tk:nth-child(2n){ border-right:none; } }`;
  if (!document.getElementById("dh-css")) { const s = document.createElement("style"); s.id = "dh-css"; s.textContent = css; document.head.appendChild(s); }
})();

// Resolve a coherent {price,pivot,stop,t1,t2} set. The canonical ticker is
// already consistent; off-universe stubs reuse one ticker's levels with their
// own price, so we rescale geometry around price when it's clearly inconsistent.
// Returns the REAL trade-plan levels — never fabricates geometry. `valid` is true
// only when the engine produced an ordered, complete plan (stop<pivot<t1<t2, all >0);
// callers show "—" / a "no plan" note when !valid instead of inventing numbers.
window.coherentLevels = function (t) {
  const price = t.price || t.pivot || 0;
  let pivot = t.pivot || price, stop = t.stop, t1 = t.t1, t2 = t.t2;
  const valid = stop > 0 && pivot > 0 && t1 > 0 && t2 > 0 && stop < pivot && pivot < t1 && t1 < t2;
  if (!valid) {
    // off-universe / no scan trade-plan: fill numeric placeholders from the real
    // price so consumers never crash on null.toFixed. `valid:false` stays so
    // sizing / EV / "estimated" labels can gate on it — these are NOT real S/R.
    pivot = price > 0 ? price : pivot;
    if (!(stop > 0)) stop = +(price * 0.94).toFixed(2);
    if (!(t1 > 0)) t1 = +(price * 1.06).toFixed(2);
    if (!(t2 > 0)) t2 = +(price * 1.12).toFixed(2);
  }
  return { price, pivot, stop, t1, t2, valid };
};

// ─── Shared: structural-target source-type → friendly label ───────────────────
// Used by every tab (Overview ladder, Plan targets, Scanner/Elite chips) so the
// provenance of a target reads consistently. Source `type` comes from each
// trade_engine target's `sources[].type`. Reuse via window.teSourceLabel.
const TE_SOURCE_LABEL = {
  OB: "Order Block", EW_INT: "EW Wave (W)", EW_MAJ: "EW Major [W]",
  FIB_4H: "4H Fib", FIB: "Fib Ext", FIB_D: "Fib Ext", HVN: "Vol Node",
  VAH: "Value Area", BSL: "Liquidity", SWING: "Swing High",
  AVWAP_52: "AVWAP 52w", AVWAP_EARN: "AVWAP Earn", ROUND: "Round #",
};
window.teSourceLabel = function (type) {
  return TE_SOURCE_LABEL[type] || (type ? String(type) : "");
};
// teSourceChips — given a target object {sources:[{type,weight,...}]}, return the
// top-N distinct friendly labels (weight-ordered), joined for a compact chip.
// e.g. "Order Block · 4H Fib". Returns "" when no usable sources.
window.teSourceChips = function (target, n) {
  if (!target || !Array.isArray(target.sources) || !target.sources.length) return "";
  const seen = new Set(); const out = [];
  const sorted = target.sources.slice().sort((a, b) => (b.weight || 0) - (a.weight || 0));
  for (const s of sorted) {
    const lbl = window.teSourceLabel(s.type);
    if (!lbl || seen.has(lbl)) continue;
    seen.add(lbl); out.push(lbl);
    if (out.length >= (n || 2)) break;
  }
  return out.join(" · ");
};

// ─── useTradeEngine — the RICH per-mode trade plan (real, /api/trade_engine) ───
// The scan-row `decisionsByMode` only varies `stop`; t1/t2 are identical across
// modes and entry/r_multiple are null. trade_engine returns fully-distinct per-mode
// t1/t2/stop + a real entry object + r_multiple/confluence/p_reach/warnings. This
// hook fetches the active mode's payload on (symbol, mode) change, stores it in the
// window-level BV.tradeEngineCache (keyed SYM|MODE), and forces a re-render when it
// lands — so toggling SWING/POSITION/INVEST repaints EVERY rung, not just STOP.
function useTradeEngine(symbol, mode) {
  const [, force] = React.useState(0);
  React.useEffect(() => {
    if (!symbol || !window.__BV || !window.__BV.fetchTradeEngine) return;
    let live = true;
    // already cached (incl. null = "no plan") → no fetch, just read synchronously
    const cached = window.__BV.tradeEngineCached(symbol, mode);
    if (cached !== undefined) return;
    window.__BV.fetchTradeEngine(symbol, mode).then(() => { if (live) force(n => n + 1); });
    return () => { live = false; };
  }, [symbol, mode]);
  const p = (window.__BV && window.__BV.tradeEngineCached) ? window.__BV.tradeEngineCached(symbol, mode) : undefined;
  return (p && typeof p === "object") ? p : null;   // null until loaded / no-plan
}

// teLevels — build a coherentLevels-shaped {price,pivot,stop,t1,t2,valid} from a
// rich trade_engine payload. Extracts `.price` from the nested t1/t2/stop objects
// and uses the real per-mode entry. Returns null if the payload is unusable so the
// caller can fall back to decisionsByMode → coherentLevels.
function teLevels(te, livePrice) {
  if (!te) return null;
  const pn = (o) => (o && typeof o === "object" && typeof o.price === "number" && isFinite(o.price)) ? o.price : null;
  const stop = pn(te.stop), t1 = pn(te.t1), t2 = pn(te.t2);
  // t3 is the momentum-confirmed bull-stretch extension — null/0 when unarmed
  const t3 = pn(te.t3);
  const entry = pn(te.entry) != null ? pn(te.entry) : (typeof te.price_at_analysis === "number" ? te.price_at_analysis : null);
  const price = (typeof livePrice === "number" && livePrice > 0) ? livePrice
    : (typeof te.price_at_analysis === "number" ? te.price_at_analysis : entry);
  const pivot = entry != null ? entry : price;
  // A plan is VALID with t1 + stop alone — T2 is OPTIONAL. When present it must be
  // ordered (t2>t1); when absent (null/0) the plan is still valid and uses the
  // engine, never the poisoned coherentLevels fallback. This is the root fix: a
  // sane engine T1 (e.g. INTC $118) must win even when the engine emits no T2.
  const hasT2 = t2 > 0;
  const valid = stop > 0 && pivot > 0 && t1 > 0 && stop < pivot && pivot < t1 && (!hasT2 || t1 < t2);
  if (!(stop > 0 && t1 > 0)) return null;   // need at least an ordered stop + T1 → else caller falls back
  return {
    price, pivot, stop, t1, valid, _entry: entry, _te: te,
    t2: (hasT2 ? t2 : null),                // T2 optional — null when the engine didn't emit one
    t3: (t3 > 0 ? t3 : null),
    // rich target objects carry sources[] + p_reach for provenance/reachability chips
    _tt1: te.t1, _tt2: (hasT2 ? te.t2 : null), _tt3: te.t3 || null,
  };
}

// teRRof — per-mode structural R:R from a cached trade_engine payload, else the
// scan-row fallback. SINGLE source so every Overview surface (ladder, §2 entry
// checklist, thesis ref/AI prompt, invalidation) agrees on R:R — critical after
// the overhead-supply gate, which can drop T1's R:R below the legacy scan value.
function teRRof(te, ticker) {
  if (te && te.t1 && typeof te.t1.r_multiple === "number" && isFinite(te.t1.r_multiple)) return te.t1.r_multiple;
  return (ticker && typeof ticker.rMultiple === "number") ? ticker.rMultiple : 0;
}
// teLevelsOf — coherent {price,pivot,stop,t1,t2,valid} with structural precedence
// (rich trade_engine → scan-row coherentLevels). Mirrors DecisionHero's `L`.
function teLevelsOf(te, ticker) {
  const base = window.coherentLevels(ticker);
  return teLevels(te, base.price) || base;
}

// ─── discoveryFootprint — which screen engines REALLY surfaced this name ───
// Reads each engine's live signal for this ticker from real data: RS rank, ML
// P(up), earnings-beat list, options UOA list, insider Form-4 edge, SMC pillar.
// rank (when shown) comes from the engine's actual top-N ordering (resolveEngines).
function discoveryFootprint(ticker) {
  const sym = (ticker.symbol || "").toUpperCase();
  const BV = window.__BV || {};
  const sc = ticker._scan || {};
  const n = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
  const sym0 = (s) => String(s || "").split(".")[0].toUpperCase();
  const engines = (window.resolveEngines ? window.resolveEngines() : []) || [];
  const rankIn = (id) => { const e = engines.find(x => x.id === id); if (!e || !e.rows) return null; const i = e.rows.findIndex(r => sym0(r[0]) === sym); return i >= 0 ? i + 1 : null; };
  const tone3 = (hit, strong) => !hit ? "off" : strong ? "gn" : "cy";
  const out = [];
  // Momentum — relative-strength rank
  const rs = n(ticker.rsRank) != null ? n(ticker.rsRank) : (sc.rs && sc.rs !== "—" ? parseFloat(sc.rs) : null);
  if (rs != null) out.push({ id: "momentum", label: "Momentum", surf: "momentum", sub: "rel-strength", hit: rs >= 70, rank: rankIn("momentum"), m: `RS ${Math.round(rs)}`, tone: tone3(rs >= 70, rs >= 85) });
  // ML — P(up)
  const pUp = ticker.ml && n(ticker.ml.direction) != null ? n(ticker.ml.direction) : null;
  if (pUp != null) out.push({ id: "ai-predict", label: "ML Predictions", surf: "ai-predict", sub: "model edge", hit: pUp >= 0.55, rank: rankIn("ml"), m: `P(up) ${Math.round(pUp * 100)}%`, tone: tone3(pUp >= 0.55, pUp >= 0.65) });
  // Earnings AI — present in the beat-prediction list
  const eb = (BV.earningsBeat || []).find(x => sym0(x.ticker) === sym);
  out.push({ id: "earnings", label: "Earnings AI", surf: "earnings-ai", sub: "beat prediction", hit: !!eb, rank: rankIn("earnings-ai"), m: eb ? `beat ${Math.round(eb.beat_score || 0)}` : "no print", tone: tone3(!!eb, eb && (eb.beat_score || 0) >= 70) });
  // Options Flow — present in the UOA list
  const of = (BV.optionsFlow || []).find(x => sym0(x.ticker) === sym);
  out.push({ id: "options-flow", label: "Options Flow", surf: "options", sub: "unusual activity", hit: !!of, rank: rankIn("options"), m: of ? (of.status || "UOA") : "no UOA", tone: tone3(!!of, of && of.status === "STRONG") });
  // Insider — Form-4 edge
  const ie = window.insiderEdge ? window.insiderEdge(sym) : null;
  out.push({ id: "insider", label: "Insider", surf: "insider", sub: "Form-4", hit: !!(ie && ie.buyers > 0), rank: rankIn("insider"), m: ie && ie.buyers ? `${ie.buyers} buyer${ie.buyers === 1 ? "" : "s"}` : "none", tone: tone3(!!(ie && ie.buyers), ie && ie.cluster) });
  // SMC · Patterns — smart-money pillar
  const smc = sc.pillarPct ? n(sc.pillarPct.smc) : null;
  if (smc != null) out.push({ id: "smc", label: "SMC · Patterns", lens: "patterns", sub: "structure", hit: smc >= 55, rank: rankIn("smc"), m: `SMC ${Math.round(smc)}`, tone: tone3(smc >= 55, smc >= 70) });
  return out;
}

// horizon strip — same ticker scored across all 3 modes, side by side
function HorizonStrip({ ticker, mode, onMode }) {
  const cv = window.compositeVerdict;
  if (!cv) return null;
  const modes = [["SWING", "Swing", "2–15d"], ["POSITION", "Position", "1–6mo"], ["INVESTMENT", "Invest", "1–5yr"]];
  return (
    <div className="hz">
      <span className="hz-tag mono">HORIZONS</span>
      {modes.map(([m, label, hold]) => {
        const v = cv(ticker, m);
        const bias = v.biasLabel || (window.secBias ? window.secBias(v.verdict) : v.verdict);
        return (
          <button key={m} className={`hz-cell hz-${v.vtone} ${m === mode ? "is-active" : ""}`} onClick={() => onMode && onMode(m)} title={`Score ${v.net}/100 · ${v.conf} confidence`}>
            <span className="hz-mode mono">{label}<span className="hz-hold dim2"> · {hold}</span></span>
            <span className={`hz-bias mono kpi-tone--${v.vtone}`}>{bias}</span>
            <span className="hz-net mono">{v.net}<span className="dim2">/100</span></span>
          </button>
        );
      })}
      <span className="hz-note mono dim2">one name, three time horizons — weighting reflows per mode</span>
    </div>
  );
}

// ─── RegimeFit — the missing P5 line: does THIS setup work in THIS regime? ───
const FAM_REG_FIT = {
  "Breakout Expansion": { trending: "GOOD", choppy: "OK", risk_off: "POOR", panic: "POOR" },
  "Trend Continuation": { trending: "GOOD", choppy: "OK", risk_off: "POOR", panic: "POOR" },
  "Impulse Catalyst": { trending: "GOOD", choppy: "GOOD", risk_off: "OK", panic: "OK" },
  "Special Situation": { trending: "GOOD", choppy: "GOOD", risk_off: "OK", panic: "OK" },
};
function RegimeFit({ ticker, mode }) {
  const M = (window.__BV && window.__BV.market) || null;
  const reg4 = (M && M.regime4) || (ticker._scan && ticker._scan._raw && ticker._scan._raw.regime4) || null;
  if (!reg4 && !M) return null;
  const regLabel = M ? `${M.regimeLabel} · ${M.regimeTrend}` : String(reg4 || "").replace(/_/g, " ");
  const regKind = /trending/.test(reg4 || "") ? "trending" : /choppy/.test(reg4 || "") ? "choppy" : /panic/.test(reg4 || "") ? "panic" : /off/.test(reg4 || "") ? "risk_off" : "choppy";
  const fam = ticker.setupFamily || "";
  const fit = (FAM_REG_FIT[fam] || {})[regKind] || (fam ? "OK" : null);
  const fitTone = fit === "GOOD" ? "up" : fit === "POOR" ? "dn" : "warn";
  const cat = ticker.catalystTier;
  return (
    <div className="rfit mono" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 11.5, padding: "7px 12px", margin: "0 0 10px", background: "var(--glass-bg-2)", border: "1px solid var(--glass-line)", borderRadius: 8 }}>
      <span className="label-cap" style={{ fontSize: 9 }}>REGIME FIT</span>
      <span><b className={M && !M.regimeOn ? "dn" : "up"}>{regLabel}</b>{M && M.maxSize != null ? <span className="dim2"> · max size {M.maxSize}%</span> : null}</span>
      {fam ? <span className="dim2">·</span> : null}
      {fam ? <span>setup <b>{fam}</b> in this regime: <b className={fitTone}>{fit}</b></span> : null}
      {cat ? <><span className="dim2">·</span><span>catalyst <b className={cat === 1 ? "up" : cat === 2 ? "warn" : "dim2"}>T{cat}</b></span></> : null}
      {fit === "POOR" ? <span className="dn" style={{ fontSize: 10.5 }}>⚠ setup is regime-misaligned — size down or wait</span> : null}
    </div>
  );
}
function SurfacedBy({ ticker }) {
  const engines = React.useMemo(() => discoveryFootprint(ticker), [ticker.symbol]);
  const hits = engines.filter(e => e.hit);
  const miss = engines.filter(e => !e.hit);
  const go = (e) => { if (e.lens) { window.__setLens && window.__setLens(e.lens); } else { window.__setSurface && window.__setSurface(e.surf); } };
  return (
    <div className="sfb">
      <div className="sfb-hd">
        <span className="sfb-tag mono">SURFACED BY</span>
        <span className="sfb-count mono"><b className={hits.length >= 4 ? "up" : hits.length >= 3 ? "copper" : "warn"}>{hits.length}</b> of {engines.length} engines</span>
        <span className="sfb-sub mono dim2">independent screens that flagged {ticker.symbol} — more hits = stronger confluence · click to open the engine</span>
      </div>
      <div className="sfb-chips">
        {hits.sort((a, b) => (a.rank || 99) - (b.rank || 99)).map(e => (
          <button key={e.id} className={`sfb-chip sfb-${e.tone}`} onClick={() => go(e)} title={`${e.label} · ${e.sub}`}>
            <span className="sfb-chip-l mono">{e.label}</span>
            {e.rank != null && <span className="sfb-rank mono">#{e.rank}</span>}
            <span className="sfb-m mono">{e.m}</span>
          </button>
        ))}
        {miss.length > 0 && <span className="sfb-miss mono dim2">not in · {miss.map(e => e.label).join(" · ")}</span>}
      </div>
    </div>
  );
}

// ─── SetupChart — compact TradingView candles w/ plan price-lines on the axis ───
function SetupChart({ L, sym, view = "full" }) {
  const wrap = React.useRef(null);
  const refs = React.useRef({});

  // REAL daily candles from /api/ohlcv (with the plan price-lines drawn on the axis);
  // the seeded series below is the offline/standalone fallback only.
  const [real, setReal] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !sym) { setReal(null); return; }
    let alive = true;
    BV.get("/api/ohlcv/" + encodeURIComponent(sym)).then(res => {
      if (!alive) return;
      const candles = (res && res.candles) || [];
      if (candles.length < 5) { setReal(null); return; }
      const volArr = (res && res.volume) || [];
      const bars = candles.map((c, i) => {
        const vv = volArr[i]; const v = (vv && typeof vv === "object") ? (vv.value || 0) : (typeof vv === "number" ? vv : 0);
        return { time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, value: v };
      });
      const ema = per => { const k = 2 / (per + 1); let pr = bars[0].close; return bars.map((b, i) => { pr = i === 0 ? b.close : b.close * k + pr * (1 - k); return { time: b.time, value: +pr.toFixed(2) }; }); };
      setReal({ bars, e9: ema(9), e21: ema(21) });
    }).catch(() => { if (alive) setReal(null); });
    return () => { alive = false; };
  }, [sym]);
  // deterministic seeded series — offline fallback (base → VCP contraction → live)
  const seeded = React.useMemo(() => {
    const str = sym || "ARCM"; let s = 0;
    for (let i = 0; i < str.length; i++) s += str.charCodeAt(i) * (i + 7);
    const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    const n = 46, step = 86400, now = Math.floor(Date.now() / 1000), start = now - n * step;
    const baseMid = (L.stop + L.pivot) / 2, range = (L.pivot - L.stop) || (L.pivot * 0.05);
    const bars = []; let p = L.pivot * 0.985;
    for (let i = 0; i < n; i++) {
      const t = i / (n - 1);
      // volatility contracts through the base (VCP), expands on the breakout leg
      const contract = t < 0.4 ? 1 - t * 0.6 : t < 0.78 ? 0.78 - (t - 0.4) * 1.05 : 0.36 + (t - 0.78) * 2.1;
      const vol = range * 0.18 * Math.max(0.12, contract);
      let target;
      if (t < 0.4) target = baseMid + (L.pivot - baseMid) * (0.4 - t);
      else if (t < 0.78) target = baseMid + Math.sin(i * 0.7) * vol * 0.55;
      else target = L.pivot + (L.price - L.pivot) * Math.pow((t - 0.78) / 0.22, 0.9);
      p = p + (target - p) * 0.32 + (rng() - 0.5) * vol * 1.15;
      // occasional small gap for realism
      let o = i === 0 ? p : bars[i - 1].close;
      if (i > 0 && rng() > 0.9) o = bars[i - 1].close * (1 + (rng() - 0.5) * 0.012);
      const c = +p.toFixed(2);
      const dayRange = vol * (0.55 + rng() * 1.25);              // varied true range
      const upWick = dayRange * (0.15 + rng() * 0.6);
      const dnWick = dayRange * (0.15 + rng() * 0.6);
      const hi = +(Math.max(o, c) + upWick).toFixed(2);
      const lo = +(Math.min(o, c) - dnWick).toFixed(2);
      const breakout = t > 0.78;
      const spike = rng() > 0.86 ? 0.7 : 0;
      const v = Math.round((0.35 + rng() * 0.4 + (breakout ? 0.7 : 0) + spike) * 1e6);
      bars.push({ time: start + i * step, open: +(+o).toFixed(2), high: hi, low: lo, close: c, value: v });
    }
    bars[n - 1].close = +L.price.toFixed(2);
    bars[n - 1].high = Math.max(bars[n - 1].high, bars[n - 1].close + range * 0.05);
    bars[n - 1].low = Math.min(bars[n - 1].low, bars[n - 1].close);
    const ema = per => { const k = 2 / (per + 1); let pr = bars[0].close; return bars.map((b, i) => { pr = i === 0 ? b.close : b.close * k + pr * (1 - k); return { time: b.time, value: +pr.toFixed(2) }; }); };
    return { bars, e9: ema(9), e21: ema(21) };
  }, [sym, L.pivot, L.stop, L.price, L.t1, L.t2]);
  const d = real || seeded;   // real candles when loaded, seeded fallback otherwise

  // create chart once
  React.useEffect(() => {
    if (!wrap.current || !window.LightweightCharts) return;
    const LWC = window.LightweightCharts;
    const cssv = (n, f) => (getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f);
    const chart = LWC.createChart(wrap.current, {
      autoSize: false,
      width: Math.max(10, wrap.current.clientWidth), height: Math.max(10, wrap.current.clientHeight),
      layout: { background: { color: "transparent" }, textColor: cssv("--ink-3", "#7c807c"), fontFamily: "inherit", fontSize: 9 },
      grid: { vertLines: { visible: false }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      crosshair: { mode: 1, vertLine: { visible: false, labelVisible: false }, horzLine: { labelVisible: false, color: "rgba(255,255,255,0.12)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.10)", scaleMargins: { top: 0.08, bottom: 0.22 }, entireTextOnly: true },
      timeScale: { visible: false, rightOffset: 2 },
      handleScroll: false, handleScale: false,
    });
    const candle = chart.addCandlestickSeries({
      upColor: "#34d399", downColor: "#f87171", borderUpColor: "#34d399", borderDownColor: "#f87171",
      wickUpColor: "rgba(52,211,153,0.7)", wickDownColor: "rgba(248,113,113,0.7)",
      priceLineVisible: true, priceLineColor: "rgba(217,119,87,0.85)", priceLineStyle: 0, priceLineWidth: 1, lastValueVisible: true,
      autoscaleInfoProvider: () => { const rg = refs.current.range; return rg ? { priceRange: { minValue: rg.min, maxValue: rg.max } } : null; },
    });
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
    // SVG overlay for shaded risk / reward zones (chart is static — redraw on resize)
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "dh-lw-zones");
    svg.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1;";
    wrap.current.style.position = "relative";
    wrap.current.appendChild(svg);
    refs.current = { chart, candle, vol, svg, lines: [], ov: [] };
    const draw = () => {
      const r = refs.current; if (!r.chart || !r.zones) return;
      const host = wrap.current; if (!host) return;
      const psW = (() => { try { return r.chart.priceScale("right").width(); } catch (e) { return 52; } })();
      const W = host.clientWidth - psW, H = host.clientHeight;
      while (r.svg.firstChild) r.svg.removeChild(r.svg.firstChild);
      r.zones.forEach(z => {
        const y1 = r.candle.priceToCoordinate(z.top), y2 = r.candle.priceToCoordinate(z.bot);
        if (y1 == null || y2 == null) return;
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", 0); rect.setAttribute("y", Math.min(y1, y2));
        rect.setAttribute("width", Math.max(0, W)); rect.setAttribute("height", Math.abs(y2 - y1));
        rect.setAttribute("fill", z.fill); rect.setAttribute("opacity", z.op);
        r.svg.appendChild(rect);
      });
    };
    refs.current.draw = draw;
    const fit = () => {
      const host = wrap.current; if (!host) return false;
      const r = host.getBoundingClientRect();
      const w = Math.round(r.width), h = Math.round(r.height) || 288;
      if (w < 20) { return false; }                   // still hidden / unlaid-out
      try {
        // jiggle the size so LWC reallocates the bitmap and repaints, even if it
        // was first sized while hidden (otherwise the canvas backing stays 300×150).
        chart.resize(w - 1, h, true);
        chart.resize(w, h, true);
        chart.timeScale().fitContent();
        if (refs.current.replay) refs.current.replay();
      } catch (e) {}
      draw();
      return true;
    };
    refs.current.fit = fit;
    const ro = new ResizeObserver(() => requestAnimationFrame(fit));
    ro.observe(wrap.current);
    refs.current.ro = ro;
    fit();
    // persistent self-heal: if the canvas backing ever drifts from the container width
    // (e.g. the chart mounted while the lens was hidden), re-fit. Cheap; runs for the lifetime.
    const heal = setInterval(() => {
      const host = wrap.current; if (!host) return;
      const w = Math.round(host.getBoundingClientRect().width); if (w < 20) return;
      const cv = host.querySelector("canvas");
      if (!cv || Math.abs(cv.width - w) > 6) fit();
    }, 350);
    refs.current.heal = heal;
    return () => { try { clearInterval(heal); ro.disconnect(); chart.remove(); } catch (e) {} refs.current = {}; };
  }, []);

  // feed data + zones + bold level lines + EMAs
  React.useEffect(() => {
    const r = refs.current; if (!r.chart) return;
    const lows = d.bars.map(b => b.low), highs = d.bars.map(b => b.high);
    const bLo = Math.min(...lows), bHi = Math.max(...highs);
    const mk = (price, color, title, w = 2, style = 0) => r.candle.createPriceLine({ price, color, lineWidth: w, lineStyle: style, axisLabelVisible: true, title });
    r.lines.forEach(l => r.candle.removePriceLine(l));
    if (!L.valid) {
      // no plan → frame purely on the real bars, no plan price-lines
      r.range = { min: bLo * 0.99, max: bHi * 1.01 };
      r.zones = []; r.lines = [];
    } else if (view === "action") {
      // tight frame — include recent bars AND the plan stop/trigger
      r.range = { min: Math.min(L.stop, bLo) * 0.994, max: Math.max(L.price, bHi) * 1.02 };
      r.zones = [
        { top: r.range.max, bot: L.pivot, fill: "#34d399", op: 0.06 },
        { top: L.pivot, bot: Math.max(L.stop, r.range.min), fill: "#f87171", op: 0.09 },
      ];
      r.lines = [
        mk(L.pivot, "#d97757", `TRIGGER ${L.pivot.toFixed(2)}`),
        mk(L.stop, "#f87171", `STOP ${L.stop.toFixed(2)}`),
      ];
    } else {
      // full trade — frame to encompass stop → T2 AND the real bars
      // T2 is optional — frame to the highest real target present (T2 if any, else T1)
      const topTgt = (L.t2 && L.t2 > 0) ? L.t2 : L.t1;
      r.range = { min: Math.min(L.stop, bLo) * 0.994, max: Math.max(topTgt, bHi) * 1.012 };
      r.zones = [
        { top: L.t1, bot: L.pivot, fill: "#34d399", op: 0.06 },                          // reward runway → T1
        { top: L.pivot, bot: Math.max(L.stop, r.range.min), fill: "#f87171", op: 0.09 },  // risk band → stop
      ];
      r.lines = [
        ...(L.t2 && L.t2 > 0 ? [mk(L.t2, "#34d399", `T2 ${L.t2.toFixed(2)}`, 1, 2)] : []),
        mk(L.t1, "#34d399", `T1 ${L.t1.toFixed(2)}`),
        mk(L.pivot, "#d97757", `TRIGGER ${L.pivot.toFixed(2)}`),
        mk(L.stop, "#f87171", `STOP ${L.stop.toFixed(2)}`),
      ];
    }
    r.candle.setData(d.bars);
    r.vol.setData(d.bars.map(b => ({ time: b.time, value: b.value, color: b.close >= b.open ? "rgba(52,211,153,0.30)" : "rgba(248,113,113,0.30)" })));
    r.replay = () => { try { r.candle.setData(d.bars); } catch (e) {} };
    r.ov.forEach(o => r.chart.removeSeries(o)); r.ov = [];
    const addLine = (data, color) => { const ls = r.chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }); ls.setData(data); r.ov.push(ls); };
    addLine(d.e9, "rgba(93,214,214,0.55)");
    addLine(d.e21, "rgba(167,139,250,0.5)");
    r.chart.timeScale().fitContent();
    requestAnimationFrame(() => { (r.fit || r.draw) && (r.fit || r.draw)(); });
    setTimeout(() => { (r.fit || r.draw) && (r.fit || r.draw)(); }, 60);
  }, [d, L.pivot, L.stop, L.t1, L.t2, view]);

  return <div ref={wrap} className="dh-lw" />;
}
window.SetupChart = SetupChart;

function DecisionHero({ ticker, mode, heroStyle, sizeCat, onLens }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const vtone = cv ? cv.vtone : (net >= 66 ? "gn" : net >= 50 ? "amb" : "rd");
  const bias = cv ? cv.biasLabel : (window.secBias ? window.secBias(ticker.verdict) : ticker.verdict);
  const pillars = ticker.pillars;
  // ── per-mode levels (decisions_by_mode is the authoritative plan for the active
  //    horizon — Position/Invest have different stop/T1/T2/R:R than swing) ──
  const dmKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "investment" : "swing";
  const dec = (ticker.decisionsByMode && ticker.decisionsByMode[dmKey]) || null;
  // RICH per-mode plan (real, /api/trade_engine) — fully-distinct t1/t2/stop +
  // real entry + r_multiple per horizon. Re-renders on (symbol, mode) change.
  const te = useTradeEngine(ticker.symbol, mode);
  const Lbase = window.coherentLevels(ticker);
  // precedence: rich trade_engine → scan-row decisionsByMode → coherentLevels
  const Lte = teLevels(te, Lbase.price);
  const L = Lte
    ? Lte
    : (dec && dec.stop > 0 && dec.t1 > 0 && dec.t2 > 0)
    ? { price: Lbase.price, pivot: dec.entry_mid || Lbase.pivot, stop: dec.stop, t1: dec.t1, t2: dec.t2, valid: true }
    : Lbase;
  // per-mode R:R — prefer the rich payload's t1 r_multiple, then scan-row, then ticker
  const teRR = (te && te.t1 && typeof te.t1.r_multiple === "number") ? te.t1.r_multiple : null;
  const modeRR = teRR != null ? teRR : (dec && typeof dec.rr_ratio === "number" ? dec.rr_ratio : (ticker.rMultiple || null));
  const [chartView, setChartView] = React.useState(() => { try { return localStorage.getItem("dh-chart-view") || "full"; } catch (e) { return "full"; } });
  const pickChartView = v => { setChartView(v); try { localStorage.setItem("dh-chart-view", v); } catch (e) {} };
  // ── live actions (real): watchlist toggle + route to Automated Trade / Alerts ──
  const [wlOn, setWlOn] = React.useState(() => !!(window.WatchStore && window.WatchStore.has(ticker.symbol)));
  React.useEffect(() => {
    const h = () => setWlOn(!!(window.WatchStore && window.WatchStore.has(ticker.symbol)));
    window.addEventListener("watchlist-change", h);
    return () => window.removeEventListener("watchlist-change", h);
  }, [ticker.symbol]);
  const actWatch = () => { if (window.WatchStore) window.WatchStore.toggle({ sym: ticker.symbol, name: ticker.name, price: ticker.price, chg: ticker.chg, score: ticker.score, verdict: ticker.verdict, setup: ticker.setupFamily }); };
  const actTrade = () => window.__setSurface && window.__setSurface("portfolio-srf");
  const actAlerts = () => window.__setSurface && window.__setSurface("alerts");
  const entry = L.pivot;                       // the trigger / entry
  const risk = entry - L.stop;
  const reward1 = L.t1 - entry;
  const rrToT1 = risk > 0 ? reward1 / risk : 0;
  const ss = ticker.setupStats || {};
  const wr = ss.winRate != null ? ss.winRate : null, lb = ss.wilsonLB != null ? ss.wilsonLB : null;
  const evR = (wr != null && L.valid) ? (wr * rrToT1 - (1 - wr) * 1) : null;
  // ── real book/sizing context ──
  const NAV = (window.__BV && window.__BV.nav) || null;
  const navRisk = NAV ? NAV * 0.005 : 420;          // 0.5%-NAV risk budget (½-Kelly floor)
  const held = ((window.__BV && window.__BV.realHoldings && window.__BV.realHoldings()) || []).find(p => String(p.sym || "").toUpperCase() === String(ticker.symbol || "").toUpperCase());
  const scanTs = (window.__BV && window.__BV.scanMeta && window.__BV.scanMeta.ts) || null;
  const scanT = scanTs ? String(scanTs).split(" ").slice(-2).join(" ") : null;
  const erTxt = (ticker.earnings && ticker.earnings.days != null) ? `earnings in ${ticker.earnings.days}d` : "a clean catalyst window";
  const dissenters = cv ? cv.dissenters.slice(0, 4) : [];

  // ── live STATE relative to the trigger — the "what do I do now" crown ──
  const buyTop = entry * 1.03;
  let st, stTone, stNote, stIcon = "▶";   // ▶ default; ⚠ for caution
  if (!L.valid) { st = "NO PLAN"; stTone = "ink"; stNote = "off-universe · live quote only — levels below are price-estimates, not a scan plan"; }
  else if (L.price < entry) { st = "WATCH"; stTone = "amb"; stNote = `${((entry - L.price) / L.price * 100).toFixed(1)}% below trigger · arm alert at $${entry.toFixed(2)}`; }
  else if (L.price <= buyTop) { st = "ACTIONABLE"; stTone = "gn"; stNote = "in the buy zone · trigger cleared"; }
  else { st = "EXTENDED"; stTone = "amb"; stNote = `${((L.price - entry) / entry * 100).toFixed(1)}% above trigger · wait for a pullback`; }

  // Option 2 soft-demote (2026-06-14) — a buy-zone state with too-thin reward is
  // NOT actionable. When R:R to T1 is below the floor (name jammed under a wall,
  // e.g. FTNT 0.32R into a $150 double top), demote ACTIONABLE → CAUTION so the
  // headline matches the ladder. Stays tradeable (BUY remains clickable) — the
  // truth lives in the state, it does not hard-block the action (user-agency).
  const RR_FLOOR = 2.0;   // matches the §2 entry-checklist Reward:Risk gate
  if (L.valid && st === "ACTIONABLE" && rrToT1 < RR_FLOOR) {
    st = "CAUTION"; stTone = "amb"; stIcon = "⚠";
    stNote = `poor R:R ${rrToT1.toFixed(2)}R — capped at $${L.t1.toFixed(2)}, needs a break to continue`;
  }

  // sizing math (risk-based): risk budget ÷ per-share stop distance
  const shares = (L.valid && risk > 0) ? Math.round(navRisk / risk) : 0;
  const dollars = Math.round(shares * L.price);
  const navPct = NAV ? (dollars / NAV * 100) : null;

  // price ladder rungs, high → low, distance measured from live price
  const dist = v => `${v >= L.price ? "+" : ""}${((v - L.price) / L.price * 100).toFixed(1)}%`;
  // provenance + reachability come from the rich trade_engine target objects (Lte)
  const srcOf = tt => (window.teSourceChips ? window.teSourceChips(tt, 2) : "");
  const pReachOf = tt => (tt && typeof tt.p_reach === "number" && isFinite(tt.p_reach)) ? tt.p_reach : null;
  const rungs = [
    { k: "T1", v: L.t1, cls: "dh-rung--t", d: dist(L.t1), field: "canonical_trade_plan.target1", src: srcOf(L._tt1), reach: pReachOf(L._tt1) },
    { k: "NOW", v: L.price, cls: "dh-rung--now", d: "live", field: "price" },
    { k: "TRIGGER", v: entry, cls: "dh-rung--trig", d: dist(entry), field: "canonical_trade_plan.entry.low" },
    { k: "STOP", v: L.stop, cls: "dh-rung--stop", d: dist(L.stop), field: "canonical_trade_plan.stop" },
  ];
  // T2 rung — ONLY when the engine emitted a real T2 (>0). Never synthesized.
  if (L.t2 && L.t2 > 0) {
    rungs.push({ k: "T2", v: L.t2, cls: "dh-rung--t", d: dist(L.t2), field: "canonical_trade_plan.target2", src: srcOf(L._tt2), reach: pReachOf(L._tt2) });
  }
  // T3 bull-stretch rung — ONLY when the engine armed it (price>0). Sits above T2.
  if (L.t3 && L.t3 > 0) {
    rungs.push({ k: "T3", v: L.t3, cls: "dh-rung--stretch", d: dist(L.t3), field: "canonical_trade_plan.target3", src: srcOf(L._tt3), reach: pReachOf(L._tt3), stretch: true });
  }
  rungs.sort((a, b) => b.v - a.v);
  // overall momentum-reachability (0..1) for the verdict-level pill
  const momReach = (te && te.confidence && te.confidence.components && typeof te.confidence.components.momentum_reachability === "number")
    ? te.confidence.components.momentum_reachability : null;

  return (
    <div className={`dh dh--${vtone}`}>
      <div className="dh-grid">
       <div className="dh-left">
        <div className="dh-top">
        <div className="dh-vis">
          {heroStyle === "gauge" && <Gauge value={net} label="COMPOSITE" size={sizeCat === "S" ? 108 : 124} />}
          {heroStyle === "cone" && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div className="label-cap">10d cone · ±{ticker.ml.magnitude.hi.toFixed(0)}%</div>
              <Cone lo={ticker.ml.magnitude.lo} mid={ticker.ml.magnitude.mid} hi={ticker.ml.magnitude.hi} w={200} h={100} />
            </div>
          )}
          {(heroStyle === "radar" || !heroStyle) && <Radar pillars={pillars} size={sizeCat === "S" ? 124 : 144} />}
        </div>

        <div className="dh-main">
          <div className="dh-eyebrow">
            <span className="dh-eyebrow-l mono">COMPOSITE BIAS · {cv ? cv.lenses.length : 12} LENSES · <b className="copper">{mode}</b></span>
            <Pill tone="gn" dot small>{scanT ? "AS OF " + scanT + " PT" : "LIVE"}</Pill>
          </div>

          <div className="dh-verdict">
            <span className={`dh-bias dh-bias--${vtone}`}>{bias}</span>
            <span className="dh-net mono" title="Graded for your active horizon (shown above) — the per-mode composite that drives the verdict.">{net}<span className="dh-net-of">/100</span></span>
            {typeof ticker.score === "number" && Math.round(ticker.score) !== net && (
              <span className="dh-net-alt mono" style={{ fontSize: 14, color: "var(--ink-3)", fontWeight: 600 }} title="Generic, horizon-agnostic 5-pillar score (the number shown on the Scanner). It does NOT reweight catalyst / entry-quality for your timeframe, so it usually reads higher than the per-mode number.">· overall {Math.round(ticker.score)}</span>
            )}
            {cv && cv.gated && (
              <span className="dh-gated mono" style={{ fontSize: 11, color: "var(--amb)", marginLeft: 6, fontWeight: 600 }} title="The stock itself isn't bearish — new long entries are blocked market-wide today (crash / distribution-day gate). The directional read is neutral; revisit when the market gate clears.">· entry-gated today</span>
            )}
            <span className="dh-conf mono">conf {cv ? cv.conf : "—"}</span>
            {momReach != null && (
              <span className="dh-conf mono" title="Overall momentum-reachability — how much trend/MACD/volatility budget supports price running into the target ladder (higher = T2/T3 more attainable).">reach {Math.round(momReach * 100)}%</span>
            )}
            {cv && (
              <span className="dh-counts">
                <span className="dh-cnt dh-cnt--gn">{cv.agree} agree</span>
                <span className="dh-cnt dh-cnt--amb">{cv.caution} caution</span>
                <span className="dh-cnt dh-cnt--rd">{cv.fail} against</span>
              </span>
            )}
          </div>

          <div className="dh-setup mono">
            <b className="copper">{ticker.setupFamily || "—"}</b>
            <span> · hold ~{ticker.holdDays || 9}d · </span>
            {evR != null ? <b className={evR >= 0 ? "up" : "dn"}>{evR >= 0 ? "+" : ""}{evR.toFixed(2)}R expectancy</b> : <b className="dim2">expectancy —</b>}
            <span> · edge LB <b className={lb != null ? "up" : "dim2"}>{lb != null ? (lb * 100).toFixed(0) + "%" : "—"}</b>{ss.n != null ? <span className="dim2"> n={ss.n}{ss.n < 30 ? " ⚠" : ""}</span> : null} · {erTxt}</span>
          </div>

          <div className="dh-read">
            <b className={vtone === "gn" ? "up" : vtone === "rd" ? "dn" : "warn"}>{ticker.symbol} reads {bias.toLowerCase()}</b> for a {mode.toLowerCase()} hold{ticker.setupFamily ? <> — a <b>{ticker.setupFamily.toLowerCase()}</b> setup</> : ""}{lb != null ? <> with a {ss.n != null && ss.n < 30 ? "preliminary" : "sample-validated"} edge (Wilson LB {(lb * 100).toFixed(0)}%{ss.n != null ? `, n=${ss.n}` : ""}{evR != null ? `, ${evR >= 0 ? "+" : ""}${evR.toFixed(2)}R` : ""})</> : <> (no per-setup track record yet)</>}. {L.valid ? "Downside is bounded at one stop; " : "No complete trade plan for this name; "}{erTxt} is the live caveat to size around.
          </div>

          {dissenters.length > 0 && (
            <div className="dh-dissent mono">
              <span className="dim2">Watch the dissent:</span>
              {dissenters.map(d => (
                <button key={d.k} className="dh-diss-pill" onClick={() => onLens && onLens(d.k)} title={d.why}>{d.k} <span className="dim2">{d.v}</span></button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── the setup, drawn · + price-to-levels ladder + live state ── */}
        <div className="dh-ladder">
          <div className="dh-state">
            <span className={`dh-state-badge dh-state--${stTone} mono`}>{stIcon} {st}</span>
            <span className="dh-state-note mono">{stNote}</span>
          </div>
          <div className="dh-rungs">
            {rungs.map((r, i) => {
              const reachPct = r.reach != null ? Math.round(r.reach * 100) : null;
              const reachCls = reachPct == null ? "" : reachPct >= 60 ? " dh-rung-reach--hi" : reachPct < 45 ? " dh-rung-reach--lo" : "";
              const hasMeta = !!r.src || reachPct != null || r.stretch;
              return (
              <div key={i} className={`dh-rung ${r.cls} mono`}>
                <span className="dh-rung-k">{r.k}</span>
                <span className="dh-rung-v" data-field={r.field} data-provenance="comp" title={!L.valid && r.k !== "NOW" ? "estimated from price — no scan trade plan for this off-universe name" : undefined}>{!L.valid && r.k !== "NOW" ? "~" : ""}${r.v.toFixed(2)}</span>
                <span className="dh-rung-d">{r.d}</span>
                {hasMeta && (
                  <span className="dh-rung-meta">
                    {r.stretch && <span className="dh-rung-badge" title="Momentum-confirmed bull-stretch extension — armed only when trend, MACD and budget support a run beyond T2.">STRETCH · armed</span>}
                    {r.src && <span className="dh-rung-src" title="Structural confluence behind this target (top sources).">{r.src}</span>}
                    {reachPct != null && <span className={`dh-rung-reach${reachCls}`} title="Modeled probability price reaches this target within the hold window (analog × Monte-Carlo × Bayes).">{reachPct}% reach</span>}
                  </span>
                )}
              </div>
              );
            })}
          </div>
          <div className="dh-rail-stats">
            <div className="dh-rs">
              <span className="dh-rs-l mono">R : R</span>
              <span className="dh-rs-v mono copper" data-field="canonical_trade_plan.rr_ratio">{modeRR != null ? modeRR.toFixed(2) + "R" : "—"}</span>
              <span className="dh-rs-sub mono">reward ÷ risk</span>
            </div>
            <div className="dh-rs">
              <span className="dh-rs-l mono">SIZE</span>
              <span className="dh-rs-v mono">{shares ? shares + " sh" : "—"}</span>
              <span className="dh-rs-sub mono">{shares ? `$${dollars.toLocaleString()}${navPct != null ? ` · ${navPct.toFixed(1)}% NAV` : ""}` : "no plan"}</span>
            </div>
            <div className="dh-rs">
              <span className="dh-rs-l mono">EDGE</span>
              <span className={`dh-rs-v mono ${lb != null ? "up" : "dim2"}`}>{lb != null ? (lb * 100).toFixed(0) + "%" : "—"}</span>
              <span className="dh-rs-sub mono">Wilson LB{ss.pf != null ? ` · PF ${ss.pf.toFixed(2)}` : ""}</span>
            </div>
          </div>
          <div className="dh-fit mono">
            {L.valid ? <span className="dh-fit-chip">size = ${Math.round(navRisk).toLocaleString()} risk ÷ ${risk.toFixed(2)} stop</span> : null}
            <span className="dh-fit-chip">{held ? `in book · ${Math.abs(held.qty || 0)} sh` : "not held"}</span>
            {ticker.beta != null ? <span className="dh-fit-chip">β {ticker.beta.toFixed(2)} → market</span> : null}
            {Lte ? <span className="dh-fit-chip" title="Levels sourced from the per-mode structural target engine (distinct T1/T2/stop/entry for this horizon).">structural · {mode.toLowerCase()} plan</span> : null}
            {te && te.invest_stub ? <span className="dh-fit-chip warn" title={(te.warnings && te.warnings[0]) || "Invest targets are analyst-consensus PT × 1.0/1.3 (interim — structural IV targets pending)."}>⚠ analyst-PT targets</span> : null}
            <span>{NAV ? "½-Kelly · 0.5%-NAV risk" : "½-Kelly reference"}</span>
          </div>
        </div>
       </div>

       <div className="dh-chart">
          <div className="dh-chart-h">
            <span className="label-cap mono">{chartView === "action" ? "THE SETUP · stop · trigger · EMA 9/21" : `THE SETUP · stop · trigger · ${(L.t2 && L.t2 > 0) ? "T1 / T2" : "T1"} · EMA 9/21`}</span>
            <div className="dh-chart-hr">
              <span className="mono dim2 dh-ema-leg"><b style={{ color: "var(--cy)" }}>━</b> EMA9 <b style={{ color: "var(--violet)" }}>━</b> EMA21</span>
              <div className="dh-chart-toggle mono">
                <button className={chartView === "action" ? "is-on" : ""} onClick={() => pickChartView("action")} title="Tight frame — bigger candles">Action</button>
                <button className={chartView === "full" ? "is-on" : ""} onClick={() => pickChartView("full")} title="Show the full trade — targets on chart">Full trade</button>
              </div>
            </div>
          </div>
          <SetupChart L={L} sym={ticker.symbol} view={chartView} />
        </div>
      </div>

      <div className="dh-actions">
        <button className="dh-act dh-act--primary" onClick={actTrade} title="Open Automated Trade to place a bracket order">▲ Place bracket</button>
        <button className={`dh-act ${wlOn ? "dh-act--primary" : ""}`} onClick={actWatch}>{wlOn ? "✓ Watchlisted" : "＋ Watchlist"}</button>
        <button className="dh-act" onClick={actTrade} title="Open Automated Trade to size the position">⚙ Adjust size</button>
        <button className="dh-act" onClick={actAlerts} title="Open Alerts to arm a price alert">🔔 Alert at ${entry.toFixed(2)}</button>
        <button className="dh-act dh-act--rd dh-act--spacer" onClick={actTrade} title="Open Automated Trade to place a short">▼ Place short</button>
      </div>
    </div>
  );
}
window.DecisionHero = DecisionHero;

// ─── Thesis card — crisp bull/bear case synthesized across all lenses ───
(function () {
  const css = `
  .thx { background:var(--glass-bg-1); border:1px solid color-mix(in oklab,var(--copper) 22%,var(--glass-line)); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:11px; margin-bottom:4px; }
  .thx-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .thx-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .thx-bias { font:700 11px var(--mono); padding:3px 10px; border-radius:999px; border:1px solid color-mix(in oklab,currentColor 42%,transparent); background:color-mix(in oklab,currentColor 12%,transparent); }
  .thx-head-sub { font-size:10px; }
  .thx-ai-btn { flex:none; }
  .thx-tag { flex:none; font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .thx-line { font-size:13.5px; line-height:1.55; color:var(--ink-1); }
  .thx-col { padding-left:9px; border-left:2px solid var(--glass-line); }
  .thx-col--bull { border-left-color:color-mix(in oklab,var(--gn) 45%,transparent); }
  .thx-col--bear { border-left-color:color-mix(in oklab,var(--rd) 45%,transparent); }
  .thx-cols { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .thx-col-h { font-size:9.5px; letter-spacing:0.08em; margin-bottom:5px; }
  .thx-pt { display:flex; gap:8px; align-items:baseline; padding:3px 0; font-size:12px; line-height:1.45; }
  .thx-pt-k { flex:none; min-width:58px; font-weight:700; color:var(--ink-1); font-size:10.5px; }
  .thx-score { flex:none; display:inline-flex; align-items:center; justify-content:center; min-width:24px; height:15px; border-radius:3px; font-size:9.5px; font-weight:700; }
  .thx-score--gn { background:color-mix(in oklab,var(--gn) 20%,transparent); color:var(--gn); }
  .thx-score--amb { background:color-mix(in oklab,var(--amb) 18%,transparent); color:var(--amb); }
  .thx-score--rd { background:color-mix(in oklab,var(--rd) 18%,transparent); color:var(--rd); }
  .thx-pt-d { color:var(--ink-2); }
  .thx-ref { background:var(--glass-bg-2); border:1px solid var(--glass-line); border-radius:6px; padding:9px 11px; }
  .thx-ref-h { font-size:8.5px; letter-spacing:0.1em; display:block; margin-bottom:7px; }
  .thx-ref-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px 14px; }
  .thx-ref-cell { display:flex; flex-direction:column; gap:1px; }
  .thx-ref-cell .dim2 { font-size:9px; letter-spacing:0.04em; text-transform:uppercase; }
  .thx-ref-cell .mono:last-child { font-size:12.5px; font-weight:600; color:var(--ink-1); }
  .thx-foot { font-size:9.5px; padding-top:6px; border-top:1px solid var(--glass-line); }
  @media (max-width:760px){ .thx-cols{ grid-template-columns:1fr; } .thx-ref-grid{ grid-template-columns:repeat(2,1fr); } }`;
  if (!document.getElementById("thx-css")) { const s = document.createElement("style"); s.id = "thx-css"; s.textContent = css; document.head.appendChild(s); }
})();

function ThesisCard({ ticker, mode }) {
  const [tAi, setTAi] = React.useState(null);   // null | "loading" | text
  // structural per-mode plan — keeps the ref table + AI thesis levels coherent
  // with the hero ladder (overhead-supply gate aware).
  const te = useTradeEngine(ticker.symbol, mode);
  const Lt = teLevelsOf(te, ticker);
  const rrT = teRRof(te, ticker);
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const bias = cv ? cv.biasLabel : (window.secBias ? window.secBias(ticker.verdict) : ticker.verdict);
  const tone = net >= 66 ? "up" : net >= 50 ? "warn" : "dn";
  // verdict-derived tone for the BIAS WORD (so word + color agree even when the
  // numeric score is high but the verdict is gated to Neutral); `tone` above stays
  // for the numeric score (magnitude color).
  const vtoneCls = cv ? (cv.vtone === "gn" ? "up" : cv.vtone === "rd" ? "dn" : "warn") : tone;
  const sTone = v => v >= 62 ? "gn" : v >= 46 ? "amb" : "rd";
  const entry = (ticker.pivot || ticker.price || 0) * 1.002;
  const ss = ticker.setupStats || {};
  const erTxt = (ticker.earnings && ticker.earnings.days != null) ? `earnings in ${ticker.earnings.days}d` : "a clean catalyst window";
  const bulls = cv ? cv.lenses.filter(l => l.v >= 60).sort((a, b) => b.v - a.v).slice(0, 4) : [];
  const bears = cv ? cv.lenses.filter(l => l.v < 48).sort((a, b) => a.v - b.v).slice(0, 3) : [];
  const ref = [
    ["Entry", `$${entry.toFixed(2)}`],
    ["Stop", `$${((Lt && Lt.stop) || ticker.stop || 0).toFixed(2)}`],
    ["T1 · T2", `$${((Lt && Lt.t1) || ticker.t1 || 0).toFixed(2)} · $${((Lt && Lt.t2) || ticker.t2 || 0).toFixed(2)}`],
    ["R:R", `${(rrT || 0).toFixed(2)}R`],
    ["Setup", ticker.setupFamily || "—"],
    ["Win · Wilson", ss.winRate ? `${(ss.winRate * 100).toFixed(0)}% · ${(ss.wilsonLB * 100).toFixed(0)}% LB` : "—"],
    ["Sample", ss.n ? `n=${ss.n}` : "—"],
    ["Earnings", ticker.earnings ? `${ticker.earnings.days}d${ticker.earnings.date ? ` · ${ticker.earnings.date}` : ""}` : "—"],
  ];
  const aiThesis = () => `Write a crisp swing-trade thesis for ${ticker.symbol}${ticker.name ? " (" + ticker.name + ")" : ""}, ${mode} timeframe, overall read ${bias} ${net}/100. 4-5 sentences in plain English: the core idea, the 2-3 strongest supporting points, the single biggest risk, and the key levels to watch.
Supporting: ${bulls.length ? bulls.map(b => `${b.k} ${b.v}/100 (${b.why})`).join("; ") : "composite score " + net}.
Risks / weakest: ${bears.length ? bears.map(b => `${b.k} ${b.v}/100 (${b.why})`).join("; ") : erTxt}.
Levels: entry $${entry.toFixed(2)}, stop $${((Lt && Lt.stop) || ticker.stop || 0).toFixed(2)}, targets $${((Lt && Lt.t1) || ticker.t1 || 0).toFixed(2)} / $${((Lt && Lt.t2) || ticker.t2 || 0).toFixed(2)}, R:R ${(rrT || 0).toFixed(2)}, setup ${ticker.setupFamily || "continuation"}.`;
  const writeThesis = async () => { setTAi("loading"); const r = await window.aiComplete(aiThesis()); setTAi(r.text); };
  const Pt = ({ b }) => (
    <div className="thx-pt"><span className="thx-pt-k mono">{b.k}</span><span className={`thx-score thx-score--${sTone(b.v)} mono`}>{b.v}</span><span className="thx-pt-d">{b.why}</span></div>
  );
  return (
    <div className="thx">
      <div className="thx-head">
        <div className="thx-head-l">
          <span className="thx-tag mono">THESIS</span>
          <span className={`thx-bias mono kpi-tone--${cv ? cv.vtone : sTone(net)}`}>{bias} · {net}/100</span>
          <span className="thx-head-sub mono dim2">{mode.toLowerCase()} · synthesized across 14 lenses</span>
        </div>
        <button className="thx-ai-btn aix-btn mono" onClick={writeThesis} disabled={tAi === "loading"}>
          {tAi === "loading" ? "✦ thinking…" : "✦ Write the full thesis"}
        </button>
      </div>

      <div className="thx-line">{ticker.symbol} reads <b className={vtoneCls}>{bias}</b> for a {mode.toLowerCase()} hold — a <b>{ticker.setupFamily || "continuation"}</b> setup on a <b className={tone}>{net}/100</b> cross-lens score, into {erTxt}.</div>

      <div className="thx-cols">
        <div className="thx-col thx-col--bull">
          <div className="thx-col-h mono up">▲ WHY · THE CASE</div>
          {bulls.length ? bulls.map((b, i) => <Pt key={i} b={b} />)
            : <div className="thx-pt"><span className="thx-pt-d dim2">Composite {net}/100 with broad lens agreement.</span></div>}
        </div>
        <div className="thx-col thx-col--bear">
          <div className="thx-col-h mono dn">▼ WHY NOT · THE RISK</div>
          {bears.length ? bears.map((b, i) => <Pt key={i} b={b} />)
            : <div className="thx-pt"><span className="thx-pt-d dim2">No lens materially dissents — main risk is {erTxt} and the broad tape.</span></div>}
        </div>
      </div>

      {tAi && tAi !== "loading" && (
        <div className="aix-out mono thx-aiout">
          <span className="aix-tag">✦ KAIROS THESIS</span>
          <span className="aix-txt">{tAi}</span>
        </div>
      )}

      <div className="thx-foot mono dim2">Click any lens above to verify a point. Informational / educational only — not advice.</div>
    </div>
  );
}
window.ThesisCard = ThesisCard;

// ─── News Catalyst classifier — LLM-structured headline reads ───
(function () {
  const css = `
  .nc { background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:9px; margin-bottom:4px; }
  .nc-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .nc-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .nc-tag { font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .nc-sub { font-size:10.5px; }
  .nc-row { display:flex; align-items:center; gap:9px; padding:6px 8px; background:var(--glass-bg-2); border-radius:5px; border-left:2px solid var(--glass-line); }
  .nc-row--high { border-left-color:var(--gn); } .nc-row--med { border-left-color:var(--amb); } .nc-row--low { border-left-color:var(--ink-4); }
  .nc-time { flex:none; font:600 9.5px var(--mono); color:var(--ink-3); min-width:34px; }
  .nc-type { flex:none; font:700 8.5px var(--mono); letter-spacing:0.05em; padding:2px 6px; border-radius:3px; background:color-mix(in oklab,var(--cy) 14%,transparent); color:var(--cy); }
  .nc-mat { flex:none; font:700 8px var(--mono); letter-spacing:0.06em; }
  .nc-mat--high { color:var(--gn); } .nc-mat--med { color:var(--amb); } .nc-mat--low { color:var(--ink-3); }
  .nc-h { font-size:11.5px; color:var(--ink-2); line-height:1.4; }
  .nc-foot { font-size:9.5px; padding-top:5px; border-top:1px solid var(--glass-line); }`;
  if (!document.getElementById("nc-css")) { const s = document.createElement("style"); s.id = "nc-css"; s.textContent = css; document.head.appendChild(s); }
})();

function ncAge(dateStr) {
  if (!dateStr) return "";
  const then = Date.parse(String(dateStr).replace(" ", "T"));
  if (!isFinite(then)) return "";
  const h = (Date.now() - then) / 3600000;
  if (h < 1) return Math.max(0, Math.round(h * 60)) + "m";
  if (h < 24) return Math.round(h) + "h";
  const d = Math.round(h / 24);
  return d <= 9 ? d + "d" : "9d+";
}
function NewsCatalysts({ ticker }) {
  const [ai, setAi] = React.useState(null);
  const [news, setNews] = React.useState(null);  // null=loading · []=none · [..]=real
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !ticker.symbol) { setNews([]); return; }
    let alive = true;
    BV.get("/api/news?t=" + encodeURIComponent(ticker.symbol) + "&limit=6")
      .then(d => { if (alive) setNews((d && d.articles) || []); })
      .catch(() => { if (alive) setNews([]); });
    return () => { alive = false; };
  }, [ticker.symbol]);
  const heads = (news || []).map(a => {
    const s = typeof a.sent === "number" ? a.sent : 0;
    const mat = Math.abs(s) >= 0.5 ? "high" : Math.abs(s) >= 0.2 ? "med" : "low";
    const type = s >= 0.15 ? "POSITIVE" : s <= -0.15 ? "NEGATIVE" : "NEUTRAL";
    return { t: ncAge(a.date), h: a.title, type, mat, src: a.source || "", url: a.url || "", sent: s };
  });
  const classify = async () => {
    setAi("loading");
    const prompt = `You are a news catalyst classifier for a stock trader following ${ticker.symbol}. For EACH headline below, give one short line: catalyst type, how material it is (high/med/low), and whether it's tradeable now or already priced in. Be concise.\n` + heads.map(h => `- ${h.h}`).join("\n");
    const r = await window.aiComplete(prompt);
    setAi(r.text);
  };
  return (
    <div className="nc">
      <div className="nc-head">
        <div className="nc-head-l">
          <span className="nc-tag mono">NEWS CATALYSTS</span>
          <span className="nc-sub mono dim2">live headlines · sentiment-scored</span>
        </div>
        <button className="aix-btn mono" onClick={classify} disabled={ai === "loading" || !heads.length}>{ai === "loading" ? "✦ thinking…" : "✦ Classify catalysts"}</button>
      </div>
      {news === null
        ? <div className="nc-row"><span className="nc-h dim2">Loading headlines…</span></div>
        : heads.length === 0
        ? <div className="nc-row"><span className="nc-h dim2">No recent news for {ticker.symbol}.</span></div>
        : heads.map((n, i) => (
          <a key={i} className={`nc-row nc-row--${n.mat}`} href={n.url || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: "none", cursor: n.url ? "pointer" : "default" }}>
            <span className="nc-time">{n.t}</span>
            <span className="nc-type" style={{ color: n.type === "POSITIVE" ? "var(--gn)" : n.type === "NEGATIVE" ? "var(--rd)" : "var(--ink-3)" }}>{n.type}</span>
            <span className={`nc-mat nc-mat--${n.mat}`}>{n.mat === "high" ? "MATERIAL" : n.mat === "med" ? "MODERATE" : "LOW"}</span>
            <span className="nc-h">{n.h}{n.src ? <span className="dim2"> · {n.src}</span> : null}</span>
          </a>
        ))}
      {ai && ai !== "loading" && (
        <div className="aix-out mono" style={{ width: "100%" }}>
          <span className="aix-tag">✦ KAIROS · CATALYST READ</span>
          <span className="aix-txt">{ai}</span>
        </div>
      )}
      <div className="nc-foot mono dim2">Live EODHD headlines, sentiment-scored · type/materiality classified by the LLM. Informational only — not advice.</div>
    </div>
  );
}
window.NewsCatalysts = NewsCatalysts;

// ─── Entry Checklist — runs the buy funnel live as ✓/✗ rows ───
(function () {
  const css = `
  .bk { background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:8px; padding:13px 15px; display:flex; flex-direction:column; gap:10px; margin-bottom:4px; }
  .bk-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .bk-head-l { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .bk-tag { font:700 9px var(--mono); letter-spacing:0.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .bk-score { font:700 13px var(--mono); }
  .bk-verdict { font:700 9px var(--mono); letter-spacing:0.08em; padding:3px 9px; border-radius:999px; border:1px solid currentColor; }
  .bk-bar { height:6px; border-radius:999px; background:var(--glass-bg-2); overflow:hidden; }
  .bk-bar i { display:block; height:100%; border-radius:999px; }
  .bk-rows { display:grid; grid-template-columns:1fr 1fr; gap:6px 14px; }
  .bk-row { display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid var(--glass-line); }
  .bk-ic { flex:none; width:17px; height:17px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font:700 10px var(--mono); }
  .bk-ic--pass { background:color-mix(in oklab,var(--gn) 22%,transparent); color:var(--gn); }
  .bk-ic--fail { background:color-mix(in oklab,var(--rd) 18%,transparent); color:var(--rd); }
  .bk-k { flex:1; font-size:11.5px; color:var(--ink-1); }
  .bk-v { flex:none; font:600 11px var(--mono); }
  .bk-need { flex:none; font:500 9px var(--mono); color:var(--ink-3); min-width:54px; text-align:right; }
  .bk-foot { font-size:10px; padding-top:5px; border-top:1px solid var(--glass-line); }
  @media (max-width:680px){ .bk-rows{ grid-template-columns:1fr; } }`;
  if (!document.getElementById("bk-css")) { const s = document.createElement("style"); s.id = "bk-css"; s.textContent = css; document.head.appendChild(s); }
})();

function BuyChecklist({ ticker, mode }) {
  // structural per-mode R:R — the §2 readiness gate must agree with the hero
  // ladder, so a buy-into-wall name (low R:R after the overhead-supply gate)
  // correctly FAILS the Reward:Risk check instead of passing on the legacy value.
  const teBc = useTradeEngine(ticker.symbol, mode);
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  const net = cv ? cv.net : (ticker.score || 60);
  const bias = cv ? cv.biasLabel : (window.biasRead ? window.biasRead(ticker).label : (window.secBias ? window.secBias(ticker.verdict) : "—"));
  const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const proj = (window.AIPredict && ticker.symbol) ? window.AIPredict.projection(ticker.symbol, moKey) : null;
  const lensV = n => cv ? (cv.lenses.find(l => l.k === n || l.k.startsWith(n)) || {}).v : null;
  const ss = ticker.setupStats || {};
  const rr = teRRof(teBc, ticker);
  const erDays = ticker.earnings ? ticker.earnings.days : null;
  const hold = ticker.holdDays || 9;
  const checks = [
    { k: "Composite ≥ 66", v: `${net}/100`, need: "≥66", pass: net >= 66 },
    { k: "Lens confluence", v: cv ? `${cv.agree}/${cv.lenses.length}` : "—", need: "majority", pass: cv ? cv.agree >= Math.ceil(cv.lenses.length * 0.5) : false },
    { k: "Technicals aligned", v: lensV("Technicals") != null ? `${lensV("Technicals")}` : "—", need: "≥60", pass: (lensV("Technicals") || 0) >= 60 },
    { k: "Pattern / SMC", v: lensV("Patterns") != null ? `${lensV("Patterns")}` : "—", need: "≥60", pass: (lensV("Patterns") || 0) >= 60 },
    { k: "AI P(up)", v: proj ? `${Math.round(proj.pUp * 100)}%` : "—", need: "≥55%", pass: proj ? proj.pUp >= 0.55 : false },
    { k: "Setup edge", v: ss.wilsonLB ? `${(ss.wilsonLB * 100).toFixed(0)}% n${ss.n}` : "—", need: "LB≥45·n≥30", pass: (ss.wilsonLB || 0) >= 0.45 && (ss.n || 0) >= 30 },
    { k: "Reward : Risk", v: `${rr.toFixed(2)}R`, need: "≥2.0", pass: rr >= 2 },
    (mode === "INVESTMENT"
      ? { k: "Earnings (core event)", v: erDays != null ? `${erDays}d` : "none", need: "review", pass: true }
      : mode === "POSITION"
      ? { k: "Earnings (catalyst)", v: erDays != null ? `${erDays}d` : "none", need: "≤30d ok", pass: true }
      : { k: "Earnings clear", v: erDays != null ? `${erDays}d` : "none", need: ">7d", pass: erDays != null ? erDays > 7 : true }),
  ];
  const passed = checks.filter(c => c.pass).length, total = checks.length;
  const vtone = passed === total ? "gn" : passed >= total - 2 ? "amb" : "rd";
  const vlabel = passed === total ? "COMPLETE" : passed >= total - 2 ? "FORMING" : "INCOMPLETE";
  return (
    <div className="bk">
      <div className="bk-head">
        <div className="bk-head-l">
          <span className="bk-tag mono">ENTRY CHECKLIST</span>
          <span className={`bk-score kpi-tone--${vtone}`}>{passed}<span className="dim2">/{total}</span></span>
          <span className="mono dim2" style={{ fontSize: 10.5 }}>criteria met · the buy funnel, live</span>
        </div>
        <span className={`bk-verdict kpi-tone--${vtone}`}>{vlabel}</span>
      </div>
      <div className="bk-bar"><i style={{ width: `${passed / total * 100}%`, background: `var(--${vtone})` }} /></div>
      <div className="bk-rows">
        {checks.map((c, i) => (
          <div key={i} className="bk-row">
            <span className={`bk-ic bk-ic--${c.pass ? "pass" : "fail"}`}>{c.pass ? "✓" : "✕"}</span>
            <span className="bk-k">{c.k}</span>
            <span className={`bk-v kpi-tone--${c.pass ? "gn" : "rd"}`}>{c.v}</span>
            <span className="bk-need">{c.need}</span>
          </div>
        ))}
      </div>
      <div className="bk-foot mono dim2">{passed === total ? "All entry criteria met — the setup is complete." : `${total - passed} criterion${total - passed === 1 ? "" : "a"} not met — treat as a watch until they clear.`} Informational / educational only — not advice.</div>
    </div>
  );
}
window.BuyChecklist = BuyChecklist;

// per-ticker pre-mortem note — persisted to localStorage
function PreMortemNote({ symbol }) {
  const key = "premortem-" + (symbol || "x");
  const [val, setVal] = React.useState(() => { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } });
  return (
    <div className="pm-note-wrap">
      <div className="label-cap" style={{ marginBottom: 6 }}>Your pre-mortem · written before entry</div>
      <textarea className="pm-note mono" placeholder="If this trade fails, the most likely reason will be… (your own words — saved per ticker)"
        value={val} onChange={e => { setVal(e.target.value); try { localStorage.setItem(key, e.target.value); } catch (e2) {} }} />
    </div>
  );
}

// ─── OvSection — collapsible Overview section (persists open/closed) ───
function OvSection({ n, title, sub, headerStyle, defaultOpen = true, teaser, children }) {
  const key = "ovsecv5-" + n;
  const [open, setOpen] = React.useState(() => { try { const v = localStorage.getItem(key); return v == null ? defaultOpen : v === "1"; } catch (e) { return defaultOpen; } });
  React.useEffect(() => {
    const h = (e) => { if (e.detail === n - 1) setOpen(true); };
    window.addEventListener("ov-jump-open", h);
    return () => window.removeEventListener("ov-jump-open", h);
  }, [n]);
  const toggle = () => setOpen(o => { const nx = !o; try { localStorage.setItem(key, nx ? "1" : "0"); } catch (e) {} return nx; });
  return (
    <div className={`lens-section ov-sec ${open ? "is-open" : "is-closed"}`}>
      <div className="ov-sec-head" onClick={toggle} role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
        <SectionHeader n={n} title={title} sub={sub} style={headerStyle}
          right={<span className={`ov-sec-chev mono ${open ? "is-open" : ""}`}>▸</span>} />
      </div>
      {open
        ? <div className="lens-pad">{children}</div>
        : <button className="ov-sec-teaser mono" onClick={toggle}>{teaser || `Show ${(title || "").split(" · ")[0]}`} <span className="copper">· expand</span></button>}
    </div>
  );
}
window.OvSection = OvSection;

// ════════════════════════════════════════════════════════════════════
// QUANT MICRO-VISUALS — the probabilistic edge made visible (not walls of
// numbers): conviction meter, P(T1 vs stop), forward-return distribution,
// Wilson CI band. All from real ml/setupStats data.
// ════════════════════════════════════════════════════════════════════
(function () {
  const css = `
  .cm{ background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:10px; padding:11px 14px; margin-bottom:10px; }
  .cm-net{ display:flex; align-items:baseline; gap:4px; margin-bottom:8px; }
  .cm-num{ font:700 30px var(--mono); line-height:1; } .cm-of{ font-size:13px; }
  .cm-bias{ font:700 12px var(--mono); padding:2px 9px; border-radius:999px; border:1px solid color-mix(in oklab,currentColor 35%,transparent); }
  .cm-bar{ display:flex; height:10px; border-radius:6px; overflow:hidden; background:var(--glass-bg-2); }
  .cm-seg{ height:100%; } .cm-g{ background:var(--gn); } .cm-a{ background:var(--amb); } .cm-r{ background:var(--rd); }
  .cm-leg{ font-size:10px; margin-top:5px; }
  .eo-card{ background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:10px; padding:11px 14px; margin-bottom:10px; display:flex; flex-direction:column; gap:9px; }
  .eo-hd{ display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .eo-tag{ font:700 9px var(--mono); letter-spacing:.12em; color:var(--copper); border:1px solid color-mix(in oklab,var(--copper) 40%,transparent); border-radius:3px; padding:3px 8px; }
  .eo-row{ display:grid; grid-template-columns:128px 1fr 92px; align-items:center; gap:10px; }
  .eo-k{ font-size:9.5px; letter-spacing:.05em; color:var(--ink-3); }
  .eo-v{ font-size:12px; text-align:right; white-space:nowrap; }
  .eo-track{ position:relative; height:14px; background:var(--glass-bg-2); border-radius:4px; }
  .eo-split{ position:relative; display:flex; height:14px; border-radius:4px; overflow:hidden; background:var(--glass-bg-2); }
  .eo-split-g{ background:color-mix(in oklab,var(--gn) 80%,transparent); height:100%; } .eo-split-r{ background:color-mix(in oklab,var(--rd) 75%,transparent); height:100%; }
  .eo-band{ position:absolute; top:3px; height:8px; background:color-mix(in oklab,var(--copper) 35%,transparent); border-radius:3px; }
  .eo-ci{ position:absolute; top:4px; height:6px; background:color-mix(in oklab,var(--gn) 35%,transparent); border-radius:3px; }
  .eo-pt{ position:absolute; top:1px; width:2px; height:12px; background:var(--ink-1); border-radius:1px; transform:translateX(-1px); }
  .eo-zero{ position:absolute; top:0; width:1px; height:14px; background:var(--ink-3); opacity:.6; }
  .eo-be{ position:absolute; top:-2px; width:0; height:18px; border-left:1px dashed var(--amb); }
  .eo-foot{ font-size:10px; padding-top:5px; border-top:1px solid var(--glass-line); }
  .conf-cell{ position:relative; } .conf-spark{ display:block; height:4px; border-radius:2px; margin-top:4px; background:var(--glass-bg-2); position:relative; overflow:hidden; }
  .conf-spark i{ position:absolute; top:0; height:100%; }
  .sleeve-rbar{ display:inline-block; height:7px; border-radius:2px; vertical-align:middle; margin-left:6px; }
  .shp-card{ background:var(--glass-bg-1); border:1px solid var(--glass-line); border-radius:10px; padding:11px 14px; margin-bottom:10px; display:flex; flex-direction:column; gap:6px; }
  .shp-row{ display:grid; grid-template-columns:152px 1fr 50px; align-items:center; gap:10px; }
  .shp-k{ font-size:10px; color:var(--ink-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .shp-track{ position:relative; height:12px; background:var(--glass-bg-2); border-radius:3px; }
  .shp-mid{ position:absolute; left:50%; top:0; width:1px; height:12px; background:var(--ink-3); opacity:.55; }
  .shp-bar{ position:absolute; top:2px; height:8px; border-radius:2px; }
  .shp-up{ background:color-mix(in oklab,var(--gn) 72%,transparent); } .shp-dn{ background:color-mix(in oklab,var(--rd) 70%,transparent); }
  .shp-v{ font-size:11px; text-align:right; }
  .ov-conv2col{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:12px; align-items:start; }
  .ov-conv-col{ display:flex; flex-direction:column; gap:10px; min-width:0; }
  .ov-conv-coltag{ font:700 8.5px var(--mono); letter-spacing:.12em; color:var(--ink-3); margin-bottom:-2px; }
  @media (max-width:900px){ .ov-conv2col{ grid-template-columns:1fr; } }`;
  if (!document.getElementById("eo-css")) { const s = document.createElement("style"); s.id = "eo-css"; s.textContent = css; document.head.appendChild(s); }
})();
const _pc = v => Math.max(0, Math.min(100, v));
function ConvictionMeter({ cv }) {
  if (!cv) return null;
  const total = (cv.agree + cv.caution + cv.fail) || 1;
  const tone = cv.net >= 66 ? "gn" : cv.net >= 50 ? "amb" : "rd";
  return (
    <div className="cm">
      <div className="cm-net">
        <span className={`cm-num kpi-tone--${tone}`}>{cv.net}</span><span className="cm-of mono dim2">/100</span>
        <span className={`cm-bias mono kpi-tone--${cv.vtone}`} style={{ marginLeft: 10 }}>{cv.biasLabel || (window.secBias ? window.secBias(cv.verdict) : cv.verdict)}</span>
        <span className="mono dim2" style={{ marginLeft: 10, fontSize: 11 }}>conf {cv.conf}</span>
      </div>
      <div className="cm-bar">
        <div className="cm-seg cm-g" style={{ width: cv.agree / total * 100 + "%" }} title={`${cv.agree} agree`} />
        <div className="cm-seg cm-a" style={{ width: cv.caution / total * 100 + "%" }} title={`${cv.caution} caution`} />
        <div className="cm-seg cm-r" style={{ width: cv.fail / total * 100 + "%" }} title={`${cv.fail} against`} />
      </div>
      <div className="cm-leg mono"><b className="up">{cv.agree}</b> agree · <b className="warn">{cv.caution}</b> caution · <b className="dn">{cv.fail}</b> against · {cv.lenses.length} lenses</div>
    </div>
  );
}
function EdgeOdds({ ticker, mode }) {
  const ml = ticker.ml || {};
  const ss = ticker.setupStats || {};
  const dmKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "investment" : "swing";
  const dec = ticker.decisionsByMode && ticker.decisionsByMode[dmKey];
  // RICH per-mode plan → real per-horizon R:R + structural P(reach) for THIS mode
  const te = useTradeEngine(ticker.symbol, mode);
  const teRR = (te && te.t1 && typeof te.t1.r_multiple === "number") ? te.t1.r_multiple : null;
  const tePReach = (te && te.t1 && typeof te.t1.p_reach === "number") ? te.t1.p_reach : null;
  const rr = teRR != null ? teRR : ((dec && dec.rr_ratio) || ticker.rMultiple);
  const mag = ml.magnitude;
  if (ml.pT1 == null && !mag && ss.winRate == null && tePReach == null) return null;
  // hit odds
  const oddsT = (ml.pT1 != null && ml.pStop != null) ? ml.pT1 / (ml.pT1 + ml.pStop) * 100 : null;
  // distribution scale
  const lo = mag && mag.lo, mid = mag && mag.mid, hi = mag && mag.hi;
  const dMin = (lo != null) ? Math.min(lo, 0) - 1 : 0, dMax = (hi != null) ? Math.max(hi, 0) + 1 : 1, dSpan = (dMax - dMin) || 1;
  const dx = v => _pc((v - dMin) / dSpan * 100);
  // wilson CI
  const wr = ss.winRate, lb = ss.wilsonLB;
  const wUp = (wr != null && lb != null) ? Math.min(1, wr + (wr - lb)) : null;
  const be = rr ? 1 / (1 + rr) : null;
  return (
    <div className="eo-card">
      <div className="eo-hd"><span className="eo-tag mono">PROBABILISTIC EDGE</span>{ml.modelAuc != null ? <span className="mono dim2" style={{ fontSize: 10 }}>ML AUC {ml.modelAuc.toFixed(2)}{ml.modelN ? ` · n=${ml.modelN.toLocaleString()}` : ""}</span> : null}</div>
      {oddsT != null ? (
        <div className="eo-row">
          <span className="eo-k mono">P(T1 vs STOP first)</span>
          <div className="eo-split"><div className="eo-split-g" style={{ width: oddsT + "%" }} /><div className="eo-split-r" style={{ width: (100 - oddsT) + "%" }} /></div>
          <span className="eo-v mono"><b className={ml.pT1 >= ml.pStop ? "up" : "dn"}>{(ml.pT1 * 100).toFixed(0)}%</b> <span className="dim2">/ {(ml.pStop * 100).toFixed(0)}%</span></span>
        </div>
      ) : null}
      {tePReach != null ? (
        <div className="eo-row">
          <span className="eo-k mono">P(reach T1) · {mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing"}</span>
          <div className="eo-track"><div className="eo-band" style={{ left: "0%", width: _pc(tePReach * 100) + "%", background: "var(--copper)" }} /></div>
          <span className="eo-v mono copper" title="Structural target-engine probability of tagging T1 for this horizon (analog + Monte-Carlo + Bayes blend).">{(tePReach * 100).toFixed(0)}%</span>
        </div>
      ) : null}
      {lo != null && hi != null ? (
        <div className="eo-row">
          <span className="eo-k mono">10d RETURN · Q10–90</span>
          <div className="eo-track"><div className="eo-zero" style={{ left: dx(0) + "%" }} /><div className="eo-band" style={{ left: dx(lo) + "%", width: (dx(hi) - dx(lo)) + "%" }} />{mid != null ? <div className="eo-pt" style={{ left: dx(mid) + "%" }} /> : null}</div>
          <span className={`eo-v mono ${mid >= 0 ? "up" : "dn"}`}>{mid >= 0 ? "+" : ""}{mid != null ? mid.toFixed(1) : "—"}%</span>
        </div>
      ) : null}
      {wr != null && lb != null ? (
        <div className="eo-row">
          <span className="eo-k mono">WIN RATE · 95% CI</span>
          <div className="eo-track">{be != null ? <div className="eo-be" style={{ left: _pc(be * 100) + "%" }} title={`breakeven ${(be * 100).toFixed(0)}%`} /> : null}<div className="eo-ci" style={{ left: _pc(lb * 100) + "%", width: _pc((wUp - lb) * 100) + "%" }} /><div className="eo-pt" style={{ left: _pc(wr * 100) + "%" }} /></div>
          <span className={`eo-v mono ${be != null && wr > be ? "up" : "warn"}`}>{(wr * 100).toFixed(0)}% <span className="dim2">LB {(lb * 100).toFixed(0)}</span></span>
        </div>
      ) : null}
      <div className="eo-foot mono">{ml.direction != null ? <>P(up) <b className={ml.direction >= 0.5 ? "up" : "dn"}>{(ml.direction * 100).toFixed(0)}%</b> · </> : ""}ML hit-net <b className={ml.hitNet >= 0 ? "up" : "dn"}>{ml.hitNet >= 0 ? "+" : ""}{ml.hitNet}</b>{ss.pf != null ? <> · setup PF <b className={ss.pf >= 1.3 ? "up" : "warn"}>{ss.pf.toFixed(2)}</b></> : ""}{ss.n != null && ss.n < 30 ? <span className="warn"> · n&lt;30 ⚠</span> : ""}</div>
    </div>
  );
}
// humanize ML feature names for the SHAP driver chart
const SHAP_LABELS = {
  pctrank_ema50_dist: "Dist from EMA50 (%ile)", ema50_dist: "EMA50 distance", ema21_dist: "EMA21 distance", ema200_dist: "EMA200 distance",
  pctrank_dist_52w_low: "Above 52w low (%ile)", pctrank_dist_52w_high: "Below 52w high (%ile)", dist_52w_low: "52w-low distance", dist_52w_high: "52w-high distance",
  ret_63d: "63-day return", ret_21d: "21-day return", ret_5d: "5-day return", ret_252d: "1-year return",
  pctrank_rs_vs_spy_63d: "RS vs SPY 63d (%ile)", rs_vs_spy_63d: "RS vs SPY 63d", rs_rank: "RS rank",
  rsi: "RSI", rsi_14: "RSI(14)", macd: "MACD", macd_hist: "MACD histogram", adx: "ADX", rvol: "RVOL",
  atr_pct: "ATR %", obv_slope: "OBV slope", vol_zscore: "Volume z-score", bb_pctb: "Bollinger %B",
  stochrsi: "StochRSI", mfi: "MFI", cmf: "CMF", beta: "Beta", short_float: "Short float",
};
function humanShap(f) {
  if (SHAP_LABELS[f]) return SHAP_LABELS[f];
  let s = String(f || ""); const pct = /^pctrank_/.test(s); s = s.replace(/^pctrank_/, "");
  s = s.replace(/_/g, " ").replace(/\bema(\d+)\b/gi, "EMA$1").replace(/\brs\b/gi, "RS").replace(/\bspy\b/gi, "SPY").replace(/\bret\b/gi, "return").replace(/\bdist\b/gi, "distance").replace(/(\d+)d\b/g, "$1d");
  return s + (pct ? " (%ile)" : "");
}
function ShapDrivers({ ticker }) {
  const sh = ticker.ml && ticker.ml.shap;
  if (!sh || !sh.length) return null;
  const max = Math.max(...sh.map(x => Math.abs(x.shap))) || 1;
  const upN = sh.filter(x => x.shap >= 0).length;
  return (
    <div className="shp-card">
      <div className="eo-hd">
        <span className="eo-tag mono">MODEL DRIVERS · SHAP</span>
        <span className="mono dim2" style={{ fontSize: 10 }}>{upN >= 3 ? "net bullish drivers" : upN <= 1 ? "net bearish drivers" : "mixed drivers"}</span>
      </div>
      {sh.map((x, i) => {
        const v = x.shap, up = v >= 0, w = Math.abs(v) / max * 48;
        return (
          <div key={i} className="shp-row">
            <span className="shp-k mono" title={x.feature}>{humanShap(x.feature)}</span>
            <div className="shp-track">
              <div className="shp-mid" />
              <div className={`shp-bar ${up ? "shp-up" : "shp-dn"}`} style={up ? { left: "50%", width: w + "%" } : { right: "50%", width: w + "%" }} />
            </div>
            <span className={`shp-v mono ${up ? "up" : "dn"}`}>{up ? "+" : ""}{v.toFixed(2)}</span>
          </div>
        );
      })}
      <div className="eo-foot mono dim2">Green pushes the model up · red down · bar = |impact|. Top SHAP feature attributions for {ticker.symbol}.</div>
    </div>
  );
}

function LensOverview({ ticker: t0, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const ticker = (window.modeAdjust ? window.modeAdjust(t0, mode) : t0);
  // structural per-mode plan for the section-level surfaces (INVALIDATION stop +
  // pre-mortem stop) so they quote the SAME stop as the hero ladder.
  const teOv = useTradeEngine(ticker.symbol, mode);
  const Lov = teLevelsOf(teOv, ticker);

  // route a lens name → lens id, used by the hero dissent pills + confluence grid
  const routeLens = (name) => {
    const map = { "Overview": "overview", "AI Edge": "mledge", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Track Rec.": "mledge", "Plan": "plan", "Earnings": "earnings", "Options": "options", "Insider": "tape", "Tape": "tape", "Chart": "chart", "Portfolio": "tape" };
    if (window.__setLens && map[name]) window.__setLens(map[name]);
  };

  const isInvest = mode === "INVESTMENT";
  return (
    <div className="lens lens--ov">

      {/* ── 1 · THE CALL + THE TRADE · one canonical answer block ── */}
      {window.DecisionHero && <DecisionHero ticker={ticker} mode={mode} heroStyle={heroStyle} sizeCat={sizeCat} onLens={routeLens} />}

      {/* ── INVALIDATION · the kill-switch sits WITH the trade (risk-first, P3/P15) ── */}
      {(() => {
        const L = Lov;
        const er = ticker.earnings && ticker.earnings.days;
        const rs = ticker.rsRank;
        return (
          <div className="ov-inval mono" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 11.5, padding: "7px 12px", margin: "0 0 12px", background: "color-mix(in oklab, var(--rd) 8%, var(--glass-bg-2))", border: "1px solid color-mix(in oklab, var(--rd) 30%, var(--glass-line))", borderRadius: 8 }}>
            <span className="label-cap dn" style={{ fontSize: 9 }}>INVALIDATION</span>
            {L.valid ? <span>Exit on a close below <b className="dn">${L.stop.toFixed(2)}</b> · hard stop</span> : <span className="dim2">no complete plan — wait for levels</span>}
            {er != null && er >= 0 ? <><span className="dim2">·</span><span>earnings <b className={er <= 7 ? "dn" : "warn"}>T−{er}d</b> binary risk</span></> : null}
            {rs != null && rs < 50 ? <><span className="dim2">·</span><span className="warn">RS {Math.round(rs)} — leadership weak</span></> : null}
          </div>
        );
      })()}

      {/* ── 2 · ARE WE CLEARED? · the buy funnel + rule-engine audit ── */}
      <OvSection n={2} title="Are We Cleared? · Entry Readiness"
        sub="the buy funnel as ✓/✗ · plus the full rule-engine audit" headerStyle={headerStyle} defaultOpen={true}>
        <BuyChecklist ticker={ticker} mode={mode} />
        {(window.__tier ?? 4) >= 3 && (
          <details className="ov-more">
            <summary className="ov-more-sum mono">Show the full rule-engine audit · how {(() => { const u = window.__BV && window.__BV.market && window.__BV.market.funnel && window.__BV.market.funnel.universe; return u ? u.toLocaleString() + " names" : "the universe"; })()} ranked → {window.secBias ? window.secBias((window.compositeVerdict ? window.compositeVerdict(ticker, mode).verdict : "BUY")) : "Bullish"} · PRO+</summary>
            <div className="ov-more-body"><GateCascade ticker={ticker} /></div>
          </details>
        )}
      </OvSection>

      {/* ── 3 · CONVICTION · the 4 agreement views, consolidated ── */}
      <OvSection n={3} title="Conviction · Do The Signals Agree?"
        sub="3 horizons · regime fit · which engines flagged it · every lens' read"
        headerStyle={headerStyle} defaultOpen={true}
        teaser="conviction meter · probabilistic edge · horizons · lens confluence">
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(() => { const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null; return cv ? <ConvictionMeter cv={cv} /> : null; })()}
          <div className="ov-conv2col">
            {/* LEFT · the model's quantified edge */}
            <div className="ov-conv-col">
              <div className="ov-conv-coltag mono">▼ THE MODEL · QUANTIFIED EDGE</div>
              <EdgeOdds ticker={ticker} mode={mode} />
              <ShapDrivers ticker={ticker} />
            </div>
            {/* RIGHT · do independent views agree */}
            <div className="ov-conv-col">
              <div className="ov-conv-coltag mono">▼ INDEPENDENT VIEWS · AGREEMENT</div>
              <HorizonStrip ticker={ticker} mode={mode} onMode={(m) => window.__setMode && window.__setMode(m)} />
              <RegimeFit ticker={ticker} mode={mode} />
              <SurfacedBy ticker={ticker} />
              <ConfluenceHeatmap ticker={ticker} mode={mode} />
            </div>
          </div>
        </div>
      </OvSection>

      {/* ── 4 · THE CASE · bull vs bear ── */}
      <OvSection n={4} title="The Case · Bull vs Bear"
        sub="why it's a buy — and what would make it wrong" headerStyle={headerStyle} defaultOpen={true}>
        <ThesisCard ticker={ticker} mode={mode} />
      </OvSection>

      {/* ── 5 · WHAT WOULD BREAK IT · risk-first pre-mortem + book stress ── */}
      <OvSection n={5} title="What Would Break It · Risk"
        sub="pre-mortem triggers · your note · book stress under shocks"
        headerStyle={headerStyle} defaultOpen={true}
        teaser="pre-mortem triggers · your note · β-scaled stress">
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr)", gap: 12 }}>
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">▼ What would make this wrong · pre-mortem</div>
            <div className="premortem">
              {(() => {
                const L = Lov;
                const reg = String((window.__BV && window.__BV.market && window.__BV.market.regime4) || (ticker._scan && ticker._scan._raw && ticker._scan._raw.regime4) || "the current regime").replace(/_/g, " ");
                const rs = ticker.rsRank;
                const er = ticker.earnings && ticker.earnings.days;
                const stopV = (L && L.stop) || ticker.stop || 0;
                const rows = [];
                rows.push(["1", `Closes below the stop $${stopV.toFixed(2)} — hard invalidation, exit on the close.`, "HARD", "rd"]);
                rows.push(["2", `Regime flips out of ${reg} — the setup's backdrop is gone (re-check the regime gate).`, "MACRO", "amb"]);
                if (rs != null) rows.push(["3", `RS rank falls below 40 (now ${Math.round(rs)}) — relative leadership lost.`, "MOMENTUM", rs < 50 ? "rd" : "amb"]);
                else rows.push(["3", "Sector relative strength rolls over — relative leadership lost.", "MOMENTUM", "amb"]);
                if (er != null && er >= 0 && er <= 30) rows.push(["4", `Earnings in ${er}d — binary event; trim or exit before the print unless the thesis confirms.`, "CATALYST", "rd"]);
                else if (isInvest) rows.push(["4", "ROE / operating margins deteriorate, or price exceeds fair value — margin of safety gone.", "FUNDAMENTAL", "amb"]);
                else rows.push(["4", "Distribution-day cluster (heavy down-volume on no news) — institutions exiting.", "FUNDAMENTAL", "rd"]);
                return rows.map(([n, t, tag, tone]) => (
                  <div key={n} className="premortem-row"><span className="pm-num mono">{n}</span><span className="pm-text">{t}</span><Pill tone={tone} small>{tag}</Pill></div>
                ));
              })()}
            </div>
            <PreMortemNote symbol={ticker.symbol} />
          </div>
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">▼ Book stress · β-scaled shocks</div>
            <StressSnapshot ticker={ticker} />
          </div>
        </div>
      </OvSection>

      {/* ── 6 · CONTEXT · company / valuation / catalysts (open for INVEST) ── */}
      <OvSection n={6} title="Company & Catalysts · Context"
        sub="who they are · valuation · earnings · what's hitting the tape"
        headerStyle={headerStyle} defaultOpen={isInvest}
        teaser="Profile · real valuation & quality · next earnings · live catalysts">
        <div className="ov-co2x2">
          <CompanySnapshot ticker={ticker} />
          <CompanyValuation ticker={ticker} />
          <NewsCatalysts ticker={ticker} />
        </div>
      </OvSection>

      {/* ── 7 · TRACK RECORD · WHAT CHANGED · MACRO (housekeeping, collapsed) ── */}
      <OvSection n={7} title="Track Record · What Changed · Macro"
        sub="sleeve mechanism + last trades · change vs prior scan · the macro backdrop"
        headerStyle={headerStyle} defaultOpen={false}
        teaser="sleeve edge + last 5 · 24h change · regime / rates / credit">
        <div className="ov-honest-3col">
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">⚙ Why the edge exists · mechanism</div>
            <SleeveAttribution ticker={ticker} />
          </div>
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">↗ What changed · vs prior scan</div>
            <WhatChanged ticker={ticker} />
          </div>
          <div className="ov-honest-block">
            <div className="ov-honest-sub label-cap">▼ Macro backdrop</div>
            <MacroDrill />
          </div>
        </div>
      </OvSection>
    </div>
  );
}

function ConfluenceHeatmap({ ticker, mode }) {
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  if (!cv || !cv.lenses) return <div className="conf-grid"><span className="mono dim2" style={{ padding: 8 }}>Lens confluence unavailable for this name.</span></div>;
  const lensId = { "Overview": "overview", "AI Edge": "mledge", "Technicals": "technicals", "Patterns": "patterns", "SMC": "smc", "Value": "investment", "Risk": "risk", "Track Rec.": "mledge", "Plan": "plan", "Earnings": "earnings", "Options": "options", "Insider": "tape" };
  const cells = cv.lenses.slice().sort((a, b) => b.v - a.v);
  const dis = cv.fail >= 3 ? ["elevated", "warn", "mixed signals — verify the dissent before acting"]
    : cv.fail >= 1 ? ["some", "amb", "mostly aligned with a few cautions"]
    : ["low", "up", "clean confluence across the lenses"];
  return (
    <div className="conf-grid">
      {cells.map((c, i) => {
        const tone = c.tone || (c.v >= 62 ? "gn" : c.v >= 46 ? "amb" : "rd");
        const go = () => { if (window.__setLens && lensId[c.k]) window.__setLens(lensId[c.k]); };
        return (
          <button key={i} className={`conf-cell conf-${tone}`} onClick={go} title={`open ${c.k} · weight ${(c.w * 100).toFixed(0)}%`}>
            <div className="conf-lens mono">{c.k}</div>
            <div className={`conf-v mono kpi-tone--${tone}`}>{c.v}</div>
            <div className="conf-spark"><i style={{ left: Math.min(c.v, 50) + "%", width: Math.abs(c.v - 50) + "%", background: c.v >= 50 ? "var(--gn)" : "var(--rd)" }} /></div>
            <div className="conf-note mono dim2">{c.why}</div>
          </button>
        );
      })}
      <div className="conf-summary">
        <Pill tone="gn" dot>{cv.agree} PASS</Pill>
        <Pill tone="amb" small>{cv.caution} CAUTION</Pill>
        <Pill tone="rd" small>{cv.fail} FAIL</Pill>
        <span className="mono dim2" style={{ marginLeft: 12 }}>
          Disagreement: <b className={dis[1] === "warn" ? "warn" : dis[1] === "amb" ? "warn" : "up"}>{dis[0]}</b> — {dis[2]}.
        </span>
      </div>
    </div>
  );
}

const SLEEVE_MECH = {
  "Breakout Expansion": <>Post-base breakout on volume expansion. <b className="copper">Alpha:</b> supply absorption before markup. <b className="copper">Works when</b> accumulation is observable pre-breakout (VCP / 52wk).</>,
  "Trend Continuation": <>Pullback to value (EMA / support) in an uptrend. <b className="copper">Alpha:</b> institutional re-add at the mean. <b className="copper">Works in</b> trending / choppy-up regimes.</>,
  "Impulse Catalyst": <>Post-catalyst drift (PEAD / UOA / gap). <b className="copper">Alpha:</b> under-reaction to fresh information. <b className="copper">Works in</b> the 1–5d window after the print.</>,
  "Special Situation": <>Insider cluster / float rotation / squeeze. <b className="copper">Alpha:</b> informed buying or forced covering. <b className="copper">Works</b> across regimes.</>,
};
function SleeveAttribution({ ticker }) {
  const fam = ticker.setupFamily || "—";
  const ss = ticker.setupStats || {};
  const SL = window.SigLedger;
  // real recent trades of the same / closest setup, from the forward-scored ledger
  const recent = React.useMemo(() => {
    if (!SL || !SL.SIGNALS || !SL.SIGNALS.length) return [];
    const fkey = String(fam).toLowerCase();
    const toks = fkey.split(/\s+/).filter(w => w.length > 3);
    const match = (st) => {
      st = String(st || "").toLowerCase();
      if (toks.some(t => st.includes(t))) return true;
      if (/breakout/.test(fkey) && /breakout|vcp|52wk|pivot|rs new/.test(st)) return true;
      if (/(continuation|trend)/.test(fkey) && /(continuation|ema|pullback|bounce|week)/.test(st)) return true;
      if (/(impulse|catalyst)/.test(fkey) && /(gap|pead|breakout|pivot)/.test(st)) return true;
      if (/(special|situation)/.test(fkey) && /(insider|cluster|squeeze)/.test(st)) return true;
      return false;
    };
    return SL.SIGNALS.filter(s => match(s.setup)).map(s => {
      const ret = s.ret || {}; let r = null;
      for (const h of ["W2", "W1", "D5", "D3", "W4", "M1"]) if (ret[h] != null) { r = ret[h]; break; }
      if (r == null) { const ks = Object.keys(ret).filter(k => ret[k] != null); if (ks.length) r = ret[ks[ks.length - 1]]; }
      return { sym: s.sym, age: s.age, date: s.date, ret: r != null ? (s.dir === "short" ? -r : r) : null };
    }).filter(x => x.ret != null).sort((a, b) => a.age - b.age).slice(0, 5);
  }, [fam, SL && SL.real, SL && SL.SIGNALS && SL.SIGNALS.length]);
  const pf = (window.__BV && window.__BV.portfolio) || null;
  const heldInFam = pf && pf.positions ? pf.positions.filter(p => String(p.setup_type || "").toLowerCase().includes(String(fam).toLowerCase().split(" ")[0])).length : 0;
  return (
    <div className="sleeve">
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">SLEEVE</span>
        <div><Pill tone="copper">{String(fam).toUpperCase()}</Pill> <span className="mono dim2">· {ss.n != null ? `n=${ss.n} sample` : "no ledger sample"}{heldInFam ? ` · ${heldInFam} held in book` : ""}</span></div>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">MECHANISM</span>
        <span className="mono">{SLEEVE_MECH[fam] || <>Edge from a {String(fam).toLowerCase()} setup — see the Plan lens for the full mechanism + falsification.</>}</span>
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">WILSON</span>
        {ss.n != null && ss.winRate != null && ss.wilsonLB != null
          ? <WilsonPill n={ss.n} winRate={ss.winRate} lb={ss.wilsonLB} />
          : <span className="mono dim2">no per-setup track record yet (n=0)</span>}
      </div>
      <div className="sleeve-row">
        <span className="sleeve-lbl mono">LAST 5</span>
        {recent.length ? (
          <div className="sleeve-recent">
            {recent.map((s, i) => {
              const tone = s.ret >= 1 ? "gn" : s.ret <= -1 ? "rd" : "amb";
              return (
                <div key={i} className="sleeve-rec">
                  <span className="mono"><b>{s.sym}</b></span>
                  <span className="mono dim2">{s.age}d ago</span>
                  <span className={`mono kpi-tone--${tone}`}>{s.ret >= 0 ? "+" : ""}{s.ret.toFixed(1)}%</span>
                  <span className="sleeve-rbar" style={{ width: Math.max(3, Math.min(42, Math.abs(s.ret) * 3)) + "px", background: s.ret >= 0 ? "var(--gn)" : "var(--rd)" }} />
                </div>
              );
            })}
          </div>
        ) : <span className="mono dim2">no recent same-setup trades in the ledger</span>}
      </div>
    </div>
  );
}

function GateCascade({ ticker }) {
  const ge = (ticker && ticker.gatesEvaluated) || null;
  if (!ge || !ge.length) return <div className="gates"><div className="gates-summary mono dim2">No rule-engine audit trail recorded for this name.</div></div>;
  const LABELS = {
    system_circuit_breaker: "System circuit breaker", macro_blackout: "Macro event blackout",
    liquidity: "Liquidity · spread / ADV", earnings_blackout: "Earnings blackout window",
    regime_gate: "Regime gate", fund_adequacy: "Fundamental adequacy",
    entry_quality: "Entry quality · value zone", decision_state: "Decision state",
    tail_loss_filter: "Tail-loss filter · tier_zero", setup_score_band: "Setup score band",
    rr_floor: "R:R floor", score_floor: "Composite score floor", signal_filter: "Signal whitelist",
  };
  const pass = ge.filter(g => g.passed).length, total = ge.length;
  return (
    <div className="gates">
      {ge.map((g, i) => {
        const tone = g.passed ? "gn" : "rd";
        return (
          <div key={i} className={`gate-row gate-${tone}`} title={g.reason || ""}>
            <span className="gate-n mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="gate-mark mono">{g.passed ? "✓" : "✕"}</span>
            <span className="gate-lbl">{LABELS[g.name] || String(g.name || "gate").replace(/_/g, " ")}</span>
            <span className={`gate-result mono kpi-tone--${tone}`} style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.passed ? "PASS" : (g.reason || "BLOCKED")}</span>
          </div>
        );
      })}
      <div className="gates-summary mono">
        <b className={pass === total ? "up" : "warn"}>{pass} of {total} gate{total === 1 ? "" : "s"} pass{pass < total ? ` · ${total - pass} blocked` : ""}.</b>
        {ticker.rejectReason ? <> Blocking reason: <b className="dn">{ticker.rejectReason}</b>.</> : " Clear to act per the plan."}
      </div>
    </div>
  );
}

function MacroDrill() {
  const c = (window.__BV && window.__BV.critical) || null;
  const M = (window.__BV && window.__BV.market) || null;
  const mac = (c && c.macro_signals) || {};
  const bf = (c && c.bonds_forex) || {};
  const rg = (c && c.regime) || {};
  const n = v => (typeof v === "number" && isFinite(v)) ? v : null;
  const vix = n(rg.vix_current) != null ? n(rg.vix_current) : (rg.vix && n(rg.vix.vix_current));
  const tiles = [];
  if (M) tiles.push({ label: "Regime · multi-factor", value: `${M.regimeLabel} · ${M.regimeTrend}`, tone: M.regimeOn ? "gn" : "rd", sub: M.maxSize != null ? `max size ${M.maxSize}%` : "regime gate" });
  if (vix != null) tiles.push({ label: "VIX", value: vix.toFixed(1), tone: vix < 18 ? "gn" : vix < 25 ? "amb" : "rd", sub: vix < 18 ? "low-vol · risk-on" : vix < 25 ? "elevated" : "stressed" });
  if (M && M.breadthPct != null) tiles.push({ label: "Breadth >50-DMA", value: Math.round(M.breadthPct) + "%", tone: M.breadthPct >= 55 ? "gn" : M.breadthPct >= 40 ? "amb" : "rd", sub: "participation" });
  if (mac.credit && mac.credit.state) tiles.push({ label: "HY credit (HYG)", value: mac.credit.state, tone: mac.credit.state === "healthy" ? "gn" : "amb", sub: mac.hyg && mac.hyg.chg5d != null ? `5d ${mac.hyg.chg5d >= 0 ? "+" : ""}${mac.hyg.chg5d}%` : "risk appetite" });
  if (mac.dxy && mac.dxy.chg5d != null) tiles.push({ label: "Dollar (UUP)", value: `${mac.dxy.chg5d >= 0 ? "+" : ""}${mac.dxy.chg5d}% 5d`, tone: mac.dxy.trend === "rising" ? "amb" : "gn", sub: mac.dxy.trend || "fx" });
  if (bf["TYX.INDX"] && n(bf["TYX.INDX"].price) != null) tiles.push({ label: "US 30Y yield", value: n(bf["TYX.INDX"].price).toFixed(2) + "%", tone: "ink", sub: "duration" });
  if (!tiles.length) return <span className="mono dim2">Macro context unavailable.</span>;
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: `repeat(${Math.min(3, tiles.length)}, 1fr)` }}>
      {tiles.map((t, i) => <KpiTile key={i} {...t} />)}
    </div>
  );
}

function WhatChanged({ ticker }) {
  const [hist, setHist] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !ticker.symbol) { setHist([]); return; }
    let alive = true;
    BV.get("/api/ticker-history?t=" + encodeURIComponent(ticker.symbol) + "&n=30")
      .then(d => { if (alive) setHist((d && d.history) || []); })
      .catch(() => { if (alive) setHist([]); });
    return () => { alive = false; };
  }, [ticker.symbol]);
  if (hist === null) return <div className="wc"><span className="mono dim2">Loading change history…</span></div>;
  // one entry per date (keep the last of the day), diff the two most recent dates
  const byDate = {}; (hist || []).forEach(h => { if (h.date) byDate[h.date] = h; });
  const dates = Object.keys(byDate).sort();
  const cur = dates.length ? byDate[dates[dates.length - 1]] : null;
  const prev = dates.length > 1 ? byDate[dates[dates.length - 2]] : null;
  if (!cur || !prev) return <div className="wc"><span className="mono dim2">First appearance — no prior scan to diff against.</span></div>;
  const n = v => (typeof v === "number" && isFinite(v)) ? v : null;
  const vtone = v => /BUY/i.test(v) ? "gn" : /AVOID|SELL|SHORT/i.test(v) ? "rd" : "amb";
  const items = [];
  const numRow = (label, o, nw, fmt, betterUp = true) => {
    o = n(o); nw = n(nw); if (o == null || nw == null || o === nw) return;
    const up = nw > o, good = betterUp ? up : !up;
    items.push({ label, old: fmt(o), now: fmt(nw), tone: good ? "gn" : "rd", note: (up ? "+" : "") + fmt(nw - o) });
  };
  if (prev.verdict !== cur.verdict) items.push({ label: "Verdict", old: prev.verdict, now: cur.verdict, tone: vtone(cur.verdict), note: "changed" });
  numRow("Composite score", prev.score, cur.score, v => Math.round(v));
  numRow("RS rank", prev.rs_rank, cur.rs_rank, v => Math.round(v));
  numRow("R:R", prev.rr_ratio, cur.rr_ratio, v => v.toFixed(2));
  if (prev.regime4 !== cur.regime4) items.push({ label: "Regime", old: String(prev.regime4 || "—").replace(/_/g, " "), now: String(cur.regime4 || "—").replace(/_/g, " "), tone: "amb", note: "shifted" });
  if (prev.setup_type !== cur.setup_type) items.push({ label: "Setup", old: prev.setup_type || "—", now: cur.setup_type || "—", tone: "amb", note: "re-classified" });
  if (!prev.has_catalyst && cur.has_catalyst) items.push({ label: "Catalyst", old: "none", now: "active", tone: "gn", note: "appeared" });
  if (!items.length) return <div className="wc"><span className="mono dim2">No material change vs {prev.date} — score/verdict/RS/regime steady.</span></div>;
  return (
    <div className="wc">
      <div className="wc-row" style={{ opacity: .7 }}><span className="mono dim2" style={{ fontSize: 10 }}>{prev.date} → {cur.date}</span></div>
      {items.map((it, i) => (
        <div key={i} className="wc-row">
          <span className="mono wc-lbl">{it.label}</span>
          <span className="mono dim2 wc-old">{it.old}</span>
          <span className="mono dim">→</span>
          <span className={`mono wc-new kpi-tone--${it.tone}`}><b>{it.now}</b></span>
          <span className="mono dim wc-note">{it.note}</span>
        </div>
      ))}
    </div>
  );
}

function StressSnapshot({ ticker }) {
  const NAV = (window.__BV && window.__BV.nav) || 100000;
  const beta = ticker.beta != null ? ticker.beta : 1.0;
  const posPct = 0.05;                         // 5%-NAV notional position reference
  const pos = NAV * posPct;
  const scen = [
    { name: "Market −3%", mkt: -3 },
    { name: "Market −5%", mkt: -5 },
    { name: "VIX spike (−8%)", mkt: -8 },
    { name: "Risk-off (−10%)", mkt: -10 },
  ];
  const tiles = scen.map(s => {
    const move = s.mkt * beta;                 // stock move ≈ β × market move
    const pnl = pos * move / 100;
    const pct = pnl / NAV * 100;
    return { label: s.name, value: `${pnl < 0 ? "−$" : "$"}${Math.abs(Math.round(pnl)).toLocaleString()}`, tone: pct <= -0.6 ? "rd" : pct <= -0.3 ? "amb" : "ink", sub: `${pct.toFixed(2)}% NAV · β${beta.toFixed(2)}` };
  });
  return (
    <div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        {tiles.map((t, i) => <KpiTile key={i} {...t} />)}
      </div>
      <div className="mono dim2" style={{ fontSize: 10, marginTop: 4 }}>β-scaled P&L on a {(posPct * 100)}%-NAV (${Math.round(pos).toLocaleString()}) position vs real NAV ${Math.round(NAV).toLocaleString()}. Illustrative market shocks; β is real.</div>
    </div>
  );
}

// Override the in-file LensOverview from detail-panel.jsx
window.LensOverview = LensOverview;

// ─── Desk Read — how a 20-yr quant scans it in 2 seconds ────────
// ─── Company Snapshot · Quant Read ──────────────────────────
function CompanySnapshot({ ticker }) {
  return (
    <React.Fragment>
      <div className="cs-card cs-card--who">
        <div className="cs-card-hdr">
          <div className="label-cap">WHO · {ticker.symbol}</div>
          <span className="mono dim2">{ticker.exchange} · {ticker.sector} · {ticker.industry}</span>
        </div>
        <div className="cs-name mono">{ticker.name}</div>
        <div className="cs-blurb mono dim">
          {ticker.description ? (ticker.description.length > 230 ? ticker.description.slice(0, 230) + "…" : ticker.description)
            : `${ticker.name} — ${ticker.sector || "—"}${ticker.industry ? " · " + ticker.industry : ""}.`}
        </div>
        <div className="cs-meta">
          {ticker.mcap ? <span className="cs-chip mono"><span className="dim2">mcap</span> <b>${(ticker.mcap / 1e9).toFixed(2)}B</b></span> : null}
          {ticker.beta != null ? <span className="cs-chip mono"><span className="dim2">β</span> <b>{ticker.beta.toFixed(2)}</b></span> : null}
          {ticker.sharesFloat != null ? <span className="cs-chip mono"><span className="dim2">float</span> <b>{(ticker.sharesFloat / 1e6).toFixed(1)}M</b></span> : null}
          {ticker.shortFloat != null ? <span className="cs-chip mono"><span className="dim2">short</span> <b className={ticker.shortFloat >= 15 ? "dn" : ""}>{ticker.shortFloat.toFixed(1)}%</b></span> : null}
          {ticker.insiderOwn != null ? <span className="cs-chip mono"><span className="dim2">insider own</span> <b>{ticker.insiderOwn.toFixed(1)}%</b></span> : null}
          {ticker.instOwn != null ? <span className="cs-chip mono"><span className="dim2">inst own</span> <b>{ticker.instOwn.toFixed(0)}%</b></span> : null}
          {ticker.avgVol ? <span className="cs-chip mono"><span className="dim2">ADV</span> <b>{(ticker.avgVol / 1e6).toFixed(2)}M sh</b></span> : null}
          {ticker.dvol ? <span className="cs-chip mono"><span className="dim2">$ ADV</span> <b>${(ticker.dvol / 1e6).toFixed(0)}M</b></span> : null}
          {ticker.spread != null ? <span className="cs-chip mono"><span className="dim2">spread</span> <b className={ticker.spread <= 0.1 ? "up" : ticker.spread >= 0.5 ? "dn" : ""}>{ticker.spread.toFixed(2)}%</b></span> : null}
        </div>
      </div>

      {(() => {
        const eb = ((window.__BV && window.__BV.earningsBeat) || []).find(e => String(e.ticker || "").split(".")[0].toUpperCase() === ticker.symbol);
        const eh = ticker.earningsHistory || [];
        const days = ticker.earnings && ticker.earnings.days;
        const future = eh.filter(x => x.epsActual == null && x.reportDate).sort((a, b) => String(a.reportDate).localeCompare(String(b.reportDate)));
        const nextDate = (eb && eb.report_date) || (future[0] && future[0].reportDate) || null;
        const bd = (eb && eb.breakdown) || {};
        const hist = bd.historical || {};
        const imp = bd.implied_move && bd.implied_move.implied_move_pct;
        const past = eh.filter(x => typeof x.surprisePercent === "number").slice(-8);
        const eps = future[0] && future[0].epsEstimate;
        return (
        <div className="cs-card cs-card--er">
          <div className="cs-card-hdr">
            <div className="label-cap">EARNINGS · NEXT CATALYST</div>
            {days != null ? <Pill tone={days <= 7 ? "rd" : "amb"} small>T−{days}d</Pill> : <Pill tone="ink" small>—</Pill>}
          </div>
          <div className="cs-er-big">
            <div className="cs-er-num mono">{days != null ? days : "—"}</div>
            <div className="cs-er-meta">
              <div className="mono dim2">days to print</div>
              <div className="mono">{nextDate ? <b>{nextDate}</b> : <span className="dim2">date TBD</span>}{eb && eb.before_after ? " · " + (/before/i.test(eb.before_after) ? "BMO" : "AMC") : ""}</div>
            </div>
          </div>
          <div className="cs-er-tiles">
            <div className="cs-er-tile"><span className="label-cap">Beat score</span><span className="mono"><b>{eb && eb.beat_score != null ? Math.round(eb.beat_score) : "—"}</b></span></div>
            <div className="cs-er-tile"><span className="label-cap">Beat rate</span><span className="mono up"><b>{hist.rate != null ? Math.round(hist.rate) + "%" : "—"}</b></span></div>
            <div className="cs-er-tile"><span className="label-cap">EPS est.</span><span className="mono"><b>{eps != null ? "$" + (+eps).toFixed(2) : "—"}</b></span></div>
            <div className="cs-er-tile"><span className="label-cap">Implied move</span><span className="mono warn"><b>{imp != null ? "±" + (+imp).toFixed(1) + "%" : "—"}</b></span></div>
          </div>
          {past.length ? (
            <div className="cs-er-history mono">
              <span className="dim2">recent surprises:</span>
              {past.map((q, i) => <span key={i} className={q.surprisePercent >= 0 ? "up" : "dn"}>{q.surprisePercent >= 0 ? "▲" : "▼"}{Math.abs(q.surprisePercent).toFixed(1)}</span>)}
            </div>
          ) : null}
        </div>
        );
      })()}
    </React.Fragment>
  );
}

// Valuation card pulled out so §4 can show it beside News in a 2-col row.
function CompanyValuation({ ticker }) {
  const n = v => (typeof v === "number" && isFinite(v)) ? v : null;
  const pct = v => v == null ? "—" : (v * 100).toFixed(1) + "%";
  const rat = (v, dp = 1) => v == null ? "—" : v.toFixed(dp);
  const roe = n(ticker.roe), opm = n(ticker.opMargin), pm = n(ticker.profitMargin), roa = n(ticker.roa);
  const Tile = ({ label, val, tone }) => (
    <div className="cs-val-tile"><span className="label-cap">{label}</span><span className={`mono ${tone || ""}`}><b>{val}</b></span></div>
  );
  return (
      <div className="cs-card cs-card--val">
        <div className="cs-card-hdr">
          <div className="label-cap">VALUATION · QUALITY</div>
          <span className="mono dim2" style={{ fontSize: 10 }}>real · EODHD fundamentals</span>
        </div>
        <div className="cs-val-row">
          <Tile label="P/E TTM" val={ticker.pe != null ? ticker.pe.toFixed(1) : "—"} />
          <Tile label="Fwd P/E" val={ticker.fwdPe != null ? ticker.fwdPe.toFixed(1) : "—"} />
          <Tile label="P/S TTM" val={rat(n(ticker.ps), 2)} />
          <Tile label="EV/EBITDA" val={rat(n(ticker.evEbitda), 1)} />
        </div>
        <div className="cs-val-row">
          <Tile label="ROE TTM" val={pct(roe)} tone={roe != null ? (roe >= 0.15 ? "up" : roe < 0 ? "dn" : "") : ""} />
          <Tile label="ROA TTM" val={pct(roa)} tone={roa != null ? (roa >= 0.08 ? "up" : roa < 0 ? "dn" : "") : ""} />
          <Tile label="Op margin" val={pct(opm)} tone={opm != null ? (opm >= 0.15 ? "up" : opm < 0 ? "dn" : "") : ""} />
          <Tile label="Profit margin" val={pct(pm)} tone={pm != null ? (pm >= 0.10 ? "up" : pm < 0 ? "dn" : "") : ""} />
        </div>
      </div>
  );
}
window.CompanyValuation = CompanyValuation;
