/* global window */

/* Mock data for the terminal. Plausible swing-trading universe. */

const MACRO = [
  { sym: 'SPX',  val: '5,847.21', chg: +0.42, spark: 'up' },
  { sym: 'NDX',  val: '20,512.4', chg: +0.61, spark: 'up' },
  { sym: 'RUT',  val: '2,318.7',  chg: -0.18, spark: 'flat' },
  { sym: 'VIX',  val: '14.20',    chg: -3.10, spark: 'down', invert: true },
  { sym: 'DXY',  val: '102.41',   chg: +0.12, spark: 'flat' },
  { sym: 'US10Y',val: '4.213%',   chg: -0.04, spark: 'down', invert: true },
  { sym: 'GOLD', val: '$2,418',   chg: +0.31, spark: 'up' },
  { sym: 'WTI',  val: '$78.42',   chg: -1.24, spark: 'down' },
];

const TAPE = [
  ['NVDA',192.40,1.84],['AVGO',1742.10,0.92],['META',612.30,0.41],['MSFT',432.18,0.55],
  ['GOOGL',182.44,1.12],['TSLA',248.10,-2.14],['AMD',164.20,2.01],['PANW',382.41,-0.22],
  ['SHOP',98.10,1.10],['CRWD',342.50,0.66],['NOW',912.40,0.34],['UBER',76.10,1.45],
  ['LLY',812.30,0.88],['COIN',218.40,3.12],['MARA',18.40,-1.21],['XOM',104.20,-1.40],
  ['JPM',218.40,0.21],['BRK.B',432.10,0.11],['UNH',542.10,-0.42],['HD',412.40,0.38]
];

const SECTORS = [
  { name: 'SEMIS',     pct: +1.84, vol: '4.2B', winners: 12, losers: 2 },
  { name: 'SOFTWARE',  pct: +0.91, vol: '3.1B', winners: 18, losers: 6 },
  { name: 'CONSUMER',  pct: +0.42, vol: '2.4B', winners: 14, losers: 8 },
  { name: 'FINANCE',   pct: +0.04, vol: '5.8B', winners: 22, losers: 22 },
  { name: 'HEALTH',    pct: -0.18, vol: '2.9B', winners: 12, losers: 16 },
  { name: 'STAPLES',   pct: +0.10, vol: '1.6B', winners: 10, losers: 9  },
  { name: 'UTIL',      pct: -0.62, vol: '0.9B', winners: 4,  losers: 14 },
  { name: 'ENERGY',    pct: -1.42, vol: '2.1B', winners: 3,  losers: 18 },
  { name: 'MATERIALS', pct: -0.34, vol: '1.1B', winners: 6,  losers: 11 },
];

const INTEL = [
  { t: '13:42', sym: 'NVDA', text: '<b>Citi</b> raises PT to $215 — cites datacenter capex acceleration', sent: 'up' },
  { t: '12:55', sym: 'AVGO', text: '<b>VMware</b> integration ahead of plan, mgmt reaffirms FY guide', sent: 'up' },
  { t: '12:14', sym: 'AMD',  text: 'Supply chain note flags MI300 lead times slipping 2 weeks', sent: 'nu' },
  { t: '11:30', sym: 'MKT',  text: '<b>CPI</b> +2.4% YoY in line — risk-on bid across growth names', sent: 'up' },
  { t: '11:02', sym: 'TSLA', text: 'Q1 deliveries miss by 4%; FSD progress noted but margins compress', sent: 'dn' },
  { t: '10:14', sym: 'PANW', text: 'Defense win — $1.2B 5-year IDIQ contract awarded', sent: 'up' },
  { t: '09:55', sym: 'NVDA', text: '<b>CES</b> keynote details leak — new edge inference SKU', sent: 'nu' },
  { t: '09:22', sym: 'XOM',  text: 'Refining margins compressed Q-on-Q, downgrade at JPM', sent: 'dn' },
  { t: '08:14', sym: 'TSMC', text: 'TSMC capex raised to $42B for 2026 — bullish for semi cap-ex chain', sent: 'up' },
];

/* Watchlist universe — 22 tickers. */
const WATCHLIST = [
  { rank:1,  sym:'NVDA', name:'NVIDIA Corp',          sect:'SEMI', cap:'4.7T', setup:'Bull flag · D1',
    bap:88, tech:74, fund:91, smc:68, intel:84,
    px:192.40, chg:+1.84, d5:+4.2, d20:+11.4, rvol:1.4,
    stage:'READY', earn:12, news:'up',
    entry:[189,194], stop:182, t1:208, t2:224, lo:175, hi:230 },
  { rank:2,  sym:'AVGO', name:'Broadcom Inc',         sect:'SEMI', cap:'820B', setup:'Bull flag · D1',
    bap:82, tech:78, fund:85, smc:72, intel:74,
    px:1742.10, chg:+0.92, d5:+2.8, d20:+8.4, rvol:1.2,
    stage:'READY', earn:null, news:'up',
    entry:[1720,1755], stop:1670, t1:1880, t2:1980, lo:1620, hi:2020 },
  { rank:3,  sym:'META', name:'Meta Platforms',       sect:'INET', cap:'1.5T', setup:'Pullback to 50',
    bap:79, tech:71, fund:84, smc:64, intel:72,
    px:612.30, chg:+0.41, d5:-1.2, d20:+5.1, rvol:0.9,
    stage:'READY', earn:8, news:'up',
    entry:[605,618], stop:585, t1:650, t2:684, lo:560, hi:700 },
  { rank:4,  sym:'PANW', name:'Palo Alto Networks',   sect:'CYBR', cap:'124B', setup:'Cup & handle',
    bap:76, tech:68, fund:79, smc:71, intel:78,
    px:382.41, chg:-0.22, d5:+0.8, d20:+6.2, rvol:1.1,
    stage:'READY', earn:22, news:'up',
    entry:[378,388], stop:362, t1:412, t2:438, lo:340, hi:450 },
  { rank:5,  sym:'SHOP', name:'Shopify Inc',          sect:'INET', cap:'128B', setup:'Breakout retest',
    bap:74, tech:78, fund:62, smc:74, intel:66,
    px:98.10, chg:+1.10, d5:+3.4, d20:+9.1, rvol:1.5,
    stage:'READY', earn:null, news:'nu',
    entry:[96,100], stop:91, t1:108, t2:118, lo:84, hi:122 },
  { rank:6,  sym:'MSFT', name:'Microsoft Corp',       sect:'SOFT', cap:'3.2T', setup:'Trail · base',
    bap:72, tech:66, fund:82, smc:62, intel:70,
    px:432.18, chg:+0.55, d5:+1.4, d20:+4.2, rvol:0.8,
    stage:'IN TRADE', earn:18, news:'nu',
    entry:[420,435], stop:408, t1:462, t2:482, lo:390, hi:495 },
  { rank:7,  sym:'GOOGL',name:'Alphabet Inc',         sect:'INET', cap:'2.3T', setup:'Stage 2 trend',
    bap:70, tech:72, fund:78, smc:60, intel:64,
    px:182.44, chg:+1.12, d5:+2.1, d20:+5.8, rvol:1.0,
    stage:'IN TRADE', earn:9, news:'up',
    entry:[178,184], stop:172, t1:198, t2:212, lo:164, hi:222 },
  { rank:8,  sym:'CRWD', name:'CrowdStrike',          sect:'CYBR', cap:'82B',  setup:'Base building',
    bap:68, tech:64, fund:74, smc:58, intel:68,
    px:342.50, chg:+0.66, d5:+1.2, d20:+3.4, rvol:0.9,
    stage:'WATCH', earn:31, news:'nu',
    entry:[338,348], stop:322, t1:368, t2:388, lo:308, hi:402 },
  { rank:9,  sym:'NOW',  name:'ServiceNow',           sect:'SOFT', cap:'190B', setup:'Wait trigger',
    bap:66, tech:60, fund:78, smc:56, intel:60,
    px:912.40, chg:+0.34, d5:-0.4, d20:+2.1, rvol:0.7,
    stage:'WATCH', earn:14, news:'nu',
    entry:[905,924], stop:875, t1:962, t2:1004, lo:840, hi:1040 },
  { rank:10, sym:'UBER', name:'Uber Technologies',    sect:'CONS', cap:'162B', setup:'Above 200',
    bap:64, tech:62, fund:68, smc:54, intel:64,
    px:76.10, chg:+1.45, d5:+1.8, d20:+4.1, rvol:1.1,
    stage:'WATCH', earn:25, news:'up',
    entry:[75,77], stop:71, t1:82, t2:88, lo:68, hi:92 },
  { rank:11, sym:'LLY',  name:'Eli Lilly',            sect:'HLTH', cap:'780B', setup:'Cooling base',
    bap:62, tech:58, fund:74, smc:52, intel:60,
    px:812.30, chg:+0.88, d5:-2.1, d20:-1.4, rvol:0.9,
    stage:'WATCH', earn:6, news:'nu',
    entry:[800,820], stop:768, t1:868, t2:912, lo:740, hi:940 },
  { rank:12, sym:'COIN', name:'Coinbase',             sect:'FIN',  cap:'52B',  setup:'High vol · choppy',
    bap:55, tech:52, fund:48, smc:60, intel:64,
    px:218.40, chg:+3.12, d5:+5.1, d20:+12.4, rvol:1.8,
    stage:'WATCH', earn:32, news:'up',
    entry:[212,224], stop:198, t1:248, t2:272, lo:182, hi:288 },
  { rank:13, sym:'JPM',  name:'JPMorgan Chase',       sect:'FIN',  cap:'620B', setup:'Stage 1',
    bap:54, tech:48, fund:62, smc:50, intel:56,
    px:218.40, chg:+0.21, d5:+0.4, d20:+1.1, rvol:0.7,
    stage:'WATCH', earn:11, news:'nu',
    entry:[216,222], stop:208, t1:232, t2:244, lo:198, hi:252 },
  { rank:14, sym:'HD',   name:'Home Depot',           sect:'CONS', cap:'412B', setup:'Sideways',
    bap:50, tech:46, fund:56, smc:48, intel:50,
    px:412.40, chg:+0.38, d5:-0.2, d20:+0.4, rvol:0.6,
    stage:'WATCH', earn:28, news:'nu',
    entry:[408,418], stop:395, t1:434, t2:452, lo:380, hi:464 },
  { rank:15, sym:'AAPL', name:'Apple Inc',            sect:'CONS', cap:'3.4T', setup:'Failing',
    bap:45, tech:42, fund:54, smc:38, intel:48,
    px:228.20, chg:-0.42, d5:-1.4, d20:-2.1, rvol:0.9,
    stage:'COOLING', earn:21, news:'nu',
    entry:[226,232], stop:218, t1:242, t2:254, lo:210, hi:262 },
  { rank:16, sym:'MARA', name:'Marathon Digital',     sect:'FIN',  cap:'5.2B', setup:'Wait reset',
    bap:42, tech:48, fund:32, smc:46, intel:38,
    px:18.40, chg:-1.21, d5:-3.1, d20:-8.4, rvol:1.4,
    stage:'COOLING', earn:38, news:'nu',
    entry:[18,19.2], stop:16.8, t1:21.2, t2:23.4, lo:15.2, hi:24.8 },
  { rank:17, sym:'TSLA', name:'Tesla Inc',            sect:'CONS', cap:'782B', setup:'Failed breakout',
    bap:38, tech:34, fund:42, smc:32, intel:44,
    px:248.10, chg:-2.14, d5:-3.4, d20:-8.1, rvol:1.6,
    stage:'COOLING', earn:14, news:'dn',
    entry:[244,252], stop:232, t1:268, t2:284, lo:218, hi:292 },
  { rank:18, sym:'XOM',  name:'Exxon Mobil',          sect:'ENRG', cap:'412B', setup:'Distribution',
    bap:32, tech:28, fund:48, smc:24, intel:32,
    px:104.20, chg:-1.40, d5:-2.8, d20:-5.4, rvol:1.2,
    stage:'COOLING', earn:9, news:'dn',
    entry:[102,106], stop:97, t1:112, t2:118, lo:91, hi:124 },
  { rank:19, sym:'UNH',  name:'UnitedHealth',         sect:'HLTH', cap:'520B', setup:'Below 200',
    bap:30, tech:26, fund:54, smc:24, intel:36,
    px:542.10, chg:-0.42, d5:-3.8, d20:-7.2, rvol:1.1,
    stage:'COOLING', earn:16, news:'dn',
    entry:[538,548], stop:518, t1:572, t2:598, lo:498, hi:610 },
  { rank:20, sym:'CVX',  name:'Chevron Corp',         sect:'ENRG', cap:'298B', setup:'Stage 4',
    bap:28, tech:22, fund:46, smc:20, intel:30,
    px:148.10, chg:-1.12, d5:-2.4, d20:-4.8, rvol:0.9,
    stage:'COOLING', earn:13, news:'dn',
    entry:[146,150], stop:138, t1:158, t2:166, lo:132, hi:172 },
];

/* Score sub-pillars for the focused ticker (NVDA) */
const PILLARS = {
  TECH: [
    { name:'Trend',         val:'Stage 2',  pts:18, max:20 },
    { name:'Momentum',      val:'+11.4 / 20D', pts:14, max:20 },
    { name:'Volume',        val:'1.4× RVOL',  pts:18, max:20 },
    { name:'Pattern',       val:'Bull flag',  pts:14, max:20 },
    { name:'Rel. Strength', val:'+8 vs SPX', pts:15, max:20 },
  ],
  FUND: [
    { name:'Growth',        val:'+82% YoY rev',  pts:46, max:50 },
    { name:'Profitability', val:'76% gross',    pts:44, max:50 },
    { name:'Quality',       val:'42% ROIC',     pts:43, max:50 },
    { name:'Valuation',     val:'42x fwd',      pts:28, max:50 },
    { name:'Momentum',      val:'8/8 beats',    pts:48, max:50 },
  ],
  SMC: [
    { name:'BOS',           val:'D1 · 4w ago',  pts:14, max:20 },
    { name:'Order Block',   val:'$185 demand',  pts:16, max:20 },
    { name:'FVG',           val:'$190-192',     pts:14, max:20 },
    { name:'Liquidity',     val:'sweep at $179',pts:12, max:20 },
  ],
};

/* Simple SVG path generator for sparklines */
function genSpark(seed, n = 24, trend = 0) {
  let v = 50; const pts = [];
  let s = seed;
  for (let i = 0; i < n; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = (s / 233280) - 0.5;
    v += r * 8 + trend;
    v = Math.max(10, Math.min(90, v));
    pts.push(v);
  }
  return pts;
}

/* Candle data for the hero chart — generates a believable 90-bar candle stream */
function genCandles(n = 90, seed = 42, end = 192.4) {
  let s = seed;
  const out = [];
  let close = end - 30;
  for (let i = 0; i < n; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = (s / 233280) - 0.45;
    const open = close;
    const wick = 1.5 + Math.abs(r) * 3;
    const body = r * 2.4 + (i / n) * 0.6;
    close = open + body + (i % 11 === 0 ? r * 4 : 0);
    const high = Math.max(open, close) + wick * Math.random();
    const low  = Math.min(open, close) - wick * Math.random();
    out.push({ open, high, low, close, vol: 0.4 + Math.abs(r) * 1.2 });
  }
  // calibrate so the last close ~= end
  const last = out[out.length - 1].close;
  const offset = end - last;
  return out.map(c => ({ open: c.open + offset, high: c.high + offset, low: c.low + offset, close: c.close + offset, vol: c.vol }));
}

window.ST_DATA = { MACRO, TAPE, SECTORS, INTEL, WATCHLIST, PILLARS, genSpark, genCandles };
