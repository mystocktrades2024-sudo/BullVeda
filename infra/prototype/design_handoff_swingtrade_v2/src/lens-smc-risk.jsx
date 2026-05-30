// lens-smc.jsx + lens-risk.jsx — Smart Money Concepts and Risk lenses

const { useMemo: useMemoSR } = React;

// ────────────────────────────────────────────────────────────
// SMC — order blocks, FVG, BoS/CHoCH, liquidity sweeps
// ────────────────────────────────────────────────────────────
function LensSMC({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("sm-1"); const s2 = useStateToggle("sm-2");
  const s3 = useStateToggle("sm-3"); const s4 = useStateToggle("sm-4");
  const s0 = useStateToggle("sm-0"); const s5 = useStateToggle("sm-5");
  const s6b = useStateToggle("sm-6"); const s7b = useStateToggle("sm-7");
  const s8b = useStateToggle("sm-8"); const s9b = useStateToggle("sm-9");
  const s10b = useStateToggle("sm-10");
  const s11b = useStateToggle("sm-11"); const s12b = useStateToggle("sm-12");
  const s13b = useStateToggle("sm-13"); const s14b = useStateToggle("sm-14");

  return (
    <div className="lens lens--smc">
      {window.LensSummaryBar && <LensSummaryBar ticker={ticker} mode={mode} kind="smc" />}
      <div className="hero smc-hero">
        <div className="th-left">
          <div className="label-cap">SMC structure read · {mode}</div>
          <div className="th-score">
            <div className="th-score-num mono">PASS</div>
            <Pill tone="cy" dot>BoS + OB held</Pill>
            <Pill tone="gn" small>HTF bull</Pill>
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
        <SectionHeader title="Cross-Discipline Confluence"
          sub="how SMC lines up with the other theories on this name" style="minimal" />
        <div className="lens-pad">
          <CrossLens lead="cy" cells={[
            { lens: "SMC", verdict: "BULL BOS", tone: "gn", note: "OB held · liquidity above $70.40" },
            { lens: "Wyckoff", verdict: "PHASE D", tone: "gn", note: "spring + SOS · accumulating" },
            { lens: "Elliott", verdict: "WAVE 3", tone: "gn", note: "impulse · 1.618 ext target" },
            { lens: "Volume Profile", verdict: "ABOVE VAH", tone: "gn", note: "value migrating up · POC support" },
            { lens: "Verdict", verdict: "STACKED", tone: "gn", note: "structure + flow + value aligned" },
          ]} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={0} title="Macro · Higher-Timeframe Context"
          sub="draw on liquidity · HTF bias · premium/discount · daily/weekly levels"
          style={headerStyle} right={<StateToggle name="sm-0" />} />
        <StateWrap state={s0.value} source="MTF structure · D/W/M levels · session liquidity">
          <div className="lens-pad"><SMCMacro /></div>
        </StateWrap>
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
        <SectionHeader n={3} title="Liquidity Sweeps · Pools"
          sub="stop-hunts above prior highs / below prior lows · resting liquidity"
          style={headerStyle} right={<StateToggle name="sm-3" />} />
        <StateWrap state={s3.value} source="sweep detector · 30 sessions">
          <div className="lens-pad"><LiquiditySweeps /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Premium / Discount · Equilibrium"
          sub="dealing-range zones · where to buy vs sell"
          style={headerStyle} right={<StateToggle name="sm-5" />} />
        <StateWrap state={s5.value} source="dealing range · trailing extremes">
          <div className="lens-pad"><SMCZones /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="MTF Screener"
          sub="confluence across 1H · 4H · D · W"
          style={headerStyle} right={<StateToggle name="sm-4" />} />
        <StateWrap state={s4.value} source="MTF aggregator · 1H/4H/D/W structure">
          <div className="lens-pad"><MTFScreener /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Inducement · Liquidity Engineering"
          sub="the trap before the move · minor liquidity swept first"
          style={headerStyle} right={<StateToggle name="sm-6" />} />
        <StateWrap state={s6b.value} source="inducement detector · sub-pivot sweeps">
          <div className="lens-pad"><SMCInducement /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Breaker · Mitigation Blocks"
          sub="failed OBs that flip polarity · revisited origins"
          style={headerStyle} right={<StateToggle name="sm-7" />} />
        <StateWrap state={s7b.value} source="polarity-flip detector">
          <div className="lens-pad"><SMCBreakers /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Liquidity Voids · Displacement · OTE"
          sub="inefficiencies · momentum leg · optimal trade entry 62–79%"
          style={headerStyle} right={<StateToggle name="sm-8" />} />
        <StateWrap state={s8b.value} source="displacement + fib OTE engine">
          <div className="lens-pad"><SMCVoidOTE /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={9} title="Kill Zones · SMT Divergence"
          sub="session timing edge · correlated-pair divergence"
          style={headerStyle} right={<StateToggle name="sm-9" />} />
        <StateWrap state={s9b.value} source="session clock + SMT vs sector ETF">
          <div className="lens-pad"><SMCKillSMT /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={10} title="Entry Model · Confluence Grade"
          sub="sweep → CHoCH → FVG → OB · step tracker + A–F grade"
          style={headerStyle} right={<StateToggle name="sm-10" />} />
        <StateWrap state={s10b.value} source="entry-model state machine">
          <div className="lens-pad"><SMCEntryModel /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={11} title="Trend-State Machine"
          sub="persistent CHoCH/BoS regime across timeframes"
          style={headerStyle} right={<StateToggle name="sm-11" />} />
        <StateWrap state={s11b.value} source="structure state machine">
          <div className="lens-pad"><SMCTrendState /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={12} title="Confluence Stacking · A+ Zones"
          sub="OB + FVG + OTE + HTF level + liquidity aligned"
          style={headerStyle} right={<StateToggle name="sm-12" />} />
        <StateWrap state={s12b.value} source="confluence scorer">
          <div className="lens-pad"><SMCConfluence /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={13} title="Mitigation Hit-Rate · Liquidity Heatmap"
          sub="zone respect history + resting liquidity density"
          style={headerStyle} right={<StateToggle name="sm-13" />} />
        <StateWrap state={s13b.value} source="zone tracker + liquidity density">
          <div className="lens-pad"><SMCMitigationHeat /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={14} title="SMC Alerts"
          sub="price-entering-OB · FVG fill · liquidity sweep triggers"
          style={headerStyle} right={<StateToggle name="sm-14" />} />
        <StateWrap state={s14b.value} source="alert engine · SMC conditions">
          <div className="lens-pad"><SMCAlerts /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="cy" cells={[
            { lens: "SMC",        verdict: "PASS",  tone: "gn",  note: "BoS + OB held · liquidity above" },
            { lens: "Macro",      verdict: "BULL",  tone: "gn",  note: "HTF D/W aligned · risk-on" },
            { lens: "Technicals", verdict: "PASS",  tone: "gn",  note: "RSI 64 · stacked MAs" },
            { lens: "Volume",     verdict: "DRY",   tone: "amb", note: "below avg on pullback" },
            { lens: "Risk",       verdict: "OK",    tone: "gn",  note: "stop below last OB" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · SMC</span>
        <span className="mono">
          HTF bullish + price in discount · OB at <b className="copper">$63.20–$63.80</b> held the spring ·
          draw on liquidity rests above <b className="up">$70.40</b>. Long from discount toward buy-side liquidity.
        </span>
      </div>
    </div>
  );
}

// Macro / HTF context for SMC
function SMCMacro() {
  return (
    <div className="smc-macro">
      <div className="smc-macro-grid">
        <div className="smc-mc smc-mc--gn">
          <div className="label-cap">HTF BIAS · D / W / M</div>
          <div className="mono smc-mc-v up">BULLISH</div>
          <div className="mono dim2">Daily BoS↑ · Weekly HH/HL · Monthly up</div>
        </div>
        <div className="smc-mc smc-mc--cy">
          <div className="label-cap">DRAW ON LIQUIDITY</div>
          <div className="mono smc-mc-v cy">$70.40 ↑</div>
          <div className="mono dim2">buy-side · equal highs magnet</div>
        </div>
        <div className="smc-mc smc-mc--gn">
          <div className="label-cap">DEALING RANGE</div>
          <div className="mono smc-mc-v">DISCOUNT</div>
          <div className="mono dim2">price below 50% equilibrium $66.25</div>
        </div>
        <div className="smc-mc smc-mc--amb">
          <div className="label-cap">SESSION</div>
          <div className="mono smc-mc-v warn">NY AM</div>
          <div className="mono dim2">London high swept · NY continuation</div>
        </div>
      </div>
      <table className="dtable">
        <thead><tr><th>HTF Level</th><th className="r">Price</th><th>Type</th><th>Status</th></tr></thead>
        <tbody>
          {[
            ["PWH · prior week high","$70.40","buy-side liq","untapped","cy"],
            ["PDH · prior day high","$68.10","buy-side liq","untapped","cy"],
            ["Daily OB","$63.20–63.80","HTF demand","holding","gn"],
            ["Weekly FVG","$61.10–62.40","HTF imbalance","unfilled","violet"],
            ["PWL · prior week low","$58.40","sell-side liq","swept","rd"],
            ["Monthly 50%","$56.20","equilibrium","below","ink"],
          ].map((r,i)=>(
            <tr key={i}>
              <td className="mono">{r[0]}</td>
              <td className="r mono">{r[1]}</td>
              <td className="mono dim">{r[2]}</td>
              <td><Pill tone={r[4]} small>{r[3]}</Pill></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mono dim" style={{fontSize:11}}>
        Macro read: HTF bullish with price in <b className="up">discount</b> below equilibrium — institutional
        accumulation zone. Draw on liquidity is buy-side ($70.40 equal highs). Long bias from discount OB toward the magnet.
      </div>
    </div>
  );
}

// Premium / Discount / Equilibrium zones
function SMCZones() {
  const hi=70.40, lo=58.40, eq=(hi+lo)/2, spot=67.42;
  const q75=lo+(hi-lo)*0.75, q25=lo+(hi-lo)*0.25;
  const obTop=63.80, obBot=63.20;
  const W=520, H=240, padT=18, padB=18, axisX=150, barX=176, barW=120;
  const y=p=> padT + (1-(p-lo)/(hi-lo))*(H-padT-padB);
  const pct=((spot-lo)/(hi-lo)*100);
  return (
    <div className="smc-zones2">
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="smc-zsvg">
        <defs>
          <linearGradient id="smc-prem" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.30"/><stop offset="100%" stopColor="var(--rd)" stopOpacity="0.06"/></linearGradient>
          <linearGradient id="smc-disc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.06"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0.30"/></linearGradient>
        </defs>
        {/* zone fills */}
        <rect x={barX} y={y(hi)} width={barW} height={y(eq)-y(hi)} fill="url(#smc-prem)"/>
        <rect x={barX} y={y(eq)} width={barW} height={y(lo)-y(eq)} fill="url(#smc-disc)"/>
        {/* equilibrium band */}
        <rect x={barX} y={y(eq)-1} width={barW} height="2" fill="var(--amb)"/>
        {/* OB band inside */}
        <rect x={barX} y={y(obTop)} width={barW} height={Math.max(3,y(obBot)-y(obTop))} fill="var(--cy)" opacity="0.4"/>
        <rect x={barX} y={y(hi)} width={barW} height={y(lo)-y(hi)} fill="none" stroke="var(--glass-line)"/>
        {/* level ticks + labels (left) */}
        {[["PWH · buy-side liq",hi,"var(--cy)"],["75% premium",q75,"var(--ink-3)"],["EQ 50% · fair value",eq,"var(--amb)"],["25% discount",q25,"var(--ink-3)"],["PWL · swept",lo,"var(--rd)"]].map((r,i)=>(
          <g key={i}>
            <line x1={axisX} y1={y(r[1])} x2={barX} y2={y(r[1])} stroke={r[2]} strokeWidth="1" opacity="0.5"/>
            <text x={axisX-6} y={y(r[1])+3} fontSize="9.5" className="mono" textAnchor="end" fill={r[2]}>{r[0]}</text>
            <text x={barX+barW+6} y={y(r[1])+3} fontSize="9.5" className="mono" fill={r[2]}>${r[1].toFixed(2)}</text>
          </g>
        ))}
        {/* OB label */}
        <text x={barX+barW/2} y={y((obTop+obBot)/2)+3} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--cy)">OB $63.2–63.8</text>
        {/* zone captions */}
        <text x={barX+8} y={y((hi+eq)/2)} fontSize="10" className="mono" fill="var(--rd)" opacity="0.7" transform={`rotate(-90 ${barX+8} ${y((hi+eq)/2)})`}>PREMIUM · sell</text>
        <text x={barX+8} y={y((eq+lo)/2)} fontSize="10" className="mono" fill="var(--gn)" opacity="0.7" transform={`rotate(-90 ${barX+8} ${y((eq+lo)/2)})`}>DISCOUNT · buy</text>
        {/* spot marker */}
        <line x1={barX-6} y1={y(spot)} x2={barX+barW+6} y2={y(spot)} stroke="var(--copper)" strokeWidth="2" style={{filter:"drop-shadow(0 0 4px var(--copper))"}}/>
        <circle cx={barX+barW} cy={y(spot)} r="4" fill="var(--copper)" style={{filter:"drop-shadow(0 0 6px var(--copper))"}}/>
        <rect x={barX+barW+34} y={y(spot)-9} width="74" height="18" rx="9" fill="color-mix(in oklab,var(--copper) 18%,transparent)" stroke="var(--copper)" strokeWidth="0.8"/>
        <text x={barX+barW+71} y={y(spot)+3} fontSize="9" className="mono" textAnchor="middle" fill="var(--copper)">SPOT ${spot.toFixed(2)}</text>
      </svg>
      <div className="smc-zone-read">
        <div className="kpi-row" style={{gridTemplateColumns:"repeat(3,1fr)"}}>
          <KpiTile label="Dealing range" value={`$${lo.toFixed(0)}–$${hi.toFixed(0)}`} tone="ink" sub="swing low → high" />
          <KpiTile label="Equilibrium" value={`$${eq.toFixed(2)}`} tone="amb" sub="50% · fair value" />
          <KpiTile label="Current zone" value={pct<50?"DISCOUNT":"PREMIUM"} tone={pct<50?"gn":"rd"} sub={`${pct.toFixed(0)}% of range`} />
        </div>
        <div className="mono dim" style={{fontSize:11,marginTop:8}}>
          Price sits at <b>{pct.toFixed(0)}%</b> of range — marginal premium. Ideal SMC longs fill in discount (&lt;50%);
          favor a pullback into the <b className="cy">$63–64 OB</b> rather than chasing here.
        </div>
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
            <td><span className={`ob-mit ob-mit--${r.state === "Unmitigated" ? "fresh" : r.state === "Held" ? "tapped" : "spent"}`}><span className="ob-mit-dot" />{r.state === "Unmitigated" ? "Fresh" : r.state === "Held" ? "Tapped · held" : "Mitigated · spent"}</span></td>
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
          <div className="lens-pad"><RiskCones ticker={ticker} mode={mode} /></div>
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
          <div className="lens-pad"><VarTable ticker={ticker} mode={mode} /></div>
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
    <svg viewBox="0 0 280 110" width="280" height="110" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="lc-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="lc-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="20" y1="55" x2="270" y2="55" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 55 Q 130 14 270 14 L 270 55 Z" fill="url(#lc-gn)" />
      <path d="M 20 55 Q 130 96 270 96 L 270 55 Z" fill="url(#lc-rd)" />
      <path d="M 20 55 Q 130 30 270 30"  stroke="var(--gn)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
      <path d="M 20 55 Q 130 78 270 78"  stroke="var(--rd)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 5px var(--rd))" }} />
      <path d="M 20 55 Q 130 14 270 14"  stroke="var(--gn)" strokeWidth="1.1" fill="none" opacity="0.5" />
      <path d="M 20 55 Q 130 96 270 96"  stroke="var(--rd)" strokeWidth="1.1" fill="none" opacity="0.5" />
      <circle cx="20" cy="55" r="4" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x="266" y="11" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">+3σ +6.4%</text>
      <text x="266" y="27" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">+1σ +2.1%</text>
      <text x="266" y="82" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">−1σ −2.1%</text>
      <text x="266" y="106" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">−3σ −6.4%</text>
    </svg>
  );
}

function RiskCones({ ticker, mode }) {
  const px = (ticker && ticker.price) || 67.42;
  const dvol = 0.021;                                   // 1d 1σ
  const hd = mode === "POSITION" ? 10 : mode === "INVESTMENT" ? 21 : 1;
  const lbl = hd === 1 ? "1d" : hd + "d";
  const s1 = dvol * Math.sqrt(hd);
  const band = (k) => `$${(px * (1 - s1 * k)).toFixed(2)} — $${(px * (1 + s1 * k)).toFixed(2)}`;
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      <KpiTile label={`${lbl} · 1σ`} value={`±${(s1 * 100).toFixed(1)}%`} tone="ink" sub={band(1)} />
      <KpiTile label={`${lbl} · 2σ`} value={`±${(s1 * 200).toFixed(1)}%`} tone="amb" sub={band(2)} />
      <KpiTile label={`${lbl} · 3σ`} value={`±${(s1 * 300).toFixed(1)}%`} tone="rd" sub={band(3)} />
      <KpiTile label={`${hd === 1 ? "10d" : (hd * 2) + "d"} · 1σ`} value={`±${(dvol * Math.sqrt(hd === 1 ? 10 : hd * 2) * 100).toFixed(1)}%`} tone="amb" sub={band(1)} />
    </div>
  );
}

function VarTable({ ticker, mode }) {
  const hd = mode === "POSITION" ? 10 : mode === "INVESTMENT" ? 21 : 1;
  const lbl = hd === 1 ? "1d" : hd + "d";
  const dvol = 0.021;                                  // 1-day 1σ
  const sig = dvol * Math.sqrt(hd);
  const inv = 7416;                                    // demo book notional for the position
  const var95 = +(sig * 1.645 * 100).toFixed(1);
  const cvar = +(sig * 2.06 * 100).toFixed(1);
  const var2x = +(dvol * Math.sqrt(hd === 1 ? 10 : hd * 2) * 1.645 * 100).toFixed(1);
  const rows = [
    { metric: `VaR · ${lbl} · 95%`,  v: `−${var95}%`, abs: `−$${Math.round(var95/100*inv)} (110 sh)`, tone: var95 > 5 ? "rd" : "amb" },
    { metric: `CVaR · ${lbl} · 95%`, v: `−${cvar}%`, abs: `−$${Math.round(cvar/100*inv)} (tail avg)`, tone: "rd" },
    { metric: `VaR · ${hd === 1 ? "10d" : (hd*2)+"d"} · 95%`, v: `−${var2x}%`, abs: `−$${Math.round(var2x/100*inv)}`, tone: "rd" },
    { metric: "Sharpe contrib", v: "+0.04", abs: "on book", tone: "gn" },
    { metric: "Sortino contrib", v: "+0.07", abs: "on book", tone: "gn" },
    { metric: "Max DD if stop hits", v: "−5.9%", abs: "−$420 · 0.39% NAV", tone: "rd" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Metric · {mode} horizon</th><th className="r">Value</th><th>Absolute</th></tr></thead>
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

// Trend-state machine across timeframes
function SMCTrendState() {
  const rows=[
    ["1H","BULLISH","BoS ↑","2 bars ago","gn"],
    ["4H","BULLISH","CHoCH→BoS","6 bars ago","gn"],
    ["1D","BULLISH","BoS ↑","3 sessions","gn"],
    ["1W","NEUTRAL","range","no break","amb"],
  ];
  return (
    <div className="smc-sub">
      <div className="smc-ts-strip">
        {rows.map((r,i)=>(
          <div key={i} className={`smc-ts smc-ts--${r[4]}`}>
            <span className="mono smc-ts-tf">{r[0]}</span>
            <span className={`mono smc-ts-bias kpi-tone--${r[4]==="gn"?"gn":"amb"}`}>{r[1]}</span>
            <span className="mono dim2">{r[2]} · {r[3]}</span>
          </div>
        ))}
      </div>
      <div className="mono dim" style={{fontSize:11}}>Aligned bullish 1H→1D; weekly still ranging. State machine flips to bearish only on a 4H CHoCH below $63.20. Current regime: <b className="up">BULLISH (3 of 4 TF)</b>.</div>
    </div>
  );
}

// Confluence stacking — A+ zones where multiple SMC factors align
function SMCConfluence() {
  const zones=[
    { px:"$63.9–64.6", factors:["OB+","FVG","OTE 70.5%","HTF demand","unswept liq"], grade:"A+", tone:"gn" },
    { px:"$66.1–66.6", factors:["OB+","pivot floor"], grade:"B", tone:"amb" },
    { px:"$70.0–70.8", factors:["OB−","buy-side liq","premium"], grade:"C", tone:"rd" },
  ];
  return (
    <div className="smc-sub">
      {zones.map((z,i)=>(
        <div key={i} className={`smc-conf smc-conf--${z.tone}`}>
          <div className="smc-conf-grade">{z.grade}</div>
          <div className="smc-conf-body">
            <div className="mono smc-conf-px"><b>{z.px}</b> <span className="dim2">· {z.factors.length} factors</span></div>
            <div className="smc-conf-tags">{z.factors.map((f,j)=><span key={j} className="smc-conf-tag mono">{f}</span>)}</div>
          </div>
        </div>
      ))}
      <div className="mono dim" style={{fontSize:11}}>The $63.9–64.6 zone stacks 5 factors (OB+ · FVG · OTE · HTF demand · unswept liquidity) → <b className="up">A+ entry</b>. Highest-probability long if price retraces there.</div>
    </div>
  );
}

// Mitigation hit-rate + liquidity heatmap
function SMCMitigationHeat() {
  return (
    <div className="smc-2col">
      <div>
        <div className="label-cap" style={{marginBottom:6}}>ZONE RESPECT · last 90d</div>
        <table className="dtable">
          <thead><tr><th>Zone type</th><th className="r">Tested</th><th className="r">Respected</th><th className="r">Rate</th></tr></thead>
          <tbody>
            {[["Bullish OB",14,11,"79%","gn"],["Bearish OB",9,6,"67%","amb"],["FVG fill",22,15,"68%","amb"],["Liq sweep→rev",8,7,"88%","gn"]].map((r,i)=>(
              <tr key={i}><td className="mono">{r[0]}</td><td className="r mono">{r[1]}</td><td className="r mono">{r[2]}</td><td className={`r mono kpi-tone--${r[4]}`}>{r[3]}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <div className="label-cap" style={{marginBottom:6}}>RESTING LIQUIDITY · density</div>
        <div className="smc-heat">
          {[["$70.40",90,"buy","cy"],["$68.10",55,"buy","cy"],["$67.42",10,"spot","ink"],["$64.30",35,"sell","rd"],["$62.10",70,"sell","rd"],["$58.40",80,"sell","rd"]].map((r,i)=>(
            <div key={i} className="smc-heat-row">
              <span className="mono smc-heat-px">{r[0]}</span>
              <div className="smc-heat-bar"><div className={`smc-heat-fill smc-heat--${r[3]}`} style={{width:`${r[1]}%`}}/></div>
              <span className="mono dim2">{r[2]}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// SMC alerts
function SMCAlerts() {
  const alerts=[
    ["price entering OB $63.2–63.8","armed","gn"],
    ["FVG fill $64.3–64.9","armed","cy"],
    ["liquidity sweep < $58.40","armed","amb"],
    ["4H CHoCH < $63.20 (invalidation)","armed","rd"],
    ["buy-side liq tap $70.40","armed","cy"],
  ];
  return (
    <div className="smc-sub">
      <div className="smc-alert-list">
        {alerts.map((a,i)=>(
          <div key={i} className={`smc-alert smc-alert--${a[2]}`}>
            <span className="smc-alert-dot"/>
            <span className="mono smc-alert-txt">{a[0]}</span>
            <span className="mono dim2">{a[1]}</span>
            <button className="btn btn--sm">🔔</button>
          </div>
        ))}
      </div>
      <div className="mono dim" style={{fontSize:11}}>5 conditions armed · fires to Alerts surface + push. Mirrors the LuxAlgo alertcondition set (OB breakout, FVG, sweep, CHoCH).</div>
    </div>
  );
}

// ── New SMC building-block components ──
// Annotated structure map: where OB+ (demand), OB− (supply), FVG sit vs price
function SMCStructureMap() {
  const W=900,H=340,padT=20,padB=26,padL=14,padR=150;
  const lo=60, hi=72, y=p=>padT+(1-(p-lo)/(hi-lo))*(H-padT-padB);
  const zones=[
    { top:70.8, bot:70.0, type:"OB−", tone:"rd", note:"supply · unmitigated" },
    { top:67.8, bot:67.4, type:"FVG", tone:"violet", note:"bullish imbalance" },
    { top:66.6, bot:66.1, type:"OB+", tone:"gn", note:"demand · pivot floor" },
    { top:64.3, bot:63.9, type:"FVG", tone:"violet", note:"unfilled gap" },
    { top:63.8, bot:63.2, type:"OB+", tone:"gn", note:"demand · spring held" },
    { top:62.4, bot:61.1, type:"FVG", tone:"violet", note:"weekly imbalance" },
  ];
  const spot=67.42;
  // synth candles trending down into demand then reversing up
  const cl=[67.0,68.4,69.2,68.1,66.4,64.9,63.6,63.9,64.8,65.6,66.2,65.4,66.1,66.9,67.42];
  const candles=cl.map((c,i)=>{ const o=i===0?66.6:cl[i-1]; const hi2=Math.max(o,c)+0.3; const lo2=Math.min(o,c)-0.3; return {o,c,hi:hi2,lo:lo2}; });
  const cw=(W-padL-padR)/candles.length;
  const cx=i=>padL+i*cw+cw/2;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="smc-map-svg">
      <defs>
        <linearGradient id="smc-obp" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.28"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0.08"/></linearGradient>
        <linearGradient id="smc-obm" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.28"/><stop offset="100%" stopColor="var(--rd)" stopOpacity="0.08"/></linearGradient>
        <linearGradient id="smc-fvg" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--violet)" stopOpacity="0.20"/><stop offset="100%" stopColor="var(--violet)" stopOpacity="0.05"/></linearGradient>
      </defs>
      {/* zones with right-edge label tabs (spaced to avoid overlap) */}
      {zones.map((z,i)=>{
        const fill = z.type==="OB+"?"url(#smc-obp)":z.type==="OB−"?"url(#smc-obm)":"url(#smc-fvg)";
        const cy=(y(z.top)+y(z.bot))/2;
        return (
          <g key={i}>
            <rect x={padL} y={y(z.top)} width={W-padL-padR} height={Math.max(4,y(z.bot)-y(z.top))} fill={fill}
              stroke={`var(--${z.tone})`} strokeOpacity="0.4" strokeWidth="0.7" strokeDasharray={z.type==="FVG"?"4 3":"none"}/>
            {/* connector + label tab on right */}
            <line x1={W-padR} y1={cy} x2={W-padR+14} y2={cy} stroke={`var(--${z.tone})`} strokeOpacity="0.5"/>
            <rect x={W-padR+14} y={cy-11} width={130} height={22} rx="5" fill="var(--bg-1)" stroke={`var(--${z.tone})`} strokeOpacity="0.5"/>
            <text x={W-padR+20} y={cy+1} fontSize="9.5" className="mono" fill={`var(--${z.tone})`} fontWeight="600">
              {z.type==="OB+"?"▲ OB+":z.type==="OB−"?"▼ OB−":"▦ FVG"}
            </text>
            <text x={W-padR+20} y={cy+10} fontSize="7.5" className="mono" fill="var(--ink-3)">{z.note}</text>
            <text x={W-padR+138} y={cy-1} fontSize="9" className="mono" textAnchor="end" fill={`var(--${z.tone})`}>${((z.top+z.bot)/2).toFixed(1)}</text>
          </g>
        );
      })}
      {/* candles */}
      {candles.map((c,i)=>{ const up=c.c>=c.o; const col=up?"var(--gn)":"var(--rd)"; return (
        <g key={i}>
          <line x1={cx(i)} y1={y(c.hi)} x2={cx(i)} y2={y(c.lo)} stroke={col} strokeWidth="1"/>
          <rect x={cx(i)-cw*0.3} y={y(Math.max(c.o,c.c))} width={cw*0.6} height={Math.max(1.5,Math.abs(y(c.o)-y(c.c)))} fill={col}/>
        </g>
      );})}
      {/* spot line */}
      <line x1={padL} y1={y(spot)} x2={W-padR} y2={y(spot)} stroke="var(--copper)" strokeWidth="1" strokeDasharray="3 3"/>
      <circle cx={cx(candles.length-1)} cy={y(spot)} r="4.5" fill="var(--copper)" style={{filter:"drop-shadow(0 0 6px var(--copper))"}}/>
      {/* legend */}
      <g transform={`translate(${padL+6},${padT+6})`}>
        <rect x="0" y="-2" width="11" height="8" fill="var(--gn)" opacity="0.4"/><text x="15" y="5" fontSize="9" className="mono" fill="var(--ink-2)">OB+ demand</text>
        <rect x="92" y="-2" width="11" height="8" fill="var(--rd)" opacity="0.4"/><text x="107" y="5" fontSize="9" className="mono" fill="var(--ink-2)">OB− supply</text>
        <rect x="184" y="-2" width="11" height="8" fill="var(--violet)" opacity="0.4"/><text x="199" y="5" fontSize="9" className="mono" fill="var(--ink-2)">FVG gap</text>
      </g>
    </svg>
  );
}

function SMCInducement() {
  return (
    <div className="smc-sub">
      <SMCStructureMap />
      <div className="smc-sub-rows">
        <div className="smc-row smc-row--amb"><span className="mono">Inducement low</span><span className="mono">$65.10</span><span className="mono dim2">minor liq · trap before sweep</span></div>
        <div className="smc-row smc-row--rd"><span className="mono">Engineered sweep</span><span className="mono">$62.10</span><span className="mono dim2">stops grabbed → reversal</span></div>
        <div className="smc-row smc-row--gn"><span className="mono">True intent</span><span className="mono">↑ $70.40</span><span className="mono dim2">real draw on liquidity</span></div>
      </div>
      <div className="mono dim" style={{fontSize:11}}>Read: minor low at $65.10 induced breakout-sellers; price swept $62.10 stops then reversed — classic liquidity engineering. Intent is up toward $70.40.</div>
    </div>
  );
}

function SMCBreakers() {
  return (
    <table className="dtable">
      <thead><tr><th>Block</th><th className="r">Zone</th><th>Origin</th><th>Polarity</th><th>Status</th></tr></thead>
      <tbody>
        {[
          ["Breaker","$65.10–65.40","failed bull OB","now resistance","active","rd"],
          ["Mitigation","$63.20–63.80","last down candle","support on retest","holding","gn"],
          ["Breaker","$60.40–60.90","failed bear OB","now support","untested","cy"],
        ].map((r,i)=>(
          <tr key={i}><td className="mono"><b>{r[0]}</b></td><td className="r mono">{r[1]}</td><td className="mono dim">{r[2]}</td><td className="mono">{r[3]}</td><td><Pill tone={r[5]} small>{r[4]}</Pill></td></tr>
        ))}
      </tbody>
    </table>
  );
}

function SMCVoidOTE() {
  return (
    <div className="smc-sub">
      <div className="kpi-row" style={{gridTemplateColumns:"repeat(4,1fr)"}}>
        <KpiTile label="Displacement leg" value="+5.8%" tone="gn" sub="$62.10 → $66.80 · 4 bars" />
        <KpiTile label="Liquidity void" value="$64.3–64.9" tone="violet" sub="single-candle · unfilled" />
        <KpiTile label="OTE 62–79%" value="$63.9–64.6" tone="copper" sub="optimal entry zone" />
        <KpiTile label="OTE 70.5%" value="$64.18" tone="amb" sub="sweet spot" />
      </div>
      <div className="mono dim" style={{fontSize:11}}>Displacement confirms intent (impulsive 4-bar leg). Best entries retrace into OTE 62–79% of that leg — $63.9–64.6 — which also overlaps the $63.2–63.8 OB. High-confluence pullback zone.</div>
    </div>
  );
}

function SMCKillSMT() {
  return (
    <div className="smc-sub smc-2col">
      <div>
        <div className="label-cap" style={{marginBottom:6}}>KILL ZONES · session edge</div>
        {[["London open","02:00–05:00","done · swept high","ink"],["NY AM","08:30–11:00","ACTIVE · continuation","gn"],["NY PM","13:30–16:00","upcoming","amb"]].map((r,i)=>(
          <div key={i} className={`smc-row smc-row--${r[3]}`}><span className="mono">{r[0]}</span><span className="mono dim2">{r[1]}</span><span className={`mono ${r[3]==="gn"?"up":"dim2"}`}>{r[2]}</span></div>
        ))}
      </div>
      <div>
        <div className="label-cap" style={{marginBottom:6}}>SMT DIVERGENCE · vs XLB</div>
        <div className="smc-row smc-row--gn"><span className="mono">ARCM</span><span className="mono up">higher low ✓</span></div>
        <div className="smc-row smc-row--rd"><span className="mono">XLB (sector)</span><span className="mono dn">lower low</span></div>
        <div className="mono dim" style={{fontSize:11,marginTop:6}}>Bullish SMT: ARCM held a higher low while the sector ETF made a lower low — relative strength, smart-money accumulation signal.</div>
      </div>
    </div>
  );
}

function SMCEntryModel() {
  const steps=[
    { s:"1 · Liquidity sweep", done:true, note:"$62.10 stops grabbed" },
    { s:"2 · CHoCH / BoS", done:true, note:"4H break of structure ↑" },
    { s:"3 · FVG / imbalance", done:true, note:"$64.3–64.9 formed" },
    { s:"4 · OB / OTE entry", done:false, note:"awaiting retrace to $63.9–64.6" },
    { s:"5 · Confirmation", done:false, note:"LTF CHoCH on entry tap" },
  ];
  const grade="B+";
  return (
    <div className="smc-sub">
      <div className="smc-grade-row">
        <div className="smc-grade">{grade}</div>
        <div className="smc-grade-meta mono dim2">3 of 5 steps · OB at HTF level + unswept liquidity above = high confluence. Waiting on retrace + LTF confirm.</div>
      </div>
      <div className="smc-steps">
        {steps.map((st,i)=>(
          <div key={i} className={`smc-step ${st.done?"is-done":""}`}>
            <span className="smc-step-ck">{st.done?"✓":"○"}</span>
            <span className="mono smc-step-s">{st.s}</span>
            <span className="mono dim2 smc-step-n">{st.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
