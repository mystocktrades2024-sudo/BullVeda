// tabs/performance/performance.js — Performance / Trade Journal tab.
// Extracted from dashboard.html:7408-7775 (2026-05-09).
// _wilsonCI helper is inlined here (was only used by this renderer).

import { getData, $ } from '../../core/shared.js';

function _wilsonCI(wins, n) {
  if (n === 0) return { lo: 0, hi: 0 };
  const z = 1.96, p = wins / n;
  const denom = 1 + z*z/n;
  const center = (p + z*z/(2*n)) / denom;
  const margin = z * Math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom;
  return { lo: Math.max(0, center - margin), hi: Math.min(1, center + margin) };
}

export function render() {
  const DATA = getData();
  const perf = DATA.performance || {};
  const total = perf.total || 0;
  const closed = perf.closed || 0;
  const wr = perf.win_rate;
  const wins = perf.wins || 0;
  const losses = perf.losses || 0;
  const attr = perf.setup_attribution || {};
  const scoreBuckets = perf.by_score_bucket || {};
  const trail = perf.audit_trail || [];

  const _journalEl = document.getElementById('journalBody');
  const _journalMeta = document.getElementById('journalMeta');
  if (_journalEl) {
    const closedTrades = ((DATA.portfolio || {}).closed || []);
    if (closedTrades.length === 0) {
      if (_journalMeta) _journalMeta.textContent = '0 closed trades';
      _journalEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--paper-3);font-size:12px">No closed trades yet — journal entries will populate as positions close.</div>';
    } else {
      const bySetup = {};
      closedTrades.forEach(t => {
        const k = t.setup_type || t.setup || 'unspecified';
        if (!bySetup[k]) bySetup[k] = { trades: [], wins: 0, losses: 0, totalPnl: 0, totalR: 0, n: 0 };
        bySetup[k].trades.push(t);
        bySetup[k].n++;
        const pnl = t.pnl_dollars || t.pnl || 0;
        bySetup[k].totalPnl += pnl;
        if (pnl > 0) bySetup[k].wins++; else bySetup[k].losses++;
        if (t.r_multiple != null) bySetup[k].totalR += t.r_multiple;
      });
      const groups = Object.entries(bySetup).sort((a, b) => b[1].n - a[1].n);
      const totalPnl = closedTrades.reduce((s, t) => s + (t.pnl_dollars || t.pnl || 0), 0);
      const totalWins = closedTrades.filter(t => (t.pnl_dollars || t.pnl || 0) > 0).length;
      const overallWR = closedTrades.length ? Math.round(totalWins / closedTrades.length * 100) : 0;
      if (_journalMeta) _journalMeta.textContent = `${closedTrades.length} closed · ${overallWR}% WR · ${totalPnl >= 0 ? '+' : '−'}$${Math.abs(totalPnl).toFixed(0)} total`;

      _journalEl.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
          <th style="text-align:left;padding:8px 12px">Setup</th>
          <th style="text-align:right;padding:8px 12px">N</th>
          <th style="text-align:right;padding:8px 12px">WR</th>
          <th style="text-align:right;padding:8px 12px">Avg R</th>
          <th style="text-align:right;padding:8px 12px">$ Total</th>
          <th style="text-align:left;padding:8px 12px">Recent tickers</th>
        </tr></thead><tbody>
        ${groups.map(([k, g]) => {
          const wrPct = Math.round(g.wins / g.n * 100);
          const avgR = g.totalR / g.n;
          const recent = g.trades.slice(-5).map(t => t.ticker).reverse().join(' · ');
          return `<tr style="border-bottom:1px solid var(--line)">
            <td style="padding:8px 12px;font-weight:700">${k}</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono)">${g.n}</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${wrPct >= 60 ? 'var(--green)' : wrPct >= 50 ? 'var(--warn)' : 'var(--red)'};font-weight:700">${wrPct}%</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${avgR >= 1 ? 'var(--green)' : avgR >= 0 ? 'var(--warn)' : 'var(--red)'};font-weight:700">${avgR >= 0 ? '+' : ''}${avgR.toFixed(2)}R</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${g.totalPnl >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:700">${g.totalPnl >= 0 ? '+$' : '−$'}${Math.abs(g.totalPnl).toFixed(0)}</td>
            <td style="padding:8px 12px;color:var(--ink-2);font-size:11px">${recent || '—'}</td>
          </tr>`;
        }).join('')}
        </tbody></table>
        <div style="padding:14px 16px;border-top:1px dashed var(--rule);font-size:11px;color:var(--ink-2);line-height:1.55">
          <b style="color:var(--ink-0)">How to use:</b> Each row aggregates all closed trades by setup family. Look for setups with WR ≥ 60% AND avg R ≥ 1.0 → keep taking. Setups with WR < 50% or avg R < 0 → skip or investigate why they're failing. Sample size matters: groups with N &lt; 10 are anecdotal.
        </div>`;
    }
  }

  const NOTIONAL = (typeof window !== 'undefined' && window.PERF_NOTIONAL) || 10000;
  let pnlOpen = 0, pnlOpenCount = 0, pnlClosed = 0, pnlClosedCount = 0;
  let bestPnl = null, worstPnl = null;
  trail.forEach(s => {
    const pct = s.pct_now;
    if (pct == null) return;
    const dollarPnl = (pct / 100) * NOTIONAL;
    if (s.status && s.status !== 'OPEN') {
      pnlClosed += dollarPnl;
      pnlClosedCount++;
    } else {
      pnlOpen += dollarPnl;
      pnlOpenCount++;
    }
    if (!bestPnl || dollarPnl > bestPnl.pnl) bestPnl = { ...s, pnl: dollarPnl };
    if (!worstPnl || dollarPnl < worstPnl.pnl) worstPnl = { ...s, pnl: dollarPnl };
  });
  const pnlTotal = pnlOpen + pnlClosed;

  const strategyPnl = {};
  trail.forEach(s => {
    const pct = s.pct_now;
    if (pct == null) return;
    const strat = s.strategy || 'Unknown';
    if (!strategyPnl[strat]) strategyPnl[strat] = { count: 0, totalPct: 0, totalPnl: 0, wins: 0, losses: 0 };
    strategyPnl[strat].count++;
    strategyPnl[strat].totalPct += pct;
    strategyPnl[strat].totalPnl += (pct / 100) * NOTIONAL;
    if (pct > 0) strategyPnl[strat].wins++;
    else if (pct < 0) strategyPnl[strat].losses++;
  });

  $('perfMeta').textContent = `${total} signals · ${perf.open || 0} open · ${closed} closed · @ $${(NOTIONAL/1000).toFixed(0)}K notional`;

  let verdictLabel, verdictColor, verdictAction, verdictIcon;
  if (closed < 30) {
    verdictLabel = 'AWAITING DATA';
    verdictColor = '#a3aebf';
    verdictAction = `Need ${30 - closed} more closed trades for statistical confidence (currently ${closed} closed of ${total} logged)`;
    verdictIcon = '⏱';
  } else if (wr >= 55 && (perf.mfe_avg / Math.abs(perf.mae_avg || 1)) >= 1.5) {
    verdictLabel = 'STRONG EDGE';
    verdictColor = 'var(--green)';
    verdictAction = 'KEEP TRADING — your edge is real and statistically significant';
    verdictIcon = '⬆';
  } else if (wr >= 45) {
    verdictLabel = 'MARGINAL EDGE';
    verdictColor = 'var(--accent)';
    verdictAction = 'TRADE WITH CAUTION — reduce size, focus on top setups only';
    verdictIcon = '◆';
  } else {
    verdictLabel = 'NO EDGE';
    verdictColor = 'var(--red)';
    verdictAction = 'STOP TRADING — review setup mix, drop losing strategies';
    verdictIcon = '⬇';
  }

  const fmtPnl = (n) => (n >= 0 ? '+$' : '-$') + Math.abs(n).toLocaleString(undefined, {maximumFractionDigits: 0});
  const pnlColor = pnlTotal >= 0 ? 'var(--green)' : 'var(--red)';

  $('perfTiles').innerHTML = `
    <div style="grid-column: span 4; background: linear-gradient(135deg, color-mix(in oklch, ${verdictColor} 10%, var(--ink)) 0%, var(--ink) 60%); border: 1px solid ${verdictColor}; border-left: 4px solid ${verdictColor}; border-radius: 8px; padding: 18px 22px; margin-bottom: 8px;">
      <div style="display:flex; align-items:flex-start; gap:18px;">
        <div style="font-size:36px; color:${verdictColor}; line-height:1; font-weight:900;">${verdictIcon}</div>
        <div style="flex:1;">
          <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.18em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:4px;">System Edge</div>
          <div style="font-size:24px; font-weight:800; color:${verdictColor}; letter-spacing:-0.01em; line-height:1.1; margin-bottom:6px;">${verdictLabel}</div>
          <div style="display:flex; gap:18px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);"><b>${wr != null ? wr.toFixed(1) + '%' : '—'}</b> WR</span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);"><b>${wins}W</b> · <b>${losses}L</b></span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);">Avg R:R <b>${perf.rr_avg ? perf.rr_avg.toFixed(2) + '×' : '—'}</b></span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);">MFE <b style="color:var(--green)">${perf.mfe_avg != null ? '+' + perf.mfe_avg.toFixed(1) + '%' : '—'}</b> · MAE <b style="color:var(--red)">${perf.mae_avg != null ? perf.mae_avg.toFixed(1) + '%' : '—'}</b></span>
          </div>
          <div style="font-size:14px; color:var(--paper-2); line-height:1.5;">${verdictAction}</div>
        </div>
      </div>
    </div>
    <div style="grid-column: span 4; display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-top:4px;">
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid ${pnlColor}; border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Total P&amp;L (Live)</div>
        <div style="font-size:22px; font-weight:800; color:${pnlColor}; font-family:var(--mono);">${fmtPnl(pnlTotal)}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnlOpenCount + pnlClosedCount} signals @ $${(NOTIONAL/1000).toFixed(0)}K each</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--accent); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Open P&amp;L (Unrealized)</div>
        <div style="font-size:22px; font-weight:800; color:${pnlOpen >= 0 ? 'var(--green)' : 'var(--red)'}; font-family:var(--mono);">${fmtPnl(pnlOpen)}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnlOpenCount} open positions</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--green); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Best Trade</div>
        <div style="font-size:18px; font-weight:800; color:var(--green); font-family:var(--mono);">${bestPnl ? fmtPnl(bestPnl.pnl) : '—'}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${bestPnl ? bestPnl.ticker + ' · ' + bestPnl.pct_now.toFixed(1) + '%' : '—'}</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--red); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Worst Trade</div>
        <div style="font-size:18px; font-weight:800; color:var(--red); font-family:var(--mono);">${worstPnl ? fmtPnl(worstPnl.pnl) : '—'}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${worstPnl ? worstPnl.ticker + ' · ' + worstPnl.pct_now.toFixed(1) + '%' : '—'}</div>
      </div>
    </div>
  `;

  const families = Object.entries(attr).map(([name, s]) => ({
    name, ...s,
    edge: ((s.win_rate || 0) / 100) * (s.profit_factor || 0),
  }));

  let podiumHtml = '';
  if (families.length === 0 && perf.by_strategy) {
    const bystr = Object.entries(perf.by_strategy).map(([name, count]) => {
      const sp = strategyPnl[name] || { count: 0, totalPct: 0, totalPnl: 0, wins: 0, losses: 0 };
      return { name, count, ...sp };
    });
    bystr.sort((a, b) => b.totalPnl - a.totalPnl);
    podiumHtml = `
      <div style="background:var(--surf-card); border:1px solid var(--line); border-radius:8px; padding:18px 22px; margin-bottom:14px;">
        <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px;">
          <div>
            <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700;">Setup P&amp;L Ranking — Live</div>
            <div style="font-size:14px; color:var(--paper); margin-top:2px;">Strategies ordered by current $ P&amp;L · sourced from live signal trail</div>
          </div>
          <div style="font-family:var(--mono); font-size:12px; color:var(--paper-3);">${total} signals · @$${(NOTIONAL/1000).toFixed(0)}K each</div>
        </div>
        <div style="display:grid; grid-template-columns:24px 1fr 90px 60px 90px 70px 90px; gap:10px; padding:6px 0 8px; font-family:var(--mono); font-size:9.5px; letter-spacing:0.12em; color:var(--paper-3); text-transform:uppercase; font-weight:700; border-bottom:1px solid var(--line);">
          <span>#</span><span>Strategy</span><span style="text-align:right;">$ P&amp;L</span><span style="text-align:right;">Signals</span><span style="text-align:right;">Avg %</span><span style="text-align:right;">Win Rate</span><span></span>
        </div>
        ${bystr.slice(0, 10).map((s, i) => {
          const pnlColor = s.totalPnl >= 0 ? 'var(--green)' : 'var(--red)';
          const avgPct = s.count > 0 ? s.totalPct / s.count : 0;
          const closedSig = s.wins + s.losses;
          const winPct = closedSig > 0 ? (s.wins / closedSig * 100) : null;
          const wrColor = winPct == null ? 'var(--paper-3)' : winPct >= 55 ? 'var(--green)' : winPct >= 45 ? 'var(--accent)' : 'var(--red)';
          const barPct = Math.min(100, Math.abs(s.totalPnl) / Math.max(1, Math.abs(bystr[0].totalPnl)) * 100);
          return `
            <div style="display:grid; grid-template-columns:24px 1fr 90px 60px 90px 70px 90px; gap:10px; padding:9px 0; border-bottom:1px dashed var(--line); align-items:center; font-family:var(--mono); font-size:12px;">
              <span style="color:var(--paper-3); text-align:right;">${i+1}</span>
              <span style="color:var(--paper); font-weight:600;">${s.name}</span>
              <span style="text-align:right; color:${pnlColor}; font-weight:800; font-size:13px;">${fmtPnl(s.totalPnl)}</span>
              <span style="text-align:right; color:var(--paper);">${s.count}</span>
              <span style="text-align:right; color:${avgPct >= 0 ? 'var(--green)' : 'var(--red)'};">${avgPct >= 0 ? '+' : ''}${avgPct.toFixed(2)}%</span>
              <span style="text-align:right; color:${wrColor}; font-weight:700;">${winPct != null ? winPct.toFixed(0) + '%' : '—'}</span>
              <div style="background:var(--surf-elev); height:8px; border-radius:4px; overflow:hidden;">
                <div style="background:${pnlColor}; height:100%; width:${barPct}%;"></div>
              </div>
            </div>
          `;
        }).join('')}
        <div style="margin-top:10px; padding-top:8px; border-top:1px dashed var(--line); font-size:10.5px; color:var(--paper-3);">
          P&amp;L assumes <b style="color:var(--paper);">$${NOTIONAL.toLocaleString()}</b> notional per signal. Override with <code style="background:var(--ink); padding:1px 5px; border-radius:3px; font-family:var(--mono);">window.PERF_NOTIONAL = 5000</code> in console.
        </div>
      </div>`;
  } else {
    families.sort((a, b) => b.edge - a.edge);
    const winners = families.slice(0, 3);
    const losers = families.slice(3).filter(f => f.profit_factor < 1.0 || f.win_rate < 40);
    const rankColors = ['#FFD700', '#C0C0C0', '#CD7F32'];
    const rankLabels = ['🥇', '🥈', '🥉'];

    podiumHtml = `
      <div style="background:var(--surf-card); border:1px solid var(--line); border-radius:8px; padding:18px 22px; margin-bottom:14px;">
        <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px;">
          <div>
            <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700;">Winners Podium</div>
            <div style="font-size:14px; color:var(--paper); margin-top:2px;">Top 3 setup families by edge — keep trading these</div>
          </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(${winners.length}, 1fr); gap:12px;">
          ${winners.map((f, i) => {
            const wrPct = f.win_rate || 0;
            const pf = f.profit_factor || 0;
            const ci = _wilsonCI(f.wins || 0, f.trades || 1);
            const action = pf >= 1.5 ? 'KEEP TRADING' : pf >= 1.2 ? 'STRONG' : pf >= 1.0 ? 'OK' : 'WATCH';
            const actionColor = pf >= 1.5 ? 'var(--green)' : pf >= 1.0 ? 'var(--accent)' : 'var(--red)';
            return `
              <div style="background:var(--ink); border:1px solid ${rankColors[i]}; border-top:3px solid ${rankColors[i]}; border-radius:8px; padding:14px;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;">
                  <span style="font-size:24px;">${rankLabels[i]}</span>
                  <span style="font-family:var(--mono); font-size:10px; color:${actionColor}; font-weight:700; letter-spacing:0.1em;">${action}</span>
                </div>
                <div style="font-size:14px; font-weight:700; color:var(--paper); margin-bottom:8px;">${f.name}</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-family:var(--mono); font-size:11px;">
                  <div><span style="color:var(--paper-3);">WR</span><br><b style="color:var(--paper); font-size:14px;">${wrPct.toFixed(0)}%</b></div>
                  <div><span style="color:var(--paper-3);">PF</span><br><b style="color:var(--paper); font-size:14px;">${pf.toFixed(2)}</b></div>
                  <div><span style="color:var(--paper-3);">N</span><br><b style="color:var(--paper); font-size:14px;">${f.trades}</b></div>
                  <div><span style="color:var(--paper-3);">CI ±</span><br><b style="color:var(--paper); font-size:14px;">${((ci.hi - ci.lo) * 50).toFixed(0)}%</b></div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
        ${losers.length > 0 ? `
          <div style="margin-top:14px; padding-top:14px; border-top:1px dashed var(--line);">
            <div style="font-family:var(--mono); font-size:10.5px; letter-spacing:0.14em; color:var(--red); text-transform:uppercase; font-weight:700; margin-bottom:8px;">⚠ Losers — drop or reduce</div>
            ${losers.map(f => `
              <div style="display:flex; justify-content:space-between; padding:6px 0; font-family:var(--mono); font-size:12px;">
                <span style="color:var(--paper);">${f.name}</span>
                <span style="color:var(--red);">${(f.win_rate || 0).toFixed(0)}% WR · ${(f.profit_factor || 0).toFixed(2)} PF · N=${f.trades}</span>
              </div>
            `).join('')}
          </div>` : ''}
      </div>`;
  }

  const order = ['90+','80-89','70-79','60-69','<60'];
  const totalScored = Object.values(scoreBuckets).reduce((a,b) => a+b, 0) || 1;
  const calibrationHtml = `
    <div style="background:var(--surf-card); border:1px solid var(--line); border-radius:8px; padding:18px 22px; margin-bottom:14px;">
      <div style="margin-bottom:14px;">
        <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700;">Score Calibration</div>
        <div style="font-size:14px; color:var(--paper); margin-top:2px;">Signal distribution across conviction tiers — higher score should mean higher quality</div>
      </div>
      ${order.filter(k => scoreBuckets[k]).map(k => {
        const count = scoreBuckets[k];
        const pct = count / totalScored * 100;
        const barColor = k === '90+' ? 'var(--green)' : k === '80-89' ? 'var(--accent-2)' : k === '70-79' ? 'var(--accent)' : k === '60-69' ? 'var(--paper-3)' : 'var(--paper-4)';
        const tierLabel = k === '90+' ? 'T1 elite' : k === '80-89' ? 'T1' : k === '70-79' ? 'T2' : k === '60-69' ? 'T3 / WATCH' : 'below threshold';
        return `
          <div style="display:grid; grid-template-columns:80px 1fr 100px 60px; gap:14px; padding:9px 0; border-bottom:1px dashed var(--line); align-items:center;">
            <div>
              <div style="font-family:var(--mono); font-size:14px; font-weight:800; color:${barColor};">${k}</div>
              <div style="font-size:10px; color:var(--paper-3); letter-spacing:0.06em; text-transform:uppercase;">${tierLabel}</div>
            </div>
            <div style="background:var(--surf-elev); height:18px; border-radius:4px; overflow:hidden;">
              <div style="background:${barColor}; height:100%; width:${pct}%; transition:width 320ms;"></div>
            </div>
            <div style="font-family:var(--mono); font-size:14px; color:var(--paper); font-weight:700; text-align:right;">${count} signals</div>
            <div style="font-family:var(--mono); font-size:13px; color:var(--paper-3); text-align:right;">${pct.toFixed(1)}%</div>
          </div>
        `;
      }).join('')}
      <div style="margin-top:14px; padding-top:10px; border-top:1px dashed var(--line); font-size:11.5px; color:var(--paper-3); line-height:1.6;">
        <b style="color:var(--paper);">How to read:</b> If 90+ signals win at higher rates than 60-69 → conviction score is predictive. If they're flat → score is noise.
        ${closed >= 30 ? 'Your data is statistically meaningful (N≥30).' : 'Need 30+ closed trades to compute per-bucket win rates with confidence.'}
      </div>
    </div>`;

  const actions = [];
  if (closed === 0) {
    actions.push({ icon: '⏱', color: 'var(--paper-3)', text: `${total} signals open · awaiting 5-10 day evaluation window before closures populate.` });
  }
  if (closed >= 30 && wr >= 55) {
    actions.push({ icon: '✓', color: 'var(--green)', text: `Win rate ${wr.toFixed(1)}% across ${closed} trades — system has edge. Consider scaling up size on T1 picks.` });
  }
  if (closed >= 30 && wr < 45) {
    actions.push({ icon: '⚠', color: 'var(--red)', text: `Win rate ${wr.toFixed(1)}% — below break-even. Stop trading, audit setup mix, run forward-walk validation.` });
  }
  Object.entries(attr).forEach(([name, s]) => {
    if ((s.trades || 0) >= 10 && (s.win_rate || 0) >= 65 && (s.profit_factor || 0) >= 1.8) {
      actions.push({ icon: '↑', color: 'var(--green)', text: `${name}: ${s.win_rate}% WR / ${s.profit_factor} PF — increase allocation, this is your best setup.` });
    }
    if ((s.trades || 0) >= 10 && (s.profit_factor || 0) < 0.9) {
      actions.push({ icon: '↓', color: 'var(--red)', text: `${name}: ${s.profit_factor} PF — losing money. Drop this setup family until you can fix it.` });
    }
    if ((s.trades || 0) < 10) {
      actions.push({ icon: '○', color: 'var(--paper-3)', text: `${name}: only ${s.trades} trades — too small to judge. Need 30+ for statistical confidence.` });
    }
  });
  if (perf.by_strategy && Object.keys(perf.by_strategy).length > 0) {
    const top = Object.entries(perf.by_strategy).sort((a,b) => b[1] - a[1])[0];
    if (top && top[1] >= total * 0.4) {
      actions.push({ icon: 'ⓘ', color: 'var(--accent)', text: `${top[0]} dominates with ${top[1]}/${total} signals (${(top[1]/total*100).toFixed(0)}%) — concentration risk. Diversify setup mix.` });
    }
  }

  const actionsHtml = `
    <div style="background:var(--surf-card); border:1px solid var(--green); border-radius:8px; padding:18px 22px;">
      <div style="margin-bottom:12px;">
        <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--green); text-transform:uppercase; font-weight:700;">From Your Data — Action Items</div>
        <div style="font-size:13px; color:var(--paper-2); margin-top:2px;">Auto-generated from your signal log + attribution stats</div>
      </div>
      ${actions.length === 0 ? '<div style="padding:14px; color:var(--paper-3); font-size:13px; text-align:center;">No actionable signals yet — check back after first 30 closures.</div>' :
        actions.map(a => `
          <div style="display:flex; align-items:flex-start; gap:10px; padding:10px 0; border-bottom:1px dashed var(--line); font-size:13px; line-height:1.5; color:var(--paper);">
            <span style="color:${a.color}; font-size:16px; font-weight:800; min-width:18px;">${a.icon}</span>
            <span>${a.text}</span>
          </div>
        `).join('')}
    </div>`;

  const attribTarget = document.getElementById('perfAttribBody');
  if (attribTarget) {
    attribTarget.parentElement.parentElement.innerHTML = podiumHtml + calibrationHtml + actionsHtml;
  }
}

export function dispose() { /* no-op */ }
