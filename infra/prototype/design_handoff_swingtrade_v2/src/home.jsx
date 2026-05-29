// home.jsx — landing/home view for the terminal
// Full-bleed market map + summary cards. Shown when no ticker is "drilled into".

const { useMemo: useMemoH } = React;

function HomeView({ onTicker, mode, surface }) {
  return (
    <div className="home">
      <HomeHero mode={mode} />

      <div className="home-grid">
        <div className="home-map-wrap">
          <MarketMap onTicker={onTicker} dims={{ w: 1100, h: 460 }} />
        </div>

        <div className="home-side">
          <HomeCard
            title="Top BUY · today"
            sub="ranked by R × Wilson LB"
            cta="Open BUY surface →"
          >
            <HomeTopList
              items={WATCHLIST.filter(w => w.verdict === "BUY").slice(0, 5)}
              onTicker={onTicker}
            />
          </HomeCard>

          <HomeCard
            title="Macro · regime"
            sub="bull · low-VIX · trend up"
          >
            <HomeMacro />
          </HomeCard>
        </div>
      </div>

      <div className="home-grid-2">
        <HomeCard title="Day's movers" sub="±% on the day · scan output">
          <HomeMovers onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Calendar · next 14d" sub="ER · macro · capacity">
          <HomeCalendar />
        </HomeCard>
        <HomeCard title="Your book" sub="3 positions · $108,420 NAV">
          <HomeBook />
        </HomeCard>
      </div>
    </div>
  );
}

// ─── Hero strip ──────────────────────────────────────────────────
function HomeHero({ mode }) {
  return (
    <div className="home-hero">
      <div className="hh-left">
        <div className="hh-eyebrow mono">SwingTrade · 2026-05-28 · 14:23 ET</div>
        <h1 className="hh-title mono">
          <span>612 ranked</span>
          <span className="hh-sep">/</span>
          <span className="up">14 BUY</span>
          <span className="hh-sep">·</span>
          <span className="warn">8 WATCH-CLOSE</span>
          <span className="hh-sep">·</span>
          <span className="dn">31 AVOID</span>
        </h1>
        <div className="hh-line mono dim2">
          Bundle generated <b>02:14:08 ET</b> · sleeves: Continuation BO · VCP · Earnings drift · Mean revert.
          Mode <b className="copper">{mode}</b>. Click any tile or row to enter the 14-lens detail.
        </div>
      </div>
      <div className="hh-stats">
        <HomeStat label="S&P 500"   value="6,148.2" delta="+0.42%" tone="gn" />
        <HomeStat label="NASDAQ"    value="20,310"  delta="+0.84%" tone="gn" />
        <HomeStat label="RUSSELL"   value="2,182"   delta="−0.21%" tone="rd" />
        <HomeStat label="VIX"       value="17.4"    delta="−1.8%"  tone="gn" />
        <HomeStat label="DXY"       value="103.4"   delta="+0.10%" tone="ink" />
        <HomeStat label="US10Y"     value="4.32%"   delta="−2bp"   tone="gn" />
      </div>
    </div>
  );
}

function HomeStat({ label, value, delta, tone }) {
  return (
    <div className="hs">
      <div className="hs-label label-cap">{label}</div>
      <div className="hs-value mono">{value}</div>
      <div className={`hs-delta mono kpi-tone--${tone}`}>{delta}</div>
    </div>
  );
}

// ─── Card wrapper ────────────────────────────────────────────────
function HomeCard({ title, sub, cta, children }) {
  return (
    <div className="hc">
      <div className="hc-hdr">
        <div>
          <div className="hc-title mono">{title}</div>
          {sub && <div className="hc-sub mono dim">{sub}</div>}
        </div>
        {cta && <button className="hc-cta mono">{cta}</button>}
      </div>
      <div className="hc-body">{children}</div>
    </div>
  );
}

// ─── Top BUY list ────────────────────────────────────────────────
function HomeTopList({ items, onTicker }) {
  return (
    <div className="htl">
      {items.map((it, i) => (
        <button key={it.sym} className="htl-row" onClick={() => onTicker(it.sym)}>
          <span className="htl-rank mono dim">{String(i + 1).padStart(2, "0")}</span>
          <span className="htl-sym mono"><b>{it.sym}</b></span>
          <span className="htl-name dim">{it.name}</span>
          <span className={`htl-chg mono ${it.chg >= 0 ? "up" : "dn"}`}>
            {it.chg >= 0 ? "+" : ""}{it.chg.toFixed(2)}%
          </span>
          <span className="htl-score mono"><b>{it.score}</b></span>
        </button>
      ))}
    </div>
  );
}

// ─── Macro panel ─────────────────────────────────────────────────
function HomeMacro() {
  const indicators = [
    { k: "QQQ vs 50-DMA",    v: "+3.4%",  tone: "gn" },
    { k: "SPY vs 200-DMA",   v: "+7.2%",  tone: "gn" },
    { k: "VIX percentile 1y",v: "32%",    tone: "gn" },
    { k: "Yield-curve 2s10s",v: "+24bp",  tone: "gn", sub: "un-inverted" },
    { k: "Credit spreads (HY)",v: "342bp", tone: "amb", sub: "stable" },
    { k: "Dollar (DXY) z",   v: "+0.4",   tone: "ink" },
  ];
  return (
    <div className="macro-list">
      {indicators.map((m, i) => (
        <div key={i} className="macro-row">
          <span className="mono dim2">{m.k}</span>
          <span className={`mono kpi-tone--${m.tone}`}>{m.v}</span>
          {m.sub && <span className="mono dim">{m.sub}</span>}
        </div>
      ))}
      <div className="macro-foot">
        <Pill tone="gn" dot>BULL · LOW-VIX</Pill>
        <span className="mono dim2">all 6 gates passing · highest WR regime</span>
      </div>
    </div>
  );
}

// ─── Movers grid ─────────────────────────────────────────────────
function HomeMovers({ onTicker }) {
  const movers = useMemoH(() => {
    return HEATMAP
      .map(([sym, sector, mcap, chg]) => ({ sym, sector, mcap, chg }))
      .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg))
      .slice(0, 12);
  }, []);
  return (
    <div className="hm-grid">
      {movers.map(m => (
        <button key={m.sym} className="hm-cell" onClick={() => onTicker(m.sym)}>
          <span className="mono hm-sym"><b>{m.sym}</b></span>
          <span className={`mono hm-chg ${m.chg >= 0 ? "up" : "dn"}`}>
            {m.chg >= 0 ? "+" : ""}{m.chg.toFixed(1)}%
          </span>
          <span className="mono dim2 hm-sector">{m.sector}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Calendar ────────────────────────────────────────────────────
function HomeCalendar() {
  const events = [
    { d: "May 29", e: "FOMC minutes · 14:00 ET",            tone: "amb", imp: "high" },
    { d: "May 30", e: "PCE · 08:30 ET",                     tone: "amb", imp: "high" },
    { d: "Jun 03", e: "ISM Manufacturing PMI",              tone: "ink", imp: "med" },
    { d: "Jun 05", e: "ECB rate decision",                  tone: "amb", imp: "high" },
    { d: "Jun 07", e: "NFP payrolls · 08:30 ET",            tone: "amb", imp: "high" },
    { d: "Jun 09", e: "ARCM · Q1 ER · BMO",                 tone: "copper", imp: "high" },
  ];
  return (
    <div className="cal-list">
      {events.map((ev, i) => (
        <div key={i} className={`cl-row cl-${ev.tone}`}>
          <span className="mono cl-when">{ev.d}</span>
          <span className="mono cl-evt">{ev.e}</span>
          <Pill tone={ev.imp === "high" ? "amb" : "ink"} small>{ev.imp}</Pill>
        </div>
      ))}
    </div>
  );
}

// ─── Book summary ────────────────────────────────────────────────
function HomeBook() {
  return (
    <div className="hb">
      <div className="hb-top">
        <div className="hb-cell">
          <div className="label-cap">NAV</div>
          <div className="mono hb-v">$108,420</div>
        </div>
        <div className="hb-cell">
          <div className="label-cap">Today</div>
          <div className="mono hb-v up">+$1,284 · +1.20%</div>
        </div>
        <div className="hb-cell">
          <div className="label-cap">Cash</div>
          <div className="mono hb-v">$90,628</div>
        </div>
      </div>
      <div className="hb-bar">
        <div className="hb-seg hb-cash" style={{ width: "83.6%" }} />
        <div className="hb-seg hb-pos1" style={{ width: "7.4%" }} title="BORA" />
        <div className="hb-seg hb-pos2" style={{ width: "5.6%" }} title="FLNX" />
        <div className="hb-seg hb-pos3" style={{ width: "3.4%" }} title="INPR" />
      </div>
      <div className="hb-legend mono dim2">
        Cash 83.6% · BORA 7.4% · FLNX 5.6% · INPR 3.4% · Sleep score <span className="up">A−</span>
      </div>
    </div>
  );
}

window.HomeView = HomeView;
