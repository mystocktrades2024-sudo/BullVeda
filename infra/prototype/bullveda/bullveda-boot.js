/* bullveda-boot.js — REAL-DATA bootstrap for BullVeda terminal.
 *
 * Loads BEFORE every Babel module (plain synchronous <script>). It performs a
 * blocking same-origin XHR to /api/universe so the prototype's data modules
 * (data.jsx, surface-signal.jsx, …) see REAL rows at module-eval time and their
 * derived universes become real automatically — no mock seed, no hardcoded data.
 *
 * The mapping from a raw /api/universe row → the prototype's scanner-row contract
 * lives here (window.__BV.scanRow). This is the handover's "single data adapter":
 * one place shapes live feeds into the exact object contracts the components read.
 *
 * Feed-honest: fields with no real per-row source (ATR, days-to-cover, the
 * Wilson-LB / n / pf / regime-WR ledger stats) are set null → cells render "—".
 */
(function () {
  "use strict";
  var BV = (window.__BV = window.__BV || {});
  BV.ready = false;
  BV.errors = [];
  if (/bvdebug=1/.test(location.search)) {
    window.addEventListener("error", function (ev) {
      try { console.log("[BV-ERR]", ev.message, "@", ev.filename, (ev.lineno || "?") + ":" + (ev.colno || "?")); } catch (e) {}
    }, true);
  }

  function syncGet(url) {
    try {
      var x = new XMLHttpRequest();
      x.open("GET", url, false); // synchronous — completes before later <script>s run
      x.send(null);
      if (x.status >= 200 && x.status < 300) return JSON.parse(x.responseText);
      BV.errors.push(url + " → " + x.status);
    } catch (e) {
      BV.errors.push(url + " → " + (e && e.message));
    }
    return null;
  }
  BV.syncGet = syncGet;
  // async GET (post-mount enrichment: per-ticker, portfolio, …)
  BV.get = function (url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(url + " → " + r.status);
      return r.json();
    });
  };

  // ── Pattern engines (real, per-ticker, mode-aware) — Patterns lens ──
  // Generic cached fetch of /api/pattern/{engine}/{sym}?mode=. The React hook
  // (usePatternModel in patterns-core) reads the cache synchronously and falls
  // back to each theory's illustrative fixture until the real payload resolves
  // (and when the server is absent, e.g. the standalone dev showcase). Cache key
  // is engine|sym|MODE so SWING/POSITION/INVEST each cache independently.
  BV.patternCache = {};
  BV.fetchPattern = function (engine, sym, mode) {
    engine = (engine || "").toLowerCase();
    sym = (sym || "").toUpperCase();
    mode = (mode || "SWING").toUpperCase();
    if (!engine || !sym) return Promise.resolve(null);
    var key = engine + "|" + sym + "|" + mode;
    if (BV.patternCache[key]) return Promise.resolve(BV.patternCache[key]);
    return BV.get("/api/pattern/" + encodeURIComponent(engine) + "/" + encodeURIComponent(sym) + "?mode=" + encodeURIComponent(mode))
      .then(function (d) { BV.patternCache[key] = d; return d; })
      .catch(function () { return null; });
  };
  BV.patternCached = function (engine, sym, mode) {
    var key = (engine || "").toLowerCase() + "|" + (sym || "").toUpperCase() + "|" + (mode || "SWING").toUpperCase();
    return BV.patternCache[key] || null;
  };
  // back-compat (Wyckoff-only callers)
  BV.wyckCache = BV.patternCache;
  BV.fetchWyckoff = function (sym, mode) { return BV.fetchPattern("wyckoff", sym, mode); };

  // ── sector normaliser: real GICS sector → prototype short bucket ──
  var SECMAP = {
    "Technology": "Tech", "Information Technology": "Tech",
    "Financial Services": "Finance", "Financials": "Finance", "Finance": "Finance",
    "Healthcare": "Healthcare", "Health Care": "Healthcare",
    "Basic Materials": "Materials", "Materials": "Materials",
    "Energy": "Energy",
    "Consumer Cyclical": "Consumer", "Consumer Defensive": "Consumer",
    "Consumer Discretionary": "Consumer", "Consumer Staples": "Consumer",
    "Industrials": "Industrials",
    "Communication Services": "Comm", "Communication": "Comm",
    "Real Estate": "REIT",
    "Utilities": "Utilities",
    "Unknown": "Other", "": "Other",
  };
  BV.normSector = function (s) { return SECMAP[s] || s || "Other"; };

  // ── verdict (stage) normaliser → BUY / WATCH / AVOID / SHORT ──
  BV.verdict = function (stage) {
    var s = (stage || "").toUpperCase();
    if (s === "WAIT") return "WATCH";
    if (s === "SELL") return "AVOID";
    return s || "WATCH";
  };

  var GR = function (n) { return n >= 82 ? "A" : n >= 66 ? "B" : n >= 46 ? "C" : n >= 30 ? "D" : "F"; };
  var GNUM = { A: 90, B: 72, C: 55, D: 38, F: 20 };
  var clamp = function (n, lo, hi) { return Math.max(lo, Math.min(hi, n)); };
  var num = function (v, d) { return (typeof v === "number" && isFinite(v)) ? v : (d === undefined ? null : d); };

  // ── raw /api/universe row → scanner-row contract (matches surface-signal SS_UNIVERSE) ──
  BV.scanRow = function (r) {
    var price = num(r.price, 0) || 0;
    var score = num(r.score, 0) || 0;
    var rr = num(r.rr, 0) || 0;
    var rvol = num(r.rvol);
    var verdict = BV.verdict(r.stage);
    // pillar component ratios (real)
    var techMax = num(r.tech_max, 38) || 38, fundMax = num(r.fund_max, 30) || 30,
        smcMax = num(r.smc_max, 15) || 15, sentMax = num(r.sent_max, 10) || 10;
    var techPct = clamp((num(r.tech_score, 0) / techMax) * 100, 0, 100);
    var fundPct = clamp((num(r.fund_score, 0) / fundMax) * 100, 0, 100);
    var smcPct = clamp((num(r.smc_score, 0) / smcMax) * 100, 0, 100);
    var sentPct = clamp((num(r.sent_score, 0) / sentMax) * 100, 0, 100);
    // tfsn pass(2)/neutral(1)/fail(0) from real pillar ratios — [tech, fund, smc, sent]
    var lvl = function (p) { return p >= 66 ? 2 : p >= 40 ? 1 : 0; };
    var tfsn = [lvl(techPct), lvl(fundPct), lvl(smcPct), lvl(sentPct)];
    // multi-timeframe proxy from real indicator booleans
    var mtf = [
      r.above_50ema ? "up" : "down",
      r.above_200sma ? "up" : "down",
      (r.macd_signal === "bullish" || r.macd_signal === true) ? "up" : (r.macd_signal === "bearish" ? "down" : "flat"),
      num(r.rsi, 50) >= 55 ? "up" : num(r.rsi, 50) <= 45 ? "down" : "flat",
    ];
    // EDGE factor grades (A–F) — value/growth from real letter grades, rest derived from real pillar scores
    var gT = techPct, gM = clamp(((num(r.rsi, 50) - 30) / 50) * 60 + (num(r.adx, 15) / 78) * 40, 4, 99),
        gS = clamp(score, 4, 99), gR = clamp((rr / 4) * 100, 4, 99);
    var vLetter = r.grade_value || GR(clamp(50 + (fundPct - 50), 4, 99));
    var gLetter = r.grade_growth || GR(clamp(50 + (num(r.perf_3m, 0) || 0) * 2, 4, 99));
    var gNumV = { t: gT, m: gM, s: gS, r: gR, v: GNUM[vLetter] || 50, g: GNUM[gLetter] || 50 };
    var eW = { s: 1.4, t: 1.3, m: 1.2, r: 1.0, v: 0.6, g: 0.6 };
    var edgePct = clamp(Object.keys(eW).reduce(function (a, k) { return a + gNumV[k] * eW[k]; }, 0) /
      Object.values(eW).reduce(function (a, b) { return a + b; }, 0), 4, 99);
    var grades = { t: GR(gT), m: GR(gM), s: GR(gS), r: GR(gR), v: vLetter, g: gLetter };
    // entry-gate "ready" count (real thresholds)
    var rs = num(r.rs_rank, 0) || 0;
    var ready = [score >= 66, rr >= 2, (rvol || 0) >= 1.3, rs >= 45,
                 num(r.rsi, 0) >= 45, (num(r.earn_days, 99) || 99) > 14].filter(Boolean).length;
    var off52 = (r.week52_high && price) ? ((price - r.week52_high) / r.week52_high) * 100 : null;
    var vwapPct = (r.vwap20 && price) ? ((price - r.vwap20) / r.vwap20) * 100 : null;
    // squeeze_flag.level is "low"/"medium"/"high" (compression tier) OR "ON"/"FIRED"
    // on some rows — map both vocabularies to a rank so the Squeeze group surfaces.
    var squeeze = (r.squeeze || "OFF");
    var _sqU = String(squeeze).toUpperCase();
    var sqRank = (_sqU === "FIRED" || _sqU === "HIGH") ? 3
               : (_sqU === "ON" || _sqU.indexOf("MED") === 0) ? 2
               : (_sqU === "LOW") ? 1 : 0;
    var signals = [];
    if ((rvol || 0) >= 1.5) signals.push("🔥");
    if (r.catalyst_tier === 1 || squeeze === "FIRED") signals.push("⚡");
    if (!signals.length) signals.push(verdict === "BUY" ? "⚡" : "🔥");

    return {
      sym: r.ticker, name: r.name || r.ticker,
      sector: BV.normSector(r.sector), industry: r.industry || "",
      mcap: (num(r.market_cap, 0) || 0) / 1e9,
      price: price, chg: num(r.pct_chg, 0),
      score: Math.round(score), verdict: verdict, setup: r.setup || "",
      tfsn: tfsn, tfsnScore: tfsn.reduce(function (a, b) { return a + b; }, 0),
      mtf: mtf, mtfUp: mtf.filter(function (m) { return m === "up"; }).length,
      sigCount: signals.length, signals: signals,
      sqRank: sqRank, squeeze: squeeze, ready: ready,
      mechanism: r.setup ? r.setup + (r.reject_reason ? " · " + r.reject_reason : "") : (r.reject_reason || "—"),
      tier: r.conviction_tier || "—", eq: r.entry_quality || "—",
      cat: r.catalyst_tier != null ? "T" + r.catalyst_tier : "—",
      stop: num(r.stop) != null ? r.stop.toFixed(2) : "—",
      entry: num(r.entry_lo) != null ? r.entry_lo.toFixed(2) : "—",
      t1plan: num(r.t1) != null ? r.t1.toFixed(2) : "—",
      t2plan: num(r.t2) != null ? r.t2.toFixed(2) : "—",
      atr: null, // not in scan feed → feed-honest "—"
      rr: rr ? rr.toFixed(1) : "—",
      rvol: rvol != null ? rvol.toFixed(2) : "—",
      rs: rs ? rs.toFixed(0) : "—",
      wlb: null, n: null, pf: null, regWR: null, // ledger-derived (🔶) → feed-honest
      iv: num(r.iv_rank),
      sent: Math.round(num(r.sent_score, 5) - 5),
      er: num(r.earn_days),
      aiEdge: num(r.p_up) != null ? +(r.p_up - 0.5).toFixed(2) : null,
      grades: grades, gradesRaw: gNumV, edge: GR(edgePct), edgePct: Math.round(edgePct),
      vgm: { v: grades.v, g: grades.g, m: grades.m },
      adx: num(r.adx) != null ? Math.round(r.adx) : null,
      beta: num(r.beta) != null ? +r.beta.toFixed(2) : null,
      dvol: (price && num(r.avg_volume)) ? price * r.avg_volume : null,
      si: num(r.short_float),
      dtc: null, // days-to-cover not in feed
      spread: num(r.spread_pct) != null ? +r.spread_pct.toFixed(2) : null,
      off52: off52 != null ? +off52.toFixed(1) : null,
      vwap: vwapPct != null ? +vwapPct.toFixed(2) : null,
      r1m: num(r.perf_month), r3m: num(r.perf_3m),
      tgt: (num(r.t1) != null && price) ? Math.round(((r.t1 - price) / price) * 100) : null,
      newsAge: num(r.news_age_h) != null ? Math.round(r.news_age_h) : null,
      insUsd: num(r.insider_usd) ? +(r.insider_usd / 1e6).toFixed(1) : 0,
      insNet: num(r.insider_net, 0),
      star: num(r.star_rating),
      sharpe: num(r.sharpe_126d),
      pillarPct: { technical: techPct, fundamental: fundPct, smc: smcPct, sentiment: sentPct },
      _raw: r,
    };
  };

  // ── scanner-row → full per-ticker detail contract (data.jsx TICKER shape) ──
  // Reused by the featured ticker and the scan-column click handler. Deep fields
  // not present in the scan feed (ml magnitude cone, Wilson setup stats) are left
  // null and enriched asynchronously from /api/ml + /api/ticker after click.
  // Wilson 95% lower bound (client-side, real — Agresti-Coull form)
  function wilsonLB(p, n) {
    if (!n || p == null) return null;
    var z = 1.96, z2 = z * z;
    return (p + z2 / (2 * n) - z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n);
  }

  // sr = scanRow, fund = /api/fundamentals, ml = /api/ml, sb = /api/setup-backtest
  BV.detailFor = function (sr, fund, ml, sb) {
    if (!sr) return null;
    var r = sr._raw || {};
    var H = (fund && fund.highlights) || {}, V = (fund && fund.valuation) || {}, S = (fund && fund.shares) || {};
    var entry = num(r.entry_lo, sr.price);
    var pUp = (ml && ml.direction && num(ml.direction.p_up) != null) ? ml.direction.p_up : num(r.p_up);
    var mag = (ml && ml.magnitude) || null;
    var hit = (ml && ml.hit_net) || null;
    // setup track-record (real) — prefer setup_family_stats (has Wilson CI), else /api/setup-backtest
    var ss;
    var fam = BV.setupStatsBy && BV.setupStatsBy[sr.setup];
    if (fam && num(fam.trades)) {
      ss = { n: fam.trades, winRate: num(fam.win_rate), wilsonLB: num(fam.wr_low_95),
        pf: num(fam.profit_factor), medianR: num(fam.avg_r), reliability: fam.reliability };
    } else if (sb && num(sb.n)) {
      var wr = num(sb.winRate);
      ss = { n: sb.n, winRate: wr, wilsonLB: wilsonLB(wr, sb.n), pf: num(sb.pf), medianR: num(sb.avgR) };
    } else {
      ss = { n: null, winRate: null, wilsonLB: null, pf: null, medianR: null }; // feed-honest
    }
    var divY = num(H.DividendYield);
    return {
      symbol: sr.sym, name: (fund && fund.name) || sr.name, exchange: r.exchange || "",
      // Engine's authoritative per-mode verdict (audit #6) — so the composite verdict
      // renders the REAL swing/position/invest call, not a client recompute.
      decisionsByMode: r.decisions_by_mode || null,
      sector: sr.sector, industry: (fund && fund.industry) || sr.industry,
      mcap: num(H.MarketCapitalization) || (sr.mcap || 0) * 1e9,
      price: sr.price, chg: sr.chg, chgAbs: +(sr.price * (sr.chg / 100)).toFixed(2),
      prev: +(sr.price / (1 + sr.chg / 100)).toFixed(2),
      vol: num(r.avg_volume), avgVol: num(r.avg_volume),
      rsi: num(r.rsi),
      beta: num(H.Beta) != null ? +num(H.Beta).toFixed(2) : (sr.beta != null ? sr.beta : 1.0),
      shortFloat: num(S.ShortPercentFloat) != null ? +(S.ShortPercentFloat * 100).toFixed(1) : (sr.si != null ? sr.si : 0),
      insiderOwn: num(S.PercentInsiders) != null ? +num(S.PercentInsiders).toFixed(1) : 0,
      instOwn: num(S.PercentInstitutions),
      pe: num(H.PERatio) != null ? num(H.PERatio) : num(V.TrailingPE),
      fwdPe: num(V.ForwardPE),
      divYield: divY != null ? +(divY * 100).toFixed(2) : 0,
      ps: num(V.PriceSalesTTM), pb: num(V.PriceBookMRQ),
      profitMargin: num(H.ProfitMargin), roe: num(H.ReturnOnEquityTTM),
      revGrowth: num(H.QuarterlyRevenueGrowthYOY), targetPrice: num(H.WallStreetTargetPrice),
      earnings: { days: sr.er, date: "" },
      setupFamily: sr.setup, pivot: entry, stop: num(r.stop, 0) || 0, t1: num(r.t1, 0) || 0, t2: num(r.t2, 0) || 0,
      trail: "ATR(14)-based", holdDays: ({ "Impulse Catalyst": 6, "Breakout Expansion": 14, "Trend Continuation": 14, "Special Situation": 10 })[sr.setup] || 10,
      rMultiple: num(r.rr, 0) || 0,
      pillars: {
        technical: Math.round(sr.pillarPct.technical),
        fundamental: Math.round(sr.pillarPct.fundamental),
        catalyst: r.catalyst_tier === 1 ? 80 : r.catalyst_tier === 2 ? 60 : 40,
        risk: Math.round(clamp((num(r.rr, 0) / 4) * 100, 0, 100)),
        edge: sr.edgePct,
      },
      verdict: sr.verdict, score: sr.score,
      ml: {
        direction: pUp != null ? pUp : 0.5,
        hitNet: hit ? +((num(hit.p_t1_first, 0)) - (num(hit.p_stop_first, 0))).toFixed(2)
          : (pUp != null ? +(pUp - (1 - pUp)).toFixed(2) : 0),
        magnitude: mag ? { lo: +num(mag.q10, 0).toFixed(1), mid: +num(mag.q50, 0).toFixed(1), hi: +num(mag.q90, 0).toFixed(1) }
          : { lo: 0, mid: 0, hi: 0 },
      },
      setupStats: ss,
      holders: (fund && fund.holders_institutions) || null,
      insiderTx: (fund && fund.insider_transactions) || null,
      _scan: sr, _fund: fund || null, _ml: ml || null,
    };
  };

  // Synchronous click-time enrichment: fundamentals + ml + setup-backtest, all real.
  BV.detailSync = function (sym) {
    var sr = BV.findRow(sym);
    if (!sr) return null;
    var enc = encodeURIComponent(sym);
    var fund = syncGet("/api/fundamentals/" + enc);
    var ml = syncGet("/api/ml/" + enc);
    return BV.detailFor(sr, fund, ml, null); // setup stats come from setup_family_stats (real, preloaded)
  };

  // ── light per-row Time Anatomy lookup (for the scanner TIME column / HOLD badge) ──
  // Direct cell + 1-level collapse only (O(1)-ish) so it's cheap across ~1000 rows.
  BV._tqCache = {};
  BV.timeQuick = function (sr) {
    var TT = BV.timeTable; if (!TT || !TT.cells || !sr) return null; // deferred → null until loaded
    if (BV._tqCache[sr.sym] !== undefined) return BV._tqCache[sr.sym];
    var _r = BV._timeQuickCompute(sr); BV._tqCache[sr.sym] = _r; return _r;
  };
  BV._timeQuickCompute = function (sr) {
    var TT = BV.timeTable;
    var r = sr._raw || {};
    var entry = num(r.entry_lo, sr.price), stop = num(r.stop), t1 = num(r.t1);
    if (entry == null || stop == null || t1 == null || entry <= stop || t1 <= entry) return null;
    var ATR = (entry - stop) / 1.25, dist = (t1 - entry) / ATR;
    var distB = dist < 2 ? "<2" : dist <= 5 ? "2-5" : dist <= 10 ? "5-10" : ">10";
    var reg = (BV.market && BV.market.regime4) || "risk_on_choppy";
    var rv = num(sr.rvol), vb = rv == null ? "normal" : rv < 0.7 ? "compressed" : rv <= 1.1 ? "normal" : rv <= 1.5 ? "expanding" : "spike";
    var rs = num(sr.rs), rb = rs == null ? "neutral" : rs >= 80 ? "strong_in" : rs >= 60 ? "mild_in" : rs >= 40 ? "neutral" : rs >= 20 ? "mild_out" : "strong_out";
    var sco = num(sr.score, 60), qb = sco >= 80 ? "elite" : sco >= 65 ? "high" : "standard";
    var st = (sr.setup || "").toLowerCase();
    var fam = /breakout|vcp|52w|expansion|gap/.test(st) ? "breakout" : /pullback|bounce|ema|value/.test(st) ? "pullback" : /trend|continuation|momentum/.test(st) ? "trend" : "other";
    var NMIN = TT.meta.n_min || 40, HZ = TT.meta.horizon;
    var keys = [[reg, vb, rb, fam, qb, distB], [reg, vb, rb, fam, "any", distB]];
    var cell = TT.cells[keys[0].join("|")];
    if (!cell || cell.n < NMIN) { // 1-level collapse: aggregate over qual within same fam
      var agN = 0, Sr = null;
      for (var k in TT.cells) {
        var p = k.split("|");
        if (p[0] === reg && p[1] === vb && p[2] === rb && p[3] === fam && p[5] === distB) {
          var c = TT.cells[k], w = c.n; agN += w;
          if (!Sr) Sr = new Array(HZ + 1).fill(0);
          for (var s = 0; s <= HZ; s++) Sr[s] += (c.S_reach[s] || 0) * w;
        }
      }
      if (agN >= NMIN && Sr) { for (var s2 = 0; s2 <= HZ; s2++) Sr[s2] /= agN; cell = { n: agN, S_reach: Sr, p_reach: Sr[HZ] }; }
    }
    if (!cell || cell.n < NMIN || !(cell.p_reach > 0)) return null;
    var med = null, stp = null;
    for (var s3 = 0; s3 <= HZ; s3++) { if (med == null && cell.S_reach[s3] >= cell.p_reach * 0.5) med = s3; if (stp == null && cell.S_reach[s3] >= cell.p_reach * 0.6) stp = s3; }
    var ceil = 21; // swing default ceiling for the badge
    return { taMedT1: med, taStop: Math.min(stp == null ? ceil : stp, ceil), taPReach: +(cell.p_reach * 100).toFixed(0), taN: cell.n };
  };

  // ── perform the blocking load (skippable with ?mock=1 for A/B debugging) ──
  // ONE combined round-trip (cuts cold tunnel load ~11s→~3s); fall back to the six
  // individual endpoints/files if the combined endpoint is unavailable.
  var MOCK = /mock=1/.test(location.search);
  var BOOT = MOCK ? null : syncGet("/api/bullveda-boot");
  if (BOOT) console.info("[BullVeda] combined boot payload (1 request)");
  var uni = BOOT ? BOOT.universe : (MOCK ? null : syncGet("/api/universe"));
  BV.universe = (uni && uni.screener) || [];
  // Scan freshness (audit #7) — so the desktop can show "as of HH:MM · Nh old" and
  // flag a stale/missed-scan bundle instead of rendering it as if it were today's.
  BV.scanMeta = uni ? { ts: uni.run_timestamp || null, ageMin: (uni.age_min != null ? uni.age_min : null), stale: !!uni.stale, n: uni.n } : null;
  var _rowsCache = null, _bySym = null;
  BV.scanRows = function () {
    if (!_rowsCache) {
      _rowsCache = BV.universe.map(BV.scanRow);
      _bySym = {};
      _rowsCache.forEach(function (r) { _bySym[r.sym] = r; });
    }
    return _rowsCache;
  };
  BV.findRow = function (sym) { BV.scanRows(); return _bySym[sym] || null; };
  BV.ready = BV.universe.length > 0;

  // ── real portfolio (Alpaca paper sync) → NAV + positions ──
  var pf = BOOT ? BOOT.portfolio : (MOCK ? null : syncGet("/api/portfolio"));
  BV.portfolio = pf || null;
  BV.nav = (pf && num(pf.equity) != null) ? pf.equity : null;
  BV.navDayPct = (function () {
    if (!pf || !pf.positions || !pf.equity) return null;
    var un = pf.positions.reduce(function (a, p) { return a + (num(p.unrealized_pnl_dollars, 0) || 0); }, 0);
    return +((un / pf.equity) * 100).toFixed(2);
  })();
  BV.navStr = function () {
    return BV.nav == null ? "—" : "$" + Math.round(BV.nav).toLocaleString();
  };
  // real holdings (Alpaca paper positions) → MyPF seed shape + real price map
  BV.realHoldings = function () {
    if (!pf || !pf.positions || !pf.positions.length) return null;
    return pf.positions.map(function (p) {
      return {
        sym: p.ticker, qty: Math.abs(num(p.shares, 0) || 0), cost: num(p.entry_price, 0) || 0,
        type: "stock", buyDate: p.entry_date || "", notes: p.notes || "",
        target: num(p.target1), target2: num(p.target2), stop: num(p.stop),
        account: "Alpaca Paper", direction: p.direction || "long", priceOverride: null,
      };
    });
  };
  BV.realCash = pf ? num(pf.cash, 0) : null;
  BV.realPrices = (function () {
    var m = {};
    if (pf && pf.positions) pf.positions.forEach(function (p) {
      var last = num(p.current_price);
      if (last != null) m[p.ticker.toUpperCase()] = { last: +last.toFixed(2), dayPct: 0, base: +last.toFixed(2) };
    });
    return m;
  })();

  // ── slim domain feeds (from the combined payload, else individual /v2/* files) ──
  if (!MOCK) {
    var cj = BOOT ? BOOT.crypto : syncGet("/v2/data_crypto.json");
    BV.crypto = (cj && cj.crypto) || null; // { top_picks, all_scored, rejected }
    var ej = BOOT ? BOOT.earnings : syncGet("/v2/data_earnings.json");
    BV.earningsBeat = (ej && ej.earnings_beat_predictions) || null;
    BV.earningsWatch = (ej && ej.earnings_watchlist) || null;
    // Time Anatomy table + Track-Record ledger are DEFERRED (heavy) — loaded async
    // after first paint via /api/bullveda-heavy, then bv:heavyready fires a re-render.
    BV.timeTable = null;
    BV.leaders = null;
    // critical subset — real market context + setup stats + options flow (essential, stays sync)
    BV.critical = BOOT ? BOOT.critical : (syncGet("/v2/data.critical.json") || null);
    BV.optionsFlow = (BV.critical && BV.critical.options_flow_top30) || null; // ticker-level UOA (from critical)
    BV.marketNews = (BV.critical && BV.critical.market_news) || null; // real EODHD market headlines (Home · MARKETS·NEWS)
    // true headline-index tape (Schwab indices + EODHD crypto): boot payload first
    // (fresh, <120s), else the copy persisted in critical (scan-cadence fallback).
    BV.indexQuotes = (BOOT && BOOT.index_quotes) || (BV.critical && BV.critical.index_quotes) || null;
    // real per-setup track-record stats (Wilson) keyed by setup family
    BV.setupStatsBy = (function () {
      var sf = BV.critical && BV.critical.setup_family_stats;
      if (!sf) return null;
      var m = {};
      (Array.isArray(sf) ? sf : Object.keys(sf).map(function (k) { var o = sf[k] || {}; o.setup = o.setup || k; return o; }))
        .forEach(function (s) { if (s && s.setup) m[s.setup] = s; });
      return m;
    })();
  } else { BV.crypto = BV.earningsBeat = BV.earningsWatch = BV.optionsFlow = BV.marketNews = BV.indexQuotes = BV.critical = BV.setupStatsBy = BV.leaders = null; }

  // ── real market context for the Home hero (regime · funnel · breadth · mood) ──
  BV.market = (function () {
    var c = BV.critical;
    if (!c) return null;
    var rg = c.regime || {}, mb = c.market_breadth || {}, mac = c.macro_signals || {};
    var r4 = rg.regime4 || "risk_on_choppy";
    var on = !/risk_off|panic/.test(r4);
    var trend = /trending/.test(r4) ? "TRENDING" : /choppy/.test(r4) ? "CHOPPY" : /panic/.test(r4) ? "PANIC" : "—";
    var pc = (mac.put_call && num(mac.put_call.equity_pc)) || null;
    var breadth = num(mb.pct_above_50d, null);
    var fg = (breadth != null) ? clamp(Math.round(breadth * 0.6 + (pc != null ? (1 - pc) * 40 : 20)), 0, 100) : null;
    return {
      regime4: r4, regimeOn: on, regimeTrend: trend,
      regimeLabel: (on ? "RISK-ON" : "RISK-OFF"),
      maxSize: num(rg.max_size_pct, null),
      breadthPct: breadth, breadth100: num(mb.pct_above_100d), breadth200: num(mb.pct_above_200d),
      newHighs: num(mb.new_highs), newLows: num(mb.new_lows),
      spy: num(rg.spy_price), qqq: num(rg.qqq_price),
      putCall: pc, fearGreed: fg, fgLabel: (mac.put_call && mac.put_call.signal) || null,
      funnel: { universe: num(c.scan_count, 0), bullish: num(c.buy_count, 0), neutral: num(c.watch_count, 0), bearish: num(c.killed_count, 0), short: num(c.short_count, 0) },
      sectors: c.sector_etf || null, movers: c.market_movers || null,
    };
  })();

  if (!BV.ready) console.warn("[BullVeda] no live universe — surfaces will show feed-honest empty states.", BV.errors);
  else console.info("[BullVeda] live universe loaded:", BV.universe.length, "rows · NAV", BV.navStr(),
    "· crypto", BV.crypto && BV.crypto.all_scored && BV.crypto.all_scored.length,
    "· earnings", BV.earningsBeat && BV.earningsBeat.length, "· optflow", BV.optionsFlow && BV.optionsFlow.length);

  // ── deferred heavy feeds: load async after first paint, then notify for re-render ──
  if (BV.ready && !MOCK) {
    BV.get("/api/bullveda-heavy").then(function (h) {
      if (h && h.time_table) BV.timeTable = h.time_table;
      if (h && h.data_leaders) BV.leaders = h.data_leaders;
      BV._tqCache = {}; // reset the timeQuick memo
      // populate the scan rows' TIME fields so the scanner column + sort work after re-render
      if (BV.timeTable) try {
        BV.scanRows().forEach(function (r) { var q = BV.timeQuick(r); if (q) { r.taMedT1 = q.taMedT1; r.taStop = q.taStop; } });
      } catch (e) {}
      try { window.dispatchEvent(new CustomEvent("bv:heavyready")); } catch (e) {}
      console.info("[BullVeda] heavy feeds ready — time table + ledger");
    }).catch(function (e) { console.warn("[BullVeda] heavy feeds failed", e); });
  }
})();
