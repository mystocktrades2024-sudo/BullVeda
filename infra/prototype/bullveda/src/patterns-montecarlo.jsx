// patterns-montecarlo.jsx — Monte Carlo path simulation. Setup-conditional cone,
// terminal-outcome distribution, percentile ladder, and bull/base/bear scenarios.

const { useMemo: useMemoMc } = React;
const MC_N = 500, MC_DAYS = 90;

function useMonteCarlo(ticker) {
  const start = (ticker && ticker.price) || 213.4;
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x9a7;
  return useMemoMc(() => {
    const t1 = start * 1.054, stop = start * 0.966;     // targets relative to entry
    const rng = mulberry32(seed);
    const gauss = () => { let u = 0, v = 0; while (!u) u = rng(); while (!v) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    const drift = 0.0009, vol = 0.0135;
    const paths = [], terminal = [];
    let t1First = 0, stopFirst = 0;
    for (let p = 0; p < MC_N; p++) {
      let px = start; const arr = [px]; let hit = null;
      for (let d = 0; d < MC_DAYS; d++) {
        px = px * (1 + drift + vol * gauss());
        arr.push(px);
        if (!hit) { if (px >= t1) { hit = "t1"; t1First++; } else if (px <= stop) { hit = "stop"; stopFirst++; } }
      }
      paths.push(arr); terminal.push(px);
    }
    // per-day percentile bands → the cone
    const bands = { p10: [], p25: [], p50: [], p75: [], p90: [] };
    for (let d = 0; d <= MC_DAYS; d++) {
      const col = paths.map(p => p[d]).sort((a, b) => a - b);
      const at = q => col[Math.min(MC_N - 1, Math.floor(q * MC_N))];
      bands.p10.push(at(0.1)); bands.p25.push(at(0.25)); bands.p50.push(at(0.5)); bands.p75.push(at(0.75)); bands.p90.push(at(0.9));
    }
    const term = [...terminal].sort((a, b) => a - b);
    const pct = q => term[Math.min(MC_N - 1, Math.floor(q * MC_N))];
    const median = pct(0.5);
    const lo = term[0], hi = term[MC_N - 1], nb = 22, bw = (hi - lo) / nb || 1;
    const hist = new Array(nb).fill(0);
    term.forEach(t => { hist[Math.min(nb - 1, Math.floor((t - lo) / bw))]++; });
    return {
      start, t1, stop, paths, terminal: term, median, bands,
      p: { p5: pct(0.05), p25: pct(0.25), p50: median, p75: pct(0.75), p95: pct(0.95) },
      t1First: t1First / MC_N, stopFirst: stopFirst / MC_N,
      hist, histLo: lo, histHi: hi,
    };
  }, [start, seed]);
}

function MCCone({ mc }) {
  const [ref, w] = useWidth(900);
  const h = 240, padR = 64, padL = 8, padT = 12;
  const plotW = w - padR - padL, plotR = padL + plotW, plotH = h - padT - 16;
  const allLo = Math.min(...mc.bands.p10, mc.stop), allHi = Math.max(...mc.bands.p90, mc.t1);
  const pad = (allHi - allLo) * 0.06, lo = allLo - pad, hi = allHi + pad;
  const xOf = d => padL + (d / MC_DAYS) * plotW;
  const yOf = v => padT + plotH - ((v - lo) / (hi - lo)) * plotH;
  const pts = arr => arr.map((v, d) => `${xOf(d).toFixed(1)},${yOf(v).toFixed(1)}`);
  const area = (top, bot) => `M ${pts(top).join(" L ")} L ${pts(bot).slice().reverse().join(" L ")} Z`;
  const lvls = [[mc.t1, "gn", `T1 ${mc.t1.toFixed(1)}`, "5 4"], [mc.start, "ink-3", `entry ${mc.start.toFixed(1)}`, "1 5"], [mc.stop, "rd", `stop ${mc.stop.toFixed(1)}`, "5 4"]];
  return (
    <div className="pv-chart" ref={ref}>
      <svg width={w} height={h}>
        {lvls.map(([v, t, l, dash], k) => (
          <g key={k}>
            <line x1={padL} y1={yOf(v)} x2={plotR} y2={yOf(v)} stroke={`var(--${t})`} strokeDasharray={dash} opacity="0.8" />
            <text x={plotR + 5} y={yOf(v) + 3} fontSize="9.5" className="mono" fill={`var(--${t})`}>{l}</text>
          </g>
        ))}
        <path d={area(mc.bands.p90, mc.bands.p10)} fill="var(--violet)" opacity="0.10" />
        <path d={area(mc.bands.p75, mc.bands.p25)} fill="var(--violet)" opacity="0.20" />
        <polyline points={pts(mc.bands.p90).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="1" opacity="0.4" />
        <polyline points={pts(mc.bands.p10).join(" ")} fill="none" stroke="var(--violet)" strokeWidth="1" opacity="0.4" />
        <polyline points={pts(mc.bands.p50).join(" ")} fill="none" stroke="var(--copper)" strokeWidth="2" />
        <circle cx={xOf(MC_DAYS)} cy={yOf(mc.median)} r="3.2" fill="var(--copper)" stroke="var(--bg-1)" strokeWidth="1" />
        <text x={xOf(MC_DAYS) - 4} y={yOf(mc.median) - 6} fontSize="9.5" textAnchor="end" className="mono" fill="var(--copper)">median {mc.median.toFixed(1)}</text>
      </svg>
      <div className="mc-cone-leg mono dim2">P10–P90 (outer) · P25–P75 (band) · median path (copper) · {MC_N} paths · 90 sessions</div>
    </div>
  );
}

function MCHistogram({ mc }) {
  const w = 1000, h = 150, padT = 8, padB = 18;
  const maxC = Math.max(...mc.hist);
  const bw = w / mc.hist.length;
  const priceAt = k => mc.histLo + (k / mc.hist.length) * (mc.histHi - mc.histLo);
  return (
    <div className="pv-chart">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {mc.hist.map((c, k) => {
          const pr = priceAt(k);
          const tone = pr >= mc.t1 ? "gn" : pr <= mc.stop ? "rd" : pr >= mc.start ? "gn" : "amb";
          const bh = (c / maxC) * (h - padT - padB);
          return <rect key={k} x={k * bw + 1} y={h - padB - bh} width={bw - 2} height={bh} fill={`var(--${tone})`} opacity="0.55" />;
        })}
        {[mc.start, mc.median].map((v, i) => {
          const x = ((v - mc.histLo) / (mc.histHi - mc.histLo)) * w;
          return <line key={i} x1={x} y1={padT} x2={x} y2={h - padB} stroke={`var(--${i === 0 ? "ink-2" : "copper"})`} strokeDasharray="3 3" />;
        })}
        <text x={6} y={h - 5} fontSize="9.5" className="mono" fill="var(--ink-3)">${mc.histLo.toFixed(0)}</text>
        <text x={w - 6} y={h - 5} fontSize="9.5" textAnchor="end" className="mono" fill="var(--ink-3)">${mc.histHi.toFixed(0)}</text>
        <text x={w / 2} y={h - 5} fontSize="9.5" textAnchor="middle" className="mono" fill="var(--copper)">terminal price · 90d</text>
      </svg>
    </div>
  );
}

function MCPercentiles({ mc }) {
  const r = v => ((v / mc.start - 1) * 100);
  const rows = [
    { q: "P95 · bull tail", v: mc.p.p95, tone: "gn" },
    { q: "P75 · bull case", v: mc.p.p75, tone: "gn" },
    { q: "P50 · median", v: mc.p.p50, tone: "copper" },
    { q: "P25 · bear case", v: mc.p.p25, tone: "amb" },
    { q: "P5 · bear tail", v: mc.p.p5, tone: "rd" },
  ];
  return <MiniTable
    cols={[{ h: "Percentile", k: "q" }, { h: "Price", k: "p", mono: true, align: "right" }, { h: "Return", k: "r", mono: true, align: "right" }]}
    rows={rows.map(x => ({ q: <b style={{ color: `var(--${x.tone})` }}>{x.q}</b>, p: <b>${x.v.toFixed(1)}</b>,
      r: <span className={r(x.v) >= 0 ? "up" : "dn"}>{r(x.v) >= 0 ? "+" : ""}{r(x.v).toFixed(1)}%</span> }))} />;
}

function MCStat({ mc }) {
  const medR = ((mc.median / mc.start - 1) * 100);
  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Median 90d</div><div className="pv-stat-v mono up">+{medR.toFixed(1)}%</div></div>
      <div className="pv-stat-cell"><div className="label-cap">P(T1 first)</div><div className="pv-stat-v mono up">{Math.round(mc.t1First * 100)}%</div></div>
      <div className="pv-stat-cell"><div className="label-cap">P(stop first)</div><div className="pv-stat-v mono warn">{Math.round(mc.stopFirst * 100)}%</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Edge</div><div className="pv-stat-v mono up">+{((mc.t1First * (mc.t1 / mc.start - 1) - mc.stopFirst * (1 - mc.stop / mc.start)) * 100).toFixed(1)}%</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Paths</div><div className="pv-stat-v mono">{MC_N.toLocaleString()}</div></div>
    </div>
  );
}

function MonteCarloView({ ticker, dir }) {
  const mc = useMonteCarlo(ticker || { price: 213.4, symbol: "ARGN" });

  const cone = (
    <>
      <SectionHeader n={1} title="Cone of outcomes" sub={`${MC_N} setup-conditional paths · 90 sessions`} style="minimal" />
      <div className="pv-pad"><MCCone mc={mc} /></div>
    </>
  );
  const dist = (
    <>
      <SectionHeader n={2} title="Terminal distribution" sub="where price lands after 90d" style="minimal" />
      <div className="pv-pad"><MCHistogram mc={mc} /></div>
    </>
  );

  if (dir === "C") {
    return (
      <div className="pv-view pv-view--dossier">
        <MCStat mc={mc} />
        <div className="pv-pad"><MCCone mc={mc} /></div>
        <div className="pv-2col">
          <div><div className="pv-block-h label-cap">Terminal distribution</div><div style={{ padding: "0 16px" }}><MCHistogram mc={mc} /></div></div>
          <div><div className="pv-block-h label-cap">Percentile ladder</div><MCPercentiles mc={mc} /></div>
        </div>
      </div>
    );
  }

  if (dir === "B") {
    return (
      <div className="pv-view">
        <MCStat mc={mc} />
        <div className="pv-split">
          <div className="pv-split-main">{cone}{dist}</div>
          <div className="pv-split-side">
            <SectionHeader n={3} title="Percentile ladder" style="minimal" />
            <div className="pv-pad"><MCPercentiles mc={mc} /></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pv-view">
      <MCStat mc={mc} />
      {cone}
      <div className="pv-2col">
        <div><div className="pv-block-h label-cap">Terminal distribution</div><div style={{ padding: "0 16px" }}><MCHistogram mc={mc} /></div></div>
        <div><div className="pv-block-h label-cap">Percentile ladder</div><MCPercentiles mc={mc} /></div>
      </div>
      <div className="pv-pad">
        <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)" }}>
          <span className="label-cap">Read</span>
          <span className="mono">Distribution is right-skewed: median <b className="up">+{((mc.median / mc.start - 1) * 100).toFixed(1)}%</b>, P(reach T1 before stop) <b className="up">{Math.round(mc.t1First * 100)}%</b> vs P(stop first) <b className="warn">{Math.round(mc.stopFirst * 100)}%</b> — positive expectancy, conditional on the setup holding.</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MonteCarloView });
