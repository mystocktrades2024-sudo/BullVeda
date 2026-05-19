// tabs/audit/expand_panel.js — Row expand/collapse + 4-section detail panel.
// Reads current trail via getData() (fixed up from a bare-DATA reference that
// shipped broken in the original extraction).

import { getData } from '../../core/shared.js';

export function toggleExpand(rowKey, event) {
  if (event && (event.target.tagName === 'A' || event.target.closest('a'))) return;
  const tbody = document.getElementById('auditTbody');
  if (!tbody) return;
  const row = tbody.querySelector(`tr[data-rowkey="${rowKey}"]`);
  if (!row) return;
  const arrow = row.querySelector('.audit-row-arrow');

  // Already expanded — collapse
  const next = row.nextElementSibling;
  if (next && next.classList.contains('audit-expand')) {
    next.remove();
    if (arrow) arrow.style.transform = 'rotate(0deg)';
    return;
  }
  // Collapse any other open expand rows first
  tbody.querySelectorAll('tr.audit-expand').forEach(r => r.remove());
  tbody.querySelectorAll('.audit-row-arrow').forEach(a => { a.style.transform = 'rotate(0deg)'; });

  // Find signal data
  const DATA  = getData();
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];
  const sig   = trail.find(s => `${s.ticker}__${s.date}__${s.mode || 'Swing'}` === rowKey);
  if (!sig) return;

  const tr = document.createElement('tr');
  tr.className = 'audit-expand';
  tr.innerHTML = `<td colspan="100" style="padding:0; background:var(--ink); border-bottom:1px solid var(--paper-5);">
    ${renderDetailPanel(sig)}
  </td>`;
  row.after(tr);
  if (arrow) arrow.style.transform = 'rotate(90deg)';
}

export function renderDetailPanel(s) {
  const fmt      = (v, suffix='', dp=2) => v == null ? '<span style="color:var(--paper-4)">—</span>' : (typeof v === 'number' ? v.toFixed(dp) + suffix : v + suffix);
  const fmtPct   = v => v == null ? '<span style="color:var(--paper-4)">—</span>' : `<span style="color:${v >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:700">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
  const fmtRMult = v => v == null ? '<span style="color:var(--paper-4)">—</span>' : `<span style="color:${v >= 1 ? 'var(--green)' : v >= 0 ? 'var(--accent)' : 'var(--red)'};font-weight:700">${v >= 0 ? '+' : ''}${v.toFixed(2)}R</span>`;
  const regimeColor = (r) => r === 'risk_on_trending' ? 'var(--green)' : r === 'risk_on_choppy' ? 'var(--accent)' : r === 'risk_off_trending' ? 'var(--warn)' : r === 'panic' ? 'var(--red)' : 'var(--paper-3)';
  const convColor   = (c) => c === 'T1' ? 'var(--green)' : c === 'T2' ? 'var(--accent)' : c === 'T3' ? 'var(--warn)' : 'var(--paper-3)';
  const eqColor     = (e) => e === 'FRESH' ? 'var(--green)' : e === 'PULLBACK' ? 'var(--accent)' : e === 'VALID' ? 'var(--accent)' : e === 'EXTENDED' ? 'var(--warn)' : 'var(--red)';
  const exitColor   = (e) => e === 'target_hit' ? 'var(--green)' : e === 'stop_hit' ? 'var(--red)' : e && e.includes('time_stop') ? 'var(--warn)' : 'var(--paper-3)';

  const pill = (text, color) => text ? `<span style="display:inline-block;padding:2px 8px;border-radius:3px;background:color-mix(in oklch, ${color} 18%, transparent);color:${color};border:1px solid color-mix(in oklch, ${color} 45%, transparent);font-weight:700;font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;">${text}</span>` : '<span style="color:var(--paper-4)">—</span>';
  const cell = (label, val) => `<div style="padding:6px 0; border-bottom:1px dashed var(--paper-5); display:flex; justify-content:space-between; align-items:center; font-size:11.5px;"><span style="color:var(--paper-3); letter-spacing:0.04em;">${label}</span><span style="font-family:var(--mono); font-weight:600; color:var(--paper);">${val}</span></div>`;

  return `
    <div style="padding:18px 22px; background:linear-gradient(180deg, color-mix(in oklch, var(--accent) 4%, var(--ink)) 0%, var(--ink) 50%); border-left:3px solid var(--accent);">
      <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:24px;">

        <!-- 1. Regime context at signal time -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">REGIME @ SIGNAL</div>
          ${cell('Regime4', pill(s.regime4 || '—', regimeColor(s.regime4)))}
          ${cell('VIX', fmt(s.vix_at_signal, '', 1))}
          ${cell('HMM Bull',    s.hmm_p_bull    != null ? `<span style="color:var(--green)">${(s.hmm_p_bull*100).toFixed(0)}%</span>`    : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('HMM Neutral', s.hmm_p_neutral != null ? `<span style="color:var(--accent)">${(s.hmm_p_neutral*100).toFixed(0)}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('HMM Bear',    s.hmm_p_bear    != null ? `<span style="color:var(--red)">${(s.hmm_p_bear*100).toFixed(0)}%</span>`      : '<span style="color:var(--paper-4)">—</span>')}
        </div>

        <!-- 2. Conviction + Setup -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">CONVICTION + SETUP</div>
          ${cell('Conviction',   pill(s.conviction_label || '—', convColor(s.conviction_label)))}
          ${cell('Entry Quality', pill(s.entry_quality || '—',   eqColor(s.entry_quality)))}
          ${cell('Setup Family', s.setup_family || s.strategy || '<span style="color:var(--paper-4)">—</span>')}
          ${cell('Stars',        `${s.stars || 0}/5`)}
          ${cell('Tail Filter',  s.tail_filter_demoted ? '<span style="color:var(--red);font-weight:800">✗ DEMOTED</span>' : '<span style="color:var(--green);font-weight:800">✓ CLEARED</span>')}
        </div>

        <!-- 3. Forward predictions (V-1 + V-3) -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">FORWARD PREDICTIONS</div>
          ${cell('MC P(profit)',     s.mc_p_profit       != null ? `<span style="color:${s.mc_p_profit >= 60 ? 'var(--green)' : s.mc_p_profit >= 45 ? 'var(--accent)' : 'var(--red)'}">${s.mc_p_profit}%</span>`  : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('MC P(T1 first)',   s.mc_p_target_first != null ? `<span style="color:var(--green)">${s.mc_p_target_first}%</span>`        : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('MC P(stop first)', s.mc_p_stop_first   != null ? `<span style="color:var(--red)">${s.mc_p_stop_first}%</span>`            : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('VaR-95',           s.fd_var_95_pct     != null ? `<span style="color:var(--red)">${s.fd_var_95_pct}%</span>`             : '<span style="color:var(--paper-4)">—</span>')}
          ${cell('CVaR-97.5',        s.fd_cvar_975_pct   != null ? `<span style="color:var(--red)">${s.fd_cvar_975_pct}%</span>`           : '<span style="color:var(--paper-4)">—</span>')}
        </div>

        <!-- 4. Outcome (when closed) + alpha vs SPY -->
        <div>
          <div style="font-family:var(--mono); font-size:10px; color:var(--accent); font-weight:800; letter-spacing:0.16em; text-transform:uppercase; padding-bottom:6px; border-bottom:1px solid var(--paper-5); margin-bottom:6px;">OUTCOME ${s.status === 'CLOSED' ? '· CLOSED' : '· OPEN'}</div>
          ${cell('Exit Reason',  pill(s.exit_reason || (s.status === 'OPEN' ? 'still open' : '—'), exitColor(s.exit_reason)))}
          ${cell('Days to T1',   fmt(s.days_to_first_target_hit, 'd', 0))}
          ${cell('Days to Stop', fmt(s.days_to_stop_hit, 'd', 0))}
          ${cell('Realized R',   fmtRMult(s.actual_r_multiple))}
          ${cell('SPY return',   fmtPct(s.spy_return_over_hold))}
          ${cell('Alpha vs SPY', s.alpha_vs_spy != null ? `<span style="color:${s.alpha_vs_spy > 0 ? 'var(--green)' : s.alpha_vs_spy < 0 ? 'var(--red)' : 'var(--paper-3)'};font-weight:800">${s.alpha_vs_spy >= 0 ? '+' : ''}${s.alpha_vs_spy}%</span>` : '<span style="color:var(--paper-4)">—</span>')}
        </div>

      </div>

      ${s.live ? `<div style="margin-top:14px; padding:8px 12px; background:color-mix(in oklch, var(--accent) 12%, transparent); border:1px solid color-mix(in oklch, var(--accent) 35%, transparent); border-radius:4px; font-size:11.5px; color:var(--paper-2); display:flex; align-items:center; gap:8px;">
        <span style="color:var(--accent); font-weight:800;">●  LIVE</span>
        <span>This pick is from today's bundle — not yet persisted to <code style="color:var(--accent)">signal_log.json</code>. Will be logged next time <code style="color:var(--accent)">swing_trade.py</code> runs.</span>
      </div>` : ''}

      <div style="margin-top:12px; display:flex; gap:8px; align-items:center; font-size:11px; color:var(--paper-3);">
        <span>Trade plan:</span>
        <span style="color:var(--paper-2)">Entry <b style="color:var(--paper)">$${(s.entry_price||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">Stop <b style="color:var(--red)">$${(s.stop||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">T1 <b style="color:var(--green)">$${(s.target1||0).toFixed(2)}</b></span>
        <span>·</span>
        <span style="color:var(--paper-2)">R:R <b style="color:var(--paper)">1:${(s.rr||0).toFixed(1)}</b></span>
        <span style="margin-left:auto;">
          <a href="#" onclick="window.setDetailTicker && window.setDetailTicker('${s.ticker}'); return false;" style="color:var(--accent); text-decoration:none; font-weight:700;">Open Full Analysis →</a>
        </span>
      </div>
    </div>
  `;
}
