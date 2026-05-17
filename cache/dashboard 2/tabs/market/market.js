// tabs/market/market.js — extracted from dashboard.html (renderMarket 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const r = DATA.regime || {};
  const br = DATA.market_breadth || {};
  const ms = DATA.macro_signals || {};
  const vix = typeof r.vix === 'object' ? r.vix.vix_current : r.vix || r.vix_current;
  const vixCls = vix < 16 ? 'ok' : vix < 22 ? 'warn' : 'bad';
  const breadthCls = (br.pct_above_50d || 0) >= 60 ? 'ok' : (br.pct_above_50d || 0) >= 40 ? 'warn' : 'bad';

  $('marketTiles').innerHTML = `
    <div class="stat-tile ${vixCls}"><div class="lbl">VIX</div><div class="v">${(vix || 0).toFixed(2)}</div><div class="sub">${vixCls === 'ok' ? 'low vol' : vixCls === 'warn' ? 'elevated' : 'panic zone'}</div></div>
    <div class="stat-tile ${breadthCls}"><div class="lbl">Breadth 50D</div><div class="v">${(br.pct_above_50d || 0).toFixed(1)}%</div><div class="sub">${br.label_50 || '—'}</div></div>
    <div class="stat-tile"><div class="lbl">Regime</div><div class="v" style="font-size:14px">${(r.regime4 || r.regime || '—').toUpperCase().replace(/_/g,' ')}</div><div class="sub">SPY ${r.above_50ema ? 'above' : 'below'} EMA50</div></div>
    <div class="stat-tile"><div class="lbl">Cycle</div><div class="v" style="font-size:14px">${(r.market_cycle || '—').toUpperCase()}</div><div class="sub">distribution: ${r.distribution_days ?? '—'}</div></div>
  `;

  $('breadthBody').innerHTML = `
    <div class="hc-row"><div>Above 50-day</div><div class="hc-bar"><div class="hc-bar-fill" style="width:${br.pct_above_50d || 0}%;background:${(br.pct_above_50d||0) >= 60 ? 'var(--green)' : 'var(--accent)'}"></div></div><div class="hc-pct">${(br.pct_above_50d||0).toFixed(1)}%</div><div style="font-size:10px;color:var(--ink-3);text-align:right">${br.above_50d}/${br.total}</div></div>
    <div class="hc-row"><div>Above 100-day</div><div class="hc-bar"><div class="hc-bar-fill" style="width:${br.pct_above_100d || 0}%;background:${(br.pct_above_100d||0) >= 60 ? 'var(--green)' : 'var(--accent)'}"></div></div><div class="hc-pct">${(br.pct_above_100d||0).toFixed(1)}%</div><div style="font-size:10px;color:var(--ink-3);text-align:right">${br.above_100d}/${br.total}</div></div>
    <div class="hc-row"><div>Above 200-day</div><div class="hc-bar"><div class="hc-bar-fill" style="width:${br.pct_above_200d || 0}%;background:${(br.pct_above_200d||0) >= 60 ? 'var(--green)' : 'var(--accent)'}"></div></div><div class="hc-pct">${(br.pct_above_200d||0).toFixed(1)}%</div><div style="font-size:10px;color:var(--ink-3);text-align:right">${br.above_200d}/${br.total}</div></div>
    <div class="hc-row" style="border:none;margin-top:10px"><div>New highs / lows</div><div></div><div class="hc-pct" style="color:var(--green)">${br.new_highs} / <span style="color:var(--red)">${br.new_lows}</span></div><div style="font-size:10px;color:var(--ink-3);text-align:right">ratio ${(br.hl_ratio || 0).toFixed(1)}</div></div>
  `;

  const macroEntries = Object.entries(ms).filter(([k,v]) => v != null && typeof v === 'object' && v.price != null);
  $('macroBody').innerHTML = `
    <table class="simple"><thead><tr><th>SIGNAL</th><th class="r">PRICE</th><th class="r">5D</th><th class="r">20D</th><th class="r">TREND</th></tr></thead><tbody>
    ${macroEntries.map(([k,v]) => `
      <tr>
        <td><span class="sym">${k.toUpperCase()}</span></td>
        <td class="r">${v.price?.toFixed(2)}</td>
        <td class="r ${chgClass2(v.chg5d)}">${fmt(v.chg5d, 2)}%</td>
        <td class="r ${chgClass2(v.chg20d)}">${fmt(v.chg20d, 2)}%</td>
        <td class="r" style="font-size:11px;color:var(--ink-2)">${v.trend || '—'}</td>
      </tr>
    `).join('')}
    <tr style="border-top:1px solid var(--rule-2)"><td colspan="5" style="padding-top:12px"><b>Risk signal:</b> <span style="color:${ms.risk_signal === 'risk_on' ? 'var(--green)' : ms.risk_signal === 'risk_off' ? 'var(--red)' : 'var(--accent)'};font-weight:700">${(ms.risk_signal || 'neutral').toUpperCase().replace(/_/g,' ')}</span></td></tr>
    </tbody></table>
  `;

  // EODHD Economic Events — real upcoming US macro calendar
  const events = DATA.economic_events || [];
  const evContainer = document.getElementById('economicEvents');
  if (evContainer) {
    if (!events.length) {
      evContainer.innerHTML = `<div style="padding:18px;color:var(--ink-3);font-size:12px">No upcoming events in the next 14 days.</div>`;
    } else {
      const importanceCls = (type) => {
        const high = ['Federal', 'Non-Farm', 'Interest Rate', 'CPI', 'GDP', 'FOMC'];
        return high.some(h => (type||'').includes(h)) ? 'var(--red)' : 'var(--accent)';
      };
      evContainer.innerHTML = events.slice(0, 10).map(e => `
        <div class="hc-row" style="grid-template-columns:90px 1fr 60px;padding:8px 0;border-bottom:1px dashed var(--rule)">
          <div style="font-size:11px;color:var(--ink-3)">${(e.date||'').slice(0,10)}</div>
          <div style="font-size:12.5px"><b>${e.type || '—'}</b><span style="font-size:10.5px;color:var(--ink-3);margin-left:8px">${e.period || ''}</span>
            ${e.previous != null ? `<div style="font-size:10px;color:var(--ink-3);margin-top:2px">prev: ${e.previous}</div>` : ''}
          </div>
          <div style="width:8px;height:8px;border-radius:50%;background:${importanceCls(e.type)};margin-top:6px;flex-shrink:0"></div>
        </div>`).join('');
    }
  }
}

export function dispose() { /* no-op */ }
