// lens-earnings.jsx + lens-options.jsx

// ────────────────────────────────────────────────────────────
// EARNINGS — countdown, implied-move cone, beat probability
// ────────────────────────────────────────────────────────────
function LensEarnings({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("er-1"); const s2 = useStateToggle("er-2");
  const s3 = useStateToggle("er-3"); const s4 = useStateToggle("er-4");

  return (
    <div className="lens lens--er">
      <div className="hero er-hero">
        <div className="er-hero-left">
          <div className="label-cap">Next earnings · Q1 FY26</div>
          <div className="er-countdown">
            <div className="er-cd-num mono">11</div>
            <div className="er-cd-unit mono">days</div>
            <div className="er-cd-date mono dim2">Jun 09 · BMO · Wed</div>
          </div>
          <div className="er-pills">
            <Pill tone="amb" small>ESP +4.1%</Pill>
            <Pill tone="gn" small>Beat prob 64%</Pill>
            <Pill tone="amb" small>Implied move ±6.4%</Pill>
            <Pill tone="rd" small>3/4 last beats</Pill>
          </div>
        </div>
        <div className="er-hero-right">
          <ImpliedMoveCone />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Implied Move · Cone"
          sub="ATM straddle pricing the move · current vs 4-quarter realized"
          style={headerStyle} right={<StateToggle name="er-1" />} />
        <StateWrap state={s1.value} source="Schwab · options chain ATM">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Implied 1-day" value="±6.4%" tone="amb" sub="$63.10 — $71.74" />
              <KpiTile label="Realized 4Q avg" value="±5.8%" tone="ink" sub="historic move" />
              <KpiTile label="Implied / realized" value="1.10×" tone="amb" sub="slightly rich" />
              <KpiTile label="IV at ATM" value="48.2%" tone="ink" sub="vs 30d HV 34%" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Beat-Probability · ESP"
          sub="Zacks ESP + earnings-surprise model"
          style={headerStyle} right={<StateToggle name="er-2" />} />
        <StateWrap state={s2.value} source="Zacks · ESP · proprietary blend">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Zacks ESP" value="+4.1%" tone="gn" sub="most accurate est. − consensus" />
              <KpiTile label="Zacks rank" value="#2 BUY" tone="gn" sub="6 analyst rev up · 1 down" />
              <KpiTile label="Model beat prob" value="64%" tone="gn" sub="Wilson LB 51%" />
              <KpiTile label="Post-ER drift" value="+1.8%" tone="gn" sub="median · last 12 quarters" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="8-Quarter Track Record"
          sub="EPS surprise · revenue surprise · 1-day reaction"
          style={headerStyle} right={<StateToggle name="er-3" />} />
        <StateWrap state={s3.value} source="EODHD · Earnings history">
          <div className="lens-pad"><ERHistory /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Pre-ER Drift · IV Crush"
          sub="how the name typically behaves heading in & out of print"
          style={headerStyle} right={<StateToggle name="er-4" />} />
        <StateWrap state={s4.value} source="EODHD + Schwab · 12-Q backtest">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Pre-ER drift T−5" value="+1.2%" tone="gn" sub="median · 12-Q" />
              <KpiTile label="Pre-ER drift T−1" value="+0.4%" tone="gn" sub="last-day rally" />
              <KpiTile label="IV crush · T+0" value="−42%" tone="rd" sub="ATM crush typical" />
              <KpiTile label="Avg post-ER vol" value="22 → 32%" tone="amb" sub="vol expansion" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="amb" cells={[
            { lens: "Earnings",   verdict: "11 d",   tone: "amb", note: "trim 25% T−2 · ESP +4.1%" },
            { lens: "Options",    verdict: "RICH",   tone: "amb", note: "IV/HV 1.42 · post crush −42%" },
            { lens: "Plan",       verdict: "ADJUST", tone: "amb", note: "scale down through window" },
            { lens: "Risk",       verdict: "CAPPED", tone: "gn",  note: "max loss bounded at stop" },
            { lens: "Track Rec",  verdict: "EDGE",   tone: "gn",  note: "beat-drift hist. positive" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · Earnings</span>
        <span className="mono">
          Hold the breakout · scale down 25% at T−2 sessions · re-add on post-ER vol crush
          if thesis intact. Don't be a hero on the print.
        </span>
      </div>
    </div>
  );
}

function ImpliedMoveCone() {
  return (
    <svg viewBox="0 0 300 130" width="300" height="130">
      <line x1="20" y1="65" x2="280" y2="65" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 65 Q 150 14 280 14" stroke="var(--gn)" strokeWidth="1.3" fill="none" />
      <path d="M 20 65 Q 150 116 280 116" stroke="var(--rd)" strokeWidth="1.3" fill="none" />
      {/* Today marker */}
      <circle cx="20" cy="65" r="3" fill="var(--copper)" />
      <text x="20" y="128" fontSize="9" className="mono" textAnchor="start" fill="var(--ink-2)">T−11</text>
      {/* ER day */}
      <line x1="230" y1="0" x2="230" y2="130" stroke="var(--amb)" strokeWidth="1" strokeDasharray="2 2" />
      <text x="232" y="11" fontSize="9" className="mono" fill="var(--amb)">ER · Jun 09</text>
      <text x="276" y="11" fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">+6.4%</text>
      <text x="276" y="125" fontSize="9" className="mono" textAnchor="end" fill="var(--rd)">−6.4%</text>
    </svg>
  );
}

function ERHistory() {
  const rows = [
    { q: "Q4'25", date: "Mar 06", epsE: 0.84, epsA: 0.91, surp: "+8.3%", react: "+5.2%", tone: "gn" },
    { q: "Q3'25", date: "Dec 04", epsE: 0.71, epsA: 0.76, surp: "+7.0%", react: "+3.1%", tone: "gn" },
    { q: "Q2'25", date: "Sep 05", epsE: 0.65, epsA: 0.62, surp: "−4.6%", react: "−6.2%", tone: "rd" },
    { q: "Q1'25", date: "Jun 06", epsE: 0.58, epsA: 0.61, surp: "+5.2%", react: "+2.4%", tone: "gn" },
    { q: "Q4'24", date: "Mar 07", epsE: 0.52, epsA: 0.52, surp: "0.0%",  react: "+0.6%", tone: "ink" },
    { q: "Q3'24", date: "Dec 06", epsE: 0.48, epsA: 0.50, surp: "+4.2%", react: "+2.8%", tone: "gn" },
    { q: "Q2'24", date: "Sep 07", epsE: 0.41, epsA: 0.43, surp: "+4.9%", react: "−1.4%", tone: "amb" },
    { q: "Q1'24", date: "Jun 07", epsE: 0.38, epsA: 0.41, surp: "+7.9%", react: "+3.9%", tone: "gn" },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Quarter</th><th>Date</th>
          <th className="r">EPS est</th><th className="r">EPS act</th>
          <th className="r">Surprise</th><th className="r">1-day react</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono"><b>{r.q}</b></td>
            <td className="mono dim">{r.date}</td>
            <td className="r mono tabular">{r.epsE.toFixed(2)}</td>
            <td className="r mono tabular">{r.epsA.toFixed(2)}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.surp}</td>
            <td className={`r mono tabular kpi-tone--${r.tone}`}>{r.react}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ────────────────────────────────────────────────────────────
// OPTIONS — IV surface, max-pain, UOA, chain grid, payoff
// ────────────────────────────────────────────────────────────
function LensOptions({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("op-1"); const s2 = useStateToggle("op-2");
  const s3 = useStateToggle("op-3"); const s4 = useStateToggle("op-4");
  const s5 = useStateToggle("op-5");

  return (
    <div className="lens lens--opt">
      <div className="hero opt-hero">
        <div className="th-left">
          <div className="label-cap">Vol regime · ARCM options</div>
          <div className="th-score">
            <div className="th-score-num mono">RICH</div>
            <Pill tone="amb" dot>IV/HV 1.42×</Pill>
            <Pill tone="gn" small>UOA · CALL 70Cs</Pill>
            <Pill tone="amb" small>Skew steep</Pill>
          </div>
          <div className="th-pill-row">
            <Pill tone="ink" small>Max pain $65</Pill>
            <Pill tone="ink" small>Put/Call 0.62</Pill>
            <Pill tone="ink" small>30d IV 48%</Pill>
            <Pill tone="ink" small>60d IV 42%</Pill>
          </div>
        </div>
        <div className="th-right">
          <IVSmile />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Vol Richness"
          sub="IV vs realized · vs sector · vs own 1y"
          style={headerStyle} right={<StateToggle name="op-1" />} />
        <StateWrap state={s1.value} source="Schwab · chain + bespoke vol model">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="30d IV" value="48.2%" tone="amb" sub="rich vs HV 34%" />
              <KpiTile label="IV / HV" value="1.42×" tone="amb" sub="seller-favorable" />
              <KpiTile label="IV rank 1y" value="68%" tone="amb" sub="above median" />
              <KpiTile label="Sector IV avg" value="38%" tone="ink" sub="+10pt premium" />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Unusual Options Activity"
          sub="recent prints · OI build · large premium"
          style={headerStyle} right={<StateToggle name="op-2" />} />
        <StateWrap state={s2.value} source="Schwab · time & sales · prop UOA detector">
          <div className="lens-pad"><UOATable /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Chain Grid · ATM ±3 strikes"
          sub="Jul 18 expiry · Greeks · OI · vol"
          style={headerStyle} right={<StateToggle name="op-3" />} />
        <StateWrap state={s3.value} source="Schwab · option chain">
          <div className="lens-pad"><ChainGrid /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Strategy Matrix"
          sub="conditional on swing-trade thesis · BUY-STOP + collar variants"
          style={headerStyle} right={<StateToggle name="op-4" />} />
        <StateWrap state={s4.value} source="strategy synthesizer">
          <div className="lens-pad"><StrategyMatrix /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Payoff · Bull-Call-Spread alt."
          sub="if option-overlay preferred over equity entry"
          style={headerStyle} right={<StateToggle name="op-5" />} />
        <StateWrap state={s5.value} source="payoff calc">
          <div className="lens-pad"><PayoffDiagram /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="amb" cells={[
            { lens: "Options",  verdict: "RICH", tone: "amb", note: "IV/HV 1.42 · sell vol favored" },
            { lens: "Earnings", verdict: "11 d", tone: "amb", note: "post-ER crush expected" },
            { lens: "Plan",     verdict: "READY",tone: "gn",  note: "stock entry preferred" },
            { lens: "Flow",     verdict: "BULL", tone: "gn",  note: "70Cs buying · UOA flagged" },
            { lens: "Risk",     verdict: "CAPPED",tone:"gn",  note: "bracket caps tail" },
          ]} />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · Options</span>
        <span className="mono">
          Equity entry preferred · if hedging, <b className="copper">Aug $65/$75 call-spread</b>
          for $2.85 · max gain $7.15 · 2.50R. Avoid naked premium pre-ER.
        </span>
      </div>
    </div>
  );
}

function IVSmile() {
  // synthetic skew (steeper put side)
  return (
    <svg viewBox="0 0 280 110" width="280" height="110">
      <line x1="20" y1="90" x2="270" y2="90" stroke="var(--line)" strokeDasharray="3 3" />
      <line x1="145" y1="0" x2="145" y2="110" stroke="var(--copper)" strokeWidth="1" strokeDasharray="2 3" />
      <text x="148" y="11" fontSize="9" className="mono" fill="var(--copper)">ATM $67</text>
      <path d="M 20 38 Q 80 78, 145 70 Q 210 64, 270 50" stroke="var(--violet)" strokeWidth="1.5" fill="none" />
      {/* Put side / call side */}
      <text x="22" y="34" fontSize="9" className="mono" fill="var(--rd)">put · 62%</text>
      <text x="266" y="46" fontSize="9" className="mono" textAnchor="end" fill="var(--gn)">call · 44%</text>
    </svg>
  );
}

function UOATable() {
  const rows = [
    { t: "13:52", side: "CALL", strike: "$70", exp: "Jul 18", prem: "$1.42", vol: 4_280, oi: 1_120, note: "BTO · 3.8× OI", tone: "gn" },
    { t: "12:14", side: "CALL", strike: "$72.5", exp: "Aug 15", prem: "$1.10", vol: 2_140, oi: 480, note: "BTO · sweeper", tone: "gn" },
    { t: "11:08", side: "PUT",  strike: "$62.5", exp: "Jul 18", prem: "$0.88", vol: 1_240, oi: 940, note: "Hedge buy", tone: "amb" },
    { t: "10:42", side: "CALL", strike: "$67.5", exp: "Jun 20", prem: "$1.86", vol: 1_960, oi: 620, note: "Pre-ER buy", tone: "gn" },
  ];
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Time</th><th>Side</th><th>Strike</th><th>Exp</th>
          <th className="r">Prem</th><th className="r">Vol</th><th className="r">OI</th><th>Note</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="mono dim">{r.t}</td>
            <td><Pill tone={r.side === "CALL" ? "gn" : "rd"} small>{r.side}</Pill></td>
            <td className="mono"><b>{r.strike}</b></td>
            <td className="mono dim">{r.exp}</td>
            <td className="r mono tabular">{r.prem}</td>
            <td className="r mono tabular">{r.vol.toLocaleString()}</td>
            <td className="r mono tabular dim">{r.oi.toLocaleString()}</td>
            <td className={`mono ${r.tone === "gn" ? "up" : "warn"}`}>{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ChainGrid() {
  const strikes = [65, 66, 67, 68, 70];
  const cur = 67.42;
  return (
    <table className="dtable chain">
      <thead>
        <tr>
          <th colSpan="4" className="ch-side-c">CALLS</th>
          <th>Strike</th>
          <th colSpan="4" className="ch-side-p">PUTS</th>
        </tr>
        <tr>
          <th>OI</th><th>Vol</th><th>IV</th><th className="r">Bid/Ask</th>
          <th></th>
          <th className="r">Bid/Ask</th><th>IV</th><th>Vol</th><th>OI</th>
        </tr>
      </thead>
      <tbody>
        {strikes.map(k => {
          const itm = k <= cur;
          return (
            <tr key={k} className={k === Math.round(cur) ? "is-current" : ""}>
              <td className="mono dim">{(2400 - k * 12).toLocaleString()}</td>
              <td className="mono">{(740 - k * 8).toLocaleString()}</td>
              <td className="mono">{(42 + (cur - k) * 1.2).toFixed(0)}%</td>
              <td className={`r mono tabular ${itm ? "up" : "dim"}`}>{Math.max(0.05, cur - k + 1.4).toFixed(2)} / {(Math.max(0.10, cur - k + 1.5)).toFixed(2)}</td>
              <td className="mono ch-strike"><b>${k}</b></td>
              <td className={`r mono tabular ${!itm ? "up" : "dim"}`}>{Math.max(0.05, k - cur + 1.3).toFixed(2)} / {Math.max(0.10, k - cur + 1.4).toFixed(2)}</td>
              <td className="mono">{(44 + (k - cur) * 1.4).toFixed(0)}%</td>
              <td className="mono">{(380 + k * 6).toLocaleString()}</td>
              <td className="mono dim">{(1100 + k * 12).toLocaleString()}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function StrategyMatrix() {
  const rows = [
    { name: "Equity · BUY-STOP",          R: "1.74", maxL: "$420", maxG: "open", pref: true, note: "primary" },
    { name: "Aug $65/$75 call-spread",   R: "2.50", maxL: "$285", maxG: "$715", pref: false, note: "defined-risk alt" },
    { name: "Aug $65 long call",         R: "2.10", maxL: "$510", maxG: "open", pref: false, note: "high IV — costly" },
    { name: "Collar (long stock + Aug 62/72)", R: "0.95", maxL: "$220", maxG: "$385", pref: false, note: "if hedging long" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Strategy</th><th className="r">R</th><th className="r">Max Loss</th><th className="r">Max Gain</th><th>Note</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={r.pref ? "is-current" : ""}>
            <td className="mono"><b>{r.name}</b></td>
            <td className="r mono tabular copper">{r.R}</td>
            <td className="r mono tabular dn">{r.maxL}</td>
            <td className="r mono tabular up">{r.maxG}</td>
            <td className="mono dim">{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PayoffDiagram() {
  // Bull call spread $65/$75 paid $2.85
  const w = 520, h = 160;
  const minPx = 58, maxPx = 80;
  const cost = 2.85, low = 65, high = 75;
  const range = maxPx - minPx;
  const x = p => 20 + ((p - minPx) / range) * (w - 40);
  const y = pnl => {
    // pnl from -300 to 750
    const yMin = -350, yMax = 800;
    return h - 12 - ((pnl - yMin) / (yMax - yMin)) * (h - 20);
  };
  const pnlAt = (px) => Math.min(high - low, Math.max(0, px - low)) - cost;
  const samples = [];
  for (let p = minPx; p <= maxPx; p += 0.5) {
    samples.push([x(p), y(pnlAt(p) * 100)]);
  }
  return (
    <div className="payoff-block">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <line x1={20} y1={y(0)} x2={w - 20} y2={y(0)} stroke="var(--line)" />
        <line x1={x(low)} y1="0" x2={x(low)} y2={h} stroke="var(--copper)" strokeDasharray="3 3" opacity="0.6" />
        <line x1={x(high)} y1="0" x2={x(high)} y2={h} stroke="var(--gn)" strokeDasharray="3 3" opacity="0.6" />
        <polyline points={samples.map(p => p.join(",")).join(" ")} stroke="var(--copper)" strokeWidth="2" fill="none" />
        <text x={x(low)} y="10" fontSize="9" className="mono" textAnchor="middle" fill="var(--copper)">$65</text>
        <text x={x(high)} y="10" fontSize="9" className="mono" textAnchor="middle" fill="var(--gn)">$75</text>
        <text x={w - 22} y={y(715) - 4} fontSize="10" className="mono" textAnchor="end" fill="var(--gn)">+$715 max</text>
        <text x={w - 22} y={y(-285) + 12} fontSize="10" className="mono" textAnchor="end" fill="var(--rd)">−$285 max</text>
      </svg>
    </div>
  );
}

window.LensEarnings = LensEarnings;
window.LensOptions = LensOptions;
