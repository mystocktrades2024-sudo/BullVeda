// lens-time.jsx — Time Anatomy lens (Kairos whitepaper Phase 4, MVP).
// Answers WHEN a setup resolves: session-by-session survival curves for T1/T2,
// a decay-threshold time stop, P(T2|T1), and an earnings-wall flag.
//
// DATA: reads ONLY the live scan-bundle variables already in the ticker object
// (V1 regime, V2 vol, V3 sector RS, V4 quality×family, V5/V6 ATR-distance, plus
// catalyst tier + days-to-earnings). ZERO new API calls — no /api/fundamentals,
// no /api/ml, no per-ticker scan. This MVP is a PARAMETRIC estimator seeded by
// those real inputs; it is explicitly stamped "modeled · not yet calibrated"
// until the 20-yr survival table (Phase 4.1–4.2) replaces the curve generator.

const { useMemo: useTAm } = React;

// ── dispatcher: real calibrated table first; parametric estimator as fallback ──
function timeAnatomy(t, mode) {
  if (!t) return null;
  const real = (window.__BV && window.__BV.timeTable) ? timeAnatomyTable(t, mode) : null;
  if (real && real.ok) return real;
  return timeAnatomyParametric(t, mode);
}
window.timeAnatomy = timeAnatomy;

// ── REAL engine: look up the regime-conditioned survival cell (whitepaper §6) ──
// Cell index = [regime, vol, rs, qual, dist-bucket]. T1/T2 are the same survival
// process queried at their two ATR-distance buckets. Sparse cells collapse the
// least-significant dim (qual → rs → vol); deeper collapse lowers confidence.
function timeAnatomyTable(t, mode) {
  const TT = window.__BV.timeTable; if (!TT || !TT.cells || !TT.meta) return null;
  const M = TT.meta, cells = TT.cells, HZ = M.horizon;
  const sc = t._scan || {};
  const num = (v) => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const entry = num(t.pivot) ?? num(t.price), stop = num(t.stop), t1 = num(t.t1), t2 = num(t.t2);
  if (entry == null || stop == null || t1 == null || entry <= stop || t1 <= entry) {
    return { ok: false, reason: "No defined entry/stop/target — cannot estimate a time horizon." };
  }
  const R = entry - stop, ATR = R / 1.25;
  const distT1 = (t1 - entry) / ATR, distT2 = (t2 != null && t2 > entry) ? (t2 - entry) / ATR : null;
  const distBucket = (d) => d == null ? null : d < 2 ? "<2" : d <= 5 ? "2-5" : d <= 10 ? "5-10" : ">10";
  // live conditioning buckets (same definitions as the build)
  const regime4 = (window.__BV.market && window.__BV.market.regime4) || "risk_on_choppy";
  const rvol = num(sc.rvol);
  const vb = rvol == null ? "normal" : rvol < 0.7 ? "compressed" : rvol <= 1.1 ? "normal" : rvol <= 1.5 ? "expanding" : "spike";
  const rs = num(sc.rs);
  const rb = rs == null ? "neutral" : rs >= 80 ? "strong_in" : rs >= 60 ? "mild_in" : rs >= 40 ? "neutral" : rs >= 20 ? "mild_out" : "strong_out";
  const score = num(t.score) ?? 60;
  const qb = score >= 80 ? "elite" : score >= 65 ? "high" : "standard";
  // map the live setup string → historical family bucket (V4)
  const setupStr = (t.setupFamily || sc.setup || "").toLowerCase();
  const fam = /breakout|vcp|52w|expansion|gap/.test(setupStr) ? "breakout"
    : /pullback|bounce|ema|value/.test(setupStr) ? "pullback"
    : /trend|continuation|momentum/.test(setupStr) ? "trend" : "other";
  const NMIN = M.n_min || 40;

  // look up one [reg,vol,rs,family,qb,dist] cell with graceful collapse (qual→family→rs→vol)
  function lookup(distB) {
    if (!distB) return null;
    const tries = [
      [regime4, vb, rb, fam, qb, distB],       // depth 0 — exact
      [regime4, vb, rb, fam, "*", distB],      // drop qual
      [regime4, vb, rb, "*", "*", distB],      // drop family
      [regime4, vb, "*", "*", "*", distB],     // drop rs
      [regime4, "*", "*", "*", "*", distB],    // drop vol
    ];
    for (let depth = 0; depth < tries.length; depth++) {
      const spec = tries[depth];
      if (spec.indexOf("*") === -1) {
        const c = cells[spec.join("|")];
        if (c && c.n >= NMIN) return { cell: c, depth };
        continue;
      }
      const agg = aggregate(spec);
      if (agg && agg.n >= NMIN) return { cell: agg, depth };
    }
    // last resort: best available even if < NMIN
    const c0 = cells[[regime4, vb, rb, fam, qb, distB].join("|")];
    if (c0) return { cell: c0, depth: 0, thin: true };
    const aggAny = aggregate([regime4, "*", "*", "*", "*", distB]);
    return aggAny ? { cell: aggAny, depth: 4, thin: true } : null;
  }
  function aggregate(spec) {
    let n = 0, recent = 0; const Sr = new Array(HZ + 1).fill(0), Ss = new Array(HZ + 1).fill(0);
    for (const key in cells) {
      const parts = key.split("|"); let ok = true;
      for (let i = 0; i < 6; i++) if (spec[i] !== "*" && spec[i] !== parts[i]) { ok = false; break; }
      if (!ok) continue;
      const c = cells[key], w = c.n;
      n += c.n; recent += (c.recent_share || 0) * c.n;
      for (let s = 0; s <= HZ; s++) { Sr[s] += (c.S_reach[s] || 0) * w; Ss[s] += (c.S_stop[s] || 0) * w; }
    }
    if (!n) return null;
    return { n, recent_share: recent / n, S_reach: Sr.map(x => x / n), S_stop: Ss.map(x => x / n),
      p_reach: Sr[HZ] / n, p_stop: Ss[HZ] / n };
  }

  const luT1 = lookup(distBucket(distT1));
  if (!luT1) return { ok: false, reason: "No analogues for this setup's conditions even after collapse — NO ESTIMATE." };
  const luT2 = distT2 == null ? null : lookup(distBucket(distT2));
  const cT1 = luT1.cell, cT2 = luT2 && luT2.cell;

  const m = (mode || window.__tmode || "SWING").toUpperCase();
  const ceiling = m.startsWith("POS") ? 63 : m.startsWith("INV") ? 126 : 21;
  const horizon = Math.min(HZ, ceiling > 21 ? ceiling : Math.min(HZ, 45));

  // build the curve array the component renders
  const curve = [];
  for (let s = 0; s <= horizon; s++) {
    const sT1 = cT1.S_reach[s] || 0, sSt = cT1.S_stop[s] || 0;
    const sT2 = cT2 ? (cT2.S_reach[s] || 0) : 0;
    curve.push({ s, sT1: +sT1.toFixed(4), sT2: +sT2.toFixed(4), sSt: +sSt.toFixed(4),
      sOp: +Math.max(0, 1 - sT1 - sSt).toFixed(4) });
  }
  const pHitT1 = cT1.p_reach, pHitT2 = cT2 ? cT2.p_reach : null;
  // median = first session reaching 50% of eventual reach-mass; decay = 90%; capture 25→75%
  const sessAt = (cell, frac) => {
    const tgt = cell.p_reach * frac; if (cell.p_reach <= 0) return null;
    for (let s = 0; s <= horizon; s++) if (cell.S_reach[s] >= tgt) return s;
    return null;
  };
  const medianT1 = sessAt(cT1, 0.5), medianT2 = cT2 ? sessAt(cT2, 0.5) : null;
  // decay / time-stop = session where ~60% of eventual winners have resolved (marginal
  // reach rate has materially decayed). Backtested: edge-neutral, −18% holding / −20%
  // loser-time vs holding to 30D (scripts/prove_time_stop.py). Earlier than 90%, which
  // fired too late to free capital.
  const decayT1 = sessAt(cT1, 0.6), decayT2 = cT2 ? sessAt(cT2, 0.6) : null;
  const captureLo = sessAt(cT1, 0.25), captureHi = sessAt(cT1, 0.75);
  let hardStop = ceiling;
  for (const c of curve) { if (c.sOp < 0.15) { hardStop = Math.min(c.s, ceiling); break; } }
  const pT2givenT1 = pHitT2 == null ? null : Math.max(0.05, Math.min(0.95, pHitT2 / Math.max(pHitT1, 0.08)));
  const earnDays = num(t.earnings && t.earnings.days);
  const earnWallT2 = earnDays != null && medianT2 != null && earnDays < medianT2;

  // confidence from analogue count + collapse depth + recency
  const depth = luT1.depth, nAna = cT1.n;
  let level = "HIGH";
  if (luT1.thin || nAna < NMIN) level = "LOW";
  else if (depth >= 2 || nAna < 100) level = "MED";
  else if (depth === 1) level = "MED";
  const collapseTxt = depth === 0 ? "exact cell" : `collapsed ${depth} dim${depth > 1 ? "s" : ""}`;

  return {
    ok: true, source: "calibrated", horizon, curve,
    medianT1, medianT2, decayT1, decayT2, hardStop, pHitT1, pHitT2, pT2givenT1,
    captureLo: captureLo ?? medianT1, captureHi: captureHi ?? medianT1,
    earnDays, earnWallT2, ceiling, holdMode: m,
    distT1: +distT1.toFixed(1), distT2: distT2 == null ? null : +distT2.toFixed(1),
    buckets: {
      V1: ({ risk_on_trending: "Trending Bull", risk_on_choppy: "Choppy Bull", risk_off_trending: "Trending Bear", panic: "Crisis / Spike" }[regime4]) || regime4,
      V2: vb[0].toUpperCase() + vb.slice(1), V3: rb.replace("_", "-"),
      V4: `${t.setupFamily || "—"} · ${qb[0].toUpperCase() + qb.slice(1)}`,
      V5: distBucket(distT1) + " ATR", V6: distT2 == null ? "—" : distBucket(distT2) + " ATR",
    },
    confidence: { level, note: `${nAna.toLocaleString()} analogues · ${collapseTxt} · ${(cT1.recent_share * 100).toFixed(0)}% recent (≤3y)`,
      analogues: nAna, depth, builtAt: M.built_at, dateRange: M.date_range },
  };
}

// ── parametric fallback: used only when the table is absent or NO-ESTIMATE ──
function timeAnatomyParametric(t, mode) {
  if (!t) return null;
  const sc = t._scan || {};
  const num = (v) => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const entry = num(t.pivot) ?? num(t.price);
  const stop = num(t.stop);
  const t1 = num(t.t1), t2 = num(t.t2);
  if (entry == null || stop == null || t1 == null || entry <= stop || t1 <= entry) {
    return { ok: false, reason: "No defined entry/stop/target — cannot estimate a time horizon." };
  }
  const R = entry - stop;                       // risk unit
  const ATR = R / 1.25;                          // stop ≈ 1.25×ATR (config stop_atr_mult)
  const distT1 = (t1 - entry) / ATR;
  const distT2 = t2 != null && t2 > entry ? (t2 - entry) / ATR : null;

  // ── V1..V6 bucketing (whitepaper §3.2) ──
  const regime4 = (window.__BV && window.__BV.market && window.__BV.market.regime4) || "risk_on_choppy";
  const V1 = { risk_on_trending: ["Trending Bull", 0.80], risk_on_choppy: ["Choppy Bull", 1.00],
    risk_off_trending: ["Trending Bear", 1.28], panic: ["Crisis / Spike", 1.55] }[regime4] || ["Choppy Bull", 1.0];
  const rvol = num(sc.rvol);
  const V2 = rvol == null ? ["Normal", 1.0] : rvol < 0.7 ? ["Compressed", 0.85] : rvol <= 1.1 ? ["Normal", 1.0] : rvol <= 1.5 ? ["Expanding", 1.2] : ["Spike", 1.45];
  const rs = num(sc.rs);
  const V3 = rs == null ? ["Neutral", 1.0] : rs >= 80 ? ["Strong-In", 0.9] : rs >= 60 ? ["Mild-In", 0.97] : rs >= 40 ? ["Neutral", 1.0] : rs >= 20 ? ["Mild-Out", 1.08] : ["Strong-Out", 1.18];
  const score = num(t.score) ?? 60;
  const qband = score >= 80 ? ["Elite", 0.85] : score >= 65 ? ["High", 1.0] : ["Standard", 1.15];
  const family = t.setupFamily || sc.setup || "—";
  const catT1 = sc.cat === "T1" || sc.cat === "T1";
  const catMult = (sc.cat === "T1") ? 0.85 : (sc.cat === "T3") ? 1.1 : 1.0;
  const bkt = (d) => d == null ? "—" : d < 2 ? "<2" : d <= 5 ? "2–5" : d <= 10 ? "5–10" : ">10";
  // base median sessions by ATR-distance bucket (anchored to whitepaper worked example: >10 ATR → ~26 to T1)
  const baseT1 = { "<2": 4, "2–5": 9, "5–10": 16, ">10": 26 }[bkt(distT1)] || 16;
  const baseT2 = { "<2": 8, "2–5": 16, "5–10": 30, ">10": 44 }[bkt(distT2)] || 30;

  const mult = V1[1] * V2[1] * V3[1] * qband[1] * catMult;
  const medianT1 = Math.max(2, Math.round(baseT1 * mult));
  const medianT2 = distT2 == null ? null : Math.max(medianT1 + 2, Math.round(baseT2 * mult));

  // asymptotic hit probabilities (eventual P(T1)/P(T2) before stop)
  const regAdj = { risk_on_trending: 0.10, risk_on_choppy: 0.0, risk_off_trending: -0.10, panic: -0.18 }[regime4] || 0;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const pHitT1 = clamp(0.52 + (score - 60) / 130 + regAdj - Math.max(0, (distT1 - 5)) * 0.012, 0.18, 0.86);
  const pHitT2 = distT2 == null ? null : clamp(pHitT1 * (0.78 - Math.max(0, (distT2 - 8)) * 0.01), 0.08, pHitT1);
  const pStopAsym = (1 - pHitT1) * 0.62;        // of the non-T1 mass, share that stops out

  // hold ceiling by mode
  const m = (mode || (window.__tmode) || "SWING").toUpperCase();
  const ceiling = m.startsWith("POS") ? 63 : m.startsWith("INV") ? 126 : 21;
  const horizon = Math.min(Math.max((medianT2 || medianT1) * 2, 30), ceiling > 21 ? ceiling : 35);

  // logistic survival generator: reaches asymptote `cap`, 50%-of-cap at `med`
  const scaleT1 = Math.max(2, medianT1 * 0.42 * V2[1]);
  const scaleT2 = medianT2 == null ? null : Math.max(3, medianT2 * 0.42 * V2[1]);
  const scaleSt = Math.max(2, medianT1 * 0.32);
  const medStop = Math.max(2, Math.round(medianT1 * 0.7));
  const logistic = (t_, med, scale) => 1 / (1 + Math.exp(-(t_ - med) / scale));

  const earnDays = num(t.earnings && t.earnings.days);
  const earnWallT2 = earnDays != null && medianT2 != null && earnDays < medianT2;

  const curve = [];
  for (let s = 0; s <= horizon; s++) {
    const sT1 = pHitT1 * logistic(s, medianT1, scaleT1);
    let sT2 = scaleT2 == null ? 0 : pHitT2 * logistic(s, medianT2, scaleT2);
    if (earnWallT2 && s >= earnDays) sT2 = pHitT2 * logistic(earnDays, medianT2, scaleT2); // truncate at ER
    const sSt = pStopAsym * logistic(s, medStop, scaleSt);
    const sOp = clamp(1 - sT1 - sSt, 0, 1);
    curve.push({ s, sT1: +sT1.toFixed(4), sT2: +sT2.toFixed(4), sSt: +sSt.toFixed(4), sOp: +sOp.toFixed(4) });
  }
  // decay threshold = session reaching 90% of the eventual T1 mass (marginal gain → ~cost of carry)
  const decayT1 = Math.min(horizon, Math.round(medianT1 + scaleT1 * Math.log(9)));
  const decayT2 = medianT2 == null ? null : Math.min(horizon, Math.round(medianT2 + scaleT2 * Math.log(9)));
  // hard time stop = first session where still-open < 15%, capped by hold ceiling
  let hardStop = ceiling;
  for (const c of curve) { if (c.sOp < 0.15) { hardStop = Math.min(c.s, ceiling); break; } }
  const pT2givenT1 = pHitT2 == null ? null : clamp((pHitT2 / Math.max(pHitT1, 0.1)) * 0.95, 0.08, 0.9);

  // fastest-capture zone = sessions spanning 25%→75% of eventual T1 mass
  const zLo = Math.max(1, Math.round(medianT1 - scaleT1 * Math.log(3)));
  const zHi = Math.min(horizon, Math.round(medianT1 + scaleT1 * Math.log(3)));

  return {
    ok: true, horizon, curve,
    medianT1, medianT2, decayT1, decayT2, hardStop, pHitT1, pHitT2, pT2givenT1,
    captureLo: zLo, captureHi: zHi, earnDays, earnWallT2, ceiling, holdMode: m,
    distT1: +distT1.toFixed(1), distT2: distT2 == null ? null : +distT2.toFixed(1),
    buckets: {
      V1: V1[0], V2: V2[0], V3: V3[0], V4: `${family} · ${qband[0]}`,
      V5: bkt(distT1) + " ATR", V6: distT2 == null ? "—" : bkt(distT2) + " ATR",
    },
    source: "modeled",
    confidence: { level: "MODELED", note: "parametric estimate · no calibrated analogues for these conditions", analogues: null },
  };
}
window.timeAnatomy = timeAnatomy;

// ── survival-curve chart (hand-drawn SVG, themed via CSS vars) ──
function TaCurve({ data }) {
  const W = 720, H = 240, PADL = 40, PADB = 26, PADT = 14, PADR = 14;
  const xs = (s) => PADL + (s / data.horizon) * (W - PADL - PADR);
  const ys = (p) => PADT + (1 - p) * (H - PADT - PADB);
  const path = (key) => data.curve.map((c, i) => `${i ? "L" : "M"}${xs(c.s).toFixed(1)},${ys(c[key]).toFixed(1)}`).join("");
  const vline = (s, color, dash) => s == null ? null : <line x1={xs(s)} y1={PADT} x2={xs(s)} y2={H - PADB} stroke={color} strokeWidth="1.2" strokeDasharray={dash || "3 3"} opacity="0.7" />;
  // 95% CI ribbon around the reach (T1) curve — normal-approx half-width from cell n
  const nAna = (data.confidence && data.confidence.analogues) || 0;
  const ciBand = (() => {
    if (!nAna) return null;
    const up = [], lo = [];
    data.curve.forEach((c) => {
      const p = c.sT1 || 0, hw = 1.96 * Math.sqrt(Math.max(p * (1 - p), 0.0001) / nAna);
      up.push([xs(c.s), ys(Math.min(1, p + hw))]); lo.push([xs(c.s), ys(Math.max(0, p - hw))]);
    });
    return "M" + up.map(q => q[0].toFixed(1) + "," + q[1].toFixed(1)).join("L") + "L" +
      lo.reverse().map(q => q[0].toFixed(1) + "," + q[1].toFixed(1)).join("L") + "Z";
  })();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <g key={p}>
          <line x1={PADL} y1={ys(p)} x2={W - PADR} y2={ys(p)} stroke="var(--ink-2)" strokeWidth="0.5" opacity="0.25" />
          <text x={PADL - 6} y={ys(p) + 3} textAnchor="end" fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono">{(p * 100).toFixed(0)}%</text>
        </g>
      ))}
      {/* earnings wall */}
      {data.earnDays != null && data.earnDays <= data.horizon && (
        <g><rect x={xs(data.earnDays)} y={PADT} width={Math.max(2, xs(data.horizon) - xs(data.earnDays))} height={H - PADT - PADB} fill="var(--rd)" opacity="0.07" />
          {vline(data.earnDays, "var(--rd)", "4 2")}
          <text x={xs(data.earnDays) + 3} y={PADT + 10} fontSize="8.5" fill="var(--rd)" fontFamily="JetBrains Mono">ER S{data.earnDays}</text></g>
      )}
      {vline(data.decayT1, "var(--copper)")}
      {vline(data.hardStop, "var(--amb)", "1 2")}
      {/* 95% CI ribbon on the reach curve */}
      {ciBand && <path d={ciBand} fill="var(--gn)" opacity="0.12" stroke="none" />}
      {/* curves */}
      <path d={path("sOp")} fill="none" stroke="var(--ink-2)" strokeWidth="1" strokeDasharray="2 3" opacity="0.55" />
      <path d={path("sSt")} fill="none" stroke="var(--rd)" strokeWidth="1.4" opacity="0.8" />
      {data.medianT2 != null && <path d={path("sT2")} fill="none" stroke="var(--violet)" strokeWidth="2" />}
      <path d={path("sT1")} fill="none" stroke="var(--gn)" strokeWidth="2.2" />
      {/* x ticks */}
      {[0, Math.round(data.horizon / 3), Math.round(2 * data.horizon / 3), data.horizon].map((s) => (
        <text key={s} x={xs(s)} y={H - PADB + 14} textAnchor="middle" fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono">S{s}</text>
      ))}
    </svg>
  );
}

function TaTile({ k, v, sub, tone }) {
  return (
    <div style={{ background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 10, padding: "10px 12px", minWidth: 0 }}>
      <div className="label-cap mono" style={{ fontSize: 9.5, color: "var(--ink-2)", letterSpacing: ".12em" }}>{k}</div>
      <div className="mono" style={{ fontSize: 19, fontWeight: 600, color: tone ? `var(--${tone})` : "var(--ink-0)", marginTop: 2 }}>{v}</div>
      {sub && <div className="mono dim2" style={{ fontSize: 10, marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

function LensTime({ ticker, mode }) {
  const ta = useTAm(() => timeAnatomy(ticker, mode), [ticker && ticker.symbol, mode]);
  if (!ta) return null;
  if (!ta.ok) {
    return <div className="lens-pad" style={{ padding: 20 }}>
      <div className="mono" style={{ color: "var(--amb)", fontSize: 13 }}>⏱ TIME ANATOMY — NO ESTIMATE</div>
      <div className="mono dim2" style={{ fontSize: 12, marginTop: 8 }}>{ta.reason}</div>
    </div>;
  }
  const sess = (n) => n == null ? "—" : "S" + n;
  // ── derive the quant read from the curve (natural frequencies + time distribution) ──
  const ceil = Math.min(ta.ceiling, ta.curve.length - 1);
  const atC = ta.curve[ceil] || ta.curve[ta.curve.length - 1];
  let reached = Math.round((atC.sT1 || 0) * 100);
  let stopped = Math.round((atC.sSt || 0) * 100);
  let openN = Math.max(0, 100 - reached - stopped);
  const pctlSess = (frac) => { const tgt = ta.pHitT1 * frac; for (let s = 0; s < ta.curve.length; s++) if ((ta.curve[s].sT1 || 0) >= tgt) return s; return null; };
  const p25 = pctlSess(0.25), p75 = pctlSess(0.75);
  // time stop = decay threshold, but never beyond the mode's hard ceiling
  const timeStop = Math.min(ta.decayT1 != null ? ta.decayT1 : ta.hardStop, ta.hardStop);
  // verdict
  let verdict, vtone;
  if (ta.earnWallT2) { verdict = "HOLD TO T1 · TRIM INTO ER"; vtone = "amb"; }
  else if (reached >= stopped + 8) { verdict = "FAVORABLE CLOCK"; vtone = "gn"; }
  else if (stopped >= reached + 12) { verdict = "STOP-HEAVY · TIGHT TIME BUDGET"; vtone = "rd"; }
  else { verdict = "BALANCED CLOCK"; vtone = "amb"; }
  const readMedian = ta.medianT1 != null ? `a median of ${ta.medianT1} sessions${p75 != null ? ` (a quarter need >${p75})` : ""}` : "an uncertain horizon";
  // ── LIVE conditional monitor: if this ticker is a held position, re-read the clock given days_held ──
  let monitor = null;
  const pos = ((window.__BV && window.__BV.portfolio && window.__BV.portfolio.positions) || []).find(p => p.ticker === ticker.symbol);
  if (pos && pos.days_held != null) {
    const k = Math.min(pos.days_held, ta.curve.length - 1);
    const ck = ta.curve[k] || ta.curve[ta.curve.length - 1];
    const sOpenK = Math.max(0.02, ck.sOp || 0);
    const condReach = Math.max(0, Math.min(1, (ta.pHitT1 - (ck.sT1 || 0)) / sOpenK));  // remaining reach mass / still-open
    const entryP = parseFloat(pos.entry_price), stopP = parseFloat(pos.stop);
    const oneRpct = (entryP && stopP && entryP > stopP) ? (entryP - stopP) / entryP * 100 : null;
    const gainR = (oneRpct && pos.unrealized_pnl_pct != null) ? pos.unrealized_pnl_pct / oneRpct : null;
    const pastZone = k >= (ta.captureHi != null ? ta.captureHi : ta.medianT1 || 99);
    const stall = pastZone && gainR != null && gainR < 0.3;
    const pastStop = k >= timeStop;
    monitor = { k, condReach, gainR, stall, pastStop, pnlPct: pos.unrealized_pnl_pct };
  }

  return (
    <div className="lens-pad" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div className="mono" style={{ fontSize: 15, fontWeight: 700, color: "var(--copper)", letterSpacing: ".04em" }}>⏱ TIME ANATOMY</div>
        <span className="mono dim2" style={{ fontSize: 12 }}>how long until this hits its target — or times out?</span>
        {ta.source === "calibrated"
          ? <span className="mono" style={{ marginLeft: "auto", fontSize: 10, padding: "3px 8px", borderRadius: 999, background: "color-mix(in oklab, var(--gn) 16%, var(--bg-1))", color: "var(--gn)", border: "1px solid color-mix(in oklab, var(--gn) 35%, transparent)" }}>CALIBRATED · {ta.confidence.level} · n={ta.confidence.analogues.toLocaleString()}</span>
          : <span className="mono" style={{ marginLeft: "auto", fontSize: 10, padding: "3px 8px", borderRadius: 999, background: "color-mix(in oklab, var(--amb) 16%, var(--bg-1))", color: "var(--amb)", border: "1px solid color-mix(in oklab, var(--amb) 35%, transparent)" }}>MODELED · NO ANALOGUES</span>}
      </div>

      {/* ── THE READ — plain-English synthesis + verdict ── */}
      <div style={{ background: "linear-gradient(180deg, color-mix(in oklab, var(--copper) 9%, var(--bg-1)), var(--bg-1))", border: "1px solid color-mix(in oklab, var(--copper) 30%, transparent)", borderRadius: 12, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span className="label-cap mono" style={{ fontSize: 10, color: "var(--copper)", letterSpacing: ".14em" }}>THE READ</span>
          <span className="mono" style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999, color: `var(--${vtone})`, background: `color-mix(in oklab, var(--${vtone}) 14%, transparent)`, border: `1px solid color-mix(in oklab, var(--${vtone}) 35%, transparent)` }}>{verdict}</span>
        </div>
        <div className="mono" style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ink-0)" }}>
          Across <b>{ta.confidence.analogues != null ? ta.confidence.analogues.toLocaleString() : "—"}</b> historical setups in <i>this exact context</i>, by your <b>{ta.holdMode}</b> horizon (<b>S{ta.ceiling}</b>): <b className="gn">{reached}</b> reached T1 first, <b className="rd">{stopped}</b> stopped out first. The ones that worked hit T1 in {readMedian}. <b>Edge decays after S{timeStop}</b> — exit there if still unresolved.{ta.earnWallT2 ? <span> Earnings land at <b className="rd">S{ta.earnDays}</b>, before the T2 median — treat as <b>T1-only into the event</b>.</span> : (ta.medianT2 != null ? <span> A runner to T2 needs a median <b>S{ta.medianT2}</b>.</span> : null)}
        </div>
      </div>

      {/* ── LIVE MONITOR — only when this is a held position (conditional re-read) ── */}
      {monitor && (
        <div style={{ background: monitor.stall || monitor.pastStop ? "color-mix(in oklab, var(--rd) 11%, var(--bg-1))" : "color-mix(in oklab, var(--gn) 9%, var(--bg-1))", border: `1px solid color-mix(in oklab, var(--${monitor.stall || monitor.pastStop ? "rd" : "gn"}) 32%, transparent)`, borderRadius: 10, padding: "10px 14px", display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
          <span className="mono" style={{ fontSize: 11, fontWeight: 700, color: monitor.stall || monitor.pastStop ? "var(--rd)" : "var(--gn)" }}>● LIVE · HELD {monitor.k} SESSION{monitor.k === 1 ? "" : "S"}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-0)" }}>given still open at S{monitor.k}, P(T1 from here) <b>{(monitor.condReach * 100).toFixed(0)}%</b></span>
          {monitor.gainR != null && <span className="mono dim2" style={{ fontSize: 12 }}>· at {monitor.gainR >= 0 ? "+" : ""}{monitor.gainR.toFixed(2)}R</span>}
          {monitor.pastStop
            ? <span className="mono" style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "var(--rd)" }}>⏲ PAST TIME STOP (S{timeStop}) — edge decayed, free the slot</span>
            : monitor.stall
              ? <span className="mono" style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "var(--rd)" }}>⚠ STALL — past capture zone with &lt;0.3R, soft-exit watch</span>
              : <span className="mono" style={{ marginLeft: "auto", fontSize: 11, color: "var(--gn)" }}>within capture window · clock OK</span>}
        </div>
      )}

      {/* ── NATURAL FREQUENCY — the competing-risk outcome, in plain counts ── */}
      <div>
        <div className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em", marginBottom: 6 }}>OUT OF 100 SETUPS LIKE THIS · BY YOUR S{ta.ceiling} HORIZON</div>
        <div style={{ display: "flex", height: 30, borderRadius: 8, overflow: "hidden", border: "1px solid var(--ink-2)" }}>
          {reached > 0 && <div style={{ width: reached + "%", background: "color-mix(in oklab, var(--gn) 80%, transparent)", display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono" style={{ fontSize: 11, fontWeight: 700, color: "#071" }}>{reached}</span></div>}
          {stopped > 0 && <div style={{ width: stopped + "%", background: "color-mix(in oklab, var(--rd) 78%, transparent)", display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono" style={{ fontSize: 11, fontWeight: 700, color: "#400" }}>{stopped}</span></div>}
          {openN > 0 && <div style={{ width: openN + "%", background: "var(--ink-2)", display: "flex", alignItems: "center", justifyContent: "center" }}><span className="mono" style={{ fontSize: 11, color: "var(--ink-0)" }}>{openN}</span></div>}
        </div>
        <div style={{ display: "flex", gap: 18, marginTop: 5 }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--gn)" }}>■ {reached} reached T1 first</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--rd)" }}>■ {stopped} stopped out first</span>
          <span className="mono dim2" style={{ fontSize: 11 }}>■ {openN} still open (timed out)</span>
        </div>
      </div>

      {/* ── TIME-TO-T1 distribution (those that reached) ── */}
      {ta.medianT1 != null && (
        <div>
          <div className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em", marginBottom: 6 }}>IF IT WORKS · SESSIONS TO T1</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6 }}>
            {[["P10", pctlSess(0.1)], ["P25", p25], ["MEDIAN", ta.medianT1], ["P75", p75], ["P90", pctlSess(0.9)]].map(([k, v]) => (
              <div key={k} style={{ textAlign: "center", padding: "7px 4px", background: k === "MEDIAN" ? "color-mix(in oklab, var(--gn) 14%, var(--bg-1))" : "var(--bg-1)", border: "1px solid " + (k === "MEDIAN" ? "color-mix(in oklab, var(--gn) 40%, transparent)" : "var(--ink-2)"), borderRadius: 8 }}>
                <div className="mono dim2" style={{ fontSize: 9.5 }}>{k}</div>
                <div className="mono" style={{ fontSize: 16, fontWeight: 600, color: k === "MEDIAN" ? "var(--gn)" : "var(--ink-0)" }}>{sess(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── decision tiles ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
        <TaTile k="TIME STOP" v={sess(timeStop)} sub="exit if unresolved" tone="copper" />
        <TaTile k="HARD CEILING" v={sess(ta.hardStop)} sub={`${ta.holdMode} max ${ta.ceiling}`} tone="amb" />
        <TaTile k="→ T2 MEDIAN" v={sess(ta.medianT2)} sub={ta.earnWallT2 ? "post-ER" : (ta.distT2 != null ? ta.distT2 + " ATR away" : "—")} tone="violet" />
        <TaTile k="P(T2 | T1)" v={ta.pT2givenT1 == null ? "—" : (ta.pT2givenT1 * 100).toFixed(0) + "%"} sub="runner reaches T2" tone="violet" />
      </div>

      {/* ── survival chart ── */}
      <div style={{ background: "var(--bg-1)", border: "1px solid var(--ink-2)", borderRadius: 12, padding: "12px 14px" }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 6 }}>
          <span className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em" }}>CUMULATIVE PROBABILITY BY SESSION</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--gn)", marginLeft: "auto" }}>━ reached T1</span>
          {ta.medianT2 != null && <span className="mono" style={{ fontSize: 11, color: "var(--violet)" }}>━ reached T2</span>}
          <span className="mono" style={{ fontSize: 11, color: "var(--rd)" }}>━ stopped out</span>
          <span className="mono dim2" style={{ fontSize: 11 }}>┈ still open</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--copper)" }}>┊ time stop S{timeStop}</span>
        </div>
        <TaCurve data={ta} />
      </div>

      {ta.earnWallT2 && (
        <div style={{ background: "color-mix(in oklab, var(--rd) 10%, var(--bg-1))", border: "1px solid color-mix(in oklab, var(--rd) 35%, transparent)", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, lineHeight: 1.5, color: "var(--ink-1)" }}>
          <b className="rd">⛔ EARNINGS WALL.</b> Earnings in ~<b>{ta.earnDays}</b> sessions but T2 typically needs <b>S{ta.medianT2}</b> — T2 is <b>not reachable pre-earnings</b>. Trade it as <b>T1-only into the event</b>, trim at T1, then re-evaluate the runner once the binary resolves.
        </div>
      )}

      {/* ── conditions in plain English ── */}
      <div>
        <div className="label-cap mono" style={{ fontSize: 10, color: "var(--ink-2)", letterSpacing: ".12em", marginBottom: 6 }}>WHY THIS CLOCK · THE 6 LIVE CONDITIONS MATCHED</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 6 }}>
          {[["Market regime", ta.buckets.V1], ["Volatility", ta.buckets.V2], ["Relative strength", ta.buckets.V3], ["Setup × quality", ta.buckets.V4], ["Distance to T1", ta.buckets.V5], ["Distance to T2", ta.buckets.V6]].map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 10px", background: "var(--bg-1)", borderRadius: 7, border: "1px solid var(--ink-2)" }}>
              <span className="mono dim2" style={{ fontSize: 10.5 }}>{k}</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-0)", fontWeight: 600 }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mono dim2" style={{ fontSize: 10.5, lineHeight: 1.5, borderTop: "1px solid var(--ink-2)", paddingTop: 8 }}>
        Confidence: <b className={ta.source === "calibrated" ? (ta.confidence.level === "HIGH" ? "gn" : ta.confidence.level === "MED" ? "amb" : "rd") : "amb"}>{ta.confidence.level}</b> — {ta.confidence.note}.
        {ta.source === "calibrated"
          ? ` Empirical competing-risk survival from cached daily bars (${ta.confidence.dateRange ? ta.confidence.dateRange[0] + "→" + ta.confidence.dateRange[1] : "multi-year"}), matched on the 6 live conditions (k-nearest collapse for sparse cells). It estimates the time-to-resolution distribution for setups like this — not a prediction for this specific name. v1 window ~3y; the 20-yr rebuild widens regime coverage.`
          : " Parametric estimate seeded by the live conditions — shown only because no calibrated analogues matched."}
        {" "}Informational & educational · not advice.
      </div>
    </div>
  );
}
window.LensTime = LensTime;
