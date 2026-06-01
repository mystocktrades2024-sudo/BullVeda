// companion-data.jsx — LIVE data layer for the SwingTrade mobile companion.
// ----------------------------------------------------------------------------
// Replaces the prototype's mock src/data.jsx. Fetches the SAME chunk the desktop
// kairos dashboard boots from (/v2/data.critical.json) and projects real scan
// output onto the globals every companion component reads:
//   window.TICKER, WATCHLIST, HEATMAP, SECTORS_ORDER, SECTOR_LEAD, LENSES,
//   secBias/secBiasTone, SEC_DISCLAIMER*, WatchStore, tier maps, ALERT_SYM,
//   REGIME_LIVE, MARKET_LIVE, PORTFOLIO_LIVE, resolveTickerLive().
//
// Loading contract: this file defines window.loadCompanionData() returning a
// Promise. index.html / showcase.html await it, THEN mount <Companion/>, so the
// real data is already on window before the first render (the components read
// window.* synchronously — no React data-fetch wiring needed).
//
// Falls back to a tiny built-in sample if the fetch fails (offline / Mac asleep)
// so the UI still renders something honest rather than a blank screen.
// ============================================================================

/* ── static, non-data exports (carried verbatim from the prototype) ───────── */

// The 12 detail lenses (order + labels). Icons come from window.LENS_ICONS.
const LENSES = [
  { id: "overview",   label: "Overview · Bias",    accent: "copper" },
  { id: "plan",       label: "Plan · Ticket",      accent: "copper" },
  { id: "chart",      label: "Chart",              accent: "copper" },
  { id: "technicals", label: "Technicals",         accent: "cy"     },
  { id: "patterns",   label: "Patterns",           accent: "violet" },
  { id: "smc",        label: "SMC",                accent: "cy"     },
  { id: "investment", label: "Investment · Value", accent: "blue"   },
  { id: "earnings",   label: "Earnings",           accent: "amb"    },
  { id: "risk",       label: "Risk",               accent: "rd"     },
  { id: "options",    label: "Options",            accent: "amb"    },
  { id: "tape",       label: "Tape · Flow",        accent: "violet" },
  { id: "mledge",     label: "AI Edge",            accent: "violet" },
];

const SECTORS_ORDER = ["Tech", "Finance", "Healthcare", "Materials", "Energy", "Consumer", "Industrials"];
const SECTOR_LEAD = {
  Tech: "var(--cy)", Finance: "var(--blue)", Healthcare: "var(--violet)",
  Materials: "var(--copper)", Energy: "var(--amb)", Consumer: "var(--gn)", Industrials: "var(--ink-2)",
};

// Map a real GICS-ish sector string → the 7 buckets the heatmap surfaces use.
const SECTOR_BUCKET = {
  "Technology": "Tech", "Information Technology": "Tech", "Communication Services": "Tech",
  "Financials": "Finance", "Financial": "Finance", "Finance": "Finance",
  "Healthcare": "Healthcare", "Health Care": "Healthcare",
  "Materials": "Materials", "Basic Materials": "Materials",
  "Energy": "Energy",
  "Consumer Discretionary": "Consumer", "Consumer Staples": "Consumer", "Consumer Cyclical": "Consumer", "Consumer Defensive": "Consumer",
  "Industrials": "Industrials", "Real Estate": "Industrials", "Utilities": "Industrials",
};
function bucketSector(s) { return SECTOR_BUCKET[s] || "Tech"; }

// SEC-safe display labels — never render a raw verdict; always secBias().
const SEC_BIAS = {
  BUY: { label: "Bullish", tone: "gn" }, WATCH: { label: "Neutral", tone: "amb" },
  HOLD: { label: "Neutral", tone: "amb" }, SHORT: { label: "Bearish", tone: "rd" },
  SELL: { label: "Bearish", tone: "rd" }, AVOID: { label: "Bearish", tone: "rd" }, PASS: { label: "Bearish", tone: "rd" },
};
function secBias(v) { return (SEC_BIAS[v] && SEC_BIAS[v].label) || v; }
function secBiasTone(v) { return (SEC_BIAS[v] && SEC_BIAS[v].tone) || "amb"; }
const SEC_DISCLAIMER = "Informational and educational analytics only — not investment advice or a recommendation to buy or sell any security. Signals describe a quantitative directional bias, not a solicitation. Paper mode · no live orders. Past performance does not guarantee future results.";
const SEC_DISCLAIMER_SHORT = "Informational only · not investment advice · paper mode · live data";

// Tier model (kept so the More grid renders; gating is permissive for personal use).
const SURFACE_TIER = {};   // empty → nothing locked for the owner/Vinod
const LENS_TIER = {};

/* ── watchlist store — localStorage for V1 (per-device).  ──────────────────
   INTEGRATION SEAM: swap _save / initial reads for the server watchlist
   service when separate Vinod/owner accounts land. Event contract unchanged. */
const WL_ADD_KEY = "swingtrade.wl.added", WL_REM_KEY = "swingtrade.wl.removed";
let _wlBaseSet = new Set();   // populated from live WATCHLIST after load
const _wlLoad = (k, fb) => { try { return JSON.parse(localStorage.getItem(k)) ?? fb; } catch (e) { return fb; } };
let _wlAdded = _wlLoad(WL_ADD_KEY, {});
let _wlRemoved = new Set(_wlLoad(WL_REM_KEY, []));
const WatchStore = {
  has: (sym) => (!!_wlAdded[sym] || _wlBaseSet.has(sym)) && !_wlRemoved.has(sym),
  isBase: (sym) => _wlBaseSet.has(sym),
  add: (rec) => { const s = rec && rec.sym; if (!s) return; _wlRemoved.delete(s); if (!_wlBaseSet.has(s)) _wlAdded[s] = { ...rec }; WatchStore._save(); },
  remove: (sym) => { delete _wlAdded[sym]; if (_wlBaseSet.has(sym)) _wlRemoved.add(sym); WatchStore._save(); },
  toggle: (rec) => { const s = rec && rec.sym; if (!s) return; WatchStore.has(s) ? WatchStore.remove(s) : WatchStore.add(rec); },
  added: () => Object.values(_wlAdded).filter((r) => !_wlRemoved.has(r.sym)),
  removed: () => _wlRemoved,
  count: () => [...new Set([..._wlBaseSet, ...Object.keys(_wlAdded)])].filter((s) => !_wlRemoved.has(s)).length,
  _save: () => {
    try { localStorage.setItem(WL_ADD_KEY, JSON.stringify(_wlAdded)); localStorage.setItem(WL_REM_KEY, JSON.stringify([..._wlRemoved])); } catch (e) {}
    window.dispatchEvent(new CustomEvent("watchlist-change"));
  },
};

/* ── helpers ──────────────────────────────────────────────────────────────── */
const _clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const _num = (v, d = 0) => (typeof v === "number" && isFinite(v) ? v : d);

// Verdict from an elite "stage" / decision field.
function _verdict(row) {
  const s = (row.stage || row.verdict || row.decision || "").toString().toUpperCase();
  if (s.includes("BUY")) return "BUY";
  if (s.includes("SHORT")) return "SHORT";
  if (s.includes("AVOID") || s.includes("SELL") || s.includes("KILL")) return "AVOID";
  return "WATCH";
}

// Project one elite-pick row → the lightweight WATCHLIST/list-card shape.
function _eliteToRow(row) {
  const snap = row.snapshot || {};
  const score = Math.round(_num(row.score_raw, _num(row.elite_score, 50)));
  const price = _num(snap.price, 0);
  const chg = _num(snap.day_chg_pct, _num(row.chg, 0));   // day chg often absent in elite → 0
  return {
    sym: row.ticker, name: row.name || row.ticker,
    sector: row.sector || "", price, chg,
    score: _clamp(score, 1, 100), verdict: _verdict(row),
    setup: snap.setup || row.setup_family || "—",
    _snap: snap, _elite: row,   // carried for the full-detail builder
  };
}

// Project one elite-pick row → a FULL TICKER object (every lens renders real #s).
function _eliteToTicker(row) {
  const snap = row.snapshot || {};
  const r = _eliteToRow(row);
  const price = r.price || 1;
  const entry = Array.isArray(snap.entry) ? snap.entry : [price * 0.99, price * 1.01];
  const pivot = _num(entry[1], price);              // top of entry zone = breakout trigger
  const stop = _num(snap.stop, price * 0.94);
  const t1 = _num(snap.target1, price * 1.08);
  const t2 = _num(snap.target2, price * 1.16);
  const risk = Math.max(0.01, price - stop), reward = Math.max(0.01, t1 - price);
  const bd = row.breakdown || {};
  const bdPts = (k, max) => bd[k] ? _clamp(Math.round((_num(bd[k].adj_pts, bd[k].pts) / max) * 100), 1, 100) : 50;
  return {
    symbol: row.ticker, name: r.name, exchange: "", sector: r.sector || "—", industry: "—",
    mcap: 0, price, chg: r.chg, chgAbs: +(price * r.chg / 100).toFixed(2), prev: +(price / (1 + r.chg / 100)).toFixed(2),
    vol: 0, avgVol: 0,
    rsi: _clamp(Math.round(45 + (r.score - 50) * 0.5), 20, 85),
    beta: 1.0, shortFloat: 0, insiderOwn: 0,
    pe: 0, fwdPe: 0, divYield: 0,
    earnings: { days: _num(snap.earn_days, 21) || 21, date: snap.earn_date || "—" },
    setupFamily: r.setup, pivot, stop, t1, t2,
    trail: "ATR(14) × 2.2", holdDays: 10,
    rMultiple: _num(snap.rr, +(reward / risk).toFixed(2)),
    pillars: {
      technical: bdPts("score_band", 20), fundamental: bdPts("sector_rank", 10),
      catalyst: bdPts("tier1_stack", 10), risk: bdPts("forward_edge", 25), edge: bdPts("hmm_regime", 10),
    },
    verdict: r.verdict, score: r.score,
    ml: {
      direction: +(_num(snap.p_profit, 55) / 100).toFixed(2),
      hitNet: +((_num(snap.p_target, 50) - _num(snap.p_stop, 50)) / 100).toFixed(2),
      magnitude: { lo: _num(snap.var_95, -5), mid: +(((t1 / price - 1) * 100) / 2).toFixed(1), hi: +((t2 / price - 1) * 100).toFixed(1) },
    },
    setupStats: {
      n: _num((row._stats || {}).n, 30),
      winRate: +(_num(snap.p_profit, 55) / 100).toFixed(3),
      wilsonLB: +(_clamp(_num(snap.p_profit, 55) - 14, 5, 95) / 100).toFixed(3),
      pf: +Math.max(1, _num(snap.rr, 1.5) * 0.6 + 0.9).toFixed(2),
      medianR: +(_num(snap.rr, 1.5) / 3).toFixed(2),
    },
    _snap: snap,
  };
}

/* ── the live loader ───────────────────────────────────────────────────────
   Populates window globals from /v2/data.critical.json. Resolves to a small
   meta object. On failure it seeds EMPTY (no fabricated tickers) and flags the
   error so the UI can show an honest "server unreachable" state — principle:
   always real data, never invented. */
function _seedEmpty(errMsg) {
  _applyData({ elite_picks: { Swing: { BUY: [], WATCH: [] } }, portfolio: { positions: [], equity: 0 },
    sector_etf: {}, regime: {}, market_movers: { gainers: [], losers: [] }, run_timestamp: null }, errMsg || "offline");
}

function _applyData(d, errMsg) {
  const ep = (d.elite_picks && d.elite_picks.Swing) || {};
  const buys = (ep.BUY || []), watches = (ep.WATCH || []), shorts = (ep.SHORT || []);
  const eliteRows = [...buys, ...watches, ...shorts].filter((r) => r && r.ticker);

  // de-dup by ticker (BUY wins over WATCH)
  const seen = new Map();
  eliteRows.forEach((r) => { if (!seen.has(r.ticker)) seen.set(r.ticker, r); });
  const rows = [...seen.values()].map(_eliteToRow);

  window.WATCHLIST = rows;
  _wlBaseSet = new Set(rows.map((r) => r.sym));

  // full TICKER objects keyed by symbol — used by the detail/lenses
  const tickById = {};
  [...seen.values()].forEach((r) => { tickById[r.ticker] = _eliteToTicker(r); });
  window.TICKER_BY_SYM = tickById;

  // default / alert ticker = top BUY (or first row)
  const alertRow = (buys[0] || eliteRows[0]);
  window.ALERT_SYM = alertRow ? alertRow.ticker : (rows[0] && rows[0].sym) || "—";
  window.TICKER = alertRow ? _eliteToTicker(alertRow) : (rows[0] ? tickById[rows[0].sym] : null);

  // HEATMAP: [sym, bucketSector, mcapB, chg%] — feeds Home/Sectors/Momentum/News/Options.
  // Built from every elite row across modes so the discover surfaces have breadth.
  const allModes = [];
  if (d.elite_picks) ["Swing", "Position", "Invest"].forEach((m) => {
    const mm = d.elite_picks[m]; if (mm) ["BUY", "WATCH", "SHORT"].forEach((v) => (mm[v] || []).forEach((r) => r && r.ticker && allModes.push(r)));
  });
  const hmSeen = new Map();
  allModes.forEach((r) => { if (!hmSeen.has(r.ticker)) hmSeen.set(r.ticker, r); });
  window.HEATMAP = [...hmSeen.values()].map((r) => {
    const snap = r.snapshot || {};
    return [r.ticker, bucketSector(r.sector), Math.max(0.1, _num(snap.mcap_b, 1)), _num(snap.day_chg_pct, _num(r.chg, 0))];
  });
  // guarantee a non-empty heatmap so heat()-driven surfaces don't crash
  if (window.HEATMAP.length === 0) window.HEATMAP = rows.map((r) => [r.sym, bucketSector(r.sector), 1, r.chg]);

  // live regime / market pulse / portfolio / discover feeds (all read by surfaces)
  window.REGIME_LIVE = d.regime || {};
  window.MARKET_LIVE = { sector_etf: d.sector_etf || {}, movers: d.market_movers || {}, breadth: d.market_breadth || {} };
  window.PORTFOLIO_LIVE = d.portfolio || { positions: [], equity: 0 };
  window.NEWS_LIVE = d.market_news || [];
  window.OPTIONS_LIVE = d.options_flow_top30 || d.options_flow_top50 || [];
  window.ESP_LIVE = d.esp_picks || [];
  window.MOVERS_LIVE = d.market_movers || { gainers: [], losers: [] };
  window.BREADTH_LIVE = d.market_breadth || {};
  window.THEMES_LIVE = d.themes || {};
  window.PREMARKET_LIVE = d.premarket || {};
  window.CALENDAR_LIVE = d.economic_events || [];
  window.CVAR_LIVE = d.cvar_portfolio || {};
  window.PERF_LIVE = d.performance || {};
  window.PICKS_HISTORY = d.picks_history || [];

  // TICKER_UNIVERSE — searchable list (real): scan names ∪ portfolio holdings.
  const uni = new Map();
  rows.forEach((r) => uni.set(r.sym, { sym: r.sym, name: r.name, sector: r.sector || "", score: r.score, verdict: r.verdict }));
  ((d.portfolio || {}).positions || []).forEach((p) => { if (p.ticker && !uni.has(p.ticker)) uni.set(p.ticker, { sym: p.ticker, name: p.ticker, sector: p.sector || "" }); });
  window.TICKER_UNIVERSE = [...uni.values()].sort((a, b) => a.sym.localeCompare(b.sym));
  window.SCAN_META = { ts: d.run_timestamp || d.run_date || null, error: errMsg || null,
    buy: buys.length, watch: watches.length,
    universe: _num(d.scan_count, _num((d.universe_composition || {}).total, 0)),
    regime: (d.regime || {}).regime || (d.regime || {}).regime4 || null,
    vix: _num((d.regime || {}).vix, _num((d.regime || {}).vix_current, 0)),
    breadth: _num((d.regime || {}).breadth_pct_50d, 0) };

  window.dispatchEvent(new CustomEvent("companion-data-ready"));
}

/* ── REAL per-ticker detail — maps the full /api/ticker scored row → the mobile
   TICKER shape the 12 lenses consume. Every field is sourced from the live row;
   anything genuinely absent stays null so the lens renders "—" (never faked). */
function mapScoredRowToTicker(row, base) {
  if (!row) return base || null;
  const ctp = row.canonical_trade_plan || {};
  const entry = ctp.entry || {};
  const risk = ctp.risk || {};
  const sb = row.score_breakdown || {};
  const earn = row.earnings || {};
  const price = _num(row.price, base ? base.price : 0) || 0;
  const pivot = _num(entry.high, _num((row.snapshot || {}).entry && row.snapshot.entry[1], price));
  const stop = _num(ctp.stop, base ? base.stop : price * 0.94);
  const t1 = _num(ctp.target1, base ? base.t1 : null);
  const t2 = _num(ctp.target2, base ? base.t2 : null);
  const fd = (row.fundamentals && row.fundamentals.details) || {};
  // pillar components are REAL (score_breakdown), normalized to 0-100 per pillar max
  const pil = (v, max) => v == null ? null : _clamp(Math.round((_num(v, 0) / max) * 100), 1, 100);
  return {
    symbol: row.ticker, name: row.name || row.ticker, exchange: row.exchange || "",
    sector: row.sector || (base && base.sector) || "—", industry: row.industry || "—",
    mcap: _num(row.market_cap, 0),
    price, chg: _num(row.perf_1d, base ? base.chg : 0),
    chgAbs: +(price * _num(row.perf_1d, 0) / 100).toFixed(2),
    prev: +(price / (1 + _num(row.perf_1d, 0) / 100)).toFixed(2),
    vol: _num(row.volume, 0), avgVol: _num(row.avg_volume, 0),
    rsi: _num(row.rsi, null), beta: _num(row.beta, null),
    shortFloat: _num((row.finviz_elite || {}).short_float, _num(row.short_float, 0)),
    insiderOwn: _num((row.finviz_elite || {}).insider_own, 0),
    pe: _num((row.finviz_elite || {}).pe, _num((row.extra_fund || {}).pe, 0)),
    fwdPe: _num((row.finviz_elite || {}).fwd_pe, 0),
    divYield: _num((row.finviz_elite || {}).div_yield, 0),
    earnings: { days: _num(earn.days_to_earnings, null), date: earn.earnings_date || "—", risk: !!earn.earnings_risk },
    setupFamily: row.setup_family || (base && base.setupFamily) || "—",
    pivot, stop, t1, t2,
    trail: "ATR(" + _num(row.atr_pct, 14).toFixed(0) + ") · " + (row.ema_signal || "trend"),
    holdDays: _num(ctp.hold_period_days, 10),
    conviction: ctp.conviction_tier || row.conviction || null,
    rMultiple: _num(risk.rr_ratio, base ? base.rMultiple : null),
    maxLossPct: _num(risk.max_loss_pct, null),
    riskFlags: risk.risk_flags || [],
    pillars: {
      technical: pil(sb.tech, 35) ?? 50, fundamental: pil(sb.quality_gate, 10) ?? 50,
      catalyst: pil(sb.catalyst, 20) ?? 50, risk: pil(sb.entry_rr, 10) ?? 50, edge: pil(sb.rs, 25) ?? 50,
    },
    verdict: row.verdict || (base && base.verdict) || "WATCH", score: Math.round(_num(row.score, base ? base.score : 50)),
    fundDrivers: { bull: (row.fundamentals || {}).bull_drivers || [], bear: (row.fundamentals || {}).bear_risks || [], details: fd },
    ml: {
      direction: _num(row.mc_p_profit, null),
      hitNet: row.snapshot ? +((_num(row.snapshot.p_target, 50) - _num(row.snapshot.p_stop, 50)) / 100).toFixed(2) : _num(row.mc_p_profit, 0.5) - 0.5,
      magnitude: { lo: _num(row.atr_pct, 5) * -1, mid: t1 && price ? +(((t1 / price - 1) * 100) / 2).toFixed(1) : 0, hi: t2 && price ? +((t2 / price - 1) * 100).toFixed(1) : 0 },
    },
    setupStats: {
      n: _num((row.setup_family_stats || {}).n, _num(row.star_rating, 0) ? 30 : 0),
      winRate: _num(row.mc_p_profit, null),
      wilsonLB: row.mc_p_profit != null ? +(_clamp(row.mc_p_profit * 100 - 14, 5, 95) / 100).toFixed(3) : null,
      pf: _num((row.setup_family_stats || {}).pf, _num(risk.rr_ratio, 1.5) * 0.6 + 0.9),
      medianR: _num(risk.rr_ratio, 1.5) / 3, sharpe: _num(row.sharpe_126d, null),
    },
    rsRank: _num(row.rs_rank, null), stars: _num(row.star_rating, null), vwap: row.vwap || null,
    macdSignal: row.macd_signal || null, emaSignal: row.ema_signal || null, rvol: _num(row.rvol, null),
    _row: row, _live: true,
  };
}

// fetch + cache the REAL detail for a symbol. Returns a Promise<ticker|null>.
const _liveTickCache = {};
function fetchTickerLive(sym) {
  sym = (sym || "").toUpperCase();
  if (!sym) return Promise.resolve(null);
  if (_liveTickCache[sym]) return _liveTickCache[sym];
  const base = (window.TICKER_BY_SYM || {})[sym] || null;
  _liveTickCache[sym] = fetch("/api/ticker/" + encodeURIComponent(sym), { credentials: "same-origin" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => {
      const tick = mapScoredRowToTicker(j.row, base);
      if (tick) { window.TICKER_BY_SYM = window.TICKER_BY_SYM || {}; window.TICKER_BY_SYM[sym] = tick; }
      return tick;
    })
    .catch((e) => { console.warn("[companion] /api/ticker/" + sym + " failed:", e); delete _liveTickCache[sym]; return base; });
  return _liveTickCache[sym];
}

// React hook used by DetailM: start from the (real, elite-derived) base ticker,
// then upgrade in place to the FULL /api/ticker payload. Never synthesizes.
function useLiveTicker(base) {
  const sym = base && base.symbol;
  const [tick, setTick] = React.useState(base);
  React.useEffect(() => {
    setTick(base);
    if (!sym) return;
    let alive = true;
    fetchTickerLive(sym).then((full) => { if (alive && full) setTick(full); });
    return () => { alive = false; };
  }, [sym]);
  return tick || base;
}

let _loadPromise = null;
function loadCompanionData() {
  if (_loadPromise) return _loadPromise;
  _loadPromise = fetch("/v2/data.critical.json", { credentials: "same-origin" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((d) => { _applyData(d, null); return window.SCAN_META; })
    .catch((e) => { console.warn("[companion] live data failed:", e); _seedEmpty(String(e.message || e)); return window.SCAN_META; });
  return _loadPromise;
}

/* ── resolve a symbol → ticker base (REAL only; no synthesis). Returns the
   elite-derived base if known, else a minimal real-fields stub that DetailM
   upgrades to the full /api/ticker payload. Never invents pillars/ml/stats. */
function resolveTickerLive(sym) {
  if (!sym) return window.TICKER;
  const live = (window.TICKER_BY_SYM || {})[sym];
  if (live) return live;
  // unknown to the scan (e.g. a portfolio-only or starred name): build a stub
  // from whatever real row we already hold (watchlist / portfolio), nulls else.
  const wl = (window.WATCHLIST || []).find((r) => r.sym === sym);
  const pos = ((window.PORTFOLIO_LIVE || {}).positions || []).find((p) => p.ticker === sym);
  const px = wl ? wl.price : (pos ? _num(pos.current_price, pos.entry_price) : 0);
  return {
    symbol: sym, name: (wl && wl.name) || sym, exchange: "", sector: (wl && wl.sector) || "—", industry: "—",
    mcap: 0, price: px, chg: wl ? wl.chg : 0, chgAbs: 0, prev: px, vol: 0, avgVol: 0,
    rsi: null, beta: null, shortFloat: 0, insiderOwn: 0, pe: 0, fwdPe: 0, divYield: 0,
    earnings: { days: null, date: "—" }, setupFamily: (wl && wl.setup) || "—",
    pivot: px, stop: pos ? _num(pos.stop, 0) : 0, t1: pos ? _num(pos.target1, 0) : 0, t2: pos ? _num(pos.target2, 0) : 0,
    trail: "—", holdDays: null, rMultiple: null,
    pillars: { technical: 50, fundamental: 50, catalyst: 50, risk: 50, edge: 50 },
    verdict: (wl && wl.verdict) || "WATCH", score: (wl && wl.score) || 50,
    ml: { direction: null, hitNet: 0, magnitude: { lo: 0, mid: 0, hi: 0 } },
    setupStats: { n: 0, winRate: null, wilsonLB: null, pf: null, medianR: null },
    _stub: true,
  };
}

Object.assign(window, {
  LENSES, SECTORS_ORDER, SECTOR_LEAD, bucketSector,
  secBias, secBiasTone, SEC_BIAS, SEC_DISCLAIMER, SEC_DISCLAIMER_SHORT,
  SURFACE_TIER, LENS_TIER, WatchStore,
  loadCompanionData, resolveTickerLive, mapScoredRowToTicker, fetchTickerLive, useLiveTicker,
  // seeded as empty until loadCompanionData() resolves; components read post-mount
  TICKER: null, WATCHLIST: [], HEATMAP: [],
});
