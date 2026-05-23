// subtabs/tv/tv.js — TradingView Advanced Chart embed.
// 2026-05-22 — Rewrote to use embed-widget-advanced-chart.js (auto-mount)
// instead of tv.js (Charting Library, requires manual widget construction).
// Old code referenced _mountTV() which was never defined → tv.js auto-init
// fell through to TradingView's internal symbol-search bootstrap with a
// null search engine, throwing "Search engine null is not supported".
//
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — set by
// core/elite-detail-shell.js before calling render().

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  if (!T) return;
  const sym = T.ticker;
  const cid = `tv_${sym}_${Date.now()}`;
  const isLight = document.body.classList.contains('light');

  const body = document.getElementById('tvBody');
  if (!body) return;

  body.innerHTML = `
    <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:6px;padding:0;overflow:hidden">
      <div style="padding:12px 18px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;align-items:center">
        <div><b style="color:var(--ink-0)">${sym}</b> <span style="color:var(--ink-2);font-size:11px">· TradingView Advanced Chart</span></div>
        <a href="https://www.tradingview.com/symbols/${sym}/" target="_blank" rel="noopener" style="color:var(--info);font-size:11px;letter-spacing:.06em;text-transform:uppercase">Open in TradingView →</a>
      </div>
      <div class="tradingview-widget-container" id="${cid}" style="height:560px;width:100%"></div>
    </div>`;

  const container = document.getElementById(cid);
  if (!container) return;

  const script = document.createElement('script');
  script.type = 'text/javascript';
  script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  script.async = true;
  script.innerHTML = JSON.stringify({
    autosize: true,
    symbol: sym,
    interval: 'D',
    timezone: 'America/Los_Angeles',
    theme: isLight ? 'light' : 'dark',
    style: '1',
    locale: 'en',
    enable_publishing: false,
    allow_symbol_change: true,
    hide_side_toolbar: false,
    container_id: cid,
  });
  container.appendChild(script);
}

export function dispose() { /* no-op */ }
