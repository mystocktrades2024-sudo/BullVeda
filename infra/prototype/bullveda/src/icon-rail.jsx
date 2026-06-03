// icon-rail.jsx — leftmost narrow nav rail (icons only)
// Hover to expand into a popover with the full grouped nav.

const { useState: useStateIR, useRef: useRefIR, useEffect: useEffectIR } = React;

// Icon definitions — minimal terminal glyphs.
const ICONS = {
  home:       () => <svg viewBox="0 0 16 16"><path d="M2 7 L8 2 L14 7 V14 H10 V10 H6 V14 H2 Z" /></svg>,
  signal:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" /><circle cx="8" cy="8" r="4" /><circle cx="8" cy="8" r="7" opacity="0.55" /></svg>,
  map:        () => <svg viewBox="0 0 16 16"><rect x="1" y="1" width="6" height="6" /><rect x="9" y="1" width="6" height="6" /><rect x="1" y="9" width="6" height="6" /><rect x="9" y="9" width="6" height="6" /></svg>,
  premkt:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" /><path d="M8 4 L8 8 L11 8.5" /><circle cx="13" cy="3" r="1" fill="currentColor" stroke="none" /></svg>,
  sectoretf:  () => <svg viewBox="0 0 16 16"><rect x="2" y="3" width="3" height="11" /><rect x="6.5" y="6" width="3" height="8" /><rect x="11" y="9" width="3" height="5" /></svg>,
  social:     () => <svg viewBox="0 0 16 16"><path d="M3 4 H13 V11 H8 L5 13 V11 H3 Z" /><circle cx="6" cy="7.5" r="0.8" fill="currentColor" stroke="none" /><circle cx="8" cy="7.5" r="0.8" fill="currentColor" stroke="none" /><circle cx="10" cy="7.5" r="0.8" fill="currentColor" stroke="none" /></svg>,
  portfolio:  () => <svg viewBox="0 0 16 16"><path d="M8 2 A 6 6 0 0 1 14 8 H8 Z" fill="currentColor" /><path d="M8 2 A 6 6 0 0 0 2 8 H8 Z" /><path d="M8 8 A 6 6 0 0 1 4.5 13.2" /></svg>,
  journal:    () => <svg viewBox="0 0 16 16"><path d="M3 2 H12 A1 1 0 0 1 13 3 V13 A1 1 0 0 1 12 14 H3 Z" /><line x1="3" y1="2" x2="3" y2="14" strokeWidth="1.8" /><line x1="5.5" y1="5.5" x2="11" y2="5.5" /><line x1="5.5" y1="8" x2="11" y2="8" /><line x1="5.5" y1="10.5" x2="9" y2="10.5" /></svg>,
  insider:    () => <svg viewBox="0 0 16 16"><rect x="2" y="6" width="12" height="8" rx="1" /><path d="M5 6 V4.5 A3 3 0 0 1 11 4.5 V6" /><circle cx="8" cy="10" r="1.3" fill="currentColor" stroke="none" /></svg>,
  news:       () => <svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="1" /><line x1="4.5" y1="6" x2="11.5" y2="6" /><line x1="4.5" y1="8.5" x2="11.5" y2="8.5" /><line x1="4.5" y1="11" x2="9" y2="11" /></svg>,
  watch:      () => <svg viewBox="0 0 16 16"><circle cx="6" cy="8" r="4" /><path d="M9.5 8L14 8" /><circle cx="6" cy="8" r="1.5" fill="currentColor" stroke="none" /></svg>,
  screener:   () => <svg viewBox="0 0 16 16"><rect x="1" y="2" width="14" height="2" /><rect x="3" y="6" width="10" height="2" /><rect x="5" y="10" width="6" height="2" /><rect x="6.5" y="13" width="3" height="1.5" /></svg>,
  buy:        () => <svg viewBox="0 0 16 16"><path d="M2 14 L14 2 M14 2 L14 9 M14 2 L7 2" /></svg>,
  elite:      () => <svg viewBox="0 0 16 16"><path d="M8 1 L10 6 L15 6.5 L11 10 L12 15 L8 12.5 L4 15 L5 10 L1 6.5 L6 6 Z" /></svg>,
  themes:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" /><line x1="2" y1="8" x2="14" y2="8" /><line x1="8" y1="2" x2="8" y2="14" /></svg>,
  momentum:   () => <svg viewBox="0 0 16 16"><path d="M2 12 L6 8 L9 10 L14 4" /><polyline points="11,4 14,4 14,7" /><circle cx="14" cy="4" r="0.8" fill="currentColor" /></svg>,
  ai:         () => <svg viewBox="0 0 16 16"><path d="M8 2 L9.2 6.2 L13.5 7.5 L9.2 8.8 L8 13 L6.8 8.8 L2.5 7.5 L6.8 6.2 Z" /><circle cx="13" cy="3" r="1" /><circle cx="3" cy="13" r="0.8" /></svg>,
  epred:      () => <svg viewBox="0 0 16 16"><path d="M2 13 L6 8 L9 10 L14 4" /><polyline points="11,4 14,4 14,7" /><path d="M2.5 3.2 L3.1 4.6 L4.5 5 L3.1 5.4 L2.5 6.8 L1.9 5.4 L0.6 5 L1.9 4.6 Z" fill="currentColor" stroke="none" /></svg>,
  optflow:    () => <svg viewBox="0 0 16 16"><path d="M2 10 L5 7 L8 9 L11 5 L14 7" /><path d="M2 13 L5 11 L8 12 L11 9 L14 11" opacity="0.55" /><polyline points="11,4 14,4 14,7" opacity="0.7" /></svg>,
  strategy:   () => <svg viewBox="0 0 16 16"><circle cx="4" cy="4" r="2" /><circle cx="12" cy="4" r="2" /><circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><line x1="4" y1="4" x2="12" y2="12" /><line x1="12" y1="4" x2="4" y2="12" /></svg>,
  perf:       () => <svg viewBox="0 0 16 16"><polyline points="1,13 5,9 8,11 14,3" fill="none" /><circle cx="14" cy="3" r="1" fill="currentColor" /></svg>,
  alerts:     () => <svg viewBox="0 0 16 16"><path d="M8 2 C 5 2 4 4 4 7 V10 L 2.5 12 H 13.5 L 12 10 V7 C12 4 11 2 8 2 Z" /><path d="M6 13 C 6 14.5 7 15 8 15 C 9 15 10 14.5 10 13" /></svg>,
  book:       () => <svg viewBox="0 0 16 16"><path d="M2 3 V13 H7 V3 Z M9 3 V13 H14 V3 Z" /><line x1="3.5" y1="5.5" x2="5.5" y2="5.5" /><line x1="3.5" y1="7.5" x2="5.5" y2="7.5" /><line x1="3.5" y1="9.5" x2="5.5" y2="9.5" /><line x1="10.5" y1="5.5" x2="12.5" y2="5.5" /><line x1="10.5" y1="7.5" x2="12.5" y2="7.5" /><line x1="10.5" y1="9.5" x2="12.5" y2="9.5" /></svg>,
  settings:   () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="2.5" /><path d="M8 1 V3 M8 13 V15 M1 8 H3 M13 8 H15 M3 3 L4.5 4.5 M11.5 11.5 L13 13 M3 13 L4.5 11.5 M11.5 4.5 L13 3" /></svg>,
  status:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5" /><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" /></svg>,
  usermgmt:   () => <svg viewBox="0 0 16 16"><circle cx="6" cy="5.5" r="2.4" /><path d="M1.5 14 C 1.5 10.5 3.5 9.2 6 9.2 C 8.5 9.2 10.5 10.5 10.5 14" /><circle cx="12" cy="6.5" r="1.8" /><path d="M11 9.6 C 13 9.6 14.5 10.8 14.5 13" /></svg>,
  risk:       () => <svg viewBox="0 0 16 16"><path d="M8 1.5 L13.5 3.6 V8 C13.5 11.4 11 13.8 8 14.8 C5 13.8 2.5 11.4 2.5 8 V3.6 Z" /><path d="M5.5 8 L7.2 9.8 L10.5 6" /></svg>,
  calendar:   () => <svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="1" /><line x1="2" y1="6.2" x2="14" y2="6.2" /><line x1="5" y1="1.5" x2="5" y2="4" /><line x1="11" y1="1.5" x2="11" y2="4" /><circle cx="6" cy="9.5" r="0.7" fill="currentColor" stroke="none" /><circle cx="9" cy="9.5" r="0.7" fill="currentColor" stroke="none" /></svg>,
  macro:      () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" /><ellipse cx="8" cy="8" rx="2.6" ry="6" /><line x1="2.2" y1="8" x2="13.8" y2="8" /></svg>,
  ipo:        () => <svg viewBox="0 0 16 16"><path d="M8 1.5 C10.5 4 11 7 8 10.5 C5 7 5.5 4 8 1.5 Z" /><circle cx="8" cy="5.5" r="1.1" fill="currentColor" stroke="none" /><path d="M6 9 L4 13 L6.5 11.5 M10 9 L12 13 L9.5 11.5" /></svg>,
  crypto:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" /><path d="M6 4.5 H9 A1.8 1.8 0 0 1 9 8 H6 M6 8 H9.3 A1.8 1.8 0 0 1 9.3 11.5 H6 M6 4.5 V11.5 M7.4 3.3 V4.5 M7.4 11.5 V12.7 M8.8 3.3 V4.5 M8.8 11.5 V12.7" /></svg>,
  breadth:    () => <svg viewBox="0 0 16 16"><path d="M2 12 A6 6 0 0 1 14 12" /><line x1="8" y1="12" x2="11" y2="7.5" strokeWidth="1.6" /><circle cx="8" cy="12" r="1.1" fill="currentColor" stroke="none" /></svg>,
  lock:       () => <svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" /><path d="M5 7 V5 A3 3 0 0 1 11 5 V7" /><circle cx="8" cy="10.5" r="1.1" fill="currentColor" stroke="none" /></svg>,
  structure:  () => <svg viewBox="0 0 16 16"><rect x="2" y="7" width="4" height="6" /><rect x="10" y="4" width="4" height="9" /><line x1="4" y1="3" x2="4" y2="7" /><line x1="12" y1="2" x2="12" y2="4" /><line x1="6" y1="9" x2="10" y2="6" strokeDasharray="1.5 1.5" /></svg>,
  flask:      () => <svg viewBox="0 0 16 16"><path d="M6 2 V6 L3 12 A1 1 0 0 0 4 13.5 H12 A1 1 0 0 0 13 12 L10 6 V2" /><line x1="5.5" y1="2" x2="10.5" y2="2" strokeWidth="1.6" /><circle cx="7" cy="10.5" r="0.8" fill="currentColor" stroke="none" /><circle cx="9.5" cy="11.5" r="0.6" fill="currentColor" stroke="none" /></svg>,
  wallet:     () => <svg viewBox="0 0 16 16"><rect x="2" y="4" width="12" height="9" rx="1.5" /><path d="M2 6.5 H12 A1 1 0 0 1 13 7.5 V9" opacity="0.5" /><circle cx="11.5" cy="9" r="1.2" fill="currentColor" stroke="none" /></svg>,
  helpq:      () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.2" /><path d="M6.2 6.2 C6.2 4.6 9.8 4.6 9.8 6.6 C9.8 8 8 8 8 9.4" /><circle cx="8" cy="11.6" r="0.9" fill="currentColor" stroke="none" /></svg>,
};

// Sidebar items grouped by the buy-side workflow:
// Markets (top-down context) → Discover (screen + alpha) → Research (analyze)
// → Manage (portfolio + risk) → Review (process) → Admin (governance)
const RAIL_GROUPS = [
  { group: "Markets", items: [
    { id: "themes",         icon: "themes",    label: "Themes",          count: 6,  tone: "violet" },
    { id: "sector-etf",    icon: "sectoretf", label: "Sectors · ETFs",  count: 96, tone: "cy" },
    { id: "premarket",     icon: "premkt",    label: "Pre-Market",      count: 18, tone: "blue" },
    { id: "ipos",          icon: "ipo",       label: "Upcoming IPOs",   count: 12, tone: "gn" },
    { id: "crypto",        icon: "crypto",    label: "Crypto Market",   count: 18, tone: "amb" },
    { id: "news",          icon: "news",      label: "News · Sentiment",count: 24, tone: "blue" },
  ]},
  { group: "Discover", items: [
    { id: "momentum",      icon: "momentum",  label: "Momentum",        count: 22, tone: "copper" },
    { id: "earnings-ai",   icon: "epred",     label: "Earnings AI",      count: 22, tone: "gn" },
    { id: "ai-predict",    icon: "ai",        label: "ML Predictions",  count: 5,  tone: "violet" },
    { id: "options",       icon: "optflow",   label: "Options Flow",    count: 19, tone: "amb" },
    { id: "insider",       icon: "insider",   label: "Insider Trading", count: 38, tone: "cy" },
    { id: "smc-patterns",  icon: "structure", label: "SMC / Patterns",  count: 16, tone: "violet" },
  ]},
  { group: "Research", items: [
    { id: "strategies",    icon: "strategy",  label: "Strategies · Backtests", count: 11, tone: "blue" },
    { id: "lab",           icon: "flask",     label: "Research Lab",    tone: "violet" },
  ]},
  { group: "Manage", items: [
    { id: "portfolio-srf", icon: "portfolio", label: "Automated Trade", tone: "copper" },
    { id: "myportfolios",  icon: "wallet",    label: "My Portfolios",   tone: "gn" },
    { id: "book-risk",     icon: "breadth",   label: "Book Risk",       tone: "amb" },
  ]},
  { group: "Review", items: [
    { id: "track-record", icon: "perf",      label: "Track Record",    tone: "gn" },
    { id: "playbook",      icon: "book",      label: "Playbook", tone: "copper" },
  ]},
  { group: "Admin", items: [
    { id: "settings",      icon: "settings",  label: "Settings", tone: "blue" },
    { id: "users",         icon: "usermgmt",  label: "User Management", tone: "amb" },
    { id: "status",        icon: "status",    label: "System Status",   tone: "gn" },
    { id: "help",          icon: "helpq",     label: "Help · Docs",      tone: "cy" },
  ]},
];

// tone → CSS color
function irTone(t) { return t ? `var(--${t})` : "var(--ink-2)"; }

function IconRail({ activeId, onPick, tier = 4, expanded = false, onToggleExpand }) {
  const [hoverGroup, setHoverGroup] = useStateIR(null);
  const [, forceIR] = useStateIR(0);
  const popoverRef = useRefIR(null);

  useEffectIR(() => {
    const h = () => forceIR(x => x + 1);
    window.addEventListener("watchlist-change", h);
    return () => window.removeEventListener("watchlist-change", h);
  }, []);

  return (
    <aside className={`ir ${expanded ? "ir--expanded" : ""}`}>
      <div className="ir-brand-row">
        <div className="ir-brand" title="SwingTrade · v2">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
            <rect x="2"  y="14" width="3" height="8"  fill="var(--copper)" />
            <rect x="7"  y="9"  width="3" height="13" fill="var(--copper)" />
            <rect x="12" y="4"  width="3" height="18" fill="var(--copper)" />
            <line x1="1" y1="22" x2="22" y2="1" stroke="var(--ink)" strokeWidth="1.25" />
          </svg>
          <span className="ir-brand-name mono">SwingTrade</span>
        </div>
        <button className="ir-toggle" onClick={onToggleExpand} title={expanded ? "Collapse" : "Expand"}>
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d={expanded ? "M10 3 L5 8 L10 13" : "M6 3 L11 8 L6 13"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      </div>

      <button
        className={`ir-item ir-item--top ${activeId === "home" ? "is-active" : ""}`}
        style={{ "--ir-accent": "var(--copper)" }}
        onClick={() => onPick("home")}
        title="Home">
        <span className="ir-icon">{ICONS.home()}</span>
        <span className="ir-label">Home</span>
        <span className="ir-dot" />
      </button>

      <div className="ir-search" title="Signal Scanner · all tickers · ⌘K"
           onClick={() => onPick && onPick("signal-scanner")}
           style={{ cursor: "pointer", "--ir-accent": "var(--gn)" }}>
        <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
          <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.4" />
          <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.4" />
        </svg>
        <span className="ir-label">Signal Scanner</span>
      </div>

      {RAIL_GROUPS.map((g, gi) => (
        <div key={g.group} className="ir-group">
          {gi > 0 && <div className="ir-sep" />}
          <div className="ir-grp-lbl mono">{g.group}</div>
          {g.items.map(it => {
            const Icon = ICONS[it.icon];
            const active = activeId === it.id;
            const minT = (window.SURFACE_TIER || {})[it.id] ?? 0;
            const locked = minT > tier;
            const count = (it.id === "watchlist" && window.WatchStore) ? window.WatchStore.count() : it.count;
            return (
              <button
                key={it.id}
                className={`ir-item ${active ? "is-active" : ""} ${locked ? "is-locked" : ""}`}
                style={{ "--ir-accent": irTone(it.tone) }}
                onClick={() => onPick(it.id)}
                onMouseEnter={() => setHoverGroup(it.id)}
                onMouseLeave={() => setHoverGroup(null)}
                title={it.label}
              >
                <span className="ir-icon"><Icon /></span>
                <span className="ir-label">{it.label}</span>
                {locked
                  ? <span className="ir-lock" title={`Tier ${minT}+`}>🔒</span>
                  : count != null && (
                    <span className={`ir-count ${it.tone ? `ir-count--${it.tone}` : ""}`}>{count}</span>
                  )}
                {it.hot && !locked && <span className="ir-dot" />}
                {hoverGroup === it.id && (
                  <span className="ir-tip mono">{it.label}{locked ? ` · TIER ${minT}+` : count != null ? ` · ${count}` : ""}</span>
                )}
              </button>
            );
          })}
        </div>
      ))}

      <div className="ir-foot">
        <div className="ir-foot-pulse" title="Market open · live">
          <span className="ir-foot-dot" />
        </div>
      </div>
    </aside>
  );
}

window.IconRail = IconRail;
