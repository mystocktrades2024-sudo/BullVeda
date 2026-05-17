// tabs/audit/exports.js — CSV export of the full audit_trail.
// Reads the live trail via getData() (was a bare-DATA reference in the
// original extraction — fixed during the split).

import { getData } from '../../core/shared.js';

export function exportCsv() {
  const DATA  = getData();
  const trail = (DATA.performance && DATA.performance.audit_trail) || [];
  const dayCols   = window.AUDIT_DAY_COLS   || [];
  const weekCols  = window.AUDIT_WEEK_COLS  || [];
  const monthCols = window.AUDIT_MONTH_COLS || [];

  const cols = [
    'ticker', 'mode', 'date', 'strategy', 'verdict', 'score', 'entry_price',
    'today', 'pct_now',
    ...dayCols.map(c   => c + '_pct'),
    ...weekCols.map(c  => c + '_pct'),
    ...monthCols.map(c => c + '_pct'),
    'status',
  ];

  const csv = [cols.join(',')]
    .concat(trail.map(s => cols.map(c => {
      if (c === 'mode') return `"${s.mode || 'Swing'}"`;
      if (c === 'verdict') return s.verdict || (s.direction === 'short' ? 'SHORT' : 'BUY');
      return s[c] != null ? `"${s[c]}"` : '';
    }).join(',')))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `audit_trail_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}
