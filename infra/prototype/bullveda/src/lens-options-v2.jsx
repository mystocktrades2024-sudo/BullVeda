// lens-options-v2.jsx — Quant Options lens, mirroring kairos.html structure.
// §0 Session · §1 Vol Regime · §2 Expected Move · §3 Flow · §3.5 NBBO · §3.7 Chain ·
// §4 Strategy Matrix · §4.5 Profit Grid · §5 Payoff · §6 Scenario · §8 Triggers.
// Replaces window.LensOptions.

const { useMemo: useMemoOQ } = React;

function LensOptions({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s = (n) => useStateToggle("opx-" + n);
  const sec = [s(0), s(1), s(2), s(3), s(35), s(37), s(4), s(45), s(5), s(6), s(8)];
  return (
    <div className="lens lens--opt">
      <OptionsHeroPro />
      <div className="lens-section">
        <SectionHeader n="0" title="Session · Context"
          sub="pre-trade gates · session decomposition · venue routing · contract metadata"
          style={headerStyle} right={<StateToggle name="opx-0" />} />
        <StateWrap state={sec[0].value} source="Schwab /markets/hours · /markets/quotes · venue routing">
          <div className="lens-pad"><SessionContext /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="1" title="Vol Regime"
          sub="is option premium cheap or expensive right now?"
          style={headerStyle} right={<StateToggle name="opx-1" />} />
        <StateWrap state={sec[1].value} source="EODHD /options · 252d ATM 30d history">
          <div className="lens-pad"><VolRegime /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="2" title="Vol Richness · Expected Move"
          sub="IV vs realized 30d + ±1σ / ±2σ price projections"
          style={headerStyle} right={<StateToggle name="opx-2" />} />
        <StateWrap state={sec[2].value} source="EODHD · IV from chain · HV from /technical">
          <div className="lens-pad"><ExpectedMove /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="3" title="Flow · Positioning"
          sub="open interest by strike · dealer gamma · max-pain magnet"
          style={headerStyle} right={<StateToggle name="opx-3" />} />
        <StateWrap state={sec[3].value} source="EODHD OI · gamma model · Schwab UOA">
          <div className="lens-pad"><FlowPositioning /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="3.5" title="Liquidity · NBBO Quotes"
          sub="Schwab real-time bid/ask · spread width · size · liquidity gates"
          style={headerStyle} right={<StateToggle name="opx-35" />} />
        <StateWrap state={sec[4].value} source="Schwab /markets/quotes · NBBO · model fallback">
          <div className="lens-pad"><NBBOTable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="3.7" title="Full Options Chain · 35 DTE"
          sub="all strikes · bid/mid/ask · vol · OI · IV · Δ · BS-priced ladder"
          style={headerStyle} right={<StateToggle name="opx-37" />} />
        <StateWrap state={sec[5].value} source="Schwab /markets/options/chains · Black-Scholes overlay">
          <div className="lens-pad"><FullChain /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="4" title="Strategy Matrix"
          sub="priced via Black-Scholes · strikes auto-selected from Plan T1/T2 · DTE matched to hold"
          style={headerStyle} right={<StateToggle name="opx-4" />} />
        <StateWrap state={sec[6].value} source="strategy synthesizer · BS priced ATM σ=48.8%, r=4.5%">
          <div className="lens-pad"><StrategyTable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="4.5" title="Profit Calculator · Daily % Return Grid"
          sub="P&L at each (price · day) · Black-Scholes re-priced every cell · % of max risk"
          style={headerStyle} right={<StateToggle name="opx-45" />} />
        <StateWrap state={sec[7].value} source="BS engine · time-decay aware · σ=49% r=4.5%">
          <div className="lens-pad"><ProfitGrid /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="5" title="Payoff Diagrams"
          sub="visual P&L curves at expiry · stop/T1/T2 markers · R/R + POP"
          style={headerStyle} right={<StateToggle name="opx-5" />} />
        <StateWrap state={sec[8].value} source="payoff calc · Greeks-aware">
          <div className="lens-pad"><PayoffDiagram /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="6" title="Scenario P&L"
          sub="same scenarios, different vehicles · stock vs options at expiration"
          style={headerStyle} right={<StateToggle name="opx-6" />} />
        <StateWrap state={sec[9].value} source="scenario engine · Plan-derived levels">
          <div className="lens-pad"><ScenarioPL /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n="8" title="Management Triggers"
          sub="pre-decided exits · the system is the discipline · no emotional override"
          style={headerStyle} right={<StateToggle name="opx-8" />} />
        <StateWrap state={sec[10].value} source="playbook · per-strategy rules">
          <div className="lens-pad"><MgmtTriggers /></div>
        </StateWrap>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Options</span>
        <span className="mono">
          IV under-prices realized (<b className="warn">0.77×</b>) → <b className="copper">long premium</b> has positive expectancy.
          Trigger: <b>Bear Put Spread · 35 DTE · +740P/−625P</b> · model debit <b>$3,574</b> · POP 35% · max loss capped at premium.
        </span>
      </div>
    </div>
  );
}

// ─── Hero ──────────────────────────────────────────────────────────
function OptionsHeroPro() {
  return (
    <div className="hero ohp">
      <div className="ohp-top">
        <div className="ohp-id">
          <span className="ohp-sym mono">PWR</span>
          <span className="ohp-px mono">$742.18</span>
          <Pill tone="amb" small>Neutral</Pill>
          <span className="ohp-meta mono dim2">score 65 · R:R 2.5</span>
          <span className="ohp-slogan mono dim2">system informs · you decide</span>
        </div>
        <div className="ohp-actions">
          <button className="ohp-act ohp-act--gn">▲ BUY</button>
          <button className="ohp-act ohp-act--rd">▼ SHORT</button>
          <button className="ohp-act">+ WATCH</button>
        </div>
      </div>

      <div className="ohp-strat">
        <div className="ohp-strat-lbl mono label-cap">Options · 30-90 DTE</div>
        <div className="ohp-strat-tags mono">
          <span className="ohp-tag ohp-tag--cop">SPREAD</span>
          <span className="ohp-tag">★★★☆☆ conv MED</span>
          <span className="ohp-tag">hold 35d</span>
          <span className="ohp-tag ohp-tag--gn">data FULL</span>
        </div>
      </div>

      <div className="ohp-kpis">
        <OhpKpi label="IV Rank (52w)"  v="50%"   tone="amb" sub="mid range" />
        <OhpKpi label="IV / HV 30d"    v="0.77"  tone="gn"  sub="market under-priced" />
        <OhpKpi label="Expected Move"  v="±14.0%" tone="amb" sub="ATM IV · 30d" />
        <OhpKpi label="P/C OI"         v="1.78"  tone="amb" sub="put-skewed" />
        <OhpKpi label="Max Pain"       v="$750"  tone="copper" sub="+1.1% vs spot" />
      </div>

      <div className="ohp-rows">
        <div className="ohp-row">
          <span className="ohp-row-lbl mono">Trigger</span>
          <span className="mono">
            <b className="copper">Bear Put Spread · 35 DTE · +740P/−625P</b> — model debit <b>$3,574</b> · POP 35% · Δ −0.34 · Θ $−30/d
          </span>
        </div>
        <div className="ohp-row">
          <span className="ohp-row-lbl mono">Invalidate</span>
          <span className="mono dim2">
            IV-rank crosses — · IV/HV crosses 1.0 · spot breaks <b className="dn">$624.06</b> on close. Any single trigger closes the position.
          </span>
        </div>
        <div className="ohp-row">
          <span className="ohp-row-lbl mono">Sizing</span>
          <span className="mono dim2">
            <b className="copper">0.5–1.5% NAV</b> in premium (debit only, no naked risk). Max loss capped at premium paid.
            Cross-link: Risk tab for full sizing math.
          </span>
        </div>
      </div>
    </div>
  );
}

function OhpKpi({ label, v, tone, sub }) {
  return (
    <div className="ohp-kpi">
      <div className="ohp-kpi-l label-cap">{label}</div>
      <div className={`ohp-kpi-v mono kpi-tone--${tone}`}>{v}</div>
      <div className="ohp-kpi-sub mono dim">{sub}</div>
    </div>
  );
}

// ─── §0 Session Context ─────────────────────────────────────────────
function SessionContext() {
  return (
    <div className="sec-ctx">
      <div className="sc-bar">
        <span className="sc-segment sc-pre">Pre</span>
        <span className="sc-segment sc-rth is-on">RTH</span>
        <span className="sc-segment sc-post">Post</span>
        <span className="sc-spot mono">$742.18</span>
      </div>
      <div className="sc-axis mono dim2">
        <span>−2d</span>
        <span>−1d</span>
        <span>today</span>
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginTop: 8 }}>
        <KpiTile label="Pre-Market"   value="—"     tone="ink" sub="04:00 → 09:29 ET" />
        <KpiTile label="RTH (regular)"value="—"     tone="ink" sub="close $742.18" />
        <KpiTile label="Post-Market"  value="—"     tone="ink" sub="16:00 → 20:00 ET" />
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginTop: 8 }}>
        <KpiTile label="Security Status"  value="NORMAL"  tone="gn" sub="not halted · regular trading" />
        <KpiTile label="Best Bid · Venue" value="$742.18" tone="ink" sub="—" />
        <KpiTile label="Best Ask · Venue" value="$742.18" tone="ink" sub="—" />
        <KpiTile label="Leverage Factor" value="1.0×"   tone="ink" sub="standard equity · no ETF amp" />
      </div>
    </div>
  );
}

// ─── §1 Vol Regime ──────────────────────────────────────────────────
function VolRegime() {
  return (
    <div className="vr">
      <div className="vr-chart-wrap">
        <div className="vr-chart-hdr">
          <span className="label-cap">IV Percentile · 252-day · ATM 30d</span>
          <span className="mono dim2">P80 / P50 / P20 bands</span>
        </div>
        <IVPercentileChart />
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="IV Rank"        value="50%"   tone="amb"    sub="mid · spreads" />
        <KpiTile label="Current IV ATM" value="48.8%" tone="ink"    sub="30d · ann. 1σ" />
        <KpiTile label="Term Structure" value="flat"  tone="ink"    sub="no contango / backwardation" />
        <KpiTile label="25Δ Skew"       value="+3.0"  tone="amb"    sub="fear premium" />
      </div>
    </div>
  );
}

function IVPercentileChart() {
  const w = 580, h = 180, padT = 14, padB = 30, padL = 36, padR = 14;
  // Synthetic 252d series of ATM 30d IV (annualized %), trending 35..55 with noise
  const data = useMemoOQ(() => {
    const out = [];
    let v = 38;
    for (let i = 0; i < 252; i++) {
      v += (Math.sin(i * 0.08) + Math.cos(i * 0.13)) * 0.6 + (Math.random() - 0.5) * 0.4;
      out.push(Math.max(25, Math.min(70, v)));
    }
    return out;
  }, []);
  const sorted = [...data].sort((a, b) => a - b);
  const p20 = sorted[Math.floor(sorted.length * 0.20)];
  const p50 = sorted[Math.floor(sorted.length * 0.50)];
  const p80 = sorted[Math.floor(sorted.length * 0.80)];
  const yMin = 25, yMax = 70;
  const x = i => padL + (i / (data.length - 1)) * (w - padL - padR);
  const y = v => padT + (1 - (v - yMin) / (yMax - yMin)) * (h - padT - padB);
  const pts = data.map((v, i) => [x(i), y(v)]);
  const last = data[data.length - 1];
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="iv-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.20" />
          <stop offset="100%" stopColor="var(--copper)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* P-bands */}
      <rect x={padL} y={y(p80)} width={w - padL - padR} height={y(p20) - y(p80)}
            fill="var(--amb)" opacity="0.06" />
      <line x1={padL} y1={y(p80)} x2={w - padR} y2={y(p80)} stroke="var(--amb-dim)" strokeDasharray="3 3" />
      <line x1={padL} y1={y(p50)} x2={w - padR} y2={y(p50)} stroke="var(--ink-3)" strokeDasharray="3 3" />
      <line x1={padL} y1={y(p20)} x2={w - padR} y2={y(p20)} stroke="var(--amb-dim)" strokeDasharray="3 3" />
      <text x={w - padR + 4} y={y(p80) + 3} fontSize="9" className="mono" fill="var(--amb)">P80</text>
      <text x={w - padR + 4} y={y(p50) + 3} fontSize="9" className="mono" fill="var(--ink-3)">P50</text>
      <text x={w - padR + 4} y={y(p20) + 3} fontSize="9" className="mono" fill="var(--amb)">P20</text>
      {/* axis labels */}
      {[30, 40, 50, 60].map(v => (
        <text key={v} x={padL - 6} y={y(v) + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">{v}%</text>
      ))}
      {/* fill + line */}
      <path d={`M ${padL} ${y(yMin)} L ${pts.map(p => p.join(",")).join(" L ")} L ${w - padR} ${y(yMin)} Z`} fill="url(#iv-fill)" />
      <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--copper)" strokeWidth="1.4" fill="none"
                style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
      {/* current marker */}
      <circle cx={x(data.length - 1)} cy={y(last)} r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x={x(data.length - 1) - 6} y={y(last) - 8} fontSize="9.5" className="mono" textAnchor="end" fill="var(--copper)">
        IV {last.toFixed(1)}%
      </text>
      {/* x ticks */}
      <text x={padL} y={h - padB + 14} fontSize="9" className="mono" textAnchor="start" fill="var(--ink-3)">−252d</text>
      <text x={padL + (w - padL - padR) / 2} y={h - padB + 14} fontSize="9" className="mono" textAnchor="middle" fill="var(--ink-3)">−126d</text>
      <text x={w - padR} y={h - padB + 14} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">today</text>
    </svg>
  );
}

// ─── §2 Expected Move ────────────────────────────────────────────────
function ExpectedMove() {
  return (
    <div className="em">
      <div className="em-chart-wrap">
        <div className="em-chart-hdr">
          <span className="label-cap">±1σ / ±2σ Price Cone · 60d horizon · lognormal</span>
          <span className="mono dim2">spot $742 · STOP $624.06 · T1 $1032.30 · T2 $1265.58</span>
        </div>
        <EMCone />
      </div>
      <table className="dtable em-tbl">
        <thead>
          <tr>
            <th>Metric</th><th className="r">IV</th><th className="r">HV30</th>
            <th className="r">Ratio</th><th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="mono">ATM 30-day</td>
            <td className="r mono tabular">48.8%</td>
            <td className="r mono tabular">63.2%</td>
            <td className="r mono tabular up">0.77</td>
            <td><Pill tone="gn" small>long premium</Pill></td>
          </tr>
          <tr><td className="mono">±1σ · 7d</td><td className="r mono tabular">±$50.16</td><td className="r mono tabular" colSpan="3">±6.76%</td></tr>
          <tr><td className="mono">±1σ · 30d</td><td className="r mono tabular">±$103.83</td><td className="r mono tabular" colSpan="3">±13.99%</td></tr>
          <tr><td className="mono">±1σ · 60d</td><td className="r mono tabular">±$146.84</td><td className="r mono tabular" colSpan="3">±19.79%</td></tr>
        </tbody>
      </table>
      <div className="mono dim" style={{ fontSize: 11 }}>
        Verdict: IV under-prices realized → long premium has positive expectancy.
      </div>
    </div>
  );
}

function EMCone() {
  const w = 580, h = 200, padT = 18, padB = 30, padL = 50, padR = 60;
  const spot = 742.18, stop = 624.06, t1 = 1032.30, t2 = 1265.58;
  const yMin = 550, yMax = 1300;
  const x = d => padL + (d / 60) * (w - padL - padR);
  const y = v => padT + (1 - (v - yMin) / (yMax - yMin)) * (h - padT - padB);
  // 1σ and 2σ ranges
  const sig1 = d => Math.sqrt(d / 252) * 0.488 * spot;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="em-1s" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.20" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0.04" />
        </linearGradient>
        <linearGradient id="em-2s" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--violet)" stopOpacity="0.14" />
          <stop offset="100%" stopColor="var(--violet)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* 2σ */}
      <path d={`M ${x(0)} ${y(spot)} L ${[...Array(31)].map((_,i) => [x(i*2), y(spot + 2*sig1(i*2))].join(",")).join(" L ")} L ${x(60)} ${y(spot)} Z`} fill="url(#em-2s)" />
      <path d={`M ${x(0)} ${y(spot)} L ${[...Array(31)].map((_,i) => [x(i*2), y(spot - 2*sig1(i*2))].join(",")).join(" L ")} L ${x(60)} ${y(spot)} Z`} fill="url(#em-2s)" />
      {/* 1σ */}
      <path d={`M ${x(0)} ${y(spot)} L ${[...Array(31)].map((_,i) => [x(i*2), y(spot + sig1(i*2))].join(",")).join(" L ")} L ${x(60)} ${y(spot)} Z`} fill="url(#em-1s)" />
      <path d={`M ${x(0)} ${y(spot)} L ${[...Array(31)].map((_,i) => [x(i*2), y(spot - sig1(i*2))].join(",")).join(" L ")} L ${x(60)} ${y(spot)} Z`} fill="url(#em-1s)" />
      {/* center */}
      <line x1={x(0)} y1={y(spot)} x2={x(60)} y2={y(spot)} stroke="var(--ink-3)" strokeDasharray="3 3" />
      {/* spot, stop, T1, T2 */}
      {[
        { v: spot, l: "$742 spot", c: "var(--copper)" },
        { v: stop, l: "STOP $624.06", c: "var(--rd)" },
        { v: t1,   l: "T1 $1032.30", c: "var(--gn)" },
        { v: t2,   l: "T2 $1265.58", c: "var(--gn)" },
      ].map((m, i) => (
        <g key={i}>
          <line x1={padL} y1={y(m.v)} x2={w - padR} y2={y(m.v)} stroke={m.c} strokeWidth="1" strokeDasharray="2 3" opacity="0.7"
                style={{ filter: `drop-shadow(0 0 3px ${m.c})` }} />
          <text x={w - padR + 4} y={y(m.v) + 3} fontSize="9.5" className="mono" fill={m.c}>{m.l}</text>
        </g>
      ))}
      {/* spot dot */}
      <circle cx={x(0)} cy={y(spot)} r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      {/* x labels */}
      <text x={x(0)} y={h - padB + 14} fontSize="9" className="mono" textAnchor="start" fill="var(--ink-3)">today</text>
      <text x={x(30)} y={h - padB + 14} fontSize="9" className="mono" textAnchor="middle" fill="var(--ink-3)">+30d</text>
      <text x={x(60)} y={h - padB + 14} fontSize="9" className="mono" textAnchor="middle" fill="var(--ink-3)">+60d</text>
      {/* y labels */}
      {[600, 800, 1000, 1200].map(v => (
        <text key={v} x={padL - 6} y={y(v) + 3} fontSize="9" className="mono" textAnchor="end" fill="var(--ink-3)">${v}</text>
      ))}
      {/* legend */}
      <g transform={`translate(${padL + 6}, ${padT + 4})`}>
        <rect x="0" y="0" width="14" height="4" fill="var(--gn)" opacity="0.6" rx="2" />
        <text x="20" y="5" fontSize="9" className="mono" fill="var(--ink-1)">±1σ (68%)</text>
        <rect x="0" y="12" width="14" height="4" fill="var(--violet)" opacity="0.6" rx="2" />
        <text x="20" y="17" fontSize="9" className="mono" fill="var(--ink-1)">±2σ (95%)</text>
      </g>
    </svg>
  );
}

// ─── §3 Flow / Positioning ─────────────────────────────────────────
function FlowPositioning() {
  return (
    <div className="fp">
      <div className="fp-2col">
        <div className="vcp-block">
          <div className="vcp-block-hdr">
            <span className="label-cap">Open Interest · by strike</span>
            <span className="mono dim2">Call OI vs Put OI</span>
          </div>
          <OIByStrike />
        </div>
        <div className="vcp-block">
          <div className="vcp-block-hdr">
            <span className="label-cap">Dealer Gamma Profile</span>
            <span className="mono dim2">long-gamma = calm · short = amplify</span>
          </div>
          <GammaProfile />
        </div>
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="P/C Ratio"        value="1.78"  tone="amb" sub="put-skewed · vol C/P 0k/0k" />
        <KpiTile label="UOA Block Flow"   value="—"     tone="ink" sub="no unusual single-strike vol" />
        <KpiTile label="Net Gamma · Dealers" value="—" tone="ink" sub="no data" />
        <KpiTile label="Max Pain"         value="$750"  tone="copper" sub="+1.1% vs spot · pin strong" />
      </div>
    </div>
  );
}

function OIByStrike() {
  const w = 280, h = 150;
  // synthetic 11 strikes, ATM at index 5
  const strikes = ["−8%","−6%","−4%","−2%","spot","+2%","+4%","+6%","+8%"];
  const callOI = [180, 240, 320, 460, 720, 880, 540, 380, 240];
  const putOI =  [380, 560, 720, 920, 1100, 580, 360, 240, 160];
  const max = Math.max(...callOI, ...putOI);
  const slotW = w / strikes.length;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
      <line x1="0" y1={h/2} x2={w} y2={h/2} stroke="var(--glass-line)" />
      {strikes.map((s, i) => {
        const cx = i * slotW + slotW / 2;
        const cH = (callOI[i] / max) * (h/2 - 6);
        const pH = (putOI[i] / max) * (h/2 - 6);
        const isATM = s === "spot";
        return (
          <g key={i}>
            <rect x={cx - slotW * 0.35} y={h/2 - cH} width={slotW * 0.7} height={cH}
                  fill="var(--gn)" opacity={isATM ? "1" : "0.5"}
                  style={isATM ? { filter: "drop-shadow(0 0 6px var(--gn))" } : null} />
            <rect x={cx - slotW * 0.35} y={h/2} width={slotW * 0.7} height={pH}
                  fill="var(--rd)" opacity={isATM ? "1" : "0.5"}
                  style={isATM ? { filter: "drop-shadow(0 0 6px var(--rd))" } : null} />
            <text x={cx} y={h - 2} fontSize="8.5" className="mono" textAnchor="middle"
                  fill={isATM ? "var(--copper)" : "var(--ink-3)"}>{s}</text>
          </g>
        );
      })}
      <text x={4} y={12} fontSize="9" className="mono" fill="var(--gn)">← CALL OI</text>
      <text x={w - 4} y={h - 16} fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">PUT OI →</text>
    </svg>
  );
}

function GammaProfile() {
  const w = 280, h = 150;
  // gamma flips sign across spot
  const xs = [];
  for (let i = 0; i < 60; i++) {
    const p = -1 + i / 30; // -1 to +1
    const g = Math.exp(-p*p*2) * (p > 0 ? -1 : 1);
    xs.push([i * (w / 60), h/2 - g * (h/2 - 12)]);
  }
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="gp-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.30" />
          <stop offset="50%" stopColor="transparent" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.30" />
        </linearGradient>
      </defs>
      <line x1="0" y1={h/2} x2={w} y2={h/2} stroke="var(--glass-line)" />
      <line x1={w/2} y1="0" x2={w/2} y2={h} stroke="var(--copper)" strokeDasharray="3 3"
            style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
      <path d={`M ${xs.map(p => p.join(",")).join(" L ")}`} stroke="var(--copper)" strokeWidth="2" fill="none"
            style={{ filter: "drop-shadow(0 0 4px var(--copper))" }} />
      <path d={`M ${xs.map(p => p.join(",")).join(" L ")} L ${w} ${h/2} L 0 ${h/2} Z`} fill="url(#gp-fill)" />
      <text x={4} y={12} fontSize="9" className="mono" fill="var(--gn)">Long (calm)</text>
      <text x={w - 4} y={h - 4} fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">Short (amplify)</text>
      <text x={w/2 + 4} y={12} fontSize="9" className="mono" fill="var(--copper)">spot</text>
      <text x={4} y={h/2 - 4} fontSize="9" className="mono" fill="var(--ink-3)">+γ</text>
      <text x={4} y={h/2 + 12} fontSize="9" className="mono" fill="var(--ink-3)">−γ</text>
    </svg>
  );
}

// ─── §3.5 NBBO ──────────────────────────────────────────────────────
function NBBOTable() {
  return (
    <div className="nbbo">
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="Underlying NBBO"  value="$742.11 / $742.25" tone="gn" sub="spread ~2 bp · tight · 1,753 × 3,378" />
        <KpiTile label="ATM Call Spread"  value="$46.33 / $48.22" tone="gn" sub="4.0% mid" />
        <KpiTile label="ATM Put Spread"   value="$41.07 / $42.75" tone="gn" sub="4.0% mid" />
        <KpiTile label="Avg Chain Liquidity" value="B" tone="amb" sub="4.0% avg spread" />
      </div>
      <table className="dtable nbbo-tbl">
        <thead>
          <tr>
            <th>Strike · Type</th><th>Exp</th>
            <th className="r">Bid</th><th className="r">Ask</th><th className="r">Mid</th><th className="r">Theo</th>
            <th className="r">Spread</th><th>Intr / Extr</th><th className="r">Vol · OI</th><th>IV · Δ</th><th>Liq</th>
          </tr>
        </thead>
        <tbody>
          {[
            ["$740 C ATM",     "M · 35d","$46.33","$48.22","$47.27","$46.80","4.0%","$2.18 / $45.09",   "3,194 · 8,484","48.8% · +0.55","A · TIGHT","gn"],
            ["$740 P ATM",     "M · 35d","$41.07","$42.75","$41.91","$41.49","4.0%","$0.00 / $41.91",   "3,194 · 8,484","48.8% · −0.45","A · TIGHT","gn"],
            ["$735 C ITM 1%",  "M · 35d","$48.76","$50.75","$49.75","$49.25","4.0%","$7.18 / $42.57",   "3,137 · 8,333","48.8% · +0.57","A · TIGHT","gn"],
            ["$735 P ITM 1%",  "M · 35d","$38.62","$40.20","$39.41","$39.01","4.0%","$0.00 / $39.41",   "3,137 · 8,333","48.8% · −0.43","A · TIGHT","gn"],
            ["$1030 C T1 OTM", "M · 35d","$0.74", "$0.78", "$0.76", "$0.75", "5.3%","$0.00 / $0.76",    "200 · 500",    "48.8% · +0.02","B · OK","amb"],
            ["$1030 P T1 OTM", "M · 35d","$278.46","$289.83","$284.15","$281.30","4.0%","$287.82 / $−3.67","200 · 500","48.8% · −0.98","A · TIGHT","gn"],
            ["$1265 C T2 OTM", "M · 35d","$0.00", "$0.03", "$0.01", "$0.01", "470%","$0.00 / $0.01",    "200 · 500",    "48.8% · +0.00","C · WIDE","rd"],
            ["$1265 P T2 OTM", "M · 35d","$507.03","$527.73","$517.38","$512.21","4.0%","$522.82 / $−5.44","200 · 500","48.8% · −1.00","A · TIGHT","gn"],
          ].map((r, i) => (
            <tr key={i}>
              <td className="mono"><b>{r[0]}</b></td>
              <td className="mono dim">{r[1]}</td>
              <td className="r mono tabular">{r[2]}</td>
              <td className="r mono tabular">{r[3]}</td>
              <td className="r mono tabular">{r[4]}</td>
              <td className="r mono tabular dim">{r[5]}</td>
              <td className="r mono tabular">{r[6]}</td>
              <td className="mono dim">{r[7]}</td>
              <td className="r mono tabular dim">{r[8]}</td>
              <td className="mono">{r[9]}</td>
              <td><Pill tone={r[11]} small>{r[10]}</Pill></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mono dim" style={{ fontSize: 11 }}>
        Read: Tight ATM spreads (~2–5%) → limit orders fill at mid. Wide OTM spreads (&gt;10%) → slip into worse fills · downgrade strategies that touch wide-spread legs.
      </div>
    </div>
  );
}

// ─── §3.7 Full Chain ────────────────────────────────────────────────
function FullChain() {
  const rows = [
    ["2,959","7,891","48.8%","+0.60","53.88","54.98","56.08","725","33.98","34.68","35.37","−0.40","48.8%","7,891","2,959"],
    ["3,124","8,330","48.8%","+0.58","51.27","52.32","53.37","730","36.26","37.00","37.74","−0.42","48.8%","8,330","3,124"],
    ["3,237","8,633","48.8%","+0.57","48.76","49.75","50.75","735","38.62","39.41","40.20","−0.43","48.8%","8,633","3,237"],
    ["3,294","8,784","48.8%","+0.55","46.33","47.27","48.22","740","41.07","41.91","42.75","−0.45","48.8%","8,784","3,294"],
    ["3,290","8,774","48.8%","+0.53","43.99","44.88","45.78","745","43.61","44.50","45.39","−0.47","48.8%","8,774","3,290"],
    ["3,226","8,603","48.8%","+0.51","41.73","42.58","43.43","750","46.23","47.17","48.11","−0.49","48.8%","8,603","3,226"],
    ["3,105","8,281","48.8%","+0.50","39.56","40.37","41.17","755","48.94","49.93","50.93","−0.50","48.8%","8,281","3,105"],
    ["2,935","7,827","48.8%","+0.48","37.47","38.24","39.00","760","51.73","52.78","53.84","−0.52","48.8%","7,827","2,935"],
  ];
  return (
    <div className="fc">
      <table className="dtable fc-tbl">
        <thead>
          <tr>
            <th colSpan="7" className="fc-side-c">CALLS</th>
            <th>Strike</th>
            <th colSpan="7" className="fc-side-p">PUTS</th>
          </tr>
          <tr>
            <th>Vol</th><th>OI</th><th>IV</th><th>Δ</th>
            <th className="r">Bid</th><th className="r">Mid</th><th className="r">Ask</th>
            <th></th>
            <th className="r">Bid</th><th className="r">Mid</th><th className="r">Ask</th>
            <th>Δ</th><th>IV</th><th>OI</th><th>Vol</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isATM = r[7] === "740";
            return (
              <tr key={i} className={isATM ? "is-current" : ""}>
                <td className="mono dim">{r[0]}</td>
                <td className="mono dim">{r[1]}</td>
                <td className="mono">{r[2]}</td>
                <td className="mono up">{r[3]}</td>
                <td className="r mono tabular">{r[4]}</td>
                <td className="r mono tabular">{r[5]}</td>
                <td className="r mono tabular">{r[6]}</td>
                <td className="mono fc-strike"><b>${r[7]}</b></td>
                <td className="r mono tabular">{r[8]}</td>
                <td className="r mono tabular">{r[9]}</td>
                <td className="r mono tabular">{r[10]}</td>
                <td className="mono dn">{r[11]}</td>
                <td className="mono">{r[12]}</td>
                <td className="mono dim">{r[13]}</td>
                <td className="mono dim">{r[14]}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mono dim" style={{ fontSize: 11 }}>
        Reading: ITM cells tinted (intrinsic backs premium) · OTM dim. Tags: ATM at-the-money · T1/T2 plan targets · STOP invalidation strike.
      </div>
    </div>
  );
}

// ─── §4 Strategy Matrix ─────────────────────────────────────────────
function StrategyTable() {
  return (
    <div>
      <table className="dtable">
        <thead>
          <tr>
            <th>Strategy · DTE</th><th>Strikes</th>
            <th className="r">Cost</th><th className="r">Max P</th><th className="r">Max L</th>
            <th className="r">Breakeven</th><th className="r">POP</th>
            <th className="r">Δ</th><th className="r">Θ/d</th><th className="r">ν</th>
          </tr>
        </thead>
        <tbody>
          <tr className="is-current">
            <td className="mono">
              <b>Bear Put Spread · 35 DTE</b>
              <div className="mono dim2" style={{ fontSize: 10, marginTop: 2 }}>
                mid IV + bearish — defined risk, short leg at support
              </div>
            </td>
            <td className="mono">+740P/−625P</td>
            <td className="r mono tabular copper">+$3,574 <span className="dim">debit</span></td>
            <td className="r mono tabular up">$7,926</td>
            <td className="r mono tabular dn">$3,574</td>
            <td className="r mono tabular">$704.26</td>
            <td className="r mono tabular">35%</td>
            <td className="r mono tabular dn">−0.34</td>
            <td className="r mono tabular dn">−$30.3</td>
            <td className="r mono tabular up">+48.6</td>
          </tr>
        </tbody>
      </table>
      <div className="mono dim" style={{ fontSize: 10.5, marginTop: 8 }}>
        Black-Scholes priced at ATM σ=48.8%, r=4.5%. Strikes auto-selected from spot + Plan T1/T2 · DTE matched to hold window (35d swing).
        Live quotes via Schwab chain (when wired) — model price ± true mid.
      </div>
    </div>
  );
}

// ─── §4.5 Profit Grid ────────────────────────────────────────────────
function ProfitGrid() {
  const prices = [770,768,766,764,762,760,758,756,754,752,750,748,746,744,742,740,738,736,734,732,730,728,726];
  const days = ["Today","+5d","+10d","+15d","+20d","+25d","+30d","EXPIRY"];
  const dateLabels = ["May 28","Jun 02","Jun 07","Jun 12","Jun 17","Jun 22","Jun 27","Jul 02"];
  const spot = 742;
  const breakeven = 787;
  // Linear interp from reference table
  const grid = [
    [35,28,20,11,2,-9,-22,-36],
    [33,25,17,9,-1,-12,-26,-40],
    [30,23,15,6,-4,-15,-29,-45],
    [27,20,12,3,-7,-18,-32,-49],
    [25,17,9,0,-9,-21,-35,-53],
    [22,15,7,-2,-12,-24,-38,-57],
    [20,12,4,-5,-15,-26,-41,-62],
    [17,10,1,-7,-17,-29,-44,-66],
    [14,7,-1,-10,-20,-32,-46,-70],
    [12,5,-4,-12,-22,-34,-49,-74],
    [10,2,-6,-15,-25,-37,-52,-78],
    [7,0,-8,-17,-27,-39,-54,-83],
    [5,-3,-11,-20,-30,-42,-57,-87],
    [2,-5,-13,-22,-32,-44,-59,-91],
    [0,-7,-15,-24,-34,-46,-61,-95],
    [-2,-10,-18,-27,-37,-48,-64,-100],
    [-5,-12,-20,-29,-39,-51,-66,-100],
    [-7,-14,-22,-31,-41,-53,-68,-100],
    [-9,-16,-24,-33,-43,-55,-70,-100],
    [-11,-19,-27,-35,-45,-57,-72,-100],
    [-13,-21,-29,-37,-47,-59,-74,-100],
    [-16,-23,-31,-39,-49,-61,-75,-100],
    [-18,-25,-33,-41,-51,-63,-77,-100],
  ];
  const cellColor = v => {
    if (v >= 25) return { bg: `rgba(74,222,128,${0.18 + Math.min(0.35, v / 120)})`, color: "#dffce6" };
    if (v >= 10) return { bg: `rgba(74,222,128,${0.10 + v / 200})`, color: "#cfeed8" };
    if (v >= 0)  return { bg: `rgba(74,222,128,0.06)`, color: "#b8d8c1" };
    if (v >= -25) return { bg: `rgba(248,113,113,${0.06 + Math.abs(v) / 150})`, color: "#e8c4c4" };
    if (v >= -50) return { bg: `rgba(248,113,113,${0.16 + Math.abs(v) / 200})`, color: "#f1c8c8" };
    return { bg: `rgba(248,113,113,${0.30 + Math.abs(v) / 220})`, color: "#fde4e4" };
  };
  return (
    <div className="pg">
      <div className="pg-hdr">
        <div className="pg-hdr-block">
          <div className="label-cap">LONG $740 CALL · 35 DTE</div>
        </div>
        <div className="pg-hdr-kpis">
          <span className="mono"><span className="label-cap">Entry Cost</span> <b>$4,727</b></span>
          <span className="mono"><span className="label-cap">Max Risk</span> <b className="dn">−$4,727</b></span>
          <span className="mono"><span className="label-cap">Max Return</span> <b className="up">∞</b></span>
          <span className="mono"><span className="label-cap">Breakeven</span> <b className="warn">$787.27</b></span>
          <span className="mono"><span className="label-cap">Prob. Profit</span> <b>33.1%</b></span>
          <span className="mono"><span className="label-cap">Spot</span> <b className="copper">$742.18</b></span>
          <span className="mono dim2">σ 49% · r 4.5%</span>
        </div>
      </div>
      <div className="pg-tbl-wrap">
        <table className="pg-tbl mono">
          <thead>
            <tr>
              <th>Price ▼</th>
              {days.map((d, i) => (
                <th key={i}>
                  <div>{d}</div>
                  <div className="dim2" style={{ fontSize: 9, marginTop: 1 }}>{dateLabels[i]}</div>
                </th>
              ))}
              <th>±% spot</th>
            </tr>
          </thead>
          <tbody>
            {prices.map((p, ri) => {
              const isSpot = p === spot;
              const isStrike = p === 740;
              const isBE = p === breakeven || Math.abs(p - breakeven) < 1;
              const pct = ((p / spot - 1) * 100).toFixed(1);
              return (
                <tr key={p} className={isSpot ? "pg-row-spot" : isStrike ? "pg-row-strike" : isBE ? "pg-row-be" : ""}>
                  <td className="pg-px">
                    ${p}{isStrike && <span className="pg-tag"> K</span>}
                  </td>
                  {grid[ri].map((v, ci) => {
                    const c = cellColor(v);
                    return (
                      <td key={ci} className="pg-cell" style={{ background: c.bg, color: c.color }}>
                        {v > 0 ? "+" : ""}{v}
                      </td>
                    );
                  })}
                  <td className="pg-pct">{isSpot ? "spot" : (Number(pct) > 0 ? "+" : "") + pct + "%"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mono dim" style={{ fontSize: 11 }}>
        Reading: Each cell shows position's % return if closed at that (price, date).
        Bright green top-right = deep ITM near expiry. Deep red bottom = total premium loss.
        Spot row copper-outlined · break-even row amber. Black-Scholes re-priced every cell.
      </div>
    </div>
  );
}

// ─── §6 Scenario P&L ────────────────────────────────────────────────
function ScenarioPL() {
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Vehicle</th><th>Position</th>
          <th className="r">Stop $624.06<div className="mono dim2" style={{ fontSize: 9 }}>−15.9%</div></th>
          <th className="r">Entry $742.18<div className="mono dim2" style={{ fontSize: 9 }}>0.0%</div></th>
          <th className="r">T1 $1,032.30<div className="mono dim2" style={{ fontSize: 9 }}>+39.1%</div></th>
          <th className="r">T2 $1,265.58<div className="mono dim2" style={{ fontSize: 9 }}>+70.5%</div></th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td className="mono">Long 100 Shares</td>
          <td className="mono dim">$74,218 cap</td>
          <td className="r mono tabular dn">−$11,812</td>
          <td className="r mono tabular dim">+$0</td>
          <td className="r mono tabular up">+$29,012</td>
          <td className="r mono tabular up">+$52,340</td>
        </tr>
        <tr className="is-current">
          <td className="mono"><b>Bear Put Spread</b></td>
          <td className="mono dim">debit $3,574</td>
          <td className="r mono tabular up">+$7,926</td>
          <td className="r mono tabular dn">−$3,574</td>
          <td className="r mono tabular dn">−$3,574</td>
          <td className="r mono tabular dn">−$3,574</td>
        </tr>
      </tbody>
    </table>
  );
}

// ─── §8 Management Triggers ─────────────────────────────────────────
function MgmtTriggers() {
  return (
    <table className="dtable">
      <thead>
        <tr><th>Strategy</th><th>Take Profit</th><th>Time Stop</th><th>Loss Stop</th></tr>
      </thead>
      <tbody>
        <tr>
          <td className="mono">
            <b>Bear Put Spread</b>
            <div className="mono dim2" style={{ fontSize: 10, marginTop: 2 }}>long premium</div>
          </td>
          <td className="mono">Sell ½ at <b className="up">+100% gain</b> · trail rest</td>
          <td className="mono">21 DTE close if no thesis confirmation <span className="dim">(avoid gamma curse)</span></td>
          <td className="mono"><b className="dn">−50% debit</b> · cut at −$1,787</td>
        </tr>
      </tbody>
    </table>
  );
}

// Replace the old LensOptions export
window.LensOptions = LensOptions;
