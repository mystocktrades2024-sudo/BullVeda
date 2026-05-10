// tabs/accuracy/accuracy.js — extracted from dashboard.html (renderAccuracy 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const acc = DATA.accuracy || {};
  if (acc.error) {
    $('accuracyBody').innerHTML = `<div class="ac-empty"><div class="ico">⚠</div><div class="h">Accuracy data unavailable</div><div class="sub">${acc.error}</div></div>`;
    return;
  }
  const closed = acc.n_closed || 0;
  if (closed === 0) {
    $('accuracyBody').innerHTML = `<div class="ac-empty"><div class="ico">○</div><div class="h">No closed trades yet</div><div class="sub">Accuracy framework needs CLOSED signals in <code>signal_log.json</code> to validate the scoring engine. Currently 0 closed of ${acc.n_total || 0} total.</div></div>`;
    return;
  }

  const k = acc.kupiec_pof || {};
  const c = acc.christoffersen || {};
  const b = acc.basel || {};
  const s = acc.summary || {};
  const byBand  = acc.by_score_band || {};
  const byStrat = acc.by_strategy || {};
  const byDir   = acc.by_direction || {};

  // ── Hero — Basel zone is the headline ──
  const zone = b.zone || 'INSUFFICIENT_DATA';
  const zoneCls = zone === 'GREEN' ? 'green' : zone === 'YELLOW' ? 'yellow' : zone === 'RED' ? 'red' : 'dim';
  const zoneIcon = zone === 'GREEN' ? '✓' : zone === 'YELLOW' ? '⚠' : zone === 'RED' ? '✗' : '○';

  // ── Score band rows sorted by band ──
  const bandOrder = ['90-100', '80-89', '70-79', '60-69', '<60', 'no_score'];
  const bands = bandOrder.filter(b => byBand[b]).map(b => [b, byBand[b]]);

  // Top strategies by sample size (n)
  const strats = Object.entries(byStrat).filter(([_,m]) => m.n > 0).sort((a,b) => b[1].n - a[1].n).slice(0, 12);

  $('accuracyBody').innerHTML = `
    <!-- HERO: Basel zone -->
    <div class="ac-hero ${zoneCls}">
      <div class="ac-hero-icon">${zoneIcon}</div>
      <div class="ac-hero-mid">
        <div class="ac-hero-tag">BASEL III TRAFFIC-LIGHT · LAST ${b.window || 250} TRADES</div>
        <div class="ac-hero-h">Model in <span class="em">${zone}</span> zone</div>
        <div class="ac-hero-narr">${b.recommendation || '—'} <b>${b.n_exceptions ?? '—'}</b> exceptions of <b>${b.n_trades ?? '—'}</b> trades · expected <b>${b.expected ?? '—'}</b> at VaR(95%) · actual rate <b>${b.exception_rate ?? '—'}%</b>.</div>
      </div>
      <div class="ac-hero-r">
        <div class="v">${b.exception_rate ?? '—'}%</div>
        <div class="lbl">Exception Rate</div>
      </div>
    </div>

    <!-- 4 STAT TILES -->
    <div class="ac-tiles">
      <div class="ac-tile">
        <div class="lbl">Closed Trades</div>
        <div class="v">${closed}</div>
        <div class="sub">of ${acc.n_total} total</div>
      </div>
      <div class="ac-tile pass">
        <div class="lbl">Win Rate</div>
        <div class="v ${s.win_rate >= 60 ? 'pass' : s.win_rate >= 50 ? 'warn' : 'fail'}">${s.win_rate ?? '—'}%</div>
        <div class="sub">${s.n} trades</div>
      </div>
      <div class="ac-tile info">
        <div class="lbl">Avg R-multiple</div>
        <div class="v ${s.avg_r >= 1 ? 'pass' : s.avg_r >= 0 ? 'warn' : 'fail'}">${s.avg_r >= 0 ? '+' : ''}${s.avg_r ?? '—'}R</div>
        <div class="sub">+${s.avg_win}R wins · ${s.avg_loss}R losses</div>
      </div>
      <div class="ac-tile warn">
        <div class="lbl">Profit Factor</div>
        <div class="v ${s.pf >= 2 ? 'pass' : s.pf >= 1.5 ? 'warn' : 'fail'}">${s.pf ?? '—'}</div>
        <div class="sub">expectancy ${s.expectancy >= 0 ? '+' : ''}${s.expectancy}R/trade</div>
      </div>
    </div>

    <!-- A1 + A2: Statistical tests -->
    <div class="ac-grid-2">
      <div class="ac-card">
        <div class="ac-card-h"><span class="ico">∫</span>A1 · KUPIEC POF TEST<span class="badge ${k.accepted ? 'pass' : 'fail'}">${k.verdict || '—'}</span></div>
        <div class="ac-card-narr">Tests if actual exception rate matches the expected ${k.expected_rate ?? 5}%. <b>Reject H₀ if p-value < 0.05</b>.</div>
        <div class="ac-row"><span class="l">Trades observed</span><span class="r">${k.n_trades ?? '—'}</span></div>
        <div class="ac-row"><span class="l">Exceptions (≤${k.threshold_r ?? -1}R)</span><span class="r ${k.actual_rate > k.expected_rate * 1.5 ? 'fail' : ''}">${k.n_exceptions ?? '—'}</span></div>
        <div class="ac-row"><span class="l">Actual rate</span><span class="r ${k.actual_rate > k.expected_rate * 1.5 ? 'fail' : 'pass'}">${k.actual_rate ?? '—'}%</span></div>
        <div class="ac-row"><span class="l">Expected rate</span><span class="r">${k.expected_rate ?? '—'}%</span></div>
        <div class="ac-row"><span class="l">LR statistic</span><span class="r">${k.lr_stat ?? '—'}</span></div>
        <div class="ac-row"><span class="l">p-value</span><span class="r ${k.p_value < 0.05 ? 'fail' : 'pass'}">${k.p_value ?? '—'}</span></div>
        <div class="ac-row" style="border-bottom:none"><span class="l">Verdict</span><span class="r ${k.accepted ? 'pass' : 'fail'}">${k.verdict || '—'}</span></div>
        ${!k.accepted ? `<div class="ac-callout fail">Model is rejecting more / fewer exceptions than expected. Either: (a) stops are mis-sized for this regime, (b) score is over-confident in losing trades, or (c) the -1R VaR proxy is too aggressive for swing horizons.</div>` : ''}
      </div>

      <div class="ac-card">
        <div class="ac-card-h"><span class="ico">⤳</span>A2 · CHRISTOFFERSEN TEST<span class="badge ${c.accepted ? 'pass' : 'fail'}">${c.clustering_verdict || '—'}</span></div>
        <div class="ac-card-narr">Tests if exceptions are <b>independent</b> (random over time) or <b>clustered</b> (model failure mode).</div>
        ${c.transitions ? `
        <div class="ac-row"><span class="l">No-exc → No-exc</span><span class="r mono">${c.transitions['00']}</span></div>
        <div class="ac-row"><span class="l">No-exc → Exc</span><span class="r mono">${c.transitions['01']}</span></div>
        <div class="ac-row"><span class="l">Exc → No-exc</span><span class="r mono">${c.transitions['10']}</span></div>
        <div class="ac-row"><span class="l">Exc → Exc</span><span class="r mono ${c.transitions['11'] > c.transitions['00'] * 0.05 ? 'warn' : ''}">${c.transitions['11']}</span></div>
        <div class="ac-row"><span class="l">P(exc | no-exc)</span><span class="r">${(c.pi_after_no_exc * 100).toFixed(2)}%</span></div>
        <div class="ac-row"><span class="l">P(exc | exc)</span><span class="r ${c.pi_after_exc > c.pi_after_no_exc * 1.5 ? 'fail' : 'pass'}">${(c.pi_after_exc * 100).toFixed(2)}%</span></div>
        <div class="ac-row"><span class="l">LR statistic</span><span class="r">${c.lr_stat}</span></div>
        <div class="ac-row"><span class="l">p-value</span><span class="r ${c.p_value < 0.05 ? 'fail' : 'pass'}">${c.p_value}</span></div>
        <div class="ac-row" style="border-bottom:none"><span class="l">Clustering</span><span class="r ${c.accepted ? 'pass' : 'fail'}">${c.clustering_verdict}</span></div>
        ` : `<div class="ac-callout">${c.verdict || 'Insufficient data'}</div>`}
      </div>
    </div>

    <!-- A3: Per-score-band -->
    <div class="ac-card">
      <div class="ac-card-h"><span class="ico">📊</span>A3 · ACCURACY BY SCORE BAND<span class="badge info">score predicts WR</span></div>
      <div class="ac-card-narr">Higher score should = higher win rate. Validates the 5-pillar scoring is actually predictive.</div>
      <table class="ac-tbl">
        <thead><tr><th>Score Band</th><th class="r">Trades</th><th class="r">Win Rate</th><th class="r">Avg R</th><th class="r">Profit Factor</th><th class="r">Avg Win</th><th class="r">Avg Loss</th></tr></thead>
        <tbody>
        ${bands.map(([band, m]) => `
          <tr>
            <td><b>${band}</b></td>
            <td class="r mono">${m.n}</td>
            <td class="r mono ${m.win_rate >= 70 ? 'pass' : m.win_rate >= 55 ? 'warn' : 'fail'}">${m.win_rate}%</td>
            <td class="r mono ${m.avg_r >= 1 ? 'pass' : m.avg_r >= 0 ? 'warn' : 'fail'}">${m.avg_r >= 0 ? '+' : ''}${m.avg_r}R</td>
            <td class="r mono ${m.pf >= 2 ? 'pass' : m.pf >= 1.5 ? 'warn' : 'fail'}">${m.pf}</td>
            <td class="r mono pass">+${m.avg_win}R</td>
            <td class="r mono fail">${m.avg_loss}R</td>
          </tr>`).join('')}
        </tbody>
      </table>
      ${(() => {
        // Verify score predictiveness: WR should be monotone-increasing with band
        const wrs = bandOrder.filter(b => byBand[b] && b !== 'no_score' && b !== '<60').map(b => [b, byBand[b].win_rate]);
        if (wrs.length < 3) return '';
        const ok = wrs.every((cur, i, arr) => i === arr.length - 1 || cur[1] >= arr[i+1][1] - 5);
        return ok
          ? `<div class="ac-callout pass">✓ Score is monotone-predictive — higher band → higher WR. Scoring engine is calibrated.</div>`
          : `<div class="ac-callout warn">⚠ Score band WR is non-monotone — lower bands beating higher bands. Investigate scoring weights.</div>`;
      })()}
    </div>

    <!-- A3: Per-strategy -->
    <div class="ac-card">
      <div class="ac-card-h"><span class="ico">🎯</span>A3 · ACCURACY BY STRATEGY<span class="badge info">${strats.length} strategies w/ ≥1 closed trade</span></div>
      <div class="ac-card-narr">Per-strategy edge — sample size matters. n &lt; 20 = thin / unreliable.</div>
      <table class="ac-tbl">
        <thead><tr><th>Strategy</th><th class="r">n</th><th class="r">Win Rate</th><th class="r">Avg R</th><th class="r">PF</th><th class="r">Expectancy</th><th>Sample</th></tr></thead>
        <tbody>
        ${strats.map(([name, m]) => `
          <tr>
            <td><b>${name}</b></td>
            <td class="r mono">${m.n}</td>
            <td class="r mono ${m.win_rate >= 70 ? 'pass' : m.win_rate >= 55 ? 'warn' : 'fail'}">${m.win_rate}%</td>
            <td class="r mono ${m.avg_r >= 1 ? 'pass' : m.avg_r >= 0 ? 'warn' : 'fail'}">${m.avg_r >= 0 ? '+' : ''}${m.avg_r}R</td>
            <td class="r mono ${m.pf >= 2 ? 'pass' : m.pf >= 1.5 ? 'warn' : 'fail'}">${m.pf || '—'}</td>
            <td class="r mono ${m.expectancy >= 0.5 ? 'pass' : m.expectancy >= 0 ? 'warn' : 'fail'}">${m.expectancy >= 0 ? '+' : ''}${m.expectancy}R</td>
            <td><span class="ac-pill ${m.n >= 50 ? 'pass' : m.n >= 20 ? 'warn' : 'fail'}">${m.n >= 50 ? 'reliable' : m.n >= 20 ? 'moderate' : 'thin'}</span></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <!-- A3: Per-direction -->
    ${Object.keys(byDir).length > 1 ? `
    <div class="ac-card">
      <div class="ac-card-h"><span class="ico">↕</span>A3 · ACCURACY BY DIRECTION</div>
      <table class="ac-tbl">
        <thead><tr><th>Direction</th><th class="r">n</th><th class="r">Win Rate</th><th class="r">Avg R</th><th class="r">PF</th></tr></thead>
        <tbody>
        ${Object.entries(byDir).map(([dir, m]) => `
          <tr>
            <td><b>${dir}</b></td>
            <td class="r mono">${m.n}</td>
            <td class="r mono ${m.win_rate >= 60 ? 'pass' : m.win_rate >= 50 ? 'warn' : 'fail'}">${m.win_rate}%</td>
            <td class="r mono ${m.avg_r >= 1 ? 'pass' : 'warn'}">${m.avg_r >= 0 ? '+' : ''}${m.avg_r}R</td>
            <td class="r mono">${m.pf || '—'}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : ''}

    <!-- Footer with computed timestamp + methodology link -->
    <div class="ac-foot">
      <b>Methodology:</b> VaR(95%) proxy = -1R (stop hit). Kupiec POF = likelihood-ratio test on exception rate · χ² 1df critical = 3.841. Christoffersen = LR test on transition independence · same critical. Basel III = 250-trade exception count. <b>Source:</b> <code>accuracy_framework.py</code> · runs each scan via <code>build_data._compute_accuracy_safe()</code>. <b>Computed:</b> ${acc._computed_at?.split('T')[0] || '—'}.
    </div>`;
}

export function dispose() { /* no-op */ }
