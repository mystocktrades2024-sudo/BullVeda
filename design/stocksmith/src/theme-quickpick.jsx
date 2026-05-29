// theme-quickpick.jsx — inline theme swatch picker for the command bar.
// Renders a single circle (current theme) that opens a small popover of all themes.

const { useState: useStateTQ, useEffect: useEffectTQ, useRef: useRefTQ } = React;

function ThemeQuickPick({ value, onChange }) {
  const [open, setOpen] = useStateTQ(false);
  const ref = useRefTQ(null);
  useEffectTQ(() => {
    const onClick = (e) => {
      // Don't close if click is inside the button OR inside the portaled menu
      if (ref.current && ref.current.contains(e.target)) return;
      if (e.target.closest(".tqp-menu")) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const current = (window.THEMES || []).find(t => t.id === value) || (window.THEMES || [])[0];
  return (
    <div className="tqp" ref={ref}>
      <button className="tqp-btn" onClick={() => setOpen(o => !o)} title={`Theme · ${current?.name || value}`}>
        <span className="tqp-current">
          {current && current.sw.slice(0, 3).map((c, i) => (
            <span key={i} className="tqp-chip" style={{ background: c }} />
          ))}
        </span>
        <span className="tqp-name mono">{current?.name?.replace(/^Aurora |^Daylight /, "") || "Theme"}</span>
        <span className="tqp-caret">▾</span>
      </button>
      {open && ReactDOM.createPortal((
        <div className="tqp-menu">
          <div className="tqp-menu-hdr mono label-cap">Theme palette</div>
          <div className="tqp-menu-groups">
            {[
              { lbl: "GLOSSY · GLASS", test: t => !t.id.startsWith("matte-") && t.id !== "paper-flat" && !t.id.startsWith("arctic") && !t.id.startsWith("ivory") },
              { lbl: "FLAT · MATTE",   test: t => t.id.startsWith("matte-") },
              { lbl: "LIGHT",          test: t => t.id.startsWith("arctic") || t.id.startsWith("ivory") || t.id === "paper-flat" },
            ].map((grp, gi) => (
              <React.Fragment key={grp.lbl}>
                <div className="tqp-group-lbl mono dim2" style={{ marginTop: gi ? 6 : 0 }}>{grp.lbl}</div>
                {(window.THEMES || []).filter(grp.test).map(t => (
                  <button key={t.id} className={`tqp-opt ${value === t.id ? "is-on" : ""}`} onClick={() => { onChange(t.id); setOpen(false); }}>
                    <span className="tqp-opt-sw">{t.sw.slice(0, 4).map((c, i) => <span key={i} className="tqp-chip" style={{ background: c }} />)}</span>
                    <span className="tqp-opt-name">{t.name}</span>
                  </button>
                ))}
              </React.Fragment>
            ))}
          </div>
        </div>
      ), document.body)}
    </div>
  );
}

window.ThemeQuickPick = ThemeQuickPick;
