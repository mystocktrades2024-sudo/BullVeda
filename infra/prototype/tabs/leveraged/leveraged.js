// tabs/leveraged/leveraged.js — extracted from dashboard.html (renderLeveraged 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export function render() {
  const DATA = getData();
  const host = document.getElementById('leveragedDynamic');
  const meta = document.getElementById('leveragedMeta');
  if (!host || !DATA) return;
  const lev = DATA.leveraged || {};
  const regime = DATA.regime || {};
  const vix = (typeof regime.vix === 'number' ? regime.vix
              : regime.vix?.vix_current) ?? null;
  const regimeName = regime.regime || regime.regime4 || 'unknown';
  const picks = lev.picks || [];
  const watchlist = lev.watchlist || [];

  // Hard rules surfaced as a status banner
  const vixHot = vix != null && vix > 25;
  const trending = String(regimeName).includes('trending');
  let stance, stanceColor, stanceMsg;
  if (vixHot) {
    stance = 'NO TRADES'; stanceColor = 'var(--red)';
    stanceMsg = `VIX ${vix?.toFixed(1)} > 25 — leveraged ETFs are too risky. Volatility drag will compound losses faster than directional moves can recover.`;
  } else if (trending) {
    stance = 'PERMITTED'; stanceColor = 'var(--green)';
    stanceMsg = `VIX ${vix?.toFixed(1) ?? '?'} · regime ${regimeName} · trend-following leveraged ETFs are allowed (TQQQ/UPRO/SOXL with the trend).`;
  } else {
    stance = 'CAUTION'; stanceColor = 'var(--accent)';
    stanceMsg = `VIX ${vix?.toFixed(1) ?? '?'} · regime ${regimeName} · trend isn't established. Wait for confirmation before deploying leveraged ETFs.`;
  }

  if (meta) meta.textContent = `${picks.length}/${watchlist.length} in scan · stance: ${stance}`;

  // Top picks (if any passed scan)
  let picksHTML = '';
  if (picks.length) {
    const rows = picks.map(p => {
      const sc = p.score || 0;
      const scColor = sc >= 80 ? 'var(--green)' : sc >= 70 ? 'var(--accent)' : 'var(--ink-3)';
      return `<tr style="border-bottom:1px dashed var(--rule)">
        <td style="padding:8px 12px;font-family:var(--mono);font-weight:700">
          <a href="#" onclick="window.setDetailTicker && window.setDetailTicker('${p.ticker}'); return false;" style="color:var(--ink-0);text-decoration:none">${p.ticker}</a>
        </td>
        <td style="padding:8px 12px;text-align:right;font-family:var(--mono)">$${(p.price ?? 0).toFixed(2)}</td>
        <td style="padding:8px 12px;text-align:right;color:${scColor};font-weight:700">${sc.toFixed(0)}</td>
        <td style="padding:8px 12px;text-align:center;">${p.verdict || '—'}</td>
        <td style="padding:8px 12px;color:var(--ink-2);font-size:11px">${p.setup || '—'}</td>
        <td style="padding:8px 12px;color:var(--ink-2);font-size:11px">${p.sector || '—'}</td>
      </tr>`;
    }).join('');
    picksHTML = `
      <div class="card" style="margin-bottom:10px"><div class="card-h">Leveraged ETFs that passed today's scan</div>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead style="background:var(--bg-2);color:var(--ink-3);text-align:left;border-bottom:1px solid var(--rule-2)">
            <tr><th style="padding:9px 12px">TICKER</th><th style="padding:9px 12px;text-align:right">PRICE</th><th style="padding:9px 12px;text-align:right">SCORE</th><th style="padding:9px 12px;text-align:center">VERDICT</th><th style="padding:9px 12px">SETUP</th><th style="padding:9px 12px">SECTOR</th></tr>
          </thead><tbody>${rows}</tbody></table>
      </div>`;
  } else {
    picksHTML = `
      <div class="card" style="margin-bottom:10px;padding:14px 18px;border:1px dashed var(--rule);">
        <span style="color:var(--ink-2);font-size:12.5px">
          <b>0 of ${watchlist.length} leveraged ETFs</b> made today's scan. Your watchlist:
          <span style="font-family:var(--mono);color:var(--ink-3)">${watchlist.join(', ')}</span>
        </span>
        <div style="margin-top:6px;color:var(--ink-3);font-size:11px;line-height:1.55;">
          Leveraged ETFs are filtered out by the prescreen because they don't have classic stock-setup patterns.
          They're tactical-only — deploy when regime + trend align (see stance banner above).
        </div>
      </div>`;
  }

  host.innerHTML = `
    <div style="margin-bottom:14px;padding:14px 18px;background:linear-gradient(90deg, color-mix(in oklch, ${stanceColor} 16%, var(--bg-1)) 0%, var(--bg-1) 70%);border:1px solid ${stanceColor};border-left:4px solid ${stanceColor};border-radius:8px;">
      <div style="display:flex;align-items:baseline;gap:14px;">
        <span style="font-weight:700;color:${stanceColor};font-size:13px;letter-spacing:0.06em;">STANCE: ${stance}</span>
        <span style="color:var(--ink-2);font-size:12px">${stanceMsg}</span>
      </div>
    </div>
    ${picksHTML}`;
}

export function dispose() { /* no-op */ }
