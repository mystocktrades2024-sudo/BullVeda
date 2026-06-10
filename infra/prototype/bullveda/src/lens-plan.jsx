// lens-plan.jsx — Plan · Ticket lens
// Order ticket, sizing cascade, price ladder, size explorer, invalidation ladder,
// TIME-ANATOMY RIBBON (timeline scaled to hold-period), reaction playbook, pre-mortem,
// post-fill checklist.

const { useState: usePL, useMemo: useMemoPL } = React;

// Re-rank stops/targets/hold per mode toggle.
function modeAdjust(ticker, mode) {
  // SSOT (2026-06-09): per-mode verdict binds the canonical engine call
  // (decisionsByMode), never a score-threshold recompute. NOTE: the stop/target
  // SCALING below is legacy synthesis — per-mode T1/T2/stop should come from
  // /api/trade_engine?mode= (tracked under OVERVIEW-VERDICT-RECON / per-mode
  // targets). Left as-is here to keep this change scoped to the verdict.
  if (mode === "POSITION") {
    return {
      ...ticker,
      stop: ticker.stop * 0.96,
      t1:   ticker.t1   * 1.10,
      t2:   ticker.t2   * 1.18,
      holdDays: 38,
      rMultiple: 2.21,
      score: Math.max(0, ticker.score - 3),
      verdict: (ticker.decisionsByMode && ticker.decisionsByMode.position && ticker.decisionsByMode.position.verdict) || ticker.verdict,
    };
  }
  if (mode === "INVESTMENT") {
    return {
      ...ticker,
      stop: ticker.stop * 0.84,
      t1:   ticker.t1   * 1.32,
      t2:   ticker.t2   * 1.58,
      holdDays: 180,
      rMultiple: 2.94,
      verdict: (ticker.decisionsByMode && ticker.decisionsByMode.investment && ticker.decisionsByMode.investment.verdict) || ticker.verdict,
    };
  }
  return ticker;
}

function LensPlan({ ticker: t0, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const ticker = useMemoPL(() => modeAdjust(t0, mode), [t0, mode]);
  const s1 = useStateToggle("pl-1");
  const s2 = useStateToggle("pl-2");
  const s3 = useStateToggle("pl-3");
  const s4 = useStateToggle("pl-4");
  const s5 = useStateToggle("pl-5");
  const s6 = useStateToggle("pl-6");
  const s7 = useStateToggle("pl-7");

  return (
    <div className="lens lens--plan">
      <PlanHero ticker={ticker} mode={mode} />

      {/* §1 — Order ticket */}
      <div className="lens-section">
        <SectionHeader n={1} title="Order Ticket"
          sub={`${mode} · risk-first · BUY-STOP LIMIT · OCO bracket`}
          style={headerStyle}
          right={<StateToggle name="pl-1" />}
        />
        <StateWrap state={s1.value} source="Schwab · order builder · paper">
          <div className="lens-pad">
            <OrderTicket ticker={ticker} mode={mode} />
          </div>
        </StateWrap>
      </div>

      {/* §2 — Sizing cascade waterfall */}
      <div className="lens-section">
        <SectionHeader n={2} title="Sizing Cascade · Waterfall"
          sub="half-Kelly × regime × VIX × DD × β × VaR × Sharpe"
          style={headerStyle}
          right={<StateToggle name="pl-2" />}
        />
        <StateWrap state={s2.value} source="risk engine · kelly + portfolio_state">
          <div className="lens-pad"><SizingWaterfall /></div>
        </StateWrap>
      </div>

      {/* §3 — Price ladder */}
      <div className="lens-section">
        <SectionHeader n={3} title="Price Ladder"
          sub="entry → trail → t1 → t2 · with daily ATR bands"
          style={headerStyle}
          right={<StateToggle name="pl-3" />}
        />
        <StateWrap state={s3.value} source="EODHD · intraday">
          <div className="lens-pad"><PriceLadder ticker={ticker} /></div>
        </StateWrap>
      </div>

      {/* §4 — Invalidation ladder */}
      <div className="lens-section">
        <SectionHeader n={4} title="Invalidation Ladder"
          sub="staged exits if the thesis cracks"
          style={headerStyle}
          right={<StateToggle name="pl-4" />}
        />
        <StateWrap state={s4.value} source="rules · cache/last_bundle.json">
          <div className="lens-pad"><InvalidationLadder ticker={ticker} /></div>
        </StateWrap>
      </div>

      {/* §5 — Time anatomy ribbon */}
      <div className="lens-section">
        <SectionHeader n={5} title="Time Anatomy"
          sub={`hold ~${ticker.holdDays}d · plotted in trading sessions`}
          style={headerStyle}
          right={<StateToggle name="pl-5" />}
        />
        <StateWrap state={s5.value} source="planner · setup_stats + calendar">
          <div className="lens-pad"><TimeAnatomy ticker={ticker} mode={mode} /></div>
        </StateWrap>
      </div>

      {/* §6 — Reaction playbook + Pre-mortem */}
      <div className="lens-section">
        <SectionHeader n={6} title="Reaction Playbook · Pre-Mortem"
          sub="if X happens → do Y · written before entry"
          style={headerStyle}
          right={<StateToggle name="pl-6" />}
        />
        <StateWrap state={s6.value} source="playbook · per-setup rules">
          <div className="lens-pad"><ReactionPlaybook /></div>
        </StateWrap>
      </div>

      {/* §7 — Post-fill checklist */}
      <div className="lens-section">
        <SectionHeader n={7} title="Post-Fill Checklist"
          sub="discipline gates that fire after the order is live"
          style={headerStyle}
          right={<StateToggle name="pl-7" />}
        />
        <StateWrap state={s7.value} source="rule engine · gate audit">
          <div className="lens-pad"><PostFillChecklist /></div>
        </StateWrap>
      </div>

      {/* Cross-lens strip */}
      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          <CrossLens
            lead="copper"
            cells={[
              { lens: "Plan",       verdict: "READY", tone: "gn", note: `R ${ticker.rMultiple.toFixed(2)} · half-Kelly` },
              { lens: "Technicals", verdict: "PASS",  tone: "gn", note: "RSI 64 · VWAP-reclaim" },
              { lens: "Risk",       verdict: "OK",    tone: "gn", note: "VaR(1d) −2.1%" },
              { lens: "Earnings",   verdict: "11 d",  tone: "amb",note: "size −25% pre-ER" },
              { lens: "Track Rec.", verdict: "EDGE",  tone: "gn", note: `n=${ticker.setupStats.n ?? "—"} · pf ${ticker.setupStats.pf != null ? ticker.setupStats.pf.toFixed(2) : "—"}` },
            ]}
          />
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · {mode}</span>
        <span className="mono">
          BUY-STOP LIMIT <b className="copper">${(ticker.pivot * 1.002).toFixed(2)}</b> ·
          stop <b className="dn">${ticker.stop.toFixed(2)}</b> ·
          T1 <b className="up">${ticker.t1.toFixed(2)}</b> ·
          {' '}max risk <b>$420</b> · {Math.round((420/(ticker.price*0.057))*ticker.price).toLocaleString()} notional.
        </span>
      </div>
    </div>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────
function PlanHero({ ticker, mode }) {
  const entry = ticker.pivot * 1.002;
  const risk = entry - ticker.stop;
  const reward1 = ticker.t1 - entry;
  return (
    <div className="hero plan-hero">
      <div className="plan-hero-strip">
        <div className="plan-hero-cell">
          <div className="label-cap">Action</div>
          <div className="plan-hero-value mono copper">BUY-STOP</div>
        </div>
        <div className="plan-hero-cell">
          <div className="label-cap">Entry</div>
          <div className="plan-hero-value mono">${entry.toFixed(2)}</div>
        </div>
        <div className="plan-hero-cell plan-hero-cell--rd">
          <div className="label-cap">Stop</div>
          <div className="plan-hero-value mono dn">${ticker.stop.toFixed(2)}</div>
          <div className="mono dim2">−${risk.toFixed(2)} · −{(risk/entry*100).toFixed(1)}%</div>
        </div>
        <div className="plan-hero-cell plan-hero-cell--gn">
          <div className="label-cap">T1 · T2</div>
          <div className="plan-hero-value mono up">${ticker.t1.toFixed(2)}</div>
          <div className="mono dim2">+${reward1.toFixed(2)} · {(reward1/risk).toFixed(2)}R · T2 ${ticker.t2.toFixed(2)}</div>
        </div>
        <div className="plan-hero-cell">
          <div className="label-cap">Size</div>
          <div className="plan-hero-value mono">110 sh</div>
          <div className="mono dim2">$7,416 · 6.8% of NAV</div>
        </div>
        <div className="plan-hero-cell">
          <div className="label-cap">Max loss</div>
          <div className="plan-hero-value mono dn">$420</div>
          <div className="mono dim2">0.39% of NAV</div>
        </div>
      </div>
    </div>
  );
}

// ─── §1 Order ticket ──────────────────────────────────────────────
function OrderTicket({ ticker, mode }) {
  return (
    <div className="ticket">
      <div className="ticket-grid">
        <Field label="Action" value={<span className="copper mono">BUY</span>} />
        <Field label="Symbol" value={<span className="mono"><b>{ticker.symbol}</b></span>} />
        <Field label="Order Type" value={<span className="mono">STOP LIMIT</span>} />
        <Field label="TIF" value={<span className="mono">GTC · ext-hrs OFF</span>} />
        <Field label="Stop trigger" value={<span className="mono copper">${ticker.pivot.toFixed(2)}</span>} />
        <Field label="Limit" value={<span className="mono">${(ticker.pivot * 1.004).toFixed(2)}</span>} />
        <Field label="Qty" value={<span className="mono">110 sh</span>} />
        <Field label="Notional" value={<span className="mono">$7,416</span>} />
        <Field label="Stop loss" value={<span className="mono dn">${ticker.stop.toFixed(2)} (HARD)</span>} />
        <Field label="$ Risk" value={<span className="mono dn">$420 · 0.39% NAV</span>} />
        <Field label="T1 (½ off)" value={<span className="mono up">${ticker.t1.toFixed(2)} → trail rest</span>} />
        <Field label="T2 (full)" value={<span className="mono up">${ticker.t2.toFixed(2)}</span>} />
        <Field label="Trail" value={<span className="mono">{ticker.trail} · after T1</span>} />
        <Field label="Time stop" value={<span className="mono">{ticker.holdDays}d · close if &lt; entry +0.5R</span>} />
      </div>
      <div className="ticket-rail">
        <div className="ticket-rail-row">
          <span className="label-cap">P&L profile</span>
          <span className="mono dim2">linear · no options</span>
        </div>
        <PayoffMini ticker={ticker} />
        <div className="ticket-actions">
          <button className="btn btn--primary">PLACE BRACKET</button>
          <button className="btn">SAVE PLAN</button>
          <button className="btn">DRY-RUN</button>
        </div>
        <div className="ticket-gates">
          <GateRow label="R:R ≥ 1.5" pass />
          <GateRow label="Stop ≤ 0.75% NAV" pass />
          <GateRow label="Wilson LB ≥ 45%" pass note="47.7%" />
          <GateRow label="Correl-to-book ≤ 0.55" pass note="0.31" />
          <GateRow label="ER not in T1 window" warn note={`ER in ${ticker.earnings.days}d`} />
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="field">
      <div className="field-label label-cap">{label}</div>
      <div className="field-value">{value}</div>
    </div>
  );
}

function GateRow({ label, pass, warn, fail, note }) {
  const tone = fail ? "rd" : warn ? "amb" : pass ? "gn" : "ink";
  const mark = fail ? "✕" : warn ? "!" : "✓";
  return (
    <div className={`gate gate--${tone}`}>
      <span className="gate-mark mono">{mark}</span>
      <span className="gate-label mono">{label}</span>
      {note && <span className="gate-note mono dim2">{note}</span>}
    </div>
  );
}

function PayoffMini({ ticker }) {
  const entry = ticker.pivot * 1.002;
  const stop = ticker.stop;
  const t1 = ticker.t1;
  const t2 = ticker.t2;
  const qty = 110;
  const w = 460, h = 160, padT = 20, padB = 30, padL = 20, padR = 50;
  const innerH = h - padT - padB;
  const minPx = stop - 1, maxPx = t2 + 1;
  const x = (p) => padL + ((p - minPx) / (maxPx - minPx)) * (w - padL - padR);
  // P&L $ at price p — bracketed bull stock: stop loss locked, T2 capped (assume full exit at T2)
  const pnlAt = (p) => Math.max(stop - entry, Math.min(t2 - entry, p - entry)) * qty;
  const maxLoss = (stop - entry) * qty;
  const maxGain = (t2 - entry) * qty;
  const pnlMin = maxLoss * 1.15;
  const pnlMax = maxGain * 1.15;
  const y = (pnl) => padT + innerH - ((pnl - pnlMin) / (pnlMax - pnlMin)) * innerH;
  const y0 = y(0);

  // payoff polyline samples
  const samples = [];
  for (let p = minPx; p <= maxPx; p += 0.25) samples.push([x(p), y(pnlAt(p))]);

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet"
         className="payoff-mini" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="po-gn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stopColor="var(--gn)" stopOpacity="0.36" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="po-rd" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%"  stopColor="var(--rd)" stopOpacity="0.36" />
          <stop offset="100%" stopColor="var(--rd)" stopOpacity="0.02" />
        </linearGradient>
        <clipPath id="po-clip-gn"><rect x="0" y="0" width={w} height={y0} /></clipPath>
        <clipPath id="po-clip-rd"><rect x="0" y={y0} width={w} height={h - y0} /></clipPath>
      </defs>

      {/* Grid lines */}
      <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--glass-line)" />
      <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--glass-line)" />
      <line x1={padL} y1={y0} x2={w - padR} y2={y0} stroke="var(--ink-3)" strokeDasharray="3 3" opacity="0.5" />
      <text x={w - padR + 6} y={y0 + 3} fontSize="9" fill="var(--ink-3)" className="mono">$0</text>

      {/* Filled regions — green above 0, red below 0 */}
      <g clipPath="url(#po-clip-gn)">
        <path d={`M ${padL} ${y0} L ${samples.map(s => s.join(",")).join(" L ")} L ${w - padR} ${y0} Z`} fill="url(#po-gn)" />
      </g>
      <g clipPath="url(#po-clip-rd)">
        <path d={`M ${padL} ${y0} L ${samples.map(s => s.join(",")).join(" L ")} L ${w - padR} ${y0} Z`} fill="url(#po-rd)" />
      </g>

      {/* Vertical guides at stop/entry/t1/t2 */}
      {[[stop, "var(--rd)"], [entry, "var(--copper)"], [t1, "var(--gn-dim)"], [t2, "var(--gn)"]].map(([p, c], i) => (
        <line key={i} x1={x(p)} y1={padT - 4} x2={x(p)} y2={h - padB} stroke={c} strokeDasharray={i === 1 ? "0" : "3 3"} opacity="0.5" />
      ))}

      {/* Entry vertical glow */}
      <line x1={x(entry)} y1={padT - 4} x2={x(entry)} y2={h - padB}
            stroke="var(--copper)" strokeWidth="1.4"
            style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />

      {/* Payoff line */}
      <polyline points={samples.map(s => s.join(",")).join(" ")}
                stroke="var(--ink)" strokeWidth="2" fill="none" strokeLinejoin="round"
                style={{ filter: "drop-shadow(0 0 6px color-mix(in oklab, var(--copper) 50%, transparent))" }} />

      {/* Anchor dots */}
      <circle cx={x(stop)} cy={y(pnlAt(stop))} r="4" fill="var(--rd)"
              style={{ filter: "drop-shadow(0 0 8px var(--rd))" }} />
      <circle cx={x(entry)} cy={y(0)} r="4" fill="var(--copper)"
              style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <circle cx={x(t1)} cy={y(pnlAt(t1))} r="3.5" fill="var(--gn)"
              style={{ filter: "drop-shadow(0 0 7px var(--gn))" }} />
      <circle cx={x(t2)} cy={y(pnlAt(t2))} r="4" fill="var(--gn)"
              style={{ filter: "drop-shadow(0 0 8px var(--gn))" }} />

      {/* Pill callouts above */}
      <PayoffCallout x={x(stop)} y={padT - 4} px={stop} pnl={pnlAt(stop)} tone="rd" anchor="middle" label="STOP" />
      <PayoffCallout x={x(entry)} y={padT - 4} px={entry} pnl={0} tone="copper" anchor="middle" label="ENTRY" />
      <PayoffCallout x={x(t1)} y={padT - 4} px={t1} pnl={pnlAt(t1)} tone="gn" anchor="middle" label="T1" />
      <PayoffCallout x={x(t2)} y={padT - 4} px={t2} pnl={pnlAt(t2)} tone="gn" anchor="middle" label="T2" />

      {/* Bottom price axis labels */}
      {[stop, entry, t1, t2].map((p, i) => (
        <text key={i} x={x(p)} y={h - padB + 14} fontSize="9.5" className="mono"
              textAnchor="middle" fill="var(--ink-3)" fontFeatureSettings='"tnum"'>${p.toFixed(2)}</text>
      ))}

      {/* Right $ P&L axis labels */}
      <text x={w - padR + 6} y={y(maxGain) + 3} fontSize="9.5" className="mono" fill="var(--gn)">+${maxGain.toFixed(0)}</text>
      <text x={w - padR + 6} y={y(maxLoss) + 3} fontSize="9.5" className="mono" fill="var(--rd)">−${Math.abs(maxLoss).toFixed(0)}</text>

      {/* R-multiple annotation */}
      <text x={padL} y={padT - 6} fontSize="9.5" className="mono" fill="var(--ink-3)" letterSpacing="0.10em">
        P/L · 110 sh · BRACKET TO T2
      </text>
    </svg>
  );
}

function PayoffCallout({ x, y, px, pnl, tone, label }) {
  const color = `var(--${tone})`;
  return (
    <g transform={`translate(${x}, ${y - 18})`}>
      <rect x="-22" y="-12" width="44" height="14" rx="7" fill="color-mix(in oklab, var(--bg-1) 70%, transparent)"
            stroke={color} strokeWidth="0.8" />
      <text x="0" y="-2" fontSize="8.5" className="mono" textAnchor="middle" fill={color} letterSpacing="0.10em">
        {label}
      </text>
    </g>
  );
}

// ─── §2 Sizing cascade waterfall ─────────────────────────────────────
function SizingWaterfall() {
  const steps = [
    { label: "Raw Kelly",       v: 0.84, note: "(p·b − q) / b" },
    { label: "× ½ Kelly",       v: 0.42, note: "discipline cap" },
    { label: "× Regime",        v: 0.36, note: "QQQ > 50dma · 0.86" },
    { label: "× VIX scalar",    v: 0.30, note: "VIX 17.4 · 0.84" },
    { label: "× DD throttle",   v: 0.28, note: "DD −2.1% · 0.94" },
    { label: "× β-net cap",     v: 0.25, note: "book β 0.93 · 0.88" },
    { label: "× VaR floor",     v: 0.23, note: "VaR(1d) −2.1% · 0.92" },
    { label: "× Sharpe trim",   v: 0.21, note: "rolling 0.84 · 0.91" },
    { label: "Final size %",    v: 0.068, note: "of NAV", final: true },
  ];
  const max = Math.max(...steps.map(s => s.v));
  return (
    <div className="waterfall">
      {steps.map((s, i) => {
        const pct = (s.v / max) * 100;
        return (
          <div key={s.label} className={`wf-row ${s.final ? "wf-final" : ""}`}>
            <span className="wf-label mono">{s.label}</span>
            <div className="wf-bar">
              <div className="wf-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="wf-v mono">{(s.v * 100).toFixed(s.final ? 2 : 1)}%</span>
            <span className="wf-note mono dim2">{s.note}</span>
          </div>
        );
      })}
      <div className="wf-tail mono dim2">
        ⤷ 6.80% of $108,420 = $7,373 notional → <b className="copper">110 shares</b> @ ${(67.42).toFixed(2)}
      </div>
    </div>
  );
}

// ─── §3 Price ladder ─────────────────────────────────────────────────
function PriceLadder({ ticker }) {
  const levels = [
    { label: "T2 target",   px: ticker.t2,   tone: "gn",   note: "+16% · take full" },
    { label: "T1 target",   px: ticker.t1,   tone: "gn",   note: "+8.0% · half off, trail rest" },
    { label: "+1 ATR",      px: ticker.price + 2.4, tone: "ink", note: "extension band" },
    { label: "Current",     px: ticker.price, tone: "copper", note: "VWAP $66.81" },
    { label: "Entry stop",  px: ticker.pivot, tone: "copper", note: "pivot of base #2" },
    { label: "−1 ATR",      px: ticker.price - 2.4, tone: "ink", note: "support band" },
    { label: "50-DMA",      px: 64.10, tone: "ink", note: "rising" },
    { label: "Hard stop",   px: ticker.stop, tone: "rd", note: "−5.7% · invalidate" },
    { label: "200-DMA",     px: 58.40, tone: "ink", note: "well below" },
  ];
  return (
    <div className="ladder">
      {levels.map((l, i) => (
        <div key={i} className={`ladder-row ladder-${l.tone}`}>
          <span className="ladder-label mono dim2">{l.label}</span>
          <div className="ladder-bar"><div className="ladder-tick" /></div>
          <span className={`ladder-px mono kpi-tone--${l.tone}`}>${l.px.toFixed(2)}</span>
          <span className="ladder-note mono dim">{l.note}</span>
        </div>
      ))}
    </div>
  );
}

// ─── §4 Invalidation ladder ──────────────────────────────────────────
function InvalidationLadder({ ticker }) {
  const rows = [
    { trig: "VWAP fail intraday + close < $66.40", action: "Cut 50%", tone: "amb" },
    { trig: "Close < entry on +1.5σ volume", action: "Cut to 25%", tone: "amb" },
    { trig: "Close < $65.10 (BO retest fails)", action: "Exit balance", tone: "rd" },
    { trig: "Hits hard stop $62.40", action: "OCO auto-exit", tone: "rd" },
    { trig: "Sector ETF XLB < 50-DMA on vol", action: "Reduce 50% · pause new", tone: "amb" },
    { trig: "Time stop: < +0.5R after 8 sessions", action: "Flatten · re-evaluate", tone: "ink" },
  ];
  return (
    <div className="inv-ladder">
      {rows.map((r, i) => (
        <div key={i} className={`inv-row inv-${r.tone}`}>
          <span className="inv-num mono">{String(i + 1).padStart(2, "0")}</span>
          <span className="inv-trig mono">{r.trig}</span>
          <Pill tone={r.tone} small>{r.action}</Pill>
        </div>
      ))}
    </div>
  );
}

// ─── §5 Time anatomy ribbon ──────────────────────────────────────────
function TimeAnatomy({ ticker, mode }) {
  // Sessions ribbon: pre-entry (0..−3) | entry day | hold | t1 expected | t2 expected | ER (if in window) | time stop
  const totalSessions = ticker.holdDays + 4;
  const events = [
    { t: -3, label: "Setup formed", tone: "ink" },
    { t: -1, label: "Pivot tested · vol-dry", tone: "ink" },
    { t:  0, label: "Entry · breakout", tone: "copper", big: true },
    { t:  1, label: "Confirmation close", tone: "ink" },
    { t:  Math.floor(ticker.holdDays * 0.35), label: "T1 expected (med-R day)", tone: "gn" },
    { t:  Math.min(ticker.earnings.days, ticker.holdDays - 1), label: `ER · ${ticker.earnings.date}`, tone: "amb" },
    { t:  Math.floor(ticker.holdDays * 0.85), label: "T2 expected", tone: "gn" },
    { t:  ticker.holdDays, label: "Time stop", tone: "rd" },
  ];
  return (
    <div className="time-anatomy">
      <div className="ta-meta mono dim2">
        Session 0 = entry day · {totalSessions} sessions plotted · width scales to hold
      </div>
      <div className="ta-ribbon">
        {/* base ribbon */}
        <div className="ta-track">
          {/* phase backgrounds */}
          <div className="ta-phase ta-phase--pre"    style={{ left: 0, width: `${(4/totalSessions)*100}%` }} />
          <div className="ta-phase ta-phase--hold"   style={{ left: `${(4/totalSessions)*100}%`, width: `${(ticker.holdDays/totalSessions)*100}%` }} />
          {/* tick marks (sessions) */}
          {Array.from({ length: totalSessions + 1 }, (_, i) => (
            <div key={i} className={`ta-tick ${i === 4 ? "ta-tick-major" : ""}`}
                 style={{ left: `${(i/totalSessions)*100}%` }} />
          ))}
          {/* events */}
          {events.map((e, i) => {
            const x = ((e.t + 4) / totalSessions) * 100;
            return (
              <div key={i} className={`ta-event ta-event--${e.tone} ${e.big ? "is-big" : ""}`}
                   style={{ left: `${x}%` }}>
                <div className="ta-event-stem" />
                <div className="ta-event-dot" />
                <div className={`ta-event-label mono ${i % 2 ? "ta-up" : "ta-dn"}`}>{e.label}</div>
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
      <div className="ta-legend mono">
        <span><span className="ta-leg-sw ta-leg--pre" /> pre-entry</span>
        <span><span className="ta-leg-sw ta-leg--hold" /> hold window</span>
        <span><span className="ta-leg-sw ta-leg--er" /> earnings risk</span>
      </div>
    </div>
  );
}

// ─── §6 Reaction playbook ────────────────────────────────────────────
function ReactionPlaybook() {
  const rows = [
    { if_: "Gap +3% at open on news", then: "Skip — wait first 30m, re-validate pivot.", tone: "amb" },
    { if_: "Gap −2% on no news",      then: "Hold — first 15m candle is the read.",       tone: "ink" },
    { if_: "VWAP reclaim by 11:00",   then: "Add ¼ on consolidation > VWAP.",              tone: "gn"  },
    { if_: "Volume < 0.6× avg by 14:00", then: "Trim ¼ — distribution risk.",              tone: "amb" },
    { if_: "Close strong + > +1R",    then: "Trail stop to breakeven.",                   tone: "gn"  },
    { if_: "Pre-mortem #1 fires",     then: "OCO already armed — no manual override.",    tone: "rd"  },
  ];
  return (
    <div className="play">
      {rows.map((r, i) => (
        <div key={i} className={`play-row play-${r.tone}`}>
          <span className="play-tag mono">IF</span>
          <span className="play-if">{r.if_}</span>
          <span className="play-arrow mono">→</span>
          <span className="play-tag mono">THEN</span>
          <span className="play-then">{r.then}</span>
        </div>
      ))}
    </div>
  );
}

// ─── §7 Post-fill checklist ──────────────────────────────────────────
function PostFillChecklist() {
  const items = [
    { label: "OCO bracket sent (stop + T1 + T2)", done: true },
    { label: "Position added to portfolio_state", done: true },
    { label: "Correlation-to-book ≤ 0.55 after fill", done: true, note: "0.34" },
    { label: "Sleep-test: max-down today < $750", done: true, note: "−$420 max" },
    { label: "Alert: ER reminder T−2 sessions", done: true },
    { label: "Journal entry written (1-paragraph thesis)", done: false },
  ];
  return (
    <div className="checklist">
      {items.map((it, i) => (
        <div key={i} className={`check-row ${it.done ? "is-done" : ""}`}>
          <span className="check-box">{it.done ? "✓" : ""}</span>
          <span className="check-label">{it.label}</span>
          {it.note && <span className="check-note mono dim2">{it.note}</span>}
        </div>
      ))}
    </div>
  );
}

window.LensPlan = LensPlan;
window.Field = Field;
window.PayoffCallout = PayoffCallout;
