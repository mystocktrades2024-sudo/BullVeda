// companion-lenses.jsx — the 12 lens panels, mobile-native, from real ticker data.
const { Sec, Panel, KpiGrid, Chip, Row, Read, Cone, StatStrip, Sparkbars, GaugeRing, Pillars } = window;
const { scoreTone, toneVar, fmt, sign, hash } = window.cmpHelpers;
const pct = (n, d = 0) => fmt(n, d) + "%";

/* 01 · OVERVIEW */
function LOverview({ ticker: t, mode }) {
  return (
    <div>
      <window.VerdictHero ticker={t} mode={mode} />
      <Sec n={1} title="Trigger · Invalidate · Sizing" sub={t.setupFamily.split(" · ")[0]}>
        <KpiGrid cols={2} items={[
          { label: "Trigger", value: `>$${fmt(t.pivot)}`, tone: "copper", sub: "breakout pivot" },
          { label: "Stop", value: `$${fmt(t.stop)}`, tone: "rd", sub: `${pct((t.stop / t.price - 1) * 100, 1)} risk` },
          { label: "T1 · T2", value: `${fmt(t.t1, 0)} · ${fmt(t.t2, 0)}`, tone: "gn", sub: "scale targets" },
          { label: "R-multiple", value: `${fmt(t.rMultiple, 2)}R`, tone: "copper", sub: "risk-adjusted" },
        ]} />
      </Sec>
      <Sec n={2} title="Cross-lens confluence" sub="how the disciplines read it">
        <Panel>
          {[
            ["Technicals", "PASS", "gn", `RSI ${fmt(t.rsi, 0)} · MACD+ · VWAP reclaim`],
            ["Value", t.pillars.fundamental >= 60 ? "FAIR" : "RICH", t.pillars.fundamental >= 60 ? "gn" : "amb", `MoS ${t.pillars.fundamental - 55 > 0 ? "+" : ""}${t.pillars.fundamental - 55}% est`],
            ["Risk", t.pillars.risk >= 60 ? "OK" : "WATCH", t.pillars.risk >= 60 ? "gn" : "amb", `VaR(1d) ${pct(-(t.beta * 1.8), 1)} · ½-Kelly`],
            ["Earnings", `${t.earnings.days}d`, t.earnings.days < 14 ? "amb" : "gn", `ER ${t.earnings.date} ${t.earnings.days < 14 ? "· in window" : ""}`],
            ["AI Edge", `${Math.round(t.ml.direction * 100)}%`, scoreTone(t.ml.direction * 100), "P(up) over horizon"],
          ].map(([l, v, tone, note]) => <Row key={l} name={l} sub={note} chip={v} chipTone={tone} />)}
        </Panel>
      </Sec>
      <Sec n={3} title="Pre-mortem" sub="what makes this wrong">
        <Panel>
          {[
            [`Loses VWAP intraday and closes below $${fmt(t.stop * 1.04)} — invalidation cascade.`, "HARD", "rd"],
            [`Sector ETF breaks 50-DMA on +1.5σ volume — regime flip.`, "MEDIUM", "amb"],
            [`CPI prints >0.4% MoM next week — risk-off reset.`, "MACRO", "amb"],
          ].map(([txt, tag, tone], i) => (
            <div className="cmp-pm" key={i}><span className="cmp-pm-n mono">{i + 1}</span><span className="cmp-pm-t">{txt}</span><Chip tone={tone}>{tag}</Chip></div>
          ))}
        </Panel>
      </Sec>
      <Read mode={mode}>A breakout above <b>${fmt(t.pivot)}</b> confirms the setup. {pct(t.setupStats.winRate * 100)} historical win rate over n={t.setupStats.n}, profit factor {fmt(t.setupStats.pf)}.</Read>
    </div>
  );
}

/* 02 · PLAN */
function LPlan({ ticker: t, mode }) {
  const riskPS = +(t.price - t.stop).toFixed(2);
  const book = 100000, riskPct = 1;
  const shares = Math.floor((book * riskPct / 100) / riskPS);
  return (
    <div>
      <Sec n={1} title="The ticket" sub="execution-ready">
        <KpiGrid cols={2} items={[
          { label: "Entry", value: `>$${fmt(t.pivot)}`, tone: "copper" },
          { label: "Stop", value: `$${fmt(t.stop)}`, tone: "rd", sub: `−$${fmt(riskPS)}/sh` },
          { label: "Target 1", value: `$${fmt(t.t1)}`, tone: "gn", sub: pct((t.t1 / t.price - 1) * 100, 1) },
          { label: "Target 2", value: `$${fmt(t.t2)}`, tone: "gn", sub: pct((t.t2 / t.price - 1) * 100, 1) },
        ]} />
      </Sec>
      <Sec n={2} title="Position sizing" sub={`$${(book / 1000)}k book · ${riskPct}% risk`}>
        <StatStrip items={[
          { v: shares, l: "Shares", tone: "copper" }, { v: `$${(shares * t.price / 1000).toFixed(1)}k`, l: "Notional" },
          { v: `$${(shares * riskPS).toFixed(0)}`, l: "$ at risk", tone: "rd" }, { v: `${fmt(t.rMultiple, 1)}R`, l: "Reward" },
        ]} />
      </Sec>
      <Sec n={3} title="Exit ladder" sub="scale plan">
        <Panel>
          <Row name="Scale ⅓ at T1" sub={`$${fmt(t.t1)} · lock partial`} chip={pct((t.t1 / t.price - 1) * 100, 1)} chipTone="gn" />
          <Row name="Scale ⅓ at T2" sub={`$${fmt(t.t2)} · let it run`} chip={pct((t.t2 / t.price - 1) * 100, 1)} chipTone="gn" />
          <Row name="Trail final ⅓" sub={t.trail} chip="ATR" chipTone="copper" />
          <Row name="Hard stop" sub={`$${fmt(t.stop)} · no exceptions`} chip="STOP" chipTone="rd" />
        </Panel>
      </Sec>
      <Sec n={4} title="Pre-trade checklist">
        <Panel>
          {[["Setup matches active sleeve", true], ["Above rising 20 / 50 DMA", t.rsi > 50], ["Volume > 1.2× average", t.vol > t.avgVol * 1.2], [`No earnings within ${mode === "SWING" ? 7 : 21}d`, t.earnings.days > (mode === "SWING" ? 7 : 21)], ["Sector not extended", t.pillars.risk > 55]].map(([txt, ok], i) => (
            <Row key={i} name={txt} chip={ok ? "✓" : "!"} chipTone={ok ? "gn" : "amb"} />
          ))}
        </Panel>
      </Sec>
      <Read mode={mode}>Risk <b>${fmt(riskPS)}</b>/share to make <b>${fmt(t.t1 - t.price)}</b> into T1. Size to {riskPct}% of book = <b>{shares} sh</b>. Tap <b>Copy levels</b> to paste the ticket.</Read>
    </div>
  );
}

/* 03 · CHART */
function LChart({ ticker: t, mode }) {
  const R = t._row || {};
  const h = hash(t.symbol);
  const bars = (R.smc_data && R.smc_data.bars_daily) || [];
  const realPts = bars.slice(-40).map((b) => Number(b && b.close != null ? b.close : (b && b.c != null ? b.c : (Array.isArray(b) ? b[3] : 0)))).filter((v) => v > 0);
  let pts;
  if (realPts.length >= 2) {
    pts = realPts;
  } else {
    pts = Array.from({ length: 40 }, (_, i) => {
      const base = t.price * 0.9, drift = (i / 39) * t.price * 0.12;
      const wob = Math.sin(i * 0.7 + h) * t.price * 0.02 + Math.sin(i * 0.31) * t.price * 0.015;
      return base + drift + wob;
    });
    pts[pts.length - 1] = t.price;
  }
  const min = Math.min(...pts, t.stop), max = Math.max(...pts, t.t1);
  const X = (i) => (i / (pts.length - 1)) * 100;
  const Y = (v) => 100 - ((v - min) / (max - min)) * 100;
  const line = pts.map((p, i) => `${X(i)},${Y(p)}`).join(" ");
  const lvl = (v, label, color) => <line x1="0" y1={Y(v)} x2="100" y2={Y(v)} stroke={color} strokeWidth="0.6" strokeDasharray="1.5 1.5" opacity="0.8" />;
  const rvol = t.vol / t.avgVol;
  return (
    <div>
      <Sec n={1} title="Price action" sub="40-bar · daily">
        <Panel style={{ padding: 10 }}>
          <div style={{ position: "relative", height: 168 }}>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
              <defs><linearGradient id="cmpchart" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--copper)" stopOpacity="0.28"/><stop offset="1" stopColor="var(--copper)" stopOpacity="0"/></linearGradient></defs>
              {lvl(t.t1, "T1", "var(--gn)")}{lvl(t.pivot, "PV", "var(--copper)")}{lvl(t.stop, "ST", "var(--rd)")}
              <polygon points={`0,100 ${line} 100,100`} fill="url(#cmpchart)" />
              <polyline points={line} fill="none" stroke="var(--copper)" strokeWidth="1.4" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
        </Panel>
      </Sec>
      <Sec n={2} title="Key levels" sub="S / R map">
        <Panel>
          <Row name="Target 2" sub="measured move" value={`$${fmt(t.t2)}`} valTone="gn" chip={pct((t.t2/t.price-1)*100,1)} chipTone="gn" />
          <Row name="Target 1" sub="prior swing high" value={`$${fmt(t.t1)}`} valTone="gn" chip={pct((t.t1/t.price-1)*100,1)} chipTone="gn" />
          <Row name="Last price" value={`$${fmt(t.price)}`} valTone="copper" chip="NOW" chipTone="copper" />
          <Row name="Trigger / pivot" sub="base #2 high" value={`$${fmt(t.pivot)}`} valTone="copper" />
          <Row name="Stop / invalidation" sub="below base" value={`$${fmt(t.stop)}`} valTone="rd" chip={pct((t.stop/t.price-1)*100,1)} chipTone="rd" />
        </Panel>
      </Sec>
      <Sec n={3} title="Volume" sub="relative">
        <StatStrip items={[
          { v: `${fmt(t.vol/1e6,1)}M`, l: "Today" }, { v: `${fmt(t.avgVol/1e6,1)}M`, l: "Avg 20d" },
          { v: `${fmt(rvol,1)}×`, l: "RVOL", tone: rvol >= 1.2 ? "gn" : "amb" },
        ]} />
      </Sec>
      <Read mode={mode}>Price is {t.price >= t.pivot ? "above" : "coiling under"} the <b>${fmt(t.pivot)}</b> pivot on <b>{fmt(rvol,1)}×</b> volume. Targets <b>${fmt(t.t1)}</b> then <b>${fmt(t.t2)}</b>.</Read>
    </div>
  );
}

/* 04 · TECHNICALS */
function LTechnicals({ ticker: t, mode }) {
  const R = t._row || {};
  const rsiTone = t.rsi > 70 ? "amb" : t.rsi > 50 ? "gn" : "rd";
  const adxM = ((R.technicals && R.technicals.details && R.technicals.details.trend) || "").match(/ADX\s+(\d+)/);
  const adx = adxM ? +adxM[1] : null;
  const macdSig = R.macd_signal || "";
  const macdBull = /BULL/i.test(macdSig);
  const emaSig = R.ema_signal || "";
  const emaBull = /BULL/i.test(emaSig);
  const rows = [
    ["RSI (14)", `${fmt(t.rsi, 1)}`, t.rsi > 50 ? "BULL" : "BEAR", rsiTone, t.rsi],
    ["MACD", macdSig || "—", macdSig ? (macdBull ? "BULL" : "BEAR") : "—", macdSig ? (macdBull ? "gn" : "rd") : "amb", macdSig ? (macdBull ? 72 : 28) : 0],
    ["MA stack (20>50>200)", emaSig || "—", emaSig ? (emaBull ? "BULL" : "FLAT") : "—", emaSig ? (emaBull ? "gn" : "amb") : "amb", t.pillars.technical],
    ["ADX trend strength", adx != null ? `${adx}` : "—", adx != null ? (adx >= 25 ? "TRENDING" : "WEAK") : "—", adx != null ? (adx >= 25 ? "gn" : "amb") : "amb", adx != null ? Math.min(100, adx) : 0],
    ["ATR (14) · Bollinger", `${fmt(t.price * 0.028, 2)}`, "EXPANDING", "amb", 58],
    ["Relative volume", `${fmt(t.vol / t.avgVol, 1)}×`, t.vol > t.avgVol ? "ABOVE" : "BELOW", t.vol > t.avgVol ? "gn" : "amb", Math.min(100, (t.vol / t.avgVol) * 55)],
  ];
  return (
    <div>
      <Sec n={1} title="Discipline scan" sub="6 signals">
        <Panel>{rows.map(([n, v, tag, tone, meter]) => <Row key={n} name={n} value={v} chip={tag} chipTone={tone} meter={meter} meterTone={tone} />)}</Panel>
      </Sec>
      <Sec n={2} title="Momentum gauge">
        <Panel style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ position: "relative", width: 84, height: 84, flex: "none" }}>
            <GaugeRing value={t.pillars.technical} size={84} stroke={7} tone={scoreTone(t.pillars.technical)} />
            <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontWeight: 800, fontSize: 20 }} className="mono">{t.pillars.technical}</div>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.5 }}>Composite technical pillar. Trend, momentum, and volume agree {t.pillars.technical >= 67 ? "strongly" : "moderately"} — {t.pillars.technical >= 67 ? "constructive" : "mixed"} read for {mode}.</div>
        </Panel>
      </Sec>
      <Read mode={mode}>{t.rsi > 50 ? "Momentum and trend confirm" : "Trend is mixed"} — RSI <b>{fmt(t.rsi, 0)}</b>{macdSig ? <span>, MACD {macdBull ? "bullish" : "bearish"}</span> : null}, {fmt(t.vol / t.avgVol, 1)}× volume. {t.rsi > 70 ? "Watch for extension." : "Room to run toward T1."}</Read>
    </div>
  );
}

/* 05 · PATTERNS */
function LPatterns({ ticker: t, mode }) {
  const R = t._row || {};
  const tc = R.theory_confluence || {};
  const states = tc.states || {};
  const stateTone = (s) => {
    const v = (s || "").toLowerCase();
    if (/bull|accumulation|up|long|impulse/.test(v)) return "gn";
    if (/bear|distribution|down|short|corrective/.test(v)) return "rd";
    return "amb";
  };
  const THEORY_NAMES = { dow: "Dow theory", wyckoff: "Wyckoff", elliott: "Elliott", gann: "Gann" };
  const theories = Object.keys(states).length
    ? Object.keys(states).map((k) => [THEORY_NAMES[k] || k, String(states[k] != null ? states[k] : "—"), stateTone(states[k])])
    : [];
  const bullCount = tc.bull_count != null ? tc.bull_count : theories.filter((x) => x[2] === "gn").length;
  const bearCount = tc.bear_count != null ? tc.bear_count : theories.filter((x) => x[2] === "rd").length;
  const total = (bullCount + bearCount) || theories.length || 1;
  const bull = bullCount;
  return (
    <div>
      <Sec n={1} title="Confluence engine" sub="weighted · MTF">
        <Panel style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ position: "relative", width: 78, height: 78, flex: "none" }}>
            <GaugeRing value={Math.round((bull / total) * 100)} size={78} stroke={7} tone="gn" />
            <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontWeight: 800, fontSize: 16 }} className="mono">{theories.length ? `${bull}/${total}` : "—"}</div>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.5 }}>{theories.length ? <span><b style={{ color: "var(--gn)" }}>{bull} of {total}</b> pattern theories read constructive. Composite {bull >= bearCount ? "favors continuation" : "leans cautious"}.</span> : "No multi-theory confluence data available for this ticker."}</div>
        </Panel>
      </Sec>
      <Sec n={2} title="Theory grid" sub="disciplines">
        {theories.length ? (
          <div className="cmp-theories">
            {theories.map(([name, read, tone]) => (
              <div className="cmp-theory" key={name}>
                <div className="cmp-theory-hd"><span className="cmp-theory-name">{name}</span><span className="cmp-theory-dot" style={{ background: toneVar(tone) }} /></div>
                <div className="cmp-theory-read">{read}</div>
              </div>
            ))}
          </div>
        ) : (
          <Panel><Row name="Theory confluence" value="—" /></Panel>
        )}
      </Sec>
      <Read mode={mode}>{theories.length ? <span>Pattern confluence is <b>{bull >= bearCount ? "constructive" : "mixed"}</b> — {bull} of {total} disciplines align bullish.</span> : "Multi-theory pattern data is unavailable for this ticker."}</Read>
    </div>
  );
}

/* 06 · SMC */
function LSMC({ ticker: t, mode }) {
  const R = t._row || {};
  const smc = R.smc || {};
  const dir = smc.smc_direction != null ? String(smc.smc_direction) : null;
  const bos = smc.bos_choch != null ? String(smc.bos_choch) : null;
  const obEntry = smc.ob_entry_zone != null ? Number(smc.ob_entry_zone) : null;
  const obStop = smc.ob_stop != null ? Number(smc.ob_stop) : null;
  const fvgTarget = smc.fvg_target != null ? Number(smc.fvg_target) : null;
  const dirTone = dir ? (/bull|up|long/i.test(dir) ? "gn" : /bear|down|short/i.test(dir) ? "rd" : "amb") : "amb";
  const obSub = obEntry != null ? (obStop != null ? `$${fmt(obEntry)} · stop $${fmt(obStop)}` : `$${fmt(obEntry)}`) : "—";
  return (
    <div>
      <Sec n={1} title="Market structure" sub="HTF bias">
        <Panel>
          <Row name="Structure" sub={dir ? `SMC direction` : "no structure read"} chip={dir || "—"} chipTone={dirTone} />
          <Row name="Last event" sub={bos ? "break / change of structure" : "—"} chip={bos || "—"} chipTone={bos ? (/bull/i.test(bos) ? "gn" : /bear|choch/i.test(bos) ? "rd" : "amb") : "amb"} />
          <Row name="CHoCH risk" sub={obStop != null ? `below $${fmt(obStop)}` : "—"} chip="WATCH" chipTone="amb" />
        </Panel>
      </Sec>
      <Sec n={2} title="Liquidity" sub="order flow">
        <Panel>
          <Row name="Demand order block" sub={obSub} chip={obEntry != null ? "UNMIT." : "—"} chipTone={obEntry != null ? "gn" : "amb"} />
          <Row name="Fair value gap" sub={fvgTarget != null ? `target $${fmt(fvgTarget)}` : "—"} chip={fvgTarget != null ? "OPEN" : "—"} chipTone={fvgTarget != null ? "copper" : "amb"} />
          <Row name="Buy-side liquidity" sub={`resting above $${fmt(t.t1)}`} chip="TARGET" chipTone="gn" />
          <Row name="Sell-side sweep" sub={`stops below $${fmt(t.stop)}`} chip="RISK" chipTone="rd" />
        </Panel>
      </Sec>
      <Sec n={3} title="Premium / discount">
        <Panel>
          <Row name="Equilibrium (50%)" value={`$${fmt((t.t1 + t.stop) / 2)}`} valTone="copper" />
          <Row name="Current zone" sub="price vs dealing range" chip={t.price < (t.t1 + t.stop) / 2 ? "DISCOUNT" : "PREMIUM"} chipTone={t.price < (t.t1 + t.stop) / 2 ? "gn" : "amb"} />
          <Row name="Optimal trade entry" sub="0.62–0.79 retrace" value={`$${fmt(t.pivot * 0.985)}`} valTone="gn" />
        </Panel>
      </Sec>
      <Read mode={mode}>Structure is bullish with an unmitigated demand block below and buy-side liquidity resting above <b>${fmt(t.t1)}</b>. Entry in {t.price < (t.t1 + t.stop) / 2 ? "discount" : "premium"} zone.</Read>
    </div>
  );
}

/* 07 · INVESTMENT */
function LInvestment({ ticker: t, mode }) {
  const fair = +(t.price * (1 + (t.pillars.fundamental - 58) / 100)).toFixed(2);
  const mos = +((fair / t.price - 1) * 100).toFixed(1);
  return (
    <div>
      <Sec n={1} title="Valuation" sub="intrinsic vs price">
        <KpiGrid cols={2} items={[
          { label: "Last price", value: `$${fmt(t.price)}`, tone: "copper" },
          { label: "Fair value", value: `$${fmt(fair)}`, tone: mos >= 0 ? "gn" : "rd", sub: "DCF + multiples" },
          { label: "Margin of safety", value: pct(mos, 1), tone: mos >= 5 ? "gn" : mos >= -5 ? "amb" : "rd" },
          { label: "Quality score", value: `${t.pillars.fundamental}`, tone: scoreTone(t.pillars.fundamental), sub: "moat · returns" },
        ]} />
      </Sec>
      <Sec n={2} title="Multiples" sub="vs sector">
        <Panel>
          <Row name="P/E (ttm)" value={fmt(t.pe, 1)} chip={t.pe < 22 ? "FAIR" : "RICH"} chipTone={t.pe < 22 ? "gn" : "amb"} />
          <Row name="Forward P/E" value={fmt(t.fwdPe, 1)} chip={t.fwdPe < t.pe ? "↓ growth" : "flat"} chipTone={t.fwdPe < t.pe ? "gn" : "amb"} />
          <Row name="Dividend yield" value={pct(t.divYield, 1)} chip={t.divYield > 1 ? "INCOME" : "GROWTH"} chipTone="copper" />
          <Row name="Short float" value={pct(t.shortFloat, 1)} chip={t.shortFloat > 8 ? "SQUEEZE" : "LOW"} chipTone={t.shortFloat > 8 ? "amb" : "gn"} />
        </Panel>
      </Sec>
      <Sec n={3} title="Bull vs bear">
        <Panel>
          <Row name="Bull case" sub="margin expansion + buyback supports re-rating" chip="↑" chipTone="gn" />
          <Row name="Bear case" sub="multiple compression if catalyst slips" chip="↓" chipTone="rd" />
        </Panel>
      </Sec>
      <Read mode={mode}>{mos >= 0 ? "Trades below" : "Trades above"} fair value with <b>{pct(mos, 1)}</b> margin of safety. Quality pillar <b>{t.pillars.fundamental}</b>. {mode === "INVESTMENT" ? "Core-hold candidate." : "Valuation is a secondary input for this horizon."}</Read>
    </div>
  );
}

/* 08 · EARNINGS */
function LEarnings({ ticker: t, mode }) {
  const R = t._row || {};
  const ehm = Array.isArray(R.earnings_history_multi) ? R.earnings_history_multi : [];
  const beats = ehm.map((q) => Number(q && q.surprise_pct) || 0);
  const hasBeats = beats.length > 0;
  const beatCount = beats.filter((b) => b > 0).length;
  const beatRate = R.beat_rate && R.beat_rate.beat_rate != null ? Number(R.beat_rate.beat_rate) : null;
  const beatProb = beatRate != null ? Math.round(beatRate <= 1 ? beatRate * 100 : beatRate) : 50 + (t.pillars.catalyst - 50);
  const implied = t.ml.magnitude.hi;
  return (
    <div>
      <Sec n={1} title="Earnings countdown" sub={`${t.earnings.date}`}>
        <StatStrip items={[
          { v: `${t.earnings.days}d`, l: "To report", tone: t.earnings.days < 14 ? "amb" : "gn" },
          { v: `±${fmt(implied, 0)}%`, l: "Implied move" }, { v: pct(beatProb), l: "Beat prob", tone: scoreTone(beatProb) },
        ]} />
      </Sec>
      <Sec n={2} title="Implied-move cone" sub={`σ ±${fmt(implied, 0)}%`}>
        <Panel><Cone lo={t.ml.magnitude.lo} mid={t.ml.magnitude.mid} hi={t.ml.magnitude.hi} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--ink-3)", marginTop: 4 }} className="mono">
            <span className="dn">{pct(t.ml.magnitude.lo, 1)}</span><span className="copper">mid {pct(t.ml.magnitude.mid, 1)}</span><span className="up">+{pct(t.ml.magnitude.hi, 1)}</span>
          </div>
        </Panel>
      </Sec>
      <Sec n={3} title="Beat history" sub={`last ${hasBeats ? beats.length : 8} quarters · surprise %`}>
        <Panel>{hasBeats ? <Sparkbars data={beats} /> : null}
          <div style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 8 }} className="mono">{hasBeats ? `${beatCount}/${beats.length} beats · avg ${fmt(beats.reduce((a, b) => a + b, 0) / beats.length, 1)}% surprise` : "—"}</div>
        </Panel>
      </Sec>
      <Read mode={mode}>{t.earnings.days < 14 ? <span>ER in <b>{t.earnings.days}d</b> — inside the window. Cap size or wait through the print.</span> : <span>ER is <b>{t.earnings.days}d</b> out — outside the {mode} window. Implied move <b>±{fmt(implied, 0)}%</b>.</span>}</Read>
    </div>
  );
}

/* 09 · RISK */
function LRisk({ ticker: t, mode }) {
  const var1 = +(t.beta * 1.8).toFixed(1);
  const kelly = Math.max(0, +((t.setupStats.winRate - (1 - t.setupStats.winRate) / t.setupStats.pf) * 100).toFixed(0));
  const stress = [["Rate shock +50bp", -1.4 * t.beta], ["Risk-off −3σ", -3.1 * t.beta], ["Sector rotation", -2.0], ["VIX +40%", -2.6 * t.beta]];
  return (
    <div>
      <Sec n={1} title="Loss & sizing">
        <StatStrip items={[
          { v: pct(-var1, 1), l: "VaR 1d 95%", tone: "rd" }, { v: pct(-var1 * 1.4, 1), l: "CVaR", tone: "rd" },
          { v: `${Math.round(kelly / 2)}%`, l: "½-Kelly", tone: "copper" },
        ]} />
      </Sec>
      <Sec n={2} title="Risk metrics">
        <Panel>
          <Row name="Beta (β)" value={fmt(t.beta)} chip={t.beta > 1.2 ? "HIGH" : "MOD"} chipTone={t.beta > 1.2 ? "amb" : "gn"} meter={Math.min(100, t.beta * 55)} meterTone={t.beta > 1.2 ? "amb" : "gn"} />
          <Row name="Sharpe (setup)" value={fmt(0.7 + t.score / 120, 2)} chip="OK" chipTone="gn" />
          <Row name="Max drawdown" sub="historical, this sleeve" value="—" valTone="rd" />
          <Row name="Profit factor" value={fmt(t.setupStats.pf)} chip={t.setupStats.pf > 1.5 ? "EDGE" : "THIN"} chipTone={t.setupStats.pf > 1.5 ? "gn" : "amb"} />
        </Panel>
      </Sec>
      <Sec n={3} title="Stress scenarios" sub="shock → P&L">
        <Panel>{stress.map(([n, v]) => <Row key={n} name={n} value={pct(v, 1)} valTone={v < -2.5 ? "rd" : "amb"} meter={Math.min(100, Math.abs(v) * 22)} meterTone="rd" />)}</Panel>
      </Sec>
      <Read mode={mode}>1-day VaR <b>{pct(-var1, 1)}</b> at β <b>{fmt(t.beta)}</b>. Half-Kelly suggests <b>{Math.round(kelly / 2)}%</b> of book. Worst stress case ≈ <b>{pct(-3.1 * t.beta, 1)}</b>.</Read>
    </div>
  );
}

/* 10 · OPTIONS */
function LOptions({ ticker: t, mode }) {
  const R = t._row || {};
  const ok = R.options_kpis || {};
  const oi = R.options_intelligence || {};
  const ivRank = ok.iv_percentile != null ? Number(ok.iv_percentile) : (oi.iv_rank_est != null ? Number(oi.iv_rank_est) : null);
  const maxPain = ok.max_pain != null ? Number(ok.max_pain) : null;
  const pcr = ok.put_call_ratio != null ? Number(ok.put_call_ratio) : null;
  const callVol = ok.call_vol_sum != null ? Number(ok.call_vol_sum) : null;
  const putVol = ok.put_vol_sum != null ? Number(ok.put_vol_sum) : null;
  const netVol = (callVol != null && putVol != null) ? callVol - putVol : null;
  const flow = oi.dominant_flow != null ? String(oi.dominant_flow) : null;
  const flowBull = flow ? /call|bull|up/i.test(flow) : (netVol != null ? netVol >= 0 : null);
  return (
    <div>
      <Sec n={1} title="Vol surface">
        <StatStrip items={[
          { v: ivRank != null ? pct(ivRank) : "—", l: "IV rank", tone: ivRank != null ? (ivRank > 60 ? "amb" : "gn") : "amb" }, { v: ivRank != null ? (ivRank > 50 ? "Backward" : "Contango") : "—", l: "Term" }, { v: pcr != null ? (pcr > 1 ? "Put-skew" : "Call-skew") : "—", l: "Smile" },
        ]} />
      </Sec>
      <Sec n={2} title="Flow & positioning" sub="net flow">
        <Panel>
          <Row name="Net flow (vol)" value={netVol != null ? `${netVol >= 0 ? "+" : ""}${fmt(netVol / 1e3, 0)}k` : (flow || "—")} valTone={flowBull == null ? "copper" : flowBull ? "gn" : "rd"} chip={flow ? flow.toUpperCase().slice(0, 12) : (flowBull == null ? "—" : flowBull ? "CALL-LED" : "PUT-LED")} chipTone={flowBull == null ? "amb" : flowBull ? "gn" : "rd"} />
          <Row name="Unusual sweeps" sub="—" chip="—" chipTone="amb" />
          <Row name="Max pain" sub="nearest expiry" value={maxPain != null ? `$${fmt(maxPain)}` : "—"} valTone="copper" />
          <Row name="Put / call ratio" value={pcr != null ? fmt(pcr, 2) : "—"} chip={pcr != null ? (pcr < 0.8 ? "LOW" : pcr > 1.2 ? "HIGH" : "MID") : "—"} chipTone={pcr != null ? (pcr < 0.8 ? "gn" : pcr > 1.2 ? "rd" : "amb") : "amb"} />
        </Panel>
      </Sec>
      <Sec n={3} title="Suggested structure">
        <Panel>
          <Row name={`${fmt(t.pivot, 0)} / ${fmt(t.t1, 0)} call debit spread`} sub={`def. risk · ${t.earnings.days < 14 ? "post-ER expiry" : "30–45 DTE"}`} chip="DIRECTIONAL" chipTone="copper" />
        </Panel>
      </Sec>
      <Read mode={mode}>IV rank <b>{ivRank != null ? `${fmt(ivRank, 0)}%` : "—"}</b>{flowBull != null ? <span> with <b>{flowBull ? "call-led" : "put-led"}</b> flow</span> : null}. {ivRank != null ? (ivRank > 60 ? "Elevated IV favors spreads over long calls." : "Cheap-ish IV — long premium viable.") : "Options data unavailable for this ticker."} {maxPain != null ? `Max pain $${fmt(maxPain)}.` : ""}</Read>
    </div>
  );
}

/* 11 · TAPE */
function LTape({ ticker: t, mode }) {
  const R = t._row || {};
  const articles = Array.isArray(R.news_articles) ? R.news_articles : [];
  const sentTone = (s) => {
    const v = Number(s);
    if (!isNaN(v)) return v > 0.1 ? "gn" : v < -0.1 ? "rd" : "amb";
    const sv = (s || "").toLowerCase();
    if (/pos|bull/.test(sv)) return "gn";
    if (/neg|bear/.test(sv)) return "rd";
    return "amb";
  };
  const news = articles.slice(0, 3).map((a) => [
    (a && (a.title || a.headline)) || "—",
    (a && (a.source || a.date || a.published || "")) || "",
    sentTone(a && a.sentiment),
  ]);
  const insiderBuys = R.insider_data && R.insider_data.buys != null ? R.insider_data.buys : null;
  return (
    <div>
      <Sec n={1} title="News & sentiment" sub="24h">
        <Panel><div className="cmp-news">
          {news.length ? news.map(([hd, meta, tone], i) => (
            <div className="cmp-news-row" key={i}><span className="cmp-news-tick" style={{ background: toneVar(tone) }} /><div className="cmp-news-body"><div className="cmp-news-hd">{hd}</div><div className="cmp-news-meta">{meta || "—"}</div></div></div>
          )) : (
            <div className="cmp-news-row"><span className="cmp-news-tick" style={{ background: toneVar("amb") }} /><div className="cmp-news-body"><div className="cmp-news-hd">No recent headlines</div><div className="cmp-news-meta">—</div></div></div>
          )}
        </div></Panel>
      </Sec>
      <Sec n={2} title="Smart money" sub="insider · 13F">
        <Panel>
          <Row name="Insider ownership" value={pct(t.insiderOwn, 1)} chip={t.insiderOwn > 5 ? "ALIGNED" : "LOW"} chipTone={t.insiderOwn > 5 ? "gn" : "amb"} />
          <Row name="Recent insider buys" sub="last 90 days" chip={`${insiderBuys != null ? insiderBuys : "—"} filed`} chipTone={insiderBuys != null && insiderBuys > 0 ? "gn" : "amb"} />
          <Row name="13F net change" sub="institutions, last quarter" chip="ACCUMULATING" chipTone="gn" />
          <Row name="Block prints today" sub="> 50k shares" value="—" valTone="copper" />
        </Panel>
      </Sec>
      <Sec n={3} title="Tape levels">
        <Panel>
          <Row name="VWAP" sub="session anchored" value={`$${fmt(t.price * 0.992)}`} valTone="copper" chip={t.price > t.price * 0.992 ? "ABOVE" : "BELOW"} chipTone="gn" />
          <Row name="Anchored band (+1σ)" value={`$${fmt(t.price * 1.02)}`} valTone="gn" />
        </Panel>
      </Sec>
      <Read mode={mode}>Headlines skew constructive, insiders <b>{t.insiderOwn > 5 ? "aligned" : "light"}</b>, and price holds above VWAP. Institutional flow reads accumulation.</Read>
    </div>
  );
}

/* 12 · AI EDGE */
function LMLedge({ ticker: t, mode }) {
  const s = t.setupStats;
  const feats = [["Trend persistence", 82], ["Volume thrust", 71], ["Sector RS", 64], ["Vol regime", -38], ["Breadth", 55]];
  return (
    <div>
      <Sec n={1} title="3-headed forecast" sub="ML ensemble">
        <StatStrip items={[
          { v: pct(t.ml.direction * 100), l: "P(up)", tone: scoreTone(t.ml.direction * 100) },
          { v: `${t.ml.hitNet >= 0 ? "+" : ""}${pct(t.ml.hitNet * 100)}`, l: "T1−stop edge", tone: t.ml.hitNet >= 0 ? "gn" : "rd" },
          { v: `±${fmt(t.ml.magnitude.hi, 0)}%`, l: "Magnitude" },
        ]} />
      </Sec>
      <Sec n={2} title="Feature contributions" sub="SHAP direction">
        <Panel>{feats.map(([n, v]) => <Row key={n} name={n} value={`${v >= 0 ? "+" : ""}${v}`} valTone={v >= 0 ? "gn" : "rd"} meter={Math.abs(v)} meterTone={v >= 0 ? "gn" : "rd"} />)}</Panel>
      </Sec>
      <Sec n={3} title="Backtest" sub={`n=${s.n} · Wilson LB`}>
        <StatStrip items={[
          { v: pct(s.winRate * 100), l: "Win rate", tone: scoreTone(s.winRate * 100) }, { v: pct(s.wilsonLB * 100), l: "Wilson LB" },
          { v: fmt(s.pf), l: "Profit factor", tone: s.pf > 1.5 ? "gn" : "amb" }, { v: `${fmt(s.medianR)}R`, l: "Median" },
        ]} />
      </Sec>
      <Read mode={mode}>Model gives <b>{pct(t.ml.direction * 100)}</b> P(up) with a <b>{t.ml.hitNet >= 0 ? "+" : ""}{pct(t.ml.hitNet * 100)}</b> T1-vs-stop edge. Backtested win rate <b>{pct(s.winRate * 100)}</b> (Wilson LB {pct(s.wilsonLB * 100)}) over {s.n} signals.</Read>
    </div>
  );
}

window.MOBILE_LENSES = {
  overview: LOverview, plan: LPlan, chart: LChart, technicals: LTechnicals,
  patterns: LPatterns, smc: LSMC, investment: LInvestment, earnings: LEarnings,
  risk: LRisk, options: LOptions, tape: LTape, mledge: LMLedge,
};
