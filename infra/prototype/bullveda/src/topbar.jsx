// topbar.jsx — top bar with command, mode toggle, account state

function TopBar({ mode, onMode, onOpenTicker, theme, onTheme }) {
  return (
    <div className="topbar">
      <div className="tb-left">
        <button className="tb-back" title="Back">←</button>
        <button className="tb-fwd" title="Forward">→</button>
        <div className="tb-breadcrumb">
          <span className="dim mono">Workspace</span>
          <span className="dim">›</span>
          <span className="mono">Market Map</span>
        </div>
      </div>

      <div className="tb-center">
        <div className="tb-cmd">
          <span className="tb-cmd-icon">⌕</span>
          <input placeholder="Quote, command (e.g. /verdict ARCM, /scan breakout)…" />
          <span className="kbd">/</span>
        </div>
      </div>

      <div className="tb-right">
        {(() => {
          // Scan freshness chip (audit #7) — surfaces the bundle age so a stale /
          // missed-scan dataset is visible instead of looking like today's scan.
          const m = (typeof window !== "undefined" && window.__BV && window.__BV.scanMeta) || null;
          if (!m || !m.ts) return null;
          const hrs = m.ageMin != null ? m.ageMin / 60 : null;
          const ageStr = hrs == null ? "" : (hrs < 1 ? Math.round(m.ageMin) + "m" : hrs.toFixed(hrs < 10 ? 1 : 0) + "h");
          const hhmm = String(m.ts).slice(11, 16);
          return (
            <div className="mono" title={`Scan bundle: ${m.ts} PT${m.stale ? " · STALE (>20h — scan may have been missed)" : ""}`}
              style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, padding: "2px 8px", borderRadius: 6, border: "1px solid var(--line)", color: m.stale ? "var(--amb)" : "var(--ink-3)", whiteSpace: "nowrap" }}>
              {m.stale ? "⚠ " : "● "}scan {hhmm}{ageStr ? " · " + ageStr + " old" : ""}
            </div>
          );
        })()}
        <div className="tb-mode" role="tablist" aria-label="Trade horizon mode">
          {["SWING", "POSITION", "INVESTMENT"].map(m => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={`tb-mode-btn ${mode === m ? "is-on" : ""}`}
              onClick={() => onMode(m)}
            >
              {m}
            </button>
          ))}
        </div>

        <button className="tb-icon" onClick={() => onTheme(theme === "dark" ? "light" : "dark")} title="Toggle theme">
          {theme === "dark" ? "☼" : "☾"}
        </button>

        <div className="tb-acct">
          <div className="tb-acct-row">
            <span className="label-cap">Account</span>
            <span className="mono">PAPER · $108,420</span>
          </div>
          <div className="tb-acct-row">
            <span className="label-cap">Today</span>
            <span className="mono up">+$1,284 · +1.20%</span>
          </div>
        </div>
      </div>
    </div>
  );
}

window.TopBar = TopBar;
