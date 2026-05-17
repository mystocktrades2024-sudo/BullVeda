// tabs/audit/live_poll.js — 5-second live-quote poller for the audit grid.
// Hits /api/live/quote (Schwab → EODHD fallback) and updates Today + %Δ + DN
// cells in place. Auto-starts on module import; resume-safe across tab
// switches (interval keeps running, idle when document is hidden).

let _pollIntervalId = null;

// Walk visible tbody rows. Two pools:
//   1. Recent rows (entry within last 7 trading days) — ALWAYS update,
//      D1-D5 cells still actively being filled.
//   2. First 100 visible rows not in pool 1 — keeps Today + %Δ live for browse.
// Combined cap: 250 tickers per poll, chunked into 2 batches of 125 to fit
// Schwab's batch quote limit.
export async function pollOnce() {
  try {
    const tbody = document.getElementById('auditTbody');
    if (!tbody) return;
    const rows = [...tbody.querySelectorAll('tr[data-ticker]')];
    if (rows.length === 0) return;

    const recentTickers = new Set();
    const otherTickers  = [];
    rows.forEach(row => {
      const t = row.dataset.ticker;
      if (!t) return;
      const date    = row.dataset.date;
      const tdSince = tradingDaysSince(date);
      if (tdSince != null && tdSince <= 7) {
        recentTickers.add(t);
      } else if (otherTickers.length < 100 && !recentTickers.has(t)) {
        otherTickers.push(t);
      }
    });
    const tickers = [...new Set([...recentTickers, ...otherTickers])].slice(0, 250);
    if (tickers.length === 0) return;

    const CHUNK   = 125;
    const batches = [];
    for (let i = 0; i < tickers.length; i += CHUNK) batches.push(tickers.slice(i, i + CHUNK));

    const results = await Promise.all(batches.map(batch =>
      fetch(`/api/live/quote?tickers=${batch.join(',')}`, { signal: AbortSignal.timeout(6000) })
        .then(r => r.ok ? r.json() : null)
        .catch(() => null)
    ));
    const prices = {};
    let source = 'unknown';
    for (const d of results) {
      if (!d) continue;
      Object.assign(prices, d.prices || {});
      if (d.source) source = d.source;
    }

    rows.forEach(row => {
      const t     = row.dataset.ticker;
      const entry = parseFloat(row.dataset.entry || 0);
      const px    = prices[t];
      if (px == null || !entry) return;
      const pct = (px / entry - 1) * 100;
      const c   = pct > 0 ? 'var(--green)' : pct < 0 ? 'var(--red)' : 'var(--paper-3)';

      const todayCell = row.querySelector('.audit-today');
      const pctCell   = row.querySelector('.audit-pctnow');
      if (todayCell) todayCell.textContent = '$' + px.toFixed(2);
      if (pctCell) {
        pctCell.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
        pctCell.style.color = c;
      }

      // Intraday live price is NOT a valid D-cell value during market hours —
      // D{k} is the CLOSE of trading-day k, which doesn't exist until after
      // 4pm ET. Previous synthesis overwrote D1 with the live %Δ, making
      // closed cells indistinguishable from in-progress and confusing users.
      // Live %Δ lives in .audit-pctnow only. D-cells are filled by the
      // EOD-rebuilt audit_ledger (run_daily_scan.sh runs build_audit_ledger.py).
    });

    const meta = document.getElementById('auditMeta');
    if (meta && source) {
      const srcLabel = source === 'schwab' ? '🟢 SCHWAB · LIVE'
                     : source === 'eodhd'  ? '🟡 EODHD · 15m'
                     : source === 'cache'  ? '🔘 CACHED'
                     : source;
      const baseTxt = meta.textContent.split(' · ')[0];
      meta.textContent = `${baseTxt} · ${srcLabel} · ${recentTickers.size} recent`;
    }
  } catch (e) { /* silent */ }
}

export function tradingDaysSince(entryISO) {
  if (!entryISO) return null;
  const entry = new Date(entryISO + 'T00:00:00');
  const today = new Date();
  let n = 0;
  const cur = new Date(entry);
  while (cur < today) {
    cur.setDate(cur.getDate() + 1);
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) n++;  // skip Sat/Sun
  }
  return n;
}

export function startPolling() {
  if (_pollIntervalId) return;
  _pollIntervalId = setInterval(() => {
    if (document.visibilityState !== 'hidden') pollOnce();
  }, 5000);
}
