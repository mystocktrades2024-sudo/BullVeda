// subtabs/models/horizons.js — extracted from elite-detail.html (renderHorizons 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const px      = +(T.price || 0);
  const atr     = +((T.atr_pct || 0) / 100 * px);
  const w52h    = +(T.week52_high || 0);
  const w52l    = +(T.week52_low || 0);
  const fracL   = +(T.fractal_low || 0);
  const fracH   = +(T.fractal_high || 0);
  const sma200  = px && T.above_200sma === false ? null : null; // not directly in bundle
  const fr      = T.fund_real || {};
  const an      = T.analyst || {};
  const tc      = T.theory_confluence || {};
  const tcStates = tc.states || {};

  // ── SWING (real bundle data) ────────────────────────────────────────────
  const swing = {
    verdict:   T.verdict || '—',
    state:     T.decision_state || T.entry_quality || '—',
    score:     +(T.score || 0),
    rr:        +(T.rr_ratio || T.rr || 0),
    entry_lo:  +(T.entry_lo || 0),
    entry_hi:  +(T.entry_hi || 0),
    stop:      +(T.stop || 0),
    t1:        +(T.t1 || 0),
    t2:        +(T.t2 || 0),
    setup:     T.setup_family || T.setup || '—',
    hold:      `${T.max_hold_days || '—'}d max`,
    sizing:    T.alloc_pct != null ? `${(+T.alloc_pct).toFixed(1)}%` : '—',
    conviction: T.conviction_tier || (swing => swing >= 80 ? 'T1' : swing >= 70 ? 'T2' : 'T3')(+(T.score || 0)),
    decision_label: T.decision_label || (typeof T.thesis === 'string' ? T.thesis : '') || '',
  };

  // ── POSITION (medium-term — synthesize entry/stop/target from price + ATR + fractals) ──
  // Entry: 0.5–1.5 ATR pullback below price (deeper than swing entry)
  // Stop: 1× ATR below entry low or fractal_low if available
  // T1: 1.5× the entry-stop distance, anchored to fractal_high or week52_high
  // T2: 2.5× entry-stop distance
  const posEntryHi = px - 0.5 * atr;
  const posEntryLo = px - 1.8 * atr;
  const posStop    = Math.max(0.01, fracL > 0 && fracL < posEntryLo ? fracL : posEntryLo - 1.0 * atr);
  const posRisk    = posEntryLo - posStop;
  const posT1Raw   = posEntryLo + 3.0 * posRisk;
  const posT1      = w52h > posEntryLo ? Math.max(posT1Raw, fracH || 0) : posT1Raw;
  const posT2      = posEntryLo + 5.0 * posRisk;
  const posRR      = posRisk > 0 ? (posT1 - posEntryLo) / posRisk : 0;
  const posScore   = +(T.medium_term_score || 0);
  const posReasons = T.medium_term_gate_reasons || [];
  const position = {
    verdict:  T.medium_term_verdict || '—',
    gate:     T.medium_term_gate_status || '—',
    score:    posScore,
    rr:       posRR,
    entry_lo: posEntryLo, entry_hi: posEntryHi,
    stop:     posStop, t1: posT1, t2: posT2,
    hold:     '3–8 weeks',
    sizing:   posScore >= 80 ? '8–12%' : posScore >= 70 ? '5–8%' : '3–5%',
    reasons:  posReasons,
    synth:    true, // flag — these levels are synthesized from price+ATR, not bundle
  };

  // ── INVEST (long-term — fundamentals-driven; floor & fair from analyst + ratios) ──
  const ltScore = +(T.long_term_score || 0);
  const floor   = w52l > 0 ? w52l : px * 0.7;
  const fairTarget = an.target_mean || (an.target_high && an.target_low ? (an.target_high + an.target_low)/2 : null);
  const upside  = fairTarget && px ? ((fairTarget - px) / px * 100) : null;
  const lt = T.long_term_breakdown || {};
  const invest = {
    verdict:  T.long_term_verdict || '—',
    score:    ltScore,
    floor:    floor,
    fair:     fairTarget,
    upside:   upside,
    cost:     px,
    hold:     '12–24 months',
    sizing:   ltScore >= 80 ? '15–20%' : ltScore >= 70 ? '10–15%' : '5–10%',
    rev_g:    fr.rev_growth_pct,
    margin:   fr.net_margin_pct,
    roe:      fr.roe_pct,
    peg:      fr.peg,
    drivers:  fr.bull_drivers || [],
    risks:    fr.bear_risks || [],
    gate_fails: lt.gate_fails || [],
  };

  // ── Best horizon highlight (highest score with non-AVOID verdict) ──
  const candidates = [
    { id: 'swing',    score: swing.score,    verdict: swing.verdict },
    { id: 'position', score: position.score, verdict: position.verdict },
    { id: 'invest',   score: invest.score,   verdict: invest.verdict },
  ].filter(c => c.verdict && !['AVOID','SHORT','—'].includes(String(c.verdict).toUpperCase()));
  const bestId = candidates.length ? candidates.sort((a,b) => b.score - a.score)[0].id : null;

  // ── Verdict pill helpers ──
  const verdictColor = v => {
    const u = String(v || '').toUpperCase();
    if (['BUY','STRONG BUY'].includes(u)) return 'var(--pass)';
    if (['WATCH','HOLD'].includes(u))     return 'var(--warn)';
    if (['SHORT','AVOID','SELL'].includes(u)) return 'var(--fail)';
    return 'var(--ink-3)';
  };
  const stateColor = s => {
    const u = String(s || '').toUpperCase();
    if (['FRESH','PULLBACK','VALID','ELIGIBLE','READY'].includes(u)) return 'var(--pass)';
    if (['EXTENDED','WAIT'].includes(u)) return 'var(--warn)';
    if (['MISSED','BLOCKED','ENTRY_MISSED'].includes(u)) return 'var(--fail)';
    return 'var(--ink-2)';
  };
  const fmt = (v, d=2) => v == null || isNaN(v) ? '—' : '$' + (+v).toFixed(d);
  const fmtPct = (v, d=1) => v == null || isNaN(v) ? '—' : (+v).toFixed(d) + '%';

  // ── Build the three cards ──
  const swingCard = `
    <div class="hz-card ${bestId === 'swing' ? 'hz-best' : ''}" data-hz="swing">
      <div class="hz-head">
        <div class="hz-icon swing">⚡</div>
        <div class="hz-h-text">
          <div class="hz-title">SWING</div>
          <div class="hz-sub">2–14 days · momentum / catalyst</div>
        </div>
        ${bestId === 'swing' ? '<div class="hz-best-badge">★ BEST</div>' : ''}
      </div>
      <div class="hz-pills">
        <span class="hz-pill verdict" style="color:${verdictColor(swing.verdict)};border-color:${verdictColor(swing.verdict)}">${swing.verdict}</span>
        <span class="hz-pill state" style="color:${stateColor(swing.state)};border-color:${stateColor(swing.state)}">${swing.state}</span>
        <span class="hz-pill conv">${swing.conviction}</span>
      </div>
      <div class="hz-stats-row">
        <div class="hz-stat"><div class="lbl">Score</div><div class="val">${swing.score}</div></div>
        <div class="hz-stat"><div class="lbl">R:R</div><div class="val ${swing.rr >= 3 ? 'pass' : swing.rr >= 2 ? 'warn' : 'fail'}">${swing.rr.toFixed(1)}×</div></div>
        <div class="hz-stat"><div class="lbl">Hold</div><div class="val">${swing.hold}</div></div>
        <div class="hz-stat"><div class="lbl">Size</div><div class="val">${swing.sizing}</div></div>
      </div>
      <div class="hz-plan">
        <div class="hz-plan-h">TRADE PLAN</div>
        <div class="hz-plan-row"><span class="lb">Entry</span><span class="vl">${fmt(swing.entry_lo)} → ${fmt(swing.entry_hi)}</span></div>
        <div class="hz-plan-row"><span class="lb">Stop</span><span class="vl fail">${fmt(swing.stop)}</span></div>
        <div class="hz-plan-row"><span class="lb">T1</span><span class="vl pass">${fmt(swing.t1)} <span class="rr">${swing.rr ? `${swing.rr.toFixed(1)}×` : ''}</span></span></div>
        <div class="hz-plan-row"><span class="lb">T2</span><span class="vl pass">${fmt(swing.t2)}</span></div>
      </div>
      <div class="hz-meta">
        <div><span class="hz-mlbl">Setup</span><span class="hz-mv">${swing.setup}</span></div>
      </div>
      ${swing.decision_label ? `<div class="hz-decision">${swing.decision_label}</div>` : ''}
    </div>`;

  const positionCard = `
    <div class="hz-card ${bestId === 'position' ? 'hz-best' : ''}" data-hz="position">
      <div class="hz-head">
        <div class="hz-icon position">📈</div>
        <div class="hz-h-text">
          <div class="hz-title">POSITION</div>
          <div class="hz-sub">3–8 weeks · weekly trend</div>
        </div>
        ${bestId === 'position' ? '<div class="hz-best-badge">★ BEST</div>' : ''}
      </div>
      <div class="hz-pills">
        <span class="hz-pill verdict" style="color:${verdictColor(position.verdict)};border-color:${verdictColor(position.verdict)}">${position.verdict}</span>
        <span class="hz-pill state" style="color:${stateColor(position.gate)};border-color:${stateColor(position.gate)}">${position.gate.replace(/_/g,' ')}</span>
        <span class="hz-pill synth" title="Levels synthesized from price + ATR; bundle does not yet ship per-horizon entry/stop/target">SYNTH</span>
      </div>
      <div class="hz-stats-row">
        <div class="hz-stat"><div class="lbl">Score</div><div class="val">${position.score.toFixed(0)}</div></div>
        <div class="hz-stat"><div class="lbl">R:R</div><div class="val ${position.rr >= 3 ? 'pass' : position.rr >= 2 ? 'warn' : 'fail'}">${position.rr.toFixed(1)}×</div></div>
        <div class="hz-stat"><div class="lbl">Hold</div><div class="val">${position.hold}</div></div>
        <div class="hz-stat"><div class="lbl">Size</div><div class="val">${position.sizing}</div></div>
      </div>
      <div class="hz-plan">
        <div class="hz-plan-h">TRADE PLAN <span class="hz-synth">synthesized from price + ${T.atr_pct ? T.atr_pct.toFixed(1) + '% ATR' : 'ATR'}</span></div>
        <div class="hz-plan-row"><span class="lb">Entry</span><span class="vl">${fmt(position.entry_lo)} → ${fmt(position.entry_hi)}</span></div>
        <div class="hz-plan-row"><span class="lb">Stop</span><span class="vl fail">${fmt(position.stop)}</span></div>
        <div class="hz-plan-row"><span class="lb">T1</span><span class="vl pass">${fmt(position.t1)} <span class="rr">${position.rr ? `${position.rr.toFixed(1)}×` : ''}</span></span></div>
        <div class="hz-plan-row"><span class="lb">T2</span><span class="vl pass">${fmt(position.t2)}</span></div>
      </div>
      <div class="hz-meta">
        <div><span class="hz-mlbl">Wyckoff</span><span class="hz-mv ${(tcStates.wyckoff||'').includes('MARK') ? 'pass' : ''}">${tcStates.wyckoff || '—'}</span></div>
        <div><span class="hz-mlbl">Dow</span><span class="hz-mv">${tcStates.dow || '—'}</span></div>
      </div>
      ${position.reasons && position.reasons.length ? `<div class="hz-decision">${position.reasons[0]}</div>` : ''}
    </div>`;

  const investCard = `
    <div class="hz-card ${bestId === 'invest' ? 'hz-best' : ''}" data-hz="invest">
      <div class="hz-head">
        <div class="hz-icon invest">🚀</div>
        <div class="hz-h-text">
          <div class="hz-title">INVEST</div>
          <div class="hz-sub">12–24 months · fundamentals + valuation</div>
        </div>
        ${bestId === 'invest' ? '<div class="hz-best-badge">★ BEST</div>' : ''}
      </div>
      <div class="hz-pills">
        <span class="hz-pill verdict" style="color:${verdictColor(invest.verdict)};border-color:${verdictColor(invest.verdict)}">${invest.verdict}</span>
        ${invest.gate_fails.length ? `<span class="hz-pill state" style="color:var(--fail);border-color:var(--fail)" title="${invest.gate_fails.join(', ')}">QUALITY GATE: ${invest.gate_fails.length} FAIL</span>` : '<span class="hz-pill state" style="color:var(--pass);border-color:var(--pass)">QUALITY PASS</span>'}
      </div>
      <div class="hz-stats-row">
        <div class="hz-stat"><div class="lbl">Score</div><div class="val">${invest.score.toFixed(0)}</div></div>
        <div class="hz-stat"><div class="lbl">Upside</div><div class="val ${invest.upside != null && invest.upside >= 15 ? 'pass' : invest.upside != null && invest.upside >= 5 ? 'warn' : ''}">${invest.upside != null ? (invest.upside >= 0 ? '+' : '') + invest.upside.toFixed(1) + '%' : '—'}</div></div>
        <div class="hz-stat"><div class="lbl">Hold</div><div class="val">${invest.hold}</div></div>
        <div class="hz-stat"><div class="lbl">Size</div><div class="val">${invest.sizing}</div></div>
      </div>
      <div class="hz-plan">
        <div class="hz-plan-h">VALUATION ANCHORS</div>
        <div class="hz-plan-row"><span class="lb">Cost basis</span><span class="vl">${fmt(invest.cost)}</span></div>
        <div class="hz-plan-row"><span class="lb">Floor (52w low)</span><span class="vl fail">${fmt(invest.floor)}</span></div>
        <div class="hz-plan-row"><span class="lb">Analyst target</span><span class="vl ${invest.fair ? 'pass' : ''}">${invest.fair ? fmt(invest.fair) : '—'}</span></div>
      </div>
      <div class="hz-meta">
        <div><span class="hz-mlbl">Rev growth</span><span class="hz-mv ${invest.rev_g >= 15 ? 'pass' : invest.rev_g >= 5 ? 'warn' : 'fail'}">${fmtPct(invest.rev_g)}</span></div>
        <div><span class="hz-mlbl">Net margin</span><span class="hz-mv ${invest.margin >= 20 ? 'pass' : invest.margin >= 10 ? 'warn' : 'fail'}">${fmtPct(invest.margin)}</span></div>
        <div><span class="hz-mlbl">ROE</span><span class="hz-mv ${invest.roe >= 15 ? 'pass' : ''}">${fmtPct(invest.roe)}</span></div>
        <div><span class="hz-mlbl">PEG</span><span class="hz-mv ${invest.peg && invest.peg < 1.5 ? 'pass' : invest.peg && invest.peg > 3 ? 'fail' : ''}">${invest.peg != null ? invest.peg.toFixed(2) : '—'}</span></div>
      </div>
      ${invest.drivers.length ? `<div class="hz-driver-list"><div class="hz-driver-h">BULL DRIVERS</div>${invest.drivers.slice(0,3).map(d => `<div class="hz-driver-item">+ ${d}</div>`).join('')}</div>` : ''}
      ${invest.risks.length ? `<div class="hz-driver-list bear"><div class="hz-driver-h">RISKS</div>${invest.risks.slice(0,2).map(d => `<div class="hz-driver-item">− ${d}</div>`).join('')}</div>` : ''}
    </div>`;

  // Per-horizon recommendation banner
  const recoBanner = bestId ? `
    <div class="hz-reco">
      <span class="hz-reco-i">▸</span>
      <span class="hz-reco-t">EVIDENCE FAVORS <b>${bestId.toUpperCase()}</b> HORIZON</span>
      <span class="hz-reco-d">${
        bestId === 'swing' ? 'Catalyst momentum + R:R favor a 2–14 day setup. Position/Invest are secondary.' :
        bestId === 'position' ? 'Weekly trend + score favor a 3–8 week hold. Swing entry may be missed; wait for pullback.' :
        'Fundamentals + valuation favor a multi-month hold. Tactical entries optional via swing.'
      }</span>
    </div>` : `
    <div class="hz-reco no-go">
      <span class="hz-reco-i">⊘</span>
      <span class="hz-reco-t">NO ACTIONABLE HORIZON</span>
      <span class="hz-reco-d">All three timeframes show AVOID/SHORT/no verdict. Skip this name.</span>
    </div>`;

  $('horizonsBody').innerHTML = `
    ${recoBanner}
    <div class="hz-grid">
      ${swingCard}
      ${positionCard}
      ${investCard}
    </div>
    <div class="hz-foot">
      <span class="hz-foot-i">i</span>
      <span>Position-horizon entry/stop/target are <b>synthesized from price + ATR</b> (bundle ships per-horizon scoring but not per-horizon levels yet). Invest valuation uses analyst target where available, else 52-week low as floor. Swing levels come directly from the live scoring engine.</span>
    </div>`;
}

export function dispose() { /* no-op */ }
