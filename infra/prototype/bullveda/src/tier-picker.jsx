// tier-picker.jsx — commercial tier switcher dropdown (top-right command bar)

const { useState: useStateTP, useEffect: useEffectTP, useRef: useRefTP } = React;

function TierPicker({ value, onChange }) {
  const [open, setOpen] = useStateTP(false);
  const ref = useRefTP(null);
  useEffectTP(() => {
    const onClick = (e) => {
      if (ref.current && ref.current.contains(e.target)) return;
      if (e.target.closest(".tp-menu")) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const tiers = window.TIER_LIST || [];
  const cur = tiers.find(t => t.id === value) || tiers[0];
  return (
    <div className="tp" ref={ref}>
      <button className="tp-btn" onClick={() => setOpen(o => !o)} title={`Subscription tier · ${cur?.name}`}>
        <span className="tp-badge mono">TIER {value}</span>
        <span className="tp-name mono">{cur?.name}</span>
        <span className="tp-caret">▾</span>
      </button>
      {open && ReactDOM.createPortal((
        <div className="tp-menu">
          <div className="tp-menu-hdr mono label-cap">Subscription tier · preview gating</div>
          {tiers.map(t => (
            <button key={t.id} className={`tp-opt ${value === t.id ? "is-on" : ""}`} onClick={() => { onChange(t.id); setOpen(false); }}>
              <span className="tp-opt-badge mono">T{t.id}</span>
              <span className="tp-opt-main">
                <span className="tp-opt-name mono">{t.name}</span>
                <span className="tp-opt-tag mono dim2">{t.tag}</span>
              </span>
              <span className="tp-opt-price mono">{t.price}</span>
            </button>
          ))}
          <div className="tp-menu-foot mono dim2">Switches which tabs &amp; lenses unlock. Locked surfaces show an upgrade gate.</div>
        </div>
      ), document.body)}
    </div>
  );
}

window.TierPicker = TierPicker;
