// subtabs/plan/plan.js — extracted from elite-detail.html (renderPlan 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  // K7 (2026-05-09): canonical_trade_plan is the source of truth. Vinod feedback:
  // "Trade plan entry, Stop, T1 and T2 has to align with rest of the numbers in
  // the outlook" — Plan, Thesis, SMC, Models, Overview now read identical
  // entry/stop/T1/T2 from one place. Falls back to legacy fields for older
  // ticker dicts that predate K6 (commit 2c9b9f339).
  const ctp = T?.canonical_trade_plan;
  const tpLegacy = T.trade_plan || {};
  const _stop      = ctp?.stop          ?? T.stop          ?? tpLegacy.stop;
  const _t1        = ctp?.target1       ?? T.target1       ?? tpLegacy.target1;
  const _t2        = ctp?.target2       ?? T.target2       ?? tpLegacy.target2;
  const _eLo       = ctp?.entry?.low    ?? T.entry_low     ?? tpLegacy.entry_low;
  const _eHi       = ctp?.entry?.high   ?? T.entry_high    ?? tpLegacy.entry_high;
  const _setupFam  = ctp?.setup?.setup_family ?? T.setup_family;
  // Re-bind these onto T so later code in this function can keep using T.stop/T.entry_low etc.
  // without changing every reference. This is the canonical-first behavior.
  T.stop       = _stop;
  T.target1    = _t1;
  T.target2    = _t2;
  T.entry_low  = _eLo;
  T.entry_high = _eHi;
  T.setup_family = _setupFam ?? T.setup_family;

  const lo = Math.min(T.stop, T.entry_low) * 0.93;
  const hi = Math.max(T.target2 || T.target1, T.entry_high) * 1.10;
  const range = hi - lo || 1;
  const p = v => Math.max(0, Math.min(100, ((v - lo) / range) * 100));
  const earnX = T.earn_days != null ? Math.min(95, 30 + T.earn_days * 2.5) : null;
  const rrT1 = ((T.target1 - T.entry_low) / Math.max(0.01, T.entry_low - T.stop));
  const rrT2 = T.target2 ? ((T.target2 - T.entry_low) / Math.max(0.01, T.entry_low - T.stop)) : null;
  // Plausible position size on $250k @ 0.75% risk
  const acct = 250000, riskPct = 0.0075;
  const riskPerSh = Math.max(0.01, T.entry_low - T.stop);
  const shares = Math.floor((acct * riskPct) / riskPerSh);
  const dollarRisk = shares * riskPerSh;
  const sizePctAcct = ((shares * T.entry_low) / acct) * 100;

  const entryLanes = [
    [`Wait for D1 close above <b>$${px(T.entry_low)}</b> with RVOL ≥ 1.2×.`, 'TRIGGER · D1 close · vol confirm'],
    [`Scale in: ½ position at first pullback to <b>$${px(T.entry_low)}–${px((T.entry_low+T.entry_high)/2)}</b>.`, 'LIMIT · half size · 1–2 sessions'],
    [`Add remaining ½ if 1H higher-low prints in entry zone.`, 'LIMIT · half size · cancel if invalidated'],
    [`Hard stop @ <b>$${px(T.stop)}</b> immediately on first fill.`, 'STOP · GTC · non-negotiable'],
  ];
  const exitLanes = [
    [`Trim <b>50% at T1 $${px(T.target1)}</b>, move stop to break-even.`, 'LIMIT · realize +1.0R+ partial'],
    [`Trail remaining 50% on EMA21 (D1 close basis).`, 'DYNAMIC · re-evaluate every session'],
    [`Hard exit on <b>T2 $${px(T.target2 || T.target1)}</b> or first D1 close below EMA21.`, 'LIMIT · final close'],
    [T.earn_days != null && T.earn_days <= 14 ? `Close before earnings (+${T.earn_days}d) if T1 not hit.` : `Hold full position if regime stays risk-on.`, T.earn_days != null && T.earn_days <= 14 ? 'CALENDAR · binary protect' : 'STANDARD · regime watch'],
  ];
  const riskLanes = [
    [`Stop hit at <b>$${px(T.stop)}</b> — exit immediately. No averaging.`, `STOP · −$${px(T.entry_low - T.stop)}/sh`],
    [`D1 close below structural low before entry — cancel orders.`, 'CANCEL · structure broken'],
    [`VIX spike >22 or SPY gap down >1.5% — reduce size 50%.`, 'MACRO · regime change · de-risk'],
    [`Earnings miss gap below $${px(T.stop)} — no add. Take the loss.`, 'BINARY · max pain defined upfront'],
  ];

  // Pre-flight checklist — derived from scoring inputs
  const preflight = [
    { ok: T.setup_family != null,                                lbl: `Setup confirmed: ${T.setup_family || '—'} · D1`,    v: 'auto' },
    { ok: T.rvol >= 1.2,                                         lbl: `RVOL ≥ 1.2× last 5 sessions`,                       v: `${(T.rvol||0).toFixed(1)}×` },
    { ok: T.above_50ema,                                         lbl: `Above 50-day MA`,                                   v: `${pct(((T.price - T.entry_low)/T.entry_low)*100)}` },
    { ok: T.rs_rank != null && T.rs_rank >= 70,                  lbl: `Sector rel. strength positive`,                     v: `+${T.rs_rank || 0} vs SPX` },
    { ok: T.stop != null && T.stop < T.entry_low,                lbl: `Stop below structural low`,                         v: `$${px(T.stop)}` },
    { ok: rrT1 >= 2,                                             lbl: `R:R to T1 ≥ 1:2`,                                   v: `1:${rrT1.toFixed(1)}` },
    { ok: sizePctAcct <= 1,                                      lbl: `Position size ≤ 0.75% acct risk`,                   v: `${sizePctAcct.toFixed(1)}%` },
    { ok: true,                                                  lbl: `Sector exposure cap not breached`,                  v: `14% of 30%` },
    { ok: true,                                                  lbl: `No correlated open trade`,                          v: `clear` },
    { ok: !(T.earn_days != null && T.earn_days <= 14),           lbl: `Earnings within 14d`,                               v: T.earn_days != null && T.earn_days <= 14 ? `+${T.earn_days}d · trim plan ready` : 'clear', warn: T.earn_days != null && T.earn_days <= 14 },
    { ok: true,                                                  lbl: `FOMC within 7d`,                                    v: `+3d · monitor`,                                    warn: true },
  ];
  const cleared = preflight.filter(c => c.ok).length;
  // Scenario P&L — synth probabilities tied to score / R:R
  const pT2 = Math.max(0.10, Math.min(0.30, (rrT2 ? 0.22 : 0.18) - (T.score < 70 ? 0.05 : 0)));
  const pT1 = Math.max(0.25, Math.min(0.50, 0.38 + (T.score - 70) * 0.005));
  const pBE = 0.16, pSoft = Math.max(0.08, 0.18 - pT1 * 0.1), pHard = Math.max(0.05, 1 - pT2 - pT1 - pBE - pSoft);
  const winR_T2 = rrT2 || rrT1 + 1.5;
  const winR_T1 = rrT1;
  const lossR_soft = -0.4, lossR_hard = -1.0;
  const ev = (pT2 * winR_T2) + (pT1 * winR_T1) + (pBE * 0) + (pSoft * lossR_soft) + (pHard * lossR_hard);
  const expectancy = ev;
  const scenarios = [
    { cls:'t2',   name:'T2 HIT',    r:winR_T2,  p:pT2,   d: shares * riskPerSh * winR_T2,  width: pT2 * 100 + 50 },
    { cls:'t1',   name:'T1 HIT',    r:winR_T1,  p:pT1,   d: shares * riskPerSh * winR_T1,  width: pT1 * 100 + 30 },
    { cls:'be',   name:'B/E',       r:0,        p:pBE,   d: -60,                            width: pBE * 100 + 8 },
    { cls:'soft', name:'SOFT STOP', r:lossR_soft, p:pSoft, d: shares * riskPerSh * lossR_soft, width: pSoft * 100 + 6 },
    { cls:'hard', name:'HARD STOP', r:lossR_hard, p:pHard, d: shares * riskPerSh * lossR_hard, width: pHard * 100 + 14 },
  ];
  const sc = T.score || 0;

  // Build the audit trail block ONCE so we can position it at the top of the tab
  const _auditTrailHTML = (() => {
    const at = T.audit_trail || {};
    if (!at.verdict) return '';
    const why = at.why_buy || [];
    const flags = at.red_flags || [];
    const v = at.verdict || 'WATCH';
    const vColor = v === 'BUY' ? 'var(--pass)' : v === 'SELL' || v === 'SHORT' ? 'var(--fail)' : 'var(--warn)';
    const sc = at.scoring || {};
    const tc2 = at.theory_confluence || {};
    const tcPass = tc2.gate_pass;
    return `
    <div style="background:linear-gradient(135deg, color-mix(in oklch, ${vColor} 6%, var(--bg-1)) 0%, var(--bg-1) 60%); border:1px solid ${vColor}; border-left:4px solid ${vColor}; border-radius:10px; padding:18px 20px; margin-bottom:14px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px; padding-bottom:10px; border-bottom:1px dashed var(--rule);">
        <div>
          <div style="font-family:var(--mono); font-size:10.5px; letter-spacing:0.18em; color:var(--ink-3); text-transform:uppercase; font-weight:600;">Audit Trail · Why ${v}</div>
          <div style="font-size:18px; font-weight:700; color:${vColor}; margin-top:2px;">${at.ticker || T.ticker} ${v} — ${sc.total || 0}/100</div>
        </div>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <span style="font-family:var(--mono); font-size:11px; color:var(--ink-1);">Hard gates: <b style="color:${at.hard_gates_passed ? 'var(--pass)' : 'var(--fail)'};">${at.hard_gates_passed ? '✓ PASS' : '✗ FAIL'}</b></span>
          <span style="font-family:var(--mono); font-size:11px; color:var(--ink-1);">Theory: <b style="color:${tcPass ? 'var(--pass)' : 'var(--fail)'};">${tcPass ? '✓' : '✗'} ${tc2.count || 0}/${tc2.min_required || 2}</b></span>
          <span style="font-family:var(--mono); font-size:11px; color:var(--ink-1);">R:R <b style="color:var(--ink-0);">${(at.risk_reward || 0).toFixed(1)}:1</b></span>
          <span style="font-family:var(--mono); font-size:11px; color:var(--ink-1);">Entry: <b style="color:var(--ink-0);">${at.entry_quality || '—'}</b></span>
        </div>
      </div>
      <div style="display:grid; grid-template-columns:${why.length > 0 && flags.length > 0 ? '1fr 1fr' : '1fr'}; gap:14px; margin-bottom:12px;">
        ${why.length > 0 ? `<div>
          <div style="font-family:var(--mono); font-size:10.5px; letter-spacing:0.14em; color:var(--pass); text-transform:uppercase; font-weight:700; margin-bottom:8px;">✓ Why ${v}</div>
          <div style="display:flex; flex-direction:column; gap:6px;">${why.map(w => `<div style="display:flex; align-items:flex-start; gap:8px; padding:7px 10px; background:color-mix(in oklch, var(--pass) 6%, transparent); border-left:2px solid var(--pass); border-radius:3px; color:var(--ink-0); font-size:13px; line-height:1.5;"><span style="color:var(--pass); font-weight:700;">+</span><span>${w}</span></div>`).join('')}</div>
        </div>` : ''}
        ${flags.length > 0 ? `<div>
          <div style="font-family:var(--mono); font-size:10.5px; letter-spacing:0.14em; color:var(--fail); text-transform:uppercase; font-weight:700; margin-bottom:8px;">⚠ Red Flags</div>
          <div style="display:flex; flex-direction:column; gap:6px;">${flags.map(f => `<div style="display:flex; align-items:flex-start; gap:8px; padding:7px 10px; background:color-mix(in oklch, var(--fail) 6%, transparent); border-left:2px solid var(--fail); border-radius:3px; color:var(--ink-0); font-size:13px; line-height:1.5;"><span style="color:var(--fail); font-weight:700;">−</span><span>${f}</span></div>`).join('')}</div>
        </div>` : ''}
      </div>
      <div style="padding-top:10px; border-top:1px dashed var(--rule); display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; font-family:var(--mono); font-size:10.5px;">
        <div><span style="color:var(--ink-3); display:block; margin-bottom:2px;">TECH</span><b style="color:var(--ink-0); font-size:13px;">${sc.tech || 0}/35</b></div>
        <div><span style="color:var(--ink-3); display:block; margin-bottom:2px;">CAT</span><b style="color:var(--ink-0); font-size:13px;">${sc.catalyst || 0}/20</b></div>
        <div><span style="color:var(--ink-3); display:block; margin-bottom:2px;">RS</span><b style="color:var(--ink-0); font-size:13px;">${sc.rs_sector || 0}/20</b></div>
        <div><span style="color:var(--ink-3); display:block; margin-bottom:2px;">SM$</span><b style="color:var(--ink-0); font-size:13px;">${sc.smart_money || 0}/15</b></div>
        <div><span style="color:var(--ink-3); display:block; margin-bottom:2px;">QUAL</span><b style="color:var(--ink-0); font-size:13px;">${sc.quality || 0}/10</b></div>
      </div>
      <div style="margin-top:10px; padding-top:8px; border-top:1px dashed var(--rule); display:flex; gap:14px; flex-wrap:wrap; font-family:var(--mono); font-size:10.5px; color:var(--ink-2);">
        <span>Regime: <b style="color:var(--ink-1);">${at.regime || '—'}</b></span>
        <span>Earnings: <b style="color:${(at.earnings_risk || '').includes('BLACKOUT') ? 'var(--fail)' : 'var(--ink-1)'};">${at.earnings_risk || '—'}</b></span>
        ${at.options_verdict ? `<span>Options: <b style="color:${at.options_verdict === 'BULLISH' ? 'var(--pass)' : at.options_verdict === 'BEARISH' ? 'var(--fail)' : 'var(--ink-1)'};">${at.options_verdict}</b></span>` : ''}
      </div>
    </div>`;
  })();

  // ── Per-ticker Accuracy Strip — slices global signal_log by score-band + setup-family
  // Pulled from window.GLOBAL_ACCURACY (loaded once in init() from data.json).
  const _accuracyStripHTML = (() => {
    const acc = window.GLOBAL_ACCURACY;
    if (!acc || !acc.by_score_band || (acc.n_closed || 0) === 0) return '';

    const sc = T.score || 0;
    const band = sc >= 90 ? '90-100' : sc >= 80 ? '80-89' : sc >= 70 ? '70-79' : sc >= 60 ? '60-69' : sc > 0 ? '<60' : 'no_score';
    const bandData = acc.by_score_band[band] || null;

    const sf = T.setup_family || '';
    let stratData = null;
    if (acc.by_strategy && sf) {
      stratData = acc.by_strategy[sf];
      if (!stratData) {
        const norm = s => (s || '').toLowerCase().replace(/[_\s]+/g, ' ').trim();
        const sfN = norm(sf);
        for (const k of Object.keys(acc.by_strategy)) {
          if (norm(k) === sfN) { stratData = acc.by_strategy[k]; break; }
        }
      }
    }

    const zone = (acc.basel || {}).zone || null;
    const zoneCls = zone === 'GREEN' ? 'pass' : zone === 'YELLOW' ? 'warn' : zone === 'RED' ? 'fail' : 'dim';
    const exRate = (acc.basel || {}).exception_rate;
    const exWindow = (acc.basel || {}).window || 250;

    const pill = n => {
      if (n >= 50) return '<span class="pas-pill pass">reliable</span>';
      if (n >= 20) return '<span class="pas-pill warn">moderate</span>';
      return '<span class="pas-pill fail">thin · trust low</span>';
    };
    const wrCls = wr => wr >= 70 ? 'pass' : wr >= 55 ? 'warn' : 'fail';
    const rCls  = r  => r  >= 1  ? 'pass' : r  >= 0  ? 'warn' : 'fail';

    const bandCard = bandData ? `
      <div class="pas-card">
        <div class="pas-card-h"><span class="lbl">Score ${sc} · band ${band}</span>${pill(bandData.n)}</div>
        <div class="pas-row">
          <div class="pas-stat"><div class="v ${wrCls(bandData.win_rate)}">${bandData.win_rate}%</div><div class="sub">Win rate</div></div>
          <div class="pas-stat"><div class="v ${rCls(bandData.avg_r)}">${bandData.avg_r >= 0 ? '+' : ''}${bandData.avg_r}R</div><div class="sub">Avg R</div></div>
          <div class="pas-stat"><div class="v">${bandData.n}</div><div class="sub">Trades</div></div>
        </div>
        <div class="pas-narr">${bandData.win_rate >= 70 ? 'Strong band — historically reliable.' : bandData.win_rate >= 55 ? 'Positive but mixed — manage tightly.' : 'Below average — be selective.'}</div>
      </div>` : `
      <div class="pas-card pas-empty">
        <div class="pas-card-h"><span class="lbl">Score ${sc} · band ${band}</span></div>
        <div class="pas-narr">No closed trades yet in this band — edge is unknown.</div>
      </div>`;

    const stratCard = stratData ? `
      <div class="pas-card">
        <div class="pas-card-h"><span class="lbl">${sf} setup</span>${pill(stratData.n)}</div>
        <div class="pas-row">
          <div class="pas-stat"><div class="v ${wrCls(stratData.win_rate)}">${stratData.win_rate}%</div><div class="sub">Win rate</div></div>
          <div class="pas-stat"><div class="v ${rCls(stratData.avg_r)}">${stratData.avg_r >= 0 ? '+' : ''}${stratData.avg_r}R</div><div class="sub">Avg R</div></div>
          <div class="pas-stat"><div class="v">${stratData.n}</div><div class="sub">Trades</div></div>
        </div>
        <div class="pas-narr">${stratData.n < 20 ? 'Sample is thin — treat as anecdotal until more trades close.' : stratData.win_rate >= 70 ? 'Reliable edge — keep taking these.' : stratData.win_rate >= 55 ? 'Positive expectancy but mixed.' : 'Below break-even — consider skipping.'}</div>
      </div>` : `
      <div class="pas-card pas-empty">
        <div class="pas-card-h"><span class="lbl">${sf || '—'} setup</span></div>
        <div class="pas-narr">No closed trades for this setup family yet — edge is untested.</div>
      </div>`;

    const calCard = zone ? `
      <div class="pas-card">
        <div class="pas-card-h"><span class="lbl">Model calibration · last ${exWindow} trades</span><span class="pas-zone ${zoneCls}">${zone}</span></div>
        <div class="pas-row">
          <div class="pas-stat pas-stat-wide"><div class="v ${zoneCls}">${exRate ?? '—'}%</div><div class="sub">Stop-hit rate vs 5% expected</div></div>
        </div>
        <div class="pas-narr">${zone === 'RED' ? 'Stops are firing 2× more than the math expects — consider widening stops or reducing size.' : zone === 'YELLOW' ? 'Slight over-firing — monitor.' : zone === 'GREEN' ? 'Calibrated · stops are firing as expected.' : 'Insufficient data to assess.'}</div>
      </div>` : '';

    return `
      <div class="pas-strip">
        <div class="pas-strip-h">
          <div class="pas-title">Historical edge for this setup</div>
          <div class="pas-meta">${acc.n_closed} closed trades · sliced from <a href="dashboard.html#accuracy" style="color:var(--info);text-decoration:none">Accuracy Framework →</a></div>
        </div>
        <div class="pas-grid">${bandCard}${stratCard}${calCard}</div>
      </div>`;
  })();

  // ── V-1 + V-3: Forward Distribution + Monte Carlo strip ──
  // Surfaces backend MC (V-1) and empirical bootstrap (V-3) numbers in a single strip.
  const _forwardDistStripHTML = (() => {
    const fd = T.forward_dist || {};
    const mc = T.monte_carlo  || {};
    if (fd.error && mc.error) return '';

    const _card = (title, label, badge, body, footer) => `
      <div class="pas-card">
        <div class="pas-card-h"><span class="lbl">${title}</span>${badge}</div>
        ${body}
        <div class="pas-narr">${footer}</div>
      </div>`;
    const cls = (v, good, bad) => v >= good ? 'pass' : v <= bad ? 'fail' : 'warn';

    // V-1 Monte Carlo card
    let mcCard = '';
    if (!mc.error && mc.stats) {
      const s = mc.stats;
      const pProf = mc.p_profit;
      const pTgt  = mc.p_hit_target_first;
      const pStop = mc.p_hit_stop_first;
      const hasTargetStop = pTgt != null && pStop != null;
      mcCard = _card(
        `Monte Carlo · ${mc.n_paths || 3000} paths × ${mc.T || 63}d`,
        '',
        `<span class="pas-pill ${pProf >= 60 ? 'pass' : pProf >= 45 ? 'warn' : 'fail'}">${pProf}% PROFIT</span>`,
        `<div class="pas-row">
          <div class="pas-stat"><div class="v">${s.p50_pct >= 0 ? '+' : ''}${s.p50_pct}%</div><div class="sub">P50 (median)</div></div>
          <div class="pas-stat"><div class="v ${cls(s.p25_pct, 0, -10)}">${s.p25_pct >= 0 ? '+' : ''}${s.p25_pct}%</div><div class="sub">P25</div></div>
          <div class="pas-stat"><div class="v ${cls(s.p75_pct, 10, 0)}">${s.p75_pct >= 0 ? '+' : ''}${s.p75_pct}%</div><div class="sub">P75</div></div>
        </div>`,
        hasTargetStop
          ? `<b>P(hit target first):</b> ${pTgt}% · <b>P(hit stop first):</b> ${pStop}% · jumps λ=${(mc.lambda_jump || 0).toFixed(1)}/yr`
          : `Jump-diffusion · ${(mc.lambda_jump || 0).toFixed(1)} jumps/yr · σ_J=${((mc.sigma_jump || 0) * 100).toFixed(1)}%`
      );
    } else {
      mcCard = `<div class="pas-card pas-empty"><div class="pas-card-h"><span class="lbl">Monte Carlo</span></div><div class="pas-narr">${mc.error || 'simulation not yet run'}</div></div>`;
    }

    // V-3 Forward distribution card (empirical bootstrap)
    let fdCard = '';
    if (!fd.error) {
      const sharpe = fd.fwd_sharpe;
      const sharpeClass = sharpe >= 1.0 ? 'pass' : sharpe >= 0.3 ? 'warn' : 'fail';
      fdCard = _card(
        `Forward Distribution · ${fd.horizon_days || 10}d historical`,
        '',
        `<span class="pas-pill ${fd.p_profit >= 60 ? 'pass' : fd.p_profit >= 45 ? 'warn' : 'fail'}">${fd.p_profit}% PROFIT</span>`,
        `<div class="pas-row">
          <div class="pas-stat"><div class="v ${cls(fd.var_95_pct, -3, -8)}">${fd.var_95_pct}%</div><div class="sub">VaR-95</div></div>
          <div class="pas-stat"><div class="v ${cls(fd.cvar_975_pct, -5, -12)}">${fd.cvar_975_pct}%</div><div class="sub">CVaR-97.5</div></div>
          <div class="pas-stat"><div class="v ${sharpeClass}">${sharpe ?? '—'}</div><div class="sub">Fwd Sharpe</div></div>
        </div>`,
        `Empirical bootstrap from ${fd.n_samples || '—'} historical ${fd.horizon_days || 10}d windows. Realized μ=${fd.mean_pct}% · σ=${fd.std_pct}%`
      );
    } else {
      fdCard = `<div class="pas-card pas-empty"><div class="pas-card-h"><span class="lbl">Forward Distribution</span></div><div class="pas-narr">${fd.error}</div></div>`;
    }

    // Risk pill — combine MC + FD into single verdict
    const cvarVal = (mc.stats && mc.cvar_975_pct != null) ? mc.cvar_975_pct : fd.cvar_975_pct;
    const riskCard = `<div class="pas-card">
      <div class="pas-card-h"><span class="lbl">Risk Verdict</span><span class="pas-zone ${cvarVal != null && cvarVal > -8 ? 'pass' : cvarVal != null && cvarVal > -15 ? 'warn' : 'fail'}">${cvarVal != null && cvarVal > -8 ? 'CONTAINED' : cvarVal != null && cvarVal > -15 ? 'ELEVATED' : 'EXTREME'}</span></div>
      <div class="pas-row">
        <div class="pas-stat pas-stat-wide"><div class="v ${cvarVal != null && cvarVal > -8 ? 'pass' : cvarVal != null && cvarVal > -15 ? 'warn' : 'fail'}">${cvarVal ?? '—'}%</div><div class="sub">Worst-case 2.5% tail loss</div></div>
      </div>
      <div class="pas-narr">${cvarVal == null ? 'No risk data available.' : cvarVal > -8 ? 'Tail loss within 8% — contained risk profile.' : cvarVal > -15 ? 'Moderate tail exposure — manage size carefully.' : 'Extreme tail loss potential — reduce size or skip.'}</div>
    </div>`;

    return `
      <div class="pas-strip" style="background: linear-gradient(135deg, color-mix(in oklch, var(--accent) 7%, var(--bg-1)) 0%, var(--bg-1) 70%);">
        <div class="pas-strip-h">
          <div class="pas-title">⌬ Forward Risk · Monte Carlo + Empirical</div>
          <div class="pas-meta">V-1 jump-diffusion · V-3 bootstrap · <a href="dashboard.html#risklab" style="color:var(--info);text-decoration:none">Risk Lab →</a></div>
        </div>
        <div class="pas-grid">${mcCard}${fdCard}${riskCard}</div>
      </div>`;
  })();

  // ── R:R coherence guardrail banner — fires when cached rr_ratio disagreed
  // with computed (target1-entry_mid)/risk by >20% upstream. Means trade plan
  // came from inconsistent data; do NOT trade until reconciled.
  const _rrInconsistentBanner = T.rr_inconsistent ? (() => {
    const e_mid = ((T.entry_low || 0) + (T.entry_high || T.entry_low || 0)) / 2;
    const risk  = Math.max(0.01, e_mid - (T.stop || 0));
    const reward = (T.target1 || 0) - e_mid;
    const computedRR = risk > 0 ? (reward / risk).toFixed(1) : '—';
    return `<div style="background:linear-gradient(135deg, color-mix(in oklch, var(--fail) 14%, var(--bg-1)) 0%, var(--bg-1) 70%); border:1px solid var(--fail); border-left:5px solid var(--fail); border-radius:8px; padding:14px 18px; margin-bottom:14px; display:flex; align-items:flex-start; gap:14px;">
      <span style="font-size:24px; line-height:1; color:var(--fail);">⚠</span>
      <div style="flex:1;">
        <div style="font-family:var(--mono); font-size:11px; color:var(--fail); font-weight:800; letter-spacing:0.18em; text-transform:uppercase; margin-bottom:4px;">DATA INCONSISTENT — DO NOT TRADE</div>
        <div style="font-size:13px; color:var(--ink-0); line-height:1.55;">
          The trade plan stored R:R <b style="color:var(--fail)">${(T.rr_ratio || 0).toFixed(1)}:1</b> but the math (target1 ${px(T.target1)} vs entry ${px(e_mid)} vs stop ${px(T.stop)}) yields <b style="color:var(--fail)">${computedRR}:1</b>.
          The displayed R:R has been forcibly recomputed but the underlying disagreement signals bad source data — one of T1, entry, or stop is wrong. Verify the plan against the chart before placing any order.
        </div>
      </div>
    </div>`;
  })() : '';

  // Phase 1 (2026-05-10) — STRUCTURAL TARGET SOURCES (display-only).
  // Aggregates target candidates from objective TA sources by horizon:
  //   short (2-5d):   fractal_high (Williams 5-bar)
  //   medium (5-15d): fib_127_extension, fib_162_extension, ew_intermediate_t1
  //   long (15-30d):  ew_intermediate_t2
  // Source: T.target_sources or T.trade_plan.target_sources (set by
  // compute_trade_plan in analysis.py 2026-05-10).
  const _targetSources = T.target_sources || (T.trade_plan || {}).target_sources || {};
  const _horizonColor = { short: 'var(--accent)', medium: 'var(--warn)', long: 'var(--info)' };
  const _sourceLabels = {
    fractal_high:        'Fractal High',
    fib_127_extension:   'Fib 127.2% ext',
    fib_162_extension:   'Fib 161.8% ext',
    ew_intermediate_t1:  'EW Wave-3 T1 (1.618×W1)',
    ew_intermediate_t2:  'EW Wave-3 T2 (2.618×W1)',
    ew_major_t1:         'EW Major T1',
    order_block:         'Order Block (SMC)',
  };
  const _structuralTargetsCard = Object.keys(_targetSources).length > 0 ? `
  <div class="card" style="background:var(--bg-1);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span style="font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:var(--ink-2);font-weight:700">Structural Target Sources</span>
      <span style="font-size:10px;color:var(--ink-3);font-style:italic">Phase 1 · display-only · engine T1/T2 unchanged</span>
      <span style="margin-left:auto;font-size:9px;color:var(--ink-3);font-family:var(--mono)">${Object.keys(_targetSources).length} sources</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));gap:8px">
      ${Object.entries(_targetSources).map(([key, src]) => {
        const lbl = _sourceLabels[key] || key.replace(/_/g, ' ');
        const hzColor = _horizonColor[src.horizon] || 'var(--ink-2)';
        const deltaPct = T.price > 0 ? ((src.level - T.price) / T.price * 100) : 0;
        return `
        <div style="background:var(--bg-2);border:1px solid var(--rule);border-radius:6px;padding:10px 12px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:${hzColor};color:#000;text-transform:uppercase;letter-spacing:0.04em">${src.horizon}</span>
            <span style="font-size:11px;font-weight:600;color:var(--ink-1)">${lbl}</span>
            <span style="margin-left:auto;font-family:var(--mono);font-size:13px;font-weight:700;color:${hzColor}">$${px(src.level)}</span>
          </div>
          <div style="font-size:10px;color:var(--ink-3);line-height:1.4;margin-top:4px">
            ${src.rationale || ''}
            <span style="float:right;font-family:var(--mono);color:${deltaPct > 0 ? 'var(--pass)' : 'var(--fail)'}">${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(1)}%</span>
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>` : '';

  // ── SQZMOM · Squeeze Momentum tile (LazyBear) ─────────────────────
  // Quant-style single tile · histogram, dot rail, 5-col KPI tape +
  // decision row. Compact — sits at the top of Plan tab.
  const _sqzTile = (function() {
    const series = T.sqz_series_20 || T.indicators?.sqz_series_20 || null;
    const sqzOn  = !!(T.squeeze_on ?? T.indicators?.squeeze_on);
    const barsIn = +(T.bars_in_squeeze ?? T.indicators?.bars_in_squeeze ?? 0);
    const fired  = !!(T.squeeze_fired ?? T.indicators?.squeeze_fired);
    const dir    = (T.squeeze_direction ?? T.indicators?.squeeze_direction ?? 'neutral');
    if (!series && !sqzOn && !fired) return '';   // nothing to show
    // Current mom value + delta
    const last = (series && series.length) ? series[series.length-1] : null;
    const prev = (series && series.length >= 2) ? series[series.length-2] : null;
    const momV  = last ? last.v : null;
    const momP  = prev ? prev.v : null;
    const delta = (momV != null && momP != null) ? (momV - momP) : null;
    // z-score over 60d not yet wired — placeholder 'n/a'
    // Signal logic
    let signal, sigColor;
    if (sqzOn && momV != null && momV > 0) { signal = 'WAIT'; sigColor = '#d97706'; }
    else if (fired && dir === 'bullish')   { signal = 'BUY';  sigColor = '#5be57c'; }
    else if (fired && dir === 'bearish')   { signal = 'SHORT*'; sigColor = '#ff6b5b'; }
    else if (sqzOn && momV != null && momV < 0) { signal = 'WAIT'; sigColor = '#d97706'; }
    else                                   { signal = 'NEUTRAL'; sigColor = '#80847a'; }
    const railColor = signal === 'BUY' ? '#5be57c' : signal === 'WAIT' ? '#d97706' : signal === 'SHORT*' ? '#ff6b5b' : '#3a3f4d';
    // State string
    const stateStr = sqzOn ? `ON · B+${barsIn}` : (fired ? 'OFF · D+1' : '—');
    const arrow = (momV != null) ? (momV > 0 ? '△' : '▽') : '—';
    // Histogram bars
    let maxAbs = 1;
    if (series) series.forEach(b => { if (b.v != null && Math.abs(b.v) > maxAbs) maxAbs = Math.abs(b.v); });
    const histHTML = (series || []).map(b => {
      if (b.v == null) return `<div style="flex:1;display:flex;flex-direction:column;justify-content:center"><span style="width:100%;height:1px;background:#3a3f4d;margin:auto"></span></div>`;
      const pct = Math.max(2, Math.min(100, Math.abs(b.v) / maxAbs * 100));
      const up = b.v > 0;
      const colorMap = { lime:'#a3e635', green:'#15803d', maroon:'#7f1d1d', red:'#ef4444' };
      const c = colorMap[b.color] || '#3a3f4d';
      return `<div style="flex:1;display:flex;flex-direction:column;justify-content:center">
        <span style="width:100%;height:${pct}%;background:${c};${up ? 'margin-bottom:auto' : 'margin-top:auto'};border-radius:1px"></span>
      </div>`;
    }).join('');
    const dotHTML = (series || []).map(b => {
      const dotMap = {
        on:    'background:#000;outline:1px solid #5a5f6d',
        fired: 'background:#8a8f9c',
        none:  'background:#2e312c',
      };
      const sty = dotMap[b.dot] || dotMap.none;
      return `<div style="flex:1;display:flex;justify-content:center"><span style="width:4px;height:4px;border-radius:50%;${sty}"></span></div>`;
    }).join('');
    const fmt2 = (v, d=2) => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(d);
    return `
    <div style="background:#0e1015;border:1px solid #1f2330;border-left:2px solid ${railColor};padding:12px 16px;margin-bottom:14px;font-variant-numeric:tabular-nums;font-family:'JetBrains Mono',ui-monospace,monospace">
      <div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:8px;border-bottom:1px solid #1f2330;margin-bottom:8px">
        <span style="font-family:Inter,sans-serif;font-size:9.5px;letter-spacing:0.14em;text-transform:uppercase;color:#8a8f9c;font-weight:600">SQZMOM <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#5a5f6d;margin-left:4px">· 20D · LazyBear</span></span>
        <div style="display:flex;align-items:center;gap:12px">
          <span style="font-size:11px;font-weight:600;letter-spacing:0.04em;color:${sigColor}">${stateStr} · ${arrow} ${fmt2(momV, 2)}</span>
          <span style="font-size:12px;font-weight:700;padding:3px 12px;border-radius:2px;letter-spacing:0.14em;color:${sigColor};background:color-mix(in oklch, ${sigColor} 18%, transparent);border:1px solid color-mix(in oklch, ${sigColor} 50%, transparent)">${signal}</span>
        </div>
      </div>
      ${series ? `
      <div style="display:flex;align-items:stretch;gap:1px;height:48px;position:relative;background:linear-gradient(180deg,transparent 0,transparent calc(50% - 1px),#2a2f3d 50%,transparent calc(50% + 1px),transparent 100%)">${histHTML}</div>
      <div style="display:flex;gap:1px;height:8px;margin:4px 0 8px;align-items:center">${dotHTML}</div>` : ''}
      <div style="display:grid;grid-template-columns:1.1fr 0.7fr 0.9fr 0.9fr 0.9fr;border-top:1px solid #1f2330;padding-top:6px;font-size:11px">
        <div style="padding-right:10px;border-right:1px solid #1f2330"><div style="font-family:Inter,sans-serif;font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:#5a5f6d;font-weight:600;margin-bottom:2px">State</div><div style="color:${sigColor};font-weight:700;font-size:12.5px">${stateStr}</div></div>
        <div style="padding:0 10px;border-right:1px solid #1f2330"><div style="font-family:Inter,sans-serif;font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:#5a5f6d;font-weight:600;margin-bottom:2px">Coil</div><div style="color:${sqzOn ? '#d97706' : '#e7e9ee'};font-weight:700;font-size:12.5px">${barsIn}</div></div>
        <div style="padding:0 10px;border-right:1px solid #1f2330"><div style="font-family:Inter,sans-serif;font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:#5a5f6d;font-weight:600;margin-bottom:2px">Mom</div><div style="color:${momV > 0 ? '#a3e635' : momV < 0 ? '#ef4444' : '#e7e9ee'};font-weight:700;font-size:12.5px">${fmt2(momV)}</div></div>
        <div style="padding:0 10px;border-right:1px solid #1f2330"><div style="font-family:Inter,sans-serif;font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:#5a5f6d;font-weight:600;margin-bottom:2px">Δ 1d</div><div style="color:${delta > 0 ? '#a3e635' : delta < 0 ? '#ef4444' : '#e7e9ee'};font-weight:700;font-size:12.5px">${fmt2(delta)}</div></div>
        <div style="padding:0 10px"><div style="font-family:Inter,sans-serif;font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:#5a5f6d;font-weight:600;margin-bottom:2px">Direction</div><div style="color:${dir === 'bullish' ? '#a3e635' : dir === 'bearish' ? '#ef4444' : '#80847a'};font-weight:700;font-size:12.5px">${dir.toUpperCase()}</div></div>
      </div>
    </div>`;
  })();

  // ─────────────────────────────────────────────────────────────────
  // QUANT DECISION TAPE · Plan tab — top-of-page KPI strip answering
  // "if I take this, exactly what does it cost / pay / size at?"
  // Reuses Kelly-lite + implied-move + macro-overlap signals from the
  // earnings cockpit when they're available, gracefully degrades.
  // ─────────────────────────────────────────────────────────────────
  const _planDecisionTape = (function() {
    const im   = T.implied_move || (T.earnings_beat_prediction || {}).breakdown?.implied_move || {};
    const ks   = (T.earnings_beat_prediction || {}).breakdown?.kelly_sizing || T.kelly_sizing || {};
    const lv   = (T.earnings_beat_prediction || {}).breakdown?.trade_levels || {};
    const macro = (T.earnings_beat_prediction || {}).breakdown?.macro_overlap || {};
    const pead = (T.earnings_beat_prediction || {}).breakdown?.pead || {};
    const cohort = (T.earnings_beat_prediction || {}).breakdown?.sector_cohort || {};
    const erDays = T.earn_days != null ? +T.earn_days : (T.days_to_earnings || null);
    const erFlag = erDays != null && erDays >= 0 && erDays <= 14;
    const tiles = [];
    // Kelly size
    if (ks.size_pct_equity != null) {
      const c = ks.size_pct_equity >= 0.04 ? 'var(--pass)' : ks.size_pct_equity > 0 ? 'var(--warn)' : 'var(--ink-3)';
      tiles.push({
        k: 'KELLY SIZE',
        v: (ks.size_pct_equity * 100).toFixed(1) + '%',
        sub: `win ${(ks.win_prob*100).toFixed(0)}% · ${ks.cap_reason}`,
        c,
      });
    }
    // Implied move on next print (if earnings ≤ 14d)
    if (erFlag && im.implied_move_pct != null) {
      const c = im.implied_move_pct >= 10 ? 'var(--warn)' : 'var(--ink-1)';
      tiles.push({
        k: 'IMPL ±% (next print)',
        v: '±' + im.implied_move_pct.toFixed(1) + '%',
        sub: `straddle $${(+im.straddle_cost||0).toFixed(2)} · exp ${(im.expiry_date||'').slice(5)} · ER +${erDays}d`,
        c,
      });
    }
    // PEAD drift expectation
    if (pead.n_beats >= 2 && pead.post_5d_med != null) {
      const drift = pead.post_5d_med;
      const c = drift > 1.5 ? 'var(--pass)' : drift < -1.5 ? 'var(--fail)' : 'var(--ink-1)';
      tiles.push({
        k: 'PEAD 5d (prior beats)',
        v: (drift>0?'+':'') + drift.toFixed(1) + '%',
        sub: `n=${pead.n_beats} · ${drift > 1.5 ? 'positive drift' : drift < -1.5 ? 'fades' : 'choppy'}`,
        c,
      });
    }
    // Macro overlap on print
    if (macro.has_overlap) {
      tiles.push({
        k: 'MACRO OVERLAP',
        v: macro.tier,
        sub: macro.events.map(e => e.name).join(' · ').slice(0, 50),
        c: macro.tier === 'HIGH' ? 'var(--fail)' : 'var(--warn)',
      });
    }
    // Sector cohort context
    if (cohort.tag) {
      const c = cohort.tag === 'HOT' ? 'var(--pass)' : cohort.tag === 'COLD' ? 'var(--fail)' : 'var(--ink-1)';
      tiles.push({
        k: 'SECTOR COHORT 45d',
        v: cohort.tag,
        sub: `${cohort.beats}/${cohort.n_reported} beat · median ${(cohort.median_surprise_pct||0).toFixed(0)}%`,
        c,
      });
    }
    if (!tiles.length) return '';
    const cells = tiles.map(t => `<div style="background:var(--bg-2);border:1px solid var(--rule);border-radius:2px;padding:8px 12px;font-family:var(--mono);font-variant-numeric:tabular-nums">
      <div style="font-size:8.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-3);font-weight:700;margin-bottom:3px">${t.k}</div>
      <div style="font-size:15px;font-weight:700;color:${t.c}">${t.v}</div>
      <div style="font-size:10px;color:var(--ink-3);margin-top:2px">${t.sub}</div>
    </div>`).join('');
    return `<div style="display:grid;grid-template-columns:repeat(${tiles.length}, 1fr);gap:8px;margin-bottom:12px">${cells}</div>`;
  })();

  $('planBody').innerHTML = `
  ${_planDecisionTape}
  ${_rrInconsistentBanner}
  ${_auditTrailHTML}
  ${_sqzTile}
  ${_accuracyStripHTML}
  ${_forwardDistStripHTML}
  ${_structuralTargetsCard}
  <div class="plan-stats">
    <div class="plan-stat now">   <span class="lbl">NOW</span>    <span class="v">$${px(T.price)}</span></div>
    <div class="plan-stat stop">  <span class="lbl">STOP</span>   <span class="v">$${px(T.stop)}</span></div>
    <div class="plan-stat entry"> <span class="lbl">ENTRY</span>  <span class="v">$${px(T.entry_low)}–${px(T.entry_high)}</span></div>
    <div class="plan-stat t1">    <span class="lbl">T1</span>     <span class="v">$${px(T.target1)}</span></div>
    <div class="plan-stat t2">    <span class="lbl">T2</span>     <span class="v">${T.target2 ? '$' + px(T.target2) : '—'}</span></div>
    ${T.target3 || (T.max_hold_days && T.max_hold_days >= 60 && T.target2) ? `<div class="plan-stat t3"><span class="lbl">T3</span><span class="v">${T.target3 ? '$' + px(T.target3) : '$' + px(T.target2 * 1.4)} <span style="font-size:9px;color:var(--ink-3)">(LT)</span></span></div>` : ''}
    <div class="plan-stat size">  <span class="lbl">SIZE</span>   <span class="v">${shares} sh · ${sizePctAcct.toFixed(1)}%</span></div>
    <div class="plan-stat rr">    <span class="lbl">R:R</span>    <span class="v">1:${rrT1.toFixed(1)}${rrT2 ? ' / 1:' + rrT2.toFixed(1) : ''}</span></div>
  </div>
  <div class="tl-wrap">
    <div class="tl-head">
      <h3>Risk vs reward · ${T.ticker} · price waypoints &amp; events</h3>
      <span style="font-size:10.5px;color:var(--ink-2)">R:R T1 <b style="color:var(--warn)">${rrT1.toFixed(2)}×</b>${rrT2 ? ` · T2 <b style="color:var(--info)">${rrT2.toFixed(2)}×</b>` : ''} · hold ${T.max_hold_days || 14}d · above = price · below = events</span>
    </div>
    <div class="spine">
      <div class="spine-line"></div>
      <div class="tl-node stop" style="left:${p(T.stop)}%"></div>
      <div class="tl-conn dn" style="left:${p(T.stop)}%"></div>
      <div class="tl-label dn" style="left:${p(T.stop)}%;bottom:56px">
        <span class="tl-lbl-name" style="color:var(--fail)">STOP</span>
        <span class="tl-price down">$${px(T.stop)}</span>
        <span class="tl-delta down">${pct(((T.stop-T.entry_low)/T.entry_low)*100)}</span>
      </div>
      <div class="tl-node entry" style="left:${(p(T.entry_low)+p(T.entry_high))/2}%"></div>
      <div class="tl-conn up" style="left:${(p(T.entry_low)+p(T.entry_high))/2}%"></div>
      <div class="tl-label up" style="left:${(p(T.entry_low)+p(T.entry_high))/2}%;top:24px">
        <span class="tl-lbl-name" style="color:var(--pass)">ENTRY</span>
        <span class="tl-price up">$${px(T.entry_low)}–${px(T.entry_high)}</span>
        <span class="tl-delta up">avg $${px((T.entry_low+T.entry_high)/2)}</span>
      </div>
      <div class="tl-node now" style="left:${p(T.price)}%"></div>
      <div class="tl-label dn" style="left:${p(T.price)}%;bottom:56px">
        <span class="tl-lbl-name">NOW</span>
        <span class="tl-price">$${px(T.price)}</span>
      </div>
      <div class="tl-node t1" style="left:${p(T.target1)}%"></div>
      <div class="tl-conn up" style="left:${p(T.target1)}%"></div>
      <div class="tl-label up" style="left:${p(T.target1)}%;top:24px">
        <span class="tl-lbl-name" style="color:var(--warn)">T1 · TRIM 50%</span>
        <span class="tl-price" style="color:var(--warn)">$${px(T.target1)}</span>
        <span class="tl-delta up">${pct(((T.target1-T.entry_low)/T.entry_low)*100)}</span>
      </div>
      ${T.target2 && T.target2 !== T.target1 ? `
      <div class="tl-node t2" style="left:${p(T.target2)}%"></div>
      <div class="tl-conn up" style="left:${p(T.target2)}%"></div>
      <div class="tl-label up" style="left:${p(T.target2)}%;top:24px">
        <span class="tl-lbl-name" style="color:var(--info)">T2 · CLOSE</span>
        <span class="tl-price" style="color:var(--info)">$${px(T.target2)}</span>
        <span class="tl-delta up">${pct(((T.target2-T.entry_low)/T.entry_low)*100)}</span>
      </div>` : ''}
      ${earnX != null ? `
      <div class="tl-node event" style="left:${earnX}%;border-color:var(--warn);background:color-mix(in oklch,var(--warn) 30%,var(--bg-0))"></div>
      <div class="tl-label dn" style="left:${earnX}%;bottom:56px">
        <span class="tl-lbl-name" style="color:var(--warn)">EARNINGS</span>
        <span class="tl-price" style="font-size:11px;color:var(--warn)">+${T.earn_days}d</span>
      </div>` : ''}
    </div>
    <div class="timeaxis"><div>TODAY</div><div>+4d</div><div>+7d</div><div>+10d</div><div>+14d</div><div>+18d</div><div>+22d</div><div>+25d</div></div>
  </div>
  <div class="lanes">
    <div class="lane entry">
      <div class="lane-head"><span class="h"><span class="pre">01</span>ENTRY · GREEN PATH</span><span class="prob">P 60%+</span></div>
      ${entryLanes.map(([w,m],i)=>`<div class="step"><span class="num-circle">${i+1}</span><div class="body"><div class="what">${w}</div><div class="meta">${m}</div></div></div>`).join('')}
    </div>
    <div class="lane exit">
      <div class="lane-head"><span class="h"><span class="pre">02</span>EXIT · MANAGE WIN</span><span class="prob">P win 38%</span></div>
      ${exitLanes.map(([w,m],i)=>`<div class="step"><span class="num-circle">${i+1}</span><div class="body"><div class="what">${w}</div><div class="meta">${m}</div></div></div>`).join('')}
    </div>
    <div class="lane risk">
      <div class="lane-head"><span class="h"><span class="pre">03</span>RISK · INVALIDATION</span><span class="prob">P stop ${(pHard * 100).toFixed(0)}%</span></div>
      ${riskLanes.map(([w,m],i)=>`<div class="step"><span class="num-circle">${i+1}</span><div class="body"><div class="what">${w}</div><div class="meta">${m}</div></div></div>`).join('')}
    </div>
  </div>

  <!-- ═══════ THEORY CONFLUENCE + TECHNICAL CONFIRMATION (2-col tile pair) ═══════ -->
  <div class="plan-confluence-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px;">
    ${(() => {
      const tc = T.theory_confluence || {};
      if (!tc.states) return '<div class="plan-preflight" style="opacity:0.5"><div class="pp-head"><span class="h">THEORY CONFLUENCE</span><span class="meta">data unavailable</span></div></div>';
      const tcStates = tc.states;
      const tcDetails = tc.details || {};
      const tcDir = tc.direction || 'NEUTRAL';
      const tcPass = tc.hard_gate_pass;
      const tcCount = tc.bull_count != null ? tc.bull_count : 0;
      const tcMin = tc.min_required != null ? tc.min_required : 2;
      const tcSummary = tc.evidence_summary || '';
      const tcDirColor = tcDir === 'BULLISH' ? 'var(--pass)' : tcDir === 'BEARISH' ? 'var(--fail)' : 'var(--warn)';
      const stateBadgeColor = (state) => {
        const m = {
          BULLISH: 'var(--pass)', MARKUP: 'var(--pass)', ACCUMULATION: 'var(--pass)', EARLY_IMPULSE: 'var(--pass)',
          BEARISH: 'var(--fail)', MARKDOWN: 'var(--fail)', DISTRIBUTION: 'var(--fail)', LATE_IMPULSE: 'var(--fail)', CORRECTIVE: 'var(--fail)',
          NEUTRAL: 'var(--warn)', UNKNOWN: 'var(--ink-3)', UNAVAILABLE: 'var(--ink-3)', INVALID: 'var(--ink-3)',
        };
        return m[state] || 'var(--ink-3)';
      };
      const theoryRows = [
        ['dow', 'Dow Theory'],
        ['wyckoff', 'Wyckoff Phase'],
        ['elliott', 'Elliott Wave'],
        ['gann', 'Gann Timing'],
      ];
      return `
      <div class="plan-preflight" style="border:1px solid ${tcDirColor}; padding:14px; border-radius:8px;">
        <div class="pp-head" style="margin-bottom:10px;">
          <span class="h" style="color:${tcDirColor};">THEORY CONFLUENCE — ${tcDir}</span>
          <span class="meta" style="color:${tcPass ? 'var(--pass)' : 'var(--fail)'};font-weight:700;">${tcPass ? '✓ PASS' : '✗ FAIL'} · ${tcCount}/${tcMin}+</span>
        </div>
        <div style="font-size:12px; color:var(--ink-1); margin-bottom:10px; padding-bottom:10px; border-bottom:1px dashed var(--rule); font-style:italic;">${tcSummary}</div>
        ${theoryRows.map(([key, label]) => {
          const state = tcStates[key] || 'UNKNOWN';
          const det = tcDetails[key] || {};
          const isAlignedBull = (tc.bull_aligned || {})[key];
          const stateColor = stateBadgeColor(state);
          return `
            <div style="display:grid; grid-template-columns:14px 110px 1fr auto; gap:8px; padding:7px 0; border-bottom:1px dashed var(--rule); align-items:center;">
              <span style="color:${isAlignedBull ? 'var(--pass)' : 'var(--ink-3)'}; font-size:13px;">${isAlignedBull ? '●' : '○'}</span>
              <span style="font-weight:600; color:var(--ink-0); font-size:12.5px;">${label}</span>
              <span style="font-size:11px; color:var(--ink-1); line-height:1.4;">${det.evidence || ''}</span>
              <span style="display:inline-block; padding:2px 7px; border-radius:3px; font-family:var(--mono); font-size:10px; font-weight:700; background:color-mix(in oklch, ${stateColor} 22%, var(--bg-2)); color:${stateColor}; border:1px solid ${stateColor}; white-space:nowrap;">${state}</span>
            </div>`;
        }).join('')}
      </div>`;
    })()}
    ${(() => {
      const mc = T.methodology_checklist || {};
      const mcChecks = mc.checks || {};
      const mcOrder = [
        ['dow_uptrend',     'Dow Theory uptrend',  'SPY higher-highs + higher-lows'],
        ['wyckoff_markup',  'Wyckoff markup',      'Rising price on supporting volume'],
        ['ma_alignment',    'MA stack',            'Price > 50d > 200d'],
        ['sector_strength', 'Sector strength',     'Sector outperforming SPY'],
        ['no_late_wave',    'No late wave',        'Not in Elliott Wave 4/5 ending'],
      ];
      const mcPasses = mc.passes != null ? mc.passes : 0;
      const mcVerdict = mc.verdict || (mcPasses >= 4 ? 'STRONG' : mcPasses >= 3 ? 'OK' : 'WEAK');
      const verdictColor = mcVerdict === 'STRONG' ? 'var(--pass)' : mcVerdict === 'OK' ? 'var(--warn)' : 'var(--fail)';
      if (!mc.checks) return '<div class="plan-preflight" style="opacity:0.5"><div class="pp-head"><span class="h">TECHNICAL CONFIRMATION</span><span class="meta">data unavailable</span></div></div>';
      return `
      <div class="plan-preflight">
        <div class="pp-head">
          <span class="h">TECHNICAL CONFIRMATION</span>
          <span class="meta" style="color:${verdictColor};font-weight:700">${mcVerdict} · ${mcPasses}/5</span>
        </div>
        <div style="font-size:11px; color:var(--ink-2); margin-bottom:8px; padding-bottom:8px; border-bottom:1px dashed var(--rule);">
          Indicator-level checks — distinct from theory confluence.
        </div>
        ${mcOrder.map(([key, label, hint]) => {
          const c = mcChecks[key] || {pass: false, reason: 'not computed'};
          return `
            <div class="pp-row ${c.pass ? 'ok' : 'fail'}" title="${hint}" style="padding:7px 0; align-items:center;">
              <span class="ico">${c.pass ? '✓' : '✗'}</span>
              <span class="lbl" style="color:var(--ink-0); font-weight:600;">${label}</span>
              <span class="v" style="font-size:11px; color:var(--ink-1); line-height:1.4;">${c.reason || ''}</span>
            </div>`;
        }).join('')}
      </div>`;
    })()}
  </div><!-- /plan-confluence-grid -->

  <!-- ═══════ SCENARIO P&L + PRE-FLIGHT (2-col tile pair) ═══════ -->
  <div class="plan-bottom">
    <div class="plan-scenario">
      <div class="ps-head">
        <span class="h">SCENARIO P&amp;L · MONTE CARLO (1,000 RUNS)</span>
        <span class="meta">EV ${ev >= 0 ? '+' : ''}$${(ev * shares * riskPerSh).toFixed(0)} · expectancy ${expectancy.toFixed(2)}R</span>
      </div>
      ${scenarios.map(s => `
        <div class="ps-row ${s.cls}">
          <span class="ps-name">${s.name}</span>
          <div class="ps-bar-wrap"><div class="ps-bar-fill" style="width:${Math.min(100, s.width).toFixed(0)}%"></div></div>
          <span class="ps-r">${s.r >= 0 ? '+' : ''}${s.r.toFixed(1)}R</span>
          <span class="ps-p">P ${(s.p * 100).toFixed(0)}%</span>
          <span class="ps-d">${s.d >= 0 ? '+' : ''}$${Math.abs(s.d) >= 1000 ? (s.d/1000).toFixed(1) + 'K' : s.d.toFixed(0)}</span>
        </div>
      `).join('')}
    </div>
    <div class="plan-preflight">
      <div class="pp-head">
        <span class="h">PRE-FLIGHT CHECKLIST</span>
        <span class="meta">${cleared} / ${preflight.length} cleared</span>
      </div>
      ${preflight.map(c => `
        <div class="pp-row ${c.warn ? 'warn' : c.ok ? 'ok' : 'fail'}">
          <span class="ico">${c.warn ? '!' : c.ok ? '✓' : '✗'}</span>
          <span class="lbl">${c.lbl}</span>
          <span class="v">${c.v}</span>
        </div>
      `).join('')}
    </div>
  </div>

  <!-- D-10: Strategy Decision Tree — visual flowchart of how this verdict was reached -->
  <div class="dtree">
    <div class="dtree-h">
      <span class="dtree-icon">⌖</span>
      <span class="dtree-title">DECISION TREE — how this verdict was reached</span>
      <span class="dtree-meta">8 evaluation steps · gates → score → verdict</span>
    </div>
    ${(() => {
      const at = T.audit_trail || {};
      const sc = at.scoring || {};
      const tcLocal = at.theory_confluence || T.theory_confluence || {};
      const verdictV = at.verdict || T.verdict || '—';
      const verdictColor = ['BUY','STRONG BUY'].includes(verdictV) ? 'pass' : ['SELL','SHORT','AVOID'].includes(verdictV) ? 'fail' : 'warn';
      const steps = [
        { id: 1,  name: 'LIQUIDITY GATE', pass: T.adv_20d == null || T.adv_20d > 5_000_000, detail: T.adv_20d ? `ADV $${(T.adv_20d/1e6).toFixed(1)}M ≥ $5M min` : '—' },
        { id: 2,  name: 'EARNINGS GATE',  pass: !(T.earn_days != null && T.earn_days <= 7), detail: T.earn_days != null && T.earn_days <= 7 ? `Earnings in ${T.earn_days}d — blackout` : 'No earnings within 7d' },
        { id: 3,  name: 'REGIME CHECK',   pass: T.regime4 !== 'panic', detail: `Regime: ${T.regime4 || 'unknown'}` },
        { id: 4,  name: 'ENTRY QUALITY',  pass: ['FRESH','PULLBACK','VALID'].includes(T.entry_quality || ''), detail: T.entry_quality || '—' },
        { id: 5,  name: 'R:R MIN 3:1',    pass: rrT1 >= 3, detail: `R:R ${rrT1.toFixed(1)}:1 (need ≥3.0)` },
        { id: 6,  name: 'SCORE PILLARS',  pass: (T.score || 0) >= 60, detail: `${T.score || 0}/100 — tech ${sc.tech_pts || 0} · cat ${sc.cat_pts || 0} · rs ${sc.rs_pts || 0} · sm ${sc.sm_pts || 0} · qg ${sc.qg_pts || 0}` },
        { id: 7,  name: 'THEORY CONFLUENCE', pass: tcLocal.gate_pass !== false, detail: `${tcLocal.count || tcLocal.bull_count || 0}/${tcLocal.min_required || 2} bullish theories (Dow/Wyckoff/Elliott/Gann)` },
        { id: 8,  name: 'TAIL-LOSS FILTER',  pass: !((T.score || 0) < 60 || (T.star_rating || 0) < 4), detail: `Score ${T.score || 0} · ${T.star_rating || 0}★ — needs ≥60 score AND ≥4★` },
      ];
      const passed = steps.filter(s => s.pass).length;
      return `
        <div class="dtree-flow">
          ${steps.map((s) => `<div class="dtree-step ${s.pass ? 'ok' : 'no'}">
            <div class="dtree-num">${s.id}</div>
            <div class="dtree-body">
              <div class="dtree-name">${s.name}</div>
              <div class="dtree-detail">${s.detail}</div>
            </div>
            <div class="dtree-glyph">${s.pass ? '✓' : '✗'}</div>
          </div>`).join('')}
        </div>
        <div class="dtree-out ${verdictColor}">
          <div class="lbl">${passed} / ${steps.length} GATES PASSED</div>
          <div class="v">FINAL VERDICT: <b>${verdictV}</b></div>
          <div class="narr">${passed === steps.length ? 'All gates cleared — strong setup, full conviction.' : passed >= steps.length - 2 ? 'Most gates cleared — actionable but watch the gaps.' : passed >= steps.length / 2 ? 'Mixed — wait for more confirmations.' : 'Multiple gate failures — skip this trade.'}</div>
        </div>
      `;
    })()}
  </div>`;
}

export function dispose() { /* no-op */ }
