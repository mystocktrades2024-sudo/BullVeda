// home.jsx — landing/home view for the terminal
// Full-bleed market map + summary cards. Shown when no ticker is "drilled into".

const { useMemo: useMemoH } = React;

function HomeView({ onTicker, onSurface, mode, surface }) {
  return (
    <div className="home">
      {/* TIER 1 · MARKET STATE — regime + scan funnel + cross-asset tape */}
      <HomeHero mode={mode} onSurface={onSurface} />
      <IndexStrip />

      {/* TIER 1.5 · MARKET CONTEXT — the daily top-down briefing (regime · pre-market · calendar) */}
      <div className="home-sec-label"><span className="mono">MARKET CONTEXT · BEFORE YOU TRADE</span><span className="mono dim2">top-down read · regime gates your size · click any card to go deeper</span></div>
      <MarketBriefing onSurface={onSurface} onTicker={onTicker} />

      {/* TIER 1.7 · MARKETS · NEWS — news-forward board (featured · latest · trending/gainers rail) */}
      <div className="home-sec-label"><span className="mono">MARKETS · NEWS</span><span className="mono dim2">the tape in words · trending names · today's movers</span></div>
      <NewsMarketsBoard onTicker={onTicker} onSurface={onSurface} />

      {/* TIER 2 · WHAT THE SYSTEM FOUND TODAY — opportunity surfaces */}
      <div className="home-sec-label"><span className="mono">OPPORTUNITY · TODAY'S SCAN</span><span className="mono dim2">612 ranked · regime-fit · edge-validated</span></div>
      <div className="home-grid-3">
        <HomeCard title="Top setups" sub="top 5 of 612 universe · ranked by edge (R × Wilson LB)" cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
          <TopSetups onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="◐ Discovery" sub="52w highs · squeezes · insider · UOA · emerging" cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
          <Discovery onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Top movers" sub="gainers · losers · in-scan universe">
          <TopMovers onTicker={onTicker} />
        </HomeCard>
      </div>

      {/* TIER 2.5 · BEST IDEAS PER ENGINE — top 5 from each discovery source */}
      <div className="home-sec-label"><span className="mono">BEST IDEAS · TOP 5 PER ENGINE</span><span className="mono dim2">each discovery model's highest-conviction names today</span></div>
      <TopByEngine onTicker={onTicker} onSurface={onSurface} />

      {/* TIER 3 · ATTENTION — catalysts, news, what changed */}
      <div className="home-sec-label"><span className="mono">ATTENTION · CATALYSTS & FLOW</span><span className="mono dim2">next 24h · sentiment-scored</span></div>
      <div className="home-grid-3">
        <HomeCard title="Earnings today" sub="reporting · implied move · your exposure" cta="Calendar →" onCta={() => onSurface && onSurface("premarket")}>
          <EarningsToday onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Top stories" sub="market-moving · last 6h · sentiment-scored" cta="News →" onCta={() => onSurface && onSurface("news")}>
          <TopStories onTicker={onTicker} />
        </HomeCard>
        <HomeCard title="Overnight signals" sub="bias shifts · alerts · insider · ML" cta="View all →" onCta={() => onSurface && onSurface("alerts")}>
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
    { s: "US 2Y",   v: "4.71%",   c: -0.30, tone: "gn" },
    { s: "DXY",     v: "103.4",   c: +0.10, tone: "ink" },
    { s: "BTCUSD",  v: "71,240",  c: +2.14, tone: "gn" },
    { s: "ETHUSD",  v: "3,842",   c: +1.63, tone: "gn" },
    { s: "WTI",     v: "$74.10",  c: -0.92, tone: "rd" },
    { s: "GOLD",    v: "2,418",   c: +0.34, tone: "gn" },
    { s: "COPPER",  v: "$4.58",   c: +0.71, tone: "gn" },
  ];
  return (
    <div className="ix-strip">
      {idx.map((i, k) => (
        <div key={k} className={`ix ix--${i.c >= 0 ? "gn" : i.tone === "ink" ? "ink" : "rd"}`}>
          <span className="ix-s mono">{i.s}</span>
          <span className="ix-v mono">{i.v}</span>
          <span className={`ix-c mono ${i.c >= 0 ? "up" : "dn"}`}>{i.c >= 0 ? "+" : ""}{i.c.toFixed(2)}%</span>
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
  return <Sparkline data={data} color={`var(--${up ? "gn" : "rd"})`} w={48} h={20} />;
}

// ─── Market Context briefing — 3 condensed top-down cards ──────────
function MarketBriefing({ onSurface, onTicker }) {
  const go = (id) => onSurface && onSurface(id);
  // breadth / regime internals (mock — wire to internals engine)
  const breadth = [
    { k: ">50-DMA", v: "62%", tone: "gn" },
    { k: ">200-DMA", v: "58%", tone: "gn" },
    { k: "A/D line", v: "+1,240", tone: "gn" },
    { k: "New H–L", v: "+86", tone: "gn" },
    { k: "VIX", v: "16.3", tone: "gn" },
    { k: "Put/Call", v: "0.82", tone: "amb" },
  ];
  const gappers = [
    { sym: "NVDA", pct: +4.2, why: "capex guide", held: false },
    { sym: "ARGN", pct: +2.1, why: "sector flows", held: true },
    { sym: "XOM", pct: -2.6, why: "crude −2%", held: false },
    { sym: "GENO", pct: -3.8, why: "offering", held: false },
  ];
  const events = [
    { d: "Tue", t: "CPI · MoM", imp: "high", note: "08:30 · core in focus" },
    { d: "Wed", t: "FOMC minutes", imp: "high", note: "14:00 · dot-plot" },
    { d: "Thu", t: "ARGN earnings", imp: "med", note: "AMC · ±6.4% implied", held: true },
    { d: "Fri", t: "PCE · NFP", imp: "med", note: "08:30" },
  ];
  return (
    <div className="home-grid-3 mbf">
      {/* REGIME */}
      <div className="mbf-card" onClick={() => go("internals")}>
        <div className="mbf-hd">
          <span className="mbf-tag mono">REGIME</span>
          <span className="mbf-go mono">Internals →</span>
        </div>
        <div className="mbf-regime">
          <span className="mbf-regime-v mono"><b className="up">RISK-ON</b> · <b className="warn">CHOPPY</b></span>
          <span className="mbf-regime-cap mono dim2">~70% size · BUY floor 72</span>
        </div>
        <div className="mbf-breadth">
          {breadth.map((b, i) => (
            <div key={i} className="mbf-br">
              <span className="mbf-br-k mono dim2">{b.k}</span>
              <span className={`mbf-br-v mono ${b.tone === "gn" ? "up" : b.tone === "rd" ? "dn" : "warn"}`}>{b.v}</span>
            </div>
          ))}
        </div>
        <div className="mbf-foot mono dim2">Breadth healthy but tape choppy — CPI 08:30 is the risk. Trim to ~70% size until it resolves.</div>
      </div>

      {/* PRE-MARKET */}
      <div className="mbf-card" onClick={() => go("premarket")}>
        <div className="mbf-hd">
          <span className="mbf-tag mono">PRE-MARKET</span>
          <span className="mbf-go mono">Gap board →</span>
        </div>
        <div className="mbf-sub mono dim2">ES +0.3% · NQ +0.5% · 4:42 ET · top gaps</div>
        <div className="mbf-gaps">
          {gappers.map((g, i) => (
            <button key={i} className="mbf-gap" onClick={(e) => { e.stopPropagation(); onTicker && onTicker(g.sym); }}>
              <span className="mbf-gap-sym mono">{g.sym}{g.held && <span className="mbf-held mono">HELD</span>}</span>
              <span className={`mbf-gap-pct mono ${g.pct >= 0 ? "up" : "dn"}`}>{g.pct >= 0 ? "+" : ""}{g.pct.toFixed(1)}%</span>
              <span className="mbf-gap-why mono dim2">{g.why}</span>
            </button>
          ))}
        </div>
        <div className="mbf-foot mono dim2"><b className="copper">ARGN</b> in your book gapping +2.1% on sector flows.</div>
      </div>

      {/* CALENDAR */}
      <div className="mbf-card" onClick={() => go("macro-cal")}>
        <div className="mbf-hd">
          <span className="mbf-tag mono">THIS WEEK</span>
          <span className="mbf-go mono">Calendar →</span>
        </div>
        <div className="mbf-sub mono dim2">macro prints + your earnings · event risk</div>
        <div className="mbf-events">
          {events.map((e, i) => (
            <div key={i} className={`mbf-evt mbf-evt--${e.imp}`}>
              <span className="mbf-evt-d mono">{e.d}</span>
              <span className="mbf-evt-t mono">{e.t}{e.held && <span className="mbf-held mono">HELD</span>}</span>
              <span className="mbf-evt-n mono dim2">{e.note}</span>
            </div>
          ))}
        </div>
        <div className="mbf-foot mono dim2">CPI Tue + FOMC Wed are regime risks — size into them carefully.</div>
      </div>
    </div>
  );
}

// ─── Top Stories / news ──────────────────────────────────────────
function TopStories({ onTicker }) {
  const stories = [
    { t: "12:48", sym: "NVDA", sent: +0.8, tone: "gn", src: "Reuters", head: "Chipmakers rally as data-center capex guidance lifts sector",
      sum: "Three hyperscalers lifted FY capex guides on the same morning — direct read-through to GPU and networking suppliers. Group +2.8% on 1.6× volume.",
      impact: "Sector tailwind", affects: ["NVDA", "AVGO", "ARM"] },
    { t: "11:30", sym: null, sent: +0.3, tone: "gn", src: "Bloomberg", head: "Fed minutes preview: market prices 88% hold, dot-plot in focus",
      sum: "Minutes land 14:00 ET. A hold is fully priced; the swing factors are the dot-plot path and any balance-sheet language — both move duration and risk appetite.",
      impact: "Macro · rates", affects: ["SPY", "TLT"] },
    { t: "10:14", sym: "ARCM", sent: +0.7, tone: "gn", src: "Barron's", head: "Specialty-materials names see insider buying cluster",
      sum: "Form 4s show CFO + COO open-market buys across the group over five sessions. Historically a positive 3-month signal in this sleeve (Wilson LB 61%).",
      impact: "Stock-specific", affects: ["ARCM"] },
    { t: "09:02", sym: "XOM", sent: -0.4, tone: "rd", src: "WSJ", head: "Crude slips on demand worries; energy complex under pressure",
      sum: "Brent −2.1% on soft China PMI; majors and oil-services lower pre-bell. XLE testing its 50-DMA — a break opens rotation out of energy.",
      impact: "Sector risk", affects: ["XOM", "CVX", "XLE"] },
    { t: "08:20", sym: "GENO", sent: +0.5, tone: "gn", src: "FierceBio", head: "Genoa Bio Phase-2 readout expected ahead of next-week print",
      sum: "Topline due before earnings; options imply a ±18% event move. Binary catalyst — size for the gap, not the drift.",
      impact: "Binary catalyst", affects: ["GENO"] },
  ];
  const impactTone = { "Sector tailwind": "gn", "Stock-specific": "gn", "Macro · rates": "amb", "Binary catalyst": "amb", "Sector risk": "rd" };
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
          <div className="ts-sum">{s.sum}</div>
          <div className="ts-foot">
            <span className={`ts-impact mono kpi-tone--${impactTone[s.impact] || "amb"}`}>{s.impact}</span>
            <span className="ts-affects mono dim2">affects</span>
            {s.affects.map(tk => (
              <button key={tk} className="ts-tk mono" onClick={(e) => { e.stopPropagation(); onTicker(tk); }}>{tk}</button>
            ))}
          </div>
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

// ─── Top 5 per discovery engine ──────────────────────────────────
const TBE_ENGINES = [
  { id: "momentum", title: "Momentum", metric: "RS", surface: "momentum", accent: "#d97757",
    rows: [["NVRH", "98"], ["ARGN", "96"], ["KARO", "94"], ["FLNX", "91"], ["NEXO", "89"]] },
  { id: "earnings-ai", title: "Earnings AI", metric: "beat", surface: "earnings-ai", accent: "var(--amb)",
    rows: [["GENO", "82%"], ["DRSH", "78%"], ["INPR", "74%"], ["ZOTR", "71%"], ["MERC", "68%"]] },
  { id: "ml", title: "ML Predictions", metric: "P(up)", surface: "ai-predict", ml: true, accent: "var(--cy, #5bc0c9)",
    rows: [["ARGN", "65%"], ["ARCM", "61%"], ["KARO", "59%"], ["NVRH", "57%"], ["FLNX", "55%"]] },
  { id: "options", title: "Options Flow", metric: "R:R", surface: "options", accent: "var(--violet, #9a86c4)",
    rows: [["MERC", "5.1"], ["GENO", "2.8"], ["ARGN", "3.1"], ["DRSH", "2.5"], ["VLCT", "2.2"]] },
  { id: "insider", title: "Insider", metric: "conv", surface: "insider", accent: "var(--gn)",
    rows: [["ARGN", "92"], ["KOPL", "84"], ["INPR", "79"], ["BORA", "73"], ["HAVN", "68"]] },
  { id: "smc", title: "SMC / Patterns", metric: "conf", surface: "smc-patterns", accent: "var(--blue, #5b9bd5)",
    rows: [["ARGN", "A"], ["NVRH", "A-"], ["KARO", "B+"], ["ARCM", "B"], ["NEXO", "B"]] },
];

// Scanner's flagged names (mirrors TopSetups below) — part of the consensus universe.
const SCANNER_PICKS = [
  { sym: "ARGN", name: "Argentum Robotics", score: 81, rr: "2.4", wlb: 54, edge: "+0.24", v: "BUY" },
  { sym: "ARCM", name: "Arclight Materials", score: 78, rr: "1.74",wlb: 48, edge: "+0.18", v: "BUY" },
  { sym: "DRSH", name: "Druseh Energy",      score: 66, rr: "1.6", wlb: 45, edge: "+0.14", v: "BUY" },
  { sym: "NVRH", name: "Novara Health",      score: 71, rr: "1.9", wlb: 46, edge: "+0.12", v: "BUY" },
  { sym: "ZOTR", name: "Zotran Industries",  score: 69, rr: "1.5", wlb: 44, edge: "+0.09", v: "WATCH" },
];

// Resolve engines with live ML when the AIPredict ensemble is available.
function resolveEngines() {
  return TBE_ENGINES.map(e => {
    if (e.ml && window.AIPredict && window.AIPredict.all) {
      const top = window.AIPredict.all().slice(0, 5).map(p => [p.sym, Math.round((p.pUp || 0.5) * 100) + "%"]);
      if (top.length === 5) return { ...e, rows: top };
    }
    return e;
  });
}

// Expose the discovery universe so the Consensus panel stays in sync.
window.TBE_ENGINES = TBE_ENGINES;
window.SCANNER_PICKS = SCANNER_PICKS;
window.resolveEngines = resolveEngines;
function TopByEngine({ onTicker, onSurface }) {
  // ML pulls live from the AIPredict ensemble when available
  const engines = useMemoH(() => resolveEngines(), []);
  return (
    <div className="tbe-grid">
      {engines.map(e => (
        <div key={e.id} className="tbe-card" style={{ "--eng": e.accent }}>
          <button className="tbe-head" onClick={() => onSurface && onSurface(e.surface)}>
            <span className="tbe-title mono"><span className="tbe-dot" />{e.title}</span>
            <span className="tbe-metric mono dim2">{e.metric} <span className="tbe-arrow">→</span></span>
          </button>
          <div className="tbe-list">
            {e.rows.map(([sym, v], i) => (
              <button key={sym} className={`tbe-row ${i === 0 ? "is-lead" : ""}`} onClick={() => onTicker && onTicker(sym)}>
                <span className="tbe-rank mono">{i + 1}</span>
                <span className="tbe-sym mono"><b>{sym}</b></span>
                <span className="tbe-v mono">{v}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Top Setups (merged Top BUY + best edge) ─────────────────────
function TopSetups({ onTicker }) {
  const rows = SCANNER_PICKS;
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
          <span className={`tset-v mono ${r.v === "BUY" ? "up" : "warn"}`}>{secBias(r.v)}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Markets · News board — featured + latest feed + trending/gainers rail ──
function NewsMarketsBoard({ onTicker, onSurface }) {
  const featured = {
    head: "Chipmakers extend rally as hyperscaler capex guides lift the group",
    src: "Reuters", time: "12m", live: true, tickers: [["NVDA", +6.26], ["AVGO", +3.1], ["ARM", +2.4]],
    sum: "Three hyperscalers raised FY capex on the same morning — a direct read-through to GPU and networking suppliers. Group +2.8% on 1.6× volume.",
  };
  const leftStack = [
    { head: "Fed minutes preview: market prices 88% hold, dot-plot in focus", src: "Bloomberg", time: "1h", tickers: [["SPY", +0.4]] },
    { head: "Specialty-materials names see insider buying cluster", src: "Barron's", time: "2h", tickers: [["ARGN", +2.1]] },
    { head: "Crude slips on demand worries; energy complex under pressure", src: "WSJ", time: "3h", tickers: [["XOM", -2.6], ["XLE", -1.8]] },
    { head: "Alphabet plans to raise capex for AI; Street models 2027 payback", src: "Yahoo Finance", time: "5h", tickers: [["GOOGL", -1.0]] },
  ];
  const latest = [
    { head: "Genoa Bio Phase-2 readout expected ahead of next-week print", src: "FierceBio", time: "16m", tickers: [["GENO", +0.5]] },
    { head: "Gold edges higher as traders weigh rate-path confusion", src: "Bloomberg", time: "36m", tickers: [["GLD", +0.7]] },
    { head: "BOJ should signal a clear rate path after June hike, says SMFG chief", src: "Reuters", time: "1h", tickers: [["JPY", +0.1]] },
    { head: "Lithium names rebound on supply-cut headlines out of Chile", src: "Reuters", time: "1h", tickers: [["LAC", +5.8]] },
    { head: "Software multiples compress as Street trims FY estimates", src: "Bloomberg", time: "2h", tickers: [["MDB", +20.4], ["TWLO", +19.4]] },
    { head: "Retail sales beat lifts consumer-discretionary breadth", src: "Reuters", time: "3h", tickers: [["XLY", +1.2]] },
  ];
  const trending = [
    { sym: "NVDA", name: "NVIDIA Corp", px: "884.20", chg: +7.04, up: true },
    { sym: "BTC", name: "Bitcoin USD", px: "69,969", chg: -3.76, up: false },
    { sym: "ARGN", name: "Argentum Robotics", px: "213.40", chg: +3.10, up: true },
    { sym: "LAC", name: "Lithium Americas", px: "5.51", chg: +5.76, up: true },
    { sym: "ABVX", name: "ABIVAX SA", px: "129.69", chg: -2.22, up: false },
  ];
  const gainers = [
    { sym: "FLNC", name: "Fluence Energy", px: "27.15", chg: +43.8 },
    { sym: "MDB", name: "MongoDB Inc", px: "403.88", chg: +20.4 },
    { sym: "TWLO", name: "Twilio Inc", px: "227.54", chg: +19.4 },
    { sym: "GENO", name: "Genoa Bio", px: "29.40", chg: +12.1 },
  ];
  const Story = ({ s, big }) => (
    <button className={`nm-story ${big ? "nm-story--big" : ""}`} onClick={() => s.tickers[0] && onTicker(s.tickers[0][0])}>
      {big && <div className="nm-feat-img"><span className="mono">◧ MARKETS</span></div>}
      <div className="nm-head">{s.head}</div>
      <div className="nm-meta mono">
        {s.live && <span className="nm-live">● LIVE</span>}
        <span className="nm-src">{s.src}</span><span className="dim2"> · {s.time} ago</span>
      </div>
      {big && s.sum && <div className="nm-sum">{s.sum}</div>}
      <div className="nm-chips">
        {s.tickers.map(([t, c], i) => (
          <span key={i} className="nm-chip mono" onClick={(e) => { e.stopPropagation(); onTicker(t); }}>{t} <b className={c >= 0 ? "up" : "dn"}>{c >= 0 ? "+" : ""}{c.toFixed(2)}%</b></span>
        ))}
      </div>
    </button>
  );
  return (
    <div className="nm-board">
      <div className="nm-col nm-col--feat">
        <Story s={featured} big />
        <div className="nm-stack">{leftStack.map((s, i) => <Story key={i} s={s} />)}</div>
        <button className="nm-more mono" onClick={() => onSurface && onSurface("news")}>View all news →</button>
      </div>
      <div className="nm-col nm-col--latest">
        <div className="nm-col-h mono">LATEST</div>
        <div className="nm-feed">{latest.map((s, i) => <Story key={i} s={s} />)}</div>
      </div>
      <div className="nm-col nm-col--rail">
        <div className="nm-lookup" onClick={() => onSurface && onSurface("signal-scanner")}><span className="mono dim2">⌕ Quote lookup</span></div>
        <div className="nm-rail-card">
          <div className="nm-rail-h mono"><span>TRENDING TICKERS</span><span className="nm-rail-go" onClick={() => onSurface && onSurface("signal-scanner")}>Scanner →</span></div>
          {trending.map((r, i) => (
            <button key={i} className="nm-row" onClick={() => onTicker(r.sym)}>
              <span className="nm-row-l"><b className="nm-row-sym mono">{r.sym}</b><span className="nm-row-name dim2">{r.name}</span></span>
              <Sparkline data={useMemoH(() => { const a = []; let v = 0; for (let j = 0; j < 16; j++) { v += (Math.sin(j * .7 + r.sym.charCodeAt(0)) + (r.up ? .2 : -.18)) * .5; a.push(v); } return a; }, [r.sym])} color={`var(--${r.up ? "gn" : "rd"})`} w={52} h={20} />
              <span className="nm-row-r"><span className="nm-row-px mono">{r.px}</span><span className={`nm-row-chg mono ${r.chg >= 0 ? "up" : "dn"}`}>{r.chg >= 0 ? "+" : ""}{r.chg.toFixed(2)}%</span></span>
            </button>
          ))}
        </div>
        <div className="nm-rail-card">
          <div className="nm-rail-h mono"><span>TOP GAINERS</span><span className="nm-rail-go" onClick={() => onSurface && onSurface("momentum")}>Movers →</span></div>
          {gainers.map((r, i) => (
            <button key={i} className="nm-row nm-row--g" onClick={() => onTicker(r.sym)}>
              <span className="nm-row-l"><b className="nm-row-sym mono">{r.sym}</b><span className="nm-row-name dim2">{r.name}</span></span>
              <span className="nm-row-r"><span className="nm-row-px mono">{r.px}</span><span className="nm-row-chg mono up">+{r.chg.toFixed(1)}%</span></span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function HomeHero({ mode, onSurface }) {
  const go = (id) => () => onSurface && onSurface(id);
  const scan = (f) => () => { window.__scanFilter = f; go("signal-scanner")(); };
  const M = (window.__BV && window.__BV.market) || null;
  const buy = M ? M.funnel.bullish : 14, watch = M ? M.funnel.neutral : 8, avoid = M ? M.funnel.bearish : 31;
  const universe = M ? M.funnel.universe : 612;
  const flagged = buy + watch + avoid || 1;
  const seg = (n) => `${(n / flagged) * 100}%`;
  const mood = [
    { l: "FEAR/GREED", v: M && M.fearGreed != null ? String(M.fearGreed) : "62", tone: "gn", pct: M && M.fearGreed != null ? M.fearGreed : 62 },
    { l: "BREADTH",    v: M && M.breadthPct != null ? Math.round(M.breadthPct) + "%" : "56%", tone: "gn", pct: M && M.breadthPct != null ? Math.round(M.breadthPct) : 56 },
    { l: "PUT/CALL",   v: M && M.putCall != null ? M.putCall.toFixed(2) : "0.78", tone: "gn", pct: 60 },
    { l: "NEW HIGHS",  v: M && M.newHighs != null ? String(M.newHighs) : "—", tone: "gn", pct: 50 },
    { l: ">200-DMA",   v: M && M.breadth200 != null ? Math.round(M.breadth200) + "%" : "—", tone: "gn", pct: M && M.breadth200 != null ? Math.round(M.breadth200) : 55 },
    { l: "MAX SIZE",   v: M && M.maxSize != null ? M.maxSize + "%" : "70%", tone: "amb", pct: M && M.maxSize != null ? M.maxSize : 70 },
  ];
  const regOn = M ? M.regimeLabel : "RISK-ON";
  const regTrend = M ? M.regimeTrend : "CHOPPY";
  return (
    <div className="home-hero qhero">
      <div className="qh-top">
        <div className="qh-eyebrow mono">SwingTrade {(() => {
          // Real scan timestamp from BV.scanMeta (bundle run_timestamp) — was a
          // hardcoded "2026-05-28 · 14:23:08 ET" that never updated (audit 2026-06-04).
          const m = (typeof window !== "undefined" && window.__BV && window.__BV.scanMeta) || null;
          if (!m || !m.ts) return <span className="dim2">· last refresh unavailable</span>;
          const hrs = m.ageMin != null ? m.ageMin / 60 : null;
          const age = hrs == null ? "" : (hrs < 1 ? Math.round(m.ageMin) + "m" : hrs.toFixed(hrs < 10 ? 1 : 0) + "h");
          const cls = m.stale ? "amb" : "dim2";
          return <span className={cls}>· refreshed {String(m.ts).replace(" ", " · ")} PT{age ? " · " + age + " ago" : ""}</span>;
        })()}</div>
        {(() => {
          const m = (typeof window !== "undefined" && window.__BV && window.__BV.scanMeta) || null;
          const stale = !!(m && m.stale);
          return <span className={`qh-live mono${stale ? " is-stale" : ""}`}><span className="qh-live-dot" />{stale ? "STALE" : "LIVE"} · MARKET MOOD</span>;
        })()}
      </div>

      <div className="qh-band">
        <button className="qh-regime" onClick={go("signal-scanner")} title="Multi-factor regime → open Scanner">
          <span className="qh-cap mono">REGIME · TAPE</span>
          <span className="qh-regime-v mono"><b className={regOn === "RISK-ON" ? "up" : "dn"}>{regOn}</b><span className="qh-sep">·</span><b className="amb">{regTrend}</b></span>
          <span className="qh-regime-wr mono dim2">multi-factor{M && M.maxSize != null ? ` · max size ${M.maxSize}%` : ""}</span>
        </button>

        <div className="qh-funnel">
          <div className="qh-cap mono">SCAN FUNNEL <span className="dim2">· {universe} ranked → {flagged} flagged</span></div>
          <div className="qh-funnel-bar">
            <i className="qh-seg qh-seg--gn"  style={{ width: seg(buy) }}   title={`${buy} Bullish`} />
            <i className="qh-seg qh-seg--amb" style={{ width: seg(watch) }} title={`${watch} Neutral`} />
            <i className="qh-seg qh-seg--rd"  style={{ width: seg(avoid) }} title={`${avoid} Bearish`} />
          </div>
          <div className="qh-funnel-stats">
            <button className="qh-fstat qh-fstat--copper" onClick={scan("ALL")}   title="Scanner · all"><b>{universe}</b><span>universe</span></button>
            <button className="qh-fstat qh-fstat--gn"     onClick={scan("BUY")}   title="Scanner · Bullish"><b>{buy}</b><span>bullish</span></button>
            <button className="qh-fstat qh-fstat--amb"    onClick={scan("WATCH")} title="Scanner · Neutral"><b>{watch}</b><span>neutral</span></button>
            <button className="qh-fstat qh-fstat--rd"     onClick={scan("SHORT")} title="Scanner · Bearish"><b>{avoid}</b><span>bearish</span></button>
          </div>
        </div>

        <div className="qh-mood">
          <div className="qh-cap mono">MARKET MOOD</div>
          <div className="qh-mood-row">
            {mood.map((m, i) => (
              <div key={i} className={`qh-m qh-m--${m.tone}`}>
                <span className="qh-m-l mono">{m.l}</span>
                <span className="qh-m-v mono">{m.v}</span>
                <span className="qh-m-bar"><i style={{ width: `${m.pct}%` }} /></span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <HomeBrief />
    </div>
  );
}

function MoodTile({ label, value, tone, delta, pct = 50 }) {
  return (
    <div className={`hv-mood-tile hv-mood-tile--${tone}`}>
      <div className="hv-mt-l mono">{label}</div>
      <div className={`hv-mt-v mono kpi-tone--${tone}`}>{value}</div>
      <div className={`hv-mt-meter hv-mt-meter--${tone}`}>
        <span className="hv-mt-meter-fill" style={{ width: `${Math.max(4, Math.min(100, pct))}%` }} />
      </div>
      <div className="hv-mt-s mono dim2">{delta}</div>
    </div>
  );
}

// Overnight "what changed vs yesterday" — compact one-line writeup.
function HomeBrief() {
  return (
    <div className="hh-brief">
      <span className="hh-brief-tag mono">WHAT CHANGED · vs yesterday</span>
      <span className="hh-brief-txt mono">
        Regime softened <b className="amb">trending → CHOPPY</b> (CPI 08:30 risk) · Fear/Greed <b className="up">55 → 62</b> on AI-capex + CRWV beat · breadth <b className="up">49 → 56%</b> · VIX %ile <b className="up">41 → 32</b> calmer.
      </span>
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
          <div className="mono hb-v">{(window.__BV && window.__BV.navStr()) || "$108,420"}</div>
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
    { t: "06:14", tone: "gn",  tag: "BULLISH", sym: "ARGN", text: "Bias shifted Neutral → Bullish · score 71 → 81" },
    { t: "05:48", tone: "gn",  tag: "ALERT",  sym: "ARCM", text: "Pivot break: close > $66.40 on +1.6× RVOL" },
    { t: "04:22", tone: "amb", tag: "ER",     sym: "GENO", text: "ER in 9 sessions · event-risk elevated" },
    { t: "03:41", tone: "rd",  tag: "BEARISH", sym: "BIVO", text: "Distribution signature · moved to excluded" },
    { t: "02:14", tone: "ink", tag: "BUNDLE", sym: null,   text: "Daily bundle generated · 612 ranked · 14 Bullish · 8 Neutral · 31 Bearish" },
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
    { done: false, tag: "BRACKET",     text: "Place BUY-STOP $66.18 ARCM · 110 sh · OCO (self-directed)", time: "now",   tone: "copper" },
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
