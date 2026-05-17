// tabs/performance/actions.js — Auto-generated action items from the user's
// signal log + setup attribution. Surfaces concrete next-step recommendations
// based on Wilson CI / profit factor / win rate / sample size thresholds.
// Returns an HTML string consumed by the entry orchestrator.

export function buildActions(perf, attr, total, closed, wr) {
  const actions = [];

  if (closed === 0) {
    actions.push({
      icon: '⏱', color: 'var(--paper-3)',
      text: `${total} signals open · awaiting 5-10 day evaluation window before closures populate.`,
    });
  }
  if (closed >= 30 && wr >= 55) {
    actions.push({
      icon: '✓', color: 'var(--green)',
      text: `Win rate ${wr.toFixed(1)}% across ${closed} trades — system has edge. Consider scaling up size on T1 picks.`,
    });
  }
  if (closed >= 30 && wr < 45) {
    actions.push({
      icon: '⚠', color: 'var(--red)',
      text: `Win rate ${wr.toFixed(1)}% — below break-even. Stop trading, audit setup mix, run forward-walk validation.`,
    });
  }

  Object.entries(attr).forEach(([name, s]) => {
    if ((s.trades || 0) >= 10 && (s.win_rate || 0) >= 65 && (s.profit_factor || 0) >= 1.8) {
      actions.push({
        icon: '↑', color: 'var(--green)',
        text: `${name}: ${s.win_rate}% WR / ${s.profit_factor} PF — increase allocation, this is your best setup.`,
      });
    }
    if ((s.trades || 0) >= 10 && (s.profit_factor || 0) < 0.9) {
      actions.push({
        icon: '↓', color: 'var(--red)',
        text: `${name}: ${s.profit_factor} PF — losing money. Drop this setup family until you can fix it.`,
      });
    }
    if ((s.trades || 0) < 10) {
      actions.push({
        icon: '○', color: 'var(--paper-3)',
        text: `${name}: only ${s.trades} trades — too small to judge. Need 30+ for statistical confidence.`,
      });
    }
  });

  if (perf.by_strategy && Object.keys(perf.by_strategy).length > 0) {
    const top = Object.entries(perf.by_strategy).sort((a, b) => b[1] - a[1])[0];
    if (top && top[1] >= total * 0.4) {
      actions.push({
        icon: 'ⓘ', color: 'var(--accent)',
        text: `${top[0]} dominates with ${top[1]}/${total} signals (${(top[1]/total*100).toFixed(0)}%) — concentration risk. Diversify setup mix.`,
      });
    }
  }

  return `
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
}
