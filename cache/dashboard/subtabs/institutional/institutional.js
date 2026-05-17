// subtabs/institutional/institutional.js — extracted from elite-detail.html (renderInstitutional 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  // Render all 4 sub-panes (Zacks already wired separately, but call here too for safety)
  try { renderZacks(); } catch (e) { console.error('zacks pane', e); }
  try { renderInstOwnership(); } catch (e) { console.error('ownership pane', e); }
  try { renderSmartFlow(); } catch (e) { console.error('flow pane', e); }
  try { renderPreTradeCheck(); } catch (e) { console.error('pretrade pane', e); }
  // Wire sub-tab clicks (idempotent — fine if called multiple times)
  document.querySelectorAll('.inst-stab').forEach(t => {
    if (t._wired) return;
    t._wired = true;
    t.addEventListener('click', () => {
      const tab = t.dataset.inst;
      document.querySelectorAll('.inst-stab').forEach(x => x.classList.toggle('on', x === t));
      document.querySelectorAll('.inst-pane').forEach(p => p.classList.toggle('on', p.dataset.instPane === tab));
      // Trigger the corresponding renderer in case sub-pane wasn't ready earlier
      if (tab === 'pretrade') {
        try { renderPreTradeCheck(); } catch (e) { console.error('pretrade pane', e); }
      } else if (tab === 'zacks') {
        try { renderZacks(); } catch (e) {}
      } else if (tab === 'ownership') {
        try { renderInstOwnership(); } catch (e) {}
      } else if (tab === 'flow') {
        try { renderSmartFlow(); } catch (e) {}
      }
    });
  });
}

export function dispose() { /* no-op */ }
