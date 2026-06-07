// ai-predict-data.jsx — AI Predictions data layer (REAL, 2026-06-07).
// Replaces the former seeded/synthetic generator. Sources the production model
// board from /api/ai_predict — rows already arrive in this surface's contract:
//   heads  = REAL Direction / Magnitude / Hit-Net components (server _ai_build_heads)
//   cone / horizons / target / stop = REAL, derived from magnitude quantiles
//   feats  = REAL SHAP drivers  ·  analogs = [] (honestly not computed)
//   _model = REAL calibration (score-band → realized WR) + 533k-holdout backtest
// Per-mode projection (swing/position/invest) from /api/ml/{sym}?mode= and the
// resolved-prediction ledger from /api/ml-edge-track. Exposes window.AIPredict
// with the same API the surface + analyst consume — no fabricated values.
(function () {
  var BV = window.__BV;
  function sg(url) { try { return (BV && BV.syncGet) ? BV.syncGet(url) : null; } catch (e) { return null; } }

  // ── board (one blocking fetch at load, like the rest of the prototype) ──
  var DOC = sg("/api/ai_predict?limit=300") || {};
  var ROWS = Array.isArray(DOC.rows) ? DOC.rows : [];
  var MODEL = DOC._model || {};
  var BYSYM = {}; ROWS.forEach(function (r) { if (r && r.sym) BYSYM[r.sym] = r; });

  var BACKTEST = MODEL.backtest || { auc: null, hit: null, n: null, brier: null, horizon: "5d" };

  // calibration: server returns a score-band → outcome dict; map to the
  // {lo,hi,pred,realized,n} shape the calibration scatter expects.
  function parseBand(k) {
    if (k.indexOf("<") === 0) { var hi = +k.slice(1); return [Math.max(0, hi - 20), hi]; }
    if (k.indexOf(">=") === 0) { return [+k.slice(2), 100]; }
    var m = k.split("-"); return [+m[0], +m[1]];
  }
  var CALIB = (function () {
    var c = MODEL.calibration;
    if (!c || typeof c !== "object" || Array.isArray(c)) return [];
    return Object.keys(c).map(function (k) {
      var b = parseBand(k), v = c[k] || {};
      return { lo: b[0] / 100, hi: b[1] / 100, pred: (b[0] + b[1]) / 200, realized: (v.win_rate != null ? v.win_rate : 0) / 100, n: v.n || 0, expectancy: v.expectancy, pf: v.pf };
    }).sort(function (a, z) { return a.pred - z.pred; });
  })();

  // ── per-ticker predict: board row if present, else a real one-off fetch ──
  var _pc = {};
  function predict(sym) {
    if (!sym) return null;
    if (BYSYM[sym]) return BYSYM[sym];
    if (sym in _pc) return _pc[sym];
    var r = sg("/api/ai_predict/" + encodeURIComponent(sym));
    return (_pc[sym] = (r && r.sym) ? r : null);
  }
  function all() { return ROWS; }

  // ── per-mode projection from the real per-ticker model (/api/ml) ──
  var MODE_META = { swing: ["Swing", "5d"], position: ["Position", "21d"], invest: ["Invest", "126d"] };
  var _jc = {};
  function projection(sym, mode) {
    var key = sym + ":" + mode;
    if (key in _jc) return _jc[key];
    var me = sg("/api/ml/" + encodeURIComponent(sym) + "?mode=" + encodeURIComponent(mode));
    if (!me || !me.direction) return (_jc[key] = null);
    var base = predict(sym) || {}; var px = base.px || me.px || 0;
    var mag = me.magnitude || {}, hit = me.hit_net || {}, dir = me.direction || {};
    var pc = function (q) { return +(px * (1 + (q || 0) / 100)).toFixed(2); };
    var entry = px, t1 = pc(mag.q75), t2 = pc(mag.q90), stop = pc(mag.q10), mid = pc(mag.q50);
    var risk = entry - stop, reward = t1 - entry;
    var rr = risk > 0 ? +(reward / risk).toFixed(2) : null;
    var ev = (hit.p_t1_first != null && hit.p_stop_first != null && entry > 0)
      ? +((hit.p_t1_first * (t1 / entry - 1) - hit.p_stop_first * (1 - stop / entry)) * 100).toFixed(2) : null;
    var lab = MODE_META[mode] || MODE_META.swing;
    var v = dir.p_up >= 0.6 ? "BUY" : dir.p_up <= 0.45 ? "AVOID" : "WATCH";
    return (_jc[key] = {
      sym: sym, mode: mode, label: lab[0], horizon: lab[1], hd: me.horizon_days, px: px, entry: entry,
      stop: stop, t1: t1, t2: t2, mid: mid, projLow: pc(mag.q10), projMid: mid, projHigh: pc(mag.q90),
      pUp: dir.p_up, p_chop: dir.p_chop, p_dn: dir.p_dn, ci: null, mag: mag, hit: hit,
      retMid: mag.q50 != null ? +mag.q50.toFixed(1) : 0, rr: rr, ev: ev, verdict: v,
      color: (me.verdict && me.verdict.color) || "ink",
    });
  }

  // adaptive BUY list — same contract; pUp drawn from the real board verdicts.
  function buyList(mode) {
    var pool = ROWS.map(function (p) {
      return { sym: p.sym, name: p.name, pUp: p.pUp, color: (p.verdict === "BUY" ? "bull" : p.verdict === "SELL" ? "bear" : "neutral") };
    });
    var poolMax = pool.length ? Math.max.apply(null, pool.map(function (p) { return p.pUp || 0; })) : 0;
    var defensive = poolMax < 0.55;
    var minPup = defensive ? Math.max(0.45, poolMax - 0.10) : 0.55;
    var picks = pool.filter(function (p) { return (p.pUp || 0) >= minPup; }).sort(function (a, b) { return b.pUp - a.pUp; });
    return { picks: picks, poolMax: +poolMax.toFixed(3), defensive: defensive, minPup: +minPup.toFixed(2) };
  }

  // resolved-prediction ledger — REAL, from /api/ml-edge-track.
  function resolved() {
    var doc = sg("/api/ml-edge-track");
    var arr = (doc && Array.isArray(doc.resolved)) ? doc.resolved : [];
    var now = Date.now();
    return arr.map(function (r) {
      var fwd = (r.realized_pct != null) ? +(+r.realized_pct).toFixed(1) : null;
      var pu = r.p_up != null ? +(+r.p_up).toFixed(2) : null;
      var ageW = null;
      try { ageW = Math.max(1, Math.round((now - new Date(r.scan_date || r.scan_ts).getTime()) / 6048e5)); } catch (e) {}
      var verdict = (r.side === "short") ? "SELL" : (pu != null && pu >= 0.55 ? "BUY" : "HOLD");
      var hit = fwd == null ? null : (verdict === "SELL" ? fwd < 0 : fwd > 0);
      return { sym: r.ticker, ageW: ageW, verdict: verdict, pUp: pu, score: pu != null ? Math.round(50 + (pu - 0.5) * 90) : null, fwd: fwd, hit: hit, exit: r.exit_date };
    }).filter(function (r) { return r.fwd != null; }).sort(function (a, b) { return (a.ageW || 0) - (b.ageW || 0); });
  }

  var FEATURES = (BACKTEST && BACKTEST.feature_cols) || [];

  window.AIPredict = {
    predict: predict, all: all, FEATURES: FEATURES, CALIB: CALIB, BACKTEST: BACKTEST,
    RESOLVED: resolved(), buyList: buyList, projection: projection,
    MODES: ["swing", "position", "invest"], _real: ROWS.length > 0,
  };
})();
