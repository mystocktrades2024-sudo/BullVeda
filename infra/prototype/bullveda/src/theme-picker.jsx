// theme-picker.jsx — curated theme palette picker (custom Tweak control)
// Renders rows of swatch-strip + name; selected has copper outline.

const THEMES = [
  { id: "bold-volt",       name: "⚡ Voltage Mint",  sw: ["#05080a", "#15e8a6", "#ff5d6c", "#ffc83d"], bold: true },
  { id: "bold-ion",        name: "⚡ Ion Cyan",      sw: ["#04070e", "#1fe0e6", "#ff5277", "#ffd23d"], bold: true },
  { id: "bold-acid",       name: "⚡ Acid Terminal", sw: ["#060a05", "#b6f53a", "#ff6a4d", "#8df03a"], bold: true },
  { id: "bold-plasma",     name: "⚡ Plasma",        sw: ["#07060c", "#ff3d8b", "#25f0a8", "#ffc23d"], bold: true },
  { id: "midnight-cyan",   name: "Aurora Cyan",     sw: ["#0a0e14", "#5dd6d6", "#a78bfa", "#4ade80"] },
  { id: "deep-violet",     name: "Aurora Violet",   sw: ["#0d0b14", "#a78bfa", "#ec4899", "#4ade80"] },
  { id: "forest-terminal", name: "Aurora Mint",     sw: ["#0a100c", "#6ee098", "#5dd6d6", "#4ade80"] },
  { id: "obsidian-gold",   name: "Aurora Sunset",   sw: ["#0a0d0c", "#d97757", "#ec4899", "#4ade80"] },
  { id: "carbon-amber",    name: "Aurora Amber",    sw: ["#0d0d0d", "#fbbf24", "#ff9a76", "#4ade80"] },
  { id: "bronze-noir",     name: "Aurora Bronze",   sw: ["#08080a", "#c79152", "#a78bfa", "#4ade80"] },
  { id: "slate-mint",      name: "Aurora Slate",    sw: ["#0e1216", "#5ee3a8", "#5dd6d6", "#4ade80"] },
  { id: "aurora-rose",     name: "Aurora Rose",     sw: ["#140a10", "#fb7199", "#a78bfa", "#4ade80"] },
  { id: "aurora-ice",      name: "Aurora Ice",      sw: ["#0a0f16", "#5b9bf2", "#5dd6d6", "#4ade80"] },
  { id: "aurora-lime",     name: "Aurora Lime",     sw: ["#0c1009", "#a3e635", "#5dd6d6", "#4ade80"] },
  { id: "matte-carbon",    name: "Matte Carbon",    sw: ["#161616", "#e0a030", "#7c8aa0", "#3fa46a"] },
  { id: "matte-graphite",  name: "Matte Graphite",  sw: ["#14181d", "#4cc5c5", "#8a93a3", "#3fa46a"] },
  { id: "matte-navy",      name: "Matte Navy",      sw: ["#12161f", "#5b8def", "#8089a0", "#3fa46a"] },
  { id: "arctic-light",    name: "Daylight Pearl",  sw: ["#f4f6fa", "#2563c8", "#6a4ad9", "#1e8a4a"] },
  { id: "ivory-editorial", name: "Daylight Sand",   sw: ["#f6f5f1", "#b85d3e", "#a8421a", "#1e8a4a"] },
  { id: "paper-flat",      name: "Paper Flat",      sw: ["#eeeae2", "#9a5a2c", "#5a6a4a", "#1e8a4a"] },
  { id: "custom-crimson",  name: "Crimson Noir",    sw: ["#0e0a0b", "#f0556a", "#c79bf0", "#4ade80"], custom: true },
  { id: "custom-gold",     name: "Gold Noir",       sw: ["#0b0b0c", "#d4af37", "#b79bf0", "#4ade80"], custom: true },
  { id: "custom-indigo",   name: "Electric Indigo", sw: ["#0a0c16", "#818cf8", "#a78bfa", "#4ade80"], custom: true },
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
