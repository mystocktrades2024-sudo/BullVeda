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
  // active horizon → decisions_by_mode key
  function modeKey(mode) {
    const m = String(mode || window.__tmode || "swing").toLowerCase();
    return m.indexOf("pos") === 0 ? "position" : m.indexOf("inv") === 0 ? "investment" : "swing";
  }
  // per-mode engine verdict (BUY/WATCH/AVOID/SHORT) for a scan row — so Home sections
  // respect the Swing/Position/Invest toggle instead of always showing the overall call.
  function mdec(row, mode) {
    const dbm = row && row._raw && row._raw.decisions_by_mode;
    return (dbm && dbm[modeKey(mode)]) || null;
  }
  function vmode(row, mode) {
    const d = mdec(row, mode);
    return String((d && d.verdict) || (row && row.verdict) || "").toUpperCase();
  }
  return { num, numStr, sym0, rows, pool, ledgerSet, ledgerReal, auditOnly, inAudit, findRow, held, modeKey, vmode, mdec, has: () => rows().length > 0 };
})();

function HomeView({ onTicker, onSurface, mode, surface }) {
  const uni = (window.__BV && window.__BV.market && window.__BV.market.funnel && window.__BV.market.funnel.universe) || null;
  // "TODAY'S SCAN" must reflect the LIVE scan rows — not a stale critical-bundle
  // count. When the live universe is empty, show "—" so the label matches the
  // honest-empty setups/discovery below it (instead of "1000 ranked · 0 setups").
  const uniStr = (uni != null && HR.has()) ? uni.toLocaleString() : (window.__BV ? "—" : "612");
  const liveDown = !HR.has();  // live universe empty → sections fall back to a placeholder layout
  // Real "as of" stamp from the last scan bundle (same source the hero uses).
  const _sm = (window.__BV && window.__BV.scanMeta) || null;
  const _asOf = _sm && _sm.ts ? String(_sm.ts) + " PT" : "the last scan";
  return (
    <div className="home">
      {liveDown && (
        <div className="home-feed-warn mono" style={{
          margin: "0 0 10px", padding: "10px 14px", borderRadius: 10, fontSize: 12.5, lineHeight: 1.5,
          background: "color-mix(in oklab, var(--amb) 12%, var(--bg-1))",
          border: "1px solid color-mix(in oklab, var(--amb) 42%, transparent)", color: "var(--ink-1)",
        }}>
          <b className="amb">DATA AS OF {_asOf}</b> — the latest scan returned no live names yet, so the
          tickers and prices below are a <b>placeholder layout, not real values</b>. They refresh
          automatically once the next scan lands.
        </div>
      )}
      {/* TIER 1 · MARKET STATE — cross-asset tape (above the hero), then regime + scan funnel */}
      <IndexStrip />
      <HomeHero mode={mode} onSurface={onSurface} />

      {/* TIER 1.6 · AUTOMATED BOOK — the system's auto-traded paper account, shared
          across all viewers (NOT the individual user's book). Per-user position
          tracking isn't wired; this is the model/track-record portfolio. */}
      {(window.__BV && window.__BV.portfolio && (window.__BV.portfolio.positions || []).length > 0) && (
        <>
          <div className="home-sec-label"><span className="mono">AUTOMATED BOOK · LIVE P&L</span><span className="mono dim2">system paper account · auto-traded · same for every viewer · click to open ticket</span></div>
          <BookStrip onTicker={onTicker} />
        </>
      )}

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
        <HomeCard title="Market movers" sub="trending · most active · in-scan universe" cta="Scanner →" onCta={() => onSurface && onSurface("signal-scanner")}>
          <MarketMovers onTicker={onTicker} onSurface={onSurface} />
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
function resolveIndexStrip(liveIq) {
  const BV = window.__BV;
  const n = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
  const fmt = (v, dp = 2) => v == null ? "—" : v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(dp);
  const out = [];
  const have = new Set();
  const push = (s, v, c2, spark) => { if (v != null && v !== "—" && !have.has(s)) { out.push({ s, v, c: c2, spark: spark || null }); have.add(s); } };
  // ── TRUE headline tape — Schwab indices/yields/ETFs + EODHD crypto + Stooq futures ──
  const iq = liveIq || (BV && BV.indexQuotes) || null;
  if (iq && iq.length) {
    iq.forEach(q => {
      if (!q || q.value == null) return;
      const v = q.suffix === "%" ? (q.value.toFixed(2) + "%") : fmt(q.value);
      push(q.label, v, q.chg != null ? q.chg : null, q.spark_sym);
    });
  }
  // ── FX from bonds_forex (real daily change_p); dollar/credit/30Y now come from
  //    index_quotes as real-daily Schwab ETFs, so they're not re-added here ──
  const c = (BV && BV.critical) || null;
  if (c) {
    const bf = c.bonds_forex || {};
    const bfc = (k) => bf[k] ? n(bf[k].change_p) : null;
    if (bf["EURUSD.FOREX"]) push("EUR/USD", fmt(n(bf["EURUSD.FOREX"].price), 4), bfc("EURUSD.FOREX"), "EURUSD.FOREX");
    if (bf["USDJPY.FOREX"]) push("USD/JPY", fmt(n(bf["USDJPY.FOREX"].price), 2), bfc("USDJPY.FOREX"), "USDJPY.FOREX");
  }
  return out.length >= 4 ? out : (window.__BV ? out : IDXSTRIP_MOCK.map(m => ({ ...m, spark: null })));
}
function IndexStrip() {
  const { useState: uS, useEffect: uE } = React;
  const [liveIq, setLiveIq] = uS(null);
  const [sparks, setSparks] = uS({});
  const [age, setAge] = uS(0);
  const idx = useMemoH(() => resolveIndexStrip(liveIq), [bvTok(), liveIq]);
  const sparkKey = idx.map(i => i.spark).filter(Boolean).join(",");
  // poll live quotes every 60s (boot snapshot → ticking tape)
  uE(() => {
    const BV = window.__BV; if (!BV || !BV.get) return;
    let alive = true, tLast = Date.now();
    const tick = () => BV.get("/api/index-quotes").then(d => { if (alive && d && d.index_quotes && d.index_quotes.length) { setLiveIq(d.index_quotes); tLast = Date.now(); } }).catch(() => {});
    tick(); // immediate first poll so the tape reflects live truth, not the stale boot snapshot
    const iv = setInterval(tick, 60000);
    const ageIv = setInterval(() => { if (alive) setAge(Math.round((Date.now() - tLast) / 1000)); }, 5000);
    return () => { alive = false; clearInterval(iv); clearInterval(ageIv); };
  }, []);
  // real daily-close sparklines for the tile symbols (fetched once; server caches 30m)
  uE(() => {
    const BV = window.__BV; if (!BV || !BV.get || !sparkKey) return;
    let alive = true;
    BV.get("/api/spark?syms=" + encodeURIComponent(sparkKey)).then(d => { if (alive && d && d.sparks) setSparks(s => ({ ...s, ...d.sparks })); }).catch(() => {});
    return () => { alive = false; };
  }, [sparkKey]);
  // One tile (rendered twice — once per marquee half — for a seamless loop).
  const tile = (i, k) => {
    const series = i.spark ? sparks[i.spark] : null;
    const up = i.c == null ? true : i.c >= 0;
    const isCommodity = ["WTI", "GOLD", "COPPER", "SILVER"].includes(i.s);
    const tip = i.spark ? (isCommodity
      ? `value = front-month future · sparkline tracks the ${i.spark} ETF (closest free proxy path)`
      : `sparkline: ${i.spark} · 22 daily closes`) : undefined;
    return (
      <div key={k} className={`ix ix--${i.c == null ? "ink" : up ? "gn" : "rd"}`} title={tip}>
        <span className="ix-s mono">{i.s}</span>
        <span className="ix-v mono">{i.v}</span>
        {i.c != null
          ? <span className={`ix-c mono ${up ? "up" : "dn"}`}>{i.c >= 0 ? "+" : ""}{i.c.toFixed(2)}%</span>
          : <span className="ix-c mono dim2">—</span>}
        {series && series.length >= 3
          ? <Sparkline data={series} color={`var(--${up ? "gn" : "rd"})`} w={48} h={20} />
          : <span style={{ width: 48, height: 20, display: "inline-block" }} />}
      </div>
    );
  };
  // Seamless marquee: each of the two halves must be at least as wide as the
  // widest plausible viewport, else a short tape (few live tiles) leaves a blank
  // gap on the right. Repeat the tile set enough times to fill ~3000px per half.
  const TILE_W = 179; // 178px tile + 1px gap
  const setW = Math.max(1, idx.length * TILE_W);
  const reps = idx.length ? Math.max(1, Math.ceil(3000 / setW)) : 1;
  const half = []; // reps copies of the tile set, keys unique within the half
  for (let r = 0; r < reps; r++) idx.forEach((i, k) => half.push(tile(i, r * 1000 + k)));
  // constant scroll speed (~70px/s) regardless of how many tiles are live
  const dur = Math.max(18, Math.round((reps * setW) / 70));
  // ── staleness / partial-feed detection (informational only — never fakes a tile) ──
  // A healthy tape carries the Schwab headline indices; when Schwab auth lapses those
  // (and the commodity ETF proxies) drop, leaving only crypto + FX. Surface it so the
  // feed degrades loudly instead of silently. Stale = live poll dead for 10m+.
  const hasCore = idx.some(i => ["S&P 500", "NASDAQ", "VIX"].includes(i.s));
  const partial = idx.length > 0 && !hasCore;
  const stale = !partial && age >= 600;
  const warn = partial
    ? { kind: "partial", msg: "TAPE PARTIAL — index & commodity quotes unavailable (Schwab auth likely expired); showing crypto + FX only.", fix: "python3 schwab_auth.py oauth" }
    : stale
      ? { kind: "stale", msg: `TAPE STALE — live quotes haven't refreshed in ${Math.round(age / 60)}m; the feed may be rate-limited.`, fix: null }
      : null;
  return (
    <>
    {warn && (
      <div className={`ix-warn ix-warn--${warn.kind} mono`} role="status">
        <span className="ix-warn-i">⚠</span>
        <span className="ix-warn-t">{warn.msg}{warn.fix ? <> · fix: <code className="ix-warn-cmd">{warn.fix}</code></> : null}</span>
      </div>
    )}
    <div className="ix-strip ix-strip--marquee">
      <div className="ix ix--ink ix-live" title={`Live tape · refreshed ${age < 5 ? "now" : age + "s ago"}`}>
        <span className="ix-s mono" style={{ color: "var(--gn)" }}>● LIVE</span>
        <span className="ix-v mono dim2">{age < 90 ? "tape" : "delayed"}</span>
      </div>
      <div className="ix-viewport">
        <div className="ix-track" style={{ animationDuration: `${dur}s` }}>
          <div className="ix-group">{half}</div>
          <div className="ix-group" aria-hidden="true">{half}</div>
        </div>
      </div>
    </div>
    </>
  );
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
    { k: "F&G proxy", v: M.fearGreed != null ? String(M.fearGreed) : "—", tone: "gn" },
    { k: "Put/Call", v: M.putCall != null ? M.putCall.toFixed(2) : "—", tone: "amb" },
  ] : (window.__BV ? [
    { k: ">50-DMA", v: "—", tone: "ink" }, { k: ">200-DMA", v: "—", tone: "ink" },
    { k: "New highs", v: "—", tone: "ink" }, { k: "New lows", v: "—", tone: "ink" },
    { k: "F&G proxy", v: "—", tone: "ink" }, { k: "Put/Call", v: "—", tone: "ink" },
  ] : [
    { k: ">50-DMA", v: "62%", tone: "gn" }, { k: ">200-DMA", v: "58%", tone: "gn" },
    { k: "A/D line", v: "+1,240", tone: "gn" }, { k: "New H–L", v: "+86", tone: "gn" },
    { k: "VIX", v: "16.3", tone: "gn" }, { k: "Put/Call", v: "0.82", tone: "amb" },
  ]);
  // gappers — biggest movers from the live universe (audit-log intersected)
  const gappers = useMemoH(() => {
    const rows = HR.pool();
    if (!rows.length) return window.__BV ? [] : [
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
    // served → honest empty; standalone showcase → demo calendar
    return window.__BV ? [] : [
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
// How many of the top headlines the MARKETS·NEWS board consumes (featured + left
// stack + latest). The TIER-3 "Top stories" card starts AFTER this so the two
// surfaces never show the same headline twice.
const NEWS_BOARD_TAKE = 11;
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

// ─── Earnings Today ──────────────────────────────────────────────
const EARNINGS_MOCK = [
  { sym: "CRWV", when: "BMO", time: "today", beat: 71, tier: "SOLID",  tone: "amb", held: false },
  { sym: "GENO", when: "AMC", time: "today", beat: 64, tier: "SOLID",  tone: "amb", held: false },
  { sym: "TURM", when: "AMC", time: "today", beat: 48, tier: "WEAK",   tone: "rd",  held: false },
  { sym: "BORA", when: "AMC", time: "today", beat: 82, tier: "STRONG", tone: "gn",  held: true },
];

function resolveEarningsToday() {
  const eb = (window.__BV && window.__BV.earningsBeat) || [];
  if (!eb.length) return window.__BV ? [] : EARNINGS_MOCK;
  const held = HR.held();
  const tierTone = (t) => /strong/i.test(t) ? "gn" : /solid/i.test(t) ? "amb" : "rd";
  const today = eb.filter(e => e.ticker && HR.num(e.days_to_earnings, 99) <= 1);
  const src = (today.length ? today : eb).slice(0, 6)
    .sort((a, b) => (b.beat_score || 0) - (a.beat_score || 0));
  return src.map(e => {
    const sym = HR.sym0(e.ticker);
    const d = HR.num(e.days_to_earnings, null);
    const im = ((e.breakdown || {}).implied_move || {});
    const imp = HR.num(im.implied_move_pct, null);  // real Schwab straddle-implied move
    return {
      sym, when: /before/i.test(e.before_after || "") ? "BMO" : "AMC",
      time: d === 0 ? "today" : d != null ? "T−" + d : "",
      beat: e.beat_score != null ? Math.round(e.beat_score) : null,
      imp: imp != null ? "±" + imp.toFixed(1) + "%" : null,
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
        <span> · implied move + beat-score</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className={`et-row ${r.held ? "is-held" : ""}`} onClick={() => onTicker(r.sym)}>
          <span className="et-sym mono"><b>{r.sym}</b></span>
          <span className={`et-when mono ${r.when === "BMO" ? "cy" : "amb"}`}>{r.when}</span>
          <span className="et-time mono dim2">{r.time}</span>
          <span className="et-move mono warn" title="options-implied move (Schwab ATM straddle)">{r.imp || "—"}</span>
          <span className={`et-esp mono kpi-tone--${r.tone}`}>{r.tier ? r.tier + (r.beat != null ? " " + r.beat : "") : (r.beat != null ? "BEAT " + r.beat : "—")}</span>
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
  if (!rows.length) return window.__BV ? [] : DISCOVERY_MOCK;
  const pick = (arr, n) => HR.auditOnly(arr.map(x => x[0]).slice(0, n + 4))
    .slice(0, n).map(s => { const o = arr.find(a => a[0] === s); return o ? [o[0], o[1]] : [s, ""]; });
  const hi = rows.filter(r => r.off52 != null && r.off52 >= -3 && HR.num(r.chg, null) != null)
    .sort((a, b) => b.off52 - a.off52).map(r => [r.sym, (r.chg >= 0 ? "+" : "") + r.chg.toFixed(1)]);
  const sq = rows.filter(r => r.sqRank >= 1).sort((a, b) => b.sqRank - a.sqRank || b.score - a.score)
    .map(r => [r.sym, String(r.squeeze).toUpperCase()]);
  // insider $-value (total_buy_value) is never populated by the feed — the real
  // signal is the net buy count (insider_net = buys − sells), which IS populated.
  const ins = rows.filter(r => HR.num(r.insNet, 0) > 0).sort((a, b) => b.insNet - a.insNet)
    .map(r => [r.sym, "+" + r.insNet + " net"]);
  const of = (window.__BV && window.__BV.optionsFlow) || [];
  const uoa = of.filter(o => o.ticker).sort((a, b) => (b.uoa_calls || 0) - (a.uoa_calls || 0))
    .map(o => [HR.sym0(o.ticker), o.status || "UOA"]);
  const emg = rows.filter(r => HR.vmode(r) === "WATCH" && r.score >= 55).sort((a, b) => b.score - a.score)
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
  return filled.length ? groups.map(g => g.items.length ? g : { ...g, items: [] }) : (window.__BV ? [] : DISCOVERY_MOCK);
}

function Discovery({ onTicker }) {
  const groups = useMemoH(() => resolveDiscovery(), [bvTok()]).filter(g => g.items.length);
  if (!groups.length) return <div className="disc"><span className="mono dim2">No discovery signals yet — waiting on today's scan.</span></div>;
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
const bvTok = () => (HR.has() ? 1 : 0) + (HR.ledgerReal() ? 2 : 0) + (window.AIPredict && window.AIPredict.all ? 4 : 0)
  + (window.__tmode === "position" ? 100 : window.__tmode === "investment" ? 200 : 0);

// Scan funnel computed from the SAME per-mode engine verdicts the scanner/TopSetups
// read (decisions_by_mode), so the hero funnel can't disagree with the rest of Home.
// (critical.buy_count drifts from the per-row verdicts — e.g. says "9 bullish" while
// every row's swing verdict is WATCH/AVOID.) Falls back to BV.market.funnel.
function realFunnel(mode) {
  const rows = HR.rows();
  if (!rows.length) return null;
  const m = String(mode || window.__tmode || "swing").toLowerCase();
  const key = m.indexOf("pos") === 0 ? "position" : m.indexOf("inv") === 0 ? "investment" : "swing";
  let bull = 0, neu = 0, bear = 0;
  rows.forEach(r => {
    const dbm = (r._raw && r._raw.decisions_by_mode) || null;
    const v = String((dbm && dbm[key] && dbm[key].verdict) || r.verdict || "").toUpperCase();
    if (v === "BUY") bull++;
    else if (v === "SHORT" || v === "AVOID" || v === "SELL") bear++;
    else neu++;
  });
  return { universe: rows.length, bullish: bull, neutral: neu, bearish: bear };
}

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
    const r = rows.filter(x => HR.num(x.insNet, 0) > 0).sort((a, b) => b.insNet - a.insNet)
      .map(x => [x.sym, "+" + x.insNet]);
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
  const live = HR.has() || !!(typeof window !== "undefined" && window.__BV); // served → honest empty, never curated
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
  if (!rows.length) return window.__BV ? [] : SCANNER_PICKS;
  const rank = (v) => v === "BUY" ? 0 : v === "WATCH" ? 1 : v === "SHORT" ? 2 : 3;
  // per-mode verdict/score/R:R (Swing/Position/Invest) from decisions_by_mode —
  // so the WHOLE row reflects the active horizon, not a swing call with swing R:R.
  const picks = [...rows]
    .map(r => ({ r, d: HR.mdec(r), vm: HR.vmode(r) }))
    .filter(x => ["BUY", "WATCH", "SHORT"].includes(x.vm) && HR.inAudit(x.r.sym))
    .sort((a, b) => {
      const sa = (a.d && HR.num(a.d.composite_score, a.r.score)) || a.r.score;
      const sb = (b.d && HR.num(b.d.composite_score, b.r.score)) || b.r.score;
      return rank(a.vm) - rank(b.vm) || sb - sa;
    })
    .slice(0, 5)
    .map(({ r, d, vm }) => {
      const modeRR = d && HR.num(d.rr_ratio, null);
      const modeScore = d && HR.num(d.composite_score, null);
      return {
        sym: r.sym, name: r.name,
        score: modeScore != null ? Math.round(modeScore) : r.score,
        rr: modeRR != null ? modeRR.toFixed(1) : (r.rr !== "—" ? r.rr : null),
        wlb: r.wlb,  // feed-honest (null → "—")
        edge: r.aiEdge != null ? (r.aiEdge >= 0 ? "+" : "") + r.aiEdge.toFixed(2) : null,
        v: vm,
      };
    });
  return picks.length ? picks : (window.__BV ? [] : SCANNER_PICKS);
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
  const anyBuy = rows.some(r => r.v === "BUY");
  if (!rows.length) return <div className="tset"><div className="tset-note mono dim2" style={{ padding: "8px" }}>No setups yet — waiting on today's scan bundle.</div></div>;
  return (
    <div className="tset">
      {!anyBuy && HR.has() && (
        <div className="tset-note mono dim2" style={{ padding: "4px 8px", fontSize: 11, opacity: .75 }}>
          No fresh BUYs in {String(window.__tmode || "swing").toLowerCase()} — every name is extended past its value zone. Top watchlist by score:
        </div>
      )}
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
  const stories = realStories(99);
  const toStory = (s, live) => ({
    head: s.head, src: s.src, time: s.t, url: s.url, live: !!live, sum: s.sum, sym: s.sym, tone: s.tone,
    tickers: (s.tickers && s.tickers.length) ? s.tickers : (s.sym ? [[s.sym, 0]] : []),
  });
  let featured = null, leftStack = null, latest = null, catalysts = null;
  if (stories && stories.length) {
    featured = toStory(stories[0], true);
    leftStack = stories.slice(1, 5).map(s => toStory(s));
    latest = stories.slice(5, NEWS_BOARD_TAKE).map(s => toStory(s));
    // Col 3 — stock-specific catalysts BELOW the headline cut (named tickers
    // preferred), so the board never repeats a headline already shown in cols 1-2.
    const seen = new Set(stories.slice(0, NEWS_BOARD_TAKE).map(s => s.head));
    const rest = stories.filter(s => !seen.has(s.head));
    const named = rest.filter(s => s.sym);
    const pick = (named.length >= 3 ? named : rest).slice(0, 6);
    catalysts = pick.map(s => toStory(s));
  }
  return { featured, leftStack, latest, catalysts };
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
  // Col 3 — stock-specific catalyst headlines (real, from the news feed). Served →
  // honest [] when none remain beyond the headline cut; mock only in standalone preview.
  const catalysts = real.catalysts || (window.__BV ? [] : [
    { head: "Specialty-materials names see insider buying cluster", src: "Barron's", time: "2h", sym: "ARGN", tone: "gn", tickers: [["ARGN", +2.1]] },
    { head: "Genoa Bio Phase-2 readout expected ahead of next-week print", src: "FierceBio", time: "16m", sym: "GENO", tone: "gn", tickers: [["GENO", +0.5]] },
    { head: "Lithium names rebound on supply-cut headlines out of Chile", src: "Reuters", time: "1h", sym: "LAC", tone: "gn", tickers: [["LAC", +5.8]] },
    { head: "Software multiples compress as Street trims FY estimates", src: "Bloomberg", time: "2h", sym: "MDB", tone: "rd", tickers: [["MDB", -4.4]] },
  ]);
  // sentiment label from EODHD story tone (gn/rd/amb). Honest to the feed — note
  // most "Is X a good buy" headlines score positive, so BULLISH dominates until
  // genuine negative news flows.
  const SENT = { gn: "BULLISH", rd: "BEARISH", amb: "NEUTRAL" };
  const Story = ({ s, big }) => {
    const tone = s.tone || "amb";
    return (
    <button className={`nm-story nm-story--t-${tone} ${big ? "nm-story--big" : ""}`} onClick={() => s.tickers[0] && onTicker(s.tickers[0][0])}>
      {big && <div className="nm-feat-img"><span className="mono">◧ MARKETS</span></div>}
      <div className="nm-head">{s.head}</div>
      <div className="nm-meta mono">
        {s.live && <span className="nm-live">● LIVE</span>}
        <span className={`nm-sent nm-sent--${tone}`} title="News sentiment (EODHD)">{SENT[tone]}</span>
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
  };
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
      <div className="nm-col nm-col--cat">
        <div className="nm-col-h mono">STOCK CATALYSTS</div>
        <div className="nm-feed">
          {catalysts.length
            ? catalysts.map((s, i) => <Story key={i} s={s} />)
            : <div className="nm-cat-empty mono dim2">No stock-specific catalysts beyond the headlines.</div>}
        </div>
      </div>
    </div>
  );
}

// ─── Market movers — trending + most-active rails (moved out of the news board) ──
function MarketMovers({ onTicker, onSurface }) {
  const { trending, gainers } = useMemoH(() => {
    const rows = HR.pool();
    if (!rows.length) return { trending: [], gainers: [] };
    const px = (p) => p >= 1000 ? Math.round(p).toLocaleString() : p.toFixed(2);
    const audited = rows.filter(r => HR.inAudit(r.sym) && HR.num(r.chg, null) != null && HR.num(r.price, null) != null);
    const trending = [...audited].sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 5)
      .map(r => ({ sym: r.sym, name: r.name, px: px(r.price), chg: r.chg }));
    // "Most active" by dollar-volume — a distinct metric from the Top-movers card (by %).
    const gainers = [...audited].filter(r => HR.num(r.dvol, null) != null).sort((a, b) => b.dvol - a.dvol).slice(0, 5)
      .map(r => ({ sym: r.sym, name: r.name, px: px(r.price), chg: r.chg, dvol: r.dvol }));
    return { trending, gainers };
  }, [bvTok()]);
  const [trendSparks, setTrendSparks] = React.useState({});
  const trendKey = trending.map(r => r.sym).join(",");
  React.useEffect(() => {
    const BV = window.__BV; if (!BV || !BV.get || !trendKey) return;
    let alive = true;
    BV.get("/api/spark?syms=" + encodeURIComponent(trendKey)).then(d => { if (alive && d && d.sparks) setTrendSparks(s => ({ ...s, ...d.sparks })); }).catch(() => {});
    return () => { alive = false; };
  }, [trendKey]);
  if (!trending.length && !gainers.length)
    return <div className="nm-cat-empty mono dim2">No movers in the live scan yet.</div>;
  return (
    <div className="mv-wrap">
      <div className="nm-rail-card">
        <div className="nm-rail-h mono"><span>TRENDING TICKERS</span><span className="nm-rail-go" onClick={() => onSurface && onSurface("signal-scanner")}>Scanner →</span></div>
        {trending.map((r, i) => {
          const series = trendSparks[r.sym];
          return (
          <button key={i} className="nm-row" onClick={() => onTicker(r.sym)}>
            <span className="nm-row-l"><b className="nm-row-sym mono">{r.sym}</b><span className="nm-row-name dim2">{r.name}</span></span>
            {series && series.length >= 3
              ? <Sparkline data={series} color={`var(--${r.chg >= 0 ? "gn" : "rd"})`} w={52} h={20} />
              : <span style={{ width: 52, height: 20, display: "inline-block" }} />}
            <span className="nm-row-r"><span className="nm-row-px mono">{r.px}</span><span className={`nm-row-chg mono ${r.chg >= 0 ? "up" : "dn"}`}>{r.chg >= 0 ? "+" : ""}{r.chg.toFixed(2)}%</span></span>
          </button>
          );
        })}
      </div>
      <div className="nm-rail-card">
        <div className="nm-rail-h mono"><span>MOST ACTIVE</span><span className="nm-rail-go" onClick={() => onSurface && onSurface("momentum")}>Movers →</span></div>
        {gainers.map((r, i) => {
          const dv = r.dvol != null ? (r.dvol >= 1e9 ? "$" + (r.dvol / 1e9).toFixed(1) + "B" : "$" + Math.round(r.dvol / 1e6) + "M") : null;
          return (
          <button key={i} className="nm-row nm-row--g" onClick={() => onTicker(r.sym)}>
            <span className="nm-row-l"><b className="nm-row-sym mono">{r.sym}</b><span className="nm-row-name dim2">{dv || r.name}</span></span>
            <span className="nm-row-r"><span className="nm-row-px mono">{r.px}</span><span className={`nm-row-chg mono ${r.chg >= 0 ? "up" : "dn"}`}>{r.chg >= 0 ? "+" : ""}{r.chg.toFixed(1)}%</span></span>
          </button>
          );
        })}
      </div>
    </div>
  );
}

// Fear/Greed → tone. Low = fear (red), ~50 = neutral (amber), high = greed (green).
// Was hardcoded "gn"/"up" everywhere so 50 rendered green regardless of value.
function fgTone(v) {
  if (v == null) return "amb";
  if (v >= 55) return "gn";
  if (v >= 45) return "amb";
  return "rd";
}
function fgClass(v) {
  const t = fgTone(v);
  return t === "gn" ? "up" : t === "rd" ? "dn" : "amb";
}

function HomeHero({ mode, onSurface }) {
  const go = (id) => () => onSurface && onSurface(id);
  const scan = (f) => () => { window.__scanFilter = f; go("signal-scanner")(); };
  const M = (window.__BV && window.__BV.market) || null;
  // funnel from the live per-mode verdicts (consistent with TopSetups/Discovery);
  // falls back to the critical funnel only when no live universe is loaded.
  const F = realFunnel(mode) || (M ? M.funnel : null);
  const SV = !!(typeof window !== "undefined" && window.__BV); // served (real deploy) → no demo numbers
  const buy = F ? F.bullish : (SV ? 0 : 14), watch = F ? F.neutral : (SV ? 0 : 8), avoid = F ? F.bearish : (SV ? 0 : 31);
  const universe = F ? F.universe : (SV ? 0 : 612);
  const flagged = buy + watch + avoid || 1;
  const seg = (n) => `${(n / flagged) * 100}%`;
  const mood = [
    { l: "FEAR/GREED", v: M && M.fearGreed != null ? String(M.fearGreed) : (SV ? "—" : "62"), tone: fgTone(M && M.fearGreed != null ? M.fearGreed : 62), pct: M && M.fearGreed != null ? M.fearGreed : (SV ? 0 : 62) },
    { l: "BREADTH",    v: M && M.breadthPct != null ? Math.round(M.breadthPct) + "%" : (SV ? "—" : "56%"), tone: "gn", pct: M && M.breadthPct != null ? Math.round(M.breadthPct) : (SV ? 0 : 56) },
    { l: "PUT/CALL",   v: M && M.putCall != null ? M.putCall.toFixed(2) : (SV ? "—" : "0.78"), tone: "gn", pct: SV && !(M && M.putCall != null) ? 0 : 60 },
    { l: "NEW HIGHS",  v: M && M.newHighs != null ? String(M.newHighs) : "—", tone: "gn", pct: 50 },
    { l: ">200-DMA",   v: M && M.breadth200 != null ? Math.round(M.breadth200) + "%" : "—", tone: "gn", pct: M && M.breadth200 != null ? Math.round(M.breadth200) : 55 },
    { l: "MAX SIZE",   v: M && M.maxSize != null ? M.maxSize + "%" : (SV ? "—" : "70%"), tone: "amb", pct: M && M.maxSize != null ? M.maxSize : (SV ? 0 : 70) },
  ];
  const regOn = M && M.regimeLabel ? M.regimeLabel : (SV ? "—" : "RISK-ON");
  const regTrend = M && M.regimeTrend ? M.regimeTrend : (SV ? "" : "CHOPPY");
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
          <span className="qh-regime-v mono"><b className={regOn === "—" ? "dim2" : regOn === "RISK-ON" ? "up" : "dn"}>{regOn}</b>{regTrend ? <><span className="qh-sep">·</span><b className="amb">{regTrend}</b></> : null}</span>
          <span className="qh-regime-wr mono dim2">multi-factor{M && M.maxSize != null ? ` · max size ${M.maxSize}%` : ""}</span>
        </button>

        <div className="qh-funnel">
          <div className="qh-cap mono">SCAN FUNNEL <span className="dim2">· {universe} ranked → {flagged} flagged</span></div>
          <div className="qh-funnel-bar">
            <i className="qh-seg qh-seg--gn"  style={{ width: seg(buy) }}   title={`${buy} Bullish`} />
            <i className="qh-seg qh-seg--amb" style={{ width: seg(watch) }} title={`${watch} Neutral`} />
            <i className="qh-seg qh-seg--rd"  style={{ width: seg(avoid) }} title={`${avoid} Avoid (excluded from longs)`} />
          </div>
          <div className="qh-funnel-stats">
            <button className="qh-fstat qh-fstat--copper" onClick={scan("ALL")}   title="Scanner · all"><b>{universe}</b><span>universe</span></button>
            <button className="qh-fstat qh-fstat--gn"     onClick={scan("BUY")}   title="Scanner · Bullish"><b>{buy}</b><span>bullish</span></button>
            <button className="qh-fstat qh-fstat--amb"    onClick={scan("WATCH")} title="Scanner · Neutral"><b>{watch}</b><span>neutral</span></button>
            <button className="qh-fstat qh-fstat--rd"     onClick={scan("SHORT")} title="Scanner · Avoid — excluded from longs (not necessarily shortable)"><b>{avoid}</b><span>avoid</span></button>
          </div>
        </div>

        <div className="qh-mood">
          <div className="qh-cap mono">MARKET MOOD</div>
          <div className="qh-mood-row">
            {mood.map((m, i) => (
              <div key={i} className={`qh-m qh-m--${m.tone}`} title={m.l === "FEAR/GREED" ? "Computed proxy from breadth + put/call (not the CNN Fear & Greed index)" : undefined}>
                <span className="qh-m-l mono">{m.l === "FEAR/GREED" ? "F&G PROXY" : m.l}</span>
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
        {M.fearGreed != null ? <> · Fear/Greed <b className={fgClass(M.fearGreed)}>{M.fearGreed}</b></> : null}
        {M.breadthPct != null ? <> · breadth <b>{Math.round(M.breadthPct)}%</b></> : null}
        {vix != null ? <> · VIX <b>{vix.toFixed(1)}</b></> : null}
        {spyChg != null ? <> · SPY <b className={spyChg >= 0 ? "up" : "dn"}>{spyChg >= 0 ? "+" : ""}{spyChg.toFixed(1)}%</b></> : null}
        {dist ? <> · <b className="dim2">{dist}</b></> : null}.
      </span>
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

// ─── Automated Book — REAL open positions from the shared auto-traded Alpaca
//     paper account (system model portfolio · same for every viewer · NOT the
//     individual user's book — per-user position tracking is not wired). ──────
function BookStrip({ onTicker }) {
  const pf = (window.__BV && window.__BV.portfolio) || null;
  if (!pf) return null;
  const positions = (pf.positions || []).slice();
  const num = (v) => (typeof v === "number" && isFinite(v)) ? v : (parseFloat(v) || 0);
  const money = (v) => (v < 0 ? "−$" : "$") + Math.abs(Math.round(num(v))).toLocaleString();
  const openPnl = positions.reduce((a, p) => a + num(p.unrealized_pnl_dollars), 0);
  const equity = num(pf.equity), cash = num(pf.cash);
  const openPct = equity ? (openPnl / equity) * 100 : null;
  const tone = openPnl >= 0 ? "gn" : "rd";
  positions.sort((a, b) => Math.abs(num(b.unrealized_pnl_dollars)) - Math.abs(num(a.unrealized_pnl_dollars)));
  return (
    <div className="ap-strip">
      {/* book summary tile */}
      <div className="ap-card ap-card--ink">
        <div className="ap-hdr">
          <span className="mono ap-sym"><b>NAV</b></span>
          <span className={`mono ap-pl kpi-tone--${tone}`}>{openPnl >= 0 ? "+" : ""}{money(openPnl)}</span>
        </div>
        <div className="ap-meta mono dim2">{positions.length} open · {pf.config_label || "Alpaca paper"}</div>
        <div className="ap-bars">
          <div className="ap-bar"><div className="ap-bar-l label-cap">Equity</div><div className="ap-bar-v mono">{money(equity)}</div></div>
          <div className="ap-bar"><div className="ap-bar-l label-cap">Open P&L</div><div className={`ap-bar-v mono kpi-tone--${tone}`}>{openPct != null ? (openPct >= 0 ? "+" : "") + openPct.toFixed(2) + "%" : "—"}</div></div>
          <div className="ap-bar"><div className="ap-bar-l label-cap">Cash</div><div className="ap-bar-v mono">{money(cash)}</div></div>
          <div className="ap-bar"><div className="ap-bar-l label-cap">Slots</div><div className="ap-bar-v mono">{pf.open_count != null ? pf.open_count : positions.length}/{pf.max_positions != null ? pf.max_positions : "—"}</div></div>
        </div>
      </div>
      {positions.map(p => {
        const pnl = num(p.unrealized_pnl_dollars), pct = num(p.unrealized_pnl_pct);
        const t = pnl >= 0 ? "gn" : "rd";
        const short = String(p.direction || "").toLowerCase() === "short" || num(p.signed_qty) < 0;
        const last = num(p.current_price), entry = num(p.entry_price), stop = num(p.stop);
        const stopDist = (last && stop) ? ((short ? (stop - last) : (last - stop)) / last) * 100 : null;
        return (
          <button key={p.ticker} className={`ap-card ap-card--${t}`} onClick={() => onTicker && onTicker(p.ticker)}>
            <div className="ap-hdr">
              <span className="mono ap-sym"><b>{p.ticker}</b> <span className={`mono ${short ? "dn" : "up"}`} style={{ fontSize: 10 }}>{short ? "SHORT" : "LONG"}</span></span>
              <span className={`mono ap-pl kpi-tone--${t}`}>{pnl >= 0 ? "+" : ""}{money(pnl)}</span>
            </div>
            <div className="ap-meta mono dim2">{Math.abs(num(p.shares))} sh · {p.days_held != null ? "held " + p.days_held + "d" : (p.setup_type || "")}</div>
            <div className="ap-bars">
              <div className="ap-bar"><div className="ap-bar-l label-cap">Open %</div><div className={`ap-bar-v mono kpi-tone--${t}`}>{pct ? (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%" : "—"}</div></div>
              <div className="ap-bar"><div className="ap-bar-l label-cap">Stop dist</div><div className={`ap-bar-v mono ${stopDist != null && stopDist >= 0 ? "up" : "dn"}`}>{stopDist != null ? (stopDist >= 0 ? "+" : "") + stopDist.toFixed(1) + "%" : "—"}</div></div>
              <div className="ap-bar"><div className="ap-bar-l label-cap">Entry</div><div className="ap-bar-v mono">{entry ? "$" + entry.toFixed(2) : "—"}</div></div>
              <div className="ap-bar"><div className="ap-bar-l label-cap">Last</div><div className="ap-bar-v mono">{last ? "$" + last.toFixed(2) : "—"}</div></div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
window.BookStrip = BookStrip;

window.HomeView = HomeView;

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
  // Served (real) mode: never fall back to the demo feed — return honest empty
  // so 500 viewers don't see fabricated ARGN/ARCM signals during a scan outage.
  // The SIGNALFEED_MOCK is the standalone-showcase default only (no window.__BV).
  const SERVED = !!(typeof window !== "undefined" && window.__BV);
  const rows = HR.pool();
  if (!rows.length) return SERVED ? [] : SIGNALFEED_MOCK;
  const inA = (r) => HR.inAudit(r.sym);
  const buys = rows.filter(r => HR.vmode(r) === "BUY" && inA(r)).sort((a, b) => b.score - a.score);
  const ins = rows.filter(r => HR.num(r.insNet, 0) > 0 && inA(r)).sort((a, b) => b.insNet - a.insNet);
  const er = rows.filter(r => HR.num(r.er, 99) <= 9 && HR.num(r.er, 99) >= 0 && inA(r)).sort((a, b) => a.er - b.er);
  const bear = rows.filter(r => { const v = HR.vmode(r); return (v === "SHORT" || v === "AVOID") && inA(r); }).sort((a, b) => a.score - b.score);
  const ai = rows.filter(r => r.aiEdge != null && inA(r)).sort((a, b) => b.aiEdge - a.aiEdge);
  const M = (window.__BV && window.__BV.market) || null;
  // all these signals derive from the latest scan bundle → stamp them with the real
  // scan time (not fabricated clocks). e.g. "2026-06-05 05:15" → "05:15".
  const sm = (window.__BV && window.__BV.scanMeta) || null;
  const scanT = (sm && sm.ts && String(sm.ts).split(" ")[1]) ? String(sm.ts).split(" ")[1].slice(0, 5) : "";
  const out = [];
  if (buys[0]) out.push({ t: scanT, tone: "gn", tag: "BULLISH", sym: buys[0].sym, text: `BUY verdict · score ${buys[0].score}${buys[0].setup ? " · " + buys[0].setup : ""}` });
  if (buys[1]) out.push({ t: scanT, tone: "gn", tag: "ALERT", sym: buys[1].sym, text: `Entry ${buys[1].eq || "in zone"} · R:R ${buys[1].rr}${buys[1].rvol !== "—" ? " · " + buys[1].rvol + "× RVOL" : ""}` });
  if (er[0]) out.push({ t: scanT, tone: "amb", tag: "ER", sym: er[0].sym, text: `ER in ${er[0].er} sessions · event-risk elevated` });
  if (bear[0]) out.push({ t: scanT, tone: "rd", tag: "BEARISH", sym: bear[0].sym, text: `${HR.vmode(bear[0])} · score ${bear[0].score} · excluded from longs` });
  const _F = realFunnel(window.__tmode) || (M && M.funnel);
  if (_F) out.push({ t: scanT, tone: "ink", tag: "BUNDLE", sym: null, text: `Daily bundle · ${_F.universe} ranked · ${_F.bullish} Bullish · ${_F.neutral} Neutral · ${_F.bearish} Avoid` });
  if (ai[0]) out.push({ t: scanT, tone: "violet", tag: "AI", sym: ai[0].sym, text: `AI edge +${ai[0].aiEdge.toFixed(2)} · highest hit-net today` });
  if (ins[0]) out.push({ t: scanT, tone: "cy", tag: "INSIDER", sym: ins[0].sym, text: `Insider cluster · +${ins[0].insNet} net open-market buys` });
  return out.length ? out : (SERVED ? [] : SIGNALFEED_MOCK);
}

function SignalFeed({ onTicker }) {
  const events = useMemoH(() => resolveSignalFeed(), [bvTok()]);
  if (!events.length) {
    return <div className="sf"><div className="sf-row sf-ink"><span className="sf-text mono dim2">No signals yet — waiting on today's scan bundle.</span></div></div>;
  }
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
