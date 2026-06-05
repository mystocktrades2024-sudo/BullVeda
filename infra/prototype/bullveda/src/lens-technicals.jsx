// lens-technicals.jsx — Technicals (REAL DATA)
// Every indicator, MA, S/R level, volume read and the mini-chart is computed from
// real EODHD OHLCV via /api/indicators. No hardcoded constants, no seeded charts.
// The hero structure read is derived from the SAME data as the score, so it can
// never contradict it (the old build showed "WEAK 21/100" next to "STACKED-BULLISH").

const { useMemo: useMemoTL } = React;

// real technical suite for a symbol
function useTech(sym) {
  const [d, setD] = React.useState(null);
  React.useEffect(() => {
    const BV = window.__BV;
    if (!BV || !BV.get || !sym) { setD(null); return; }
    let on = true; setD(null);
    BV.get("/api/indicators/" + encodeURIComponent(sym)).then(j => { if (on) setD(j || false); }).catch(() => { if (on) setD(false); });
    return () => { on = false; };
  }, [sym]);
  return d;   // null = loading, false = failed, object = data
}

const _n = (v, d) => (typeof v === "number" && isFinite(v)) ? v : (d === undefined ? null : d);
const _f = (v, dp = 2) => v == null ? "—" : v.toFixed(dp);

// MA-stack structure read — derived from real MAs, shared by hero + §2 so they agree
function maRead(t) {
  const p = _n(t.price), e9 = _n(t.ema9), e21 = _n(t.ema21), s50 = _n(t.sma50), s200 = _n(t.sma200);
  if (p == null) return { label: "—", tone: "ink", primary: "—" };
  const seq = [p, e9, e21, s50, s200].filter(x => x != null);
  const bull = seq.every((x, i) => i === 0 || seq[i - 1] >= x);
  const bear = seq.every((x, i) => i === 0 || seq[i - 1] <= x);
  const primary = s200 != null ? (p >= s200 ? "above 200-day" : "below 200-day") : "—";
  if (bull && seq.length >= 4) return { label: "STACKED-BULLISH", tone: "gn", primary };
  if (bear && seq.length >= 4) return { label: "STACKED-BEARISH", tone: "rd", primary };
  const above = [e9, e21, s50, s200].filter(m => m != null && p >= m).length;
  const tot = [e9, e21, s50, s200].filter(m => m != null).length || 1;
  if (above >= tot - 1) return { label: "CONSTRUCTIVE", tone: "gn", primary };
  if (above <= 1) return { label: "WEAK / BELOW MAs", tone: "rd", primary };
  return { label: "MIXED · PULLBACK", tone: "amb", primary };
}

function LensTechnicals({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const s1 = useStateToggle("tl-1"); const s2 = useStateToggle("tl-2");
  const s3 = useStateToggle("tl-3"); const s4 = useStateToggle("tl-4");
  const s5 = useStateToggle("tl-5"); const s6 = useStateToggle("tl-6");
  const s7 = useStateToggle("tl-7"); const s8 = useStateToggle("tl-8");
  const L = window.coherentLevels ? window.coherentLevels(ticker) : { pivot: ticker.pivot, stop: ticker.stop, t1: ticker.t1, t2: ticker.t2, price: ticker.price };
  const t = useTech(ticker.symbol);
  const loading = t === null, failed = t === false;
  const T = (t && typeof t === "object") ? t : {};

  return (
    <div className="lens lens--tech">
      {window.LensSummaryBar && <LensSummaryBar ticker={ticker} mode={mode} kind="technicals" />}
      <TechHero ticker={ticker} mode={mode} t={T} loading={loading} failed={failed} />

      <div className="lens-section">
        <SectionHeader n={1} title="Indicator Dashboard"
          sub="RSI · MACD · Stoch · ADX · MFI · CMF · ATR · %B — all computed live"
          style={headerStyle} right={<StateToggle name="tl-1" />} />
        <StateWrap state={s1.value} source="computed from EODHD daily OHLCV">
          <div className="lens-pad"><IndicatorDash t={T} loading={loading} failed={failed} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={2} title="EMA / SMA Stack"
          sub="real moving averages · price vs each · alignment"
          style={headerStyle} right={<StateToggle name="tl-2" />} />
        <StateWrap state={s2.value} source="computed · EMA9/21/100 · SMA20/50/200">
          <div className="lens-pad"><MAStack ticker={ticker} t={T} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Structure Snapshot"
          sub="52-week position · swing distances · trend strength — full theory in the Patterns lens"
          style={headerStyle} right={<StateToggle name="tl-3" />} />
        <StateWrap state={s3.value} source="computed from price structure">
          <div className="lens-pad">
            <button className="tl-xlink mono" onClick={() => window.__setLens && window.__setLens("patterns")}>
              ↗ Open <b>Patterns</b> for the 14-theory confluence engine (Wyckoff · Elliott · Fib · Harmonic …)
            </button>
            <StructureSnapshot ticker={ticker} t={T} />
          </div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={4} title="S / R Confluence Ladder"
          sub="52w high/low · swing pivots · moving averages · VWAP — real levels, sorted"
          style={headerStyle} right={<StateToggle name="tl-4" />} />
        <StateWrap state={s4.value} source="computed from OHLCV structure">
          <div className="lens-pad"><SRLadder ticker={ticker} t={T} L={L} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={5} title="Volume Analytics"
          sub="RVOL · OBV · money-flow · last-60-session bars"
          style={headerStyle} right={<StateToggle name="tl-5" />} />
        <StateWrap state={s5.value} source="computed from EODHD volume">
          <div className="lens-pad"><VolumeAnalytics t={T} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={6} title="Statistical Backbone"
          sub="this setup's realized record · Wilson 95% lower bound"
          style={headerStyle} right={<StateToggle name="tl-6" />} />
        <StateWrap state={s6.value} source="picks_history · setup-conditional">
          <div className="lens-pad"><StatBackbone ticker={ticker} /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={7} title="Market Regime · Now"
          sub="the live macro regime this setup is trading into"
          style={headerStyle} right={<StateToggle name="tl-7" />} />
        <StateWrap state={s7.value} source="regime engine · live">
          <div className="lens-pad"><RegimeNow /></div>
        </StateWrap>
      </div>

      <div className="lens-section">
        <SectionHeader n={8} title="Cross-Lens Confluence"
          sub="this technical read alongside the live reads from the other engine lenses"
          style={headerStyle} right={<StateToggle name="tl-8" />} />
        <StateWrap state={s8.value} source="compositeVerdict reconciliation">
          <div className="lens-pad"><CrossLens lead="cy" cells={techCrossCells(ticker, mode, T)} /></div>
        </StateWrap>
      </div>

      <TheReadTech ticker={ticker} t={T} L={L} />
    </div>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────
function TechHero({ ticker, mode, t, loading, failed }) {
  const score = Math.round(_n(ticker.pillars && ticker.pillars.technical, 0));
  const sLabel = score >= 66 ? "STRONG" : score >= 45 ? "NEUTRAL" : "WEAK";
  const sTone = score >= 66 ? "gn" : score >= 45 ? "amb" : "rd";
  const ma = maRead(t);
  const rsi = _n(t.rsi), adx = _n(t.adx), rvol = _n(t.rvol), hist = _n(t.macd_hist), vwap = _n(t.vwap20), price = _n(t.price);
  const rsiTone = rsi == null ? "ink" : rsi >= 70 ? "amb" : rsi >= 50 ? "gn" : rsi >= 40 ? "amb" : "rd";
  return (
    <div className="hero tech-hero">
      <div className="th-left">
        <div className="label-cap">Composite technical · {mode}</div>
        <div className="th-score">
          <div className="th-score-num mono">{score}<span className="th-score-unit">/100</span></div>
          <Pill tone={sTone} dot>{sLabel}</Pill>
          {ma.label !== "—" && <Pill tone={ma.tone} small>{ma.label}</Pill>}
        </div>
        <div className="th-pill-row">
          {rsi != null && <Pill tone={rsiTone} small>RSI {rsi.toFixed(0)}</Pill>}
          {hist != null && <Pill tone={hist >= 0 ? "gn" : "rd"} small>MACD {hist >= 0 ? "+" : "−"}</Pill>}
          {adx != null && <Pill tone={adx >= 25 ? "gn" : "amb"} small>ADX {adx.toFixed(0)}</Pill>}
          {rvol != null && <Pill tone={rvol >= 1.3 ? "gn" : "amb"} small>RVOL {rvol.toFixed(2)}×</Pill>}
          {price != null && vwap != null && <Pill tone={price >= vwap ? "gn" : "rd"} small>{price >= vwap ? "VWAP·rec" : "sub-VWAP"}</Pill>}
        </div>
        {ma.primary !== "—" && <div className="mono dim2" style={{ fontSize: 11, marginTop: 6 }}>Primary trend: <b className={/above/.test(ma.primary) ? "up" : "dn"}>{ma.primary}</b></div>}
      </div>
      <div className="th-right">
        {loading ? <div className="mono dim2" style={{ padding: 30 }}>loading chart…</div>
          : failed ? <div className="mono dim2" style={{ padding: 30 }}>chart unavailable</div>
            : <MiniChart t={t} />}
      </div>
    </div>
  );
}

// real OHLC mini-chart from the last 60 candles + EMA21 + 52w-high + current price
function MiniChart({ t }) {
  const w = 320, h = 110;
  const data = (t.candles || []);
  if (data.length < 5) return <div className="mono dim2" style={{ padding: 30 }}>no candles</div>;
  const ema21 = _n(t.ema21), hi52 = _n(t.high_52w), cur = _n(t.price);
  const lows = data.map(d => d.l), highs = data.map(d => d.h);
  const min = Math.min(...lows), max = Math.max(...highs);
  const range = (max - min) || 1;
  const xStep = w / data.length;
  const yFor = v => h - ((v - min) / range) * (h - 10) - 5;
  const last = data[data.length - 1], lastX = (data.length - 1) * xStep + xStep / 2;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="mini-chart" style={{ overflow: "visible" }}>
      <line x1="0" y1={yFor((min + max) / 2)} x2={w} y2={yFor((min + max) / 2)} stroke="var(--line)" strokeDasharray="2 3" opacity="0.4" />
      {ema21 != null && ema21 >= min && ema21 <= max && <line x1="0" y1={yFor(ema21)} x2={w} y2={yFor(ema21)} stroke="var(--cy)" strokeOpacity="0.55" strokeDasharray="4 3" />}
      {hi52 != null && hi52 >= min && hi52 <= max && <><line x1="0" y1={yFor(hi52)} x2={w} y2={yFor(hi52)} stroke="var(--copper)" strokeOpacity="0.6" strokeDasharray="3 3" /><text x={w - 4} y={yFor(hi52) - 3} fontSize="8" className="mono" textAnchor="end" fill="var(--copper)">52w hi {hi52.toFixed(0)}</text></>}
      {data.map((d, i) => {
        const up = d.c >= d.o, x = i * xStep + 1, ww = Math.max(1.2, xStep - 2);
        return (
          <g key={i}>
            <line x1={x + ww / 2} y1={yFor(d.h)} x2={x + ww / 2} y2={yFor(d.l)} stroke={up ? "var(--gn)" : "var(--rd)"} strokeWidth="0.6" />
            <rect x={x} y={yFor(Math.max(d.o, d.c))} width={ww} height={Math.max(1, Math.abs(yFor(d.o) - yFor(d.c)))} fill={up ? "var(--gn)" : "var(--rd)"} opacity="0.9" />
          </g>
        );
      })}
      <circle cx={lastX} cy={yFor(last.c)} r="3.2" fill="var(--copper)" style={{ filter: "drop-shadow(0 0 6px var(--copper))" }} />
      {cur != null && <text x={lastX - 4} y={yFor(last.c) - 6} fontSize="8.5" className="mono" textAnchor="end" fill="var(--copper)">{cur.toFixed(2)}</text>}
    </svg>
  );
}

// ─── §1 Indicator dashboard (real) ───────────────────────────────────
function IndicatorDash({ t, loading, failed }) {
  if (loading) return <div className="mono dim2" style={{ padding: 16 }}>computing indicators…</div>;
  if (failed || t.price == null) return <div className="mono dim2" style={{ padding: 16 }}>Indicators unavailable for this name (no OHLCV).</div>;
  const dv = t.divergence;
  const div = !dv || dv.type === "none" ? { t: "NO DIVERGENCE", tone: "gn", note: dv ? dv.note : "oscillators confirm price" }
    : dv.type === "bearish" ? { t: "BEARISH DIVERGENCE", tone: "rd", note: dv.note }
      : { t: "BULLISH DIVERGENCE", tone: "gn", note: dv.note };
  const rsi = _n(t.rsi), macd = _n(t.macd), macdSig = _n(t.macd_signal), hist = _n(t.macd_hist), cross = _n(t.macd_cross_bars);
  const sk = _n(t.stoch_k), sd = _n(t.stoch_d), adx = _n(t.adx), pdi = _n(t.plus_di), mdi = _n(t.minus_di);
  const mfi = _n(t.mfi), cmf = _n(t.cmf), atr = _n(t.atr), atrp = _n(t.atr_pct), pctb = _n(t.bb_pctb);
  const cells = [
    { name: "RSI(14)", v: _f(rsi, 1), state: rsi >= 70 ? "overbought" : rsi >= 50 ? "bullish" : rsi >= 40 ? "neutral" : rsi >= 30 ? "weak" : "oversold", note: rsi >= 50 ? "above midline" : "below midline", tone: rsi == null ? "ink" : rsi >= 70 ? "amb" : rsi >= 50 ? "gn" : rsi >= 40 ? "amb" : "rd" },
    { name: "MACD(12,26,9)", v: hist == null ? "—" : (hist >= 0 ? "+" : "") + hist.toFixed(2), state: hist >= 0 ? "bullish" : "bearish", note: cross != null ? `crossed ${cross}d ago` : (macd != null && macdSig != null ? `${macd.toFixed(2)} vs ${macdSig.toFixed(2)}` : ""), tone: hist == null ? "ink" : hist >= 0 ? "gn" : "rd" },
    { name: "Stoch(14,3,3)", v: sk == null ? "—" : `${sk.toFixed(0)} / ${_f(sd, 0)}`, state: sk >= 80 ? "overbought" : sk >= 50 ? "rising" : sk >= 20 ? "neutral" : "oversold", note: sk != null && sd != null ? (sk >= sd ? "%K above %D" : "%K below %D") : "", tone: sk == null ? "ink" : sk >= 80 ? "amb" : sk >= 50 ? "gn" : sk >= 20 ? "amb" : "rd" },
    { name: "ADX(14)", v: _f(adx, 1), state: adx >= 25 ? "trending" : adx >= 20 ? "building" : "no trend", note: pdi != null && mdi != null ? (pdi >= mdi ? "+DI leads (bulls)" : "−DI leads (bears)") : "", tone: adx == null ? "ink" : adx >= 25 ? (pdi >= mdi ? "gn" : "rd") : "amb" },
    { name: "MFI(14)", v: _f(mfi, 1), state: mfi >= 80 ? "overbought" : mfi >= 50 ? "inflow" : mfi >= 20 ? "neutral" : "oversold", note: "volume-weighted", tone: mfi == null ? "ink" : mfi >= 80 ? "amb" : mfi >= 50 ? "gn" : mfi >= 20 ? "amb" : "rd" },
    { name: "CMF(20)", v: cmf == null ? "—" : (cmf >= 0 ? "+" : "") + cmf.toFixed(3), state: cmf >= 0.05 ? "accumulation" : cmf <= -0.05 ? "distribution" : "neutral", note: cmf >= 0 ? "buyers control" : "sellers control", tone: cmf == null ? "ink" : cmf >= 0.05 ? "gn" : cmf <= -0.05 ? "rd" : "amb" },
    { name: "ATR(14)", v: atr == null ? "—" : `$${atr.toFixed(2)}`, state: "volatility", note: atrp != null ? `${atrp.toFixed(1)}% of price` : "", tone: "ink" },
    { name: "BB %B(20,2)", v: _f(pctb, 2), state: pctb == null ? "—" : pctb >= 1 ? "above band" : pctb >= 0.8 ? "upper" : pctb >= 0.2 ? "mid" : pctb >= 0 ? "lower" : "below band", note: pctb != null && (pctb >= 1 || pctb <= 0) ? "extended" : "in range", tone: pctb == null ? "ink" : pctb >= 1 || pctb <= 0 ? "amb" : "gn" },
  ];
  return (
    <div>
      <div className={`ind-div ind-div--${div.tone}`}>
        <span className={`ind-div-tag kpi-tone--${div.tone}`}>⚡ {div.t}</span>
        <span className="mono dim2">{div.note}</span>
      </div>
      <div className="ind-grid">
        {cells.map((i, idx) => (
          <div key={idx} className={`ind-cell ind-${i.tone}`}>
            <div className="ind-name mono">{i.name}</div>
            <div className={`ind-v mono kpi-tone--${i.tone}`}>{i.v}</div>
            <div className="ind-state mono">{i.state}</div>
            <div className="ind-note mono dim">{i.note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── §2 MA stack (real) ──────────────────────────────────────────────
function MAStack({ ticker, t }) {
  const price = _n(t.price, _n(ticker.price));
  if (price == null) return <div className="mono dim2" style={{ padding: 14 }}>No price data.</div>;
  const defs = [["EMA 9", t.ema9], ["EMA 21", t.ema21], ["SMA 20", t.sma20], ["SMA 50", t.sma50], ["EMA 100", t.ema100], ["SMA 200", t.sma200]];
  const rows = [{ ma: "Price", v: price, tone: "copper", delta: null }].concat(
    defs.filter(([, v]) => _n(v) != null).map(([ma, v]) => {
      const mv = _n(v); const above = price >= mv;
      return { ma, v: mv, tone: above ? "gn" : "rd", delta: ((price / mv - 1) * 100) };
    })
  );
  const ma = maRead(t);
  return (
    <div className="ma-stack">
      <div className="ma-stack-grid">
        {rows.map((r, i) => (
          <div key={i} className="ma-row">
            <span className="mono ma-label">{r.ma}</span>
            <span className={`mono kpi-tone--${r.tone} ma-v`}>${r.v.toFixed(2)}</span>
            {r.delta != null && <span className={`mono ma-delta ${r.delta >= 0 ? "up" : "dn"}`}>{r.delta >= 0 ? "+" : ""}{r.delta.toFixed(1)}%</span>}
          </div>
        ))}
      </div>
      <div className="ma-summary">
        <Pill tone={ma.tone} dot>{ma.label}</Pill>
        <span className="mono dim2">Price vs {rows.length - 1} moving averages · {ma.primary}.</span>
      </div>
    </div>
  );
}

// ─── §3 Structure snapshot (real — replaces the old fabricated pattern matrix) ──
function StructureSnapshot({ ticker, t }) {
  const price = _n(t.price), hi = _n(t.high_52w), lo = _n(t.low_52w);
  const sh20 = _n(t.swing_hi_20), sl20 = _n(t.swing_lo_20), sh60 = _n(t.swing_hi_60), sl60 = _n(t.swing_lo_60);
  const adx = _n(t.adx), pdi = _n(t.plus_di), mdi = _n(t.minus_di), atrp = _n(t.atr_pct);
  if (price == null) return <div className="mono dim2" style={{ padding: 14 }}>No structure data.</div>;
  const pos52 = (hi != null && lo != null && hi > lo) ? ((price - lo) / (hi - lo) * 100) : null;
  const dist = (lvl) => lvl == null ? "—" : (price >= lvl ? "+" : "") + ((price / lvl - 1) * 100).toFixed(1) + "%";
  const cells = [
    { k: "52-week position", v: pos52 == null ? "—" : pos52.toFixed(0) + "%", note: hi != null ? `range $${lo.toFixed(0)}–$${hi.toFixed(0)}` : "", tone: pos52 == null ? "ink" : pos52 >= 75 ? "gn" : pos52 >= 40 ? "amb" : "rd" },
    { k: "vs 20d swing high", v: dist(sh20), note: sh20 != null ? `$${sh20.toFixed(2)}` : "", tone: sh20 == null ? "ink" : price >= sh20 * 0.99 ? "gn" : "amb" },
    { k: "vs 20d swing low", v: dist(sl20), note: sl20 != null ? `$${sl20.toFixed(2)}` : "", tone: sl20 == null ? "ink" : price <= sl20 * 1.01 ? "rd" : "gn" },
    { k: "vs 60d swing high", v: dist(sh60), note: sh60 != null ? `$${sh60.toFixed(2)}` : "", tone: "ink" },
    { k: "Trend strength (ADX)", v: adx == null ? "—" : adx.toFixed(0), note: adx == null ? "" : adx >= 25 ? (pdi >= mdi ? "trending up" : "trending down") : "no clear trend", tone: adx == null ? "ink" : adx >= 25 ? (pdi >= mdi ? "gn" : "rd") : "amb" },
    { k: "Daily volatility (ATR)", v: atrp == null ? "—" : atrp.toFixed(1) + "%", note: "of price", tone: "ink" },
  ];
  return (
    <div className="struct-grid">
      {cells.map((c, i) => (
        <div key={i} className={`struct-cell ind-${c.tone}`}>
          <div className="struct-k mono dim2">{c.k}</div>
          <div className={`struct-v mono kpi-tone--${c.tone}`}>{c.v}</div>
          <div className="struct-note mono dim">{c.note}</div>
        </div>
      ))}
    </div>
  );
}

// ─── §4 S/R Confluence (real levels) ─────────────────────────────────
function SRLadder({ ticker, t, L }) {
  const price = _n(t.price, _n(ticker.price));
  if (price == null) return <div className="mono dim2" style={{ padding: 14 }}>No price data.</div>;
  const stop = _n(L && L.stop);
  const raw = [
    { px: _n(t.high_52w), lbl: "52-week high", src: "52w" },
    { px: _n(t.swing_hi_60), lbl: "60-day swing high", src: "Swing" },
    { px: _n(t.swing_hi_20), lbl: "20-day swing high", src: "Swing" },
    { px: _n(t.vwap20), lbl: "20-day VWAP", src: "VWAP" },
    { px: _n(t.ema21), lbl: "EMA 21", src: "MA" },
    { px: _n(t.sma50), lbl: "SMA 50", src: "MA" },
    { px: _n(t.sma200), lbl: "SMA 200 · primary trend", src: "MA" },
    { px: _n(t.swing_lo_20), lbl: "20-day swing low", src: "Swing" },
    { px: _n(t.swing_lo_60), lbl: "60-day swing low", src: "Swing" },
    { px: _n(t.low_52w), lbl: "52-week low", src: "52w" },
    stop != null ? { px: stop, lbl: "Plan stop (1.25× ATR)", src: "ATR", stop: true } : null,
  ].filter(r => r && r.px != null);
  raw.push({ px: price, lbl: "Current price", src: "—", current: true });
  // dedupe near-identical levels (within 0.4%)
  raw.sort((a, b) => b.px - a.px);
  const rows = [];
  raw.forEach(r => { if (!rows.some(x => Math.abs(x.px - r.px) / r.px < 0.004 && !r.current && !x.current)) rows.push(r); });
  return (
    <div className="sr-ladder">
      {rows.map((r, i) => {
        const d = (r.px / price - 1) * 100;
        return (
          <div key={i} className={`sr-row ${r.current ? "sr-current" : ""} ${r.stop ? "sr-stop" : ""}`}>
            <span className={`mono sr-px ${r.stop ? "dn" : r.current ? "copper" : r.px >= price ? "up" : "dn"}`}>${r.px.toFixed(2)}</span>
            <span className="mono sr-lbl">{r.lbl}</span>
            <span className="mono dim2" style={{ minWidth: 54, textAlign: "right" }}>{r.current ? "" : (d >= 0 ? "+" : "") + d.toFixed(1) + "%"}</span>
            <span className="sr-sources">{r.src !== "—" && <span className="sr-src mono">{r.src}</span>}</span>
          </div>
        );
      })}
    </div>
  );
}

// ─── §5 Volume analytics (real) ──────────────────────────────────────
function VolumeAnalytics({ t }) {
  const rvol = _n(t.rvol), avg = _n(t.avg_vol20), obv = t.obv_trend, cmf = _n(t.cmf), candles = t.candles || [];
  const fmtVol = v => v == null ? "—" : v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : (v / 1e3).toFixed(0) + "K";
  if (!candles.length) return <div className="mono dim2" style={{ padding: 14 }}>No volume data.</div>;
  const vols = candles.map(c => c.v);
  const vmax = Math.max(...vols) || 1;
  return (
    <div className="vol-block">
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <KpiTile label="RVOL today" value={rvol == null ? "—" : rvol.toFixed(2) + "×"} tone={rvol == null ? "ink" : rvol >= 1.3 ? "gn" : "amb"} sub={rvol != null && rvol >= 1.3 ? "above 1.3× trigger" : "below 1.3× trigger"} />
        <KpiTile label="20d avg vol" value={fmtVol(avg)} tone="ink" sub="shares/day" />
        <KpiTile label="OBV trend" value={obv ? (obv === "rising" ? "↑ rising" : "↓ falling") : "—"} tone={obv === "rising" ? "gn" : obv === "falling" ? "rd" : "ink"} sub="21-day slope" />
        <KpiTile label="Money flow (CMF)" value={cmf == null ? "—" : (cmf >= 0 ? "+" : "") + cmf.toFixed(3)} tone={cmf == null ? "ink" : cmf >= 0.05 ? "gn" : cmf <= -0.05 ? "rd" : "amb"} sub={cmf >= 0 ? "accumulation" : "distribution"} />
      </div>
      <div className="vol-bars">
        {candles.map((c, i) => {
          const up = c.c >= c.o;
          return <div key={i} className={`vol-bar ${up ? "up" : "dn"} ${i === candles.length - 1 ? "is-pivot" : ""}`} style={{ height: `${Math.max(4, (c.v / vmax) * 100)}%` }} title={`vol ${fmtVol(c.v)}`} />;
        })}
      </div>
      <div className="vol-note mono dim2">Last {candles.length} sessions · bar height = real session volume · green/red = up/down close.</div>
    </div>
  );
}

// ─── §6 Statistical backbone (real setupStats only) ──────────────────
function StatBackbone({ ticker }) {
  const s = ticker.setupStats || {};
  const has = _n(s.n) != null && s.n > 0;
  if (!has) return (
    <div className="stat-block">
      <div className="mono dim2" style={{ padding: 12 }}>No closed-trade sample for this setup yet — the statistical backbone needs realized history (picks_history). Nothing to show rather than invent a track record.</div>
    </div>
  );
  const small = s.n < 30;
  return (
    <div className="stat-block">
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        {window.WilsonPill && <WilsonPill n={s.n} winRate={s.winRate} lb={s.wilsonLB} />}
        <Pill tone={s.pf != null && s.pf >= 1.3 ? "gn" : "amb"} small>PROFIT FACTOR {s.pf != null ? s.pf.toFixed(2) : "—"}</Pill>
        <Pill tone="copper" small>MEDIAN {s.medianR != null ? (s.medianR >= 0 ? "+" : "") + s.medianR.toFixed(2) + "R" : "—"}</Pill>
        {small && <Pill tone="rd" small>n &lt; 30 · preliminary</Pill>}
      </div>
      <div className="stat-note mono dim" style={{ marginTop: 10 }}>
        Source: picks_history (setup-conditional) · Wilson 95% lower bound{small ? " · sample under 30 — treat as preliminary, half-size per the calibration overlay." : "."}
      </div>
    </div>
  );
}

// ─── §7 Live market regime (real) ────────────────────────────────────
function RegimeNow() {
  const m = (window.__BV && window.__BV.market) || {};
  const regime = m.regime || (m.funnel && m.funnel.regime) || null;
  const vix = _n(m.vix), breadth = _n(m.breadth_pct_above_50d != null ? m.breadth_pct_above_50d : m.breadth);
  if (!regime && vix == null) return <div className="mono dim2" style={{ padding: 12 }}>Live regime unavailable — see the Market tab.</div>;
  const tone = /panic|risk_off|bear/i.test(regime || "") ? "rd" : /choppy|neutral/i.test(regime || "") ? "amb" : "gn";
  return (
    <div className="reg-now">
      <div className="reg-now-main">
        <Pill tone={tone} dot>{(regime || "—").replace(/_/g, " ").toUpperCase()}</Pill>
        <span className="mono dim2">the live macro regime this setup trades into</span>
      </div>
      <div className="kpi-row" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 10 }}>
        <KpiTile label="VIX" value={vix == null ? "—" : vix.toFixed(1)} tone={vix == null ? "ink" : vix >= 25 ? "rd" : vix >= 18 ? "amb" : "gn"} sub={vix != null ? (vix >= 25 ? "elevated" : vix >= 18 ? "moderate" : "calm") : ""} />
        <KpiTile label="Breadth >50d" value={breadth == null ? "—" : breadth.toFixed(0) + "%" } tone={breadth == null ? "ink" : breadth >= 55 ? "gn" : breadth >= 35 ? "amb" : "rd"} sub="% of universe" />
      </div>
      <div className="mono dim2" style={{ fontSize: 10.5, marginTop: 8 }}>Per-setup × per-regime win rates require the backtest decomposition (regime_sharpe_decomp) — not fabricated here. This shows the live regime context only.</div>
    </div>
  );
}

// ─── §8 Cross-lens (real engine reads) ───────────────────────────────
function techCrossCells(ticker, mode, t) {
  const cells = [];
  const ma = maRead(t);
  cells.push({ lens: "Technicals", verdict: ma.label === "—" ? "—" : ma.tone === "gn" ? "BULL" : ma.tone === "rd" ? "BEAR" : "MIXED", tone: ma.tone, note: ma.label === "—" ? "computing" : `${ma.label.toLowerCase()}` });
  const cv = window.compositeVerdict ? window.compositeVerdict(ticker, mode) : null;
  if (cv && cv.lenses) {
    ["Patterns", "SMC", "AI Edge", "Risk", "Track Rec."].forEach(k => {
      const l = cv.lenses.find(x => x.k === k);
      if (l) cells.push({ lens: l.k, verdict: l.v >= 60 ? "BULL" : l.v >= 45 ? "MIXED" : "BEAR", tone: l.tone, note: l.why });
    });
  }
  return cells;
}

// ─── The Read (real) ─────────────────────────────────────────────────
function TheReadTech({ ticker, t, L }) {
  const price = _n(t.price, _n(ticker.price));
  const trigger = _n(t.swing_hi_20) || _n(t.high_52w);
  const stop = _n(L && L.stop);
  const atr = _n(t.atr);
  const ma = maRead(t);
  const rvolNote = "1.3× RVOL";
  return (
    <div className="lens-call">
      <span className="label-cap">The Read · Technicals</span>
      <span className="mono">
        <b className={`kpi-tone--${ma.tone}`}>{ma.label === "—" ? "Structure pending" : ma.label}</b>
        {trigger != null && price != null && <> · {price >= trigger ? <>holding above</> : <>breakout confirms on a close &gt;</>} <b className="copper">${trigger.toFixed(2)}</b> on &gt; <b>{rvolNote}</b></>}
        {stop != null && <>. Stop <b className="dn">${stop.toFixed(2)}</b>{atr != null && <> ({(atr).toFixed(2)} ATR)</>}</>}
        {L && L.t1 != null && L.pivot != null && L.stop != null && (L.pivot * 1.002 - L.stop) !== 0 && <>. R-multiple {(((L.t1 - L.pivot * 1.002) / (L.pivot * 1.002 - L.stop))).toFixed(2)}.</>}
      </span>
    </div>
  );
}

window.LensTechnicals = LensTechnicals;
