/* 2026-05-25 · Earnings §8 IV Crush — wire from per-ticker iv_history.
   Fetches /api/iv-history?t=TKR&days=60, plots IV ramp + projected crush. */
(function () {
  function paint() {
    var root = document.getElementById('qearn-iv-root');
    if (!root) return;
    var t = window._currentT || {};
    var tk = (t.ticker || t.symbol || '').toString().toUpperCase();
    if (!tk) {
      root.innerHTML = '<div style="padding:24px;text-align:center;color:var(--ink-3);font:600 11px var(--mono)">No ticker</div>';
      return;
    }
    root.dataset.tk = tk;
    fetch('/api/iv-history?t=' + encodeURIComponent(tk) + '&days=90', { credentials: 'include' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        // Bail if user switched ticker
        if (root.dataset.tk !== tk) return;
        if (!d || !d.points || d.points.length < 5) {
          root.innerHTML = '<div style="padding:24px;text-align:center;color:var(--ink-3);font:600 11px var(--mono)">No IV history for ' + tk + ' (need ≥5 daily points)</div>';
          return;
        }
        var pts = d.points;  // [{date, iv}]
        var current = +pts[pts.length - 1].iv || 0;
        // Compute percentile rank
        var sorted = pts.map(function (p) { return +p.iv; }).filter(function (x) { return x > 0; }).sort(function (a, b) { return a - b; });
        var rank = sorted.indexOf(current);
        var ivPctile = sorted.length > 1 ? (rank / (sorted.length - 1) * 100) : 50;
        // Detect ramps (date sequence where iv climbed >20% over 7 days = pre-ER ramp)
        var W = 600, H = 200, PAD_L = 40, PAD_R = 20, PAD_T = 20, PAD_B = 30;
        var plotH = H - PAD_T - PAD_B, plotW = W - PAD_L - PAD_R;
        var minIv = Math.min.apply(null, pts.map(function (p) { return +p.iv; }));
        var maxIv = Math.max.apply(null, pts.map(function (p) { return +p.iv; }));
        var rangeIv = maxIv - minIv || 1;
        var path = '';
        pts.forEach(function (p, i) {
          var x = PAD_L + (i / (pts.length - 1)) * plotW;
          var y = PAD_T + plotH - ((+p.iv - minIv) / rangeIv) * plotH;
          path += (i === 0 ? 'M ' : 'L ') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
        });
        // Today marker
        var lastX = PAD_L + plotW;
        var lastY = PAD_T + plotH - ((current - minIv) / rangeIv) * plotH;
        // Crush projection — if IV is high (>60th pctile) AND earnings within 14d, project -30pp
        var erDays = (t.earn_days != null) ? +t.earn_days : null;
        var crushArrow = '';
        if (erDays != null && erDays >= 0 && erDays <= 14 && ivPctile >= 60) {
          // Estimate post-crush IV at 30% of current
          var crushY = PAD_T + plotH - ((current * 0.7 - minIv) / rangeIv) * plotH;
          crushArrow = '<line x1="' + lastX + '" y1="' + lastY + '" x2="' + lastX + '" y2="' + crushY + '" stroke="#f87171" stroke-width="2" stroke-dasharray="4 3" marker-end="url(#crushArr)"/>'
            + '<text x="' + (lastX - 6) + '" y="' + crushY + '" text-anchor="end" font-family="ui-monospace,monospace" font-size="9" fill="#f87171" font-weight="800">~ -30%</text>';
        }
        var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto">'
          + '<defs><marker id="crushArr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#f87171"/></marker></defs>'
          + '<path d="' + path + '" fill="none" stroke="#fbbf24" stroke-width="1.8"/>'
          + '<circle cx="' + lastX + '" cy="' + lastY + '" r="4" fill="#d97757"/>'
          + crushArrow
          + '<text x="' + (lastX + 6) + '" y="' + (lastY + 4) + '" font-family="ui-monospace,monospace" font-size="9" fill="#d97757" font-weight="700">TODAY · ' + current.toFixed(1) + '%</text>'
          + '<line x1="' + PAD_L + '" y1="' + (PAD_T + plotH) + '" x2="' + (W - PAD_R) + '" y2="' + (PAD_T + plotH) + '" stroke="var(--ink-4)"/>'
          + '<text x="' + PAD_L + '" y="' + (PAD_T - 6) + '" font-family="ui-monospace,monospace" font-size="9" fill="var(--ink-3)" letter-spacing="0.06em">' + tk + ' IV — last ' + pts.length + ' sessions</text>'
          + '</svg>';
        var pctileCls = ivPctile >= 70 ? 'rd' : ivPctile >= 30 ? 'am' : 'gn';
        root.innerHTML = svg
          + '<div style="margin-top:10px;font:600 11px var(--mono);color:var(--ink-2);line-height:1.5">'
          + 'Current IV: <b style="color:var(--ink)">' + current.toFixed(2) + '%</b> · '
          + 'IV Rank (window): <b class="' + pctileCls + '">' + ivPctile.toFixed(0) + 'th pctile</b> · '
          + 'range: ' + minIv.toFixed(1) + ' – ' + maxIv.toFixed(1) + '% · '
          + (erDays != null ? 'ER in <b>' + erDays + 'd</b> · ' : '')
          + (crushArrow ? '<b class="rd">projected ~30% crush at print</b>' : '<span style="color:var(--ink-3)">no near-term ER · no crush projection</span>')
          + '</div>';
      })
      .catch(function (e) {
        root.innerHTML = '<div style="color:var(--rd);padding:14px;font:600 11px var(--mono)">IV history fetch failed: ' + e.message + '</div>';
      });
  }
  if (window._qearnIvInit) return;
  window._qearnIvInit = true;
  var _prev = null;
  setInterval(function () {
    var t = window._currentT || {};
    var sig = (t.ticker || '') + '|' + (t._enriched ? '1' : '0');
    if (sig === _prev) return;
    _prev = sig;
    paint();
  }, 500);
  paint();
})();
