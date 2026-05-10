// subtabs/insider/insider.js — Insider sub-tab thin orchestrator.
//
// Sub-modules:
//   aggregate.js — pure data transform: txs → totals, c-suite counts,
//                  verdict, narrative, horizon-impact. Plus title helpers.
//   view.js      — HTML builders: verdict banner + tiles + pattern card +
//                  horizon card + Form-4 table.
//
// Entry handles:
//   1. Loading state
//   2. /api/insider/<ticker>?days=90 fetch
//   3. Empty + error states
//   4. Aggregate → view assembly

import { aggregate } from './aggregate.js';
import { buildBody } from './view.js';

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export async function render() {
  const T = _T();
  if (!T) return;
  const body = document.getElementById('insiderBody');
  if (!body) return;

  body.innerHTML = '<div style="padding:30px;color:var(--ink-1);text-align:center">Loading insider transactions…</div>';

  try {
    const r = await fetch(`/api/insider/${T.ticker}?days=90`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d   = await r.json();
    const txs = d.transactions || [];

    if (txs.length === 0) {
      body.innerHTML = `
        <div class="ins-empty">
          <div class="ico">○</div>
          <div class="h">No Form 4 filings for ${T.ticker}</div>
          <div class="sub">No insider transactions reported in the last 90 days. Could mean: insiders in lockup, low public-float company, or simply quiet quarter.</div>
        </div>`;
      return;
    }

    const agg = aggregate(txs, T);
    body.innerHTML = buildBody(T, txs, agg);
  } catch (e) {
    body.innerHTML = `<div class="ins-empty"><div class="ico">⚠</div><div class="h">Could not load insider data</div><div class="sub">${e.message}</div></div>`;
  }
}

export function dispose() { /* no-op */ }
