// Mock data for TICKR — used by all three design directions

window.TICKR_DATA = {
  ticker: "TICKR",
  company: "Tickr Industrial Holdings",
  sector: "Industrials / Aerospace & Defense",
  price: 247.83,
  change: 4.27,
  changePct: 1.75,
  marketCap: "42.7B",
  avgVol: "3.2M",
  float: "168.4M",
  beta: 1.24,
  verdict: "BUY",
  conviction: 78,
  setup: "EMA21 Pullback · Trend Continuation",
  asOf: "2026-04-25 15:58 ET",

  // Scoring
  scores: {
    technical: 82,
    fundamental: 71,
    sentiment: 64,
    smc: 88,
    risk: 73,
    composite: 78,
  },

  // Key metrics
  metrics: {
    rsi14: 58.4,
    macd: 1.82,
    macdSignal: 1.41,
    adx14: 28.7,
    atr14: 6.42,
    sma20: 238.91,
    sma50: 224.18,
    sma200: 198.42,
    ema21: 240.12,
    vwap: 245.66,
    relStrength: 1.34, // vs SPY
  },

  // Fundamentals
  fundamentals: {
    pe: 24.8,
    forwardPe: 19.2,
    pegRatio: 1.42,
    priceToSales: 4.1,
    priceToBook: 6.8,
    epsTtm: 9.98,
    epsGrowth: 28.4,
    revenueGrowth: 17.2,
    grossMargin: 42.1,
    operatingMargin: 18.7,
    netMargin: 14.2,
    fcfYield: 3.8,
    debtToEquity: 0.42,
    roe: 22.4,
    roic: 16.8,
    nextEarnings: "2026-05-14",
    earningsBeats: "8 of last 10",
  },

  // SMC
  smc: {
    structure: "Bullish BOS confirmed @ 244.10",
    orderBlocks: [
      { type: "demand", high: 232.40, low: 228.10, strength: "strong", date: "2026-04-08" },
      { type: "demand", high: 218.70, low: 214.30, strength: "very strong", date: "2026-03-21" },
      { type: "supply", high: 268.40, low: 264.10, strength: "moderate", date: "2026-02-12" },
    ],
    fvgs: [
      { high: 241.20, low: 237.85, status: "unfilled", direction: "bullish" },
      { high: 226.10, low: 222.40, status: "filled", direction: "bullish" },
    ],
    liquidity: [
      { level: 268.40, type: "buy-side", note: "Feb swing high — magnet" },
      { level: 214.30, type: "sell-side", note: "Stop cluster below 3/21 low" },
    ],
    premium_discount: "Trading in equilibrium (52% of range)",
  },

  // Trade plan
  plan: {
    bias: "long",
    entry: 246.50,
    entryZone: [244.80, 248.20],
    stop: 238.40,
    target1: 262.50,
    target2: 278.00,
    target3: 295.00,
    rr1: 1.97,
    rr2: 3.88,
    rr3: 5.99,
    riskPctAccount: 0.75,
    sharesSuggested: 124,
    notional: 30538,
    holdDays: "8–14",
    invalidation: "Daily close below 238.40 or break of 4/8 swing low",
  },

  // Risk
  risk: {
    accountSize: 250000,
    positionRisk: 1875,
    portfolioHeat: 3.2,
    maxHeat: 6.0,
    correlations: [
      { ticker: "RTX", corr: 0.71 },
      { ticker: "LMT", corr: 0.68 },
      { ticker: "GE", corr: 0.54 },
    ],
    var95: 4820,
    expectedShortfall: 7140,
    kellyFraction: 0.18,
  },

  // News
  news: [
    { time: "2h ago", source: "Reuters", title: "Tickr lands $1.2B DoD hypersonics contract — 5-year IDIQ", sentiment: "bullish", impact: "high" },
    { time: "6h ago", source: "Bloomberg", title: "Analyst upgrades: Morgan Stanley to Overweight, PT $295", sentiment: "bullish", impact: "medium" },
    { time: "1d ago", source: "WSJ", title: "Industrial sector ETF sees record inflows; Tickr cited", sentiment: "bullish", impact: "low" },
    { time: "2d ago", source: "Reuters", title: "Supply chain cost pressures persist into Q2", sentiment: "bearish", impact: "low" },
    { time: "3d ago", source: "CNBC", title: "Insider buying: CFO purchased $480k worth", sentiment: "bullish", impact: "medium" },
  ],

  // Sentiment
  sentiment: {
    analystBuy: 18,
    analystHold: 6,
    analystSell: 1,
    avgPriceTarget: 282.40,
    socialBullish: 71,
    socialBearish: 22,
    socialNeutral: 7,
    putCallRatio: 0.62,
    shortInterest: 4.1,
  },

  // Backtest
  backtest: {
    setupName: "EMA21 Pullback in Uptrend",
    historical: 142,
    winRate: 64.8,
    avgRMultiple: 1.42,
    avgWin: 2.8,
    avgLoss: -1.0,
    expectancy: 0.78,
    avgHoldDays: 11.4,
    bestMonth: 8.2,
    worstMonth: -3.1,
    similarSetups: [
      { date: "2026-02-04", outcome: "+2.4R", days: 9 },
      { date: "2025-11-18", outcome: "+1.8R", days: 12 },
      { date: "2025-09-22", outcome: "-1.0R", days: 4 },
      { date: "2025-07-11", outcome: "+3.2R", days: 14 },
      { date: "2025-04-29", outcome: "+1.1R", days: 7 },
    ],
  },

  // Earnings
  earnings: [
    { q: "Q4 25", epsEst: 2.41, epsAct: 2.68, surprise: 11.2, revEst: 4.21, revAct: 4.38 },
    { q: "Q3 25", epsEst: 2.18, epsAct: 2.32, surprise: 6.4, revEst: 3.98, revAct: 4.04 },
    { q: "Q2 25", epsEst: 2.04, epsAct: 2.11, surprise: 3.4, revEst: 3.71, revAct: 3.79 },
    { q: "Q1 25", epsEst: 1.88, epsAct: 2.02, surprise: 7.4, revEst: 3.52, revAct: 3.61 },
  ],

  // Bull/bear
  scenarios: {
    bull: {
      probability: 58,
      target: 295,
      thesis: "Defense backlog acceleration + margin expansion from automation. New contract wins flow through to FY27 estimates. Sector rotation into industrials persists.",
      catalysts: ["Q1 earnings beat & raise (May 14)", "Pentagon FY27 budget", "Spin-off of Marine Systems unit", "Buyback announcement at Investor Day"],
    },
    base: {
      probability: 28,
      target: 262,
      thesis: "Steady execution, no surprises. Stock grinds higher with sector. Multiple compression offset by EPS growth.",
      catalysts: ["In-line Q1 print", "Status quo backlog conversion"],
    },
    bear: {
      probability: 14,
      target: 198,
      thesis: "Continuing-resolution defense budget delays revenue recognition. Aluminum cost spike compresses margins. Risk-off rotates out of industrials.",
      catalysts: ["Government shutdown drag", "Margin guide cut", "Major contract loss to competitor"],
    },
  },

  // Generated candle data (90 days ending today at 247.83)
  candles: generateCandles(),

  // Journal notes
  notes: [
    { date: "2026-04-22", text: "Watching for retest of 240 EMA21. If holds with volume, that's the entry. Not chasing." },
    { date: "2026-04-18", text: "Q1 print on 5/14 is the binary event. Sized to survive a 12% gap-down miss reaction." },
    { date: "2026-04-10", text: "Got the 218 OB tap & rip. Trailing stop on remaining 50% of position to 238." },
  ],
};

function generateCandles() {
  // Deterministic-ish synthetic candles trending up to 247.83
  const out = [];
  let price = 195;
  const drift = 0.0035;
  const vol = 0.018;
  const seed = (i) => Math.sin(i * 12.9898) * 43758.5453;
  for (let i = 0; i < 90; i++) {
    const r1 = seed(i + 1) - Math.floor(seed(i + 1));
    const r2 = seed(i + 31) - Math.floor(seed(i + 31));
    const open = price;
    const dailyDrift = drift + (i > 60 ? 0.002 : 0);
    const close = open * (1 + dailyDrift + (r1 - 0.5) * vol);
    const high = Math.max(open, close) * (1 + Math.abs(r2) * 0.008);
    const low = Math.min(open, close) * (1 - Math.abs(r1) * 0.008);
    const volume = 2_000_000 + Math.abs(r1) * 4_000_000;
    out.push({
      i,
      date: new Date(2026, 0, 23 + i).toISOString().slice(0, 10),
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume: Math.round(volume),
    });
    price = close;
  }
  // Force final close to 247.83
  const last = out[out.length - 1];
  const adj = 247.83 / last.close;
  for (let i = 80; i < out.length; i++) {
    out[i].open = +(out[i].open * adj).toFixed(2);
    out[i].close = +(out[i].close * adj).toFixed(2);
    out[i].high = +(out[i].high * adj).toFixed(2);
    out[i].low = +(out[i].low * adj).toFixed(2);
  }
  return out;
}

// Mock dashboard scanner data — many tickers for the heatmap/watchlist
window.SCANNER_DATA = (function () {
  const tickers = [
    ["TICKR", "Tickr Industrial", "Industrials", 247.83, 1.75, 78, "BUY", "EMA21 Pullback", 82, 88],
    ["NVRA", "Novara Semi", "Technology", 412.60, 2.84, 84, "BUY", "Breakout", 88, 76],
    ["HLIO", "Helios Energy", "Energy", 88.42, -1.21, 42, "WAIT", "Range", 51, 38],
    ["VRTX", "Vertex Bio", "Healthcare", 318.91, 0.84, 71, "BUY", "Trend Continuation", 76, 68],
    ["KAIO", "Kaio Logistics", "Industrials", 64.18, 3.42, 81, "BUY", "Cup & Handle", 84, 72],
    ["MERID", "Meridian Cap", "Financials", 124.50, -0.42, 58, "HOLD", "Pullback", 62, 55],
    ["AURA", "Aurora Robotics", "Technology", 198.40, 4.18, 86, "BUY", "Flag", 91, 81],
    ["PHAS", "Phasor Networks", "Technology", 76.20, -2.84, 32, "AVOID", "Breakdown", 28, 24],
    ["OREL", "Orelius Pharma", "Healthcare", 142.80, 1.92, 68, "BUY", "Reversal", 71, 64],
    ["FLNT", "Fluent Materials", "Materials", 58.40, 0.71, 54, "HOLD", "Consolidation", 58, 52],
    ["SOLT", "Solterra Mining", "Materials", 92.10, 2.41, 74, "BUY", "Breakout", 78, 70],
    ["NEXA", "Nexa Payments", "Financials", 218.60, -0.84, 47, "WAIT", "Range", 49, 44],
    ["KORE", "Korelis Software", "Technology", 384.20, 1.42, 72, "BUY", "Trend Continuation", 76, 67],
    ["BRMA", "Brama Foods", "Consumer", 41.80, 0.21, 51, "HOLD", "Base", 54, 48],
    ["AETH", "Aether Aero", "Industrials", 312.40, 2.18, 79, "BUY", "EMA21 Pullback", 82, 74],
    ["DRYL", "Drayl Bio", "Healthcare", 84.20, -3.42, 28, "AVOID", "Breakdown", 24, 22],
    ["CLAR", "Clarity Cloud", "Technology", 168.40, 1.84, 75, "BUY", "Flag", 78, 70],
    ["MVRK", "Maverick Auto", "Consumer", 218.80, -1.18, 44, "WAIT", "Pullback", 48, 42],
    ["SOMA", "Somatic AI", "Technology", 482.40, 3.84, 88, "BUY", "Breakout", 92, 84],
    ["PRYM", "Prym Defense", "Industrials", 184.20, 1.42, 76, "BUY", "Trend Continuation", 79, 72],
    ["KNDR", "Kindred Retail", "Consumer", 38.40, -0.84, 41, "HOLD", "Range", 44, 38],
    ["VECT", "Vector Telecom", "Telecom", 62.10, 0.42, 56, "HOLD", "Base", 59, 52],
    ["LMRA", "Lumira Optics", "Technology", 142.80, 2.18, 73, "BUY", "Flag", 76, 68],
    ["TRAV", "Traverse Hotels", "Consumer", 84.60, -1.42, 38, "WAIT", "Pullback", 41, 36],
    ["OBLQ", "Obliq Networks", "Technology", 218.40, 1.18, 67, "HOLD", "Consolidation", 70, 62],
    ["VESP", "Vesper Banks", "Financials", 96.20, 0.62, 62, "HOLD", "Base", 64, 58],
    ["NTRO", "Nitro Chemicals", "Materials", 124.40, -0.42, 51, "HOLD", "Range", 53, 48],
    ["ASCN", "Ascend Aviation", "Industrials", 68.20, 2.84, 72, "BUY", "Breakout", 75, 68],
    ["RNDR", "Render Studios", "Communication", 184.60, 1.42, 69, "BUY", "Trend Continuation", 72, 64],
    ["FLRA", "Flora Health", "Healthcare", 41.20, -2.18, 34, "AVOID", "Breakdown", 32, 28],
  ];
  return tickers.map(t => ({
    ticker: t[0], name: t[1], sector: t[2], price: t[3], changePct: t[4],
    score: t[5], verdict: t[6], setup: t[7], technical: t[8], smc: t[9],
  }));
})();
