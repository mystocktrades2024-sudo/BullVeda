// lens-technicals.jsx — Technicals (10-section discipline view)
// Indicator dashboard, EMA stack, pattern detection, S/R confluence,
// volume, statistical backbone (Wilson), cross-source confluence,
// regime-conditional edge, pre-mortem, sizing+exits.

const { useMemo: useMemoTL } = React;

function LensTechnicals({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tl-1"); const s2 = useStateToggle("tl-2");
  const s3 = useStateToggle("tl-3"); const s4 = useStateToggle("tl-4");
  const s5 = useStateToggle("tl-5"); const s6 = useStateToggle("tl-6");
  const s7 = useStateToggle("tl-7"); const s8 = useStateToggle("tl-8");
  const L = window.coherentLevels ? window.coherentLevels(ticker) : { pivot: ticker.pivot, stop: ticker.stop, t1: ticker.t1, t2: ticker.t2, price: ticker.price };
  const sc = v => +(v * (L.pivot / 66.18)).toFixed(2);

  return (
    <div className="lens lens--tech">
      {window.LensSummaryBar && <LensSummaryBar ticker={ticker} mode={mode} kind="technicals" />}
      <TechHero ticker={ticker} mode={mode} heroStyle={heroStyle} sizeCat={sizeCat} />

      <div className="lens-section">
        <SectionHeader n={1} title="Indicator Dashboard"
          sub="RSI · MACD · Stoch · ADX · MFI · CMF · cross-confirms"
          style={headerStyle} right={<StateToggle name="tl-1" />} />
        <StateWrap state={s1.value} source="EODHD · daily OHLC + computed">
          <div className="lens-pad"><IndicatorDash ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="EMA / SMA Stack"
          sub="stacked-bullish · price above all major MAs"
          style={headerStyle} right={<StateToggle name="tl-2" />} />
        <StateWrap state={s2.value} source="computed · 200d window">
          <div className="lens-pad"><MAStack ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Pattern · Signal Detection"
          sub="quick read — full theory analysis lives in the Patterns lens"
          style={headerStyle} right={<StateToggle name="tl-3" />} />
        <StateWrap state={s3.value} source="pattern detector · TA-Lib + bespoke">
          <div className="lens-pad">
            <button className="tl-xlink mono" onClick={() => window.__setLens && window.__setLens("patterns")}>
              ↗ Open <b>Patterns</b> for the 14-theory confluence engine (Wyckoff · Elliott · Fib · Harmonic …) — single source of truth for setups
            </button>
            <PatternMatrix sc={sc} />
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="S / R Confluence Ladder"
          sub="VWAP · Fibs · pivots · prior highs · option-OI walls"
          style={headerStyle} right={<StateToggle name="tl-4" />} />
        <StateWrap state={s4.value} source="6-source confluence engine">
          <div className="lens-pad"><SRLadder ticker={ticker} sc={sc} L={L} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Volume Analytics"
          sub="RVOL · OBV · MFI · pocket-pivot · accumulation/distribution"
          style={headerStyle} right={<StateToggle name="tl-5" />} />
        <StateWrap state={s5.value} source="EODHD · intraday + daily">
          <div className="lens-pad"><VolumeAnalytics /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Statistical Backbone"
          sub="this exact setup over the historical record"
          style={headerStyle} right={<StateToggle name="tl-6" />} />
        <StateWrap state={s6.value} source="setup_stats.json · Wilson-CI'd">
          <div className="lens-pad"><StatBackbone ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Regime-Conditional Edge"
          sub="same setup across 4 macro regimes"
          style={headerStyle} right={<StateToggle name="tl-7" />} />
        <StateWrap state={s7.value} source="regime engine · VIX × trend × yield-slope">
          <div className="lens-pad"><RegimeEdge /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Source Confluence"
          sub="how 6 lenses score the same name"
          style={headerStyle} right={<StateToggle name="tl-8" />} />
        <StateWrap state={s8.value} source="all-lens aggregator">
          <div className="lens-pad">
            <CrossLens lead="cy" cells={[
              { lens: "Technicals", verdict: "PASS",   tone: "gn", note: "RSI 64 · MACD+ · VWAP-reclaim" },
              { lens: "Patterns",   verdict: "FLAG·B", tone: "gn", note: "8-wk base · vol-dry pullback" },
              { lens: "SMC",        verdict: "OB+BoS", tone: "gn", note: `BoS @ $${sc(66)} · OB held $${sc(63)}` },
              { lens: "Risk",       verdict: "OK",     tone: "gn", note: "VaR(1d) −2.1%" },
              { lens: "ML Edge",    verdict: "+0.18",  tone: "gn", note: "hit-net edge · cal-OK" },
            ]} />
          </div>
        </StateWrap>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Technicals</span>
        <span className="mono">
          Stacked-bullish · breakout confirmed if close &gt; <b className="copper">${sc(66.40)}</b>
          on &gt; <b>1.30× RVOL</b>. Stop <b className="dn">${L.stop.toFixed(2)}</b>. R-multiple {(((L.t1 - L.pivot * 1.002) / (L.pivot * 1.002 - L.stop))).toFixed(2)}.
        </span>
      </div>
    </div>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────
function TechHero({ ticker, mode, heroStyle, sizeCat }) {
  return (
    <div className="hero tech-hero">
      <div className="th-left">
        <div className="label-cap">Composite technical · {mode}</div>
        <div className="th-score">
          <div className="th-score-num mono">{Math.round(ticker.pillars.technical)}<span className="th-score-unit">/100</span></div>
          <Pill tone="gn" dot>STACKED-BULLISH</Pill>
        </div>
        <div className="th-pill-row">
          <Pill tone="gn" small>RSI 64</Pill>
          <Pill tone="gn" small>MACD+</Pill>
          <Pill tone="gn" small>ADX 28</Pill>
          <Pill tone="amb" small>RVOL 1.18×</Pill>
          <Pill tone="gn" small>VWAP·rec</Pill>
        </div>
      </div>
      <div className="th-right">
        <MiniChart />
      </div>
    </div>
  );
}

// Mock OHLC chart preview
function MiniChart() {
  const w = 320, h = 110;
  const bars = 60;
  const data = useMemoTL(() => {
    const out = [];
    let p = 56;
    for (let i = 0; i < bars; i++) {
      const trend = 0.18 + (i > 42 ? 0.4 : 0);
      const noise = (Math.sin(i * 0.7) + Math.cos(i * 0.3)) * 0.4;
      const dip = (i > 28 && i < 42) ? -0.8 : 0;
      p = p + trend + noise + dip;
      const o = p - Math.random() * 0.3;
      const c = p + (Math.random() - 0.4) * 0.5;
      const hi = Math.max(o, c) + Math.random() * 0.4;
      const lo = Math.min(o, c) - Math.random() * 0.4;
      out.push({ o, c, hi, lo });
    }
    return out;
  }, []);
  const min = Math.min(...data.map(d => d.lo));
  const max = Math.max(...data.map(d => d.hi));
  const range = max - min;
  const xStep = w / bars;
  const yFor = v => h - ((v - min) / range) * (h - 10) - 5;
  const pivotY = yFor(min + range * 0.78);
  const lastBar = data[data.length - 1];
  const lastX = (data.length - 1) * xStep + xStep / 2;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="mini-chart" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="mc-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.08" />
          <stop offset="100%" stopColor="var(--copper)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width={w} height={pivotY} fill="url(#mc-bg)" />
      {/* Grid */}
      <line x1="0" y1={yFor((min + max) / 2)} x2={w} y2={yFor((min + max) / 2)} stroke="var(--line)" strokeDasharray="2 3" opacity="0.5" />
      {/* Pivot line */}
      <line x1="0" y1={pivotY} x2={w} y2={pivotY} stroke="var(--copper)" strokeOpacity="0.7" strokeDasharray="3 3"
            style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
      <text x={w - 4} y={pivotY - 3} fontSize="8.5" className="mono" textAnchor="end" fill="var(--copper)" letterSpacing="0.10em">PIVOT 66.18</text>
      {/* Candles */}
      {data.map((d, i) => {
        const up = d.c >= d.o;
        const x = i * xStep + 1;
        const ww = xStep - 2;
        return (
          <g key={i}>
            <line x1={x + ww/2} y1={yFor(d.hi)} x2={x + ww/2} y2={yFor(d.lo)} stroke={up ? "var(--gn)" : "var(--rd)"} strokeWidth="0.6" />
            <rect x={x} y={yFor(Math.max(d.o, d.c))} width={ww} height={Math.max(1.2, Math.abs(yFor(d.o) - yFor(d.c)))}
                  fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.92" />
          </g>
        );
      })}
      {/* Last price marker */}
      <circle cx={lastX} cy={yFor(lastBar.c)} r="3.5" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 7px var(--copper))" }} />
    </svg>
  );
}

// ─── §1 Indicator dashboard ──────────────────────────────────────────
function IndicatorDash({ ticker }) {
  // RSI/price divergence detector — derived per-ticker so it varies by name
  const P = (ticker && ticker.pillars) || {};
  const tech = P.technical ?? 60, edge = P.edge ?? 60;
  const rsiSlope = tech - 55, priceSlope = edge - 55;
  const bearDiv = priceSlope > 4 && rsiSlope < -2;
  const bullDiv = priceSlope < -4 && rsiSlope > 2;
  const div = bearDiv ? { t: "BEARISH DIVERGENCE", tone: "rd", note: "price making highs, RSI/MACD not confirming — momentum fading" }
            : bullDiv ? { t: "BULLISH DIVERGENCE", tone: "gn", note: "price making lows, momentum turning up — reversal setup" }
            : { t: "NO DIVERGENCE", tone: "gn", note: "oscillators confirm price — trend intact" };
  const indicators = [
    { name: "RSI(14)",       v: 64.2,  state: "bullish", note: ">50, not overbought", tone: "gn" },
    { name: "MACD(12,26,9)", v: "+0.42", state: "bullish", note: "fresh cross 3d ago", tone: "gn" },
    { name: "Stoch(14,3,3)", v: "76 / 71", state: "rising", note: "no divergence", tone: "gn" },
    { name: "ADX(14)",       v: 28.4,  state: "trending", note: ">25 = trend", tone: "gn" },
    { name: "MFI(14)",       v: 62.1,  state: "neutral", note: "money-flow rising", tone: "gn" },
    { name: "CMF(20)",       v: "+0.14", state: "accumulation", note: "buyers control", tone: "gn" },
    { name: "ATR(14)",       v: "1.24 ($)", state: "stable", note: "1.8% of price", tone: "ink" },
    { name: "BB %B(20,2)",   v: 0.71,  state: "upper third", note: "no squeeze", tone: "amb" },
  ];
  return (
    <div>
      <div className={`ind-div ind-div--${div.tone}`}>
        <span className={`ind-div-tag kpi-tone--${div.tone}`}>⚡ {div.t}</span>
        <span className="mono dim2">{div.note}</span>
      </div>
      <div className="ind-grid">
      {indicators.map((i, idx) => (
        <div key={idx} className={`ind-cell ind-${i.tone}`}>
          <div className="ind-name mono">{i.name}</div>
          <div className={`ind-v mono kpi-tone--${i.tone}`}>{i.v}</div>
          <div className="ind-state mono">{i.state}</div>
          <div className="ind-note mono dim">{i.note}</div>
        </div>
      ))}
      </div>
    </div>
  );
}

// ─── §2 MA stack ─────────────────────────────────────────────────────
function MAStack({ ticker }) {
  const rows = [
    { ma: "Price",   v: ticker.price, tone: "copper" },
    { ma: "EMA 9",   v: 66.80, tone: "gn", delta: "+0.62" },
    { ma: "EMA 21",  v: 65.10, tone: "gn", delta: "+2.32" },
    { ma: "SMA 50",  v: 64.10, tone: "gn", delta: "+3.32" },
    { ma: "EMA 100", v: 61.20, tone: "gn", delta: "+6.22" },
    { ma: "SMA 200", v: 58.40, tone: "gn", delta: "+9.02" },
  ];
  return (
    <div className="ma-stack">
      <div className="ma-stack-grid">
        {rows.map((r, i) => (
          <div key={i} className="ma-row">
            <span className="mono ma-label">{r.ma}</span>
            <span className={`mono kpi-tone--${r.tone} ma-v`}>${r.v.toFixed(2)}</span>
            {r.delta && <span className="mono ma-delta up">{r.delta}</span>}
          </div>
        ))}
      </div>
      <div className="ma-summary">
        <Pill tone="gn" dot>STACKED-BULLISH</Pill>
        <span className="mono dim2">Every MA below price · slopes positive · last cross 32d ago.</span>
      </div>
    </div>
  );
}

// ─── §3 Pattern matrix ───────────────────────────────────────────────
function PatternMatrix({ sc }) {
  const f = sc || (v => v);
  const rows = [
    { method: "Cup & Handle",   det: "FORMING",  conf: 0.46, note: "handle 6d in" },
    { method: "VCP (Minervini)", det: "CONFIRMED", conf: 0.74, note: "5 contractions · vol-dry" },
    { method: "Flag",           det: "—",        conf: 0,    note: "no flag context" },
    { method: "Breakout-Base #2",det: "ACTIVE",  conf: 0.81, note: `pivot $${f(66.18).toFixed(2)} · vol dry` },
    { method: "Wyckoff",        det: "PHASE D",  conf: 0.62, note: "spring + SOS confirmed" },
    { method: "Elliott (impulse)", det: "WAVE 3", conf: 0.51, note: `of 5 · target $${f(74.20).toFixed(2)}` },
  ];
  return (
    <div className="pat-tbl">
      <div className="pat-row pat-row--hdr">
        <span className="label-cap">Method</span>
        <span className="label-cap">Detected</span>
        <span className="label-cap" style={{ textAlign: "right" }}>Conf</span>
        <span className="label-cap">Note</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="pat-row">
          <span className="mono">{r.method}</span>
          <span className={`mono ${r.det === "—" ? "dim" : r.det === "CONFIRMED" || r.det === "ACTIVE" ? "up" : "copper"}`}>{r.det}</span>
          <span className="mono" style={{ textAlign: "right" }}>
            {r.conf ? (
              <span className="pat-conf">
                <span className="pat-conf-bar"><span style={{ width: `${r.conf * 100}%` }} /></span>
                {(r.conf * 100).toFixed(0)}%
              </span>
            ) : "—"}
          </span>
          <span className="mono dim">{r.note}</span>
        </div>
      ))}
    </div>
  );
}

// ─── §4 S/R Confluence ───────────────────────────────────────────────
function SRLadder({ ticker, sc, L }) {
  const f = sc || (v => v);
  const cur = (L && L.price) ? L.price : f(67.42);
  const rows = [
    { px: f(74.20), lbl: "R3 · Elliott wv-3 target",       sources: ["EW", "Fib"], strong: true },
    { px: f(72.80), lbl: "T1 · 0.618 extension",           sources: ["Fib", "VWAP"] },
    { px: f(70.40), lbl: "Prior swing high",               sources: ["Pivot", "PriorH"] },
    { px: f(68.10), lbl: "0.382 ext.",                     sources: ["Fib"] },
    { px: cur,      lbl: "Current price",                  sources: ["—"], current: true },
    { px: f(66.18), lbl: "Pivot · base #2 high",           sources: ["Pivot", "Volume"], strong: true },
    { px: f(65.10), lbl: "Day-VWAP · also 5-day VAH",      sources: ["VWAP", "Profile"] },
    { px: f(64.10), lbl: "50-DMA · rising",                sources: ["MA"] },
    { px: f(62.40), lbl: "Hard stop · last LL",            sources: ["Pivot", "ATR"], strong: true, stop: true },
    { px: f(60.00), lbl: `$${f(60).toFixed(0)} strike OI wall`, sources: ["Opt"] },
  ].sort((a, b) => b.px - a.px);
  return (
    <div className="sr-ladder">
      {rows.map((r, i) => (
        <div key={i} className={`sr-row ${r.current ? "sr-current" : ""} ${r.stop ? "sr-stop" : ""} ${r.strong ? "sr-strong" : ""}`}>
          <span className={`mono sr-px ${r.stop ? "dn" : r.current ? "copper" : ""}`}>${r.px.toFixed(2)}</span>
          <span className="mono sr-lbl">{r.lbl}</span>
          <span className="sr-sources">
            {r.sources.map((s, j) => s !== "—" ? <span key={j} className="sr-src mono">{s}</span> : null)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── §5 Volume analytics ─────────────────────────────────────────────
function VolumeAnalytics() {
  return (
    <div className="vol-block">
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="RVOL today" value="1.18×" tone="amb" sub="below pivot trigger (≥1.3×)" />
        <KpiTile label="20d avg vol" value="1.12M" tone="ink" sub="sh/day" />
        <KpiTile label="OBV trend" value="↑ rising" tone="gn" sub="14-day slope positive" />
        <KpiTile label="A/D line" value="ACCUM." tone="gn" sub="3 of last 5 weeks" />
      </div>
      <div className="vol-bars">
        {Array.from({ length: 32 }, (_, i) => {
          const v = 0.4 + Math.abs(Math.sin(i * 0.6)) * 0.6 + (i > 26 ? 0.3 : 0);
          const up = (i % 3) !== 1;
          return (
            <div
              key={i}
              className={`vol-bar ${up ? "up" : "dn"} ${i === 28 ? "is-pivot" : ""}`}
              style={{ height: `${v * 100}%` }}
              title={`session ${i}`}
            />
          );
        })}
      </div>
      <div className="vol-note mono dim2">
        Last 32 sessions · pivot tested on lower-than-avg volume (dry pullback = constructive).
      </div>
    </div>
  );
}

// ─── §6 Statistical backbone (Wilson) ────────────────────────────────
function StatBackbone({ ticker }) {
  const s = ticker.setupStats;
  return (
    <div className="stat-block">
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <WilsonPill n={s.n} winRate={s.winRate} lb={s.wilsonLB} />
        <Pill tone="gn" small>PROFIT FACTOR {s.pf != null ? s.pf.toFixed(2) : "—"}</Pill>
        <Pill tone="copper" small>MEDIAN {s.medianR != null ? "+" + s.medianR.toFixed(2) + "R" : "—"}</Pill>
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginTop: 12 }}>
        <KpiTile label="Forward 10d (n=47)" value="+2.4%" tone="gn" sub="median return" />
        <KpiTile label="Hit rate T1" value="58.5%" tone="gn" sub="of n=47" />
        <KpiTile label="Avg loser" value="−1.04R" tone="rd" sub="bounded at stop" />
        <KpiTile label="Edge decay" value="STABLE" tone="gn" sub="last 12-mo block" />
      </div>
      <OutcomeDist ticker={ticker} />
      <div className="stat-note mono dim">
        Source: setup_stats.json · Wilson 95% lower bound used everywhere.
        Sample &lt; 30 would flag this section red.
      </div>
    </div>
  );
}

// ─── §6b Outcome distribution — histogram of realized R over the sample ──
function OutcomeDist({ ticker }) {
  const seed = (ticker.symbol || "X").charCodeAt(0) + (ticker.symbol || "X").length;
  // R buckets from -2R to +4R; shape skews to the setup's win-rate
  const wr = (ticker.setupStats && ticker.setupStats.winRate) || 0.6;
  const buckets = [
    { r: "≤−2R", base: 3 }, { r: "−2→−1R", base: 8 }, { r: "−1→0R", base: 14 },
    { r: "0→+1R", base: 12 }, { r: "+1→+2R", base: 11 }, { r: "+2→+3R", base: 7 }, { r: "≥+3R", base: 4 },
  ].map((b, i) => {
    const win = i >= 3;
    const v = Math.max(1, Math.round(b.base * (win ? wr * 1.6 : (1 - wr) * 1.7) + ((seed * (i + 3)) % 5)));
    return { ...b, v, win };
  });
  const max = Math.max(...buckets.map(b => b.v));
  const total = buckets.reduce((s, b) => s + b.v, 0);
  return (
    <div className="odist">
      <div className="odist-h mono dim2">OUTCOME DISTRIBUTION · realized R over n={total} <span className="dim">(setup-conditional)</span></div>
      <div className="odist-bars">
        {buckets.map((b, i) => (
          <div key={i} className="odist-col" title={`${b.r}: ${b.v} trades`}>
            <span className={`odist-bar ${b.win ? "win" : "loss"}`} style={{ height: `${(b.v / max) * 64 + 4}px` }} />
            <span className="odist-k mono">{b.r}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── §7 Regime-conditional edge ──────────────────────────────────────
function RegimeEdge() {
  const regimes = [
    { name: "Bull · low-VIX",  wr: 0.71, n: 22, pf: 2.40, current: true },
    { name: "Bull · high-VIX", wr: 0.58, n: 14, pf: 1.62 },
    { name: "Range",           wr: 0.46, n: 8,  pf: 0.94 },
    { name: "Bear",            wr: 0.32, n: 3,  pf: 0.41, low: true },
  ];
  return (
    <div className="reg-grid">
      {regimes.map((r, i) => (
        <div key={i} className={`reg-cell ${r.current ? "is-current" : ""} ${r.low ? "is-low" : ""}`}>
          <div className="reg-name mono">{r.name}</div>
          {r.current && <div className="reg-pin mono copper">NOW</div>}
          <div className="reg-wr mono">
            <span className="reg-wr-v">{(r.wr * 100).toFixed(0)}%</span>
            <span className="label-cap dim">win-rate · n={r.n}</span>
          </div>
          <div className="reg-pf mono dim2">PF {r.pf.toFixed(2)}</div>
          {r.low && <Pill tone="rd" small>n&lt;30</Pill>}
        </div>
      ))}
    </div>
  );
}

window.LensTechnicals = LensTechnicals;
window.PatternMatrix = PatternMatrix;
