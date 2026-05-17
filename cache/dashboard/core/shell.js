// core/shell.js — registry-driven tab module loader.
//
// Strategy: read the CapStudio capability registry (/api/capability-registry).
// Any entry under `tabs` or `sub_tabs` that has a `module` field is treated
// as a candidate for module-based override of the inline renderXxx function.
//
// shell.js then mutates window.TAB_RENDERERS[id] = wrappedRender(id) for each
// such entry. The inline function body in dashboard.html is NEVER deleted —
// it stays as a safety fallback. If shell.js fails or a module fails to load,
// the inline render still works.
//
// (2026-05-09 — second attempt after the broken-render incident this morning.
//  Lessons applied: registry-driven loader, inline body kept as fallback,
//  per-tab browser verify between extractions, console-log for debug.)

console.log('[shell] CapStudio module loader booting…');
performance.mark('shell-loader-start');

const _moduleCache = {};   // id → import promise (cached/idempotent)
const _disposers   = {};   // id → disposer function from the previous activation
let   _activeTab   = null;
let   REGISTRY     = null; // populated from /api/capability-registry

function _loadModule(modulePath) {
  if (!_moduleCache[modulePath]) {
    const v = window.__moduleVersion || '1';
    const url = `../${modulePath}?v=${v}`;
    const t0 = performance.now();
    _moduleCache[modulePath] = import(url)
      .then(mod => {
        const ms = (performance.now() - t0).toFixed(1);
        console.log(`[shell] loaded ${modulePath} in ${ms}ms`);
        if (typeof window.__capStudioMetrics !== 'undefined') {
          window.__capStudioMetrics.moduleLoadMs[modulePath] = +ms;
        }
        return mod;
      })
      .catch(err => {
        console.error(`[shell] failed to import '${url}':`, err);
        delete _moduleCache[modulePath];
        return null;
      });
  }
  return _moduleCache[modulePath];
}

// CapStudio metrics container — populated by _loadModule + _wrapRender.
// Inspect at runtime: `window.__capStudioMetrics`
window.__capStudioMetrics = window.__capStudioMetrics || { moduleLoadMs: {}, renderMs: {} };

function _wrapRender(id, modulePath) {
  // Returns a sync function compatible with TAB_RENDERERS lookup.
  // setupTabSwitcher() calls TAB_RENDERERS[tab]() synchronously, so we
  // kick off the async load and paint when the module resolves.
  return function _moduleRender() {
    // Dispose previous tab if it exposed one
    if (_activeTab && _activeTab !== id && _disposers[_activeTab]) {
      try { _disposers[_activeTab](); } catch (e) { console.warn(`[shell] dispose '${_activeTab}' failed:`, e); }
      delete _disposers[_activeTab];
    }
    _activeTab = id;

    _loadModule(modulePath).then(mod => {
      if (!mod) return; // import failed; inline fallback already ran via legacy path
      // Race guard: user may have switched tabs mid-load
      if (_activeTab !== id) return;
      try {
        if (typeof mod.render === 'function') {
          const t0 = performance.now();
          mod.render();
          const ms = (performance.now() - t0).toFixed(1);
          console.log(`[shell] rendered tab '${id}' from module ${modulePath} in ${ms}ms`);
          if (window.__capStudioMetrics) window.__capStudioMetrics.renderMs[id] = +ms;
        }
        if (typeof mod.dispose === 'function') _disposers[id] = mod.dispose;
      } catch (e) {
        console.error(`[shell] module render '${id}' threw:`, e);
      }
    });
  };
}

async function _installOverrides() {
  if (!window.TAB_RENDERERS) {
    console.warn('[shell] window.TAB_RENDERERS not yet available; retrying in 100ms…');
    setTimeout(_installOverrides, 100);
    return;
  }
  if (!REGISTRY) {
    console.warn('[shell] registry not loaded; cannot install overrides');
    return;
  }

  let installed = 0;
  // Walk both `tabs` and `sub_tabs` (sub_tabs go into FD_TAB_MAP_RENDERERS later;
  // for now we only override main `tabs` entries with a `module` field).
  for (const [id, meta] of Object.entries(REGISTRY.tabs || {})) {
    if (!meta.module) continue;
    if (!(id in window.TAB_RENDERERS)) {
      console.warn(`[shell] tab '${id}' has module '${meta.module}' but is not in TAB_RENDERERS — skipping`);
      continue;
    }
    window.TAB_RENDERERS[id] = _wrapRender(id, meta.module);
    installed++;
  }
  console.log(`[shell] installed ${installed} module override(s) for tabs:`,
    Object.keys(REGISTRY.tabs || {}).filter(id => REGISTRY.tabs[id].module && id in window.TAB_RENDERERS));
  performance.mark('shell-modules-installed');

  // If the user has already activated an extracted tab (e.g. landed on
  // /v2/#playbook), force a re-render so the module's render fires now
  // rather than waiting for the next tab switch.
  const current = (location.hash || '').replace('#', '') || window._currentTab;
  if (current && window.TAB_RENDERERS[current] && REGISTRY.tabs[current]?.module) {
    try { window.TAB_RENDERERS[current](); } catch (e) { console.warn('[shell] initial paint failed:', e); }
  }
}

// ── Bootstrap ──────────────────────────────────────────────────────────
// 1. Fetch /v2/_v for cache-bust version (mtime of core/ + tabs/)
// 2. Fetch /api/capability-registry to know which tabs have modules
// 3. Install overrides into window.TAB_RENDERERS
(async function _boot() {
  // Steps 1+2 combined (PERF-1b 2026-05-09): single /api/v2-bootstrap call returns
  // both version + registry. HTML head has <link rel="preload"> for this URL so
  // the browser warms the response before this code even parses.
  // Falls back to the two split endpoints (/v2/_v + /api/capability-registry) if 404.
  try {
    const r = await fetch('/api/v2-bootstrap', {credentials: 'include'});
    if (r.ok) {
      const j = await r.json();
      window.__moduleVersion = j.version || String(Date.now());
      REGISTRY = j.registry;
      console.log(`[shell] bootstrap: v=${window.__moduleVersion}, ${Object.keys(REGISTRY.tabs || {}).length} tabs, ${Object.keys(REGISTRY.sub_tabs || {}).length} sub-tabs (1 RTT)`);
    } else {
      throw new Error(`bootstrap ${r.status}`);
    }
  } catch (e) {
    console.warn('[shell] bootstrap failed, falling back to split endpoints:', e.message);
    // Fallback path — old behavior, two sequential fetches
    try {
      const r = await fetch('./_v', {cache: 'no-store', credentials: 'include'});
      window.__moduleVersion = r.ok ? (await r.text()).trim() : String(Date.now());
    } catch (_) { window.__moduleVersion = String(Date.now()); }
    try {
      const r = await fetch('/api/capability-registry', {credentials: 'include'});
      if (!r.ok) {
        console.warn(`[shell] /api/capability-registry returned ${r.status}; no overrides will install`);
        return;
      }
      REGISTRY = await r.json();
      console.log(`[shell] loaded registry: ${Object.keys(REGISTRY.tabs || {}).length} tabs, ${Object.keys(REGISTRY.sub_tabs || {}).length} sub-tabs (fallback path)`);
    } catch (e2) { console.error('[shell] registry fetch failed:', e2); return; }
  }

  // Step 3: install overrides
  _installOverrides();

  // Step 4: load core modules in PARALLEL (PERF-1a 2026-05-09)
  // Previously sequential awaits — drawer (168ms) → widgets → actions added up.
  // These three are independent; Promise.allSettled overlaps their fetches.
  const v = window.__moduleVersion || '1';
  await Promise.allSettled([
    // drawer — _renderInlineDrawer keystone, used by 3 row-expand surfaces
    import(`./drawer.js?v=${v}`).then(drawer => {
      window.__drawer = drawer;
      console.log('[shell] drawer module loaded');
      performance.mark('shell-drawer-loaded');
    }).catch(e => console.error('[shell] drawer module failed to load:', e)),

    // widgets — auto-binds exports to window for inline HTML callers
    import(`./widgets.js?v=${v}`).then(() => {
      console.log('[shell] widgets module loaded');
      performance.mark('shell-widgets-loaded');
    }).catch(e => console.error('[shell] widgets module failed to load:', e)),

    // actions — sets window.X = actions.X for inline onclick="posMoveToBE(...)"
    import(`./actions.js?v=${v}`).then(actions => {
      window.__actions = actions;
      for (const [name, fn] of Object.entries(actions)) {
        if (typeof fn === 'function') window[name] = fn;
      }
      console.log(`[shell] actions module loaded: ${Object.keys(actions).filter(k => typeof actions[k] === 'function').length} handlers`);
      performance.mark('shell-actions-loaded');
    }).catch(e => console.error('[shell] actions module failed to load:', e)),
  ]);
  performance.mark('shell-core-modules-all-loaded');
})();
