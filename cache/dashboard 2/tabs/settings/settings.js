// tabs/settings/settings.js — extracted from dashboard.html (renderSettings 2026-05-09)
// CapStudio modular loader. DATA accessed via getData() from core/shared.js.
// Window-bound helpers (function declarations) referenced as window.X where needed.
import { getData, $ } from '../../core/shared.js';

export async function render() {
  const DATA = getData();
  // Sectioned settings: Tab Visibility · Profile · Admin · Config
  const profile = window._VIS_PROFILE || 'trader';
  const tabsCount = document.querySelectorAll('.fs-link[data-tab]').length;
  const visCount = document.querySelectorAll('.fs-link[data-tab]:not([data-vis-hidden="1"])').length;

  $('settingsBody').innerHTML = `
    <div class="stg-tabs">
      <div class="stg-tab on" data-stg="visibility">🎯 Tab Visibility</div>
      <div class="stg-tab" data-stg="config">📋 Config</div>
      <div class="stg-tab" data-stg="admin">🔐 Admin</div>
      <div class="stg-tab" data-stg="users" id="stgTabUsers" style="display:none">👥 Users</div>
      <div class="stg-tab" data-stg="roles" id="stgTabRoles" style="display:none">🎭 Roles</div>
      <div class="stg-tab" data-stg="capstudio" id="stgTabCapStudio" style="display:none">🛡 CapStudio</div>
    </div>

    <!-- VISIBILITY PANE -->
    <div class="stg-pane on" data-stgpane="visibility">

      <div class="stg-stats">
        <div class="stg-stat"><div class="num" id="stgShown">${visCount}</div><div class="lbl">Tabs Shown</div></div>
        <div class="stg-stat"><div class="num" id="stgHidden" style="color:var(--paper-3)">${tabsCount - visCount}</div><div class="lbl">Tabs Hidden</div></div>
        <div class="stg-stat"><div class="num" style="color:var(--info,#3b82f6)" id="stgProfile">${(profile.charAt(0).toUpperCase() + profile.slice(1))}</div><div class="lbl">Active Profile</div></div>
        <div class="stg-stat"><div class="num" style="color:var(--green)">${tabsCount}</div><div class="lbl">Total Available</div></div>
      </div>

      <div class="stg-card">
        <h4>📊 Dashboard sidebar tabs</h4>
        <p class="desc">${tabsCount} tabs available. Click ☑ to toggle · click ▶ to expand groups · 🔒 = always visible.</p>
        <input type="text" class="stg-search" id="stgSearch" placeholder="🔍 Filter tabs by name…" oninput="_stgFilter(this.value)">
        <div class="stg-tree" id="stgTree"></div>
        <div class="stg-row-actions">
          <button class="stg-btn primary" onclick="_stgSave()">💾 Save</button>
          <button class="stg-btn" onclick="_stgResetToProfile()">↺ Reset to profile</button>
          <button class="stg-btn" onclick="_stgExport()">📥 Export</button>
        </div>
      </div>

      <div class="stg-card" style="border-left:3px solid #a855f7">
        <h4>👤 Active profile · ${PROFILE_NAMES[profile]}</h4>
        <p class="desc">${PROFILE_DESCRIPTIONS[profile]}</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
          ${Object.keys(PROFILES).map(p => `<span class="stg-btn ${p===profile?'primary':''}" onclick="_selectProfile('${p}')">${PROFILE_NAMES[p]} · ${PROFILES[p].length}</span>`).join('')}
        </div>
      </div>
    </div>

    <!-- CONFIG PANE -->
    <div class="stg-pane" data-stgpane="config">
      <div id="stgConfigBody"><div style="padding:20px;color:var(--paper-3);font-size:12px">Loading config…</div></div>
    </div>

    <!-- ADMIN PANE -->
    <div class="stg-pane" data-stgpane="admin">
      <div class="stg-admin">
        <b>🔐 Admin controls — gari only</b>
        <p style="margin:8px 0 0;font-size:11.5px;color:var(--paper-3)">These settings persist server-side and apply to all users. Currently your settings are local-only via localStorage.</p>
      </div>
      <div class="stg-card">
        <h4>Default profile for new sessions</h4>
        <p class="desc">When a fresh browser opens, this profile loads first.</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${Object.keys(PROFILES).filter(p => p !== 'custom').map(p => `<span class="stg-btn ${p==='trader'?'primary':''}">${PROFILE_NAMES[p]}</span>`).join('')}
        </div>
      </div>
      <div class="stg-card">
        <h4>Force-hidden tabs (global)</h4>
        <p class="desc">Tabs hidden here will be invisible to all users regardless of profile.</p>
        <div style="font-size:11.5px;color:var(--paper-3)">No tabs force-hidden.</div>
      </div>
      <div class="stg-card">
        <h4>Locked-essential tabs (global)</h4>
        <p class="desc">Tabs locked here can never be hidden.</p>
        <div style="font-size:11.5px;color:var(--paper-3)">⚙ Settings · 📋 Cheat Sheet (locked by default).</div>
      </div>
      <div class="stg-row-actions">
        <button class="stg-btn primary">💾 Save admin defaults</button>
        <button class="stg-btn">📤 Audit log · who changed what</button>
      </div>
    </div>

    <!-- USERS PANE (admin-only, embeds settings_users.html via iframe) -->
    <div class="stg-pane" data-stgpane="users">
      <iframe id="stgUsersFrame" src="" style="width:100%;height:78vh;border:1px solid var(--rule);border-radius:6px;background:var(--bg-1)"></iframe>
    </div>

    <!-- ROLES PANE (admin-only, embeds settings_roles.html via iframe) -->
    <div class="stg-pane" data-stgpane="roles">
      <iframe id="stgRolesFrame" src="" style="width:100%;height:78vh;border:1px solid var(--rule);border-radius:6px;background:var(--bg-1)"></iframe>
    </div>

    <!-- CAPSTUDIO PANE (admin-only, embeds settings_capstudio.html — RBAC matrix UI) -->
    <div class="stg-pane" data-stgpane="capstudio">
      <iframe id="stgCapStudioFrame" src="" style="width:100%;height:82vh;border:1px solid var(--rule);border-radius:6px;background:var(--bg-1)"></iframe>
    </div>
  `;

  // Wire stg-tab switching
  document.querySelectorAll('.stg-tab').forEach(t => {
    t.addEventListener('click', () => {
      const id = t.dataset.stg;
      document.querySelectorAll('.stg-tab').forEach(x => x.classList.toggle('on', x === t));
      document.querySelectorAll('.stg-pane').forEach(p => p.classList.toggle('on', p.dataset.stgpane === id));
      if (id === 'config') _stgRenderConfig();
      if (id === 'users') {
        const f = document.getElementById('stgUsersFrame');
        if (f && !f.src) f.src = 'settings_users.html';
      }
      if (id === 'roles') {
        const f = document.getElementById('stgRolesFrame');
        if (f && !f.src) f.src = 'settings_roles.html';
      }
      if (id === 'capstudio') {
        const f = document.getElementById('stgCapStudioFrame');
        if (f && !f.src) f.src = 'settings_capstudio.html';
      }
    });
  });

  // Reveal Users + Roles + CapStudio sub-tabs only for admins
  fetch('/api/whoami', {credentials: 'include'})
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d && d.is_admin) {
        const u = document.getElementById('stgTabUsers');
        const r = document.getElementById('stgTabRoles');
        const c = document.getElementById('stgTabCapStudio');
        if (u) u.style.display = '';
        if (r) r.style.display = '';
        if (c) c.style.display = '';
      }
    })
    .catch(() => {});

  // Build tree
  _stgBuildTree();
}

export function dispose() { /* no-op */ }


// ─── Helpers folded from dashboard.html (CapStudio sub-helpers fold 2026-05-09) ───
function _stgBuildTree() {
  const tree = $('stgTree');
  if (!tree) return;
  // Discover all tabs from the actual sidebar so we don't get stale
  const groups = {};
  document.querySelectorAll('.fs-link[data-tab]').forEach(el => {
    const id = el.dataset.tab;
    const name = (el.querySelector('span')?.textContent || id).trim();
    // Group by parent .fs-section's .fs-h
    const sec = el.closest('.fs-section');
    const groupName = sec ? (sec.querySelector('.fs-h')?.textContent || 'Other') : 'Other';
    if (!groups[groupName]) groups[groupName] = [];
    groups[groupName].push({ id, name, locked: id === 'settings' });
  });

  const profile = window._VIS_PROFILE || 'trader';
  const visibleSet = new Set(profile === 'custom'
    ? (window._VIS_CUSTOM || PROFILES[profile] || PROFILES.trader)
    : (PROFILES[profile] || PROFILES.trader));

  let html = '';
  Object.entries(groups).forEach(([gName, items]) => {
    const shown = items.filter(i => visibleSet.has(i.id)).length;
    const total = items.length;
    const allOn = shown === total;
    const allOff = shown === 0;
    const checkClass = allOn ? 'on' : allOff ? '' : 'partial';
    const checkLabel = allOn ? '✓' : allOff ? '·' : '∼';
    html += `<div class="stg-node parent" onclick="_stgToggleNode(event)">
      <span class="chev open">▶</span>
      <span class="stg-check ${checkClass}" data-grp="${gName}" onclick="event.stopPropagation();_stgToggleGroup('${gName}')">${checkLabel}</span>
      <span class="label">${gName}</span>
      <span class="count">${shown} of ${total}</span>
    </div>
    <div class="stg-children open" data-grp-children="${gName}">`;
    items.forEach(i => {
      const isShown = visibleSet.has(i.id);
      const lockBadge = i.locked ? '<span class="badge req">REQUIRED</span>' : '';
      html += `<div class="stg-node">
        <span class="chev leaf">·</span>
        <span class="stg-check ${isShown?'on':''} ${i.locked?'locked':''}" data-tab-id="${i.id}" onclick="${i.locked?'':`_stgToggleTab('${i.id}')`}">${isShown?'✓':'·'}</span>
        <span class="label ${isShown?'':'dim'}">${i.name}</span>
        ${lockBadge}
      </div>`;
    });
    html += '</div>';
  });
  tree.innerHTML = html;
}

async function _stgRenderConfig() {
  const body = $('stgConfigBody');
  if (!body || body.dataset.loaded) return;
  try {
    const r = await fetch('/api/config', { signal: AbortSignal.timeout(3000) });
    if (!r.ok) throw new Error(r.status);
    const cfg = await r.json();
    // Group top-level keys into readable sections
    const KEY_GROUPS = {
      'Scoring & Filters': ['scoring', 'scoring_weights', 'filters', 'gates', 'tail_loss_filter', 'score_bands', 'sector_relative_ranking'],
      'Regime': ['regime4_thresholds', 'regime_thresholds', 'regime_multipliers', 'regime_hysteresis', 'regime_weight_shifts', 'breadth_bands'],
      'Portfolio': ['portfolio', 'portfolio_vol_targeting', 'risk_budget', 'drawdown_controls', 'position_gates', 'account_profiles'],
      'Setups': ['setup_gates', 'catalyst_tiers', 'hold_period_by_family', 'hold_period_days', 'time_stops', 'entry_quality_rules', 'exit_rules', 'short_rules'],
      'Tier-1 & Signals': ['tier1_signals', 'technicals', 'adx', 'sector_rotation'],
      'VIX & Volatility': ['vix', 'vix_multipliers'],
      'Data': ['universe', 'data_sources', 'enrichment', 'price_buckets', 'options', 'reddit_wsb', 'congressional'],
      'Misc': ['_meta', 'alerts', 'output', 'performance', 'walk_forward', 'weekly', 'decisions', 'email', 'alpaca'],
    };
    let html = '<p style="font-size:11.5px;color:var(--paper-3);margin:0 0 14px">Read-only — edit via <code style="background:var(--bg-2);padding:1px 6px;border-radius:3px">config/config.json</code> on disk.</p>';
    Object.entries(KEY_GROUPS).forEach(([gName, keys]) => {
      const present = keys.filter(k => k in cfg);
      if (!present.length) return;
      html += `<div class="stg-config-grp"><h5>${gName}</h5>`;
      present.forEach(k => {
        const v = cfg[k];
        if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
          // Nested — show one row per inner key
          Object.entries(v).slice(0, 8).forEach(([ik, iv]) => {
            const cls = typeof iv === 'boolean' ? `bool-${iv}` : typeof iv === 'number' ? 'num' : '';
            html += `<div class="stg-kv"><span class="stg-k">${k}.${ik}</span><span class="stg-v ${cls}">${typeof iv === 'object' ? '{…}' : JSON.stringify(iv)}</span></div>`;
          });
          if (Object.keys(v).length > 8) html += `<div class="stg-kv"><span class="stg-k">${k}…</span><span class="stg-v">+${Object.keys(v).length - 8} more</span></div>`;
        } else {
          const cls = typeof v === 'boolean' ? `bool-${v}` : typeof v === 'number' ? 'num' : '';
          html += `<div class="stg-kv"><span class="stg-k">${k}</span><span class="stg-v ${cls}">${JSON.stringify(v)}</span></div>`;
        }
      });
      html += '</div>';
    });
    body.innerHTML = html;
    body.dataset.loaded = '1';
  } catch (e) {
    body.innerHTML = `<div style="padding:20px;font-size:12px;color:var(--paper-3)">Config endpoint unavailable: ${e.message}</div>`;
  }
}

function _stgToggleNode(e) {
  e.stopPropagation();
  const node = e.currentTarget;
  const next = node.nextElementSibling;
  const chev = node.querySelector('.chev');
  if (next && next.classList.contains('stg-children')) {
    next.classList.toggle('open');
    chev.classList.toggle('open');
  }
}

function _stgToggleTab(tabId) {
  if (window._VIS_PROFILE !== 'custom') {
    window._VIS_CUSTOM = (PROFILES[window._VIS_PROFILE] || PROFILES.trader).slice();
    window._VIS_PROFILE = 'custom';
  }
  const idx = window._VIS_CUSTOM.indexOf(tabId);
  if (idx >= 0) window._VIS_CUSTOM.splice(idx, 1);
  else window._VIS_CUSTOM.push(tabId);
  _applyVisibility();
  _stgBuildTree();
  _updateProfileUI();
}

function _stgToggleGroup(groupName) {
  // Toggle all tabs in this group at once
  const checks = document.querySelectorAll(`[data-grp-children="${groupName}"] .stg-check[data-tab-id]`);
  if (window._VIS_PROFILE !== 'custom') {
    window._VIS_CUSTOM = (PROFILES[window._VIS_PROFILE] || PROFILES.trader).slice();
    window._VIS_PROFILE = 'custom';
  }
  // Decide direction: if all currently on, turn off; otherwise turn on
  const allOn = Array.from(checks).every(c => c.classList.contains('on'));
  checks.forEach(c => {
    const tabId = c.dataset.tabId;
    if (c.classList.contains('locked')) return;
    const idx = window._VIS_CUSTOM.indexOf(tabId);
    if (allOn) {
      // Turn off
      if (idx >= 0) window._VIS_CUSTOM.splice(idx, 1);
    } else {
      // Turn on
      if (idx < 0) window._VIS_CUSTOM.push(tabId);
    }
  });
  _applyVisibility();
  _stgBuildTree();
  _updateProfileUI();
}

function _stgFilter(query) {
  const q = query.toLowerCase().trim();
  document.querySelectorAll('#stgTree .stg-node').forEach(n => {
    const label = n.querySelector('.label')?.textContent.toLowerCase() || '';
    const matches = !q || label.includes(q);
    n.style.display = matches ? '' : 'none';
  });
}

function _stgSave() {
  try {
    localStorage.setItem('_swing_profile', window._VIS_PROFILE || 'trader');
    if (window._VIS_PROFILE === 'custom') {
      localStorage.setItem('_swing_custom_tabs', JSON.stringify(window._VIS_CUSTOM || []));
    }
    _showToast('💾 Saved · ' + (PROFILE_NAMES[window._VIS_PROFILE] || 'Trader'));
  } catch (e) {
    _showToast('Save failed: ' + e.message, 'err');
  }
}

function _stgResetToProfile() {
  if (!confirm('Reset to default Trader profile?')) return;
  window._VIS_PROFILE = 'trader';
  delete window._VIS_CUSTOM;
  try { localStorage.removeItem('_swing_custom_tabs'); localStorage.setItem('_swing_profile', 'trader'); } catch (e) {}
  _applyVisibility();
  _stgBuildTree();
  _updateProfileUI();
}

function _stgExport() {
  const cfg = {
    profile: window._VIS_PROFILE || 'trader',
    custom: window._VIS_CUSTOM || null,
    timestamp: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `swingtrade-tabs-${cfg.profile}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function _selectProfile(profile, e) {
  if (e) e.stopPropagation();
  // Non-admin users with a server-assigned tab_profile cannot switch.
  // (Phase 2 enforcement — admin pins them to a profile.)
  const isAdmin = !!(window._WHOAMI_V2?.is_admin);
  const serverProfile = window._WHOAMI_V2?.user?.tab_profile;
  if (!isAdmin && serverProfile) {
    alert(`Your tab profile is set to "${serverProfile}" by your administrator and cannot be changed here. Contact admin to update.`);
    document.getElementById('fhPdrop')?.classList.remove('open');
    return;
  }
  window._VIS_PROFILE = profile;
  if (profile !== 'custom') {
    delete window._VIS_CUSTOM;
    try { localStorage.removeItem('_swing_custom_tabs'); } catch (_) {}
  }
  try { localStorage.setItem('_swing_profile', profile); } catch (_) {}
  _applyVisibility();
  _updateProfileUI();
  // If settings is open, rebuild tree
  const tree = document.getElementById('stgTree');
  if (tree) _stgBuildTree();
  // Close dropdown
  document.getElementById('fhPdrop')?.classList.remove('open');
}


// Auto-bind helpers to window for inline-HTML onclick callers
if (typeof window !== 'undefined') {
  window._stgBuildTree = _stgBuildTree;
  window._stgRenderConfig = _stgRenderConfig;
  window._stgToggleNode = _stgToggleNode;
  window._stgToggleTab = _stgToggleTab;
  window._stgToggleGroup = _stgToggleGroup;
  window._stgFilter = _stgFilter;
  window._stgSave = _stgSave;
  window._stgResetToProfile = _stgResetToProfile;
  window._stgExport = _stgExport;
  window._selectProfile = _selectProfile;
}
