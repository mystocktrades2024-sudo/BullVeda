// signalledger-data.jsx — system-wide signal accountability dataset.
// Logs every published call (8 sources), scores forward returns across horizons
// (D1–D7, W1–W8, M1–M9), direction-aligned, with maturity awareness, regime
// tagging, and AI calibration. Exposes window.SigLedger.
//
// 2026-06-03 (audit): now loads the REAL per-signal forward-scored ledger from
// /v2/data_leaders.json (cache/audit_ledger + signal_log → emitted nightly,
// ~3,600 calls over the live window with real ret at every horizon). Falls back
// to the synthetic generator only if that feed is unavailable. The aggregation
// layer (aggregate / leaderboard / ledger / calibration / regime / equity) is
// generic over {SIGNALS, HZ, ret}, so it is shared by both paths unchanged.

(function () {
  // ── primitives, assigned by whichever data path is active ──
  let HZ, HZ_BY, SOURCES, SOURCE_BY, SIGNALS, ret, totalCalls, REAL = false;

  // ── try the REAL forward-scored ledger (synchronous, like the boot loader) ──
  // The real ledger (data_leaders) is DEFERRED — boot loads it async, so it's usually
  // null at module-eval (→ synthetic) and the real path is applied later on bv:heavyready.
  let LDR = (window.__BV && window.__BV.leaders) || null;
  function _validLdr(L) { return L && Array.isArray(L.signals) && L.signals.length && Array.isArray(L.horizons); }
  function _realRet(sig, hz) {
    const v = (sig.ret || {})[hz.id];
    if (v == null) return { edge: null, raw: null, mature: false };
    const aligned = +(((sig.dir === "short") ? -v : v)).toFixed(2);
    return { edge: aligned, raw: aligned, mature: true };
  }
  function applyReal(L) {
    REAL = true;
    HZ = L.horizons.map((h, i) => ({ id: h.id, label: h.label, days: h.days, group: h.group, idx: h.idx != null ? h.idx : i }));
    HZ_BY = {}; HZ.forEach(h => { HZ_BY[h.id] = h; });
    SOURCES = (L.sources || []).map(s => ({ id: s.id, label: s.label }));
    SOURCE_BY = {}; SOURCES.forEach(s => { SOURCE_BY[s.id] = s; });
    SIGNALS = L.signals;
    totalCalls = L.totalCalls || SIGNALS.length;
    ret = _realRet;
  }

  if (_validLdr(LDR)) {
    applyReal(LDR);  // REAL path (preloaded)
  } else {
    // ── SYNTHETIC fallback (only when /v2/data_leaders.json is unavailable) ──
    HZ = [];
    for (let d = 1; d <= 5; d++) HZ.push({ id: "D" + d, label: "D" + d, days: d, group: "D" });
    for (let w = 1; w <= 12; w++) HZ.push({ id: "W" + w, label: "W" + w, days: w * 5, group: "W" });
    for (let m = 1; m <= 12; m++) HZ.push({ id: "M" + m, label: "M" + m, days: m * 21, group: "M" });
    HZ_BY = {}; HZ.forEach((h, i) => { h.idx = i; HZ_BY[h.id] = h; });
    SOURCES = [
      { id: "screeners", label: "Screeners", peak: 18, amp: 2.6, breadth: 22, base: 0.2, vol: 3.2, dirBias: 0.86, n: 34 },
      { id: "earnings", label: "Earnings", peak: 4, amp: 3.4, breadth: 12, base: -0.1, vol: 4.1, dirBias: 0.78, n: 28 },
      { id: "options", label: "Options", peak: 9, amp: 2.9, breadth: 14, base: 0.0, vol: 4.6, dirBias: 0.6, n: 26 },
      { id: "ai", label: "AI Predictions", peak: 25, amp: 3.0, breadth: 34, base: 0.3, vol: 3.0, dirBias: 0.82, n: 40, hasProb: true },
      { id: "insiders", label: "Insiders", peak: 63, amp: 3.6, breadth: 55, base: 0.1, vol: 3.4, dirBias: 0.9, n: 22 },
      { id: "momentum", label: "Momentum", peak: 16, amp: 3.1, breadth: 18, base: 0.1, vol: 3.6, dirBias: 0.92, n: 32 },
      { id: "smc", label: "SMC / Patterns", peak: 10, amp: 2.4, breadth: 15, base: 0.0, vol: 3.8, dirBias: 0.7, n: 24 },
      { id: "verdict", label: "Overall Verdict", peak: 22, amp: 3.2, breadth: 30, base: 0.4, vol: 2.8, dirBias: 0.84, n: 36 },
    ];
    SOURCE_BY = {}; SOURCES.forEach(s => SOURCE_BY[s.id] = s);
    const SYMS = ["NVDA","ARGN","ARCM","DRSH","BORA","FLNX","INPR","MERC","NVRH","KOPL","ZOTR","HAVN","VLCT","GENO","KARO","NEXO","FRAC","LIGN","BIVO","AXLE","IPSO","TSLA","AMD","SOFI","PLTR","CRWD","SNOW","NET","DDOG","ABNB"];
    const REGIMES = ["bull", "bull", "chop", "bull", "chop", "bear"];
    const mulberry = (a) => function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const gauss = (rng) => { let u = 0, v = 0; while (!u) u = rng(); while (!v) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    const rng = mulberry(987654321);
    SIGNALS = []; let sid = 0;
    SOURCES.forEach(src => { for (let k = 0; k < src.n; k++) {
      const age = Math.floor(Math.pow(rng(), 0.7) * 365) + 1;
      SIGNALS.push({ id: "s" + (sid++), source: src.id, sym: SYMS[Math.floor(rng() * SYMS.length)], dir: rng() < src.dirBias ? "long" : "short", regime: REGIMES[Math.floor(rng() * REGIMES.length)], age, refPrice: +(15 + rng() * 400).toFixed(2), predProb: src.hasProb ? +(0.5 + rng() * 0.45).toFixed(2) : null, skill: (rng() - 0.42), seed: Math.floor(rng() * 1e9) });
    } });
    const meanEdge = (src, hz) => src.base + src.amp * Math.exp(-Math.pow(hz.days - src.peak, 2) / (2 * src.breadth * src.breadth)) - 0.004 * hz.days;
    const spyMove = (hz, seed) => { const r = mulberry(seed ^ 0xABCD); return hz.days * 0.018 + gauss(r) * Math.sqrt(hz.days) * 0.35; };
    ret = function (sig, hz) {
      const src = SOURCE_BY[sig.source]; const mature = hz.days <= sig.age;
      const r = mulberry(sig.seed ^ (hz.idx * 2654435761)); const idio = gauss(r) * src.vol;
      const peakProx = Math.exp(-Math.pow(hz.days - src.peak, 2) / (2 * src.breadth * src.breadth));
      const edge = meanEdge(src, hz) + idio + sig.skill * src.amp * peakProx * 1.4;
      const sM = spyMove(hz, sig.seed); const raw = sig.dir === "long" ? edge + sM : edge - sM;
      return { edge: +edge.toFixed(2), raw: +raw.toFixed(2), mature };
    };
    totalCalls = SIGNALS.length;
  }

  // ── aggregation layer (SHARED — generic over {SIGNALS, HZ, ret}) ──
  function aggregate(sourceId, hz, metric) {
    const sigs = SIGNALS.filter(s => s.source === sourceId);
    const vals = [];
    sigs.forEach(s => { const r = ret(s, hz); if (r.mature) vals.push(metric === "raw" ? r.raw : r.edge); });
    const n = vals.length;
    if (!n) return { mean: null, hit: null, n: 0, t: 0 };
    const mean = vals.reduce((a, b) => a + b, 0) / n;
    const hit = vals.filter(v => v > 0).length / n;
    const sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, n - 1)) || 1;
    const t = mean / (sd / Math.sqrt(n));
    return { mean: +mean.toFixed(2), hit: +(hit * 100).toFixed(0), n, t: +t.toFixed(2), sd: +sd.toFixed(2) };
  }
  function sourceSummary(sourceId, metric) {
    const decay = HZ.map(hz => ({ hz: hz.id, group: hz.group, days: hz.days, ...aggregate(sourceId, hz, metric) }));
    const matured = decay.filter(d => d.n > 0);
    const band = matured.filter(d => d.days >= 5 && d.days <= 20);
    const ref = band.length ? band : matured;
    const avgEdge = ref.length ? +(ref.reduce((a, d) => a + d.mean, 0) / ref.length).toFixed(2) : 0;
    const avgHit = ref.length ? +(ref.reduce((a, d) => a + d.hit, 0) / ref.length).toFixed(0) : 0;
    let best = null; matured.forEach(d => { if (!best || d.mean > best.mean) best = d; });
    const sigs = SIGNALS.filter(s => s.source === sourceId);
    const w2 = HZ_BY["W2"] || HZ[Math.min(HZ.length - 1, 8)]; let gw = 0, gl = 0, nb = 0; const indiv = [];
    sigs.forEach(s => { const r = ret(s, w2); if (r.mature) { const v = metric === "raw" ? r.raw : r.edge; if (v > 0) gw += v; else gl += -v; nb++; indiv.push({ sym: s.sym, v }); } });
    const pf = gl > 0 ? +(gw / gl).toFixed(2) : (gw > 0 ? 99 : 0);
    indiv.sort((a, b) => b.v - a.v);
    const tstat = aggregate(sourceId, w2, metric).t;
    return { id: sourceId, label: (SOURCE_BY[sourceId] || {}).label || sourceId, decay, avgEdge, avgHit, best, pf, nTotal: sigs.length, nMatured: nb, best1: indiv[0], worst1: indiv[indiv.length - 1], tstat, sig: Math.abs(tstat) >= 2 };
  }
  function leaderboard(metric) { return SOURCES.map(s => sourceSummary(s.id, metric)).sort((a, b) => b.avgEdge - a.avgEdge); }
  function ledger(metric, filter) {
    return SIGNALS.filter(s => !filter || !filter.source || s.source === filter.source).map(s => {
      const path = HZ.map(hz => { const r = ret(s, hz); return { hz: hz.id, days: hz.days, v: metric === "raw" ? r.raw : r.edge, mature: r.mature }; });
      const mat = path.filter(p => p.mature); const last = mat.length ? mat[mat.length - 1] : null;
      // Tiered maturity (2026-06-09). The old binary flag only flipped to "matured"
      // once a call cleared its LONGEST horizon (~M9/189d), so a track record younger
      // than 6mo showed "maturing" for everything. Anchor the meaningful milestone on
      // the SWING band (W4 ≈ 20d) — once it elapses the swing thesis is resolved — and
      // keep "matured" for fully-resolved (all horizons in). status = CSS-safe key;
      // statusLabel = display text.
      const _terminal = (HZ_BY["M12"] || HZ_BY["M9"] || HZ[HZ.length - 1]).days;
      const _swingDays = (HZ_BY["W4"] || {}).days || 20;
      const _st = s.age >= _terminal ? "matured"
                : s.age >= _swingDays ? "swing"
                : s.age >= 3 ? "maturing"
                : "fresh";
      const _stLabel = { matured: "matured", swing: "swing ✓", maturing: "maturing", fresh: "fresh" }[_st];
      return { ...s, label: (SOURCE_BY[s.source] || {}).label || s.source, path, last, status: _st, statusLabel: _stLabel, maturedN: mat.length };
    }).sort((a, b) => a.age - b.age);
  }
  function calibration(metric) {
    const w2 = HZ_BY["W2"] || HZ[Math.min(HZ.length - 1, 8)]; const buckets = [[.5,.6],[.6,.7],[.7,.8],[.8,.9],[.9,1.01]];
    return buckets.map(([lo, hi]) => {
      const sigs = SIGNALS.filter(s => s.source === "ai" && s.predProb != null && s.predProb >= lo && s.predProb < hi);
      let n = 0, w = 0; sigs.forEach(s => { const r = ret(s, w2); if (r.mature) { n++; if ((metric === "raw" ? r.raw : r.edge) > 0) w++; } });
      return { lo, hi, pred: (lo + hi) / 2, realized: n ? w / n : null, n };
    });
  }
  function regimeHits(metric) {
    const w2 = HZ_BY["W2"] || HZ[Math.min(HZ.length - 1, 8)]; const out = {};
    ["bull", "chop", "bear"].forEach(rg => {
      out[rg] = SOURCES.map(src => {
        const sigs = SIGNALS.filter(s => s.source === src.id && s.regime === rg);
        let n = 0, w = 0; sigs.forEach(s => { const r = ret(s, w2); if (r.mature) { n++; if ((metric === "raw" ? r.raw : r.edge) > 0) w++; } });
        return { source: src.id, label: src.label, hit: n ? +(w / n * 100).toFixed(0) : null, n };
      });
    });
    return out;
  }
  function equityCurve(sourceId, hzId, metric) {
    const hz = HZ_BY[hzId] || HZ_BY["W2"] || HZ[Math.min(HZ.length - 1, 8)];
    const sigs = SIGNALS.filter(s => (sourceId === "__all" || s.source === sourceId)).slice().sort((a, b) => b.age - a.age);
    let cum = 0; const pts = [{ i: 0, v: 0 }];
    sigs.forEach((s, i) => { const r = ret(s, hz); if (r.mature) { cum += (metric === "raw" ? r.raw : r.edge); pts.push({ i: i + 1, v: +cum.toFixed(2) }); } });
    return pts;
  }

  window.SigLedger = { HZ, HZ_BY, SOURCES, SOURCE_BY, SIGNALS, aggregate, sourceSummary, leaderboard, ledger, calibration, regimeHits, equityCurve, totalCalls, real: REAL };

  // The real ledger is loaded async by boot — when it lands, apply it and refresh the
  // exported data (the aggregation fns close over the module vars, so reassigning is enough).
  if (!REAL) window.addEventListener("bv:heavyready", function () {
    const L = window.__BV && window.__BV.leaders;
    if (!_validLdr(L)) return;
    applyReal(L);
    const SL = window.SigLedger;
    SL.HZ = HZ; SL.HZ_BY = HZ_BY; SL.SOURCES = SOURCES; SL.SOURCE_BY = SOURCE_BY;
    SL.SIGNALS = SIGNALS; SL.totalCalls = totalCalls; SL.real = REAL;
  }, { once: true });
})();
