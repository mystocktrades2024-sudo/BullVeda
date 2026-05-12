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
  // Differentiated fallback thesis — previously this always blamed "Schwab
  // refresh token may have expired" regardless of actual cause. That string
  // was the #1 source of false Schwab-broken reports because it fires for at
  // least four distinct upstream conditions. Split into honest states:
  //   1. verdict.thesis present → use it (populated path)
  //   2. options_kpis missing entirely → either ticker isn't in current scan,
  //      or it's killed/non-actionable (no analysis pool membership)
  //   3. options_kpis present but empty / zero OI both sides → ticker simply
  //      has no listed options (common for micro-cap / low-float names)
  //   4. options_kpis present with chain data but no computed verdict →
  //      genuine KPI compute failure (most likely Schwab token expired)
  const _hasKpisKey   = (T.options_kpis !== undefined) && (T.options_kpis !== null);
  const _kpisEmpty    = _hasKpisKey && Object.keys(k).length === 0;
  const _zeroOI       = _hasKpisKey && (k.total_call_oi === 0 || k.total_call_oi == null)
                                    && (k.total_put_oi  === 0 || k.total_put_oi  == null)
                                    && (k.total_call_vol === 0 || k.total_call_vol == null)
                                    && (k.total_put_vol  === 0 || k.total_put_vol  == null);
  let thesis;
  if (v.thesis) {
    thesis = v.thesis;
  } else if (!_hasKpisKey) {
    thesis = T.score
      ? `Options data not included in this ticker's bundle payload. Open /api/elite/${T.ticker || '<TICKER>'}?deep=true to fetch options KPIs on-demand (~15-25s).`
      : `${T.ticker || 'This ticker'} isn't in the latest scan's analysis pool. Use the on-demand detail path (?deep=true) to compute options KPIs.`;
  } else if (_kpisEmpty || _zeroOI) {
    thesis = 'No actionable options on this ticker — Schwab returned an empty chain (zero open interest both sides). Common for low-float / micro-cap names without a listed options market.';
  } else {
    thesis = 'Options data partial — Schwab returned a chain but the KPI verdict didn\'t compute. Refresh token may have expired. Run `python3 schwab_auth.py oauth` to re-enable IV / UOA / put-call signals.';
  }
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

  // Earnings event-vol tape — when ER in next 30d, surface the implied move,
  // straddle cost, IV crush expectation, and RICH/CHEAP verdict.
  const _erTape = (function() {
    const ebp = T.earnings_beat_prediction;
    if (!ebp || !ebp.breakdown) return '';
    const im = ebp.breakdown.implied_move || {};
    const hist = ebp.breakdown.historical || {};
    const dte = ebp.days_to_earnings;
    if (dte == null || dte > 30 || im.implied_move_pct == null) return '';
    const ms = hist.median_surprise_pct;
    let verdict = 'FAIR', verdictColor = 'var(--ink-1)';
    if (ms != null && Math.abs(ms) > im.implied_move_pct) {
      verdict = 'CHEAP'; verdictColor = 'var(--pass)';
    } else if (ms != null && Math.abs(ms) < im.implied_move_pct * 0.5) {
      verdict = 'RICH'; verdictColor = 'var(--fail)';
    }
    return `<div style="margin-bottom:12px;padding:10px 14px;background:var(--bg-2);border:1px solid var(--rule);border-left:2px solid ${verdictColor};border-radius:2px;font-family:var(--mono);font-variant-numeric:tabular-nums">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
        <span style="font-size:9.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-3);font-weight:700">EVENT VOL · ER in ${dte}d · Schwab ATM straddle</span>
        <span style="font-size:12px;font-weight:700;color:${verdictColor};letter-spacing:0.14em;padding:2px 10px;border-radius:2px;background:color-mix(in oklch,${verdictColor} 16%,transparent);border:1px solid color-mix(in oklch,${verdictColor} 40%,transparent)">${verdict}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;font-size:11.5px">
        <div><div style="font-size:8.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700">Implied ±%</div><div style="font-size:14px;color:${im.implied_move_pct>=10?'var(--warn)':'var(--ink)'};font-weight:700">±${im.implied_move_pct.toFixed(2)}%</div></div>
        <div><div style="font-size:8.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700">Straddle</div><div style="font-size:14px;color:var(--ink);font-weight:700">$${(+im.straddle_cost||0).toFixed(2)}</div></div>
        <div><div style="font-size:8.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700">ATM K</div><div style="font-size:14px;color:var(--ink);font-weight:700">$${(+im.atm_strike||0).toFixed(2)}</div></div>
        <div><div style="font-size:8.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700">Expiry</div><div style="font-size:14px;color:var(--ink);font-weight:700">${(im.expiry_date||'').slice(5)}</div></div>
        <div><div style="font-size:8.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700">Prior median surp</div><div style="font-size:14px;color:${ms!=null?(ms>0?'var(--pass)':'var(--fail)'):'var(--ink-3)'};font-weight:700">${ms!=null?(ms>0?'+':'')+ms.toFixed(1)+'%':'—'}</div></div>
      </div>
    </div>`;
  })();

  target.innerHTML = _erTape
                   + buildHero(ctx)
                   + buildKpiRow(ctx)
                   + buildPerModeOverlay(ctx)
                   + buildInstitutionalRead(ctx);
}

export function dispose() { /* no-op */ }
