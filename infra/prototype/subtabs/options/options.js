// subtabs/options/options.js — extracted from elite-detail.html (renderOptionsTab 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const k = T.options_kpis || {};
  const v = k.verdict || {};
  const verdict = (v.verdict || 'NO_DATA').toUpperCase();
  const confidence = v.confidence || 'LOW';
  const edge = v.edge != null ? v.edge : 0;
  const thesis = v.thesis || 'Options data unavailable — Schwab refresh token may have expired. Run python3 schwab_auth.py oauth to re-enable IV / UOA / put-call signals.';
  const narrative = v.narrative || '';
  const confluences = v.confluences || [];

  // Color tokens by verdict
  const vColor = {
    BULLISH: 'var(--pass)', BEARISH: 'var(--fail)',
    MIXED: 'var(--warn)', NEUTRAL: 'var(--ink-2)', NO_DATA: 'var(--ink-3)'
  }[verdict] || 'var(--ink-2)';
  const vIcon = {BULLISH:'▲', BEARISH:'▼', MIXED:'◆', NEUTRAL:'■', NO_DATA:'○'}[verdict] || '○';
  const confColor = {HIGH:'var(--pass)', MED:'var(--warn)', LOW:'var(--ink-3)'}[confidence] || 'var(--ink-3)';

  // KPI extracts
  const ivPct = k.iv_percentile;
  const ivCur = k.iv_current;
  const pc = k.put_call_ratio;
  const uoaC = k.uoa_calls;
  const uoaP = k.uoa_puts;
  const uoaCDetail = k.uoa_call_detail;
  const uoaPDetail = k.uoa_put_detail;
  const skew = k.skew_25d;
  const term = k.term_structure || {};
  const gamma = k.gamma_net;
  const maxPain = k.max_pain;
  const callOI = k.total_call_oi || 0;
  const putOI = k.total_put_oi || 0;
  const callVol = k.total_call_vol || 0;
  const putVol = k.total_put_vol || 0;

  // Per-mode overlay
  const pm = k.per_mode || {};
  const swingMode = pm.swing || {};
  const positionMode = pm.position || {};
  const investMode = pm.invest || {};

  // Base scores from T (the existing per-mode scoring)
  const swingScore = T.score || 0;
  const swingVerdict = T.verdict || T.stage || 'WATCH';
  const positionScore = T.medium_term_score || '—';
  const positionVerdict = T.medium_term_verdict || '—';
  const positionGateStatus = T.medium_term_gate_status || '';
  const positionGateReasons = T.medium_term_gate_reasons || [];
  const investScore = T.long_term_score || '—';
  const investVerdict = T.long_term_verdict || '—';

  const fmtDelta = d => d > 0 ? `+${d}` : (d < 0 ? `${d}` : '0');
  const statusBadge = s => {
    const m = {CONFIRMED:'pass', CAUTIONED:'warn', CONTRADICTED:'fail', NEUTRAL:'info', NO_DATA:'info'};
    return m[s] || 'info';
  };
  const px = n => n != null ? '$' + (+n).toFixed(2) : '—';

  $('optionsBody').innerHTML = `
    <!-- ═══════════ HERO VERDICT TILE ═══════════ -->
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
    </div>

    <!-- ═══════════ KPI ROW — IV REGIME · FLOW · POSITIONING ═══════════ -->
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
    </div>

    <!-- ═══════════ PER-MODE OVERLAY ═══════════ -->
    <div style="margin-bottom:20px;">
      <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; text-transform:uppercase; color:var(--ink-3); margin-bottom:10px; font-weight:600;">
        How options flow modifies conviction per holding period
      </div>
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:14px;">
        ${[
          {mode: swingMode, name:'SWING', subtitle:'2–21 day hold', baseScore:swingScore, baseVerdict:swingVerdict, color:'var(--swing, #60a5fa)', gateReasons:[], gateStatus:''},
          {mode: positionMode, name:'POSITION', subtitle:'1–3 month hold', baseScore:positionScore, baseVerdict:positionVerdict, color:'var(--position, #a78bfa)', gateReasons:positionGateReasons, gateStatus:positionGateStatus},
          {mode: investMode, name:'INVEST', subtitle:'6–12 month hold', baseScore:investScore, baseVerdict:investVerdict, color:'var(--invest, #34d399)', gateReasons:[], gateStatus:''}
        ].map(m => {
          const status = m.mode.status || 'NO_DATA';
          const sCls = statusBadge(status);
          const sColor = {pass:'var(--pass)', warn:'var(--warn)', fail:'var(--fail)', info:'var(--ink-2)'}[sCls];
          const delta = m.mode.score_delta || 0;
          const adjScore = (typeof m.baseScore === 'number') ? m.baseScore + delta : null;
          const arrow = delta > 0 ? '↑' : delta < 0 ? '↓' : '→';
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
                  const c = isHard ? 'var(--fail)' : isSoft ? 'var(--warn)' : 'var(--ink-2)';
                  return `<div style="font-size:10.5px; color:${c}; line-height:1.4; margin:2px 0;">• ${r}</div>`;
                }).join('')}
              </div>` : ''}
          </div>`;
        }).join('')}
      </div>
    </div>

    <!-- ═══════════ INSTITUTIONAL READ ═══════════ -->
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

export function dispose() { /* no-op */ }
