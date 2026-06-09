// surface-signal.jsx — Signal Scanner landing surface (full column set, mirrors kairos scanner)

const { useState: useStateSS, useMemo: useMemoSS } = React;

// BULLVEDA: live scan rows (real /api/universe) when available; mock seed only offline.
const SS_UNIVERSE = (window.__BV && window.__BV.ready) ? window.__BV.scanRows().map(r => (window.__BV.timeQuick ? Object.assign(r, window.__BV.timeQuick(r) || {}) : r)) : (() => {
  const seed = WATCHLIST.concat(
    HEATMAP.filter(h => !WATCHLIST.find(w => w.sym === h[0]))
      .slice(0, 16)
      .map(([sym, sector, mcap, chg]) => ({
        sym, name: sector + " Co.", sector, mcap, chg,
        price: 20 + (sym.charCodeAt(0) % 200) + (sym.charCodeAt(1) || 0) % 20,
        score: Math.max(28, Math.min(94, 50 + Math.round(chg * 5))),
        verdict: chg > 1.5 ? "BUY" : chg < -1 ? "AVOID" : "WATCH",
        setup: chg > 1.5 ? "Breakout Expansion" : chg > 0 ? "Pullback" : "Distribution",
      }))
  );
  return seed.map(t => {
    const code = (t.sym?.charCodeAt(0) || 65) + (t.sym?.charCodeAt(1) || 65);
    const atr = ((code % 7) + 1) * 0.18;
    const rvol = (0.6 + (code % 15) / 10);
    const stop = (t.price * 0.92).toFixed(2);
    const entry = (t.price * 1.0).toFixed(2);
    const t1 = (t.price * 1.18).toFixed(2);
    const mtfStates = ["up","up","up","flat","down"];
    const mtf = [0,1,2,3].map(i => {
      const idx = (code + i * 3) % mtfStates.length;
      return mtfStates[idx];
    });
    const regimeBase = (t.score >= 70 ? 65 : t.score >= 55 ? 52 : 42);
    const mechPool = [
      "Supply absorbed at base · vol-dry pullback",
      "Demand zone reclaim · institutional bid",
      "Breakout retest holding pivot",
      "VCP contraction · 5th tightening",
      "Gap-and-go · catalyst-driven",
      "Liquidity sweep + reversal off lows",
      "Distribution · failing breakout",
      "Range compression pre-expansion",
    ];
    const tfsnVals = [0,1,2,3].map(i => (code + i * 5) % 3); // 0 fail,1 neutral,2 pass
    // ── Factor grades (A–F) + EDGE composite — quantitative analytics, informational only ──
    const _GR = (n) => n >= 82 ? "A" : n >= 66 ? "B" : n >= 46 ? "C" : n >= 30 ? "D" : "F";
    const _cl = (n) => Math.max(4, Math.min(99, Math.round(n)));
    const gRaw = {
      t: _cl(40 + (t.score - 50) * 1.0 + (code % 18)),                       // Trend
      m: _cl(38 + (t.score - 50) * 1.15 + (code % 16)),                      // Momentum
      s: _cl(36 + (t.score - 50) * 1.3 + (code % 20)),                       // Setup
      r: _cl(30 + ((1 + (t.score - 50) / 30) - 1) * 38 + (code % 12)),       // Risk/Reward
      v: _cl(92 - (t.score - 50) * 0.85 + (code % 22) - 8),                  // Value
      g: _cl(44 + (t.chg || 0) * 4.2 + (code % 26)),                         // Growth
    };
    // EDGE = weighted composite. Swing weighting: Setup/Trend/Momentum heaviest.
    const _eW = { s: 1.4, t: 1.3, m: 1.2, r: 1.0, v: 0.6, g: 0.6 };
    const edgePct = _cl(Object.keys(_eW).reduce((a, k) => a + gRaw[k] * _eW[k], 0) /
      Object.values(_eW).reduce((a, b) => a + b, 0));
    const grades = { t: _GR(gRaw.t), m: _GR(gRaw.m), s: _GR(gRaw.s), r: _GR(gRaw.r), v: _GR(gRaw.v), g: _GR(gRaw.g) };
    return {
      ...t,
      tfsn: tfsnVals,
      tfsnScore: tfsnVals.reduce((a, b) => a + b, 0),
      mtfUp: mtf.filter(m => m === "up").length,
      sigCount: code % 3 === 0 ? 2 : 1,
      sqRank: code % 5 === 0 ? 2 : (code % 5 === 1 || code % 5 === 2) ? 1 : 0,
      ready: [t.score >= 66, (1 + (t.score - 50) / 30) >= 2, rvol >= 1.3, Math.max(28, Math.min(72, t.score * 0.7 + 5)) >= 45, Math.max(20, Math.min(98, 40 + (t.score - 50) * 1.2)) >= 60, (4 + (code % 60)) > 14].filter(Boolean).length,
      mechanism: t.verdict === "AVOID" ? mechPool[6] : mechPool[code % mechPool.length],
      tier: t.score >= 75 ? "T1" : t.score >= 60 ? "T2" : "T3",
      eq: t.score >= 75 ? "EXTENDED" : t.score >= 60 ? "MISSED" : "NEUTRAL",
      cat: t.score >= 75 ? "T1" : "T2",
      stop, entry, t1plan: t1,
      atr: atr.toFixed(2),
      rr: (1 + (t.score - 50) / 30).toFixed(1),
      rvol: rvol.toFixed(2),
      rs: Math.max(20, Math.min(98, 40 + (t.score - 50) * 1.2)).toFixed(0),
      wlb: Math.max(28, Math.min(72, t.score * 0.7 + 5)).toFixed(0),
      n: 180 + (code % 8) * 50,
      pf: (1.2 + (t.score - 50) / 50).toFixed(1),
      iv: 30 + (code % 24),
      sent: ((code % 7) - 3),
      er: 4 + (code % 60),
      signals: code % 3 === 0 ? ["🔥","⚡"] : code % 3 === 1 ? ["⚡"] : ["🔥"],
      mtf,
      regWR: regimeBase + (code % 12),
      aiEdge: +(((t.score - 58) / 90) + (((code % 7) - 3)) * 0.02).toFixed(2),
      grades,
      gradesRaw: gRaw,
      edge: _GR(edgePct),
      edgePct,
      vgm: { v: grades.v, g: grades.g, m: grades.m },
      adx: Math.max(8, Math.min(62, Math.round(14 + (t.score - 50) * 0.9 + (code % 14)))),
      squeeze: (code % 5 === 0) ? "FIRED" : (code % 5 === 1 || code % 5 === 2) ? "ON" : "OFF",
      beta: +(0.7 + (code % 16) / 10).toFixed(2),
      dvol: (t.price || 50) * (1e6 + (code % 40) * 7e5) * rvol,
      si: +(((code % 28) + (t.verdict === "AVOID" ? 8 : 0))).toFixed(1),
      dtc: +(1 + (code % 9) * 0.6).toFixed(1),
      spread: (code % 11) + 2,
      off52: -(((code % 24) + (t.score >= 75 ? 1 : 6))),
      vwap: +((((t.chg || 0) * 0.6) + ((code % 7) - 3) * 0.4)).toFixed(2),
      r1m: +((((t.score - 50) * 0.6) + ((code % 20) - 8))).toFixed(1),
      r3m: +((((t.score - 50) * 1.4) + ((code % 30) - 12))).toFixed(1),
      tgt: Math.max(-8, Math.round(((t.score - 45) * 0.5) + (code % 14))),
      newsAge: (code % 23) + 1,
      insUsd: (() => {
        const m = code % 5;
        if (m === 0) return 0;
        const sign = m <= 2 ? 1 : -1;
        return +(sign * ((code % 40) * 0.1 + 0.3)).toFixed(1);
      })(),
    };
  });
})();

const SS_TABS = [
  { id: "scanner",   label: "SCANNER",   count: SS_UNIVERSE.length },
  { id: "consensus", label: "CONSENSUS", count: 0, tone: "gn" },
  { id: "top-picks", label: "TOP PICKS", count: SS_UNIVERSE.filter(t => t.score >= 75).length, tone: "copper" },
  { id: "fresh",     label: "FRESH",     count: 3, tone: "cy" },
  { id: "earnings",  label: "EARNINGS",  count: SS_UNIVERSE.filter(t => t.er <= 14).length, tone: "amb" },
  { id: "surges",    label: "SURGES",    count: SS_UNIVERSE.filter(t => parseFloat(t.rvol) >= 1.5).length, tone: "gn" },
  { id: "ai-edge",   label: "AI EDGE",   count: SS_UNIVERSE.filter(t => t.aiEdge >= 0.05).length, tone: "violet" },
  { id: "killed",    label: "EXCLUDED",  count: SS_UNIVERSE.filter(t => t.verdict === "AVOID").length, tone: "rd" },
];

const SS_PILLS = [  { id: "top20",    label: "★ TOP 20% SCORE" },
  { id: "breakout", label: "🔥 BREAKOUT" },
  { id: "t1",       label: "⚡ T1 CATALYST" },
  { id: "er14",     label: "📅 ER ≤14D" },
  { id: "insider",  label: "💰 INSIDER" },
  { id: "watch",    label: "⭐ MY WATCHLIST" },
  { id: "rvol",     label: "🔥 RVOL ≥1.5×" },
];

// SIGNALS column vocabulary — each flag is derived live from the row's data,
// with a hover tooltip; the legend strip above the table documents them.
const SS_SIGNALS = [
  { icon: "★",  id: "top",      label: "Top score",     desc: "Top-tier composite score (≥ 75)",        test: t => t.score >= 75 },
  { icon: "🔥", id: "breakout", label: "Breakout · RVOL", desc: "Breaking out on elevated volume (RVOL ≥ 1.5×)", test: t => parseFloat(t.rvol) >= 1.5 },
  { icon: "⚡", id: "catalyst", label: "Fresh catalyst", desc: "News catalyst in the last 6 hours",       test: t => t.newsAge <= 6 },
  { icon: "🧲", id: "squeeze",  label: "Squeeze",        desc: "Volatility squeeze on or just fired",     test: t => t.squeeze === "ON" || t.squeeze === "FIRED" },
  { icon: "📅", id: "er",       label: "Earnings ≤ 14d", desc: "Reports earnings within 14 days",         test: t => t.er <= 14 },
  { icon: "💰", id: "insider",  label: "Insider buying", desc: "Net insider buying over the last 90 days", test: t => t.insUsd > 0 },
];
function ssSignals(t) { return SS_SIGNALS.filter(s => s.test(t)); }

// ── Column manager — every toggleable column with its DOM nth-child index ──
// (cols 1=checkbox, 2=Ticker, 44=Spark are always on). Hidden columns are
// collapsed via injected nth-child CSS so the table cells never change.
const SS_COLS = [
  { id: "name",      label: "Name",                nth: 3,  grp: "Identity" },
  { id: "sector",    label: "Sector",              nth: 4,  grp: "Identity" },
  { id: "tfsn",      label: "T.F.S.N pillars",     nth: 5,  grp: "Verdict" },
  { id: "mechanism", label: "Mechanism (thesis)",  nth: 6,  grp: "Verdict" },
  { id: "score",     label: "Score",               nth: 7,  grp: "Verdict" },
  { id: "verdict",   label: "Bias",                nth: 8,  grp: "Verdict" },
  { id: "ready",     label: "Ready",               nth: 9,  grp: "Verdict" },
  { id: "tier",      label: "Tier",                nth: 10, grp: "Verdict" },
  { id: "setup",     label: "Setup",               nth: 11, grp: "Verdict" },
  { id: "eq",        label: "Entry quality (EQ)",  nth: 12, grp: "Verdict" },
  { id: "cat",       label: "Catalyst tier (CAT)", nth: 13, grp: "Verdict" },
  { id: "edge",      label: "Edge · grades",       nth: 14, grp: "Verdict" },
  { id: "price",     label: "Price",               nth: 15, grp: "Price" },
  { id: "chg",       label: "% change",            nth: 16, grp: "Price" },
  { id: "off52",     label: "% from 52w high",     nth: 17, grp: "Price" },
  { id: "vwap",      label: "vs VWAP",             nth: 18, grp: "Price" },
  { id: "rr",        label: "R : R",               nth: 19, grp: "Plan" },
  { id: "plan",      label: "Plan (stop/entry/T1)",nth: 20, grp: "Plan" },
  { id: "atr",       label: "ATR",                 nth: 21, grp: "Risk · liquidity" },
  { id: "rvol",      label: "RVOL",                nth: 22, grp: "Volume" },
  { id: "adx",       label: "ADX",                 nth: 23, grp: "Volume" },
  { id: "sq",        label: "Squeeze",             nth: 24, grp: "Volume" },
  { id: "beta",      label: "Beta",                nth: 25, grp: "Risk · liquidity" },
  { id: "dvol",      label: "$ volume",            nth: 26, grp: "Risk · liquidity" },
  { id: "si",        label: "Short interest",      nth: 27, grp: "Risk · liquidity" },
  { id: "spread",    label: "Spread",              nth: 28, grp: "Risk · liquidity" },
  { id: "mtf",       label: "MTF alignment",       nth: 29, grp: "Strength" },
  { id: "regWR",     label: "Regime win rate",     nth: 30, grp: "Strength" },
  { id: "rs",        label: "RS rank",             nth: 31, grp: "Strength" },
  { id: "r1m",       label: "1-month return",      nth: 32, grp: "Strength" },
  { id: "r3m",       label: "3-month return",      nth: 33, grp: "Strength" },
  { id: "wlb",       label: "Win % (Wilson LB)",   nth: 34, grp: "Backtest" },
  { id: "n",         label: "Sample size (N)",     nth: 35, grp: "Backtest" },
  { id: "pf",        label: "Profit factor",       nth: 36, grp: "Backtest" },
  { id: "iv",        label: "IV rank",             nth: 37, grp: "Catalyst" },
  { id: "sent",      label: "Sentiment",           nth: 38, grp: "Catalyst" },
  { id: "tgt",       label: "Target upside",       nth: 39, grp: "Catalyst" },
  { id: "newsAge",   label: "News age",            nth: 40, grp: "Catalyst" },
  { id: "insUsd",    label: "Insider $",           nth: 41, grp: "Catalyst" },
  { id: "er",        label: "Earnings (days)",     nth: 42, grp: "Catalyst" },
  { id: "signals",   label: "Signals",             nth: 43, grp: "Verdict" },
  { id: "aiEdge",    label: "AI Edge (ML)",        nth: 44, grp: "Verdict" },
  { id: "time",      label: "Time → T1 (ETA)",     nth: 46, grp: "Plan" },
];
const SS_PRESETS = {
  Essentials: ["sector","score","verdict","setup","edge","price","chg","rr","plan","time","rvol","mtf","wlb","er","signals"],
  Momentum:   ["sector","score","verdict","setup","price","chg","off52","rvol","adx","mtf","rs","r1m","r3m","signals"],
  "Risk · liquidity": ["sector","score","verdict","price","rr","plan","atr","beta","dvol","si","spread","iv","signals"],
  Catalyst:   ["sector","score","verdict","price","chg","er","newsAge","insUsd","iv","sent","tgt","signals"],
  Everything: SS_COLS.map(c => c.id),
};
const SS_COLS_KEY = "kairos.ss2.cols.v1";
const SS_DEFAULT_KEY = "kairos.ss2.cols.default.v1";
function ssLoadDefault() {
  if (window.UserPrefs) { const v = window.UserPrefs.get("ss2.cols.default", null); if (Array.isArray(v) && v.length) return v; }
  try { const v = JSON.parse(localStorage.getItem(SS_DEFAULT_KEY)); if (Array.isArray(v) && v.length) return v; } catch (e) {}
  return null;
}
function ssLoadCols() {
  if (window.UserPrefs) { const v = window.UserPrefs.get("ss2.cols", null); if (Array.isArray(v) && v.length) return v; }
  try { const v = JSON.parse(localStorage.getItem(SS_COLS_KEY)); if (Array.isArray(v) && v.length) return v; } catch (e) {}
  const d = ssLoadDefault();
  if (d) return d;
  return SS_PRESETS.Essentials.slice();
}

const VGM_LABEL = { V: "Value", G: "Growth", M: "Momentum" };

// EDGE factor grade system — quantitative analytics (informational only, not advice)
const GRADE_FACTORS = [
  ["t", "TRD", "Trend"],
  ["m", "MOM", "Momentum"],
  ["s", "SET", "Setup"],
  ["r", "R:R", "Risk/Reward"],
  ["v", "VAL", "Value"],
  ["g", "GRO", "Growth"],
];
const gradeTone = (ltr) => (ltr === "A" || ltr === "B") ? "g" : ltr === "C" ? "a" : "r";

// compact dollar-volume formatter ($1.2B / $340M / $52K)
const ssFmtBig = (n) => {
  const v = +n;
  if (!isFinite(v)) return "—";
  if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(0) + "M";
  if (v >= 1e3) return "$" + (v / 1e3).toFixed(0) + "K";
  return "$" + v.toFixed(0);
};

// Append-only scan ledger — snapshots every screened name once per day to
// localStorage so the universe is auditable & backtestable. In production this
// writes the append-only signal_ledger table (see HANDOVER_track_record.md).
const SCAN_LEDGER_KEY = "kairos.scan_ledger.v1";
function logScanLedger(rows) {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const log = JSON.parse(localStorage.getItem(SCAN_LEDGER_KEY) || "[]");
    const seen = new Set(log.map(e => e.d + "|" + e.sym));
    let added = 0;
    rows.forEach(t => {
      const id = today + "|" + t.sym;
      if (seen.has(id)) return;
      log.push({ d: today, ts: Date.now(), sym: t.sym, name: t.name, sector: t.sector, score: t.score,
        edge: t.edge, edgePct: t.edgePct, ready: t.ready, verdict: t.verdict, rr: t.rr, rvol: t.rvol,
        rs: t.rs, wlb: t.wlb, adx: t.adx, si: t.si, iv: t.iv, er: t.er, price: t.price, chg: t.chg,
        vG: t.grades && t.grades.v, gG: t.grades && t.grades.g, mG: t.grades && t.grades.m });
      seen.add(id); added++;
    });
    if (added) localStorage.setItem(SCAN_LEDGER_KEY, JSON.stringify(log.slice(-8000)));
    return log.length;
  } catch (e) { return 0; }
}
function exportScanLedger() {
  try {
    const log = JSON.parse(localStorage.getItem(SCAN_LEDGER_KEY) || "[]");
    if (!log.length) return;
    const cols = ["d","ts","sym","name","sector","score","edge","edgePct","ready","verdict","rr","rvol","rs","wlb","adx","si","iv","er","price","chg","vG","gG","mG"];
    const esc = v => { v = v == null ? "" : String(v); v = v.replace(/"/g, '""'); return /[",\n]/.test(v) ? `"${v}"` : v; };
    const csv = [cols.join(","), ...log.map(e => cols.map(c => esc(e[c])).join(","))].join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `scan-ledger-${log.length}.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
  } catch (e) {}
}

function SurfaceSignalScanner({ onTicker, onSurface }) {
  const [tab, setTab] = useStateSS("scanner");
  const [pills, setPills] = useStateSS({});
  const [sel, setSel] = useStateSS("ARCM");
  const [side, setSide] = useStateSS(() => window.__scanFilter || "ALL");
  React.useEffect(() => {
    if (window.__scanFilter) {
      setSide(window.__scanFilter);
      setPills({});
      setTab(window.__scanFilter === "ALL" ? "scanner" : "scanner");
      window.__scanFilter = null;
    }
  }, []);
  const [sort, setSort] = useStateSS({ col: "sym", dir: 1 });
  const [selected, setSelected] = useStateSS(() => new Set());
  const [secF, setSecF] = useStateSS("all");
  const [setupF, setSetupF] = useStateSS("all");
  const [sortSel, setSortSel] = useStateSS("Ticker A→Z");
  const [q, setQ] = useStateSS("");
  const [wlTick, setWlTick] = useStateSS(0);
  React.useEffect(() => {
    const h = () => setWlTick(x => x + 1);
    window.addEventListener("watchlist-change", h);
    return () => window.removeEventListener("watchlist-change", h);
  }, []);
  const [ledgerN, setLedgerN] = useStateSS(0);
  React.useEffect(() => { setLedgerN(logScanLedger(SS_UNIVERSE)); }, []);

  // column manager
  const [cols, setCols] = useStateSS(() => ssLoadCols());
  const [colsOpen, setColsOpen] = useStateSS(false);
  const colsRef = React.useRef(null);
  React.useEffect(() => {
    const h = e => { if (colsRef.current && !colsRef.current.contains(e.target)) setColsOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const visCols = useMemoSS(() => new Set(cols), [cols]);
  const persistCols = (next) => {
    setCols(next);
    if (window.UserPrefs) window.UserPrefs.set("ss2.cols", next);
    else { try { localStorage.setItem(SS_COLS_KEY, JSON.stringify(next)); } catch (e) {} }
  };
  // cross-device: pick up column-layout changes synced from another device
  React.useEffect(() => {
    if (!window.UserPrefs) return;
    return window.UserPrefs.subscribe("ss2.cols", (v) => { if (Array.isArray(v) && v.length) setCols(v); });
  }, []);
  const toggleCol = (id) => persistCols(visCols.has(id) ? cols.filter(c => c !== id) : [...cols, id]);
  const applyPreset = (name) => persistCols(SS_PRESETS[name].slice());
  const hiddenCols = SS_COLS.filter(c => !(visCols.has(c.id) || (tab === "ai-edge" && c.id === "aiEdge")));
  const activePreset = Object.keys(SS_PRESETS).find(p => {
    const a = SS_PRESETS[p].slice().sort().join(","); return a === cols.slice().sort().join(",");
  });
  // personal saved layout ("My View")
  const [myDefault, setMyDefault] = useStateSS(() => ssLoadDefault());
  const [savedFlash, setSavedFlash] = useStateSS(false);
  const sameCols = (a) => a && a.slice().sort().join(",") === cols.slice().sort().join(",");
  const saveMyDefault = () => {
    if (window.UserPrefs) window.UserPrefs.set("ss2.cols.default", cols);
    else { try { localStorage.setItem(SS_DEFAULT_KEY, JSON.stringify(cols)); } catch (e) {} }
    setMyDefault(cols.slice());
    setSavedFlash(true); setTimeout(() => setSavedFlash(false), 1600);
  };
  const applyMyDefault = () => { if (myDefault) persistCols(myDefault.slice()); };
  const colGroups = useMemoSS(() => {
    const g = {}; SS_COLS.forEach(c => { (g[c.grp] = g[c.grp] || []).push(c); }); return g;
  }, []);
  // wire the Sort dropdown → sort state
  const SORT_MAP = { "Ticker A→Z": { col: "sym", dir: 1 }, "EDGE ↓": { col: "edgePct", dir: -1 }, "Score ↓": { col: "score", dir: -1 }, "R:R ↓": { col: "rr", dir: -1 }, "RVOL ↓": { col: "rvol", dir: -1 } };
  const onSortSel = (label) => { setSortSel(label); if (SORT_MAP[label]) setSort(SORT_MAP[label]); };
  const sectorOpts = useMemoSS(() => ["all", ...Array.from(new Set(SS_UNIVERSE.map(r => r.sector))).sort()], []);
  const setupOpts = useMemoSS(() => ["all", ...Array.from(new Set(SS_UNIVERSE.map(r => r.setup).filter(Boolean))).sort()], []);
  const toggleSel = (sym) => setSelected(s => {
    const n = new Set(s);
    if (n.has(sym)) n.delete(sym); else n.add(sym);
    return n;
  });
  const clearSel = () => setSelected(new Set());
  const [flash, setFlash] = useStateSS("");
  React.useEffect(() => { if (!flash) return; const t = setTimeout(() => setFlash(""), 1800); return () => clearTimeout(t); }, [flash]);
  const selRows = () => SS_UNIVERSE.filter(t => selected.has(t.sym));
  const addSelWatch = () => {
    const ws = window.WatchStore; if (!ws) return;
    const n = selected.size;
    selRows().forEach(t => ws.add({ sym: t.sym, name: t.name, sector: t.sector, price: t.price, chg: t.chg, score: t.score, verdict: t.verdict, setup: t.setup }));
    clearSel(); setFlash(`added ${n} to watchlist`);
  };
  const exportCSV = () => {
    const rs = selected.size ? selRows() : rows;
    const cols = ["sym","name","sector","score","verdict","tier","setup","price","chg","rr","rvol","rs","wlb","pf","iv","er","aiEdge"];
    const esc = (v) => { v = v == null ? "" : String(v); v = v.replace(/"/g, '""'); return /[",\n]/.test(v) ? `"${v}"` : v; };
    const flat = (t) => ({ ...t, edge: t.edge, edgePct: t.edgePct,
      gTrend: t.grades?.t, gMomentum: t.grades?.m, gSetup: t.grades?.s, gRiskReward: t.grades?.r, gValue: t.grades?.v, gGrowth: t.grades?.g });
    const outCols = [...cols.slice(0, 7), "edge", "edgePct", "gTrend", "gMomentum", "gSetup", "gRiskReward", "gValue", "gGrowth", ...cols.slice(7),
      "off52", "vwap", "adx", "squeeze", "beta", "dvol", "si", "dtc", "spread", "r1m", "r3m", "tgt", "newsAge", "insUsd"];
    const csv = [outCols.join(","), ...rs.map(t => { const f = flat(t); return outCols.map(c => esc(f[c])).join(","); })].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `signal-scan-${rs.length}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
    setFlash(`exported ${rs.length} rows`);
  };

  const rows = useMemoSS(() => {
    let r = SS_UNIVERSE;
    if (tab === "top-picks") r = r.filter(t => t.score >= 75);
    if (tab === "earnings") r = r.filter(t => t.er <= 14);
    if (tab === "surges") r = r.filter(t => parseFloat(t.rvol) >= 1.5);
    if (tab === "killed") r = r.filter(t => t.verdict === "AVOID");
    if (tab === "fresh") r = r.slice(0, 3);
    if (tab === "ai-edge") r = r.filter(t => t.aiEdge >= 0.05);
    if (side === "BUY")   r = r.filter(t => t.verdict === "BUY");
    if (side === "WATCH") r = r.filter(t => t.verdict === "WATCH");
    if (side === "SHORT") r = r.filter(t => t.verdict === "AVOID");
    if (pills.top20)   r = r.filter(t => t.score >= 70);
    if (pills.rvol)    r = r.filter(t => parseFloat(t.rvol) >= 1.5);
    if (pills.er14)    r = r.filter(t => t.er <= 14);
    if (pills.insider) r = r.filter(t => t.sent > 0);
    if (pills.t1)      r = r.filter(t => t.tier === "T1");
    if (pills.breakout)r = r.filter(t => (t.setup || "").toLowerCase().includes("break"));
    if (pills.watch)   r = r.filter(t => window.WatchStore && window.WatchStore.has(t.sym));
    if (secF !== "all") r = r.filter(t => t.sector === secF);
    if (setupF !== "all") r = r.filter(t => t.setup === setupF);
    if (q.trim()) { const s = q.trim().toLowerCase(); r = r.filter(t => (t.sym + " " + (t.name || "")).toLowerCase().includes(s)); }
    r = [...r].sort((a, b) => {
      const av = a[sort.col], bv = b[sort.col];
      const aN = parseFloat(av), bN = parseFloat(bv);
      if (!isNaN(aN) && !isNaN(bN)) return (aN - bN) * sort.dir;
      return String(av).localeCompare(String(bv)) * sort.dir;
    });
    if (tab === "ai-edge") r = [...r].sort((a, b) => b.aiEdge - a.aiEdge); // rank by ML edge
    return r;
  }, [tab, pills, side, sort, secF, setupF, q, wlTick]);

  const consensusCount = useMemoSS(() => {
    const c = window.buildConsensus ? window.buildConsensus() : { rows: [] };
    return c.rows.filter(r => r.count >= 2).length;
  }, []);

  return (
    <div className="surface ss-surface ss2-surface">
      <div className="ss2-tabs">
        {SS_TABS.map(t => (
          <button key={t.id} className={`ss2-tab ${tab === t.id ? "is-on" : ""}`} onClick={() => setTab(t.id)}>
            <span className="ss2-tab-l">{t.label}</span>
            <span className={`ss2-tab-c mono ${t.tone ? `ss2-c--${t.tone}` : ""}`}>{t.id === "consensus" ? consensusCount : t.count}</span>
          </button>
        ))}
      </div>

      {tab === "consensus" ? (
        <div className="ss2-consensus">
          <div className="ss2-cns-intro mono dim2">
            Names surfaced by more than one of the <b className="copper">6 engines + scanner</b> — ranked by how many agree. Click a row to open the ticker, a dot to open that engine.
          </div>
          <ConsensusPanel onTicker={onTicker} onSurface={onSurface} />
        </div>
      ) : (
      <React.Fragment>
      <div className="ss2-pills">
        {SS_PILLS.map(p => (
          <button key={p.id} className={`ss2-pill ${pills[p.id] ? "is-on" : ""}`}
                  onClick={() => setPills(s => ({ ...s, [p.id]: !s[p.id] }))}>
            {p.label}
          </button>
        ))}
        <button className="ss2-reset mono"
                onClick={() => { setPills({}); setTab("scanner"); setSide("ALL"); }}
                title="Clear all filters">↺ RESET</button>
      </div>

      <div className="ss2-toolbar">
        <span className="ss2-count mono"><b className="copper">{rows.length}</b> <span className="dim2">picks</span></span>

        <span className="ss2-tdiv" />

        <div className="ss2-side" title="Directional bias">
          {["BUY","WATCH","SHORT","ALL"].map(s => (
            <button key={s} className={`ss2-side-btn ss2-side--${s.toLowerCase()} ${side === s ? "is-on" : ""}`}
                    onClick={() => setSide(s)}>{s === "ALL" ? "ALL" : secBias(s)}</button>
          ))}
        </div>

        <span className="ss2-tdiv" />

        <label className="ss2-field">
          <span className="ss2-field-l mono">SORT</span>
          <select className="ss2-sel mono" value={sortSel} onChange={e => onSortSel(e.target.value)}>
            {["Ticker A→Z","EDGE ↓","Score ↓","R:R ↓","RVOL ↓"].map((o, i) => <option key={i} value={o}>{o}</option>)}
          </select>
        </label>
        <label className="ss2-field">
          <span className="ss2-field-l mono">SECTOR</span>
          <select className="ss2-sel mono" value={secF} onChange={e=>setSecF(e.target.value)}>
            {sectorOpts.map((s, i) => <option key={`${s}-${i}`} value={s}>{s==="all"?"All":s}</option>)}
          </select>
        </label>
        <label className="ss2-field">
          <span className="ss2-field-l mono">SETUP</span>
          <select className="ss2-sel mono" value={setupF} onChange={e=>setSetupF(e.target.value)}>
            {setupOpts.map((s, i) => <option key={`${s}-${i}`} value={s}>{s==="all"?"All":s}</option>)}
          </select>
        </label>
        {(secF!=="all"||setupF!=="all") && <button className="ss2-clear mono" onClick={()=>{setSecF("all");setSetupF("all");}}>✕ clear</button>}

        <div className="ss2-tbar-right">
          <div className="ss2-search-wrap">
            <input className="ss2-search mono" placeholder="⌕ search ticker / name…" value={q} onChange={e => setQ(e.target.value)} />
            {q && <button className="ss2-search-x" onClick={() => setQ("")}>✕</button>}
          </div>
          <span className="ss2-tdiv" />
          <span className="ss2-ledger mono dim2" title="Append-only scan ledger (localStorage) — every name snapshotted daily for backtest + audit">⛁ {ledgerN.toLocaleString()}</span>
          <button className="ss2-clear mono" onClick={exportScanLedger} title="Export the full scan ledger as CSV">⤓ CSV</button>
          <div className="ss2-colmgr" ref={colsRef}>
            <button className={`ss2-clear ss2-colbtn mono ${colsOpen ? "is-on" : ""}`} onClick={() => setColsOpen(o => !o)} title="Show / hide columns">⚙ Columns · {cols.length}</button>
            {colsOpen && (
            <div className="ss2-colpanel">
              <div className="ss2-colpanel-h">
                <span className="mono dim2">PRESETS</span>
                <div className="ss2-presets">
                  {myDefault && (
                    <button className={`ss2-preset ss2-preset--mine mono ${sameCols(myDefault) ? "is-on" : ""}`} onClick={applyMyDefault} title="Apply your saved column layout">★ My View</button>
                  )}
                  {Object.keys(SS_PRESETS).map(p => (
                    <button key={p} className={`ss2-preset mono ${activePreset === p ? "is-on" : ""}`} onClick={() => applyPreset(p)}>{p}</button>
                  ))}
                </div>
              </div>
              <div className="ss2-colgroups">
                {Object.entries(colGroups).map(([grp, items]) => (
                  <div key={grp} className="ss2-colgroup">
                    <div className="ss2-colgroup-h mono dim2">{grp}</div>
                    {items.map(c => (
                      <label key={c.id} className="ss2-colrow mono">
                        <input type="checkbox" checked={visCols.has(c.id)} onChange={() => toggleCol(c.id)} />
                        <span>{c.label}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
              <div className="ss2-colpanel-f">
                <button className="ss2-savedef mono" onClick={saveMyDefault} title="Remember this column layout as your personal default on this device">
                  {savedFlash ? "✓ Saved" : "★ Save current as My View"}
                </button>
                <span className="mono dim2">{cols.length} shown · saved on this device</span>
              </div>
            </div>
          )}
          </div>
        </div>
      </div>

      {hiddenCols.length > 0 && (
        <style dangerouslySetInnerHTML={{ __html: hiddenCols.map(c => `.ss2-tbl tr > :nth-child(${c.nth})`).join(",") + "{display:none}" }} />
      )}

      <div className="ss2-legend mono">
        <span className="ss2-legend-l dim2">SIGNALS</span>
        {SS_SIGNALS.map(s => (
          <span key={s.id} className="ss2-leg" title={s.desc}>
            <span className="ss2-leg-i">{s.icon}</span>
            <span className="ss2-leg-t">{s.label}</span>
          </span>
        ))}
      </div>

      {tab === "ai-edge" && (
        <div className="ss2-tab-note mono">
          Ranked by the <b className="violet">ML ensemble's forward edge</b> — the model's expected risk-adjusted excess return. Showing names with edge ≥ <b>+0.05</b> (see the <b>AI EDGE</b> column). Open <b>ML Predictions</b> for the full per-name forecast.
        </div>
      )}

      <div className="ss2-tbl-wrap">
        <table className="dtable ss2-tbl">
          <thead>
            <tr>
              <th>
                <input type="checkbox"
                  checked={rows.length > 0 && selected.size === rows.length}
                  onChange={(e) => {
                    if (e.target.checked) setSelected(new Set(rows.map(r => r.sym)));
                    else clearSel();
                  }}
                  onClick={(e) => e.stopPropagation()} />
              </th>
              <Th col="sym" sort={sort} onClick={setSort}>TICKER</Th>
              <Th col="name" sort={sort} onClick={setSort}>NAME</Th>
              <Th col="sector" sort={sort} onClick={setSort}>SECTOR</Th>
              <Th col="tfsnScore" sort={sort} onClick={setSort}>T.F.S.N</Th>
              <Th col="mechanism" sort={sort} onClick={setSort}>MECHANISM</Th>
              <Th col="score" sort={sort} onClick={setSort} r>SCORE</Th>
              <Th col="verdict" sort={sort} onClick={setSort}>BIAS</Th>
              <Th col="ready" sort={sort} onClick={setSort} r>READY</Th>
              <Th col="tier" sort={sort} onClick={setSort}>TIER</Th>
              <Th col="setup" sort={sort} onClick={setSort}>SETUP</Th>
              <Th col="eq" sort={sort} onClick={setSort}>EQ</Th>
              <Th col="cat" sort={sort} onClick={setSort}>CAT</Th>
              <Th col="edgePct" sort={sort} onClick={setSort}>EDGE · GRADES</Th>
              <Th col="price" sort={sort} onClick={setSort} r>PRICE</Th>
              <Th col="chg" sort={sort} onClick={setSort} r>%CHG</Th>
              <Th col="off52" sort={sort} onClick={setSort} r>%52WH</Th>
              <Th col="vwap" sort={sort} onClick={setSort} r>vsVWAP</Th>
              <Th col="rr" sort={sort} onClick={setSort} r>R:R</Th>
              <Th col="entry" sort={sort} onClick={setSort}>PLAN</Th>
              <Th col="atr" sort={sort} onClick={setSort} r>ATR</Th>
              <Th col="rvol" sort={sort} onClick={setSort} r>RVOL</Th>
              <Th col="adx" sort={sort} onClick={setSort} r>ADX</Th>
              <Th col="sqRank" sort={sort} onClick={setSort}>SQ</Th>
              <Th col="beta" sort={sort} onClick={setSort} r>BETA</Th>
              <Th col="dvol" sort={sort} onClick={setSort} r>$VOL</Th>
              <Th col="si" sort={sort} onClick={setSort} r>SI%</Th>
              <Th col="spread" sort={sort} onClick={setSort} r>SPRD</Th>
              <Th col="mtfUp" sort={sort} onClick={setSort}>MTF · 1H·4H·1D·1W</Th>
              <Th col="regWR" sort={sort} onClick={setSort} r>REG WR</Th>
              <Th col="rs" sort={sort} onClick={setSort} r>RS</Th>
              <Th col="r1m" sort={sort} onClick={setSort} r>1M</Th>
              <Th col="r3m" sort={sort} onClick={setSort} r>3M</Th>
              <Th col="wlb" sort={sort} onClick={setSort} r>W% LB</Th>
              <Th col="n" sort={sort} onClick={setSort} r>N</Th>
              <Th col="pf" sort={sort} onClick={setSort} r>PF</Th>
              <Th col="iv" sort={sort} onClick={setSort} r>IV%</Th>
              <Th col="sent" sort={sort} onClick={setSort} r>SENT</Th>
              <Th col="tgt" sort={sort} onClick={setSort} r>TGT↑</Th>
              <Th col="newsAge" sort={sort} onClick={setSort} r>NEWS</Th>
              <Th col="insUsd" sort={sort} onClick={setSort} r>INS$</Th>
              <Th col="er" sort={sort} onClick={setSort} r>ER</Th>
              <Th col="sigCount" sort={sort} onClick={setSort}>SIGNALS</Th>
              <Th col="aiEdge" sort={sort} onClick={setSort} r>AI EDGE</Th>
              <Th col="chg" sort={sort} onClick={setSort}>SPARK</Th>
              <Th col="taMedT1" sort={sort} onClick={setSort} r>TIME→T1</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={t.sym + i} onClick={() => onTicker(t.sym)}>
                <td className="ss2-chk"><input type="checkbox"
                  checked={selected.has(t.sym)}
                  onChange={() => toggleSel(t.sym)}
                  onClick={(e) => e.stopPropagation()} /></td>
                <td className="mono ss2-sym"><span className="ss2-star">★</span><b>{t.sym}</b></td>
                <td className="mono dim">{t.name}</td>
                <td className="dim2 mono">{t.sector}</td>
                <td className="mono dim"><span className="ss2-tfsn">{(t.tfsn||[]).map((v,k)=>(
                  <span key={k} className={`ss2-tfsn-dot ss2-tfsn--${v===2?"pass":v===1?"neut":"fail"}`} title={["Tech","Fund","SMC","News"][k]} />
                ))}</span></td>
                <td className="mono dim2">{t.mechanism}</td>
                <td className="r"><span className={`ss2-score ss2-score--${t.score >= 75 ? "gn" : t.score >= 60 ? "amb" : "rd"}`}>{t.score}</span></td>
                <td><Pill tone={secBiasTone(t.verdict)} small>{secBias(t.verdict)}</Pill></td>
                <td className="r">{(() => {
                  const n = t.ready;
                  const tn = n >= 6 ? "gn" : n >= 4 ? "amb" : "rd";
                  return <span className={`ss2-ready ss2-ready--${tn}`} title={`${n} of 6 entry criteria met`}>{n}/6</span>;
                })()}</td>
                <td><span className={`ss2-tier ss2-tier--${t.tier.toLowerCase()}`}>{t.tier}</span></td>
                <td className="mono dim">{t.setup}</td>
                <td><span className={`ss2-eq ss2-eq--${t.eq === "EXTENDED" ? "amb" : t.eq === "MISSED" ? "rd" : "ink"}`}>{t.eq}</span></td>
                <td><span className="ss2-cat mono">{t.cat}</span></td>
                <td>
                  <span className="ss2-edge" title="EDGE · composite factor score — quantitative analytics, informational only (not a recommendation)">
                    <span className={`ss2-medal ss2-medal--${gradeTone(t.edge)}`} style={{ "--deg": (t.edgePct * 3.6) + "deg" }}>{t.edge}</span>
                    <span className="ss2-gstrip">
                      {GRADE_FACTORS.map(([k, lbl, full]) => (
                        <span key={k} className="ss2-gs" title={`${full} · grade ${t.grades[k]}`}>
                          <span className="ss2-gs-k">{lbl}</span>
                          <span className={`ss2-gs-v g-${t.grades[k].toLowerCase()}`}>{t.grades[k]}</span>
                        </span>
                      ))}
                    </span>
                  </span>
                </td>
                <td className="r mono tabular">{t.price != null && isFinite(t.price) && t.price > 0 ? "$" + t.price.toFixed(2) : "—"}</td>
                <td className={`r mono tabular ${t.chg >= 0 ? "up" : "dn"}`}>{t.chg == null || !isFinite(t.chg) ? "—" : (t.chg >= 0 ? "+" : "") + t.chg.toFixed(2) + "%"}</td>
                <td className={`r mono tabular ${t.off52 >= -5 ? "up" : t.off52 >= -15 ? "" : "dim"}`} title="distance from 52-week high">{t.off52 == null ? "—" : t.off52 + "%"}</td>
                <td className={`r mono tabular ${t.vwap >= 0 ? "up" : "dn"}`} title="price vs session VWAP">{t.vwap == null ? "—" : (t.vwap >= 0 ? "+" : "") + t.vwap + "%"}</td>
                <td className="r mono tabular"><b className={parseFloat(t.rr) >= 2 ? "up" : ""}>{t.rr}</b></td>
                <td className="mono ss2-plan" title={t.t3plan ? "Stop · Entry · Target · T3 bull-stretch (armed)" : "Stop · Entry · Target"}>
                  <span className="dn"><i className="ss2-plan-k">S</i>${t.stop}</span>
                  <span className="copper"><i className="ss2-plan-k">E</i>${t.entry}</span>
                  <span className="up"><i className="ss2-plan-k">T</i>${t.t1plan}</span>
                  {t.t3plan ? <span style={{ color: "var(--violet)" }} title="T3 bull-stretch extension — momentum-confirmed runner target beyond T2"><i className="ss2-plan-k">T3</i>${t.t3plan}</span> : null}
                </td>
                <td className="r mono tabular dim">{t.atr == null ? "—" : t.atr}</td>
                <td className={`r mono tabular ${parseFloat(t.rvol) >= 1.5 ? "up" : "dim"}`}>{t.rvol == null || t.rvol === "—" ? "—" : t.rvol + "×"}</td>
                <td className={`r mono tabular ${t.adx >= 25 ? "up" : t.adx >= 20 ? "warn" : "dim"}`} title="ADX · trend strength">{t.adx == null ? "—" : t.adx}</td>
                <td><span className={`ss2-sq ss2-sq--${(t.squeeze || "off").toLowerCase()}`}>{!t.squeeze || t.squeeze === "OFF" ? "—" : t.squeeze}</span></td>
                <td className="r mono tabular dim" title="beta vs SPY">{t.beta == null ? "—" : t.beta.toFixed(2)}</td>
                <td className="r mono tabular dim" title="dollar volume (price × RVOL-adj shares)">{t.dvol == null ? "—" : ssFmtBig(t.dvol)}</td>
                <td className={`r mono tabular ${t.si >= 20 ? "warn" : "dim"}`} title={`short interest · ${t.dtc == null ? "n/a" : t.dtc} days to cover`}>{t.si == null ? "—" : t.si + "%"}</td>
                <td className="r mono tabular dim" title="avg bid/ask spread">{t.spread == null ? "—" : t.spread + "bp"}</td>
                <td><MTFDots states={t.mtf} /></td>
                <td className={`r mono tabular ${t.regWR >= 60 ? "up" : t.regWR >= 50 ? "warn" : "dn"}`}>{t.regWR == null ? "—" : t.regWR + "%"}</td>
                <td className="r mono tabular">{t.rs == null ? "—" : t.rs}</td>
                <td className={`r mono tabular ${t.r1m >= 0 ? "up" : "dn"}`} title="1-month return">{t.r1m == null ? "—" : (t.r1m >= 0 ? "+" : "") + t.r1m + "%"}</td>
                <td className={`r mono tabular ${t.r3m >= 0 ? "up" : "dn"}`} title="3-month return">{t.r3m == null ? "—" : (t.r3m >= 0 ? "+" : "") + t.r3m + "%"}</td>
                <td className={`r mono tabular ${t.wlb >= 50 ? "up" : "warn"}`}>{t.wlb == null ? "—" : t.wlb + "%"}</td>
                <td className="r mono tabular dim">{t.n == null ? "—" : t.n}</td>
                <td className="r mono tabular">{t.pf == null ? "—" : t.pf}</td>
                <td className={`r mono tabular ${t.iv >= 70 ? "warn" : "dim"}`} title="IV rank">{t.iv == null ? "—" : t.iv + "%"}</td>
                <td className={`r mono tabular ${t.sent > 0 ? "up" : t.sent < 0 ? "dn" : "dim"}`}>{t.sent == null ? "—" : (t.sent > 0 ? "+" : "") + t.sent.toFixed(2)}</td>
                <td className={`r mono tabular ${t.tgt >= 15 ? "up" : t.tgt >= 5 ? "warn" : "dim"}`} title="upside to mean analyst target">{t.tgt == null ? "—" : "+" + t.tgt + "%"}</td>
                <td className={`r mono tabular ${t.newsAge <= 6 ? "warn" : "dim"}`} title="hours since last catalyst">{t.newsAge == null ? "—" : t.newsAge + "h"}</td>
                <td className={`r mono tabular ${t.insUsd > 0 ? "up" : t.insUsd < 0 ? "dn" : "dim"}`} title="insider net 90d">{t.insUsd === 0 ? "—" : (t.insUsd > 0 ? "+" : "−") + "$" + Math.abs(t.insUsd).toFixed(1) + "M"}</td>
                <td className={`r mono tabular ${t.er <= 14 ? "warn" : "dim"}`}>{t.er <= 60 ? t.er : "—"}</td>
                <td className="mono ss2-signals">{ssSignals(t).map(s => (
                  <span key={s.id} className="ss2-sig" title={`${s.label} — ${s.desc}`}>{s.icon}</span>
                ))}{ssSignals(t).length === 0 && <span className="dim">—</span>}</td>
                <td className="r mono tabular ss2-aiedge" title="ML ensemble forward edge — expected risk-adjusted excess return from the model">
                  <span className={t.aiEdge >= 0.05 ? "up" : t.aiEdge <= -0.05 ? "dn" : "dim"}>{t.aiEdge == null ? "—" : (t.aiEdge >= 0 ? "+" : "") + t.aiEdge.toFixed(2)}</span>
                  <span className="ss2-aiedge-bar"><i className={t.aiEdge >= 0 ? "up" : "dn"} style={{ width: `${t.aiEdge == null ? 0 : Math.min(100, Math.abs(t.aiEdge) * 180)}%` }} /></span>
                </td>
                <td><SsSpark sym={t.sym} chg={t.chg} /></td>
                <td className="r mono tabular" title="median sessions to T1 · time-stop (Time Anatomy)">
                  {t.taMedT1 == null ? <span className="dim">—</span>
                    : <span><b className="copper">S{t.taMedT1}</b><span className="dim2"> · ⏲S{t.taStop}</span></span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected.size > 0 && (
        <div className="ss2-bulk">
          <div className="ss2-bulk-l">
            <Pill tone="copper" dot>{selected.size} SELECTED</Pill>
            {flash
              ? <span className="mono gn">✓ {flash}</span>
              : <span className="mono dim2">{[...selected].slice(0, 4).join(" · ")}{selected.size > 4 ? ` +${selected.size - 4}` : ""}</span>}
          </div>
          <div className="ss2-bulk-r">
            <button className="btn btn--sm" onClick={addSelWatch}>＋ WATCHLIST</button>
            <button className="btn btn--sm" onClick={() => setFlash(`${selected.size} sent to Playbook`)}>📓 PLAYBOOK</button>
            <button className="btn btn--sm" onClick={() => setFlash(`basket of ${selected.size} built`)}>🧺 BUILD BASKET</button>
            <button className="btn btn--sm" onClick={() => setFlash(`backtest queued · ${selected.size} names`)}>⚙ BACKTEST</button>
            <button className="btn btn--sm" onClick={exportCSV}>⤓ EXPORT CSV</button>
            <button className="btn btn--sm" onClick={clearSel} title="Clear selection">✕</button>
          </div>
        </div>
      )}
      </React.Fragment>
      )}
    </div>
  );
}

function MTFDots({ states }) {
  const labels = ["1H","4H","1D","1W"];
  return (
    <span className="mtf-dots">
      {states.map((s, i) => (
        <span key={i} className={`mtf-dot mtf-${s}`} title={`${labels[i]} · ${s}`} />
      ))}
    </span>
  );
}

function SsSpark({ sym, chg }) {
  const data = useMemoSS(() => {
    const code = (sym?.charCodeAt(0) || 65);
    const arr = [];
    let v = 0;
    for (let i = 0; i < 24; i++) {
      v += (Math.sin(i * 0.4 + code) + Math.cos(i * 0.7)) * 0.5 + (chg || 0) * 0.06;
      arr.push(v);
    }
    return arr;
  }, [sym, chg]);
  return <Sparkline data={data} color={`var(--${chg >= 0 ? "gn" : "rd"})`} w={70} h={20} />;
}

function Th({ col, sort, onClick, r, children }) {
  const active = sort.col === col;
  return (
    <th className={`${r ? "r" : ""} ss-th ${active ? "is-active" : ""}`}
        onClick={() => onClick(s => s.col === col ? { col, dir: -s.dir } : { col, dir: -1 })}>
      <span>{children}</span>
      {active && <span className="ss-th-arrow mono">{sort.dir > 0 ? "▲" : "▼"}</span>}
    </th>
  );
}

window.SurfaceSignalScanner = SurfaceSignalScanner;

// ── Right detail pane · 13 condensed evidence sections (per spec) ──
function ScannerDetailPane({ sym, onTicker }) {
  const raw = SS_UNIVERSE.find(r => r.sym === sym) || SS_UNIVERSE[0];
  if (!raw) return null;
  const t = { sector: "Materials", mechanism: "Setup forming", tier: "T2", eq: "VALID",
    entry: (raw.price||50).toFixed(2), stop: ((raw.price||50)*0.94).toFixed(2),
    t1plan: ((raw.price||50)*1.12).toFixed(2), n: 180, pf: "1.6", iv: 40, wlb: 46,
    insider: 0, sent: 0.4, er: 30, ...raw };
  const toneV = t.verdict === "BUY" ? "gn" : t.verdict === "AVOID" ? "rd" : "amb";
  const Sec = ({ n, title, children }) => (
    <div className="sdp-sec">
      <div className="sdp-sec-h"><span className="sdp-sec-n mono">{n}</span><span className="mono">{title}</span></div>
      <div className="sdp-sec-b">{children}</div>
    </div>
  );
  const KV = ({ k, v, tone }) => (
    <div className="sdp-kv"><span className="mono dim2">{k}</span><span className={`mono ${tone ? `kpi-tone--${tone}` : ""}`}>{v}</span></div>
  );
  return (
    <div className="sdp">
      <div className="sdp-hdr">
        <div>
          <div className="sdp-sym mono"><b>{t.sym}</b> <span className="dim2">{t.sector}</span></div>
          <div className="sdp-px mono">{t.price != null && isFinite(t.price) && t.price > 0 ? "$" + t.price.toFixed(2) : "—"} <span className={t.chg>=0?"up":"dn"}>{t.chg == null || !isFinite(t.chg) ? "—" : (t.chg>=0?"+":"") + t.chg.toFixed(2) + "%"}</span></div>
        </div>
        <div className="sdp-hdr-r">
          <span className={`ss2-score ss2-score--${t.score>=75?"gn":t.score>=60?"amb":"rd"}`}>{t.score}</span>
          <Pill tone={toneV} small>{secBias(t.verdict)}</Pill>
        </div>
      </div>
      <button className="sdp-open mono" onClick={() => onTicker(t.sym)}>OPEN 14-LENS DETAIL →</button>

      <div className="sdp-body">
        <Sec n="01" title="CONVICTION">
          <div className="sdp-arc"><div className="sdp-arc-fill" style={{ width: `${t.score}%` }} /></div>
          <KV k="tier" v={t.tier} /><KV k="conviction" v={`${t.score}%`} tone="copper" />
          {t.edge && <div className="sdp-edge">
            <span className={`ss2-medal ss2-medal--${gradeTone(t.edge)}`} style={{ "--deg": (t.edgePct * 3.6) + "deg" }} title="EDGE · composite factor score (informational)">{t.edge}</span>
            <span className="sdp-edge-strip">
              {GRADE_FACTORS.map(([k, lbl, full]) => (
                <span key={k} className="ss2-gs" title={`${full} · grade ${t.grades[k]}`}>
                  <span className="ss2-gs-k">{lbl}</span>
                  <span className={`ss2-gs-v g-${t.grades[k].toLowerCase()}`}>{t.grades[k]}</span>
                </span>
              ))}
            </span>
          </div>}
        </Sec>
        <Sec n="02" title="T.F.S.N PILLARS">
          {[["Tech",t.score-2,"cy"],["Fund",t.score-12,"blue"],["SMC",t.score-6,"gn"],["News",t.score-18,"violet"]].map(([l,v,c],i)=>(
            <div key={i} className="sdp-bar"><span className="mono dim2">{l}</span><div className="sdp-bar-t"><div className="sdp-bar-f" style={{width:`${Math.max(8,Math.min(100,v))}%`,background:`var(--${c})`}}/></div><span className="mono">{Math.max(8,Math.min(100,v))}</span></div>
          ))}
        </Sec>
        <Sec n="03" title="MECHANISM"><div className="sdp-mech mono">{t.mechanism} <span className="dim2">· falsify: closes below stop on vol</span></div></Sec>
        <Sec n="04" title="ENTRY TRIGGERS"><KV k="zone" v={`$${t.entry}–$${(parseFloat(t.entry)*1.005).toFixed(2)}`} /><KV k="EQ" v={t.eq} tone={t.eq==="MISSED"?"rd":t.eq==="EXTENDED"?"amb":"gn"} /></Sec>
        <Sec n="05" title="PLAN · HOLD"><KV k="stop" v={`$${t.stop}`} tone="rd" /><KV k="T1" v={`$${t.t1plan}`} tone="gn" />{t.t3plan ? <KV k="T3 stretch" v={`$${t.t3plan}`} tone="violet" /> : null}<KV k="R:R" v={t.rr} tone="copper" /><KV k="hold" v="8–14 sessions" /></Sec>
        <Sec n="06" title="SMC ZONES"><KV k="OB demand" v={`$${(t.price*0.94).toFixed(2)}`} tone="gn" /><KV k="FVG" v={`$${(t.price*1.03).toFixed(2)}`} /><KV k="BoS" v="confirmed" tone="gn" /></Sec>
        <Sec n="07" title="SETUP STATS"><KV k="family" v={t.setup} /><KV k="win-rate" v={`${(t.wlb+8)}%`} /><KV k="Wilson LB" v={`${t.wlb}%`} tone={t.wlb>=50?"gn":"amb"} /><KV k="n · PF" v={`${t.n} · ${t.pf}`} /></Sec>
        <Sec n="08" title="EARNINGS"><KV k="reports in" v={`${t.er<=70?t.er+"d":"—"}`} tone={t.er<=10?"amb":"ink"} /><KV k="implied move" v={`±${(t.iv/6).toFixed(1)}%`} /></Sec>
        <Sec n="09" title="OPTIONS SKEW"><KV k="IV rank" v={`${t.iv}%`} tone={t.iv>=70?"amb":"ink"} /><KV k="put/call" v="0.78" tone="gn" /></Sec>
        <Sec n="10" title="SMART MONEY"><KV k="insider 90d" v={`${t.insider>0?"+":""}${t.insider} net`} tone={t.insider>0?"gn":t.insider<0?"rd":"ink"} /><KV k="13F" v={t.insider>0?"adds":"flat"} />{(()=>{const c=t.congress;return c&&c.net&&c.net!=="neutral"?<KV k="congress" v={`${c.n} ${c.net==="bullish"?"buy":"sell"}`} tone={c.net==="bullish"?"gn":"rd"} />:<KV k="congress" v="—" tone="ink" />;})()}<KV k="news sent" v={t.sent?`${t.sent>0?"+":""}${t.sent.toFixed(2)}`:"+0.4"} tone="gn" /></Sec>
        <Sec n="11" title="PORTFOLIO IMPACT"><KV k="correl-to-book" v="0.34" tone="gn" /><KV k="NAV after" v="6.8%" /><KV k="sector tilt" v={`+${(t.sector || "Mat").slice(0,4)}`} tone="amb" /></Sec>
        <Sec n="12" title="DECISION GATES"><KV k="gates passed" v={`${t.verdict==="AVOID"?"6":"9"} / 10`} tone={t.verdict==="AVOID"?"rd":"gn"} /><KV k="audit" v="logged" /></Sec>
        <Sec n="13" title="KILL-LIST">{t.verdict==="AVOID"
          ? <KV k="reason" v="distribution · Wilson < 45%" tone="rd" />
          : <KV k="status" v="clear · not killed" tone="gn" />}</Sec>
      </div>
    </div>
  );
}

