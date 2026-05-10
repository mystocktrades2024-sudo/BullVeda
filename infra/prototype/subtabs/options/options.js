// subtabs/options/options.js — Options sub-tab thin orchestrator.
//
// Sub-modules:
//   kpis.js     — Hero verdict tile + 3 KPI tiles (IV / Flow / Positioning)
//   per_mode.js — Per-mode overlay (Swing / Position / Invest) + Institutional Read
//
// Entry pulls all data points off T.options_kpis, builds a single ctx object,
// and dispatches to the section builders.

import { buildHero, buildKpiRow }                from './kpis.js';
import { buildPerModeOverlay, buildInstitutionalRead } from './per_mode.js';

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;

  const k        = T.options_kpis || {};
  const v        = k.verdict || {};
  const verdict  = (v.verdict || 'NO_DATA').toUpperCase();
  const confidence = v.confidence || 'LOW';
  const edge     = v.edge != null ? v.edge : 0;
  const thesis   = v.thesis || 'Options data unavailable — Schwab refresh token may have expired. Run python3 schwab_auth.py oauth to re-enable IV / UOA / put-call signals.';
  const confluences = v.confluences || [];

  const vColor = {
    BULLISH: 'var(--pass)', BEARISH: 'var(--fail)',
    MIXED:   'var(--warn)', NEUTRAL: 'var(--ink-2)', NO_DATA: 'var(--ink-3)',
  }[verdict] || 'var(--ink-2)';
  const vIcon     = { BULLISH: '▲', BEARISH: '▼', MIXED: '◆', NEUTRAL: '■', NO_DATA: '○' }[verdict] || '○';
  const confColor = { HIGH: 'var(--pass)', MED: 'var(--warn)', LOW: 'var(--ink-3)' }[confidence] || 'var(--ink-3)';

  // KPI extracts
  const ctx = {
    verdict, vColor, vIcon, edge, confidence, confColor, thesis, confluences,
    ivPct:      k.iv_percentile,
    ivCur:      k.iv_current,
    pc:         k.put_call_ratio,
    uoaC:       k.uoa_calls,
    uoaP:       k.uoa_puts,
    uoaCDetail: k.uoa_call_detail,
    uoaPDetail: k.uoa_put_detail,
    skew:       k.skew_25d,
    term:       k.term_structure || {},
    gamma:      k.gamma_net,
    maxPain:    k.max_pain,
    callOI:     k.total_call_oi  || 0,
    putOI:      k.total_put_oi   || 0,
    callVol:    k.total_call_vol || 0,
    putVol:     k.total_put_vol  || 0,

    swingMode:    (k.per_mode || {}).swing    || {},
    positionMode: (k.per_mode || {}).position || {},
    investMode:   (k.per_mode || {}).invest   || {},

    swingScore:    T.score || 0,
    swingVerdict:  T.verdict || T.stage || 'WATCH',
    positionScore: T.medium_term_score    || '—',
    positionVerdict: T.medium_term_verdict || '—',
    positionGateStatus:  T.medium_term_gate_status  || '',
    positionGateReasons: T.medium_term_gate_reasons || [],
    investScore:   T.long_term_score   || '—',
    investVerdict: T.long_term_verdict || '—',
  };

  const target = document.getElementById('optionsBody');
  if (!target) return;
  target.innerHTML = buildHero(ctx)
                   + buildKpiRow(ctx)
                   + buildPerModeOverlay(ctx)
                   + buildInstitutionalRead(ctx);
}

export function dispose() { /* no-op */ }
