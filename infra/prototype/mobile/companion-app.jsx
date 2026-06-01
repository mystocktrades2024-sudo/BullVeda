// companion-app.jsx — navigation chrome (tab bar / rail), More grid,
// compact surfaces, and the Companion root that routes everything.
const { useState: aS, useEffect: aE, useRef: aR } = React;
const ax = window.cmpHelpers;

/* ── nav icons (compact terminal glyphs) ── */
const NavIco = {
  home: <svg viewBox="0 0 24 24" fill="none"><path d="M3 11l9-7 9 7M5 9.5V20h5v-6h4v6h5V9.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  scan: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1.8"/><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" opacity="0.5"/></svg>,
  watch: <svg viewBox="0 0 24 24" fill="none"><path d="M12 5C6 5 2.5 12 2.5 12S6 19 12 19s9.5-7 9.5-7S18 5 12 5z" stroke="currentColor" strokeWidth="1.8"/><circle cx="12" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.8"/></svg>,
  portfolio: <svg viewBox="0 0 24 24" fill="none"><path d="M12 3a9 9 0 109 9h-9z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/><path d="M12 3v9h9" stroke="currentColor" strokeWidth="1.8" opacity="0.5"/></svg>,
  more: <svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.8"/></svg>,
  news: <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.8"/><path d="M7 9h7M7 12h7M7 15h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>,
  sectors: <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="10" width="4" height="10" stroke="currentColor" strokeWidth="1.8"/><rect x="10" y="5" width="4" height="15" stroke="currentColor" strokeWidth="1.8"/><rect x="17" y="13" width="4" height="7" stroke="currentColor" strokeWidth="1.8"/></svg>,
  momentum: <svg viewBox="0 0 24 24" fill="none"><path d="M3 17l5-5 4 3 7-8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><path d="M16 7h4v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  earnings: <svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="4.5" width="17" height="16" rx="2" stroke="currentColor" strokeWidth="1.8"/><path d="M3.5 9h17M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><circle cx="12" cy="14.5" r="2.5" stroke="currentColor" strokeWidth="1.6"/></svg>,
  options: <svg viewBox="0 0 24 24" fill="none"><path d="M3 15l4 1 2-8 3 11 2-7 2 3h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  themes: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/><path d="M3 12h18M12 3v18" stroke="currentColor" strokeWidth="1.5"/></svg>,
  internals: <svg viewBox="0 0 24 24" fill="none"><path d="M3 18a9 9 0 0118 0" stroke="currentColor" strokeWidth="1.8"/><path d="M12 18l5-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><circle cx="12" cy="18" r="1.6" fill="currentColor"/></svg>,
  premarket: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8"/><path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
  calendar: <svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="4.5" width="17" height="16" rx="2" stroke="currentColor" strokeWidth="1.8"/><path d="M3.5 9h17M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
  ai: <svg viewBox="0 0 24 24" fill="none"><path d="M12 3l1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg>,
  insider: <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="10" width="18" height="11" rx="2" stroke="currentColor" strokeWidth="1.8"/><path d="M7.5 10V7a4.5 4.5 0 019 0v3" stroke="currentColor" strokeWidth="1.8"/></svg>,
  smc: <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="9" width="7" height="9" stroke="currentColor" strokeWidth="1.8"/><rect x="14" y="5" width="7" height="9" stroke="currentColor" strokeWidth="1.8"/></svg>,
  strategies: <svg viewBox="0 0 24 24" fill="none"><circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.8"/><circle cx="18" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.8"/><circle cx="6" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.8"/><circle cx="18" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.8"/><path d="M6 8.5v7M18 8.5v7M8.5 6h7M8.5 18h7" stroke="currentColor" strokeWidth="1.5"/></svg>,
  lab: <svg viewBox="0 0 24 24" fill="none"><path d="M9 3v6l-5 9a1.5 1.5 0 001.3 2.2h13.4A1.5 1.5 0 0020 18l-5-9V3" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/><path d="M8 3h8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
  autotrade: <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.8"/><path d="M7 12h3l1.5-2.5L13 14l1-2h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  bookrisk: <svg viewBox="0 0 24 24" fill="none"><path d="M12 3l8 3v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  track: <svg viewBox="0 0 24 24" fill="none"><path d="M4 19l5-5 3 2 7-8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><circle cx="19" cy="8" r="1.6" fill="currentColor"/></svg>,
  playbook: <svg viewBox="0 0 24 24" fill="none"><path d="M4 4h9a2 2 0 012 2v14H6a2 2 0 01-2-2z" stroke="currentColor" strokeWidth="1.8"/><path d="M15 6h5v12a2 2 0 01-2 2h-3" stroke="currentColor" strokeWidth="1.8"/></svg>,
  settings: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>,
  users: <svg viewBox="0 0 24 24" fill="none"><circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.8"/><path d="M3 20c0-3.3 2.7-5 6-5s6 1.7 6 5" stroke="currentColor" strokeWidth="1.8"/><circle cx="17" cy="9" r="2.3" stroke="currentColor" strokeWidth="1.6"/><path d="M16 14c2.6 0 4.5 1.5 4.5 4" stroke="currentColor" strokeWidth="1.6"/></svg>,
  status: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8"/><circle cx="12" cy="12" r="2.5" fill="currentColor"/></svg>,
  help: <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/><path d="M9.5 9.5c0-2.5 5-2.5 5 .5 0 2-2.5 2-2.5 4M12 17.5h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
};

/* ── More IA (mirrors the desktop icon-rail groups) ── */
const MORE_GROUPS = [
  { group: "Markets", items: [
    { id: "sectors", icon: "sectors", label: "Sectors · ETFs", sub: "rotation heat", surf: "sectors" },
    { id: "internals", icon: "internals", label: "Market Internals", sub: "breadth", surf: "internals" },
    { id: "premarket", icon: "premarket", label: "Pre-Market", sub: "gap board", surf: "premarket" },
    { id: "calendar", icon: "calendar", label: "Macro Calendar", sub: "events", surf: "calendar" },
    { id: "news", icon: "news", label: "News · Sentiment", sub: "24h feed", surf: "news" },
    { id: "themes", icon: "themes", label: "Themes", sub: "baskets", surf: "themes" },
  ]},
  { group: "Discover", items: [
    { id: "momentum", icon: "momentum", label: "Momentum", sub: "RS leaders", surf: "momentum" },
    { id: "earnings", icon: "earnings", label: "Earnings AI", sub: "implied moves", surf: "earnings" },
    { id: "ai", icon: "ai", label: "ML Predictions", sub: "model picks", surf: "ai" },
    { id: "options", icon: "options", label: "Options Flow", sub: "smart money", surf: "options" },
    { id: "insider", icon: "insider", label: "Insider Trading", sub: "filings", surf: "insider" },
    { id: "smc", icon: "smc", label: "SMC / Patterns", sub: "structure", surf: "smc" },
  ]},
  { group: "Research", items: [
    { id: "strategies", icon: "strategies", label: "Strategies", sub: "backtests", compact: "strategies" },
    { id: "lab", icon: "lab", label: "Research Lab", sub: "walk-forward", compact: "lab" },
  ]},
  { group: "Manage", items: [
    { id: "autotrade", icon: "autotrade", label: "Automated Trade", sub: "execution", compact: "autotrade" },
    { id: "bookrisk", icon: "bookrisk", label: "Book Risk", sub: "live limits", surf: "bookrisk" },
  ]},
  { group: "Review", items: [
    { id: "track", icon: "track", label: "Track Record", sub: "equity curve", surf: "track" },
    { id: "playbook", icon: "playbook", label: "Playbook", sub: "process", compact: "playbook" },
  ]},
  { group: "Admin", items: [
    { id: "settings", icon: "settings", label: "Settings", sub: "preferences", compact: "settings" },
    { id: "users", icon: "users", label: "User Mgmt", sub: "RBAC", compact: "users" },
    { id: "status", icon: "status", label: "System Status", sub: "health", compact: "status" },
    { id: "help", icon: "help", label: "Help · Docs", sub: "guides", compact: "help" },
  ]},
];

const COMPACT_META = {
  internals: { label: "Market Internals", icon: "internals", desc: "Breadth, advance/decline, new highs–lows, and McClellan oscillator across the tape.", kpis: [["A/D line", "+1,240", "gn"], ["New H–L", "+186", "gn"], ["% > 50DMA", "62%", "gn"]] },
  premarket: { label: "Pre-Market", icon: "premarket", desc: "Overnight gappers, futures tape, and the catalyst board before the open.", kpis: [["Gappers", "18", "copper"], ["ES fut", "+0.4%", "gn"], ["Catalysts", "11", "amb"]] },
  calendar: { label: "Macro Calendar", icon: "calendar", desc: "Economic releases, Fed speakers, and scheduled events with market-impact ratings.", kpis: [["Today", "4", "amb"], ["High-impact", "1", "rd"], ["This week", "15"]] },
  themes: { label: "Themes", icon: "themes", desc: "Curated thematic baskets — AI, onshoring, GLP-1 — with constituent drill-downs.", kpis: [["Baskets", "6", "violet"], ["Leading", "AI +2.1%", "gn"], ["Names", "84"]] },
  ai: { label: "ML Predictions", icon: "ai", desc: "The 3-headed model's ranked directional picks with confidence and feature drivers.", kpis: [["Picks", "5", "violet"], ["Avg P(up)", "64%", "gn"], ["Hit rate", "58%"]] },
  insider: { label: "Insider Trading", icon: "insider", desc: "Form 4 filings — cluster buys, CFO/CEO transactions, and net insider flow.", kpis: [["Filings", "38", "cy"], ["Net buys", "+24", "gn"], ["Clusters", "3", "copper"]] },
  smc: { label: "SMC / Patterns", icon: "smc", desc: "Smart-money structure and the 13-discipline pattern confluence across the universe.", kpis: [["Setups", "16", "violet"], ["BOS today", "9", "gn"], ["FVGs open", "22"]] },
  strategies: { label: "Strategies", icon: "strategies", desc: "Backtested sleeves with walk-forward stats, activation matrix, and edge decay.", kpis: [["Sleeves", "11", "blue"], ["Active", "7", "gn"], ["Avg PF", "1.8"]] },
  lab: { label: "Research Lab", icon: "lab", desc: "Hypothesis builder, walk-forward results, IC analysis, and the scan-tuning sandbox.", kpis: [["Experiments", "9", "violet"], ["Best IC", "0.07", "gn"], ["Models", "4"]] },
  autotrade: { label: "Automated Trade", icon: "autotrade", desc: "Live execution engine — routing, fills, and per-rule automation status.", kpis: [["Rules", "5", "copper"], ["Live", "paper", "amb"], ["Fills today", "12"]] },
  bookrisk: { label: "Book Risk", icon: "bookrisk", desc: "Portfolio-level VaR, limits, stress scenarios, and factor exposures live.", kpis: [["VaR 1d", "-2.4%", "rd"], ["Limit use", "61%", "amb"], ["β net", "0.9"]] },
  track: { label: "Track Record", icon: "track", desc: "Verified equity curve, R-multiple distribution, and edge-by-sleeve attribution.", kpis: [["Net R", "+148", "gn"], ["Win rate", "61%", "gn"], ["Sharpe", "1.4"]] },
  playbook: { label: "Playbook", icon: "playbook", desc: "Entry gates, sizing policy, sleeve activation, and the behavioral cost ledger.", kpis: [["Gates", "8"], ["Sleeves", "11"], ["Cost of R", "0.3", "amb"]] },
  settings: { label: "Settings", icon: "settings", desc: "Account, notifications, data feeds, theme, and tier preferences.", kpis: [["Tier", "Elite", "copper"], ["Alerts", "3", "amb"], ["Theme", "Obsidian"]] },
  users: { label: "User Management", icon: "users", desc: "RBAC roles, seats, and access controls for your desk.", kpis: [["Seats", "6", "amb"], ["Admins", "2"], ["Pending", "1", "rd"]] },
  status: { label: "System Status", icon: "status", desc: "Feed health, model freshness, and pipeline run history.", kpis: [["Feeds", "OK", "gn"], ["Models", "fresh", "gn"], ["Last run", "2m"]] },
  help: { label: "Help · Docs", icon: "help", desc: "Guides, the metric glossary, keyboard shortcuts, and support.", kpis: [["Articles", "42"], ["Glossary", "120"], ["Support", "live", "gn"]] },
};

/* ── More grid + compact ── */
function MoreGrid({ go }) {
  const tier = 4;
  return (
    <div className="cmp-surface">
      <window.SHead title="All surfaces" sub="full workspace" />
      {MORE_GROUPS.map((g) => (
        <div className="cmp-moregrp" key={g.group}>
          <div className="cmp-moregrp-l">{g.group}</div>
          <div className="cmp-grid">
            {g.items.map((it) => {
              const locked = ((window.SURFACE_TIER || {})[it.id] ?? 0) > tier;
              return (
                <button className="cmp-gcard" key={it.id} onClick={() => go(it)}>
                  <span className="cmp-gcard-ic" style={{ color: "var(--copper)" }}>{NavIco[it.icon]}</span>
                  <span style={{ minWidth: 0 }}><span className="cmp-gcard-t">{it.label}</span><span className="cmp-gcard-s">{it.sub}</span></span>
                  {it.compact && <span className="cmp-gcard-lock">↗</span>}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <div className="cmp-disc">{window.SEC_DISCLAIMER_SHORT}</div>
    </div>
  );
}

function CompactSurface({ id, onDesktop }) {
  const m = COMPACT_META[id] || { label: id, icon: "more", desc: "", kpis: [] };
  return (
    <div className="cmp-compact">
      <div className="cmp-compact-hero">
        <div className="cmp-compact-ic">{NavIco[m.icon]}</div>
        <div className="cmp-compact-t">{m.label}</div>
        <div className="cmp-compact-d">{m.desc}</div>
      </div>
      <window.StatStrip items={m.kpis.map(([l, v, tone]) => ({ l, v, tone }))} />
      <div style={{ textAlign: "center", marginTop: 22 }}>
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginBottom: 14, lineHeight: 1.5 }}>This view is built for the wide terminal.<br/>Open it on desktop for the full workspace.</div>
        <button className="cmp-compact-btn" onClick={onDesktop}>{window.Ico.ext} Open on desktop</button>
      </div>
    </div>
  );
}
window.SHead = ({ title, sub }) => (
  <div className="cmp-shead">
    <span className="cmp-shead-t">{title}</span>
    <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
      {sub && <span className="cmp-shead-s" style={{ marginLeft: 0 }}>{sub}</span>}
      {window.HeaderActions && <window.HeaderActions />}
    </div>
  </div>
);

/* ── nav chrome ── */
const TABS = [["home", "Home", "home"], ["scan", "Scan", "scan"], ["watchlist", "Watchlist", "watch"], ["portfolio", "Portfolio", "portfolio"], ["more", "More", "more"]];
function BottomTabBar({ tab, onTab }) {
  return (
    <nav className="cmp-tabbar">
      {TABS.map(([id, label, ic]) => (
        <button key={id} className={`cmp-tab ${tab === id ? "is-on" : ""}`} onClick={() => onTab(id)}>{NavIco[ic]}<span>{label}</span></button>
      ))}
    </nav>
  );
}
function LeftRail({ tab, onTab }) {
  const [, f] = aS(0);
  aE(() => { const h = () => f((x) => x + 1); window.addEventListener("alerts-change", h); return () => window.removeEventListener("alerts-change", h); }, []);
  const n = window.AlertStore ? window.AlertStore.count() : 0;
  return (
    <div className="cmp-leftrail">
      <div className="cmp-railbrand">S</div>
      {TABS.map(([id, label, ic]) => (
        <button key={id} className={`cmp-railitem ${tab === id ? "is-on" : ""}`} onClick={() => onTab(id)}>{NavIco[ic]}<span>{label}</span></button>
      ))}
      <div className="cmp-railsep" />
      <button className="cmp-railitem" onClick={() => window.__cmpSearch && window.__cmpSearch()}>
        <svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8"/><path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg><span>Search</span>
      </button>
      <button className="cmp-railitem" style={{ position: "relative" }} onClick={() => window.__cmpAlerts && window.__cmpAlerts()}>
        <svg viewBox="0 0 24 24" fill="none"><path d="M18 8a6 6 0 10-12 0c0 7-3 8-3 8h18s-3-1-3-8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M13.7 21a2 2 0 01-3.4 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg><span>Alerts</span>
        {n > 0 && <span className="cmp-hdrbadge" style={{ top: 4, right: 12 }}>{n}</span>}
      </button>
      <div className="cmp-railspacer" />
      <div className="cmp-raillive" title="Market open" />
    </div>
  );
}

/* ════════════ ROOT ════════════ */
function Companion({ initialTab = "home", initialSym = null, initialDetail = false }) {
  const ref = aR(null);
  const [posture, setPosture] = aS("phone");
  const [tab, setTab] = aS(initialTab);
  const [moreSel, setMoreSel] = aS(null);     // {surf|compact, id, label}
  const [scan, setScan] = aS("all");
  const [sym, setSym] = aS(initialSym);
  const [lensId, setLensId] = aS("overview");
  const [mode, setMode] = aS("SWING");
  const [detail, setDetail] = aS(initialDetail); // full detail screen (phone push / overlay)
  const [sheet, setSheet] = aS(null);
  const [toast, setToast] = aS(null);
  const [search, setSearch] = aS(false);
  const [alertsOpen, setAlertsOpen] = aS(false);

  aE(() => {
    window.__cmpSearch = () => setSearch(true);
    window.__cmpAlerts = () => setAlertsOpen(true);
    return () => { window.__cmpSearch = null; window.__cmpAlerts = null; };
  }, []);

  aE(() => {
    if (!ref.current) return;
    const measure = () => { if (ref.current) setPosture(ref.current.offsetWidth >= 760 ? "split" : "phone"); };
    measure();
    const ro = new ResizeObserver(measure); ro.observe(ref.current);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  React.useLayoutEffect(() => { if (ref.current) setPosture(ref.current.offsetWidth >= 760 ? "split" : "phone"); }, []);

  const isSplitList = posture === "split" && (tab === "scan" || tab === "watchlist");
  // default selection for split list panes
  aE(() => { if (isSplitList && !sym) setSym(window.ALERT_SYM); }, [isSplitList, sym]);

  const showToast = (msg) => { setToast(msg); clearTimeout(window.__cmpToast); window.__cmpToast = setTimeout(() => setToast(null), 2200); };
  const ticker = sym ? ax.resolveTicker(sym) : null;

  const openSym = (s) => { setSym(s); setLensId("overview"); if (!(posture === "split" && (tab === "scan" || tab === "watchlist"))) setDetail(true); };
  const onTab = (t) => { setTab(t); setMoreSel(null); setDetail(false); };

  const doAction = (kind) => {
    const t = ticker;
    if (kind === "desktop") { setSheet(null); const url = "/app?view=desktop" + (t ? "&t=" + encodeURIComponent(t.symbol) : ""); try { window.top.location.href = url; } catch (e) { window.location.href = url; } return; }
    if (!t) return;
    if (kind === "actions") return setSheet("actions");
    if (kind === "alert") return setSheet("alert");
    if (kind === "copy" || kind === "share") {
      const txt = `${t.symbol} · ${window.secBias(t.verdict)} ${t.score}/100 · ${mode}\nEntry >$${ax.fmt(t.pivot)}  Stop $${ax.fmt(t.stop)}\nT1 $${ax.fmt(t.t1)}  T2 $${ax.fmt(t.t2)}  ·  ${ax.fmt(t.rMultiple, 1)}R`;
      try { navigator.clipboard && navigator.clipboard.writeText(txt); } catch (e) {}
      setSheet(null); showToast(kind === "share" ? "Copied for Slack — paste in channel" : "Trade levels copied");
    }
  };

  const DetailM = window.DetailM;
  const detailEl = (onBack) => ticker
    ? <DetailM ticker={ticker} mode={mode} setMode={setMode} lensId={lensId} setLensId={setLensId} onBack={onBack} posture={posture} onAction={doAction} />
    : <div className="cmp-empty">{window.Ico.search}<div className="cmp-empty-t">Pick a stock</div><div className="cmp-empty-s">Tap any name to open its full 12-lens read.</div></div>;

  // surface content for the active tab
  const surfaceEl = () => {
    if (tab === "scan") return <window.ScanList scan={scan} setScan={setScan} selectedSym={sym} onOpen={openSym} posture={posture} />;
    if (tab === "watchlist") return <window.MOBILE_SURF.watchlist openSym={openSym} selectedSym={sym} />;
    if (tab === "home") return <window.MOBILE_SURF.home openSym={openSym} />;
    if (tab === "portfolio") return <window.MOBILE_SURF.portfolio openSym={openSym} />;
    if (tab === "more") {
      if (!moreSel) return <MoreGrid go={(it) => setMoreSel(it)} />;
      return (
        <React.Fragment>
          <div className="cmp-sback"><button onClick={() => setMoreSel(null)}>{window.Ico.chevL} All surfaces</button></div>
          {moreSel.surf ? React.createElement(window.MOBILE_SURF[moreSel.surf], { openSym }) : <CompactSurface id={moreSel.compact} onDesktop={() => doAction("desktop")} />}
        </React.Fragment>
      );
    }
    return null;
  };

  const isList = tab === "scan" || tab === "watchlist";

  return (
    <div className={`cmp cmp-${posture === "split" ? "split" : "phone"}`} ref={ref} data-screen-label={posture}>
      {posture === "split" ? (
        <React.Fragment>
          <LeftRail tab={tab} onTab={onTab} />
          {isSplitList ? (
            <React.Fragment>{surfaceEl()}<div className="cmp-detailwrap">{detailEl(null)}</div></React.Fragment>
          ) : (
            <div className="cmp-appcol">
              {isList ? surfaceEl() : <div className="cmp-surfacewrap"><window.Loader key={tab + (moreSel ? moreSel.id : "")}>{surfaceEl()}</window.Loader></div>}
              {detail && ticker && <div className="cmp-detailoverlay">{detailEl(() => setDetail(false))}</div>}
            </div>
          )}
        </React.Fragment>
      ) : (
        detail && ticker ? detailEl(() => setDetail(false)) : (
          <div className="cmp-appcol">
            {isList ? surfaceEl() : <div className="cmp-surfacewrap"><window.Loader key={tab + (moreSel ? moreSel.id : "")}>{surfaceEl()}</window.Loader></div>}
            <BottomTabBar tab={tab} onTab={onTab} />
          </div>
        )
      )}
      {sheet === "actions" && ticker && <window.ActionSheet ticker={ticker} onClose={() => setSheet(null)} onAction={doAction} />}
      {sheet === "alert" && ticker && <window.AlertSheet ticker={ticker} onClose={() => setSheet(null)} onToast={showToast} />}
      {alertsOpen && <div className="cmp-detailoverlay" style={{ zIndex: 45 }}><window.SrfAlerts onClose={() => setAlertsOpen(false)} openSym={(s) => { setAlertsOpen(false); openSym(s); }} /></div>}
      {search && <window.SearchOverlay onClose={() => setSearch(false)} onPick={openSym} />}
      {toast && <div className="cmp-toast">{window.Ico.check}{toast}</div>}
    </div>
  );
}

window.Companion = Companion;
