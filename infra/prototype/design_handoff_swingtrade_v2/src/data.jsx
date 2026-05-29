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
    { id: "buy",          label: "BUY candidates",count: 14, badgeColor: "gn" },
    { id: "killed",       label: "Killed / AVOID",count: 31, badgeColor: "rd" },
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
  { id: "overview",    label: "Overview · Verdict", kbd: "1", q: "Should I look closer?",         accent: "copper", verdict: "gn"  },
  { id: "plan",        label: "Plan · Ticket",      kbd: "2", q: "Execution-ready ticket",         accent: "copper", verdict: "gn"  },
  { id: "chart",       label: "Chart",              kbd: "3", q: "Full OHLC + indicators",         accent: "copper", verdict: "gn"  },
  { id: "technicals",  label: "Technicals",         kbd: "T", q: "10-section discipline view",     accent: "cy",     verdict: "gn"  },
  { id: "patterns",    label: "Patterns",           kbd: "4", q: "Chart patterns + Elliott/Wyckoff",accent: "violet", verdict: "gn"  },
  { id: "smc",         label: "SMC",                kbd: "5", q: "Smart Money Concepts",           accent: "cy",     verdict: "gn"  },
  { id: "investment",  label: "Investment · Value", kbd: "V", q: "Intrinsic value & quality",      accent: "blue",   verdict: "amb" },
  { id: "risk",        label: "Risk",               kbd: "R", q: "VaR · Kelly · stress",           accent: "rd",     verdict: "gn"  },
  { id: "earnings",    label: "Earnings",           kbd: "E", q: "ER countdown & implied move",    accent: "amb",    verdict: "amb" },
  { id: "options",     label: "Options",            kbd: "O", q: "IV · flow · payoff",             accent: "amb",    verdict: "amb" },
  { id: "portfolio",   label: "Portfolio",          kbd: "P", q: "Cap usage & correlation",        accent: "copper", verdict: "gn"  },
  { id: "tape",        label: "Tape · Flow",        kbd: "I", q: "News + insider + 13F",           accent: "violet", verdict: "gn"  },
  { id: "track",       label: "Track Record",       kbd: "7", q: "Has this setup worked?",         accent: "gn",     verdict: "gn"  },
  { id: "mledge",      label: "ML Edge",            kbd: "M", q: "3-headed model forecast",        accent: "violet", verdict: "gn"  },
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

Object.assign(window, {
  TICKER, HEATMAP, SECTORS_ORDER, SECTOR_LEAD, NAV, LENSES, WATCHLIST,
});
