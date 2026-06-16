// detail-panel.jsx — the resizable, sub-tab-nav right panel
// Hosts the 14 lens shells (only 3 are fully built: Plan, Technicals, Investment).

const { useState: useStateDP, useEffect: useEffectDP, useRef: useRefDP } = React;

// Live watchlist membership for `sym`, re-rendering on watchlist-change.
function useWatchlist(sym) {
  const [, force] = useStateDP(0);
  useEffectDP(() => {
    const h = () => force(x => x + 1);
    window.addEventListener("watchlist-change", h);
    return () => window.removeEventListener("watchlist-change", h);
  }, []);
  return window.WatchStore ? window.WatchStore.has(sym) : false;
}

function DetailPanel({
  ticker, lensId, onLensId,
  containerWidth = 800,
  mode,
  headerStyle, kpiStyle, heroStyle, lensTabs = "wrap",
  focusMode, onToggleFocus, tier = 4, onTier
}) {
  // resolve panel size category for reflow (driven by actual rendered width)
  const sizeCat = containerWidth < 540 ? "S" : containerWidth < 760 ? "M" : containerWidth < 1000 ? "L" : "XL";
  const lensMinT = (window.LENS_TIER || {})[lensId] ?? 0;
  const lensLocked = lensMinT > tier;

  return (
    <section className={`dpanel dpanel--${sizeCat}`}>
      <DetailHeader ticker={ticker} mode={mode} sizeCat={sizeCat}
      focusMode={focusMode} onToggleFocus={onToggleFocus} />

      <DetailTabs lensId={lensId} onLensId={onLensId} sizeCat={sizeCat} tier={tier} variant={lensTabs} />

      <div className="dpanel-body">
        {lensLocked ?
        <UpgradeGate kind="lens" name={(window.LENSES || []).find((l) => l.id === lensId)?.label || lensId} minTier={lensMinT} onTier={onTier} /> :
        <React.Fragment>
          <SectionNav lensId={lensId} />
          <DetailLens
            lensId={lensId}
            ticker={ticker}
            mode={mode}
            sizeCat={sizeCat}
            headerStyle={headerStyle}
            kpiStyle={kpiStyle}
            heroStyle={heroStyle} />
        </React.Fragment>
        }
      </div>
    </section>);

}

// Sticky in-lens section jump-nav. Scans the rendered lens for §N · title
// headers, renders quick-jump chips, scroll-spies the active section.
function SectionNav({ lensId }) {
  const [items, setItems] = useStateDP([]);
  const [active, setActive] = useStateDP(0);
  const navRef = useRefDP(null);

  useEffectDP(() => {
    const scan = () => {
      const body = navRef.current && navRef.current.closest(".dpanel-body");
      if (!body) return;
      const secs = [...body.querySelectorAll(".lens-section")];
      const found = secs.map((el, i) => {
        const title = el.querySelector(".sec-hdr-title");
        if (!title) return null;
        const label = title.textContent.trim();
        el.dataset.secIdx = i;
        return { i, n: String(i + 1), label };
      }).filter(Boolean);
      setItems(found);
    };
    // let the lens paint first
    const t1 = setTimeout(scan, 60);
    const t2 = setTimeout(scan, 260);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [lensId]);

  useEffectDP(() => {
    const body = navRef.current && navRef.current.closest(".dpanel-body");
    if (!body || items.length === 0) return;
    const onScroll = () => {
      const navH = navRef.current ? navRef.current.offsetHeight : 0;
      const secs = [...body.querySelectorAll(".lens-section")];
      let cur = 0;
      for (let i = 0; i < secs.length; i++) {
        if (secs[i].offsetTop - navH - 24 <= body.scrollTop) cur = i;
      }
      setActive(cur);
    };
    body.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => body.removeEventListener("scroll", onScroll);
  }, [items]);

  const jump = (i) => {
    const body = navRef.current && navRef.current.closest(".dpanel-body");
    if (!body) return;
    // let collapsible Overview sections open themselves before we measure
    window.dispatchEvent(new CustomEvent("ov-jump-open", { detail: i }));
    const sec = body.querySelector(`.lens-section[data-sec-idx="${i}"]`);
    if (!sec) return;
    const navH = navRef.current ? navRef.current.offsetHeight : 0;
    const target = Math.max(0, sec.offsetTop - navH - 10);
    setActive(i);
    // rAF tween for smoothness; guaranteed final assignment so it always lands
    const start = body.scrollTop, dist = target - start, dur = 300;
    let t0 = null, raf = 0;
    const step = (ts) => {
      if (t0 === null) t0 = ts;
      const p = Math.min(1, (ts - t0) / dur);
      const ease = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      body.scrollTop = start + dist * ease;
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    // fallback: re-measure after any collapsed section has expanded, then land
    setTimeout(() => {
      const s2 = body.querySelector(`.lens-section[data-sec-idx="${i}"]`);
      const finalT = s2 ? Math.max(0, s2.offsetTop - navH - 10) : target;
      if (Math.abs(body.scrollTop - finalT) > 2) body.scrollTop = finalT;
    }, dur + 90);
  };

  if (items.length < 2) return <div ref={navRef} className="sec-nav sec-nav--empty" />;
  return (
    <div ref={navRef} className="sec-nav">
      <span className="sec-nav-cap mono">SECTIONS</span>
      <div className="sec-nav-chips">
        {items.map((it) => (
          <button key={it.i} className={`sec-nav-chip ${active === it.i ? "is-active" : ""}`}
            onClick={() => jump(it.i)} title={it.label}>
            <span className="sec-nav-n mono">§{it.n}</span>
            <span className="sec-nav-l">{it.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// real wall-clock in US Eastern (market tz), ticking — replaces the old frozen 14:23:08
function LiveClock() {
  const [t, setT] = React.useState(() => Date.now());
  React.useEffect(() => { const id = setInterval(() => setT(Date.now()), 1000); return () => clearInterval(id); }, []);
  let s;
  try { s = new Date(t).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false }); }
  catch (e) { s = new Date(t).toLocaleTimeString("en-US", { hour12: false }); }
  return <>{s} ET</>;
}

function DetailHeader({ ticker, mode, sizeCat, focusMode, onToggleFocus }) {
  const onWatch = useWatchlist(ticker.symbol);
  const addWatch = () => window.WatchStore && window.WatchStore.toggle({
    sym: ticker.symbol, name: ticker.name, sector: ticker.sector,
    price: ticker.price, chg: ticker.chg, score: ticker.score,
    verdict: ticker.verdict, setup: ticker.setupFamily,
  });
  return (
    <div className="dp-hdr">
      <div className="dp-hdr-row">
        <div className="dp-hdr-id">
          <div className="dp-hdr-sym mono"><b>{ticker.symbol}</b>{ticker.live && <span className="dp-live-badge mono" title="Not in the seeded universe — pulled live on-demand">⚡ LIVE</span>}</div>
          <div className="dp-hdr-meta dim2">
            <span>{ticker.exchange}</span>
            <span>·</span>
            <span>{ticker._loading ? "fetching live quote…" : ticker.live ? "live quote · limited history" : `${ticker.sector} · ${ticker.industry}`}</span>
            {ticker.mcap != null && <><span>·</span><span className="mono">${(ticker.mcap / 1e9).toFixed(2)}B</span></>}
          </div>
        </div>
        <div className="dp-hdr-actions">
          <div className="dp-hdr-modeseg seg">
            {["SWING", "POSITION", "INVESTMENT"].map(m => (
              <button key={m} className={`seg-btn ${mode === m ? "is-on" : ""}`} onClick={() => window.__setMode && window.__setMode(m)} title={`${m} horizon`}>
                {m === "INVESTMENT" ? "INVEST" : m}
              </button>
            ))}
          </div>
          <button
            className={`btn btn--sm ${onWatch ? "is-watched" : ""}`}
            onClick={addWatch}
            title={onWatch ? `Remove ${ticker.symbol} from watchlist` : `Add ${ticker.symbol} to watchlist`}>
            {onWatch ? "✓ On Watchlist" : "＋ Watchlist"}
          </button>
          <button
            className={`btn btn--sm ${focusMode ? "btn--primary" : ""}`}
            onClick={onToggleFocus}
            title={focusMode ? "Exit focus mode (show scan list)" : "Focus mode (collapse scan list)"}>
            
            {focusMode ? "◀ Exit Focus" : "◉ Focus"}
          </button>
        </div>
      </div>
      <div className="dp-hdr-row dp-hdr-quote">
        <div className="dp-quote-price mono"><b>{ticker.price != null ? "$" + ticker.price.toFixed(2) : (ticker._loading ? "…" : "—")}</b></div>
        {ticker.price != null && ticker.chgAbs != null && (
          <div className={`dp-quote-chg mono ${ticker.chg >= 0 ? "up" : "dn"}`}>
            {ticker.chg >= 0 ? "+" : ""}{ticker.chgAbs.toFixed(2)} ({ticker.chg.toFixed(2)}%)
          </div>
        )}
        <div className="dp-quote-extra mono dim">
          {ticker.vol != null && <span>VOL <b className="dim2">{(ticker.vol / 1e6).toFixed(2)}M</b> · </span>}
          {ticker.rvol != null && <span>RVOL <b className="dim2">{ticker.rvol.toFixed(2)}×</b> · </span>}
          {ticker.avgVol != null && <span>AVG <b className="dim2">{(ticker.avgVol / 1e6).toFixed(2)}M</b></span>}
          <span>· RSI <b className="dim2">{ticker.rsi != null ? ticker.rsi.toFixed(1) : "—"}</b></span>
          <span>· β <b className="dim2">{ticker.beta != null ? ticker.beta.toFixed(2) : "—"}</b></span>
        </div>
        <div className="dp-hdr-spacer" />
        <Pill tone="gn" small dot>LIVE · <LiveClock /></Pill>
        {ticker.score != null
          ? <Pill tone="copper" small>{(window.biasRead ? window.biasRead(ticker).label : secBias(ticker.verdict))} · {ticker.score}</Pill>
          : ticker._offUniverse ? <Pill tone="slate" small>off-universe · not scanned</Pill> : null}
      </div>
    </div>);

}

function DetailTabs({ lensId, onLensId, sizeCat, tier = 4, variant = "wrap" }) {
  return (
    <div className={`dp-tabs dp-tabs--${variant}`}>
      <div className="dp-tabs-scroll">
        {LENSES.map((l, i) => {
          const active = lensId === l.id;
          const minT = (window.LENS_TIER || {})[l.id] ?? 0;
          const locked = minT > tier;
          return (
            <button
              key={l.id}
              className={`dp-tab dp-tab--${l.accent} ${active ? "is-on" : ""} ${locked ? "is-locked" : ""}`}
              onClick={() => onLensId(l.id)}
              title={locked ? `${l.q} · TIER ${minT}+` : l.q}>
              
              <span className="dp-tab-icon">{locked ? "🔒" : LENS_ICONS[l.id]}</span>
              <span className="dp-tab-num mono">{String(i + 1).padStart(2, "0")}</span>
              <span className="dp-tab-label">{l.label.replace(/ · .*/, "")}</span>
              {locked ?
              <span className="dp-tab-tier mono">T{minT}</span> :
              <span className={`dp-tab-dot dp-tab-dot--${l.verdict}`} title={`${({ gn: "Constructive", amb: "Mixed", rd: "Cautious" })[l.verdict] || "Neutral"} read · informational`} />}
              <span className="dp-tab-kbd kbd">{l.kbd}</span>
            </button>);

        })}
      </div>
    </div>);

}

function DetailLens({ lensId, ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const props = { ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle };
  // off-universe ticker is still resolving (detailLive) — many lenses derive off a
  // real price; render a loading state rather than compute on a null price.
  if (ticker && (ticker._loading || ticker.price == null) && !ticker._noData) {
    return <div className="lens" style={{ padding: "48px 18px", textAlign: "center" }}>
      <div className="mono dim2" style={{ fontSize: 13 }}>Fetching live data for <b className="copper">{ticker.symbol}</b>…</div>
    </div>;
  }
  if (ticker && ticker._noData) {
    return <div className="lens" style={{ padding: "48px 18px", textAlign: "center" }}>
      <div className="mono dim2" style={{ fontSize: 13 }}>No market data available for <b className="copper">{ticker.symbol}</b> — it may be delisted, an index, or outside coverage.</div>
    </div>;
  }
  if (lensId === "plan") return <LensPlan {...props} />;
  if (lensId === "technicals") return <LensTechnicals {...props} />;
  if (lensId === "investment") return <LensInvestment {...props} />;
  if (lensId === "overview") return <LensOverview {...props} />;
  if (lensId === "chart") return <LensChart {...props} />;
  if (lensId === "patterns") return <LensPatterns {...props} />;
  if (lensId === "smc") return <LensSMC {...props} />;
  if (lensId === "earnings") return <LensEarnings {...props} />;
  if (lensId === "risk") return <LensRisk {...props} />;
  if (lensId === "options") return <LensOptions {...props} />;
  if (lensId === "tape") return <LensTape {...props} />;
  if (lensId === "portfolio") return <LensPortfolio {...props} />;
  if (lensId === "time" && window.LensTime) return <window.LensTime {...props} />;
  if (lensId === "tv" && window.LensTV) return <window.LensTV {...props} />;
  if (lensId === "bullalgo" && window.LensBullAlgo) return <window.LensBullAlgo {...props} />;
  // AI Edge lens = real per-ticker model forecast (LensML, /api/ml). The
  // synthetic AIAnalystView (3-head vote + historical analogs — constructs the
  // real model doesn't emit) was removed here 2026-06-07; it survives only on
  // the AI Predictions board surface pending a real rebuild.
  if (lensId === "mledge") return (
    <div className="lens-ml-wrap">
      <LensML {...props} />
    </div>
  );
  return <LensStub lensId={lensId} />;
}

function LensStub({ lensId }) {
  const lens = LENSES.find((l) => l.id === lensId);
  return (
    <div className="lens-stub">
      <div className="lens-stub-card">
        <div className="label-cap">Lens</div>
        <h2 className="mono">{lens?.label}</h2>
        <div className="mono dim2">{lens?.q}</div>
        <div className="state-banner" style={{ margin: 0, marginTop: 16 }}>
          <span className="state-banner-icon">⚠</span>
          <span>
            <b>Partial scaffolding</b> — lens shell reachable, content not built in this prototype.
            <br />
            Built lenses: <b>Overview · Plan · Ticket · Technicals · Investment · Value</b>.
          </span>
        </div>
      </div>
    </div>);

}

// ──── Overview lens (compact — relies on hero + cross-lens) ──────────
function LensOverview({ ticker, mode, sizeCat, headerStyle, kpiStyle, heroStyle }) {
  const state = useStateToggle("ov-state", "live");
  return (
    <div className="lens">
      <VerdictHero ticker={ticker} mode={mode} heroStyle={heroStyle} sizeCat={sizeCat} />

      <div className="lens-section">
        <SectionHeader n={1} title="Trigger · Invalidate · Sizing"
        sub={`Source: scan output · ${ticker.setupFamily}`}
        style={headerStyle}
        right={<StateToggle name="ov-state" />} />
        
        <StateWrap state={state.value} source="scan output · last_bundle.json">
          <div className="lens-pad">
            <div className="kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
              <KpiTile label="Trigger" value={`>$${ticker.pivot.toFixed(2)}`} tone="copper" sub="pivot of base #2" style={kpiStyle} />
              <KpiTile label="Stop" value={`$${ticker.stop.toFixed(2)}`} tone="rd" sub="−5.7% from entry" style={kpiStyle} />
              <KpiTile label="T1 / T2" value={`$${ticker.t1.toFixed(0)} · $${ticker.t2.toFixed(0)}`} tone="gn" sub="+8.0% · +16.0%" style={kpiStyle} />
              <KpiTile label="R-mult" value={ticker.rMultiple.toFixed(2)} unit="R" tone="copper" sub="risk-adjusted" style={kpiStyle}
              delta={null} />
            </div>
          </div>
        </StateWrap>
      </div>

      <div className="lens-2col">
      <div className="lens-section">
        <SectionHeader n={2} title="Cross-Lens Confluence"
          sub="How the other disciplines see ARCM right now"
          style={headerStyle} />
        
        <div className="lens-pad">
          <CrossLens
              lead="copper"
              cells={[
              { lens: "Overview", verdict: "Bullish", tone: "gn", note: `score ${ticker.score} · 4 of 5 pillars green` },
              { lens: "Technicals", verdict: "PASS", tone: "gn", note: "RSI 64 · MACD+ · VWAP-reclaim" },
              { lens: "Value", verdict: "MARG.", tone: "amb", note: "MoS 6% · slight premium" },
              { lens: "Risk", verdict: "OK", tone: "gn", note: "VaR(1d) −2.1% · half-Kelly 0.42" },
              { lens: "Earnings", verdict: "11 d", tone: "amb", note: "ER in window · cap size" }]
              } />
          
        </div>
      </div>

      <div className="lens-section">
        <SectionHeader n={3} title="Pre-Mortem"
          sub="What would make this thesis wrong?"
          style={headerStyle} />
        
        <div className="lens-pad">
          <div className="premortem">
            <div className="premortem-row">
              <span className="pm-num mono">1</span>
              <span className="pm-text">Loses VWAP intraday AND closes below $65.10 — invalidation cascade.</span>
              <Pill tone="rd" small>HARD</Pill>
            </div>
            <div className="premortem-row">
              <span className="pm-num mono">2</span>
              <span className="pm-text">Sector ETF (XLB) breaks 50-DMA on +1.5σ volume — regime flip.</span>
              <Pill tone="amb" small>MEDIUM</Pill>
            </div>
            <div className="premortem-row">
              <span className="pm-num mono">3</span>
              <span className="pm-text">CPI prints &gt;0.4% MoM next Wed — risk-off reset.</span>
              <Pill tone="amb" small>MACRO</Pill>
            </div>
          </div>
        </div>
      </div>
      </div>

      <div className="lens-call">
        <span className="label-cap">The Read · {mode}</span>
        <span className="mono">
          A breakout above <b className="copper">${ticker.pivot.toFixed(2)}</b> would confirm the setup ·
          half-Kelly sizing reference · {ticker.setupStats.winRate != null ? (ticker.setupStats.winRate * 100).toFixed(0) + "% historical · n=" + ticker.setupStats.n : "no ledger history yet"}.
        </span>
      </div>
    </div>);

}

// ─── Hero ────────────────────────────────────────────────────────────
function VerdictHero({ ticker, mode, heroStyle, sizeCat }) {
  // heroStyle: 'radar' | 'gauge' | 'cone'
  return (
    <div className="hero" style={{ fontSize: "13px", lineHeight: "1" }}>
      <div className="hero-left">
        <div className="hero-verdict-block">
          <div className="label-cap">Composite bias · {mode}</div>
          <div className="hero-verdict">
            <span className="hero-verdict-tag">{(window.biasRead ? window.biasRead(ticker).label : secBias(ticker.verdict))}</span>
            <span className="hero-verdict-score mono">{ticker.score}<span className="hero-score-unit">/100</span></span>
          </div>
          <div className="hero-verdict-line mono dim2">
            {ticker.setupFamily} · hold ~{ticker.holdDays}d · target {ticker.rMultiple.toFixed(1)}R
          </div>
        </div>

        <div className="hero-pillars">
          {Object.entries(ticker.pillars).map(([k, v]) =>
          <div key={k} className="hero-pill-row">
              <span className="label-cap" style={{ fontSize: "13px" }}>{k}</span>
              <div className="hero-pill-bar">
                <div
                className="hero-pill-fill"
                style={{ width: `${v}%`, background: v >= 70 ? "var(--gn)" : v >= 50 ? "var(--amb)" : "var(--rd)" }} />
              
              </div>
              <span className="mono tabular">{v}</span>
            </div>
          )}
        </div>
      </div>

      <div className="hero-right">
        {heroStyle === "gauge" && <Gauge value={ticker.score} label="OVERALL SCORE" size={sizeCat === "S" ? 110 : 150} />}
        {heroStyle === "radar" && <Radar pillars={ticker.pillars} size={sizeCat === "S" ? 150 : 200} />}
        {heroStyle === "cone" &&
        <div className="hero-cone-wrap">
            <div className="label-cap" style={{ marginBottom: 6 }}>10D implied cone · σ ±{ticker.ml.magnitude.hi.toFixed(0)}%</div>
            <Cone lo={ticker.ml.magnitude.lo} mid={ticker.ml.magnitude.mid} hi={ticker.ml.magnitude.hi} />
          </div>
        }
      </div>
    </div>);

}

// State toggle helper — tiny hook + UI
const __stateStore = {};
function useStateToggle(key, initial = "live") {
  const [v, setV] = useStateDP(() => __stateStore[key] || initial);
  useEffectDP(() => {
    const handler = (e) => {if (e.detail.key === key) setV(e.detail.value);};
    window.addEventListener("state-toggle", handler);
    return () => window.removeEventListener("state-toggle", handler);
  }, [key]);
  return { value: v };
}

function StateToggle({ name }) {
  const [v, setV] = useStateDP(() => __stateStore[name] || "live");
  const set = (val) => {
    __stateStore[name] = val;
    setV(val);
    window.dispatchEvent(new CustomEvent("state-toggle", { detail: { key: name, value: val } }));
  };
  return (
    <div className="state-toggle" title="Cycle the 4 data states for this section">
      {[
      { v: "live", label: "Live", tone: "gn" },
      { v: "loading", label: "···", tone: "ink" },
      { v: "empty", label: "Empty", tone: "ink" },
      { v: "scaffold", label: "Scaf", tone: "amb" }].
      map((opt) =>
      <button
        key={opt.v}
        className={`st-btn ${v === opt.v ? `is-on st-${opt.tone}` : ""}`}
        onClick={() => set(opt.v)}>
        {opt.label}</button>
      )}
    </div>);

}

Object.assign(window, { DetailPanel, useStateToggle, StateToggle, VerdictHero });