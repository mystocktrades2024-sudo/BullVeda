// sidebar.jsx — left sidebar workspace nav

const { useState: useStateSB } = React;

function Sidebar({ activeId, onPick, collapsed, onToggle }) {
  return (
    <aside className={`sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="sidebar-hdr">
        <div className="sb-brand">
          <div className="sb-brand-mark">
            {/* original mark — three rising bars + slash */}
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
              <rect x="2"  y="14" width="3" height="8"  fill="var(--copper)" />
              <rect x="7"  y="9"  width="3" height="13" fill="var(--copper)" />
              <rect x="12" y="4"  width="3" height="18" fill="var(--copper)" />
              <line x1="1" y1="22" x2="22" y2="1" stroke="var(--ink)" strokeWidth="1.25" />
            </svg>
          </div>
          {!collapsed && (
            <div className="sb-brand-text">
              <div className="sb-brand-name">SwingTrade</div>
              <div className="sb-brand-ver mono">v2 · terminal</div>
            </div>
          )}
        </div>
        <button className="sb-collapse" onClick={onToggle} title="Collapse sidebar">
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      <div className="sb-search">
        {!collapsed ? (
          <div className="sb-search-input">
            <span className="sb-search-icon">⌕</span>
            <input placeholder="Find ticker, lens, command" />
            <span className="kbd">⌘K</span>
          </div>
        ) : (
          <button className="sb-search-mini" title="Search">⌕</button>
        )}
      </div>

      <nav className="sb-nav">
        {NAV.map(group => (
          <div key={group.group} className="sb-group">
            {!collapsed && <div className="sb-group-hdr label-cap">{group.group}</div>}
            {group.items.map(item => (
              <button
                key={item.id}
                className={`sb-item ${activeId === item.id ? "is-active" : ""}`}
                onClick={() => onPick(item.id)}
                title={collapsed ? item.label : undefined}
              >
                <span className="sb-item-dot" />
                {!collapsed && (
                  <>
                    <span className="sb-item-label">{item.label}</span>
                    {item.count != null && (
                      <span className={`sb-item-count ${item.badgeColor ? `tone-${item.badgeColor}` : ""}`}>
                        {item.count}
                      </span>
                    )}
                    {item.badge && (
                      <span className={`sb-item-badge ${item.badge === "live" ? "is-live" : ""}`}>
                        {item.badge}
                      </span>
                    )}
                  </>
                )}
              </button>
            ))}
          </div>
        ))}
      </nav>

      {!collapsed && (
        <div className="sb-footer">
          <div className="sb-foot-row">
            <span className="label-cap">Market</span>
            <span className="pill pill--gn pill--sm"><span className="pill-dot" />Open</span>
          </div>
          <div className="sb-foot-row">
            <span className="label-cap">As of</span>
            <span className="mono dim2">14:23:08 ET</span>
          </div>
          <div className="sb-foot-row">
            <span className="label-cap">Bundle</span>
            <span className="mono dim2">2026-05-27 · 612 ✓</span>
          </div>
        </div>
      )}
    </aside>
  );
}

window.Sidebar = Sidebar;
