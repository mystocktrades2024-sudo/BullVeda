// tabs/earnings/banner.js — STRONG / SOLID beat-prediction banner.
// Returns the HTML string for the top banner (priority: STRONG > SOLID > none).

export function buildBeatBanner(predictions) {
  const strong = (predictions || []).filter(p => p.tier === 'STRONG');
  const solid  = (predictions || []).filter(p => p.tier === 'SOLID');

  if (strong.length > 0) {
    return `
      <div style="margin-bottom:14px;padding:14px 18px;background:linear-gradient(90deg, color-mix(in oklch, var(--green) 18%, var(--bg-1)) 0%, var(--bg-1) 70%);border:1px solid var(--green);border-left:4px solid var(--green);border-radius:8px;">
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
          <span style="font-size:18px;">🎯</span>
          <div style="flex:1;min-width:200px;">
            <div style="font-weight:700;color:var(--green);font-size:13px;letter-spacing:0.04em;">${strong.length} STRONG beat-prediction${strong.length>1?'s':''}</div>
            <div style="color:var(--ink-2);font-size:11.5px;margin-top:3px;">
              ${strong.map(p => `<a href="#" onclick="window.setDetailTicker && window.setDetailTicker('${p.ticker}'); return false;" style="color:var(--ink-0);text-decoration:none;font-weight:700;">${p.ticker}</a>(${p.beat_score.toFixed(0)}, ${p.days_to_earnings}d)`).join(' · ')}
            </div>
          </div>
          <button onclick="_earnFilterChange('beat','STRONG')" style="padding:7px 14px;background:var(--green);border:none;border-radius:5px;color:var(--bg-0);font-weight:700;cursor:pointer;font-family:DM Sans;font-size:11px;letter-spacing:0.06em;">FILTER →</button>
        </div>
      </div>`;
  }
  if (solid.length > 0) {
    return `
      <div style="margin-bottom:14px;padding:12px 16px;background:color-mix(in oklch, var(--accent) 10%, var(--bg-1));border:1px solid color-mix(in oklch, var(--accent) 40%, var(--rule));border-radius:8px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:14px;color:var(--accent);">◆</span>
          <span style="color:var(--ink-2);font-size:11.5px;">No STRONG beat predictions today, but <b style="color:var(--accent)">${solid.length} SOLID</b> candidates are close. </span>
          <button onclick="_earnFilterChange('beat','SOLID')" style="margin-left:auto;padding:5px 11px;background:transparent;border:1px solid var(--accent);border-radius:4px;color:var(--accent);font-weight:700;cursor:pointer;font-family:DM Sans;font-size:11px;">VIEW SOLID</button>
        </div>
      </div>`;
  }
  return '';
}
