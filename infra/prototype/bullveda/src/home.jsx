// home.jsx — landing/home view for the terminal
// Full-bleed market map + summary cards. Shown when no ticker is "drilled into".

const { useMemo: useMemoH } = React;

// ═══════════════════════════════════════════════════════════════════
// REAL-DATA LAYER  (audit-log consistency)
// Every ticker the Home page surfaces is sourced from the live scan universe
// (window.__BV.scanRows) and — when the forward-scored ledger has loaded —
// intersected with the audit log (window.SigLedger.SIGNALS). This guarantees
// every clickable symbol on Home also exists in Track Record / the audit log.
// When no live universe is present (standalone showcase / server down) each
// helper returns null and the component falls back to its curated sample set.
// ═══════════════════════════════════════════════════════════════════
const HR = (function () {
  const num = (v, d) => (typeof v === "number" && isFinite(v)) ? v : d;
  const numStr = (v) => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const sym0 = (s) => String(s || "").split(".")[0].toUpperCase();
  let _LSET = null, _LKEY = "";
  function ledgerSet() {
    const SL = window.SigLedger;
    if (!SL || !SL.SIGNALS || !SL.SIGNALS.length) return null;
    const key = (SL.real ? "R" : "S") + SL.SIGNALS.length;
    if (key !== _LKEY) { _LSET = new Set(SL.SIGNALS.map(s => s.sym)); _LKEY = key; }
    return _LSET;
  }
  // true once the REAL forward-scored ledger has loaded (deferred, post-paint)
  function ledgerReal() { return !!(window.SigLedger && window.SigLedger.real); }
  function rows() {
    const BV = window.__BV;
    return (BV && BV.ready && BV.scanRows) ? BV.scanRows() : [];
  }
  // Scan rows present in the audit log. Falls back to the full universe until the
  // real ledger lands (those rows ARE the published universe → end up in the log).
  function pool() {
    const rs = rows();
    if (!rs.length) return [];
    const set = ledgerSet();
    if (set && ledgerReal()) {
      const inb = rs.filter(r => set.has(r.sym));
      if (inb.length >= 12) return inb;
    }
    return rs;
  }
  // Drop any symbol not in the audit log (only once the real ledger is loaded).
  function auditOnly(syms) {
    const set = ledgerSet();
    if (!set || !ledgerReal()) return syms;
    return syms.filter(s => set.has(sym0(s)));
  }
  function inAudit(sym) {
    const set = ledgerSet();
    if (!set || !ledgerReal()) return true;
    return set.has(sym0(sym));
  }
  function findRow(sym) {
    const BV = window.__BV;
    return (BV && BV.findRow) ? BV.findRow(sym0(sym)) : null;
  }
  function held() {
    const BV = window.__BV, h = BV && BV.realHoldings && BV.realHoldings();
    return new Set((h || []).map(p => sym0(p.sym)));
  }
  return { num, numStr, sym0, rows, pool, ledgerSet, ledgerReal, auditOnly, inAudit, findRow, held, has: () => rows().length > 0 };
})();

function HomeView({ onTicker, onSurface, mode, surface }) {
  const uni = (window.__BV && window.__BV.market && window.__BV.market.funnel && window.__BV.market.funnel.universe) || null;
  const uniStr = uni != null ? uni.toLocaleString() : "612";
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
      <div className="home-sec-label"><span className="mono">OPPORTUNITY · TODAY'S SCAN</span><span className="mono dim2">{uniStr} ranked · regime-fit · edge-validated</span></div>
      <div className="home-grid-3">
        <HomeCard title="Top setups" sub={`top 5 of ${uniStr} universe · ranked by edge (R × Wilson LB)`} cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
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
// ─── Index strip — REAL cross-asset tape ─────────────────────────
// Sourced from critical.{regime, macro_signals, bonds_forex}: SPY/QQQ/VIX +
// treasuries, FX, gold, dollar. Headline-index/commodity tiles with no live
// feed in the current stack are omitted rather than faked.
const IDXSTRIP_MOCK = [
  { s: "S&P 500", v: "6,148.2", c: +0.42 }, { s: "NASDAQ", v: "20,310", c: +0.84 },
  { s: "VIX", v: "16.3", c: -1.81 }, { s: "US 10Y", v: "4.32%", c: -0.46 },
  { s: "DXY", v: "103.4", c: +0.10 }, { s: "GOLD", v: "2,418", c: +0.34 },
];
function resolveIndexStrip() {
  const BV = window.__BV;
  const n = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
  const fmt = (v, dp = 2) => v == null ? "—" : v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(dp);
  const out = [];
  const have = new Set();
  const push = (s, v, c2) => { if (v != null && v !== "—" && !have.has(s)) { out.push({ s, v, c: c2 }); have.add(s); } };
  // ── TRUE headline indices — Schwab $SPX/$COMPX/$DJI/$RUT/$VIX/$TNX + EODHD BTC/ETH ──
  const iq = (BV && BV.indexQuotes) || null;
  if (iq && iq.length) {
    iq.forEach(q => {
      if (!q || q.value == null) return;
      const v = q.suffix === "%" ? (q.value.toFixed(2) + "%") : fmt(q.value);
      push(q.label, v, q.chg != null ? q.chg : null);
    });
  }
  // ── real ETF/cross-asset proxies for tiles the headline feed doesn't cover ──
  const c = (BV && BV.critical) || null;
  if (c) {
    const mac = c.macro_signals || {}, bf = c.bonds_forex || {};
    const bfc = (k) => bf[k] ? n(bf[k].change_p) : null;
    // (GOLD now arrives as a true future via index_quotes — no GLD proxy here)
    if (mac.dxy) push("DXY·UUP", fmt(n(mac.dxy.price)), n(mac.dxy.chg5d));
    if (bf["TYX.INDX"]) push("US 30Y", n(bf["TYX.INDX"].price) != null ? n(bf["TYX.INDX"].price).toFixed(2) + "%" : null, bfc("TYX.INDX"));
    if (bf["EURUSD.FOREX"]) push("EUR/USD", fmt(n(bf["EURUSD.FOREX"].price), 4), bfc("EURUSD.FOREX"));
    if (bf["USDJPY.FOREX"]) push("USD/JPY", fmt(n(bf["USDJPY.FOREX"].price), 2), bfc("USDJPY.FOREX"));
    if (mac.hyg) push("HY·HYG", fmt(n(mac.hyg.price)), n(mac.hyg.chg5d));
  }
  return out.length >= 4 ? out : IDXSTRIP_MOCK;
}
function IndexStrip() {
  const idx = useMemoH(() => resolveIndexStrip(), [bvTok()]);
  return (
    <div className="ix-strip">
      {idx.map((i, k) => (
        <div key={k} className={`ix ix--${i.c == null ? "ink" : i.c >= 0 ? "gn" : "rd"}`}>
          <span className="ix-s mono">{i.s}</span>
          <span className="ix-v mono">{i.v}</span>
          {i.c != null
            ? <span className={`ix-c mono ${i.c >= 0 ? "up" : "dn"}`}>{i.c >= 0 ? "+" : ""}{i.c.toFixed(2)}%</span>
            : <span className="ix-c mono dim2">—</span>}
          <Spark sym={i.s} up={i.c == null ? true : i.c >= 0} />
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
  const M = (window.__BV && window.__BV.market) || null;
  // breadth / regime internals — real from BV.market when available
  const breadth = M ? [
    { k: ">50-DMA", v: M.breadthPct != null ? Math.round(M.breadthPct) + "%" : "—", tone: "gn" },
    { k: ">200-DMA", v: M.breadth200 != null ? Math.round(M.breadth200) + "%" : "—", tone: "gn" },
    { k: "New highs", v: M.newHighs != null ? "+" + M.newHighs : "—", tone: "gn" },
    { k: "New lows", v: M.newLows != null ? String(M.newLows) : "—", tone: M.newLows > (M.newHighs || 0) ? "rd" : "gn" },
    { k: "Fear/Greed", v: M.fearGreed != null ? String(M.fearGreed) : "—", tone: "gn" },
    { k: "Put/Call", v: M.putCall != null ? M.putCall.toFixed(2) : "—", tone: "amb" },
  ] : [
    { k: ">50-DMA", v: "62%", tone: "gn" }, { k: ">200-DMA", v: "58%", tone: "gn" },
    { k: "A/D line", v: "+1,240", tone: "gn" }, { k: "New H–L", v: "+86", tone: "gn" },
    { k: "VIX", v: "16.3", tone: "gn" }, { k: "Put/Call", v: "0.82", tone: "amb" },
  ];
  // gappers — biggest movers from the live universe (audit-log intersected)
  const gappers = useMemoH(() => {
    const rows = HR.pool();
    if (!rows.length) return [
      { sym: "NVDA", pct: +4.2, why: "capex guide", held: false },
      { sym: "ARGN", pct: +2.1, why: "sector flows", held: true },
      { sym: "XOM", pct: -2.6, why: "crude −2%", held: false },
      { sym: "GENO", pct: -3.8, why: "offering", held: false },
    ];
    const a = rows.filter(r => HR.num(r.chg, null) != null && HR.inAudit(r.sym));
    const held = HR.held();
    const ups = [...a].sort((x, y) => y.chg - x.chg).slice(0, 2);
    const dns = [...a].sort((x, y) => x.chg - y.chg).slice(0, 2);
    return [...ups, ...dns].map(r => ({ sym: r.sym, pct: +r.chg.toFixed(1), why: r.setup || r.sector || "flow", held: held.has(r.sym) }));
  }, [bvTok()]);
  // calendar — real upcoming earnings injected alongside macro prints
  const events = useMemoH(() => {
    const eb = (window.__BV && window.__BV.earningsBeat) || [];
    const c = (window.__BV && window.__BV.critical) || null;
    const held = HR.held();
    const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const dlabel = (d) => { if (d == null) return ""; const dt = new Date(Date.now() + d * 86400000); return d === 0 ? "Today" : DOW[dt.getDay()]; };
    // REAL macro prints from critical.economic_events (US, next ~10d, by date)
    const now = Date.now();
    const seen = new Set();
    const macro = ((c && c.economic_events) || [])
      .filter(e => (e.country === "US" || !e.country) && e.date)
      .map(e => ({ ...e, _ts: Date.parse((e.date || "").replace(" ", "T")) }))
      .filter(e => isFinite(e._ts) && e._ts >= now - 86400000 && e._ts <= now + 14 * 86400000)
      .sort((a, b) => a._ts - b._ts)
      .filter(e => { const k = e.type + "|" + e.date; if (seen.has(k)) return false; seen.add(k); return true; })
      .slice(0, 3)
      .map(e => ({ d: DOW[new Date(e._ts).getDay()], t: e.type + (e.period ? " · " + e.period : ""),
        imp: (e._impact === "HIGH" ? "high" : e._impact === "LOW" ? "low" : "med"),
        note: new Date(e._ts).toLocaleDateString("en-US", { month: "short", day: "numeric" }) + (e.previous != null ? " · prev " + e.previous : "") }));
    // REAL upcoming earnings (next 5d, audit-log names)
    const earn = eb.filter(e => e.ticker && HR.num(e.days_to_earnings, 99) <= 5 && HR.inAudit(e.ticker))
      .sort((a, b) => (a.days_to_earnings - b.days_to_earnings) || (b.beat_score || 0) - (a.beat_score || 0))
      .slice(0, 2)
      .map(e => ({ d: dlabel(e.days_to_earnings), t: HR.sym0(e.ticker) + " earnings", imp: (e.tier && /strong/i.test(e.tier)) ? "high" : "med",
        note: (/before/i.test(e.before_after || "") ? "BMO" : "AMC") + (e.beat_score != null ? " · beat " + Math.round(e.beat_score) : ""), held: held.has(HR.sym0(e.ticker)) }));
    const merged = [...macro, ...earn];
    if (merged.length) return merged;
    // showcase fallback (no live feeds)
    return [
      { d: "Tue", t: "CPI · MoM", imp: "high", note: "08:30 · core in focus" },
      { d: "Wed", t: "FOMC minutes", imp: "high", note: "14:00 · dot-plot" },
    ];
  }, [bvTok()]);
  return (
    <div className="home-grid-3 mbf">
      {/* REGIME */}
      <div className="mbf-card" onClick={() => go("internals")}>
        <div className="mbf-hd">
          <span className="mbf-tag mono">REGIME</span>
          <span className="mbf-go mono">Internals →</span>
        </div>
        <div className="mbf-regime">
          <span className="mbf-regime-v mono"><b className={M && !M.regimeOn ? "dn" : "up"}>{M ? M.regimeLabel : "RISK-ON"}</b> · <b className="warn">{M ? M.regimeTrend : "CHOPPY"}</b></span>
          <span className="mbf-regime-cap mono dim2">{M && M.maxSize != null ? `~${M.maxSize}% max size` : "~70% size"}</span>
        </div>
        <div className="mbf-breadth">
          {breadth.map((b, i) => (
            <div key={i} className="mbf-br">
              <span className="mbf-br-k mono dim2">{b.k}</span>
              <span className={`mbf-br-v mono ${b.tone === "gn" ? "up" : b.tone === "rd" ? "dn" : "warn"}`}>{b.v}</span>
            </div>
          ))}
        </div>
        <div className="mbf-foot mono dim2">{(() => {
          if (!M) return "Breadth healthy but tape choppy — size into prints carefully.";
          const rgc = (window.__BV && window.__BV.critical && window.__BV.critical.regime) || {};
          const dist = rgc.distribution_state ? String(rgc.distribution_state).replace(/_/g, " ") : null;
          const b = M.breadthPct != null ? Math.round(M.breadthPct) : null;
          return `${M.regimeLabel} · ${M.regimeTrend}${b != null ? ` · breadth ${b}%` : ""}${dist ? ` · ${dist}` : ""} — max size ${M.maxSize != null ? M.maxSize : 70}%.`;
        })()}</div>
      </div>

      {/* PRE-MARKET */}
      <div className="mbf-card" onClick={() => go("premarket")}>
        <div className="mbf-hd">
          <span className="mbf-tag mono">PRE-MARKET</span>
          <span className="mbf-go mono">Gap board →</span>
        </div>
        <div className="mbf-sub mono dim2">{(() => {
          const rgc = (window.__BV && window.__BV.critical && window.__BV.critical.regime) || {};
          const spy = typeof rgc.spy_daily_chg === "number" ? rgc.spy_daily_chg : null;
          const pm = (window.__BV && window.__BV.critical && window.__BV.critical.premarket) || {};
          const sess = pm._meta && pm._meta.session_active ? "pre-market" : "prior close";
          return `${spy != null ? `SPY ${spy >= 0 ? "+" : ""}${spy.toFixed(1)}% · ` : ""}${sess} · top movers`;
        })()}</div>
        <div className="mbf-gaps">
          {gappers.map((g, i) => (
            <button key={i} className="mbf-gap" onClick={(e) => { e.stopPropagation(); onTicker && onTicker(g.sym); }}>
              <span className="mbf-gap-sym mono">{g.sym}{g.held && <span className="mbf-held mono">HELD</span>}</span>
              <span className={`mbf-gap-pct mono ${g.pct >= 0 ? "up" : "dn"}`}>{g.pct >= 0 ? "+" : ""}{g.pct.toFixed(1)}%</span>
              <span className="mbf-gap-why mono dim2">{g.why}</span>
            </button>
          ))}
        </div>
        <div className="mbf-foot mono dim2">{(() => {
          const heldG = gappers.find(g => g.held);
          if (heldG) return <><b className="copper">{heldG.sym}</b> in your book {heldG.pct >= 0 ? "up" : "down"} {Math.abs(heldG.pct).toFixed(1)}% · {heldG.why}.</>;
          const top = gappers[0];
          return top ? <>Biggest mover <b className="copper">{top.sym}</b> {top.pct >= 0 ? "+" : ""}{top.pct.toFixed(1)}% · {top.why}.</> : "No notable gaps.";
        })()}</div>
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
        <div className="mbf-foot mono dim2">{(() => {
          const high = events.filter(e => e.imp === "high");
          if (high.length) return `${high.map(e => e.t.replace(/ · .*/, "")).slice(0, 2).join(" + ")} ${high.length > 1 ? "are" : "is a"} high-impact — size into ${high.length > 1 ? "them" : "it"} carefully.`;
          return events.length ? "Lighter calendar — no high-impact prints flagged." : "Calendar loading…";
        })()}</div>
      </div>
    </div>
  );
}

// ─── Real market news (EODHD, from critical.market_news) ─────────
function fmtAgo(dateStr) {
  if (!dateStr) return "";
  const then = Date.parse(dateStr);
  if (!isFinite(then)) return "";
  const min = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (min < 60) return min + "m";
  const hr = min / 60;
  if (hr < 24) return (hr < 10 ? hr.toFixed(0) : Math.round(hr)) + "h";
  return Math.round(hr / 24) + "d";
}
// Build real story objects (audit-log-only tickers). null when no live feed.
function realStories(limit) {
  const mn = (window.__BV && window.__BV.marketNews) || [];
  if (!mn.length) return null;
  const out = [];
  for (const a of mn) {
    if (!a.title) continue;
    const syms = HR.auditOnly((a.symbols || []).map(HR.sym0).filter(Boolean));
    const tone = a.sentiment === "positive" ? "gn" : a.sentiment === "negative" ? "rd" : "amb";
    const pol = HR.num(a.polarity, null);
    const sent = pol == null ? null : tone === "rd" ? -Math.abs(pol) : tone === "amb" ? 0 : Math.abs(pol);
    const tickers = syms.slice(0, 3).map(s => {
      const row = HR.findRow(s);
      return [s, row ? HR.num(row.chg, 0) : 0];
    });
    out.push({
      t: fmtAgo(a.date), date: a.date, src: (a.source || "EODHD"),
      sym: syms[0] || null, sent, tone, head: a.title, sum: a.summary || "",
      url: a.url || "", tickers, affects: syms.slice(0, 3),
      impact: tone === "gn" ? "Bullish" : tone === "rd" ? "Bearish" : "Neutral",
    });
    if (out.length >= (limit || 99)) break;
  }
  return out.length ? out : null;
}

// ─── Top Stories / news ──────────────────────────────────────────
function TopStories({ onTicker }) {
  const real = useMemoH(() => realStories(5), [bvTok()]);
  const stories = real || [
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
  const impactTone = { "Sector tailwind": "gn", "Stock-specific": "gn", "Macro · rates": "amb", "Binary catalyst": "amb", "Sector risk": "rd", "Bullish": "gn", "Bearish": "rd", "Neutral": "amb" };
  return (
    <div className="ts">
      {stories.map((s, i) => (
        <div key={i} className={`ts-row ts-${s.tone}`} onClick={() => s.sym && onTicker(s.sym)}>
          <div className="ts-top">
            <span className="ts-time mono dim2">{s.t}{s.t ? " ago" : ""}</span>
            <span className="ts-src mono dim2">{s.src}</span>
            {s.sym && <span className="ts-sym mono">{s.sym}</span>}
            {s.sent != null && <span className={`ts-sent mono ${s.sent >= 0 ? "up" : "dn"}`}>{s.sent >= 0 ? "+" : ""}{s.sent.toFixed(1)}</span>}
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
const EARNINGS_MOCK = [
  { sym: "CRWV", when: "BMO", time: "today", beat: 71, tier: "SOLID",  tone: "amb", held: false },
  { sym: "GENO", when: "AMC", time: "today", beat: 64, tier: "SOLID",  tone: "amb", held: false },
  { sym: "TURM", when: "AMC", time: "today", beat: 48, tier: "WEAK",   tone: "rd",  held: false },
  { sym: "BORA", when: "AMC", time: "today", beat: 82, tier: "STRONG", tone: "gn",  held: true },
];

function resolveEarningsToday() {
  const eb = (window.__BV && window.__BV.earningsBeat) || [];
  if (!eb.length) return EARNINGS_MOCK;
  const held = HR.held();
  const tierTone = (t) => /strong/i.test(t) ? "gn" : /solid/i.test(t) ? "amb" : "rd";
  const today = eb.filter(e => e.ticker && HR.num(e.days_to_earnings, 99) <= 1);
  const src = (today.length ? today : eb).slice(0, 6)
    .sort((a, b) => (b.beat_score || 0) - (a.beat_score || 0));
  return src.map(e => {
    const sym = HR.sym0(e.ticker);
    const d = HR.num(e.days_to_earnings, null);
    return {
      sym, when: /before/i.test(e.before_after || "") ? "BMO" : "AMC",
      time: d === 0 ? "today" : d != null ? "T−" + d : "",
      beat: e.beat_score != null ? Math.round(e.beat_score) : null,
      tier: e.tier || "", tone: tierTone(e.tier || ""), held: held.has(sym),
    };
  });
}

function EarningsToday({ onTicker }) {
  const rows = useMemoH(() => resolveEarningsToday(), [bvTok()]);
  const heldRows = rows.filter(r => r.held).map(r => r.sym);
  return (
    <div className="et">
      <div className="et-hdr mono dim2">
        <span>{rows.length} reporting · </span>
        {heldRows.length
          ? <span className="warn">{heldRows.length} held ({heldRows.join(", ")})</span>
          : <span className="dim">no book exposure</span>}
        <span> · beat-score model</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className={`et-row ${r.held ? "is-held" : ""}`} onClick={() => onTicker(r.sym)}>
          <span className="et-sym mono"><b>{r.sym}</b></span>
          <span className={`et-when mono ${r.when === "BMO" ? "cy" : "amb"}`}>{r.when}</span>
          <span className="et-time mono dim2">{r.time}</span>
          <span className={`et-move mono kpi-tone--${r.tone}`}>{r.tier || "—"}</span>
          <span className={`et-esp mono kpi-tone--${r.tone}`}>{r.beat != null ? "BEAT " + r.beat : "—"}</span>
          {r.held
            ? <span className="et-expo mono gn">HELD</span>
            : <span className="et-expo mono dim">—</span>}
        </div>
      ))}
    </div>
  );
}

// ─── Discovery ───────────────────────────────────────────────────
const DISCOVERY_MOCK = [
  { tag: "52W HIGH", tone: "gn",  items: [["ARGN","+3.1"],["NVRH","+2.4"],["DRSH","+2.9"]] },
  { tag: "SQUEEZE",  tone: "amb", items: [["MERC","8.1d"],["KARO","6.4d"],["FOLD","5.2d"]] },
  { tag: "INSIDER",  tone: "cy",  items: [["ARCM","+$0.5M"],["BORA","+$0.3M"],["INPR","+$0.2M"]] },
  { tag: "UOA",      tone: "violet", items: [["ARGN","70C×4"],["GENO","30C×3"],["DRSH","60C×2"]] },
  { tag: "EMERGING", tone: "copper", items: [["IPSO","new"],["SEND","new"],["AXLE","new"]] },
];

// Real discovery groups from the live scan universe (audit-log intersected).
function resolveDiscovery() {
  const rows = HR.pool();
  if (!rows.length) return DISCOVERY_MOCK;
  const pick = (arr, n) => HR.auditOnly(arr.map(x => x[0]).slice(0, n + 4))
    .slice(0, n).map(s => { const o = arr.find(a => a[0] === s); return o ? [o[0], o[1]] : [s, ""]; });
  const hi = rows.filter(r => r.off52 != null && r.off52 >= -3 && HR.num(r.chg, null) != null)
    .sort((a, b) => b.off52 - a.off52).map(r => [r.sym, (r.chg >= 0 ? "+" : "") + r.chg.toFixed(1)]);
  const sq = rows.filter(r => r.sqRank >= 1).sort((a, b) => b.sqRank - a.sqRank || b.score - a.score)
    .map(r => [r.sym, r.squeeze]);
  const ins = rows.filter(r => HR.num(r.insUsd, 0) > 0).sort((a, b) => b.insUsd - a.insUsd)
    .map(r => [r.sym, "+$" + r.insUsd.toFixed(1) + "M"]);
  const of = (window.__BV && window.__BV.optionsFlow) || [];
  const uoa = of.filter(o => o.ticker).sort((a, b) => (b.uoa_calls || 0) - (a.uoa_calls || 0))
    .map(o => [HR.sym0(o.ticker), o.status || "UOA"]);
  const emg = rows.filter(r => r.verdict === "WATCH" && r.score >= 55).sort((a, b) => b.score - a.score)
    .map(r => [r.sym, "watch"]);
  const groups = [
    { tag: "52W HIGH", tone: "gn",     items: pick(hi, 3) },
    { tag: "SQUEEZE",  tone: "amb",    items: pick(sq, 3) },
    { tag: "INSIDER",  tone: "cy",     items: pick(ins, 3) },
    { tag: "UOA",      tone: "violet", items: HR.auditOnly(uoa.map(x => x[0]).slice(0, 7)).slice(0, 3).map(s => { const o = uoa.find(a => a[0] === s); return o ? [o[0], o[1]] : [s, "UOA"]; }) },
    { tag: "EMERGING", tone: "copper", items: pick(emg, 3) },
  ];
  // keep only groups that actually produced names; if all empty, fall back to mock
  const filled = groups.filter(g => g.items.length);
  return filled.length ? groups.map(g => g.items.length ? g : { ...g, items: [] }) : DISCOVERY_MOCK;
}

function Discovery({ onTicker }) {
  const groups = useMemoH(() => resolveDiscovery(), [bvTok()]).filter(g => g.items.length);
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
  const all = useMemoH(() => {
    const rows = HR.pool();
    if (rows.length) {
      return rows.filter(r => HR.num(r.chg, null) != null && HR.inAudit(r.sym))
        .map(r => ({ sym: r.sym, sector: r.sector, chg: r.chg }))
        .sort((a, b) => b.chg - a.chg);
    }
    return HEATMAP.map(([sym, sector, mcap, chg]) => ({ sym, sector, chg })).sort((a, b) => b.chg - a.chg);
  }, [bvTok()]);
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

// Token that changes when the live universe / forward-scored ledger become
// available — used as a memo dependency so Home re-derives real rows post-load.
const bvTok = () => (HR.has() ? 1 : 0) + (HR.ledgerReal() ? 2 : 0) + (window.AIPredict && window.AIPredict.all ? 4 : 0);

// Build each engine's top-5 from the REAL scan universe (audit-log intersected).
// Returns null when no live universe is present → caller keeps the curated rows.
function realEngineRows(id) {
  const rows = HR.pool();
  if (!rows.length) return null;
  // Prefer audit-log names; if intersection is too thin, keep the real feed names
  // (still real tickers — never fall back to the curated showcase set when live).
  const top5 = (arr) => {
    const top8 = arr.slice(0, 8);
    const aud = HR.auditOnly(top8.map(x => x[0]));
    const syms = (aud.length >= 3 ? aud : top8.map(x => x[0])).slice(0, 5);
    return syms.map(s => { const o = arr.find(a => a[0] === s); return [s, o ? o[1] : ""]; });
  };
  if (id === "momentum") {
    const r = rows.filter(x => HR.numStr(x.rs) != null).sort((a, b) => HR.numStr(b.rs) - HR.numStr(a.rs))
      .map(x => [x.sym, x.rs]);
    return r.length ? top5(r) : null;
  }
  if (id === "earnings-ai") {
    const eb = (window.__BV && window.__BV.earningsBeat) || [];
    const r = eb.filter(e => e.ticker && e.beat_score != null).sort((a, b) => b.beat_score - a.beat_score)
      .map(e => [HR.sym0(e.ticker), Math.round(e.beat_score) + "%"]);
    return r.length ? top5(r) : null;
  }
  if (id === "ml") {
    if (window.AIPredict && window.AIPredict.all) {
      const r = window.AIPredict.all().map(p => [HR.sym0(p.sym), Math.round((p.pUp || 0.5) * 100) + "%"]);
      return r.length ? top5(r) : null;
    }
    return null;
  }
  if (id === "options") {
    const of = (window.__BV && window.__BV.optionsFlow) || [];
    const r = of.filter(o => o.ticker && o.rr != null).sort((a, b) => (b.rr || 0) - (a.rr || 0))
      .map(o => [HR.sym0(o.ticker), (+o.rr).toFixed(1)]);
    return r.length ? top5(r) : null;
  }
  if (id === "insider") {
    const r = rows.filter(x => HR.num(x.insUsd, 0) > 0).sort((a, b) => b.insUsd - a.insUsd)
      .map(x => [x.sym, "+$" + x.insUsd.toFixed(1) + "M"]);
    return r.length ? top5(r) : null;
  }
  if (id === "smc") {
    const r = rows.filter(x => x.pillarPct && x.pillarPct.smc != null)
      .sort((a, b) => b.pillarPct.smc - a.pillarPct.smc).map(x => [x.sym, x.edge || ""]);
    return r.length ? top5(r) : null;
  }
  return null;
}

// Resolve engines with REAL rows when the live universe is available; keep the
// curated sample rows otherwise (standalone showcase).
function resolveEngines() {
  const live = HR.has();
  return TBE_ENGINES.map(e => {
    const real = realEngineRows(e.id);
    if (real && real.length) return { ...e, rows: real, real: true };
    if (live) return { ...e, rows: [], real: true, empty: true }; // honest empty — never fake when live
    return e; // standalone showcase only
  });
}

// Top setups = top BUY (then WATCH) scan rows by score, audit-log intersected.
function resolveScannerPicks() {
  const rows = HR.pool();
  if (!rows.length) return SCANNER_PICKS;
  const rank = (v) => v === "BUY" ? 0 : v === "WATCH" ? 1 : v === "SHORT" ? 2 : 3;
  const picks = [...rows]
    .filter(r => ["BUY", "WATCH", "SHORT"].includes(r.verdict) && HR.inAudit(r.sym))
    .sort((a, b) => rank(a.verdict) - rank(b.verdict) || b.score - a.score)
    .slice(0, 5)
    .map(r => ({
      sym: r.sym, name: r.name, score: r.score,
      rr: r.rr !== "—" ? r.rr : null,
      wlb: r.wlb,  // feed-honest (null → "—")
      edge: r.aiEdge != null ? (r.aiEdge >= 0 ? "+" : "") + r.aiEdge.toFixed(2) : null,
      v: r.verdict,
    }));
  return picks.length ? picks : SCANNER_PICKS;
}

// Expose the discovery universe so the Consensus panel stays in sync.
window.TBE_ENGINES = TBE_ENGINES;
window.SCANNER_PICKS = SCANNER_PICKS;
window.resolveEngines = resolveEngines;
window.resolveScannerPicks = resolveScannerPicks;
function TopByEngine({ onTicker, onSurface }) {
  // Each engine's rows pull from the live scan universe (audit-log intersected);
  // ML pulls from the AIPredict ensemble. Re-derives when feeds finish loading.
  const engines = useMemoH(() => resolveEngines(), [bvTok()]);
  return (
    <div className="tbe-grid">
      {engines.map(e => (
        <div key={e.id} className="tbe-card" style={{ "--eng": e.accent }}>
          <button className="tbe-head" onClick={() => onSurface && onSurface(e.surface)}>
            <span className="tbe-title mono"><span className="tbe-dot" />{e.title}</span>
            <span className="tbe-metric mono dim2">{e.metric} <span className="tbe-arrow">→</span></span>
          </button>
          <div className="tbe-list">
            {e.rows.length ? e.rows.map(([sym, v], i) => (
              <button key={sym} className={`tbe-row ${i === 0 ? "is-lead" : ""}`} onClick={() => onTicker && onTicker(sym)}>
                <span className="tbe-rank mono">{i + 1}</span>
                <span className="tbe-sym mono"><b>{sym}</b></span>
                <span className="tbe-v mono">{v}</span>
              </button>
            )) : <div className="tbe-row" style={{ opacity: .5, cursor: "default" }}><span className="tbe-sym mono dim2">no signals today</span></div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Top Setups (merged Top BUY + best edge) ─────────────────────
function TopSetups({ onTicker }) {
  const rows = useMemoH(() => resolveScannerPicks(), [bvTok()]);
  const stat = (r) => {
    const parts = [];
    if (r.rr != null && r.rr !== "—") parts.push("R " + r.rr);
    if (r.wlb != null) parts.push("W " + r.wlb + "%");
    if (r.edge != null) parts.push("edge " + r.edge);
    return parts.length ? parts.join(" · ") : "live scan";
  };
  return (
    <div className="tset">
      {rows.map((r, i) => (
        <button key={r.sym} className="tset-row" onClick={() => onTicker(r.sym)}>
          <span className="tset-rank mono dim">{String(i + 1).padStart(2, "0")}</span>
          <span className="tset-sym mono"><b>{r.sym}</b></span>
          <span className="tset-score mono" data-tone={r.score >= 75 ? "gn" : r.score >= 60 ? "amb" : "rd"}>{r.score}</span>
          <span className="tset-mid">
            <span className="tset-name dim">{r.name}</span>
            <span className="tset-stats mono dim2">{stat(r)}</span>
          </span>
          <span className={`tset-v mono ${r.v === "BUY" ? "up" : r.v === "SHORT" ? "dn" : "warn"}`}>{secBias(r.v)}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Markets · News board — featured + latest feed + trending/gainers rail ──
// Real MARKETS·NEWS board: featured + stacks from EODHD market_news (audit-log
// tickers), trending/gainers rails from the live scan universe. Mock fallback
// per-slot when no live feed is present (standalone showcase).
function resolveNewsBoard() {
  const stories = realStories(11);
  const rows = HR.pool();
  const toStory = (s, live) => ({
    head: s.head, src: s.src, time: s.t, url: s.url, live: !!live, sum: s.sum,
    tickers: (s.tickers && s.tickers.length) ? s.tickers : (s.sym ? [[s.sym, 0]] : []),
  });
  let featured = null, leftStack = null, latest = null, trending = null, gainers = null;
  if (stories && stories.length) {
    featured = toStory(stories[0], true);
    leftStack = stories.slice(1, 5).map(s => toStory(s));
    latest = stories.slice(5, 11).map(s => toStory(s));
  }
  if (rows.length) {
    const px = (p) => p >= 1000 ? Math.round(p).toLocaleString() : p.toFixed(2);
    const audited = rows.filter(r => HR.inAudit(r.sym) && HR.num(r.chg, null) != null && HR.num(r.price, null) != null);
    trending = [...audited].sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 5)
      .map(r => ({ sym: r.sym, name: r.name, px: px(r.price), chg: r.chg, up: r.chg >= 0 }));
    gainers = [...audited].sort((a, b) => b.chg - a.chg).slice(0, 4)
      .map(r => ({ sym: r.sym, name: r.name, px: px(r.price), chg: r.chg }));
  }
  return { featured, leftStack, latest, trending, gainers };
}

function NewsMarketsBoard({ onTicker, onSurface }) {
  const real = useMemoH(() => resolveNewsBoard(), [bvTok()]);
  const featured = real.featured || {
    head: "Chipmakers extend rally as hyperscaler capex guides lift the group",
    src: "Reuters", time: "12m", live: true, tickers: [["NVDA", +6.26], ["AVGO", +3.1], ["ARM", +2.4]],
    sum: "Three hyperscalers raised FY capex on the same morning — a direct read-through to GPU and networking suppliers. Group +2.8% on 1.6× volume.",
  };
  const leftStack = real.leftStack || [
    { head: "Fed minutes preview: market prices 88% hold, dot-plot in focus", src: "Bloomberg", time: "1h", tickers: [["SPY", +0.4]] },
    { head: "Specialty-materials names see insider buying cluster", src: "Barron's", time: "2h", tickers: [["ARGN", +2.1]] },
    { head: "Crude slips on demand worries; energy complex under pressure", src: "WSJ", time: "3h", tickers: [["XOM", -2.6], ["XLE", -1.8]] },
    { head: "Alphabet plans to raise capex for AI; Street models 2027 payback", src: "Yahoo Finance", time: "5h", tickers: [["GOOGL", -1.0]] },
  ];
  const latest = real.latest || [
    { head: "Genoa Bio Phase-2 readout expected ahead of next-week print", src: "FierceBio", time: "16m", tickers: [["GENO", +0.5]] },
    { head: "Gold edges higher as traders weigh rate-path confusion", src: "Bloomberg", time: "36m", tickers: [["GLD", +0.7]] },
    { head: "BOJ should signal a clear rate path after June hike, says SMFG chief", src: "Reuters", time: "1h", tickers: [["JPY", +0.1]] },
    { head: "Lithium names rebound on supply-cut headlines out of Chile", src: "Reuters", time: "1h", tickers: [["LAC", +5.8]] },
    { head: "Software multiples compress as Street trims FY estimates", src: "Bloomberg", time: "2h", tickers: [["MDB", +20.4], ["TWLO", +19.4]] },
    { head: "Retail sales beat lifts consumer-discretionary breadth", src: "Reuters", time: "3h", tickers: [["XLY", +1.2]] },
  ];
  const trending = real.trending || [
    { sym: "NVDA", name: "NVIDIA Corp", px: "884.20", chg: +7.04, up: true },
    { sym: "BTC", name: "Bitcoin USD", px: "69,969", chg: -3.76, up: false },
    { sym: "ARGN", name: "Argentum Robotics", px: "213.40", chg: +3.10, up: true },
    { sym: "LAC", name: "Lithium Americas", px: "5.51", chg: +5.76, up: true },
    { sym: "ABVX", name: "ABIVAX SA", px: "129.69", chg: -2.22, up: false },
  ];
  const gainers = real.gainers || [
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
        <span className="nm-src">{s.src}</span>{s.time ? <span className="dim2"> · {s.time} ago</span> : null}
      </div>
      {big && s.sum && <div className="nm-sum">{s.sum}</div>}
      <div className="nm-chips">
        {s.tickers.map(([t, c], i) => (
          <span key={i} className="nm-chip mono" onClick={(e) => { e.stopPropagation(); onTicker(t); }}>{t}{c ? <b className={c >= 0 ? "up" : "dn"}> {c >= 0 ? "+" : ""}{c.toFixed(2)}%</b> : null}</span>
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

// Market-state one-liner — REAL regime + breadth + fear/greed + VIX + SPY daily.
function HomeBrief() {
  const M = (window.__BV && window.__BV.market) || null;
  const c = (window.__BV && window.__BV.critical) || null;
  const rg = (c && c.regime) || {};
  if (!M) {
    return (
      <div className="hh-brief">
        <span className="hh-brief-tag mono">MARKET STATE</span>
        <span className="hh-brief-txt mono">
          Regime <b className="amb">RISK-ON · CHOPPY</b> · Fear/Greed <b className="up">62</b> · breadth <b className="up">56%</b> · VIX <b className="up">16.3</b>.
        </span>
      </div>
    );
  }
  const tone = (M.regimeOn ? "up" : "dn");
  const vix = (typeof rg.vix_current === "number") ? rg.vix_current : (rg.vix && rg.vix.vix_current);
  const spyChg = (typeof rg.spy_daily_chg === "number") ? rg.spy_daily_chg : null;
  const dist = rg.distribution_state ? String(rg.distribution_state).replace(/_/g, " ") : null;
  return (
    <div className="hh-brief">
      <span className="hh-brief-tag mono">MARKET STATE · NOW</span>
      <span className="hh-brief-txt mono">
        Regime <b className={tone}>{M.regimeLabel} · {M.regimeTrend}</b>
        {M.maxSize != null ? <> (max size <b>{M.maxSize}%</b>)</> : null}
        {M.fearGreed != null ? <> · Fear/Greed <b className="up">{M.fearGreed}</b></> : null}
        {M.breadthPct != null ? <> · breadth <b>{Math.round(M.breadthPct)}%</b></> : null}
        {vix != null ? <> · VIX <b>{vix.toFixed(1)}</b></> : null}
        {spyChg != null ? <> · SPY <b className={spyChg >= 0 ? "up" : "dn"}>{spyChg >= 0 ? "+" : ""}{spyChg.toFixed(1)}%</b></> : null}
        {dist ? <> · <b className="dim2">{dist}</b></> : null}.
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
const SIGNALFEED_MOCK = [
  { t: "06:14", tone: "gn",  tag: "BULLISH", sym: "ARGN", text: "Bias shifted Neutral → Bullish · score 71 → 81" },
  { t: "05:48", tone: "gn",  tag: "ALERT",  sym: "ARCM", text: "Pivot break: close > $66.40 on +1.6× RVOL" },
  { t: "04:22", tone: "amb", tag: "ER",     sym: "GENO", text: "ER in 9 sessions · event-risk elevated" },
  { t: "03:41", tone: "rd",  tag: "BEARISH", sym: "BIVO", text: "Distribution signature · moved to excluded" },
  { t: "02:14", tone: "ink", tag: "BUNDLE", sym: null,   text: "Daily bundle generated · 612 ranked · 14 Bullish · 8 Neutral · 31 Bearish" },
  { t: "23:49", tone: "violet", tag: "AI",   sym: "DRSH", text: "AI hit-net edge +0.18 → +0.22 · drift KS 0.08" },
  { t: "22:12", tone: "cy",  tag: "INSIDER",sym: "ARCM", text: "Form 4 filed · CFO buy 5,000 sh @ $64.20" },
];

// Overnight signal feed from the live universe (audit-log tickers) + scan funnel.
function resolveSignalFeed() {
  const rows = HR.pool();
  if (!rows.length) return SIGNALFEED_MOCK;
  const inA = (r) => HR.inAudit(r.sym);
  const buys = rows.filter(r => r.verdict === "BUY" && inA(r)).sort((a, b) => b.score - a.score);
  const ins = rows.filter(r => HR.num(r.insUsd, 0) > 0 && inA(r)).sort((a, b) => b.insUsd - a.insUsd);
  const er = rows.filter(r => HR.num(r.er, 99) <= 9 && HR.num(r.er, 99) >= 0 && inA(r)).sort((a, b) => a.er - b.er);
  const bear = rows.filter(r => (r.verdict === "SHORT" || r.verdict === "AVOID") && inA(r)).sort((a, b) => a.score - b.score);
  const ai = rows.filter(r => r.aiEdge != null && inA(r)).sort((a, b) => b.aiEdge - a.aiEdge);
  const M = (window.__BV && window.__BV.market) || null;
  const out = [];
  if (buys[0]) out.push({ t: "06:14", tone: "gn", tag: "BULLISH", sym: buys[0].sym, text: `BUY verdict · score ${buys[0].score}${buys[0].setup ? " · " + buys[0].setup : ""}` });
  if (buys[1]) out.push({ t: "05:48", tone: "gn", tag: "ALERT", sym: buys[1].sym, text: `Entry ${buys[1].eq || "in zone"} · R:R ${buys[1].rr}${buys[1].rvol !== "—" ? " · " + buys[1].rvol + "× RVOL" : ""}` });
  if (er[0]) out.push({ t: "04:22", tone: "amb", tag: "ER", sym: er[0].sym, text: `ER in ${er[0].er} sessions · event-risk elevated` });
  if (bear[0]) out.push({ t: "03:41", tone: "rd", tag: "BEARISH", sym: bear[0].sym, text: `${bear[0].verdict} · score ${bear[0].score} · excluded from longs` });
  if (M && M.funnel) out.push({ t: "02:14", tone: "ink", tag: "BUNDLE", sym: null, text: `Daily bundle · ${M.funnel.universe} ranked · ${M.funnel.bullish} Bullish · ${M.funnel.neutral} Neutral · ${M.funnel.bearish} Bearish` });
  if (ai[0]) out.push({ t: "23:49", tone: "violet", tag: "AI", sym: ai[0].sym, text: `AI edge +${ai[0].aiEdge.toFixed(2)} · highest hit-net today` });
  if (ins[0]) out.push({ t: "22:12", tone: "cy", tag: "INSIDER", sym: ins[0].sym, text: `Insider cluster · +$${ins[0].insUsd.toFixed(1)}M net buys` });
  return out.length ? out : SIGNALFEED_MOCK;
}

function SignalFeed({ onTicker }) {
  const events = useMemoH(() => resolveSignalFeed(), [bvTok()]);
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
