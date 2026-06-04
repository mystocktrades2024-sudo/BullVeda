// patterns-altcharts.jsx — alternative chart constructions theory sub-tab.
// Renko · Kagi · Heikin-Ashi — noise filters that clarify trend & reversal.
//
// REAL DATA: HA candles, ATR-brick Renko, and ATR-reversal Kagi are computed
// server-side by engines/altcharts.py over live EODHD bars, then fetched via
// the shared usePatternModel hook. When the server is absent (standalone dev
// showcase) or the feed returns no usable structure, we fall back to the
// illustrative fixture below — and the header badge says so, honestly.

const { useMemo: useMemoAc, useState: useStateAc } = React;

// ── seeded mock bar generator (used only for the fixture fallback) ──
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

// ── Heikin-Ashi transform (client-side, used for the fixture fallback only) ──
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

// ── Renko bricks (client-side, fixture fallback only) ──────────────
function renko(bars, box) {
  const out = []; let base = Math.round(bars[0].c / box) * box;
  for (const b of bars) {
    while (b.c >= base + box) { out.push({ dir: 1, lo: base, hi: base + box }); base += box; }
    while (b.c <= base - box) { out.push({ dir: -1, lo: base - box, hi: base }); base -= box; }
  }
  return out;
}

// ── fixture constants (illustrative; clearly labelled in the UI) ───
const AC_META_FIXTURE = {
  renko:  { label: "Renko", sub: "fixed $3 bricks · time-independent", signal: "6 green bricks · uptrend intact", reversal: "needs a $3 down-brick to flip", filters: "all time-based noise; only price moves of ≥1 box print", tone: "gn" },
  heikin: { label: "Heikin-Ashi", sub: "averaged candles · trend smoother", signal: "run of hollow candles · strong trend", reversal: "first filled candle w/ upper-wick loss", filters: "intrabar chop; smooths the trend body", tone: "gn" },
  kagi:   { label: "Kagi", sub: "thick/thin reversal line", signal: "yang (thick) line · demand in control", reversal: "yin flip on a $4 counter-move", filters: "minor swings below the reversal amount", tone: "cy" },
};

// Fixture model (used when server is absent or returns no structure)
function buildFixtureModel(ticker) {
  return { isReal: false, bars: null, ha: null, renko: null, kagi: null, stat: null, meta_display: null };
}

// ── data hook: real → fixture fallback (mode-aware) ────────────────
function useAltChartsModel(ticker, mode) {
  const { real, state, sym } = usePatternModel("altcharts", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;

  // real, fully-formed payload?
  const usable = (
    state === "loaded" && real && real.ok &&
    real.state === "real" &&
    real.bars && real.bars.length &&
    real.ha && real.ha.length &&
    real.renko && real.renko.bricks
  );

  if (usable) {
    return {
      model: {
        isReal: true, source: "real",
        bars: real.bars,
        ha: real.ha,
        renko: real.renko,
        kagi: real.kagi || {},
        stat: real.stat || {},
        meta_display: real.meta_display || {},
        read: real.read || "",
        confidence: real.confidence || 0,
        tf, ticker: real.ticker,
      },
      state: "real", sym, tf, usable: true,
    };
  }

  // real responded but no structure → honest empty state
  if (state === "loaded" && real && real.ok) {
    return {
      model: buildFixtureModel(ticker),
      state: "none", sym, tf, usable: false,
      message: real.message || "No usable structure detected.",
    };
  }

  // not yet loaded / server absent → illustrative fixture
  return {
    model: buildFixtureModel(ticker),
    state: state === "loading" ? "loading" : "mock",
    sym, tf, usable: false,
  };
}

// ── mini-chart for any alt-construction (shared renderer) ──────────
function AltMiniChart({ kind, bars, haData, renkoData }) {
  const [ref, w] = useWidth(620);
  const h = 240, padT = 12, padB = 16, padL = 8, padR = 50;
  const plotH = h - padT - padB, plotR = w - padR;

  if (kind === "renko") {
    // Use real renko bricks if provided, else compute from raw bars
    const bricks = renkoData ? renkoData.bricks : (bars ? renko(bars, 3.0) : []);
    if (!bricks || bricks.length === 0) return <div className="pv-chart" ref={ref}><svg width={w} height={h}><text x={20} y={h/2} fill="var(--ink-3)" fontSize="11" className="mono">no bricks</text></svg></div>;
    const vals = bricks.flatMap(b => [b.lo, b.hi]);
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const range = mx - mn || 1;
    // show last 80 bricks max
    const visible = bricks.slice(-80);
    const bw = Math.max(3, Math.min(16, (plotR - padL) / visible.length - 2));
    const y = v => padT + plotH - ((v - mn) / range) * plotH;
    return (
      <div className="pv-chart" ref={ref}><svg width={w} height={h}>
        {visible.map((b, i) => (
          <rect key={i} x={padL + i * (bw + 2)} y={y(b.hi)} width={bw} height={Math.max(2, y(b.lo) - y(b.hi))}
                fill={b.dir > 0 ? "var(--gn)" : "var(--rd)"} opacity="0.85" rx="1" />
        ))}
        {renkoData && renkoData.reversal_price != null && (() => {
          const yRev = y(renkoData.reversal_price);
          return <line x1={padL} y1={yRev} x2={plotR} y2={yRev} stroke="var(--amb)" strokeDasharray="4 3" strokeWidth="1.2" opacity="0.75" />;
        })()}
        <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
        <text x={plotR + 5} y={y(mn)} fontSize="9" className="mono" fill="var(--ink-3)">{mn.toFixed(0)}</text>
      </svg></div>
    );
  }

  if (kind === "heikin") {
    // Use real HA candles if provided, else compute from raw bars
    const data = haData ? haData : (bars ? heikin(bars) : []);
    if (!data || data.length === 0) return <div className="pv-chart" ref={ref}><svg width={w} height={h}><text x={20} y={h/2} fill="var(--ink-3)" fontSize="11" className="mono">no data</text></svg></div>;
    // normalise key names: engine uses {o,c,hi,lo}; client-side heikin uses {o,c,h,l}
    const norm = data.map(b => ({ o: b.o, c: b.c, h: b.hi != null ? b.hi : b.h, l: b.lo != null ? b.lo : b.l }));
    const vals = norm.flatMap(b => [b.h, b.l]);
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const range = mx - mn || 1;
    const xStep = (plotR - padL) / norm.length;
    const x = i => padL + i * xStep + xStep / 2;
    const y = v => padT + plotH - ((v - mn) / range) * plotH;
    const bw = Math.max(1.6, xStep * 0.6);
    return (
      <div className="pv-chart" ref={ref}><svg width={w} height={h}>
        {norm.map((b, i) => {
          const up = b.c >= b.o; const col = up ? "var(--gn)" : "var(--rd)";
          return (
            <g key={i}>
              <line x1={x(i)} y1={y(b.h)} x2={x(i)} y2={y(b.l)} stroke={col} strokeWidth="0.9" opacity="0.85" />
              <rect x={x(i) - bw / 2} y={y(Math.max(b.o, b.c))} width={bw} height={Math.max(1.4, Math.abs(y(b.o) - y(b.c)))} fill={up ? "var(--bg-1)" : col} stroke={col} strokeWidth="1" />
            </g>
          );
        })}
        <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
        <text x={plotR + 5} y={y(norm[norm.length - 1].c) + 3} fontSize="9" className="mono" fill="var(--gn)">{norm[norm.length - 1].c.toFixed(0)}</text>
      </svg></div>
    );
  }

  if (kind === "kagi") {
    // Kagi stepped-line renderer using real Kagi lines from server
    if (bars && !haData) {
      // fixture fallback: stepped from raw close prices
      const data = bars;
      const vals = data.flatMap(b => [b.h != null ? b.h : (b.hi || b.c), b.l != null ? b.l : (b.lo || b.c)]);
      const mn = Math.min(...vals), mx = Math.max(...vals);
      const range = mx - mn || 1;
      const xStep = (plotR - padL) / data.length;
      const x = i => padL + i * xStep + xStep / 2;
      const y = v => padT + plotH - ((v - mn) / range) * plotH;
      const pts = []; let dir = 1, ext = data[0].c;
      const thresh = 4;
      data.forEach((b, i) => {
        if (dir > 0) { if (b.c > ext) ext = b.c; else if (ext - b.c > thresh) { dir = -1; ext = b.c; } }
        else { if (b.c < ext) ext = b.c; else if (b.c - ext > thresh) { dir = 1; ext = b.c; } }
        pts.push({ x: x(i), y: y(b.c), dir });
      });
      let d = `M ${pts[0].x},${pts[0].y}`;
      for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x},${pts[i - 1].y} L ${pts[i].x},${pts[i].y}`;
      return (
        <div className="pv-chart" ref={ref}><svg width={w} height={h}>
          <path d={d} fill="none" stroke="var(--cy)" strokeWidth="2.4" strokeLinejoin="round" />
          <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
          <text x={plotR + 5} y={y(data[data.length - 1].c) + 3} fontSize="9" className="mono" fill="var(--cy)">{data[data.length - 1].c.toFixed(0)}</text>
        </svg></div>
      );
    }
    // Real Kagi lines from server
    if (haData && haData.lines && haData.lines.length) {
      const lines = haData.lines;
      const allP = lines.flatMap(l => [l.from, l.to]);
      const mn = Math.min(...allP), mx = Math.max(...allP);
      const range = mx - mn || 1;
      const xStep = (plotR - padL) / lines.length;
      const x = i => padL + i * xStep + xStep / 2;
      const y = v => padT + plotH - ((v - mn) / range) * plotH;
      let d = `M ${x(0)},${y(lines[0].from)}`;
      for (let i = 0; i < lines.length; i++) {
        d += ` L ${x(i)},${y(lines[i].from)} L ${x(i)},${y(lines[i].to)}`;
      }
      // reversal trigger line
      const revY = haData.reversal_trigger != null ? y(haData.reversal_trigger) : null;
      return (
        <div className="pv-chart" ref={ref}><svg width={w} height={h}>
          <path d={d} fill="none" stroke="var(--cy)" strokeWidth="2.4" strokeLinejoin="round" />
          {revY != null && <line x1={padL} y1={revY} x2={plotR} y2={revY} stroke="var(--amb)" strokeDasharray="4 3" strokeWidth="1.2" opacity="0.75" />}
          <text x={plotR + 5} y={y(mx) + 8} fontSize="9" className="mono" fill="var(--ink-3)">{mx.toFixed(0)}</text>
          <text x={plotR + 5} y={y(lines[lines.length - 1].to) + 3} fontSize="9" className="mono" fill="var(--cy)">{lines[lines.length - 1].to.toFixed(0)}</text>
        </svg></div>
      );
    }
    return <div className="pv-chart" ref={ref}><svg width={w} height={h}><text x={20} y={h/2} fill="var(--ink-3)" fontSize="11" className="mono">no kagi data</text></svg></div>;
  }

  // fallback: raw bar line
  if (!bars || bars.length === 0) return <div className="pv-chart" ref={ref}><svg width={w} height={h}></svg></div>;
  const vals = bars.flatMap(b => [(b.hi != null ? b.hi : b.h) || b.c, (b.lo != null ? b.lo : b.l) || b.c]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const range = mx - mn || 1;
  const xStep = (plotR - padL) / bars.length;
  const x = i => padL + i * xStep + xStep / 2;
  const y = v => padT + plotH - ((v - mn) / range) * plotH;
  let d = bars.map((b, i) => `${i === 0 ? "M" : "L"} ${x(i)},${y(b.c)}`).join(" ");
  return (
    <div className="pv-chart" ref={ref}><svg width={w} height={h}>
      <path d={d} fill="none" stroke="var(--cy)" strokeWidth="1.6" />
    </svg></div>
  );
}

// ── stat strip (real or fixture) ────────────────────────────────────
function AcStat({ model, kind, isReal }) {
  const stat = (model && model.stat) || {};
  const md = (model && model.meta_display) || {};

  if (!isReal) {
    // fixture stat strip (from original fixture AC_META)
    const m = AC_META_FIXTURE[kind] || AC_META_FIXTURE.heikin;
    return (
      <div className="pv-stat">
        <div className="pv-stat-cell"><div className="label-cap">Construction</div><div className="pv-stat-v mono cy">{m.label}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Signal</div><div className="pv-stat-v mono up" style={{ fontSize: 13 }}>{m.signal.split(" · ")[0]}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Trend</div><div className="pv-stat-v mono up">PERSISTENT</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Reversal trigger</div><div className="pv-stat-v mono" style={{ fontSize: 12 }}>{m.reversal}</div></div>
        <div className="pv-stat-cell"><div className="label-cap">Noise filtered</div><div className="pv-stat-v mono">HIGH</div></div>
      </div>
    );
  }

  // Real stat strip
  const verdict = (stat.verdict || "NEUTRAL").toUpperCase();
  const verdTone = verdict === "UP" ? "up" : verdict === "DOWN" ? "dn" : "dim2";
  const warnColor = stat.reversal_warning ? "var(--amb)" : "var(--gn)";

  const kindLabels = { renko: "Renko", heikin: "Heikin-Ashi", kagi: "Kagi" };
  const kindLabel = kindLabels[kind] || kind;

  // Per-construction live read
  let signalText = "", reversalText = "";
  if (kind === "heikin") {
    signalText = md.ha_signal || `${stat.ha_streak || 0} ${(stat.ha_trend || "").toLowerCase()} candles`;
    reversalText = md.ha_reversal || "first opposite candle";
  } else if (kind === "renko") {
    signalText = md.renko_signal || `${stat.renko_bricks || 0} ${(stat.renko_dir || "").toLowerCase()} bricks`;
    reversalText = md.renko_reversal || "next opposite brick";
  } else if (kind === "kagi") {
    signalText = `${stat.kagi_state || "YANG"} line · ${(model.kagi || {}).reversals || 0} reversals`;
    reversalText = md.kagi_reversal || `flip on ${((model.kagi || {}).reversal_amount || 0).toFixed(2)} reversal`;
  }

  return (
    <div className="pv-stat">
      <div className="pv-stat-cell"><div className="label-cap">Construction</div><div className="pv-stat-v mono cy">{kindLabel}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Signal</div><div className="pv-stat-v mono up" style={{ fontSize: 13 }}>{signalText}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Trend consensus</div><div className={`pv-stat-v mono ${verdTone}`}>{verdict}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Reversal trigger</div><div className="pv-stat-v mono" style={{ fontSize: 12, color: warnColor }}>{reversalText}</div></div>
      <div className="pv-stat-cell"><div className="label-cap">Confidence</div><div className="pv-stat-v"><ConfBar value={stat.confidence || 0.5} tone="cy" width={72} /></div></div>
    </div>
  );
}

// ── read table (real or fixture) ────────────────────────────────────
function AcReadTable({ model, kind, isReal }) {
  const stat = (model && model.stat) || {};
  const md = (model && model.meta_display) || {};
  const kagi = (model && model.kagi) || {};

  if (!isReal) {
    const m = AC_META_FIXTURE[kind] || AC_META_FIXTURE.heikin;
    return (
      <MiniTable
        cols={[{ h: "Read", k: "k" }, { h: "", k: "v" }]}
        rows={[
          { k: <span className="dim2">Current signal</span>, v: <b style={{ color: `var(--${m.tone})` }}>{m.signal}</b> },
          { k: <span className="dim2">Reversal trigger</span>, v: <span className="mono">{m.reversal}</span> },
          { k: <span className="dim2">What it filters</span>, v: <span className="mono dim2">{m.filters}</span> },
          { k: <span className="dim2">Best used for</span>, v: <span className="mono">trend confirmation + cleaner stops vs raw candles</span> },
        ]} />
    );
  }

  // Real reads per construction
  let rows = [];
  if (kind === "heikin") {
    const dirTone = stat.ha_trend === "UP" ? "up" : "dn";
    rows = [
      { k: <span className="dim2">HA trend</span>, v: <b className={dirTone}>{(stat.ha_trend || "").toUpperCase()} · {stat.ha_streak || 0}-bar streak</b> },
      { k: <span className="dim2">Reversal trigger</span>, v: <span className="mono">{md.ha_reversal || "first opposite candle"}</span> },
      { k: <span className="dim2">What it filters</span>, v: <span className="mono dim2">intrabar chop; open/high/low averaged — smooths the trend body</span> },
      { k: <span className="dim2">Best used for</span>, v: <span className="mono">sizing conviction in the trend body; mechanical trail-stop</span> },
    ];
  } else if (kind === "renko") {
    const dirTone = stat.renko_dir === "UP" ? "up" : "dn";
    const renko = (model && model.renko) || {};
    rows = [
      { k: <span className="dim2">Renko direction</span>, v: <b className={dirTone}>{stat.renko_dir || "?"} · {stat.renko_bricks || 0} bricks since reversal</b> },
      { k: <span className="dim2">Brick size (ATR)</span>, v: <span className="mono">{(renko.brick_size || 0).toFixed(2)}</span> },
      { k: <span className="dim2">Reversal trigger</span>, v: <span className="mono">{md.renko_reversal || `price @ ${renko.reversal_price || ""}`}</span> },
      { k: <span className="dim2">What it filters</span>, v: <span className="mono dim2">time; only price moves ≥ 1 ATR brick print — strips sideways noise</span> },
      { k: <span className="dim2">Best used for</span>, v: <span className="mono">trail-stop level · mechanical trend confirmation</span> },
    ];
  } else if (kind === "kagi") {
    const stateTone = (kagi.state || "") === "yang" ? "up" : "dn";
    rows = [
      { k: <span className="dim2">Kagi state</span>, v: <b className={stateTone}>{(kagi.state || "").toUpperCase()} · {kagi.reversals || 0} line reversals</b> },
      { k: <span className="dim2">Reversal amount</span>, v: <span className="mono">{(kagi.reversal_amount || 0).toFixed(2)}</span> },
      { k: <span className="dim2">Reversal trigger</span>, v: <span className="mono">{md.kagi_reversal || `flip @ ${kagi.reversal_trigger || ""}`}</span> },
      { k: <span className="dim2">What it filters</span>, v: <span className="mono dim2">minor swings below the reversal amount — only real turns print</span> },
      { k: <span className="dim2">Best used for</span>, v: <span className="mono">yang/yin confirmation · supply/demand line flips</span> },
    ];
  }

  return (
    <MiniTable
      cols={[{ h: "Read", k: "k" }, { h: "", k: "v" }]}
      rows={rows} />
  );
}

// ── why-it-matters box ──────────────────────────────────────────────
function AcWhyBox({ model, isReal }) {
  const read = model && model.read;
  return (
    <div className="pv-invalid" style={{ border: "1px solid var(--line)", background: "var(--bg-1)", marginTop: 10 }}>
      <span className="label-cap">Why it matters</span>
      <span className="mono">
        {isReal && read
          ? read
          : <>These constructions strip time/noise so the <b className="up">trend and its reversal threshold</b> are unambiguous — use Renko/Kagi for a mechanical trail-stop and Heikin-Ashi to size conviction in the trend body. They confirm direction; they do not time entries.</>
        }
      </span>
    </div>
  );
}

// ── three-construction summary table (used in split/dossier dirs) ───
function AcSummaryTable({ model, isReal }) {
  if (!isReal || !model || !model.stat) return null;
  const stat = model.stat;
  const renko = model.renko || {};
  const kagi = model.kagi || {};

  const rows = [
    {
      c: "Heikin-Ashi",
      dir: stat.ha_trend || "?",
      detail: `${stat.ha_streak || 0}-bar streak`,
      tone: stat.ha_trend === "UP" ? "up" : "dn",
      warn: stat.reversal_warning ? "⚠ reversal warning" : "",
    },
    {
      c: "Renko",
      dir: stat.renko_dir || "?",
      detail: `${stat.renko_bricks || 0} bricks · size ${(renko.brick_size || 0).toFixed(2)}`,
      tone: stat.renko_dir === "UP" ? "up" : "dn",
      warn: renko.reversal_price != null ? `rev @ ${renko.reversal_price}` : "",
    },
    {
      c: "Kagi",
      dir: (kagi.state || "").toUpperCase() || "?",
      detail: `${kagi.reversals || 0} line reversals`,
      tone: kagi.state === "yang" ? "up" : "dn",
      warn: kagi.reversal_trigger != null ? `flip @ ${kagi.reversal_trigger}` : "",
    },
  ];

  return (
    <MiniTable
      cols={[
        { h: "Construction", k: "c" },
        { h: "Direction", k: "dir", mono: true },
        { h: "Detail", k: "detail", mono: true },
        { h: "Reversal trigger", k: "warn", mono: true },
      ]}
      rows={rows.map(r => ({
        c: <b>{r.c}</b>,
        dir: <span className={r.tone}>{r.dir}</span>,
        detail: <span className="dim2">{r.detail}</span>,
        warn: <span style={{ color: "var(--amb)" }}>{r.warn}</span>,
      }))} />
  );
}

// ── honest empty state ──────────────────────────────────────────────
function AcNone({ sym, message }) {
  return (
    <div className="pv-view">
      <div className="pv-empty">
        <div className="pv-empty-i mono">— no Alt-Charts structure</div>
        <div className="pv-empty-msg">{message || `Not enough bars available for ${sym || "this name"}'s Alt-Chart analysis.`}</div>
        <div className="pv-empty-sub mono dim2">The detector requires ≥30 daily / ≥20 weekly / ≥12 monthly bars. Connect to the live server for real data.</div>
      </div>
    </div>
  );
}

// ── view assembler (3 directions) ───────────────────────────────────
function AltChartsView({ ticker, dir, mode }) {
  const { model, state, sym, tf, usable, message } = useAltChartsModel(ticker, mode);
  const mockBars = useAltSeries(ticker);
  const [kind, setKind] = useStateAc("heikin");

  const tabs = [["heikin", "Heikin-Ashi"], ["renko", "Renko"], ["kagi", "Kagi"]];

  // Choose bar data sources for the current construction
  const chartBars = usable ? model.bars : mockBars;
  const haData = usable ? model.ha : null;
  const renkoData = usable ? model.renko : null;
  const kagiData = usable ? model.kagi : null;

  const SrcBar = (
    <div className="pv-srcbar">
      <PatternSrcBadge state={state} usable={usable} sym={sym} tier={null} tf={tf} />
    </div>
  );

  // No-structure honest state
  if (state === "none") {
    return (
      <div className="pv-view">
        {SrcBar}
        <AcNone sym={sym} message={message} />
      </div>
    );
  }

  const ConstructionPicker = (
    <div className="pv-degsel" style={{ marginBottom: 10 }}>
      <span className="pv-degsel-cap label-cap">Construction</span>
      {tabs.map(([id, nm]) => (
        <button key={id} className={`pv-degsel-btn pv-degsel-btn--cy ${kind === id ? "is-on" : ""}`} onClick={() => setKind(id)}>{nm}</button>
      ))}
    </div>
  );

  const Chart = (
    <AltMiniChart
      kind={kind}
      bars={chartBars}
      haData={kind === "heikin" ? haData : kind === "kagi" ? kagiData : null}
      renkoData={kind === "renko" ? renkoData : null}
    />
  );

  const StatStrip = <AcStat model={model} kind={kind} isReal={usable} />;
  const ReadTable = <AcReadTable model={model} kind={kind} isReal={usable} />;
  const WhyBox = <AcWhyBox model={model} isReal={usable} />;

  if (dir === "B") {
    // SPLIT — chart left, analysis right
    return (
      <div className="pv-view">
        {SrcBar}
        {StatStrip}
        <div className="pv-split">
          <div className="pv-split-main">
            <SectionHeader n={1} title="Alt-Chart construction" sub="select Heikin-Ashi · Renko · Kagi" style="minimal" />
            <div className="pv-pad">
              {ConstructionPicker}
              {Chart}
            </div>
          </div>
          <div className="pv-split-side">
            <SectionHeader n={2} title="Construction read" style="minimal" />
            <div className="pv-pad">{ReadTable}</div>
            {usable && (
              <>
                <SectionHeader n={3} title="Consensus summary" style="minimal" />
                <div className="pv-pad"><AcSummaryTable model={model} isReal={usable} /></div>
              </>
            )}
          </div>
        </div>
        <div className="pv-pad">{WhyBox}</div>
      </div>
    );
  }

  if (dir === "C") {
    // DOSSIER — compact, data-dense
    return (
      <div className="pv-view pv-view--dossier">
        {SrcBar}
        {StatStrip}
        <div className="pv-pad">
          {ConstructionPicker}
          {Chart}
        </div>
        {usable && (
          <div className="pv-2col">
            <div>
              <div className="pv-block-h label-cap">Construction read</div>
              {ReadTable}
            </div>
            <div>
              <div className="pv-block-h label-cap">All constructions</div>
              <AcSummaryTable model={model} isReal={usable} />
            </div>
          </div>
        )}
        {!usable && <div className="pv-pad">{ReadTable}</div>}
        <div className="pv-pad">{WhyBox}</div>
      </div>
    );
  }

  // A — CHART-LED (default)
  return (
    <div className="pv-view">
      {SrcBar}
      {StatStrip}
      <div className="pv-pad">
        {ConstructionPicker}
        {Chart}
      </div>
      <SectionHeader n={1} title={`${kind === "heikin" ? "Heikin-Ashi" : kind === "renko" ? "Renko" : "Kagi"} · read`}
                    sub={kind === "heikin" ? "averaged candles · trend smoother" : kind === "renko" ? `ATR brick = ${usable ? (model.renko || {}).brick_size || "~1×ATR" : "$3"} · time-independent` : "thick/thin reversal line · ATR-scaled"}
                    style="minimal" />
      <div className="pv-pad">
        {ReadTable}
        {usable && (
          <>
            <div className="pv-block-h label-cap" style={{ marginTop: 16 }}>All constructions — consensus</div>
            <AcSummaryTable model={model} isReal={usable} />
          </>
        )}
        {WhyBox}
      </div>
    </div>
  );
}

Object.assign(window, { AltChartsView });
