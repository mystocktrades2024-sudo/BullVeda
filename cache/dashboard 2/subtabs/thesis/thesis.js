// subtabs/thesis/thesis.js — extracted from elite-detail.html (renderThesisDetail 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const body = document.getElementById('thesisSecBody');
  if (!body) return;
  const th = (T && (T.thesis_card || (typeof T.thesis === 'object' ? T.thesis : null))) || null;
  if (!th || th.error) {
    body.innerHTML = `<div style="color:var(--ink-2);font-size:13px;padding:8px 0;">No thesis available${th && th.error ? ` — ${th.error}` : ''}.</div>`;
    return;
  }
  // Defensive coercion — never render an object directly as text
  const _s = (v, fallback = '') => {
    if (v == null) return fallback;
    if (typeof v === 'string' || typeof v === 'number') return String(v);
    if (typeof v === 'object') return v.label || v.name || v.value || JSON.stringify(v).slice(0, 60);
    return String(v);
  };
  const escape = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const verdict = _s(th.verdict, '?');
  const verdictColor = verdict === 'BUY' ? 'var(--pass)' : verdict === 'SELL' ? 'var(--fail)' : 'var(--info)';
  const score = (typeof th.score === 'number') ? th.score : 0;
  const tier = _s(th.tier);
  const regime = _s(th.regime);
  const sector = _s(th.sector || T.sector, '—');
  const industry = _s(th.industry || T.industry);

  let html = `<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:14px;font-size:12px;font-family:var(--mono);">
    <span style="background:${verdictColor};color:var(--bg-0);padding:3px 9px;border-radius:4px;font-weight:700;">${verdict}</span>
    <span style="color:var(--ink-2);">Score <b style="color:var(--ink-0);">${score}</b></span>
    <span style="color:var(--ink-3);">·</span>
    <span style="color:var(--ink-2);">${escape(sector)}${industry ? ' · ' + escape(industry) : ''}</span>
    ${tier ? `<span style="color:var(--ink-3);">·</span><span style="color:var(--accent);">${escape(tier)}</span>` : ''}
    ${regime ? `<span style="color:var(--ink-3);">·</span><span style="color:var(--ink-2);">${escape(regime)}</span>` : ''}
  </div>`;

  html += `<div style="background:var(--bg-1);border-left:3px solid var(--accent);padding:14px 18px;border-radius:0 6px 6px 0;font-size:14px;line-height:1.55;color:var(--ink-0);margin-bottom:18px;">
    ${escape(th.narrative || '')}
  </div>`;

  if (Array.isArray(th.score_breakdown) && th.score_breakdown.length) {
    html += `<h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-2);margin:14px 0 8px;">Score Breakdown</h3>`;
    html += `<table style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px;margin-bottom:18px;">
      <thead><tr style="text-align:left;color:var(--ink-2);border-bottom:1px solid var(--rule);">
        <th style="padding:8px 4px;font-weight:600;">Pillar</th>
        <th style="padding:8px 4px;font-weight:600;text-align:right;">Pts</th>
        <th style="padding:8px 4px;font-weight:600;text-align:right;">Max</th>
        <th style="padding:8px 4px;font-weight:600;text-align:center;">Bar</th>
      </tr></thead><tbody>`;
    for (const p of th.score_breakdown) {
      const ok = p.verdict === 'check' ? '✓' : p.verdict === 'warn' ? '⚠' : '✗';
      const okC = p.verdict === 'check' ? 'var(--pass)' : p.verdict === 'warn' ? 'var(--warn)' : 'var(--fail)';
      const isNum = typeof p.max === 'number';
      const pct = isNum ? Math.max(0, Math.min(100, (p.pts / p.max) * 100)) : 0;
      html += `<tr style="border-bottom:1px solid color-mix(in oklch, var(--rule) 50%, transparent);">
        <td style="padding:8px 4px;color:var(--ink-0);"><span style="color:${okC};margin-right:6px;">${ok}</span>${escape(p.pillar)}</td>
        <td style="padding:8px 4px;text-align:right;color:var(--ink-0);">${p.pts}</td>
        <td style="padding:8px 4px;text-align:right;color:var(--ink-2);">${p.max}</td>
        <td style="padding:8px 4px;width:160px;">${isNum ? `<div style="background:var(--bg-2);height:7px;border-radius:3px;overflow:hidden;"><div style="width:${pct}%;height:100%;background:${okC};"></div></div>` : ''}</td>
      </tr>`;
    }
    html += '</tbody></table>';
  }

  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px;">`;
  html += `<div><h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--pass);margin:0 0 8px;">Why Bullish</h3>`;
  if (Array.isArray(th.why_bullish) && th.why_bullish.length) {
    html += '<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.65;color:var(--ink-0);">';
    for (const b of th.why_bullish) html += `<li style="margin-bottom:4px;">${escape(b)}</li>`;
    html += '</ul>';
  } else { html += '<div style="color:var(--ink-2);font-size:12px;">—</div>'; }
  html += '</div>';
  html += `<div><h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--warn);margin:0 0 8px;">Risks</h3>`;
  if (Array.isArray(th.risks) && th.risks.length) {
    html += '<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.65;color:var(--ink-0);">';
    for (const r of th.risks) html += `<li style="margin-bottom:4px;">${escape(r)}</li>`;
    html += '</ul>';
  } else { html += '<div style="color:var(--ink-2);font-size:12px;">—</div>'; }
  html += '</div></div>';

  // K9 (2026-05-09): prefer canonical_trade_plan; fall back to legacy trade_plan dict.
  // The canonical plan is the authoritative source — if present, all sub-tabs (Plan,
  // Thesis, SMC, Models, Overview) display IDENTICAL entry/stop/T1/T2 numbers.
  const ctp = th?.canonical_trade_plan;
  const tp = th.trade_plan || {};
  const _stop = ctp?.stop ?? tp.stop;
  const _t1   = ctp?.target1 ?? tp.target1;
  const _t2   = ctp?.target2 ?? tp.target2;
  const _eLo  = ctp?.entry?.low  ?? tp.entry_low;
  const _eHi  = ctp?.entry?.high ?? tp.entry_high;
  const _setupType = ctp?.setup?.setup_type ?? tp.setup_type;
  const _rr   = ctp?.risk?.rr_ratio ?? tp.rr_ratio;
  const _hold = ctp?.hold_period_days ?? tp.max_hold_days;
  const _sizePct = ctp?.position_size_pct ?? tp.size_pct;
  if ((_eLo || _stop || _t1)) {
    html += `<h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-2);margin:14px 0 8px;">Trade Plan</h3>`;
    html += `<div style="background:var(--bg-1);padding:14px 18px;border-radius:6px;border:1px solid var(--rule);font-family:var(--mono);font-size:13px;color:var(--ink-0);line-height:1.85;">`;
    if (_setupType) html += `<div><span style="color:var(--ink-2);">Setup:</span> ${escape(_setupType)}${tp.entry_quality_adj ? ` <span style="color:var(--ink-2);">— ${escape(tp.entry_quality_adj)}</span>` : ''}</div>`;
    if (_eLo && _eHi) html += `<div><span style="color:var(--ink-2);">Entry:</span> $${_eLo} – $${_eHi}</div>`;
    if (_stop) html += `<div><span style="color:var(--ink-2);">Stop:</span> <span style="color:var(--fail);">$${_stop}</span></div>`;
    if (_t1) html += `<div><span style="color:var(--ink-2);">T1:</span> <span style="color:var(--pass);">$${_t1}</span>${_rr ? ` <span style="color:var(--ink-2);">(${_rr}R)</span>` : ''}</div>`;
    if (_t2) html += `<div><span style="color:var(--ink-2);">T2:</span> <span style="color:var(--pass);">$${_t2}</span></div>`;
    if (_hold) html += `<div><span style="color:var(--ink-2);">Hold:</span> ${_hold} ${typeof _hold === 'number' ? 'days' : ''}</div>`;
    if (_sizePct) html += `<div><span style="color:var(--ink-2);">Size:</span> ${(+_sizePct).toFixed(2)}% of account</div>`;
    html += `</div>`;
  }

  if (th.decision_reason) {
    html += `<div style="margin-top:14px;padding:11px 16px;background:color-mix(in oklch, var(--info) 10%, var(--bg-1));border-left:3px solid var(--info);border-radius:0 4px 4px 0;font-size:12.5px;color:var(--ink-0);">
      <b style="color:var(--info);">Decision:</b> ${escape(th.decision_reason)}
    </div>`;
  }

  body.innerHTML = html;
}

export function dispose() { /* no-op */ }
