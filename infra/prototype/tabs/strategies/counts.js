// tabs/strategies/counts.js — Setup-distribution + verdict-distribution bars.
// Owns DOM: #setupCountsBody and #verdictCountsBody.

export function renderCountsPanels(setupCounts, verdictCounts) {
  const sc       = setupCounts   || {};
  const vc       = verdictCounts || {};
  const total    = Object.values(sc).reduce((a, b) => a + b, 0) || 1;
  const totalV   = Object.values(vc).reduce((a, b) => a + b, 0) || 1;
  const setups   = Object.entries(sc).sort((a, b) => b[1] - a[1]);
  const verdicts = Object.entries(vc).sort((a, b) => b[1] - a[1]);

  const setupBody = document.getElementById('setupCountsBody');
  if (setupBody) {
    setupBody.innerHTML = setups.map(([k, v]) => `
      <div class="hc-row" style="grid-template-columns:1fr 1fr 50px 60px">
        <div style="font-size:12px">${k}</div>
        <div class="hc-bar"><div class="hc-bar-fill" style="width:${v/total*100}%;background:var(--accent)"></div></div>
        <div class="hc-pct">${v}</div>
        <div class="hc-pct" style="color:var(--ink-3);font-size:10.5px">${(v/total*100).toFixed(1)}%</div>
      </div>
    `).join('');
  }

  const verdictBody = document.getElementById('verdictCountsBody');
  if (verdictBody) {
    verdictBody.innerHTML = verdicts.map(([k, v]) => `
      <div class="hc-row" style="grid-template-columns:1fr 1fr 50px 60px">
        <div style="font-size:12px;color:${k==='BUY'?'var(--green)':k==='WATCH'?'var(--accent)':k==='SHORT'?'var(--red)':'var(--ink-2)'};font-weight:700">${k}</div>
        <div class="hc-bar"><div class="hc-bar-fill" style="width:${v/totalV*100}%;background:${k==='BUY'?'var(--green)':k==='WATCH'?'var(--accent)':k==='SHORT'?'var(--red)':'var(--ink-3)'}"></div></div>
        <div class="hc-pct">${v}</div>
        <div class="hc-pct" style="color:var(--ink-3);font-size:10.5px">${(v/totalV*100).toFixed(1)}%</div>
      </div>
    `).join('');
  }
}
