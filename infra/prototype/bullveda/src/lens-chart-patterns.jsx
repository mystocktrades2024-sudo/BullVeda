// lens-chart.jsx + lens-patterns.jsx — Chart and Patterns lenses

const { useMemo: useMemoCh } = React;

// ────────────────────────────────────────────────────────────
// CHART lens — full OHLC + HTF bias strip + indicator overlays
// ────────────────────────────────────────────────────────────
// scale the legacy ARCM-$66 level world onto the live ticker's price regime,
// so Chart/Patterns levels always tie to coherentLevels (no $66-vs-$213 drift).
function chartScaler(ticker) {
  const L = window.coherentLevels ? window.coherentLevels(ticker) : { pivot: ticker.pivot, stop: ticker.stop, t1: ticker.t1, t2: ticker.t2, price: ticker.price };
  const k = L.pivot / 66.18;
  return { L, k, sc: v => +(v * k).toFixed(2) };
}

function LensChart({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("ch-1"); const s2 = useStateToggle("ch-2");
  const s3 = useStateToggle("ch-3");
  const { L, sc } = chartScaler(ticker);

  return (
    <div className="lens lens--chart">
      <ChartHero ticker={ticker} sc={sc} />

      <div className="lens-section">
        <SectionHeader n={1} title="Daily OHLC · 6 months"
          sub="EMA 9/21/50 · VWAP · pivot · prior swing highs"
          style={headerStyle} right={<StateToggle name="ch-1" />} />
        <StateWrap state={s1.value} source="EODHD · daily bars · LightweightChart">
          <div className="lens-pad"><BigChart ticker={ticker} L={L} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Higher-Timeframe Bias"
          sub="weekly · monthly · sector ETF · regime"
          style={headerStyle} right={<StateToggle name="ch-2" />} />
        <StateWrap state={s2.value} source="multi-TF aggregator">
          <div className="lens-pad"><HTFBias sc={sc} L={L} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Drawing Tools · Annotations"
          sub="trendlines · fib retracements · prior reactions"
          style={headerStyle} right={<StateToggle name="ch-3" />} />
        <StateWrap state={s3.value} source="user annotations · stored in thesis library">
          <div className="lens-pad">
            <div className="annot-grid">
              <AnnotRow tool="Trendline" desc={`Connect $${sc(58)} swing low → $${sc(63)} swing low · slope rising`} tone="gn" />
              <AnnotRow tool="Fib 0–100" desc={`Anchor $${sc(52)} (Apr low) → $${sc(70)} (May high) · 0.382 = $${sc(63.13)} (held)`} tone="copper" />
              <AnnotRow tool="Volume profile" desc={`VAH $${sc(68.40)} · POC $${sc(64.20)} · VAL $${sc(61.10)}`} tone="ink" />
              <AnnotRow tool="Box" desc={`$${sc(62)}–$${sc(66)} base #2 · 8 weeks · vol drying`} tone="copper" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="copper" cells={[
            { lens: "Chart",      verdict: "TREND+", tone: "gn",  note: "stacked-bullish · base #2" },
            { lens: "Technicals", verdict: "PASS",   tone: "gn",  note: "RSI 64 · MACD+" },
            { lens: "Patterns",   verdict: "VCP",    tone: "gn",  note: "5 contractions · conf 74%" },
            { lens: "SMC",        verdict: "BoS",    tone: "gn",  note: `OB held $${sc(63)} · liquidity above` },
            { lens: "AI Edge",    verdict: "+0.18",  tone: "gn",  note: "hit-net edge positive" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Chart</span>
        <span className="mono">
          Stacked-bullish, base #2 pivot at <b className="copper">${L.pivot.toFixed(2)}</b>.
          Breakout valid above pivot on &gt; 1.30× RVOL with daily close.
        </span>
      </div>
    </div>
  );
}

function ChartHero({ ticker, sc }) {
  return (
    <div className="hero chart-hero">
      <div className="ch-hero-left">
        <div className="label-cap">Chart bias</div>
        <div className="ch-hero-pills">
          <Pill tone="gn" dot>STACKED-BULLISH</Pill>
          <Pill tone="gn" small>Daily PASS</Pill>
          <Pill tone="gn" small>Weekly PASS</Pill>
          <Pill tone="amb" small>Monthly NEUTRAL</Pill>
        </div>
        <div className="ch-hero-stats mono">
          <span><span className="label-cap">52w Hi</span> <b>${sc(74.20)}</b></span>
          <span><span className="label-cap">52w Lo</span> <b>${sc(42.10)}</b></span>
          <span><span className="label-cap">% off Hi</span> <b className="warn">−9.1%</b></span>
          <span><span className="label-cap">% off Lo</span> <b className="up">+60.1%</b></span>
        </div>
      </div>
    </div>
  );
}

function BigChart({ ticker, L }) {
  // 120 bars
  const w = 900, h = 360;
  const data = useMemoCh(() => {
    const out = [];
    let p = 50;
    for (let i = 0; i < 120; i++) {
      const phase =
        i < 30  ? 0.12 :
        i < 50  ? 0.30 :
        i < 70  ? -0.08 :
        i < 90  ? -0.05 :
        i < 108 ? 0.10 :
                  0.42;
      const noise = (Math.sin(i * 0.45) + Math.cos(i * 0.31)) * 0.45;
      p += phase + noise;
      const o = p - Math.random() * 0.4;
      const c = p + (Math.random() - 0.4) * 0.6;
      const hi = Math.max(o, c) + Math.random() * 0.5;
      const lo = Math.min(o, c) - Math.random() * 0.5;
      const v = (Math.abs(Math.sin(i * 0.7)) + 0.2) * (i > 100 ? 1.3 : 1) * 600_000;
      out.push({ o, c, hi, lo, v });
    }
    return out;
  }, []);

  const min = Math.min(...data.map(d => d.lo));
  const max = Math.max(...data.map(d => d.hi));
  const range = max - min;
  const priceH = h * 0.72;
  const volH = h * 0.22;
  const xStep = w / data.length;
  const yPx = v => priceH - ((v - min) / range) * (priceH - 20) - 8;
  const maxVol = Math.max(...data.map(d => d.v));
  const yVol = v => priceH + 12 + (volH - 4) * (1 - v / maxVol);

  // simple EMAs
  const ema = (period, src) => {
    const k = 2 / (period + 1);
    const out = [];
    let prev = src[0].c;
    for (let i = 0; i < src.length; i++) {
      prev = src[i].c * k + prev * (1 - k);
      out.push(prev);
    }
    return out;
  };
  const e9  = ema(9,  data);
  const e21 = ema(21, data);
  const e50 = ema(50, data);

  // synthetic candles have their own scale — position the plan lines proportionally
  // within the visible range, but LABEL them with the live coherent levels.
  const pPivot = min + range * 0.58, pT1 = min + range * 0.82, pStop = min + range * 0.40;
  return (
    <div className="big-chart-wrap">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {/* grid */}
        {[0.2, 0.4, 0.6, 0.8].map(f => (
          <line key={f} x1="0" y1={priceH * f} x2={w} y2={priceH * f} stroke="var(--line)" strokeDasharray="2 4" opacity="0.5" />
        ))}
        {/* pivot/stop/t1 lines */}
        <line x1="0" y1={yPx(pPivot)} x2={w} y2={yPx(pPivot)} stroke="var(--copper)" strokeDasharray="4 4" strokeWidth="1" />
        <line x1="0" y1={yPx(pT1)} x2={w} y2={yPx(pT1)} stroke="var(--gn)" strokeDasharray="3 3" opacity="0.7" />
        <line x1="0" y1={yPx(pStop)} x2={w} y2={yPx(pStop)} stroke="var(--rd)" strokeDasharray="3 3" opacity="0.7" />
        <text x={w - 4} y={yPx(pPivot) - 3} fontSize="10" className="mono" textAnchor="end" fill="var(--copper)">PIVOT {L.pivot.toFixed(2)}</text>
        <text x={w - 4} y={yPx(pT1) - 3} fontSize="10" className="mono" textAnchor="end" fill="var(--gn)">T1 {L.t1.toFixed(2)}</text>
        <text x={w - 4} y={yPx(pStop) + 11} fontSize="10" className="mono" textAnchor="end" fill="var(--rd)">STOP {L.stop.toFixed(2)}</text>
        {/* EMAs */}
        <polyline fill="none" stroke="var(--cy)" strokeWidth="1.1" opacity="0.8"
                  points={e9.map((v, i) => `${i * xStep + xStep/2},${yPx(v)}`).join(" ")} />
        <polyline fill="none" stroke="var(--violet)" strokeWidth="1.1" opacity="0.8"
                  points={e21.map((v, i) => `${i * xStep + xStep/2},${yPx(v)}`).join(" ")} />
        <polyline fill="none" stroke="var(--amb)" strokeWidth="1.1" opacity="0.7"
                  points={e50.map((v, i) => `${i * xStep + xStep/2},${yPx(v)}`).join(" ")} />
        {/* candles */}
        {data.map((d, i) => {
          const up = d.c >= d.o;
          const x = i * xStep + 1;
          const ww = xStep - 1.5;
          return (
            <g key={i}>
              <line x1={x + ww/2} y1={yPx(d.hi)} x2={x + ww/2} y2={yPx(d.lo)} stroke={up ? "var(--gn)" : "var(--rd)"} strokeWidth="0.6" />
              <rect x={x} y={yPx(Math.max(d.o, d.c))} width={ww} height={Math.max(1.5, Math.abs(yPx(d.o) - yPx(d.c)))}
                    fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.9" />
            </g>
          );
        })}
        {/* volume */}
        {data.map((d, i) => {
          const up = d.c >= d.o;
          const x = i * xStep + 1;
          const ww = xStep - 1.5;
          const yT = yVol(d.v);
          return (
            <rect key={`v${i}`} x={x} y={yT} width={ww} height={priceH + volH - yT}
                  fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.35" />
          );
        })}
        {/* axis */}
        <line x1="0" y1={priceH + 4} x2={w} y2={priceH + 4} stroke="var(--line)" />
      </svg>
      <div className="chart-legend mono">
        <span><span className="dot" style={{ background: "var(--cy)" }} /> EMA 9</span>
        <span><span className="dot" style={{ background: "var(--violet)" }} /> EMA 21</span>
        <span><span className="dot" style={{ background: "var(--amb)" }} /> EMA 50</span>
        <span><span className="dot" style={{ background: "var(--copper)" }} /> Pivot</span>
        <span><span className="dot" style={{ background: "var(--gn)" }} /> T1</span>
        <span><span className="dot" style={{ background: "var(--rd)" }} /> Stop</span>
      </div>
    </div>
  );
}

function HTFBias({ sc, L }) {
  const rows = [
    { tf: "Monthly", bias: "NEUTRAL", note: `consolidating above $${sc(58)} · range top $${sc(74)}`, tone: "amb" },
    { tf: "Weekly",  bias: "BULLISH", note: "higher highs & lows · close > 20w EMA",   tone: "gn"  },
    { tf: "Daily",   bias: "BULLISH", note: `base #2 · pivot $${L.pivot.toFixed(2)} · vol-dry`,       tone: "gn"  },
    { tf: "Sector ETF (XLB)", bias: "BULLISH", note: "above 50-DMA · RSI 58",        tone: "gn"  },
    { tf: "Regime",  bias: "BULL · LOW-VIX", note: "QQQ > 50 · VIX 17.4 · trend up", tone: "gn"  },
  ];
  return (
    <div className="htf">
      {rows.map((r, i) => (
        <div key={i} className={`htf-row htf-${r.tone}`}>
          <span className="mono htf-tf">{r.tf}</span>
          <Pill tone={r.tone} small>{r.bias}</Pill>
          <span className="mono dim2 htf-note">{r.note}</span>
        </div>
      ))}
    </div>
  );
}

function AnnotRow({ tool, desc, tone }) {
  return (
    <div className={`annot annot-${tone}`}>
      <Pill tone={tone === "copper" ? "copper" : tone === "gn" ? "gn" : "ink"} small>{tool}</Pill>
      <span className="mono">{desc}</span>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// PATTERNS lens — multi-method matrix + Wyckoff + Elliott + Monte-Carlo
// ────────────────────────────────────────────────────────────
function LensPatterns({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("pt-1"); const s2 = useStateToggle("pt-2");
  const s3 = useStateToggle("pt-3"); const s4 = useStateToggle("pt-4");
  const s5 = useStateToggle("pt-5");
  const { L, sc } = chartScaler(ticker);

  return (
    <div className="lens lens--patterns">
      <PatternsHero ticker={ticker} />

      <div className="lens-section">
        <SectionHeader n={1} title="Method Matrix"
          sub="6 detection systems · max-confidence pattern wins"
          style={headerStyle} right={<StateToggle name="pt-1" />} />
        <StateWrap state={s1.value} source="pattern-detector ensemble">
          <div className="lens-pad"><PatternMatrix /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Wyckoff Phase"
          sub="accumulation / mark-up / distribution / mark-down"
          style={headerStyle} right={<StateToggle name="pt-2" />} />
        <StateWrap state={s2.value} source="bespoke · volume + structure">
          <div className="lens-pad"><WyckoffPanel sc={sc} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Elliott Wave"
          sub="impulse · corrective · wave count + targets"
          style={headerStyle} right={<StateToggle name="pt-3" />} />
        <StateWrap state={s3.value} source="EW labeler · 0.62 confidence">
          <div className="lens-pad"><ElliottPanel sc={sc} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Monte Carlo · 90d"
          sub="2,000 paths · conditional on base #2 setup"
          style={headerStyle} right={<StateToggle name="pt-4" />} />
        <StateWrap state={s4.value} source="MC engine · setup-conditional">
          <div className="lens-pad"><MonteCarlo ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Action Ladder"
          sub="exact triggers · sized to base"
          style={headerStyle} right={<StateToggle name="pt-5" />} />
        <StateWrap state={s5.value} source="rule engine">
          <div className="lens-pad">
            <div className="action-ladder">
              <div className="al-row al-gn"><span className="mono">CLOSE &gt; ${sc(66.40)} + RVOL ≥ 1.30×</span><Pill tone="gn" small>GO · full size</Pill></div>
              <div className="al-row al-amb"><span className="mono">Intraday &gt; pivot, fades by close</span><Pill tone="amb" small>WAIT · half size on retest</Pill></div>
              <div className="al-row al-rd"><span className="mono">Close &lt; ${sc(65.10)} (BO retest fails)</span><Pill tone="rd" small>EXIT · skip</Pill></div>
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Patterns</span>
        <span className="mono">
          VCP confirmed (conf 74%) · Wyckoff Phase D · Elliott Wave 3 · MC median
          +<b className="up">6.4%</b> 90d. Trigger above <b className="copper">${sc(66.40)}</b>.
        </span>
      </div>
    </div>
  );
}

function PatternsHero({ ticker }) {
  return (
    <div className="hero patt-hero">
      <div className="ph2-cell">
        <div className="label-cap">Top method</div>
        <div className="ph2-v mono">VCP <span className="mono dim2" style={{ fontSize: 11 }}>· conf 74%</span></div>
      </div>
      <div className="ph2-cell">
        <div className="label-cap">Wyckoff</div>
        <div className="ph2-v mono">PHASE D <span className="dim2" style={{ fontSize: 11 }}>· spring + SOS</span></div>
      </div>
      <div className="ph2-cell">
        <div className="label-cap">Elliott</div>
        <div className="ph2-v mono">WAVE 3 <span className="dim2" style={{ fontSize: 11 }}>· of 5</span></div>
      </div>
      <div className="ph2-cell">
        <div className="label-cap">MC median 90d</div>
        <div className="ph2-v mono up">+6.4%</div>
      </div>
    </div>
  );
}

function WyckoffPanel({ sc }) {
  const phases = ["A · Accum.", "B · Buildup", "C · Spring", "D · SOS", "E · Markup"];
  return (
    <div className="wy-panel">
      <div className="wy-strip">
        {phases.map((p, i) => (
          <div key={i} className={`wy-cell ${i === 3 ? "is-current" : ""} ${i < 3 ? "is-past" : ""}`}>
            <span className="mono">{p}</span>
            {i === 3 && <Pill tone="copper" small>NOW</Pill>}
          </div>
        ))}
      </div>
      <div className="wy-notes mono dim2">
        Spring at ${sc(62.10)} (Apr 22) ✓ · Sign-of-Strength close ${sc(66.80)} on +1.6× vol ✓.
        Last-Point-of-Support retest at ${sc(64.30)} (May 15) held.
      </div>
    </div>
  );
}

function ElliottPanel({ sc }) {
  return (
    <div className="ew-panel">
      <svg viewBox="0 0 320 110" width="100%" height="110" preserveAspectRatio="xMidYMid meet">
        {/* zig-zag impulse */}
        <polyline points="10,90 60,52 90,72 150,30 180,50 240,18 270,38 310,8"
                  fill="none" stroke="var(--copper)" strokeWidth="1.6" />
        {[
          { x: 60,  y: 52, l: "1" },
          { x: 90,  y: 72, l: "2" },
          { x: 150, y: 30, l: "3" },
          { x: 180, y: 50, l: "4" },
          { x: 240, y: 18, l: "5" },
        ].map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r="3" fill="var(--copper)" />
            <text x={p.x + 4} y={p.y - 4} fontSize="10" className="mono" fill="var(--copper)">{p.l}</text>
          </g>
        ))}
        <text x="270" y="8" fontSize="9" className="mono" textAnchor="end" fill="var(--ink-2)">target ${sc(74.20)}</text>
      </svg>
      <div className="ew-rows">
        <Field label="Current count" value={<span className="mono copper">Wave 3 of 5 (impulse)</span>} />
        <Field label="Wave-3 target (1.618×W1)" value={<span className="mono up">${sc(74.20)}</span>} />
        <Field label="Invalidation" value={<span className="mono dn">close &lt; ${sc(62.10)} (W2 low)</span>} />
        <Field label="Confidence" value={<span className="mono">0.51 · medium</span>} />
      </div>
    </div>
  );
}

function MonteCarlo({ ticker }) {
  const w = 520, h = 160;
  // synthetic cone-of-uncertainty
  const samples = 30;
  const paths = useMemoCh(() => {
    const out = [];
    for (let s = 0; s < samples; s++) {
      let p = ticker.price;
      const arr = [p];
      const trend = 0.04 + Math.random() * 0.10;
      for (let i = 0; i < 90; i++) {
        p += trend + (Math.random() - 0.5) * 1.4;
        arr.push(p);
      }
      out.push(arr);
    }
    return out;
  }, []);
  const all = paths.flat();
  const min = Math.min(...all) * 0.97;
  const max = Math.max(...all) * 1.02;
  const xStep = w / 90;
  const yFor = v => h - ((v - min) / (max - min)) * (h - 4) - 2;
  return (
    <div className="mc-panel">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {paths.map((path, i) => (
          <polyline key={i} fill="none" stroke={i % 3 === 0 ? "var(--gn)" : "var(--copper)"} opacity="0.18" strokeWidth="1"
                    points={path.map((v, j) => `${j * xStep},${yFor(v)}`).join(" ")} />
        ))}
        <line x1="0" y1={yFor(ticker.price * 1.064)} x2={w} y2={yFor(ticker.price * 1.064)} stroke="var(--copper)" strokeDasharray="3 3" />
        <text x={w - 4} y={yFor(ticker.price * 1.064) - 3} fontSize="10" textAnchor="end" className="mono" fill="var(--copper)">Median +6.4%</text>
      </svg>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginTop: 8 }}>
        <KpiTile label="Median 90d" value="+6.4%" tone="gn" />
        <KpiTile label="P(T1 hit first)" value="58%" tone="gn" />
        <KpiTile label="P(stop hit first)" value="40%" tone="amb" />
        <KpiTile label="Paths" value="2,000" tone="ink" sub="setup-conditional" />
      </div>
    </div>
  );
}

// Field helper (shared from Plan lens via window) — but for safety also define a fallback
window.LensChart = LensChart;
window.LensPatterns = LensPatterns;
