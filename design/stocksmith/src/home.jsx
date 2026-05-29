// home.jsx — landing/home view for the terminal
// Full-bleed market map + summary cards. Shown when no ticker is "drilled into".

const { useMemo: useMemoH } = React;

function HomeView({ onTicker, onSurface, mode, surface }) {
  return (
    <div className="home">
      {/* TIER 1 · MARKET STATE — regime + scan funnel + cross-asset tape */}
      <HomeHero mode={mode} onSurface={onSurface} />
      <IndexStrip />

      {/* TIER 2 · WHAT THE SYSTEM FOUND TODAY — opportunity surfaces */}
      <div className="home-sec-label"><span className="mono">OPPORTUNITY · TODAY'S SCAN</span><span className="mono dim2">612 ranked · regime-fit · edge-validated</span></div>
      <div className="home-grid-3">
        <HomeCard title="Top setups" sub="ranked by edge · R × Wilson LB" cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
          <TopSetups onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="◐ Discovery" sub="52w highs · squeezes · insider · UOA · emerging" cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
          <Discovery onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Top movers" sub="gainers · losers · in-scan universe">
          <TopMovers onTicker={onTicker} />
        </HomeCard>
      </div>

      {/* TIER 3 · ATTENTION — catalysts, news, what changed */}
      <div className="home-sec-label"><span className="mono">ATTENTION · CATALYSTS & FLOW</span><span className="mono dim2">next 24h · sentiment-scored</span></div>
      <div className="home-grid-3">
        <HomeCard title="Earnings today" sub="reporting · implied move · your exposure" cta="Calendar →" onCta={() => onSurface && onSurface("premarket")}>
          <EarningsToday onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Top stories" sub="market-moving · last 6h · sentiment-scored" cta="News →" onCta={() => onSurface && onSurface("news")}>
          <TopStories onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Overnight signals" sub="verdict flips · alerts · insider · ML" cta="View all →" onCta={() => onSurface && onSurface("alerts")}>
          <SignalFeed onTicker={onTicker} />
        </HomeCard>
      </div>
    </div>
  );
}

// ─── Hero strip ──────────────────────────────────────────────────
// ─── Index strip ─────────────────────────────────────────────────
function IndexStrip() {
  const idx = [
    { s: "S&P 500", v: "6,148.2", c: +0.42, tone: "gn" },
    { s: "NASDAQ",  v: "20,310",  c: +0.84, tone: "gn" },
    { s: "DOW",     v: "42,684",  c: +0.18, tone: "gn" },
    { s: "RUSSELL", v: "2,182",   c: -0.21, tone: "rd" },
    { s: "VIX",     v: "16.3",    c: -1.81, tone: "gn" },
    { s: "US 10Y",  v: "4.32%",   c: -0.46, tone: "gn" },
    { s: "DXY",     v: "103.4",   c: +0.10, tone: "ink" },
    { s: "BTC",     v: "71,240",  c: +2.14, tone: "gn" },
    { s: "WTI",     v: "$74.10",  c: -0.92, tone: "rd" },
    { s: "GOLD",    v: "2,418",   c: +0.34, tone: "gn" },
  ];
  return (
    <div className="ix-strip">
      {idx.map((i, k) => (
        <div key={k} className={`ix ix--${i.c >= 0 ? "gn" : i.tone === "ink" ? "ink" : "rd"}`}>
          <div className="ix-s mono">{i.s}</div>
          <div className="ix-v mono">{i.v}</div>
          <div className={`ix-c mono ${i.c >= 0 ? "up" : "dn"}`}>{i.c >= 0 ? "+" : ""}{i.c.toFixed(2)}%</div>
          <Spark sym={i.s} up={i.c >= 0} />
        </div>
      ))}
    </div>
  );
}

function Spark({ sym, up }) {
  const data = useMemoH(() => {
    const code = (sym.charCodeAt(0) || 65) + (sym.charCodeAt(2) || 65);
    const a = []; let v = 0;
    for (let i = 0; i < 18; i++) { v += (Math.sin(i * 0.6 + code) + (up ? 0.18 : -0.14)) * 0.5; a.push(v); }
    return a;
  }, [sym, up]);
  return <Sparkline data={data} color={`var(--${up ? "gn" : "rd"})`} w={56} h={18} />;
}

// ─── Top Stories / news ──────────────────────────────────────────
function TopStories({ onTicker }) {
  const stories = [
    { t: "12:48", sym: "NVDA", sent: +0.8, tone: "gn", src: "Reuters", head: "Chipmakers rally as data-center capex guidance lifts sector" },
    { t: "11:30", sym: null,   sent: +0.3, tone: "gn", src: "Bloomberg", head: "Fed minutes preview: market prices 88% hold, dot-plot in focus" },
    { t: "10:14", sym: "ARCM", sent: +0.7, tone: "gn", src: "Barron's", head: "Specialty materials names see insider buying cluster" },
    { t: "09:02", sym: "XOM",  sent: -0.4, tone: "rd", src: "WSJ", head: "Crude slips on demand worries; energy complex under pressure" },
    { t: "08:20", sym: "GENO", sent: +0.5, tone: "gn", src: "FierceBio", head: "Genoa Bio Phase-2 readout ahead of next-week print" },
  ];
  return (
    <div className="ts">
      {stories.map((s, i) => (
        <div key={i} className={`ts-row ts-${s.tone}`} onClick={() => s.sym && onTicker(s.sym)}>
          <div className="ts-top">
            <span className="ts-time mono dim2">{s.t}</span>
            <span className="ts-src mono dim2">{s.src}</span>
            {s.sym && <span className="ts-sym mono">{s.sym}</span>}
            <span className={`ts-sent mono ${s.sent >= 0 ? "up" : "dn"}`}>{s.sent >= 0 ? "+" : ""}{s.sent.toFixed(1)}</span>
          </div>
          <div className="ts-head">{s.head}</div>
        </div>
      ))}
    </div>
  );
}

// ─── Market Sentiment ────────────────────────────────────────────
function MarketSentiment() {
  const v = 62; // 0-100 fear→greed
  const tone = v >= 60 ? "gn" : v >= 45 ? "amb" : "rd";
  const label = v >= 75 ? "EXTREME GREED" : v >= 55 ? "GREED" : v >= 45 ? "NEUTRAL" : v >= 25 ? "FEAR" : "EXTREME FEAR";
  return (
    <div className="ms">
      <div className="ms-gauge">
        <svg viewBox="0 0 200 116" width="100%" height="116" style={{ overflow: "visible" }}>
          <defs>
            <linearGradient id="ms-arc" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--rd)" /><stop offset="50%" stopColor="var(--amb)" /><stop offset="100%" stopColor="var(--gn)" />
            </linearGradient>
          </defs>
          <path d="M 24 104 A 76 76 0 0 1 176 104" stroke="var(--line)" strokeWidth="13" fill="none" strokeLinecap="round" />
          <path d="M 24 104 A 76 76 0 0 1 176 104" stroke="url(#ms-arc)" strokeWidth="13" fill="none" strokeLinecap="round"
                style={{ filter: "drop-shadow(0 0 8px color-mix(in oklab, var(--gn) 35%, transparent))" }} />
          {(() => {
            const a = -180 + (v / 100) * 180;
            const tx = 100 + 66 * Math.cos(a * Math.PI / 180);
            const ty = 104 + 66 * Math.sin(a * Math.PI / 180);
            return <>
              <line x1="100" y1="104" x2={tx} y2={ty} stroke="var(--copper)" strokeWidth="3" strokeLinecap="round"
                    style={{ filter: "drop-shadow(0 0 8px var(--copper))" }} />
              <circle cx="100" cy="104" r="7" fill="var(--bg-1)" stroke="var(--copper)" strokeWidth="2.5" />
            </>;
          })()}
          <text x="100" y="92" textAnchor="middle" className="mono" fontSize="30" fontWeight="600" fill={`var(--${tone})`}>{v}</text>
        </svg>
        <div className={`ms-label mono kpi-tone--${tone}`}>{label}</div>
      </div>
      <div className="ms-rows">
        <MsRow label="News tone 24h" v="+0.42" tone="gn" pct={71} />
        <MsRow label="Social buzz" v="+0.31" tone="gn" pct={64} />
        <MsRow label="Put/Call ratio" v="0.78" tone="gn" pct={58} />
        <MsRow label="Breadth A/D" v="1.84" tone="gn" pct={66} />
        <MsRow label="VIX percentile" v="32%" tone="gn" pct={32} />
      </div>
    </div>
  );
}

function MsRow({ label, v, tone, pct }) {
  return (
    <div className="ms-row">
      <span className="mono dim2 ms-row-l">{label}</span>
      <div className="ms-bar"><div className={`ms-fill ms-fill--${tone}`} style={{ width: `${pct}%` }} /></div>
      <span className={`mono kpi-tone--${tone} ms-row-v`}>{v}</span>
    </div>
  );
}

// ─── Earnings Today ──────────────────────────────────────────────
function EarningsToday({ onTicker }) {
  const rows = [
    { sym: "CRWV", when: "BMO", time: "08:00", exp: "±9.2%", expo: "—",     esp: +5.1, tone: "amb", held: false },
    { sym: "GENO", when: "AMC", time: "16:05", exp: "±11.4%",expo: "WATCH", esp: +2.4, tone: "amb", held: false },
    { sym: "TURM", when: "AMC", time: "16:30", exp: "±6.8%", expo: "—",     esp: -1.2, tone: "rd",  held: false },
    { sym: "BORA", when: "AMC", time: "16:45", exp: "±5.1%", expo: "HELD",  esp: +3.8, tone: "gn",  held: true },
  ];
  return (
    <div className="et">
      <div className="et-hdr mono dim2">
        <span>4 reporting · </span><span className="warn">1 held (BORA)</span><span> · implied moves shown</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className={`et-row ${r.held ? "is-held" : ""}`} onClick={() => onTicker(r.sym)}>
          <span className="et-sym mono"><b>{r.sym}</b></span>
          <span className={`et-when mono ${r.when === "BMO" ? "cy" : "amb"}`}>{r.when}</span>
          <span className="et-time mono dim2">{r.time}</span>
          <span className="et-move mono warn">{r.exp}</span>
          <span className={`et-esp mono ${r.esp >= 0 ? "up" : "dn"}`}>ESP {r.esp >= 0 ? "+" : ""}{r.esp}%</span>
          {r.expo !== "—"
            ? <span className={`et-expo mono ${r.held ? "gn" : "amb"}`}>{r.expo}</span>
            : <span className="et-expo mono dim">—</span>}
        </div>
      ))}
    </div>
  );
}

// ─── Discovery ───────────────────────────────────────────────────
function Discovery({ onTicker }) {
  const groups = [
    { tag: "52W HIGH", tone: "gn",  items: [["ARGN","+3.1"],["NVRH","+2.4"],["DRSH","+2.9"]] },
    { tag: "SQUEEZE",  tone: "amb", items: [["MERC","8.1d"],["KARO","6.4d"],["FOLD","5.2d"]] },
    { tag: "INSIDER",  tone: "cy",  items: [["ARCM","+$0.5M"],["BORA","+$0.3M"],["INPR","+$0.2M"]] },
    { tag: "UOA",      tone: "violet", items: [["ARGN","70C×4"],["GENO","30C×3"],["DRSH","60C×2"]] },
    { tag: "EMERGING", tone: "copper", items: [["IPSO","new"],["SEND","new"],["AXLE","new"]] },
  ];
  return (
    <div className="disc">
      {groups.map((g, i) => (
        <div key={i} className="disc-grp">
          <div className={`disc-tag mono disc-tag--${g.tone}`}>{g.tag}</div>
          <div className="disc-items">
            {g.items.map(([sym, val], j) => (
              <button key={j} className="disc-chip" onClick={() => onTicker(sym)}>
                <span className="mono"><b>{sym}</b></span>
                <span className={`mono disc-val disc-val--${g.tone}`}>{val}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Top Movers (gainers / losers) ───────────────────────────────
function TopMovers({ onTicker }) {
  const all = useMemoH(() => HEATMAP.map(([sym, sector, mcap, chg]) => ({ sym, sector, chg }))
    .sort((a, b) => b.chg - a.chg), []);
  const gainers = all.slice(0, 6);
  const losers = all.slice(-6).reverse();
  const col = (items) => (
    <div className="tm-col">
      {items.map(m => (
        <button key={m.sym} className="tm-row" onClick={() => onTicker(m.sym)}>
          <span className="tm-sym mono"><b>{m.sym}</b></span>
          <span className="tm-sector mono dim2">{m.sector}</span>
          <span className={`tm-chg mono ${m.chg >= 0 ? "up" : "dn"}`}>{m.chg >= 0 ? "+" : ""}{m.chg.toFixed(1)}%</span>
          <span className="tm-bar"><i className={m.chg >= 0 ? "up" : "dn"} style={{ width: `${Math.min(100, Math.abs(m.chg) * 20)}%` }} /></span>
        </button>
      ))}
    </div>
  );
  return (
    <div className="tm">
      <div className="tm-head">
        <span className="mono gn">▲ GAINERS</span>
        <span className="mono rd">▼ LOSERS</span>
      </div>
      <div className="tm-2col">
        {col(gainers)}
        {col(losers)}
      </div>
    </div>
  );
}

// ─── Top Setups (merged Top BUY + best edge) ─────────────────────
function TopSetups({ onTicker }) {
  const rows = [
    { sym: "ARGN", name: "Argentum Robotics", score: 81, rr: "2.4", wlb: 54, edge: "+0.24", v: "BUY" },
    { sym: "ARCM", name: "Arclight Materials", score: 78, rr: "1.74",wlb: 48, edge: "+0.18", v: "BUY" },
    { sym: "DRSH", name: "Druseh Energy",      score: 66, rr: "1.6", wlb: 45, edge: "+0.14", v: "BUY" },
    { sym: "NVRH", name: "Novara Health",      score: 71, rr: "1.9", wlb: 46, edge: "+0.12", v: "BUY" },
    { sym: "ZOTR", name: "Zotran Industries",  score: 69, rr: "1.5", wlb: 44, edge: "+0.09", v: "WATCH" },
  ];
  return (
    <div className="tset">
      {rows.map((r, i) => (
        <button key={r.sym} className="tset-row" onClick={() => onTicker(r.sym)}>
          <span className="tset-rank mono dim">{String(i + 1).padStart(2, "0")}</span>
          <span className="tset-sym mono"><b>{r.sym}</b></span>
          <span className="tset-score mono" data-tone={r.score >= 75 ? "gn" : r.score >= 60 ? "amb" : "rd"}>{r.score}</span>
          <span className="tset-mid">
            <span className="tset-name dim">{r.name}</span>
            <span className="tset-stats mono dim2">R {r.rr} · W {r.wlb}% · edge {r.edge}</span>
          </span>
          <span className={`tset-v mono ${r.v === "BUY" ? "up" : "warn"}`}>{r.v}</span>
        </button>
      ))}
    </div>
  );
}

function HomeHero({ mode, onSurface }) {
  const go = (id) => () => onSurface && onSurface(id);
  return (
    <div className="home-hero">
      <div className="hh-eyebrow-row">
        <div className="hh-eyebrow mono">SwingTrade · 2026-05-28 · 14:23:08 ET · 612 ranked</div>
        <span className="hh-mood-live"><span className="hh-mood-pulse" />LIVE · MARKET MOOD</span>
      </div>

      <div className="hh-vitals">
        <div className="hh-vitals-counts">
          <button className="hv-stat hv-stat--copper" onClick={() => { window.__scanFilter = "ALL"; go("signal-scanner")(); }} title="Open Signal Scanner · all">
            <div className="hv-stat-l mono">RANKED</div>
            <div className="hv-stat-v mono">612</div>
            <div className="hv-stat-s mono dim2">universe →</div>
          </button>
          <button className="hv-stat hv-stat--gn" onClick={() => { window.__scanFilter = "BUY"; go("signal-scanner")(); }} title="Scanner · BUY">
            <div className="hv-stat-l mono">BUY</div>
            <div className="hv-stat-v mono">14</div>
            <div className="hv-stat-s mono dim2">+2 vs last bundle →</div>
          </button>
          <button className="hv-stat hv-stat--amb" onClick={() => { window.__scanFilter = "WATCH"; go("signal-scanner")(); }} title="Scanner · WATCH">
            <div className="hv-stat-l mono">WATCH-CLOSE</div>
            <div className="hv-stat-v mono">8</div>
            <div className="hv-stat-s mono dim2">edge near gate →</div>
          </button>
          <button className="hv-stat hv-stat--rd" onClick={() => { window.__scanFilter = "SHORT"; go("signal-scanner")(); }} title="Scanner · AVOID">
            <div className="hv-stat-l mono">AVOID</div>
            <div className="hv-stat-v mono">31</div>
            <div className="hv-stat-s mono dim2">setups failing →</div>
          </button>
        </div>

        <div className="hh-vitals-mood">
          <div className="hv-regime hv-regime--gn">
            <div className="hv-regime-l mono">REGIME · TAPE</div>
            <div className="hv-regime-v mono" style={{ display: "block", whiteSpace: "nowrap", fontSize: 20, fontWeight: 500, letterSpacing: "0.04em" }}>
              <span className="hv-regime-on" style={{ whiteSpace: "nowrap" }}>RISK&nbsp;ON</span>
              <span className="hv-regime-dot" style={{ margin: "0 8px" }}>·</span>
              <span className="hv-regime-tape" style={{ whiteSpace: "nowrap" }}>CHOPPY</span>
            </div>
            <div className="hv-regime-s mono dim2">multi-factor regime · 71% historical WR</div>
          </div>

          <div className="hv-mood-grid">
            <MoodTile label="FEAR/GREED" value="62" tone="gn"  delta="greed" />
            <MoodTile label="BREADTH" value="56%"   tone="gn"  delta="A/D 1.84" />
            <MoodTile label="PUT/CALL" value="0.78" tone="gn"  delta="bullish" />
            <MoodTile label="VIX %ILE" value="32%"  tone="gn"  delta="1y · low" />
            <MoodTile label="NEWS TONE" value="+0.42" tone="gn" delta="24h" />
            <MoodTile label="HY OAS"   value="342bp" tone="amb" delta="stable" />
          </div>
        </div>
      </div>

      <div className="hh-line mono dim2">
        Bundle generated <b>02:14:08 ET</b> · sleeves: Continuation BO · VCP · Earnings drift · Mean revert.
        Click any tile or row to enter the 14-lens detail.
      </div>
    </div>
  );
}

function MoodTile({ label, value, tone, delta }) {
  return (
    <div className={`hv-mood-tile hv-mood-tile--${tone}`}>
      <div className="hv-mt-l mono">{label}</div>
      <div className={`hv-mt-v mono kpi-tone--${tone}`}>{value}</div>
      <div className="hv-mt-s mono dim2">{delta}</div>
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
function HomeCard({ title, sub, cta, onCta, children }) {
  return (
    <div className="hc">
      <div className="hc-hdr">
        <div>
          <div className="hc-title mono">{title}</div>
          {sub && <div className="hc-sub mono dim">{sub}</div>}
        </div>
        {cta && <button className="hc-cta mono" onClick={onCta}>{cta}</button>}
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

// ─── Performance strip ───────────────────────────────────────────
function HomePerformanceStrip() {
  return (
    <div className="hp-strip">
      <div className="hp-curve">
        <div className="hp-curve-hdr">
          <div className="label-cap">Equity curve · 30d</div>
          <span className="mono dim2">vs SPY benchmark</span>
        </div>
        <HpEquityChart />
        <div className="hp-curve-foot mono">
          <span><b className="up">+$1,284</b> today</span>
          <span className="dim2">·</span>
          <span><span className="label-cap">Sharpe</span> <b>1.84</b></span>
          <span className="dim2">·</span>
          <span><span className="label-cap">Max DD</span> <b className="dn">−2.1%</b></span>
        </div>
      </div>
      <div className="hp-stats">
        <HpStat label="TODAY"   value="+$1,284" delta="+1.20%" tone="gn" />
        <HpStat label="WTD"     value="+$2,840" delta="+2.68%" tone="gn" />
        <HpStat label="MTD"     value="+$4,210" delta="+4.04%" tone="gn" />
        <HpStat label="YTD"     value="+$11,860"delta="+12.27%"tone="gn" sub="vs SPY +9.42%" />
        <HpStat label="α YTD"   value="+2.85%"  delta="net of fees" tone="copper" />
        <HpStat label="VOL"     value="14.2%"   delta="annualized"  tone="ink" />
      </div>
    </div>
  );
}

function HpStat({ label, value, delta, tone, sub }) {
  return (
    <div className={`hp-stat hp-stat--${tone}`}>
      <div className="hp-stat-l mono">{label}</div>
      <div className={`hp-stat-v mono kpi-tone--${tone}`}>{value}</div>
      <div className="hp-stat-s mono dim2">{delta}{sub ? ` · ${sub}` : ""}</div>
    </div>
  );
}

function HpEquityChart() {
  const w = 460, h = 110, padT = 8, padB = 16, padL = 8, padR = 8;
  const data = [];
  const spy = [];
  let v = 0, s = 0;
  for (let i = 0; i < 30; i++) {
    v += 0.4 + (Math.sin(i * 0.4) + Math.cos(i * 0.7)) * 0.4 + (Math.random() - 0.42) * 0.5;
    s += 0.18 + (Math.random() - 0.5) * 0.5;
    data.push(v); spy.push(s);
  }
  const min = Math.min(...data, ...spy, -1);
  const max = Math.max(...data, ...spy, 14);
  const x = i => padL + (i / (data.length - 1)) * (w - padL - padR);
  const y = vv => padT + (1 - (vv - min) / (max - min)) * (h - padT - padB);
  const pts = data.map((vv, i) => [x(i), y(vv)]);
  const spyPts = spy.map((vv, i) => [x(i), y(vv)]);
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="hp-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gn)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--gn)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1={padL} y1={y(0)} x2={w - padR} y2={y(0)} stroke="var(--glass-line)" strokeDasharray="2 3" />
      <path d={`M ${padL} ${y(0)} L ${pts.map(p => p.join(",")).join(" L ")} L ${w - padR} ${y(0)} Z`} fill="url(#hp-fill)" />
      <polyline points={spyPts.map(p => p.join(",")).join(" ")} stroke="var(--ink-3)" strokeWidth="1.2" fill="none" />
      <polyline points={pts.map(p => p.join(",")).join(" ")} stroke="var(--gn)" strokeWidth="1.8" fill="none"
                style={{ filter: "drop-shadow(0 0 5px var(--gn))" }} />
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="3.5" fill="var(--gn)"
              style={{ filter: "drop-shadow(0 0 7px var(--gn))" }} />
    </svg>
  );
}

// ─── Active Positions strip ──────────────────────────────────────
function ActivePositionsStrip({ onTicker }) {
  const positions = [
    { sym: "BORA", name: "Bora Industries",   qty: 240, entry: 28.40, last: 31.10, openR: "+1.30R", pl: "+$648",  dist: "+9.5%", days: 8,  tone: "gn" },
    { sym: "FLNX", name: "Felinex Tech",      qty: 60,  entry: 162.00, last: 168.40, openR: "+0.71R", pl: "+$384", dist: "+3.9%", days: 12, tone: "gn" },
    { sym: "INPR", name: "Inpera Capital",    qty: 180, entry: 41.20, last: 39.80, openR: "−0.42R", pl: "−$252", dist: "−3.4%", days: 4,  tone: "rd" },
  ];
  return (
    <div className="ap-strip">
      {positions.map(p => (
        <button key={p.sym} className={`ap-card ap-card--${p.tone}`} onClick={() => onTicker(p.sym)}>
          <div className="ap-hdr">
            <span className="mono ap-sym"><b>{p.sym}</b></span>
            <span className={`mono ap-pl kpi-tone--${p.tone}`}>{p.pl}</span>
          </div>
          <div className="ap-meta mono dim2">{p.name} · {p.qty} sh · held {p.days}d</div>
          <div className="ap-bars">
            <div className="ap-bar">
              <div className="ap-bar-l label-cap">Open R</div>
              <div className={`ap-bar-v mono kpi-tone--${p.tone}`}>{p.openR}</div>
            </div>
            <div className="ap-bar">
              <div className="ap-bar-l label-cap">Stop dist</div>
              <div className={`ap-bar-v mono ${p.dist.startsWith("+") ? "up" : "dn"}`}>{p.dist}</div>
            </div>
            <div className="ap-bar">
              <div className="ap-bar-l label-cap">Entry</div>
              <div className="ap-bar-v mono">${p.entry.toFixed(2)}</div>
            </div>
            <div className="ap-bar">
              <div className="ap-bar-l label-cap">Last</div>
              <div className="ap-bar-v mono">${p.last.toFixed(2)}</div>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

// ─── Today's Signal Feed ─────────────────────────────────────────
function SignalFeed({ onTicker }) {
  const events = [
    { t: "06:14", tone: "gn",  tag: "BUY",    sym: "ARGN", text: "Verdict flipped from WATCH → BUY · score 71 → 81" },
    { t: "05:48", tone: "gn",  tag: "ALERT",  sym: "ARCM", text: "Pivot break: close > $66.40 on +1.6× RVOL" },
    { t: "04:22", tone: "amb", tag: "ER",     sym: "GENO", text: "ER in 9 sessions · WATCH-CLOSE · trim size" },
    { t: "03:41", tone: "rd",  tag: "AVOID",  sym: "BIVO", text: "Distribution signature · cut to KILLED" },
    { t: "02:14", tone: "ink", tag: "BUNDLE", sym: null,   text: "Daily bundle generated · 612 ranked · 14 BUY · 8 WATCH · 31 AVOID" },
    { t: "23:49", tone: "violet", tag: "AI",   sym: "DRSH", text: "AI hit-net edge +0.18 → +0.22 · drift KS 0.08" },
    { t: "22:12", tone: "cy",  tag: "INSIDER",sym: "ARCM", text: "Form 4 filed · CFO buy 5,000 sh @ $64.20" },
  ];
  return (
    <div className="sf">
      {events.map((e, i) => (
        <div key={i} className={`sf-row sf-${e.tone}`} onClick={() => e.sym && onTicker(e.sym)}>
          <span className="sf-time mono dim2">{e.t}</span>
          <span className={`sf-tag mono sf-tag--${e.tone}`}>{e.tag}</span>
          {e.sym && <span className="sf-sym mono"><b>{e.sym}</b></span>}
          <span className="sf-text mono">{e.text}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Today's Tasks ────────────────────────────────────────────────
function TodaysTasks() {
  const tasks = [
    { done: true,  tag: "PRE-MARKET", text: "Review overnight signals + pre-market gappers", time: "07:00" },
    { done: true,  tag: "RISK",        text: "Confirm OCO brackets on BORA, FLNX, INPR", time: "08:15" },
    { done: false, tag: "BRACKET",     text: "Send BUY-STOP $66.18 ARCM · 110 sh · OCO", time: "now",   tone: "copper" },
    { done: false, tag: "TRIM",        text: "Trim 25% GENO before ER window (T−2 = May 30)", time: "EOD" },
    { done: false, tag: "JOURNAL",     text: "Write 1-paragraph thesis for ARCM entry", time: "after fill" },
    { done: false, tag: "RESEARCH",    text: "Read FOMC minutes (Wed 14:00) · score regime impact", time: "Wed" },
    { done: false, tag: "ALERT",       text: "Wire alert: XLB < 50-DMA on +1.5σ volume", time: "EOD" },
  ];
  return (
    <div className="tt">
      {tasks.map((t, i) => (
        <div key={i} className={`tt-row ${t.done ? "is-done" : ""} ${t.tone ? `tt-${t.tone}` : ""}`}>
          <span className="tt-check">{t.done ? "✓" : ""}</span>
          <span className={`tt-tag mono`}>{t.tag}</span>
          <span className="tt-text">{t.text}</span>
          <span className="tt-time mono dim2">{t.time}</span>
        </div>
      ))}
      <div className="tt-foot mono dim2">2 of 7 done · 5 pending · 1 priority (copper)</div>
    </div>
  );
}
