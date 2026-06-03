// kairos-data.jsx — data registry for the Kairos assistant.
// Aggregates every dataset (in production these map to your JSON files / Supabase
// tables) behind one queryable surface so Kairos can pull whatever a question
// needs. window.KairosData.retrieve(query, ctx) → compact JSON slices for the prompt.

(function () {
  // ── dataset providers — each returns plain JSON (swap to fetch() in prod) ──
  const SOURCES = {
    universe: {
      desc: "All scanned tickers with verdict, score, setup, price.",
      keywords: ["scan", "universe", "buy", "verdict", "score", "ranked", "list", "which", "top"],
      get: () => (window.TICKER_UNIVERSE || []).map(t => ({ sym: t.sym, name: t.name, sector: t.sector, verdict: t.verdict, score: t.score })),
    },
    predictions: {
      desc: "AI ML forecasts: edge score, P(up), ensemble, verdict, 3M target per name.",
      keywords: ["predict", "forecast", "ml", "ai", "edge", "probability", "ensemble", "p(up)", "target", "cone"],
      get: () => (window.AIPredict ? window.AIPredict.all().map(p => ({ sym: p.sym, verdict: p.verdict, score: p.score, pUp: p.pUp, ens: p.ens, conf: p.conf, target3m: p.horizons && p.horizons[2] ? +p.horizons[2].med.toFixed(2) : null })) : []),
    },
    aiBacktest: {
      desc: "AI model out-of-sample accuracy: AUC, hit rate, Brier, Sharpe + calibration buckets.",
      keywords: ["accuracy", "calibration", "backtest", "auc", "brier", "reliable", "hit rate"],
      get: () => window.AIPredict ? { backtest: window.AIPredict.BACKTEST, calibration: window.AIPredict.CALIB } : null,
    },
    trackRecord: {
      desc: "System-wide signal accountability: per-source hit-rate, edge, profit factor.",
      keywords: ["track record", "accountability", "did it work", "hit rate", "source", "leaderboard", "edge vs spy", "audit"],
      get: () => window.SigLedger ? window.SigLedger.leaderboard("edge").map(s => ({ source: s.label, hitRate: s.avgHit, avgEdge: s.avgEdge, profitFactor: s.pf, optimalHold: s.best ? s.best.hz : null, significant: s.sig })) : [],
    },
    portfolios: {
      desc: "User's own portfolios: holdings, P&L, cash, risk profile.",
      keywords: ["my portfolio", "holding", "position", "p&l", "pnl", "own", "i hold", "my book", "cash", "gain"],
      get: () => {
        if (!window.MyPF) return null;
        return window.MyPF.list().map(p => { const s = window.MyPF.summarize(p); return { name: p.name, totalValue: +s.totalValue.toFixed(0), unrealized: +s.unrealized.toFixed(0), cash: p.cash, holdings: p.holdings.map(h => ({ sym: h.sym, qty: h.qty, cost: h.cost })) }; });
      },
    },
    help: {
      desc: "Documentation: how every surface/section/field works and is computed.",
      keywords: ["how", "what is", "explain", "mean", "computed", "work", "use", "help", "definition"],
      get: () => (window.HELP_DOCS || []).map(d => ({ topic: d.title, what: d.what, computed: d.computed })),
    },
  };

  // pick the most relevant sources for a query, return compact JSON for the prompt
  function retrieve(query, ctx) {
    const ql = (query || "").toLowerCase();
    const sym = ctx && ctx.ticker ? ctx.ticker.symbol : null;
    const picked = [];
    Object.entries(SOURCES).forEach(([key, src]) => {
      const score = src.keywords.reduce((n, k) => n + (ql.includes(k) ? 1 : 0), 0);
      if (score > 0) picked.push({ key, src, score });
    });
    picked.sort((a, b) => b.score - a.score);
    const use = picked.slice(0, 2);
    const out = {};
    use.forEach(({ key, src }) => {
      let data = src.get();
      // if a ticker is open, narrow row-lists to that name + a few peers
      if (sym && Array.isArray(data)) {
        const mine = data.filter(r => r.sym === sym);
        data = mine.length ? mine.concat(data.filter(r => r.sym !== sym).slice(0, 8)) : data.slice(0, 12);
      } else if (Array.isArray(data)) {
        data = data.slice(0, 14);
      }
      out[key] = data;
    });
    return out;
  }

  // a one-line catalog of what Kairos can pull (for the system prompt)
  function catalog() {
    return Object.entries(SOURCES).map(([k, s]) => `${k}: ${s.desc}`).join(" | ");
  }

  window.KairosData = { SOURCES, retrieve, catalog };
})();
