// tabs/performance/podium.js — Setup Family Podium (top-3 by edge) when
// setup_attribution is populated, OR fallback "Setup P&L Ranking — Live"
// (open-position $-PnL ordering) when only by_strategy is available.
// Returns an HTML string consumed by the entry orchestrator.

import { wilsonCI } from './wilson.js';
import { fmtPnl }   from './pnl.js';

export function buildPodium(perf, attr, byStrategy, total, notional) {
  const families = Object.entries(attr).map(([name, s]) => ({
    name, ...s,
    edge: ((s.win_rate || 0) / 100) * (s.profit_factor || 0),
  }));

  if (families.length === 0 && perf.by_strategy) {
    return _buildStrategyRanking(perf, byStrategy, total, notional);
  }
  return _buildFamilyPodium(families);
}

function _buildStrategyRanking(perf, byStrategy, total, notional) {
  const bystr = Object.entries(perf.by_strategy).map(([name, count]) => {
    const sp = byStrategy[name] || { count: 0, totalPct: 0, totalPnl: 0, wins: 0, losses: 0 };
    return { name, count, ...sp };
  });
  bystr.sort((a, b) => b.totalPnl - a.totalPnl);

  return `
    <div style="background:var(--surf-card); border:1px solid var(--line); border-radius:8px; padding:18px 22px; margin-bottom:14px;">
      <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px;">
        <div>
          <div style="font-family:var(--mono); font-size:11px; letter-spacing:0.16em; color:var(--paper-3); text-transform:uppercase; font-weight:700;">Setup P&amp;L Ranking — Live</div>
          <div style="font-size:14px; color:var(--paper); margin-top:2px;">Strategies ordered by current $ P&amp;L · sourced from live signal trail</div>
        </div>
        <div style="font-family:var(--mono); font-size:12px; color:var(--paper-3);">${total} signals · @$${(notional/1000).toFixed(0)}K each</div>
      </div>
      <div style="display:grid; grid-template-columns:24px 1fr 90px 60px 90px 70px 90px; gap:10px; padding:6px 0 8px; font-family:var(--mono); font-size:9.5px; letter-spacing:0.12em; color:var(--paper-3); text-transform:uppercase; font-weight:700; border-bottom:1px solid var(--line);">
        <span>#</span><span>Strategy</span><span style="text-align:right;">$ P&amp;L</span><span style="text-align:right;">Signals</span><span style="text-align:right;">Avg %</span><span style="text-align:right;">Win Rate</span><span></span>
      </div>
      ${bystr.slice(0, 10).map((s, i) => {
        const pnlColor = s.totalPnl >= 0 ? 'var(--green)' : 'var(--red)';
        const avgPct   = s.count > 0 ? s.totalPct / s.count : 0;
        const closedSig = s.wins + s.losses;
        const winPct  = closedSig > 0 ? (s.wins / closedSig * 100) : null;
        const wrColor = winPct == null ? 'var(--paper-3)' : winPct >= 55 ? 'var(--green)' : winPct >= 45 ? 'var(--accent)' : 'var(--red)';
        const barPct  = Math.min(100, Math.abs(s.totalPnl) / Math.max(1, Math.abs(bystr[0].totalPnl)) * 100);
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
        P&amp;L assumes <b style="color:var(--paper);">$${notional.toLocaleString()}</b> notional per signal. Override with <code style="background:var(--ink); padding:1px 5px; border-radius:3px; font-family:var(--mono);">window.PERF_NOTIONAL = 5000</code> in console.
      </div>
    </div>`;
}

function _buildFamilyPodium(families) {
  families.sort((a, b) => b.edge - a.edge);
  const winners = families.slice(0, 3);
  const losers  = families.slice(3).filter(f => f.profit_factor < 1.0 || f.win_rate < 40);
  const rankColors = ['#FFD700', '#C0C0C0', '#CD7F32'];
  const rankLabels = ['🥇', '🥈', '🥉'];

  return `
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
          const pf    = f.profit_factor || 0;
          const ci    = wilsonCI(f.wins || 0, f.trades || 1);
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
