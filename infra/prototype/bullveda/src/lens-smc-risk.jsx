// lens-smc.jsx + lens-risk.jsx — Smart Money Concepts and Risk lenses

const { useMemo: useMemoSR, useState: useStateSMC, useEffect: useEffSMC } = React;

// Real SMC model from the server engine (engines/smc.py) via /api/pattern/smc.
// Mode-aware (SWING=daily, POSITION=weekly, INVEST=monthly). No mock fallback —
// when the feed has no usable structure the sections render honest empty states.
function useSmcModel(ticker, mode) {
  const sym = (ticker && ticker.symbol) || "";
  const md = (mode || "SWING").toUpperCase();
  const key = "smc|" + sym + "|" + md;
  const read = () => { try { return (window.__BV && window.__BV.patternCached && window.__BV.patternCached("smc", sym, md)) || null; } catch (e) { return null; } };
  const [real, setReal] = useStateSMC(read);
  useEffSMC(() => {
    let alive = true;
    setReal(read());
    try { if (window.__BV && window.__BV.fetchPattern && sym) window.__BV.fetchPattern("smc", sym, md).then(d => { if (alive) setReal(d); }); } catch (e) {}
    return () => { alive = false; };
  }, [key]);
  let st = "mock";
  if (real && typeof real === "object" && ("ok" in real)) st = "loaded";
  else if (real === null && window.__BV && window.__BV.fetchPattern) st = "loading";
  return { m: real, state: st };
}

const _smcUsable = (m) => !!(m && m.ok);
function SmcEmpty({ state, what }) {
  const msg = state === "loading" ? "loading live bars…"
    : state === "loaded" ? `no ${what || "structure"} computed from this timeframe's bars`
    : "connect to :7432 for live data";
  return <div className="smc-empty mono dim2">— {msg}</div>;
}
function smcMoney(v) { return (typeof v === "number" && isFinite(v)) ? "$" + v.toFixed(2) : "—"; }
function smcTone(state) { return state === "fresh" ? "ink" : state === "held" ? "gn" : state === "mitigated" ? "amb" : "cy"; }

// real 1h intraday bars (for kill-zone session timing) via /api/smc_bars
function useSmcIntraday(sym) {
  const [d, setD] = useStateSMC(null);
  useEffSMC(() => {
    let on = true; if (!sym) return;
    fetch(`/api/smc_bars?t=${encodeURIComponent(sym)}&interval=1h`, { credentials: "same-origin" })
      .then(r => r.ok ? r.json() : null).then(j => { if (on) setD(j || { bars: [] }); }).catch(() => { if (on) setD({ bars: [] }); });
    return () => { on = false; };
  }, [sym]);
  return d;
}

// bucket recent 1h bars into ICT kill zones (ET) + prior-session sweep detection
function smcKillZones(bars) {
  if (!Array.isArray(bars) || !bars.length) return null;
  const fmt = (t, o) => { try { return new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: "America/New_York" }, o)).format(new Date(t * 1000)); } catch (e) { return ""; } };
  const etHour = t => { const h = +fmt(t, { hour: "2-digit", hour12: false }); return isFinite(h) ? h : null; };
  const etDay = t => fmt(t, { month: "2-digit", day: "2-digit" });
  const zoneOf = h => h == null ? null : (h >= 2 && h < 5) ? "London" : (h >= 8 && h < 11) ? "NY AM" : (h >= 13 && h < 16) ? "NY PM" : (h >= 20 || h < 1) ? "Asia" : null;
  const sess = {};
  bars.forEach(b => {
    const z = zoneOf(etHour(b.time)); if (!z) return;
    const k = etDay(b.time) + "|" + z;
    const s = sess[k] || (sess[k] = { z, day: etDay(b.time), hi: -1e9, lo: 1e9, last: 0 });
    s.hi = Math.max(s.hi, b.high); s.lo = Math.min(s.lo, b.low); s.last = Math.max(s.last, b.time);
  });
  const arr = Object.values(sess).sort((a, b) => a.last - b.last);
  for (let i = 1; i < arr.length; i++) { arr[i].sweptHigh = arr[i].hi > arr[i - 1].hi; arr[i].sweptLow = arr[i].lo < arr[i - 1].lo; }
  return { sessions: arr.slice(-4), active: zoneOf(etHour(bars[bars.length - 1].time)) };
}

// Assemble the engine's structure into ONE tradeable decision: verdict + entry zone
// (unmitigated OB) + stop (just beyond it) + target (draw on liquidity) + R:R +
// plain invalidation. Resolves the bull-but-premium case into WAIT-for-pullback.
function smcDecision(m) {
  if (!m || !m.ok) return null;
  const cur = m.cur_close, r = m.range, draw = m.draw_on_liquidity;
  const bull = m.bias === "bull", bear = m.bias === "bear";
  const obs = m.order_blocks || [];
  // nearest in-direction OB to current price
  let ob = null;
  if (bull) ob = obs.filter(o => o.type === "demand" && o.hi <= cur * 1.005).sort((a, b) => b.hi - a.hi)[0] || null;
  else if (bear) ob = obs.filter(o => o.type === "supply" && o.lo >= cur * 0.995).sort((a, b) => a.lo - b.lo)[0] || null;
  const obMid = ob ? (ob.lo + ob.hi) / 2 : null;
  const obFar = obMid != null && Math.abs(obMid - cur) / cur > 0.12;   // >12% away = not an actionable entry
  const nearEntry = !!(ob && !obFar);
  let entry = null, stop = null;
  if (nearEntry) {
    entry = +(((ob.lo + ob.hi) / 2)).toFixed(2);
    stop = bull ? +(ob.lo * 0.99).toFixed(2) : +(ob.hi * 1.01).toFixed(2);
  }
  // target: a real level BEYOND current price in the bias direction — else blue-sky/none
  let target = null;
  if (bull) target = (draw && draw.price > cur) ? draw.price : (r.hi > cur ? r.hi : null);
  else if (bear) target = (draw && draw.price < cur) ? draw.price : (r.lo < cur ? r.lo : null);
  if (entry != null && target != null) {
    if (bull && target <= entry) target = Math.max(r.hi, +(entry * 1.02).toFixed(2));
    else if (bear && target >= entry) target = Math.min(r.lo, +(entry * 0.98).toFixed(2));
  }
  let rr = null;
  if (entry != null && stop != null && target != null) {
    const risk = Math.abs(entry - stop), rew = Math.abs(target - entry);
    const valid = bull ? (target > entry && entry > stop) : (target < entry && entry < stop);
    rr = (valid && risk > 0) ? rew / risk : null;
  }
  const obPct = obMid != null ? Math.round(Math.abs(obMid - cur) / cur * 100) : null;
  let verdict, vtone, action;
  if (!bull && !bear) {
    verdict = "NO EDGE"; vtone = "amb";
    action = "Range-bound — no committed bias. Wait for a break of structure before trading.";
  } else if (bull) {
    if (!nearEntry) {
      verdict = "EXTENDED"; vtone = "amb";
      action = `Bullish but extended at ${r.pct}% of range — no low-risk entry near price${ob ? ` (nearest demand OB is ${smcMoney(ob.lo)}–${smcMoney(ob.hi)}, ~${obPct}% below)` : ""}. Don't chase — wait for a pullback into structure or a fresh base.`;
    } else if (r.zone === "discount" || r.ote_active) {
      verdict = "BUY"; vtone = "gn";
      action = `Bullish and in ${r.ote_active ? "the OTE zone" : "discount"} — long the demand OB ${smcMoney(ob.lo)}–${smcMoney(ob.hi)}${target ? ` toward ${smcMoney(target)}` : ""}.`;
    } else {
      verdict = "WAIT"; vtone = "amb";
      action = `Bullish but extended (premium, ${r.pct}% of range). Don't chase — wait for a pullback into ${smcMoney(ob.lo)}–${smcMoney(ob.hi)} / OTE ${smcMoney(r.ote_lo)}–${smcMoney(r.ote_hi)}, then long.`;
    }
  } else {
    verdict = "AVOID"; vtone = "rd";
    action = `Bearish structure — no long. ${(nearEntry && r.zone === "premium") ? `Short setup from the supply OB ${smcMoney(ob.lo)}–${smcMoney(ob.hi)}${target ? ` toward ${smcMoney(target)}` : ""}.` : "Stand aside until structure flips."}`;
  }
  const invalid = (entry != null && stop != null) ? `price closes ${bull ? "below" : "above"} ${smcMoney(stop)}` : `${m.tf} structure flips (${bull ? "CHoCH down" : "CHoCH up"})`;
  const targetFar = (entry != null && target != null) && (Math.abs(target - entry) / entry > 0.20);
  return { verdict, vtone, action, entry, stop, target, rr, ob: nearEntry ? ob : null, invalid, bull, bear, targetFar };
}

// The annotated map: real candles with OB / FVG / liquidity / OTE zones drawn on
// price — the "show me the zones on the chart" view a retail trader needs first.
function SMCAnnotatedChart({ m, state }) {
  if (!_smcUsable(m) || !Array.isArray(m.ohlc) || m.ohlc.length < 5) return <SmcEmpty state={state} what="chart" />;
  const bars = m.ohlc, r = m.range, draw = m.draw_on_liquidity, cur = m.cur_close;
  const obs = (m.order_blocks || []).slice(0, 4);
  const fvgs = (m.fvgs || []).filter(g => g.state === "unfilled").slice(0, 3);
  const W = 900, H = 320, padT = 14, padB = 16, padL = 8, padR = 150;
  const zP = [].concat(obs.flatMap(o => [o.lo, o.hi]), fvgs.flatMap(g => [g.lo, g.hi]), draw ? [draw.price] : [], [r.ote_lo, r.ote_hi, cur]);
  const lo = Math.min(...bars.map(b => b.l), ...zP) * 0.999;
  const hi = Math.max(...bars.map(b => b.h), ...zP) * 1.001;
  const span = Math.max(hi - lo, 1e-6);
  const y = p => padT + (1 - (p - lo) / span) * (H - padT - padB);
  const cw = (W - padL - padR) / bars.length, cx = i => padL + i * cw + cw / 2;
  // right-edge labels, de-overlapped greedily
  const labels = [];
  const addLabel = (price, text, color) => { const yy = y(price); if (labels.some(l => Math.abs(l.y - yy) < 12)) return; labels.push({ y: yy, text, color }); };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="xMidYMid meet" className="smc-map-svg">
      <defs>
        <linearGradient id="ac-obp" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.22"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0.05"/></linearGradient>
        <linearGradient id="ac-obm" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.22"/><stop offset="100%" stopColor="var(--rd)" stopOpacity="0.05"/></linearGradient>
      </defs>
      {/* OTE band */}
      <rect x={padL} y={y(r.ote_hi)} width={W - padL - padR} height={Math.max(2, y(r.ote_lo) - y(r.ote_hi))} fill="var(--copper)" opacity="0.10" />
      {/* OB zones */}
      {obs.map((o, i) => { addLabel(o.hi, `${o.type === "demand" ? "▲ OB+" : "▼ OB−"} ${o.state}`, o.type === "demand" ? "var(--gn)" : "var(--rd)");
        return <rect key={"ob" + i} x={padL} y={y(o.hi)} width={W - padL - padR} height={Math.max(3, y(o.lo) - y(o.hi))} fill={o.type === "demand" ? "url(#ac-obp)" : "url(#ac-obm)"} stroke={`var(--${o.type === "demand" ? "gn" : "rd"})`} strokeOpacity="0.35" strokeWidth="0.6" />; })}
      {/* FVG zones */}
      {fvgs.map((g, i) => { addLabel(g.hi, "▦ FVG", "var(--violet)");
        return <rect key={"fv" + i} x={padL} y={y(g.hi)} width={W - padL - padR} height={Math.max(2, y(g.lo) - y(g.hi))} fill="var(--violet)" opacity="0.12" strokeDasharray="3 3" stroke="var(--violet)" strokeOpacity="0.3" />; })}
      {/* draw-on-liquidity */}
      {draw && (()=>{ addLabel(draw.price, `◆ draw ${draw.side}`, "var(--amb)"); return <line x1={padL} y1={y(draw.price)} x2={W - padR} y2={y(draw.price)} stroke="var(--amb)" strokeDasharray="5 3" opacity="0.7" />; })()}
      {/* candles */}
      {bars.map((b, i) => { const up = b.c >= b.o, col = up ? "var(--gn)" : "var(--rd)";
        return <g key={i}><line x1={cx(i)} y1={y(b.h)} x2={cx(i)} y2={y(b.l)} stroke={col} strokeWidth="0.8" opacity="0.85" /><rect x={cx(i) - cw * 0.3} y={y(Math.max(b.o, b.c))} width={Math.max(1, cw * 0.6)} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} fill={col} opacity="0.9" /></g>; })}
      {/* current price */}
      <line x1={padL} y1={y(cur)} x2={W - padR} y2={y(cur)} stroke="var(--copper)" strokeWidth="1" strokeDasharray="2 2" />
      <circle cx={cx(bars.length - 1)} cy={y(cur)} r="3.5" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 5px var(--copper))" }} />
      {/* right-edge labels */}
      {labels.concat([{ y: y(cur), text: `● ${smcMoney(cur)}`, color: "var(--copper)" }]).map((l, i) => (
        <g key={"lb" + i}>
          <line x1={W - padR} y1={l.y} x2={W - padR + 10} y2={l.y} stroke={l.color} strokeOpacity="0.5" />
          <text x={W - padR + 14} y={l.y + 3.5} fontSize="10" className="mono" fill={l.color}>{l.text}</text>
        </g>
      ))}
    </svg>
  );
}

function SmcQuickCard({ m }) {
  if (!_smcUsable(m)) return null;
  const d = smcDecision(m);
  if (!d) return null;
  // far target ⇒ the big R:R is a liquidity-void number, not a near target — tone it amber, not green
  const rrTone = d.rr == null ? "ink" : d.targetFar ? "amb" : d.rr >= 2 ? "gn" : d.rr >= 1 ? "amb" : "rd";
  return (
    <div className={`smc-qc smc-qc--${d.vtone}`}>
      <div className="smc-qc-l">
        <div className="smc-qc-head">
          <span className={`smc-qc-verdict smc-qc-verdict--${d.vtone}`}>{d.verdict}</span>
          <span className="label-cap">Quick Read · SMC · {m.tf}</span>
          <span className="smc-qc-real mono" title={`computed from ${m.bars} live ${m.tf} bars`}>● REAL · {m.bars} bars</span>
        </div>
        <div className="smc-qc-action mono">{d.action}</div>
        <div className="smc-qc-invalid mono dim2">✕ Idea is wrong if {d.invalid}.</div>
      </div>
      <div className="smc-qc-r">
        <div className="smc-qc-tiles">
          <div className="smc-qc-tile" title="Buy zone — the unmitigated demand order block to enter on a pullback.">
            <span className="label-cap">Entry zone</span><span className="mono copper">{d.ob ? `${smcMoney(d.ob.lo)}–${smcMoney(d.ob.hi)}` : smcMoney(d.entry)}</span></div>
          <div className="smc-qc-tile" title="Protective stop — just beyond the order block; a close past it invalidates the setup.">
            <span className="label-cap">Stop</span><span className="mono dn">{smcMoney(d.stop)}</span></div>
          <div className="smc-qc-tile" title="Target — the draw on liquidity the move is reaching for.">
            <span className="label-cap">Target</span><span className="mono up">{smcMoney(d.target)}</span></div>
          <div className="smc-qc-tile" title={d.targetFar ? "Target is the next liquidity pool >20% away (a void) — large R:R, but it's a far target, not a near one." : "Reward-to-risk if filled at the entry zone."}>
            <span className="label-cap">R:R{d.targetFar ? " · far" : ""}</span><span className={`mono kpi-tone--${rrTone}`}>{d.rr != null ? d.rr.toFixed(2) + "R" : "—"}</span></div>
        </div>
        <button className="smc-qc-btn" title="Open the Plan tab to size this and see $ risk"
          onClick={() => { try { window.__setLens && window.__setLens("plan"); } catch (e) {} }}>→ Size in Plan</button>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// SMC — order blocks, FVG, BoS/CHoCH, liquidity sweeps
// ────────────────────────────────────────────────────────────
function LensSMC({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const { m, state } = useSmcModel(ticker, mode);
  const ok = _smcUsable(m);
  const bias = ok ? m.bias : null;
  const biasTone = bias === "bull" ? "gn" : bias === "bear" ? "rd" : "amb";
  const zone = ok ? m.range.zone : null;
  const zoneTone = zone === "discount" ? "gn" : zone === "premium" ? "rd" : "amb";
  const draw = ok ? m.draw_on_liquidity : null;
  const obs = ok ? m.order_blocks : [];
  const nUnmit = obs.filter(o => o.state !== "mitigated").length;
  const nFVGu = ok ? m.fvgs.filter(g => g.state === "unfilled").length : 0;
  const lastEvt = ok && m.structure.events.length ? m.structure.events[m.structure.events.length - 1] : null;
  const [adv, setAdv] = useStateSMC(false);
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
      {window.LensSummaryBar && <LensSummaryBar ticker={ticker} mode={mode} kind="smc" smc={m} />}
      <SmcQuickCard m={m} />
      <div className="hero smc-hero">
        <div className="th-left">
          <div className="label-cap">SMC structure read · {mode}{ok ? " · " + m.tf : ""}</div>
          <div className="th-score">
            <div className="th-score-num mono">{ok ? (m.smc_score >= 66 ? "PASS" : m.smc_score >= 50 ? "MIXED" : "WEAK") : "—"}</div>
            {ok && <Pill tone={biasTone} dot>{m.headline}</Pill>}
            {ok && <Pill tone={zoneTone} small>{zone}</Pill>}
          </div>
          <div className="th-pill-row">
            {ok ? <>
              <Pill tone="gn" small>{nUnmit} fresh OB{nUnmit === 1 ? "" : "s"} · {bias === "bull" ? "dip-buy zones" : bias === "bear" ? "rip-sell zones" : "watch zones"}</Pill>
              {nFVGu > 0 ? <Pill tone="cy" small>{nFVGu} open gap{nFVGu === 1 ? "" : "s"} · price magnets</Pill> : <Pill tone="ink" small>no open gaps</Pill>}
              {draw && <Pill tone="amb" small>target {smcMoney(draw.price)}</Pill>}
              <Pill tone={biasTone} small>structure {m.smc_score}/100</Pill>
            </> : <Pill tone="amb" small>{state === "loading" ? "loading live bars…" : "no live structure"}</Pill>}
          </div>
        </div>
        <div className="th-right">
          <SMCMicroChart m={m} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader title="SMC Snapshot"
          sub="bias · structure · range · draw · score — all computed from live bars" style="minimal" />
        <div className="lens-pad">
          {ok ? <CrossLens lead="cy" cells={[
            { lens: "Bias", verdict: m.bias.toUpperCase(), tone: biasTone, note: m.headline },
            { lens: "Structure", verdict: lastEvt ? lastEvt.evt : "—", tone: lastEvt ? (lastEvt.dir === "up" ? "gn" : "rd") : "amb",
              note: lastEvt ? `${lastEvt.dir} @ ${smcMoney(lastEvt.price)} · ${lastEvt.date}` : "no break of structure" },
            { lens: "Range", verdict: zone.toUpperCase(), tone: zoneTone, note: `${m.range.pct}% of ${smcMoney(m.range.lo)}–${smcMoney(m.range.hi)}` },
            { lens: "Draw", verdict: draw ? smcMoney(draw.price) : "—", tone: "cy", note: draw ? draw.side + " liquidity" : "none in bias direction" },
            { lens: "Score", verdict: String(m.smc_score), tone: biasTone, note: "structure quality (not a return forecast)" },
          ]} /> : <SmcEmpty state={state} what="SMC structure" />}
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader title="Annotated Map · zones on price"
          sub="real candles with order blocks · FVGs · liquidity draw · OTE drawn to scale" style="minimal" />
        <div className="lens-pad"><SMCAnnotatedChart m={m} state={state} /></div>
      </div>

      <div className="lens-section">
        <SectionHeader n={0} title="Macro · Higher-Timeframe Context"
          sub="draw on liquidity · HTF bias · premium/discount · daily/weekly levels"
          style={headerStyle} right={<StateToggle name="sm-0" />} />
        <StateWrap state={s0.value} source="MTF structure · D/W/M levels · session liquidity">
          <div className="lens-pad"><SMCMacro m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Order Blocks" tip={'Order Block (OB): the last opposite-color candle before a strong move that broke structure — where institutions likely filled. Price often respects it on a revisit.'}
          sub="last 6 unmitigated demand/supply zones · institutional footprints"
          style={headerStyle} right={<StateToggle name="sm-1" />} />
        <StateWrap state={s1.value} source="bespoke detector · candle structure">
          <div className="lens-pad"><OBTable m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Fair Value Gaps · BoS · CHoCH" tip={'FVG: a 3-bar price gap (imbalance) the market tends to revisit. BoS: break of structure (trend continues). CHoCH: change of character (possible reversal).'}
          sub="structural shifts · break-of-structure log"
          style={headerStyle} right={<StateToggle name="sm-2" />} />
        <StateWrap state={s2.value} source="structure aggregator">
          <div className="lens-pad"><StructureLog m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Liquidity Sweeps · Pools" tip={'Liquidity = clustered stops at prior highs/lows. Price often sweeps (spikes through) them to fill size, then reverses.'}
          sub="stop-hunts above prior highs / below prior lows · resting liquidity"
          style={headerStyle} right={<StateToggle name="sm-3" />} />
        <StateWrap state={s3.value} source="sweep detector · 30 sessions">
          <div className="lens-pad"><LiquiditySweeps m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Premium / Discount · Equilibrium" tip={'Dealing range split at 50% equilibrium: below = discount (buy zone), above = premium (sell zone).'}
          sub="dealing-range zones · where to buy vs sell"
          style={headerStyle} right={<StateToggle name="sm-5" />} />
        <StateWrap state={s5.value} source="dealing range · trailing extremes">
          <div className="lens-pad"><SMCZones m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="MTF Screener"
          sub="confluence across 1H · 4H · D · W"
          style={headerStyle} right={<StateToggle name="sm-4" />} />
        <StateWrap state={s4.value} source="MTF aggregator · 1H/4H/D/W structure">
          <div className="lens-pad"><MTFScreener m={m} state={state} /></div>
        </StateWrap>
      </div>

      <button className="smc-adv-toggle mono" onClick={() => setAdv(!adv)}>
        {adv ? "▾ Hide advanced SMC" : "▸ Advanced SMC"} <span className="dim2">· inducement · breakers · OTE · kill-zones · entry model · confluence · heatmap · alerts</span>
      </button>
      {adv && (<>
      <div className="lens-section">
        <SectionHeader n={6} title="Inducement · Liquidity Engineering" tip={'Inducement: a minor high/low that lures breakout traders so their stops get swept before the real move.'}
          sub="the trap before the move · minor liquidity swept first"
          style={headerStyle} right={<StateToggle name="sm-6" />} />
        <StateWrap state={s6b.value} source="inducement detector · sub-pivot sweeps">
          <div className="lens-pad"><SMCInducement m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Breaker · Mitigation Blocks" tip={'Breaker: a failed OB that flips polarity (old support → resistance). Mitigation block: an OB revisited and partially filled.'}
          sub="failed OBs that flip polarity · revisited origins"
          style={headerStyle} right={<StateToggle name="sm-7" />} />
        <StateWrap state={s7b.value} source="polarity-flip detector">
          <div className="lens-pad"><SMCBreakers m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Liquidity Voids · Displacement · OTE" tip={'Displacement: an impulsive move leaving an imbalance (void). OTE = Optimal Trade Entry: the 62–79% retracement of that move.'}
          sub="inefficiencies · momentum leg · optimal trade entry 62–79%"
          style={headerStyle} right={<StateToggle name="sm-8" />} />
        <StateWrap state={s8b.value} source="displacement + fib OTE engine">
          <div className="lens-pad"><SMCVoidOTE m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={9} title="Kill Zones · SMT Divergence" tip={'Kill zones: high-activity session windows (London / NY). SMT: when a stock and its sector/index disagree on a high/low — a relative-strength tell.'}
          sub="session timing edge · correlated-pair divergence"
          style={headerStyle} right={<StateToggle name="sm-9" />} />
        <StateWrap state={s9b.value} source="session clock + SMT vs sector ETF">
          <div className="lens-pad"><SMCKillSMT m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={10} title="Entry Model · Confluence Grade" tip={'A–F checklist: liquidity sweep → CHoCH/BoS → FVG → OB/OTE entry → confirmation. More steps complete = higher-confluence setup.'}
          sub="sweep → CHoCH → FVG → OB · step tracker + A–F grade"
          style={headerStyle} right={<StateToggle name="sm-10" />} />
        <StateWrap state={s10b.value} source="entry-model state machine">
          <div className="lens-pad"><SMCEntryModel m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={11} title="Trend-State Machine"
          sub="persistent CHoCH/BoS regime across timeframes"
          style={headerStyle} right={<StateToggle name="sm-11" />} />
        <StateWrap state={s11b.value} source="structure state machine">
          <div className="lens-pad"><SMCTrendState m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={12} title="Confluence Stacking · A+ Zones" tip={'Zones where multiple SMC factors overlap (OB + FVG + OTE + discount + HTF level). More factors = higher-probability entry.'}
          sub="OB + FVG + OTE + HTF level + liquidity aligned"
          style={headerStyle} right={<StateToggle name="sm-12" />} />
        <StateWrap state={s12b.value} source="confluence scorer">
          <div className="lens-pad"><SMCConfluence m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={13} title="Mitigation Hit-Rate · Liquidity Heatmap" tip={'How often each zone type was respected historically (replayed on real bars) + where resting liquidity is densest.'}
          sub="zone respect history + resting liquidity density"
          style={headerStyle} right={<StateToggle name="sm-13" />} />
        <StateWrap state={s13b.value} source="zone tracker + liquidity density">
          <div className="lens-pad"><SMCMitigationHeat m={m} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={14} title="SMC Alerts"
          sub="price-entering-OB · FVG fill · liquidity sweep triggers"
          style={headerStyle} right={<StateToggle name="sm-14" />} />
        <StateWrap state={s14b.value} source="alert engine · SMC conditions">
          <div className="lens-pad"><SMCAlerts m={m} state={state} /></div>
        </StateWrap>
      </div>
      </>)}

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          {ok ? (() => {
            const px = ticker.pillars || {};
            const tech = px.technical;
            const mtfH = m.mtf && m.mtf.length > 1 ? m.mtf[1] : null;
            return <CrossLens lead="cy" cells={[
              { lens: "SMC", verdict: m.smc_score >= 66 ? "PASS" : m.smc_score >= 50 ? "MIXED" : "WEAK", tone: biasTone, note: m.headline },
              { lens: "HTF", verdict: mtfH ? mtfH.bias : "—", tone: mtfH && mtfH.bias === "BULL" ? "gn" : mtfH && mtfH.bias === "BEAR" ? "rd" : "amb", note: mtfH ? mtfH.tf + " timeframe" : "single TF" },
              { lens: "Range", verdict: zone.toUpperCase(), tone: zoneTone, note: `${m.range.pct}% of range` },
              { lens: "Technicals", verdict: tech == null ? "—" : tech >= 60 ? "STRONG" : tech >= 45 ? "OK" : "WEAK", tone: tech == null ? "amb" : tech >= 60 ? "gn" : tech >= 45 ? "amb" : "rd", note: tech == null ? "open Technicals lens" : `pillar ${Math.round(tech)}` },
              { lens: "Draw", verdict: draw ? smcMoney(draw.price) : "—", tone: "cy", note: draw ? draw.side : "none" },
            ]} />;
          })() : <SmcEmpty state={state} what="confluence" />}
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · SMC</span>
        {ok ? (() => {
          const ob = obs.find(o => o.state !== "mitigated") || obs[0];
          const longBias = m.bias === "bull";
          return <span className="mono">
            {m.bias.toUpperCase()} structure · price in <b className={zoneTone === "gn" ? "up" : zoneTone === "rd" ? "dn" : "warn"}>{zone}</b> ({m.range.pct}% of range)
            {ob ? <> · {ob.type} OB at <b className="copper">{smcMoney(ob.lo)}–{smcMoney(ob.hi)}</b> ({ob.state})</> : null}
            {draw ? <> · draw on liquidity {draw.side} at <b className={longBias ? "up" : "dn"}>{smcMoney(draw.price)}</b>.</> : "."}
            {" "}{longBias ? "Favor longs from discount toward buy-side liquidity." : m.bias === "bear" ? "Favor shorts from premium toward sell-side liquidity." : "Range-bound — fade the edges, no committed bias."}
          </span>;
        })() : <span className="mono dim2">No SMC structure computed for {(ticker && ticker.symbol) || "this name"} on the {mode} timeframe — the feed returned no usable bars.</span>}
      </div>
    </div>
  );
}

// Macro / HTF context for SMC
function SMCMacro({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="macro context" />;
  const r = m.range, draw = m.draw_on_liquidity;
  const bTone = m.bias === "bull" ? "gn" : m.bias === "bear" ? "rd" : "amb";
  const zTone = r.zone === "discount" ? "gn" : r.zone === "premium" ? "rd" : "amb";
  return (
    <div className="smc-macro">
      <div className="smc-macro-grid">
        <div className={`smc-mc smc-mc--${bTone}`}>
          <div className="label-cap">HTF BIAS · {m.tf}</div>
          <div className={`mono smc-mc-v ${m.bias === "bull" ? "up" : m.bias === "bear" ? "dn" : "warn"}`}>{m.bias.toUpperCase()}</div>
          <div className="mono dim2">{m.headline}</div>
        </div>
        <div className="smc-mc smc-mc--cy">
          <div className="label-cap">DRAW ON LIQUIDITY</div>
          <div className="mono smc-mc-v cy">{draw ? smcMoney(draw.price) : "—"}</div>
          <div className="mono dim2">{draw ? draw.side + " · nearest untapped" : "none in bias direction"}</div>
        </div>
        <div className={`smc-mc smc-mc--${zTone}`}>
          <div className="label-cap">DEALING RANGE</div>
          <div className="mono smc-mc-v">{r.zone.toUpperCase()}</div>
          <div className="mono dim2">{r.pct}% of range · eq {smcMoney(r.eq)}</div>
        </div>
        <div className={`smc-mc smc-mc--${r.ote_active ? "gn" : "amb"}`}>
          <div className="label-cap">OTE ZONE</div>
          <div className={`mono smc-mc-v ${r.ote_active ? "up" : ""}`}>{smcMoney(r.ote_lo)}–{smcMoney(r.ote_hi)}</div>
          <div className="mono dim2">{r.ote_active ? "price in OTE now" : "0.62–0.79 retrace"}</div>
        </div>
      </div>
      {m.htf_levels && m.htf_levels.length ? (
        <table className="dtable">
          <thead><tr><th>HTF Level</th><th className="r">Price</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {m.htf_levels.map((lv, i) => (
              <tr key={i}>
                <td className="mono">{lv.label}</td>
                <td className="r mono">{smcMoney(lv.price)}</td>
                <td className="mono dim">{lv.type}</td>
                <td><Pill tone={lv.state === "swept" ? "rd" : "cy"} small>{lv.state}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <div className="mono dim" style={{ fontSize: 11 }}>
        Macro read: {m.tf} structure is <b className={m.bias === "bull" ? "up" : m.bias === "bear" ? "dn" : "warn"}>{m.bias}</b>, price in <b className={zTone === "gn" ? "up" : zTone === "rd" ? "dn" : "warn"}>{r.zone}</b> ({r.pct}% of the {smcMoney(r.lo)}–{smcMoney(r.hi)} dealing range).
        {draw ? <> Draw on liquidity is {draw.side} at {smcMoney(draw.price)}.</> : null}
      </div>
    </div>
  );
}

// Premium / Discount / Equilibrium zones
function SMCZones({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="dealing range" />;
  const r = m.range;
  const hi = r.hi, lo = r.lo, eq = r.eq, spot = m.cur_close;
  const span = Math.max(hi - lo, 1e-6);
  const q75 = lo + span * 0.75, q25 = lo + span * 0.25;
  const ob = (m.order_blocks || []).filter(o => o.type === "demand" && o.hi >= lo && o.lo <= hi)
    .sort((a, b) => Math.abs((a.lo + a.hi) / 2 - spot) - Math.abs((b.lo + b.hi) / 2 - spot))[0];
  const zTone = r.zone === "discount" ? "gn" : r.zone === "premium" ? "rd" : "amb";
  const W=520, H=240, padT=18, padB=18, axisX=150, barX=176, barW=120;
  const y=p=> padT + (1-(p-lo)/span)*(H-padT-padB);
  const pct = r.pct;
  return (
    <div className="smc-zones2">
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="smc-zsvg">
        <defs>
          <linearGradient id="smc-prem" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.30"/><stop offset="100%" stopColor="var(--rd)" stopOpacity="0.06"/></linearGradient>
          <linearGradient id="smc-disc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.06"/><stop offset="100%" stopColor="var(--gn)" stopOpacity="0.30"/></linearGradient>
        </defs>
        <rect x={barX} y={y(hi)} width={barW} height={y(eq)-y(hi)} fill="url(#smc-prem)"/>
        <rect x={barX} y={y(eq)} width={barW} height={y(lo)-y(eq)} fill="url(#smc-disc)"/>
        <rect x={barX} y={y(eq)-1} width={barW} height="2" fill="var(--amb)"/>
        {ob && <rect x={barX} y={y(ob.hi)} width={barW} height={Math.max(3,y(ob.lo)-y(ob.hi))} fill="var(--cy)" opacity="0.4"/>}
        <rect x={barX} y={y(hi)} width={barW} height={y(lo)-y(hi)} fill="none" stroke="var(--glass-line)"/>
        {[["range high · liq",hi,"var(--cy)"],["75% premium",q75,"var(--ink-3)"],["EQ 50% · fair value",eq,"var(--amb)"],["25% discount",q25,"var(--ink-3)"],["range low · liq",lo,"var(--rd)"]].map((rw,i)=>(
          <g key={i}>
            <line x1={axisX} y1={y(rw[1])} x2={barX} y2={y(rw[1])} stroke={rw[2]} strokeWidth="1" opacity="0.5"/>
            <text x={axisX-6} y={y(rw[1])+3} fontSize="9.5" className="mono" textAnchor="end" fill={rw[2]}>{rw[0]}</text>
            <text x={barX+barW+6} y={y(rw[1])+3} fontSize="9.5" className="mono" fill={rw[2]}>${rw[1].toFixed(2)}</text>
          </g>
        ))}
        {ob && <text x={barX+barW/2} y={y((ob.hi+ob.lo)/2)+3} fontSize="8.5" className="mono" textAnchor="middle" fill="var(--cy)">OB {smcMoney(ob.lo)}–{smcMoney(ob.hi)}</text>}
        <text x={barX+8} y={y((hi+eq)/2)} fontSize="10" className="mono" fill="var(--rd)" opacity="0.7" transform={`rotate(-90 ${barX+8} ${y((hi+eq)/2)})`}>PREMIUM · sell</text>
        <text x={barX+8} y={y((eq+lo)/2)} fontSize="10" className="mono" fill="var(--gn)" opacity="0.7" transform={`rotate(-90 ${barX+8} ${y((eq+lo)/2)})`}>DISCOUNT · buy</text>
        <line x1={barX-6} y1={y(spot)} x2={barX+barW+6} y2={y(spot)} stroke="var(--copper)" strokeWidth="2" style={{filter:"drop-shadow(0 0 4px var(--copper))"}}/>
        <circle cx={barX+barW} cy={y(spot)} r="4" fill="var(--copper)" style={{filter:"drop-shadow(0 0 6px var(--copper))"}}/>
        <rect x={barX+barW+34} y={y(spot)-9} width="74" height="18" rx="9" fill="color-mix(in oklab,var(--copper) 18%,transparent)" stroke="var(--copper)" strokeWidth="0.8"/>
        <text x={barX+barW+71} y={y(spot)+3} fontSize="9" className="mono" textAnchor="middle" fill="var(--copper)">SPOT ${spot.toFixed(2)}</text>
      </svg>
      <div className="smc-zone-read">
        <div className="kpi-row" style={{gridTemplateColumns:"repeat(3,1fr)"}}>
          <KpiTile label="Dealing range" value={`${smcMoney(lo)}–${smcMoney(hi)}`} tone="ink" sub="swing low → high" />
          <KpiTile label="Equilibrium" value={smcMoney(eq)} tone="amb" sub="50% · fair value" />
          <KpiTile label="Current zone" value={r.zone.toUpperCase()} tone={zTone} sub={`${pct}% of range`} />
        </div>
        <div className="mono dim" style={{fontSize:11,marginTop:8}}>
          Price sits at <b>{pct}%</b> of the dealing range — <b className={zTone==="gn"?"up":zTone==="rd"?"dn":"warn"}>{r.zone}</b>. SMC longs favor discount (&lt;45%)
          {ob ? <>; nearest demand OB is <b className="cy">{smcMoney(ob.lo)}–{smcMoney(ob.hi)}</b> ({ob.state}).</> : "."}
        </div>
      </div>
    </div>
  );
}

function SMCMicroChart({ m }) {
  const W = 280, H = 110, padX = 8, padY = 10;
  if (!_smcUsable(m) || !Array.isArray(m.spark) || m.spark.length < 4) {
    return <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}><text x={W/2} y={H/2} fontSize="9" className="mono" textAnchor="middle" fill="var(--ink-3)">no live bars</text></svg>;
  }
  const s = m.spark;
  const draw = m.draw_on_liquidity;
  const ob = (m.order_blocks || []).filter(o => o.type === "demand")[0];
  const lvls = [m.range.lo, m.range.hi, m.cur_close].concat(draw ? [draw.price] : []).concat(ob ? [ob.lo, ob.hi] : []);
  const lo = Math.min(Math.min(...s), ...lvls);
  const hi = Math.max(Math.max(...s), ...lvls);
  const span = Math.max(hi - lo, 1e-6);
  const x = i => padX + (i / (s.length - 1)) * (W - padX * 2);
  const y = p => padY + (1 - (p - lo) / span) * (H - padY * 2);
  const pts = s.map((c, i) => `${x(i).toFixed(1)},${y(c).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} preserveAspectRatio="xMidYMid meet">
      {ob && <rect x={padX} y={y(ob.hi)} width={W - padX * 2} height={Math.max(2, y(ob.lo) - y(ob.hi))} fill="var(--cy)" opacity="0.18" />}
      {ob && <text x={padX + 2} y={y(ob.hi) - 2} fontSize="8" className="mono" fill="var(--cy)">OB {smcMoney(ob.lo)}</text>}
      {draw && <><line x1="0" y1={y(draw.price)} x2={W} y2={y(draw.price)} stroke="var(--amb)" strokeDasharray="3 3" opacity="0.6" /><text x="4" y={y(draw.price) - 2} fontSize="8" className="mono" fill="var(--amb)">DRAW {smcMoney(draw.price)}</text></>}
      <polyline fill="none" stroke="var(--copper)" strokeWidth="1.5" points={pts} />
      <circle cx={x(s.length - 1)} cy={y(s[s.length - 1])} r="2.5" fill="var(--copper)" />
    </svg>
  );
}

function OBTable({ m, state }) {
  if (!_smcUsable(m) || !m.order_blocks.length) return <SmcEmpty state={state} what="order blocks" />;
  const cur = m.cur_close;
  return (
    <table className="dtable">
      <thead>
        <tr><th>Zone</th><th>Type</th><th>State</th><th>Distance</th></tr>
      </thead>
      <tbody>
        {m.order_blocks.map((r, i) => {
          const mid = (r.lo + r.hi) / 2;
          const dist = ((mid - cur) / cur * 100);
          return (
            <tr key={i}>
              <td className="mono">{smcMoney(r.lo)}–{smcMoney(r.hi)}</td>
              <td><Pill tone={r.type === "demand" ? "gn" : "rd"} small>{r.type.toUpperCase()}</Pill></td>
              <td><span className={`ob-mit ob-mit--${r.state === "fresh" ? "fresh" : r.state === "held" ? "tapped" : "spent"}`}><span className="ob-mit-dot" />{r.state === "fresh" ? "Fresh" : r.state === "held" ? "Tapped · held" : "Mitigated"}</span></td>
              <td className="mono dim">{dist >= 0 ? "+" : ""}{dist.toFixed(1)}% · {r.date}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function StructureLog({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="structure" />;
  const evts = (m.structure.events || []).slice().reverse();
  const fvgs = m.fvgs || [];
  return (
    <div>
      <div className="struct-log">
        {evts.length ? evts.map((e, i) => (
          <div key={i} className={`sl-row sl-${e.dir === "up" ? "gn" : "rd"}`}>
            <span className="mono dim2 sl-when">{e.date}</span>
            <span className="mono sl-evt">{e.evt} · {e.dir === "up" ? "↑" : "↓"} {e.tf}</span>
            <span className="mono copper sl-px">{smcMoney(e.price)}</span>
            <span className="mono dim sl-impact">{e.evt === "CHoCH" ? "character change" : "continuation"}</span>
          </div>
        )) : <div className="smc-empty mono dim2">— no break-of-structure in this window</div>}
      </div>
      <div className="label-cap" style={{ marginTop: 12, marginBottom: 4 }}>Fair Value Gaps</div>
      {fvgs.length ? (
        <table className="dtable">
          <thead><tr><th>Gap</th><th>Type</th><th>State</th><th>Date</th></tr></thead>
          <tbody>{fvgs.map((g, i) => (
            <tr key={i}>
              <td className="mono">{smcMoney(g.lo)}–{smcMoney(g.hi)}</td>
              <td><Pill tone={g.type === "bull" ? "gn" : "rd"} small>{g.type.toUpperCase()}</Pill></td>
              <td><Pill tone={g.state === "unfilled" ? "cy" : "ink"} small>{g.state}</Pill></td>
              <td className="mono dim">{g.date}</td>
            </tr>
          ))}</tbody>
        </table>
      ) : <div className="smc-empty mono dim2">— no fair-value gaps detected</div>}
    </div>
  );
}

function LiquiditySweeps({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="liquidity" />;
  const L = m.liquidity;
  const buy = (L.buyside || [])[0];
  const sell = (L.sellside || [])[0];
  // overhead resting liquidity = nearest equal-high cluster ABOVE price (none → honest "—")
  const eqh = (L.equal_highs || []).filter(c => c.price > m.cur_close).sort((a, b) => a.price - b.price)[0] || null;
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
      <KpiTile label="Sell-side · prior lows" value={sell ? smcMoney(sell.price) : "—"} tone="amb" sub={sell ? "resting below price" : "none below"} />
      <KpiTile label="Buy-side · prior highs" value={buy ? smcMoney(buy.price) : "—"} tone="copper" sub={buy ? ((buy.state || "untapped") + " · target above") : "none above"} />
      <KpiTile label="Equal highs · resting liq" value={eqh ? smcMoney(eqh.price) : "—"} tone="amb" sub={eqh ? `${eqh.touches}-touch · magnet above` : "none above price"} />
    </div>
  );
}

function MTFScreener({ m, state }) {
  if (!_smcUsable(m) || !m.mtf || !m.mtf.length) return <SmcEmpty state={state} what="MTF bias" />;
  return (
    <table className="dtable">
      <thead>
        <tr><th>TF</th><th>Bias</th><th>Trend</th><th>Read</th></tr>
      </thead>
      <tbody>
        {m.mtf.map((r, i) => {
          const t = r.bias === "BULL" ? "gn" : r.bias === "BEAR" ? "rd" : "amb";
          const tr = r.bias === "BULL" ? "↑" : r.bias === "BEAR" ? "↓" : "→";
          return (
            <tr key={i}>
              <td className="mono"><b>{r.tf}</b></td>
              <td><Pill tone={t} small>{r.bias}</Pill></td>
              <td className={`mono ${t === "gn" ? "up" : t === "rd" ? "dn" : "warn"}`}>{tr}</td>
              <td className="mono dim">{r.note}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ────────────────────────────────────────────────────────────
// RISK — VaR, Kelly, drawdown, stress, liquidity
// ────────────────────────────────────────────────────────────
// real account NAV (live equity → MyPF rollup → labeled demo)
function _riskNav() {
  const bv = (window.__BV && typeof window.__BV.nav === "number") ? window.__BV.nav : null;
  if (bv && bv > 0) return { nav: bv, demo: false };
  try { if (window.MyPF) { const s = window.MyPF.summarize(window.MyPF.combined()); if (s && s.totalValue > 0) return { nav: s.totalValue, demo: false }; } } catch (e) {}
  return { nav: 100000, demo: true };
}
// real risk model from engines/risk.py via /api/pattern/risk
function useRiskModel(ticker, mode) {
  const sym = (ticker && ticker.symbol) || "", md = (mode || "SWING").toUpperCase();
  const key = "risk|" + sym + "|" + md;
  const read = () => { try { return (window.__BV && window.__BV.patternCached && window.__BV.patternCached("risk", sym, md)) || null; } catch (e) { return null; } };
  const [real, setReal] = useStateSMC(read);
  useEffSMC(() => {
    let on = true; setReal(read());
    try { if (window.__BV && window.__BV.fetchPattern && sym) window.__BV.fetchPattern("risk", sym, md).then(d => { if (on) setReal(d); }); } catch (e) {}
    return () => { on = false; };
  }, [key]);
  let st = "mock";
  if (real && typeof real === "object" && ("ok" in real)) st = "loaded";
  else if (real === null && window.__BV && window.__BV.fetchPattern) st = "loading";
  return { rm: real, state: st };
}
// position sizing from the real coherent ladder + NAV + ledger (Kelly)
function riskSizing(ticker, mode) {
  const md = (mode || "SWING").toUpperCase();
  const t2 = window.modeAdjust ? window.modeAdjust(ticker, md) : ticker;
  const L = window.coherentLevels ? window.coherentLevels(t2) : null;
  const { nav, demo } = _riskNav();
  if (!L || L.valid === false || !(L.stop > 0 && L.pivot > L.stop && L.t1 > L.pivot)) return { nav, demo, ok: false };
  const entry = +(L.pivot * 1.002).toFixed(2), stop = L.stop, t1 = L.t1;
  const risk = Math.max(0.01, entry - stop);
  const shares = Math.max(1, Math.round(Math.round(nav * 0.0039) / risk));
  const notional = shares * entry, maxLoss = shares * risk;
  const rr = (t1 - entry) / risk;
  const ss = ticker.setupStats || {}, wr = ss.winRate;
  const kelly = (wr != null && rr > 0) ? Math.max(0, (wr * rr - (1 - wr)) / rr) : null;
  return { ok: true, nav, demo, entry, stop, t1, risk, shares, notional, maxLoss, rr, kelly, wr, n: ss.n,
           navPct: notional / nav * 100, lossNavPct: maxLoss / nav * 100, pctToStop: risk / entry * 100 };
}

function LensRisk({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("rk-1"); const s2 = useStateToggle("rk-2");
  const s3 = useStateToggle("rk-3"); const s4 = useStateToggle("rk-4");
  const s5 = useStateToggle("rk-5");
  const { rm, state } = useRiskModel(ticker, mode);
  const sz = riskSizing(ticker, mode);
  const erD = ticker.earnings && ticker.earnings.days != null ? ticker.earnings.days : null;
  const gatesOK = sz.ok && sz.lossNavPct <= 0.75 && sz.navPct <= 10;
  const hot = (rm && rm.ok && rm.beta != null && rm.beta > 2) || (sz.ok && sz.lossNavPct > 0.75);
  const verdict = !sz.ok ? "—" : hot ? "HOT" : gatesOK ? "OK" : "REVIEW";
  const vTone = verdict === "OK" ? "gn" : verdict === "HOT" ? "rd" : "amb";

  return (
    <div className="lens lens--risk">
      <div className="hero risk-hero">
        <div className="th-left">
          <div className="label-cap">Risk read · per-trade · {mode}{rm && rm.ok ? " · " + rm.tf : ""}</div>
          <div className="th-score">
            <div className="th-score-num mono">{verdict}</div>
            {sz.ok && <Pill tone={gatesOK ? "gn" : "rd"} dot>{gatesOK ? "within gates" : "over size cap"}</Pill>}
            {rm && rm.ok && rm.beta != null && <Pill tone={rm.beta > 2 ? "rd" : rm.beta > 1.3 ? "amb" : "gn"} small>β {rm.beta}</Pill>}
            {erD != null && erD <= 10 && <Pill tone="amb" small>ER in {erD}d · cap size</Pill>}
          </div>
        </div>
        <div className="th-right">
          <LossCone rm={rm} />
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={1} title="Loss-Distribution Cones"
          sub={`${mode} horizon · 1σ / 2σ / 3σ · from 126d realized vol`}
          style={headerStyle} right={<StateToggle name="rk-1" />} tip="How far price typically swings over the hold, from real 126-day volatility. 1σ ≈ 68% of outcomes, 2σ ≈ 95%, 3σ ≈ 99%." />
        <StateWrap state={s1.value} source="vol engine · 126d realized">
          <div className="lens-pad"><RiskCones rm={rm} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="Kelly · Sizing Metrics"
          sub="position size from the real ladder + ledger edge"
          style={headerStyle} right={<StateToggle name="rk-2" />} tip="Kelly = growth-optimal bet size from your win-rate & R:R. Needs ledger history; half-Kelly is the safer default." />
        <StateWrap state={s2.value} source="risk engine · ledger + NAV">
          <div className="lens-pad"><RiskSizing sz={sz} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="VaR · CVaR · Sharpe"
          sub={`${mode} horizon · parametric + historical · from real returns`}
          style={headerStyle} right={<StateToggle name="rk-3" />} tip="VaR: the loss you won't exceed 95% of days. CVaR: the average loss on the worst 5% of days. Sharpe/Sortino: risk-adjusted return (annualized)." />
        <StateWrap state={s3.value} source="risk engine · 126d returns">
          <div className="lens-pad"><VarTable rm={rm} sz={sz} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="Stress Scenarios"
          sub="beta- and vol-scaled shocks on this position"
          style={headerStyle} right={<StateToggle name="rk-4" />} tip="What each shock does to THIS position, scaled by the stock's real beta and volatility." />
        <StateWrap state={s4.value} source="scenario engine · real β + vol">
          <div className="lens-pad"><StressGrid rm={rm} sz={sz} state={state} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Liquidity · β exposure"
          sub="spread · ADV participation · beta"
          style={headerStyle} right={<StateToggle name="rk-5" />} />
        <StateWrap state={s5.value} source="quotes + risk engine">
          <div className="lens-pad"><RiskLiquidity ticker={ticker} sz={sz} rm={rm} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Cross-Lens Confluence" style={headerStyle} />
        <div className="lens-pad">
          {sz.ok ? <CrossLens lead="rd" cells={[
            { lens: "Risk", verdict: verdict, tone: vTone, note: gatesOK ? "size within gates" : "over size cap" },
            { lens: "Plan", verdict: sz.rr >= 1.5 ? "READY" : "THIN", tone: sz.rr >= 1.5 ? "gn" : "amb", note: `R ${sz.rr.toFixed(2)} · stop $${sz.stop.toFixed(2)}` },
            { lens: "VaR(1d)", verdict: rm && rm.ok ? `−${rm.var95_pct}%` : "—", tone: "amb", note: rm && rm.ok ? "95% parametric" : "—" },
            { lens: "Max loss", verdict: `$${Math.round(sz.maxLoss)}`, tone: "rd", note: `${sz.lossNavPct.toFixed(2)}% of NAV` },
            { lens: "Beta", verdict: rm && rm.ok && rm.beta != null ? String(rm.beta) : "—", tone: rm && rm.ok && rm.beta > 2 ? "rd" : "gn", note: "vs SPY" },
          ]} /> : <SmcEmpty state={state} what="risk metrics" />}
        </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · Risk</span>
        {sz.ok ? <span className="mono">
          Max loss <b className="dn">${Math.round(sz.maxLoss)}</b> = {sz.lossNavPct.toFixed(2)}% of NAV{sz.demo ? " (demo)" : ""}
          {rm && rm.ok ? <> · VaR(1d 95%) <b className="warn">−{rm.var95_pct}%</b> · vol {rm.vol_ann_pct}% ann · β {rm.beta != null ? rm.beta : "—"}</> : null}
          {". "}<b className={vTone === "gn" ? "up" : vTone === "rd" ? "dn" : "warn"}>{verdict === "OK" ? "Within risk gates." : verdict === "HOT" ? "Hot — trim size." : "Review size."}</b>
        </span> : <span className="mono dim2">No coherent ladder for {(ticker && ticker.symbol) || "this name"} — sizing & risk can't be computed without fabricating levels.</span>}
      </div>
    </div>
  );
}

function LossCone({ rm }) {
  const s1 = (rm && rm.ok && rm.cones && rm.cones[0]) ? rm.cones[0].pct : null;
  const s3 = (rm && rm.ok && rm.cones && rm.cones[2]) ? rm.cones[2].pct : null;
  return (
    <svg viewBox="0 0 280 110" width="280" height="110" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="lc-gn" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--gn)" stopOpacity="0.35" /><stop offset="100%" stopColor="var(--gn)" stopOpacity="0" /></linearGradient>
        <linearGradient id="lc-rd" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stopColor="var(--rd)" stopOpacity="0.35" /><stop offset="100%" stopColor="var(--rd)" stopOpacity="0" /></linearGradient>
      </defs>
      <line x1="20" y1="55" x2="270" y2="55" stroke="var(--line)" strokeDasharray="3 3" />
      <path d="M 20 55 Q 130 14 270 14 L 270 55 Z" fill="url(#lc-gn)" />
      <path d="M 20 55 Q 130 96 270 96 L 270 55 Z" fill="url(#lc-rd)" />
      <path d="M 20 55 Q 130 30 270 30" stroke="var(--gn)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
      <path d="M 20 55 Q 130 78 270 78" stroke="var(--rd)" strokeWidth="1.6" fill="none" style={{ filter: "drop-shadow(0 0 5px var(--rd))" }} />
      <circle cx="20" cy="55" r="4" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
      <text x="266" y="11" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">+3σ {s3 != null ? "+" + s3 + "%" : "—"}</text>
      <text x="266" y="27" fontSize="9.5" className="mono" textAnchor="end" fill="var(--gn)">+1σ {s1 != null ? "+" + s1 + "%" : "—"}</text>
      <text x="266" y="82" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">−1σ {s1 != null ? "−" + s1 + "%" : "—"}</text>
      <text x="266" y="106" fontSize="9.5" className="mono" textAnchor="end" fill="var(--rd)">−3σ {s3 != null ? "−" + s3 + "%" : "—"}</text>
    </svg>
  );
}

function RiskSizing({ sz }) {
  if (!sz.ok) return <SmcEmpty state="loaded" what="sizing (no coherent ladder)" />;
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      <KpiTile label="Raw Kelly" value={sz.kelly != null ? (sz.kelly * 100).toFixed(0) + "%" : "—"} tone="amb" sub={sz.kelly != null ? `f* · n=${sz.n}` : "no ledger edge"} />
      <KpiTile label="½ Kelly" value={sz.kelly != null ? (sz.kelly * 50).toFixed(0) + "%" : "—"} tone="copper" sub="discipline haircut" />
      <KpiTile label="Size · % NAV" value={`${sz.navPct.toFixed(1)}%`} tone={sz.navPct > 10 ? "rd" : sz.navPct > 7 ? "amb" : "gn"} sub={`${sz.shares} sh${sz.demo ? " · demo NAV" : ""}`} />
      <KpiTile label="Max loss" value={`$${Math.round(sz.maxLoss)}`} tone="rd" sub={`${sz.lossNavPct.toFixed(2)}% of NAV`} />
    </div>
  );
}

function RiskCones({ rm, state }) {
  if (!rm || !rm.ok) return <SmcEmpty state={state} what="volatility cones" />;
  const cur = rm.cur_close;
  const band = (c) => `$${c.lo.toFixed(2)} — $${c.hi.toFixed(2)}`;
  const tone = ["ink", "amb", "rd"];
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      {rm.cones.map((c, i) => (
        <KpiTile key={i} label={`${rm.hd === 1 ? "1d" : rm.hd + "d"} · ${c.k}σ`} value={`±${c.pct}%`} tone={tone[i]} sub={band(c)} />
      ))}
      <KpiTile label="Vol · annualized" value={`${rm.vol_ann_pct}%`} tone="amb" sub={`${rm.vol_1d_pct}% daily`} />
    </div>
  );
}

function VarTable({ rm, sz, state }) {
  if (!rm || !rm.ok) return <SmcEmpty state={state} what="VaR metrics" />;
  const notional = sz.ok ? sz.notional : 0;
  const dollar = (p) => sz.ok ? `−$${Math.round(p / 100 * notional)} (${sz.shares} sh)` : "—";
  const rows = [
    { metric: `VaR · ${rm.hd === 1 ? "1d" : rm.hd + "d"} · 95% (parametric)`, v: `−${rm.var95_pct}%`, abs: dollar(rm.var95_pct), tone: rm.var95_pct > 5 ? "rd" : "amb" },
    { metric: "VaR · 95% (historical)", v: `−${rm.var95_hist_pct}%`, abs: dollar(rm.var95_hist_pct), tone: "amb" },
    { metric: "CVaR · 95% (tail avg)", v: `−${rm.cvar95_pct}%`, abs: dollar(rm.cvar95_pct), tone: "rd" },
    { metric: "VaR · 99% (parametric)", v: `−${rm.var99_pct}%`, abs: dollar(rm.var99_pct), tone: "rd" },
    { metric: "Sharpe (126d, ann)", v: rm.sharpe_126d.toFixed(2), abs: "risk-adj return", tone: rm.sharpe_126d >= 1 ? "gn" : "amb" },
    { metric: "Sortino (126d, ann)", v: rm.sortino_126d.toFixed(2), abs: "downside-adj", tone: rm.sortino_126d >= 1 ? "gn" : "amb" },
    { metric: "Max drawdown (1yr)", v: `${rm.max_dd_pct}%`, abs: "peak-to-trough", tone: "rd" },
  ];
  return (
    <table className="dtable">
      <thead><tr><th>Metric</th><th className="r">Value</th><th>Absolute</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}><td className="mono">{r.metric}</td><td className={`r mono tabular kpi-tone--${r.tone}`}>{r.v}</td><td className="mono dim">{r.abs}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function StressGrid({ rm, sz, state }) {
  if (!rm || !rm.ok || !sz.ok) return <SmcEmpty state={state} what="stress scenarios" />;
  const beta = rm.beta != null ? rm.beta : 1.0, vol = rm.vol_1d_pct / 100, stopMove = sz.pctToStop / 100;
  const scen = [
    { s: "Market −2σ day", m: -0.02 * beta },
    { s: "Market −3σ gap", m: -0.03 * beta },
    { s: "Vol doubles (panic)", m: -2 * vol },
    { s: "Sector −5%", m: -0.05 * Math.min(beta, 1.6) },
    { s: "Earnings gap −10%", m: -0.10 },
    { s: "Stop hit", m: -stopMove },
  ];
  const outcomes = ["P&L", "% NAV", "Stop hit?", "Action"];
  const grid = scen.map(x => {
    const pnl = sz.notional * x.m, navp = pnl / sz.nav * 100, stopHit = Math.abs(x.m) >= stopMove;
    const action = navp <= -1.0 ? "flatten" : stopHit ? "OCO exit" : navp <= -0.5 ? "trim 25%" : "hold";
    return [
      { v: `−$${Math.abs(Math.round(pnl))}`, tone: navp <= -1 ? "rd" : "amb" },
      { v: `${navp.toFixed(2)}%`, tone: navp <= -1 ? "rd" : "amb" },
      { v: stopHit ? "YES" : "no", tone: stopHit ? "rd" : "gn" },
      { v: action, tone: action === "hold" ? "gn" : action === "flatten" ? "rd" : "amb" },
    ];
  });
  return (
    <div className="stress-grid">
      <div className="sg-corner" />
      {outcomes.map((o, i) => (<div key={i} className="sg-col-hdr mono label-cap">{o}</div>))}
      {scen.map((x, r) => (
        <React.Fragment key={r}>
          <div className="sg-row-hdr mono">{x.s}</div>
          {grid[r].map((c, ci) => (<div key={ci} className={`sg-cell sg-${c.tone}`}>{c.v}</div>))}
        </React.Fragment>
      ))}
    </div>
  );
}

function RiskLiquidity({ ticker, sz, rm }) {
  const spread = (typeof ticker.spread === "number" && ticker.spread > 0) ? ticker.spread : null;
  const dvol = (typeof ticker.dvol === "number" && ticker.dvol > 0) ? ticker.dvol : null;
  const partPct = (dvol && sz.ok) ? sz.notional / dvol * 100 : null;
  const advFmt = dvol ? (dvol >= 1e9 ? "$" + (dvol / 1e9).toFixed(1) + "B" : "$" + (dvol / 1e6).toFixed(0) + "M") : "—";
  return (
    <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
      <KpiTile label="Spread" value={spread != null ? `${spread.toFixed(2)}%` : "—"} tone={spread == null ? "ink" : spread <= 0.1 ? "gn" : spread <= 0.5 ? "amb" : "rd"} sub={spread != null ? "bid/ask" : "no quote"} />
      <KpiTile label="ADV ($)" value={advFmt} tone="ink" sub="avg daily $-vol" />
      <KpiTile label="Participation" value={partPct != null ? (partPct < 0.01 ? "<0.01%" : partPct.toFixed(2) + "%") : "—"} tone={partPct == null ? "ink" : partPct < 1 ? "gn" : "amb"} sub="order ÷ ADV" />
      <KpiTile label="Beta · vs SPY" value={rm && rm.ok && rm.beta != null ? rm.beta.toFixed(2) : "—"} tone={rm && rm.ok && rm.beta > 2 ? "rd" : rm && rm.ok && rm.beta > 1.3 ? "amb" : "gn"} sub="position β" />
    </div>
  );
}

window.LensSMC = LensSMC;
window.LensRisk = LensRisk;

// Trend-state machine across timeframes
function SMCTrendState({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="trend state" />;
  const rows = m.mtf || [];
  const flip = m.structure.last_bos ? m.structure.last_bos.price : null;
  const bull = rows.filter(r => r.bias === "BULL").length;
  return (
    <div className="smc-sub">
      <div className="smc-ts-strip">
        {rows.map((r, i) => {
          const t = r.bias === "BULL" ? "gn" : r.bias === "BEAR" ? "rd" : "amb";
          return (
            <div key={i} className={`smc-ts smc-ts--${t}`}>
              <span className="mono smc-ts-tf">{r.tf}</span>
              <span className={`mono smc-ts-bias kpi-tone--${t}`}>{r.bias}</span>
              <span className="mono dim2">{r.note}</span>
            </div>
          );
        })}
      </div>
      <div className="mono dim" style={{ fontSize: 11 }}>{m.tf} regime: <b className={m.bias === "bull" ? "up" : m.bias === "bear" ? "dn" : "warn"}>{m.bias.toUpperCase()}</b> ({bull}/{rows.length} TF bullish).{flip ? <> Flips on a close {m.bias === "bull" ? "below" : "above"} <b>{smcMoney(flip)}</b>.</> : null}</div>
    </div>
  );
}

// Confluence stacking — A+ zones where multiple SMC factors align
function SMCConfluence({ m, state }) {
  if (!_smcUsable(m) || !m.order_blocks.length) return <SmcEmpty state={state} what="confluence zones" />;
  const r = m.range, fvgs = m.fvgs || [], atr = m.atr || 1;
  const zones = m.order_blocks.slice(0, 4).map(ob => {
    const mid = (ob.lo + ob.hi) / 2;
    const factors = [ob.type === "demand" ? "OB+" : "OB−"];
    if (ob.state !== "mitigated") factors.push("unmitigated");
    if (fvgs.some(g => g.hi >= ob.lo && g.lo <= ob.hi)) factors.push("FVG");
    if (mid >= r.ote_lo && mid <= r.ote_hi) factors.push("OTE");
    factors.push(mid < r.eq ? "discount" : "premium");
    if ((m.htf_levels || []).some(lv => Math.abs(lv.price - mid) < atr * 0.6)) factors.push("HTF lvl");
    const n = factors.length;
    const grade = n >= 5 ? "A+" : n >= 4 ? "A" : n >= 3 ? "B" : "C";
    const tone = grade[0] === "A" ? "gn" : grade === "B" ? "amb" : "rd";
    return { px: `${smcMoney(ob.lo)}–${smcMoney(ob.hi)}`, factors, grade, tone, n };
  }).sort((a, b) => b.n - a.n);
  const best = zones[0];
  return (
    <div className="smc-sub">
      {zones.map((z, i) => (
        <div key={i} className={`smc-conf smc-conf--${z.tone}`}>
          <div className="smc-conf-grade">{z.grade}</div>
          <div className="smc-conf-body">
            <div className="mono smc-conf-px"><b>{z.px}</b> <span className="dim2">· {z.factors.length} factors</span></div>
            <div className="smc-conf-tags">{z.factors.map((f, j) => <span key={j} className="smc-conf-tag mono">{f}</span>)}</div>
          </div>
        </div>
      ))}
      {best && <div className="mono dim" style={{ fontSize: 11 }}>The {best.px} zone stacks {best.n} factors ({best.factors.join(" · ")}) → <b className={best.tone === "gn" ? "up" : "warn"}>{best.grade}</b>. Highest-confluence zone on this timeframe.</div>}
    </div>
  );
}

// Mitigation hit-rate + liquidity heatmap
function SMCMitigationHeat({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="liquidity density" />;
  const zs = m.zone_stats || { demand: {}, supply: {}, fvg: {} };
  // sample-aware: n<10 → greyed + asterisk (don't dress up a 5-sample rate as edge)
  const rateCell = (rate, tested) => {
    if (rate == null) return { tone: "ink", label: "—" };
    const low = (tested || 0) < 10;
    return { tone: low ? "ink" : rate >= 70 ? "gn" : rate >= 50 ? "amb" : "rd", label: rate + "%" + (low ? "*" : "") };
  };
  const dC = rateCell(zs.demand.rate, zs.demand.tested), sC = rateCell(zs.supply.rate, zs.supply.tested), fC = rateCell(zs.fvg.rate, zs.fvg.total);
  const anyLow = [zs.demand.tested, zs.supply.tested, zs.fvg.total].some(t => (t || 0) < 10);
  // resting-liquidity density: each pool weighted by proximity to price + equal-touch count
  const L = m.liquidity, cur = m.cur_close;
  const pools = []
    .concat((L.buyside || []).map(b => ({ price: b.price, side: "buy", w: (b.equal || 1) })))
    .concat((L.sellside || []).map(s => ({ price: s.price, side: "sell", w: 1 })))
    .concat([{ price: cur, side: "spot", w: 0 }]);
  const maxw = Math.max(1, ...pools.map(p => p.w));
  pools.sort((a, b) => b.price - a.price);
  return (
    <div className="smc-2col">
      <div>
        <div className="label-cap" style={{ marginBottom: 6 }}>ZONE RESPECT · replayed on {m.bars} bars</div>
        <table className="dtable">
          <thead><tr><th>Zone</th><th className="r">Tested</th><th className="r">Respected</th><th className="r">Rate</th></tr></thead>
          <tbody>
            <tr><td className="mono">Demand OB</td><td className="r mono">{zs.demand.tested ?? 0}</td><td className="r mono">{zs.demand.respected ?? 0}</td><td className={`r mono kpi-tone--${dC.tone}`}>{dC.label}</td></tr>
            <tr><td className="mono">Supply OB</td><td className="r mono">{zs.supply.tested ?? 0}</td><td className="r mono">{zs.supply.respected ?? 0}</td><td className={`r mono kpi-tone--${sC.tone}`}>{sC.label}</td></tr>
            <tr><td className="mono">FVG fill</td><td className="r mono">{zs.fvg.total ?? 0}</td><td className="r mono">{zs.fvg.filled ?? 0}</td><td className={`r mono kpi-tone--${fC.tone}`}>{fC.label}</td></tr>
          </tbody>
        </table>
        <div className="mono dim2" style={{ fontSize: 10, marginTop: 6 }}>Respect = price re-entered the zone then closed back out within 3 bars. Replayed on this timeframe's real bars.{anyLow ? " * n<10 — low confidence." : ""}</div>
      </div>
      <div>
        <div className="label-cap" style={{ marginBottom: 6 }}>RESTING LIQUIDITY · density</div>
        <div className="smc-heat">
          {pools.map((p, i) => (
            <div key={i} className="smc-heat-row">
              <span className="mono smc-heat-px">{smcMoney(p.price)}</span>
              <div className="smc-heat-bar"><div className={`smc-heat-fill smc-heat--${p.side === "buy" ? "buy" : p.side === "sell" ? "sell" : "spot"}`} style={{ width: `${p.side === "spot" ? 8 : 25 + (p.w / maxw) * 65}%` }} /></div>
              <span className="mono dim2">{p.side}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// SMC alerts
function SMCAlerts({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="alert conditions" />;
  const obFresh = (m.order_blocks || []).find(o => o.state !== "mitigated");
  const fvgU = (m.fvgs || []).find(g => g.state === "unfilled");
  const sell = (m.liquidity.sellside || [])[0];
  const buy = (m.liquidity.buyside || [])[0];
  const flip = m.structure.last_bos ? m.structure.last_bos.price : null;
  const alerts = [
    obFresh && [`price entering ${obFresh.type} OB ${smcMoney(obFresh.lo)}–${smcMoney(obFresh.hi)}`, "armed", obFresh.type === "demand" ? "gn" : "rd"],
    fvgU && [`FVG fill ${smcMoney(fvgU.lo)}–${smcMoney(fvgU.hi)}`, "armed", "cy"],
    sell && [`liquidity sweep < ${smcMoney(sell.price)}`, "armed", "amb"],
    flip && [`CHoCH ${m.bias === "bull" ? "<" : ">"} ${smcMoney(flip)} (invalidation)`, "armed", "rd"],
    buy && [`buy-side liq tap ${smcMoney(buy.price)}`, "armed", "cy"],
  ].filter(Boolean);
  if (!alerts.length) return <SmcEmpty state={state} what="alert conditions" />;
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
function SMCStructureMap({ m, state }) {
  if (!_smcUsable(m) || !Array.isArray(m.spark) || m.spark.length < 4) return <SmcEmpty state={state} what="structure map" />;
  const W=900,H=340,padT=20,padB=26,padL=14,padR=150;
  const zones = []
    .concat((m.order_blocks || []).slice(0, 4).map(o => ({
      top: o.hi, bot: o.lo, type: o.type === "demand" ? "OB+" : "OB−",
      tone: o.type === "demand" ? "gn" : "rd", note: `${o.type} · ${o.state}` })))
    .concat((m.fvgs || []).filter(g => g.state === "unfilled").slice(0, 3).map(g => ({
      top: g.hi, bot: g.lo, type: "FVG", tone: "violet", note: `${g.type} · unfilled` })));
  const spot = m.cur_close;
  const cl = m.spark.slice(-16);
  const allP = cl.concat(zones.flatMap(z => [z.top, z.bot])).concat([spot]);
  const lo = Math.min(...allP) * 0.998, hi = Math.max(...allP) * 1.002;
  const y=p=>padT+(1-(p-lo)/(hi-lo))*(H-padT-padB);
  const candles=cl.map((c,i)=>{ const o=i===0?cl[0]:cl[i-1]; const hi2=Math.max(o,c)*1.002; const lo2=Math.min(o,c)*0.998; return {o,c,hi:hi2,lo:lo2}; });
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

function SMCInducement({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="inducement" />;
  const sell = m.liquidity.sellside || [];
  const sweep = sell[0] || null;
  const induce = sell[1] || null;
  const draw = m.draw_on_liquidity;
  return (
    <div className="smc-sub">
      <SMCStructureMap m={m} state={state} />
      <div className="smc-sub-rows">
        {induce && <div className="smc-row smc-row--amb"><span className="mono">Inducement low</span><span className="mono">{smcMoney(induce.price)}</span><span className="mono dim2">minor liq · trap before the deeper sweep</span></div>}
        {sweep && <div className="smc-row smc-row--rd"><span className="mono">Resting liquidity</span><span className="mono">{smcMoney(sweep.price)}</span><span className="mono dim2">stops below · likely sweep target</span></div>}
        {draw && <div className="smc-row smc-row--gn"><span className="mono">True intent</span><span className="mono">{m.bias === "bull" ? "↑" : "↓"} {smcMoney(draw.price)}</span><span className="mono dim2">{draw.side} draw on liquidity</span></div>}
        {!sweep && !draw && <div className="smc-empty mono dim2">— no clear engineered-liquidity setup on this timeframe</div>}
      </div>
      <div className="mono dim" style={{ fontSize: 11 }}>
        {sweep ? `Resting liquidity at ${smcMoney(sweep.price)} below price is a likely sweep target before the real move. ` : ""}
        {draw ? `Intent is ${m.bias === "bull" ? "up" : "down"} toward ${smcMoney(draw.price)} (${draw.side}).` : "No draw on liquidity in the bias direction."}
      </div>
    </div>
  );
}

function SMCBreakers({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="breaker / mitigation blocks" />;
  const cur = m.cur_close;
  const rows = (m.order_blocks || []).filter(o => o.state !== "fresh").map(o => {
    const flipped = (o.type === "supply" && cur > o.hi) || (o.type === "demand" && cur < o.lo);
    const block = flipped ? "Breaker" : "Mitigation";
    const polarity = o.type === "supply"
      ? (cur > o.hi ? "flipped → support" : "supply on retest")
      : (cur < o.lo ? "flipped → resistance" : "support on retest");
    const status = flipped ? "active" : o.state;
    const tone = flipped ? (o.type === "supply" ? "gn" : "rd") : "amb";
    return { block, zone: `${smcMoney(o.lo)}–${smcMoney(o.hi)}`, origin: `${o.type} OB`, polarity, status, tone };
  });
  if (!rows.length) return <SmcEmpty state={state} what="breaker / mitigation blocks" />;
  return (
    <table className="dtable">
      <thead><tr><th>Block</th><th className="r">Zone</th><th>Origin</th><th>Polarity</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}><td className="mono"><b>{r.block}</b></td><td className="r mono">{r.zone}</td><td className="mono dim">{r.origin}</td><td className="mono">{r.polarity}</td><td><Pill tone={r.tone} small>{r.status}</Pill></td></tr>
        ))}
      </tbody>
    </table>
  );
}

function SMCVoidOTE({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="OTE / voids" />;
  const r = m.range, s = m.spark || [];
  let disp = null;
  if (s.length >= 6) {
    let lo = s[0], loi = 0;
    for (let i = 0; i < s.length; i++) if (s[i] < lo) { lo = s[i]; loi = i; }
    let hi = lo, hii = loi;
    for (let i = loi; i < s.length; i++) if (s[i] > hi) { hi = s[i]; hii = i; }
    if (hi > lo && hii > loi) disp = { lo, hi, pct: (hi - lo) / lo * 100, bars: hii - loi };
  }
  const v = (m.fvgs || []).find(g => g.state === "unfilled");
  return (
    <div className="smc-sub">
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <KpiTile label="Displacement leg" value={disp ? `+${disp.pct.toFixed(1)}%` : "—"} tone="gn" sub={disp ? `${smcMoney(disp.lo)} → ${smcMoney(disp.hi)} · ${disp.bars} bars` : "no clear leg"} />
        <KpiTile label="Liquidity void" value={v ? `${smcMoney(v.lo)}–${smcMoney(v.hi)}` : "—"} tone="violet" sub={v ? `${v.type} FVG · unfilled` : "none unfilled"} />
        <KpiTile label="OTE 62–79%" value={`${smcMoney(r.ote_lo)}–${smcMoney(r.ote_hi)}`} tone="copper" sub="optimal entry zone" />
        <KpiTile label="In OTE now?" value={r.ote_active ? "YES" : "NO"} tone={r.ote_active ? "gn" : "amb"} sub={`${r.pct}% of range`} />
      </div>
      <div className="mono dim" style={{ fontSize: 11 }}>OTE (0.62–0.79 retrace of the dealing range) sits at <b className="copper">{smcMoney(r.ote_lo)}–{smcMoney(r.ote_hi)}</b>. {r.ote_active ? "Price is in the OTE zone now." : "Await a retrace into OTE for the highest-confluence entry."}</div>
    </div>
  );
}

function SMCKillSMT({ m, state }) {
  const sym = (m && m.ticker) || "";
  const isSwing = m && m.tf === "Daily";   // 1H session timing only matters for swing
  const intr = useSmcIntraday(isSwing ? sym : null);
  const kz = smcKillZones(intr && intr.bars);
  const smt = m && m.smt;
  return (
    <div className="smc-sub smc-2col">
      <div>
        <div className="label-cap" style={{ marginBottom: 6 }}>KILL ZONES · 1H session edge (ET)</div>
        {!isSwing ? <div className="smc-empty mono dim2">— session-timing edge is a swing concept; switch to SWING mode for 1H kill-zones ({m && m.tf} bars here)</div>
          : !intr ? <SmcEmpty state="loading" what="intraday sessions" />
          : kz && kz.sessions.length ? kz.sessions.map((s, i) => {
            const active = s.z === kz.active && i === kz.sessions.length - 1;
            const tone = active ? "gn" : s.sweptHigh ? "cy" : s.sweptLow ? "rd" : "ink";
            const note = active ? "ACTIVE now" : s.sweptHigh ? `swept high ${smcMoney(s.hi)}` : s.sweptLow ? `swept low ${smcMoney(s.lo)}` : `${smcMoney(s.lo)}–${smcMoney(s.hi)}`;
            return <div key={i} className={`smc-row smc-row--${tone}`}><span className="mono">{s.z}</span><span className="mono dim2">{s.day}</span><span className={`mono ${active ? "up" : "dim2"}`}>{note}</span></div>;
          }) : <div className="smc-empty mono dim2">— no intraday bars returned for {sym}</div>}
      </div>
      <div>
        <div className="label-cap" style={{ marginBottom: 6 }}>SMT DIVERGENCE · vs {smt ? smt.ref : "SPY"}</div>
        {smt ? <>
          <div className={`smc-row smc-row--${smt.type === "bullish" ? "gn" : smt.type === "bearish" ? "rd" : "ink"}`}>
            <span className="mono">{sym}</span>
            <span className={`mono ${smt.type === "bullish" ? "up" : smt.type === "bearish" ? "dn" : "dim2"}`}>{smt.type.toUpperCase()}</span>
          </div>
          <div className="mono dim" style={{ fontSize: 11, marginTop: 6 }}>{smt.note}.</div>
        </> : <SmcEmpty state={state} what="SMT divergence" />}
      </div>
    </div>
  );
}

function SMCEntryModel({ m, state }) {
  if (!_smcUsable(m)) return <SmcEmpty state={state} what="entry model" />;
  const sell = (m.liquidity.sellside || [])[0];
  const bos = m.structure.last_bos;
  const fvgU = (m.fvgs || []).find(g => g.state === "unfilled");
  const obFresh = (m.order_blocks || []).find(o => o.state !== "mitigated");
  const inOte = m.range.ote_active;
  const steps = [
    { s: "1 · Liquidity sweep", done: !!sell, note: sell ? `sell-side resting ${smcMoney(sell.price)}` : "no resting liquidity below" },
    { s: "2 · CHoCH / BoS", done: !!bos, note: bos ? `${bos.evt} ${bos.dir} @ ${smcMoney(bos.price)}` : "no structure break" },
    { s: "3 · FVG / imbalance", done: !!fvgU, note: fvgU ? `${smcMoney(fvgU.lo)}–${smcMoney(fvgU.hi)} unfilled` : "no unfilled FVG" },
    { s: "4 · OB / OTE entry", done: !!(obFresh && inOte), note: inOte ? "price in OTE now" : obFresh ? `unmitigated OB ${smcMoney(obFresh.lo)} · await OTE` : "no fresh OB" },
    { s: "5 · Confirmation", done: false, note: "LTF confirm on entry tap (manual)" },
  ];
  const n = steps.filter(x => x.done).length;
  const grade = n >= 4 ? "A" : n >= 3 ? "B+" : n >= 2 ? "B" : "C";
  return (
    <div className="smc-sub">
      <div className="smc-grade-row">
        <div className="smc-grade">{grade}</div>
        <div className="smc-grade-meta mono dim2">{n} of 5 steps complete · {m.bias} bias. {n >= 4 ? "High-confluence setup — await final confirmation." : n >= 2 ? "Partial setup — needs the remaining steps before entry." : "Setup not yet formed."}</div>
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
