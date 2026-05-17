// tabs/reference/reference.js — extracted from dashboard.html (renderReference 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  if (typeof TIPS === 'undefined') { $('referenceBody').innerHTML = '<div class="stub">Load tooltips.js first</div>'; return; }
  const cats = [
    ['Verdict & Stage',    ['verdict','stg','stage','buy','watch','short','avoid']],
    ['Score & Pillars',    ['score','bap','tech','fund','smc','news','sentiment']],
    ['Price & Volume',     ['px','price','now','%d','rvol','volume','atr','atr%','beta']],
    ['Momentum',           ['rsi','macd','stochrsi','mfi','obv','cmf','adx']],
    ['Moving Averages',    ['ema','sma','vwap','rs','rs rank']],
    ['Trade Plan',         ['entry','ent','entry zone','stop','t1','t2','r:r','rr','earn','earnings','size','alloc']],
    ['Fundamentals',       ['rev','rev growth','margin','net margin','roe','roa','pe','p/e','peg','pt','analyst','consensus','upside']],
    ['Smart Money',        ['insider','insider buys','insider sells','short interest','iv rank','p/c ratio']],
    ['Patterns & Methods', ['vcp','pullback','breakout','squeeze','52wk','fresh','extended']],
    ['Elliott & Wyckoff',  ['wave','w0','w1','w2','w3','w4','w5','fibonacci','fib','wyckoff','sc','ar','creek','spring','phase a','phase b','phase c','phase d','phase e']],
    ['Monte Carlo',        ['mu','μ','sigma','σ','sharpe','p(profit)','var','5% var','ev','expected value','p10','p50','p90','gbm','monte carlo']],
    ['Market & Regime',    ['regime','breadth','distribution','vix']],
    ['Portfolio',          ['equity','cash','unrealized','realized','long','mfe','mae']],
  ];
  $('referenceBody').innerHTML = cats.map(([cat, keys]) => {
    const entries = keys.map(k => [k, TIPS[k]]).filter(([,v]) => v);
    if (!entries.length) return '';
    return `<div class="card" style="margin-bottom:14px">
      <div class="card-h">${cat} <span class="meta">${entries.length} terms</span></div>
      ${entries.map(([k, v]) => `
        <div style="display:grid;grid-template-columns:130px 1fr;gap:14px;padding:9px 0;border-bottom:1px dashed var(--rule);align-items:start">
          <span style="font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-0)">${k}</span>
          <span style="font-size:11.5px;color:var(--ink-2);line-height:1.5;white-space:pre-wrap">${v}</span>
        </div>`).join('')}
    </div>`;
  }).join('');
}

export function dispose() { /* no-op */ }
