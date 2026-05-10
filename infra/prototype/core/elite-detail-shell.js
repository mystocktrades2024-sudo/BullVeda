// core/elite-detail-shell.js — registry-driven sub-tab module loader for
// the per-ticker detail page (elite-detail.html).
//
// Strategy: same as core/shell.js but for the per-ticker page's sub-tab
// renderers. Loads each module from /api/capability-registry's sub_tabs
// entries (and their .extras list). After load, sets window.renderXxx =
// module.render — overrides the inline function declarations from
// elite-detail.html's classic <script> block.
//
// Inline bodies in elite-detail.html are NOT deleted by this iteration;
// they remain as safety fallback if a module fails to load.
// (CapStudio sub-tab wiring 2026-05-09)

console.log('[detail-shell] CapStudio sub-tab loader booting…');
performance.mark('detail-shell-loader-start');

// Metrics container — inspect at runtime: window.__detailMetrics
window.__detailMetrics = window.__detailMetrics || { moduleLoadMs: {}, renderMs: {} };

const _moduleCache = {};
let REGISTRY = null;

// Map module FILE → window function name to override.
// File naming: subtabs/<sub_id>/<file>.js → renderXxx
// (see scripts/extract_elite_detail_renderers when re-running.)
const FILE_TO_WINDOW_FN = {
  'subtabs/overview/overview.js':              'renderEliteOverview',
  'subtabs/overview/earnings_banner.js':       'renderEarningsBanner',
  'subtabs/overview/head.js':                  'renderHead',
  'subtabs/overview/verdict.js':               'renderVerdict',
  'subtabs/overview/scorecard.js':             'renderScorecard',
  'subtabs/thesis/thesis.js':                  'renderThesisDetail',
  'subtabs/research/research.js':              'renderResearchDetail',
  'subtabs/plan/plan.js':                      'renderPlan',
  'subtabs/plan/risk.js':                      'renderRisk',
  'subtabs/plan/backtest.js':                  'renderBacktest',
  'subtabs/technicals/chart.js':               'renderChart',
  'subtabs/technicals/mtf.js':                 'renderMTF',
  'subtabs/models/horizons.js':                'renderHorizons',
  'subtabs/models/elliott.js':                 'renderElliott',
  'subtabs/models/multimethod.js':             'renderMultiMethod',
  'subtabs/tv/tv.js':                          'renderTV',
  'subtabs/smc/smc.js':                        'renderSMC',
  'subtabs/fundamentals/fundamentals.js':      'renderFund',
  'subtabs/fundamentals/intel.js':             'renderIntel',
  'subtabs/sentiment/sentiment.js':            'renderSentimentTab',
  'subtabs/options/options.js':                'renderOptionsTab',
  'subtabs/news/news.js':                      'renderNewsTab',
  'subtabs/insider/insider.js':                'renderInsider',
  'subtabs/institutional/institutional.js':    'renderInstitutional',
  'subtabs/ruleengine/rule_engine.js':         'renderRuleEngine',
};

async function _loadAndOverride(modulePath) {
  if (_moduleCache[modulePath]) return _moduleCache[modulePath];
  const v = window.__moduleVersion || '1';
  const url = `../${modulePath}?v=${v}`;
  _moduleCache[modulePath] = (async () => {
    const t0 = performance.now();
    try {
      const mod = await import(url);
      const ms = +(performance.now() - t0).toFixed(1);
      window.__detailMetrics.moduleLoadMs[modulePath] = ms;
      const fnName = FILE_TO_WINDOW_FN[modulePath];
      if (!fnName) {
        console.warn(`[detail-shell] no window function name mapped for ${modulePath}`);
        return null;
      }
      if (typeof mod.render !== 'function') {
        console.warn(`[detail-shell] ${modulePath} has no exported render()`);
        return null;
      }
      // Override window's existing function declaration. Future calls to
      // `renderXxx()` from anywhere in elite-detail.html resolve to this.
      window[fnName] = mod.render;
      return mod;
    } catch (err) {
      console.error(`[detail-shell] failed to import '${url}':`, err);
      return null;
    }
  })();
  return _moduleCache[modulePath];
}

(async function _boot() {
  // Steps 1+2 combined (PERF-1b 2026-05-09): single /api/v2-bootstrap call.
  // HTML head has <link rel="preload"> so browser warms this response early.
  try {
    const r = await fetch('/api/v2-bootstrap', {credentials: 'include'});
    if (r.ok) {
      const j = await r.json();
      window.__moduleVersion = j.version || String(Date.now());
      REGISTRY = j.registry;
      console.log(`[detail-shell] bootstrap: v=${window.__moduleVersion}, ${Object.keys(REGISTRY.sub_tabs || {}).length} sub-tabs (1 RTT)`);
    } else {
      throw new Error(`bootstrap ${r.status}`);
    }
  } catch (e) {
    console.warn('[detail-shell] bootstrap failed, falling back:', e.message);
    try {
      const r = await fetch('./_v', {cache: 'no-store', credentials: 'include'});
      window.__moduleVersion = r.ok ? (await r.text()).trim() : String(Date.now());
    } catch (_) { window.__moduleVersion = String(Date.now()); }
    try {
      const r = await fetch('/api/capability-registry', {credentials: 'include'});
      if (!r.ok) { console.warn(`[detail-shell] registry ${r.status}; no overrides`); return; }
      REGISTRY = await r.json();
    } catch (e2) { console.error('[detail-shell] registry fetch failed:', e2); return; }
  }

  // Step 3: collect every (subtab.module + extras) into a single set
  const paths = new Set();
  for (const meta of Object.values(REGISTRY.sub_tabs || {})) {
    if (meta.module)  paths.add(meta.module);
    for (const extra of (meta.extras || [])) paths.add(extra);
  }
  console.log(`[detail-shell] loading ${paths.size} sub-tab modules in parallel…`);

  // Step 4: parallel load + override
  const results = await Promise.allSettled(Array.from(paths).map(_loadAndOverride));
  const ok   = results.filter(r => r.status === 'fulfilled' && r.value).length;
  const fail = results.filter(r => r.status === 'rejected' || !r.value).length;
  console.log(`[detail-shell] sub-tab module load complete: ${ok} OK · ${fail} fail`);
  performance.mark('detail-shell-modules-loaded');

  // Step 5: wait for init() to set T, then render ONLY the active sub-tab.
  // (PERF-3 2026-05-09 — was: render all 25 modules up-front. Now: render
  // active sub-tab on boot, lazy-render others when fdSwitchTab fires.)
  const tReady = await new Promise(resolve => {
    let attempts = 0;
    const max = 60;  // 6s total at 100ms
    const tick = () => {
      const T = window.__getDetailTicker ? window.__getDetailTicker() : window.T;
      if (T && T.ticker) return resolve(true);
      if (++attempts >= max) {
        console.warn('[detail-shell] T not set after 6s — rendering may be incomplete');
        return resolve(false);
      }
      setTimeout(tick, 100);
    };
    tick();
  });
  if (!tReady) return;

  // Group module renderers by sub-tab id (derived from path: subtabs/<id>/<file>.js).
  // overview/* includes head + earningsBanner — those paint with overview and stay
  // visible across other tabs (FD_TAB_MAP toggles section visibility, not chrome).
  const SUBTAB_RENDERERS = {};
  for (const [path, fnName] of Object.entries(FILE_TO_WINDOW_FN)) {
    const m = path.match(/^subtabs\/([^/]+)\//);
    if (!m) continue;
    const id = m[1];
    if (!SUBTAB_RENDERERS[id]) SUBTAB_RENDERERS[id] = [];
    SUBTAB_RENDERERS[id].push(fnName);
  }

  // Render-once cache so re-activating a sub-tab is free.
  const _rendered = new Set();
  function _renderFn(name) {
    if (_rendered.has(name)) return;
    if (typeof window[name] !== 'function') return;
    _rendered.add(name);
    const t0 = performance.now();
    try { window[name](); }
    catch (e) { console.warn(`[detail-shell] render '${name}' failed:`, e); }
    window.__detailMetrics.renderMs[name] = +(performance.now() - t0).toFixed(1);
  }
  function _renderSubtab(id) {
    const fns = SUBTAB_RENDERERS[id] || [];
    for (const f of fns) _renderFn(f);
  }

  // Determine the active sub-tab. Hash route wins; otherwise default 'overview'.
  // (elite-detail.html's init() calls fdSwitchTab('overview') after sections paint.)
  function _activeSubtab() {
    const h = (location.hash || '').replace(/^#/, '').trim();
    if (h && SUBTAB_RENDERERS[h]) return h;
    return 'overview';
  }

  // Boot paint — only the active sub-tab.
  const initial = _activeSubtab();
  _renderSubtab(initial);
  console.log(`[detail-shell] PERF-3 lazy: painted '${initial}' (${_rendered.size} fns); other ${Object.keys(SUBTAB_RENDERERS).length - 1} sub-tabs deferred`);
  performance.mark('detail-shell-painted');

  // Wrap fdSwitchTab — render destination's renderers on first switch.
  // Idempotent: _renderFn caches per fn, so re-activations are O(1).
  const _origFdSwitch = window.fdSwitchTab;
  window.fdSwitchTab = function _lazyFdSwitch(tab) {
    _renderSubtab(tab);
    if (typeof _origFdSwitch === 'function') {
      return _origFdSwitch.apply(this, arguments);
    }
  };
  console.log('[detail-shell] PERF-3 wrapped fdSwitchTab for lazy paint-on-switch');
})();
