// tabs/performance/pnl.js — Live P&L computation from audit_trail.
// Pure data transform: walks every signal in audit_trail, multiplies pct_now by
// notional, separates open vs closed, tracks best/worst, aggregates by strategy.
// No DOM. Returns an object the verdict / podium renderers consume.

export function computePnL(trail, notional) {
  let pnlOpen = 0, pnlOpenCount = 0, pnlClosed = 0, pnlClosedCount = 0;
  let bestPnl = null, worstPnl = null;
  const byStrategy = {};

  trail.forEach(s => {
    const pct = s.pct_now;
    if (pct == null) return;
    const dollarPnl = (pct / 100) * notional;
    if (s.status && s.status !== 'OPEN') {
      pnlClosed += dollarPnl;
      pnlClosedCount++;
    } else {
      pnlOpen += dollarPnl;
      pnlOpenCount++;
    }
    if (!bestPnl || dollarPnl > bestPnl.pnl)  bestPnl  = { ...s, pnl: dollarPnl };
    if (!worstPnl || dollarPnl < worstPnl.pnl) worstPnl = { ...s, pnl: dollarPnl };

    const strat = s.strategy || 'Unknown';
    if (!byStrategy[strat]) byStrategy[strat] = { count: 0, totalPct: 0, totalPnl: 0, wins: 0, losses: 0 };
    byStrategy[strat].count++;
    byStrategy[strat].totalPct += pct;
    byStrategy[strat].totalPnl += dollarPnl;
    if (pct > 0)      byStrategy[strat].wins++;
    else if (pct < 0) byStrategy[strat].losses++;
  });

  return {
    open:        pnlOpen,
    openCount:   pnlOpenCount,
    closed:      pnlClosed,
    closedCount: pnlClosedCount,
    total:       pnlOpen + pnlClosed,
    best:        bestPnl,
    worst:       worstPnl,
    byStrategy,
  };
}

export function fmtPnl(n) {
  return (n >= 0 ? '+$' : '-$') + Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}
