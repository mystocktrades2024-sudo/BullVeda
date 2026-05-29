// icon-rail.jsx — leftmost narrow nav rail (icons only)
// Hover to expand into a popover with the full grouped nav.

const { useState: useStateIR, useRef: useRefIR, useEffect: useEffectIR } = React;

// Icon definitions — minimal terminal glyphs.
const ICONS = {
  map:        () => <svg viewBox="0 0 16 16"><rect x="1" y="1" width="6" height="6" /><rect x="9" y="1" width="6" height="6" /><rect x="1" y="9" width="6" height="6" /><rect x="9" y="9" width="6" height="6" /></svg>,
  watch:      () => <svg viewBox="0 0 16 16"><circle cx="6" cy="8" r="4" /><path d="M9.5 8L14 8" /><circle cx="6" cy="8" r="1.5" fill="currentColor" stroke="none" /></svg>,
  screener:   () => <svg viewBox="0 0 16 16"><rect x="1" y="2" width="14" height="2" /><rect x="3" y="6" width="10" height="2" /><rect x="5" y="10" width="6" height="2" /><rect x="6.5" y="13" width="3" height="1.5" /></svg>,
  buy:        () => <svg viewBox="0 0 16 16"><path d="M2 14 L14 2 M14 2 L14 9 M14 2 L7 2" /></svg>,
  elite:      () => <svg viewBox="0 0 16 16"><path d="M8 1 L10 6 L15 6.5 L11 10 L12 15 L8 12.5 L4 15 L5 10 L1 6.5 L6 6 Z" /></svg>,
  themes:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" /><line x1="2" y1="8" x2="14" y2="8" /><line x1="8" y1="2" x2="8" y2="14" /></svg>,
  strategy:   () => <svg viewBox="0 0 16 16"><circle cx="4" cy="4" r="2" /><circle cx="12" cy="4" r="2" /><circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><line x1="4" y1="4" x2="12" y2="12" /><line x1="12" y1="4" x2="4" y2="12" /></svg>,
  perf:       () => <svg viewBox="0 0 16 16"><polyline points="1,13 5,9 8,11 14,3" fill="none" /><circle cx="14" cy="3" r="1" fill="currentColor" /></svg>,
  alerts:     () => <svg viewBox="0 0 16 16"><path d="M8 2 C 5 2 4 4 4 7 V10 L 2.5 12 H 13.5 L 12 10 V7 C12 4 11 2 8 2 Z" /><path d="M6 13 C 6 14.5 7 15 8 15 C 9 15 10 14.5 10 13" /></svg>,
  book:       () => <svg viewBox="0 0 16 16"><path d="M2 3 V13 H7 V3 Z M9 3 V13 H14 V3 Z" /><line x1="3.5" y1="5.5" x2="5.5" y2="5.5" /><line x1="3.5" y1="7.5" x2="5.5" y2="7.5" /><line x1="3.5" y1="9.5" x2="5.5" y2="9.5" /><line x1="10.5" y1="5.5" x2="12.5" y2="5.5" /><line x1="10.5" y1="7.5" x2="12.5" y2="7.5" /><line x1="10.5" y1="9.5" x2="12.5" y2="9.5" /></svg>,
  settings:   () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="2.5" /><path d="M8 1 V3 M8 13 V15 M1 8 H3 M13 8 H15 M3 3 L4.5 4.5 M11.5 11.5 L13 13 M3 13 L4.5 11.5 M11.5 4.5 L13 3" /></svg>,
  status:     () => <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5" /><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" /></svg>,
};

// Map sidebar items to icons
const RAIL_GROUPS = [
  { group: "Scan", items: [
    { id: "market-map", icon: "map",      label: "Market Map",     hot: true },
    { id: "watchlist",  icon: "watch",    label: "Watchlist",      count: 12 },
    { id: "buy",        icon: "buy",      label: "BUY candidates", count: 14, tone: "gn" },
    { id: "elite",      icon: "elite",    label: "Elite Picks",    count: 8 },
    { id: "screener",   icon: "screener", label: "Screener" },
    { id: "themes",     icon: "themes",   label: "Themes",         count: 6 },
  ]},
  { group: "Tools", items: [
    { id: "strategies", icon: "strategy", label: "Strategies",     count: 11 },
    { id: "performance",icon: "perf",     label: "Performance" },
    { id: "alerts",     icon: "alerts",   label: "Alerts",         count: 3, tone: "amb" },
    { id: "playbook",   icon: "book",     label: "Playbook" },
  ]},
  { group: "Admin", items: [
    { id: "settings",   icon: "settings", label: "Settings" },
    { id: "status",     icon: "status",   label: "System Status",  tone: "gn" },
  ]},
];

function IconRail({ activeId, onPick }) {
  const [hoverGroup, setHoverGroup] = useStateIR(null);
  const popoverRef = useRefIR(null);

  return (
    <aside className="ir">
      <div className="ir-brand" title="SwingTrade · v2">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <rect x="2"  y="14" width="3" height="8"  fill="var(--copper)" />
          <rect x="7"  y="9"  width="3" height="13" fill="var(--copper)" />
          <rect x="12" y="4"  width="3" height="18" fill="var(--copper)" />
          <line x1="1" y1="22" x2="22" y2="1" stroke="var(--ink)" strokeWidth="1.25" />
        </svg>
      </div>

      <div className="ir-search" title="Search · ⌘K">
        <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
          <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.4" />
          <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      </div>

      {RAIL_GROUPS.map((g, gi) => (
        <div key={g.group} className="ir-group">
          {gi > 0 && <div className="ir-sep" />}
          {g.items.map(it => {
            const Icon = ICONS[it.icon];
            const active = activeId === it.id;
            return (
              <button
                key={it.id}
                className={`ir-item ${active ? "is-active" : ""}`}
                onClick={() => onPick(it.id)}
                onMouseEnter={() => setHoverGroup(it.id)}
                onMouseLeave={() => setHoverGroup(null)}
                title={it.label}
              >
                <span className="ir-icon"><Icon /></span>
                {it.count != null && (
                  <span className={`ir-count ${it.tone ? `ir-count--${it.tone}` : ""}`}>{it.count}</span>
                )}
                {it.hot && <span className="ir-dot" />}
                {hoverGroup === it.id && (
                  <span className="ir-tip mono">{it.label}{it.count != null && ` · ${it.count}`}</span>
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
