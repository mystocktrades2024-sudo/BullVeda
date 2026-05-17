// tabs/performance/calibration.js — Score Calibration bars.
// Shows signal distribution across conviction tiers (90+/80-89/70-79/60-69/<60).
// Returns an HTML string consumed by the entry orchestrator.

const ORDER = ['90+', '80-89', '70-79', '60-69', '<60'];

export function buildCalibration(scoreBuckets, closed) {
  const totalScored = Object.values(scoreBuckets).reduce((a, b) => a + b, 0) || 1;

  return `
    <div style="background:var(--surf-card); border:1px solid var(--line); border-radius:8px; padding:18px 22px; margin-bottom:14px;">
      <div style="margin-bottom:14px;">
        <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700;">Score Calibration</div>
        <div style="font-size:14px; color:var(--paper); margin-top:2px;">Signal distribution across conviction tiers — higher score should mean higher quality</div>
      </div>
      ${ORDER.filter(k => scoreBuckets[k]).map(k => {
        const count    = scoreBuckets[k];
        const pct      = count / totalScored * 100;
        const barColor = k === '90+' ? 'var(--green)' : k === '80-89' ? 'var(--accent-2)' : k === '70-79' ? 'var(--accent)' : k === '60-69' ? 'var(--paper-3)' : 'var(--paper-4)';
        const tierLabel = k === '90+' ? 'T1 elite' : k === '80-89' ? 'T1' : k === '70-79' ? 'T2' : k === '60-69' ? 'T3 / WATCH' : 'below threshold';
        return `
          <div style="display:grid; grid-template-columns:80px 1fr 100px 60px; gap:14px; padding:9px 0; border-bottom:1px dashed var(--line); align-items:center;">
            <div>
              <div style="font-family:var(--mono); font-size:14px; font-weight:800; color:${barColor};">${k}</div>
              <div style="font-size:10px; color:var(--paper-3); letter-spacing:0.06em; text-transform:uppercase;">${tierLabel}</div>
            </div>
            <div style="background:var(--surf-elev); height:18px; border-radius:4px; overflow:hidden;">
              <div style="background:${barColor}; height:100%; width:${pct}%; transition:width 320ms;"></div>
            </div>
            <div style="font-family:var(--mono); font-size:14px; color:var(--paper); font-weight:700; text-align:right;">${count} signals</div>
            <div style="font-family:var(--mono); font-size:13px; color:var(--paper-3); text-align:right;">${pct.toFixed(1)}%</div>
          </div>
        `;
      }).join('')}
      <div style="margin-top:14px; padding-top:10px; border-top:1px dashed var(--line); font-size:11.5px; color:var(--paper-3); line-height:1.6;">
        <b style="color:var(--paper);">How to read:</b> If 90+ signals win at higher rates than 60-69 → conviction score is predictive. If they're flat → score is noise.
        ${closed >= 30 ? 'Your data is statistically meaningful (N≥30).' : 'Need 30+ closed trades to compute per-bucket win rates with confidence.'}
      </div>
    </div>`;
}
