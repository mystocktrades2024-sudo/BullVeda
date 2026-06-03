// lens-track.jsx + lens-mledge.jsx — Track Record + AI Edge

// ────────────────────────────────────────────────────────────
// TRACK RECORD — Wilson CI per setup, PF, median R, edge decay
// ────────────────────────────────────────────────────────────
function LensTrack({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tr-1"); const s2 = useStateToggle("tr-2");
  const s3 = useStateToggle("tr-3"); const s4 = useStateToggle("tr-4");
  const s5 = useStateToggle("tr-5");

  return (
    <div className="lens lens--track">
      <div className="hero track-hero">
        <div className="th-left">
          <div className="label-cap">Setup edge · "{ticker.setupFamily}"</div>
          <div className="th-score">
            <div className="th-score-num mono">EDGE</div>
            <Pill tone="gn" dot>Wilson LB 47.7%</Pill>
            <Pill tone="gn" small>PF 1.84 (raw)</Pill>
            <Pill tone="amb" small>PF 1.41 (haircut)</Pill>
          </div>
          <div style={{ marginTop: 12 }}>
            <WilsonPill n={ticker.setupStats.n} winRate={ticker.setupStats.winRate} lb={ticker.setupStats.wilsonLB} />
          </div>
        </div>
        <div className="th-right">
          <EdgeDecayChart />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Headline Edge"
          sub="Wilson CI · profit factor · median R · n"
          style={headerStyle} right={<StateToggle name="tr-1" />} />
        <StateWrap state={s1.value} source="setup_stats.json · per-family">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Win rate" value="61.7%" tone="gn" sub="n=47" />
              <KpiTile label="Wilson 95% LB" value="47.7%" tone="gn" sub="above 45% gate" />
              <KpiTile label="Profit factor" value="1.84" tone="gn" sub="haircut 1.41" />
              <KpiTile label="Median R" value="+0.72" tone="gn" sub="per closed trade" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Forward Expectancy"
          sub="conditional on this exact setup, regime-matched"
          style={headerStyle} right={<StateToggle name="tr-2" />} />
        <StateWrap state={s2.value} source="walk-forward · 12-mo holdout">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Median fwd 10d" value="+2.4%" tone="gn" />
              <KpiTile label="P(T1 first)" value="58.5%" tone="gn" />
              <KpiTile label="P(stop first)" value="40.0%" tone="amb" />
              <KpiTile label="Expectancy · R" value="+0.51" tone="gn" sub="per trade" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Edge Decay · 12-mo Blocks"
          sub="rolling Wilson LB over trailing windows"
          style={headerStyle} right={<StateToggle name="tr-3" />} />
        <StateWrap state={s3.value} source="rolling-window backtest">
          <div className="lens-pad"><EdgeDecayPanel /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Walk-Forward Holdout"
          sub="train · validate · holdout slices · prevents over-fit"
          style={headerStyle} right={<StateToggle name="tr-4" />} />
        <StateWrap state={s4.value} source="walk-forward harness">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="In-sample WR" value="63.2%" tone="ink" sub="train" />
              <KpiTile label="Out-of-sample WR" value="61.7%" tone="gn" sub="holdout — no decay" />
              <KpiTile label="KS drift" value="0.08" tone="gn" sub="below 0.15 alert" />
              <KpiTile label="Stability score" value="A−" tone="gn" sub="stable last 4 blocks" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Forward Monte Carlo"
          sub="2,000 paths · setup-conditional · 10-day horizon"
          style={headerStyle} right={<StateToggle name="tr-5" />} />
        <StateWrap state={s5.value} source="MC harness · holdout-trained">
          <div className="lens-pad"><DistributionBars /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="gn" cells={[
            { lens: "Track Rec.",  verdict: "EDGE",  tone: "gn",  note: "Wilson 47.7% · PF 1.41 haircut" },
            { lens: "Plan",        verdict: "READY", tone: "gn",  note: "R 1.74 · sized" },
            { lens: "AI Edge",     verdict: "+0.18", tone: "gn",  note: "hit-net agrees" },
            { lens: "Regime",      verdict: "BULL",  tone: "gn",  note: "highest historical WR regime" },
            { lens: "Risk",        verdict: "OK",    tone: "gn",  note: "expectancy · half-Kelly fits" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Track Record</span>
        <span className="mono">
          n=<b>47</b>, Wilson LB <b className="up">47.7%</b>, expectancy
          <b className="up">+0.51R</b> per trade. <b>Edge is real and stable.</b>
        </span>
      </div>
    </div>
  );
}

function EdgeDecayChart() {
  const w = 240, h = 90;
  // 12 blocks of WR
  const data = [0.54, 0.58, 0.61, 0.59, 0.62, 0.65, 0.63, 0.60, 0.58, 0.61, 0.62, 0.617];
  const xStep = (w - 24) / (data.length - 1);
  const y = v => h - 14 - ((v - 0.40) / 0.30) * (h - 24);
  const pts = data.map((v, i) => [12 + i * xStep, y(v)]);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1="0" y1={y(0.45)} x2={w} y2={y(0.45)} stroke="var(--rd-dim)" strokeDasharray="3 3" />
      <text x="2" y={y(0.45) - 3} fontSize="9" className="mono" fill="var(--rd)">45% gate</text>
      <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--gn)" strokeWidth="1.6" fill="none" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2" fill={i === pts.length-1 ? "var(--copper)" : "var(--gn)"} />)}
      <text x={w - 2} y="12" fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">stable</text>
    </svg>
  );
}

function EdgeDecayPanel() {
  const blocks = [
    { period: "2023 H1", wr: 0.54, lb: 0.40, n: 16, tone: "amb" },
    { period: "2023 H2", wr: 0.59, lb: 0.43, n: 19, tone: "gn" },
    { period: "2024 H1", wr: 0.62, lb: 0.48, n: 22, tone: "gn" },
    { period: "2024 H2", wr: 0.60, lb: 0.45, n: 18, tone: "gn" },
    { period: "2025 H1", wr: 0.65, lb: 0.51, n: 24, tone: "gn" },
    { period: "TTM",     wr: 0.617, lb: 0.477, n: 47, tone: "gn", current: true },
  ];
  return (
    <div className="ed-grid">
      {blocks.map((b, i) => (
        <div key={i} className={`ed-cell ${b.current ? "is-current" : ""}`}>
          <div className="ed-period mono dim">{b.period}</div>
          <div className={`ed-wr mono kpi-tone--${b.tone}`}>{(b.wr * 100).toFixed(1)}%</div>
          <div className="ed-meta mono dim2">LB {(b.lb * 100).toFixed(0)}% · n={b.n}</div>
        </div>
      ))}
    </div>
  );
}

function DistributionBars() {
  // synthetic forward 10d return distribution (% buckets)
  const buckets = [
    { lo: -10, hi: -7, p: 4 },
    { lo: -7,  hi: -5, p: 8 },
    { lo: -5,  hi: -3, p: 12 },
    { lo: -3,  hi: -1, p: 16 },
    { lo: -1,  hi: 1,  p: 14 },
    { lo: 1,   hi: 3,  p: 16 },
    { lo: 3,   hi: 5,  p: 14 },
    { lo: 5,   hi: 8,  p: 10 },
    { lo: 8,   hi: 12, p: 6  },
  ];
  const max = Math.max(...buckets.map(b => b.p));
  return (
    <div className="dist-block">
      <div className="dist-bars">
        {buckets.map((b, i) => {
          const positive = (b.lo + b.hi) / 2 >= 0;
          return (
            <div key={i} className="dist-bar-col">
              <div className="dist-bar" style={{
                height: `${(b.p / max) * 100}%`,
                background: positive ? "var(--gn)" : "var(--rd)",
                opacity: 0.7,
              }} />
              <div className="dist-bar-lbl mono dim">{b.lo > 0 ? "+" : ""}{b.lo}</div>
            </div>
          );
        })}
      </div>
      <div className="dist-stats">
        <span className="mono">Median <b className="up">+2.4%</b></span>
        <span className="mono">P25 <b>−1.1%</b></span>
        <span className="mono">P75 <b className="up">+5.6%</b></span>
        <span className="mono dim2">2,000 paths · holdout-trained</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// ML EDGE — direction, magnitude cone, hit-net probability
// ────────────────────────────────────────────────────────────
function LensML({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("ml-1"); const s2 = useStateToggle("ml-2");
  const s3 = useStateToggle("ml-3"); const s4 = useStateToggle("ml-4");
  // mode-aware forecast from the shared projection engine
  const moKey = mode === "POSITION" ? "position" : mode === "INVESTMENT" ? "invest" : "swing";
  const pj = (window.AIPredict && ticker && ticker.symbol) ? window.AIPredict.projection(ticker.symbol, moKey) : null;
  const hz = pj ? pj.horizon : "10d";
  const pUp = pj ? pj.pUp : 0.61;
  const hitNet = pj ? +(pj.hit.p_t1_first - pj.hit.p_stop_first).toFixed(2) : 0.18;
  const dirTone = pUp >= 0.6 ? "gn" : pUp >= 0.45 ? "amb" : "rd";

  return (
    <div className="lens lens--ml">
      <div className="hero ml-hero">
        <div className="th-left">
          <div className="label-cap">3-head ML forecast · {hz} horizon · {mode}</div>
          <div className="th-score">
            <div className="th-score-num mono">{hitNet >= 0 ? "+" : ""}{hitNet.toFixed(2)}</div>
            <Pill tone={hitNet >= 0 ? "gn" : "rd"} dot>hit-net edge</Pill>
            <Pill tone={dirTone} small>Direction {Math.round(pUp * 100)}%</Pill>
            <Pill tone="amb" small>Magnitude wide</Pill>
          </div>
          <div className="th-pill-row">
            <Pill tone="ink" small>Calibration · OK</Pill>
            <Pill tone="ink" small>Drift KS 0.07</Pill>
            <Pill tone="ink" small>Top-3 features</Pill>
          </div>
        </div>
        <div className="th-right">
          <MLConeChart ticker={ticker} pj={pj} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Head 1 · Direction"
          sub={`P(up) over next ${hz}`}
          style={headerStyle} right={<StateToggle name="ml-1" />} />
        <StateWrap state={s1.value} source="ml_edge_predictions.json · classifier head">
          <div className="lens-pad"><ProbBar v={pUp} label={`P(up · ${hz})`} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Head 2 · Magnitude Cone"
          sub={`quantile regression · ${hz} return distribution`}
          style={headerStyle} right={<StateToggle name="ml-2" />} />
        <StateWrap state={s2.value} source="quantile regressor head">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="P10" value={`${pj ? (pj.mag.q10>=0?"+":"") + pj.mag.q10 : "−4.2"}%`} tone="rd" />
              <KpiTile label="P50 (median)" value={`${pj ? (pj.mag.q50>=0?"+":"") + pj.mag.q50 : "+6.4"}%`} tone={pj && pj.mag.q50 < 0 ? "rd" : "gn"} />
              <KpiTile label="P90" value={`${pj ? "+" + pj.mag.q90 : "+12.1"}%`} tone="gn" />
              <KpiTile label="Skew" value={pj ? ((pj.mag.q90 + pj.mag.q10) >= 0 ? "+0.42" : "−0.31") : "+0.42"} tone="gn" sub="right-skewed" />
            </div>
          </div>
        </StateWrap>
      </div>

      {window.AIProjectionChart && pj && (
        <div className="lens-section">
          <SectionHeader n={2.5} title="Price Projection · annotated chart"
            sub={`candles · MA20/50/200 · breakout base · forward AI zone → target +${pj.mag.q90}%`}
            style={headerStyle} right={<StateToggle name="ml-25" />} />
          <StateWrap state={s2.value} source="OHLCV (demo) + ml_edge projection">
            <div className="lens-pad">{React.createElement(window.AIProjectionChart, { P: { sym: ticker.symbol, px: ticker.price }, proj: pj })}</div>
          </StateWrap>
        </div>
      )}

      <div className="lens-section">
        <SectionHeader n={3} title="Head 3 · Hit-Net (T1 vs Stop)"
          sub="P(T1 first) − P(stop first) — the actionable edge"
          style={headerStyle} right={<StateToggle name="ml-3" />} />
        <StateWrap state={s3.value} source="hit-net head · path-conditional">
          <div className="lens-pad"><HitNetBar /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Calibration · Feature Importance"
          sub="reliability diagram + top features by SHAP"
          style={headerStyle} right={<StateToggle name="ml-4" />} />
        <StateWrap state={s4.value} source="model card · monthly recalibrate">
          <div className="lens-pad"><CalibrationPanel /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="violet" cells={[
            { lens: "AI Edge",     verdict: `${hitNet >= 0 ? "+" : ""}${hitNet.toFixed(2)}`, tone: hitNet >= 0 ? "gn" : "rd", note: `hit-net · ${hz}` },
            { lens: "Direction",   verdict: `${Math.round(pUp * 100)}%`,   tone: dirTone, note: `P(up) ${hz}` },
            { lens: "Magnitude",   verdict: "WIDE",  tone: "amb",note: pj ? `q10 ${pj.mag.q10} / q90 +${pj.mag.q90}` : "P10 −4 / P90 +12" },
            { lens: "Track Rec.",  verdict: "EDGE",  tone: "gn", note: "Wilson 47.7%" },
            { lens: "Plan",        verdict: "READY", tone: "gn", note: "R 1.74" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · AI Edge · {mode}</span>
        <span className="mono">
          P(T1 first) − P(stop first) = <b className={hitNet >= 0 ? "up" : "dn"}>{hitNet >= 0 ? "+" : ""}{hitNet.toFixed(2)}</b> over the <b>{hz}</b> horizon. Calibration OK,
          drift low. Model and rules agree.
        </span>
      </div>
    </div>
  );
}

function ProbBar({ v, label }) {
  return (
    <div className="probbar">
      <div className="probbar-label mono dim2">{label}</div>
      <div className="probbar-bar">
        <div className="probbar-fill" style={{ width: `${v * 100}%` }} />
        <div className="probbar-mid" />
      </div>
      <div className="probbar-val mono"><b>{(v * 100).toFixed(0)}%</b></div>
      <div className="probbar-meta mono dim">vs 50% baseline · +11pt edge</div>
    </div>
  );
}

function HitNetBar() {
  const pT1 = 0.58, pStop = 0.40;
  return (
    <div className="hitnet">
      <div className="hn-row">
        <span className="hn-label mono">P(T1 first)</span>
        <div className="hn-bar"><div className="hn-fill hn-gn" style={{ width: `${pT1 * 100}%` }} /></div>
        <span className="hn-val mono up">{(pT1 * 100).toFixed(0)}%</span>
      </div>
      <div className="hn-row">
        <span className="hn-label mono">P(stop first)</span>
        <div className="hn-bar"><div className="hn-fill hn-rd" style={{ width: `${pStop * 100}%` }} /></div>
        <span className="hn-val mono dn">{(pStop * 100).toFixed(0)}%</span>
      </div>
      <div className="hn-row hn-final">
        <span className="hn-label mono">Hit-net</span>
        <div className="hn-bar"><div className="hn-fill" style={{
          width: `${(pT1 - pStop) * 100}%`,
          background: "linear-gradient(90deg, var(--copper), var(--violet))",
        }} /></div>
        <span className="hn-val mono copper"><b>+{((pT1 - pStop) * 100).toFixed(0)}%</b></span>
      </div>
    </div>
  );
}

function MLConeChart({ ticker, pj }) {
  const q90 = pj ? pj.mag.q90 : 12.1, q50 = pj ? pj.mag.q50 : 6.4, q10 = pj ? pj.mag.q10 : -4.2;
  const hz = pj ? pj.horizon : "10d";
  return (
    <svg viewBox="0 0 300 120" width="300" height="120" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="mlc-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="mlc-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="60" x2="280" y2="60" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 60 Q 150 24 280 16 L 280 60 L 20 60 Z" fill="url(#mlc-gn)" />
      <path d="M 20 60 Q 150 88 280 104 L 280 60 L 20 60 Z" fill="url(#mlc-rd)" />
      <path d="M 20 60 Q 150 24 280 16" stroke="var(--gn)" strokeWidth="1.4" fill="none" opacity="0.55" />
      <path d="M 20 60 Q 150 38 280 38" stroke="var(--gn)" strokeWidth="1.8" fill="none"
            style={{ filter: "drop-shadow(0 0 6px var(--gn))" }} />
      <path d="M 20 60 Q 150 88 280 104" stroke="var(--rd)" strokeWidth="1.4" fill="none" opacity="0.55" />
      <circle cx="20" cy="60" r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x="276" y="13" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">P90 +{q90}%</text>
      <text x="276" y="35" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)" fontWeight="500">P50 {q50 >= 0 ? "+" : ""}{q50}%</text>
      <text x="276" y="113" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">P10 {q10}%</text>
      <text x="20" y="113" fontSize="9" className="mono" fill="var(--ink-3)">T+0</text>
      <text x="276" y="60" fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{hz}</text>
    </svg>
  );
}

function CalibrationPanel() {
  const features = [
    { f: "RVOL × pivot-distance", w: 0.28 },
    { f: "Sector ETF 1M return",  w: 0.18 },
    { f: "Insider net 90d (z)",   w: 0.14 },
    { f: "VIX regime",            w: 0.12 },
    { f: "Wilson LB · same setup",w: 0.11 },
    { f: "Earnings days · log",   w: 0.09 },
  ];
  return (
    <div className="cal-grid">
      <div className="cal-block">
        <div className="label-cap" style={{ marginBottom: 6 }}>Reliability</div>
        <svg viewBox="0 0 200 110" width="100%" height="110">
          <line x1="20" y1="100" x2="190" y2="10" stroke="var(--line)" strokeDasharray="3 3" />
          {[
            [30, 92], [60, 78], [90, 60], [120, 44], [150, 30], [180, 14],
          ].map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="var(--copper)" />)}
          <text x="190" y="9" fontSize="9" className="mono" textAnchor="end" fill="var(--copper)">obs ≈ pred</text>
          <text x="20" y="108" fontSize="9" className="mono" fill="var(--ink-3)">0</text>
          <text x="190" y="108" fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">1.0</text>
        </svg>
        <div className="cal-note mono dim2" style={{ marginTop: 6 }}>Brier 0.21 · log-loss 0.59 · ECE 0.04</div>
      </div>
      <div className="cal-block">
        <div className="label-cap" style={{ marginBottom: 6 }}>Top features · SHAP</div>
        <div className="feat-list">
          {features.map((f, i) => (
            <div key={i} className="feat-row">
              <span className="mono">{f.f}</span>
              <div className="feat-bar"><div className="feat-fill" style={{ width: `${f.w * 280}%` }} /></div>
              <span className="mono dim">{(f.w * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

window.LensTrack = LensTrack;
window.LensML = LensML;
