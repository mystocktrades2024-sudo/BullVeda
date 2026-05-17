// tabs/performance/performance.js — Performance / Trade Journal tab.
// Thin orchestrator. Each visual section lives in its own sub-module:
//
//   wilson.js      — Wilson 95% CI helper (pure)
//   pnl.js         — Live $-P&L computation from audit_trail (pure)
//   verdict.js     — System Edge verdict banner + 4 P&L tiles (#perfTiles)
//   journal.js     — Trade Journal aggregate (#journalBody, #journalMeta)
//   podium.js      — Setup Family Podium / fallback Setup P&L Ranking
//   calibration.js — Score Calibration bars
//   actions.js     — Auto-generated action items
//
// Render order:
//   1. Compute pnl + per-strategy totals from audit_trail
//   2. Verdict banner + 4 P&L tiles into #perfTiles
//   3. Trade Journal into #journalBody (independent target)
//   4. Build podium + calibration + actions HTML strings
//   5. Inject all three together into perfAttribBody's grand-grandparent
//      (the legacy DOM target — see CLAUDE.md "DOM targets" note)

import { getData }      from '../../core/shared.js';
import { computePnL }   from './pnl.js';
import { renderVerdict } from './verdict.js';
import { renderJournal } from './journal.js';
import { buildPodium }   from './podium.js';
import { buildCalibration } from './calibration.js';
import { buildActions }  from './actions.js';

export function render() {
  const DATA = getData();
  const perf  = DATA.performance || {};
  const total   = perf.total   || 0;
  const closed  = perf.closed  || 0;
  const wr      = perf.win_rate;
  const attr    = perf.setup_attribution || {};
  const buckets = perf.by_score_bucket   || {};
  const trail   = perf.audit_trail        || [];

  const NOTIONAL = (typeof window !== 'undefined' && window.PERF_NOTIONAL) || 10000;

  const pnl = computePnL(trail, NOTIONAL);

  renderVerdict(perf, pnl, NOTIONAL, total, closed);
  renderJournal((DATA.portfolio || {}).closed || []);

  const podiumHtml      = buildPodium(perf, attr, pnl.byStrategy, total, NOTIONAL);
  const calibrationHtml = buildCalibration(buckets, closed);
  const actionsHtml     = buildActions(perf, attr, total, closed, wr);

  const attribTarget = document.getElementById('perfAttribBody');
  if (attribTarget) {
    attribTarget.parentElement.parentElement.innerHTML = podiumHtml + calibrationHtml + actionsHtml;
  }
}

export function dispose() { /* no-op */ }
