// ─── SwingTrade iPad Shell ────────────────────────────────────────────
// MVP: split-view list + iframe detail. Reuses /v2/elite-detail.html for
// per-ticker rendering — no module duplication.
// Data source: same data.critical.json + tickers.json the desktop uses.

const $ = id => document.getElementById(id);

// State
const state = {
  data: null,             // data.critical.json
  tickers: null,          // tickers.json (lazy-loaded on first detail open)
  activeTab: 'scanner',
  selectedTicker: null,
};

// ─── DATA LOADING ─────────────────────────────────────────────────────
async function loadCriticalData() {
  try {
    const r = await fetch('/v2/data.critical.json', { credentials: 'include' });
    state.data = await r.json();
    return true;
  } catch (e) {
    console.error('[ipad] data.critical.json failed', e);
    return false;
  }
}

async function loadTickersIfNeeded() {
  if (state.tickers) return state.tickers;
  try {
    const r = await fetch('/v2/tickers.json', { credentials: 'include' });
    state.tickers = await r.json();
  } catch (e) {
    console.error('[ipad] tickers.json failed', e);
    state.tickers = {};
  }
  return state.tickers;
}

// ─── TOP-BAR RENDERS ──────────────────────────────────────────────────
function renderTopBar() {
  const d = state.data || {};
  const regime = (d.regime || {}).regime || (d.regime || {}).regime4 || 'unknown';
  const regimeLabel = {
    bull: 'BULL', neutral: 'NEUTRAL', bear: 'BEAR',
    risk_on_trending: 'RISK-ON', risk_on_choppy: 'CHOPPY',
    risk_off_trending: 'RISK-OFF', panic: 'PANIC',
  }[regime] || regime.toUpperCase();
  const regimeBadge = $('ipRegimeBadge');
  regimeBadge.textContent = regimeLabel;
  regimeBadge.className = 'ip-regime ' +
    (regime === 'bull' || regime === 'risk_on_trending' ? 'bull' :
     regime === 'neutral' || regime === 'risk_on_choppy' ? 'neutral' : 'bear');

  const t = (d.scan_time || d.last_scan_time || d.run_date || '').slice(0, 16).replace('T', ' ');
  $('ipScanTime').textContent = t || '—';
}

// ─── ROW BUILDER ──────────────────────────────────────────────────────
function buildRow(r) {
  const t = r.ticker || '';
  const px = +(r.price || 0);
  const score = +(r.score || 0);
  const verdict = (r.verdict || r.stage || 'WATCH').toUpperCase();
  const setup = r.strategy || r.setup || '';
  const rs = r.rs_rank || 0;
  const sel = state.selectedTicker === t ? ' on' : '';
  const scoreCls = score >= 80 ? 'high' : score >= 65 ? 'mid' : 'low';
  return `
    <div class="ip-row${sel}" data-ticker="${t}">
      <div class="ip-row-l">
        <span class="ip-row-tk">${t}</span>
        <span class="ip-row-px">$${px.toFixed(2)}</span>
      </div>
      <div class="ip-row-mid">
        <div class="ip-row-name">${(setup || '—').slice(0, 30)}</div>
        <div class="ip-row-meta">
          <span>RS <b>${rs}</b></span>
          ${r.rr ? `<span>R:R <b>${(+r.rr).toFixed(1)}</b></span>` : ''}
          ${r.sector ? `<span>${r.sector.slice(0, 12)}</span>` : ''}
        </div>
      </div>
      <div class="ip-row-r">
        <span class="ip-pill ${verdict}">${verdict}</span>
        <span class="ip-row-score ${scoreCls}">${score}</span>
      </div>
    </div>`;
}

// ─── TAB CONTENT ──────────────────────────────────────────────────────
function getRowsForTab(tab) {
  const d = state.data || {};

  if (tab === 'scanner') {
    // BUY + WATCH from short_term, sorted by score desc
    const all = (d.short_term || []).concat(d.medium_term || []);
    return all
      .filter(r => ['BUY', 'WATCH'].includes((r.verdict || '').toUpperCase()))
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 100);
  }
  if (tab === 'elite') {
    // Top by EV — fall through to elite_picks if present, else top-25 by score
    const elite = (d.elite_picks || {}).picks || (d.elite_picks || []) ||
                  (d.short_term || []).slice(0, 25);
    return Array.isArray(elite) ? elite : [];
  }
  if (tab === 'watchlist') {
    // Custom watchlist — pull anything with custom_added flag or watchlist=true
    const all = (d.short_term || []).concat(d.medium_term || []);
    return all.filter(r => r.custom_added || r.in_watchlist || r.watchlist);
  }
  if (tab === 'portfolio') {
    return (d.portfolio || {}).positions || (d.portfolio || []) || [];
  }
  if (tab === 'settings') {
    return [];   // settings tab renders differently (see renderList)
  }
  return [];
}

// ─── LIST RENDER ──────────────────────────────────────────────────────
function renderList() {
  const tab = state.activeTab;
  const body = $('ipListBody');
  const titleMap = {
    scanner: 'Scanner',
    watchlist: 'Watchlist',
    portfolio: 'Portfolio',
    elite: 'Elite Picks',
    settings: 'Settings',
  };
  $('ipListTitle').textContent = titleMap[tab] || tab;

  if (tab === 'settings') {
    body.innerHTML = renderSettingsView();
    $('ipListCount').textContent = '';
    return;
  }

  const rows = getRowsForTab(tab);
  $('ipListCount').textContent = rows.length;
  if (!rows.length) {
    body.innerHTML = `<div class="ip-empty">${
      tab === 'watchlist' ? 'No tickers in your watchlist yet.' :
      tab === 'portfolio' ? 'No open positions.' :
      'No picks for this view.'
    }</div>`;
    return;
  }
  body.innerHTML = rows.map(buildRow).join('');
}

function renderSettingsView() {
  const d = state.data || {};
  const cfg = d.config || {};
  const r4 = (cfg.regime4_thresholds || {}).risk_on_trending || {};
  const buyMin = r4.buy_min_score || '—';
  return `
  <div style="padding: 20px;">
    <div style="font-size: 11px; color: var(--paper-3); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px;">Account</div>
    <div style="background: var(--bg-2); border: 1px solid var(--rule); border-radius: 10px; padding: 14px; margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
        <span>Equity</span>
        <span style="font-family: var(--mono); font-weight: 600;">$${((d.portfolio || {}).equity || 5000).toLocaleString()}</span>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-top: 1px solid var(--rule);">
        <span>Open positions</span>
        <span style="font-family: var(--mono); font-weight: 600;">${((d.portfolio || {}).positions || []).length}</span>
      </div>
    </div>

    <div style="font-size: 11px; color: var(--paper-3); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px;">Active Config</div>
    <div style="background: var(--bg-2); border: 1px solid var(--rule); border-radius: 10px; padding: 14px; margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
        <span>BUY min score (trending)</span>
        <span style="font-family: var(--mono); font-weight: 600;">${buyMin}</span>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-top: 1px solid var(--rule);">
        <span>Universe</span>
        <span style="font-family: var(--mono); font-weight: 600;">${d.universe_count || 'S&P+R1k+R2k'}</span>
      </div>
    </div>

    <div style="font-size: 11px; color: var(--paper-3); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px;">Open Desktop View</div>
    <button onclick="window.location='/v2/dashboard.html'" style="width: 100%; padding: 14px; background: var(--bg-2); border: 1px solid var(--rule); border-radius: 10px; color: var(--accent); font-size: 14px; font-weight: 500; cursor: pointer; min-height: 44px;">
      Open full desktop dashboard →
    </button>
    <div style="font-size: 11px; color: var(--paper-3); margin-top: 8px; text-align: center;">
      iPad shell · v0.1 · 2026-05-10
    </div>
  </div>`;
}

// ─── DETAIL PANE ──────────────────────────────────────────────────────
function showDetail(ticker) {
  state.selectedTicker = ticker;
  $('ipDetailTicker').textContent = ticker;
  // Reuse existing elite-detail.html via iframe — no module duplication
  const body = $('ipDetailBody');
  body.innerHTML = `<iframe src="/v2/elite-detail.html?t=${encodeURIComponent(ticker)}" loading="lazy"></iframe>`;

  // Portrait: slide in detail pane
  $('ipDetailPane').classList.add('shown');

  // Update list selection highlight
  document.querySelectorAll('.ip-row').forEach(el => {
    el.classList.toggle('on', el.dataset.ticker === ticker);
  });

  // Update External-link button to open detail in new tab
  $('ipExternBtn').onclick = () => {
    window.open(`/v2/elite-detail.html?t=${encodeURIComponent(ticker)}`, '_blank');
  };
}

function hideDetail() {
  $('ipDetailPane').classList.remove('shown');
  state.selectedTicker = null;
  document.querySelectorAll('.ip-row.on').forEach(el => el.classList.remove('on'));
}

// ─── TAB SWITCHING ────────────────────────────────────────────────────
function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('.ip-tab').forEach(el => {
    el.classList.toggle('on', el.dataset.tab === tab);
  });
  hideDetail();
  renderList();
}

// ─── PULL-TO-REFRESH (touch-driven) ───────────────────────────────────
function wirePullToRefresh() {
  const body = $('ipListBody');
  let startY = 0, pulling = false, threshold = 70;
  body.addEventListener('touchstart', e => {
    if (body.scrollTop <= 0) {
      startY = e.touches[0].clientY;
      pulling = true;
    }
  }, { passive: true });
  body.addEventListener('touchmove', e => {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > threshold && body.scrollTop <= 0) {
      pulling = false;
      refreshData();
    }
  }, { passive: true });
  body.addEventListener('touchend', () => { pulling = false; }, { passive: true });
}

async function refreshData() {
  $('ipScanTime').textContent = 'refreshing…';
  await loadCriticalData();
  renderTopBar();
  renderList();
}

// ─── EVENT WIRING ─────────────────────────────────────────────────────
function wireEvents() {
  // Tab buttons
  document.querySelectorAll('.ip-tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  // Row clicks (delegated)
  $('ipListBody').addEventListener('click', e => {
    const row = e.target.closest('.ip-row');
    if (row && row.dataset.ticker) showDetail(row.dataset.ticker);
  });
  // Back button (portrait)
  $('ipBackBtn').addEventListener('click', hideDetail);
  // Refresh
  $('ipRefreshBtn').addEventListener('click', refreshData);

  wirePullToRefresh();
}

// ─── BOOT ─────────────────────────────────────────────────────────────
async function boot() {
  wireEvents();
  const ok = await loadCriticalData();
  if (!ok) {
    $('ipListBody').innerHTML = `<div class="ip-empty">Failed to load data. <button onclick="location.reload()" style="margin-top: 12px; padding: 10px 20px; background: var(--accent); border: none; color: white; border-radius: 8px;">Retry</button></div>`;
    return;
  }
  renderTopBar();
  renderList();

  // If URL has ?t=NVDA, auto-open detail
  const params = new URLSearchParams(location.search);
  const initT = params.get('t');
  if (initT) showDetail(initT.toUpperCase());
}

boot();
