// tabs/risklab/risklab.js — Risk Lab tab.
// Extracted from dashboard.html:5238-5365 (2026-05-09).
// Self-contained — only DATA reads, no helper deps.

import { getData } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const dcc     = DATA.dcc_garch || {};
  const cop     = DATA.tail_copula || {};
  const cvar    = DATA.cvar_portfolio || {};
  const meta    = document.getElementById('risklabMeta');
  if (meta) meta.textContent = `${(dcc.tickers || []).length} tickers · DCC ν=${cop.nu || '—'} · CVaR ${cvar.cvar_pct ?? '—'}%`;

  const cvarBody = document.getElementById('cvarBody');
  const cvarMeta = document.getElementById('cvarMeta');
  if (cvarBody) {
    if (cvar.error || cvar.status !== 'optimal') {
      cvarBody.innerHTML = `<div style="padding:24px;text-align:center;color:var(--paper-3);font-size:12px">${cvar.error ? 'CVaR optimizer error: ' + cvar.error : 'Solver status: ' + (cvar.status || 'unknown')}</div>`;
    } else {
      const holdings = cvar.holdings || [];
      if (cvarMeta) cvarMeta.textContent = `${holdings.length} positions · gross ${cvar.gross_exposure_pct}% · CVaR ${cvar.cvar_pct}%`;
      cvarBody.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0;padding:16px 18px;border-bottom:1px solid var(--rule)">
          <div><div style="font-size:10px;letter-spacing:0.16em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:5px">E[Return]</div><div style="font-family:var(--mono);font-size:22px;font-weight:800;color:${cvar.expected_return_pct >= 0 ? 'var(--green)' : 'var(--red)'}">${cvar.expected_return_pct >= 0 ? '+' : ''}${cvar.expected_return_pct}%</div></div>
          <div><div style="font-size:10px;letter-spacing:0.16em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:5px">VaR-95</div><div style="font-family:var(--mono);font-size:22px;font-weight:800;color:var(--warn)">${cvar.var_pct >= 0 ? '+' : ''}${cvar.var_pct}%</div></div>
          <div><div style="font-size:10px;letter-spacing:0.16em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:5px">CVaR-97.5</div><div style="font-family:var(--mono);font-size:22px;font-weight:800;color:var(--red)">${cvar.cvar_pct >= 0 ? '+' : ''}${cvar.cvar_pct}%</div></div>
          <div><div style="font-size:10px;letter-spacing:0.16em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:5px">Gross Exposure</div><div style="font-family:var(--mono);font-size:22px;font-weight:800;color:var(--ink-0)">${cvar.gross_exposure_pct}%</div></div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="background:var(--ink-3);color:var(--paper-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">
            <th style="text-align:left;padding:8px 12px">#</th>
            <th style="text-align:left;padding:8px 12px">Ticker</th>
            <th style="text-align:left;padding:8px 12px">Sector</th>
            <th style="text-align:right;padding:8px 12px">Weight</th>
            <th style="text-align:right;padding:8px 12px">E[R] (per asset)</th>
            <th style="text-align:left;padding:8px 12px">Allocation Bar</th>
          </tr></thead><tbody>
          ${holdings.map((h, i) => `<tr style="border-bottom:1px solid var(--line);cursor:pointer" onclick="window.setDetailTicker && window.setDetailTicker('${h.ticker}')">
            <td style="padding:8px 12px;font-family:var(--mono);color:var(--ink-2)">${i + 1}</td>
            <td style="padding:8px 12px;font-weight:700">${h.ticker}</td>
            <td style="padding:8px 12px;color:var(--ink-2)">${h.sector || '—'}</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono);font-weight:800;color:var(--ink-0)">${h.weight_pct}%</td>
            <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:${h.expected_return_pct >= 0 ? 'var(--green)' : 'var(--red)'}">${h.expected_return_pct >= 0 ? '+' : ''}${h.expected_return_pct}%</td>
            <td style="padding:8px 12px"><div style="height:14px;width:${Math.min(100, h.weight_pct * 5)}%;background:linear-gradient(90deg,color-mix(in oklch,var(--green) 60%,transparent),var(--green));border-radius:3px"></div></td>
          </tr>`).join('')}
          </tbody>
        </table>
        <div style="padding:11px 16px;border-top:1px dashed var(--rule);font-size:11px;color:var(--ink-2);line-height:1.55"><b style="color:var(--ink-0)">Methodology:</b> Rockafellar-Uryasev LP. Maximizes E[Return] subject to: CVaR-95 ≤ ${cvar.cvar_pct?.toFixed?.(1) ?? '8'}% budget · gross ≤ 80% · max position 10% · max sector 30%. Scenarios from bootstrapped 250-day return history × 63d horizon.</div>`;
    }
  }

  const dccBody = document.getElementById('dccBody');
  const dccMeta = document.getElementById('dccMeta');
  if (dccBody) {
    if (dcc.error || !dcc.R_t) {
      dccBody.innerHTML = `<div style="padding:24px;text-align:center;color:var(--paper-3);font-size:12px">${dcc.error || 'No DCC data — need ≥2 BUY tickers with 60+ days history'}</div>`;
    } else {
      const tickers = dcc.tickers || [];
      const R = dcc.R_t || [];
      const persistenceLabel = dcc.persistence > 0.95 ? 'highly persistent (slow decay)' : dcc.persistence > 0.85 ? 'moderate' : 'fast-decay';
      const spikeAlert = dcc.corr_spike > 0.05 ? '⚠ spike vs static' : '— stable';
      if (dccMeta) dccMeta.textContent = `α=${dcc.alpha} β=${dcc.beta} (persistence ${dcc.persistence})`;
      dccBody.innerHTML = `
        <div style="padding:14px 16px;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:1fr 1fr;gap:18px">
          <div>
            <div style="font-size:10px;letter-spacing:0.14em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:4px">Avg Correlation Now</div>
            <div style="font-family:var(--mono);font-size:18px;font-weight:800;color:${dcc.avg_corr_now > 0.7 ? 'var(--red)' : dcc.avg_corr_now > 0.5 ? 'var(--warn)' : 'var(--green)'}">${dcc.avg_corr_now}</div>
            <div style="font-size:10px;color:var(--ink-3);margin-top:2px">vs static <span style="color:var(--ink-1);font-family:var(--mono)">${dcc.avg_corr_static}</span> ${spikeAlert}</div>
          </div>
          <div>
            <div style="font-size:10px;letter-spacing:0.14em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:4px">Most Correlated Pair</div>
            <div style="font-family:var(--mono);font-size:14px;font-weight:700;color:var(--ink-0)">${(dcc.max_corr_pair || ['—','—',0]).slice(0,2).join(' / ')}</div>
            <div style="font-family:var(--mono);font-size:11px;color:${(dcc.max_corr_pair||[null,null,0])[2] > 0.8 ? 'var(--red)' : 'var(--warn)'};margin-top:2px">ρ = ${(dcc.max_corr_pair || ['','',0])[2]}</div>
          </div>
        </div>
        <div style="overflow-x:auto;padding:12px 14px">
          <table style="border-collapse:collapse;font-size:10.5px;font-family:var(--mono)">
            <thead><tr><th></th>${tickers.map(t => `<th style="padding:4px 6px;color:var(--ink-2);font-weight:700">${t}</th>`).join('')}</tr></thead>
            <tbody>
            ${tickers.map((t, i) => `<tr>
              <td style="padding:4px 8px;color:var(--ink-2);font-weight:700">${t}</td>
              ${R[i].map((v, j) => {
                const cls = i === j ? 'var(--ink-3)' : Math.abs(v) > 0.7 ? 'var(--red)' : Math.abs(v) > 0.5 ? 'var(--warn)' : Math.abs(v) > 0.3 ? 'var(--accent)' : 'var(--green)';
                const bg = i === j ? 'transparent' : 'color-mix(in oklch, ' + cls + ' ' + Math.round(Math.abs(v) * 28) + '%, transparent)';
                return `<td style="padding:4px 6px;text-align:center;color:${cls};background:${bg};font-weight:600">${v.toFixed(2)}</td>`;
              }).join('')}
            </tr>`).join('')}
            </tbody>
          </table>
        </div>
        <div style="padding:11px 16px;border-top:1px dashed var(--rule);font-size:11px;color:var(--ink-2);line-height:1.55"><b style="color:var(--ink-0)">DCC-GARCH:</b> Engle (2002) Dynamic Conditional Correlation. α (news shock) = ${dcc.alpha} · β (persistence) = ${dcc.beta} → ${persistenceLabel}. Updates daily. Spike vs static = correlation regime change → reduce stacked exposure when spike > 0.05.</div>`;
    }
  }

  const cBody = document.getElementById('copulaBody');
  const cMeta = document.getElementById('copulaMeta');
  if (cBody) {
    if (cop.error || cop.nu == null) {
      cBody.innerHTML = `<div style="padding:24px;text-align:center;color:var(--paper-3);font-size:12px">${cop.error || 'No tail dependence data'}</div>`;
    } else {
      const nu = cop.nu;
      const nuColor = nu <= 5 ? 'var(--red)' : nu <= 8 ? 'var(--warn)' : nu <= 15 ? 'var(--accent)' : 'var(--green)';
      const topPairs = cop.max_tail_dep_pairs || [];
      if (cMeta) cMeta.textContent = `ν = ${nu} · ${cop.tail_regime || ''}`;
      cBody.innerHTML = `
        <div style="padding:14px 16px;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:1fr 1fr;gap:18px">
          <div>
            <div style="font-size:10px;letter-spacing:0.14em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:4px">Degrees of Freedom (ν)</div>
            <div style="font-family:var(--mono);font-size:22px;font-weight:800;color:${nuColor}">${nu}</div>
            <div style="font-size:10px;color:var(--ink-3);margin-top:2px">low ν = more tail-dep · high ν ≈ Gaussian</div>
          </div>
          <div>
            <div style="font-size:10px;letter-spacing:0.14em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:4px">Avg Tail Dependence</div>
            <div style="font-family:var(--mono);font-size:22px;font-weight:800;color:${cop.avg_tail_dep > 0.3 ? 'var(--red)' : cop.avg_tail_dep > 0.15 ? 'var(--warn)' : 'var(--green)'}">${cop.avg_tail_dep}</div>
            <div style="font-size:10px;color:var(--ink-3);margin-top:2px">λ_L ∈ [0,1]: probability of joint crash</div>
          </div>
        </div>
        <div style="padding:12px 16px">
          <div style="font-size:10px;letter-spacing:0.14em;color:var(--ink-2);text-transform:uppercase;font-weight:700;margin-bottom:8px">Top Tail-Dependent Pairs</div>
          ${topPairs.slice(0, 6).map(p => {
            const cls = p[2] > 0.3 ? 'var(--red)' : p[2] > 0.15 ? 'var(--warn)' : 'var(--ink-1)';
            return `<div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px dashed var(--rule);font-size:12px">
              <span style="font-family:var(--mono);font-weight:700">${p[0]} · ${p[1]}</span>
              <span style="font-family:var(--mono);font-weight:800;color:${cls}">λ_L = ${p[2]}</span>
            </div>`;
          }).join('')}
        </div>
        <div style="padding:11px 16px;border-top:1px dashed var(--rule);font-size:11px;color:var(--ink-2);line-height:1.55"><b style="color:var(--ink-0)">Tail regime:</b> ${cop.tail_regime || ''}. <b style="color:var(--ink-0)">When ν drops</b> (typically below 8), tail dependence rises — pairs that look uncorrelated in calm markets crash together in stress. Reduce stacked exposure to high-λ_L pairs during regime shifts.</div>`;
    }
  }
}

export function dispose() { /* no-op */ }
