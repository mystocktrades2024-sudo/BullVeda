// theme-picker.jsx — curated theme palette picker (custom Tweak control)
// Renders rows of swatch-strip + name; selected has copper outline.

const THEMES = [
  { id: "midnight-cyan",   name: "Aurora Cyan",     sw: ["#0a0e14", "#5dd6d6", "#a78bfa", "#4ade80"] },
  { id: "deep-violet",     name: "Aurora Violet",   sw: ["#0d0b14", "#a78bfa", "#ec4899", "#4ade80"] },
  { id: "forest-terminal", name: "Aurora Mint",     sw: ["#0a100c", "#6ee098", "#5dd6d6", "#4ade80"] },
  { id: "obsidian-gold",   name: "Aurora Sunset",   sw: ["#0a0d0c", "#d97757", "#ec4899", "#4ade80"] },
  { id: "carbon-amber",    name: "Aurora Amber",    sw: ["#0d0d0d", "#fbbf24", "#ff9a76", "#4ade80"] },
  { id: "bronze-noir",     name: "Aurora Bronze",   sw: ["#08080a", "#c79152", "#a78bfa", "#4ade80"] },
  { id: "slate-mint",      name: "Aurora Slate",    sw: ["#0e1216", "#5ee3a8", "#5dd6d6", "#4ade80"] },
  { id: "arctic-light",    name: "Daylight Pearl",  sw: ["#f4f6fa", "#2563c8", "#6a4ad9", "#1e8a4a"] },
  { id: "ivory-editorial", name: "Daylight Sand",   sw: ["#f6f5f1", "#b85d3e", "#a8421a", "#1e8a4a"] },
];

function ThemePicker({ value, onChange }) {
  return (
    <div className="tk-themes">
      {THEMES.map(t => (
        <button
          key={t.id}
          className={`tk-theme ${value === t.id ? "is-on" : ""}`}
          onClick={() => onChange(t.id)}
          title={t.name}
        >
          <span className="tk-theme-sw">
            {t.sw.map((c, i) => (
              <span key={i} className="tk-theme-chip" style={{ background: c }} />
            ))}
          </span>
          <span className="tk-theme-name">{t.name}</span>
        </button>
      ))}
    </div>
  );
}

window.ThemePicker = ThemePicker;
window.THEMES = THEMES;
