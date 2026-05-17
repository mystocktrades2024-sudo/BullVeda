// tabs/elite/helpers.js — pure helpers used across elite-tab sub-modules.
// Tier classifier, stage badge, mode label, $ formatter, score arc SVG.
// No DOM, no DATA dependency.

export function tier(score) {
  if (score >= 80) return { label: 'ELITE',    color: 'var(--green)',   bg: 'color-mix(in oklch, var(--green) 12%, transparent)' };
  if (score >= 65) return { label: 'HIGH',     color: 'var(--info)',    bg: 'color-mix(in oklch, var(--info) 12%, transparent)' };
  if (score >= 50) return { label: 'MARGINAL', color: 'var(--ink-1)',   bg: 'var(--bg-2)' };
  return                  { label: 'WEAK',     color: 'var(--paper-3)', bg: 'var(--bg-2)' };
}

export function stageBadge(stage) {
  if (stage === 'BUY')   return { label: 'BUY',   color: 'var(--green)',  icon: '▲' };
  if (stage === 'SHORT') return { label: 'SHORT', color: 'var(--red)',    icon: '▼' };
  return                       { label: 'WATCH', color: 'var(--accent)', icon: '◆' };
}

export function modeLabel(mode) {
  return mode === 'Swing'    ? 'Swing · 2-14d'
       : mode === 'Position' ? 'Position · 3-8w'
       :                       'Invest · 12+mo';
}

export function money(v) { return v != null ? '$' + (+v).toFixed(2) : '—'; }

// Score arc SVG — reusable, sized via params. Used by hero card + track row.
export function arc(score, color, size = 68, font = 18) {
  const r  = (size - 12) / 2;
  const C  = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const cx = size / 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex-shrink:0">
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="3"/>
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"
            transform="rotate(-90 ${cx} ${cx})"/>
    <text x="${cx}" y="${cx}" text-anchor="middle" dominant-baseline="central"
          font-size="${font}" font-weight="800" font-family="var(--mono)" fill="${color}">${Math.round(score)}</text>
  </svg>`;
}
