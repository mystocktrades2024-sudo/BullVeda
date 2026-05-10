// core/actions.js — write-action handlers (Portfolio + Add Position +
// Bulk Import + Thesis Modal + Alpaca Sync). Extracted from dashboard.html
// 2026-05-09 (CapStudio modular loader).
//
// All handlers are also assigned to window in core/shell.js after import,
// so inline HTML `onclick="posMoveToBE(...)"` continues to resolve.
//
// CapStudio gating: each handler should call window.capHasAction(actionId)

// Toast helper for permission-denied feedback (CapStudio).
// Replaces the bare alert() that was triggering on every gated action.
// Renders a fixed-position pill in the bottom-right that auto-dismisses.
if (typeof window !== 'undefined' && !window.__capToast) {
  window.__capToast = function(msg, kind) {
    let host = document.getElementById('__capToastHost');
    if (!host) {
      host = document.createElement('div');
      host.id = '__capToastHost';
      host.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:10000;display:flex;flex-direction:column;gap:8px;pointer-events:none;font-family:Aptos,Inter,system-ui,sans-serif;';
      document.body.appendChild(host);
    }
    const t = document.createElement('div');
    const isFail = kind === 'fail';
    t.style.cssText = `padding:12px 18px;border-radius:8px;color:${isFail?'#f87171':'#34d399'};background:${isFail?'rgba(248,113,113,0.14)':'rgba(52,211,153,0.14)'};border:1px solid ${isFail?'#f87171':'#34d399'};font-size:13px;font-weight:600;backdrop-filter:blur(8px);box-shadow:0 12px 32px -8px rgba(0,0,0,0.4);transform:translateY(20px);opacity:0;transition:all 0.2s;pointer-events:auto;max-width:380px;`;
    t.textContent = msg;
    host.appendChild(t);
    requestAnimationFrame(() => { t.style.transform = 'translateY(0)'; t.style.opacity = '1'; });
    setTimeout(() => {
      t.style.transform = 'translateY(20px)';
      t.style.opacity = '0';
      setTimeout(() => t.remove(), 220);
    }, 2800);
  };
}

// at entry. (TODO once gating taxonomy is finalized.)

export async function posClosePosition(ticker, shares, price, event) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('pos_close')) { window.__capToast && window.__capToast('🚫 Denied · pos_close', 'fail'); return; }
  if (event) event.stopPropagation();
  const tk = (ticker || '').toUpperCase();
  if (!confirm(`Close ${tk} on Alpaca paper?\n\n• If long → submits market SELL of ${shares} shares\n• If short → submits market BUY of ${shares} shares (buy-to-cover)\n• Updates local portfolio P&L\n\nProceed?`)) {
    return;
  }
  try {
    const r = await fetch('/api/portfolio/close_on_alpaca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: tk })
    });
    const data = await r.json();
    if (!r.ok || data.error) {
      const msg = data.detail || data.error || r.statusText;
      alert(`Close failed: ${msg}`);
      return;
    }
    alert(`✓ ${data.message}\n\nOrder ID: ${data.submitted_order_id}\nStatus: ${data.status}`);
    // Re-sync to pull updated state from Alpaca after the fill
    setTimeout(() => syncAlpacaPositions(false), 1500);
  } catch (e) {
    alert(`Close error: ${e.message}`);
  }
}

export async function posMoveToBE(ticker, event) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('pos_move_to_be')) { window.__capToast && window.__capToast('🚫 Denied · pos_move_to_be', 'fail'); return; }
  if (event) event.stopPropagation();
  const tk = (ticker || '').toUpperCase();
  if (!confirm(`Move ${tk} stop to break-even (entry price)?`)) return;
  try {
    const r = await fetch('/api/portfolio/move_stop_be', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: tk })
    });
    const data = await r.json();
    if (!r.ok || data.error) { alert(`Failed: ${data.error || r.statusText}`); return; }
    alert(`✓ ${tk} stop moved to break-even at $${(data.new_stop || 0).toFixed(2)}`);
    setTimeout(() => location.reload(), 600);
  } catch (e) {
    alert(`Move-to-BE error: ${e.message}`);
  }
}

export async function posTrailStop(ticker, currentPrice, event) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('pos_trail_stop')) { window.__capToast && window.__capToast('🚫 Denied · pos_trail_stop', 'fail'); return; }
  if (event) event.stopPropagation();
  const tk = (ticker || '').toUpperCase();
  const trail = prompt(`Trail stop for ${tk} (currently at $${currentPrice.toFixed(2)})\n\nTrail by ATR multiple (default 1.25):`, '1.25');
  if (trail == null) return;
  try {
    const r = await fetch('/api/portfolio/trail_stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: tk, atr_mult: parseFloat(trail) || 1.25 })
    });
    const data = await r.json();
    if (!r.ok || data.error) { alert(`Failed: ${data.error || r.statusText}`); return; }
    alert(`✓ ${tk} stop trailed to $${(data.new_stop || 0).toFixed(2)}`);
    setTimeout(() => location.reload(), 600);
  } catch (e) {
    alert(`Trail-stop error: ${e.message}`);
  }
}

export async function syncAlpacaPositions(showAlert = false) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  const btn = document.getElementById('syncAlpacaBtn');
  const status = document.getElementById('syncAlpacaStatus');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Syncing...'; }
  if (status) status.textContent = 'syncing...';
  try {
    const r = await fetch('/api/portfolio/sync_alpaca', { method: 'POST' });
    const data = await r.json();
    if (!r.ok) {
      const msg = data.detail || data.error || r.statusText;
      if (status) { status.textContent = '✗ ' + msg; status.style.color = 'var(--red)'; }
      if (showAlert) alert(`Alpaca sync failed: ${msg}\n\nMake sure ALPACA_API_KEY is in .env and the server has been restarted to pick it up.`);
      return;
    }
    const ts = new Date(data.synced_at);
    const tStr = ts.toLocaleTimeString();
    if (status) {
      const parts = [];
      if (data.alpaca_positions > 0) parts.push(`${data.alpaca_positions} positions`);
      if (data.inserted?.length) parts.push(`+${data.inserted.length} new`);
      if (data.closed?.length) parts.push(`-${data.closed.length} closed`);
      const summary = parts.length ? parts.join(' · ') : 'no positions';
      status.textContent = `✓ synced ${tStr} · ${summary} · acct ${data.alpaca_account}`;
      status.style.color = 'var(--green)';
    }
    if (showAlert) {
      let msg = `✓ Synced from Alpaca paper (${data.alpaca_account})\n\n`;
      msg += `  Equity: $${data.equity.toLocaleString()}\n`;
      msg += `  Cash: $${data.cash.toLocaleString()}\n`;
      msg += `  Buying Power: $${data.buying_power.toLocaleString()}\n`;
      msg += `  Alpaca positions: ${data.alpaca_positions}\n`;
      msg += `  Local positions after sync: ${data.local_positions_after}\n`;
      if (data.inserted?.length) msg += `\n  Inserted: ${data.inserted.join(', ')}`;
      if (data.closed?.length)   msg += `\n  Closed (Alpaca closed externally): ${data.closed.join(', ')}`;
      if (data.updated?.length)  msg += `\n  Updated prices: ${data.updated.length} positions`;
      alert(msg);
    }
    // Use the fresh portfolio block returned by the sync endpoint —
    // it reads portfolio_state.json directly so it's the live truth, not
    // the cached data.json bundle (which is built only when swing_trade.py runs).
    if (data.portfolio && DATA) {
      DATA.portfolio = data.portfolio;
    }
    if (typeof renderPortfolio === 'function') {
      try { renderPortfolio(); } catch (_) {}
    }
  } catch (e) {
    if (status) { status.textContent = '✗ ' + e.message; status.style.color = 'var(--red)'; }
    if (showAlert) alert(`Sync error: ${e.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '↻ Sync Alpaca'; }
  }
}

export function _autoSyncPortfolio() {
  const now = Date.now();
  if (now - _lastAlpacaSync < 30_000) return; // debounce 30s
  _lastAlpacaSync = now;
  syncAlpacaPositions(false);
}

export async function _apAutofillFromTicker() {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  const tEl = document.getElementById('_apTicker');
  const t = (tEl?.value || '').trim().toUpperCase();
  if (!t || t.length < 1) return;
  tEl.value = t;  // normalize to uppercase

  // Reset auto markers
  ['_apEntryAuto','_apStopAuto','_apT1Auto','_apT2Auto'].forEach(id => {
    const el = document.getElementById(id); if (el) el.textContent = '';
  });

  let plan = null, price = null;
  try {
    const all = await _getTickers();   // cached; same path as compare modal
    const T = all && all[t];
    if (T) {
      plan = T.trade_plan || {};
      price = T.price ?? T.last;
    }
  } catch (_) {}

  // Fall back to a live analysis if ticker isn't in today's scan universe.
  // /api/analyze runs run_deep_dive() server-side and returns the trade_plan.
  if (!plan || (!plan.stop && !plan.target1)) {
    try {
      const r = await fetch(`/api/analyze/${encodeURIComponent(t)}`, {credentials:'include'});
      if (r.ok) {
        const d = await r.json();
        plan = d.trade_plan || plan || {};
        price = price ?? d.price;
      }
    } catch (_) {}
  }

  if (!plan) return;

  // Populate ONLY when the user hasn't already typed something
  const setIfEmpty = (id, val, autoId, label) => {
    const el = document.getElementById(id);
    if (!el || val == null || isNaN(Number(val))) return;
    if (!el.value) {
      el.value = Number(val).toFixed(2);
      const auto = document.getElementById(autoId);
      if (auto) auto.textContent = `· ${label} auto`;
    }
  };
  // Entry: prefer the entry_low (start of zone), or current price
  const entryFill = plan.entry_low ?? plan.entry ?? price;
  setIfEmpty('_apEntry', entryFill, '_apEntryAuto', 'plan');
  setIfEmpty('_apStop',  plan.stop,    '_apStopAuto', 'plan');
  setIfEmpty('_apT1',    plan.target1, '_apT1Auto',   'plan');
  setIfEmpty('_apT2',    plan.target2, '_apT2Auto',   'plan');
}

export async function _submitAddPosition(e) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  e.preventDefault();
  const msg = document.getElementById('_apMsg');
  msg.textContent = '';
  // If user left stop/T1 blank, try one more autofill pass (idempotent)
  await _apAutofillFromTicker();
  const stopV = document.getElementById('_apStop').value;
  const t1V   = document.getElementById('_apT1').value;
  if (!stopV || !t1V) {
    msg.textContent = `No trade plan found for this ticker — set ${!stopV ? 'STOP' : ''}${!stopV && !t1V ? ' and ' : ''}${!t1V ? 'T1' : ''} manually.`;
    return false;
  }
  const body = {
    ticker:        document.getElementById('_apTicker').value.trim().toUpperCase(),
    entry_price:   parseFloat(document.getElementById('_apEntry').value),
    shares:        parseInt(document.getElementById('_apShares').value, 10),
    stop:          parseFloat(stopV),
    target1:       parseFloat(t1V),
    target2:       document.getElementById('_apT2').value ? parseFloat(document.getElementById('_apT2').value) : null,
    direction:     document.getElementById('_apDir').value,
    entry_date:    document.getElementById('_apDate').value || null,
    notes:         document.getElementById('_apNotes').value || '',
    setup:         '',
  };
  // Sanity check: stop must be on the right side of entry
  if (body.direction === 'long' && body.stop >= body.entry_price) {
    msg.textContent = 'For LONG: stop must be BELOW entry.'; return false;
  }
  if (body.direction === 'short' && body.stop <= body.entry_price) {
    msg.textContent = 'For SHORT: stop must be ABOVE entry.'; return false;
  }
  try {
    const r = await fetch('/api/portfolio/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'include',
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      msg.textContent = (await r.text()) || `HTTP ${r.status}`;
      return false;
    }
    _closeModal('_addPosModal');
    if (typeof renderPortfolio === 'function') renderPortfolio();
    return false;
  } catch (err) {
    msg.textContent = String(err);
    return false;
  }
}

export function openAddPositionModal() {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  _closeModal('_addPosModal');
  const m = document.createElement('div');
  m.id = '_addPosModal';
  m.style.cssText = 'position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;font-family:DM Sans,Aptos,system-ui,sans-serif;color:var(--ink-0);';
  m.innerHTML = `
    <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:10px;padding:24px;width:480px;max-width:92vw;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2 style="margin:0;font-size:16px;letter-spacing:0.04em;">+ Add Paper Position</h2>
        <button onclick="_closeModal('_addPosModal')" style="background:transparent;border:none;color:var(--ink-3);font-size:18px;cursor:pointer;">×</button>
      </div>
      <p style="color:var(--ink-2);font-size:12px;margin:0 0 14px;line-height:1.5;">
        Type a ticker, then tab/blur — entry/stop/T1/T2 auto-fill from the latest scan's trade plan.
        Override any field manually. Live P&amp;L updates every 5s; intraday alerts fire on stop/T1 within 60s.
      </p>
      <form id="_addPosForm" onsubmit="return _submitAddPosition(event)" style="display:grid;gap:10px;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">TICKER *</span>
            <input id="_apTicker" required maxlength="6" placeholder="AAPL"
              onblur="_apAutofillFromTicker()"
              onchange="_apAutofillFromTicker()"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;text-transform:uppercase;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">SHARES *</span>
            <input id="_apShares" type="number" min="1" required placeholder="100"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">ENTRY $ <span id="_apEntryAuto" style="color:var(--info);font-size:10px;"></span></span>
            <input id="_apEntry" type="number" step="0.01" min="0.01" required placeholder="auto"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">STOP $ <span id="_apStopAuto" style="color:var(--info);font-size:10px;"></span></span>
            <input id="_apStop" type="number" step="0.01" min="0.01" placeholder="auto from trade plan"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">T1 $ <span id="_apT1Auto" style="color:var(--info);font-size:10px;"></span></span>
            <input id="_apT1" type="number" step="0.01" min="0.01" placeholder="auto from trade plan"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">T2 $ <span id="_apT2Auto" style="color:var(--info);font-size:10px;"></span></span>
            <input id="_apT2" type="number" step="0.01" min="0.01" placeholder="auto from trade plan"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">DIRECTION</span>
            <select id="_apDir" style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;">
            <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">ENTRY DATE</span>
            <input id="_apDate" type="date"
              style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
          </label>
        </div>
        <label style="display:flex;flex-direction:column;gap:4px;">
          <span style="font-size:11px;color:var(--ink-3);letter-spacing:0.06em;">SETUP / NOTES</span>
          <input id="_apNotes" placeholder="e.g. Trend Continuation — held since IPO"
            style="padding:9px 11px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:DM Sans;font-size:13px;">
        </label>
        <div id="_apMsg" style="font-size:12px;min-height:18px;color:var(--fail);"></div>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
          <button type="button" onclick="_closeModal('_addPosModal')" style="padding:9px 16px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-1);font-family:DM Sans;cursor:pointer;">Cancel</button>
          <button type="submit" style="padding:9px 18px;background:var(--accent);border:none;border-radius:5px;color:var(--bg-0);font-weight:700;cursor:pointer;font-family:DM Sans;">Add Position</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(m);
  setTimeout(() => document.getElementById('_apTicker')?.focus(), 50);
}

export function openBulkImportModal() {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  _closeModal('_bulkImportModal');
  const m = document.createElement('div');
  m.id = '_bulkImportModal';
  m.style.cssText = 'position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;font-family:DM Sans,Aptos,system-ui,sans-serif;color:var(--ink-0);';
  m.innerHTML = `
    <div style="background:var(--bg-1);border:1px solid var(--rule);border-radius:10px;padding:24px;width:640px;max-width:92vw;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2 style="margin:0;font-size:16px;letter-spacing:0.04em;">⇡ Bulk Import Positions (CSV)</h2>
        <button onclick="_closeModal('_bulkImportModal')" style="background:transparent;border:none;color:var(--ink-3);font-size:18px;cursor:pointer;">×</button>
      </div>
      <p style="color:var(--ink-2);font-size:12px;margin:0 0 8px;line-height:1.5;">
        Paste CSV below, one row per holding. <b>Required columns:</b> ticker, entry, shares, stop, target1.
        <b>Optional:</b> target2, direction, entry_date, notes.
      </p>
      <p style="color:var(--ink-3);font-size:11px;margin:0 0 12px;font-family:var(--mono);">
        Example header: <code>ticker,entry,shares,stop,target1,target2,direction,entry_date,notes</code>
      </p>
      <textarea id="_biCsv" rows="9" placeholder="ticker,entry,shares,stop,target1
AAPL,180.00,100,168.50,200.00
NVDA,500.00,50,470.00,560.00"
        style="width:100%;box-sizing:border-box;padding:10px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-0);font-family:JetBrains Mono,monospace;font-size:12px;"></textarea>
      <div id="_biMsg" style="font-size:12px;min-height:18px;color:var(--ink-2);margin-top:8px;"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:12px;">
        <button type="button" onclick="_closeModal('_bulkImportModal')" style="padding:9px 16px;background:var(--bg-2);border:1px solid var(--rule-2);border-radius:5px;color:var(--ink-1);font-family:DM Sans;cursor:pointer;">Cancel</button>
        <button type="button" onclick="_submitBulkImport()" style="padding:9px 18px;background:var(--info);border:none;border-radius:5px;color:var(--bg-0);font-weight:700;cursor:pointer;font-family:DM Sans;">Import All</button>
      </div>
    </div>`;
  document.body.appendChild(m);
  setTimeout(() => document.getElementById('_biCsv')?.focus(), 50);
}

export async function _submitBulkImport() {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('submit_trade')) { window.__capToast && window.__capToast('🚫 Denied · submit_trade', 'fail'); return; }
  const txt = document.getElementById('_biCsv').value.trim();
  const msg = document.getElementById('_biMsg');
  if (!txt) { msg.textContent = 'Paste CSV first.'; msg.style.color = 'var(--fail)'; return; }

  // Parse CSV — header row required
  const lines = txt.split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) { msg.textContent = 'Need a header row + at least one data row.'; msg.style.color = 'var(--fail)'; return; }
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
  const required = ['ticker','entry','shares','stop','target1'];
  const missing = required.filter(r => !headers.includes(r));
  if (missing.length) { msg.textContent = 'Missing required columns: ' + missing.join(', '); msg.style.color = 'var(--fail)'; return; }

  msg.style.color = 'var(--ink-2)';
  msg.textContent = `Parsed ${lines.length - 1} rows. Importing...`;

  let added = 0, skipped = 0, failed = 0;
  const errors = [];
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i].split(',').map(c => c.trim());
    const obj = {}; headers.forEach((h, idx) => obj[h] = row[idx] || '');
    const body = {
      ticker:      obj.ticker.toUpperCase(),
      entry_price: parseFloat(obj.entry),
      shares:      parseInt(obj.shares, 10),
      stop:        parseFloat(obj.stop),
      target1:     parseFloat(obj.target1),
      target2:     obj.target2 ? parseFloat(obj.target2) : null,
      direction:   (obj.direction || 'long').toLowerCase(),
      entry_date:  obj.entry_date || null,
      notes:       obj.notes || '',
      setup:       obj.setup || '',
    };
    try {
      const r = await fetch('/api/portfolio/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify(body),
      });
      if (r.ok) { added++; }
      else {
        const err = await r.text();
        if (err.includes('already has')) skipped++;
        else { failed++; errors.push(`${body.ticker}: ${err}`); }
      }
    } catch (e) {
      failed++; errors.push(`${body.ticker}: ${e}`);
    }
  }
  msg.style.color = failed > 0 ? 'var(--warn)' : 'var(--pass)';
  msg.textContent = `✓ ${added} added · ⊘ ${skipped} already open · ✗ ${failed} failed`;
  if (errors.length) msg.textContent += '  →  ' + errors.slice(0, 3).join(' | ');
  if (added > 0 && typeof renderPortfolio === 'function') renderPortfolio();
}

export async function openThesisModal(ticker) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('edit_thesis')) { window.__capToast && window.__capToast('🚫 Denied · edit_thesis', 'fail'); return; }
  if (!ticker) return;
  ticker = String(ticker).toUpperCase();
  _closeModal('_thesisModal');
  const m = document.createElement('div');
  m.id = '_thesisModal';
  m.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.78);display:flex;align-items:center;justify-content:center;font-family:DM Sans,Aptos,system-ui,sans-serif;color:var(--ink-0);padding:20px;';
  m.innerHTML = `<div id="_thesisCard" style="background:var(--bg-1);border:1px solid var(--rule);border-radius:12px;padding:0;width:760px;max-width:96vw;max-height:90vh;overflow:auto;box-shadow:0 12px 60px rgba(0,0,0,0.6);">
    <div style="padding:20px 24px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:var(--bg-1);z-index:1;">
      <div style="display:flex;align-items:baseline;gap:14px;">
        <h2 style="margin:0;font-size:22px;letter-spacing:0.02em;font-weight:700;">${ticker}</h2>
        <span id="_thNarrSrc" style="font-size:10px;color:var(--ink-3);font-family:var(--mono);letter-spacing:0.1em;text-transform:uppercase;"></span>
      </div>
      <button onclick="_closeModal('_thesisModal')" style="background:transparent;border:none;color:var(--ink-3);font-size:22px;cursor:pointer;line-height:1;padding:4px 8px;">×</button>
    </div>
    <div id="_thesisBody" style="padding:20px 24px;">Loading thesis…</div>
  </div>`;
  document.body.appendChild(m);
  m.addEventListener('click', (ev) => { if (ev.target === m) _closeModal('_thesisModal'); });

  let row = null;
  try {
    const all = await _getTickers();
    row = all && all[ticker];
  } catch (_e) { /* fall through */ }
  const body = document.getElementById('_thesisBody');
  if (!body) return;
  // 2026-05-08 — structured thesis lives on `thesis_card` (the legacy `thesis`
  // string field is reserved for the Overview tab's one-liner).
  const th = (row && (row.thesis_card || (typeof row.thesis === 'object' ? row.thesis : null))) || null;
  if (!th || th.error) {
    body.innerHTML = `<div style="color:var(--ink-2);font-size:13px;">No thesis available for ${ticker}${th && th.error ? ` — ${th.error}` : ''}.</div>`;
    return;
  }
  document.getElementById('_thNarrSrc').textContent = 'auto-generated';
  body.innerHTML = _renderThesisCard(row, th);
}

export function _renderThesisCard(row, th) {
  // CapStudio gate (2026-05-09)
  if (typeof window !== 'undefined' && window.capHasAction && !window.capHasAction('edit_thesis')) { window.__capToast && window.__capToast('🚫 Denied · edit_thesis', 'fail'); return; }
  // Defensive scalar coercion — never render an object directly
  const _s = (v, fallback = '') => {
    if (v == null) return fallback;
    if (typeof v === 'string' || typeof v === 'number') return String(v);
    if (typeof v === 'object') return v.label || v.name || v.value || JSON.stringify(v).slice(0, 60);
    return String(v);
  };
  const score = (typeof th.score === 'number') ? th.score : 0;
  const verdict = _s(th.verdict, '?');
  const verdictColor = verdict === 'BUY' ? 'var(--pass)' : verdict === 'SELL' ? 'var(--fail)' : 'var(--info)';
  const sector = _s(th.sector || row.sector, '—');
  const industry = _s(th.industry || row.industry);
  const tier = _s(th.tier);
  const regime = _s(th.regime);
  const price = (typeof row.price === 'number' ? row.price : (typeof row.last_price === 'number' ? row.last_price : 0));
  // Header strip
  let html = `<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:14px;font-size:12px;font-family:var(--mono);">
    <span style="background:${verdictColor};color:var(--bg-0);padding:3px 9px;border-radius:4px;font-weight:700;">${verdict}</span>
    <span style="color:var(--ink-2);">Score <b style="color:var(--ink-0);">${score}</b></span>
    <span style="color:var(--ink-3);">·</span>
    <span style="color:var(--ink-2);">$${(+price).toFixed(2)}</span>
    <span style="color:var(--ink-3);">·</span>
    <span style="color:var(--ink-2);">${sector}${industry ? ' · ' + industry : ''}</span>
    ${tier ? `<span style="color:var(--ink-3);">·</span><span style="color:var(--accent);">${tier}</span>` : ''}
    ${regime ? `<span style="color:var(--ink-3);">·</span><span style="color:var(--ink-2);">${regime}</span>` : ''}
  </div>`;

  // Narrative
  html += `<div style="background:var(--bg-2);border-left:3px solid var(--accent);padding:12px 14px;border-radius:0 6px 6px 0;font-size:14px;line-height:1.55;color:var(--ink-0);margin-bottom:18px;">
    ${_escapeHtml(th.narrative || '')}
  </div>`;

  // Score breakdown
  if (Array.isArray(th.score_breakdown) && th.score_breakdown.length) {
    html += `<h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-3);margin:14px 0 8px;">Score Breakdown</h3>`;
    html += `<table style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px;margin-bottom:18px;">
      <thead><tr style="text-align:left;color:var(--ink-3);border-bottom:1px solid var(--rule-2);">
        <th style="padding:6px 4px;font-weight:600;">Pillar</th>
        <th style="padding:6px 4px;font-weight:600;text-align:right;">Pts</th>
        <th style="padding:6px 4px;font-weight:600;text-align:right;">Max</th>
        <th style="padding:6px 4px;font-weight:600;text-align:center;">Bar</th>
      </tr></thead><tbody>`;
    for (const p of th.score_breakdown) {
      const ok = p.verdict === 'check' ? '✓' : p.verdict === 'warn' ? '⚠' : '✗';
      const okC = p.verdict === 'check' ? 'var(--pass)' : p.verdict === 'warn' ? 'var(--warn)' : 'var(--fail)';
      const isNum = typeof p.max === 'number';
      const pct = isNum ? Math.max(0, Math.min(100, (p.pts / p.max) * 100)) : 0;
      html += `<tr style="border-bottom:1px solid color-mix(in oklch, var(--rule-2) 40%, transparent);">
        <td style="padding:6px 4px;color:var(--ink-1);"><span style="color:${okC};margin-right:6px;">${ok}</span>${_escapeHtml(p.pillar)}</td>
        <td style="padding:6px 4px;text-align:right;color:var(--ink-0);">${p.pts}</td>
        <td style="padding:6px 4px;text-align:right;color:var(--ink-2);">${p.max}</td>
        <td style="padding:6px 4px;width:140px;">${isNum ? `<div style="background:var(--bg-2);height:6px;border-radius:3px;overflow:hidden;"><div style="width:${pct}%;height:100%;background:${okC};"></div></div>` : ''}</td>
      </tr>`;
    }
    html += '</tbody></table>';
  }

  // Why bullish & risks (two columns)
  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px;">`;
  html += `<div><h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--pass);margin:0 0 8px;">Why Bullish</h3>`;
  if (Array.isArray(th.why_bullish) && th.why_bullish.length) {
    html += '<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;color:var(--ink-1);">';
    for (const b of th.why_bullish) html += `<li>${_escapeHtml(b)}</li>`;
    html += '</ul>';
  } else { html += '<div style="color:var(--ink-3);font-size:12px;">—</div>'; }
  html += '</div>';
  html += `<div><h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--warn);margin:0 0 8px;">Risks</h3>`;
  if (Array.isArray(th.risks) && th.risks.length) {
    html += '<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;color:var(--ink-1);">';
    for (const r of th.risks) html += `<li>${_escapeHtml(r)}</li>`;
    html += '</ul>';
  } else { html += '<div style="color:var(--ink-3);font-size:12px;">—</div>'; }
  html += '</div></div>';

  // Trade plan
  const tp = th.trade_plan || {};
  if (tp && (tp.entry_low || tp.stop || tp.target1)) {
    html += `<h3 style="font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-3);margin:14px 0 8px;">Trade Plan</h3>`;
    html += `<div style="background:var(--bg-2);padding:12px 14px;border-radius:6px;font-family:var(--mono);font-size:12px;color:var(--ink-1);line-height:1.7;">`;
    if (tp.setup_type) html += `<div><span style="color:var(--ink-3);">Setup:</span> ${_escapeHtml(tp.setup_type)}${tp.entry_quality_adj ? ` <span style="color:var(--ink-3);">— ${_escapeHtml(tp.entry_quality_adj)}</span>` : ''}</div>`;
    if (tp.entry_low && tp.entry_high) html += `<div><span style="color:var(--ink-3);">Entry:</span> $${tp.entry_low} – $${tp.entry_high}</div>`;
    if (tp.stop) html += `<div><span style="color:var(--ink-3);">Stop:</span> <span style="color:var(--fail);">$${tp.stop}</span></div>`;
    if (tp.target1) html += `<div><span style="color:var(--ink-3);">T1:</span> <span style="color:var(--pass);">$${tp.target1}</span>${tp.rr_ratio ? ` <span style="color:var(--ink-3);">(${tp.rr_ratio}R)</span>` : ''}</div>`;
    if (tp.target2) html += `<div><span style="color:var(--ink-3);">T2:</span> <span style="color:var(--pass);">$${tp.target2}</span></div>`;
    if (tp.max_hold_days) html += `<div><span style="color:var(--ink-3);">Hold:</span> ${tp.max_hold_days} ${typeof tp.max_hold_days === 'number' ? 'days' : ''}</div>`;
    if (tp.size_pct) html += `<div><span style="color:var(--ink-3);">Size:</span> ${(+tp.size_pct).toFixed(2)}% of account</div>`;
    html += `</div>`;
  }

  if (th.decision_reason) {
    html += `<div style="margin-top:14px;padding:10px 14px;background:color-mix(in oklch, var(--info) 8%, var(--bg-2));border-left:3px solid var(--info);border-radius:0 4px 4px 0;font-size:12px;color:var(--ink-2);">
      <b style="color:var(--info);">Decision:</b> ${_escapeHtml(th.decision_reason)}
    </div>`;
  }

  html += `<div style="margin-top:18px;text-align:right;font-size:11px;color:var(--ink-3);">
    <a href="/v2/elite-detail.html?t=${row.ticker}" style="color:var(--accent);text-decoration:none;">Open full detail page →</a>
  </div>`;

  return html;
}

