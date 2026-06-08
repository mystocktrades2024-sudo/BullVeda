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

  // ── single source of truth — every level/size/R:R below reads from here ──
  const [navTick, setNavTick] = useStateP2(0);   // bump to re-read per-user NAV after a self-select edit
  const pm = useMemoP2(() => planMath(ticker), [ticker, navTick]);
  const size = useMemoP2(() => planSize(pm, sizeMult, kellyFrac), [pm, sizeMult, kellyFrac]);
  const editNav = () => {
    try {
      const cur = window.getAccountNav ? window.getAccountNav().nav : 100000;
      const v = window.prompt("Your account size ($) — sizing scales to this:", String(Math.round(cur)));
      if (v != null && +v > 0 && window.setAccountNav) { window.setAccountNav(+v); setNavTick(n => n + 1); }
    } catch (e) {}
  };
  const fillLive = (typeof pm.spread === "number" && pm.spread > 0) && (typeof pm.dvol === "number" && pm.dvol > 0);

  if (!pm.levelsValid) {
    return (
      <div className="lens lens--plan2">
        <div className="lens-section"><div className="lens-pad">
          <div className="fr-read mono dim2" style={{ padding: "18px 16px" }}>
            <b className="warn">No coherent trade plan for {ticker.symbol} in {mode} mode.</b> This name
            isn't in today's scan with a valid stop/entry/T1/T2 ladder (stop&nbsp;&lt;&nbsp;entry&nbsp;&lt;&nbsp;T1&nbsp;&lt;&nbsp;T2),
            so the ticket, sizing and payoff geometry can't be computed without fabricating levels.
            Run a scan that surfaces it, or use the Chart / Patterns lens for structure.
          </div>
        </div></div>
      </div>
    );
  }

  return (
    <div className="lens lens--plan2">
      <PlanActionPanel pm={pm} size={size} mode={mode} sym={ticker.symbol} family={ticker.setupFamily} />

      <div className="lens-section">
        <SectionHeader title="Why / Why Not · the case for &amp; against" style="minimal"
          sub="real factors pro &amp; con · pre-mortem before you commit" />
        <div className="lens-pad"><WhyWhyNot pm={pm} size={size} ticker={ticker} mode={mode} /></div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Trade Blueprint"
          sub="payoff geometry · stop / entry / T1 / T2 · R-multiples (size-independent)"
          style={headerStyle} right={<StateToggle name="plv2-1" />} />
        <StateWrap state={s1.value} source="Schwab quotes · ATR est (stop÷1.25)">
          <div className="lens-pad">
            <TradeBlueprint pm={pm} size={size} />
            {mode !== "SWING" && (
              <div className="tbv2-note mono dim2">
                {ticker._modeReal
                  ? <>Stop &amp; horizon are <b className="copper">{mode === "POSITION" ? "position" : "investment"}</b>-specific{ticker.stopBasis ? ` (${ticker.stopBasis})` : ""} from the engine. Targets are the shared structural ladder — horizon-scaled targets arrive with the structural-target engine.</>
                  : <>No {mode.toLowerCase()}-specific decision in this scan — showing the swing ladder with a {mode.toLowerCase()} horizon (targets not fabricated).</>}
              </div>
            )}
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Sizing Workbench · live"
          sub="adjust Kelly fraction + size multiplier · shares, $ risk, NAV% recompute live"
          style={headerStyle} right={<StateToggle name="plv2-2" />} />
        <StateWrap state={s2.value} source="risk engine · portfolio_state">
          <div className="lens-pad">
            <SizingWorkbench
              pm={pm} size={size} onEditNav={editNav}
              sizeMult={sizeMult} onSizeMult={setSizeMult}
              kellyFrac={kellyFrac} onKellyFrac={setKellyFrac}
            />
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Decision Gates · go/no-go"
          sub="the full pre-trade audit — size caps recompute in §2"
          style={headerStyle} right={<StateToggle name="plv2-3" />} />
        <StateWrap state={s3.value} source="rule engine · live gates">
          <div className="lens-pad"><DecisionGates pm={pm} size={size} ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title={`Fill Realism · ${fillLive ? "live fills" : "modeled fills"}`}
          sub={fillLive
            ? "what you'd realistically fill at — next-bar open + live spread + ADV-scaled slippage"
            : "what you'd likely fill at — next-bar open + spread + slippage (modeled from β; live spread/ADV unavailable)"}
          style={headerStyle} />
        <div className="lens-pad"><FillRealism pm={pm} size={size} /></div>
      </div>

      <div className="lens-2col plan-2col">
      <div className="lens-section">
        <SectionHeader n={5} title="Time Anatomy"
          sub={`hold ${ticker.holdLabel ? ticker.holdLabel : "~" + ticker.holdDays + "d"} · sessions plotted to scale`}
          style={headerStyle} right={<StateToggle name="plv2-4" />} />
        <StateWrap state={s4.value} source="planner · setup_stats + calendar">
          <div className="lens-pad"><TimeAnatomyV2 ticker={ticker} pm={pm} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Conditional Playbook · IF/THEN tree"
          sub={`pre-decided reactions for a ${mode === "POSITION" ? "1–6 month position" : mode === "INVESTMENT" ? "multi-year holding" : "2–15 day swing"} — tied to your ladder`}
          style={headerStyle} right={<StateToggle name="plv2-5" />} />
        <StateWrap state={s5.value} source={`playbook · ${mode.toLowerCase()} horizon rules`}>
          <div className="lens-pad"><PlaybookTree mode={mode} pm={pm} /></div>
        </StateWrap>
      </div>
      </div>

      <div className="lens-2col plan-2col">
      <div className="lens-section">
        <SectionHeader n={7} title="Audit · pre-fill + post-fill"
          sub="every decision logged · the system is the discipline"
          style={headerStyle} right={<StateToggle name="plv2-6" />} />
        <StateWrap state={s6.value} source="rule engine · audit log">
          <div className="lens-pad"><AuditLog pm={pm} size={size} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          {(() => {
            const px = ticker.pillars || {};
            const tech = px.technical != null ? px.technical : null;
            const erD = ticker.earnings && ticker.earnings.days != null ? ticker.earnings.days : null;
            const t1Days = Math.max(1, Math.floor((pm.holdDays || 10) * 0.35));
            const ss = ticker.setupStats || {};
            const planReady = pm.rr1 >= 1.5 && size.lossNavPct <= 0.75 && size.navPct <= 10 && (pm.kelly == null || pm.kelly > 0);
            return <CrossLens lead="copper" cells={[
              { lens: "Plan",       verdict: planReady ? "READY" : "REVIEW", tone: planReady ? "gn" : "amb",
                note: `R ${pm.rr1.toFixed(2)} · ${pm.kelly != null ? (pm.kelly * 100).toFixed(0) + "% Kelly" : "no ledger edge"}` },
              { lens: "Technicals", verdict: tech == null ? "—" : tech >= 60 ? "STRONG" : tech >= 45 ? "OK" : "WEAK",
                tone: tech == null ? "amb" : tech >= 60 ? "gn" : tech >= 45 ? "amb" : "rd",
                note: tech == null ? "no pillar data" : `tech pillar ${Math.round(tech)}` },
              { lens: "Risk",       verdict: size.lossNavPct <= 0.75 ? "OK" : "HOT", tone: size.lossNavPct <= 0.75 ? "gn" : "rd",
                note: `max loss ${size.lossNavPct.toFixed(2)}% NAV` },
              { lens: "Earnings",   verdict: erD == null ? "—" : `T+${erD}d`, tone: "amb",
                note: erD == null ? "no ER date" : erD <= t1Days ? "inside T1 window" : "clear of T1" },
              { lens: "Track Rec.", verdict: ss.n == null ? "—" : "EDGE", tone: ss.n == null ? "amb" : "gn",
                note: `n=${ss.n ?? "—"} · pf ${ss.pf != null ? ss.pf.toFixed(2) : "—"}` },
            ]} />;
          })()}
        </div>
      </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · {mode}</span>
        <span className="mono">
          BUY-STOP LIMIT <b className="copper">${pm.entry.toFixed(2)}</b> ·
          stop <b className="dn">${pm.stop.toFixed(2)}</b> · T1 <b className="up">${pm.t1.toFixed(2)}</b> ·
          {' '}{size.sh} sh · max risk <b>${Math.round(size.maxLoss)}</b> · {size.navPct.toFixed(1)}% NAV · <b className={pm.rr1 >= 2 ? "up" : "warn"}>{pm.rr1.toFixed(2)}R</b> to T1.
        </span>
      </div>
    </div>
  );
}

// POSITION / INVESTMENT levels come from the engine's real per-mode decision
// (decisions_by_mode: mode-specific stop basis 1.25×/1.75× ATR / −15% DD + horizon).
// SWING is the base ladder. We NO LONGER fabricate targets by constant multipliers;
// if the engine has no per-mode decision we keep the swing ladder (honest) and only
// change the plotted horizon. (Targets aren't horizon-scaled until the structural-
// target engine ships — see _modeReal note in §1.)
function modeAdjustP2(ticker, mode) {
  if (mode !== "POSITION" && mode !== "INVESTMENT") return ticker;
  const nz = (v, f) => (typeof v === "number" && isFinite(v)) ? v : f;
  const holdPlot = mode === "POSITION" ? 45 : 120;     // plottable horizon for the §5 ribbon
  const dm = ticker.decisionsByMode || null;
  const md = dm ? (dm[mode.toLowerCase()] || dm[mode]) : null;
  if (md && typeof md === "object") {
    return { ...ticker,
      stop: nz(md.stop, ticker.stop),
      t1: nz(md.t1, ticker.t1),
      t2: nz(md.t2, ticker.t2),
      pivot: nz(md.entry_mid, ticker.pivot),
      holdDays: holdPlot,
      holdLabel: ((md.rulebook || "").split("·")[1] || "").trim() || null,
      stopBasis: md.stop_basis || null,
      _modeReal: true,
    };
  }
  return { ...ticker, holdDays: holdPlot, _modeReal: false };   // no per-mode decision → no fabricated targets
}
window.modeAdjust = modeAdjustP2;

// ── planMath — ONE source of truth for levels, geometry, base sizing ──
// Reads coherentLevels (same as Overview), so the Plan tab can never drift
// from the chart/ladder. All $ figures derive from a fixed risk budget.
function planMath(t) {
  const L = window.coherentLevels ? window.coherentLevels(t) : { price: t.price, pivot: t.pivot, stop: t.stop, t1: t.t1, t2: t.t2 };
  const entry = +(L.pivot * 1.002).toFixed(2);          // BUY-STOP just over the pivot
  const risk = Math.max(0.01, entry - L.stop);
  const rr1 = (L.t1 - entry) / risk;
  const rr2 = (L.t2 - entry) / risk;
  // per-user NAV from the single shared source (#2/#3) — never the owner's account
  const _nv = window.getAccountNav ? window.getAccountNav() : { nav: 100000, source: "demo" };
  const PLAN_NAV = _nv.nav, navDemo = _nv.source !== "user";
  const riskBudget = Math.round(PLAN_NAV * 0.0039);     // 0.39% NAV per trade
  const baseShares = Math.max(1, Math.round(riskBudget / risk));
  const ss = t.setupStats || {};
  // never fabricate edge — null when the setup has no ledger history (n<1)
  const wr = (ss.winRate != null) ? ss.winRate : null;
  const lb = (ss.wilsonLB != null) ? ss.wilsonLB : null;
  const evR = (wr != null) ? wr * rr1 - (1 - wr) : null;            // expectancy in R (real WR only)
  const kelly = (wr != null && rr1 > 0) ? Math.max(0, (wr * rr1 - (1 - wr)) / rr1) : null; // raw Kelly f*
  const atr = +(risk / 1.25).toFixed(2);                 // ATR est: system stop = 1.25×ATR ⇒ ATR ≈ risk/1.25
  const levelsValid = (L.valid !== false) && L.stop > 0 && entry > L.stop && L.t1 > entry && L.t2 > L.t1;
  return { symbol: t.symbol, price: L.price, entry, stop: L.stop, t1: L.t1, t2: L.t2,
           risk, rr1, rr2, NAV: PLAN_NAV, navDemo, riskBudget, baseShares, wr, lb, evR, kelly, atr, levelsValid,
           spread: t.spread, dvol: t.dvol, beta: t.beta, sector: t.sector,
           holdDays: t.holdDays, earnings: t.earnings || { days: null, date: "" }, setupStats: ss };
}
// live sizing — scales base shares by the workbench sliders
function planSize(pm, sizeMult, kellyFrac) {
  const sh = Math.max(1, Math.round(pm.baseShares * (sizeMult || 1) * ((kellyFrac || 0.5) / 0.5)));
  const notional = sh * pm.entry;
  const maxLoss = sh * pm.risk;
  return { sh, notional, navPct: notional / pm.NAV * 100, maxLoss, lossNavPct: maxLoss / pm.NAV * 100,
           t1Gain: sh * (pm.t1 - pm.entry), t2Gain: sh * (pm.t2 - pm.entry) };
}
window.planMath = planMath; window.planSize = planSize;

// ─── Fill Realism — modeled fills (next-bar open + spread + slippage placeholder)
function FillRealism({ pm, size }) {
  const shares = size.sh;
  const signal = pm.entry;                              // the price the plan shows
  // Real frictions from live spread % + ADV participation + beta (square-root impact).
  const spreadPct = (typeof pm.spread === "number" && pm.spread > 0) ? pm.spread : null;
  const dvol = (typeof pm.dvol === "number" && pm.dvol > 0) ? pm.dvol : null;
  const beta = (typeof pm.beta === "number" && pm.beta > 0) ? pm.beta : 1.0;
  const real = spreadPct != null && dvol != null;
  const participationPct = dvol != null ? (size.notional / dvol) * 100 : 0.02;  // % of daily $-vol
  const spreadBps = spreadPct != null ? Math.max(1, Math.round(spreadPct * 50)) : 4;  // half-spread
  const slipBps = Math.max(1, Math.round(10 * Math.sqrt(Math.max(participationPct, 0.0001))));  // √-impact
  const gapBps = Math.max(2, Math.round(beta * 3));     // next-bar open drift, scales with beta
  const nextOpen = signal * (1 + gapBps / 1e4);
  const halfSpread = signal * spreadBps / 1e4;
  const slip = signal * slipBps / 1e4;
  const fill = +(nextOpen + halfSpread + slip).toFixed(2);
  const slipCost = Math.round((fill - signal) * shares);
  const slipPct = (fill / signal - 1) * 100;
  const stop = pm.stop;
  const stopGapBps = Math.max(4, Math.round(beta * 6)); // stops gap worse on adverse moves, scales with beta
  const stopFill = +(stop * (1 - stopGapBps / 1e4)).toFixed(2);
  const stopExtra = Math.round((stop - stopFill) * shares);
  const t1 = pm.t1;
  const rrIdeal = (t1 - signal) / (signal - stop);
  const rrReal = (t1 - fill) / (fill - stopFill);
  const rtCost = slipCost + Math.round((halfSpread + slip * 0.6) * shares);  // round-trip friction
  const steps = [
    { l: "Signal", v: `$${signal.toFixed(2)}`, s: "plan price", tone: "ink" },
    { l: "Next-bar open", v: `+${gapBps}bp`, s: "stop-buy triggers", tone: "amb", add: true },
    { l: "½ spread", v: `+${spreadBps}bp`, s: "pay the offer", tone: "amb", add: true },
    { l: "Slippage", v: `+${slipBps}bp`, s: "market impact", tone: "amb", add: true },
    { l: "Realistic fill", v: `$${fill.toFixed(2)}`, s: `${slipPct >= 0 ? "+" : ""}${slipPct.toFixed(2)}%`, tone: "rd", strong: true },
  ];
  return (
    <div className="fr">
      <div className="fr-hd">
        <span className="fr-tag mono">FILL REALISM · {real ? "LIVE" : "MODELED"}</span>
        <span className="fr-sub mono dim2">
          {real
            ? `spread ${spreadPct.toFixed(2)}% · ADV $${dvol >= 1e9 ? (dvol/1e9).toFixed(1)+"B" : (dvol/1e6).toFixed(0)+"M"} · β ${beta.toFixed(2)} · ${participationPct < 0.01 ? "<0.01" : participationPct.toFixed(2)}% of daily vol`
            : "live spread/ADV unavailable — modeled from β"}
          {real && spreadPct > 0.5 && (
            <b className="warn" title="Reported spread is unusually wide for the price — friction below may be overstated. Verify the live quote before sizing.">{" · ⚠ wide spread — verify quote"}</b>
          )}
        </span>
      </div>
      <div className="fr-flow">
        {steps.map((st, i) => (
          <React.Fragment key={i}>
            <div className={`fr-step ${st.strong ? "is-strong" : ""}`}>
              <span className="fr-step-l mono dim2">{st.l}</span>
              <span className={`fr-step-v mono kpi-tone--${st.tone}`}>{st.v}</span>
              <span className="fr-step-s mono dim2">{st.s}</span>
            </div>
            {i < steps.length - 1 && <span className="fr-arrow mono">{steps[i + 1].add ? "+" : "→"}</span>}
          </React.Fragment>
        ))}
      </div>
      <div className="fr-kpis">
        <div className="fr-kpi"><span className="label-cap">Entry slippage</span><span className="mono kpi-tone--rd fr-kpi-v">−${Math.abs(slipCost)}</span><span className="mono dim2">{slipPct.toFixed(2)}% · {shares} sh</span></div>
        <div className="fr-kpi"><span className="label-cap">Stop gap-fill</span><span className="mono kpi-tone--rd fr-kpi-v">${stopFill.toFixed(2)}</span><span className="mono dim2">−${stopExtra} vs ${stop.toFixed(2)}</span></div>
        <div className="fr-kpi"><span className="label-cap">R:R ideal → real</span><span className="mono fr-kpi-v"><span className="dim2">{rrIdeal.toFixed(2)}→</span><b className={rrReal >= 2 ? "up" : "warn"}>{rrReal.toFixed(2)}</b></span><span className="mono dim2">after fills</span></div>
        <div className="fr-kpi"><span className="label-cap">Round-trip friction</span><span className="mono kpi-tone--amb fr-kpi-v">−${rtCost}</span><span className="mono dim2">in + out</span></div>
      </div>
      <div className="fr-read mono dim2">
        A stop-buy fills at the <b>next bar's open + spread + slippage</b>, not your signal price — so the entry costs ~<b className="dn">−${Math.abs(slipCost)}</b> ({slipPct.toFixed(2)}%) and the stop can gap <b className="dn">${stopExtra}</b> worse, dropping real R:R to <b className={rrReal >= 2 ? "up" : "warn"}>{rrReal.toFixed(2)}</b>. {real ? <>Friction is computed from this name's <b>live spread, ADV participation &amp; beta</b>.</> : <>Live spread/ADV is missing here, so friction is <b>modeled from beta</b>.</>} Paper P&L &amp; Track Record score actual fills.
      </div>
    </div>
  );
}

// ─── Why / Why-Not — the case for & against, pre-mortem before commit ─────────
// Every bullet is derived from real plan data (R:R, ledger edge, sample, pillars,
// risk %, earnings, liquidity, beta) — never fabricated. Mirrors principles 4
// (adversarial) + 15 (pre-mortem with falsification) from the operating mindset.
function WhyWhyNot({ pm, size, ticker, mode }) {
  const px = ticker.pillars || {};
  const tech = px.technical != null ? px.technical : null;
  const ss = pm.setupStats || {};
  const n = ss.n != null ? ss.n : null;
  const pf = ss.pf != null ? ss.pf : null;
  const erD = (pm.earnings && pm.earnings.days != null) ? pm.earnings.days : null;
  const hold = pm.holdDays || 10;
  const pros = [], cons = [];

  // R:R geometry
  if (pm.rr1 >= 3) pros.push({ h: `R:R ${pm.rr1.toFixed(1)}:1 to T1`, d: "well above the 2:1 floor — asymmetric payoff" });
  else if (pm.rr1 >= 2) pros.push({ h: `R:R ${pm.rr1.toFixed(1)}:1 to T1`, d: "clears the 2:1 minimum" });
  else cons.push({ h: `R:R only ${pm.rr1.toFixed(1)}:1 to T1`, d: "below the 2:1 floor — thin payoff for the risk taken" });

  // ledger edge / expectancy
  if (pm.kelly != null && pm.kelly > 0 && pm.evR != null && pm.evR > 0)
    pros.push({ h: `Positive expectancy +${pm.evR.toFixed(2)}R`, d: `${(pm.wr * 100).toFixed(0)}% WR × ${pm.rr1.toFixed(1)}R · Kelly ${(pm.kelly * 100).toFixed(0)}%` });
  else if (pm.kelly == null)
    cons.push({ h: "No ledger edge", d: "this setup has no closed-trade history (n<1) — expectancy unproven" });
  else if (pm.evR != null && pm.evR <= 0)
    cons.push({ h: `Negative expectancy ${pm.evR.toFixed(2)}R`, d: "hasn't paid historically at this win-rate × payoff" });

  // sample size / profit factor
  if (n != null && n >= 10 && pf != null && pf >= 1.2)
    pros.push({ h: `Track record PF ${pf.toFixed(2)}`, d: `n=${n}${pm.lb != null ? ` · Wilson LB ${(pm.lb * 100).toFixed(0)}%` : ""}` });
  else if (n != null && n > 0 && n < 10)
    cons.push({ h: `Thin sample (n=${n})`, d: "below the n≥10 floor — stats are noisy, size half" });

  // technical pillar
  if (tech != null && tech >= 60) pros.push({ h: `Technicals strong (${Math.round(tech)})`, d: "trend / momentum pillar confirms the entry" });
  else if (tech != null && tech < 45) cons.push({ h: `Technicals weak (${Math.round(tech)})`, d: "momentum pillar not supporting the long" });

  // risk budget
  if (size.lossNavPct <= 0.5) pros.push({ h: `Risk contained ${size.lossNavPct.toFixed(2)}% NAV`, d: `max loss $${Math.round(size.maxLoss)} at the stop` });
  else if (size.lossNavPct > 0.75) cons.push({ h: `Risk hot ${size.lossNavPct.toFixed(2)}% NAV`, d: "over the 0.75% per-trade budget — cut size in §2" });

  // earnings proximity
  if (erD != null && erD <= hold) cons.push({ h: `Earnings in ${erD}d`, d: "inside the hold window — overnight gap risk through the print" });
  else if (erD != null && erD > hold) pros.push({ h: "Clear of earnings", d: `next report T+${erD}d, beyond the ~${hold}d hold` });

  // liquidity / spread
  if (typeof pm.spread === "number" && pm.spread > 0.5)
    cons.push({ h: `Wide spread ${pm.spread.toFixed(2)}%`, d: "fills will slip — verify the live quote before sizing" });

  // beta
  if (typeof pm.beta === "number" && pm.beta >= 1.6)
    cons.push({ h: `High beta ${pm.beta.toFixed(2)}`, d: "amplifies both ways — first to fall in a risk-off tape" });

  const Item = ({ x }) => (
    <div className="ww-item">
      <div className="ww-item-h mono">{x.h}</div>
      <div className="ww-item-d mono dim2">{x.d}</div>
    </div>
  );
  return (
    <div className="ww">
      <div className="ww-cols">
        <div className="ww-col ww-col--pro">
          <div className="ww-col-h mono"><span className="ww-ic">✓</span> WHY TAKE IT <span className="dim2">· {pros.length}</span></div>
          {pros.length ? pros.map((x, i) => <Item key={i} x={x} />)
            : <div className="ww-empty mono dim2">No standout supporting factors in this scan.</div>}
        </div>
        <div className="ww-col ww-col--con">
          <div className="ww-col-h mono"><span className="ww-ic">✕</span> WHY NOT · WATCH-OUTS <span className="dim2">· {cons.length}</span></div>
          {cons.length ? cons.map((x, i) => <Item key={i} x={x} />)
            : <div className="ww-empty mono dim2">No material red flags — the risk still lives at the stop below.</div>}
        </div>
      </div>
      <div className="ww-inval mono">
        <span className="ww-inval-tag">PRE-MORTEM</span>
        Thesis is wrong if <b>{pm.symbol}</b> closes below <b className="dn">${pm.stop.toFixed(2)}</b> — exit on the close, never average down.
        {erD != null && erD <= hold ? <> Earnings T+{erD}d is the live binary risk.</> : null}
      </div>
    </div>
  );
}

// ─── §0 Action Panel — functional, paper-only execution ─────────
// FIRE adds an OCO bracket to the ACTIVE paper portfolio (window.MyPF). SAVE /
// JOURNAL persist via window.UserPrefs (cross-device). Every action returns an
// inline confirmation — no silent no-ops. Live trading is intentionally not wired.
function PlanActionPanel({ pm, size, mode, sym, family }) {
  const [msg, setMsg] = useStateP2(null);   // { text, tone }
  const [armed, setArmed] = useStateP2(false);  // 2-step confirm guard
  const mk = (window.__BV && window.__BV.market) || null;
  const pctToT1 = (pm.t1 - pm.entry) / pm.entry * 100;
  const plan = {
    sym, mode, family, entry: pm.entry, stop: pm.stop, t1: pm.t1, t2: pm.t2,
    shares: size.sh, notional: Math.round(size.notional), navPct: +size.navPct.toFixed(1),
    rr1: +pm.rr1.toFixed(2), maxLoss: Math.round(size.maxLoss), ts: new Date().toISOString(),
  };
  const dryRun = () => setMsg({ tone: "ink", text:
    `DRY-RUN · BUY-STOP ${size.sh} ${sym} @ $${pm.entry.toFixed(2)} · stop $${pm.stop.toFixed(2)} (−$${Math.round(size.maxLoss)}) · T1 $${pm.t1.toFixed(2)} · ${pm.rr1.toFixed(2)}R · ${size.navPct.toFixed(1)}% NAV — no order sent.` });
  const savePlan = () => {
    try {
      if (!window.UserPrefs) return setMsg({ tone: "amb", text: "Prefs unavailable — plan not saved." });
      const all = window.UserPrefs.get("savedPlans", {}) || {};
      all[sym] = plan; window.UserPrefs.set("savedPlans", all);
      setMsg({ tone: "gn", text: `✓ Plan saved for ${sym} · restore from any device.` });
    } catch (e) { setMsg({ tone: "rd", text: "Couldn't save plan." }); }
  };
  const journal = () => {
    try {
      if (!window.UserPrefs) return setMsg({ tone: "amb", text: "Prefs unavailable — not journaled." });
      const log = window.UserPrefs.get("journal", []) || [];
      log.unshift({ ...plan, note: `Plan logged · ${family} · ${mode}` });
      window.UserPrefs.set("journal", log.slice(0, 200));
      setMsg({ tone: "gn", text: `✓ Journaled ${sym} plan · ${log.length} total entries.` });
    } catch (e) { setMsg({ tone: "rd", text: "Couldn't write journal entry." }); }
  };
  const fire = () => {
    if (!window.MyPF) return setMsg({ tone: "amb", text: "Paper book unavailable." });
    if (!armed) {   // step 1: arm + ask for confirmation (prevents misclick)
      setArmed(true);
      setMsg({ tone: "amb", text: `Confirm PAPER fill — click again to add ${size.sh} sh ${sym} @ $${pm.entry.toFixed(2)} to your paper book.` });
      return;
    }
    setArmed(false);   // step 2: execute
    try {
      const pid = window.MyPF.activeId();
      window.MyPF.addHolding(pid, { sym, qty: size.sh, cost: pm.entry, stop: pm.stop,
        target: pm.t1, target2: pm.t2, notes: `${mode} · ${family} · OCO bracket from Plan tab` });
      const nm = (window.MyPF.active() || {}).name || "paper book";
      setMsg({ tone: "gn", text: `✓ PAPER FILL · ${size.sh} sh ${sym} @ $${pm.entry.toFixed(2)} added to "${nm}" with OCO stop $${pm.stop.toFixed(2)} / T1 $${pm.t1.toFixed(2)} / T2 $${pm.t2.toFixed(2)}.` });
    } catch (e) { setMsg({ tone: "rd", text: "Couldn't add to paper book." }); }
  };
  return (
    <div className="pap">
      <div className="pap-l">
        <div className="pap-eyebrow mono">PLAN · TICKET · {mode}
          {mk && mk.regime4 && (
            <span className="pap-regime" title="Current market regime + max position-size cap. The whole system is regime-conditioned — a setup's edge depends on the regime.">
              {" · "}{mk.regime4.replace(/_/g, " ")}{mk.maxSize != null ? ` · max ${mk.maxSize}%` : ""}
            </span>
          )}
        </div>
        <div className="pap-headline mono">
          <span className="pap-action">BUY-STOP BRACKET</span>
          <span className="pap-sym">{sym}</span>
          <span className="pap-px copper">${pm.entry.toFixed(2)}</span>
        </div>
        <div className="pap-line mono dim2">
          {family} · {size.sh} sh · ${Math.round(size.notional).toLocaleString()} notional · <b>{size.navPct.toFixed(1)}% NAV</b> · <span title="One-Cancels-Other: the stop and target orders are placed together; filling one cancels the other.">OCO</span> stop ${pm.stop.toFixed(2)}
        </div>
        <div className="pap-read mono">
          ▸ Buy-stop at <b className="copper">${pm.entry.toFixed(2)}</b> · you risk <b className="dn">${Math.round(size.maxLoss)}</b> ({size.lossNavPct.toFixed(2)}% of account) if it stops out · first target <b className="up">${pm.t1.toFixed(2)}</b> <span className="dim2">(+{pctToT1.toFixed(1)}%)</span>.
        </div>
      </div>
      <div className="pap-r">
        <button className={`pap-fire ${armed ? "is-armed" : ""}`} onClick={fire}
          title="Adds an OCO bracket (entry + stop + targets) to your local paper book. Live trading is not wired.">
          ⚡ {armed ? "CONFIRM PAPER FILL" : "FIRE BRACKET"} <span className="pap-paper">PAPER</span>
        </button>
        <div className="pap-r-actions">
          <button className="btn btn--sm" onClick={savePlan}>SAVE PLAN</button>
          <button className="btn btn--sm" onClick={dryRun}>DRY-RUN</button>
          <button className="btn btn--sm" onClick={journal}>＋ JOURNAL</button>
        </div>
      </div>
      {msg && <div className={`pap-msg mono kpi-tone--${msg.tone}`}>{msg.text}</div>}
    </div>
  );
}

// ─── §1 Trade Blueprint — horizontal payoff diagram ────────────
function TradeBlueprint({ pm, size }) {
  const entry = pm.entry;
  const cur = pm.price;
  const stop = pm.stop;
  const t1 = pm.t1;
  const t2 = pm.t2;
  const atr = pm.atr;
  const risk = pm.risk;
  const reward1 = t1 - entry;
  const reward2 = t2 - entry;
  const qty = size.sh;
  const maxLoss = risk * qty;
  const t1Gain = reward1 * qty;
  const t2Gain = reward2 * qty;
  // scale-out plan: sell ⅓ at T1 (lock gain + stop→breakeven), runner to T2
  const thirdSh = Math.max(1, Math.round(qty / 3));
  const runnerSh = Math.max(0, qty - thirdSh);
  const t1Lock = thirdSh * (t1 - entry);
  const runnerT2 = runnerSh * (t2 - entry);
  const blendedR = ((thirdSh * (reward1 / risk)) + (runnerSh * (reward2 / risk))) / qty;  // if plan fills

  const W = 900, H = 408, padT = 56, padB = 78, padL = 72, padR = 108;
  const span = t2 - stop;
  const xMin = stop - span * 0.16, xMax = t2 + span * 0.16;   // visible flat shelves: −1R floor + T2 ceiling
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
    { p: entry, c: "var(--copper)", lbl: "ENTRY", v: `$${entry.toFixed(2)}`, sub: `pivot · ${qty} sh`, big: true },
    { p: cur,   c: "var(--copper)", lbl: "NOW",   v: `$${cur.toFixed(2)}`,   sub: pnlAt(cur) >= 0 ? `+$${pnlAt(cur).toFixed(0)}` : `−$${Math.abs(pnlAt(cur)).toFixed(0)}`, dotted: true },
    { p: t1,    c: "var(--gn)",     lbl: "T1",    v: `$${t1.toFixed(2)}`,    sub: `+$${t1Gain.toFixed(0)}`, big: true },
    { p: t2,    c: "var(--gn)",     lbl: "T2",    v: `$${t2.toFixed(2)}`,    sub: `+$${t2Gain.toFixed(0)}` },
  ];

  // collision-aware 2-row label layout — STOP/ENTRY/NOW pile up when prices are
  // close, so stagger overlapping markers onto a second row instead of overprinting.
  const MIN_GAP = 80;
  const lab = levels.map((m) => ({ ...m, xPos: x(m.p) }));
  const lastByRow = [-Infinity, -Infinity];
  [...lab].sort((a, b) => a.xPos - b.xPos).forEach((m) => {
    if (m.xPos - lastByRow[0] >= MIN_GAP) { m.row = 0; lastByRow[0] = m.xPos; }
    else if (m.xPos - lastByRow[1] >= MIN_GAP) { m.row = 1; lastByRow[1] = m.xPos; }
    else { m.row = 0; lastByRow[0] = m.xPos; }
  });

  return (
    <div className="tbv2">
      <div className="tbv2-metrics">
        <TbMetric label="R:R · T1" value={`${(reward1/risk).toFixed(2)}R`} sub={`+$${t1Gain.toFixed(0)} @ ${qty} sh`} tone="gn" big primary
          tip="Reward-to-risk to the first target = (T1 − entry) ÷ (entry − stop). ≥2 is healthy; the system floor is 1.5." />
        <TbMetric label="Risk · 1R" value={`$${risk.toFixed(2)}`} sub={`stop · −$${maxLoss.toFixed(0)} @ ${qty} sh`} tone="rd" primary
          tip="1R = your risk per share (entry − stop). Every target and result is measured in multiples of this 'R'." />
        <TbMetric label="% to T1" value={`+${(reward1/entry*100).toFixed(2)}%`} sub={`$${t1.toFixed(2)}`} tone="gn" primary
          tip="How far price must move from entry to reach the first target." />
        <TbMetric label="% to Stop" value={`−${(risk/entry*100).toFixed(2)}%`} sub={`$${stop.toFixed(2)}`} tone="rd"
          tip="How far price can fall from entry before the stop triggers." />
        <TbMetric label="R:R · T2" value={`${(reward2/risk).toFixed(2)}R`} sub={`+$${t2Gain.toFixed(0)} @ ${qty} sh`} tone="gn" secondary
          tip="Reward-to-risk to the second (runner) target." />
        <TbMetric label="% to T2" value={`+${(reward2/entry*100).toFixed(2)}%`} sub={`$${t2.toFixed(2)}`} tone="gn" secondary
          tip="How far price must move from entry to reach the second target." />
        <TbMetric label="ATR · est" value={`$${atr.toFixed(2)}`} sub={`${(atr/entry*100).toFixed(1)}% · stop÷1.25`} tone="ink" secondary
          tip="Average True Range — typical daily move. Estimated as stop ÷ 1.25 (the stop is set at 1.25× ATR)." />
        <TbMetric label="Wilson WR" value={pm.lb != null ? `${(pm.lb*100).toFixed(1)}%` : "—"} sub={`LB · n=${pm.setupStats.n ?? "—"}`} tone="copper" secondary
          tip="Wilson 95% lower-bound win-rate for this setup over n past trades — the conservative, sample-size-aware floor, not the rosy point estimate." />
      </div>

      <div className="tbv2-cap mono">
        <span>P&amp;L ($) at exit · <b>{qty} sh</b> BUY-STOP bracket</span>
        <span className="dim2">exit price →</span>
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

          {lab.map((m, i) => {
            const yTop = padT - 14 - m.row * 23;          // stagger overlapping pills upward
            const valY = H - padB + 17 + m.row * 27;       // stagger overlapping axis labels downward
            return (
            <g key={i}>
              <line x1={m.xPos} y1={yTop + 6} x2={m.xPos} y2={H - padB + 4}
                    stroke={m.c} strokeWidth={m.big ? "1.6" : "1.1"}
                    strokeDasharray={m.dotted ? "2 3" : "4 4"} opacity="0.65"
                    style={{ filter: `drop-shadow(0 0 4px ${m.c})` }} />
              <g transform={`translate(${m.xPos}, ${yTop})`}>
                <rect x="-30" y="-11" width="60" height="20" rx="10"
                      fill="color-mix(in oklab, var(--bg-1) 94%, transparent)"
                      stroke={m.c} strokeWidth={m.big ? "1.4" : "0.8"}
                      style={{ filter: m.big ? `drop-shadow(0 0 6px ${m.c})` : "none" }} />
                <text x="0" y="4" fontSize="10.5" className="mono" textAnchor="middle" fill={m.c}
                      fontWeight="600" letterSpacing="0.08em">{m.lbl}</text>
              </g>
              <text x={m.xPos} y={valY} fontSize="11" className="mono" textAnchor="middle"
                    fill={m.c} fontWeight="500">{m.v}</text>
              <text x={m.xPos} y={valY + 13} fontSize="9.5" className="mono" textAnchor="middle" fill="var(--ink-3)">
                {m.sub}
              </text>
            </g>
            );
          })}

          <polyline points={samples.map(s => s.join(",")).join(" ")}
                    stroke="var(--ink)" strokeWidth="2.5" fill="none" strokeLinejoin="round"
                    style={{ filter: "drop-shadow(0 0 6px color-mix(in oklab, var(--copper) 60%, transparent))" }} />

          {lab.map((d, i) => (
            <circle key={i} cx={d.xPos} cy={y(pnlAt(d.p))} r={d.big ? 6 : 4.5} fill={d.c}
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
        </svg>
      </div>

      <div className="tbv2-legend mono">
        <span><span className="tbv2-leg-dot tbv2-leg-cop" /> bracket payoff · stop → T2 capped</span>
        <span><span className="tbv2-leg-dot tbv2-leg-gn" /> profit zone</span>
        <span><span className="tbv2-leg-dot tbv2-leg-rd" /> loss zone</span>
        <span className="dim2">price on X · $ P&L on Y · R-mult on right axis</span>
      </div>

      <div className="tbv2-scale mono">
        <span className="label-cap" title="Pre-decided exit plan: bank part of the position at the first target, let the rest run to the second.">Scale-out</span>
        <span>Sell <b className="copper">⅓ ({thirdSh} sh)</b> at T1 → <b className="up">+${Math.round(t1Lock)}</b> locked, stop→breakeven</span>
        <span className="tbv2-scale-sep">·</span>
        <span>Runner <b className="copper">{runnerSh} sh</b> to T2 → <b className="up">+${Math.round(runnerT2)}</b></span>
        <span className="tbv2-scale-sep">·</span>
        <span title="Position-weighted R if both targets fill: (⅓ at T1 + runner at T2) ÷ shares.">Blended <b className="up">{blendedR.toFixed(2)}R</b> if plan fills</span>
        <span className="tbv2-scale-sep">·</span>
        <span className="dim2">after the T1 partial + stop→BE the runner's <b className="up">planned downside is removed</b> (barring a gap through the stop — see §4)</span>
      </div>
    </div>
  );
}

function TbMetric({ label, value, sub, tone, big, primary, secondary, tip }) {
  return (
    <div className={`tbv2-metric tbv2-metric--${tone} ${big ? "is-big" : ""} ${primary ? "is-primary" : ""} ${secondary ? "is-secondary" : ""} ${tip ? "has-tip" : ""}`} title={tip || undefined}>
      <div className="tbv2-metric-l label-cap">{label}</div>
      <div className={`tbv2-metric-v mono kpi-tone--${tone}`}>{value}</div>
      <div className="tbv2-metric-s mono dim2">{sub}</div>
    </div>
  );
}

// ─── §2 Sizing Workbench ───────────────────────────────────────
function SizingWorkbench({ pm, size, sizeMult, onSizeMult, kellyFrac, onKellyFrac, onEditNav }) {
  const entry = pm.entry;
  const risk = pm.risk;
  const reward = pm.t1 - entry;
  const sh = size.sh;
  const notional = size.notional;
  const maxLoss = size.maxLoss;
  const navPct = size.navPct;
  const lossNavPct = size.lossNavPct;
  return (
    <div className="sw">
      <div className="sw-controls">
        <div className="sw-ctrl">
          <div className="sw-ctrl-l">
            <span className="label-cap" title="Kelly = the bet size that maximizes long-run growth from your win-rate and reward-to-risk. f* is the raw optimum; the slider applies a fraction of it — half-Kelly (50%) is the common, safer choice that cuts volatility.">Kelly fraction</span>
            <span className="mono">
              <b className="copper">{(kellyFrac * 100).toFixed(0)}%</b> of raw Kelly{" "}
              {pm.kelly != null
                ? <span className="dim2">(f*&nbsp;={(pm.kelly * 100).toFixed(1)}% · {(pm.kelly * kellyFrac * 100).toFixed(1)}% applied)</span>
                : <span className="dim2">(f* n/a — no ledger edge)</span>}
            </span>
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
            <span className="mono"><b className="copper">{sizeMult.toFixed(2)}×</b> of base {pm.baseShares} sh</span>
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
        <SwTile label="% NAV"    value={`${navPct.toFixed(1)}%`}         tone={navPct > 10 ? "rd" : navPct > 7 ? "amb" : "gn"} sub="cap 10%" />
        <SwTile label="Max loss" value={`$${maxLoss.toFixed(0)}`}        tone="rd" sub={`${lossNavPct.toFixed(2)}% NAV`} />
        <SwTile label="R-mult"   value={`${(reward/risk).toFixed(2)}R`}  tone="copper" sub="T1 / risk"
                tip="Reward-to-risk at the first target — the same ratio shown in §1, recomputed at your current size." />
        <SwTile label="Expectancy"
                value={pm.evR != null ? `${pm.evR >= 0 ? "+" : "−"}$${Math.abs(pm.evR * risk * sh).toFixed(0)}` : "—"}
                tone={pm.evR == null ? "ink" : pm.evR >= 0 ? "gn" : "rd"}
                sub={pm.evR != null ? `${pm.evR.toFixed(2)}R × ${sh} sh` : "no ledger edge"}
                tip="Average $ you'd expect per trade at this size = win% × reward − loss% × risk, using this setup's real win-rate. Needs ledger history." />
      </div>
      <div className="sw-gates">
        <div className="sw-gates-cap label-cap">
          Live size caps · recompute as you size · full go/no-go in §3
          {pm.navDemo
            ? <span className="sw-navtag is-demo" onClick={onEditNav} style={{ cursor: "pointer" }} title="Click to set your account size"> NAV $100k (demo · click to set yours)</span>
            : <span className="sw-navtag" onClick={onEditNav} style={{ cursor: "pointer" }} title="Click to change your account size"> NAV ${Math.round(pm.NAV).toLocaleString()} (yours · edit)</span>}
        </div>
        <SwGate label="Max loss ≤ 0.75% NAV" v={lossNavPct.toFixed(2)+"%"} pass={lossNavPct <= 0.75} />
        <SwGate label="% NAV ≤ 10%"          v={navPct.toFixed(1)+"%"}    pass={navPct <= 10} />
        <SwGate label="R-mult ≥ 1.5"         v={(reward/risk).toFixed(2)+"R"} pass={(reward/risk) >= 1.5} />
      </div>
    </div>
  );
}

function SwTile({ label, value, tone, sub, tip }) {
  return (
    <div className={`sw-tile sw-tile--${tone} ${tip ? "has-tip" : ""}`} title={tip || undefined}>
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
// Every gate is computed from the live plan (pm), live sizing (size) and the
// ticker's real setup ledger / earnings. Gates we cannot evaluate from data
// render N/A — never a fabricated pass. (CLAUDE.md principle 1 & 4.)
function DecisionGates({ pm, size, ticker }) {
  const ss = pm.setupStats || {};
  const erDays = (ticker.earnings && ticker.earnings.days != null) ? ticker.earnings.days : null;
  const t1Days = Math.max(1, Math.floor((pm.holdDays || 10) * 0.35));
  const lossNavPct = size.lossNavPct, navPct = size.navPct;
  const atrPct = pm.atr / pm.entry;
  const g = (label, state, detail) => ({ label, state, detail });   // state: pass|fail|warn|na

  const stages = [
    { stage: "SETUP", gates: [
      g("Levels coherent (stop<entry<T1<T2)", pm.levelsValid ? "pass" : "fail"),
      g("Pivot / entry defined", pm.entry > 0 ? "pass" : "fail", `$${pm.entry.toFixed(2)}`),
      g("ATR ≥ 0.5% of price", atrPct >= 0.005 ? "pass" : "warn", `${(atrPct * 100).toFixed(2)}%`),
    ]},
    { stage: "EDGE", gates: [
      g("Wilson LB ≥ 45%", (ss.n == null || pm.lb == null) ? "na" : (pm.lb >= 0.45 ? "pass" : "fail"),
        (ss.n == null || pm.lb == null) ? "no ledger" : `${(pm.lb * 100).toFixed(0)}% · n=${ss.n}`),
      g("Profit factor ≥ 1.2", ss.pf == null ? "na" : (ss.pf >= 1.2 ? "pass" : "fail"),
        ss.pf == null ? "no ledger" : ss.pf.toFixed(2)),
      g("Expectancy > 0", pm.evR == null ? "na" : (pm.evR > 0 ? "pass" : "fail"),
        pm.evR == null ? "no ledger" : `${pm.evR.toFixed(2)}R`),
    ]},
    { stage: "RISK", gates: [
      g("Max loss ≤ 0.75% NAV", lossNavPct <= 0.75 ? "pass" : "fail", `${lossNavPct.toFixed(2)}%`),
      g("Position ≤ 10% NAV", navPct <= 10 ? "pass" : "fail", `${navPct.toFixed(1)}%`),
      g("R-mult ≥ 1.5", pm.rr1 >= 1.5 ? "pass" : "fail", `${pm.rr1.toFixed(2)}R`),
    ]},
    { stage: "TIMING", gates: [
      g("ER outside T1 window", erDays == null ? "na" : (erDays <= t1Days ? "warn" : "pass"),
        erDays == null ? "no ER date" : `ER T+${erDays}d · T1 ~T+${t1Days}d`),
    ]},
  ];

  let pass = 0, fail = 0, warn = 0, na = 0, total = 0;
  stages.forEach(s => s.gates.forEach(x => {
    total++; if (x.state === "pass") pass++; else if (x.state === "fail") fail++;
    else if (x.state === "warn") warn++; else na++;
  }));
  const mark = { pass: "✓", fail: "✕", warn: "!", na: "·" };
  const stageState = (gates) => gates.some(x => x.state === "fail") ? "fail"
    : gates.some(x => x.state === "warn") ? "warn" : "pass";

  return (
    <div className="dg">
      {stages.map((s, i) => {
        const st = stageState(s.gates);
        const ok = s.gates.filter(x => x.state === "pass").length;
        return (
          <div key={i} className={`dg-stage ${st === "warn" ? "is-warn" : st === "fail" ? "is-fail" : ""}`}>
            <div className="dg-stage-hdr">
              <span className="dg-stage-l mono">{s.stage}</span>
              <span className={`dg-stage-c mono ${st === "pass" ? "up" : st === "fail" ? "dn" : "warn"}`}>{ok} / {s.gates.length}</span>
            </div>
            {s.gates.map((x, j) => (
              <div key={j} className={`dg-gate is-${x.state}`}>
                <span className="dg-mark mono">{mark[x.state]}</span>
                <span className="dg-lbl mono">{x.label}</span>
                {x.detail && <span className="dg-det mono dim2">{x.detail}</span>}
              </div>
            ))}
          </div>
        );
      })}
      <div className="dg-foot mono dim2">
        {fail > 0
          ? <b className="dn">{fail} gate{fail === 1 ? "" : "s"} FAIL · {pass}/{total} pass{warn ? ` · ${warn} caution` : ""}{na ? ` · ${na} n/a` : ""}. Do not fire until cleared.</b>
          : warn > 0
            ? <b className="warn">{pass}/{total} pass · {warn} caution{na ? ` · ${na} n/a` : ""}. Clear to fire — review cautions{erDays != null && erDays <= t1Days ? " (ER inside T1 window — consider a size cut)" : ""}.</b>
            : <b className="up">{pass}/{total} gates pass{na ? ` · ${na} n/a (no ledger)` : ""}. Clear to fire.</b>}
        {" "}<span>The 3 SETUP checks are structural sanity (rarely fail); the EDGE / RISK / TIMING gates carry the real go/no-go weight.{na > 0 ? " N/A = no ledger history yet — not counted as pass." : ""}</span>
      </div>
    </div>
  );
}

// ─── §4 Time Anatomy V2 ────────────────────────────────────────
function TimeAnatomyV2({ ticker, pm }) {
  const hold = ticker.holdDays || 10;
  const totalSessions = hold + 4;
  const entry = pm.entry;
  const erDays = (ticker.earnings && ticker.earnings.days != null) ? ticker.earnings.days : null;
  const erLabel = erDays == null ? null
    : `ER · ${ticker.earnings.date && ticker.earnings.date.trim() ? ticker.earnings.date : "T+" + erDays + "d"}`;
  const events = [
    { t: -3, label: "Setup formed",            tone: "ink",    px: pm.stop + (pm.entry - pm.stop) * 0.4 },
    { t: -1, label: "Pivot tested · vol-dry", tone: "ink",    px: pm.entry * 0.998 },
    { t:  0, label: "ENTRY · breakout",       tone: "copper", big: true, px: entry },
    { t:  1, label: "Confirm close",          tone: "ink",    px: entry * 1.012 },
    { t:  Math.floor(hold * 0.35),  label: "T1 expected",   tone: "gn", px: pm.t1 },
    ...(erDays != null ? [{ t: Math.min(erDays, hold - 1), label: erLabel, tone: "amb" }] : []),
    { t:  Math.floor(hold * 0.85),  label: "T2 expected",   tone: "gn", px: pm.t2 },
    { t:  hold, label: "Time stop", tone: "rd", px: pm.stop },
  ];
  // collision-aware label layout — alternate sides in X-ORDER (adjacent events go
  // opposite sides) and stack to a 2nd level only if still overlapping.
  const MINX = 9;   // % min horizontal separation before stacking
  const ev = events.map((e) => ({ ...e, x: ((e.t + 4) / totalSessions) * 100 }));
  const upLanes = [], dnLanes = [];
  let sideToggle = 0;
  [...ev].sort((a, b) => a.x - b.x).forEach((e) => {
    const up = (sideToggle++ % 2) === 0;
    const lanes = up ? upLanes : dnLanes;
    let lvl = 0;
    while (lvl < lanes.length && e.x - lanes[lvl] < MINX) lvl++;
    lanes[lvl] = e.x;
    e._up = up; e._lvl = lvl;
  });
  return (
    <div className="time-anatomy">
      <div className="ta-meta mono dim2">
        Session 0 = entry · {totalSessions} sessions plotted · {erDays != null ? `ER at T+${erDays}d` : "no ER in window"}
      </div>
      <div className="ta-ribbon">
        <div className="ta-track">
          <div className="ta-phase ta-phase--pre"  style={{ left: 0, width: `${(4/totalSessions)*100}%` }} />
          <div className="ta-phase ta-phase--hold" style={{ left: `${(4/totalSessions)*100}%`, width: `${(hold/totalSessions)*100}%` }} />
          {Array.from({ length: totalSessions + 1 }, (_, i) => (
            <div key={i} className={`ta-tick ${i === 4 ? "ta-tick-major" : ""}`}
                 style={{ left: `${(i/totalSessions)*100}%` }} />
          ))}
          {ev.map((e, i) => {
            const labelTop = e._up ? -86 - e._lvl * 46 : 28 + e._lvl * 46;
            return (
              <div key={i} className={`ta-event ta-event--${e.tone} ${e.big ? "is-big" : ""}`} style={{ left: `${e.x}%` }}>
                <div className="ta-event-stem" />
                <div className="ta-event-dot" />
                <div className={`ta-event-label mono ${e._up ? "ta-up" : "ta-dn"}`} style={{ top: `${labelTop}px` }}>
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
          <span style={{ left: `${((4 + Math.floor(hold/2))/totalSessions)*100}%` }}>T+{Math.floor(hold/2)}</span>
          <span style={{ left: "100%" }}>T+{hold}</span>
        </div>
      </div>
    </div>
  );
}

// ─── §5 Playbook IF/THEN tree — mode-aware ─────────────────────
// Rules are pre-decided per trade horizon and reference the live ladder. Swing
// reacts intraday/over days; Position reacts on weekly closes; Investment on
// fundamentals/quarters. Conditions cite $entry/$stop/$T1 so they're actionable.
function playbookFor(mode, pm) {
  const E = `$${pm.entry.toFixed(2)}`, S = `$${pm.stop.toFixed(2)}`, T1 = `$${pm.t1.toFixed(2)}`, T2 = `$${pm.t2.toFixed(2)}`;
  if (mode === "POSITION") return [
    { tag: "ENTER", scenarios: [
      { cond: `Weekly close back above pivot ${E}`, then: "Take the planned starter · scale on 21-EMA pullbacks", tone: "gn" },
      { cond: `Opens below ${E}, trend intact`,      then: "Wait for the BUY-STOP — don't pre-buy weakness",       tone: "ink" },
      { cond: "RS rank ≥ 80 + sector leading",       then: "Size to full target weight",                          tone: "gn" },
    ]},
    { tag: "MANAGE", scenarios: [
      { cond: `First target ${T1} (+1R)`,            then: "Trim ¼ · trail remainder under the weekly 21-EMA",     tone: "gn" },
      { cond: "50-DMA flattens / RS fades < 70",     then: "Stop adding · ride core only",                         tone: "amb" },
      { cond: `Runs to ${T2} on expanding volume`,   then: "Trim ¼ more · let the rest trend",                     tone: "gn" },
    ]},
    { tag: "EXIT", scenarios: [
      { cond: `Weekly close below ${S}`,             then: "Trend break · exit on the close (no intraday override)", tone: "rd" },
      { cond: "Earnings miss / guidance cut",        then: "Reduce 50% · re-rate the thesis before re-adding",     tone: "amb" },
      { cond: "Time stop — thesis stalls 6–8 wks",   then: "Recycle capital to a fresher setup",                   tone: "ink" },
    ]},
  ];
  if (mode === "INVESTMENT") return [
    { tag: "ACCUMULATE", scenarios: [
      { cond: `Price within ~5% of value support ${S}`, then: "Add a tranche · dollar-cost on weakness",           tone: "gn" },
      { cond: "Quarter beats + raises guide",           then: "Hold full weight · let it compound",                tone: "gn" },
      { cond: "Multiple re-rates rich vs 5-yr history", then: "Hold — don't add at a premium",                     tone: "amb" },
    ]},
    { tag: "HOLD", scenarios: [
      { cond: `Unrealized > +30% toward ${T2}`,         then: "Trim to target weight · book partial gains",        tone: "gn" },
      { cond: "Annual rebalance window",                then: "Reset position to model weight",                    tone: "ink" },
      { cond: "Dividend raised / buyback expanded",     then: "Reinvest · thesis strengthening",                   tone: "gn" },
    ]},
    { tag: "EXIT", scenarios: [
      { cond: "Thesis pillar breaks (margins / share loss / 2 misses)", then: "Sell · reallocate capital",         tone: "rd" },
      { cond: "Dividend cut / balance-sheet stress",    then: "Exit — fundamental break",                          tone: "rd" },
      { cond: "Better risk-adjusted opportunity",       then: "Rotate · opportunity cost",                         tone: "ink" },
    ]},
  ];
  // SWING (default) — execution over 2–15 days
  return [
    { tag: "OPEN", scenarios: [
      { cond: `Triggers + holds above ${E} first 30m`, then: "In play · trail under the 5-min higher-lows",        tone: "gn" },
      { cond: `Gaps >3% above ${E} on news`,           then: `Don't chase · re-enter only on a higher-low above ${E}`, tone: "amb" },
      { cond: `Opens below ${E}, no catalyst`,         then: "Stand down · let the BUY-STOP do the work",          tone: "ink" },
    ]},
    { tag: "MANAGE", scenarios: [
      { cond: `Hits +1R near ${T1}`,                   then: "Sell ⅓ · move stop to breakeven " + E,               tone: "gn" },
      { cond: "Volume < 0.6× avg for 2 sessions",      then: "Tighten to ATR×1.5 · momentum fading",               tone: "amb" },
      { cond: `Closes strong toward ${T2}`,            then: "Trail the rest with ATR×2.2",                        tone: "gn" },
    ]},
    { tag: "INVALIDATE", scenarios: [
      { cond: `Daily close below ${S}`,                then: "Exit on close · OCO covers the intraday wick",       tone: "rd" },
      { cond: "Sector ETF −2% intraday",               then: "Halve size · correlation risk",                      tone: "amb" },
      { cond: "Hard stop hit",                         then: "OCO auto-exit · no manual override",                 tone: "rd" },
    ]},
  ];
}

function PlaybookTree({ mode, pm }) {
  const branches = playbookFor(mode, pm);
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
function AuditLog({ pm, size }) {
  // real book concentration from the active paper portfolio
  let bookSub = "book unavailable", bookTxt = "Book concentration check";
  try {
    if (window.MyPF) {
      const pf = window.MyPF.combined();
      const hold = (pf && pf.holdings) || [];
      const n = hold.length;
      const held = hold.some(h => (h.sym || "").toUpperCase() === pm.symbol);
      bookTxt = `Book concentration · ${n} open position${n === 1 ? "" : "s"}${held ? " · ALREADY HELD" : ""}`;
      bookSub = n === 0 ? "book empty — no concentration risk" : held ? "adding to an existing name" : "no overlap with this name";
    }
  } catch (e) {}
  const beta = (typeof pm.beta === "number" && pm.beta > 0) ? pm.beta : 1.0;
  const gapMult = 1 + Math.min(1.5, beta * 0.5);        // beta-scaled overnight gap stress
  const items = [
    { phase: "PRE-FILL", item: `OCO bracket constructed · stop $${pm.stop.toFixed(2)} + T1 $${pm.t1.toFixed(2)} + T2 $${pm.t2.toFixed(2)}`, done: true },
    { phase: "PRE-FILL", item: `Sizing approved · ${size.sh} sh · ${size.navPct.toFixed(1)}% NAV · max risk $${Math.round(size.maxLoss)}`, done: true },
    { phase: "PRE-FILL", item: bookTxt, done: true, sub: bookSub },
    { phase: "PRE-FILL", item: `Sleep-test · β-gap worst-case −$${Math.round(size.maxLoss * gapMult)} vs −$${Math.round(size.maxLoss)} planned`, done: true, sub: `β ${beta.toFixed(2)} overnight gap` },
    { phase: "PRE-FILL", item: pm.earnings.days != null ? `ER alert · T−2 reminder set (ER in ${pm.earnings.days}d)` : "ER alert · none in hold window", done: true },
    { phase: "FILL",     item: "Order staged to paper book · OCO bracket armed",                    done: false, sub: "fires on FIRE BRACKET" },
    { phase: "POST-FILL",item: "Position added to paper book · risk recompute",                      done: false },
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
