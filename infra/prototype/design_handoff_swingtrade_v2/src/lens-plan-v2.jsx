// lens-plan-v2.jsx — completely redesigned Plan · Ticket lens.
// Decision-first quant view. Replaces window.LensPlan.

const { useState: useStateP2, useMemo: useMemoP2 } = React;

function LensPlan({ ticker: t0, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const ticker = useMemoP2(() => modeAdjustP2(t0, mode), [t0, mode]);
  const [sizeMult, setSizeMult] = useStateP2(1.0);
  const [kellyFrac, setKellyFrac] = useStateP2(0.5);
  const s1 = useStateToggle("plv2-1"); const s2 = useStateToggle("plv2-2");
  const s3 = useStateToggle("plv2-3"); const s4 = useStateToggle("plv2-4");
  const s5 = useStateToggle("plv2-5"); const s6 = useStateToggle("plv2-6");

  return (
    <div className="lens lens--plan2">
      <PlanActionPanel ticker={ticker} mode={mode} sizeMult={sizeMult} />

      <div className="lens-2col plan-2col">
      <div className="lens-section">
        <SectionHeader n={1} title="Trade Blueprint"
          sub="visual ladder · ATR bands · stop / entry / T1 / T2 / current price"
          style={headerStyle} right={<StateToggle name="plv2-1" />} />
        <StateWrap state={s1.value} source="Schwab quotes · ATR computed">
          <div className="lens-pad"><TradeBlueprint ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Sizing Workbench · live"
          sub="adjust Kelly fraction + size multiplier · R:R, $ risk, NAV% recompute live"
          style={headerStyle} right={<StateToggle name="plv2-2" />} />
        <StateWrap state={s2.value} source="risk engine · portfolio_state">
          <div className="lens-pad">
            <SizingWorkbench
              ticker={ticker}
              sizeMult={sizeMult} onSizeMult={setSizeMult}
              kellyFrac={kellyFrac} onKellyFrac={setKellyFrac}
            />
          </div>
        </StateWrap>
      </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Decision Gates · go/no-go"
          sub="every gate must pass before the bracket fires"
          style={headerStyle} right={<StateToggle name="plv2-3" />} />
        <StateWrap state={s3.value} source="rule engine · 10 gates">
          <div className="lens-pad"><DecisionGates /></div>
        </StateWrap>
      </div>

      <div className="lens-2col plan-2col">
      <div className="lens-section">
        <SectionHeader n={4} title="Time Anatomy"
          sub={`hold ~${ticker.holdDays}d · sessions plotted to scale`}
          style={headerStyle} right={<StateToggle name="plv2-4" />} />
        <StateWrap state={s4.value} source="planner · setup_stats + calendar">
          <div className="lens-pad"><TimeAnatomyV2 ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Conditional Playbook · IF/THEN tree"
          sub="pre-decided reactions to every realistic price/vol path"
          style={headerStyle} right={<StateToggle name="plv2-5" />} />
        <StateWrap state={s5.value} source="playbook · per-setup family rules">
          <div className="lens-pad"><PlaybookTree /></div>
        </StateWrap>
      </div>
      </div>

      <div className="lens-2col plan-2col">
      <div className="lens-section">
        <SectionHeader n={6} title="Audit · pre-fill + post-fill"
          sub="every decision logged · the system is the discipline"
          style={headerStyle} right={<StateToggle name="plv2-6" />} />
        <StateWrap state={s6.value} source="rule engine · audit log">
          <div className="lens-pad"><AuditLog /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens lead="copper" cells={[
            { lens: "Plan",       verdict: "READY", tone: "gn",  note: `R ${ticker.rMultiple.toFixed(2)} · half-Kelly` },
            { lens: "Technicals", verdict: "PASS",  tone: "gn",  note: "RSI 64 · VWAP-reclaim" },
            { lens: "Risk",       verdict: "OK",    tone: "gn",  note: "VaR(1d) −2.1%" },
            { lens: "Earnings",   verdict: "11 d",  tone: "amb", note: "size −25% pre-ER" },
            { lens: "Track Rec.", verdict: "EDGE",  tone: "gn",  note: `n=${ticker.setupStats.n} · pf ${ticker.setupStats.pf.toFixed(2)}` },
          ]} />
        </div>
      </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Call · {mode}</span>
        <span className="mono">
          BUY-STOP LIMIT <b className="copper">${(ticker.pivot * 1.002).toFixed(2)}</b> ·
          stop <b className="dn">${ticker.stop.toFixed(2)}</b> · T1 <b className="up">${ticker.t1.toFixed(2)}</b> ·
          {' '}max risk <b>$420</b> · {Math.round(110 * sizeMult)} shares · {(6.8 * sizeMult).toFixed(1)}% NAV.
        </span>
      </div>
    </div>
  );
}

function modeAdjustP2(ticker, mode) {
  if (mode === "POSITION") return { ...ticker, stop: ticker.stop * 0.96, t1: ticker.t1 * 1.10, t2: ticker.t2 * 1.18, holdDays: 38, rMultiple: 2.21 };
  if (mode === "INVESTMENT") return { ...ticker, stop: ticker.stop * 0.84, t1: ticker.t1 * 1.32, t2: ticker.t2 * 1.58, holdDays: 180, rMultiple: 2.94 };
  return ticker;
}
window.modeAdjust = modeAdjustP2;

// ─── §0 Action Panel ────────────────────────────────────────────
function PlanActionPanel({ ticker, mode, sizeMult }) {
  const entry = ticker.pivot * 1.002;
  const sh = Math.round(110 * sizeMult);
  const notional = (sh * entry).toFixed(0);
  const navPct = (6.8 * sizeMult).toFixed(1);
  return (
    <div className="pap">
      <div className="pap-l">
        <div className="pap-eyebrow mono">PLAN · TICKET · {mode}</div>
        <div className="pap-headline mono">
          <span className="pap-action">BUY-STOP BRACKET</span>
          <span className="pap-sym">{ticker.symbol}</span>
          <span className="pap-px copper">${entry.toFixed(2)}</span>
        </div>
        <div className="pap-line mono dim2">
          {ticker.setupFamily} · {sh} sh · ${Number(notional).toLocaleString()} notional · <b>{navPct}% NAV</b> · OCO armed
        </div>
      </div>
      <div className="pap-r">
        <button className="pap-fire">⚡ FIRE BRACKET <span className="kbd">⌘↵</span></button>
        <div className="pap-r-actions">
          <button className="btn btn--sm">SAVE PLAN</button>
          <button className="btn btn--sm">DRY-RUN</button>
          <button className="btn btn--sm">＋ JOURNAL</button>
        </div>
      </div>
    </div>
  );
}

// ─── §1 Trade Blueprint — horizontal payoff diagram ────────────
function TradeBlueprint({ ticker }) {
  const entry = ticker.pivot * 1.002;
  const cur = ticker.price;
  const stop = ticker.stop;
  const t1 = ticker.t1;
  const t2 = ticker.t2;
  const atr = 1.24;
  const risk = entry - stop;
  const reward1 = t1 - entry;
  const reward2 = t2 - entry;
  const qty = 110;
  const maxLoss = risk * qty;
  const t1Gain = reward1 * qty;
  const t2Gain = reward2 * qty;

  const W = 900, H = 380, padT = 46, padB = 60, padL = 72, padR = 100;
  const xMin = stop - 1.5, xMax = t2 + 1.5;
  const xRange = xMax - xMin;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const x = (p) => padL + ((p - xMin) / xRange) * innerW;
  const pnlMin = -maxLoss * 1.20, pnlMax = t2Gain * 1.15;
  const y = (pnl) => padT + (1 - (pnl - pnlMin) / (pnlMax - pnlMin)) * innerH;
  const y0 = y(0);

  const pnlAt = (price) => {
    if (price <= stop) return -maxLoss;
    if (price <= entry) return -maxLoss + ((price - stop) / risk) * maxLoss;
    if (price <= t2) return ((price - entry) / (t2 - entry)) * t2Gain;
    return t2Gain;
  };
  const samples = [];
  for (let p = xMin; p <= xMax; p += 0.2) samples.push([x(p), y(pnlAt(p))]);

  const levels = [
    { p: stop,  c: "var(--rd)",     lbl: "STOP",  v: `$${stop.toFixed(2)}`,  sub: `−$${maxLoss.toFixed(0)}` },
    { p: entry, c: "var(--copper)", lbl: "ENTRY", v: `$${entry.toFixed(2)}`, sub: "pivot · 110 sh", big: true },
    { p: cur,   c: "var(--copper)", lbl: "NOW",   v: `$${cur.toFixed(2)}`,   sub: pnlAt(cur) >= 0 ? `+$${pnlAt(cur).toFixed(0)}` : `−$${Math.abs(pnlAt(cur)).toFixed(0)}`, dotted: true },
    { p: t1,    c: "var(--gn)",     lbl: "T1",    v: `$${t1.toFixed(2)}`,    sub: `+$${t1Gain.toFixed(0)}`, big: true },
    { p: t2,    c: "var(--gn)",     lbl: "T2",    v: `$${t2.toFixed(2)}`,    sub: `+$${t2Gain.toFixed(0)}` },
  ];

  return (
    <div className="tbv2">
      <div className="tbv2-metrics">
        <TbMetric label="Risk · 1R" value={`−$${maxLoss.toFixed(0)}`} sub={`${(maxLoss/108420*100).toFixed(2)}% NAV`} tone="rd" />
        <TbMetric label="R:R · T1" value={`${(reward1/risk).toFixed(2)}R`} sub={`+$${t1Gain.toFixed(0)} reward`} tone="gn" big />
        <TbMetric label="R:R · T2" value={`${(reward2/risk).toFixed(2)}R`} sub={`+$${t2Gain.toFixed(0)} reward`} tone="gn" />
        <TbMetric label="% to Stop" value={`−${(risk/entry*100).toFixed(2)}%`} sub={`$${risk.toFixed(2)} below`} tone="rd" />
        <TbMetric label="% to T1" value={`+${(reward1/entry*100).toFixed(2)}%`} sub={`$${reward1.toFixed(2)} above`} tone="gn" />
        <TbMetric label="ATR · 14d" value={`$${atr.toFixed(2)}`} sub="1.8% · daily" tone="ink" />
        <TbMetric label="Days · T1" value="6.5" sub="setup median" tone="ink" />
        <TbMetric label="Wilson WR" value="47.7%" sub="LB · n=47" tone="copper" />
      </div>

      <div className="tbv2-chart">
        <svg viewBox={`0 0 ${W} ${H}`} className="tbv2-svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="tbv2-gn" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.40" />
              <stop offset="100%" stopColor="var(--gn)" stopOpacity="0.02" />
            </linearGradient>
            <linearGradient id="tbv2-rd" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="var(--rd)" stopOpacity="0.40" />
              <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.02" />
            </linearGradient>
            <clipPath id="tbv2-clip-gn"><rect x="0" y="0" width={W} height={y0} /></clipPath>
            <clipPath id="tbv2-clip-rd"><rect x="0" y={y0} width={W} height={H - y0} /></clipPath>
          </defs>

          <rect x={padL} y={padT} width={innerW} height={innerH}
                fill="color-mix(in oklab, var(--bg-1) 55%, transparent)" rx="8" />
          {[0.25, 0.5, 0.75].map(f => (
            <line key={f} x1={padL + innerW * f} y1={padT} x2={padL + innerW * f} y2={H - padB}
                  stroke="var(--glass-line)" strokeWidth="0.5" />
          ))}

          <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="var(--ink-3)" strokeDasharray="3 3" opacity="0.55" />
          <text x={padL - 8} y={y0 + 3} fontSize="10" className="mono" textAnchor="end" fill="var(--ink-3)">$0</text>

          <g clipPath="url(#tbv2-clip-gn)">
            <path d={`M ${padL} ${y0} L ${samples.map(s => s.join(",")).join(" L ")} L ${W - padR} ${y0} Z`} fill="url(#tbv2-gn)" />
          </g>
          <g clipPath="url(#tbv2-clip-rd)">
            <path d={`M ${padL} ${y0} L ${samples.map(s => s.join(",")).join(" L ")} L ${W - padR} ${y0} Z`} fill="url(#tbv2-rd)" />
          </g>

          {levels.map((m, i) => (
            <g key={i}>
              <line x1={x(m.p)} y1={padT - 4} x2={x(m.p)} y2={H - padB + 4}
                    stroke={m.c} strokeWidth={m.big ? "1.6" : "1.2"}
                    strokeDasharray={m.dotted ? "2 3" : "4 4"} opacity="0.7"
                    style={{ filter: `drop-shadow(0 0 4px ${m.c})` }} />
              <g transform={`translate(${x(m.p)}, ${padT - 22})`}>
                <rect x="-32" y="-12" width="64" height="22" rx="11"
                      fill="color-mix(in oklab, var(--bg-1) 92%, transparent)"
                      stroke={m.c} strokeWidth={m.big ? "1.4" : "0.8"}
                      style={{ filter: m.big ? `drop-shadow(0 0 6px ${m.c})` : "none" }} />
                <text x="0" y="3" fontSize="11" className="mono" textAnchor="middle" fill={m.c}
                      fontWeight="600" letterSpacing="0.10em">{m.lbl}</text>
              </g>
              <text x={x(m.p)} y={H - padB + 20} fontSize="11" className="mono" textAnchor="middle"
                    fill={m.c} fontWeight="500">{m.v}</text>
              <text x={x(m.p)} y={H - padB + 34} fontSize="10" className="mono" textAnchor="middle" fill="var(--ink-3)">
                {m.sub}
              </text>
            </g>
          ))}

          <polyline points={samples.map(s => s.join(",")).join(" ")}
                    stroke="var(--ink)" strokeWidth="2.5" fill="none" strokeLinejoin="round"
                    style={{ filter: "drop-shadow(0 0 6px color-mix(in oklab, var(--copper) 60%, transparent))" }} />

          {levels.map((d, i) => (
            <circle key={i} cx={x(d.p)} cy={y(pnlAt(d.p))} r={d.big ? 6 : 4.5} fill={d.c}
                    stroke="var(--bg)" strokeWidth="2"
                    style={{ filter: `drop-shadow(0 0 8px ${d.c})` }} />
          ))}

          {[-maxLoss, t1Gain, t2Gain].map((pnl, i) => (
            <g key={i}>
              <line x1={padL - 4} y1={y(pnl)} x2={padL} y2={y(pnl)} stroke="var(--ink-3)" />
              <text x={padL - 8} y={y(pnl) + 3} fontSize="10" className="mono" textAnchor="end"
                    fill={pnl > 0 ? "var(--gn)" : "var(--rd)"} fontWeight="500">
                {pnl > 0 ? "+" : ""}${Math.abs(pnl).toFixed(0)}
              </text>
            </g>
          ))}

          <text x={W - padR + 8} y={y(t2Gain) + 3} fontSize="10" className="mono" fill="var(--gn)">
            +{(reward2/risk).toFixed(2)}R
          </text>
          <text x={W - padR + 8} y={y(t1Gain) + 3} fontSize="10" className="mono" fill="var(--gn)">
            +{(reward1/risk).toFixed(2)}R
          </text>
          <text x={W - padR + 8} y={y(-maxLoss) + 3} fontSize="10" className="mono" fill="var(--rd)">
            −1.00R
          </text>

          <text x={padL} y={20} fontSize="11" className="mono" fill="var(--ink-2)" letterSpacing="0.14em">
            P&L · $ (110 sh · BUY-STOP bracket)
          </text>
          <text x={W - padR} y={H - 8} fontSize="10.5" className="mono" textAnchor="end" fill="var(--ink-3)">
            price ($)  →
          </text>
        </svg>
      </div>

      <div className="tbv2-legend mono">
        <span><span className="tbv2-leg-dot tbv2-leg-cop" /> bracket payoff · stop → T2 capped</span>
        <span><span className="tbv2-leg-dot tbv2-leg-gn" /> profit zone</span>
        <span><span className="tbv2-leg-dot tbv2-leg-rd" /> loss zone</span>
        <span className="dim2">price on X · $ P&L on Y · R-mult on right axis</span>
      </div>
    </div>
  );
}

function TbMetric({ label, value, sub, tone, big }) {
  return (
    <div className={`tbv2-metric tbv2-metric--${tone} ${big ? "is-big" : ""}`}>
      <div className="tbv2-metric-l label-cap">{label}</div>
      <div className={`tbv2-metric-v mono kpi-tone--${tone}`}>{value}</div>
      <div className="tbv2-metric-s mono dim2">{sub}</div>
    </div>
  );
}

// ─── §2 Sizing Workbench ───────────────────────────────────────
function SizingWorkbench({ ticker, sizeMult, onSizeMult, kellyFrac, onKellyFrac }) {
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward = ticker.t1 - entry;
  const baseSh = 110;
  const sh = Math.round(baseSh * sizeMult * (kellyFrac / 0.5));
  const notional = sh * entry;
  const maxLoss = sh * risk;
  const navPct = notional / 108420 * 100;
  const lossNavPct = maxLoss / 108420 * 100;
  return (
    <div className="sw">
      <div className="sw-controls">
        <div className="sw-ctrl">
          <div className="sw-ctrl-l">
            <span className="label-cap">Kelly fraction</span>
            <span className="mono"><b className="copper">{(kellyFrac * 100).toFixed(0)}%</b> of raw Kelly</span>
          </div>
          <input type="range" min="0.10" max="1.00" step="0.05" value={kellyFrac}
                 onChange={e => onKellyFrac(parseFloat(e.target.value))} className="sw-range" />
          <div className="sw-ticks mono dim2">
            <span>¼K</span><span>½K</span><span>¾K</span><span>full</span>
          </div>
        </div>
        <div className="sw-ctrl">
          <div className="sw-ctrl-l">
            <span className="label-cap">Size multiplier</span>
            <span className="mono"><b className="copper">{sizeMult.toFixed(2)}×</b> of base 110 sh</span>
          </div>
          <input type="range" min="0.25" max="2.50" step="0.05" value={sizeMult}
                 onChange={e => onSizeMult(parseFloat(e.target.value))} className="sw-range" />
          <div className="sw-ticks mono dim2">
            <span>0.25×</span><span>1×</span><span>1.5×</span><span>2×</span><span>2.5×</span>
          </div>
        </div>
      </div>
      <div className="sw-out">
        <SwTile label="Shares"   value={sh}                              tone="copper" />
        <SwTile label="Notional" value={`$${notional.toLocaleString(undefined, {maximumFractionDigits:0})}`} tone="ink" />
        <SwTile label="% NAV"    value={`${navPct.toFixed(1)}%`}         tone={navPct > 10 ? "amb" : navPct > 7 ? "amb" : "gn"} sub="cap 10%" />
        <SwTile label="Max loss" value={`$${maxLoss.toFixed(0)}`}        tone="rd" sub={`${lossNavPct.toFixed(2)}% NAV`} />
        <SwTile label="R-mult"   value={`${(reward/risk).toFixed(2)}R`}  tone="copper" sub="T1 / risk" />
        <SwTile label="Expectancy"value={`+$${(reward * 0.617 - risk * 0.383).toFixed(0)} ·`} tone={navPct > 0 ? "gn" : "ink"} sub={`× ${sh} sh · Wilson WR`} />
      </div>
      <div className="sw-gates">
        <SwGate label="Max loss ≤ 0.75% NAV" v={lossNavPct.toFixed(2)+"%"} pass={lossNavPct <= 0.75} />
        <SwGate label="% NAV ≤ 10%"          v={navPct.toFixed(1)+"%"}    pass={navPct <= 10} />
        <SwGate label="R-mult ≥ 1.5"         v={(reward/risk).toFixed(2)+"R"} pass={(reward/risk) >= 1.5} />
        <SwGate label="Wilson LB ≥ 45%"      v="47.7%"                    pass={true} />
      </div>
    </div>
  );
}

function SwTile({ label, value, tone, sub }) {
  return (
    <div className={`sw-tile sw-tile--${tone}`}>
      <div className="sw-tile-l label-cap">{label}</div>
      <div className={`sw-tile-v mono kpi-tone--${tone}`}>{value}</div>
      {sub && <div className="sw-tile-s mono dim2">{sub}</div>}
    </div>
  );
}

function SwGate({ label, v, pass }) {
  return (
    <div className={`sw-gate ${pass ? "is-pass" : "is-fail"}`}>
      <span className="sw-gate-m mono">{pass ? "✓" : "✕"}</span>
      <span className="sw-gate-l mono">{label}</span>
      <span className={`sw-gate-v mono ${pass ? "up" : "dn"}`}>{v}</span>
    </div>
  );
}

// ─── §3 Decision Gates flow ────────────────────────────────────
function DecisionGates() {
  const stages = [
    { stage: "SETUP",      gates: ["Pattern conf ≥ 0.60", "Pivot defined", "ATR ≥ 0.5%"], pass: 3, of: 3 },
    { stage: "EDGE",       gates: ["Wilson LB ≥ 45%", "Regime-WR ≥ 50%", "Edge stable"], pass: 3, of: 3 },
    { stage: "RISK",       gates: ["Stop ≤ 0.75% NAV", "R-mult ≥ 1.5", "Correl-to-book ≤ 0.55"], pass: 3, of: 3 },
    { stage: "TIMING",     gates: ["RVOL ≥ 1.30×", "Time-of-day window", "ER not in T1 window"], pass: 2, of: 3, warn: true },
    { stage: "EXECUTION",  gates: ["Liquidity gate (spread, size)", "Venue ready", "OCO armed"], pass: 3, of: 3 },
  ];
  return (
    <div className="dg">
      {stages.map((s, i) => (
        <div key={i} className={`dg-stage ${s.warn ? "is-warn" : ""}`}>
          <div className="dg-stage-hdr">
            <span className="dg-stage-l mono">{s.stage}</span>
            <span className={`dg-stage-c mono ${s.pass === s.of ? "up" : "warn"}`}>{s.pass} / {s.of}</span>
          </div>
          {s.gates.map((g, j) => {
            const p = j < s.pass;
            return (
              <div key={j} className={`dg-gate ${p ? "is-pass" : "is-fail"}`}>
                <span className="dg-mark mono">{p ? "✓" : "!"}</span>
                <span className="dg-lbl mono">{g}</span>
              </div>
            );
          })}
        </div>
      ))}
      <div className="dg-foot mono dim2">
        <b className="up">14 of 15 gates pass · 1 caution (ER in window).</b>
        Trade is clear to fire with <b>25% size cut</b> applied.
      </div>
    </div>
  );
}

// ─── §4 Time Anatomy V2 ────────────────────────────────────────
function TimeAnatomyV2({ ticker }) {
  const totalSessions = ticker.holdDays + 4;
  const entry = ticker.pivot * 1.002;
  const events = [
    { t: -3, label: "Setup formed",            tone: "ink",    px: ticker.pivot * 0.96 },
    { t: -1, label: "Pivot tested · vol-dry", tone: "ink",    px: ticker.pivot },
    { t:  0, label: "ENTRY · breakout",       tone: "copper", big: true, px: entry },
    { t:  1, label: "Confirm close",          tone: "ink",    px: entry * 1.012 },
    { t:  Math.floor(ticker.holdDays * 0.35),  label: "T1 expected",   tone: "gn", px: ticker.t1 },
    { t:  Math.min(ticker.earnings.days, ticker.holdDays - 1), label: `ER · ${ticker.earnings.date}`, tone: "amb" },
    { t:  Math.floor(ticker.holdDays * 0.85),  label: "T2 expected",   tone: "gn", px: ticker.t2 },
    { t:  ticker.holdDays, label: "Time stop", tone: "rd", px: ticker.stop },
  ];
  return (
    <div className="time-anatomy">
      <div className="ta-meta mono dim2">
        Session 0 = entry · {totalSessions} sessions plotted · ER at T+{ticker.earnings.days}d
      </div>
      <div className="ta-ribbon">
        <div className="ta-track">
          <div className="ta-phase ta-phase--pre"  style={{ left: 0, width: `${(4/totalSessions)*100}%` }} />
          <div className="ta-phase ta-phase--hold" style={{ left: `${(4/totalSessions)*100}%`, width: `${(ticker.holdDays/totalSessions)*100}%` }} />
          {Array.from({ length: totalSessions + 1 }, (_, i) => (
            <div key={i} className={`ta-tick ${i === 4 ? "ta-tick-major" : ""}`}
                 style={{ left: `${(i/totalSessions)*100}%` }} />
          ))}
          {events.map((e, i) => {
            const x = ((e.t + 4) / totalSessions) * 100;
            return (
              <div key={i} className={`ta-event ta-event--${e.tone} ${e.big ? "is-big" : ""}`} style={{ left: `${x}%` }}>
                <div className="ta-event-stem" />
                <div className="ta-event-dot" />
                <div className={`ta-event-label mono ${i % 2 ? "ta-up" : "ta-dn"}`}>
                  {e.label}
                  {e.px != null && <span className="ta-event-px mono">${e.px.toFixed(2)}</span>}
                </div>
              </div>
            );
          })}
        </div>
        <div className="ta-axis mono">
          <span style={{ left: "0%" }}>T−4</span>
          <span style={{ left: `${(4/totalSessions)*100}%`, color: "var(--copper)" }}>ENTRY</span>
          <span style={{ left: `${((4 + Math.floor(ticker.holdDays/2))/totalSessions)*100}%` }}>T+{Math.floor(ticker.holdDays/2)}</span>
          <span style={{ left: "100%" }}>T+{ticker.holdDays}</span>
        </div>
      </div>
    </div>
  );
}

// ─── §5 Playbook IF/THEN tree ──────────────────────────────────
function PlaybookTree() {
  const branches = [
    { tag: "OPEN",  scenarios: [
      { cond: "Gap +3% on news",      then: "Skip · wait first 30m · re-validate pivot", tone: "amb" },
      { cond: "Gap −2% no news",      then: "Hold · first 15m candle is the read",        tone: "ink" },
      { cond: "VWAP reclaim by 11:00",then: "Add ¼ on consolidation > VWAP",                tone: "gn" },
    ]},
    { tag: "MID",   scenarios: [
      { cond: "Volume < 0.6× avg by 14:00", then: "Trim ¼ · distribution risk",              tone: "amb" },
      { cond: "T1 hit on +1.5× vol", then: "Sell ½ · trail rest with ATR×2.2",               tone: "gn"  },
      { cond: "Close strong + > +1R", then: "Trail stop to breakeven · raise next day",      tone: "gn"  },
    ]},
    { tag: "INVAL", scenarios: [
      { cond: "Pre-mortem #1 fires",  then: "OCO armed · no manual override",                tone: "rd" },
      { cond: "Sector ETF −5%",       then: "Reduce 50% · pause new entries",                tone: "amb" },
      { cond: "Hits hard stop",       then: "OCO auto-exit",                                  tone: "rd" },
    ]},
  ];
  return (
    <div className="pbk">
      {branches.map((b, i) => (
        <div key={i} className="pbk-branch">
          <div className="pbk-tag mono">{b.tag}</div>
          <div className="pbk-paths">
            {b.scenarios.map((s, j) => (
              <div key={j} className={`pbk-path pbk-${s.tone}`}>
                <span className="pbk-cond"><span className="mono dim2">IF</span> {s.cond}</span>
                <span className="pbk-arrow mono">→</span>
                <span className="pbk-then"><span className="mono dim2">THEN</span> {s.then}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── §6 Audit Log ──────────────────────────────────────────────
function AuditLog() {
  const items = [
    { phase: "PRE-FILL", item: "OCO bracket constructed · stop $62.40 + T1 $72.80 + T2 $78.20", done: true },
    { phase: "PRE-FILL", item: "Sizing approved · half-Kelly · 110 sh · 6.8% NAV",                done: true },
    { phase: "PRE-FILL", item: "Correlation-to-book check · 0.34 ≤ 0.55",                          done: true },
    { phase: "PRE-FILL", item: "Sleep-test · max-down $750 ≥ −$420",                               done: true },
    { phase: "PRE-FILL", item: "ER alert · T−2 reminder set for May 30",                            done: true },
    { phase: "FILL",     item: "Order acknowledged by Schwab · venue NSDQ · OCO IDs assigned",     done: false, sub: "awaits trigger" },
    { phase: "POST-FILL",item: "Position added to portfolio_state · risk recompute",                done: false },
    { phase: "POST-FILL",item: "Journal entry written · 1-paragraph thesis",                        done: false },
    { phase: "POST-FILL",item: "Alert wired · trail stop to breakeven at T+0.5R",                   done: false },
  ];
  return (
    <div className="al">
      {items.map((it, i) => (
        <div key={i} className={`al-row ${it.done ? "is-done" : ""}`}>
          <span className="al-check">{it.done ? "✓" : ""}</span>
          <span className={`al-phase mono al-phase--${it.phase.toLowerCase().replace("-", "")}`}>{it.phase}</span>
          <span className="al-text">{it.item}</span>
          {it.sub && <span className="al-sub mono dim2">{it.sub}</span>}
        </div>
      ))}
    </div>
  );
}

window.LensPlan = LensPlan;
