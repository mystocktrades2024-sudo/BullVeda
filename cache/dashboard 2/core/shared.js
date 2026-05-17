// core/shared.js — singleton state + utilities for the V2 dashboard.
//
// This module is the ONLY place that defines globals shared across tabs.
// Tab modules import from here; legacy inline code in dashboard.html also
// works through window.* assignments below (compatibility bridge).
//
// Single writer rule: only the data-poll path in dashboard.html mutates DATA.
// Tab modules treat getData() as read-only.

// ── State accessors ────────────────────────────────────────────────────
// dashboard.html declares DATA/CURRENT/TIER/SEARCH with `let` (script-block
// scoped, NOT bound to window). It exposes closure-based getters so this
// module can read the current value at call time. (CapStudio 2026-05-09)
export const getData    = () => window._getDashboardData ? window._getDashboardData() : window.DATA;
export const getTickers = () => window._getTickers ? window._getTickers() : Promise.resolve(null);
export const getProfile = () => ({
  tier:    window._getDashboardTier    ? window._getDashboardTier()    : window.TIER,
  search:  window._getDashboardSearch  ? window._getDashboardSearch()  : window.SEARCH,
  current: window._getDashboardCurrent ? window._getDashboardCurrent() : window.CURRENT,
  visProfile: window._VIS_PROFILE,
  visCustom:  window._VIS_CUSTOM,
});

// ── DOM helpers ────────────────────────────────────────────────────────
export const $ = (id) => document.getElementById(id);

export const escapeHtml = (s) => {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]
  ));
};

// ── Number / currency formatters ──────────────────────────────────────
export const fmt    = (v, d=2) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d);
export const px     = (v)      => v == null ? '—' : Number(v).toFixed(2);
export const dollar = (v)      => v == null ? '—' : '$' + Number(v).toFixed(2);

// ── Widget proxies (delegate to dashboard.html until those move out) ──
export const logoHtml            = (ticker, size=20) => window._logoHtml ? window._logoHtml(ticker, size) : '';
export const updateSidebarCounts = ()                => window._updateSidebarCounts && window._updateSidebarCounts();
export const expandPanel         = (t)               => window.expandPanel && window.expandPanel(t);

// ── Compat bridge: also expose under their legacy names on window. ────
// Lets inline scripts that ran before this module continue to work.
// Module is loaded as `type=module` (deferred), so it executes after the
// classic <script> block has populated window.{DATA, _logoHtml, ...}.
// Re-assigning the same names here is a no-op for legacy callers.
if (typeof window !== 'undefined') {
  window.__core = window.__core || {};
  window.__core.shared = { getData, getTickers, getProfile, $, escapeHtml, fmt, px, dollar, logoHtml, updateSidebarCounts, expandPanel };
}
