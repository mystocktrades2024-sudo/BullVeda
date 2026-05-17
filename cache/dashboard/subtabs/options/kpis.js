// subtabs/options/kpis.js — Hero verdict tile + 3 KPI tiles (IV / Flow / Positioning).
// Returns one HTML chunk.

const px = n => n != null ? '$' + (+n).toFixed(2) : '—';

export function buildHero(ctx) {
  const { verdict, vColor, vIcon, edge, confidence, confColor, confluences, thesis } = ctx;
  return `
    <!-- HERO VERDICT TILE -->
    <div class="opt-verdict-hero" style="border:1px solid ${vColor}; border-left:4px solid ${vColor}; border-radius:10px; padding:24px 28px; margin-bottom:20px; background:linear-gradient(135deg, color-mix(in oklch, ${vColor} 8%, var(--bg-1)) 0%, var(--bg-1) 60%);">
      <div style="display:flex; align-items:flex-start; gap:18px; margin-bottom:16px;">
        <div style="font-size:42px; color:${vColor}; line-height:1; font-weight:700;">${vIcon}</div>
        <div style="flex:1;">
          <div style="font-family:var(--mono); font-size:10.5px; letter-spacing:0.18em; color:var(--ink-3); text-transform:uppercase; margin-bottom:4px;">Options Verdict</div>
          <div style="font-size:30px; font-weight:800; color:${vColor}; letter-spacing:-0.01em; line-height:1.1; margin-bottom:6px;">${verdict}</div>
          <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap;">
            <span style="display:inline-flex; align-items:center; gap:6px; font-family:var(--mono); font-size:11px; color:var(--ink-2);">
              <span style="color:var(--ink-3); letter-spacing:0.12em; text-transform:uppercase;">Edge</span>
              <span style="color:${vColor}; font-weight:700; font-size:13px;">${edge}/10</span>
            </span>
            <span style="display:inline-flex; align-items:center; gap:6px; font-family:var(--mono); font-size:11px; color:var(--ink-2);">
              <span style="color:var(--ink-3); letter-spacing:0.12em; text-transform:uppercase;">Confidence</span>
              <span style="color:${confColor}; font-weight:700;">${confidence}</span>
            </span>
            <span style="display:inline-flex; align-items:center; gap:6px; font-family:var(--mono); font-size:11px; color:var(--ink-2);">
              <span style="color:var(--ink-3); letter-spacing:0.12em; text-transform:uppercase;">Confluences</span>
              <span style="color:var(--ink-0); font-weight:700;">${confluences.length}</span>
            </span>
          </div>
        </div>
      </div>
      <div style="font-size:14.5px; line-height:1.65; color:var(--ink-1); margin-bottom:14px; max-width:120ch;">
        ${thesis}
      </div>
      ${confluences.length > 0 ? `
        <div style="display:flex; gap:6px; flex-wrap:wrap; padding-top:12px; border-top:1px dashed var(--rule);">
          ${confluences.slice(0, 6).map(c => `<span style="display:inline-block; padding:3px 9px; border-radius:4px; font-family:var(--mono); font-size:10.5px; background:color-mix(in oklch, ${vColor} 12%, transparent); color:${vColor}; border:1px solid color-mix(in oklch, ${vColor} 30%, transparent); font-weight:600;">${c}</span>`).join('')}
        </div>` : ''}
    </div>`;
}

export function buildKpiRow(ctx) {
  const { ivPct, ivCur, term, uoaC, uoaP, uoaCDetail, uoaPDetail, pc, callVol, putVol,
          gamma, maxPain, skew, callOI, putOI } = ctx;

  return `
    <div class="opt-grid" style="display:grid; grid-template-columns:repeat(3, 1fr); gap:14px; margin-bottom:20px;">

      <!-- IV REGIME -->
      <div class="opt-tile ${ivPct == null ? 'info' : ivPct < 35 ? 'pass' : ivPct > 75 ? 'fail' : 'warn'}" style="padding:18px;">
        <div class="lbl" style="margin-bottom:8px;">IV Regime</div>
        <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:6px;">
          <div class="opt-v" style="font-size:30px;">${ivPct != null ? ivPct : '—'}</div>
          <div style="font-size:11px; color:var(--ink-3); font-family:var(--mono);">/100 RANK</div>
        </div>
        ${ivPct != null ? `<div style="height:6px; border-radius:3px; background:var(--bg-3); overflow:hidden; margin:8px 0;">
          <div style="height:100%; width:${Math.min(100,Math.max(0,ivPct))}%; background:${ivPct < 35 ? 'var(--pass)' : ivPct > 75 ? 'var(--fail)' : 'var(--warn)'};"></div>
        </div>` : ''}
        <div class="opt-sub" style="font-size:11.5px;">
          ${ivPct == null ? 'no data' : ivPct < 35 ? 'CHEAP — upside not priced in' : ivPct > 75 ? 'EXPENSIVE — fear priced' : 'MODERATE — typical regime'}
        </div>
        ${ivCur != null ? `<div style="font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-top:6px;">Current IV: ${ivCur}%</div>` : ''}
        ${term.structure ? `<div style="font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-top:3px;">Term: ${term.structure} (front ${term.front_iv}% / back ${term.back_iv}%)</div>` : ''}
      </div>

      <!-- FLOW SIGNAL -->
      <div class="opt-tile ${(uoaC || uoaP) ? (uoaC && !uoaP ? 'pass' : uoaP && !uoaC ? 'fail' : 'warn') : 'info'}" style="padding:18px;">
        <div class="lbl" style="margin-bottom:8px;">Flow Signal</div>
        <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:6px;">
          <div class="opt-v" style="font-size:24px;">
            ${uoaC && uoaP ? 'BOTH' : uoaC ? 'CALLS' : uoaP ? 'PUTS' : 'QUIET'}
          </div>
        </div>
        <div class="opt-sub" style="font-size:11.5px; line-height:1.5;">
          ${uoaC ? `<div style="color:var(--pass); margin-bottom:3px;"><b>CALL UOA</b> ${uoaCDetail || ''}</div>` : ''}
          ${uoaP ? `<div style="color:var(--fail); margin-bottom:3px;"><b>PUT UOA</b> ${uoaPDetail || ''}</div>` : ''}
          ${!uoaC && !uoaP ? 'No unusual single-strike activity' : ''}
        </div>
        ${pc != null ? `<div style="font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-top:8px; padding-top:6px; border-top:1px dashed var(--rule);">P/C OI: <b style="color:${pc<0.7?'var(--pass)':pc>1.3?'var(--fail)':'var(--ink-1)'}">${pc}</b> · Vol calls/puts: ${(callVol/1000).toFixed(0)}K / ${(putVol/1000).toFixed(0)}K</div>` : ''}
      </div>

      <!-- POSITIONING -->
      <div class="opt-tile ${gamma != null ? (gamma > 0 ? 'pass' : 'warn') : 'info'}" style="padding:18px;">
        <div class="lbl" style="margin-bottom:8px;">Positioning</div>
        <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:6px;">
          <div class="opt-v" style="font-size:22px;">
            ${gamma != null ? (gamma > 0 ? '+' : '') + (Math.abs(gamma) > 1e6 ? (gamma/1e6).toFixed(1) + 'M' : (gamma/1e3).toFixed(0) + 'K') : '—'}
          </div>
          <div style="font-size:11px; color:var(--ink-3); font-family:var(--mono);">NET Γ</div>
        </div>
        <div class="opt-sub" style="font-size:11.5px; line-height:1.5;">
          ${gamma == null ? 'no gamma data' : gamma > 0 ? 'STABILIZING — dealers buy dips' : 'AMPLIFYING — moves accelerated'}
        </div>
        ${maxPain ? `<div style="font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-top:8px; padding-top:6px; border-top:1px dashed var(--rule);">Max Pain: <b style="color:var(--ink-1)">${px(maxPain)}</b> · Skew 25Δ: <b style="color:${skew!=null?(skew<0?'var(--pass)':skew>3?'var(--fail)':'var(--ink-1)'):'var(--ink-3)'}">${skew != null ? (skew > 0 ? '+' : '') + skew : '—'}</b></div>` : ''}
        <div style="font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-top:3px;">OI calls/puts: ${(callOI/1000).toFixed(0)}K / ${(putOI/1000).toFixed(0)}K</div>
      </div>
    </div>`;
}
