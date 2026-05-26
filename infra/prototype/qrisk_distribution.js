/* 2026-05-25 · Risk tab — VaR/CVaR distribution histogram from t.forward_dist
   + Kelly cascade visual from t.kelly_size. Replaces AVGO §1 loss-cone SVG. */
(function () {
  function paint() {
    var root = document.getElementById('qrisk-dist-root');
    if (!root) return;
    var t = window._currentT || {};
    var fd = t.forward_dist || {};
    var ks = t.kelly_size || {};
    var n = fd.n_samples || 0;
    if (n < 100 || fd.var_95_pct == null) {
      root.innerHTML = '<div style="padding:24px;text-align:center;color:var(--ink-3);font:600 11px var(--mono)">No forward-dist data — needs full enrichment + ≥90d history</div>';
      return;
    }
    // Distribution shape from p25/p50/p75 + mean/std — approximate a normal
    // curve for the histogram backdrop, then overlay actual percentiles.
    var p25 = fd.p25_pct, p50 = fd.p50_pct, p75 = fd.p75_pct;
    var mean = fd.mean_pct, std = fd.std_pct || ((p75 - p25) / 1.349);
    var var95 = fd.var_95_pct, cvar = fd.cvar_975_pct;
    // x-axis: span 4 sigma below mean to 4 sigma above
    var xLo = mean - 4 * std, xHi = mean + 4 * std;
    var W = 600, H = 220, PAD_L = 50, PAD_R = 20, PAD_T = 20, PAD_B = 40;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
    function x2px(x) { return PAD_L + (x - xLo) / (xHi - xLo) * plotW; }
    function y2px(y, ymax) { return PAD_T + plotH - (y / ymax) * plotH; }
    // Build normal curve y values
    var nBins = 60;
    var bins = [];
    for (var i = 0; i < nBins; i++) {
      var x = xLo + (i / nBins) * (xHi - xLo);
      var z = (x - mean) / std;
      var pdf = Math.exp(-z * z / 2) / Math.sqrt(2 * Math.PI);
      bins.push({ x: x, y: pdf });
    }
    var ymax = Math.max.apply(null, bins.map(function (b) { return b.y; }));
    // Build SVG path
    var path = '';
    bins.forEach(function (b, i) {
      var px = x2px(b.x);
      var py = y2px(b.y, ymax);
      path += (i === 0 ? 'M ' : 'L ') + px.toFixed(1) + ' ' + py.toFixed(1) + ' ';
    });
    // Fill area
    var fillPath = path + 'L ' + x2px(xHi).toFixed(1) + ' ' + (PAD_T + plotH).toFixed(1)
      + ' L ' + x2px(xLo).toFixed(1) + ' ' + (PAD_T + plotH).toFixed(1) + ' Z';
    // Shaded tail (loss region — left of VaR)
    var tailPts = bins.filter(function (b) { return b.x <= var95; });
    var tailPath = '';
    tailPts.forEach(function (b, i) {
      var px = x2px(b.x);
      var py = y2px(b.y, ymax);
      tailPath += (i === 0 ? 'M ' : 'L ') + px.toFixed(1) + ' ' + py.toFixed(1) + ' ';
    });
    if (tailPts.length > 0) {
      tailPath += 'L ' + x2px(var95).toFixed(1) + ' ' + (PAD_T + plotH).toFixed(1)
        + ' L ' + x2px(xLo).toFixed(1) + ' ' + (PAD_T + plotH).toFixed(1) + ' Z';
    }
    // Vertical lines for key levels
    function vLine(x, color, label) {
      var px = x2px(x);
      return '<line x1="' + px + '" y1="' + PAD_T + '" x2="' + px + '" y2="' + (PAD_T + plotH) + '" stroke="' + color + '" stroke-width="1.5" stroke-dasharray="3 2"/>'
        + '<text x="' + px + '" y="' + (PAD_T - 4) + '" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9" fill="' + color + '" font-weight="800">' + label + ' ' + (x >= 0 ? '+' : '') + x.toFixed(1) + '%</text>';
    }
    // x-axis ticks
    var ticks = '';
    for (var i = 0; i <= 8; i++) {
      var x = xLo + (i / 8) * (xHi - xLo);
      var px = x2px(x);
      ticks += '<line x1="' + px + '" y1="' + (PAD_T + plotH) + '" x2="' + px + '" y2="' + (PAD_T + plotH + 4) + '" stroke="var(--ink-4)"/>'
        + '<text x="' + px + '" y="' + (PAD_T + plotH + 16) + '" text-anchor="middle" font-family="ui-monospace,monospace" font-size="9" fill="var(--ink-3)">' + (x >= 0 ? '+' : '') + x.toFixed(0) + '%</text>';
    }
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto">'
      + '<defs><linearGradient id="distFill" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0%" stop-color="rgba(96,165,250,0.45)"/>'
      + '<stop offset="100%" stop-color="rgba(96,165,250,0.05)"/></linearGradient></defs>'
      + '<path d="' + fillPath + '" fill="url(#distFill)" stroke="#60a5fa" stroke-width="1.5"/>'
      + (tailPath ? '<path d="' + tailPath + '" fill="rgba(248,113,113,0.30)" stroke="#f87171" stroke-width="1.2"/>' : '')
      + vLine(mean, '#9a9e98', 'μ')
      + vLine(var95, '#f87171', 'VaR 95%')
      + (cvar != null ? vLine(cvar, '#dc2626', 'CVaR 97.5%') : '')
      + ticks
      + '<text x="' + (PAD_L) + '" y="' + (H - 6) + '" font-family="ui-monospace,monospace" font-size="9" fill="var(--ink-3)" letter-spacing="0.06em">FORWARD-DISTRIBUTION · ' + n + ' Monte Carlo paths · 63d horizon</text>'
      + '</svg>';
    root.innerHTML = svg
      + '<div style="margin-top:10px;font:600 11px var(--mono);color:var(--ink-2);line-height:1.5">'
      + 'Tail loss (red shaded): worst-case <b>' + var95.toFixed(1) + '%</b> at 95% confidence · '
      + 'beyond-tail expected loss CVaR <b style="color:var(--rd)">' + (cvar != null ? cvar.toFixed(1) + '%' : '—') + '</b> · '
      + 'mode return <b style="color:var(--ink)">' + (mean >= 0 ? '+' : '') + mean.toFixed(1) + '%</b> · '
      + 'P(profit) <b class="' + (fd.p_profit >= 55 ? 'gn' : fd.p_profit >= 45 ? 'am' : 'rd') + '">' + (fd.p_profit != null ? fd.p_profit.toFixed(0) + '%' : '—') + '</b>'
      + '</div>';
  }
  // Repaint on every tab render (read _currentT lazily)
  if (window._qriskDistInit) return;
  window._qriskDistInit = true;
  var _qrPrev = null;
  setInterval(function () {
    var t = window._currentT || {};
    var sig = (t.ticker || '') + '|' + (t._enriched ? '1' : '0');
    if (sig === _qrPrev) return;
    _qrPrev = sig;
    paint();
  }, 500);
  // Initial paint
  paint();
})();
