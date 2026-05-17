// subtabs/options/per_mode.js — Per-mode overlay (Swing / Position / Invest)
// + Institutional Read panel. Returns one HTML chunk.

const fmtDelta = d => d > 0 ? `+${d}` : (d < 0 ? `${d}` : '0');
const _statusBadge = s => {
  const m = { CONFIRMED: 'pass', CAUTIONED: 'warn', CONTRADICTED: 'fail', NEUTRAL: 'info', NO_DATA: 'info' };
  return m[s] || 'info';
};

export function buildPerModeOverlay(ctx) {
  const { swingMode, positionMode, investMode,
          swingScore, swingVerdict, positionScore, positionVerdict,
          positionGateStatus, positionGateReasons,
          investScore, investVerdict } = ctx;

  const modes = [
    { mode: swingMode,    name: 'SWING',    subtitle: '2–21 day hold',  baseScore: swingScore,    baseVerdict: swingVerdict,    color: 'var(--swing, #60a5fa)',     gateReasons: [],                 gateStatus: '' },
    { mode: positionMode, name: 'POSITION', subtitle: '1–3 month hold', baseScore: positionScore, baseVerdict: positionVerdict, color: 'var(--position, #a78bfa)',  gateReasons: positionGateReasons, gateStatus: positionGateStatus },
    { mode: investMode,   name: 'INVEST',   subtitle: '6–12 month hold',baseScore: investScore,   baseVerdict: investVerdict,   color: 'var(--invest, #34d399)',    gateReasons: [],                 gateStatus: '' },
  ];

  return `
    <div style="margin-bottom:20px;">
      <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; text-transform:uppercase; color:var(--ink-3); margin-bottom:10px; font-weight:600;">
        How options flow modifies conviction per holding period
      </div>
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:14px;">
        ${modes.map(m => {
          const status   = m.mode.status || 'NO_DATA';
          const sCls     = _statusBadge(status);
          const sColor   = { pass: 'var(--pass)', warn: 'var(--warn)', fail: 'var(--fail)', info: 'var(--ink-2)' }[sCls];
          const delta    = m.mode.score_delta || 0;
          const adjScore = (typeof m.baseScore === 'number') ? m.baseScore + delta : null;
          const arrow    = delta > 0 ? '↑' : delta < 0 ? '↓' : '→';
          return `
          <div style="background:var(--bg-1); border:1px solid var(--rule); border-top:3px solid ${m.color}; border-radius:8px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;">
              <div>
                <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.14em; color:${m.color}; font-weight:700;">${m.name}</div>
                <div style="font-size:10.5px; color:var(--ink-3); margin-top:2px;">${m.subtitle}</div>
              </div>
              <span style="display:inline-block; padding:3px 8px; border-radius:4px; font-family:var(--mono); font-size:10px; font-weight:700; letter-spacing:0.06em; background:color-mix(in oklch, ${sColor} 14%, transparent); color:${sColor}; border:1px solid color-mix(in oklch, ${sColor} 30%, transparent);">${status}</span>
            </div>
            <div style="display:flex; align-items:baseline; gap:10px; margin-bottom:8px;">
              <div style="font-size:24px; font-weight:800; color:var(--ink-0);">${m.baseScore}</div>
              <div style="font-size:14px; color:var(--ink-3); font-family:var(--mono);">${arrow} ${adjScore != null ? adjScore : '—'}</div>
              <div style="font-size:11px; color:${delta>0?'var(--pass)':delta<0?'var(--fail)':'var(--ink-3)'}; font-family:var(--mono); font-weight:700;">${fmtDelta(delta)}</div>
            </div>
            <div style="font-size:11px; color:var(--ink-2); font-family:var(--mono); letter-spacing:0.06em; margin-bottom:10px; text-transform:uppercase;">
              Base: <b style="color:var(--ink-0)">${m.baseVerdict}</b> · Edge: <b style="color:${m.mode.edge==='HIGH'?'var(--pass)':m.mode.edge==='LOW'?'var(--fail)':'var(--ink-1)'}">${m.mode.edge || '—'}</b>
            </div>
            <div style="font-size:12.5px; line-height:1.55; color:var(--ink-1); padding-top:10px; border-top:1px dashed var(--rule);">
              ${m.mode.narrative || 'Options flow not directional for this horizon'}
            </div>
            ${(m.gateReasons && m.gateReasons.length > 0) ? `
              <div style="margin-top:10px; padding-top:8px; border-top:1px dashed var(--rule);">
                <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.12em; color:var(--ink-3); text-transform:uppercase; margin-bottom:4px; font-weight:600;">Gate reasons (${m.gateStatus || 'unknown'})</div>
                ${m.gateReasons.slice(0, 5).map(r => {
                  const isHard = r.startsWith('HARD');
                  const isSoft = r.startsWith('SOFT');
                  const c      = isHard ? 'var(--fail)' : isSoft ? 'var(--warn)' : 'var(--ink-2)';
                  return `<div style="font-size:10.5px; color:${c}; line-height:1.4; margin:2px 0;">• ${r}</div>`;
                }).join('')}
              </div>` : ''}
          </div>`;
        }).join('')}
      </div>
    </div>`;
}

export function buildInstitutionalRead(ctx) {
  const { uoaC, uoaP, uoaCDetail, uoaPDetail, callOI, putOI, callVol, putVol, verdict } = ctx;

  return `
    <div style="background:var(--bg-1); border:1px solid var(--rule); border-radius:8px; padding:18px;">
      <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; text-transform:uppercase; color:var(--ink-3); margin-bottom:14px; font-weight:600;">
        Institutional Read
      </div>
      <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:18px;">
        <div>
          <div style="font-size:13px; color:var(--ink-1); margin-bottom:10px; font-weight:600;">Notable Recent Prints</div>
          ${(uoaC || uoaP) ? `
            ${uoaC ? `<div style="display:flex; align-items:center; gap:10px; padding:8px 10px; background:color-mix(in oklch, var(--pass) 8%, transparent); border-radius:5px; margin-bottom:6px;">
              <span style="color:var(--pass); font-size:14px;">▲</span>
              <span style="font-family:var(--mono); font-size:11.5px; color:var(--ink-1); flex:1;">${uoaCDetail || 'Call sweep detected'}</span>
              <span style="font-family:var(--mono); font-size:10px; color:var(--pass); font-weight:700;">CALL UOA</span>
            </div>` : ''}
            ${uoaP ? `<div style="display:flex; align-items:center; gap:10px; padding:8px 10px; background:color-mix(in oklch, var(--fail) 8%, transparent); border-radius:5px; margin-bottom:6px;">
              <span style="color:var(--fail); font-size:14px;">▼</span>
              <span style="font-family:var(--mono); font-size:11.5px; color:var(--ink-1); flex:1;">${uoaPDetail || 'Put block detected'}</span>
              <span style="font-family:var(--mono); font-size:10px; color:var(--fail); font-weight:700;">PUT UOA</span>
            </div>` : ''}
          ` : `<div style="padding:12px; color:var(--ink-3); font-size:12px; text-align:center; background:var(--bg-2); border-radius:5px;">No unusual single-strike prints detected today.</div>`}
        </div>
        <div>
          <div style="font-size:13px; color:var(--ink-1); margin-bottom:10px; font-weight:600;">Net Positioning</div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-family:var(--mono); font-size:11.5px;">
            <div style="padding:8px 10px; background:var(--bg-2); border-radius:5px;"><div style="color:var(--ink-3); font-size:10px;">CALL OI</div><div style="color:var(--pass); font-weight:700;">${(callOI/1000).toFixed(0)}K</div></div>
            <div style="padding:8px 10px; background:var(--bg-2); border-radius:5px;"><div style="color:var(--ink-3); font-size:10px;">PUT OI</div><div style="color:var(--fail); font-weight:700;">${(putOI/1000).toFixed(0)}K</div></div>
            <div style="padding:8px 10px; background:var(--bg-2); border-radius:5px;"><div style="color:var(--ink-3); font-size:10px;">CALL VOL</div><div style="color:var(--ink-1); font-weight:700;">${(callVol/1000).toFixed(0)}K</div></div>
            <div style="padding:8px 10px; background:var(--bg-2); border-radius:5px;"><div style="color:var(--ink-3); font-size:10px;">PUT VOL</div><div style="color:var(--ink-1); font-weight:700;">${(putVol/1000).toFixed(0)}K</div></div>
          </div>
        </div>
      </div>
      ${verdict === 'NO_DATA' ? `
        <div style="margin-top:14px; padding:10px 14px; background:color-mix(in oklch, var(--warn) 8%, transparent); border:1px solid color-mix(in oklch, var(--warn) 30%, transparent); border-radius:5px; color:var(--warn); font-size:11.5px; line-height:1.5;">
          <b>Schwab refresh token expired.</b> Schwab tokens roll every 7 days. Re-authenticate in a browser session: <code style="font-family:var(--mono); background:var(--bg-3); padding:1px 5px; border-radius:3px;">python3 schwab_auth.py oauth</code>. After re-auth, the next scan will populate IV rank, UOA, put/call, max-pain, and gamma-exposure for institutional-flow analysis.
        </div>` : ''}
    </div>`;
}
