// patterns-core.jsx — shared engine for the reworked Patterns lens
// Seeded OHLC generation, an annotated candlestick chart (events / waves /
// phase bands / fib lines drawn directly on real bars), confidence bars,
// and the sub-tab + layout-direction controls.

const { useState: usePC, useMemo: useMemoPC, useEffect: useEffPC } = React;

// ── seeded RNG ──────────────────────────────────────────────────
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function seedFromSym(sym = "ARGN") {
  let h = 2166136261;
  for (let i = 0; i < sym.length; i++) { h ^= sym.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

// Build an OHLCV series whose closes pass through anchor points {i, price}.
// dips/peaks: per-bar overrides for wick extremes (e.g. spring undershoot).
// volSpikes: { barIndex: multiplier }.
function buildSeries({ n, anchors, seed = 1, volSpikes = {}, wicks = {} }) {
  const rng = mulberry32(seed);
  const sorted = anchors.slice().sort((a, b) => a.i - b.i);
  const closeAt = (i) => {
    let lo = sorted[0], hi = sorted[sorted.length - 1];
    for (let k = 0; k < sorted.length - 1; k++) {
      if (i >= sorted[k].i && i <= sorted[k + 1].i) { lo = sorted[k]; hi = sorted[k + 1]; break; }
    }
    if (i <= sorted[0].i) return sorted[0].price;
    if (i >= hi.i && hi === sorted[sorted.length - 1]) return hi.price;
    const t = (i - lo.i) / Math.max(1, (hi.i - lo.i));
    // smoothstep for organic curves
    const ts = t * t * (3 - 2 * t);
    return lo.price + (hi.price - lo.price) * ts;
  };
  const bars = [];
  let prevC = closeAt(0);
  const scale = Math.max(...anchors.map(a => a.price)) * 0.012;
  for (let i = 0; i < n; i++) {
    const base = closeAt(i);
    const noise = (rng() - 0.5) * scale * 1.4;
    const c = base + noise;
    const o = prevC + (rng() - 0.5) * scale * 0.7;
    let hi = Math.max(o, c) + rng() * scale * 0.9;
    let lo = Math.min(o, c) - rng() * scale * 0.9;
    if (wicks[i] != null) {
      if (wicks[i] < lo) lo = wicks[i];
      if (wicks[i] > hi) hi = wicks[i];
    }
    const v = (0.5 + rng() * 0.5) * (volSpikes[i] || 1);
    bars.push({ o, c, hi, lo, v });
    prevC = c;
  }
  return bars;
}

// ── annotated candlestick chart ─────────────────────────────────
// measure container width for crisp 1:1 rendering (no SVG stretch)
function useWidth(initial = 900) {
  const ref = React.useRef(null);
  const [w, setW] = usePC(initial);
  useEffPC(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => { const cw = es[0].contentRect.width; if (cw > 0) setW(Math.round(cw)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// props:
//   bars, height
//   bands:   [{from,to,label,tone}]        vertical phase backgrounds (bar idx)
//   hlines:  [{price,label,tone,dash}]      horizontal target/invalidation lines
//   markers: [{i,label,tone,place}]         event/wave labels pinned to a bar's hi/lo
//   skeleton:[{i,price}]  + skeletonTail    polyline through wave pivots
function CandleChart({ bars, height = 300, bands = [], hlines = [], markers = [],
                       skeleton = null, skeletonTail = 0, volume = true, accent = "copper",
                       span = null, projectFrom = null, lines = [], zones = [], profile = null, cloud = null }) {
  const uid = React.useId();
  const [ref, w] = useWidth(900);
  const padR = 54, padL = 8, padT = 12;
  const cols = span || bars.length;
  const volH = volume ? Math.max(34, height * 0.15) : 0;
  const priceH = height - volH - padT - 16;
  const plotW = w - padR - padL;
  const plotR = padL + plotW;

  const allHi = bars.map(b => b.hi).concat(hlines.map(h => h.price));
  const allLo = bars.map(b => b.lo).concat(hlines.map(h => h.price));
  if (skeleton) skeleton.forEach(p => { allHi.push(p.price); allLo.push(p.price); });
  const max = Math.max(...allHi), min = Math.min(...allLo);
  const range = (max - min) || 1;
  const pad = range * 0.06;
  const yMin = min - pad, yMax = max + pad;
  const xStep = plotW / cols;
  const xOf = i => padL + i * xStep + xStep / 2;
  const yOf = v => padT + priceH - ((v - yMin) / (yMax - yMin)) * priceH;
  const maxVol = Math.max(...bars.map(b => b.v));
  const volTop = padT + priceH + 14;
  const yVol = v => volTop + (volH - 2) * (1 - v / maxVol);
  const bw = Math.max(1.6, Math.min(9, xStep * 0.62));

  const gridVals = [0, 0.25, 0.5, 0.75, 1].map(f => yMin + (yMax - yMin) * f);
  const last = bars[bars.length - 1];
  const lastY = yOf(last.c);
  // area path under the close line (real bars only)
  const areaTop = bars.map((d, i) => `${xOf(i).toFixed(1)},${yOf(d.c).toFixed(1)}`).join(" L ");
  const areaPath = `M ${xOf(0).toFixed(1)},${(padT + priceH).toFixed(1)} L ${areaTop} L ${xOf(bars.length - 1).toFixed(1)},${(padT + priceH).toFixed(1)} Z`;

  return (
    <div className="pv-chart" ref={ref} style={{ "--pv-accent": `var(--${accent})` }}>
      <svg width={w} height={height}>
        <defs>
          <linearGradient id={`pvArea-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={`var(--${accent})`} stopOpacity="0.14" />
            <stop offset="100%" stopColor={`var(--${accent})`} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* projection region (forecast bars beyond live data) */}
        {projectFrom != null && projectFrom < cols && (() => {
          const xb = padL + projectFrom * xStep;
          return (
            <g>
              <rect x={xb} y={padT} width={plotR - xb} height={priceH} fill="var(--ink-4)" opacity="0.08" />
              <line x1={xb} y1={padT} x2={xb} y2={padT + priceH} stroke="var(--ink-3)" strokeDasharray="2 3" opacity="0.55" />
              <text x={xb + 6} y={padT + priceH - 6} fontSize="9.5" className="mono" fill="var(--ink-3)" style={{ letterSpacing: "0.12em" }}>PROJECTED →</text>
            </g>
          );
        })()}

        {/* phase bands — only current tinted; others get a quiet divider + label */}
        {bands.map((b, k) => {
          const x0 = padL + b.from * xStep;
          const x1 = padL + (b.to + 1) * xStep;
          const cur = b.tone === "copper";
          return (
            <g key={`band${k}`}>
              {cur && <rect x={x0} y={padT} width={Math.max(0, x1 - x0)} height={priceH} fill="var(--copper)" opacity="0.06" />}
              {k > 0 && <line x1={x0} y1={padT} x2={x0} y2={padT + priceH} stroke="var(--line)" strokeDasharray="2 5" opacity="0.6" />}
              <text x={(x0 + x1) / 2} y={padT + 2} fontSize="10.5" textAnchor="middle"
                    className="mono" fill={cur ? "var(--copper)" : "var(--ink-4)"} style={{ fontWeight: 700, letterSpacing: "0.12em" }}>
                {b.label}
              </text>
            </g>
          );
        })}

        {/* gridlines + right price axis */}
        {gridVals.map((gv, k) => (
          <g key={`g${k}`}>
            <line x1={padL} y1={yOf(gv)} x2={plotR} y2={yOf(gv)} stroke="var(--line)" strokeDasharray="1 6" opacity="0.45" />
            <line x1={plotR} y1={yOf(gv)} x2={plotR + 3} y2={yOf(gv)} stroke="var(--line-2)" />
            <text x={plotR + 7} y={yOf(gv) + 3} fontSize="9.5" className="mono" fill="var(--ink-3)">{gv.toFixed(0)}</text>
          </g>
        ))}
        <line x1={plotR} y1={padT} x2={plotR} y2={padT + priceH} stroke="var(--line)" opacity="0.7" />

        {/* area under price */}
        <path d={areaPath} fill={`url(#pvArea-${uid})`} />

        {/* Ichimoku cloud (Kumo) — filled between span A and span B */}
        {cloud && (() => {
          const a = cloud.spanA, b = cloud.spanB;
          const bull = a[a.length - 1].price >= b[b.length - 1].price;
          const fwd = a.map(p => `${xOf(p.i)},${yOf(p.price)}`).join(" L ");
          const rev = b.slice().reverse().map(p => `${xOf(p.i)},${yOf(p.price)}`).join(" L ");
          return (
            <g>
              <path d={`M ${fwd} L ${rev} Z`} fill={`var(--${bull ? "gn" : "rd"})`} opacity="0.12" />
              <polyline points={a.map(p => `${xOf(p.i)},${yOf(p.price)}`).join(" ")} fill="none" stroke="var(--gn)" strokeWidth="1" opacity="0.55" />
              <polyline points={b.map(p => `${xOf(p.i)},${yOf(p.price)}`).join(" ")} fill="none" stroke="var(--rd)" strokeWidth="1" opacity="0.55" />
            </g>
          );
        })()}

        {/* volume-by-price profile (right margin, behind candles) */}
        {profile && (() => {
          const profW = plotW * 0.34;
          const maxV = Math.max(...profile.map(p => p.vol));
          const step = profile.length > 1 ? Math.abs(yOf(profile[1].price) - yOf(profile[0].price)) : 6;
          const bh = Math.max(2, step - 1.5);
          return (
            <g>
              {profile.map((p, k) => {
                const wpx = (p.vol / maxV) * profW;
                const fill = p.poc ? "var(--copper)" : p.hvn ? "var(--cy)" : p.lvn ? "var(--ink-3)" : "var(--ink-2)";
                return <rect key={`pr${k}`} x={plotR - wpx} y={yOf(p.price) - bh / 2} width={wpx} height={bh}
                             fill={fill} opacity={p.poc ? 0.5 : 0.26} />;
              })}
            </g>
          );
        })()}

        {/* horizontal price zones (neckline band / PRZ) */}
        {zones.map((z, k) => {
          const yA = yOf(Math.max(z.lo, z.hi)), yB = yOf(Math.min(z.lo, z.hi));
          return (
            <g key={`z${k}`}>
              <rect x={padL} y={yA} width={plotW} height={Math.max(2, yB - yA)} fill={`var(--${z.tone || "amb"})`} opacity="0.1" />
              <line x1={padL} y1={yA} x2={plotR} y2={yA} stroke={`var(--${z.tone || "amb"})`} strokeDasharray="3 3" opacity="0.5" />
              <line x1={padL} y1={yB} x2={plotR} y2={yB} stroke={`var(--${z.tone || "amb"})`} strokeDasharray="3 3" opacity="0.5" />
              {z.label && <text x={padL + 5} y={yA - 4} fontSize="9.5" className="mono" fill={`var(--${z.tone || "amb"})`} style={{ fontWeight: 500 }}>{z.label}</text>}
            </g>
          );
        })}

        {/* horizontal target / invalidation lines */}
        {hlines.map((h, k) => (
          <g key={`h${k}`}>
            <line x1={padL} y1={yOf(h.price)} x2={plotR} y2={yOf(h.price)}
                  stroke={`var(--${h.tone || "copper"})`} strokeDasharray={h.dash || "5 4"} strokeWidth="1.1" opacity="0.8" />
            <text x={padL + 5} y={yOf(h.price) + (h.labelBelow ? 11 : -4)} fontSize="9.5" className="mono"
                  fill={`var(--${h.tone || "copper"})`} style={{ fontWeight: 500 }}>{h.label}</text>
          </g>
        ))}

        {/* candles — hollow up, filled down */}
        {bars.map((d, i) => {
          const up = d.c >= d.o;
          const x = xOf(i);
          const col = up ? "var(--gn)" : "var(--rd)";
          const bodyT = yOf(Math.max(d.o, d.c));
          const bodyH = Math.max(1.2, Math.abs(yOf(d.o) - yOf(d.c)));
          return (
            <g key={i}>
              <line x1={x} y1={yOf(d.hi)} x2={x} y2={yOf(d.lo)} stroke={col} strokeWidth="1" opacity="0.9" />
              <rect x={x - bw / 2} y={bodyT} width={bw} height={bodyH} rx="0.6"
                    fill={up ? "var(--bg-1)" : col} stroke={col} strokeWidth="1" opacity={up ? 1 : 0.92} />
            </g>
          );
        })}

        {/* volume */}
        {volume && (
          <g>
            <line x1={padL} y1={volTop + volH} x2={plotR} y2={volTop + volH} stroke="var(--line)" opacity="0.6" />
            {bars.map((d, i) => {
              const up = d.c >= d.o;
              const x = xOf(i);
              const yT = yVol(d.v);
              return <rect key={`v${i}`} x={x - bw / 2} y={yT} width={bw} height={volTop + volH - yT}
                           fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.28" />;
            })}
          </g>
        )}

        {/* wave skeleton */}
        {skeleton && (() => {
          const pts = skeleton.map(p => `${xOf(p.i)},${yOf(p.price)}`);
          const solidCount = skeleton.length - skeletonTail;
          const solid = pts.slice(0, Math.max(2, solidCount)).join(" ");
          const dashed = pts.slice(Math.max(1, solidCount - 1)).join(" ");
          return (
            <g>
              <polyline points={solid} fill="none" stroke={`var(--${accent})`} strokeWidth="2" strokeLinejoin="round" />
              {skeletonTail > 0 && <polyline points={dashed} fill="none" stroke={`var(--${accent})`} strokeWidth="1.6" strokeDasharray="5 4" opacity="0.7" />}
              {skeleton.map((p, k) => (
                <circle key={k} cx={xOf(p.i)} cy={yOf(p.price)} r="3.2" fill="var(--bg-1)" stroke={`var(--${accent})`} strokeWidth="1.6" />
              ))}
            </g>
          );
        })()}

        {/* diagonal trendlines / pattern outlines */}
        {lines.map((ln, k) => (
          <polyline key={`ln${k}`} fill="none" stroke={`var(--${ln.tone || "ink-2"})`}
                    strokeWidth={ln.width || 1.4} strokeDasharray={ln.dash || "none"} opacity={ln.opacity != null ? ln.opacity : 0.85}
                    points={ln.pts.map(p => `${xOf(p.i)},${yOf(p.price)}`).join(" ")} />
        ))}

        {/* last-price tag */}
        <g>
          <line x1={padL} y1={lastY} x2={plotR} y2={lastY} stroke={`var(--${accent})`} strokeDasharray="2 3" opacity="0.5" />
          <rect x={plotR + 1} y={lastY - 8} width={padR - 2} height={16} rx="2.5" fill={`var(--${accent})`} />
          <text x={plotR + (padR - 2) / 2 + 1} y={lastY + 3.5} fontSize="9.5" textAnchor="middle" className="mono"
                fill="var(--bg-0)" style={{ fontWeight: 700 }}>{last.c.toFixed(1)}</text>
        </g>

        {/* event / wave markers */}
        {markers.map((m, k) => {
          const x = xOf(m.i);
          const bar = bars[m.i];
          const above = m.place !== "below";
          const anchorY = bar ? (above ? yOf(bar.hi) : yOf(bar.lo)) : yOf(m.price);
          const ly = above ? anchorY - 17 : anchorY + 17;
          const cw = m.label.length * 6.6 + 13;
          const tx = Math.min(Math.max(x - cw / 2, 2), w - cw - 2);
          return (
            <g key={`m${k}`}>
              <line x1={x} y1={anchorY} x2={x} y2={above ? ly + 7 : ly - 7} stroke={`var(--${m.tone || "copper"})`} strokeWidth="1" opacity="0.6" />
              <circle cx={x} cy={anchorY} r="2.6" fill={`var(--${m.tone || "copper"})`} stroke="var(--bg-1)" strokeWidth="1" />
              <g transform={`translate(${tx}, ${above ? ly - 12 : ly - 4})`}>
                <rect width={cw} height="16" rx="3.5" fill="var(--bg-2)" stroke={`var(--${m.tone || "copper"})`} strokeWidth="1" />
                <text x={cw / 2} y="11.5" fontSize="10" textAnchor="middle" className="mono"
                      fill={`var(--${m.tone || "copper"})`} style={{ fontWeight: 700 }}>{m.label}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── shared real-data fetch primitive (mode-aware) ───────────────
// Every pattern view calls this with its engine name + the active SWING/
// POSITION/INVEST mode. Returns { real, state, sym, mode } where state is
// "loading" (fetch in flight), "loaded" (server responded — `real.ok`/payload
// present), or "mock" (no server — standalone showcase). Each view decides
// whether `real` is *usable* and otherwise renders its illustrative fixture.
function usePatternModel(engine, ticker, mode) {
  const sym = (ticker && ticker.symbol) || "ARGN";
  const md = (mode || "SWING").toUpperCase();
  const key = engine + "|" + sym + "|" + md;
  const read = () => {
    try { return (window.__BV && window.__BV.patternCached && window.__BV.patternCached(engine, sym, md)) || null; }
    catch (e) { return null; }
  };
  const [real, setReal] = usePC(read);
  useEffPC(() => {
    let alive = true;
    const cached = read();
    if (cached) setReal(cached);
    else setReal(null);
    try {
      if (window.__BV && window.__BV.fetchPattern) {
        window.__BV.fetchPattern(engine, sym, md).then(d => { if (alive) setReal(d); });
      }
    } catch (e) {}
    return () => { alive = false; };
  }, [key]);
  let state = "mock";
  if (real && typeof real === "object" && ("ok" in real || real.bars || real.events)) state = "loaded";
  else if (real === null && window.__BV && window.__BV.fetchPattern) state = "loading";
  return { real, state, sym, mode: md };
}

// generic source badge usable by any theory
function PatternSrcBadge({ state, usable, sym, tier, tf }) {
  if (usable) return <span className="wy-src wy-src--real mono" title={`computed from live ${tf || ""} bars · ${tier || "eodhd"}`}>● REAL · {sym || ""}{tf ? " · " + tf : ""}</span>;
  if (state === "loading") return <span className="wy-src wy-src--load mono">◌ loading live data…</span>;
  if (state === "loaded") return <span className="wy-src wy-src--none mono" title="real feed returned no usable structure for this timeframe">— no structure · illustrative</span>;
  return <span className="wy-src wy-src--mock mono" title="standalone showcase — connect to :7432 for live data">◑ illustrative</span>;
}

// ── confidence bar ──────────────────────────────────────────────
function ConfBar({ value, tone = "copper", width = 64 }) {
  const pct = Math.round(value * 100);
  return (
    <span className="pv-conf" title={`confidence ${pct}%`}>
      <span className="pv-conf-track" style={{ width }}>
        <span className="pv-conf-fill" style={{ width: `${pct}%`, background: `var(--${tone})` }} />
      </span>
      <span className="pv-conf-num mono">{pct}%</span>
    </span>
  );
}

// ── persisted layout direction ──────────────────────────────────
function usePatternsDir() {
  const [dir, setDir] = usePC(() => {
    try { return localStorage.getItem("pv-dir") || "A"; } catch (e) { return "A"; }
  });
  const set = (d) => { setDir(d); try { localStorage.setItem("pv-dir", d); } catch (e) {} };
  return [dir, set];
}

const PV_DIRS = [
  { id: "A", label: "Chart-led" },
  { id: "B", label: "Split" },
  { id: "C", label: "Dossier" },
];

function DirSwitch({ dir, onDir }) {
  return (
    <div className="pv-seg" role="tablist" aria-label="Layout">
      <span className="pv-seg-cap label-cap">Layout</span>
      {PV_DIRS.map(d => (
        <button key={d.id} className={`pv-seg-btn ${dir === d.id ? "is-on" : ""}`}
                onClick={() => onDir(d.id)} aria-pressed={dir === d.id}>{d.label}</button>
      ))}
    </div>
  );
}

// ── sub-tabs (Wyckoff / Elliott / Ensemble) ─────────────────────
function SubTabs({ tab, onTab, items }) {
  return (
    <div className="pv-subtabs" role="tablist">
      {items.map(it => (
        <button key={it.id} className={`pv-subtab pv-subtab--${it.accent} ${tab === it.id ? "is-on" : ""}`}
                onClick={() => onTab(it.id)} role="tab" aria-selected={tab === it.id}>
          <span className="pv-subtab-label">{it.label}</span>
          <span className="pv-subtab-sub mono">{it.sub}</span>
        </button>
      ))}
    </div>
  );
}

// ── small reusable data table ───────────────────────────────────
function MiniTable({ cols, rows, dense }) {
  return (
    <table className={`pv-table ${dense ? "is-dense" : ""}`}>
      <thead>
        <tr>{cols.map((c, i) => <th key={i} style={{ textAlign: c.align || "left" }} className="label-cap">{c.h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, ri) => (
          <tr key={ri} className={r._tone ? `pv-tr--${r._tone}` : ""}>
            {cols.map((c, ci) => <td key={ci} style={{ textAlign: c.align || "left" }} className={c.mono ? "mono" : ""}>{r[c.k]}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

Object.assign(window, {
  mulberry32, seedFromSym, buildSeries, CandleChart, ConfBar, useWidth,
  usePatternsDir, DirSwitch, SubTabs, MiniTable, PV_DIRS,
  usePatternModel, PatternSrcBadge,
});
