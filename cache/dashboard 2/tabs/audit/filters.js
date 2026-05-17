// tabs/audit/filters.js — 14-filter UI logic + date presets + clear-all.
// Owns: filter dropdowns + filter input reading + applyFilters() pure transform.
// Does NOT own: filter inputs themselves (they live in dashboard.html).

import { getData } from '../../core/shared.js';

// Populate the month + strategy <select> dropdowns from the trail. Idempotent
// via window._auditFiltersInit so it only runs once per page load.
export function populateFilterDropdowns(trail) {
  if (window._auditFiltersInit) return;
  window._auditFiltersInit = true;

  const monthSel = document.getElementById('auditFilterMonth');
  const stratSel = document.getElementById('auditFilterStrategy');
  const months = new Set(), strats = new Set();
  trail.forEach(s => {
    if (s.date)     months.add(s.date.slice(0, 7));
    if (s.strategy) strats.add(s.strategy);
  });
  [...months].sort().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    monthSel && monthSel.appendChild(opt);
  });
  [...strats].sort().forEach(s => {
    const opt = document.createElement('option');
    opt.value = s; opt.textContent = s;
    stratSel && stratSel.appendChild(opt);
  });
}

// Read all 14 filter input values. Returned object is shaped for applyFilters().
export function readFilters() {
  const get = (id, dflt = '') => (document.getElementById(id) || { value: dflt }).value;
  return {
    sym:        (get('auditFilterSymbol') || '').trim().toUpperCase(),
    from:        get('auditFilterDateFrom'),
    to:          get('auditFilterDateTo'),
    month:       get('auditFilterMonth'),
    status:      get('auditFilterStatus'),
    verdict:     get('auditFilterVerdict'),
    pnl:         get('auditFilterPnl'),
    mode:        get('auditFilterMode'),
    regime:      get('auditFilterRegime'),
    conviction:  get('auditFilterConviction'),
    exit:        get('auditFilterExitReason'),
    elite:       get('auditFilterElite'),
    strategy:    get('auditFilterStrategy'),
  };
}

// Apply the 14 filters to the audit_trail array. Pure function — no DOM.
export function applyFilters(trail, f) {
  return trail.filter(s => {
    const verdict = s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
    if (f.sym         && !(s.ticker || '').toUpperCase().includes(f.sym))   return false;
    if (f.from        && (s.date || '') < f.from)                            return false;
    if (f.to          && (s.date || '') > f.to)                              return false;
    if (f.month       && !(s.date || '').startsWith(f.month))                return false;
    if (f.status      && (s.status || '').toUpperCase() !== f.status)       return false;
    if (f.verdict     && verdict !== f.verdict)                             return false;
    if (f.strategy    && s.strategy !== f.strategy)                         return false;
    if (f.mode        && (s.mode || 'Swing') !== f.mode)                    return false;
    if (f.regime      && (s.regime4 || '') !== f.regime)                    return false;
    if (f.conviction  && (s.conviction_label || '') !== f.conviction)       return false;
    if (f.exit) {
      if (f.exit === 'open' && s.status !== 'OPEN')                          return false;
      if (f.exit !== 'open' && (s.exit_reason || '') !== f.exit)             return false;
    }
    if (f.elite === 'elite'     && !s.is_elite) return false;
    if (f.elite === 'non_elite' && s.is_elite)  return false;
    if (f.pnl) {
      const p = s.pct_now;
      if (p == null) return false;
      if (f.pnl === 'gain'     && p <= 0)   return false;
      if (f.pnl === 'loss'     && p >= 0)   return false;
      if (f.pnl === 'big-gain' && p < 10)   return false;
      if (f.pnl === 'big-loss' && p > -10)  return false;
    }
    return true;
  });
}

// ─── Date-range preset helpers (bound to window for inline onclick callers) ───

export function clearFilters() {
  ['auditFilterSymbol','auditFilterDateFrom','auditFilterDateTo'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['auditFilterMonth','auditFilterVerdict','auditFilterStatus','auditFilterPnl',
   'auditFilterMode','auditFilterRegime','auditFilterConviction',
   'auditFilterExitReason','auditFilterElite','auditFilterStrategy'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  if (typeof window.renderAudit === 'function') window.renderAudit();
}

export function presetRange(days) {
  const today = new Date();
  const past  = new Date(today.getTime() - days * 86400000);
  const fmt   = d => d.toISOString().slice(0, 10);
  document.getElementById('auditFilterDateFrom').value = fmt(past);
  document.getElementById('auditFilterDateTo').value   = fmt(today);
  _markPresetActive(days + 'd');
  if (typeof window.renderAudit === 'function') window.renderAudit();
}

export function presetYtd() {
  const today = new Date();
  const ytd   = new Date(today.getFullYear(), 0, 1);
  const fmt   = d => d.toISOString().slice(0, 10);
  document.getElementById('auditFilterDateFrom').value = fmt(ytd);
  document.getElementById('auditFilterDateTo').value   = fmt(today);
  _markPresetActive('YTD');
  if (typeof window.renderAudit === 'function') window.renderAudit();
}

export function presetAll() {
  document.getElementById('auditFilterDateFrom').value = '';
  document.getElementById('auditFilterDateTo').value   = '';
  _markPresetActive('All');
  if (typeof window.renderAudit === 'function') window.renderAudit();
}

function _markPresetActive(label) {
  document.querySelectorAll('.audit-preset').forEach(b => {
    b.classList.toggle('on', b.textContent.trim() === label);
  });
}
