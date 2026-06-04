// patterns-montecarlo.jsx — Monte Carlo path simulation, real-data wired.
//
// REAL DATA: drift + vol are estimated from the asset's own block-bootstrapped
// log-return history, fetched via /api/pattern/montecarlo/{sym}?mode={mode}.
// The Python engine (engines/montecarlo.py) runs 2 000 paths, computes the
// percentile cone, terminal histogram, and P(T1 before stop). When the server
// is absent (standalone showcase) or returns state:"none", we fall back to the
// illustrative fixture below — and the header badge says so honestly.

const { useMemo: useMemoMc } = React;

// ── fixture model (fallback only — used in standalone showcase) ─────────────
// These constants are kept as-is so the standalone BullVeda.dev.html still
// renders without a server. The fixture uses 500 paths / 90 days for speed.
const MC_FIXTURE_N    = 500;
const MC_FIXTURE_DAYS = 90;

function _buildFixture(ticker) {
  const start = (ticker && ticker.price) || 213.4;
  const seed  = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x9a7;
  const t1 = start * 1.054, stop = start * 0.966;
  const rng  = mulberry32(seed);
  const gauss = () => { let u = 0, v = 0; while (!u) u = rng(); while (!v) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const drift = 0.0009, vol = 0.0135;
  const N = MC_FIXTURE_N, DAYS = MC_FIXTURE_DAYS;
  const paths = [], terminal = [];
  let t1First = 0, stopFirst = 0;
  for (let p = 0; p < N; p++) {
    let px = start; const arr = [px]; let hit = null;
    for (let d = 0; d < DAYS; d++) {
      px = px * (1 + drift + vol * gauss());
      arr.push(px);
      if (!hit) { if (px >= t1) { hit = "t1"; t1First++; } else if (px <= stop) { hit = "stop"; stopFirst++; } }
    }
    paths.push(arr); terminal.push(px);
  }
  const bands = { p10: [], p25: [], p50: [], p75: [], p90: [] };
  for (let d = 0; d <= DAYS; d++) {
    const col = paths.map(p => p[d]).sort((a, b) => a - b);
    const at = q => col[Math.min(N - 1, Math.floor(q * N))];
    bands.p10.push(at(0.1)); bands.p25.push(at(0.25)); bands.p50.push(at(0.5));
    bands.p75.push(at(0.75)); bands.p90.push(at(0.9));
  }
  const term = [...terminal].sort((a, b) => a - b);
  const pct  = q => term[Math.min(N - 1, Math.floor(q * N))];
  const median = pct(0.5);
  const lo = term[0], hi = term[N - 1], nb = 22, bw = (hi - lo) / nb || 1;
  const hist = new Array(nb).fill(0);
  term.forEach(t => { hist[Math.min(nb - 1, Math.floor((t - lo) / bw))]++; });
  return {
    start, t1, stop,
    numPaths: N, numDays: DAYS,
    median, skew: 0.05,
    bands,
    p: { p5: pct(0.05), p25: pct(0.25), p50: median, p75: pct(0.75), p95: pct(0.95) },
    t1First: t1First / N, stopFirst: stopFirst / N,
    hist, histLo: lo, histHi: hi,
    bars: [],   // no chart bars in fixture (the chart uses MCCone directly)
    read: null, // suppressed in mock state
  };
}

// ── data hook: real → fixture fallback (mode-aware) ─────────────────────────
function useMonteCarloModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("montecarlo", ticker, mode);
  const tf      = (real && real.meta && real.meta.tf) || null;
  const fixture = useMemoMc(() => _buildFixture(ticker), [sym]);

  // fully formed real payload?
  const usable = (
    state === "loaded" &&
    real && real.ok &&
    real.state === "real" &&
    real.bands && real.bands.p50 && real.bands.p50.length > 1
  );

  if (usable) {
    return {
      mc: {
        start:    real.start,
        t1:       real.t1,
        stop:     real.stop,
        numPaths: real.numPaths || 2000,
        numDays:  real.numDays  || 10,
        skew:     real.skew     || 0,
        median:   real.median,
        bands:    real.bands,
        p:        real.p,
        t1First:  real.t1First,
        stopFirst: real.stopFirst,
        hist:     real.hist     || [],
        histLo:   real.histLo,
        histHi:   real.histHi,
        bars:     real.bars     || [],
        read:     real.read     || null,
      },
      state: "real", sym, tf, usable: true,
    };
  }

  // real feed returned nothing useful
  if (state === "loaded" && real && real.ok) {
    return {
      mc: fixture,
      state: "none", sym, tf, usable: false,
      message: (real && real.message) || "No usable bar history for simulation.",
    };
  }

  // pre-load or no server
  return {
    mc: fixture,
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── probability cone SVG ─────────────────────────────────────────────────────
function MCCone({ mc }) {
  const [ref, w] = useWidth(900);
  const h = 240, padR = 64, padL = 8, padT = 12;
  const plotW = w - padR - padL, plotR = padL + plotW, plotH = h - padT - 16;
  const numDays = (mc.bands && mc.bands.p50 && mc.bands.p50.length - 1) || (mc.numDays || 90);
  const allLo = Math.min(...(mc.bands.p10 || [mc.stop]), mc.stop);
  const allHi = Math.max(...(mc.bands.p90 || [mc.t1]),  mc.t1);
  const pad = (allHi - allLo) * 0.06, lo = allLo - pad, hi = allHi + pad;
  const xOf = d => padL + (d / numDays) * plotW;
  const yOf = v => padT + plotH - ((v - lo) / (hi - lo)) * plotH;
  const pts  = arr => arr.map((v, d) => `${xOf(d).toFixed(1)},${yOf(v).toFixed(1)}`);
  const area = (top, bot) => `M ${pts(top).join(" L ")} L ${pts(bot).slice().reverse().join(" L ")} Z`;
  const lvls = [
    [mc.t1,    "gn",    `T1 ${(+mc.t1).toFixed(1)}`,      "5 4"],
    [mc.start, "ink-3", `entry ${(+mc.start).toFixed(1)}`, "1 5"],
    [mc.stop,  "rd",    `stop ${(+mc.stop).toFixed(1)}`,   "5 4"],
  ];
  const b = mc.bands || {};
  return (
    <div className="pv-chart" ref={ref}>
      <svg width={w} height={h}>
        {lvls.map(([v, t, l, dash], k) => (
          <g key={k}>
            <line x1={padL} y1={yOf(v)} x2={plotR} y2={yOf(v)} stroke={`var(--${t})`} strokeDasharray={dash} opacity="0.8" />
            <text x={plotR + 5} y={yOf(v) + 3} fontSize="9.5" className="mono" fill={`var(--${t})`}>{l}</text>
          </g>
        ))}
        {b.p90 && b.p10 && <path d={area(b.p90, b.p10)} fill="var(--violet)" opacity="0.10" />}
        {b.p75 && b.p25 && <path d={area(b.p75, b.p25)} fill="var(--violet)" opacity="0.20" />}
        {b.p90 && <polyline points={pts(b.p90).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="1" opacity="0.4" />}
        {b.p10 && <polyline points={pts(b.p10).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="1" opacity="0.4" />}
        {b.p50 && <polyline points={pts(b.p50).join(" ")} fill="none" stroke="var(--copper)" strokeWidth="2" />}
        <circle cx={xOf(numDays)} cy={yOf(mc.median)} r="3.2" fill="var(--copper)" stroke="var(--bg-1)" strokeWidth="1" />
        <text x={xOf(numDays) - 4} y={yOf(mc.median) - 6} fontSize="9.5" textAnchor="end" className="mono" fill="var(--copper)">
          median {(+mc.median).toFixed(1)}
        </text>
      </svg>
      <div className="mc-cone-leg mono dim2">
        P10–P90 (outer) · P25–P75 (band) · median path (copper) · {(mc.numPaths || 2000).toLocaleString()} paths · {numDays} sessions
      </div>
    </div>
  );
}

// ── terminal distribution histogram ─────────────────────────────────────────
function MCHistogram({ mc }) {
  const w = 1000, h = 150, padT = 8, padB = 18;
  const hist = mc.hist || [];
  if (!hist.length) return null;
  const maxC = Math.max(...hist, 1);
  const bw = w / hist.length;
  const priceAt = k => (mc.histLo || 0) + (k / hist.length) * ((mc.histHi || 1) - (mc.histLo || 0));
  return (
    <div className="pv-chart">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {hist.map((c, k) => {
          const pr  = priceAt(k);
          const t1  = mc.t1   || 0;
          const stp = mc.stop || 0;
          const strt= mc.start|| 0;
          const tone = pr >= t1 ? "gn" : pr <= stp ? "rd" : pr >= strt ? "gn" : "amb";
          const bh = (c / maxC) * (h - padT - padB);
          return <rect key={k} x={k * bw + 1} y={h - padB - bh} width={bw - 2} height={bh} fill={`var(--${tone})`} opacity="0.55" />;
        })}
        {[mc.start, mc.median].map((v, i) => {
          const x = ((v - (mc.histLo || 0)) / ((mc.histHi || 1) - (mc.histLo || 0))) * w;
          return <line key={i} x1={x} y1={padT} x2={x} y2={h - padB} stroke={`var(--${i === 0 ? "ink-2" : "copper"})`} strokeDasharray="3 3" />;
        })}
        <text x={6} y={h - 5} fontSize="9.5" className="mono" fill="var(--ink-3)">${(+(mc.histLo || 0)).toFixed(0)}</text>
        <text x={w - 6} y={h - 5} fontSize="9.5" textAnchor="end" className="mono" fill="var(--ink-3)">${(+(mc.histHi || 0)).toFixed(0)}</text>
        <text x={w / 2} y={h - 5} fontSize="9.5" textAnchor="middle" className="mono" fill="var(--copper)">
          terminal price · {mc.numDays || 90} sessions
        </text>
      </svg>
    </div>
  );
}

// ── percentile ladder ────────────────────────────────────────────────────────
function MCPercentiles({ mc }) {
  const start = mc.start || 1;
  const r = v => ((v / start - 1) * 100);
  const p = mc.p || {};
  const rows = [
    { q: "P95 · bull tail", v: p.p95, tone: "gn" },
    { q: "P75 · bull case", v: p.p75, tone: "gn" },
    { q: "P50 · median",    v: p.p50, tone: "copper" },
    { q: "P25 · bear case", v: p.p25, tone: "amb" },
    { q: "P5  · bear tail", v: p.p5,  tone: "rd" },
  ].filter(x => x.v != null);
  return <MiniTable
    cols={[{ h: "Percentile", k: "q" }, { h: "Price", k: "price", mono: true, align: "right" }, { h: "Return", k: "ret", mono: true, align: "right" }]}
    rows={rows.map(x => ({
      q:     <b style={{ color: `var(--${x.tone})` }}>{x.q}</b>,
      price: <b>${(+x.v).toFixed(1)}</b>,
      ret:   <span className={r(x.v) >= 0 ? "up" : "dn"}>{r(x.v) >= 0 ? "+" : ""}{r(x.v).toFixed(1)}%</span>,
    }))} />;
}

// ── header stat strip ────────────────────────────────────────────────────────
function MCStat({ mc }) {
  const start  = mc.start  || 1;
  const median = mc.median || start;
  const medR   = ((median / start - 1) * 100);
  const t1F    = mc.t1First   || 0;
  const stpF   = mc.stopFirst || 0;
  const t1     = mc.t1   || start;
  const stop   = mc.stop || start;
  const edge   = t1F * (t1 / start - 1) - stpF * (1 - stop / start);
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell">
        <div className="label-cap">Median {mc.numDays || 90}d</div>
        <div className={`pv-stat-v mono ${medR >= 0 ? "up" : "dn"}`}>{medR >= 0 ? "+" : ""}{medR.toFixed(1)}%</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">P(T1 first)</div>
        <div className="pv-stat-v mono up">{Math.round(t1F * 100)}%</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">P(stop first)</div>
        <div className="pv-stat-v mono warn">{Math.round(stpF * 100)}%</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Edge</div>
        <div className={`pv-stat-v mono ${edge >= 0 ? "up" : "dn"}`}>{edge >= 0 ? "+" : ""}{(edge * 100).toFixed(1)}%</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Paths</div>
        <div className="pv-stat-v mono">{(mc.numPaths || 2000).toLocaleString()}</div>
      </div>
    </div>
  );
}

// ── skew / stat extras (shown only in real mode) ─────────────────────────────
function MCStatExtra({ mc, tf }) {
  const stat = mc && typeof mc.skew !== "undefined" ? mc : null;
  if (!stat) return null;
  const skewLabel = stat.skew > 0.15 ? "right-skewed ▶" : stat.skew < -0.15 ? "left-skewed ◀" : "symmetric ≈";
  const skewTone  = stat.skew > 0.1 ? "gn" : stat.skew < -0.1 ? "rd" : "ink-2";
  return (
    <div className="pv-stat" style={{ marginTop: 4 }}>
      <div className="pv-stat-cell">
        <div className="label-cap">Distribution skew</div>
        <div className="pv-stat-v mono" style={{ color: `var(--${skewTone})` }}>{skewLabel}</div>
      </div>
      <div className="pv-stat-cell">
        <div className="label-cap">Timeframe</div>
        <div className="pv-stat-v mono">{tf || "Daily"}</div>
      </div>
    </div>
  );
}

// ── read box ─────────────────────────────────────────────────────────────────
function MCRead({ mc, state }) {
  const start  = mc.start  || 1;
  const median = mc.median || start;
  const medR   = ((median / start - 1) * 100);
  const t1F    = mc.t1First   || 0;
  const stpF   = mc.stopFirst || 0;
  const t1     = mc.t1   || start;
  const stop   = mc.stop || start;
  const edge   = t1F * (t1 / start - 1) - stpF * (1 - stop / start);

  // prefer the server-generated read in real mode
  if (state === "real" && mc.read) {
    return (
      <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)" }}>
        <span className="label-cap">Read</span>
        <span className="mono">{mc.read}</span>
      </div>
    );
  }

  // fixture / loading fallback (generic copy)
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)" }}>
      <span className="label-cap">Read</span>
      <span className="mono">
        Distribution is {mc.skew > 0.1 ? "right-skewed" : mc.skew < -0.1 ? "left-skewed" : "roughly symmetric"}:
        median <b className={medR >= 0 ? "up" : "dn"}>{medR >= 0 ? "+" : ""}{medR.toFixed(1)}%</b>,
        P(reach T1 before stop) <b className="up">{Math.round(t1F * 100)}%</b> vs
        P(stop first) <b className="warn">{Math.round(stpF * 100)}%</b> — {" "}
        <b className={edge >= 0 ? "up" : "dn"}>{edge >= 0 ? "positive" : "negative"} expectancy</b>,
        conditional on the setup holding.
      </span>
    </div>
  );
}

// ── main view (3 layout directions) ─────────────────────────────────────────
function MonteCarloView({ ticker, dir, mode }) {
  const { mc, state, message, sym, tf, usable } = useMonteCarloModel(ticker, mode);

  // source badge (using shared PatternSrcBadge)
  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tf={tf} />
    </div>
  );

  // honest empty state (server responded but no usable bars)
  if (state === "none") {
    return (
      <div className="pv-view">
        {SrcBar}
        <div className="pv-empty">
          <div className="pv-empty-i mono">— no simulation data</div>
          <div className="pv-empty-msg">{message || `Insufficient bar history to simulate ${sym || "this asset"}.`}</div>
          <div className="pv-empty-sub mono dim2">The engine requires ≥30 historical bars. When data is available it will populate automatically.</div>
        </div>
      </div>
    );
  }

  const cone = (
    <>
      <SectionHeader n={1} title="Cone of outcomes"
        sub={`${(mc.numPaths || 2000).toLocaleString()} ${state === "real" ? "block-bootstrapped" : "simulated"} paths · ${mc.numDays || 90} sessions`}
        style="minimal" />
      <div className="pv-pad"><MCCone mc={mc} /></div>
    </>
  );

  const dist = (
    <>
      <SectionHeader n={2} title="Terminal distribution"
        sub={`where price lands after ${mc.numDays || 90} sessions`}
        style="minimal" />
      <div className="pv-pad"><MCHistogram mc={mc} /></div>
    </>
  );

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        <MCStat mc={mc} />
        {state === "real" && <MCStatExtra mc={mc} tf={tf} />}
        <div className="pv-pad"><MCCone mc={mc} /></div>
        <div className="pv-2col">
          <div>
            <div className="pv-block-h label-cap">Terminal distribution</div>
            <div style={{ padding: "0 16px" }}><MCHistogram mc={mc} /></div>
          </div>
          <div>
            <div className="pv-block-h label-cap">Percentile ladder</div>
            <MCPercentiles mc={mc} />
          </div>
        </div>
        <div className="pv-pad"><MCRead mc={mc} state={state} /></div>
      </div>
    );
  }

  if (dir === "B") {
    return (
      <div className="pv-view">
        {SrcBar}
        <MCStat mc={mc} />
        {state === "real" && <MCStatExtra mc={mc} tf={tf} />}
        <div className="pv-split">
          <div className="pv-split-main">{cone}{dist}</div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Percentile ladder" style="minimal" />
            <div className="pv-pad"><MCPercentiles mc={mc} /></div>
            <div className="pv-pad"><MCRead mc={mc} state={state} /></div>
          </div>
        </div>
      </div>
    );
  }

  // A — chart-led (default)
  return (
    <div className="pv-view">
      {SrcBar}
      <MCStat mc={mc} />
      {state === "real" && <MCStatExtra mc={mc} tf={tf} />}
      {cone}
      <div className="pv-2col">
        <div>
          <div className="pv-block-h label-cap">Terminal distribution</div>
          <div style={{ padding: "0 16px" }}><MCHistogram mc={mc} /></div>
        </div>
        <div>
          <div className="pv-block-h label-cap">Percentile ladder</div>
          <MCPercentiles mc={mc} />
        </div>
      </div>
      <div className="pv-pad"><MCRead mc={mc} state={state} /></div>
    </div>
  );
}

// ── dynamic read line (for lens summary / overview) ──────────────────────────
function MonteCarloReadLine({ ticker, mode }) {
  const { mc, state } = useMonteCarloModel(ticker, mode);
  if (state !== "real") {
    const start = (ticker && ticker.price) || 213.4;
    return (
      <span className="mono">
        Monte Carlo (illustrative): median <b className="up">+{((mc.median / mc.start - 1) * 100).toFixed(1)}%</b>,
        P(T1 first) <b className="up">{Math.round(mc.t1First * 100)}%</b> — connect to live data for asset-specific paths.
      </span>
    );
  }
  const t1F  = mc.t1First   || 0;
  const stpF = mc.stopFirst || 0;
  const med  = mc.median    || mc.start;
  const medR = ((med / mc.start - 1) * 100);
  const t1   = mc.t1   || mc.start;
  const stop = mc.stop || mc.start;
  const edge = t1F * (t1 / mc.start - 1) - stpF * (1 - stop / mc.start);
  return (
    <span className="mono">
      Block-bootstrapped {(mc.numPaths || 2000).toLocaleString()} paths · {mc.numDays || 10} sessions:
      median <b className={medR >= 0 ? "up" : "dn"}>{medR >= 0 ? "+" : ""}{medR.toFixed(1)}%</b>,
      P(T1 first) <b className="up">{Math.round(t1F * 100)}%</b> vs
      P(stop) <b className="warn">{Math.round(stpF * 100)}%</b> —
      <b className={edge >= 0 ? "up" : "dn"}> {edge >= 0 ? "positive" : "negative"} expectancy</b>
      {mc.skew > 0.1 ? ", right-skewed" : mc.skew < -0.1 ? ", left-skewed" : ""}.
    </span>
  );
}

Object.assign(window, { MonteCarloView, MonteCarloReadLine });
