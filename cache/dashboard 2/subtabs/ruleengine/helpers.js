// subtabs/ruleengine/helpers.js — pure helpers used across rule-engine sub-modules.
// No DOM, no DATA, no T dependency.

export const getT = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export const fmtScore = (s, max) => s != null ? `${s.toFixed ? s.toFixed(0) : s}/${max}` : `—/${max}`;

export const pct = (s, max) => s != null && max > 0 ? (s / max * 100).toFixed(0) + '%' : '—';

export const toneFromPct = (s, max) => {
  if (s == null || max <= 0) return 'low';
  const r = s / max;
  return r >= 0.7 ? 'high' : r >= 0.4 ? 'med' : 'low';
};

export const stateBadge = (state) => {
  const m = {
    BULLISH: 'pass',  MARKUP: 'pass',     ACCUMULATION: 'pass',  EARLY_IMPULSE: 'pass',
    BEARISH: 'fail',  MARKDOWN: 'fail',   DISTRIBUTION: 'fail',  LATE_IMPULSE:  'fail',  CORRECTIVE: 'fail',
    NEUTRAL: 'warn',
    UNKNOWN: 'info',  UNAVAILABLE: 'info', INVALID: 'info',
  };
  return m[state] || 'info';
};
