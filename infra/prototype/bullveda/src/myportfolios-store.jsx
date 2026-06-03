// myportfolios-store.jsx — user-owned multi-portfolio store (localStorage),
// price simulation (overridable), and risk analytics. Exposes window.MyPF.

(function () {
  const LS_KEY = "bullveda_pf_v1"; // fresh key so stale demo localStorage never shadows real seed

  // ── seeded price sim ──────────────────────────────────────────
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  // deterministic "current" price + day-change for a ticker (stable per session
  // unless re-jittered). Cost-anchored so demo P&L is varied but believable.
  const PRICE_CACHE = {};
  function simPrice(sym, anchor) {
    const key = sym.toUpperCase();
    // BULLVEDA: real current price for live Alpaca positions
    if (window.__BV && window.__BV.realPrices && window.__BV.realPrices[key]) {
      if (!PRICE_CACHE[key]) PRICE_CACHE[key] = window.__BV.realPrices[key];
      return PRICE_CACHE[key];
    }
    if (PRICE_CACHE[key]) return PRICE_CACHE[key];
    const h = hash(key);
    const dayPct = (((h >> 3) % 720) / 100 - 3.2);                  // ~ −3.2%..+4.0%
    // Anchor to the holding's cost when known → believable P&L (−16%..+38% total
    // return), so targets sit above and stops below the live price as expected.
    const ret = ((h % 540) / 1000) - 0.16;                          // −0.16..+0.38
    const last = anchor ? anchor * (1 + ret) : (12 + (h % 480) + ((h >> 9) % 100) / 100);
    const base = last / (1 + dayPct / 100);                          // implied prev close
    const p = { last: +last.toFixed(2), dayPct: +dayPct.toFixed(2), base: +base.toFixed(2) };
    PRICE_CACHE[key] = p;
    return p;
  }
  function reprice() { Object.keys(PRICE_CACHE).forEach(k => { delete PRICE_CACHE[k]; }); }

  // live intraday tick — random-walk each cached price, recompute day-% vs prev
  // close (the deterministic `base`). Ephemeral (not persisted). Returns count moved.
  function tick() {
    const keys = Object.keys(PRICE_CACHE);
    keys.forEach(k => {
      const p = PRICE_CACHE[k];
      const prevClose = p.base || p.last;
      const drift = (Math.random() - 0.5) * 0.0035;            // ±~0.17% per tick
      const last = Math.max(0.01, +(p.last * (1 + drift)).toFixed(2));
      p.last = last;
      p.dayPct = +(((last / prevClose) - 1) * 100).toFixed(2);
    });
    if (keys.length) emit();
    return keys.length;
  }

  // sector / beta lookup (deterministic, demo)
  const SECTORS = ["Tech", "Finance", "Healthcare", "Energy", "Materials", "Industrials", "Consumer", "Utilities"];
  function metaFor(sym, assetType) {
    const h = hash(sym.toUpperCase());
    if (assetType === "crypto") return { sector: "Crypto", beta: 1.6 + (h % 80) / 100 };
    if (assetType === "cash") return { sector: "Cash", beta: 0 };
    return { sector: SECTORS[h % SECTORS.length], beta: +(0.6 + (h % 130) / 100).toFixed(2) };
  }

  // ── persistence ───────────────────────────────────────────────
  let state = load();
  function load() {
    if (window.UserPrefs) { const v = window.UserPrefs.get("portfolios", null); if (v) return v; }
    try { const raw = localStorage.getItem(LS_KEY); if (raw) return JSON.parse(raw); } catch (e) {}
    return seed();
  }
  function save() {
    if (window.UserPrefs) window.UserPrefs.set("portfolios", state);
    else { try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (e) {} }
    emit();
  }
  // cross-device: when another device/tab updates this user's portfolios, re-hydrate
  if (window.UserPrefs) {
    window.UserPrefs.subscribe("portfolios", (v) => { if (v && v !== state) { state = v; emit(); } });
  }
  function emit() { window.dispatchEvent(new CustomEvent("mypf-change")); }

  function uid() { return Math.random().toString(36).slice(2, 9); }

  function seed() {
    const mk = (sym, qty, cost, type, sector, date, notes, tgt, stop, acct, tgt2) =>
      ({ id: uid(), sym, qty, cost, type, buyDate: date, notes: notes || "", target: tgt || null, target2: tgt2 || null, stop: stop || null, account: acct || "Main", priceOverride: null });
    // BULLVEDA: seed the default portfolio from the REAL Alpaca paper book when available.
    if (window.__BV && window.__BV.realHoldings) {
      const rh = window.__BV.realHoldings();
      if (rh && rh.length) {
        return {
          activeId: "live",
          portfolios: [{
            id: "live", name: "Alpaca Paper (live)",
            cash: window.__BV.realCash != null ? Math.round(window.__BV.realCash) : 0,
            holdings: rh.map(h => ({ id: uid(), ...h })),
            trades: rh.map(h => ({ id: uid(), sym: h.sym, side: h.direction === "short" ? "SELL" : "BUY",
              qty: h.qty, price: h.cost, date: h.buyDate, note: h.notes || "Synced position", fee: 0 })),
          }],
          riskProfile: "moderate",
        };
      }
    }
    return {
      activeId: "p1",
      portfolios: [
        { id: "p1", name: "Core Equity", cash: 12400, holdings: [
          mk("NVDA", 40, 88.20, "stock", null, "2024-08-12", "AI capex cycle leader", 160, 102, "Schwab", 190),
          mk("ARGN", 120, 188.40, "stock", null, "2025-01-20", "Continuation breakout, sleeve A", 248, 178, "Schwab", 286),
          mk("ARCM", 110, 66.18, "stock", null, "2026-05-02", "Materials rotation", 80, 62, "Schwab", 92),
          mk("VOO", 30, 410.0, "etf", null, "2023-11-01", "Core index ballast", null, null, "IRA", null),
        ], trades: [
          { id: uid(), sym: "NVDA", side: "BUY", qty: 40, price: 88.20, date: "2024-08-12", note: "Initial position", fee: 0 },
          { id: uid(), sym: "ARGN", side: "BUY", qty: 120, price: 188.40, date: "2025-01-20", note: "Breakout entry", fee: 0 },
          { id: uid(), sym: "TSLA", side: "BUY", qty: 25, price: 210.0, date: "2025-09-03", note: "Swing", fee: 0 },
          { id: uid(), sym: "TSLA", side: "SELL", qty: 25, price: 246.5, date: "2025-10-15", note: "Hit target +1.7R", fee: 0 },
          { id: uid(), sym: "ARCM", side: "BUY", qty: 110, price: 66.18, date: "2026-05-02", note: "Add on retest", fee: 0 },
        ]},
        { id: "p2", name: "Crypto", cash: 3000, holdings: [
          mk("BTC", 0.6, 41200, "crypto", null, "2024-02-10", "Core hold", null, null, "Coinbase"),
          mk("ETH", 5, 2400, "crypto", null, "2024-05-18", "", null, null, "Coinbase"),
        ], trades: [
          { id: uid(), sym: "BTC", side: "BUY", qty: 0.6, price: 41200, date: "2024-02-10", note: "DCA", fee: 0 },
          { id: uid(), sym: "ETH", side: "BUY", qty: 5, price: 2400, date: "2024-05-18", note: "", fee: 0 },
        ]},
      ],
      riskProfile: "moderate", // conservative | moderate | aggressive
    };
  }

  // ── derived: enrich a holding with live price + P&L ───────────
  function enrich(h) {
    const sim = simPrice(h.sym, h.type === "cash" ? null : h.cost);
    const last = h.priceOverride != null ? h.priceOverride : (h.type === "cash" ? 1 : sim.last);
    const dayPct = h.priceOverride != null ? 0 : sim.dayPct;
    const mv = h.qty * last;
    const costBasis = h.qty * h.cost;
    const pnl = mv - costBasis;
    const pnlPct = costBasis ? (pnl / costBasis) * 100 : 0;
    const dayChg = mv * dayPct / 100;
    const meta = metaFor(h.sym, h.type);
    return { ...h, last, dayPct, mv, costBasis, pnl, pnlPct, dayChg, sector: meta.sector, beta: meta.beta };
  }

  function summarize(pf) {
    const rows = pf.holdings.map(enrich);
    const invested = rows.reduce((s, r) => s + r.mv, 0);
    const cost = rows.reduce((s, r) => s + r.costBasis, 0);
    const totalValue = invested + (pf.cash || 0);
    const unrealized = invested - cost;
    const dayChg = rows.reduce((s, r) => s + r.dayChg, 0);
    const realized = (pf.trades || []).filter(t => t.side === "SELL").reduce((s, t) => {
      // realized vs avg cost approximation using current holding cost
      const hb = pf.holdings.find(h => h.sym === t.sym);
      const basis = hb ? hb.cost : t.price * 0.9;
      return s + (t.price - basis) * t.qty - (t.fee || 0);
    }, 0);
    const divIncome = rows.reduce((s, r) => s + (r.type === "stock" || r.type === "etf" ? r.mv * 0.012 : 0), 0); // ~1.2% yield demo
    let best = null, worst = null;
    rows.forEach(r => { if (r.type === "cash") return; if (!best || r.pnlPct > best.pnlPct) best = r; if (!worst || r.pnlPct < worst.pnlPct) worst = r; });
    return { rows, invested, cost, totalValue, unrealized, unrealizedPct: cost ? unrealized / cost * 100 : 0, dayChg, dayChgPct: invested ? dayChg / invested * 100 : 0, realized, divIncome, best, worst, cash: pf.cash || 0 };
  }

  // ── risk analytics ────────────────────────────────────────────
  function risk(pf) {
    const { rows, invested } = summarize(pf);
    const eq = rows.filter(r => r.type !== "cash");
    const w = eq.map(r => ({ ...r, wt: invested ? r.mv / invested : 0 }));
    const beta = w.reduce((s, r) => s + r.wt * r.beta, 0);
    // concentration: HHI + top weight
    const hhi = w.reduce((s, r) => s + r.wt * r.wt, 0);
    const top = w.slice().sort((a, b) => b.mv - a.mv)[0];
    // sector exposure
    const secMap = {}; w.forEach(r => { secMap[r.sector] = (secMap[r.sector] || 0) + r.wt; });
    const sectors = Object.entries(secMap).map(([k, v]) => ({ k, pct: v * 100 })).sort((a, b) => b.pct - a.pct);
    // volatility: weighted, beta-scaled market vol ~16% + idio
    const vol = Math.sqrt(w.reduce((s, r) => s + r.wt * Math.pow(r.beta * 16 + (hash(r.sym) % 12), 2), 0)) || 0;
    const annVol = +(vol).toFixed(1);
    // parametric 1-day 95% VaR
    const dailyVol = annVol / Math.sqrt(252) / 100;
    const var95 = invested * 1.645 * dailyVol;
    const cvar = invested * 2.06 * dailyVol;
    // max drawdown (demo, beta-scaled)
    const maxDD = +(- (8 + beta * 9)).toFixed(1);
    return { beta: +beta.toFixed(2), hhi: +hhi.toFixed(3), topWt: top ? top.wt * 100 : 0, topSym: top ? top.sym : "—", sectors, annVol, var95, cvar, maxDD, nNames: eq.length, invested };
  }

  // ── public API ────────────────────────────────────────────────
  const MyPF = {
    list: () => state.portfolios,
    active: () => state.portfolios.find(p => p.id === state.activeId) || state.portfolios[0],
    activeId: () => state.activeId,
    setActive: (id) => { state.activeId = id; save(); },
    riskProfile: () => state.riskProfile,
    setRiskProfile: (v) => { state.riskProfile = v; save(); },
    create: (name) => { const p = { id: uid(), name: name || "New Portfolio", cash: 0, holdings: [], trades: [] }; state.portfolios.push(p); state.activeId = p.id; save(); return p.id; },
    rename: (id, name) => { const p = state.portfolios.find(x => x.id === id); if (p) p.name = name; save(); },
    remove: (id) => { state.portfolios = state.portfolios.filter(p => p.id !== id); if (state.activeId === id) state.activeId = (state.portfolios[0] || {}).id; save(); },
    setCash: (id, cash) => { const p = state.portfolios.find(x => x.id === id); if (p) p.cash = +cash || 0; save(); },
    addHolding: (id, h) => { const p = state.portfolios.find(x => x.id === id); if (!p) return; p.holdings.push({ id: uid(), priceOverride: null, account: "Main", notes: "", target: null, target2: null, stop: null, ...h }); if (h.sym && h.qty && h.cost) p.trades.push({ id: uid(), sym: h.sym, side: "BUY", qty: +h.qty, price: +h.cost, date: h.buyDate || new Date().toISOString().slice(0, 10), note: "Opened position", fee: 0 }); save(); },
    updateHolding: (id, hid, patch) => { const p = state.portfolios.find(x => x.id === id); if (!p) return; const h = p.holdings.find(x => x.id === hid); if (h) Object.assign(h, patch); save(); },
    removeHolding: (id, hid) => { const p = state.portfolios.find(x => x.id === id); if (!p) return; p.holdings = p.holdings.filter(x => x.id !== hid); save(); },
    addTrade: (id, t) => { const p = state.portfolios.find(x => x.id === id); if (!p) return; p.trades.unshift({ id: uid(), fee: 0, ...t }); save(); },
    removeTrade: (id, tid) => { const p = state.portfolios.find(x => x.id === id); if (!p) return; p.trades = p.trades.filter(x => x.id !== tid); save(); },
    summarize, risk, enrich, simPrice, reprice, tick,
    // combined "All" rollup as a synthetic portfolio
    combined: () => ({ id: "__all", name: "All Portfolios", cash: state.portfolios.reduce((s, p) => s + (p.cash || 0), 0), holdings: state.portfolios.flatMap(p => p.holdings), trades: state.portfolios.flatMap(p => p.trades) }),
    reset: () => { state = seed(); save(); },
  };
  window.MyPF = MyPF;
})();
