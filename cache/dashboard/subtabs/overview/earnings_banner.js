// subtabs/overview/earnings_banner.js — extracted from elite-detail.html (renderEarningsBanner 2026-05-09)
// CapStudio modular loader for the per-ticker detail page.
// T (current ticker) accessed via window.__getDetailTicker() — NOT yet wired
// in elite-detail.html. This module is created as a candidate for future
// activation; calling render() before wiring requires window.T to be set.

const _T = () => (window.__getDetailTicker ? window.__getDetailTicker() : window.T);

export function render() {
  const T = _T();
  const body = document.getElementById('earningsBannerBody');
  if (!body || !T) return;
  const ed = T.earn_days != null ? T.earn_days : T.days_to_earnings;
  if (ed == null || ed > 7 || ed < 0) {
    body.innerHTML = '';
    // Strip both classes so the section disappears completely — the CSS rule
    // `.sec.fd-active { display: block !important }` would otherwise override
    // any inline display:none we set here.
    body.parentElement.classList.remove('fd-active');
    body.parentElement.style.display = 'none';
    return;
  }
  body.parentElement.style.display = '';
  const sev = ed <= 3 ? 'fail' : ed <= 5 ? 'warn' : 'info';
  const msg = ed === 0 ? 'TODAY' : ed === 1 ? 'TOMORROW' : `IN ${ed} DAYS`;
  const advice = ed <= 3
    ? 'HARD BLACKOUT — earnings binary risk. New entries blocked by gates.'
    : ed <= 5
    ? 'BLACKOUT WINDOW — size below 50% if entering. Consider waiting until after report.'
    : 'Earnings approaching — review consensus and prior surprises in Fundamentals tab.';
  const earnTime = T.earnings?.time || T.earnings_time || '';
  const epsExp = T.earnings?.eps_estimate || T.earnings_eps_estimate;
  body.innerHTML = `
    <div class="earn-banner ${sev}">
      <div class="earn-icon">⚠</div>
      <div class="earn-text">
        <div class="earn-h">EARNINGS ${msg}${earnTime ? ' · ' + earnTime : ''}</div>
        <div class="earn-sub">${advice}${epsExp != null ? ' · EPS est $' + (+epsExp).toFixed(2) : ''}</div>
      </div>
    </div>`;
}

export function dispose() { /* no-op */ }
