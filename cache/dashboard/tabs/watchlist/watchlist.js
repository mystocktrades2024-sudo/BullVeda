// tabs/watchlist/watchlist.js — extracted from dashboard.html (_renderWatchlistTab 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const wl = _getWatchlist();
  const body = document.getElementById('watchlistBody');
  const meta = document.getElementById('watchlistCardMeta');
  if (meta) meta.textContent = `${wl.length} ticker${wl.length !== 1 ? 's' : ''}`;
  if (!body) return;
  if (wl.length === 0) {
    body.innerHTML = '<div style="padding:30px;color:var(--paper-3);text-align:center;font-size:13px">No starred tickers yet. Click ☆ on any scanner row to add.</div>';
    return;
  }
  // Cross-reference with DATA rows
  const rowMap = {};
  if (DATA) {
    [...(DATA.short_term || []), ...(DATA.medium_term || []), ...(DATA.long_term || []), ...(DATA.killed || [])].forEach(r => { rowMap[r.ticker] = r; });
  }
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;padding:6px">
      ${wl.map(t => {
        const r = rowMap[t] || { ticker: t };
        const v = r.stage || r.verdict || '—';
        const c = r.pct_chg || 0;
        const upDn = c > 0 ? 'up' : c < 0 ? 'dn' : 'dim';
        return `
          <div style="background:var(--ink-2);border:1px solid var(--line);border-radius:6px;padding:12px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px" onclick="window.location.href='elite-detail.html?t=${t}&from=watchlist'">
            <div style="display:flex;align-items:center;gap:10px;min-width:0">
              ${_logoHtml(t, 28)}
              <div style="min-width:0">
                <div style="font-weight:700;font-size:14px;color:var(--paper)">${t}</div>
                <div style="font-size:11px;color:var(--paper-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${(r.sector || '—').slice(0, 30)}</div>
              </div>
            </div>
            <div style="text-align:right">
              <div style="font-size:13px;font-weight:700;color:var(--paper)">${r.price ? '$' + r.price.toFixed(2) : '—'}</div>
              <div class="${upDn}" style="font-size:11px">${r.pct_chg != null ? (c >= 0 ? '+' : '') + c.toFixed(2) + '%' : ''}</div>
            </div>
            <button onclick="event.stopPropagation();_toggleStar(event,'${t}',null);_renderWatchlistTab();" style="background:none;border:0;color:var(--watch);font-size:18px;cursor:pointer;padding:4px 8px" title="Remove">★</button>
          </div>`;
      }).join('')}
    </div>`;
}

export function dispose() { /* no-op */ }
