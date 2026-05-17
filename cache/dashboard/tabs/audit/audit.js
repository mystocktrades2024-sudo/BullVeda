// tabs/audit/audit.js — Audit tab thin orchestrator.
// Each visual section lives in its own sub-module:
//
//   filters.js      — 14-filter UI: dropdown population, readFilters, applyFilters,
//                     clearFilters, presetRange/Ytd/All
//   summary.js      — 4 stat tiles (#auditSummary)
//   rows.js         — <thead> + <tbody> grid (#auditThead, #auditTbody)
//   live_poll.js    — 5s /api/live/quote poller; auto-starts
//   expand_panel.js — row click → 4-section detail panel
//   exports.js      — CSV export of full trail
//
// All onclick / onload helpers are exposed on window for inline-HTML callers
// (auditToggleExpand, auditClearFilters, auditExportCsv, auditPreset*).

import { getData } from '../../core/shared.js';
import { populateFilterDropdowns, readFilters, applyFilters,
         clearFilters, presetRange, presetYtd, presetAll } from './filters.js';
import { renderSummary }                from './summary.js';
import { renderHead, renderBody }       from './rows.js';
import { pollOnce, startPolling }       from './live_poll.js';
import { toggleExpand }                 from './expand_panel.js';
import { exportCsv }                    from './exports.js';

const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

export function render() {
  const DATA  = getData();
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];

  populateFilterDropdowns(trail);

  const filters  = readFilters();
  const filtered = applyFilters(trail, filters);

  setText('auditMeta', `${filtered.length} of ${trail.length} signals shown`);
  setText('fsAuditCt', trail.length);
  setText('sbAuditCt', trail.length);

  // Coverage notice — show if no WATCH/SHORT verdicts have populated yet
  const hasWatchOrShort = trail.some(s => s.verdict === 'WATCH' || s.verdict === 'SHORT');
  const notice = document.getElementById('auditCoverageNotice');
  if (notice) notice.style.display = (trail.length > 0 && !hasWatchOrShort) ? 'block' : 'none';

  renderSummary(filtered);
  renderHead();
  renderBody(filtered);

  // Kick a one-off live-quote update so newly rendered rows fill in immediately
  // (the recurring 5s interval was started at module load time).
  if (filtered.length > 0) pollOnce();
}

export function dispose() { /* poller intentionally keeps running; see CLAUDE.md "Dispose" note */ }

// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window.renderAudit         = render;
  window.auditToggleExpand   = toggleExpand;
  window.auditClearFilters   = clearFilters;
  window.auditExportCsv      = exportCsv;
  window.auditPresetRange    = presetRange;
  window.auditPresetYtd      = presetYtd;
  window.auditPresetAll      = presetAll;
  window._auditLivePoll      = pollOnce;
}

// Auto-start the 5s live-quote poller on module load
startPolling();
