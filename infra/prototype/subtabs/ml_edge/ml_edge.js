// subtabs/ml_edge/ml_edge.js — ML Edge sub-tab thin orchestrator.
//
// Sub-modules (risk-redesign aesthetic, scoped under .rk-scope):
//   hero.js   — Breadcrumb + .rk-hero (banner + cone + 3 gauges + conviction matrix + foot ribbon)
//   heads.js  — §1 3-Head Decomposition (split-3 chart cards)
//   cone.js   — §3 Drilldown (dir tiles + skew + quantile + per-horizon | cone | level-hit ladder)
//   levels.js — §4 SHAP attributions + reconciliation note + footer
//
// Data flow:
//   ml_edge_predictions.json (sibling to data.json) is fetched once and cached
//   on window.__mlEdgeCache. Per-ticker payload is read by symbol. No bundle
//   patching required.
//
// Empty-state contract (mirrors options.js fallback thesis):
//   1. cache miss entirely  → predictions file not generated (no daily inference run)
//   2. ticker absent from cache → not in the 449-row scan pool
//   3. payload present with verdict NEUTRAL → model has no edge, surface honestly

import { buildHero }   from './hero.js';
import { buildHeads }  from './heads.js';
import { buildDrilldown } from './cone.js';
import { buildShapAndRecon } from './levels.js';
import { RK_STYLES }   from './rk_styles.js';

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

// Absolute /v2/ path — survives whichever mount kairos/elite-detail is loaded from.
// The catch-all /v2/{path:path} route in server.py serves all files under infra/prototype/.
const PRED_URL = '/v2/ml_edge_predictions.json';

async function _loadPredictions() {
  // Reuse cache ONLY if the previous fetch succeeded. A cached _meta.error
  // means a prior load failed; re-fetch on the next render call so a freshly
  // deployed fix surfaces without requiring a hard refresh.
  if (window.__mlEdgeCache && !(window.__mlEdgeCache._meta || {}).error) {
    return window.__mlEdgeCache;
  }
  try {
    const r = await fetch(PRED_URL, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    window.__mlEdgeCache = j;
    return j;
  } catch (e) {
    window.__mlEdgeCache = { _meta: { error: String(e) }, predictions: {} };
    return window.__mlEdgeCache;
  }
}

function _ensureStyles() {
  if (document.getElementById('ml-edge-rk-styles')) return;
  const s = document.createElement('style');
  s.id = 'ml-edge-rk-styles';
  s.textContent = RK_STYLES;
  document.head.appendChild(s);
}

function _renderEmpty(target, msg) {
  target.innerHTML = `
    <div class="rk-scope">
      <div class="rk-section" style="border-left:4px solid var(--ink-3);">
        <div class="rk-section-head">
          <div class="rk-section-title"><span class="num">!</span>ML Edge · No prediction</div>
        </div>
        <div class="rk-section-body" style="font-size:12px; color:var(--ink-1); line-height:1.6;">
          ${msg}
        </div>
      </div>
    </div>`;
}

export async function render() {
  const T = _T();
  if (!T) return;
  const target = document.getElementById('mlEdgeBody');
  if (!target) return;

  _ensureStyles();

  const sym = (T.ticker || T.symbol || '').toUpperCase();
  if (!sym) { _renderEmpty(target, 'Ticker symbol not available on detail bundle.'); return; }

  // loading state
  target.innerHTML = `<div class="rk-scope" style="padding:20px;color:var(--ink-3);font-family:var(--mono);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;">Loading ML predictions…</div>`;

  const all = await _loadPredictions();
  if (all._meta && all._meta.error) {
    _renderEmpty(target,
      `Predictions file not loadable (<span style="font-family:var(--mono)">${all._meta.error}</span>). Run <code style="font-family:var(--mono);background:var(--bg-3);padding:1px 5px;border-radius:2px;color:var(--copper)">python3 -m ml.run_ml_edge</code> to generate it.`);
    return;
  }

  // predictions JSON is mode-keyed: predictions[mode][ticker] = payload.
  // Resolve order: T._mode hint → swing → position → invest → flat fallback.
  const preds = all.predictions || {};
  const modeHint = (T._mode || T.mode || '').toLowerCase();
  const modeOrder = [modeHint, 'swing', 'position', 'invest'].filter(m => m && preds[m]);
  let payload = null;
  let resolvedMode = null;
  for (const m of modeOrder) {
    const candidate = (preds[m] || {})[sym];
    if (candidate && !candidate.error) { payload = candidate; resolvedMode = m; break; }
  }
  // Legacy flat fallback (older predictions files)
  if (!payload && preds[sym]) { payload = preds[sym]; resolvedMode = 'flat'; }

  if (!payload || payload.error) {
    const why = payload && payload.error
      ? `inference failed: ${payload.error}`
      : `${sym} was not in the last scan's analysis pool (${(all._meta||{}).n_tickers||'?'} tickers scored).`;
    _renderEmpty(target, why);
    return;
  }

  const ctx = {
    T, sym,
    payload,
    mode:   resolvedMode,
    meta:   all._meta || {},
    model:  (all._meta && all._meta.model) || payload.model_meta || {},
  };

  target.innerHTML = `
    <div class="rk-scope">
      ${buildHero(ctx)}
      ${buildHeads(ctx)}
      ${buildDrilldown(ctx)}
      ${buildShapAndRecon(ctx)}
    </div>`;
}

export function dispose() { /* no-op */ }
