// subtabs/tv/tv.js — extracted from elite-detail.html (renderTV 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const sym = T.ticker;
  $('tvBody').innerHTML = `
    <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:6px;padding:0;overflow:hidden">
      <div style="padding:12px 18px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;align-items:center">
        <div><b style="color:var(--ink-0)">${sym}</b> <span style="color:var(--ink-2);font-size:11px">· TradingView Advanced Chart</span></div>
        <a href="https://www.tradingview.com/symbols/${sym}/" target="_blank" rel="noopener" style="color:var(--info);font-size:11px;letter-spacing:.06em;text-transform:uppercase">Open in TradingView →</a>
      </div>
      <div class="tradingview-widget-container" style="height:560px;width:100%">
        <div id="tradingview_${sym}" style="height:100%;width:100%"></div>
      </div>
    </div>`;
  // Lazy-load TradingView widget
  if (!window._tvLoaded) {
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/tv.js';
    s.async = true;
    s.onload = () => { window._tvLoaded = true; _mountTV(sym); };
    document.head.appendChild(s);
  } else {
    _mountTV(sym);
  }
}

export function dispose() { /* no-op */ }
