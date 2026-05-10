// tabs/performance/journal.js — Trade Journal aggregate (closed trades grouped
// by setup family). Owns DOM region: #journalBody + #journalMeta.
// Reads DATA.portfolio.closed[] (driven by portfolio_tracker.close_position()).

export function renderJournal(closedTrades) {
  const journalEl   = document.getElementById('journalBody');
  const journalMeta = document.getElementById('journalMeta');
  if (!journalEl) return;

  if (closedTrades.length === 0) {
    if (journalMeta) journalMeta.textContent = '0 closed trades';
    journalEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--paper-3);font-size:12px">No closed trades yet — journal entries will populate as positions close.</div>';
    return;
  }

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
  const groups   = Object.entries(bySetup).sort((a, b) => b[1].n - a[1].n);
  const totalPnl = closedTrades.reduce((s, t) => s + (t.pnl_dollars || t.pnl || 0), 0);
  const totalWins = closedTrades.filter(t => (t.pnl_dollars || t.pnl || 0) > 0).length;
  const overallWR = closedTrades.length ? Math.round(totalWins / closedTrades.length * 100) : 0;
  if (journalMeta) journalMeta.textContent = `${closedTrades.length} closed · ${overallWR}% WR · ${totalPnl >= 0 ? '+' : '−'}$${Math.abs(totalPnl).toFixed(0)} total`;

  journalEl.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
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
      const avgR  = g.totalR / g.n;
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
