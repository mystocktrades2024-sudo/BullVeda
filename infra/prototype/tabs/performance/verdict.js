// tabs/performance/verdict.js — System Edge verdict banner + 4 P&L tiles.
// Owns DOM region: #perfTiles + #perfMeta header text.
// Verdict thresholds (WR≥55 + MFE/MAE≥1.5 = STRONG · WR≥45 = MARGINAL · else NO EDGE)
// must stay in sync with decision_engine.py. See CLAUDE.md "Coherence note".

import { $ } from '../../core/shared.js';
import { fmtPnl } from './pnl.js';

export function renderVerdict(perf, pnl, notional, total, closed) {
  const wr     = perf.win_rate;
  const wins   = perf.wins   || 0;
  const losses = perf.losses || 0;

  $('perfMeta').textContent = `${total} signals · ${perf.open || 0} open · ${closed} closed · @ $${(notional/1000).toFixed(0)}K notional`;

  let label, color, action, icon;
  if (closed < 30) {
    label  = 'AWAITING DATA';
    color  = '#a3aebf';
    action = `Need ${30 - closed} more closed trades for statistical confidence (currently ${closed} closed of ${total} logged)`;
    icon   = '⏱';
  } else if (wr >= 55 && (perf.mfe_avg / Math.abs(perf.mae_avg || 1)) >= 1.5) {
    label  = 'STRONG EDGE';
    color  = 'var(--green)';
    action = 'KEEP TRADING — your edge is real and statistically significant';
    icon   = '⬆';
  } else if (wr >= 45) {
    label  = 'MARGINAL EDGE';
    color  = 'var(--accent)';
    action = 'TRADE WITH CAUTION — reduce size, focus on top setups only';
    icon   = '◆';
  } else {
    label  = 'NO EDGE';
    color  = 'var(--red)';
    action = 'STOP TRADING — review setup mix, drop losing strategies';
    icon   = '⬇';
  }

  const pnlColor = pnl.total >= 0 ? 'var(--green)' : 'var(--red)';

  $('perfTiles').innerHTML = `
    <div style="grid-column: span 4; background: linear-gradient(135deg, color-mix(in oklch, ${color} 10%, var(--ink)) 0%, var(--ink) 60%); border: 1px solid ${color}; border-left: 4px solid ${color}; border-radius: 8px; padding: 18px 22px; margin-bottom: 8px;">
      <div style="display:flex; align-items:flex-start; gap:18px;">
        <div style="font-size:36px; color:${color}; line-height:1; font-weight:900;">${icon}</div>
        <div style="flex:1;">
          <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.18em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:4px;">System Edge</div>
          <div style="font-size:24px; font-weight:800; color:${color}; letter-spacing:-0.01em; line-height:1.1; margin-bottom:6px;">${label}</div>
          <div style="display:flex; gap:18px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);"><b>${wr != null ? wr.toFixed(1) + '%' : '—'}</b> WR</span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);"><b>${wins}W</b> · <b>${losses}L</b></span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);">Avg R:R <b>${perf.rr_avg ? perf.rr_avg.toFixed(2) + '×' : '—'}</b></span>
            <span style="font-family:var(--mono); font-size:13px; color:var(--paper);">MFE <b style="color:var(--green)">${perf.mfe_avg != null ? '+' + perf.mfe_avg.toFixed(1) + '%' : '—'}</b> · MAE <b style="color:var(--red)">${perf.mae_avg != null ? perf.mae_avg.toFixed(1) + '%' : '—'}</b></span>
          </div>
          <div style="font-size:14px; color:var(--paper-2); line-height:1.5;">${action}</div>
        </div>
      </div>
    </div>
    <div style="grid-column: span 4; display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-top:4px;">
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid ${pnlColor}; border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Total P&amp;L (Live)</div>
        <div style="font-size:22px; font-weight:800; color:${pnlColor}; font-family:var(--mono);">${fmtPnl(pnl.total)}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnl.openCount + pnl.closedCount} signals @ $${(notional/1000).toFixed(0)}K each</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--accent); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Open P&amp;L (Unrealized)</div>
        <div style="font-size:22px; font-weight:800; color:${pnl.open >= 0 ? 'var(--green)' : 'var(--red)'}; font-family:var(--mono);">${fmtPnl(pnl.open)}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnl.openCount} open positions</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--green); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Best Trade</div>
        <div style="font-size:18px; font-weight:800; color:var(--green); font-family:var(--mono);">${pnl.best ? fmtPnl(pnl.best.pnl) : '—'}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnl.best ? pnl.best.ticker + ' · ' + pnl.best.pct_now.toFixed(1) + '%' : '—'}</div>
      </div>
      <div style="background:var(--surf-card); border:1px solid var(--line); border-left:3px solid var(--red); border-radius:8px; padding:14px 16px;">
        <div style="font-family:var(--mono); font-size:10px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Worst Trade</div>
        <div style="font-size:18px; font-weight:800; color:var(--red); font-family:var(--mono);">${pnl.worst ? fmtPnl(pnl.worst.pnl) : '—'}</div>
        <div style="font-size:10.5px; color:var(--paper-3); margin-top:2px;">${pnl.worst ? pnl.worst.ticker + ' · ' + pnl.worst.pct_now.toFixed(1) + '%' : '—'}</div>
      </div>
    </div>
  `;
}
