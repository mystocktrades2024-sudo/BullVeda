/* 2026-05-25 · Options Flow projection-accuracy block.
   Injected into the Options tab render. Fetches /api/options-flow-accuracy
   on first display, renders WR / PF / MFE / MAE + per-STATUS breakdown. */
(function () {
  if (window._qoptAccLoaded) return;
  window._qoptAccLoaded = true;
  fetch('/api/options-flow-accuracy?window_days=90', { credentials: 'include' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      var el = document.getElementById('qopt-accuracy-body');
      if (!el) return;
      if (!d || !d.resolved) {
        var ht = d ? d.history_total : 0, op = d ? d.open_count : 0;
        el.innerHTML = '<span style="color:var(--ink-3)">📊 <b>' + ht
          + '</b> picks logged · <b>' + op + '</b> still open · '
          + ((d && d.message) || 'history accumulating') + '</span>';
        return;
      }
      var wrCls = d.win_rate_pct >= 55 ? 'gn' : d.win_rate_pct >= 45 ? 'am' : 'rd';
      var pfCls = d.profit_factor >= 1.5 ? 'gn' : d.profit_factor >= 1 ? 'am' : 'rd';
      var h = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:10px">'
        + '<div><div style="color:var(--ink-3);font-size:9.5px;letter-spacing:0.10em;margin-bottom:4px">RESOLVED</div><div style="font-size:17px;font-weight:800;color:var(--ink)">' + d.resolved + '</div></div>'
        + '<div><div style="color:var(--ink-3);font-size:9.5px;letter-spacing:0.10em;margin-bottom:4px">WIN RATE</div><div class="' + wrCls + '" style="font-size:17px;font-weight:800">' + (d.win_rate_pct != null ? d.win_rate_pct.toFixed(0) + '%' : '—') + '</div></div>'
        + '<div><div style="color:var(--ink-3);font-size:9.5px;letter-spacing:0.10em;margin-bottom:4px">PF</div><div class="' + pfCls + '" style="font-size:17px;font-weight:800">' + (d.profit_factor != null ? d.profit_factor.toFixed(2) : '—') + '</div></div>'
        + '<div><div style="color:var(--ink-3);font-size:9.5px;letter-spacing:0.10em;margin-bottom:4px">AVG MFE</div><div class="gn" style="font-size:17px;font-weight:800">+' + (d.avg_mfe_pct || 0).toFixed(1) + '%</div></div>'
        + '<div><div style="color:var(--ink-3);font-size:9.5px;letter-spacing:0.10em;margin-bottom:4px">AVG MAE</div><div class="rd" style="font-size:17px;font-weight:800">' + (d.avg_mae_pct || 0).toFixed(1) + '%</div></div>'
        + '</div>'
        + '<div style="font:600 10px var(--mono);color:var(--ink-2);margin-bottom:10px">🎯 <b class="gn">'
        + d.target_hit + ' target hit</b> · 🛑 <b class="rd">' + d.stop_hit
        + ' stop hit</b> · ⏱ <b class="am">' + d.expired + ' expired</b> · '
        + d.open_count + ' open · ' + d.window_days + 'd window</div>';
      var ps = d.per_status || {};
      var rows = Object.keys(ps).map(function (k) {
        var s = ps[k];
        var wr = s.n > 0 ? (s.wins / s.n * 100).toFixed(0) : '—';
        return '<div style="display:grid;grid-template-columns:90px 60px 60px 60px 60px;gap:8px;padding:5px 0;border-bottom:1px dashed var(--line)">'
          + '<span style="color:var(--ink-1);font-weight:700">' + k + '</span>'
          + '<span style="text-align:right;color:var(--ink-2)">n=' + s.n + '</span>'
          + '<span class="gn" style="text-align:right">🎯 ' + s.wins + '</span>'
          + '<span class="rd" style="text-align:right">🛑 ' + s.stops + '</span>'
          + '<span style="text-align:right;color:var(--ink);font-weight:700">' + wr + '%</span>'
          + '</div>';
      }).join('');
      if (rows) {
        h += '<div style="font:800 10px var(--mono);color:var(--ink-3);letter-spacing:0.14em;margin:10px 0 6px">PER-STATUS BREAKDOWN</div>'
          + '<div style="display:grid;grid-template-columns:90px 60px 60px 60px 60px;gap:8px;padding:0 0 4px;border-bottom:1px solid var(--line);font:700 9px var(--mono);color:var(--ink-3);letter-spacing:0.10em">'
          + '<span>Status</span><span style="text-align:right">N</span>'
          + '<span style="text-align:right">Wins</span><span style="text-align:right">Stops</span>'
          + '<span style="text-align:right">WR</span></div>'
          + rows;
      }
      el.innerHTML = h;
    })
    .catch(function (e) {
      var el = document.getElementById('qopt-accuracy-body');
      if (el) el.innerHTML = '<span class="rd">accuracy load failed</span>';
    });
})();
