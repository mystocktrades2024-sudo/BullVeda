// tabs/crypto/crypto.js — extracted from dashboard.html (renderCrypto 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render() {
  const DATA = getData();
  const CRYPTO = ['BTC-USD.CC', 'ETH-USD.CC', 'SOL-USD.CC', 'BNB-USD.CC'];
  const EQUITIES = ['MSTR', 'COIN', 'MARA', 'RIOT', 'CLSK'];
  let prices = {};
  try {
    const r = await fetch(`/api/live/quote?tickers=${[...CRYPTO, ...EQUITIES].join(',')}`, { signal: AbortSignal.timeout(4000) });
    if (r.ok) prices = (await r.json()).prices || {};
  } catch (_) {}
  $('cryptoMeta').textContent = Object.keys(prices).length ? `${Object.keys(prices).length} quotes live` : 'offline · cached data';
  const fmtCrypto = (sym) => {
    const p = prices[sym];
    return p ? `<b>$${p.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</b>` : '<span style="color:var(--ink-3)">—</span>';
  };
  $('cryptoTiles').innerHTML = ['BTC-USD.CC','ETH-USD.CC','SOL-USD.CC','BNB-USD.CC'].map(sym => {
    const label = sym.replace('-USD.CC','');
    const p = prices[sym];
    return `<div class="stat-tile"><div class="lbl">${label}</div><div class="v" style="font-size:16px">${p ? '$' + Number(p).toLocaleString(undefined,{maximumFractionDigits:2}) : '—'}</div><div class="sub">USD · 15min delayed</div></div>`;
  }).join('');
}

export function dispose() { /* no-op */ }
