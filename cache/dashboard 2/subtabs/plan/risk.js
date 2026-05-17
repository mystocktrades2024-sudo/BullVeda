// subtabs/plan/risk.js — extracted from elite-detail.html (renderRisk 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const k = T.kelly_size || {};
  const tp = T.trade_plan || {};
  const acct = 250000;
  const riskPct = (k.risk_per_trade_pct != null) ? k.risk_per_trade_pct / 100 : 0.0075;
  const riskDollar = acct * riskPct;
  const riskPerSh = T.risk_per_share || k.risk_per_share || (T.entry_low - T.stop) || 1;
  const shares = k.shares != null ? k.shares : Math.max(1, Math.floor(riskDollar / riskPerSh));
  const notional = shares * (T.entry_low || T.price || 1);
  const allocPct = k.allocation_pct != null ? k.allocation_pct : (notional / acct * 100);
  const kellyPct = k.kelly_pct != null ? k.kelly_pct : (k.kelly_fraction != null ? k.kelly_fraction * 100 : null);
  const sizingMult = T.sizing_multiplier || k.sizing_multiplier || 1.0;
  const betaAdj = k.beta_adj_multiplier || tp.beta_adj_multiplier || 1.0;
  const beta = T.beta || k.beta;
  const winProb = k.win_prob_pct != null ? k.win_prob_pct : (k.win_prob != null ? k.win_prob * 100 : null);
  const avgWin = k.avg_win_R || k.avg_winner_R;
  const avgLoss = k.avg_loss_R || k.avg_loser_R || -1.0;
  const heatNow = 3.20, heatAfter = heatNow + (notional / acct) * 100 * 0.4;
  const heatCap = 6.0;
  const expectancy = (winProb && avgWin) ? (winProb/100*avgWin + (1-winProb/100)*(avgLoss||-1)) : null;
  const rawShares = Math.floor(riskDollar / riskPerSh);
  const conviction = T.score >= 80 ? 'T1' : T.score >= 70 ? 'T2' : 'T3';

  $('riskBody').innerHTML = `
    <!-- HERO TILES -->
    <div class="rsk-hero">
      <div class="rsk-hero-tile equity">
        <div class="lbl"><span class="ico">💼</span>Account Equity</div>
        <div class="v">$${(acct/1000).toFixed(0)}K</div>
        <div class="sub">paper @ Alpaca</div>
      </div>
      <div class="rsk-hero-tile shares">
        <div class="lbl"><span class="ico">📦</span>Suggested Shares</div>
        <div class="v">${shares}</div>
        <div class="sub">@ $${(T.entry_low || T.price || 0).toFixed(2)} entry</div>
      </div>
      <div class="rsk-hero-tile notional">
        <div class="lbl"><span class="ico">💰</span>Notional</div>
        <div class="v">$${notional >= 1000 ? (notional/1000).toFixed(1) + 'K' : notional.toFixed(0)}</div>
        <div class="sub">${allocPct.toFixed(2)}% of book</div>
      </div>
      <div class="rsk-hero-tile kelly">
        <div class="lbl"><span class="ico">🎯</span>Kelly Fraction</div>
        <div class="v">${kellyPct != null ? kellyPct.toFixed(1) + '%' : '—'}</div>
        <div class="sub">half-Kelly capped 25%</div>
      </div>
    </div>

    <!-- SIZING FLOW -->
    <div class="rsk-flow">
      <div class="rsk-flow-h"><span class="ico">🧮</span>SIZING DECOMPOSITION<span class="meta">how ${shares} shares was computed</span></div>
      <div class="rsk-flow-grid">
        <div class="rsk-flow-step input">
          <div class="lbl">Risk / share</div>
          <div class="v">$${riskPerSh.toFixed(2)}</div>
          <div class="formula">$${(T.entry_low||0).toFixed(2)} − $${(T.stop||0).toFixed(2)}</div>
        </div>
        <div class="rsk-flow-arrow">÷</div>
        <div class="rsk-flow-step input">
          <div class="lbl">Risk $</div>
          <div class="v">$${riskDollar.toFixed(0)}</div>
          <div class="formula">${(riskPct*100).toFixed(2)}% × $${(acct/1000).toFixed(0)}K</div>
        </div>
        <div class="rsk-flow-arrow">=</div>
        <div class="rsk-flow-step calc">
          <div class="lbl">Raw shares</div>
          <div class="v">${rawShares}</div>
          <div class="formula">$${riskDollar.toFixed(0)} ÷ $${riskPerSh.toFixed(2)}</div>
        </div>
        <div class="rsk-flow-arrow">×</div>
        <div class="rsk-flow-step adj">
          <div class="lbl">Conviction · ${conviction}</div>
          <div class="v">${sizingMult.toFixed(2)}×</div>
          <div class="formula">${conviction === 'T1' ? 'full conviction' : conviction === 'T2' ? 'moderate' : 'small'}</div>
        </div>
        <div class="rsk-flow-arrow">×</div>
        <div class="rsk-flow-step adj">
          <div class="lbl">Beta · β${beta ? beta.toFixed(2) : '—'}</div>
          <div class="v">${betaAdj.toFixed(2)}×</div>
          <div class="formula">${beta > 1.5 ? 'high vol → size down' : beta < 0.7 ? 'low vol → size up' : 'normal'}</div>
        </div>
        <div class="rsk-flow-arrow">=</div>
        <div class="rsk-flow-step final">
          <div class="lbl">Final shares</div>
          <div class="v">${shares} sh</div>
          <div class="formula">$${notional.toFixed(0)} notional</div>
        </div>
      </div>
    </div>

    <!-- KELLY INPUTS + PORTFOLIO HEAT (side-by-side) -->
    <div class="rsk-grid-2">
      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">🎲</span>KELLY INPUTS<span class="badge ${expectancy > 0 ? 'pass' : expectancy < 0 ? 'fail' : 'warn'}">${expectancy != null ? (expectancy >= 0 ? '+' : '') + expectancy.toFixed(2) + 'R EV' : 'NO DATA'}</span></div>
        <div class="tch-row"><span class="l">Win probability</span><span class="r ${winProb >= 55 ? 'pass' : winProb >= 45 ? 'warn' : winProb != null ? 'fail' : ''}">${winProb != null ? winProb.toFixed(1) + '%' : '—'}</span></div>
        <div class="tch-row"><span class="l">Avg winner</span><span class="r pass">${avgWin != null ? '+' + avgWin.toFixed(2) + 'R' : '—'}</span></div>
        <div class="tch-row"><span class="l">Avg loser</span><span class="r fail">${avgLoss != null ? avgLoss.toFixed(2) + 'R' : '—'}</span></div>
        <div class="tch-row"><span class="l">Expectancy</span><span class="r ${expectancy > 0.3 ? 'pass' : expectancy > 0 ? 'warn' : 'fail'}">${expectancy != null ? (expectancy >= 0 ? '+' : '') + expectancy.toFixed(2) + 'R' : '—'}</span></div>
        <div class="tch-row"><span class="l">Setup family</span><span class="r" style="font-family:inherit;font-weight:600">${T.setup_family || '—'}</span></div>
        <div class="tch-row" style="border-bottom:none"><span class="l" style="font-style:italic">Formula</span><span class="r" style="font-family:var(--mono);font-size:11px;color:var(--ink-1)">EV = WR×W − LR×|L|</span></div>
      </div>

      <div class="tch-card">
        <div class="tch-card-h"><span class="ico">🔥</span>PORTFOLIO HEAT<span class="badge ${heatAfter < heatCap*0.7 ? 'pass' : heatAfter < heatCap ? 'warn' : 'fail'}">${heatAfter.toFixed(2)}% / ${heatCap}%</span></div>
        <div class="rsk-heat-bar">
          <div class="rsk-heat-bar-h">Aggregate risk across all open positions</div>
          <div class="rsk-heat-track">
            <div class="rsk-heat-fill" style="width:${(heatAfter/heatCap*100).toFixed(0)}%"></div>
            <div class="rsk-heat-marker" style="left:${(heatNow/heatCap*100).toFixed(1)}%"><div class="lbl">Now ${heatNow.toFixed(1)}%</div></div>
            <div class="rsk-heat-marker" style="left:${(heatAfter/heatCap*100).toFixed(1)}%;background:var(--ink-0)"></div>
          </div>
          <div class="legend"><span>0%</span><span style="color:var(--fail);font-weight:700">CAP ${heatCap}%</span></div>
        </div>
        <div class="tch-row" style="margin-top:10px"><span class="l">Current heat</span><span class="r warn">${heatNow.toFixed(2)}%</span></div>
        <div class="tch-row"><span class="l">After this entry</span><span class="r ${heatAfter < heatCap*0.7 ? 'pass' : heatAfter < heatCap ? 'warn' : 'fail'}">+${(heatAfter-heatNow).toFixed(2)}% → ${heatAfter.toFixed(2)}%</span></div>
        <div class="tch-row" style="border-bottom:none"><span class="l">Hard cap</span><span class="r fail">${heatCap.toFixed(2)}%</span></div>
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }
