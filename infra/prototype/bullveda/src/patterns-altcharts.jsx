// patterns-altcharts.jsx — alternative chart constructions theory sub-tab.
// Renko · Kagi · Heikin-Ashi · Three-Line-Break — noise filters that clarify
// trend & reversal. A construction toggle redraws the same series each way.

const { useMemo: useMemoAc, useState: useStateAc } = React;

function useAltSeries(ticker) {
  const seed = seedFromSym((ticker && ticker.symbol) || "ARGN") ^ 0x6ab;
  return useMemoAc(() => {
    const rng = mulberry32(seed);
    const bars = []; let p = 184;
    for (let i = 0; i < 66; i++) {
      const drift = i < 14 ? -0.2 : i < 22 ? 0.1 : 0.55;
      p += drift + (rng() - 0.5) * 3.0;
      const o = p - (rng() - 0.5) * 1.6;
      const c = p + (rng() - 0.5) * 1.8;
      const h = Math.max(o, c) + rng() * 1.4;
      const l = Math.min(o, c) - rng() * 1.4;
      bars.push({ o, h, l, c });
    }
    bars[bars.length - 1].c = 213.4;
    return bars;
  }, [seed]);
}

// Heikin-Ashi transform
function heikin(bars) {
  const out = []; let po = bars[0].o, pc = bars[0].c;
  for (const b of bars) {
    const c = (b.o + b.h + b.l + b.c) / 4;
    const o = (po + pc) / 2;
    out.push({ o, c, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c) });
    po = o; pc = c;
  }
  return out;
}
// Renko bricks
function renko(bars, box) {
  const out = []; let base = Math.round(bars[0].c / box) * box;
  for (const b of bars) {
    while (b.c >= base + box) { out.push({ dir: 1, lo: base, hi: base + box }); base += box; }
    while (b.c <= base - box) { out.push({ dir: -1, lo: base - box, hi: base }); base -= box; }
  }
  return out;
}

function AltMiniChart({ kind, bars }) {
  const [ref, w] = useWidth(620);
  const h = 240, padT = 12, padB = 16, padL = 8, padR = 50;
  const plotH = h - padT - padB, plotR = w - padR;
  if (kind === "renko") {
    const bricks = renko(bars, 3.0);
    const vals = bricks.flatMap(b => [b.lo, b.hi]);
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const bw = Math.max(3, Math.min(16, (plotR - padL) / bricks.length - 2));
    const y = v => padT + plotH - ((v - mn) / (mx - mn)) * plotH;
    return (
      <div className="pv-chart" ref={ref}><svg width={w} height={h}>
        {bricks.map((b, i) => (
          <rect key={i} x={padL + i * (bw + 2)} y={y(b.hi)} width={bw} height={Math.max(2, y(b.lo) - y(b.hi))}
                fill={b.dir > 0 ? "var(--gn)" : "var(--rd)"} opacity="0.85" rx="1" />
        ))}
        <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
        <text x={plotR + 5} y={y(mn)} fontSize="9" className="mono" fill="var(--ink-3)">{mn.toFixed(0)}</text>
      </svg></div>
    );
  }
  // candle-style constructions (heikin / kagi / 3lb share a candle/line renderer)
  const data = kind === "heikin" ? heikin(bars) : bars;
  const vals = data.flatMap(b => [b.h, b.l]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const xStep = (plotR - padL) / data.length;
  const x = i => padL + i * xStep + xStep / 2;
  const y = v => padT + plotH - ((v - mn) / (mx - mn)) * plotH;
  const bw = Math.max(1.6, xStep * 0.6);
  if (kind === "kagi" || kind === "3lb") {
    // stepped line that flips on a 3-bar / threshold reversal
    const pts = []; let dir = 1, ext = data[0].c;
    const thresh = kind === "kagi" ? 4 : 3.5;
    data.forEach((b, i) => {
      if (dir > 0) { if (b.c > ext) ext = b.c; else if (ext - b.c > thresh) { dir = -1; ext = b.c; } }
      else { if (b.c < ext) ext = b.c; else if (b.c - ext > thresh) { dir = 1; ext = b.c; } }
      pts.push({ x: x(i), y: y(b.c), dir });
    });
    let d = `M ${pts[0].x},${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x},${pts[i - 1].y} L ${pts[i].x},${pts[i].y}`;
    return (
      <div className="pv-chart" ref={ref}><svg width={w} height={h}>
        <path d={d} fill="none" stroke="var(--cy)" strokeWidth={kind === "kagi" ? 2.4 : 1.8} strokeLinejoin="round" />
        {kind === "3lb" && data.map((b, i) => {
          const up = b.c >= b.o;
          return <rect key={i} x={x(i) - bw / 2} y={y(Math.max(b.o, b.c))} width={bw} height={Math.max(2, Math.abs(y(b.o) - y(b.c)))} fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.5" />;
        })}
        <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
        <text x={plotR + 5} y={y(data[data.length - 1].c) + 3} fontSize="9" className="mono" fill="var(--cy)">{data[data.length - 1].c.toFixed(0)}</text>
      </svg></div>
    );
  }
  // heikin-ashi candles
  return (
    <div className="pv-chart" ref={ref}><svg width={w} height={h}>
      {data.map((b, i) => {
        const up = b.c >= b.o; const col = up ? "var(--gn)" : "var(--rd)";
        return (
          <g key={i}>
            <line x1={x(i)} y1={y(b.h)} x2={x(i)} y2={y(b.l)} stroke={col} strokeWidth="0.9" opacity="0.85" />
            <rect x={x(i) - bw / 2} y={y(Math.max(b.o, b.c))} width={bw} height={Math.max(1.4, Math.abs(y(b.o) - y(b.c)))} fill={up ? "var(--bg-1)" : col} stroke={col} strokeWidth="1" />
          </g>
        );
      })}
      <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
      <text x={plotR + 5} y={y(data[data.length - 1].c) + 3} fontSize="9" className="mono" fill="var(--gn)">{data[data.length - 1].c.toFixed(0)}</text>
    </svg></div>
  );
}

const AC_META = {
  renko:  { label: "Renko", sub: "fixed $3 bricks · time-independent", signal: "6 green bricks · uptrend intact", reversal: "needs a $3 down-brick to flip", filters: "all time-based noise; only price moves of ≥1 box print", tone: "gn" },
  heikin: { label: "Heikin-Ashi", sub: "averaged candles · trend smoother", signal: "run of hollow candles · strong trend", reversal: "first filled candle w/ upper-wick loss", filters: "intrabar chop; smooths the trend body", tone: "gn" },
  kagi:   { label: "Kagi", sub: "thick/thin reversal line", signal: "yang (thick) line · demand in control", reversal: "yin flip on a $4 counter-move", filters: "minor swings below the reversal amount", tone: "cy" },
  "3lb":  { label: "Three-Line-Break", sub: "break-of-3 reversal bars", signal: "extended green run · trend persists", reversal: "close beyond the last 3 lines", filters: "shallow pullbacks; flips only on real breaks", tone: "gn" },
};

function AltChartsView({ ticker, dir }) {
  const { bars } = { bars: useAltSeries(ticker) };
  const [kind, setKind] = useStateAc("heikin");
  const m = AC_META[kind];
  const tabs = [["renko", "Renko"], ["heikin", "Heikin-Ashi"], ["kagi", "Kagi"], ["3lb", "3-Line-Break"]];
  return (
    <div className="pv-view">
      <div className="pv-stat">
        <div className="pv-stat-cell"><div className="label-cap">Construction</div><div className="pv-stat-v mono cy">{m.label}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Signal</div><div className="pv-stat-v mono up" style={{ fontSize: 13 }}>{m.signal.split(" · ")[0]}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Trend</div><div className="pv-stat-v mono up">PERSISTENT</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Reversal trigger</div><div className="pv-stat-v mono" style={{ fontSize: 12 }}>{m.reversal}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Noise filtered</div><div className="pv-stat-v mono">HIGH</div></div>
      </div>
      <div className="pv-pad">
        <div className="pv-degsel" style={{ marginBottom: 10 }}>
          <span className="pv-degsel-cap label-cap">Construction</span>
          {tabs.map(([id, nm]) => (
            <button key={id} className={`pv-degsel-btn pv-degsel-btn--cy ${kind === id ? "is-on" : ""}`} onClick={() => setKind(id)}>{nm}</button>
          ))}
        </div>
        <AltMiniChart kind={kind} bars={bars} />
      </div>
      <SectionHeader n={1} title={`${m.label} · read`} sub={m.sub} style="minimal" />
      <div className="pv-pad">
        <MiniTable
          cols={[{ h: "Read", k: "k" }, { h: "", k: "v" }]}
          rows={[
            { k: <span className="dim2">Current signal</span>, v: <b style={{ color: `var(--${m.tone})` }}>{m.signal}</b> },
            { k: <span className="dim2">Reversal trigger</span>, v: <span className="mono">{m.reversal}</span> },
            { k: <span className="dim2">What it filters</span>, v: <span className="mono dim2">{m.filters}</span> },
            { k: <span className="dim2">Best used for</span>, v: <span className="mono">trend confirmation + cleaner stops vs raw candles</span> },
          ]} />
        <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", marginTop: 10 }}>
          <span className="label-cap">Why it matters</span>
          <span className="mono">These constructions strip time/noise so the <b className="up">trend and its reversal threshold</b> are unambiguous — use Renko/3-Line-Break for a mechanical trail-stop and Heikin-Ashi to size conviction in the trend body. They confirm direction; they do not time entries.</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AltChartsView });
