// crypto-feed.jsx — crypto market data module. SIMULATED now; shaped to map 1:1
// onto EODHD crypto endpoints (price/volume/change) + CoinGecko (mcap/dominance)
// + Alternative.me (Fear & Greed). Replace the sim in tick()/seed with real calls.
// Exposes window.CryptoFeed. Emits "crypto-change" on each tick.
//
// EODHD mapping (production):
//   real-time:  GET /real-time/{SYM}-USD.CC   → { close, change_p, high, low, volume, timestamp }
//   history:    GET /eod/{SYM}-USD.CC          → 7d/30d change derived from closes
//   mcap/dominance: CoinGecko /coins/markets + /global
//   fear&greed: Alternative.me /fng

(function () {
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

  // sym, name, category, seed price (USD), circulating supply (for mcap)
  const COINS = [
    { sym: "BTC",  name: "Bitcoin",      cat: "L1",    px: 71240,  supply: 19.7e6 },
    { sym: "ETH",  name: "Ethereum",     cat: "L1",    px: 3842,   supply: 120.3e6 },
    { sym: "SOL",  name: "Solana",       cat: "L1",    px: 165.2,  supply: 462e6 },
    { sym: "BNB",  name: "BNB",          cat: "L1",    px: 601.4,  supply: 147e6 },
    { sym: "XRP",  name: "XRP",          cat: "Payments", px: 0.624, supply: 56.1e9 },
    { sym: "ADA",  name: "Cardano",      cat: "L1",    px: 0.481,  supply: 35.4e9 },
    { sym: "AVAX", name: "Avalanche",    cat: "L1",    px: 37.9,   supply: 408e6 },
    { sym: "DOGE", name: "Dogecoin",     cat: "Meme",  px: 0.162,  supply: 144e9 },
    { sym: "LINK", name: "Chainlink",    cat: "DeFi",  px: 17.4,   supply: 626e6 },
    { sym: "DOT",  name: "Polkadot",     cat: "L1",    px: 7.18,   supply: 1.44e9 },
    { sym: "MATIC",name: "Polygon",      cat: "L2",    px: 0.722,  supply: 9.9e9 },
    { sym: "LTC",  name: "Litecoin",     cat: "Payments", px: 92.1, supply: 74.6e6 },
    { sym: "ATOM", name: "Cosmos",       cat: "L1",    px: 9.46,   supply: 391e6 },
    { sym: "ARB",  name: "Arbitrum",     cat: "L2",    px: 1.13,   supply: 3.5e9 },
    { sym: "OP",   name: "Optimism",     cat: "L2",    px: 2.31,   supply: 1.1e9 },
    { sym: "INJ",  name: "Injective",    cat: "DeFi",  px: 28.4,   supply: 96e6 },
    { sym: "SUI",  name: "Sui",          cat: "L1",    px: 1.42,   supply: 2.8e9 },
    { sym: "TIA",  name: "Celestia",     cat: "L1",    px: 9.02,   supply: 220e6 },
  ];

  // BULLVEDA: replace the demo coin list with the REAL crypto screener (data_crypto.json)
  if (window.__BV && window.__BV.crypto && window.__BV.crypto.all_scored && window.__BV.crypto.all_scored.length) {
    COINS.length = 0;
    window.__BV.crypto.all_scored.forEach(c => COINS.push({
      sym: c.symbol, name: c.name, cat: c.category || "Crypto", px: c.price,
      supply: c.price ? c.market_cap / c.price : 0,
      _real: { chg24: c.d24h, chg7: c.d7d, chg30: c.d30d, vol: c.vol_24h, mcap: c.market_cap, score: c.score, decision: c.decision, note: c.fund_note },
    }));
  }

  // seed each coin's quote (REAL 24h/7d/30d when available; else deterministic demo)
  const Q = {};
  COINS.forEach(c => {
    if (c._real) {
      const r = c._real;
      const prevClose = +(c.px / (1 + (r.chg24 || 0) / 100)).toFixed(c.px < 1 ? 5 : 2);
      Q[c.sym] = { last: c.px, prevClose, chg24: +(r.chg24 || 0).toFixed(2), chg7: +(r.chg7 || 0).toFixed(2), chg30: +(r.chg30 || 0).toFixed(2), vol: r.vol || 0 };
      return;
    }
    const h = hash(c.sym);
    const chg24 = ((h % 1400) / 100) - 6.5;                 // ~ −6.5%..+7.5%
    const chg7 = ((((h >>> 5) % 5000) / 100) - 22);          // ~ −22%..+28%
    const chg30 = ((((h >>> 9) % 9000) / 100) - 38);         // ~ −38%..+52%
    const prevClose = +(c.px / (1 + chg24 / 100)).toFixed(c.px < 1 ? 5 : 2);
    const vol = c.px * c.supply * (0.02 + ((h >>> 3) % 80) / 1000); // 24h $ volume
    Q[c.sym] = { last: c.px, prevClose, chg24: +chg24.toFixed(2), chg7: +chg7.toFixed(2), chg30: +chg30.toFixed(2), vol };
  });

  function emit() { window.dispatchEvent(new CustomEvent("crypto-change")); }

  function list() {
    return COINS.map(c => {
      const q = Q[c.sym];
      const mcap = q.last * c.supply;
      return { ...c, last: q.last, chg24: q.chg24, chg7: q.chg7, chg30: q.chg30, vol: q.vol, mcap };
    }).sort((a, b) => b.mcap - a.mcap).map((c, i) => ({ ...c, rank: i + 1, ...signal(c) }));
  }

  // ── Kairos signal — the "should I buy?" read per coin ──────────
  // Trend-following blend: 30d & 7d momentum (the edge) minus 24h over-extension
  // (don't chase), nudged by a deterministic per-asset quality seed. 0–100.
  function signal(c) {
    // BULLVEDA: real screener score/decision when present
    if (c._real && typeof c._real.score === "number") {
      const v = c._real.decision || "WATCH";
      return { score: c._real.score, verdict: v, vtone: v === "BUY" ? "gn" : v === "AVOID" ? "rd" : "amb",
        why: c._real.note || (v === "BUY" ? "screener edge" : v === "AVOID" ? "no edge" : "constructive") };
    }
    const h = hash(c.sym + "sig");
    const quality = (h % 24) - 8;                       // −8..+15 idiosyncratic
    const trend = c.chg30 * 0.7 + c.chg7 * 1.1;         // medium-term momentum
    const overext = Math.max(0, c.chg24 - 4) * 2.2;     // penalise a name already ripped today
    let score = Math.round(52 + trend * 0.9 - overext + quality);
    score = Math.max(3, Math.min(98, score));
    let verdict, tone, why;
    if (score >= 70) { verdict = "BUY"; tone = "gn"; why = c.chg24 > 4 ? "strong trend · let it pull back" : "trend + momentum aligned"; }
    else if (score >= 50) { verdict = "WATCH"; tone = "amb"; why = c.chg7 < 0 ? "basing · needs a trigger" : "constructive · not yet confirmed"; }
    else { verdict = "AVOID"; tone = "rd"; why = c.chg30 < 0 ? "downtrend · no edge" : "weak structure"; }
    return { score, verdict, vtone: tone, why };
  }

  function globals() {
    const rows = list();
    const totalMcap = rows.reduce((s, r) => s + r.mcap, 0);
    const totalVol = rows.reduce((s, r) => s + r.vol, 0);
    const btc = rows.find(r => r.sym === "BTC");
    const eth = rows.find(r => r.sym === "ETH");
    const btcDom = btc ? btc.mcap / totalMcap * 100 : 0;
    const ethDom = eth ? eth.mcap / totalMcap * 100 : 0;
    // Fear & Greed proxy from mean 24h move of majors (0–100)
    const meanChg = rows.slice(0, 10).reduce((s, r) => s + r.chg24, 0) / 10;
    const fng = Math.max(4, Math.min(96, Math.round(50 + meanChg * 6)));
    const fngLabel = fng >= 75 ? "Extreme Greed" : fng >= 55 ? "Greed" : fng >= 45 ? "Neutral" : fng >= 25 ? "Fear" : "Extreme Fear";
    return { totalMcap, totalVol, btcDom, ethDom, fng, fngLabel };
  }

  // live 24/7 tick — random-walk each close, recompute 24h % vs the stored prev close
  function tick() {
    COINS.forEach(c => {
      const q = Q[c.sym];
      const drift = (Math.random() - 0.5) * 0.006;          // ±~0.3% (crypto vol > equities)
      const last = q.last * (1 + drift);
      q.last = +last.toFixed(c.px < 1 ? 5 : 2);
      q.chg24 = +(((q.last / q.prevClose) - 1) * 100).toFixed(2);
    });
    emit();
  }

  window.CryptoFeed = { COINS, list, globals, tick };
})();
