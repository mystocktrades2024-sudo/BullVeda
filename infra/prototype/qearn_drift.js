/* 2026-05-25 · Earnings tab §6 Pre-ER drift bars — computed from
   t.earnings_history dates + t.ohlcv (5d pre-ER return per quarter). */
(function () {
  function paint() {
    var root = document.getElementById('qearn-drift-root');
    if (!root) return;
    var t = window._currentT || {};
    var eh = (t.earnings_history || []).filter(function (x) { return x && x.date; });
    var ohlcv = (t.ohlcv || []);
    if (eh.length < 2 || ohlcv.length < 10) {
      root.innerHTML = '<div style="padding:24px;text-align:center;color:var(--ink-3);font:600 11px var(--mono)">No earnings_history or ohlcv data</div>';
      return;
    }
    // Sort ohlcv ascending by date for binary-search style scan
    var bars = ohlcv.slice().sort(function (a, b) { return (a.d || '') < (b.d || '') ? -1 : 1; });
    function closeAt(date) {
      // Find close on date OR the bar just before (handles weekends/holidays)
      var prev = null;
      for (var i = 0; i < bars.length; i++) {
        var d = bars[i].d || '';
        if (d > date) return prev;
        prev = +bars[i].c;
      }
      return prev;
    }
    function addDays(iso, n) {
      var d = new Date(iso); d.setDate(d.getDate() + n);
      return d.toISOString().slice(0, 10);
    }
    // Use the 8 most-recent earnings dates (oldest first for chronological plot)
    var picks = eh.slice(0, 8).reverse();
    var drifts = picks.map(function (h) {
      var ed = (h.reportDate || h.date || '').slice(0, 10);
      var d5 = addDays(ed, -5);
      var d1 = addDays(ed, -1);
      var c5 = closeAt(d5);
      var c1 = closeAt(d1);
      if (c5 && c1) return { date: ed, drift: ((c1 - c5) / c5) * 100 };
      return { date: ed, drift: null };
    }).filter(function (x) { return x.drift !== null; });
    if (drifts.length < 2) {
      root.innerHTML = '<div style="padding:24px;text-align:center;color:var(--ink-3);font:600 11px var(--mono)">Insufficient OHLCV around earnings dates (need ≥5d pre-ER bars)</div>';
      return;
    }
    var maxAbs = Math.max(4, Math.max.apply(null, drifts.map(function (x) { return Math.abs(x.drift); })));
    var W = 600, H = 160, PAD_L = 40, PAD_R = 20, PAD_T = 20, PAD_B = 30;
    var plotH = H - PAD_T - PAD_B;
    var plotW = W - PAD_L - PAD_R;
    var bw = plotW / Math.max(1, drifts.length) - 8;
    var zeroY = PAD_T + plotH / 2;
    var bars_svg = drifts.map(function (d, i) {
      var cx = PAD_L + (i + 0.5) * (plotW / drifts.length);
      var h = (Math.abs(d.drift) / maxAbs) * (plotH / 2);
      var x = cx - bw / 2;
      var y = d.drift >= 0 ? zeroY - h : zeroY;
      var color = d.drift >= 0 ? '#22c55e' : '#f87171';
      var quarter = (d.date || '').slice(2, 4) + 'Q' + Math.ceil((parseInt((d.date || '').slice(5, 7)) || 0) / 3);
      return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + color + '" opacity="0.85"/>'
        + '<text x="' + cx.toFixed(1) + '" y="' + (d.drift >= 0 ? y - 4 : y + h + 11).toFixed(1) + '" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9" fill="' + color + '" font-weight="700">' + (d.drift >= 0 ? '+' : '') + d.drift.toFixed(1) + '</text>'
        + '<text x="' + cx.toFixed(1) + '" y="' + (PAD_T + plotH + 18) + '" text-anchor="middle" font-family="ui-monospace,monospace" font-size="8" fill="var(--ink-3)">' + quarter + '</text>';
    }).join('');
    var avg = drifts.reduce(function (a, b) { return a + b.drift; }, 0) / drifts.length;
    var positive = drifts.filter(function (x) { return x.drift > 0; }).length;
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto">'
      + '<line x1="' + PAD_L + '" y1="' + zeroY + '" x2="' + (W - PAD_R) + '" y2="' + zeroY + '" stroke="var(--ink-4)" stroke-width="0.6"/>'
      + '<text x="' + (PAD_L - 4) + '" y="' + PAD_T + '" text-anchor="end" font-family="ui-monospace,monospace" font-size="8" fill="var(--ink-3)">+' + maxAbs.toFixed(0) + '%</text>'
      + '<text x="' + (PAD_L - 4) + '" y="' + zeroY + '" text-anchor="end" font-family="ui-monospace,monospace" font-size="8" fill="var(--ink-3)">0%</text>'
      + '<text x="' + (PAD_L - 4) + '" y="' + (PAD_T + plotH) + '" text-anchor="end" font-family="ui-monospace,monospace" font-size="8" fill="var(--ink-3)">-' + maxAbs.toFixed(0) + '%</text>'
      + bars_svg
      + '</svg>';
    var avgCls = avg > 0 ? 'gn' : avg < 0 ? 'rd' : 'am';
    root.innerHTML = svg
      + '<div style="margin-top:10px;font:600 11px var(--mono);color:var(--ink-2);line-height:1.5">'
      + '5-day pre-ER drift across <b>' + drifts.length + '</b> quarters · '
      + '<b class="' + avgCls + '">' + positive + '/' + drifts.length + ' positive</b> · '
      + 'avg <b class="' + avgCls + '">' + (avg >= 0 ? '+' : '') + avg.toFixed(2) + '%</b> · '
      + '<span style="color:var(--ink-3)">computed from t.earnings_history + t.ohlcv</span>'
      + '</div>';
  }
  if (window._qearnDriftInit) return;
  window._qearnDriftInit = true;
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
