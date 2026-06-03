// data.jsx — mock data for the SwingTrade terminal
// All numbers are illustrative — feed-honest empty/scaffolding states are baked in.

const TICKER = {
  symbol: "ARCM",
  name: "Arclight Materials Corp",
  exchange: "NASDAQ",
  sector: "Materials",
  industry: "Specialty Chemicals",
  mcap: 4.82e9,        // ~$4.8B — mid-cap
  price: 67.42,
  chg: 1.84,           // +%
  chgAbs: 1.22,
  prev: 66.20,
  vol: 1_842_000,
  avgVol: 1_120_000,
  rsi: 64.2,
  beta: 1.18,
  shortFloat: 6.8,
  insiderOwn: 4.2,
  pe: 22.4,
  fwdPe: 18.9,
  divYield: 0.4,
  earnings: { days: 11, date: "Jun 09" },
  // breakout setup
  setupFamily: "Continuation Breakout · base #2",
  pivot: 66.18,
  stop: 62.40,
  t1: 72.80,
  t2: 78.20,
  trail: "ATR(14) × 2.2",
  holdDays: 14,
  rMultiple: 1.74,
  // 5-pillar scores (0–100)
  pillars: {
    technical: 82,
    fundamental: 71,
    catalyst:   58,
    risk:       66,
    edge:       74,
  },
  verdict: "BUY",
  score: 78,
  // ML
  ml: {
    direction: 0.61,      // P(up over horizon)
    hitNet:    0.18,      // P(T1 first) − P(stop first)
    magnitude: { lo: -4.2, mid: 6.4, hi: 12.1 }, // %
  },
  // Track record (Wilson)
  setupStats: {
    n: 47,
    winRate: 0.617,
    wilsonLB: 0.477,
    pf: 1.84,
    medianR: 0.72,
  },
};

// Heatmap tickers (sized by mcap, colored by daily %). All fictional.
const HEATMAP = [
  // [symbol, sector, mcap (B), chg%]
  ["NVRH", "Tech",       2240, +2.4],
  ["KLYX", "Tech",       1980, -0.6],
  ["ZOTR", "Tech",       1610, +1.8],
  ["TWPN", "Tech",       1420, -1.2],
  ["FLNX", "Tech",        980, +0.4],
  ["ARGN", "Tech",        720, +3.1],
  ["MERC", "Tech",        540, -2.8],
  ["OPTH", "Tech",        410, +0.9],
  ["VEKR", "Tech",        320, -0.3],
  ["SPND", "Tech",        260, +1.1],
  ["KARO", "Tech",        180, -4.2],
  ["LIRO", "Tech",        140, +0.7],
  ["IPSO", "Tech",         95, +2.0],

  ["BRMK", "Finance",     920, +0.8],
  ["VLCT", "Finance",     680, +1.6],
  ["HARP", "Finance",     510, -0.4],
  ["KENT", "Finance",     380, +0.2],
  ["FOLD", "Finance",     280, -1.1],
  ["INPR", "Finance",     220, +2.6],
  ["NUFR", "Finance",     150, -0.7],

  ["MERA", "Healthcare",  780, +1.4],
  ["BIVO", "Healthcare",  610, -2.1],
  ["PHRX", "Healthcare",  490, +0.6],
  ["GENO", "Healthcare",  340, +4.8],
  ["VRTK", "Healthcare",  240, -0.9],
  ["CORP", "Healthcare",  180, +1.2],
  ["NEXO", "Healthcare",  120, -3.4],

  ["ARCM", "Materials",   482, +1.84],   // our ticker
  ["TURM", "Materials",   320, +0.3],
  ["WLDA", "Materials",   240, -1.0],
  ["KOPL", "Materials",   180, +2.2],
  ["RUST", "Materials",   110, -0.5],

  ["DRSH", "Energy",      710, +2.9],
  ["VAUL", "Energy",      520, -1.6],
  ["PETK", "Energy",      390, +0.7],
  ["FRAC", "Energy",      260, +3.4],
  ["LIGN", "Energy",      170, -2.2],

  ["GLBC", "Consumer",    660, +0.9],
  ["TRIB", "Consumer",    480, -0.4],
  ["HAVN", "Consumer",    320, +1.7],
  ["MIRT", "Consumer",    220, -0.8],
  ["SEND", "Consumer",    150, +0.3],

  ["INDX", "Industrials", 580, +1.2],
  ["CRAG", "Industrials", 430, -0.6],
  ["BORA", "Industrials", 310, +0.4],
  ["AXLE", "Industrials", 220, +2.1],
  ["FORG", "Industrials", 160, -1.4],
];

const SECTORS_ORDER = [
  "Tech", "Finance", "Healthcare", "Materials", "Energy", "Consumer", "Industrials",
];

const SECTOR_LEAD = {
  Tech: "var(--cy)",
  Finance: "var(--blue)",
  Healthcare: "var(--violet)",
  Materials: "var(--copper)",
  Energy: "var(--amb)",
  Consumer: "var(--gn)",
  Industrials: "var(--ink-2)",
};

// Sidebar nav
const NAV = [
  { group: "Scan results", items: [
    { id: "market-map",   label: "Market Map",    badge: "live",  kbd: null  },
    { id: "watchlist",    label: "Watchlist",     count: 12             },
    { id: "screener",     label: "Screener"                              },
    { id: "elite",        label: "Elite Picks",   count: 8              },
    { id: "buy",          label: "Bullish candidates",count: 14, badgeColor: "gn" },
    { id: "killed",       label: "Excluded",        count: 31, badgeColor: "rd" },
    { id: "industries",   label: "Industries"                            },
    { id: "themes",       label: "Themes",        count: 6              },
    { id: "leveraged",    label: "Leveraged"                             },
    { id: "crypto",       label: "Crypto"                                },
    { id: "events",       label: "Events · IPO/Splits"                   },
    { id: "premarket",    label: "Pre-Market",    badge: "closed"        },
    { id: "pairs",        label: "Pairs"                                 },
  ]},
  { group: "Strategy & performance", items: [
    { id: "strategies",   label: "Strategies",    count: 11             },
    { id: "performance",  label: "Performance"                           },
    { id: "accuracy",     label: "Accuracy"                              },
    { id: "macro",        label: "Macro · Events"                        },
    { id: "options-flow", label: "Options Flow"                          },
    { id: "alerts",       label: "Alerts",        count: 3, badgeColor: "amb" },
  ]},
  { group: "Knowledge", items: [
    { id: "playbook",     label: "Playbook"                              },
    { id: "reference",    label: "Reference / Cheat"                     },
    { id: "thesis",       label: "Thesis Library"                        },
    { id: "research",     label: "Research"                              },
  ]},
  { group: "Admin", items: [
    { id: "settings",     label: "Settings"                              },
    { id: "status",       label: "System Status", badge: "ok"            },
    { id: "capstudio",    label: "CapStudio · RBAC"                      },
    { id: "audit",        label: "Audit · Change Hx"                     },
    { id: "lab",          label: "Research Lab"                          },
    { id: "factor",       label: "Factor Exposure"                       },
  ]},
];

// The 14 lenses
const LENSES = [
  { id: "overview",    label: "Overview · Bias",    kbd: "1", q: "Should I look closer?",         accent: "copper", verdict: "gn"  },
  { id: "plan",        label: "Plan · Ticket",      kbd: "2", q: "Execution-ready ticket",         accent: "copper", verdict: "gn"  },
  { id: "chart",       label: "Chart",              kbd: "3", q: "Full OHLC + indicators",         accent: "copper", verdict: "gn"  },
  { id: "technicals",  label: "Technicals",         kbd: "T", q: "10-section discipline view",     accent: "cy",     verdict: "gn"  },
  { id: "patterns",    label: "Patterns",           kbd: "4", q: "Chart patterns + Elliott/Wyckoff",accent: "violet", verdict: "gn"  },
  { id: "smc",         label: "SMC",                kbd: "5", q: "Smart Money Concepts",           accent: "cy",     verdict: "gn"  },
  { id: "investment",  label: "Investment · Value", kbd: "V", q: "Intrinsic value & quality",      accent: "blue",   verdict: "amb" },
  { id: "earnings",    label: "Earnings",           kbd: "E", q: "ER countdown & implied move",    accent: "amb",    verdict: "amb" },
  { id: "risk",        label: "Risk",               kbd: "R", q: "VaR · Kelly · drawdown · stress",  accent: "rd",     verdict: "amb" },
  { id: "options",     label: "Options",            kbd: "O", q: "IV · flow · payoff",             accent: "amb",    verdict: "amb" },
  { id: "tape",        label: "Tape · Flow",        kbd: "I", q: "News + insider + 13F",           accent: "violet", verdict: "gn"  },
  { id: "mledge",      label: "AI Edge",            kbd: "M", q: "3-headed model forecast",        accent: "violet", verdict: "gn"  },
];

// Watchlist rows (mock)
const WATCHLIST = [
  { sym: "ARCM", name: "Arclight Materials",   price: 67.42, chg:  1.84, score: 78, verdict: "BUY",   setup: "Cont. breakout" },
  { sym: "NVRH", name: "Novara Health",        price: 142.10,chg:  2.41, score: 71, verdict: "BUY",   setup: "Pullback" },
  { sym: "KLYX", name: "Klystron Logic",       price:  88.30,chg: -0.62, score: 64, verdict: "WATCH", setup: "Base #3" },
  { sym: "ZOTR", name: "Zotran Industries",    price:  41.80,chg:  1.80, score: 69, verdict: "WATCH", setup: "Flag" },
  { sym: "GENO", name: "Genoa Biosystems",     price:  29.40,chg:  4.83, score: 58, verdict: "WATCH", setup: "Gap & go" },
  { sym: "MERC", name: "Mercia Semiconductor", price:  17.20,chg: -2.81, score: 41, verdict: "AVOID", setup: "Failed BO" },
  { sym: "DRSH", name: "Druseh Energy",        price:  56.10,chg:  2.92, score: 66, verdict: "BUY",   setup: "Breakout" },
  { sym: "BIVO", name: "Bivota Pharma",        price:  72.55,chg: -2.10, score: 44, verdict: "AVOID", setup: "Distrib." },
  { sym: "ARGN", name: "Argentum Robotics",    price: 213.40,chg:  3.10, score: 81, verdict: "BUY",   setup: "Cont. BO" },
  { sym: "HARP", name: "Harpoon Capital",      price:  39.10,chg: -0.41, score: 55, verdict: "WATCH", setup: "Range" },
];

// ── Searchable ticker universe (WATCHLIST names ∪ HEATMAP) ──────────
const COMPANY_NAMES = {
  NVRH:"Novara Health", KLYX:"Klystron Logic", ZOTR:"Zotran Industries", TWPN:"Twin Peak Networks",
  FLNX:"Flux Nexus", ARGN:"Argentum Robotics", MERC:"Mercia Semiconductor", OPTH:"Optherion",
  VEKR:"Vektor AI", SPND:"Spindle Cloud", KARO:"Karo Systems", LIRO:"Lirosoft", IPSO:"Ipsotech",
  BRMK:"Brightmark Financial", VLCT:"Velocity Capital", HARP:"Harpoon Capital", KENT:"Kent Trust",
  FOLD:"Foldera Bank", INPR:"Inproova", NUFR:"Nufront Finance", MERA:"Meralux Health", BIVO:"Bivota Pharma",
  PHRX:"Pharexia", GENO:"Genoa Biosystems", VRTK:"Vertik Bio", CORP:"Corpath Medical", NEXO:"Nexora Health",
  ARCM:"Arclight Materials", TURM:"Turmaline Mining", WLDA:"Welda Chemicals", KOPL:"Koppel Metals",
  RUST:"Rustler Resources", DRSH:"Druseh Energy", VAUL:"Vault Petroleum", PETK:"Petrokast", FRAC:"Fractal Energy",
  LIGN:"Lignite Power", GLBC:"Globic Consumer", TRIB:"Tribeca Brands", HAVN:"Haven Goods", MIRT:"Mirato Retail",
  SEND:"Sendoa", INDX:"Indexa Industrial", CRAG:"Cragmont Mfg", BORA:"Borealis Aero", AXLE:"Axle Logistics", FORG:"Forgewright",
};
// ── BULLVEDA real-data override ─────────────────────────────────────
// If the synchronous bootstrap loaded a live universe, replace the mock
// TICKER / WATCHLIST / HEATMAP / SECTOR_LEAD contents IN PLACE (const bindings)
// before any derived universe (TICKER_UNIVERSE below, SS_UNIVERSE in the scanner)
// is computed — so everything downstream is real with zero demo data.
(function () {
  const BV = window.__BV;
  if (!BV || !BV.ready) return; // server unreachable → keep mock as last-resort scaffold
  const _skip = (k) => new RegExp("bvskip=([a-z,]*)?" + k).test(location.search);
  const rows = BV.scanRows();
  const buys = rows.filter(r => r.verdict === "BUY").sort((a, b) => b.score - a.score);
  const featured = (buys[0] || rows.slice().sort((a, b) => b.score - a.score)[0]);
  if (featured && !_skip("ticker")) Object.assign(TICKER, BV.detailFor(featured));
  if (!_skip("wl")) {
    WATCHLIST.length = 0;
    rows.slice().sort((a, b) => b.score - a.score).slice(0, 24).forEach(r => {
      WATCHLIST.push({ sym: r.sym, name: r.name, price: r.price, chg: r.chg,
        score: r.score, verdict: r.verdict, setup: r.setup });
    });
  }
  if (!_skip("hm")) {
    HEATMAP.length = 0;
    rows.slice().sort((a, b) => b.mcap - a.mcap).slice(0, 220).forEach(r => {
      HEATMAP.push([r.sym, r.sector, +r.mcap.toFixed(2), +(r.chg || 0).toFixed(2)]);
    });
  }
  const palette = ["var(--cy)", "var(--blue)", "var(--violet)", "var(--copper)",
    "var(--amb)", "var(--gn)", "var(--ink-2)", "var(--rd)"];
  let pi = 0;
  Array.from(new Set(HEATMAP.map(h => h[1]))).forEach(sec => {
    if (!SECTOR_LEAD[sec]) SECTOR_LEAD[sec] = palette[pi++ % palette.length];
    if (!SECTORS_ORDER.includes(sec)) SECTORS_ORDER.push(sec);
  });
  rows.forEach(r => { if (r.name && r.name !== r.sym) COMPANY_NAMES[r.sym] = r.name; });
  BV.scanReady = true;
})();

const TICKER_UNIVERSE = (() => {
  const m = new Map();
  WATCHLIST.forEach(w => m.set(w.sym, { sym: w.sym, name: w.name, sector: "", inWL: true, score: w.score, verdict: w.verdict }));
  HEATMAP.forEach(([sym, sector]) => { const e = m.get(sym) || { sym }; e.sector = sector; if (!e.name) e.name = COMPANY_NAMES[sym] || sym; m.set(sym, e); });
  if (!m.has(TICKER.symbol)) m.set(TICKER.symbol, { sym: TICKER.symbol, name: TICKER.name, sector: TICKER.sector });
  return [...m.values()].sort((a, b) => a.sym.localeCompare(b.sym));
})();
window.TICKER_UNIVERSE = TICKER_UNIVERSE;

// ── Commercial tier model (cumulative) ──────────────────────────
const TIER_LIST = [
  { id: 0, key: "FREE",    name: "Free",     price: "$0",      tag: "Prove you belong here." },
  { id: 1, key: "STARTER", name: "Starter",  price: "$19.99",  tag: "Real signals. Real time." },
  { id: 2, key: "CORE",    name: "Core",     price: "$49.99",  tag: "The full intelligence layer." },
  { id: 3, key: "PRO",     name: "Pro",      price: "$149",    tag: "Your record. Verified." },
  { id: 4, key: "ELITE",   name: "Elite",    price: "$330",    tag: "Institutional-grade." },
  { id: 5, key: "ADMIN",   name: "Admin",    price: "internal",tag: "Full access · RBAC · system ops." },
];

// Minimum tier required per icon-rail surface
const SURFACE_TIER = {
  home: 0, "signal-scanner": 0, "market-map": 0, watchlist: 0, buy: 0, playbook: 0, settings: 0, status: 0,
  alerts: 1, screener: 1, premarket: 1, "sector-etf": 1, "etf-screener": 1, "options-flow": 1, options: 1, news: 1,
  elite: 2, strategies: 2, themes: 2, momentum: 2, performance: 2, "ai-predict": 2, insider: 2, journal: 2,
  social: 3, "portfolio-srf": 0,
  myportfolios: 0,
  "track-record": 0, "smc-patterns": 1,
  supabase: 0, status: 0, help: 0,
  risk: 2, "earnings-cal": 1, "macro-cal": 0, internals: 1,
  "earnings-ai": 2,
  capstudio: 5, audit: 5, "factor-exposure": 5, lab: 5,
};

// Minimum tier required per per-ticker lens
const LENS_TIER = {
  overview: 0, plan: 2, chart: 1, technicals: 1, patterns: 2, smc: 2, investment: 2,
  risk: 2, earnings: 2, options: 1, portfolio: 2, tape: 1, track: 3, mledge: 2,
};

// ── Section-level access map ────────────────────────────────────
// Every surface decomposes into a few coarse GROUPS, each holding the
// individual PANELS rendered on that surface. Each panel may carry:
//   match : an UPPERCASE substring of the panel's on-screen header
//           (used to locate its .lab-card in the live DOM for gating)
//   sel   : a CSS selector (used instead of match for non-card panels)
// A panel with neither is config-only (no live gate yet).
// Live gating clamps each panel to MAX(surface tier, section override),
// so a section can be raised above its surface but never dropped below it.
const SURFACE_SECTIONS = {
  home: [
    { id: "state", label: "Market state", panels: [
      { id: "hero",  label: "Regime & scan funnel", sel: ".home-hero" },
      { id: "index", label: "Cross-asset index strip", sel: ".ix-strip" },
    ]},
    { id: "opportunity", label: "Opportunity · today's scan", panels: [
      { id: "setups",    label: "Top setups",  match: "TOP SETUPS" },
      { id: "discovery", label: "Discovery",   match: "DISCOVERY" },
      { id: "movers",    label: "Top movers",  match: "TOP MOVERS" },
    ]},
    { id: "attention", label: "Attention · catalysts & flow", panels: [
      { id: "earnings", label: "Earnings today",    match: "EARNINGS TODAY" },
      { id: "stories",  label: "Top stories",       match: "TOP STORIES" },
      { id: "signals",  label: "Overnight signals", match: "OVERNIGHT SIGNALS" },
    ]},
  ],
  premarket: [
    { id: "board", label: "Core board", panels: [
      { id: "read",     label: "Pre-Market Read",        sel: ".pm-read" },
      { id: "tape",     label: "Futures · risk tape",    sel: ".pm-tape" },
      { id: "kpis",     label: "Gap KPI strip",          sel: ".wsx-kpis" },
      { id: "gaptbl",   label: "Gap board (table)",      sel: ".pm-tbl" },
    ]},
    { id: "catalyst", label: "Catalyst & calendar", panels: [
      { id: "macro",    label: "Macro calendar",         match: "MACRO CALENDAR" },
      { id: "earnings", label: "Earnings reporters",     match: "EARNINGS REPORTERS" },
      { id: "wire",     label: "News wire",              match: "NEWS WIRE" },
    ]},
    { id: "risk", label: "Risk & edge", panels: [
      { id: "book",     label: "Your book · exposure",   match: "YOUR BOOK" },
      { id: "secheat",  label: "Sector pre-market heat", match: "SECTOR PRE-MARKET HEAT" },
      { id: "gapstats", label: "Gap statistics · edge",  match: "GAP STATISTICS" },
    ]},
  ],
  options: [
    { id: "tape", label: "Flow tape", panels: [
      { id: "read",   label: "Net-premium flow read",    sel: ".of-read" },
      { id: "kpis",   label: "Flow KPI strip",           sel: ".wsx-kpis" },
      { id: "prints", label: "Smart-money tape (table)", sel: ".of-tape-wrap" },
    ]},
    { id: "analytics", label: "Dealer & vol analytics", panels: [
      { id: "byticker", label: "Net premium · by ticker", match: "NET PREMIUM" },
      { id: "gamma",    label: "Dealer gamma",            match: "DEALER GAMMA" },
      { id: "ivrank",   label: "IV rank · movers",        match: "IV RANK" },
      { id: "expiries", label: "Most-active expiries",    match: "MOST-ACTIVE EXPIRIES" },
    ]},
    { id: "ideas", label: "Options ideas", panels: [
      { id: "tickets", label: "Ranked option tickets", sel: ".oi-wrap, .oi-tbl-wrap, .wsx-body" },
    ]},
  ],
  news: [
    { id: "feed", label: "Feed", panels: [
      { id: "read", label: "Sentiment read banner",  sel: ".nw-read" },
      { id: "main", label: "Headline feed",          sel: ".nw-feed" },
    ]},
    { id: "rail", label: "Intelligence rail", panels: [
      { id: "trend",  label: "Trending tickers",     match: "TRENDING TICKERS" },
      { id: "src",    label: "Source breakdown",     match: "SOURCE BREAKDOWN" },
      { id: "macro",  label: "Macro wire",           match: "MACRO WIRE" },
      { id: "senttr", label: "Sentiment · 24h trend", match: "SENTIMENT" },
    ]},
  ],
  "portfolio-srf": [
    { id: "exposure", label: "Exposure", panels: [
      { id: "alloc",  label: "Sector allocation",        match: "SECTOR ALLOCATION" },
      { id: "factor", label: "Factor exposure",          match: "FACTOR EXPOSURE" },
    ]},
    { id: "attribution", label: "Attribution & returns", panels: [
      { id: "plsleeve", label: "P&L attribution · sleeve", match: "ATTRIBUTION · BY SLEEVE" },
      { id: "plsector", label: "P&L attribution · sector", match: "ATTRIBUTION · BY SECTOR" },
      { id: "corr",     label: "Correlation matrix",       match: "CORRELATION MATRIX" },
      { id: "periodic", label: "Periodic returns",         match: "PERIODIC RETURNS" },
    ]},
    { id: "risk", label: "Risk", panels: [
      { id: "bookrisk", label: "Book risk · live limits",  match: "BOOK RISK" },
      { id: "stress",   label: "Stress · shock scenarios",  match: "STRESS" },
    ]},
  ],
  "sector-etf": [
    { id: "rotation", label: "Rotation", panels: [
      { id: "heatmap",  label: "11-sector heatmap",   match: "SECTOR HEATMAP" },
      { id: "rrg",      label: "RRG rotation quadrant", match: "ROTATION QUADRANT" },
    ]},
    { id: "leadership", label: "Leadership & flow", panels: [
      { id: "lead",     label: "Sector leadership",   match: "SECTOR LEADERSHIP" },
      { id: "velocity", label: "Earnings velocity",   match: "EARNINGS VELOCITY" },
      { id: "xasset",   label: "Cross-asset · thematic ETFs", match: "CROSS-ASSET" },
    ]},
  ],
  momentum: [
    { id: "board", label: "Momentum board", panels: [
      { id: "kpis", label: "Momentum KPI strip", sel: ".wsx-kpis" },
      { id: "tbl",  label: "Leaders table",      sel: ".wsx-body" },
    ]},
    { id: "edge", label: "Edge analytics", panels: [
      { id: "equity", label: "Equity curve · closed signals", match: "EQUITY CURVE" },
      { id: "dist",   label: "Outcome distribution",          match: "OUTCOME DISTRIBUTION" },
    ]},
  ],
  performance: [
    { id: "returns", label: "Returns", panels: [
      { id: "months",   label: "Monthly returns",         match: "MONTHLY RETURNS" },
      { id: "periodic", label: "Periodic returns · vs SPY", match: "PERIODIC RETURNS" },
    ]},
    { id: "attribution", label: "Attribution & shape", panels: [
      { id: "plsleeve", label: "P&L attribution · sleeve", match: "ATTRIBUTION · BY SLEEVE" },
      { id: "plsector", label: "P&L attribution · sector", match: "ATTRIBUTION · BY SECTOR" },
      { id: "rmult",    label: "R-multiple distribution",  match: "R-MULTIPLE DISTRIBUTION" },
    ]},
    { id: "edge", label: "Edge decay", panels: [
      { id: "decay", label: "Edge decay · Wilson LB", match: "EDGE DECAY" },
      { id: "mech",  label: "Mechanism + falsifier",  match: "MECHANISM" },
    ]},
  ],
  playbook: [
    { id: "record", label: "Track record", panels: [
      { id: "cumr",   label: "Cumulative R · equity",    match: "CUMULATIVE R" },
      { id: "rmult",  label: "R-multiple distribution",  match: "R-MULTIPLE DISTRIBUTION" },
      { id: "sleeve", label: "Edge by sleeve · net R",   match: "EDGE BY SLEEVE" },
      { id: "behav",  label: "Behavioral · cost of R",   match: "BEHAVIORAL" },
    ]},
    { id: "process", label: "Process & gates", panels: [
      { id: "activation", label: "Sleeve activation matrix", match: "SLEEVE ACTIVATION MATRIX" },
      { id: "gates",      label: "Entry gates",               match: "ENTRY GATES" },
      { id: "sizing",     label: "Sizing & risk policy",      match: "SIZING" },
    ]},
  ],
  themes: [
    { id: "board", label: "Theme board", panels: [
      { id: "tbl",   label: "Theme table",        sel: ".wsx-body" },
      { id: "cons",  label: "Constituents drill-down", match: "CONSTITUENTS" },
    ]},
  ],
  lab: [
    { id: "research", label: "Research", panels: [
      { id: "hypo",  label: "Hypothesis builder",       match: "HYPOTHESIS" },
      { id: "wf",    label: "Walk-forward results",      match: "WALK-FORWARD" },
      { id: "ic",    label: "Information coefficient",   match: "INFORMATION COEFFICIENT" },
    ]},
    { id: "models", label: "Models & regime", panels: [
      { id: "registry",  label: "Model registry",          match: "MODEL REGISTRY" },
      { id: "winrate",   label: "Setup win-rate × regime",  match: "SETUP WIN-RATE" },
      { id: "transition",label: "Regime transition matrix", match: "REGIME TRANSITION" },
      { id: "sandbox",   label: "Scan-tuning sandbox",      match: "SCAN-TUNING" },
    ]},
  ],
  "signal-scanner": [
    { id: "scanner", label: "Scanner", panels: [
      { id: "tabs",   label: "Result tabs",        sel: ".ss2-tabs" },
      { id: "pills",  label: "Quick-filter pills", sel: ".ss2-pills" },
      { id: "table",  label: "Scanner table",      sel: ".ss2-tbl-wrap" },
    ]},
    { id: "evidence", label: "Evidence", panels: [
      { id: "detail", label: "Detail evidence pane (13 sections)", sel: ".sdp" },
    ]},
  ],
};

// Generic structural fallback for workspace surfaces without a bespoke map
// above — these classes are shared across every "wsx" surface, so the labels
// describe what's really on screen (header KPIs, the filter bar, the table).
const SURFACE_SECTIONS_DEFAULT = [
  { id: "layout", label: "Surface layout", panels: [
    { id: "kpis", label: "Header KPI strip", sel: ".wsx-kpis" },
    { id: "tabs", label: "Filter bar",       sel: ".lab-tabs" },
    { id: "body", label: "Main table / feed", sel: ".wsx-body" },
  ]},
];
function surfaceSections(surface) {
  return SURFACE_SECTIONS[surface] || SURFACE_SECTIONS_DEFAULT;
}

// Per-ticker lens section maps — grouped panels for tier-gating each lens's
// individual sections (mirrors SURFACE_SECTIONS but for the 14 detail lenses).
const LENS_SECTIONS = {
  overview: [
    { id: "verdict", label: "Verdict", panels: [
      { id: "snapshot", label: "Company snapshot · quant read" },
      { id: "confluence", label: "14-lens confluence heatmap" },
      { id: "sleeve", label: "Sleeve attribution · mechanism" },
    ]},
    { id: "audit", label: "Audit & honesty", panels: [
      { id: "gates", label: "Rule-engine · gate cascade" },
      { id: "delta", label: "What changed · 24h delta" },
      { id: "premortem", label: "Pre-mortem · honesty surface" },
    ]},
  ],
  plan: [
    { id: "ticket", label: "The ticket", panels: [
      { id: "entry", label: "Entry · stop · targets" },
      { id: "sizing", label: "Position sizing · R" },
      { id: "exits", label: "Exit ladder · scale plan" },
    ]},
    { id: "context", label: "Context", panels: [
      { id: "checklist", label: "Pre-trade checklist" },
      { id: "scenarios", label: "Scenario tree" },
    ]},
  ],
  chart: [
    { id: "price", label: "Price action", panels: [
      { id: "candles", label: "Candlestick chart" },
      { id: "volume", label: "Volume profile" },
      { id: "levels", label: "Key levels · S/R" },
    ]},
    { id: "overlays", label: "Overlays", panels: [
      { id: "ma", label: "Moving averages" },
      { id: "anno", label: "Pattern annotations" },
    ]},
  ],
  technicals: [
    { id: "trend", label: "Trend", panels: [
      { id: "ma", label: "MA stack · alignment" },
      { id: "adx", label: "ADX · trend strength" },
    ]},
    { id: "momentum", label: "Momentum", panels: [
      { id: "rsi", label: "RSI · stochastics" },
      { id: "macd", label: "MACD" },
    ]},
    { id: "vol", label: "Volatility & volume", panels: [
      { id: "atr", label: "ATR · Bollinger" },
      { id: "rvol", label: "Relative volume" },
    ]},
  ],
  patterns: [
    { id: "engine", label: "Confluence engine", panels: [
      { id: "composite", label: "Weighted composite · MTF" },
    ]},
    { id: "theories", label: "Theories", panels: [
      { id: "wyckoff", label: "Wyckoff" },
      { id: "elliott", label: "Elliott Wave" },
      { id: "fibonacci", label: "Fibonacci" },
      { id: "volprofile", label: "Volume Profile" },
      { id: "ichimoku", label: "Ichimoku" },
      { id: "td", label: "TD Sequential" },
      { id: "classical", label: "Classical" },
      { id: "harmonic", label: "Harmonic" },
      { id: "wolfe", label: "Wolfe Wave" },
      { id: "candles", label: "Candlesticks" },
      { id: "altcharts", label: "Alt charts" },
      { id: "gann", label: "Gann" },
      { id: "montecarlo", label: "Monte Carlo" },
    ]},
  ],
  smc: [
    { id: "structure", label: "Market structure", panels: [
      { id: "bos", label: "Break of structure · CHoCH" },
      { id: "confluence", label: "Cross-discipline confluence" },
    ]},
    { id: "liquidity", label: "Liquidity", panels: [
      { id: "ob", label: "Order blocks" },
      { id: "fvg", label: "Fair value gaps" },
      { id: "sweeps", label: "Liquidity sweeps · stop-runs" },
    ]},
    { id: "zones", label: "Zones", panels: [
      { id: "pd", label: "Premium / discount equilibrium" },
      { id: "ote", label: "Optimal trade entry" },
    ]},
  ],
  investment: [
    { id: "valuation", label: "Valuation", panels: [
      { id: "iv", label: "Price vs intrinsic value · 5y" },
      { id: "mos", label: "Margin of safety" },
      { id: "quality", label: "Quality scorecard" },
    ]},
    { id: "capital", label: "Capital & statements", panels: [
      { id: "peer", label: "Peer comparison" },
      { id: "stmts", label: "Statement trends" },
      { id: "alloc", label: "Capital allocation" },
    ]},
    { id: "thesis", label: "Thesis", panels: [
      { id: "bullbear", label: "Bull vs bear" },
      { id: "catalysts", label: "Catalyst calendar" },
    ]},
  ],
  risk: [
    { id: "loss", label: "Loss & sizing", panels: [
      { id: "cones", label: "Loss-Distribution Cones" },
      { id: "kelly", label: "Live Kelly · Sizing Metrics" },
      { id: "var", label: "VaR · CVaR · Sharpe" },
    ]},
    { id: "stress", label: "Stress & liquidity", panels: [
      { id: "stress", label: "Stress · 6 × 5 Heatmap" },
      { id: "ladder", label: "Liquidity Ladder · β exposure" },
    ]},
  ],
  earnings: [
    { id: "countdown", label: "Countdown", panels: [
      { id: "cone", label: "ER countdown · implied-move cone" },
      { id: "beat", label: "Beat probability" },
    ]},
    { id: "history", label: "History & drift", panels: [
      { id: "revisions", label: "Analyst EPS revisions" },
      { id: "track", label: "8-quarter beat history" },
      { id: "pead", label: "Post-earnings drift · PEAD" },
    ]},
  ],
  options: [
    { id: "surface", label: "Vol surface", panels: [
      { id: "iv", label: "IV term structure" },
      { id: "skew", label: "Skew · smile" },
    ]},
    { id: "flow", label: "Flow & positioning", panels: [
      { id: "unusual", label: "Unusual options flow" },
      { id: "oi", label: "Open interest · max pain" },
    ]},
    { id: "strategy", label: "Strategy", panels: [
      { id: "spreads", label: "Suggested spreads" },
    ]},
  ],
  portfolio: [
    { id: "holdings", label: "Holdings", panels: [
      { id: "positions", label: "Position · weight · P&L" },
    ]},
    { id: "attribution", label: "Attribution & returns", panels: [
      { id: "sleeve", label: "P&L attribution · sleeve" },
      { id: "sector", label: "P&L attribution · sector" },
      { id: "corr", label: "Correlation matrix" },
      { id: "periodic", label: "Periodic returns" },
    ]},
    { id: "risk", label: "Risk", panels: [
      { id: "book", label: "Book risk · live limits" },
      { id: "stress", label: "Stress · shock scenarios" },
    ]},
  ],
  tape: [
    { id: "flow", label: "Order flow", panels: [
      { id: "prints", label: "Time & sales · prints" },
      { id: "blocks", label: "Block trades · sweeps" },
    ]},
    { id: "levels", label: "Levels", panels: [
      { id: "vwap", label: "VWAP · anchored bands" },
    ]},
  ],
  track: [
    { id: "returns", label: "Returns", panels: [
      { id: "equity", label: "Equity curve" },
      { id: "rmult", label: "R-multiple distribution" },
      { id: "periodic", label: "Periodic returns" },
    ]},
    { id: "attribution", label: "Attribution", panels: [
      { id: "sleeve", label: "Edge by sleeve · net R" },
      { id: "behav", label: "Behavioral · cost of R" },
    ]},
  ],
  mledge: [
    { id: "model", label: "Model output", panels: [
      { id: "prediction", label: "Probability of success" },
      { id: "features", label: "Feature contributions" },
    ]},
    { id: "validation", label: "Validation", panels: [
      { id: "backtest", label: "Backtest metrics" },
      { id: "regime", label: "Win-rate × regime" },
    ]},
  ],
};
function lensSections(lensId) {
  return LENS_SECTIONS[lensId] || [
    { id: "main", label: "Sections", panels: [{ id: "body", label: "Lens body" }] },
  ];
}

// Live section overrides (mutable, edited from Tier Access · Configure)
const SECTION_TIER = {            // "surface:panelId" -> override min tier
  "premarket:gapstats": 4,        // backtested edge → Elite analytics
  "options:gamma": 4,        // dealer gamma → Elite
  "options:expiries": 2,
  "news:senttr": 2,
  "portfolio-srf:stress": 4,
  "performance:decay": 3,
  "premarket:secheat": 2,
};
const SECTION_OFF = {             // "surface:panelId" -> true when disabled
};
function sectionKey(s, p) { return s + ":" + p; }
function sectionTier(surface, panelId) {
  const base = surface.indexOf("lens:") === 0
    ? ((window.LENS_TIER || {})[surface.slice(5)] ?? 0)
    : ((window.SURFACE_TIER || {})[surface] ?? 0);
  const ov = (window.SECTION_TIER || {})[sectionKey(surface, panelId)];
  return Math.max(base, ov == null ? 0 : ov);
}
function sectionOff(surface, panelId) {
  return !!(window.SECTION_OFF || {})[sectionKey(surface, panelId)];
}

// ══════════════════════════════════════════════════════════════════════
// ⚠ BACKEND INTEGRATION SEAM — User watchlist store
// ----------------------------------------------------------------------
// PROTOTYPE: persistence is localStorage-only (client-side mock).
// PRODUCTION: replace the localStorage calls in `_save` + the initial
// `_wlLoad` reads with the watchlist service. Suggested contract:
//   GET    /api/watchlist            -> { added:[{sym,...}], removed:[sym] }
//   POST   /api/watchlist/{sym}      (body: ticker record)   // add
//   DELETE /api/watchlist/{sym}                              // remove
// Also reconcile with "Signal Scanner stars" (the header sub-text promises
// this list is synced from starred scanner rows). Keep the "watchlist-change"
// event so the rail badge, detail-panel button, and Watchlist surface stay
// in sync. Search this file for `WL_ADD_KEY` to find every touch-point.
// ══════════════════════════════════════════════════════════════════════
// Base WATCHLIST is always present; users add/remove on top. Membership =
// (base ∪ added) − removed. Emits "watchlist-change" so the UI re-renders.
const WL_ADD_KEY = "swingtrade.wl.added";
const WL_REM_KEY = "swingtrade.wl.removed";
const _wlBase = new Set(WATCHLIST.map(w => w.sym));
const _wlLoad = (k, fb) => { try { return JSON.parse(localStorage.getItem(k)) ?? fb; } catch (e) { return fb; } };
let _wlAdded = _wlLoad(WL_ADD_KEY, {});      // INTEGRATION: load from GET /api/watchlist instead
let _wlRemoved = new Set(_wlLoad(WL_REM_KEY, []));
const WatchStore = {
  has: (sym) => (!!_wlAdded[sym] || _wlBase.has(sym)) && !_wlRemoved.has(sym),
  isBase: (sym) => _wlBase.has(sym),
  add: (rec) => {
    const s = rec && rec.sym; if (!s) return;
    _wlRemoved.delete(s);
    if (!_wlBase.has(s)) _wlAdded[s] = { ...rec };
    WatchStore._save();
  },
  remove: (sym) => {
    delete _wlAdded[sym];
    if (_wlBase.has(sym)) _wlRemoved.add(sym);
    WatchStore._save();
  },
  toggle: (rec) => { const s = rec && rec.sym; if (!s) return; WatchStore.has(s) ? WatchStore.remove(s) : WatchStore.add(rec); },
  added: () => Object.values(_wlAdded).filter(r => !_wlRemoved.has(r.sym)),
  removed: () => _wlRemoved,
  count: () => [...new Set([..._wlBase, ...Object.keys(_wlAdded)])].filter(s => !_wlRemoved.has(s)).length,
  _save: () => {
    try {
      // INTEGRATION: replace these two writes with POST/DELETE /api/watchlist/{sym}
      localStorage.setItem(WL_ADD_KEY, JSON.stringify(_wlAdded));
      localStorage.setItem(WL_REM_KEY, JSON.stringify([..._wlRemoved]));
    } catch (e) {}
    window.dispatchEvent(new CustomEvent("watchlist-change"));
  },
};

// ── SEC-safe display labels ─────────────────────────────────────────
// Internal verdict codes (BUY/WATCH/SHORT/AVOID/SELL/HOLD) drive logic &
// filters; these map them to DESCRIPTIVE, non-prescriptive display text so
// the UI reads as informational analysis of a directional bias rather than
// an instruction to transact. Never render a raw verdict — always secBias().
const SEC_BIAS = {
  BUY:   { label: "Bullish", tone: "gn"  },
  WATCH: { label: "Neutral", tone: "amb" },
  HOLD:  { label: "Neutral", tone: "amb" },
  SHORT: { label: "Bearish", tone: "rd"  },
  SELL:  { label: "Bearish", tone: "rd"  },
  AVOID: { label: "Bearish", tone: "rd"  },
  PASS:  { label: "Bearish", tone: "rd"  },
};
function secBias(v) { return (SEC_BIAS[v] && SEC_BIAS[v].label) || v; }
function secBiasTone(v) { return (SEC_BIAS[v] && SEC_BIAS[v].tone) || "amb"; }
const SEC_DISCLAIMER = "Informational and educational analytics only — not investment advice or a recommendation to buy or sell any security. Signals describe a quantitative directional bias, not a solicitation. Paper mode · no live orders. Past performance does not guarantee future results.";
const SEC_DISCLAIMER_SHORT = "Informational only · not investment advice · paper mode";

Object.assign(window, {
  TICKER, HEATMAP, SECTORS_ORDER, SECTOR_LEAD, NAV, LENSES, WATCHLIST,
  TIER_LIST, SURFACE_TIER, LENS_TIER,
  SURFACE_SECTIONS, SURFACE_SECTIONS_DEFAULT, surfaceSections,
  LENS_SECTIONS, lensSections,
  SECTION_TIER, SECTION_OFF, sectionKey, sectionTier, sectionOff,
  WatchStore,
  secBias, secBiasTone, SEC_BIAS, SEC_DISCLAIMER, SEC_DISCLAIMER_SHORT,
});
