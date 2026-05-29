// lens-smc.jsx + lens-risk.jsx — Smart Money Concepts and Risk lenses

const { useMemo: useMemoSR } = React;

// ────────────────────────────────────────────────────────────
// SMC — order blocks, FVG, BoS/CHoCH, liquidity sweeps
// ────────────────────────────────────────────────────────────
function LensSMC({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("sm-1"); const s2 = useStateToggle("sm-2");
  const s3 = useStateToggle("sm-3"); const s4 = useStateToggle("sm-4");

  return (
    <div className="lens lens--smc">
      <div className="hero smc-hero">
        <div className="th-left">
          <div className="label-cap">SMC structure read</div>
          <div className="th-score">
            <div className="th-score-num mono">PASS</div>
            <Pill tone="cy" dot>BoS + OB held</Pill>
          </div>
          <div className="th-pill-row">
            <Pill tone="gn" small>4 OB · 2 mitigated</Pill>
            <Pill tone="cy" small>3 FVG · 1 filled</Pill>
            <Pill tone="amb" small>liquidity above $70.40</Pill>
            <Pill tone="gn" small>VWAP reclaimed</Pill>
          </div>
        </div>
        <div className="th-right">
          <SMCMicroChart />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Order Blocks"
          sub="last 6 unmitigated demand/supply zones · institutional footprints"
          style={headerStyle} right={<StateToggle name="sm-1" />} />
        <StateWrap state={s1.value} source="bespoke detector · candle structure">
          <div className="lens-pad"><OBTable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Fair Value Gaps · BoS · CHoCH"
          sub="structural shifts · break-of-structure log"
          style={headerStyle} right={<StateToggle name="sm-2" />} />
        <StateWrap state={s2.value} source="structure aggregator">
          <div className="lens-pad"><StructureLog /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Liquidity Sweeps"
          sub="stop-hunts above prior highs / below prior lows"
          style={headerStyle} right={<StateToggle name="sm-3" />} />
        <StateWrap state={s3.value} source="sweep detector · 30 sessions">
          <div className="lens-pad"><LiquiditySweeps /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="LuxAlgo MTF Screener"
          sub="confluence across 1H · 4H · D · W"
          style={headerStyle} right={<StateToggle name="sm-4" />} />
        <StateWrap state={s4.value} source="LuxAlgo · external feed">
          <div className="lens-pad"><MTFScreener /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="cy" cells={[
            { lens: "SMC",        verdict: "PASS",  tone: "gn",  note: "BoS + OB held · liquidity above" },
            { lens: "Technicals", verdict: "PASS",  tone: "gn",  note: "RSI 64 · stacked MAs" },
            { lens: "Patterns",   verdict: "VCP",   tone: "gn",  note: "5 contractions" },
            { lens: "Volume",     verdict: "DRY",   tone: "amb", note: "below avg on pullback" },
            { lens: "Risk",       verdict: "OK",    tone: "gn",  note: "stop below last OB" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · SMC</span>
        <span className="mono">
          OB at <b className="copper">$63.20–$63.80</b> held the spring · liquidity rests
          above <b className="up">$70.40</b>. Entry valid above pivot · stop below OB.
        </span>
      </div>
    </div>
  );
}

function SMCMicroChart() {
  return (
    <svg viewBox="0 0 280 110" width="280" height="110" preserveAspectRatio="xMidYMid meet">
      {/* OB zone */}
      <rect x="40" y="68" width="220" height="14" fill="var(--cy)" opacity="0.20" />
      <text x="46" y="78" fontSize="9" className="mono" fill="var(--cy)">OB · $63.80</text>
      {/* FVG */}
      <rect x="170" y="40" width="60" height="10" fill="var(--violet)" opacity="0.25" />
      <text x="174" y="48" fontSize="8" className="mono" fill="var(--violet)">FVG</text>
      {/* Price line */}
      <polyline fill="none" stroke="var(--copper)" strokeWidth="1.5"
                points="10,90 30,75 50,82 70,72 100,76 130,60 160,50 190,55 220,38 260,22" />
      {/* BoS label */}
      <line x1="155" y1="50" x2="155" y2="62" stroke="var(--gn)" strokeWidth="1" strokeDasharray="2 2" />
      <text x="158" y="58" fontSize="8" className="mono" fill="var(--gn)">BoS</text>
      {/* Liquidity zone */}
      <line x1="0" y1="22" x2="280" y2="22" stroke="var(--amb)" strokeDasharray="3 3" opacity="0.6" />
      <text x="4" y="20" fontSize="8" className="mono" fill="var(--amb)">LIQUIDITY</text>
    </svg>
  );
}

function OBTable() {
  const rows = [
    { px: "$70.10–$70.80", type: "SUPPLY", state: "Unmitigated", note: "high-vol gap-fill zone", tone: "rd" },
    { px: "$67.40–$67.80", type: "DEMAND", state: "Held",        note: "intraday flip · weak",   tone: "amb" },
    { px: "$66.10–$66.60", type: "DEMAND", state: "Mitigated",   note: "current pivot floor",   tone: "gn"  },
    { px: "$63.20–$63.80", type: "DEMAND", state: "Held",        note: "spring · stop below",   tone: "gn"  },
    { px: "$60.40–$60.90", type: "DEMAND", state: "Unmitigated", note: "deep pullback target",  tone: "ink" },
    { px: "$56.10–$57.00", type: "DEMAND", state: "Unmitigated", note: "earnings-gap origin",   tone: "ink" },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Zone</th><th>Type</th><th>State</th><th>Note</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono">{r.px}</td>
            <td><Pill tone={r.type === "DEMAND" ? "gn" : "rd"} small>{r.type}</Pill></td>
            <td><Pill tone={r.tone} small>{r.state}</Pill></td>
            <td className="mono dim">{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StructureLog() {
  const events = [
    { when: "May 22", evt: "BoS · 4H", px: "$66.10", impact: "trend continuation up", tone: "gn" },
    { when: "May 19", evt: "FVG filled · D", px: "$64.30", impact: "demand confirmed", tone: "gn" },
    { when: "May 12", evt: "CHoCH · 1H", px: "$63.20", impact: "minor correction end", tone: "amb" },
    { when: "May 06", evt: "BoS · D", px: "$65.40", impact: "macro structure flipped bullish", tone: "gn" },
    { when: "Apr 22", evt: "Spring · D", px: "$62.10", impact: "swept Apr lows, reversed", tone: "cy" },
  ];
  return (
    <div className="struct-log">
      {events.map((e, i) => (
        <div key={i} className={`sl-row sl-${e.tone}`}>
          <span className="mono dim2 sl-when">{e.when}</span>
          <span className="mono sl-evt">{e.evt}</span>
          <span className="mono copper sl-px">{e.px}</span>
          <span className="mono dim sl-impact">{e.impact}</span>
        </div>
      ))}
    </div>
  );
}

function LiquiditySweeps() {
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
      <KpiTile label="Sell-side · prior lows" value="$62.10" tone="amb" sub="swept Apr 22 · reversed" />
      <KpiTile label="Buy-side · prior highs" value="$70.40" tone="copper" sub="untaken · target above" />
      <KpiTile label="Equal highs · resting liq" value="$74.20" tone="amb" sub="3-touch · magnet" />
    </div>
  );
}

function MTFScreener() {
  const rows = [
    { tf: "1H",  bias: "BULL", trend: "↑", note: "above EMA stack, BoS intact",       tone: "gn" },
    { tf: "4H",  bias: "BULL", trend: "↑", note: "above OB $63.20, BoS confirmed",   tone: "gn" },
    { tf: "1D",  bias: "BULL", trend: "↑", note: "macro structure flipped bullish",   tone: "gn" },
    { tf: "1W",  bias: "NEUT", trend: "→", note: "range $58–$74, awaiting break",     tone: "amb" },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr><th>TF</th><th>Bias</th><th>Trend</th><th>Read</th></tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono"><b>{r.tf}</b></td>
            <td><Pill tone={r.tone} small>{r.bias}</Pill></td>
            <td className={`mono ${r.tone === "gn" ? "up" : "warn"}`}>{r.trend}</td>
            <td className="mono dim">{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ────────────────────────────────────────────────────────────
// RISK — VaR, Kelly, drawdown, stress, liquidity
// ────────────────────────────────────────────────────────────
function LensRisk({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("rk-1"); const s2 = useStateToggle("rk-2");
  const s3 = useStateToggle("rk-3"); const s4 = useStateToggle("rk-4");
  const s5 = useStateToggle("rk-5");

  return (
    <div className="lens lens--risk">
      <div className="hero risk-hero">
        <div className="th-left">
          <div className="label-cap">Risk read · per-trade + book</div>
          <div className="th-score">
            <div className="th-score-num mono">OK</div>
            <Pill tone="gn" dot>within gates</Pill>
            <Pill tone="amb" small>ER in 11d · cap size</Pill>
          </div>
        </div>
        <div className="th-right">
          <LossCone />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Loss-Distribution Cones"
          sub="1-day · 1σ / 2σ / 3σ · based on 60d realized vol"
          style={headerStyle} right={<StateToggle name="rk-1" />} />
        <StateWrap state={s1.value} source="vol engine · 60d realized">
          <div className="lens-pad"><RiskCones ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Live Kelly · Sizing Metrics"
          sub="real-time using current edge + portfolio_state"
          style={headerStyle} right={<StateToggle name="rk-2" />} />
        <StateWrap state={s2.value} source="risk engine">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Raw Kelly" value="84%" tone="amb" sub="(p·b−q)/b" />
              <KpiTile label="½ Kelly · capped" value="42%" tone="copper" sub="discipline" />
              <KpiTile label="Final size %" value="6.8%" tone="copper" sub="of NAV · 110 sh" />
              <KpiTile label="Max loss" value="$420" tone="rd" sub="0.39% of NAV" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="VaR · CVaR · Sharpe"
          sub="1d · 10d · per-ticker + post-fill book impact"
          style={headerStyle} right={<StateToggle name="rk-3" />} />
        <StateWrap state={s3.value} source="risk engine · MC + parametric">
          <div className="lens-pad"><VarTable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Stress · 6 × 5 Heatmap"
          sub="scenario × outcome · MoS in each cell"
          style={headerStyle} right={<StateToggle name="rk-4" />} />
        <StateWrap state={s4.value} source="scenario engine">
          <div className="lens-pad"><StressGrid /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Liquidity Ladder · β exposure"
          sub="bid/ask depth · ADV slip · book-β post-fill"
          style={headerStyle} right={<StateToggle name="rk-5" />} />
        <StateWrap state={s5.value} source="quotes + portfolio_state">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="L1 spread" value="$0.04" tone="gn" sub="6 bps · OK" />
              <KpiTile label="ADV slip est." value="−$0.03" tone="gn" sub="110 sh / 1.12M ADV" />
              <KpiTile label="Book β · pre" value="0.93" tone="ink" />
              <KpiTile label="Book β · post" value="0.96" tone="amb" sub="+0.03 · within cap 1.10" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="rd" cells={[
            { lens: "Risk",       verdict: "OK",     tone: "gn",  note: "all gates pass · cap size pre-ER" },
            { lens: "Plan",       verdict: "READY",  tone: "gn",  note: "R 1.74 · stop $62.40" },
            { lens: "Earnings",   verdict: "11 d",   tone: "amb", note: "trim 25% pre-ER" },
            { lens: "Portfolio",  verdict: "FIT",    tone: "gn",  note: "correl 0.34 · NAV 6.8%" },
            { lens: "Liquidity",  verdict: "OK",     tone: "gn",  note: "1.12M ADV · 6 bps spread" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · Risk</span>
        <span className="mono">
          Max loss <b className="dn">$420</b> = 0.39% NAV · VaR(1d) <b className="warn">−2.1%</b> ·
          Sharpe contrib +0.04. <b>Pass.</b>
        </span>
      </div>
    </div>
  );
}

function LossCone() {
  return (
    <svg viewBox="0 0 280 110" width="280" height="110">
      <line x1="20" y1="55" x2="270" y2="55" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 55 Q 130 14 270 14"  stroke="var(--gn)" strokeWidth="1.2" fill="none" opacity="0.5" />
      <path d="M 20 55 Q 130 30 270 30"  stroke="var(--gn)" strokeWidth="1.4" fill="none" />
      <path d="M 20 55 Q 130 78 270 78"  stroke="var(--rd)" strokeWidth="1.4" fill="none" />
      <path d="M 20 55 Q 130 96 270 96"  stroke="var(--rd)" strokeWidth="1.2" fill="none" opacity="0.5" />
      <circle cx="20" cy="55" r="3" fill="var(--copper)" />
      <text x="266" y="11" fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">+3σ +6.4%</text>
      <text x="266" y="27" fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">+1σ +2.1%</text>
      <text x="266" y="82" fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">−1σ −2.1%</text>
      <text x="266" y="106" fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">−3σ −6.4%</text>
    </svg>
  );
}

function RiskCones({ ticker }) {
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      <KpiTile label="1d · 1σ" value="±2.1%" tone="ink" sub="$66.01 — $68.83" />
      <KpiTile label="1d · 2σ" value="±4.2%" tone="amb" sub="$64.60 — $70.24" />
      <KpiTile label="1d · 3σ" value="±6.4%" tone="rd" sub="$63.10 — $71.74" />
      <KpiTile label="10d · 1σ" value="±6.6%" tone="amb" sub="$62.97 — $71.87" />
    </div>
  );
}

function VarTable() {
  const rows = [
    { metric: "VaR · 1d · 95%",  v: "−2.1%", abs: "−$155 (110 sh)", tone: "amb" },
    { metric: "CVaR · 1d · 95%", v: "−2.9%", abs: "−$214 (tail avg)", tone: "amb" },
    { metric: "VaR · 10d · 95%", v: "−6.6%", abs: "−$487",          tone: "rd"  },
    { metric: "Sharpe contrib", v: "+0.04", abs: "on book",         tone: "gn"  },
    { metric: "Sortino contrib",v: "+0.07", abs: "on book",         tone: "gn"  },
    { metric: "Max DD if stop hits", v: "−5.9%", abs: "−$420 · 0.39% NAV", tone: "rd" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Metric</th><th className="r">Value</th><th>Absolute</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono">{r.metric}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.v}</td>
            <td className="mono dim">{r.abs}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StressGrid() {
  const scenarios = [
    "−3σ market gap", "Rate +50bp", "VIX → 30", "Sector ETF −5%", "Earnings −15%", "Liquidity halve",
  ];
  const outcomes = ["P&L", "% NAV", "Stop hit?", "Days to recover", "Action"];
  // synthesize
  const grid = scenarios.map((s, i) => [
    { v: `−$${(380 + i * 90).toFixed(0)}`,  tone: i < 3 ? "amb" : "rd" },
    { v: `−${(0.35 + i * 0.10).toFixed(2)}%`, tone: i < 3 ? "amb" : "rd" },
    { v: i < 2 ? "no" : i < 4 ? "tight" : "YES", tone: i < 2 ? "gn" : i < 4 ? "amb" : "rd" },
    { v: i < 2 ? "1–2" : i < 4 ? "3–5" : "—", tone: "ink" },
    { v: i < 2 ? "hold" : i < 4 ? "trim 25%" : "flatten", tone: i < 2 ? "gn" : i < 4 ? "amb" : "rd" },
  ]);
  return (
    <div className="stress-grid">
      <div className="sg-corner" />
      {outcomes.map((o, i) => (
        <div key={i} className="sg-col-hdr mono label-cap">{o}</div>
      ))}
      {scenarios.map((s, r) => (
        <React.Fragment key={r}>
          <div className="sg-row-hdr mono">{s}</div>
          {grid[r].map((c, ci) => (
            <div key={ci} className={`sg-cell sg-${c.tone}`}>{c.v}</div>
          ))}
        </React.Fragment>
      ))}
    </div>
  );
}

window.LensSMC = LensSMC;
window.LensRisk = LensRisk;
